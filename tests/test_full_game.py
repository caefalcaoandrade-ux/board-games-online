"""Simulate a full game between two WebSocket clients.

Connects two players, creates a room, joins, then plays moves (always
picking the first legal move) until the game ends.  Every message sent
and received is printed so you can see the full communication flow.

Usage:  python tests/test_full_game.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from server.main import app, rooms
from games import create_game

GAME = "Bashni"
MAX_MOVES = 1000


# ── Formatting helpers ───────────────────────────────────────────────────────

def short_state(state, limit=200):
    """Return a compact representation of a game state dict."""
    s = json.dumps(state)
    if len(s) <= limit:
        return s
    return f"<state: {len(s)} bytes JSON>"


def fmt_recv(msg):
    """Format a received message for display, compacting the state."""
    d = dict(msg)
    if "state" in d:
        d["state"] = short_state(d["state"])
    return json.dumps(d, indent=2)


def fmt_move(move):
    """Format a move for display, truncating if very long."""
    s = json.dumps(move)
    return s if len(s) <= 120 else s[:117] + "..."


# ── Main simulation ─────────────────────────────────────────────────────────

def main():
    rooms.clear()
    client = TestClient(app)
    logic = create_game(GAME)

    ws1 = client.websocket_connect("/ws").__enter__()
    ws2 = client.websocket_connect("/ws").__enter__()

    sep = "=" * 70
    print(sep)
    print(f"  FULL GAME SIMULATION: {GAME}")
    print(sep)

    # ── Step 1: Player 1 creates the room ────────────────────────────────

    out = {"type": "create_room", "game": GAME}
    print(f"\n→ P1 SEND: {json.dumps(out)}")
    ws1.send_json(out)

    msg = ws1.receive_json()
    print(f"← P1 RECV: {fmt_recv(msg)}")
    assert msg["type"] == "room_created"
    code = msg["code"]

    # ── Step 2: Player 2 joins the room ──────────────────────────────────

    out = {"type": "join_room", "code": code}
    print(f"\n→ P2 SEND: {json.dumps(out)}")
    ws2.send_json(out)

    msg = ws2.receive_json()                    # room_joined
    print(f"← P2 RECV: {fmt_recv(msg)}")
    assert msg["type"] == "room_joined"

    msg = ws1.receive_json()                    # player_joined (to P1)
    print(f"← P1 RECV: {fmt_recv(msg)}")
    assert msg["type"] == "player_joined"

    # ── Step 3: Both receive game_started ─────────────────────────────────

    p1_start = ws1.receive_json()
    print(f"← P1 RECV: {fmt_recv(p1_start)}")
    assert p1_start["type"] == "game_started"

    p2_start = ws2.receive_json()
    print(f"← P2 RECV: {fmt_recv(p2_start)}")
    assert p2_start["type"] == "game_started"

    state = p1_start["state"]
    current_turn = p1_start["current_turn"]

    print(f"\n{sep}")
    print(f"  GAME STARTED — Player {current_turn} moves first")
    print(f"{sep}")

    # ── Step 4: Game loop — alternate moves until game over ──────────────

    move_num = 0
    while move_num < MAX_MOVES:
        moves = logic.get_legal_moves(state, current_turn)
        if not moves:
            print(f"\n  No legal moves for player {current_turn}")
            break

        move = moves[0]
        move_num += 1

        # Identify active (mover) and passive (opponent) sockets
        if current_turn == 1:
            active_ws,  active_tag  = ws1, "P1"
            passive_ws, passive_tag = ws2, "P2"
        else:
            active_ws,  active_tag  = ws2, "P2"
            passive_ws, passive_tag = ws1, "P1"

        print(f"\n── Move {move_num} (Player {current_turn}) "
              f"── [{len(moves)} legal moves available] ──")

        out = {"type": "make_move", "move": move}
        print(f"→ {active_tag} SEND: {{\"type\": \"make_move\", "
              f"\"move\": {fmt_move(move)}}}")
        active_ws.send_json(out)

        # Both players receive the server's response
        resp_a = active_ws.receive_json()
        resp_p = passive_ws.receive_json()
        print(f"← {active_tag} RECV: {fmt_recv(resp_a)}")
        print(f"← {passive_tag} RECV: {fmt_recv(resp_p)}")

        if resp_a["type"] == "game_over":
            winner = resp_a["winner"]
            is_draw = resp_a["is_draw"]
            print(f"\n{sep}")
            if is_draw:
                print(f"  GAME OVER after {move_num} moves — DRAW")
            elif winner is not None:
                print(f"  GAME OVER after {move_num} moves — Player {winner} WINS")
            else:
                print(f"  GAME OVER after {move_num} moves — no winner")
            print(sep)
            break

        # Advance to the next turn
        state = resp_a["state"]
        current_turn = resp_a["current_turn"]
    else:
        print(f"\n  Move limit ({MAX_MOVES}) reached — game did not finish.")

    ws1.close()
    ws2.close()
    rooms.clear()
    print(f"\n  Total moves played: {move_num}")
    print("  Connections closed.\n")


if __name__ == "__main__":
    main()
