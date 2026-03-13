"""
Bashni (Column Draughts) — 12×12 Board
Complete implementation for local human-vs-human play.

Controls:
  Left Click — Select a piece / choose a move or capture destination
  R          — Reset the game
  U          — Undo last full move
  Q / Esc    — Quit
  Hover      — Inspect column composition in the right panel

Rules implemented:
  • 12×12 board, dark squares only. 30 pieces per side.
  • Columns: ordered stacks. The top piece (commander) controls the column.
  • Captured commanders go to the BOTTOM of the capturing column (no piece leaves play).
  • Man: moves diag-forward 1; captures diag any direction by jumping.
  • King (flying): moves/captures any distance diagonally.
  • Capture is mandatory; multi-jump sequences must be completed.
  • King must choose landing that allows further capture if available.
  • No immediate direction reversal during a multi-jump.
  • Promotion on far row is immediate, even mid-sequence (gains flying powers).
  • Win: opponent has no legal move. Draw: threefold repetition or 25-move quiet rule.
"""

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
import sys
from copy import deepcopy
from collections import defaultdict

# ═══════════════════════════ Constants ═══════════════════════════

BOARD_N = 12
SQ = 66                         # square pixel size
MARGIN = 32                     # coordinate label gutter
PANEL_W = 210                   # right-side column inspector width
INFO_H = 48                     # bottom info bar height

BOARD_PX = BOARD_N * SQ
WIN_W = MARGIN + BOARD_PX + MARGIN + PANEL_W
WIN_H = MARGIN + BOARD_PX + INFO_H

FPS = 60

# Piece identifiers
W, B = "W", "B"
MAN, KING = "M", "K"

DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

# ── Colour palette ──
C_BG          = (36, 33, 30)
C_DARK_SQ     = (160, 108, 60)
C_LIGHT_SQ    = (230, 210, 172)
C_WHITE_TOP   = (242, 236, 220)    # white piece face
C_WHITE_SIDE  = (215, 208, 192)    # white piece rim/edge
C_WHITE_BD    = (165, 155, 140)    # white piece outline
C_BLACK_TOP   = (50, 50, 50)      # black piece face
C_BLACK_SIDE  = (32, 32, 32)      # black piece rim
C_BLACK_BD    = (95, 95, 95)      # black piece outline
C_CROWN_W     = (175, 138, 28)
C_CROWN_B     = (220, 182, 52)
C_SEL         = (40, 130, 240)
C_MOVE        = (50, 195, 50)
C_CAPTURE     = (220, 60, 40)
C_LASTMOVE    = (200, 190, 50)
C_TEXT        = (218, 215, 208)
C_TEXT_DIM    = (140, 135, 125)
C_COORD       = (175, 165, 150)
C_INFO_BG     = (46, 42, 38)
C_PANEL_BG    = (42, 38, 34)
C_PANEL_BD    = (70, 65, 58)
C_SHADOW      = (22, 20, 18)

COL_LABELS = "abcdefghijkl"

# Disc geometry
DISC_RX = int(SQ * 0.38)           # horizontal radius of disc ellipse
DISC_RY = 6                        # vertical radius of disc ellipse (3D "thickness")
DISC_STEP_MAX = DISC_RY * 2 + 2    # max vertical step between disc centres (loose stack)
DISC_STEP_MIN = 2                   # minimum step for very tall columns

# ═══════════════════════════ Helpers ═════════════════════════════

def in_bounds(r, c):
    return 0 <= r < BOARD_N and 0 <= c < BOARD_N

def is_dark(r, c):
    return (r + c) % 2 == 0

def opponent(player):
    return B if player == W else W

def promo_row(player):
    return 11 if player == W else 0

def board_key(board, turn):
    parts = []
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col = board[r][c]
            if col:
                parts.append((r, c, tuple(tuple(p) for p in col)))
    return (tuple(parts), turn)

# ═══════════════════════════ Board Init ══════════════════════════

def make_board():
    board = [[None] * BOARD_N for _ in range(BOARD_N)]
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if not is_dark(r, c):
                continue
            if r < 5:
                board[r][c] = [[W, MAN]]
            elif r > 6:
                board[r][c] = [[B, MAN]]
    return board

# ═══════════════════════════ Move / Capture Logic ════════════════

