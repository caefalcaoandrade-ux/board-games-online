"""Board Games Online -- main client application.

Run from the project root::

    python client/main.py                            # shows connect screen
    python client/main.py ws://192.168.1.5:8000/ws   # skips straight to lobby

The application opens a lobby where you can browse available games, create
or join rooms, and play against other connected players.  After each game
you return to the lobby automatically.  Close the window to exit.
"""

import sys
import os
import time
import threading

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

DEFAULT_URL = "ws://localhost:8000/ws"

# Palette (matches lobby)
_BG       = (34, 32, 36)
_BTN      = (55, 120, 200)
_BTN_HOV  = (75, 140, 220)
_BTN_DIS  = (55, 52, 60)
_TXT      = (215, 215, 215)
_TXT_DIM  = (130, 130, 130)
_TXT_BTN  = (240, 240, 240)
_INPUT_BG = (38, 34, 42)
_INPUT_BD = (75, 70, 85)
_INPUT_AC = (90, 150, 230)
_ERR_BG   = (60, 15, 15)
_ERR_CLR  = (225, 75, 65)
_OK_CLR   = (90, 210, 120)

WIN_W, WIN_H = 520, 320


# ── Connect screen ────────────────────────────────────────────────────────

def _try_connect(url, result_holder):
    """Background thread: try to open a WebSocket and report success/failure."""
    try:
        import websocket
        ws = websocket.create_connection(url, timeout=4)
        ws.close()
        result_holder["ok"] = True
    except Exception as exc:
        result_holder["error"] = str(exc)


