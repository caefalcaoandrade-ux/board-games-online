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
import games._suppress                # noqa: F401
import games.abalone_logic            # noqa: F401
import games.amazons_logic            # noqa: F401
import games.arimaa_logic             # noqa: F401
import games.bagh_chal_logic          # noqa: F401
import games.bao_logic                # noqa: F401
import games.bashni_logic             # noqa: F401
import games.entrapment_logic         # noqa: F401
import games.havannah_logic           # noqa: F401
import games.hive_logic               # noqa: F401
import games.hnefatafl_logic          # noqa: F401
import games.shobu_logic              # noqa: F401
import games.tumbleweed_logic         # noqa: F401
import games.yinsh_logic              # noqa: F401

# ── Game display modules (Pygame-based, loaded lazily by the lobby) ───────
import games.abalone_display          # noqa: F401
import games.amazons_display          # noqa: F401
import games.arimaa_display           # noqa: F401
import games.bagh_chal_display        # noqa: F401
import games.bao_display              # noqa: F401
import games.bashni_display           # noqa: F401
import games.entrapment_display       # noqa: F401
import games.havannah_display         # noqa: F401
import games.hive_display             # noqa: F401
import games.hnefatafl_display        # noqa: F401
import games.shobu_display            # noqa: F401
import games.tumbleweed_display       # noqa: F401
import games.yinsh_display            # noqa: F401

# ── Game registry ─────────────────────────────────────────────────────────
import games                          # noqa: F401

# ── Client modules ────────────────────────────────────────────────────────
import client.network                 # noqa: F401
import client.lobby                   # noqa: F401
import client.main                    # noqa: F401
import client.shared                  # noqa: F401
import client.rules                   # noqa: F401
import client.host                    # noqa: F401
import client.bot                     # noqa: F401
import client.bot_game                # noqa: F401
import client.claude_bot              # noqa: F401

# ── Server (embedded for self-hosting) ───────────────────────────────────
import server.main                    # noqa: F401

# ── SSL / certificate support for wss:// connections ──────────────────────
import certifi                        # noqa: F401
import ssl                            # noqa: F401

# ── Clipboard ────────────────────────────────────────────────────────────
import pyperclip                      # noqa: F401

# ── Hosting / tunnel dependencies ────────────────────────────────────────
import pyngrok                        # noqa: F401
import pyngrok.ngrok                  # noqa: F401
import pyngrok.conf                   # noqa: F401
import pyngrok.installer              # noqa: F401
import pyngrok.process                # noqa: F401
import pyngrok.exception              # noqa: F401

# ── uvicorn sub-modules PyInstaller misses ───────────────────────────────
import uvicorn                        # noqa: F401
import uvicorn.config                 # noqa: F401
import uvicorn.main                   # noqa: F401
import uvicorn.loops.auto             # noqa: F401
import uvicorn.lifespan.on            # noqa: F401
import uvicorn.protocols.websockets.auto  # noqa: F401
