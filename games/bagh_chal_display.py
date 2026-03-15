"""
Bagh Chal — Pygame display and local hotseat play.

Controls: Left-click to select/place/move. Right-click to deselect.
          R to restart. F to flip board. Esc/Q to quit.
"""

import copy
import sys
import math
try:
    import games._suppress  # noqa: F401
except ImportError:
    try:
        import _suppress  # noqa: F401
    except ImportError:
        pass
import pygame

try:
    from games.bagh_chal_logic import (
        BaghChalLogic, ADJACENCY, EMPTY, TIGER, GOAT,
        PLAYER_GOAT, PLAYER_TIGER,
    )
except ImportError:
    from bagh_chal_logic import (
        BaghChalLogic, ADJACENCY, EMPTY, TIGER, GOAT,
        PLAYER_GOAT, PLAYER_TIGER,
    )

# ── Display Constants ────────────────────────────────────────────────────────

CELL = 120
MARGIN = 70
BOARD_PX = CELL * 4
PANEL_W = 260
WIN_W = MARGIN + BOARD_PX + MARGIN + PANEL_W
WIN_H = MARGIN + BOARD_PX + MARGIN + 40

BG        = (42, 40, 48)
BOARD_COL = (205, 170, 110)
BOARD_BD  = (120, 90, 50)
LINE_COL  = (90, 70, 45)
DIAG_COL  = (110, 85, 55)
NODE_COL  = (90, 70, 45)

TIGER_FILL = (200, 55, 40)
TIGER_OUT  = (140, 30, 20)
GOAT_FILL  = (230, 220, 200)
GOAT_OUT   = (140, 130, 115)

HL_PLACE   = (100, 200, 100, 140)
HL_MOVE    = (80, 180, 255, 140)
HL_CAPTURE = (255, 80, 80, 140)
SEL_COL    = (255, 220, 60)
TXT_COL    = (230, 225, 215)
DIM_COL    = (160, 155, 145)
GOAT_LBL   = (200, 195, 180)
TIGER_LBL  = (220, 90, 75)
ERR_COL    = (225, 75, 65)

PIECE_R = 22
NODE_R  = 6


# ── Game Client ──────────────────────────────────────────────────────────────


class GameClient:
    """Client-side controller with select-then-move UI."""

    def __init__(self, online=False, my_player=None):
        self.logic = BaghChalLogic()
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
        self._game_over_message = None

    def _sync(self):
        self.board = list(self.state["board"])
        self.turn = self.state["turn"]
        self._status = self.logic.get_game_status(self.state)
        self._legal = self.logic.get_legal_moves(self.state, self.turn)

    @property
    def is_my_turn(self):
        if not self.online:
            return True
        return self.turn == self.my_player

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def is_draw(self):
        return self._status["is_draw"]

    @property
    def goats_in_reserve(self):
        return self.state["goats_in_reserve"]

    @property
    def goats_captured(self):
        return self.state["goats_captured"]

    @property
    def phase(self):
        return "placement" if self.state["goats_in_reserve"] > 0 else "movement"

    def load_state(self, state):
        self.state = state
        self._sync()
        self.sel = None
        self.targets = []
        self._game_over_message = None
        self.net_error = ""

    def set_game_over(self, winner, is_draw, reason=""):
        self._status = {"is_over": True, "winner": winner, "is_draw": is_draw}
        if is_draw:
            self._game_over_message = "Game over \u2014 Draw!"
        elif reason == "forfeit":
            name = "Goats" if winner == PLAYER_GOAT else "Tigers"
            self._game_over_message = f"{name} win by forfeit!"
        else:
            self._game_over_message = None

    def click(self, node):
        """Handle a click on node. Returns move to send in online mode."""
        if self.game_over or node is None:
            return None
        if self.online and not self.is_my_turn:
            return None

        player = self.turn

        # Phase 1 goat placement
        if player == PLAYER_GOAT and self.goats_in_reserve > 0:
            for m in self._legal:
                if m["type"] == "place" and m["to"] == node:
                    if self.online:
                        return m
                    self.undo_stack.append(copy.deepcopy(self.state))
                    self.state = self.logic.apply_move(self.state, player, m)
                    self._sync()
                    self.sel = None
                    self.targets = []
                    return None
            return None

        # Select-then-move
        if self.sel is None:
            piece = GOAT if player == PLAYER_GOAT else TIGER
            if self.board[node] == piece:
                dests = [m for m in self._legal if m.get("from") == node]
                if dests:
                    self.sel = node
                    self.targets = dests
            return None

        if node == self.sel:
            self.sel = None
            self.targets = []
            return None

        for m in self.targets:
            if m["to"] == node:
                if self.online:
                    self.sel = None
                    self.targets = []
                    return m
                self.undo_stack.append(copy.deepcopy(self.state))
                self.state = self.logic.apply_move(self.state, player, m)
                self._sync()
                self.sel = None
                self.targets = []
                return None

        # Re-select another piece
        piece = GOAT if player == PLAYER_GOAT else TIGER
        if self.board[node] == piece:
            dests = [m for m in self._legal if m.get("from") == node]
            if dests:
                self.sel = node
                self.targets = dests
                return None
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


