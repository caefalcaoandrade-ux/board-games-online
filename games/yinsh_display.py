"""
YINSH -- Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls:
  Left-click     Select / confirm actions
  Right-click    Deselect / cancel
  Left / Right   Cycle through row choices (when resolving rows)
  N              New game
  Esc / Q        Quit
"""

import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.yinsh_logic import (
        YinshLogic, WHITE, BLACK,
        PHASE_PLACEMENT, PHASE_MAIN,
        ST_PLACE_RING, ST_SELECT_RING, ST_MOVE_RING,
        ST_CHOOSE_ROW, ST_REMOVE_RING, ST_GAME_OVER,
        VALID_POSITIONS, VALID_SET, BOARD_LINES, DIRECTIONS,
        SQRT3_2,
        _key, _from_key, _opp,
        is_valid_pos, compute_destinations, compute_jumped,
        find_rows, clabel,
    )
except ImportError:
    from yinsh_logic import (
        YinshLogic, WHITE, BLACK,
        PHASE_PLACEMENT, PHASE_MAIN,
        ST_PLACE_RING, ST_SELECT_RING, ST_MOVE_RING,
        ST_CHOOSE_ROW, ST_REMOVE_RING, ST_GAME_OVER,
        VALID_POSITIONS, VALID_SET, BOARD_LINES, DIRECTIONS,
        SQRT3_2,
        _key, _from_key, _opp,
        is_valid_pos, compute_destinations, compute_jumped,
        find_rows, clabel,
    )

# ════════════════════════════════════════════════════════════════════
#  DISPLAY CONSTANTS
# ════════════════════════════════════════════════════════════════════

WINDOW_W, WINDOW_H = 1200, 900
FPS = 60

HEX_SP   = 50          # pixel spacing between adjacent intersections
BOARD_CX = 465         # board centre x
BOARD_CY = 448         # board centre y

RING_R   = 19          # ring outer radius
RING_W   = 6           # ring annulus width
MARKER_R = 13          # marker filled-circle radius
DOT_R    = 3           # empty-intersection dot radius
CLICK_R  = HEX_SP * 0.44

PANEL_X  = 865
PANEL_W  = 315

# ─── colour palette ───────────────────────────────────────────────

BG            = (237, 233, 222)
GRID_LINE_C   = (200, 196, 186)
GRID_DOT_C    = (175, 170, 160)
LABEL_C       = (140, 135, 125)

# pieces — white player
W_RING_FILL   = (220, 216, 208)
W_RING_EDGE   = (150, 146, 138)
W_MARKER_FILL = (248, 246, 238)
W_MARKER_EDGE = (175, 172, 164)

# pieces — black player
B_RING_FILL   = (52, 52, 58)
B_RING_EDGE   = (25, 25, 28)
B_MARKER_FILL = (40, 40, 46)
B_MARKER_EDGE = (20, 20, 22)

# highlights
HL_VALID      = (80, 190, 105, 150)    # valid-move dot
HL_SELECT     = (255, 210, 45)         # selected-ring glow
HL_ROW        = (220, 60, 55)          # active candidate row
HL_ROW_ALT    = (255, 160, 55)         # other candidate rows
HL_RING_REM   = (175, 55, 195)         # removable-ring glow
HL_LAST       = (130, 175, 230, 100)   # last-move feedback

# panel
PANEL_BG      = (227, 223, 213)
PANEL_BORDER  = (200, 196, 186)
TXT_DARK      = (42, 40, 36)
TXT_MID       = (115, 111, 103)
TXT_LIGHT     = (160, 156, 148)
TAG_W         = (210, 206, 198)
TAG_B         = (58, 56, 52)
ACCENT_W      = (180, 176, 168)
ACCENT_B      = (90, 88, 82)


# ════════════════════════════════════════════════════════════════════
#  HEXAGONAL BOARD GEOMETRY (display helpers)
# ════════════════════════════════════════════════════════════════════

def h2p(q, r):
    """Axial hex → pixel."""
    return (BOARD_CX + HEX_SP * (q + r * 0.5),
            BOARD_CY - HEX_SP * r * SQRT3_2)


