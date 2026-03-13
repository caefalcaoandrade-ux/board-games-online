# Entrapment — Definitive Ruleset for Implementation

## 1. Components

- **Board**: 7×7 grid of squares. Between every pair of orthogonally adjacent squares is a **groove** that can hold exactly one barrier. The board also supports a **6×7 variant** where one row is removed from play using a bar/stick.
- **Players**: 2 (designated Light/White and Dark/Black).
- **Roamers**: 3 per player (6 total). Roamers occupy squares.
- **Barriers**: 25 per player (50 total). Barriers occupy grooves.

## 2. Barrier States

A barrier on the board exists in exactly one of two states:

- **Resting**: lying flat (on its long side) in a groove. A resting barrier is passable by its owner's roamers via jumping (see §6) and can be flipped, relocated, or left in place by its owner.
- **Standing** (also called "upturned" or "on end"): standing upright (on its short side) in a groove. A standing barrier is **permanently immovable and impassable to both players**. It can never be flipped back, relocated, or jumped.

A barrier transitions from resting to standing in exactly two ways: its owner flips it as a barrier action (see §7), or a friendly roamer jumps over it (see §6). Once standing, the transition is irreversible.

## 3. Objective

A player wins by capturing all 3 of the opponent's roamers. The game ends immediately upon the third capture.

## 4. Setup Phase

The board begins completely empty (no roamers, no barriers).

1. **White places 1 roamer** on any empty square.
2. **Black places 1 roamer** on any empty square.
3. **White places 1 roamer** on any empty square.
4. **Black places 1 roamer** on any empty square.
5. **White places 1 roamer** on any empty square.
6. **Black places 1 roamer** on any empty square.

Players alternate, placing exactly one roamer per turn, until all 6 roamers are on the board. No barriers are placed during setup. No roamer may be placed on an occupied square.

## 5. Turn Structure (Post-Setup)

After setup, players alternate turns beginning with White. Each turn consists of **actions** governed by these rules:

- **White's first post-setup turn only**: White takes exactly **1 action**. That action must be a roamer move (not a barrier action). This half-turn rule compensates for first-player advantage.
- **All subsequent turns**: Each turn consists of exactly **2 actions**.
  - **Action 1 (mandatory roamer move)**: The player must move a roamer. If the player has an entrapped-but-uncaptured roamer (a "forced" roamer — see §8), that roamer must be the one moved.
  - **Action 2 (choice)**: The player performs exactly one of the following:
    - A second roamer move (same roamer as Action 1, or a different roamer — subject to forced-move constraints in §8), OR
    - A barrier action (see §7).
- **No passing**: A player may never skip a turn or skip an action within a turn.

Note: A roamer may turn a corner within a single turn only by being moved in Action 1 in one direction and then moved again in Action 2 in a perpendicular direction. A single move action is always in a straight line.

## 6. Roamer Movement

A single roamer move action obeys all of the following:

1. **Direction**: Exactly one orthogonal direction (up, down, left, or right). No diagonal movement. No turning within a single move action.
2. **Distance**: Exactly 1 or exactly 2 squares.
3. **Destination**: The landing square must be empty (no roamer of either color).
4. **Obstructions for a 1-square move**: The groove between the origin square and the destination square must not contain a standing barrier, an enemy resting barrier, or any impassable obstruction. If the groove contains a friendly resting barrier, the roamer jumps it (see below). If an enemy roamer occupies the destination, the move is illegal.
5. **2-square move — plain**: If both intervening grooves are clear (no barriers of any kind) and the intervening square is empty, the roamer slides 2 squares. If the intervening square contains any roamer, the move is illegal as a plain slide; evaluate as a jump instead.
6. **2-square move — jump**: A roamer may jump exactly one adjacent friendly piece (a friendly roamer on the adjacent square, or a friendly resting barrier in the adjacent groove), landing on the square immediately beyond it. Conditions:
   - The jumped object must be **friendly**.
   - The jumped object must be either a **friendly roamer** or a **friendly resting barrier** (not a standing barrier, not an enemy piece of any kind).
   - The landing square (2 squares from origin) must be **empty**.
   - There must be no obstruction between the jumped object and the landing square (i.e., the groove between the intermediate square and the landing square must be clear if jumping a roamer; if jumping a barrier in the first groove, the second groove and intermediate square must also be clear).
   - Only **one** object may be jumped per move action.
7. **Effect of jumping a friendly resting barrier**: Immediately after the jump completes, that barrier is flipped to the **standing** state. It becomes permanently immovable and impassable.
8. **Effect of jumping a friendly roamer**: No state change. The jumped roamer remains in place.

### What blocks movement (impassable obstructions)

