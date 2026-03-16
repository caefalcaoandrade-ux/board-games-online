# 6×6 TAK: Evaluation Function Implementation Reference

## Constants

- Board: 6×6 = 36 squares
- Each player: 30 flat stones + 1 capstone = 31 pieces
- Carry limit: 6 (max stones moved from a stack in one move)
- Komi (competitive): +2 flats to Black's count at flat-win resolution
- First-player win rate: ~52% without komi

## Win Conditions (Priority Order)

**Road win (instant, overrides everything):** An orthogonally connected chain of a player's flats and/or capstone spanning any two opposite board edges (left↔right or top↔bottom). Walls (standing stones) do NOT count for roads. Diagonals do NOT count. If a move creates roads for both players simultaneously (Dragon Clause), the moving player wins.

**Flat win (triggered when game ends without a road):** The game ends when the board is completely filled OR any player places their last reserve piece. The player with more visible flat stones on the board surface wins. Only flats on TOP of stacks count — capstones, walls, and buried flats do not count. Equal flat counts = draw.

**Stalemate draw rule (optional, PlayTak.com):** Draw if no stone is placed from reserve and no wall is flattened for 25 consecutive moves.

---

## Feature Set

### Tier 1 — Terminal and Threat Override (weight: ±100,000)

**Road completion detection:** Build a graph over squares where the top piece is the player's flat or capstone (walls excluded). Connect orthogonally adjacent qualifying squares. Test whether any connected component touches both opposite edges (north+south or east+west). Use flood-fill or union-find. If complete road found, return ±1.0 immediately.

**Immediate road-winning move count:** For each player, count moves that complete a road in one action. Two distinct types:

- *Placement wins:* For each empty square, simulate placing a flat. Check if it connects components whose union touches both required opposite edges. Optimization: precompute per-component which edges it touches; for an empty square, union the edge-touch sets of all adjacent same-color components plus any edges the square itself lies on.

- *Movement wins:* For each controlled stack with height > 1, generate legal movement permutations (spread along orthogonal directions, dropping pieces). Test resulting states for road completion. This is expensive — limit to stacks adjacent to near-complete road segments.

If own winning moves > 0: massive bonus. If opponent winning moves > 0: massive penalty. If opponent winning moves ≥ 2 and no single defensive move blocks all: near-certain loss (Tinuë / forced win). Return near-terminal score.

---

### Tier 2 — Road Race (weight: ±5,000)

**Minimum road-completion cost per player per orientation:** Compute shortest-path cost for north↔south and east↔west, take the minimum. Cost model for entering each square:

| Square state | Cost for owner | Cost for opponent |
|---|---|---|
| Empty | +1 | +1 |
| Your flat or capstone (road-eligible) | +0 | +2 |
| Your wall (not road-eligible) | +2 | +4 |
| Opponent flat | +2 | +0 |
| Opponent wall or capstone | +4 | +0 or +2 |

Clamp costs at 7 (too far to matter tactically on 6×6). Compute `road_cost_differential = opp_min_road_cost - own_min_road_cost`. Positive = you're closer to a road = favorable.

**Road-component span metrics:** For each player's connected components of road-eligible squares, compute: which of the 4 board edges it touches, bounding-box width and height (how much of the board it spans). A single group spanning 4 of 6 rows is far more valuable than two groups spanning 2 each. Apply exponential scaling — the NikhilGupta engine proved this critical: per-row and per-column counts of controlled squares with disproportionately higher scores for more squares in a single line.

**Threat multiplicity:** Count distinct winning placement squares and distinct winning movement sequences. Single threat = Tak (forces response). Two or more non-overlapping threats = compound Tak. If no single defensive move blocks all threats = Tinuë (forced win). Score threat differential with steep escalation: 1 threat = large bonus, 2+ threats = near-terminal bonus.

---

### Tier 3 — Flat Count and Material (weight: ±500)

**Visible flat differential:** `own_top_flats - opp_top_flats`. Count ONLY flats on the surface (top of stack or alone on square). Capstones, walls, and buried flats do NOT count. This is the literal tiebreaker for flat wins and the single most important continuous metric after road threats.

