"""Tests for the Hnefatafl display module's online multiplayer support.

Verifies that GameClient correctly behaves in both local and online modes,
and that the run_online entry point integrates with the server via
two NetworkClient instances playing a real game.
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

from games.hnefatafl_logic import (
    HnefataflLogic,
    PLAYER_ATTACKER,
    PLAYER_DEFENDER,
    ATTACKER,
    DEFENDER,
    KING,
)
from games.hnefatafl_display import GameClient, Renderer, run_online, WIN_W, WIN_H


# ── Unit tests for GameClient ────────────────────────────────────────────────


def test_local_mode_unchanged():
    """Default (local) mode should work exactly as before."""
    g = GameClient()
    assert g.online is False
    assert g.my_player is None
    assert g.is_my_turn is True
    assert g.game_over is False
    assert g.turn == PLAYER_ATTACKER  # attackers move first

    # Selecting and moving should apply locally and return None
    board = g.board
    for r in range(11):
        for c in range(11):
            if board[r][c] == ATTACKER:
                result = g.click(r, c)
                if g.sel is not None and g.targets:
                    tr, tc = g.targets[0]
                    move_result = g.click(tr, tc)
                    assert move_result is None, "Local mode click should return None"
                    assert g.turn == PLAYER_DEFENDER, "Turn should switch"
                    return
    assert False, "No attacker piece found"


def test_online_mode_is_my_turn():
    """is_my_turn should correctly reflect whose turn it is."""
    logic = HnefataflLogic()
    state = logic.create_initial_state()

    # Player 1 = attacker, attacker moves first
    g1 = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g1.load_state(state)
    assert g1.is_my_turn is True

    g2 = GameClient(online=True, my_player=PLAYER_DEFENDER)
    g2.load_state(state)
    assert g2.is_my_turn is False


def test_online_click_blocked_when_not_turn():
    """Clicks should be completely ignored when it's not the player's turn."""
    g = GameClient(online=True, my_player=PLAYER_DEFENDER)
    g.load_state(HnefataflLogic().create_initial_state())

    # Try clicking every cell — should all return None
    for r in range(11):
        for c in range(11):
            result = g.click(r, c)
            assert result is None
    assert g.sel is None
    assert g.targets == []


def test_online_click_returns_move():
    """In online mode, clicking a valid destination should return the move."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    # Find an attacker, select it, move to a valid target
    for r in range(11):
        for c in range(11):
            if g.board[r][c] == ATTACKER:
                g.click(r, c)
                if g.sel and g.targets:
                    fr, fc = g.sel
                    tr, tc = g.targets[0]
                    move = g.click(tr, tc)
                    assert move is not None
                    assert move == [[fr, fc], [tr, tc]]
                    # State should NOT have changed (server handles it)
                    assert g.turn == PLAYER_ATTACKER
                    return
    assert False, "Could not find a valid attacker move"


def test_online_click_selection_returns_none():
    """Selecting a piece (without choosing destination) returns None."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    for r in range(11):
        for c in range(11):
            if g.board[r][c] == ATTACKER:
                result = g.click(r, c)
                if g.sel is not None:
                    assert result is None, "Selection alone should return None"
                    return
    assert False, "No attacker found"


def test_load_state():
    """load_state should replace the full game state and clear selection."""
    logic = HnefataflLogic()
    state1 = logic.create_initial_state()
    state2 = logic.create_initial_state()

    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(state1)

    # Select a piece
    for r in range(11):
        for c in range(11):
            if g.board[r][c] == ATTACKER:
                g.click(r, c)
                if g.sel:
                    break
        if g.sel:
            break

    assert g.sel is not None, "Should have selected a piece"

    # Load new state — selection should clear
    g.load_state(state2)
    assert g.sel is None
    assert g.targets == []


def test_set_game_over_normal():
    """set_game_over should correctly flag the game as over."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    g.set_game_over(winner=PLAYER_ATTACKER, is_draw=False)
    assert g.game_over is True
    assert g.winner == PLAYER_ATTACKER


def test_set_game_over_forfeit():
    """Forfeit should produce a forfeit message."""
    g = GameClient(online=True, my_player=PLAYER_DEFENDER)
    g.load_state(HnefataflLogic().create_initial_state())

    g.set_game_over(winner=PLAYER_DEFENDER, is_draw=False, reason="forfeit")
    assert g.game_over is True
    assert "forfeit" in g.message.lower()


def test_set_game_over_draw():
    """Draw should produce a draw message."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    g.set_game_over(winner=None, is_draw=True)
    assert g.game_over is True
    assert "draw" in g.message.lower()


def test_undo_blocked_online():
    """Undo should be a no-op in online mode."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    g.undo()  # should silently do nothing
    assert g.turn == PLAYER_ATTACKER


def test_opponent_disconnected_flag():
    """opponent_disconnected flag should be settable."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())

    assert g.opponent_disconnected is False
    g.opponent_disconnected = True
    assert g.opponent_disconnected is True
    g.opponent_disconnected = False
    assert g.opponent_disconnected is False


def test_net_error_field():
    """net_error should start empty and be settable."""
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    assert g.net_error == ""
    g.net_error = "Connection lost"
    assert g.net_error == "Connection lost"


# ── Renderer tests (headless) ────────────────────────────────────────────────


def test_renderer_draws_local():
    """Renderer should draw without errors in local mode."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    renderer = Renderer(screen)
    g = GameClient()
    renderer.draw(g)  # should not raise
    pygame.quit()


def test_renderer_draws_online():
    """Renderer should draw without errors in online mode."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    renderer = Renderer(screen)
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())
    renderer.draw(g)  # should not raise
    pygame.quit()


def test_renderer_draws_online_opponent_disconnected():
    """Renderer should draw the disconnected overlay without errors."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    renderer = Renderer(screen)
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())
    g.opponent_disconnected = True
    renderer.draw(g)  # should not raise
    pygame.quit()


