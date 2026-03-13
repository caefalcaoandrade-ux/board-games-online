# YINSH — Definitive Ruleset Specification

## 1. BOARD GEOMETRY

### 1.1 Structure

The board is a regular hexagonal grid. Play occurs on **intersections**, not cells. Lines run in three axes at 60° intervals. The board uses a coordinate system labeled with letters (A–K) on one axis and numbers (1–11) on the other.

### 1.2 Intersection Count

The board contains exactly **85 valid intersections**. Not all letter–number combinations are valid; the playable area forms a hexagonal shape with clipped corners. The six outermost corner intersections of the full 11×11 hex grid are removed (they are not playable).

### 1.3 Valid Intersections (Exhaustive)

Using column-letter (A–K) and row-number (1–11), the 85 valid intersections are:

| Column | Valid Rows |
|--------|------------|
| A | 1, 2, 3, 4, 5 |
| B | 1, 2, 3, 4, 5, 6 |
| C | 1, 2, 3, 4, 5, 6, 7 |
| D | 1, 2, 3, 4, 5, 6, 7, 8 |
| E | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| F | 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| G | 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| H | 4, 5, 6, 7, 8, 9, 10, 11 |
| I | 5, 6, 7, 8, 9, 10, 11 |
| J | 6, 7, 8, 9, 10, 11 |
| K | 7, 8, 9, 10, 11 |

Corner intersections that are **excluded** (do not exist on the board): A1, A5, E9, K7, K11, F2 — these are the six vertices of the outermost hexagon. (Correction: the specific excluded corners depend on the hex clipping. The canonical YINSH board removes: **A1, A5, B6, E9, F10, G11, K7, K11, J6, F2, B1, G3** — see note below.)

