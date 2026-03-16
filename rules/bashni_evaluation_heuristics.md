# Bashni: Evaluation Function Implementation Reference

## Constants

- Board: 8×8, 32 playable dark squares
- Each player: 12 pieces (men), total 24 pieces on the board at all times
- Pieces are NEVER removed — captured pieces are placed under the capturing piece to form stacks
- Flying kings: kings move/capture any distance diagonally (Russian draughts rules)
- Men can capture backwards (but cannot make non-capturing backward moves)
- Captures are mandatory — if a capture exists, you must capture
- No maximum-capture rule — player freely chooses among available capture sequences
- Carry: entire stack moves as one unit, commanded by the top piece

## Win Condition

A player wins when the opponent has **zero legal moves**. This occurs via:

1. **Total imprisonment:** All opponent pieces are buried inside the winner's stacks (no free opponent pieces on the board).
2. **Complete blockade:** Opponent's remaining free stacks are geometrically blocked and cannot make any legal move.

Both are equivalent for evaluation — the side with zero legal moves loses.

**Draw conditions:** Threefold repetition, mutual agreement, or 15-move rule (no material composition change for 15 consecutive moves). Draws are extremely rare in Bashni due to the liberation mechanic creating constant imbalance — the evaluation should be more aggressive than in standard draughts.

---

## The Core Insight: Stack Composition, Not Piece Count

In standard draughts, material balance dominates. In Bashni, total piece count is a constant (24) throughout the entire game. What changes is **who controls which stacks and what's buried inside them**. A player controlling 4 stacks that collectively imprison 8 enemy pieces is dominating, even if the opponent has 6 free stacks. A single capture can flip tower ownership and liberate a swarm of enemy pieces, reversing the position entirely. The evaluation must track the full layer-by-layer composition of every stack.

---

## Stack Terminology

For any stack `s` with pieces ordered `[top ... bottom]`:

- **Commander:** The top piece. Determines ownership (color) and movement type (man or king).
- **Cap depth:** Number of consecutive pieces from the top matching the commander's color. The "cap" of controlling pieces.
- **Prisoners:** Opponent-colored pieces buried under the cap. `prisoners(s) = height(s) - capDepth(s)`.
- **First-degree prisoner:** A piece at index 1 (directly under the commander). Has immediate liberation potential — if the commander is captured, this piece becomes the new commander.
- **Hostile payload:** An enemy piece at index 1 inside YOUR stack. If your commander is captured, the enemy gains an active piece.
- **Hard stack:** Cap depth is high relative to height (cap ratio ≥ 0.5). Resilient — multiple captures needed to flip.
- **Soft stack / Weak cap:** Cap depth ≤ 2 with prisoners ≥ 2. Vulnerable — one capture can flip ownership and release a swarm.
- **Insulating pieces:** Friendly pieces buried inside friendly stacks. Provide buffer — if commander is captured, next piece is still friendly, maintaining control.

---

## Feature Set

### Tier 1 — Terminal and Mobility Override (weight: ±100,000)

**Zero legal moves = immediate loss.** Check `legalMoves(player)`. If 0, return terminal loss score.

**Near-zero mobility (≤ 2 moves):** Apply asymptotic penalty as mobility approaches 0. When `legalMoves(P) ≤ 2` and opponent has ≥ 6, position is critically collapsing.

**Mate-in-one detection:** For each legal move, compute opponent's legal moves in the resulting state. If any result has `legalMoves(opponent) = 0`, return near-terminal win score.

**Mandatory capture regime:** When a capture exists, non-capturing moves are illegal. Mobility must be computed in the correct regime — count only capturing moves when captures are available.

---

### Tier 2 — Tactical Threats and Forced Sequences (weight: ±5,000)

**Capture-and-flip threat (negative potential realization):** Detect positions where opponent can capture the top of your weak-cap stack (`capDepth ≤ 2, prisoners ≥ 2`), causing tower ownership to flip. For each such vulnerable stack, check if opponent has any capture sequence that removes the top piece. If the new top piece after capture is opponent-colored, they gain control of the entire tower plus all prisoners. Score: penalty proportional to `prisoners²` (exponential punishment for many prisoners under thin cap).

