"""
Havannah -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Havannah,
a hex-board connection game for two players.

Board representation
--------------------
The board uses hex axial coordinates (q, r).
State stores the board as a dict with STRING keys like "0,1",
values are ints: 0=empty, 1=white, 2=black.

A move is either:
- [q, r] — place a stone at (q, r)
- "swap" — claim the opponent's first stone (only after move 1)

Win conditions:
- Bridge: connect two corners of the hex board
- Fork:   connect three sides of the hex board
- Ring:   form a closed loop enclosing at least one cell
"""

import copy
from collections import deque

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

EMPTY, WHITE, BLACK = 0, 1, 2
DEFAULT_SIZE = 8

# Six hex directions in axial coordinates (dq, dr)
DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


# ── Coordinate helpers ──────────────────────────────────────────────────────

def cell_key(q, r):
    """Axial coord -> string key for state dict."""
    return "{},{}".format(q, r)


def key_to_cell(k):
    """String key -> [q, r] list."""
    parts = k.split(",")
    return [int(parts[0]), int(parts[1])]


# ── Geometry precomputation ─────────────────────────────────────────────────

def _precompute_geometry(size):
    """Precompute board topology for a given board size.

    Returns a dict with:
        cells:        set of (q, r) tuples
        corners:      list of 6 corner (q, r) tuples
        corner_set:   set of corner (q, r) tuples
        corner_index: dict mapping corner (q, r) -> index 0-5
        sides:        list of 6 sets, each containing (q, r) tuples on that side
        side_index:   dict mapping side (q, r) -> side index 0-5
        boundary:     set of all boundary (q, r) tuples (corners + sides)
        neighbors:    dict mapping (q, r) -> list of neighbor (q, r) tuples
    """
    S = size
    cells = set()
    for q in range(-(S - 1), S):
        for r in range(-(S - 1), S):
            if max(abs(q), abs(r), abs(-q - r)) <= S - 1:
                cells.add((q, r))

    # Corners: hex board vertices
    corner_qrs = [
        (S - 1, -(S - 1), 0), (S - 1, 0, -(S - 1)),
        (0, S - 1, -(S - 1)), (-(S - 1), S - 1, 0),
        (-(S - 1), 0, S - 1), (0, -(S - 1), S - 1),
    ]
    corners = [(q, r) for q, r, _ in corner_qrs]
    corner_set = set(corners)
    corner_index = {c: i for i, c in enumerate(corners)}

    # 6 sides (boundary cells excluding corners)
    sides = [set() for _ in range(6)]
    for qr in cells:
        q, r = qr
        s = -q - r
        if qr in corner_set:
            continue
        if max(abs(q), abs(r), abs(s)) < S - 1:
            continue
        if   s == -(S - 1): sides[0].add(qr)
        elif q ==  (S - 1): sides[1].add(qr)
        elif r == -(S - 1): sides[2].add(qr)
        elif s ==  (S - 1): sides[3].add(qr)
        elif q == -(S - 1): sides[4].add(qr)
        elif r ==  (S - 1): sides[5].add(qr)

    side_index = {}
    for i, side in enumerate(sides):
        for c in side:
            side_index[c] = i

    boundary = set()
    for qr in cells:
        q, r = qr
        if max(abs(q), abs(r), abs(-q - r)) == S - 1:
            boundary.add(qr)

    neighbors = {}
    for qr in cells:
        q, r = qr
        neighbors[qr] = [
            (q + dq, r + dr)
            for dq, dr in DIRS
            if (q + dq, r + dr) in cells
        ]

    return {
        "cells": cells,
        "corners": corners,
        "corner_set": corner_set,
        "corner_index": corner_index,
        "sides": sides,
        "side_index": side_index,
        "boundary": boundary,
        "neighbors": neighbors,
    }


# ── Win detection ───────────────────────────────────────────────────────────