def p2h(mx, my, flipped=False):
    """Pixel → nearest valid hex (or None if too far)."""
    if flipped:
        mx = 2 * BOARD_CX - mx
        my = 2 * BOARD_CY - my
    rf = (BOARD_CY - my) / (HEX_SP * SQRT3_2)
    qf = (mx - BOARD_CX) / HEX_SP - rf * 0.5
    sf = -qf - rf
    rq, rr, rs = round(qf), round(rf), round(sf)
    dq, dr, ds = abs(rq - qf), abs(rr - rf), abs(rs - sf)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    k = _key(rq, rr)
    if k in VALID_SET:
        px, py = h2p(rq, rr)
        if math.hypot(mx - px, my - py) < CLICK_R:
            return [rq, rr]
    return None


# precompute grid drawing data
def _grid_segs():
    segs = []
    for pos in VALID_POSITIONS:
        q, r = pos[0], pos[1]
        for dq, dr in [(1, 0), (0, 1), (1, -1)]:
            nk = _key(q + dq, r + dr)
            if nk in VALID_SET:
                segs.append((h2p(q, r), h2p(q + dq, r + dr)))
    return segs


def _edge_labels():
    col_lbl = {}
    for q in range(-5, 6):
        pts = [pos for pos in VALID_POSITIONS if pos[0] == q]
        if not pts:
            continue
        top = max(pts, key=lambda p: p[1])
        px, py = h2p(top[0], top[1])
        col_lbl[chr(65 + q + 5)] = (px, py - 26)

    row_lbl = {}
    r_values = {}
    for pos in VALID_POSITIONS:
        r_values[pos[1] + 6] = True
    for rn in sorted(r_values.keys()):
        r_ax = rn - 6
        pts = [pos for pos in VALID_POSITIONS if pos[1] == r_ax]
        if not pts:
            continue
        left = min(pts, key=lambda p: h2p(p[0], p[1])[0])
        px, py = h2p(left[0], left[1])
        row_lbl[str(rn)] = (px - 24, py)
    return col_lbl, row_lbl


GRID_SEGS = _grid_segs()
COL_LBL, ROW_LBL = _edge_labels()


# ════════════════════════════════════════════════════════════════════
#  GAME CLIENT
# ════════════════════════════════════════════════════════════════════

