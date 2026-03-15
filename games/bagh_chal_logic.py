"""Bagh Chal (Tigers and Goats) — server-side game logic.

Implements the full Bagh Chal ruleset via the AbstractBoardGame interface.
No Pygame imports.  Player 1 = Goats, Player 2 = Tigers.
"""

import copy
import math

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# Piece constants
EMPTY = ""
TIGER = "T"
GOAT = "G"

# Player mapping: 1 = Goats, 2 = Tigers
PLAYER_GOAT = 1
PLAYER_TIGER = 2

# Pre-computed adjacency list for the 5x5 board (from rules §2.4)
ADJACENCY = [
    [1, 5, 6],                          # 0
    [0, 2, 6],                          # 1
    [1, 3, 6, 7, 8],                    # 2
    [2, 4, 8],                          # 3
    [3, 8, 9],                          # 4
    [0, 6, 10],                         # 5
    [0, 1, 2, 5, 7, 10, 11, 12],        # 6
    [2, 6, 8, 12],                      # 7
    [2, 3, 4, 7, 9, 12, 13, 14],        # 8
    [4, 8, 14],                         # 9
    [5, 6, 11, 15, 16],                 # 10
    [6, 10, 12, 16],                    # 11
    [6, 7, 8, 11, 13, 16, 17, 18],      # 12
    [8, 12, 14, 18],                    # 13
    [8, 9, 13, 18, 19],                 # 14
    [10, 16, 20],                       # 15
    [10, 11, 12, 15, 17, 20, 21, 22],   # 16
    [12, 16, 18, 22],                   # 17
    [12, 13, 14, 17, 19, 22, 23, 24],   # 18
    [14, 18, 24],                       # 19
    [15, 16, 21],                       # 20
    [16, 20, 22],                       # 21
    [16, 17, 18, 21, 23],               # 22
    [18, 22, 24],                       # 23
    [18, 19, 23],                       # 24
]


def _state_key(board, turn):
    """Unique string for board position + side-to-move."""
    return "".join(board) + "|" + str(turn)


