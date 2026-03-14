# CLAUDE.md

## Project Overview

A modular online multiplayer hub for abstract strategy board games. Currently has 13 games (Abalone, Amazons, Arimaa, Bagh Chal, Bao, Bashni, Entrapment, Havannah, Hive, Hnefatafl, Shobu, Tumbleweed, YINSH) with four play modes: Host Game (embedded server + ngrok tunnel), Join Game (WebSocket client), Play Locally (hotseat), and Play vs Bot (Weak/Strong MCTS or Expert/Claude AI). Builds as native executables for Windows, Linux, and macOS.

## Architecture

### Server-Authoritative Design
The FastAPI WebSocket server (`server/main.py`) owns the canonical game state, validates every move via the game logic module, and broadcasts updates. Clients never decide whether moves are valid — they send move requests and render whatever state the server provides.

### Module Layers
- **Game logic** (`games/*_logic.py`) — Pure Python, no Pygame. Implements the `AbstractBoardGame` interface. Each game is a self-contained module.
- **Game display** (`games/*_display.py`) — Pygame rendering and input. Each has `GameClient`, `Renderer`, `run_online()`, and `main()`.
- **Server** (`server/main.py`) — Room management, WebSocket protocol, reconnection with forfeit timers.
- **Client** (`client/`) — Main menu, lobby, network client, self-hosting (ngrok), bots, shared display utilities.

### AbstractBoardGame Interface (`games/base_game.py`)
Every game must subclass this and implement seven methods:
- `_get_name()` → str
- `_get_player_count()` → int
- `_create_initial_state()` → dict
- `_get_current_player(state)` → int
- `_get_legal_moves(state, player)` → list
- `_apply_move(state, player, move)` → dict (must deepcopy, must validate)
- `_get_game_status(state)` → `{"is_over": bool, "winner": int|None, "is_draw": bool}`

The base class wraps these with automatic JSON validation, turn-order enforcement, move-legality checks, and immutability verification. **Do not modify `base_game.py`.**

## Directory Structure

```
board-games-online/
├── CLAUDE.md                  ← this file
├── games/
│   ├── base_game.py           ← AbstractBoardGame interface (DO NOT MODIFY)
│   ├── __init__.py            ← game registry (GAME_REGISTRY dict)
│   ├── [game]_logic.py        ← pure game rules, inherits AbstractBoardGame
│   ├── [game]_display.py      ← Pygame rendering + online/local/bot play
│   └── [game].py              ← original standalone files (backups)
├── rules/
│   └── [game]_logic.md        ← authoritative rule descriptions per game
├── server/
│   └── main.py                ← FastAPI WebSocket server, room management
├── client/
│   ├── main.py                ← main menu, app entry point
│   ├── lobby.py               ← online lobby, dispatch table for launching games
│   ├── network.py             ← WebSocket client, background thread, message queue
│   ├── shared.py              ← History, Orientation, command panel, shared input
│   ├── host.py                ← embedded server + pyngrok tunnel management
│   ├── bot.py                 ← MCTS bot (Weak/Strong), game-agnostic
│   ├── bot_game.py            ← BotNetAdapter connecting bot to display modules
│   └── claude_bot.py          ← Claude API bot (Expert), game-agnostic
├── tests/                     ← pytest test suite
├── .github/workflows/         ← GitHub Actions CI (Windows/Linux/macOS builds)
├── requirements.txt
├── pyinstaller_imports.py     ← explicit imports for PyInstaller bundling
└── BoardGamesOnline.spec      ← PyInstaller build configuration
```

## Critical Constraints

### Data Serialization
All game state and move data must be JSON-serializable — **only** `dict` (string keys), `list`, `str`, `int`, `float`, `bool`, `None`. No tuples, sets, numpy arrays, custom objects, or non-string dict keys. Enforced at runtime by `base_game.py` — violations crash immediately.

### Player IDs
Always integers: `1` and `2`. Never strings like `"white"`/`"black"`.

### No Pygame in Logic
Game logic files must never import Pygame.

### Immutability
`_apply_move` must `copy.deepcopy(state)` and return a new dict. The base class verifies the original is unmodified. The bot calls `_apply_move` thousands of times speculatively — mutations corrupt the search tree.

