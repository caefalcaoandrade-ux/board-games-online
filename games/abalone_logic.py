"""
Abalone -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Abalone (Belgian Daisy),
a hex-board abstract strategy game for two players.

Board representation
--------------------
The board uses hex cube coordinates (q, r, s) where q + r + s == 0.
State stores the board as a dict with STRING keys like "0,1,-1",
values are ints: 0=empty, 1=black, 2=white.

A move is a dict::

    {"marbles": [[q,r,s], ...], "direction": [dq,dr,ds]}

All coordinates are lists (never tuples).
"""

import copy

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

EMPTY, BLACK, WHITE = 0, 1, 2

# Row lengths for the hex board (R1–R9)
ROW_LENS = [5, 6, 7, 8, 9, 8, 7, 6, 5]

# Six unit directions in cube coordinates [dq, dr, ds]  q+r+s == 0
DIRS = [
    [1, -1, 0],   # E
    [1, 0, -1],   # NE
    [0, 1, -1],   # NW
    [-1, 1, 0],   # W
    [-1, 0, 1],   # SW
    [0, -1, 1],   # SE
]


# ── Coordinate helpers (cube coords: q+r+s == 0, board radius 4) ────────────

def rc_to_cube(r, c):
    """0-indexed (row, col) -> cube [q, r, s] as a list."""
    z = r - 4
    x = c - min(4, r)
    y = -x - z
    return [x, y, z]


def cube_to_rc(x, y, z):
    """Cube (x, y, z) -> 0-indexed [row, col] as a list."""
    r = z + 4
    c = x + min(4, r)
    return [r, c]


def on_board(x, y, z):
    """True if cube coord (x, y, z) is within the radius-4 hex board."""
    return (x + y + z == 0) and max(abs(x), abs(y), abs(z)) <= 4


def cube_key(x, y, z):
    """Cube coord -> string key for state dict."""
    return "{},{},{}".format(x, y, z)


def key_to_cube(k):
    """String key -> [x, y, z] list."""
    parts = k.split(",")
    return [int(parts[0]), int(parts[1]), int(parts[2])]


def cube_add(a, d):
    """Add two cube coords (lists)."""
    return [a[0] + d[0], a[1] + d[1], a[2] + d[2]]


def cube_sub(a, b):
    """Subtract two cube coords (lists)."""
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def cube_dist(a, b):
    """Chebyshev distance between two cube coords."""
    d = cube_sub(a, b)
    return max(abs(d[0]), abs(d[1]), abs(d[2]))


# ── Private helper functions ─────────────────────────────────────────────────

