"""Rules file viewer — shared utility for game selection screens.

Provides functions to locate and display game rules from the rules/
folder, rendered as scrollable formatted text in a Pygame overlay.
"""

import os
import sys

import pygame

# ── Path helpers ──────────────────────────────────────────────────────────

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_HELP_CLR = (100, 140, 200)
_HELP_HOV = (130, 170, 230)
HELP_SZ   = 18

_BG      = (34, 32, 36)
_TXT     = (215, 215, 215)
_TXT_DIM = (130, 130, 130)


def rules_dir() -> str:
    """Return the path to the rules/ folder, handling PyInstaller bundles."""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "rules")
    return os.path.join(_project_root, "rules")


def rules_file_for(game_name: str) -> str | None:
    """Return the path to a game's rules markdown file, or None."""
    name_map = {
        "BaghChal": "bagh_chal_logic",
        "YINSH": "yinsh_logic",
    }
    base = name_map.get(game_name, game_name.lower() + "_logic")
    path = os.path.join(rules_dir(), base + ".md")
    return path if os.path.isfile(path) else None


def draw_help_icon(screen, font, x, y, mx, my, clip_rect=None):
    """Draw a small '?' circle icon. Returns True if the mouse hovers it."""
    cx = x + HELP_SZ // 2
    cy = y + HELP_SZ // 2
    r = HELP_SZ // 2
    hov = (mx - cx) ** 2 + (my - cy) ** 2 <= r * r
    if clip_rect and not clip_rect.collidepoint(mx, my):
        hov = False
    color = _HELP_HOV if hov else _HELP_CLR
    pygame.draw.circle(screen, color, (cx, cy), r)
    q = font.render("?", True, (255, 255, 255))
    screen.blit(q, (cx - q.get_width() // 2, cy - q.get_height() // 2))
    return hov


def run_rules_viewer(screen, fonts, game_name):
    """Show a scrollable rules viewer for *game_name*.

    *fonts* is a 4-tuple ``(f_title, f_sub, f_btn, f_small)`` — any
    game-selection screen's font tuple works.

    Returns when the user presses Escape or clicks Close.
    """
    clock = pygame.time.Clock()
    f_title, _, f_btn, f_small = fonts
    f_body = pygame.font.SysFont("arial", 15)
    f_heading = pygame.font.SysFont("arial", 17, bold=True)
    f_h1 = pygame.font.SysFont("arial", 20, bold=True)

    win_w, win_h = screen.get_size()

    # Load rules text
    path = rules_file_for(game_name)
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            raw = "Could not read rules file."
    else:
        raw = "No rules available for this game."

    # Parse markdown into rendered lines
    margin = 30
    max_w = win_w - 2 * margin - 10
    rendered = []  # (surface | None, gap_if_none)

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            rendered.append((None, 8))
            continue
        if stripped.startswith("# "):
            font, text = f_h1, stripped[2:]
        elif stripped.startswith("## "):
            font, text = f_heading, stripped[3:]
        elif stripped.startswith("### "):
            font, text = f_heading, stripped[4:]
        elif stripped.startswith("| ") or stripped.startswith("|-"):
            font, text = f_small, stripped
        else:
            font, text = f_body, stripped

        # Word-wrap
        words = text.split()
        cur = ""
        for word in words:
            test = (cur + " " + word).strip()
            if font.size(test)[0] > max_w and cur:
                rendered.append((font.render(cur, True, _TXT), 0))
                cur = word
            else:
                cur = test
        if cur:
            rendered.append((font.render(cur, True, _TXT), 0))

    line_h = 20
    total_h = sum(line_h if surf else gap for surf, gap in rendered)
    content_top = 40
    content_bot = win_h - 40
    max_scroll = max(0, total_h - (content_bot - content_top))
    scroll = 0

    # Button helper (local, avoids importing from main)
    def _btn(rect, label, mx, my):
        hov = rect.collidepoint(mx, my)
        bg = (75, 140, 220) if hov else (55, 120, 200)
        pygame.draw.rect(screen, bg, rect, border_radius=8)
        lbl = f_btn.render(label, True, (240, 240, 240))
        screen.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                          rect.centery - lbl.get_height() // 2))
        return hov

    while True:
        mx, my = pygame.mouse.get_pos()
        clicked = False

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicked = True
            if ev.type == pygame.MOUSEWHEEL:
                scroll = max(0, min(max_scroll, scroll - ev.y * 30))

        screen.fill(_BG)

        title = f_title.render(f"{game_name} \u2014 Rules", True, _TXT)
        screen.blit(title, (win_w // 2 - title.get_width() // 2, 8))

        clip = pygame.Rect(margin - 5, content_top,
                           win_w - 2 * margin + 10,
                           content_bot - content_top)
        screen.set_clip(clip)
        y = content_top - scroll
        for surf, gap in rendered:
            if surf is None:
                y += gap
            else:
                if content_top - line_h < y < content_bot + line_h:
                    screen.blit(surf, (margin, y))
                y += line_h
        screen.set_clip(None)

        # Scroll indicators
        if scroll > 0:
            a = f_small.render("\u25b2", True, _TXT_DIM)
            screen.blit(a, (win_w // 2 - a.get_width() // 2, content_top - 2))
        if scroll < max_scroll:
            a = f_small.render("\u25bc", True, _TXT_DIM)
            screen.blit(a, (win_w // 2 - a.get_width() // 2, content_bot))

        btn_close = pygame.Rect(win_w // 2 - 50, win_h - 36, 100, 30)
        if clicked and _btn(btn_close, "Close", mx, my):
            return
        _btn(btn_close, "Close", mx, my)

        esc = f_small.render("Esc to close", True, (70, 68, 75))
        screen.blit(esc, (win_w - esc.get_width() - 10, win_h - 30))

        pygame.display.flip()
        clock.tick(60)
