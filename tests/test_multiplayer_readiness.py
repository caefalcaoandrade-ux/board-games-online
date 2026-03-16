"""Comprehensive online multiplayer readiness audit.

Check 1: Registry & logic — every game imports without Pygame, creates state,
         plays 3 moves, survives JSON round-trip at each step.
Check 2: Server integration — 3 games (Havannah=simple, Hnefatafl=mid,
         Entrapment=complex) get full room lifecycle tests via real WebSocket
         clients: create, join, valid move, invalid move rejection, game-over.
"""

import sys
import os
import json
import time
import random
import threading
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from games import GAME_REGISTRY, list_games, create_game
from games.base_game import AbstractBoardGame

ALL_GAMES = list(GAME_REGISTRY.keys())

# ═══════════════════════════════════════════════════════════════════════════
# CHECK 1 — Registry & logic: no Pygame, JSON round-trip, 3-move play
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_no_pygame_import(game_name):
    """Logic module must not import Pygame."""
    import importlib
    mod_name = f"games.{game_name.lower()}_logic"
    # YINSH has uppercase name in registry but lowercase module
    if game_name == "YINSH":
        mod_name = "games.yinsh_logic"
    elif game_name == "BaghChal":
        mod_name = "games.bagh_chal_logic"
    mod = importlib.import_module(mod_name)
    # Check that pygame is not in the module's globals
    assert "pygame" not in dir(mod), f"{mod_name} imports pygame"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_inherits_base(game_name):
    """Every registered game must subclass AbstractBoardGame."""
    cls = GAME_REGISTRY[game_name]
    assert issubclass(cls, AbstractBoardGame), \
        f"{game_name} does not subclass AbstractBoardGame"


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_implements_all_methods(game_name):
    """Every game must implement all required abstract methods."""
    logic = create_game(game_name)
    # These calls will raise if abstract methods are missing
    assert isinstance(logic.name, str) and len(logic.name) > 0
    assert isinstance(logic.player_count, int) and logic.player_count >= 1
    state = logic.create_initial_state()
    assert isinstance(state, dict)
    player = logic.get_current_player(state)
    assert isinstance(player, int)
    moves = logic.get_legal_moves(state, player)
    assert isinstance(moves, list) and len(moves) > 0
    status = logic.get_game_status(state)
    assert status["is_over"] is False


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_3_moves_json_roundtrip(game_name):
    """Create game, play 3 legal moves, confirm JSON round-trip at each step."""
    logic = create_game(game_name)
    state = logic.create_initial_state()

    # Initial state round-trip
    rt = json.loads(json.dumps(state))
    assert rt == state, f"{game_name}: initial state changed after JSON round-trip"

    rng = random.Random(42)
    for move_num in range(3):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        moves = logic.get_legal_moves(state, player)
        if not moves:
            break

        move = rng.choice(moves)

        # Move round-trip
        move_rt = json.loads(json.dumps(move))
        assert move_rt == move, \
            f"{game_name} move {move_num}: move changed after JSON round-trip"

        # Apply the round-tripped move to verify it's accepted
        state = logic.apply_move(state, player, move_rt)

        # State round-trip
        state_rt = json.loads(json.dumps(state))
        assert state_rt == state, \
            f"{game_name} move {move_num}: state changed after JSON round-trip"

        # Verify the round-tripped state is usable
        logic.get_game_status(state_rt)


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_wrong_player_rejected(game_name):
    """Moves from the wrong player must raise ValueError."""
    logic = create_game(game_name)
    state = logic.create_initial_state()
    current = logic.get_current_player(state)
    wrong = 2 if current == 1 else 1
    moves = logic.get_legal_moves(state, current)
    assert len(moves) > 0
    with pytest.raises(ValueError):
        logic.apply_move(state, wrong, moves[0])


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_invalid_move_rejected(game_name):
    """A garbage move must raise ValueError."""
    logic = create_game(game_name)
    state = logic.create_initial_state()
    current = logic.get_current_player(state)
    with pytest.raises(ValueError):
        logic.apply_move(state, current, "__invalid__")


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_logic_immutability(game_name):
    """apply_move must not mutate the original state."""
    logic = create_game(game_name)
    state = logic.create_initial_state()
    player = logic.get_current_player(state)
    moves = logic.get_legal_moves(state, player)
    snapshot = json.dumps(state, sort_keys=True)
    logic.apply_move(state, player, moves[0])
    assert json.dumps(state, sort_keys=True) == snapshot, \
        f"{game_name}: apply_move mutated original state"