def _collinear(positions):
    """True if all positions (list of [q,r,s]) are collinear along a DIRS axis."""
    if len(positions) < 2:
        return True
    p0 = positions[0]
    d0 = cube_sub(positions[1], p0)
    dist0 = max(abs(d0[0]), abs(d0[1]), abs(d0[2]))
    if dist0 == 0:
        return False
    unit = [d0[0] // dist0, d0[1] // dist0, d0[2] // dist0]
    if unit not in DIRS:
        return False
    neg = [-unit[0], -unit[1], -unit[2]]
    for p in positions[2:]:
        d = cube_sub(p, p0)
        dl = max(abs(d[0]), abs(d[1]), abs(d[2]))
        if dl == 0:
            return False
        u = [d[0] // dl, d[1] // dl, d[2] // dl]
        if u != unit and u != neg:
            return False
    return True


def _contiguous(positions):
    """True if positions form a contiguous group (1-3 marbles)."""
    if len(positions) <= 1:
        return True
    if len(positions) == 2:
        return cube_dist(positions[0], positions[1]) == 1
    dists = sorted(cube_dist(positions[i], positions[j])
                   for i in range(3) for j in range(i + 1, 3))
    return dists == [1, 1, 2]


def _group_axis(positions):
    """Return the unit direction [dq,dr,ds] along the group's axis."""
    d = cube_sub(positions[1], positions[0])
    dl = max(abs(d[0]), abs(d[1]), abs(d[2]))
    return [d[0] // dl, d[1] // dl, d[2] // dl]


def _sort_along(positions, direction):
    """Sort positions by projection along direction."""
    def proj(p):
        return p[0] * direction[0] + p[1] * direction[1] + p[2] * direction[2]
    return sorted(positions, key=proj)


def _valid_group(board, turn, positions):
    """True if positions form a valid selection group for the current player."""
    if not 1 <= len(positions) <= 3:
        return False
    for p in positions:
        k = cube_key(p[0], p[1], p[2])
        if board.get(k) != turn:
            return False
    if len(positions) == 1:
        return True
    return _collinear(positions) and _contiguous(positions)


def _can_add(board, turn, selected, pos):
    """True if pos can be added to the current selection to form a valid group."""
    k = cube_key(pos[0], pos[1], pos[2])
    if board.get(k) != turn:
        return False
    ns = selected + [pos]
    if len(ns) > 3:
        return False
    if len(ns) == 1:
        return True
    return _collinear(ns) and _contiguous(ns)


def _try_move_on_board(board, turn, captured, selected, direction, real):
    """Attempt a move. Returns (success, new_board, new_turn, new_captured, game_over, winner).

    If real is False, only checks legality and returns (success, ...) without
    modifying anything. When real is True, returns updated state components.
    board is a dict with string keys.
    """
    if not _valid_group(board, turn, selected):
        return (False, None, None, None, False, None)

    n = len(selected)

    # Single marble
    if n == 1:
        dest = cube_add(selected[0], direction)
        if not on_board(dest[0], dest[1], dest[2]):
            return (False, None, None, None, False, None)
        dk = cube_key(dest[0], dest[1], dest[2])
        if board.get(dk, -1) != EMPTY:
            return (False, None, None, None, False, None)
        if real:
            new_board = dict(board)
            sk = cube_key(selected[0][0], selected[0][1], selected[0][2])
            new_board[dk] = turn
            new_board[sk] = EMPTY
            new_turn = WHITE if turn == BLACK else BLACK
            return (True, new_board, new_turn, dict(captured), False, None)
        return (True, None, None, None, False, None)

    # Multi-marble: inline vs side-step
    axis = _group_axis(selected)
    neg_axis = [-axis[0], -axis[1], -axis[2]]
    if direction == axis or direction == neg_axis:
        return _do_inline(board, turn, captured, selected, direction, real)
    else:
        return _do_sidestep(board, turn, captured, selected, direction, real)


def _do_inline(board, turn, captured, selected, direction, real):
    """Inline push move."""
    ordered = _sort_along(selected, direction)
    front = ordered[-1]
    tail = ordered[0]
    ahead = cube_add(front, direction)

    if not on_board(ahead[0], ahead[1], ahead[2]):
        return (False, None, None, None, False, None)

    ak = cube_key(ahead[0], ahead[1], ahead[2])
    cell_ahead = board[ak]
    opp = WHITE if turn == BLACK else BLACK

    # Empty ahead -> simple advance
    if cell_ahead == EMPTY:
        if real:
            new_board = dict(board)
            new_board[ak] = turn
            tk = cube_key(tail[0], tail[1], tail[2])
            new_board[tk] = EMPTY
            new_turn = WHITE if turn == BLACK else BLACK
            return (True, new_board, new_turn, dict(captured), False, None)
        return (True, None, None, None, False, None)

    # Own marble ahead -> blocked
    if cell_ahead == turn:
        return (False, None, None, None, False, None)

    # Opponent ahead -> push attempt
    enemies = []
    pos = list(ahead)
    while on_board(pos[0], pos[1], pos[2]) and board.get(cube_key(pos[0], pos[1], pos[2])) == opp:
        enemies.append(list(pos))
        pos = cube_add(pos, direction)

    n_fr = len(selected)
    n_en = len(enemies)
    if n_fr <= n_en or n_en > 2:
        return (False, None, None, None, False, None)

    beyond = pos  # position after the last enemy

    if on_board(beyond[0], beyond[1], beyond[2]):
        bk = cube_key(beyond[0], beyond[1], beyond[2])
        if board[bk] != EMPTY:
            return (False, None, None, None, False, None)
        if real:
            new_board = dict(board)
            new_board[bk] = opp
            new_board[ak] = turn
            tk = cube_key(tail[0], tail[1], tail[2])
            new_board[tk] = EMPTY
            new_turn = WHITE if turn == BLACK else BLACK
            return (True, new_board, new_turn, dict(captured), False, None)
        return (True, None, None, None, False, None)
    else:
        # Ejection: enemy pushed off the board
        if real:
            new_board = dict(board)
            new_captured = dict(captured)
            new_captured[str(turn)] = new_captured.get(str(turn), 0) + 1
            if n_en == 2:
                ek = cube_key(enemies[1][0], enemies[1][1], enemies[1][2])
                new_board[ek] = opp
            new_board[ak] = turn
            tk = cube_key(tail[0], tail[1], tail[2])
            new_board[tk] = EMPTY
            game_over = False
            winner = None
            if new_captured[str(turn)] >= 6:
                game_over = True
                winner = turn
            new_turn = WHITE if turn == BLACK else BLACK
            return (True, new_board, new_turn, new_captured, game_over, winner)
        return (True, None, None, None, False, None)


def _do_sidestep(board, turn, captured, selected, direction, real):
    """Side-step move (all marbles move in a direction perpendicular to their axis)."""
    dests = []
    for p in selected:
        d = cube_add(p, direction)
        if not on_board(d[0], d[1], d[2]):
            return (False, None, None, None, False, None)
        dk = cube_key(d[0], d[1], d[2])
        if board.get(dk, -1) != EMPTY:
            return (False, None, None, None, False, None)
        dests.append(d)
    if real:
        new_board = dict(board)
        for p in selected:
            pk = cube_key(p[0], p[1], p[2])
            new_board[pk] = EMPTY
        for d in dests:
            dk = cube_key(d[0], d[1], d[2])
            new_board[dk] = turn
        new_turn = WHITE if turn == BLACK else BLACK
        return (True, new_board, new_turn, dict(captured), False, None)
    return (True, None, None, None, False, None)


def _valid_targets(board, turn, captured, game_over, winner, selected):
    """Compute valid target cells for a selected group.

    Returns a dict mapping string cube keys to 'move' or 'push'.
    """
    if not _valid_group(board, turn, selected):
        return {}
    targets = {}
    for d in DIRS:
        ok, _, _, _, _, _ = _try_move_on_board(
            board, turn, captured, list(selected), d, False)
        if not ok:
            continue
        ordered = _sort_along(selected, d)
        ahead = cube_add(ordered[-1], d)
        is_push = (on_board(ahead[0], ahead[1], ahead[2])
                   and board.get(cube_key(ahead[0], ahead[1], ahead[2]))
                   not in (EMPTY, turn, None))
        sel_set = set(cube_key(p[0], p[1], p[2]) for p in selected)
        for p in selected:
            c = cube_add(p, d)
            ck = cube_key(c[0], c[1], c[2])
            if on_board(c[0], c[1], c[2]) and ck not in sel_set:
                targets[ck] = "push" if is_push else "move"
    return targets


# ── Game class ───────────────────────────────────────────────────────────────

class AbaloneLogic(AbstractBoardGame):
    """Abalone game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "board":     {str: int, ...},  # cube-key -> EMPTY/BLACK/WHITE
            "turn":      int,              # BLACK (1) or WHITE (2)
            "captured":  {"1": int, "2": int},  # captures by each player
            "game_over": bool,
            "winner":    int or None
        }

    A move is a dict::

        {"marbles": [[q,r,s], ...], "direction": [dq,dr,ds]}
    """

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Abalone"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        board = {}
        for r in range(9):
            for c in range(ROW_LENS[r]):
                cube = rc_to_cube(r, c)
                board[cube_key(cube[0], cube[1], cube[2])] = EMPTY

        # Belgian Daisy setup - Black marbles
        for r, c in [(0, 3), (0, 4), (1, 3), (1, 4), (1, 5), (2, 4), (2, 5),
                      (6, 1), (6, 2), (7, 0), (7, 1), (7, 2), (8, 0), (8, 1)]:
            cube = rc_to_cube(r, c)
            board[cube_key(cube[0], cube[1], cube[2])] = BLACK

        # Belgian Daisy setup - White marbles
        for r, c in [(0, 0), (0, 1), (1, 0), (1, 1), (1, 2), (2, 1), (2, 2),
                      (6, 4), (6, 5), (7, 3), (7, 4), (7, 5), (8, 3), (8, 4)]:
            cube = rc_to_cube(r, c)
            board[cube_key(cube[0], cube[1], cube[2])] = WHITE

        return {
            "board": board,
            "turn": BLACK,
            "captured": {"1": 0, "2": 0},
            "game_over": False,
            "winner": None,
        }

    def _get_current_player(self, state):
        return state["turn"]

    def _get_legal_moves(self, state, player):
        board = state["board"]
        turn = state["turn"]
        captured = state["captured"]
        game_over = state["game_over"]
        winner = state["winner"]

        if game_over:
            return []

        # Find all positions belonging to the current player
        own_positions = []
        for k, v in board.items():
            if v == player:
                own_positions.append(key_to_cube(k))

        moves = []
        seen = set()

        # Generate all valid groups of 1, 2, and 3 marbles
        for i, p1 in enumerate(own_positions):
            # Single marble
            for d in DIRS:
                ok, _, _, _, _, _ = _try_move_on_board(
                    board, turn, captured, [p1], d, False)
                if ok:
                    move_key = (tuple(p1[0:3]), tuple(d))
                    if move_key not in seen:
                        seen.add(move_key)
                        moves.append({
                            "marbles": [list(p1)],
                            "direction": list(d),
                        })

            # Pairs
            for j in range(i + 1, len(own_positions)):
                p2 = own_positions[j]
                pair = [p1, p2]
                if not (_collinear(pair) and _contiguous(pair)):
                    continue
                for d in DIRS:
                    ok, _, _, _, _, _ = _try_move_on_board(
                        board, turn, captured, pair, d, False)
                    if ok:
                        sorted_pair = sorted([list(p1), list(p2)])
                        move_key = (tuple(sorted_pair[0]), tuple(sorted_pair[1]), tuple(d))
                        if move_key not in seen:
                            seen.add(move_key)
                            moves.append({
                                "marbles": sorted_pair,
                                "direction": list(d),
                            })

                # Triples
                for m in range(j + 1, len(own_positions)):
                    p3 = own_positions[m]
                    triple = [p1, p2, p3]
                    if not (_collinear(triple) and _contiguous(triple)):
                        continue
                    for d in DIRS:
                        ok, _, _, _, _, _ = _try_move_on_board(
                            board, turn, captured, triple, d, False)
                        if ok:
                            sorted_triple = sorted([list(p1), list(p2), list(p3)])
                            move_key = (tuple(sorted_triple[0]), tuple(sorted_triple[1]),
                                        tuple(sorted_triple[2]), tuple(d))
                            if move_key not in seen:
                                seen.add(move_key)
                                moves.append({
                                    "marbles": sorted_triple,
                                    "direction": list(d),
                                })

        return moves

    def _apply_move(self, state, player, move):
        new_state = copy.deepcopy(state)
        marbles = move["marbles"]
        direction = move["direction"]

        board = new_state["board"]
        turn = new_state["turn"]
        captured = new_state["captured"]

        ok, new_board, new_turn, new_cap, go, w = _try_move_on_board(
            board, turn, captured, marbles, direction, True)

        if not ok:
            return new_state  # should not happen if move was validated

        new_state["board"] = new_board
        new_state["turn"] = new_turn
        new_state["captured"] = new_cap
        new_state["game_over"] = go
        new_state["winner"] = w
        return new_state

    def _get_game_status(self, state):
        if state["game_over"]:
            return {
                "is_over": True,
                "winner": state["winner"],
                "is_draw": False,
            }
        return {
            "is_over": False,
            "winner": None,
            "is_draw": False,
        }

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves."""
        if not isinstance(move, dict):
            return False
        if "marbles" not in move or "direction" not in move:
            return False
        marbles = move["marbles"]
        direction = move["direction"]
        if not isinstance(marbles, list) or not isinstance(direction, list):
            return False
        if len(direction) != 3:
            return False
        if not 1 <= len(marbles) <= 3:
            return False
        # Direction must be one of the six valid directions
        if direction not in DIRS:
            return False
        # Each marble must be a list of 3 ints
        for m in marbles:
            if not isinstance(m, list) or len(m) != 3:
                return False
            if not all(isinstance(v, int) for v in m):
                return False

        board = state["board"]
        turn = state["turn"]
        captured = state["captured"]

        ok, _, _, _, _, _ = _try_move_on_board(
            board, turn, captured, marbles, direction, False)
        return ok

    # ── Extra helpers for client / display use ───────────────────────────

    @staticmethod
    def can_add_to_selection(board, turn, selected, pos):
        """Check if pos can be added to form a valid group.

        Parameters: board is a dict with string keys, turn is int,
        selected is a list of [q,r,s] lists, pos is a [q,r,s] list.
        """
        return _can_add(board, turn, selected, pos)

    @staticmethod
    def valid_targets_for_selection(board, turn, captured, game_over, winner, selected):
        """Compute valid targets for a selected group.

        Returns a dict mapping string cube keys to 'move' or 'push'.
        """
        return _valid_targets(board, turn, captured, game_over, winner, selected)

    @staticmethod
    def dir_from_click(selected, clicked):
        """Determine the direction from a selected group to a clicked cell.

        selected: list of [q,r,s] lists
        clicked: [q,r,s] list
        Returns a direction [dq,dr,ds] list or None.
        """
        for d in DIRS:
            for p in selected:
                if cube_add(p, d) == clicked:
                    return d
        return None
