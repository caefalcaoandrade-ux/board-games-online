"""Board Games Online -- main client application.

Run from the project root::

    python client/main.py                            # local server
    python client/main.py ws://192.168.1.5:8000/ws   # remote server

The application opens a lobby where you can browse available games, create
or join rooms, and play against other connected players.  After each game
you return to the lobby automatically.  Close the window to exit.
"""

import sys
import os

# ── Path setup ────────────────────────────────────────────────────────────
# Ensure the project root is on sys.path so ``client.*`` and ``games.*``
# imports work regardless of the working directory.

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Imports ───────────────────────────────────────────────────────────────

import pygame
from client.lobby import run_lobby, launch_game

# ── Constants ─────────────────────────────────────────────────────────────

DEFAULT_SERVER = "ws://localhost:8000/ws"


# ── Main loop ─────────────────────────────────────────────────────────────

def main():
    server_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVER

    print()
    print("  Board Games Online")
    print(f"  Server:  {server_url}")
    if server_url == DEFAULT_SERVER:
        print("  Tip:     python client/main.py ws://host:port/ws  to connect elsewhere")
    print()

    try:
        while True:
            # ── Lobby ─────────────────────────────────────────────────
            # run_lobby initialises Pygame, shows the lobby screen, and
            # blocks until either a game starts or the user closes the
            # window.  On game-start it returns the server's
            # ``game_started`` message and the live NetworkClient.  On
            # window-close it returns (None, None) and calls pygame.quit().

            game_msg, net = run_lobby(server_url)

            if game_msg is None:
                # User closed the lobby window — exit cleanly.
                break

            # ── Game ──────────────────────────────────────────────────
            # launch_game dispatches to the correct display module's
            # run_online() based on game_msg["game"].  Each run_online
            # resizes the window, runs its own event loop, and returns
            # when the game ends or the user presses Esc / closes the
            # window.  launch_game then disconnects the network client.
            # Pygame stays initialised throughout so we can loop back
            # to the lobby.

            launch_game(game_msg, net)

            # ── Back to lobby ─────────────────────────────────────────
            # If Pygame was shut down (should not happen — none of the
            # run_online functions call pygame.quit) bail out instead
            # of looping into a broken state.

            if not pygame.get_init():
                break

    except KeyboardInterrupt:
        pass
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
