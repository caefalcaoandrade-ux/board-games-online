"""
YINSH — Abstract Strategy Board Game
Local human-vs-human implementation using Pygame.

Rules based on the official YINSH ruleset by Kris Burm.
85-intersection hexagonal board, 5 rings per player, 51 shared markers.
First player to remove 3 of their own rings (by forming rows of 5) wins.

Controls:
  Left-click     Select / confirm actions
  Right-click    Deselect / cancel
  Left / Right   Cycle through row choices (when resolving rows)
  N              New game
  Esc / Q        Quit
"""

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
import sys
import math
from enum import Enum, auto

# ════════════════════════════════════════════════════════════════════
#  DISPLAY CONSTANTS
# ════════════════════════════════════════════════════════════════════

WINDOW_W, WINDOW_H = 1200, 900
FPS = 60

HEX_SP   = 50          # pixel spacing between adjacent intersections
BOARD_CX = 465         # board centre x
BOARD_CY = 448         # board centre y

RING_R   = 19          # ring outer radius
RING_W   = 6           # ring annulus width
MARKER_R = 13          # marker filled-circle radius
DOT_R    = 3           # empty-intersection dot radius
CLICK_R  = HEX_SP * 0.44

PANEL_X  = 865
PANEL_W  = 315

# ─── colour palette ───────────────────────────────────────────────

BG            = (237, 233, 222)
GRID_LINE_C   = (200, 196, 186)
GRID_DOT_C    = (175, 170, 160)
LABEL_C       = (140, 135, 125)

# pieces — white player
W_RING_FILL   = (220, 216, 208)
W_RING_EDGE   = (150, 146, 138)
W_MARKER_FILL = (248, 246, 238)
W_MARKER_EDGE = (175, 172, 164)

# pieces — black player
B_RING_FILL   = (52, 52, 58)
B_RING_EDGE   = (25, 25, 28)
B_MARKER_FILL = (40, 40, 46)
B_MARKER_EDGE = (20, 20, 22)

# highlights
HL_VALID      = (80, 190, 105, 150)    # valid-move dot
HL_SELECT     = (255, 210, 45)         # selected-ring glow
HL_ROW        = (220, 60, 55)          # active candidate row
HL_ROW_ALT    = (255, 160, 55)         # other candidate rows
HL_RING_REM   = (175, 55, 195)         # removable-ring glow
HL_LAST       = (130, 175, 230, 100)   # last-move feedback

# panel
PANEL_BG      = (227, 223, 213)
PANEL_BORDER  = (200, 196, 186)
TXT_DARK      = (42, 40, 36)
TXT_MID       = (115, 111, 103)
TXT_LIGHT     = (160, 156, 148)
TAG_W         = (210, 206, 198)
TAG_B         = (58, 56, 52)
ACCENT_W      = (180, 176, 168)
ACCENT_B      = (90, 88, 82)

# ════════════════════════════════════════════════════════════════════
#  HEXAGONAL BOARD GEOMETRY   (axial coordinates, 85 intersections)
# ════════════════════════════════════════════════════════════════════

SQRT3_2 = math.sqrt(3) / 2.0
DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]


def _make_valid():
    corners = frozenset({(5, 0), (-5, 0), (0, 5), (0, -5), (5, -5), (-5, 5)})
    return frozenset(
        (q, r)
        for q in range(-5, 6)
        for r in range(-5, 6)
        if max(abs(q), abs(r), abs(q + r)) <= 5 and (q, r) not in corners
    )


VALID = _make_valid()
assert len(VALID) == 85


def h2p(q, r):
    """Axial hex → pixel."""
    return (BOARD_CX + HEX_SP * (q + r * 0.5),
            BOARD_CY - HEX_SP * r * SQRT3_2)


def p2h(mx, my):
    """Pixel → nearest valid hex (or None if too far)."""
    rf = (BOARD_CY - my) / (HEX_SP * SQRT3_2)
    qf = (mx - BOARD_CX) / HEX_SP - rf * 0.5
    sf = -qf - rf
    rq, rr, rs = round(qf), round(rf), round(sf)
    dq, dr, ds = abs(rq - qf), abs(rr - rf), abs(rs - sf)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    pos = (rq, rr)
    if pos in VALID:
        px, py = h2p(*pos)
        if math.hypot(mx - px, my - py) < CLICK_R:
            return pos
    return None


