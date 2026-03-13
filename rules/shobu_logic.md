# SHŌBU — Definitive Ruleset for Programmatic Implementation

## 1. Global Structure

SHŌBU is a deterministic, perfect-information, zero-sum game for exactly 2 players. There are no random elements, no hidden state, and no simultaneous actions.

## 2. Board Topology

The play area consists of **four independent 4×4 grids** (sub-boards), each containing 16 squares. No stone may ever move from one sub-board to another; each sub-board is a fully isolated coordinate space.

The four sub-boards are arranged in a 2×2 macro-layout and are separated by two conceptual axes:

- **Horizontal axis** (the rope): divides the macro-layout into two **regions** — one per player.
- **Vertical axis**: separates left boards from right boards.

Each sub-board has two immutable properties:

| Board ID | Color | Region Owner | Quadrant |
|----------|-------|-------------|----------|
| B0 | Dark | Player 1 (South) | Bottom-Left |
| B1 | Light | Player 1 (South) | Bottom-Right |
| B2 | Light | Player 2 (North) | Top-Left |
| B3 | Dark | Player 2 (North) | Top-Right |

**Homeboards**: The two sub-boards in a player's own region are that player's homeboards. Each player has exactly one dark homeboard and one light homeboard.

- Player 1 homeboards: {B0, B1}
- Player 2 homeboards: {B2, B3}

**Color-parity groupings** (used for aggressive move targeting):

- Dark boards: {B0, B3}
- Light boards: {B1, B2}

## 3. Coordinate System

Each square is uniquely identified by a tuple **(b, x, y)** where:

- **b** ∈ {0, 1, 2, 3} — the sub-board identifier.
- **x** ∈ {1, 2, 3, 4} — column, incrementing left-to-right from Player 1's perspective.
- **y** ∈ {1, 2, 3, 4} — row, incrementing bottom-to-top (South-to-North) from Player 1's perspective.

A coordinate is **in-bounds** if and only if 1 ≤ x ≤ 4 and 1 ≤ y ≤ 4. Any coordinate violating this is out-of-bounds.

Each square holds at most one stone.

## 4. Pieces and Initial State

There are 32 stones: 16 Black (Player 1) and 16 White (Player 2).

At setup, each sub-board receives exactly 4 Black stones and 4 White stones, placed as follows:

- **Player 1 (Black)** stones occupy row y=1 (the row nearest Player 1) on every sub-board: positions (b, 1, 1), (b, 2, 1), (b, 3, 1), (b, 4, 1) for each b ∈ {0, 1, 2, 3}.
- **Player 2 (White)** stones occupy row y=4 (the row nearest Player 2) on every sub-board: positions (b, 1, 4), (b, 2, 4), (b, 3, 4), (b, 4, 4) for each b ∈ {0, 1, 2, 3}.

Rows y=2 and y=3 on all boards begin empty.

## 5. Turn Order

Players alternate turns. **Black (Player 1) takes the first turn.** This alternation continues until a terminal state is reached.

## 6. Turn Structure

Each turn is an **atomic transaction** consisting of exactly two sequential phases, both mandatory:

1. **Phase I — Passive Move**
2. **Phase II — Aggressive Move**

A turn is complete and committed only after both phases resolve successfully. If Phase II cannot be legally executed given the vector established in Phase I, then Phase I is invalid and must be retracted — the player must choose a different passive move.

## 7. Movement Vectors

All movement in SHŌBU is defined by a translation vector **V = ⟨Δx, Δy⟩** applied to a stone's current (x, y) position within its sub-board.

A vector V is **structurally valid** if and only if:

1. **max(|Δx|, |Δy|) ∈ {1, 2}** — the Chebyshev distance is exactly 1 or 2.
2. **If both |Δx| > 0 and |Δy| > 0, then |Δx| = |Δy|** — diagonal movement must be at a perfect 45° angle.

This yields exactly **16 valid vectors**: 8 directions × 2 magnitudes.

