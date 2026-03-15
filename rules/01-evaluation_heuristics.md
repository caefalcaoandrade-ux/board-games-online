# Game-Specific Evaluation Functions: Implementation Reference

## Architecture

Every evaluation function below follows this structure:

```
def evaluate_position(state, player_id) -> float:
    # Layer 1: Terminal/threat overrides (±1.0 or near it)
    # Layer 2: Weighted feature sum, phase-adjusted
    # Layer 3: Sigmoid normalization to [0.0, 1.0]
```

Return 1.0 = certain win for player_id, 0.0 = certain loss, 0.5 = even.

**Performance constraint:** Called thousands of times per second by the MCTS bot. Avoid calling get_legal_moves inside the evaluation — use direct state inspection instead.

---

## 1. ABALONE

**Win condition:** Push 6 of opponent's 14 marbles off the hex board edge.

**The one feature that matters most:** Marble differential (pushed-off count). Weight: 800. This single feature accounts for ~70% of evaluation accuracy.

**Feature set:**

| Feature | Weight | Computation | Why |
|---------|--------|-------------|-----|
| Marbles pushed off differential | 800 | `opp_off - own_off` | Direct win progress, irreversible |
| Center distance | 8 | `-Σ hex_distance(marble, center)` for own marbles | Central marbles can't be pushed off, have max push power |
| Group cohesion | 3 | `-Σ pairwise_distance(own_marbles)` | Connected groups execute pushes; isolated marbles get picked off |
| Edge exposure | 30 | Count own marbles on outermost ring adjacent to opponent inline groups | Immediate push-off vulnerability |
| Push threats (sumito) | 50 | Count 3v1, 3v2, 2v1 alignments where push leads off-board | One-move win progress |

**Threat override:** If any push-off is available this turn → large bonus. If opponent can push off next turn → large penalty.

**Phase detection:** `total_pushed_off = own_off + opp_off`. Early (0-1): weight center + cohesion 2×. Late (3+): weight marble differential 100×, shift to pure aggression.

**Pitfall:** Pushing off a marble that fragments your own formation can lose the game. Don't reward pushes without checking resulting cohesion. Games can cycle indefinitely — add move-count penalty to encourage decisive play.

---

## 2. AMAZONS

**Win condition:** Opponent has no legal moves (queens move, then shoot blocking arrows on 10×10 board).

**The one feature that matters most:** Territory differential via distance maps. This game is fundamentally about spatial partitioning.

**Feature set (Lieberum 2005 — Computer Olympiad champion):**

| Feature | Phase Weight | Computation |
|---------|-------------|-------------|
| Queen-distance territory (t1) | Peaks late | For each empty square, BFS queen-move distance from each player. Square owned by closer player. `Σ sign(D_opp - D_own)` |
| King-distance territory (t2) | Peaks early | Same but single-step distance. More stable early measure |
| Continuous territory (c1) | Mid-weight | `Σ clamp((D_opp - D_own)/2, -1, 1)` — partial credit for partial advantage |
| Mobility correction (m) | ±18 points | Per-amazon reachability with distance decay. Enclosed amazon (α=0) penalized ≥10 points |

**Phase detection:** `w = Σ 2^{-|D_own(sq) - D_opp(sq)|}` over contested squares. w=0 means board fully partitioned (filling phase). Blend territory measures using w as continuous phase parameter.

**Threat override:** Any move+arrow leaving opponent with 0 legal moves = immediate win. Detect arrow placements that sever the board graph at articulation vertices.

**Pitfall:** "Defective territory" — regions that appear accessible but cost extra moves to enter. Pure square-counting without distance weighting fails catastrophically. Ignoring side-to-move in late positions misses zugzwang (common in filling phase).

---

## 3. ARIMAA

**Win condition:** Rabbit reaches opponent's 8th rank. Also: eliminate all opponent rabbits or immobilize opponent. Each turn = 4 steps.

**The one feature that matters most:** Trap control. The 4 trap squares (c3, f3, c6, f6) are the only capture mechanism.

**Feature set (Wu 2015 — SHARP, Arimaa Challenge winner):**

| Feature | Priority | Computation |
|---------|----------|-------------|
| Goal threat | OVERRIDE | Can any rabbit reach goal in ≤4 steps? If yes, massive bonus. If opponent can, massive penalty. |
| Trap control | 1st | Per trap: count friendly defenders (0-4), strongest piece present, steps-to-capture nearby enemy pieces |
| Relative material (HarLog) | 2nd | Piece values depend on remaining opponents. Baseline: Elephant=∞, Camel≈5000, Horse≈3000, Dog≈1800, Cat≈1500, Rabbit≈1000 |
| Frozen/immobilized pieces | 3rd | Count pieces adjacent to stronger enemy with no friendly support |
| Hostage/frame patterns | 4th | Pieces held near opponent's trap, tying down strong pieces |
| Rabbit advancement | 5th | Max rank of most advanced rabbit (higher = closer to goal) |

