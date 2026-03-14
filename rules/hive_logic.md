# Hive — Definitive Unified Ruleset (Complete Edition)

## 1. Game Definition

Hive is a two-player, zero-chance, perfect-information abstract strategy game played on a virtual infinite hexagonal grid. There is no physical board; the pieces themselves form the playing area (the "hive"). The game includes the base set plus three official expansion pieces: Mosquito, Ladybug, and Pillbug.

## 2. Coordinate System

The game space is an unbounded hexagonal lattice. Each position is identified by axial coordinates (q, r) derived from the cube coordinate system (x, y, z) where x + y + z = 0 and z = -q - r.

Each position has exactly six neighbors, reached by adding one of six direction vectors:

| Direction   | (Δq, Δr) | Cube (Δx, Δy, Δz) |
|-------------|-----------|---------------------|
| North       | (0, +1)   | (0, +1, -1)         |
| North-East  | (+1, 0)   | (+1, 0, -1)         |
| South-East  | (+1, -1)  | (+1, -1, 0)         |
| South       | (0, -1)   | (0, -1, +1)         |
| South-West  | (-1, 0)   | (-1, 0, +1)         |
| North-West  | (-1, +1)  | (-1, +1, 0)         |

A third axis, height h, tracks vertical stacking. Ground level is h = 0. A piece stacked atop another occupies h = (number of pieces below it). The full position of any piece is the tuple (q, r, h). Two positions are horizontally adjacent if and only if their (q, r) coordinates differ by exactly one direction vector, regardless of h.

## 3. Pieces

Each player has 14 pieces:

| Piece        | Count | Movement Paradigm              |
|--------------|-------|--------------------------------|
| Queen Bee    | 1     | 1 crawl                        |
| Spider       | 2     | Exactly 3 crawls               |
| Beetle       | 2     | 1 step (crawl, climb, or fall) |
| Grasshopper  | 3     | 1 jump in a straight line      |
| Soldier Ant  | 3     | Any number of crawls            |
| Mosquito     | 1     | Copies adjacent piece's ability |
| Ladybug      | 1     | 1 climb + 1 crawl/climb + 1 fall (must start and end on ground, must be off ground in between) |
| Pillbug      | 1     | 1 crawl; OR special ability     |

Total: 28 pieces (14 per player).

## 4. Terminology

- **Hive**: All pieces currently in play, forming one connected structure.
- **Reserve/Hand**: A player's pieces not yet placed.
- **Cell**: A position on the hexagonal grid. A cell is empty if it contains zero pieces, occupied if it contains one or more.
- **Stack**: One or more pieces occupying the same cell. The topmost piece is the only one that can act.
- **Color of a cell/stack**: The color of the topmost piece in that cell.
- **Covered**: A piece with one or more pieces on top of it. Covered pieces cannot move and cannot use powers.
- **Pinned**: A piece located at an articulation point of the hive graph. Pinned pieces cannot move but CAN use powers (relevant to Pillbug/Mosquito).
- **Resting**: A piece that was moved (or was moved by a Pillbug/Mosquito-as-Pillbug) during the previous turn. Resting pieces cannot move and cannot be moved by Pillbug/Mosquito-as-Pillbug on the current turn.
- **Ground**: The playing surface; h = 0.
- **Level**: A piece's position within its stack, equal to the number of pieces below it.
- **Height of a cell**: The number of pieces in the stack at that cell (0 if empty).

## 5. Objective and End Conditions

A player wins by causing all six cells adjacent to the opponent's Queen Bee to be occupied (by pieces of either color).

