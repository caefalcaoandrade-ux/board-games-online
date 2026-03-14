# Bao la Kiswahili — Definitive Ruleset Specification

## 1. Board Topology

The board is a 4×8 grid of 32 pits. Each player owns two adjacent rows: a **front row** (inner, facing the opponent) and a **back row** (outer, away from the opponent). Pit indexing per player runs left-to-right from that player's perspective: **F1–F8** (front row) and **B1–B8** (back row).

Opposed pits: a player's **F1** directly faces the opponent's **F1**, **F2** faces **F2**, and so on through **F8**.

The sowing track forms a 16-pit closed loop per player. Clockwise traversal: F1→F2→…→F8→B8→B7→…→B1→F1. Anticlockwise is the reverse.

## 2. Named Pits

Each player's front row contains these named pits:

| Name | Pits | Role |
|---|---|---|
| **Kichwa** (head) | F1 and F8 | Mandatory entry points for captured seeds |
| **Kimbi** (flank) | F1, F2, F7, F8 | Directional constraint zone (includes the kichwa) |
| **Nyumba** (house) | F5 | Accumulation pit with special stopping and taxation rules |

F1 is the **left kichwa**; F8 is the **right kichwa**. F2 is the **left kimbi**; F7 is the **right kimbi**.

## 3. Seeds and Initial Setup

Total seeds in the game: **64** (32 per player). Each player begins with:

- **F5 (nyumba):** 6 seeds
- **F6:** 2 seeds
- **F7:** 2 seeds
- All other pits: 0 seeds
- **Store (off-board reserve):** 22 seeds

**South moves first.**

## 4. Objective and Game End

A player **loses** immediately if any of the following occur, checked continuously even mid-move:

1. The player's front row is completely empty.
2. The player has no legal move (all pits contain at most 1 seed and no store seeds remain).
3. The player's only available move is infinite (non-terminating).

## 5. Game Phases

### 5.1 Kunamua (Opening Phase)

Active while the moving player has seeds remaining in their store. Every turn begins by placing exactly 1 seed from the store into a non-empty front-row pit, then proceeding according to the capture or takata rules below.

### 5.2 Mtaji (Main Phase)

Begins for a player the moment their store is empty. Turns begin by selecting a pit on the player's own side containing ≥2 seeds, then sowing its contents. Each player transitions independently; one may be in mtaji while the other is still in kunamua.

## 6. Move Classification

Every turn is classified at its outset and the classification is **locked for the entire turn**:

- **Mtaji turn (capture turn):** The first action of the turn produces a capture. Further captures may occur during relay sowing.
- **Takata turn (non-capture turn):** The first action does not produce a capture. **No capture may occur at any point during this turn**, regardless of board geometry encountered later.

**Forced capture rule:** If any legal opening that produces a capture exists, the player **must** choose a capture opening. Takata is only legal when no capture opening exists.

## 7. Capture Mechanics

### 7.1 Capture Condition

A capture occurs when a sowing ends (last seed drops) in a pit on the player's own front row such that:

- The ending pit is **non-empty after the drop** (i.e., contained ≥1 seed before the drop).
- The **directly opposed** opponent front-row pit is **non-empty**.
- The current turn is classified as a **mtaji turn** (or this is the opening action that would classify it as mtaji).

Only opponent **front-row** pits can be captured. Back-row seeds are always safe.

### 7.2 Capture Execution

1. Remove **all** seeds from the opponent's opposed front-row pit.
2. Leave the player's own seeds in the capturing pit **untouched** (they are not picked up).
3. Sow the captured seeds starting from a **kichwa**, following the directional rules below.

### 7.3 Kichwa Selection and Direction

**When the capture is the first capture of the turn (opening capture):**

- Capture in **F1 or F2** (left kimbi zone) → sow from **left kichwa (F1)** → **clockwise**.
- Capture in **F7 or F8** (right kimbi zone) → sow from **right kichwa (F8)** → **anticlockwise**.
- Capture in **F3, F4, F5, or F6** (central pits) → player **chooses** left or right kichwa (and thereby clockwise or anticlockwise).

**When the capture is a subsequent capture during relay sowing:**

- Capture in a **kimbi** pit → sow from the **nearest kichwa** (this may reverse the current direction).
- Capture in a **non-kimbi** pit → **preserve the current sowing direction**. Clockwise continues from left kichwa; anticlockwise continues from right kichwa.

Kimbi captures are the **only** mechanism that can change direction mid-turn.

## 8. Sowing and Relay (Kuendelea)

### 8.1 Basic Sowing

Pick up all seeds from the origin pit (setting it to 0). Drop them one per pit sequentially in the chosen direction around the player's 16-pit loop.

