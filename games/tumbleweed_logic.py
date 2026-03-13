"""
Tumbleweed -- Pure game logic (no Pygame, no numpy).

Implements the AbstractBoardGame contract for Tumbleweed,
a hex-based abstract strategy game for two players designed by
Mike Zapawa (2020).

Hex cube coordinates (x, y, z where x+y+z=0) are used throughout.
Cells are stored as string keys like "0,1,-1" in dicts.
Moves use [x, y, z] lists.

A move depends on the game phase::

    SETUP: {"cell": [x, y, z]}        -- place a seed
    PIE:   {"swap": true/false}        -- choose whether to swap colours
    PLAY:  {"cell": [x, y, z]}         -- place a stack
           {"pass": true}              -- pass your turn
"""

import copy

try:
    from games.base_game import AbstractBoardGame
except ImportError:
    from base_game import AbstractBoardGame

# ── Constants (exported for display module) ──────────────────────────────────

BOARD_SIZE = 9          # hex-hex edge length (9 -> 217 cells)
RED = 1
WHITE = 2
NEUTRAL = 3

PH_SETUP = "setup"
PH_PIE = "pie"
PH_PLAY = "play"
PH_OVER = "over"

COLOUR_NAME = {RED: "Red", WHITE: "White", NEUTRAL: "Neutral"}

# Six cube-coordinate direction vectors
DIRS = [[1, 0, -1], [1, -1, 0], [0, -1, 1],
        [-1, 0, 1], [-1, 1, 0], [0, 1, -1]]


# ── Pure helper functions ────────────────────────────────────────────────────

def _cell_key(x, y, z):
    """Convert cube coordinates to a string key for dict storage."""
    return f"{x},{y},{z}"


def _key_to_coords(key):
    """Convert a string key back to a list [x, y, z]."""
    parts = key.split(",")
    return [int(parts[0]), int(parts[1]), int(parts[2])]


def _valid(x, y, z):
    """True if (x, y, z) is a valid cell on the hex board."""
    return x + y + z == 0 and max(abs(x), abs(y), abs(z)) <= BOARD_SIZE - 1


def _all_cells():
    """Generate all valid cell keys for the board."""
    cells = []
    s = BOARD_SIZE
    for x in range(-(s - 1), s):
        for z in range(-(s - 1), s):
            y = -x - z
            if _valid(x, y, z):
                cells.append(_cell_key(x, y, z))
    return cells


def _visible_from(cell_key, stacks, all_cells_set):
    """Return list of cell keys for stacks visible along six rays from cell_key.

    Walks outward in each of the six hex directions, stopping at the first
    occupied cell (a stack).
    """
    coords = _key_to_coords(cell_key)
    cx, cy, cz = coords[0], coords[1], coords[2]
    vis = []
    for d in DIRS:
        dx, dy, dz = d[0], d[1], d[2]
        x, y, z = cx + dx, cy + dy, cz + dz
        while True:
            key = _cell_key(x, y, z)
            if key not in all_cells_set:
                break
            if key in stacks:
                vis.append(key)
                break
            x, y, z = x + dx, y + dy, z + dz
    return vis


def _flos(cell_key, colour, stacks, all_cells_set):
    """Count friendly lines of sight to cell_key for the given colour."""
    count = 0
    for v in _visible_from(cell_key, stacks, all_cells_set):
        if stacks[v][0] == colour:
            count += 1
    return count


def _compute_scores(stacks, all_cells, all_cells_set):
    """Compute scores and control map.

    Returns (scores_dict, ctrl_map_dict) where:
      scores_dict = {RED: [own, ctrl, total], WHITE: [own, ctrl, total]}
      ctrl_map_dict = {cell_key: colour or -1 for contested}
    """
    own = {RED: 0, WHITE: 0}
    ctrl = {RED: 0, WHITE: 0}
    cmap = {}
    for cell_key in all_cells:
        if cell_key in stacks:
            c = stacks[cell_key][0]
            if c in (RED, WHITE):
                own[c] += 1
        else:
            vis = _visible_from(cell_key, stacks, all_cells_set)
            cr = 0
            cw = 0
            for v in vis:
                if stacks[v][0] == RED:
                    cr += 1
                elif stacks[v][0] == WHITE:
                    cw += 1
            if cr > cw:
                ctrl[RED] += 1
                cmap[cell_key] = RED
            elif cw > cr:
                ctrl[WHITE] += 1
                cmap[cell_key] = WHITE
            else:
                cmap[cell_key] = -1  # contested
    scores = {
        str(RED): [own[RED], ctrl[RED], own[RED] + ctrl[RED]],
        str(WHITE): [own[WHITE], ctrl[WHITE], own[WHITE] + ctrl[WHITE]],
    }
    return scores, cmap