**Phase detection:** By total pieces captured and rabbit advancement depth. Early: trap control dominates. Mid: hostage tactics. Late: goal threats override everything — material sacrifices for rabbit advancement become sound.

**Pitfall:** MCTS fails catastrophically for Arimaa — random rollouts value extra rabbits over elephants because rabbits randomly stumble to goal. Branching factor is ~17,000. Static piece values are wrong — always compute relative values based on remaining opponents. Never ignore that rabbits cannot move backward.

---

## 4. BAGH CHAL

**Win condition:** Tigers win by capturing 5 goats. Goats win by immobilizing all 4 tigers. Asymmetric.

**The one feature that matters most:** Tiger aggregate mobility (for goat evaluation) / Captured goats count (for tiger evaluation).

**Feature set (asymmetric — evaluate from each side):**

| Feature | Tiger Weight | Goat Weight | Computation |
|---------|-------------|-------------|-------------|
| Captured goats | +500 per goat | -500 per goat | Count goats removed from play |
| Tiger total mobility | +15 per move | -15 per move | `Σ legal_moves(each_tiger)` — use direct adjacency check, not get_legal_moves |
| Available captures | +50 per capture | -50 per capture | Count immediate jump-capture options (tiger, adjacent goat, empty landing) |
| Trapped tigers (0 moves) | -100 each | +100 each | Count tigers with no adjacent empty nodes |

**Positional value:** Center node (2,2) has 8 connections — highest value. Corners have only 3. The 5×5 grid has irregular diagonal connectivity (not all positions connect diagonally).

**Phase detection:** Binary: placement phase (goats_placed < 20) vs movement phase. During placement, goats prioritize safe placement avoiding jump-capture alignments. During movement, goats close the net.

**Pitfall:** Optimal play is a draw. Under random play tigers win disproportionately — biases MCTS training. Must penalize individual tiger isolation, not just aggregate mobility. Repetition loops are extremely common — penalize repeated positions.

---

## 5. BAO LA KISWAHILI

**Win condition:** Empty all seeds from opponent's front row (8 pits), or opponent has no legal moves.

**The one feature that matters most:** Opponent's empty front-row pits. Each empty pit is direct, often irreversible progress toward winning.

**Feature set:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Opponent empty front pits | 100 per pit | Count empty pits in opponent's front row (0-8) |
| Front row seed differential | 40 | `own_front_seeds - opp_front_seeds` |
| Capture opportunities | 30 | Count own non-empty front pits facing non-empty opponent front pits (markers) |
| Opponent singleton count | 8 per singleton | Opponent pits with exactly 1 seed (immobile in mtaji) |
| Own pits with ≥2 seeds | 20 | Count own pits with 2+ seeds (legal sowing starts in mtaji) |
| Nyumba status | 15 | Binary: own nyumba functional with ≥6 seeds |

**Phase detection:** `namua` (seeds in hand > 0) vs `mtaji` (all seeds on board). Detect by checking if either player has seeds remaining in hand. In namua: weight capture initiation from hand. In mtaji: weight relay chain potential and pit distribution.

**Pitfall:** Total seed count is deeply misleading — captures move seeds to your side rather than removing them. Relay sowing makes static evaluation unreliable — a balanced position can be won in one move through a long chain. Infinite relay loops exist and must be detected. Search depth 6+ is essential.

---

## 6. BASHNI

**Win condition:** Opponent has no legal moves (captured or blocked). Captured pieces stack under captor and are freed when the top piece is captured.

**The one feature that matters most:** Stack ownership — number of stacks where your color is on top. Buried pieces are useless until liberated.

**Feature set:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Controlled stacks (your color on top) | 1000 per stack | Iterate all occupied squares, check top piece color |
| King-topped stacks | 500 per king | Count stacks where top piece is a promoted king |
| Hidden prisoners | 200 per prisoner | `opponent_pieces_under_your_stacks - your_pieces_under_opponent_stacks` |
| Stack composition depth | 150 per level | Per own stack: count consecutive friendly pieces from top before hitting enemy |
| Center control | 30 per piece | Own top-pieces on center squares (rows 3-6 of 10×10) |
| Advancement toward promotion | 20-80 graduated | Distance to promotion row, weighted higher when closer |