def get_simple_moves(board, r, c, player):
    col = board[r][c]
    if not col or col[-1][0] != player:
        return []
    is_king = col[-1][1] == KING
    moves = []
    if is_king:
        for dr, dc in DIRS:
            d = 1
            while True:
                nr, nc = r + dr * d, c + dc * d
                if not in_bounds(nr, nc):
                    break
                if board[nr][nc] is not None:
                    break
                moves.append((nr, nc))
                d += 1
    else:
        fwd = 1 if player == W else -1
        for dc in (-1, 1):
            nr, nc = r + fwd, c + dc
            if in_bounds(nr, nc) and board[nr][nc] is None:
                moves.append((nr, nc))
    return moves


def _raw_jumps(board, r, c, player, last_dir=None):
    col = board[r][c]
    if not col or col[-1][0] != player:
        return []
    is_king = col[-1][1] == KING
    results = []
    for dr, dc in DIRS:
        if last_dir and (dr, dc) == (-last_dir[0], -last_dir[1]):
            continue
        if is_king:
            d = 1
            tgt = None
            while True:
                tr, tc = r + dr * d, c + dc * d
                if not in_bounds(tr, tc):
                    break
                cell = board[tr][tc]
                if cell is not None:
                    if cell[-1][0] != player:
                        tgt = (tr, tc)
                    break
                d += 1
            if not tgt:
                continue
            tr, tc = tgt
            ld = 1
            while True:
                lr, lc = tr + dr * ld, tc + dc * ld
                if not in_bounds(lr, lc):
                    break
                if board[lr][lc] is not None:
                    break
                results.append((lr, lc, tr, tc, (dr, dc)))
                ld += 1
        else:
            tr, tc = r + dr, c + dc
            lr, lc = r + 2 * dr, c + 2 * dc
            if (in_bounds(tr, tc) and in_bounds(lr, lc)
                    and board[tr][tc] is not None
                    and board[tr][tc][-1][0] != player
                    and board[lr][lc] is None):
                results.append((lr, lc, tr, tc, (dr, dc)))
    return results


def _has_raw_jump(board, r, c, player, last_dir=None):
    col = board[r][c]
    if not col or col[-1][0] != player:
        return False
    is_king = col[-1][1] == KING
    for dr, dc in DIRS:
        if last_dir and (dr, dc) == (-last_dir[0], -last_dir[1]):
            continue
        if is_king:
            d = 1
            tgt = None
            while True:
                tr, tc = r + dr * d, c + dc * d
                if not in_bounds(tr, tc):
                    break
                cell = board[tr][tc]
                if cell is not None:
                    if cell[-1][0] != player:
                        tgt = (tr, tc)
                    break
                d += 1
            if not tgt:
                continue
            tr, tc = tgt
            lr, lc = tr + dr, tc + dc
            if in_bounds(lr, lc) and board[lr][lc] is None:
                return True
        else:
            tr, tc = r + dr, c + dc
            lr, lc = r + 2 * dr, c + 2 * dc
            if (in_bounds(tr, tc) and in_bounds(lr, lc)
                    and board[tr][tc] is not None
                    and board[tr][tc][-1][0] != player
                    and board[lr][lc] is None):
                return True
    return False


def _sim_jump(board, fr, fc, lr, lc, tr, tc, player):
    b = deepcopy(board)
    exec_jump(b, fr, fc, lr, lc, tr, tc, player)
    return b


def get_jumps(board, r, c, player, last_dir=None):
    raw = _raw_jumps(board, r, c, player, last_dir)
    if not raw:
        return []
    col = board[r][c]
    is_king = col[-1][1] == KING
    if not is_king:
        return raw

    groups = defaultdict(list)
    for item in raw:
        _lr, _lc, tr, tc, d = item
        groups[(tr, tc, d)].append(item)

    filtered = []
    for _key, items in groups.items():
        continuing = []
        non_continuing = []
        for item in items:
            lr, lc, tr, tc, d = item
            sim = _sim_jump(board, r, c, lr, lc, tr, tc, player)
            if _has_raw_jump(sim, lr, lc, player, d):
                continuing.append(item)
            else:
                non_continuing.append(item)
        filtered.extend(continuing if continuing else non_continuing)
    return filtered


def any_capture(board, player):
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            if _has_raw_jump(board, r, c, player):
                return True
    return False


