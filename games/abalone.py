"""
Abalone – Two-Player Board Game (Belgian Daisy)
================================================
A complete, interactive implementation using Pygame.

Controls:
  Left-click own marble  → select / deselect
  Left-click empty cell  → move selected group in that direction
  Left-click enemy marble→ push in that direction (if legal)
  Right-click            → clear selection
  U                      → undo last move
  R                      → restart game
  Esc                    → quit
"""

import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

# ──────────────────────────── Constants ────────────────────────────

WINDOW_W, WINDOW_H = 1100, 920
FPS = 60

# Piece codes
EMPTY, BLACK, WHITE = 0, 1, 2

# Row lengths for the hex board (R1–R9)
ROW_LENS = (5, 6, 7, 8, 9, 8, 7, 6, 5)

# Six unit directions in cube coordinates (dx, dy, dz)  x+y+z == 0
DIRS = [
    ( 1, -1,  0),  # E
    ( 1,  0, -1),  # NE
    ( 0,  1, -1),  # NW
    (-1,  1,  0),  # W
    (-1,  0,  1),  # SW
    ( 0, -1,  1),  # SE
]

# ── Visual layout ─────────────────────────────────────────────────
CELL_SP   = 70            # pixel distance between adjacent cell centers
CELL_R    = 29            # cell-pit drawn radius
MARBLE_R  = 25            # marble drawn radius
BOARD_CX  = WINDOW_W // 2
BOARD_CY  = WINDOW_H // 2 + 5
ROW_DY    = CELL_SP * math.sqrt(3) / 2.0   # ≈ 60.6

# ── Warm colour palette ──────────────────────────────────────────
C_BG          = ( 42,  38,  34)

# Board wood tones
C_BOARD       = (190, 155, 100)
C_BOARD_LT    = (210, 175, 120)
C_BOARD_DK    = (140, 110,  68)
C_BOARD_EDGE  = (110,  85,  50)

# Cell pit
C_PIT         = (130, 100,  62)
C_PIT_INNER   = (105,  80,  48)
C_PIT_EDGE    = (100,  78,  46)

# Black marble
C_BLK_BODY    = ( 30,  30,  35)
C_BLK_MID     = ( 55,  55,  62)
C_BLK_SHINE   = (120, 120, 130)
C_BLK_RIM     = ( 18,  18,  22)

# White marble
C_WHT_BODY    = (235, 230, 218)
C_WHT_MID     = (215, 210, 198)
C_WHT_SHINE   = (255, 255, 255)
C_WHT_RIM     = (170, 165, 152)

# UI accents
C_SEL_RING    = (255, 210,  50)
C_HINT_MOVE   = ( 80, 200, 100)
C_HINT_PUSH   = (240, 160,  50)
C_COORD       = ( 90,  72,  44)
C_LABEL       = ( 75,  60,  35)
C_MSG_ERR     = (255, 100,  90)
C_MSG_OK      = (100, 210, 120)
C_DIM         = (120, 100,  70)
C_TURN_BLK    = (200, 200, 210)
C_TURN_WHT    = (240, 235, 225)

# ═══════════════════════════════════════════════════════════════════
#  Coordinate helpers  (cube coords: x+y+z == 0, board radius 4)
# ═══════════════════════════════════════════════════════════════════

def rc_to_cube(r: int, c: int) -> tuple:
    """0-indexed (row, col) → cube (x, y, z)."""
    z = r - 4
    x = c - min(4, r)
    y = -x - z
    return (x, y, z)

def cube_to_rc(x: int, y: int, z: int) -> tuple:
    """Cube (x, y, z) → 0-indexed (row, col)."""
    r = z + 4
    c = x + min(4, r)
    return (r, c)

def on_board(x: int, y: int, z: int) -> bool:
    return (x + y + z == 0) and max(abs(x), abs(y), abs(z)) <= 4

def cube_add(a, d):
    return (a[0]+d[0], a[1]+d[1], a[2]+d[2])

def cube_sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def cube_dist(a, b):
    d = cube_sub(a, b)
    return max(abs(d[0]), abs(d[1]), abs(d[2]))

