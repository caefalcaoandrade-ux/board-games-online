"""Hive — server-side game logic (Base + Mosquito, Ladybug, Pillbug).

Implements the AbstractBoardGame interface for the Hive board game.
All game state is JSON-serializable.  Player IDs are 1 (White) and
2 (Black).  The board is stored as a dict mapping ``"q,r"`` string
keys to lists of ``{"type": str, "owner": int}`` piece dicts (stacks).
Hands are stored under string player keys ``"1"`` and ``"2"``.

Moves are dicts with an ``"action"`` key:
  - ``"place"``:   place a piece from hand onto the board
  - ``"move"``:    move an already-placed piece
  - ``"pillbug"``: use the Pillbug (or Mosquito-as-Pillbug) special ability
  - ``"pass"``:    forced pass when no legal actions exist
"""

import copy
from collections import deque

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants ────────────────────────────────────────────────────────

# Axial hex directions: E, NE, NW, W, SW, SE
DIRECTIONS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]]

INITIAL_HAND = {
    "queen": 1, "spider": 2, "beetle": 2, "grasshopper": 3,
    "ant": 3, "mosquito": 1, "ladybug": 1, "pillbug": 1
}

PIECE_ABBREV = {
    "queen": "Q", "spider": "S", "beetle": "B", "grasshopper": "G",
    "ant": "A", "mosquito": "M", "ladybug": "L", "pillbug": "P"
}


# ── Module-level helper functions ────────────────────────────────────

def _key(q, r):
    """Return the string key for axial coordinates ``(q, r)``."""
    return f"{q},{r}"


def _parse_key(key):
    """Parse a ``"q,r"`` string key into an ``(int, int)`` tuple."""
    parts = key.split(",")
    return int(parts[0]), int(parts[1])


def _neighbors(q, r):
    """Return the six axial neighbors of ``(q, r)`` as lists."""
    return [[q + d[0], r + d[1]] for d in DIRECTIONS]


def _are_adjacent(q1, r1, q2, r2):
    """Return ``True`` if two hex cells are adjacent."""
    dq = q2 - q1
    dr = r2 - r1
    return [dq, dr] in DIRECTIONS


# ── HiveLogic ────────────────────────────────────────────────────────

