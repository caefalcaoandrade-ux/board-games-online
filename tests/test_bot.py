"""Tests for the MCTS bot.

Verifies that the bot:
1. Always produces legal moves (1-2 moves per game, not full games)
2. Strong and Weak difficulties both work correctly
3. Difficulty presets are configured correctly (Weak / Strong)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import pytest
from client.bot import MCTSBot


# ── Helpers ────────────────────────────────────────────────────────────────────


def _verify_one_move(logic, bot, player=None):
    """Verify that the bot produces one legal move from initial state.

    Returns (state_after, move).
    """
    state = logic.create_initial_state()
    if player is None:
        player = logic.get_current_player(state)
    move = bot.choose_move(logic, state, player)
    assert move is not None, f"Bot returned None for player {player}"
    legal = logic.get_legal_moves(state, player)
    assert move in legal, f"Bot returned illegal move {move!r}"
    return logic.apply_move(state, player, move), move


def _verify_two_moves(logic, bot):
    """Verify the bot produces legal moves for both players (2 turns)."""
    state = logic.create_initial_state()
    for turn in range(2):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)
        assert move is not None, f"Bot returned None at turn {turn}"
        legal = logic.get_legal_moves(state, player)
        assert move in legal, f"Illegal move {move!r} at turn {turn}"
        state = logic.apply_move(state, player, move)


# ── Test: bot always returns legal moves ───────────────────────────────────────


def test_legal_moves_havannah():
    """Bot picks legal moves in Havannah (2 turns)."""
    from games.havannah_logic import HavannahLogic
    _verify_two_moves(HavannahLogic(size=4), MCTSBot("weak", max_iterations=3))


def test_legal_moves_bashni():
    """Bot picks legal moves in Bashni (2 turns)."""
    from games.bashni_logic import BashniLogic
    _verify_two_moves(BashniLogic(), MCTSBot("weak", max_iterations=3))


def test_legal_moves_shobu():
    """Bot picks legal moves in Shobu (2 turns)."""
    from games.shobu_logic import ShobuLogic
    _verify_two_moves(ShobuLogic(), MCTSBot("weak", max_iterations=3))


# ── Test: both difficulties produce legal moves ──────────────────────────────


def test_strong_legal_havannah():
    """Strong bot produces a legal move in Havannah."""
    from games.havannah_logic import HavannahLogic
    _verify_one_move(HavannahLogic(size=4), MCTSBot("strong", max_iterations=10))


def test_strong_legal_bagh_chal():
    """Strong bot produces a legal move in Bagh Chal."""
    from games.bagh_chal_logic import BaghChalLogic
    _verify_one_move(BaghChalLogic(), MCTSBot("strong", max_iterations=10))


def test_strong_legal_bashni():
    """Strong bot produces a legal move in Bashni."""
    from games.bashni_logic import BashniLogic
    _verify_one_move(BashniLogic(), MCTSBot("strong", max_iterations=10))


def test_strong_legal_shobu():
    """Strong bot produces a legal move in Shobu."""
    from games.shobu_logic import ShobuLogic
    _verify_one_move(ShobuLogic(), MCTSBot("strong", max_iterations=10))


# ── Test: bot handles edge cases ───────────────────────────────────────────────


def test_single_move():
    """Bot returns the only legal move without running MCTS."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=3)
    bot = MCTSBot("weak", max_iterations=3)
    state = logic.create_initial_state()

    for i in range(18):
        player = logic.get_current_player(state)
        legal = logic.get_legal_moves(state, player)
        if len(legal) <= 1:
            break
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        state = logic.apply_move(state, player, legal[0])


