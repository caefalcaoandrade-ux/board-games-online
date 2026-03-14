"""MCTS bot for Board Games Online.

Uses Monte Carlo Tree Search with UCB1 selection and MAST-biased
playouts.  Works with any game implementing the AbstractBoardGame
interface — never imports or references any specific game.

Usage::

    from client.bot import MCTSBot

    bot = MCTSBot("hard")
    move = bot.choose_move(logic, state, my_player)

Difficulty levels:
    easy   — responds in under 1 second (near-random play)
    medium — responds in 1-2 seconds
    hard   — responds in up to 4 seconds
"""

import math
import random
import time


# ── MCTS Node ────────────────────────────────────────────────────────────────


class _Node:
    """A node in the MCTS search tree."""
    __slots__ = ("state", "move", "parent", "children",
                 "visits", "wins", "untried")

    def __init__(self, state, move=None, parent=None):
        self.state = state
        self.move = move
        self.parent = parent
        self.children = []
        self.visits = 0
        self.wins = 0.0
        self.untried = None       # lazy-loaded list of unexpanded moves


def _ucb1(node, c):
    """Upper Confidence Bound for tree node selection."""
    if node.visits == 0:
        return float("inf")
    return (node.wins / node.visits
            + c * math.sqrt(math.log(node.parent.visits) / node.visits))


# Playout depth cap — keeps each simulation fast so more iterations
# fit in the time budget.  Most game-deciding patterns emerge within
# 30 moves; hitting the cap returns a draw (0.5).
_PLAYOUT_DEPTH = 30


# ── Bot ───────────────────────────────────────────────────────────────────────


