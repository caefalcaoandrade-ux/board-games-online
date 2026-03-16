"""
Tak 6x6 -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Tak,
a two-player abstract strategy game played on a 6x6 grid.

Player 1 = White, Player 2 = Black.

Board representation
--------------------
The board is a 6x6 grid stored as a list of lists.
Each cell is a list (stack) of piece dicts, bottom to top.
A piece dict: {"owner": 1 or 2, "type": "flat" | "standing" | "capstone"}

Stacks are stored as lists of [owner, type_code] pairs for JSON-compactness:
  type_code: 0 = flat, 1 = standing, 2 = capstone
  e.g. [1, 0] = Player 1 flat stone

A move is a dict:
  Place: {"action": "place", "row": r, "col": c, "piece": "flat"|"standing"|"capstone"}
  Move:  {"action": "move", "row": r, "col": c, "direction": d, "drops": [d1, d2, ...]}
         where direction is 0=north(+row), 1=south(-row), 2=east(+col), 3=west(-col)
"""

import copy
import math
from collections import deque

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

BOARD_SIZE = 6
CARRY_LIMIT = 6  # Equal to board width per rules §6.2
INITIAL_STONES = 30
INITIAL_CAPSTONES = 1

# Player identifiers
WHITE = 1
BLACK = 2

# Piece type codes (compact for JSON state)
FLAT = 0
STANDING = 1
CAPSTONE = 2

# Direction codes and deltas: 0=north(+r), 1=south(-r), 2=east(+c), 3=west(-c)
DIR_NORTH = 0
DIR_SOUTH = 1
DIR_EAST = 2
DIR_WEST = 3

_DIR_DELTAS = [
    [1, 0],   # north: row increases
    [-1, 0],  # south: row decreases
    [0, 1],   # east: col increases
    [0, -1],  # west: col decreases
]

DIR_NAMES = ["north", "south", "east", "west"]

# File/rank labels for display
FILES = "abcdef"
RANKS = "123456"


# ── Pure helper functions ────────────────────────────────────────────────────

def _in_bounds(r, c):
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


def sq_label(r, c):
    """Algebraic label for a square, e.g. 'a1'."""
    return "{}{}".format(FILES[c], RANKS[r])


def _top_piece(stack):
    """Return the top piece [owner, type] of a stack, or None if empty."""
    if not stack:
        return None
    return stack[-1]


def _top_type(stack):
    """Return the type code of the top piece, or -1 if empty."""
    if not stack:
        return -1
    return stack[-1][1]


def _top_owner(stack):
    """Return the owner of the top piece, or 0 if empty."""
    if not stack:
        return 0
    return stack[-1][0]


def _is_road_piece(piece, player):
    """True if this piece contributes to roads for player.

    Per §3.1 / §8.1: flat stones and capstones count, standing stones do not.
    """
    return piece[0] == player and piece[1] != STANDING


# ── Road detection ───────────────────────────────────────────────────────────

def _has_road(board, player):
    """Check if player has a road connecting opposite edges (§8.1).

    A road connects West(col=0) to East(col=5) or South(row=0) to North(row=5).
    Only flat stones and capstones count. Standing stones do not.
    """
    # Build a set of road-contributing squares
    road_squares = set()
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            stack = board[r][c]
            if stack and _is_road_piece(stack[-1], player):
                road_squares.add((r, c))

    if not road_squares:
        return False

    # BFS: West to East (col 0 to col 5)
    west_starts = [(r, 0) for r in range(BOARD_SIZE) if (r, 0) in road_squares]
    if west_starts:
        visited = set(west_starts)
        queue = deque(west_starts)
        while queue:
            r, c = queue.popleft()
            if c == BOARD_SIZE - 1:
                return True
            for dr, dc in _DIR_DELTAS:
                nr, nc = r + dr, c + dc
                if (nr, nc) in road_squares and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc))

    # BFS: South to North (row 0 to row 5)
    south_starts = [(0, c) for c in range(BOARD_SIZE) if (0, c) in road_squares]
    if south_starts:
        visited = set(south_starts)
        queue = deque(south_starts)
        while queue:
            r, c = queue.popleft()
            if r == BOARD_SIZE - 1:
                return True
            for dr, dc in _DIR_DELTAS:
                nr, nc = r + dr, c + dc
                if (nr, nc) in road_squares and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc))

    return False


