#!/usr/bin/env python3
"""
TAK — 6×6 Abstract Strategy Board Game
Complete implementation with Pygame display for local human-vs-human play.
"""

# ============================================================
# SECTION 1 — GAME LOGIC CLASS
# Pure Python, no Pygame. Fully self-contained and serializable.
# ============================================================

import copy


class TakGame:
    """Complete game logic for 6×6 Tak."""

    BOARD_SIZE = 6
    CARRY_LIMIT = 6  # Equal to board width
    INITIAL_STONES = 30
    INITIAL_CAPSTONES = 1

    DIRECTIONS = {
        "north": [1, 0],
        "south": [-1, 0],
        "east": [0, 1],
        "west": [0, -1],
    }

    # ── Factory / meta ──────────────────────────────────────

    def get_game_name(self):
        return "Tak (6x6)"

    def get_player_count(self):
        return 2

    def get_current_player(self, state):
        return state["current_player"]

    # ── Initial state ───────────────────────────────────────

    def create_initial_state(self):
        board = [[[] for _ in range(self.BOARD_SIZE)] for _ in range(self.BOARD_SIZE)]
        return {
            "board": board,
            "reserves": {
                "white": {"stones": self.INITIAL_STONES, "capstones": self.INITIAL_CAPSTONES},
                "black": {"stones": self.INITIAL_STONES, "capstones": self.INITIAL_CAPSTONES},
            },
            "current_player": "white",
            "turn_number": 1,
            "game_over": False,
            "winner": None,
        }

    # ── Legal moves ─────────────────────────────────────────

    def get_legal_moves(self, state, player):
        if state["game_over"] or state["current_player"] != player:
            return []

        moves = []
        turn = state["turn_number"]
        board = state["board"]

        if turn <= 2:
            # Opening protocol: place opponent's flat stone on any empty square
            for r in range(self.BOARD_SIZE):
                for c in range(self.BOARD_SIZE):
                    if not board[r][c]:
                        moves.append({"action": "place", "row": r, "col": c, "piece_type": "flat"})
            return moves

        # Normal turn (turn >= 3): placement + movement
        reserves = state["reserves"][player]

        # Placement moves
        for r in range(self.BOARD_SIZE):
            for c in range(self.BOARD_SIZE):
                if not board[r][c]:
                    if reserves["stones"] > 0:
                        moves.append({"action": "place", "row": r, "col": c, "piece_type": "flat"})
                        moves.append({"action": "place", "row": r, "col": c, "piece_type": "standing"})
                    if reserves["capstones"] > 0:
                        moves.append({"action": "place", "row": r, "col": c, "piece_type": "capstone"})

        # Movement moves
        for r in range(self.BOARD_SIZE):
            for c in range(self.BOARD_SIZE):
                stack = board[r][c]
                if stack and stack[-1]["owner"] == player:
                    max_carry = min(len(stack), self.CARRY_LIMIT)
                    for carry in range(1, max_carry + 1):
                        carried = stack[-carry:]  # bottom-to-top of carried bundle
                        for dir_name, (dr, dc) in self.DIRECTIONS.items():
                            drop_sequences = []
                            self._gen_drops(board, r, c, dr, dc, list(carried), [], drop_sequences)
                            for drops in drop_sequences:
                                moves.append({
                                    "action": "move",
                                    "row": r, "col": c,
                                    "direction": dir_name,
                                    "carry": carry,
                                    "drops": drops,
                                })
        return moves

    def _gen_drops(self, board, r, c, dr, dc, carried, drops_so_far, results):
        """Recursively enumerate valid drop sequences."""
        nr, nc = r + dr, c + dc
        if not (0 <= nr < self.BOARD_SIZE and 0 <= nc < self.BOARD_SIZE):
            return

        stack = board[nr][nc]
        remaining = len(carried)

        if stack:
            top_type = stack[-1]["type"]
            if top_type == "capstone":
                return  # Absolute block
            if top_type == "standing":
                # Capstone flatten: only the capstone alone on the final drop
                if remaining == 1 and carried[0]["type"] == "capstone":
                    results.append(drops_so_far + [1])
                return

        # Square is empty or flat-topped
        for drop in range(1, remaining + 1):
            new_carried = carried[drop:]
            new_drops = drops_so_far + [drop]
            if not new_carried:
                results.append(new_drops)
            else:
                self._gen_drops(board, nr, nc, dr, dc, new_carried, new_drops, results)

    # ── Apply move ──────────────────────────────────────────

    def apply_move(self, state, player, move):
        new_state = copy.deepcopy(state)
        board = new_state["board"]
        turn = new_state["turn_number"]

        if move["action"] == "place":
            r, c = move["row"], move["col"]
            if turn <= 2:
                # Opening: place opponent's flat stone
                opponent = "black" if player == "white" else "white"
                piece = {"owner": opponent, "type": "flat"}
                new_state["reserves"][opponent]["stones"] -= 1
            else:
                piece = {"owner": player, "type": move["piece_type"]}
                if move["piece_type"] == "capstone":
                    new_state["reserves"][player]["capstones"] -= 1
                else:
                    new_state["reserves"][player]["stones"] -= 1
            board[r][c].append(piece)

        elif move["action"] == "move":
            r, c = move["row"], move["col"]
            carry = move["carry"]
            drops = move["drops"]
            dr, dc = self.DIRECTIONS[move["direction"]]

            # Lift pieces from the top of the stack
            carried = board[r][c][-carry:]
            board[r][c] = board[r][c][:-carry]

            cr, cc = r, c
            for d in drops:
                cr += dr
                cc += dc
                dropping = carried[:d]
                carried = carried[d:]

                # Capstone flatten: if top of destination is standing, flatten it
                if board[cr][cc] and board[cr][cc][-1]["type"] == "standing":
                    board[cr][cc][-1]["type"] = "flat"

                board[cr][cc].extend(dropping)

        # Advance turn
        new_state["current_player"] = "black" if player == "white" else "white"
        new_state["turn_number"] = turn + 1

        # Check for game end
        winner = self._evaluate_winner(new_state, player)
        if winner is not None:
            new_state["game_over"] = True
            new_state["winner"] = winner

        return new_state

    # ── Winner evaluation ───────────────────────────────────

    def check_winner(self, state):
        if state["game_over"]:
            return state["winner"]
        return None

    def _evaluate_winner(self, state, active_player):
        """Called after active_player's move. Checks roads, then terminal flat count."""
        inactive = "black" if active_player == "white" else "white"

        active_road = self._has_road(state, active_player)
        inactive_road = self._has_road(state, inactive)

        if active_road and inactive_road:
            return active_player  # Double road: active wins
        if active_road:
            return active_player
        if inactive_road:
            return inactive

        # Terminal conditions: board full or either reserve exhausted
        board = state["board"]
        board_full = all(board[r][c] for r in range(self.BOARD_SIZE) for c in range(self.BOARD_SIZE))
        white_empty = (state["reserves"]["white"]["stones"] == 0 and
                       state["reserves"]["white"]["capstones"] == 0)
        black_empty = (state["reserves"]["black"]["stones"] == 0 and
                       state["reserves"]["black"]["capstones"] == 0)

        if board_full or white_empty or black_empty:
            return self._flat_winner(state)

        return None

    def _has_road(self, state, player):
        """Check if player has a road connecting opposite edges."""
        board = state["board"]

        def is_road_sq(r, c):
            stack = board[r][c]
            if not stack:
                return False
            top = stack[-1]
            return top["owner"] == player and top["type"] in ("flat", "capstone")

        # BFS helper
        def bfs(starts, goal_fn):
            visited = set()
            queue = list(starts)
            for pos in queue:
                visited.add(pos)
            while queue:
                r, c = queue.pop(0)
                if goal_fn(r, c):
                    return True
                for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.BOARD_SIZE and 0 <= nc < self.BOARD_SIZE:
                        if (nr, nc) not in visited and is_road_sq(nr, nc):
                            visited.add((nr, nc))
                            queue.append((nr, nc))
            return False

        # West (col=0) to East (col=5)
        west_starts = [(r, 0) for r in range(self.BOARD_SIZE) if is_road_sq(r, 0)]
        if west_starts and bfs(west_starts, lambda r, c: c == self.BOARD_SIZE - 1):
            return True

        # South (row=0) to North (row=5)
        south_starts = [(0, c) for c in range(self.BOARD_SIZE) if is_road_sq(0, c)]
        if south_starts and bfs(south_starts, lambda r, c: r == self.BOARD_SIZE - 1):
            return True

        return False

    def _flat_winner(self, state):
        white_flats = 0
        black_flats = 0
        for r in range(self.BOARD_SIZE):
            for c in range(self.BOARD_SIZE):
                stack = state["board"][r][c]
                if stack and stack[-1]["type"] == "flat":
                    if stack[-1]["owner"] == "white":
                        white_flats += 1
                    else:
                        black_flats += 1
        if white_flats > black_flats:
            return "white"
        elif black_flats > white_flats:
            return "black"
        return "draw"


