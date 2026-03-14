"""
Hive — Pygame display, local hotseat play, and online multiplayer.

Two players on the same computer taking turns (local), or one player
against a remote opponent (online).
Controls:
  Left-click   Select piece from hand or board, click destination
  Right-click  Pan the board view (drag)
  U            Undo last move (local only)
  R            Reset game (local only)
  Esc / Q      Quit
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
    from games.hive_logic import HiveLogic, PIECE_ABBREV, INITIAL_HAND, _key, _parse_key, _neighbors
except ImportError:
    from hive_logic import HiveLogic, PIECE_ABBREV, INITIAL_HAND, _key, _parse_key, _neighbors

# ── Palette ─────────────────────────────────────────────────────────────────

BG              = (35,  39,  46)
WHITE_PIECE     = (248, 243, 233)
WHITE_BORDER    = (195, 190, 180)
BLACK_PIECE     = (45,  48,  56)
BLACK_BORDER    = (85,  88, 100)
MOVE_HIGHLIGHT  = (70,  200, 115)
SELECT_HIGHLIGHT = (90, 145, 255)
PILLBUG_TARGET  = (255, 170,  50)
PILLBUG_DROP    = (200, 120, 255)
TEXT_PRIMARY     = (215, 218, 225)
TEXT_DIM         = (110, 115, 125)
PANEL_BG         = (42,  46,  54)
PERIMETER_STROKE = (60,  64,  72)
LAST_MOVE_FROM   = (220,  80,  80)
LAST_MOVE_TO     = (80, 220, 120)
WIN_GLOW         = (80, 255, 120)

# ── Layout Constants ────────────────────────────────────────────────────────

WIN_W = 1280
WIN_H = 820
PANEL_W = 185
HEX_SIZE = 34

# Piece type ordering for hand display
PIECE_ORDER = ["queen", "spider", "beetle", "grasshopper", "ant",
               "mosquito", "ladybug", "pillbug"]

# Selection modes
MODE_NONE = 0
MODE_HAND_PIECE = 1
MODE_BOARD_PIECE = 2
MODE_PILLBUG_SELECT = 3
MODE_PILLBUG_TARGET = 4


# ── Game Client ─────────────────────────────────────────────────────────────

class GameClient:
    """Client-side controller wrapping HiveLogic.

    Maintains local UI state (selection, highlights, history) and exposes
    state attributes for the Renderer.  The authoritative game state is
    only updated through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = HiveLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._game_over_message = None
        self.history = []
        self.clear_selection()
        self._refresh_legal()

    def clear_selection(self):
        """Reset all selection/highlight state."""
        self.mode = MODE_NONE
        self.selected_hand_piece = None      # piece type string
        self.selected_board_q = None
        self.selected_board_r = None
        self.move_destinations = set()       # (q,r) tuples — green
        self.pillbug_targets = set()         # (q,r) tuples — orange
        self.pillbug_drops = set()           # (q,r) tuples — purple
        self.pillbug_by_q = None
        self.pillbug_by_r = None
        self.pillbug_target_q = None
        self.pillbug_target_r = None

    def _refresh_legal(self):
        self._legal_moves = self.logic.get_legal_moves(
            self.state, self.state["current_player"])

    # ── Properties (read by Renderer) ────────────────────────────────────

    @property
    def board(self):
        return self.state["board"]

    @property
    def hands(self):
        return self.state["hands"]

    @property
    def turn(self):
        return self.state["current_player"]

    @property
    def turn_number(self):
        return self.state["turn_number"]

    @property
    def player_turns(self):
        return self.state["player_turns"]

    @property
    def last_moved_from(self):
        return self.state.get("last_moved_from", [])

    @property
    def last_moved_to(self):
        return self.state.get("last_moved_to", [])

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def is_my_turn(self):
        if not self.online:
            return True
        return self.turn == self.my_player

    @property
    def only_pass_legal(self):
        """True when the only legal move is pass."""
        return (len(self._legal_moves) == 1
                and self._legal_moves[0].get("action") == "pass")

    # ── Online mode helpers ──────────────────────────────────────────────

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._status = self.logic.get_game_status(self.state)
        self.clear_selection()
        self.net_error = ""
        self._refresh_legal()

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_message = "Game over -- Draw!"
        elif reason == "forfeit":
            wn = "White" if winner == 1 else "Black"
            self._game_over_message = f"{wn} wins by forfeit!"
        else:
            self._game_over_message = None

    # ── Selection actions ────────────────────────────────────────────────

    def select_hand_piece(self, piece_type):
        """Select a piece from the current player's hand.

        Computes and highlights valid placement destinations.
        """
        if self.game_over:
            return
        if self.online and not self.is_my_turn:
            return

        player = self.turn
        p_key = str(player)
        hand = self.state["hands"][p_key]
        if hand.get(piece_type, 0) <= 0:
            return

        # Collect all placement destinations for this piece type
        dests = set()
        for m in self._legal_moves:
            if m["action"] == "place" and m["piece"] == piece_type:
                dests.add((m["to"][0], m["to"][1]))

        if not dests:
            return

        self.clear_selection()
        self.mode = MODE_HAND_PIECE
        self.selected_hand_piece = piece_type
        self.move_destinations = dests

    def select_board_piece(self, q, r):
        """Select a piece on the board for movement.

        Computes movement destinations and pillbug ability targets.
        """
        if self.game_over:
            return
        if self.online and not self.is_my_turn:
            return

        key = _key(q, r)
        if key not in self.state["board"] or not self.state["board"][key]:
            return

        top = self.state["board"][key][-1]
        player = self.turn
        if top["owner"] != player:
            return

        # Normal movement destinations
        move_dests = set()
        for m in self._legal_moves:
            if m["action"] == "move" and m["from"] == [q, r]:
                move_dests.add((m["to"][0], m["to"][1]))

        # Pillbug ability: this piece is the "by" piece, collect targets
        pb_targets = set()
        for m in self._legal_moves:
            if m["action"] == "pillbug" and m["by"] == [q, r]:
                pb_targets.add((m["target"][0], m["target"][1]))

        if not move_dests and not pb_targets:
            return

        self.clear_selection()
        self.mode = MODE_BOARD_PIECE
        self.selected_board_q = q
        self.selected_board_r = r
        self.move_destinations = move_dests
        self.pillbug_targets = pb_targets
        # Store the "by" location for pillbug
        if pb_targets:
            self.pillbug_by_q = q
            self.pillbug_by_r = r

    def select_pillbug_target(self, tq, tr):
        """After selecting a pillbug piece, select the target to lift.

        Computes drop destinations for the pillbug ability.
        """
        if self.game_over:
            return
        if self.pillbug_by_q is None:
            return

        by_q = self.pillbug_by_q
        by_r = self.pillbug_by_r
        drops = set()
        for m in self._legal_moves:
            if (m["action"] == "pillbug"
                    and m["by"] == [by_q, by_r]
                    and m["target"] == [tq, tr]):
                drops.add((m["to"][0], m["to"][1]))

        if not drops:
            return

        self.mode = MODE_PILLBUG_TARGET
        self.pillbug_target_q = tq
        self.pillbug_target_r = tr
        self.move_destinations = set()
        self.pillbug_targets = set()
        self.pillbug_drops = drops

    def click_destination(self, q, r):
        """Click on a highlighted destination cell.

        Returns the move dict in online mode, or None.
        """
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None

        move = None

        if self.mode == MODE_HAND_PIECE and (q, r) in self.move_destinations:
            move = {
                "action": "place",
                "piece": self.selected_hand_piece,
                "to": [q, r],
            }
        elif self.mode == MODE_BOARD_PIECE and (q, r) in self.move_destinations:
            move = {
                "action": "move",
                "from": [self.selected_board_q, self.selected_board_r],
                "to": [q, r],
            }
        elif self.mode == MODE_PILLBUG_TARGET and (q, r) in self.pillbug_drops:
            move = {
                "action": "pillbug",
                "by": [self.pillbug_by_q, self.pillbug_by_r],
                "target": [self.pillbug_target_q, self.pillbug_target_r],
                "to": [q, r],
            }
        else:
            return None

        if move is None:
            return None

        if self.online:
            self.clear_selection()
            return move

        # Local mode: apply immediately
        self.history.append(copy.deepcopy(self.state))
        player = self.turn
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        self.clear_selection()
        self._refresh_legal()
        return None

    def click_pass(self):
        """Execute a pass move. Returns the move dict in online mode."""
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None
        if not self.only_pass_legal:
            return None

        move = {"action": "pass"}

        if self.online:
            self.clear_selection()
            return move

        # Local mode
        self.history.append(copy.deepcopy(self.state))
        player = self.turn
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)
        self.clear_selection()
        self._refresh_legal()
        return None

    def undo(self):
        """Undo the last move (local mode only)."""
        if self.online:
            return
        if not self.history:
            return
        self.state = self.history.pop()
        self._status = self.logic.get_game_status(self.state)
        self.clear_selection()
        self._refresh_legal()


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        # Neutralise UI state
        self.mode = MODE_NONE
        self.selected_hand_piece = None
        self.selected_board_q = None
        self.selected_board_r = None
        self.move_destinations = set()
        self.pillbug_targets = set()
        self.pillbug_drops = set()
        self.pillbug_by_q = None
        self.pillbug_by_r = None
        self.pillbug_target_q = None
        self.pillbug_target_r = None
        self._legal_moves = []

    @property
    def board(self):
        return self.state["board"]

    @property
    def hands(self):
        return self.state["hands"]

    @property
    def turn(self):
        return self.state["current_player"]

    @property
    def turn_number(self):
        return self.state["turn_number"]

    @property
    def player_turns(self):
        return self.state["player_turns"]

    @property
    def last_moved_from(self):
        return self.state.get("last_moved_from", [])

    @property
    def last_moved_to(self):
        return self.state.get("last_moved_to", [])

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def only_pass_legal(self):
        return False


