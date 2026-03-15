"""Claude API-powered bot for Board Games Online.

Uses the Anthropic Python SDK to ask Claude to analyze positions and
choose moves.  Fully game-agnostic — works through the AbstractBoardGame
interface only, never imports any specific game module.

The bot formats the game state as readable text, lists all legal moves
with numbers, and asks Claude to pick one.  This numbered-list approach
eliminates parsing ambiguity.

Usage::

    from client.claude_bot import ClaudeBot, needs_api_key, save_api_key

    if needs_api_key():
        save_api_key(key_from_user)

    bot = ClaudeBot()
    move = bot.choose_move(logic, state, my_player)
"""

import json
import os
import re

# ── API key persistence ──────────────────────────────────────────────────────

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".board_games_online")
_KEY_FILE = os.path.join(_CONFIG_DIR, "anthropic_key.txt")

# In-memory cache so we don't re-read disk every call
_cached_key = None


def needs_api_key() -> bool:
    """Return True if no Anthropic API key is configured."""
    return not _load_key()


def save_api_key(key: str):
    """Save an Anthropic API key so it persists across sessions."""
    global _cached_key
    key = key.strip()
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_KEY_FILE, "w") as f:
        f.write(key)
    _cached_key = key


def _load_key() -> str:
    """Return the saved API key, or empty string if none."""
    global _cached_key
    if _cached_key:
        return _cached_key

    # Check environment variable first
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        _cached_key = env_key
        return env_key

    # Check config file
    if os.path.isfile(_KEY_FILE):
        try:
            with open(_KEY_FILE) as f:
                key = f.read().strip()
            if key:
                _cached_key = key
                return key
        except OSError:
            pass
    return ""


# ── State formatting ─────────────────────────────────────────────────────────


def _format_state(state, game_name, player):
    """Convert a game state dict into human-readable text.

    This is game-agnostic — it inspects the state structure and formats
    it as cleanly as possible without knowing which game it is.
    """
    lines = [f"Game: {game_name}", f"Your player: {player}", ""]

    rendered_keys = set()

    # Board rendering — detect the structure and format accordingly
    board = state.get("board")
    if board is not None:
        rendered_keys.add("board")
        lines.append("Board:")
        if isinstance(board, dict):
            lines.append(_format_dict_board(board))
        elif isinstance(board, list):
            if board and isinstance(board[0], list):
                lines.append(_format_grid_board(board))
            else:
                lines.append(_format_flat_board(board))

    # Multi-board games (Shobu: "boards" key)
    boards = state.get("boards")
    if boards is not None and isinstance(boards, list):
        rendered_keys.add("boards")
        for i, b in enumerate(boards):
            lines.append(f"Board {i}:")
            if isinstance(b, list) and b and isinstance(b[0], list):
                lines.append(_format_grid_board(b))
            else:
                lines.append(str(b))

    # Mancala-style (Bao): player dicts with front/back rows
    for pk in ("1", "2"):
        pdata = state.get(pk)
        if isinstance(pdata, dict) and "front" in pdata:
            rendered_keys.add(pk)
            label = f"Player {pk}"
            front = pdata.get("front", [])
            back = pdata.get("back", [])
            store = pdata.get("store", 0)
            nyumba = "owned" if pdata.get("nyumba_owned") else "lost"
            lines.append(
                f"{label}: front={front}  back={back}  "
                f"store={store}  nyumba={nyumba}"
            )

    # Hex stacks (Tumbleweed): stacks dict
    stacks = state.get("stacks")
    if isinstance(stacks, dict) and stacks:
        rendered_keys.add("stacks")
        lines.append("Stacks (coord -> [owner, height]):")
        for k in sorted(stacks.keys()):
            v = stacks[k]
            lines.append(f"  {k}: owner={v[0]} height={v[1]}")

    # Ring/marker games (YINSH): rings + markers dicts
    rings = state.get("rings")
    markers = state.get("markers")
    if isinstance(rings, dict):
        rendered_keys.add("rings")
        if rings:
            lines.append("Rings:")
            for k in sorted(rings.keys()):
                lines.append(f"  {k}: player {rings[k]}")
        else:
            lines.append("Rings: (none placed)")
    if isinstance(markers, dict):
        rendered_keys.add("markers")
        if markers:
            lines.append("Markers:")
            for k in sorted(markers.keys()):
                lines.append(f"  {k}: player {markers[k]}")

    # Other state fields — skip already-rendered and noise fields
    skip = rendered_keys | {
        "position_counts", "pos_history", "history",
        "winning_chain", "last_move", "captured_last", "message",
        "turn_start_board", "position_history", "ctrl_map",
    }
    for key, val in state.items():
        if key in skip:
            continue
        if isinstance(val, (dict, list)) and len(str(val)) > 300:
            lines.append(f"{key}: <{type(val).__name__} with {len(val)} entries>")
        else:
            lines.append(f"{key}: {val}")

    return "\n".join(lines)


