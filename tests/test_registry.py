"""Test that every game in the registry can be created and produces valid state."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games import list_games, create_game

names = list_games()
print(f"Registered games: {names}")
print()

for name in names:
    game = create_game(name)
    state = game.create_initial_state()
    player = game.get_current_player(state)
    moves = game.get_legal_moves(state, player)
    status = game.get_game_status(state)

    # JSON round-trip
    restored = json.loads(json.dumps(state))
    assert restored == state, f"{name}: state failed JSON round-trip"

    print(f"  {name}")
    print(f"    players:       {game.player_count}")
    print(f"    first player:  {player}")
    print(f"    legal moves:   {len(moves)}")
    print(f"    game over:     {status['is_over']}")
    print(f"    JSON bytes:    {len(json.dumps(state))}")
    print()

print(f"All {len(names)} game(s) passed.")
