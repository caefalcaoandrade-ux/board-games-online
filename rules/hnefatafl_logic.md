# Copenhagen Hnefatafl 11×11 — Definitive Ruleset for Implementation

## 1. Board

The board is an 11×11 square grid. Files are labeled A–K (left to right, mapped to x = 1–11). Ranks are labeled 1–11 (bottom to top, mapped to y = 1–11). Total nodes: 121.

### 1.1 Restricted Squares

There are exactly 5 restricted squares:

- **Throne:** F6 (6,6) — the board center.
- **Corners:** A1 (1,1), A11 (1,11), K1 (11,1), K11 (11,11).

Occupancy rule: only the King may stop on a restricted square. All other pieces are forbidden from ending their move on any restricted square.

### 1.2 Hostility

Restricted squares are **hostile**, meaning they substitute for an enemy piece when evaluating captures (see §5). Specific hostility behavior:

- **Corners:** hostile to both attackers and defenders, always.
- **Throne:** always hostile to attackers. Hostile to defenders **only when the throne is empty** (i.e., the King is not on it).
- **Board edge:** the edge is **NOT hostile**. It never substitutes for an enemy piece in capture evaluation.

### 1.3 Throne Transit

Any piece (attacker or defender) may **pass through** the throne during a move, provided the throne is currently empty. No piece other than the King may end its move on the throne. No piece may pass through the throne if the King occupies it. Corner squares cannot appear as intermediate path nodes because they sit at board extremities.

## 2. Pieces and Setup

### 2.1 Factions

- **Attackers (dark/black):** 24 pieces.
- **Defenders (light/white):** 12 pieces + 1 King = 13 total on the defending side.
- The King belongs to the defending faction for all alliance evaluations.

### 2.2 King Properties

- The King is **armed**: he participates in captures as both hammer (moving piece) and anvil (stationary bracketing piece).
- The King is **strong**: he requires special capture conditions (see §6), not standard custodial capture.
- The King has **edge immunity**: he cannot be captured while on any perimeter square (see §6.3).
- The King is the only piece permitted to occupy restricted squares.

### 2.3 Initial Position

**Attackers (24):**

| Group | Coordinates |
|-------|-------------|
| North | D11, E11, F11, G11, H11, F10 |
| South | D1, E1, F1, G1, H1, F2 |
| West | A4, A5, A6, A7, A8, B6 |
| East | K4, K5, K6, K7, K8, J6 |

**Defenders (12):** D6, E5, E6, E7, F4, F5, F7, F8, G5, G6, G7, H6

**King (1):** F6 (on the throne)

All remaining 84 nodes begin empty.

```
11  C . . A A A A A . . C
10  . . . . . A . . . . .
 9  . . . . . . . . . . .
 8  A . . . . D . . . . A
 7  A . . . D D D . . . A
 6  A A . D D K D D . A A
 5  A . . . D D D . . . A
 4  A . . . . D . . . . A
 3  . . . . . . . . . . .
 2  . . . . . A . . . . .
 1  C . . A A A A A . . C
    A B C D E F G H I J K
```

## 3. Turn Order

Attackers move first. Players then alternate, one move per turn. Passing is not permitted.

## 4. Movement

All pieces (attackers, defenders, and King) move identically:

- A piece moves any number of squares along a single row or column (orthogonal sliding, like a chess rook).
- **Diagonal movement is never permitted.**
- The piece may not jump over or land on any occupied square.
- Path validation: every intermediate square between origin and destination must be empty.
- Destination validation: the destination square must be empty.
- Restricted square constraint: if the destination is a restricted square, the moving piece must be the King.
- Throne transit exception: a non-King piece may pass through F6 during its move if F6 is empty, but may not stop there.

## 5. Capture — Standard Custodial

Applies to **all pieces except the King** as the target. The King may never be captured by this method; use §6 instead.

### 5.1 Mechanism

Immediately after the active player completes a move, evaluate all four orthogonal directions from the destination square. For each direction:

1. Identify the **adjacent square** (distance 1) in that direction. If it contains an enemy piece (the **target**), proceed.
2. Identify the **next square** (distance 2) in the same direction (the **anvil**). The target is captured if the anvil is:
   - Occupied by a piece allied to the moving player, **OR**
   - A restricted square that is currently hostile to the target's faction (see §1.2 for hostility rules).

### 5.2 Constraints

- Only **orthogonal** bracketing counts. Diagonal adjacency never triggers capture.
- Capture is **active only**: the trap must be closed by the aggressor's move. A piece may safely move into a square between two enemy pieces without being captured.
- The King counts as a valid allied piece for the defending faction when serving as the anvil in a custodial capture of an attacker.
- A single move can trigger captures in multiple directions simultaneously. All captures from one move are resolved concurrently — a piece captured on one axis is not used as an anvil on another axis during the same evaluation.

## 6. Capture — King (Regicide)

The King is never captured by standard custodial rules. Instead, the following location-dependent conditions apply. King capture results in an immediate attacker victory.

### 6.1 On a Standard Interior Square

If the King is on any square that is not on the board edge and not orthogonally adjacent to the throne, he is captured when **all four orthogonally adjacent squares** are occupied by attackers.

