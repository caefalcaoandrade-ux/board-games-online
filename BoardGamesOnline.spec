# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for Board Games Online.
#
# Build with:
#     pyinstaller BoardGamesOnline.spec
#
# This produces:  dist/BoardGamesOnline.exe  (single-file console executable)
#
# To switch to windowed mode (no terminal) once everything works, change
# console=True to console=False in the EXE section below.

import os
import sys
import certifi

# ── Analysis ──────────────────────────────────────────────────────────────

a = Analysis(
    ['build_exe.py'],

    pathex=['.'],

    binaries=[],

    # Data files bundled into the executable.
    datas=[
        ('games', 'games'),
        ('client', 'client'),
        ('server', 'server'),
        ('rules', 'rules'),
        # Bundle certifi's CA certificate file so wss:// connections work
        # inside the PyInstaller .exe (the OS cert store is not available).
        (certifi.where(), 'certifi'),
        # Note: pyngrok downloads the ngrok binary at runtime via its
        # installer module.  No ngrok binary needs to be bundled here.
    ],

    hiddenimports=[
        # Game registry and base class
        'games',
        'games.base_game',
        'games._suppress',

        # Logic modules
        'games.abalone_logic',
        'games.amazons_logic',
        'games.arimaa_logic',
        'games.bagh_chal_logic',
        'games.bao_logic',
        'games.bashni_logic',
        'games.entrapment_logic',
        'games.havannah_logic',
        'games.hnefatafl_logic',
        'games.shobu_logic',
        'games.tumbleweed_logic',
        'games.yinsh_logic',

        # Display modules
        'games.abalone_display',
        'games.amazons_display',
        'games.arimaa_display',
        'games.bagh_chal_display',
        'games.bao_display',
        'games.bashni_display',
        'games.entrapment_display',
        'games.havannah_display',
        'games.hnefatafl_display',
        'games.shobu_display',
        'games.tumbleweed_display',
        'games.yinsh_display',

        # Client modules
        'client',
        'client.main',
        'client.lobby',
        'client.network',
        'client.shared',
        'client.host',
        'client.bot',
        'client.bot_game',

        # Server (embedded for self-hosting)
        'server',
        'server.main',

        # Third-party packages
        'websocket',
        'numpy',
        'pygame',

        # uvicorn and sub-modules PyInstaller misses
        'uvicorn',
        'uvicorn.config',
        'uvicorn.main',
        'uvicorn.loops.auto',
        'uvicorn.lifespan.on',
        'uvicorn.protocols.websockets.auto',

        # fastapi
        'fastapi',

        # pyngrok and sub-modules
        'pyngrok',
        'pyngrok.ngrok',
        'pyngrok.conf',
        'pyngrok.installer',
        'pyngrok.process',
        'pyngrok.exception',

        # Clipboard
        'pyperclip',

        # SSL / certificates
        'certifi',
        'ssl',
        '_ssl',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# ── PYZ ───────────────────────────────────────────────────────────────────

pyz = PYZ(a.pure)

# ── EXE ───────────────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BoardGamesOnline',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,

    # Console mode — shows a terminal window alongside the Pygame window.
    # Change to False once the build is stable and you no longer need to
    # see print() output or tracebacks.
    console=True,

    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,

    # Uncomment and set this to an .ico file path to give the .exe an icon:
    # icon='icon.ico',
)

# ── macOS .app bundle ────────────────────────────────────────────────────
# On macOS, wrap the executable in a .app bundle so users can double-click it.
# BUNDLE is only defined in the PyInstaller spec namespace on macOS.

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='BoardGamesOnline.app',
        bundle_identifier='com.boardgamesonline.app',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
