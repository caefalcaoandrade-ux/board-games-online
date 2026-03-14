"""
Comprehensive audit of Amazons game logic against rules/amazons_logic.md.

Tests:
  1. Initial board setup
  2. Movement rules (queen-like)
  3. Move structure
  4. Blocking rules (amazons, arrows, board edges)
  5. Win condition
  6. Turn order
  7. Arrow can fire back through vacated origin
  8. Mid-game verification with manually enumerated legal moves
"""

import sys
import os
import copy

# Ensure imports work from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.amazons_logic import (
    AmazonsLogic, BOARD_N, EMPTY, WHITE, BLACK, BLOCKED,
    _W_START, _B_START, _queen_reach, _is_queen_reachable,
    _has_legal_turn,
)


def test_board_size():
    """Rule 1: 10x10 board."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    board = state["board"]
    assert len(board) == 10, f"Expected 10 rows, got {len(board)}"
    for i, row in enumerate(board):
        assert len(row) == 10, f"Row {i}: expected 10 cols, got {len(row)}"
    assert BOARD_N == 10


def test_initial_positions():
    """Rule 4: White amazons at a4,d1,g1,j4; Black at a7,d10,g10,j7."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    board = state["board"]

    # Coordinate mapping: row = 9 - y, col = x
    # where algebraic notation file a-j = x 0-9, rank 1-10 = y 0-9
    expected_white = {
        "a4": (6, 0),   # x=0, y=3 => row=6, col=0
        "d1": (9, 3),   # x=3, y=0 => row=9, col=3
        "g1": (9, 6),   # x=6, y=0 => row=9, col=6
        "j4": (6, 9),   # x=9, y=3 => row=6, col=9
    }
    expected_black = {
        "a7": (3, 0),   # x=0, y=6 => row=3, col=0
        "d10": (0, 3),  # x=3, y=9 => row=0, col=3
        "g10": (0, 6),  # x=6, y=9 => row=0, col=6
        "j7": (3, 9),   # x=9, y=6 => row=3, col=9
    }

    for name, (r, c) in expected_white.items():
        assert board[r][c] == WHITE, (
            f"White amazon expected at {name} = ({r},{c}), "
            f"got {board[r][c]}"
        )

    for name, (r, c) in expected_black.items():
        assert board[r][c] == BLACK, (
            f"Black amazon expected at {name} = ({r},{c}), "
            f"got {board[r][c]}"
        )

    # Count total amazons
    white_count = sum(1 for r in range(10) for c in range(10) if board[r][c] == WHITE)
    black_count = sum(1 for r in range(10) for c in range(10) if board[r][c] == BLACK)
    assert white_count == 4, f"Expected 4 white amazons, got {white_count}"
    assert black_count == 4, f"Expected 4 black amazons, got {black_count}"

    # Count empty squares (should be 92)
    empty_count = sum(1 for r in range(10) for c in range(10) if board[r][c] == EMPTY)
    assert empty_count == 92, f"Expected 92 empty squares, got {empty_count}"


def test_initial_turn_order():
    """Rule 5: White moves first."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    assert state["turn"] == WHITE, f"Expected WHITE (1) to move first, got {state['turn']}"
    assert game.get_current_player(state) == WHITE


def test_turn_alternation():
    """Rule 5: Players alternate turns."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    assert game.get_current_player(state) == WHITE
    moves = game.get_legal_moves(state, WHITE)
    state2 = game.apply_move(state, WHITE, moves[0])
    assert game.get_current_player(state2) == BLACK

    moves2 = game.get_legal_moves(state2, BLACK)
    state3 = game.apply_move(state2, BLACK, moves2[0])
    assert game.get_current_player(state3) == WHITE


