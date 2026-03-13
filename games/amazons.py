"""
Amazons — Interactive Board Game (Human vs Human)
A 10×10 deterministic abstract strategy game.
Controls: Left-click to select/move/shoot. Right-click or U to undo move. R to restart. Esc to quit.
"""

import sys
import numpy as np
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

# ── Constants ────────────────────────────────────────────────────────────────

BOARD_N = 10
CELL = 68
MARGIN = 30
BOARD_PX = BOARD_N * CELL
STATUS_H = 56
WIN_W = BOARD_PX + 2 * MARGIN
WIN_H = BOARD_PX + 2 * MARGIN + STATUS_H
BX, BY = MARGIN, MARGIN  # board pixel origin

EMPTY, WHITE, BLACK, BLOCKED = 0, 1, 2, 3
PH_SELECT, PH_MOVE, PH_ARROW = 0, 1, 2
DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
FILES = "abcdefghij"

# Initial amazon positions  (row, col)  where row 0 = rank 10
W_START = [(6, 0), (9, 3), (9, 6), (6, 9)]   # a4 d1 g1 j4
B_START = [(3, 0), (0, 3), (0, 6), (3, 9)]   # a7 d10 g10 j7

# ── Palette ──────────────────────────────────────────────────────────────────

C_BG          = ( 38,  36,  33)
C_LIGHT_SQ    = (238, 216, 180)
C_DARK_SQ     = (181, 137, 100)
C_COORD       = (170, 165, 155)
C_BLOCKED_DOT = ( 82,  78,  72)
C_SEL_SQ      = ( 80, 165,  85, 110)
C_SRC_SQ      = (200, 205, 100,  65)
C_LAST_SQ     = (200, 205, 100,  55)
C_MOVE_DOT    = ( 80, 160,  85)
C_ARROW_DOT   = (205,  72,  72)
C_ARROW_RING  = (175,  55,  55)
C_LAST_ARROW  = (190,  65,  65)
C_WHITE_FILL  = (255, 252, 237)
C_WHITE_OUT   = ( 55,  55,  55)
C_BLACK_FILL  = ( 32,  32,  32)
C_BLACK_OUT   = (185, 185, 185)
C_STATUS_TXT  = (195, 192, 185)
C_WIN_TXT     = (255, 215,  50)
C_HINT_TXT    = (105, 102,  96)
C_HOVER       = (255, 255, 255,  30)

# ── Game Logic ───────────────────────────────────────────────────────────────


