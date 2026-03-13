# ── PyInstaller hidden imports for Board Games Online ─────────────────────
#
# PyInstaller cannot detect dynamically imported modules (e.g. those loaded
# via the game registry or the lobby dispatch table).  This file explicitly
# imports every module that must be bundled so PyInstaller's dependency
# scanner picks them up.
#
# *** IMPORTANT ***
# When you add a new game to the project, add its logic module AND its
# display module here.  If you forget, the new game will be missing from
# the Windows build and will crash at runtime with an ImportError.

# ── Game logic modules (no Pygame dependency) ─────────────────────────────
import games.base_game                # noqa: F401
import games.abalone_logic            # noqa: F401
import games.amazons_logic            # noqa: F401
import games.bashni_logic             # noqa: F401
import games.entrapment_logic         # noqa: F401
import games.havannah_logic           # noqa: F401
import games.hnefatafl_logic          # noqa: F401
import games.shobu_logic              # noqa: F401
import games.tumbleweed_logic         # noqa: F401
import games.yinsh_logic              # noqa: F401

# ── Game display modules (Pygame-based, loaded lazily by the lobby) ───────
import games.abalone_display          # noqa: F401
import games.amazons_display          # noqa: F401
import games.bashni_display           # noqa: F401
import games.entrapment_display       # noqa: F401
import games.havannah_display         # noqa: F401
import games.hnefatafl_display        # noqa: F401
import games.shobu_display            # noqa: F401
import games.tumbleweed_display       # noqa: F401
import games.yinsh_display            # noqa: F401

# ── Game registry ─────────────────────────────────────────────────────────
import games                          # noqa: F401  (__init__.py with GAME_REGISTRY)

# ── Client modules ────────────────────────────────────────────────────────
import client.network                 # noqa: F401
import client.lobby                   # noqa: F401
import client.main                    # noqa: F401

# ── SSL / certificate support for wss:// connections ──────────────────────
import certifi                        # noqa: F401
import ssl                            # noqa: F401
