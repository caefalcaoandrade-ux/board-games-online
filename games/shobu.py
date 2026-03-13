"""
SHŌBU — Two-Player Abstract Strategy Board Game
═══════════════════════════════════════════════════
Run:      python shobu.py
Requires: pygame, numpy

Controls
────────
  Left-click   Select stone / Choose destination
  Esc          Deselect current stone
  U            Undo passive move (before aggressive is played)
  R            Restart game

Board Layout
────────────
       A (Dark)      B (Light)     ← WHITE's homeboards
              ── ROPE ──
       C (Light)     D (Dark)      ← BLACK's homeboards

Coordinates: columns a–d (left→right), rows 4–1 (top→bottom)
"""

import sys
import numpy as np
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════
CELL      = 90
BOARD_PX  = CELL * 4
GAP_X     = 56
GAP_Y     = 68
PAD_L     = 62
PAD_R     = 28
PAD_TOP   = 96
PAD_BOT   = 40

WIN_W = PAD_L + BOARD_PX * 2 + GAP_X + PAD_R
WIN_H = PAD_TOP + BOARD_PX * 2 + GAP_Y + PAD_BOT

# Palette
BG            = (34, 32, 36)
DARK_WOOD     = (142, 104, 68)
DARK_WOOD2    = (132,  95, 60)
LITE_WOOD     = (200, 172, 136)
LITE_WOOD2    = (190, 162, 126)
GRID_LINE     = (0, 0, 0)
BLACK_STONE   = (22, 22, 25)
WHITE_STONE   = (232, 228, 218)
SPEC_B        = (52, 52, 56)
SPEC_W        = (255, 255, 248)
ROPE_CLR      = (155, 138, 108)
SEL_RING      = (255, 210, 40)
VALID_FILL    = (60, 200, 80, 55)
VALID_DOT     = (50, 190, 70)
HINT_FILL     = (80, 170, 255, 40)
PUSH_FILL     = (255, 70, 50, 55)
PUSH_RING     = (255, 70, 50)
BORDER_NORM   = (65, 58, 50)
BORDER_HOME   = (70, 145, 220)
BORDER_AGG    = (220, 75, 65)
TXT           = (210, 210, 210)
TXT_DIM       = (135, 135, 135)
COORD_CLR     = (165, 158, 144)
LABEL_CLR     = (180, 172, 156)
WIN_GOLD      = (255, 215, 0)

# Game enums
EMPTY, BLACK, WHITE = 0, 1, 2
DARK_T, LITE_T      = 0, 1

BOARD_TYPE = [DARK_T, LITE_T, LITE_T, DARK_T]   # A B C D
BOARD_NAME = ["A", "B", "C", "D"]
HOME       = {BLACK: [2, 3], WHITE: [0, 1]}

DIRS = [(-1, 0), (-1, 1), (0, 1), (1, 1),
        (1, 0),  (1, -1), (0, -1), (-1, -1)]
DIR_NAME = {(-1,0):"N", (-1,1):"NE", (0,1):"E", (1,1):"SE",
            (1,0):"S",  (1,-1):"SW", (0,-1):"W", (-1,-1):"NW"}

PH_PSEL, PH_PDST, PH_ASEL, PH_ADST, PH_OVER = range(5)


def on_grid(r, c):
    return 0 <= r < 4 and 0 <= c < 4


