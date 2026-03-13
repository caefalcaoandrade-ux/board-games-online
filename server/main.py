"""
FastAPI server with WebSocket-based multiplayer rooms for board games.

Run with:  uvicorn server.main:app --reload
"""

import asyncio
import os
import sys
import random
import string

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# Ensure the games package is importable when running from the server/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games import list_games, create_game

app = FastAPI(title="Board Games Online")

RECONNECT_TIMEOUT = 60  # seconds before forfeit


# ── Room Model ────────────────────────────────────────────────────────────────


class Room:
    """A single game session between players."""

    def __init__(self, code: str, game_name: str, logic):
        self.code = code
        self.game_name = game_name
        self.logic = logic
        self.needed: int = logic.player_count
        self.players: dict[int, WebSocket] = {}          # connected players
        self.disconnected: dict[int, asyncio.Task] = {}  # player_id -> timeout task
        self.state: dict | None = None
        self.started: bool = False

    @property
    def is_full(self) -> bool:
        return len(self.players) + len(self.disconnected) >= self.needed


# ── Room Storage ──────────────────────────────────────────────────────────────

rooms: dict[str, Room] = {}

CODE_CHARS = string.ascii_uppercase + string.digits
CODE_LENGTH = 4


def generate_room_code() -> str:
    """Generate a short unique room code (4 uppercase alphanumeric chars)."""
    for _ in range(100):
        code = "".join(random.choices(CODE_CHARS, k=CODE_LENGTH))
        if code not in rooms:
            return code
    # Fall back to a longer code if too many collisions
    return "".join(random.choices(CODE_CHARS, k=CODE_LENGTH + 2))


# ── Helpers ───────────────────────────────────────────────────────────────────


async def send(ws: WebSocket, msg: dict):
    """Send a JSON message to one client."""
    await ws.send_json(msg)


async def broadcast(room: Room, msg: dict):
    """Send a JSON message to every connected player in a room."""
    for ws in list(room.players.values()):
        try:
            await ws.send_json(msg)
        except Exception:
            pass


def cleanup_room(room: Room):
    """Cancel all pending reconnect timers and remove the room."""
    for task in room.disconnected.values():
        task.cancel()
    room.disconnected.clear()
    rooms.pop(room.code, None)


async def start_game(room: Room):
    """Initialize the game state and notify all players."""
    room.state = room.logic.create_initial_state()
    room.started = True
    current_turn = room.logic.get_current_player(room.state)

    for pid, ws in room.players.items():
        await send(ws, {
            "type": "game_started",
            "game": room.game_name,
            "state": room.state,
            "your_player": pid,
            "current_turn": current_turn,
        })


async def forfeit_after_timeout(room: Room, player_id: int):
    """Wait for reconnection timeout, then forfeit the disconnected player."""
    try:
        await asyncio.sleep(RECONNECT_TIMEOUT)
    except asyncio.CancelledError:
        return  # Player reconnected — timer cancelled

    # Timeout expired
    room.disconnected.pop(player_id, None)

    remaining = list(room.players.keys())

    if len(remaining) == 1 and not room.disconnected:
        # One player left, no other pending reconnects — they win
        await broadcast(room, {
            "type": "game_over",
            "state": room.state,
            "winner": remaining[0],
            "is_draw": False,
            "reason": "forfeit",
        })
        cleanup_room(room)
    elif not remaining and not room.disconnected:
        # Nobody left at all
        rooms.pop(room.code, None)
    else:
        # Other players still present or pending — just announce the forfeit
        await broadcast(room, {
            "type": "player_forfeited",
            "player": player_id,
        })


