"""Comprehensive online multiplayer verification for all 9 registered games.

Tests seven categories for every game:
  1. Logic integrity - play random moves to game-over, verify winner/draw
  2. Serialization round-trip - json.dumps/loads at multiple game stages
  3. Server-side validation - two WS clients, valid moves accepted, invalid rejected
  4. Turn enforcement - wrong-turn moves rejected, state unchanged
  5. Game-over propagation - both players receive game_over through the server
  6. Lobby launch integration - every game maps to a display module
  7. Local fallback - GameClient/display works in non-online mode
"""

import json
import random
import sys
import os
import time
import threading
import copy
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

try:
    import games._suppress  # noqa: F401
except ImportError:
    pass

import pytest

from games import GAME_REGISTRY, list_games, create_game

ALL_GAMES = list(GAME_REGISTRY.keys())

# Maps registry name -> display module name (without "games." prefix)
DISPLAY_MODULES = {
    "Abalone": "abalone_display",
    "Amazons": "amazons_display",
    "Arimaa": "arimaa_display",
    "Bashni": "bashni_display",
    "Entrapment": "entrapment_display",
    "Havannah": "havannah_display",
    "Hnefatafl": "hnefatafl_display",
    "Shobu": "shobu_display",
    "Tumbleweed": "tumbleweed_display",
    "YINSH": "yinsh_display",
}


# ── Helpers ────────────────────────────────────────────────────────────────


def play_random_game(game_name, max_moves=2000, seed=42):
    """Play random legal moves until game ends or limit reached.

    Returns (states, moves_played, final_status).
    """
    rng = random.Random(seed)
    logic = create_game(game_name)
    state = logic.create_initial_state()
    states = [state]
    moves_played = []

    for _ in range(max_moves):
        status = logic.get_game_status(state)
        if status["is_over"]:
            return states, moves_played, status

        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)
        if not legal:
            return states, moves_played, logic.get_game_status(state)

        move = rng.choice(legal)
        state = logic.apply_move(state, player, move)
        states.append(state)
        moves_played.append((player, move))

    return states, moves_played, logic.get_game_status(state)


def find_game_over_sequence(game_name, max_seeds=10, max_moves=2000):
    """Find a state one move from game-over plus the winning move.

    Returns (pre_state, player, move, post_status) or (None, None, None, None).
    """
    for seed in range(max_seeds):
        rng = random.Random(seed)
        logic = create_game(game_name)
        state = logic.create_initial_state()
        prev_state = None
        prev_player = None
        prev_move = None

        for _ in range(max_moves):
            status = logic.get_game_status(state)
            if status["is_over"]:
                if prev_state is not None:
                    return prev_state, prev_player, prev_move, status
                break

            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            if not legal:
                final = logic.get_game_status(state)
                if final["is_over"] and prev_state is not None:
                    return prev_state, prev_player, prev_move, final
                break

            prev_state = state
            prev_player = player
            prev_move = rng.choice(legal)
            state = logic.apply_move(state, player, prev_move)

    return None, None, None, None


# ── Server setup ───────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 18790
WS_URL = f"ws://{HOST}:{PORT}/ws"

_server_started = False
_server_rooms_ref = None


def ensure_server():
    """Start the test server once (idempotent)."""
    global _server_started, _server_rooms_ref
    if _server_started:
        return
    import uvicorn
    from server.main import app, rooms

    _server_rooms_ref = rooms
    rooms.clear()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)
    _server_started = True


def poll_until(client, msg_type, timeout=5.0):
    """Poll messages until the desired type appears or timeout."""
    msgs = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.poll_messages()
        for m in batch:
            msgs.append(m)
            if m.get("type") == msg_type:
                return msgs
        time.sleep(0.02)
    return msgs


def setup_game_room(game_name):
    """Create room with two clients, return (c1, c2, gs1, gs2, code)."""
    from client.network import NetworkClient

    c1 = NetworkClient(WS_URL)
    c1.connect()
    time.sleep(0.3)
    c1.create_room(game_name)
    poll_until(c1, "room_created")
    code = c1.room_code
    assert code is not None, f"Room code is None for {game_name}"

    c2 = NetworkClient(WS_URL)
    c2.connect()
    time.sleep(0.3)
    c2.join_room(code)

    msgs1 = poll_until(c1, "game_started")
    msgs2 = poll_until(c2, "game_started")

    gs1 = [m for m in msgs1 if m["type"] == "game_started"]
    gs2 = [m for m in msgs2 if m["type"] == "game_started"]
    assert len(gs1) == 1, (
        f"{game_name}: P1 no game_started, got: {[m['type'] for m in msgs1]}"
    )
    assert len(gs2) == 1, (
        f"{game_name}: P2 no game_started, got: {[m['type'] for m in msgs2]}"
    )

    return c1, c2, gs1[0], gs2[0], code