def dir_dist(fr, fc, tr, tc):
    """Return ((dr,dc), distance) for a straight-line move, or None."""
    dr, dc = tr - fr, tc - fc
    if dr == 0 and dc == 0:
        return None
    d = max(abs(dr), abs(dc))
    if d not in (1, 2):
        return None
    if dr != 0 and dc != 0 and abs(dr) != abs(dc):
        return None
    nd = (dr // d, dc // d)
    return (nd, d) if nd in DIRS else None


def opp_color_boards(board_idx):
    """Boards whose type is opposite to board_idx's type."""
    want = LITE_T if BOARD_TYPE[board_idx] == DARK_T else DARK_T
    return [b for b in range(4) if BOARD_TYPE[b] == want]


# ═══════════════════════════════════════════════════════════════════════
#  GAME LOGIC
# ═══════════════════════════════════════════════════════════════════════
class Game:
    def __init__(self):
        self.bd = np.zeros((4, 4, 4), dtype=np.int8)
        for b in range(4):
            self.bd[b, 0, :] = WHITE      # top row
            self.bd[b, 3, :] = BLACK      # bottom row
        self.turn    = BLACK
        self.phase   = PH_PSEL
        self.sel     = None               # (board, row, col)
        self.pmove   = None               # passive move record
        self.vstone  = []                  # selectable stones
        self.vdest   = []                  # valid destinations
        self.winner  = None
        self.push_info = None             # (board, opp_r, opp_c, dest_r, dest_c, off_board)
        self._recompute_stones()

    # ── validation helpers ───────────────────────────────────────────
    def _path_clear_passive(self, b, fr, fc, d, dist):
        """All cells in path (inclusive of destination) must be empty."""
        for s in range(1, dist + 1):
            nr, nc = fr + d[0] * s, fc + d[1] * s
            if not on_grid(nr, nc) or self.bd[b, nr, nc] != EMPTY:
                return False
        return True

    def _passive_legal(self, b, fr, fc, tr, tc):
        """Full passive legality: correct board, clear path, has aggr follow-up."""
        if b not in HOME[self.turn]:
            return False
        if self.bd[b, fr, fc] != self.turn:
            return False
        if not on_grid(tr, tc):
            return False
        dd = dir_dist(fr, fc, tr, tc)
        if dd is None:
            return False
        d, dist = dd
        if not self._path_clear_passive(b, fr, fc, d, dist):
            return False
        return self._has_aggr_followup(b, d, dist)

    def _aggr_legal(self, b, fr, fc, d, dist):
        """Check aggressive move legality on board b from (fr,fc)."""
        p   = self.turn
        opp = WHITE if p == BLACK else BLACK
        if self.bd[b, fr, fc] != p:
            return False
        tr, tc = fr + d[0] * dist, fc + d[1] * dist
        if not on_grid(tr, tc):
            return False
        hit = []
        for s in range(1, dist + 1):
            nr, nc = fr + d[0] * s, fc + d[1] * s
            v = self.bd[b, nr, nc]
            if v == p:
                return False            # blocked by own stone
            if v == opp:
                hit.append((nr, nc))
        if len(hit) > 1:
            return False                # can't push two stones
        if len(hit) == 1:
            or_, oc_ = hit[0]
            pr, pc = or_ + d[0] * dist, oc_ + d[1] * dist
            if on_grid(pr, pc) and self.bd[b, pr, pc] != EMPTY:
                # push destination occupied ─ but it might be occupied by
                # the moving stone's origin which will be vacated.  However,
                # the moving stone starts at (fr,fc) and the push dest is
                # elsewhere, so no special case needed unless push_dest == (fr,fc).
                if (pr, pc) == (fr, fc):
                    pass   # origin will be vacated → legal
                else:
                    return False
        return True

    def _has_aggr_followup(self, pass_board, d, dist):
        for b in opp_color_boards(pass_board):
            for r in range(4):
                for c in range(4):
                    if self.bd[b, r, c] == self.turn:
                        if self._aggr_legal(b, r, c, d, dist):
                            return True
        return False

    # ── compute UI lists ─────────────────────────────────────────────
    def _recompute_stones(self):
        self.vstone = []
        self.push_info = None
        if self.phase == PH_PSEL:
            for b in HOME[self.turn]:
                for r in range(4):
                    for c in range(4):
                        if self.bd[b, r, c] != self.turn:
                            continue
                        usable = False
                        for d in DIRS:
                            for dist in (1, 2):
                                tr, tc = r + d[0] * dist, c + d[1] * dist
                                if on_grid(tr, tc) and self._passive_legal(b, r, c, tr, tc):
                                    usable = True
                                    break
                            if usable:
                                break
                        if usable:
                            self.vstone.append((b, r, c))
        elif self.phase == PH_ASEL:
            d, dist = self.pmove["dir"], self.pmove["dist"]
            for b in opp_color_boards(self.pmove["board"]):
                for r in range(4):
                    for c in range(4):
                        if self.bd[b, r, c] == self.turn:
                            if self._aggr_legal(b, r, c, d, dist):
                                self.vstone.append((b, r, c))

    def _recompute_dests(self):
        self.vdest = []
        self.push_info = None
        if self.sel is None:
            return
        b, r, c = self.sel
        if self.phase == PH_PDST:
            for d in DIRS:
                for dist in (1, 2):
                    tr, tc = r + d[0] * dist, c + d[1] * dist
                    if on_grid(tr, tc) and self._passive_legal(b, r, c, tr, tc):
                        self.vdest.append((b, tr, tc))
        elif self.phase == PH_ADST:
            d, dist = self.pmove["dir"], self.pmove["dist"]
            tr, tc = r + d[0] * dist, c + d[1] * dist
            if on_grid(tr, tc) and self._aggr_legal(b, r, c, d, dist):
                self.vdest.append((b, tr, tc))
                self._compute_push_info(b, r, c, d, dist)

    def _compute_push_info(self, b, fr, fc, d, dist):
        """Set self.push_info if the aggressive move pushes a stone."""
        opp = WHITE if self.turn == BLACK else BLACK
        for s in range(1, dist + 1):
            nr, nc = fr + d[0] * s, fc + d[1] * s
            if self.bd[b, nr, nc] == opp:
                pr, pc = nr + d[0] * dist, nc + d[1] * dist
                off = not on_grid(pr, pc)
                self.push_info = (b, nr, nc, pr, pc, off)
                return
        self.push_info = None

    # ── execution ────────────────────────────────────────────────────
    def _exec_passive(self, b, fr, fc, tr, tc):
        dd = dir_dist(fr, fc, tr, tc)
        d, dist = dd
        self.bd[b, fr, fc] = EMPTY
        self.bd[b, tr, tc] = self.turn
        self.pmove = {"board": b, "fr": fr, "fc": fc,
                      "tr": tr, "tc": tc, "dir": d, "dist": dist}

    def _exec_aggressive(self, b, fr, fc):
        d, dist = self.pmove["dir"], self.pmove["dist"]
        opp = WHITE if self.turn == BLACK else BLACK
        tr, tc = fr + d[0] * dist, fc + d[1] * dist
        # resolve push first
        for s in range(1, dist + 1):
            nr, nc = fr + d[0] * s, fc + d[1] * s
            if self.bd[b, nr, nc] == opp:
                self.bd[b, nr, nc] = EMPTY
                pr, pc = nr + d[0] * dist, nc + d[1] * dist
                if on_grid(pr, pc):
                    self.bd[b, pr, pc] = opp
                break
        # move stone
        self.bd[b, fr, fc] = EMPTY
        self.bd[b, tr, tc] = self.turn

    def _check_win(self):
        opp = WHITE if self.turn == BLACK else BLACK
        for b in range(4):
            if not np.any(self.bd[b] == opp):
                self.winner = self.turn
                return True
        return False

    # ── public interface ─────────────────────────────────────────────
    def click(self, b, r, c):
        if self.phase == PH_OVER:
            return

        if self.phase == PH_PSEL:
            if (b, r, c) in self.vstone:
                self.sel = (b, r, c)
                self.phase = PH_PDST
                self._recompute_dests()

        elif self.phase == PH_PDST:
            if (b, r, c) in self.vstone:
                self.sel = (b, r, c)
                self._recompute_dests()
                return
            if (b, r, c) in self.vdest:
                sb, sr, sc = self.sel
                self._exec_passive(sb, sr, sc, r, c)
                self.sel = None
                self.vdest = []
                self.phase = PH_ASEL
                self._recompute_stones()

        elif self.phase == PH_ASEL:
            if (b, r, c) in self.vstone:
                self.sel = (b, r, c)
                self.phase = PH_ADST
                self._recompute_dests()

        elif self.phase == PH_ADST:
            if (b, r, c) in self.vstone:
                self.sel = (b, r, c)
                self._recompute_dests()
                return
            if (b, r, c) in self.vdest:
                sb, sr, sc = self.sel
                self._exec_aggressive(sb, sr, sc)
                if self._check_win():
                    self.phase = PH_OVER
                    self.sel = None
                    self.vstone = []
                    self.vdest = []
                    self.push_info = None
                    return
                # next turn
                self.turn = WHITE if self.turn == BLACK else BLACK
                self.sel = None
                self.pmove = None
                self.vdest = []
                self.push_info = None
                self.phase = PH_PSEL
                self._recompute_stones()
                if not self.vstone:
                    self.winner = WHITE if self.turn == BLACK else BLACK
                    self.phase = PH_OVER

    def undo_passive(self):
        if self.phase in (PH_ASEL, PH_ADST) and self.pmove:
            pm = self.pmove
            self.bd[pm["board"], pm["tr"], pm["tc"]] = EMPTY
            self.bd[pm["board"], pm["fr"], pm["fc"]] = self.turn
            self.pmove = None
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_PSEL
            self._recompute_stones()

    def deselect(self):
        if self.phase == PH_PDST:
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_PSEL
            self._recompute_stones()
        elif self.phase == PH_ADST:
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_ASEL
            self._recompute_stones()

    def stone_counts(self, board_idx):
        """Return (black_count, white_count) for a board."""
        return (int(np.sum(self.bd[board_idx] == BLACK)),
                int(np.sum(self.bd[board_idx] == WHITE)))


# ═══════════════════════════════════════════════════════════════════════
#  RENDERER / UI
# ═══════════════════════════════════════════════════════════════════════
class UI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("SHŌBU")
        self.clock = pygame.time.Clock()
        self.game  = Game()

        # fonts (SysFont gracefully falls back if name missing)
        self.f_lg  = pygame.font.SysFont("arial", 30, bold=True)
        self.f_md  = pygame.font.SysFont("arial", 20)
        self.f_sm  = pygame.font.SysFont("arial", 16)
        self.f_xs  = pygame.font.SysFont("arial", 14)
        self.f_co  = pygame.font.SysFont("arial", 15)

        self.bpos = [
            (PAD_L,                      PAD_TOP),
            (PAD_L + BOARD_PX + GAP_X,   PAD_TOP),
            (PAD_L,                      PAD_TOP + BOARD_PX + GAP_Y),
            (PAD_L + BOARD_PX + GAP_X,   PAD_TOP + BOARD_PX + GAP_Y),
        ]

    # ── coordinate mapping ───────────────────────────────────────────
    def _hit_test(self, mx, my):
        for i, (bx, by) in enumerate(self.bpos):
            if bx <= mx < bx + BOARD_PX and by <= my < by + BOARD_PX:
                c = (mx - bx) // CELL
                r = (my - by) // CELL
                if 0 <= r < 4 and 0 <= c < 4:
                    return (i, r, c)
        return None

    # ── drawing ──────────────────────────────────────────────────────
    def _draw_all(self):
        self.screen.fill(BG)
        self._draw_rope()
        for b in range(4):
            self._draw_board(b)
        self._draw_hud()
        pygame.display.flip()

    def _draw_rope(self):
        ry = PAD_TOP + BOARD_PX + GAP_Y // 2
        x0 = PAD_L - 8
        x1 = PAD_L + BOARD_PX * 2 + GAP_X + 8
        # rope line
        pygame.draw.line(self.screen, ROPE_CLR, (x0, ry), (x1, ry), 5)
        # knots
        mid = (x0 + x1) // 2
        for dx in (-10, 0, 10):
            pygame.draw.circle(self.screen, ROPE_CLR, (mid + dx, ry), 4)
        # side labels
        ws = self.f_sm.render("\u25B2 WHITE's side", True, TXT_DIM)
        bs = self.f_sm.render("\u25BC BLACK's side", True, TXT_DIM)
        self.screen.blit(ws, (x0 + 6, ry - 22))
        self.screen.blit(bs, (x0 + 6, ry + 7))

    def _draw_board(self, bi):
        bx, by = self.bpos[bi]
        g = self.game
        dark = BOARD_TYPE[bi] == DARK_T
        c1 = DARK_WOOD  if dark else LITE_WOOD
        c2 = DARK_WOOD2 if dark else LITE_WOOD2
        ov = pygame.Surface((CELL, CELL), pygame.SRCALPHA)

        # border colour
        bc = BORDER_NORM
        if g.phase in (PH_PSEL, PH_PDST) and bi in HOME[g.turn]:
            bc = BORDER_HOME
        elif g.phase in (PH_ASEL, PH_ADST) and g.pmove:
            if bi in opp_color_boards(g.pmove["board"]):
                bc = BORDER_AGG
        bw = 3
        pygame.draw.rect(self.screen, bc,
                         (bx - bw, by - bw, BOARD_PX + 2 * bw, BOARD_PX + 2 * bw), bw)

        # cells
        for r in range(4):
            for c in range(4):
                x, y = bx + c * CELL, by + r * CELL
                pygame.draw.rect(self.screen, c1 if (r + c) % 2 == 0 else c2,
                                 (x, y, CELL, CELL))
                pygame.draw.rect(self.screen, GRID_LINE, (x, y, CELL, CELL), 1)

        # ─ highlights ─
        # selectable stones
        for (vb, vr, vc) in g.vstone:
            if vb == bi:
                ov.fill(HINT_FILL)
                self.screen.blit(ov, (bx + vc * CELL, by + vr * CELL))

        # valid destinations
        for (vb, vr, vc) in g.vdest:
            if vb == bi:
                ov.fill(VALID_FILL)
                self.screen.blit(ov, (bx + vc * CELL, by + vr * CELL))
                cx = bx + vc * CELL + CELL // 2
                cy = by + vr * CELL + CELL // 2
                pygame.draw.circle(self.screen, VALID_DOT, (cx, cy), 9)

        # push preview
        pi = g.push_info
        if pi and pi[0] == bi:
            _, opr, opc, pdr, pdc, off = pi
            # highlight pushed stone
            ov.fill(PUSH_FILL)
            self.screen.blit(ov, (bx + opc * CELL, by + opr * CELL))
            # small X on push source
            cx = bx + opc * CELL + CELL // 2
            cy = by + opr * CELL + CELL // 2
            pygame.draw.line(self.screen, PUSH_RING, (cx-6,cy-6),(cx+6,cy+6), 2)
            pygame.draw.line(self.screen, PUSH_RING, (cx+6,cy-6),(cx-6,cy+6), 2)
            if not off:
                # ring where pushed stone lands
                px = bx + pdc * CELL + CELL // 2
                py = by + pdr * CELL + CELL // 2
                pygame.draw.circle(self.screen, PUSH_RING, (px, py), 12, 2)
            else:
                # arrow pointing off board edge
                ex, ey = bx + opc * CELL + CELL // 2, by + opr * CELL + CELL // 2
                d = g.pmove["dir"]
                ax = ex + d[1] * CELL * 0.6
                ay = ey + d[0] * CELL * 0.6
                pygame.draw.line(self.screen, PUSH_RING, (ex, ey), (int(ax), int(ay)), 2)

        # ─ stones ─
        for r in range(4):
            for c in range(4):
                v = g.bd[bi, r, c]
                if v == EMPTY:
                    continue
                cx = bx + c * CELL + CELL // 2
                cy = by + r * CELL + CELL // 2
                rad = CELL // 2 - 9

                # selection ring (behind stone)
                if g.sel == (bi, r, c):
                    pygame.draw.circle(self.screen, SEL_RING, (cx, cy), rad + 5, 3)

                # shadow
                pygame.draw.circle(self.screen, (0, 0, 0), (cx + 2, cy + 2), rad)
                # body
                sc = BLACK_STONE if v == BLACK else WHITE_STONE
                pygame.draw.circle(self.screen, sc, (cx, cy), rad)
                # specular highlight
                sp = SPEC_B if v == BLACK else SPEC_W
                pygame.draw.circle(self.screen, sp,
                                   (cx - rad // 3, cy - rad // 3), max(rad // 4, 3))

        # ─ coordinates ─
        for c in range(4):
            lbl = self.f_co.render(chr(ord("a") + c), True, COORD_CLR)
            self.screen.blit(lbl, (bx + c * CELL + CELL // 2 - lbl.get_width() // 2,
                                   by + BOARD_PX + 5))
        for r in range(4):
            lbl = self.f_co.render(str(4 - r), True, COORD_CLR)
            self.screen.blit(lbl, (bx - lbl.get_width() - 6,
                                   by + r * CELL + CELL // 2 - lbl.get_height() // 2))

        # ─ board label + stone counts ─
        kind = "Dark" if dark else "Light"
        nm = self.f_md.render(f"{BOARD_NAME[bi]} ({kind})", True, LABEL_CLR)
        self.screen.blit(nm, (bx + 2, by - 26))

        bc_, wc_ = g.stone_counts(bi)
        tag = self.f_sm.render(f"\u25CF{bc_}  \u25CB{wc_}", True, TXT_DIM)
        self.screen.blit(tag, (bx + BOARD_PX - tag.get_width() - 2, by - 24))

    def _draw_hud(self):
        g = self.game
        pname = "BLACK" if g.turn == BLACK else "WHITE"

        if g.phase == PH_OVER:
            wn = "BLACK" if g.winner == BLACK else "WHITE"
            s = self.f_lg.render(f"{wn} WINS!", True, WIN_GOLD)
            self.screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 6))
            rs = self.f_sm.render("Press R to restart", True, TXT_DIM)
            self.screen.blit(rs, (WIN_W // 2 - rs.get_width() // 2, 36))
            return

        # player icon
        sc = BLACK_STONE if g.turn == BLACK else WHITE_STONE
        pygame.draw.circle(self.screen, sc, (24, 24), 12)
        if g.turn == WHITE:
            pygame.draw.circle(self.screen, (0, 0, 0), (24, 24), 12, 1)

        tl = self.f_lg.render(f"{pname}'s Turn", True, TXT)
        self.screen.blit(tl, (44, 6))

        phase_msg = {
            PH_PSEL: "Select stone for PASSIVE move (on your homeboard)",
            PH_PDST: "Choose destination for PASSIVE move",
            PH_ASEL: "Select stone for AGGRESSIVE move (opposite-color board)",
            PH_ADST: "Choose destination for AGGRESSIVE move",
        }
        ms = self.f_sm.render(phase_msg.get(g.phase, ""), True, TXT_DIM)
        self.screen.blit(ms, (44, 40))

        # right-side key hints
        hints = []
        if g.phase in (PH_ASEL, PH_ADST):
            hints.append("[U] Undo passive")
            if g.pmove:
                dn = DIR_NAME[g.pmove["dir"]]
                hints.append(f"Dir {dn} · Dist {g.pmove['dist']}")
        if g.phase in (PH_PDST, PH_ADST):
            hints.append("[Esc] Deselect")
        hints.append("[R] Restart")
        rx = WIN_W - 16
        for i, h in enumerate(hints):
            hs = self.f_sm.render(h, True, TXT_DIM)
            self.screen.blit(hs, (rx - hs.get_width(), 8 + i * 20))

    # ── main loop ────────────────────────────────────────────────────
    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    hit = self._hit_test(*ev.pos)
                    if hit:
                        self.game.click(*hit)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_r:
                        self.game = Game()
                    elif ev.key == pygame.K_u:
                        self.game.undo_passive()
                    elif ev.key == pygame.K_ESCAPE:
                        self.game.deselect()
            self._draw_all()
            self.clock.tick(60)


# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    UI().run()