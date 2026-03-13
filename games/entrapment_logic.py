"""
Entrapment -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Entrapment,
a two-player abstract strategy board game on a 7x7 grid where players
move roaming pieces on cells and place barriers on edges between cells.

A move is represented as a dict::

    {
        "roamer_from": [r, c],      # source cell (or null if setup/pass)
        "roamer_to":   [r, c],      # destination cell (or null if barrier-only action)
        "barrier":     ["h"|"v", r, c] | null   # barrier action, null if none
    }

During the setup phase, moves are::

    {"setup_place": [r, c]}

During the play phase when the acting player must choose which opponent
roamer to capture (simultaneous entrapment), the move is::

    {"choose_capture": [r, c]}

A full turn in the play phase consists of either one or two actions
(action_num 1 and 2).  Each action submitted through apply_move is one
of the move dicts above.
"""

import copy

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

ROWS, COLS = 7, 7
BARRIERS_PER_PLAYER = 25
DIRS = [[-1, 0], [1, 0], [0, -1], [0, 1]]

PLAYER_NAMES = {1: "Light", 2: "Dark"}
COL_LABELS = "ABCDEFG"


# ── Pure helper functions ────────────────────────────────────────────────────

def _in_bounds(r, c):
    """True if (r, c) is within the board."""
    return 0 <= r < ROWS and 0 <= c < COLS


def _coord_label(r, c):
    """Human-readable label for a cell, e.g. 'A1'."""
    return "{}{}".format(COL_LABELS[c], r + 1)


def _groove_key(r1, c1, r2, c2):
    """Return (type, key_r, key_c) for the groove between two adjacent cells.

    For a horizontal groove (same row, adjacent cols): ("h", r, min(c1,c2))
    For a vertical groove (same col, adjacent rows):   ("v", min(r1,r2), c)
    """
    if r1 == r2:
        return "h", r1, min(c1, c2)
    return "v", min(r1, r2), c1


def _get_barrier(state, r1, c1, r2, c2):
    """Return the barrier value at the groove between two adjacent cells, or None.

    Barrier value is [player, state_str] where state_str is "resting" or "standing".
    Returns None if no barrier is present.
    """
    gt, kr, kc = _groove_key(r1, c1, r2, c2)
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(kr, kc)
    val = barriers.get(key)
    return val


def _set_barrier(state, r1, c1, r2, c2, val):
    """Set or remove a barrier at the groove between two adjacent cells.

    val should be [player, state_str] or None to remove.
    """
    gt, kr, kc = _groove_key(r1, c1, r2, c2)
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(kr, kc)
    if val is None:
        barriers.pop(key, None)
    else:
        barriers[key] = val


def _get_barrier_by_groove(state, gt, gr, gc):
    """Get barrier value by groove type and position."""
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(gr, gc)
    return barriers.get(key)


def _set_barrier_by_groove(state, gt, gr, gc, val):
    """Set or remove a barrier by groove type and position."""
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(gr, gc)
    if val is None:
        barriers.pop(key, None)
    else:
        barriers[key] = val


def _iter_all_grooves(state):
    """Yield [type, r, c, value_or_None] for every groove position."""
    result = []
    for r in range(ROWS):
        for c in range(COLS - 1):
            val = _get_barrier_by_groove(state, "h", r, c)
            result.append(["h", r, c, val])
    for r in range(ROWS - 1):
        for c in range(COLS):
            val = _get_barrier_by_groove(state, "v", r, c)
            result.append(["v", r, c, val])
    return result


def _iter_empty_grooves(state):
    """Return list of [type, r, c] for all empty grooves."""
    result = []
    for gt, r, c, v in _iter_all_grooves(state):
        if v is None:
            result.append([gt, r, c])
    return result


def _iter_player_resting(state, player):
    """Return list of [type, r, c] for a player's resting barriers on the board."""
    result = []
    for gt, r, c, v in _iter_all_grooves(state):
        if v is not None and v[0] == player and v[1] == "resting":
            result.append([gt, r, c])
    return result