# ── Renderer ────────────────────────────────────────────────────────────────

class Renderer:
    """Handles all Pygame drawing for Hive."""

    def __init__(self, screen, game):
        self.screen = screen
        self.flipped = False
        self.hs = HEX_SIZE

        self.win_w, self.win_h = screen.get_size()

        # Board area: between left and right panels
        self.board_left = PANEL_W
        self.board_right = self.win_w - PANEL_W
        self.board_cx = (self.board_left + self.board_right) / 2.0
        self.board_cy = self.win_h / 2.0

        # Pan offset (right-click drag)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._pan_start = None

        # Flat-top hex vertex offsets
        self.hex_verts = []
        for i in range(6):
            a = math.radians(60 * i)
            self.hex_verts.append((math.cos(a), math.sin(a)))

        # Fonts
        self.f_tiny  = pygame.font.SysFont("consolas,monospace", 11)
        self.f_small = pygame.font.SysFont("segoeui,arial,sans-serif", 14)
        self.f_med   = pygame.font.SysFont("segoeui,arial,sans-serif", 17, bold=True)
        self.f_large = pygame.font.SysFont("segoeui,arial,sans-serif", 24, bold=True)
        self.f_piece = pygame.font.SysFont("consolas,monospace", 18, bold=True)
        self.f_badge = pygame.font.SysFont("consolas,monospace", 10, bold=True)

        # Button rects (set during draw)
        self.btn_pass = pygame.Rect(0, 0, 0, 0)

        # Hand piece click rects: { piece_type: Rect } for each panel
        self.hand_rects_1 = {}  # White (player 1) — left panel
        self.hand_rects_2 = {}  # Black (player 2) — right panel

    # ── Coordinate transforms ──────────────────────────────────────────

    def hex_to_pixel(self, q, r):
        """Convert axial hex (q, r) to pixel position (flat-top)."""
        hs = self.hs
        x = hs * (3.0 / 2.0 * q)
        y = hs * (math.sqrt(3) * (r + q / 2.0))
        if self.flipped:
            y = -y
        px = self.board_cx + self.pan_x + x
        py = self.board_cy + self.pan_y + y
        return px, py

    def pixel_to_hex(self, mx, my):
        """Convert pixel position to axial hex (q, r) — nearest cell."""
        x = mx - self.board_cx - self.pan_x
        y = my - self.board_cy - self.pan_y
        if self.flipped:
            y = -y
        hs = self.hs
        q = (2.0 / 3.0 * x) / hs
        r = (-1.0 / 3.0 * x + math.sqrt(3) / 3.0 * y) / hs
        # Cube round
        s = -q - r
        rq, rr, rs = round(q), round(r), round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds:
            rq = -rr - rs
        elif dr > ds:
            rr = -rq - rs
        return int(rq), int(rr)

    # ── Hex drawing ────────────────────────────────────────────────────

    def _hex_points(self, cx, cy, sz):
        return [(cx + sz * dx, cy + sz * dy) for dx, dy in self.hex_verts]

    def _draw_hex(self, cx, cy, sz, fill, stroke=None, sw=1):
        pts = self._hex_points(cx, cy, sz)
        pygame.draw.polygon(self.screen, fill, pts)
        if stroke:
            pygame.draw.aalines(self.screen, stroke, True, pts)
            if sw > 1:
                pygame.draw.polygon(self.screen, stroke, pts, sw)

    def _draw_hex_outline(self, cx, cy, sz, stroke, sw=1):
        pts = self._hex_points(cx, cy, sz)
        pygame.draw.aalines(self.screen, stroke, True, pts)
        if sw > 1:
            pygame.draw.polygon(self.screen, stroke, pts, sw)

    # ── Pan handling ───────────────────────────────────────────────────

    def start_pan(self, mx, my):
        self._pan_start = (mx - self.pan_x, my - self.pan_y)

    def update_pan(self, mx, my):
        if self._pan_start:
            self.pan_x = mx - self._pan_start[0]
            self.pan_y = my - self._pan_start[1]

    def end_pan(self):
        self._pan_start = None

    # ── Occupied and perimeter cell computation ────────────────────────

    def _get_occupied_cells(self, board):
        """Return set of (q, r) tuples for all occupied cells."""
        cells = set()
        for key in board:
            if board[key]:
                q, r = _parse_key(key)
                cells.add((q, r))
        return cells

    def _get_perimeter_cells(self, occupied):
        """Return set of (q, r) tuples that are empty neighbors of occupied."""
        perimeter = set()
        for (q, r) in occupied:
            for nq, nr in _neighbors(q, r):
                if (nq, nr) not in occupied:
                    perimeter.add((nq, nr))
        return perimeter

    # ── Main draw ──────────────────────────────────────────────────────

    def draw(self, game):
        self.screen.fill(BG)
        self._draw_board(game)
        self._draw_left_panel(game)
        self._draw_right_panel(game)
        self._draw_status_bar(game)
        if game.online:
            self._draw_online_status(game)

    # ── Board drawing ──────────────────────────────────────────────────

    def _draw_board(self, game):
        board = game.board
        hs = self.hs

        occupied = self._get_occupied_cells(board)
        in_selection = game.mode != MODE_NONE

        # Gather all highlighted cells
        all_highlights = set()
        all_highlights.update(game.move_destinations)
        all_highlights.update(game.pillbug_targets)
        all_highlights.update(game.pillbug_drops)

        # Draw perimeter outlines when in selection mode
        if in_selection:
            perimeter = self._get_perimeter_cells(occupied)
            for (q, r) in perimeter:
                px, py = self.hex_to_pixel(q, r)
                # Only draw if within screen bounds (roughly)
                if (self.board_left - hs < px < self.board_right + hs
                        and -hs < py < self.win_h + hs):
                    self._draw_hex_outline(px, py, hs - 1, PERIMETER_STROKE, 1)

        # Draw highlight destinations (empty cells)
        for (q, r) in game.move_destinations:
            if (q, r) not in occupied:
                px, py = self.hex_to_pixel(q, r)
                col = (*MOVE_HIGHLIGHT, 80)
                surf = pygame.Surface((hs * 2 + 2, hs * 2 + 2), pygame.SRCALPHA)
                local_pts = self._hex_points(hs + 1, hs + 1, hs - 1)
                pygame.draw.polygon(surf, col, local_pts)
                self.screen.blit(surf, (px - hs - 1, py - hs - 1))
                self._draw_hex_outline(px, py, hs - 1, MOVE_HIGHLIGHT, 2)

        for (q, r) in game.pillbug_targets:
            if (q, r) not in occupied or True:  # targets are always occupied
                px, py = self.hex_to_pixel(q, r)
                self._draw_hex_outline(px, py, hs + 2, PILLBUG_TARGET, 2)

        for (q, r) in game.pillbug_drops:
            if (q, r) not in occupied:
                px, py = self.hex_to_pixel(q, r)
                col = (*PILLBUG_DROP, 80)
                surf = pygame.Surface((hs * 2 + 2, hs * 2 + 2), pygame.SRCALPHA)
                local_pts = self._hex_points(hs + 1, hs + 1, hs - 1)
                pygame.draw.polygon(surf, col, local_pts)
                self.screen.blit(surf, (px - hs - 1, py - hs - 1))
                self._draw_hex_outline(px, py, hs - 1, PILLBUG_DROP, 2)

        # Draw occupied cells (pieces)
        # Sort by stack height so tall stacks draw on top
        sorted_cells = sorted(occupied, key=lambda c: len(board[_key(c[0], c[1])]))
        for (q, r) in sorted_cells:
            px, py = self.hex_to_pixel(q, r)
            key = _key(q, r)
            stack = board[key]
            if not stack:
                continue

            top = stack[-1]
            height = len(stack)
            owner = top["owner"]
            piece_type = top["type"]
            abbrev = PIECE_ABBREV.get(piece_type, "?")

            # Piece colors
            if owner == 1:
                fill = WHITE_PIECE
                stroke = WHITE_BORDER
                text_col = (30, 30, 35)
            else:
                fill = BLACK_PIECE
                stroke = BLACK_BORDER
                text_col = (220, 222, 230)

            # Selection highlight ring
            is_selected = False
            if game.mode == MODE_BOARD_PIECE:
                if game.selected_board_q == q and game.selected_board_r == r:
                    is_selected = True
            if game.mode in (MODE_PILLBUG_SELECT, MODE_PILLBUG_TARGET):
                if game.pillbug_by_q == q and game.pillbug_by_r == r:
                    is_selected = True

            if is_selected:
                self._draw_hex(px, py, hs + 2, SELECT_HIGHLIGHT)

            # Draw the piece hex
            self._draw_hex(px, py, hs - 1, fill, stroke, 2)

            # Last move indicators
            lmf = game.last_moved_from
            lmt = game.last_moved_to
            if lmt and lmt[0] == q and lmt[1] == r and not game.game_over:
                # Small dot at bottom of hex
                pygame.draw.circle(self.screen, LAST_MOVE_TO,
                                   (int(px), int(py + hs * 0.6)), 3)
            if lmf and lmf[0] == q and lmf[1] == r and not game.game_over:
                pygame.draw.circle(self.screen, LAST_MOVE_FROM,
                                   (int(px), int(py + hs * 0.6)), 3)

            # Piece letter
            txt = self.f_piece.render(abbrev, True, text_col)
            self.screen.blit(txt, (px - txt.get_width() // 2,
                                   py - txt.get_height() // 2))

            # Stack height badge
            if height > 1:
                badge_x = int(px + hs * 0.5)
                badge_y = int(py - hs * 0.5)
                pygame.draw.circle(self.screen, (180, 50, 50),
                                   (badge_x, badge_y), 9)
                pygame.draw.circle(self.screen, (255, 255, 255),
                                   (badge_x, badge_y), 9, 1)
                btxt = self.f_badge.render(str(height), True, (255, 255, 255))
                self.screen.blit(btxt, (badge_x - btxt.get_width() // 2,
                                        badge_y - btxt.get_height() // 2))

            # Highlight ring if this cell is a move destination (occupied)
            if (q, r) in game.move_destinations:
                self._draw_hex_outline(px, py, hs + 2, MOVE_HIGHLIGHT, 2)

            # Pillbug target highlight ring
            if (q, r) in game.pillbug_targets:
                self._draw_hex_outline(px, py, hs + 3, PILLBUG_TARGET, 2)

            # Pillbug target selection highlight
            if (game.mode == MODE_PILLBUG_TARGET
                    and game.pillbug_target_q == q
                    and game.pillbug_target_r == r):
                self._draw_hex_outline(px, py, hs + 2, PILLBUG_TARGET, 3)

        # If board is empty, draw a faint hex at origin as a guide
        if not occupied and game.mode == MODE_NONE:
            px, py = self.hex_to_pixel(0, 0)
            self._draw_hex_outline(px, py, hs - 1, PERIMETER_STROKE, 1)

    # ── Left panel (White's hand) ──────────────────────────────────────

    def _draw_left_panel(self, game):
        scr = self.screen
        panel_rect = pygame.Rect(0, 0, PANEL_W, self.win_h)
        pygame.draw.rect(scr, PANEL_BG, panel_rect)
        pygame.draw.line(scr, (55, 59, 67),
                         (PANEL_W - 1, 0), (PANEL_W - 1, self.win_h), 1)

        x0 = 12
        y = 14

        # Title
        surf = self.f_med.render("White (P1)", True, WHITE_PIECE)
        scr.blit(surf, (x0, y))
        # Turn indicator
        if game.turn == 1 and not game.game_over:
            ind_x = x0 + surf.get_width() + 12
            ind_y = y + surf.get_height() // 2
            pygame.draw.circle(scr, MOVE_HIGHLIGHT, (ind_x, ind_y), 5)
        y += 30

        hand = game.hands.get("1", {})
        self.hand_rects_1 = {}
        for piece_type in PIECE_ORDER:
            count = hand.get(piece_type, 0)
            abbrev = PIECE_ABBREV.get(piece_type, "?")

            rect = pygame.Rect(x0, y, PANEL_W - 24, 28)
            self.hand_rects_1[piece_type] = rect

            # Highlight if selected
            is_sel = (game.mode == MODE_HAND_PIECE
                      and game.selected_hand_piece == piece_type
                      and game.turn == 1)
            if is_sel:
                pygame.draw.rect(scr, SELECT_HIGHLIGHT, rect, border_radius=4)
                pygame.draw.rect(scr, SELECT_HIGHLIGHT, rect.inflate(-4, -4),
                                 border_radius=3)

            # Piece abbreviation
            if count > 0:
                txt_col = WHITE_PIECE
            else:
                txt_col = TEXT_DIM

            # Draw small hex icon
            hx = x0 + 14
            hy = y + 14
            mini_hs = 10
            mini_pts = self._hex_points(hx, hy, mini_hs)
            if count > 0:
                pygame.draw.polygon(scr, WHITE_PIECE, mini_pts)
                pygame.draw.aalines(scr, WHITE_BORDER, True, mini_pts)
            else:
                pygame.draw.aalines(scr, TEXT_DIM, True, mini_pts)

            # Abbreviation in mini hex
            atxt = self.f_badge.render(abbrev, True,
                                       (30, 30, 35) if count > 0 else TEXT_DIM)
            scr.blit(atxt, (hx - atxt.get_width() // 2,
                            hy - atxt.get_height() // 2))

            # Piece name and count
            name_txt = self.f_small.render(
                f"{piece_type.capitalize()}", True, txt_col)
            scr.blit(name_txt, (x0 + 30, y + 4))

            count_txt = self.f_small.render(f"x{count}", True, txt_col)
            scr.blit(count_txt, (PANEL_W - 36, y + 4))

            y += 30

        # Player turn count
        y += 8
        pt = game.player_turns.get("1", 0)
        surf = self.f_tiny.render(f"Turns: {pt}", True, TEXT_DIM)
        scr.blit(surf, (x0, y))

    # ── Right panel (Black's hand) ─────────────────────────────────────

    def _draw_right_panel(self, game):
        scr = self.screen
        rx = self.win_w - PANEL_W
        panel_rect = pygame.Rect(rx, 0, PANEL_W, self.win_h)
        pygame.draw.rect(scr, PANEL_BG, panel_rect)
        pygame.draw.line(scr, (55, 59, 67),
                         (rx, 0), (rx, self.win_h), 1)

        x0 = rx + 12
        y = 14

        # Title
        surf = self.f_med.render("Black (P2)", True, TEXT_PRIMARY)
        scr.blit(surf, (x0, y))
        # Turn indicator
        if game.turn == 2 and not game.game_over:
            ind_x = x0 + surf.get_width() + 12
            ind_y = y + surf.get_height() // 2
            pygame.draw.circle(scr, MOVE_HIGHLIGHT, (ind_x, ind_y), 5)
        y += 30

        hand = game.hands.get("2", {})
        self.hand_rects_2 = {}
        for piece_type in PIECE_ORDER:
            count = hand.get(piece_type, 0)
            abbrev = PIECE_ABBREV.get(piece_type, "?")

            rect = pygame.Rect(x0, y, PANEL_W - 24, 28)
            self.hand_rects_2[piece_type] = rect

            # Highlight if selected
            is_sel = (game.mode == MODE_HAND_PIECE
                      and game.selected_hand_piece == piece_type
                      and game.turn == 2)
            if is_sel:
                pygame.draw.rect(scr, SELECT_HIGHLIGHT, rect, border_radius=4)
                pygame.draw.rect(scr, SELECT_HIGHLIGHT, rect.inflate(-4, -4),
                                 border_radius=3)

            if count > 0:
                txt_col = TEXT_PRIMARY
            else:
                txt_col = TEXT_DIM

            # Draw small hex icon
            hx = x0 + 14
            hy = y + 14
            mini_hs = 10
            mini_pts = self._hex_points(hx, hy, mini_hs)
            if count > 0:
                pygame.draw.polygon(scr, BLACK_PIECE, mini_pts)
                pygame.draw.aalines(scr, BLACK_BORDER, True, mini_pts)
            else:
                pygame.draw.aalines(scr, TEXT_DIM, True, mini_pts)

            atxt = self.f_badge.render(abbrev, True,
                                       (220, 222, 230) if count > 0 else TEXT_DIM)
            scr.blit(atxt, (hx - atxt.get_width() // 2,
                            hy - atxt.get_height() // 2))

            name_txt = self.f_small.render(
                f"{piece_type.capitalize()}", True, txt_col)
            scr.blit(name_txt, (x0 + 30, y + 4))

            count_txt = self.f_small.render(f"x{count}", True, txt_col)
            scr.blit(count_txt, (rx + PANEL_W - 36, y + 4))

            y += 30

        # Player turn count
        y += 8
        pt = game.player_turns.get("2", 0)
        surf = self.f_tiny.render(f"Turns: {pt}", True, TEXT_DIM)
        scr.blit(surf, (x0, y))

    # ── Status bar ─────────────────────────────────────────────────────

    def _draw_status_bar(self, game):
        scr = self.screen
        bar_h = 34
        bar_y = self.win_h - bar_h
        bar_rect = pygame.Rect(PANEL_W, bar_y, self.win_w - 2 * PANEL_W, bar_h)
        pygame.draw.rect(scr, PANEL_BG, bar_rect)
        pygame.draw.line(scr, (55, 59, 67),
                         (PANEL_W, bar_y), (self.win_w - PANEL_W, bar_y), 1)

        cx = (self.board_left + self.board_right) / 2
        y_mid = bar_y + bar_h // 2

        if game.game_over:
            if game._game_over_message:
                msg = game._game_over_message
            elif game.winner == 1:
                msg = "White wins!"
            elif game.winner == 2:
                msg = "Black wins!"
            elif game.winner is None and self._is_draw(game):
                msg = "Draw!"
            else:
                msg = "Game over!"
            surf = self.f_med.render(msg, True, WIN_GLOW)
            scr.blit(surf, (cx - surf.get_width() // 2,
                            y_mid - surf.get_height() // 2))
        else:
            turn_name = "White" if game.turn == 1 else "Black"
            turn_col = WHITE_PIECE if game.turn == 1 else TEXT_PRIMARY
            msg = f"{turn_name}'s turn  |  Turn {game.turn_number}"
            surf = self.f_med.render(msg, True, turn_col)
            scr.blit(surf, (cx - surf.get_width() // 2,
                            y_mid - surf.get_height() // 2))

            # Pass button
            self.btn_pass = pygame.Rect(0, 0, 0, 0)
            if game.only_pass_legal and (not game.online or game.is_my_turn):
                bw, bh = 80, 26
                bx = int(cx + surf.get_width() // 2 + 20)
                by = bar_y + (bar_h - bh) // 2
                self.btn_pass = pygame.Rect(bx, by, bw, bh)
                pygame.draw.rect(scr, (100, 70, 50), self.btn_pass,
                                 border_radius=5)
                pygame.draw.rect(scr, (170, 130, 80), self.btn_pass, 2,
                                 border_radius=5)
                ptxt = self.f_small.render("PASS", True, (230, 200, 150))
                scr.blit(ptxt, (bx + bw // 2 - ptxt.get_width() // 2,
                                by + bh // 2 - ptxt.get_height() // 2))

            # Selection mode hint
            hints = {
                MODE_NONE: "",
                MODE_HAND_PIECE: "Click a green hex to place",
                MODE_BOARD_PIECE: "Green=move  Orange=pillbug target",
                MODE_PILLBUG_SELECT: "Select piece to use pillbug on",
                MODE_PILLBUG_TARGET: "Purple=drop destination",
            }
            hint = hints.get(game.mode, "")
            if hint:
                hsrf = self.f_tiny.render(hint, True, TEXT_DIM)
                scr.blit(hsrf, (PANEL_W + 10, bar_y + 4))

        # Online role indicator
        if game.online:
            role = "White" if game.my_player == 1 else "Black"
            acol = WHITE_PIECE if game.my_player == 1 else TEXT_PRIMARY
            tag = self.f_tiny.render(f"You: {role}", True, acol)
            scr.blit(tag, (self.board_right - tag.get_width() - 8,
                           bar_y + bar_h // 2 - tag.get_height() // 2))

    def _is_draw(self, game):
        return game._status.get("is_draw", False) if hasattr(game, '_status') else False

    # ── Online overlays ────────────────────────────────────────────────

    def _draw_online_status(self, game):
        win_w, win_h = self.win_w, self.win_h

        if not game.game_over and not game.is_my_turn:
            wait = self.f_small.render(
                "Opponent's turn -- waiting...", True, TEXT_DIM)
            cx = (self.board_left + self.board_right) / 2
            self.screen.blit(wait, (cx - wait.get_width() // 2, 8))

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
                "Waiting for reconnection...", True, TEXT_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(win_w // 2, banner_y + 42)))

        if game.net_error:
            bar = pygame.Rect(0, 0, win_w, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_small.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(win_w // 2, 14)))

    # ── Hit-testing helpers ────────────────────────────────────────────

    def is_in_board_area(self, mx, my):
        """Check if pixel position is in the board area (between panels)."""
        return PANEL_W <= mx <= self.win_w - PANEL_W

    def hand_piece_at(self, mx, my, player):
        """Return the piece type string if (mx, my) is in a hand panel rect."""
        rects = self.hand_rects_1 if player == 1 else self.hand_rects_2
        for piece_type, rect in rects.items():
            if rect.collidepoint(mx, my):
                return piece_type
        return None


# ── Online entry point ──────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Hive in online multiplayer mode.

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

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Hive -- Online")
    clock = pygame.time.Clock()

    game = GameClient(online=True, my_player=my_player)
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

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                # Right-click: start panning
                renderer.start_pan(event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEMOTION:
                if event.buttons[2]:  # right button held
                    renderer.update_pan(event.pos[0], event.pos[1])

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                renderer.end_pan()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue

                mx, my = event.pos

                # Pass button
                if renderer.btn_pass.collidepoint(mx, my):
                    move = game.click_pass()
                    if move is not None:
                        net.send_move(move)
                    continue

                # Left panel (White's hand) — only if it's white's turn
                if mx < PANEL_W and game.turn == 1:
                    pt = renderer.hand_piece_at(mx, my, 1)
                    if pt is not None:
                        game.select_hand_piece(pt)
                    continue

                # Right panel (Black's hand) — only if it's black's turn
                if mx > renderer.win_w - PANEL_W and game.turn == 2:
                    pt = renderer.hand_piece_at(mx, my, 2)
                    if pt is not None:
                        game.select_hand_piece(pt)
                    continue

                # Board area
                if renderer.is_in_board_area(mx, my):
                    q, r = renderer.pixel_to_hex(mx, my)

                    # Check if clicking a destination
                    if (q, r) in game.move_destinations:
                        move = game.click_destination(q, r)
                        if move is not None:
                            net.send_move(move)
                        continue

                    # Check if clicking a pillbug target
                    if (q, r) in game.pillbug_targets:
                        game.select_pillbug_target(q, r)
                        continue

                    # Check if clicking a pillbug drop
                    if (q, r) in game.pillbug_drops:
                        move = game.click_destination(q, r)
                        if move is not None:
                            net.send_move(move)
                        continue

                    # Check if clicking an owned piece on the board
                    key = _key(q, r)
                    if (key in game.board and game.board[key]
                            and game.board[key][-1]["owner"] == game.turn):
                        game.select_board_piece(q, r)
                        continue

                    # Click on empty space: clear selection
                    game.clear_selection()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    game.clear_selection()

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


# ── Main loop (local hotseat play) ──────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Hive")
    clock = pygame.time.Clock()

    game = GameClient()
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
                    renderer.pan_x = 0
                    renderer.pan_y = 0
                elif ev.key == pygame.K_u:
                    game.undo()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                renderer.start_pan(ev.pos[0], ev.pos[1])

            elif ev.type == pygame.MOUSEMOTION:
                if ev.buttons[2]:
                    renderer.update_pan(ev.pos[0], ev.pos[1])

            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
                renderer.end_pan()

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if game.game_over:
                    continue

                mx, my = ev.pos

                # Pass button
                if renderer.btn_pass.collidepoint(mx, my):
                    game.click_pass()
                    continue

                # Left panel (White's hand) — only if it's white's turn
                if mx < PANEL_W and game.turn == 1:
                    pt = renderer.hand_piece_at(mx, my, 1)
                    if pt is not None:
                        game.select_hand_piece(pt)
                    continue

                # Right panel (Black's hand) — only if it's black's turn
                if mx > renderer.win_w - PANEL_W and game.turn == 2:
                    pt = renderer.hand_piece_at(mx, my, 2)
                    if pt is not None:
                        game.select_hand_piece(pt)
                    continue

                # Board area
                if renderer.is_in_board_area(mx, my):
                    q, r = renderer.pixel_to_hex(mx, my)

                    # Check if clicking a destination
                    if (q, r) in game.move_destinations:
                        game.click_destination(q, r)
                        continue

                    # Check if clicking a pillbug target
                    if (q, r) in game.pillbug_targets:
                        game.select_pillbug_target(q, r)
                        continue

                    # Check if clicking a pillbug drop
                    if (q, r) in game.pillbug_drops:
                        game.click_destination(q, r)
                        continue

                    # Check if clicking an owned piece on the board
                    key = _key(q, r)
                    if (key in game.board and game.board[key]
                            and game.board[key][-1]["owner"] == game.turn):
                        game.select_board_piece(q, r)
                        continue

                    # Click on empty space: clear selection
                    game.clear_selection()

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