The game ends immediately when any Queen Bee is fully surrounded:
- If only one Queen Bee is surrounded: that Queen's owner loses.
- If both Queen Bees are surrounded on the same turn: the game is a draw.
- If both players have exactly repeated the same board position three times: the game is a draw. (Board positions must be normalized relative to a fixed anchor, such as one Queen's position, to account for translational equivalence.)
- A draw may also be agreed upon by both players if forced repetition with no resolution is apparent.

## 6. Turn Structure

Players alternate turns, starting with White. On each turn a player must perform exactly one action:
- **Place** a piece from reserve into the hive, OR
- **Move** one of their own pieces already in play (only if their Queen Bee has been placed), OR
- **Use a power** (Pillbug special ability or Mosquito copying Pillbug) instead of moving (only if their Queen Bee has been placed), OR
- **Pass** — if and only if the player has no legal placement and no legal move/power. Passing is never voluntary.

A forced pass causes the opponent to take the next turn. This can result in the same player acting multiple consecutive turns.

## 7. Placement Rules

A piece is placed from the player's reserve onto an empty ground-level cell (h = 0).

**Turn 1 (White):** White places any one piece (except the Queen Bee) at the grid origin. No adjacency constraints.

**Turn 2 (Black):** Black places any one piece (except the Queen Bee) adjacent to White's first piece. This is the only time a piece may be placed adjacent to an opponent's piece.

**Turn 3 onward:** A newly placed piece must satisfy ALL of:
1. The destination cell is empty (h = 0).
2. The destination cell is adjacent to at least one cell whose topmost piece belongs to the placing player.
3. The destination cell is NOT adjacent to any cell whose topmost piece belongs to the opponent.
4. Sliding access is NOT required for placement — a piece may be placed into a surrounded empty cell if it satisfies conditions 1–3.

**Queen Bee placement obligation:** The Queen Bee may be placed on turns 2, 3, or 4. If unplaced by turn 4, it MUST be placed on turn 4 (no other action is legal).

**Tournament Opening Rule (default):** Neither player may place their Queen Bee on turn 1.

Once placed, a piece can never be removed from the game.

## 8. Global Movement Constraints

These constraints apply to ALL movement actions unless a piece's rules explicitly exempt it.

### 8.1 One Hive Rule

All pieces in play must remain a single connected group at all times. This includes during transit — a move that temporarily disconnects the hive is illegal even if the final position would reconnect it.

Implementation: Model the hive as an undirected graph G = (V, E) where vertices are occupied cells and edges are adjacencies. Any piece at an articulation point (cut vertex) of this graph cannot be moved (it is "pinned"). Use Tarjan's algorithm or equivalent to identify articulation points before generating moves.

For multi-step moves (Spider, Ant, Ladybug), the moving piece must maintain contact with the remaining hive at every intermediate step. Formally: after temporarily removing the moving piece from its origin, the remaining graph must be connected, AND at each step the piece must be adjacent to at least one piece in the hive.

### 8.2 Freedom to Move (Sliding Constraint)

A piece moving horizontally (crawling) from cell S to adjacent cell D must physically slide between the two cells L and R that are mutually adjacent to both S and D.

**Ground-level gate check:** The slide from S to D is blocked if BOTH L and R are occupied at the piece's current level or above. If at least one of L, R is empty or shorter, the slide is permitted.

**Vertical gate check (Beetle gates):** When a piece climbs, falls, or crawls at elevation h > 0, the gate check compares the heights of the stacks at L and R against the relevant elevations. A step from S to D is blocked if the height of the stack at L ≥ max(level_of_mover_at_S, height_of_D) AND the height of the stack at R ≥ max(level_of_mover_at_S, height_of_D). (The mover's own presence in the stack at S is excluded from the height calculation.)

**Exemptions from Freedom to Move:** The Grasshopper (which jumps) is fully exempt. The Ladybug's vertical transitions follow the gate check as applicable.

### 8.3 Ownership

A player may only move their own pieces on their turn. The sole exception is the Pillbug special ability (and Mosquito copying it), which can move an adjacent piece of either color.

### 8.4 No Backtracking

During any multi-step move (Spider, Ant, Ladybug), the moving piece cannot enter a cell it has already occupied during that move. A null move (ending where it started) is never legal.

## 9. Basic Maneuvers

All piece movements are composed of these atomic maneuvers:

### 9.1 Crawl
A purely horizontal move from cell S to adjacent cell D while the piece remains at the same level. Requirements:
- D's height (before the piece arrives) equals the piece's current level.
- The gate formed by L and R is not blocking (see §8.2).
- The piece maintains contact with the hive: either the piece's level > 0, or L's height > 0, or R's height > 0 (at least one neighbor along the path is occupied).
- After crawling, the piece drops to the lowest unoccupied level in the destination cell.

### 9.2 Climb
A vertical ascent to the height of an adjacent occupied cell, followed immediately by a legal crawl onto that cell. The piece's level increases to the destination cell's current height. The combined climb+crawl is subject to the gate check at the destination elevation.

### 9.3 Fall
A crawl at the piece's current level (horizontally, subject to gate check), followed by a vertical descent to the destination cell's height. The piece's level decreases to match the destination.

### 9.4 Jump
An instantaneous move directly from one cell to another, NOT subject to the Freedom to Move rule. Only the Grasshopper uses this maneuver.

## 10. Piece Movement Rules

### 10.1 Queen Bee
- 1 crawl.

### 10.2 Beetle
- 1 step: an optional climb followed by 1 crawl. This allows the Beetle to:
  - Crawl on the ground like a Queen.
  - Climb onto an adjacent occupied cell (moving on top of the hive).
  - Move from one occupied cell to another while on top of the hive.
  - Fall from the top of the hive down to ground level.
  - Drop into surrounded spaces inaccessible to ground-level sliders.
- A piece beneath a Beetle cannot move.
- A cell with a Beetle on top counts as the Beetle's color for placement purposes.
- Beetles cannot be placed directly on top of the hive; they must enter play at ground level.
- Beetle movement IS subject to the gate check (including Beetle gates at elevation).

### 10.3 Grasshopper
- Does NOT crawl. Moves by jumping.
- Jumps in a straight line along one of the six hex directions.
- Must jump over at least one occupied cell.
- Must land in the first empty cell encountered along that line.
- Cannot jump over any empty cell (the line of occupied cells must be contiguous).
- Exempt from Freedom to Move. Can jump into or out of surrounded spaces.
- Always lands at ground level.

### 10.4 Spider
- Exactly 3 crawls, no more, no less.
- Each crawl must independently satisfy the Freedom to Move rule.
- No backtracking: cannot revisit any cell during the 3-step path.
- Must maintain hive contact at every intermediate step.

### 10.5 Soldier Ant
- Any number of crawls (one or more).
- Each crawl must independently satisfy the Freedom to Move rule.
- No backtracking: cannot revisit any cell during the sequence.
- Must maintain hive contact at every step.
- Implementation: BFS/flood-fill of all reachable ground-level perimeter cells, checking Freedom to Move at each transition.

### 10.6 Mosquito
- Has no inherent movement ability.
- At the start of its turn, it copies the movement ability or power of any non-Mosquito piece that is the topmost piece of an adjacent stack.
- If touching multiple different piece types, it may use any one of their abilities.
- If touching ONLY other Mosquitoes (and no other piece types), it cannot move at all.
- If the Mosquito copies Beetle and climbs to h > 0, it is locked into Beetle movement until it descends back to h = 0. While on top of the hive, it ignores what it is adjacent to and moves only as a Beetle.
- The Mosquito can copy the Pillbug's special ability (see §10.8) even if the adjacent Pillbug is resting/stunned, provided the Pillbug is not covered.

### 10.7 Ladybug
- Exactly 3 steps with a fixed profile:
  1. Step 1: Climb onto an adjacent occupied cell (must go on top of the hive).
  2. Step 2: Crawl or climb to another occupied cell (must stay on top of the hive).
  3. Step 3: Fall into an adjacent empty cell at ground level (must descend to h = 0).
- Must start on the ground and end on the ground.
- Must NOT be on the ground at any intermediate step.
- Cannot end where it started.
- Gate checks apply to each step.
- Because it travels over the top, it can reach surrounded ground-level cells inaccessible to Ants/Spiders.

### 10.8 Pillbug
**Ordinary movement:** 1 crawl (identical to Queen Bee).

**Special ability (used instead of moving):** Move an adjacent piece (friendly or enemy) by lifting it onto the Pillbug's cell, then placing it down into a different empty cell adjacent to the Pillbug. Formally: target piece executes 1 climb onto the Pillbug, then 1 crawl to an adjacent cell, then 1 fall into that empty cell.

**Restrictions on the special ability — the Pillbug CANNOT:**
1. Target a piece that is covered (part of a stack with something on top).
2. Target a piece if the Pillbug itself is covered.
3. Target a piece whose removal would split the hive (One Hive Rule).
4. Target a piece if the climb onto the Pillbug or the fall into the destination is blocked by a gate (Beetle gate check applies).
5. Target a piece that was moved (by any means) on the opponent's immediately preceding turn (the "resting" piece).
6. Use the ability if the Pillbug itself was moved on the opponent's immediately preceding turn (the Pillbug is "resting").

**Stun/Rest effect:** Any piece moved by the Pillbug's special ability becomes "resting" and cannot move or be moved by any Pillbug/Mosquito-as-Pillbug on the next player's turn. This status clears after that turn.

## 11. Move Legality Checklist

### A placement is legal if ALL of:
1. The piece comes from the player's reserve.
2. The destination is an empty ground-level cell.
3. The destination is adjacent to the existing hive (except for the very first piece of the game).
4. The placement satisfies the color-adjacency rule for the current turn number (see §7).
5. If it is the player's 4th turn and the Queen Bee is unplaced, the piece MUST be the Queen Bee.
6. Neither player may place the Queen Bee on their 1st turn (Tournament Opening Rule).

### A move/power is legal if ALL of:
1. The player's Queen Bee has already been placed.
2. The piece performing the action is owned by the player (except targets of Pillbug ability).
3. The piece is the topmost piece in its stack (not covered).
4. The piece is not resting.
5. The move does not violate the One Hive Rule at any point during transit.
6. The move satisfies Freedom to Move (gate checks) at every step where applicable.
7. The move matches the exact movement specification of the piece type (§10).
8. No backtracking occurs during multi-step moves.
9. All Pillbug-specific restrictions (§10.8) are satisfied if the Pillbug ability is being used.

## 12. State Evaluation Pipeline (Per Turn)

1. **Clear resting flags** from pieces that were flagged as resting on the previous turn.
2. **Check forced Queen placement:** If the active player's turn count = 4 and their Queen Bee is unplaced, restrict the entire action space to Queen Bee placement only.
3. **Identify articulation points** in the hive graph (Tarjan's algorithm). Pinned pieces cannot move but can use powers.
4. **Generate legal placements:** Iterate empty cells adjacent to allied-colored cells; filter out any adjacent to enemy-colored cells (except turns 1–2); verify ground level.
5. **Generate legal moves/powers:** For each non-pinned, non-covered, non-resting piece belonging to the active player, compute destinations per piece type rules, applying Freedom to Move and One Hive checks at each step.
6. **If no legal action exists:** Force pass; transfer turn to opponent.
7. **Execute chosen action:** Update piece positions, set resting flags on any piece moved by Pillbug ability.
8. **Evaluate terminal conditions:**
   - Count occupied neighbors of both Queens. If either has 6/6: game ends.
   - If both have 6/6 simultaneously: draw.
   - If only one has 6/6: that Queen's owner loses.
9. **Hash the board state** (normalized to a fixed anchor point). If this state has occurred 3 times in the game history: draw.
10. **Increment turn counter, swap active player.**

## 13. Board State Hashing

Because the hive has no fixed position on the infinite grid, board states must be normalized before comparison. Normalize all piece coordinates relative to a fixed reference piece (e.g., White's Queen Bee) so that translationally identical states produce the same hash. The hash must encode: all piece positions (q, r, h), piece types and owners, which pieces are resting, and whose turn it is.