def _compute_legal_moves(turn, stacks, all_cells, all_cells_set):
    """Compute all legal moves for the given player during PLAY phase.

    Returns a list of dicts: {"cell": [x,y,z]} for placements.
    A cell is legal if the player's friendly LOS count is >= 1 (for empty)
    or greater than the existing stack height (for occupied cells).
    """
    moves = []
    for cell_key in all_cells:
        f = _flos(cell_key, turn, stacks, all_cells_set)
        if cell_key not in stacks:
            if f >= 1:
                moves.append({"cell": _key_to_coords(cell_key)})
        else:
            if f > stacks[cell_key][1]:
                moves.append({"cell": _key_to_coords(cell_key)})
    return moves


def cell_label(x, y, z):
    """Human-readable label: column letter + row number."""
    col_letter = chr(65 + x + BOARD_SIZE - 1)
    row_number = z + BOARD_SIZE
    return f"{col_letter}{row_number}"


# ── Game class ───────────────────────────────────────────────────────────────

class TumbleweedLogic(AbstractBoardGame):
    """Tumbleweed game logic implementing the AbstractBoardGame contract.

    State dict::

        {
            "stacks":     {str: [int, int], ...},  # cell_key -> [colour, height]
            "phase":      str,                     # "setup"/"pie"/"play"/"over"
            "turn":       int,                     # RED (1) or WHITE (2)
            "passes":     int,                     # consecutive pass count
            "setup_step": int,                     # 0 = place Red, 1 = place White
            "winner":     int | None,              # winner colour or None
            "msg":        str,                     # status message
            "scores":     {str: [int,int,int],...}, # player -> [own,ctrl,total]
            "ctrl_map":   {str: int, ...},         # cell_key -> colour or -1
        }

    Moves depend on the phase:
        SETUP: {"cell": [x, y, z]}
        PIE:   {"swap": true/false}
        PLAY:  {"cell": [x, y, z]} or {"pass": true}
    """

    def __init__(self):
        self._all_cells = _all_cells()
        self._all_cells_set = {}
        for key in self._all_cells:
            self._all_cells_set[key] = True
        self._total_cells = len(self._all_cells)

    # ── Required base-class methods ──────────────────────────────────────

    def _get_name(self):
        return "Tumbleweed"

    def _get_player_count(self):
        return 2

    def _create_initial_state(self):
        centre = _cell_key(0, 0, 0)
        stacks = {centre: [NEUTRAL, 2]}
        scores, ctrl_map = _compute_scores(
            stacks, self._all_cells, self._all_cells_set
        )
        return {
            "stacks": stacks,
            "phase": PH_SETUP,
            "turn": RED,
            "passes": 0,
            "setup_step": 0,
            "winner": None,
            "msg": "Host: click any empty cell to place the Red seed",
            "scores": scores,
            "ctrl_map": ctrl_map,
        }

    def _get_current_player(self, state):
        phase = state["phase"]
        if phase == PH_SETUP:
            # During setup, player 1 (RED) controls both seed placements
            return RED
        if phase == PH_PIE:
            # Guest (player 2) decides whether to swap
            return WHITE
        if phase == PH_OVER:
            # Game is over; return the last turn value
            return state["turn"]
        # PH_PLAY
        return state["turn"]

    def _get_legal_moves(self, state, player):
        phase = state["phase"]

        if phase == PH_SETUP:
            # Any empty cell is legal for seed placement
            moves = []
            for cell_key in self._all_cells:
                if cell_key not in state["stacks"]:
                    moves.append({"cell": _key_to_coords(cell_key)})
            return moves

        if phase == PH_PIE:
            return [{"swap": True}, {"swap": False}]

        if phase == PH_PLAY:
            play_moves = _compute_legal_moves(
                state["turn"], state["stacks"],
                self._all_cells, self._all_cells_set
            )
            # Always allow passing
            play_moves.append({"pass": True})
            return play_moves

        # PH_OVER
        return []

    def _apply_move(self, state, player, move):
        new = copy.deepcopy(state)
        phase = new["phase"]

        if phase == PH_SETUP:
            cell_coords = move["cell"]
            cell_key = _cell_key(cell_coords[0], cell_coords[1], cell_coords[2])

            if new["setup_step"] == 0:
                new["stacks"][cell_key] = [RED, 1]
                new["setup_step"] = 1
                new["msg"] = "Host: click any empty cell to place the White seed"
            else:
                new["stacks"][cell_key] = [WHITE, 1]
                new["phase"] = PH_PIE
                new["msg"] = "Guest: choose which colour to play"

        elif phase == PH_PIE:
            # The pie rule: guest decides to swap or not.
            if move.get("swap"):
                # Swap the colours of the two seed stacks.
                for ck, sv in new["stacks"].items():
                    if sv[0] == RED:
                        sv[0] = WHITE
                    elif sv[0] == WHITE:
                        sv[0] = RED
                new["msg"] = "Colours swapped! Red's turn"
            else:
                new["msg"] = "Red's turn"
            # In either case, Red moves first in the play phase.
            new["phase"] = PH_PLAY
            new["turn"] = RED

        elif phase == PH_PLAY:
            if "pass" in move and move["pass"]:
                passer = new["turn"]
                new["passes"] = new["passes"] + 1
                new["turn"] = WHITE if new["turn"] == RED else RED
                if new["passes"] >= 2:
                    new["phase"] = PH_OVER
                    # Recompute scores for final state
                    scores, ctrl_map = _compute_scores(
                        new["stacks"], self._all_cells, self._all_cells_set
                    )
                    new["scores"] = scores
                    new["ctrl_map"] = ctrl_map
                    sr = scores[str(RED)][2]
                    sw = scores[str(WHITE)][2]
                    if sr == sw:
                        new["winner"] = None
                        new["msg"] = f"Game over -- Draw!   Red {sr}  ·  White {sw}"
                    else:
                        winner = RED if sr > sw else WHITE
                        new["winner"] = winner
                        wn = COLOUR_NAME[winner]
                        new["msg"] = f"Game over -- {wn} wins!   Red {sr}  ·  White {sw}"
                else:
                    passer_name = COLOUR_NAME[passer]
                    turn_name = COLOUR_NAME[new["turn"]]
                    new["msg"] = f"{turn_name}'s turn  ({passer_name} passed)"
            else:
                cell_coords = move["cell"]
                cell_key = _cell_key(
                    cell_coords[0], cell_coords[1], cell_coords[2]
                )
                # Calculate the stack height from friendly LOS
                f = _flos(
                    cell_key, new["turn"], new["stacks"],
                    self._all_cells_set
                )
                new["stacks"][cell_key] = [new["turn"], f]
                new["passes"] = 0
                new["turn"] = WHITE if new["turn"] == RED else RED
                turn_name = COLOUR_NAME[new["turn"]]
                new["msg"] = f"{turn_name}'s turn"

        # Recompute scores (unless we already did for game-over above)
        if new["phase"] != PH_OVER:
            scores, ctrl_map = _compute_scores(
                new["stacks"], self._all_cells, self._all_cells_set
            )
            new["scores"] = scores
            new["ctrl_map"] = ctrl_map

        return new

    def _get_game_status(self, state):
        if state["phase"] == PH_OVER:
            winner = state["winner"]
            if winner is None:
                return {"is_over": True, "winner": None, "is_draw": True}
            return {"is_over": True, "winner": winner, "is_draw": False}
        return {"is_over": False, "winner": None, "is_draw": False}

    # ── Efficient override ───────────────────────────────────────────────

    def is_valid_move(self, state, player, move):
        """Validate a single move without enumerating all legal moves."""
        if not isinstance(move, dict):
            return False

        phase = state["phase"]

        if phase == PH_SETUP:
            if "cell" not in move:
                return False
            cell_coords = move["cell"]
            if not isinstance(cell_coords, list) or len(cell_coords) != 3:
                return False
            x, y, z = cell_coords[0], cell_coords[1], cell_coords[2]
            if not all(isinstance(v, int) for v in [x, y, z]):
                return False
            cell_key = _cell_key(x, y, z)
            return (cell_key in self._all_cells_set
                    and cell_key not in state["stacks"])

        if phase == PH_PIE:
            if "swap" not in move:
                return False
            return isinstance(move["swap"], bool)

        if phase == PH_PLAY:
            if "pass" in move:
                return move["pass"] is True

            if "cell" not in move:
                return False
            cell_coords = move["cell"]
            if not isinstance(cell_coords, list) or len(cell_coords) != 3:
                return False
            x, y, z = cell_coords[0], cell_coords[1], cell_coords[2]
            if not all(isinstance(v, int) for v in [x, y, z]):
                return False
            cell_key = _cell_key(x, y, z)
            if cell_key not in self._all_cells_set:
                return False

            turn = state["turn"]
            f = _flos(cell_key, turn, state["stacks"], self._all_cells_set)
            if cell_key not in state["stacks"]:
                return f >= 1
            else:
                return f > state["stacks"][cell_key][1]

        # PH_OVER
        return False

    # ── Extra helpers for client / display use ───────────────────────────

    @property
    def all_cells(self):
        """List of all cell keys on the board."""
        return self._all_cells

    @property
    def all_cells_set(self):
        """Dict acting as a set of all valid cell keys."""
        return self._all_cells_set

    @property
    def total_cells(self):
        """Total number of cells on the board."""
        return self._total_cells

    @staticmethod
    def flos(cell_key, colour, stacks, all_cells_set):
        """Count friendly lines of sight to cell_key for the given colour.

        Exposed for the display module to show LOS info in the side panel.
        """
        return _flos(cell_key, colour, stacks, all_cells_set)

    @staticmethod
    def visible_from(cell_key, stacks, all_cells_set):
        """Return list of cell keys for stacks visible along six rays from cell_key.

        Exposed for the display module.
        """
        return _visible_from(cell_key, stacks, all_cells_set)
