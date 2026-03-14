#!/usr/bin/env python3
"""
Arimaa — Complete interactive board game (Human vs Human, local).
Requires: Python 3, Pygame.
"""

# ============================================================
# SECTION 1 — GAME LOGIC CLASS
# ============================================================

import copy


class ArimaaLogic:
    """Full Arimaa rule engine.  No display / Pygame references."""

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

    # ---- helpers ----
    @staticmethod
    def _owner(piece):
        if piece is None:
            return None
        return "gold" if piece.isupper() else "silver"

    @staticmethod
    def _enemy(player):
        return "silver" if player == "gold" else "gold"

    def _is_own(self, piece, player):
        if piece is None:
            return False
        return (player == "gold" and piece.isupper()) or (
            player == "silver" and piece.islower())

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
        t = "R" if player == "gold" else "r"
        n = 0
        for r in range(8):
            for c in range(8):
                if board[r][c] == t:
                    n += 1
        return n

    def _has_rabbit_on_goal(self, board, player):
        if player == "gold":
            row, ch = 7, "R"
        else:
            row, ch = 0, "r"
        for c in range(8):
            if board[row][c] == ch:
                return True
        return False

    @staticmethod
    def _rabbit_ok(player, dr):
        if player == "gold" and dr == -1:
            return False
        if player == "silver" and dr == 1:
            return False
        return True

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
        pk = bk + "|" + nxt
        cnt = 0
        for h in state["position_history"]:
            if h == pk:
                cnt += 1
        return cnt < 2

    # ---- public API ----
    def get_game_name(self):
        return "Arimaa"

    def get_num_players(self):
        return 2

    def create_initial_state(self):
        board = [[None] * 8 for _ in range(8)]
        return {
            "board": board,
            "phase": "setup_gold",
            "current_player": "gold",
            "pieces_to_place": list(self.GOLD_PIECES),
            "steps_remaining": 0,
            "steps_taken": 0,
            "turn_start_board": None,
            "position_history": [],
            "turn_just_ended": False,
        }

    # ---- legal moves ----
    def get_legal_moves(self, state, player):
        phase = state["phase"]
        if phase.startswith("setup"):
            return self._setup_moves(state, player)
        if phase == "play":
            return self._play_moves(state, player)
        return []

    def _setup_moves(self, state, player):
        board = state["board"]
        pieces = state["pieces_to_place"]
        if not pieces:
            return []
        if player == "gold":
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

                        pullable = []
                        for d in self.DIRS:
                            er, ec = r + d[0], c + d[1]
                            if not (0 <= er < 8 and 0 <= ec < 8):
                                continue
                            enemy = board[er][ec]
                            if enemy is not None and self._is_enemy_piece(enemy, player) and self.STRENGTH[enemy] < strength:
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

        if state["steps_taken"] > 0:
            bk = self._board_key(board)
            tsb = self._board_key(state["turn_start_board"])
            if bk != tsb:
                nxt = self._enemy(player)
                pk = bk + "|" + nxt
                cnt = 0
                for h in state["position_history"]:
                    if h == pk:
                        cnt += 1
                if cnt < 2:
                    moves.append(["end_turn"])
        return moves

    # ---- apply move ----
    def apply_move(self, state, player, move):
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

    def _do_place(self, s, move):
        piece, r, c = move[1], move[2], move[3]
        s["board"][r][c] = piece
        s["pieces_to_place"].remove(piece)
        if not s["pieces_to_place"]:
            if s["phase"] == "setup_gold":
                s["phase"] = "setup_silver"
                s["current_player"] = "silver"
                s["pieces_to_place"] = list(self.SILVER_PIECES)
            else:
                s["phase"] = "play"
                s["current_player"] = "gold"
                s["steps_remaining"] = 4
                s["steps_taken"] = 0
                s["turn_start_board"] = copy.deepcopy(s["board"])
        return s

    def _finish_turn(self, s, player):
        bk = self._board_key(s["board"])
        nxt = self._enemy(player)
        pk = bk + "|" + nxt
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

    # ---- game over ----
    def check_game_over(self, state):
        if state["phase"] != "play":
            return None
        if not state["turn_just_ended"]:
            return None
        board = state["board"]
        player_a = self._enemy(state["current_player"])
        player_b = state["current_player"]

        if self._has_rabbit_on_goal(board, player_a):
            return player_a
        if self._has_rabbit_on_goal(board, player_b):
            return player_b
        if self._count_rabbits(board, player_b) == 0:
            return player_a
        if self._count_rabbits(board, player_a) == 0:
            return player_b
        legal = self.get_legal_moves(state, player_b)
        if not legal:
            return player_a
        return None


