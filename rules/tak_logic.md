# Definitive 6×6 Tak Ruleset

## 1. Game Definition

Tak is a deterministic, zero-sum, perfect-information, two-player abstract strategy game. There are no chance elements. The game is played on a 6×6 grid. Players alternate turns; passing is never permitted.

## 2. Board Geometry

The board is a 6×6 grid of 36 squares. Squares connect orthogonally only (shared edges). Diagonal adjacency does not exist for any purpose: no diagonal movement, no diagonal road connections.

**Coordinate system (algebraic):**
- Files: `a` through `f` (left to right, west to east).
- Ranks: `1` through `6` (bottom to top, south to north).
- Origin `a1` is the bottom-left corner from Player 1's perspective; `f6` is the top-right corner.

**Edges:**
- West edge: all squares in file `a`.
- East edge: all squares in file `f`.
- South edge: all squares in rank `1`.
- North edge: all squares in rank `6`.

**Orthogonal adjacency test:** Two squares are adjacent if and only if the Manhattan distance between them equals exactly 1.

**Direction identifiers:**
- `+` = north (rank increases).
- `-` = south (rank decreases).
- `>` = east (file increases).
- `<` = west (file decreases).

## 3. Pieces and Reserves

Each player begins with an off-board reserve containing exactly **30 stones** and **1 capstone**.

Stones are a single pool; each stone placed (whether flat or standing) decrements the stone count by 1. The capstone is a separate, unique piece; once placed, the player has zero capstones remaining.

A stone can be placed in one of two orientations: **flat** or **standing**. This orientation is declared at the moment of placement and cannot be changed afterward except by the capstone-flatten mechanic. The capstone is a distinct piece type, not a stone orientation.

### 3.1 Piece Properties Summary

| Property | Flat Stone | Standing Stone (Wall) | Capstone |
|---|---|---|---|
| Counts toward road | Yes | **No** | Yes |
| Counts toward flat score | Yes | No | No |
| Can be covered (stacked upon) | Yes | **No** | **No** |
| Can flatten a standing stone | No | No | **Yes** (under constraints) |

### 3.2 Stack Invariant

Because standing stones and capstones cannot be covered, they can only ever appear as the topmost piece in a stack. Every valid stack has the form: zero or more flat stones (bottom to top), optionally topped by exactly one standing stone or capstone. No piece of any kind may exist above a standing stone or capstone within a stack.

## 4. Turn Sequence and Opening Protocol

### 4.1 Opening Protocol (Mandatory)

The game begins with an empty board. The first two turns follow a special rule:

- **Turn 1 (Player 1):** Must place one of **Player 2's stones** as a **flat stone** on any empty square. This decrements Player 2's stone reserve by 1.
- **Turn 2 (Player 2):** Must place one of **Player 1's stones** as a **flat stone** on any empty square. This decrements Player 1's stone reserve by 1.

During the opening protocol: standing stones and capstones are illegal; the placed piece belongs to the opponent; it must be flat.

### 4.2 Normal Turns (Turn 3 Onward)

Starting from Turn 3, Player 1 takes the first normal turn. From this point forward, players place and move **their own** pieces. On each turn, the active player must execute exactly one action: **Place** or **Move**.

## 5. Action: Place

Place exactly one piece from the active player's own reserve onto any **empty** square. The player chooses one of:
- A flat stone (costs 1 stone from reserve).
- A standing stone (costs 1 stone from reserve).
- The capstone (costs the 1 capstone from reserve; only legal if not yet placed).

**Placement constraints:**
- The target square must be empty. A piece is never placed directly onto another piece or stack; stacks form exclusively through movement.
- The player must have the chosen piece type available in reserve.
- If this placement fills the last empty square on the board or exhausts the player's reserve, the game ends immediately after this action (see Section 8).

## 6. Action: Move

Move a stack (including a single piece) that the active player controls.

### 6.1 Control

A stack is controlled by the player whose piece is on top. Only controlled stacks may be selected as the source of a move.

### 6.2 Pickup (Lift)

The player chooses a number of pieces `k` to lift from the top of the source stack, where `1 ≤ k ≤ min(stack_height, 6)`. The constant `6` is the **carry limit**, equal to the board width. Any pieces not lifted remain on the source square (which may become empty if all pieces are lifted). The internal order of lifted pieces is preserved exactly as they were stacked.

### 6.3 Direction

The player chooses exactly one orthogonal direction: north, south, east, or west. The entire move proceeds in this single direction. No diagonal movement. No direction change mid-move.

### 6.4 Drop Sequence

The carried pieces move square-by-square along the chosen direction. On **each** square entered, the player must drop **at least one piece** from the **bottom** of the carried bundle. The player chooses a sequence of positive integers (drop counts) that sum to `k`, where each integer represents pieces dropped on successive squares along the path.

Consequently: carrying `k` pieces permits traversing between 1 and `k` squares (inclusive). Skipping a square is never permitted.

### 6.5 Destination Validity

Each square entered along the movement path must satisfy one of:
- The square is empty, **or**
- The square's topmost piece is a flat stone.

If the square's topmost piece is a standing stone or capstone, the square is blocked and cannot be entered — **except** for the capstone-flatten interaction (Section 7).

When pieces are dropped onto a square, they are placed on top of any existing stack, preserving order. This is how control of squares changes — by covering, not by removal.

## 7. Capstone Flatten (Crush/Smash)

A capstone may move onto a square topped by a standing stone, converting that standing stone to a flat stone, if and only if **all** of the following conditions are met:

1. The piece being dropped is a capstone.
2. The capstone is the **sole piece** dropped on that square in the **final step** of the move.
3. The destination square's topmost piece is a standing stone (of either player).

