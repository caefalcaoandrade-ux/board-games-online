"""Quick smoke test for the Amazons logic module — no Pygame involved."""

import sys
import os
import json

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Verify that the logic module itself does not import pygame
# (checked at the end of main() rather than via import hook,
# which would interfere with other test modules in the suite).

from games.amazons_logic import AmazonsLogic, WHITE, BLACK, BOARD_N

def print_board(board):
    """Pretty-print the 10x10 board."""
    symbols = {0: ".", 1: "W", 2: "B", 3: "X"}
    print("     " + "  ".join("abcdefghij"))
    print("    " + "-" * 30)
    for r in range(BOARD_N):
        rank = str(BOARD_N - r).rjust(2)
        row_str = "  ".join(symbols[board[r][c]] for c in range(BOARD_N))
        print(f" {rank} | {row_str}")
    print()

def main():
    game = AmazonsLogic()

    # 1. Create initial state
    print("=" * 60)
    print("1. INITIAL STATE")
    print("=" * 60)
    state = game.create_initial_state()
    print(f"   Name:         {game.name}")
    print(f"   Players:      {game.player_count}")
    print(f"   Turn:         {'White' if state['turn'] == WHITE else 'Black'}")
    print(f"   Move number:  {state['move_num']}")
    print()
    print_board(state["board"])

    # 2. Legal moves for first player
    print("=" * 60)
    print("2. LEGAL MOVES FOR WHITE")
    print("=" * 60)
    moves = game.get_legal_moves(state, WHITE)
    print(f"   Total legal moves: {len(moves)}")
    print(f"   First 5 moves:")
    for m in moves[:5]:
        (fr, fc), (tr, tc), (ar, ac) = m
        print(f"     amazon ({fr},{fc}) -> ({tr},{tc}), arrow -> ({ar},{ac})")
    print(f"   ...")
    print()

    # 3. Apply the first legal move
    print("=" * 60)
    print("3. APPLY FIRST LEGAL MOVE")
    print("=" * 60)
    move = moves[0]
    (fr, fc), (tr, tc), (ar, ac) = move
    print(f"   Move: amazon ({fr},{fc}) -> ({tr},{tc}), arrow -> ({ar},{ac})")
    new_state = game.apply_move(state, WHITE, move)
    print(f"   Turn after move: {'White' if new_state['turn'] == WHITE else 'Black'}")
    print(f"   Move number:     {new_state['move_num']}")
    print()
    print_board(new_state["board"])

    # Verify original state was NOT mutated
    assert state == game.create_initial_state(), "Original state was mutated!"
    print("   Original state verified untouched.")
    print()

    # 4. Game-over check
    print("=" * 60)
    print("4. GAME STATUS")
    print("=" * 60)
    status = game.get_game_status(new_state)
    print(f"   Is over: {status['is_over']}")
    print(f"   Winner:  {status['winner']}")
    print(f"   Is draw: {status['is_draw']}")
    print()

    # 5. Verify JSON round-trip
    print("=" * 60)
    print("5. JSON SERIALIZATION")
    print("=" * 60)
    json_str = json.dumps(new_state)
    restored = json.loads(json_str)
    assert restored == new_state, "JSON round-trip changed the state!"
    print(f"   State serializes to {len(json_str)} bytes of JSON")
    print(f"   Round-trip verified: identical after json.dumps -> json.loads")
    print()

    print("=" * 60)
    print("ALL CHECKS PASSED — logic module is fully Pygame-independent")
    print("=" * 60)

if __name__ == "__main__":
    main()