def _format_grid_board(board):
    """Format a 2D list board as a labeled grid."""
    rows = []
    cols = len(board[0]) if board else 0
    # Column header
    if cols <= 26:
        header = "    " + "  ".join(chr(ord('A') + c) for c in range(cols))
        rows.append(header)
    for r, row in enumerate(board):
        label = f"{r:>3} "
        cells = []
        for cell in row:
            if cell is None or cell == "" or cell == 0:
                cells.append(" .")
            elif isinstance(cell, list):
                # Stack (Bashni) — show top piece
                cells.append(f" {_piece_char(cell)}")
            else:
                cells.append(f" {_piece_char(cell)}")
        rows.append(label + "".join(cells))
    return "\n".join(rows)


def _format_dict_board(board):
    """Format a dict-keyed board (hex coordinates)."""
    if not board:
        return "(empty)"
    # Parse coordinates to find bounds
    entries = []
    for k, v in board.items():
        parts = k.split(",")
        coords = [int(p) for p in parts]
        entries.append((coords, v))

    if not entries:
        return "(empty)"

    # Show non-empty cells only, sorted
    non_empty = [(c, v) for c, v in entries if v and v != 0]
    if not non_empty:
        return "(all empty)"

    if len(non_empty) > 50:
        # Too many to list — summarize
        counts = {}
        for _, v in entries:
            counts[v] = counts.get(v, 0) + 1
        return "  " + ", ".join(f"{v}: {n} cells" for v, n in sorted(counts.items()))

    lines = []
    for coords, v in sorted(non_empty):
        coord_str = ",".join(str(c) for c in coords)
        lines.append(f"  ({coord_str}): {_piece_char(v)}")
    return "\n".join(lines)


def _format_flat_board(board):
    """Format a flat-list board (like BaghChal's 25-node board)."""
    n = len(board)
    # Try to detect a square layout
    side = int(n ** 0.5)
    if side * side == n:
        rows = []
        for r in range(side):
            cells = []
            for c in range(side):
                val = board[r * side + c]
                cells.append(_piece_char(val) if val else ".")
            rows.append(f"  {' '.join(cells)}")
        return "\n".join(rows)
    # Otherwise just list
    return "  " + " ".join(_piece_char(v) if v else "." for v in board)


def _piece_char(val):
    """Convert a piece value to a short display character."""
    if val is None or val == "" or val == 0:
        return "."
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val[0] if val else "."
    if isinstance(val, dict):
        # Hive piece dict: {"type": "ant", "owner": 1}
        t = val.get("type", "?")
        o = val.get("owner", "?")
        return f"{t[0].upper()}{o}" if isinstance(t, str) else "?"
    if isinstance(val, list):
        if not val:
            return "."
        top = val[-1]
        # Hive stack: list of {"type":..., "owner":...} dicts — show top
        if isinstance(top, dict) and "type" in top:
            o = "W" if top.get("owner") == 1 else "B"
            t = top["type"][0].upper() if isinstance(top["type"], str) else "?"
            h = len(val)
            return f"{o}{t}" if h == 1 else f"{o}{t}{h}"
        # Bashni stack: list of [color, rank] pairs — show top piece
        if isinstance(top, list) and len(top) >= 2:
            color = top[0][0] if isinstance(top[0], str) else str(top[0])
            return color
        # Single [color, rank] pair
        if len(val) >= 2 and isinstance(val[0], str) and isinstance(val[1], str):
            return val[0][0]
        return str(val[0])[:1]
    return str(val)[:1]


_MAX_LISTED_MOVES = 150  # cap to keep prompts under token limits


def _format_moves(moves):
    """Format legal moves as a numbered list.

    If there are more than ``_MAX_LISTED_MOVES``, only the first batch
    is shown and the total count is noted so Claude knows options exist
    beyond what is listed.
    """
    total = len(moves)
    listed = moves[:_MAX_LISTED_MOVES]
    lines = []
    for i, move in enumerate(listed, 1):
        lines.append(f"  {i}. {json.dumps(move)}")
    if total > _MAX_LISTED_MOVES:
        lines.append(f"  ... ({total - _MAX_LISTED_MOVES} more moves not shown; "
                     f"pick from 1-{total})")
    return "\n".join(lines)


# ── Claude Bot ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a world-class abstract strategy game analyst. You think "
    "concretely and tactically, never in vague generalities. For any "
    "abstract strategy game, you evaluate positions by: counting material "
    "and pieces for each side, measuring who controls more territory or "
    "board space, assessing which pieces are safe versus vulnerable, "
    "detecting immediate threats (can the opponent win, capture, or create "
    "an unstoppable advantage next turn), and identifying forcing moves "
    "(captures, pushes, surrounding moves, connection completions, "
    "territory gains) that demand the opponent respond. You always "
    "consider what the opponent will do after your move. You never choose "
    "a move without first identifying the most urgent threat on the board "
    "and verifying your chosen move addresses it. You prefer moves that "
    "create concrete, measurable advantages over moves that merely look "
    "reasonable."
)