When flattening occurs:
- The standing stone's orientation changes to flat (same owner, same position in stack).
- The capstone is placed on top, becoming the new top piece.
- All pieces beneath the formerly standing stone remain unchanged.

**Additional flatten constraints:**
- A capstone may be carried as part of a multi-piece bundle during earlier steps of the move, as long as the final drop onto the standing stone consists of only the capstone.
- A capstone **cannot** flatten another capstone. A capstone on a square is an absolute block.
- Flattening your own standing stone is legal.
- No other mechanism exists to change a standing stone to flat or a flat stone to standing during play.

## 8. Win Conditions and Game End

After every completed action (Place or Move), evaluate the following in strict order:

### 8.1 Road Win (Primary)

A **road** is a connected chain of orthogonally adjacent squares spanning two opposite edges of the board, where every square in the chain has a top piece that is the claiming player's **flat stone** or **capstone**. Standing stones do not contribute to roads.

A valid road connects either:
- West edge (file `a`) to East edge (file `f`), **or**
- South edge (rank `1`) to North edge (rank `6`).

A road may zigzag; it does not need to be straight. A single square may contribute to multiple roads. Corner squares belong to two edges simultaneously.

**Evaluation order:**
1. Check if the active player has a completed road.
2. Check if the inactive player has a completed road.
3. If both players have a road (**Double Road**): the **active player wins**.
4. If exactly one player has a road: that player wins.
5. If no road exists: proceed to 8.2.

### 8.2 Game-End Trigger (Secondary)

If no road win occurs, check whether the game has reached a terminal state:
- The board is **completely full** (all 36 squares occupied), **or**
- **Either** player's reserve is fully exhausted (zero stones remaining and capstone already placed, or equivalently, the player has no pieces left to place).

If neither trigger is met, the game continues with the other player to move.

### 8.3 Flat Win / Draw

When a game-end trigger fires without a road win, determine the winner by **flat count**:
- For each of the 36 squares, examine only the **topmost** piece.
- If the topmost piece is a **flat stone**, increment its owner's flat count by 1.
- Standing stones on top: contribute 0.
- Capstones on top: contribute 0.
- Buried pieces of any kind: contribute 0.

The player with the higher flat count wins. If flat counts are equal, the game is a **draw**.

### 8.4 Adjudication Priority Summary

Road win supersedes flat win. If a move simultaneously completes a road AND triggers a board-full/reserve-empty condition, the road win takes precedence.

## 9. Portable Tak Notation (PTN)

### 9.1 Square Identifiers

`a1` through `f6`, file letter followed by rank number.

### 9.2 Placement Notation

- `[square]` — place a flat stone (e.g., `c3`).
- `S[square]` — place a standing stone (e.g., `Sc3`).
- `C[square]` — place a capstone (e.g., `Cc3`).

### 9.3 Movement Notation

Format: `[count][source][direction][drops]`

- **count** (optional): number of pieces lifted. Omitted when 1.
- **source**: origin square (e.g., `b4`).
- **direction**: one of `+` `-` `>` `<`.
- **drops** (optional): sequence of digits, each indicating pieces dropped per square. Omitted when the entire carried stack drops on the immediately adjacent square (distance = 1).

The sum of drop digits must equal the count. If drops are omitted and count is omitted, 1 piece moves 1 square.

**Examples:**
- `a1>` — move 1 piece from `a1` one square east (to `b1`).
- `3b2+111` — lift 3 from `b2`, move north, drop 1 on `b3`, 1 on `b4`, 1 on `b5`.
- `5b4>212` — lift 5 from `b4`, move east, drop 2 on `c4`, 1 on `d4`, 2 on `e4`.

A `*` suffix indicates a capstone flatten occurred on the final square (e.g., `3c3>21*`).

### 9.4 Result Tags

- `R-0` / `0-R` — road win for Player 1 / Player 2.
- `F-0` / `0-F` — flat win for Player 1 / Player 2.
- `1/2-1/2` — draw.

## 10. TPS (Tak Positional System) for State Serialization

Format: `[board] [active_player] [move_number]`

- **board**: ranks serialized top-to-bottom (rank 6 first, rank 1 last), separated by `/`. Within each rank, squares are left-to-right (file `a` to `f`), separated by `,`. Empty squares are `x`; consecutive empties compress as `xN` (e.g., `x6` = entire empty rank). Occupied squares serialize stacks bottom-to-top using `1` (Player 1) and `2` (Player 2). The topmost piece is assumed flat unless suffixed with `S` (standing) or `C` (capstone). Example: `12S` = Player 1 flat on bottom, Player 2 standing on top.
- **active_player**: `1` or `2`.
- **move_number**: starts at 1, increments after both players have moved (a full round).

Empty board: `x6/x6/x6/x6/x6/x6 1 1`.

## 11. Complete Illegality Catalogue

The following actions must be rejected without modifying game state:

**Placement violations:**
- Placing on a non-empty square.
- Placing a piece type not available in reserve (no stones left, or capstone already placed).
- During the opening protocol: placing a standing stone, capstone, or one's own piece.
- Placing after the game has ended.

**Movement violations:**
- Moving a stack not controlled by the active player.
- Lifting more than 6 pieces (carry limit) or more pieces than exist in the stack.
- Moving diagonally or changing direction mid-move.
- A drop sequence that does not place at least one piece on every traversed square.
- A drop sequence whose sum does not equal the number of lifted pieces.
- Dropping onto a square topped by a standing stone (unless it is a legal capstone flatten on the final step).
- Dropping onto a square topped by a capstone (absolute block, no exception).
- Attempting a flatten where the dropping piece is not a capstone, or the capstone is not alone on the final drop, or the target top piece is a capstone rather than a standing stone.
- Moving off the edge of the board.
- Moving zero squares (the carried pieces must enter at least one new square).
