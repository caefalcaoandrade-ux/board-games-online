# Bagh Chal — Definitive Ruleset Specification

## 1. Game Classification

Bagh Chal is a two-player, asymmetric, zero-sum, deterministic abstract strategy board game of perfect information. One player controls 4 Tigers. The other player controls 20 Goats.

## 2. Board Architecture

### 2.1 Grid

The board is a 5×5 lattice of 25 intersection points (nodes). Pieces occupy nodes, never the spaces between them. Only one piece may occupy a node at any time.

### 2.2 Coordinate System

Each node is identified by a coordinate pair (row, col) where row ∈ {0,1,2,3,4} (top to bottom) and col ∈ {0,1,2,3,4} (left to right).

Linear index: `id = 5 * row + col`
Reverse: `row = id ÷ 5` (integer division), `col = id mod 5`

The 25 nodes indexed 0–24:

```
 0  1  2  3  4
 5  6  7  8  9
10 11 12 13 14
15 16 17 18 19
20 21 22 23 24
```

### 2.3 Connectivity Rules

Movement occurs only along board lines connecting adjacent nodes. Two types of connections exist:

**Orthogonal edges:** Every node connects to its horizontally and vertically adjacent neighbors. Formally, nodes A(r1,c1) and B(r2,c2) share an orthogonal edge if `|r1−r2| + |c1−c2| = 1`.

**Diagonal edges:** A diagonal edge exists between two diagonally adjacent nodes if and only if **both** endpoints have even coordinate parity, meaning `(row + col) mod 2 = 0` for both nodes. Formally, nodes A(r1,c1) and B(r2,c2) share a diagonal edge if `|r1−r2| = 1` AND `|c1−c2| = 1` AND `(r1+c1) mod 2 = 0` AND `(r2+c2) mod 2 = 0`.

Nodes where `(row + col)` is odd have orthogonal connections only and zero diagonal connections.

### 2.4 Complete Adjacency List

| ID | (row,col) | Parity | Neighbors |
|----|-----------|--------|-----------|
| 0  | (0,0)     | Even   | 1, 5, 6 |
| 1  | (0,1)     | Odd    | 0, 2, 6 |
| 2  | (0,2)     | Even   | 1, 3, 6, 7, 8 |
| 3  | (0,3)     | Odd    | 2, 4, 8 |
| 4  | (0,4)     | Even   | 3, 8, 9 |
| 5  | (1,0)     | Odd    | 0, 6, 10 |
| 6  | (1,1)     | Even   | 0, 1, 2, 5, 7, 10, 11, 12 |
| 7  | (1,2)     | Odd    | 2, 6, 8, 12 |
| 8  | (1,3)     | Even   | 2, 3, 4, 7, 9, 12, 13, 14 |
| 9  | (1,4)     | Odd    | 4, 8, 14 |
| 10 | (2,0)     | Even   | 5, 6, 11, 15, 16 |
| 11 | (2,1)     | Odd    | 6, 10, 12, 16 |
| 12 | (2,2)     | Even   | 6, 7, 8, 11, 13, 16, 17, 18 |
| 13 | (2,3)     | Odd    | 8, 12, 14, 18 |
| 14 | (2,4)     | Even   | 8, 9, 13, 18, 19 |
| 15 | (3,0)     | Odd    | 10, 16, 20 |
| 16 | (3,1)     | Even   | 10, 11, 12, 15, 17, 20, 21, 22 |
| 17 | (3,2)     | Odd    | 12, 16, 18, 22 |
| 18 | (3,3)     | Even   | 12, 13, 14, 17, 19, 22, 23, 24 |
| 19 | (3,4)     | Odd    | 14, 18, 24 |
| 20 | (4,0)     | Even   | 15, 16, 21 |
| 21 | (4,1)     | Odd    | 16, 20, 22 |
| 22 | (4,2)     | Even   | 16, 17, 18, 21, 23 |
| 23 | (4,3)     | Odd    | 18, 22, 24 |
| 24 | (4,4)     | Even   | 18, 19, 23 |

## 3. Initial Setup

- Tigers occupy the four corners: nodes 0, 4, 20, 24.
- All 20 Goats begin off the board in a reserve pool.
- The Goat player takes the first turn.

## 4. Game Phases

### 4.1 Phase 1 — Goat Placement Phase

Active while the Goat reserve count is greater than zero.

**Goat turn:** The Goat player must place exactly 1 Goat from reserve onto any empty node. Goats already on the board cannot be moved during this phase.

**Tiger turn:** The Tiger player must either (a) move one Tiger to an adjacent empty node along a board line, or (b) execute a capture jump with one Tiger (see Section 6). Tigers are fully mobile and may capture from the very first Tiger turn onward.

### 4.2 Phase 2 — Movement Phase

