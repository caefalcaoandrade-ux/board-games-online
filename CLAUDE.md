# CLAUDE.md

## Project Overview

This project is a modular online hub for abstract board games.

## Architecture

The server is authoritative — it owns the official game state, validates every move, and broadcasts updates. Clients never decide whether moves are valid.

Pygame is used only on the client side for rendering. Game logic files must never import Pygame.

Every game must implement the same standard interface so the server can work with any game generically.

## Data Serialization

All game state and move data must be JSON-serializable — only basic Python types (dicts, lists, strings, numbers, booleans). No numpy arrays, no custom objects, no tuples in state or moves.

## Tech Stack

- Python
- FastAPI
- uvicorn
- websockets
- Pygame
- numpy
- pytest

## Development Practices

Original game files in the games folder should be preserved as backups when refactored.

Always write and run tests before wiring new features into the hub.
