"""Single-player vs bot — local game using the MCTS bot.

Provides a ``BotNetAdapter`` that mimics the ``NetworkClient`` API so
each game's existing ``run_online`` function works unchanged.  The
adapter intercepts ``send_move`` calls, applies the human's move
locally, then runs the bot in a background thread and returns its
response as a ``move_made`` (or ``game_over``) message via
``poll_messages()``.

Usage::

    from client.bot_game import run_vs_bot
    run_vs_bot(screen, "Havannah", "strong")
"""

import sys
import os
import threading
import time

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from games import create_game
from client.bot import MCTSBot
from client.claude_bot import ClaudeBot


class BotNetAdapter:
    """Mimics ``NetworkClient`` for local bot play.

    The human's ``run_online`` display module talks to this object
    exactly as it would talk to a real network client.  Moves are
    applied locally and the bot computes its responses in a background
    thread so the Pygame window stays responsive.
    """

    def __init__(self, logic, bot, human_player):
        self.logic = logic
        self.bot = bot
        self.human_player = human_player
        self.bot_player = 3 - human_player  # assumes 2-player games
        self.state = logic.create_initial_state()
        self._queue = []
        self._thinking = False
        self._bot_result = {}
        self._move_time = time.monotonic()
        self._min_delay = 0.5  # seconds before bot move appears
        self._fallback_notified = False

        # If bot goes first, start thinking immediately
        self._maybe_start_bot()

    # ── NetworkClient-compatible API ─────────────────────────────────

    def send_move(self, move):
        """Human made a move — apply it, then start bot if needed."""
        player = self.logic.get_current_player(self.state)
        self.state = self.logic.apply_move(self.state, player, move)
        status = self.logic.get_game_status(self.state)

        if status["is_over"]:
            self._queue.append({
                "type": "game_over",
                "state": self.state,
                "winner": status["winner"],
                "is_draw": status["is_draw"],
            })
            return

        # Broadcast human's move so the display updates
        self._queue.append({
            "type": "move_made",
            "state": self.state,
        })

        self._move_time = time.monotonic()
        self._maybe_start_bot()

    def poll_messages(self):
        """Return pending messages — including bot moves once ready."""
        msgs = list(self._queue)
        self._queue.clear()

        # Detect Claude->MCTS fallback swap and notify display once
        if (not self._fallback_notified
                and hasattr(self.bot, "switched_to_fallback")
                and self.bot.switched_to_fallback):
            self._fallback_notified = True
            msgs.append({
                "type": "error",
                "message": "AI unavailable \u2014 switching to Strong bot",
            })

        # Check if bot finished thinking
        if self._thinking and "move" in self._bot_result:
            elapsed = time.monotonic() - self._move_time
            if elapsed >= self._min_delay:
                self._thinking = False
                bot_move = self._bot_result["move"]
                if bot_move is not None:
                    player = self.logic.get_current_player(self.state)
                    self.state = self.logic.apply_move(
                        self.state, player, bot_move)
                    status = self.logic.get_game_status(self.state)
                    if status["is_over"]:
                        msgs.append({
                            "type": "game_over",
                            "state": self.state,
                            "winner": status["winner"],
                            "is_draw": status["is_draw"],
                        })
                    else:
                        msgs.append({
                            "type": "move_made",
                            "state": self.state,
                        })
                        # After bot moves, it might be bot's turn again
                        # (multi-step games like Arimaa)
                        self._move_time = time.monotonic()
                        self._maybe_start_bot()

        return msgs

    def disconnect(self):
        """No-op — no network to disconnect."""
        pass

    @property
    def connected(self):
        return True

    @property
    def is_bot_thinking(self):
        """True while the bot is computing its move."""
        return self._thinking

    # ── Internal ─────────────────────────────────────────────────────

    def _maybe_start_bot(self):
        """If it's the bot's turn and game isn't over, start thinking."""
        status = self.logic.get_game_status(self.state)
        if status["is_over"]:
            return
        current = self.logic.get_current_player(self.state)
        if current == self.bot_player and not self._thinking:
            self._thinking = True
            self._bot_result = {}
            state_snapshot = self.state
            bot_ref = self.bot
            bot_player = self.bot_player
            logic_ref = self.logic

            def _think():
                move = bot_ref.choose_move(
                    logic_ref, state_snapshot, bot_player)
                self._bot_result["move"] = move

            threading.Thread(target=_think, daemon=True).start()


# ── Public API ────────────────────────────────────────────────────────────────


def run_vs_bot(screen, game_name, difficulty):
    """Launch a single-player game against a bot.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized by the game).
    game_name : str
        Name of the game (must be in the registry).
    difficulty : str
        "weak", "average", "strong", or "claude".

    Returns when the game ends or the user closes the window.
    """
    # Lazy import to avoid circular dependencies
    from client.lobby import _load_dispatch, _ONLINE_DISPATCH

    logic = create_game(game_name)
    if difficulty == "claude":
        bot = ClaudeBot()
    else:
        bot = MCTSBot(difficulty)
    human_player = 1  # human is always player 1

    adapter = BotNetAdapter(logic, bot, human_player)
    initial_state = adapter.state

    # Load the game's online display function
    _load_dispatch()
    run_fn = _ONLINE_DISPATCH.get(game_name)

    if run_fn is not None:
        run_fn(screen, adapter, human_player, initial_state)
    else:
        # Fallback — shouldn't happen if registry matches dispatch
        import pygame
        font = pygame.font.SysFont("arial", 22)
        screen.fill((34, 32, 36))
        msg = font.render(f"{game_name} display not available", True,
                          (215, 215, 215))
        screen.blit(msg, (screen.get_width() // 2 - msg.get_width() // 2,
                          screen.get_height() // 2))
        pygame.display.flip()
        waiting = True
        while waiting:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    waiting = False
            pygame.time.wait(50)

    adapter.disconnect()
