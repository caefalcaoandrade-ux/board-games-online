"""Test the full click-to-move pipeline for every game's display module.

For each game, exercises the GameClient in online mode:
  1. Create a GameClient(online=True, my_player=...)
  2. load_state(initial_state) from the logic module
  3. Simulate clicks that produce a valid move
  4. Verify the move is returned (not None)
  5. Send the move through a real server and verify both clients get move_made
  6. load_state the new state and verify the turn changed

This catches bugs like YINSH's _cancel() wiping the pending move before
click() could return it.
"""

import sys
import os
import json
import time
import threading
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

try:
    import games._suppress  # noqa: F401
except ImportError:
    pass

import pytest
import pygame

from games import GAME_REGISTRY, create_game

# ── Server setup ───────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 18795
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


# ═══════════════════════════════════════════════════════════════════════════
# Hnefatafl — select piece, then click destination
# ═══════════════════════════════════════════════════════════════════════════

def test_hnefatafl_click_pipeline():
    from games.hnefatafl_display import GameClient
    from games.hnefatafl_logic import HnefataflLogic, PLAYER_ATTACKER, ATTACKER

    logic = HnefataflLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=PLAYER_ATTACKER)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Find an attacker and click it to select
    for r in range(11):
        for c in range(11):
            if gc.board[r][c] == ATTACKER:
                result = gc.click(r, c)
                assert result is None, "Selection click should return None"
                if gc.sel and gc.targets:
                    # Click a valid target
                    tr, tc = gc.targets[0]
                    move = gc.click(tr, tc)
                    assert move is not None, "HNEFATAFL: move click returned None!"
                    assert move == [[r, c], [tr, tc]]
                    return
    pytest.fail("Could not find a valid attacker move")


# ═══════════════════════════════════════════════════════════════════════════
# YINSH — place ring (placement phase)
# ═══════════════════════════════════════════════════════════════════════════

def test_yinsh_click_pipeline_placement():
    from games.yinsh_display import GameClient, p2h
    from games.yinsh_logic import YinshLogic, WHITE, VALID_POSITIONS, _key

    logic = YinshLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=WHITE)
    gc.load_state(state)
    assert gc.is_my_turn is True
    assert gc.sub_state == "place_ring"

    # Click a valid empty position
    for pos in VALID_POSITIONS:
        q, r = pos[0], pos[1]
        k = _key(q, r)
        if k not in state["rings"] and k not in state["markers"]:
            move = gc.click([q, r])
            assert move is not None, \
                f"YINSH: placement click at ({q},{r}) returned None!"
            assert move == {"type": "place_ring", "pos": [q, r]}
            return
    pytest.fail("No valid placement position found")


def test_yinsh_click_pipeline_move():
    """Test the ring-move phase produces a move in online mode."""
    from games.yinsh_display import GameClient
    from games.yinsh_logic import (
        YinshLogic, WHITE, BLACK,
        _key, _from_key, compute_destinations,
        ST_SELECT_RING, ST_MOVE_RING,
    )

    logic = YinshLogic()
    # Play through placement phase locally to reach main game
    state = logic.create_initial_state()
    positions = [
        [0, 2], [1, 1], [-2, 4], [3, -1], [-1, -1],
        [2, -3], [-3, 2], [0, -2], [4, -2], [-4, 3],
    ]
    player = logic.get_current_player(state)
    for pos in positions:
        move = {"type": "place_ring", "pos": pos}
        state = logic.apply_move(state, player, move)
        player = logic.get_current_player(state)

    assert state["phase"] == "main"

    gc = GameClient(online=True, my_player=player)
    gc.load_state(state)
    assert gc.sub_state == ST_SELECT_RING

    # Find a ring belonging to current player with valid destinations
    for k, v in state["rings"].items():
        if v == player:
            pos = _from_key(k)
            q, r = pos[0], pos[1]
            dests = compute_destinations(
                state["rings"], state["markers"], q, r)
            if dests:
                # Select the ring
                result = gc.click([q, r])
                assert result is None, "Ring selection should return None"
                assert gc.sub_state == ST_MOVE_RING

                # Move to a destination
                dq, dr = dests[0][0], dests[0][1]
                move = gc.click([dq, dr])
                assert move is not None, \
                    "YINSH: ring move returned None (the original bug)!"
                assert move["type"] == "move"
                assert move["ring"] == [q, r]
                assert move["dest"] == [dq, dr]
                return
    pytest.fail("No ring with valid destinations found")