# ── Movement validation ─────────────────────────────────────────────────────

def _can_1sq(state, r, c, dr, dc, player):
    """1-square move: groove must be empty, dest must be empty."""
    nr, nc = r + dr, c + dc
    if not _in_bounds(nr, nc):
        return False
    if _get_barrier(state, r, c, nr, nc) is not None:
        return False
    if state["board"][nr][nc] is not None:
        return False
    return True


def _can_slide2(state, r, c, dr, dc, player):
    """Plain 2-sq slide: both grooves empty, intermediate empty, dest empty."""
    mr, mc = r + dr, c + dc
    fr, fc = r + 2 * dr, c + 2 * dc
    if not _in_bounds(fr, fc):
        return False
    if _get_barrier(state, r, c, mr, mc) is not None:
        return False
    if state["board"][mr][mc] is not None:
        return False
    if _get_barrier(state, mr, mc, fr, fc) is not None:
        return False
    if state["board"][fr][fc] is not None:
        return False
    return True


def _can_jump_barrier(state, r, c, dr, dc, player):
    """Jump friendly resting barrier in first groove -> land 2 sq away."""
    mr, mc = r + dr, c + dc
    fr, fc = r + 2 * dr, c + 2 * dc
    if not _in_bounds(fr, fc):
        return False
    b = _get_barrier(state, r, c, mr, mc)
    if b is None or b[0] != player or b[1] != "resting":
        return False
    if state["board"][mr][mc] is not None:
        return False
    if _get_barrier(state, mr, mc, fr, fc) is not None:
        return False
    if state["board"][fr][fc] is not None:
        return False
    return True


def _can_jump_roamer(state, r, c, dr, dc, player):
    """Jump friendly roamer on adjacent sq -> land 2 sq away."""
    mr, mc = r + dr, c + dc
    fr, fc = r + 2 * dr, c + 2 * dc
    if not _in_bounds(fr, fc):
        return False
    if _get_barrier(state, r, c, mr, mc) is not None:
        return False
    if state["board"][mr][mc] != player:
        return False
    if _get_barrier(state, mr, mc, fr, fc) is not None:
        return False
    if state["board"][fr][fc] is not None:
        return False
    return True


def legal_moves_for_roamer(state, r, c, player=None):
    """Return list of [dest_r, dest_c, move_type] for roamer at (r,c).

    Exported for display module use.
    """
    if player is None:
        player = state["board"][r][c]
    if player is None:
        return []
    moves = []
    for d in DIRS:
        dr, dc = d[0], d[1]
        if _can_1sq(state, r, c, dr, dc, player):
            moves.append([r + dr, c + dc, "1sq"])
        if _can_jump_barrier(state, r, c, dr, dc, player):
            moves.append([r + 2 * dr, c + 2 * dc, "jump_barrier"])
        elif _can_jump_roamer(state, r, c, dr, dc, player):
            moves.append([r + 2 * dr, c + 2 * dc, "jump_roamer"])
        elif _can_slide2(state, r, c, dr, dc, player):
            moves.append([r + 2 * dr, c + 2 * dc, "slide2"])
    return moves


def _has_legal_move(state, r, c, player=None):
    return len(legal_moves_for_roamer(state, r, c, player)) > 0


# ── Entrapment / capture logic ──────────────────────────────────────────────

def _is_surrounded(state, r, c):
    """True if every orthogonal side is obstructed (barrier, piece, or edge)."""
    for d in DIRS:
        dr, dc = d[0], d[1]
        nr, nc = r + dr, c + dc
        if not _in_bounds(nr, nc):
            continue  # edge blocks
        if _get_barrier(state, r, c, nr, nc) is not None:
            continue  # barrier blocks
        if state["board"][nr][nc] is not None:
            continue  # piece blocks
        return False  # open side found
    return True