class MCTSBot:
    """Game-agnostic MCTS bot with three difficulty levels.

    The levels differ in exploration constant, loss-prevention depth,
    MAST usage, and playout heuristic depth — creating a genuine skill
    gap even at low iteration counts.

    ============  ====  ======  =========  ==========  ====
    Level         C     Loss    Heuristic  MAST        Time
                        check   depth      playouts
    ============  ====  ======  =========  ==========  ====
    easy          2.0   off     0          off         0.8s
    medium        0.7   15      1          on          1.5s
    hard          0.5   20      2          on          3.5s
    ============  ====  ======  =========  ==========  ====
    """

    PRESETS = {
        "easy":   {"time": 0.8,  "c": 2.0,  "hdepth": 0,
                   "loss_check": 0,  "use_mast": False},
        "medium": {"time": 1.5,  "c": 0.7,  "hdepth": 1,
                   "loss_check": 15, "use_mast": True},
        "hard":   {"time": 3.5,  "c": 0.5,  "hdepth": 2,
                   "loss_check": 20, "use_mast": True},
    }

    def __init__(self, difficulty="medium", max_iterations=None):
        p = self.PRESETS.get(difficulty, self.PRESETS["medium"])
        self.time_limit = p["time"]
        self.c = p["c"]
        self.hdepth = p["hdepth"]
        self.loss_check = p["loss_check"]
        self.use_mast = p["use_mast"]
        self.max_iterations = max_iterations
        self.mast = {}  # repr(move) -> [wins, total]

    # ── Public API ────────────────────────────────────────────────────

    def choose_move(self, logic, state, player):
        """Choose the best move for *player* in *state*.

        Returns the chosen move, or None if no legal moves exist.
        """
        moves = logic._get_legal_moves(state, player)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # ── Immediate win (always — this is cheap) ────────────────────
        for m in moves:
            ns = logic._apply_move(state, player, m)
            st = logic._get_game_status(ns)
            if st["is_over"] and st["winner"] == player:
                return m

        # ── Loss prevention (skipped at Easy) ─────────────────────────
        if self.loss_check and len(moves) <= self.loss_check:
            safe = []
            for m in moves:
                ns = logic._apply_move(state, player, m)
                st = logic._get_game_status(ns)
                if st["is_over"]:
                    continue
                opp = logic._get_current_player(ns)
                opp_mvs = logic._get_legal_moves(ns, opp)
                danger = False
                for om in opp_mvs:
                    os = logic._apply_move(ns, opp, om)
                    ost = logic._get_game_status(os)
                    if ost["is_over"] and ost["winner"] == opp:
                        danger = True
                        break
                if not danger:
                    safe.append(m)
            if safe and len(safe) < len(moves):
                moves = safe

        # ── MCTS ──────────────────────────────────────────────────────
        root = _Node(state)
        root.untried = list(moves)

        if self.max_iterations:
            for _ in range(self.max_iterations):
                self._iterate(root, logic, player)
        else:
            deadline = time.monotonic() + self.time_limit
            while time.monotonic() < deadline:
                self._iterate(root, logic, player)

        if not root.children:
            return random.choice(moves)
        return max(root.children, key=lambda n: n.visits).move

    # ── MCTS iteration ────────────────────────────────────────────────

    def _iterate(self, root, logic, player):
        node = root
        sim = root.state

        # Selection
        while (node.untried is not None
               and not node.untried
               and node.children):
            node = max(node.children, key=lambda n: _ucb1(n, self.c))
            sim = node.state

        # Expansion
        if node.untried is None:
            st = logic._get_game_status(sim)
            if st["is_over"]:
                node.untried = []
            else:
                p = logic._get_current_player(sim)
                node.untried = list(logic._get_legal_moves(sim, p))

        if node.untried:
            mv = node.untried.pop(random.randrange(len(node.untried)))
            p = logic._get_current_player(sim)
            ns = logic._apply_move(sim, p, mv)
            child = _Node(ns, mv, node)
            node.children.append(child)
            node = child
            sim = ns

        # Simulation
        result = self._playout(sim, logic, player)

        # Backpropagation
        n = node
        while n is not None:
            n.visits += 1
            if result == player:
                n.wins += 1.0
            elif result is None:
                n.wins += 0.5
            n = n.parent

    # ── Playout ───────────────────────────────────────────────────────

    def _playout(self, state, logic, bot_player):
        """Simulate up to _PLAYOUT_DEPTH moves and return the winner.

        Uses immediate-win detection for the first ``hdepth`` moves,
        then MAST ε-greedy selection (or pure random for Easy).
        """
        depth = 0
        played = []

        while depth < _PLAYOUT_DEPTH:
            st = logic._get_game_status(state)
            if st["is_over"]:
                winner = st["winner"]
                if self.use_mast:
                    self._mast_update(played, winner)
                return winner

            p = logic._get_current_player(state)
            mvs = logic._get_legal_moves(state, p)
            if not mvs:
                if self.use_mast:
                    self._mast_update(played, None)
                return None

            mv = None

            # Win-check in first hdepth playout moves (cheap heuristic)
            if depth < self.hdepth:
                for m in mvs:
                    ns = logic._apply_move(state, p, m)
                    s = logic._get_game_status(ns)
                    if s["is_over"] and s["winner"] == p:
                        mv = m
                        break

            # Move selection: MAST ε-greedy or pure random
            if mv is None:
                if self.use_mast and self.mast:
                    mv = self._mast_pick(mvs)
                else:
                    mv = random.choice(mvs)

            if self.use_mast:
                played.append((repr(mv), p))
            state = logic._apply_move(state, p, mv)
            depth += 1

        # Depth cap hit — indeterminate (scored as draw)
        if self.use_mast:
            self._mast_update(played, None)
        return None

    # ── MAST (Move Average Sampling Technique) ────────────────────────

    def _mast_pick(self, moves):
        """ε-greedy MAST: 90% pick highest win-rate, 10% random."""
        if random.random() < 0.1:
            return random.choice(moves)
        best = None
        best_rate = -1.0
        for m in moves:
            entry = self.mast.get(repr(m))
            if entry and entry[1] > 0:
                rate = entry[0] / entry[1]
                if rate > best_rate:
                    best_rate = rate
                    best = m
        return best if best is not None else random.choice(moves)

    def _mast_update(self, played, winner):
        """Update MAST statistics for all moves in a completed playout."""
        for mk, p in played:
            if mk not in self.mast:
                self.mast[mk] = [0.0, 0]
            self.mast[mk][1] += 1
            if winner == p:
                self.mast[mk][0] += 1.0
