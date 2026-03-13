"""
Abstract base class that every board game in the hub must implement.

The server is authoritative — it owns game state, validates every move, and
broadcasts updates.  This base class defines the universal contract so the
server can manage any game generically.

Subclasses implement the underscore-prefixed abstract methods (e.g.
``_create_initial_state``).  The public methods (without underscore) wrap
them with automatic enforcement of the JSON-serialization contract, turn-
order checks, move-legality checks, and immutability verification.

Serialization rule
------------------
All game state and move data must consist solely of: ``dict`` (string keys
only), ``list``, ``str``, ``int``, ``float``, ``bool``, and ``None``.
No tuples, sets, frozensets, numpy arrays, bytes, enums, or custom objects.
This guarantees safe ``json.dumps`` / ``json.loads`` round-trips over the
network.
"""

import json
from abc import ABC, abstractmethod


class AbstractBoardGame(ABC):
    """Universal template for abstract strategy board games.

    Lifecycle on the server::

        game  = SomeGame()
        state = game.create_initial_state()

        while not game.get_game_status(state)["is_over"]:
            player = game.get_current_player(state)
            moves  = game.get_legal_moves(state, player)
            # ... send moves to client, receive chosen move ...
            state  = game.apply_move(state, player, chosen_move)
    """

    # ── Properties ──────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Human-readable name of this game (e.g. ``'Hnefatafl'``)."""
        return self._get_name()

    @property
    def player_count(self) -> int:
        """Number of players this game requires (e.g. ``2``)."""
        count = self._get_player_count()
        if not isinstance(count, int) or count < 1:
            raise ValueError(
                f"player_count must be a positive int, got {count!r}"
            )
        return count

    # ── Public API (validated wrappers) ─────────────────────────────

    def create_initial_state(self) -> dict:
        """Create and return the starting state of a new game.

        Returns
        -------
        dict
            The full initial game state.  Must be JSON-serializable.

        Raises
        ------
        TypeError
            If the returned state contains non-serializable types.
        """
        state = self._create_initial_state()
        if not isinstance(state, dict):
            raise TypeError(
                f"_create_initial_state must return a dict, "
                f"got {type(state).__name__}"
            )
        self.validate_json_serializable(state, "initial state")
        return state

    def get_current_player(self, state: dict) -> int:
        """Determine whose turn it is.

        Parameters
        ----------
        state : dict
            The current game state.

        Returns
        -------
        int
            Player identifier (e.g. ``1`` or ``2``).
        """
        player = self._get_current_player(state)
        if not isinstance(player, int):
            raise TypeError(
                f"_get_current_player must return an int, "
                f"got {type(player).__name__}: {player!r}"
            )
        return player

    def get_legal_moves(self, state: dict, player: int) -> list:
        """Return every legal move available to *player* in *state*.

        Parameters
        ----------
        state : dict
            The current game state.
        player : int
            The player whose moves to compute.

        Returns
        -------
        list
            Legal moves, each of which is JSON-serializable.  An empty
            list means the player has no moves (the game may be over, or
            the player must pass).

        Raises
        ------
        TypeError
            If any move contains non-serializable types.
        """
        moves = self._get_legal_moves(state, player)
        if not isinstance(moves, list):
            raise TypeError(
                f"_get_legal_moves must return a list, "
                f"got {type(moves).__name__}"
            )
        self.validate_json_serializable(moves, "legal moves")
        return moves

    def apply_move(self, state: dict, player: int, move) -> dict:
        """Validate and apply a move, returning the new game state.

        Enforcement performed automatically:

        1. The incoming *move* is checked for JSON-serializability.
        2. Turn order is verified (*player* must be the current player).
        3. The move must be legal.
        4. The original *state* must not be mutated (checked via JSON
           snapshot comparison).
        5. The returned state must be a new dict and JSON-serializable.

        Parameters
        ----------
        state : dict
            The current game state (must not be mutated).
        player : int
            The player making the move.
        move
            The chosen move (must be JSON-serializable).

        Returns
        -------
        dict
            The new game state after applying the move.

        Raises
        ------
        TypeError
            If the move or resulting state is not JSON-serializable.
        ValueError
            If it is not *player*'s turn or the move is illegal.
        RuntimeError
            If ``_apply_move`` mutated the original state or returned
            the same object.
        """
        # 1. Validate the incoming move
        self.validate_json_serializable(move, "move")

        # 2. Enforce turn order
        current = self.get_current_player(state)
        if player != current:
            raise ValueError(
                f"Not player {player}'s turn (current player: {current})"
            )

        # 3. Enforce move legality
        if not self.is_valid_move(state, player, move):
            raise ValueError(f"Illegal move for player {player}: {move!r}")

        # Snapshot original state for mutation check
        snapshot = json.dumps(state, sort_keys=True)

        # 4. Apply
        new_state = self._apply_move(state, player, move)

        # 5a. Must be a new object
        if new_state is state:
            raise RuntimeError(
                "_apply_move returned the same state object — "
                "it must create and return a new dict"
            )

        # 5b. Original must be untouched
        if json.dumps(state, sort_keys=True) != snapshot:
            raise RuntimeError(
                "_apply_move mutated the original state dict — "
                "use copy.deepcopy or build a fresh dict"
            )

        # 5c. New state must be a serializable dict
        if not isinstance(new_state, dict):
            raise TypeError(
                f"_apply_move must return a dict, "
                f"got {type(new_state).__name__}"
            )
        self.validate_json_serializable(new_state, "state after apply_move")

        return new_state

    def get_game_status(self, state: dict) -> dict:
        """Check whether the game is over and determine the outcome.

        Parameters
        ----------
        state : dict
            The current game state.

        Returns
        -------
        dict
            ``{"is_over": bool, "winner": int | None, "is_draw": bool}``

            Valid combinations::

                {"is_over": False, "winner": None, "is_draw": False}   # ongoing
                {"is_over": True,  "winner": 1,    "is_draw": False}   # player 1 wins
                {"is_over": True,  "winner": None,  "is_draw": True}   # draw
        """
        status = self._get_game_status(state)
        self._validate_status(status)
        return status

    def is_valid_move(self, state: dict, player: int, move) -> bool:
        """Check whether *move* is legal for *player* in *state*.

        The default implementation checks membership in the list returned
        by ``_get_legal_moves``.  Subclasses may override this with a
        cheaper check if full move generation is expensive.

        Parameters
        ----------
        state : dict
            The current game state.
        player : int
            The player identifier.
        move
            The move to validate.

        Returns
        -------
        bool
        """
        return move in self._get_legal_moves(state, player)

    # ── Abstract methods (subclass must implement) ──────────────────

    @abstractmethod
    def _get_name(self) -> str:
        """Return the human-readable name of this game.

        Example: ``"Hnefatafl"`` or ``"YINSH"``.
        """
        ...

    @abstractmethod
    def _get_player_count(self) -> int:
        """Return how many players this game requires.

        Typically ``2`` for abstract strategy games.
        """
        ...

    @abstractmethod
    def _create_initial_state(self) -> dict:
        """Build and return the starting game state.

        The returned dict must contain only JSON-serializable types
        (dict with string keys, list, str, int, float, bool, None).

        It should include everything needed to fully describe the game
        at this point: the board layout, whose turn it is, scores or
        capture counters, phase information for multi-step turns, etc.
        """
        ...

    @abstractmethod
    def _get_current_player(self, state: dict) -> int:
        """Extract the current player from *state*.

        Returns an int identifying the player whose turn it is
        (e.g. ``1`` or ``2``).
        """
        ...

    @abstractmethod
    def _get_legal_moves(self, state: dict, player: int) -> list:
        """Compute all legal moves for *player* in *state*.

        Each move must be JSON-serializable.  For simple games a move
        might be a list like ``[row, col]``.  For multi-step turns it
        might be a dict like ``{"from": [r1, c1], "to": [r2, c2],
        "arrow": [r3, c3]}``.

        Return an empty list if the player has no legal moves.
        """
        ...

    @abstractmethod
    def _apply_move(self, state: dict, player: int, move) -> dict:
        """Apply *move* and return the **new** game state.

        **Do not mutate** the original *state*.  Either
        ``copy.deepcopy(state)`` first, or build a fresh dict.

        *move* has already been validated as legal by the time this
        method is called from the public ``apply_move`` wrapper.
        """
        ...

    @abstractmethod
    def _get_game_status(self, state: dict) -> dict:
        """Return the game-over status for *state*.

        Must return a dict with exactly three keys::

            {"is_over": bool, "winner": int | None, "is_draw": bool}

        See ``get_game_status`` for valid key combinations.
        """
        ...

    # ── Validation & enforcement utilities ──────────────────────────

    @staticmethod
    def validate_json_serializable(data, label: str = "data") -> bool:
        """Validate that *data* contains only JSON-safe Python types.

        Performs two layers of checking:

        1. **Recursive type walk** — only ``dict`` (string keys), ``list``,
           ``str``, ``int``, ``float``, ``bool``, and ``None`` are allowed.
           Gives precise error paths (e.g. ``"state.board[3]"``).
        2. **JSON round-trip** — ``json.dumps`` then ``json.loads``,
           verifying the data survives intact.

        Parameters
        ----------
        data
            The value to validate.
        label : str
            Human-readable context for error messages
            (e.g. ``"initial state"``, ``"legal moves"``).

        Returns
        -------
        bool
            ``True`` if validation passes.

        Raises
        ------
        TypeError
            With a message showing the exact path and type of any
            offending value.
        """
        AbstractBoardGame._check_types(data, path=label)

        # Belt-and-suspenders: actual JSON round-trip
        try:
            serialized = json.dumps(data)
            restored = json.loads(serialized)
        except (TypeError, ValueError, OverflowError) as exc:
            raise TypeError(
                f"{label}: JSON serialization failed: {exc}"
            ) from exc

        if restored != data:
            raise TypeError(
                f"{label}: data changed after JSON round-trip "
                f"(possible float precision issue or hidden type coercion)"
            )

        return True

    @staticmethod
    def _check_types(data, path: str = "root"):
        """Recursively verify every value is a JSON-safe type.

        Allowed: ``dict`` (string keys), ``list``, ``str``, ``int``,
        ``float``, ``bool``, ``None``.

        Gives targeted hints for common mistakes (tuples, sets, numpy
        arrays, enums, bytes).
        """
        if data is None:
            return

        # bool must be checked before int (bool is a subclass of int)
        if isinstance(data, bool):
            return

        if isinstance(data, int):
            return

        if isinstance(data, float):
            if data != data:  # NaN
                raise TypeError(
                    f"At {path}: NaN is not valid JSON"
                )
            if data == float("inf") or data == float("-inf"):
                raise TypeError(
                    f"At {path}: Infinity is not valid JSON"
                )
            return

        if isinstance(data, str):
            return

        if isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"At {path}: dict key must be str, "
                        f"got {type(key).__name__}: {key!r}. "
                        f"Hint: convert to a string key"
                    )
                AbstractBoardGame._check_types(
                    value, f"{path}.{key}"
                )
            return

        if isinstance(data, list):
            for i, item in enumerate(data):
                AbstractBoardGame._check_types(
                    item, f"{path}[{i}]"
                )
            return

        # ── Rejected types with helpful hints ──
        type_name = type(data).__name__
        hints = {
            "tuple": "convert to a list",
            "set": "convert to a sorted list",
            "frozenset": "convert to a sorted list",
            "ndarray": "use .tolist() to convert numpy array to nested lists",
            "bytes": "decode to str or encode as a base64 string",
            "bytearray": "decode to str or encode as a base64 string",
        }
        hint = hints.get(type_name, "")

        # Check for enum instances
        if not hint and hasattr(data, "value"):
            hint = "use .value to get the underlying primitive"

        # Check for numpy scalar types
        if not hint and "numpy" in type(data).__module__ if hasattr(type(data), "__module__") else False:
            hint = "use .item() to convert numpy scalar to a Python builtin"

        msg = f"At {path}: non-serializable type {type_name}: {data!r}"
        if hint:
            msg += f". Hint: {hint}"
        raise TypeError(msg)

    @staticmethod
    def _validate_status(status: dict):
        """Verify a game-status dict has the correct shape and logic."""
        if not isinstance(status, dict):
            raise TypeError(
                f"game status must be a dict, got {type(status).__name__}"
            )

        required = {"is_over", "winner", "is_draw"}
        missing = required - status.keys()
        if missing:
            raise TypeError(f"game status missing required keys: {missing}")

        if not isinstance(status["is_over"], bool):
            raise TypeError(
                f"status['is_over'] must be bool, "
                f"got {type(status['is_over']).__name__}"
            )
        if not isinstance(status["is_draw"], bool):
            raise TypeError(
                f"status['is_draw'] must be bool, "
                f"got {type(status['is_draw']).__name__}"
            )
        if status["winner"] is not None and not isinstance(status["winner"], int):
            raise TypeError(
                f"status['winner'] must be int or None, "
                f"got {type(status['winner']).__name__}"
            )

        # Logical consistency
        if not status["is_over"]:
            if status["winner"] is not None or status["is_draw"]:
                raise ValueError(
                    "Game is not over but 'winner' or 'is_draw' is set"
                )
        else:
            if status["is_draw"] and status["winner"] is not None:
                raise ValueError(
                    "Game is a draw but 'winner' is also set"
                )
            if not status["is_draw"] and status["winner"] is None:
                raise ValueError(
                    "Game is over and not a draw, but no 'winner' is set"
                )

    # ── Testing helper ──────────────────────────────────────────────

    def validate_implementation(self) -> list[str]:
        """Smoke-test a game implementation for contract compliance.

        Creates a game, inspects the initial state, applies the first
        legal move, and checks everything along the way.  Intended to
        be called from a test suite.

        Returns
        -------
        list[str]
            A list of checks that passed (useful for logging).

        Raises
        ------
        TypeError, ValueError, RuntimeError, AssertionError
            If any check fails.
        """
        passed = []

        # Name and player count
        name = self.name
        assert isinstance(name, str) and len(name) > 0, "name must be a non-empty str"
        passed.append(f"name = {name!r}")

        pc = self.player_count
        assert pc >= 1, f"player_count must be >= 1, got {pc}"
        passed.append(f"player_count = {pc}")

        # Initial state
        state = self.create_initial_state()
        passed.append("create_initial_state returned valid JSON-serializable dict")

        # Current player
        player = self.get_current_player(state)
        assert isinstance(player, int), f"current player must be int, got {type(player)}"
        passed.append(f"current player = {player}")

        # Game status at start
        status = self.get_game_status(state)
        assert not status["is_over"], "game should not be over at start"
        passed.append("game is not over at start")

        # Legal moves
        moves = self.get_legal_moves(state, player)
        assert isinstance(moves, list), "legal moves must be a list"
        assert len(moves) > 0, "starting player should have at least one legal move"
        passed.append(f"starting player has {len(moves)} legal move(s)")

        # Apply first move and verify immutability
        snapshot = json.dumps(state, sort_keys=True)
        new_state = self.apply_move(state, player, moves[0])
        assert json.dumps(state, sort_keys=True) == snapshot, (
            "apply_move mutated the original state"
        )
        passed.append("apply_move preserved original state (immutability OK)")
        passed.append("state after move is valid JSON-serializable dict")

        # Game status after first move
        _ = self.get_game_status(new_state)
        passed.append("game status after first move is valid")

        # Verify illegal-move rejection
        try:
            self.apply_move(state, player, "__obviously_invalid_move__")
            passed.append("WARNING: invalid move was not rejected")
        except ValueError:
            passed.append("illegal move correctly rejected")

        # Verify wrong-player rejection (if multiplayer)
        if pc > 1:
            wrong_player = (player % pc) + 1
            try:
                self.apply_move(state, wrong_player, moves[0])
                passed.append("WARNING: wrong-player move was not rejected")
            except ValueError:
                passed.append("wrong-player move correctly rejected")

        return passed
