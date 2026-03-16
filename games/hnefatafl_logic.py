"""
Copenhagen Hnefatafl 11x11 -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Copenhagen Hnefatafl,
an 11x11 asymmetric strategy game for two players.

Player 1 = Attacker, Player 2 = Defender.

A move is represented as two [row, col] pairs::

    [[from_r, from_c], [to_r, to_c]]
"""

import copy
import math
from collections import deque

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

BOARD_N = 11

# Piece codes
EMPTY    = 0
ATTACKER = 1
DEFENDER = 2
KING     = 3

# Player identifiers (used in state["turn"] and as player arg)
PLAYER_ATTACKER = 1
PLAYER_DEFENDER = 2

COL_LABELS = "ABCDEFGHIJK"

# ── Private constants ────────────────────────────────────────────────────────

_DIRS = [[0, 1], [0, -1], [1, 0], [-1, 0]]

_CORNERS = [[0, 0], [0, 10], [10, 0], [10, 10]]
_CORNERS_SET = {(0, 0), (0, 10), (10, 0), (10, 10)}
_THRONE = [5, 5]
_RESTRICTED_SET = _CORNERS_SET | {(5, 5)}

# Initial positions
_INIT_KING = [5, 5]

_INIT_DEFENDERS = [
    [5, 3], [4, 4], [5, 4], [6, 4],
    [3, 5], [4, 5], [6, 5], [7, 5],
    [4, 6], [5, 6], [6, 6], [5, 7],
]

_INIT_ATTACKERS = [
    # left wing
    [3, 0], [4, 0], [5, 0], [6, 0], [7, 0], [5, 1],
    # bottom wing
    [0, 3], [0, 4], [0, 5], [1, 5], [0, 6], [0, 7],
    # top wing
    [10, 3], [10, 4], [10, 5], [9, 5], [10, 6], [10, 7],
    # right wing
    [5, 9], [3, 10], [4, 10], [5, 10], [6, 10], [7, 10],
]


# ── Pure helper functions ────────────────────────────────────────────────────

def _in_bounds(r, c):
    return 0 <= r < BOARD_N and 0 <= c < BOARD_N


def _is_corner(r, c):
    return (r, c) in _CORNERS_SET


def _is_restricted(r, c):
    return (r, c) in _RESTRICTED_SET


def _is_edge(r, c):
    return r == 0 or r == BOARD_N - 1 or c == 0 or c == BOARD_N - 1


def _side_of(piece):
    """Return 0 for attacker side, 1 for defender/king side, -1 for empty."""
    if piece == ATTACKER:
        return 0
    if piece in (DEFENDER, KING):
        return 1
    return -1


def _coord_label(r, c):
    """Human-readable coordinate, e.g. 'F6'."""
    return f"{COL_LABELS[c]}{r + 1}"


def _find_king(board):
    """Return [r, c] of the king, or [None, None] if not found."""
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if board[r][c] == KING:
                return r, c
    return None, None


def _get_legal_moves_for_piece(board, r, c):
    """Compute legal destination squares for the piece at (r, c).

    Returns a list of [row, col] lists.
    """
    piece = board[r][c]
    if piece == EMPTY:
        return []
    is_king = piece == KING
    moves = []
    for dr, dc in _DIRS:
        nr, nc = r + dr, c + dc
        while _in_bounds(nr, nc):
            if board[nr][nc] != EMPTY:
                break
            if _is_restricted(nr, nc) and not is_king:
                if (nr, nc) == (5, 5):
                    # may pass through the empty throne, but not land
                    nr += dr
                    nc += dc
                    continue
                else:
                    break  # corners: can't land or pass
            moves.append([nr, nc])
            nr += dr
            nc += dc
    return moves


def _has_legal_move(board, side):
    """True if the given side (PLAYER_ATTACKER or PLAYER_DEFENDER) has any legal move."""
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            p = board[r][c]
            if p == EMPTY:
                continue
            if side == PLAYER_ATTACKER and p != ATTACKER:
                continue
            if side == PLAYER_DEFENDER and p not in (DEFENDER, KING):
                continue
            if _get_legal_moves_for_piece(board, r, c):
                return True
    return False


