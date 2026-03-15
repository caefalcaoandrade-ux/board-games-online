"""
Bashni (Column Draughts) -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Bashni, a 10x10 column
draughts game for two players.

Board representation
--------------------
The board is a 10x10 nested list.  Each cell is either ``None`` (empty)
or a list of ``[color, rank]`` pairs representing a column (stack of
pieces).  Index 0 is the bottom piece, index -1 is the top (commander).

Color: ``"W"`` or ``"B"``.  Rank: ``"man"`` or ``"king"``.

Move representation
-------------------
Simple move (non-capture)::

    {"from": [r, c], "to": [r, c]}

Capture sequence (one or more jumps)::

    {"from": [r, c], "jumps": [[land_r, land_c], ...]}

Player mapping: ``"W"`` -> int 1, ``"B"`` -> int 2 for the base class
interface.
"""

import copy
import math

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

BOARD_N = 10
W, B = "W", "B"
MAN, KING = "man", "king"
DIRS = [[-1, -1], [-1, 1], [1, -1], [1, 1]]

# Player int <-> color string mapping
PLAYER_TO_COLOR = {1: W, 2: B}
COLOR_TO_PLAYER = {W: 1, B: 2}

# ── Pure helper functions ────────────────────────────────────────────────────


def in_bounds(r, c):
    """True if (r, c) is within the board."""
    return 0 <= r < BOARD_N and 0 <= c < BOARD_N


def is_dark(r, c):
    """True if (r, c) is a dark (playable) square."""
    return (r + c) % 2 == 0


def opponent_color(color):
    """Return the opposing color string."""
    return B if color == W else W


def promo_row(color):
    """Return the promotion row for the given color."""
    return BOARD_N - 1 if color == W else 0


def make_board():
    """Create and return the initial board."""
    board = [[None] * BOARD_N for _ in range(BOARD_N)]
    setup_rows = (BOARD_N - 2) // 2  # 4 for N=10
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if not is_dark(r, c):
                continue
            if r < setup_rows:
                board[r][c] = [[W, MAN]]
            elif r >= BOARD_N - setup_rows:
                board[r][c] = [[B, MAN]]
    return board


def board_key(board, turn):
    """Produce a hashable key for position-repetition tracking.

    Returns a string representation of the board + turn.
    """
    parts = []
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col = board[r][c]
            if col:
                pieces = "|".join(f"{p[0]}{p[1]}" for p in col)
                parts.append(f"{r},{c}:{pieces}")
    return ";".join(parts) + "/" + turn


# ── Move / capture logic ────────────────────────────────────────────────────


def get_simple_moves(board, r, c, color):
    """Return list of [nr, nc] destinations for a non-capture move."""
    col = board[r][c]
    if not col or col[-1][0] != color:
        return []
    is_king = col[-1][1] == KING
    moves = []
    if is_king:
        for d in DIRS:
            dr, dc = d[0], d[1]
            dist = 1
            while True:
                nr, nc = r + dr * dist, c + dc * dist
                if not in_bounds(nr, nc):
                    break
                if board[nr][nc] is not None:
                    break
                moves.append([nr, nc])
                dist += 1
    else:
        fwd = 1 if color == W else -1
        for dc in (-1, 1):
            nr, nc = r + fwd, c + dc
            if in_bounds(nr, nc) and board[nr][nc] is None:
                moves.append([nr, nc])
    return moves