def has_legal_move(board, player):
    cap = any_capture(board, player)
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col = board[r][c]
            if not col or col[-1][0] != player:
                continue
            if cap:
                if get_jumps(board, r, c, player):
                    return True
            else:
                if get_simple_moves(board, r, c, player):
                    return True
    return False

# ═══════════════════════════ Move Execution ══════════════════════

def exec_move(board, fr, fc, tr, tc, player):
    col = board[fr][fc]
    was_man = col[-1][1] == MAN
    board[tr][tc] = col
    board[fr][fc] = None
    if tr == promo_row(player) and col[-1][1] == MAN:
        col[-1] = [col[-1][0], KING]
    return was_man


def exec_jump(board, fr, fc, lr, lc, tr, tc, player):
    cap_col = board[fr][fc]
    tgt_col = board[tr][tc]
    captured = tgt_col.pop()
    cap_col.insert(0, captured)
    board[lr][lc] = cap_col
    board[fr][fc] = None
    if not tgt_col:
        board[tr][tc] = None
    if lr == promo_row(player) and cap_col[-1][1] == MAN:
        cap_col[-1] = [cap_col[-1][0], KING]

# ═══════════════════════════ Game State ══════════════════════════

class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        self.board = make_board()
        self.turn = W
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self.game_over = False
        self.winner = None
        self.status = "White's turn"
        self.pos_history = defaultdict(int)
        self.quiet_half = 0
        self.last_from = None
        self.last_to = None
        self.undo_stack = []
        self.hover_pos = None       # board (r, c) under mouse
        self._record_position()

    def _record_position(self):
        key = board_key(self.board, self.turn)
        self.pos_history[key] += 1

    def _save_undo(self):
        self.undo_stack.append((
            deepcopy(self.board), self.turn, self.quiet_half,
            dict(self.pos_history), self.last_from, self.last_to,
        ))

    def undo(self):
        if not self.undo_stack or self.game_over:
            return
        snap = self.undo_stack.pop()
        self.board, self.turn, self.quiet_half, hist, self.last_from, self.last_to = snap
        self.pos_history = defaultdict(int, hist)
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self.game_over = False
        self.winner = None
        self.status = f"{'White' if self.turn == W else 'Black'}'s turn"

    def click(self, r, c):
        if self.game_over:
            return
        if not is_dark(r, c):
            return

        if self.jumping:
            self._handle_jump_click(r, c)
            return

        if self.selected is not None:
            dest = self._find_dest(r, c)
            if dest is not None:
                self._execute_dest(dest)
                return

        col = self.board[r][c]
        if col and col[-1][0] == self.turn:
            must_cap = any_capture(self.board, self.turn)
            if must_cap:
                jumps = get_jumps(self.board, r, c, self.turn)
                if jumps:
                    self.selected = (r, c)
                    self.valid_dests = jumps
                    self.is_capture_mode = True
                else:
                    self.selected = None
                    self.valid_dests = []
                    self.is_capture_mode = False
            else:
                moves = get_simple_moves(self.board, r, c, self.turn)
                if moves:
                    self.selected = (r, c)
                    self.valid_dests = [(mr, mc) for mr, mc in moves]
                    self.is_capture_mode = False
                else:
                    self.selected = None
                    self.valid_dests = []
        else:
            self.selected = None
            self.valid_dests = []
            self.is_capture_mode = False

    def _find_dest(self, r, c):
        for d in self.valid_dests:
            if d[0] == r and d[1] == c:
                return d
        return None

    def _execute_dest(self, dest):
        sr, sc = self.selected
        if self.is_capture_mode:
            lr, lc, tr, tc, d = dest
            self._save_undo()
            exec_jump(self.board, sr, sc, lr, lc, tr, tc, self.turn)
            self.last_from = (sr, sc)
            self.last_to = (lr, lc)
            self.quiet_half = 0
            further = get_jumps(self.board, lr, lc, self.turn, last_dir=d)
            if further:
                self.jumping = (lr, lc)
                self.jump_dir = d
                self.selected = (lr, lc)
                self.valid_dests = further
                self.is_capture_mode = True
            else:
                self._end_turn()
        else:
            lr, lc = dest
            self._save_undo()
            was_man = exec_move(self.board, sr, sc, lr, lc, self.turn)
            self.last_from = (sr, sc)
            self.last_to = (lr, lc)
            self.quiet_half = 0 if was_man else self.quiet_half + 1
            self._end_turn()

    def _handle_jump_click(self, r, c):
        dest = self._find_dest(r, c)
        if dest is None:
            return
        lr, lc, tr, tc, d = dest
        jr, jc = self.jumping
        exec_jump(self.board, jr, jc, lr, lc, tr, tc, self.turn)
        self.last_to = (lr, lc)
        further = get_jumps(self.board, lr, lc, self.turn, last_dir=d)
        if further:
            self.jumping = (lr, lc)
            self.jump_dir = d
            self.selected = (lr, lc)
            self.valid_dests = further
        else:
            self._end_turn()

    def _end_turn(self):
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self.turn = opponent(self.turn)
        self._record_position()

        key = board_key(self.board, self.turn)
        if self.pos_history[key] >= 3:
            self.game_over = True
            self.winner = None
            self.status = "Draw \u2014 threefold repetition"
            return
        if self.quiet_half >= 50:
            self.game_over = True
            self.winner = None
            self.status = "Draw \u2014 25-move rule"
            return
        if not has_legal_move(self.board, self.turn):
            self.game_over = True
            self.winner = opponent(self.turn)
            self.status = f"{'White' if self.winner == W else 'Black'} wins!"
            return

        name = "White" if self.turn == W else "Black"
        self.status = f"{name}'s turn"
        if any_capture(self.board, self.turn):
            self.status += "  (must capture)"

