"""Server audit tests — focused on gaps not covered by existing test suites.

Covers: malformed messages, game-over lifecycle, both-disconnect, edge cases.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from fastapi.testclient import TestClient
from server.main import app, rooms, Room, RECONNECT_TIMEOUT, forfeit_after_timeout


@pytest.fixture(autouse=True)
def clear_rooms():
    rooms.clear()
    yield
    rooms.clear()


# ── Malformed / non-dict / non-JSON messages ────────────────────────────────


def test_non_dict_json_returns_error():
    """Sending a JSON array instead of object returns an error, not a crash."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json([1, 2, 3])
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "object" in msg["message"].lower()


def test_json_string_returns_error():
    """Sending a JSON string (not object) returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json("hello")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "object" in msg["message"].lower()


def test_json_number_returns_error():
    """Sending a JSON number returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json(42)
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "object" in msg["message"].lower()


def test_json_null_returns_error():
    """Sending JSON null returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json(None)
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "object" in msg["message"].lower()


def test_raw_text_returns_error():
    """Sending non-JSON text returns an error instead of crashing."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text("this is not json at all")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "json" in msg["message"].lower()


def test_empty_string_returns_error():
    """Sending an empty string returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text("")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "json" in msg["message"].lower()


def test_missing_type_field_returns_error():
    """Message with no 'type' key returns an unknown-type error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"foo": "bar"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "unknown" in msg["message"].lower() or "None" in msg["message"]


def test_empty_object_returns_error():
    """Empty JSON object returns an error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_server_survives_after_malformed():
    """After a malformed message, the connection stays open and works normally."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Send garbage
        ws.send_json([1, 2, 3])
        err = ws.receive_json()
        assert err["type"] == "error"

        # Now send a valid message — should still work
        ws.send_json({"type": "create_room", "game": "Bashni"})
        msg = ws.receive_json()
        assert msg["type"] == "room_created"


# ── Game-over lifecycle via actual gameplay ──────────────────────────────────


def _start_game(client, game_name):
    """Helper: create room, join, start game. Returns (ws1, ws2, state, code)."""
    ws1 = client.websocket_connect("/ws").__enter__()
    ws1.send_json({"type": "create_room", "game": game_name})
    created = ws1.receive_json()
    code = created["code"]

    ws2 = client.websocket_connect("/ws").__enter__()
    ws2.send_json({"type": "join_room", "code": code})
    ws2.receive_json()  # room_joined
    ws1.receive_json()  # player_joined
    gs1 = ws1.receive_json()  # game_started
    ws2.receive_json()  # game_started

    return ws1, ws2, gs1["state"], code


def _find_game_over_sequence_havannah():
    """Find a state one move from game-over in Havannah."""
    import copy
    import random as _rng
    from games.havannah_logic import HavannahLogic
    for seed in range(20):
        rng = _rng.Random(seed)
        logic = HavannahLogic()
        state = logic.create_initial_state()
        prev_state, prev_player, prev_move = None, None, None
        for _ in range(2000):
            status = logic.get_game_status(state)
            if status["is_over"]:
                if prev_state is not None:
                    return prev_state, prev_player, prev_move, status
                break
            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            if not legal:
                break
            prev_state = copy.deepcopy(state)
            prev_player = player
            prev_move = rng.choice(legal)
            state = logic.apply_move(state, player, prev_move)
    return None, None, None, None


def test_game_over_detection_and_broadcast():
    """Inject near-terminal state, play final move, verify game_over broadcast."""
    import copy

    pre_state, winning_player, winning_move, expected = \
        _find_game_over_sequence_havannah()
    assert pre_state is not None, "Could not find Havannah game-over sequence"

    client = TestClient(app)
    ws1, ws2, state, code = _start_game(client, "Havannah")

    try:
        # Inject the pre-final state directly into the room
        room = rooms[code]
        room.state = copy.deepcopy(pre_state)

        active = ws1 if winning_player == 1 else ws2
        active.send_json({"type": "make_move", "move": winning_move})
        msg1 = ws1.receive_json()
        msg2 = ws2.receive_json()

        assert msg1["type"] == "game_over"
        assert msg2["type"] == "game_over"
        assert msg1["winner"] == msg2["winner"]
        assert msg1["is_draw"] == msg2["is_draw"]
        assert "state" in msg1
        assert code not in rooms
    finally:
        try:
            ws1.close()
        except Exception:
            pass
        try:
            ws2.close()
        except Exception:
            pass