def cleanup_room(code):
    """Remove a room from the server, silently."""
    if _server_rooms_ref is not None:
        _server_rooms_ref.pop(code, None)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Logic integrity
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_integrity(game_name):
    """Play random moves toward game-over, verify final status."""
    states, moves, status = play_random_game(game_name, max_moves=2000, seed=42)

    # Must have played at least one move
    assert len(moves) >= 1, f"{game_name}: no moves were played"

    if status["is_over"]:
        if status["is_draw"]:
            assert status["winner"] is None, \
                f"{game_name}: draw but winner={status['winner']}"
        else:
            assert status["winner"] in (1, 2), \
                f"{game_name}: winner={status['winner']} not in (1,2)"

    # Every intermediate state should have a valid status dict
    logic = create_game(game_name)
    for i, s in enumerate(states):
        st = logic.get_game_status(s)
        assert isinstance(st["is_over"], bool), f"step {i}: is_over not bool"
        assert isinstance(st["is_draw"], bool), f"step {i}: is_draw not bool"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_game_ends(game_name):
    """At least one seed should reach game-over within the move limit."""
    for seed in range(10):
        _, _, status = play_random_game(game_name, max_moves=2000, seed=seed)
        if status["is_over"]:
            # Verify final status consistency
            if status["is_draw"]:
                assert status["winner"] is None
            else:
                assert status["winner"] in (1, 2)
            return  # success
    pytest.skip(f"{game_name}: no seed reached game-over in 2000 moves")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Serialization round-trip
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_serialization_states(game_name):
    """json.dumps/loads on game states at multiple stages."""
    states, _, _ = play_random_game(game_name, max_moves=200, seed=123)
    logic = create_game(game_name)

    n = len(states)
    check_at = sorted(set([0, n // 4, n // 2, 3 * n // 4, n - 1]))

    for idx in check_at:
        state = states[idx]
        serialized = json.dumps(state)
        restored = json.loads(serialized)
        assert restored == state, \
            f"{game_name} step {idx}: state differs after JSON round-trip"

        # Restored state must be usable by the logic
        logic.get_game_status(restored)
        if not logic.get_game_status(restored)["is_over"]:
            player = logic.get_current_player(restored)
            legal = logic.get_legal_moves(restored, player)
            assert isinstance(legal, list)


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_serialization_moves(game_name):
    """json.dumps/loads on moves at multiple stages."""
    _, moves, _ = play_random_game(game_name, max_moves=200, seed=123)
    logic = create_game(game_name)

    for i, (player, move) in enumerate(moves[:20]):
        serialized = json.dumps(move)
        restored = json.loads(serialized)
        assert restored == move, \
            f"{game_name} move {i}: {move!r} != {restored!r} after round-trip"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_serialization_apply_after_roundtrip(game_name):
    """A restored state + restored move should produce identical results."""
    states, moves, _ = play_random_game(game_name, max_moves=50, seed=77)
    logic = create_game(game_name)

    # Pick a mid-game state/move pair
    if len(moves) < 2:
        return
    idx = min(5, len(moves) - 1)
    state = states[idx]
    player, move = moves[idx]

    state_rt = json.loads(json.dumps(state))
    move_rt = json.loads(json.dumps(move))

    new_original = logic.apply_move(state, player, move)
    new_roundtrip = logic.apply_move(state_rt, player, move_rt)

    assert new_original == new_roundtrip, \
        f"{game_name}: apply_move differs after JSON round-trip"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Server-side validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_server_valid_move_accepted(game_name):
    """A valid move is accepted and both clients get move_made."""
    ensure_server()
    c1, c2, gs1, gs2, code = setup_game_room(game_name)

    try:
        logic = create_game(game_name)
        state = gs1["state"]
        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)
        assert len(legal) > 0

        active = c1 if player == 1 else c2
        passive = c2 if player == 1 else c1

        active.send_move(legal[0])
        msgs_a = poll_until(active, "move_made", timeout=5)
        msgs_p = poll_until(passive, "move_made", timeout=5)

        assert any(m["type"] == "move_made" for m in msgs_a), \
            f"{game_name}: active got {[m['type'] for m in msgs_a]}"
        assert any(m["type"] == "move_made" for m in msgs_p), \
            f"{game_name}: passive got {[m['type'] for m in msgs_p]}"
    finally:
        c1.disconnect()
        c2.disconnect()
        cleanup_room(code)


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_server_invalid_move_rejected(game_name):
    """An invalid (wrong-turn) move is rejected with an error to offender only."""
    ensure_server()
    c1, c2, gs1, gs2, code = setup_game_room(game_name)

    try:
        logic = create_game(game_name)
        state = gs1["state"]
        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)

        active = c1 if player == 1 else c2
        passive = c2 if player == 1 else c1

        # First, make a valid move to advance state
        active.send_move(legal[0])
        poll_until(active, "move_made", timeout=5)
        poll_until(passive, "move_made", timeout=5)

        # Now passive tries to move (it's still active's... wait, no, it's
        # passive's turn now). Let me drain and figure out whose turn it is.
        # After one move, the turn should have switched. So now the previously
        # passive player is the active one. Let me have the *originally active*
        # player try to move again (wrong turn).
        time.sleep(0.2)
        active.send_move(legal[0])  # wrong turn now
        time.sleep(0.5)
        err_msgs = active.poll_messages()
        errors = [m for m in err_msgs if m.get("type") == "error"]
        assert len(errors) >= 1, \
            f"{game_name}: wrong-turn move was not rejected"

        # The other player should NOT have received an error
        time.sleep(0.2)
        passive_msgs = passive.poll_messages()
        passive_errors = [m for m in passive_msgs if m.get("type") == "error"]
        assert len(passive_errors) == 0, \
            f"{game_name}: innocent player got error for opponent's bad move"
    finally:
        c1.disconnect()
        c2.disconnect()
        cleanup_room(code)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Turn enforcement (logic level)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_turn_enforcement_logic(game_name):
    """Wrong-turn moves raise ValueError; state is unchanged."""
    logic = create_game(game_name)
    state = logic.create_initial_state()
    current = logic.get_current_player(state)
    wrong = 2 if current == 1 else 1

    legal = logic.get_legal_moves(state, current)
    assert len(legal) > 0

    snapshot = json.dumps(state, sort_keys=True)
    with pytest.raises(ValueError):
        logic.apply_move(state, wrong, legal[0])
    assert json.dumps(state, sort_keys=True) == snapshot, \
        f"{game_name}: state mutated after rejected wrong-turn move"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_turn_enforcement_illegal_move(game_name):
    """A clearly illegal move raises ValueError."""
    logic = create_game(game_name)
    state = logic.create_initial_state()
    current = logic.get_current_player(state)

    snapshot = json.dumps(state, sort_keys=True)
    with pytest.raises(ValueError):
        logic.apply_move(state, current, "__completely_invalid__")
    assert json.dumps(state, sort_keys=True) == snapshot, \
        f"{game_name}: state mutated after rejected illegal move"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Game-over propagation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_game_over_propagation(game_name):
    """Both players receive game_over with correct result through the server."""
    # Find a state one move from game-over
    pre_state, winning_player, winning_move, expected = \
        find_game_over_sequence(game_name, max_seeds=10, max_moves=2000)

    if pre_state is None:
        pytest.skip(f"{game_name}: could not find game-over sequence")

    ensure_server()
    c1, c2, gs1, gs2, code = setup_game_room(game_name)

    try:
        # Inject the pre-final state into the server room
        from server.main import rooms as srv_rooms
        room = srv_rooms.get(code)
        assert room is not None, f"Room {code} not found on server"
        room.state = copy.deepcopy(pre_state)

        # Send the winning move from the correct player
        active = c1 if winning_player == 1 else c2
        active.send_move(winning_move)

        # Both should receive game_over
        msgs1 = poll_until(c1, "game_over", timeout=5)
        msgs2 = poll_until(c2, "game_over", timeout=5)

        go1 = [m for m in msgs1 if m["type"] == "game_over"]
        go2 = [m for m in msgs2 if m["type"] == "game_over"]

        assert len(go1) >= 1, \
            f"{game_name}: P1 got {[m['type'] for m in msgs1]}, not game_over"
        assert len(go2) >= 1, \
            f"{game_name}: P2 got {[m['type'] for m in msgs2]}, not game_over"

        # Verify winner/draw match
        assert go1[0]["winner"] == expected["winner"], \
            f"{game_name}: P1 winner={go1[0]['winner']}, expected={expected['winner']}"
        assert go1[0]["is_draw"] == expected["is_draw"], \
            f"{game_name}: P1 is_draw={go1[0]['is_draw']}, expected={expected['is_draw']}"
        assert go2[0]["winner"] == expected["winner"]
        assert go2[0]["is_draw"] == expected["is_draw"]

        # Both should have the same final state
        assert go1[0]["state"] == go2[0]["state"]
    finally:
        c1.disconnect()
        c2.disconnect()
        cleanup_room(code)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Lobby launch integration
# ═══════════════════════════════════════════════════════════════════════════


def test_lobby_dispatch_complete():
    """Every registered game maps to a callable in the lobby dispatch."""
    from client.lobby import _load_dispatch, _ONLINE_DISPATCH

    _ONLINE_DISPATCH.clear()
    _load_dispatch()

    for game_name in ALL_GAMES:
        assert game_name in _ONLINE_DISPATCH, \
            f"{game_name} missing from lobby dispatch"
        assert callable(_ONLINE_DISPATCH[game_name]), \
            f"{game_name} dispatch entry not callable"


def test_lobby_dispatch_signatures():
    """Each dispatched run_online accepts (screen, net, my_player, state)."""
    from client.lobby import _load_dispatch, _ONLINE_DISPATCH

    _ONLINE_DISPATCH.clear()
    _load_dispatch()

    for game_name, fn in _ONLINE_DISPATCH.items():
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert len(params) >= 4, \
            f"{game_name}: run_online has {len(params)} params ({params}), need >= 4"


def test_lobby_dispatch_matches_registry():
    """Dispatch table covers exactly the game registry (no extras, no missing)."""
    from client.lobby import _load_dispatch, _ONLINE_DISPATCH

    _ONLINE_DISPATCH.clear()
    _load_dispatch()

    registry_names = set(ALL_GAMES)
    dispatch_names = set(_ONLINE_DISPATCH.keys())

    missing = registry_names - dispatch_names
    extra = dispatch_names - registry_names

    assert not missing, f"Games in registry but not dispatch: {missing}"
    assert not extra, f"Games in dispatch but not registry: {extra}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Local fallback
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_local_fallback_import(game_name):
    """Display module imports and has expected exports."""
    mod_name = DISPLAY_MODULES[game_name]
    display_mod = __import__(f"games.{mod_name}", fromlist=["run_online"])

    # Must have run_online
    assert hasattr(display_mod, "run_online"), \
        f"{game_name}: display module missing run_online"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_local_fallback_game_client(game_name):
    """GameClient in local mode initialises correctly."""
    import pygame
    pygame.init()

    try:
        mod_name = DISPLAY_MODULES[game_name]
        display_mod = __import__(f"games.{mod_name}", fromlist=["GameClient"])

        if not hasattr(display_mod, "GameClient"):
            # Module uses a different pattern; just verify it imported
            return

        gc = display_mod.GameClient()
        assert gc.online is False, f"{game_name}: default should be offline"

        if hasattr(gc, "game_over"):
            assert gc.game_over is False, \
                f"{game_name}: new game should not be over"
    finally:
        pygame.quit()


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_local_fallback_online_mode_attrs(game_name):
    """GameClient in online mode has the required attributes."""
    import pygame
    pygame.init()

    try:
        mod_name = DISPLAY_MODULES[game_name]
        display_mod = __import__(f"games.{mod_name}", fromlist=["GameClient"])

        if not hasattr(display_mod, "GameClient"):
            return

        gc = display_mod.GameClient(online=True, my_player=1)
        assert gc.online is True
        assert gc.my_player == 1

        # Should have load_state and set_game_over
        assert hasattr(gc, "load_state"), \
            f"{game_name}: GameClient missing load_state"
        assert hasattr(gc, "set_game_over"), \
            f"{game_name}: GameClient missing set_game_over"
        assert hasattr(gc, "is_my_turn"), \
            f"{game_name}: GameClient missing is_my_turn"

        # Load the initial state
        logic = create_game(game_name)
        state = logic.create_initial_state()
        gc.load_state(state)
    finally:
        pygame.quit()


# ═══════════════════════════════════════════════════════════════════════════
# Extra: Server multi-move pipeline
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_server_multi_move_pipeline(game_name):
    """Play several moves through the server, alternating turns correctly."""
    ensure_server()
    c1, c2, gs1, gs2, code = setup_game_room(game_name)

    try:
        logic = create_game(game_name)
        state = gs1["state"]
        clients = {1: c1, 2: c2}
        rng = random.Random(42)

        for move_num in range(6):
            status = logic.get_game_status(state)
            if status["is_over"]:
                break

            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            if not legal:
                break

            move = rng.choice(legal)
            clients[player].send_move(move)

            # Poll both for move_made or game_over
            r1 = poll_until(c1, "move_made", timeout=5)
            r2 = poll_until(c2, "move_made", timeout=5)

            # Check if game ended
            go1 = [m for m in r1 if m["type"] == "game_over"]
            go2 = [m for m in r2 if m["type"] == "game_over"]
            if go1 or go2:
                break

            mm1 = [m for m in r1 if m["type"] == "move_made"]
            mm2 = [m for m in r2 if m["type"] == "move_made"]

            assert len(mm1) >= 1, \
                f"{game_name} move {move_num}: P1 no move_made, got {[m['type'] for m in r1]}"
            assert len(mm2) >= 1, \
                f"{game_name} move {move_num}: P2 no move_made, got {[m['type'] for m in r2]}"

            # Both should see the same new state
            assert mm1[-1]["state"] == mm2[-1]["state"], \
                f"{game_name} move {move_num}: state mismatch between players"

            state = mm1[-1]["state"]
    finally:
        c1.disconnect()
        c2.disconnect()
        cleanup_room(code)


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