# ============================================================
# SECTION 2 — DISPLAY AND INPUT (Pygame)
# ============================================================

import pygame
import sys
import math

# ── Colour palette ──────────────────────────────────────────

COL_BG           = (42, 30, 22)
COL_BOARD        = (196, 162, 107)
COL_BOARD_DARK   = (178, 143, 90)
COL_BOARD_BORDER = (90, 58, 30)
COL_GRID_LINE    = (140, 105, 60)
COL_COORD_TEXT   = (210, 185, 145)

COL_WHITE_PIECE  = (240, 220, 175)
COL_WHITE_EDGE   = (200, 180, 135)
COL_BLACK_PIECE  = (82, 55, 35)
COL_BLACK_EDGE   = (55, 35, 20)

COL_SELECT       = (255, 220, 80, 120)
COL_LEGAL        = (100, 220, 100, 100)
COL_PATH         = (100, 160, 255, 100)
COL_TEXT          = (230, 215, 185)
COL_TEXT_DIM      = (160, 140, 110)
COL_TURN_WHITE   = (255, 240, 200)
COL_TURN_BLACK   = (160, 110, 70)
COL_BUTTON       = (110, 80, 50)
COL_BUTTON_HOVER = (140, 105, 65)
COL_BUTTON_TEXT  = (240, 225, 195)
COL_RESULT_BG    = (30, 20, 12, 200)