**Reserve tracking:** Stones remaining in reserve + whether capstone is still unplayed. Compute `end_trigger_distance = min(empty_squares, min(own_reserves, opp_reserves))`. When end_trigger_distance is small (≤5), flat differential becomes critical. If you lead in flats and have fewer reserves, you can force the game to end — strongest possible endgame position.

**End-trigger pressure alignment:** If `flat_differential > 0` and you can end the game soon (low reserves), bonus. If `flat_differential < 0` and the game is about to end, penalty.

---

### Tier 4 — Control and Stack Quality (weight: ±50–300)

**Controlled squares count:** Number of stacks where your piece is on top. More = more options, more potential road material, more threats.

**Stack composition (hard vs soft):**

- *Hard stack:* You control it and the majority of pieces inside are yours. Resilient, valuable. High hardness ratio = `own_pieces_in_stack / total_height ≥ 0.5`.
- *Soft stack:* You control it but opponent has majority inside. Dangerous — one recapture liberates a swarm of enemy pieces. Low hardness ratio = liability.

Compute `hard_stack_mass - soft_stack_mass` per player. Penalize soft stacks, especially tall ones near opponent's strong pieces.

**Future Potential Flat Count Differential (FPFCD):** Count own flats buried under opponent stacks minus opponent flats buried under own stacks. These are latent material that can swing the flat count dramatically when stacks are recaptured. Critical advanced metric that naive implementations miss.

**Capstone status:**

- *Hard cap:* Capstone with same-color flat directly beneath it. Best configuration — can crush walls while the "deputy" flat retains control of the square left behind. Weight: +200.
- *Soft cap:* Capstone with opponent-color piece directly beneath. Weaker — moving concedes the square. Weight: +50.
- *Overloaded cap:* Capstone on a tall stack with many captives. Reduced mobility and crushing ability. Penalty.
- *Pinned cap:* Moving the capstone would allow opponent road completion. Severe penalty — functionally useless for offense.

**Liberties/expansion:** Count empty squares orthogonally adjacent to your road-eligible connected mass. More liberties = more places to extend, defend, and create threats.

---

### Tier 5 — Positional (weight: ±10–100)

**Square value matrix for 6×6:**

```
     a   b   c   d   e   f
6  [ 2,  3,  3,  3,  3,  2]
5  [ 3,  4,  4,  4,  4,  3]
4  [ 3,  4,  4,  4,  4,  3]
3  [ 3,  4,  4,  4,  4,  3]
2  [ 3,  4,  4,  4,  4,  3]
1  [ 2,  3,  3,  3,  3,  2]
```

Center squares (c3,c4,d3,d4) have 4 orthogonal neighbors — maximum connectivity and influence. Corners have only 2 — weakest. But edge squares are necessary as road anchors — a road MUST touch both opposite edges.

**Capstone centrality:** Explicit bonus for capstone closer to center. The NikhilGupta engine found this significantly improves play. `capstone_centrality = 3 - manhattan_distance_to_nearest_center_square`.

**Edge anchoring:** Penalize edge placement UNLESS the piece is serving as an anchor in the player's current best road orientation (touching an edge that the minimum-cost road needs). Anchors are conditionally valuable — roads require them.

**Adjacency multiplier:** A controlled square adjacent to other friendly road-eligible pieces is worth 1.5× its positional value. An isolated square is worth 0.5×. This encourages cohesive connected clusters over scattered pieces.

**Wall evaluation:**

- Own walls: small penalty (walls don't count as flats, don't count for roads, block your own paths).
- Opponent walls: larger penalty from opponent's perspective (blocks their roads AND costs them flat count).
- Exception: a wall directly blocking the opponent's only viable road path is extremely valuable.
- Walls on edges are more effective defensively (the edge restricts workaround options).
- "Drawbridge" formation: wall on top of own flat in a stack. Hidden offensive weapon — spreading the stack reveals the flat and can complete a road. Bonus when drawbridge position is detected.

---

## Threat Detection Patterns

**Single Tak threat:** One move from road completion. Two sub-types:

