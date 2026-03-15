"""
Amazons -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for the Game of the Amazons,
a 10x10 deterministic abstract strategy game for two players.

A move is represented as three [row, col] pairs::

    [[from_r, from_c], [to_r, to_c], [arrow_r, arrow_c]]
"""

import copy
import math
from collections import deque

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

BOARD_N = 10
EMPTY, WHITE, BLACK, BLOCKED = 0, 1, 2, 3

# ── Private constants ────────────────────────────────────────────────────────

_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1),
         (-1, -1), (-1, 1), (1, -1), (1, 1)]

_W_START = [(6, 0), (9, 3), (9, 6), (6, 9)]   # a4 d1 g1 j4
_B_START = [(3, 0), (0, 3), (0, 6), (3, 9)]   # a7 d10 g10 j7


# ── Pure helper functions ────────────────────────────────────────────────────

def _queen_reach(board, r0, c0):
    """All empty squares reachable by queen-move from (r0, c0).

    Returns a list of (row, col) tuples.
    """
    result = []
    for dr, dc in _DIRS:
        r, c = r0 + dr, c0 + dc
        while 0 <= r < BOARD_N and 0 <= c < BOARD_N and board[r][c] == EMPTY:
            result.append((r, c))
            r += dr
            c += dc
    return result


def _is_queen_reachable(board, r0, c0, r1, c1):
    """True if (r1, c1) is reachable from (r0, c0) by a single queen slide.

    All intermediate squares and the target itself must be EMPTY.
    """
    if r0 == r1 and c0 == c1:
        return False
    dr = r1 - r0
    dc = c1 - c0
    # Must lie on a horizontal, vertical, or diagonal line
    if dr != 0 and dc != 0 and abs(dr) != abs(dc):
        return False
    sr = (1 if dr > 0 else -1) if dr != 0 else 0
    sc = (1 if dc > 0 else -1) if dc != 0 else 0
    r, c = r0 + sr, c0 + sc
    while (r, c) != (r1, c1):
        if board[r][c] != EMPTY:
            return False
        r += sr
        c += sc
    return board[r1][c1] == EMPTY


def _amazon_destinations(board, r, c):
    """Move destinations from (r, c) that also allow an arrow shot afterward.

    Returns a list of (row, col) tuples.  Temporarily mutates *board*
    during computation but restores it before returning.
    """
    player = board[r][c]
    valid = []
    for mr, mc in _queen_reach(board, r, c):
        board[r][c] = EMPTY
        board[mr][mc] = player
        if _queen_reach(board, mr, mc):
            valid.append((mr, mc))
        board[mr][mc] = EMPTY
        board[r][c] = player
    return valid


def _has_legal_turn(board, player):
    """True if *player* can make at least one complete turn (move + arrow).

    Temporarily mutates *board* during computation but restores it
    before returning.
    """
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if board[r][c] != player:
                continue
            for mr, mc in _queen_reach(board, r, c):
                board[r][c] = EMPTY
                board[mr][mc] = player
                can_shoot = len(_queen_reach(board, mr, mc)) > 0
                board[mr][mc] = EMPTY
                board[r][c] = player
                if can_shoot:
                    return True
    return False


# ── Game class ───────────────────────────────────────────────────────────────