# ── Layout constants ────────────────────────────────────────

CELL_SIZE   = 85
BOARD_PAD   = 55   # space for coordinates on left / bottom
BOARD_X0    = BOARD_PAD + 15
BOARD_Y0    = 30
BOARD_PX    = CELL_SIZE * 6
PANEL_X     = BOARD_X0 + BOARD_PX + 30
PANEL_W     = 310
WIN_W       = PANEL_X + PANEL_W + 15
WIN_H       = BOARD_Y0 + BOARD_PX + BOARD_PAD + 20

FILES = "abcdef"
RANKS = "123456"


# ── Helper: algebraic label ─────────────────────────────────

def sq_label(r, c):
    return f"{FILES[c]}{RANKS[r]}"


# ── Piece drawing ───────────────────────────────────────────

def piece_colors(owner):
    if owner == "white":
        return COL_WHITE_PIECE, COL_WHITE_EDGE
    return COL_BLACK_PIECE, COL_BLACK_EDGE


def draw_flat(surface, cx, cy, owner, w=36, h=12):
    fill, edge = piece_colors(owner)
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.ellipse(surface, fill, rect)
    pygame.draw.ellipse(surface, edge, rect, 2)


def draw_standing(surface, cx, cy, owner, w=12, h=34):
    fill, edge = piece_colors(owner)
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surface, fill, rect, border_radius=3)
    pygame.draw.rect(surface, edge, rect, 2, border_radius=3)


def draw_capstone(surface, cx, cy, owner, radius=16):
    fill, edge = piece_colors(owner)
    pygame.draw.circle(surface, fill, (cx, cy), radius)
    pygame.draw.circle(surface, edge, (cx, cy), radius, 2)
    # Small inner dot
    pygame.draw.circle(surface, edge, (cx, cy), 5)


def draw_piece(surface, cx, cy, piece, scale=1.0):
    t = piece["type"]
    o = piece["owner"]
    if t == "flat":
        draw_flat(surface, cx, cy, o, w=int(36 * scale), h=int(12 * scale))
    elif t == "standing":
        draw_standing(surface, cx, cy, o, w=int(12 * scale), h=int(34 * scale))
    elif t == "capstone":
        draw_capstone(surface, cx, cy, o, radius=int(16 * scale))


# ── Board coordinate helpers ────────────────────────────────

def cell_screen_pos(r, c):
    """Top-left corner of cell (r, c) on screen.  Row 0 = rank 1 = bottom of display."""
    sx = BOARD_X0 + c * CELL_SIZE
    sy = BOARD_Y0 + (5 - r) * CELL_SIZE  # flip so rank 1 is at bottom
    return sx, sy


def cell_center(r, c):
    sx, sy = cell_screen_pos(r, c)
    return sx + CELL_SIZE // 2, sy + CELL_SIZE // 2


def screen_to_cell(mx, my):
    """Convert mouse position to board (row, col) or None."""
    c = (mx - BOARD_X0) // CELL_SIZE
    inv_r = (my - BOARD_Y0) // CELL_SIZE
    r = 5 - inv_r
    if 0 <= r < 6 and 0 <= c < 6:
        return r, c
    return None


# ── Overlay surface helper ──────────────────────────────────

def make_overlay(w, h, color):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(color)
    return s


# ── UI state machine ────────────────────────────────────────

PHASE_IDLE         = "idle"
PHASE_PLACE_TYPE   = "place_type"     # choosing piece type for placement
PHASE_CARRY        = "carry"          # choosing carry count
PHASE_DIRECTION    = "direction"      # choosing movement direction
PHASE_DROPS        = "drops"          # choosing drop counts step by step


class Button:
    def __init__(self, x, y, w, h, text, value):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.value = value

    def draw(self, surface, font, hover=False):
        col = COL_BUTTON_HOVER if hover else COL_BUTTON
        pygame.draw.rect(surface, col, self.rect, border_radius=6)
        pygame.draw.rect(surface, COL_BOARD_BORDER, self.rect, 2, border_radius=6)
        txt = font.render(self.text, True, COL_BUTTON_TEXT)
        tx = self.rect.centerx - txt.get_width() // 2
        ty = self.rect.centery - txt.get_height() // 2
        surface.blit(txt, (tx, ty))

    def contains(self, pos):
        return self.rect.collidepoint(pos)