class HiveLogic(AbstractBoardGame):
    """Complete Hive game logic with all expansion pieces.

    Conforms to the :class:`AbstractBoardGame` interface so the hub
    server can drive any game generically.
    """

    # ==================================================================
    # AbstractBoardGame interface
    # ==================================================================

    def _get_name(self):
        return "Hive"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        return {
            "board": {},                # "q,r" -> [{"type": str, "owner": int}, ...]
            "hands": {
                "1": dict(INITIAL_HAND),
                "2": dict(INITIAL_HAND),
            },
            "current_player": 1,
            "turn_number": 1,           # global turn counter
            "player_turns": {"1": 0, "2": 0},  # per-player completed turns
            "last_moved_from": [],      # [q, r] of piece that moved last turn
            "last_moved_to": [],        # [q, r] destination of that piece
            "pillbug_moved": [],        # [[q, r], ...] pieces moved by pillbug ability
            "game_over": False,
            "winner": None,
        }

    def _get_current_player(self, state):
        return state["current_player"]

    def _get_legal_moves(self, state, player):
        if state["game_over"]:
            return []
        if state["current_player"] != player:
            return []

        moves = []
        p_key = str(player)
        p_turns = state["player_turns"][p_key]
        player_turn_num = p_turns + 1       # the turn this player is about to take

        queen_placed = state["hands"][p_key]["queen"] == 0

        # Check forced queen placement (player's 4th turn, queen still in hand)
        forced_queen = (player_turn_num == 4 and not queen_placed)

        # --- Placements ---
        placements = self._get_placements(state, player, player_turn_num, forced_queen)
        moves.extend(placements)

        # --- Movement / Power moves (only when own queen is placed) ---
        if queen_placed and not forced_queen:
            movement_moves = self._get_all_movement_moves(state, player)
            moves.extend(movement_moves)

        # If nothing is legal the player must pass
        if not moves:
            moves.append({"action": "pass"})

        return moves

    def _apply_move(self, state, player, move):
        new_state = copy.deepcopy(state)

        action = move["action"]
        p_key = str(player)
        opponent = 2 if player == 1 else 1

        if action == "pass":
            # Nothing to update on the board
            new_state["last_moved_from"] = []
            new_state["last_moved_to"] = []
            new_state["pillbug_moved"] = []

        elif action == "place":
            piece_type = move["piece"]
            q, r = move["to"]
            key = _key(q, r)
            if key not in new_state["board"]:
                new_state["board"][key] = []
            new_state["board"][key].append({"type": piece_type, "owner": player})
            new_state["hands"][p_key][piece_type] -= 1
            # Placement is NOT movement — do not set last_moved_to.
            # Per rules §6/§10.8, only "moved" pieces are protected
            # from Pillbug targeting, not freshly placed pieces.
            new_state["last_moved_from"] = []
            new_state["last_moved_to"] = []
            new_state["pillbug_moved"] = []

        elif action == "move":
            fq, fr = move["from"]
            tq, tr = move["to"]
            fkey = _key(fq, fr)
            tkey = _key(tq, tr)
            # Remove top piece from source
            piece = new_state["board"][fkey].pop()
            if not new_state["board"][fkey]:
                del new_state["board"][fkey]
            # Place on destination
            if tkey not in new_state["board"]:
                new_state["board"][tkey] = []
            new_state["board"][tkey].append(piece)
            new_state["last_moved_from"] = [fq, fr]
            new_state["last_moved_to"] = [tq, tr]
            new_state["pillbug_moved"] = []

        elif action == "pillbug":
            tq, tr = move["target"]
            dq, dr = move["to"]
            tkey = _key(tq, tr)
            dkey = _key(dq, dr)
            # Remove top piece from target
            piece = new_state["board"][tkey].pop()
            if not new_state["board"][tkey]:
                del new_state["board"][tkey]
            # Place on destination
            if dkey not in new_state["board"]:
                new_state["board"][dkey] = []
            new_state["board"][dkey].append(piece)
            new_state["last_moved_from"] = [tq, tr]
            new_state["last_moved_to"] = [dq, dr]
            new_state["pillbug_moved"] = [[dq, dr]]

        # Update turn counters
        new_state["player_turns"][p_key] += 1
        new_state["turn_number"] += 1

        # Swap current player
        new_state["current_player"] = opponent

        # Check terminal conditions
        result = self._check_queen_surrounded(new_state)
        if result is not None:
            new_state["game_over"] = True
            new_state["winner"] = result

        return new_state

    def _get_game_status(self, state):
        if state["game_over"]:
            winner = state["winner"]
            if winner == "draw":
                return {"is_over": True, "winner": None, "is_draw": True}
            return {"is_over": True, "winner": winner, "is_draw": False}

        # Also check the board directly (handles states not produced by
        # _apply_move, e.g. manually constructed test states).
        result = self._check_queen_surrounded(state)
        if result is not None:
            if result == "draw":
                return {"is_over": True, "winner": None, "is_draw": True}
            return {"is_over": True, "winner": result, "is_draw": False}

        return {"is_over": False, "winner": None, "is_draw": False}

    # ==================================================================
    # Board query helpers
    # ==================================================================

    def _height(self, board, q, r):
        """Return the number of pieces stacked at ``(q, r)``."""
        key = _key(q, r)
        if key in board:
            return len(board[key])
        return 0

    def _top_piece(self, board, q, r):
        """Return the topmost piece dict at ``(q, r)``, or ``None``."""
        key = _key(q, r)
        if key in board and board[key]:
            return board[key][-1]
        return None

    def _occupied_cells(self, board):
        """Return the set of all occupied cell keys."""
        return set(k for k in board if board[k])

    # ==================================================================
    # Connectivity / One Hive Rule
    # ==================================================================

    def _is_connected_without(self, board, exclude_key):
        """Check if the hive stays connected after removing the top piece at
        *exclude_key*.  If the cell is a stack the cell remains (just shorter)."""
        cells = set()
        for k in board:
            if not board[k]:
                continue
            if k == exclude_key:
                if len(board[k]) > 1:
                    cells.add(k)
                # single piece: cell disappears
            else:
                cells.add(k)

        if len(cells) <= 1:
            return True

        start = next(iter(cells))
        visited = {start}
        queue = deque([start])
        while queue:
            curr = queue.popleft()
            cq, cr = _parse_key(curr)
            for nq, nr in _neighbors(cq, cr):
                nk = _key(nq, nr)
                if nk in cells and nk not in visited:
                    visited.add(nk)
                    queue.append(nk)
        return len(visited) == len(cells)

    def _can_remove_piece(self, board, q, r):
        """Return ``True`` if removing the top piece at ``(q, r)`` keeps the
        hive connected."""
        key = _key(q, r)
        if key not in board or not board[key]:
            return False
        return self._is_connected_without(board, key)

    # ==================================================================
    # Gate / slide helpers
    # ==================================================================

    def _find_direction_index(self, sq, sr, dq, dr):
        """Find the index in DIRECTIONS from ``(sq, sr)`` to ``(dq, dr)``."""
        ddq = dq - sq
        ddr = dr - sr
        for i, d in enumerate(DIRECTIONS):
            if d[0] == ddq and d[1] == ddr:
                return i
        return -1

    def _get_gate_cells(self, sq, sr, dq, dr):
        """Return the two gate cells ``(L, R)`` between ``S`` and ``D``."""
        di = self._find_direction_index(sq, sr, dq, dr)
        if di < 0:
            return None, None
        l_dir = DIRECTIONS[(di - 1) % 6]
        r_dir = DIRECTIONS[(di + 1) % 6]
        return [sq + l_dir[0], sr + l_dir[1]], [sq + r_dir[0], sr + r_dir[1]]

    def _can_slide_ground(self, board, sq, sr, dq, dr, exclude_key=None):
        """Check if a ground-level piece can slide from ``S`` to adjacent ``D``.

        *exclude_key* is the origin key of the moving piece (its contribution
        to height is decremented by 1).
        """
        if not _are_adjacent(sq, sr, dq, dr):
            return False

        left, right = self._get_gate_cells(sq, sr, dq, dr)
        if left is None:
            return False

        def ht(q, r):
            key = _key(q, r)
            if key == exclude_key:
                h = self._height(board, q, r) - 1
                return max(0, h)
            return self._height(board, q, r)

        hl = ht(left[0], left[1])
        hr = ht(right[0], right[1])

        # Gate check: blocked if both gate cells are occupied
        if hl > 0 and hr > 0:
            return False

        # Hive contact: at least one gate cell must be occupied
        if hl == 0 and hr == 0:
            return False

        # Destination must be empty (for a ground crawl)
        dest_h = ht(dq, dr)
        if dest_h > 0:
            return False

        return True

    def _can_step_elevated(self, board, sq, sr, sh, dq, dr, exclude_key=None):
        """Check if a piece at level *sh* at ``(sq, sr)`` can step to
        ``(dq, dr)`` using the elevated (beetle) gate check.

        *exclude_key* height is decremented by 1 (the moving piece is removed
        from its origin for calculation purposes).
        """
        if not _are_adjacent(sq, sr, dq, dr):
            return False

        left, right = self._get_gate_cells(sq, sr, dq, dr)
        if left is None:
            return False

        def ht(q, r):
            key = _key(q, r)
            if key == exclude_key:
                return max(0, self._height(board, q, r) - 1)
            return self._height(board, q, r)

        hl = ht(left[0], left[1])
        hr = ht(right[0], right[1])
        hd = ht(dq, dr)

        threshold = max(sh, hd)
        if hl >= threshold and hr >= threshold and threshold > 0:
            return False

        return True

    # ==================================================================
    # Temporary-board helpers (piece already removed)
    # ==================================================================

    def _temp_remove(self, board, key):
        """Return a *new* board dict with the top piece at *key* removed."""
        temp = {}
        for k, v in board.items():
            if k == key:
                if len(v) > 1:
                    temp[k] = v[:-1]
                # else: cell disappears
            else:
                temp[k] = v
        return temp

    def _can_slide_ground_temp(self, board, sq, sr, dq, dr):
        """Ground-slide check on a temporary board (no exclude_key)."""
        if not _are_adjacent(sq, sr, dq, dr):
            return False

        left, right = self._get_gate_cells(sq, sr, dq, dr)
        if left is None:
            return False

        hl = self._height(board, left[0], left[1])
        hr = self._height(board, right[0], right[1])

        if hl > 0 and hr > 0:
            return False
        if hl == 0 and hr == 0:
            return False

        # Destination must be empty
        if self._height(board, dq, dr) > 0:
            return False

        return True

    def _can_step_elevated_temp(self, board, sq, sr, sh, dq, dr):
        """Elevated gate check on a temporary board (no exclude_key)."""
        if not _are_adjacent(sq, sr, dq, dr):
            return False

        left, right = self._get_gate_cells(sq, sr, dq, dr)
        if left is None:
            return False

        hl = self._height(board, left[0], left[1])
        hr = self._height(board, right[0], right[1])
        hd = self._height(board, dq, dr)

        threshold = max(sh, hd)
        if threshold > 0 and hl >= threshold and hr >= threshold:
            return False

        return True

    # ==================================================================
    # Win / draw detection
    # ==================================================================

    def _check_queen_surrounded(self, state):
        """Check if any queen is fully surrounded.

        Returns ``1`` (White wins), ``2`` (Black wins), ``"draw"``, or
        ``None`` (game continues).
        """
        board = state["board"]
        queen_pos = {1: None, 2: None}

        for key, stack in board.items():
            for piece in stack:
                if piece["type"] == "queen":
                    q, r = _parse_key(key)
                    queen_pos[piece["owner"]] = (q, r)

        surrounded = {1: False, 2: False}
        for owner in (1, 2):
            pos = queen_pos[owner]
            if pos is not None:
                q, r = pos
                surrounded[owner] = all(
                    _key(q + d[0], r + d[1]) in board
                    and board[_key(q + d[0], r + d[1])]
                    for d in DIRECTIONS
                )

        if surrounded[1] and surrounded[2]:
            return "draw"
        elif surrounded[1]:
            return 2          # White queen surrounded -> Black wins
        elif surrounded[2]:
            return 1          # Black queen surrounded -> White wins
        return None

    # ==================================================================
    # Resting / pillbug-stun helpers
    # ==================================================================

    def _is_resting(self, state, q, r):
        """Return ``True`` if the piece at ``(q, r)`` was moved by a Pillbug
        ability last turn (resting: cannot move and cannot be targeted)."""
        for pos in state.get("pillbug_moved", []):
            if pos[0] == q and pos[1] == r:
                return True
        return False

    def _is_pillbug_stunned(self, state, q, r):
        """Return ``True`` if the piece at ``(q, r)`` was moved last turn
        by *any* means and therefore cannot be targeted by a Pillbug ability."""
        lmt = state.get("last_moved_to", [])
        if lmt and lmt[0] == q and lmt[1] == r:
            return True
        for pos in state.get("pillbug_moved", []):
            if pos[0] == q and pos[1] == r:
                return True
        return False

    # ==================================================================
    # Placement generation
    # ==================================================================

    def _get_placements(self, state, player, player_turn_num, forced_queen):
        """Generate all legal placement moves for *player*."""
        board = state["board"]
        p_key = str(player)
        hand = state["hands"][p_key]
        opponent = 2 if player == 1 else 1
        moves = []

        total_pieces_on_board = sum(len(v) for v in board.values())

        # Determine which piece types may be placed
        if forced_queen:
            placeable = ["queen"] if hand["queen"] > 0 else []
        else:
            placeable = [p for p, c in hand.items() if c > 0]
            # Tournament rule: no queen on a player's 1st turn
            if player_turn_num == 1 and "queen" in placeable:
                placeable.remove("queen")

        if not placeable:
            return []

        # Determine valid placement cells
        if total_pieces_on_board == 0:
            # Very first piece of the game -> origin
            valid_cells = [[0, 0]]
        elif total_pieces_on_board == 1:
            # Second piece: adjacent to the first piece (any colour allowed)
            for key in board:
                if board[key]:
                    q, r = _parse_key(key)
                    valid_cells = _neighbors(q, r)
                    break
        else:
            # Normal placement (turn 3+): friendly colour, not enemy colour
            valid_cells = self._get_placement_cells(board, player, opponent)

        for cell in valid_cells:
            q, r = cell
            if self._height(board, q, r) > 0:
                continue  # must be empty
            for piece_type in placeable:
                moves.append({
                    "action": "place",
                    "piece": piece_type,
                    "to": [q, r],
                })

        return moves

    def _get_placement_cells(self, board, player, opponent):
        """Return cells valid for normal placement (turn 3+).

        Adjacent to at least one friendly top-colour cell, not adjacent to any
        enemy top-colour cell.
        """
        occupied = self._occupied_cells(board)
        candidates = set()

        for key in occupied:
            q, r = _parse_key(key)
            for nq, nr in _neighbors(q, r):
                nk = _key(nq, nr)
                if nk not in occupied:
                    candidates.add((nq, nr))

        valid = []
        for (cq, cr) in candidates:
            adjacent_to_friendly = False
            adjacent_to_enemy = False
            for nq, nr in _neighbors(cq, cr):
                top = self._top_piece(board, nq, nr)
                if top:
                    if top["owner"] == player:
                        adjacent_to_friendly = True
                    else:
                        adjacent_to_enemy = True
            if adjacent_to_friendly and not adjacent_to_enemy:
                valid.append([cq, cr])
        return valid

    # ==================================================================
    # Movement generation (dispatcher)
    # ==================================================================

    def _get_all_movement_moves(self, state, player):
        """Generate all movement and power moves for *player*."""
        board = state["board"]
        moves = []

        for key in list(board.keys()):
            if not board[key]:
                continue
            top = board[key][-1]
            q, r = _parse_key(key)
            h = len(board[key]) - 1  # level of top piece (0 = ground)

            if top["owner"] != player:
                continue

            can_remove = self._can_remove_piece(board, q, r)

            # A piece moved by Pillbug ability last turn is "resting" and
            # cannot move at all.
            is_pillbug_resting = self._is_resting(state, q, r)

            # --- Normal movement (requires can_remove and not resting) ---
            if not is_pillbug_resting and can_remove:
                piece_type = top["type"]
                if h > 0 and piece_type == "mosquito":
                    # Mosquito on top of hive acts as beetle
                    piece_moves = self._get_beetle_moves(board, q, r, key)
                elif piece_type == "queen":
                    piece_moves = self._get_queen_moves(board, q, r, key)
                elif piece_type == "beetle":
                    piece_moves = self._get_beetle_moves(board, q, r, key)
                elif piece_type == "grasshopper":
                    piece_moves = self._get_grasshopper_moves(board, q, r, key)
                elif piece_type == "spider":
                    piece_moves = self._get_spider_moves(board, q, r, key)
                elif piece_type == "ant":
                    piece_moves = self._get_ant_moves(board, q, r, key)
                elif piece_type == "mosquito":
                    piece_moves = self._get_mosquito_moves(board, q, r, key, state)
                elif piece_type == "ladybug":
                    piece_moves = self._get_ladybug_moves(board, q, r, key)
                elif piece_type == "pillbug":
                    piece_moves = self._get_pillbug_own_moves(board, q, r, key)
                else:
                    piece_moves = []

                for dest in piece_moves:
                    moves.append({
                        "action": "move",
                        "from": [q, r],
                        "to": dest,
                    })

            # --- Pillbug special ability ---
            # Can be used even if the Pillbug is pinned, but NOT if covered
            # (top piece is never covered) and NOT if the Pillbug is resting
            # and NOT if the Pillbug was moved by any means last turn.
            if top["type"] == "pillbug" and not is_pillbug_resting:
                was_moved_last_turn = self._is_pillbug_stunned(state, q, r)
                if not was_moved_last_turn:
                    pb_moves = self._get_pillbug_ability(board, q, r, player, state)
                    moves.extend(pb_moves)

            # --- Mosquito copying Pillbug ability ---
            if top["type"] == "mosquito" and h == 0 and not is_pillbug_resting:
                was_moved_last_turn = self._is_pillbug_stunned(state, q, r)
                if not was_moved_last_turn:
                    has_adjacent_pillbug = False
                    for nq, nr in _neighbors(q, r):
                        ntop = self._top_piece(board, nq, nr)
                        if ntop and ntop["type"] == "pillbug":
                            has_adjacent_pillbug = True
                            break
                    if has_adjacent_pillbug:
                        pb_moves = self._get_pillbug_ability(board, q, r, player, state)
                        moves.extend(pb_moves)

        return moves

    # ==================================================================
    # Piece-specific movement generators
    # ==================================================================

    def _get_queen_moves(self, board, q, r, origin_key):
        """Queen Bee: 1 ground crawl."""
        results = []
        for nq, nr in _neighbors(q, r):
            if self._can_slide_ground(board, q, r, nq, nr, exclude_key=origin_key):
                results.append([nq, nr])
        return results

    def _get_beetle_moves(self, board, q, r, origin_key):
        """Beetle: 1 step (crawl / climb / fall).

        Ground beetle to empty cell -> standard ground slide.
        Ground beetle to occupied cell -> elevated gate check (climbing).
        Elevated beetle to any cell -> elevated gate check.
        """
        results = []
        h = len(board[origin_key]) - 1  # level of beetle

        for nq, nr in _neighbors(q, r):
            nh = self._height(board, nq, nr)

            if h == 0 and nh == 0:
                # Ground to empty: standard ground slide
                if self._can_slide_ground(board, q, r, nq, nr, exclude_key=origin_key):
                    results.append([nq, nr])
            else:
                # Climbing, falling, or crawling on top of hive
                if self._can_step_elevated(board, q, r, h, nq, nr, exclude_key=origin_key):
                    if nh == 0:
                        # Falling to ground: verify hive contact at destination
                        remaining_h = h  # origin height after removing beetle
                        has_contact = False
                        for nnq, nnr in _neighbors(nq, nr):
                            if nnq == q and nnr == r:
                                if remaining_h > 0:
                                    has_contact = True
                                    break
                            elif self._height(board, nnq, nnr) > 0:
                                has_contact = True
                                break
                        if not has_contact:
                            continue
                    results.append([nq, nr])
        return results

    def _get_grasshopper_moves(self, board, q, r, origin_key):
        """Grasshopper: jump in a straight line over contiguous occupied cells.

        Exempt from the Freedom-to-Move gate check.
        """
        results = []
        for d in DIRECTIONS:
            cq, cr = q + d[0], r + d[1]
            if self._height(board, cq, cr) == 0:
                continue  # must jump over at least one
            while self._height(board, cq, cr) > 0:
                if _key(cq, cr) == origin_key and len(board[origin_key]) == 1:
                    break
                cq += d[0]
                cr += d[1]
            if self._height(board, cq, cr) == 0:
                results.append([cq, cr])
        return results

    def _get_spider_moves(self, board, q, r, origin_key):
        """Spider: exactly 3 ground crawls, no backtracking."""
        results = set()
        temp_board = self._temp_remove(board, origin_key)

        def dfs(cq, cr, steps, visited):
            if steps == 3:
                results.add((cq, cr))
                return
            for nq, nr in _neighbors(cq, cr):
                if (nq, nr) in visited:
                    continue
                nk = _key(nq, nr)
                # Must be empty on the temp board
                if nk in temp_board and temp_board[nk]:
                    continue
                if self._can_slide_ground_temp(temp_board, cq, cr, nq, nr):
                    visited.add((nq, nr))
                    dfs(nq, nr, steps + 1, visited)
                    visited.remove((nq, nr))

        visited = {(q, r)}
        dfs(q, r, 0, visited)
        results.discard((q, r))
        return [[rq, rr] for (rq, rr) in results]

    def _get_ant_moves(self, board, q, r, origin_key):
        """Soldier Ant: BFS flood fill of all reachable ground-level cells."""
        temp_board = self._temp_remove(board, origin_key)

        reachable = set()
        queue = deque()
        queue.append((q, r))
        visited = {(q, r)}

        while queue:
            cq, cr = queue.popleft()
            for nq, nr in _neighbors(cq, cr):
                if (nq, nr) in visited:
                    continue
                nk = _key(nq, nr)
                if nk in temp_board and temp_board[nk]:
                    continue  # occupied
                if self._can_slide_ground_temp(temp_board, cq, cr, nq, nr):
                    visited.add((nq, nr))
                    reachable.add((nq, nr))
                    queue.append((nq, nr))

        reachable.discard((q, r))
        return [[rq, rr] for (rq, rr) in reachable]

    def _get_mosquito_moves(self, board, q, r, origin_key, state):
        """Mosquito at ground level: copies adjacent non-mosquito piece types."""
        types = set()
        for nq, nr in _neighbors(q, r):
            top = self._top_piece(board, nq, nr)
            if top and top["type"] != "mosquito":
                types.add(top["type"])

        if not types:
            return []

        all_dests = set()
        for t in types:
            if t == "queen":
                dests = self._get_queen_moves(board, q, r, origin_key)
            elif t == "beetle":
                dests = self._get_beetle_moves(board, q, r, origin_key)
            elif t == "grasshopper":
                dests = self._get_grasshopper_moves(board, q, r, origin_key)
            elif t == "spider":
                dests = self._get_spider_moves(board, q, r, origin_key)
            elif t == "ant":
                dests = self._get_ant_moves(board, q, r, origin_key)
            elif t == "ladybug":
                dests = self._get_ladybug_moves(board, q, r, origin_key)
            elif t == "pillbug":
                dests = self._get_pillbug_own_moves(board, q, r, origin_key)
            else:
                dests = []
            for d in dests:
                all_dests.add((d[0], d[1]))

        return [[dq, dr] for (dq, dr) in all_dests]

    def _get_ladybug_moves(self, board, q, r, origin_key):
        """Ladybug: 3 steps — climb occupied, crawl/climb occupied, fall to
        empty ground.  Must be off the ground at intermediate steps."""
        results = set()
        temp_board = self._temp_remove(board, origin_key)

        # Step 1: climb onto an adjacent occupied cell
        for n1q, n1r in _neighbors(q, r):
            n1k = _key(n1q, n1r)
            if n1k not in temp_board or not temp_board[n1k]:
                continue  # must be occupied
            # Gate check for climbing from ground (level 0) to top of n1
            if not self._can_step_elevated_temp(temp_board, q, r, 0, n1q, n1r):
                continue

            # Step 2: crawl/climb on top to another occupied cell
            for n2q, n2r in _neighbors(n1q, n1r):
                if n2q == q and n2r == r:
                    continue  # no going back to origin
                n2k = _key(n2q, n2r)
                if n2k not in temp_board or not temp_board[n2k]:
                    continue  # must be occupied (stay on hive)
                h_at_n1 = len(temp_board[n1k])
                if not self._can_step_elevated_temp(
                    temp_board, n1q, n1r, h_at_n1, n2q, n2r
                ):
                    continue

                # Step 3: fall into an adjacent empty cell at ground level
                for n3q, n3r in _neighbors(n2q, n2r):
                    if n3q == q and n3r == r:
                        continue  # cannot return to start
                    n3k = _key(n3q, n3r)
                    if n3k in temp_board and temp_board[n3k]:
                        continue  # must be empty
                    h_at_n2 = len(temp_board[n2k])
                    if not self._can_step_elevated_temp(
                        temp_board, n2q, n2r, h_at_n2, n3q, n3r
                    ):
                        continue
                    results.add((n3q, n3r))

        return [[rq, rr] for (rq, rr) in results]

    def _get_pillbug_own_moves(self, board, q, r, origin_key):
        """Pillbug's own movement: 1 ground crawl (same as Queen)."""
        return self._get_queen_moves(board, q, r, origin_key)

    def _get_pillbug_ability(self, board, q, r, player, state):
        """Generate Pillbug (or Mosquito-as-Pillbug) special ability moves.

        The Pillbug at ``(q, r)`` may lift an adjacent piece onto itself and
        drop it into a different adjacent empty cell.

        Returns a list of ``{"action": "pillbug", ...}`` move dicts.
        """
        moves = []
        pillbug_key = _key(q, r)

        for tq, tr in _neighbors(q, r):
            tk = _key(tq, tr)
            if tk not in board or not board[tk]:
                continue

            # Cannot target a covered piece (only the top piece is targetable,
            # and by definition the top piece is never covered — but a stack
            # height > 1 means there is a piece beneath; the *target* is the
            # top piece which is fine).  However, we must not target a cell
            # where the top piece has something on top — that is only the case
            # for the Pillbug's own cell.  Top piece is always accessible.

            # Cannot target if removing breaks the hive
            if not self._can_remove_piece(board, tq, tr):
                continue

            # Cannot target piece that was moved last turn (any means)
            if self._is_pillbug_stunned(state, tq, tr):
                continue

            # Gate check: can the target climb onto the Pillbug?
            target_h = len(board[tk]) - 1
            if not self._can_step_elevated(board, tq, tr, target_h, q, r,
                                           exclude_key=tk):
                continue

            # Determine valid drop destinations (adjacent to Pillbug, empty)
            for dq, dr in _neighbors(q, r):
                if dq == tq and dr == tr:
                    continue  # can't drop back to where it came from

                dk = _key(dq, dr)
                # Figure out destination height accounting for target removal
                dest_h = self._height(board, dq, dr)
                if dk == tk:
                    # The target's origin cell — after removing the target
                    if len(board[tk]) <= 1:
                        dest_h = 0  # will be empty
                    else:
                        continue  # still occupied
                if dest_h > 0:
                    continue  # must be empty

                # Gate check: can the piece fall from Pillbug to destination?
                # Build a temp board with the target removed from its origin
                temp_board = dict(board)
                temp_stack = list(board[tk])
                temp_stack.pop()
                if temp_stack:
                    temp_board[tk] = temp_stack
                else:
                    temp_board = {k: v for k, v in board.items() if k != tk}

                # The piece sits on top of the Pillbug; effective height is
                # the Pillbug stack height (in the temp board).
                effective_h = self._height(temp_board, q, r)

                if self._can_step_elevated_temp(
                    temp_board, q, r, effective_h, dq, dr
                ):
                    moves.append({
                        "action": "pillbug",
                        "by": [q, r],
                        "target": [tq, tr],
                        "to": [dq, dr],
                    })

        return moves