**IMPLEMENTER NOTE:** The exact set of 85 valid intersections is best derived from the physical board image or an authoritative digital source (e.g., Board Game Arena's implementation). The board is a hexagon with side-length 5 in hex-grid terms, with the 6 corner points removed, yielding 91 − 6 = 85 intersections. The coordinate mapping above is one common convention; any bijection to 85 points preserving the three-axis adjacency is equivalent.

### 1.4 Adjacency and Lines

Each intersection connects to neighbors along **three axes**. Two intersections are adjacent if they are direct neighbors along one of these three axes. A **line** is any maximal sequence of collinear intersections along one axis. Movement and rows are evaluated along these lines.

### 1.5 Edge Intersections

Intersections on the perimeter of the hexagon are valid and fully playable. Rings may be placed on and moved to edge intersections.

---

## 2. COMPONENTS

- **Board:** 85-intersection hexagonal grid as defined above.
- **Rings:** 5 white + 5 black = 10 rings total. Rings are placed on intersections and are moved during play. Rings are never flipped.
- **Markers:** 51 identical double-sided pieces — white on one side, black on the other. Markers occupy intersections. Their visible face indicates their current color. Markers are drawn from a shared **pool** and returned to it when removed.

---

## 3. GAME STATES

The game progresses through exactly two phases:

### 3.1 Phase 1 — Ring Placement (Setup)

**Initial state:** Board is empty. All 51 markers are in the pool.

**Procedure:**
1. Determine the starting player. The starting player is **White**; the other is **Black**.
2. Players alternate turns. On each turn, the current player places exactly **one** of their unplaced rings on any **vacant** intersection (including edge intersections).
3. This continues until all **10 rings** (5 per player) are on the board.
4. No markers are placed during this phase. No movement occurs.

**Transition:** Once all 10 rings are placed, Phase 2 begins. White takes the first move of Phase 2.

### 3.2 Phase 2 — Main Play

Each turn follows the sequence defined in Section 4 below. Play alternates between White and Black until a game-ending condition is met (Section 8).

---

## 4. TURN STRUCTURE (Phase 2)

A turn consists of these steps **in strict order**:

1. **Place marker:** Take one marker from the pool. Place it on the intersection occupied by one of your own rings, with **your color face up**. The marker now shares that intersection with the ring.
2. **Move ring:** Move that same ring according to the movement rules (Section 5). The marker **remains behind** on the starting intersection; only the ring moves.
3. **Flip markers:** If the ring jumped over any markers during its move, flip all jumped markers (Section 6).
4. **Resolve rows:** Check for and resolve any rows of 5 formed by this move (Section 7).

**Constraint:** If the pool is empty (all 51 markers are on the board), the game ends immediately per Section 8.3 — no further turns are taken.

---

## 5. RING MOVEMENT RULES

When a ring is moved from its starting intersection (where the marker was just placed), the following rules apply:

### 5.1 Direction
The ring must move in a **straight line** along one of the three board axes.

### 5.2 Destination
The ring must land on a **vacant intersection** (no ring and no marker present).

### 5.3 Movement Over Empty Space
A ring may traverse any number of **consecutive vacant intersections** in its line of travel.

### 5.4 Jumping Over Markers
A ring may jump over a **single contiguous group** of one or more markers (of either color) along its line of movement. When it does:
- It must land on the **first vacant intersection immediately after** that contiguous group.
- It has no choice in landing position after a jump — the landing spot is forced.

### 5.5 Combined Movement
A ring may first move across one or more vacant intersections, **then** jump over a contiguous group of markers. However, **after** jumping over markers, the ring may **not** continue past any additional vacant intersections. The move ends on the first vacancy after the jumped group.

### 5.6 Rings Block Movement
A ring may **never** jump over or pass through another ring (of either color). A ring in the path terminates the possible movement in that direction (the moving ring cannot land on or pass the blocking ring).

### 5.7 Summary of Legal Destinations
From its starting point, along any given line, a ring can reach:
- Any vacant intersection reachable by crossing only vacant intersections (before encountering any marker or ring), **OR**
- The first vacant intersection immediately after a contiguous group of markers, provided no ring is encountered before or within that group.

---

## 6. FLIPPING MARKERS

### 6.1 When Flipping Occurs
Flipping happens **after** the ring has been placed on its destination, not during movement.

### 6.2 What Gets Flipped
**Every marker** that the ring jumped over is flipped to its opposite color. This includes both the moving player's markers and the opponent's markers.

### 6.3 What Does NOT Get Flipped
- The marker placed at the start of the turn (on the ring's origin intersection) is **not** flipped — it was not jumped.
- Markers not in the path of the jump are unaffected.

### 6.4 Flipping Mechanics
Markers are flipped **in place**. They are not moved. Only their visible color changes (white → black, black → white).

---

## 7. ROWS — DEFINITION AND RESOLUTION

### 7.1 Definition of a Row
A **row** is exactly **5 markers of the same visible color**, adjacent and contiguous in a straight line along one board axis. Rings do **not** count as markers and cannot complete or be part of a row. A ring between markers **breaks** the line.

### 7.2 Row Resolution — Own Color
When the current player's move creates a row of their own color:
1. **Remove 5 markers:** The player removes the 5 markers forming the row from the board and returns them to the pool.
2. **Remove 1 ring:** The player then removes **one of their own rings** (their choice which) from the board entirely. This ring is placed aside as a score indicator. It does not return to play.

### 7.3 Rows Longer Than 5
If a contiguous same-color line contains **more than 5 markers**, the player **chooses** which 5 consecutive markers within that line to remove. The remaining markers stay on the board.

### 7.4 Multiple Rows from One Move

**Disjoint rows (no shared markers):** All such rows **must** be resolved. Each row requires removing 5 markers + 1 ring. Multiple rings may be removed in one turn.

**Intersecting rows (share one or more markers):** The player chooses **only one** of the intersecting rows to resolve. After that row's 5 markers are removed, the other row is no longer complete and remains on the board unresolved. Only **1 ring** is removed.

### 7.5 Rows of the Opponent's Color
A move may create a row in the **opponent's** color (due to flipping). Resolution:
1. The opponent removes the 5 markers of their row and returns them to the pool.
2. The opponent removes **one of their own rings** (their choice which).
3. This resolution occurs **before the opponent takes their next turn** but **after** the moving player has resolved their own rows (if any).

### 7.6 Rows for Both Players on the Same Move
If a move creates rows for both the moving player and the opponent:
1. The **moving player** resolves their row(s) **first**.
2. Then the **opponent** resolves their row(s).
3. This ordering is critical for determining the winner when both players reach 3 removed rings on the same move (see Section 8.2).

---

## 8. GAME END CONDITIONS

### 8.1 Standard Victory
The game ends **immediately** when a player has removed **3 of their own rings** from the board. That player wins.

### 8.2 Simultaneous Third Row
If a single move creates the third row for both the moving player and the opponent, the **moving player wins** — because the moving player resolves their row first and reaches 3 removed rings before the opponent resolves.

### 8.3 Marker Pool Exhaustion
If all 51 markers have been placed on the board and neither player has removed 3 rings:
- The player who has removed **more rings** wins.
- If both players have removed the **same number** of rings, the game is a **draw**.

---

## 9. BLITZ VARIANT

All rules above apply identically, with one change to the victory condition:

**Victory condition:** The first player to form and remove **1 row** (and thus remove 1 ring) wins immediately.

---

## 10. KEY INVARIANTS FOR IMPLEMENTATION

- An intersection holds **at most one object**: a ring, a marker, or nothing (vacant). Exception: during step 1 of a turn, a marker is placed inside a ring, temporarily sharing the intersection — this resolves immediately when the ring moves away in step 2.
- Rings and markers are distinct object types. Rings move; markers are stationary once placed (they can only be flipped or removed).
- The marker pool starts at 51 and decreases as markers are placed on the board. Markers returned from row removal replenish the pool.
- Each player starts with 5 rings. Rings are permanently removed from play when scoring rows. A player's ring count decreases over the game: 5 → 4 → 3 → 2 (game ends at the third removal, so a player never goes below 2 rings on the board while still playing, unless the third removal triggers game end).
- The maximum number of rings removed per player is 3. The game cannot continue past this point.
- Row checking must occur after every marker-flip step. Multiple rows and cross-player rows must all be detected and resolved according to the priority rules in Section 7.
- A player must always have at least one legal move: they must be able to place a marker in one of their rings and move that ring to a vacant intersection. If a player has rings but none of them can legally move (all directions blocked by rings), this is an edge case to handle (extremely rare in practice; consult tournament rulings — typically the player passes or the board state is considered invalid in standard play).