def _raw_jumps(board, r, c, color, jumped_set=None):
    """Return raw jump data from (r, c).

    Each result is [land_r, land_c, target_r, target_c, dir_r, dir_c].
    jumped_set = set of (r, c) coordinates already jumped in this sequence.
    """
    col = board[r][c]
    if not col or col[-1][0] != color:
        return []
    is_king = col[-1][1] == KING
    results = []
    for d in DIRS:
        dr, dc = d[0], d[1]
        if is_king:
            dist = 1
            tgt = None
            while True:
                tr, tc = r + dr * dist, c + dc * dist
                if not in_bounds(tr, tc):
                    break
                cell = board[tr][tc]
                if cell is not None:
                    if cell[-1][0] != color:
                        tgt = [tr, tc]
                    break
                dist += 1
            if not tgt:
                continue
            tr, tc = tgt[0], tgt[1]
            # §8.4: cannot jump a coordinate that was already jumped
            if jumped_set and (tr, tc) in jumped_set:
                continue
            ld = 1
            while True:
                lr, lc = tr + dr * ld, tc + dc * ld
                if not in_bounds(lr, lc):
                    break
                if board[lr][lc] is not None:
                    break
                results.append([lr, lc, tr, tc, dr, dc])
                ld += 1
        else:
            tr, tc = r + dr, c + dc
            lr, lc = r + 2 * dr, c + 2 * dc
            # §8.4: cannot jump a coordinate that was already jumped
            if jumped_set and (tr, tc) in jumped_set:
                continue
            if (in_bounds(tr, tc) and in_bounds(lr, lc)
                    and board[tr][tc] is not None
                    and board[tr][tc][-1][0] != color
                    and board[lr][lc] is None):
                results.append([lr, lc, tr, tc, dr, dc])
    return results


def _has_raw_jump(board, r, c, color, jumped_set=None):
    """True if there is at least one raw jump from (r, c)."""
    col = board[r][c]
    if not col or col[-1][0] != color:
        return False
    is_king = col[-1][1] == KING
    for d in DIRS:
        dr, dc = d[0], d[1]
        if is_king:
            dist = 1
            tgt = None
            while True:
                tr, tc = r + dr * dist, c + dc * dist
                if not in_bounds(tr, tc):
                    break
                cell = board[tr][tc]
                if cell is not None:
                    if cell[-1][0] != color:
                        tgt = [tr, tc]
                    break
                dist += 1
            if not tgt:
                continue
            tr, tc = tgt[0], tgt[1]
            if jumped_set and (tr, tc) in jumped_set:
                continue
            lr, lc = tr + dr, tc + dc
            if in_bounds(lr, lc) and board[lr][lc] is None:
                return True
        else:
            tr, tc = r + dr, c + dc
            lr, lc = r + 2 * dr, c + 2 * dc
            if jumped_set and (tr, tc) in jumped_set:
                continue
            if (in_bounds(tr, tc) and in_bounds(lr, lc)
                    and board[tr][tc] is not None
                    and board[tr][tc][-1][0] != color
                    and board[lr][lc] is None):
                return True
    return False


def _exec_jump_on_board(board, fr, fc, lr, lc, tr, tc, color):
    """Execute a single jump on the board IN PLACE.

    The capturing column at (fr, fc) jumps over the target at (tr, tc)
    and lands at (lr, lc).  The top piece of the target column is
    captured (inserted at bottom of the captor column).
    """
    cap_col = board[fr][fc]
    tgt_col = board[tr][tc]
    captured = tgt_col.pop()
    cap_col.insert(0, captured)
    board[lr][lc] = cap_col
    board[fr][fc] = None
    if not tgt_col:
        board[tr][tc] = None
    if lr == promo_row(color) and cap_col[-1][1] == MAN:
        cap_col[-1] = [cap_col[-1][0], KING]


def _exec_move_on_board(board, fr, fc, tr, tc, color):
    """Execute a simple move on the board IN PLACE.

    Returns True if the moved piece was a man (used for quiet-move counting).
    """
    col = board[fr][fc]
    was_man = col[-1][1] == MAN
    board[tr][tc] = col
    board[fr][fc] = None
    if tr == promo_row(color) and col[-1][1] == MAN:
        col[-1] = [col[-1][0], KING]
    return was_man


def _sim_jump(board, fr, fc, lr, lc, tr, tc, color):
    """Return a new board with a single jump applied (does not mutate original)."""
    b = copy.deepcopy(board)
    _exec_jump_on_board(b, fr, fc, lr, lc, tr, tc, color)
    return b


