# 12×12 Bashni — Definitive Ruleset Specification

## 1. Board

The board is a 12×12 grid of alternating dark and light squares (144 total, 72 dark, 72 light). Only the 72 dark squares are playable. Coordinates use algebraic notation: files `a` through `l` (left to right from White's perspective), ranks `1` through `12` (bottom to top from White's perspective). Square `a1` is dark. A square at file index `x` (a=1, b=2, … l=12) and rank `y` is dark (playable) if and only if `(x + y) % 2 == 0`. Each rank contains exactly 6 playable squares.

## 2. Players, Pieces, and Setup

Two players: **White** and **Black**. White moves first. Players alternate turns; passing is illegal.

Each player begins with **30 men** placed on the dark squares of the 5 ranks nearest their own side:

| Player | Starting Ranks | Piece Count |
|--------|---------------|-------------|
| White  | 1, 2, 3, 4, 5 | 30 (6 per rank) |
| Black  | 8, 9, 10, 11, 12 | 30 (6 per rank) |

Ranks 6 and 7 begin empty. Total atomic pieces in the game: **60**. This count is invariant across all game states (pieces are never removed from play).

## 3. Piece Types

Each atomic piece has two properties:

- **Color**: White or Black. Immutable for the lifetime of the game.
- **Rank**: Man or King. A Man may be promoted to King (one-way; Kings never demote).

## 4. Stacks

Every occupied square holds exactly one **stack**: an ordered array of atomic pieces `[p₀, p₁, … pₙ]` where `p₀` is the **top piece** (the "commander").

- **Ownership** of the stack is determined solely by `color(p₀)`.
- **Movement class** of the stack is determined solely by `rank(p₀)`.
- All pieces at indices `1…n` are **prisoners**: completely inert. They retain their individual color and rank in memory but have no influence on gameplay until they become the top piece of some stack.

A stack of length 1 (a single piece with no prisoners) follows all the same rules; every piece on the board is always modeled as a stack.

## 5. Objective and Victory

A player wins when the opponent, at the start of the opponent's turn, has **no legal move**. This includes:

- The opponent has no stacks with a friendly top piece (all their pieces are imprisoned), or
- The opponent has friendly-controlled stacks but every one is completely blocked from moving or capturing.

## 6. Move Obligation and Mandatory Capture

On each turn, a player must make exactly one move with exactly one of their controlled stacks. **Capture is mandatory**: if any controlled stack has at least one legal capture available anywhere on the board, the player must execute a capturing move. A non-capturing (quiet) move is legal only if zero captures exist for the current player on the entire board.

When multiple capture sequences are available, the player may freely choose **any** legal capture sequence. There is **no maximum-capture rule**. However, once a capture sequence is initiated, it must be completed to its full extent (all available continuation jumps on the chosen path must be taken).

## 7. Non-Capturing (Quiet) Movement

Quiet moves are legal only when no capture exists anywhere on the board for the active player.

### 7.1 Man Movement

A Man-commanded stack moves **one square diagonally forward** to an adjacent empty playable square. Forward means: toward rank 12 for White, toward rank 1 for Black.

### 7.2 King Movement (Flying King)

A King-commanded stack moves diagonally in **any of the four diagonal directions** across **any number of contiguous empty squares**. The King selects any one empty square along the chosen ray as its destination. The ray is blocked by the first occupied square encountered; the King cannot pass through or land on occupied squares.

## 8. Capture Rules

### 8.1 Man Capture

A Man-commanded stack captures by jumping diagonally over **one adjacent enemy-controlled stack** to the **empty square immediately beyond it** on the same diagonal. Men may capture in **all four diagonal directions** (forward and backward). The landing square must be empty and within board boundaries.

### 8.2 King Capture (Flying King Capture)

A King-commanded stack captures an enemy stack on the same diagonal if:

1. All squares between the King and the target are empty.
2. At least one empty square exists beyond the target on the same diagonal.

The King jumps over the single enemy stack and may land on **any empty square beyond it** along that same diagonal (before any other occupied square). Two consecutive occupied squares on a diagonal block the jump.

### 8.3 Multi-Jump Continuation

After completing one jump and landing, if the same moving stack has another legal capture from its new position, it **must** continue capturing as part of the same turn. The turn ends only when no further legal capture exists for the moving stack from its current position.

### 8.4 Path Constraints

During a single capture sequence:

- A stack **may** revisit (land on or pass through) the same empty square multiple times.
- A stack **may not** jump over the same board coordinate twice. Once a stack at coordinate `(x, y)` has been jumped, that coordinate is **locked** for the remainder of the turn — even if a new piece has been exposed there by the capture. Track jumped coordinates, not piece identities.

### 8.5 King Landing Constraint

When a King has a choice of landing squares after a jump, if one of those landing squares allows a further capture, the King **must** choose a landing square from which the capture sequence can continue (if any such square exists).

## 9. Capture Resolution — The Tower Mechanic

