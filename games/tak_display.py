"""
Tak 6x6 -- Pygame display, online multiplayer, and local hotseat play.

Controls: Left-click to select/place/move. Right-click or Esc to cancel.
          R to restart (local). F to flip board. Arrow keys for history.
"""

import sys
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.tak_logic import (
        TakLogic, WHITE, BLACK, FLAT, STANDING, CAPSTONE,
        BOARD_SIZE, CARRY_LIMIT, _DIR_DELTAS, DIR_NAMES,
        FILES, RANKS, sq_label, _top_owner, _top_type,
    )
except ImportError:
    from tak_logic import (
        TakLogic, WHITE, BLACK, FLAT, STANDING, CAPSTONE,
        BOARD_SIZE, CARRY_LIMIT, _DIR_DELTAS, DIR_NAMES,
        FILES, RANKS, sq_label, _top_owner, _top_type,
    )

# ── Display Constants ────────────────────────────────────────────────────────

CELL      = 85
BOARD_PX  = CELL * BOARD_SIZE
PAD_LEFT  = 70
PAD_TOP   = 50
PAD_BOT   = 60
PANEL_GAP = 35
PANEL_W   = 280

WIN_W = PAD_LEFT + BOARD_PX + PANEL_GAP + PANEL_W + 20
WIN_H = PAD_TOP + BOARD_PX + PAD_BOT

# Palette
BG            = (42, 30, 22)
BOARD_CLR     = (196, 162, 107)
BOARD_CLR2    = (178, 143, 90)
BOARD_BORDER  = (90, 58, 30)
GRID_LINE     = (140, 105, 60)
COORD_CLR     = (210, 185, 145)

WHITE_FILL    = (240, 220, 175)
WHITE_EDGE    = (200, 180, 135)
BLACK_FILL    = (82, 55, 35)
BLACK_EDGE    = (55, 35, 20)

SEL_CLR       = (255, 220, 80, 120)
LEGAL_CLR     = (100, 220, 100, 90)
PATH_CLR      = (100, 160, 255, 90)

TXT           = (230, 215, 185)
TXT_DIM       = (160, 140, 110)
TXT_WARN      = (255, 180, 80)
TURN_WHITE    = (255, 240, 200)
TURN_BLACK    = (160, 110, 70)
BTN_CLR       = (110, 80, 50)
BTN_HOVER     = (140, 105, 65)
BTN_TEXT      = (240, 225, 195)
WIN_GOLD      = (255, 215, 0)

# UI phases
PH_IDLE       = 0
PH_PLACE_TYPE = 1
PH_CARRY      = 2
PH_DIRECTION  = 3
PH_DROPS      = 4


# ── Button helper ────────────────────────────────────────────────────────────