# ============================================================
# SECTION 2 — DISPLAY AND INPUT (Pygame)
# ============================================================

import pygame, sys  # noqa: E402

CELL = 74
BOARD_OFF_X = 56
BOARD_OFF_Y = 62
BOARD_PX = CELL * 8
PANEL_X = BOARD_OFF_X + BOARD_PX + 20
PANEL_W = 280
WIN_W = PANEL_X + PANEL_W + 10
WIN_H = BOARD_OFF_Y + BOARD_PX + 44

COL_BG        = (30, 30, 36)
COL_LIGHT     = (240, 217, 181)
COL_DARK      = (181, 136, 99)
COL_TRAP_L    = (224, 180, 164)
COL_TRAP_D    = (178, 116, 96)
COL_GOLD_P    = (218, 170, 40)
COL_SILVER_P  = (165, 175, 190)
COL_SEL       = (80, 160, 255)
COL_TEXT       = (230, 230, 230)
COL_PANEL_BG  = (42, 42, 50)
COL_BTN       = (70, 130, 90)
COL_BTN_HOV   = (90, 160, 110)
COL_GOLD_BDR  = (155, 115, 8)
COL_SILVER_BDR= (90, 96, 110)

FILES = "abcdefgh"
PIECE_DISP = {"E":"E","M":"M","H":"H","D":"D","C":"C","R":"R",
              "e":"E","m":"M","h":"H","d":"D","c":"C","r":"R"}
TRAP_SET = frozenset([(2,2),(2,5),(5,2),(5,5)])

PIECE_UNICODE = {
    "E": "\u265A", "M": "\u265B", "H": "\u265C", "D": "\u265D", "C": "\u265E", "R": "\u265F",
}


def bts(r, c):
    """Board row/col to screen pixel top-left."""
    return BOARD_OFF_X + c * CELL, BOARD_OFF_Y + (7 - r) * CELL


def stb(mx, my):
    """Screen pixel to board row/col (or None,None)."""
    c = (mx - BOARD_OFF_X) // CELL
    r = 7 - (my - BOARD_OFF_Y) // CELL
    if 0 <= r < 8 and 0 <= c < 8:
        return r, c
    return None, None