Begins immediately after the 20th Goat has been placed. The Goat reserve is now zero and placement is permanently disabled.

**Goat turn:** The Goat player must move exactly 1 Goat already on the board to an adjacent empty node along a board line.

**Tiger turn:** Same as Phase 1 — move one Tiger to an adjacent empty node, or execute a capture jump.

## 5. Ordinary Movement

A non-capturing move consists of moving exactly one piece along exactly one board edge to an adjacent empty node. This applies identically to both Tigers and Goats (Goats only in Phase 2).

## 6. Tiger Capture Rules

Only Tigers capture. Goats can never capture or jump.

A Tiger at origin node O can capture a Goat at intermediate node I and land on destination node D if and only if **all** of the following are true:

1. **I is adjacent to O** along a board line.
2. **I contains a Goat** (not a Tiger, not empty).
3. **D is the node directly beyond I**, continuing in the same straight-line direction from O through I. Formally: `D_row = 2 * I_row − O_row` and `D_col = 2 * I_col − O_col`.
4. **D exists** (coordinates within 0–4 bounds).
5. **D is empty.**
6. **D is adjacent to I** along a board line (this is automatically satisfied if the direction is orthogonal; for diagonal jumps, it requires that the diagonal edge O→I and the diagonal edge I→D both exist, which means O, I, and D must all be even-parity nodes).

Upon capture:
- The Tiger moves from O to D.
- The Goat at I is permanently removed from the game.
- The captured-goat counter increments by 1.

### 6.1 Capture Constraints

- A Tiger may capture **only one Goat per turn**. Multiple sequential jumps are not allowed.
- A Tiger **cannot jump over another Tiger**.
- A Tiger **cannot change direction** mid-jump.
- **Capture is not compulsory.** A Tiger may choose a non-capturing move even when a capture is available.
- Captured Goats are permanently removed and never return to the board or to reserve.

## 7. Win Conditions

The game ends immediately when either condition is met:

**Tiger victory:** The Tigers have captured exactly 5 Goats (captured-goat counter reaches 5).

**Goat victory:** At the start of the Tiger player's turn, no Tiger on the board has any legal move (neither a slide to an adjacent empty node nor a valid capture jump). All 4 Tigers must be simultaneously immobilized.

### 7.1 Clarifications

- A Tiger that is individually blocked is not removed; it remains on the board.
- Blocking fewer than all 4 Tigers does not end the game.
- If a blocked Tiger later gains a legal move (because surrounding pieces have shifted), it is no longer blocked.
- If the Goat player has no legal move on their turn, the Tiger player wins.

## 8. Repetition and Draw Handling

This is a variant-dependent rule. Implementations should support a configurable toggle between two modes:

**Mode A — Strict No-Repeat (Traditional):** Once Phase 2 begins, no move may produce a board state (piece positions + side to move) that has already occurred at any earlier point in the game. Any such move is illegal and excluded from the legal move list.

**Mode B — Threefold Repetition Draw (Computational):** If the same board state (piece positions + side to move) occurs 3 times during the game, the game immediately ends in a draw.

If neither mode is enabled, the game ends only by Tiger capture of 5 Goats or Goat immobilization of all 4 Tigers, with no draw mechanism.

## 9. Minimal Complete Game State

A fully restorable game state requires:

- Occupancy of each of the 25 nodes (empty, Tiger, or Goat)
- Number of Goats remaining in reserve (0–20)
- Number of Goats captured (0–5)
- Side to move (Goat or Tiger)
- Position history (only if a repetition rule variant is enabled)

## 10. FEN Notation

Board state serialized row by row, top to bottom, rows separated by `/`. Consecutive empty nodes represented by their count (1–5). `B` = Tiger, `G` = Goat. Followed by a space, the active player (`G` or `B`), a space, and the captured-goat count.

Starting position: `B3B/5/5/5/B3B G 0`

## 11. Move Notation

- **Goat placement (Phase 1):** `G` + destination node ID. Example: `G12` (Goat placed on node 12).
- **Slide move:** Piece type + origin ID + destination ID. Example: `B0006` (Tiger slides from 0 to 6).
- **Capture move:** Piece type + `x` + origin ID + destination ID. Example: `Bx0012` (Tiger at 0 captures Goat at 6, lands on 12).

## 12. Illegal Actions Summary

The following are always illegal:
- Moving to an occupied node
- Moving along a direction not connected by a board line
- Moving more than one edge in a non-capturing move
- Moving a Goat during Phase 1
- Any Goat jump or capture
- A Tiger jumping over another Tiger
- A Tiger jumping over more than one piece
- A Tiger jumping where the landing node is occupied, nonexistent, or not connected by a board line
- A Tiger making multiple captures in one turn
- Placing a Goat on an occupied node
- Placing a Goat when the reserve is empty
- Any move violating the active repetition rule (if enabled)
