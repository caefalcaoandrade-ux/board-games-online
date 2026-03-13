#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  ENTRAPMENT — Two-player abstract strategy board game       ║
║  Run:  python entrapment.py                                 ║
║  Controls: Left-click for all interactions · Esc to cancel  ║
╚══════════════════════════════════════════════════════════════╝
"""

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame
import sys
from typing import Optional, List, Tuple, Dict

# ═══════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════

ROWS, COLS = 7, 7
BARRIERS_PER_PLAYER = 25

SQ   = 80                                   # square side (px)
GW   = 14                                   # groove width (px)
CELL = SQ + GW                              # pitch origin-to-origin
BOARD_PX = COLS * SQ + (COLS - 1) * GW      # 644

BOARD_X = 62                                # left margin for labels
BOARD_Y = 50                                # top margin for labels

INFO_X = BOARD_X + BOARD_PX + 34
INFO_W = 350
WIN_W  = INFO_X + INFO_W + 24
WIN_H  = BOARD_Y + BOARD_PX + 58

FPS = 60

# ── colour palette ─────────────────────────────────────────
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

PLAYER_NAMES = {0: "Light", 1: "Dark"}
PLAYER_COLS  = {0: C_P0_ROAMER, 1: C_P1_ROAMER}
PLAYER_EDGES = {0: C_P0_EDGE,   1: C_P1_EDGE}
COL_LABELS   = "ABCDEFG"
DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# ═══════════════════════════════════════════════════════════════
#  GAME STATE  &  RULE ENGINE
# ═══════════════════════════════════════════════════════════════

class Game:
    """Complete game state and rule enforcement for Entrapment."""

    def __init__(self):
        self.board: List[List[Optional[int]]] = [
            [None] * COLS for _ in range(ROWS)
        ]
        # barriers stored as dicts: key=(r,c)  value=(player, "resting"|"standing")
        #   h_barriers[(r,c)] -> groove between sq(r,c) and sq(r,c+1)
        #   v_barriers[(r,c)] -> groove between sq(r,c) and sq(r+1,c)
        self.h_barriers: Dict[Tuple[int,int], Tuple[int,str]] = {}
        self.v_barriers: Dict[Tuple[int,int], Tuple[int,str]] = {}

        self.roamers: Dict[int, List[Tuple[int,int]]] = {0: [], 1: []}
        self.supply  = {0: BARRIERS_PER_PLAYER, 1: BARRIERS_PER_PLAYER}
        self.captures = {0: 0, 1: 0}

        self.phase          = "setup"     # setup | play | over
        self.current_player = 0
        self.setup_count    = 0
        self.action_num     = 1           # 1 or 2 within a turn
        self.first_white_turn = True
        self.winner: Optional[int] = None

        self.status  = "Light places a roamer."
        self.log: List[str] = []

    # ── coordinate helpers ─────────────────────────────────────

    @staticmethod
    def in_bounds(r: int, c: int) -> bool:
        return 0 <= r < ROWS and 0 <= c < COLS

    @staticmethod
    def coord_label(r: int, c: int) -> str:
        return f"{COL_LABELS[c]}{r + 1}"

    def _groove_dict(self, r1, c1, r2, c2):
        """Return (dict, key) for the groove between two adjacent squares."""
        if r1 == r2:
            return self.h_barriers, (r1, min(c1, c2))
        return self.v_barriers, (min(r1, r2), c1)

    def groove_at(self, r1, c1, r2, c2):
        d, k = self._groove_dict(r1, c1, r2, c2)
        return d.get(k)

    def set_groove(self, r1, c1, r2, c2, val):
        d, k = self._groove_dict(r1, c1, r2, c2)
        if val is None:
            d.pop(k, None)
        else:
            d[k] = val

    def iter_all_grooves(self):
        """Yield (type, r, c, value_or_None) for every groove position."""
        for r in range(ROWS):
            for c in range(COLS - 1):
                yield ("h", r, c, self.h_barriers.get((r, c)))
        for r in range(ROWS - 1):
            for c in range(COLS):
                yield ("v", r, c, self.v_barriers.get((r, c)))

    def iter_empty_grooves(self):
        for gt, r, c, v in self.iter_all_grooves():
            if v is None:
                yield (gt, r, c)

    def iter_player_resting(self, player):
        """Yield (type, r, c) for player's resting barriers on the board."""
        for gt, r, c, v in self.iter_all_grooves():
            if v is not None and v[0] == player and v[1] == "resting":
                yield (gt, r, c)

    # ── movement validation ────────────────────────────────────

    def _can_1sq(self, r, c, dr, dc, player):
        """1-square move: groove must be totally empty, dest must be empty."""
        nr, nc = r + dr, c + dc
        if not self.in_bounds(nr, nc):
            return False
        if self.groove_at(r, c, nr, nc) is not None:
            return False
        if self.board[nr][nc] is not None:
            return False
        return True

    def _can_slide2(self, r, c, dr, dc, player):
        """Plain 2-sq slide: both grooves empty, intermediate empty, dest empty."""
        mr, mc = r + dr, c + dc
        fr, fc = r + 2 * dr, c + 2 * dc
        if not self.in_bounds(fr, fc):
            return False
        if self.groove_at(r, c, mr, mc) is not None:
            return False
        if self.board[mr][mc] is not None:
            return False
        if self.groove_at(mr, mc, fr, fc) is not None:
            return False
        if self.board[fr][fc] is not None:
            return False
        return True

    def _can_jump_barrier(self, r, c, dr, dc, player):
        """Jump friendly resting barrier in first groove -> land 2 sq away.
        Conditions: first groove has own resting barrier, intermediate sq empty,
        second groove empty, landing sq empty."""
        mr, mc = r + dr, c + dc
        fr, fc = r + 2 * dr, c + 2 * dc
        if not self.in_bounds(fr, fc):
            return False
        b = self.groove_at(r, c, mr, mc)
        if b is None or b[0] != player or b[1] != "resting":
            return False
        if self.board[mr][mc] is not None:
            return False
        if self.groove_at(mr, mc, fr, fc) is not None:
            return False
        if self.board[fr][fc] is not None:
            return False
        return True

    def _can_jump_roamer(self, r, c, dr, dc, player):
        """Jump friendly roamer on adjacent sq -> land 2 sq away.
        Conditions: first groove empty, adjacent sq has friendly roamer,
        second groove empty, landing sq empty."""
        mr, mc = r + dr, c + dc
        fr, fc = r + 2 * dr, c + 2 * dc
        if not self.in_bounds(fr, fc):
            return False
        if self.groove_at(r, c, mr, mc) is not None:
            return False
        if self.board[mr][mc] != player:
            return False
        if self.groove_at(mr, mc, fr, fc) is not None:
            return False
        if self.board[fr][fc] is not None:
            return False
        return True

    def legal_moves(self, r, c, player=None):
        """Return list of (dest_r, dest_c, move_type) for roamer at (r,c)."""
        if player is None:
            player = self.board[r][c]
        if player is None:
            return []
        moves = []
        for dr, dc in DIRS:
            if self._can_1sq(r, c, dr, dc, player):
                moves.append((r + dr, c + dc, "1sq"))
            if self._can_jump_barrier(r, c, dr, dc, player):
                moves.append((r + 2*dr, c + 2*dc, "jump_barrier"))
            elif self._can_jump_roamer(r, c, dr, dc, player):
                moves.append((r + 2*dr, c + 2*dc, "jump_roamer"))
            elif self._can_slide2(r, c, dr, dc, player):
                moves.append((r + 2*dr, c + 2*dc, "slide2"))
        return moves

    def has_legal_move(self, r, c, player=None):
        return len(self.legal_moves(r, c, player)) > 0

    # ── entrapment / capture logic ─────────────────────────────

    def is_surrounded(self, r, c):
        """True if every orthogonal side is obstructed."""
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            if not self.in_bounds(nr, nc):
                continue                          # edge blocks
            if self.groove_at(r, c, nr, nc) is not None:
                continue                          # barrier blocks
            if self.board[nr][nc] is not None:
                continue                          # piece blocks
            return False                          # open side found
        return True

    def _can_be_freed(self, r, c, player):
        """Can any adjacent friendly roamer move away to free this piece?
        We temporarily remove each adjacent friendly roamer and check if
        the trapped roamer gains a legal move or becomes unsurrounded."""
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            if not self.in_bounds(nr, nc):
                continue
            if self.board[nr][nc] != player:
                continue
            # temporarily remove the neighbour and re-check
            self.board[nr][nc] = None
            freed = self.has_legal_move(r, c, player) or not self.is_surrounded(r, c)
            self.board[nr][nc] = player
            if freed:
                return True
        return False

    def should_capture(self, r, c, player):
        """True if roamer must be immediately removed (entrapped + un-free-able)."""
        if not self.is_surrounded(r, c):
            return False
        if self.has_legal_move(r, c, player):
            return False
        if self._can_be_freed(r, c, player):
            return False
        return True

    def is_forced(self, r, c, player):
        """Surrounded but NOT captured — needs mandatory attention."""
        if not self.is_surrounded(r, c):
            return False
        return not self.should_capture(r, c, player)

    def forced_roamers(self, player):
        return [p for p in self.roamers[player]
                if self.is_forced(p[0], p[1], player)]

    def _capture(self, player, pos):
        r, c = pos
        self.board[r][c] = None
        if pos in self.roamers[player]:
            self.roamers[player].remove(pos)
        self.captures[1 - player] += 1
        self.log.append(f"{PLAYER_NAMES[player]} roamer captured at {self.coord_label(r, c)}!")

    def process_captures(self, acting_player) -> List[Tuple[int,int]]:
        """Process all captures. Returns non-empty list if acting player must
        choose which opponent roamer to capture (simultaneous entrapment)."""
        changed = True
        while changed:
            changed = False
            for player in (1 - acting_player, acting_player):
                to_cap = [p for p in list(self.roamers[player])
                          if self.should_capture(p[0], p[1], player)]
                if not to_cap:
                    continue
                if player != acting_player and len(to_cap) > 1:
                    return to_cap          # UI must ask acting player to choose
                for pos in to_cap:
                    self._capture(player, pos)
                    changed = True

            # double-force rule: at most 1 forced roamer per player
            for player in (0, 1):
                forced = self.forced_roamers(player)
                if len(forced) > 1:
                    self._capture(player, forced[-1])
                    changed = True
        return []

    def check_winner(self):
        for p in (0, 1):
            if self.captures[p] >= 3:
                self.winner = p
                self.phase = "over"
                self.status = f"{PLAYER_NAMES[p]} wins the game!"
                return True
        return False

    # ── execute actions ────────────────────────────────────────

    def exec_move(self, r1, c1, r2, c2) -> bool:
        player = self.board[r1][c1]
        if player is None or player != self.current_player:
            return False
        moves = self.legal_moves(r1, c1, player)
        match = [m for m in moves if m[0] == r2 and m[1] == c2]
        if not match:
            return False

        mtype = match[0][2]
        self.board[r1][c1] = None
        self.board[r2][c2] = player
        idx = self.roamers[player].index((r1, c1))
        self.roamers[player][idx] = (r2, c2)

        if mtype == "jump_barrier":
            dr = 1 if r2 > r1 else (-1 if r2 < r1 else 0)
            dc = 1 if c2 > c1 else (-1 if c2 < c1 else 0)
            self.set_groove(r1, c1, r1 + dr, c1 + dc, (player, "standing"))

        self.log.append(
            f"{PLAYER_NAMES[player]} {self.coord_label(r1,c1)}->{self.coord_label(r2,c2)}"
            + (" [jump]" if "jump" in mtype else "")
        )
        return True

    def exec_place(self, gt, gr, gc) -> bool:
        player = self.current_player
        if self.supply[player] <= 0:
            return False
        d = self.h_barriers if gt == "h" else self.v_barriers
        if (gr, gc) in d:
            return False
        d[(gr, gc)] = (player, "resting")
        self.supply[player] -= 1
        self.log.append(f"{PLAYER_NAMES[player]} places barrier")
        return True

    def exec_flip(self, gt, gr, gc) -> bool:
        player = self.current_player
        d = self.h_barriers if gt == "h" else self.v_barriers
        v = d.get((gr, gc))
        if v is None or v[0] != player or v[1] != "resting":
            return False
        d[(gr, gc)] = (player, "standing")
        self.log.append(f"{PLAYER_NAMES[player]} flips barrier")
        return True

    def exec_relocate(self, sgt, sr, sc, dgt, dr_, dc_) -> bool:
        player = self.current_player
        sd = self.h_barriers if sgt == "h" else self.v_barriers
        v = sd.get((sr, sc))
        if v is None or v[0] != player or v[1] != "resting":
            return False
        dd = self.h_barriers if dgt == "h" else self.v_barriers
        if (dr_, dc_) in dd:
            return False
        sd.pop((sr, sc))
        dd[(dr_, dc_)] = (player, "resting")
        self.log.append(f"{PLAYER_NAMES[player]} relocates barrier")
        return True

    # ── forced-move helpers ───────────────────────────────────

    def selectable_for_action1(self):
        """Which roamers may be selected for the mandatory Action 1 move?"""
        p = self.current_player
        forced = self.forced_roamers(p)
        if not forced:
            return [pos for pos in self.roamers[p]
                    if self.has_legal_move(pos[0], pos[1], p)]
        fp = forced[0]
        fr, fc = fp
        ok = set()
        if self.has_legal_move(fr, fc, p):
            ok.add(fp)
        for dr, dc in DIRS:
            nr, nc = fr + dr, fc + dc
            if not self.in_bounds(nr, nc) or self.board[nr][nc] != p:
                continue
            adj = (nr, nc)
            if adj not in self.roamers[p]:
                continue
            if not self.has_legal_move(nr, nc, p):
                continue
            # does removing this neighbour actually open a side / give a move?
            self.board[nr][nc] = None
            helps = not self.is_surrounded(fr, fc) or self.has_legal_move(fr, fc, p)
            self.board[nr][nc] = p
            if helps:
                ok.add(adj)
        return list(ok)

    def selectable_for_action2_move(self):
        p = self.current_player
        forced = self.forced_roamers(p)
        if not forced:
            return [pos for pos in self.roamers[p]
                    if self.has_legal_move(pos[0], pos[1], p)]
        return self.selectable_for_action1()

    def can_do_barrier_action(self):
        p = self.current_player
        if self.supply[p] > 0 and any(True for _ in self.iter_empty_grooves()):
            return True
        if any(True for _ in self.iter_player_resting(p)):
            return True
        return False

    def any_valid_action(self):
        """Can the current player do anything at all this action?"""
        if self.action_num == 1:
            return len(self.selectable_for_action1()) > 0
        # action 2
        if len(self.selectable_for_action2_move()) > 0:
            return True
        return self.can_do_barrier_action()

    # ── turn management ───────────────────────────────────────

    def advance_turn(self):
        if self.phase != "play":
            return
        if self.action_num == 1:
            if self.first_white_turn and self.current_player == 0:
                self.first_white_turn = False
                self.current_player = 1
                self.action_num = 1
            else:
                self.action_num = 2
        else:
            self.current_player = 1 - self.current_player
            self.action_num = 1

        # Edge case: if the (new) player cannot act, skip action 2
        if not self.any_valid_action() and self.action_num == 2:
            self.current_player = 1 - self.current_player
            self.action_num = 1

        self._refresh_status()

    def _refresh_status(self):
        p = PLAYER_NAMES[self.current_player]
        if self.phase == "setup":
            self.status = f"{p} places a roamer."
        elif self.phase == "play":
            forced = self.forced_roamers(self.current_player)
            a = self.action_num
            half = " (half-turn)" if self.first_white_turn and self.current_player == 0 else ""
            if a == 1:
                if forced:
                    fl = self.coord_label(*forced[0])
                    self.status = f"{p} | Action 1{half} — Move roamer (forced: {fl})."
                else:
                    self.status = f"{p} | Action 1{half} — Move a roamer."
            else:
                self.status = f"{p} | Action 2 — Move roamer or barrier action."


