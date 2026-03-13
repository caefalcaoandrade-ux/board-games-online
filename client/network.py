"""Client-side networking module for WebSocket communication with the game server.

Runs the WebSocket listener in a background thread so the Pygame main loop
stays responsive.  Incoming messages are placed in a thread-safe queue that
the Pygame code drains each frame via ``poll_messages()``.

Typical usage inside a Pygame display module::

    from client.network import NetworkClient

    net = NetworkClient("ws://localhost:8000/ws")
    net.connect()
    net.create_room("Bashni")

    # In the game loop:
    for msg in net.poll_messages():
        handle(msg)

    # On player action:
    net.send_move(move_dict)

    # On shutdown:
    net.disconnect()
"""

import json
import queue
import threading

import websocket  # websocket-client package


class NetworkClient:
    """Non-blocking WebSocket client for the board-game server.

    All server messages are placed in an internal ``queue.Queue``.
    Call ``poll_messages()`` every frame to retrieve them.
    """

    def __init__(self, url: str):
        self.url = url
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue = queue.Queue()
        self._connected = False
        self._error: str | None = None
        self._room_code: str | None = None
        self._player_id: int | None = None

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """True while the WebSocket connection is open."""
        return self._connected

    @property
    def error(self) -> str | None:
        """Last connection error message, or None."""
        return self._error

    @property
    def room_code(self) -> str | None:
        """Room code assigned after create/join, or None."""
        return self._room_code

    @property
    def player_id(self) -> int | None:
        """Player ID assigned by the server, or None."""
        return self._player_id

    # ── Connection lifecycle ──────────────────────────────────────────────

    def connect(self):
        """Open the WebSocket and start the background listener thread."""
        if self._connected:
            return

        self._error = None
        self._ws = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            daemon=True,
        )
        self._thread.start()

    def disconnect(self):
        """Cleanly close the WebSocket connection."""
        if self._ws is not None:
            self._ws.close()
        self._connected = False

    # ── Sending messages ──────────────────────────────────────────────────

    def _send(self, msg: dict):
        """Serialize and send a JSON message to the server."""
        if not self._connected or self._ws is None:
            self._queue.put({
                "type": "error",
                "message": "Not connected to the server.",
            })
            return
        try:
            self._ws.send(json.dumps(msg))
        except Exception as exc:
            self._error = str(exc)
            self._queue.put({
                "type": "error",
                "message": f"Send failed: {exc}",
            })

    def create_room(self, game_name: str):
        """Ask the server to create a new room for *game_name*."""
        self._send({"type": "create_room", "game": game_name})

    def join_room(self, code: str):
        """Ask the server to join the room with the given code."""
        self._send({"type": "join_room", "code": code})

    def rejoin_room(self, code: str, player: int):
        """Attempt to rejoin a room after a disconnect."""
        self._send({"type": "rejoin_room", "code": code, "player": player})

    def send_move(self, move):
        """Send a move to the server."""
        self._send({"type": "make_move", "move": move})

    # ── Polling (called each Pygame frame) ────────────────────────────────

    def poll_messages(self) -> list[dict]:
        """Return all messages received since the last call.

        Never blocks.  Returns an empty list if there are no new messages.
        """
        msgs = []
        while True:
            try:
                msgs.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    # ── WebSocketApp callbacks (run in background thread) ─────────────────

    def _on_open(self, ws):
        self._connected = True
        self._error = None

    def _on_message(self, ws, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Track room code and player ID locally
        msg_type = msg.get("type")
        if msg_type == "room_created":
            self._room_code = msg.get("code")
            self._player_id = 1
        elif msg_type == "room_joined":
            self._room_code = msg.get("code")
            self._player_id = msg.get("your_player")
        elif msg_type == "room_rejoined":
            self._room_code = msg.get("code")
            self._player_id = msg.get("your_player")

        self._queue.put(msg)

    def _on_error(self, ws, exc):
        self._error = str(exc)
        self._connected = False
        self._queue.put({
            "type": "connection_error",
            "message": str(exc),
        })

    def _on_close(self, ws, close_status_code, close_msg):
        was_connected = self._connected
        self._connected = False
        if was_connected:
            self._queue.put({
                "type": "connection_closed",
                "message": "Connection to server lost.",
            })
