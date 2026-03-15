"""
Abalone -- Pygame display and local hotseat play (Belgian Daisy).

Two players on the same computer taking turns.
Controls:
  Left-click own marble  -> select / deselect
  Left-click empty cell  -> move selected group in that direction
  Left-click enemy marble-> push in that direction (if legal)
  Right-click            -> clear selection
  U                      -> undo last move
  R                      -> restart game
  Esc                    -> quit
"""

import copy
import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.abalone_logic import (
        AbaloneLogic, EMPTY, BLACK, WHITE, ROW_LENS, DIRS,
        rc_to_cube, cube_to_rc, cube_key, key_to_cube, cube_add, on_board,
    )
except ImportError:
    from abalone_logic import (
        AbaloneLogic, EMPTY, BLACK, WHITE, ROW_LENS, DIRS,
        rc_to_cube, cube_to_rc, cube_key, key_to_cube, cube_add, on_board,
    )

# ── Display Constants ────────────────────────────────────────────────────────

WINDOW_W, WINDOW_H = 1100, 920
FPS = 60

CELL_SP   = 70            # pixel distance between adjacent cell centers
CELL_R    = 29            # cell-pit drawn radius
MARBLE_R  = 25            # marble drawn radius
BOARD_CX  = WINDOW_W // 2
BOARD_CY  = WINDOW_H // 2 + 5
ROW_DY    = CELL_SP * math.sqrt(3) / 2.0   # ~60.6

# ── Warm colour palette ─────────────────────────────────────────────────────

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


# ── Pixel helpers ────────────────────────────────────────────────────────────

def cube_to_pixel(cube):
    """Cube coordinates [q,r,s] -> pixel position on screen."""
    rc = cube_to_rc(cube[0], cube[1], cube[2])
    r, c = rc[0], rc[1]
    rl = ROW_LENS[r]
    px = BOARD_CX + (c - (rl - 1) / 2.0) * CELL_SP
    py = BOARD_CY + (r - 4) * ROW_DY
    return (px, py)


def _lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _board_hex_vertices(pad):
    """6 vertices of the board hexagon, expanded outward by `pad` pixels."""
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


def _make_marble_surface(who, radius):
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


# ── Game Client ──────────────────────────────────────────────────────────────

