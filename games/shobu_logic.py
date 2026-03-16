"""
Shobu -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Shobu,
a two-player abstract strategy game played on four 4x4 boards.

A complete move is represented as a dict::

    {
        "passive_board":  int,       # board index 0-3
        "passive_from":   [r, c],    # source of passive stone
        "passive_to":     [r, c],    # destination of passive stone
        "aggressive_board": int,     # board index 0-3
        "aggressive_from":  [r, c],  # source of aggressive stone
        "aggressive_to":    [r, c],  # destination of aggressive stone
    }

Board layout::

       A (Dark)      B (Light)     <-- WHITE's homeboards (indices 0, 1)
              -- ROPE --
       C (Light)     D (Dark)      <-- BLACK's homeboards (indices 2, 3)

Player 1 = BLACK, Player 2 = WHITE.
"""

import copy
import math

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

EMPTY, BLACK, WHITE = 0, 1, 2
DARK_T, LITE_T = 0, 1

BOARD_TYPE = [DARK_T, LITE_T, LITE_T, DARK_T]   # A B C D
BOARD_NAME = ["A", "B", "C", "D"]
HOME = {BLACK: [2, 3], WHITE: [0, 1]}

DIRS = [[-1, 0], [-1, 1], [0, 1], [1, 1],
        [1, 0],  [1, -1], [0, -1], [-1, -1]]

DIR_NAME = {
    "-1,0": "N", "-1,1": "NE", "0,1": "E", "1,1": "SE",
    "1,0": "S",  "1,-1": "SW", "0,-1": "W", "-1,-1": "NW",
}


# ── Pure helper functions ────────────────────────────────────────────────────

def on_grid(r, c):
    """True if (r, c) is within the 4x4 board."""
    return 0 <= r < 4 and 0 <= c < 4


