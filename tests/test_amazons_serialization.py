"""Test that all Amazons game data survives JSON round-trips perfectly."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games.amazons_logic import AmazonsLogic, WHITE, BLACK

game = AmazonsLogic()
passed = 0
failed = 0


def check(label, data):
    global passed, failed
    try:
        encoded = json.dumps(data)
        decoded = json.loads(encoded)
    except TypeError as e:
        print(f"  FAIL  {label}: json.dumps raised {e}")
        failed += 1
        return

    if decoded != data:
        print(f"  FAIL  {label}: data changed after round-trip")
        print(f"         before: {repr(data)[:120]}")
        print(f"         after:  {repr(decoded)[:120]}")
        failed += 1
    else:
        print(f"  OK    {label}")
        passed += 1


# 1. Initial state
state = game.create_initial_state()
check("initial state", state)

# 2. Legal moves list
moves = game.get_legal_moves(state, WHITE)
check(f"legal moves ({len(moves)} moves)", moves)

# 3. Each individual move (spot-check first, middle, last)
for i in [0, len(moves) // 2, len(moves) - 1]:
    check(f"  move[{i}] = {moves[i]}", moves[i])

# 4. State after applying a move
state_after = game.apply_move(state, WHITE, moves[0])
check("state after White's first move", state_after)

# 5. Second player's moves and state
moves_b = game.get_legal_moves(state_after, BLACK)
check(f"Black's legal moves ({len(moves_b)} moves)", moves_b)

state_after_2 = game.apply_move(state_after, BLACK, moves_b[0])
check("state after Black's first move", state_after_2)

# 6. Game status dicts
for label, s in [("initial", state), ("after move 1", state_after),
                 ("after move 2", state_after_2)]:
    status = game.get_game_status(s)
    check(f"game status ({label})", status)

# 7. Play 10 moves and check every resulting state
s = state
for i in range(10):
    player = game.get_current_player(s)
    m = game.get_legal_moves(s, player)
    if not m:
        break
    s = game.apply_move(s, player, m[0])
    check(f"state after move {i + 1} (player {player})", s)

print()
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
print("All JSON serialization checks passed.")