**Threat detection — liberation threat is paramount:** Detect when opponent can capture the top of your tall stack, freeing their buried pieces. A stack [YourPiece, EnemyPiece, EnemyPiece, ...] is a bomb — one capture flips ownership of everything below.

**Phase detection:** By total pieces remaining and capture availability. Early: back-row integrity (weight 2×). Mid: stack composition critical, liberation threats constant. Late: king possession and stack composition dominate.

**Pitfall:** The #1 mistake is ignoring stack internals. Counting only top pieces misses that capturing one piece can liberate 5 enemies. Standard checkers heuristics fail completely. Mandatory capture rules mean mobility scoring is wrong whenever a capture exists. Expert strategy: "It is often advantageous to feed several of one's own men to a not-too-strong opponent stack and then capture the top layer."

---

## 7. ENTRAPMENT

**Win condition:** Eliminate all 3 opponent roamers by immobilizing them (surrounded on 4 orthogonal sides by barriers, edges, or other roamers).

**The one feature that matters most:** Minimum roamer mobility — the weakest roamer's move count matters more than aggregate mobility.

**Feature set:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Roamer count differential | 10000 | `own_roamers - opp_roamers` |
| Minimum own roamer mobility | 500 | Lowest move count among any own roamer (0 = dead) |
| Enclosure progress | 300 per side | Per opponent roamer: count blocked orthogonal sides (0-4) |
| Total mobility differential | 100 per move | `Σ own_roamer_moves - Σ opp_roamer_moves` |
| Barrier economy | 20 per barrier | `own_barriers_remaining - opp_barriers_remaining` |

**Positional value:** Corners need only 2 barriers to trap (2 sides are board edges). Edges need 3. Center needs 4. Push opponents toward edges; keep own roamers central.

**Threat detection:** Opponent roamer with exactly 1 legal move + you have a legal barrier placement that blocks it = trap-in-1. Enumerate barrier placements near their escape squares.

**Phase detection:** By barrier density (barriers placed / total) and average roamer mobility. Early (high mobility): weight central safety. Mid (maze forming): weight confinement. Late (tight): near-terminal trap detection dominates.

**Pitfall:** Standing barriers block both players equally. Always verify a barrier reduces opponent mobility more than your own. Having 3 roamers with 1 move each is worse than 2 roamers with 8 moves — don't overvalue raw roamer count vs mobility. Must account for the jump-to-lock mechanic (jumping own resting barrier flips it to permanent standing barrier).

---

## 8. HAVANNAH

**Win condition:** Complete a ring (closed loop), bridge (connects 2 of 6 corners), or fork (connects 3 of 6 edges).

**The one feature that matters most:** No single static feature works. All competitive Havannah programs use MCTS, not minimax. Use these as MCTS bias features, not static evaluation.

**MCTS bias features (priority order):**

| Priority | Feature | Implementation |
|----------|---------|----------------|
| 1 | Decisive/anti-decisive moves | Any move that immediately wins or blocks opponent's win. OVERRIDE all other heuristics. |
| 2 | Virtual connections (2-bridges) | Two stones with two shared empty neighbors = virtually connected. Bonus for maintaining VCs. |
| 3 | Edge/corner adjacency | Moves connecting a group to a board edge or corner progress toward bridge/fork. Count distinct edges touched. |
| 4 | Distance to win | Minimum additional stones needed to complete any bridge/fork/ring. Lower = better. |
| 5 | Independent threats | Count of disjoint near-win structures. Multiple simultaneous threats are often unblockable. |

**If used as playout cutoff evaluation:** Count edges touched by largest group (fork progress), corners touched (bridge progress), and whether any group forms a near-ring. Weight fork progress highest since forks are the dominant strategic win condition.

**Phase detection:** By move count or best-frame widths. Early: distance heuristic and center/edge influence. Mid: connection patterns and virtual connections. Late: decisive move detection critical — ring threats emerge and are hard to detect.

**Pitfall:** Ring blindness — MCTS with random rollouts misses ring threats entirely. Virtual connections from Hex don't directly transfer. Programs struggle when threats span multiple win types simultaneously (fork + ring). Evaluating only connected group sizes misses virtual connections.

---

## 9. HIVE

**Win condition:** Completely surround opponent's Queen Bee (all 6 adjacent hexes occupied by any color).

**The one feature that matters most:** Queen surround differential. `pieces_around_opp_queen - pieces_around_own_queen`. This accounts for ~60-80% of evaluation accuracy.