def test_move_structure():
    """Rule 6: Move is [[from_r, from_c], [to_r, to_c], [arrow_r, arrow_c]]."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    moves = game.get_legal_moves(state, WHITE)
    assert len(moves) > 0

    for move in moves[:10]:  # check a sample
        assert isinstance(move, list), f"Move must be list, got {type(move)}"
        assert len(move) == 3, f"Move must have 3 parts, got {len(move)}"
        for part in move:
            assert isinstance(part, list), f"Each part must be list, got {type(part)}"
            assert len(part) == 2, f"Each part must have 2 coords, got {len(part)}"
            assert isinstance(part[0], int) and isinstance(part[1], int)
            assert 0 <= part[0] < 10 and 0 <= part[1] < 10


def test_queen_movement_directions():
    """Rule 7: Movement along 8 directions (horizontal, vertical, diagonal)."""
    # Place a single amazon in the center of an empty board
    board = [[EMPTY] * 10 for _ in range(10)]
    board[5][5] = WHITE

    reachable = set(_queen_reach(board, 5, 5))

    # Horizontal: row 5, cols 0-4 and 6-9
    for c in range(10):
        if c != 5:
            assert (5, c) in reachable, f"(5,{c}) should be reachable horizontally"

    # Vertical: col 5, rows 0-4 and 6-9
    for r in range(10):
        if r != 5:
            assert (r, 5) in reachable, f"({r},5) should be reachable vertically"

    # Diagonals
    for d in range(1, 5):
        for dr, dc in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            r, c = 5 + d*dr, 5 + d*dc
            if 0 <= r < 10 and 0 <= c < 10:
                assert (r, c) in reachable, f"({r},{c}) should be reachable diagonally"

    # Total: 9 + 9 + 4*4 + 1*4 = 9 + 9 + 9 + 9 = ... let me count precisely
    # Row 5: 9 squares, Col 5: 9 squares, diag up-left: 5, diag up-right: 4,
    # diag down-left: 4, diag down-right: 4
    # Wait, let me just count: from (5,5), diag (-1,-1): (4,4),(3,3),(2,2),(1,1),(0,0) = 5
    # diag (-1,+1): (4,6),(3,7),(2,8),(1,9) = 4
    # diag (+1,-1): (6,4),(7,3),(8,2),(9,1) = 4
    # diag (+1,+1): (6,6),(7,7),(8,8),(9,9) = 4
    # Total: 9 + 9 + 5 + 4 + 4 + 4 = 35
    assert len(reachable) == 35, f"Expected 35 reachable squares, got {len(reachable)}"


def test_blocking_by_amazons():
    """Rule 7: Amazons block movement (cannot jump over or land on)."""
    board = [[EMPTY] * 10 for _ in range(10)]
    board[5][5] = WHITE
    board[5][7] = BLACK  # blocks rightward at col 7

    reachable = set(_queen_reach(board, 5, 5))

    # Can reach (5,6) but NOT (5,7) or beyond
    assert (5, 6) in reachable, "(5,6) should be reachable"
    assert (5, 7) not in reachable, "(5,7) is blocked by BLACK amazon"
    assert (5, 8) not in reachable, "(5,8) is blocked (behind BLACK amazon)"


def test_blocking_by_arrows():
    """Rule 7: Arrows block movement."""
    board = [[EMPTY] * 10 for _ in range(10)]
    board[5][5] = WHITE
    board[3][3] = BLOCKED  # arrow blocks diagonal

    reachable = set(_queen_reach(board, 5, 5))

    # Diagonal up-left: (4,4) reachable but (3,3) blocked
    assert (4, 4) in reachable
    assert (3, 3) not in reachable
    assert (2, 2) not in reachable


def test_blocking_by_board_edges():
    """Rule 7: Board edges block movement."""
    board = [[EMPTY] * 10 for _ in range(10)]
    board[0][0] = WHITE  # corner

    reachable = set(_queen_reach(board, 0, 0))

    # From corner (0,0), can only go right, down, and diag down-right
    # Right: (0,1)...(0,9) = 9
    # Down: (1,0)...(9,0) = 9
    # Diag: (1,1)...(9,9) = 9
    assert len(reachable) == 27
    # No negative coordinates
    for r, c in reachable:
        assert 0 <= r < 10 and 0 <= c < 10


def test_no_stay_in_place():
    """Rule 11: Moving to the same square is illegal (displacement >= 1)."""
    board = [[EMPTY] * 10 for _ in range(10)]
    board[5][5] = WHITE

    # _queen_reach should not include (5,5) itself
    reachable = _queen_reach(board, 5, 5)
    assert (5, 5) not in reachable

    # _is_queen_reachable should return False for same square
    assert not _is_queen_reachable(board, 5, 5, 5, 5)


def test_arrow_back_to_vacated_origin():
    """Rule 8: Arrow can fire back to the amazon's vacated origin square."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    board = state["board"]

    # White amazon at (6,0) = a4. Move it to (5,0). Then shoot arrow to (6,0).
    # Check if this is a valid move.
    move = [[6, 0], [5, 0], [6, 0]]
    assert game.is_valid_move(state, WHITE, move), (
        "Arrow should be able to fire back to the vacated origin square"
    )


