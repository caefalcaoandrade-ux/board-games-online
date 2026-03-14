#!/usr/bin/env python3
"""
Bao la Kiswahili — Complete Implementation
A traditional East African abstract strategy board game.

SECTION 1 — GAME LOGIC CLASS
SECTION 2 — DISPLAY AND INPUT (Pygame)
"""

# ============================================================================
# SECTION 1 — GAME LOGIC CLASS
# ============================================================================
import copy
import json


class BaoGame:
    """Complete Bao la Kiswahili rules. No Pygame dependency."""

    NYUMBA_IDX = 4  # F5 is index 4 (0-indexed)

    # Clockwise track: F1,F2,...,F8,B8,B7,...,B1
    CW_TRACK = [("front", i) for i in range(8)] + \
               [("back", i) for i in range(7, -1, -1)]
    CCW_TRACK = list(reversed(CW_TRACK))

    def __init__(self):
        pass

    def get_name(self):
        return "Bao la Kiswahili"

    def get_num_players(self):
        return 2

    def get_current_player(self, state):
        return state["turn"]

    def create_initial_state(self):
        def make_player():
            return {
                "front": [0, 0, 0, 0, 6, 2, 2, 0],
                "back":  [0, 0, 0, 0, 0, 0, 0, 0],
                "store": 22,
                "nyumba_owned": True
            }
        return {
            "south": make_player(),
            "north": make_player(),
            "turn": "south",
            "kutakatia": None
        }

    # ---- helpers ----

    def _opp(self, p):
        return "north" if p == "south" else "south"

    def _track_pos(self, row, idx, d):
        t = self.CW_TRACK if d == "cw" else self.CCW_TRACK
        for i, (r, x) in enumerate(t):
            if r == row and x == idx:
                return i
        return -1

    def _front_sum(self, b, p):
        return sum(b[p]["front"])

    def _front_empty(self, b, p):
        return self._front_sum(b, p) == 0

    def _is_kimbi(self, idx):
        return idx in (0, 1, 6, 7)

    def _is_kichwa(self, idx):
        return idx in (0, 7)

    def _nyumba_functional(self, b, p):
        return b[p].get("nyumba_owned", False) and b[p]["front"][self.NYUMBA_IDX] >= 6

    def _phase(self, state, p):
        return "kunamua" if state[p]["store"] > 0 else "mtaji"

    # ---- core sowing simulation (always works on the passed board in-place,
    #      deep copies are made BEFORE calling for enumeration) ----

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

        track = self.CW_TRACK if direction == "cw" else self.CCW_TRACK
        pos = self._track_pos(start_row, start_idx, direction)
        opp = self._opp(player)

        # Distribute seeds
        current_pos = pos
        for _ in range(num_seeds):
            current_pos = (current_pos + 1) % 16
            r, x = track[current_pos]
            if skip_origin and r == skip_origin[0] and x == skip_origin[1]:
                current_pos = (current_pos + 1) % 16
                r, x = track[current_pos]
            b[player][r][x] += 1

        tr, tx = track[current_pos]
        tv = b[player][tr][tx]

        # ---- terminal evaluation (section 8.2 priority) ----

        # 1. front-row empty check
        if self._front_empty(b, player) or self._front_empty(b, opp):
            return [(b, nyo, [], kut_info)]

        # 2. capture check (mtaji turns only)
        if turn_is_mtaji and tr == "front" and tv >= 2 and b[opp]["front"][tx] > 0:
            captured = b[opp]["front"][tx]
            b[opp]["front"][tx] = 0
            if self._front_empty(b, opp):
                return [(b, nyo, [], kut_info)]
            if tx == self.NYUMBA_IDX and nyo:
                nyo = False
            return self._do_capture_sow(b, player, nyo, tx, captured, direction,
                                         False, is_takata, turn_is_mtaji, phase,
                                         kut_info, depth)

        # 3. nyumba stop
        if (tr == "front" and tx == self.NYUMBA_IDX and
                nyo and b[player]["front"][self.NYUMBA_IDX] >= 6):
            if is_takata:
                return [(b, nyo, [], kut_info)]
            if turn_is_mtaji:
                if phase == "mtaji":
                    # forced safari
                    nyo = False
                    seeds = b[player]["front"][self.NYUMBA_IDX]
                    b[player]["front"][self.NYUMBA_IDX] = 0
                    return self._simulate_sow(b, player, nyo, "front",
                                              self.NYUMBA_IDX, direction, seeds,
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
                    seeds = b[player]["front"][self.NYUMBA_IDX]
                    b[player]["front"][self.NYUMBA_IDX] = 0
                    for res in self._simulate_sow(b, player, nyo, "front",
                                                   self.NYUMBA_IDX, direction,
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
            seeds = b[player][tr][tx]
            b[player][tr][tx] = 0
            if tr == "front" and self._front_empty(b, player):
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

            t = self.CW_TRACK if sd == "cw" else self.CCW_TRACK
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

    # ---- move generation ----

    def _make_board_copy(self, state):
        return {
            "south": {"front": list(state["south"]["front"]),
                      "back":  list(state["south"]["back"]),
                      "nyumba_owned": state["south"]["nyumba_owned"]},
            "north": {"front": list(state["north"]["front"]),
                      "back":  list(state["north"]["back"]),
                      "nyumba_owned": state["north"]["nyumba_owned"]}
        }

    def _takata_dirs(self, state, player, pit_row, pit_idx):
        """Valid directions for takata, respecting kichwa constraint."""
        if pit_row != "front":
            return ["cw", "ccw"]
        other = [i for i in range(8) if i != pit_idx and state[player]["front"][i] >= 1]
        if not other and self._is_kichwa(pit_idx):
            return ["cw"] if pit_idx == 0 else ["ccw"]
        return ["cw", "ccw"]

    def get_legal_moves(self, state, player):
        if state["turn"] != player:
            return []
        if self._phase(state, player) == "kunamua":
            return self._kunamua_moves(state, player)
        else:
            return self._mtaji_moves(state, player)

    def _kunamua_moves(self, state, player):
        opp = self._opp(player)
        cap_pits = [i for i in range(8)
                    if state[player]["front"][i] >= 1 and state[opp]["front"][i] > 0]
        if cap_pits:
            return self._kunamua_capture_moves(state, player, cap_pits)
        return self._kunamua_takata_moves(state, player)

    def _kunamua_capture_moves(self, state, player, cap_pits):
        opp = self._opp(player)
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
                b[player]["front"][pi] += 1
                captured = b[opp]["front"][pi]
                b[opp]["front"][pi] = 0
                nyo = b[player]["nyumba_owned"]
                if pi == self.NYUMBA_IDX and nyo:
                    nyo = False
                results = self._do_capture_sow(
                    b, player, nyo, pi, captured, d, True, False, True,
                    "kunamua", state.get("kutakatia"), 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, player):
                        m = {"pit_row": "front", "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "capture"}
                        if m not in moves:
                            moves.append(m)
        return moves

    def _kunamua_takata_moves(self, state, player):
        moves = []
        nyo_func = self._nyumba_functional(state, player)
        occupied = [i for i in range(8) if state[player]["front"][i] >= 1]
        if not occupied:
            return []
        if nyo_func and len(occupied) == 1 and occupied[0] == self.NYUMBA_IDX:
            return self._taxation_moves(state, player)
        valid = [i for i in occupied if not (i == self.NYUMBA_IDX and nyo_func)]
        if not valid:
            return self._taxation_moves(state, player) if nyo_func else []
        if not state[player]["nyumba_owned"]:
            multi = [i for i in valid if state[player]["front"][i] >= 2]
            if multi:
                valid = multi
        for pi in valid:
            for d in self._takata_dirs(state, player, "front", pi):
                b = self._make_board_copy(state)
                b[player]["front"][pi] += 1
                seeds = b[player]["front"][pi]
                b[player]["front"][pi] = 0
                nyo = b[player]["nyumba_owned"]
                results = self._simulate_sow(
                    b, player, nyo, "front", pi, d, seeds, None,
                    True, False, "kunamua", state.get("kutakatia"), 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, player):
                        m = {"pit_row": "front", "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "takata"}
                        if m not in moves:
                            moves.append(m)
        return moves

    def _taxation_moves(self, state, player):
        moves = []
        for d in ["cw", "ccw"]:
            b = self._make_board_copy(state)
            b[player]["front"][self.NYUMBA_IDX] += 1
            b[player]["front"][self.NYUMBA_IDX] -= 2
            nyo = True
            results = self._simulate_sow(
                b, player, nyo, "front", self.NYUMBA_IDX, d, 2, None,
                True, False, "kunamua", state.get("kutakatia"), 0)
            for rb, rn, rc, rk in results:
                if not self._front_empty(rb, player):
                    m = {"pit_row": "front", "pit_idx": self.NYUMBA_IDX,
                         "direction": d, "choices": rc,
                         "move_type": "taxation", "taxation": True}
                    if m not in moves:
                        moves.append(m)
        return moves

    def _mtaji_moves(self, state, player):
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
        pr, pi, d = move["pit_row"], move["pit_idx"], move["direction"]
        seeds = state[player][pr][pi]
        track = self.CW_TRACK if d == "cw" else self.CCW_TRACK
        pos = self._track_pos(pr, pi, d)
        for _ in range(seeds):
            pos = (pos + 1) % 16
        return track[pos][0] == "front" and track[pos][1] == target_idx

    def _mtaji_capture_moves(self, state, player):
        opp = self._opp(player)
        kut = state.get("kutakatia")
        moves = []
        for row in ["front", "back"]:
            for idx in range(8):
                seeds = state[player][row][idx]
                if seeds < 2 or seeds >= 16:
                    continue
                if (kut and kut["target_player"] == player and
                        row == "front" and idx == kut["pit_idx"]):
                    continue
                for d in ["cw", "ccw"]:
                    b = self._make_board_copy(state)
                    b[player][row][idx] = 0
                    track = self.CW_TRACK if d == "cw" else self.CCW_TRACK
                    cp = self._track_pos(row, idx, d)
                    for _ in range(seeds):
                        cp = (cp + 1) % 16
                        r, x = track[cp]
                        b[player][r][x] += 1
                    tr, tx = track[cp]
                    if not (tr == "front" and b[player][tr][tx] >= 2 and
                            b[opp]["front"][tx] > 0):
                        continue
                    # valid capture opening
                    captured = b[opp]["front"][tx]
                    b[opp]["front"][tx] = 0
                    if self._front_empty(b, opp):
                        m = {"pit_row": row, "pit_idx": idx,
                             "direction": d, "choices": [],
                             "move_type": "capture"}
                        if m not in moves:
                            moves.append(m)
                        continue
                    nyo = b[player].get("nyumba_owned", False)
                    if tx == self.NYUMBA_IDX and nyo:
                        nyo = False
                    results = self._do_capture_sow(
                        b, player, nyo, tx, captured, d, True, False, True,
                        "mtaji", kut, 0)
                    for rb, rn, rc, rk in results:
                        if not self._front_empty(rb, player):
                            m = {"pit_row": row, "pit_idx": idx,
                                 "direction": d, "choices": rc,
                                 "move_type": "capture"}
                            if m not in moves:
                                moves.append(m)
        return moves

    def _mtaji_takata_moves(self, state, player):
        kut = state.get("kutakatia")
        moves = []
        front_pits = [i for i in range(8) if state[player]["front"][i] >= 2
                      and not (kut and kut["target_player"] == player
                               and kut["pit_idx"] == i)]
        if front_pits:
            pits = [("front", i) for i in front_pits]
        else:
            back_pits = [i for i in range(8) if state[player]["back"][i] >= 2]
            if not back_pits:
                return []
            pits = [("back", i) for i in back_pits]
        for pr, pi in pits:
            seeds = state[player][pr][pi]
            skip = (pr, pi) if seeds >= 16 else None
            for d in self._takata_dirs(state, player, pr, pi):
                b = self._make_board_copy(state)
                b[player][pr][pi] = 0
                nyo = b[player].get("nyumba_owned", False)
                results = self._simulate_sow(
                    b, player, nyo, pr, pi, d, seeds, skip,
                    True, False, "mtaji", kut, 0)
                for rb, rn, rc, rk in results:
                    if not self._front_empty(rb, player):
                        m = {"pit_row": pr, "pit_idx": pi,
                             "direction": d, "choices": rc,
                             "move_type": "takata"}
                        if m not in moves:
                            moves.append(m)
        return moves

    # ---- apply_move (deterministic in-place version) ----

    def apply_move(self, state, player, move):
        """Apply a move and return a brand new state."""
        ns = copy.deepcopy(state)
        opp = self._opp(player)
        phase = self._phase(ns, player)
        pr = move.get("pit_row", "front")
        pi = move["pit_idx"]
        d = move["direction"]
        mt = move.get("move_type", "")
        choices = list(move.get("choices", []))

        if phase == "kunamua":
            ns[player]["store"] -= 1
            if move.get("taxation"):
                ns[player]["front"][self.NYUMBA_IDX] += 1
                ns[player]["front"][self.NYUMBA_IDX] -= 2
                self._det_sow(ns, player, "front", self.NYUMBA_IDX,
                              d, 2, None, True, False, "kunamua", choices)
                ns[player]["nyumba_owned"] = True
            elif mt == "capture":
                ns[player]["front"][pi] += 1
                captured = ns[opp]["front"][pi]
                ns[opp]["front"][pi] = 0
                if pi == self.NYUMBA_IDX and ns[player]["nyumba_owned"]:
                    ns[player]["nyumba_owned"] = False
                self._det_capture_sow(ns, player, pi, captured, d,
                                       True, False, True, "kunamua", choices)
            else:
                ns[player]["front"][pi] += 1
                seeds = ns[player]["front"][pi]
                ns[player]["front"][pi] = 0
                self._det_sow(ns, player, "front", pi, d, seeds, None,
                              True, False, "kunamua", choices)
        else:
            seeds = ns[player][pr][pi]
            ns[player][pr][pi] = 0
            if mt == "capture":
                track = self.CW_TRACK if d == "cw" else self.CCW_TRACK
                pos = self._track_pos(pr, pi, d)
                for _ in range(seeds):
                    pos = (pos + 1) % 16
                    r, x = track[pos]
                    ns[player][r][x] += 1
                tr, tx = track[pos]
                captured = ns[opp]["front"][tx]
                ns[opp]["front"][tx] = 0
                if tx == self.NYUMBA_IDX and ns[player]["nyumba_owned"]:
                    ns[player]["nyumba_owned"] = False
                if not self._front_empty(ns, opp):
                    self._det_capture_sow(ns, player, tx, captured, d,
                                           True, False, True, "mtaji", choices)
            else:
                skip = (pr, pi) if seeds >= 16 else None
                self._det_sow(ns, player, pr, pi, d, seeds, skip,
                              True, False, "mtaji", choices)

        # Update nyumba ownership
        for p in ["south", "north"]:
            if ns[p]["nyumba_owned"] and ns[p]["front"][self.NYUMBA_IDX] == 0:
                ns[p]["nyumba_owned"] = False

        # Kutakatia
        new_kut = None
        if self._phase(ns, player) == "mtaji" and mt == "takata":
            new_kut = self._check_kutakatia(ns, player)
        ns["kutakatia"] = new_kut
        ns["turn"] = opp
        return ns

    def _det_sow(self, ns, player, sr, si, direction, num_seeds,
                 skip_origin, is_takata, turn_is_mtaji, phase, choices,
                 depth=0):
        """Deterministic sowing for apply_move. Modifies ns in-place."""
        if depth > 200:
            return
        opp = self._opp(player)
        track = self.CW_TRACK if direction == "cw" else self.CCW_TRACK
        pos = self._track_pos(sr, si, direction)

        current_pos = pos
        for _ in range(num_seeds):
            current_pos = (current_pos + 1) % 16
            r, x = track[current_pos]
            if skip_origin and r == skip_origin[0] and x == skip_origin[1]:
                current_pos = (current_pos + 1) % 16
                r, x = track[current_pos]
            ns[player][r][x] += 1

        tr, tx = track[current_pos]
        tv = ns[player][tr][tx]

        if self._front_empty(ns, player) or self._front_empty(ns, opp):
            return
        if turn_is_mtaji and tr == "front" and tv >= 2 and ns[opp]["front"][tx] > 0:
            captured = ns[opp]["front"][tx]
            ns[opp]["front"][tx] = 0
            if self._front_empty(ns, opp):
                return
            if tx == self.NYUMBA_IDX and ns[player]["nyumba_owned"]:
                ns[player]["nyumba_owned"] = False
            self._det_capture_sow(ns, player, tx, captured, direction,
                                   False, is_takata, turn_is_mtaji, phase, choices)
            return
        if (tr == "front" and tx == self.NYUMBA_IDX and
                ns[player]["nyumba_owned"] and
                ns[player]["front"][self.NYUMBA_IDX] >= 6):
            if is_takata:
                return
            if turn_is_mtaji:
                if phase == "mtaji":
                    ns[player]["nyumba_owned"] = False
                    seeds = ns[player]["front"][self.NYUMBA_IDX]
                    ns[player]["front"][self.NYUMBA_IDX] = 0
                    self._det_sow(ns, player, "front", self.NYUMBA_IDX,
                                  direction, seeds, None, is_takata,
                                  turn_is_mtaji, phase, choices, depth + 1)
                    return
                else:
                    ch = choices.pop(0) if choices else "stop"
                    if ch == "stop":
                        return
                    ns[player]["nyumba_owned"] = False
                    seeds = ns[player]["front"][self.NYUMBA_IDX]
                    ns[player]["front"][self.NYUMBA_IDX] = 0
                    self._det_sow(ns, player, "front", self.NYUMBA_IDX,
                                  direction, seeds, None, is_takata,
                                  turn_is_mtaji, phase, choices, depth + 1)
                    return
        kut = ns.get("kutakatia")
        if (kut and kut["target_player"] == player and
                tr == "front" and tx == kut["pit_idx"]):
            return
        if tv >= 2:
            seeds = ns[player][tr][tx]
            ns[player][tr][tx] = 0
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

        t = self.CW_TRACK if sd == "cw" else self.CCW_TRACK
        kp = next(j for j, (r, x) in enumerate(t) if r == "front" and x == ki)
        pre = (kp - 1) % 16
        pr, px = t[pre]
        self._det_sow(ns, player, pr, px, sd, captured, None,
                      is_takata, turn_is_mtaji, phase, choices, 0)

    # ---- kutakatia ----

    def _check_kutakatia(self, state, player):
        opp = self._opp(player)
        if state[opp]["store"] > 0:
            return None
        # Simplified kutakatia check:
        # 1. opponent has no captures
        opp_caps = self._mtaji_capture_moves(state, opp)
        if opp_caps:
            return None
        # 2. exactly one threatened opp pit
        threatened = [i for i in range(8)
                      if state[opp]["front"][i] > 0 and state[player]["front"][i] > 0]
        if len(threatened) != 1:
            return None
        # 3. none of player's pits threatened
        for i in range(8):
            if state[player]["front"][i] > 0 and state[opp]["front"][i] > 0:
                return None
        tp = threatened[0]
        # exceptions
        if self._nyumba_functional(state, opp) and tp == self.NYUMBA_IDX:
            return None
        occ = [i for i in range(8) if state[opp]["front"][i] > 0]
        if len(occ) <= 1:
            return None
        multi = [i for i in range(8) if state[opp]["front"][i] >= 2]
        if len(multi) <= 1 and tp in multi:
            return None
        return {"target_player": opp, "pit_idx": tp, "set_by": player}

    # ---- game over ----

    def check_game_over(self, state):
        for p in ["south", "north"]:
            if self._front_empty(state, p):
                return self._opp(p)
        current = state["turn"]
        legal = self.get_legal_moves(state, current)
        if not legal:
            return self._opp(current)
        return None


# ============================================================================
# SECTION 2 — DISPLAY AND INPUT (Pygame)
# ============================================================================

import pygame
import sys
import math

# Colors
WOOD_MED = (180, 120, 60)
WOOD_BORDER = (100, 65, 25)
WOOD_LIGHT = (210, 160, 90)
PIT_DARK = (90, 60, 25)
PIT_MED = (120, 80, 40)
PIT_SHADOW = (70, 45, 15)
SEED_COL = (200, 195, 180)
SEED_SHAD = (160, 155, 140)
SEED_HL = (230, 225, 210)
TEXT_L = (240, 230, 210)
TEXT_D = (80, 55, 25)
HL_GOLD = (255, 215, 0)
HL_GREEN = (100, 200, 100)
HL_RED = (220, 80, 80)
NYUMBA_ACC = (200, 160, 80)
BG = (45, 35, 25)
BTN_BG = (100, 70, 35)
BTN_HOV = (140, 100, 50)
BTN_TXT = (240, 230, 210)
CW_COL = (80, 180, 80)
CCW_COL = (80, 130, 220)


class BaoDisplay:
    def __init__(self):
        pygame.init()
        self.W, self.H = 1200, 780
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("Bao la Kiswahili")

        self.BX, self.BY = 60, 150
        self.BW, self.BH = 920, 460
        self.PR = 42
        self.SX = self.BW // 8
        self.SY = self.BH // 4

        self.font_title = pygame.font.SysFont("Georgia", 30, bold=True)
        self.font_med = pygame.font.SysFont("Georgia", 22)
        self.font_sm = pygame.font.SysFont("Georgia", 16)
        self.font_seed = pygame.font.SysFont("Georgia", 26, bold=True)
        self.font_lbl = pygame.font.SysFont("Georgia", 13)
        self.font_big = pygame.font.SysFont("Georgia", 40, bold=True)

        self.game = BaoGame()
        self.state = self.game.create_initial_state()
        self.legal_moves = []
        self.sel_pit = None
        self.filtered = []
        self.game_over = False
        self.winner = None
        self.status = ""
        self.dir_btns = []
        self.choice_btns = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.pending_choices = []
        self.pending_ci = 0
        self.pending_filtered = []
        self.restart_rect = pygame.Rect(0, 0, 0, 0)
        self._refresh()

    def _refresh(self):
        cur = self.game.get_current_player(self.state)
        self.legal_moves = self.game.get_legal_moves(self.state, cur)
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.dir_btns = []
        self.choice_btns = []
        if not self.legal_moves and not self.game_over:
            r = self.game.check_game_over(self.state)
            if r:
                self.game_over = True
                self.winner = r
                self.status = f"Game Over! {r.upper()} wins!"

    def _pit_xy(self, dr, dc):
        return (self.BX + dc * self.SX + self.SX // 2,
                self.BY + dr * self.SY + self.SY // 2)

    def _to_display(self, player, row, idx):
        if player == "north":
            return (0 if row == "back" else 1, 7 - idx)
        return (2 if row == "front" else 3, idx)

    def _from_screen(self, mx, my):
        for p in ["north", "south"]:
            for r in ["front", "back"]:
                for i in range(8):
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    if math.hypot(mx - cx, my - cy) <= self.PR + 5:
                        return (p, r, i)
        return None

    def _clickable(self):
        cur = self.game.get_current_player(self.state)
        return {(cur, m.get("pit_row", "front"), m["pit_idx"])
                for m in self.legal_moves}

    def _draw(self):
        self.screen.fill(BG)

        # Title
        t = self.font_title.render("BAO LA KISWAHILI", True, TEXT_L)
        self.screen.blit(t, (self.W // 2 - t.get_width() // 2, 10))

        # Turn info
        cur = self.game.get_current_player(self.state)
        ph = self.game._phase(self.state, cur)
        info = f"{cur.upper()}'s turn  \u2502  {ph.upper()}"
        if ph == "kunamua":
            info += f"  \u2502  Store: {self.state[cur]['store']}"
        col = HL_RED if self.game_over else HL_GOLD
        ts = self.font_med.render(info, True, col)
        self.screen.blit(ts, (self.W // 2 - ts.get_width() // 2, 48))

        # Side panel info
        for p in ["north", "south"]:
            pph = self.game._phase(self.state, p)
            ptxt = f"{p.upper()}: {pph}"
            if pph == "kunamua":
                ptxt += f" ({self.state[p]['store']})"
            if self.state[p]["nyumba_owned"]:
                ptxt += " \u2302"  # house symbol
            sx = self.BX + self.BW + 25
            sy = self.BY + (15 if p == "north" else self.BH - 35)
            ps = self.font_sm.render(ptxt, True, TEXT_L)
            self.screen.blit(ps, (sx, sy))

        # Board background
        pygame.draw.rect(self.screen, WOOD_MED,
                          (self.BX - 12, self.BY - 12,
                           self.BW + 24, self.BH + 24), border_radius=14)
        pygame.draw.rect(self.screen, WOOD_BORDER,
                          (self.BX - 12, self.BY - 12,
                           self.BW + 24, self.BH + 24), 3, border_radius=14)
        # Divider
        dy = self.BY + self.BH // 2
        pygame.draw.line(self.screen, WOOD_BORDER,
                          (self.BX - 8, dy), (self.BX + self.BW + 8, dy), 3)

        # Side labels
        nl = self.font_sm.render("NORTH", True, WOOD_LIGHT)
        self.screen.blit(nl, (self.BX + self.BW // 2 - nl.get_width() // 2,
                               self.BY - nl.get_height() - 5))
        sl = self.font_sm.render("SOUTH", True, WOOD_LIGHT)
        self.screen.blit(sl, (self.BX + self.BW // 2 - sl.get_width() // 2,
                               self.BY + self.BH + 5))

        clickable = self._clickable() if not self.game_over else set()

        # Pits
        for p in ["north", "south"]:
            for r in ["front", "back"]:
                for i in range(8):
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    seeds = self.state[p][r][i]
                    is_ny = (r == "front" and i == BaoGame.NYUMBA_IDX)
                    is_sel = (self.sel_pit == (p, r, i))
                    is_click = (p, r, i) in clickable
                    self._draw_pit(cx, cy, seeds, is_ny, is_sel, is_click, p)

        # Labels
        for i in range(8):
            for p in ["south", "north"]:
                for r in ["front", "back"]:
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    prefix = "F" if r == "front" else "B"
                    lb = self.font_lbl.render(f"{prefix}{i+1}", True, TEXT_D)
                    if p == "south":
                        self.screen.blit(lb, (cx - lb.get_width() // 2,
                                               cy + self.PR + 4))
                    else:
                        self.screen.blit(lb, (cx - lb.get_width() // 2,
                                               cy - self.PR - 16))

        if self.awaiting_dir:
            self._draw_dir_btns()
        if self.awaiting_choice:
            self._draw_choice_btns()

        # Status
        if self.status and not self.game_over:
            ss = self.font_med.render(self.status, True, TEXT_L)
            self.screen.blit(ss, (self.W // 2 - ss.get_width() // 2, self.H - 65))

        # Instructions
        if not self.game_over and not self.awaiting_dir and not self.awaiting_choice:
            inst = "Click a highlighted pit to start" if not self.sel_pit else ""
            if inst:
                its = self.font_sm.render(inst, True, TEXT_L)
                self.screen.blit(its, (self.BX, self.H - 35))

        # Game over
        if self.game_over:
            ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 150))
            self.screen.blit(ov, (0, 0))
            gt = self.font_big.render(f"{self.winner.upper()} WINS!", True, HL_GOLD)
            self.screen.blit(gt, (self.W // 2 - gt.get_width() // 2, self.H // 2 - 50))
            sub = self.font_med.render("Press R or click New Game", True, TEXT_L)
            self.screen.blit(sub, (self.W // 2 - sub.get_width() // 2, self.H // 2 + 10))

        # Restart
        rr = pygame.Rect(self.W - 175, self.H - 48, 145, 34)
        mx, my = pygame.mouse.get_pos()
        hov = rr.collidepoint(mx, my)
        pygame.draw.rect(self.screen, BTN_HOV if hov else BTN_BG, rr, border_radius=8)
        pygame.draw.rect(self.screen, WOOD_BORDER, rr, 2, border_radius=8)
        rt = self.font_sm.render("New Game (R)", True, BTN_TXT)
        self.screen.blit(rt, (rr.centerx - rt.get_width() // 2,
                               rr.centery - rt.get_height() // 2))
        self.restart_rect = rr

    def _draw_pit(self, cx, cy, seeds, is_ny, is_sel, is_click, player):
        r = self.PR
        if is_sel:
            pygame.draw.circle(self.screen, HL_GOLD, (cx, cy), r + 6)
        elif is_click:
            tick = pygame.time.get_ticks() / 500.0
            alpha = int(140 + 80 * math.sin(tick * 3))
            s = pygame.Surface((r * 2 + 12, r * 2 + 12), pygame.SRCALPHA)
            pygame.draw.circle(s, (*HL_GREEN, min(255, alpha)),
                                (r + 6, r + 6), r + 4, 3)
            self.screen.blit(s, (cx - r - 6, cy - r - 6))

        if is_ny:
            rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.rect(self.screen, PIT_SHADOW, rect.inflate(4, 4),
                              border_radius=8)
            pygame.draw.rect(self.screen, PIT_DARK, rect, border_radius=8)
            pygame.draw.rect(self.screen, PIT_MED, rect.inflate(-6, -6),
                              border_radius=6)
            if self.state[player]["nyumba_owned"]:
                nt = self.font_lbl.render("NYU", True, NYUMBA_ACC)
                self.screen.blit(nt, (cx - nt.get_width() // 2, cy - r + 3))
        else:
            pygame.draw.circle(self.screen, PIT_SHADOW, (cx + 2, cy + 2), r)
            pygame.draw.circle(self.screen, PIT_DARK, (cx, cy), r)
            pygame.draw.circle(self.screen, PIT_MED, (cx, cy), r - 4)

        if seeds > 0:
            if seeds <= 6:
                self._draw_dots(cx, cy, seeds)
            else:
                st = self.font_seed.render(str(seeds), True, SEED_COL)
                self.screen.blit(st, (cx - st.get_width() // 2,
                                       cy - st.get_height() // 2 + (3 if is_ny else 0)))

    def _draw_dots(self, cx, cy, n):
        sr = 6
        layouts = {
            1: [(0, 0)],
            2: [(-10, 0), (10, 0)],
            3: [(-10, -7), (10, -7), (0, 8)],
            4: [(-10, -8), (10, -8), (-10, 8), (10, 8)],
            5: [(-10, -10), (10, -10), (-10, 8), (10, 8), (0, 0)],
            6: [(-12, -10), (0, -10), (12, -10), (-12, 8), (0, 8), (12, 8)]
        }
        for dx, dy in layouts.get(n, [(0, 0)]):
            pygame.draw.circle(self.screen, SEED_SHAD, (cx+dx+1, cy+dy+1), sr)
            pygame.draw.circle(self.screen, SEED_COL, (cx+dx, cy+dy), sr)
            pygame.draw.circle(self.screen, SEED_HL, (cx+dx-2, cy+dy-2), 3)

    def _draw_dir_btns(self):
        if not self.sel_pit:
            return
        p, r, i = self.sel_pit
        dr, dc = self._to_display(p, r, i)
        cx, cy = self._pit_xy(dr, dc)
        dirs = {m["direction"] for m in self.filtered}
        self.dir_btns = []
        bw, bh = 65, 30
        by = cy + self.PR + 25 if p == "south" else cy - self.PR - 55
        mx, my = pygame.mouse.get_pos()
        if "cw" in dirs:
            rect = pygame.Rect(cx - bw - 5, by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, CW_COL if hov else (60, 140, 60),
                              rect, border_radius=6)
            lb = self.font_lbl.render("CW \u2192", True, TEXT_L)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                   rect.centery - lb.get_height() // 2))
            self.dir_btns.append((rect, "cw"))
        if "ccw" in dirs:
            rect = pygame.Rect(cx + 5, by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, CCW_COL if hov else (60, 100, 180),
                              rect, border_radius=6)
            lb = self.font_lbl.render("\u2190 CCW", True, TEXT_L)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                   rect.centery - lb.get_height() // 2))
            self.dir_btns.append((rect, "ccw"))

    def _draw_choice_btns(self):
        bw, bh = 150, 36
        by = self.H - 115
        self.choice_btns = []
        total_w = len(self.pending_choices) * (bw + 10) - 10
        sx = self.W // 2 - total_w // 2
        mx, my = pygame.mouse.get_pos()
        lbl = self.font_sm.render("Choose:", True, HL_GOLD)
        self.screen.blit(lbl, (self.W // 2 - lbl.get_width() // 2, by - 24))
        for j, (val, text) in enumerate(self.pending_choices):
            rect = pygame.Rect(sx + j * (bw + 10), by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, BTN_HOV if hov else BTN_BG,
                              rect, border_radius=8)
            pygame.draw.rect(self.screen, HL_GOLD, rect, 2, border_radius=8)
            lb = self.font_sm.render(text, True, BTN_TXT)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                   rect.centery - lb.get_height() // 2))
            self.choice_btns.append((rect, val))

    def _click(self, mx, my):
        if self.game_over:
            if self.restart_rect.collidepoint(mx, my):
                self._restart()
            return
        if self.restart_rect.collidepoint(mx, my):
            self._restart()
            return
        if self.awaiting_dir:
            for rect, d in self.dir_btns:
                if rect.collidepoint(mx, my):
                    self._pick_dir(d)
                    return
        if self.awaiting_choice:
            for rect, v in self.choice_btns:
                if rect.collidepoint(mx, my):
                    self._pick_choice(v)
                    return
        pit = self._from_screen(mx, my)
        if pit:
            self._pick_pit(pit)

    def _pick_pit(self, pit):
        p, r, i = pit
        cur = self.game.get_current_player(self.state)
        if p != cur:
            return
        matching = [m for m in self.legal_moves
                    if m.get("pit_row", "front") == r and m["pit_idx"] == i]
        if not matching:
            self.sel_pit = None
            self.filtered = []
            self.awaiting_dir = False
            return
        self.sel_pit = (p, r, i)
        self.filtered = matching
        dirs = {m["direction"] for m in matching}
        if len(dirs) == 1:
            self._pick_dir(list(dirs)[0])
        else:
            self.awaiting_dir = True

    def _pick_dir(self, d):
        self.awaiting_dir = False
        matching = [m for m in self.filtered if m["direction"] == d]
        if len(matching) == 1:
            self._apply(matching[0])
        elif matching:
            self._present_choice(matching)
        else:
            self.sel_pit = None
            self.filtered = []

    def _present_choice(self, moves):
        max_ch = max(len(m.get("choices", [])) for m in moves)
        if max_ch == 0:
            self._apply(moves[0])
            return
        for ci in range(max_ch):
            vals = set()
            for m in moves:
                ch = m.get("choices", [])
                vals.add(ch[ci] if ci < len(ch) else None)
            if len(vals) > 1:
                self.awaiting_choice = True
                self.pending_choices = []
                self.pending_ci = ci
                self.pending_filtered = moves
                labels = {"left": "\u2190 Left Kichwa", "right": "Right Kichwa \u2192",
                           "stop": "Stop (Nyumba)", "continue": "Safari \u2192"}
                for v in sorted(v2 for v2 in vals if v2 is not None):
                    self.pending_choices.append((v, labels.get(v, str(v))))
                return
        self._apply(moves[0])

    def _pick_choice(self, val):
        self.awaiting_choice = False
        ci = self.pending_ci
        matching = [m for m in self.pending_filtered
                    if ci < len(m.get("choices", [])) and m["choices"][ci] == val]
        if len(matching) == 1:
            self._apply(matching[0])
        elif matching:
            self._present_choice(matching)
        else:
            self.sel_pit = None
            self.filtered = []

    def _apply(self, move):
        cur = self.game.get_current_player(self.state)
        self.state = self.game.apply_move(self.state, cur, move)
        r = self.game.check_game_over(self.state)
        if r:
            self.game_over = True
            self.winner = r
            self.status = f"Game Over! {r.upper()} wins!"
        else:
            self.status = ""
        self._refresh()

    def _restart(self):
        self.state = self.game.create_initial_state()
        self.game_over = False
        self.winner = None
        self.status = ""
        self._refresh()

    def run(self):
        clock = pygame.time.Clock()
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self._click(*ev.pos)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_r:
                        self._restart()
            self._draw()
            pygame.display.flip()
            clock.tick(30)
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    display = BaoDisplay()
    display.run()