class ArimaaUI:
    IDLE = 0; PIECE_SEL = 1; PUSH_DEST = 2; PULL_OPT = 3

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Arimaa")
        self.clock = pygame.time.Clock()
        self.logic = ArimaaLogic()
        self.state = self.logic.create_initial_state()
        self.winner = None

        self.fsm = pygame.font.SysFont("arial", 14, bold=True)
        self.fmd = pygame.font.SysFont("arial", 17, bold=True)
        self.flg = pygame.font.SysFont("arial", 24, bold=True)
        self.fpc = pygame.font.SysFont("arial", 30, bold=True)
        self.fxl = pygame.font.SysFont("arial", 38, bold=True)

        self.ui = self.IDLE
        self.sel = None          # (r,c) of selected piece
        self.sdests = []         # step destinations list
        self.ptargets = {}       # push targets dict (er,ec)->[[dest],...]
        self.push_info = None    # (pr,pc,er,ec,dests)
        self.pull_info = None    # (pr,pc,pdr,pdc,enemies)
        self.setup_sel = None    # selected setup piece char
        self.setup_rects = {}
        self.btn_end = None

        self.legal = self.logic.get_legal_moves(self.state, self.state["current_player"])

    def _refresh(self):
        self.legal = self.logic.get_legal_moves(self.state, self.state["current_player"])

    def _apply(self, move):
        player = self.state["current_player"]
        self.state = self.logic.apply_move(self.state, player, move)
        w = self.logic.check_game_over(self.state)
        if w:
            self.winner = w
        self._refresh()
        self.ui = self.IDLE
        self.sel = None
        self.push_info = None
        self.pull_info = None

    def _step_dests(self, r, c):
        return [[m[3], m[4]] for m in self.legal if m[0] == "step" and m[1] == r and m[2] == c]

    def _push_tgts(self, r, c):
        d = {}
        for m in self.legal:
            if m[0] == "push" and m[1] == r and m[2] == c:
                k = (m[3], m[4])
                d.setdefault(k, []).append([m[5], m[6]])
        return d

    def _pull_opts(self, pr, pc, pdr, pdc):
        return [[m[5], m[6]] for m in self.legal if m[0] == "pull" and m[1] == pr and m[2] == pc and m[3] == pdr and m[4] == pdc]

    def _has_end(self):
        return any(m[0] == "end_turn" for m in self.legal)

    # ---- draw ----
    def _draw_board(self):
        for r in range(8):
            for c in range(8):
                sx, sy = bts(r, c)
                trap = (r, c) in TRAP_SET
                if (r + c) % 2 == 0:
                    col = COL_TRAP_L if trap else COL_LIGHT
                else:
                    col = COL_TRAP_D if trap else COL_DARK
                pygame.draw.rect(self.screen, col, (sx, sy, CELL, CELL))
                if trap:
                    # small X marker
                    cx, cy = sx + CELL // 2, sy + CELL // 2
                    off = 8
                    pygame.draw.line(self.screen, (180, 60, 50, 100), (cx-off, cy-off), (cx+off, cy+off), 2)
                    pygame.draw.line(self.screen, (180, 60, 50, 100), (cx+off, cy-off), (cx-off, cy+off), 2)

        # border
        pygame.draw.rect(self.screen, (120, 100, 80), (BOARD_OFF_X-2, BOARD_OFF_Y-2, BOARD_PX+4, BOARD_PX+4), 2)

        # coordinates
        for c in range(8):
            sx = BOARD_OFF_X + c * CELL + CELL // 2
            for (yy, anchor) in [(BOARD_OFF_Y + BOARD_PX + 6, None), (BOARD_OFF_Y - 18, None)]:
                t = self.fsm.render(FILES[c], True, COL_TEXT)
                self.screen.blit(t, (sx - t.get_width() // 2, yy))
        for r in range(8):
            sy = BOARD_OFF_Y + (7 - r) * CELL + CELL // 2
            for xx in [BOARD_OFF_X - 22, BOARD_OFF_X + BOARD_PX + 8]:
                t = self.fsm.render(str(r + 1), True, COL_TEXT)
                self.screen.blit(t, (xx, sy - t.get_height() // 2))

    def _draw_highlight(self, r, c, color):
        sx, sy = bts(r, c)
        s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        s.fill(color)
        self.screen.blit(s, (sx, sy))

    def _draw_dot(self, r, c, color, radius=10):
        sx, sy = bts(r, c)
        s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        pygame.draw.circle(s, color, (CELL // 2, CELL // 2), radius)
        self.screen.blit(s, (sx, sy))

    def _draw_highlights(self):
        if self.ui == self.PIECE_SEL and self.sel:
            for d in self.sdests:
                self._draw_dot(d[0], d[1], (50, 200, 70, 150), 12)
            for k in self.ptargets:
                self._draw_highlight(k[0], k[1], (230, 120, 50, 100))

        elif self.ui == self.PUSH_DEST and self.push_info:
            _, _, er, ec, dests = self.push_info
            self._draw_highlight(er, ec, (230, 120, 50, 100))
            for d in dests:
                self._draw_dot(d[0], d[1], (240, 210, 50, 160), 12)

        elif self.ui == self.PULL_OPT and self.pull_info:
            pr, pc, pdr, pdc, enemies = self.pull_info
            self._draw_dot(pdr, pdc, (50, 200, 70, 150), 12)
            for e in enemies:
                self._draw_highlight(e[0], e[1], (180, 60, 200, 110))

        # Setup valid squares
        if self.state["phase"].startswith("setup") and self.setup_sel:
            player = self.state["current_player"]
            rows = [0, 1] if player == "gold" else [6, 7]
            board = self.state["board"]
            for r in rows:
                for c in range(8):
                    if board[r][c] is None:
                        self._draw_dot(r, c, (50, 200, 70, 120), 10)

    def _draw_pieces(self):
        board = self.state["board"]
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p is None:
                    continue
                sx, sy = bts(r, c)
                cx, cy = sx + CELL // 2, sy + CELL // 2
                rad = CELL // 2 - 7
                is_gold = p.isupper()
                base = COL_GOLD_P if is_gold else COL_SILVER_P
                bdr = COL_GOLD_BDR if is_gold else COL_SILVER_BDR

                if self.sel and self.sel[0] == r and self.sel[1] == c:
                    pygame.draw.circle(self.screen, COL_SEL, (cx, cy), rad + 4)

                pygame.draw.circle(self.screen, bdr, (cx, cy), rad + 1)
                pygame.draw.circle(self.screen, base, (cx, cy), rad)

                # gradient shading (simple top highlight)
                hl = pygame.Surface((rad*2, rad*2), pygame.SRCALPHA)
                pygame.draw.circle(hl, (255,255,255,40), (rad, rad - 4), rad - 4)
                self.screen.blit(hl, (cx - rad, cy - rad))

                # frozen ring
                if self.state["phase"] == "play" and self.logic._is_frozen(board, r, c):
                    pygame.draw.circle(self.screen, (60, 140, 230), (cx, cy), rad + 3, 3)

                txt_col = (30, 20, 5) if is_gold else (240, 242, 248)
                txt = self.fpc.render(PIECE_DISP[p], True, txt_col)
                self.screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

    def _draw_panel(self):
        pygame.draw.rect(self.screen, COL_PANEL_BG, (PANEL_X, 0, PANEL_W + 10, WIN_H))
        player = self.state["current_player"]
        phase = self.state["phase"]
        x0 = PANEL_X + 14
        y = 14

        self._txt(self.flg, "ARIMAA", x0, y, COL_TEXT); y += 34
        pcol = COL_GOLD_P if player == "gold" else COL_SILVER_P
        self._txt(self.fmd, f"{player.upper()}'s Turn", x0, y, pcol); y += 26

        if phase == "play":
            sr = self.state["steps_remaining"]
            st = self.state["steps_taken"]
            self._txt(self.fsm, f"Steps remaining: {sr}  (used: {st})", x0, y, (175,175,175)); y += 24

            for i in range(4):
                col = (80,200,100) if i < st else (70,70,80)
                pygame.draw.circle(self.screen, col, (x0 + 10 + i * 24, y + 8), 9)
                pygame.draw.circle(self.screen, (40,40,48), (x0 + 10 + i * 24, y + 8), 9, 1)
            y += 30

            self.btn_end = None
            if self._has_end():
                bw, bh = 160, 36
                mx, my = pygame.mouse.get_pos()
                hov = x0 <= mx < x0+bw and y <= my < y+bh
                col = COL_BTN_HOV if hov else COL_BTN
                rect = pygame.Rect(x0, y, bw, bh)
                pygame.draw.rect(self.screen, col, rect, border_radius=6)
                t = self.fmd.render("End Turn", True, (235,235,235))
                self.screen.blit(t, (x0 + bw//2 - t.get_width()//2, y + bh//2 - t.get_height()//2))
                self.btn_end = rect
            y += 48

            # piece counts
            self._txt(self.fsm, "Pieces:", x0, y, (155,155,155)); y += 20
            board = self.state["board"]
            for side, lab, col in [("gold","Gold",COL_GOLD_P),("silver","Silver",COL_SILVER_P)]:
                pc = {}
                for rr in range(8):
                    for cc in range(8):
                        pp = board[rr][cc]
                        if pp and self.logic._owner(pp) == side:
                            k = pp.upper()
                            pc[k] = pc.get(k,0)+1
                line = "  ".join(f"{k}{pc.get(k,0)}" for k in ["E","M","H","D","C","R"] if pc.get(k,0))
                self._txt(self.fsm, lab+":", x0, y, col); y += 17
                self._txt(self.fsm, line if line else "(none)", x0 + 4, y, (180,180,180)); y += 22

            y += 14
            hints = {
                self.IDLE: "Click your piece to select",
                self.PIECE_SEL: "Green = move destination\nOrange = enemy to push\nRight-click = cancel",
                self.PUSH_DEST: "Yellow = push destination\nRight-click = cancel",
                self.PULL_OPT: "Purple = pull this enemy\nRight-click = just move",
            }
            for line in hints.get(self.ui, "").split("\n"):
                self._txt(self.fsm, line, x0, y, (140,175,140)); y += 17

        elif phase.startswith("setup"):
            self._draw_setup_palette(x0, y)

    def _draw_setup_palette(self, x0, y0):
        pieces = self.state["pieces_to_place"]
        player = self.state["current_player"]
        if not pieces:
            return
        counts = {}
        for p in pieces:
            counts[p] = counts.get(p, 0) + 1

        self._txt(self.fmd, "Place your pieces", x0, y0, (200,200,200))
        y0 += 28
        valid = "Ranks 1-2" if player == "gold" else "Ranks 7-8"
        self._txt(self.fsm, f"Valid rows: {valid}", x0, y0, (160,160,160))
        y0 += 28

        order = ["E","M","H","D","C","R"] if player == "gold" else ["e","m","h","d","c","r"]
        self.setup_rects = {}
        idx = 0
        for p in order:
            if p not in counts:
                continue
            bx = x0 + (idx % 3) * 86
            by = y0 + (idx // 3) * 66
            w, h = 78, 54
            is_gold = p.isupper()
            base = COL_GOLD_P if is_gold else COL_SILVER_P
            bdr = COL_GOLD_BDR if is_gold else COL_SILVER_BDR
            rect = pygame.Rect(bx, by, w, h)
            self.setup_rects[p] = rect

            if self.setup_sel == p:
                pygame.draw.rect(self.screen, COL_SEL, rect.inflate(6,6), border_radius=7)
            pygame.draw.rect(self.screen, bdr, rect, border_radius=5)
            pygame.draw.rect(self.screen, base, rect.inflate(-3,-3), border_radius=4)

            tc = (30,20,5) if is_gold else (235,235,242)
            t1 = self.fpc.render(PIECE_DISP[p], True, tc)
            self.screen.blit(t1, (bx + 6, by + h//2 - t1.get_height()//2))
            t2 = self.fmd.render(f"x{counts[p]}", True, tc)
            self.screen.blit(t2, (bx + 40, by + h//2 - t2.get_height()//2))
            idx += 1

        y_hint = y0 + ((idx + 2) // 3) * 66 + 10
        self._txt(self.fsm, "Click piece, then board", x0, y_hint, (140,160,140))

    def _draw_game_over(self):
        if not self.winner:
            return
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,170))
        self.screen.blit(ov, (0,0))
        msg = f"{self.winner.upper()} WINS!"
        col = COL_GOLD_P if self.winner == "gold" else COL_SILVER_P
        t = self.fxl.render(msg, True, col)
        bx = WIN_W//2 - t.get_width()//2
        by = WIN_H//2 - t.get_height()//2 - 16
        pad = 32
        box = pygame.Rect(bx-pad, by-pad, t.get_width()+pad*2, t.get_height()+pad*2+36)
        pygame.draw.rect(self.screen, (20,20,30), box, border_radius=12)
        pygame.draw.rect(self.screen, col, box, 2, border_radius=12)
        self.screen.blit(t, (bx, by))
        sub = self.fmd.render("Press R to restart", True, (180,180,180))
        self.screen.blit(sub, (WIN_W//2 - sub.get_width()//2, by + t.get_height() + 14))

    def _txt(self, font, text, x, y, color):
        t = font.render(text, True, color)
        self.screen.blit(t, (x, y))

    # ---- input ----
    def _click(self, mx, my, btn):
        if self.winner:
            return

        phase = self.state["phase"]
        player = self.state["current_player"]
        board = self.state["board"]

        # End turn button
        if phase == "play" and self.btn_end and btn == 1 and self.btn_end.collidepoint(mx, my):
            self._apply(["end_turn"])
            return

        r, c = stb(mx, my)

        # ---- SETUP ----
        if phase.startswith("setup"):
            if btn != 1:
                return
            for p, rect in self.setup_rects.items():
                if rect.collidepoint(mx, my):
                    self.setup_sel = p
                    return
            if r is not None and self.setup_sel:
                valid_rows = [0,1] if player == "gold" else [6,7]
                if r in valid_rows and board[r][c] is None:
                    move = ["place", self.setup_sel, r, c]
                    if move in self.legal:
                        self._apply(move)
                        if self.setup_sel not in self.state.get("pieces_to_place", []):
                            self.setup_sel = None
            return

        if phase != "play" or r is None:
            return

        # Right-click: cancel / skip
        if btn == 3:
            if self.ui == self.PULL_OPT and self.pull_info:
                pr, pc, pdr, pdc, _ = self.pull_info
                self._apply(["step", pr, pc, pdr, pdc])
            else:
                self.ui = self.IDLE
                self.sel = None
                self.push_info = None
                self.pull_info = None
            return

        if btn != 1:
            return

        if self.ui == self.IDLE:
            p = board[r][c]
            if p and self.logic._is_own(p, player):
                sd = self._step_dests(r, c)
                pt = self._push_tgts(r, c)
                if sd or pt:
                    self.ui = self.PIECE_SEL
                    self.sel = (r, c)
                    self.sdests = sd
                    self.ptargets = pt

        elif self.ui == self.PIECE_SEL:
            sr, sc = self.sel
            for d in self.sdests:
                if d[0] == r and d[1] == c:
                    pulls = self._pull_opts(sr, sc, r, c)
                    if pulls and self.state["steps_remaining"] >= 2:
                        self.ui = self.PULL_OPT
                        self.pull_info = (sr, sc, r, c, pulls)
                    else:
                        self._apply(["step", sr, sc, r, c])
                    return
            if (r, c) in self.ptargets:
                self.ui = self.PUSH_DEST
                self.push_info = (sr, sc, r, c, self.ptargets[(r, c)])
                return
            # Re-select another own piece
            p = board[r][c]
            if p and self.logic._is_own(p, player):
                sd = self._step_dests(r, c)
                pt = self._push_tgts(r, c)
                if sd or pt:
                    self.sel = (r, c)
                    self.sdests = sd
                    self.ptargets = pt
                    return
            self.ui = self.IDLE
            self.sel = None

        elif self.ui == self.PUSH_DEST:
            if self.push_info:
                pr, pc, er, ec, dests = self.push_info
                for d in dests:
                    if d[0] == r and d[1] == c:
                        self._apply(["push", pr, pc, er, ec, r, c])
                        return
            self.ui = self.IDLE
            self.sel = None
            self.push_info = None

        elif self.ui == self.PULL_OPT:
            if self.pull_info:
                pr, pc, pdr, pdc, enemies = self.pull_info
                for e in enemies:
                    if e[0] == r and e[1] == c:
                        self._apply(["pull", pr, pc, pdr, pdc, r, c])
                        return
                # skip pull
                self._apply(["step", pr, pc, pdr, pdc])

    # ---- main loop ----
    def run(self):
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    self._click(ev.pos[0], ev.pos[1], ev.button)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        if self.ui != self.IDLE:
                            self.ui = self.IDLE
                            self.sel = None
                            self.push_info = None
                            self.pull_info = None
                        else:
                            running = False
                    elif ev.key == pygame.K_r and self.winner:
                        self.__init__()

            self.screen.fill(COL_BG)
            self._draw_board()
            self._draw_highlights()
            self._draw_pieces()
            self._draw_panel()
            self._draw_game_over()
            pygame.display.flip()
            self.clock.tick(30)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    ArimaaUI().run()