def clabel(q, r):
    """Coordinate label, e.g. 'F6'."""
    return f"{chr(65 + q + 5)}{r + 6}"


# precompute grid drawing data
def _grid_segs():
    segs = []
    for q, r in VALID:
        for dq, dr in [(1, 0), (0, 1), (1, -1)]:
            nb = (q + dq, r + dr)
            if nb in VALID:
                segs.append((h2p(q, r), h2p(*nb)))
    return segs


def _board_lines():
    """Maximal collinear sequences along each axis (length >= 2)."""
    lines = []
    for dq, dr in [(1, 0), (0, 1), (1, -1)]:
        seen = set()
        for pos in VALID:
            if pos in seen:
                continue
            q, r = pos
            while (q - dq, r - dr) in VALID:
                q -= dq; r -= dr
            line = []
            while (q, r) in VALID:
                line.append((q, r)); seen.add((q, r))
                q += dq; r += dr
            if len(line) >= 2:
                lines.append(tuple(line))
    return lines


def _edge_labels():
    col_lbl = {}
    for q in range(-5, 6):
        pts = [p for p in VALID if p[0] == q]
        if not pts:
            continue
        top = max(pts, key=lambda p: p[1])
        px, py = h2p(*top)
        col_lbl[chr(65 + q + 5)] = (px, py - 26)

    row_lbl = {}
    for rn in sorted({r + 6 for (_, r) in VALID}):
        r_ax = rn - 6
        pts = [p for p in VALID if p[1] == r_ax]
        if not pts:
            continue
        left = min(pts, key=lambda p: h2p(*p)[0])
        px, py = h2p(*left)
        row_lbl[str(rn)] = (px - 24, py)
    return col_lbl, row_lbl


GRID_SEGS = _grid_segs()
BOARD_LINES = _board_lines()
COL_LBL, ROW_LBL = _edge_labels()


# ════════════════════════════════════════════════════════════════════
#  GAME STATE
# ════════════════════════════════════════════════════════════════════

class Phase(Enum):
    PLACEMENT = auto()
    MAIN      = auto()


class St(Enum):
    PLACE_RING  = auto()
    SELECT_RING = auto()
    MOVE_RING   = auto()
    CHOOSE_ROW  = auto()
    REMOVE_RING = auto()
    GAME_OVER   = auto()


def _opp(c):
    return 'B' if c == 'W' else 'W'