# ── Move generation helpers ──────────────────────────────────────────────────

def _gen_drop_sequences(board, r, c, dr, dc, carried, drops_so_far, results):
    """Recursively enumerate valid drop sequences for a move (§6.4-6.5, §7).

    carried: list of pieces [owner, type] from bottom to top of the carried bundle.
    Each step must drop >= 1 piece from the bottom of the carried bundle.
    """
    nr, nc = r + dr, c + dc
    if not _in_bounds(nr, nc):
        return

    stack = board[nr][nc]
    remaining = len(carried)

    if stack:
        top_t = stack[-1][1]
        if top_t == CAPSTONE:
            # Absolute block — cannot enter (§6.5, §7)
            return
        if top_t == STANDING:
            # Can only enter via capstone flatten (§7):
            # capstone must be the sole piece dropped, on the final step
            if remaining == 1 and carried[0][1] == CAPSTONE:
                results.append(drops_so_far + [1])
            return

    # Square is empty or flat-topped — can drop 1..remaining pieces
    for drop in range(1, remaining + 1):
        new_carried = carried[drop:]
        new_drops = drops_so_far + [drop]
        if not new_carried:
            # All pieces dropped — move complete
            results.append(new_drops)
        else:
            # Continue to next square
            _gen_drop_sequences(board, nr, nc, dr, dc, new_carried,
                                new_drops, results)


# ── Flat count ───────────────────────────────────────────────────────────────

def _count_flats(board):
    """Count flat stones on top of each stack for flat-win scoring (§8.3).

    Returns (white_flats, black_flats).
    """
    w, b = 0, 0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            stack = board[r][c]
            if stack and stack[-1][1] == FLAT:
                if stack[-1][0] == WHITE:
                    w += 1
                else:
                    b += 1
    return w, b


# ── Evaluation helpers ──────────────────────────────────────────────────────

_SQ_VALUE = (
    (2, 3, 3, 3, 3, 2),
    (3, 4, 4, 4, 4, 3),
    (3, 4, 4, 4, 4, 3),
    (3, 4, 4, 4, 4, 3),
    (3, 4, 4, 4, 4, 3),
    (2, 3, 3, 3, 3, 2),
)


def _analyze_road_components(road_set):
    """Find connected components of road-eligible squares and detect roads.

    Returns (components, has_road). Each component is:
        (square_set, (north, south, east, west), row_span, col_span)
    """
    if not road_set:
        return [], False
    visited = set()
    components = []
    has_road = False
    for start in road_set:
        if start in visited:
            continue
        comp = {start}
        queue = deque([start])
        tn = ts = te = tw = False
        rows = set()
        cols = set()
        while queue:
            r, c = queue.popleft()
            rows.add(r)
            cols.add(c)
            if r == 5: tn = True
            if r == 0: ts = True
            if c == 5: te = True
            if c == 0: tw = True
            for dr, dc in _DIR_DELTAS:
                nr, nc = r + dr, c + dc
                if (nr, nc) in road_set and (nr, nc) not in comp:
                    comp.add((nr, nc))
                    queue.append((nr, nc))
        visited |= comp
        if (tn and ts) or (te and tw):
            has_road = True
        components.append((comp, (tn, ts, te, tw), len(rows), len(cols)))
    return components, has_road


def _placement_threat_count(components, empty_squares):
    """Count empty squares where placing a flat would complete a road."""
    if not components:
        return 0
    sq_to_comp = {}
    for i, (comp_set, _, _, _) in enumerate(components):
        for sq in comp_set:
            sq_to_comp[sq] = i
    count = 0
    for er, ec in empty_squares:
        has_n = (er == 5)
        has_s = (er == 0)
        has_e = (ec == 5)
        has_w = (ec == 0)
        seen = set()
        for dr, dc in _DIR_DELTAS:
            nr, nc = er + dr, ec + dc
            ci = sq_to_comp.get((nr, nc))
            if ci is not None and ci not in seen:
                seen.add(ci)
                cn, cs, ce, cw = components[ci][1]
                has_n |= cn
                has_s |= cs
                has_e |= ce
                has_w |= cw
        if (has_n and has_s) or (has_e and has_w):
            count += 1
    return count


