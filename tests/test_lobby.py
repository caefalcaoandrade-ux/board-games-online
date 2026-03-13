"""Smoke-test the lobby module: imports, constants, and the helper function."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from client.lobby import (
    run_lobby, _draw_button, launch_game, _load_dispatch, _ONLINE_DISPATCH,
    PH_PICK, PH_WAITING,
    WIN_W, WIN_H,
)
from games import list_games

import pygame


def test_constants():
    assert WIN_W > 0 and WIN_H > 0
    assert PH_PICK == 0
    assert PH_WAITING == 1


def test_game_list_populated():
    games = list_games()
    assert len(games) >= 9
    assert "Bashni" in games
    assert "Shobu" in games


def test_draw_button():
    pygame.init()
    screen = pygame.display.set_mode((200, 100))
    font = pygame.font.SysFont("arial", 16)
    rect = pygame.Rect(10, 10, 100, 30)

    # Not clicked
    result = _draw_button(screen, font, "Test", rect, 50, 25, False)
    assert result is False

    # Clicked inside
    result = _draw_button(screen, font, "Test", rect, 50, 25, True)
    assert result is True

    # Clicked outside
    result = _draw_button(screen, font, "Test", rect, 180, 80, True)
    assert result is False

    # Disabled
    result = _draw_button(screen, font, "Test", rect, 50, 25, True, enabled=False)
    assert result is False

    pygame.quit()


def test_dispatch_loads_hnefatafl():
    """_load_dispatch should register Hnefatafl's run_online."""
    _ONLINE_DISPATCH.clear()
    _load_dispatch()
    assert "Hnefatafl" in _ONLINE_DISPATCH
    from games.hnefatafl_display import run_online
    assert _ONLINE_DISPATCH["Hnefatafl"] is run_online


def test_dispatch_idempotent():
    """Calling _load_dispatch twice should not error or duplicate entries."""
    _ONLINE_DISPATCH.clear()
    _load_dispatch()
    _load_dispatch()
    assert len(_ONLINE_DISPATCH) >= 1


def test_launch_game_calls_run_online(monkeypatch):
    """launch_game should dispatch to the game's run_online function."""
    pygame.init()
    screen = pygame.display.set_mode((200, 100))

    called_with = {}

    def fake_run_online(scr, net, my_player, state):
        called_with["screen"] = scr
        called_with["net"] = net
        called_with["my_player"] = my_player
        called_with["state"] = state

    _ONLINE_DISPATCH.clear()
    _ONLINE_DISPATCH["Hnefatafl"] = fake_run_online

    class FakeNet:
        def disconnect(self):
            self.disconnected = True

    fake_net = FakeNet()
    game_msg = {
        "game": "Hnefatafl",
        "your_player": 1,
        "state": {"board": [], "turn": 1},
    }

    launch_game(game_msg, fake_net)

    assert called_with["my_player"] == 1
    assert called_with["state"] == {"board": [], "turn": 1}
    assert called_with["net"] is fake_net
    assert fake_net.disconnected is True
    pygame.quit()


def test_launch_game_unsupported_game():
    """launch_game with an unregistered game should not crash."""
    pygame.init()
    screen = pygame.display.set_mode((200, 100))

    _ONLINE_DISPATCH.clear()
    _load_dispatch()

    class FakeNet:
        def disconnect(self):
            self.disconnected = True

    fake_net = FakeNet()
    game_msg = {
        "game": "UnknownGame",
        "your_player": 1,
        "state": {},
    }

    # Monkeypatch pygame.event.get to immediately return QUIT
    original_get = pygame.event.get
    quit_sent = [False]

    def fake_event_get():
        if not quit_sent[0]:
            quit_sent[0] = True
            quit_event = pygame.event.Event(pygame.QUIT)
            return [quit_event]
        return []

    pygame.event.get = fake_event_get
    try:
        launch_game(game_msg, fake_net)
    finally:
        pygame.event.get = original_get

    assert fake_net.disconnected is True
    pygame.quit()


if __name__ == "__main__":
    PASS = FAIL = 0
    for fn in [test_constants, test_game_list_populated, test_draw_button,
               test_dispatch_loads_hnefatafl, test_dispatch_idempotent]:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            PASS += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            FAIL += 1
    print(f"\n{PASS + FAIL} tests: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