class Amazons:
    """Full Amazons game state and rules engine."""

    def __init__(self):
        self.reset()

    # ── Setup ────────────────────────────────────────────────────────────

    def reset(self):
        self.board = np.zeros((BOARD_N, BOARD_N), dtype=np.int8)
        for r, c in W_START:
            self.board[r, c] = WHITE
        for r, c in B_START:
            self.board[r, c] = BLACK
        self.turn = WHITE
        self.phase = PH_SELECT
        self.sel = None          # selected amazon (r,c)
        self.move_src = None     # where amazon came from (for undo)
        self.move_dst = None     # where amazon landed
        self.targets = []        # valid cells for current phase
        self.game_over = False
        self.winner = None
        self.move_num = 1
        self.last_src = None
        self.last_dst = None
        self.last_arrow = None

    # ── Movement helpers ─────────────────────────────────────────────────

    def queen_reach(self, r0, c0):
        """Return all empty squares reachable by queen-move from (r0,c0)."""
        result = []
        for dr, dc in DIRS:
            r, c = r0 + dr, c0 + dc
            while 0 <= r < BOARD_N and 0 <= c < BOARD_N and self.board[r, c] == EMPTY:
                result.append((r, c))
                r += dr
                c += dc
        return result

    def _has_legal_turn(self, player):
        """Does *player* have at least one legal turn (move + arrow)?"""
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                if self.board[r, c] != player:
                    continue
                for mr, mc in self.queen_reach(r, c):
                    # temporarily execute the move
                    self.board[r, c] = EMPTY
                    self.board[mr, mc] = player
                    can_shoot = len(self.queen_reach(mr, mc)) > 0
                    # undo
                    self.board[mr, mc] = EMPTY
                    self.board[r, c] = player
                    if can_shoot:
                        return True
        return False

    def _valid_moves_for(self, r, c):
        """Queen destinations from (r,c) that also allow an arrow shot after."""
        player = self.board[r, c]
        valid = []
        for mr, mc in self.queen_reach(r, c):
            self.board[r, c] = EMPTY
            self.board[mr, mc] = player
            if self.queen_reach(mr, mc):
                valid.append((mr, mc))
            self.board[mr, mc] = EMPTY
            self.board[r, c] = player
        return valid

    # ── Click handling ───────────────────────────────────────────────────

    def click(self, row, col):
        if self.game_over or not (0 <= row < BOARD_N and 0 <= col < BOARD_N):
            return

        if self.phase == PH_SELECT:
            if self.board[row, col] == self.turn:
                valid = self._valid_moves_for(row, col)
                if valid:
                    self.sel = (row, col)
                    self.targets = valid
                    self.phase = PH_MOVE

        elif self.phase == PH_MOVE:
            # click same amazon → deselect
            if (row, col) == self.sel:
                self._cancel()
                return
            # click another friendly amazon → re-select
            if self.board[row, col] == self.turn:
                self._cancel()
                self.click(row, col)
                return
            # click a valid destination → move
            if (row, col) in self.targets:
                sr, sc = self.sel
                self.board[sr, sc] = EMPTY
                self.board[row, col] = self.turn
                self.move_src = (sr, sc)
                self.move_dst = (row, col)
                self.targets = self.queen_reach(row, col)
                self.phase = PH_ARROW

        elif self.phase == PH_ARROW:
            if (row, col) in self.targets:
                self.board[row, col] = BLOCKED
                # record history for highlights
                self.last_src = self.move_src
                self.last_dst = self.move_dst
                self.last_arrow = (row, col)
                # advance turn
                prev = self.turn
                self.turn = BLACK if self.turn == WHITE else WHITE
                if prev == BLACK:
                    self.move_num += 1
                self._cancel()
                # check end condition
                if not self._has_legal_turn(self.turn):
                    self.game_over = True
                    self.winner = BLACK if self.turn == WHITE else WHITE

    def undo_move(self):
        """During arrow phase, put the amazon back."""
        if self.phase == PH_ARROW and self.move_src and self.move_dst:
            r, c = self.move_dst
            sr, sc = self.move_src
            self.board[r, c] = EMPTY
            self.board[sr, sc] = self.turn
            self._cancel()

    def _cancel(self):
        self.sel = None
        self.move_src = None
        self.move_dst = None
        self.targets = []
        self.phase = PH_SELECT

    @staticmethod
    def notation(r, c):
        return f"{FILES[c]}{BOARD_N - r}"


# ── Rendering ────────────────────────────────────────────────────────────────


def _make_piece_surfaces(font):
    """Pre-render white and black queen surfaces with outlines."""
    def outlined(char, fill, outline):
        base = font.render(char, True, fill)
        edge = font.render(char, True, outline)
        w, h = base.get_width() + 4, base.get_height() + 4
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    surf.blit(edge, (2 + dx, 2 + dy))
        surf.blit(base, (2, 2))
        return surf

    glyph = "\u265B"  # ♛
    w_surf = outlined(glyph, C_WHITE_FILL, C_WHITE_OUT)
    b_surf = outlined(glyph, C_BLACK_FILL, C_BLACK_OUT)
    return w_surf, b_surf


