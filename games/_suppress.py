"""Suppress noisy startup messages before Pygame loads.

Import this module before ``import pygame`` to silence:
- Pygame community banner  (PYGAME_HIDE_SUPPORT_PROMPT)
- AVX2 RuntimeWarning      (pygame C-extension build notice)
- pkg_resources UserWarning (setuptools deprecation notice)
"""

import os
import warnings

# "Hello from the pygame community" banner
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# "Your system is avx2 capable but pygame was not built with support for it"
warnings.filterwarnings("ignore", message=".*avx2.*", category=RuntimeWarning)

# "pkg_resources is deprecated as an API" (emitted as UserWarning by some
# setuptools versions, DeprecationWarning by others — suppress both)
warnings.filterwarnings(
    "ignore", message=".*pkg_resources.*", category=UserWarning
)
warnings.filterwarnings(
    "ignore", message=".*pkg_resources.*", category=DeprecationWarning
)