def test_arrow_through_vacated_origin():
    """Rule 8: Arrow can pass through the vacated origin square."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    # White amazon at (6,0) = a4. Move it to (5,0) (one step up).
    # Shoot arrow from (5,0) through (6,0) to (7,0).
    # (6,0) is the vacated origin, (7,0) should be EMPTY at start.
    move = [[6, 0], [5, 0], [7, 0]]
    assert game.is_valid_move(state, WHITE, move), (
        "Arrow should be able to pass through the vacated origin square"
    )


def test_cannot_move_opponents_amazon():
    """Rule 6: Can only move friendly amazons."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    # Try to move a BLACK amazon as WHITE
    # Black amazon at (3,0). Move it somewhere.
    move = [[3, 0], [4, 0], [5, 0]]
    assert not game.is_valid_move(state, WHITE, move), (
        "Should not be able to move opponent's amazon"
    )


def test_invalid_move_structures():
    """Various invalid move formats should be rejected."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    # Wrong number of parts
    assert not game.is_valid_move(state, WHITE, [[6, 0], [5, 0]])
    assert not game.is_valid_move(state, WHITE, [[6, 0]])
    assert not game.is_valid_move(state, WHITE, [])

    # Out of bounds
    assert not game.is_valid_move(state, WHITE, [[6, 0], [-1, 0], [5, 0]])
    assert not game.is_valid_move(state, WHITE, [[6, 0], [5, 0], [10, 0]])

    # Non-queen-line move (L-shaped)
    assert not game.is_valid_move(state, WHITE, [[6, 0], [4, 1], [5, 0]])


def test_win_condition():
    """Rule 9: Player with no legal turns loses."""
    game = AmazonsLogic()

    # Create a board where WHITE is completely trapped
    board = [[BLOCKED] * 10 for _ in range(10)]
    # Put WHITE amazons in corners, surrounded by BLOCKED
    board[0][0] = WHITE
    board[0][1] = WHITE
    board[1][0] = WHITE
    board[1][1] = WHITE
    # All adjacent squares are BLOCKED, so no moves possible
    # Put BLACK amazons somewhere (they need space to move)
    board[5][5] = BLACK
    board[5][6] = BLACK
    board[6][5] = BLACK
    board[6][6] = BLACK
    # Make some space around BLACK
    board[4][4] = EMPTY
    board[4][5] = EMPTY
    board[4][6] = EMPTY
    board[4][7] = EMPTY
    board[5][4] = EMPTY
    board[5][7] = EMPTY
    board[6][4] = EMPTY
    board[6][7] = EMPTY
    board[7][4] = EMPTY
    board[7][5] = EMPTY
    board[7][6] = EMPTY
    board[7][7] = EMPTY

    state = {"board": board, "turn": WHITE, "move_num": 1}

    status = game.get_game_status(state)
    assert status["is_over"] is True, "Game should be over when player can't move"
    assert status["winner"] == BLACK, "BLACK should win when WHITE can't move"
    assert status["is_draw"] is False


def test_draw_impossible():
    """Rule 10: Draws are impossible (is_draw always False)."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    status = game.get_game_status(state)
    assert status["is_draw"] is False


def test_state_immutability():
    """apply_move must not mutate the original state."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    import json
    snapshot = json.dumps(state, sort_keys=True)
    moves = game.get_legal_moves(state, WHITE)
    new_state = game.apply_move(state, WHITE, moves[0])
    assert json.dumps(state, sort_keys=True) == snapshot


def test_arrow_permanently_blocks():
    """Rule 2: Arrow squares remain blocked for the rest of the game."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    moves = game.get_legal_moves(state, WHITE)
    new_state = game.apply_move(state, WHITE, moves[0])

    # The arrow position should be BLOCKED
    ar, ac = moves[0][2]
    assert new_state["board"][ar][ac] == BLOCKED


def test_move_num_increments():
    """move_num increments after BLACK's turn."""
    game = AmazonsLogic()
    state = game.create_initial_state()
    assert state["move_num"] == 1

    moves_w = game.get_legal_moves(state, WHITE)
    state2 = game.apply_move(state, WHITE, moves_w[0])
    assert state2["move_num"] == 1  # Still 1 after WHITE

    moves_b = game.get_legal_moves(state2, BLACK)
    state3 = game.apply_move(state2, BLACK, moves_b[0])
    assert state3["move_num"] == 2  # Increments after BLACK