def _can_be_freed(state, r, c, player):
    """Can any adjacent friendly roamer move away to free this piece?

    Temporarily mutates state during computation but restores it.
    """
    board = state["board"]
    for d in DIRS:
        dr, dc = d[0], d[1]
        nr, nc = r + dr, c + dc
        if not _in_bounds(nr, nc):
            continue
        if board[nr][nc] != player:
            continue
        # temporarily remove the neighbour and re-check
        board[nr][nc] = None
        freed = _has_legal_move(state, r, c, player) or not _is_surrounded(state, r, c)
        board[nr][nc] = player
        if freed:
            return True
    return False


def _should_capture(state, r, c, player):
    """True if roamer must be immediately removed (entrapped + un-free-able)."""
    if not _is_surrounded(state, r, c):
        return False
    if _has_legal_move(state, r, c, player):
        return False
    if _can_be_freed(state, r, c, player):
        return False
    return True


def _is_forced(state, r, c, player):
    """Surrounded but NOT captured -- needs mandatory attention."""
    if not _is_surrounded(state, r, c):
        return False
    return not _should_capture(state, r, c, player)


def forced_roamers(state, player):
    """Return list of [r, c] positions that are forced for the given player.

    Exported for display module use.
    """
    result = []
    for pos in state["roamers"][str(player)]:
        if _is_forced(state, pos[0], pos[1], player):
            result.append(pos)
    return result


def _capture(state, player, pos):
    """Remove a roamer from the board. Modifies state in place."""
    r, c = pos[0], pos[1]
    state["board"][r][c] = None
    roamers = state["roamers"][str(player)]
    for i, p in enumerate(roamers):
        if p[0] == r and p[1] == c:
            roamers.pop(i)
            break
    opp = 3 - player  # 1->2, 2->1
    state["captures"][str(opp)] = state["captures"][str(opp)] + 1
    state["log"].append("{} roamer captured at {}!".format(
        PLAYER_NAMES[player], _coord_label(r, c)))


def _process_captures(state, acting_player):
    """Process all captures. Returns list of capturable positions if the acting
    player must choose which opponent roamer to capture (simultaneous entrapment).
    Returns empty list otherwise.
    """
    changed = True
    while changed:
        changed = False
        for player in [3 - acting_player, acting_player]:
            to_cap = []
            for pos in list(state["roamers"][str(player)]):
                if _should_capture(state, pos[0], pos[1], player):
                    to_cap.append(pos)
            if not to_cap:
                continue
            if player != acting_player and len(to_cap) > 1:
                return to_cap  # UI must ask acting player to choose
            for pos in to_cap:
                _capture(state, player, pos)
                changed = True

        # double-force rule: at most 1 forced roamer per player
        for player in [1, 2]:
            fr = forced_roamers(state, player)
            if len(fr) > 1:
                _capture(state, player, fr[-1])
                changed = True
    return []


def _check_winner(state):
    """Check if a player has won. Returns the winner (1 or 2) or None."""
    for p in [1, 2]:
        if state["captures"][str(p)] >= 3:
            return p
    return None


# ── Turn management helpers ─────────────────────────────────────────────────