### Legal Moves as Source of Truth
`_get_legal_moves` must be perfectly accurate. Display modules, bots, and the server all rely on it. The `rules/` folder contains the authoritative rule reference — rules files win over original game files on any disagreement.

## Tech Stack

Python 3.11+, Pygame, FastAPI, uvicorn, websockets, pyngrok, anthropic, certifi, pyperclip, PyInstaller, pytest, GitHub Actions.

## Bot System

Three difficulties, all fully game-agnostic (work through `AbstractBoardGame` only, never import any specific game):

- **Weak** (`MCTSBot("weak")`) — Pure `random.choice`, instant, no search.
- **Strong** (`MCTSBot("strong")`) — MCTS with GRAVE, mobility evaluation, MCTS-Solver, 3-ply loss prevention, tree reuse. 8s budget.
- **Expert** (`ClaudeBot()`) — Claude API with formatted board state and numbered moves. Falls back to Strong if API fails. Key stored in `~/.board_games_online/anthropic_key.txt`.

**Do not modify** `client/bot.py`, `client/bot_game.py`, or `client/claude_bot.py` when adding games.

## Display Module Pattern

Every display module follows this structure:

- `GameClient` — Controller with online/local modes, `load_state()`, `set_game_over()`, `is_my_turn` property. Click handlers return move dict (online) or apply locally.
- `_HistoryView` — Lightweight proxy for rendering past states during history browsing.
- `Renderer` — All Pygame drawing, supports `flipped` orientation.
- `run_online(screen, net, my_player, initial_state)` — Handles all 7 message types: `move_made`, `game_over`, `player_disconnected`, `player_reconnected`, `error`, `connection_error`, `connection_closed`.
- `main()` — Local hotseat entry point.

Must use shared utilities from `client/shared.py`: `History`, `Orientation`, `draw_command_panel`, `handle_shared_input`. Command panel is a hover-reveal 22x22 "?" icon. No overlapping UI elements.

## Adding a New Game

Update these files in order:

1. Create `games/GAME_logic.py` — inherits `AbstractBoardGame`
2. Create `games/GAME_display.py` — follows the standard display pattern
3. `games/__init__.py` — import + registry entry
4. `client/lobby.py` — import + dispatch entry in `_load_dispatch()`
5. `pyinstaller_imports.py` — add both logic and display imports
6. `tests/test_rules_compliance.py` — append rules tests before Runner section
7. `tests/test_all_games_online.py` — add to `DISPLAY_MODULES` dict
8. `tests/test_click_pipeline.py` — add to `_DISPLAY_MODULES` dict

Preserve original `games/GAME.py` as backup. Verify bot compatibility after integration.

## Test Suite

```bash
python -m pytest tests/ -v --tb=short
```

- `test_rules_compliance.py` — Per-game rule verification
- `test_multiplayer_readiness.py` — Parameterized checks for all games
- `test_all_games_online.py` — Server validation, lobby dispatch for all games
- `test_click_pipeline.py` — Display `is_my_turn` and server round-trip for all games
- `test_server.py` / `test_server_robustness.py` / `test_server_audit.py` — Server edge cases
- `test_bot.py` — Bot legality, matchups, Claude bot degradation

Some WebSocket tests are timing-sensitive and may flake on port conflicts.

## Commands

```bash
python client/main.py                              # Run the app
python client/main.py ws://localhost:8000/ws        # Connect directly to server
uvicorn server.main:app --host 0.0.0.0 --port 8000 # Standalone server
python -m pytest tests/ -v --tb=short               # Run tests
pkill -f ngrok                                      # Kill stale ngrok
```

## Do Not

- Make the client authoritative
- Put Pygame imports in logic modules
- Use tuples, sets, numpy, or custom objects in game state or moves
- Modify `base_game.py`, `server/main.py`, `client/bot.py`, `client/claude_bot.py`, or `client/shared.py` when adding games
- Modify original `[game].py` backup files
- Bundle ngrok manually — pyngrok handles it at runtime
- Hardcode game-specific logic in server, bots, or shared utilities
- Weaken test assertions to make tests pass — fix the underlying code