class GameClient:
    """Client-side controller wrapping AbaloneLogic.

    Maintains local UI state (selection, messages) and exposes
    attributes that the Renderer reads each frame.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = AbaloneLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self.selected = []      # list of [q,r,s] lists
        self.msg = ""
        self.msg_timer = 0
        self.msg_color = C_MSG_ERR
        self.history = []       # list of previous states for undo
        self._game_over_msg = None

    # ── Properties (read by Renderer) ────────────────────────────────────

    @property
    def board(self):
        return self.state["board"]

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def captured(self):
        return self.state["captured"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

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
        self.selected = []
        self.msg = ""
        self.msg_timer = 0
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_msg = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            wn = "Black" if winner == BLACK else "White"
            self._game_over_msg = f"{wn} wins by forfeit!"
        else:
            self._game_over_msg = None  # use default display

    # ── Pixel positions (computed once, cached) ──────────────────────────

    _pix_cache = None

    @staticmethod
    def get_pix():
        """Compute pixel positions for all 61 cells. Returns dict: str-key -> (px, py)."""
        if GameClient._pix_cache is not None:
            return GameClient._pix_cache
        pix = {}
        for r in range(9):
            for c in range(ROW_LENS[r]):
                cube = rc_to_cube(r, c)
                k = cube_key(cube[0], cube[1], cube[2])
                pix[k] = cube_to_pixel(cube)
        GameClient._pix_cache = pix
        return pix

    # ── Hit detection ────────────────────────────────────────────────────

    @staticmethod
    def hit(mx, my):
        """Find which cell was clicked. Returns [q,r,s] list or None."""
        pix = GameClient.get_pix()
        best, bd = None, 1e9
        for k, (px, py) in pix.items():
            d = math.hypot(mx - px, my - py)
            if d < CELL_R + 4 and d < bd:
                best, bd = k, d
        if best is None:
            return None
        return key_to_cube(best)

    # ── Click handling ───────────────────────────────────────────────────

    def on_left_click(self, mx, my):
        """Handle a left-click.

        In online mode, returns the complete move dict (JSON-serializable)
        to send to the server instead of applying it locally.
        Returns None otherwise.
        """
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None
        hit = self.hit(mx, my)
        if hit is None:
            self.selected = []
            return None

        hk = cube_key(hit[0], hit[1], hit[2])
        val = self.board.get(hk)

        if val == self.turn:
            # Clicking an own marble: toggle selection
            if hit in self.selected:
                self.selected.remove(hit)
            elif AbaloneLogic.can_add_to_selection(self.board, self.turn, self.selected, hit):
                self.selected.append(hit)
            else:
                self.selected = [hit]
            return None
        else:
            # Clicking an empty/enemy cell: attempt a move
            if not self.selected:
                return None
            d = AbaloneLogic.dir_from_click(self.selected, hit)
            if d is None:
                self._flash("Click a cell adjacent to selection", C_MSG_ERR)
                return None

            move = {
                "marbles": [list(m) for m in self.selected],
                "direction": list(d),
            }

            # Check validity
            if not self.logic.is_valid_move(self.state, self.turn, move):
                self._flash("Illegal move", C_MSG_ERR)
                return None

            if self.online:
                # Don't apply locally — send to server
                self.selected = []
                return move

            # Local mode: apply immediately
            self.history.append(self.state)
            self.state = self.logic.apply_move(self.state, self.turn, move)
            self._status = self.logic.get_game_status(self.state)
            self.selected = []
            self._flash("", C_MSG_OK)
            return None

    def undo(self):
        """Undo the last move. No-op in online mode."""
        if self.online:
            return False
        if not self.history:
            return False
        self.state = self.history.pop()
        self._status = self.logic.get_game_status(self.state)
        self.selected = []
        return True

    def _flash(self, msg, color):
        self.msg = msg
        self.msg_color = color
        self.msg_timer = 150

    # ── Targets for current selection ────────────────────────────────────

    def get_targets(self):
        """Return valid targets dict for current selection (str-key -> 'move'/'push')."""
        if not self.selected:
            return {}
        return AbaloneLogic.valid_targets_for_selection(
            self.board, self.turn, self.captured,
            self.game_over, self.winner, self.selected)


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.board = state["board"]
        self.turn = state["turn"]
        self.captured = state["captured"]
        self._status = game.logic.get_game_status(state)
        self._game_over_msg = None
        self.selected = []
        self.msg = ""
        self.msg_timer = 0
        self.msg_color = C_MSG_ERR
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

    def get_targets(self):
        return {}


# ── Renderer ─────────────────────────────────────────────────────────────────

class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen
        self.flipped = False

        # Pre-render marble surfaces
        self.marble_surf = {
            BLACK: _make_marble_surface(BLACK, MARBLE_R),
            WHITE: _make_marble_surface(WHITE, MARBLE_R),
        }

        # Board outline vertices
        self.hex_outer = _board_hex_vertices(CELL_R + 22)
        self.hex_mid   = _board_hex_vertices(CELL_R + 16)
        self.hex_inner = _board_hex_vertices(CELL_R + 8)

        # Fonts
        self.f_big   = pygame.font.SysFont("Arial", 34, bold=True)
        self.f_med   = pygame.font.SysFont("Arial", 20)
        self.f_sm    = pygame.font.SysFont("Arial", 14)
        self.f_coord = pygame.font.SysFont("Consolas", 12)
        self.f_lbl   = pygame.font.SysFont("Arial", 16, bold=True)

    def _flip_px(self, px, py):
        """Flip a pixel position 180° around the board center."""
        if self.flipped:
            return (2 * BOARD_CX - px, 2 * BOARD_CY - py)
        return (px, py)

    def hit_cell(self, mx, my):
        """Find which cell was clicked, accounting for flip. Returns [q,r,s] or None."""
        if self.flipped:
            mx = 2 * BOARD_CX - mx
            my = 2 * BOARD_CY - my
        return GameClient.hit(mx, my)

    def draw(self, game):
        """Draw the full scene given a GameClient instance."""
        scr = self.screen
        scr.fill(C_BG)
        self._draw_board()
        self._draw_cells(game)
        self._draw_labels(game)
        self._draw_hud(game)
        if game.online:
            self._draw_online_status(game)

    # ── Board background ─────────────────────────────────────────────────

    def _draw_board(self):
        """Draw the wooden hexagonal board background with beveled edge."""
        pygame.draw.polygon(self.screen, C_BOARD_EDGE, self.hex_outer)
        pygame.draw.polygon(self.screen, C_BOARD_DK, self.hex_mid)
        pygame.draw.polygon(self.screen, C_BOARD, self.hex_inner)
        inner2 = _board_hex_vertices(CELL_R + 2)
        pygame.draw.polygon(self.screen, C_BOARD_LT, inner2)

    # ── Cells, marbles, hints ────────────────────────────────────────────

    def _draw_cells(self, game):
        targets = game.get_targets()
        pix = GameClient.get_pix()
        board = game.board
        selected_keys = set(cube_key(s[0], s[1], s[2]) for s in game.selected)

        for k, raw_pos in pix.items():
            px, py = self._flip_px(*raw_pos)
            ipx, ipy = int(px), int(py)
            val = board[k]

            # Cell pit (recessed hole in wood)
            pygame.draw.circle(self.screen, C_PIT_EDGE, (ipx, ipy), CELL_R)
            pygame.draw.circle(self.screen, C_PIT, (ipx, ipy), CELL_R - 2)
            pygame.draw.circle(self.screen, C_PIT_INNER, (ipx, ipy), CELL_R - 4)

            # Move/push hint
            if k in targets:
                hcol = C_HINT_PUSH if targets[k] == "push" else C_HINT_MOVE
                pygame.draw.circle(self.screen, hcol, (ipx, ipy), 10)
                inner = _lerp_color(hcol, (255, 255, 255), 0.35)
                pygame.draw.circle(self.screen, inner, (ipx, ipy), 5)

            # Marble
            if val in (BLACK, WHITE):
                s = self.marble_surf[val]
                self.screen.blit(s,
                    (ipx - s.get_width() // 2, ipy - s.get_height() // 2))

            # Selection ring
            if k in selected_keys:
                pygame.draw.circle(self.screen, C_SEL_RING,
                                   (ipx, ipy), CELL_R + 2, 3)

            # Coordinate label (only on empty, unhinted cells)
            if val == EMPTY and k not in targets:
                cube = key_to_cube(k)
                rc = cube_to_rc(cube[0], cube[1], cube[2])
                r, c = rc[0], rc[1]
                lbl = self.f_coord.render(f"{r+1}.{c+1}", True, C_COORD)
                self.screen.blit(lbl, (ipx - lbl.get_width() // 2,
                                       ipy - lbl.get_height() // 2))

    # ── Row/column labels ────────────────────────────────────────────────

    def _draw_labels(self, game):
        pix = GameClient.get_pix()

        for r in range(9):
            cube = rc_to_cube(r, 0)
            k = cube_key(cube[0], cube[1], cube[2])
            px, py = self._flip_px(*pix[k])
            lbl = self.f_lbl.render(f"R{r+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - CELL_R - 38,
                                   int(py) - lbl.get_height() // 2))

        for c in range(ROW_LENS[8]):
            cube = rc_to_cube(8, c)
            k = cube_key(cube[0], cube[1], cube[2])
            px, py = self._flip_px(*pix[k])
            lbl = self.f_coord.render(f"C{c+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - lbl.get_width() // 2,
                                   int(py) + CELL_R + 10))

        for c in range(ROW_LENS[0]):
            cube = rc_to_cube(0, c)
            k = cube_key(cube[0], cube[1], cube[2])
            px, py = self._flip_px(*pix[k])
            lbl = self.f_coord.render(f"C{c+1}", True, C_LABEL)
            self.screen.blit(lbl, (int(px) - lbl.get_width() // 2,
                                   int(py) - CELL_R - 18))

    # ── HUD (turn, scores, messages, controls) ───────────────────────────

    def _draw_hud(self, game):
        # Turn / Winner
        if game.game_over:
            if game._game_over_msg:
                msg = game._game_over_msg
            else:
                name = "BLACK" if game.winner == BLACK else "WHITE"
                msg = f"{name}  WINS!"
            txt = self.f_big.render(msg, True, C_SEL_RING)
        else:
            name = "BLACK" if game.turn == BLACK else "WHITE"
            col  = C_TURN_BLK if game.turn == BLACK else C_TURN_WHT
            txt  = self.f_big.render(f"{name}'s turn", True, col)
        self.screen.blit(txt, (WINDOW_W // 2 - txt.get_width() // 2, 14))

        # Capture scores
        self._draw_score(game, BLACK, 30, WINDOW_H - 82)
        self._draw_score(game, WHITE, WINDOW_W - 280, WINDOW_H - 82)

        # Controls / role indicator
        if game.online:
            role = "Black" if game.my_player == BLACK else "White"
            accent = C_TURN_BLK if game.my_player == BLACK else C_TURN_WHT
            tag = self.f_sm.render(f"You: {role}", True, accent)
            self.screen.blit(tag, (WINDOW_W // 2 - tag.get_width() // 2,
                                   WINDOW_H - 18))
        else:
            lines = [
                "LClick: select marble / move \u00b7 RClick: deselect",
                "U: undo \u00b7 R: restart \u00b7 Esc: quit",
            ]
            for i, line in enumerate(lines):
                s = self.f_sm.render(line, True, C_DIM)
                self.screen.blit(s, (WINDOW_W // 2 - s.get_width() // 2,
                                     WINDOW_H - 34 + i * 16))

        # Flash message
        if game.msg_timer > 0 and game.msg:
            game.msg_timer -= 1
            s = self.f_med.render(game.msg, True, game.msg_color)
            self.screen.blit(s, (WINDOW_W // 2 - s.get_width() // 2, 54))

        # Game-over overlay banner
        if game.game_over:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self.screen.blit(overlay, (0, 0))
            banner_h = 80
            banner_y = WINDOW_H // 2 - banner_h // 2
            accent = C_TURN_BLK if game.winner == BLACK else C_TURN_WHT
            pygame.draw.rect(self.screen, C_BG,
                             (0, banner_y, WINDOW_W, banner_h))
            pygame.draw.line(self.screen, accent,
                             (0, banner_y), (WINDOW_W, banner_y), 3)
            pygame.draw.line(self.screen, accent,
                             (0, banner_y + banner_h),
                             (WINDOW_W, banner_y + banner_h), 3)
            if game._game_over_msg:
                big_msg = game._game_over_msg
            else:
                wname = "BLACK" if game.winner == BLACK else "WHITE"
                big_msg = f"{wname}  WINS!"
            big = self.f_big.render(big_msg, True, C_SEL_RING)
            self.screen.blit(big, big.get_rect(
                center=(WINDOW_W // 2, banner_y + 28)))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.f_sm.render(
                    f"{sub_text}  Q / Esc to leave", True, C_DIM)
            else:
                sub = self.f_sm.render(
                    "Press R to play again", True, C_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(WINDOW_W // 2, banner_y + 56)))

    def _draw_score(self, game, color, x, y):
        name = "Black" if color == BLACK else "White"
        tcol = C_TURN_BLK if color == BLACK else C_TURN_WHT
        cap = game.captured.get(str(color), 0)
        lbl = self.f_med.render(f"{name} captured:", True, tcol)
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

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            wait = self.f_sm.render(
                "Opponent's turn \u2014 waiting\u2026", True, C_DIM)
            self.screen.blit(wait, (12, 58))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WINDOW_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, C_BG,
                             (0, banner_y, WINDOW_W, banner_h))
            msg = self.f_big.render("Opponent disconnected", True, C_SEL_RING)
            self.screen.blit(msg, msg.get_rect(
                center=(WINDOW_W // 2, banner_y + 18)))
            sub = self.f_sm.render(
                "Waiting for reconnection\u2026", True, C_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(WINDOW_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WINDOW_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_sm.render(game.net_error, True, C_MSG_ERR)
            self.screen.blit(err, err.get_rect(center=(WINDOW_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Abalone in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized).
    net : client.network.NetworkClient
        Active network connection to the game server.
    my_player : int
        This player's ID (1 = BLACK, 2 = WHITE).
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

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Abalone \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

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

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if game.game_over:
                        continue
                    # Flip click coords before hit detection
                    mx, my = event.pos
                    if orient.flipped:
                        mx = 2 * BOARD_CX - mx
                        my = 2 * BOARD_CY - my
                    move = game.on_left_click(mx, my)
                    if move is not None:
                        net.send_move(move)
                elif event.button == 3:
                    game.selected = []

        # ── Draw ────────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(FPS)


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Abalone \u2014 Belgian Daisy")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    mx, my = ev.pos
                    if renderer.flipped:
                        mx = 2 * BOARD_CX - mx
                        my = 2 * BOARD_CY - my
                    game.on_left_click(mx, my)
                elif ev.button == 3:
                    game.selected = []
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_r:
                    game.reset()
                    game._flash("Game restarted", C_MSG_OK)
                elif ev.key == pygame.K_u:
                    if game.undo():
                        game._flash("Move undone", C_MSG_OK)
                    else:
                        game._flash("Nothing to undo", C_MSG_ERR)
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped
                elif ev.key == pygame.K_ESCAPE:
                    running = False

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