class GameClient:
    """Client-side controller with six-state UI interaction.

    Wraps YinshLogic and maintains local UI state (selection, phase,
    targets, row choices, highlights) that the Renderer reads each frame.
    The authoritative game state is only updated when a complete atomic
    move is committed through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = YinshLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.reset()

    # ── Setup ─────────────────────────────────────────────────────────

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._cancel()
        self.hover = None
        self.last_marker = None
        self.last_dest = None
        # For multi-step move building
        self._pending_ring = None
        self._pending_dest = None
        self._pending_remove_seqs = []
        self._pending_opp_remove_seqs = []
        # Simulated state for row resolution display
        self._sim_rings = None
        self._sim_markers = None
        # Online mode: completed move waiting to be sent
        self._online_pending_move = None

    def _cancel(self):
        self.sel = None
        self.vmoves = []
        self.crows = []
        self.crow_i = 0
        self.rplayer = None
        self.ui_sub_state = None
        self._pending_ring = None
        self._pending_dest = None
        self._pending_remove_seqs = []
        self._pending_opp_remove_seqs = []
        self._sim_rings = None
        self._sim_markers = None
        self._last_resolved_row = None
        self._online_pending_move = None

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
        self._cancel()
        self.hover = None
        self.last_marker = None
        self.last_dest = None
        self.net_error = ""
        self._sim_rings = None
        self._sim_markers = None

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self.state["sub_state"] = ST_GAME_OVER
            self.state["is_draw"] = True
        elif reason == "forfeit":
            self.state["sub_state"] = ST_GAME_OVER
            self.state["winner"] = winner
        else:
            self.state["sub_state"] = ST_GAME_OVER
            self.state["winner"] = winner

    # ── Properties (read by Renderer) ─────────────────────────────────

    @property
    def rings(self):
        if self._sim_rings is not None:
            return self._sim_rings
        return self.state["rings"]

    @property
    def markers(self):
        if self._sim_markers is not None:
            return self._sim_markers
        return self.state["markers"]

    @property
    def pool(self):
        return self.state["pool"]

    @property
    def removed(self):
        return self.state["removed"]

    @property
    def placed(self):
        return self.state["placed"]

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def phase(self):
        return self.state["phase"]

    @property
    def sub_state(self):
        if self.ui_sub_state is not None:
            return self.ui_sub_state
        return self.state["sub_state"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def is_draw(self):
        return self._status["is_draw"]

    @property
    def pname(self):
        return "White" if self.turn == WHITE else "Black"

    @property
    def rname(self):
        if self.rplayer is None:
            return self.pname
        return "White" if self.rplayer == WHITE else "Black"

    @property
    def status(self):
        sub = self.sub_state
        if sub == ST_GAME_OVER:
            if self.is_draw:
                return "Game over  \u2014  Draw!"
            w = "White" if self.winner == WHITE else "Black"
            return "Game over  \u2014  {} wins!".format(w)
        if sub == ST_PLACE_RING:
            n = 5 - self.state["placed"][str(self.turn)]
            return "{}: place a ring ({} left)".format(self.pname, n)
        if sub == ST_SELECT_RING:
            return "{}: select one of your rings".format(self.pname)
        if sub == ST_MOVE_RING:
            return "{}: move ring to a green spot  (right-click to cancel)".format(self.pname)
        if sub == ST_CHOOSE_ROW:
            n = len(self.crows)
            hint = "  [left/right to cycle]" if n > 1 else ""
            return "{}: click a highlighted row to remove{}".format(self.rname, hint)
        if sub == ST_REMOVE_RING:
            return "{}: click one of your rings to remove it".format(self.rname)
        return ""

    # ── Click handling ────────────────────────────────────────────────

    def click(self, pos):
        """Handle a click on board position *pos* ([q, r] or None).

        In online mode, returns the complete move dict to send to the
        server instead of applying it locally.  Returns None otherwise.
        """
        if pos is None or self.sub_state == ST_GAME_OVER:
            return None
        if self.online and not self.is_my_turn:
            # During row/ring removal for the opponent (rplayer != turn),
            # we still allow interaction because the *active* player is
            # building the move that includes opponent removal sequences.
            # But if the basic turn check fails and we're not mid-move, skip.
            if self._pending_ring is None:
                return None

        self._online_pending_move = None

        sub = self.sub_state
        if sub == ST_PLACE_RING:
            self._do_place(pos)
        elif sub == ST_SELECT_RING:
            self._do_select(pos)
        elif sub == ST_MOVE_RING:
            self._do_move(pos)
        elif sub == ST_CHOOSE_ROW:
            self._do_choose_row(pos)
        elif sub == ST_REMOVE_RING:
            self._do_remove_ring(pos)

        return self._online_pending_move

    def rclick(self):
        if self.sub_state == ST_MOVE_RING:
            self.sel = None
            self.vmoves = []
            self.ui_sub_state = ST_SELECT_RING

    def cycle(self, d):
        if self.sub_state == ST_CHOOSE_ROW and len(self.crows) > 1:
            self.crow_i = (self.crow_i + d) % len(self.crows)

    # ── Placement ─────────────────────────────────────────────────────

    def _do_place(self, pos):
        q, r = pos[0], pos[1]
        k = _key(q, r)
        rings = self.state["rings"]
        markers = self.state["markers"]
        if k in VALID_SET and k not in rings and k not in markers:
            move = {"type": "place_ring", "pos": [q, r]}
            if self.online:
                # Don't apply locally — send to server
                self._cancel()
                self._online_pending_move = move
                return
            self.state = self.logic.apply_move(self.state, self.turn, move)
            self._status = self.logic.get_game_status(self.state)
            self._cancel()

    # ── Ring selection ────────────────────────────────────────────────

    def _do_select(self, pos):
        q, r = pos[0], pos[1]
        k = _key(q, r)
        rings = self.state["rings"]
        if k in rings and rings[k] == self.turn:
            dests = compute_destinations(rings, self.state["markers"], q, r)
            if dests:
                self.sel = [q, r]
                self.vmoves = dests
                self.ui_sub_state = ST_MOVE_RING

    # ── Ring movement ─────────────────────────────────────────────────

    def _do_move(self, pos):
        q, r = pos[0], pos[1]
        k = _key(q, r)

        # Click on selected ring = deselect
        if self.sel and q == self.sel[0] and r == self.sel[1]:
            self.rclick()
            return

        # Click another of player's rings = reselect
        rings = self.state["rings"]
        if k in rings and rings[k] == self.turn:
            dests = compute_destinations(rings, self.state["markers"], q, r)
            if dests:
                self.sel = [q, r]
                self.vmoves = dests
            return

        # Check if destination is valid
        if [q, r] not in self.vmoves:
            return

        origin = self.sel
        oq, orr = origin[0], origin[1]

        # Simulate the move locally for row resolution display
        sim_rings = {}
        for sk, sv in self.state["rings"].items():
            sim_rings[sk] = sv
        sim_markers = {}
        for sk, sv in self.state["markers"].items():
            sim_markers[sk] = sv

        origin_k = _key(oq, orr)
        dest_k = _key(q, r)

        # Place marker at origin
        sim_markers[origin_k] = self.turn

        # Move ring
        del sim_rings[origin_k]
        sim_rings[dest_k] = self.turn

        # Flip jumped markers
        jumped = compute_jumped(oq, orr, q, r)
        for jp in jumped:
            jk = _key(jp[0], jp[1])
            if jk in sim_markers:
                sim_markers[jk] = _opp(sim_markers[jk])

        self._sim_rings = sim_rings
        self._sim_markers = sim_markers
        self._pending_ring = [oq, orr]
        self._pending_dest = [q, r]
        self._pending_remove_seqs = []
        self._pending_opp_remove_seqs = []
        self.sel = None
        self.vmoves = []

        self.last_marker = [oq, orr]
        self.last_dest = [q, r]

        # Check for rows - active player first
        self.rplayer = self.turn
        self._enter_row_check()

    def _enter_row_check(self):
        """Check for rows of 5 for the current rplayer."""
        rows = find_rows(self._sim_markers, self.rplayer)
        if rows:
            self.crows = rows
            self.crow_i = 0
            self.ui_sub_state = ST_CHOOSE_ROW
        elif self.rplayer == self.turn:
            # No rows for active player, check opponent
            self.rplayer = _opp(self.turn)
            self._enter_row_check()
        else:
            # No rows for anyone, commit the move
            self._commit_move()

    def _do_choose_row(self, pos):
        q, r = pos[0], pos[1]
        # Check if clicked position is in any candidate row
        for i, row in enumerate(self.crows):
            for rpos in row:
                if rpos[0] == q and rpos[1] == r:
                    self.crow_i = i
                    self._resolve_row()
                    return
        # If only one row, click anywhere to confirm
        if len(self.crows) == 1:
            self._resolve_row()

    def _do_remove_ring(self, pos):
        q, r = pos[0], pos[1]
        k = _key(q, r)
        if k not in self._sim_rings or self._sim_rings[k] != self.rplayer:
            return

        # Remove ring from simulation
        del self._sim_rings[k]

        # Build the removal record using the row stored by _resolve_row
        seq_entry = {"row": self._last_resolved_row, "ring": [q, r]}

        if self.rplayer == self.turn:
            self._pending_remove_seqs.append(seq_entry)
        else:
            self._pending_opp_remove_seqs.append(seq_entry)

        # Check if this player won (3 rings removed)
        removed_count = self.state["removed"][str(self.rplayer)]
        if self.rplayer == self.turn:
            removed_count += len(self._pending_remove_seqs)
        else:
            removed_count += len(self._pending_opp_remove_seqs)

        if removed_count >= 3:
            # Commit the winning move
            self._commit_move()
            return

        # Check for more rows
        self._enter_row_check()

    def _resolve_row(self):
        """Remove the selected row's markers from simulation."""
        row = self.crows[self.crow_i]
        # Store the row for when ring is removed
        self._last_resolved_row = []
        for pos in row:
            self._last_resolved_row.append([pos[0], pos[1]])
        for pos in row:
            pk = _key(pos[0], pos[1])
            if pk in self._sim_markers:
                del self._sim_markers[pk]
        self.crows = []
        self.ui_sub_state = ST_REMOVE_RING

    def _commit_move(self):
        """Build and apply the atomic move through the logic module."""
        move = {
            "type": "move",
            "ring": self._pending_ring,
            "dest": self._pending_dest,
        }
        if self._pending_remove_seqs:
            move["remove_sequences"] = self._pending_remove_seqs
        if self._pending_opp_remove_seqs:
            move["opp_remove_sequences"] = self._pending_opp_remove_seqs

        if self.online:
            # Don't apply locally — store for caller to send to server
            self._cancel()
            self._online_pending_move = move
            return

        player = self.state["turn"]
        self.state = self.logic.apply_move(self.state, player, move)
        self._status = self.logic.get_game_status(self.state)

        # Preserve last move info
        last_m = self.last_marker
        last_d = self.last_dest

        self._cancel()

        self.last_marker = last_m
        self.last_dest = last_d