def cube_to_pixel(cube):
    """Cube coordinates → pixel position on screen."""
    r, c = cube_to_rc(*cube)
    rl = ROW_LENS[r]
    px = BOARD_CX + (c - (rl - 1) / 2.0) * CELL_SP
    py = BOARD_CY + (r - 4) * ROW_DY
    return (px, py)


# ═══════════════════════════════════════════════════════════════════
#  Game Logic
# ═══════════════════════════════════════════════════════════════════

class AbaloneGame:
    """Full Abalone rules engine (Belgian Daisy, 2-player)."""

    def __init__(self):
        self.board: dict[tuple, int] = {}
        self.turn = BLACK
        self.captured = {BLACK: 0, WHITE: 0}
        self.game_over = False
        self.winner = None
        self.history: list = []
        self._init_belgian_daisy()

    def _init_belgian_daisy(self):
        for r in range(9):
            for c in range(ROW_LENS[r]):
                self.board[rc_to_cube(r, c)] = EMPTY

        for r, c in [(0,3),(0,4),(1,3),(1,4),(1,5),(2,4),(2,5),
                      (6,1),(6,2),(7,0),(7,1),(7,2),(8,0),(8,1)]:
            self.board[rc_to_cube(r, c)] = BLACK

        for r, c in [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1),(2,2),
                      (6,4),(6,5),(7,3),(7,4),(7,5),(8,3),(8,4)]:
            self.board[rc_to_cube(r, c)] = WHITE

    # ── group helpers ─────────────────────────────────────────────

    @staticmethod
    def _collinear(positions) -> bool:
        if len(positions) < 2:
            return True
        p0 = positions[0]
        d0 = cube_sub(positions[1], p0)
        dist0 = max(abs(d0[0]), abs(d0[1]), abs(d0[2]))
        if dist0 == 0:
            return False
        unit = (d0[0]//dist0, d0[1]//dist0, d0[2]//dist0)
        if unit not in DIRS:
            return False
        neg = (-unit[0], -unit[1], -unit[2])
        for p in positions[2:]:
            d = cube_sub(p, p0)
            dl = max(abs(d[0]), abs(d[1]), abs(d[2]))
            if dl == 0:
                return False
            u = (d[0]//dl, d[1]//dl, d[2]//dl)
            if u != unit and u != neg:
                return False
        return True

    @staticmethod
    def _contiguous(positions) -> bool:
        if len(positions) <= 1:
            return True
        if len(positions) == 2:
            return cube_dist(positions[0], positions[1]) == 1
        dists = sorted(cube_dist(positions[i], positions[j])
                       for i in range(3) for j in range(i+1, 3))
        return dists == [1, 1, 2]

    def valid_group(self, positions) -> bool:
        if not 1 <= len(positions) <= 3:
            return False
        if any(self.board.get(p) != self.turn for p in positions):
            return False
        if len(positions) == 1:
            return True
        return self._collinear(positions) and self._contiguous(positions)

    @staticmethod
    def _group_axis(positions):
        d = cube_sub(positions[1], positions[0])
        dl = max(abs(d[0]), abs(d[1]), abs(d[2]))
        return (d[0]//dl, d[1]//dl, d[2]//dl)

    @staticmethod
    def _sort_along(positions, direction):
        def proj(p):
            return p[0]*direction[0] + p[1]*direction[1] + p[2]*direction[2]
        return sorted(positions, key=proj)

    # ── state management ──────────────────────────────────────────

    def _save(self):
        self.history.append((
            dict(self.board), self.turn, dict(self.captured),
            self.game_over, self.winner))

    def undo(self) -> bool:
        if not self.history:
            return False
        self.board, self.turn, self.captured, self.game_over, self.winner = \
            self.history.pop()
        return True

    # ── move execution ────────────────────────────────────────────

    def try_move(self, selected: list, direction: tuple, real=True) -> bool:
        if self.game_over:
            return False
        if not self.valid_group(selected):
            return False

        n = len(selected)

        # Single marble
        if n == 1:
            dest = cube_add(selected[0], direction)
            if not on_board(*dest) or self.board.get(dest, -1) != EMPTY:
                return False
            if real:
                self._save()
                self.board[dest] = self.turn
                self.board[selected[0]] = EMPTY
                self._next_turn()
            return True

        # Multi-marble: inline vs side-step
        axis = self._group_axis(selected)
        neg_axis = (-axis[0], -axis[1], -axis[2])
        if direction == axis or direction == neg_axis:
            return self._do_inline(selected, direction, real)
        else:
            return self._do_sidestep(selected, direction, real)

    def _do_inline(self, selected, direction, real) -> bool:
        ordered = self._sort_along(selected, direction)
        front, tail = ordered[-1], ordered[0]
        ahead = cube_add(front, direction)

        if not on_board(*ahead):
            return False

        cell_ahead = self.board[ahead]
        opp = WHITE if self.turn == BLACK else BLACK

        # Empty ahead → simple advance
        if cell_ahead == EMPTY:
            if real:
                self._save()
                self.board[ahead] = self.turn
                self.board[tail]  = EMPTY
                self._next_turn()
            return True

        # Own marble ahead → blocked
        if cell_ahead == self.turn:
            return False

        # Opponent ahead → push attempt
        enemies = []
        pos = ahead
        while on_board(*pos) and self.board.get(pos) == opp:
            enemies.append(pos)
            pos = cube_add(pos, direction)

        n_fr, n_en = len(selected), len(enemies)
        if n_fr <= n_en or n_en > 2:
            return False

        beyond = pos

        if on_board(*beyond):
            if self.board[beyond] != EMPTY:
                return False
            if real:
                self._save()
                self.board[beyond] = opp
                self.board[ahead]  = self.turn
                self.board[tail]   = EMPTY
                self._next_turn()
        else:
            # Ejection
            if real:
                self._save()
                self.captured[self.turn] += 1
                if n_en == 2:
                    self.board[enemies[1]] = opp
                self.board[ahead] = self.turn
                self.board[tail]  = EMPTY
                if self.captured[self.turn] >= 6:
                    self.game_over = True
                    self.winner = self.turn
                self._next_turn()
        return True

    def _do_sidestep(self, selected, direction, real) -> bool:
        dests = []
        for p in selected:
            d = cube_add(p, direction)
            if not on_board(*d) or self.board.get(d, -1) != EMPTY:
                return False
            dests.append(d)
        if real:
            self._save()
            for p in selected:
                self.board[p] = EMPTY
            for d in dests:
                self.board[d] = self.turn
            self._next_turn()
        return True

    def _next_turn(self):
        if not self.game_over:
            self.turn = WHITE if self.turn == BLACK else BLACK

    # ── query helpers ─────────────────────────────────────────────

    def can_add(self, selected, pos) -> bool:
        if self.board.get(pos) != self.turn:
            return False
        ns = selected + [pos]
        if len(ns) > 3:
            return False
        if len(ns) == 1:
            return True
        return self._collinear(ns) and self._contiguous(ns)

    def valid_targets(self, selected) -> dict:
        if not self.valid_group(selected):
            return {}
        targets = {}
        for d in DIRS:
            test = AbaloneGame.__new__(AbaloneGame)
            test.board    = dict(self.board)
            test.turn     = self.turn
            test.captured = dict(self.captured)
            test.game_over = self.game_over
            test.winner   = self.winner
            test.history  = []
            if not test.try_move(list(selected), d, real=False):
                continue
            ordered = self._sort_along(selected, d)
            ahead = cube_add(ordered[-1], d)
            is_push = (on_board(*ahead)
                       and self.board.get(ahead) not in (EMPTY, self.turn, None))
            for p in selected:
                c = cube_add(p, d)
                if on_board(*c) and c not in selected:
                    targets[c] = 'push' if is_push else 'move'
        return targets


# ═══════════════════════════════════════════════════════════════════
#  Rendering helpers
# ═══════════════════════════════════════════════════════════════════

def _lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _make_marble_surface(who: int, radius: int) -> pygame.Surface:
    """Pre-render a marble with 3D shading as an RGBA surface."""
    sz = radius * 2 + 8
    surf = pygame.Surface((sz, sz), pygame.SRCALPHA)
    cx, cy = sz // 2, sz // 2

    if who == BLACK:
        rim, body, mid, shine = C_BLK_RIM, C_BLK_BODY, C_BLK_MID, C_BLK_SHINE
    else:
        rim, body, mid, shine = C_WHT_RIM, C_WHT_BODY, C_WHT_MID, C_WHT_SHINE

    # Drop shadow
    pygame.draw.circle(surf, (0, 0, 0, 45), (cx + 2, cy + 3), radius)

    # Outer rim
    pygame.draw.circle(surf, rim, (cx, cy), radius)

    # Body with radial gradient (concentric circles)
    steps = max(10, radius // 2)
    for i in range(steps, 0, -1):
        t = i / steps
        r_i = int((radius - 2) * t)
        # Offset center toward upper-left for 3D illusion
        ox = cx - int(3.5 * (1 - t))
        oy = cy - int(4.5 * (1 - t))
        col = _lerp_color(mid, body, t)
        if r_i > 0:
            pygame.draw.circle(surf, col, (ox, oy), r_i)

    # Specular highlights
    pygame.draw.circle(surf, shine, (cx - 7, cy - 8), max(3, radius // 5))
    hl2 = _lerp_color(shine, mid, 0.45)
    pygame.draw.circle(surf, hl2, (cx - 5, cy - 6), max(2, radius // 4))

    return surf


def _board_hex_vertices(pad: float) -> list:
    """6 vertices of the board hexagon, expanded outward by `pad` pixels."""
    # Corner cells of the hex board
    corners = [
        rc_to_cube(4, 8),  # right       (R5 C9)
        rc_to_cube(0, 4),  # top-right   (R1 C5)
        rc_to_cube(0, 0),  # top-left    (R1 C1)
        rc_to_cube(4, 0),  # left        (R5 C1)
        rc_to_cube(8, 0),  # bottom-left (R9 C1)
        rc_to_cube(8, 4),  # bottom-right(R9 C5)
    ]
    pts = []
    for cube in corners:
        px, py = cube_to_pixel(cube)
        dx, dy = px - BOARD_CX, py - BOARD_CY
        dist = math.hypot(dx, dy)
        if dist > 0:
            px += dx / dist * pad
            py += dy / dist * pad
        else:
            px += pad
        pts.append((px, py))
    return pts


# ═══════════════════════════════════════════════════════════════════
#  Main UI
# ═══════════════════════════════════════════════════════════════════

class AbaloneUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Abalone — Belgian Daisy")
        self.clock = pygame.time.Clock()
        self.game = AbaloneGame()
        self.selected: list[tuple] = []
        self.msg = ""
        self.msg_timer = 0
        self.msg_color = C_MSG_ERR

        # Pre-compute pixel positions for all 61 cells
        self.pix: dict[tuple, tuple] = {}
        for r in range(9):
            for c in range(ROW_LENS[r]):
                cube = rc_to_cube(r, c)
                self.pix[cube] = cube_to_pixel(cube)

        # Pre-render marble surfaces
        self.marble_surf = {
            BLACK: _make_marble_surface(BLACK, MARBLE_R),
            WHITE: _make_marble_surface(WHITE, MARBLE_R),
        }

        # Board outline vertices (outer border, inner fill, innermost)
        self.hex_outer = _board_hex_vertices(CELL_R + 22)
        self.hex_mid   = _board_hex_vertices(CELL_R + 16)
        self.hex_inner = _board_hex_vertices(CELL_R + 8)

        # Fonts
        self.f_big   = pygame.font.SysFont("Arial", 34, bold=True)
        self.f_med   = pygame.font.SysFont("Arial", 20)
        self.f_sm    = pygame.font.SysFont("Arial", 14)
        self.f_coord = pygame.font.SysFont("Consolas", 12)
        self.f_lbl   = pygame.font.SysFont("Arial", 16, bold=True)

    # ── hit detection ─────────────────────────────────────────────

    def _hit(self, mx, my) -> tuple | None:
        best, bd = None, 1e9
        for cube, (px, py) in self.pix.items():
            d = math.hypot(mx - px, my - py)
            if d < CELL_R + 4 and d < bd:
                best, bd = cube, d
        return best

    def _dir_from_click(self, clicked) -> tuple | None:
        for d in DIRS:
            for p in self.selected:
                if cube_add(p, d) == clicked:
                    return d
        return None

    # ── input ─────────────────────────────────────────────────────

    def _on_left_click(self, mx, my):
        if self.game.game_over:
            return
        hit = self._hit(mx, my)
        if hit is None:
            self.selected.clear()
            return

        val = self.game.board.get(hit)
        if val == self.game.turn:
            if hit in self.selected:
                self.selected.remove(hit)
            elif self.game.can_add(self.selected, hit):
                self.selected.append(hit)
            else:
                self.selected = [hit]
        else:
            if not self.selected:
                return
            d = self._dir_from_click(hit)
            if d is None:
                self._flash("Click a cell adjacent to selection", C_MSG_ERR)
                return
            sel_copy = list(self.selected)
            if self.game.try_move(sel_copy, d, real=True):
                self.selected.clear()
                self._flash("", C_MSG_OK)
            else:
                self._flash("Illegal move", C_MSG_ERR)

    def _flash(self, msg, color):
        self.msg = msg
        self.msg_color = color
        self.msg_timer = 150

    # ── drawing ───────────────────────────────────────────────────

    def _draw_board(self):
        """Draw the wooden hexagonal board background with beveled edge."""
        # Dark outer edge
        pygame.draw.polygon(self.screen, C_BOARD_EDGE, self.hex_outer)
        # Mid tone
        pygame.draw.polygon(self.screen, C_BOARD_DK, self.hex_mid)
        # Inner fill (main board wood)
        pygame.draw.polygon(self.screen, C_BOARD, self.hex_inner)
        # Subtle lighter highlight
        inner2 = _board_hex_vertices(CELL_R + 2)
        pygame.draw.polygon(self.screen, C_BOARD_LT, inner2)

    def _draw_cells(self):
        targets = self.game.valid_targets(self.selected) if self.selected else {}

        for cube, (px, py) in self.pix.items():
            ipx, ipy = int(px), int(py)
            val = self.game.board[cube]

            # Cell pit (recessed hole in wood)
            pygame.draw.circle(self.screen, C_PIT_EDGE, (ipx, ipy), CELL_R)
            pygame.draw.circle(self.screen, C_PIT, (ipx, ipy), CELL_R - 2)
            pygame.draw.circle(self.screen, C_PIT_INNER, (ipx, ipy), CELL_R - 4)

            # Move/push hint
            if cube in targets:
                hcol = C_HINT_PUSH if targets[cube] == 'push' else C_HINT_MOVE
                pygame.draw.circle(self.screen, hcol, (ipx, ipy), 10)
                inner = _lerp_color(hcol, (255, 255, 255), 0.35)
                pygame.draw.circle(self.screen, inner, (ipx, ipy), 5)

            # Marble
            if val in (BLACK, WHITE):
                s = self.marble_surf[val]
                self.screen.blit(s,
                    (ipx - s.get_width() // 2, ipy - s.get_height() // 2))

            # Selection ring
            if cube in self.selected:
                pygame.draw.circle(self.screen, C_SEL_RING,
                                   (ipx, ipy), CELL_R + 2, 3)

            # Coordinate label (only on empty, unhinted cells)
            if val == EMPTY and cube not in targets:
                r, c = cube_to_rc(*cube)
                lbl = self.f_coord.render(f"{r+1}.{c+1}", True, C_COORD)
                self.screen.blit(lbl, (ipx - lbl.get_width() // 2,
                                       ipy - lbl.get_height() // 2))

    def _draw_labels(self):
        """Row labels R1–R9 on the left, column labels above R1 / below R9."""
        for r in range(9):
            cube = rc_to_cube(r, 0)
            px, py = self.pix[cube]
            lbl = self.f_lbl.render(f"R{r+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - CELL_R - 38,
                                   int(py) - lbl.get_height() // 2))

        for c in range(ROW_LENS[8]):
            px, py = self.pix[rc_to_cube(8, c)]
            lbl = self.f_coord.render(f"C{c+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - lbl.get_width() // 2,
                                   int(py) + CELL_R + 10))

        for c in range(ROW_LENS[0]):
            px, py = self.pix[rc_to_cube(0, c)]
            lbl = self.f_coord.render(f"C{c+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - lbl.get_width() // 2,
                                   int(py) - CELL_R - 18))

    def _draw_hud(self):
        g = self.game

        # Turn / Winner
        if g.game_over:
            name = "BLACK" if g.winner == BLACK else "WHITE"
            txt = self.f_big.render(f"{name}  WINS!", True, C_SEL_RING)
        else:
            name = "BLACK" if g.turn == BLACK else "WHITE"
            col  = C_TURN_BLK if g.turn == BLACK else C_TURN_WHT
            txt  = self.f_big.render(f"{name}'s turn", True, col)
        self.screen.blit(txt, (WINDOW_W // 2 - txt.get_width() // 2, 14))

        # Capture scores
        self._draw_score(BLACK, 30, WINDOW_H - 82)
        self._draw_score(WHITE, WINDOW_W - 280, WINDOW_H - 82)

        # Controls
        lines = [
            "LClick: select marble / move · RClick: deselect",
            "U: undo · R: restart · Esc: quit",
        ]
        for i, line in enumerate(lines):
            s = self.f_sm.render(line, True, C_DIM)
            self.screen.blit(s, (WINDOW_W // 2 - s.get_width() // 2,
                                 WINDOW_H - 34 + i * 16))

        # Flash message
        if self.msg_timer > 0 and self.msg:
            self.msg_timer -= 1
            s = self.f_med.render(self.msg, True, self.msg_color)
            self.screen.blit(s, (WINDOW_W // 2 - s.get_width() // 2, 54))

    def _draw_score(self, color, x, y):
        g = self.game
        name = "Black" if color == BLACK else "White"
        tcol = C_TURN_BLK if color == BLACK else C_TURN_WHT
        cap  = g.captured[color]
        lbl  = self.f_med.render(f"{name} captured:", True, tcol)
        self.screen.blit(lbl, (x, y))

        opp_body = C_WHT_BODY if color == BLACK else C_BLK_BODY
        opp_rim  = C_WHT_RIM  if color == BLACK else C_BLK_RIM
        for i in range(6):
            cx = x + lbl.get_width() + 16 + i * 24
            cy = y + lbl.get_height() // 2
            if i < cap:
                pygame.draw.circle(self.screen, opp_rim, (cx, cy), 9)
                pygame.draw.circle(self.screen, opp_body, (cx, cy), 7)
                pygame.draw.circle(self.screen, C_SEL_RING, (cx, cy), 9, 1)
            else:
                pygame.draw.circle(self.screen, C_PIT_EDGE, (cx, cy), 9)
                pygame.draw.circle(self.screen, C_PIT_INNER, (cx, cy), 7)

    # ── main loop ─────────────────────────────────────────────────

    def run(self):
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    if ev.button == 1:
                        self._on_left_click(*ev.pos)
                    elif ev.button == 3:
                        self.selected.clear()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_r:
                        self.game = AbaloneGame()
                        self.selected.clear()
                        self._flash("Game restarted", C_MSG_OK)
                    elif ev.key == pygame.K_u:
                        if self.game.undo():
                            self.selected.clear()
                            self._flash("Move undone", C_MSG_OK)
                        else:
                            self._flash("Nothing to undo", C_MSG_ERR)
                    elif ev.key == pygame.K_ESCAPE:
                        running = False

            self.screen.fill(C_BG)
            self._draw_board()
            self._draw_cells()
            self._draw_labels()
            self._draw_hud()
            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    AbaloneUI().run()