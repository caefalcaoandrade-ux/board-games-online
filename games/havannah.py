#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════╗
║   H A V A N N A H  –  Local Human vs Human Board Game    ║
║   Pygame implementation · Cube-coordinate hex geometry    ║
╚═══════════════════════════════════════════════════════════╝

Run:  python havannah.py [board_size]
      Default board_size = 8  (standard: 8 or 10)

Controls:
  Left-click   Place a stone / click buttons
  R            Reset game
  Esc / Q      Quit
"""

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
import sys
import math
from collections import deque

# ─────────────────────────────────────────────────────────
# PALETTE
# ─────────────────────────────────────────────────────────
BG              = (32,  33,  38)
EMPTY_FILL      = (62,  66,  74)
EMPTY_STROKE    = (82,  86,  94)
WHITE_STONE     = (235, 235, 230)
WHITE_OUTLINE   = (190, 190, 185)
BLACK_STONE     = (30,  30,  34)
BLACK_OUTLINE   = (70,  70,  76)
HOVER_W         = (170, 190, 220)
HOVER_B         = (100,  85, 130)
CORNER_ACCENT   = (255, 175,  50)
SIDE_ACCENT     = (60,  170, 240)
WIN_GLOW        = (80,  255, 120)
LAST_MOVE_MARK  = (220,  60,  70)
TEXT_PRIMARY     = (210, 212, 218)
TEXT_DIM         = (130, 134, 142)
PANEL_BG        = (40,  42,  48)
BTN_SWAP_BG     = (85,  65, 145)
BTN_SWAP_BORDER = (125, 105, 185)
BTN_NEW_BG      = (55, 105,  55)
BTN_NEW_BORDER  = (85, 145,  85)


# ─────────────────────────────────────────────────────────
# GAME LOGIC
# ─────────────────────────────────────────────────────────
class HavannahGame:
    """Full Havannah rules engine with union-find chain tracking."""

    DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

    def __init__(self, size: int = 8):
        self.size = size
        self._precompute()
        self.reset()

    # ── static geometry ──────────────────────────────────
    def _precompute(self):
        S = self.size
        self.cells: set[tuple[int, int]] = set()
        for q in range(-(S - 1), S):
            for r in range(-(S - 1), S):
                if max(abs(q), abs(r), abs(-q - r)) <= S - 1:
                    self.cells.add((q, r))

        # corners: exactly 2 of |q|,|r|,|s| == S-1
        corner_qrs = [
            (S - 1, -(S - 1), 0), (S - 1, 0, -(S - 1)),
            (0, S - 1, -(S - 1)), (-(S - 1), S - 1, 0),
            (-(S - 1), 0, S - 1), (0, -(S - 1), S - 1),
        ]
        self.corners = [(q, r) for q, r, _ in corner_qrs]
        self.corner_set = set(self.corners)
        self.corner_index: dict[tuple[int, int], int] = {
            c: i for i, c in enumerate(self.corners)
        }

        # 6 sides (boundary minus corners)
        self.sides: list[set[tuple[int, int]]] = [set() for _ in range(6)]
        for qr in self.cells:
            q, r = qr
            s = -q - r
            if qr in self.corner_set:
                continue
            if max(abs(q), abs(r), abs(s)) < S - 1:
                continue
            if   s == -(S - 1): self.sides[0].add(qr)
            elif q ==  (S - 1): self.sides[1].add(qr)
            elif r == -(S - 1): self.sides[2].add(qr)
            elif s ==  (S - 1): self.sides[3].add(qr)
            elif q == -(S - 1): self.sides[4].add(qr)
            elif r ==  (S - 1): self.sides[5].add(qr)

        self.side_index: dict[tuple[int, int], int] = {}
        for i, side in enumerate(self.sides):
            for c in side:
                self.side_index[c] = i

        # boundary (corners + sides)
        self.boundary: set[tuple[int, int]] = set()
        for qr in self.cells:
            q, r = qr
            if max(abs(q), abs(r), abs(-q - r)) == S - 1:
                self.boundary.add(qr)

        # neighbor lookup
        self.neighbors: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for qr in self.cells:
            q, r = qr
            self.neighbors[qr] = [
                (q + dq, r + dr)
                for dq, dr in self.DIRS
                if (q + dq, r + dr) in self.cells
            ]

        # human-readable labels  (row letter + column number)
        self.cell_label: dict[tuple[int, int], str] = {}
        S = self.size
        row_i = 0
        for r in range(S - 1, -(S), -1):
            row_cells = sorted([c for c in self.cells if c[1] == r])
            letter = chr(ord('A') + row_i)
            for ci, c in enumerate(row_cells):
                self.cell_label[c] = f"{letter}{ci + 1}"
            row_i += 1

    # ── state management ─────────────────────────────────
    def reset(self):
        self.board: dict[tuple[int, int], str] = {}
        self.current_player: str = 'W'
        self.move_count: int = 0
        self.swap_available: bool = False
        self.game_over: bool = False
        self.winner: str | None = None
        self.win_type: str | None = None
        self.winning_chain: set[tuple[int, int]] = set()
        self.last_move: tuple[int, int] | None = None
        self.history: list = []
        # union-find
        self._par: dict[tuple[int, int], tuple[int, int]] = {}
        self._rnk: dict[tuple[int, int], int] = {}
        self._ch_corners: dict[tuple[int, int], set[int]] = {}
        self._ch_sides:   dict[tuple[int, int], set[int]] = {}

    # ── union-find ───────────────────────────────────────
    def _find(self, x):
        while self._par[x] != x:
            self._par[x] = self._par[self._par[x]]
            x = self._par[x]
        return x

    def _union(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return ra
        if self._rnk[ra] < self._rnk[rb]:
            ra, rb = rb, ra
        self._par[rb] = ra
        if self._rnk[ra] == self._rnk[rb]:
            self._rnk[ra] += 1
        self._ch_corners[ra] |= self._ch_corners.pop(rb)
        self._ch_sides[ra]   |= self._ch_sides.pop(rb)
        return ra

    def _chain_cells(self, root) -> set[tuple[int, int]]:
        return {c for c in self.board if self._find(c) == root}

    # ── moves ────────────────────────────────────────────
    def place(self, cell: tuple[int, int]) -> bool:
        if self.game_over or cell not in self.cells or cell in self.board:
            return False

        color = self.current_player
        self.board[cell] = color
        self.move_count += 1
        self.last_move = cell
        self.history.append(('place', cell, color))

        # init UF node
        self._par[cell] = cell
        self._rnk[cell] = 0
        self._ch_corners[cell] = set()
        self._ch_sides[cell]   = set()
        if cell in self.corner_index:
            self._ch_corners[cell].add(self.corner_index[cell])
        if cell in self.side_index:
            self._ch_sides[cell].add(self.side_index[cell])

        # merge adjacent same-color
        for nb in self.neighbors[cell]:
            if nb in self.board and self.board[nb] == color:
                self._union(cell, nb)

        # ── check wins ───────────────────────────────────
        root = self._find(cell)
        if len(self._ch_corners[root]) >= 2:
            return self._declare_win(color, "Bridge", root)
        if len(self._ch_sides[root]) >= 3:
            return self._declare_win(color, "Fork", root)
        if self._has_ring(color):
            chain = self._ring_chain(color)
            self.game_over = True
            self.winner = color
            self.win_type = "Ring"
            self.winning_chain = chain
            return True

        # draw?
        if len(self.board) == len(self.cells):
            self.game_over = True
            self.win_type = "Draw"
            return True

        # swap window
        if self.move_count == 1:
            self.swap_available = True
        else:
            self.swap_available = False

        self.current_player = 'B' if color == 'W' else 'W'
        return True

    def swap(self) -> bool:
        if not self.swap_available or self.move_count != 1:
            return False
        # players exchange roles; the stone stays White,
        # new-Black (formerly White) moves next
        self.swap_available = False
        self.current_player = 'B'
        self.history.append(('swap',))
        return True

    def _declare_win(self, color, wtype, root):
        self.game_over = True
        self.winner = color
        self.win_type = wtype
        self.winning_chain = self._chain_cells(root)
        return True

    # ── ring detection (flood-fill background) ───────────
    def _has_ring(self, color: str) -> bool:
        occupied = {c for c, cl in self.board.items() if cl == color}
        if len(occupied) < 6:
            return False
        background = self.cells - occupied
        visited: set[tuple[int, int]] = set()
        for start in background:
            if start in visited:
                continue
            touches_edge = False
            queue = deque([start])
            visited.add(start)
            component: list[tuple[int, int]] = []
            while queue:
                cur = queue.popleft()
                component.append(cur)
                if cur in self.boundary:
                    touches_edge = True
                for nb in self.neighbors[cur]:
                    if nb in background and nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if not touches_edge:
                return True
        return False

    def _ring_chain(self, color: str) -> set[tuple[int, int]]:
        occupied = {c for c, cl in self.board.items() if cl == color}
        background = self.cells - occupied
        visited: set[tuple[int, int]] = set()
        enclosed: set[tuple[int, int]] = set()
        for start in background:
            if start in visited:
                continue
            touches_edge = False
            queue = deque([start])
            visited.add(start)
            comp: list[tuple[int, int]] = []
            while queue:
                cur = queue.popleft()
                comp.append(cur)
                if cur in self.boundary:
                    touches_edge = True
                for nb in self.neighbors[cur]:
                    if nb in background and nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if not touches_edge:
                enclosed.update(comp)
        # the ring = player cells neighbouring the enclosed region
        ring: set[tuple[int, int]] = set()
        for c in enclosed:
            for nb in self.neighbors[c]:
                if nb in occupied:
                    ring.add(nb)
        if ring:
            root = self._find(next(iter(ring)))
            return self._chain_cells(root)
        return occupied


# ─────────────────────────────────────────────────────────
# RENDERER  /  GUI
# ─────────────────────────────────────────────────────────
class HavannahGUI:

    def __init__(self, board_size: int = 8):
        pygame.init()
        self.game = HavannahGame(board_size)
        S = board_size

        # auto-scale hex size to fit comfortably
        self.hex_size = max(18, min(42, int(830 / (3 * (S - 1)))))
        hs = self.hex_size
        sqrt3 = math.sqrt(3)

        board_w = sqrt3 * hs * (2 * S - 1) + hs
        board_h = 1.5  * hs * (2 * S - 1) + hs

        margin = 70
        self.panel_w = 230

        self.win_w = int(board_w + 2 * margin + self.panel_w)
        self.win_h = int(max(board_h + 2 * margin + 10, 680))

        self.cx = margin + board_w / 2
        self.cy = self.win_h / 2

        self.screen = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.display.set_caption("Havannah")
        self.clock = pygame.time.Clock()
        self.hovered: tuple[int, int] | None = None

        # precompute pixel centers
        self.centers: dict[tuple[int, int], tuple[float, float]] = {
            c: self._hex_px(c) for c in self.game.cells
        }

        # precompute hex vertex offsets (pointy-top)
        self.hex_verts = []
        for i in range(6):
            a = math.radians(30 + 60 * i)
            self.hex_verts.append((math.cos(a), math.sin(a)))

        # fonts
        self.f_tiny  = pygame.font.SysFont("consolas,monospace", max(10, hs // 3))
        self.f_small = pygame.font.SysFont("segoeui,arial,sans-serif", max(12, hs // 2 - 1))
        self.f_med   = pygame.font.SysFont("segoeui,arial,sans-serif", 17, bold=True)
        self.f_large = pygame.font.SysFont("segoeui,arial,sans-serif", 24, bold=True)
        self.f_title = pygame.font.SysFont("segoeui,arial,sans-serif", 30, bold=True)

        # button rects (set during draw)
        self.btn_swap  = pygame.Rect(0, 0, 0, 0)
        self.btn_reset = pygame.Rect(0, 0, 0, 0)

    # ── coordinate transforms ────────────────────────────
    def _hex_px(self, cell):
        q, r = cell
        x = self.hex_size * math.sqrt(3) * (q + r / 2.0)
        y = self.hex_size * 1.5 * r
        return (self.cx + x, self.cy + y)

    def _px_to_hex(self, mx, my):
        x = mx - self.cx
        y = my - self.cy
        hs = self.hex_size
        q = (math.sqrt(3) / 3 * x - y / 3) / hs
        r = (2.0 / 3 * y) / hs
        return self._cube_round(q, r)

    def _cube_round(self, q, r):
        s = -q - r
        rq, rr, rs = round(q), round(r), round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds:
            rq = -rr - rs
        elif dr > ds:
            rr = -rq - rs
        cell = (rq, rr)
        return cell if cell in self.game.cells else None

    # ── hex drawing ──────────────────────────────────────
    def _hex_points(self, cx, cy, sz):
        return [(cx + sz * dx, cy + sz * dy) for dx, dy in self.hex_verts]

    def _draw_hex(self, cx, cy, sz, fill, stroke=None, sw=1):
        pts = self._hex_points(cx, cy, sz)
        pygame.draw.polygon(self.screen, fill, pts)
        if stroke:
            pygame.draw.aalines(self.screen, stroke, True, pts)
            if sw > 1:
                pygame.draw.polygon(self.screen, stroke, pts, sw)

    # ── main draw ────────────────────────────────────────
    def draw(self):
        self.screen.fill(BG)
        g = self.game
        hs = self.hex_size

        # ── board cells ──────────────────────────────────
        for cell in g.cells:
            cx, cy = self.centers[cell]
            stone = g.board.get(cell)

            # pick colours
            if g.game_over and cell in g.winning_chain:
                fill = WIN_GLOW
                stroke = (40, 200, 80)
                sw = 2
            elif stone == 'W':
                fill = WHITE_STONE
                stroke = WHITE_OUTLINE
                sw = 2
            elif stone == 'B':
                fill = BLACK_STONE
                stroke = BLACK_OUTLINE
                sw = 2
            elif cell == self.hovered and not g.game_over:
                fill = HOVER_W if g.current_player == 'W' else HOVER_B
                stroke = EMPTY_STROKE
                sw = 1
            else:
                fill = EMPTY_FILL
                stroke = EMPTY_STROKE
                sw = 1

            # topology accent for border cells
            if cell in g.corner_set and stone is None and not (g.game_over and cell in g.winning_chain):
                stroke = CORNER_ACCENT
                sw = 2
            elif cell in g.side_index and stone is None and not (g.game_over and cell in g.winning_chain):
                stroke = SIDE_ACCENT
                sw = 2

            self._draw_hex(cx, cy, hs - 1, fill, stroke, sw)

            # last-move dot
            if cell == g.last_move and not g.game_over:
                dot_col = BLACK_STONE if stone == 'W' else WHITE_STONE
                pygame.draw.circle(self.screen, dot_col, (int(cx), int(cy)), max(3, hs // 7))

            # coordinate label on hover (empty cells)
            if cell == self.hovered and stone is None and not g.game_over:
                lbl = g.cell_label.get(cell, "")
                surf = self.f_tiny.render(lbl, True, TEXT_PRIMARY)
                self.screen.blit(surf, (cx - surf.get_width() // 2,
                                        cy - surf.get_height() // 2))

        # ── edge labels ──────────────────────────────────
        self._draw_edge_labels()

        # ── side panel ───────────────────────────────────
        self._draw_panel()

        pygame.display.flip()

    # ── edge labels ──────────────────────────────────────
    def _draw_edge_labels(self):
        g = self.game
        S = g.size
        hs = self.hex_size
        offset = hs * 1.35

        # row letters (left side of each row)
        row_i = 0
        for r in range(S - 1, -S, -1):
            row = sorted([c for c in g.cells if c[1] == r])
            if not row:
                continue
            letter = chr(ord('A') + row_i)
            lx, ly = self.centers[row[0]]
            surf = self.f_small.render(letter, True, TEXT_DIM)
            self.screen.blit(surf, (lx - offset - surf.get_width() // 2,
                                     ly - surf.get_height() // 2))
            row_i += 1

        # column numbers along the bottom row
        bottom_row = sorted([c for c in g.cells if c[1] == S - 1])
        for ci, cell in enumerate(bottom_row):
            bx, by = self.centers[cell]
            num = str(ci + 1)
            surf = self.f_small.render(num, True, TEXT_DIM)
            self.screen.blit(surf, (bx - surf.get_width() // 2,
                                     by + offset - surf.get_height() // 2 + 2))

    # ── info panel ───────────────────────────────────────
    def _draw_panel(self):
        g = self.game
        px = self.win_w - self.panel_w + 10
        y = 28

        # panel background
        panel_rect = pygame.Rect(self.win_w - self.panel_w - 5, 0, self.panel_w + 5, self.win_h)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)
        pygame.draw.line(self.screen, EMPTY_STROKE,
                         (panel_rect.x, 0), (panel_rect.x, self.win_h), 1)

        # title
        surf = self.f_title.render("HAVANNAH", True, TEXT_PRIMARY)
        self.screen.blit(surf, (px, y)); y += 42

        # board size
        surf = self.f_small.render(f"Board size {g.size}  ·  {len(g.cells)} cells", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 30

        # ── turn info ────────────────────────────────────
        pygame.draw.line(self.screen, EMPTY_STROKE, (px, y), (px + self.panel_w - 30, y))
        y += 12

        if not g.game_over:
            name = "White" if g.current_player == 'W' else "Black"
            surf = self.f_med.render(f"{name}'s turn", True, TEXT_PRIMARY)
            self.screen.blit(surf, (px, y))

            # stone indicator
            ind_col = WHITE_STONE if g.current_player == 'W' else BLACK_STONE
            ind_out = WHITE_OUTLINE if g.current_player == 'W' else BLACK_OUTLINE
            ind_x = px + surf.get_width() + 18
            ind_y = y + surf.get_height() // 2
            pygame.draw.circle(self.screen, ind_col, (ind_x, ind_y), 9)
            pygame.draw.circle(self.screen, ind_out, (ind_x, ind_y), 9, 2)
            y += 34

        surf = self.f_med.render(f"Move  {g.move_count}", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 34

        # ── hovered cell ─────────────────────────────────
        if self.hovered and not g.game_over:
            lbl = g.cell_label.get(self.hovered, "?")
            q, r = self.hovered
            surf = self.f_med.render(f"Cell  {lbl}", True, TEXT_PRIMARY)
            self.screen.blit(surf, (px, y)); y += 22
            surf = self.f_tiny.render(f"q={q}  r={r}  s={-q - r}", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 18

            # topology tag
            tag = ""
            if self.hovered in g.corner_set:
                tag = "Corner"
            elif self.hovered in g.side_index:
                tag = f"Side {g.side_index[self.hovered] + 1}"
            else:
                if max(abs(q), abs(r), abs(-q - r)) < g.size - 1:
                    tag = "Interior"
            if tag:
                surf = self.f_tiny.render(tag, True, TEXT_DIM)
                self.screen.blit(surf, (px, y))
            y += 22
        else:
            y += 62

        # ── swap button ──────────────────────────────────
        if g.swap_available and g.move_count == 1 and not g.game_over:
            btn = pygame.Rect(px, y, 170, 36)
            self.btn_swap = btn
            pygame.draw.rect(self.screen, BTN_SWAP_BG, btn, border_radius=6)
            pygame.draw.rect(self.screen, BTN_SWAP_BORDER, btn, 2, border_radius=6)
            surf = self.f_med.render("⇄  SWAP", True, (220, 215, 255))
            self.screen.blit(surf, (btn.centerx - surf.get_width() // 2,
                                     btn.centery - surf.get_height() // 2))
            y += 50

            surf = self.f_tiny.render("Black claims White's", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 15
            surf = self.f_tiny.render("opening stone.", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 25
        else:
            self.btn_swap = pygame.Rect(0, 0, 0, 0)

        # ── game over ────────────────────────────────────
        if g.game_over:
            y += 6
            if g.winner:
                wn = "White" if g.winner == 'W' else "Black"
                surf = self.f_large.render(f"{wn} wins!", True, WIN_GLOW)
                self.screen.blit(surf, (px, y)); y += 32
                surf = self.f_med.render(f"by {g.win_type}", True, WIN_GLOW)
                self.screen.blit(surf, (px, y)); y += 36
            else:
                surf = self.f_large.render("Draw!", True, TEXT_PRIMARY)
                self.screen.blit(surf, (px, y)); y += 36

            btn = pygame.Rect(px, y, 170, 38)
            self.btn_reset = btn
            pygame.draw.rect(self.screen, BTN_NEW_BG, btn, border_radius=6)
            pygame.draw.rect(self.screen, BTN_NEW_BORDER, btn, 2, border_radius=6)
            surf = self.f_med.render("NEW GAME", True, (180, 255, 180))
            self.screen.blit(surf, (btn.centerx - surf.get_width() // 2,
                                     btn.centery - surf.get_height() // 2))
            y += 52
        else:
            self.btn_reset = pygame.Rect(0, 0, 0, 0)

        # ── win conditions legend ────────────────────────
        y = self.win_h - 185
        pygame.draw.line(self.screen, EMPTY_STROKE, (px, y), (px + self.panel_w - 30, y))
        y += 12
        surf = self.f_small.render("Win conditions", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 24

        for label in ("Bridge – 2 corners", "Fork   – 3 sides", "Ring   – closed loop"):
            surf = self.f_tiny.render(label, True, TEXT_DIM)
            self.screen.blit(surf, (px + 4, y)); y += 18

        y += 10
        surf = self.f_small.render("Legend", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 22

        for color, label in [(CORNER_ACCENT, "Corner cell"),
                             (SIDE_ACCENT,   "Side cell"),
                             (WIN_GLOW,      "Winning chain")]:
            pygame.draw.circle(self.screen, color, (px + 8, y + 5), 5)
            surf = self.f_tiny.render(label, True, TEXT_DIM)
            self.screen.blit(surf, (px + 20, y)); y += 20

        y += 6
        surf = self.f_tiny.render("R = reset   Esc = quit", True, TEXT_DIM)
        self.screen.blit(surf, (px, y))

    # ── input handling ───────────────────────────────────
    def _click(self, pos):
        if self.btn_swap.collidepoint(pos):
            self.game.swap()
            return
        if self.btn_reset.collidepoint(pos):
            self.game.reset()
            return
        cell = self._px_to_hex(pos[0], pos[1])
        if cell:
            self.game.place(cell)

    # ── main loop ────────────────────────────────────────
    def run(self):
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif ev.key == pygame.K_r:
                        self.game.reset()
                elif ev.type == pygame.MOUSEMOTION:
                    self.hovered = self._px_to_hex(ev.pos[0], ev.pos[1])
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self._click(ev.pos)

            self.draw()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    size = 8
    if len(sys.argv) > 1:
        try:
            s = int(sys.argv[1])
            if 3 <= s <= 15:
                size = s
            else:
                print(f"Board size must be 3-15. Using default {size}.")
        except ValueError:
            print(f"Invalid size argument. Using default {size}.")

    HavannahGUI(size).run()