# ═══════════════════════════ Rendering ═══════════════════════════

def board_to_px(r, c):
    """Board (row, col) -> pixel top-left. Row 0 at bottom of screen."""
    return MARGIN + c * SQ, MARGIN + (BOARD_N - 1 - r) * SQ

def px_to_board(mx, my):
    c = (mx - MARGIN) // SQ
    r = (BOARD_N - 1) - (my - MARGIN) // SQ
    if 0 <= r < BOARD_N and 0 <= c < BOARD_N:
        return r, c
    return None

def _alpha_rect(surf, rgb, alpha, rect):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    s.fill((*rgb, alpha))
    surf.blit(s, (rect[0], rect[1]))

def _alpha_circle(surf, rgb, alpha, center, radius):
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(s, (*rgb, alpha), (radius, radius), radius)
    surf.blit(s, (center[0] - radius, center[1] - radius))


# ── 3D stacked-disc column drawing ──

def _disc_colors(piece):
    """Return (top_fill, side_fill, border) for a piece [color, rank]."""
    if piece[0] == W:
        return C_WHITE_TOP, C_WHITE_SIDE, C_WHITE_BD
    else:
        return C_BLACK_TOP, C_BLACK_SIDE, C_BLACK_BD


def draw_column(surf, col_data, sq_x, sq_y, fonts):
    """Render a column as 3D-stacked discs inside its square.

    Each piece is drawn as a short cylinder:
      • a coloured side band (rectangle + bottom-edge ellipse)
      • a top-face ellipse
    Pieces are painted bottom-to-top so upper discs naturally
    occlude the lower ones — exactly like a physical stack.
    """
    n = len(col_data)
    cx = sq_x + SQ // 2
    rx = DISC_RX
    ry = DISC_RY              # ellipse vertical half-axis for face

    pad = 3
    avail = SQ - 2 * pad      # usable vertical pixels inside the square

    # ── Compute step (vertical distance between consecutive face-centres) ──
    if n == 1:
        step = 0.0
    else:
        step = min(float(DISC_STEP_MAX), (avail - ry * 2) / (n - 1))
        step = max(step, float(DISC_STEP_MIN))

    # Total visual height from topmost face-centre to bottommost face-centre
    stack_span = step * max(0, n - 1)

    # Position the stack: bottom piece's face near the square bottom
    bot_face_cy = sq_y + SQ - pad - ry
    top_face_cy = bot_face_cy - stack_span

    # If top piece pokes above the square, shift everything down (shrink step)
    if top_face_cy - ry < sq_y + pad:
        top_face_cy = sq_y + pad + ry
        bot_face_cy = top_face_cy + stack_span
        if bot_face_cy + ry > sq_y + SQ - pad:
            # Recalculate step to exactly fit
            step = (avail - ry * 2) / max(1, n - 1)
            step = max(step, 1.0)
            bot_face_cy = sq_y + SQ - pad - ry
            top_face_cy = bot_face_cy - step * (n - 1)

    # Disc depth (how tall the visible side-band is for each piece)
    if n == 1:
        depth = 8                      # single piece — comfy thickness
    else:
        depth = max(int(step), 2)
        depth = min(depth, 10)

    # ── Paint bottom-to-top (painter's order) ──
    for i in range(n):
        piece = col_data[i]            # index 0 = bottom of column
        face_cy = int(bot_face_cy - i * step)
        top_fill, side_fill, border = _disc_colors(piece)

        # Visible side band (below the face)
        side_top_y = face_cy + 1       # just below face centre
        side_bot_y = min(face_cy + depth, sq_y + SQ - 1)
        if side_bot_y > side_top_y:
            # Filled rectangle for the cylindrical side
            pygame.draw.rect(surf, side_fill,
                             (cx - rx, side_top_y, rx * 2, side_bot_y - side_top_y))
            # Bottom edge ellipse (gives the disc a rounded bottom)
            bot_ell = pygame.Rect(cx - rx, side_bot_y - ry, rx * 2, ry * 2)
            pygame.draw.ellipse(surf, side_fill, bot_ell)
            pygame.draw.ellipse(surf, border, bot_ell, 1)
            # Vertical side-edge lines
            pygame.draw.line(surf, border,
                             (cx - rx, side_top_y), (cx - rx, side_bot_y), 1)
            pygame.draw.line(surf, border,
                             (cx + rx - 1, side_top_y), (cx + rx - 1, side_bot_y), 1)

        # Top face ellipse
        face_rect = pygame.Rect(cx - rx, face_cy - ry, rx * 2, ry * 2)
        pygame.draw.ellipse(surf, top_fill, face_rect)
        pygame.draw.ellipse(surf, border, face_rect, 1)

        # King crown on commander (topmost piece)
        if i == n - 1 and piece[1] == KING:
            crown_c = C_CROWN_W if piece[0] == W else C_CROWN_B
            _draw_crown(surf, cx, face_cy, crown_c, rx)

    # ── Height badge ──
    if n > 1:
        badge = fonts["badge"].render(str(n), True, (255, 70, 60))
        surf.blit(badge, (sq_x + SQ - badge.get_width() - 1, sq_y + 1))