def _is_hostile_to(board, r, c, target_side):
    """Is the square (r,c) hostile to target_side when empty?"""
    if not _is_restricted(r, c):
        return False
    if _is_corner(r, c):
        return True  # hostile to both sides
    # Throne
    if (r, c) == (5, 5):
        if target_side == 0:  # attacker
            return True  # always hostile
        return board[5][5] == EMPTY  # hostile to defenders only when empty
    return False


def _is_captor(board, r, c, mover_side, target_side):
    """Does (r,c) act as the far jaw of a sandwich for mover_side?"""
    if not _in_bounds(r, c):
        return False
    p = board[r][c]
    if p != EMPTY:
        return _side_of(p) == mover_side
    return _is_hostile_to(board, r, c, target_side)


def _standard_captures(board, mr, mc, ms, es):
    """Find standard custodial captures after piece moves to (mr, mc)."""
    caps = []
    for dr, dc in _DIRS:
        ar, ac = mr + dr, mc + dc
        if not _in_bounds(ar, ac):
            continue
        adj = board[ar][ac]
        if adj == EMPTY or adj == KING:
            continue  # king handled separately
        if _side_of(adj) != es:
            continue
        br, bc = ar + dr, ac + dc
        if _is_captor(board, br, bc, ms, es):
            caps.append([ar, ac])
    return caps


def _shieldwall_captures(board, mr, mc, ms, es):
    """Find shieldwall captures after piece moves to (mr, mc)."""
    caps = []
    # (is_row?, fixed, inward_dr, inward_dc)
    edges = [
        (True,  0,   1,  0),   # bottom edge row 0, inward = +row
        (True,  10, -1,  0),   # top edge row 10
        (False, 0,   0,  1),   # left edge col 0, inward = +col
        (False, 10,  0, -1),   # right edge col 10
    ]
    for is_row, fixed, idr, idc in edges:
        # Collect cells along this edge
        cells = []
        for v in range(BOARD_N):
            if is_row:
                rc_r, rc_c = fixed, v
            else:
                rc_r, rc_c = v, fixed
            cells.append((rc_r, rc_c, board[rc_r][rc_c]))

        # Find contiguous enemy groups of length >= 2
        groups = []
        cur = []
        for r, c, p in cells:
            if p != EMPTY and _side_of(p) == es:
                cur.append((r, c, p))
            else:
                if len(cur) >= 2:
                    groups.append(cur)
                cur = []
        if len(cur) >= 2:
            groups.append(cur)

        for grp in groups:
            fr, fc, _ = grp[0]
            lr, lc, _ = grp[-1]
            # Bracket positions (one step before / after along edge)
            if is_row:
                before = (fr, fc - 1)
                after = (lr, lc + 1)
            else:
                before = (fr - 1, fc)
                after = (lr + 1, lc)

            def _bracket_ok(pos):
                br, bc = pos
                if not _in_bounds(br, bc):
                    return False
                if _is_corner(br, bc):
                    return True  # corner substitutes
                bp = board[br][bc]
                return bp != EMPTY and _side_of(bp) == ms

            if not (_bracket_ok(before) and _bracket_ok(after)):
                continue

            # Every piece in the group must be fronted by a mover-side piece
            fronted = True
            for r, c, _ in grp:
                ir, ic = r + idr, c + idc
                if not _in_bounds(ir, ic):
                    fronted = False
                    break
                ip = board[ir][ic]
                if ip == EMPTY or _side_of(ip) != ms:
                    fronted = False
                    break
            if not fronted:
                continue

            # The moving piece must be one of the brackets or fronters
            involved = set()
            if _in_bounds(*before) and not _is_corner(*before):
                involved.add(before)
            if _in_bounds(*after) and not _is_corner(*after):
                involved.add(after)
            for r, c, _ in grp:
                involved.add((r + idr, c + idc))
            if (mr, mc) not in involved:
                continue

            for r, c, p in grp:
                if p != KING:
                    caps.append([r, c])
    return caps