**Feature set (Ibn-Nasar 2020, Kampert/Leiden IEEE):**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Queen surround differential | 2000 | `adj_occupied(opp_queen) - adj_occupied(own_queen)` (each 0-6) |
| Kill spots | 500 each | Empty hexes adjacent to opponent queen reachable by any own piece in 1 move |
| Mobility differential | 100 | `own_movable_pieces - opp_movable_pieces` (accounting for One Hive pins) |
| Beetle coverage | 300 | Own beetle on top of any piece adjacent to opponent queen |
| Queen placement timing | -200 | Penalty if queen not placed by turn 4 (mandatory rule) |

**Piece values:** Queen=50, Beetle=20, Ant=15-20 (strongest late game), Grasshopper=15, Spider=10.

**Threat detection:** At 5/6 queen surround, check if any piece can reach the last hex. Grasshopper jump finishes (jumping over a line to land on the final hex) are commonly missed by AIs. Ant rush: check if any ant can reach an empty hex adjacent to opponent queen.

**Phase detection:** Early (turns 1-6): placement decisions, queen must be placed by turn 4. Mid (7-15): mobility and pin detection critical. Late (16+): queen surround differential overwhelmingly dominant.

**Pitfall:** AIs consistently over-attack without defending — surrounding opponent queen while own queen sits at 4/6 surrounded. Beetles chronically undervalued. Must enforce One Hive Rule in mobility counting (pieces that are articulation points can't move). Simultaneous-surround = draw, must handle explicitly.

---

## 10. COPENHAGEN HNEFATAFL

**Win condition:** Defenders: king escapes to any corner. Attackers: capture king (surround on 4 sides, or 3 + edge/throne).

**The one feature that matters most:** King distance to nearest corner (defenders) / King containment integrity (attackers). Asymmetric evaluation required.

**Defender evaluation:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Guaranteed escape (clear edge row) | +1000 | Any edge row completely free = 2-move win |
| King distance to corner | 200 per step | BFS: empty=cost 1, ally=cost 2, enemy=cost 3 |
| King escape routes | 100 per route | Count unobstructed straight-line paths to any corner |
| Defender material | 20 per piece | `defenders_alive - (attackers_alive * 0.5)` scaled for asymmetry |

**Attacker evaluation:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| King capturable next move | +1000 | King surrounded on 3 sides + can place 4th |
| King has no escape route | +800 | All paths to corners blocked |
| Capture contact | 200 per side | Pieces adjacent to king (0-4 needed) |
| Encirclement quality | 100 | Average distance of attackers from king, low variance = good ring |
| Material advantage | 15 per piece | Each defender captured matters more than each attacker lost |

**Phase detection:** By piece density and king location. Early: corridor creation/denial. Mid: tactical capture nets, shieldwall threats. Late: king racing vs final capture.

**Pitfall:** Evaluation MUST be asymmetric — separate functions per side. King on throne requires 4 pieces to capture, not 2. Edge fort / shieldwall detection essential for Copenhagen variant but missing from most implementations. 7×7 boards favor material; larger boards favor positional play. Missing "clear edge" detection = missing 2-move wins.

---

## 11. SHOBU

**Win condition:** Push all 4 opponent stones off any single board (4 boards: 2 light, 2 dark, each 4×4).

**The one feature that matters most:** `min(opponent_stones[board])` across all 4 boards. The board closest to being cleared is everything. Total stones across boards is meaningless.

**Feature set (Foltz 104K game analysis):**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Critical board (min opp stones) | 5000 × (4 - min) | `min(opp_stones[b] for b in boards)` |
| Executable push-off threats | 2000 each | Edge stones with valid matching passive move in same direction/distance |
| Own critical board defense | -4000 × (4 - min) | `min(own_stones[b] for b in boards)` |
| Edge vulnerability | 300 per stone | Count opponent stones on board edges |
| Center control | 100 per stone | Stones at [1,1], [1,2], [2,1], [2,2] per board |

**THE CRITICAL CONSTRAINT:** Every aggressive push must match the direction AND distance of a passive move on a home board. An evaluation that scores push-off threats without verifying a matching passive move exists is fundamentally broken. Home board positions dictate which aggressive actions are possible.

**Phase detection:** By `min(opp_stones)` and `min(own_stones)`. Early (all 4s): center control and vector flexibility. Mid (someone at 1-2): target weakest board. Late: "preventing your own pieces from being pushed rather than pushing" — defense dominates.

**Pitfall:** Board myopia — evaluating boards independently misses passive-aggressive coupling. Having 0-4-4-4 stones (12 total) is a LOSS despite 12 remaining. Players consistently report overlooking an opponent's winning move on one board while focused on another. 43% of first-player wins occur on their closest home board.

---

## 12. TUMBLEWEED

**Win condition:** Control more hexes (own stacks + exclusively reachable empty cells) when both players pass.

**The one feature that matters most:** Territory differential = `(own_stacks + own_controlled_empty) - (opp_stacks + opp_controlled_empty)`.

**Feature set:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Territory differential | 100 per cell | Occupied + controlled empty cells per player |
| Stack safety | 200 per safe stack | Safe if `stack_height ≥ max_possible_enemy_LOS` on that hex |
| Capture threats | 150 each | Enemy stacks where your LOS count > their height |
| Network connectivity | -100 per extra group | Fewer disconnected groups = stronger (harder to capture) |
| Group life/death | 500 per alive group | Groups that cannot be captured regardless of play = alive |

**Core mechanic — Line of Sight (LOS):** Each stack sees in 6 hex directions up to the nearest other stack. New stack height = count of own stacks with LOS to that hex. Captures require strictly larger resulting stack.

**Key patterns:** "3-stacks in corners are always alive." Wall-building (continuous lines cutting off enemy LOS into entire sectors) is the dominant strategic concept. Triangular formations are efficient.

**Phase detection:** By board occupancy. Early: maximize LOS influence, 1-2 stacks dominate. Mid: wall building, cutting networks, capture tactics. Late: exact territory counting, life/death of groups is paramount (becomes Go-like).

**Pitfall:** Ignoring life and death is the #1 error — territory containing dead stacks is worth 0. Reinforcing to a 2-stack is almost always bad. Capturing isn't always good — costs tempo. Beware snipers: late-stage long-LOS captures across the board. Stack height is purely defensive — a height-8 stack sees no further than height-1.

---

## 13. YINSH

**Win condition:** First to remove 3 of own rings (by completing rows of 5 same-color markers). Each ring removal costs one ring.

**The one feature that matters most:** Rings removed differential. But the PARADOX: scoring reduces your rings, reducing your mobility. Leading 2-1 means you have 3 rings vs opponent's 4.

**Feature set:**

| Feature | Weight | Computation |
|---------|--------|-------------|
| Rings removed differential | 1000 per ring | `own_scored - opp_scored` (0-3 each) |
| 4-in-a-row threats | 200 each | Count lines of 4 own-color markers (one flip from scoring) |
| 3-in-a-row potential | 50 each | Count lines of 3 own-color markers |
| Ring mobility total | 10 per move | `Σ legal_ring_positions(each_ring)` via direct adjacency, not get_legal_moves |
| Double threats | 500 | Two simultaneous near-rows = nearly unblockable |

**Threat override:** Any ring move creating a row of 5 = forced score. CRITICAL: moving a ring flips all markers it jumps over — must simulate full flip consequences. A move can inadvertently create a row of 5 for the opponent.

**Ring removal choice:** When scoring, remove the ring with lowest mobility / worst position. When multiple rows form, only one is scorable — choice matters.

**Phase detection:** By markers on board + markers in pool + rings removed. Placement (turns 1-5): ring positioning. Early movement (6-15): spread markers. Mid (15-30): flip chains powerful, board crowding. Late (after first removal): "rubber-band" effect — trailing player often has more tactical tools with more rings.

**Pitfall:** "Winning is losing" paradox must be explicitly modeled. Flip cascades completely transform the board in one move — static evaluation without simulating flips is unreliable. Row overlap (multiple rows, only one scorable) creates complex decisions. AIs often score too early, crippling their own mobility.

---

## Cross-Cutting Implementation Guidance

1. **The dominant feature accounts for 60-80% of evaluation accuracy.** Get it right before adding complexity: marble count (Abalone), territory (Amazons/Tumbleweed), queen surround (Hive), min-board stones (Shobu), king distance (Hnefatafl).

2. **Phase-dependent weight shifting is essential.** Use continuous blending parameters rather than hard phase boundaries. Nearly every game requires different weights in opening vs endgame.

3. **Threat detection at the evaluation level, not just search.** Amazons enclosures, Arimaa goal threats, Hive grasshopper finishes, Hnefatafl clear-edge wins, Shobu push-off availability — all must be computed in the evaluator because search alone misses them at practical depths.

4. **Keep evaluations fast.** Avoid calling get_legal_moves inside evaluate_position. Use direct state inspection: count pieces by iterating the board, check adjacency by coordinate math, detect patterns by scanning specific positions. The bot calls this function thousands of times per second.

5. **Asymmetric games need separate evaluation logic per side.** Bagh Chal, Hnefatafl — the same position is evaluated completely differently depending on which side you are.
