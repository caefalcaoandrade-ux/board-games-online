"""
Copenhagen Hnefatafl 11x11 -- Pygame display and local hotseat play.

Two players on the same computer taking turns.
Controls: Left-click to select/move. U to undo. R to restart. F to flip.
          Esc/Q to quit. Left/Right arrows to browse history (online).
"""

import copy
import sys

try:
    import games._suppress  # noqa: F401
except ImportError:
    import _suppress  # noqa: F401
import pygame

try:
    from games.hnefatafl_logic import (
        HnefataflLogic, BOARD_N, EMPTY, ATTACKER, DEFENDER, KING,
        PLAYER_ATTACKER, PLAYER_DEFENDER, COL_LABELS,
    )
except ImportError:
    from hnefatafl_logic import (
        HnefataflLogic, BOARD_N, EMPTY, ATTACKER, DEFENDER, KING,
        PLAYER_ATTACKER, PLAYER_DEFENDER, COL_LABELS,
    )

# ── Display Constants ────────────────────────────────────────────────────────

N = BOARD_N
CELL = 68
BOARD_PX = N * CELL
LABEL_M = 44
TOP_M = 32
RIGHT_M = 16
PANEL_H = 64
WIN_W = LABEL_M + BOARD_PX + RIGHT_M
WIN_H = TOP_M + BOARD_PX + LABEL_M + PANEL_H

THRONE = (5, 5)

# ── Colour palette ───────────────────────────────────────────────────────────

C_BG           = (40, 36, 32)
C_CELL_A       = (225, 202, 165)
C_CELL_B       = (213, 190, 153)
C_THRONE       = (186, 168, 132)
C_CORNER       = (164, 148, 118)
C_GRID         = (140, 128, 110)
C_MARK         = (130, 116, 96)
C_SEL_FILL     = (100, 190, 70, 70)
C_SEL_BORDER   = (100, 210, 60)
C_MOVE_DOT     = (80, 170, 60)
C_MOVE_RING    = (55, 130, 45)
C_LAST         = (210, 200, 80, 45)
C_CAPTURE_RING = (230, 55, 55)

C_ATK          = (62, 30, 22)
C_ATK_RIM      = (42, 18, 12)
C_DEF          = (242, 237, 224)
C_DEF_RIM      = (182, 174, 156)
C_KING_FILL    = (244, 222, 110)
C_KING_RIM     = (185, 155, 45)
C_KING_MARK    = (155, 120, 20)

