"""
Havannah — Pygame display, local hotseat play, and online multiplayer.

Two players on the same computer taking turns (local), or one player
against a remote opponent (online).
Controls:
  Left-click   Place a stone / click buttons
  U            Undo last move (local only)
  R            Reset game (local only)
  Esc / Q      Quit
"""

import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.havannah_logic import (
        HavannahLogic, EMPTY, WHITE, BLACK, DEFAULT_SIZE,
        cell_key, key_to_cell,
    )
except ImportError:
    from havannah_logic import (
        HavannahLogic, EMPTY, WHITE, BLACK, DEFAULT_SIZE,
        cell_key, key_to_cell,
    )

# ── Palette ─────────────────────────────────────────────────────────────────

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
C_ACCENT_WHITE  = (190, 190, 185)
C_ACCENT_BLACK  = (130, 115, 175)


# ── Cell label computation (display concern) ────────────────────────────────

def _compute_cell_labels(geo, size):
    """Human-readable labels: row letter + column number."""
    labels = {}
    row_i = 0
    for r in range(size - 1, -size, -1):
        row_cells = sorted([c for c in geo["cells"] if c[1] == r])
        if not row_cells:
            continue
        letter = chr(ord('A') + row_i)
        for ci, c in enumerate(row_cells):
            labels[c] = f"{letter}{ci + 1}"
        row_i += 1
    return labels


# ── Game Client ─────────────────────────────────────────────────────────────

class GameClient:
    """Client-side controller wrapping HavannahLogic.

    Maintains local UI state (hover, history) and exposes state
    attributes for the Renderer.  The authoritative game state is
    only updated through the logic module.
    """

    def __init__(self, size=DEFAULT_SIZE, online=False, my_player=None):
        self.logic = HavannahLogic(size)
        self.geo = self.logic.get_geometry()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._game_over_message = None
        self.hovered = None
        self.history = []

    # ── Properties (read by Renderer) ──────────────────────────────────────

    @property
    def board(self):
        return self.state["board"]

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def move_count(self):
        return self.state["move_count"]

    @property
    def swap_available(self):
        return self.state["swap_available"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def win_type(self):
        return self.state["win_type"]

    @property
    def winning_chain(self):
        return self.state["winning_chain"]

    @property
    def last_move(self):
        return self.state["last_move"]

    @property
    def size(self):
        return self.state["size"]

    # ── Online mode helpers ────────────────────────────────────────────

    @property
    def is_my_turn(self):
        """In online mode, True only when it's this player's turn."""
        if not self.online:
            return True
        return self.turn == self.my_player

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._status = self.logic.get_game_status(self.state)
        self.hovered = None
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            wn = "White" if winner == WHITE else "Black"
            self._game_over_message = f"{wn} wins by forfeit!"
        else:
            self._game_over_message = None

    # ── Actions ────────────────────────────────────────────────────────────

    def place(self, q, r):
        """Attempt to place a stone at (q, r).

        In online mode, returns the move list to send to the server
        instead of applying it locally.  Returns None otherwise.
        """
        if self.game_over:
            return None if self.online else False
        if self.online and not self.is_my_turn:
            return None
        move = [q, r]
        if not self.logic.is_valid_move(self.state, self.turn, move):
            return None if self.online else False
        if self.online:
            # Don't apply locally — send to server
            self.hovered = None
            return move
        # Local mode: apply immediately
        self.history.append(self.state)
        self.state = self.logic.apply_move(self.state, self.turn, move)
        self._status = self.logic.get_game_status(self.state)
        return True

    def swap(self):
        """Attempt the swap move.

        In online mode, returns the string "swap" to send to the server
        instead of applying it locally.  Returns None otherwise.
        """
        move = "swap"
        if self.game_over:
            return None if self.online else False
        if self.online and not self.is_my_turn:
            return None
        if not self.logic.is_valid_move(self.state, self.turn, move):
            return None if self.online else False
        if self.online:
            self.hovered = None
            return move
        # Local mode: apply immediately
        self.history.append(self.state)
        self.state = self.logic.apply_move(self.state, self.turn, move)
        self._status = self.logic.get_game_status(self.state)
        return True

    def undo(self):
        """Undo the last move."""
        if self.online:
            return
        if not self.history:
            return False
        self.state = self.history.pop()
        self._status = self.logic.get_game_status(self.state)
        return True


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self.board = state["board"]
        self.turn = state["turn"]
        self.move_count = state["move_count"]
        self.swap_available = state["swap_available"]
        self.size = state["size"]
        self.last_move = state["last_move"]
        self.win_type = state["win_type"]
        self.winning_chain = state["winning_chain"]
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.hovered = None
        self.geo = game.geo
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]


