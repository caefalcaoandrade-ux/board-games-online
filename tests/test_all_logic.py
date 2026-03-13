"""Comprehensive test for every registered game's logic module.

For each game: imports without Pygame, creates an instance, gets initial state,
gets legal moves, applies the first move, checks game-over status, and verifies
JSON round-trip integrity on the initial state, legal moves, and post-move state.
"""

import sys
import os
import json

# Block pygame so we prove no logic module depends on it
sys.modules["pygame"] = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from games import list_games, create_game

PASS = 0
FAIL = 0
FAILURES = []


def check(game_name, label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        msg = f"  FAIL: {game_name} — {label}"
        if detail:
            msg += f" ({detail})"
        FAILURES.append(msg)
        print(msg)


def json_roundtrip(data):
    """Return the data after a json.dumps -> json.loads cycle."""
    return json.loads(json.dumps(data))


names = list_games()
print(f"Registered games ({len(names)}): {names}\n")
print("=" * 70)

for name in names:
    print(f"\n── {name} ──")

    # 1. Create instance
    game = create_game(name)
    check(name, "create instance", game is not None)

    # 2. Initial state
    state = game.create_initial_state()
    check(name, "initial state is dict", isinstance(state, dict))
    print(f"  Initial state keys: {list(state.keys())}")
    state_json = json.dumps(state, indent=2)
    print(f"  Initial state ({len(state_json)} bytes JSON):")
    # Print truncated for readability
    for line in state_json.splitlines()[:12]:
        print(f"    {line}")
    if state_json.count("\n") > 12:
        print(f"    ... ({state_json.count(chr(10)) - 12} more lines)")

    # 3. Current player
    player = game.get_current_player(state)
    check(name, "current player is int", isinstance(player, int))
    print(f"  First player: {player}")

    # 4. Legal moves
    moves = game.get_legal_moves(state, player)
    check(name, "legal moves is list", isinstance(moves, list))
    check(name, "has at least one legal move", len(moves) > 0,
          f"got {len(moves)}")
    print(f"  Legal moves: {len(moves)}")
    if moves:
        print(f"  First move sample: {moves[0]}")

    # 5. Apply first legal move
    new_state = game.apply_move(state, player, moves[0])
    check(name, "apply_move returns dict", isinstance(new_state, dict))
    check(name, "apply_move returns new object", new_state is not state)
    new_json = json.dumps(new_state, indent=2)
    print(f"  Post-move state ({len(new_json)} bytes JSON):")
    for line in new_json.splitlines()[:12]:
        print(f"    {line}")
    if new_json.count("\n") > 12:
        print(f"    ... ({new_json.count(chr(10)) - 12} more lines)")

    # 6. Game-over status
    status = game.get_game_status(new_state)
    check(name, "status is dict", isinstance(status, dict))
    check(name, "status has is_over", "is_over" in status)
    check(name, "status has winner", "winner" in status)
    check(name, "status has is_draw", "is_draw" in status)
    print(f"  Game over after first move: {status['is_over']}")

    # 7. JSON round-trip: initial state
    rt_state = json_roundtrip(state)
    check(name, "JSON round-trip: initial state",
          rt_state == state,
          "data changed after round-trip")

    # 8. JSON round-trip: legal moves
    rt_moves = json_roundtrip(moves)
    check(name, "JSON round-trip: legal moves",
          rt_moves == moves,
          "data changed after round-trip")

    # 9. JSON round-trip: post-move state
    rt_new = json_roundtrip(new_state)
    check(name, "JSON round-trip: post-move state",
          rt_new == new_state,
          "data changed after round-trip")

    checks_for_game = 12  # total checks per game
    print(f"  ✓ all checks passed" if not any(
        name in f for f in FAILURES) else "")


# ── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"\nTotal checks: {PASS + FAIL}  |  Passed: {PASS}  |  Failed: {FAIL}")

if FAILURES:
    print("\nFailed checks:")
    for f in FAILURES:
        print(f)
    sys.exit(1)
else:
    print(f"\nAll {PASS} checks across {len(names)} game(s) passed.")