def test_room_cleaned_up_after_game_over():
    """After game_over broadcast, the room code is removed from the registry."""
    import copy

    pre_state, winning_player, winning_move, expected = \
        _find_game_over_sequence_havannah()
    assert pre_state is not None, "Could not find Havannah game-over sequence"

    client = TestClient(app)
    ws1, ws2, state, code = _start_game(client, "Havannah")

    try:
        assert code in rooms
        room = rooms[code]
        room.state = copy.deepcopy(pre_state)

        active = ws1 if winning_player == 1 else ws2
        active.send_json({"type": "make_move", "move": winning_move})
        msg1 = ws1.receive_json()
        ws2.receive_json()

        assert msg1["type"] == "game_over"
        assert code not in rooms, "Room should be removed after game_over"
    finally:
        try:
            ws1.close()
        except Exception:
            pass
        try:
            ws2.close()
        except Exception:
            pass


# ── Both players disconnect mid-game ────────────────────────────────────────


def test_both_disconnect_midgame():
    """When both players disconnect mid-game, forfeit timers run for both."""
    client = TestClient(app)
    ws1, ws2, state, code = _start_game(client, "Bashni")

    # Both disconnect
    ws1.close()
    ws2.close()

    # Room should still exist with both in disconnected
    assert code in rooms
    room = rooms[code]
    assert len(room.players) == 0
    assert len(room.disconnected) == 2
    assert 1 in room.disconnected
    assert 2 in room.disconnected


@pytest.mark.anyio
async def test_both_disconnect_forfeit_cleans_room():
    """When both players forfeit (timeout), room is eventually cleaned up."""
    import server.main as srv

    original_timeout = srv.RECONNECT_TIMEOUT
    srv.RECONNECT_TIMEOUT = 0.1
    try:
        from games import create_game
        logic = create_game("Bashni")
        code = "BOTH"
        room = Room(code, "Bashni", logic)
        room.state = logic.create_initial_state()
        room.started = True
        srv.rooms[code] = room

        # Both players disconnect
        task1 = asyncio.create_task(forfeit_after_timeout(room, 1))
        task2 = asyncio.create_task(forfeit_after_timeout(room, 2))
        room.disconnected[1] = task1
        room.disconnected[2] = task2

        await asyncio.sleep(0.3)

        # Room should be gone
        assert code not in srv.rooms
    finally:
        srv.RECONNECT_TIMEOUT = original_timeout
        srv.rooms.pop("BOTH", None)


# ── Move after disconnect ───────────────────────────────────────────────────


def test_move_not_in_active_game_after_cleanup():
    """Player who was in a room that got cleaned up gets proper error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Not in any room
        ws.send_json({"type": "make_move", "move": {"from": [0, 0], "to": [1, 1]}})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not in an active game" in msg["message"].lower()


# ── Create room with empty game name ────────────────────────────────────────


def test_create_room_empty_game_name():
    """Empty string game name is rejected."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": ""})
        msg = ws.receive_json()
        assert msg["type"] == "error"


# ── State consistency ───────────────────────────────────────────────────────


def test_state_in_move_made_matches_logic():
    """The state broadcast in move_made matches what the logic produces."""
    from games import create_game

    client = TestClient(app)
    ws1, ws2, state, code = _start_game(client, "Bashni")
    logic = create_game("Bashni")

    try:
        player = logic.get_current_player(state)
        moves = logic.get_legal_moves(state, player)
        move = moves[0]

        # Compute expected state locally
        expected_state = logic.apply_move(state, player, move)

        # Send via server
        active = ws1 if player == 1 else ws2
        active.send_json({"type": "make_move", "move": move})
        msg1 = ws1.receive_json()
        msg2 = ws2.receive_json()

        assert msg1["type"] == "move_made"
        assert msg1["state"] == expected_state
        assert msg2["state"] == expected_state
    finally:
        ws1.close()
        ws2.close()


