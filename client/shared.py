"""Shared utilities for online display modules.

Provides state history browsing, board orientation toggle, a command
panel overlay, and a shared input handler.  Each game's display module
imports what it needs and wires these into its own event loop and
render path.

Typical usage inside a game's ``run_online``::

    from client.shared import History, Orientation, draw_command_panel, handle_shared_input

    hist = History()
    orient = Orientation()

    # When server sends a new state:
    hist.push(new_state)

    # In the event loop:
    result = handle_shared_input(event, hist, orient)
    if result == "quit":
        running = False
    elif result == "input_blocked":
        continue  # viewing history — ignore click
    elif result is None:
        ...  # game handles the event normally

    # Decide which state to render:
    render_state = hist.current()

    # Coordinate flip:
    if orient.flipped:
        # game-specific coordinate inversion
        ...

    # After drawing the board:
    draw_command_panel(screen, hist, is_my_turn)
"""

import pygame


# ── State History ────────────────────────────────────────────────────────────


class History:
    """Ordered list of game states with back/forward navigation."""

    def __init__(self):
        self._states: list = []
        self._pos: int = -1  # index into _states; -1 means empty

    def push(self, state):
        """Append a new state and jump to live."""
        self._states.append(state)
        self._pos = len(self._states) - 1

    def back(self):
        """Move one step into the past (no-op at the beginning)."""
        if self._pos > 0:
            self._pos -= 1

    def forward(self):
        """Move one step toward live (no-op when already live)."""
        if self._pos < len(self._states) - 1:
            self._pos += 1

    def jump_to_live(self):
        """Jump to the most recent state."""
        if self._states:
            self._pos = len(self._states) - 1

    def current(self):
        """Return the state that should be rendered, or None if empty."""
        if 0 <= self._pos < len(self._states):
            return self._states[self._pos]
        return None

    @property
    def is_live(self) -> bool:
        """True when viewing the most recent state."""
        return self._pos == len(self._states) - 1

    @property
    def position_str(self) -> str:
        """Human-readable position like 'Move 3 / 8'."""
        if not self._states:
            return ""
        return f"Move {self._pos + 1} / {len(self._states)}"


# ── Board Orientation ────────────────────────────────────────────────────────


class Orientation:
    """Simple toggle for board flip."""

    def __init__(self):
        self.flipped: bool = False

    def toggle(self):
        self.flipped = not self.flipped


# ── Command Panel Renderer ───────────────────────────────────────────────────

_font_cache: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    global _font_cache
    if _font_cache is None:
        _font_cache = pygame.font.SysFont("consolas,monospace", 13)
    return _font_cache


def draw_command_panel(surface: pygame.Surface, hist: History,
                       is_my_turn: bool = True):
    """Draw a small semi-transparent command reference in the bottom-right."""
    font = _get_font()
    pad_x, pad_y = 10, 6
    line_h = 17
    fg = (180, 180, 180)
    fg_dim = (120, 120, 120)

    lines: list[tuple[str, tuple]] = []
    lines.append(("F: Flip  \u2190\u2192: History  Esc: Live  Q: Quit", fg_dim))
    if not hist.is_live:
        lines.append((hist.position_str, fg))
    if not is_my_turn and hist.is_live:
        lines.append(("Waiting for opponent", fg_dim))

    # Measure
    max_w = 0
    rendered = []
    for text, color in lines:
        surf = font.render(text, True, color)
        rendered.append(surf)
        max_w = max(max_w, surf.get_width())

    panel_w = max_w + pad_x * 2
    panel_h = len(rendered) * line_h + pad_y * 2
    win_w, win_h = surface.get_size()
    px = win_w - panel_w - 8
    py = win_h - panel_h - 8

    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 100))
    surface.blit(bg, (px, py))

    for i, surf in enumerate(rendered):
        surface.blit(surf, (px + pad_x, py + pad_y + i * line_h))


# ── Shared Input Handler ────────────────────────────────────────────────────


def handle_shared_input(event: pygame.event.Event, hist: History,
                        orient: Orientation) -> str | None:
    """Process shared keyboard/mouse commands.

    Returns
    -------
    ``"quit"``
        The user pressed Q or closed the window — caller should exit.
    ``"input_blocked"``
        A mouse click occurred while viewing history — caller should
        skip game-specific click handling.
    ``None``
        The event is not a shared command — caller should handle it
        normally (game-specific logic).
    """
    if event.type == pygame.QUIT:
        return "quit"

    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_q:
            return "quit"
        if event.key == pygame.K_f:
            orient.toggle()
            return "handled"
        if event.key == pygame.K_LEFT:
            hist.back()
            return "handled"
        if event.key == pygame.K_RIGHT:
            hist.forward()
            return "handled"
        if event.key == pygame.K_ESCAPE:
            hist.jump_to_live()
            return "handled"

    # Block clicks while reviewing history
    if (event.type == pygame.MOUSEBUTTONDOWN and not hist.is_live):
        return "input_blocked"

    return None