# ═══════════════════════════════════════════════════════════════════════════
# CHECK 2 — Server integration: 3 games via real WebSocket
# ═══════════════════════════════════════════════════════════════════════════

HOST = "127.0.0.1"
PORT = 18799
WS_URL = f"ws://{HOST}:{PORT}/ws"

_server_started = False


def ensure_server():
    global _server_started
    if _server_started:
        return
    import uvicorn
    from server.main import app, rooms
    rooms.clear()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)
    _server_started = True


def poll_until(client, msg_type, timeout=5.0):
    msgs = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        for m in client.poll_messages():
            msgs.append(m)
            if m.get("type") == msg_type:
                return msgs
        time.sleep(0.02)
    return msgs


def setup_room(game_name):
    from client.network import NetworkClient
    c1 = NetworkClient(WS_URL)
    c1.connect()
    time.sleep(0.1)
    c1.create_room(game_name)
    poll_until(c1, "room_created")
    code = c1.room_code

    c2 = NetworkClient(WS_URL)
    c2.connect()
    time.sleep(0.1)
    c2.join_room(code)

    msgs1 = poll_until(c1, "game_started")
    msgs2 = poll_until(c2, "game_started")

    gs1 = [m for m in msgs1 if m["type"] == "game_started"][0]
    gs2 = [m for m in msgs2 if m["type"] == "game_started"][0]

    return c1, c2, gs1, gs2, code


# ── Simple game: Havannah (stone placement, no multi-step) ────────────────

def test_server_havannah_lifecycle():
    """Full room lifecycle for Havannah: create, join, move, reject, detect end."""
    ensure_server()
    from server.main import rooms

    c1, c2, gs1, gs2, code = setup_room("Havannah")
    try:
        logic = create_game("Havannah")
        state = gs1["state"]
        assert gs1["your_player"] == 1
        assert gs2["your_player"] == 2

        # Valid move by player 1
        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)
        active = c1 if player == 1 else c2
        passive = c2 if player == 1 else c1

        active.send_move(legal[0])
        r1 = poll_until(active, "move_made")
        r2 = poll_until(passive, "move_made")
        assert any(m["type"] == "move_made" for m in r1)
        assert any(m["type"] == "move_made" for m in r2)

        # Wrong-turn move by the same player (now it's the other's turn)
        active.send_move(legal[0])
        time.sleep(0.1)
        errs = [m for m in active.poll_messages() if m.get("type") == "error"]
        assert len(errs) >= 1, "Wrong-turn move should be rejected"

        # Passive player should NOT have received an error
        time.sleep(0.1)
        passive_errs = [m for m in passive.poll_messages()
                        if m.get("type") == "error"]
        assert len(passive_errs) == 0, "Innocent player got error"
    finally:
        c1.disconnect()
        c2.disconnect()
        rooms.pop(code, None)


# ── Mid-complexity: Hnefatafl (piece selection + destination) ─────────────

def test_server_hnefatafl_lifecycle():
    """Full room lifecycle for Hnefatafl."""
    ensure_server()
    from server.main import rooms

    c1, c2, gs1, gs2, code = setup_room("Hnefatafl")
    try:
        logic = create_game("Hnefatafl")
        state = gs1["state"]

        # Play 4 alternating moves
        clients = {1: c1, 2: c2}
        rng = random.Random(99)
        for _ in range(4):
            status = logic.get_game_status(state)
            if status["is_over"]:
                break
            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            move = rng.choice(legal)
            clients[player].send_move(move)

            r1 = poll_until(c1, "move_made")
            r2 = poll_until(c2, "move_made")
            mm = [m for m in r1 if m["type"] == "move_made"]
            assert len(mm) >= 1
            state = mm[0]["state"]

        # Illegal move: garbage data
        player = logic.get_current_player(state)
        clients[player].send_move("garbage")
        time.sleep(0.1)
        errs = [m for m in clients[player].poll_messages()
                if m.get("type") == "error"]
        assert len(errs) >= 1, "Illegal move should be rejected"
    finally:
        c1.disconnect()
        c2.disconnect()
        rooms.pop(code, None)


# ── Complex: Entrapment (setup phase + multi-action turns) ────────────────