def _draw_crown(surf, cx, cy, color, rx):
    """Small crown symbol on a king's face."""
    s = rx * 0.42
    pts = [
        (cx - s,       cy + s * 0.38),
        (cx - s,       cy - s * 0.22),
        (cx - s * 0.5, cy + s * 0.12),
        (cx,           cy - s * 0.62),
        (cx + s * 0.5, cy + s * 0.12),
        (cx + s,       cy - s * 0.22),
        (cx + s,       cy + s * 0.38),
    ]
    pts_i = [(int(round(x)), int(round(y))) for x, y in pts]
    pygame.draw.polygon(surf, color, pts_i)
    pygame.draw.polygon(surf, (0, 0, 0), pts_i, 1)


# ── Main draw routine ──

def draw_board(surf, game, fonts):
    surf.fill(C_BG)

    # ── Board squares ──
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            x, y = board_to_px(r, c)
            color = C_DARK_SQ if is_dark(r, c) else C_LIGHT_SQ
            pygame.draw.rect(surf, color, (x, y, SQ, SQ))

    # ── Last-move highlight ──
    for pos in (game.last_from, game.last_to):
        if pos:
            x, y = board_to_px(*pos)
            _alpha_rect(surf, C_LASTMOVE, 42, (x, y, SQ, SQ))

    # ── Selected square ──
    if game.selected:
        x, y = board_to_px(*game.selected)
        _alpha_rect(surf, C_SEL, 75, (x, y, SQ, SQ))

    # ── Valid destinations ──
    for d in game.valid_dests:
        dr, dc = d[0], d[1]
        x, y = board_to_px(dr, dc)
        col = C_CAPTURE if game.is_capture_mode else C_MOVE
        _alpha_rect(surf, col, 55, (x, y, SQ, SQ))
        cx, cy = x + SQ // 2, y + SQ // 2
        _alpha_circle(surf, col, 170, (cx, cy), 8)

    # ── Hover highlight ──
    if game.hover_pos:
        hr, hc = game.hover_pos
        if is_dark(hr, hc) and game.board[hr][hc]:
            x, y = board_to_px(hr, hc)
            _alpha_rect(surf, (255, 255, 255), 25, (x, y, SQ, SQ))

    # ── Coordinate labels ──
    fc = fonts["coord"]
    for c in range(BOARD_N):
        xc = MARGIN + c * SQ + SQ // 2
        lbl = fc.render(COL_LABELS[c], True, C_COORD)
        surf.blit(lbl, lbl.get_rect(center=(xc, MARGIN + BOARD_PX + 12)))
        surf.blit(lbl, lbl.get_rect(center=(xc, MARGIN - 12)))
    for r in range(BOARD_N):
        yc = MARGIN + (BOARD_N - 1 - r) * SQ + SQ // 2
        lbl = fc.render(str(r + 1), True, C_COORD)
        surf.blit(lbl, lbl.get_rect(center=(MARGIN - 13, yc)))

    # ── Pieces ──
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col_data = game.board[r][c]
            if col_data:
                draw_column(surf, col_data, *board_to_px(r, c), fonts)

    # ── Board border ──
    bx, by = MARGIN, MARGIN
    pygame.draw.rect(surf, (95, 88, 75), (bx - 2, by - 2, BOARD_PX + 4, BOARD_PX + 4), 2)

    # ── Right-side column inspector panel ──
    draw_panel(surf, game, fonts)

    # ── Bottom info bar ──
    info_y = MARGIN + BOARD_PX
    pygame.draw.rect(surf, C_INFO_BG, (0, info_y, MARGIN + BOARD_PX, INFO_H))

    # Turn indicator disc
    ind_top = C_WHITE_TOP if game.turn == W else C_BLACK_TOP
    ind_bd = C_WHITE_BD if game.turn == W else C_BLACK_BD
    iy = info_y + INFO_H // 2
    pygame.draw.circle(surf, ind_top, (18, iy), 10)
    pygame.draw.circle(surf, ind_bd, (18, iy), 10, 2)

    surf.blit(fonts["status"].render(game.status, True, C_TEXT), (36, info_y + 14))

    hint = fonts["hint"].render("R: Reset   U: Undo   Q: Quit", True, C_TEXT_DIM)
    hint_x = MARGIN + BOARD_PX - hint.get_width() - 8
    surf.blit(hint, (hint_x, info_y + 16))