- *Potential road* (gap fillable by placing a new flat): Opponent can block by placing in the gap. Detect by testing each empty square as described above.
- *Road threat* (completable by moving existing stack): Cannot be blocked by placement alone — requires capture or movement to defend. Significantly harder to defend. Detect by simulating stack movements of stacks adjacent to near-complete road segments.

**Compound Tak / Tinuë:** Multiple simultaneous road-completion options. If each requires at least one defensive move but defender gets only one move, it's forced win. Sub-types:

- *Forked roads:* Single connected group with two separate paths to completion.
- *Bypass roads:* Alternative route around defender's blockage.
- *Bi-cardinal roads:* Corner-anchored road that can complete via either axis.
- *Crush-mates:* Road gap blocked only by a wall, attacker has capstone to flatten it, defender's capstone committed elsewhere.

**Capstone flattening threat:** Capstone adjacent to wall blocking near-complete road. If defender must address this AND another threat simultaneously, compound threat.

**Stack spread threat:** Single stack movement claiming multiple squares. On 6×6 with carry limit 6, a stack can spread across up to 6 squares. A tall controlled stack near center can threaten road completion in multiple directions. Check whether any controlled stack, when optimally spread in any direction, would complete a road.

**Flat-win threat:** Can end game this turn (place last reserve piece or fill last empty square) while leading in visible flats. Immediate winning threat.

**Drawbridge reveal:** Wall-topped stack containing accessible own flat. Spreading the stack reveals the flat, potentially completing a road or creating new winning placement squares.

---

## Danger Signals (detect and penalize)

1. **Opponent has compound Tak** (2+ simultaneous road threats, no single move blocks all) — near-certain loss. Near-terminal penalty.

2. **Opponent controls tall central stack** (3-4+ flats) aimed at near-complete road segments — one spread can complete a road that looked 6 moves away. Severe penalty.

3. **Own capstone overloaded with prisoners** — can't flatten walls, mobility reduced to short-range shuffles. Moderate penalty.

4. **Own pieces scattered, low connectivity** while opponent has connected chain spanning 4+ rows/columns. Moderate penalty.

5. **Behind in flat count with more reserves remaining** — worst endgame position, can't force game-ending board fill. Penalty increasing as reserves deplete.

6. **Opponent capstone centrally positioned in hard-cap configuration** — maximum offensive potential in every direction. Moderate penalty.

