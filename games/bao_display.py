"""
Bao la Kiswahili -- Pygame display and local hotseat play.

Controls: Left-click to select a pit, pick direction, pick choice.
          Right-click to deselect. R to restart. F to flip board.
          Esc/Q to quit.
"""

import copy
import sys
import math

try:
    import games._suppress  # noqa: F401
except ImportError:
    try:
        import _suppress  # noqa: F401
    except ImportError:
        pass
import pygame

try:
    from games.bao_logic import (
        BaoGame, PLAYER_SOUTH, PLAYER_NORTH, NYUMBA_IDX, CW_TRACK, CCW_TRACK,
    )
except ImportError:
    from bao_logic import (
        BaoGame, PLAYER_SOUTH, PLAYER_NORTH, NYUMBA_IDX, CW_TRACK, CCW_TRACK,
    )

# ── Display Constants ────────────────────────────────────────────────────────

WIN_W = 1200
WIN_H = 780

WOOD_MED = (180, 120, 60)
WOOD_BORDER = (100, 65, 25)
WOOD_LIGHT = (210, 160, 90)
PIT_DARK = (90, 60, 25)
PIT_MED = (120, 80, 40)
PIT_SHADOW = (70, 45, 15)
SEED_COL = (200, 195, 180)
SEED_SHAD = (160, 155, 140)
SEED_HL = (230, 225, 210)
TEXT_L = (240, 230, 210)
TEXT_D = (80, 55, 25)
HL_GOLD = (255, 215, 0)
HL_GREEN = (100, 200, 100)
HL_RED = (220, 80, 80)
NYUMBA_ACC = (200, 160, 80)
BG = (45, 35, 25)
BTN_BG = (100, 70, 35)
BTN_HOV = (140, 100, 50)
BTN_TXT = (240, 230, 210)
CW_COL = (80, 180, 80)
CCW_COL = (80, 130, 220)
DIM_COL = (160, 155, 145)
ERR_COL = (225, 75, 65)