def get_jumps(board, r, c, color, jumped_set=None):
    """Return filtered jump list from (r, c).

    For kings, if a landing square allows further capture, prefer it over
    those that don't (per the same captured-piece / direction group).
    This implements §8.5 (King Landing Constraint).

    Each result is [land_r, land_c, target_r, target_c, dir_r, dir_c].
    jumped_set = set of (r, c) coordinates already jumped in this sequence.
    """
    raw = _raw_jumps(board, r, c, color, jumped_set)
    if not raw:
        return []
    col = board[r][c]
    is_king = col[-1][1] == KING
    if not is_king:
        return raw

    # Group by (target, direction)
    groups = {}
    for item in raw:
        key = (item[2], item[3], item[4], item[5])
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    filtered = []
    for _key, items in groups.items():
        continuing = []
        non_continuing = []
        for item in items:
            lr, lc, tr, tc, dr, dc = item
            sim = _sim_jump(board, r, c, lr, lc, tr, tc, color)
            new_jumped = (jumped_set or set()) | {(tr, tc)}
            if _has_raw_jump(sim, lr, lc, color, new_jumped):
                continuing.append(item)
            else:
                non_continuing.append(item)
        filtered.extend(continuing if continuing else non_continuing)
    return filtered


def any_capture(board, color):
    """True if any piece of the given color can capture."""
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if _has_raw_jump(board, r, c, color):
                return True
    return False


def has_legal_move(board, color):
    """True if the given color has at least one legal move or capture."""
    cap = any_capture(board, color)
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col = board[r][c]
            if not col or col[-1][0] != color:
                continue
            if cap:
                if get_jumps(board, r, c, color):
                    return True
            else:
                if get_simple_moves(board, r, c, color):
                    return True
    return False


# ── Full move enumeration ────────────────────────────────────────────────────


def _enumerate_capture_sequences(board, r, c, color, jumped_set=None):
    """Recursively enumerate all complete capture sequences from (r, c).

    Returns a list of sequences, where each sequence is a list of
    [land_r, land_c] landing squares.
    jumped_set = set of (r, c) coordinates already jumped in this sequence.
    """
    if jumped_set is None:
        jumped_set = set()
    jumps = get_jumps(board, r, c, color, jumped_set)
    if not jumps:
        return []

    sequences = []
    for item in jumps:
        lr, lc, tr, tc, dr, dc = item
        new_board = _sim_jump(board, r, c, lr, lc, tr, tc, color)
        new_jumped = jumped_set | {(tr, tc)}
        further = _enumerate_capture_sequences(
            new_board, lr, lc, color, jumped_set=new_jumped
        )
        if further:
            for seq in further:
                sequences.append([[lr, lc]] + seq)
        else:
            sequences.append([[lr, lc]])
    return sequences


def _get_all_legal_moves(board, color):
    """Return all legal moves for the given color.

    Returns a list of move dicts. If captures are available, only
    capture moves are returned (mandatory capture rule).
    """
    cap = any_capture(board, color)
    moves = []

    if cap:
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                col = board[r][c]
                if not col or col[-1][0] != color:
                    continue
                seqs = _enumerate_capture_sequences(board, r, c, color)
                for seq in seqs:
                    moves.append({"from": [r, c], "jumps": seq})
    else:
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                col = board[r][c]
                if not col or col[-1][0] != color:
                    continue
                for dest in get_simple_moves(board, r, c, color):
                    moves.append({"from": [r, c], "to": dest})
    return moves


# ── Applying a full move to produce new state ────────────────────────────────


