# Arimaa: Definitive Ruleset Specification

## 1. Board

An 8×8 grid of 64 squares. Files are labeled **a–h** (left to right). Ranks are labeled **1–8** (bottom to top from Gold's perspective). Each square is identified by its file and rank (e.g., a1 is the bottom-left corner for Gold; h8 is the top-right).

All adjacency in Arimaa is strictly orthogonal (north, south, east, west). Diagonals are never relevant for any rule: not for movement, freezing, support, pushing, pulling, or trap safety.

### 1.1 Trap Squares

Four squares are designated as traps: **c3, f3, c6, f6**. A piece occupying a trap square is immediately removed from the game unless at least one friendly piece is orthogonally adjacent to that trap square. Trap removal is evaluated after every individual step (see Section 7).

### 1.2 Goal Ranks

Gold's goal rank is **rank 8** (the eighth rank). Silver's goal rank is **rank 1** (the first rank). A player wins by having one of their own rabbits on their goal rank at the end of a completed turn.

## 2. Players and Pieces

Two players: **Gold** and **Silver**. Each controls 16 pieces.

### 2.1 Piece Inventory (per player)

| Piece    | Count | Strength | Gold Notation | Silver Notation | Chess Equivalent |
|----------|-------|----------|---------------|-----------------|------------------|
| Elephant | 1     | 6        | E             | e               | King             |
| Camel    | 1     | 5        | M             | m               | Queen            |
| Horse    | 2     | 4        | H             | h               | Rook             |
| Dog      | 2     | 3        | D             | d               | Bishop           |
| Cat      | 2     | 2        | C             | c               | Knight           |
| Rabbit   | 8     | 1        | R             | r               | Pawn             |

### 2.2 Strength Hierarchy

**Elephant > Camel > Horse > Dog > Cat > Rabbit.** This ordering is strict. Pieces of equal strength have no power over each other (cannot freeze, push, or pull one another). A piece can only freeze, push, or pull an enemy piece that is strictly weaker.

## 3. Setup Phase

The game begins with a completely empty board. Setup proceeds in two sequential stages.

**Stage 1 — Gold deploys:** Gold places all 16 Gold pieces on any squares of ranks 1 and 2, one piece per square, in any arrangement.

**Stage 2 — Silver deploys:** After Gold's placement is committed, Silver places all 16 Silver pieces on any squares of ranks 7 and 8, one piece per square, in any arrangement. Silver can see Gold's formation before placing.

After both deployments are committed, the board contains 32 pieces. The game transitions to the main play phase, with Gold taking the first turn.

## 4. Turn Structure

After setup, players alternate turns, starting with Gold. Each turn consists of **1 to 4 steps**. Steps may be distributed among any number of the player's pieces in any combination (e.g., one piece takes all 4 steps; four pieces take 1 step each; one piece takes 3 steps and another takes 1; etc.).

A player may voluntarily end their turn after 1, 2, or 3 steps. Unused steps are forfeited; they do not carry over. A player may **not** pass an entire turn and **must** make at least one step that produces a net change in position.

## 5. Movement Rules

### 5.1 Ordinary Steps

A single step moves one piece from its current square to an orthogonally adjacent empty square. Diagonal movement is never permitted. Each step consumes 1 step from the turn budget.

### 5.2 Directional Restriction on Rabbits

All pieces except rabbits may step in all four cardinal directions (north, south, east, west). Rabbits have a backward restriction:

- **Gold rabbits** may step north, east, or west — never south (toward rank 1).
- **Silver rabbits** may step south, east, or west — never north (toward rank 8).

This restriction applies only to the rabbit's own voluntary movement. A rabbit may be pushed or pulled in any direction, including backward, by a stronger enemy piece.

### 5.3 Push (2 consecutive steps)

A player's piece (the **pusher**) that is strictly stronger than an adjacent enemy piece (the **target**) may push the target.

**Preconditions:**
- The pusher and target are orthogonally adjacent.
- The pusher is strictly stronger than the target.
- The pusher is not frozen.
- There is at least one empty square orthogonally adjacent to the target.
- The player has at least 2 steps remaining in the turn.

**Execution (two consecutive steps, both within the same turn):**
1. The target is moved to a chosen empty square orthogonally adjacent to the target.
2. The pusher moves into the square the target just vacated.

These two steps must be consecutive and cannot be interrupted by any other step.

### 5.4 Pull (2 consecutive steps)

A player's piece (the **puller**) that is strictly stronger than an adjacent enemy piece (the **target**) may pull the target.

**Preconditions:**
- The puller and target are orthogonally adjacent.
- The puller is strictly stronger than the target.
- The puller is not frozen.
- There is at least one empty square orthogonally adjacent to the puller.
- The player has at least 2 steps remaining in the turn.

**Execution (two consecutive steps, both within the same turn):**
1. The puller moves to a chosen empty square orthogonally adjacent to the puller.
2. The target moves into the square the puller just vacated.

These two steps must be consecutive and cannot be interrupted by any other step.

### 5.5 Push/Pull Constraints

- A push or pull always consumes exactly 2 steps.
- Both steps must occur within the same turn (cannot begin on one turn and finish on the next).
- A single two-step action cannot simultaneously be both a push and a pull. A piece completing a push cannot also pull a different piece along with it in that same two-step action.
- Any combination of separate pushes, pulls, and ordinary steps may occur in a single turn, provided the total does not exceed 4 steps and each push/pull is completed as a contiguous pair.
- Only enemy pieces that are strictly weaker can be pushed or pulled. Friendly pieces cannot be pushed or pulled.
- Frozen pieces can be pushed or pulled by the opponent. A piece adjacent to a friendly piece is not protected from being pushed or pulled — friendly adjacency prevents freezing, not displacement.
- An elephant can never be pushed or pulled because no piece is stronger.

## 6. Freezing

A piece is **frozen** if and only if both conditions are true:
1. It is orthogonally adjacent to at least one strictly stronger enemy piece.
2. It is **not** orthogonally adjacent to any friendly piece.

**Properties of freezing:**
- A frozen piece cannot be moved by its owner (no voluntary steps).
- A frozen piece can still be pushed or pulled by the opponent.
- A frozen piece still exerts its own freezing effect on weaker adjacent enemy pieces that lack friendly support.
- Frozen status is recalculated dynamically after every step. It is not a persistent state — it depends entirely on the current adjacency situation.
- Pieces of equal strength do not freeze each other.
- Any friendly piece (regardless of its own strength) adjacent to the threatened piece negates the freeze.
- An elephant is never frozen because no piece is stronger.

## 7. Trap Capture

A piece on a trap square (c3, f3, c6, f6) is immediately removed from the game if it has no friendly piece orthogonally adjacent to that trap square. This evaluation occurs:

- After every individual step (including each sub-step of a push or pull).
- For all four trap squares globally (not just the square a piece moved to or from).

**Key trap behaviors:**

- A piece may voluntarily step onto a trap square. If it has no friendly support there, it is captured.
- If a piece on a trap has friendly support, and that supporting piece moves away (or is pushed/pulled away), the piece on the trap is immediately captured when the supporter's step resolves.
- Trap capture applies to all pieces equally, including elephants.
- During a pull: if the pulling piece steps onto a trap and is captured (no friendly support), the pull still completes — the target piece is still moved into the puller's vacated square. The puller's capture does not cancel the second sub-step of the pull.
- Enemy adjacency does not provide trap safety. Only friendly adjacency counts.

## 8. Turn Legality Constraints

### 8.1 Net Change Rule

A completed turn must produce a board position different from the position at the start of that turn. A sequence of steps that returns all pieces to their starting squares is illegal (equivalent to passing).

Only the final position after all steps is compared to the starting position. Intermediate states during the turn do not matter for this rule.

### 8.2 Threefold Repetition Rule

A turn may not result in a board position (combined with the same side to move) that has already occurred twice before in the game. If committing a turn would create a third occurrence of the same position-plus-side-to-move, that turn is illegal.

- Only completed end-of-turn positions are tracked for repetition. Mid-turn intermediate states are not recorded.
- If a player's only available moves all produce third-time repetitions, that player loses (has no legal move).

## 9. End-of-Turn Resolution and Victory Conditions

After a player (Player A) completes a turn, the following conditions are checked in this exact order. Player B is the opponent who would move next.

1. **Goal — Player A:** If any rabbit belonging to Player A is on Player A's goal rank, Player A wins.
2. **Goal — Player B:** If any rabbit belonging to Player B is on Player B's goal rank, Player B wins.
3. **Elimination — Player B's rabbits:** If Player B has zero rabbits remaining on the board, Player A wins.
4. **Elimination — Player A's rabbits:** If Player A has zero rabbits remaining on the board, Player B wins.
5. **Immobilization:** If Player B has no legal move (all pieces frozen or blocked, with no valid step available), Player A wins.
6. **Forced repetition:** If every possible move Player B can make would create an illegal third-time repetition, Player A wins.
7. Otherwise, play continues with Player B's turn.

**Consequences of this priority order:**
- If both players have a rabbit on their goal rank at end of turn, the moving player (A) wins (check 1 before check 2).
- If both players lose all rabbits on the same turn, the moving player (A) wins (check 3 before check 4).
- Goal and elimination are checked before immobilization. A player who achieves goal or eliminates all enemy rabbits wins even if their own pieces are technically immobilized.
- If an enemy rabbit is pushed or pulled onto its goal rank during a turn but is moved off that rank before the turn ends, no goal is scored for that rabbit — the check only applies to the position at the end of the completed turn.

## 10. Arimaa Is Drawless

No draws exist under the official rules. The threefold repetition rule prevents infinite loops by converting forced repetition into a loss. The priority ordering of win conditions resolves all simultaneous-event edge cases into a decisive outcome.

## 11. Notation

### 11.1 Piece Characters

Gold: E (Elephant), M (Camel), H (Horse), D (Dog), C (Cat), R (Rabbit) — uppercase.
Silver: e, m, h, d, c, r — lowercase.

### 11.2 Step Notation

Each step is notated as: **[piece][origin square][direction]**

Directions: **n** (north, toward rank 8), **s** (south, toward rank 1), **e** (east, toward file h), **w** (west, toward file a). Directions are always from Gold's perspective.

Capture is denoted by **x** in place of a direction: e.g., rc3x means a silver rabbit on c3 is captured (removed).

### 11.3 Turn Notation

A turn is prefixed by its number and player: e.g., **2g** = Gold's first regular turn, **2s** = Silver's first regular turn. (1g and 1s are the setup placements.)

Steps within a turn are separated by spaces. Consecutive steps by the same piece may be condensed by giving the origin square only once (e.g., Rh6nn = rabbit on h6 steps north twice).

### 11.4 Capture Logging in Notation

When a piece is captured as the result of a step, the capture event (piece + trap square + x) is logged immediately after the step that caused it, before the next step is logged. In a push where the target lands on an unprotected trap: the target's displacement step is logged, then the capture, then the pusher's occupation step.

Example: Gold Horse on b2 pushes Silver rabbit from b3 east into c3 trap — notation: **rb3e rc3x Hb2n**.

### 11.5 Setup Notation

During setup, each placement is: **[piece][destination square]** (e.g., Da2 = place Gold Dog on a2).