def _component_span_score(components):
    """Score road potential from connected component spans.

    Quadratic scaling for row/col coverage plus edge-touch bonuses.
    """
    score = 0.0
    for _, (n, s, e, w), row_span, col_span in components:
        ns = row_span * row_span
        ew = col_span * col_span
        if n and s:
            ns += 100
        elif n or s:
            ns += 10
        if e and w:
            ew += 100
        elif e or w:
            ew += 10
        score += max(ns, ew)
    return score


# ── Game class ───────────────────────────────────────────────────────────────

class TakLogic(AbstractBoardGame):
    """Tak 6x6 game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":       [[[int,int], ...], ...],  # 6x6 grid of stacks
            "turn":        int,                      # WHITE (1) or BLACK (2)
            "turn_number": int,                      # starts at 1
            "reserves":    {"1": {"stones": int, "capstones": int},
                            "2": {"stones": int, "capstones": int}},
            "game_over":   bool,
            "winner":      int or None,
            "win_type":    str or None,  # "road" / "flat" / "draw"
        }

    A move is a dict:
      Place: {"action": "place", "row": r, "col": c, "piece": "flat"|"standing"|"capstone"}
      Move:  {"action": "move", "row": r, "col": c, "direction": d, "drops": [d1, ...]}
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Tak"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [[[] for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        return {
            "board": board,
            "turn": WHITE,
            "turn_number": 1,
            "reserves": {
                "1": {"stones": INITIAL_STONES, "capstones": INITIAL_CAPSTONES},
                "2": {"stones": INITIAL_STONES, "capstones": INITIAL_CAPSTONES},
            },
            "game_over": False,
            "winner": None,
            "win_type": None,
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        if state["game_over"]:
            return []

        board = state["board"]
        turn_number = state["turn_number"]
        moves = []

        if turn_number <= 2:
            # Opening protocol (§4.1): place opponent's flat stone on any empty
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if not board[r][c]:
                        moves.append({
                            "action": "place", "row": r, "col": c,
                            "piece": "flat",
                        })
            return moves

        # Normal turns (§4.2): placement + movement
        p_key = str(player)
        reserves = state["reserves"][p_key]

        # Placement moves (§5)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if not board[r][c]:
                    if reserves["stones"] > 0:
                        moves.append({
                            "action": "place", "row": r, "col": c,
                            "piece": "flat",
                        })
                        moves.append({
                            "action": "place", "row": r, "col": c,
                            "piece": "standing",
                        })
                    if reserves["capstones"] > 0:
                        moves.append({
                            "action": "place", "row": r, "col": c,
                            "piece": "capstone",
                        })

        # Movement moves (§6)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                stack = board[r][c]
                if not stack or stack[-1][0] != player:
                    continue  # Not controlled by this player (§6.1)
                max_carry = min(len(stack), CARRY_LIMIT)
                for carry in range(1, max_carry + 1):
                    carried = stack[-carry:]  # bottom-to-top of carried bundle
                    for direction in range(4):
                        dr, dc = _DIR_DELTAS[direction]
                        drop_sequences = []
                        _gen_drop_sequences(board, r, c, dr, dc,
                                            list(carried), [], drop_sequences)
                        for drops in drop_sequences:
                            moves.append({
                                "action": "move",
                                "row": r, "col": c,
                                "direction": direction,
                                "drops": drops,
                            })

        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)
        board = new["board"]
        turn_number = new["turn_number"]

        if move["action"] == "place":
            r, c = move["row"], move["col"]
            piece_name = move["piece"]

            if turn_number <= 2:
                # Opening protocol (§4.1): place opponent's flat stone
                opponent = BLACK if player == WHITE else WHITE
                board[r][c].append([opponent, FLAT])
                new["reserves"][str(opponent)]["stones"] -= 1
            else:
                # Normal placement (§5)
                type_code = {"flat": FLAT, "standing": STANDING,
                             "capstone": CAPSTONE}[piece_name]
                board[r][c].append([player, type_code])
                p_key = str(player)
                if type_code == CAPSTONE:
                    new["reserves"][p_key]["capstones"] -= 1
                else:
                    new["reserves"][p_key]["stones"] -= 1

        elif move["action"] == "move":
            r, c = move["row"], move["col"]
            drops = move["drops"]
            carry = sum(drops)
            direction = move["direction"]
            dr, dc = _DIR_DELTAS[direction]

            # Lift pieces from top of stack (§6.2)
            carried = board[r][c][-carry:]
            board[r][c] = board[r][c][:-carry]

            # Drop sequence (§6.4)
            cr, cc = r, c
            for d in drops:
                cr += dr
                cc += dc
                dropping = carried[:d]
                carried = carried[d:]

                # Capstone flatten (§7): if top of destination is standing
                dest = board[cr][cc]
                if dest and dest[-1][1] == STANDING:
                    dest[-1] = [dest[-1][0], FLAT]

                dest.extend(dropping)

        # Advance turn
        new["turn"] = BLACK if player == WHITE else WHITE
        new["turn_number"] = turn_number + 1

        # Check game end (§8)
        self._check_game_end(new, player)

        return new

    def _get_game_status(self, state):
        if state["game_over"]:
            w = state["winner"]
            if w is not None:
                return {"is_over": True, "winner": w, "is_draw": False}
            return {"is_over": True, "winner": None, "is_draw": True}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Game-end evaluation (§8) ─────────────────────────────────────────

    def _check_game_end(self, state, active_player):
        """Evaluate game-end conditions after active_player's move.

        Modifies state in-place (only called on the deepcopy in _apply_move).
        """
        board = state["board"]
        inactive = BLACK if active_player == WHITE else WHITE

        # §8.1: Road win (primary) — check active first, then inactive
        active_road = _has_road(board, active_player)
        inactive_road = _has_road(board, inactive)

        if active_road or inactive_road:
            if active_road:
                # §8.1.3: Double road → active wins; or just active road
                state["game_over"] = True
                state["winner"] = active_player
                state["win_type"] = "road"
            else:
                # Only inactive has road
                state["game_over"] = True
                state["winner"] = inactive
                state["win_type"] = "road"
            return

        # §8.2: Terminal conditions — board full or either reserve exhausted
        board_full = True
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if not board[r][c]:
                    board_full = False
                    break
            if not board_full:
                break

        reserve_empty = False
        for p_key in ("1", "2"):
            res = state["reserves"][p_key]
            if res["stones"] == 0 and res["capstones"] == 0:
                reserve_empty = True
                break

        if board_full or reserve_empty:
            # §8.3: Flat win / draw
            w_flats, b_flats = _count_flats(board)
            state["game_over"] = True
            if w_flats > b_flats:
                state["winner"] = WHITE
                state["win_type"] = "flat"
            elif b_flats > w_flats:
                state["winner"] = BLACK
                state["win_type"] = "flat"
            else:
                state["winner"] = None
                state["win_type"] = "draw"

    # ── Position evaluation for bot ───────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate position from player's perspective. Returns float in [0, 1]."""
        if state["game_over"]:
            w = state["winner"]
            return 1.0 if w == player else (0.0 if w is not None else 0.5)

        board = state["board"]
        opp = 3 - player

        # ── Single board scan ──────────────────────────────────────────
        p_road = set()
        o_road = set()
        p_flats = o_flats = 0
        p_ctrl = o_ctrl = 0
        p_walls = o_walls = 0
        p_cap = o_cap = None
        p_pos = o_pos = 0
        p_hard = p_soft = 0
        o_hard = o_soft = 0
        p_captive = o_captive = 0
        p_over = o_over = 0
        empty_count = 0
        empty_list = []

        for r in range(BOARD_SIZE):
            brow = board[r]
            for c in range(BOARD_SIZE):
                stk = brow[c]
                if not stk:
                    empty_count += 1
                    empty_list.append((r, c))
                    continue

                top_o = stk[-1][0]
                top_t = stk[-1][1]
                h = len(stk)
                sv = _SQ_VALUE[r][c]
                is_p = (top_o == player)

                if is_p:
                    p_ctrl += 1
                    if top_t == FLAT:
                        p_flats += 1
                        p_road.add((r, c))
                        p_pos += sv
                    elif top_t == CAPSTONE:
                        p_road.add((r, c))
                        p_cap = (r, c)
                        p_pos += sv
                    else:
                        p_walls += 1
                    if h > 1:
                        own = 0
                        opp_f = 0
                        for pc in stk:
                            if pc[0] == player:
                                own += 1
                            elif pc[1] == FLAT:
                                opp_f += 1
                        p_captive += opp_f
                        if own * 2 >= h:
                            p_hard += h
                        else:
                            p_soft += h
                        if h > CARRY_LIMIT:
                            p_over += h - CARRY_LIMIT
                else:
                    o_ctrl += 1
                    if top_t == FLAT:
                        o_flats += 1
                        o_road.add((r, c))
                        o_pos += sv
                    elif top_t == CAPSTONE:
                        o_road.add((r, c))
                        o_cap = (r, c)
                        o_pos += sv
                    else:
                        o_walls += 1
                    if h > 1:
                        own = 0
                        our_f = 0
                        for pc in stk:
                            if pc[0] == opp:
                                own += 1
                            elif pc[1] == FLAT:
                                our_f += 1
                        o_captive += our_f
                        if own * 2 >= h:
                            o_hard += h
                        else:
                            o_soft += h
                        if h > CARRY_LIMIT:
                            o_over += h - CARRY_LIMIT

        # ── Road analysis ──────────────────────────────────────────────
        p_comps, p_has_road = _analyze_road_components(p_road)
        o_comps, o_has_road = _analyze_road_components(o_road)

        if p_has_road:
            return 1.0
        if o_has_road:
            return 0.0

        # ── Phase detection ────────────────────────────────────────────
        density = (36 - empty_count) / 36.0
        res_p = state["reserves"][str(player)]
        res_o = state["reserves"][str(opp)]
        r_p = res_p["stones"] + res_p["capstones"]
        r_o = res_o["stones"] + res_o["capstones"]
        r_min = min(r_p, r_o)
        endgame_factor = max(0, 7 - min(r_min, 7)) / 7.0

        # ── Tier 1: Placement threats ──────────────────────────────────
        p_threats = _placement_threat_count(p_comps, empty_list)
        o_threats = _placement_threat_count(o_comps, empty_list)

        threat_score = 0
        if p_threats >= 2:
            threat_score += 80000
        elif p_threats == 1:
            threat_score += 5000
        if o_threats >= 2:
            threat_score -= 80000
        elif o_threats == 1:
            threat_score -= 5000

        # ── Tier 2: Road race ──────────────────────────────────────────
        road_score = _component_span_score(p_comps) - _component_span_score(o_comps)

        # ── Tier 3: Flat count ─────────────────────────────────────────
        flat_diff = p_flats - o_flats

        # ── Tier 4: Control & stacks ───────────────────────────────────
        ctrl_diff = p_ctrl - o_ctrl
        stack_q = (p_hard - p_soft) - (o_hard - o_soft)
        fpfcd = o_captive - p_captive
        over_diff = p_over - o_over

        # Capstone evaluation
        cap_score = 0.0
        for cp, owner, other in ((p_cap, player, opp), (o_cap, opp, player)):
            if cp is None:
                continue
            cr, cc = cp
            val = (3.0 - (abs(cr - 2.5) + abs(cc - 2.5))) * 30
            stk = board[cr][cc]
            if len(stk) >= 2:
                if stk[-2][0] == owner:
                    val += 200
                else:
                    val += 50
                if len(stk) > 4:
                    val -= (len(stk) - 4) * 30
            if owner == player:
                cap_score += val
            else:
                cap_score -= val

        # Liberties: empty squares adjacent to road-eligible pieces
        p_libs = set()
        o_libs = set()
        for er, ec in empty_list:
            for dr, dc in _DIR_DELTAS:
                nr, nc = er + dr, ec + dc
                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                    if (nr, nc) in p_road:
                        p_libs.add((er, ec))
                    if (nr, nc) in o_road:
                        o_libs.add((er, ec))
        lib_diff = len(p_libs) - len(o_libs)

        # Wall scoring: own walls penalized, opponent walls cost them flats
        wall_score = -p_walls * 15 + o_walls * 10

        # ── Tier 5: Positional ─────────────────────────────────────────
        pos_diff = p_pos - o_pos

        # ── End-trigger pressure ───────────────────────────────────────
        end_dist = min(empty_count, min(r_p, r_o))
        end_pressure = 0
        if end_dist <= 5:
            if flat_diff > 0:
                end_pressure = (6 - end_dist) * 80
            elif flat_diff < 0:
                end_pressure = -(6 - end_dist) * 80

        # ── Phase-weighted combination ─────────────────────────────────
        # Weights: (road, flat, ctrl, pos, stack, lib, wall, fpfcd, over)
        if density < 0.33:
            w = (2000, 400, 200, 80, 30, 40, 10, 10, -15)
        elif density < 0.75 and r_min >= 8:
            w = (5000, 500, 150, 50, 80, 30, 20, 15, -20)
        else:
            w = (5000, 500, 100, 30, 50, 20, 50, 10, -25)

        flat_w = w[1] * (1.0 + endgame_factor * 4.0)

        score = (
            threat_score
            + road_score * w[0] / 100.0
            + flat_diff * flat_w
            + ctrl_diff * w[2]
            + pos_diff * w[3]
            + stack_q * w[4]
            + lib_diff * w[5]
            + wall_score * w[6] / 10.0
            + fpfcd * w[7]
            + over_diff * w[8]
            + cap_score
            + end_pressure
        )

        # ── Sigmoid normalization to [0.0, 1.0] ───────────────────────
        try:
            return 1.0 / (1.0 + math.exp(-score / 3000.0))
        except OverflowError:
            return 0.0 if score < 0 else 1.0

    # ── Efficient move validation override ───────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without full legal move enumeration."""
        if state["game_over"]:
            return False
        if not isinstance(move, dict):
            return False
        action = move.get("action")
        if action not in ("place", "move"):
            return False

        board = state["board"]
        turn_number = state["turn_number"]

        if action == "place":
            r = move.get("row")
            c = move.get("col")
            piece = move.get("piece")
            if not isinstance(r, int) or not isinstance(c, int):
                return False
            if not _in_bounds(r, c):
                return False
            if board[r][c]:
                return False  # Not empty
            if piece not in ("flat", "standing", "capstone"):
                return False

            if turn_number <= 2:
                # Opening: only flat allowed
                return piece == "flat"

            # Normal: check reserves
            p_key = str(player)
            res = state["reserves"][p_key]
            if piece == "capstone":
                return res["capstones"] > 0
            return res["stones"] > 0

        # action == "move"
        r = move.get("row")
        c = move.get("col")
        direction = move.get("direction")
        drops = move.get("drops")

        if not isinstance(r, int) or not isinstance(c, int):
            return False
        if not _in_bounds(r, c):
            return False
        if not isinstance(direction, int) or direction not in (0, 1, 2, 3):
            return False
        if not isinstance(drops, list) or not drops:
            return False

        # Opening turns: movement not allowed
        if turn_number <= 2:
            return False

        stack = board[r][c]
        if not stack or stack[-1][0] != player:
            return False  # Not controlled

        carry = sum(drops)
        if carry < 1 or carry > min(len(stack), CARRY_LIMIT):
            return False
        if any(not isinstance(d, int) or d < 1 for d in drops):
            return False

        # Simulate the drop sequence
        carried = stack[-carry:]
        dr, dc = _DIR_DELTAS[direction]
        cr, cc = r, c
        for i, d in enumerate(drops):
            cr += dr
            cc += dc
            if not _in_bounds(cr, cc):
                return False
            dest = board[cr][cc]
            if dest:
                top_t = dest[-1][1]
                if top_t == CAPSTONE:
                    return False  # Absolute block
                if top_t == STANDING:
                    # Capstone flatten: must be last drop, sole piece, and capstone
                    is_last = (i == len(drops) - 1)
                    piece_being_dropped = carried[:d]
                    if not (is_last and d == 1
                            and piece_being_dropped[0][1] == CAPSTONE):
                        return False
            carried = carried[d:]

        return True

    # ── Extra helpers for display / tests ─────────────────────────────────

    def get_flat_counts(self, state):
        """Return (white_flats, black_flats) for display."""
        return _count_flats(state["board"])