**Liberation surge:** Detect positions where a capture sequence increases `sumPrisonersHeld` substantially (≥ 3) AND reduces opponent mobility below a threshold (≤ 2). This combination signals imminent win by imprisonment.

**Forced-capture trap (all captures are bad):** When `forcedCaptureExists(P)` is true, evaluate whether ALL legal capture sequences lead to worse positions (opponent refutation within 2 ply makes things worse). If every forced capture is losing, apply severe penalty — player is being "force-fed" into self-destruction.

**Promotion-in-one threat:** Detect legal moves that crown a man-top stack, especially via capture sequences (since a man crowned mid-sequence immediately becomes a flying king and may continue capturing as a king in the same turn). Large bonus.

**Forced feeding detection:** Opponent moves a low-value man into your commander's mandatory capture path, and the landing square after capture places your commander into a larger enemy stack's capture range. Detect by tracing forced-capture landing squares and checking if they fall within enemy capture rays. Extreme penalty.

---

### Tier 3 — Material and Stack Composition (weight: ±500)

**Commander count differential:** `controlledStacks(P) - controlledStacks(O)`. This is the true "material" of Bashni — not raw piece count but number of independently movable units. Three stacks of height 1 vastly outperform one stack of height 3 (3 intersections controlled, 3× the moves).

**Commander type weighting:** Kings are ~3.5× the value of men (flying kings in Russian draughts move/capture any distance diagonally).