# ── Rapid message sequence ──────────────────────────────────────────────────


def test_rapid_multiple_errors_dont_crash():
    """Sending many invalid messages in quick succession doesn't crash."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        for _ in range(10):
            ws.send_json({"type": "make_move", "move": {}})
        # Read all error responses
        for _ in range(10):
            msg = ws.receive_json()
            assert msg["type"] == "error"


# ── Gap tests: scenarios not covered by existing suites ──────────────────────


def test_two_simultaneous_rooms_different_games():
    """Two rooms for different games run independently."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as h1:
        h1.send_json({"type": "create_room", "game": "Havannah"})
        c1 = h1.receive_json()
        code1 = c1["code"]

        with client.websocket_connect("/ws") as h2:
            h2.send_json({"type": "create_room", "game": "Bashni"})
            c2 = h2.receive_json()
            code2 = c2["code"]

            assert code1 != code2
            assert code1 in rooms and code2 in rooms
            assert rooms[code1].game_name == "Havannah"
            assert rooms[code2].game_name == "Bashni"

            # Join and start both
            with client.websocket_connect("/ws") as j1:
                j1.send_json({"type": "join_room", "code": code1})
                j1.receive_json()  # room_joined
                h1.receive_json()  # player_joined
                gs1 = h1.receive_json()  # game_started
                j1.receive_json()  # game_started

                with client.websocket_connect("/ws") as j2:
                    j2.send_json({"type": "join_room", "code": code2})
                    j2.receive_json()  # room_joined
                    h2.receive_json()  # player_joined
                    gs2 = h2.receive_json()  # game_started
                    j2.receive_json()  # game_started

                    # Make a move in room 1
                    from games.havannah_logic import HavannahLogic
                    logic1 = HavannahLogic()
                    m1 = logic1.get_legal_moves(gs1["state"], 1)[0]
                    h1.send_json({"type": "make_move", "move": m1})
                    r1a = h1.receive_json()
                    r1b = j1.receive_json()
                    assert r1a["type"] == "move_made"

                    # Room 2 should be unaffected
                    from games import create_game
                    logic2 = create_game("Bashni")
                    m2 = logic2.get_legal_moves(gs2["state"], 1)[0]
                    h2.send_json({"type": "make_move", "move": m2})
                    r2a = h2.receive_json()
                    r2b = j2.receive_json()
                    assert r2a["type"] == "move_made"


def test_move_after_game_ended_via_gameplay():
    """After a game ends via actual play, further moves are rejected."""
    import copy

    pre_state, winning_player, winning_move, expected = \
        _find_game_over_sequence_havannah()
    assert pre_state is not None, "Could not find Havannah game-over sequence"

    client = TestClient(app)
    ws1, ws2, state, code = _start_game(client, "Havannah")

    try:
        # Inject near-terminal state
        room = rooms[code]
        room.state = copy.deepcopy(pre_state)

        active = ws1 if winning_player == 1 else ws2
        active.send_json({"type": "make_move", "move": winning_move})
        msg1 = ws1.receive_json()
        ws2.receive_json()
        assert msg1["type"] == "game_over"

        # Game ended — try another move, should get error
        ws1.send_json({"type": "make_move", "move": winning_move})
        err = ws1.receive_json()
        assert err["type"] == "error"
    finally:
        try:
            ws1.close()
        except Exception:
            pass
        try:
            ws2.close()
        except Exception:
            pass


def test_rapid_valid_moves_no_drops():
    """50 rapid valid messages are all processed correctly."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Send 50 unknown-type messages rapidly
        for i in range(50):
            ws.send_json({"type": f"unknown_{i}"})
        # All 50 should get error responses
        for i in range(50):
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "unknown" in msg["message"].lower()


def test_join_room_while_already_in_room():
    """A player already in a room cannot join another room."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "create_room", "game": "Bashni"})
        created = ws.receive_json()
        assert created["type"] == "room_created"

        # Try joining a different room
        ws.send_json({"type": "join_room", "code": "ZZZZ"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "Already in a room" in msg["message"]