# ═══════════════════════════════════════════════════════════════════════════
# MID-GAME VERIFICATION: play a sequence of moves and manually verify
# the legal moves for a specific piece at a known board state.
# ═══════════════════════════════════════════════════════════════════════════

def test_midgame_legal_moves_verification():
    """
    Play a specific sequence of moves, then manually compute and verify
    the legal moves for one amazon at the resulting board state.

    Setup: We'll create a small confined scenario by placing pieces
    manually to have a tractable verification.
    """
    game = AmazonsLogic()

    # Instead of playing from the start (too many possibilities),
    # create a custom mid-game board state that we can fully analyze.
    #
    # Board layout (10x10, row 0 = top, row 9 = bottom):
    #   - Most squares EMPTY
    #   - White amazon at (5,5) = center
    #   - Arrows forming a partial cage around it
    #   - Other amazons far away
    #
    board = [[EMPTY] * 10 for _ in range(10)]

    # White amazons
    board[5][5] = WHITE   # The piece we'll analyze
    board[0][0] = WHITE   # Far corner
    board[0][1] = WHITE   # Far corner
    board[0][2] = WHITE   # Far corner

    # Black amazons
    board[9][7] = BLACK
    board[9][8] = BLACK
    board[9][9] = BLACK
    board[8][9] = BLACK

    # Place arrows to create a partially confined space around (5,5)
    board[5][7] = BLOCKED   # blocks rightward at col 7
    board[3][5] = BLOCKED   # blocks upward at row 3
    board[7][3] = BLOCKED   # blocks diag down-left direction
    board[4][4] = BLOCKED   # blocks diag up-left at (4,4)

    state = {"board": board, "turn": WHITE, "move_num": 5}

    # Now manually compute queen_reach for (5,5):
    # Directions from (5,5):
    #   Up (-1,0):    (4,5) EMPTY, (3,5) BLOCKED => stop. Reachable: [(4,5)]
    #   Down (+1,0):  (6,5) EMPTY, (7,5) EMPTY, (8,5) EMPTY, (9,5) EMPTY => [(6,5),(7,5),(8,5),(9,5)]
    #   Left (0,-1):  (5,4) EMPTY, (5,3) EMPTY, (5,2) EMPTY, (5,1) EMPTY, (5,0) EMPTY => [(5,4),(5,3),(5,2),(5,1),(5,0)]
    #   Right (0,+1): (5,6) EMPTY, (5,7) BLOCKED => stop. Reachable: [(5,6)]
    #   Up-Left (-1,-1): (4,4) BLOCKED => stop. Reachable: []
    #   Up-Right (-1,+1): (4,6) EMPTY, (3,7) EMPTY, (2,8) EMPTY, (1,9) EMPTY => [(4,6),(3,7),(2,8),(1,9)]
    #   Down-Left (+1,-1): (6,4) EMPTY, (7,3) BLOCKED => stop. Reachable: [(6,4)]
    #   Down-Right (+1,+1): (6,6) EMPTY, (7,7) EMPTY, (8,8) EMPTY, (9,9) BLACK => stop. Reachable: [(6,6),(7,7),(8,8)]

    expected_reach = {
        (4, 5),                                   # up
        (6, 5), (7, 5), (8, 5), (9, 5),          # down
        (5, 4), (5, 3), (5, 2), (5, 1), (5, 0),  # left
        (5, 6),                                    # right
        # up-left: nothing (blocked by arrow at (4,4))
        (4, 6), (3, 7), (2, 8), (1, 9),          # up-right
        (6, 4),                                    # down-left
        (6, 6), (7, 7), (8, 8),                   # down-right
    }

    actual_reach = set(_queen_reach(board, 5, 5))
    assert actual_reach == expected_reach, (
        f"queen_reach mismatch for (5,5).\n"
        f"  Expected: {sorted(expected_reach)}\n"
        f"  Actual:   {sorted(actual_reach)}\n"
        f"  Missing:  {sorted(expected_reach - actual_reach)}\n"
        f"  Extra:    {sorted(actual_reach - expected_reach)}"
    )

    # Now verify full legal moves for the amazon at (5,5).
    # For each move destination, we need to:
    #   1. Temporarily move (5,5) -> destination
    #   2. Compute queen_reach from destination (with the amazon at destination, origin vacated)
    #   3. Each reachable square from destination is a valid arrow target
    #
    # We'll verify a few specific destinations in detail.

    # === Destination (5,6): move amazon right one ===
    # After moving: (5,5) = EMPTY, (5,6) = WHITE
    # Queen reach from (5,6):
    #   Up: (4,6) EMPTY, (3,6) EMPTY, (2,6) EMPTY, (1,6) EMPTY, (0,6) EMPTY => 5
    #   Down: (6,6) EMPTY, (7,6) EMPTY, (8,6) EMPTY, (9,6) EMPTY => 4
    #   Left: (5,5) EMPTY [vacated!], (5,4) EMPTY, (5,3) EMPTY, (5,2) EMPTY, (5,1) EMPTY, (5,0) EMPTY => 6
    #   Right: (5,7) BLOCKED => 0
    #   Up-Left: (4,5) EMPTY, (3,4) EMPTY, (2,3) EMPTY, (1,2) EMPTY, (0,1) WHITE => stop => 4
    #     Wait, (0,1) has WHITE. So: (4,5),(3,4),(2,3),(1,2) => 4
    #   Up-Right: (4,7) EMPTY, (3,8) EMPTY, (2,9) EMPTY => 3
    #   Down-Left: (6,5) EMPTY, (7,4) EMPTY, (8,3) EMPTY, (9,2) EMPTY => 4
    #   Down-Right: (6,7) EMPTY, (7,8) EMPTY, (8,9) BLACK => stop => 2
    # Total arrow targets from (5,6): 5+4+6+0+4+3+4+2 = 28

    # Let's verify this programmatically by temporarily moving and computing
    test_board = [row[:] for row in board]
    test_board[5][5] = EMPTY
    test_board[5][6] = WHITE
    reach_from_56 = set(_queen_reach(test_board, 5, 6))

    expected_from_56 = set()
    # Up from (5,6): (4,6),(3,6),(2,6),(1,6),(0,6)
    expected_from_56.update([(4,6),(3,6),(2,6),(1,6),(0,6)])
    # Down from (5,6): (6,6),(7,6),(8,6),(9,6)
    expected_from_56.update([(6,6),(7,6),(8,6),(9,6)])
    # Left from (5,6): (5,5),(5,4),(5,3),(5,2),(5,1),(5,0)
    expected_from_56.update([(5,5),(5,4),(5,3),(5,2),(5,1),(5,0)])
    # Right from (5,6): (5,7) BLOCKED => nothing
    # Up-Left from (5,6): (4,5),(3,4),(2,3),(1,2) -- (0,1) is WHITE
    expected_from_56.update([(4,5),(3,4),(2,3),(1,2)])
    # Up-Right from (5,6): (4,7),(3,8),(2,9)  -- (1,10) OOB
    expected_from_56.update([(4,7),(3,8),(2,9)])
    # Down-Left from (5,6): (6,5),(7,4),(8,3),(9,2)
    expected_from_56.update([(6,5),(7,4),(8,3),(9,2)])
    # Down-Right from (5,6): (6,7),(7,8) -- (8,9) is BLACK
    expected_from_56.update([(6,7),(7,8)])

    assert reach_from_56 == expected_from_56, (
        f"Arrow targets from (5,6) mismatch.\n"
        f"  Missing: {sorted(expected_from_56 - reach_from_56)}\n"
        f"  Extra:   {sorted(reach_from_56 - expected_from_56)}"
    )

    # Restore test board
    test_board[5][5] = WHITE
    test_board[5][6] = EMPTY

    # === Now verify the full legal move list from _get_legal_moves ===
    all_moves = game._get_legal_moves(state, WHITE)

    # Extract only moves involving the amazon at (5,5)
    moves_from_55 = [m for m in all_moves if m[0] == [5, 5]]

    # Manually build the expected set of moves from (5,5)
    expected_moves_55 = set()
    for dest in expected_reach:
        # Temporarily move amazon to dest, compute arrow targets
        tmp_board = [row[:] for row in board]
        tmp_board[5][5] = EMPTY
        tmp_board[dest[0]][dest[1]] = WHITE
        arrows = _queen_reach(tmp_board, dest[0], dest[1])
        for arrow in arrows:
            expected_moves_55.add(((5, 5), dest, arrow))

    actual_moves_55 = set()
    for m in moves_from_55:
        actual_moves_55.add((tuple(m[0]), tuple(m[1]), tuple(m[2])))

    assert actual_moves_55 == expected_moves_55, (
        f"Legal moves from (5,5) mismatch.\n"
        f"  Expected count: {len(expected_moves_55)}\n"
        f"  Actual count:   {len(actual_moves_55)}\n"
        f"  Missing: {sorted(expected_moves_55 - actual_moves_55)[:10]}\n"
        f"  Extra:   {sorted(actual_moves_55 - expected_moves_55)[:10]}"
    )

    print(f"  Amazon at (5,5) has {len(expected_reach)} move destinations")
    print(f"  Total legal moves from (5,5): {len(expected_moves_55)}")
    print(f"  All match the implementation.")


