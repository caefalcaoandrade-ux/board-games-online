# Abalone — Definitive Two-Player Ruleset (Belgian Daisy)

## 1. Board

The board is a regular hexagon of 61 cells. Rows are numbered R1–R9 top to bottom with the following lengths:

| Row | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 |
|-----|----|----|----|----|----|----|----|----|-----|
| Cells | 5 | 6 | 7 | 8 | 9 | 8 | 7 | 6 | 5 |

Within each row, cells are numbered C1, C2, … left to right. Two cells are adjacent if and only if they share an edge. The hexagonal geometry yields exactly 6 movement directions per cell (along 3 axes).

## 2. Pieces and Objective

Each player controls 14 marbles (Black and White). Black moves first. The objective is to eject exactly 6 of the opponent's marbles off the board. The game ends immediately upon the sixth ejection.

## 3. Initial Position (Belgian Daisy)

```
R1:  W  W  .  B  B
R2:  W  W  W  B  B  B
R3:  .  W  W  .  B  B  .
R4:  .  .  .  .  .  .  .  .
R5:  .  .  .  .  .  .  .  .  .
R6:  .  .  .  .  .  .  .  .
R7:  .  B  B  .  W  W  .
R8:  B  B  B  W  W  W
R9:  B  B  .  W  W
```

Coordinate listing:

**Black:** R1C4, R1C5, R2C4, R2C5, R2C6, R3C5, R3C6, R7C2, R7C3, R8C1, R8C2, R8C3, R9C1, R9C2.

**White:** R1C1, R1C2, R2C1, R2C2, R2C3, R3C2, R3C3, R7C5, R7C6, R8C4, R8C5, R8C6, R9C4, R9C5.

## 4. Turn Structure

Players alternate turns, Black first. Each turn consists of exactly one action: a non-pushing move or a push.

## 5. Moving Group

A player may only act with their own marbles. A valid moving group is:

- Exactly 1, 2, or 3 marbles.
- All of the same color.
- If 2 or 3 marbles: they must be contiguous and collinear (lying in a single straight line along one board axis).

No group of 4 or more marbles may ever be moved.

## 6. Non-Pushing Moves

Every marble in a non-pushing move moves exactly one cell. All destination cells must be on the board and empty.

### 6.1 Single-Marble Move

One marble moves to any one of its 6 adjacent cells, provided that cell is on the board and empty.

### 6.2 In-Line Move

The direction of movement is along the axis of the group's own line. The group of 2 or 3 collinear marbles advances one cell forward or backward along its line. Only the leading destination cell (the one cell beyond the front marble in the direction of travel) must be on the board and empty.

### 6.3 Side-Step Move

The direction of movement is not along the group's own line. Each marble in the group of 2 or 3 collinear marbles moves one cell in the same lateral direction. Every individual destination cell must be on the board and empty. A side-step never pushes.

## 7. Pushing Moves (Sumito)

A push is an in-line move in which a player's group displaces one or more opponent marbles. A push is legal if and only if all of the following conditions are met:

1. The moving group contains 2 or 3 friendly marbles, collinear.
2. The movement direction is along the group's own line (in-line only).
3. Immediately adjacent to the front marble of the moving group, in the direction of movement, there is a contiguous line of 1 or 2 enemy marbles on the same axis, with no gap.
4. The moving group is strictly larger than the enemy group (legal configurations: 2v1, 3v1, 3v2).
5. The cell immediately beyond the last enemy marble (in the push direction) is either: an empty on-board cell, or off the board.

If the cell beyond the enemy group is occupied by any marble (friendly or enemy), the push is illegal.

## 8. Effect of a Push

A legal push advances every marble in the confronted line (both friendly and enemy) by exactly one cell in the push direction.

- If the cell beyond the last enemy marble is an empty on-board cell: all enemy marbles shift one cell in the push direction, and all friendly marbles also advance one cell.
- If the cell beyond the last enemy marble is off the board: the foremost enemy marble is ejected (permanently removed from play), and all remaining marbles in the line shift one cell in the push direction.

## 9. Illegal Push Situations (Exhaustive)

The following are always illegal:

- Pushing with a single marble (1v1 or 1v0).
- Equal-sized confrontations: 2v2, 3v3.
- Any confrontation against 3 or more enemy marbles (an enemy line of 3 can never be pushed).
- Using 4 or more friendly marbles as a group.
- Pushing via a side-step move.
- Pushing when the groups are not directly adjacent (any gap between them).
- Pushing when the cell beyond the last enemy marble is occupied by any marble.

## 10. Ejection and Victory

A marble is ejected when a legal push sends it off the board edge. Ejected marbles are permanently out of play. The game ends immediately when a player has ejected 6 opposing marbles; that player wins.

## 11. Complete Legal Turn Summary

A legal turn is exactly one of the following four actions:

1. **Single-marble move:** Move 1 friendly marble one cell to an adjacent empty on-board cell.
2. **In-line move (no push):** Move 2 or 3 collinear friendly marbles one cell along their line into an empty on-board destination.
3. **Side-step move:** Move 2 or 3 collinear friendly marbles one cell in a direction not along their line; each marble's destination must be an empty on-board cell. Never pushes.
4. **In-line push (Sumito):** Move 2 or 3 collinear friendly marbles one cell along their line, displacing a strictly smaller adjacent enemy group (2v1, 3v1, or 3v2), with the cell beyond the enemy group either empty or off-board.
