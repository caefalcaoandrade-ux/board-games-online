"""
Bashni (Column Draughts) -- Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls:
  Left Click -- Select a piece / choose a move or capture destination
  R          -- Reset the game
  U          -- Undo last full move
  Q / Esc    -- Quit
  Hover      -- Inspect column composition in the right panel
"""

import sys
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
from copy import deepcopy

try:
    from games.bashni_logic import (
        BashniLogic, BOARD_N, W, B, MAN, KING, DIRS,
        PLAYER_TO_COLOR, COLOR_TO_PLAYER,
        in_bounds, is_dark, opponent_color, promo_row, board_key,
    )
except ImportError:
    from bashni_logic import (
        BashniLogic, BOARD_N, W, B, MAN, KING, DIRS,
        PLAYER_TO_COLOR, COLOR_TO_PLAYER,
        in_bounds, is_dark, opponent_color, promo_row, board_key,
    )

# ── Display Constants ────────────────────────────────────────────────────────

SQ = 66                         # square pixel size
MARGIN = 32                     # coordinate label gutter
PANEL_W = 210                   # right-side column inspector width
INFO_H = 48                     # bottom info bar height

BOARD_PX = BOARD_N * SQ
WIN_W = MARGIN + BOARD_PX + MARGIN + PANEL_W
WIN_H = MARGIN + BOARD_PX + INFO_H

FPS = 60

# ── Colour palette ───────────────────────────────────────────────────────────

C_BG          = (36, 33, 30)
C_DARK_SQ     = (160, 108, 60)
C_LIGHT_SQ    = (230, 210, 172)
C_WHITE_TOP   = (242, 236, 220)
C_WHITE_SIDE  = (215, 208, 192)
C_WHITE_BD    = (165, 155, 140)
C_BLACK_TOP   = (50, 50, 50)
C_BLACK_SIDE  = (32, 32, 32)
C_BLACK_BD    = (95, 95, 95)
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
DISC_RX = int(SQ * 0.38)
DISC_RY = 6
DISC_STEP_MAX = DISC_RY * 2 + 2
DISC_STEP_MIN = 2

# ── Coordinate conversion ───────────────────────────────────────────────────


def board_to_px(r, c):
    """Board (row, col) -> pixel top-left. Row 0 at bottom of screen."""
    return MARGIN + c * SQ, MARGIN + (BOARD_N - 1 - r) * SQ


def px_to_board(mx, my):
    c = (mx - MARGIN) // SQ
    r = (BOARD_N - 1) - (my - MARGIN) // SQ
    if 0 <= r < BOARD_N and 0 <= c < BOARD_N:
        return r, c
    return None


# ── Alpha-blended drawing helpers ────────────────────────────────────────────


def _alpha_rect(surf, rgb, alpha, rect):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    s.fill((*rgb, alpha))
    surf.blit(s, (rect[0], rect[1]))


def _alpha_circle(surf, rgb, alpha, center, radius):
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(s, (*rgb, alpha), (radius, radius), radius)
    surf.blit(s, (center[0] - radius, center[1] - radius))


# ── 3D stacked-disc column drawing ──────────────────────────────────────────


def _disc_colors(piece):
    """Return (top_fill, side_fill, border) for a piece [color, rank]."""
    if piece[0] == W:
        return C_WHITE_TOP, C_WHITE_SIDE, C_WHITE_BD
    else:
        return C_BLACK_TOP, C_BLACK_SIDE, C_BLACK_BD


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