def _apply_full_move(board, color, move):
    """Apply a complete move dict to a deepcopy of board and return the new board.

    Also returns whether the move was quiet (for the 15-move rule counter).
    A move is quiet if it's a non-capture and the piece was already a king.
    """
    new_board = copy.deepcopy(board)
    fr, fc = move["from"][0], move["from"][1]

    if "jumps" in move:
        # Capture sequence
        cur_r, cur_c = fr, fc
        jumped_coords = set()
        for landing in move["jumps"]:
            lr, lc = landing[0], landing[1]
            # Find the target and direction for this jump
            jumps = get_jumps(new_board, cur_r, cur_c, color, jumped_coords)
            target_found = False
            for item in jumps:
                if item[0] == lr and item[1] == lc:
                    jumped_coords.add((item[2], item[3]))
                    _exec_jump_on_board(
                        new_board, cur_r, cur_c, lr, lc,
                        item[2], item[3], color
                    )
                    target_found = True
                    break
            if not target_found:
                raise ValueError(
                    f"Invalid jump landing [{lr}, {lc}] from [{cur_r}, {cur_c}]"
                )
            cur_r, cur_c = lr, lc
        return new_board, False  # captures reset quiet counter
    else:
        # Simple move
        tr, tc = move["to"][0], move["to"][1]
        was_man = _exec_move_on_board(new_board, fr, fc, tr, tc, color)
        is_quiet = not was_man
        return new_board, is_quiet


# ── Game class ───────────────────────────────────────────────────────────────