# ── Main application ────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Tak  6×6")
    clock = pygame.time.Clock()

    font_lg  = pygame.font.SysFont("Georgia", 26, bold=True)
    font_md  = pygame.font.SysFont("Georgia", 18)
    font_sm  = pygame.font.SysFont("Georgia", 14)
    font_xs  = pygame.font.SysFont("Georgia", 12)
    font_coord = pygame.font.SysFont("Consolas", 15, bold=True)

    game = TakGame()
    state = game.create_initial_state()
    legal_moves = game.get_legal_moves(state, state["current_player"])

    # UI state
    phase = PHASE_IDLE
    sel_rc = None          # selected square (r, c)
    filtered = []          # legal moves filtered by current selections
    buttons = []           # dynamic action buttons
    carry_count = 0
    move_dir = None        # "north"/"south"/"east"/"west"
    partial_drops = []     # drops chosen so far
    move_path = []         # squares traversed so far in move
    hovered_cell = None
    message = ""
    move_history = []      # list of move strings for display

    # Pre-computed overlays
    sel_overlay   = make_overlay(CELL_SIZE, CELL_SIZE, COL_SELECT)
    legal_overlay = make_overlay(CELL_SIZE, CELL_SIZE, COL_LEGAL)
    path_overlay  = make_overlay(CELL_SIZE, CELL_SIZE, COL_PATH)

    def reset_ui():
        nonlocal phase, sel_rc, filtered, buttons, carry_count, move_dir, partial_drops, move_path, message
        phase = PHASE_IDLE
        sel_rc = None
        filtered = []
        buttons = []
        carry_count = 0
        move_dir = None
        partial_drops = []
        move_path = []
        message = ""

    def build_buttons(options, y_start=None):
        """Build a column of buttons in the panel for the given (label, value) pairs."""
        bx = PANEL_X + 15
        by = y_start if y_start else 380
        bw, bh = 130, 36
        gap = 6
        btn_list = []
        for label, val in options:
            btn_list.append(Button(bx, by, bw, bh, label, val))
            by += bh + gap
        return btn_list

    def apply_chosen_move(move):
        nonlocal state, legal_moves
        player = state["current_player"]
        # Build a human-readable notation
        notation = format_move(move, state)
        move_history.append(f"{player}: {notation}")
        state = game.apply_move(state, player, move)
        legal_moves = game.get_legal_moves(state, state["current_player"])
        reset_ui()

    def format_move(move, st):
        """Simple PTN-like notation."""
        sq = sq_label(move["row"], move["col"])
        if move["action"] == "place":
            t = move["piece_type"]
            if t == "flat":
                # During opening, note it's opponent's piece
                if st["turn_number"] <= 2:
                    return f"{sq} (opening)"
                return sq
            elif t == "standing":
                return f"S{sq}"
            else:
                return f"C{sq}"
        else:
            carry = move["carry"]
            direction = {
                "north": "+", "south": "-", "east": ">", "west": "<"
            }[move["direction"]]
            drops = "".join(str(d) for d in move["drops"])
            c_str = str(carry) if carry > 1 else ""
            d_str = drops if len(move["drops"]) > 1 or carry > 1 else ""
            return f"{c_str}{sq}{direction}{d_str}"

    def get_legal_squares():
        """Squares that are sources of at least one legal move."""
        squares = set()
        for m in legal_moves:
            squares.add((m["row"], m["col"]))
        return squares

    def get_legal_targets():
        """For highlighting: target squares of filtered moves."""
        targets = set()
        for m in filtered:
            if m["action"] == "place":
                targets.add((m["row"], m["col"]))
            elif m["action"] == "move":
                dr, dc = TakGame.DIRECTIONS[m["direction"]]
                r, c = m["row"], m["col"]
                for d in m["drops"]:
                    r += dr
                    c += dc
                targets.add((r, c))  # final destination
        return targets

    # ── Drawing functions ───────────────────────────────────

    def draw_board():
        # Board background
        board_rect = pygame.Rect(BOARD_X0 - 4, BOARD_Y0 - 4, BOARD_PX + 8, BOARD_PX + 8)
        pygame.draw.rect(screen, COL_BOARD_BORDER, board_rect, border_radius=4)

        for r in range(6):
            for c in range(6):
                sx, sy = cell_screen_pos(r, c)
                col = COL_BOARD if (r + c) % 2 == 0 else COL_BOARD_DARK
                pygame.draw.rect(screen, col, (sx, sy, CELL_SIZE, CELL_SIZE))
                pygame.draw.rect(screen, COL_GRID_LINE, (sx, sy, CELL_SIZE, CELL_SIZE), 1)

        # Coordinates: files (a-f) along bottom
        for c in range(6):
            sx, _ = cell_screen_pos(0, c)
            label = font_coord.render(FILES[c], True, COL_COORD_TEXT)
            screen.blit(label, (sx + CELL_SIZE // 2 - label.get_width() // 2,
                                BOARD_Y0 + BOARD_PX + 8))

        # Coordinates: ranks (1-6) along left
        for r in range(6):
            _, sy = cell_screen_pos(r, 0)
            label = font_coord.render(RANKS[r], True, COL_COORD_TEXT)
            screen.blit(label, (BOARD_X0 - 22, sy + CELL_SIZE // 2 - label.get_height() // 2))

    def draw_stacks():
        board = state["board"]
        for r in range(6):
            for c in range(6):
                stack = board[r][c]
                if not stack:
                    continue
                cx, cy = cell_center(r, c)

                # Draw mini stack indicators (bottom pieces as thin lines)
                height = len(stack)
                if height > 1:
                    for i in range(min(height - 1, 8)):
                        piece = stack[i]
                        fill, _ = piece_colors(piece["owner"])
                        iy = cy + 20 - i * 4
                        pygame.draw.rect(screen, fill, (cx - 16, iy, 32, 3), border_radius=1)
                        pygame.draw.rect(screen, COL_GRID_LINE, (cx - 16, iy, 32, 3), 1, border_radius=1)

                # Draw top piece
                top = stack[-1]
                top_y = cy - (min(height - 1, 8)) * 2
                draw_piece(screen, cx, top_y, top)

                # Stack height number
                if height > 1:
                    num = font_xs.render(str(height), True, COL_TEXT)
                    screen.blit(num, (cx + 22, cy + 16))

    def draw_highlights():
        # Highlight selected square
        if sel_rc:
            sx, sy = cell_screen_pos(*sel_rc)
            screen.blit(sel_overlay, (sx, sy))

        if phase == PHASE_IDLE:
            # Show which squares the current player can interact with (subtle)
            if not state["game_over"]:
                legal_sqs = get_legal_squares()
                # Don't highlight all legal squares in idle (too noisy for placement)
                # Only highlight if it's a movement-only situation or similar
                pass
        elif phase in (PHASE_PLACE_TYPE, PHASE_CARRY):
            # Selected square is highlighted above
            pass
        elif phase == PHASE_DIRECTION:
            # Highlight valid directions
            targets = set()
            for m in filtered:
                dr, dc = TakGame.DIRECTIONS[m["direction"]]
                targets.add((sel_rc[0] + dr, sel_rc[1] + dc))
            for (tr, tc) in targets:
                if 0 <= tr < 6 and 0 <= tc < 6:
                    sx, sy = cell_screen_pos(tr, tc)
                    screen.blit(legal_overlay, (sx, sy))
        elif phase == PHASE_DROPS:
            # Highlight the path taken
            for pr, pc in move_path:
                sx, sy = cell_screen_pos(pr, pc)
                screen.blit(path_overlay, (sx, sy))
            # Highlight valid next squares (should be exactly one: the next in direction)
            if filtered:
                # The next square to drop on
                dr, dc = TakGame.DIRECTIONS[move_dir]
                nr = move_path[-1][0] + dr if move_path else sel_rc[0] + dr
                nc = move_path[-1][1] + dc if move_path else sel_rc[1] + dc
                if 0 <= nr < 6 and 0 <= nc < 6:
                    sx, sy = cell_screen_pos(nr, nc)
                    screen.blit(legal_overlay, (sx, sy))

    def draw_panel():
        # Title
        title = font_lg.render("TAK  6×6", True, COL_TEXT)
        screen.blit(title, (PANEL_X + 15, 15))

        # Separator
        pygame.draw.line(screen, COL_BOARD_BORDER, (PANEL_X + 10, 52), (PANEL_X + PANEL_W - 10, 52), 2)

        # Turn indicator
        cp = state["current_player"]
        if state["game_over"]:
            w = state["winner"]
            if w == "draw":
                turn_text = "GAME OVER — DRAW"
                turn_col = COL_TEXT
            else:
                turn_text = f"GAME OVER — {w.upper()} WINS!"
                turn_col = COL_TURN_WHITE if w == "white" else COL_TURN_BLACK
            txt = font_md.render(turn_text, True, turn_col)
            screen.blit(txt, (PANEL_X + 15, 65))
        else:
            turn_col = COL_TURN_WHITE if cp == "white" else COL_TURN_BLACK
            turn_text = f"Turn {state['turn_number']}:  {cp.upper()}'s move"
            txt = font_md.render(turn_text, True, turn_col)
            screen.blit(txt, (PANEL_X + 15, 65))

            # Opening indicator
            if state["turn_number"] <= 2:
                opp = "black" if cp == "white" else "white"
                note = font_sm.render(f"(place {opp}'s flat stone)", True, COL_TEXT_DIM)
                screen.blit(note, (PANEL_X + 15, 90))

        # Piece indicator next to turn
        if not state["game_over"]:
            px = PANEL_X + 260
            py = 73
            dummy = {"owner": cp, "type": "flat"}
            draw_piece(screen, px, py, dummy, scale=0.8)

        # Reserves
        y = 118
        pygame.draw.line(screen, COL_BOARD_BORDER, (PANEL_X + 10, y), (PANEL_X + PANEL_W - 10, y), 1)
        y += 10

        for p in ["white", "black"]:
            res = state["reserves"][p]
            col = COL_TURN_WHITE if p == "white" else COL_TURN_BLACK
            txt = font_md.render(f"{p.capitalize()}", True, col)
            screen.blit(txt, (PANEL_X + 15, y))
            info = font_sm.render(f"Stones: {res['stones']}   Capstones: {res['capstones']}", True, COL_TEXT_DIM)
            screen.blit(info, (PANEL_X + 100, y + 3))
            y += 30

        # Separator
        y += 5
        pygame.draw.line(screen, COL_BOARD_BORDER, (PANEL_X + 10, y), (PANEL_X + PANEL_W - 10, y), 1)
        y += 10

        # Selected square info
        if sel_rc:
            r, c = sel_rc
            stack = state["board"][r][c]
            lbl = font_md.render(f"Selected: {sq_label(r, c)}", True, COL_TEXT)
            screen.blit(lbl, (PANEL_X + 15, y))
            y += 25
            if stack:
                info = font_sm.render(f"Stack height: {len(stack)}", True, COL_TEXT_DIM)
                screen.blit(info, (PANEL_X + 15, y))
                y += 20
                # Show stack contents (bottom to top)
                for i, piece in enumerate(stack):
                    ptype = piece["type"][0].upper()
                    pown = piece["owner"][0].upper()
                    col = COL_TURN_WHITE if piece["owner"] == "white" else COL_TURN_BLACK
                    idx_str = "TOP" if i == len(stack) - 1 else str(i + 1)
                    txt = font_xs.render(f"  {idx_str}: {piece['owner']} {piece['type']}", True, col)
                    screen.blit(txt, (PANEL_X + 15, y))
                    y += 16
            else:
                info = font_sm.render("Empty square", True, COL_TEXT_DIM)
                screen.blit(info, (PANEL_X + 15, y))
                y += 20
        elif hovered_cell and not state["game_over"]:
            r, c = hovered_cell
            stack = state["board"][r][c]
            lbl = font_sm.render(f"Hover: {sq_label(r, c)}", True, COL_TEXT_DIM)
            screen.blit(lbl, (PANEL_X + 15, y))
            y += 22
            if stack:
                top = stack[-1]
                info = font_xs.render(f"{top['owner']} {top['type']} (×{len(stack)})", True, COL_TEXT_DIM)
                screen.blit(info, (PANEL_X + 15, y))
            y += 20

        # Phase-specific instructions and buttons
        y = max(y + 10, 380)
        if not state["game_over"]:
            if phase == PHASE_IDLE:
                msg = "Click a square to act"
                txt = font_sm.render(msg, True, COL_TEXT_DIM)
                screen.blit(txt, (PANEL_X + 15, y))
            elif phase == PHASE_PLACE_TYPE:
                msg = "Choose piece to place:"
                txt = font_sm.render(msg, True, COL_TEXT)
                screen.blit(txt, (PANEL_X + 15, y - 25))
            elif phase == PHASE_CARRY:
                msg = "Choose how many to carry:"
                txt = font_sm.render(msg, True, COL_TEXT)
                screen.blit(txt, (PANEL_X + 15, y - 25))
            elif phase == PHASE_DIRECTION:
                msg = "Click adjacent square for direction"
                txt = font_sm.render(msg, True, COL_TEXT)
                screen.blit(txt, (PANEL_X + 15, y - 25))
            elif phase == PHASE_DROPS:
                remaining = carry_count - sum(partial_drops)
                msg = f"Drop pieces ({remaining} remaining):"
                txt = font_sm.render(msg, True, COL_TEXT)
                screen.blit(txt, (PANEL_X + 15, y - 25))

        # Draw buttons
        mx, my = pygame.mouse.get_pos()
        for btn in buttons:
            btn.draw(screen, font_md, hover=btn.contains((mx, my)))

        # Message
        if message:
            txt = font_sm.render(message, True, (255, 180, 80))
            screen.blit(txt, (PANEL_X + 15, WIN_H - 80))

        # Cancel hint
        if phase != PHASE_IDLE:
            txt = font_xs.render("Right-click or ESC to cancel", True, COL_TEXT_DIM)
            screen.blit(txt, (PANEL_X + 15, WIN_H - 50))

        # Move history (bottom of panel, small)
        hist_y = WIN_H - 30
        if move_history:
            last = move_history[-1]
            txt = font_xs.render(f"Last: {last}", True, COL_TEXT_DIM)
            screen.blit(txt, (PANEL_X + 15, hist_y))

    def draw_game_over_overlay():
        if not state["game_over"]:
            return
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        w = state["winner"]
        if w == "draw":
            text = "DRAW!"
            col = COL_TEXT
        else:
            text = f"{w.upper()} WINS!"
            col = COL_TURN_WHITE if w == "white" else COL_TURN_BLACK

        # Check win type
        # Determine if road or flat win
        active_prev = "black" if state["current_player"] == "white" else "white"
        inactive_prev = "white" if active_prev == "white" else "black"
        active_road = game._has_road(state, active_prev)
        inactive_road = game._has_road(state, inactive_prev)
        if active_road or inactive_road:
            win_type = "Road Victory!"
        elif w == "draw":
            win_type = "Flat scores tied"
        else:
            win_type = "Flat Victory!"

        txt1 = font_lg.render(text, True, col)
        txt2 = font_md.render(win_type, True, COL_TEXT)
        txt3 = font_sm.render("Press R to restart", True, COL_TEXT_DIM)

        cx = WIN_W // 2
        cy = WIN_H // 2
        # Background box
        box_w, box_h = 350, 140
        box = pygame.Rect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
        pygame.draw.rect(screen, (40, 28, 18), box, border_radius=12)
        pygame.draw.rect(screen, COL_BOARD_BORDER, box, 3, border_radius=12)

        screen.blit(txt1, (cx - txt1.get_width() // 2, cy - 45))
        screen.blit(txt2, (cx - txt2.get_width() // 2, cy - 5))
        screen.blit(txt3, (cx - txt3.get_width() // 2, cy + 35))

    # ── Event handling ──────────────────────────────────────

    def handle_click(pos):
        nonlocal phase, sel_rc, filtered, buttons, carry_count, move_dir, partial_drops, move_path, message

        mx, my = pos

        # Check button clicks first
        for btn in buttons:
            if btn.contains(pos):
                handle_button(btn.value)
                return

        # Board click
        cell = screen_to_cell(mx, my)
        if cell is None:
            return

        r, c = cell

        if phase == PHASE_IDLE:
            handle_idle_click(r, c)
        elif phase == PHASE_DIRECTION:
            handle_direction_click(r, c)
        elif phase == PHASE_DROPS:
            handle_drop_click(r, c)
        else:
            # Clicking board while in button-selection phase: treat as cancel + new selection
            reset_ui()
            handle_idle_click(r, c)

    def handle_idle_click(r, c):
        nonlocal phase, sel_rc, filtered, buttons, message

        if state["game_over"]:
            return

        player = state["current_player"]
        board = state["board"]
        stack = board[r][c]
        turn = state["turn_number"]

        if turn <= 2:
            # Opening: can only place on empty squares
            if not stack:
                # Auto-place flat (only option during opening)
                matching = [m for m in legal_moves if m["row"] == r and m["col"] == c]
                if matching:
                    apply_chosen_move(matching[0])
            return

        # Normal turn
        if not stack:
            # Empty square → placement
            matching = [m for m in legal_moves if m["action"] == "place" and m["row"] == r and m["col"] == c]
            if not matching:
                return
            sel_rc = (r, c)
            filtered = matching
            # Determine available types
            types = list(set(m["piece_type"] for m in matching))
            if len(types) == 1:
                # Auto-place if only one option
                apply_chosen_move(matching[0])
                return
            options = []
            for t in sorted(types):
                label = {"flat": "Flat (F)", "standing": "Standing (S)", "capstone": "Capstone (C)"}[t]
                options.append((label, t))
            phase = PHASE_PLACE_TYPE
            buttons = build_buttons(options)

        elif stack[-1]["owner"] == player:
            # Own stack → movement
            matching = [m for m in legal_moves if m["action"] == "move" and m["row"] == r and m["col"] == c]
            if not matching:
                # Maybe only placement is legal from this position? Check if placement moves exist
                message = "No moves from this stack"
                return
            sel_rc = (r, c)
            filtered = matching
            max_carry = min(len(stack), TakGame.CARRY_LIMIT)
            available_carries = sorted(set(m["carry"] for m in matching))
            if len(available_carries) == 1:
                # Auto-select carry
                carry_count_val = available_carries[0]
                select_carry(carry_count_val)
                return
            options = [(f"Carry {k}", k) for k in available_carries]
            phase = PHASE_CARRY
            buttons = build_buttons(options)

        # Else: opponent's stack, ignore

    def select_carry(val):
        nonlocal carry_count, phase, filtered, buttons
        carry_count = val
        filtered = [m for m in filtered if m["carry"] == carry_count]
        available_dirs = sorted(set(m["direction"] for m in filtered))
        if len(available_dirs) == 1:
            select_direction(available_dirs[0])
            return
        phase = PHASE_DIRECTION
        buttons = []
        # Direction selected by clicking adjacent square (see draw_highlights)

    def select_direction(dir_name):
        nonlocal move_dir, phase, filtered, buttons, partial_drops, move_path
        move_dir = dir_name
        filtered = [m for m in filtered if m["direction"] == move_dir]
        partial_drops = []
        move_path = []

        # Check if only one move remains
        if len(filtered) == 1:
            apply_chosen_move(filtered[0])
            return

        phase = PHASE_DROPS
        update_drop_buttons()

    def update_drop_buttons():
        nonlocal buttons
        remaining = carry_count - sum(partial_drops)
        if remaining <= 0:
            return

        step = len(partial_drops)
        # Find valid drop counts for this step
        valid_drops = set()
        for m in filtered:
            if len(m["drops"]) > step:
                # Check if the partial drops so far match
                if m["drops"][:step] == partial_drops:
                    valid_drops.add(m["drops"][step])

        if not valid_drops:
            return

        if len(valid_drops) == 1:
            # Auto-drop
            d = valid_drops.pop()
            execute_drop(d)
            return

        options = [(f"Drop {d}", d) for d in sorted(valid_drops)]
        buttons = build_buttons(options)

    def execute_drop(d):
        nonlocal partial_drops, move_path, filtered, buttons

        partial_drops.append(d)

        # Update path
        dr, dc = TakGame.DIRECTIONS[move_dir]
        if move_path:
            last_r, last_c = move_path[-1]
        else:
            last_r, last_c = sel_rc
        move_path.append((last_r + dr, last_c + dc))

        # Filter moves by partial drops
        filtered = [m for m in filtered if m["drops"][:len(partial_drops)] == partial_drops]

        remaining = carry_count - sum(partial_drops)
        if remaining == 0:
            # Move complete
            if len(filtered) == 1:
                apply_chosen_move(filtered[0])
                return
            # Should not happen if logic is correct, but just in case
            if filtered:
                apply_chosen_move(filtered[0])
            return

        # Check if only one move remains
        if len(filtered) == 1:
            apply_chosen_move(filtered[0])
            return

        update_drop_buttons()

    def handle_button(value):
        nonlocal phase
        if phase == PHASE_PLACE_TYPE:
            matching = [m for m in filtered if m["piece_type"] == value]
            if matching:
                apply_chosen_move(matching[0])
        elif phase == PHASE_CARRY:
            select_carry(value)
        elif phase == PHASE_DROPS:
            execute_drop(value)

    def handle_direction_click(r, c):
        if sel_rc is None:
            return
        sr, sc = sel_rc
        dr, dc = r - sr, c - sc
        # Must be adjacent
        if abs(dr) + abs(dc) != 1:
            return
        # Map to direction name
        dir_map = {(1, 0): "north", (-1, 0): "south", (0, 1): "east", (0, -1): "west"}
        dir_name = dir_map.get((dr, dc))
        if dir_name and dir_name in set(m["direction"] for m in filtered):
            select_direction(dir_name)

    def handle_drop_click(r, c):
        # The user clicks the next square in the path to confirm a drop
        # Determine which square we expect
        dr, dc = TakGame.DIRECTIONS[move_dir]
        if move_path:
            exp_r, exp_c = move_path[-1][0] + dr, move_path[-1][1] + dc
        else:
            exp_r, exp_c = sel_rc[0] + dr, sel_rc[1] + dc

        if (r, c) == (exp_r, exp_c):
            # Valid click on expected next square
            # Find valid drop counts
            step = len(partial_drops)
            valid_drops = set()
            for m in filtered:
                if len(m["drops"]) > step and m["drops"][:step] == partial_drops:
                    valid_drops.add(m["drops"][step])
            if len(valid_drops) == 1:
                execute_drop(valid_drops.pop())
            # else buttons should already be shown

    def handle_key(key):
        nonlocal state, legal_moves, move_history
        if key == pygame.K_ESCAPE:
            reset_ui()
        elif key == pygame.K_r:
            state = game.create_initial_state()
            legal_moves = game.get_legal_moves(state, state["current_player"])
            move_history = []
            reset_ui()
        elif phase == PHASE_PLACE_TYPE:
            km = {pygame.K_f: "flat", pygame.K_s: "standing", pygame.K_c: "capstone"}
            if key in km:
                val = km[key]
                matching = [m for m in filtered if m["piece_type"] == val]
                if matching:
                    apply_chosen_move(matching[0])
        elif phase == PHASE_CARRY:
            if pygame.K_1 <= key <= pygame.K_6:
                val = key - pygame.K_0
                if val in set(m["carry"] for m in filtered):
                    select_carry(val)
        elif phase == PHASE_DROPS:
            if pygame.K_1 <= key <= pygame.K_6:
                val = key - pygame.K_0
                step = len(partial_drops)
                valid = set()
                for m in filtered:
                    if len(m["drops"]) > step and m["drops"][:step] == partial_drops:
                        valid.add(m["drops"][step])
                if val in valid:
                    execute_drop(val)

    # ── Main loop ───────────────────────────────────────────

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        hovered_cell = screen_to_cell(mx, my)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    handle_click(event.pos)
                elif event.button == 3:  # Right click: cancel
                    reset_ui()
            elif event.type == pygame.KEYDOWN:
                handle_key(event.key)

        # Draw
        screen.fill(COL_BG)
        draw_board()
        draw_highlights()
        draw_stacks()
        draw_panel()

        if state["game_over"]:
            draw_game_over_overlay()

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