def draw_column(surf, col_data, sq_x, sq_y, fonts):
    """Render a column as 3D-stacked discs inside its square."""
    n = len(col_data)
    cx = sq_x + SQ // 2
    rx = DISC_RX
    ry = DISC_RY

    pad = 3
    avail = SQ - 2 * pad

    if n == 1:
        step = 0.0
    else:
        step = min(float(DISC_STEP_MAX), (avail - ry * 2) / (n - 1))
        step = max(step, float(DISC_STEP_MIN))

    stack_span = step * max(0, n - 1)

    bot_face_cy = sq_y + SQ - pad - ry
    top_face_cy = bot_face_cy - stack_span

    if top_face_cy - ry < sq_y + pad:
        top_face_cy = sq_y + pad + ry
        bot_face_cy = top_face_cy + stack_span
        if bot_face_cy + ry > sq_y + SQ - pad:
            step = (avail - ry * 2) / max(1, n - 1)
            step = max(step, 1.0)
            bot_face_cy = sq_y + SQ - pad - ry
            top_face_cy = bot_face_cy - step * (n - 1)

    if n == 1:
        depth = 8
    else:
        depth = max(int(step), 2)
        depth = min(depth, 10)

    for i in range(n):
        piece = col_data[i]
        face_cy = int(bot_face_cy - i * step)
        top_fill, side_fill, border = _disc_colors(piece)

        side_top_y = face_cy + 1
        side_bot_y = min(face_cy + depth, sq_y + SQ - 1)
        if side_bot_y > side_top_y:
            pygame.draw.rect(surf, side_fill,
                             (cx - rx, side_top_y, rx * 2, side_bot_y - side_top_y))
            bot_ell = pygame.Rect(cx - rx, side_bot_y - ry, rx * 2, ry * 2)
            pygame.draw.ellipse(surf, side_fill, bot_ell)
            pygame.draw.ellipse(surf, border, bot_ell, 1)
            pygame.draw.line(surf, border,
                             (cx - rx, side_top_y), (cx - rx, side_bot_y), 1)
            pygame.draw.line(surf, border,
                             (cx + rx - 1, side_top_y), (cx + rx - 1, side_bot_y), 1)

        face_rect = pygame.Rect(cx - rx, face_cy - ry, rx * 2, ry * 2)
        pygame.draw.ellipse(surf, top_fill, face_rect)
        pygame.draw.ellipse(surf, border, face_rect, 1)

        if i == n - 1 and piece[1] == KING:
            crown_c = C_CROWN_W if piece[0] == W else C_CROWN_B
            _draw_crown(surf, cx, face_cy, crown_c, rx)

    if n > 1:
        badge = fonts["badge"].render(str(n), True, (255, 70, 60))
        surf.blit(badge, (sq_x + SQ - badge.get_width() - 1, sq_y + 1))


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller with click-based interaction for Bashni.

    Wraps BashniLogic and maintains local UI state for piece selection,
    capture mode, multi-jump sequences, hover inspection, and undo.
    The authoritative game state is managed through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = BashniLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    # ── Setup ─────────────────────────────────────────────────────────────

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status_cache = self.logic.get_game_status(self.state)
        self.board = deepcopy(self.state["board"])
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self.game_over = False
        self.winner = None
        self.status = "White's turn"
        self.last_from = None
        self.last_to = None
        self.undo_stack = []
        self.hover_pos = None
        # Track the in-progress capture sequence for committing a full move
        self._capture_from = None
        self._capture_landings = []

    @property
    def turn(self):
        return self.state["turn"]

    # ── Online mode helpers ────────────────────────────────────────────

    @property
    def is_my_turn(self):
        """In online mode, True only when it's this player's turn."""
        if not self.online:
            return True
        return self.turn == PLAYER_TO_COLOR[self.my_player]

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._status_cache = self.logic.get_game_status(self.state)
        self.board = deepcopy(self.state["board"])
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self._capture_from = None
        self._capture_landings = []
        lf = self.state["last_from"]
        lt = self.state["last_to"]
        self.last_from = tuple(lf) if lf else None
        self.last_to = tuple(lt) if lt else None
        name = "White" if self.turn == W else "Black"
        self.status = f"{name}'s turn"
        if self._status_cache["is_over"]:
            self.game_over = True
            if self._status_cache["is_draw"]:
                self.winner = None
            else:
                self.winner = PLAYER_TO_COLOR[self._status_cache["winner"]]
        else:
            self.game_over = False
            self.winner = None
            if BashniLogic.any_capture_for(self.board, self.turn):
                self.status += "  (must capture)"

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self.game_over = True
        self.winner = PLAYER_TO_COLOR[winner] if winner else None
        if is_draw:
            self.status = "Draw!"
        elif reason == "forfeit":
            wn = "White" if winner == 1 else "Black"
            self.status = f"{wn} wins by forfeit!"
        else:
            wn = "White" if self.winner == W else "Black"
            self.status = f"{wn} wins!"

    def _save_undo(self):
        self.undo_stack.append(deepcopy(self.state))

    def undo(self):
        if self.online:
            return
        if not self.undo_stack or self.game_over:
            return
        self.state = self.undo_stack.pop()
        self._status_cache = self.logic.get_game_status(self.state)
        self.board = deepcopy(self.state["board"])
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self.game_over = False
        self.winner = None
        self._capture_from = None
        self._capture_landings = []
        lf = self.state["last_from"]
        lt = self.state["last_to"]
        self.last_from = tuple(lf) if lf else None
        self.last_to = tuple(lt) if lt else None
        name = "White" if self.turn == W else "Black"
        self.status = f"{name}'s turn"
        if BashniLogic.any_capture_for(self.board, self.turn):
            self.status += "  (must capture)"

    # ── Click handling ────────────────────────────────────────────────────

    def click(self, r, c):
        """Handle a click on board cell (r, c).

        In online mode, returns the complete move dict to send to the
        server once the full move (including multi-jump chains) is
        finished.  Returns None otherwise.
        """
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None
        if not is_dark(r, c):
            return None

        if self.jumping:
            return self._handle_jump_click(r, c)

        if self.selected is not None:
            dest = self._find_dest(r, c)
            if dest is not None:
                return self._execute_dest(dest)

        col = self.board[r][c]
        if col and col[-1][0] == self.turn:
            must_cap = BashniLogic.any_capture_for(self.board, self.turn)
            if must_cap:
                jumps = BashniLogic.get_jumps_for(self.board, r, c, self.turn)
                if jumps:
                    self.selected = (r, c)
                    self.valid_dests = jumps
                    self.is_capture_mode = True
                else:
                    self.selected = None
                    self.valid_dests = []
                    self.is_capture_mode = False
            else:
                moves = BashniLogic.get_simple_moves_for(self.board, r, c, self.turn)
                if moves:
                    self.selected = (r, c)
                    self.valid_dests = [(m[0], m[1]) for m in moves]
                    self.is_capture_mode = False
                else:
                    self.selected = None
                    self.valid_dests = []
        else:
            self.selected = None
            self.valid_dests = []
            self.is_capture_mode = False
        return None

    def _find_dest(self, r, c):
        for d in self.valid_dests:
            if d[0] == r and d[1] == c:
                return d
        return None

    def _execute_dest(self, dest):
        """Execute a selected destination.

        Returns the complete move dict in online mode (once the full
        move including any multi-jump chain is finished), or None.
        """
        sr, sc = self.selected
        if self.is_capture_mode:
            lr, lc, tr, tc, dr, dc = dest
            if self._capture_from is None:
                # First jump in a sequence -- save undo point (local only)
                if not self.online:
                    self._save_undo()
                self._capture_from = [sr, sc]
                self._capture_landings = []
            BashniLogic.exec_jump(self.board, sr, sc, lr, lc, tr, tc, self.turn)
            self._capture_landings.append([lr, lc])
            self.last_from = (sr, sc)
            self.last_to = (lr, lc)
            further = BashniLogic.get_jumps_for(self.board, lr, lc, self.turn, last_dir=[dr, dc])
            if further:
                self.jumping = (lr, lc)
                self.jump_dir = [dr, dc]
                self.selected = (lr, lc)
                self.valid_dests = further
                self.is_capture_mode = True
                return None
            else:
                # Full capture chain complete
                move = {"from": self._capture_from,
                        "jumps": list(self._capture_landings)}
                if self.online:
                    self._end_turn()
                    # Restore board from authoritative state so we don't
                    # desync (server will send the real state back)
                    self.board = deepcopy(self.state["board"])
                    return move
                self._commit_capture()
                self._end_turn()
                return None
        else:
            lr, lc = dest
            move = {"from": [sr, sc], "to": [lr, lc]}
            if self.online:
                self._end_turn()
                return move
            self._save_undo()
            BashniLogic.exec_move(self.board, sr, sc, lr, lc, self.turn)
            self._commit_simple(move)
            self.last_from = (sr, sc)
            self.last_to = (lr, lc)
            self._end_turn()
            return None

    def _handle_jump_click(self, r, c):
        """Handle a click during a multi-jump chain.

        Returns the complete move dict in online mode once the chain is
        finished, or None.
        """
        dest = self._find_dest(r, c)
        if dest is None:
            return None
        lr, lc, tr, tc, dr, dc = dest
        jr, jc = self.jumping
        BashniLogic.exec_jump(self.board, jr, jc, lr, lc, tr, tc, self.turn)
        self._capture_landings.append([lr, lc])
        self.last_to = (lr, lc)
        further = BashniLogic.get_jumps_for(self.board, lr, lc, self.turn, last_dir=[dr, dc])
        if further:
            self.jumping = (lr, lc)
            self.jump_dir = [dr, dc]
            self.selected = (lr, lc)
            self.valid_dests = further
            return None
        else:
            # Full capture chain complete
            move = {"from": self._capture_from,
                    "jumps": list(self._capture_landings)}
            if self.online:
                self._end_turn()
                self.board = deepcopy(self.state["board"])
                return move
            self._commit_capture()
            self._end_turn()
            return None

    def _commit_capture(self):
        """Commit the completed capture sequence through the logic module."""
        move = {"from": self._capture_from, "jumps": self._capture_landings}
        old_state = self.undo_stack[-1]
        player = COLOR_TO_PLAYER[old_state["turn"]]
        self.state = self.logic.apply_move(old_state, player, move)
        self._status_cache = self.logic.get_game_status(self.state)
        # Sync board from authoritative state
        self.board = deepcopy(self.state["board"])
        self._capture_from = None
        self._capture_landings = []

    def _commit_simple(self, move):
        """Commit a simple move through the logic module."""
        old_state = self.undo_stack[-1]
        player = COLOR_TO_PLAYER[old_state["turn"]]
        self.state = self.logic.apply_move(old_state, player, move)
        self._status_cache = self.logic.get_game_status(self.state)
        self.board = deepcopy(self.state["board"])

    def _end_turn(self):
        self.selected = None
        self.valid_dests = []
        self.is_capture_mode = False
        self.jumping = None
        self.jump_dir = None
        self._capture_from = None
        self._capture_landings = []

        # Update last_from / last_to from authoritative state
        lf = self.state["last_from"]
        lt = self.state["last_to"]
        self.last_from = tuple(lf) if lf else None
        self.last_to = tuple(lt) if lt else None

        if self._status_cache["is_over"]:
            self.game_over = True
            if self._status_cache["is_draw"]:
                self.winner = None
                # Determine draw reason
                brd = self.state["board"]
                turn = self.state["turn"]
                key = board_key(brd, turn)
                if self.state["pos_history"].get(key, 0) >= 3:
                    self.status = "Draw \u2014 threefold repetition"
                else:
                    self.status = "Draw \u2014 25-move rule"
            else:
                winner_int = self._status_cache["winner"]
                self.winner = PLAYER_TO_COLOR[winner_int]
                self.status = f"{'White' if self.winner == W else 'Black'} wins!"
            return

        name = "White" if self.turn == W else "Black"
        self.status = f"{name}'s turn"
        if BashniLogic.any_capture_for(self.board, self.turn):
            self.status += "  (must capture)"


