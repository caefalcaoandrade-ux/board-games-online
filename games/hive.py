#!/usr/bin/env python3
"""
Hive — Complete Implementation (Base + Mosquito, Ladybug, Pillbug)
Human vs Human local play using Pygame.
"""

# ============================================================
# SECTION 1 — GAME LOGIC CLASS
# No Pygame imports. Fully self-contained.
# ============================================================

import copy
import json
from collections import deque

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


class HiveGame:
    """Complete Hive game logic with all expansion pieces."""

    # ----------------------------------------------------------
    # Public interface methods
    # ----------------------------------------------------------

    def get_name(self):
        return "Hive"

    def get_num_players(self):
        return 2

    def get_initial_state(self):
        return {
            "board": {},          # "q,r" -> [{"type": str, "owner": str}, ...]
            "hands": {
                "white": dict(INITIAL_HAND),
                "black": dict(INITIAL_HAND)
            },
            "current_player": "white",
            "turn_number": 1,     # global turn counter
            "white_turns": 0,     # how many turns white has completed
            "black_turns": 0,
            "last_moved_from": [],  # [q, r] of piece that moved last turn (for pillbug stun)
            "last_moved_to": [],    # [q, r] where it went
            "pillbug_moved": [],    # [[q,r], ...] pieces moved by pillbug ability last turn
            "game_over": False,
            "winner": None
        }

    def get_current_player(self, state):
        return state["current_player"]

    def check_winner(self, state):
        """Returns 'white', 'black', 'draw', or None."""
        if state["game_over"]:
            return state["winner"]
        return self._check_queen_surrounded(state)

    def get_legal_moves(self, state, player):
        """Return all legal moves for the given player."""
        if state["game_over"]:
            return []
        if state["current_player"] != player:
            return []

        moves = []
        p_turns = state["white_turns"] if player == "white" else state["black_turns"]
        player_turn_num = p_turns + 1  # the turn they are about to take

        queen_placed = state["hands"][player]["queen"] == 0

        # Check forced queen placement (player's 4th turn, queen unplaced)
        forced_queen = (player_turn_num == 4 and not queen_placed)

        # Generate placements
        placements = self._get_placements(state, player, player_turn_num, forced_queen)
        moves.extend(placements)

        # Generate movement moves (only if queen is placed)
        if queen_placed and not forced_queen:
            movement_moves = self._get_all_movement_moves(state, player)
            moves.extend(movement_moves)

        # If no legal moves, must pass
        if not moves:
            moves.append({"action": "pass"})

        return moves

    def apply_move(self, state, player, move):
        """Apply a move and return a new state. Does not modify original."""
        new_state = copy.deepcopy(state)

        action = move["action"]

        if action == "pass":
            pass  # nothing to do to the board
        elif action == "place":
            piece_type = move["piece"]
            q, r = move["to"]
            key = self._key(q, r)
            if key not in new_state["board"]:
                new_state["board"][key] = []
            new_state["board"][key].append({"type": piece_type, "owner": player})
            new_state["hands"][player][piece_type] -= 1
            new_state["last_moved_from"] = []
            new_state["last_moved_to"] = [q, r]
            new_state["pillbug_moved"] = []
        elif action == "move":
            fq, fr = move["from"]
            tq, tr = move["to"]
            fkey = self._key(fq, fr)
            tkey = self._key(tq, tr)
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
            # Pillbug/Mosquito-as-Pillbug special ability
            tq, tr = move["target"]
            dq, dr = move["to"]
            tkey = self._key(tq, tr)
            dkey = self._key(dq, dr)
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
        if player == "white":
            new_state["white_turns"] += 1
        else:
            new_state["black_turns"] += 1

        new_state["turn_number"] += 1

        # Swap player
        new_state["current_player"] = "black" if player == "white" else "white"

        # Check game over
        result = self._check_queen_surrounded(new_state)
        if result is not None:
            new_state["game_over"] = True
            new_state["winner"] = result

        return new_state

    # ----------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------

    def _key(self, q, r):
        return f"{q},{r}"

    def _parse_key(self, key):
        parts = key.split(",")
        return int(parts[0]), int(parts[1])

    def _neighbors(self, q, r):
        return [[q + d[0], r + d[1]] for d in DIRECTIONS]

    def _height(self, board, q, r):
        key = self._key(q, r)
        if key in board:
            return len(board[key])
        return 0

    def _top_piece(self, board, q, r):
        key = self._key(q, r)
        if key in board and board[key]:
            return board[key][-1]
        return None

    def _occupied_cells(self, board):
        """Return set of all occupied cell keys."""
        return set(k for k in board if board[k])

    def _is_connected_without(self, board, exclude_key):
        """Check if hive remains connected after removing top piece at exclude_key.
        If the cell has a stack, removing top doesn't remove the cell."""
        # Build adjacency from occupied cells
        cells = set()
        for k in board:
            if not board[k]:
                continue
            if k == exclude_key:
                if len(board[k]) > 1:
                    cells.add(k)  # stack remains
                # else: cell is removed
            else:
                cells.add(k)

        if len(cells) <= 1:
            return True

        start = next(iter(cells))
        visited = {start}
        queue = deque([start])
        while queue:
            curr = queue.popleft()
            cq, cr = self._parse_key(curr)
            for nq, nr in self._neighbors(cq, cr):
                nk = self._key(nq, nr)
                if nk in cells and nk not in visited:
                    visited.add(nk)
                    queue.append(nk)
        return len(visited) == len(cells)

    def _can_remove_piece(self, board, q, r):
        """Check if removing the top piece at (q,r) keeps hive connected."""
        key = self._key(q, r)
        if key not in board or not board[key]:
            return False
        return self._is_connected_without(board, key)

    def _find_direction_index(self, sq, sr, dq, dr):
        """Find direction index from (sq,sr) to adjacent (dq,dr)."""
        dqq = dq - sq
        drr = dr - sr
        for i, d in enumerate(DIRECTIONS):
            if d[0] == dqq and d[1] == drr:
                return i
        return -1

    def _get_gate_cells(self, sq, sr, dq, dr):
        """Return the two gate cells (L, R) between S and D."""
        di = self._find_direction_index(sq, sr, dq, dr)
        if di < 0:
            return None, None
        l_dir = DIRECTIONS[(di - 1) % 6]
        r_dir = DIRECTIONS[(di + 1) % 6]
        return [sq + l_dir[0], sr + l_dir[1]], [sq + r_dir[0], sr + r_dir[1]]

    def _can_slide_ground(self, board, sq, sr, dq, dr, exclude_key=None):
        """Check if a ground-level piece can slide from S to adjacent D.
        exclude_key: the key of the moving piece's origin (removed from board for checking)."""
        if not self._are_adjacent(sq, sr, dq, dr):
            return False

        l, r = self._get_gate_cells(sq, sr, dq, dr)
        if l is None:
            return False

        def ht(q, r):
            key = self._key(q, r)
            if key == exclude_key:
                h = self._height(board, q, r) - 1
                return max(0, h)
            return self._height(board, q, r)

        hl = ht(l[0], l[1])
        hr = ht(r[0], r[1])

        # Gate check: blocked if both gate cells occupied
        if hl > 0 and hr > 0:
            return False

        # Hive contact: at least one gate cell must be occupied
        if hl == 0 and hr == 0:
            return False

        # Destination must be empty (for ground crawl)
        dest_h = ht(dq, dr)
        if dest_h > 0:
            return False

        return True

    def _can_step_elevated(self, board, sq, sr, sh, dq, dr, exclude_key=None):
        """Check if a piece at height sh at (sq,sr) can step to (dq,dr).
        Used for beetle/ladybug elevated movement.
        Returns True if the step is allowed (gate check passes)."""
        if not self._are_adjacent(sq, sr, dq, dr):
            return False

        l, r = self._get_gate_cells(sq, sr, dq, dr)
        if l is None:
            return False

        def ht(q, r):
            key = self._key(q, r)
            if key == exclude_key:
                return max(0, self._height(board, q, r) - 1)
            return self._height(board, q, r)

        hl = ht(l[0], l[1])
        hr = ht(r[0], r[1])
        hd = ht(dq, dr)

        # The mover is at level sh (0-indexed from ground)
        # Gate check: blocked if both gates are >= max(sh, hd)
        threshold = max(sh, hd)
        if hl >= threshold and hr >= threshold and threshold > 0:
            return False

        return True

    def _are_adjacent(self, q1, r1, q2, r2):
        dq = q2 - q1
        dr = r2 - r1
        return [dq, dr] in DIRECTIONS

    def _check_queen_surrounded(self, state):
        """Check if any queen is fully surrounded. Returns winner, 'draw', or None."""
        board = state["board"]
        white_queen_pos = None
        black_queen_pos = None

        for key, stack in board.items():
            for piece in stack:
                if piece["type"] == "queen":
                    q, r = self._parse_key(key)
                    if piece["owner"] == "white":
                        white_queen_pos = (q, r)
                    else:
                        black_queen_pos = (q, r)

        white_surrounded = False
        black_surrounded = False

        if white_queen_pos:
            q, r = white_queen_pos
            white_surrounded = all(
                self._key(q + d[0], r + d[1]) in board and board[self._key(q + d[0], r + d[1])]
                for d in DIRECTIONS
            )
        if black_queen_pos:
            q, r = black_queen_pos
            black_surrounded = all(
                self._key(q + d[0], r + d[1]) in board and board[self._key(q + d[0], r + d[1])]
                for d in DIRECTIONS
            )

        if white_surrounded and black_surrounded:
            return "draw"
        elif white_surrounded:
            return "black"
        elif black_surrounded:
            return "white"
        return None

    # ----------------------------------------------------------
    # Placement generation
    # ----------------------------------------------------------

    def _get_placements(self, state, player, player_turn_num, forced_queen):
        """Generate all legal placement moves."""
        board = state["board"]
        hand = state["hands"][player]
        opponent = "black" if player == "white" else "white"
        moves = []

        total_pieces_on_board = sum(len(v) for v in board.values())

        # Determine which pieces can be placed
        if forced_queen:
            placeable = ["queen"] if hand["queen"] > 0 else []
        else:
            placeable = [p for p, c in hand.items() if c > 0]
            # Tournament rule: cannot place queen on player's 1st turn
            if player_turn_num == 1 and "queen" in placeable:
                placeable.remove("queen")

        if not placeable:
            return []

        # Determine valid placement cells
        if total_pieces_on_board == 0:
            # First piece of the game: place at origin
            valid_cells = [[0, 0]]
        elif total_pieces_on_board == 1:
            # Second piece: must be adjacent to first piece
            for key in board:
                if board[key]:
                    q, r = self._parse_key(key)
                    valid_cells = self._neighbors(q, r)
                    break
        else:
            # Normal placement: adjacent to friendly, not adjacent to enemy
            valid_cells = self._get_placement_cells(board, player, opponent)

        for cell in valid_cells:
            q, r = cell
            # Must be empty
            if self._height(board, q, r) > 0:
                continue
            for piece_type in placeable:
                moves.append({
                    "action": "place",
                    "piece": piece_type,
                    "to": [q, r]
                })

        return moves

    def _get_placement_cells(self, board, player, opponent):
        """Get cells valid for normal placement (turn 3+)."""
        candidates = set()
        occupied = self._occupied_cells(board)

        for key in occupied:
            q, r = self._parse_key(key)
            for nq, nr in self._neighbors(q, r):
                nk = self._key(nq, nr)
                if nk not in occupied:
                    candidates.add((nq, nr))

        valid = []
        for (cq, cr) in candidates:
            adjacent_to_friendly = False
            adjacent_to_enemy = False
            for nq, nr in self._neighbors(cq, cr):
                top = self._top_piece(board, nq, nr)
                if top:
                    if top["owner"] == player:
                        adjacent_to_friendly = True
                    else:
                        adjacent_to_enemy = True
            if adjacent_to_friendly and not adjacent_to_enemy:
                valid.append([cq, cr])
        return valid

    # ----------------------------------------------------------
    # Movement generation
    # ----------------------------------------------------------

    def _is_resting(self, state, q, r):
        """Check if the piece at (q,r) was moved last turn (resting for pillbug)."""
        lmt = state.get("last_moved_to", [])
        if lmt and lmt[0] == q and lmt[1] == r:
            return True
        for pos in state.get("pillbug_moved", []):
            if pos[0] == q and pos[1] == r:
                return True
        return False

    def _is_pillbug_stunned(self, state, q, r):
        """Check if piece at (q,r) cannot be targeted by pillbug (was moved last turn by any means)."""
        lmt = state.get("last_moved_to", [])
        if lmt and lmt[0] == q and lmt[1] == r:
            return True
        for pos in state.get("pillbug_moved", []):
            if pos[0] == q and pos[1] == r:
                return True
        return False

    def _get_all_movement_moves(self, state, player):
        """Generate all movement and power moves for the player."""
        board = state["board"]
        moves = []

        for key in list(board.keys()):
            if not board[key]:
                continue
            top = board[key][-1]
            q, r = self._parse_key(key)
            h = len(board[key]) - 1  # level of top piece

            if top["owner"] == player:
                # Check if piece can move (not covered, not pinned for movement)
                # Top piece is never covered by definition
                # Check one hive rule
                can_remove = self._can_remove_piece(board, q, r)

                # Check if piece is resting (pillbug stun)
                # Resting pieces can't move at all? No - resting in section 4 definition:
                # "Resting pieces cannot move and cannot be moved by Pillbug/Mosquito-as-Pillbug"
                # But only pieces moved BY pillbug are resting. Pieces that moved normally are not.
                # Actually re-reading: the last_moved_to tracks any piece that moved. For pillbug
                # targeting restriction, any piece moved last turn can't be targeted.
                # For the "resting" status that prevents a piece from moving: only pieces moved
                # by pillbug special ability.
                is_pillbug_resting = any(
                    pos[0] == q and pos[1] == r
                    for pos in state.get("pillbug_moved", [])
                )

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
                            "to": dest
                        })

                # Pillbug special ability (can be used even if pinned, but not if covered or resting)
                if top["type"] == "pillbug" and not is_pillbug_resting:
                    # Check not covered (top piece is never covered)
                    # Pillbug itself was moved last turn? Check stun
                    was_moved_last_turn = self._is_pillbug_stunned(state, q, r)
                    if not was_moved_last_turn:
                        pb_moves = self._get_pillbug_ability(board, q, r, player, state)
                        moves.extend(pb_moves)

                # Mosquito copying pillbug ability
                if top["type"] == "mosquito" and h == 0 and not is_pillbug_resting:
                    was_moved_last_turn = self._is_pillbug_stunned(state, q, r)
                    if not was_moved_last_turn:
                        # Check if adjacent to a pillbug (topmost, not mosquito)
                        has_adjacent_pillbug = False
                        for nq, nr in self._neighbors(q, r):
                            ntop = self._top_piece(board, nq, nr)
                            if ntop and ntop["type"] == "pillbug":
                                has_adjacent_pillbug = True
                                break
                        if has_adjacent_pillbug:
                            pb_moves = self._get_pillbug_ability(board, q, r, player, state)
                            moves.extend(pb_moves)

        return moves

    # ----------------------------------------------------------
    # Piece-specific movement
    # ----------------------------------------------------------

    def _get_queen_moves(self, board, q, r, origin_key):
        """Queen: 1 ground crawl."""
        results = []
        for nq, nr in self._neighbors(q, r):
            if self._can_slide_ground(board, q, r, nq, nr, exclude_key=origin_key):
                results.append([nq, nr])
        return results

    def _get_beetle_moves(self, board, q, r, origin_key):
        """Beetle: 1 step — crawl, climb, or fall.
        Ground beetle to empty cell: standard ground slide (same rules as Queen).
        Ground beetle to occupied cell: elevated gate check (climbing).
        Elevated beetle to any cell: elevated gate check."""
        results = []
        h = len(board[origin_key]) - 1  # level of beetle (0 = ground)

        for nq, nr in self._neighbors(q, r):
            nk = self._key(nq, nr)
            # Effective dest height (exclude self if dest == origin, shouldn't happen)
            nh = self._height(board, nq, nr)

            if h == 0 and nh == 0:
                # Ground beetle to empty cell: use ground slide rules (gate + hive contact)
                if self._can_slide_ground(board, q, r, nq, nr, exclude_key=origin_key):
                    results.append([nq, nr])
            else:
                # Climbing, falling, or crawling on top of hive: elevated gate check
                if self._can_step_elevated(board, q, r, h, nq, nr, exclude_key=origin_key):
                    # For falling to ground from height, check hive contact at destination
                    if nh == 0:
                        # Destination is empty; beetle falls to ground.
                        # Must be adjacent to at least one other occupied cell.
                        remaining_h = h  # height at origin after removing beetle
                        has_contact = False
                        for nnq, nnr in self._neighbors(nq, nr):
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
        """Grasshopper: jump in straight line over occupied cells."""
        results = []
        for d in DIRECTIONS:
            # Move in direction d, must pass over at least one occupied cell
            cq, cr = q + d[0], r + d[1]
            if self._height(board, cq, cr) == 0:
                continue  # must jump over at least one
            # Keep going until we find an empty cell
            while self._height(board, cq, cr) > 0:
                # But skip self's cell (origin)
                if self._key(cq, cr) == origin_key and len(board[origin_key]) == 1:
                    break
                cq += d[0]
                cr += d[1]
            # Check it's empty
            if self._height(board, cq, cr) == 0:
                results.append([cq, cr])
        return results

    def _get_spider_moves(self, board, q, r, origin_key):
        """Spider: exactly 3 ground crawls, no backtracking."""
        results = set()
        # DFS with path tracking
        # Remove spider from board temporarily
        temp_board = self._temp_remove(board, origin_key)

        def dfs(cq, cr, steps, visited):
            if steps == 3:
                results.add((cq, cr))
                return
            for nq, nr in self._neighbors(cq, cr):
                if (nq, nr) in visited:
                    continue
                nk = self._key(nq, nr)
                # Must be empty in temp board
                if nk in temp_board and temp_board[nk]:
                    continue
                # Check slide constraint (in temp_board, no exclude needed)
                if self._can_slide_ground_temp(temp_board, cq, cr, nq, nr):
                    visited.add((nq, nr))
                    dfs(nq, nr, steps + 1, visited)
                    visited.remove((nq, nr))

        visited = {(q, r)}
        dfs(q, r, 0, visited)
        # Remove starting position from results
        results.discard((q, r))
        return [[rq, rr] for (rq, rr) in results]

    def _get_ant_moves(self, board, q, r, origin_key):
        """Soldier Ant: BFS of all reachable ground-level perimeter cells."""
        temp_board = self._temp_remove(board, origin_key)

        reachable = set()
        queue = deque()
        queue.append((q, r))
        visited = {(q, r)}

        while queue:
            cq, cr = queue.popleft()
            for nq, nr in self._neighbors(cq, cr):
                if (nq, nr) in visited:
                    continue
                nk = self._key(nq, nr)
                if nk in temp_board and temp_board[nk]:
                    continue  # occupied
                if self._can_slide_ground_temp(temp_board, cq, cr, nq, nr):
                    visited.add((nq, nr))
                    reachable.add((nq, nr))
                    queue.append((nq, nr))

        reachable.discard((q, r))
        return [[rq, rr] for (rq, rr) in reachable]

    def _get_mosquito_moves(self, board, q, r, origin_key, state):
        """Mosquito at ground level: copies adjacent piece types."""
        # Collect unique types of adjacent topmost pieces (non-mosquito)
        types = set()
        for nq, nr in self._neighbors(q, r):
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
        """Ladybug: climb onto hive, crawl on top, fall to ground."""
        results = set()
        temp_board = self._temp_remove(board, origin_key)

        # Step 1: climb onto an adjacent occupied cell
        for n1q, n1r in self._neighbors(q, r):
            n1k = self._key(n1q, n1r)
            if n1k not in temp_board or not temp_board[n1k]:
                continue  # must be occupied
            # Gate check for climbing from ground to top of n1
            h1 = len(temp_board[n1k])  # height of dest stack
            if not self._can_step_elevated_temp(temp_board, q, r, 0, n1q, n1r):
                continue

            # Step 2: crawl/climb on top of hive to another occupied cell
            for n2q, n2r in self._neighbors(n1q, n1r):
                if n2q == q and n2r == r:
                    continue  # can't go back to origin
                n2k = self._key(n2q, n2r)
                if n2k not in temp_board or not temp_board[n2k]:
                    continue  # must be occupied (stay on top)
                h_at_n1 = len(temp_board[n1k])
                if not self._can_step_elevated_temp(temp_board, n1q, n1r, h_at_n1, n2q, n2r):
                    continue

                # Step 3: fall into an adjacent empty cell at ground level
                for n3q, n3r in self._neighbors(n2q, n2r):
                    if n3q == q and n3r == r:
                        continue  # can't return to start
                    n3k = self._key(n3q, n3r)
                    if n3k in temp_board and temp_board[n3k]:
                        continue  # must be empty
                    h_at_n2 = len(temp_board[n2k])
                    if not self._can_step_elevated_temp(temp_board, n2q, n2r, h_at_n2, n3q, n3r):
                        continue
                    results.add((n3q, n3r))

        return [[rq, rr] for (rq, rr) in results]

    def _get_pillbug_own_moves(self, board, q, r, origin_key):
        """Pillbug's own movement: 1 ground crawl (same as Queen)."""
        return self._get_queen_moves(board, q, r, origin_key)

    def _get_pillbug_ability(self, board, q, r, player, state):
        """Pillbug (or Mosquito-as-Pillbug) special ability at (q,r).
        Returns list of moves with action='pillbug'."""
        moves = []
        pillbug_key = self._key(q, r)

        # Check each adjacent piece
        for tq, tr in self._neighbors(q, r):
            tk = self._key(tq, tr)
            if tk not in board or not board[tk]:
                continue
            top = board[tk][-1]

            # Cannot target covered piece (len > 1 means there's stuff on top? No, len > 1 means stack)
            # Covered means something on top. Top piece is never covered. So only top piece can be targeted.
            # But the restriction is: target piece that is covered. Top piece is not covered. OK.

            # Cannot target if it would break hive
            if not self._can_remove_piece(board, tq, tr):
                continue

            # Cannot target piece that was moved last turn (pillbug stun)
            if self._is_pillbug_stunned(state, tq, tr):
                continue

            # Gate check: can the target climb onto the pillbug?
            target_h = len(board[tk]) - 1
            pillbug_h = len(board[pillbug_key])  # height including pillbug
            if not self._can_step_elevated(board, tq, tr, target_h, q, r, exclude_key=tk):
                continue

            # Now check which empty adjacent cells the piece can fall into
            for dq, dr in self._neighbors(q, r):
                if dq == tq and dr == tr:
                    continue  # can't go back to where it came from
                dk = self._key(dq, dr)
                # Destination must be empty
                dest_h = self._height(board, dq, dr)
                if dk == tk:
                    # The target's origin - after removing target, check if empty
                    if len(board[tk]) <= 1:
                        dest_h = 0  # will be empty
                    else:
                        continue  # still occupied
                if dest_h > 0:
                    continue

                # Gate check: can piece fall from pillbug to destination?
                # Piece is on top of pillbug (height = pillbug_h)
                # Create a temporary board state for this check
                # We need to account for target removed and sitting on pillbug
                # Simplified: check gate from pillbug to dest at height pillbug_h
                temp_board = dict(board)
                # Remove target from its position
                temp_stack = list(board[tk])
                temp_stack.pop()
                temp_board = dict(board)
                if temp_stack:
                    temp_board[tk] = temp_stack
                else:
                    temp_board = {k: v for k, v in board.items() if k != tk}

                # Target is now on pillbug, pillbug stack height is now pillbug_h + 1
                # But for gate check, we check from pillbug pos to dest
                effective_h = self._height(temp_board, q, r)  # pillbug height without target on it

                if self._can_step_elevated_temp(temp_board, q, r, effective_h, dq, dr):
                    moves.append({
                        "action": "pillbug",
                        "by": [q, r],
                        "target": [tq, tr],
                        "to": [dq, dr]
                    })

        return moves

    # ----------------------------------------------------------
    # Temp board helpers
    # ----------------------------------------------------------

    def _temp_remove(self, board, key):
        """Return a new board dict with top piece at key removed."""
        temp = {}
        for k, v in board.items():
            if k == key:
                if len(v) > 1:
                    temp[k] = v[:-1]
                # else: don't include (removed)
            else:
                temp[k] = v
        return temp

    def _can_slide_ground_temp(self, board, sq, sr, dq, dr):
        """Ground slide check on a temporary board (no exclude_key needed)."""
        if not self._are_adjacent(sq, sr, dq, dr):
            return False

        l, r = self._get_gate_cells(sq, sr, dq, dr)
        if l is None:
            return False

        hl = self._height(board, l[0], l[1])
        hr = self._height(board, r[0], r[1])

        if hl > 0 and hr > 0:
            return False
        if hl == 0 and hr == 0:
            return False

        # Destination must be empty
        if self._height(board, dq, dr) > 0:
            return False

        return True

    def _can_step_elevated_temp(self, board, sq, sr, sh, dq, dr):
        """Elevated step check on temporary board."""
        if not self._are_adjacent(sq, sr, dq, dr):
            return False

        l, r = self._get_gate_cells(sq, sr, dq, dr)
        if l is None:
            return False

        hl = self._height(board, l[0], l[1])
        hr = self._height(board, r[0], r[1])
        hd = self._height(board, dq, dr)

        threshold = max(sh, hd)
        if threshold > 0 and hl >= threshold and hr >= threshold:
            return False

        return True