class BaghChalLogic(AbstractBoardGame):

    def _get_name(self):
        return "Bagh Chal"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = [EMPTY] * 25
        board[0] = TIGER
        board[4] = TIGER
        board[20] = TIGER
        board[24] = TIGER
        state = {
            "board": board,
            "goats_in_reserve": 20,
            "goats_captured": 0,
            "turn": PLAYER_GOAT,
            "history": [],
        }
        state["history"].append(_state_key(board, PLAYER_GOAT))
        return state

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        if player == PLAYER_GOAT:
            moves = self._goat_moves(state)
        else:
            moves = self._tiger_moves(state)

        # Mode B strict no-repeat filtering in Phase 2
        if state["goats_in_reserve"] == 0:
            moves = self._filter_repetition(state, moves, player)

        return moves

    def _apply_move(self, state, player, move):
        ns = copy.deepcopy(state)
        board = ns["board"]

        if move["type"] == "place":
            board[move["to"]] = GOAT
            ns["goats_in_reserve"] -= 1
        elif move["type"] == "move":
            piece = board[move["from"]]
            board[move["from"]] = EMPTY
            board[move["to"]] = piece
        elif move["type"] == "capture":
            board[move["from"]] = EMPTY
            board[move["over"]] = EMPTY
            board[move["to"]] = TIGER
            ns["goats_captured"] += 1

        ns["turn"] = PLAYER_TIGER if player == PLAYER_GOAT else PLAYER_GOAT
        ns["history"].append(_state_key(board, ns["turn"]))
        return ns

    def _get_game_status(self, state):
        # Tiger wins by capturing 5 goats
        if state["goats_captured"] >= 5:
            return {"is_over": True, "winner": PLAYER_TIGER, "is_draw": False}

        # Threefold repetition draw (Mode B)
        key = _state_key(state["board"], state["turn"])
        if state["history"].count(key) >= 3:
            return {"is_over": True, "winner": None, "is_draw": True}

        # Check if current player has no legal moves
        turn = state["turn"]
        if turn == PLAYER_GOAT:
            raw = self._goat_moves(state)
        else:
            raw = self._tiger_moves(state)

        if not raw:
            if turn == PLAYER_TIGER:
                # Tigers immobilised → Goat wins
                return {"is_over": True, "winner": PLAYER_GOAT, "is_draw": False}
            else:
                # Goats have no moves → Tiger wins (rules §7.1)
                return {"is_over": True, "winner": PLAYER_TIGER, "is_draw": False}

        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Move generation ──────────────────────────────────────────────

    def _goat_moves(self, state):
        board = state["board"]
        moves = []
        if state["goats_in_reserve"] > 0:
            for i in range(25):
                if board[i] == EMPTY:
                    moves.append({"type": "place", "to": i})
        else:
            for i in range(25):
                if board[i] == GOAT:
                    for nb in ADJACENCY[i]:
                        if board[nb] == EMPTY:
                            moves.append({"type": "move", "from": i, "to": nb})
        return moves

    def _tiger_moves(self, state):
        board = state["board"]
        moves = []
        for i in range(25):
            if board[i] != TIGER:
                continue
            # Slides
            for nb in ADJACENCY[i]:
                if board[nb] == EMPTY:
                    moves.append({"type": "move", "from": i, "to": nb})
            # Captures
            for nb in ADJACENCY[i]:
                if board[nb] != GOAT:
                    continue
                r_o, c_o = i // 5, i % 5
                r_i, c_i = nb // 5, nb % 5
                r_d = 2 * r_i - r_o
                c_d = 2 * c_i - c_o
                if not (0 <= r_d <= 4 and 0 <= c_d <= 4):
                    continue
                dest = 5 * r_d + c_d
                if board[dest] != EMPTY:
                    continue
                if dest not in ADJACENCY[nb]:
                    continue
                moves.append({"type": "capture", "from": i, "over": nb, "to": dest})
        return moves

    # ── Evaluation hook ─────────────────────────────────────────────

    def evaluate_position(self, state, player):
        """Evaluate from *player*'s perspective using piece counts and mobility."""
        board = state["board"]
        captured = state["goats_captured"]
        reserve = state["goats_in_reserve"]

        # Terminal-ish: 5 captures = tiger win
        if captured >= 5:
            return 0.0 if player == PLAYER_GOAT else 1.0

        # Compute tiger mobility, captures, and trapped count via adjacency
        tiger_mobility = 0
        available_captures = 0
        trapped_tigers = 0
        for i in range(25):
            if board[i] != TIGER:
                continue
            adj_empty = 0
            for nb in ADJACENCY[i]:
                if board[nb] == EMPTY:
                    adj_empty += 1
                elif board[nb] == GOAT:
                    # Check if capture is possible (empty landing beyond)
                    r_o, c_o = i // 5, i % 5
                    r_i, c_i = nb // 5, nb % 5
                    r_d = 2 * r_i - r_o
                    c_d = 2 * c_i - c_o
                    if 0 <= r_d <= 4 and 0 <= c_d <= 4:
                        dest = 5 * r_d + c_d
                        if board[dest] == EMPTY and dest in ADJACENCY[nb]:
                            available_captures += 1
            tiger_mobility += adj_empty
            if adj_empty == 0:
                trapped_tigers += 1

        # All tigers trapped = goat win
        if trapped_tigers == 4:
            return 1.0 if player == PLAYER_GOAT else 0.0

        # Tiger-perspective score
        score = (captured * 500
                 + tiger_mobility * 15
                 + available_captures * 50
                 - trapped_tigers * 100)

        # Placement phase penalty: goats adjacent to tigers with capture behind
        if reserve > 0:
            vulnerable_goats = 0
            for i in range(25):
                if board[i] != GOAT:
                    continue
                for nb in ADJACENCY[i]:
                    if board[nb] == TIGER:
                        # Is there an empty landing beyond goat from tiger?
                        r_t, c_t = nb // 5, nb % 5
                        r_g, c_g = i // 5, i % 5
                        r_d = 2 * r_g - r_t
                        c_d = 2 * c_g - c_t
                        if 0 <= r_d <= 4 and 0 <= c_d <= 4:
                            dest = 5 * r_d + c_d
                            if board[dest] == EMPTY and dest in ADJACENCY[i]:
                                vulnerable_goats += 1
                                break
            score += vulnerable_goats * 30

        # Sigmoid normalization
        x = max(-20.0, min(20.0, score / 300.0))
        tiger_val = 1.0 / (1.0 + math.exp(-x))

        # Return from requested player's perspective
        if player == PLAYER_TIGER:
            return tiger_val
        return 1.0 - tiger_val

    def _filter_repetition(self, state, moves, player):
        """Remove moves that would create a position already in history."""
        history_set = set(state["history"])
        filtered = []
        for m in moves:
            ns = self._apply_move(state, player, m)
            key = _state_key(ns["board"], ns["turn"])
            if key not in history_set:
                filtered.append(m)
        return filtered if filtered else moves
