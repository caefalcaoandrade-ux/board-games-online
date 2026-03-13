"""
Tumbleweed -- Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls: Left-click to place / move.  Buttons in the side panel.
          Press N anytime for a new game, Q or Esc to quit.
"""

import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.tumbleweed_logic import (
        TumbleweedLogic, BOARD_SIZE, RED, WHITE, NEUTRAL,
        PH_SETUP, PH_PIE, PH_PLAY, PH_OVER,
        COLOUR_NAME, DIRS, cell_label,
    )
    from games.tumbleweed_logic import _cell_key, _key_to_coords
except ImportError:
    from tumbleweed_logic import (
        TumbleweedLogic, BOARD_SIZE, RED, WHITE, NEUTRAL,
        PH_SETUP, PH_PIE, PH_PLAY, PH_OVER,
        COLOUR_NAME, DIRS, cell_label,
    )
    from tumbleweed_logic import _cell_key, _key_to_coords

# ── Display Constants ────────────────────────────────────────────────────────

HEX_R = 27          # hex circumradius in pixels
WIN_W, WIN_H = 1340, 880
BOARD_CX = 420      # board centre x
BOARD_CY = 440      # board centre y
PANEL_LEFT = 790    # info-panel left edge
FPS = 60

_S3 = math.sqrt(3)

# ── Colour palette ───────────────────────────────────────────────────────────

BG          = (30, 32, 36)
PANEL_BG    = (40, 42, 47)
PANEL_LINE  = (60, 62, 68)
HEX_FILL    = (225, 216, 196)
HEX_EDGE    = (168, 158, 138)
LEGAL_FILL  = (175, 215, 135)
LEGAL_EDGE  = (135, 178, 100)
HOVER_FILL  = (248, 238, 175)
HOVER_EDGE  = (205, 195, 140)
CTRL_RED_T  = (210, 140, 130)
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

COLOUR_RGB = {RED: RED_C, WHITE: WHT_C, NEUTRAL: NEU_C}


# ── Hex geometry helpers ─────────────────────────────────────────────────────

def _cube2px(x, z):
    """Cube coordinate -> pixel centre (flat-top hex)."""
    px = HEX_R * 1.5 * x + BOARD_CX
    py = HEX_R * _S3 * (z + x * 0.5) + BOARD_CY
    return (px, py)


def _px2cube(mx, my):
    """Pixel -> nearest valid cube coordinate as a cell key string, or None."""
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
    if rx + ry + rz == 0 and max(abs(rx), abs(ry), abs(rz)) <= BOARD_SIZE - 1:
        return _cell_key(rx, ry, rz)
    return None


def _hex_corners(cx, cy):
    """Six corners of a flat-top hex centred at (cx, cy)."""
    return [(cx + HEX_R * math.cos(math.pi / 3 * i),
             cy + HEX_R * math.sin(math.pi / 3 * i)) for i in range(6)]


# ── Simple button widget ────────────────────────────────────────────────────

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


# ── Game Client ──────────────────────────────────────────────────────────────