| Piece type | Base value |
|---|---|
| Free man (man on top of stack or alone) | 100 |
| Free king (king on top of stack or alone) | 350 |
| Imprisoned enemy man (under your stack) | +50 (latent advantage, neutralized) |
| Imprisoned enemy king (under your stack) | +80 (kings retain rank when freed, so imprisoning them is more valuable) |
| Own imprisoned man (under opponent's stack) | -50 (liability, inactive) |
| Own imprisoned king (under opponent's stack) | -80 |

**Material formula:**

```
material = (free_own_men × 100 + free_own_kings × 350)
         - (free_opp_men × 100 + free_opp_kings × 350)
         + (imprisoned_opp_men × 50 + imprisoned_opp_kings × 80)
         - (imprisoned_own_men × 50 + imprisoned_own_kings × 80)
```

**Cap depth and negative potential:**

Per stack owned by P, compute cap depth (consecutive own-color pieces from top). Aggregate:

- `sumCap(P)` = Σ capDepth(s) over P's stacks. More is better — deeper caps mean more resilient towers.
- `negPotential(P)` = Σ `prisoners(s)²` for each stack where `capDepth(s) ≤ 2`. Lower is better. The squared term sharply punishes many prisoners under thin caps.

**Stack resilience (diminishing returns):**

A stack of all friendly pieces requires H separate captures to neutralize. Bonus for stack resilience:

```
resilience_bonus = Σ (8 / layer) for layer in 2..own_pieces_in_stack
                 ≈ 8 + 4 + 2.7 + 2 + ...
```

Cap at 4 own pieces — beyond that, the cost of occupying only one square outweighs resilience. Stacks of 3-4 own pieces are optimal.

**Cap safety multiplier for imprisonment value:**

```
cap_safety = min(1.0, own_pieces_on_top / (enemy_prisoners × 0.5))
imprisonment_value = enemy_prisoners × 50 × cap_safety
```

Thick cap + many prisoners = strong. Thin cap + many prisoners = liability.

---

### Tier 4 — Mobility and Advancement (weight: ±100–300)

**Mobility differential:** `legalMoves(P) - legalMoves(O)`. Weight: 4 per move. Mobility matters less than in chess but is the direct proxy for the win condition (zero moves = loss). Apply non-linear multiplier: penalty escalates exponentially when moves drop below 3.

**Moveable pieces count:** Number of stacks that have at least one legal move. Weight: 8-10 per moveable piece. Better indicator than raw move count for avoiding blockade.

**King-top mobility advantage:** King-topped stacks have long-range diagonal movement and capture. Count opponent's king-top stacks with high diagonal reach (many reachable empty squares) as a danger signal.

**Promotion distance:** Sum of rows remaining to promotion for all own man-commanders. Lower total is better. Weight: 5 per row. Runaway man (unobstructed path to king row): +150, minus 3 per square remaining.

**Back rank pieces:** Men still on home row. Weight: +15 each in opening/midgame (defensive integrity bonus).

---

### Tier 5 — Positional (weight: ±10–50)

**Back-rank integrity bonus:**

Count own men on starting back row with `capDepth ≥ 1`. Men on the back row cannot be targeted from behind (they can't make non-capturing backward moves, so pieces there are safe). Back row also denies opponent promotion squares. Weight: +40 per back-rank man in opening, decaying to 0 in endgame.

**Center control:**

The four center dark squares (14, 15, 18, 19 in standard numbering) maximize diagonal options and threat reach. But apply conditionally:

- King-top stack in center: +40 (maximum ray projection)
- Single man or low stack in center: +15
- Tall stack (height > 3) in center: **-20** (massive target, immobile, vulnerable to multi-directional attack)

**Edge shelter for vulnerable stacks:**

Edge squares are immune to being jumped from the outside (no landing square beyond the board). Stacks holding enemy prisoners benefit from edge positioning:

- Stack with prisoners ≥ 2 on edge: +25 (protected from capture that would liberate prisoners)
- King on edge: -15 (truncates long-range mobility, halves attack rays)

**Safe-storage bonus for prisoner-heavy towers:**

Stacks with many prisoners should be positioned in own territory (own half of board, ranks 1-4 from own perspective):

- Prisoner-heavy stack in own half: `+8 × prisoners(s)`
- Prisoner-heavy stack in opponent half: `-8 × prisoners(s)` (exposed to capture/flip)

**Promotion runway:** Squares on penultimate and antepenultimate ranks carry escalating value for men. A man on rank 7 is worth significantly more than on rank 4.

---

## Threat Detection Patterns

**Forced feeding maneuver (sacrificial trap):** Opponent deliberately places a low-value man into your mandatory capture path. After your forced capture, the landing square puts your commander in range of a larger enemy stack or flying king. Detection: generate opponent quiet moves, check if each enables a mandatory capture for you, trace the landing square, check if enemy capture rays intersect it. Extreme penalty.

**Liberation threat (tower flip):** Enemy can capture the top of your stack where `capDepth ≤ 2` and `prisoners ≥ 2`. After capture, the piece at index 1 becomes new commander. If it's opponent-colored, they gain the entire tower. Detection: identify vulnerable stacks, check if enemy has any capture sequence hitting them. Penalty = value of all prisoners that would be released.

**Flying king X-ray alignment:** Enemy flying king shares a diagonal with your stack, separated only by empty squares. If the square beyond your stack is empty, immediate capture threat. Detection: ray-cast from all enemy kings along all 4 diagonals. If first entity hit is your stack and square beyond is empty, flag as en prise. Multi-jump alignment (multiple stacks on same diagonal with gaps) scales penalty exponentially.

**Backwards capture vulnerability:** Men in Bashni capture backwards. A piece positioned directly behind an advancing enemy man with an empty landing square is vulnerable. Detection: project backward diagonal capture zones from all enemy men. Penalize pieces in these blind spots.

**Promotion-in-capture threat:** Man-top stack captures through the promotion rank and becomes a flying king mid-sequence, continuing to capture with king powers in the same turn. Detection: trace capture sequences, check if any landing is on promotion rank with a man commander. Large bonus — explosive tactical potential.

**Multi-jump imprisonment surge:** A capture chain that captures 2+ stacks, adding a prisoner at each jump, building a formidable tower. Evaluate full composition change from any multi-jump, not just the number of captures. The net material swing must account for what's released if any captured stack had your prisoners inside.

---

## Danger Signals (detect and penalize)

Ordered by severity:

1. **Zero legal moves** — immediate loss. Terminal.

2. **Near-zero mobility (≤ 2 moves) while opponent has many** — functional loss, blockade imminent. Asymptotic penalty as moves approach 0.

3. **All stacks have thin caps** — mass liberation for opponent is one capture away from each stack. Count stacks where `capDepth ≤ 1` and `prisoners ≥ 2`. If this is most of your army, position is collapsing.

4. **All forced captures are losing** — every available capture (mandatory) leads to opponent refutation. Detection: if `forcedCaptureExists(P)` is true and all captures lose material or position, severe penalty.

5. **Significant king disadvantage** — opponent's flying kings control the board. Without own kings, cannot contest diagonals. Weight: -200 per king deficit.

6. **Mega-stack concentration** — single stack contains > 40% of total own pieces on board. Occupies one square, trivially blockaded. Severe mobility and flexibility penalty.

7. **Back-rank collapse in opening/midgame** — fewer than 2 own pieces on home row. Opponent men advance to promotion unopposed. Penalty: -80.

8. **Hostile payload on critical stacks** — enemy piece at index 1 inside your most important stacks (highest value, most prisoners). If your commander is captured, opponent gains an active piece AND liberates their prisoners. Detection: check index 1 of all own stacks. Penalty scaled by value of the hostile piece (king at index 1 = severe).

9. **Overgrown stacks (tipping point)** — stacks with height > 5 suffer diminishing returns. They're immobile, easy to corner, and a single capture loses the entire concentration. Penalty: `-5 × (height - 4)` per such stack, increasing in endgame.

10. **Irreversible prisoner deficit** — own pieces buried at depth ≥ 2 in opponent stacks vastly outnumber opponent pieces at depth ≥ 2 in own stacks. These deep prisoners are extremely unlikely to be liberated. If differential exceeds 4 pieces, position is strategically bankrupt. Persistent penalty.

---

## Phase Detection and Weight Adjustment

**Detection metric: Total Board Density** = number of active stacks (independently moving units) on the board, regardless of color. Physical piece count is useless (always 24).

| Phase | Active stacks | King presence | Typical moves |
|---|---|---|---|
| Opening | 20-24 | No kings | 1-8 |
| Middlegame | 10-19 | Kings emerging | 8-25 |
| Endgame | 2-9 | Kings dominate | 25+ |

Alternative detection: combine `stackCountTotal`, `topKings(P) + topKings(O)`, and `controlledStacks(P)`.

**Opening weight adjustments:**

- Back-rank integrity: **2× weight** — keep home row intact. Expert advice: "Keep one's own back row intact." Prefer backward captures that create stacks in safe territory.
- Center control: **1.5× weight** — fight for central squares.
- Stack composition: **0.3× weight** — few stacks exist, barely relevant.
- Advancement: **0.5× weight** — don't rush forward. Overextension is the most common opening error.
- Negative potential: **0.5× weight** — few prisoner-heavy stacks exist yet.
- Tipping point penalty: negligible — early stacks are surrounded by protective structure.

**Middlegame weight adjustments:**

- Stack composition: **2× weight** — this is where Bashni diverges most from standard draughts. Assess cap thickness, prisoner count, liberation potential for every stack.
- Imprisonment balance: **1.5× weight** — the side with more imprisoned enemy pieces is usually winning.
- Liberation potential: **1.5× weight** — can you force captures that free your buried pieces?
- King creation: **1.5× weight** — getting a flying king onto a stack is game-changing.
- Mobility: **1.2× weight** — maintaining options prevents forced-into-bad-captures scenarios.
- Back-rank: **1× weight** — still relevant but less critical.

**Endgame weight adjustments:**

- Mobility and blocking: **3× weight** — blocking becomes the primary winning mechanism. The side that runs out of moves loses.
- King count: **2× weight** — flying kings dominate the endgame. The long diagonal (a1-h8, the "highway") becomes critical.
- Commander delta: **2× weight** — fewer stacks means each one matters more.
- Back-rank: **0× weight** — strategically irrelevant; men must advance to promote.
- Center control: **0.3× weight** — king diagonal control matters more than geographic center.
- Tipping point penalty: **3× weight** — a single mega-stack on a near-empty board is trivially blockaded.

---

## Known Pitfalls

**Counting "material" like normal checkers (pieces removed from game).**
Captured pieces stay on the board as prisoners. Total physical piece count is always 24. Material advantage is about composition and vulnerability, not raw count. A stack of 5 friendly pieces is functionally identical to a single man in terms of movement — the 4 buried pieces are dead weight until the commander is captured.

**Ignoring stack internal composition.**
Two stacks can look identical on the surface (same top piece, same square) but have completely different values based on what's buried inside. Always track full layer-by-layer composition. A stack you control with 4 enemy prisoners under a 1-piece cap is a ticking bomb, not an asset.

**Overvaluing raw prisoner count without cap security.**
A big bonus for "holding many prisoners" regardless of cap depth is wrong. A weak tower (capDepth ≤ 2, prisoners ≥ 2) has negative potential — it can be attacked and converted. Expert strategy: "It is often advantageous to feed several of one's own men to a not-too-strong opponent stack and then capture the top layer."

**Assuming maximum-capture rule applies.**
Bashni does NOT require choosing the capture sequence that takes the most pieces. Player freely chooses among available capture sequences. An engine that assumes forced maximum capture will miscalculate threat detection entirely.

**Computing mobility incorrectly under mandatory capture.**
If a capture exists, non-capturing moves are illegal. Mobility must be computed in the correct move regime — count only capturing moves when captures are available, count only quiet moves when no captures exist.

**Ignoring special capture-path properties.**
During a capture sequence, a piece may revisit squares and may jump the same piece more than once. Threat detection that prunes these possibilities will miss real forced lines.

**Treating buried kings as active kings.**
A king at index 2+ inside a tower cannot use its flying movement. It moves as the commander (man or king on top) dictates. Only evaluate buried kings for their latent threat value (high value if freed) — they contribute zero to current mobility or active threats.

**Applying standard draughts positional heuristics unchanged.**
Center control matters less in Bashni because positional advantages are more temporary (liberation can reverse the board). Blocking matters far more in the endgame than in standard draughts. The "never resign" principle is more valid — dramatic reversals via tower flips are a core feature.

**No quiescence search for capture sequences.**
Evaluating a position mid-capture-sequence produces wildly inaccurate scores. Always extend search through all forcing captures before applying static evaluation. This is even more critical in Bashni than standard draughts because a single capture chain can flip tower ownership across the board.

**The "Beshenyie stolby" (Mad towers) pattern.**
Two towers can enter forced-capture loops creating periodic positions. The AI must detect repetition to avoid infinite loops and correctly evaluate such positions as draws.

**Overvaluing maximum capture size.**
Capturing more pieces is not always better. Even striving for maximum material can build a catastrophically vulnerable stack. Evaluate the full composition change, not just the number of captures.

**Letting towers grow arbitrarily tall with no penalty.**
"Bigger stack is always better" is false. Excessive height weakens the position by occupying one square, reducing mobility, and creating an easy blockade target. Optimal stack size is 3-4 own pieces. Beyond that, diminishing returns set in sharply.

---

## Implementation Summary

```
1. TERMINAL: legalMoves(P) = 0? → loss. legalMoves(O) = 0? → win.
2. MATE-IN-ONE: Any move leaves opponent with 0 legal moves? → near-terminal win.
3. TACTICAL: Capture-flip threats, liberation surges, forced-feed traps, promotion threats.
4. MATERIAL: Commander delta (weighted by king ratio) + imprisonment balance (adjusted by cap safety).
5. COMPOSITION: Cap depth, negative potential, stack resilience, hostile payloads.
6. MOBILITY: Legal moves differential (non-linear penalty below 3), moveable pieces count.
7. POSITIONAL: Back-rank integrity, center control (conditional on stack height), edge shelter, promotion distance.
8. PHASE: Interpolate weights based on total board density (stacks remaining).
9. SIGMOID: Map weighted sum to [0.0, 1.0].
```

The evaluation's core tension: imprisoning opponent pieces is the path to victory (reduces their legal moves toward zero), but the stacks holding those prisoners become high-value targets that can flip ownership in a single capture. Correctly balancing imprisonment value against cap vulnerability — and adjusting that balance across game phases — is the central engineering challenge.
