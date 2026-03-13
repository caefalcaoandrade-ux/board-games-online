# Havannah: Definitive Ruleset for Computational Implementation

## 1. Board Geometry

Havannah is played on a hex-hex board of side length S (standard sizes: S=8 or S=10). The board is a regular hexagon whose six outer edges each contain S cells.

### 1.1 Coordinate System

Use cube coordinates (q, r, s) where every cell satisfies the invariant q + r + s = 0. The set of all valid cells is:

    P = { (q, r, s) ∈ Z³ | q + r + s = 0 and max(|q|, |r|, |s|) ≤ S-1 }

Total playable cells: T = 3S² − 3S + 1 (S=8 → 169 cells; S=10 → 271 cells).

### 1.2 Adjacency

Two cells are adjacent if and only if their cube-coordinate distance is exactly 1. From any cell (q, r, s), the six neighbors are obtained by adding one of:

    (+1, 0, −1)  (+1, −1, 0)  (0, −1, +1)
    (−1, 0, +1)  (−1, +1, 0)  (0, +1, −1)

A neighbor is valid only if it is a member of P.

### 1.3 Distance

The distance between two cells p₁(q₁, r₁, s₁) and p₂(q₂, r₂, s₂) is:

    D(p₁, p₂) = max(|q₁−q₂|, |r₁−r₂|, |s₁−s₂|)

## 2. Board Topology: Corners, Sides, Interior

The boundary is the set of cells where max(|q|, |r|, |s|) = S−1. The boundary is partitioned into corners and sides. All remaining cells are interior.

### 2.1 Corners

There are exactly 6 corner cells. A cell is a corner if and only if exactly two of {|q|, |r|, |s|} equal S−1 (the third is necessarily 0). The six corners for any board of size S are:

    (S−1, −(S−1), 0)    (S−1, 0, −(S−1))    (0, S−1, −(S−1))
    (−(S−1), S−1, 0)    (−(S−1), 0, S−1)     (0, −(S−1), S−1)

Corner cells have exactly 3 valid neighbors.

### 2.2 Sides

There are exactly 6 sides. A side cell is any boundary cell that is not a corner — equivalently, exactly one of {|q|, |r|, |s|} equals S−1. Side cells have exactly 4 valid neighbors.

**Corners do not belong to any side.** This exclusion is mandatory for fork detection.

The 6 sides are the 6 connected boundary segments remaining after the 6 corners are removed. They are partitioned by which coordinate reaches the limit:

    Side 1: s = −(S−1), with 0 < q < S−1
    Side 2: q = S−1,    with −(S−1) < r < 0
    Side 3: r = −(S−1), with 0 < q < S−1
    Side 4: s = S−1,    with −(S−1) < q < 0
    Side 5: q = −(S−1), with 0 < r < S−1
    Side 6: r = S−1,    with −(S−1) < q < 0

Each side contains exactly S−2 cells.

### 2.3 Interior

Interior cells satisfy max(|q|, |r|, |s|) < S−1 and have exactly 6 valid neighbors.

## 3. Players and Turns

Two players: White and Black. The board starts empty. Players alternate turns, placing one stone of their own color on any empty cell. White moves first. Stones once placed are never moved, removed, captured, or changed in color.

## 4. Swap Rule

After White's first move, Black has a one-time choice: either place a Black stone normally, or swap — taking ownership of White's opening stone and becoming White (the former White player becomes Black and moves next). After this decision point, all subsequent turns are standard single-stone placements with strict alternation. The swap option occurs exactly once per game and is permanently disabled after turn 2.

## 5. Chains (Connected Components)

A chain is a maximal connected set of same-color stones under edge-adjacency. Two same-color stones belong to the same chain if and only if there exists a path of adjacent same-color stones connecting them. When a stone is placed adjacent to one or more existing same-color stones, their chains merge into a single chain. All three winning conditions are evaluated on chains.

## 6. Winning Conditions

A player wins immediately upon completing any one of the following structures with a single chain of their color. The game ends the instant a winning structure is formed.

### 6.1 Bridge

A chain that contains at least 2 distinct corner cells.

Detection: count how many of the 6 corner cells are occupied by stones in the chain. If ≥ 2, it is a bridge.

### 6.2 Fork

A chain that touches at least 3 distinct sides. A chain "touches" a side if it contains at least one cell belonging to that side. Corner cells within the chain do not count as contact with any side.

Detection: for each of the 6 sides, check whether the chain contains any cell from that side. If the chain touches ≥ 3 distinct sides, it is a fork.

### 6.3 Ring

A chain that forms a closed loop enclosing at least one cell. The enclosed cells may be empty or occupied by either color — their contents are irrelevant.

Detection (background flood-fill method): define the "background" as all cells in P not belonging to the active player's stones. Compute the connected components of the background under edge-adjacency. A background component is "enclosed" if it contains no corner cell and no side cell (it has zero intersection with the board boundary). If any enclosed background component exists, the active player has completed a ring. The minimum ring size is 6 stones.

## 7. End of Game

The game ends when either:

1. A player completes a bridge, fork, or ring — that player wins immediately.
2. The board is completely filled and neither player has any winning structure — the game is a draw.

Only the active player's chains need to be evaluated after their move, because a player's stone placement can only advance their own structures, never the opponent's. Draws are theoretically possible but extremely rare in practice.

## 8. Static Data to Precompute at Initialization

For a given board size S, precompute and store as immutable structures:

- The full set of valid cells P.
- The 6 corner cell coordinates.
- The 6 side cell sets (each side as a distinct labeled group), with corners excluded.
- The neighbor list for every cell in P.

## 9. State Representation

The game state consists of:

- The color assignment (White/Black) of every occupied cell, or empty.
- Whose turn it is.
- Whether the swap option is still available (true only before Black's first action).
- The chain membership of every occupied cell (maintained incrementally via union on placement).
- For each chain: which corners it contains, which sides it touches.

## 10. Move Validation

A move to cell p is legal if and only if:

1. p is a member of P (valid coordinate).
2. p is currently empty.

The only exception is the swap action on turn 2, which is an alternative to placing a stone.

## 11. Post-Move Evaluation Sequence

After each stone placement:

1. Merge the new stone's chain with all adjacent same-color chains.
2. Update the resulting chain's corner count and side-contact set.
3. Check bridge: chain corner count ≥ 2.
4. Check fork: chain distinct side contacts ≥ 3.
5. Check ring: run background flood-fill; if any background component is fully enclosed (touches no boundary cell), a ring exists.
6. If any check is true, the active player wins and the game terminates.
7. If no win and no empty cells remain, the game is a draw.
8. Otherwise, pass the turn to the other player.
