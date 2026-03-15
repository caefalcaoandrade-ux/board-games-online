"""
Entrapment -- Pygame display and local hotseat play (+ online multiplayer).

Two players on the same computer taking turns.
Controls: Left-click for all interactions. Esc to cancel current selection.
"""

import sys
import copy
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.entrapment_logic import (
        EntrapmentLogic, ROWS, COLS, BARRIERS_PER_PLAYER, DIRS,
        PLAYER_NAMES, COL_LABELS,
        legal_moves_for_roamer, forced_roamers,
        selectable_for_action1, selectable_for_action2_move,
        can_do_barrier_action,
        _iter_all_grooves, _iter_empty_grooves, _iter_player_resting,
        _get_barrier_by_groove, _in_bounds,
    )
except ImportError:
    from entrapment_logic import (
        EntrapmentLogic, ROWS, COLS, BARRIERS_PER_PLAYER, DIRS,
        PLAYER_NAMES, COL_LABELS,
        legal_moves_for_roamer, forced_roamers,
        selectable_for_action1, selectable_for_action2_move,
        can_do_barrier_action,
        _iter_all_grooves, _iter_empty_grooves, _iter_player_resting,
        _get_barrier_by_groove, _in_bounds,
    )

# ── Display Constants ────────────────────────────────────────────────────────

SQ   = 80                                   # square side (px)
GW   = 14                                   # groove width (px)
CELL = SQ + GW                              # pitch origin-to-origin
BOARD_PX = COLS * SQ + (COLS - 1) * GW      # 644

BOARD_X = 78                                # left margin for labels
BOARD_Y = 66                                # top margin for labels

INFO_X = BOARD_X + BOARD_PX + 34
INFO_W = 350
WIN_W  = INFO_X + INFO_W + 24
WIN_H  = BOARD_Y + BOARD_PX + 58

FPS = 60

# ── Colour palette ───────────────────────────────────────────────────────────

C_BG        = (38, 35, 32)
C_BOARD     = (162, 138, 104)
C_SQUARE    = (214, 196, 164)
C_SQ_HOVER  = (226, 212, 182)
C_GROOVE    = (145, 122, 92)
C_GRV_HOVER = (170, 150, 115)
C_INTERSECT = (138, 116, 88)

C_P0_ROAMER = (242, 230, 200)
C_P0_EDGE   = (175, 158, 120)
C_P1_ROAMER = (108, 52, 52)
C_P1_EDGE   = (60, 28, 28)

C_P0_REST   = (218, 188, 82)
C_P0_STAND  = (198, 165, 48)
C_P1_REST   = (148, 55, 78)
C_P1_STAND  = (122, 38, 58)

C_SEL       = (80, 190, 255)
C_VALID     = (88, 200, 110)
C_CAPTURE   = (230, 60, 60)
C_FORCED    = (255, 185, 50)

C_TEXT      = (232, 228, 218)
C_TEXT_DIM  = (150, 145, 136)
C_PANEL     = (52, 48, 44)
C_BTN       = (75, 70, 64)
C_BTN_HOV   = (95, 88, 80)
C_BTN_ACT   = (55, 128, 88)
C_BTN_DIS   = (55, 52, 48)
C_DIVIDER   = (80, 76, 70)

# Player display mappings (logic uses 1 and 2)
PLAYER_COLS  = {1: C_P0_ROAMER, 2: C_P1_ROAMER}
PLAYER_EDGES = {1: C_P0_EDGE,   2: C_P1_EDGE}


# ── UI Button ────────────────────────────────────────────────────────────────

class Btn:
    def __init__(self, x, y, w, h, label, aid):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.aid = aid
        self.hover = False
        self.active = False
        self.enabled = True

    def draw(self, surf, font):
        if not self.enabled:
            bg, fg = C_BTN_DIS, (88, 84, 78)
        elif self.active:
            bg, fg = C_BTN_ACT, C_TEXT
        elif self.hover:
            bg, fg = C_BTN_HOV, C_TEXT
        else:
            bg, fg = C_BTN, C_TEXT
        pygame.draw.rect(surf, bg, self.rect, border_radius=6)
        border = (105, 100, 92) if self.enabled else (62, 58, 54)
        pygame.draw.rect(surf, border, self.rect, 1, border_radius=6)
        ts = font.render(self.label, True, fg)
        surf.blit(ts, ts.get_rect(center=self.rect.center))


# ── Game Client ──────────────────────────────────────────────────────────────