class BashniLogic(AbstractBoardGame):
    """Bashni game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":         [[cell, ...], ...],  # 10x10, cell = None or [[color, rank], ...]
            "turn":          str,                  # "W" or "B"
            "quiet_half":    int,                  # half-moves without man move or capture
            "pos_history":   {"key": count, ...},  # position repetition tracker
            "last_from":     [r, c] or None,
            "last_to":       [r, c] or None
        }
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Bashni"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = make_board()
        state = {
            "board": board,
            "turn": W,
            "quiet_half": 0,
            "pos_history": {},
            "last_from": None,
            "last_to": None,
        }
        key = board_key(board, W)
        state["pos_history"][key] = 1
        return state

    def _get_current_player(self, state):
        return COLOR_TO_PLAYER[state["turn"]]

    def _get_legal_moves(self, state, player):
        color = PLAYER_TO_COLOR[player]
        return _get_all_legal_moves(state["board"], color)

    def _apply_move(self, state, player, move):
        color = PLAYER_TO_COLOR[player]
        new_board, is_quiet = _apply_full_move(state["board"], color, move)
        next_turn = opponent_color(color)

        # Compute quiet half-move counter
        if is_quiet:
            new_quiet = state["quiet_half"] + 1
        else:
            new_quiet = 0

        # Copy and update position history
        new_history = dict(state["pos_history"])
        key = board_key(new_board, next_turn)
        new_history[key] = new_history.get(key, 0) + 1

        # Determine last_from / last_to
        fr, fc = move["from"][0], move["from"][1]
        if "jumps" in move:
            last_landing = move["jumps"][-1]
            last_to = [last_landing[0], last_landing[1]]
        else:
            last_to = [move["to"][0], move["to"][1]]

        return {
            "board": new_board,
            "turn": next_turn,
            "quiet_half": new_quiet,
            "pos_history": new_history,
            "last_from": [fr, fc],
            "last_to": last_to,
        }

    def _get_game_status(self, state):
        board = state["board"]
        turn = state["turn"]

        # Threefold repetition
        key = board_key(board, turn)
        if state["pos_history"].get(key, 0) >= 3:
            return {"is_over": True, "winner": None, "is_draw": True}

        # 15-move rule (30 half-moves)
        if state["quiet_half"] >= 30:
            return {"is_over": True, "winner": None, "is_draw": True}

        # No legal moves = loss
        if not has_legal_move(board, turn):
            winner_color = opponent_color(turn)
            return {
                "is_over": True,
                "winner": COLOR_TO_PLAYER[winner_color],
                "is_draw": False,
            }

        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Evaluation hook ─────────────────────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate from *player*'s perspective using stack features."""
        board = state["board"]
        color = PLAYER_TO_COLOR[player]
        opp_c = opponent_color(color)

        own_stacks = 0
        opp_stacks = 0
        own_kings = 0
        opp_kings = 0
        own_prisoners = 0    # own pieces buried under opponent stacks
        opp_prisoners = 0    # opponent pieces buried under own stacks
        own_comp = 0
        opp_comp = 0
        own_center = 0
        opp_center = 0
        own_adv = 0.0
        opp_adv = 0.0
        lib_penalty = 0

        for r in range(BOARD_N):
            for c in range(BOARD_N):
                col = board[r][c]
                if col is None:
                    continue
                top = col[-1]
                tc = top[0]
                is_center = 3 <= r <= 6 and 3 <= c <= 6

                if tc == color:
                    own_stacks += 1
                    if top[1] == KING:
                        own_kings += 1
                    if is_center:
                        own_center += 1
                    # Advancement toward promotion row
                    if color == W:
                        own_adv += 20 + 60.0 * r / 9.0
                    else:
                        own_adv += 20 + 60.0 * (9 - r) / 9.0
                    # Composition depth: consecutive friendly from top
                    depth = 0
                    for i in range(len(col) - 1, -1, -1):
                        if col[i][0] == color:
                            depth += 1
                        else:
                            break
                    own_comp += depth
                    # Prisoners: opponent pieces in own stack
                    for p in col:
                        if p[0] == opp_c:
                            opp_prisoners += 1
                    # Liberation threat: only 1 friendly on top, >=2 enemies below
                    if depth == 1 and len(col) >= 3:
                        enemies = sum(1 for p in col[:-1] if p[0] == opp_c)
                        if enemies >= 2:
                            lib_penalty += enemies * 100
                else:
                    opp_stacks += 1
                    if top[1] == KING:
                        opp_kings += 1
                    if is_center:
                        opp_center += 1
                    if opp_c == W:
                        opp_adv += 20 + 60.0 * r / 9.0
                    else:
                        opp_adv += 20 + 60.0 * (9 - r) / 9.0
                    depth = 0
                    for i in range(len(col) - 1, -1, -1):
                        if col[i][0] == opp_c:
                            depth += 1
                        else:
                            break
                    opp_comp += depth
                    for p in col:
                        if p[0] == color:
                            own_prisoners += 1

        if own_stacks == 0:
            return 0.0
        if opp_stacks == 0:
            return 1.0

        score = (
            (own_stacks - opp_stacks) * 1000
            + (own_kings - opp_kings) * 500
            + (opp_prisoners - own_prisoners) * 200
            + (own_comp - opp_comp) * 150
            + (own_center - opp_center) * 30
            + (own_adv - opp_adv)
            - lib_penalty
        )
        x = max(-20.0, min(20.0, score / 2000.0))
        return 1.0 / (1.0 + math.exp(-x))

    # ── Extra helpers for display module ─────────────────────────────────

    @staticmethod
    def get_simple_moves_for(board, r, c, color):
        """Return simple move destinations from (r, c) as list of [nr, nc]."""
        return get_simple_moves(board, r, c, color)

    @staticmethod
    def get_jumps_for(board, r, c, color, jumped_set=None):
        """Return filtered jumps from (r, c).

        Each result is [land_r, land_c, target_r, target_c, dir_r, dir_c].
        jumped_set = set of (r, c) coordinates already jumped in this sequence.
        """
        return get_jumps(board, r, c, color, jumped_set)

    @staticmethod
    def any_capture_for(board, color):
        """True if any piece of color can capture."""
        return any_capture(board, color)

    @staticmethod
    def exec_jump(board, fr, fc, lr, lc, tr, tc, color):
        """Execute a single jump on board IN PLACE (for display use)."""
        _exec_jump_on_board(board, fr, fc, lr, lc, tr, tc, color)

    @staticmethod
    def exec_move(board, fr, fc, tr, tc, color):
        """Execute a simple move on board IN PLACE (for display use).

        Returns True if the piece was a man.
        """
        return _exec_move_on_board(board, fr, fc, tr, tc, color)
