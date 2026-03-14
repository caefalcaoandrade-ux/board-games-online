"""Board Games Online -- main client application.

Run from the project root::

    python client/main.py                            # shows main menu
    python client/main.py ws://192.168.1.5:8000/ws   # skips straight to lobby

The application opens a main menu where you can host or join a game.
Hosting starts a local server and opens an ngrok tunnel automatically.
After each game you return to the lobby.  Close the window to exit.
"""

import sys
import os
import time
import threading
import atexit

# ── Path setup ────────────────────────────────────────────────────────────

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── Imports ───────────────────────────────────────────────────────────────

import pygame
from client.lobby import run_lobby, launch_game

# ── Constants ─────────────────────────────────────────────────────────────

_BG       = (34, 32, 36)
_BTN      = (55, 120, 200)
_BTN_HOV  = (75, 140, 220)
_BTN_DIS  = (55, 52, 60)
_BTN_HOST = (50, 140, 80)
_BTN_HOST_HOV = (65, 165, 95)
_TXT      = (215, 215, 215)
_TXT_DIM  = (130, 130, 130)
_TXT_BTN  = (240, 240, 240)
_INPUT_BG = (38, 34, 42)
_INPUT_BD = (75, 70, 85)
_INPUT_AC = (90, 150, 230)
_ERR_BG   = (60, 15, 15)
_ERR_CLR  = (225, 75, 65)
_OK_CLR   = (90, 210, 120)
_URL_CLR  = (120, 220, 255)
_GOLD     = (228, 192, 56)

WIN_W, WIN_H = 580, 400


# ── Cross-platform clipboard ─────────────────────────────────────────────


def _clipboard_get() -> str:
    """Get text from the system clipboard.  Returns '' on failure."""
    # pyperclip — cleanest cross-platform clipboard (uses native mechanisms)
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        pass
    # Fallback: tkinter (bundled with Python, works on most desktops)
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text
    except Exception:
        pass
    return ""


_sdl2 = None  # cached ctypes handle for SDL2 clipboard

def _clipboard_set(text: str) -> bool:
    """Put text onto the system clipboard.  Returns True on success."""
    global _sdl2
    # Primary: SDL2 clipboard via ctypes — same library Pygame uses.
    # This bypasses pygame.scrap (which hangs on Wayland) and works
    # on both X11 and Wayland without any external tools.
    try:
        if _sdl2 is None:
            import ctypes
            import ctypes.util
            path = (ctypes.util.find_library("SDL2")
                    or ctypes.util.find_library("SDL2-2.0"))
            _sdl2 = ctypes.CDLL(path or "libSDL2-2.0.so.0")
            _sdl2.SDL_SetClipboardText.argtypes = [ctypes.c_char_p]
            _sdl2.SDL_SetClipboardText.restype = ctypes.c_int
        if _sdl2.SDL_SetClipboardText(text.encode("utf-8")) == 0:
            print("[clipboard] copied via SDL2")
            return True
    except Exception as exc:
        print(f"[clipboard] SDL2 ctypes failed: {exc}")
    # Fallback: pyperclip (needs xclip/xsel/wl-copy installed)
    try:
        import pyperclip
        pyperclip.copy(text)
        print("[clipboard] copied via pyperclip")
        return True
    except Exception as exc:
        print(f"[clipboard] pyperclip failed: {exc}")
    print("[clipboard] all copy methods failed")
    return False


def _is_paste(ev) -> bool:
    """True if the event is Ctrl+V (Windows/Linux) or Cmd+V (Mac)."""
    if ev.type != pygame.KEYDOWN or ev.key != pygame.K_v:
        return False
    return bool(ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))


def _is_copy(ev) -> bool:
    """True if the event is Ctrl+C (Windows/Linux) or Cmd+C (Mac)."""
    if ev.type != pygame.KEYDOWN or ev.key != pygame.K_c:
        return False
    return bool(ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))


# ── Helpers ───────────────────────────────────────────────────────────────


def _try_connect(url, result_holder):
    """Background thread: try to open a WebSocket and report success/failure."""
    try:
        import websocket as ws_mod
        ws = ws_mod.create_connection(url, timeout=5)
        ws.close()
        result_holder["ok"] = True
    except Exception as exc:
        result_holder["error"] = str(exc)