# ============================================================
# SECTION 2 — DISPLAY AND INPUT (Pygame)
# ============================================================

import pygame
import sys
import math

# --- Colors ---
BG_COLOR = (35, 39, 46)
BOARD_BG = (50, 55, 64)
GRID_COLOR = (72, 78, 88)
WHITE_PIECE = (248, 243, 233)
BLACK_PIECE = (45, 48, 56)
WHITE_PIECE_BORDER = (195, 190, 180)
BLACK_PIECE_BORDER = (85, 88, 100)
WHITE_TEXT = (35, 35, 35)
BLACK_TEXT = (225, 225, 230)
HIGHLIGHT_MOVE = (70, 200, 115)
HIGHLIGHT_MOVE_FILL = (70, 200, 115, 80)
HIGHLIGHT_SELECT = (90, 145, 255)
HIGHLIGHT_TARGET = (255, 170, 50)
HIGHLIGHT_PILLBUG_DEST = (200, 120, 255)
TEXT_COLOR = (215, 218, 225)
DIM_TEXT = (110, 115, 125)
PANEL_BG = (42, 46, 54)
PANEL_BORDER = (62, 66, 76)
BUTTON_COLOR = (65, 125, 175)
BUTTON_HOVER = (85, 150, 200)
STATUS_GREEN = (110, 215, 135)
STATUS_RED = (225, 95, 95)
STATUS_YELLOW = (255, 210, 80)
STACK_BADGE = (255, 200, 55)
COORD_COLOR = (65, 70, 80)

