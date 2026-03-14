"""Self-hosted server with ngrok tunnel for Board Games Online.

Starts the FastAPI game server in a background thread and opens an ngrok
tunnel so remote players can connect.  No terminal or separate process
needed -- everything runs inside the application.

Usage::

    from client.host import start_hosting, stop_hosting, save_authtoken, needs_authtoken

    if needs_authtoken():
        save_authtoken(token_from_user)

    url = start_hosting()       # returns "wss://xxxx.ngrok-free.app/ws"
    # ... play the game ...
    stop_hosting()               # clean shutdown
"""

import os
import sys
import threading

# ── Path setup ───────────────────────────────────────────────────────────
_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Module state ─────────────────────────────────────────────────────────

_server_thread: threading.Thread | None = None
_server_instance = None          # uvicorn.Server
_tunnel = None                   # ngrok tunnel object
_public_url: str | None = None

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000


# ── Authtoken management ────────────────────────────────────────────────


def needs_authtoken() -> bool:
    """Return True if no ngrok authtoken is configured."""
    try:
        from pyngrok import conf
        cfg = conf.get_default()
        return not cfg.auth_token
    except Exception:
        return True


def save_authtoken(token: str):
    """Save an ngrok authtoken so it persists across sessions."""
    from pyngrok import ngrok, conf
    ngrok.set_auth_token(token)
    # Also update the in-memory config so needs_authtoken() sees it
    # immediately without needing to re-read from disk.
    conf.get_default().auth_token = token


# ── Server ───────────────────────────────────────────────────────────────


def _run_server():
    """Run the uvicorn server (blocking -- call in a thread)."""
    import uvicorn
    from server.main import app

    global _server_instance
    config = uvicorn.Config(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="warning",
    )
    _server_instance = uvicorn.Server(config)
    _server_instance.run()


# ── Public API ───────────────────────────────────────────────────────────


def start_hosting() -> str:
    """Start the server + ngrok tunnel and return the public wss:// URL.

    Raises
    ------
    RuntimeError
        If the ngrok authtoken is missing or the tunnel fails to open.
    """
    global _server_thread, _tunnel, _public_url

    if _public_url is not None:
        return _public_url  # already hosting

    # 1. Start the FastAPI server in a background daemon thread
    _server_thread = threading.Thread(target=_run_server, daemon=True)
    _server_thread.start()

    # Wait for the server to bind the port
    import time
    import socket
    for _ in range(50):
        try:
            with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)

    # 2. Open the ngrok tunnel
    from pyngrok import ngrok, conf
    from pyngrok.exception import PyngrokNgrokError

    if needs_authtoken():
        raise RuntimeError(
            "ngrok authtoken not configured. "
            "Call save_authtoken(token) first."
        )

    # Kill any stale ngrok process from a previous crashed session
    # to prevent ERR_NGROK_334 (tunnel limit exceeded).
    try:
        ngrok.kill()
    except Exception:
        pass

    try:
        _tunnel = ngrok.connect(SERVER_PORT, "http")
    except PyngrokNgrokError as exc:
        raise RuntimeError(f"Failed to open ngrok tunnel: {exc}") from exc

    # Convert the http(s) URL to a wss:// WebSocket URL
    raw_url = _tunnel.public_url  # e.g. "https://xxxx.ngrok-free.app"
    if raw_url.startswith("https://"):
        ws_url = "wss://" + raw_url[len("https://"):] + "/ws"
    elif raw_url.startswith("http://"):
        ws_url = "ws://" + raw_url[len("http://"):] + "/ws"
    else:
        ws_url = raw_url + "/ws"

    _public_url = ws_url
    return ws_url


def get_public_url() -> str | None:
    """Return the current public URL, or None if not hosting."""
    return _public_url


def get_local_url() -> str:
    """Return the local WebSocket URL for the host to connect to."""
    return f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"


def stop_hosting():
    """Shut down the ngrok tunnel and the server."""
    global _server_thread, _server_instance, _tunnel, _public_url

    # Close the ngrok tunnel
    if _tunnel is not None:
        try:
            from pyngrok import ngrok
            ngrok.disconnect(_tunnel.public_url)
            ngrok.kill()
        except Exception:
            pass
        _tunnel = None

    # Signal the uvicorn server to shut down
    if _server_instance is not None:
        _server_instance.should_exit = True
        _server_instance = None

    # The daemon thread will exit when the process exits or when
    # uvicorn's event loop sees should_exit.  We don't join it
    # because it's a daemon thread.
    _server_thread = None
    _public_url = None