The **magnitude** (distance in spaces) of a vector is defined as max(|Δx|, |Δy|), which is either 1 or 2.

The **unit direction** of a vector is **û = ⟨sign(Δx), sign(Δy)⟩**, where sign(0) = 0. For a magnitude-2 vector, the **intermediate square** is the square at offset û from the origin.

## 8. Phase I — Passive Move Rules

The active player selects one of their own stones on one of their homeboards and moves it along a valid vector. The following conditions must **all** be satisfied:

1. **Ownership**: The stone at the origin must belong to the active player.
2. **Homeboard constraint**: The origin sub-board must be one of the active player's homeboards. (Player 1: b ∈ {0, 1}; Player 2: b ∈ {2, 3}.)
3. **Board isolation**: The stone remains on the same sub-board (no cross-board movement).
4. **Valid vector**: The computed vector V must be one of the 16 structurally valid vectors.
5. **Destination in-bounds**: The target square (x₀ + Δx, y₀ + Δy) must satisfy 1 ≤ x ≤ 4 and 1 ≤ y ≤ 4.
6. **Path completely clear**: Every square along the path must be empty (no stone of either color).
   - If magnitude = 1: the destination square must be empty.
   - If magnitude = 2: both the intermediate square and the destination square must be empty.
7. **No pushing**: The passive move cannot push any stone. (This is enforced by rule 6 — the path and destination must be empty.)

If all conditions are met, the system caches:
- The vector **V_passive = ⟨Δx, Δy⟩**
- The **color of the origin sub-board** (dark or light)

The stone is tentatively moved. This move is provisional until Phase II succeeds.

## 9. Phase II — Aggressive Move Rules

The active player selects one of their own stones on a valid target board and moves it using the exact same vector established in Phase I. The following conditions must **all** be satisfied:

1. **Ownership**: The stone at the origin must belong to the active player.
2. **Color-parity constraint**: The aggressive move must be on a sub-board whose color is the **opposite** of the passive move's sub-board. The aggressive move is **not** restricted to the active player's home region — it may be on either board of the required color.
   - If passive was on a Dark board → aggressive must be on a Light board (B1 or B2).
   - If passive was on a Light board → aggressive must be on a Dark board (B0 or B3).
3. **Exact vector replication**: The vector applied must be identical to V_passive — same direction and same magnitude.
4. **Active stone stays in-bounds**: The destination square for the moving stone must be in-bounds (1 ≤ x ≤ 4 and 1 ≤ y ≤ 4). A player may never move their own stone off the board.
5. **Push legality** (see Section 10 below): The path may contain **at most one** opponent stone, and **zero** friendly stones. That opponent stone may be pushed. No more than one stone may be pushed.

## 10. Push (Displacement) Mechanics

Pushing occurs **only** during the aggressive move and is **never mandatory**. An aggressive move may push at most **one** opponent stone. It may **never** push a friendly stone, and may **never** push two or more stones.

The pushed stone is displaced along the same unit direction û as the movement vector. The detailed resolution depends on the magnitude of the vector:

### Magnitude 1 (V has Chebyshev distance 1):

- The aggressive stone moves from origin O to destination D = O + V.
- **If D is empty**: move succeeds, no push occurs.
- **If D contains a friendly stone**: move is **illegal**.
- **If D contains an opponent stone**: a push is attempted. The opponent stone would be displaced to D + û (one square further along the same direction).
  - If D + û is **in-bounds and empty**: push succeeds. Opponent stone moves to D + û; aggressive stone moves to D.
  - If D + û is **out-of-bounds**: push succeeds. Opponent stone is **permanently removed from the game**; aggressive stone moves to D.
  - If D + û is **in-bounds but occupied** (by any stone): move is **illegal** (cannot cascade-push).

### Magnitude 2 (V has Chebyshev distance 2):

