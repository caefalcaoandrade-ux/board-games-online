# Tumbleweed — Definitive Ruleset

## 1. Game Identity

Tumbleweed is a two-player, deterministic, perfect-information territorial abstract game. There is no randomness, no hidden information, and no draws. The game was designed by Mike Zapawa in 2020.

## 2. Board

The board is a hexhex (regular hexagon of hexagonal cells) parameterized by size S, where S is the number of cells along each outer edge. The default competitive size is S = 8. Supported sizes range from S = 5 (minimum playable) to S = 14.

**Total cells:** 3S(S − 1) + 1.

**Coordinate system:** Cube coordinates (x, y, z) with the constraint x + y + z = 0. A cell is valid if and only if max(|x|, |y|, |z|) ≤ S − 1. The center cell is (0, 0, 0).

**Six cardinal directions** (unit vectors):

| Direction   | Vector (Δx, Δy, Δz) |
|-------------|----------------------|
| D0          | (+1, 0, −1)          |
| D1          | (+1, −1, 0)          |
| D2          | (0, −1, +1)          |
| D3          | (−1, 0, +1)          |
| D4          | (−1, +1, 0)          |
| D5          | (0, +1, −1)          |

Each direction Di has an opposite direction D(i+3 mod 6), obtained by negating the vector.

## 3. Stacks

A stack is the fundamental game entity. Each cell holds at most one stack. A stack has exactly two properties, both immutable once placed:

- **Color:** Red, White, or Neutral.
- **Height:** An integer from 1 to 6.

Height has strictly defensive significance: a stack of height H can only be replaced by a stack of height strictly greater than H. Height does not affect attack power or visibility range. A 1-stack and a 6-stack both project exactly one line of sight and both block lines of sight identically.

## 4. Line of Sight (LOS)

**Definition:** From any cell C, cast a ray in each of the six cardinal directions. Step outward one cell at a time. The first occupied cell encountered (if any) is visible from C in that direction. All cells beyond a visible stack are blocked. Empty cells do not block. If the ray exits the board before hitting a stack, nothing is visible in that direction.

**Visibility set V(C):** The set of all stacks visible from cell C. Since there are six directions, 0 ≤ |V(C)| ≤ 6.

**Friendly LOS (fLOS):** The subset of V(C) whose stacks match the active player's color. The count of fLOS from C determines the height of any new stack placed at C.

**Enemy LOS (eLOS):** The subset of V(C) whose stacks match the opponent's color.

**Neutral stacks** block line of sight (they are opaque like any stack) but are never friendly to either player and contribute zero to any player's fLOS count.

## 5. Setup Phase

The setup is a strict sequence involving two roles: the Host (first actor) and the Guest (second actor).

**Step 1 — Neutral placement:** The Host places one Neutral stack of height 2 on the center cell (0, 0, 0). This is mandatory and fixed.

**Step 2 — Seed placement:** The Host places one Red 1-stack and one White 1-stack on any two distinct empty cells. The Host has full discretion over their positions.

**Step 3 — Pie rule (color choice):** The Guest examines the board and chooses to play as either Red or White for the remainder of the game.

**Step 4 — Transition:** The setup phase ends. Red moves first. Play alternates strictly: Red, White, Red, White, and so on.

## 6. Legal Actions (Main Game Loop)

On each turn, the active player must perform exactly one of the following three actions.

### 6.1 Settle an Empty Cell

Target an empty cell C. Compute fLOS(C) for the active player. The move is legal if and only if fLOS(C) ≥ 1. If legal, place a new stack of the active player's color on C with height equal to fLOS(C).

### 6.2 Replace an Occupied Cell

Target an occupied cell C containing a stack of height H_existing. Compute fLOS(C) for the active player. Call this H_new. The move is legal if and only if fLOS(C) ≥ 1 AND H_new > H_existing (strictly greater). If legal, remove the existing stack entirely and place a new stack of the active player's color on C with height H_new.

This single rule governs three sub-cases uniformly:

- **Capture (opponent's stack):** The opponent's stack is removed and replaced.
- **Capture (neutral stack):** The neutral stack (height 2) is removed and replaced. Requires H_new ≥ 3.
- **Reinforcement (own stack):** The player's own stack is replaced with a taller one.

Equal-height or lower-height replacement is always illegal.

### 6.3 Pass

Passing is always legal. It requires no conditions. No board state changes occur.

## 7. State Mutations

**After any placement (settle or replace):** Exactly one cell changes. No other cells are affected. There is no movement, no chain reactions, no multi-cell effects. Stack heights on all other cells remain unchanged regardless of how lines of sight may have shifted.

**Consecutive pass counter:** Maintained as a global integer. Incremented by 1 after each pass. Reset to 0 after any non-pass move.

**Turn alternation:** After every action (including pass), the active player switches.

## 8. Game Termination

The game ends when either condition is met:

1. Two consecutive passes occur (one by each player in immediate succession).
2. Neither player has any legal non-pass move available.

## 9. Scoring

Upon termination, freeze the board and compute scores.

### 9.1 Owned Cells

Each occupied cell scores exactly 1 point for the color of its stack. Stack height is irrelevant to scoring; a 6-stack and a 1-stack each score 1 point.

### 9.2 Controlled Empty Cells

For each empty cell C, cast all six rays and count visible Red stacks (Count_Red) and visible White stacks (Count_White). Neutral stacks do not count for either side.

- If Count_Red > Count_White → cell is controlled by Red (+1 to Red).
- If Count_White > Count_Red → cell is controlled by White (+1 to White).
- If Count_Red = Count_White (including 0 = 0) → cell is contested, scores for neither.

### 9.3 Final Score

Total_Red = Owned(Red) + Controlled(Red).
Total_White = Owned(White) + Controlled(White).

The player with the strictly higher total wins.

## 10. No-Draw Guarantee

Tumbleweed cannot end in a draw. Standard board sizes (e.g., hexhex-8 with 169 cells) contain an odd total cell count, and the territorial scoring mechanic ensures a strict winner always emerges. If consecutive passes would produce a tied score, the passes are premature and play must continue until a unique winner is determined.

## 11. Legality Checklist (Summary)

A move to cell C by the active player is legal if and only if:

- C is empty AND fLOS(C) ≥ 1; OR
- C is occupied with height H AND fLOS(C) > H; OR
- The action is a pass.

No other moves exist.

## 12. Key Invariants

- A cell holds at most one stack at any time.
- Stack height is set at placement and never changes unless the stack is replaced.
- Stack heights are always integers in {1, 2, 3, 4, 5, 6}.
- A height-6 stack is immortal (cannot be replaced, since no stack can exceed 6).
- The neutral stack exists only from setup; once captured, it is gone permanently.
- Lines of sight are computed instantaneously at the moment of each proposed move; they are not stored properties of the board.
- All information is public at all times. No hidden state exists.