class Game:
    """Complete YINSH game state and rule engine."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.rings   = {}          # pos -> 'W'|'B'
        self.markers = {}          # pos -> 'W'|'B'
        self.pool    = 51
        self.removed = {'W': 0, 'B': 0}
        self.placed  = {'W': 0, 'B': 0}
        self.turn    = 'W'
        self.phase   = Phase.PLACEMENT
        self.st      = St.PLACE_RING
        self.sel     = None        # selected ring pos
        self.vmoves  = set()       # valid move destinations
        self.crows   = []          # candidate rows (list of 5-tuples)
        self.crow_i  = 0           # highlighted candidate index
        self.rplayer = None        # who is resolving rows
        self.mturn   = 'W'        # who made the move (for opp resolution)
        self.winner  = None        # 'W','B','draw', or None
        self.hover   = None
        self.last_marker = None    # pos of last placed marker
        self.last_dest   = None    # pos ring moved to

    # ── public input ──────────────────────────────────────────

    def click(self, pos):
        if pos is None or self.st == St.GAME_OVER:
            return
        {
            St.PLACE_RING:  self._do_place,
            St.SELECT_RING: self._do_select,
            St.MOVE_RING:   self._do_move,
            St.CHOOSE_ROW:  self._do_choose_row,
            St.REMOVE_RING: self._do_remove_ring,
        }.get(self.st, lambda p: None)(pos)

    def rclick(self):
        if self.st == St.MOVE_RING:
            self.sel = None; self.vmoves = set()
            self.st = St.SELECT_RING

    def cycle(self, d):
        if self.st == St.CHOOSE_ROW and len(self.crows) > 1:
            self.crow_i = (self.crow_i + d) % len(self.crows)

    # ── status text ───────────────────────────────────────────

    @property
    def pname(self):
        return "White" if self.turn == 'W' else "Black"

    @property
    def rname(self):
        return "White" if self.rplayer == 'W' else "Black"

    @property
    def status(self):
        if self.st == St.GAME_OVER:
            if self.winner == 'draw':
                return "Game over  —  Draw!"
            w = "White" if self.winner == 'W' else "Black"
            return f"Game over  —  {w} wins!"
        if self.st == St.PLACE_RING:
            n = 5 - self.placed[self.turn]
            return f"{self.pname}: place a ring ({n} left)"
        if self.st == St.SELECT_RING:
            return f"{self.pname}: select one of your rings"
        if self.st == St.MOVE_RING:
            return f"{self.pname}: move ring to a green spot  (right-click to cancel)"
        if self.st == St.CHOOSE_ROW:
            n = len(self.crows)
            hint = "  [left/right to cycle]" if n > 1 else ""
            return f"{self.rname}: click a highlighted row to remove{hint}"
        if self.st == St.REMOVE_RING:
            return f"{self.rname}: click one of your rings to remove it"
        return ""

    # ── placement phase ───────────────────────────────────────

    def _do_place(self, pos):
        if not self._vacant(pos):
            return
        self.rings[pos] = self.turn
        self.placed[self.turn] += 1
        if self.placed['W'] + self.placed['B'] >= 10:
            self.phase = Phase.MAIN
            self.turn = 'W'; self.mturn = 'W'
            self.st = St.SELECT_RING
            self._check_turn_start()
        else:
            self.turn = _opp(self.turn)

    # ── ring selection ────────────────────────────────────────

    def _do_select(self, pos):
        if pos in self.rings and self.rings[pos] == self.turn:
            m = self._dests(pos)
            if m:
                self.sel = pos; self.vmoves = m; self.st = St.MOVE_RING

    # ── ring movement ─────────────────────────────────────────

    def _do_move(self, pos):
        if pos == self.sel:
            self.rclick(); return
        if pos in self.rings and self.rings[pos] == self.turn:
            m = self._dests(pos)
            if m:
                self.sel = pos; self.vmoves = m
            return
        if pos not in self.vmoves:
            return

        origin = self.sel

        # A — place marker
        self.markers[origin] = self.turn
        self.pool -= 1
        self.last_marker = origin

        # B — move ring
        del self.rings[origin]
        self.rings[pos] = self.turn
        self.last_dest = pos

        # C — flip jumped markers
        for jp in self._jumped(origin, pos):
            self.markers[jp] = _opp(self.markers[jp])

        self.sel = None; self.vmoves = set()

        # D — resolve rows (active player first)
        self.mturn = self.turn; self.rplayer = self.turn
        self._enter_row_check()

    # ── row resolution ────────────────────────────────────────

    def _enter_row_check(self):
        rows = self._find_rows(self.rplayer)
        if rows:
            self.crows = rows; self.crow_i = 0
            self.st = St.CHOOSE_ROW
        elif self.rplayer == self.mturn:
            self.rplayer = _opp(self.mturn)
            self._enter_row_check()
        else:
            self._end_turn()

    def _do_choose_row(self, pos):
        for i, row in enumerate(self.crows):
            if pos in row:
                self.crow_i = i; self._resolve_row(); return
        if len(self.crows) == 1:
            self._resolve_row()

    def _resolve_row(self):
        for p in self.crows[self.crow_i]:
            del self.markers[p]; self.pool += 1
        self.crows = []; self.st = St.REMOVE_RING

    def _do_remove_ring(self, pos):
        if pos not in self.rings or self.rings[pos] != self.rplayer:
            return
        del self.rings[pos]
        self.removed[self.rplayer] += 1
        if self.removed[self.rplayer] >= 3:
            self.winner = self.rplayer; self.st = St.GAME_OVER; return
        self._enter_row_check()

    # ── turn management ───────────────────────────────────────

    def _end_turn(self):
        self.turn = _opp(self.turn); self.mturn = self.turn
        self.st = St.SELECT_RING
        self.last_marker = None; self.last_dest = None
        self._check_turn_start()

    def _check_turn_start(self):
        if self.pool <= 0:
            w, b = self.removed['W'], self.removed['B']
            self.winner = 'W' if w > b else ('B' if b > w else 'draw')
            self.st = St.GAME_OVER; return
        if not any(self._dests(p) for p, c in self.rings.items() if c == self.turn):
            # no legal moves — pass (extremely rare)
            self.turn = _opp(self.turn); self.mturn = self.turn

    # ── movement engine ───────────────────────────────────────

    def _vacant(self, pos):
        return pos in VALID and pos not in self.rings and pos not in self.markers

    def _dests(self, rp):
        out = set()
        for dq, dr in DIRECTIONS:
            cq, cr = rp[0] + dq, rp[1] + dr
            jumped = False
            while (cq, cr) in VALID:
                if (cq, cr) in self.rings:
                    break
                if (cq, cr) in self.markers:
                    jumped = True
                    cq += dq; cr += dr; continue
                out.add((cq, cr))
                if jumped:
                    break
                cq += dq; cr += dr
        return out

    def _jumped(self, s, e):
        dq, dr = e[0] - s[0], e[1] - s[1]
        n = max(abs(dq), abs(dr), abs(dq + dr))
        sq, sr = dq // n, dr // n
        res = []
        cq, cr = s[0] + sq, s[1] + sr
        while (cq, cr) != e:
            if (cq, cr) in self.markers:
                res.append((cq, cr))
            cq += sq; cr += sr
        return res

    # ── row finder ────────────────────────────────────────────

    def _find_rows(self, colour):
        cands = []
        for line in BOARD_LINES:
            run = []
            for pos in line:
                if pos in self.markers and self.markers[pos] == colour:
                    run.append(pos)
                else:
                    _extract(run, cands); run = []
            _extract(run, cands)
        seen = set(); unique = []
        for row in cands:
            k = tuple(sorted(row))
            if k not in seen:
                seen.add(k); unique.append(row)
        return unique


def _extract(run, out):
    if len(run) >= 5:
        for i in range(len(run) - 4):
            out.append(tuple(run[i:i + 5]))


# ════════════════════════════════════════════════════════════════════
#  RENDERER
# ════════════════════════════════════════════════════════════════════

class Renderer:
    def __init__(self, surf):
        self.s = surf
        pygame.font.init()
        self.f_sm = pygame.font.SysFont("consolas", 14)
        self.f_md = pygame.font.SysFont("consolas", 16, bold=True)
        self.f_lg = pygame.font.SysFont("consolas", 21, bold=True)
        self.f_xl = pygame.font.SysFont("consolas", 34, bold=True)

    def draw(self, g: Game):
        self.s.fill(BG)
        self._grid()
        self._labels()
        self._highlights(g)
        self._pieces(g)
        self._hover(g)
        self._panel(g)
        pygame.display.flip()

    # ── board ─────────────────────────────────────────────────

    def _grid(self):
        for a, b in GRID_SEGS:
            pygame.draw.aaline(self.s, GRID_LINE_C, a, b)
        for pos in VALID:
            px, py = h2p(*pos)
            pygame.draw.circle(self.s, GRID_DOT_C, (int(px), int(py)), DOT_R)

    def _labels(self):
        for lbl, (x, y) in COL_LBL.items():
            t = self.f_sm.render(lbl, True, LABEL_C)
            self.s.blit(t, (x - t.get_width() // 2, y - t.get_height() // 2))
        for lbl, (x, y) in ROW_LBL.items():
            t = self.f_sm.render(lbl, True, LABEL_C)
            self.s.blit(t, (x - t.get_width() // 2, y - t.get_height() // 2))

    # ── highlights ────────────────────────────────────────────

    def _highlights(self, g: Game):
        # last move feedback
        for lp in [g.last_marker, g.last_dest]:
            if lp:
                px, py = h2p(*lp)
                hs = pygame.Surface((RING_R * 2 + 12, RING_R * 2 + 12), pygame.SRCALPHA)
                pygame.draw.circle(hs, HL_LAST, (RING_R + 6, RING_R + 6), RING_R + 5)
                self.s.blit(hs, (px - RING_R - 6, py - RING_R - 6))

        # valid moves
        if g.st == St.MOVE_RING:
            for pos in g.vmoves:
                px, py = h2p(*pos)
                hs = pygame.Surface((MARKER_R * 2 + 8, MARKER_R * 2 + 8), pygame.SRCALPHA)
                pygame.draw.circle(hs, HL_VALID, (MARKER_R + 4, MARKER_R + 4), MARKER_R + 3)
                self.s.blit(hs, (px - MARKER_R - 4, py - MARKER_R - 4))

        # selected ring
        if g.sel:
            px, py = h2p(*g.sel)
            pygame.draw.circle(self.s, HL_SELECT, (int(px), int(py)), RING_R + 5, 3)

        # candidate rows
        if g.st == St.CHOOSE_ROW:
            for i, row in enumerate(g.crows):
                c = HL_ROW if i == g.crow_i else HL_ROW_ALT
                for pos in row:
                    px, py = h2p(*pos)
                    pygame.draw.circle(self.s, c, (int(px), int(py)), MARKER_R + 6, 3)

        # removable rings
        if g.st == St.REMOVE_RING:
            for pos, c in g.rings.items():
                if c == g.rplayer:
                    px, py = h2p(*pos)
                    pygame.draw.circle(self.s, HL_RING_REM, (int(px), int(py)), RING_R + 6, 3)

    # ── pieces ────────────────────────────────────────────────

    def _pieces(self, g: Game):
        # markers
        for pos, c in g.markers.items():
            px, py = h2p(*pos)
            ip = (int(px), int(py))
            fill = W_MARKER_FILL if c == 'W' else B_MARKER_FILL
            edge = W_MARKER_EDGE if c == 'W' else B_MARKER_EDGE
            pygame.draw.circle(self.s, fill, ip, MARKER_R)
            pygame.draw.circle(self.s, edge, ip, MARKER_R, 2)

        # rings (annulus: thick outline = hollow centre)
        for pos, c in g.rings.items():
            px, py = h2p(*pos)
            ip = (int(px), int(py))
            fill = W_RING_FILL if c == 'W' else B_RING_FILL
            edge = W_RING_EDGE if c == 'W' else B_RING_EDGE
            # thick annulus body
            pygame.draw.circle(self.s, fill, ip, RING_R, RING_W)
            # outer and inner edges for crispness
            pygame.draw.circle(self.s, edge, ip, RING_R, 2)
            pygame.draw.circle(self.s, edge, ip, RING_R - RING_W + 1, 2)

    # ── hover tooltip ─────────────────────────────────────────

    def _hover(self, g: Game):
        if g.hover and g.hover in VALID:
            q, r = g.hover
            lbl = clabel(q, r)
            px, py = h2p(q, r)
            t = self.f_sm.render(lbl, True, TXT_DARK)
            tx, ty = int(px) + 20, int(py) - 20
            if tx + t.get_width() > WINDOW_W - 20:
                tx = int(px) - 20 - t.get_width()
            bg = pygame.Rect(tx - 4, ty - 2, t.get_width() + 8, t.get_height() + 4)
            pygame.draw.rect(self.s, (255, 255, 248), bg, border_radius=3)
            pygame.draw.rect(self.s, LABEL_C, bg, 1, border_radius=3)
            self.s.blit(t, (tx, ty))

    # ── side panel ────────────────────────────────────────────

    def _panel(self, g: Game):
        panel = pygame.Rect(PANEL_X, 18, PANEL_W, WINDOW_H - 36)
        pygame.draw.rect(self.s, PANEL_BG, panel, border_radius=10)
        pygame.draw.rect(self.s, PANEL_BORDER, panel, 2, border_radius=10)

        x0 = PANEL_X + 22
        y = 40

        # title
        self.s.blit(self.f_xl.render("YINSH", True, TXT_DARK), (x0, y))
        y += 50

        # phase badge
        ptxt = "PLACEMENT" if g.phase == Phase.PLACEMENT else "MAIN GAME"
        self.s.blit(self.f_sm.render(ptxt, True, TXT_LIGHT), (x0, y))
        y += 28

        self._sep(x0, y); y += 16

        # scoreboard
        self.s.blit(self.f_lg.render("Score", True, TXT_DARK), (x0, y)); y += 30

        for colour, name in [('W', 'White'), ('B', 'Black')]:
            tag = TAG_W if colour == 'W' else TAG_B
            acc = ACCENT_W if colour == 'W' else ACCENT_B
            # swatch
            pygame.draw.circle(self.s, tag, (x0 + 10, y + 12), 9)
            pygame.draw.circle(self.s, acc, (x0 + 10, y + 12), 9, 2)
            # name
            self.s.blit(self.f_md.render(f"{name}", True, TXT_DARK), (x0 + 28, y))
            # pips for scored rings
            nw = self.f_md.size(name)[0]
            for k in range(3):
                cx_pip = x0 + 28 + nw + 14 + k * 20
                if k < g.removed[colour]:
                    pygame.draw.circle(self.s, tag, (cx_pip, y + 9), 7)
                    pygame.draw.circle(self.s, acc, (cx_pip, y + 9), 7, 2)
                else:
                    pygame.draw.circle(self.s, PANEL_BORDER, (cx_pip, y + 9), 7, 2)

            n_on = sum(1 for v in g.rings.values() if v == colour)
            self.s.blit(self.f_sm.render(
                f"{n_on} ring{'s' if n_on != 1 else ''} on board", True, TXT_MID), (x0 + 28, y + 22))
            y += 50

        self._sep(x0, y); y += 16

        # marker pool
        self.s.blit(self.f_md.render(f"Marker pool:  {g.pool}", True, TXT_DARK), (x0, y)); y += 22
        self.s.blit(self.f_sm.render(f"On board:  {len(g.markers)}", True, TXT_MID), (x0, y)); y += 30

        self._sep(x0, y); y += 16

        # active player indicator
        if g.st != St.GAME_OVER:
            active = g.rplayer if g.st in (St.CHOOSE_ROW, St.REMOVE_RING) else g.turn
            aname = "White" if active == 'W' else "Black"
            atag = TAG_W if active == 'W' else TAG_B
            aacc = ACCENT_W if active == 'W' else ACCENT_B
            self.s.blit(self.f_md.render("Turn:", True, TXT_MID), (x0, y))
            off = self.f_md.size("Turn: ")[0] + 4
            pygame.draw.circle(self.s, atag, (x0 + off + 8, y + 9), 8)
            pygame.draw.circle(self.s, aacc, (x0 + off + 8, y + 9), 8, 2)
            self.s.blit(self.f_lg.render(aname, True, TXT_DARK), (x0 + off + 22, y - 3))
            y += 36

        # status
        y += 4
        self._wrap(g.status, x0, y, PANEL_W - 44, self.f_md, TXT_DARK)
        y += 58

        self._sep(x0, y); y += 16

        # controls
        self.s.blit(self.f_md.render("Controls", True, TXT_DARK), (x0, y)); y += 24
        for line in [
            "Left-click   Select / confirm",
            "Right-click   Cancel",
            "Left/Right   Cycle row choices",
            "N   New game",
            "Esc   Quit",
        ]:
            self.s.blit(self.f_sm.render(line, True, TXT_MID), (x0, y)); y += 19

    def _sep(self, x, y):
        pygame.draw.line(self.s, PANEL_BORDER, (x, y), (PANEL_X + PANEL_W - 22, y))

    def _wrap(self, text, x, y, maxw, font, col):
        line = ""
        for w in text.split():
            t = line + (" " if line else "") + w
            if font.size(t)[0] > maxw and line:
                self.s.blit(font.render(line, True, col), (x, y))
                y += font.get_linesize() + 2; line = w
            else:
                line = t
        if line:
            self.s.blit(font.render(line, True, col), (x, y))


# ════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ════════════════════════════════════════════════════════════════════

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("YINSH")
    clock = pygame.time.Clock()

    game = Game()
    renderer = Renderer(screen)

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit(); sys.exit()
                elif ev.key == pygame.K_n:
                    game.reset()
                elif ev.key == pygame.K_LEFT:
                    game.cycle(-1)
                elif ev.key == pygame.K_RIGHT:
                    game.cycle(1)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                pos = p2h(*ev.pos)
                if ev.button == 1:
                    game.click(pos)
                elif ev.button == 3:
                    game.rclick()

            elif ev.type == pygame.MOUSEMOTION:
                game.hover = p2h(*ev.pos)

        renderer.draw(game)
        clock.tick(FPS)


if __name__ == "__main__":
    main()