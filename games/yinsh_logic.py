"""
YINSH -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for YINSH,
an abstract strategy game on an 85-intersection hexagonal board.

Each player places 5 rings, then takes turns moving rings along grid lines,
leaving markers behind and flipping jumped markers.  Forming a row of 5
same-colour markers lets you remove that row plus one of your own rings.
First player to remove 3 rings wins.

Move representations (all JSON-safe)::

    Placement phase:
        {"type": "place_ring", "pos": [q, r]}

    Main phase (no row formed):
        {"type": "move", "ring": [q, r], "dest": [q, r]}

    Main phase (row(s) formed for the active player):
        {"type": "move", "ring": [q, r], "dest": [q, r],
         "remove_sequences": [
             {"row": [[q,r], ...5 positions...], "ring": [q, r]},
             ...  (if multiple rows must be resolved)
         ]}

    Main phase (opponent also has rows to resolve after the active player):
        {"type": "move", "ring": [q, r], "dest": [q, r],
         "remove_sequences": [...],
         "opp_remove_sequences": [
             {"row": [[q,r], ...5 positions...], "ring": [q, r]},
             ...
         ]}
"""

import copy
import math

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

# Player identifiers
WHITE = 1
BLACK = 2

# Game phases (replacing Phase enum)
PHASE_PLACEMENT = "placement"
PHASE_MAIN = "main"

# Sub-states (replacing St enum)
ST_PLACE_RING = "place_ring"
ST_SELECT_RING = "select_ring"
ST_MOVE_RING = "move_ring"
ST_CHOOSE_ROW = "choose_row"
ST_REMOVE_RING = "remove_ring"
ST_GAME_OVER = "game_over"

# Hex directions (axial coordinates)
DIRECTIONS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, -1], [-1, 1]]

SQRT3_2 = math.sqrt(3) / 2.0

# ── Board geometry ───────────────────────────────────────────────────────────

def _make_valid_positions():
    """Build the list of all 85 valid board intersections.

    The YINSH board is a hexagonal grid with axial coords (q, r),
    excluding the 6 corner positions.
    """
    corners = [[5, 0], [-5, 0], [0, 5], [0, -5], [5, -5], [-5, 5]]
    corner_set = {}
    for c in corners:
        corner_set[_key(c[0], c[1])] = True

    positions = []
    for q in range(-5, 6):
        for r in range(-5, 6):
            if max(abs(q), abs(r), abs(q + r)) <= 5:
                if _key(q, r) not in corner_set:
                    positions.append([q, r])
    return positions


def _key(q, r):
    """Convert axial coords to a string key for dict storage."""
    return str(q) + "," + str(r)


def _from_key(k):
    """Convert string key back to [q, r] list."""
    parts = k.split(",")
    return [int(parts[0]), int(parts[1])]


VALID_POSITIONS = _make_valid_positions()
VALID_SET = {}
for _p in VALID_POSITIONS:
    VALID_SET[_key(_p[0], _p[1])] = True
assert len(VALID_SET) == 85


def _make_board_lines():
    """Maximal collinear sequences along each axis (length >= 2).

    Used for 5-in-a-row detection.  Returns list of lists of [q, r].
    """
    lines = []
    for d in [[1, 0], [0, 1], [1, -1]]:
        dq, dr = d[0], d[1]
        seen = {}
        for pos in VALID_POSITIONS:
            pk = _key(pos[0], pos[1])
            if pk in seen:
                continue
            q, r = pos[0], pos[1]
            # walk to start of line
            while _key(q - dq, r - dr) in VALID_SET:
                q -= dq
                r -= dr
            line = []
            while _key(q, r) in VALID_SET:
                line.append([q, r])
                seen[_key(q, r)] = True
                q += dq
                r += dr
            if len(line) >= 2:
                lines.append(line)
    return lines


BOARD_LINES = _make_board_lines()