# --- Layout ---
HEX_SIZE = 34
WINDOW_W = 1280
WINDOW_H = 820
PANEL_W = 185
SQRT3 = math.sqrt(3)

# Full piece names for display
PIECE_NAMES = {
    "queen": "Queen Bee", "spider": "Spider", "beetle": "Beetle",
    "grasshopper": "Grasshopper", "ant": "Soldier Ant", "mosquito": "Mosquito",
    "ladybug": "Ladybug", "pillbug": "Pillbug"
}


def hex_to_pixel(q, r, ox, oy):
    """Axial hex to pixel (flat-top orientation)."""
    x = HEX_SIZE * 1.5 * q + ox
    y = HEX_SIZE * (SQRT3 * 0.5 * q + SQRT3 * r) + oy
    return x, y


def pixel_to_hex(px, py, ox, oy):
    """Pixel to axial hex (flat-top)."""
    x = (px - ox) / HEX_SIZE
    y = (py - oy) / HEX_SIZE
    q = 2.0 / 3 * x
    r = -1.0 / 3 * x + SQRT3 / 3 * y
    # Round to nearest hex
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return int(rq), int(rr)


def hex_corners(cx, cy, size):
    """Flat-top hexagon corners."""
    return [(cx + size * math.cos(math.radians(60 * i)),
             cy + size * math.sin(math.radians(60 * i))) for i in range(6)]