def _draw_btn(screen, rect, label, font, mx, my, enabled=True):
    """Draw a button and return True if it was clicked this frame."""
    hover = enabled and rect.collidepoint(mx, my)
    bg = _BTN_DIS if not enabled else _BTN_HOV if hover else _BTN
    pygame.draw.rect(screen, bg, rect, border_radius=8)
    lbl = font.render(label, True, _TXT_BTN if enabled else _TXT_DIM)
    screen.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                      rect.centery - lbl.get_height() // 2))
    return hover


def _draw_error(screen, font, msg, ttl, win_w, win_h):
    """Draw an error bar at the bottom if ttl > 0."""
    if ttl > 0:
        bar = pygame.Rect(0, win_h - 40, win_w, 40)
        pygame.draw.rect(screen, _ERR_BG, bar)
        es = font.render(msg, True, _ERR_CLR)
        screen.blit(es, (win_w // 2 - es.get_width() // 2, win_h - 32))


# ── Screen 1: Main Menu ──────────────────────────────────────────────────


_BTN_BOT     = (130, 80, 170)
_BTN_BOT_HOV = (150, 100, 195)
_BTN_LOCAL     = (160, 120, 50)
_BTN_LOCAL_HOV = (185, 145, 65)


def _run_main_menu(screen, fonts):
    """Show four mode buttons.  Returns 'host'|'join'|'local'|'bot'|None."""
    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts

    bw, bh = 150, 46
    row1_y = 145
    row2_y = 270
    left_x  = WIN_W // 2 - bw - 10
    right_x = WIN_W // 2 + 10

    btn_host  = pygame.Rect(left_x,  row1_y, bw, bh)
    btn_join  = pygame.Rect(right_x, row1_y, bw, bh)
    btn_local = pygame.Rect(left_x,  row2_y, bw, bh)
    btn_bot   = pygame.Rect(right_x, row2_y, bw, bh)

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True

        screen.fill(_BG)

        # Title
        t = f_title.render("Board Games Online", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 30))

        s = f_small.render("Play abstract board games with a friend", True, _TXT_DIM)
        screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 66))

        # ── Online section ────────────────────────────────────────────
        section_y = 100
        pygame.draw.line(screen, (60, 58, 65),
                         (WIN_W // 2 - 180, section_y),
                         (WIN_W // 2 + 180, section_y))
        lbl = f_small.render("Online", True, (90, 88, 95))
        screen.blit(lbl, (WIN_W // 2 - lbl.get_width() // 2, section_y + 4))

        # Host button (green)
        h_hover = btn_host.collidepoint(mx, my)
        pygame.draw.rect(screen, _BTN_HOST_HOV if h_hover else _BTN_HOST,
                         btn_host, border_radius=8)
        hl = f_btn.render("Host Game", True, _TXT_BTN)
        screen.blit(hl, (btn_host.centerx - hl.get_width() // 2,
                         btn_host.centery - hl.get_height() // 2))

        # Join button (blue)
        j_hover = btn_join.collidepoint(mx, my)
        pygame.draw.rect(screen, _BTN_HOV if j_hover else _BTN,
                         btn_join, border_radius=8)
        jl = f_btn.render("Join Game", True, _TXT_BTN)
        screen.blit(jl, (btn_join.centerx - jl.get_width() // 2,
                         btn_join.centery - jl.get_height() // 2))

        # Descriptions
        hd = f_small.render("Start server & invite", True, _TXT_DIM)
        screen.blit(hd, (btn_host.centerx - hd.get_width() // 2, row1_y + bh + 4))
        jd = f_small.render("Connect to a friend", True, _TXT_DIM)
        screen.blit(jd, (btn_join.centerx - jd.get_width() // 2, row1_y + bh + 4))

        # ── Offline section ───────────────────────────────────────────
        section_y2 = 225
        pygame.draw.line(screen, (60, 58, 65),
                         (WIN_W // 2 - 180, section_y2),
                         (WIN_W // 2 + 180, section_y2))
        lbl2 = f_small.render("Offline", True, (90, 88, 95))
        screen.blit(lbl2, (WIN_W // 2 - lbl2.get_width() // 2, section_y2 + 4))

        # Local button (golden/olive)
        l_hover = btn_local.collidepoint(mx, my)
        pygame.draw.rect(screen, _BTN_LOCAL_HOV if l_hover else _BTN_LOCAL,
                         btn_local, border_radius=8)
        ll = f_btn.render("Play Locally", True, _TXT_BTN)
        screen.blit(ll, (btn_local.centerx - ll.get_width() // 2,
                         btn_local.centery - ll.get_height() // 2))

        # Bot button (purple)
        b_hover = btn_bot.collidepoint(mx, my)
        pygame.draw.rect(screen, _BTN_BOT_HOV if b_hover else _BTN_BOT,
                         btn_bot, border_radius=8)
        bl = f_btn.render("Play vs Bot", True, _TXT_BTN)
        screen.blit(bl, (btn_bot.centerx - bl.get_width() // 2,
                         btn_bot.centery - bl.get_height() // 2))

        # Descriptions
        ld = f_small.render("Hotseat for two", True, _TXT_DIM)
        screen.blit(ld, (btn_local.centerx - ld.get_width() // 2, row2_y + bh + 4))
        bd = f_small.render("vs computer AI", True, _TXT_DIM)
        screen.blit(bd, (btn_bot.centerx - bd.get_width() // 2, row2_y + bh + 4))

        # Footer
        ft = f_small.render("Esc to quit", True, (70, 68, 75))
        screen.blit(ft, (WIN_W // 2 - ft.get_width() // 2, WIN_H - 30))

        if clicked:
            if h_hover:
                return "host"
            if j_hover:
                return "join"
            if l_hover:
                return "local"
            if b_hover:
                return "bot"

        pygame.display.flip()
        clock.tick(60)


# ── Screen: Authtoken Input ──────────────────────────────────────────────


def _run_authtoken_screen(screen, fonts):
    """Ask user to paste their ngrok authtoken.  Returns True on save, None on back."""
    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts
    f_input = pygame.font.SysFont("courier", 20)

    token_text = ""
    input_active = True
    error_msg = ""
    error_ttl = 0

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return None
                if input_active:
                    if ev.key == pygame.K_BACKSPACE:
                        token_text = token_text[:-1]
                    elif ev.key == pygame.K_RETURN and token_text.strip():
                        from client.host import save_authtoken
                        try:
                            save_authtoken(token_text.strip())
                            return True
                        except Exception as exc:
                            error_msg = str(exc)
                            error_ttl = 300
                    elif _is_paste(ev):
                        pasted = _clipboard_get()
                        if pasted:
                            token_text += pasted
                    elif ev.unicode and ev.unicode.isprintable():
                        token_text += ev.unicode
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True

        screen.fill(_BG)

        # Title
        t = f_title.render("ngrok Setup", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 20))

        # Instructions
        lines = [
            "To host games online, you need a free ngrok account.",
            "1. Go to ngrok.com and sign up (free)",
            "2. Copy your authtoken from the dashboard",
            "3. Paste it below and click Save",
        ]
        y = 65
        for line in lines:
            s = f_small.render(line, True, _TXT_DIM)
            screen.blit(s, (WIN_W // 2 - s.get_width() // 2, y))
            y += 22

        # Label
        lbl = f_sub.render("Authtoken:", True, _TXT_DIM)
        screen.blit(lbl, (WIN_W // 2 - 230, 168))

        # Input
        ir = pygame.Rect(WIN_W // 2 - 230, 190, 460, 38)
        bd = _INPUT_AC if input_active else _INPUT_BD
        pygame.draw.rect(screen, _INPUT_BG, ir, border_radius=5)
        pygame.draw.rect(screen, bd, ir, 2, border_radius=5)

        url_surf = f_input.render(token_text, True, _TXT)
        text_area = ir.inflate(-16, 0)
        scroll_x = max(0, url_surf.get_width() - text_area.width)

        screen.set_clip(text_area)
        screen.blit(url_surf, (text_area.x - scroll_x, ir.y + 8))
        screen.set_clip(None)

        if input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
            vis_w = min(url_surf.get_width(), text_area.width)
            cx = text_area.x + vis_w + 1
            pygame.draw.line(screen, _TXT, (cx, ir.y + 8), (cx, ir.y + 30), 2)

        # Save button
        btn_save = pygame.Rect(WIN_W // 2 - 80, 248, 160, 40)
        can_save = len(token_text.strip()) > 0
        save_hover = _draw_btn(screen, btn_save, "Save", f_btn, mx, my, can_save)
        if clicked and save_hover and can_save:
            from client.host import save_authtoken
            try:
                save_authtoken(token_text.strip())
                return True
            except Exception as exc:
                error_msg = str(exc)
                error_ttl = 300

        # Back hint
        bk = f_small.render("Esc to go back", True, (70, 68, 75))
        screen.blit(bk, (WIN_W // 2 - bk.get_width() // 2, 300))

        if error_ttl > 0:
            error_ttl -= 1
        _draw_error(screen, f_small, error_msg, error_ttl, WIN_W, WIN_H)

        pygame.display.flip()
        clock.tick(60)


# ── Screen: Hosting in progress ──────────────────────────────────────────


def _run_hosting_screen(screen, fonts):
    """Start server + tunnel, show URL.  Returns (local_url, public_url) or None."""
    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts
    f_url = pygame.font.SysFont("courier", 18, bold=True)

    phase = "starting"   # starting -> ready | error
    public_url = None
    local_url = None
    error_msg = ""
    dots = 0
    start_result = {}

    # Start hosting in background thread
    def _do_start():
        try:
            from client.host import start_hosting, get_local_url
            url = start_hosting()
            start_result["public_url"] = url
            start_result["local_url"] = get_local_url()
        except Exception as exc:
            start_result["error"] = str(exc)

    t = threading.Thread(target=_do_start, daemon=True)
    t.start()

    copied_tick = 0   # frame counter for "Copied!" feedback (0 = not copied)
    url_box = None       # set during "ready" rendering; used for click detection
    url_selected = False
    copy_fail_tick = 0

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return None
                if url_selected and public_url and _is_copy(ev):
                    if _clipboard_set(public_url):
                        copied_tick = 120
                    else:
                        copy_fail_tick = 240
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True
                if url_box is not None:
                    url_selected = url_box.collidepoint(ev.pos)

        # Check background result
        if phase == "starting" and start_result:
            if "error" in start_result:
                phase = "error"
                error_msg = start_result["error"]
            else:
                phase = "ready"
                public_url = start_result["public_url"]
                local_url = start_result["local_url"]
                # Always print to terminal — guaranteed fallback
                print()
                print(f"  Share this URL: {public_url}")
                print()

        screen.fill(_BG)

        if phase == "starting":
            dots = (dots + 1) % 180
            dot_str = "." * ((dots // 30) % 4)
            t = f_title.render(f"Starting server{dot_str}", True, _TXT)
            screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 100))
            s = f_small.render("Setting up ngrok tunnel...", True, _TXT_DIM)
            screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 145))

        elif phase == "error":
            t = f_title.render("Hosting Failed", True, _ERR_CLR)
            screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 60))
            # Wrap error text
            words = error_msg.split()
            line = ""
            y = 110
            for w in words:
                test = line + (" " if line else "") + w
                if f_small.size(test)[0] > WIN_W - 60:
                    s = f_small.render(line, True, _TXT_DIM)
                    screen.blit(s, (30, y))
                    y += 20
                    line = w
                else:
                    line = test
            if line:
                s = f_small.render(line, True, _TXT_DIM)
                screen.blit(s, (30, y))

            btn_back = pygame.Rect(WIN_W // 2 - 80, 280, 160, 40)
            back_hover = _draw_btn(screen, btn_back, "Back", f_btn, mx, my)
            if clicked and back_hover:
                from client.host import stop_hosting
                stop_hosting()
                return None

        elif phase == "ready":
            t = f_title.render("Server Ready!", True, _OK_CLR)
            screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 30))

            s = f_sub.render("Share this URL with your friend:", True, _TXT_DIM)
            screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 75))

            # URL box — auto-size to fit the URL text
            us = f_url.render(public_url, True, _URL_CLR)
            url_text_w = us.get_width()
            # If the URL is wider than the window allows, use a smaller font
            max_box_w = WIN_W - 40  # 20px margin each side
            if url_text_w + 24 > max_box_w:
                us_small = pygame.font.SysFont("courier", 14, bold=True)
                us = us_small.render(public_url, True, _URL_CLR)
                url_text_w = us.get_width()
            box_w = min(max(url_text_w + 24, 300), max_box_w)
            url_box = pygame.Rect(WIN_W // 2 - box_w // 2, 105, box_w, 42)
            pygame.draw.rect(screen, _INPUT_BG, url_box, border_radius=6)
            pygame.draw.rect(screen, _URL_CLR, url_box, 2, border_radius=6)
            if url_selected:
                hl = us.get_rect(center=url_box.center).inflate(6, 2)
                pygame.draw.rect(screen, (30, 70, 140), hl)
            screen.blit(us, (url_box.centerx - us.get_width() // 2,
                             url_box.y + (42 - us.get_height()) // 2))

            # Copy button
            if copied_tick > 0:
                copied_tick -= 1
            if copy_fail_tick > 0:
                copy_fail_tick -= 1

            if copy_fail_tick > 0:
                copy_label = "Copy failed — URL printed to terminal"
            elif copied_tick > 0:
                copy_label = "Copied!"
            else:
                copy_label = "Copy to Clipboard"

            cl = f_small.render(copy_label, True, _TXT_BTN)
            btn_w = max(180, cl.get_width() + 24)
            btn_copy = pygame.Rect(WIN_W // 2 - btn_w // 2, 165, btn_w, 36)
            copy_hover = btn_copy.collidepoint(mx, my)

            if copy_fail_tick > 0:
                copy_bg = _ERR_CLR
            elif copied_tick > 0:
                copy_bg = _OK_CLR
            elif copy_hover:
                copy_bg = _BTN_HOV
            else:
                copy_bg = _BTN
            pygame.draw.rect(screen, copy_bg, btn_copy, border_radius=6)
            screen.blit(cl, (btn_copy.centerx - cl.get_width() // 2,
                             btn_copy.centery - cl.get_height() // 2))

            if clicked and copy_hover and copied_tick == 0 and copy_fail_tick == 0:
                if _clipboard_set(public_url):
                    copied_tick = 120
                else:
                    copy_fail_tick = 240

            # Info
            info = f_small.render(
                "Your friend pastes this URL in their app to join.",
                True, _TXT_DIM)
            screen.blit(info, (WIN_W // 2 - info.get_width() // 2, 215))

            # Continue button
            btn_go = pygame.Rect(WIN_W // 2 - 100, 260, 200, 48)
            go_hover = btn_go.collidepoint(mx, my)
            go_bg = _BTN_HOST_HOV if go_hover else _BTN_HOST
            pygame.draw.rect(screen, go_bg, btn_go, border_radius=8)
            gl = f_btn.render("Continue to Lobby", True, _TXT_BTN)
            screen.blit(gl, (btn_go.centerx - gl.get_width() // 2,
                             btn_go.centery - gl.get_height() // 2))
            if clicked and go_hover:
                return (local_url, public_url)

            # Footer
            ft = f_small.render("Esc to cancel and stop server", True, (70, 68, 75))
            screen.blit(ft, (WIN_W // 2 - ft.get_width() // 2, WIN_H - 28))

        pygame.display.flip()
        clock.tick(60)


# ── Screen: Local Game Selection ─────────────────────────────────────────


def _run_local_setup(screen, fonts):
    """Game selection for local hotseat play.  Returns game_name or None."""
    from games import list_games

    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts
    games = list_games()
    selected_game = None

    _ITEM_BG  = (52, 48, 58)
    _ITEM_HOV = (62, 58, 68)
    _ITEM_SEL = (45, 100, 180)

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True

        screen.fill(_BG)

        t = f_title.render("Play Locally", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 20))

        sub = f_small.render("Two players, same computer", True, _TXT_DIM)
        screen.blit(sub, (WIN_W // 2 - sub.get_width() // 2, 54))

        # Game list — centred
        lx = WIN_W // 2 - 130
        ly = 85
        h = f_sub.render("Select a Game", True, _TXT_DIM)
        screen.blit(h, (WIN_W // 2 - h.get_width() // 2, ly))
        ly += 28

        for gname in games:
            r = pygame.Rect(lx, ly, 260, 30)
            hov = r.collidepoint(mx, my)
            if gname == selected_game:
                pygame.draw.rect(screen, _ITEM_SEL, r, border_radius=4)
            elif hov:
                pygame.draw.rect(screen, _ITEM_HOV, r, border_radius=4)
            else:
                pygame.draw.rect(screen, _ITEM_BG, r, border_radius=4)
            screen.blit(f_small.render(gname, True, _TXT), (lx + 10, ly + 7))
            if hov and clicked:
                selected_game = gname
            ly += 34

        # Start button
        btn_start = pygame.Rect(WIN_W // 2 - 80, ly + 10, 160, 44)
        can_start = selected_game is not None
        start_hover = btn_start.collidepoint(mx, my) and can_start
        sbg = (_BTN_LOCAL_HOV if start_hover
               else (_BTN_LOCAL if can_start else _BTN_DIS))
        pygame.draw.rect(screen, sbg, btn_start, border_radius=8)
        sl = f_btn.render("Start Game", True,
                          _TXT_BTN if can_start else _TXT_DIM)
        screen.blit(sl, (btn_start.centerx - sl.get_width() // 2,
                         btn_start.centery - sl.get_height() // 2))
        if clicked and start_hover:
            return selected_game

        bk = f_small.render("Esc to go back", True, (70, 68, 75))
        screen.blit(bk, (WIN_W // 2 - bk.get_width() // 2, WIN_H - 28))

        pygame.display.flip()
        clock.tick(60)


def _launch_local_game(game_name):
    """Launch a game in standalone hotseat mode.

    Calls the display module's main() function.  When it exits
    (via pygame.quit + sys.exit), we catch SystemExit and
    reinitialise Pygame so the main menu can resume.
    """
    mod_name = game_name.lower() + "_display"
    mod = __import__(f"games.{mod_name}", fromlist=["main"])
    try:
        mod.main()
    except SystemExit:
        pass
    # Reinitialise Pygame for the menu
    if not pygame.get_init():
        pygame.init()


# ── Screen: Bot Setup (game + difficulty selection) ──────────────────────


def _run_bot_setup(screen, fonts):
    """Game and difficulty selection for single-player vs bot.

    Returns (game_name, difficulty) or None on back/quit.
    """
    from games import list_games

    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts

    games = list_games()
    selected_game = None
    selected_diff = "medium"
    diffs = ["easy", "medium", "hard"]
    diff_labels = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
    diff_colors = {
        "easy":   (90, 180, 90),
        "medium": (200, 170, 50),
        "hard":   (200, 70, 70),
    }

    _ITEM_BG  = (52, 48, 58)
    _ITEM_HOV = (62, 58, 68)
    _ITEM_SEL = (45, 100, 180)

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True

        screen.fill(_BG)

        # Title
        t = f_title.render("Play vs Bot", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 16))

        # ── Left column: game list ────────────────────────────────────
        lx, ly = 24, 55
        h = f_sub.render("Select a Game", True, _TXT_DIM)
        screen.blit(h, (lx, ly))
        ly += 28

        for gname in games:
            r = pygame.Rect(lx, ly, 250, 30)
            hov = r.collidepoint(mx, my)
            if gname == selected_game:
                pygame.draw.rect(screen, _ITEM_SEL, r, border_radius=4)
            elif hov:
                pygame.draw.rect(screen, _ITEM_HOV, r, border_radius=4)
            else:
                pygame.draw.rect(screen, _ITEM_BG, r, border_radius=4)
            screen.blit(f_small.render(gname, True, _TXT), (lx + 10, ly + 7))
            if hov and clicked:
                selected_game = gname
            ly += 34

        # ── Right column: difficulty ──────────────────────────────────
        rx, ry = 310, 55
        screen.blit(f_sub.render("Difficulty", True, _TXT_DIM), (rx, ry))
        ry += 28

        for d in diffs:
            r = pygame.Rect(rx, ry, 240, 36)
            hov = r.collidepoint(mx, my)
            if d == selected_diff:
                pygame.draw.rect(screen, _ITEM_SEL, r, border_radius=4)
            elif hov:
                pygame.draw.rect(screen, _ITEM_HOV, r, border_radius=4)
            else:
                pygame.draw.rect(screen, _ITEM_BG, r, border_radius=4)
            lbl = f_btn.render(diff_labels[d], True, diff_colors[d])
            screen.blit(lbl, (rx + 14, ry + 8))
            if hov and clicked:
                selected_diff = d
            ry += 42

        # Difficulty description
        ry += 6
        desc = {
            "easy": "Fast, makes mistakes",
            "medium": "Moderate thinking time",
            "hard": "Thinks several seconds",
        }
        dt = f_small.render(desc[selected_diff], True, _TXT_DIM)
        screen.blit(dt, (rx, ry))

        # ── Start button ──────────────────────────────────────────────
        btn_start = pygame.Rect(rx, ry + 40, 240, 44)
        can_start = selected_game is not None
        start_hover = btn_start.collidepoint(mx, my) and can_start
        sbg = _BTN_HOST_HOV if start_hover else (_BTN_HOST if can_start else _BTN_DIS)
        pygame.draw.rect(screen, sbg, btn_start, border_radius=8)
        sl = f_btn.render("Start Game", True,
                          _TXT_BTN if can_start else _TXT_DIM)
        screen.blit(sl, (btn_start.centerx - sl.get_width() // 2,
                         btn_start.centery - sl.get_height() // 2))
        if clicked and start_hover:
            return (selected_game, selected_diff)

        # Back hint
        bk = f_small.render("Esc to go back", True, (70, 68, 75))
        screen.blit(bk, (WIN_W // 2 - bk.get_width() // 2, WIN_H - 28))

        pygame.display.flip()
        clock.tick(60)


# ── Screen: Join (URL input) ─────────────────────────────────────────────


def _run_join_screen(screen, fonts):
    """URL input screen.  Returns a validated URL string, or None."""
    clock = pygame.time.Clock()
    f_title, f_sub, f_btn, f_small = fonts
    f_input = pygame.font.SysFont("courier", 20)

    url_text = ""
    input_active = True
    error_msg = ""
    error_ttl = 0
    connecting = False
    connect_result = {}

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True
                ir = pygame.Rect(WIN_W // 2 - 230, 140, 460, 38)
                input_active = ir.collidepoint(mx, my)
            if ev.type == pygame.KEYDOWN and not connecting:
                if ev.key == pygame.K_ESCAPE:
                    return "back"
                if input_active:
                    if ev.key == pygame.K_BACKSPACE:
                        url_text = url_text[:-1]
                        error_ttl = 0
                    elif ev.key == pygame.K_RETURN and url_text.strip():
                        connecting = True
                        connect_result = {}
                        error_ttl = 0
                        threading.Thread(
                            target=_try_connect,
                            args=(url_text.strip(), connect_result),
                            daemon=True,
                        ).start()
                    elif _is_paste(ev):
                        pasted = _clipboard_get()
                        if pasted:
                            url_text += pasted
                    elif ev.unicode and ev.unicode.isprintable():
                        url_text += ev.unicode

        # Check connection result
        if connecting and connect_result:
            connecting = False
            if connect_result.get("ok"):
                return url_text.strip()
            else:
                err = connect_result.get("error", "Unknown error")
                if "getaddrinfo failed" in err or "not known" in err:
                    err = "Server not found — check the address"
                elif "Connection refused" in err:
                    err = "Connection refused — is the host running?"
                elif "timed out" in err.lower():
                    err = "Connection timed out — check address"
                error_msg = err
                error_ttl = 360

        screen.fill(_BG)

        t = f_title.render("Join Game", True, _TXT)
        screen.blit(t, (WIN_W // 2 - t.get_width() // 2, 30))

        s = f_sub.render("Paste the URL your friend shared with you:", True, _TXT_DIM)
        screen.blit(s, (WIN_W // 2 - s.get_width() // 2, 75))

        # Label
        lbl = f_sub.render("Server URL:", True, _TXT_DIM)
        screen.blit(lbl, (WIN_W // 2 - 230, 118))

        # Input
        ir = pygame.Rect(WIN_W // 2 - 230, 140, 460, 38)
        bd = _INPUT_AC if input_active else _INPUT_BD
        pygame.draw.rect(screen, _INPUT_BG, ir, border_radius=5)
        pygame.draw.rect(screen, bd, ir, 2, border_radius=5)

        url_surf = f_input.render(url_text, True, _TXT)
        text_area = ir.inflate(-16, 0)
        scroll_x = max(0, url_surf.get_width() - text_area.width)

        screen.set_clip(text_area)
        screen.blit(url_surf, (text_area.x - scroll_x, ir.y + 8))
        screen.set_clip(None)

        if input_active and not connecting and (pygame.time.get_ticks() // 500) % 2 == 0:
            vis_w = min(url_surf.get_width(), text_area.width)
            cx = text_area.x + vis_w + 1
            pygame.draw.line(screen, _TXT, (cx, ir.y + 8), (cx, ir.y + 30), 2)

        # Connect button
        btn_conn = pygame.Rect(WIN_W // 2 - 80, 200, 160, 40)
        can_click = len(url_text.strip()) > 0 and not connecting
        conn_label = "Connecting..." if connecting else "Connect"
        conn_hover = _draw_btn(screen, btn_conn, conn_label, f_btn, mx, my, can_click)
        if clicked and conn_hover and can_click:
            connecting = True
            connect_result = {}
            error_ttl = 0
            threading.Thread(
                target=_try_connect,
                args=(url_text.strip(), connect_result),
                daemon=True,
            ).start()

        # Status
        if connecting:
            st = f_small.render("Connecting...", True, _TXT_DIM)
            screen.blit(st, (WIN_W // 2 - st.get_width() // 2, 250))

        # Back hint
        bk = f_small.render("Esc to go back", True, (70, 68, 75))
        screen.blit(bk, (WIN_W // 2 - bk.get_width() // 2, 300))

        if error_ttl > 0:
            error_ttl -= 1
        _draw_error(screen, f_small, error_msg, error_ttl, WIN_W, WIN_H)

        pygame.display.flip()
        clock.tick(60)


# ── Main loop ─────────────────────────────────────────────────────────────


def main():
    is_host = False

    if len(sys.argv) > 1:
        # CLI argument provided — skip menu, go straight to lobby
        server_url = sys.argv[1]
        print()
        print("  Board Games Online")
        print(f"  Server:  {server_url}")
        print()
    else:
        # Show the main menu
        pygame.init()
        screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("Board Games Online")

        fonts = (
            pygame.font.SysFont("arial", 24, bold=True),  # title
            pygame.font.SysFont("arial", 16),              # sub
            pygame.font.SysFont("arial", 17, bold=True),   # btn
            pygame.font.SysFont("arial", 14),              # small
        )

        server_url = None

        while server_url is None:
            choice = _run_main_menu(screen, fonts)

            if choice is None:
                pygame.quit()
                return

            elif choice == "host":
                # Check authtoken
                from client.host import needs_authtoken
                if needs_authtoken():
                    result = _run_authtoken_screen(screen, fonts)
                    if result is None:
                        continue  # back to menu

                # Start hosting
                result = _run_hosting_screen(screen, fonts)
                if result is None:
                    from client.host import stop_hosting
                    stop_hosting()
                    continue  # back to menu

                local_url, public_url = result
                server_url = local_url
                is_host = True

            elif choice == "local":
                game_name = _run_local_setup(screen, fonts)
                if game_name is None:
                    continue  # back to menu
                _launch_local_game(game_name)
                screen = pygame.display.set_mode((WIN_W, WIN_H))
                pygame.display.set_caption("Board Games Online")
                continue

            elif choice == "bot":
                result = _run_bot_setup(screen, fonts)
                if result is None:
                    continue  # back to menu
                game_name, difficulty = result
                from client.bot_game import run_vs_bot
                run_vs_bot(screen, game_name, difficulty)
                screen = pygame.display.set_mode((WIN_W, WIN_H))
                pygame.display.set_caption("Board Games Online")
                continue

            elif choice == "join":
                result = _run_join_screen(screen, fonts)
                if result is None:
                    pygame.quit()
                    return
                if result == "back":
                    continue  # back to menu
                server_url = result

    # Register cleanup for hosting
    if is_host:
        def _cleanup():
            try:
                from client.host import stop_hosting
                stop_hosting()
            except Exception:
                pass
        atexit.register(_cleanup)

    # ── Game loop ─────────────────────────────────────────────────────
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
        if is_host:
            try:
                from client.host import stop_hosting
                stop_hosting()
            except Exception:
                pass
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