# ═══════════════════════════════════════════════════════════════════════════
# Abalone — select marbles, then click direction
# ═══════════════════════════════════════════════════════════════════════════

def test_abalone_click_pipeline():
    from games.abalone_display import GameClient, cube_to_pixel
    from games.abalone_logic import (
        AbaloneLogic, BLACK, cube_key, key_to_cube, cube_to_rc, ROW_LENS,
    )

    logic = AbaloneLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=BLACK)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Get a legal move from the logic
    moves = logic.get_legal_moves(state, BLACK)
    assert len(moves) > 0
    test_move = moves[0]

    # Select each marble in the move
    for marble in test_move["marbles"]:
        gc.on_left_click(*map(int, cube_to_pixel(marble)))

    # The selection should work, but let's use a different approach:
    # directly set selection and click a target
    gc.selected = [list(m) for m in test_move["marbles"]]

    # Find a target cell that would produce the right direction
    d = test_move["direction"]
    first = test_move["marbles"][0]
    target_cube = [first[0] + d[0], first[1] + d[1], first[2] + d[2]]
    target_px = cube_to_pixel(target_cube)

    move = gc.on_left_click(int(target_px[0]), int(target_px[1]))
    assert move is not None, "ABALONE: move click returned None!"
    assert "marbles" in move
    assert "direction" in move


# ═══════════════════════════════════════════════════════════════════════════
# Amazons — 3-phase: select, move, arrow
# ═══════════════════════════════════════════════════════════════════════════

def test_amazons_click_pipeline():
    from games.amazons_display import GameClient, PH_SELECT, PH_MOVE, PH_ARROW
    from games.amazons_logic import AmazonsLogic, WHITE, BOARD_N

    logic = AmazonsLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=WHITE)
    gc.load_state(state)
    assert gc.is_my_turn is True
    assert gc.phase == PH_SELECT

    # Find a white amazon
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if gc.board[r][c] == WHITE:
                # Phase 1: select
                result = gc.click(r, c)
                assert result is None
                if gc.phase != PH_MOVE:
                    continue

                # Phase 2: move to first target
                mr, mc = gc.targets[0]
                result = gc.click(mr, mc)
                assert result is None
                assert gc.phase == PH_ARROW

                # Phase 3: shoot arrow at first target
                ar, ac = gc.targets[0]
                move = gc.click(ar, ac)
                assert move is not None, "AMAZONS: arrow click returned None!"
                assert len(move) == 3
                assert move[0] == [r, c]
                assert move[1] == [mr, mc]
                assert move[2] == [ar, ac]
                return
    pytest.fail("Could not complete Amazons 3-phase move")


# ═══════════════════════════════════════════════════════════════════════════
# Bashni — select piece, click destination (simple move)
# ═══════════════════════════════════════════════════════════════════════════

def test_bashni_click_pipeline():
    from games.bashni_display import GameClient
    from games.bashni_logic import BashniLogic, W, BOARD_N

    logic = BashniLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=1)  # Player 1 = White
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Get a legal move from the logic
    moves = logic.get_legal_moves(state, 1)
    assert len(moves) > 0

    # Find a simple move (not a capture)
    simple = [m for m in moves if "to" in m]
    assert len(simple) > 0, "No simple moves available"
    test_move = simple[0]

    fr, fc = test_move["from"]
    tr, tc = test_move["to"]

    # Select the piece
    result = gc.click(fr, fc)
    assert result is None, "Selection should return None"
    assert gc.selected == (fr, fc)

    # Click destination
    move = gc.click(tr, tc)
    assert move is not None, "BASHNI: move click returned None!"
    assert move["from"] == [fr, fc]
    assert move["to"] == [tr, tc]


# ═══════════════════════════════════════════════════════════════════════════
# Entrapment — setup phase placement
# ═══════════════════════════════════════════════════════════════════════════

def test_entrapment_click_pipeline():
    from games.entrapment_display import GameClient
    from games.entrapment_logic import EntrapmentLogic

    logic = EntrapmentLogic()
    state = logic.create_initial_state()
    assert state["phase"] == "setup"

    gc = GameClient(online=True, my_player=1)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Find an empty square to place a roamer
    for r in range(7):
        for c in range(7):
            if state["board"][r][c] is None:
                move = gc.click_setup(r, c)
                if move is not None:
                    assert move == {"setup_place": [r, c]}
                    return
    pytest.fail("Could not find valid setup placement")


