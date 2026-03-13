"""Verify the NetworkClient works with the actual server end-to-end.

Starts uvicorn, connects two NetworkClient instances, creates a room,
joins it, and prints every message received through game start.

Usage:  python tests/test_network_flow.py
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uvicorn
from server.main import app, rooms
from client.network import NetworkClient

HOST = "127.0.0.1"
PORT = 18766
WS_URL = f"ws://{HOST}:{PORT}/ws"


def start_server():
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)


def poll_until(client, timeout=3.0):
    """Collect messages until the queue is idle for a short window."""
    msgs = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.poll_messages()
        if batch:
            msgs.extend(batch)
            deadline = time.time() + 0.3  # extend window after each batch
        time.sleep(0.02)
    return msgs


def main():
    rooms.clear()
    start_server()

    print("=" * 60)
    print("  NetworkClient → Server integration test")
    print("=" * 60)

    # ── Client 1: create room ────────────────────────────────
    c1 = NetworkClient(WS_URL)
    c1.connect()
    time.sleep(0.3)
    print(f"\nClient 1 connected: {c1.connected}")

    c1.create_room("Bashni")
    time.sleep(0.3)
    msgs = poll_until(c1, timeout=1.0)

    print("\nClient 1 messages after create_room:")
    for m in msgs:
        print(f"  {m}")

    code = c1.room_code
    print(f"\nRoom code: {code}")
    print(f"Client 1 player_id: {c1.player_id}")

    # ── Client 2: join room ──────────────────────────────────
    c2 = NetworkClient(WS_URL)
    c2.connect()
    time.sleep(0.3)
    print(f"\nClient 2 connected: {c2.connected}")

    c2.join_room(code)
    time.sleep(0.5)

    msgs1 = poll_until(c1, timeout=1.0)
    msgs2 = poll_until(c2, timeout=1.0)

    print("\nClient 1 messages after Client 2 joined:")
    for m in msgs1:
        print(f"  {m}")

    print("\nClient 2 messages after join_room:")
    for m in msgs2:
        print(f"  {m}")

    print(f"\nClient 2 player_id: {c2.player_id}")
    print(f"Client 2 room_code: {c2.room_code}")

    # ── Verify ───────────────────────────────────────────────
    all1 = [m["type"] for m in msgs1]
    all2 = [m["type"] for m in msgs2]

    ok = True
    if "game_started" not in all1:
        print("\nFAIL: Client 1 did not receive game_started")
        ok = False
    if "game_started" not in all2:
        print("\nFAIL: Client 2 did not receive game_started")
        ok = False
    if c1.player_id != 1:
        print(f"\nFAIL: Client 1 player_id is {c1.player_id}, expected 1")
        ok = False
    if c2.player_id != 2:
        print(f"\nFAIL: Client 2 player_id is {c2.player_id}, expected 2")
        ok = False

    c1.disconnect()
    c2.disconnect()
    rooms.clear()

    print()
    print("=" * 60)
    if ok:
        print("  PASS — both clients received game_started")
    else:
        print("  FAIL — see errors above")
    print("=" * 60)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
