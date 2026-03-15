"""
Amazons — Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls: Left-click to select/move/shoot. Right-click or U to undo move.
          R to restart.  Esc to quit.
"""

import copy
import sys
try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.amazons_logic import (
        AmazonsLogic, BOARD_N, EMPTY, WHITE, BLACK, BLOCKED,
    )
except ImportError:
    from amazons_logic import (
        AmazonsLogic, BOARD_N, EMPTY, WHITE, BLACK, BLOCKED,
    )

# ── Display Constants ────────────────────────────────────────────────────────

CELL = 68
MARGIN = 30
TOP_M = 46
BOARD_PX = BOARD_N * CELL
STATUS_H = 56
WIN_W = BOARD_PX + 2 * MARGIN
WIN_H = BOARD_PX + TOP_M + MARGIN + STATUS_H
BX = MARGIN
BY = TOP_M

PH_SELECT, PH_MOVE, PH_ARROW = 0, 1, 2
FILES = "abcdefghij"

# ── Palette ──────────────────────────────────────────────────────────────────

C_BG          = ( 38,  36,  33)
C_LIGHT_SQ    = (238, 216, 180)
C_DARK_SQ     = (181, 137, 100)
C_COORD       = (170, 165, 155)
C_BLOCKED_DOT = ( 82,  78,  72)
C_SEL_SQ      = ( 80, 165,  85, 110)
C_SRC_SQ      = (200, 205, 100,  65)
C_LAST_SQ     = (200, 205, 100,  55)
C_MOVE_DOT    = ( 80, 160,  85)
C_ARROW_DOT   = (205,  72,  72)
C_ARROW_RING  = (175,  55,  55)
C_LAST_ARROW  = (190,  65,  65)
C_WHITE_FILL  = (255, 252, 237)
C_WHITE_OUT   = ( 55,  55,  55)
C_BLACK_FILL  = ( 32,  32,  32)
C_BLACK_OUT   = (185, 185, 185)
C_STATUS_TXT  = (195, 192, 185)
C_WIN_TXT     = (255, 215,  50)
C_HINT_TXT    = (105, 102,  96)
C_HOVER       = (255, 255, 255,  30)


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller with three-phase UI interaction.

    Wraps AmazonsLogic and maintains local UI state (selection, phase,
    targets, highlights) that the Renderer reads each frame.  The
    authoritative game state is only updated when a complete move
    (amazon move + arrow) is committed through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = AmazonsLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.undo_stack = []
        self.reset()

    # ── Setup ─────────────────────────────────────────────────────────────

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._status = self.logic.get_game_status(self.state)
        self._sync_board()
        self._cancel()
        self.last_src = None
        self.last_dst = None
        self.last_arrow = None
        self.undo_stack = []
        self._game_over_message = None

    def _sync_board(self):
        """Copy the authoritative board for mutable display use."""
        self.board = [row[:] for row in self.state["board"]]

    def _cancel(self):
        self.sel = None
        self.move_src = None
        self.move_dst = None
        self.targets = []
        self.phase = PH_SELECT

    # ── Online mode helpers ────────────────────────────────────────────

    @property
    def is_my_turn(self):
        """In online mode, True only when it's this player's turn."""
        if not self.online:
            return True
        return self.turn == self.my_player

    def load_state(self, state):
        """Replace the authoritative state from the server."""
        self.state = state
        self._status = self.logic.get_game_status(self.state)
        self._sync_board()
        self._cancel()
        self.last_src = None
        self.last_dst = None
        self.last_arrow = None
        self._game_over_message = None
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            wn = "White" if winner == WHITE else "Black"
            self._game_over_message = f"{wn} wins by forfeit!"
        else:
            self._game_over_message = None

    # ── Properties (read by Renderer) ─────────────────────────────────────

    @property
    def turn(self):
        return self.state["turn"]

    @property
    def move_num(self):
        return self.state["move_num"]

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    # ── Click handling ────────────────────────────────────────────────────

    def click(self, row, col):
        """Handle a click on board cell (row, col).

        In online mode, returns the complete move (all 3 phases) to send
        to the server instead of applying it locally.  Returns None
        otherwise, or when the move is incomplete / not the player's turn.
        """
        if self.game_over or not (0 <= row < BOARD_N and 0 <= col < BOARD_N):
            return None
        if self.online and not self.is_my_turn:
            return None

        if self.phase == PH_SELECT:
            if self.board[row][col] == self.turn:
                valid = AmazonsLogic.amazon_destinations(self.board, row, col)
                if valid:
                    self.sel = (row, col)
                    self.targets = valid
                    self.phase = PH_MOVE
            return None

        elif self.phase == PH_MOVE:
            # click same amazon → deselect
            if (row, col) == self.sel:
                self._cancel()
                return None
            # click another friendly amazon → re-select
            if self.board[row][col] == self.turn:
                self._cancel()
                self.click(row, col)
                return None
            # click a valid destination → move amazon visually
            if (row, col) in self.targets:
                sr, sc = self.sel
                self.board[sr][sc] = EMPTY
                self.board[row][col] = self.turn
                self.move_src = (sr, sc)
                self.move_dst = (row, col)
                self.targets = AmazonsLogic.queen_reach(self.board, row, col)
                self.phase = PH_ARROW
            return None

        elif self.phase == PH_ARROW:
            if (row, col) in self.targets:
                # Build the complete move
                move = [
                    [self.move_src[0], self.move_src[1]],
                    [self.move_dst[0], self.move_dst[1]],
                    [row, col],
                ]
                if self.online:
                    # Don't apply locally — send to server
                    self._sync_board()
                    self._cancel()
                    return move
                # Local mode: apply immediately
                self.undo_stack.append(copy.deepcopy(self.state))
                self.state = self.logic.apply_move(
                    self.state, self.state["turn"], move
                )
                self._status = self.logic.get_game_status(self.state)
                self._sync_board()
                # Record highlights
                self.last_src = self.move_src
                self.last_dst = self.move_dst
                self.last_arrow = (row, col)
                self._cancel()
            return None
        return None

    def undo_move(self):
        """During arrow phase, put the amazon back (restore from state)."""
        if self.online:
            return
        if self.phase == PH_ARROW and self.move_src and self.move_dst:
            self._sync_board()
            self._cancel()

    @staticmethod
    def notation(r, c):
        return f"{FILES[c]}{BOARD_N - r}"


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state."""

    def __init__(self, state, game):
        self.board = [row[:] for row in state["board"]]
        self.turn = state["turn"]
        self.move_num = state["move_num"]
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.sel = None
        self.move_src = None
        self.move_dst = None
        self.targets = []
        self.phase = PH_SELECT
        self.last_src = None
        self.last_dst = None
        self.last_arrow = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]


# ── Rendering ────────────────────────────────────────────────────────────────


def _make_piece_surfaces(font):
    """Pre-render white and black queen surfaces with outlines."""
    def outlined(char, fill, outline):
        base = font.render(char, True, fill)
        edge = font.render(char, True, outline)
        w, h = base.get_width() + 4, base.get_height() + 4
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    surf.blit(edge, (2 + dx, 2 + dy))
        surf.blit(base, (2, 2))
        return surf

    glyph = "\u265B"  # ♛
    w_surf = outlined(glyph, C_WHITE_FILL, C_WHITE_OUT)
    b_surf = outlined(glyph, C_BLACK_FILL, C_BLACK_OUT)
    return w_surf, b_surf


def _make_fallback_pieces():
    """Circle-based fallback if Unicode queen doesn't render."""
    radius = CELL // 3
    size = radius * 2 + 6
    surfaces = []
    for fill, outline in [(C_WHITE_FILL, C_WHITE_OUT), (C_BLACK_FILL, C_BLACK_OUT)]:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        pygame.draw.circle(s, fill, (cx, cy), radius)
        pygame.draw.circle(s, outline, (cx, cy), radius, 2)
        # small crown ticks
        for angle_x in (-0.6, 0, 0.6):
            tx = int(cx + angle_x * radius)
            ty = cy - radius + 2
            pygame.draw.line(s, outline, (tx, cy - radius // 2), (tx, ty - 5), 2)
            pygame.draw.circle(s, fill, (tx, ty - 5), 3)
            pygame.draw.circle(s, outline, (tx, ty - 5), 3, 1)
        surfaces.append(s)
    return surfaces[0], surfaces[1]


class Renderer:
    """Handles all drawing to screen."""

    def __init__(self, screen):
        self.screen = screen
        self.flipped = False
        self.coord_font = pygame.font.SysFont("monospace", 14)
        self.status_font = pygame.font.SysFont("sans-serif", 18, bold=True)
        self.hint_font = pygame.font.SysFont("monospace", 13)

        # attempt Unicode queen
        pfont_size = max(12, int(CELL * 0.72))
        for family in ["DejaVu Sans", "Noto Sans Symbols2", "Segoe UI Symbol",
                        "Apple Symbols", "Arial Unicode MS", None]:
            pfont = pygame.font.SysFont(family, pfont_size)
            test = pfont.render("\u265B", True, (0, 0, 0))
            if test.get_width() > pfont_size * 0.25:
                self.w_piece, self.b_piece = _make_piece_surfaces(pfont)
                self._unicode = True
                break
        else:
            self.w_piece, self.b_piece = _make_fallback_pieces()
            self._unicode = False

        self._hl = pygame.Surface((CELL, CELL), pygame.SRCALPHA)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _sq_px(self, r, c):
        """Top-left pixel of square (r, c), accounting for flip."""
        if self.flipped:
            return BX + (BOARD_N - 1 - c) * CELL, BY + (BOARD_N - 1 - r) * CELL
        return BX + c * CELL, BY + r * CELL

    def _sq_center(self, r, c):
        x, y = self._sq_px(r, c)
        return x + CELL // 2, y + CELL // 2

    def pixel_to_cell(self, mx, my):
        """Convert pixel position to board (r, c), or None."""
        bx = mx - BX
        by = my - BY
        if bx < 0 or by < 0 or bx >= BOARD_PX or by >= BOARD_PX:
            return None
        gc = bx // CELL
        gr = by // CELL
        if self.flipped:
            return BOARD_N - 1 - gr, BOARD_N - 1 - gc
        return gr, gc

    def _fill_sq(self, r, c, rgba):
        self._hl.fill(rgba)
        self.screen.blit(self._hl, self._sq_px(r, c))

    # ── Main draw ────────────────────────────────────────────────────────

    def draw(self, game, mouse_pos):
        scr = self.screen
        scr.fill(C_BG)

        # board outline
        pygame.draw.rect(scr, (60, 58, 55),
                         (BX - 2, BY - 2, BOARD_PX + 4, BOARD_PX + 4), 2)

        # squares
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                color = C_LIGHT_SQ if (r + c) % 2 == 0 else C_DARK_SQ
                pygame.draw.rect(scr, color, (*self._sq_px(r, c), CELL, CELL))

        # ── Highlights ───────────────────────────────────────────────────

        # last-move highlight (only visible when back to select phase)
        if game.last_src and game.phase == PH_SELECT:
            for pos in (game.last_src, game.last_dst):
                self._fill_sq(*pos, C_LAST_SQ)

        # selected amazon
        if game.sel and game.phase == PH_MOVE:
            self._fill_sq(*game.sel, C_SEL_SQ)

        # moved amazon & source trail during arrow phase
        if game.move_dst and game.phase == PH_ARROW:
            self._fill_sq(*game.move_dst, C_SEL_SQ)
            if game.move_src:
                self._fill_sq(*game.move_src, C_SRC_SQ)

        # hover highlight
        if mouse_pos and not game.game_over:
            cell = self.pixel_to_cell(*mouse_pos)
            if cell and cell in game.targets:
                self._fill_sq(*cell, C_HOVER)

        # valid-target dots
        for tr, tc in game.targets:
            cx, cy = self._sq_center(tr, tc)
            if game.phase == PH_ARROW:
                pygame.draw.circle(scr, C_ARROW_DOT, (cx, cy), 9)
                pygame.draw.circle(scr, C_ARROW_RING, (cx, cy), 9, 2)
            else:
                pygame.draw.circle(scr, C_MOVE_DOT, (cx, cy), 9)

        # ── Pieces & blocked squares ─────────────────────────────────────

        for r in range(BOARD_N):
            for c in range(BOARD_N):
                cx, cy = self._sq_center(r, c)
                v = game.board[r][c]
                if v == BLOCKED:
                    pygame.draw.circle(scr, C_BLOCKED_DOT, (cx, cy), CELL // 5)
                    if game.last_arrow == (r, c) and game.phase == PH_SELECT:
                        pygame.draw.circle(scr, C_LAST_ARROW, (cx, cy),
                                           CELL // 5 + 3, 2)
                elif v == WHITE:
                    s = self.w_piece
                    scr.blit(s, (cx - s.get_width() // 2, cy - s.get_height() // 2))
                elif v == BLACK:
                    s = self.b_piece
                    scr.blit(s, (cx - s.get_width() // 2, cy - s.get_height() // 2))

        # ── Coordinates ──────────────────────────────────────────────────

        for i in range(BOARD_N):
            # files
            f_idx = (BOARD_N - 1 - i) if self.flipped else i
            lbl = self.coord_font.render(FILES[f_idx], True, C_COORD)
            x = BX + i * CELL + CELL // 2 - lbl.get_width() // 2
            scr.blit(lbl, (x, BY - 16))
            scr.blit(lbl, (x, BY + BOARD_PX + 6))
            # ranks
            rank_num = (i + 1) if self.flipped else (BOARD_N - i)
            rank_str = str(rank_num)
            lbl = self.coord_font.render(rank_str, True, C_COORD)
            y = BY + i * CELL + CELL // 2 - lbl.get_height() // 2
            scr.blit(lbl, (BX - MARGIN + 4 + (8 if rank_num < 10 else 0), y))
            scr.blit(lbl, (BX + BOARD_PX + 8, y))

        # ── Status bar ───────────────────────────────────────────────────

        sy = BY + BOARD_PX + MARGIN + 4

        if game.game_over:
            # Game-over message
            if game._game_over_message:
                msg_text = game._game_over_message
            else:
                who = "White" if game.winner == WHITE else "Black"
                msg_text = f"{who} wins!"
            txt = self.status_font.render(msg_text, True, C_WIN_TXT)
            scr.blit(txt, (BX, sy))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.hint_font.render(
                    f"  {sub_text}  Q / Esc to leave", True, C_HINT_TXT)
            else:
                sub = self.hint_font.render(
                    "  Press R to play again", True, C_HINT_TXT)
            scr.blit(sub, (BX + txt.get_width(), sy + 3))
        else:
            name = "White" if game.turn == WHITE else "Black"
            dot_col = C_WHITE_FILL if game.turn == WHITE else C_BLACK_FILL
            dot_out = C_WHITE_OUT if game.turn == WHITE else C_BLACK_OUT
            pygame.draw.circle(scr, dot_col, (BX + 8, sy + 10), 7)
            pygame.draw.circle(scr, dot_out, (BX + 8, sy + 10), 7, 1)

            phases = {PH_SELECT: "Select amazon", PH_MOVE: "Move amazon",
                      PH_ARROW: "Shoot arrow"}
            msg = f" {name}  \u2014  {phases[game.phase]}       Move {game.move_num}"
            txt = self.status_font.render(msg, True, C_STATUS_TXT)
            scr.blit(txt, (BX + 20, sy))

        # hints / role indicator
        if game.online:
            role = "White" if game.my_player == WHITE else "Black"
            accent = C_WHITE_FILL if game.my_player == WHITE else C_BLACK_FILL
            tag = self.hint_font.render(f"You: {role}", True, accent)
            scr.blit(tag, (WIN_W - tag.get_width() - BX, sy + 26))
        else:
            parts = []
            if game.phase == PH_ARROW:
                parts.append("Right-click: undo")
            parts.append("F: flip")
            parts.append("R: new game")
            parts.append("Esc: quit")
            hint = self.hint_font.render("    ".join(parts), True, C_HINT_TXT)
            scr.blit(hint, (BX, sy + 26))

        if game.online:
            self._draw_online_status(game)

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            sy = BY + BOARD_PX + MARGIN + 4
            wait = self.hint_font.render(
                "Opponent's turn \u2014 waiting\u2026", True, C_COORD)
            self.screen.blit(wait, (BX, sy + 26))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, C_BG,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.status_font.render(
                "Opponent disconnected", True, C_STATUS_TXT)
            self.screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.hint_font.render(
                "Waiting for reconnection\u2026", True, C_HINT_TXT)
            self.screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.hint_font.render(
                game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Amazons in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized).
    net : client.network.NetworkClient
        Active network connection to the game server.
    my_player : int
        This player's ID (1 = White, 2 = Black).
    initial_state : dict
        The initial game state from the server's ``game_started`` message.

    Returns when the game ends or the user closes the window.
    Does **not** call ``pygame.quit()`` — the caller handles cleanup.
    """
    try:
        from client.shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )
    except ImportError:
        from shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Amazons \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        # ── Poll network ────────────────────────────────────────────
        for msg in net.poll_messages():
            mtype = msg.get("type")
            if mtype == "move_made":
                game.load_state(msg["state"])
                hist.push(msg["state"])
            elif mtype == "game_over":
                game.load_state(msg["state"])
                hist.push(msg["state"])
                game.set_game_over(
                    msg.get("winner"),
                    msg.get("is_draw", False),
                    msg.get("reason", ""),
                )
            elif mtype == "player_disconnected":
                game.opponent_disconnected = True
            elif mtype == "player_reconnected":
                game.opponent_disconnected = False
            elif mtype == "error":
                game.net_error = msg.get("message", "Server error")
            elif mtype in ("connection_error", "connection_closed"):
                game.net_error = msg.get("message", "Connection lost")

        # ── Events ──────────────────────────────────────────────────
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                cell = renderer.pixel_to_cell(*event.pos)
                if cell is None:
                    continue
                move = game.click(*cell)
                if move is not None:
                    net.send_move(move)

        # ── Draw ────────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display, mouse_pos)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(30)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Amazons")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    game = GameClient()

    while True:
        mouse_pos = pygame.mouse.get_pos()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit()
                    sys.exit()
                elif ev.key == pygame.K_r:
                    game.reset()
                elif ev.key == pygame.K_u:
                    game.undo_move()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                cell = renderer.pixel_to_cell(*ev.pos)
                if cell is None:
                    continue
                if ev.button == 1:
                    game.click(*cell)
                elif ev.button == 3:
                    game.undo_move()

        renderer.draw(game, mouse_pos)
        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()
