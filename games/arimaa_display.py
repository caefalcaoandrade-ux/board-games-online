"""
Arimaa — Pygame display and local hotseat play.

Controls: Left-click to select/move pieces.  Right-click to cancel / skip pull.
          F: flip board.  R: restart (local).  Esc/Q: quit.
"""

import copy
import sys
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.arimaa_logic import ArimaaLogic
except ImportError:
    from arimaa_logic import ArimaaLogic

# ── Display Constants ────────────────────────────────────────────────────────

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
COL_SILVER_BDR = (90, 96, 110)
COL_HINT      = (140, 175, 140)
COL_DIM       = (175, 175, 175)
COL_WIN_TXT   = (255, 215, 50)

FILES = "abcdefgh"
PIECE_DISP = {
    "E": "E", "M": "M", "H": "H", "D": "D", "C": "C", "R": "R",
    "e": "E", "m": "M", "h": "H", "d": "D", "c": "C", "r": "R",
}
TRAP_SET = frozenset([(2, 2), (2, 5), (5, 2), (5, 5)])

# UI FSM states
IDLE = 0
PIECE_SEL = 1
PUSH_DEST = 2
PULL_OPT = 3


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side game state and input handling."""

    def __init__(self, online=False, my_player=None):
        self.logic = ArimaaLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._cancel()
        self.setup_sel = None
        self._game_over_message = None
        self._refresh_legal()

    def _cancel(self):
        self.ui = IDLE
        self.sel = None
        self.sdests = []
        self.ptargets = {}
        self.push_info = None
        self.pull_info = None

    def _refresh_legal(self):
        self.legal = self.logic.get_legal_moves(
            self.state, self.state["current_player"])

    # ── Online mode helpers ──────────────────────────────────────────────

    @property
    def is_my_turn(self):
        if not self.online:
            return True
        return self.state["current_player"] == self.my_player

    def load_state(self, state):
        self.state = state
        self._status = self.logic.get_game_status(state)
        self._cancel()
        self.setup_sel = None
        self._game_over_message = None
        self.net_error = ""
        self._refresh_legal()

    def set_game_over(self, winner, is_draw, reason=""):
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            name = "Gold" if winner == 1 else "Silver"
            self._game_over_message = f"{name} wins by forfeit!"
        else:
            self._game_over_message = None

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def current_player(self):
        return self.state["current_player"]

    @property
    def phase(self):
        return self.state["phase"]

    @property
    def board(self):
        return self.state["board"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def steps_remaining(self):
        return self.state["steps_remaining"]

    @property
    def steps_taken(self):
        return self.state["steps_taken"]

    @property
    def pieces_to_place(self):
        return self.state.get("pieces_to_place", [])

    # ── Derived data for highlights ──────────────────────────────────────

    def _step_dests(self, r, c):
        return [[m[3], m[4]] for m in self.legal
                if m[0] == "step" and m[1] == r and m[2] == c]

    def _push_tgts(self, r, c):
        d = {}
        for m in self.legal:
            if m[0] == "push" and m[1] == r and m[2] == c:
                k = (m[3], m[4])
                d.setdefault(k, []).append([m[5], m[6]])
        return d

    def _pull_opts(self, pr, pc, pdr, pdc):
        return [[m[5], m[6]] for m in self.legal
                if m[0] == "pull" and m[1] == pr and m[2] == pc
                and m[3] == pdr and m[4] == pdc]

    def has_end_turn(self):
        return any(m[0] == "end_turn" for m in self.legal)

    # ── Move application (local mode only) ───────────────────────────────

    def _apply_local(self, move):
        player = self.state["current_player"]
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        self._cancel()
        self._refresh_legal()

    # ── Click handling ───────────────────────────────────────────────────

    def click_setup_piece(self, piece):
        """Select a piece from the setup palette."""
        self.setup_sel = piece

    def click_end_turn(self):
        """End turn early.  Returns the move in online mode, else None."""
        if not self.has_end_turn():
            return None
        move = ["end_turn"]
        if self.online:
            return move
        self._apply_local(move)
        return None

    def click(self, r, c, button=1):
        """Handle a board click.  Returns a move to send in online mode."""
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None

        phase = self.state["phase"]
        if phase.startswith("setup"):
            return self._click_setup(r, c, button)
        if phase == "play":
            return self._click_play(r, c, button)
        return None

    def _click_setup(self, r, c, button):
        if button != 1 or self.setup_sel is None:
            return None
        player = self.state["current_player"]
        board = self.state["board"]
        valid_rows = [0, 1] if player == 1 else [6, 7]
        if r in valid_rows and board[r][c] is None:
            move = ["place", self.setup_sel, r, c]
            if move in self.legal:
                if self.online:
                    return move
                self._apply_local(move)
                if self.setup_sel not in self.pieces_to_place:
                    self.setup_sel = None
        return None

    def _click_play(self, r, c, button):
        player = self.state["current_player"]
        board = self.state["board"]

        # Right-click: cancel or skip pull (just step)
        if button == 3:
            if self.ui == PULL_OPT and self.pull_info:
                pr, pc, pdr, pdc, _ = self.pull_info
                move = ["step", pr, pc, pdr, pdc]
                self._cancel()
                if self.online:
                    return move
                self._apply_local(move)
                return None
            self._cancel()
            return None

        if button != 1:
            return None

        if self.ui == IDLE:
            p = board[r][c]
            if p and self.logic._is_own(p, player):
                sd = self._step_dests(r, c)
                pt = self._push_tgts(r, c)
                if sd or pt:
                    self.ui = PIECE_SEL
                    self.sel = (r, c)
                    self.sdests = sd
                    self.ptargets = pt
            return None

        elif self.ui == PIECE_SEL:
            sr, sc = self.sel
            # Step destination?
            for d in self.sdests:
                if d[0] == r and d[1] == c:
                    pulls = self._pull_opts(sr, sc, r, c)
                    if pulls and self.state["steps_remaining"] >= 2:
                        self.ui = PULL_OPT
                        self.pull_info = (sr, sc, r, c, pulls)
                        return None
                    move = ["step", sr, sc, r, c]
                    self._cancel()
                    if self.online:
                        return move
                    self._apply_local(move)
                    return None
            # Push target?
            if (r, c) in self.ptargets:
                self.ui = PUSH_DEST
                self.push_info = (sr, sc, r, c, self.ptargets[(r, c)])
                return None
            # Re-select another piece
            p = board[r][c]
            if p and self.logic._is_own(p, player):
                sd = self._step_dests(r, c)
                pt = self._push_tgts(r, c)
                if sd or pt:
                    self.sel = (r, c)
                    self.sdests = sd
                    self.ptargets = pt
                    return None
            self._cancel()
            return None

        elif self.ui == PUSH_DEST:
            if self.push_info:
                pr, pc, er, ec, dests = self.push_info
                for d in dests:
                    if d[0] == r and d[1] == c:
                        move = ["push", pr, pc, er, ec, r, c]
                        self._cancel()
                        if self.online:
                            return move
                        self._apply_local(move)
                        return None
            self._cancel()
            return None

        elif self.ui == PULL_OPT:
            if self.pull_info:
                pr, pc, pdr, pdc, enemies = self.pull_info
                for e in enemies:
                    if e[0] == r and e[1] == c:
                        move = ["pull", pr, pc, pdr, pdc, r, c]
                        self._cancel()
                        if self.online:
                            return move
                        self._apply_local(move)
                        return None
                # Click elsewhere: just step without pulling
                move = ["step", pr, pc, pdr, pdc]
                self._cancel()
                if self.online:
                    return move
                self._apply_local(move)
                return None

        return None


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        # Neutralise UI state
        self.ui = IDLE
        self.sel = None
        self.sdests = []
        self.ptargets = {}
        self.push_info = None
        self.pull_info = None
        self.setup_sel = None

    @property
    def current_player(self):
        return self.state["current_player"]

    @property
    def phase(self):
        return self.state["phase"]

    @property
    def board(self):
        return self.state["board"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def steps_remaining(self):
        return self.state["steps_remaining"]

    @property
    def steps_taken(self):
        return self.state["steps_taken"]

    @property
    def pieces_to_place(self):
        return self.state.get("pieces_to_place", [])

    def has_end_turn(self):
        return False


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    """Handles all drawing."""

    def __init__(self, screen):
        self.screen = screen
        self.flipped = False
        self.fsm = pygame.font.SysFont("arial", 14, bold=True)
        self.fmd = pygame.font.SysFont("arial", 17, bold=True)
        self.flg = pygame.font.SysFont("arial", 24, bold=True)
        self.fpc = pygame.font.SysFont("arial", 30, bold=True)
        self.fxl = pygame.font.SysFont("arial", 38, bold=True)
        self.fhint = pygame.font.SysFont("monospace", 13)
        self._hl = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        self.btn_end = None
        self.setup_rects = {}

    # ── Coordinate helpers ───────────────────────────────────────────────

    def _sq_px(self, r, c):
        if self.flipped:
            return BOARD_OFF_X + (7 - c) * CELL, BOARD_OFF_Y + r * CELL
        return BOARD_OFF_X + c * CELL, BOARD_OFF_Y + (7 - r) * CELL

    def _sq_center(self, r, c):
        x, y = self._sq_px(r, c)
        return x + CELL // 2, y + CELL // 2

    def pixel_to_cell(self, mx, my):
        bx = mx - BOARD_OFF_X
        by = my - BOARD_OFF_Y
        if bx < 0 or by < 0 or bx >= BOARD_PX or by >= BOARD_PX:
            return None
        gc = bx // CELL
        gr = by // CELL
        if self.flipped:
            return gr, 7 - gc
        return 7 - gr, gc

    # ── Drawing primitives ───────────────────────────────────────────────

    def _fill_sq(self, r, c, rgba):
        self._hl.fill(rgba)
        self.screen.blit(self._hl, self._sq_px(r, c))

    def _draw_dot(self, r, c, color, radius=10):
        cx, cy = self._sq_center(r, c)
        s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        pygame.draw.circle(s, color, (CELL // 2, CELL // 2), radius)
        self.screen.blit(s, self._sq_px(r, c))

    def _txt(self, font, text, x, y, color):
        t = font.render(text, True, color)
        self.screen.blit(t, (x, y))

    # ── Main draw ────────────────────────────────────────────────────────

    def draw(self, game, mouse_pos):
        scr = self.screen
        scr.fill(COL_BG)

        self._draw_board()
        self._draw_highlights(game)
        self._draw_pieces(game)
        self._draw_coords()
        self._draw_panel(game)
        self._draw_game_over(game)

        if game.online:
            self._draw_online_status(game)

    # ── Board ────────────────────────────────────────────────────────────

    def _draw_board(self):
        for r in range(8):
            for c in range(8):
                sx, sy = self._sq_px(r, c)
                trap = (r, c) in TRAP_SET
                if (r + c) % 2 == 0:
                    col = COL_TRAP_L if trap else COL_LIGHT
                else:
                    col = COL_TRAP_D if trap else COL_DARK
                pygame.draw.rect(self.screen, col, (sx, sy, CELL, CELL))
                if trap:
                    cx, cy = sx + CELL // 2, sy + CELL // 2
                    off = 8
                    tc = (180, 60, 50, 100)
                    pygame.draw.line(self.screen, tc,
                                     (cx - off, cy - off), (cx + off, cy + off), 2)
                    pygame.draw.line(self.screen, tc,
                                     (cx + off, cy - off), (cx - off, cy + off), 2)
        pygame.draw.rect(self.screen, (120, 100, 80),
                         (BOARD_OFF_X - 2, BOARD_OFF_Y - 2,
                          BOARD_PX + 4, BOARD_PX + 4), 2)

    def _draw_coords(self):
        for i in range(8):
            # Files
            f_idx = (7 - i) if self.flipped else i
            lbl = self.fsm.render(FILES[f_idx], True, COL_TEXT)
            sx = BOARD_OFF_X + i * CELL + CELL // 2
            self.screen.blit(lbl, (sx - lbl.get_width() // 2,
                                   BOARD_OFF_Y + BOARD_PX + 6))
            self.screen.blit(lbl, (sx - lbl.get_width() // 2,
                                   BOARD_OFF_Y - 18))
            # Ranks
            rank_num = (i + 1) if self.flipped else (8 - i)
            lbl = self.fsm.render(str(rank_num), True, COL_TEXT)
            sy = BOARD_OFF_Y + i * CELL + CELL // 2
            self.screen.blit(lbl, (BOARD_OFF_X - 22,
                                   sy - lbl.get_height() // 2))
            self.screen.blit(lbl, (BOARD_OFF_X + BOARD_PX + 8,
                                   sy - lbl.get_height() // 2))

    # ── Highlights ───────────────────────────────────────────────────────

    def _draw_highlights(self, game):
        if game.ui == PIECE_SEL and game.sel:
            self._fill_sq(game.sel[0], game.sel[1], (80, 160, 255, 70))
            for d in game.sdests:
                self._draw_dot(d[0], d[1], (50, 200, 70, 150), 12)
            for k in game.ptargets:
                self._fill_sq(k[0], k[1], (230, 120, 50, 100))

        elif game.ui == PUSH_DEST and game.push_info:
            _, _, er, ec, dests = game.push_info
            self._fill_sq(er, ec, (230, 120, 50, 100))
            for d in dests:
                self._draw_dot(d[0], d[1], (240, 210, 50, 160), 12)

        elif game.ui == PULL_OPT and game.pull_info:
            pr, pc, pdr, pdc, enemies = game.pull_info
            self._draw_dot(pdr, pdc, (50, 200, 70, 150), 12)
            for e in enemies:
                self._fill_sq(e[0], e[1], (180, 60, 200, 110))

        # Setup valid squares
        if game.phase.startswith("setup") and game.setup_sel:
            player = game.current_player
            rows = [0, 1] if player == 1 else [6, 7]
            board = game.board
            for r in rows:
                for c in range(8):
                    if board[r][c] is None:
                        self._draw_dot(r, c, (50, 200, 70, 120), 10)

    # ── Pieces ───────────────────────────────────────────────────────────

    def _draw_pieces(self, game):
        board = game.board
        logic = ArimaaLogic()
        for r in range(8):
            for c in range(8):
                p = board[r][c]
                if p is None:
                    continue
                cx, cy = self._sq_center(r, c)
                rad = CELL // 2 - 7
                is_gold = p.isupper()
                base = COL_GOLD_P if is_gold else COL_SILVER_P
                bdr = COL_GOLD_BDR if is_gold else COL_SILVER_BDR

                if game.sel and game.sel[0] == r and game.sel[1] == c:
                    pygame.draw.circle(self.screen, COL_SEL, (cx, cy), rad + 4)

                pygame.draw.circle(self.screen, bdr, (cx, cy), rad + 1)
                pygame.draw.circle(self.screen, base, (cx, cy), rad)

                # Frozen ring
                if game.phase == "play" and logic._is_frozen(board, r, c):
                    pygame.draw.circle(self.screen, (60, 140, 230),
                                       (cx, cy), rad + 3, 3)

                txt_col = (30, 20, 5) if is_gold else (240, 242, 248)
                txt = self.fpc.render(PIECE_DISP[p], True, txt_col)
                self.screen.blit(txt, (cx - txt.get_width() // 2,
                                       cy - txt.get_height() // 2))

    # ── Side panel ───────────────────────────────────────────────────────

    def _draw_panel(self, game):
        scr = self.screen
        pygame.draw.rect(scr, COL_PANEL_BG,
                         (PANEL_X, 0, PANEL_W + 10, WIN_H))
        player = game.current_player
        phase = game.phase
        x0 = PANEL_X + 14
        y = 14

        self._txt(self.flg, "ARIMAA", x0, y, COL_TEXT)
        y += 34
        pcol = COL_GOLD_P if player == 1 else COL_SILVER_P
        pname = "GOLD" if player == 1 else "SILVER"
        self._txt(self.fmd, f"{pname}'s Turn", x0, y, pcol)
        y += 26

        if phase == "play":
            sr = game.steps_remaining
            st = game.steps_taken
            self._txt(self.fsm, f"Steps remaining: {sr}  (used: {st})",
                      x0, y, COL_DIM)
            y += 24

            for i in range(4):
                col = (80, 200, 100) if i < st else (70, 70, 80)
                pygame.draw.circle(scr, col, (x0 + 10 + i * 24, y + 8), 9)
                pygame.draw.circle(scr, (40, 40, 48),
                                   (x0 + 10 + i * 24, y + 8), 9, 1)
            y += 30

            # End Turn button
            self.btn_end = None
            if game.has_end_turn():
                bw, bh = 160, 36
                mx, my = pygame.mouse.get_pos()
                hov = x0 <= mx < x0 + bw and y <= my < y + bh
                col = COL_BTN_HOV if hov else COL_BTN
                rect = pygame.Rect(x0, y, bw, bh)
                pygame.draw.rect(scr, col, rect, border_radius=6)
                t = self.fmd.render("End Turn", True, (235, 235, 235))
                scr.blit(t, (x0 + bw // 2 - t.get_width() // 2,
                             y + bh // 2 - t.get_height() // 2))
                self.btn_end = rect
            y += 48

            # Piece counts
            self._txt(self.fsm, "Pieces:", x0, y, (155, 155, 155))
            y += 20
            board = game.board
            for side, lab, col in [(1, "Gold", COL_GOLD_P),
                                   (2, "Silver", COL_SILVER_P)]:
                pc = {}
                for rr in range(8):
                    for cc in range(8):
                        pp = board[rr][cc]
                        if pp and ArimaaLogic._owner(pp) == side:
                            k = pp.upper()
                            pc[k] = pc.get(k, 0) + 1
                line = "  ".join(
                    f"{k}{pc.get(k, 0)}"
                    for k in ["E", "M", "H", "D", "C", "R"] if pc.get(k, 0))
                self._txt(self.fsm, lab + ":", x0, y, col)
                y += 17
                self._txt(self.fsm, line if line else "(none)",
                          x0 + 4, y, (180, 180, 180))
                y += 22

            y += 14
            hints = {
                IDLE: "Click your piece to select",
                PIECE_SEL: "Green=move  Orange=push\nRight-click=cancel",
                PUSH_DEST: "Yellow=push destination\nRight-click=cancel",
                PULL_OPT: "Purple=pull enemy\nRight-click=just move",
            }
            for line in hints.get(game.ui, "").split("\n"):
                self._txt(self.fsm, line, x0, y, COL_HINT)
                y += 17

        elif phase.startswith("setup"):
            self._draw_setup_palette(game, x0, y)

        # Role indicator (online)
        if game.online:
            name = "Gold" if game.my_player == 1 else "Silver"
            acol = COL_GOLD_P if game.my_player == 1 else COL_SILVER_P
            tag = self.fhint.render(f"You: {name}", True, acol)
            scr.blit(tag, (PANEL_X + PANEL_W - tag.get_width(),
                           WIN_H - 28))

    def _draw_setup_palette(self, game, x0, y0):
        pieces = game.pieces_to_place
        player = game.current_player
        if not pieces:
            return
        counts = {}
        for p in pieces:
            counts[p] = counts.get(p, 0) + 1

        self._txt(self.fmd, "Place your pieces", x0, y0, (200, 200, 200))
        y0 += 28
        valid = "Ranks 1-2" if player == 1 else "Ranks 7-8"
        self._txt(self.fsm, f"Valid rows: {valid}", x0, y0, (160, 160, 160))
        y0 += 28

        order = (["E", "M", "H", "D", "C", "R"] if player == 1
                 else ["e", "m", "h", "d", "c", "r"])
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

            if game.setup_sel == p:
                pygame.draw.rect(self.screen, COL_SEL,
                                 rect.inflate(6, 6), border_radius=7)
            pygame.draw.rect(self.screen, bdr, rect, border_radius=5)
            pygame.draw.rect(self.screen, base,
                             rect.inflate(-3, -3), border_radius=4)

            tc = (30, 20, 5) if is_gold else (235, 235, 242)
            t1 = self.fpc.render(PIECE_DISP[p], True, tc)
            self.screen.blit(t1, (bx + 6, by + h // 2 - t1.get_height() // 2))
            t2 = self.fmd.render(f"x{counts[p]}", True, tc)
            self.screen.blit(t2, (bx + 40, by + h // 2 - t2.get_height() // 2))
            idx += 1

        y_hint = y0 + ((idx + 2) // 3) * 66 + 10
        self._txt(self.fsm, "Click piece, then board", x0, y_hint, COL_HINT)

    # ── Game over overlay ────────────────────────────────────────────────

    def _draw_game_over(self, game):
        if not game.game_over:
            return
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        self.screen.blit(ov, (0, 0))

        if game._game_over_message:
            msg = game._game_over_message
        elif game.winner is not None:
            name = "GOLD" if game.winner == 1 else "SILVER"
            msg = f"{name} WINS!"
        else:
            msg = "Game Over"

        col = COL_GOLD_P if game.winner == 1 else COL_SILVER_P
        t = self.fxl.render(msg, True, col)
        bx = WIN_W // 2 - t.get_width() // 2
        by = WIN_H // 2 - t.get_height() // 2 - 16
        pad = 32
        box = pygame.Rect(bx - pad, by - pad,
                          t.get_width() + pad * 2, t.get_height() + pad * 2 + 36)
        pygame.draw.rect(self.screen, (20, 20, 30), box, border_radius=12)
        pygame.draw.rect(self.screen, col, box, 2, border_radius=12)
        self.screen.blit(t, (bx, by))

        if game.online:
            you_won = game.winner == game.my_player
            sub_text = "You win!" if you_won else "You lose."
            sub = self.fhint.render(
                f"{sub_text}  Press Esc to exit", True, (180, 180, 180))
        else:
            sub = self.fhint.render(
                "Press R to restart", True, (180, 180, 180))
        self.screen.blit(sub, (WIN_W // 2 - sub.get_width() // 2,
                               by + t.get_height() + 14))

    # ── Online overlays ──────────────────────────────────────────────────

    def _draw_online_status(self, game):
        if not game.game_over and not game.is_my_turn:
            wait = self.fhint.render(
                "Opponent's turn \u2014 waiting\u2026", True, COL_DIM)
            self.screen.blit(wait, (PANEL_X + 14, WIN_H - 28))

        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, COL_BG,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.fmd.render("Opponent disconnected", True, COL_TEXT)
            self.screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.fhint.render(
                "Waiting for reconnection\u2026", True, COL_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.fhint.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Arimaa in online multiplayer mode."""
    try:
        from client.shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )
    except ImportError:
        from shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Arimaa \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        # ── Poll network ─────────────────────────────────────────────
        for msg in net.poll_messages():
            mtype = msg.get("type")
            if mtype == "move_made":
                game.load_state(msg["state"])
                hist.push(msg["state"])
            elif mtype == "game_over":
                game.load_state(msg["state"])
                hist.push(msg["state"])
                game.set_game_over(
                    msg.get("winner"),
                    msg.get("is_draw", False),
                    msg.get("reason", ""),
                )
            elif mtype == "player_disconnected":
                game.opponent_disconnected = True
            elif mtype == "player_reconnected":
                game.opponent_disconnected = False
            elif mtype == "error":
                game.net_error = msg.get("message", "Server error")
            elif mtype in ("connection_error", "connection_closed"):
                game.net_error = msg.get("message", "Connection lost")

        # ── Events ───────────────────────────────────────────────────
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game.game_over:
                    continue
                # End turn button
                if (event.button == 1 and renderer.btn_end
                        and renderer.btn_end.collidepoint(event.pos)):
                    move = game.click_end_turn()
                    if move is not None:
                        net.send_move(move)
                    continue
                # Setup palette
                if event.button == 1 and game.phase.startswith("setup"):
                    for p, rect in renderer.setup_rects.items():
                        if rect.collidepoint(event.pos):
                            game.click_setup_piece(p)
                            break
                # Board click
                cell = renderer.pixel_to_cell(*event.pos)
                if cell is not None:
                    move = game.click(*cell, event.button)
                    if move is not None:
                        net.send_move(move)

        # ── Draw ─────────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display, mouse_pos)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(30)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Arimaa")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        mouse_pos = pygame.mouse.get_pos()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit()
                    sys.exit()
                elif ev.key == pygame.K_r and game.game_over:
                    game.reset()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if game.game_over:
                    continue
                # End turn button
                if (ev.button == 1 and renderer.btn_end
                        and renderer.btn_end.collidepoint(ev.pos)):
                    game.click_end_turn()
                    continue
                # Setup palette
                if ev.button == 1 and game.phase.startswith("setup"):
                    for p, rect in renderer.setup_rects.items():
                        if rect.collidepoint(ev.pos):
                            game.click_setup_piece(p)
                            break
                # Board click
                cell = renderer.pixel_to_cell(*ev.pos)
                if cell is not None:
                    game.click(*cell, ev.button)

        renderer.draw(game, mouse_pos)
        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()