class HiveDisplay:
    """Pygame display and input handler for Hive."""

    # Selection modes
    MODE_NONE = 0
    MODE_HAND_PIECE = 1       # Piece from hand selected, showing placement destinations
    MODE_BOARD_PIECE = 2      # Board piece selected, showing move destinations
    MODE_PILLBUG_SELECT = 3   # Pillbug/Mosquito selected, showing targets for ability
    MODE_PILLBUG_TARGET = 4   # Pillbug target selected, showing drop destinations

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Hive — Human vs Human")
        self.clock = pygame.time.Clock()

        # Fonts
        self.font_title = pygame.font.SysFont("Arial", 22, bold=True)
        self.font_medium = pygame.font.SysFont("Arial", 17)
        self.font_small = pygame.font.SysFont("Arial", 13)
        self.font_piece = pygame.font.SysFont("Arial", 15, bold=True)
        self.font_tiny = pygame.font.SysFont("Arial", 10)
        self.font_status = pygame.font.SysFont("Arial", 18, bold=True)

        self.game = HiveGame()
        self.state = self.game.get_initial_state()
        self.legal_moves = self.game.get_legal_moves(self.state, self.state["current_player"])

        # View offset (panning)
        self.offset_x = WINDOW_W // 2
        self.offset_y = WINDOW_H // 2

        # Selection state
        self.mode = self.MODE_NONE
        self.sel_hand_piece = None       # (player, piece_type)
        self.sel_board_pos = None        # (q, r)
        self.sel_pillbug_pos = None      # (q, r) — the pillbug using ability
        self.sel_pillbug_target = None   # (q, r) — the piece being targeted
        self.move_destinations = []      # [[q,r], ...] for movement
        self.place_destinations = []     # [[q,r], ...] for placement
        self.pillbug_targets = []        # [[q,r], ...] targets for pillbug ability
        self.pillbug_drop_dests = []     # [[q,r], ...] destinations after selecting target
        self.current_moves = []          # matching moves for current selection

        # Panning
        self.panning = False
        self.pan_start = None
        self.pan_offset_start = None

        # UI rects
        self.left_panel = pygame.Rect(0, 0, PANEL_W, WINDOW_H)
        self.right_panel = pygame.Rect(WINDOW_W - PANEL_W, 0, PANEL_W, WINDOW_H)
        self.board_area = pygame.Rect(PANEL_W, 0, WINDOW_W - 2 * PANEL_W, WINDOW_H)
        self.hand_rects = {"white": {}, "black": {}}
        self.new_game_btn = pygame.Rect(WINDOW_W - PANEL_W + 12, WINDOW_H - 52, PANEL_W - 24, 36)
        self.pass_btn = pygame.Rect(PANEL_W + 10, WINDOW_H - 52, 120, 36)

        # Message
        self.status_msg = ""
        self.status_color = TEXT_COLOR

        # Overlay surface for alpha blending
        self.overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:
                        self.panning = False
                elif event.type == pygame.MOUSEMOTION:
                    if self.panning and self.pan_start:
                        dx = event.pos[0] - self.pan_start[0]
                        dy = event.pos[1] - self.pan_start[1]
                        self.offset_x = self.pan_offset_start[0] + dx
                        self.offset_y = self.pan_offset_start[1] + dy
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._clear_selection()
                    elif event.key == pygame.K_n:
                        self._new_game()

            self._draw()
            self.clock.tick(60)
        pygame.quit()

    # ----------------------------------------------------------
    # State management
    # ----------------------------------------------------------

    def _new_game(self):
        self.state = self.game.get_initial_state()
        self.legal_moves = self.game.get_legal_moves(self.state, self.state["current_player"])
        self._clear_selection()
        self.offset_x = WINDOW_W // 2
        self.offset_y = WINDOW_H // 2

    def _clear_selection(self):
        self.mode = self.MODE_NONE
        self.sel_hand_piece = None
        self.sel_board_pos = None
        self.sel_pillbug_pos = None
        self.sel_pillbug_target = None
        self.move_destinations = []
        self.place_destinations = []
        self.pillbug_targets = []
        self.pillbug_drop_dests = []
        self.current_moves = []
        self.status_msg = ""

    def _execute_move(self, move):
        player = self.state["current_player"]
        self.state = self.game.apply_move(self.state, player, move)
        self.legal_moves = self.game.get_legal_moves(self.state, self.state["current_player"])
        self._clear_selection()

    def _select_hand_piece(self, player, piece_type):
        self._clear_selection()
        self.mode = self.MODE_HAND_PIECE
        self.sel_hand_piece = (player, piece_type)
        self.current_moves = [
            m for m in self.legal_moves
            if m["action"] == "place" and m["piece"] == piece_type
        ]
        self.place_destinations = [m["to"] for m in self.current_moves]
        self.status_msg = f"Place {PIECE_NAMES[piece_type]}: click a green cell"

    def _select_board_piece(self, q, r):
        self._clear_selection()
        # Gather move-type moves
        movement = [
            m for m in self.legal_moves
            if m["action"] == "move" and m["from"] == [q, r]
        ]
        # Gather pillbug ability moves where this piece is the actor
        pb_ability = [
            m for m in self.legal_moves
            if m["action"] == "pillbug" and m.get("by") == [q, r]
        ]

        if not movement and not pb_ability:
            self.status_msg = "This piece has no legal moves"
            return

        self.sel_board_pos = (q, r)

        if pb_ability and movement:
            # Has both regular moves and pillbug ability
            self.mode = self.MODE_BOARD_PIECE
            self.current_moves = movement + pb_ability
            self.move_destinations = [m["to"] for m in movement]
            # Collect unique pillbug targets
            seen = set()
            self.pillbug_targets = []
            for m in pb_ability:
                t = tuple(m["target"])
                if t not in seen:
                    seen.add(t)
                    self.pillbug_targets.append(m["target"])
            top = self.game._top_piece(self.state["board"], q, r)
            tname = PIECE_NAMES.get(top["type"], top["type"]) if top else "Piece"
            self.status_msg = f"{tname}: click green to move, or orange target for ability"
        elif movement:
            self.mode = self.MODE_BOARD_PIECE
            self.current_moves = movement
            self.move_destinations = [m["to"] for m in movement]
            top = self.game._top_piece(self.state["board"], q, r)
            tname = PIECE_NAMES.get(top["type"], top["type"]) if top else "Piece"
            self.status_msg = f"Move {tname}: click a green cell"
        else:
            # Only pillbug ability
            self.mode = self.MODE_PILLBUG_SELECT
            self.sel_pillbug_pos = (q, r)
            self.current_moves = pb_ability
            seen = set()
            self.pillbug_targets = []
            for m in pb_ability:
                t = tuple(m["target"])
                if t not in seen:
                    seen.add(t)
                    self.pillbug_targets.append(m["target"])
            self.status_msg = "Pillbug ability: click an orange target piece"

    def _select_pillbug_target(self, tq, tr):
        """After selecting a pillbug, select which piece to grab."""
        by = self.sel_pillbug_pos or self.sel_board_pos
        if not by:
            return
        bq, br = by

        # Find matching moves for this target
        matching = [
            m for m in self.legal_moves
            if m["action"] == "pillbug" and m.get("by") == [bq, br] and m["target"] == [tq, tr]
        ]
        if not matching:
            return

        self.mode = self.MODE_PILLBUG_TARGET
        self.sel_pillbug_pos = (bq, br)
        self.sel_pillbug_target = (tq, tr)
        self.current_moves = matching
        self.pillbug_drop_dests = [m["to"] for m in matching]
        top = self.game._top_piece(self.state["board"], tq, tr)
        tname = PIECE_NAMES.get(top["type"], top["type"]) if top else "piece"
        self.status_msg = f"Drop {tname}: click a purple cell"

    # ----------------------------------------------------------
    # Input handling
    # ----------------------------------------------------------

    def _handle_click(self, event):
        mx, my = event.pos

        # Right-click pan
        if event.button == 3:
            self.panning = True
            self.pan_start = (mx, my)
            self.pan_offset_start = (self.offset_x, self.offset_y)
            return

        if event.button == 4:  # scroll up — zoom not implemented, ignore
            return
        if event.button == 5:
            return
        if event.button != 1:
            return

        # New game button
        if self.new_game_btn.collidepoint(mx, my):
            self._new_game()
            return

        if self.state["game_over"]:
            return

        player = self.state["current_player"]

        # Pass button (visible when only option is pass)
        is_pass_only = (len(self.legal_moves) == 1 and self.legal_moves[0]["action"] == "pass")
        if is_pass_only and self.pass_btn.collidepoint(mx, my):
            self._execute_move(self.legal_moves[0])
            return

        # Hand panel clicks
        if self.left_panel.collidepoint(mx, my) and player == "white":
            self._check_hand_click("white", mx, my)
            return
        if self.right_panel.collidepoint(mx, my) and player == "black":
            self._check_hand_click("black", mx, my)
            return

        # Board clicks
        if not self.board_area.collidepoint(mx, my):
            return

        hq, hr = pixel_to_hex(mx, my, self.offset_x, self.offset_y)

        if self.mode == self.MODE_HAND_PIECE:
            # Try to place
            for m in self.current_moves:
                if m["to"] == [hq, hr]:
                    self._execute_move(m)
                    return
            self._clear_selection()

        elif self.mode == self.MODE_BOARD_PIECE:
            # Check if clicking a move destination
            for m in self.current_moves:
                if m["action"] == "move" and m["to"] == [hq, hr]:
                    self._execute_move(m)
                    return

            # Check if clicking a pillbug target
            if self.pillbug_targets:
                for t in self.pillbug_targets:
                    if t == [hq, hr]:
                        self._select_pillbug_target(hq, hr)
                        return

            # Click on another friendly piece?
            self._try_select_piece(hq, hr, player)

        elif self.mode == self.MODE_PILLBUG_SELECT:
            # Click a target
            for t in self.pillbug_targets:
                if t == [hq, hr]:
                    self._select_pillbug_target(hq, hr)
                    return
            self._try_select_piece(hq, hr, player)

        elif self.mode == self.MODE_PILLBUG_TARGET:
            # Click a drop destination
            for m in self.current_moves:
                if m["to"] == [hq, hr]:
                    self._execute_move(m)
                    return
            # Go back
            if self.sel_pillbug_pos:
                bq, br = self.sel_pillbug_pos
                self._select_board_piece(bq, br)
            else:
                self._clear_selection()

        else:  # MODE_NONE
            self._try_select_piece(hq, hr, player)

    def _check_hand_click(self, player, mx, my):
        for piece_type, rect in self.hand_rects[player].items():
            if rect.collidepoint(mx, my):
                if self.state["hands"][player].get(piece_type, 0) > 0:
                    # Check if any placement moves exist for this piece
                    has_placement = any(
                        m["action"] == "place" and m["piece"] == piece_type
                        for m in self.legal_moves
                    )
                    if has_placement:
                        self._select_hand_piece(player, piece_type)
                    else:
                        self._clear_selection()
                        self.status_msg = f"Cannot place {piece_type} now"
                return

    def _try_select_piece(self, hq, hr, player):
        """Try to select a board piece at (hq, hr)."""
        top = self.game._top_piece(self.state["board"], hq, hr)
        if top and top["owner"] == player:
            # Check if this piece has any legal action
            has_moves = any(
                (m["action"] == "move" and m["from"] == [hq, hr]) or
                (m["action"] == "pillbug" and m.get("by") == [hq, hr])
                for m in self.legal_moves
            )
            if has_moves:
                self._select_board_piece(hq, hr)
            else:
                self._clear_selection()
                self.status_msg = "This piece cannot move (pinned or blocked)"
        else:
            self._clear_selection()

    # ----------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------

    def _draw(self):
        self.screen.fill(BG_COLOR)
        pygame.draw.rect(self.screen, BOARD_BG, self.board_area)

        self._draw_board()
        self._draw_hand_panel("white", self.left_panel)
        self._draw_hand_panel("black", self.right_panel)
        self._draw_status_bar()

        # New game button
        self._draw_button(self.new_game_btn, "New Game (N)")

        # Pass button
        is_pass_only = (len(self.legal_moves) == 1 and
                        not self.state["game_over"] and
                        self.legal_moves[0]["action"] == "pass")
        if is_pass_only:
            self._draw_button(self.pass_btn, "Pass Turn", color=(180, 80, 80), hover_color=(210, 100, 100))

        pygame.display.flip()

    def _draw_board(self):
        board = self.state["board"]

        # Collect cells to render
        cells = set()
        for key in board:
            if board[key]:
                q, r = self.game._parse_key(key)
                cells.add((q, r))
                for nq, nr in self.game._neighbors(q, r):
                    cells.add((nq, nr))

        # Add highlighted cells
        all_highlights = (self.move_destinations + self.place_destinations +
                          self.pillbug_drop_dests)
        for d in all_highlights:
            cells.add((d[0], d[1]))
            for nq, nr in self.game._neighbors(d[0], d[1]):
                cells.add((nq, nr))
        for t in self.pillbug_targets:
            cells.add((t[0], t[1]))

        # Empty board: show origin region
        if not board:
            for dq in range(-3, 4):
                for dr in range(-3, 4):
                    cells.add((dq, dr))

        # Draw empty grid cells
        for (q, r) in cells:
            key = self.game._key(q, r)
            if key in board and board[key]:
                continue  # draw pieces separately
            px, py = hex_to_pixel(q, r, self.offset_x, self.offset_y)
            if not (PANEL_W - 40 < px < WINDOW_W - PANEL_W + 40 and -50 < py < WINDOW_H + 50):
                continue
            corners = hex_corners(px, py, HEX_SIZE - 1)
            pygame.draw.polygon(self.screen, GRID_COLOR, corners, 1)
            # Coord label
            ct = self.font_tiny.render(f"{q},{r}", True, COORD_COLOR)
            self.screen.blit(ct, ct.get_rect(center=(px, py)))

        # Draw placement highlights (green, semi-transparent fill)
        self.overlay.fill((0, 0, 0, 0))
        for d in self.place_destinations:
            px, py = hex_to_pixel(d[0], d[1], self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE - 2)
            pygame.draw.polygon(self.overlay, (70, 200, 115, 60), corners)
            pygame.draw.polygon(self.overlay, (70, 200, 115, 200), corners, 2)

        # Draw move highlights (green)
        for d in self.move_destinations:
            px, py = hex_to_pixel(d[0], d[1], self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE - 2)
            pygame.draw.polygon(self.overlay, (70, 200, 115, 60), corners)
            pygame.draw.polygon(self.overlay, (70, 200, 115, 200), corners, 2)

        # Draw pillbug drop destinations (purple)
        for d in self.pillbug_drop_dests:
            px, py = hex_to_pixel(d[0], d[1], self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE - 2)
            pygame.draw.polygon(self.overlay, (200, 120, 255, 60), corners)
            pygame.draw.polygon(self.overlay, (200, 120, 255, 200), corners, 2)

        self.screen.blit(self.overlay, (0, 0))

        # Draw pieces
        for key in board:
            if not board[key]:
                continue
            q, r = self.game._parse_key(key)
            stack = board[key]
            px, py = hex_to_pixel(q, r, self.offset_x, self.offset_y)
            if not (PANEL_W - 40 < px < WINDOW_W - PANEL_W + 40):
                continue

            # Draw stack layers
            for i, piece in enumerate(stack):
                off = i * 4
                self._draw_piece_hex(px - off, py - off, piece, HEX_SIZE - 2,
                                     is_top=(i == len(stack) - 1))

            # Stack badge
            if len(stack) > 1:
                bx = px + HEX_SIZE - 10
                by = py - HEX_SIZE + 10
                pygame.draw.circle(self.screen, STACK_BADGE, (int(bx), int(by)), 9)
                pygame.draw.circle(self.screen, (200, 160, 30), (int(bx), int(by)), 9, 1)
                st = self.font_tiny.render(str(len(stack)), True, (30, 30, 30))
                self.screen.blit(st, st.get_rect(center=(bx, by)))

            # Coordinate label below piece
            top = stack[-1]
            cc = (140, 135, 125) if top["owner"] == "white" else (130, 133, 145)
            ct = self.font_tiny.render(f"{q},{r}", True, cc)
            self.screen.blit(ct, ct.get_rect(center=(px, py + HEX_SIZE * 0.6)))

        # Draw pillbug target highlights (orange ring around piece)
        for t in self.pillbug_targets:
            px, py = hex_to_pixel(t[0], t[1], self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE + 1)
            pygame.draw.polygon(self.screen, HIGHLIGHT_TARGET, corners, 3)

        # Draw pillbug target selected highlight
        if self.sel_pillbug_target:
            tq, tr = self.sel_pillbug_target
            px, py = hex_to_pixel(tq, tr, self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE + 2)
            pygame.draw.polygon(self.screen, (255, 100, 50), corners, 3)

        # Draw selection highlight (blue ring)
        if self.sel_board_pos:
            sq, sr = self.sel_board_pos
            px, py = hex_to_pixel(sq, sr, self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE + 1)
            pygame.draw.polygon(self.screen, HIGHLIGHT_SELECT, corners, 3)

        if self.sel_pillbug_pos and self.sel_pillbug_pos != self.sel_board_pos:
            sq, sr = self.sel_pillbug_pos
            px, py = hex_to_pixel(sq, sr, self.offset_x, self.offset_y)
            corners = hex_corners(px, py, HEX_SIZE + 1)
            pygame.draw.polygon(self.screen, HIGHLIGHT_SELECT, corners, 3)

    def _draw_piece_hex(self, cx, cy, piece, size, is_top=True):
        corners = hex_corners(cx, cy, size)

        if piece["owner"] == "white":
            fill = WHITE_PIECE if is_top else (220, 215, 205)
            border = WHITE_PIECE_BORDER
            text_col = WHITE_TEXT
        else:
            fill = BLACK_PIECE if is_top else (35, 38, 46)
            border = BLACK_PIECE_BORDER
            text_col = BLACK_TEXT

        pygame.draw.polygon(self.screen, fill, corners)
        pygame.draw.polygon(self.screen, border, corners, 2)

        abbrev = PIECE_ABBREV.get(piece["type"], "?")
        t = self.font_piece.render(abbrev, True, text_col)
        self.screen.blit(t, t.get_rect(center=(cx, cy - 1)))

    def _draw_hand_panel(self, player, rect):
        pygame.draw.rect(self.screen, PANEL_BG, rect)
        edge_x = rect.right if player == "white" else rect.left
        pygame.draw.line(self.screen, PANEL_BORDER, (edge_x, 0), (edge_x, WINDOW_H), 2)

        is_current = self.state["current_player"] == player
        col = STATUS_GREEN if is_current else DIM_TEXT
        title = self.font_title.render(player.upper(), True, col)
        self.screen.blit(title, title.get_rect(centerx=rect.centerx, top=12))

        if is_current and not self.state["game_over"]:
            tag = self.font_small.render("● YOUR TURN", True, STATUS_GREEN)
            self.screen.blit(tag, tag.get_rect(centerx=rect.centerx, top=40))

        # Count pieces on board for this player
        on_board = 0
        for k, stack in self.state["board"].items():
            for p in stack:
                if p["owner"] == player:
                    on_board += 1
        in_hand = sum(self.state["hands"][player].values())
        info = self.font_tiny.render(f"Hand: {in_hand}  Board: {on_board}", True, DIM_TEXT)
        self.screen.blit(info, info.get_rect(centerx=rect.centerx, top=58))

        hand = self.state["hands"][player]
        piece_order = ["queen", "beetle", "grasshopper", "spider",
                       "ant", "mosquito", "ladybug", "pillbug"]

        self.hand_rects[player] = {}
        y0 = 80

        for i, pt in enumerate(piece_order):
            count = hand.get(pt, 0)
            y = y0 + i * 48
            pr = pygame.Rect(rect.left + 8, y, rect.width - 16, 43)
            self.hand_rects[player][pt] = pr

            is_selected = (self.sel_hand_piece and
                           self.sel_hand_piece[0] == player and
                           self.sel_hand_piece[1] == pt)

            if count > 0 and is_current:
                bg = (70, 82, 105) if not is_selected else (80, 120, 200)
                pygame.draw.rect(self.screen, bg, pr, border_radius=5)
                if is_selected:
                    pygame.draw.rect(self.screen, HIGHLIGHT_SELECT, pr, 2, border_radius=5)
            else:
                pygame.draw.rect(self.screen, (50, 53, 60), pr, border_radius=5)

            # Mini piece
            mini = {"type": pt, "owner": player}
            self._draw_piece_hex(rect.left + 32, y + 22, mini, 15)

            # Text
            nc = TEXT_COLOR if (count > 0 and is_current) else (80, 83, 92)
            nm = self.font_small.render(PIECE_NAMES[pt], True, nc)
            self.screen.blit(nm, (rect.left + 54, y + 7))
            ct = self.font_small.render(f"× {count}", True, nc)
            self.screen.blit(ct, (rect.left + 54, y + 24))

    def _draw_status_bar(self):
        bar = pygame.Rect(PANEL_W, WINDOW_H - 55, WINDOW_W - 2 * PANEL_W, 55)
        pygame.draw.rect(self.screen, PANEL_BG, bar)
        pygame.draw.line(self.screen, PANEL_BORDER, (bar.left, bar.top), (bar.right, bar.top), 1)

        player = self.state["current_player"]

        if self.state["game_over"]:
            w = self.state["winner"]
            if w == "draw":
                msg = "GAME OVER — DRAW"
                col = STATUS_YELLOW
            else:
                msg = f"GAME OVER — {w.upper()} WINS!"
                col = STATUS_GREEN
        elif self.status_msg:
            msg = self.status_msg
            col = TEXT_COLOR
        else:
            p_turns = self.state["white_turns"] if player == "white" else self.state["black_turns"]
            msg = f"Turn {self.state['turn_number']}  ·  {player.capitalize()}'s move (turn #{p_turns + 1})"
            is_pass = (len(self.legal_moves) == 1 and self.legal_moves[0]["action"] == "pass")
            if is_pass:
                msg += "  — MUST PASS (no legal actions)"
                col = STATUS_RED
            else:
                col = TEXT_COLOR

        mt = self.font_status.render(msg, True, col)
        self.screen.blit(mt, mt.get_rect(centerx=bar.centerx, centery=bar.top + 18))

        hint = self.font_tiny.render(
            "Right-drag: pan  |  Esc: deselect  |  N: new game", True, (85, 90, 100))
        self.screen.blit(hint, hint.get_rect(centerx=bar.centerx, centery=bar.bottom - 12))

    def _draw_button(self, rect, text, color=None, hover_color=None):
        mx, my = pygame.mouse.get_pos()
        hover = rect.collidepoint(mx, my)
        c = (hover_color or BUTTON_HOVER) if hover else (color or BUTTON_COLOR)
        pygame.draw.rect(self.screen, c, rect, border_radius=5)
        t = self.font_small.render(text, True, (255, 255, 255))
        self.screen.blit(t, t.get_rect(center=rect.center))


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    display = HiveDisplay()
    display.run()
