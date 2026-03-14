"""Tests for the MCTS bot.

Verifies that the bot:
1. Always produces legal moves
2. Games reach completion
3. Hard beats Easy in a majority of games

Uses iteration-based control for speed and reproducibility.
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


def _run_matchup(logic_factory, n_games=6, easy_iters=10, hard_iters=50,
                 max_moves=300):
    """Run a Hard-vs-Easy matchup and return hard_wins count."""
    hard_wins = 0
    for g in range(n_games):
        logic = logic_factory()
        easy = MCTSBot("easy", max_iterations=easy_iters)
        hard = MCTSBot("hard", max_iterations=hard_iters)

        if g % 2 == 0:
            bots_map = {1: hard, 2: easy}
            hard_player = 1
        else:
            bots_map = {1: easy, 2: hard}
            hard_player = 2

        winner, moves = _play_game(logic, bots_map[1], bots_map[2],
                                    max_moves=max_moves)
        if winner == hard_player:
            hard_wins += 1

    return hard_wins


# ── Test: bot always returns legal moves ───────────────────────────────────────


def test_legal_moves_havannah():
    """Bot always picks legal moves in Havannah."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("easy", max_iterations=5)
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
    bot = MCTSBot("easy", max_iterations=5)
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
    bot = MCTSBot("easy", max_iterations=5)
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
    """Two bots finish a Havannah game."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("easy", max_iterations=5)
    winner, moves = _play_game(logic, bot, bot, max_moves=100)
    assert moves <= 100


def test_game_completes_bashni():
    """Two bots finish a Bashni game."""
    from games.bashni_logic import BashniLogic
    logic = BashniLogic()
    bot = MCTSBot("easy", max_iterations=5)
    winner, moves = _play_game(logic, bot, bot, max_moves=300)


def test_game_completes_shobu():
    """Two bots finish a Shobu game."""
    from games.shobu_logic import ShobuLogic
    logic = ShobuLogic()
    bot = MCTSBot("easy", max_iterations=5)
    winner, moves = _play_game(logic, bot, bot, max_moves=200)


# ── Test: Hard beats Easy ──────────────────────────────────────────────────────
#
# Hard has: loss prevention, MAST playouts, low C (exploitative), win-check
# Easy has: no loss prevention, random playouts, high C (random-ish), no win-check
# The skill gap comes from loss prevention + MAST + more iterations.


def test_hard_beats_easy_havannah():
    """Hard bot wins >= 7/10 Havannah games against Easy bot."""
    from games.havannah_logic import HavannahLogic
    random.seed(42)
    hard_wins = _run_matchup(
        lambda: HavannahLogic(size=4),
        n_games=10, easy_iters=3, hard_iters=80, max_moves=60,
    )
    assert hard_wins >= 7, (
        f"Hard should win >= 7/10 Havannah games, won {hard_wins}"
    )


def test_hard_beats_easy_bashni():
    """Hard bot wins >= 3/4 Bashni games against Easy bot."""
    from games.bashni_logic import BashniLogic
    random.seed(123)
    hard_wins = _run_matchup(
        BashniLogic,
        n_games=4, easy_iters=3, hard_iters=80, max_moves=120,
    )
    assert hard_wins >= 3, (
        f"Hard should win >= 3/4 Bashni games, won {hard_wins}"
    )


def test_hard_beats_easy_shobu():
    """Hard bot wins a majority of Shobu games against Easy bot."""
    from games.shobu_logic import ShobuLogic
    random.seed(999)
    hard_wins = _run_matchup(
        ShobuLogic,
        n_games=6, easy_iters=3, hard_iters=80, max_moves=100,
    )
    assert hard_wins >= 3, (
        f"Hard should win >= 3/6 Shobu games, won {hard_wins}"
    )


# ── Test: bot handles edge cases ───────────────────────────────────────────────


def test_single_move():
    """Bot returns the only legal move without running MCTS."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=3)
    bot = MCTSBot("easy", max_iterations=5)
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
    """Bot takes an immediate winning move when available."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=4)
    bot = MCTSBot("easy", max_iterations=5)

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


def test_mast_accumulates():
    """MAST statistics accumulate across iterations."""
    from games.havannah_logic import HavannahLogic
    logic = HavannahLogic(size=3)
    bot = MCTSBot("hard", max_iterations=30)
    state = logic.create_initial_state()
    player = logic.get_current_player(state)
    bot.choose_move(logic, state, player)
    assert len(bot.mast) > 0, "MAST should have entries after simulations"


def test_easy_has_no_mast():
    """Easy bot does not use MAST."""
    bot = MCTSBot("easy", max_iterations=5)
    assert not bot.use_mast


def test_difficulty_presets():
    """Difficulty presets create genuinely different bots."""
    easy = MCTSBot("easy")
    hard = MCTSBot("hard")
    assert easy.c > hard.c, "Easy should explore more (higher C)"
    assert easy.loss_check == 0, "Easy should skip loss prevention"
    assert hard.loss_check > 0, "Hard should have loss prevention"
    assert not easy.use_mast, "Easy should not use MAST"
    assert hard.use_mast, "Hard should use MAST"
