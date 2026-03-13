"""
Tumbleweed — Two-player abstract strategy board game.
Designed by Mike Zapawa (2020).  Pygame implementation for local play.

Run:  python tumbleweed.py
Controls:  Left-click to place / move.  Buttons in the side panel.
           Press N anytime for a new game, Q or Esc to quit.
"""

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
import sys
import math

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════
BOARD_SIZE    = 8          # hex-hex edge length  (8 → 169 cells)
HEX_R        = 29         # hex circumradius in pixels
WIN_W, WIN_H = 1340, 880  # window dimensions
BOARD_CX     = 420        # board centre x
BOARD_CY     = 440        # board centre y
PANEL_LEFT   = 790        # info-panel left edge
FPS          = 60

# six cube-coordinate direction vectors
DIRS = [(1, 0, -1), (1, -1, 0), (0, -1, 1),
        (-1, 0, 1), (-1, 1, 0), (0, 1, -1)]

_S3 = math.sqrt(3)

# ── Colour palette ────────────────────────────────────────
BG          = (30, 32, 36)
PANEL_BG    = (40, 42, 47)
PANEL_LINE  = (60, 62, 68)
HEX_FILL    = (225, 216, 196)
HEX_EDGE    = (168, 158, 138)
LEGAL_FILL  = (175, 215, 135)
LEGAL_EDGE  = (135, 178, 100)
HOVER_FILL  = (248, 238, 175)
HOVER_EDGE  = (205, 195, 140)
CTRL_RED_T  = (210, 140, 130)   # controlled-cell tint (game-over)
CTRL_WHT_T  = (175, 195, 215)
CONTESTED_T = (200, 200, 185)
RED_C       = (195, 50, 50)
RED_HI      = (225, 80, 80)
WHT_C       = (238, 238, 238)
WHT_DK      = (198, 198, 198)
NEU_C       = (148, 148, 152)
NEU_HI      = (172, 172, 176)
TXT         = (220, 220, 220)
TXT_DIM     = (130, 130, 135)
TXT_DARK    = (32, 32, 32)
BTN_BG      = (65, 70, 80)
BTN_HV      = (88, 93, 108)
GOLD        = (228, 192, 56)
STATUS_BG   = (50, 52, 58)

# ── Enumerations ──────────────────────────────────────────
RED, WHITE, NEUTRAL = 0, 1, 2
PH_SETUP, PH_PIE, PH_PLAY, PH_OVER = 0, 1, 2, 3

COLOUR_NAME  = {RED: "Red", WHITE: "White", NEUTRAL: "Neutral"}
COLOUR_RGB   = {RED: RED_C, WHITE: WHT_C, NEUTRAL: NEU_C}


# ══════════════════════════════════════════════════════════════
#  HEX GEOMETRY  (flat-top orientation)
# ══════════════════════════════════════════════════════════════

def _valid(x, y, z):
    return x + y + z == 0 and max(abs(x), abs(y), abs(z)) <= BOARD_SIZE - 1


def _cube2px(x, z):
    """Cube coordinate → pixel centre (flat-top hex)."""
    px = HEX_R * 1.5 * x + BOARD_CX
    py = HEX_R * _S3 * (z + x * 0.5) + BOARD_CY
    return (px, py)


