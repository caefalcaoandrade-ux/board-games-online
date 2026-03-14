"""Pygame lobby screen — select a game, create or join a room, wait for opponent.

Returns the ``game_started`` server message and the live :class:`NetworkClient`
so the caller can hand off to the appropriate game display module.

Usage::

    from client.lobby import run_lobby

    result, net = run_lobby("ws://localhost:8000/ws")
    if result is not None:
        # result["game"], result["state"], result["your_player"], ...
        launch_game_display(result, net)
"""

import sys
import os

# Ensure the project root is on sys.path so sibling-package imports work
# when running this file directly (e.g. `python client/lobby.py`).
_project_root = os.path.join(os.path.dirname(__file__), "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    import games._suppress  # noqa: F401
except ImportError:
    pass

import pygame

from client.network import NetworkClient
from games import list_games
from client.rules import (
    rules_file_for as _rules_file_for,
    run_rules_viewer as _run_rules_viewer,
    draw_help_icon as _draw_help_icon,
    HELP_SZ as _HELP_SZ,
)

# ── Layout / palette ─────────────────────────────────────────────────────────

WIN_W, WIN_H = 620, 520

BG        = (34, 32, 36)
BTN       = (55, 120, 200)
BTN_HOV   = (75, 140, 220)
BTN_DIS   = (55, 52, 60)
ITEM_BG   = (52, 48, 58)
ITEM_HOV  = (62, 58, 68)
ITEM_SEL  = (45, 100, 180)
TXT       = (215, 215, 215)
TXT_DIM   = (130, 130, 130)
TXT_BTN   = (240, 240, 240)
INPUT_BG  = (38, 34, 42)
INPUT_BD  = (75, 70, 85)
INPUT_AC  = (90, 150, 230)
ERR_BG    = (60, 15, 15)
ERR_CLR   = (225, 75, 65)
CODE_CLR  = (90, 210, 120)
DIVIDER   = (65, 60, 72)

# Screen phases
PH_PICK    = 0
PH_WAITING = 1


# ── Helpers ──────────────────────────────────────────────────────────────────

def _draw_button(screen, font, text, rect, mx, my, clicked, enabled=True):
    """Draw a rounded rectangle button.  Return True if clicked this frame."""
    hover = enabled and rect.collidepoint(mx, my)
    color = BTN_DIS if not enabled else BTN_HOV if hover else BTN
    pygame.draw.rect(screen, color, rect, border_radius=6)
    lbl = font.render(text, True, TXT_BTN if enabled else TXT_DIM)
    screen.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                      rect.centery - lbl.get_height() // 2))
    return hover and clicked and enabled


# ── Public entry point ───────────────────────────────────────────────────────

def run_lobby(server_url: str = "ws://localhost:8000/ws"):
    """Run the lobby UI.

    Returns ``(game_started_msg, network_client)`` when the game begins,
    or ``(None, None)`` if the user closed the window.
    """
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Board Games Online")
    clock = pygame.time.Clock()

    # Fonts
    f_title   = pygame.font.SysFont("arial", 24, bold=True)
    f_head    = pygame.font.SysFont("arial", 18, bold=True)
    f_item    = pygame.font.SysFont("arial", 17)
    f_btn     = pygame.font.SysFont("arial", 17, bold=True)
    f_small   = pygame.font.SysFont("arial", 14)
    f_code    = pygame.font.SysFont("courier", 38, bold=True)
    f_input   = pygame.font.SysFont("courier", 20)
    f_status  = pygame.font.SysFont("arial", 20)

    # State
    games = list_games()
    selected_game: str | None = None
    game_scroll = 0
    code_input = ""
    input_active = False
    error_msg = ""
    error_ttl = 0          # frames remaining
    phase = PH_PICK
    waiting_code = ""

    net: NetworkClient | None = None
    pending: tuple | None = None   # ("create", name) | ("join", code)
    result: dict | None = None

    def show_error(msg: str):
        nonlocal error_msg, error_ttl
        error_msg = msg
        error_ttl = 240            # ~4 s at 60 fps

    def cancel_waiting():
        nonlocal phase, pending, net
        pending = None
        if net is not None:
            net.disconnect()
            net = None
        phase = PH_PICK

    def begin_action(action: str, arg: str):
        nonlocal net, pending
        if net is not None:
            net.disconnect()
        net = NetworkClient(server_url)
        net.connect()
        pending = (action, arg)

    # ── Main loop ────────────────────────────────────────────────────────

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True

            elif ev.type == pygame.MOUSEWHEEL and phase == PH_PICK:
                _GSTEP = 38
                _GTOTAL = len(games) * _GSTEP - 4
                _GVIS = WIN_H - 180 - 90
                _GMAX = max(0, _GTOTAL - _GVIS)
                game_scroll = max(0, min(_GMAX, game_scroll - ev.y * _GSTEP))

            elif ev.type == pygame.KEYDOWN and phase == PH_PICK:
                if input_active:
                    if ev.key == pygame.K_BACKSPACE:
                        code_input = code_input[:-1]
                    elif ev.key == pygame.K_ESCAPE:
                        input_active = False
                    elif ev.key == pygame.K_RETURN and code_input.strip():
                        begin_action("join", code_input.strip())
                    elif (ev.key == pygame.K_v
                          and (ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))):
                        # Ctrl+V / Cmd+V paste
                        pasted = ""
                        try:
                            import pyperclip
                            pasted = pyperclip.paste()
                        except Exception:
                            try:
                                import tkinter as tk
                                root = tk.Tk()
                                root.withdraw()
                                pasted = root.clipboard_get()
                                root.destroy()
                            except Exception:
                                pass
                        # Filter to alnum and respect 6-char limit
                        for ch in pasted:
                            if len(code_input) >= 6:
                                break
                            if ch.isalnum():
                                code_input += ch.upper()
                    elif len(code_input) < 6 and ev.unicode.isalnum():
                        code_input += ev.unicode.upper()

        # ── Pending action → fire once connected ─────────────────────

        if pending is not None and net is not None:
            if net.connected:
                action, arg = pending
                if action == "create":
                    net.create_room(arg)
                else:
                    net.join_room(arg)
                pending = None
            elif net.error:
                show_error(net.error)
                pending = None
                net = None

        # ── Drain network queue ──────────────────────────────────────

        if net is not None:
            for msg in net.poll_messages():
                mtype = msg.get("type")
                if mtype == "room_created":
                    waiting_code = msg.get("code", "")
                    phase = PH_WAITING
                elif mtype == "room_joined":
                    waiting_code = msg.get("code", "")
                    phase = PH_WAITING
                elif mtype == "game_started":
                    result = msg
                    running = False
                elif mtype == "error":
                    show_error(msg.get("message", "Server error"))
                    if phase == PH_WAITING:
                        cancel_waiting()
                elif mtype in ("connection_error", "connection_closed"):
                    show_error(msg.get("message", "Connection lost"))
                    if phase == PH_WAITING:
                        cancel_waiting()

        # ── Draw ─────────────────────────────────────────────────────

        screen.fill(BG)

        if phase == PH_PICK:
            # ── title ────────────────────────────────────────────────
            t = f_title.render("Board Games Online", True, TXT)
            screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 16))

            # ── left column: scrollable game list ──────────────────────
            lx = 24
            h = f_head.render("Select a Game", True, TXT_DIM)
            screen.blit(h, (lx, 60))

            G_ITEM_H, G_GAP = 34, 4
            G_STEP = G_ITEM_H + G_GAP
            G_TOP = 90
            G_BOT = WIN_H - 90
            G_W = 260
            g_total = len(games) * G_STEP - G_GAP
            g_max = max(0, g_total - (G_BOT - G_TOP))
            game_scroll = max(0, min(g_max, game_scroll))

            clip = pygame.Rect(lx - 2, G_TOP, G_W + 4, G_BOT - G_TOP)
            screen.set_clip(clip)
            help_clicked_game = None
            for gi, gname in enumerate(games):
                gy = G_TOP + gi * G_STEP - game_scroll
                r = pygame.Rect(lx, gy, G_W, G_ITEM_H)
                hov = r.collidepoint(mx, my) and clip.collidepoint(mx, my)
                if gname == selected_game:
                    pygame.draw.rect(screen, ITEM_SEL, r, border_radius=4)
                elif hov:
                    pygame.draw.rect(screen, ITEM_HOV, r, border_radius=4)
                else:
                    pygame.draw.rect(screen, ITEM_BG, r, border_radius=4)
                screen.blit(f_item.render(gname, True, TXT), (lx + 12, gy + 8))
                # Help icon
                hx = lx + G_W - _HELP_SZ - 8
                hy = gy + (G_ITEM_H - _HELP_SZ) // 2
                if _rules_file_for(gname):
                    h_hov = _draw_help_icon(screen, f_small, hx, hy,
                                            mx, my, clip)
                    if h_hov and clicked:
                        help_clicked_game = gname
                    elif hov and clicked and not h_hov:
                        selected_game = gname
                else:
                    if hov and clicked:
                        selected_game = gname
            screen.set_clip(None)

            # Scroll indicators
            arrow_col = (100, 100, 110)
            acx = lx + G_W // 2
            if game_scroll > 0:
                a = f_small.render("\u25b2 more", True, arrow_col)
                screen.blit(a, (acx - a.get_width() // 2, G_TOP - 17))
            if game_scroll < g_max:
                a = f_small.render("\u25bc more", True, arrow_col)
                screen.blit(a, (acx - a.get_width() // 2, G_BOT + 2))

            if help_clicked_game:
                lobby_fonts = (f_title, f_head, f_btn, f_small)
                _run_rules_viewer(screen, lobby_fonts, help_clicked_game)

            # ── right column: create / join ──────────────────────────
            rx, ry = 320, 60

            # Create section
            screen.blit(f_head.render("Create Room", True, TXT_DIM), (rx, ry))
            ry += 28
            if selected_game:
                sl = f_item.render(f"Game: {selected_game}", True, TXT)
            else:
                sl = f_item.render("Pick a game first", True, TXT_DIM)
            screen.blit(sl, (rx, ry)); ry += 30

            cb = pygame.Rect(rx, ry, 260, 38)
            if _draw_button(screen, f_btn, "Create Room", cb,
                            mx, my, clicked, enabled=selected_game is not None):
                begin_action("create", selected_game)
            ry += 56

            # Divider
            pygame.draw.line(screen, DIVIDER, (rx, ry), (rx + 260, ry))
            ry += 20

            # Join section
            screen.blit(f_head.render("Join Room", True, TXT_DIM), (rx, ry))
            ry += 28
            screen.blit(f_small.render("Enter room code:", True, TXT_DIM),
                        (rx, ry))
            ry += 20

            # Text input
            ir = pygame.Rect(rx, ry, 260, 36)
            bd = INPUT_AC if input_active else INPUT_BD
            pygame.draw.rect(screen, INPUT_BG, ir, border_radius=4)
            pygame.draw.rect(screen, bd, ir, 2, border_radius=4)
            its = f_input.render(code_input, True, TXT)
            screen.blit(its, (rx + 10, ry + 6))
            if input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
                cx = rx + 10 + its.get_width() + 2
                pygame.draw.line(screen, TXT, (cx, ry + 7), (cx, ry + 29), 2)
            if ir.collidepoint(mx, my) and clicked:
                input_active = True
            elif clicked and not ir.collidepoint(mx, my):
                input_active = False
            ry += 46

            jb = pygame.Rect(rx, ry, 260, 38)
            if _draw_button(screen, f_btn, "Join Room", jb,
                            mx, my, clicked,
                            enabled=len(code_input.strip()) >= 4):
                begin_action("join", code_input.strip())

        elif phase == PH_WAITING:
            cy = 130
            s = f_status.render("Waiting for opponent to join...", True, TXT)
            screen.blit(s, (WIN_W // 2 - s.get_width() // 2, cy))
            cy += 50

            cs = f_code.render(waiting_code, True, CODE_CLR)
            screen.blit(cs, (WIN_W // 2 - cs.get_width() // 2, cy))
            cy += 55

            h = f_small.render("Share this code with a friend", True, TXT_DIM)
            screen.blit(h, (WIN_W // 2 - h.get_width() // 2, cy))
            cy += 50

            bb = pygame.Rect(WIN_W // 2 - 70, cy, 140, 36)
            if _draw_button(screen, f_btn, "Cancel", bb, mx, my, clicked):
                cancel_waiting()

        # ── Error bar ────────────────────────────────────────────────

        if error_ttl > 0:
            error_ttl -= 1
            bar = pygame.Rect(0, WIN_H - 38, WIN_W, 38)
            pygame.draw.rect(screen, ERR_BG, bar)
            es = f_item.render(error_msg, True, ERR_CLR)
            screen.blit(es, (WIN_W // 2 - es.get_width() // 2, WIN_H - 32))

        pygame.display.flip()
        clock.tick(60)

    # ── Exit ─────────────────────────────────────────────────────────────

    if result is None:
        # User closed the window
        if net is not None:
            net.disconnect()
        pygame.quit()
        return None, None

    # Game is starting — leave pygame alive for the game display
    return result, net


# ── Standalone runner ────────────────────────────────────────────────────────

# ── Game dispatch ────────────────────────────────────────────────────────────
# Maps registry game names to their online entry-point functions.
# Each function has the signature: run_online(screen, net, my_player, state).

_ONLINE_DISPATCH: dict[str, callable] = {}


def _load_dispatch():
    """Lazily populate the dispatch table so Pygame imports stay deferred."""
    if _ONLINE_DISPATCH:
        return
    from games.abalone_display import run_online as abalone_online
    from games.amazons_display import run_online as amazons_online
    from games.arimaa_display import run_online as arimaa_online
    from games.bagh_chal_display import run_online as bagh_chal_online
    from games.bao_display import run_online as bao_online
    from games.bashni_display import run_online as bashni_online
    from games.entrapment_display import run_online as entrapment_online
    from games.havannah_display import run_online as havannah_online
    from games.hive_display import run_online as hive_online
    from games.hnefatafl_display import run_online as hnefatafl_online
    from games.shobu_display import run_online as shobu_online
    from games.tumbleweed_display import run_online as tumbleweed_online
    from games.yinsh_display import run_online as yinsh_online
    _ONLINE_DISPATCH["Abalone"] = abalone_online
    _ONLINE_DISPATCH["Amazons"] = amazons_online
    _ONLINE_DISPATCH["Arimaa"] = arimaa_online
    _ONLINE_DISPATCH["BaghChal"] = bagh_chal_online
    _ONLINE_DISPATCH["Bao"] = bao_online
    _ONLINE_DISPATCH["Bashni"] = bashni_online
    _ONLINE_DISPATCH["Entrapment"] = entrapment_online
    _ONLINE_DISPATCH["Havannah"] = havannah_online
    _ONLINE_DISPATCH["Hive"] = hive_online
    _ONLINE_DISPATCH["Hnefatafl"] = hnefatafl_online
    _ONLINE_DISPATCH["Shobu"] = shobu_online
    _ONLINE_DISPATCH["Tumbleweed"] = tumbleweed_online
    _ONLINE_DISPATCH["YINSH"] = yinsh_online


def launch_game(game_msg: dict, net):
    """Dispatch to the correct game's online display after lobby handoff.

    Falls back to an "unsupported" message if the game has no online mode yet.
    """
    _load_dispatch()
    game_name = game_msg["game"]
    screen = pygame.display.get_surface()

    run_fn = _ONLINE_DISPATCH.get(game_name)
    if run_fn is not None:
        run_fn(screen, net, game_msg["your_player"], game_msg["state"])
    else:
        # Placeholder for games that don't have an online display yet
        font = pygame.font.SysFont("arial", 22)
        if screen is not None:
            screen.fill((34, 32, 36))
            msg = font.render(
                f"{game_name} online mode not yet available",
                True, (215, 215, 215),
            )
            screen.blit(msg, (screen.get_width() // 2 - msg.get_width() // 2,
                              screen.get_height() // 2 - msg.get_height() // 2))
            hint = pygame.font.SysFont("arial", 14).render(
                "Close the window to exit", True, (130, 130, 130),
            )
            screen.blit(hint, (screen.get_width() // 2 - hint.get_width() // 2,
                               screen.get_height() // 2 + 30))
            pygame.display.flip()
            waiting = True
            while waiting:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        waiting = False
                pygame.time.wait(50)

    net.disconnect()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws"
    game_msg, network = run_lobby(url)
    if game_msg:
        launch_game(game_msg, network)
    else:
        print("Lobby closed.")
    pygame.quit()
