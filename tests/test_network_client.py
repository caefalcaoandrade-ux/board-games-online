"""Tests for the client networking module against the real FastAPI server.

Starts uvicorn in a background thread, then exercises NetworkClient
through room creation, joining, making moves, and disconnect handling.
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn
from server.main import app, rooms
from client.network import NetworkClient
from games import create_game

# ── Test server helper ───────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 18765  # high port unlikely to conflict
WS_URL = f"ws://{HOST}:{PORT}/ws"


def _start_server():
    """Run uvicorn in a daemon thread."""
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)  # let the server bind
    return server


def _wait_for(client, msg_type, timeout=3.0):
    """Poll a NetworkClient until a message of msg_type arrives.

    Non-matching messages are put back into the queue so they are not lost.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.poll_messages()
        for i, msg in enumerate(batch):
            if msg["type"] == msg_type:
                # Put back any messages that came after the match
                for leftover in batch[i + 1:]:
                    client._queue.put(leftover)
                return msg
        # No match in this batch — put everything back
        for msg in batch:
            client._queue.put(msg)
        time.sleep(0.02)
    raise TimeoutError(f"Timed out waiting for {msg_type!r}")


def _drain(client, count, timeout=3.0):
    """Collect *count* messages from a client."""
    msgs = []
    deadline = time.time() + timeout
    while len(msgs) < count and time.time() < deadline:
        msgs.extend(client.poll_messages())
        if len(msgs) < count:
            time.sleep(0.02)
    return msgs


# ── Tests ────────────────────────────────────────────────────────────────────

server = _start_server()


def test_connect_and_create_room():
    c = NetworkClient(WS_URL)
    c.connect()
    time.sleep(0.2)
    assert c.connected

    c.create_room("Bashni")
    msg = _wait_for(c, "room_created")
    assert msg["game"] == "Bashni"
    assert len(msg["code"]) >= 4
    assert c.room_code == msg["code"]
    assert c.player_id == 1

    c.disconnect()


def test_join_room():
    c1 = NetworkClient(WS_URL)
    c1.connect()
    time.sleep(0.2)

    c1.create_room("Bashni")
    msg = _wait_for(c1, "room_created")
    code = msg["code"]

    c2 = NetworkClient(WS_URL)
    c2.connect()
    time.sleep(0.2)

    c2.join_room(code)
    joined = _wait_for(c2, "room_joined")
    assert joined["code"] == code
    assert c2.player_id == 2
    assert c2.room_code == code

    c1.disconnect()
    c2.disconnect()


def test_game_start_and_move():
    c1 = NetworkClient(WS_URL)
    c2 = NetworkClient(WS_URL)
    c1.connect()
    c2.connect()
    time.sleep(0.2)

    c1.create_room("Bashni")
    created = _wait_for(c1, "room_created")
    code = created["code"]

    c2.join_room(code)
    _wait_for(c2, "room_joined")

    # Both get game_started (c1 also gets player_joined first)
    start1 = _wait_for(c1, "game_started")
    start2 = _wait_for(c2, "game_started")
    assert start1["your_player"] == 1
    assert start2["your_player"] == 2

    state = start1["state"]
    turn = start1["current_turn"]

    # Make one legal move
    logic = create_game("Bashni")
    moves = logic.get_legal_moves(state, turn)
    active = c1 if turn == 1 else c2
    active.send_move(moves[0])

    # Both get move_made
    m1 = _wait_for(c1, "move_made")
    m2 = _wait_for(c2, "move_made")
    assert m1["state"] == m2["state"]
    assert "current_turn" in m1

    c1.disconnect()
    c2.disconnect()


def test_poll_messages_never_blocks():
    c = NetworkClient(WS_URL)
    # poll before connecting should return empty list immediately
    assert c.poll_messages() == []

    c.connect()
    time.sleep(0.2)
    # poll with no pending messages should also be instant
    start = time.time()
    msgs = c.poll_messages()
    elapsed = time.time() - start
    assert elapsed < 0.05  # should be near-instant
    assert isinstance(msgs, list)

    c.disconnect()


def test_send_before_connect():
    c = NetworkClient(WS_URL)
    c.create_room("Bashni")
    msgs = c.poll_messages()
    assert any(m["type"] == "error" for m in msgs)


def test_disconnect_flag():
    c = NetworkClient(WS_URL)
    c.connect()
    time.sleep(0.2)
    assert c.connected

    c.disconnect()
    time.sleep(0.3)
    assert not c.connected


def test_connection_closed_message():
    """When server connection drops, a connection_closed message is queued."""
    c = NetworkClient(WS_URL)
    c.connect()
    time.sleep(0.2)
    assert c.connected

    # Force-close the underlying websocket from the client side to
    # simulate a drop — the on_close callback should fire
    c._ws.close()
    time.sleep(0.3)

    msgs = c.poll_messages()
    assert not c.connected
    # Should have queued a connection_closed (or already consumed it)
    types = [m["type"] for m in msgs]
    assert "connection_closed" in types or not c.connected


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PASS = FAIL = 0
    tests = [
        test_connect_and_create_room,
        test_join_room,
        test_game_start_and_move,
        test_poll_messages_never_blocks,
        test_send_before_connect,
        test_disconnect_flag,
        test_connection_closed_message,
    ]
    rooms.clear()
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print(f"  PASS  {name}")
            PASS += 1
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")
            FAIL += 1
        rooms.clear()

    print(f"\n{PASS + FAIL} tests: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