7. **Own stacks predominantly soft** (opponent's pieces form majority inside) — opponent can recapture and swing flat count at will. Penalty proportional to soft stack mass.

8. **Board filling and trailing in flat count** — approaching flat-win endgame you cannot win. Increasing penalty as empty squares decrease.

9. **Pinned capstone** — hard pin (moving allows opponent road) or soft pin (moving loses major material). Reduce capstone's mobility and influence scores to zero.

10. **Overgrown stacks** beyond carry limit — height above 6 is wasted (can't move in one action). Penalize `Σ max(0, height - 6)` across all own stacks.

---

## Phase Detection and Weight Adjustment

**Detection metrics:**

- Board density: `occupied_squares / 36`
- Reserve metric: `r_min = min(white_reserves, black_reserves)`
- Endgame proximity (concrete formula): `endgame_factor = max(0, 7 - min(r_min, 7)) / 7` — linearly increases flat importance as reserves approach 0.
- Capstone deployment flags: whether each capstone is in play (changes tactics via crushing and unstackability).

**Phase thresholds for 6×6:**

| Phase | Density | Reserves | Move count |
|---|---|---|---|
| Opening | < 0.33 | > 75% (23+) | 1–12 |
| Midgame | 0.33–0.75 | 25–75% | 12–35 |
| Endgame | > 0.75 | < 25% (< 8) or either player < 5 | 35+ |

**Opening weight adjustments:**

- Increase: center influence, capstone centrality, controlled squares, liberties, cohesion. Prevent edge-hugging.
- Decrease: road-cost urgency (early costs volatile before meaningful blocking).
- Avoid premature captures — placing a new flat from reserve is almost always better than a simple capture early.
- Avoid premature capstone deployment unless it simultaneously advances threats, stops opponent's, or secures a large stack.

**Midgame weight adjustments:**

- Maximize: road-cost differential, threat detection (potential roads, road threats, forks, drawbridges, crush threats).
- Increase: wall context scoring (walls that block opponent road paths are valuable; random walls waste tempo).
- Increase: soft stack penalty (mid-game captures and stack movements are frequent and volatile).
- Create threats — even easily-defeated threats force suboptimal defensive responses.

**Endgame weight adjustments:**

- Multiply flat differential weight by 5×.
- Increase wall penalty exponentially (placing a wall burns a turn without increasing flat count).
- Maintain road-win detection at full strength — road wins can appear unexpectedly from late-game stack spreads.
- If no viable road threat exists for either side, shift entirely to flat-count optimization.
- Reward wide horizontal captures that flip opponent top-level flats to friendly control.

---

## Known Pitfalls

**Overvaluing captures.** A simple capture (moving one flat onto one enemy flat) is flat-count-neutral — you trade one controlled square for another. Worse, it creates a stack with an enemy captive the opponent can recapture. Placing a new flat from reserve is almost always superior. Do not reward simple captures unless they directly contribute to a road or remove a verified threat.

**Static road-distance metrics.** Counting "shortest distance to road completion" without considering stack spreads badly underestimates tactical danger. A stack of 6 can bridge 6 squares in one move, instantly completing a road that appeared 6 moves away by naive counting.

**Ignoring stack composition.** Community mnemonic: "The Fox Prances To The Barn, Smelling Turkey" — check stacks every turn. A large opponent stack near your road network is a detonation threat. FPFCD (future potential flat count from stack liberation) must be tracked.

**Flattening opponent walls reflexively.** Their wall gave you a flat-count advantage (walls don't count as flats for them). Crushing it undoes that gift. Only flatten when it enables a specific winning sequence — road completion, major captive liberation, or blocking the only defense against your threat.

**Fixed weights across all phases.** An evaluation weighing road threats and flat count identically throughout will play the opening too aggressively and the endgame too passively. Dynamic phase-weighted scaling is essential.

**Horizon effect on stack spreads.** Documented as Tiltak's primary weakness: MCTS pruning discards branches the value network scores poorly, missing 2-move wins via stack spreads. Consider dedicated threat extensions — force evaluation of all Tak-threat moves to minimum depth regardless of pruning.

**Treating all walls equally.** A wall blocking the opponent's only road path is extremely valuable. A wall blocking your own connectivity is tempo-destroying. Evaluate walls contextually by what they block on each side's road-cost graph.

**Neglecting edge anchoring.** A connected chain spanning the center means nothing without edge connections. Track whether each player's largest group touches at least one square on each of two opposite edges.

**Counting buried flats for flat wins.** Only TOP flats count. Buried flats, capstones, and walls contribute nothing to flat-win scoring. This is the most common counting error.

**"Height is always good."** Height beyond carry limit (6) is partially unusable in one move and becomes dead weight. Practical engines explicitly penalize overstacking after observing pathological AI behavior building 16-high stacks.

**Premature capstone commitment.** Crushing a wall can strand the capstone on the board edge, trapping it on a useless stack and removing its latent threat power from the center. Only reward wall flattening if it decreases road-completion cost, liberates significant captives, or is the only defense against an opponent threat.

---

## Implementation Summary

The evaluation function architecture for 6×6 TAK:

```
1. TERMINAL CHECK: Road complete? → ±1.0
2. THREAT OVERRIDE: Immediate winning/losing moves? Tinuë? → near-terminal score
3. ROAD RACE: Road-cost differential + component span (exponential scaling) + threat count
4. FLAT MATERIAL: Visible flat differential × (1 + endgame_factor × 4)
5. CONTROL: Controlled squares + liberties + stack quality (hard/soft) + capstone status
6. POSITIONAL: Square values × adjacency multiplier + capstone centrality + anchor scoring
7. SIGMOID NORMALIZATION: Map weighted sum to [0.0, 1.0]
```

The dynamic tension between flat count and road threats — and the dramatic shift in their relative importance across game phases — is the core challenge. Three design decisions determine evaluation quality: exponential scaling for row/column road composition, dedicated threat detection separate from positional evaluation, and phase-sensitive weight adjustment shifting emphasis from connectivity to flat count as the board fills.