C_PANEL        = (50, 45, 40)
C_TEXT         = (222, 214, 200)
C_LABEL        = (175, 165, 148)
C_ACCENT_ATK   = (180, 80, 60)
C_ACCENT_DEF   = (100, 170, 220)


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller wrapping HnefataflLogic.

    Maintains local UI state (selection, targets, highlights) that the
    Renderer reads each frame. The authoritative game state is only
    updated when a complete move is committed through the logic module.
    """

    def __init__(self, online=False, my_player=None):
        self.logic = HnefataflLogic()
        self.online = online
        self.my_player = my_player
        self.opponent_disconnected = False
        self.net_error = ""
        self.undo_stack = []
        self.reset()

    def reset(self):
        self.state = self.logic.create_initial_state()
        self._sync()
        self.sel = None
        self.targets = []
        self.undo_stack = []

    def _sync(self):
        """Sync display-facing attributes from authoritative state."""
        self.board = [row[:] for row in self.state["board"]]
        self.turn = self.state["turn"]
        self.game_over = self.state["game_over"]
        self.winner = self.state["winner"]
        self.message = self.state["message"]
        self.last_move = self.state["last_move"]
        self.captured_last = self.state["captured_last"]

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
        self._sync()
        self.sel = None
        self.targets = []
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        """Force game-over state from a server message (e.g. forfeit)."""
        self.game_over = True
        self.winner = winner
        if is_draw:
            self.message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            wn = "Attackers" if winner == PLAYER_ATTACKER else "Defenders"
            self.message = f"{wn} win by forfeit!"
        # Otherwise _sync already set self.message from the state

    def click(self, r, c):
        """Handle a click on board cell (r, c).

        In online mode, returns the move list to send to the server
        instead of applying it locally.  Returns None otherwise.
        """
        if self.game_over:
            return None
        if self.online and not self.is_my_turn:
            return None
        if not HnefataflLogic.in_bounds(r, c):
            self.sel = None
            self.targets = []
            return None

        # If a legal-move square was clicked, execute the move
        if self.sel is not None and [r, c] in self.targets:
            fr, fc = self.sel
            move = [[fr, fc], [r, c]]
            if self.online:
                # Don't apply locally — send to server
                self.sel = None
                self.targets = []
                return move
            # Local mode: apply immediately
            self.undo_stack.append(copy.deepcopy(self.state))
            self.state = self.logic.apply_move(self.state, self.state["turn"], move)
            self._sync()
            self.sel = None
            self.targets = []
            return None

        # Try selecting a piece
        p = self.board[r][c]
        own = False
        if self.turn == PLAYER_ATTACKER and p == ATTACKER:
            own = True
        elif self.turn == PLAYER_DEFENDER and p in (DEFENDER, KING):
            own = True
        if own:
            moves = HnefataflLogic.get_piece_moves(self.board, r, c)
            if moves:
                self.sel = (r, c)
                self.targets = moves
            else:
                self.sel = None
                self.targets = []
        else:
            self.sel = None
            self.targets = []
        return None

    def deselect(self):
        self.sel = None
        self.targets = []

    def undo(self):
        if self.online:
            return
        if self.undo_stack:
            self.state = self.undo_stack.pop()
            self._sync()
            self.sel = None
            self.targets = []

    def piece_counts(self):
        return HnefataflLogic.piece_counts(self.board)


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    """Lightweight proxy for rendering a past state without modifying GameClient."""

    def __init__(self, state, game):
        self.board = state["board"]
        self.turn = state["turn"]
        self.game_over = state["game_over"]
        self.winner = state["winner"]
        self.message = state["message"]
        self.last_move = state["last_move"]
        self.captured_last = state["captured_last"]
        self.sel = None
        self.targets = []
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        self._board = state["board"]

    def piece_counts(self):
        return HnefataflLogic.piece_counts(self._board)


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.flipped = False
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.sfont = pygame.font.SysFont("Arial", 14)
        self.bfont = pygame.font.SysFont("Arial", 26, bold=True)

    # ── Coordinate conversion ─────────────────────────────────────────────

    def cell_xy(self, r, c):
        """Top-left pixel of board cell (r, c), accounting for flip."""
        if self.flipped:
            return LABEL_M + (N - 1 - c) * CELL, TOP_M + r * CELL
        return LABEL_M + c * CELL, TOP_M + (N - 1 - r) * CELL

    def pixel_to_cell(self, mx, my):
        """Convert pixel coordinates to board (r, c), or None."""
        bx = mx - LABEL_M
        by = my - TOP_M
        if bx < 0 or by < 0 or bx >= BOARD_PX or by >= BOARD_PX:
            return None
        gc = bx // CELL
        gr = by // CELL
        if self.flipped:
            c = N - 1 - gc
            r = gr
        else:
            c = gc
            r = (N - 1) - gr
        if not HnefataflLogic.in_bounds(r, c):
            return None
        return r, c

    # ── Main draw ─────────────────────────────────────────────────────────

    def draw(self, game):
        """Draw the full frame (does NOT call pygame.display.flip)."""
        self.screen.fill(C_BG)
        self._draw_board()
        self._draw_highlights(game)
        self._draw_pieces(game)
        self._draw_labels()
        self._draw_panel(game)
        if game.online:
            self._draw_online_status(game)

    # ── Board grid ────────────────────────────────────────────────────────

    def _draw_board(self):
        for r in range(N):
            for c in range(N):
                x, y = self.cell_xy(r, c)
                if HnefataflLogic.is_corner(r, c):
                    col = C_CORNER
                elif (r, c) == THRONE:
                    col = C_THRONE
                elif (r + c) % 2 == 0:
                    col = C_CELL_A
                else:
                    col = C_CELL_B
                pygame.draw.rect(self.screen, col, (x, y, CELL, CELL))
                pygame.draw.rect(self.screen, C_GRID, (x, y, CELL, CELL), 1)

        # Marks on restricted squares
        restricted = [[0, 0], [0, 10], [10, 0], [10, 10], [5, 5]]
        for rc in restricted:
            r, c = rc
            cx, cy = self.cell_xy(r, c)
            cx += CELL // 2
            cy += CELL // 2
            if HnefataflLogic.is_corner(r, c):
                d = CELL // 4
                pygame.draw.line(self.screen, C_MARK,
                                 (cx - d, cy - d), (cx + d, cy + d), 2)
                pygame.draw.line(self.screen, C_MARK,
                                 (cx - d, cy + d), (cx + d, cy - d), 2)
            else:
                d = CELL // 5
                pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
                pygame.draw.polygon(self.screen, C_MARK, pts, 2)

    # ── Highlights ────────────────────────────────────────────────────────

    def _draw_highlights(self, game):
        # Last move (from / to)
        if game.last_move:
            for pos in game.last_move:
                x, y = self.cell_xy(pos[0], pos[1])
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill(C_LAST)
                self.screen.blit(s, (x, y))

        # Selected piece
        if game.sel:
            x, y = self.cell_xy(*game.sel)
            s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            s.fill(C_SEL_FILL)
            self.screen.blit(s, (x, y))
            pygame.draw.rect(self.screen, C_SEL_BORDER,
                             (x, y, CELL, CELL), 3)

        # Legal-move dots
        for pos in game.targets:
            cx, cy = self.cell_xy(pos[0], pos[1])
            cx += CELL // 2
            cy += CELL // 2
            pygame.draw.circle(self.screen, C_MOVE_DOT, (cx, cy), 9)
            pygame.draw.circle(self.screen, C_MOVE_RING, (cx, cy), 9, 2)

        # Captured squares flash ring
        for pos in game.captured_last:
            cx, cy = self.cell_xy(pos[0], pos[1])
            cx += CELL // 2
            cy += CELL // 2
            pygame.draw.circle(self.screen, C_CAPTURE_RING, (cx, cy),
                               CELL // 2 - 3, 3)

    # ── Pieces ────────────────────────────────────────────────────────────

    def _draw_pieces(self, game):
        rad = CELL // 2 - 7
        for r in range(N):
            for c in range(N):
                p = game.board[r][c]
                if p == EMPTY:
                    continue
                cx, cy = self.cell_xy(r, c)
                cx += CELL // 2
                cy += CELL // 2

                if p == ATTACKER:
                    pygame.draw.circle(self.screen, C_ATK, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_ATK_RIM, (cx, cy), rad, 2)
                    pygame.draw.circle(self.screen, (90, 50, 38), (cx, cy), 5)

                elif p == DEFENDER:
                    pygame.draw.circle(self.screen, C_DEF, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_DEF_RIM, (cx, cy), rad, 2)
                    pygame.draw.circle(self.screen, (210, 205, 192),
                                       (cx, cy), 5)

                elif p == KING:
                    pygame.draw.circle(self.screen, C_KING_FILL, (cx, cy), rad)
                    pygame.draw.circle(self.screen, C_KING_RIM, (cx, cy), rad, 3)
                    # Crown: small cross + dots
                    d = rad // 2
                    pygame.draw.line(self.screen, C_KING_MARK,
                                     (cx - d, cy), (cx + d, cy), 3)
                    pygame.draw.line(self.screen, C_KING_MARK,
                                     (cx, cy - d), (cx, cy + d), 3)
                    td = d + 2
                    for dx, dy in ((-td, 0), (td, 0), (0, -td), (0, td)):
                        pygame.draw.circle(self.screen, C_KING_MARK,
                                           (cx + dx, cy + dy), 3)

    # ── Coordinate labels ─────────────────────────────────────────────────

    def _draw_labels(self):
        # Columns (below board)
        for i in range(N):
            x = LABEL_M + i * CELL + CELL // 2
            y = TOP_M + BOARD_PX + 14
            c_idx = (N - 1 - i) if self.flipped else i
            txt = self.font.render(COL_LABELS[c_idx], True, C_LABEL)
            self.screen.blit(txt, txt.get_rect(center=(x, y)))
        # Rows (left of board)
        for i in range(N):
            x = LABEL_M // 2
            y = TOP_M + i * CELL + CELL // 2
            r_idx = i if self.flipped else (N - 1 - i)
            txt = self.font.render(str(r_idx + 1), True, C_LABEL)
            self.screen.blit(txt, txt.get_rect(center=(x, y)))

    # ── Status panel ──────────────────────────────────────────────────────

    def _draw_panel(self, game):
        py = TOP_M + BOARD_PX + LABEL_M
        pygame.draw.rect(self.screen, C_PANEL, (0, py, WIN_W, PANEL_H))

        # Turn / result message
        txt = self.bfont.render(game.message, True, C_TEXT)
        self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, py + 22)))

        # Piece counts
        atk, dfn = game.piece_counts()
        lbl = self.sfont.render(f"Attackers: {atk}", True, C_ACCENT_ATK)
        self.screen.blit(lbl, (12, py + 44))
        lbl2 = self.sfont.render(f"Defenders: {dfn}", True, C_ACCENT_DEF)
        self.screen.blit(lbl2, (130, py + 44))

        # Controls / role indicator
        if game.online:
            role = "Attacker" if game.my_player == PLAYER_ATTACKER else "Defender"
            accent = C_ACCENT_ATK if game.my_player == PLAYER_ATTACKER else C_ACCENT_DEF
            tag = self.sfont.render(f"You: {role}", True, accent)
            self.screen.blit(tag, (280, py + 44))
        else:
            hint = self.sfont.render("R Restart   U Undo   F Flip   Q Quit",
                                     True, C_LABEL)
            self.screen.blit(hint, (WIN_W - hint.get_width() - 12, py + 44))

        # If game over, overlay banner
        if game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 100))
            self.screen.blit(overlay, (0, 0))
            banner_h = 80
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, C_PANEL,
                             (0, banner_y, WIN_W, banner_h))
            pygame.draw.line(self.screen,
                             C_ACCENT_ATK if game.winner == PLAYER_ATTACKER
                             else C_ACCENT_DEF,
                             (0, banner_y), (WIN_W, banner_y), 3)
            pygame.draw.line(self.screen,
                             C_ACCENT_ATK if game.winner == PLAYER_ATTACKER
                             else C_ACCENT_DEF,
                             (0, banner_y + banner_h),
                             (WIN_W, banner_y + banner_h), 3)
            big = self.bfont.render(game.message, True, C_TEXT)
            self.screen.blit(big, big.get_rect(center=(WIN_W // 2,
                                                        banner_y + 28)))
            if game.online:
                you_won = game.winner == game.my_player
                sub_text = "You win!" if you_won else "You lose."
                sub = self.sfont.render(
                    f"{sub_text}  Press Esc to exit", True, C_LABEL)
            else:
                sub = self.sfont.render("Press R to play again", True, C_LABEL)
            self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2,
                                                        banner_y + 56)))

    # ── Online overlays ───────────────────────────────────────────────

    def _draw_online_status(self, game):
        """Draw overlays specific to online multiplayer."""
        # "Waiting for opponent" when it's not your turn
        if not game.game_over and not game.is_my_turn:
            py = TOP_M + BOARD_PX + LABEL_M
            wait = self.sfont.render(
                "Opponent's turn \u2014 waiting\u2026", True, C_LABEL)
            self.screen.blit(wait, (WIN_W - wait.get_width() - 12, py + 44))

        # Opponent disconnected banner
        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            banner_h = 60
            banner_y = WIN_H // 2 - banner_h // 2
            pygame.draw.rect(self.screen, C_PANEL,
                             (0, banner_y, WIN_W, banner_h))
            msg = self.bfont.render("Opponent disconnected", True, C_TEXT)
            self.screen.blit(msg, msg.get_rect(
                center=(WIN_W // 2, banner_y + 18)))
            sub = self.sfont.render(
                "Waiting for reconnection\u2026", True, C_LABEL)
            self.screen.blit(sub, sub.get_rect(
                center=(WIN_W // 2, banner_y + 42)))

        # Connection error bar at top
        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.sfont.render(game.net_error, True, (225, 75, 65))
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    """Run Hnefatafl in online multiplayer mode.

    Parameters
    ----------
    screen : pygame.Surface
        The current Pygame display surface (will be resized).
    net : client.network.NetworkClient
        Active network connection to the game server.
    my_player : int
        This player's ID (1 = attacker, 2 = defender).
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
    pygame.display.set_caption("Copenhagen Hnefatafl \u2014 Online")
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
        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            # Game-specific input (only when live)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                cell = renderer.pixel_to_cell(*event.pos)
                if cell is None:
                    game.deselect()
                    continue
                r, c = cell
                move = game.click(r, c)
                if move is not None:
                    net.send_move(move)

        # ── Draw ────────────────────────────────────────────────────
        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(30)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Copenhagen Hnefatafl  11\u00d711")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient()

    running = True
    while running:
        renderer.draw(game)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif event.key == pygame.K_r:
                    game.reset()
                elif event.key == pygame.K_u:
                    game.undo()
                elif event.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.game_over:
                    continue
                cell = renderer.pixel_to_cell(*event.pos)
                if cell is None:
                    game.deselect()
                    continue
                r, c = cell
                game.click(r, c)

        clock.tick(30)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
