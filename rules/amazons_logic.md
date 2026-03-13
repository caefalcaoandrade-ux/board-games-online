# Game of the Amazons — Definitive Ruleset Specification

## 1. Board

A square grid of 10 columns (files a–j, left to right) × 10 rows (ranks 1–10, bottom to top). Total: 100 squares. Board coloring is cosmetic and has no rules effect.

### Coordinate system

| Notation | Mapping |
|---|---|
| Algebraic | File letter + rank number (e.g. `d1`, `g10`) |
| Cartesian (x, y) | File a = 0 … j = 9; Rank 1 = 0 … 10 = 9. Origin `(0,0)` = a1 |
| Array index | `index = y × 10 + x` (0–99) |

All coordinates with x or y outside 0–9 are out of bounds and always illegal.

## 2. Square states

Every square is in exactly one of four mutually exclusive states at all times:

| State | Description | Traversable? |
|---|---|---|
| EMPTY | Unoccupied, unrestricted | Yes |
| WHITE_AMAZON | Occupied by a White amazon | No |
| BLACK_AMAZON | Occupied by a Black amazon | No |
| ARROW | Permanently blocked | No |

Only EMPTY squares may be entered or crossed by amazons or arrows. An ARROW square remains blocked for the rest of the game.

## 3. Pieces

Each player controls exactly **4 amazons**. Amazons are never captured, removed, or added; the count stays at 4 per player for the entire game.

Arrows are not pieces in the traditional sense; they are permanent square-state mutations (EMPTY → ARROW). The theoretical maximum number of arrows in a game is 92 (the number of initially empty squares).

## 4. Starting position

White amazons: **a4, d1, g1, j4**
Black amazons: **a7, d10, g10, j7**

All other 92 squares begin EMPTY.

## 5. Turn order

White moves first. Players alternate turns. A player may never pass or skip a turn; if any legal turn exists, the player must execute one.

## 6. Turn structure

Each turn is an **atomic two-phase sequence** performed by the active player. Both phases are mandatory and must occur in this exact order:

**Phase 1 — Move amazon:** Select one friendly amazon and move it to a different EMPTY square along a legal line.

**Phase 2 — Shoot arrow:** The same amazon that just moved shoots an arrow from its new position to a different EMPTY square along a legal line. The arrow's target square immediately and permanently becomes ARROW.

A turn is legal only when both phases are completed legally. A partial turn is illegal.

## 7. Movement geometry (applies to both phases)

A legal line is any straight path along one of 8 directions: horizontal (±x), vertical (±y), or diagonal (±x and ±y changing by equal magnitude). This is identical to queen movement in chess.

The piece/arrow travels **one or more** squares along the chosen direction. The following constraints apply:

- **Path clearance:** Every intervening square between the origin and destination (exclusive of both endpoints) must be EMPTY. If any intervening square is non-EMPTY (amazon of either color, or arrow), the move is blocked and illegal. There is no jumping.
- **Destination:** The target square must be EMPTY. Moving onto or through any amazon or arrow is illegal.
- **No capture:** Amazons never displace other pieces.

## 8. State update sequence within a turn

The order of state mutations is rules-critical:

1. **Phase 1 executes:** The amazon's origin square becomes EMPTY. The amazon's destination square becomes WHITE_AMAZON or BLACK_AMAZON.
2. **Phase 2 executes:** The arrow's target square becomes ARROW.

Because the amazon's origin square is set to EMPTY before Phase 2 begins, the arrow may legally be fired back along the same path the amazon just traveled, including into or across the vacated origin square. This is explicitly legal.

## 9. End condition

At the start of a player's turn, if that player has **zero legal turns** (no amazon can perform both a legal move and a subsequent legal arrow shot), that player **loses immediately**. The opponent wins.

Equivalently: the last player to successfully complete a legal turn wins.

### Checking for legal turns

For each of the active player's 4 amazons, check whether any of the 8 adjacent directions contains at least one EMPTY square. If all 4 amazons have zero reachable EMPTY squares in any direction, the player has no legal turn. (A full check requires verifying that at least one amazon can move to at least one square from which it can then shoot an arrow to at least one square, but checking immediate adjacency for all 4 amazons is a sufficient fast-path for detecting total paralysis.)

## 10. Draws are impossible

Every completed turn permanently converts exactly one EMPTY square into an ARROW square. The number of EMPTY squares strictly decreases by 1 each turn (monotonic reduction). Because no mechanism exists to free squares, no prior board state can ever recur. The game state forms a directed acyclic graph and must terminate within at most 92 turns. No draw-detection logic, repetition tracking, or move-count limits are needed.

## 11. Summary of prohibitions

- No passing, skipping, or partial turns.
- No jumping over occupied or blocked squares.
- No capturing or displacing any piece.
- No moving an arrow after it is placed.
- No shooting the arrow from a different amazon than the one that moved.
- No moving onto an occupied or blocked square.
- No moving to the same square the piece already occupies (displacement ≥ 1 required).