def test_server_entrapment_lifecycle():
    """Full room lifecycle for Entrapment: setup phase, play phase, rejection."""
    ensure_server()
    from server.main import rooms

    c1, c2, gs1, gs2, code = setup_room("Entrapment")
    try:
        logic = create_game("Entrapment")
        state = gs1["state"]
        assert state["phase"] == "setup"

        clients = {1: c1, 2: c2}

        # Play through the 6-roamer setup phase
        for i in range(6):
            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            assert len(legal) > 0, f"Setup step {i}: no legal moves"
            clients[player].send_move(legal[0])

            r1 = poll_until(c1, "move_made")
            r2 = poll_until(c2, "move_made")
            mm = [m for m in r1 if m["type"] == "move_made"]
            assert len(mm) >= 1, f"Setup step {i}: no move_made"
            state = mm[0]["state"]

        assert state["phase"] == "play", "Should be in play phase after setup"

        # Play 2 moves in the play phase
        for i in range(2):
            status = logic.get_game_status(state)
            if status["is_over"]:
                break
            player = logic.get_current_player(state)
            legal = logic.get_legal_moves(state, player)
            if not legal:
                break
            clients[player].send_move(legal[0])

            r1 = poll_until(c1, "move_made")
            mm = [m for m in r1 if m["type"] in ("move_made", "game_over")]
            assert len(mm) >= 1
            state = mm[0]["state"]

        # Wrong-player rejection
        player = logic.get_current_player(state)
        wrong = 2 if player == 1 else 1
        legal = logic.get_legal_moves(state, player)
        if legal:
            clients[wrong].send_move(legal[0])
            time.sleep(0.1)
            errs = [m for m in clients[wrong].poll_messages()
                    if m.get("type") == "error"]
            assert len(errs) >= 1, "Wrong player move should be rejected"
    finally:
        c1.disconnect()
        c2.disconnect()
        rooms.pop(code, None)


# ── Game-over propagation through server ──────────────────────────────────

def test_server_game_over_propagation():
    """Inject near-terminal state, play final move, both players get game_over."""
    ensure_server()
    from server.main import rooms

    # Find a state one move from game-over offline (fast)
    rng = random.Random(42)
    logic = create_game("Havannah")
    pre_state, winning_player, winning_move = None, None, None
    state = logic.create_initial_state()
    for _ in range(2000):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)
        if not legal:
            break
        prev_state = copy.deepcopy(state)
        prev_player = player
        move = rng.choice(legal)
        state = logic.apply_move(state, player, move)
        post = logic.get_game_status(state)
        if post["is_over"]:
            pre_state, winning_player, winning_move = prev_state, prev_player, move
            break

    assert pre_state is not None, "Could not find Havannah game-over sequence"

    c1, c2, gs1, gs2, code = setup_room("Havannah")
    try:
        # Inject the pre-final state into the server room
        room = rooms.get(code)
        assert room is not None
        room.state = copy.deepcopy(pre_state)

        active = c1 if winning_player == 1 else c2
        passive = c2 if winning_player == 1 else c1
        active.send_move(winning_move)

        r1 = poll_until(c1, "game_over", timeout=5)
        r2 = poll_until(c2, "game_over", timeout=5)

        go1 = [m for m in r1 if m["type"] == "game_over"]
        go2 = [m for m in r2 if m["type"] == "game_over"]
        assert len(go1) >= 1, "P1 should receive game_over"
        assert len(go2) >= 1, "P2 should receive game_over"
        assert go1[0]["winner"] == go2[0]["winner"]
    finally:
        c1.disconnect()
        c2.disconnect()
        rooms.pop(code, None)


# ── Lobby dispatch completeness ───────────────────────────────────────────

def test_lobby_dispatch_covers_registry():
    """Every registered game has a dispatch entry in the lobby."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    try:
        import games._suppress  # noqa
    except ImportError:
        pass
    from client.lobby import _load_dispatch, _ONLINE_DISPATCH
    _ONLINE_DISPATCH.clear()
    _load_dispatch()

    registry_names = set(GAME_REGISTRY.keys())
    dispatch_names = set(_ONLINE_DISPATCH.keys())

    assert registry_names == dispatch_names, \
        f"Mismatch: registry={registry_names - dispatch_names}, " \
        f"dispatch={dispatch_names - registry_names}"


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