### 8.2 Terminal Pit Evaluation

After the last seed is dropped in pit D, evaluate in this strict priority order:

1. **Front-row empty check:** If either player's front row is now empty → game ends immediately.
2. **Capture check (mtaji turns only):** If D is on the player's front row, D is non-empty, and the opposed opponent pit is non-empty → execute capture (§7.2).
3. **Nyumba stop:** If D is the player's owned functional nyumba → apply nyumba rules (§9).
4. **Kutakatia stop:** If D is a kutakatia-ed pit → move ends immediately (§10).
5. **Relay (kuendelea):** If D is non-empty → pick up all seeds from D and continue sowing in the same direction.
6. **Empty pit:** If D is empty → move ends.

### 8.3 The 16-Seed Rule

If a sowing originates from a pit containing **16 or more seeds**, the turn is **forced to takata** regardless of where the last seed lands. No captures may occur. During this first lap of sowing, the origin pit is skipped (seeds are not dropped back into it), so the origin pit remains at 0 after distribution. This rule applies only to the **first sowing of a turn** in the mtaji phase (it cannot occur in kunamua since kunamua turns always start with a single seed from store).

## 9. Nyumba (House) Rules

### 9.1 Nyumba State

The nyumba has three possible states:

| State | Condition | Special rules active? |
|---|---|---|
| **Functional** | Still owned AND contains ≥6 seeds | Yes |
| **Dormant** | Still owned but contains <6 seeds (only via taxation) | No, but may become functional again if refilled to ≥6 |
| **Destroyed** | Has been emptied by sowing its contents, or captured by opponent | No, permanently. Can never regain special status |

Ownership is lost permanently the first time the nyumba's contents are sown out (whether by the player's relay, safari, or opponent capture). Taxation does **not** destroy the nyumba.

### 9.2 Stopping Rules (Functional Nyumba Only)

When sowing ends in a **functional** nyumba (≥6 seeds, still owned):

- **Takata turn:** The move **ends immediately**. No relay sowing from the nyumba.
- **Mtaji turn, no capture available at nyumba:** The player **may choose** to stop (preserving the nyumba) or to continue sowing (safari), which **destroys** the nyumba permanently.
- **Mtaji turn, capture available at nyumba:** The capture executes normally; this destroys the nyumba.

### 9.3 Mtaji Phase Override

In the **mtaji phase**, if sowing ends in the nyumba during a mtaji turn and no capture is available, the player is **forced to safari** (continue sowing), destroying the nyumba. The choice to stop is only available during the **kunamua phase**.

### 9.4 Taxation (Kunamua Takata Only)

During kunamua, if a player must play takata and the nyumba is the **only occupied pit** in their front row:

1. Place the store seed into the nyumba.
2. Remove exactly **2 seeds** from the nyumba.
3. Sow those 2 seeds in a direction of the player's choice (left or right from the nyumba).
4. The nyumba retains its remaining seeds and is **not destroyed**.
5. If this reduces the nyumba below 6 seeds, it becomes **dormant** (not destroyed).

### 9.5 Takata Restriction on Functional Nyumba

During kunamua takata, a player **may not** choose the nyumba as the starting pit unless it is the only occupied front-row pit (triggering taxation).

## 10. Kutakatia / Takasia (Blocking)

This rule applies **only in the mtaji phase**.

### 10.1 Trigger Conditions

After a player completes a **takata** move, if **all three** of the following are true:

1. The opponent's only possible moves are also takata (no capture openings exist for the opponent).
2. Exactly **one** of the opponent's front-row pits is under threat of capture (i.e., the player who just moved has exactly one legal capture available to them).
3. None of the current player's own pits are threatened by the opponent.

Then that single threatened opponent pit becomes **kutakatia-ed** (blocked).

### 10.2 Effect of Kutakatia

- The opponent **cannot** start a turn from the kutakatia-ed pit.
- If the opponent's relay sowing ends in the kutakatia-ed pit, the move **ends immediately** (no relay from it).

### 10.3 Kutakatia Exceptions

A pit **cannot** be kutakatia-ed if it is:

- The opponent's **functional nyumba** (still owned, ≥6 seeds).
- The **only occupied** pit in the opponent's front row.
- The **only pit with ≥2 seeds** in the opponent's front row.

### 10.4 Capture Obligation After Kutakatia

On the turn following the kutakatia, the player who set the block **must** execute the capture of the kutakatia-ed pit if they have a legal capture move, even if another capture would be strategically preferable.

## 11. Kunamua Phase — Turn Procedure

### 11.1 Capture Opening (Mtaji Turn)