def run_connect_screen():
    """Show a Pygame screen where the user can enter a server URL.

    Returns the validated URL string, or None if the user closed the window.
    """
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Board Games Online")
    clock = pygame.time.Clock()

    f_title = pygame.font.SysFont("arial", 24, bold=True)
    f_label = pygame.font.SysFont("arial", 16)
    f_input = pygame.font.SysFont("courier", 20)
    f_btn   = pygame.font.SysFont("arial", 17, bold=True)
    f_small = pygame.font.SysFont("arial", 14)
    f_err   = pygame.font.SysFont("arial", 14)

    url_text = DEFAULT_URL
    input_active = True
    cursor_visible = True

    error_msg = ""
    error_ttl = 0       # frames remaining
    status_msg = ""     # "Connecting..." or "Connected!"
    status_clr = _TXT_DIM

    connecting = False
    connect_result = {}
    connect_thread = None

    running = True
    result_url = None

    while running:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True
                # Click inside input field → activate
                input_rect = pygame.Rect(WIN_W // 2 - 210, 140, 420, 38)
                if input_rect.collidepoint(mx, my):
                    input_active = True
                else:
                    input_active = False

            elif ev.type == pygame.KEYDOWN and not connecting:
                if input_active:
                    if ev.key == pygame.K_BACKSPACE:
                        url_text = url_text[:-1]
                        error_ttl = 0
                    elif ev.key == pygame.K_RETURN:
                        if url_text.strip():
                            # Start connection attempt
                            connecting = True
                            connect_result = {}
                            status_msg = "Connecting..."
                            status_clr = _TXT_DIM
                            error_ttl = 0
                            connect_thread = threading.Thread(
                                target=_try_connect,
                                args=(url_text.strip(), connect_result),
                                daemon=True,
                            )
                            connect_thread.start()
                    elif ev.key == pygame.K_ESCAPE:
                        input_active = False
                    elif ev.key in (pygame.K_v,) and (ev.mod & pygame.KMOD_CTRL):
                        # Ctrl+V paste
                        try:
                            clip = pygame.scrap.get(pygame.SCRAP_TEXT)
                            if clip:
                                pasted = clip.decode("utf-8", errors="ignore")
                                pasted = pasted.rstrip("\x00")
                                url_text += pasted
                        except Exception:
                            pass
                    elif ev.unicode and ev.unicode.isprintable():
                        url_text += ev.unicode

        # ── Check connection result ───────────────────────────────────
        if connecting and connect_result:
            connecting = False
            if connect_result.get("ok"):
                status_msg = "Connected!"
                status_clr = _OK_CLR
                result_url = url_text.strip()
                running = False
            else:
                err = connect_result.get("error", "Unknown error")
                # Shorten common long error messages
                if "getaddrinfo failed" in err or "Name or service not known" in err:
                    err = "Server not found — check the address"
                elif "Connection refused" in err:
                    err = "Connection refused — is the server running?"
                elif "timed out" in err.lower():
                    err = "Connection timed out — check address and firewall"
                error_msg = err
                error_ttl = 360  # ~6 seconds at 60 fps
                status_msg = ""

        # ── Draw ──────────────────────────────────────────────────────
        screen.fill(_BG)

        # Title
        t = f_title.render("Board Games Online", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 28))

        # Subtitle
        s = f_small.render("Enter the server address to connect", True, _TXT_DIM)
        screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 64))

        # Label
        lbl = f_label.render("Server URL:", True, _TXT_DIM)
        screen.blit(lbl, (WIN_W // 2 - 210, 118))

        # Input field
        ir = pygame.Rect(WIN_W // 2 - 210, 140, 420, 38)
        bd = _INPUT_AC if input_active else _INPUT_BD
        pygame.draw.rect(screen, _INPUT_BG, ir, border_radius=5)
        pygame.draw.rect(screen, bd, ir, 2, border_radius=5)

        # Render URL text (scroll if too wide)
        url_surf = f_input.render(url_text, True, _TXT)
        text_area = ir.inflate(-16, 0)
        clip_rect = pygame.Rect(0, 0, text_area.width, url_surf.get_height())
        if url_surf.get_width() > text_area.width:
            clip_rect.x = url_surf.get_width() - text_area.width
        screen.blit(url_surf, (text_area.x - clip_rect.x, ir.y + 8),
                    area=clip_rect)

        # Cursor
        if input_active and not connecting:
            if (pygame.time.get_ticks() // 500) % 2 == 0:
                visible_w = min(url_surf.get_width(), text_area.width)
                cx = text_area.x + visible_w + 1
                pygame.draw.line(screen, _TXT, (cx, ir.y + 8),
                                 (cx, ir.y + 30), 2)

        # Connect button
        btn = pygame.Rect(WIN_W // 2 - 80, 200, 160, 40)
        can_click = len(url_text.strip()) > 0 and not connecting
        hover = can_click and btn.collidepoint(mx, my)
        bg = _BTN_DIS if not can_click else _BTN_HOV if hover else _BTN
        pygame.draw.rect(screen, bg, btn, border_radius=6)
        btn_label = "Connecting..." if connecting else "Connect"
        bl = f_btn.render(btn_label, True, _TXT_BTN if can_click else _TXT_DIM)
        screen.blit(bl, (btn.centerx - bl.get_width() // 2,
                         btn.centery - bl.get_height() // 2))
        if hover and clicked and can_click:
            connecting = True
            connect_result = {}
            status_msg = "Connecting..."
            status_clr = _TXT_DIM
            error_ttl = 0
            connect_thread = threading.Thread(
                target=_try_connect,
                args=(url_text.strip(), connect_result),
                daemon=True,
            )
            connect_thread.start()

        # Status text (below button)
        if status_msg:
            st = f_small.render(status_msg, True, status_clr)
            screen.blit(st, (WIN_W // 2 - st.get_width() // 2, 250))

        # Error bar at bottom
        if error_ttl > 0:
            error_ttl -= 1
            bar = pygame.Rect(0, WIN_H - 40, WIN_W, 40)
            pygame.draw.rect(screen, _ERR_BG, bar)
            es = f_err.render(error_msg, True, _ERR_CLR)
            screen.blit(es, (WIN_W // 2 - es.get_width() // 2, WIN_H - 32))

        # Hint at bottom (when no error)
        if error_ttl <= 0:
            h = f_small.render("Tip: ask the host for their server address",
                               True, (80, 78, 85))
            screen.blit(h, (WIN_W // 2 - h.get_width() // 2, WIN_H - 28))

        pygame.display.flip()
        clock.tick(60)

    if result_url is None:
        pygame.quit()
    return result_url


# ── Main loop ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        # CLI argument provided — skip connect screen, go straight to lobby.
        server_url = sys.argv[1]
        print()
        print("  Board Games Online")
        print(f"  Server:  {server_url}")
        print()
    else:
        # No argument — show the connect screen.
        server_url = run_connect_screen()
        if server_url is None:
            return

    try:
        while True:
            game_msg, net = run_lobby(server_url)

            if game_msg is None:
                break

            launch_game(game_msg, net)

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