def _px2cube(mx, my):
    """Pixel → nearest valid cube coordinate, or None."""
    px, py = mx - BOARD_CX, my - BOARD_CY
    q = (2.0 / 3.0 * px) / HEX_R
    r = (-px / 3.0 + _S3 / 3.0 * py) / HEX_R
    fx, fz = q, r
    fy = -fx - fz
    rx, ry, rz = round(fx), round(fy), round(fz)
    dx, dy, dz = abs(rx - fx), abs(ry - fy), abs(rz - fz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return (rx, ry, rz) if _valid(rx, ry, rz) else None


def _hex_corners(cx, cy):
    """Six corners of a flat-top hex centred at (cx, cy)."""
    return [(cx + HEX_R * math.cos(math.pi / 3 * i),
             cy + HEX_R * math.sin(math.pi / 3 * i)) for i in range(6)]


def _cell_label(x, y, z):
    """Human-readable label: column letter + row number."""
    col_letter = chr(65 + x + BOARD_SIZE - 1)   # A … O  (for S=8)
    row_number = z + BOARD_SIZE                  # 1 … 15
    return f"{col_letter}{row_number}"


# ══════════════════════════════════════════════════════════════
#  GAME LOGIC
# ══════════════════════════════════════════════════════════════

class Game:
    """Full Tumbleweed game state and rule engine."""

    def __init__(self):
        S = BOARD_SIZE
        self.all_cells = []
        for x in range(-(S - 1), S):
            for z in range(-(S - 1), S):
                y = -x - z
                if _valid(x, y, z):
                    self.all_cells.append((x, y, z))
        self.cell_set = frozenset(self.all_cells)
        self.total_cells = len(self.all_cells)
        self.reset()

    # ── reset / new game ──────────────────────────────────
    def reset(self):
        self.stacks = {}                       # cell → (colour, height)
        self.stacks[(0, 0, 0)] = (NEUTRAL, 2)  # mandatory neutral seed
        self.phase      = PH_SETUP
        self.setup_step = 0                     # 0 = place Red, 1 = place White
        self.turn       = RED
        self.passes     = 0
        self.winner     = None
        self.msg        = "Host: click any empty cell to place the Red seed"
        self._legal_cache  = None
        self._scores_cache = None
        self._ctrl_map     = {}                 # cell → colour (for game-over overlay)
        self._refresh_scores()

    # ── line of sight ─────────────────────────────────────
    def _visible_from(self, cell):
        """Return list of (cell) for each stack visible along six rays."""
        vis = []
        cx, cy, cz = cell
        for dx, dy, dz in DIRS:
            x, y, z = cx + dx, cy + dy, cz + dz
            while _valid(x, y, z):
                if (x, y, z) in self.stacks:
                    vis.append((x, y, z))
                    break
                x, y, z = x + dx, y + dy, z + dz
        return vis

    def _flos(self, cell, colour):
        """Count friendly lines of sight to *cell* for *colour*."""
        return sum(1 for v in self._visible_from(cell)
                   if self.stacks[v][0] == colour)

    # ── legal moves ───────────────────────────────────────
    def legal_moves(self):
        """Return list of (cell, new_height) for the active player."""
        if self._legal_cache is not None:
            return self._legal_cache
        moves = []
        c = self.turn
        for cell in self.all_cells:
            f = self._flos(cell, c)
            if cell not in self.stacks:
                if f >= 1:
                    moves.append((cell, f))
            else:
                if f > self.stacks[cell][1]:
                    moves.append((cell, f))
        self._legal_cache = moves
        return moves

    def legal_set(self):
        return {m[0] for m in self.legal_moves()}

    def _invalidate(self):
        self._legal_cache = None

    # ── actions ───────────────────────────────────────────
    def setup_click(self, cell):
        if cell is None or cell not in self.cell_set or cell in self.stacks:
            return False
        if self.setup_step == 0:
            self.stacks[cell] = (RED, 1)
            self.setup_step = 1
            self.msg = "Host: click any empty cell to place the White seed"
        elif self.setup_step == 1:
            self.stacks[cell] = (WHITE, 1)
            self.phase = PH_PIE
            self.msg = "Guest: choose which colour to play"
        self._invalidate()
        self._refresh_scores()
        return True

    def pie_choice(self, _colour):
        """Guest picked a colour.  Since this is local hotseat the label
        is just cosmetic — Red always moves first."""
        self.phase = PH_PLAY
        self.turn  = RED
        self._invalidate()
        self.msg = "Red's turn"

    def do_move(self, cell):
        legal_dict = {m[0]: m[1] for m in self.legal_moves()}
        if cell not in legal_dict:
            return False
        self.stacks[cell] = (self.turn, legal_dict[cell])
        self.passes = 0
        self.turn = WHITE if self.turn == RED else RED
        self._invalidate()
        self._refresh_scores()
        self.msg = f"{COLOUR_NAME[self.turn]}'s turn"
        return True

    def do_pass(self):
        passer = self.turn
        self.passes += 1
        self.turn = WHITE if self.turn == RED else RED
        self._invalidate()
        if self.passes >= 2:
            self._finish()
        else:
            self.msg = (f"{COLOUR_NAME[self.turn]}'s turn  "
                        f"({COLOUR_NAME[passer]} passed)")

    # ── scoring ───────────────────────────────────────────
    def _refresh_scores(self):
        own  = {RED: 0, WHITE: 0}
        ctrl = {RED: 0, WHITE: 0}
        cmap = {}
        for cell in self.all_cells:
            if cell in self.stacks:
                c = self.stacks[cell][0]
                if c in (RED, WHITE):
                    own[c] += 1
            else:
                vis = self._visible_from(cell)
                cr = sum(1 for v in vis if self.stacks[v][0] == RED)
                cw = sum(1 for v in vis if self.stacks[v][0] == WHITE)
                if cr > cw:
                    ctrl[RED] += 1
                    cmap[cell] = RED
                elif cw > cr:
                    ctrl[WHITE] += 1
                    cmap[cell] = WHITE
                else:
                    cmap[cell] = -1  # contested
        self._scores_cache = {
            RED:   (own[RED],   ctrl[RED],   own[RED]   + ctrl[RED]),
            WHITE: (own[WHITE], ctrl[WHITE], own[WHITE] + ctrl[WHITE]),
        }
        self._ctrl_map = cmap

    def scores(self):
        return self._scores_cache

    def _finish(self):
        self.phase = PH_OVER
        self._refresh_scores()
        sr = self._scores_cache[RED][2]
        sw = self._scores_cache[WHITE][2]
        self.winner = RED if sr > sw else WHITE
        wn = COLOUR_NAME[self.winner]
        self.msg = f"Game over — {wn} wins!   Red {sr}  ·  White {sw}"


# ══════════════════════════════════════════════════════════════
#  SIMPLE BUTTON WIDGET
# ══════════════════════════════════════════════════════════════

class Btn:
    def __init__(self, x, y, w, h, label, bg=BTN_BG, bgh=BTN_HV, fg=TXT):
        self.rect  = pygame.Rect(x, y, w, h)
        self.label = label
        self.bg    = bg
        self.bgh   = bgh
        self.fg    = fg
        self.hot   = False

    def update(self, mx, my):
        self.hot = self.rect.collidepoint(mx, my)

    def draw(self, surf, font):
        c = self.bgh if self.hot else self.bg
        pygame.draw.rect(surf, c, self.rect, border_radius=7)
        pygame.draw.rect(surf, PANEL_LINE, self.rect, 1, border_radius=7)
        t = font.render(self.label, True, self.fg)
        surf.blit(t, (self.rect.centerx - t.get_width() // 2,
                       self.rect.centery - t.get_height() // 2))

    def clicked(self, mx, my):
        return self.rect.collidepoint(mx, my)


# ══════════════════════════════════════════════════════════════
#  MAIN LOOP  (rendering + interaction)
# ══════════════════════════════════════════════════════════════

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Tumbleweed")
    clock = pygame.time.Clock()

    # ── fonts ─────────────────────────────────────────────
    try:
        _fpath = None
        fn_title = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 23, bold=True)
        fn_body  = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 17)
        fn_small = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 14)
        fn_tiny  = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 12)
        fn_hex   = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 16, bold=True)
    except Exception:
        fn_title = pygame.font.Font(None, 27)
        fn_body  = pygame.font.Font(None, 21)
        fn_small = pygame.font.Font(None, 18)
        fn_tiny  = pygame.font.Font(None, 15)
        fn_hex   = pygame.font.Font(None, 20)

    game = Game()

    # ── buttons ───────────────────────────────────────────
    PX = PANEL_LEFT + 35
    btn_pass  = Btn(PX, 630, 210, 42, "Pass")
    btn_new   = Btn(PX, 690, 210, 42, "New Game")
    btn_red   = Btn(PX, 390, 210, 46, "Play as Red",
                    bg=RED_C, bgh=RED_HI, fg=TXT)
    btn_white = Btn(PX, 450, 210, 46, "Play as White",
                    bg=(175, 175, 175), bgh=WHT_C, fg=TXT_DARK)

    # ── pre-compute edge label positions ──────────────────
    S = BOARD_SIZE
    col_label_pos = {}   # x → pixel for column letter
    row_label_pos = {}   # z → pixel for row number

    for x in range(-(S - 1), S):
        z_min = max(-(S - 1), -(S - 1) - x)
        px, py = _cube2px(x, z_min)
        col_label_pos[x] = (px, py - HEX_R - 10)

    for z in range(-(S - 1), S):
        x_min = max(-(S - 1), -(S - 1) - z)
        px, py = _cube2px(x_min, z)
        row_label_pos[z] = (px - HEX_R - 14, py)

    # ── pre-compute pixel centres for every cell ──────────
    cell_px = {}
    for cell in game.all_cells:
        x, y, z = cell
        cell_px[cell] = _cube2px(x, z)

    # ── main loop ─────────────────────────────────────────
    hover = None
    running = True

    while running:
        mx, my = pygame.mouse.get_pos()
        hover = _px2cube(mx, my)

        # ── events ────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif ev.key == pygame.K_n:
                    game.reset()
                elif ev.key == pygame.K_p and game.phase == PH_PLAY:
                    game.do_pass()

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if game.phase == PH_SETUP:
                    game.setup_click(hover)

                elif game.phase == PH_PIE:
                    if btn_red.clicked(mx, my):
                        game.pie_choice(RED)
                    elif btn_white.clicked(mx, my):
                        game.pie_choice(WHITE)

                elif game.phase == PH_PLAY:
                    if btn_pass.clicked(mx, my):
                        game.do_pass()
                    elif hover:
                        game.do_move(hover)

                elif game.phase == PH_OVER:
                    if btn_new.clicked(mx, my):
                        game.reset()

        # update button hover state
        for b in (btn_pass, btn_new, btn_red, btn_white):
            b.update(mx, my)

        # legal move set (cached inside Game)
        ls = game.legal_set() if game.phase == PH_PLAY else set()

        # ══════════════════════════════════════════════════
        #  DRAW
        # ══════════════════════════════════════════════════
        screen.fill(BG)

        # ── board hexes ───────────────────────────────────
        for cell in game.all_cells:
            cx, cy = cell_px[cell]
            pts = _hex_corners(cx, cy)
            is_legal = cell in ls
            is_hover = (cell == hover)

            # — fill colour —
            if game.phase == PH_OVER and cell not in game.stacks:
                ctrl = game._ctrl_map.get(cell, -1)
                if ctrl == RED:
                    fill, edge = CTRL_RED_T, (175, 115, 105)
                elif ctrl == WHITE:
                    fill, edge = CTRL_WHT_T, (145, 162, 178)
                else:
                    fill, edge = CONTESTED_T, (170, 170, 160)
            elif is_hover and is_legal:
                fill, edge = HOVER_FILL, HOVER_EDGE
            elif is_legal:
                fill, edge = LEGAL_FILL, LEGAL_EDGE
            elif is_hover:
                fill, edge = (238, 230, 210), HEX_EDGE
            elif game.phase == PH_SETUP and cell not in game.stacks:
                # subtle highlight for placeable cells during setup
                fill, edge = (228, 220, 202), HEX_EDGE
            else:
                fill, edge = HEX_FILL, HEX_EDGE

            pygame.draw.polygon(screen, fill, pts)
            pygame.draw.aalines(screen, edge, True, pts)

            # — stack disc —
            if cell in game.stacks:
                col, ht = game.stacks[cell]
                if col == RED:
                    dc, ec, tc = RED_C, RED_HI, TXT
                elif col == WHITE:
                    dc, ec, tc = WHT_C, WHT_DK, TXT_DARK
                else:
                    dc, ec, tc = NEU_C, NEU_HI, TXT_DARK
                r = int(HEX_R * 0.60)
                icx, icy = int(cx), int(cy)
                pygame.draw.circle(screen, dc, (icx, icy), r)
                pygame.draw.circle(screen, ec, (icx, icy), r, 2)
                txt = fn_hex.render(str(ht), True, tc)
                screen.blit(txt, (icx - txt.get_width() // 2,
                                  icy - txt.get_height() // 2))

        # ── coordinate labels along edges ─────────────────
        for x, (lx, ly) in col_label_pos.items():
            letter = chr(65 + x + S - 1)
            t = fn_tiny.render(letter, True, TXT_DIM)
            screen.blit(t, (lx - t.get_width() // 2, ly - t.get_height() // 2))

        for z, (lx, ly) in row_label_pos.items():
            num_str = str(z + S)
            t = fn_tiny.render(num_str, True, TXT_DIM)
            screen.blit(t, (lx - t.get_width(), ly - t.get_height() // 2))

        # ══════════════════════════════════════════════════
        #  SIDE PANEL
        # ══════════════════════════════════════════════════
        pygame.draw.rect(screen, PANEL_BG, (PANEL_LEFT, 0, WIN_W - PANEL_LEFT, WIN_H))
        pygame.draw.line(screen, PANEL_LINE, (PANEL_LEFT, 0), (PANEL_LEFT, WIN_H), 2)

        # title
        t = fn_title.render("TUMBLEWEED", True, GOLD)
        screen.blit(t, (PX, 22))
        t = fn_tiny.render(f"Hexhex-{S}  ·  {game.total_cells} cells  ·  by Mike Zapawa", True, TXT_DIM)
        screen.blit(t, (PX, 52))

        pygame.draw.line(screen, PANEL_LINE, (PX - 5, 78), (WIN_W - 30, 78))

        # ── player score boxes ────────────────────────────
        sc = game.scores()
        y0 = 95
        for i, (col, name, rgb) in enumerate(
                [(RED, "Red", RED_C), (WHITE, "White", WHT_C)]):
            ty = y0 + i * 130

            # colour dot + name
            pygame.draw.circle(screen, rgb, (PX + 12, ty + 14), 10)
            if col == WHITE:
                pygame.draw.circle(screen, WHT_DK, (PX + 12, ty + 14), 10, 1)
            t = fn_body.render(name, True, TXT)
            screen.blit(t, (PX + 32, ty + 3))

            # turn arrow
            if game.phase == PH_PLAY and game.turn == col:
                ax = PX - 6
                ay = ty + 9
                pygame.draw.polygon(screen, GOLD,
                                    [(ax, ay), (ax, ay + 10), (ax + 7, ay + 5)])

            # scores
            if sc:
                own, ctrl, total = sc[col]
                t = fn_small.render(f"Owned: {own}    Controlled: {ctrl}", True, TXT_DIM)
                screen.blit(t, (PX + 32, ty + 28))
                t = fn_body.render(f"Total:  {total}", True, TXT)
                screen.blit(t, (PX + 32, ty + 50))

            # winner badge
            if game.phase == PH_OVER and game.winner == col:
                t = fn_title.render("★  WINNER", True, GOLD)
                screen.blit(t, (PX + 32, ty + 76))

        pygame.draw.line(screen, PANEL_LINE, (PX - 5, 355), (WIN_W - 30, 355))

        # ── phase-specific widgets ────────────────────────
        if game.phase == PH_PIE:
            t = fn_body.render("Guest — choose your colour:", True, TXT)
            screen.blit(t, (PX, 368))
            btn_red.draw(screen, fn_body)
            btn_white.draw(screen, fn_body)

        if game.phase == PH_PLAY:
            tc = COLOUR_RGB[game.turn]
            tn = COLOUR_NAME[game.turn]
            t = fn_body.render(f"{tn}'s turn", True, tc)
            screen.blit(t, (PX, 370))
            nm = len(ls)
            if nm == 0:
                t = fn_small.render("No legal moves — must pass", True, (220, 160, 80))
            else:
                t = fn_small.render(f"{nm} legal move{'s' if nm != 1 else ''}", True, TXT_DIM)
            screen.blit(t, (PX, 396))

        # ── hover cell info ───────────────────────────────
        info_y = 520
        pygame.draw.line(screen, PANEL_LINE, (PX - 5, info_y - 12), (WIN_W - 30, info_y - 12))
        t = fn_small.render("Cell info", True, TXT_DIM)
        screen.blit(t, (PX, info_y - 8))

        if hover and hover in game.cell_set:
            x, y, z = hover
            lbl = _cell_label(x, y, z)
            t = fn_body.render(f"{lbl}", True, TXT)
            screen.blit(t, (PX, info_y + 14))
            t = fn_small.render(f"cube  ({x}, {y}, {z})", True, TXT_DIM)
            screen.blit(t, (PX + 55, info_y + 16))

            if hover in game.stacks:
                col, ht = game.stacks[hover]
                cn = COLOUR_NAME[col]
                t = fn_small.render(f"Stack:  {cn}  height {ht}", True, TXT)
                screen.blit(t, (PX, info_y + 40))

            if game.phase == PH_PLAY:
                fr = game._flos(hover, RED)
                fw = game._flos(hover, WHITE)
                t = fn_small.render(f"LOS →  Red: {fr}   White: {fw}", True, TXT_DIM)
                screen.blit(t, (PX, info_y + 62))
        else:
            t = fn_small.render("hover a cell …", True, TXT_DIM)
            screen.blit(t, (PX, info_y + 14))

        # ── buttons ───────────────────────────────────────
        if game.phase == PH_PLAY:
            btn_pass.draw(screen, fn_body)
        btn_new.draw(screen, fn_body)

        # ── bottom status bar ─────────────────────────────
        pygame.draw.rect(screen, STATUS_BG, (0, WIN_H - 38, WIN_W, 38))
        t = fn_body.render(game.msg, True, TXT)
        screen.blit(t, (18, WIN_H - 30))

        # keyboard hints on the right of status bar
        t = fn_tiny.render("N = New game    P = Pass    Q = Quit", True, TXT_DIM)
        screen.blit(t, (WIN_W - t.get_width() - 18, WIN_H - 26))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()