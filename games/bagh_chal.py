"""
Bagh Chal — Tigers and Goats
A complete implementation with game logic and Pygame display.
"""

import copy
import json

# ============================================================================
# SECTION 1 — GAME LOGIC CLASS
# No Pygame imports. Fully self-contained. JSON-serializable state.
# ============================================================================

class BaghChalLogic:
    """
    Complete Bagh Chal game logic.
    All state is plain Python dicts/lists/strings/ints/bools.
    """

    # Pre-computed adjacency list for the 5x5 board
    ADJACENCY = {
        0:  [1, 5, 6],
        1:  [0, 2, 6],
        2:  [1, 3, 6, 7, 8],
        3:  [2, 4, 8],
        4:  [3, 8, 9],
        5:  [0, 6, 10],
        6:  [0, 1, 2, 5, 7, 10, 11, 12],
        7:  [2, 6, 8, 12],
        8:  [2, 3, 4, 7, 9, 12, 13, 14],
        9:  [4, 8, 14],
        10: [5, 6, 11, 15, 16],
        11: [6, 10, 12, 16],
        12: [6, 7, 8, 11, 13, 16, 17, 18],
        13: [8, 12, 14, 18],
        14: [8, 9, 13, 18, 19],
        15: [10, 16, 20],
        16: [10, 11, 12, 15, 17, 20, 21, 22],
        17: [12, 16, 18, 22],
        18: [12, 13, 14, 17, 19, 22, 23, 24],
        19: [14, 18, 24],
        20: [15, 16, 21],
        21: [16, 20, 22],
        22: [16, 17, 18, 21, 23],
        23: [18, 22, 24],
        24: [18, 19, 23],
    }

    def get_name(self):
        return "Bagh Chal"

    def get_num_players(self):
        return 2

    def create_initial_state(self):
        """Return the initial game state as a plain dict."""
        # board: list of 25 entries, each "T", "G", or ""
        board = [""] * 25
        board[0] = "T"
        board[4] = "T"
        board[20] = "T"
        board[24] = "T"

        state = {
            "board": board,
            "goats_in_reserve": 20,
            "goats_captured": 0,
            "turn": "goat",          # "goat" or "tiger"
            "history": [],           # list of board-state strings for repetition
            "repetition_mode": "B",  # "A" = strict no-repeat, "B" = threefold draw, "none"
            "game_over": False,
            "winner": None,          # "goat", "tiger", "draw", or None
        }
        # Record initial state in history
        state["history"].append(self._state_key(state))
        return state

    # ----- helpers -----

    @staticmethod
    def _rc(node_id):
        return node_id // 5, node_id % 5

    @staticmethod
    def _id(row, col):
        return 5 * row + col

    def _state_key(self, state):
        """A string that uniquely identifies board + side-to-move."""
        return "".join(state["board"]) + "|" + state["turn"]

    def _is_adjacent(self, a, b):
        return b in self.ADJACENCY[a]

    # ----- public interface -----

    def get_current_player(self, state):
        return state["turn"]

    def get_legal_moves(self, state):
        """
        Return list of legal moves for the current player.
        Move formats (all plain dicts):
          Goat placement: {"type": "place", "to": node_id}
          Slide:          {"type": "move", "from": node_id, "to": node_id}
          Capture:        {"type": "capture", "from": origin, "over": jumped, "to": dest}
        """
        if state["game_over"]:
            return []

        player = state["turn"]
        moves = []

        if player == "goat":
            moves = self._goat_moves(state)
        else:
            moves = self._tiger_moves(state)

        # Filter out moves that violate repetition rules
        if state["repetition_mode"] == "A" and state["goats_in_reserve"] == 0:
            moves = self._filter_repetition_strict(state, moves)

        return moves

    def apply_move(self, state, player, move):
        """Apply move and return a NEW state (deep copy)."""
        ns = copy.deepcopy(state)
        board = ns["board"]

        if move["type"] == "place":
            board[move["to"]] = "G"
            ns["goats_in_reserve"] -= 1
        elif move["type"] == "move":
            piece = board[move["from"]]
            board[move["from"]] = ""
            board[move["to"]] = piece
        elif move["type"] == "capture":
            board[move["from"]] = ""
            board[move["over"]] = ""
            board[move["to"]] = "T"
            ns["goats_captured"] += 1

        # Switch turn
        ns["turn"] = "tiger" if player == "goat" else "goat"

        # Record in history
        key = self._state_key(ns)
        ns["history"].append(key)

        # Check win/draw
        self._check_game_over(ns)

        return ns

    def check_game_over(self, state):
        """
        Return winner identifier: "tiger", "goat", "draw", or None.
        """
        if state["game_over"]:
            return state["winner"]
        return None

    # ----- internal move generation -----

    def _goat_moves(self, state):
        board = state["board"]
        moves = []
        if state["goats_in_reserve"] > 0:
            # Phase 1: placement only
            for i in range(25):
                if board[i] == "":
                    moves.append({"type": "place", "to": i})
        else:
            # Phase 2: slide goats
            for i in range(25):
                if board[i] == "G":
                    for nb in self.ADJACENCY[i]:
                        if board[nb] == "":
                            moves.append({"type": "move", "from": i, "to": nb})
        return moves

    def _tiger_moves(self, state):
        board = state["board"]
        moves = []
        for i in range(25):
            if board[i] != "T":
                continue
            # Slides
            for nb in self.ADJACENCY[i]:
                if board[nb] == "":
                    moves.append({"type": "move", "from": i, "to": nb})
            # Captures
            for nb in self.ADJACENCY[i]:
                if board[nb] != "G":
                    continue
                # Compute landing node
                r_o, c_o = self._rc(i)
                r_i, c_i = self._rc(nb)
                r_d = 2 * r_i - r_o
                c_d = 2 * c_i - c_o
                if r_d < 0 or r_d > 4 or c_d < 0 or c_d > 4:
                    continue
                dest = self._id(r_d, c_d)
                if board[dest] != "":
                    continue
                # Check that I->D is also a valid board edge
                if not self._is_adjacent(nb, dest):
                    continue
                moves.append({"type": "capture", "from": i, "over": nb, "to": dest})
        return moves

    def _filter_repetition_strict(self, state, moves):
        """Mode A: remove moves that recreate any previous board state."""
        history_set = set(state["history"])
        filtered = []
        for m in moves:
            ns = self.apply_move(state, state["turn"], m)
            key = self._state_key(ns)
            # The key was already appended in apply_move; check against old history
            if key not in history_set:
                filtered.append(m)
        return filtered if filtered else moves  # if ALL moves repeat, allow them (avoid deadlock)

    def _check_game_over(self, state):
        """Mutate state to mark game_over and winner if applicable."""
        # Tiger wins by capturing 5 goats
        if state["goats_captured"] >= 5:
            state["game_over"] = True
            state["winner"] = "tiger"
            return

        # Threefold repetition draw (Mode B)
        if state["repetition_mode"] == "B":
            key = self._state_key(state)
            if state["history"].count(key) >= 3:
                state["game_over"] = True
                state["winner"] = "draw"
                return

        # Check if current player has no legal moves
        # (We must check without repetition filtering to avoid recursion)
        current = state["turn"]
        if current == "goat":
            raw_moves = self._goat_moves(state)
        else:
            raw_moves = self._tiger_moves(state)

        if len(raw_moves) == 0:
            if current == "tiger":
                # Tigers have no moves -> Goat wins
                state["game_over"] = True
                state["winner"] = "goat"
            else:
                # Goats have no moves -> Tiger wins
                state["game_over"] = True
                state["winner"] = "tiger"


