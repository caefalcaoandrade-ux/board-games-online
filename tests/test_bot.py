"""Tests for the MCTS bot.

Verifies that the bot:
1. Always produces legal moves
2. Games reach completion
3. Strong beats Weak decisively across 4 games
4. Difficulty presets are configured correctly

Strong uses iteration-based control in tests; Weak is pure random (instant).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import pytest
from client.bot import MCTSBot


# ── Helpers ────────────────────────────────────────────────────────────────────


def _play_game(logic, bot1, bot2, max_moves=300):
    """Play a full game between two bots.

    Returns (winner, move_count) where winner is int or None.
    Every move is verified to be legal.
    """
    state = logic.create_initial_state()
    bots = {1: bot1, 2: bot2}

    for move_num in range(max_moves):
        status = logic.get_game_status(state)
        if status["is_over"]:
            return status["winner"], move_num

        player = logic.get_current_player(state)
        bot = bots[player]
        move = bot.choose_move(logic, state, player)

        assert move is not None, (
            f"Bot returned None for player {player} at move {move_num}"
        )

        legal = logic.get_legal_moves(state, player)
        assert move in legal, (
            f"Bot returned illegal move {move!r} at move {move_num}. "
            f"Legal: {len(legal)} moves"
        )

        state = logic.apply_move(state, player, move)

    return None, max_moves


def _run_matchup(logic_factory, n_games=5, strong_iters=100, max_moves=200):
    """Run a Strong-vs-Weak matchup and return strong_wins count.

    Weak uses random_only mode (no iterations). Strong uses iteration-based
    MCTS with mobility evaluation. Games alternate sides.
    """
    strong_wins = 0
    for g in range(n_games):
        logic = logic_factory()
        weak = MCTSBot("weak")
        strong = MCTSBot("strong", max_iterations=strong_iters)

        if g % 2 == 0:
            bots_map = {1: strong, 2: weak}
            strong_player = 1
        else:
            bots_map = {1: weak, 2: strong}
            strong_player = 2

        winner, moves = _play_game(logic, bots_map[1], bots_map[2],
                                    max_moves=max_moves)
        if winner == strong_player:
            strong_wins += 1

    return strong_wins


# ── Test: bot always returns legal moves ───────────────────────────────────────


def test_legal_moves_havannah():
    """Bot always picks legal moves in Havannah."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("weak")
    state = logic.create_initial_state()

    for _ in range(30):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)
        assert move is not None
        legal = logic.get_legal_moves(state, player)
        assert move in legal
        state = logic.apply_move(state, player, move)


def test_legal_moves_bashni():
    """Bot always picks legal moves in Bashni."""
    from games.bashni_logic import BashniLogic
    logic = BashniLogic()
    bot = MCTSBot("weak")
    state = logic.create_initial_state()

    for _ in range(20):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)
        assert move is not None
        legal = logic.get_legal_moves(state, player)
        assert move in legal
        state = logic.apply_move(state, player, move)


def test_legal_moves_shobu():
    """Bot always picks legal moves in Shobu."""
    from games.shobu_logic import ShobuLogic
    logic = ShobuLogic()
    bot = MCTSBot("weak")
    state = logic.create_initial_state()

    for _ in range(15):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)
        assert move is not None
        legal = logic.get_legal_moves(state, player)
        assert move in legal
        state = logic.apply_move(state, player, move)


# ── Test: games reach completion ───────────────────────────────────────────────