# ═══════════════════════════════════════════════════════════════
#  UI  BUTTON
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  GAME  UI  /  RENDERER
# ═══════════════════════════════════════════════════════════════

class GameUI:
    def __init__(self, game: Game):
        self.game = game
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Entrapment")

        self.font       = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 17)
        self.font_sm    = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 14)
        self.font_lg    = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 22, bold=True)
        self.font_coord = pygame.font.SysFont("Consolas,Courier New,monospace", 14, bold=True)
        self.font_title = pygame.font.SysFont("Segoe UI,Arial,Helvetica,sans-serif", 26, bold=True)

        # interaction state
        self.selected: Optional[Tuple[int,int]] = None
        self.valid_dests: List[Tuple[int,int,str]] = []
        self.mode = "select"    # select | place | flip | reloc_pick | reloc_place | choose_cap
        self.reloc_src: Optional[Tuple[str,int,int]] = None
        self.cap_choices: List[Tuple[int,int]] = []
        self.hover_sq: Optional[Tuple[int,int]] = None
        self.hover_grv: Optional[Tuple[str,int,int]] = None

        # action-2 buttons (positioned dynamically in draw)
        self.btn_move  = Btn(0, 0, 102, 32, "Move", "move")
        self.btn_place = Btn(0, 0, 102, 32, "Place", "place")
        self.btn_flip  = Btn(0, 0, 102, 32, "Flip", "flip")
        self.btn_reloc = Btn(0, 0, 102, 32, "Relocate", "relocate")
        self.btns_a2 = [self.btn_move, self.btn_place, self.btn_flip, self.btn_reloc]

        self.btn_new = Btn(INFO_X + 100, WIN_H - 50, 130, 34, "New Game", "restart")

    # ── pixel <-> grid ─────────────────────────────────────────

    @staticmethod
    def sq_xy(r, c):
        return (BOARD_X + c * CELL, BOARD_Y + r * CELL)

    @staticmethod
    def sq_center(r, c):
        return (BOARD_X + c * CELL + SQ // 2, BOARD_Y + r * CELL + SQ // 2)

    @staticmethod
    def groove_rect(gt, gr, gc):
        if gt == "h":
            return pygame.Rect(BOARD_X + gc * CELL + SQ, BOARD_Y + gr * CELL, GW, SQ)
        return pygame.Rect(BOARD_X + gc * CELL, BOARD_Y + gr * CELL + SQ, SQ, GW)

    def px_to_sq(self, mx, my):
        for r in range(ROWS):
            for c in range(COLS):
                x, y = self.sq_xy(r, c)
                if x <= mx < x + SQ and y <= my < y + SQ:
                    return (r, c)
        return None

    def px_to_groove(self, mx, my):
        best, best_d = None, 9999
        for gt, r, c, _ in self.game.iter_all_grooves():
            rect = self.groove_rect(gt, r, c)
            exp = rect.inflate(14, 14)
            if exp.collidepoint(mx, my):
                d = abs(mx - rect.centerx) + abs(my - rect.centery)
                if d < best_d:
                    best_d, best = d, (gt, r, c)
        return best

    # ── drawing ────────────────────────────────────────────────

    def draw(self):
        g = self.game
        scr = self.screen
        scr.fill(C_BG)

        # board frame
        frame = pygame.Rect(BOARD_X - 8, BOARD_Y - 8, BOARD_PX + 16, BOARD_PX + 16)
        pygame.draw.rect(scr, C_BOARD, frame, border_radius=5)

        # intersections
        for r in range(ROWS - 1):
            for c in range(COLS - 1):
                pygame.draw.rect(scr, C_INTERSECT,
                    (BOARD_X + c * CELL + SQ, BOARD_Y + r * CELL + SQ, GW, GW))

        # grooves  (highlight on hover when relevant)
        grv_mode = self.mode in ("place", "flip", "reloc_pick", "reloc_place")
        for gt, gr, gc, val in g.iter_all_grooves():
            rect = self.groove_rect(gt, gr, gc)
            col = C_GROOVE
            if grv_mode and self.hover_grv == (gt, gr, gc):
                col = C_GRV_HOVER
            pygame.draw.rect(scr, col, rect)
            if val is not None:
                self._draw_barrier(scr, gt, gr, gc, val)

        # relocate-source highlight
        if self.mode == "reloc_place" and self.reloc_src:
            sgt, sr, sc = self.reloc_src
            rect = self.groove_rect(sgt, sr, sc)
            hl = pygame.Surface(rect.size, pygame.SRCALPHA)
            hl.fill((255, 200, 60, 80))
            scr.blit(hl, rect.topleft)

        # squares
        for r in range(ROWS):
            for c in range(COLS):
                x, y = self.sq_xy(r, c)
                col = C_SQUARE
                if self.hover_sq == (r, c) and g.phase == "setup" and g.board[r][c] is None:
                    col = C_SQ_HOVER
                pygame.draw.rect(scr, col, (x, y, SQ, SQ), border_radius=3)

        # valid-move highlights
        for dr, dc, _ in self.valid_dests:
            cx, cy = self.sq_center(dr, dc)
            x, y = self.sq_xy(dr, dc)
            hl = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
            hl.fill((*C_VALID, 45))
            scr.blit(hl, (x, y))
            pygame.draw.circle(scr, C_VALID, (cx, cy), 10)

        # capture-choice highlights
        if self.mode == "choose_cap":
            for cr, cc in self.cap_choices:
                x, y = self.sq_xy(cr, cc)
                hl = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
                hl.fill((*C_CAPTURE, 65))
                scr.blit(hl, (x, y))
                pygame.draw.rect(scr, C_CAPTURE, (x, y, SQ, SQ), 3, border_radius=3)

        # roamers
        for player in (0, 1):
            for pos in g.roamers[player]:
                self._draw_roamer(scr, pos[0], pos[1], player)

        # selection ring
        if self.selected:
            cx, cy = self.sq_center(*self.selected)
            pygame.draw.circle(scr, C_SEL, (cx, cy), SQ // 2 - 5, 3)

        # forced-roamer outlines
        if g.phase == "play":
            for pos in g.forced_roamers(g.current_player):
                if pos != self.selected:
                    cx, cy = self.sq_center(*pos)
                    pygame.draw.circle(scr, C_FORCED, (cx, cy), SQ // 2 - 3, 3)

        # coordinate labels
        for c in range(COLS):
            lbl = self.font_coord.render(COL_LABELS[c], True, C_TEXT_DIM)
            cx = BOARD_X + c * CELL + SQ // 2 - lbl.get_width() // 2
            scr.blit(lbl, (cx, BOARD_Y - 24))
            scr.blit(lbl, (cx, BOARD_Y + BOARD_PX + 10))
        for r in range(ROWS):
            lbl = self.font_coord.render(str(r + 1), True, C_TEXT_DIM)
            ry = BOARD_Y + r * CELL + SQ // 2 - lbl.get_height() // 2
            scr.blit(lbl, (BOARD_X - 24, ry))
            scr.blit(lbl, (BOARD_X + BOARD_PX + 12, ry))

        # info panel
        self._draw_panel(scr)

        pygame.display.flip()

    # ── roamer rendering ───────────────────────────────────────

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

    # ── barrier rendering ──────────────────────────────────────

    def _draw_barrier(self, scr, gt, gr, gc, val):
        player, state = val
        rect = self.groove_rect(gt, gr, gc)
        is_rest = state == "resting"
        col = (C_P0_REST if is_rest else C_P0_STAND) if player == 0 \
              else (C_P1_REST if is_rest else C_P1_STAND)

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

    # ── info panel ─────────────────────────────────────────────

    def _draw_panel(self, scr):
        g = self.game
        x0 = INFO_X
        y = 14

        # title
        scr.blit(self.font_title.render("ENTRAPMENT", True, C_TEXT), (x0, y))
        y += 40

        # current player
        pcol, pedge = PLAYER_COLS[g.current_player], PLAYER_EDGES[g.current_player]
        pygame.draw.circle(scr, pcol, (x0 + 12, y + 11), 10)
        pygame.draw.circle(scr, pedge, (x0 + 12, y + 11), 10, 2)
        scr.blit(self.font_lg.render(f"{PLAYER_NAMES[g.current_player]}'s Turn", True, C_TEXT),
                 (x0 + 30, y))
        y += 34

        # status message
        for line in self._wrap(g.status, self.font, INFO_W - 10):
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
        h = hints.get(self.mode)
        if h:
            scr.blit(self.font_sm.render(h, True, C_FORCED), (x0, y))
            y += 18
        y += 8

        # divider
        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 14

        # player stats
        for p in (0, 1):
            pygame.draw.circle(scr, PLAYER_COLS[p], (x0 + 10, y + 9), 8)
            pygame.draw.circle(scr, PLAYER_EDGES[p], (x0 + 10, y + 9), 8, 1)
            txt = f"{PLAYER_NAMES[p]}   Barriers: {g.supply[p]}   Roamers: {len(g.roamers[p])}/3"
            scr.blit(self.font.render(txt, True, C_TEXT), (x0 + 26, y + 1))
            y += 28
        y += 6

        pygame.draw.line(scr, C_DIVIDER, (x0, y), (x0 + INFO_W - 24, y))
        y += 14

        # action-2 buttons
        if g.phase == "play" and g.action_num == 2 and self.mode != "choose_cap":
            scr.blit(self.font.render("Action 2:", True, C_TEXT_DIM), (x0, y))
            y += 26
            self._layout_btns(y)
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
        for entry in g.log[-max_lines:]:
            scr.blit(self.font_sm.render(entry, True, C_TEXT_DIM), (x0 + 4, y))
            y += 16

        # new game button
        self.btn_new.draw(scr, self.font)

        # esc hint
        if self.selected or self.mode not in ("select", "choose_cap"):
            scr.blit(self.font_sm.render("Esc to cancel", True, C_TEXT_DIM), (x0, WIN_H - 16))

        # game-over overlay
        if g.phase == "over":
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            scr.blit(overlay, (0, 0))
            winner_col = PLAYER_COLS[g.winner] if g.winner is not None else C_TEXT
            msg = self.font_title.render(g.status, True, winner_col)
            scr.blit(msg, msg.get_rect(center=(BOARD_X + BOARD_PX // 2, WIN_H // 2 - 20)))
            sub = self.font.render("Click  New Game  to play again.", True, (200, 200, 200))
            scr.blit(sub, sub.get_rect(center=(BOARD_X + BOARD_PX // 2, WIN_H // 2 + 18)))

    def _layout_btns(self, y):
        g = self.game
        p = g.current_player
        gap = 8
        bx = INFO_X
        for i, b in enumerate(self.btns_a2):
            row, col = divmod(i, 2)
            b.rect.x = bx + col * (b.rect.w + gap)
            b.rect.y = y + row * (b.rect.h + gap)

        can_place = g.supply[p] > 0 and any(True for _ in g.iter_empty_grooves())
        has_rest  = any(True for _ in g.iter_player_resting(p))
        can_reloc = g.supply[p] == 0 and has_rest and any(True for _ in g.iter_empty_grooves())
        can_move  = len(g.selectable_for_action2_move()) > 0

        self.btn_move.enabled  = can_move
        self.btn_place.enabled = can_place
        self.btn_flip.enabled  = has_rest
        self.btn_reloc.enabled = can_reloc

        self.btn_move.active  = self.mode == "select"
        self.btn_place.active = self.mode == "place"
        self.btn_flip.active  = self.mode == "flip"
        self.btn_reloc.active = self.mode in ("reloc_pick", "reloc_place")

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

    # ── input handlers ─────────────────────────────────────────

    def on_mousemove(self, mx, my):
        self.hover_sq = self.px_to_sq(mx, my)
        self.hover_grv = self.px_to_groove(mx, my)
        for b in self.btns_a2 + [self.btn_new]:
            b.hover = b.rect.collidepoint(mx, my)

    def on_click(self, mx, my):
        g = self.game

        if self.btn_new.rect.collidepoint(mx, my):
            self._restart()
            return

        if g.phase == "over":
            return

        if g.phase == "setup":
            self._click_setup(mx, my)
            return

        if self.mode == "choose_cap":
            self._click_choose_cap(mx, my)
            return

        # action-2 buttons
        if g.action_num == 2:
            for b in self.btns_a2:
                if b.rect.collidepoint(mx, my) and b.enabled:
                    self._set_mode(b.aid)
                    return

        sq = self.px_to_sq(mx, my)
        grv = self.px_to_groove(mx, my)

        if self.mode == "select":
            self._click_select(sq, grv)
        elif self.mode == "place":
            self._click_place(grv)
        elif self.mode == "flip":
            self._click_flip(grv)
        elif self.mode == "reloc_pick":
            self._click_reloc_pick(grv)
        elif self.mode == "reloc_place":
            self._click_reloc_place(grv)

    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            self.selected = None
            self.valid_dests = []
            self.reloc_src = None
            if self.mode not in ("select", "choose_cap"):
                self.mode = "select"

    # ── click-mode handlers ────────────────────────────────────

    def _set_mode(self, aid):
        self.selected = None
        self.valid_dests = []
        self.reloc_src = None
        table = {"move": "select", "place": "place",
                 "flip": "flip", "relocate": "reloc_pick"}
        self.mode = table.get(aid, "select")

    def _click_setup(self, mx, my):
        g = self.game
        sq = self.px_to_sq(mx, my)
        if sq is None:
            return
        r, c = sq
        if g.board[r][c] is not None:
            return
        p = g.current_player
        g.board[r][c] = p
        g.roamers[p].append((r, c))
        g.log.append(f"{PLAYER_NAMES[p]} places roamer at {g.coord_label(r, c)}")
        g.setup_count += 1
        if g.setup_count >= 6:
            g.phase = "play"
            g.current_player = 0
            g.action_num = 1
            g.first_white_turn = True
        else:
            g.current_player = 1 - g.current_player
        g._refresh_status()

    def _click_select(self, sq, grv):
        """Handle clicks in default 'select' mode — roamer move or auto-place."""
        g = self.game
        p = g.current_player

        if sq is not None:
            r, c = sq
            # if a roamer is already selected, try moving to the destination
            if self.selected is not None:
                dests = [(d[0], d[1]) for d in self.valid_dests]
                if (r, c) in dests:
                    if g.exec_move(self.selected[0], self.selected[1], r, c):
                        self.selected = None
                        self.valid_dests = []
                        self._after_action()
                        return
                # click same roamer => deselect
                if (r, c) == self.selected:
                    self.selected = None
                    self.valid_dests = []
                    return

            # try selecting a roamer
            if g.board[r][c] == p:
                ok = (g.selectable_for_action1() if g.action_num == 1
                      else g.selectable_for_action2_move())
                if (r, c) in ok:
                    self.selected = (r, c)
                    self.valid_dests = g.legal_moves(r, c, p)
                    return

            # click elsewhere => deselect
            self.selected = None
            self.valid_dests = []

        elif grv is not None and g.action_num == 2 and self.selected is None:
            # convenience: clicking an empty groove in select mode auto-places
            gt, gr, gc = grv
            d = g.h_barriers if gt == "h" else g.v_barriers
            if (gr, gc) not in d and g.supply[p] > 0:
                if g.exec_place(gt, gr, gc):
                    self._after_action()

    def _click_place(self, grv):
        if grv is None:
            return
        gt, gr, gc = grv
        g = self.game
        d = g.h_barriers if gt == "h" else g.v_barriers
        if (gr, gc) in d:
            return
        if g.exec_place(gt, gr, gc):
            self.mode = "select"
            self._after_action()

    def _click_flip(self, grv):
        if grv is None:
            return
        gt, gr, gc = grv
        if self.game.exec_flip(gt, gr, gc):
            self.mode = "select"
            self._after_action()

    def _click_reloc_pick(self, grv):
        if grv is None:
            return
        g = self.game
        gt, gr, gc = grv
        d = g.h_barriers if gt == "h" else g.v_barriers
        v = d.get((gr, gc))
        if v and v[0] == g.current_player and v[1] == "resting":
            self.reloc_src = (gt, gr, gc)
            self.mode = "reloc_place"

    def _click_reloc_place(self, grv):
        if grv is None:
            return
        g = self.game
        gt, gr, gc = grv
        d = g.h_barriers if gt == "h" else g.v_barriers
        if (gr, gc) in d:
            return
        src = self.reloc_src
        if src and g.exec_relocate(src[0], src[1], src[2], gt, gr, gc):
            self.reloc_src = None
            self.mode = "select"
            self._after_action()

    def _click_choose_cap(self, mx, my):
        sq = self.px_to_sq(mx, my)
        if sq and sq in self.cap_choices:
            g = self.game
            opp = 1 - g.current_player
            g._capture(opp, sq)
            self.cap_choices = []
            self.mode = "select"
            self._resolve_caps()

    # ── post-action flow ──────────────────────────────────────

    def _after_action(self):
        self._resolve_caps()

    def _resolve_caps(self):
        g = self.game
        if g.check_winner():
            return
        choices = g.process_captures(g.current_player)
        if g.check_winner():
            return
        if choices:
            self.cap_choices = choices
            self.mode = "choose_cap"
            g.status = (f"{PLAYER_NAMES[g.current_player]}: "
                        "Choose which opponent roamer to capture.")
            return
        g.advance_turn()
        self.selected = None
        self.valid_dests = []
        if self.mode != "choose_cap":
            self.mode = "select"

    def _restart(self):
        self.game = Game()
        self.selected = None
        self.valid_dests = []
        self.mode = "select"
        self.cap_choices = []
        self.reloc_src = None


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    pygame.init()
    game = Game()
    ui = GameUI(game)
    clock = pygame.time.Clock()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif ev.type == pygame.MOUSEMOTION:
                ui.on_mousemove(*ev.pos)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                ui.on_click(*ev.pos)
            elif ev.type == pygame.KEYDOWN:
                ui.on_key(ev.key)

        ui.draw()
        clock.tick(FPS)


if __name__ == "__main__":
    main()