_ANALYSIS_INSTRUCTIONS = (
    "Analyze this position step by step before choosing.\n"
    "(1) Assess the position: count the key metrics for each player — "
    "pieces, territory, threats, vulnerable positions, proximity to any "
    "win condition. State specific numbers.\n"
    "(2) Identify the most urgent threat: what is the most dangerous thing "
    "the opponent can do next turn if you ignore it? Name it concretely. "
    "If there is no urgent threat, state that.\n"
    "(3) Identify your best opportunity: what is the most forcing or "
    "advantageous move available to you — a capture, a push, a surrounding "
    "move, a territory gain, a win-condition advance, a threat creation? "
    "Name it concretely.\n"
    "(4) Evaluate your top 3 candidate moves by number: for each, state "
    "what happens immediately after and what the opponent's best response "
    "would be.\n"
    "(5) Choose the move that prevents the biggest danger or creates the "
    "biggest concrete advantage. End your response with exactly MOVE: X "
    "where X is the number of your chosen move."
)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 2000
_API_TIMEOUT = 30.0  # seconds


class ClaudeBot:
    """Game-agnostic bot powered by the Claude API.

    Falls back to MCTS (strong difficulty) if the API call fails.
    """

    def __init__(self, model=None):
        self.model = model or _DEFAULT_MODEL
        self._client = None
        self._fallback = None
        self.switched_to_fallback = False  # True after API failure

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if self._client is not None:
            return self._client
        key = _load_key()
        if not key:
            return None
        try:
            import anthropic
        except ImportError:
            return None
        self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def _get_fallback(self):
        """Lazy-init the MCTS fallback bot."""
        if self._fallback is None:
            from client.bot import MCTSBot
            self._fallback = MCTSBot("strong")
        return self._fallback

    def choose_move(self, logic, state, player):
        """Choose a move by asking Claude to analyze the position.

        Falls back to MCTS if the API is unavailable or returns
        an unparseable response after retries.
        """
        moves = logic._get_legal_moves(state, player)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # Already switched — use MCTS directly
        if self.switched_to_fallback:
            return self._get_fallback().choose_move(logic, state, player)

        client = self._get_client()
        if client is None:
            self.switched_to_fallback = True
            return self._get_fallback().choose_move(logic, state, player)

        game_name = logic._get_name()
        state_text = _format_state(state, game_name, player)
        moves_text = _format_moves(moves)

        prompt = (
            f"{state_text}\n\n"
            f"Legal moves ({len(moves)} available):\n{moves_text}\n\n"
            f"{_ANALYSIS_INSTRUCTIONS}"
        )

        # Try to get a valid move number from Claude
        chosen = self._ask_claude(client, prompt, len(moves))

        if chosen is not None:
            return moves[chosen]

        # Retry with a focused extraction prompt
        retry_prompt = (
            "Respond with only MOVE: followed by the number of your "
            "chosen move, nothing else."
        )
        chosen = self._ask_claude(client, retry_prompt, len(moves))
        if chosen is not None:
            return moves[chosen]

        # All retries failed — permanently switch to MCTS
        self.switched_to_fallback = True
        return self._get_fallback().choose_move(logic, state, player)

    def _ask_claude(self, client, prompt, n_moves):
        """Send a prompt and parse the response as a move index (0-based).

        Returns the 0-based index, or None if parsing fails.
        """
        try:
            import httpx
            response = client.messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                timeout=httpx.Timeout(_API_TIMEOUT),
            )
            text = response.content[0].text.strip()
            return self._parse_move_number(text, n_moves)
        except Exception:
            return None

    def _parse_move_number(self, text, n_moves):
        """Extract a move number from Claude's response.

        Looks for the last ``MOVE: X`` pattern. Falls back to the last
        bare integer on its own line if no MOVE: tag is found.

        Returns the 0-based index (0 to n_moves-1), or None.
        """
        # Primary: find last "MOVE:" tag
        matches = re.findall(r'MOVE:\s*(\d+)', text, re.IGNORECASE)
        if matches:
            num = int(matches[-1])
            return max(0, min(n_moves - 1, num - 1))

        # Fallback: last line containing a bare integer
        for line in reversed(text.strip().splitlines()):
            line = line.strip()
            numbers = re.findall(r'\d+', line)
            if numbers:
                num = int(numbers[-1])
                if 1 <= num <= n_moves:
                    return num - 1
                if num < 1:
                    return 0
                if num > n_moves:
                    return n_moves - 1
        return None
