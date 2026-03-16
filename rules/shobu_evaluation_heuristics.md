# Shobu: Evaluation Function Implementation Reference

## Constants

- 4 boards: 2 home (your side), 2 away (opponent's side). Each board is 4×4.
- Each player: 4 stones per board × 4 boards = 16 stones total at start.
- Board colors: 2 dark boards, 2 light boards. Each player has one dark home board and one light home board.
- Move structure: every turn = one passive move (home board, no pushing) + one aggressive move (opposite-color board, can push one opponent stone). Direction and distance must match exactly.
- Passive moves: 1 or 2 squares, 8 directions (orthogonal + diagonal), cannot push any stone, must be on a home board.
- Aggressive moves: same direction and distance as passive, on a board of the opposite color, can push at most one opponent stone, cannot push own stones.
- A player who cannot make a complete legal turn (passive + matching aggressive) loses immediately.

## Win Conditions

**Board clearance (primary):** Win instantly by pushing all 4 opponent stones off any single board. Only one board needs to be cleared. The game ends the moment any board reaches 0 opponent stones.

**No legal turn (secondary):** If the player to move cannot make both a legal passive move AND a matching legal aggressive move, they lose immediately. This makes mobility existential — zero legal turns = terminal loss.

**Draw:** Extremely rare. Possible in "inside-outside" column configurations where neither player can push any stone off any board. Detect via `capMovesForYou == 0 AND capMovesForOpp == 0`.

---

## The Core Insight: Per-Board Analysis with Non-Linear Danger Scaling

Shobu's win condition is board-specific, not aggregate. A player leading 4-3 on three boards but trailing 0-4 on one board has lost. Total stones across boards is meaningless — only per-board minimums matter. The evaluation must decompose analysis per-board first, then aggregate with non-linear weighting that emphasizes the weakest front.

The second defining insight: every aggressive action requires a passive enabler on a different board. Home board stones have dual value — their material presence on that board PLUS their role as passive-move generators enabling attacks on opposite-color boards. ~73% of winning moves in 104K simulated games occurred on the winner's home boards.

---

## Feature Set

### Tier 1 — Terminal and Threat Override (weight: ±100,000)

**Board cleared:** If `opponent_stones[any_board] == 0`, return terminal win. If `own_stones[any_board] == 0`, return terminal loss.

**No legal turn:** If side-to-move has zero complete legal turns (passive + matching aggressive), return terminal loss for side-to-move.

**Win-in-1 detection:** Enumerate all legal complete turns. For each, check if any resulting board has `opponent_stones[board] == 0`. If any such turn exists for you: massive bonus. If any exists for opponent (compute by switching side-to-move): massive penalty. Win-in-1 for opponent that you cannot block = near-terminal loss.

**Forced-move survival:** If `legalTurns(you) ≤ 2`, apply steep penalty. Even states with very few legal turns should be penalized sharply because one more restriction could make them terminal.

---

### Tier 2 — Race-to-Zero Board Progress (weight: ±5,000)

**Minimum opponent stones (the attack metric):**

`minOpp = min(opponent_stones[b] for b in all_4_boards)`

This is THE most important non-terminal feature. Apply non-linear (convex) scoring — the danger curve is exponential as counts approach zero:

| Opponent stones on weakest board | Score |
|---|---|
| 4 | 0 |
| 3 | 1 |
| 2 | 4 |
| 1 | 16 |
| 0 | ∞ (terminal win) |

Formula: `attack_score = Σ_b (4 - opponent_stones[b])²` with exponential emphasis on the weakest board.

**Minimum own stones (the defense metric):**

`minMy = min(own_stones[b] for b in all_4_boards)`

Mirror the above as penalty. A board with 1 own stone is one push from losing.

Formula: `defense_penalty = -Σ_b (4 - own_stones[b])²`

**Race margin:** `minOpp - minMy`. Negative = you're closer to clearing a board than opponent is to clearing yours = favorable.

**Second-weakest board tracking:** `secondMinOpp` and `secondMinMy`. Matters for multi-board fork threats — having TWO boards where the opponent has ≤ 2 stones creates compound pressure.

**Capture moves directed at opponent's weakest board:** Among your legal turns that push a stone off a board, count those targeting the board where `opponent_stones` is already minimal. These are the captures that actually advance your win condition. Weight higher than captures on other boards.

---

### Tier 3 — Tactical Capture Pressure (weight: ±800)

**Executable push-off threats:** Count legal turns that push an opponent stone off any board edge. CRITICAL: only count threats where the passive-aggressive constraint is fully satisfied — a push-off that looks possible on one board is a phantom threat if no corresponding passive move exists on a home board of the opposite color. Every threat count must validate the passive link.

**Net capture pressure:** `capMovesForYou - capMovesForOpp`. Positive = you have more immediate threats than opponent.

**Dual-board fork threat:** A single passive vector enables winning aggressions on multiple boards simultaneously. Detection: enumerate passive moves, compute their vector, count winning aggressive moves consistent with that vector on opposite-color boards. If any vector enables ≥ 2 winning aggressions, flag as fork. Forks targeting boards with ≤ 2 opponent stones are often decisive.

**Forced push-off (unstoppable threat):** Opponent has 1 stone on a board, you have an executable push-off against it, and every legal escape move for that stone is also covered by your threats. Checkmate-equivalent.

**Tempo threat (setup move):** An aggressive move that places your stone adjacent to an opponent stone near an edge, creating a push-off threat for next turn. Even without immediate push-off, forces defensive response.

---

### Tier 4 — Home Board Retention and Mobility (weight: ±300)

**Home board stone counts:** Count your stones on each home board separately. Home board stones have a 1.5× value multiplier compared to away-board stones because they serve as passive-move generators. Losing a home board stone doesn't just reduce material — it cascades into fewer passive moves, which constrains ALL aggressive options on opposite-color boards.

**Home board depletion danger:** If either home board drops to ≤ 2 stones, apply severe penalty. At 1 stone on a home board, you can generate very few passive moves of that board's color, crippling offense on both opposite-color boards.

**Passive vector coverage:** For each home board, compute the set of distinct direction+distance vectors that can be generated as passive moves. `coverage = |vectors_dark_home ∪ vectors_light_home|`. Low coverage is a strategic red flag — it means you can neither attack nor defend in certain directions. Apply penalty when `min(vectors_dark, vectors_light)` falls below a threshold (e.g., < 3).

**Total legal turns:** `legalTurns(you) - legalTurns(opp)`. Since zero legal turns = loss, mobility is existential. A ratio above 1.5 indicates strong positional dominance. Below 0.5 signals crisis. As a cheaper proxy, count passive moves available on each home board (passive count is the binding constraint on total moves).

**Attack capacity by board color:** `attackCapacityOnColor[C]` = number of legal turns whose aggressive move targets a board of color C. Matters when opponent's weak board is of a specific color — you need passive vectors on the opposite-color home board to exploit it.

---

### Tier 5 — Positional Structure (weight: ±50–150)

**Piece-square table per 4×4 board:**

```
 0   1   1   0
 1   3   3   1
 1   3   3   1
 0   1   1   0
```

Center squares (1,1), (1,2), (2,1), (2,2): maximum mobility (8 directions at distances 1-2), cannot be pushed off in a single move (2 squares from any edge), highest passive vector generation. Weight: 3.

Edge squares (non-corner perimeter): reduced mobility (5 directions), one push from elimination. Weight: 1.

Corner squares: severe vector truncation (3 directions), easiest to push off, dead zone for passive generation. Weight: 0 (or slight penalty).

**Home board multiplier:** Multiply positional values by 1.5× for stones on own home boards. A center stone on a home board is vastly more valuable than a center stone on an away board.

**Defensive pairs / two-stone barriers:** An aggressive move can only push one stone. Two adjacent own-color stones aligned along a push direction form an immovable wall from that direction. Count barrier pairs per board. These are high-value defensive assets — opponent cannot break through without first separating the pair. Weight: +30 per pair on boards where `own_stones ≤ 2`.

**Wedge positions:** An own stone positioned between two opponent stones on the same line. Opponent cannot push the wedged stone without a specific passive enabler, and pushing would leave the other opponent stone exposed. Weight: +20 per wedge, higher on boards with low opponent stone count.

**Edge vulnerability count:** Count own stones on board edges/corners per board. Three or more on a single board is a serious liability. Penalty: -15 per edge stone beyond 2 on any single board.

---

## Threat Detection Patterns

**Direct push-off threat (validated):** Your stone at P, opponent stone at Q on a board edge, vector from P to Q points toward the edge, distance 1 or 2. No second opponent stone between P and Q. No own stone blocking. AND a valid passive move exists on a home board of the opposite color, same direction and distance. All four conditions must be met — without passive validation, the threat is phantom.

**Double threat (fork):** You have executable push-off threats on two different boards simultaneously. Since the opponent gets one turn, they cannot defend both. Detection: count boards with executable threats where opponent has ≤ 2 stones. Two or more = often decisive.

**Forced push-off (checkmate-equivalent):** Opponent has 1 stone remaining on a board, you have a push-off threat against it, and no legal move by the opponent can escape all your threats. Detection: enumerate all opponent legal moves involving that stone; check if any move escapes all your threats.

**Home board depletion attack:** Opponent threatens to push a stone off your home board that has ≤ 2 stones. This is a structural threat — losing another home board stone exponentially restricts your passive action space, cascading into reduced offense on opposite-color boards. Weight: 2× the penalty of an equivalent threat on an away board.

**Collapsing defense (forced block failure):** Your blocker stone (protecting a vulnerable stone) is itself targeted for a push by the opponent. Pattern: [your_vulnerable, your_blocker, opponent_attacker] aligned — opponent can push your blocker away, then follow up by pushing your vulnerable stone. Not a safe state — evaluate as a delayed capture.

**Dead position (stalemate indicator):** `capMovesForYou == 0 AND capMovesForOpp == 0`. Neither side can push any stone off any board. If detected, compress evaluation toward 0 (drawish) rather than allowing extreme scores that would be misleading.

---

## Danger Signals (detect and penalize)

Ordered by severity:

1. **Single stone on any board + opponent has win-in-1:** Terminal danger. Opponent can clear your last stone immediately. Near-terminal penalty.

2. **No legal turn or ≤ 2 legal turns:** At zero, terminal loss. At 1-2, one wrong opponent move can make it terminal. Asymptotic penalty as turns approach 0.

3. **Two stones on a board with opponent executable threats against them:** With 2 stones, losing either puts you at 1 (critical). If opponent has validated push-offs against this board, position is dire. Severe penalty.

4. **Home board depletion (≤ 2 stones on either home board):** Losing more than 2 stones from either home board severely limits passive move generation. With 1 stone on a home board, you have minimal passive moves of that color, crippling offense on both opposite-color boards. Penalty: -200 per home board at ≤ 2 stones, -500 at 1 stone.

5. **Passive-move lock:** Home board stones arranged so most directions are blocked (by own stones or board edges), leaving very few legal passive moves. Total passive moves < 5 across both home boards = strategic crisis. Penalty scaled inversely with passive count.

6. **Edge clustering on a single board:** Three or more own stones on board edges/corners of the same board. All are one-push targets, creating multiple simultaneous vulnerabilities. Penalty: -50 per edge stone beyond 2.

7. **Inability to block push:** Opponent has a push-off threat and you have no legal move that (a) moves the threatened stone away, (b) places a second stone behind it to block, or (c) removes the attacking opponent stone. Detection: for each opponent threat, verify if any defensive response exists.

8. **Depletion asymmetry on a single board:** If your stone count on any board is 2+ less than opponent's count on that same board (e.g., you have 1, they have 3), standard 1-for-1 trades on that board are fatal for you — opponent can trade down to 0 while retaining stones. Penalty when differential exceeds 2.

9. **Trapped singleton:** A board with 1 own stone where that stone has zero legal moves (surrounded by opponents/edges). If opponent has any validated attack vector toward it, evaluate as near-terminal loss.

---

## Phase Detection and Weight Adjustment

**Detection metrics (computed from state):**

- Board danger index: `D = min(minOpp, minMy)` — closest-to-terminal board count.
- Total stones removed: `removed = 32 - total_stones_remaining`.
- Home board health: `min(own_home_dark_stones, own_home_light_stones)`.

**Phase thresholds:**

| Phase | Detection | Character |
|---|---|---|
| Opening | `D ≥ 3` (no board close to clearing) AND `removed ≤ 4` | Development, vector building |
| Midgame | `D == 2` OR `5 ≤ removed ≤ 16` | Board-clear races, tactical forcing |
| Endgame | `D ≤ 1` OR any win-in-1 exists | Near-terminal, tactical solvability |

**Opening weight adjustments:**

- Positional quality (center control): **1.5× weight** — piece-square table matters most when all boards have 4 stones. Best opening move is a single diagonal step toward center.
- Home board passive vector coverage: **1.5× weight** — building diverse passive vectors is the foundation for all future play.
- Mobility: **1.2× weight** — avoid structural self-blocking that reduces future options.
- Per-board material: **0.8× weight** — all boards are full, concrete threats are rare.
- Defensive pairs: **1.3× weight** — establishing two-stone barriers early prevents push-offs.

**Midgame weight adjustments:**

- Per-board material (race-to-zero): **2× weight** — boards thin out, creating push-off opportunities. The weakest board dominates strategy.
- Executable threats: **1.5× weight** — capture pressure rises sharply.
- Home board retention: **2× weight** — losing the 3rd stone on a home board is a strategic inflection point. 73% of wins come from home boards.
- Positional quality: **0.7× weight** — secondary to concrete threats.
- Multi-board fork detection: **1.5× weight** — compound threats become available as boards open up.

**Endgame weight adjustments:**

- Win-in-1 / loss-in-1 detection: **DOMINANT** — short-circuit all other evaluation.
- Race-to-zero (minOpp, minMy): **3× weight** — only thing that matters aside from immediate threats.
- Push-off threats and defensive responses: **2× weight** — can the last stone(s) be cornered?
- Positional quality: **near 0× weight** — center control is irrelevant when one board has 1 stone.
- Mobility: **0.5× weight** — still matters for avoiding no-legal-turn loss, but tactical solvability dominates.
- Critical endgame phenomenon: fewer stones on a board paradoxically give the surviving stone more room to evade. The attacker needs careful coordination — ladder-like patterns (repeated chase sequences) should be detected.

---

## Known Pitfalls

**Using total material as the main score.** Counting `totalYourStones - totalOppStones` ignores the per-board win condition. A player up 2 stones total but down to 0 stones on one board has lost. Always evaluate per-board minimums first, then aggregate. The `min()` function across boards is the sole reliable material anchor.

**Phantom threat calculation (ignoring the passive gate).** Detecting an aggressive alignment without verifying the corresponding passive move exists on an opposite-color home board. Every "threat" that skips passive validation is a phantom that will never be executable. The threat detection system must be hardcoded to never score a threat without passive confirmation.

**Treating boards as independent subgames.** The passive-aggressive coupling means advantage on one board depends on vector availability from a completely different board. A player who appears to have a winning attack on Board A but cannot generate the required passive vector on any home board of the opposite color has no attack at all.

**Underweighting home board stones.** A stone on a home board has dual value: material on that board + passive-move generator for attacks on opposite-color boards. Home board stones should carry a 1.5× multiplier compared to away-board stones. Depleting home boards doesn't just lose material — it cascades into reduced offensive capability across all opposite-color boards.

**Linear danger scaling.** Treating the difference between 4→3 opponent stones the same as 2→1 is wrong. The danger curve is exponential. Use quadratic or exponential penalties as stone counts drop below 3 on any board.

**Symmetric trade acceptance.** Standard 1-for-1 trades that appear equal in material are fatal if they reduce your weakest board's count toward zero while the opponent maintains stones there. Penalize any trade that drives your minimum board count closer to 0.

**Overvaluing centralization when the position is tactically decided.** Central squares help mobility, but they don't matter if the opponent has win-in-1 or you do. The evaluation must short-circuit on terminal/near-terminal patterns before computing positional scores.

**Missing push-barrier effects.** Aggressive moves cannot push two stones at once. Two-stone barriers completely invalidate what a naive geometric evaluator thinks is a push lane. Threat detection should account for barriers, and barrier pairs should be scored as defensive assets.

**Greedy capture bias.** Pushing is never mandatory in Shobu. A push on the wrong board can accelerate the opponent's win race elsewhere. Not every available push is good — evaluate whether the capture advances your race or exposes you on another board.

**Ignoring rare dead/locked structures.** Inside-outside column configurations where no push-off is possible for either side exist. If detected (`capMovesForBoth == 0`), compress evaluation toward drawish rather than producing extreme scores.

**Failing to implement the no-legal-turn loss condition.** The designer explicitly clarified: cannot make both passive + matching aggressive = loss. Even states with very few legal turns should be penalized sharply — one more restriction makes them terminal.

**Uniform board valuation.** Not all four boards are strategically equivalent. Home boards matter more (73% of wins occur there). Threats against home boards should carry higher penalties than equivalent threats on away boards.

---

## Implementation Summary

```
1. TERMINAL: Any board cleared? No legal turn? → ±1.0
2. WIN-IN-1: Enumerate legal turns, check for board clearance → near-terminal score
3. RACE: Per-board stone counts with convex (squared) scaling, emphasis on minimum
4. THREATS: Executable push-offs (passive-validated), forks, forced captures on weakest board
5. HOME BOARDS: Stone retention × 1.5 multiplier, passive vector coverage
6. MOBILITY: Legal turn count, penalty curve as turns approach 0
7. POSITION: Piece-square table × home board multiplier, barrier pairs, wedges
8. PHASE: Shift weights based on D = min(minOpp, minMy)
9. SIGMOID: Map weighted sum to [0.0, 1.0]
```

The evaluation's defining tension: you must track four separate material balances simultaneously, and the weakest front determines survival. Every aggressive action requires a passive enabler on a different board — this cross-board coupling must be embedded in every threat calculation, not treated as an afterthought. Decompose per-board first, aggregate with non-linear weighting that emphasizes the weakest front, and always validate the passive link before counting any threat as real.