# ── WebSocket Endpoint ────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    player_room: Room | None = None
    player_id: int | None = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            # ── Create Room ────────────────────────────────────────────
            if msg_type == "create_room":
                game_name = data.get("game")
                if not game_name:
                    await send(ws, {
                        "type": "error",
                        "message": "Missing 'game' field.",
                    })
                    continue

                if player_room is not None:
                    await send(ws, {
                        "type": "error",
                        "message": "Already in a room.",
                    })
                    continue

                try:
                    logic = create_game(game_name)
                except KeyError as e:
                    await send(ws, {"type": "error", "message": str(e)})
                    continue

                code = generate_room_code()
                room = Room(code, game_name, logic)
                rooms[code] = room

                player_id = 1
                room.players[player_id] = ws
                player_room = room

                await send(ws, {
                    "type": "room_created",
                    "code": code,
                    "game": game_name,
                    "players_joined": len(room.players),
                    "players_needed": room.needed,
                })

                # Single-player game starts immediately
                if room.is_full:
                    await start_game(room)

            # ── Join Room ──────────────────────────────────────────────
            elif msg_type == "join_room":
                code = data.get("code", "").strip().upper()
                if not code:
                    await send(ws, {
                        "type": "error",
                        "message": "Missing 'code' field.",
                    })
                    continue

                if player_room is not None:
                    await send(ws, {
                        "type": "error",
                        "message": "Already in a room.",
                    })
                    continue

                room = rooms.get(code)
                if room is None:
                    await send(ws, {
                        "type": "error",
                        "message": f"Room '{code}' not found.",
                    })
                    continue

                if room.started:
                    await send(ws, {
                        "type": "error",
                        "message": "Game already in progress.",
                    })
                    continue

                if room.is_full:
                    await send(ws, {
                        "type": "error",
                        "message": "Room is full.",
                    })
                    continue

                player_id = len(room.players) + 1
                room.players[player_id] = ws
                player_room = room

                await send(ws, {
                    "type": "room_joined",
                    "code": code,
                    "game": room.game_name,
                    "your_player": player_id,
                    "players_joined": len(room.players),
                    "players_needed": room.needed,
                })

                # Notify existing players that someone joined
                for pid, other_ws in room.players.items():
                    if pid != player_id:
                        await send(other_ws, {
                            "type": "player_joined",
                            "players_joined": len(room.players),
                            "players_needed": room.needed,
                        })

                if room.is_full:
                    await start_game(room)

            # ── Rejoin Room (reconnection) ─────────────────────────────
            elif msg_type == "rejoin_room":
                code = data.get("code", "").strip().upper()
                rejoin_pid = data.get("player")

                if not code or rejoin_pid is None:
                    await send(ws, {
                        "type": "error",
                        "message": "Missing 'code' or 'player' field.",
                    })
                    continue

                if player_room is not None:
                    await send(ws, {
                        "type": "error",
                        "message": "Already in a room.",
                    })
                    continue

                room = rooms.get(code)
                if room is None:
                    await send(ws, {
                        "type": "error",
                        "message": f"Room '{code}' not found.",
                    })
                    continue

                if rejoin_pid not in room.disconnected:
                    await send(ws, {
                        "type": "error",
                        "message": "No disconnected player with that ID in this room.",
                    })
                    continue

                # Cancel the forfeit timer
                task = room.disconnected.pop(rejoin_pid)
                task.cancel()

                # Restore connection
                room.players[rejoin_pid] = ws
                player_id = rejoin_pid
                player_room = room

                current_turn = room.logic.get_current_player(room.state)
                await send(ws, {
                    "type": "room_rejoined",
                    "code": code,
                    "game": room.game_name,
                    "your_player": player_id,
                    "state": room.state,
                    "current_turn": current_turn,
                })

                # Notify others that this player is back
                for pid, other_ws in room.players.items():
                    if pid != player_id:
                        try:
                            await send(other_ws, {
                                "type": "player_reconnected",
                                "player": player_id,
                            })
                        except Exception:
                            pass

            # ── Make Move ──────────────────────────────────────────────
            elif msg_type == "make_move":
                if player_room is None or not player_room.started:
                    await send(ws, {
                        "type": "error",
                        "message": "Not in an active game.",
                    })
                    continue

                room = player_room
                current_turn = room.logic.get_current_player(room.state)

                if player_id != current_turn:
                    await send(ws, {
                        "type": "error",
                        "message": "Not your turn.",
                    })
                    continue

                move = data.get("move")
                if move is None:
                    await send(ws, {
                        "type": "error",
                        "message": "Missing 'move' field.",
                    })
                    continue

                if not room.logic.is_valid_move(room.state, player_id, move):
                    await send(ws, {
                        "type": "error",
                        "message": "Illegal move.",
                    })
                    continue

                room.state = room.logic.apply_move(
                    room.state, player_id, move
                )
                status = room.logic.get_game_status(room.state)

                if status["is_over"]:
                    await broadcast(room, {
                        "type": "game_over",
                        "state": room.state,
                        "winner": status["winner"],
                        "is_draw": status["is_draw"],
                    })
                    cleanup_room(room)
                    player_room = None
                else:
                    next_turn = room.logic.get_current_player(room.state)
                    await broadcast(room, {
                        "type": "move_made",
                        "state": room.state,
                        "current_turn": next_turn,
                    })

            # ── Unknown ────────────────────────────────────────────────
            else:
                await send(ws, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type!r}",
                })

    except WebSocketDisconnect:
        pass
    finally:
        if player_room is not None and player_id is not None:
            room = player_room

            if room.started:
                # Mid-game disconnect: keep the room, start forfeit timer
                room.players.pop(player_id, None)
                task = asyncio.create_task(
                    forfeit_after_timeout(room, player_id)
                )
                room.disconnected[player_id] = task

                # Notify remaining connected players
                for other_ws in list(room.players.values()):
                    try:
                        await other_ws.send_json({
                            "type": "player_disconnected",
                            "player": player_id,
                        })
                    except Exception:
                        pass
            else:
                # Pre-game disconnect: just remove the player
                room.players.pop(player_id, None)
                if not room.players:
                    rooms.pop(room.code, None)


# ── HTTP Endpoints ────────────────────────────────────────────────────────────


@app.get("/rooms")
async def get_waiting_rooms():
    """Return rooms currently waiting for players to join."""
    return [
        {
            "code": room.code,
            "game": room.game_name,
            "players_joined": len(room.players),
            "players_needed": room.needed,
        }
        for room in rooms.values()
        if not room.started
    ]