def selectable_for_action1(state):
    """Which roamers may be selected for the mandatory Action 1 move?

    Exported for display module use.
    """
    p = state["current_player"]
    fr = forced_roamers(state, p)
    if not fr:
        result = []
        for pos in state["roamers"][str(p)]:
            if _has_legal_move(state, pos[0], pos[1], p):
                result.append(pos)
        return result
    fp = fr[0]
    f_r, f_c = fp[0], fp[1]
    ok = []
    seen = []
    if _has_legal_move(state, f_r, f_c, p):
        ok.append([f_r, f_c])
        seen.append([f_r, f_c])
    for d in DIRS:
        dr, dc = d[0], d[1]
        nr, nc = f_r + dr, f_c + dc
        if not _in_bounds(nr, nc) or state["board"][nr][nc] != p:
            continue
        adj = [nr, nc]
        # Check this is actually in the player's roamer list
        found = False
        for rpos in state["roamers"][str(p)]:
            if rpos[0] == nr and rpos[1] == nc:
                found = True
                break
        if not found:
            continue
        if not _has_legal_move(state, nr, nc, p):
            continue
        # does removing this neighbour actually open a side / give a move?
        state["board"][nr][nc] = None
        helps = not _is_surrounded(state, f_r, f_c) or _has_legal_move(state, f_r, f_c, p)
        state["board"][nr][nc] = p
        if helps:
            already = False
            for s in seen:
                if s[0] == nr and s[1] == nc:
                    already = True
                    break
            if not already:
                ok.append(adj)
                seen.append(adj)
    return ok


def selectable_for_action2_move(state):
    """Which roamers may be selected for an Action 2 move?

    Exported for display module use.
    """
    p = state["current_player"]
    fr = forced_roamers(state, p)
    if not fr:
        result = []
        for pos in state["roamers"][str(p)]:
            if _has_legal_move(state, pos[0], pos[1], p):
                result.append(pos)
        return result
    return selectable_for_action1(state)


def can_do_barrier_action(state):
    """Can the current player do any barrier action?

    Exported for display module use.
    """
    p = state["current_player"]
    if state["supply"][str(p)] > 0 and len(_iter_empty_grooves(state)) > 0:
        return True
    if len(_iter_player_resting(state, p)) > 0:
        return True
    return False


def _any_valid_action(state):
    """Can the current player do anything at all this action?"""
    if state["action_num"] == 1:
        return len(selectable_for_action1(state)) > 0
    # action 2
    if len(selectable_for_action2_move(state)) > 0:
        return True
    return can_do_barrier_action(state)


def _refresh_status(state):
    """Update the status message in state."""
    p = PLAYER_NAMES[state["current_player"]]
    if state["phase"] == "setup":
        state["status"] = "{} places a roamer.".format(p)
    elif state["phase"] == "play":
        fr = forced_roamers(state, state["current_player"])
        a = state["action_num"]
        half = " (half-turn)" if state["first_white_turn"] and state["current_player"] == 1 else ""
        if a == 1:
            if fr:
                fl = _coord_label(fr[0][0], fr[0][1])
                state["status"] = "{} | Action 1{} -- Move roamer (forced: {}).".format(p, half, fl)
            else:
                state["status"] = "{} | Action 1{} -- Move a roamer.".format(p, half)
        else:
            state["status"] = "{} | Action 2 -- Move roamer or barrier action.".format(p)


def _advance_turn(state):
    """Advance the turn within the state. Modifies state in place."""
    if state["phase"] != "play":
        return
    if state["action_num"] == 1:
        if state["first_white_turn"] and state["current_player"] == 1:
            state["first_white_turn"] = False
            state["current_player"] = 2
            state["action_num"] = 1
        else:
            state["action_num"] = 2
    else:
        state["current_player"] = 3 - state["current_player"]
        state["action_num"] = 1

    # Edge case: if the (new) player cannot act, skip action 2
    if not _any_valid_action(state) and state["action_num"] == 2:
        state["current_player"] = 3 - state["current_player"]
        state["action_num"] = 1

    _refresh_status(state)


# ── Action execution (on mutable state) ─────────────────────────────────────