class AmazonsLogic(AbstractBoardGame):
    """Amazons game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":    [[int, ...], ...],   # 10x10, values: EMPTY/WHITE/BLACK/BLOCKED
            "turn":     int,                 # WHITE (1) or BLACK (2)
            "move_num": int                  # full-move counter (increments after BLACK)
        }

    A move is a list of three ``[row, col]`` pairs::

        [[from_r, from_c], [to_r, to_c], [arrow_r, arrow_c]]
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Amazons"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [[EMPTY] * BOARD_N for _ in range(BOARD_N)]
        for r, c in _W_START:
            board[r][c] = WHITE
        for r, c in _B_START:
            board[r][c] = BLACK
        return {"board": board, "turn": WHITE, "move_num": 1}

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        board = state["board"]
        moves = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                if board[r][c] != player:
                    continue
                for mr, mc in _queen_reach(board, r, c):
                    board[r][c] = EMPTY
                    board[mr][mc] = player
                    for ar, ac in _queen_reach(board, mr, mc):
                        moves.append([[r, c], [mr, mc], [ar, ac]])
                    board[mr][mc] = EMPTY
                    board[r][c] = player
        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)
        (fr, fc), (tr, tc), (ar, ac) = move
        new["board"][fr][fc] = EMPTY
        new["board"][tr][tc] = player
        new["board"][ar][ac] = BLOCKED
        new["turn"] = BLACK if player == WHITE else WHITE
        if player == BLACK:
            new["move_num"] = state["move_num"] + 1
        return new

    def _get_game_status(self, state):
        board = state["board"]
        turn = state["turn"]
        if _has_legal_turn(board, turn):
            return {"is_over": False, "winner": None, "is_draw": False}
        # Current player cannot move — opponent wins
        winner = BLACK if turn == WHITE else WHITE
        return {"is_over": True, "winner": winner, "is_draw": False}

    # ── Evaluation hook ────────────────────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate from *player*'s perspective using king-distance territory."""
        board = state["board"]
        opp = BLACK if player == WHITE else WHITE

        # Multi-source BFS for king-distance from each side's amazons
        INF = 200
        dist_p = [[INF] * BOARD_N for _ in range(BOARD_N)]
        dist_o = [[INF] * BOARD_N for _ in range(BOARD_N)]
        q_p = deque()
        q_o = deque()

        for r in range(BOARD_N):
            for c in range(BOARD_N):
                v = board[r][c]
                if v == player:
                    dist_p[r][c] = 0
                    q_p.append((r, c))
                elif v == opp:
                    dist_o[r][c] = 0
                    q_o.append((r, c))

        # BFS for player
        while q_p:
            r, c = q_p.popleft()
            d = dist_p[r][c] + 1
            for dr, dc in _DIRS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < BOARD_N and 0 <= nc < BOARD_N:
                    if board[nr][nc] == EMPTY and dist_p[nr][nc] > d:
                        dist_p[nr][nc] = d
                        q_p.append((nr, nc))

        # BFS for opponent
        while q_o:
            r, c = q_o.popleft()
            d = dist_o[r][c] + 1
            for dr, dc in _DIRS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < BOARD_N and 0 <= nc < BOARD_N:
                    if board[nr][nc] == EMPTY and dist_o[nr][nc] > d:
                        dist_o[nr][nc] = d
                        q_o.append((nr, nc))

        # Count territories
        own_terr = 0
        opp_terr = 0
        own_reach = 0
        opp_reach = 0
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                if board[r][c] != EMPTY:
                    continue
                dp = dist_p[r][c]
                do = dist_o[r][c]
                if dp < do:
                    own_terr += 1
                elif do < dp:
                    opp_terr += 1
                if dp < INF:
                    own_reach += 1
                if do < INF:
                    opp_reach += 1

        # Near-terminal
        if own_reach == 0:
            return 0.0
        if opp_reach == 0:
            return 1.0

        # Territory differential (dominant)
        score = (own_terr - opp_terr) * 100

        # Reachable squares (secondary mobility proxy)
        score += (own_reach - opp_reach) * 10

        x = max(-20.0, min(20.0, score / 500.0))
        return 1.0 / (1.0 + math.exp(-x))

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves.

        Checks structure, bounds, piece ownership, queen-reachability of
        the destination, and queen-reachability of the arrow target from
        the destination.
        """
        if not isinstance(move, list) or len(move) != 3:
            return False
        try:
            (fr, fc), (tr, tc), (ar, ac) = move
        except (TypeError, ValueError):
            return False
        for r, c in ((fr, fc), (tr, tc), (ar, ac)):
            if not (isinstance(r, int) and isinstance(c, int)):
                return False
            if not (0 <= r < BOARD_N and 0 <= c < BOARD_N):
                return False

        board = state["board"]
        if board[fr][fc] != player:
            return False
        if not _is_queen_reachable(board, fr, fc, tr, tc):
            return False

        # Temporarily move the amazon to test arrow reachability
        board[fr][fc] = EMPTY
        board[tr][tc] = player
        try:
            reachable = _is_queen_reachable(board, tr, tc, ar, ac)
        finally:
            board[tr][tc] = EMPTY
            board[fr][fc] = player
        return reachable

    # ── Extra helpers for client / display use ───────────────────────────

    @staticmethod
    def queen_reach(board, r0, c0):
        """All empty squares reachable by queen-move from (r0, c0).

        Returns a list of (row, col) tuples.  Useful for the client to
        compute arrow targets during the arrow phase.
        """
        return _queen_reach(board, r0, c0)

    @staticmethod
    def amazon_destinations(board, r, c):
        """Move destinations from (r, c) that allow an arrow shot afterward.

        Returns a list of (row, col) tuples.  Useful for the client to
        show valid move targets when an amazon is selected.

        Note: temporarily mutates *board* during computation but restores
        it before returning.
        """
        return _amazon_destinations(board, r, c)
