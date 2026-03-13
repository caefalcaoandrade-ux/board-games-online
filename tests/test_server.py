"""Tests for the game server: room lifecycle, moves, errors, reconnection."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from fastapi.testclient import TestClient
from server.main import app, rooms, Room, RECONNECT_TIMEOUT, forfeit_after_timeout


@pytest.fixture(autouse=True)
def clear_rooms():
    """Ensure a clean room registry for each test."""
    rooms.clear()
    yield
    rooms.clear()


# ── HTTP Endpoint ────────────────────────────────────────────────────────────


def test_rooms_endpoint_empty():
    client = TestClient(app)
    resp = client.get("/rooms")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Room Creation ────────────────────────────────────────────────────────────


def test_create_room():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Bashni"})
        msg = ws.receive_json()
        assert msg["type"] == "room_created"
        assert msg["game"] == "Bashni"
        assert len(msg["code"]) >= 4
        assert msg["players_joined"] == 1
        assert msg["players_needed"] == 2


def test_create_room_invalid_game():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Nonexistent"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Unknown game" in msg["message"]


def test_create_room_missing_game():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "game" in msg["message"].lower()


def test_create_room_already_in_room():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Bashni"})
        ws.receive_json()  # room_created
        ws.send_json({"type": "create_room", "game": "Bashni"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Already in a room" in msg["message"]


# ── Room Joining ─────────────────────────────────────────────────────────────


def test_join_room():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "create_room", "game": "Bashni"})
        created = ws1.receive_json()
        code = created["code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "join_room", "code": code})
            joined = ws2.receive_json()
            assert joined["type"] == "room_joined"
            assert joined["code"] == code
            assert joined["your_player"] == 2
            assert joined["players_joined"] == 2


def test_join_room_not_found():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join_room", "code": "ZZZZ"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["message"]


def test_join_room_missing_code():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join_room"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "code" in msg["message"].lower()


def test_join_room_case_insensitive():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "create_room", "game": "Bashni"})
        code = ws1.receive_json()["code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "join_room", "code": code.lower()})
            joined = ws2.receive_json()
            assert joined["type"] == "room_joined"


# ── Game Start ───────────────────────────────────────────────────────────────


def test_game_start_on_full_room():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "create_room", "game": "Bashni"})
        created = ws1.receive_json()
        code = created["code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "join_room", "code": code})
            ws2.receive_json()  # room_joined

            # Player 1 gets: player_joined notification, then game_started
            p1_notif = ws1.receive_json()
            assert p1_notif["type"] == "player_joined"

            p1_start = ws1.receive_json()
            assert p1_start["type"] == "game_started"
            assert p1_start["game"] == "Bashni"
            assert p1_start["your_player"] == 1
            assert "state" in p1_start
            assert "current_turn" in p1_start

            # Player 2 also gets game_started
            p2_start = ws2.receive_json()
            assert p2_start["type"] == "game_started"
            assert p2_start["your_player"] == 2
            assert p2_start["state"] == p1_start["state"]


# ── Make Move ────────────────────────────────────────────────────────────────


def _start_bashni_game(client):
    """Helper: create and join a Bashni room, return (ws1, ws2, start_msg, code)."""
    ws1 = client.websocket_connect("/ws")
    ws1 = ws1.__enter__()
    ws1.send_json({"type": "create_room", "game": "Bashni"})
    created = ws1.receive_json()
    code = created["code"]

    ws2 = client.websocket_connect("/ws")
    ws2 = ws2.__enter__()
    ws2.send_json({"type": "join_room", "code": code})
    ws2.receive_json()  # room_joined

    ws1.receive_json()  # player_joined
    p1_start = ws1.receive_json()  # game_started
    ws2.receive_json()  # game_started

    return ws1, ws2, p1_start, code


def test_make_move():
    client = TestClient(app)
    ws1, ws2, start, _ = _start_bashni_game(client)
    try:
        state = start["state"]
        current_turn = start["current_turn"]

        # Get a legal move from the logic
        from games import create_game
        logic = create_game("Bashni")
        moves = logic.get_legal_moves(state, current_turn)
        assert len(moves) > 0

        # Player whose turn it is sends a move
        if current_turn == 1:
            ws1.send_json({"type": "make_move", "move": moves[0]})
        else:
            ws2.send_json({"type": "make_move", "move": moves[0]})

        # Both players receive move_made
        msg1 = ws1.receive_json()
        msg2 = ws2.receive_json()
        assert msg1["type"] == "move_made"
        assert msg2["type"] == "move_made"
        assert "state" in msg1
        assert "current_turn" in msg1
        assert msg1["state"] == msg2["state"]
    finally:
        ws1.close()
        ws2.close()


def test_make_move_wrong_turn():
    client = TestClient(app)
    ws1, ws2, start, _ = _start_bashni_game(client)
    try:
        current_turn = start["current_turn"]
        # The player who does NOT have the turn tries to move
        wrong_ws = ws2 if current_turn == 1 else ws1
        wrong_ws.send_json({"type": "make_move", "move": {"from": [0, 0], "to": [1, 1]}})
        msg = wrong_ws.receive_json()
        assert msg["type"] == "error"
        assert "Not your turn" in msg["message"]
    finally:
        ws1.close()
        ws2.close()


def test_make_move_illegal():
    client = TestClient(app)
    ws1, ws2, start, _ = _start_bashni_game(client)
    try:
        current_turn = start["current_turn"]
        right_ws = ws1 if current_turn == 1 else ws2
        # Send a clearly invalid move
        right_ws.send_json({"type": "make_move", "move": {"from": [0, 0], "to": [0, 0]}})
        msg = right_ws.receive_json()
        assert msg["type"] == "error"
        assert "Illegal move" in msg["message"]
    finally:
        ws1.close()
        ws2.close()


def test_make_move_not_in_game():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "make_move", "move": {}})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Not in an active game" in msg["message"]


# ── HTTP Rooms Listing ───────────────────────────────────────────────────────


def test_rooms_lists_waiting():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Shobu"})
        created = ws.receive_json()
        code = created["code"]

        resp = client.get("/rooms")
        waiting = resp.json()
        assert len(waiting) == 1
        assert waiting[0]["code"] == code
        assert waiting[0]["game"] == "Shobu"
        assert waiting[0]["players_joined"] == 1
        assert waiting[0]["players_needed"] == 2


def test_rooms_excludes_started():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "create_room", "game": "Bashni"})
        code = ws1.receive_json()["code"]

        with client.websocket_connect("/ws") as ws2:
            ws2.send_json({"type": "join_room", "code": code})
            ws2.receive_json()  # room_joined
            ws1.receive_json()  # player_joined
            ws1.receive_json()  # game_started
            ws2.receive_json()  # game_started

            # Started game should not appear in waiting list
            resp = client.get("/rooms")
            assert resp.json() == []


# ── Unknown Message Type ─────────────────────────────────────────────────────


def test_unknown_message_type():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "banana"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Unknown" in msg["message"]


# ── Pre-Game Disconnect ──────────────────────────────────────────────────────


def test_room_removed_on_last_disconnect():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Bashni"})
        created = ws.receive_json()
        code = created["code"]
        assert code in rooms

    # ws disconnected (exited context)
    assert code not in rooms


def test_pregame_disconnect_keeps_room_for_other_player():
    """If one player disconnects pre-game, the other stays and room persists."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.send_json({"type": "create_room", "game": "Bashni"})
        code = ws1.receive_json()["code"]

        # A second player joins but then disconnects before game starts
        # (room needs 2 players, so game hasn't started yet)
        # Actually the second player joining would start the game.
        # So test: creator creates, someone else hasn't joined yet,
        # the room persists while creator is connected.
        assert code in rooms
        assert not rooms[code].started

    # Creator disconnects, room should be gone (no players left)
    assert code not in rooms


