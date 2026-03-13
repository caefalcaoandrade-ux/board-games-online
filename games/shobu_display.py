"""
Shobu -- Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls: Left-click to select/move. Esc to deselect. U to undo passive.
          R to restart.

Board Layout::

       A (Dark)      B (Light)     <-- WHITE's homeboards
              -- ROPE --
       C (Light)     D (Dark)      <-- BLACK's homeboards

Coordinates: columns a-d (left to right), rows 4-1 (top to bottom)
"""

import copy
import sys
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.shobu_logic import (
        ShobuLogic, EMPTY, BLACK, WHITE, DARK_T, LITE_T,
        BOARD_TYPE, BOARD_NAME, HOME, DIRS, DIR_NAME,
        on_grid, dir_dist, opp_color_boards, dir_name_key,
        stone_counts,
        get_selectable_passive_stones, get_passive_destinations,
        get_selectable_aggressive_stones, get_aggressive_destination,
        compute_push_info,
    )
except ImportError:
    from shobu_logic import (
        ShobuLogic, EMPTY, BLACK, WHITE, DARK_T, LITE_T,
        BOARD_TYPE, BOARD_NAME, HOME, DIRS, DIR_NAME,
        on_grid, dir_dist, opp_color_boards, dir_name_key,
        stone_counts,
        get_selectable_passive_stones, get_passive_destinations,
        get_selectable_aggressive_stones, get_aggressive_destination,
        compute_push_info,
    )

# ── Display Constants ────────────────────────────────────────────────────────

CELL      = 90
BOARD_PX  = CELL * 4
GAP_X     = 80
GAP_Y     = 120
PAD_L     = 74
PAD_R     = 42
PAD_TOP   = 130
PAD_BOT   = 52

WIN_W = PAD_L + BOARD_PX * 2 + GAP_X + PAD_R
WIN_H = PAD_TOP + BOARD_PX * 2 + GAP_Y + PAD_BOT

# Palette
BG            = (34, 32, 36)
DARK_WOOD     = (142, 104, 68)
DARK_WOOD2    = (132,  95, 60)
LITE_WOOD     = (200, 172, 136)
LITE_WOOD2    = (190, 162, 126)
GRID_LINE     = (0, 0, 0)
BLACK_STONE   = (22, 22, 25)
WHITE_STONE   = (232, 228, 218)
SPEC_B        = (52, 52, 56)
SPEC_W        = (255, 255, 248)
ROPE_CLR      = (155, 138, 108)
SEL_RING      = (255, 210, 40)
VALID_FILL    = (60, 200, 80, 55)
VALID_DOT     = (50, 190, 70)
HINT_FILL     = (80, 170, 255, 40)
PUSH_FILL     = (255, 70, 50, 55)
PUSH_RING     = (255, 70, 50)
BORDER_NORM   = (65, 58, 50)
BORDER_HOME   = (70, 145, 220)
BORDER_AGG    = (220, 75, 65)
TXT           = (210, 210, 210)
TXT_DIM       = (135, 135, 135)
COORD_CLR     = (165, 158, 144)
LABEL_CLR     = (180, 172, 156)
WIN_GOLD      = (255, 215, 0)