# ── History view proxy ──────────────────────────────────────────────────────


class _HistoryView:
    def __init__(self, state, game):
        self.state = state
        self.board = list(state["board"])
        self.turn = state["turn"]
        self._status = game.logic.get_game_status(state)
        self._game_over_message = None
        self.online = game.online
        self.my_player = game.my_player
        self.is_my_turn = False
        self.opponent_disconnected = False
        self.net_error = ""
        self.sel = None
        self.targets = []

    @property
    def game_over(self):
        return self._status["is_over"]

    @property
    def winner(self):
        return self._status["winner"]

    @property
    def is_draw(self):
        return self._status["is_draw"]

    @property
    def goats_in_reserve(self):
        return self.state["goats_in_reserve"]

    @property
    def goats_captured(self):
        return self.state["goats_captured"]

    @property
    def phase(self):
        return "placement" if self.state["goats_in_reserve"] > 0 else "movement"


# ── Renderer ─────────────────────────────────────────────────────────────────


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.flipped = False
        self.f_large = pygame.font.SysFont("arial", 28, bold=True)
        self.f_med = pygame.font.SysFont("arial", 20)
        self.f_small = pygame.font.SysFont("arial", 15)
        self.f_coord = pygame.font.SysFont("arial", 13)
        self.f_piece = pygame.font.SysFont("arial", 15, bold=True)
        self.f_winner = pygame.font.SysFont("arial", 38, bold=True)
        self.f_hint = pygame.font.SysFont("monospace", 13)

    def _node_px(self, node_id):
        r, c = node_id // 5, node_id % 5
        if self.flipped:
            r, c = 4 - r, 4 - c
        return MARGIN + c * CELL, MARGIN + r * CELL

    def node_from_px(self, mx, my):
        best, best_d = None, 30
        for i in range(25):
            nx, ny = self._node_px(i)
            d = math.hypot(mx - nx, my - ny)
            if d < best_d:
                best_d = d
                best = i
        return best

    def draw(self, game, mouse_pos):
        scr = self.screen
        scr.fill(BG)

        # Board background
        pad = 35
        br = pygame.Rect(MARGIN - pad, MARGIN - pad,
                         BOARD_PX + 2 * pad, BOARD_PX + 2 * pad)
        pygame.draw.rect(scr, BOARD_COL, br, border_radius=10)
        pygame.draw.rect(scr, BOARD_BD, br, 3, border_radius=10)

        # Lines
        for nid in range(25):
            x1, y1 = self._node_px(nid)
            for nb in ADJACENCY[nid]:
                if nb > nid:
                    x2, y2 = self._node_px(nb)
                    r1, c1 = nid // 5, nid % 5
                    r2, c2 = nb // 5, nb % 5
                    diag = abs(r1 - r2) == 1 and abs(c1 - c2) == 1
                    pygame.draw.line(scr, DIAG_COL if diag else LINE_COL,
                                     (x1, y1), (x2, y2), 1 if diag else 2)

        # Node dots
        for i in range(25):
            pygame.draw.circle(scr, NODE_COL, self._node_px(i), NODE_R)

        # Coordinates
        for c in range(5):
            ci = (4 - c) if self.flipped else c
            x = MARGIN + c * CELL
            lbl = self.f_coord.render(str(ci), True, DIM_COL)
            scr.blit(lbl, (x - lbl.get_width() // 2, MARGIN - 28))
            scr.blit(lbl, (x - lbl.get_width() // 2,
                           MARGIN + BOARD_PX + 14))
        for r in range(5):
            ri = (4 - r) if self.flipped else r
            y = MARGIN + r * CELL
            lbl = self.f_coord.render(str(ri), True, DIM_COL)
            scr.blit(lbl, (MARGIN - 22, y - lbl.get_height() // 2))

        # Highlights
        surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        if game.sel is not None:
            for m in game.targets:
                x, y = self._node_px(m["to"])
                col = HL_CAPTURE if m["type"] == "capture" else HL_MOVE
                pygame.draw.circle(surf, col, (x, y), PIECE_R + 4)
                if m["type"] == "capture":
                    ox, oy = self._node_px(m["over"])
                    pygame.draw.circle(surf, (255, 50, 50, 90),
                                       (ox, oy), PIECE_R + 6)
        elif (game.turn == PLAYER_GOAT
              and game.goats_in_reserve > 0
              and not game.game_over):
            for i in range(25):
                if game.board[i] == EMPTY:
                    x, y = self._node_px(i)
                    pygame.draw.circle(surf, HL_PLACE, (x, y), PIECE_R + 4)
        scr.blit(surf, (0, 0))

        # Pieces
        for i in range(25):
            p = game.board[i]
            if p == EMPTY:
                continue
            x, y = self._node_px(i)
            if i == game.sel:
                pygame.draw.circle(scr, SEL_COL, (x, y), PIECE_R + 5, 3)
            if p == TIGER:
                pygame.draw.circle(scr, TIGER_FILL, (x, y), PIECE_R)
                pygame.draw.circle(scr, TIGER_OUT, (x, y), PIECE_R, 2)
                for dy in [-7, 0, 7]:
                    pygame.draw.line(scr, TIGER_OUT,
                                     (x - 10, y + dy), (x + 10, y + dy), 2)
                t = self.f_piece.render("T", True, (255, 255, 255))
                scr.blit(t, (x - t.get_width() // 2,
                             y - t.get_height() // 2))
            else:
                pygame.draw.circle(scr, GOAT_FILL, (x, y), PIECE_R)
                pygame.draw.circle(scr, GOAT_OUT, (x, y), PIECE_R, 2)
                t = self.f_piece.render("G", True, (60, 55, 45))
                scr.blit(t, (x - t.get_width() // 2,
                             y - t.get_height() // 2))

        # Side panel
        self._draw_panel(game)

        # Game over overlay
        self._draw_game_over(game)

        # Online overlays
        if game.online:
            self._draw_online_status(game)

    def _draw_panel(self, game):
        px = MARGIN + BOARD_PX + MARGIN
        py = MARGIN

        title = self.f_large.render("Bagh Chal", True, TXT_COL)
        self.screen.blit(title, (px, 20))

        # Turn
        if game.turn == PLAYER_GOAT:
            txt, col = "GOAT'S TURN", GOAT_LBL
        else:
            txt, col = "TIGER'S TURN", TIGER_LBL
        self.screen.blit(self.f_med.render(txt, True, col), (px, py))

        # Phase
        phase = "Phase 1 \u2014 Placement" if game.phase == "placement" else "Phase 2 \u2014 Movement"
        self.screen.blit(self.f_small.render(phase, True, DIM_COL), (px, py + 28))

        # Reserve
        py += 65
        self.screen.blit(self.f_med.render(
            f"Reserve: {game.goats_in_reserve}", True, GOAT_LBL), (px, py))
        gy = py + 28
        for i in range(game.goats_in_reserve):
            gx = px + (i % 10) * 20 + 8
            gy2 = gy + (i // 10) * 20
            pygame.draw.circle(self.screen, GOAT_FILL, (gx, gy2), 7)
            pygame.draw.circle(self.screen, GOAT_OUT, (gx, gy2), 7, 1)

        # Captured
        py += 80
        self.screen.blit(self.f_med.render(
            f"Captured: {game.goats_captured} / 5", True, TIGER_LBL), (px, py))
        cy = py + 28
        for i in range(game.goats_captured):
            cx = px + i * 26 + 8
            pygame.draw.circle(self.screen, (100, 90, 80), (cx, cy), 7)
            pygame.draw.line(self.screen, (200, 50, 40),
                             (cx - 4, cy - 4), (cx + 4, cy + 4), 2)
            pygame.draw.line(self.screen, (200, 50, 40),
                             (cx - 4, cy + 4), (cx + 4, cy - 4), 2)

        # On board
        py += 60
        on_board = game.board.count(GOAT)
        self.screen.blit(self.f_small.render(
            f"Goats on board: {on_board}", True, DIM_COL), (px, py))

        # Role indicator (online)
        if game.online:
            py += 40
            role = "Goats" if game.my_player == PLAYER_GOAT else "Tigers"
            accent = GOAT_LBL if game.my_player == PLAYER_GOAT else TIGER_LBL
            self.screen.blit(self.f_small.render(
                f"You: {role}", True, accent), (px, py))
        else:
            py += 40
            self.screen.blit(self.f_small.render(
                "R: restart  U: undo  F: flip  Q: quit",
                True, (80, 78, 72)), (px, py))

    def _draw_game_over(self, game):
        if not game.game_over:
            return
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        self.screen.blit(ov, (0, 0))

        if game._game_over_message:
            msg = game._game_over_message
        elif game.is_draw:
            msg = "GAME DRAWN"
        elif game.winner == PLAYER_GOAT:
            msg = "GOATS WIN!"
        elif game.winner == PLAYER_TIGER:
            msg = "TIGERS WIN!"
        else:
            msg = "Game Over"

        col = GOAT_LBL if game.winner == PLAYER_GOAT else TIGER_LBL
        if game.is_draw:
            col = (200, 200, 100)
        t = self.f_winner.render(msg, True, col)
        bx = WIN_W // 2 - t.get_width() // 2
        by = WIN_H // 2 - t.get_height() // 2 - 16
        pad = 28
        box = pygame.Rect(bx - pad, by - pad,
                          t.get_width() + pad * 2,
                          t.get_height() + pad * 2 + 36)
        pygame.draw.rect(self.screen, (20, 20, 30), box, border_radius=12)
        pygame.draw.rect(self.screen, col, box, 2, border_radius=12)
        self.screen.blit(t, (bx, by))

        if game.online:
            sub = self.f_hint.render("Q / Esc to leave", True, DIM_COL)
        else:
            sub = self.f_hint.render("R: restart  Q: quit", True, DIM_COL)
        self.screen.blit(sub, (WIN_W // 2 - sub.get_width() // 2,
                               by + t.get_height() + 14))

    def _draw_online_status(self, game):
        if not game.game_over and not game.is_my_turn:
            wait = self.f_hint.render(
                "Opponent's turn \u2014 waiting\u2026", True, DIM_COL)
            self.screen.blit(wait, (MARGIN, MARGIN - 22))

        if game.opponent_disconnected and not game.game_over:
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 80))
            self.screen.blit(overlay, (0, 0))
            bh = 60
            by = WIN_H // 2 - bh // 2
            pygame.draw.rect(self.screen, BG, (0, by, WIN_W, bh))
            msg = self.f_med.render("Opponent disconnected", True, TXT_COL)
            self.screen.blit(msg, msg.get_rect(center=(WIN_W // 2, by + 18)))
            sub = self.f_hint.render(
                "Waiting for reconnection\u2026", True, DIM_COL)
            self.screen.blit(sub, sub.get_rect(center=(WIN_W // 2, by + 42)))

        if game.net_error:
            bar = pygame.Rect(0, 0, WIN_W, 28)
            pygame.draw.rect(self.screen, (60, 15, 15), bar)
            err = self.f_hint.render(game.net_error, True, ERR_COL)
            self.screen.blit(err, err.get_rect(center=(WIN_W // 2, 14)))


# ── Online entry point ───────────────────────────────────────────────────────


def run_online(screen, net, my_player, initial_state):
    try:
        from client.shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )
    except ImportError:
        from shared import (
            History, Orientation, draw_command_panel, handle_shared_input,
        )

    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bagh Chal \u2014 Online")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    game = GameClient(online=True, my_player=my_player)
    game.load_state(initial_state)

    hist = History()
    hist.push(initial_state)
    orient = Orientation()

    running = True
    while running:
        for msg in net.poll_messages():
            mtype = msg.get("type")
            if mtype == "move_made":
                game.load_state(msg["state"])
                hist.push(msg["state"])
            elif mtype == "game_over":
                game.load_state(msg["state"])
                hist.push(msg["state"])
                game.set_game_over(
                    msg.get("winner"), msg.get("is_draw", False),
                    msg.get("reason", ""))
            elif mtype == "player_disconnected":
                game.opponent_disconnected = True
            elif mtype == "player_reconnected":
                game.opponent_disconnected = False
            elif mtype == "error":
                game.net_error = msg.get("message", "Server error")
            elif mtype in ("connection_error", "connection_closed"):
                game.net_error = msg.get("message", "Connection lost")

        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            result = handle_shared_input(event, hist, orient)
            if result == "quit":
                running = False
            elif result in ("handled", "input_blocked"):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game.game_over:
                    continue
                if event.button == 3:
                    game.deselect()
                    continue
                if event.button == 1:
                    node = renderer.node_from_px(*event.pos)
                    move = game.click(node)
                    if move is not None:
                        net.send_move(move)

        renderer.flipped = orient.flipped
        if hist.is_live:
            display = game
        else:
            display = _HistoryView(hist.current(), game)
        renderer.draw(display, mouse_pos)
        draw_command_panel(screen, hist, game.is_my_turn)
        pygame.display.flip()
        clock.tick(60)


# ── Main loop (local hotseat play) ───────────────────────────────────────────


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Bagh Chal")
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
                    game.undo()
                elif ev.key == pygame.K_f:
                    renderer.flipped = not renderer.flipped
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 3:
                    game.deselect()
                elif ev.button == 1:
                    node = renderer.node_from_px(*ev.pos)
                    game.click(node)

        renderer.draw(game, mouse_pos)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