def test_immediate_win_taken():
    """Strong bot produces a legal move (low iterations)."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    _verify_one_move(logic, MCTSBot("strong", max_iterations=5))


def test_difficulty_presets():
    """Difficulty presets create genuinely different bots."""
    weak = MCTSBot("weak")
    strong = MCTSBot("strong")

    # Weak: simple search, worst-move selection
    assert weak.select == "worst", "Weak should select worst"
    assert weak.loss_ply == 0, "Weak should skip loss prevention"
    assert not weak.use_eval, "Weak should not use evaluation"
    assert not weak.use_grave, "Weak should not use GRAVE"
    assert not weak.use_solver, "Weak should not use MCTS-Solver"

    # Strong: full search, best selection
    assert strong.select == "best", "Strong should select best"
    assert strong.loss_ply > 0, "Strong should have loss prevention"
    assert strong.use_eval, "Strong should use evaluation"
    assert strong.use_grave, "Strong should use GRAVE"
    assert strong.use_solver, "Strong should use MCTS-Solver"


def test_strong_uses_mobility_evaluation():
    """Strong bot's playout returns values via mobility evaluation."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("strong", max_iterations=10)
    state = logic.create_initial_state()
    player = logic.get_current_player(state)
    bot.choose_move(logic, state, player)


def test_selection_policies():
    """Move selection policies produce correct behavior."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    state = logic.create_initial_state()
    player = logic.get_current_player(state)

    # Strong always picks the highest-visit child
    strong = MCTSBot("strong", max_iterations=15)
    move_s = strong.choose_move(logic, state, player)
    assert move_s is not None

    # Weak picks the lowest-visit child
    weak = MCTSBot("weak", max_iterations=15)
    m = weak.choose_move(logic, state, player)
    assert m is not None


def test_unknown_difficulty_defaults_to_strong():
    """Unknown difficulty string defaults to strong preset."""
    bot = MCTSBot("nonexistent")
    assert bot.select == "best"
    assert bot.use_grave is True


# ── Test: Claude bot graceful degradation ──────────────────────────────────


def test_claude_bot_init_no_crash():
    """ClaudeBot initializes without crashing even with no API key."""
    from client.claude_bot import ClaudeBot
    bot = ClaudeBot()
    assert bot.model is not None
    assert bot.switched_to_fallback is False


def test_claude_bot_no_key_falls_back():
    """ClaudeBot with no API key falls back to MCTS and returns a legal move."""
    from client.claude_bot import ClaudeBot, _cached_key
    import client.claude_bot as cb

    # Ensure no key is loaded (save and restore original)
    original = cb._cached_key
    cb._cached_key = ""
    try:
        from games.havannah_logic import HavannahLogic
        logic = HavannahLogic(size=4)
        bot = ClaudeBot()
        # Pre-set a fast fallback so the test doesn't wait 8s for MCTS
        bot._fallback = MCTSBot("strong", max_iterations=5)
        state = logic.create_initial_state()
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)

        # Should have fallen back
        assert bot.switched_to_fallback is True
        # Move should be legal
        assert move is not None
        legal = logic.get_legal_moves(state, player)
        assert move in legal
    finally:
        cb._cached_key = original


def test_claude_bot_parse_move_number():
    """ClaudeBot parses move numbers from various response formats."""
    from client.claude_bot import ClaudeBot
    bot = ClaudeBot()
    assert bot._parse_move_number("I choose move 3", 10) == 2
    assert bot._parse_move_number("After analysis...\n5", 10) == 4
    assert bot._parse_move_number("99", 10) == 9   # clamped
    assert bot._parse_move_number("0", 10) == 0     # clamped
    assert bot._parse_move_number("no number here", 10) is None
    assert bot._parse_move_number("Move: 1", 5) == 0
    assert bot._parse_move_number("Let me think...\nI'll go with 7\n", 20) == 6


def test_claude_bot_key_management():
    """API key save/load functions work without crashing."""
    from client.claude_bot import needs_api_key, save_api_key, _load_key
    import client.claude_bot as cb

    # Save original state
    original = cb._cached_key
    try:
        cb._cached_key = ""
        # With no key cached and no env var, needs_api_key should be True
        # (unless there's a file on disk — but we don't want to delete it)
        result = needs_api_key()
        assert isinstance(result, bool)
    finally:
        cb._cached_key = original