If any front-row pit containing ≥1 seed has a non-empty opposed opponent pit, the player **must** place the store seed into one such pit and execute a capture:

1. Decrement store by 1; increment chosen pit by 1.
2. Capture all seeds from the opposed opponent front-row pit.
3. Sow captured seeds from a kichwa per §7.3 (opening capture rules apply since this is the first capture).
4. Continue relay sowing per §8.2.

### 11.2 Non-Capture Opening (Takata Turn)

If no capture opening exists:

1. Select a non-empty front-row pit subject to these constraints:
   - **Not** a functional nyumba, unless it is the only occupied front-row pit (→ taxation per §9.4).
   - If the nyumba is destroyed: prefer pits with ≥2 seeds. Singletons are only permitted if all occupied front-row pits are singletons.
2. Decrement store by 1; increment chosen pit by 1.
3. Pick up all seeds from the pit and sow in a chosen direction.
4. Relay sow per §8.2 (no captures will occur during the entire turn).

### 11.3 Front-Row Kichwa Constraint

If the only occupied front-row pit is a kichwa, takata sowing must be directed **toward the center of the front row** (not toward the back row), to avoid emptying the front row.

## 12. Mtaji Phase — Turn Procedure

### 12.1 Capture Opening (Mtaji Turn)

A capture opening requires a pit (front or back row) with ≥2 seeds whose sowing trajectory ends in a front-row pit that is non-empty and opposed by a non-empty opponent pit.

1. The pit must contain **<16 seeds** (the 16-seed rule forces takata).
2. Select such a pit; sow its contents in the direction that produces the capture.
3. Execute capture per §7.2; sow captured seeds from kichwa per §7.3. For subsequent captures during relay, the relay continuity rules apply.
4. Continue relay sowing per §8.2.

### 12.2 Non-Capture Opening (Takata Turn)

If no capture opening exists:

1. Select a pit from the **front row** with ≥2 seeds.
2. If no front-row pit has ≥2 seeds, select from the **back row** (must have ≥2 seeds).
3. If no pit anywhere has ≥2 seeds, the player loses.
4. Sow in a chosen direction; relay per §8.2 (no captures this turn).

### 12.3 Front-Row Kichwa Constraint (Mtaji)

Same as §11.3: if the only occupied front-row pit is a kichwa, takata must be directed toward the front-row center to avoid emptying the front row.

## 13. Infinite Move Resolution

If a takata move enters a non-terminating cycle (the board state during a turn repeats identically), the move is illegal. If no alternative finite move exists for the player, that player loses.

For practical play: a cycle may be declared after the board state repeats within a single turn, or after 12 complete laps, or after 3 minutes of continuous sowing (conventions vary; choose one for implementation).

## 14. Notation System

### 14.1 Pit Notation

- **A1–A8:** Moving player's front row (left to right from their perspective). A1 = left kichwa, A5 = nyumba, A8 = right kichwa.
- **B1–B8:** Moving player's back row.
- **a1–a8:** Opponent's front row.
- **b1–b8:** Opponent's back row.

### 14.2 Move Notation

- **Direction:** `<` = clockwise (leftward along front row); `>` = anticlockwise (rightward along front row).
- **Takata:** Append `*` (e.g., `A3>*`).
- **Safari (house play):** Append `+` (e.g., `A5>+`).
- **Kutakatia:** Append `**`.

In kunamua, the row indicator may be omitted (front row is always used). If the capturing pit is a kichwa or kimbi, the direction indicator may be omitted (it is forced).

### 14.3 Game Transcript Format

Each line: move number, colon, South's move, space, North's move, semicolon, optional comments. Example: `1: A5> A4<* ; South captures from nyumba, North takata`

## 15. Summary of Mandatory Constraints

1. **Capture is mandatory** when any legal capture opening exists.
2. **Front row takes priority** over back row for takata openings.
3. **Singletons (pits with 1 seed) cannot be chosen** to start a sowing in the mtaji phase, or in kunamua takata when the nyumba is destroyed and non-singleton pits exist.
4. **Direction is locked** once established in a turn, except when a kimbi capture forces a kichwa change.
5. **Takata classification is permanent** for the turn; encountering a capture geometry mid-relay is ignored.
6. **16+ seeds force takata** on the opening sowing of a mtaji phase turn.
7. **Front row may never be emptied** by the player's own move, even temporarily.
8. **Functional nyumba** stops takata relay and offers a halt option during kunamua mtaji relay.
9. **Kutakatia** locks one opponent pit after specific takata conditions in the mtaji phase.
10. **Infinite moves are illegal**; a player with no finite legal move loses.