This is the defining rule of Bashni. Captured pieces are never removed from the game.

### 9.1 What Gets Captured

When stack `A` jumps over enemy stack `B`, only the **top piece** (`b₀`) of stack `B` is captured. The remainder of `B` (now `[b₁, b₂, … bₙ]`) stays on its original square, with `b₁` instantly becoming the new commander of that residual stack (inheriting ownership and movement class from `b₁`'s color and rank).

If `B` had length 1 (a lone piece), the square becomes empty after the capture.

### 9.2 Where the Captured Piece Goes

The captured piece `b₀` is appended to the **bottom** of the attacking stack `A`. If `A = [a₀, a₁, … aₓ]` before the jump, then after the jump `A' = [a₀, a₁, … aₓ, b₀]`.

### 9.3 Multi-Jump Ordering

In a multi-jump sequence capturing `b₀`, then `c₀`, then `d₀`, the pieces are appended to the bottom of the attacker in strict chronological order:

`A' = [a₀, … aₓ, b₀, c₀, d₀]`

Each append happens immediately after each individual jump, before evaluating the next jump in the sequence.

### 9.4 Newly Exposed Pieces

A piece revealed as the new top of a residual stack after a capture does not act during the current turn. It becomes active on future turns according to its own color and rank. However, the coordinate is locked for capture purposes for the remainder of the current sequence (see §8.4).

## 10. Promotion

**Promotion rank**: rank 12 for White, rank 1 for Black.

When the top piece (`p₀`) of a stack is a Man and the stack arrives on the promotion rank:

- **During a quiet move**: `p₀` is immediately promoted to King. The turn ends.
- **During a capture sequence**: `p₀` is immediately promoted to King. If a further capture is available using King movement rules from the promotion square, the sequence **continues with King powers** within the same turn. If no further capture is available, the turn ends.

Only the top piece (`p₀`) is promoted. All prisoners below retain their existing rank regardless of the stack's position.

## 11. Draw Conditions

### 11.1 Fifteen-Move Stagnation

The game is drawn if **15 consecutive full moves** (a full move = one White turn + one Black turn) pass without:

- Any capture occurring, or
- Any unpromoted Man making a quiet move (advancing).

Maintain a stagnation counter. Increment after each individual turn. Reset to 0 whenever a capture occurs or a Man-commanded stack makes a quiet move. If the counter reaches **30 half-moves** (= 15 full moves), the game is drawn.

### 11.2 Threefold Repetition

The game is drawn if the **exact same board state** occurs **3 times** at any points during the game (not necessarily consecutive), with the **same player to move**.

Two board states are identical if and only if:

- The same player has the move.
- Every playable square has the same occupancy (empty or occupied).
- Every stack on every occupied square has the **identical ordered array** of atomic pieces (same colors, same ranks, same sequence from top to bottom).

Implementation: generate a hash of the full board state (including all stack contents and the active player) after every turn. If any hash appears 3 times, the game is drawn.

### 11.3 Mutual Agreement

A draw may be declared by mutual agreement of both players.

## 12. Complete State Invariants

1. Only the 72 dark squares are playable.
2. Each playable square is either empty or holds exactly one stack.
3. Total atomic pieces across all stacks = **60** at all times.
4. Stack ownership and movement class derive solely from the top piece.
5. Captures remove only the top piece of the target stack.
6. Captured pieces are appended to the bottom of the attacker, never removed from play.
7. Capture is mandatory and overrides quiet movement.
8. Among available captures, any legal sequence may be chosen (no maximum-capture rule).
9. A chosen capture sequence must be completed in full.
10. A coordinate may not be jumped twice in one capture sequence.
11. Promotion affects only the current top piece upon reaching the back rank.
12. A King never demotes. Color never changes.

## 13. Coordinate Reference

### Playable Square Formula

Square `(file, rank)` where `file ∈ {a=1, b=2, … l=12}` and `rank ∈ {1…12}` is playable iff `(file + rank) % 2 == 0`.

### White Starting Squares (ranks 1–5)

Rank 1: `a1, c1, e1, g1, i1, k1`
Rank 2: `b2, d2, f2, h2, j2, l2`
Rank 3: `a3, c3, e3, g3, i3, k3`
Rank 4: `b4, d4, f4, h4, j4, l4`
Rank 5: `a5, c5, e5, g5, i5, k5`

### Black Starting Squares (ranks 8–12)

Rank 8: `b8, d8, f8, h8, j8, l8`
Rank 9: `a9, c9, e9, g9, i9, k9`
Rank 10: `b10, d10, f10, h10, j10, l10`
Rank 11: `a11, c11, e11, g11, i11, k11`
Rank 12: `b12, d12, f12, h12, j12, l12`

### Empty Zone (ranks 6–7)

Rank 6: `b6, d6, f6, h6, j6, l6`
Rank 7: `a7, c7, e7, g7, i7, k7`