def _pk(player_id):
    """Return string key for a player id."""
    return str(player_id)


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller for Bao with multi-step move resolution."""

    def __init__(self, online=False, my_player=None):
        self.logic = BaoGame()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.undo_stack = []
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._sync()
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.pending_choices = []
        self.pending_ci = 0
        self.pending_filtered = []
        self.dir_options = []
        self.undo_stack = []
        self._game_over_status = None
        self._game_over_message = None

    def _sync(self):
        self.turn = self.state["turn"]
        self._status = self.logic.get_game_status(self.state)
        self._legal = self.logic.get_legal_moves(self.state, self.turn)

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_my_turn(self):
        if not self.online:
            return True
        return self.turn == self.my_player

    @property
    def game_over(self):
        if self._game_over_status is not None:
            return self._game_over_status["is_over"]
        return self._status["is_over"]

    @property
    def winner(self):
        if self._game_over_status is not None:
            return self._game_over_status["winner"]
        return self._status["winner"]

    @property
    def phase(self):
        pk = _pk(self.turn)
        if self.state[pk]["store"] > 0:
            return "kunamua"
        return "mtaji"

    def phase_for(self, player_id):
        pk = _pk(player_id)
        if self.state[pk]["store"] > 0:
            return "kunamua"
        return "mtaji"

    def store_for(self, player_id):
        return self.state[_pk(player_id)]["store"]

    def nyumba_owned_for(self, player_id):
        return self.state[_pk(player_id)]["nyumba_owned"]

    def front_row(self, player_id):
        return self.state[_pk(player_id)]["front"]

    def back_row(self, player_id):
        return self.state[_pk(player_id)]["back"]

    def pit_seeds(self, player_id, row, idx):
        return self.state[_pk(player_id)][row][idx]

    # ── State loading (online) ────────────────────────────────────────

    def load_state(self, state):
        self.state = state
        self._sync()
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.pending_choices = []
        self.dir_options = []
        self._game_over_status = None
        self._game_over_message = None
        self.net_error = ""

    def set_game_over(self, winner, is_draw=False, reason=""):
        self._game_over_status = {"is_over": True, "winner": winner,
                                  "is_draw": is_draw}
        if reason == "forfeit":
            name = "South" if winner == PLAYER_SOUTH else "North"
            self._game_over_message = f"{name} wins by forfeit!"
        else:
            self._game_over_message = None

    # ── Clickable pits ────────────────────────────────────────────────

    def clickable_pits(self):
        """Return set of (player_id, row, idx) that can be clicked."""
        cur = self.turn
        return {(cur, m.get("pit_row", "front"), m["pit_idx"])
                for m in self._legal}

    # ── Multi-step click handling ─────────────────────────────────────

    def click_pit(self, player_id, row, idx):
        """Handle clicking a pit. Returns a move dict in online mode when
        fully resolved, or None otherwise."""
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None
        if self.awaiting_dir or self.awaiting_choice:
            return None

        cur = self.turn
        if player_id != cur:
            return None

        matching = [m for m in self._legal
                    if m.get("pit_row", "front") == row and m["pit_idx"] == idx]
        if not matching:
            self.sel_pit = None
            self.filtered = []
            return None

        self.sel_pit = (player_id, row, idx)
        self.filtered = matching
        dirs = {m["direction"] for m in matching}
        if len(dirs) == 1:
            return self._resolve_direction(list(dirs)[0])
        else:
            self.awaiting_dir = True
            self.dir_options = sorted(dirs)
            return None

    def pick_direction(self, d):
        """Resolve direction choice. Returns move if fully resolved."""
        self.awaiting_dir = False
        self.dir_options = []
        return self._resolve_direction(d)

    def _resolve_direction(self, d):
        matching = [m for m in self.filtered if m["direction"] == d]
        if len(matching) == 1:
            return self._resolve_move(matching[0])
        elif matching:
            return self._present_choice(matching)
        else:
            self.sel_pit = None
            self.filtered = []
            return None

    def _present_choice(self, moves):
        max_ch = max(len(m.get("choices", [])) for m in moves)
        if max_ch == 0:
            return self._resolve_move(moves[0])
        for ci in range(max_ch):
            vals = set()
            for m in moves:
                ch = m.get("choices", [])
                vals.add(ch[ci] if ci < len(ch) else None)
            if len(vals) > 1:
                self.awaiting_choice = True
                self.pending_choices = []
                self.pending_ci = ci
                self.pending_filtered = moves
                labels = {"left": "\u2190 Left Kichwa", "right": "Right Kichwa \u2192",
                          "stop": "Stop (Nyumba)", "continue": "Safari \u2192"}
                for v in sorted(v2 for v2 in vals if v2 is not None):
                    self.pending_choices.append((v, labels.get(v, str(v))))
                return None
        return self._resolve_move(moves[0])

    def pick_choice(self, val):
        """Resolve a branching choice. Returns move if fully resolved."""
        self.awaiting_choice = False
        ci = self.pending_ci
        matching = [m for m in self.pending_filtered
                    if ci < len(m.get("choices", [])) and m["choices"][ci] == val]
        if len(matching) == 1:
            return self._resolve_move(matching[0])
        elif matching:
            return self._present_choice(matching)
        else:
            self.sel_pit = None
            self.filtered = []
            return None

    def _resolve_move(self, move):
        """Apply or return a fully resolved move."""
        if self.online:
            self.sel_pit = None
            self.filtered = []
            self.awaiting_dir = False
            self.awaiting_choice = False
            self.dir_options = []
            self.pending_choices = []
            return move
        # Local mode: apply immediately
        self.undo_stack.append(copy.deepcopy(self.state))
        self.state = self.logic.apply_move(self.state, self.turn, move)
        self._sync()
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.dir_options = []
        self.pending_choices = []
        return None

    def deselect(self):
        """Clear selection state."""
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.dir_options = []
        self.pending_choices = []

    def undo(self):
        if self.online:
            return
        if self.undo_stack:
            self.state = self.undo_stack.pop()
            self._sync()
            self.deselect()


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Read-only proxy for rendering a past state."""

    def __init__(self, state, game):
        self.state = state
        self.turn = state["turn"]
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        # No interaction possible
        self.sel_pit = None
        self.filtered = []
        self.awaiting_dir = False
        self.awaiting_choice = False
        self.pending_choices = []
        self.dir_options = []

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def phase(self):
        pk = _pk(self.turn)
        if self.state[pk]["store"] > 0:
            return "kunamua"
        return "mtaji"

    def phase_for(self, player_id):
        pk = _pk(player_id)
        if self.state[pk]["store"] > 0:
            return "kunamua"
        return "mtaji"

    def store_for(self, player_id):
        return self.state[_pk(player_id)]["store"]

    def nyumba_owned_for(self, player_id):
        return self.state[_pk(player_id)]["nyumba_owned"]

    def front_row(self, player_id):
        return self.state[_pk(player_id)]["front"]

    def back_row(self, player_id):
        return self.state[_pk(player_id)]["back"]

    def pit_seeds(self, player_id, row, idx):
        return self.state[_pk(player_id)][row][idx]

    def clickable_pits(self):
        return set()


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    """Draws the Bao board, pits, seeds, direction/choice buttons, and panels."""

    def __init__(self, screen):
        self.screen = screen
        self.flipped = False

        self.BX, self.BY = 60, 150
        self.BW, self.BH = 920, 460
        self.PR = 42
        self.SX = self.BW // 8
        self.SY = self.BH // 4

        self.font_title = pygame.font.SysFont("Georgia", 30, bold=True)
        self.font_med = pygame.font.SysFont("Georgia", 22)
        self.font_sm = pygame.font.SysFont("Georgia", 16)
        self.font_seed = pygame.font.SysFont("Georgia", 26, bold=True)
        self.font_lbl = pygame.font.SysFont("Georgia", 13)
        self.font_big = pygame.font.SysFont("Georgia", 40, bold=True)
        self.font_hint = pygame.font.SysFont("monospace", 13)

        self.dir_btns = []
        self.choice_btns = []

    # ── Coordinate mapping ────────────────────────────────────────────

    def _to_display(self, player_id, row, idx):
        """Map (player_id, row, idx) to display grid (dr, dc), accounting
        for flipped orientation."""
        if self.flipped:
            # When flipped, south is at top, north at bottom
            if player_id == PLAYER_SOUTH:
                return (0 if row == "back" else 1, 7 - idx)
            else:
                return (2 if row == "front" else 3, idx)
        else:
            # Normal: north at top, south at bottom
            if player_id == PLAYER_NORTH:
                return (0 if row == "back" else 1, 7 - idx)
            else:
                return (2 if row == "front" else 3, idx)

    def _pit_xy(self, dr, dc):
        return (self.BX + dc * self.SX + self.SX // 2,
                self.BY + dr * self.SY + self.SY // 2)

    def pit_from_px(self, mx, my):
        """Return (player_id, row, idx) for the pit nearest (mx, my),
        or None if not close enough."""
        for p in [PLAYER_SOUTH, PLAYER_NORTH]:
            for r in ["front", "back"]:
                for i in range(8):
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    if math.hypot(mx - cx, my - cy) <= self.PR + 5:
                        return (p, r, i)
        return None

    # ── Main draw ─────────────────────────────────────────────────────

    def draw(self, game, mouse_pos):
        scr = self.screen
        scr.fill(BG)

        # Title
        t = self.font_title.render("BAO LA KISWAHILI", True, TEXT_L)
        scr.blit(t, (WIN_W // 2 - t.get_width() // 2, 10))

        # Turn info
        cur = game.turn
        cur_name = "SOUTH" if cur == PLAYER_SOUTH else "NORTH"
        ph = game.phase.upper()
        info = f"{cur_name}'s turn  |  {ph}"
        if game.phase == "kunamua":
            info += f"  |  Store: {game.store_for(cur)}"
        col = HL_RED if game.game_over else HL_GOLD
        ts = self.font_med.render(info, True, col)
        scr.blit(ts, (WIN_W // 2 - ts.get_width() // 2, 48))

        # Side panel info
        self._draw_side_panel(game)

        # Board background
        pygame.draw.rect(scr, WOOD_MED,
                         (self.BX - 12, self.BY - 12,
                          self.BW + 24, self.BH + 24), border_radius=14)
        pygame.draw.rect(scr, WOOD_BORDER,
                         (self.BX - 12, self.BY - 12,
                          self.BW + 24, self.BH + 24), 3, border_radius=14)

        # Divider
        dy = self.BY + self.BH // 2
        pygame.draw.line(scr, WOOD_BORDER,
                         (self.BX - 8, dy), (self.BX + self.BW + 8, dy), 3)

        # Side labels (top/bottom of board)
        top_player = PLAYER_SOUTH if self.flipped else PLAYER_NORTH
        bot_player = PLAYER_NORTH if self.flipped else PLAYER_SOUTH
        top_name = "SOUTH" if top_player == PLAYER_SOUTH else "NORTH"
        bot_name = "SOUTH" if bot_player == PLAYER_SOUTH else "NORTH"
        nl = self.font_sm.render(top_name, True, WOOD_LIGHT)
        scr.blit(nl, (self.BX + self.BW // 2 - nl.get_width() // 2,
                       self.BY - nl.get_height() - 5))
        sl = self.font_sm.render(bot_name, True, WOOD_LIGHT)
        scr.blit(sl, (self.BX + self.BW // 2 - sl.get_width() // 2,
                       self.BY + self.BH + 5))

        clickable = game.clickable_pits() if not game.game_over else set()

        # Pits
        for p in [PLAYER_SOUTH, PLAYER_NORTH]:
            for r in ["front", "back"]:
                for i in range(8):
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    seeds = game.pit_seeds(p, r, i)
                    is_ny = (r == "front" and i == NYUMBA_IDX)
                    is_sel = (game.sel_pit == (p, r, i))
                    is_click = (p, r, i) in clickable
                    ny_owned = game.nyumba_owned_for(p)
                    self._draw_pit(cx, cy, seeds, is_ny, is_sel, is_click,
                                   ny_owned)

        # Pit labels
        for p in [PLAYER_SOUTH, PLAYER_NORTH]:
            for r in ["front", "back"]:
                for i in range(8):
                    dr, dc = self._to_display(p, r, i)
                    cx, cy = self._pit_xy(dr, dc)
                    prefix = "F" if r == "front" else "B"
                    lb = self.font_lbl.render(f"{prefix}{i+1}", True, TEXT_D)
                    # Labels below bottom-half pits, above top-half pits
                    if dr >= 2:
                        scr.blit(lb, (cx - lb.get_width() // 2,
                                      cy + self.PR + 4))
                    else:
                        scr.blit(lb, (cx - lb.get_width() // 2,
                                      cy - self.PR - 16))

        # Direction buttons
        self.dir_btns = []
        if game.awaiting_dir:
            self._draw_dir_btns(game, mouse_pos)

        # Choice buttons
        self.choice_btns = []
        if game.awaiting_choice:
            self._draw_choice_btns(game, mouse_pos)

        # Instructions
        if not game.game_over and not game.awaiting_dir and not game.awaiting_choice:
            if not game.sel_pit:
                inst = "Click a highlighted pit to start"
                its = self.font_sm.render(inst, True, TEXT_L)
                scr.blit(its, (self.BX, WIN_H - 35))

        # Game over overlay
        self._draw_game_over(game)

        # Online status overlays
        if game.online:
            self._draw_online_status(game)

    # ── Pit drawing ───────────────────────────────────────────────────

    def _draw_pit(self, cx, cy, seeds, is_ny, is_sel, is_click, ny_owned):
        scr = self.screen
        r = self.PR

        if is_sel:
            pygame.draw.circle(scr, HL_GOLD, (cx, cy), r + 6)
        elif is_click:
            tick = pygame.time.get_ticks() / 500.0
            alpha = int(140 + 80 * math.sin(tick * 3))
            s = pygame.Surface((r * 2 + 12, r * 2 + 12), pygame.SRCALPHA)
            pygame.draw.circle(s, (*HL_GREEN, min(255, alpha)),
                               (r + 6, r + 6), r + 4, 3)
            scr.blit(s, (cx - r - 6, cy - r - 6))

        if is_ny:
            rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.rect(scr, PIT_SHADOW, rect.inflate(4, 4),
                             border_radius=8)
            pygame.draw.rect(scr, PIT_DARK, rect, border_radius=8)
            pygame.draw.rect(scr, PIT_MED, rect.inflate(-6, -6),
                             border_radius=6)
            if ny_owned:
                nt = self.font_lbl.render("NYU", True, NYUMBA_ACC)
                scr.blit(nt, (cx - nt.get_width() // 2, cy - r + 3))
        else:
            pygame.draw.circle(scr, PIT_SHADOW, (cx + 2, cy + 2), r)
            pygame.draw.circle(scr, PIT_DARK, (cx, cy), r)
            pygame.draw.circle(scr, PIT_MED, (cx, cy), r - 4)

        if seeds > 0:
            if seeds <= 6:
                self._draw_dots(cx, cy, seeds)
            else:
                st = self.font_seed.render(str(seeds), True, SEED_COL)
                scr.blit(st, (cx - st.get_width() // 2,
                              cy - st.get_height() // 2 + (3 if is_ny else 0)))

    def _draw_dots(self, cx, cy, n):
        scr = self.screen
        sr = 6
        layouts = {
            1: [(0, 0)],
            2: [(-10, 0), (10, 0)],
            3: [(-10, -7), (10, -7), (0, 8)],
            4: [(-10, -8), (10, -8), (-10, 8), (10, 8)],
            5: [(-10, -10), (10, -10), (-10, 8), (10, 8), (0, 0)],
            6: [(-12, -10), (0, -10), (12, -10), (-12, 8), (0, 8), (12, 8)]
        }
        for dx, dy in layouts.get(n, [(0, 0)]):
            pygame.draw.circle(scr, SEED_SHAD, (cx+dx+1, cy+dy+1), sr)
            pygame.draw.circle(scr, SEED_COL, (cx+dx, cy+dy), sr)
            pygame.draw.circle(scr, SEED_HL, (cx+dx-2, cy+dy-2), 3)

    # ── Direction buttons ─────────────────────────────────────────────

    def _draw_dir_btns(self, game, mouse_pos):
        if not game.sel_pit:
            return
        p, r, i = game.sel_pit
        dr, dc = self._to_display(p, r, i)
        cx, cy = self._pit_xy(dr, dc)
        dirs = {m["direction"] for m in game.filtered}
        bw, bh = 65, 30
        # Place buttons below bottom-half pits, above top-half pits
        by = cy + self.PR + 25 if dr >= 2 else cy - self.PR - 55
        mx, my = mouse_pos
        if "cw" in dirs:
            rect = pygame.Rect(cx - bw - 5, by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, CW_COL if hov else (60, 140, 60),
                             rect, border_radius=6)
            lb = self.font_lbl.render("CW \u2192", True, TEXT_L)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                  rect.centery - lb.get_height() // 2))
            self.dir_btns.append((rect, "cw"))
        if "ccw" in dirs:
            rect = pygame.Rect(cx + 5, by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, CCW_COL if hov else (60, 100, 180),
                             rect, border_radius=6)
            lb = self.font_lbl.render("\u2190 CCW", True, TEXT_L)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                  rect.centery - lb.get_height() // 2))
            self.dir_btns.append((rect, "ccw"))

    # ── Choice buttons ────────────────────────────────────────────────

    def _draw_choice_btns(self, game, mouse_pos):
        bw, bh = 150, 36
        by = WIN_H - 115
        self.choice_btns = []
        total_w = len(game.pending_choices) * (bw + 10) - 10
        sx = WIN_W // 2 - total_w // 2
        mx, my = mouse_pos
        lbl = self.font_sm.render("Choose:", True, HL_GOLD)
        self.screen.blit(lbl, (WIN_W // 2 - lbl.get_width() // 2, by - 24))
        for j, (val, text) in enumerate(game.pending_choices):
            rect = pygame.Rect(sx + j * (bw + 10), by, bw, bh)
            hov = rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, BTN_HOV if hov else BTN_BG,
                             rect, border_radius=8)
            pygame.draw.rect(self.screen, HL_GOLD, rect, 2, border_radius=8)
            lb = self.font_sm.render(text, True, BTN_TXT)
            self.screen.blit(lb, (rect.centerx - lb.get_width() // 2,
                                  rect.centery - lb.get_height() // 2))
            self.choice_btns.append((rect, val))

    # ── Side panel ────────────────────────────────────────────────────

    def _draw_side_panel(self, game):
        sx = self.BX + self.BW + 25
        for p in [PLAYER_NORTH, PLAYER_SOUTH]:
            pname = "SOUTH" if p == PLAYER_SOUTH else "NORTH"
            pph = game.phase_for(p)
            ptxt = f"{pname}: {pph}"
            if pph == "kunamua":
                ptxt += f" ({game.store_for(p)})"
            if game.nyumba_owned_for(p):
                ptxt += " \u2302"
            sy = self.BY + (15 if p == (PLAYER_SOUTH if self.flipped else PLAYER_NORTH) else self.BH - 35)
            ps = self.font_sm.render(ptxt, True, TEXT_L)
            self.screen.blit(ps, (sx, sy))

        # Role indicator (online)
        if game.online:
            role = "South" if game.my_player == PLAYER_SOUTH else "North"
            accent = HL_GOLD
            ri = self.font_sm.render(f"You: {role}", True, accent)
            self.screen.blit(ri, (sx, self.BY + self.BH // 2 - 10))
        else:
            hint = self.font_hint.render("R: restart  U: undo  F: flip  Q: quit",
                                         True, (80, 78, 72))
            self.screen.blit(hint, (sx, self.BY + self.BH // 2 - 10))

    # ── Game over overlay ─────────────────────────────────────────────

    def _draw_game_over(self, game):
        if not game.game_over:
            return
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        self.screen.blit(ov, (0, 0))

        if game._game_over_message:
            msg = game._game_over_message
        elif game.winner == PLAYER_SOUTH:
            msg = "SOUTH WINS!"
        elif game.winner == PLAYER_NORTH:
            msg = "NORTH WINS!"
        else:
            msg = "Game Over"

        t = self.font_big.render(msg, True, HL_GOLD)
        bx = WIN_W // 2 - t.get_width() // 2
        by = WIN_H // 2 - t.get_height() // 2 - 16
        pad = 28
        box = pygame.Rect(bx - pad, by - pad,
                          t.get_width() + pad * 2,
                          t.get_height() + pad * 2 + 36)
        pygame.draw.rect(self.screen, (20, 20, 30), box, border_radius=12)
        pygame.draw.rect(self.screen, HL_GOLD, box, 2, border_radius=12)
        self.screen.blit(t, (bx, by))

        if game.online:
            sub = self.font_hint.render("Press Q to exit", True, DIM_COL)
        else:
            sub = self.font_hint.render("R: restart  Q: quit", True, DIM_COL)
        self.screen.blit(sub, (WIN_W // 2 - sub.get_width() // 2,
                               by + t.get_height() + 14))

    # ── Online status overlays ────────────────────────────────────────

    def _draw_online_status(self, game):
        if not game.game_over and not game.is_my_turn:
            wait = self.font_hint.render(
                "Opponent's turn \u2014 waiting\u2026", True, DIM_COL)
            self.screen.blit(wait, (self.BX, self.BY - 22))

        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            bh = 60
            by = WIN_H // 2 - bh // 2
            pygame.draw.rect(self.screen, BG, (0, by, WIN_W, bh))
            msg = self.font_med.render("Opponent disconnected", True, TEXT_L)
            self.screen.blit(msg, msg.get_rect(center=(WIN_W // 2, by + 18)))
            sub = self.font_hint.render(
                "Waiting for reconnection\u2026", True, DIM_COL)
            self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2, by + 42)))

        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.font_hint.render(game.net_error, True, ERR_COL)
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    try:
        from client.shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )
    except ImportError:
        from shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bao la Kiswahili \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        for msg in net.poll_messages():
            mtype = msg.get("type")
            if mtype == "move_made":
                game.load_state(msg["state"])
                hist.push(msg["state"])
            elif mtype == "game_over":
                game.load_state(msg["state"])
                hist.push(msg["state"])
                game.set_game_over(
                    msg.get("winner"), msg.get("is_draw", False),
                    msg.get("reason", ""))
            elif mtype == "player_disconnected":
                game.opponent_disconnected = True
            elif mtype == "player_reconnected":
                game.opponent_disconnected = False
            elif mtype == "error":
                game.net_error = msg.get("message", "Server error")
            elif mtype in ("connection_error", "connection_closed"):
                game.net_error = msg.get("message", "Connection lost")

        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game.game_over:
                    continue
                if event.button == 3:
                    game.deselect()
                    continue
                if event.button == 1:
                    mx, my = event.pos
                    # Check direction buttons first
                    if game.awaiting_dir:
                        btn_hit = False
                        for rect, d in renderer.dir_btns:
                            if rect.collidepoint(mx, my):
                                move = game.pick_direction(d)
                                if move is not None:
                                    net.send_move(move)
                                btn_hit = True
                                break
                        if btn_hit:
                            continue
                    # Check choice buttons
                    if game.awaiting_choice:
                        btn_hit = False
                        for rect, v in renderer.choice_btns:
                            if rect.collidepoint(mx, my):
                                move = game.pick_choice(v)
                                if move is not None:
                                    net.send_move(move)
                                btn_hit = True
                                break
                        if btn_hit:
                            continue
                    # Check pit click
                    pit = renderer.pit_from_px(mx, my)
                    if pit is not None:
                        p, r, i = pit
                        move = game.click_pit(p, r, i)
                        if move is not None:
                            net.send_move(move)

        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display, mouse_pos)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(60)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bao la Kiswahili")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        mouse_pos = pygame.mouse.get_pos()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit()
                    sys.exit()
                elif ev.key == pygame.K_r:
                    game.reset()
                elif ev.key == pygame.K_u:
                    game.undo()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 3:
                    game.deselect()
                elif ev.button == 1:
                    mx, my = ev.pos
                    # Check direction buttons first
                    if game.awaiting_dir:
                        btn_hit = False
                        for rect, d in renderer.dir_btns:
                            if rect.collidepoint(mx, my):
                                game.pick_direction(d)
                                btn_hit = True
                                break
                        if btn_hit:
                            continue
                    # Check choice buttons
                    if game.awaiting_choice:
                        btn_hit = False
                        for rect, v in renderer.choice_btns:
                            if rect.collidepoint(mx, my):
                                game.pick_choice(v)
                                btn_hit = True
                                break
                        if btn_hit:
                            continue
                    # Check pit click
                    pit = renderer.pit_from_px(mx, my)
                    if pit is not None:
                        p, r, i = pit
                        game.click_pit(p, r, i)

        renderer.draw(game, mouse_pos)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