# UI phase constants
PH_PSEL, PH_PDST, PH_ASEL, PH_ADST, PH_OVER = range(5)


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller with five-phase UI interaction.

    Wraps ShobuLogic and maintains local UI state (selection, phase,
    targets, highlights) that the Renderer reads each frame.  The
    authoritative game state is only updated when a complete move
    (passive + aggressive) is committed through the logic module.

    Phases:
        PH_PSEL  -- select stone for passive move
        PH_PDST  -- choose destination for passive move
        PH_ASEL  -- select stone for aggressive move
        PH_ADST  -- choose destination for aggressive move
        PH_OVER  -- game is over
    """

    def __init__(self, online=False, my_player=None):
        self.logic = ShobuLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.undo_stack = []
        self.reset()

    # ── Setup ─────────────────────────────────────────────────────────────

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._sync_boards()
        self.phase = PH_PSEL
        self.sel = None         # [board, row, col] or None
        self.pmove = None       # passive move record dict
        self.vstone = []        # list of [b, r, c] selectable stones
        self.vdest = []         # list of [b, r, c] valid destinations
        self.push_info = None   # push preview info dict or None
        self._pending_move = None  # accumulated move parts for online mode
        self._forced_message = None  # forced message from server (e.g. forfeit)
        self.undo_stack = []
        self._recompute_stones()

    def _sync_boards(self):
        """Copy authoritative boards for mutable display use."""
        self.boards = []
        for b in self.state["boards"]:
            self.boards.append([row[:] for row in b])

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def turn(self):
        return self.state["turn"]

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
        self._sync_boards()
        # Clear ALL UI selection state
        self.phase = PH_OVER if self._status["is_over"] else PH_PSEL
        self.sel = None
        self.pmove = None
        self.vstone = []
        self.vdest = []
        self.push_info = None
        self._pending_move = None
        if not self._status["is_over"]:
            self._recompute_stones()

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        self.phase = PH_OVER
        self.sel = None
        self.pmove = None
        self.vstone = []
        self.vdest = []
        self.push_info = None
        if is_draw:
            self._forced_message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            wn = "BLACK" if winner == BLACK else "WHITE"
            self._forced_message = f"{wn} wins by forfeit!"
        else:
            self._forced_message = None

    # ── Compute UI lists ──────────────────────────────────────────────────

    def _recompute_stones(self):
        self.vstone = []
        self.push_info = None
        if self.phase == PH_PSEL:
            self.vstone = get_selectable_passive_stones(self.boards, self.turn)
        elif self.phase == PH_ASEL and self.pmove:
            d = self.pmove["dir"]
            dist = self.pmove["dist"]
            self.vstone = get_selectable_aggressive_stones(
                self.boards, self.turn, self.pmove["board"], d, dist
            )

    def _recompute_dests(self):
        self.vdest = []
        self.push_info = None
        if self.sel is None:
            return
        b, r, c = self.sel
        if self.phase == PH_PDST:
            self.vdest = get_passive_destinations(self.boards, self.turn, b, r, c)
        elif self.phase == PH_ADST and self.pmove:
            d = self.pmove["dir"]
            dist = self.pmove["dist"]
            dest = get_aggressive_destination(self.boards, self.turn, b, r, c, d, dist)
            if dest is not None:
                self.vdest = [dest]
                self.push_info = compute_push_info(self.boards, self.turn, b, r, c, d, dist)

    # ── Click handling ────────────────────────────────────────────────────

    def click(self, b, r, c):
        """Handle a click on board cell (b, r, c).

        In online mode, returns the complete move dict (JSON-serializable)
        to send to the server when the final aggressive phase completes.
        Returns None otherwise or when the move is not yet complete.
        """
        if self.phase == PH_OVER:
            return None
        if self.online and not self.is_my_turn:
            return None

        if self.phase == PH_PSEL:
            if [b, r, c] in self.vstone:
                self.sel = [b, r, c]
                self.phase = PH_PDST
                self._recompute_dests()
            return None

        elif self.phase == PH_PDST:
            if [b, r, c] in self.vstone:
                self.sel = [b, r, c]
                self._recompute_dests()
                return None
            if [b, r, c] in self.vdest:
                sb, sr, sc = self.sel
                self._exec_passive(sb, sr, sc, r, c)
                if self.online:
                    # Store passive part for later assembly
                    self._pending_move = {
                        "passive_board": sb,
                        "passive_from": [sr, sc],
                        "passive_to": [r, c],
                    }
                self.sel = None
                self.vdest = []
                self.phase = PH_ASEL
                self._recompute_stones()
            return None

        elif self.phase == PH_ASEL:
            if [b, r, c] in self.vstone:
                self.sel = [b, r, c]
                self.phase = PH_ADST
                self._recompute_dests()
            return None

        elif self.phase == PH_ADST:
            if [b, r, c] in self.vstone:
                self.sel = [b, r, c]
                self._recompute_dests()
                return None
            if [b, r, c] in self.vdest:
                sb, sr, sc = self.sel
                if self.online:
                    # Assemble complete move from pending passive + aggressive
                    d = self.pmove["dir"]
                    dist = self.pmove["dist"]
                    tr = sr + d[0] * dist
                    tc = sc + d[1] * dist
                    move = {
                        "passive_board": self._pending_move["passive_board"],
                        "passive_from": self._pending_move["passive_from"],
                        "passive_to": self._pending_move["passive_to"],
                        "aggressive_board": b,
                        "aggressive_from": [sr, sc],
                        "aggressive_to": [tr, tc],
                    }
                    # Reset UI state; server will send authoritative state
                    self._pending_move = None
                    self.sel = None
                    self.pmove = None
                    self.vdest = []
                    self.vstone = []
                    self.push_info = None
                    # Restore boards to authoritative state (undo local passive)
                    self._sync_boards()
                    return move
                # Local mode: apply through logic
                self._exec_aggressive(sb, sr, sc)
        return None

    # ── Passive / aggressive execution (local board updates) ──────────────

    def _exec_passive(self, b, fr, fc, tr, tc):
        dd = dir_dist(fr, fc, tr, tc)
        d, dist = dd
        self.boards[b][fr][fc] = EMPTY
        self.boards[b][tr][tc] = self.turn
        self.pmove = {"board": b, "fr": fr, "fc": fc,
                      "tr": tr, "tc": tc, "dir": d, "dist": dist}

    def _exec_aggressive(self, b, fr, fc):
        d = self.pmove["dir"]
        dist = self.pmove["dist"]
        opp = WHITE if self.turn == BLACK else BLACK
        tr, tc = fr + d[0] * dist, fc + d[1] * dist

        # Build the complete move to commit through the logic module
        move = {
            "passive_board": self.pmove["board"],
            "passive_from": [self.pmove["fr"], self.pmove["fc"]],
            "passive_to": [self.pmove["tr"], self.pmove["tc"]],
            "aggressive_board": b,
            "aggressive_from": [fr, fc],
            "aggressive_to": [tr, tc],
        }

        # Commit through logic (validates and produces new state)
        self.state = self.logic.apply_move(self.state, self.turn, move)
        self._status = self.logic.get_game_status(self.state)
        self._sync_boards()

        if self._status["is_over"]:
            self.phase = PH_OVER
            self.sel = None
            self.vstone = []
            self.vdest = []
            self.push_info = None
            return

        # Next turn
        self.sel = None
        self.pmove = None
        self.vdest = []
        self.push_info = None
        self.phase = PH_PSEL
        self._recompute_stones()
        if not self.vstone:
            # Current player has no moves -- opponent wins
            self.phase = PH_OVER

    def undo_passive(self):
        if self.online:
            return
        if self.phase in (PH_ASEL, PH_ADST) and self.pmove:
            self._sync_boards()
            self.pmove = None
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_PSEL
            self._recompute_stones()

    def deselect(self):
        if self.phase == PH_PDST:
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_PSEL
            self._recompute_stones()
        elif self.phase == PH_ADST:
            self.sel = None
            self.vdest = []
            self.push_info = None
            self.phase = PH_ASEL
            self._recompute_stones()

    def stone_count(self, board_idx):
        """Return [black_count, white_count] for a board."""
        return stone_counts(self.boards, board_idx)


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen
        self.f_lg = pygame.font.SysFont("arial", 30, bold=True)
        self.f_md = pygame.font.SysFont("arial", 20)
        self.f_sm = pygame.font.SysFont("arial", 16)
        self.f_xs = pygame.font.SysFont("arial", 14)
        self.f_co = pygame.font.SysFont("arial", 15)

        self.bpos = [
            (PAD_L,                      PAD_TOP),
            (PAD_L + BOARD_PX + GAP_X,   PAD_TOP),
            (PAD_L,                      PAD_TOP + BOARD_PX + GAP_Y),
            (PAD_L + BOARD_PX + GAP_X,   PAD_TOP + BOARD_PX + GAP_Y),
        ]

    # ── Coordinate mapping ────────────────────────────────────────────────

    def hit_test(self, mx, my):
        """Return (board, row, col) for a pixel position, or None."""
        for i, (bx, by) in enumerate(self.bpos):
            if bx <= mx < bx + BOARD_PX and by <= my < by + BOARD_PX:
                c = (mx - bx) // CELL
                r = (my - by) // CELL
                if 0 <= r < 4 and 0 <= c < 4:
                    return (i, r, c)
        return None

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw(self, game):
        self.screen.fill(BG)
        self._draw_rope()
        for b in range(4):
            self._draw_board(game, b)
        self._draw_hud(game)
        if game.online:
            self._draw_online_status(game)
        pygame.display.flip()

    def _draw_rope(self):
        ry = PAD_TOP + BOARD_PX + GAP_Y // 2
        x0 = PAD_L - 8
        x1 = PAD_L + BOARD_PX * 2 + GAP_X + 8
        # rope line
        pygame.draw.line(self.screen, ROPE_CLR, (x0, ry), (x1, ry), 5)
        # knots
        mid = (x0 + x1) // 2
        for dx in (-10, 0, 10):
            pygame.draw.circle(self.screen, ROPE_CLR, (mid + dx, ry), 4)
        # side labels
        ws = self.f_sm.render("\u25B2 WHITE's side", True, TXT_DIM)
        bs = self.f_sm.render("\u25BC BLACK's side", True, TXT_DIM)
        self.screen.blit(ws, (x0 + 6, ry - 24))
        self.screen.blit(bs, (x0 + 6, ry + 9))

    def _draw_board(self, game, bi):
        bx, by = self.bpos[bi]
        dark = BOARD_TYPE[bi] == DARK_T
        c1 = DARK_WOOD  if dark else LITE_WOOD
        c2 = DARK_WOOD2 if dark else LITE_WOOD2
        ov = pygame.Surface((CELL, CELL), pygame.SRCALPHA)

        # border colour
        bc = BORDER_NORM
        if game.phase in (PH_PSEL, PH_PDST) and bi in HOME[game.turn]:
            bc = BORDER_HOME
        elif game.phase in (PH_ASEL, PH_ADST) and game.pmove:
            if bi in opp_color_boards(game.pmove["board"]):
                bc = BORDER_AGG
        bw = 3
        pygame.draw.rect(self.screen, bc,
                         (bx - bw, by - bw, BOARD_PX + 2 * bw, BOARD_PX + 2 * bw), bw)

        # cells
        for r in range(4):
            for c in range(4):
                x, y = bx + c * CELL, by + r * CELL
                pygame.draw.rect(self.screen, c1 if (r + c) % 2 == 0 else c2,
                                 (x, y, CELL, CELL))
                pygame.draw.rect(self.screen, GRID_LINE, (x, y, CELL, CELL), 1)

        # highlights -- selectable stones
        for vbrc in game.vstone:
            vb, vr, vc = vbrc
            if vb == bi:
                ov.fill(HINT_FILL)
                self.screen.blit(ov, (bx + vc * CELL, by + vr * CELL))

        # valid destinations
        for vbrc in game.vdest:
            vb, vr, vc = vbrc
            if vb == bi:
                ov.fill(VALID_FILL)
                self.screen.blit(ov, (bx + vc * CELL, by + vr * CELL))
                cx = bx + vc * CELL + CELL // 2
                cy = by + vr * CELL + CELL // 2
                pygame.draw.circle(self.screen, VALID_DOT, (cx, cy), 9)

        # push preview
        pi = game.push_info
        if pi and pi["board"] == bi:
            opr, opc = pi["opp_r"], pi["opp_c"]
            pdr, pdc = pi["dest_r"], pi["dest_c"]
            off = pi["off_board"]
            # highlight pushed stone
            ov.fill(PUSH_FILL)
            self.screen.blit(ov, (bx + opc * CELL, by + opr * CELL))
            # small X on push source
            cx = bx + opc * CELL + CELL // 2
            cy = by + opr * CELL + CELL // 2
            pygame.draw.line(self.screen, PUSH_RING, (cx-6, cy-6), (cx+6, cy+6), 2)
            pygame.draw.line(self.screen, PUSH_RING, (cx+6, cy-6), (cx-6, cy+6), 2)
            if not off:
                # ring where pushed stone lands
                px = bx + pdc * CELL + CELL // 2
                py = by + pdr * CELL + CELL // 2
                pygame.draw.circle(self.screen, PUSH_RING, (px, py), 12, 2)
            else:
                # arrow pointing off board edge
                ex = bx + opc * CELL + CELL // 2
                ey = by + opr * CELL + CELL // 2
                d = game.pmove["dir"]
                ax = ex + d[1] * CELL * 0.6
                ay = ey + d[0] * CELL * 0.6
                pygame.draw.line(self.screen, PUSH_RING, (ex, ey), (int(ax), int(ay)), 2)

        # stones
        for r in range(4):
            for c in range(4):
                v = game.boards[bi][r][c]
                if v == EMPTY:
                    continue
                cx = bx + c * CELL + CELL // 2
                cy = by + r * CELL + CELL // 2
                rad = CELL // 2 - 9

                # selection ring (behind stone)
                if game.sel == [bi, r, c]:
                    pygame.draw.circle(self.screen, SEL_RING, (cx, cy), rad + 5, 3)

                # shadow
                pygame.draw.circle(self.screen, (0, 0, 0), (cx + 2, cy + 2), rad)
                # body
                sc = BLACK_STONE if v == BLACK else WHITE_STONE
                pygame.draw.circle(self.screen, sc, (cx, cy), rad)
                # specular highlight
                sp = SPEC_B if v == BLACK else SPEC_W
                pygame.draw.circle(self.screen, sp,
                                   (cx - rad // 3, cy - rad // 3), max(rad // 4, 3))

        # coordinates
        for c in range(4):
            lbl = self.f_co.render(chr(ord("a") + c), True, COORD_CLR)
            self.screen.blit(lbl, (bx + c * CELL + CELL // 2 - lbl.get_width() // 2,
                                   by + BOARD_PX + 8))
        for r in range(4):
            lbl = self.f_co.render(str(4 - r), True, COORD_CLR)
            self.screen.blit(lbl, (bx - lbl.get_width() - 6,
                                   by + r * CELL + CELL // 2 - lbl.get_height() // 2))

        # board label + stone counts
        kind = "Dark" if dark else "Light"
        nm = self.f_md.render(f"{BOARD_NAME[bi]} ({kind})", True, LABEL_CLR)
        self.screen.blit(nm, (bx + 2, by - 30))

        bc_, wc_ = game.stone_count(bi)
        tag = self.f_sm.render(f"\u25CF{bc_}  \u25CB{wc_}", True, TXT_DIM)
        self.screen.blit(tag, (bx + BOARD_PX - tag.get_width() - 2, by - 28))

    def _draw_hud(self, game):
        pname = "BLACK" if game.turn == BLACK else "WHITE"

        if game.phase == PH_OVER:
            # Determine message
            forced = getattr(game, '_forced_message', None)
            if forced:
                msg = forced
            elif game.winner is not None:
                wn = "BLACK" if game.winner == BLACK else "WHITE"
                msg = f"{wn} WINS!"
            else:
                msg = "Game Over!"
            s = self.f_lg.render(msg, True, WIN_GOLD)
            self.screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 10))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                rs = self.f_sm.render(
                    f"{sub_text}  Press Esc to exit", True, TXT_DIM)
            else:
                rs = self.f_sm.render("Press R to restart", True, TXT_DIM)
            self.screen.blit(rs, (WIN_W // 2 - rs.get_width() // 2, 44))
            return

        # player icon
        sc = BLACK_STONE if game.turn == BLACK else WHITE_STONE
        pygame.draw.circle(self.screen, sc, (24, 28), 12)
        if game.turn == WHITE:
            pygame.draw.circle(self.screen, (0, 0, 0), (24, 28), 12, 1)

        tl = self.f_lg.render(f"{pname}'s Turn", True, TXT)
        self.screen.blit(tl, (44, 10))

        phase_msg = {
            PH_PSEL: "Select stone for PASSIVE move (on your homeboard)",
            PH_PDST: "Choose destination for PASSIVE move",
            PH_ASEL: "Select stone for AGGRESSIVE move (opposite-color board)",
            PH_ADST: "Choose destination for AGGRESSIVE move",
        }
        ms = self.f_sm.render(phase_msg.get(game.phase, ""), True, TXT_DIM)
        self.screen.blit(ms, (44, 46))

        # right-side key hints
        hints = []
        if game.phase in (PH_ASEL, PH_ADST) and not game.online:
            hints.append("[U] Undo passive")
        if game.phase in (PH_ASEL, PH_ADST) and game.pmove:
            dn = DIR_NAME[dir_name_key(game.pmove["dir"])]
            hints.append(f"Dir {dn} \u00B7 Dist {game.pmove['dist']}")
        if game.phase in (PH_PDST, PH_ADST):
            hints.append("[Esc] Deselect")
        if game.online:
            role = "Black" if game.my_player == BLACK else "White"
            hints.append(f"You: {role}")
        else:
            hints.append("[R] Restart")
        rx = WIN_W - 16
        for i, h in enumerate(hints):
            hs = self.f_sm.render(h, True, TXT_DIM)
            self.screen.blit(hs, (rx - hs.get_width(), 12 + i * 22))


    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            wait = self.f_sm.render(
                "Opponent's turn \u2014 waiting\u2026", True, TXT_DIM)
            self.screen.blit(wait, (12, PAD_TOP - 46))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, BG,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.f_lg.render("Opponent disconnected", True, TXT)
            self.screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.f_sm.render(
                "Waiting for reconnection\u2026", True, TXT_DIM)
            self.screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_sm.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Shobu in online multiplayer mode.

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
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("SHOBU \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

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
                hit = renderer.hit_test(*event.pos)
                if hit is None:
                    game.deselect()
                    continue
                move = game.click(*hit)
                if move is not None:
                    net.send_move(move)

        # ── Draw ────────────────────────────────────────────────────
        renderer.draw(game)
        clock.tick(60)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("SHOBU")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                hit = renderer.hit_test(*ev.pos)
                if hit:
                    game.click(*hit)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_r:
                    game.reset()
                elif ev.key == pygame.K_u:
                    game.undo_passive()
                elif ev.key == pygame.K_ESCAPE:
                    game.deselect()
        renderer.draw(game)
        clock.tick(60)


if __name__ == "__main__":
    main()