def _exec_move(state, r1, c1, r2, c2):
    """Execute a roamer move from (r1,c1) to (r2,c2). Returns True on success."""
    player = state["board"][r1][c1]
    if player is None or player != state["current_player"]:
        return False
    moves = legal_moves_for_roamer(state, r1, c1, player)
    match = [m for m in moves if m[0] == r2 and m[1] == c2]
    if not match:
        return False

    mtype = match[0][2]
    state["board"][r1][c1] = None
    state["board"][r2][c2] = player
    roamers = state["roamers"][str(player)]
    for i, pos in enumerate(roamers):
        if pos[0] == r1 and pos[1] == c1:
            roamers[i] = [r2, c2]
            break

    if mtype == "jump_barrier":
        dr = 1 if r2 > r1 else (-1 if r2 < r1 else 0)
        dc = 1 if c2 > c1 else (-1 if c2 < c1 else 0)
        _set_barrier(state, r1, c1, r1 + dr, c1 + dc, [player, "standing"])

    label = "{} {}->{}".format(
        PLAYER_NAMES[player], _coord_label(r1, c1), _coord_label(r2, c2))
    if "jump" in mtype:
        label += " [jump]"
    state["log"].append(label)
    return True


def _exec_place(state, gt, gr, gc):
    """Place a barrier from supply. Returns True on success."""
    player = state["current_player"]
    if state["supply"][str(player)] <= 0:
        return False
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(gr, gc)
    if key in barriers:
        return False
    barriers[key] = [player, "resting"]
    state["supply"][str(player)] = state["supply"][str(player)] - 1
    state["log"].append("{} places barrier".format(PLAYER_NAMES[player]))
    return True


def _exec_flip(state, gt, gr, gc):
    """Flip a resting barrier to standing. Returns True on success."""
    player = state["current_player"]
    barriers = state["h_barriers"] if gt == "h" else state["v_barriers"]
    key = "{},{}".format(gr, gc)
    v = barriers.get(key)
    if v is None or v[0] != player or v[1] != "resting":
        return False
    barriers[key] = [player, "standing"]
    state["log"].append("{} flips barrier".format(PLAYER_NAMES[player]))
    return True


def _exec_relocate(state, sgt, sr, sc, dgt, dr_, dc_):
    """Relocate a resting barrier to a new empty groove. Returns True on success."""
    player = state["current_player"]
    sd = state["h_barriers"] if sgt == "h" else state["v_barriers"]
    skey = "{},{}".format(sr, sc)
    v = sd.get(skey)
    if v is None or v[0] != player or v[1] != "resting":
        return False
    dd = state["h_barriers"] if dgt == "h" else state["v_barriers"]
    dkey = "{},{}".format(dr_, dc_)
    if dkey in dd:
        return False
    sd.pop(skey)
    dd[dkey] = [player, "resting"]
    state["log"].append("{} relocates barrier".format(PLAYER_NAMES[player]))
    return True


def _after_action(state):
    """Post-action processing: captures, winner check, turn advance.
    Returns the state (possibly with pending_capture_choices set).
    """
    winner = _check_winner(state)
    if winner is not None:
        state["phase"] = "over"
        state["winner"] = winner
        state["status"] = "{} wins the game!".format(PLAYER_NAMES[winner])
        return state

    choices = _process_captures(state, state["current_player"])

    winner = _check_winner(state)
    if winner is not None:
        state["phase"] = "over"
        state["winner"] = winner
        state["status"] = "{} wins the game!".format(PLAYER_NAMES[winner])
        return state

    if choices:
        state["pending_capture_choices"] = [[p[0], p[1]] for p in choices]
        p_name = PLAYER_NAMES[state["current_player"]]
        state["status"] = "{}: Choose which opponent roamer to capture.".format(p_name)
        return state

    _advance_turn(state)
    return state


# ── Game class ───────────────────────────────────────────────────────────────