# ── Renderer ────────────────────────────────────────────────────────────────

class Renderer:
    """Handles all Pygame drawing for Havannah."""

    def __init__(self, screen, game):
        self.screen = screen
        self.flipped = False
        S = game.size

        # Auto-scale hex size
        self.hex_size = max(18, min(42, int(830 / (3 * (S - 1)))))
        hs = self.hex_size
        sqrt3 = math.sqrt(3)

        self.win_w, self.win_h = screen.get_size()
        margin = 70
        self.panel_w = 230

        board_w = sqrt3 * hs * (2 * S - 1) + hs
        self.cx = margin + board_w / 2
        self.cy = self.win_h / 2

        # Precompute pixel centers for all cells
        self.centers = {}
        for qr in game.geo["cells"]:
            q, r = qr
            x = hs * sqrt3 * (q + r / 2.0)
            y = hs * 1.5 * r
            self.centers[qr] = (self.cx + x, self.cy + y)

        # Hex vertex offsets (pointy-top)
        self.hex_verts = []
        for i in range(6):
            a = math.radians(30 + 60 * i)
            self.hex_verts.append((math.cos(a), math.sin(a)))

        # Cell labels
        self.cell_labels = _compute_cell_labels(game.geo, S)

        # Fonts
        self.f_tiny  = pygame.font.SysFont("consolas,monospace", max(10, hs // 3))
        self.f_small = pygame.font.SysFont("segoeui,arial,sans-serif",
                                           max(12, hs // 2 - 1))
        self.f_med   = pygame.font.SysFont("segoeui,arial,sans-serif", 17, bold=True)
        self.f_large = pygame.font.SysFont("segoeui,arial,sans-serif", 24, bold=True)
        self.f_title = pygame.font.SysFont("segoeui,arial,sans-serif", 30, bold=True)

        # Button rects (set during draw)
        self.btn_swap  = pygame.Rect(0, 0, 0, 0)
        self.btn_reset = pygame.Rect(0, 0, 0, 0)

    # ── Coordinate transforms ──────────────────────────────────────────────

    def _cell_center(self, cell):
        """Pixel center for a hex cell, accounting for flip."""
        cx, cy = self.centers[cell]
        if self.flipped:
            return (2 * self.cx - cx, 2 * self.cy - cy)
        return (cx, cy)

    def px_to_hex(self, mx, my, game):
        """Convert pixel position to hex cell (q, r) tuple or None."""
        x = mx - self.cx
        y = my - self.cy
        if self.flipped:
            x, y = -x, -y
        hs = self.hex_size
        q = (math.sqrt(3) / 3 * x - y / 3) / hs
        r = (2.0 / 3 * y) / hs
        return self._cube_round(q, r, game)

    def _cube_round(self, q, r, game):
        s = -q - r
        rq, rr, rs = round(q), round(r), round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds:
            rq = -rr - rs
        elif dr > ds:
            rr = -rq - rs
        cell = (rq, rr)
        return cell if cell in game.geo["cells"] else None

    # ── Hex drawing ────────────────────────────────────────────────────────

    def _hex_points(self, cx, cy, sz):
        return [(cx + sz * dx, cy + sz * dy) for dx, dy in self.hex_verts]

    def _draw_hex(self, cx, cy, sz, fill, stroke=None, sw=1):
        pts = self._hex_points(cx, cy, sz)
        pygame.draw.polygon(self.screen, fill, pts)
        if stroke:
            pygame.draw.aalines(self.screen, stroke, True, pts)
            if sw > 1:
                pygame.draw.polygon(self.screen, stroke, pts, sw)

    # ── Main draw ──────────────────────────────────────────────────────────

    def draw(self, game):
        self.screen.fill(BG)
        hs = self.hex_size
        geo = game.geo
        winning_chain_set = set(game.winning_chain)

        # ── Board cells ────────────────────────────────────────────────────
        for cell in geo["cells"]:
            cx, cy = self._cell_center(cell)
            k = cell_key(cell[0], cell[1])
            stone = game.board.get(k, EMPTY)

            # Determine colours
            if game.game_over and k in winning_chain_set:
                fill = WIN_GLOW
                stroke = (40, 200, 80)
                sw = 2
            elif stone == WHITE:
                fill = WHITE_STONE
                stroke = WHITE_OUTLINE
                sw = 2
            elif stone == BLACK:
                fill = BLACK_STONE
                stroke = BLACK_OUTLINE
                sw = 2
            elif cell == game.hovered and not game.game_over:
                fill = HOVER_W if game.turn == WHITE else HOVER_B
                stroke = EMPTY_STROKE
                sw = 1
            else:
                fill = EMPTY_FILL
                stroke = EMPTY_STROKE
                sw = 1

            # Topology accent for empty border cells
            if (cell in geo["corner_set"] and stone == EMPTY
                    and not (game.game_over and k in winning_chain_set)):
                stroke = CORNER_ACCENT
                sw = 2
            elif (cell in geo["side_index"] and stone == EMPTY
                  and not (game.game_over and k in winning_chain_set)):
                stroke = SIDE_ACCENT
                sw = 2

            self._draw_hex(cx, cy, hs - 1, fill, stroke, sw)

            # Last-move dot
            if (game.last_move and cell == tuple(game.last_move)
                    and not game.game_over):
                dot_col = BLACK_STONE if stone == WHITE else WHITE_STONE
                pygame.draw.circle(self.screen, dot_col,
                                   (int(cx), int(cy)), max(3, hs // 7))

            # Coordinate label on hover (empty cells)
            if cell == game.hovered and stone == EMPTY and not game.game_over:
                lbl = self.cell_labels.get(cell, "")
                surf = self.f_tiny.render(lbl, True, TEXT_PRIMARY)
                self.screen.blit(surf, (cx - surf.get_width() // 2,
                                        cy - surf.get_height() // 2))

        # ── Edge labels ────────────────────────────────────────────────────
        self._draw_edge_labels(game)

        # ── Side panel ─────────────────────────────────────────────────────
        self._draw_panel(game)

        if game.online:
            self._draw_online_status(game)

    # ── Edge labels ────────────────────────────────────────────────────────

    def _draw_edge_labels(self, game):
        S = game.size
        hs = self.hex_size
        offset = hs * 1.35

        # Row letters (left side of each row)
        row_i = 0
        for r in range(S - 1, -S, -1):
            row = sorted([c for c in game.geo["cells"] if c[1] == r])
            if not row:
                continue
            letter = chr(ord('A') + row_i)
            lx, ly = self._cell_center(row[0])
            surf = self.f_small.render(letter, True, TEXT_DIM)
            self.screen.blit(surf, (lx - offset - surf.get_width() // 2,
                                    ly - surf.get_height() // 2))
            row_i += 1

        # Column numbers along the bottom row
        bottom_row = sorted([c for c in game.geo["cells"] if c[1] == S - 1])
        for ci, cell in enumerate(bottom_row):
            bx, by = self._cell_center(cell)
            num = str(ci + 1)
            surf = self.f_small.render(num, True, TEXT_DIM)
            self.screen.blit(surf, (bx - surf.get_width() // 2,
                                    by + offset - surf.get_height() // 2 + 2))

    # ── Side panel ─────────────────────────────────────────────────────────

    def _draw_panel(self, game):
        px = self.win_w - self.panel_w + 10
        y = 28

        # Panel background
        panel_rect = pygame.Rect(self.win_w - self.panel_w - 5, 0,
                                 self.panel_w + 5, self.win_h)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)
        pygame.draw.line(self.screen, EMPTY_STROKE,
                         (panel_rect.x, 0), (panel_rect.x, self.win_h), 1)

        # Title
        surf = self.f_title.render("HAVANNAH", True, TEXT_PRIMARY)
        self.screen.blit(surf, (px, y)); y += 42

        # Board size
        geo = game.geo
        surf = self.f_small.render(
            f"Board size {game.size}  \u00b7  {len(geo['cells'])} cells",
            True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 30

        # Divider
        pygame.draw.line(self.screen, EMPTY_STROKE,
                         (px, y), (px + self.panel_w - 30, y))
        y += 12

        # Turn info
        if not game.game_over:
            name = "White" if game.turn == WHITE else "Black"
            surf = self.f_med.render(f"{name}'s turn", True, TEXT_PRIMARY)
            self.screen.blit(surf, (px, y))

            ind_col = WHITE_STONE if game.turn == WHITE else BLACK_STONE
            ind_out = WHITE_OUTLINE if game.turn == WHITE else BLACK_OUTLINE
            ind_x = px + surf.get_width() + 18
            ind_y = y + surf.get_height() // 2
            pygame.draw.circle(self.screen, ind_col, (ind_x, ind_y), 9)
            pygame.draw.circle(self.screen, ind_out, (ind_x, ind_y), 9, 2)
            y += 34

        surf = self.f_med.render(f"Move  {game.move_count}", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 34

        # Hovered cell info
        if game.hovered and not game.game_over:
            lbl = self.cell_labels.get(game.hovered, "?")
            q, r = game.hovered
            surf = self.f_med.render(f"Cell  {lbl}", True, TEXT_PRIMARY)
            self.screen.blit(surf, (px, y)); y += 22
            surf = self.f_tiny.render(
                f"q={q}  r={r}  s={-q - r}", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 18

            tag = ""
            if game.hovered in geo["corner_set"]:
                tag = "Corner"
            elif game.hovered in geo["side_index"]:
                tag = f"Side {geo['side_index'][game.hovered] + 1}"
            else:
                if max(abs(q), abs(r), abs(-q - r)) < game.size - 1:
                    tag = "Interior"
            if tag:
                surf = self.f_tiny.render(tag, True, TEXT_DIM)
                self.screen.blit(surf, (px, y))
            y += 22
        else:
            y += 62

        # Swap button
        if game.swap_available and game.move_count == 1 and not game.game_over:
            btn = pygame.Rect(px, y, 170, 36)
            self.btn_swap = btn
            pygame.draw.rect(self.screen, BTN_SWAP_BG, btn, border_radius=6)
            pygame.draw.rect(self.screen, BTN_SWAP_BORDER, btn, 2,
                             border_radius=6)
            surf = self.f_med.render("\u21c4  SWAP", True, (220, 215, 255))
            self.screen.blit(surf, (btn.centerx - surf.get_width() // 2,
                                    btn.centery - surf.get_height() // 2))
            y += 50

            surf = self.f_tiny.render("Black claims White's", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 15
            surf = self.f_tiny.render("opening stone.", True, TEXT_DIM)
            self.screen.blit(surf, (px, y)); y += 25
        else:
            self.btn_swap = pygame.Rect(0, 0, 0, 0)

        # Game over
        if game.game_over:
            y += 6
            # Use forced message from server if available
            if game.online and game._game_over_message:
                surf = self.f_large.render(
                    game._game_over_message, True, WIN_GLOW)
                self.screen.blit(surf, (px, y)); y += 36
            elif game.winner:
                wn = "White" if game.winner == WHITE else "Black"
                surf = self.f_large.render(f"{wn} wins!", True, WIN_GLOW)
                self.screen.blit(surf, (px, y)); y += 32
                surf = self.f_med.render(f"by {game.win_type}", True, WIN_GLOW)
                self.screen.blit(surf, (px, y)); y += 36
            else:
                surf = self.f_large.render("Draw!", True, TEXT_PRIMARY)
                self.screen.blit(surf, (px, y)); y += 36

            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                surf = self.f_med.render(
                    f"{sub_text}  Press Esc to exit", True, TEXT_DIM)
                self.screen.blit(surf, (px, y)); y += 52
                self.btn_reset = pygame.Rect(0, 0, 0, 0)
            else:
                btn = pygame.Rect(px, y, 170, 38)
                self.btn_reset = btn
                pygame.draw.rect(self.screen, BTN_NEW_BG, btn, border_radius=6)
                pygame.draw.rect(self.screen, BTN_NEW_BORDER, btn, 2,
                                 border_radius=6)
                surf = self.f_med.render("NEW GAME", True, (180, 255, 180))
                self.screen.blit(surf, (btn.centerx - surf.get_width() // 2,
                                        btn.centery - surf.get_height() // 2))
                y += 52
        else:
            self.btn_reset = pygame.Rect(0, 0, 0, 0)

        # Win conditions legend
        y = self.win_h - 185
        pygame.draw.line(self.screen, EMPTY_STROKE,
                         (px, y), (px + self.panel_w - 30, y))
        y += 12
        surf = self.f_small.render("Win conditions", True, TEXT_DIM)
        self.screen.blit(surf, (px, y)); y += 24

        for label in ("Bridge \u2013 2 corners",
                       "Fork   \u2013 3 sides",
                       "Ring   \u2013 closed loop"):
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
        if game.online:
            role = "White" if game.my_player == WHITE else "Black"
            accent = C_ACCENT_WHITE if game.my_player == WHITE else C_ACCENT_BLACK
            surf = self.f_tiny.render(f"You: {role}", True, accent)
            self.screen.blit(surf, (px, y))
        else:
            surf = self.f_tiny.render("R = reset   U = undo   Esc = quit",
                                      True, TEXT_DIM)
            self.screen.blit(surf, (px, y))

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        win_w, win_h = self.win_w, self.win_h

        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            wait = self.f_small.render(
                "Opponent's turn \u2014 waiting\u2026", True, TEXT_DIM)
            self.screen.blit(wait, (12, 8))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = win_h // 2 - banner_h // 2
            pygame.draw.rect(self.screen, PANEL_BG,
                             (0, banner_y, win_w, banner_h))
            msg = self.f_large.render("Opponent disconnected", True,
                                      TEXT_PRIMARY)
            self.screen.blit(msg, msg.get_rect(
                center=(win_w // 2, banner_y + 18)))
            sub = self.f_small.render(
                "Waiting for reconnection\u2026", True, TEXT_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(win_w // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, win_w, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_small.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(win_w // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Havannah in online multiplayer mode.

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
    try:
        from client.shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )
    except ImportError:
        from shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )

    size = initial_state.get("size", DEFAULT_SIZE)

    S = size
    hs = max(18, min(42, int(830 / (3 * (S - 1)))))
    sqrt3 = math.sqrt(3)
    board_w = sqrt3 * hs * (2 * S - 1) + hs
    board_h = 1.5 * hs * (2 * S - 1) + hs

    margin = 70
    panel_w = 230
    win_w = int(board_w + 2 * margin + panel_w)
    win_h = int(max(board_h + 2 * margin + 10, 680))

    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption("Havannah \u2014 Online")
    clock = pygame.time.Clock()

    game = GameClient(size=size, online=True, my_player=my_player)
    game.load_state(initial_state)

    renderer = Renderer(screen, game)
    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        # ── Poll network ────────────────────────────────────────────
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

        # ── Events ──────────────────────────────────────────────────
        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue

            elif event.type == pygame.MOUSEMOTION:
                game.hovered = renderer.px_to_hex(
                    event.pos[0], event.pos[1], game)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                # Check swap button
                if renderer.btn_swap.collidepoint(event.pos):
                    move = game.swap()
                    if move is not None:
                        net.send_move(move)
                    continue
                cell = renderer.px_to_hex(event.pos[0], event.pos[1], game)
                if cell:
                    move = game.place(cell[0], cell[1])
                    if move is not None:
                        net.send_move(move)

        # ── Draw ────────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(30)


# ── Main loop ──────────────────────────────────────────────────────────────

def main(board_size=DEFAULT_SIZE):
    pygame.init()
    game = GameClient(board_size)
    S = board_size

    hs = max(18, min(42, int(830 / (3 * (S - 1)))))
    sqrt3 = math.sqrt(3)
    board_w = sqrt3 * hs * (2 * S - 1) + hs
    board_h = 1.5 * hs * (2 * S - 1) + hs

    margin = 70
    panel_w = 230
    win_w = int(board_w + 2 * margin + panel_w)
    win_h = int(max(board_h + 2 * margin + 10, 680))

    screen = pygame.display.set_mode((win_w, win_h))
    pygame.display.set_caption("Havannah")
    clock = pygame.time.Clock()
    renderer = Renderer(screen, game)

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key == pygame.K_r:
                    game.reset()
                elif ev.key == pygame.K_u:
                    game.undo()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

            elif ev.type == pygame.MOUSEMOTION:
                game.hovered = renderer.px_to_hex(
                    ev.pos[0], ev.pos[1], game)

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if renderer.btn_swap.collidepoint(ev.pos):
                    game.swap()
                elif renderer.btn_reset.collidepoint(ev.pos):
                    game.reset()
                else:
                    cell = renderer.px_to_hex(ev.pos[0], ev.pos[1], game)
                    if cell:
                        game.place(cell[0], cell[1])

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    size = DEFAULT_SIZE
    if len(sys.argv) > 1:
        try:
            s = int(sys.argv[1])
            if 3 <= s <= 15:
                size = s
            else:
                print(f"Board size must be 3-15. Using default {size}.")
        except ValueError:
            print(f"Invalid size argument. Using default {size}.")
    main(size)
