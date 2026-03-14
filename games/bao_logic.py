"""
Bao la Kiswahili -- Pure game logic (no Pygame).

Implements the AbstractBoardGame contract for Bao la Kiswahili,
a traditional East African abstract strategy board game for two players.

Player 1 = South, Player 2 = North.

A move is represented as a dict::

    {
        "pit_row": "front",
        "pit_idx": 3,
        "direction": "cw",
        "choices": [],
        "move_type": "capture"
    }
"""

import copy

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

PLAYER_SOUTH = 1
PLAYER_NORTH = 2

NYUMBA_IDX = 4  # F5 is index 4 (0-indexed)

# Clockwise track: F1,F2,...,F8,B8,B7,...,B1
CW_TRACK = [("front", i) for i in range(8)] + \
           [("back", i) for i in range(7, -1, -1)]
CCW_TRACK = list(reversed(CW_TRACK))


def _opp(p):
    """Return the opponent player ID."""
    return PLAYER_NORTH if p == PLAYER_SOUTH else PLAYER_SOUTH


def _pk(p):
    """Return the string key for a player ID (for JSON dict keys)."""
    return str(p)


class BaoGame(AbstractBoardGame):
    """Complete Bao la Kiswahili rules via the AbstractBoardGame interface."""

    # ── Abstract method implementations ──────────────────────────────

    def _get_name(self):
        return "Bao"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        def make_player():
            return {
                "front": [0, 0, 0, 0, 6, 2, 2, 0],
                "back":  [0, 0, 0, 0, 0, 0, 0, 0],
                "store": 22,
                "nyumba_owned": True
            }
        return {
            _pk(PLAYER_SOUTH): make_player(),
            _pk(PLAYER_NORTH): make_player(),
            "turn": PLAYER_SOUTH,
            "kutakatia": None
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        if state["turn"] != player:
            return []
        pk = _pk(player)
        if self._phase(state, pk) == "kunamua":
            return self._kunamua_moves(state, player)
        else:
            return self._mtaji_moves(state, player)

    def _apply_move(self, state, player, move):
        """Apply a move and return a brand new state."""
        ns = copy.deepcopy(state)
        pk = _pk(player)
        opp = _opp(player)
        opk = _pk(opp)
        phase = self._phase(ns, pk)
        pr = move.get("pit_row", "front")
        pi = move["pit_idx"]
        d = move["direction"]
        mt = move.get("move_type", "")
        choices = list(move.get("choices", []))

        if phase == "kunamua":
            ns[pk]["store"] -= 1
            if move.get("taxation"):
                ns[pk]["front"][NYUMBA_IDX] += 1
                ns[pk]["front"][NYUMBA_IDX] -= 2
                self._det_sow(ns, player, "front", NYUMBA_IDX,
                              d, 2, None, True, False, "kunamua", choices)
                ns[pk]["nyumba_owned"] = True
            elif mt == "capture":
                ns[pk]["front"][pi] += 1
                captured = ns[opk]["front"][pi]
                ns[opk]["front"][pi] = 0
                if pi == NYUMBA_IDX and ns[pk]["nyumba_owned"]:
                    ns[pk]["nyumba_owned"] = False
                self._det_capture_sow(ns, player, pi, captured, d,
                                       True, False, True, "kunamua", choices)
            else:
                ns[pk]["front"][pi] += 1
                seeds = ns[pk]["front"][pi]
                ns[pk]["front"][pi] = 0
                self._det_sow(ns, player, "front", pi, d, seeds, None,
                              True, False, "kunamua", choices)
        else:
            seeds = ns[pk][pr][pi]
            ns[pk][pr][pi] = 0
            if mt == "capture":
                track = CW_TRACK if d == "cw" else CCW_TRACK
                pos = self._track_pos(pr, pi, d)
                for _ in range(seeds):
                    pos = (pos + 1) % 16
                    r, x = track[pos]
                    ns[pk][r][x] += 1
                tr, tx = track[pos]
                captured = ns[opk]["front"][tx]
                ns[opk]["front"][tx] = 0
                if tx == NYUMBA_IDX and ns[pk]["nyumba_owned"]:
                    ns[pk]["nyumba_owned"] = False
                if not self._front_empty(ns, opk):
                    self._det_capture_sow(ns, player, tx, captured, d,
                                           True, False, True, "mtaji", choices)
            else:
                skip = (pr, pi) if seeds >= 16 else None
                self._det_sow(ns, player, pr, pi, d, seeds, skip,
                              True, False, "mtaji", choices)

        # Update nyumba ownership
        for p in [PLAYER_SOUTH, PLAYER_NORTH]:
            ppk = _pk(p)
            if ns[ppk]["nyumba_owned"] and ns[ppk]["front"][NYUMBA_IDX] == 0:
                ns[ppk]["nyumba_owned"] = False

        # Kutakatia
        new_kut = None
        if self._phase(ns, pk) == "mtaji" and mt == "takata":
            new_kut = self._check_kutakatia(ns, player)
        ns["kutakatia"] = new_kut
        ns["turn"] = opp
        return ns

    def _get_game_status(self, state):
        for p in [PLAYER_SOUTH, PLAYER_NORTH]:
            pk = _pk(p)
            if self._front_empty(state, pk):
                winner = _opp(p)
                return {"is_over": True, "winner": winner, "is_draw": False}
        current = state["turn"]
        legal = self._get_legal_moves(state, current)
        if not legal:
            winner = _opp(current)
            return {"is_over": True, "winner": winner, "is_draw": False}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Helpers ──────────────────────────────────────────────────────

    def _track_pos(self, row, idx, d):
        t = CW_TRACK if d == "cw" else CCW_TRACK
        for i, (r, x) in enumerate(t):
            if r == row and x == idx:
                return i
        return -1

    def _front_sum(self, b, pk):
        return sum(b[pk]["front"])

    def _front_empty(self, b, pk):
        return self._front_sum(b, pk) == 0

    def _is_kimbi(self, idx):
        return idx in (0, 1, 6, 7)

    def _is_kichwa(self, idx):
        return idx in (0, 7)

    def _nyumba_functional(self, b, pk):
        return b[pk].get("nyumba_owned", False) and b[pk]["front"][NYUMBA_IDX] >= 6

    def _phase(self, state, pk):
        return "kunamua" if state[pk]["store"] > 0 else "mtaji"

    # ── Core sowing simulation ───────────────────────────────────────

    def _simulate_sow(self, b, player, nyo, start_row, start_idx, direction,
                      num_seeds, skip_origin, is_takata, turn_is_mtaji,
                      phase, kut_info, depth=0):
        """
        Simulate sowing and relay. Modifies b in-place.
        Returns list of (board, nyumba_owned, choices_list, kutakatia_info).
        For branching, deep copies are made internally.
        """
        if depth > 200:
            return []

        pk = _pk(player)
        opk = _pk(_opp(player))
        track = CW_TRACK if direction == "cw" else CCW_TRACK
        pos = self._track_pos(start_row, start_idx, direction)

        # Distribute seeds
        current_pos = pos
        for _ in range(num_seeds):
            current_pos = (current_pos + 1) % 16
            r, x = track[current_pos]
            if skip_origin and r == skip_origin[0] and x == skip_origin[1]:
                current_pos = (current_pos + 1) % 16
                r, x = track[current_pos]
            b[pk][r][x] += 1

        tr, tx = track[current_pos]
        tv = b[pk][tr][tx]

        # ---- terminal evaluation (section 8.2 priority) ----

        # 1. front-row empty check
        if self._front_empty(b, pk) or self._front_empty(b, opk):
            return [(b, nyo, [], kut_info)]

        # 2. capture check (mtaji turns only)
        if turn_is_mtaji and tr == "front" and tv >= 2 and b[opk]["front"][tx] > 0:
            captured = b[opk]["front"][tx]
            b[opk]["front"][tx] = 0
            if self._front_empty(b, opk):
                return [(b, nyo, [], kut_info)]
            if tx == NYUMBA_IDX and nyo:
                nyo = False
            return self._do_capture_sow(b, player, nyo, tx, captured, direction,
                                         False, is_takata, turn_is_mtaji, phase,
                                         kut_info, depth)

        # 3. nyumba stop
        if (tr == "front" and tx == NYUMBA_IDX and
                nyo and b[pk]["front"][NYUMBA_IDX] >= 6):
            if is_takata:
                return [(b, nyo, [], kut_info)]
            if turn_is_mtaji:
                if phase == "mtaji":
                    # forced safari
                    nyo = False
                    seeds = b[pk]["front"][NYUMBA_IDX]
                    b[pk]["front"][NYUMBA_IDX] = 0
                    return self._simulate_sow(b, player, nyo, "front",
                                              NYUMBA_IDX, direction, seeds,
                                              None, is_takata, turn_is_mtaji,
                                              phase, kut_info, depth + 1)
                else:
                    # kunamua mtaji: choice to stop or safari
                    results = []
                    # stop
                    b1 = copy.deepcopy(b)
                    results.append((b1, True, ["stop"], kut_info))
                    # safari (continue on current b)
                    nyo = False
                    seeds = b[pk]["front"][NYUMBA_IDX]
                    b[pk]["front"][NYUMBA_IDX] = 0
                    for res in self._simulate_sow(b, player, nyo, "front",
                                                   NYUMBA_IDX, direction,
                                                   seeds, None, is_takata,
                                                   turn_is_mtaji, phase,
                                                   kut_info, depth + 1):
                        rb, rn, rc, rk = res
                        results.append((rb, rn, ["continue"] + rc, rk))
                    return results

        # 4. kutakatia stop
        if (kut_info and kut_info["target_player"] == player and
                tr == "front" and tx == kut_info["pit_idx"]):
            return [(b, nyo, [], kut_info)]

        # 5. relay if non-empty (>= 2 means it had seeds before our drop)
        if tv >= 2:
            seeds = b[pk][tr][tx]
            b[pk][tr][tx] = 0
            if tr == "front" and self._front_empty(b, pk):
                return []  # would empty front row - illegal
            return self._simulate_sow(b, player, nyo, tr, tx, direction,
                                       seeds, None, is_takata, turn_is_mtaji,
                                       phase, kut_info, depth + 1)

        # 6. empty -> end
        return [(b, nyo, [], kut_info)]

    def _do_capture_sow(self, b, player, nyo, cap_idx, captured, cur_dir,
                         is_first_cap, is_takata, turn_is_mtaji, phase,
                         kut_info, depth):
        """Sow captured seeds from the correct kichwa."""
        pk = _pk(player)
        if is_first_cap:
            if cap_idx in (0, 1):
                opts = [("cw", 0)]
            elif cap_idx in (6, 7):
                opts = [("ccw", 7)]
            else:
                opts = [("cw", 0), ("ccw", 7)]
        else:
            if self._is_kimbi(cap_idx):
                if cap_idx in (0, 1):
                    opts = [("cw", 0)]
                else:
                    opts = [("ccw", 7)]
            else:
                if cur_dir == "cw":
                    opts = [("cw", 0)]
                else:
                    opts = [("ccw", 7)]

        results = []
        for i, (sd, ki) in enumerate(opts):
            # Deep copy for all branches to avoid interference
            bc = copy.deepcopy(b)
            nc = nyo

            t = CW_TRACK if sd == "cw" else CCW_TRACK
            kp = next(j for j, (r, x) in enumerate(t) if r == "front" and x == ki)
            pre = (kp - 1) % 16
            pr, px = t[pre]

            choice_tag = []
            if len(opts) > 1:
                choice_tag = ["left" if sd == "cw" else "right"]

            for res in self._simulate_sow(bc, player, nc, pr, px, sd,
                                           captured, None, is_takata,
                                           turn_is_mtaji, phase,
                                           kut_info, depth + 1):
                rb, rn, rc, rk = res
                results.append((rb, rn, choice_tag + rc, rk))
        return results

    # ── Move generation ──────────────────────────────────────────────

    def _make_board_copy(self, state):
        pk1 = _pk(PLAYER_SOUTH)
        pk2 = _pk(PLAYER_NORTH)
        return {
            pk1: {"front": list(state[pk1]["front"]),
                  "back":  list(state[pk1]["back"]),
                  "nyumba_owned": state[pk1]["nyumba_owned"]},
            pk2: {"front": list(state[pk2]["front"]),
                  "back":  list(state[pk2]["back"]),
                  "nyumba_owned": state[pk2]["nyumba_owned"]}
        }

    def _takata_dirs(self, state, player, pit_row, pit_idx):
        """Valid directions for takata, respecting kichwa constraint."""
        pk = _pk(player)
        if pit_row != "front":
            return ["cw", "ccw"]
        other = [i for i in range(8) if i != pit_idx and state[pk]["front"][i] >= 1]
        if not other and self._is_kichwa(pit_idx):
            return ["cw"] if pit_idx == 0 else ["ccw"]
        return ["cw", "ccw"]

    def _kunamua_moves(self, state, player):
        pk = _pk(player)
        opk = _pk(_opp(player))
        cap_pits = [i for i in range(8)
                    if state[pk]["front"][i] >= 1 and state[opk]["front"][i] > 0]
        if cap_pits:
            return self._kunamua_capture_moves(state, player, cap_pits)
        return self._kunamua_takata_moves(state, player)

    def _kunamua_capture_moves(self, state, player, cap_pits):
        pk = _pk(player)
        opk = _pk(_opp(player))
        moves = []
        for pi in cap_pits:
            if pi in (0, 1):
                dopts = ["cw"]
            elif pi in (6, 7):
                dopts = ["ccw"]
            else:
                dopts = ["cw", "ccw"]
            for d in dopts:
                b = self._make_board_copy(state)
                b[pk]["front"][pi] += 1
                captured = b[opk]["front"][pi]
                b[opk]["front"][pi] = 0
                nyo = b[pk]["nyumba_owned"]
                if pi == NYUMBA_IDX and nyo:
                    nyo = False
                results = self._do_capture_sow(
                    b, player, nyo, pi, captured, d, True, False, True,
                    "kunamua", state.get("kutakatia"), 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, pk):
                        m = {"pit_row": "front", "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "capture"}
                        if m not in moves:
                            moves.append(m)
        return moves

    def _kunamua_takata_moves(self, state, player):
        pk = _pk(player)
        moves = []
        nyo_func = self._nyumba_functional(state, pk)
        occupied = [i for i in range(8) if state[pk]["front"][i] >= 1]
        if not occupied:
            return []
        if nyo_func and len(occupied) == 1 and occupied[0] == NYUMBA_IDX:
            return self._taxation_moves(state, player)
        valid = [i for i in occupied if not (i == NYUMBA_IDX and nyo_func)]
        if not valid:
            return self._taxation_moves(state, player) if nyo_func else []
        if not state[pk]["nyumba_owned"]:
            multi = [i for i in valid if state[pk]["front"][i] >= 2]
            if multi:
                valid = multi
        for pi in valid:
            for d in self._takata_dirs(state, player, "front", pi):
                b = self._make_board_copy(state)
                b[pk]["front"][pi] += 1
                seeds = b[pk]["front"][pi]
                b[pk]["front"][pi] = 0
                nyo = b[pk]["nyumba_owned"]
                results = self._simulate_sow(
                    b, player, nyo, "front", pi, d, seeds, None,
                    True, False, "kunamua", state.get("kutakatia"), 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, pk):
                        m = {"pit_row": "front", "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "takata"}
                        if m not in moves:
                            moves.append(m)
        return moves

    def _taxation_moves(self, state, player):
        pk = _pk(player)
        moves = []
        for d in ["cw", "ccw"]:
            b = self._make_board_copy(state)
            b[pk]["front"][NYUMBA_IDX] += 1
            b[pk]["front"][NYUMBA_IDX] -= 2
            nyo = True
            results = self._simulate_sow(
                b, player, nyo, "front", NYUMBA_IDX, d, 2, None,
                True, False, "kunamua", state.get("kutakatia"), 0)
            for rb, rn, rc, rk in results:
                if not self._front_empty(rb, pk):
                    m = {"pit_row": "front", "pit_idx": NYUMBA_IDX,
                         "direction": d, "choices": rc,
                         "move_type": "taxation", "taxation": True}
                    if m not in moves:
                        moves.append(m)
        return moves

    def _mtaji_moves(self, state, player):
        pk = _pk(player)
        kut = state.get("kutakatia")
        cap_moves = self._mtaji_capture_moves(state, player)
        if kut and kut["set_by"] == player and cap_moves:
            specific = [m for m in cap_moves
                        if self._move_hits_pit(state, player, m, kut["pit_idx"])]
            if specific:
                cap_moves = specific
        if cap_moves:
            return cap_moves
        return self._mtaji_takata_moves(state, player)

    def _move_hits_pit(self, state, player, move, target_idx):
        """Check if initial sowing of a move ends at target front pit."""
        pk = _pk(player)
        pr, pi, d = move["pit_row"], move["pit_idx"], move["direction"]
        seeds = state[pk][pr][pi]
        track = CW_TRACK if d == "cw" else CCW_TRACK
        pos = self._track_pos(pr, pi, d)
        for _ in range(seeds):
            pos = (pos + 1) % 16
        return track[pos][0] == "front" and track[pos][1] == target_idx

    def _mtaji_capture_moves(self, state, player):
        pk = _pk(player)
        opk = _pk(_opp(player))
        kut = state.get("kutakatia")
        moves = []
        for row in ["front", "back"]:
            for idx in range(8):
                seeds = state[pk][row][idx]
                if seeds < 2 or seeds >= 16:
                    continue
                if (kut and kut["target_player"] == player and
                        row == "front" and idx == kut["pit_idx"]):
                    continue
                for d in ["cw", "ccw"]:
                    b = self._make_board_copy(state)
                    b[pk][row][idx] = 0
                    track = CW_TRACK if d == "cw" else CCW_TRACK
                    cp = self._track_pos(row, idx, d)
                    for _ in range(seeds):
                        cp = (cp + 1) % 16
                        r, x = track[cp]
                        b[pk][r][x] += 1
                    tr, tx = track[cp]
                    if not (tr == "front" and b[pk][tr][tx] >= 2 and
                            b[opk]["front"][tx] > 0):
                        continue
                    # valid capture opening
                    captured = b[opk]["front"][tx]
                    b[opk]["front"][tx] = 0
                    if self._front_empty(b, opk):
                        m = {"pit_row": row, "pit_idx": idx,
                             "direction": d, "choices": [],
                             "move_type": "capture"}
                        if m not in moves:
                            moves.append(m)
                        continue
                    nyo = b[pk].get("nyumba_owned", False)
                    if tx == NYUMBA_IDX and nyo:
                        nyo = False
                    results = self._do_capture_sow(
                        b, player, nyo, tx, captured, d, True, False, True,
                        "mtaji", kut, 0)
                    for rb, rn, rc, rk in results:
                        if not self._front_empty(rb, pk):
                            m = {"pit_row": row, "pit_idx": idx,
                                 "direction": d, "choices": rc,
                                 "move_type": "capture"}
                            if m not in moves:
                                moves.append(m)
        return moves

    def _mtaji_takata_moves(self, state, player):
        pk = _pk(player)
        kut = state.get("kutakatia")
        moves = []
        front_pits = [i for i in range(8) if state[pk]["front"][i] >= 2
                      and not (kut and kut["target_player"] == player
                               and kut["pit_idx"] == i)]
        if front_pits:
            pits = [("front", i) for i in front_pits]
        else:
            back_pits = [i for i in range(8) if state[pk]["back"][i] >= 2]
            if not back_pits:
                return []
            pits = [("back", i) for i in back_pits]
        for pr, pi in pits:
            seeds = state[pk][pr][pi]
            skip = (pr, pi) if seeds >= 16 else None
            for d in self._takata_dirs(state, player, pr, pi):
                b = self._make_board_copy(state)
                b[pk][pr][pi] = 0
                nyo = b[pk].get("nyumba_owned", False)
                results = self._simulate_sow(
                    b, player, nyo, pr, pi, d, seeds, skip,
                    True, False, "mtaji", kut, 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, pk):
                        m = {"pit_row": pr, "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "takata"}
                        if m not in moves:
                            moves.append(m)
        return moves

    # ── Deterministic sowing for apply_move ──────────────────────────

    def _det_sow(self, ns, player, sr, si, direction, num_seeds,
                 skip_origin, is_takata, turn_is_mtaji, phase, choices,
                 depth=0):
        """Deterministic sowing for apply_move. Modifies ns in-place."""
        if depth > 200:
            return
        pk = _pk(player)
        opk = _pk(_opp(player))
        track = CW_TRACK if direction == "cw" else CCW_TRACK
        pos = self._track_pos(sr, si, direction)

        current_pos = pos
        for _ in range(num_seeds):
            current_pos = (current_pos + 1) % 16
            r, x = track[current_pos]
            if skip_origin and r == skip_origin[0] and x == skip_origin[1]:
                current_pos = (current_pos + 1) % 16
                r, x = track[current_pos]
            ns[pk][r][x] += 1

        tr, tx = track[current_pos]
        tv = ns[pk][tr][tx]

        if self._front_empty(ns, pk) or self._front_empty(ns, opk):
            return
        if turn_is_mtaji and tr == "front" and tv >= 2 and ns[opk]["front"][tx] > 0:
            captured = ns[opk]["front"][tx]
            ns[opk]["front"][tx] = 0
            if self._front_empty(ns, opk):
                return
            if tx == NYUMBA_IDX and ns[pk]["nyumba_owned"]:
                ns[pk]["nyumba_owned"] = False
            self._det_capture_sow(ns, player, tx, captured, direction,
                                   False, is_takata, turn_is_mtaji, phase, choices)
            return
        if (tr == "front" and tx == NYUMBA_IDX and
                ns[pk]["nyumba_owned"] and
                ns[pk]["front"][NYUMBA_IDX] >= 6):
            if is_takata:
                return
            if turn_is_mtaji:
                if phase == "mtaji":
                    ns[pk]["nyumba_owned"] = False
                    seeds = ns[pk]["front"][NYUMBA_IDX]
                    ns[pk]["front"][NYUMBA_IDX] = 0
                    self._det_sow(ns, player, "front", NYUMBA_IDX,
                                  direction, seeds, None, is_takata,
                                  turn_is_mtaji, phase, choices, depth + 1)
                    return
                else:
                    ch = choices.pop(0) if choices else "stop"
                    if ch == "stop":
                        return
                    ns[pk]["nyumba_owned"] = False
                    seeds = ns[pk]["front"][NYUMBA_IDX]
                    ns[pk]["front"][NYUMBA_IDX] = 0
                    self._det_sow(ns, player, "front", NYUMBA_IDX,
                                  direction, seeds, None, is_takata,
                                  turn_is_mtaji, phase, choices, depth + 1)
                    return
        kut = ns.get("kutakatia")
        if (kut and kut["target_player"] == player and
                tr == "front" and tx == kut["pit_idx"]):
            return
        if tv >= 2:
            seeds = ns[pk][tr][tx]
            ns[pk][tr][tx] = 0
            self._det_sow(ns, player, tr, tx, direction, seeds, None,
                          is_takata, turn_is_mtaji, phase, choices, depth + 1)
            return

    def _det_capture_sow(self, ns, player, cap_idx, captured, cur_dir,
                          is_first, is_takata, turn_is_mtaji, phase, choices):
        """Deterministic capture sowing."""
        if is_first:
            if cap_idx in (0, 1):
                sd, ki = "cw", 0
            elif cap_idx in (6, 7):
                sd, ki = "ccw", 7
            else:
                ch = choices.pop(0) if choices else "left"
                sd = "cw" if ch == "left" else "ccw"
                ki = 0 if ch == "left" else 7
        else:
            if self._is_kimbi(cap_idx):
                sd, ki = ("cw", 0) if cap_idx in (0, 1) else ("ccw", 7)
            else:
                sd = cur_dir
                ki = 0 if cur_dir == "cw" else 7

        t = CW_TRACK if sd == "cw" else CCW_TRACK
        kp = next(j for j, (r, x) in enumerate(t) if r == "front" and x == ki)
        pre = (kp - 1) % 16
        pr, px = t[pre]
        self._det_sow(ns, player, pr, px, sd, captured, None,
                      is_takata, turn_is_mtaji, phase, choices, 0)

    # ── Kutakatia ────────────────────────────────────────────────────

    def _check_kutakatia(self, state, player):
        opp = _opp(player)
        pk = _pk(player)
        opk = _pk(opp)
        if state[opk]["store"] > 0:
            return None
        # Simplified kutakatia check:
        # 1. opponent has no captures
        opp_caps = self._mtaji_capture_moves(state, opp)
        if opp_caps:
            return None
        # 2. exactly one threatened opp pit
        threatened = [i for i in range(8)
                      if state[opk]["front"][i] > 0 and state[pk]["front"][i] > 0]
        if len(threatened) != 1:
            return None
        # 3. none of player's pits threatened
        for i in range(8):
            if state[pk]["front"][i] > 0 and state[opk]["front"][i] > 0:
                return None
        tp = threatened[0]
        # exceptions
        if self._nyumba_functional(state, opk) and tp == NYUMBA_IDX:
            return None
        occ = [i for i in range(8) if state[opk]["front"][i] > 0]
        if len(occ) <= 1:
            return None
        multi = [i for i in range(8) if state[opk]["front"][i] >= 2]
        if len(multi) <= 1 and tp in multi:
            return None
        return {"target_player": opp, "pit_idx": tp, "set_by": player}
