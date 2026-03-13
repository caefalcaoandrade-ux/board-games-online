"""
Copenhagen Hnefatafl 11×11 — Complete Implementation
=====================================================
Two-player hot-seat game using Pygame.

Controls
--------
  Left-click : select a piece, then click a highlighted square to move
  U          : undo last move
  R          : restart game
  ESC / Q    : quit
"""

import copy
import sys
from collections import defaultdict, deque

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

N = 11                       # board dimension
CELL = 68                    # pixel size of one cell
BOARD_PX = N * CELL          # total board pixels
LABEL_M = 44                 # margin for coordinate labels (left & bottom)
TOP_M = 16                   # top margin
RIGHT_M = 16                 # right margin
PANEL_H = 64                 # status panel height at the very bottom
WIN_W = LABEL_M + BOARD_PX + RIGHT_M
WIN_H = TOP_M + BOARD_PX + LABEL_M + PANEL_H

# Piece codes
EMPTY    = 0
ATTACKER = 1
DEFENDER = 2
KING     = 3

DIRS = ((0, 1), (0, -1), (1, 0), (-1, 0))

CORNERS  = frozenset(((0, 0), (0, 10), (10, 0), (10, 10)))
THRONE   = (5, 5)
RESTRICTED = CORNERS | {THRONE}

COL_LABELS = "ABCDEFGHIJK"   # 11 columns A–K (I is included)

# ── Initial setup (row, col); row 0 = game-row 1, col 0 = column A ──────────

INIT_KING = (5, 5)

INIT_DEFENDERS = [
    (5, 3), (4, 4), (5, 4), (6, 4),
    (3, 5), (4, 5), (6, 5), (7, 5),
    (4, 6), (5, 6), (6, 6), (5, 7),
]