# ============================================================================
# SECTION 2 — DISPLAY AND INPUT (Pygame)
# ============================================================================

import pygame
import sys
import math

# Colors
BG_COLOR = (42, 40, 48)
BOARD_COLOR = (205, 170, 110)
BOARD_BORDER = (120, 90, 50)
LINE_COLOR = (90, 70, 45)
DIAG_LINE_COLOR = (110, 85, 55)
NODE_BG = (190, 160, 100)

TIGER_COLOR = (200, 55, 40)
TIGER_OUTLINE = (140, 30, 20)
GOAT_COLOR = (230, 220, 200)
GOAT_OUTLINE = (140, 130, 115)

HIGHLIGHT_PLACE = (100, 200, 100, 140)
HIGHLIGHT_MOVE = (80, 180, 255, 140)
HIGHLIGHT_CAPTURE = (255, 80, 80, 140)
SELECTED_COLOR = (255, 220, 60)

TEXT_COLOR = (230, 225, 215)
DIM_TEXT = (160, 155, 145)
GOAT_LABEL_COLOR = (200, 195, 180)
TIGER_LABEL_COLOR = (220, 90, 75)

WINNER_BG = (0, 0, 0, 180)


class BaghChalDisplay:
    def __init__(self):
        pygame.init()
        self.logic = BaghChalLogic()
        self.state = self.logic.create_initial_state()

        # Window
        self.width = 900
        self.height = 750
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Bagh Chal — Tigers and Goats")

        # Board layout
        self.board_x = 80
        self.board_y = 100
        self.cell_size = 130
        self.board_size = self.cell_size * 4

        # Piece sizes
        self.piece_radius = 22
        self.node_radius = 6

        # Fonts
        self.font_large = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_med = pygame.font.SysFont("Arial", 22)
        self.font_small = pygame.font.SysFont("Arial", 16)
        self.font_coord = pygame.font.SysFont("Arial", 14)
        self.font_winner = pygame.font.SysFont("Arial", 44, bold=True)

        # Interaction state
        self.selected_node = None
        self.legal_moves = []
        self.hover_node = None

        self.clock = pygame.time.Clock()

        self._refresh_legal_moves()

    def _refresh_legal_moves(self):
        self.legal_moves = self.logic.get_legal_moves(self.state)
        self.selected_node = None

    def _node_pos(self, node_id):
        r, c = node_id // 5, node_id % 5
        x = self.board_x + c * self.cell_size
        y = self.board_y + r * self.cell_size
        return x, y

    def _node_from_pos(self, mx, my):
        """Return node_id closest to mouse if within click radius, else None."""
        best = None
        best_dist = 30  # click tolerance
        for i in range(25):
            nx, ny = self._node_pos(i)
            d = math.hypot(mx - nx, my - ny)
            if d < best_dist:
                best_dist = d
                best = i
        return best

    def _draw_board(self):
        # Board background
        pad = 35
        rect = pygame.Rect(
            self.board_x - pad, self.board_y - pad,
            self.board_size + 2 * pad, self.board_size + 2 * pad
        )
        pygame.draw.rect(self.screen, BOARD_COLOR, rect, border_radius=10)
        pygame.draw.rect(self.screen, BOARD_BORDER, rect, 3, border_radius=10)

        # Draw lines
        for node_id in range(25):
            x1, y1 = self._node_pos(node_id)
            for nb in self.logic.ADJACENCY[node_id]:
                if nb > node_id:
                    x2, y2 = self._node_pos(nb)
                    r1, c1 = self.logic._rc(node_id)
                    r2, c2 = self.logic._rc(nb)
                    is_diag = abs(r1 - r2) == 1 and abs(c1 - c2) == 1
                    color = DIAG_LINE_COLOR if is_diag else LINE_COLOR
                    width = 1 if is_diag else 2
                    pygame.draw.line(self.screen, color, (x1, y1), (x2, y2), width)

        # Draw node dots
        for i in range(25):
            x, y = self._node_pos(i)
            pygame.draw.circle(self.screen, LINE_COLOR, (x, y), self.node_radius)

        # Coordinate labels
        for c in range(5):
            x = self.board_x + c * self.cell_size
            label = self.font_coord.render(str(c), True, DIM_TEXT)
            self.screen.blit(label, (x - label.get_width() // 2, self.board_y - 30))
            self.screen.blit(label, (x - label.get_width() // 2, self.board_y + self.board_size + 14))
        for r in range(5):
            y = self.board_y + r * self.cell_size
            label = self.font_coord.render(str(r), True, DIM_TEXT)
            self.screen.blit(label, (self.board_x - 24 - label.get_width() // 2, y - label.get_height() // 2))

    def _draw_highlights(self):
        """Highlight legal destinations for current selection or placement."""
        player = self.state["turn"]
        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        if player == "goat" and self.state["goats_in_reserve"] > 0:
            # Phase 1: highlight all empty nodes
            if self.selected_node is None:
                for m in self.legal_moves:
                    if m["type"] == "place":
                        x, y = self._node_pos(m["to"])
                        pygame.draw.circle(surf, HIGHLIGHT_PLACE, (x, y), self.piece_radius + 4)
        elif self.selected_node is not None:
            # Show destinations for selected piece
            for m in self.legal_moves:
                if m.get("from") == self.selected_node:
                    dest = m["to"]
                    x, y = self._node_pos(dest)
                    color = HIGHLIGHT_CAPTURE if m["type"] == "capture" else HIGHLIGHT_MOVE
                    pygame.draw.circle(surf, color, (x, y), self.piece_radius + 4)
                    # Also highlight the captured goat
                    if m["type"] == "capture":
                        ox, oy = self._node_pos(m["over"])
                        pygame.draw.circle(surf, (255, 50, 50, 90), (ox, oy), self.piece_radius + 6)

        self.screen.blit(surf, (0, 0))

    def _draw_pieces(self):
        board = self.state["board"]
        for i in range(25):
            if board[i] == "":
                continue
            x, y = self._node_pos(i)

            # Selection ring
            if i == self.selected_node:
                pygame.draw.circle(self.screen, SELECTED_COLOR, (x, y), self.piece_radius + 5, 3)

            if board[i] == "T":
                # Tiger: filled circle with cross/stripe
                pygame.draw.circle(self.screen, TIGER_COLOR, (x, y), self.piece_radius)
                pygame.draw.circle(self.screen, TIGER_OUTLINE, (x, y), self.piece_radius, 2)
                # Stripes
                for dy in [-7, 0, 7]:
                    pygame.draw.line(self.screen, TIGER_OUTLINE,
                                     (x - 10, y + dy), (x + 10, y + dy), 2)
                # T label
                lbl = self.font_small.render("T", True, (255, 255, 255))
                self.screen.blit(lbl, (x - lbl.get_width() // 2, y - lbl.get_height() // 2))
            else:
                # Goat: filled circle
                pygame.draw.circle(self.screen, GOAT_COLOR, (x, y), self.piece_radius)
                pygame.draw.circle(self.screen, GOAT_OUTLINE, (x, y), self.piece_radius, 2)
                lbl = self.font_small.render("G", True, (60, 55, 45))
                self.screen.blit(lbl, (x - lbl.get_width() // 2, y - lbl.get_height() // 2))

    def _draw_info_panel(self):
        """Draw turn info, goat reserve, captured count."""
        # Right side panel
        px = self.board_x + self.board_size + 80
        py = self.board_y

        # Title
        title = self.font_large.render("Bagh Chal", True, TEXT_COLOR)
        self.screen.blit(title, (self.width // 2 - title.get_width() // 2, 20))

        # Turn indicator
        turn = self.state["turn"]
        turn_text = "GOAT'S TURN" if turn == "goat" else "TIGER'S TURN"
        turn_color = GOAT_LABEL_COLOR if turn == "goat" else TIGER_LABEL_COLOR
        turn_surf = self.font_med.render(turn_text, True, turn_color)
        self.screen.blit(turn_surf, (px, py))

        # Phase info
        phase = "Phase 1 — Placement" if self.state["goats_in_reserve"] > 0 else "Phase 2 — Movement"
        phase_surf = self.font_small.render(phase, True, DIM_TEXT)
        self.screen.blit(phase_surf, (px, py + 35))

        # Goats in reserve
        py += 80
        res_text = f"Goats in reserve: {self.state['goats_in_reserve']}"
        res_surf = self.font_med.render(res_text, True, GOAT_LABEL_COLOR)
        self.screen.blit(res_surf, (px, py))

        # Draw reserve goat icons (mini circles)
        gy = py + 30
        for i in range(self.state["goats_in_reserve"]):
            row_i = i // 5
            col_i = i % 5
            gx = px + col_i * 24 + 10
            gy2 = gy + row_i * 24
            pygame.draw.circle(self.screen, GOAT_COLOR, (gx, gy2), 8)
            pygame.draw.circle(self.screen, GOAT_OUTLINE, (gx, gy2), 8, 1)

        # Captured goats
        py += 140
        cap_text = f"Goats captured: {self.state['goats_captured']} / 5"
        cap_surf = self.font_med.render(cap_text, True, TIGER_LABEL_COLOR)
        self.screen.blit(cap_surf, (px, py))

        # Draw captured goat icons (X'd out)
        cy = py + 30
        for i in range(self.state["goats_captured"]):
            cx = px + i * 28 + 10
            pygame.draw.circle(self.screen, (100, 90, 80), (cx, cy), 8)
            pygame.draw.line(self.screen, (200, 50, 40), (cx - 5, cy - 5), (cx + 5, cy + 5), 2)
            pygame.draw.line(self.screen, (200, 50, 40), (cx - 5, cy + 5), (cx + 5, cy - 5), 2)

        # Goats on board
        py += 70
        goats_on_board = self.state["board"].count("G")
        gob_text = f"Goats on board: {goats_on_board}"
        gob_surf = self.font_small.render(gob_text, True, DIM_TEXT)
        self.screen.blit(gob_surf, (px, py))

        # Instructions
        py += 50
        if not self.state["game_over"]:
            if self.state["turn"] == "goat" and self.state["goats_in_reserve"] > 0:
                instr = "Click empty node to place goat"
            elif self.selected_node is not None:
                instr = "Click destination or elsewhere to deselect"
            else:
                instr = "Click a piece to select, then click destination"
            instr_surf = self.font_small.render(instr, True, DIM_TEXT)
            self.screen.blit(instr_surf, (px, py))

    def _draw_game_over(self):
        if not self.state["game_over"]:
            return
        # Overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        winner = self.state["winner"]
        if winner == "draw":
            text = "GAME DRAWN"
            color = (200, 200, 100)
        elif winner == "tiger":
            text = "TIGERS WIN!"
            color = TIGER_LABEL_COLOR
        else:
            text = "GOATS WIN!"
            color = (150, 220, 150)

        surf = self.font_winner.render(text, True, color)
        self.screen.blit(surf, (self.width // 2 - surf.get_width() // 2,
                                self.height // 2 - surf.get_height() // 2 - 20))

        sub = self.font_med.render("Press R to restart or Q to quit", True, TEXT_COLOR)
        self.screen.blit(sub, (self.width // 2 - sub.get_width() // 2,
                               self.height // 2 + 30))

    def _handle_click(self, mx, my):
        if self.state["game_over"]:
            return

        node = self._node_from_pos(mx, my)
        if node is None:
            self.selected_node = None
            return

        player = self.state["turn"]

        # Phase 1 goat placement
        if player == "goat" and self.state["goats_in_reserve"] > 0:
            for m in self.legal_moves:
                if m["type"] == "place" and m["to"] == node:
                    self.state = self.logic.apply_move(self.state, player, m)
                    self._refresh_legal_moves()
                    return
            return

        # Phase 2 or tiger turn: select then move
        if self.selected_node is None:
            # Select a piece belonging to current player
            piece = "G" if player == "goat" else "T"
            if self.state["board"][node] == piece:
                # Check if this piece has any legal moves
                has_moves = any(m.get("from") == node for m in self.legal_moves)
                if has_moves:
                    self.selected_node = node
            return

        # A piece is already selected — try to move there
        if node == self.selected_node:
            self.selected_node = None
            return

        # Try to find a matching move
        for m in self.legal_moves:
            if m.get("from") == self.selected_node and m["to"] == node:
                self.state = self.logic.apply_move(self.state, player, m)
                self._refresh_legal_moves()
                return

        # Clicked a different own piece — reselect
        piece = "G" if player == "goat" else "T"
        if self.state["board"][node] == piece:
            has_moves = any(m.get("from") == node for m in self.legal_moves)
            if has_moves:
                self.selected_node = node
            else:
                self.selected_node = None
        else:
            self.selected_node = None

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(*event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_r:
                        self.state = self.logic.create_initial_state()
                        self._refresh_legal_moves()

            # Draw
            self.screen.fill(BG_COLOR)
            self._draw_board()
            self._draw_highlights()
            self._draw_pieces()
            self._draw_info_panel()
            self._draw_game_over()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    game = BaghChalDisplay()
    game.run()