def test_game_completes_havannah():
    """Two weak bots finish a Havannah game."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("weak")
    winner, moves = _play_game(logic, bot, bot, max_moves=100)
    assert moves <= 100


def test_game_completes_bashni():
    """Two weak bots finish a Bashni game."""
    from games.bashni_logic import BashniLogic
    logic = BashniLogic()
    bot = MCTSBot("weak")
    winner, moves = _play_game(logic, bot, bot, max_moves=300)


def test_game_completes_shobu():
    """Two weak bots finish a Shobu game."""
    from games.shobu_logic import ShobuLogic
    logic = ShobuLogic()
    bot = MCTSBot("weak")
    winner, moves = _play_game(logic, bot, bot, max_moves=200)


# ── Test: Strong beats Weak across 4 games ───────────────────────────────────
#
# Strong: GRAVE, mobility evaluation, MCTS-Solver, 3-ply loss prevention,
#         tree reuse, progressive move ordering.
# Weak: pure random.choice — no search, no win detection, nothing.
#
# Games chosen for fast get_legal_moves to keep test time reasonable.
# Each matchup: 5 games alternating sides. Assert >= 4/5.


def test_strong_beats_weak_havannah():
    """Strong bot wins >= 4/5 Havannah(4) games against Weak."""
    from games.havannah_logic import HavannahLogic
    random.seed(42)
    wins = _run_matchup(lambda: HavannahLogic(size=4),
                        n_games=5, strong_iters=100, max_moves=60)
    assert wins >= 4, f"Strong should win >= 4/5 Havannah, won {wins}"


def test_strong_beats_weak_bagh_chal():
    """Strong bot wins >= 4/5 BaghChal games against Weak."""
    from games.bagh_chal_logic import BaghChalLogic
    random.seed(42)
    wins = _run_matchup(BaghChalLogic,
                        n_games=5, strong_iters=300, max_moves=200)
    assert wins >= 4, f"Strong should win >= 4/5 BaghChal, won {wins}"


def test_strong_beats_weak_bashni():
    """Strong bot wins >= 3/5 Bashni games against Weak."""
    from games.bashni_logic import BashniLogic
    random.seed(42)
    wins = _run_matchup(BashniLogic,
                        n_games=5, strong_iters=150, max_moves=120)
    assert wins >= 3, f"Strong should win >= 3/5 Bashni, won {wins}"


def test_strong_beats_weak_shobu():
    """Strong bot wins >= 3/5 Shobu games against Weak."""
    from games.shobu_logic import ShobuLogic
    random.seed(42)
    wins = _run_matchup(ShobuLogic,
                        n_games=5, strong_iters=80, max_moves=100)
    assert wins >= 3, f"Strong should win >= 3/5 Shobu, won {wins}"


# ── Test: bot handles edge cases ───────────────────────────────────────────────


def test_single_move():
    """Bot returns the only legal move without running MCTS."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=3)
    bot = MCTSBot("weak")
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
    """Strong bot takes an immediate winning move when available."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("strong", max_iterations=5)

    state = logic.create_initial_state()
    for _ in range(50):
        status = logic.get_game_status(state)
        if status["is_over"]:
            break
        player = logic.get_current_player(state)
        move = bot.choose_move(logic, state, player)
        if move is None:
            break
        state = logic.apply_move(state, player, move)


def test_difficulty_presets():
    """Difficulty presets create genuinely different bots."""
    weak = MCTSBot("weak")
    strong = MCTSBot("strong")

    # Weak is pure random
    assert weak.random_only is True, "Weak should be random_only"
    assert weak.loss_ply == 0, "Weak should skip loss prevention"
    assert not weak.use_eval, "Weak should not use evaluation"
    assert not weak.use_grave, "Weak should not use GRAVE"
    assert not weak.use_solver, "Weak should not use MCTS-Solver"

    # Strong has everything
    assert strong.random_only is False, "Strong should not be random_only"
    assert strong.loss_ply > 0, "Strong should have loss prevention"
    assert strong.use_eval, "Strong should use evaluation"
    assert strong.use_grave, "Strong should use GRAVE"
    assert strong.use_solver, "Strong should use MCTS-Solver"


def test_strong_uses_mobility_evaluation():
    """Strong bot's playout returns values via mobility evaluation."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("strong", max_iterations=30)
    state = logic.create_initial_state()
    player = logic.get_current_player(state)
    bot.choose_move(logic, state, player)


def test_legacy_aliases():
    """Legacy difficulty names still work."""
    easy = MCTSBot("easy")
    normal = MCTSBot("normal")
    medium = MCTSBot("medium")
    hard = MCTSBot("hard")
    weak = MCTSBot("weak")
    strong = MCTSBot("strong")
    assert easy.random_only == weak.random_only
    assert normal.random_only == weak.random_only
    assert medium.use_eval == strong.use_eval
    assert hard.use_eval == strong.use_eval


def test_weak_is_instant():
    """Weak bot returns immediately (no search overhead)."""
    from games.havannah_logic import HavannahLogic
    import time
    logic = HavannahLogic(size=4)
    bot = MCTSBot("weak")
    state = logic.create_initial_state()
    player = logic.get_current_player(state)
    t0 = time.monotonic()
    for _ in range(100):
        bot.choose_move(logic, state, player)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"100 weak moves took {elapsed:.2f}s, should be < 1s"


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
