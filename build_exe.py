"""Build entry point for PyInstaller.

This script exists solely to give PyInstaller a clean, unambiguous top-level
file to analyse.  It does two things:

1. Imports the hidden-imports module so PyInstaller detects every game logic
   and display module that would otherwise be missed (they are loaded
   dynamically at runtime by the registry and lobby dispatch table).

2. Calls the real main() function from client.main.

Build with::

    pyinstaller BoardGamesOnline.spec

Or one-shot without the spec file::

    pyinstaller --onefile --console --name BoardGamesOnline build_exe.py
"""

import sys
import os

# Ensure the project root is on sys.path so all package imports resolve.
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Force PyInstaller to detect every game module.
import pyinstaller_imports  # noqa: F401

# Launch the application.
from client.main import main

if __name__ == "__main__":
    main()
