"""Game registry — central index of all available games.

To register a new game, add one import and one entry to GAME_REGISTRY.
"""

from games.abalone_logic import AbaloneLogic
from games.amazons_logic import AmazonsLogic
from games.arimaa_logic import ArimaaLogic
from games.bagh_chal_logic import BaghChalLogic
from games.bao_logic import BaoGame
from games.bashni_logic import BashniLogic
from games.entrapment_logic import EntrapmentLogic
from games.havannah_logic import HavannahLogic
from games.hive_logic import HiveLogic
from games.hnefatafl_logic import HnefataflLogic
from games.shobu_logic import ShobuLogic
from games.tak_logic import TakLogic
from games.tumbleweed_logic import TumbleweedLogic
from games.yinsh_logic import YinshLogic

# ── Registry ─────────────────────────────────────────────────────────────────
# Maps game name (str) -> logic class (AbstractBoardGame subclass).
# To add a new game, add one import above and one line here:
#   "GameName": GameNameLogic,

GAME_REGISTRY: dict[str, type] = {
    "Abalone": AbaloneLogic,
    "Amazons": AmazonsLogic,
    "Arimaa": ArimaaLogic,
    "BaghChal": BaghChalLogic,
    "Bao": BaoGame,
    "Bashni": BashniLogic,
    "Entrapment": EntrapmentLogic,
    "Havannah": HavannahLogic,
    "Hive": HiveLogic,
    "Hnefatafl": HnefataflLogic,
    "Shobu": ShobuLogic,
    "Tak": TakLogic,
    "Tumbleweed": TumbleweedLogic,
    "YINSH": YinshLogic,
}


def list_games() -> list[str]:
    """Return the names of all available games."""
    return list(GAME_REGISTRY.keys())


def create_game(name: str):
    """Create and return a fresh instance of the named game.

    Raises KeyError if the name is not in the registry.
    """
    try:
        cls = GAME_REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(GAME_REGISTRY))
        raise KeyError(
            f"Unknown game {name!r}. Available: {available}"
        ) from None
    return cls()