def dir_dist(fr, fc, tr, tc):
    """Return ([dr, dc], distance) for a straight-line move, or None.

    Only distances 1 and 2 are valid in Shobu.
    """
    dr, dc = tr - fr, tc - fc
    if dr == 0 and dc == 0:
        return None
    d = max(abs(dr), abs(dc))
    if d not in (1, 2):
        return None
    if dr != 0 and dc != 0 and abs(dr) != abs(dc):
        return None
    nd = [dr // d, dc // d]
    if nd not in DIRS:
        return None
    return (nd, d)


def opp_color_boards(board_idx):
    """Boards whose type is opposite to board_idx's type."""
    want = LITE_T if BOARD_TYPE[board_idx] == DARK_T else DARK_T
    return [b for b in range(4) if BOARD_TYPE[b] == want]


def dir_name_key(d):
    """Convert a direction list to a string key for DIR_NAME lookup."""
    return str(d[0]) + "," + str(d[1])


def stone_counts(boards, board_idx):
    """Return [black_count, white_count] for a board."""
    bc = 0
    wc = 0
    for r in range(4):
        for c in range(4):
            v = boards[board_idx][r][c]
            if v == BLACK:
                bc += 1
            elif v == WHITE:
                wc += 1
    return [bc, wc]


# ── Internal validation helpers ──────────────────────────────────────────────

def _path_clear_passive(boards, b, fr, fc, d, dist):
    """All cells in path (inclusive of destination) must be empty."""
    for s in range(1, dist + 1):
        nr, nc = fr + d[0] * s, fc + d[1] * s
        if not on_grid(nr, nc) or boards[b][nr][nc] != EMPTY:
            return False
    return True


def _aggr_legal(boards, turn, b, fr, fc, d, dist):
    """Check aggressive move legality on board b from (fr, fc)."""
    opp = WHITE if turn == BLACK else BLACK
    if boards[b][fr][fc] != turn:
        return False
    tr, tc = fr + d[0] * dist, fc + d[1] * dist
    if not on_grid(tr, tc):
        return False
    hit = []
    for s in range(1, dist + 1):
        nr, nc = fr + d[0] * s, fc + d[1] * s
        v = boards[b][nr][nc]
        if v == turn:
            return False            # blocked by own stone
        if v == opp:
            hit.append([nr, nc])
    if len(hit) > 1:
        return False                # can't push two stones
    if len(hit) == 1:
        # Push destination is always D + û (one unit step beyond the
        # aggressive stone's destination), regardless of where the opponent is.
        pr, pc = tr + d[0], tc + d[1]
        if on_grid(pr, pc) and boards[b][pr][pc] != EMPTY:
            return False
    return True


def _has_aggr_followup(boards, turn, pass_board, d, dist):
    """True if any aggressive move exists matching the given direction/distance."""
    for b in opp_color_boards(pass_board):
        for r in range(4):
            for c in range(4):
                if boards[b][r][c] == turn:
                    if _aggr_legal(boards, turn, b, r, c, d, dist):
                        return True
    return False


def _passive_legal(boards, turn, b, fr, fc, tr, tc):
    """Full passive legality: correct board, clear path, has aggr follow-up."""
    if b not in HOME[turn]:
        return False
    if boards[b][fr][fc] != turn:
        return False
    if not on_grid(tr, tc):
        return False
    dd = dir_dist(fr, fc, tr, tc)
    if dd is None:
        return False
    d, dist = dd
    if not _path_clear_passive(boards, b, fr, fc, d, dist):
        return False
    return _has_aggr_followup(boards, turn, b, d, dist)


def _check_winner(boards, turn):
    """If any board has zero opponent stones, current player wins.

    Returns the winner (turn) or None.
    """
    opp = WHITE if turn == BLACK else BLACK
    for b in range(4):
        found = False
        for r in range(4):
            for c in range(4):
                if boards[b][r][c] == opp:
                    found = True
                    break
            if found:
                break
        if not found:
            return turn
    return None


def _has_any_move(boards, turn):
    """True if the current player has at least one complete legal move."""
    for pb in HOME[turn]:
        for fr in range(4):
            for fc in range(4):
                if boards[pb][fr][fc] != turn:
                    continue
                for d in DIRS:
                    for dist in (1, 2):
                        tr, tc = fr + d[0] * dist, fc + d[1] * dist
                        if on_grid(tr, tc) and _passive_legal(boards, turn, pb, fr, fc, tr, tc):
                            return True
    return False


# ── Helpers exported for the display module ──────────────────────────────────

def get_selectable_passive_stones(boards, turn):
    """Return list of [b, r, c] for stones the player can use for a passive move."""
    result = []
    for pb in HOME[turn]:
        for r in range(4):
            for c in range(4):
                if boards[pb][r][c] != turn:
                    continue
                usable = False
                for d in DIRS:
                    for dist in (1, 2):
                        tr, tc = r + d[0] * dist, c + d[1] * dist
                        if on_grid(tr, tc) and _passive_legal(boards, turn, pb, r, c, tr, tc):
                            usable = True
                            break
                    if usable:
                        break
                if usable:
                    result.append([pb, r, c])
    return result


def get_passive_destinations(boards, turn, b, r, c):
    """Return list of [b, tr, tc] for valid passive destinations."""
    result = []
    for d in DIRS:
        for dist in (1, 2):
            tr, tc = r + d[0] * dist, c + d[1] * dist
            if on_grid(tr, tc) and _passive_legal(boards, turn, b, r, c, tr, tc):
                result.append([b, tr, tc])
    return result


def get_selectable_aggressive_stones(boards, turn, pass_board, d, dist):
    """Return list of [b, r, c] for stones that can make the aggressive move."""
    result = []
    for b in opp_color_boards(pass_board):
        for r in range(4):
            for c in range(4):
                if boards[b][r][c] == turn:
                    if _aggr_legal(boards, turn, b, r, c, d, dist):
                        result.append([b, r, c])
    return result


def get_aggressive_destination(boards, turn, b, r, c, d, dist):
    """Return [b, tr, tc] if the aggressive move is legal, else None."""
    tr, tc = r + d[0] * dist, c + d[1] * dist
    if on_grid(tr, tc) and _aggr_legal(boards, turn, b, r, c, d, dist):
        return [b, tr, tc]
    return None


def compute_push_info(boards, turn, b, fr, fc, d, dist):
    """Return push info dict if the aggressive move pushes a stone, else None.

    Returns::
        {"board": int, "opp_r": int, "opp_c": int,
         "dest_r": int, "dest_c": int, "off_board": bool}
    """
    opp = WHITE if turn == BLACK else BLACK
    # Aggressive destination
    atr, atc = fr + d[0] * dist, fc + d[1] * dist
    for s in range(1, dist + 1):
        nr, nc = fr + d[0] * s, fc + d[1] * s
        if boards[b][nr][nc] == opp:
            # Push destination is always D + û
            pr, pc = atr + d[0], atc + d[1]
            off = not on_grid(pr, pc)
            return {
                "board": b, "opp_r": nr, "opp_c": nc,
                "dest_r": pr, "dest_c": pc, "off_board": off,
            }
    return None


# ── Evaluation helpers ────────────────────────────────────────────────────────

_SHOBU_PSQ = (
    (0, 1, 1, 0),
    (1, 3, 3, 1),
    (1, 3, 3, 1),
    (0, 1, 1, 0),
)


# ── Game class ───────────────────────────────────────────────────────────────

class ShobuLogic(AbstractBoardGame):
    """Shobu game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "boards": [[[int,...]*4]*4]*4,  # 4 boards, each 4x4
            "turn":   int,                  # BLACK (1) or WHITE (2)
        }

    A move is a dict::

        {
            "passive_board":    int,
            "passive_from":     [r, c],
            "passive_to":       [r, c],
            "aggressive_board": int,
            "aggressive_from":  [r, c],
            "aggressive_to":    [r, c],
        }
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Shobu"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        boards = []
        for b in range(4):
            board = [[EMPTY] * 4 for _ in range(4)]
            for c in range(4):
                board[0][c] = WHITE   # top row
                board[3][c] = BLACK   # bottom row
            boards.append(board)
        return {"boards": boards, "turn": BLACK}

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        # Work on a copy so we never mutate the original state
        boards = [[row[:] for row in b] for b in state["boards"]]
        moves = []
        for pb in HOME[player]:
            for fr in range(4):
                for fc in range(4):
                    if boards[pb][fr][fc] != player:
                        continue
                    for d in DIRS:
                        for dist in (1, 2):
                            tr, tc = fr + d[0] * dist, fc + d[1] * dist
                            if not on_grid(tr, tc):
                                continue
                            if not _passive_legal(boards, player, pb, fr, fc, tr, tc):
                                continue
                            # Apply the passive move temporarily to find aggressive options
                            boards[pb][fr][fc] = EMPTY
                            boards[pb][tr][tc] = player
                            for ab in opp_color_boards(pb):
                                for ar in range(4):
                                    for ac in range(4):
                                        if boards[ab][ar][ac] != player:
                                            continue
                                        if _aggr_legal(boards, player, ab, ar, ac, d, dist):
                                            atr = ar + d[0] * dist
                                            atc = ac + d[1] * dist
                                            moves.append({
                                                "passive_board": pb,
                                                "passive_from": [fr, fc],
                                                "passive_to": [tr, tc],
                                                "aggressive_board": ab,
                                                "aggressive_from": [ar, ac],
                                                "aggressive_to": [atr, atc],
                                            })
                            # Restore the passive move
                            boards[pb][tr][tc] = EMPTY
                            boards[pb][fr][fc] = player
        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)
        boards = new["boards"]

        # Passive move
        pb = move["passive_board"]
        pfr, pfc = move["passive_from"]
        ptr, ptc = move["passive_to"]
        boards[pb][pfr][pfc] = EMPTY
        boards[pb][ptr][ptc] = player

        # Aggressive move (handle push first)
        ab = move["aggressive_board"]
        afr, afc = move["aggressive_from"]
        atr, atc = move["aggressive_to"]
        opp = WHITE if player == BLACK else BLACK

        dd = dir_dist(afr, afc, atr, atc)
        d, dist = dd

        for s in range(1, dist + 1):
            nr, nc = afr + d[0] * s, afc + d[1] * s
            if boards[ab][nr][nc] == opp:
                boards[ab][nr][nc] = EMPTY
                # Push destination is always D + û (one step beyond
                # the aggressive stone's destination)
                pr, pc = atr + d[0], atc + d[1]
                if on_grid(pr, pc):
                    boards[ab][pr][pc] = opp
                break

        boards[ab][afr][afc] = EMPTY
        boards[ab][atr][atc] = player

        # Switch turn
        new["turn"] = WHITE if player == BLACK else BLACK
        return new

    def _get_game_status(self, state):
        boards = state["boards"]
        turn = state["turn"]

        # Check if any board has zero stones of either color
        for b in range(4):
            black_found = False
            white_found = False
            for r in range(4):
                for c in range(4):
                    if boards[b][r][c] == BLACK:
                        black_found = True
                    elif boards[b][r][c] == WHITE:
                        white_found = True
            if not black_found:
                return {"is_over": True, "winner": WHITE, "is_draw": False}
            if not white_found:
                return {"is_over": True, "winner": BLACK, "is_draw": False}

        # Check if current player has no moves
        if not _has_any_move(boards, turn):
            winner = WHITE if turn == BLACK else BLACK
            return {"is_over": True, "winner": winner, "is_draw": False}

        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Evaluation hook ────────────────────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate from *player*'s perspective using per-board Shobu heuristics.

        Features: race-to-zero with squared scaling (per-board stone counts,
        non-linear danger curve), geometric push-off threats, home board
        retention (1.5× multiplier), positional (piece-square table with
        home multiplier, barrier pairs, edge vulnerability), phase-dependent
        weighting, danger signals.
        """
        boards = state["boards"]
        opp = WHITE if player == BLACK else BLACK
        p_home = HOME[player]

        # ── Accumulators ────────────────────────────────────────────
        p_cnt = [0, 0, 0, 0]
        o_cnt = [0, 0, 0, 0]
        p_pos = o_pos = 0.0
        p_edge_brd = [0, 0, 0, 0]
        o_edge_brd = [0, 0, 0, 0]
        p_barriers = o_barriers = 0

        for b in range(4):
            brd = boards[b]
            is_ph = (b == p_home[0] or b == p_home[1])
            hmul_p = 1.5 if is_ph else 1.0
            hmul_o = 1.5 if not is_ph else 1.0

            for r in range(4):
                row = brd[r]
                for c in range(4):
                    v = row[c]
                    if v == EMPTY:
                        continue
                    sv = _SHOBU_PSQ[r][c]
                    on_edge = (r == 0 or r == 3 or c == 0 or c == 3)

                    if v == player:
                        p_cnt[b] += 1
                        p_pos += sv * hmul_p
                        if on_edge:
                            p_edge_brd[b] += 1
                        if c < 3 and row[c + 1] == player:
                            p_barriers += 1
                        if r < 3 and brd[r + 1][c] == player:
                            p_barriers += 1
                    else:
                        o_cnt[b] += 1
                        o_pos += sv * hmul_o
                        if on_edge:
                            o_edge_brd[b] += 1
                        if c < 3 and row[c + 1] == opp:
                            o_barriers += 1
                        if r < 3 and brd[r + 1][c] == opp:
                            o_barriers += 1

        # ── Terminal ────────────────────────────────────────────────
        min_p = min(p_cnt[0], p_cnt[1], p_cnt[2], p_cnt[3])
        min_o = min(o_cnt[0], o_cnt[1], o_cnt[2], o_cnt[3])
        if min_o == 0:
            return 1.0
        if min_p == 0:
            return 0.0

        # ── Push-off threat scan (geometric, no passive validation) ─
        p_pushoffs = o_pushoffs = 0
        for b in range(4):
            brd = boards[b]
            for r in range(4):
                row = brd[r]
                for c in range(4):
                    v = row[c]
                    if v == EMPTY:
                        continue
                    target = opp if v == player else player
                    for d in DIRS:
                        dr, dc = d[0], d[1]
                        for dist in (1, 2):
                            tr = r + dr * dist
                            tc = c + dc * dist
                            if not (0 <= tr < 4 and 0 <= tc < 4):
                                continue
                            # Push destination must be off grid
                            if 0 <= tr + dr < 4 and 0 <= tc + dc < 4:
                                continue
                            # Check path: exactly 1 target, no own-color
                            ok = True
                            hits = 0
                            for s in range(1, dist + 1):
                                mv = brd[r + dr * s][c + dc * s]
                                if mv == v:
                                    ok = False
                                    break
                                if mv == target:
                                    hits += 1
                            if ok and hits == 1:
                                if v == player:
                                    p_pushoffs += 1
                                else:
                                    o_pushoffs += 1

        # ── Phase detection ─────────────────────────────────────────
        total = (p_cnt[0] + p_cnt[1] + p_cnt[2] + p_cnt[3]
                 + o_cnt[0] + o_cnt[1] + o_cnt[2] + o_cnt[3])
        removed = 32 - total
        D = min(min_o, min_p)

        if D >= 3 and removed <= 4:
            phase = 0  # opening
        elif D <= 1:
            phase = 2  # endgame
        else:
            phase = 1  # midgame

        # ── Tier 2: Race-to-zero (squared scaling) ──────────────────
        attack = ((4 - o_cnt[0]) ** 2 + (4 - o_cnt[1]) ** 2
                  + (4 - o_cnt[2]) ** 2 + (4 - o_cnt[3]) ** 2)
        defense = ((4 - p_cnt[0]) ** 2 + (4 - p_cnt[1]) ** 2
                   + (4 - p_cnt[2]) ** 2 + (4 - p_cnt[3]) ** 2)
        race = attack - defense

        # Extra emphasis on weakest board
        weak_bonus = (4 - min_o) ** 2 - (4 - min_p) ** 2

        # Multi-board pressure: ≥2 boards with ≤2 opponent stones
        low_opp = (int(o_cnt[0] <= 2) + int(o_cnt[1] <= 2)
                   + int(o_cnt[2] <= 2) + int(o_cnt[3] <= 2))
        low_own = (int(p_cnt[0] <= 2) + int(p_cnt[1] <= 2)
                   + int(p_cnt[2] <= 2) + int(p_cnt[3] <= 2))
        multi = 0
        if low_opp >= 2:
            multi += 400
        if low_own >= 2:
            multi -= 400

        # ── Tier 3: Push-off threats ────────────────────────────────
        threat_diff = p_pushoffs - o_pushoffs

        # ── Tier 4: Home board retention ────────────────────────────
        home_score = 0.0
        for hb in p_home:
            hs = p_cnt[hb]
            if hs <= 1:
                home_score -= 500
            elif hs <= 2:
                home_score -= 200
        o_home = HOME[opp]
        for hb in o_home:
            hs = o_cnt[hb]
            if hs <= 1:
                home_score += 500
            elif hs <= 2:
                home_score += 200

        # ── Tier 5: Positional ──────────────────────────────────────
        pos_diff = p_pos - o_pos

        # Edge vulnerability: 3+ edge stones on a single board
        edge_vuln = 0
        for b in range(4):
            if p_edge_brd[b] > 2:
                edge_vuln -= (p_edge_brd[b] - 2) * 50
            if o_edge_brd[b] > 2:
                edge_vuln += (o_edge_brd[b] - 2) * 50

        barrier_diff = p_barriers - o_barriers

        # ── Danger signals ──────────────────────────────────────────
        danger = 0.0
        for b in range(4):
            if p_cnt[b] == 1:
                danger -= 300
            if o_cnt[b] == 1:
                danger += 300
            bd = o_cnt[b] - p_cnt[b]
            if bd >= 2:
                danger -= bd * 80
            elif bd <= -2:
                danger += (-bd) * 80

        # ── Phase-weighted combination ──────────────────────────────
        if phase == 0:  # opening
            score = (race * 800 + weak_bonus * 600 + multi
                     + threat_diff * 150
                     + home_score
                     + pos_diff * 45
                     + edge_vuln * 1.3
                     + barrier_diff * 39
                     + danger)
        elif phase == 1:  # midgame
            score = (race * 2000 + weak_bonus * 1500 + multi * 1.5
                     + threat_diff * 400
                     + home_score * 2.0
                     + pos_diff * 21
                     + edge_vuln
                     + barrier_diff * 30
                     + danger)
        else:  # endgame
            score = (race * 3000 + weak_bonus * 2500 + multi * 2.0
                     + threat_diff * 600
                     + home_score * 1.5
                     + pos_diff * 3
                     + edge_vuln * 0.5
                     + barrier_diff * 15
                     + danger * 2.0)

        # ── Sigmoid normalization ───────────────────────────────────
        x = max(-20.0, min(20.0, score / 3000.0))
        return 1.0 / (1.0 + math.exp(-x))

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves."""
        if not isinstance(move, dict):
            return False
        required_keys = {"passive_board", "passive_from", "passive_to",
                         "aggressive_board", "aggressive_from", "aggressive_to"}
        if set(move.keys()) != required_keys:
            return False

        boards = state["boards"]
        pb = move["passive_board"]
        pf = move["passive_from"]
        pt = move["passive_to"]
        ab = move["aggressive_board"]
        af = move["aggressive_from"]
        at = move["aggressive_to"]

        # Validate types
        if not isinstance(pb, int) or not isinstance(ab, int):
            return False
        for coord in (pf, pt, af, at):
            if not isinstance(coord, list) or len(coord) != 2:
                return False
            if not all(isinstance(v, int) for v in coord):
                return False

        # Validate board indices
        if not (0 <= pb < 4) or not (0 <= ab < 4):
            return False

        # Validate coordinates
        for coord in (pf, pt, af, at):
            if not on_grid(coord[0], coord[1]):
                return False

        # Validate passive move
        if not _passive_legal(boards, player, pb, pf[0], pf[1], pt[0], pt[1]):
            return False

        # Get direction and distance from passive move
        dd = dir_dist(pf[0], pf[1], pt[0], pt[1])
        if dd is None:
            return False
        d, dist = dd

        # Aggressive board must be opposite color to passive board
        if ab not in opp_color_boards(pb):
            return False

        # Aggressive destination must match direction and distance
        add = dir_dist(af[0], af[1], at[0], at[1])
        if add is None:
            return False
        ad, adist = add
        if ad != d or adist != dist:
            return False

        # Apply passive move on a copy, then check aggressive legality
        tmp = [[row[:] for row in b] for b in boards]
        tmp[pb][pf[0]][pf[1]] = EMPTY
        tmp[pb][pt[0]][pt[1]] = player

        return _aggr_legal(tmp, player, ab, af[0], af[1], d, dist)