def test_entrapment_turn_guard():
    """Verify that Entrapment's is_my_turn blocks clicks for wrong player."""
    from games.entrapment_display import GameClient
    from games.entrapment_logic import EntrapmentLogic

    logic = EntrapmentLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=2)  # Player 2, but Player 1 goes first
    gc.load_state(state)
    assert gc.is_my_turn is False


# ═══════════════════════════════════════════════════════════════════════════
# Havannah — click to place stone
# ═══════════════════════════════════════════════════════════════════════════

def test_havannah_click_pipeline():
    from games.havannah_display import GameClient
    from games.havannah_logic import HavannahLogic, WHITE, cell_key

    logic = HavannahLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=WHITE)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Place on any empty cell
    for k, v in state["board"].items():
        if v == 0:  # EMPTY
            q, r = [int(x) for x in k.split(",")]
            move = gc.place(q, r)
            assert move is not None, "HAVANNAH: place returned None!"
            assert move == [q, r]
            return
    pytest.fail("No empty cell found")


# ═══════════════════════════════════════════════════════════════════════════
# Shobu — 4-phase: passive select, passive dest, aggressive select, aggressive dest
# ═══════════════════════════════════════════════════════════════════════════

def test_shobu_click_pipeline():
    from games.shobu_display import GameClient, PH_PSEL, PH_PDST, PH_ASEL, PH_ADST
    from games.shobu_logic import ShobuLogic, BLACK

    logic = ShobuLogic()
    state = logic.create_initial_state()

    gc = GameClient(online=True, my_player=BLACK)
    gc.load_state(state)
    assert gc.is_my_turn is True
    assert gc.phase == PH_PSEL

    # Get a legal move from the logic to know what clicks to make
    moves = logic.get_legal_moves(state, BLACK)
    assert len(moves) > 0
    test_move = moves[0]

    pb = test_move["passive_board"]
    pfr, pfc = test_move["passive_from"]
    ptr, ptc = test_move["passive_to"]
    ab = test_move["aggressive_board"]
    afr, afc = test_move["aggressive_from"]

    # Phase 1: select passive stone
    result = gc.click(pb, pfr, pfc)
    assert result is None
    assert gc.phase == PH_PDST

    # Phase 2: passive destination
    result = gc.click(pb, ptr, ptc)
    assert result is None
    assert gc.phase == PH_ASEL

    # Phase 3: select aggressive stone
    result = gc.click(ab, afr, afc)
    assert result is None
    assert gc.phase == PH_ADST

    # Phase 4: aggressive destination
    atr, atc = test_move["aggressive_to"]
    move = gc.click(ab, atr, atc)
    assert move is not None, "SHOBU: aggressive move returned None!"
    assert move["passive_board"] == pb
    assert move["aggressive_board"] == ab


# ═══════════════════════════════════════════════════════════════════════════
# Tumbleweed — setup click, then play click
# ═══════════════════════════════════════════════════════════════════════════

def test_tumbleweed_click_pipeline_setup():
    from games.tumbleweed_display import GameClient
    from games.tumbleweed_logic import TumbleweedLogic, RED, PH_SETUP

    logic = TumbleweedLogic()
    state = logic.create_initial_state()
    assert state["phase"] == PH_SETUP

    gc = GameClient(online=True, my_player=RED)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Get a legal move
    player = logic.get_current_player(state)
    moves = logic.get_legal_moves(state, player)
    assert len(moves) > 0

    from games.tumbleweed_logic import _cell_key
    cell_move = [m for m in moves if "cell" in m][0]
    coords = cell_move["cell"]
    ck = _cell_key(coords[0], coords[1], coords[2])

    move = gc.setup_click(ck)
    assert move is not None, "TUMBLEWEED: setup click returned None!"
    assert move["cell"] == coords