# ════════════════════════════════════════════════════════════════════
#  RENDERER
# ════════════════════════════════════════════════════════════════════

class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.rings = state["rings"]
        self.markers = state["markers"]
        self.pool = state["pool"]
        self.removed = state["removed"]
        self.placed = state["placed"]
        self.turn = state["turn"]
        self.phase = state["phase"]
        self.sub_state = state["sub_state"]
        self._status = game.logic.get_game_status(state)
        self.sel = None
        self.vmoves = []
        self.crows = []
        self.crow_i = 0
        self.rplayer = None
        self.hover = None
        self.last_marker = None
        self.last_dest = None
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

    @property
    def is_draw(self):
        return self._status.get("is_draw", False)

    @property
    def pname(self):
        return "White" if self.turn == WHITE else "Black"

    @property
    def rname(self):
        return self.pname

    @property
    def status(self):
        if self.sub_state == ST_GAME_OVER:
            if self.is_draw:
                return "Game over  \u2014  Draw!"
            w = "White" if self.winner == WHITE else "Black"
            return "Game over  \u2014  {} wins!".format(w)
        return "{}'s turn".format(self.pname)


class Renderer:
    def __init__(self, surf):
        self.s = surf
        self.flipped = False
        pygame.font.init()
        self.f_sm = pygame.font.SysFont("consolas", 14)
        self.f_md = pygame.font.SysFont("consolas", 16, bold=True)
        self.f_lg = pygame.font.SysFont("consolas", 21, bold=True)
        self.f_xl = pygame.font.SysFont("consolas", 34, bold=True)

    def _fp(self, px, py):
        """Flip a pixel position 180° around the board center."""
        if self.flipped:
            return (2 * BOARD_CX - px, 2 * BOARD_CY - py)
        return (px, py)

    def draw(self, g):
        self.s.fill(BG)
        self._grid()
        self._labels()
        self._highlights(g)
        self._pieces(g)
        self._hover(g)
        self._panel(g)
        if g.online:
            self._draw_online_status(g)

    # ── board ─────────────────────────────────────────────────

    def _grid(self):
        for a, b in GRID_SEGS:
            pygame.draw.aaline(self.s, GRID_LINE_C, self._fp(*a), self._fp(*b))
        for pos in VALID_POSITIONS:
            px, py = self._fp(*h2p(pos[0], pos[1]))
            pygame.draw.circle(self.s, GRID_DOT_C, (int(px), int(py)), DOT_R)

    def _labels(self):
        for lbl, pos in COL_LBL.items():
            x, y = self._fp(*pos)
            t = self.f_sm.render(lbl, True, LABEL_C)
            self.s.blit(t, (x - t.get_width() // 2, y - t.get_height() // 2))
        for lbl, pos in ROW_LBL.items():
            x, y = self._fp(*pos)
            t = self.f_sm.render(lbl, True, LABEL_C)
            self.s.blit(t, (x - t.get_width() // 2, y - t.get_height() // 2))

    # ── highlights ────────────────────────────────────────────

    def _highlights(self, g):
        # last move feedback
        for lp in [g.last_marker, g.last_dest]:
            if lp:
                px, py = self._fp(*h2p(lp[0], lp[1]))
                hs = pygame.Surface((RING_R * 2 + 12, RING_R * 2 + 12), pygame.SRCALPHA)
                pygame.draw.circle(hs, HL_LAST, (RING_R + 6, RING_R + 6), RING_R + 5)
                self.s.blit(hs, (px - RING_R - 6, py - RING_R - 6))

        # valid moves
        if g.sub_state == ST_MOVE_RING:
            for vpos in g.vmoves:
                px, py = self._fp(*h2p(vpos[0], vpos[1]))
                hs = pygame.Surface((MARKER_R * 2 + 8, MARKER_R * 2 + 8), pygame.SRCALPHA)
                pygame.draw.circle(hs, HL_VALID, (MARKER_R + 4, MARKER_R + 4), MARKER_R + 3)
                self.s.blit(hs, (px - MARKER_R - 4, py - MARKER_R - 4))

        # selected ring
        if g.sel:
            px, py = self._fp(*h2p(g.sel[0], g.sel[1]))
            pygame.draw.circle(self.s, HL_SELECT, (int(px), int(py)), RING_R + 5, 3)

        # candidate rows
        if g.sub_state == ST_CHOOSE_ROW:
            for i, row in enumerate(g.crows):
                c = HL_ROW if i == g.crow_i else HL_ROW_ALT
                for rpos in row:
                    px, py = self._fp(*h2p(rpos[0], rpos[1]))
                    pygame.draw.circle(self.s, c, (int(px), int(py)), MARKER_R + 6, 3)

        # removable rings
        if g.sub_state == ST_REMOVE_RING:
            for k, v in g.rings.items():
                if v == g.rplayer:
                    pos = _from_key(k)
                    px, py = self._fp(*h2p(pos[0], pos[1]))
                    pygame.draw.circle(self.s, HL_RING_REM, (int(px), int(py)), RING_R + 6, 3)

    # ── pieces ────────────────────────────────────────────────

    def _pieces(self, g):
        # markers
        for k, c in g.markers.items():
            pos = _from_key(k)
            px, py = self._fp(*h2p(pos[0], pos[1]))
            ip = (int(px), int(py))
            fill = W_MARKER_FILL if c == WHITE else B_MARKER_FILL
            edge = W_MARKER_EDGE if c == WHITE else B_MARKER_EDGE
            pygame.draw.circle(self.s, fill, ip, MARKER_R)
            pygame.draw.circle(self.s, edge, ip, MARKER_R, 2)

        # rings (annulus: thick outline = hollow centre)
        for k, c in g.rings.items():
            pos = _from_key(k)
            px, py = self._fp(*h2p(pos[0], pos[1]))
            ip = (int(px), int(py))
            fill = W_RING_FILL if c == WHITE else B_RING_FILL
            edge = W_RING_EDGE if c == WHITE else B_RING_EDGE
            # thick annulus body
            pygame.draw.circle(self.s, fill, ip, RING_R, RING_W)
            # outer and inner edges for crispness
            pygame.draw.circle(self.s, edge, ip, RING_R, 2)
            pygame.draw.circle(self.s, edge, ip, RING_R - RING_W + 1, 2)

    # ── hover tooltip ─────────────────────────────────────────

    def _hover(self, g):
        if g.hover and is_valid_pos(g.hover[0], g.hover[1]):
            q, r = g.hover[0], g.hover[1]
            lbl = clabel(q, r)
            px, py = self._fp(*h2p(q, r))
            t = self.f_sm.render(lbl, True, TXT_DARK)
            tx, ty = int(px) + 20, int(py) - 20
            if tx + t.get_width() > WINDOW_W - 20:
                tx = int(px) - 20 - t.get_width()
            bg = pygame.Rect(tx - 4, ty - 2, t.get_width() + 8, t.get_height() + 4)
            pygame.draw.rect(self.s, (255, 255, 248), bg, border_radius=3)
            pygame.draw.rect(self.s, LABEL_C, bg, 1, border_radius=3)
            self.s.blit(t, (tx, ty))

    # ── side panel ────────────────────────────────────────────

    def _panel(self, g):
        panel = pygame.Rect(PANEL_X, 18, PANEL_W, WINDOW_H - 36)
        pygame.draw.rect(self.s, PANEL_BG, panel, border_radius=10)
        pygame.draw.rect(self.s, PANEL_BORDER, panel, 2, border_radius=10)

        x0 = PANEL_X + 22
        y = 40

        # title
        self.s.blit(self.f_xl.render("YINSH", True, TXT_DARK), (x0, y))
        y += 50

        # phase badge
        ptxt = "PLACEMENT" if g.phase == PHASE_PLACEMENT else "MAIN GAME"
        self.s.blit(self.f_sm.render(ptxt, True, TXT_LIGHT), (x0, y))
        y += 28

        self._sep(x0, y); y += 16

        # scoreboard
        self.s.blit(self.f_lg.render("Score", True, TXT_DARK), (x0, y)); y += 30

        for colour, name in [(WHITE, 'White'), (BLACK, 'Black')]:
            colour_str = str(colour)
            tag = TAG_W if colour == WHITE else TAG_B
            acc = ACCENT_W if colour == WHITE else ACCENT_B
            # swatch
            pygame.draw.circle(self.s, tag, (x0 + 10, y + 12), 9)
            pygame.draw.circle(self.s, acc, (x0 + 10, y + 12), 9, 2)
            # name
            self.s.blit(self.f_md.render(name, True, TXT_DARK), (x0 + 28, y))
            # pips for scored rings
            nw = self.f_md.size(name)[0]
            for k in range(3):
                cx_pip = x0 + 28 + nw + 14 + k * 20
                if k < g.removed[colour_str]:
                    pygame.draw.circle(self.s, tag, (cx_pip, y + 9), 7)
                    pygame.draw.circle(self.s, acc, (cx_pip, y + 9), 7, 2)
                else:
                    pygame.draw.circle(self.s, PANEL_BORDER, (cx_pip, y + 9), 7, 2)

            n_on = sum(1 for v in g.rings.values() if v == colour)
            self.s.blit(self.f_sm.render(
                "{} ring{} on board".format(n_on, 's' if n_on != 1 else ''),
                True, TXT_MID), (x0 + 28, y + 22))
            y += 50

        self._sep(x0, y); y += 16

        # marker pool
        self.s.blit(self.f_md.render("Marker pool:  {}".format(g.pool), True, TXT_DARK), (x0, y)); y += 22
        self.s.blit(self.f_sm.render("On board:  {}".format(len(g.markers)), True, TXT_MID), (x0, y)); y += 30

        self._sep(x0, y); y += 16

        # active player indicator
        if g.sub_state != ST_GAME_OVER:
            active = g.rplayer if g.sub_state in (ST_CHOOSE_ROW, ST_REMOVE_RING) else g.turn
            if active is None:
                active = g.turn
            aname = "White" if active == WHITE else "Black"
            atag = TAG_W if active == WHITE else TAG_B
            aacc = ACCENT_W if active == WHITE else ACCENT_B
            self.s.blit(self.f_md.render("Turn:", True, TXT_MID), (x0, y))
            off = self.f_md.size("Turn: ")[0] + 4
            pygame.draw.circle(self.s, atag, (x0 + off + 8, y + 9), 8)
            pygame.draw.circle(self.s, aacc, (x0 + off + 8, y + 9), 8, 2)
            self.s.blit(self.f_lg.render(aname, True, TXT_DARK), (x0 + off + 22, y - 3))
            y += 36

        # status
        y += 4
        self._wrap(g.status, x0, y, PANEL_W - 44, self.f_md, TXT_DARK)
        y += 58

        self._sep(x0, y); y += 16

        # controls / role indicator
        if g.online:
            role = "White" if g.my_player == WHITE else "Black"
            atag = TAG_W if g.my_player == WHITE else TAG_B
            aacc = ACCENT_W if g.my_player == WHITE else ACCENT_B
            self.s.blit(self.f_md.render("You:", True, TXT_MID), (x0, y))
            off = self.f_md.size("You: ")[0] + 4
            pygame.draw.circle(self.s, atag, (x0 + off + 8, y + 9), 8)
            pygame.draw.circle(self.s, aacc, (x0 + off + 8, y + 9), 8, 2)
            self.s.blit(self.f_lg.render(role, True, TXT_DARK), (x0 + off + 22, y - 3))
            y += 36
            for line in [
                "Left-click   Select / confirm",
                "Right-click   Cancel",
                "Left/Right   Cycle row choices",
                "Esc   Exit",
            ]:
                self.s.blit(self.f_sm.render(line, True, TXT_MID), (x0, y)); y += 19
        else:
            self.s.blit(self.f_md.render("Controls", True, TXT_DARK), (x0, y)); y += 24
            for line in [
                "Left-click   Select / confirm",
                "Right-click   Cancel",
                "Left/Right   Cycle row choices",
                "N   New game",
                "Esc   Quit",
            ]:
                self.s.blit(self.f_sm.render(line, True, TXT_MID), (x0, y)); y += 19

        # game-over overlay
        if g.game_over:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self.s.blit(overlay, (0, 0))
            banner_h = 80
            banner_y = WINDOW_H // 2 - banner_h // 2
            pygame.draw.rect(self.s, PANEL_BG,
                             (0, banner_y, WINDOW_W, banner_h))
            pygame.draw.line(self.s, PANEL_BORDER,
                             (0, banner_y), (WINDOW_W, banner_y), 2)
            pygame.draw.line(self.s, PANEL_BORDER,
                             (0, banner_y + banner_h),
                             (WINDOW_W, banner_y + banner_h), 2)
            big = self.f_xl.render(g.status, True, TXT_DARK)
            self.s.blit(big, big.get_rect(center=(BOARD_CX, banner_y + 28)))
            if g.online:
                you_won = g.winner == g.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.f_sm.render(
                    "{}  Q / Esc to leave".format(sub_text), True, TXT_MID)
            else:
                sub = self.f_sm.render(
                    "Press N to play again", True, TXT_MID)
            self.s.blit(sub, sub.get_rect(center=(BOARD_CX, banner_y + 56)))

    def _sep(self, x, y):
        pygame.draw.line(self.s, PANEL_BORDER, (x, y), (PANEL_X + PANEL_W - 22, y))

    def _wrap(self, text, x, y, maxw, font, col):
        line = ""
        for w in text.split():
            t = line + (" " if line else "") + w
            if font.size(t)[0] > maxw and line:
                self.s.blit(font.render(line, True, col), (x, y))
                y += font.get_linesize() + 2; line = w
            else:
                line = t
        if line:
            self.s.blit(font.render(line, True, col), (x, y))

    # ── Online overlays ───────────────────────────────────────────

    def _draw_online_status(self, g):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not g.game_over and not g.is_my_turn:
            wait = self.f_sm.render(
                "Opponent's turn \u2014 waiting\u2026", True, TXT_MID)
            self.s.blit(wait, (12, 12))

        # Opponent disconnected banner
        if g.opponent_disconnected and not g.game_over:
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.s.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WINDOW_H // 2 - banner_h // 2
            pygame.draw.rect(self.s, PANEL_BG,
                             (0, banner_y, WINDOW_W, banner_h))
            msg = self.f_xl.render("Opponent disconnected", True, TXT_DARK)
            self.s.blit(msg, msg.get_rect(
                center=(WINDOW_W // 2, banner_y + 18)))
            sub = self.f_sm.render(
                "Waiting for reconnection\u2026", True, TXT_MID)
            self.s.blit(sub, sub.get_rect(
                center=(WINDOW_W // 2, banner_y + 42)))

        # Connection error bar at top
        if g.net_error:
            bar = pygame.Rect(0, 0, WINDOW_W, 28)
            pygame.draw.rect(self.s, (60, 15, 15), bar)
            err = self.f_sm.render(g.net_error, True, (225, 75, 65))
            self.s.blit(err, err.get_rect(center=(WINDOW_W // 2, 14)))


# ════════════════════════════════════════════════════════════════════
#  ONLINE ENTRY POINT
# ════════════════════════════════════════════════════════════════════


def run_online(screen, net, my_player, initial_state):
    """Run YINSH in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
    net : client.network.NetworkClient
    my_player : int (1=White, 2=Black)
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

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("YINSH \u2014 Online")
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
            # Left/Right are used for row cycling during ST_CHOOSE_ROW —
            # let the game handle them in that state instead of history nav
            if (event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_LEFT, pygame.K_RIGHT)
                    and hist.is_live
                    and game.sub_state == ST_CHOOSE_ROW):
                game.cycle(-1 if event.key == pygame.K_LEFT else 1)
                continue

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
                        game.rclick()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = p2h(*event.pos, orient.flipped)
                if event.button == 1:
                    if game.game_over:
                        continue
                    move = game.click(pos)
                    if move is not None:
                        net.send_move(move)
                elif event.button == 3:
                    game.rclick()

            elif event.type == pygame.MOUSEMOTION:
                game.hover = p2h(*event.pos, orient.flipped)

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


# ════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ════════════════════════════════════════════════════════════════════

def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("YINSH")
    clock = pygame.time.Clock()

    game = GameClient()
    renderer = Renderer(screen)

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit(); sys.exit()
                elif ev.key == pygame.K_n:
                    game.reset()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped
                elif ev.key == pygame.K_LEFT:
                    game.cycle(-1)
                elif ev.key == pygame.K_RIGHT:
                    game.cycle(1)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                pos = p2h(*ev.pos, renderer.flipped)
                if ev.button == 1:
                    game.click(pos)
                elif ev.button == 3:
                    game.rclick()

            elif ev.type == pygame.MOUSEMOTION:
                game.hover = p2h(*ev.pos, renderer.flipped)

        renderer.draw(game)
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