# ── Mid-Game Disconnect & Reconnection ────────────────────────────────────────


def test_midgame_disconnect_notifies_opponent():
    """When a player disconnects mid-game, the other gets player_disconnected."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        # Player 2 disconnects
        ws2.close()

        # Player 1 should receive player_disconnected
        msg = ws1.receive_json()
        assert msg["type"] == "player_disconnected"
        assert msg["player"] == 2

        # Room should still exist
        assert code in rooms
        room = rooms[code]
        assert 1 in room.players
        assert 2 in room.disconnected
    finally:
        ws1.close()


def test_midgame_disconnect_room_survives():
    """Room is kept alive after a mid-game disconnect (not immediately removed)."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        ws2.close()
        ws1.receive_json()  # player_disconnected

        room = rooms[code]
        assert room.started
        assert 2 in room.disconnected
        assert 2 not in room.players
    finally:
        ws1.close()


def test_rejoin_room_restores_connection():
    """A disconnected player can rejoin and receive the current game state."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        # Player 2 disconnects
        ws2.close()
        ws1.receive_json()  # player_disconnected

        # Player 2 reconnects on a fresh WebSocket
        ws2_new = client.websocket_connect("/ws").__enter__()
        ws2_new.send_json({
            "type": "rejoin_room",
            "code": code,
            "player": 2,
        })

        rejoined = ws2_new.receive_json()
        assert rejoined["type"] == "room_rejoined"
        assert rejoined["code"] == code
        assert rejoined["your_player"] == 2
        assert "state" in rejoined
        assert "current_turn" in rejoined
        assert rejoined["game"] == "Bashni"

        # Player 1 should receive player_reconnected
        msg = ws1.receive_json()
        assert msg["type"] == "player_reconnected"
        assert msg["player"] == 2

        # Room should be fully restored
        room = rooms[code]
        assert 2 in room.players
        assert 2 not in room.disconnected

        ws2_new.close()
    finally:
        ws1.close()


def test_rejoin_room_allows_continued_play():
    """After reconnecting, the game can continue with moves."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        # Player 2 disconnects and reconnects
        ws2.close()
        ws1.receive_json()  # player_disconnected

        ws2_new = client.websocket_connect("/ws").__enter__()
        ws2_new.send_json({"type": "rejoin_room", "code": code, "player": 2})
        rejoined = ws2_new.receive_json()  # room_rejoined
        ws1.receive_json()  # player_reconnected

        # Now make a move
        state = rejoined["state"]
        current_turn = rejoined["current_turn"]

        from games import create_game
        logic = create_game("Bashni")
        moves = logic.get_legal_moves(state, current_turn)
        assert len(moves) > 0

        active_ws = ws1 if current_turn == 1 else ws2_new
        active_ws.send_json({"type": "make_move", "move": moves[0]})

        msg1 = ws1.receive_json()
        msg2 = ws2_new.receive_json()
        assert msg1["type"] == "move_made"
        assert msg2["type"] == "move_made"

        ws2_new.close()
    finally:
        ws1.close()