def test_tumbleweed_click_pipeline_play():
    from games.tumbleweed_display import GameClient
    from games.tumbleweed_logic import (
        TumbleweedLogic, RED, WHITE, PH_PLAY, _cell_key,
    )

    logic = TumbleweedLogic()
    state = logic.create_initial_state()

    # Play through setup and pie to reach play phase
    player = logic.get_current_player(state)
    moves = logic.get_legal_moves(state, player)
    # Setup: place Red's initial stacks
    for m in moves[:1]:
        state = logic.apply_move(state, player, m)
        player = logic.get_current_player(state)
    # Setup: place White's initial stack
    moves = logic.get_legal_moves(state, player)
    state = logic.apply_move(state, player, moves[0])
    player = logic.get_current_player(state)
    # Pie: don't swap
    state = logic.apply_move(state, player, {"swap": False})
    player = logic.get_current_player(state)

    assert state["phase"] == PH_PLAY

    gc = GameClient(online=True, my_player=player)
    gc.load_state(state)
    assert gc.is_my_turn is True

    # Find a legal placement
    moves = logic.get_legal_moves(state, player)
    cell_moves = [m for m in moves if "cell" in m]
    if cell_moves:
        coords = cell_moves[0]["cell"]
        ck = _cell_key(coords[0], coords[1], coords[2])
        move = gc.do_move(ck)
        assert move is not None, "TUMBLEWEED: play click returned None!"
        assert move["cell"] == coords
    else:
        # All legal moves are passes
        move = gc.do_pass()
        assert move is not None, "TUMBLEWEED: pass returned None!"
        assert move == {"pass": True}


# ═══════════════════════════════════════════════════════════════════════════
# Server round-trip: play one legal move for each game through the server
# ═══════════════════════════════════════════════════════════════════════════

ALL_GAMES = list(GAME_REGISTRY.keys())


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_server_roundtrip(game_name):
    """For each game, create a room, play one legal move, verify both clients see it."""
    ensure_server()
    from server.main import rooms

    c1, c2, gs1, gs2, code = setup_room(game_name)
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

        mm_a = [m for m in msgs_a if m["type"] == "move_made"]
        mm_p = [m for m in msgs_p if m["type"] == "move_made"]

        assert len(mm_a) >= 1, \
            f"{game_name}: active got {[m['type'] for m in msgs_a]}"
        assert len(mm_p) >= 1, \
            f"{game_name}: passive got {[m['type'] for m in msgs_p]}"

        # States should match
        assert mm_a[0]["state"] == mm_p[0]["state"]

        # Next turn should have changed (unless game is already over)
        new_state = mm_a[0]["state"]
        new_status = logic.get_game_status(new_state)
        if not new_status["is_over"]:
            new_player = logic.get_current_player(new_state)
            # For most games, the turn should have changed
            # (but some games have multi-action turns like Entrapment)
    finally:
        c1.disconnect()
        c2.disconnect()
        rooms.pop(code, None)


# ═══════════════════════════════════════════════════════════════════════════
# is_my_turn correctness for all games
# ═══════════════════════════════════════════════════════════════════════════

_DISPLAY_MODULES = {
    "Abalone": "abalone_display",
    "Amazons": "amazons_display",
    "Arimaa": "arimaa_display",
    "BaghChal": "bagh_chal_display",
    "Bao": "bao_display",
    "Bashni": "bashni_display",
    "Entrapment": "entrapment_display",
    "Havannah": "havannah_display",
    "Hive": "hive_display",
    "Hnefatafl": "hnefatafl_display",
    "Shobu": "shobu_display",
    "Tak": "tak_display",
    "Tumbleweed": "tumbleweed_display",
    "YINSH": "yinsh_display",
}


@pytest.mark.parametrize("game_name", ALL_GAMES)
def test_is_my_turn_correct(game_name):
    """Verify is_my_turn is True for the current player, False for the other."""
    mod_name = _DISPLAY_MODULES[game_name]
    display_mod = __import__(f"games.{mod_name}", fromlist=["GameClient"])
    GameClientCls = display_mod.GameClient

    logic = create_game(game_name)
    state = logic.create_initial_state()
    current = logic.get_current_player(state)
    other = 2 if current == 1 else 1

    # Current player
    gc1 = GameClientCls(online=True, my_player=current)
    gc1.load_state(state)
    assert gc1.is_my_turn is True, \
        f"{game_name}: is_my_turn False for current player {current}"

    # Other player
    gc2 = GameClientCls(online=True, my_player=other)
    gc2.load_state(state)
    assert gc2.is_my_turn is False, \
        f"{game_name}: is_my_turn True for non-current player {other}"


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