def _make_fallback_pieces():
    """Circle-based fallback if Unicode queen doesn't render."""
    radius = CELL // 3
    size = radius * 2 + 6
    surfaces = []
    for fill, outline in [(C_WHITE_FILL, C_WHITE_OUT), (C_BLACK_FILL, C_BLACK_OUT)]:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        pygame.draw.circle(s, fill, (cx, cy), radius)
        pygame.draw.circle(s, outline, (cx, cy), radius, 2)
        # small crown ticks
        for angle_x in (-0.6, 0, 0.6):
            tx = int(cx + angle_x * radius)
            ty = cy - radius + 2
            pygame.draw.line(s, outline, (tx, cy - radius // 2), (tx, ty - 5), 2)
            pygame.draw.circle(s, fill, (tx, ty - 5), 3)
            pygame.draw.circle(s, outline, (tx, ty - 5), 3, 1)
        surfaces.append(s)
    return surfaces[0], surfaces[1]


class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen
        self.coord_font = pygame.font.SysFont("monospace", 14)
        self.status_font = pygame.font.SysFont("sans-serif", 18, bold=True)
        self.hint_font = pygame.font.SysFont("monospace", 13)

        # attempt Unicode queen
        pfont_size = max(12, int(CELL * 0.72))
        for family in ["DejaVu Sans", "Noto Sans Symbols2", "Segoe UI Symbol",
                        "Apple Symbols", "Arial Unicode MS", None]:
            pfont = pygame.font.SysFont(family, pfont_size)
            test = pfont.render("\u265B", True, (0, 0, 0))
            if test.get_width() > pfont_size * 0.25:
                self.w_piece, self.b_piece = _make_piece_surfaces(pfont)
                self._unicode = True
                break
        else:
            self.w_piece, self.b_piece = _make_fallback_pieces()
            self._unicode = False

        self._hl = pygame.Surface((CELL, CELL), pygame.SRCALPHA)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _sq_px(self, r, c):
        """Top-left pixel of square (r, c)."""
        return BX + c * CELL, BY + r * CELL

    def _sq_center(self, r, c):
        x, y = self._sq_px(r, c)
        return x + CELL // 2, y + CELL // 2

    def _fill_sq(self, r, c, rgba):
        self._hl.fill(rgba)
        self.screen.blit(self._hl, self._sq_px(r, c))

    # ── Main draw ────────────────────────────────────────────────────────

    def draw(self, game: Amazons, mouse_pos):
        scr = self.screen
        scr.fill(C_BG)

        # board outline
        pygame.draw.rect(scr, (60, 58, 55),
                         (BX - 2, BY - 2, BOARD_PX + 4, BOARD_PX + 4), 2)

        # squares
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                color = C_LIGHT_SQ if (r + c) % 2 == 0 else C_DARK_SQ
                pygame.draw.rect(scr, color, (*self._sq_px(r, c), CELL, CELL))

        # ── Highlights ───────────────────────────────────────────────────

        # last-move highlight (only visible when back to select phase)
        if game.last_src and game.phase == PH_SELECT:
            for pos in (game.last_src, game.last_dst):
                self._fill_sq(*pos, C_LAST_SQ)

        # selected amazon
        if game.sel and game.phase == PH_MOVE:
            self._fill_sq(*game.sel, C_SEL_SQ)

        # moved amazon & source trail during arrow phase
        if game.move_dst and game.phase == PH_ARROW:
            self._fill_sq(*game.move_dst, C_SEL_SQ)
            if game.move_src:
                self._fill_sq(*game.move_src, C_SRC_SQ)

        # hover highlight
        if mouse_pos and not game.game_over:
            mx, my = mouse_pos
            hc = (mx - BX) // CELL
            hr = (my - BY) // CELL
            if 0 <= hr < BOARD_N and 0 <= hc < BOARD_N:
                if (hr, hc) in game.targets:
                    self._fill_sq(hr, hc, C_HOVER)

        # valid-target dots
        for tr, tc in game.targets:
            cx, cy = self._sq_center(tr, tc)
            if game.phase == PH_ARROW:
                pygame.draw.circle(scr, C_ARROW_DOT, (cx, cy), 9)
                pygame.draw.circle(scr, C_ARROW_RING, (cx, cy), 9, 2)
            else:
                pygame.draw.circle(scr, C_MOVE_DOT, (cx, cy), 9)

        # ── Pieces & blocked squares ─────────────────────────────────────

        for r in range(BOARD_N):
            for c in range(BOARD_N):
                cx, cy = self._sq_center(r, c)
                v = game.board[r, c]
                if v == BLOCKED:
                    pygame.draw.circle(scr, C_BLOCKED_DOT, (cx, cy), CELL // 5)
                    if game.last_arrow == (r, c) and game.phase == PH_SELECT:
                        pygame.draw.circle(scr, C_LAST_ARROW, (cx, cy), CELL // 5 + 3, 2)
                elif v == WHITE:
                    s = self.w_piece
                    scr.blit(s, (cx - s.get_width() // 2, cy - s.get_height() // 2))
                elif v == BLACK:
                    s = self.b_piece
                    scr.blit(s, (cx - s.get_width() // 2, cy - s.get_height() // 2))

        # ── Coordinates ──────────────────────────────────────────────────

        for i in range(BOARD_N):
            # files
            lbl = self.coord_font.render(FILES[i], True, C_COORD)
            x = BX + i * CELL + CELL // 2 - lbl.get_width() // 2
            scr.blit(lbl, (x, BY - MARGIN + 6))
            scr.blit(lbl, (x, BY + BOARD_PX + 6))
            # ranks
            rank_str = str(BOARD_N - i)
            lbl = self.coord_font.render(rank_str, True, C_COORD)
            y = BY + i * CELL + CELL // 2 - lbl.get_height() // 2
            scr.blit(lbl, (BX - MARGIN + 4 + (8 if BOARD_N - i < 10 else 0), y))
            scr.blit(lbl, (BX + BOARD_PX + 8, y))

        # ── Status bar ───────────────────────────────────────────────────

        sy = BY + BOARD_PX + MARGIN + 4

        if game.game_over:
            who = "White" if game.winner == WHITE else "Black"
            txt = self.status_font.render(f"{who} wins!", True, C_WIN_TXT)
            scr.blit(txt, (BX, sy))
            sub = self.hint_font.render("  Press R to play again", True, C_HINT_TXT)
            scr.blit(sub, (BX + txt.get_width(), sy + 3))
        else:
            name = "White" if game.turn == WHITE else "Black"
            dot_col = C_WHITE_FILL if game.turn == WHITE else C_BLACK_FILL
            dot_out = C_WHITE_OUT if game.turn == WHITE else C_BLACK_OUT
            pygame.draw.circle(scr, dot_col, (BX + 8, sy + 10), 7)
            pygame.draw.circle(scr, dot_out, (BX + 8, sy + 10), 7, 1)

            phases = {PH_SELECT: "Select amazon", PH_MOVE: "Move amazon",
                      PH_ARROW: "Shoot arrow"}
            msg = f" {name}  \u2014  {phases[game.phase]}       Move {game.move_num}"
            txt = self.status_font.render(msg, True, C_STATUS_TXT)
            scr.blit(txt, (BX + 20, sy))

        # hints
        parts = []
        if game.phase == PH_ARROW:
            parts.append("Right-click: undo")
        parts.append("R: new game")
        parts.append("Esc: quit")
        hint = self.hint_font.render("    ".join(parts), True, C_HINT_TXT)
        scr.blit(hint, (BX, sy + 26))

        pygame.display.flip()


# ── Main loop ────────────────────────────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Amazons")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = Amazons()

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
                elif ev.key == pygame.K_r:
                    game.reset()
                elif ev.key == pygame.K_u:
                    game.undo_move()

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                col = (mx - BX) // CELL
                row = (my - BY) // CELL
                if ev.button == 1:
                    game.click(row, col)
                elif ev.button == 3:
                    game.undo_move()

        renderer.draw(game, mouse_pos)
        clock.tick(30)


if __name__ == "__main__":
    main()