- Standing barriers (either player's — ownership is irrelevant once standing).
- Enemy resting barriers.
- Enemy roamers (cannot be jumped; block the path).
- Board edges.

### What can be jumped (passable with consequences)

- Friendly resting barriers (passable; flipped to standing after the jump).
- Friendly roamers (passable; no state change).

## 7. Barrier Actions

A barrier action is the player's Action 2 for the turn (never Action 1). Exactly one of the following:

1. **Place**: Take one barrier from the player's off-board supply and place it **resting** in any empty groove on the board.
2. **Flip**: Choose one of the player's own **resting** barriers already on the board and flip it to the **standing** state in the same groove.
3. **Relocate**: Choose one of the player's own **resting** barriers already on the board, remove it from its groove, and place it **resting** in any other empty groove on the board. (This is only available — and mandatory to use instead of placing from supply — when the player has no barriers remaining in their off-board supply. However, standing barriers may never be relocated.)

Constraints:
- Only the player's own resting barriers may be flipped or relocated.
- Standing barriers may never be moved, removed, or flipped back.
- A barrier may not be placed or relocated into an occupied groove.
- When a player's off-board supply is exhausted, they must relocate a friendly resting barrier from the board if they wish to take a barrier action. Standing barriers are excluded from relocation.

## 8. Entrapment, Forced Position, and Capture

### 8.1 Definitions

- **Surrounded**: A roamer is surrounded when all four orthogonal sides are obstructed (by board edges, barriers of any state/ownership, or other roamers of any color). The roamer has no open side.
- **Entrapped**: A surrounded roamer that has **no legal move action** from its current square. This means every adjacent side is blocked by an impassable obstruction: board edges, standing barriers, enemy resting barriers, enemy roamers, or friendly resting barriers that cannot be legally jumped (because the landing square beyond them is also blocked). An entrapped roamer cannot move at all.
- **Forced** (not entrapped): A surrounded roamer that **does** have at least one legal move — specifically, it can jump an adjacent friendly roamer or an adjacent friendly resting barrier to escape. The roamer is surrounded but not trapped because a friendly jumpable piece provides an exit.

### 8.2 Immediate Capture (Entrapment)

A roamer is captured and removed from the board **immediately** — at the instant the board state renders it entrapped — if:
- It has no legal move from its current square, AND
- It cannot be freed by moving a neighboring friendly roamer out of the way.

Capture is instantaneous. An entrapped roamer is removed before it could participate in any further blocking or capturing logic. A roamer may not move into a square where it would be entrapped (it is captured instantly upon arrival if entrapped there, before it could block or help entrap another piece).

### 8.3 Forced Move Obligation

If a player begins their turn with exactly one forced (surrounded but not entrapped) roamer:

1. **Action 1 must address the forced roamer.** This is done by either:
   - Moving the forced roamer itself (even if into another forced position, or even into an entrapped position where it is immediately eliminated), OR
   - Moving an adjacent friendly roamer away from the forced roamer to open a side (if that adjacent friendly roamer is one of the pieces surrounding it).
2. **If the roamer is still forced after Action 1**, and the player chooses a roamer move for Action 2, the player must again address the same forced roamer (move it or free it). The player may not move an unforced roamer as Action 2 while a force persists.
3. **If the player chooses a barrier action for Action 2 instead**, that is permitted normally regardless of whether the force persists.

A player may voluntarily create a forced position for their own roamer (e.g., as a defensive maneuver), provided they relieve it on the first action of their next turn.

### 8.4 Double Force Rule

A player may never have more than one forced roamer at the same time. If a second roamer becomes forced (surrounded but not entrapped) while the player already has one forced roamer:

- The **second** roamer to enter a forced state is **immediately captured and removed**, as though it were entrapped.
- A player may not voluntarily create a second forced position for their own roamers, as this constitutes immediate self-capture of the second forced piece.

### 8.5 Simultaneous Multiple Entrapments / Forces

If a single action causes **two or more** opponent roamers to become entrapped or forced simultaneously:

- The **moving player** (the one who performed the action) chooses which one to capture.
- Apply that capture immediately, then re-evaluate the board. The remaining roamer(s) may no longer be entrapped/forced after the removal changes the board state.

## 9. Legality Summary (Illegal Actions)

The following are always illegal:

1. Moving a roamer diagonally.
2. Moving a roamer more than 2 squares in one move action.
3. Moving a roamer onto an occupied square.
4. Jumping an enemy roamer or enemy barrier.
5. Jumping a standing barrier.
6. Jumping more than one piece in a single move action.
7. Placing or relocating a barrier into an occupied groove.
8. Moving, relocating, or flipping a standing barrier.
9. Moving, relocating, or flipping an enemy's barrier.
10. Taking a barrier action as Action 1 (Action 1 must always be a roamer move).
11. Passing or skipping an action.
12. Creating a second simultaneous forced position for your own roamers (this results in immediate self-capture of the second forced piece).

## 10. Game End

The game ends immediately when a player has captured all 3 of the opponent's roamers. That player wins. There is no draw condition in the standard rules.

## 11. Variant: 6×7 Board

One row of the 7×7 board is removed from play (cordoned off with a bar or stick), creating a 6×7 playing area. All grooves adjacent to the removed row become board edges for the purposes of movement and entrapment. No roamers or barriers may be placed in or adjacent to the removed row's squares/grooves. All other rules remain identical. This variant produces tighter, more aggressive gameplay.