def test_renderer_draws_online_game_over():
    """Renderer should draw the game-over banner in online mode."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    renderer = Renderer(screen)
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())
    g.set_game_over(winner=PLAYER_ATTACKER, is_draw=False)
    renderer.draw(g)  # should not raise
    pygame.quit()


def test_renderer_draws_online_net_error():
    """Renderer should draw the error bar in online mode."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    renderer = Renderer(screen)
    g = GameClient(online=True, my_player=PLAYER_ATTACKER)
    g.load_state(HnefataflLogic().create_initial_state())
    g.net_error = "Connection lost"
    renderer.draw(g)  # should not raise
    pygame.quit()


# ── Integration test: two clients play via real server ────────────────────────


def test_online_integration():
    """Two GameClients play a few moves through the real server."""
    import uvicorn
    from server.main import app, rooms
    from client.network import NetworkClient

    HOST = "127.0.0.1"
    PORT = 18780
    WS_URL = f"ws://{HOST}:{PORT}/ws"

    rooms.clear()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    def poll_until(client, msg_type, timeout=3.0):
        """Collect messages until we see the desired type."""
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

    # Player 1 creates room
    c1 = NetworkClient(WS_URL)
    c1.connect()
    time.sleep(0.3)
    c1.create_room("Hnefatafl")
    msgs1 = poll_until(c1, "room_created")
    code = c1.room_code
    assert code is not None

    # Player 2 joins
    c2 = NetworkClient(WS_URL)
    c2.connect()
    time.sleep(0.3)
    c2.join_room(code)

    # Both should receive game_started
    msgs1 = poll_until(c1, "game_started")
    msgs2 = poll_until(c2, "game_started")

    gs1 = [m for m in msgs1 if m["type"] == "game_started"][0]
    gs2 = [m for m in msgs2 if m["type"] == "game_started"][0]

    assert gs1["your_player"] == 1
    assert gs2["your_player"] == 2
    assert gs1["current_turn"] == PLAYER_ATTACKER

    # Create online GameClients
    g1 = GameClient(online=True, my_player=gs1["your_player"])
    g1.load_state(gs1["state"])

    g2 = GameClient(online=True, my_player=gs2["your_player"])
    g2.load_state(gs2["state"])

    # Player 1 (attacker) should be able to make a move
    assert g1.is_my_turn is True
    assert g2.is_my_turn is False

    # Find and make a valid move for player 1
    move = None
    for r in range(11):
        for c in range(11):
            if g1.board[r][c] == ATTACKER:
                g1.click(r, c)
                if g1.sel and g1.targets:
                    tr, tc = g1.targets[0]
                    move = g1.click(tr, tc)
                    break
        if move:
            break
    assert move is not None, "Should have found a valid attacker move"

    # Send move to server
    c1.send_move(move)

    # Both should receive move_made
    msgs1 = poll_until(c1, "move_made")
    msgs2 = poll_until(c2, "move_made")

    mm1 = [m for m in msgs1 if m["type"] == "move_made"]
    mm2 = [m for m in msgs2 if m["type"] == "move_made"]
    assert len(mm1) >= 1, f"Player 1 should get move_made, got: {[m['type'] for m in msgs1]}"
    assert len(mm2) >= 1, f"Player 2 should get move_made, got: {[m['type'] for m in msgs2]}"

    # Update both clients from server state
    g1.load_state(mm1[0]["state"])
    g2.load_state(mm2[0]["state"])

    # Now it should be defender's turn
    assert g1.turn == PLAYER_DEFENDER
    assert g2.turn == PLAYER_DEFENDER
    assert g1.is_my_turn is False
    assert g2.is_my_turn is True

    # Player 2 (defender) makes a move
    move2 = None
    for r in range(11):
        for c in range(11):
            if g2.board[r][c] in (DEFENDER, KING):
                g2.click(r, c)
                if g2.sel and g2.targets:
                    tr, tc = g2.targets[0]
                    move2 = g2.click(tr, tc)
                    break
        if move2:
            break
    assert move2 is not None, "Should have found a valid defender move"

    c2.send_move(move2)
    msgs1 = poll_until(c1, "move_made")
    msgs2 = poll_until(c2, "move_made")

    mm1 = [m for m in msgs1 if m["type"] == "move_made"]
    mm2 = [m for m in msgs2 if m["type"] == "move_made"]
    assert len(mm1) >= 1
    assert len(mm2) >= 1

    g1.load_state(mm1[0]["state"])
    g2.load_state(mm2[0]["state"])

    # Back to attacker's turn
    assert g1.turn == PLAYER_ATTACKER
    assert g1.is_my_turn is True
    assert g2.is_my_turn is False

    c1.disconnect()
    c2.disconnect()
    rooms.clear()


# ── Runner ────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    PASS = FAIL = 0
    tests = [
        test_local_mode_unchanged,
        test_online_mode_is_my_turn,
        test_online_click_blocked_when_not_turn,
        test_online_click_returns_move,
        test_online_click_selection_returns_none,
        test_load_state,
        test_set_game_over_normal,
        test_set_game_over_forfeit,
        test_set_game_over_draw,
        test_undo_blocked_online,
        test_opponent_disconnected_flag,
        test_net_error_field,
        test_renderer_draws_local,
        test_renderer_draws_online,
        test_renderer_draws_online_opponent_disconnected,
        test_renderer_draws_online_game_over,
        test_renderer_draws_online_net_error,
        test_online_integration,
    ]
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            PASS += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            FAIL += 1
    print(f"\n{PASS + FAIL} tests: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