# ── Rendering ────────────────────────────────────────────────────────────────


def draw_board(surf, game, fonts):
    surf.fill(C_BG)

    # Board squares
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            x, y = board_to_px(r, c)
            color = C_DARK_SQ if is_dark(r, c) else C_LIGHT_SQ
            pygame.draw.rect(surf, color, (x, y, SQ, SQ))

    # Last-move highlight
    for pos in (game.last_from, game.last_to):
        if pos:
            x, y = board_to_px(*pos)
            _alpha_rect(surf, C_LASTMOVE, 42, (x, y, SQ, SQ))

    # Selected square
    if game.selected:
        x, y = board_to_px(*game.selected)
        _alpha_rect(surf, C_SEL, 75, (x, y, SQ, SQ))

    # Valid destinations
    for d in game.valid_dests:
        dr, dc = d[0], d[1]
        x, y = board_to_px(dr, dc)
        col = C_CAPTURE if game.is_capture_mode else C_MOVE
        _alpha_rect(surf, col, 55, (x, y, SQ, SQ))
        cx, cy = x + SQ // 2, y + SQ // 2
        _alpha_circle(surf, col, 170, (cx, cy), 8)

    # Hover highlight
    if game.hover_pos:
        hr, hc = game.hover_pos
        if is_dark(hr, hc) and game.board[hr][hc]:
            x, y = board_to_px(hr, hc)
            _alpha_rect(surf, (255, 255, 255), 25, (x, y, SQ, SQ))

    # Coordinate labels
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

    # Pieces
    for r in range(BOARD_N):
        for c in range(BOARD_N):
            col_data = game.board[r][c]
            if col_data:
                draw_column(surf, col_data, *board_to_px(r, c), fonts)

    # Board border
    bx, by = MARGIN, MARGIN
    pygame.draw.rect(surf, (95, 88, 75), (bx - 2, by - 2, BOARD_PX + 4, BOARD_PX + 4), 2)

    # Right-side column inspector panel
    draw_panel(surf, game, fonts)

    # Bottom info bar
    info_y = MARGIN + BOARD_PX
    pygame.draw.rect(surf, C_INFO_BG, (0, info_y, MARGIN + BOARD_PX, INFO_H))

    # Turn indicator disc
    ind_top = C_WHITE_TOP if game.turn == W else C_BLACK_TOP
    ind_bd = C_WHITE_BD if game.turn == W else C_BLACK_BD
    iy = info_y + INFO_H // 2
    pygame.draw.circle(surf, ind_top, (18, iy), 10)
    pygame.draw.circle(surf, ind_bd, (18, iy), 10, 2)

    surf.blit(fonts["status"].render(game.status, True, C_TEXT), (36, info_y + 14))

    if game.online:
        role = "White" if game.my_player == 1 else "Black"
        accent = C_WHITE_TOP if game.my_player == 1 else C_BLACK_TOP
        tag = fonts["hint"].render(f"You: {role}", True, accent)
        tag_x = MARGIN + BOARD_PX - tag.get_width() - 8
        surf.blit(tag, (tag_x, info_y + 16))
    else:
        hint = fonts["hint"].render("R: Reset   U: Undo   Q: Quit", True, C_TEXT_DIM)
        hint_x = MARGIN + BOARD_PX - hint.get_width() - 8
        surf.blit(hint, (hint_x, info_y + 16))

    # Game-over overlay
    if game.game_over:
        board_area_w = MARGIN + BOARD_PX
        overlay = pygame.Surface((board_area_w, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        surf.blit(overlay, (0, 0))
        banner_h = 80
        banner_y = WIN_H // 2 - banner_h // 2
        pygame.draw.rect(surf, C_INFO_BG,
                         (0, banner_y, board_area_w, banner_h))
        accent = C_WHITE_TOP if game.winner == W else C_BLACK_TOP
        pygame.draw.line(surf, accent,
                         (0, banner_y), (board_area_w, banner_y), 3)
        pygame.draw.line(surf, accent,
                         (0, banner_y + banner_h),
                         (board_area_w, banner_y + banner_h), 3)
        big = fonts["status"].render(game.status, True, C_TEXT)
        surf.blit(big, big.get_rect(center=(board_area_w // 2,
                                             banner_y + 28)))
        if game.online:
            you_won = game.winner == PLAYER_TO_COLOR.get(game.my_player)
            is_draw = game.winner is None
            if is_draw:
                sub_text = "Draw."
            elif you_won:
                sub_text = "You win!"
            else:
                sub_text = "You lose."
            sub = fonts["hint"].render(
                f"{sub_text}  Press Esc to exit", True, C_TEXT_DIM)
        else:
            sub = fonts["hint"].render("Press R to play again", True, C_TEXT_DIM)
        surf.blit(sub, sub.get_rect(center=(board_area_w // 2,
                                             banner_y + 56)))

    # Online overlays
    if game.online:
        _draw_online_status(surf, game, fonts)


# ── Column inspector panel ───────────────────────────────────────────────────


def draw_panel(surf, game, fonts):
    """Right-side panel showing hovered/selected column composition."""
    px = MARGIN + BOARD_PX + MARGIN
    py = MARGIN
    pw = PANEL_W - MARGIN
    ph = BOARD_PX

    pygame.draw.rect(surf, C_PANEL_BG, (px - 4, py, pw + 8, ph))
    pygame.draw.rect(surf, C_PANEL_BD, (px - 4, py, pw + 8, ph), 1)

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

    pygame.draw.line(surf, C_PANEL_BD, (px, fy), (px + pw, fy), 1)
    fy += 8

    disc_w = min(pw - 20, 60)
    disc_h_face = 5
    disc_rx = disc_w // 2

    entry_h = 22
    max_visible = (ph - (fy - py) - 10) // entry_h

    pieces_to_show = list(reversed(inspect_col))
    overflow = len(pieces_to_show) > max_visible
    if overflow:
        pieces_to_show = pieces_to_show[:max_visible - 1]

    for idx, piece in enumerate(pieces_to_show):
        top_fill, side_fill, border = _disc_colors(piece)
        dy = fy + idx * entry_h
        disc_cy = dy + entry_h // 2

        is_commander = (idx == 0)
        rank_str = "K" if piece[1] == KING else "m"
        color_str = "W" if piece[0] == W else "B"
        pos_label = f"\u25B6 {color_str}-{rank_str}" if is_commander else f"   {color_str}-{rank_str}"

        mini_rx = disc_rx // 2
        mini_ry = disc_h_face
        disc_x = px + 16
        _r = (disc_x - mini_rx, disc_cy - mini_ry, mini_rx * 2, mini_ry * 2)
        pygame.draw.ellipse(surf, top_fill, _r)
        pygame.draw.ellipse(surf, border, _r, 1)

        if piece[1] == KING:
            crown_c = C_CROWN_W if piece[0] == W else C_CROWN_B
            _draw_crown(surf, disc_x, disc_cy, crown_c, mini_rx)

        label_c = C_TEXT if is_commander else C_TEXT_DIM
        surf.blit(fonts["panel"].render(pos_label, True, label_c), (disc_x + mini_rx + 6, disc_cy - 7))

        num = fonts["panel_small"].render(str(idx + 1), True, C_TEXT_DIM)
        surf.blit(num, (px + pw - num.get_width() - 2, disc_cy - 6))

    if overflow:
        dy = fy + len(pieces_to_show) * entry_h
        surf.blit(fonts["panel"].render(f"  ... +{len(inspect_col) - len(pieces_to_show)} more", True, C_TEXT_DIM), (px + 4, dy))


# ── Online overlays ─────────────────────────────────────────────────────────


def _draw_online_status(surf, game, fonts):
    """Draw overlays specific to online multiplayer."""
    board_area_w = MARGIN + BOARD_PX

    # "Waiting for opponent" when it's not your turn
    if not game.game_over and not game.is_my_turn:
        wait = fonts["hint"].render(
            "Opponent's turn \u2014 waiting\u2026", True, C_TEXT_DIM)
        surf.blit(wait, (12, MARGIN - 14))

    # Opponent disconnected banner
    if game.opponent_disconnected and not game.game_over:
        overlay = pygame.Surface((board_area_w, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 80))
        surf.blit(overlay, (0, 0))
        banner_h = 60
        banner_y = WIN_H // 2 - banner_h // 2
        pygame.draw.rect(surf, C_INFO_BG,
                         (0, banner_y, board_area_w, banner_h))
        msg = fonts["status"].render("Opponent disconnected", True, C_TEXT)
        surf.blit(msg, msg.get_rect(
            center=(board_area_w // 2, banner_y + 18)))
        sub = fonts["hint"].render(
            "Waiting for reconnection\u2026", True, C_TEXT_DIM)
        surf.blit(sub, sub.get_rect(
            center=(board_area_w // 2, banner_y + 42)))

    # Connection error bar at top
    if game.net_error:
        bar = pygame.Rect(0, 0, board_area_w, 28)
        pygame.draw.rect(surf, (60, 15, 15), bar)
        err = fonts["hint"].render(game.net_error, True, (225, 75, 65))
        surf.blit(err, err.get_rect(center=(board_area_w // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Bashni in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized).
    net : client.network.NetworkClient
        Active network connection to the game server.
    my_player : int
        This player's ID (1 = White, 2 = Black).
    initial_state : dict
        The initial game state from the server's ``game_started`` message.

    Returns when the game ends or the user closes the window.
    Does **not** call ``pygame.quit()`` -- the caller handles cleanup.
    """
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bashni \u2014 Online")
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

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    running = True
    while running:
        # ── Poll network ────────────────────────────────────────────
        for msg in net.poll_messages():
            mtype = msg.get("type")
            if mtype == "move_made":
                game.load_state(msg["state"])
            elif mtype == "game_over":
                game.load_state(msg["state"])
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

        # ── Events ──────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                pos = px_to_board(*event.pos)
                if pos is None:
                    continue
                r, c = pos
                move = game.click(r, c)
                if move is not None:
                    net.send_move(move)

            elif event.type == pygame.MOUSEMOTION:
                game.hover_pos = px_to_board(*event.pos)

        # ── Draw ────────────────────────────────────────────────────
        draw_board(screen, game, fonts)
        pygame.display.flip()
        clock.tick(FPS)


# ── Main loop (local hotseat play) ──────────────────────────────────────────


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

    game = GameClient()

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