class EntrapmentLogic(AbstractBoardGame):
    """Entrapment game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":          [[int|null, ...], ...],   # 7x7, values: null/1/2
            "h_barriers":     {"r,c": [player, state], ...},
            "v_barriers":     {"r,c": [player, state], ...},
            "roamers":        {"1": [[r,c], ...], "2": [[r,c], ...]},
            "supply":         {"1": int, "2": int},
            "captures":       {"1": int, "2": int},
            "phase":          str,           # "setup" | "play" | "over"
            "current_player": int,           # 1 or 2
            "setup_count":    int,
            "action_num":     int,           # 1 or 2 within a turn
            "first_white_turn": bool,
            "winner":         int | null,
            "status":         str,
            "log":            [str, ...],
            "pending_capture_choices": [[r,c], ...] | null
        }
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Entrapment"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [[None] * COLS for _ in range(ROWS)]
        return {
            "board": board,
            "h_barriers": {},
            "v_barriers": {},
            "roamers": {"1": [], "2": []},
            "supply": {"1": BARRIERS_PER_PLAYER, "2": BARRIERS_PER_PLAYER},
            "captures": {"1": 0, "2": 0},
            "phase": "setup",
            "current_player": 1,
            "setup_count": 0,
            "action_num": 1,
            "first_white_turn": True,
            "winner": None,
            "status": "Light places a roamer.",
            "log": [],
            "pending_capture_choices": None,
        }

    def _get_current_player(self, state):
        return state["current_player"]

    def _get_legal_moves(self, state, player):
        phase = state["phase"]

        # Setup phase: place roamers on any empty cell
        if phase == "setup":
            moves = []
            for r in range(ROWS):
                for c in range(COLS):
                    if state["board"][r][c] is None:
                        moves.append({"setup_place": [r, c]})
            return moves

        if phase == "over":
            return []

        # Pending capture choice
        if state["pending_capture_choices"] is not None:
            return [{"choose_capture": [p[0], p[1]]}
                    for p in state["pending_capture_choices"]]

        # Play phase
        action_num = state["action_num"]

        if action_num == 1:
            # Action 1: must move a roamer
            return self._legal_roamer_moves(state, action_num)

        # Action 2: can move a roamer OR do a barrier action
        moves = self._legal_roamer_moves(state, action_num)
        moves.extend(self._legal_barrier_moves(state))
        return moves

    def _legal_roamer_moves(self, state, action_num):
        """Generate all legal roamer-move actions."""
        p = state["current_player"]
        if action_num == 1:
            selectable = selectable_for_action1(state)
        else:
            selectable = selectable_for_action2_move(state)

        moves = []
        for sel in selectable:
            sr, sc = sel[0], sel[1]
            dests = legal_moves_for_roamer(state, sr, sc, p)
            for dest in dests:
                dr, dc = dest[0], dest[1]
                moves.append({
                    "roamer_from": [sr, sc],
                    "roamer_to": [dr, dc],
                    "barrier": None,
                })
        return moves

    def _legal_barrier_moves(self, state):
        """Generate all legal barrier actions for action 2."""
        p = state["current_player"]
        moves = []

        # Place from supply
        if state["supply"][str(p)] > 0:
            for grv in _iter_empty_grooves(state):
                moves.append({
                    "roamer_from": None,
                    "roamer_to": None,
                    "barrier": ["place", grv[0], grv[1], grv[2]],
                })

        # Flip resting -> standing
        for grv in _iter_player_resting(state, p):
            moves.append({
                "roamer_from": None,
                "roamer_to": None,
                "barrier": ["flip", grv[0], grv[1], grv[2]],
            })

        # Relocate: pick up resting barrier and place in empty groove
        if state["supply"][str(p)] == 0:
            resting = _iter_player_resting(state, p)
            empties = _iter_empty_grooves(state)
            for src in resting:
                for dst in empties:
                    # Can't relocate to same position
                    if src[0] == dst[0] and src[1] == dst[1] and src[2] == dst[2]:
                        continue
                    moves.append({
                        "roamer_from": None,
                        "roamer_to": None,
                        "barrier": ["relocate", src[0], src[1], src[2],
                                    dst[0], dst[1], dst[2]],
                    })

        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)

        # Setup phase
        if "setup_place" in move:
            r, c = move["setup_place"][0], move["setup_place"][1]
            p = new["current_player"]
            new["board"][r][c] = p
            new["roamers"][str(p)].append([r, c])
            new["log"].append("{} places roamer at {}".format(
                PLAYER_NAMES[p], _coord_label(r, c)))
            new["setup_count"] = new["setup_count"] + 1
            if new["setup_count"] >= 6:
                new["phase"] = "play"
                new["current_player"] = 1
                new["action_num"] = 1
                new["first_white_turn"] = True
            else:
                new["current_player"] = 3 - new["current_player"]
            _refresh_status(new)
            return new

        # Capture choice
        if "choose_capture" in move:
            pos = move["choose_capture"]
            opp = 3 - new["current_player"]
            _capture(new, opp, pos)
            new["pending_capture_choices"] = None
            # Continue resolving captures
            return _after_action(new)

        # Play phase: roamer move or barrier action
        if move["roamer_from"] is not None and move["roamer_to"] is not None:
            r1, c1 = move["roamer_from"][0], move["roamer_from"][1]
            r2, c2 = move["roamer_to"][0], move["roamer_to"][1]
            _exec_move(new, r1, c1, r2, c2)
            return _after_action(new)

        # Barrier action
        barrier = move["barrier"]
        action_type = barrier[0]
        if action_type == "place":
            _exec_place(new, barrier[1], barrier[2], barrier[3])
        elif action_type == "flip":
            _exec_flip(new, barrier[1], barrier[2], barrier[3])
        elif action_type == "relocate":
            _exec_relocate(new, barrier[1], barrier[2], barrier[3],
                           barrier[4], barrier[5], barrier[6])
        return _after_action(new)

    def _get_game_status(self, state):
        if state["phase"] == "over":
            winner = state["winner"]
            return {"is_over": True, "winner": winner, "is_draw": False}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without full enumeration where possible."""
        if not isinstance(move, dict):
            return False

        phase = state["phase"]

        # Setup
        if "setup_place" in move:
            if phase != "setup":
                return False
            pos = move["setup_place"]
            if not isinstance(pos, list) or len(pos) != 2:
                return False
            r, c = pos[0], pos[1]
            if not _in_bounds(r, c):
                return False
            return state["board"][r][c] is None

        # Capture choice
        if "choose_capture" in move:
            if state["pending_capture_choices"] is None:
                return False
            pos = move["choose_capture"]
            if not isinstance(pos, list) or len(pos) != 2:
                return False
            for choice in state["pending_capture_choices"]:
                if choice[0] == pos[0] and choice[1] == pos[1]:
                    return True
            return False

        # Play phase move/barrier
        if phase != "play":
            return False
        if state["pending_capture_choices"] is not None:
            return False

        # Roamer move
        if move.get("roamer_from") is not None and move.get("roamer_to") is not None:
            rf = move["roamer_from"]
            rt = move["roamer_to"]
            if not isinstance(rf, list) or len(rf) != 2:
                return False
            if not isinstance(rt, list) or len(rt) != 2:
                return False
            r1, c1 = rf[0], rf[1]
            r2, c2 = rt[0], rt[1]
            if not _in_bounds(r1, c1) or not _in_bounds(r2, c2):
                return False
            if state["board"][r1][c1] != player:
                return False
            # Check this roamer is selectable
            if state["action_num"] == 1:
                selectable = selectable_for_action1(state)
            else:
                selectable = selectable_for_action2_move(state)
            found = False
            for s in selectable:
                if s[0] == r1 and s[1] == c1:
                    found = True
                    break
            if not found:
                return False
            # Check destination is legal
            dests = legal_moves_for_roamer(state, r1, c1, player)
            for d in dests:
                if d[0] == r2 and d[1] == c2:
                    return True
            return False

        # Barrier action (action 2 only)
        if state["action_num"] != 2:
            return False
        barrier = move.get("barrier")
        if barrier is None or not isinstance(barrier, list) or len(barrier) < 4:
            return False
        # Fall back to full enumeration for barrier moves
        return move in self._get_legal_moves(state, player)
