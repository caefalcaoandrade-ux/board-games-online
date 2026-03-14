"""Arimaa — server-side game logic.

Implements the full Arimaa ruleset via the AbstractBoardGame interface.
No Pygame imports.  Players: 1 = Gold, 2 = Silver.
"""

import copy

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame


class ArimaaLogic(AbstractBoardGame):

    STRENGTH = {
        "E": 6, "M": 5, "H": 4, "D": 3, "C": 2, "R": 1,
        "e": 6, "m": 5, "h": 4, "d": 3, "c": 2, "r": 1,
    }
    TRAPS = [[2, 2], [2, 5], [5, 2], [5, 5]]
    DIRS = [[-1, 0], [1, 0], [0, -1], [0, 1]]
    GOLD_PIECES = ["R", "R", "R", "R", "R", "R", "R", "R",
                   "C", "C", "D", "D", "H", "H", "M", "E"]
    SILVER_PIECES = ["r", "r", "r", "r", "r", "r", "r", "r",
                     "c", "c", "d", "d", "h", "h", "m", "e"]

    # ── AbstractBoardGame interface ─────────────────────────────────────

    def _get_name(self):
        return "Arimaa"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [[None] * 8 for _ in range(8)]
        return {
            "board": board,
            "phase": "setup_gold",
            "current_player": 1,
            "pieces_to_place": list(self.GOLD_PIECES),
            "steps_remaining": 0,
            "steps_taken": 0,
            "turn_start_board": None,
            "position_history": [],
            "turn_just_ended": False,
        }

    def _get_current_player(self, state):
        return state["current_player"]

    def _get_legal_moves(self, state, player):
        phase = state["phase"]
        if phase.startswith("setup"):
            return self._setup_moves(state, player)
        if phase == "play":
            return self._play_moves(state, player)
        return []

    def _apply_move(self, state, player, move):
        ns = copy.deepcopy(state)
        ns["turn_just_ended"] = False
        action = move[0]
        if action == "place":
            return self._do_place(ns, move)
        if action == "step":
            return self._do_step(ns, player, move)
        if action == "push":
            return self._do_push(ns, player, move)
        if action == "pull":
            return self._do_pull(ns, player, move)
        if action == "end_turn":
            return self._do_end_turn(ns, player)
        return ns

    def _get_game_status(self, state):
        if state["phase"] != "play":
            return {"is_over": False, "winner": None, "is_draw": False}
        if not state.get("turn_just_ended", False):
            return {"is_over": False, "winner": None, "is_draw": False}

        board = state["board"]
        # player_a just finished their turn; player_b moves next
        player_b = state["current_player"]
        player_a = self._enemy(player_b)

        # Priority 1-2: goal
        if self._has_rabbit_on_goal(board, player_a):
            return {"is_over": True, "winner": player_a, "is_draw": False}
        if self._has_rabbit_on_goal(board, player_b):
            return {"is_over": True, "winner": player_b, "is_draw": False}
        # Priority 3-4: rabbit elimination
        if self._count_rabbits(board, player_b) == 0:
            return {"is_over": True, "winner": player_a, "is_draw": False}
        if self._count_rabbits(board, player_a) == 0:
            return {"is_over": True, "winner": player_b, "is_draw": False}
        # Priority 5-6: immobilization / forced repetition
        legal = self._get_legal_moves(state, player_b)
        if not legal:
            return {"is_over": True, "winner": player_a, "is_draw": False}

        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _owner(piece):
        if piece is None:
            return None
        return 1 if piece.isupper() else 2

    @staticmethod
    def _enemy(player):
        return 2 if player == 1 else 1

    def _is_own(self, piece, player):
        if piece is None:
            return False
        return (player == 1 and piece.isupper()) or (
            player == 2 and piece.islower())

    def _is_enemy_piece(self, piece, player):
        if piece is None:
            return False
        return not self._is_own(piece, player)

    def _adj(self, r, c):
        out = []
        for d in self.DIRS:
            nr, nc = r + d[0], c + d[1]
            if 0 <= nr < 8 and 0 <= nc < 8:
                out.append([nr, nc])
        return out

    def _is_frozen(self, board, r, c):
        piece = board[r][c]
        if piece is None:
            return False
        owner = self._owner(piece)
        strength = self.STRENGTH[piece]
        stronger_enemy = False
        friendly_near = False
        for nr, nc in self._adj(r, c):
            adj = board[nr][nc]
            if adj is not None:
                if self._owner(adj) != owner and self.STRENGTH[adj] > strength:
                    stronger_enemy = True
                if self._owner(adj) == owner:
                    friendly_near = True
        return stronger_enemy and not friendly_near

    def _apply_traps(self, board):
        captured = []
        for t in self.TRAPS:
            tr, tc = t[0], t[1]
            piece = board[tr][tc]
            if piece is None:
                continue
            owner = self._owner(piece)
            supported = False
            for nr, nc in self._adj(tr, tc):
                a = board[nr][nc]
                if a is not None and self._owner(a) == owner:
                    supported = True
                    break
            if not supported:
                captured.append([piece, tr, tc])
                board[tr][tc] = None
        return captured

    @staticmethod
    def _board_key(board):
        parts = []
        for r in range(8):
            for c in range(8):
                parts.append(board[r][c] if board[r][c] else ".")
        return "".join(parts)

    def _count_rabbits(self, board, player):
        ch = "R" if player == 1 else "r"
        n = 0
        for r in range(8):
            for c in range(8):
                if board[r][c] == ch:
                    n += 1
        return n

    def _has_rabbit_on_goal(self, board, player):
        if player == 1:
            row, ch = 7, "R"
        else:
            row, ch = 0, "r"
        for c in range(8):
            if board[row][c] == ch:
                return True
        return False

    @staticmethod
    def _rabbit_ok(player, dr):
        if player == 1 and dr == -1:
            return False
        if player == 2 and dr == 1:
            return False
        return True

    # ── Simulation (for legality checks) ────────────────────────────────

    def _sim_step(self, board, fr, fc, tr, tc):
        b = copy.deepcopy(board)
        b[tr][tc] = b[fr][fc]
        b[fr][fc] = None
        self._apply_traps(b)
        return b

    def _sim_push(self, board, pr, pc, er, ec, edr, edc):
        b = copy.deepcopy(board)
        b[edr][edc] = b[er][ec]
        b[er][ec] = None
        self._apply_traps(b)
        b[er][ec] = b[pr][pc]
        b[pr][pc] = None
        self._apply_traps(b)
        return b

    def _sim_pull(self, board, pr, pc, pdr, pdc, er, ec):
        b = copy.deepcopy(board)
        b[pdr][pdc] = b[pr][pc]
        b[pr][pc] = None
        self._apply_traps(b)
        b[pr][pc] = b[er][ec]
        b[er][ec] = None
        self._apply_traps(b)
        return b

    def _end_legal(self, state, new_board, player):
        bk = self._board_key(new_board)
        if bk == self._board_key(state["turn_start_board"]):
            return False
        nxt = self._enemy(player)
        pk = bk + "|" + str(nxt)
        cnt = 0
        for h in state["position_history"]:
            if h == pk:
                cnt += 1
        return cnt < 2

    # ── Legal-move generation ───────────────────────────────────────────

    def _setup_moves(self, state, player):
        board = state["board"]
        pieces = state["pieces_to_place"]
        if not pieces:
            return []
        if player == 1:
            rows = [0, 1]
        else:
            rows = [6, 7]
        seen = {}
        for p in pieces:
            seen[p] = True
        moves = []
        for piece in seen:
            for r in rows:
                for c in range(8):
                    if board[r][c] is None:
                        moves.append(["place", piece, r, c])
        return moves

    def _play_moves(self, state, player):
        if state["current_player"] != player:
            return []
        board = state["board"]
        steps = state["steps_remaining"]
        moves = []
        last_step = (steps == 1)
        last_two = (steps == 2)

        if steps > 0:
            for r in range(8):
                for c in range(8):
                    piece = board[r][c]
                    if piece is None or not self._is_own(piece, player):
                        continue
                    if self._is_frozen(board, r, c):
                        continue
                    strength = self.STRENGTH[piece]
                    is_rabbit = (piece.upper() == "R")

                    # Ordinary steps
                    for d in self.DIRS:
                        nr, nc = r + d[0], c + d[1]
                        if not (0 <= nr < 8 and 0 <= nc < 8):
                            continue
                        if board[nr][nc] is not None:
                            continue
                        if is_rabbit and not self._rabbit_ok(player, d[0]):
                            continue
                        if last_step:
                            sb = self._sim_step(board, r, c, nr, nc)
                            if not self._end_legal(state, sb, player):
                                continue
                        moves.append(["step", r, c, nr, nc])

                    # Pushes (need >= 2 steps)
                    if steps >= 2:
                        for d in self.DIRS:
                            er, ec = r + d[0], c + d[1]
                            if not (0 <= er < 8 and 0 <= ec < 8):
                                continue
                            enemy = board[er][ec]
                            if enemy is None or not self._is_enemy_piece(enemy, player):
                                continue
                            if self.STRENGTH[enemy] >= strength:
                                continue
                            for d2 in self.DIRS:
                                edr, edc = er + d2[0], ec + d2[1]
                                if not (0 <= edr < 8 and 0 <= edc < 8):
                                    continue
                                if board[edr][edc] is not None:
                                    continue
                                if last_two:
                                    sb = self._sim_push(board, r, c, er, ec, edr, edc)
                                    if not self._end_legal(state, sb, player):
                                        continue
                                moves.append(["push", r, c, er, ec, edr, edc])

                        # Pulls (need >= 2 steps)
                        pullable = []
                        for d in self.DIRS:
                            er, ec = r + d[0], c + d[1]
                            if not (0 <= er < 8 and 0 <= ec < 8):
                                continue
                            enemy = board[er][ec]
                            if (enemy is not None
                                    and self._is_enemy_piece(enemy, player)
                                    and self.STRENGTH[enemy] < strength):
                                pullable.append([er, ec])
                        if pullable:
                            for d in self.DIRS:
                                nr, nc = r + d[0], c + d[1]
                                if not (0 <= nr < 8 and 0 <= nc < 8):
                                    continue
                                if board[nr][nc] is not None:
                                    continue
                                if is_rabbit and not self._rabbit_ok(player, d[0]):
                                    continue
                                for ep in pullable:
                                    if last_two:
                                        sb = self._sim_pull(board, r, c, nr, nc, ep[0], ep[1])
                                        if not self._end_legal(state, sb, player):
                                            continue
                                    moves.append(["pull", r, c, nr, nc, ep[0], ep[1]])

        # End turn (must have taken >= 1 step, net position change, no 3rd repetition)
        if state["steps_taken"] > 0:
            bk = self._board_key(board)
            tsb = self._board_key(state["turn_start_board"])
            if bk != tsb:
                nxt = self._enemy(player)
                pk = bk + "|" + str(nxt)
                cnt = 0
                for h in state["position_history"]:
                    if h == pk:
                        cnt += 1
                if cnt < 2:
                    moves.append(["end_turn"])
        return moves

    # ── Move application ────────────────────────────────────────────────

    def _do_place(self, s, move):
        piece, r, c = move[1], move[2], move[3]
        s["board"][r][c] = piece
        s["pieces_to_place"].remove(piece)
        if not s["pieces_to_place"]:
            if s["phase"] == "setup_gold":
                s["phase"] = "setup_silver"
                s["current_player"] = 2
                s["pieces_to_place"] = list(self.SILVER_PIECES)
            else:
                s["phase"] = "play"
                s["current_player"] = 1
                s["steps_remaining"] = 4
                s["steps_taken"] = 0
                s["turn_start_board"] = copy.deepcopy(s["board"])
        return s

    def _finish_turn(self, s, player):
        bk = self._board_key(s["board"])
        nxt = self._enemy(player)
        pk = bk + "|" + str(nxt)
        s["position_history"].append(pk)
        s["current_player"] = nxt
        s["steps_remaining"] = 4
        s["steps_taken"] = 0
        s["turn_start_board"] = copy.deepcopy(s["board"])
        s["turn_just_ended"] = True

    def _do_step(self, s, player, move):
        b = s["board"]
        fr, fc, tr, tc = move[1], move[2], move[3], move[4]
        b[tr][tc] = b[fr][fc]
        b[fr][fc] = None
        self._apply_traps(b)
        s["steps_remaining"] -= 1
        s["steps_taken"] += 1
        if s["steps_remaining"] == 0:
            self._finish_turn(s, player)
        return s

    def _do_push(self, s, player, move):
        b = s["board"]
        pr, pc, er, ec, edr, edc = move[1], move[2], move[3], move[4], move[5], move[6]
        b[edr][edc] = b[er][ec]
        b[er][ec] = None
        self._apply_traps(b)
        b[er][ec] = b[pr][pc]
        b[pr][pc] = None
        self._apply_traps(b)
        s["steps_remaining"] -= 2
        s["steps_taken"] += 2
        if s["steps_remaining"] == 0:
            self._finish_turn(s, player)
        return s

    def _do_pull(self, s, player, move):
        b = s["board"]
        pr, pc, pdr, pdc, er, ec = move[1], move[2], move[3], move[4], move[5], move[6]
        b[pdr][pdc] = b[pr][pc]
        b[pr][pc] = None
        self._apply_traps(b)
        b[pr][pc] = b[er][ec]
        b[er][ec] = None
        self._apply_traps(b)
        s["steps_remaining"] -= 2
        s["steps_taken"] += 2
        if s["steps_remaining"] == 0:
            self._finish_turn(s, player)
        return s

    def _do_end_turn(self, s, player):
        self._finish_turn(s, player)
        return s