- The aggressive stone moves from origin O through intermediate M = O + û to destination D = O + V.
- **If M contains a friendly stone**: move is **illegal**.
- **If M is empty and D is empty**: move succeeds, no push occurs.
- **If M is empty and D contains a friendly stone**: move is **illegal**.
- **If M is empty and D contains an opponent stone**: a push is attempted. The opponent stone at D would be displaced to D + û.
  - If D + û is **in-bounds and empty**: push succeeds. Opponent stone moves to D + û; aggressive stone moves to D.
  - If D + û is **out-of-bounds**: push succeeds. Opponent stone is **removed from the game**; aggressive stone moves to D.
  - If D + û is **occupied** (by any stone): move is **illegal**.
- **If M contains an opponent stone**: a push is attempted. The opponent stone at M would be displaced ahead of the aggressor. The system must verify:
  - D must be **empty** (if D is occupied by any stone, the move is illegal — cannot push two stones or push through a blocking stone).
  - The displaced opponent stone lands at D (= M + û), and the aggressive stone also lands at D? — **No.** Clarification: the opponent stone at M is pushed by 1 in direction û to D. The aggressive stone moves the full 2 squares to D. This is a conflict — both cannot occupy D. **Correct resolution**: When the aggressive stone moves 2 and encounters an opponent at the intermediate square M, the opponent stone is pushed along the vector, ending at D (= M + û). The aggressive stone occupies D as well — this is contradictory. **Actual correct resolution per the rules**: The opponent stone at M is displaced continuously ahead of the moving stone. The opponent ends up at D + û (one square beyond D, not at D). The aggressive stone ends at D.
    - If D + û is **in-bounds and empty**: push succeeds. Opponent stone moves to D + û; aggressive stone moves to D.
    - If D + û is **out-of-bounds**: push succeeds. Opponent stone is **removed from the game**; aggressive stone moves to D.
    - If D + û is **occupied** (by any stone): move is **illegal**.
  - Additionally, **D itself must be empty** for the aggressive stone to land there. If D contains any stone, the move is illegal (would require pushing two stones or pushing a friendly stone).

**Summary of magnitude-2 push resolution**: Regardless of whether the single opponent stone is at M or D, the displaced opponent always ends up at D + û. The aggressive stone always ends up at D. The square D must be empty (or become empty via the displacement of the opponent stone from D). No more than one opponent stone may exist anywhere in the path {M, D}, and zero friendly stones may be in {M, D}.

### Permanent Removal

A stone pushed out-of-bounds is removed from the game permanently and never returns.

## 11. Phase I–II Dependency

If the active player's chosen passive move vector admits **no legal aggressive move** on any valid target board with any of the player's stones, then the passive move is invalid and must be undone. The player must select a different passive move that enables at least one legal aggressive move.

## 12. Win Condition

After each completed turn (both phases committed), evaluate all four sub-boards:

- For each sub-board b, count the stones of each player.
- If **any** sub-board contains **zero** stones belonging to a player, that player **loses immediately** and the opponent wins.

The win check occurs only after a turn is fully committed. Because only one opponent stone can be removed per turn, it is impossible for both players to reach zero on the same board in the same turn.

Only **one** board needs to be cleared of an opponent's stones to win. Clearing multiple boards is not required.

## 13. No-Legal-Move Condition

If the active player has **no valid turn** — meaning no combination of passive move + aggressive move is legal across all their homeboards and all target boards — that player **loses the game**.

## 14. Repetition / Draw

No official repetition rule exists in the published ruleset. For implementation robustness, the system may optionally maintain a hash ledger of all completed game states (piece positions + active player). If an exact state recurs, the game is declared a draw. However, this is not part of the core printed rules.

## 15. Invariants (always true throughout the game)

- Stones never transfer between sub-boards.
- Each square holds at most one stone.
- Removed stones never return.
- Players may move in any of the 8 directions (forward, backward, sideways, diagonal) — there is no directional restriction by player identity.
- A player may never move their own stone off the board.
- The passive move may never push any stone.
- The aggressive move may push at most one opponent stone and zero friendly stones.
- Both phases of a turn are mandatory; a turn is not complete until both are executed.