def _check_king_captured(board):
    """Check positionally whether the king is captured right now."""
    kr, kc = _find_king(board)
    if kr is None:
        return False
    if _is_edge(kr, kc):
        return False  # immune on edge

    adj_throne = (kr, kc) != (5, 5) and (abs(kr - 5) + abs(kc - 5) == 1)

    for dr, dc in _DIRS:
        nr, nc = kr + dr, kc + dc
        if adj_throne and (nr, nc) == (5, 5):
            continue  # throne counts as surrounding
        if not _in_bounds(nr, nc) or board[nr][nc] != ATTACKER:
            return False
    return True


def _check_encirclement(board):
    """Check if all defenders (including king) are encircled with no path to edge."""
    kr, kc = _find_king(board)
    if kr is None:
        return False
    visited = set()
    queue = deque()
    queue.append((kr, kc))
    visited.add((kr, kc))
    while queue:
        r, c = queue.popleft()
        if _is_edge(r, c):
            return False  # path to edge exists
        for dr, dc in _DIRS:
            nr, nc = r + dr, c + dc
            if not _in_bounds(nr, nc) or (nr, nc) in visited:
                continue
            p = board[nr][nc]
            if p == EMPTY or _side_of(p) == 1:
                visited.add((nr, nc))
                queue.append((nr, nc))
    return True


def _pos_key_str(board, turn):
    """Create a string key for position hashing / repetition detection."""
    parts = []
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            parts.append(str(board[r][c]))
    parts.append(str(turn))
    return ",".join(parts)


def _piece_counts(board):
    """Return [attacker_count, defender_count]."""
    atk = 0
    dfn = 0
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            p = board[r][c]
            if p == ATTACKER:
                atk += 1
            elif p in (DEFENDER, KING):
                dfn += 1
    return [atk, dfn]


# ── Game class ───────────────────────────────────────────────────────────────