# ── Pure helper functions ────────────────────────────────────────────────────

def _opp(player):
    """Return the opposing player."""
    return BLACK if player == WHITE else WHITE


def _color_str(player):
    """Return 'W' or 'B' for display purposes."""
    return "W" if player == WHITE else "B"


def is_valid_pos(q, r):
    """Check whether (q, r) is a valid board intersection."""
    return _key(q, r) in VALID_SET


def _vacant(rings, markers, q, r):
    """Check whether position (q, r) is a valid, unoccupied intersection."""
    k = _key(q, r)
    return k in VALID_SET and k not in rings and k not in markers


def compute_destinations(rings, markers, rq, rr):
    """Compute all valid destinations for a ring at (rq, rr).

    A ring moves along a straight line.  It may pass over (jump) one or more
    contiguous markers, but must land on the first empty space after jumping.
    It cannot pass over or land on another ring.

    Returns a list of [q, r] destination positions.
    """
    out = []
    for d in DIRECTIONS:
        dq, dr = d[0], d[1]
        cq, cr = rq + dq, rr + dr
        jumped = False
        while _key(cq, cr) in VALID_SET:
            ck = _key(cq, cr)
            if ck in rings:
                break
            if ck in markers:
                jumped = True
                cq += dq
                cr += dr
                continue
            out.append([cq, cr])
            if jumped:
                break
            cq += dq
            cr += dr
    return out


def compute_jumped(sq, sr, eq, er):
    """Return the positions of markers between start and end that get flipped.

    The ring has already been removed from start and placed at end.
    We just enumerate positions along the line between start and end.
    Returns list of [q, r] for positions that had markers (caller checks).
    """
    dq = eq - sq
    dr = er - sr
    n = max(abs(dq), abs(dr), abs(dq + dr))
    if n == 0:
        return []
    step_q = dq // n
    step_r = dr // n
    result = []
    cq, cr = sq + step_q, sr + step_r
    while cq != eq or cr != er:
        result.append([cq, cr])
        cq += step_q
        cr += step_r
    return result


def find_rows(markers, player):
    """Find all candidate rows of 5 same-colour markers for the given player.

    Returns a list of rows, where each row is a list of 5 [q, r] positions.
    Rows are de-duplicated.
    """
    cands = []
    for line in BOARD_LINES:
        run = []
        for pos in line:
            k = _key(pos[0], pos[1])
            if k in markers and markers[k] == player:
                run.append([pos[0], pos[1]])
            else:
                _extract_rows(run, cands)
                run = []
        _extract_rows(run, cands)
    # De-duplicate
    seen = {}
    unique = []
    for row in cands:
        # Sort positions for a canonical key
        sorted_row = sorted(row, key=lambda p: (p[0], p[1]))
        rk = str(sorted_row)
        if rk not in seen:
            seen[rk] = True
            unique.append(row)
    return unique


def _extract_rows(run, out):
    """Extract all length-5 windows from a contiguous run of markers."""
    if len(run) >= 5:
        for i in range(len(run) - 4):
            out.append(run[i:i + 5])


def clabel(q, r):
    """Coordinate label, e.g. 'F6'."""
    return chr(65 + q + 5) + str(r + 6)


# ── Game class ───────────────────────────────────────────────────────────────