### 6.2 Adjacent to the Throne

If the King is on one of the four squares orthogonally adjacent to the throne (E6, G6, F5, F7), he is captured when attackers occupy the **three remaining orthogonally adjacent squares**. The throne itself supplies the fourth side.

### 6.3 On the Throne

If the King is on the throne (F6), he is captured when **all four orthogonally adjacent squares** (E6, G6, F5, F7) are occupied by attackers. The throne provides no assistance to the attackers when the King occupies it.

### 6.4 On the Board Edge

The King **cannot be captured** while on any perimeter square (x=1, x=11, y=1, or y=11). Standard regicide checks are bypassed entirely for a King on the edge. The only way to neutralize an edge-positioned King is via encirclement (§8.2).

## 7. Capture — Shieldwall

A group capture mechanism for contiguous rows of pieces along the board edge.

### 7.1 Conditions (all must be true simultaneously)

1. **Edge row:** A contiguous line of 2 or more pieces of the same faction lies along one edge of the board (all on the same rank or file where that rank/file is 1, 11, A, or K).
2. **Flanking bracket:** the edge squares immediately beyond both ends of the row are each occupied by an enemy piece **OR** one end is a corner square (which may substitute for one bracketing piece).
3. **Frontal blockade:** every piece in the row has an enemy piece on the inward-adjacent square (the square one step toward the board center along the perpendicular axis).
4. **Active trigger:** the shieldwall capture is triggered only if the move just completed placed the final piece that fulfills one of the above conditions (a flanking bracket piece or a frontal blockade piece).

### 7.2 Resolution

All pieces in the qualifying edge row that belong to the targeted faction are removed simultaneously.

### 7.3 King Interaction

- The King may participate as a **bracketing piece** or as part of the **frontal blockade** when executing a shieldwall capture against enemy pieces.
- If a valid shieldwall targets a row containing the **King and one or more defenders**, the defenders in the row are captured, but the **King is not captured** (edge immunity applies).

## 8. Victory Conditions

### 8.1 Defender Victory — Corner Escape

The defenders win immediately if the King occupies any corner square: A1, A11, K1, or K11.

### 8.2 Defender Victory — Exit Fort

The defenders win immediately if all three conditions are met:

1. The King is on a board-edge square.
2. The King has at least one legal move available (he is not immobilized).
3. The defensive structure around the King is **unbreakable**: it is impossible for the attackers, through any sequence of legal moves, to capture any piece in the fort or penetrate it. The fort is a closed formation of defenders anchored to the board edge that the attackers cannot breach via custodial capture, shieldwall capture, or any other legal mechanism.

### 8.3 Attacker Victory — King Capture

The attackers win immediately upon capturing the King per the rules in §6.

### 8.4 Attacker Victory — Total Encirclement

The attackers win immediately if the King and **all remaining defenders** are completely enclosed by an unbroken barrier of attackers, with no path to the board edge.

Implementation: perform a flood-fill (BFS) from all empty perimeter squares, traversing through empty squares only (attacker-occupied squares block traversal). After the fill, if the King and every remaining defender occupy squares that were **not reached** by the flood-fill, the encirclement condition is met and the attackers win.

## 9. Immediate Loss — No Legal Move

If a player has zero legal moves at the start of their turn, that player loses immediately.

## 10. Repetition Rule

Perpetual repetitions are forbidden. If the same board position occurs for the third time, the **defenders (white) lose** regardless of which side caused the repetition.

Implementation: maintain a hash table (e.g., Zobrist hashing) recording each board state (piece positions + side to move). When any state count reaches 3, the defenders lose immediately.

## 11. Draw

If neither side can force a win — for example, the attackers have too few pieces to capture the King or encircle all defenders, and the defenders cannot reach a corner or form an exit fort — the game is a draw.

## 12. Turn Execution Sequence

For each turn, execute these phases strictly in order:

**Phase 1 — Input and Validation:**
Receive the proposed move (origin, destination). Validate: the piece at origin belongs to the active player; the vector is orthogonal; all intermediate squares are empty; the destination is empty; if the destination is restricted, the piece is the King; throne transit rules are respected.

**Phase 2 — Move Execution:**
Update the board: remove the piece from origin, place it at destination.

**Phase 3 — Capture Resolution:**
Initialize a removal set. Evaluate standard custodial captures from the destination in all four cardinal directions; add qualifying targets to the removal set. Evaluate shieldwall captures along the edge containing the destination (if applicable); add qualifying targets to the removal set, excluding the King. Remove all pieces in the removal set simultaneously.

**Phase 4 — Terminal State Evaluation (in this order):**
1. Is the King on a corner square? → Defenders win.
2. Does the King satisfy regicide conditions (§6)? → Attackers win.
3. Does flood-fill prove total encirclement (§8.4)? → Attackers win.
4. Does the King satisfy exit fort conditions (§8.2)? → Defenders win.

**Phase 5 — State Logging and Turn Transition:**
Hash the current board state and record it. If any state has occurred 3 times → defenders lose. Switch the active player. Calculate all legal moves for the new active player. If zero legal moves → that player loses.