class _Button:
    def __init__(self, x, y, w, h, text, value):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.value = value

    def draw(self, surface, font, mx, my):
        hover = self.rect.collidepoint(mx, my)
        c = BTN_HOVER if hover else BTN_CLR
        pygame.draw.rect(surface, c, self.rect, border_radius=6)
        pygame.draw.rect(surface, BOARD_BORDER, self.rect, 2, border_radius=6)
        t = font.render(self.text, True, BTN_TEXT)
        surface.blit(t, (self.rect.centerx - t.get_width() // 2,
                         self.rect.centery - t.get_height() // 2))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


# ── Piece drawing helpers ────────────────────────────────────────────────────

def _piece_colors(owner):
    if owner == WHITE:
        return WHITE_FILL, WHITE_EDGE
    return BLACK_FILL, BLACK_EDGE


def _draw_flat(surface, cx, cy, owner, w=36, h=12):
    fill, edge = _piece_colors(owner)
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.ellipse(surface, fill, rect)
    pygame.draw.ellipse(surface, edge, rect, 2)


def _draw_standing(surface, cx, cy, owner, w=12, h=34):
    fill, edge = _piece_colors(owner)
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surface, fill, rect, border_radius=3)
    pygame.draw.rect(surface, edge, rect, 2, border_radius=3)


def _draw_capstone(surface, cx, cy, owner, radius=16):
    fill, edge = _piece_colors(owner)
    pygame.draw.circle(surface, fill, (cx, cy), radius)
    pygame.draw.circle(surface, edge, (cx, cy), radius, 2)
    pygame.draw.circle(surface, edge, (cx, cy), 5)


def _draw_piece(surface, cx, cy, owner, type_code, scale=1.0):
    if type_code == FLAT:
        _draw_flat(surface, cx, cy, owner,
                   w=int(36 * scale), h=int(12 * scale))
    elif type_code == STANDING:
        _draw_standing(surface, cx, cy, owner,
                       w=int(12 * scale), h=int(34 * scale))
    elif type_code == CAPSTONE:
        _draw_capstone(surface, cx, cy, owner, radius=int(16 * scale))


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Controller for Tak with multi-phase UI interaction.

    Phases:
        PH_IDLE       -- waiting for square selection
        PH_PLACE_TYPE -- choosing piece type to place
        PH_CARRY      -- choosing carry count for movement
        PH_DIRECTION  -- choosing movement direction
        PH_DROPS      -- choosing drop counts step by step
    """

    def __init__(self, online=False, my_player=None):
        self.logic = TakLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._legal = self.logic.get_legal_moves(self.state,
                                                  self.state["turn"])
        self.phase = PH_IDLE
        self.sel_rc = None
        self.filtered = []
        self.buttons = []
        self.carry_count = 0
        self.move_dir = None       # direction int (0-3)
        self.partial_drops = []
        self.move_path = []        # squares traversed during drop phase
        self.message = ""
        self._forced_message = None

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def turn_number(self):
        return self.state["turn_number"]

    @property
    def game_over(self):
        return self.state["game_over"]

    @property
    def winner(self):
        return self.state["winner"]

    @property
    def win_type(self):
        return self.state.get("win_type")

    @property
    def is_my_turn(self):
        if not self.online:
            return True
        return self.turn == self.my_player

    # ── Online helpers ──────────────────────────────────────────────────

    def load_state(self, state):
        self.state = state
        self._legal = self.logic.get_legal_moves(state, state["turn"])
        self.phase = PH_IDLE
        self.sel_rc = None
        self.filtered = []
        self.buttons = []
        self.carry_count = 0
        self.move_dir = None
        self.partial_drops = []
        self.move_path = []
        self.message = ""
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        self.state = dict(self.state)
        self.state["game_over"] = True
        self.state["winner"] = winner
        self.phase = PH_IDLE
        self.sel_rc = None
        self.filtered = []
        self.buttons = []
        if is_draw:
            self._forced_message = "Game over -- Draw!"
        elif reason == "forfeit":
            wn = "WHITE" if winner == WHITE else "BLACK"
            self._forced_message = f"{wn} wins by forfeit!"
        else:
            self._forced_message = None

    # ── UI reset ────────────────────────────────────────────────────────

    def _reset_ui(self):
        self.phase = PH_IDLE
        self.sel_rc = None
        self.filtered = []
        self.buttons = []
        self.carry_count = 0
        self.move_dir = None
        self.partial_drops = []
        self.move_path = []
        self.message = ""

    def deselect(self):
        """Cancel current selection, return to idle."""
        self._reset_ui()

    # ── Button building ─────────────────────────────────────────────────

    def _build_buttons(self, options, panel_x, y_start):
        bx = panel_x + 15
        bw, bh, gap = 130, 34, 5
        btns = []
        by = y_start
        for label, val in options:
            btns.append(_Button(bx, by, bw, bh, label, val))
            by += bh + gap
        return btns

    # ── Click handling ──────────────────────────────────────────────────

    def click(self, r, c, panel_x):
        """Handle a board click. Returns move dict for online, or None."""
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None

        if self.phase == PH_IDLE:
            return self._click_idle(r, c, panel_x)
        elif self.phase == PH_DIRECTION:
            return self._click_direction(r, c)
        elif self.phase == PH_DROPS:
            return self._click_drops(r, c)
        else:
            # In button-selection phase, board click cancels + re-selects
            self._reset_ui()
            return self._click_idle(r, c, panel_x)

    def click_button(self, pos, panel_x):
        """Handle a button click. Returns move dict for online, or None."""
        for btn in self.buttons:
            if btn.hit(pos):
                return self._handle_button(btn.value, panel_x)
        return None

    def _click_idle(self, r, c, panel_x):
        board = self.state["board"]
        stack = board[r][c]
        tn = self.turn_number

        if tn <= 2:
            # Opening: auto-place flat on empty
            if not stack:
                matching = [m for m in self._legal
                            if m["row"] == r and m["col"] == c]
                if matching:
                    return self._commit(matching[0])
            return None

        # Normal turn
        if not stack:
            # Empty square -> placement
            matching = [m for m in self._legal
                        if m["action"] == "place"
                        and m["row"] == r and m["col"] == c]
            if not matching:
                return None
            self.sel_rc = (r, c)
            self.filtered = matching
            types = sorted(set(m["piece"] for m in matching))
            if len(types) == 1:
                return self._commit(matching[0])
            opts = []
            for t in types:
                label = {"flat": "Flat (F)", "standing": "Standing (S)",
                         "capstone": "Capstone (C)"}[t]
                opts.append((label, t))
            self.phase = PH_PLACE_TYPE
            self.buttons = self._build_buttons(opts, panel_x, 370)
            return None

        elif _top_owner(stack) == self.turn:
            # Own stack -> movement
            matching = [m for m in self._legal
                        if m["action"] == "move"
                        and m["row"] == r and m["col"] == c]
            if not matching:
                self.message = "No moves from this stack"
                return None
            self.sel_rc = (r, c)
            self.filtered = matching
            carries = sorted(set(sum(m["drops"]) for m in matching))
            if len(carries) == 1:
                return self._select_carry(carries[0], panel_x)
            opts = [(f"Carry {k}", k) for k in carries]
            self.phase = PH_CARRY
            self.buttons = self._build_buttons(opts, panel_x, 370)
        return None

    def _select_carry(self, val, panel_x=0):
        self.carry_count = val
        self.filtered = [m for m in self.filtered
                         if sum(m["drops"]) == val]
        dirs = sorted(set(m["direction"] for m in self.filtered))
        if len(dirs) == 1:
            return self._select_direction(dirs[0], panel_x)
        self.phase = PH_DIRECTION
        self.buttons = []
        return None

    def _select_direction(self, d, panel_x=0):
        self.move_dir = d
        self.filtered = [m for m in self.filtered
                         if m["direction"] == d]
        self.partial_drops = []
        self.move_path = []
        if len(self.filtered) == 1:
            return self._commit(self.filtered[0])
        self.phase = PH_DROPS
        self._update_drop_buttons(panel_x)
        return None

    def _update_drop_buttons(self, panel_x=0):
        step = len(self.partial_drops)
        valid = set()
        for m in self.filtered:
            if len(m["drops"]) > step:
                if m["drops"][:step] == self.partial_drops:
                    valid.add(m["drops"][step])
        if not valid:
            return
        if len(valid) == 1:
            return self._execute_drop(valid.pop(), panel_x)
        opts = [(f"Drop {d}", d) for d in sorted(valid)]
        self.buttons = self._build_buttons(opts, panel_x, 370)
        return None

    def _execute_drop(self, d, panel_x=0):
        self.partial_drops.append(d)
        dr, dc = _DIR_DELTAS[self.move_dir]
        if self.move_path:
            lr, lc = self.move_path[-1]
        else:
            lr, lc = self.sel_rc
        self.move_path.append((lr + dr, lc + dc))
        self.filtered = [m for m in self.filtered
                         if m["drops"][:len(self.partial_drops)]
                         == self.partial_drops]
        remaining = self.carry_count - sum(self.partial_drops)
        if remaining == 0 or len(self.filtered) == 1:
            if self.filtered:
                return self._commit(self.filtered[0])
            return None
        return self._update_drop_buttons(panel_x)

    def _click_direction(self, r, c):
        if self.sel_rc is None:
            return None
        sr, sc = self.sel_rc
        dr, dc = r - sr, c - sc
        if abs(dr) + abs(dc) != 1:
            return None
        # Map delta to direction code
        delta_to_dir = {(1, 0): 0, (-1, 0): 1, (0, 1): 2, (0, -1): 3}
        d = delta_to_dir.get((dr, dc))
        if d is not None and d in set(m["direction"] for m in self.filtered):
            return self._select_direction(d)
        return None

    def _click_drops(self, r, c):
        dr, dc = _DIR_DELTAS[self.move_dir]
        if self.move_path:
            er, ec = self.move_path[-1][0] + dr, self.move_path[-1][1] + dc
        else:
            er, ec = self.sel_rc[0] + dr, self.sel_rc[1] + dc
        if (r, c) != (er, ec):
            return None
        step = len(self.partial_drops)
        valid = set()
        for m in self.filtered:
            if len(m["drops"]) > step:
                if m["drops"][:step] == self.partial_drops:
                    valid.add(m["drops"][step])
        if len(valid) == 1:
            return self._execute_drop(valid.pop())
        return None

    def _handle_button(self, value, panel_x):
        if self.phase == PH_PLACE_TYPE:
            matching = [m for m in self.filtered if m["piece"] == value]
            if matching:
                return self._commit(matching[0])
        elif self.phase == PH_CARRY:
            return self._select_carry(value, panel_x)
        elif self.phase == PH_DROPS:
            return self._execute_drop(value, panel_x)
        return None

    def handle_key(self, key, panel_x=0):
        """Handle keyboard shortcuts during phases. Returns move or None."""
        if self.phase == PH_PLACE_TYPE:
            km = {pygame.K_f: "flat", pygame.K_s: "standing",
                  pygame.K_c: "capstone"}
            if key in km:
                matching = [m for m in self.filtered
                            if m["piece"] == km[key]]
                if matching:
                    return self._commit(matching[0])
        elif self.phase == PH_CARRY:
            if pygame.K_1 <= key <= pygame.K_6:
                val = key - pygame.K_0
                if val in set(sum(m["drops"]) for m in self.filtered):
                    return self._select_carry(val, panel_x)
        elif self.phase == PH_DROPS:
            if pygame.K_1 <= key <= pygame.K_6:
                val = key - pygame.K_0
                step = len(self.partial_drops)
                valid = set()
                for m in self.filtered:
                    if len(m["drops"]) > step:
                        if m["drops"][:step] == self.partial_drops:
                            valid.add(m["drops"][step])
                if val in valid:
                    return self._execute_drop(val, panel_x)
        return None

    def _commit(self, move):
        """Commit a move. Online: return it. Local: apply it."""
        if self.online:
            self._reset_ui()
            return move
        self.state = self.logic.apply_move(self.state, self.turn, move)
        self._legal = self.logic.get_legal_moves(self.state,
                                                  self.state["turn"])
        self._reset_ui()
        return None


# ── History view proxy ───────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self.turn = state["turn"]
        self.turn_number = state["turn_number"]
        self.game_over = state["game_over"]
        self.winner = state["winner"]
        self.win_type = state.get("win_type")
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        self._forced_message = None
        # No interactive state
        self.phase = PH_IDLE
        self.sel_rc = None
        self.filtered = []
        self.buttons = []
        self.move_path = []
        self.move_dir = None
        self.message = ""
        self.carry_count = 0
        self.partial_drops = []


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    """All Pygame drawing for Tak."""

    def __init__(self, screen):
        self.screen = screen
        self.flipped = False
        self.f_lg = pygame.font.SysFont("georgia", 26, bold=True)
        self.f_md = pygame.font.SysFont("georgia", 18)
        self.f_sm = pygame.font.SysFont("georgia", 14)
        self.f_xs = pygame.font.SysFont("georgia", 12)
        self.f_co = pygame.font.SysFont("consolas,monospace", 15, bold=True)
        self._ov_sel = self._make_ov(SEL_CLR)
        self._ov_leg = self._make_ov(LEGAL_CLR)
        self._ov_path = self._make_ov(PATH_CLR)

    def _make_ov(self, color):
        s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        s.fill(color)
        return s

    # ── Coordinate mapping (flip-aware) ─────────────────────────────────

    @property
    def panel_x(self):
        return PAD_LEFT + BOARD_PX + PANEL_GAP

    def _cell_tl(self, r, c):
        """Top-left pixel of cell (r, c). Row 0 = rank 1 = bottom."""
        if self.flipped:
            sx = PAD_LEFT + (BOARD_SIZE - 1 - c) * CELL
            sy = PAD_TOP + r * CELL
        else:
            sx = PAD_LEFT + c * CELL
            sy = PAD_TOP + (BOARD_SIZE - 1 - r) * CELL
        return sx, sy

    def _cell_center(self, r, c):
        sx, sy = self._cell_tl(r, c)
        return sx + CELL // 2, sy + CELL // 2

    def hit_test(self, mx, my):
        """Return (row, col) for a pixel, or None."""
        if self.flipped:
            gc = (BOARD_SIZE - 1) - (mx - PAD_LEFT) // CELL
            gr = (my - PAD_TOP) // CELL
        else:
            gc = (mx - PAD_LEFT) // CELL
            gr = (BOARD_SIZE - 1) - (my - PAD_TOP) // CELL
        if 0 <= gr < BOARD_SIZE and 0 <= gc < BOARD_SIZE:
            return (gr, gc)
        return None

    # ── Main draw ───────────────────────────────────────────────────────

    def draw(self, game):
        self.screen.fill(BG)
        self._draw_board(game)
        self._draw_stacks(game)
        self._draw_highlights(game)
        self._draw_panel(game)
        if game.online:
            self._draw_online_status(game)

    # ── Board ───────────────────────────────────────────────────────────

    def _draw_board(self, game):
        bx, by = PAD_LEFT, PAD_TOP
        br = pygame.Rect(bx - 4, by - 4, BOARD_PX + 8, BOARD_PX + 8)
        pygame.draw.rect(self.screen, BOARD_BORDER, br, border_radius=4)

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                sx, sy = self._cell_tl(r, c)
                clr = BOARD_CLR if (r + c) % 2 == 0 else BOARD_CLR2
                pygame.draw.rect(self.screen, clr,
                                 (sx, sy, CELL, CELL))
                pygame.draw.rect(self.screen, GRID_LINE,
                                 (sx, sy, CELL, CELL), 1)

        # File labels (a-f)
        for c in range(BOARD_SIZE):
            ci = (BOARD_SIZE - 1 - c) if self.flipped else c
            sx, _ = self._cell_tl(0, c)
            lbl = self.f_co.render(FILES[ci], True, COORD_CLR)
            # Below board
            bbot = PAD_TOP + BOARD_PX + 8
            self.screen.blit(lbl, (sx + CELL // 2 - lbl.get_width() // 2,
                                   bbot))

        # Rank labels (1-6)
        for r in range(BOARD_SIZE):
            ri = (BOARD_SIZE - 1 - r) if self.flipped else r
            _, sy = self._cell_tl(r, 0)
            lbl = self.f_co.render(RANKS[ri], True, COORD_CLR)
            self.screen.blit(lbl, (PAD_LEFT - lbl.get_width() - 8,
                                   sy + CELL // 2 - lbl.get_height() // 2))

    # ── Stacks ──────────────────────────────────────────────────────────

    def _draw_stacks(self, game):
        board = game.state["board"]
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                stack = board[r][c]
                if not stack:
                    continue
                cx, cy = self._cell_center(r, c)
                height = len(stack)
                # Mini stack indicators for buried pieces
                if height > 1:
                    for i in range(min(height - 1, 8)):
                        p = stack[i]
                        fill, _ = _piece_colors(p[0])
                        iy = cy + 20 - i * 4
                        pygame.draw.rect(self.screen, fill,
                                         (cx - 16, iy, 32, 3),
                                         border_radius=1)
                        pygame.draw.rect(self.screen, GRID_LINE,
                                         (cx - 16, iy, 32, 3), 1,
                                         border_radius=1)
                # Top piece
                top = stack[-1]
                top_y = cy - min(height - 1, 8) * 2
                _draw_piece(self.screen, cx, top_y, top[0], top[1])
                # Stack height number
                if height > 1:
                    num = self.f_xs.render(str(height), True, TXT)
                    self.screen.blit(num, (cx + 22, cy + 16))

    # ── Highlights ──────────────────────────────────────────────────────

    def _draw_highlights(self, game):
        if game.sel_rc:
            sx, sy = self._cell_tl(*game.sel_rc)
            self.screen.blit(self._ov_sel, (sx, sy))

        if game.phase == PH_DIRECTION:
            # Highlight adjacent squares with valid directions
            dirs = set(m["direction"] for m in game.filtered)
            sr, sc = game.sel_rc
            for d in dirs:
                dr, dc = _DIR_DELTAS[d]
                nr, nc = sr + dr, sc + dc
                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                    sx, sy = self._cell_tl(nr, nc)
                    self.screen.blit(self._ov_leg, (sx, sy))

        elif game.phase == PH_DROPS:
            # Highlight path taken
            for pr, pc in game.move_path:
                sx, sy = self._cell_tl(pr, pc)
                self.screen.blit(self._ov_path, (sx, sy))
            # Highlight next expected square
            if game.move_dir is not None:
                dr, dc = _DIR_DELTAS[game.move_dir]
                if game.move_path:
                    lr, lc = game.move_path[-1]
                else:
                    lr, lc = game.sel_rc
                nr, nc = lr + dr, lc + dc
                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                    sx, sy = self._cell_tl(nr, nc)
                    self.screen.blit(self._ov_leg, (sx, sy))

    # ── Side panel ──────────────────────────────────────────────────────

    def _draw_panel(self, game):
        px = self.panel_x
        # Title
        title = self.f_lg.render("TAK  6\u00D76", True, TXT)
        self.screen.blit(title, (px + 15, 15))
        pygame.draw.line(self.screen, BOARD_BORDER,
                         (px + 10, 50), (px + PANEL_W - 10, 50), 2)

        # Turn / game-over indicator
        y = 62
        if game.game_over:
            forced = getattr(game, '_forced_message', None)
            if forced:
                msg = forced
            elif game.winner is not None:
                wn = "WHITE" if game.winner == WHITE else "BLACK"
                wt = game.win_type or ""
                if wt == "road":
                    msg = f"{wn} WINS -- Road!"
                elif wt == "flat":
                    msg = f"{wn} WINS -- Flat count!"
                elif wt == "draw":
                    msg = "DRAW -- Equal flat counts!"
                else:
                    msg = f"{wn} WINS!"
            else:
                msg = "DRAW!"
            s = self.f_md.render(msg, True, WIN_GOLD)
            self.screen.blit(s, (px + 15, y))
            y += 24
            if game.online:
                you_won = game.winner == game.my_player
                sub = "You win!" if you_won else "You lose."
                rs = self.f_sm.render(f"{sub}  Q / Esc to leave",
                                      True, TXT_DIM)
            else:
                rs = self.f_sm.render("Press R to restart", True, TXT_DIM)
            self.screen.blit(rs, (px + 15, y))
            y += 22
        else:
            cp = game.turn
            pname = "WHITE" if cp == WHITE else "BLACK"
            tc = TURN_WHITE if cp == WHITE else TURN_BLACK
            turn_text = f"Turn {game.turn_number}:  {pname}"
            s = self.f_md.render(turn_text, True, tc)
            self.screen.blit(s, (px + 15, y))
            # Piece icon
            _draw_piece(self.screen, px + PANEL_W - 30, y + 10,
                        cp, FLAT, scale=0.7)
            y += 24
            if game.turn_number <= 2:
                opp = "BLACK" if cp == WHITE else "WHITE"
                note = self.f_sm.render(f"(place {opp}'s flat)",
                                        True, TXT_DIM)
                self.screen.blit(note, (px + 15, y))
            y += 20

        # Reserves
        pygame.draw.line(self.screen, BOARD_BORDER,
                         (px + 10, y), (px + PANEL_W - 10, y), 1)
        y += 8
        for p in (WHITE, BLACK):
            pk = str(p)
            res = game.state["reserves"][pk]
            pn = "White" if p == WHITE else "Black"
            c = TURN_WHITE if p == WHITE else TURN_BLACK
            nl = self.f_md.render(pn, True, c)
            self.screen.blit(nl, (px + 15, y))
            info = self.f_sm.render(
                f"Stones: {res['stones']}   Cap: {res['capstones']}",
                True, TXT_DIM)
            self.screen.blit(info, (px + 90, y + 3))
            y += 26

        # Separator
        y += 4
        pygame.draw.line(self.screen, BOARD_BORDER,
                         (px + 10, y), (px + PANEL_W - 10, y), 1)
        y += 8

        # Selected square info
        if game.sel_rc:
            r, c = game.sel_rc
            stack = game.state["board"][r][c]
            lbl = self.f_md.render(f"Selected: {sq_label(r, c)}", True, TXT)
            self.screen.blit(lbl, (px + 15, y))
            y += 22
            if stack:
                info = self.f_sm.render(f"Stack height: {len(stack)}",
                                        True, TXT_DIM)
                self.screen.blit(info, (px + 15, y))
                y += 18
                for i, piece in enumerate(stack):
                    owner = "W" if piece[0] == WHITE else "B"
                    tp = {FLAT: "flat", STANDING: "wall",
                          CAPSTONE: "cap"}[piece[1]]
                    tag = "TOP" if i == len(stack) - 1 else str(i + 1)
                    pc = TURN_WHITE if piece[0] == WHITE else TURN_BLACK
                    t = self.f_xs.render(f"  {tag}: {owner} {tp}", True, pc)
                    self.screen.blit(t, (px + 15, y))
                    y += 15
            else:
                self.screen.blit(self.f_sm.render("Empty square", True,
                                                   TXT_DIM),
                                 (px + 15, y))
                y += 18

        # Phase instructions
        y = max(y + 8, 350)
        if not game.game_over:
            phase_msg = {
                PH_IDLE: "Click a square to act",
                PH_PLACE_TYPE: "Choose piece to place:",
                PH_CARRY: "Choose how many to carry:",
                PH_DIRECTION: "Click adjacent square for direction",
                PH_DROPS: "",
            }
            msg = phase_msg.get(game.phase, "")
            if game.phase == PH_DROPS:
                rem = game.carry_count - sum(game.partial_drops)
                msg = f"Drop pieces ({rem} remaining):"
            if msg:
                self.screen.blit(self.f_sm.render(msg, True, TXT),
                                 (px + 15, y))
            y += 20

        # Buttons
        mx, my = pygame.mouse.get_pos()
        for btn in game.buttons:
            btn.draw(self.screen, self.f_md, mx, my)

        # Warning message
        if game.message:
            self.screen.blit(self.f_sm.render(game.message, True, TXT_WARN),
                             (px + 15, WIN_H - 70))

        # Cancel hint
        if game.phase != PH_IDLE and not game.game_over:
            self.screen.blit(
                self.f_xs.render("Right-click or Esc to cancel",
                                 True, TXT_DIM),
                (px + 15, WIN_H - 45))

    # ── Online overlays ─────────────────────────────────────────────────

    def _draw_online_status(self, game):
        if not game.game_over and not game.is_my_turn:
            wait = self.f_sm.render("Opponent's turn -- waiting...",
                                    True, TXT_DIM)
            self.screen.blit(wait, (PAD_LEFT, PAD_TOP - 24))

        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            bh = 60
            by = WIN_H // 2 - bh // 2
            pygame.draw.rect(self.screen, BG, (0, by, WIN_W, bh))
            msg = self.f_lg.render("Opponent disconnected", True, TXT)
            self.screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, by + 18)))
            sub = self.f_sm.render("Waiting for reconnection...",
                                   True, TXT_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, by + 42)))

        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_sm.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Tak in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
    net : client.network.NetworkClient
    my_player : int
    initial_state : dict
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
    pygame.display.set_caption("TAK 6\u00D76 \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        # ── Poll network ──────────────────────────────────────────
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

        # ── Events ────────────────────────────────────────────────
        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Try button click first
                    move = game.click_button(event.pos, renderer.panel_x)
                    if move is None:
                        hit = renderer.hit_test(*event.pos)
                        if hit is not None:
                            move = game.click(*hit, renderer.panel_x)
                        else:
                            game.deselect()
                    if move is not None:
                        net.send_move(move)
                elif event.button == 3:
                    game.deselect()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    game.deselect()
                else:
                    move = game.handle_key(event.key, renderer.panel_x)
                    if move is not None:
                        net.send_move(move)

        # ── Draw ──────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(60)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("TAK 6\u00D76")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    move = game.click_button(ev.pos, renderer.panel_x)
                    if move is None:
                        hit = renderer.hit_test(*ev.pos)
                        if hit:
                            game.click(*hit, renderer.panel_x)
                        else:
                            game.deselect()
                elif ev.button == 3:
                    game.deselect()
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_r and not game.online:
                    game.reset()
                elif ev.key == pygame.K_ESCAPE:
                    game.deselect()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped
                else:
                    game.handle_key(ev.key, renderer.panel_x)

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