# ── Column inspector panel ──

def draw_panel(surf, game, fonts):
    """Right-side panel showing hovered/selected column composition."""
    px = MARGIN + BOARD_PX + MARGIN
    py = MARGIN
    pw = PANEL_W - MARGIN
    ph = BOARD_PX

    # Panel background
    pygame.draw.rect(surf, C_PANEL_BG, (px - 4, py, pw + 8, ph))
    pygame.draw.rect(surf, C_PANEL_BD, (px - 4, py, pw + 8, ph), 1)

    # Determine which column to inspect (hover takes priority, then selected)
    inspect_pos = None
    inspect_col = None
    if game.hover_pos:
        hr, hc = game.hover_pos
        if is_dark(hr, hc) and game.board[hr][hc]:
            inspect_pos = game.hover_pos
            inspect_col = game.board[hr][hc]
    if inspect_col is None and game.selected:
        sr, sc = game.selected
        inspect_col = game.board[sr][sc]
        inspect_pos = game.selected

    if inspect_col is None:
        # Show instructions
        msg_lines = [
            "COLUMN INSPECTOR",
            "",
            "Hover over a column",
            "to see its full",
            "composition.",
            "",
            "Each disc shows the",
            "piece's color (W/B)",
            "and rank (man/king).",
            "",
            "Top = Commander",
            "Bottom = Deepest",
            "         prisoner",
        ]
        fy = py + 12
        for i, line in enumerate(msg_lines):
            f = fonts["panel_title"] if i == 0 else fonts["panel"]
            c = C_TEXT if i == 0 else C_TEXT_DIM
            surf.blit(f.render(line, True, c), (px + 4, fy))
            fy += 18 if i == 0 else 16
        return

    # Header
    r, c = inspect_pos
    coord = f"{COL_LABELS[c]}{r + 1}"
    commander = inspect_col[-1]
    owner = "White" if commander[0] == W else "Black"
    rank = "King" if commander[1] == KING else "Man"

    fy = py + 8
    surf.blit(fonts["panel_title"].render(f"Column at {coord}", True, C_TEXT), (px + 4, fy))
    fy += 22
    surf.blit(fonts["panel"].render(f"Owner: {owner} ({rank})", True, C_TEXT_DIM), (px + 4, fy))
    fy += 18
    surf.blit(fonts["panel"].render(f"Height: {len(inspect_col)} piece{'s' if len(inspect_col) > 1 else ''}", True, C_TEXT_DIM), (px + 4, fy))
    fy += 24

    # Draw separator
    pygame.draw.line(surf, C_PANEL_BD, (px, fy), (px + pw, fy), 1)
    fy += 8

    # Piece list — draw from top (commander) to bottom
    disc_w = min(pw - 20, 60)        # panel disc width
    disc_h_face = 5                   # ellipse ry for panel discs
    disc_rx = disc_w // 2
    list_x = px + pw // 2             # centre of disc column

    # How much space per entry
    entry_h = 22
    max_visible = (ph - (fy - py) - 10) // entry_h

    pieces_to_show = list(reversed(inspect_col))  # top-first
    overflow = len(pieces_to_show) > max_visible
    if overflow:
        pieces_to_show = pieces_to_show[:max_visible - 1]

    for idx, piece in enumerate(pieces_to_show):
        top_fill, side_fill, border = _disc_colors(piece)
        dy = fy + idx * entry_h
        disc_cy = dy + entry_h // 2

        # Label
        is_commander = (idx == 0)
        rank_str = "K" if piece[1] == KING else "m"
        color_str = "W" if piece[0] == W else "B"
        pos_label = f"\u25B6 {color_str}-{rank_str}" if is_commander else f"   {color_str}-{rank_str}"

        # Draw mini disc
        mini_rx = disc_rx // 2
        mini_ry = disc_h_face
        disc_x = px + 16
        _r = (disc_x - mini_rx, disc_cy - mini_ry, mini_rx * 2, mini_ry * 2)
        pygame.draw.ellipse(surf, top_fill, _r)
        pygame.draw.ellipse(surf, border, _r, 1)

        # Crown on kings
        if piece[1] == KING:
            crown_c = C_CROWN_W if piece[0] == W else C_CROWN_B
            _draw_crown(surf, disc_x, disc_cy, crown_c, mini_rx)

        # Text label
        label_c = C_TEXT if is_commander else C_TEXT_DIM
        surf.blit(fonts["panel"].render(pos_label, True, label_c), (disc_x + mini_rx + 6, disc_cy - 7))

        # Position number (from top)
        num = fonts["panel_small"].render(str(idx + 1), True, C_TEXT_DIM)
        surf.blit(num, (px + pw - num.get_width() - 2, disc_cy - 6))

    if overflow:
        dy = fy + len(pieces_to_show) * entry_h
        surf.blit(fonts["panel"].render(f"  ... +{len(inspect_col) - len(pieces_to_show)} more", True, C_TEXT_DIM), (px + 4, dy))


# ═══════════════════════════ Main Loop ═══════════════════════════

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bashni \u2014 12\u00d712 Column Draughts")
    clock = pygame.time.Clock()

    family = None
    for name in ("DejaVu Sans", "Segoe UI", "Helvetica", "Arial"):
        if name.lower().replace(" ", "") in [f.lower().replace(" ", "")
                                              for f in pygame.font.get_fonts()]:
            family = name
            break
    fonts = {
        "coord":       pygame.font.SysFont(family, 14, bold=True),
        "status":      pygame.font.SysFont(family, 18, bold=True),
        "hint":        pygame.font.SysFont(family, 13),
        "badge":       pygame.font.SysFont(family, 12, bold=True),
        "panel_title": pygame.font.SysFont(family, 15, bold=True),
        "panel":       pygame.font.SysFont(family, 14),
        "panel_small": pygame.font.SysFont(family, 11),
    }

    game = Game()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_r:
                    game.reset()
                elif event.key == pygame.K_u:
                    game.undo()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = px_to_board(*event.pos)
                if pos:
                    game.click(*pos)
            elif event.type == pygame.MOUSEMOTION:
                game.hover_pos = px_to_board(*event.pos)

        draw_board(screen, game, fonts)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()