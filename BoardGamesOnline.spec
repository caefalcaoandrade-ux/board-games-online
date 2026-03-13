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
import certifi

# ── Analysis ──────────────────────────────────────────────────────────────
# PyInstaller analyses build_exe.py to discover imports.  build_exe.py
# imports pyinstaller_imports.py, which explicitly imports every game logic
# and display module so nothing is missed.
#
# hiddenimports lists the same modules as a belt-and-suspenders backup in
# case PyInstaller's import scanner misses anything despite the explicit
# imports in pyinstaller_imports.py.

a = Analysis(
    # The build entry point script.
    ['build_exe.py'],

    pathex=['.'],

    binaries=[],

    # Include the entire games/ folder as data so that any non-.py files
    # (e.g. the original .py backups, _suppress.py, __init__.py) are
    # bundled.  The tuple is (source_path, destination_in_bundle).
    datas=[
        ('games', 'games'),
        ('client', 'client'),
        # Bundle certifi's CA certificate file so wss:// connections work
        # inside the PyInstaller .exe (the OS cert store is not available).
        (certifi.where(), 'certifi'),
    ],

    # Explicit hidden imports — every module that is loaded dynamically at
    # runtime via the game registry or the lobby dispatch table.  These
    # duplicate what pyinstaller_imports.py already covers, but listing
    # them here guarantees PyInstaller includes them even if it fails to
    # trace the explicit import file for any reason.
    hiddenimports=[
        # Game registry and base class
        'games',
        'games.base_game',

        # Logic modules (loaded by games/__init__.py registry)
        'games.abalone_logic',
        'games.amazons_logic',
        'games.bashni_logic',
        'games.entrapment_logic',
        'games.havannah_logic',
        'games.hnefatafl_logic',
        'games.shobu_logic',
        'games.tumbleweed_logic',
        'games.yinsh_logic',

        # Display modules (loaded lazily by client/lobby.py dispatch)
        'games.abalone_display',
        'games.amazons_display',
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

        # Third-party packages that PyInstaller sometimes misses
        'websocket',
        'numpy',
        'pygame',

        # SSL / certificate packages needed for wss:// connections
        'certifi',
        'ssl',
        '_ssl',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    # Do not exclude anything — we want a complete bundle.
    excludes=[],

    noarchive=False,
)

# ── PYZ ───────────────────────────────────────────────────────────────────
# Compressed archive of all pure-Python modules.  This is unpacked into
# memory at runtime by the bootloader.

pyz = PYZ(a.pure)

# ── EXE ───────────────────────────────────────────────────────────────────
# The final executable.  Key settings:
#
#   name          — output filename (BoardGamesOnline.exe on Windows)
#   onefile       — True bundles everything into a single .exe
#   console       — True keeps the terminal visible for error messages;
#                   set to False for a clean windowed release
#   icon          — set to an .ico path if you have one (e.g. 'icon.ico')

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