def test_midgame_play_sequence():
    """
    Play a specific sequence of real moves from the starting position,
    then verify the board state and legal moves at a specific point.
    """
    game = AmazonsLogic()
    state = game.create_initial_state()

    # Move 1: White amazon d1=(9,3) moves to d3=(7,3), shoots arrow to d5=(5,3)
    # Verify: (9,3) has WHITE, path to (7,3) clear, arrow path (7,3)->(5,3) clear
    move1 = [[9, 3], [7, 3], [5, 3]]
    assert game.is_valid_move(state, WHITE, move1), "Move 1 should be valid"
    state = game.apply_move(state, WHITE, move1)

    # Verify board after move 1
    assert state["board"][9][3] == EMPTY, "d1 should be empty after move"
    assert state["board"][7][3] == WHITE, "d3 should have white amazon"
    assert state["board"][5][3] == BLOCKED, "d5 should have arrow"
    assert state["turn"] == BLACK

    # Move 2: Black amazon d10=(0,3) moves to d8=(2,3), shoots arrow to d9=(1,3)
    move2 = [[0, 3], [2, 3], [1, 3]]
    assert game.is_valid_move(state, BLACK, move2), "Move 2 should be valid"
    state = game.apply_move(state, BLACK, move2)

    assert state["board"][0][3] == EMPTY
    assert state["board"][2][3] == BLACK
    assert state["board"][1][3] == BLOCKED
    assert state["turn"] == WHITE

    # Move 3: White amazon g1=(9,6) moves to g3=(7,6), shoots arrow to g5=(5,6)
    move3 = [[9, 6], [7, 6], [5, 6]]
    assert game.is_valid_move(state, WHITE, move3), "Move 3 should be valid"
    state = game.apply_move(state, WHITE, move3)

    assert state["board"][9][6] == EMPTY
    assert state["board"][7][6] == WHITE
    assert state["board"][5][6] == BLOCKED
    assert state["turn"] == BLACK

    # Now verify the board state thoroughly
    board = state["board"]

    # White amazons should be at: (6,0), (7,3), (7,6), (6,9)
    white_positions = []
    for r in range(10):
        for c in range(10):
            if board[r][c] == WHITE:
                white_positions.append((r, c))
    assert sorted(white_positions) == [(6, 0), (6, 9), (7, 3), (7, 6)], (
        f"White positions: {sorted(white_positions)}"
    )

    # Black amazons should be at: (3,0), (2,3), (0,6), (3,9)
    black_positions = []
    for r in range(10):
        for c in range(10):
            if board[r][c] == BLACK:
                black_positions.append((r, c))
    assert sorted(black_positions) == [(0, 6), (2, 3), (3, 0), (3, 9)], (
        f"Black positions: {sorted(black_positions)}"
    )

    # Arrows should be at: (5,3), (1,3), (5,6)
    arrow_positions = []
    for r in range(10):
        for c in range(10):
            if board[r][c] == BLOCKED:
                arrow_positions.append((r, c))
    assert sorted(arrow_positions) == [(1, 3), (5, 3), (5, 6)], (
        f"Arrow positions: {sorted(arrow_positions)}"
    )

    # Now verify legal moves for White's amazon at (7,3)
    # Queen reach from (7,3):
    #   Up (-1,0): (6,3) EMPTY, (5,3) BLOCKED => [(6,3)]
    #   Down (+1,0): (8,3) EMPTY, (9,3) EMPTY => [(8,3),(9,3)]
    #   Left (0,-1): (7,2) EMPTY, (7,1) EMPTY, (7,0) EMPTY => [(7,2),(7,1),(7,0)]
    #   Right (0,+1): (7,4) EMPTY, (7,5) EMPTY, (7,6) WHITE => stop => [(7,4),(7,5)]
    #   Up-Left (-1,-1): (6,2) EMPTY, (5,1) EMPTY, (4,0) EMPTY => [(6,2),(5,1),(4,0)]
    #     (3,0) has BLACK => stop. Wait, (4,0) EMPTY? Let me check: initially (3,0) is BLACK amazon.
    #     Wait no: black amazon at (3,0). So from (7,3) diag up-left: (6,2),(5,1),(4,0),(3,-1) OOB
    #     Actually (4,0): row=4, col=0, that should be EMPTY. Then next would be (3,-1) which is OOB.
    #     So: [(6,2),(5,1),(4,0)]
    #   Up-Right (-1,+1): (6,4) EMPTY, (5,5) EMPTY, (4,6) EMPTY, (3,7) EMPTY, (2,8) EMPTY, (1,9) EMPTY =>
    #     [(6,4),(5,5),(4,6),(3,7),(2,8),(1,9)]
    #     Wait, check (0,10) - OOB. So 6 squares.
    #   Down-Left (+1,-1): (8,2) EMPTY, (9,1) EMPTY => [(8,2),(9,1)]
    #     (10,0) OOB
    #   Down-Right (+1,+1): (8,4) EMPTY, (9,5) EMPTY => [(8,4),(9,5)]
    #     (10,6) OOB

    expected_reach_73 = {
        (6, 3),                                     # up
        (8, 3), (9, 3),                             # down
        (7, 2), (7, 1), (7, 0),                    # left
        (7, 4), (7, 5),                             # right
        (6, 2), (5, 1), (4, 0),                    # up-left
        (6, 4), (5, 5), (4, 6), (3, 7), (2, 8), (1, 9),  # up-right
        (8, 2), (9, 1),                             # down-left
        (8, 4), (9, 5),                             # down-right
    }

    actual_reach_73 = set(_queen_reach(board, 7, 3))
    assert actual_reach_73 == expected_reach_73, (
        f"queen_reach mismatch for (7,3).\n"
        f"  Missing: {sorted(expected_reach_73 - actual_reach_73)}\n"
        f"  Extra:   {sorted(actual_reach_73 - expected_reach_73)}"
    )

    print(f"  After 3 moves, amazon at (7,3) has {len(expected_reach_73)} move destinations")

    # Verify is_valid_move agrees with _get_legal_moves for the amazon at (7,3)
    all_legal = game._get_legal_moves(state, BLACK)  # Wait, it's BLACK's turn
    # Actually it's BLACK's turn now. Let me verify for BLACK instead.
    assert state["turn"] == BLACK

    # Verify for BLACK amazon at (2,3):
    # Queen reach from (2,3):
    #   Up (-1,0): (1,3) BLOCKED => []
    #   Down (+1,0): (3,3) EMPTY, (4,3) EMPTY, (5,3) BLOCKED => [(3,3),(4,3)]
    #   Left (0,-1): (2,2) EMPTY, (2,1) EMPTY, (2,0) EMPTY => [(2,2),(2,1),(2,0)]
    #   Right (0,+1): (2,4) EMPTY, (2,5) EMPTY, (2,6) EMPTY, (2,7) EMPTY, (2,8) EMPTY, (2,9) EMPTY => 6
    #   Up-Left (-1,-1): (1,2) EMPTY, (0,1) EMPTY => [(1,2),(0,1)]
    #   Up-Right (-1,+1): (1,4) EMPTY, (0,5) EMPTY => [(1,4),(0,5)]
    #   Down-Left (+1,-1): (3,2) EMPTY, (4,1) EMPTY, (5,0) EMPTY, (6,-1) OOB => [(3,2),(4,1),(5,0)]
    #   Down-Right (+1,+1): (3,4) EMPTY, (4,5) EMPTY, (5,6) BLOCKED => [(3,4),(4,5)]

    expected_reach_23 = {
        # up: blocked
        (3, 3), (4, 3),                             # down
        (2, 2), (2, 1), (2, 0),                    # left
        (2, 4), (2, 5), (2, 6), (2, 7), (2, 8), (2, 9),  # right
        (1, 2), (0, 1),                             # up-left
        (1, 4), (0, 5),                             # up-right
        (3, 2), (4, 1), (5, 0),                    # down-left
        (3, 4), (4, 5),                             # down-right
    }

    actual_reach_23 = set(_queen_reach(board, 2, 3))
    assert actual_reach_23 == expected_reach_23, (
        f"queen_reach mismatch for (2,3).\n"
        f"  Missing: {sorted(expected_reach_23 - actual_reach_23)}\n"
        f"  Extra:   {sorted(actual_reach_23 - expected_reach_23)}"
    )

    # Now verify full legal moves for the BLACK amazon at (2,3)
    all_black_moves = game._get_legal_moves(state, BLACK)
    moves_from_23 = [m for m in all_black_moves if m[0] == [2, 3]]

    expected_moves_23 = set()
    for dest in expected_reach_23:
        tmp_board = [row[:] for row in board]
        tmp_board[2][3] = EMPTY
        tmp_board[dest[0]][dest[1]] = BLACK
        arrows = _queen_reach(tmp_board, dest[0], dest[1])
        for arrow in arrows:
            expected_moves_23.add(((2, 3), dest, arrow))

    actual_moves_23 = set()
    for m in moves_from_23:
        actual_moves_23.add((tuple(m[0]), tuple(m[1]), tuple(m[2])))

    assert actual_moves_23 == expected_moves_23, (
        f"Legal moves from (2,3) mismatch.\n"
        f"  Expected count: {len(expected_moves_23)}\n"
        f"  Actual count:   {len(actual_moves_23)}\n"
        f"  Missing: {sorted(expected_moves_23 - actual_moves_23)[:10]}\n"
        f"  Extra:   {sorted(actual_moves_23 - expected_moves_23)[:10]}"
    )

    print(f"  Black amazon at (2,3) has {len(expected_reach_23)} destinations, "
          f"{len(expected_moves_23)} total legal moves. All verified.")