def _check_win(board_dict, geo, color, last_q, last_r):
    """Check if *color* has won after placing at (last_q, last_r).

    Rebuilds union-find from the board to check bridge, fork, and ring.

    Returns (won, win_type, winning_chain_keys):
        won:                bool
        win_type:           "Bridge", "Fork", "Ring", or None
        winning_chain_keys: list of "q,r" string keys, or []
    """
    cells = geo["cells"]
    corner_index = geo["corner_index"]
    side_index = geo["side_index"]
    boundary = geo["boundary"]
    neighbors = geo["neighbors"]

    # Gather occupied cells for this color
    occupied = {}          # (q, r) -> string key
    for k, v in board_dict.items():
        if v == color:
            qr = tuple(key_to_cell(k))
            occupied[qr] = k

    if len(occupied) < 2:
        return False, None, []

    # ── Union-find ──────────────────────────────────────────────────────
    par = {}
    rnk = {}
    ch_corners = {}
    ch_sides = {}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return ra
        if rnk[ra] < rnk[rb]:
            ra, rb = rb, ra
        par[rb] = ra
        if rnk[ra] == rnk[rb]:
            rnk[ra] += 1
        ch_corners[ra] |= ch_corners.pop(rb)
        ch_sides[ra] |= ch_sides.pop(rb)
        return ra

    for qr in occupied:
        par[qr] = qr
        rnk[qr] = 0
        ch_corners[qr] = set()
        ch_sides[qr] = set()
        if qr in corner_index:
            ch_corners[qr].add(corner_index[qr])
        if qr in side_index:
            ch_sides[qr].add(side_index[qr])

    for qr in occupied:
        for nb in neighbors[qr]:
            if nb in occupied:
                union(qr, nb)

    # ── Bridge (2+ corners in one component) ────────────────────────────
    last = (last_q, last_r)
    if last in occupied:
        root = find(last)
        if len(ch_corners.get(root, set())) >= 2:
            chain = [occupied[c] for c in occupied if find(c) == root]
            return True, "Bridge", chain
        if len(ch_sides.get(root, set())) >= 3:
            chain = [occupied[c] for c in occupied if find(c) == root]
            return True, "Fork", chain

    # ── Ring (enclosed region via flood-fill) ───────────────────────────
    if len(occupied) >= 6:
        occupied_set = set(occupied.keys())
        background = cells - occupied_set
        visited = set()
        enclosed = set()
        found_ring = False

        for start in background:
            if start in visited:
                continue
            touches_edge = False
            queue = deque([start])
            visited.add(start)
            comp = []
            while queue:
                cur = queue.popleft()
                comp.append(cur)
                if cur in boundary:
                    touches_edge = True
                for nb in neighbors[cur]:
                    if nb in background and nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if not touches_edge:
                enclosed.update(comp)
                found_ring = True

        if found_ring:
            ring = set()
            for c in enclosed:
                for nb in neighbors[c]:
                    if nb in occupied_set:
                        ring.add(nb)
            if ring:
                root = find(next(iter(ring)))
                chain = [occupied[c] for c in occupied if find(c) == root]
                return True, "Ring", chain

    return False, None, []


# ── Game class ──────────────────────────────────────────────────────────────

class HavannahLogic(AbstractBoardGame):
    """Havannah game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":          {str: int, ...},  # "q,r" -> EMPTY/WHITE/BLACK
            "turn":           int,              # WHITE (1) or BLACK (2)
            "move_count":     int,
            "swap_available": bool,
            "size":           int,
            "game_over":      bool,
            "winner":         int or None,
            "win_type":       str or None,      # "Bridge" / "Fork" / "Ring"
            "winning_chain":  [str, ...],       # list of "q,r" keys
            "last_move":      [int, int] or None
        }

    A move is either:
    - ``[q, r]`` — place a stone
    - ``"swap"`` — swap (after move 1 only)
    """

    def __init__(self, size=DEFAULT_SIZE):
        self._size = size
        self._geo = _precompute_geometry(size)

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Havannah"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = {}
        for qr in self._geo["cells"]:
            board[cell_key(qr[0], qr[1])] = EMPTY
        return {
            "board": board,
            "turn": WHITE,
            "move_count": 0,
            "swap_available": False,
            "size": self._size,
            "game_over": False,
            "winner": None,
            "win_type": None,
            "winning_chain": [],
            "last_move": None,
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        if state["game_over"]:
            return []
        moves = []
        for k, v in state["board"].items():
            if v == EMPTY:
                moves.append(key_to_cell(k))
        if state["swap_available"] and state["move_count"] == 1:
            moves.append("swap")
        return moves

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)

        if move == "swap":
            # Swap: players exchange roles.  The stone stays as WHITE,
            # turn stays at BLACK (the server layer maps physical
            # players to colors and swaps that mapping).
            new["swap_available"] = False
            return new

        # Normal placement
        q, r = move
        k = cell_key(q, r)
        new["board"][k] = player
        new["move_count"] = state["move_count"] + 1
        new["last_move"] = [q, r]

        # Win check
        geo = self._geo if state["size"] == self._size \
            else _precompute_geometry(state["size"])
        won, win_type, chain = _check_win(new["board"], geo, player, q, r)

        if won:
            new["game_over"] = True
            new["winner"] = player
            new["win_type"] = win_type
            new["winning_chain"] = chain
            return new

        # Draw check (all cells filled)
        if new["move_count"] == len(geo["cells"]):
            new["game_over"] = True
            new["win_type"] = "Draw"
            return new

        # Swap window: available only after move 1
        new["swap_available"] = (new["move_count"] == 1)

        # Switch turn
        new["turn"] = BLACK if player == WHITE else WHITE
        return new

    def _get_game_status(self, state):
        if state["game_over"]:
            if state["winner"] is not None:
                return {"is_over": True, "winner": state["winner"],
                        "is_draw": False}
            return {"is_over": True, "winner": None, "is_draw": True}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves."""
        if state["game_over"]:
            return False
        if move == "swap":
            return state["swap_available"] and state["move_count"] == 1
        if not isinstance(move, list) or len(move) != 2:
            return False
        q, r = move
        if not (isinstance(q, int) and isinstance(r, int)):
            return False
        k = cell_key(q, r)
        board = state["board"]
        return k in board and board[k] == EMPTY

    # ── Extra helpers for client / display use ───────────────────────────

    def get_geometry(self):
        """Return precomputed geometry for the display module.

        Returns a dict with cells, corners, corner_set, corner_index,
        sides, side_index, boundary, neighbors.
        """
        return self._geo