class YinshLogic(AbstractBoardGame):
    """YINSH game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "rings":    {"q,r": int, ...},  # position -> player (1 or 2)
            "markers":  {"q,r": int, ...},  # position -> player (1 or 2)
            "pool":     int,                # markers remaining in pool (starts 51)
            "removed":  {"1": int, "2": int},  # rings removed per player
            "placed":   {"1": int, "2": int},  # rings placed per player
            "turn":     int,                # WHTE (1) or BLACK (2)
            "phase":    str,                # "placement" or "main"
            "sub_state": str,               # current sub-state
            "winner":   int or None,        # 1, 2, or None (null = "draw" handled via is_draw)
            "is_draw":  bool                # True if game ended in draw
        }
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "YINSH"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        return {
            "rings": {},
            "markers": {},
            "pool": 51,
            "removed": {"1": 0, "2": 0},
            "placed": {"1": 0, "2": 0},
            "turn": WHITE,
            "phase": PHASE_PLACEMENT,
            "sub_state": ST_PLACE_RING,
            "winner": None,
            "is_draw": False,
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        phase = state["phase"]
        sub = state["sub_state"]

        if sub == ST_GAME_OVER:
            return []

        if phase == PHASE_PLACEMENT and sub == ST_PLACE_RING:
            return self._legal_placement_moves(state, player)
        elif phase == PHASE_MAIN and sub == ST_SELECT_RING:
            return self._legal_main_moves(state, player)
        else:
            return []

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)

        if move["type"] == "place_ring":
            return self._apply_placement(new, player, move)
        elif move["type"] == "move":
            return self._apply_main_move(new, player, move)
        else:
            return new

    def _get_game_status(self, state):
        if state["sub_state"] == ST_GAME_OVER:
            if state["is_draw"]:
                return {"is_over": True, "winner": None, "is_draw": True}
            else:
                return {"is_over": True, "winner": state["winner"], "is_draw": False}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Efficient move validation override ───────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a move without generating all legal moves."""
        if not isinstance(move, dict):
            return False
        move_type = move.get("type")
        if move_type is None:
            return False

        phase = state["phase"]
        sub = state["sub_state"]

        if sub == ST_GAME_OVER:
            return False

        if move_type == "place_ring":
            if phase != PHASE_PLACEMENT or sub != ST_PLACE_RING:
                return False
            pos = move.get("pos")
            if not isinstance(pos, list) or len(pos) != 2:
                return False
            q, r = pos[0], pos[1]
            if not isinstance(q, int) or not isinstance(r, int):
                return False
            return _vacant(state["rings"], state["markers"], q, r)

        elif move_type == "move":
            if phase != PHASE_MAIN or sub != ST_SELECT_RING:
                return False
            ring = move.get("ring")
            dest = move.get("dest")
            if not isinstance(ring, list) or len(ring) != 2:
                return False
            if not isinstance(dest, list) or len(dest) != 2:
                return False
            rq, rr = ring[0], ring[1]
            dq, dr = dest[0], dest[1]
            if not isinstance(rq, int) or not isinstance(rr, int):
                return False
            if not isinstance(dq, int) or not isinstance(dr, int):
                return False

            rk = _key(rq, rr)
            if rk not in state["rings"] or state["rings"][rk] != player:
                return False

            dests = compute_destinations(state["rings"], state["markers"], rq, rr)
            if [dq, dr] not in dests:
                return False

            # Simulate the move to check row removal sequences
            return self._validate_removal_sequences(state, player, move)

        return False

    # ── Placement logic ──────────────────────────────────────────────────

    def _legal_placement_moves(self, state, player):
        moves = []
        rings = state["rings"]
        markers = state["markers"]
        for pos in VALID_POSITIONS:
            q, r = pos[0], pos[1]
            if _vacant(rings, markers, q, r):
                moves.append({"type": "place_ring", "pos": [q, r]})
        return moves

    def _apply_placement(self, new, player, move):
        q, r = move["pos"][0], move["pos"][1]
        k = _key(q, r)
        new["rings"][k] = player
        new["placed"][str(player)] += 1

        total_placed = new["placed"]["1"] + new["placed"]["2"]
        if total_placed >= 10:
            new["phase"] = PHASE_MAIN
            new["turn"] = WHITE
            new["sub_state"] = ST_SELECT_RING
            self._check_turn_start(new)
        else:
            new["turn"] = _opp(player)
        return new

    # ── Main move logic ──────────────────────────────────────────────────

    def _legal_main_moves(self, state, player):
        """Generate all legal main-phase moves.

        Each move is an atomic dict that includes the ring move and
        all required row removal + ring removal actions.
        """
        rings = state["rings"]
        markers = state["markers"]

        # Find all rings belonging to the current player
        player_rings = []
        for k, v in rings.items():
            if v == player:
                player_rings.append(_from_key(k))

        moves = []
        for rpos in player_rings:
            rq, rr = rpos[0], rpos[1]
            dests = compute_destinations(rings, markers, rq, rr)
            for dest in dests:
                # Simulate the move to find rows
                base_moves = self._generate_moves_for_dest(
                    state, player, rq, rr, dest[0], dest[1]
                )
                moves.extend(base_moves)
        return moves

    def _generate_moves_for_dest(self, state, player, rq, rr, dq, dr):
        """Generate all possible atomic moves for moving ring from (rq,rr) to (dq,dr).

        This includes all combinations of row removal and ring removal
        for both the active player and the opponent.
        """
        # Simulate the ring movement
        sim_rings = {}
        for k, v in state["rings"].items():
            sim_rings[k] = v
        sim_markers = {}
        for k, v in state["markers"].items():
            sim_markers[k] = v
        sim_pool = state["pool"]

        origin_k = _key(rq, rr)
        dest_k = _key(dq, dr)

        # Place marker at origin
        sim_markers[origin_k] = player
        sim_pool -= 1

        # Move ring
        del sim_rings[origin_k]
        sim_rings[dest_k] = player

        # Flip jumped markers
        jumped_positions = compute_jumped(rq, rr, dq, dr)
        for jp in jumped_positions:
            jk = _key(jp[0], jp[1])
            if jk in sim_markers:
                sim_markers[jk] = _opp(sim_markers[jk])

        # Find rows for active player
        active_rows = find_rows(sim_markers, player)

        if not active_rows:
            # Check opponent rows
            opp = _opp(player)
            opp_rows = find_rows(sim_markers, opp)
            if not opp_rows:
                return [{"type": "move", "ring": [rq, rr], "dest": [dq, dr]}]
            else:
                # Opponent has rows to resolve
                return self._expand_opp_removals(
                    sim_rings, sim_markers, sim_pool, state, player,
                    rq, rr, dq, dr, opp, opp_rows, []
                )
        else:
            # Active player has rows to resolve
            return self._expand_active_removals(
                sim_rings, sim_markers, sim_pool, state, player,
                rq, rr, dq, dr, active_rows, []
            )

    def _expand_active_removals(self, rings, markers, pool, orig_state,
                                 player, rq, rr, dq, dr, rows, sequences_so_far):
        """Recursively expand all row+ring removal choices for the active player."""
        results = []
        for ri, row in enumerate(rows):
            # For each row choice, pick a ring to remove
            # First apply the row removal
            sim_markers = {}
            for k, v in markers.items():
                sim_markers[k] = v
            sim_pool = pool
            for pos in row:
                pk = _key(pos[0], pos[1])
                if pk in sim_markers:
                    del sim_markers[pk]
                    sim_pool += 1

            # Find rings of this player that can be removed
            player_ring_positions = []
            for k, v in rings.items():
                if v == player:
                    player_ring_positions.append(_from_key(k))

            for ring_pos in player_ring_positions:
                sim_rings = {}
                for k, v in rings.items():
                    sim_rings[k] = v
                rk = _key(ring_pos[0], ring_pos[1])
                del sim_rings[rk]

                new_removed = orig_state["removed"][str(player)]
                new_removed += len(sequences_so_far) + 1

                new_seq = sequences_so_far + [
                    {"row": row, "ring": [ring_pos[0], ring_pos[1]]}
                ]

                if new_removed >= 3:
                    # This player wins - no more removals needed
                    results.append({
                        "type": "move",
                        "ring": [rq, rr],
                        "dest": [dq, dr],
                        "remove_sequences": new_seq,
                    })
                    continue

                # Check for more rows for this player
                more_rows = find_rows(sim_markers, player)
                if more_rows:
                    results.extend(
                        self._expand_active_removals(
                            sim_rings, sim_markers, sim_pool, orig_state,
                            player, rq, rr, dq, dr, more_rows, new_seq
                        )
                    )
                else:
                    # Active player done, check opponent
                    opp = _opp(player)
                    opp_rows = find_rows(sim_markers, opp)
                    if not opp_rows:
                        results.append({
                            "type": "move",
                            "ring": [rq, rr],
                            "dest": [dq, dr],
                            "remove_sequences": new_seq,
                        })
                    else:
                        results.extend(
                            self._expand_opp_removals(
                                sim_rings, sim_markers, sim_pool, orig_state,
                                player, rq, rr, dq, dr, opp, opp_rows, new_seq
                            )
                        )
        return results

    def _expand_opp_removals(self, rings, markers, pool, orig_state,
                              player, rq, rr, dq, dr, opp, rows, active_sequences):
        """Recursively expand all row+ring removal choices for the opponent."""
        results = []
        for ri, row in enumerate(rows):
            sim_markers = {}
            for k, v in markers.items():
                sim_markers[k] = v
            sim_pool = pool
            for pos in row:
                pk = _key(pos[0], pos[1])
                if pk in sim_markers:
                    del sim_markers[pk]
                    sim_pool += 1

            opp_ring_positions = []
            for k, v in rings.items():
                if v == opp:
                    opp_ring_positions.append(_from_key(k))

            for ring_pos in opp_ring_positions:
                sim_rings = {}
                for k, v in rings.items():
                    sim_rings[k] = v
                rk = _key(ring_pos[0], ring_pos[1])
                del sim_rings[rk]

                opp_seq = [{"row": row, "ring": [ring_pos[0], ring_pos[1]]}]

                new_removed = orig_state["removed"][str(opp)] + 1

                if new_removed >= 3:
                    move_dict = {
                        "type": "move",
                        "ring": [rq, rr],
                        "dest": [dq, dr],
                    }
                    if active_sequences:
                        move_dict["remove_sequences"] = active_sequences
                    move_dict["opp_remove_sequences"] = opp_seq
                    results.append(move_dict)
                    continue

                more_rows = find_rows(sim_markers, opp)
                if more_rows:
                    # More opponent rows - expand recursively
                    sub = self._expand_opp_removals_cont(
                        sim_rings, sim_markers, sim_pool, orig_state,
                        player, rq, rr, dq, dr, opp, more_rows,
                        active_sequences, opp_seq
                    )
                    results.extend(sub)
                else:
                    move_dict = {
                        "type": "move",
                        "ring": [rq, rr],
                        "dest": [dq, dr],
                    }
                    if active_sequences:
                        move_dict["remove_sequences"] = active_sequences
                    move_dict["opp_remove_sequences"] = opp_seq
                    results.append(move_dict)
        return results

    def _expand_opp_removals_cont(self, rings, markers, pool, orig_state,
                                    player, rq, rr, dq, dr, opp, rows,
                                    active_sequences, opp_sequences_so_far):
        """Continue expanding opponent row removals."""
        results = []
        for ri, row in enumerate(rows):
            sim_markers = {}
            for k, v in markers.items():
                sim_markers[k] = v
            sim_pool = pool
            for pos in row:
                pk = _key(pos[0], pos[1])
                if pk in sim_markers:
                    del sim_markers[pk]
                    sim_pool += 1

            opp_ring_positions = []
            for k, v in rings.items():
                if v == opp:
                    opp_ring_positions.append(_from_key(k))

            for ring_pos in opp_ring_positions:
                sim_rings = {}
                for k, v in rings.items():
                    sim_rings[k] = v
                rk = _key(ring_pos[0], ring_pos[1])
                del sim_rings[rk]

                new_opp_seq = opp_sequences_so_far + [
                    {"row": row, "ring": [ring_pos[0], ring_pos[1]]}
                ]

                move_dict = {
                    "type": "move",
                    "ring": [rq, rr],
                    "dest": [dq, dr],
                }
                if active_sequences:
                    move_dict["remove_sequences"] = active_sequences
                move_dict["opp_remove_sequences"] = new_opp_seq
                results.append(move_dict)
        return results

    def _validate_removal_sequences(self, state, player, move):
        """Validate that the removal sequences in a move are correct."""
        rq, rr = move["ring"][0], move["ring"][1]
        dq, dr = move["dest"][0], move["dest"][1]

        # Simulate the ring movement
        sim_rings = {}
        for k, v in state["rings"].items():
            sim_rings[k] = v
        sim_markers = {}
        for k, v in state["markers"].items():
            sim_markers[k] = v
        sim_pool = state["pool"]

        origin_k = _key(rq, rr)
        dest_k = _key(dq, dr)

        sim_markers[origin_k] = player
        sim_pool -= 1
        del sim_rings[origin_k]
        sim_rings[dest_k] = player

        jumped_positions = compute_jumped(rq, rr, dq, dr)
        for jp in jumped_positions:
            jk = _key(jp[0], jp[1])
            if jk in sim_markers:
                sim_markers[jk] = _opp(sim_markers[jk])

        # Check active player rows
        active_rows = find_rows(sim_markers, player)
        remove_seqs = move.get("remove_sequences")

        if active_rows:
            if not remove_seqs or not isinstance(remove_seqs, list):
                return False
            # Validate each removal sequence
            for seq in remove_seqs:
                if not isinstance(seq, dict):
                    return False
                row = seq.get("row")
                ring = seq.get("ring")
                if not isinstance(row, list) or len(row) != 5:
                    return False
                if not isinstance(ring, list) or len(ring) != 2:
                    return False
                # Check the row is valid
                row_found = False
                current_rows = find_rows(sim_markers, player)
                for cr in current_rows:
                    if self._rows_equal(cr, row):
                        row_found = True
                        break
                if not row_found:
                    return False
                # Apply removal
                for pos in row:
                    pk = _key(pos[0], pos[1])
                    if pk in sim_markers:
                        del sim_markers[pk]
                        sim_pool += 1
                # Check ring belongs to player
                rk = _key(ring[0], ring[1])
                if rk not in sim_rings or sim_rings[rk] != player:
                    return False
                del sim_rings[rk]
        elif remove_seqs:
            return False

        # Check opponent rows
        opp = _opp(player)
        opp_rows = find_rows(sim_markers, opp)
        opp_seqs = move.get("opp_remove_sequences")

        if opp_rows:
            if not opp_seqs or not isinstance(opp_seqs, list):
                return False
            for seq in opp_seqs:
                if not isinstance(seq, dict):
                    return False
                row = seq.get("row")
                ring = seq.get("ring")
                if not isinstance(row, list) or len(row) != 5:
                    return False
                if not isinstance(ring, list) or len(ring) != 2:
                    return False
                current_rows = find_rows(sim_markers, opp)
                row_found = False
                for cr in current_rows:
                    if self._rows_equal(cr, row):
                        row_found = True
                        break
                if not row_found:
                    return False
                for pos in row:
                    pk = _key(pos[0], pos[1])
                    if pk in sim_markers:
                        del sim_markers[pk]
                        sim_pool += 1
                rk = _key(ring[0], ring[1])
                if rk not in sim_rings or sim_rings[rk] != opp:
                    return False
                del sim_rings[rk]
        elif opp_seqs:
            return False

        return True

    @staticmethod
    def _rows_equal(row_a, row_b):
        """Check if two rows contain the same 5 positions (order-independent)."""
        sa = sorted(row_a, key=lambda p: (p[0], p[1]))
        sb = sorted(row_b, key=lambda p: (p[0], p[1]))
        return sa == sb

    def _apply_main_move(self, new, player, move):
        """Apply a complete main-phase move atomically."""
        rq, rr = move["ring"][0], move["ring"][1]
        dq, dr = move["dest"][0], move["dest"][1]

        origin_k = _key(rq, rr)
        dest_k = _key(dq, dr)

        # Place marker at origin
        new["markers"][origin_k] = player
        new["pool"] -= 1

        # Move ring
        del new["rings"][origin_k]
        new["rings"][dest_k] = player

        # Flip jumped markers
        jumped_positions = compute_jumped(rq, rr, dq, dr)
        for jp in jumped_positions:
            jk = _key(jp[0], jp[1])
            if jk in new["markers"]:
                new["markers"][jk] = _opp(new["markers"][jk])

        # Apply active player's removal sequences
        remove_seqs = move.get("remove_sequences")
        if remove_seqs:
            for seq in remove_seqs:
                for pos in seq["row"]:
                    pk = _key(pos[0], pos[1])
                    if pk in new["markers"]:
                        del new["markers"][pk]
                        new["pool"] += 1
                rk = _key(seq["ring"][0], seq["ring"][1])
                if rk in new["rings"]:
                    del new["rings"][rk]
                new["removed"][str(player)] += 1
                if new["removed"][str(player)] >= 3:
                    new["winner"] = player
                    new["sub_state"] = ST_GAME_OVER
                    return new

        # Apply opponent's removal sequences
        opp = _opp(player)
        opp_seqs = move.get("opp_remove_sequences")
        if opp_seqs:
            for seq in opp_seqs:
                for pos in seq["row"]:
                    pk = _key(pos[0], pos[1])
                    if pk in new["markers"]:
                        del new["markers"][pk]
                        new["pool"] += 1
                rk = _key(seq["ring"][0], seq["ring"][1])
                if rk in new["rings"]:
                    del new["rings"][rk]
                new["removed"][str(opp)] += 1
                if new["removed"][str(opp)] >= 3:
                    new["winner"] = opp
                    new["sub_state"] = ST_GAME_OVER
                    return new

        # End turn
        new["turn"] = _opp(player)
        new["sub_state"] = ST_SELECT_RING
        self._check_turn_start(new)
        return new

    def _check_turn_start(self, state):
        """Check for draw (pool exhausted) or no legal moves at turn start."""
        if state["pool"] <= 0:
            w = state["removed"]["1"]
            b = state["removed"]["2"]
            if w > b:
                state["winner"] = WHITE
            elif b > w:
                state["winner"] = BLACK
            else:
                state["is_draw"] = True
            state["sub_state"] = ST_GAME_OVER
            return

        # Check if current player has any legal moves
        turn = state["turn"]
        has_move = False
        for k, v in state["rings"].items():
            if v == turn:
                pos = _from_key(k)
                dests = compute_destinations(state["rings"], state["markers"], pos[0], pos[1])
                if dests:
                    has_move = True
                    break
        if not has_move:
            # Extremely rare: pass to opponent
            state["turn"] = _opp(turn)

    # ── Extra helpers for display module ─────────────────────────────────

    @staticmethod
    def get_destinations(rings, markers, rq, rr):
        """Compute valid destinations for ring at (rq, rr).

        Returns list of [q, r] positions.
        """
        return compute_destinations(rings, markers, rq, rr)

    @staticmethod
    def get_jumped_positions(sq, sr, eq, er):
        """Get positions between start and end along the line.

        Returns list of [q, r] positions.
        """
        return compute_jumped(sq, sr, eq, er)

    @staticmethod
    def get_rows(markers, player):
        """Find all candidate rows of 5 for the given player.

        Returns list of rows, each row is list of 5 [q, r].
        """
        return find_rows(markers, player)