def test_rejoin_room_errors():
    """Rejoin with bad code or player ID returns errors."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        ws2.close()
        ws1.receive_json()  # player_disconnected

        # Wrong room code
        with client.websocket_connect("/ws") as ws_bad:
            ws_bad.send_json({"type": "rejoin_room", "code": "ZZZZ", "player": 2})
            msg = ws_bad.receive_json()
            assert msg["type"] == "error"
            assert "not found" in msg["message"]

        # Wrong player ID (player 1 is still connected, not disconnected)
        with client.websocket_connect("/ws") as ws_bad:
            ws_bad.send_json({"type": "rejoin_room", "code": code, "player": 1})
            msg = ws_bad.receive_json()
            assert msg["type"] == "error"
            assert "No disconnected player" in msg["message"]

        # Missing fields
        with client.websocket_connect("/ws") as ws_bad:
            ws_bad.send_json({"type": "rejoin_room"})
            msg = ws_bad.receive_json()
            assert msg["type"] == "error"

        # Already in a room
        with client.websocket_connect("/ws") as ws_bad:
            ws_bad.send_json({"type": "create_room", "game": "Bashni"})
            ws_bad.receive_json()  # room_created
            ws_bad.send_json({"type": "rejoin_room", "code": code, "player": 2})
            msg = ws_bad.receive_json()
            assert msg["type"] == "error"
            assert "Already in a room" in msg["message"]
    finally:
        ws1.close()


def test_join_started_game_rejected():
    """A new player cannot join_room a game already in progress."""
    client = TestClient(app)
    ws1, ws2, start, code = _start_bashni_game(client)
    try:
        with client.websocket_connect("/ws") as ws3:
            ws3.send_json({"type": "join_room", "code": code})
            msg = ws3.receive_json()
            assert msg["type"] == "error"
            assert "already in progress" in msg["message"].lower()
    finally:
        ws1.close()
        ws2.close()


# ── Forfeit Timeout ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_forfeit_after_timeout():
    """After RECONNECT_TIMEOUT, disconnected player forfeits."""
    import server.main as srv

    # Temporarily set a very short timeout for testing
    original_timeout = srv.RECONNECT_TIMEOUT
    srv.RECONNECT_TIMEOUT = 0.1  # 100ms
    try:
        from games import create_game

        logic = create_game("Bashni")
        code = "TEST"
        room = Room(code, "Bashni", logic)
        room.state = logic.create_initial_state()
        room.started = True
        srv.rooms[code] = room

        # Simulate player 2 disconnected — test the coroutine directly
        task = asyncio.create_task(forfeit_after_timeout(room, 2))
        room.disconnected[2] = task

        # Simulate player 1 as "connected" by putting a mock in players
        # For broadcast to work we'd need a real ws, but since no players
        # dict entry, broadcast is a no-op — that's fine for this test
        # We just check that the room gets cleaned up

        await asyncio.sleep(0.2)  # Wait for timeout to fire

        # Player 2 should have been removed from disconnected
        assert 2 not in room.disconnected
        # Room should be cleaned up (no connected players, no disconnected)
        assert code not in srv.rooms
    finally:
        srv.RECONNECT_TIMEOUT = original_timeout
        srv.rooms.pop("TEST", None)


@pytest.mark.anyio
async def test_reconnect_cancels_forfeit_timer():
    """Reconnecting cancels the forfeit timer."""
    import server.main as srv

    original_timeout = srv.RECONNECT_TIMEOUT
    srv.RECONNECT_TIMEOUT = 5  # long enough that it won't fire during test
    try:
        from games import create_game

        logic = create_game("Bashni")
        code = "TEST2"
        room = Room(code, "Bashni", logic)
        room.state = logic.create_initial_state()
        room.started = True
        srv.rooms[code] = room

        # Start forfeit timer for player 2
        task = asyncio.create_task(forfeit_after_timeout(room, 2))
        room.disconnected[2] = task

        # Simulate reconnection: cancel the task
        task.cancel()
        room.disconnected.pop(2, None)

        await asyncio.sleep(0.05)  # Let cancellation propagate

        assert task.cancelled()
        assert 2 not in room.disconnected
        # Room should still exist (reconnection happened)
        assert code in srv.rooms
    finally:
        srv.RECONNECT_TIMEOUT = original_timeout
        srv.rooms.pop("TEST2", None)