def test_has_legal_turn_consistency():
    """Verify _has_legal_turn is consistent with _get_legal_moves."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    # At start, both players should have legal turns
    assert _has_legal_turn(state["board"], WHITE)
    assert _has_legal_turn(state["board"], BLACK)

    # Both should have legal moves
    assert len(game._get_legal_moves(state, WHITE)) > 0
    assert len(game._get_legal_moves(state, BLACK)) > 0


def test_is_valid_move_vs_get_legal_moves():
    """Verify is_valid_move agrees with get_legal_moves for several states."""
    game = AmazonsLogic()
    state = game.create_initial_state()

    moves = game.get_legal_moves(state, WHITE)

    # All legal moves should pass is_valid_move
    for move in moves[:50]:  # sample
        assert game.is_valid_move(state, WHITE, move), (
            f"Legal move {move} failed is_valid_move"
        )

    # A clearly illegal move should fail both
    illegal = [[0, 0], [5, 5], [9, 9]]
    assert illegal not in moves
    assert not game.is_valid_move(state, WHITE, illegal)


def test_four_square_states():
    """Rule 2: Every square is EMPTY, WHITE_AMAZON, BLACK_AMAZON, or ARROW."""
    assert EMPTY == 0
    assert WHITE == 1
    assert BLACK == 2
    assert BLOCKED == 3

    game = AmazonsLogic()
    state = game.create_initial_state()
    for r in range(10):
        for c in range(10):
            assert state["board"][r][c] in (EMPTY, WHITE, BLACK, BLOCKED)


if __name__ == "__main__":
    tests = [
        test_board_size,
        test_initial_positions,
        test_initial_turn_order,
        test_turn_alternation,
        test_move_structure,
        test_queen_movement_directions,
        test_blocking_by_amazons,
        test_blocking_by_arrows,
        test_blocking_by_board_edges,
        test_no_stay_in_place,
        test_arrow_back_to_vacated_origin,
        test_arrow_through_vacated_origin,
        test_cannot_move_opponents_amazon,
        test_invalid_move_structures,
        test_win_condition,
        test_draw_impossible,
        test_state_immutability,
        test_arrow_permanently_blocks,
        test_move_num_increments,
        test_midgame_legal_moves_verification,
        test_midgame_play_sequence,
        test_has_legal_turn_consistency,
        test_is_valid_move_vs_get_legal_moves,
        test_four_square_states,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