INIT_ATTACKERS = [
    # left wing
    (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (5, 1),
    # bottom wing
    (0, 3), (0, 4), (0, 5), (1, 5), (0, 6), (0, 7),
    # top wing
    (10, 3), (10, 4), (10, 5), (9, 5), (10, 6), (10, 7),
    # right wing
    (5, 9), (3, 10), (4, 10), (5, 10), (6, 10), (7, 10),
]

# ── Colour palette ───────────────────────────────────────────────────────────

C_BG           = (40, 36, 32)
C_CELL_A       = (225, 202, 165)
C_CELL_B       = (213, 190, 153)
C_THRONE       = (186, 168, 132)
C_CORNER       = (164, 148, 118)
C_GRID         = (140, 128, 110)
C_MARK         = (130, 116, 96)
C_SEL_FILL     = (100, 190, 70, 70)
C_SEL_BORDER   = (100, 210, 60)
C_MOVE_DOT     = (80, 170, 60)
C_MOVE_RING    = (55, 130, 45)
C_LAST         = (210, 200, 80, 45)
C_CAPTURE_RING = (230, 55, 55)

C_ATK          = (62, 30, 22)
C_ATK_RIM      = (42, 18, 12)
C_DEF          = (242, 237, 224)
C_DEF_RIM      = (182, 174, 156)
C_KING_FILL    = (244, 222, 110)
C_KING_RIM     = (185, 155, 45)
C_KING_MARK    = (155, 120, 20)

C_PANEL        = (50, 45, 40)
C_TEXT         = (222, 214, 200)
C_LABEL        = (175, 165, 148)
C_ACCENT_ATK   = (180, 80, 60)
C_ACCENT_DEF   = (100, 170, 220)

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def in_bounds(r: int, c: int) -> bool:
    return 0 <= r < N and 0 <= c < N

def is_corner(r: int, c: int) -> bool:
    return (r, c) in CORNERS

def is_restricted(r: int, c: int) -> bool:
    return (r, c) in RESTRICTED

def is_edge(r: int, c: int) -> bool:
    return r == 0 or r == N - 1 or c == 0 or c == N - 1

def side_of(piece: int) -> int:
    """Return 0 for attacker side, 1 for defender/king side, -1 for empty."""
    if piece == ATTACKER:
        return 0
    if piece in (DEFENDER, KING):
        return 1
    return -1

def coord_label(r: int, c: int) -> str:
    """Human-readable coordinate, e.g. 'F6'."""
    return f"{COL_LABELS[c]}{r + 1}"

# ═══════════════════════════════════════════════════════════════════════════════
# GAME STATE
# ═══════════════════════════════════════════════════════════════════════════════

class Game:
    """Full Copenhagen Hnefatafl state + rules engine."""

    def __init__(self) -> None:
        self.board: list[list[int]] = [[EMPTY] * N for _ in range(N)]
        self.turn: int = ATTACKER          # attackers move first
        self.selected: tuple | None = None
        self.legal_moves: list[tuple] = []
        self.game_over: bool = False
        self.winner: int | None = None     # ATTACKER or DEFENDER when decided
        self.message: str = ""
        self.last_move: tuple | None = None          # ((fr,fc),(tr,tc))
        self.captured_last: list[tuple] = []          # squares captured last turn
        self.position_counts: dict = defaultdict(int)
        self._setup()
        self._record()
        self._update_message()

    # ── Setup ─────────────────────────────────────────────────────────────

    def _setup(self) -> None:
        self.board[INIT_KING[0]][INIT_KING[1]] = KING
        for r, c in INIT_DEFENDERS:
            self.board[r][c] = DEFENDER
        for r, c in INIT_ATTACKERS:
            self.board[r][c] = ATTACKER

    # ── Position hashing / repetition ─────────────────────────────────────

    def _pos_key(self) -> tuple:
        flat = tuple(self.board[r][c] for r in range(N) for c in range(N))
        return (flat, self.turn)

    def _record(self) -> None:
        self.position_counts[self._pos_key()] += 1

    def _unrecord(self) -> None:
        k = self._pos_key()
        self.position_counts[k] -= 1
        if self.position_counts[k] <= 0:
            del self.position_counts[k]

    def repetition_count(self) -> int:
        return self.position_counts.get(self._pos_key(), 0)

    # ── Message helper ────────────────────────────────────────────────────

    def _update_message(self) -> None:
        if self.game_over:
            return
        name = "Attackers" if self.turn == ATTACKER else "Defenders"
        rep = self.repetition_count()
        self.message = f"{name}' turn"
        if rep >= 2:
            self.message += f"  [position seen {rep}×  — vary play!]"

    # ── Movement ──────────────────────────────────────────────────────────

    def get_legal_moves(self, r: int, c: int) -> list[tuple]:
        piece = self.board[r][c]
        if piece == EMPTY:
            return []
        is_king = piece == KING
        moves: list[tuple] = []
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            while in_bounds(nr, nc):
                if self.board[nr][nc] != EMPTY:
                    break
                if is_restricted(nr, nc) and not is_king:
                    if (nr, nc) == THRONE:
                        # may pass through the empty throne, but not land
                        nr += dr
                        nc += dc
                        continue
                    else:
                        break          # corners: can't land or pass
                # Check repetition: would this move cause a 3rd repetition?
                moves.append((nr, nc))
                nr += dr
                nc += dc
        return moves

    def has_legal_move(self, side: int) -> bool:
        for r in range(N):
            for c in range(N):
                p = self.board[r][c]
                if p == EMPTY:
                    continue
                if side == ATTACKER and p != ATTACKER:
                    continue
                if side == DEFENDER and p not in (DEFENDER, KING):
                    continue
                if self.get_legal_moves(r, c):
                    return True
        return False

    # ── Hostile / captor logic ────────────────────────────────────────────

    def _is_hostile_to(self, r: int, c: int, target_side: int) -> bool:
        """Is the *empty* restricted square (r,c) hostile to target_side?"""
        if not is_restricted(r, c):
            return False
        if is_corner(r, c):
            return True                    # hostile to both sides
        # Throne
        if (r, c) == THRONE:
            if target_side == 0:           # attacker
                return True                # always hostile
            return self.board[5][5] == EMPTY   # hostile to defenders only when empty
        return False

    def _is_captor(self, r: int, c: int, mover_side: int, target_side: int) -> bool:
        """Does (r,c) act as the far jaw of a sandwich for *mover_side*?"""
        if not in_bounds(r, c):
            return False
        p = self.board[r][c]
        if p != EMPTY:
            return side_of(p) == mover_side
        return self._is_hostile_to(r, c, target_side)

    # ── Standard (custodial) captures ─────────────────────────────────────

    def _standard_captures(self, mr: int, mc: int,
                           ms: int, es: int) -> list[tuple]:
        caps: list[tuple] = []
        for dr, dc in DIRS:
            ar, ac = mr + dr, mc + dc
            if not in_bounds(ar, ac):
                continue
            adj = self.board[ar][ac]
            if adj == EMPTY or adj == KING:
                continue                              # king handled separately
            if side_of(adj) != es:
                continue
            br, bc = ar + dr, ac + dc
            if self._is_captor(br, bc, ms, es):
                caps.append((ar, ac))
        return caps

    # ── Shieldwall captures ───────────────────────────────────────────────

    def _shieldwall_captures(self, mr: int, mc: int,
                             ms: int, es: int) -> list[tuple]:
        caps: list[tuple] = []
        #          is_row?, fixed, inward_dr, inward_dc
        edges = [
            (True,  0,   1,  0),   # bottom edge row 0, inward = +row
            (True,  10, -1,  0),   # top edge row 10
            (False, 0,   0,  1),   # left edge col 0, inward = +col
            (False, 10,  0, -1),   # right edge col 10
        ]
        for is_row, fixed, idr, idc in edges:
            # Collect cells along this edge
            cells: list[tuple] = []
            for v in range(N):
                rc = (fixed, v) if is_row else (v, fixed)
                cells.append((*rc, self.board[rc[0]][rc[1]]))

            # Find contiguous enemy groups of length >= 2
            groups: list[list[tuple]] = []
            cur: list[tuple] = []
            for r, c, p in cells:
                if p != EMPTY and side_of(p) == es:
                    cur.append((r, c, p))
                else:
                    if len(cur) >= 2:
                        groups.append(cur)
                    cur = []
            if len(cur) >= 2:
                groups.append(cur)

            for grp in groups:
                fr, fc, _ = grp[0]
                lr, lc, _ = grp[-1]
                # Bracket positions (one step before / after along edge)
                if is_row:
                    before = (fr, fc - 1)
                    after  = (lr, lc + 1)
                else:
                    before = (fr - 1, fc)
                    after  = (lr + 1, lc)

                def _bracket_ok(pos: tuple) -> bool:
                    br, bc = pos
                    if not in_bounds(br, bc):
                        return False
                    if is_corner(br, bc):
                        return True          # corner substitutes
                    bp = self.board[br][bc]
                    return bp != EMPTY and side_of(bp) == ms

                if not (_bracket_ok(before) and _bracket_ok(after)):
                    continue

                # Every piece in the row must be fronted by a mover-side piece
                fronted = True
                for r, c, _ in grp:
                    ir, ic = r + idr, c + idc
                    if not in_bounds(ir, ic):
                        fronted = False
                        break
                    ip = self.board[ir][ic]
                    if ip == EMPTY or side_of(ip) != ms:
                        fronted = False
                        break
                if not fronted:
                    continue

                # The moving piece must be one of the brackets or fronters
                involved: set[tuple] = set()
                if in_bounds(*before) and not is_corner(*before):
                    involved.add(before)
                if in_bounds(*after) and not is_corner(*after):
                    involved.add(after)
                for r, c, _ in grp:
                    involved.add((r + idr, c + idc))
                if (mr, mc) not in involved:
                    continue

                for r, c, p in grp:
                    if p != KING:
                        caps.append((r, c))
        return caps

    # ── King capture ──────────────────────────────────────────────────────

    def _check_king_captured(self) -> bool:
        """Check positionally whether the king is captured right now."""
        kr, kc = self._find_king()
        if kr is None:
            return False
        if is_edge(kr, kc):
            return False                       # immune on edge

        adj_throne = (kr, kc) != THRONE and (abs(kr - 5) + abs(kc - 5) == 1)

        for dr, dc in DIRS:
            nr, nc = kr + dr, kc + dc
            if adj_throne and (nr, nc) == THRONE:
                continue                       # throne counts as surrounding
            if not in_bounds(nr, nc) or self.board[nr][nc] != ATTACKER:
                return False
        return True

    def _find_king(self) -> tuple:
        for r in range(N):
            for c in range(N):
                if self.board[r][c] == KING:
                    return r, c
        return None, None

    # ── Encirclement check ────────────────────────────────────────────────

    def _check_encirclement(self) -> bool:
        kr, kc = self._find_king()
        if kr is None:
            return False
        visited: set[tuple] = set()
        queue: deque[tuple] = deque()
        queue.append((kr, kc))
        visited.add((kr, kc))
        while queue:
            r, c = queue.popleft()
            if is_edge(r, c):
                return False                   # path to edge exists
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if not in_bounds(nr, nc) or (nr, nc) in visited:
                    continue
                p = self.board[nr][nc]
                if p == EMPTY or side_of(p) == 1:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
        return True

    # ── Execute a full move ───────────────────────────────────────────────

    def make_move(self, fr: int, fc: int, tr: int, tc: int) -> bool:
        if self.game_over:
            return False
        piece = self.board[fr][fc]
        ms = side_of(piece)
        es = 1 - ms

        # Move the piece
        self.board[fr][fc] = EMPTY
        self.board[tr][tc] = piece
        self.last_move = ((fr, fc), (tr, tc))

        # ── Corner escape ────────────────────────────────────────────────
        if piece == KING and is_corner(tr, tc):
            self.game_over = True
            self.winner = DEFENDER
            self.message = (f"Defenders win!  King escaped to "
                            f"{coord_label(tr, tc)}!")
            return True

        # ── Process captures ─────────────────────────────────────────────
        caps = self._standard_captures(tr, tc, ms, es)
        sw = self._shieldwall_captures(tr, tc, ms, es)
        seen: set[tuple] = set(caps)
        for pos in sw:
            if pos not in seen:
                caps.append(pos)
                seen.add(pos)
        for r, c in caps:
            self.board[r][c] = EMPTY
        self.captured_last = caps

        # ── King capture (only after attacker move) ──────────────────────
        if ms == 0 and self._check_king_captured():
            self.game_over = True
            self.winner = ATTACKER
            self.message = "Attackers win!  King is captured!"
            return True

        # ── Encirclement (only after attacker move) ──────────────────────
        if ms == 0 and self._check_encirclement():
            self.game_over = True
            self.winner = ATTACKER
            self.message = "Attackers win!  Defenders are encircled!"
            return True

        # ── Switch turn ──────────────────────────────────────────────────
        self.turn = DEFENDER if self.turn == ATTACKER else ATTACKER
        self._record()

        # ── No-move loss ─────────────────────────────────────────────────
        if not self.has_legal_move(self.turn):
            self.game_over = True
            self.winner = ATTACKER if self.turn == DEFENDER else DEFENDER
            loser = "Defenders" if self.turn == DEFENDER else "Attackers"
            self.message = (f"{loser} have no legal moves — "
                            f"{'Attackers' if self.winner == ATTACKER else 'Defenders'} win!")
            return True

        # ── Perpetual repetition ─────────────────────────────────────────
        if self.repetition_count() >= 3:
            self.game_over = True
            self.winner = ATTACKER
            self.message = ("Position repeated 3 times — "
                            "Defenders lose by perpetual repetition!")
            return True

        self._update_message()
        return True

    # ── Click helpers ─────────────────────────────────────────────────────

    def click_to_cell(self, mx: int, my: int) -> tuple | None:
        bx = mx - LABEL_M
        by = my - TOP_M
        if bx < 0 or by < 0 or bx >= BOARD_PX or by >= BOARD_PX:
            return None
        c = bx // CELL
        r = (N - 1) - (by // CELL)
        if not in_bounds(r, c):
            return None
        return r, c

    def piece_counts(self) -> tuple:
        atk = def_ = 0
        for r in range(N):
            for c in range(N):
                p = self.board[r][c]
                if p == ATTACKER:
                    atk += 1
                elif p in (DEFENDER, KING):
                    def_ += 1
        return atk, def_


# ═══════════════════════════════════════════════════════════════════════════════
# RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.sfont = pygame.font.SysFont("Arial", 14)
        self.bfont = pygame.font.SysFont("Arial", 26, bold=True)

    # ── Coordinate conversion ─────────────────────────────────────────────

    @staticmethod
    def cell_xy(r: int, c: int) -> tuple[int, int]:
        """Top-left pixel of board cell (r, c)."""
        return LABEL_M + c * CELL, TOP_M + (N - 1 - r) * CELL

    # ── Main draw ─────────────────────────────────────────────────────────

    def draw(self, game: Game) -> None:
        self.screen.fill(C_BG)
        self._draw_board()
        self._draw_highlights(game)
        self._draw_pieces(game)
        self._draw_labels()
        self._draw_panel(game)
        pygame.display.flip()

    # ── Board grid ────────────────────────────────────────────────────────

    def _draw_board(self) -> None:
        for r in range(N):
            for c in range(N):
                x, y = self.cell_xy(r, c)
                if is_corner(r, c):
                    col = C_CORNER
                elif (r, c) == THRONE:
                    col = C_THRONE
                elif (r + c) % 2 == 0:
                    col = C_CELL_A
                else:
                    col = C_CELL_B
                pygame.draw.rect(self.screen, col, (x, y, CELL, CELL))
                pygame.draw.rect(self.screen, C_GRID, (x, y, CELL, CELL), 1)

        # Marks on restricted squares
        for r, c in RESTRICTED:
            cx, cy = self.cell_xy(r, c)
            cx += CELL // 2
            cy += CELL // 2
            if is_corner(r, c):
                d = CELL // 4
                pygame.draw.line(self.screen, C_MARK,
                                 (cx - d, cy - d), (cx + d, cy + d), 2)
                pygame.draw.line(self.screen, C_MARK,
                                 (cx - d, cy + d), (cx + d, cy - d), 2)
            else:
                d = CELL // 5
                pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
                pygame.draw.polygon(self.screen, C_MARK, pts, 2)

    # ── Highlights ────────────────────────────────────────────────────────

    def _draw_highlights(self, game: Game) -> None:
        # Last move (from / to)
        if game.last_move:
            for pos in game.last_move:
                x, y = self.cell_xy(*pos)
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill(C_LAST)
                self.screen.blit(s, (x, y))

        # Selected piece
        if game.selected:
            x, y = self.cell_xy(*game.selected)
            s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            s.fill(C_SEL_FILL)
            self.screen.blit(s, (x, y))
            pygame.draw.rect(self.screen, C_SEL_BORDER,
                             (x, y, CELL, CELL), 3)

        # Legal-move dots
        for pos in game.legal_moves:
            cx, cy = self.cell_xy(*pos)
            cx += CELL // 2
            cy += CELL // 2
            pygame.draw.circle(self.screen, C_MOVE_DOT, (cx, cy), 9)
            pygame.draw.circle(self.screen, C_MOVE_RING, (cx, cy), 9, 2)

        # Captured squares flash ring
        for pos in game.captured_last:
            cx, cy = self.cell_xy(*pos)
            cx += CELL // 2
            cy += CELL // 2
            pygame.draw.circle(self.screen, C_CAPTURE_RING, (cx, cy),
                               CELL // 2 - 3, 3)

    # ── Pieces ────────────────────────────────────────────────────────────

    def _draw_pieces(self, game: Game) -> None:
        rad = CELL // 2 - 7
        for r in range(N):
            for c in range(N):
                p = game.board[r][c]
                if p == EMPTY:
                    continue
                cx, cy = self.cell_xy(r, c)
                cx += CELL // 2
                cy += CELL // 2

                if p == ATTACKER:
                    pygame.draw.circle(self.screen, C_ATK, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_ATK_RIM, (cx, cy), rad, 2)
                    # small inner dot for texture
                    pygame.draw.circle(self.screen, (90, 50, 38), (cx, cy), 5)

                elif p == DEFENDER:
                    pygame.draw.circle(self.screen, C_DEF, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_DEF_RIM, (cx, cy), rad, 2)
                    pygame.draw.circle(self.screen, (210, 205, 192),
                                       (cx, cy), 5)

                elif p == KING:
                    pygame.draw.circle(self.screen, C_KING_FILL, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_KING_RIM, (cx, cy), rad, 3)
                    # Crown: small cross + dots
                    d = rad // 2
                    pygame.draw.line(self.screen, C_KING_MARK,
                                     (cx - d, cy), (cx + d, cy), 3)
                    pygame.draw.line(self.screen, C_KING_MARK,
                                     (cx, cy - d), (cx, cy + d), 3)
                    td = d + 2
                    for dx, dy in ((-td, 0), (td, 0), (0, -td), (0, td)):
                        pygame.draw.circle(self.screen, C_KING_MARK,
                                           (cx + dx, cy + dy), 3)

    # ── Coordinate labels ─────────────────────────────────────────────────

    def _draw_labels(self) -> None:
        # Columns (below board)
        for c in range(N):
            x = LABEL_M + c * CELL + CELL // 2
            y = TOP_M + BOARD_PX + 14
            txt = self.font.render(COL_LABELS[c], True, C_LABEL)
            self.screen.blit(txt, txt.get_rect(center=(x, y)))
        # Rows (left of board)
        for r in range(N):
            x = LABEL_M // 2
            y = TOP_M + (N - 1 - r) * CELL + CELL // 2
            txt = self.font.render(str(r + 1), True, C_LABEL)
            self.screen.blit(txt, txt.get_rect(center=(x, y)))

    # ── Status panel ──────────────────────────────────────────────────────

    def _draw_panel(self, game: Game) -> None:
        py = TOP_M + BOARD_PX + LABEL_M
        pygame.draw.rect(self.screen, C_PANEL, (0, py, WIN_W, PANEL_H))

        # Turn / result message
        txt = self.bfont.render(game.message, True, C_TEXT)
        self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, py + 22)))

        # Piece counts
        atk, dfn = game.piece_counts()
        lbl = self.sfont.render(f"Attackers: {atk}", True, C_ACCENT_ATK)
        self.screen.blit(lbl, (12, py + 44))
        lbl2 = self.sfont.render(f"Defenders: {dfn}", True, C_ACCENT_DEF)
        self.screen.blit(lbl2, (130, py + 44))

        # Controls hint
        hint = self.sfont.render("R Restart   U Undo   Q Quit", True, C_LABEL)
        self.screen.blit(hint, (WIN_W - hint.get_width() - 12, py + 44))

        # If game over, overlay banner
        if game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self.screen.blit(overlay, (0, 0))
            banner_h = 80
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, C_PANEL,
                             (0, banner_y, WIN_W, banner_h))
            pygame.draw.line(self.screen,
                             C_ACCENT_ATK if game.winner == ATTACKER
                             else C_ACCENT_DEF,
                             (0, banner_y), (WIN_W, banner_y), 3)
            pygame.draw.line(self.screen,
                             C_ACCENT_ATK if game.winner == ATTACKER
                             else C_ACCENT_DEF,
                             (0, banner_y + banner_h),
                             (WIN_W, banner_y + banner_h), 3)
            big = self.bfont.render(game.message, True, C_TEXT)
            self.screen.blit(big, big.get_rect(center=(WIN_W // 2,
                                                        banner_y + 28)))
            sub = self.sfont.render("Press R to play again", True, C_LABEL)
            self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2,
                                                        banner_y + 56)))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Copenhagen Hnefatafl  11×11")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = Game()
    undo_stack: list[Game] = []

    running = True
    while running:
        renderer.draw(game)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_r:
                    game = Game()
                    undo_stack.clear()
                elif event.key == pygame.K_u and undo_stack:
                    game = undo_stack.pop()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                cell = game.click_to_cell(*event.pos)
                if cell is None:
                    game.selected = None
                    game.legal_moves = []
                    continue

                r, c = cell

                # If a legal-move square was clicked, execute the move
                if game.selected and (r, c) in game.legal_moves:
                    undo_stack.append(copy.deepcopy(game))
                    fr, fc = game.selected
                    game.selected = None
                    game.legal_moves = []
                    game.make_move(fr, fc, r, c)
                else:
                    # Try selecting a piece
                    p = game.board[r][c]
                    own = False
                    if game.turn == ATTACKER and p == ATTACKER:
                        own = True
                    elif game.turn == DEFENDER and p in (DEFENDER, KING):
                        own = True
                    if own:
                        moves = game.get_legal_moves(r, c)
                        if moves:
                            game.selected = (r, c)
                            game.legal_moves = moves
                        else:
                            game.selected = None
                            game.legal_moves = []
                    else:
                        game.selected = None
                        game.legal_moves = []

        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()