class GameClient:
    """Client-side controller with multi-phase UI interaction.

    Wraps EntrapmentLogic and maintains local UI state (selection, mode,
    targets, highlights).  The authoritative game state is only updated
    when a complete action is committed through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = EntrapmentLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    # ── Setup ─────────────────────────────────────────────────────────────

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._cancel()
        self.cap_choices = []
        self.reloc_src = None

    def _cancel(self):
        self.selected = None
        self.valid_dests = []
        self.mode = "select"
        self.reloc_src = None

    # ── Online mode helpers ────────────────────────────────────────────

    @property
    def is_my_turn(self):
        """In online mode, True only when it's this player's turn."""
        if not self.online:
            return True
        return self.current_player == self.my_player

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._cancel()
        self.cap_choices = []
        self.reloc_src = None
        self.net_error = ""
        # If the new state has pending capture choices, enter that mode
        if self.pending_capture_choices is not None:
            self.cap_choices = [
                [p[0], p[1]] for p in self.pending_capture_choices]
            self.mode = "choose_cap"

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self.state["phase"] = "over"
        self.state["winner"] = winner
        if is_draw:
            self.state["status"] = "Game over -- Draw!"
        elif reason == "forfeit":
            wn = PLAYER_NAMES.get(winner, "Player {}".format(winner))
            self.state["status"] = "{} wins by forfeit!".format(wn)
        # Otherwise the status from the state is already correct

    # ── Properties (read by Renderer) ─────────────────────────────────────

    @property
    def phase(self):
        return self.state["phase"]

    @property
    def current_player(self):
        return self.state["current_player"]

    @property
    def action_num(self):
        return self.state["action_num"]

    @property
    def game_over(self):
        return self.state["phase"] == "over"

    @property
    def winner(self):
        return self.state["winner"]

    @property
    def status(self):
        return self.state["status"]

    @property
    def board(self):
        return self.state["board"]

    @property
    def roamers(self):
        return self.state["roamers"]

    @property
    def supply(self):
        return self.state["supply"]

    @property
    def captures(self):
        return self.state["captures"]

    @property
    def log(self):
        return self.state["log"]

    @property
    def pending_capture_choices(self):
        return self.state["pending_capture_choices"]

    # ── Groove/board queries delegated to logic helpers ────────────────────

    def iter_all_grooves(self):
        return _iter_all_grooves(self.state)

    def iter_empty_grooves(self):
        return _iter_empty_grooves(self.state)

    def iter_player_resting(self, player):
        return _iter_player_resting(self.state, player)

    def get_forced_roamers(self):
        return forced_roamers(self.state, self.current_player)

    def get_selectable_action1(self):
        return selectable_for_action1(self.state)

    def get_selectable_action2_move(self):
        return selectable_for_action2_move(self.state)

    def get_can_do_barrier_action(self):
        return can_do_barrier_action(self.state)

    def get_legal_moves_for_roamer(self, r, c, player):
        return legal_moves_for_roamer(self.state, r, c, player)

    # ── Click handling: Setup ─────────────────────────────────────────────

    def click_setup(self, r, c):
        if self.state["board"][r][c] is not None:
            return None
        move = {"setup_place": [r, c]}
        if self.online:
            return move
        self.state = self.logic.apply_move(
            self.state, self.state["current_player"], move)
        return None

    # ── Click handling: Capture choice ────────────────────────────────────

    def click_choose_cap(self, r, c):
        if self.pending_capture_choices is None:
            return None
        for choice in self.pending_capture_choices:
            if choice[0] == r and choice[1] == c:
                move = {"choose_capture": [r, c]}
                if self.online:
                    self.cap_choices = []
                    self.mode = "select"
                    return move
                self.state = self.logic.apply_move(
                    self.state, self.state["current_player"], move)
                self.cap_choices = []
                self.mode = "select"
                # Check if there are more pending captures
                if self.pending_capture_choices is not None:
                    self.cap_choices = [
                        [p[0], p[1]] for p in self.pending_capture_choices]
                    self.mode = "choose_cap"
                return None
        return None

    # ── Click handling: Roamer move ───────────────────────────────────────

    def click_select(self, sq, grv):
        """Handle clicks in default 'select' mode -- roamer move or auto-place.

        In online mode, returns the move dict to send to the server when
        a complete action is formed.  Returns None otherwise.
        """
        p = self.current_player

        if sq is not None:
            r, c = sq
            # If a roamer is already selected, try moving to the destination
            if self.selected is not None:
                dests = [[d[0], d[1]] for d in self.valid_dests]
                for d in dests:
                    if d[0] == r and d[1] == c:
                        move = {
                            "roamer_from": [self.selected[0], self.selected[1]],
                            "roamer_to": [r, c],
                            "barrier": None,
                        }
                        if self.online:
                            self.selected = None
                            self.valid_dests = []
                            return move
                        self.state = self.logic.apply_move(
                            self.state, self.state["current_player"], move)
                        self.selected = None
                        self.valid_dests = []
                        self._check_pending_captures()
                        return None
                # Click same roamer => deselect
                if r == self.selected[0] and c == self.selected[1]:
                    self.selected = None
                    self.valid_dests = []
                    return None

            # Try selecting a roamer
            if self.state["board"][r][c] == p:
                if self.action_num == 1:
                    ok = self.get_selectable_action1()
                else:
                    ok = self.get_selectable_action2_move()
                for s in ok:
                    if s[0] == r and s[1] == c:
                        self.selected = [r, c]
                        self.valid_dests = self.get_legal_moves_for_roamer(r, c, p)
                        return None

            # Click elsewhere => deselect
            self.selected = None
            self.valid_dests = []

        elif grv is not None and self.action_num == 2 and self.selected is None:
            # Convenience: clicking an empty groove in select mode auto-places
            gt, gr, gc = grv[0], grv[1], grv[2]
            val = _get_barrier_by_groove(self.state, gt, gr, gc)
            if val is None and self.supply[str(p)] > 0:
                move = {
                    "roamer_from": None,
                    "roamer_to": None,
                    "barrier": ["place", gt, gr, gc],
                }
                if self.online:
                    return move
                self.state = self.logic.apply_move(
                    self.state, self.state["current_player"], move)
                self._check_pending_captures()
        return None

    # ── Click handling: Barrier actions ───────────────────────────────────

    def click_place(self, grv):
        if grv is None:
            return None
        gt, gr, gc = grv[0], grv[1], grv[2]
        val = _get_barrier_by_groove(self.state, gt, gr, gc)
        if val is not None:
            return None
        move = {
            "roamer_from": None,
            "roamer_to": None,
            "barrier": ["place", gt, gr, gc],
        }
        if self.online:
            self.mode = "select"
            return move
        self.state = self.logic.apply_move(
            self.state, self.state["current_player"], move)
        self.mode = "select"
        self._check_pending_captures()
        return None

    def click_flip(self, grv):
        if grv is None:
            return None
        gt, gr, gc = grv[0], grv[1], grv[2]
        val = _get_barrier_by_groove(self.state, gt, gr, gc)
        if val is None or val[0] != self.current_player or val[1] != "resting":
            return None
        move = {
            "roamer_from": None,
            "roamer_to": None,
            "barrier": ["flip", gt, gr, gc],
        }
        if self.online:
            self.mode = "select"
            return move
        self.state = self.logic.apply_move(
            self.state, self.state["current_player"], move)
        self.mode = "select"
        self._check_pending_captures()
        return None

    def click_reloc_pick(self, grv):
        if grv is None:
            return
        gt, gr, gc = grv[0], grv[1], grv[2]
        val = _get_barrier_by_groove(self.state, gt, gr, gc)
        if val and val[0] == self.current_player and val[1] == "resting":
            self.reloc_src = [gt, gr, gc]
            self.mode = "reloc_place"

    def click_reloc_place(self, grv):
        if grv is None:
            return None
        gt, gr, gc = grv[0], grv[1], grv[2]
        val = _get_barrier_by_groove(self.state, gt, gr, gc)
        if val is not None:
            return None
        src = self.reloc_src
        if src:
            move = {
                "roamer_from": None,
                "roamer_to": None,
                "barrier": ["relocate", src[0], src[1], src[2], gt, gr, gc],
            }
            if self.online:
                self.reloc_src = None
                self.mode = "select"
                return move
            self.state = self.logic.apply_move(
                self.state, self.state["current_player"], move)
            self.reloc_src = None
            self.mode = "select"
            self._check_pending_captures()
        return None

    # ── Mode switching ────────────────────────────────────────────────────

    def set_mode(self, aid):
        self.selected = None
        self.valid_dests = []
        self.reloc_src = None
        table = {"move": "select", "place": "place",
                 "flip": "flip", "relocate": "reloc_pick"}
        self.mode = table.get(aid, "select")

    def cancel(self):
        self.selected = None
        self.valid_dests = []
        self.reloc_src = None
        if self.mode not in ("select", "choose_cap"):
            self.mode = "select"

    # ── Post-action helpers ───────────────────────────────────────────────

    def _check_pending_captures(self):
        if self.pending_capture_choices is not None:
            self.cap_choices = [
                [p[0], p[1]] for p in self.pending_capture_choices]
            self.mode = "choose_cap"
        else:
            self.selected = None
            self.valid_dests = []
            if self.mode != "choose_cap":
                self.mode = "select"


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self.phase = state["phase"]
        self.current_player = state["current_player"]
        self.action_num = state["action_num"]
        self.game_over = state["phase"] == "over"
        self.winner = state["winner"]
        self.status = state["status"]
        self.board = state["board"]
        self.roamers = state["roamers"]
        self.supply = state["supply"]
        self.captures = state["captures"]
        self.log = state["log"]
        self.pending_capture_choices = state.get("pending_capture_choices")
        self.selected = None
        self.valid_dests = []
        self.mode = "select"
        self.cap_choices = []
        self.reloc_src = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""

    def iter_all_grooves(self):
        return _iter_all_grooves(self.state)

    def iter_empty_grooves(self):
        return _iter_empty_grooves(self.state)

    def iter_player_resting(self, player):
        return _iter_player_resting(self.state, player)

    def get_forced_roamers(self):
        return forced_roamers(self.state, self.current_player)

    def get_selectable_action2_move(self):
        return selectable_for_action2_move(self.state)


# ── Rendering ────────────────────────────────────────────────────────────────

class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen
        self.font       = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 17)
        self.font_sm    = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 14)
        self.font_lg    = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 22, bold=True)
        self.font_coord = pygame.font.SysFont("Consolas,Courier New,monospace", 14, bold=True)
        self.font_title = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 26, bold=True)

        # action-2 buttons
        self.btn_move  = Btn(0, 0, 102, 32, "Move", "move")
        self.btn_place = Btn(0, 0, 102, 32, "Place", "place")
        self.btn_flip  = Btn(0, 0, 102, 32, "Flip", "flip")
        self.btn_reloc = Btn(0, 0, 102, 32, "Relocate", "relocate")
        self.btns_a2 = [self.btn_move, self.btn_place, self.btn_flip, self.btn_reloc]

        self.btn_new = Btn(INFO_X + 100, WIN_H - 50, 130, 34, "New Game", "restart")

        self.flipped = False
        self.hover_sq = None
        self.hover_grv = None

    # ── Pixel <-> grid ────────────────────────────────────────────────────

    def sq_xy(self, r, c):
        if self.flipped:
            return (BOARD_X + (COLS - 1 - c) * CELL,
                    BOARD_Y + (ROWS - 1 - r) * CELL)
        return (BOARD_X + c * CELL, BOARD_Y + r * CELL)

    def sq_center(self, r, c):
        x, y = self.sq_xy(r, c)
        return (x + SQ // 2, y + SQ // 2)

    def groove_rect(self, gt, gr, gc):
        if self.flipped:
            if gt == "h":
                fr, fc = ROWS - 1 - gr, COLS - 2 - gc
                return pygame.Rect(BOARD_X + fc * CELL + SQ,
                                   BOARD_Y + fr * CELL, GW, SQ)
            else:
                fr, fc = ROWS - 2 - gr, COLS - 1 - gc
                return pygame.Rect(BOARD_X + fc * CELL,
                                   BOARD_Y + fr * CELL + SQ, SQ, GW)
        if gt == "h":
            return pygame.Rect(BOARD_X + gc * CELL + SQ,
                               BOARD_Y + gr * CELL, GW, SQ)
        return pygame.Rect(BOARD_X + gc * CELL,
                           BOARD_Y + gr * CELL + SQ, SQ, GW)

    def px_to_sq(self, mx, my):
        for r in range(ROWS):
            for c in range(COLS):
                x, y = self.sq_xy(r, c)
                if x <= mx < x + SQ and y <= my < y + SQ:
                    return (r, c)
        return None

    def px_to_groove(self, mx, my, game):
        best, best_d = None, 9999
        for entry in game.iter_all_grooves():
            gt, r, c = entry[0], entry[1], entry[2]
            rect = self.groove_rect(gt, r, c)
            exp = rect.inflate(14, 14)
            if exp.collidepoint(mx, my):
                d = abs(mx - rect.centerx) + abs(my - rect.centery)
                if d < best_d:
                    best_d, best = d, (gt, r, c)
        return best

    # ── Hover update ──────────────────────────────────────────────────────

    def on_mousemove(self, mx, my, game):
        self.hover_sq = self.px_to_sq(mx, my)
        self.hover_grv = self.px_to_groove(mx, my, game)
        for b in self.btns_a2 + [self.btn_new]:
            b.hover = b.rect.collidepoint(mx, my)

    # ── Main draw ─────────────────────────────────────────────────────────

    def draw(self, game):
        scr = self.screen
        scr.fill(C_BG)

        # board frame
        frame = pygame.Rect(BOARD_X - 8, BOARD_Y - 8, BOARD_PX + 16, BOARD_PX + 16)
        pygame.draw.rect(scr, C_BOARD, frame, border_radius=5)

        # intersections
        for r in range(ROWS - 1):
            for c in range(COLS - 1):
                ix, iy = self.sq_xy(r, c)
                # intersection is at bottom-right of cell (r,c) in normal view
                if self.flipped:
                    pygame.draw.rect(scr, C_INTERSECT,
                        (ix - GW, iy - GW, GW, GW))
                else:
                    pygame.draw.rect(scr, C_INTERSECT,
                        (ix + SQ, iy + SQ, GW, GW))

        # grooves (highlight on hover when relevant)
        grv_mode = game.mode in ("place", "flip", "reloc_pick", "reloc_place")
        for entry in game.iter_all_grooves():
            gt, gr, gc, val = entry[0], entry[1], entry[2], entry[3]
            rect = self.groove_rect(gt, gr, gc)
            col = C_GROOVE
            if grv_mode and self.hover_grv == (gt, gr, gc):
                col = C_GRV_HOVER
            pygame.draw.rect(scr, col, rect)
            if val is not None:
                self._draw_barrier(scr, gt, gr, gc, val)

        # relocate-source highlight
        if game.mode == "reloc_place" and game.reloc_src:
            sgt, sr, sc = game.reloc_src[0], game.reloc_src[1], game.reloc_src[2]
            rect = self.groove_rect(sgt, sr, sc)
            hl = pygame.Surface(rect.size, pygame.SRCALPHA)
            hl.fill((255, 200, 60, 80))
            scr.blit(hl, rect.topleft)

        # squares
        for r in range(ROWS):
            for c in range(COLS):
                x, y = self.sq_xy(r, c)
                col = C_SQUARE
                if (self.hover_sq == (r, c) and game.phase == "setup"
                        and game.board[r][c] is None):
                    col = C_SQ_HOVER
                pygame.draw.rect(scr, col, (x, y, SQ, SQ), border_radius=3)

        # valid-move highlights
        for dest in game.valid_dests:
            dr, dc = dest[0], dest[1]
            cx, cy = self.sq_center(dr, dc)
            x, y = self.sq_xy(dr, dc)
            hl = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
            hl.fill((*C_VALID, 45))
            scr.blit(hl, (x, y))
            pygame.draw.circle(scr, C_VALID, (cx, cy), 10)

        # capture-choice highlights
        if game.mode == "choose_cap":
            for cap in game.cap_choices:
                cr, cc = cap[0], cap[1]
                x, y = self.sq_xy(cr, cc)
                hl = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                hl.fill((*C_CAPTURE, 65))
                scr.blit(hl, (x, y))
                pygame.draw.rect(scr, C_CAPTURE, (x, y, SQ, SQ), 3, border_radius=3)

        # roamers
        for player in [1, 2]:
            for pos in game.roamers[str(player)]:
                self._draw_roamer(scr, pos[0], pos[1], player)

        # selection ring
        if game.selected:
            cx, cy = self.sq_center(game.selected[0], game.selected[1])
            pygame.draw.circle(scr, C_SEL, (cx, cy), SQ // 2 - 5, 3)

        # forced-roamer outlines
        if game.phase == "play":
            for pos in game.get_forced_roamers():
                if game.selected is None or pos[0] != game.selected[0] or pos[1] != game.selected[1]:
                    cx, cy = self.sq_center(pos[0], pos[1])
                    pygame.draw.circle(scr, C_FORCED, (cx, cy), SQ // 2 - 3, 3)

        # coordinate labels
        for i in range(COLS):
            c_idx = (COLS - 1 - i) if self.flipped else i
            lbl = self.font_coord.render(COL_LABELS[c_idx], True, C_TEXT_DIM)
            cx = BOARD_X + i * CELL + SQ // 2 - lbl.get_width() // 2
            scr.blit(lbl, (cx, BOARD_Y - 24))
            scr.blit(lbl, (cx, BOARD_Y + BOARD_PX + 10))
        for i in range(ROWS):
            r_idx = (ROWS - i) if self.flipped else (i + 1)
            lbl = self.font_coord.render(str(r_idx), True, C_TEXT_DIM)
            ry = BOARD_Y + i * CELL + SQ // 2 - lbl.get_height() // 2
            scr.blit(lbl, (BOARD_X - 24, ry))
            scr.blit(lbl, (BOARD_X + BOARD_PX + 12, ry))

        # info panel
        self._draw_panel(scr, game)

        if game.online:
            self._draw_online_status(scr, game)

    # ── Roamer rendering ──────────────────────────────────────────────────

    def _draw_roamer(self, scr, r, c, player):
        cx, cy = self.sq_center(r, c)
        rad = SQ // 2 - 11
        fill = PLAYER_COLS[player]
        edge = PLAYER_EDGES[player]
        # shadow
        pygame.draw.circle(scr, (28, 26, 24), (cx + 2, cy + 3), rad)
        # body
        pygame.draw.circle(scr, fill, (cx, cy), rad)
        # specular highlight
        hl = tuple(min(255, v + 35) for v in fill)
        pygame.draw.circle(scr, hl, (cx - rad // 4, cy - rad // 4), rad // 3)
        # rim
        pygame.draw.circle(scr, edge, (cx, cy), rad, 2)

    # ── Barrier rendering ─────────────────────────────────────────────────

    def _draw_barrier(self, scr, gt, gr, gc, val):
        player, bstate = val[0], val[1]
        rect = self.groove_rect(gt, gr, gc)
        is_rest = bstate == "resting"
        if player == 1:
            col = C_P0_REST if is_rest else C_P0_STAND
        else:
            col = C_P1_REST if is_rest else C_P1_STAND

        if is_rest:
            # thin bar spanning the groove
            if gt == "h":
                bh = max(4, GW // 2 - 1)
                br = pygame.Rect(rect.x + 5, rect.centery - bh // 2, rect.w - 10, bh)
            else:
                bw = max(4, GW // 2 - 1)
                br = pygame.Rect(rect.centerx - bw // 2, rect.y + 5, bw, rect.h - 10)
            pygame.draw.rect(scr, col, br, border_radius=2)
            darker = tuple(max(0, v - 25) for v in col)
            pygame.draw.rect(scr, darker, br, 1, border_radius=2)
        else:
            # thick block with X marking
            if gt == "h":
                bh = GW - 2
                br = pygame.Rect(rect.x + 2, rect.centery - bh // 2, rect.w - 4, bh)
            else:
                bw = GW - 2
                br = pygame.Rect(rect.centerx - bw // 2, rect.y + 2, bw, rect.h - 4)
            pygame.draw.rect(scr, col, br, border_radius=2)
            bright = tuple(min(255, v + 50) for v in col)
            pygame.draw.rect(scr, bright, br, 2, border_radius=2)
            d = min(br.w, br.h) // 2 - 2
            if d >= 2:
                lc = tuple(min(255, v + 80) for v in col)
                pygame.draw.line(scr, lc, (br.centerx - d, br.centery - d),
                                 (br.centerx + d, br.centery + d), 2)
                pygame.draw.line(scr, lc, (br.centerx - d, br.centery + d),
                                 (br.centerx + d, br.centery - d), 2)

    # ── Info panel ────────────────────────────────────────────────────────

    def _draw_panel(self, scr, game):
        x0 = INFO_X
        y = 14

        # title
        scr.blit(self.font_title.render("ENTRAPMENT", True, C_TEXT), (x0, y))
        y += 40

        # current player
        pcol = PLAYER_COLS[game.current_player]
        pedge = PLAYER_EDGES[game.current_player]
        pygame.draw.circle(scr, pcol, (x0 + 12, y + 11), 10)
        pygame.draw.circle(scr, pedge, (x0 + 12, y + 11), 10, 2)
        scr.blit(self.font_lg.render(
            "{}'s Turn".format(PLAYER_NAMES[game.current_player]), True, C_TEXT),
            (x0 + 30, y))
        y += 34

        # status message
        for line in self._wrap(game.status, self.font, INFO_W - 10):
            scr.blit(self.font.render(line, True, C_TEXT), (x0, y))
            y += 20
        y += 6

        # sub-mode hint
        hints = {
            "place":       "Click an empty groove to place a barrier.",
            "flip":        "Click your resting barrier to flip it.",
            "reloc_pick":  "Click your resting barrier to pick up.",
            "reloc_place": "Click an empty groove to relocate barrier.",
            "choose_cap":  "Click an opponent roamer to capture.",
        }
        h = hints.get(game.mode)
        if h:
            scr.blit(self.font_sm.render(h, True, C_FORCED), (x0, y))
            y += 18
        y += 8

        # divider
        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 14

        # player stats
        for p in [1, 2]:
            pygame.draw.circle(scr, PLAYER_COLS[p], (x0 + 10, y + 9), 8)
            pygame.draw.circle(scr, PLAYER_EDGES[p], (x0 + 10, y + 9), 8, 1)
            txt = "{}   Barriers: {}   Roamers: {}/3".format(
                PLAYER_NAMES[p], game.supply[str(p)],
                len(game.roamers[str(p)]))
            scr.blit(self.font.render(txt, True, C_TEXT), (x0 + 26, y + 1))
            y += 28
        y += 6

        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 14

        # action-2 buttons
        if (game.phase == "play" and game.action_num == 2
                and game.mode != "choose_cap"):
            scr.blit(self.font.render("Action 2:", True, C_TEXT_DIM), (x0, y))
            y += 26
            self._layout_btns(y, game)
            for b in self.btns_a2:
                b.draw(scr, self.font)
            y += 78
        else:
            y += 8

        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 10

        # legend
        scr.blit(self.font_sm.render("Legend:", True, C_TEXT_DIM), (x0, y))
        y += 18
        # resting barrier sample
        pygame.draw.rect(scr, C_P0_REST, (x0 + 4, y + 2, 22, 5), border_radius=1)
        pygame.draw.rect(scr, C_P1_REST, (x0 + 32, y + 2, 22, 5), border_radius=1)
        scr.blit(self.font_sm.render("= Resting barrier (jumpable by owner)", True, C_TEXT_DIM),
                 (x0 + 60, y - 1))
        y += 16
        # standing barrier sample
        pygame.draw.rect(scr, C_P0_STAND, (x0 + 4, y, 22, 10), border_radius=1)
        pygame.draw.rect(scr, C_P1_STAND, (x0 + 32, y, 22, 10), border_radius=1)
        scr.blit(self.font_sm.render("= Standing barrier (permanent wall)", True, C_TEXT_DIM),
                 (x0 + 60, y + 1))
        y += 22

        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 10

        # game log
        scr.blit(self.font_sm.render("Game Log:", True, C_TEXT_DIM), (x0, y))
        y += 18
        max_lines = max(1, (WIN_H - 70 - y) // 16)
        for entry in game.log[-max_lines:]:
            scr.blit(self.font_sm.render(entry, True, C_TEXT_DIM), (x0 + 4, y))
            y += 16

        # new game button (local mode only)
        if not game.online:
            self.btn_new.draw(scr, self.font)

        # esc hint (local mode only — shared command panel handles online)
        if not game.online and (game.selected or game.mode not in ("select", "choose_cap")):
            scr.blit(self.font_sm.render("Esc to cancel", True, C_TEXT_DIM),
                     (x0, WIN_H - 16))

        # online role indicator
        if game.online:
            role = PLAYER_NAMES.get(game.my_player, "Player {}".format(game.my_player))
            accent = PLAYER_COLS.get(game.my_player, C_TEXT)
            tag = self.font_sm.render("You: {}".format(role), True, accent)
            scr.blit(tag, (x0, WIN_H - 32))

        # game-over overlay
        if game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            scr.blit(overlay, (0, 0))
            winner_col = PLAYER_COLS[game.winner] if game.winner is not None else C_TEXT
            msg = self.font_title.render(game.status, True, winner_col)
            scr.blit(msg, msg.get_rect(center=(BOARD_X + BOARD_PX // 2, WIN_H // 2 - 20)))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.font.render("{}  Q / Esc to leave".format(sub_text), True, (200, 200, 200))
            else:
                sub = self.font.render("Click  New Game  to play again.", True, (200, 200, 200))
            scr.blit(sub, sub.get_rect(center=(BOARD_X + BOARD_PX // 2, WIN_H // 2 + 18)))

    def _layout_btns(self, y, game):
        p = game.current_player
        gap = 8
        bx = INFO_X
        for i, b in enumerate(self.btns_a2):
            row, col = divmod(i, 2)
            b.rect.x = bx + col * (b.rect.w + gap)
            b.rect.y = y + row * (b.rect.h + gap)

        can_place = (game.supply[str(p)] > 0
                     and len(game.iter_empty_grooves()) > 0)
        has_rest  = len(game.iter_player_resting(p)) > 0
        can_reloc = (game.supply[str(p)] == 0
                     and has_rest
                     and len(game.iter_empty_grooves()) > 0)
        can_move  = len(game.get_selectable_action2_move()) > 0

        self.btn_move.enabled  = can_move
        self.btn_place.enabled = can_place
        self.btn_flip.enabled  = has_rest
        self.btn_reloc.enabled = can_reloc

        self.btn_move.active  = game.mode == "select"
        self.btn_place.active = game.mode == "place"
        self.btn_flip.active  = game.mode == "flip"
        self.btn_reloc.active = game.mode in ("reloc_pick", "reloc_place")

    def _wrap(self, text, font, maxw):
        words, lines, cur = text.split(), [], ""
        for w in words:
            test = cur + (" " if cur else "") + w
            if font.size(test)[0] <= maxw:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, scr, game):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            wait = self.font_sm.render(
                "Opponent's turn \u2014 waiting\u2026", True, C_TEXT_DIM)
            scr.blit(wait, (BOARD_X, 4))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            scr.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(scr, C_PANEL,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.font_lg.render("Opponent disconnected", True, C_TEXT)
            scr.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.font_sm.render(
                "Waiting for reconnection\u2026", True, C_TEXT_DIM)
            scr.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(scr, (60, 15, 15), bar)
            err = self.font_sm.render(game.net_error, True, (225, 75, 65))
            scr.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Entrapment in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
    net : client.network.NetworkClient
    my_player : int (1 or 2)
    initial_state : dict

    Does **not** call ``pygame.quit()``.
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
    pygame.display.set_caption("Entrapment \u2014 Online")
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

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if game.game_over:
                        running = False
                    else:
                        game.cancel()

            elif event.type == pygame.MOUSEMOTION:
                renderer.on_mousemove(*event.pos, game)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos

                if game.game_over:
                    continue
                if not game.is_my_turn:
                    continue

                move = None

                if game.phase == "setup":
                    sq = renderer.px_to_sq(mx, my)
                    if sq:
                        move = game.click_setup(sq[0], sq[1])

                elif game.mode == "choose_cap":
                    sq = renderer.px_to_sq(mx, my)
                    if sq:
                        move = game.click_choose_cap(sq[0], sq[1])

                elif game.action_num == 2:
                    btn_clicked = False
                    for b in renderer.btns_a2:
                        if b.rect.collidepoint(mx, my) and b.enabled:
                            game.set_mode(b.aid)
                            btn_clicked = True
                            break
                    if not btn_clicked:
                        sq = renderer.px_to_sq(mx, my)
                        grv = renderer.px_to_groove(mx, my, game)
                        if game.mode == "select":
                            move = game.click_select(sq, grv)
                        elif game.mode == "place":
                            move = game.click_place(grv)
                        elif game.mode == "flip":
                            move = game.click_flip(grv)
                        elif game.mode == "reloc_pick":
                            game.click_reloc_pick(grv)
                        elif game.mode == "reloc_place":
                            move = game.click_reloc_place(grv)
                else:
                    sq = renderer.px_to_sq(mx, my)
                    grv = renderer.px_to_groove(mx, my, game)
                    move = game.click_select(sq, grv)

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
        clock.tick(FPS)


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Entrapment")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif ev.type == pygame.MOUSEMOTION:
                renderer.on_mousemove(*ev.pos, game)

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos

                if renderer.btn_new.rect.collidepoint(mx, my):
                    game.reset()
                    continue

                if game.game_over:
                    continue

                if game.phase == "setup":
                    sq = renderer.px_to_sq(mx, my)
                    if sq:
                        game.click_setup(sq[0], sq[1])
                    continue

                if game.mode == "choose_cap":
                    sq = renderer.px_to_sq(mx, my)
                    if sq:
                        game.click_choose_cap(sq[0], sq[1])
                    continue

                # action-2 buttons
                if game.action_num == 2:
                    for b in renderer.btns_a2:
                        if b.rect.collidepoint(mx, my) and b.enabled:
                            game.set_mode(b.aid)
                            break
                    else:
                        # No button clicked, handle board click
                        sq = renderer.px_to_sq(mx, my)
                        grv = renderer.px_to_groove(mx, my, game)
                        if game.mode == "select":
                            game.click_select(sq, grv)
                        elif game.mode == "place":
                            game.click_place(grv)
                        elif game.mode == "flip":
                            game.click_flip(grv)
                        elif game.mode == "reloc_pick":
                            game.click_reloc_pick(grv)
                        elif game.mode == "reloc_place":
                            game.click_reloc_place(grv)
                    continue

                # action 1: only roamer move
                sq = renderer.px_to_sq(mx, my)
                grv = renderer.px_to_groove(mx, my, game)
                game.click_select(sq, grv)

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    game.cancel()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