class GameClient:
    """Client-side controller wrapping TumbleweedLogic with local UI state.

    Manages phase-based interaction (setup clicks, pie choice, play clicks,
    pass) and feeds moves to the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = TumbleweedLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)

    # ── Properties (read by renderer) ────────────────────────────────────

    @property
    def phase(self):
        return self.state["phase"]

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def stacks(self):
        return self.state["stacks"]

    @property
    def msg(self):
        return self.state["msg"]

    @property
    def scores(self):
        return self.state["scores"]

    @property
    def ctrl_map(self):
        return self.state["ctrl_map"]

    @property
    def winner(self):
        return self.state["winner"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def all_cells(self):
        return self.logic.all_cells

    @property
    def all_cells_set(self):
        return self.logic.all_cells_set

    @property
    def total_cells(self):
        return self.logic.total_cells

    # ── Online mode helpers ────────────────────────────────────────────

    @property
    def is_my_turn(self):
        """In online mode, True only when it's this player's turn."""
        if not self.online:
            return True
        phase = self.phase
        if phase == PH_SETUP:
            return self.my_player == RED
        if phase == PH_PIE:
            return self.my_player == WHITE
        if phase == PH_OVER:
            return False
        # PH_PLAY
        return self.turn == self.my_player

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._status = self.logic.get_game_status(self.state)

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        self.state["phase"] = PH_OVER
        self.state["winner"] = winner
        if is_draw:
            self.state["msg"] = "Game over -- Draw!"
        elif reason == "forfeit":
            wn = COLOUR_NAME.get(winner, "?")
            self.state["msg"] = f"{wn} wins by forfeit!"
        # Otherwise load_state already set the message from the state

    # ── Legal moves (cached per state) ───────────────────────────────────

    def legal_set(self):
        """Return set of cell keys that are legal placement targets in PLAY phase."""
        if self.phase != PH_PLAY:
            return set()
        player = self.logic.get_current_player(self.state)
        moves = self.logic.get_legal_moves(self.state, player)
        result = set()
        for m in moves:
            if "cell" in m:
                coords = m["cell"]
                result.add(_cell_key(coords[0], coords[1], coords[2]))
        return result

    # ── Actions ──────────────────────────────────────────────────────────

    def setup_click(self, cell_key):
        """Handle a click during setup phase.

        In online mode, returns the move dict to send to the server
        instead of applying it locally.  Returns None otherwise
        (or False on invalid click in local mode).
        """
        if self.online and not self.is_my_turn:
            return None
        if cell_key is None:
            return False if not self.online else None
        if cell_key not in self.all_cells_set:
            return False if not self.online else None
        if cell_key in self.stacks:
            return False if not self.online else None

        coords = _key_to_coords(cell_key)
        move = {"cell": coords}
        player = self.logic.get_current_player(self.state)
        if not self.logic.is_valid_move(self.state, player, move):
            return False if not self.online else None

        if self.online:
            return move

        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        return True

    def pie_choice(self, swap):
        """Handle the pie decision. swap is a bool.

        In online mode, returns the move dict to send to the server
        instead of applying it locally.  Returns None otherwise.
        """
        if self.online and not self.is_my_turn:
            return None
        move = {"swap": swap}
        if self.online:
            return move
        player = self.logic.get_current_player(self.state)
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        return None

    def do_move(self, cell_key):
        """Handle a placement click during play phase.

        In online mode, returns the move dict to send to the server
        instead of applying it locally.  Returns None otherwise
        (or False on invalid click in local mode).
        """
        if self.online and not self.is_my_turn:
            return None
        if cell_key is None:
            return False if not self.online else None
        coords = _key_to_coords(cell_key)
        move = {"cell": coords}
        player = self.logic.get_current_player(self.state)
        if not self.logic.is_valid_move(self.state, player, move):
            return False if not self.online else None

        if self.online:
            return move

        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        return True

    def do_pass(self):
        """Handle a pass action during play phase.

        In online mode, returns the move dict to send to the server
        instead of applying it locally.  Returns None otherwise.
        """
        if self.online and not self.is_my_turn:
            return None
        move = {"pass": True}
        if self.online:
            return move
        player = self.logic.get_current_player(self.state)
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        return None

    def flos(self, cell_key, colour):
        """Friendly LOS count for display info panel."""
        return TumbleweedLogic.flos(
            cell_key, colour, self.stacks, self.all_cells_set
        )


# ── Rendering ────────────────────────────────────────────────────────────────

class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen

        # fonts
        try:
            self.fn_title = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 23, bold=True)
            self.fn_body  = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 17)
            self.fn_small = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 14)
            self.fn_tiny  = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 12)
            self.fn_hex   = pygame.font.SysFont("Segoe UI,Helvetica,Arial", 16, bold=True)
        except Exception:
            self.fn_title = pygame.font.Font(None, 27)
            self.fn_body  = pygame.font.Font(None, 21)
            self.fn_small = pygame.font.Font(None, 18)
            self.fn_tiny  = pygame.font.Font(None, 15)
            self.fn_hex   = pygame.font.Font(None, 20)

        # pre-compute edge label positions
        S = BOARD_SIZE
        self.col_label_pos = {}
        self.row_label_pos = {}
        for x in range(-(S - 1), S):
            z_min = max(-(S - 1), -(S - 1) - x)
            px, py = _cube2px(x, z_min)
            self.col_label_pos[x] = (px, py - HEX_R - 10)
        for z in range(-(S - 1), S):
            x_min = max(-(S - 1), -(S - 1) - z)
            px, py = _cube2px(x_min, z)
            self.row_label_pos[z] = (px - HEX_R - 14, py)

    def _precompute_cell_px(self, game):
        """Pre-compute pixel centres for every cell. Called once."""
        cell_px = {}
        for cell_key in game.all_cells:
            coords = _key_to_coords(cell_key)
            cell_px[cell_key] = _cube2px(coords[0], coords[2])
        return cell_px

    def draw(self, game, hover, ls, cell_px):
        """Draw the full frame."""
        screen = self.screen
        screen.fill(BG)
        S = BOARD_SIZE
        PX = PANEL_LEFT + 35

        # ── board hexes ──────────────────────────────────────────────────
        for cell_key in game.all_cells:
            cx, cy = cell_px[cell_key]
            pts = _hex_corners(cx, cy)
            is_legal = cell_key in ls
            is_hover = (cell_key == hover)

            # fill colour
            if game.phase == PH_OVER and cell_key not in game.stacks:
                ctrl = game.ctrl_map.get(cell_key, -1)
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
            elif game.phase == PH_SETUP and cell_key not in game.stacks:
                fill, edge = (228, 220, 202), HEX_EDGE
            else:
                fill, edge = HEX_FILL, HEX_EDGE

            pygame.draw.polygon(screen, fill, pts)
            pygame.draw.aalines(screen, edge, True, pts)

            # stack disc
            if cell_key in game.stacks:
                col, ht = game.stacks[cell_key]
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
                txt = self.fn_hex.render(str(ht), True, tc)
                screen.blit(txt, (icx - txt.get_width() // 2,
                                  icy - txt.get_height() // 2))

        # ── coordinate labels along edges ────────────────────────────────
        for x, (lx, ly) in self.col_label_pos.items():
            letter = chr(65 + x + S - 1)
            t = self.fn_tiny.render(letter, True, TXT_DIM)
            screen.blit(t, (lx - t.get_width() // 2, ly - t.get_height() // 2))

        for z, (lx, ly) in self.row_label_pos.items():
            num_str = str(z + S)
            t = self.fn_tiny.render(num_str, True, TXT_DIM)
            screen.blit(t, (lx - t.get_width(), ly - t.get_height() // 2))

        # ══════════════════════════════════════════════════════════════════
        #  SIDE PANEL
        # ══════════════════════════════════════════════════════════════════
        pygame.draw.rect(screen, PANEL_BG, (PANEL_LEFT, 0, WIN_W - PANEL_LEFT, WIN_H))
        pygame.draw.line(screen, PANEL_LINE, (PANEL_LEFT, 0), (PANEL_LEFT, WIN_H), 2)

        # title
        t = self.fn_title.render("TUMBLEWEED", True, GOLD)
        screen.blit(t, (PX, 22))
        t = self.fn_tiny.render(
            f"Hexhex-{S}  \u00b7  {game.total_cells} cells  \u00b7  by Mike Zapawa",
            True, TXT_DIM)
        screen.blit(t, (PX, 52))

        pygame.draw.line(screen, PANEL_LINE, (PX - 5, 78), (WIN_W - 30, 78))

        # ── player score boxes ───────────────────────────────────────────
        sc = game.scores
        y0 = 95
        for i, (col, name, rgb) in enumerate(
                [(RED, "Red", RED_C), (WHITE, "White", WHT_C)]):
            ty = y0 + i * 130

            # colour dot + name
            pygame.draw.circle(screen, rgb, (PX + 12, ty + 14), 10)
            if col == WHITE:
                pygame.draw.circle(screen, WHT_DK, (PX + 12, ty + 14), 10, 1)
            t = self.fn_body.render(name, True, TXT)
            screen.blit(t, (PX + 32, ty + 3))

            # turn arrow
            if game.phase == PH_PLAY and game.turn == col:
                ax = PX - 6
                ay = ty + 9
                pygame.draw.polygon(screen, GOLD,
                                    [(ax, ay), (ax, ay + 10), (ax + 7, ay + 5)])

            # scores
            if sc:
                col_key = str(col)
                own, ctrl, total = sc[col_key]
                t = self.fn_small.render(f"Owned: {own}    Controlled: {ctrl}", True, TXT_DIM)
                screen.blit(t, (PX + 32, ty + 28))
                t = self.fn_body.render(f"Total:  {total}", True, TXT)
                screen.blit(t, (PX + 32, ty + 50))

            # winner badge
            if game.phase == PH_OVER and game.winner == col:
                t = self.fn_title.render("\u2605  WINNER", True, GOLD)
                screen.blit(t, (PX + 32, ty + 76))

        pygame.draw.line(screen, PANEL_LINE, (PX - 5, 355), (WIN_W - 30, 355))

        # ── phase-specific widgets ───────────────────────────────────────
        # (buttons are drawn by the main loop; we just draw the text here)
        if game.phase == PH_PIE:
            t = self.fn_body.render("Guest \u2014 choose your colour:", True, TXT)
            screen.blit(t, (PX, 368))

        if game.phase == PH_PLAY:
            tc = COLOUR_RGB[game.turn]
            tn = COLOUR_NAME[game.turn]
            t = self.fn_body.render(f"{tn}'s turn", True, tc)
            screen.blit(t, (PX, 370))
            nm = len(ls)
            if nm == 0:
                t = self.fn_small.render("No legal moves \u2014 must pass", True, (220, 160, 80))
            else:
                t = self.fn_small.render(
                    f"{nm} legal move{'s' if nm != 1 else ''}", True, TXT_DIM)
            screen.blit(t, (PX, 396))

        # ── hover cell info ──────────────────────────────────────────────
        info_y = 520
        pygame.draw.line(screen, PANEL_LINE, (PX - 5, info_y - 12), (WIN_W - 30, info_y - 12))
        t = self.fn_small.render("Cell info", True, TXT_DIM)
        screen.blit(t, (PX, info_y - 8))

        if hover and hover in game.all_cells_set:
            coords = _key_to_coords(hover)
            x, y, z = coords[0], coords[1], coords[2]
            lbl = cell_label(x, y, z)
            t = self.fn_body.render(f"{lbl}", True, TXT)
            screen.blit(t, (PX, info_y + 14))
            t = self.fn_small.render(f"cube  ({x}, {y}, {z})", True, TXT_DIM)
            screen.blit(t, (PX + 55, info_y + 16))

            if hover in game.stacks:
                col, ht = game.stacks[hover]
                cn = COLOUR_NAME[col]
                t = self.fn_small.render(f"Stack:  {cn}  height {ht}", True, TXT)
                screen.blit(t, (PX, info_y + 40))

            if game.phase == PH_PLAY:
                fr = game.flos(hover, RED)
                fw = game.flos(hover, WHITE)
                t = self.fn_small.render(
                    f"LOS \u2192  Red: {fr}   White: {fw}", True, TXT_DIM)
                screen.blit(t, (PX, info_y + 62))
        else:
            t = self.fn_small.render("hover a cell \u2026", True, TXT_DIM)
            screen.blit(t, (PX, info_y + 14))

        # ── bottom status bar ────────────────────────────────────────────
        pygame.draw.rect(screen, STATUS_BG, (0, WIN_H - 38, WIN_W, 38))
        t = self.fn_body.render(game.msg, True, TXT)
        screen.blit(t, (18, WIN_H - 30))

        # keyboard hints / online role indicator
        if game.online:
            role = COLOUR_NAME.get(game.my_player, "?")
            accent = RED_C if game.my_player == RED else WHT_C
            tag = self.fn_tiny.render(f"You: {role}", True, accent)
            screen.blit(tag, (WIN_W - tag.get_width() - 18, WIN_H - 26))
        else:
            t = self.fn_tiny.render("N = New game    P = Pass    Q = Quit", True, TXT_DIM)
            screen.blit(t, (WIN_W - t.get_width() - 18, WIN_H - 26))

        # ── game-over overlay ─────────────────────────────────────────
        if game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            screen.blit(overlay, (0, 0))
            banner_h = 80
            banner_y = WIN_H // 2 - banner_h // 2
            w_col = RED_C if game.winner == RED else WHT_C
            pygame.draw.rect(screen, PANEL_BG,
                             (0, banner_y, WIN_W, banner_h))
            pygame.draw.line(screen, w_col,
                             (0, banner_y), (WIN_W, banner_y), 3)
            pygame.draw.line(screen, w_col,
                             (0, banner_y + banner_h),
                             (WIN_W, banner_y + banner_h), 3)
            big = self.fn_title.render(game.msg, True, TXT)
            screen.blit(big, big.get_rect(center=(WIN_W // 2,
                                                   banner_y + 28)))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.fn_small.render(
                    f"{sub_text}  Press Esc to exit", True, TXT_DIM)
            else:
                sub = self.fn_small.render(
                    "Press N to play again", True, TXT_DIM)
            screen.blit(sub, sub.get_rect(center=(WIN_W // 2,
                                                   banner_y + 56)))

        # ── online overlays ───────────────────────────────────────────
        if game.online:
            self._draw_online_status(game)

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        screen = self.screen

        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            wait = self.fn_small.render(
                "Opponent's turn \u2014 waiting\u2026", True, TXT_DIM)
            screen.blit(wait, (12, 8))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(screen, PANEL_BG,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.fn_title.render(
                "Opponent disconnected", True, TXT)
            screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.fn_small.render(
                "Waiting for reconnection\u2026", True, TXT_DIM)
            screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(screen, (60, 15, 15), bar)
            err = self.fn_small.render(
                game.net_error, True, (225, 75, 65))
            screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Tumbleweed in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized).
    net : client.network.NetworkClient
        Active network connection to the game server.
    my_player : int
        This player's ID (1 = Red, 2 = White).
    initial_state : dict
        The initial game state from the server's ``game_started`` message.

    Returns when the game ends or the user closes the window.
    Does **not** call ``pygame.quit()`` -- the caller handles cleanup.
    """
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Tumbleweed \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    # pre-compute pixel centres for every cell
    cell_px = renderer._precompute_cell_px(game)

    # buttons
    PX = PANEL_LEFT + 35
    btn_pass = Btn(PX, 630, 210, 42, "Pass")
    btn_red = Btn(PX, 390, 210, 46, "Play as Red",
                  bg=RED_C, bgh=RED_HI, fg=TXT)
    btn_white = Btn(PX, 450, 210, 46, "Play as White",
                    bg=(175, 175, 175), bgh=WHT_C, fg=TXT_DARK)

    hover = None
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

        mx, my = pygame.mouse.get_pos()
        hover = _px2cube(mx, my)

        # ── Events ──────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_p and game.phase == PH_PLAY:
                    move = game.do_pass()
                    if move is not None:
                        net.send_move(move)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue

                if game.phase == PH_SETUP:
                    move = game.setup_click(hover)
                    if move is not None:
                        net.send_move(move)

                elif game.phase == PH_PIE:
                    if btn_red.clicked(mx, my):
                        move = game.pie_choice(False)
                        if move is not None:
                            net.send_move(move)
                    elif btn_white.clicked(mx, my):
                        move = game.pie_choice(True)
                        if move is not None:
                            net.send_move(move)

                elif game.phase == PH_PLAY:
                    if btn_pass.clicked(mx, my):
                        move = game.do_pass()
                        if move is not None:
                            net.send_move(move)
                    elif hover:
                        move = game.do_move(hover)
                        if move is not None:
                            net.send_move(move)

        # update button hover state
        for b in (btn_pass, btn_red, btn_white):
            b.update(mx, my)

        # legal move set
        ls = game.legal_set() if game.phase == PH_PLAY else set()

        # ── Draw ────────────────────────────────────────────────────
        renderer.draw(game, hover, ls, cell_px)

        # draw buttons that the renderer delegates to main loop
        fn_body = renderer.fn_body
        if game.phase == PH_PIE and game.is_my_turn:
            btn_red.draw(screen, fn_body)
            btn_white.draw(screen, fn_body)
        if game.phase == PH_PLAY and game.is_my_turn:
            btn_pass.draw(screen, fn_body)

        pygame.display.flip()
        clock.tick(FPS)


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Tumbleweed")
    clock = pygame.time.Clock()

    renderer = Renderer(screen)
    game = GameClient()

    # pre-compute pixel centres for every cell
    cell_px = renderer._precompute_cell_px(game)

    # buttons
    PX = PANEL_LEFT + 35
    btn_pass  = Btn(PX, 630, 210, 42, "Pass")
    btn_new   = Btn(PX, 690, 210, 42, "New Game")
    btn_red   = Btn(PX, 390, 210, 46, "Play as Red",
                    bg=RED_C, bgh=RED_HI, fg=TXT)
    btn_white = Btn(PX, 450, 210, 46, "Play as White",
                    bg=(175, 175, 175), bgh=WHT_C, fg=TXT_DARK)

    hover = None
    running = True

    while running:
        mx, my = pygame.mouse.get_pos()
        hover = _px2cube(mx, my)

        # ── events ───────────────────────────────────────────────────────
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
                        game.pie_choice(False)
                    elif btn_white.clicked(mx, my):
                        game.pie_choice(True)

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

        # legal move set (cached inside GameClient)
        ls = game.legal_set() if game.phase == PH_PLAY else set()

        # ── draw ─────────────────────────────────────────────────────────
        renderer.draw(game, hover, ls, cell_px)

        # draw buttons that the renderer delegates to main loop
        fn_body = renderer.fn_body
        if game.phase == PH_PIE:
            btn_red.draw(screen, fn_body)
            btn_white.draw(screen, fn_body)
        if game.phase == PH_PLAY:
            btn_pass.draw(screen, fn_body)
        btn_new.draw(screen, fn_body)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