class HnefataflLogic(AbstractBoardGame):
    """Copenhagen Hnefatafl game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":            [[int, ...], ...],  # 11x11, values: EMPTY/ATTACKER/DEFENDER/KING
            "turn":             int,                # PLAYER_ATTACKER (1) or PLAYER_DEFENDER (2)
            "game_over":        bool,
            "winner":           int or None,        # PLAYER_ATTACKER, PLAYER_DEFENDER, or None
            "message":          str,
            "last_move":        [[fr,fc],[tr,tc]] or None,
            "captured_last":    [[r,c], ...],       # squares captured on the last turn
            "position_counts":  {"key": int, ...},  # for repetition detection
        }

    A move is a list of two [row, col] pairs::

        [[from_r, from_c], [to_r, to_c]]
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Hnefatafl"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [[EMPTY] * BOARD_N for _ in range(BOARD_N)]
        board[_INIT_KING[0]][_INIT_KING[1]] = KING
        for r, c in _INIT_DEFENDERS:
            board[r][c] = DEFENDER
        for r, c in _INIT_ATTACKERS:
            board[r][c] = ATTACKER

        turn = PLAYER_ATTACKER  # attackers move first

        pos_key = _pos_key_str(board, turn)
        position_counts = {pos_key: 1}

        rep = position_counts.get(pos_key, 0)
        message = "Attackers' turn"
        if rep >= 2:
            message += f"  [position seen {rep}x  -- vary play!]"

        return {
            "board": board,
            "turn": turn,
            "game_over": False,
            "winner": None,
            "message": message,
            "last_move": None,
            "captured_last": [],
            "position_counts": position_counts,
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        if state["game_over"]:
            return []
        board = state["board"]
        moves = []
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                p = board[r][c]
                if p == EMPTY:
                    continue
                if player == PLAYER_ATTACKER and p != ATTACKER:
                    continue
                if player == PLAYER_DEFENDER and p not in (DEFENDER, KING):
                    continue
                dests = _get_legal_moves_for_piece(board, r, c)
                for dest in dests:
                    moves.append([[r, c], dest])
        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)
        board = new["board"]
        (fr, fc), (tr, tc) = move[0], move[1]
        piece = board[fr][fc]
        ms = _side_of(piece)
        es = 1 - ms

        # Move the piece
        board[fr][fc] = EMPTY
        board[tr][tc] = piece
        new["last_move"] = [[fr, fc], [tr, tc]]

        # Corner escape
        if piece == KING and _is_corner(tr, tc):
            new["game_over"] = True
            new["winner"] = PLAYER_DEFENDER
            new["message"] = (f"Defenders win!  King escaped to "
                              f"{_coord_label(tr, tc)}!")
            new["captured_last"] = []
            return new

        # Process captures
        caps = _standard_captures(board, tr, tc, ms, es)
        sw = _shieldwall_captures(board, tr, tc, ms, es)
        seen = set()
        for cap in caps:
            seen.add((cap[0], cap[1]))
        for pos in sw:
            if (pos[0], pos[1]) not in seen:
                caps.append(pos)
                seen.add((pos[0], pos[1]))
        for cap in caps:
            board[cap[0]][cap[1]] = EMPTY
        new["captured_last"] = caps

        # King capture (only after attacker move)
        if ms == 0 and _check_king_captured(board):
            new["game_over"] = True
            new["winner"] = PLAYER_ATTACKER
            new["message"] = "Attackers win!  King is captured!"
            return new

        # Encirclement (only after attacker move)
        if ms == 0 and _check_encirclement(board):
            new["game_over"] = True
            new["winner"] = PLAYER_ATTACKER
            new["message"] = "Attackers win!  Defenders are encircled!"
            return new

        # Switch turn
        new["turn"] = PLAYER_DEFENDER if state["turn"] == PLAYER_ATTACKER else PLAYER_ATTACKER

        # Record position for repetition
        pos_key = _pos_key_str(board, new["turn"])
        pos_counts = new["position_counts"]
        pos_counts[pos_key] = pos_counts.get(pos_key, 0) + 1

        # No-move loss
        if not _has_legal_move(board, new["turn"]):
            new["game_over"] = True
            new["winner"] = PLAYER_ATTACKER if new["turn"] == PLAYER_DEFENDER else PLAYER_DEFENDER
            loser = "Defenders" if new["turn"] == PLAYER_DEFENDER else "Attackers"
            winner_name = "Attackers" if new["winner"] == PLAYER_ATTACKER else "Defenders"
            new["message"] = f"{loser} have no legal moves -- {winner_name} win!"
            return new

        # Perpetual repetition
        rep_count = pos_counts.get(pos_key, 0)
        if rep_count >= 3:
            new["game_over"] = True
            new["winner"] = PLAYER_ATTACKER
            new["message"] = ("Position repeated 3 times -- "
                              "Defenders lose by perpetual repetition!")
            return new

        # Update message
        name = "Attackers" if new["turn"] == PLAYER_ATTACKER else "Defenders"
        new["message"] = f"{name}' turn"
        if rep_count >= 2:
            new["message"] += f"  [position seen {rep_count}x  -- vary play!]"

        return new

    def _get_game_status(self, state):
        if not state["game_over"]:
            return {"is_over": False, "winner": None, "is_draw": False}
        return {"is_over": True, "winner": state["winner"], "is_draw": False}

    # ── Evaluation hook ────────────────────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate from *player*'s perspective (asymmetric: attacker vs defender)."""
        if state["game_over"]:
            return 1.0 if state["winner"] == player else 0.0

        board = state["board"]
        kr, kc = _find_king(board)
        if kr is None:
            return 1.0 if player == PLAYER_ATTACKER else 0.0

        # Piece counts
        atk_count = 0
        def_count = 0
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                p = board[r][c]
                if p == ATTACKER:
                    atk_count += 1
                elif p in (DEFENDER, KING):
                    def_count += 1

        # King distance to nearest corner (Manhattan)
        min_king_dist = 20
        for cr, cc in _CORNERS:
            d = abs(kr - cr) + abs(kc - cc)
            if d < min_king_dist:
                min_king_dist = d

        # King escape routes: unobstructed straight-line paths to any corner
        escape_routes = 0
        guaranteed_escape = False
        for cr, cc in _CORNERS:
            if kr == cr:
                c_lo, c_hi = min(kc, cc), max(kc, cc)
                clear = True
                for c in range(c_lo + 1, c_hi):
                    if board[kr][c] != EMPTY:
                        clear = False
                        break
                if clear and c_hi > c_lo:
                    escape_routes += 1
                    guaranteed_escape = True
            if kc == cc:
                r_lo, r_hi = min(kr, cr), max(kr, cr)
                clear = True
                for r in range(r_lo + 1, r_hi):
                    if board[r][kc] != EMPTY:
                        clear = False
                        break
                if clear and r_hi > r_lo:
                    escape_routes += 1
                    guaranteed_escape = True

        # Pieces adjacent to king
        king_adj_attackers = 0
        king_adj_defenders = 0
        for dr, dc in _DIRS:
            nr, nc = kr + dr, kc + dc
            if _in_bounds(nr, nc):
                adj = board[nr][nc]
                if adj == ATTACKER:
                    king_adj_attackers += 1
                elif adj == DEFENDER:
                    king_adj_defenders += 1

        # Defender-perspective score
        score = 0
        score -= min_king_dist * 70       # closer to corner = better
        score += escape_routes * 100      # escape routes
        if guaranteed_escape:
            score += 1000                 # near-win
        score += def_count * 55           # defender material
        score += king_adj_defenders * 100 # defenders protecting king
        score -= king_adj_attackers * 200 # capture contact
        if escape_routes == 0 and king_adj_attackers > 0:
            score -= 300                  # king bottled by attackers
        score -= atk_count * 8            # attacker material

        x = max(-20.0, min(20.0, score / 2500.0))
        defender_val = 1.0 / (1.0 + math.exp(-x))
        if player == PLAYER_DEFENDER:
            return defender_val
        return 1.0 - defender_val

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves."""
        if state["game_over"]:
            return False
        if not isinstance(move, list) or len(move) != 2:
            return False
        try:
            (fr, fc), (tr, tc) = move
        except (TypeError, ValueError):
            return False
        for r, c in ((fr, fc), (tr, tc)):
            if not (isinstance(r, int) and isinstance(c, int)):
                return False
            if not (0 <= r < BOARD_N and 0 <= c < BOARD_N):
                return False

        board = state["board"]
        piece = board[fr][fc]
        if piece == EMPTY:
            return False

        # Check ownership
        if player == PLAYER_ATTACKER and piece != ATTACKER:
            return False
        if player == PLAYER_DEFENDER and piece not in (DEFENDER, KING):
            return False

        # Check that [tr, tc] is a legal destination for this piece
        legal_dests = _get_legal_moves_for_piece(board, fr, fc)
        return [tr, tc] in legal_dests

    # ── Static helpers for display module ─────────────────────────────────

    @staticmethod
    def get_piece_moves(board, r, c):
        """Get legal destination squares for the piece at (r, c).

        Returns a list of [row, col] lists. Useful for the display module
        to show valid move targets when a piece is selected.
        """
        return _get_legal_moves_for_piece(board, r, c)

    @staticmethod
    def piece_counts(board):
        """Return [attacker_count, defender_count]."""
        return _piece_counts(board)

    @staticmethod
    def coord_label(r, c):
        """Human-readable coordinate, e.g. 'F6'."""
        return _coord_label(r, c)

    @staticmethod
    def side_of(piece):
        """Return 0 for attacker side, 1 for defender/king side, -1 for empty."""
        return _side_of(piece)

    @staticmethod
    def is_corner(r, c):
        return _is_corner(r, c)

    @staticmethod
    def is_restricted(r, c):
        return _is_restricted(r, c)

    @staticmethod
    def in_bounds(r, c):
        return _in_bounds(r, c)
