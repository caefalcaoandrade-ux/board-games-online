"""MCTS bot for Board Games Online.

Uses Monte Carlo Tree Search with GRAVE (Generalized Rapid Action Value
Estimation) for tree selection, mobility-based playout evaluation,
MCTS-Solver backpropagation, and tree reuse between moves.

Fully game-agnostic — works through the AbstractBoardGame interface only.

Usage::

    from client.bot import MCTSBot

    bot = MCTSBot("strong")
    move = bot.choose_move(logic, state, my_player)

Difficulty levels:
    weak   — pure random (instant), no search at all
    strong — 8 s, GRAVE selection, mobility eval at cutoff,
             MCTS-Solver, 3-ply loss prevention, tree reuse
"""

import math
import random
import time


# ── Constants ────────────────────────────────────────────────────────────────

_PLAYOUT_DEPTH = 15       # shorter playouts + evaluation = more iterations
_GRAVE_K = 500            # GRAVE bias blending constant
_GRAVE_REF = 50           # min visits before node's own AMAF table is used
_SIGMOID_TEMP = 8.0       # sigmoid temperature for mobility evaluation
_INF = float("inf")


# ── MCTS Node ────────────────────────────────────────────────────────────────


class _Node:
    """A node in the MCTS search tree with AMAF statistics."""
    __slots__ = ("state", "player", "move", "parent", "children",
                 "visits", "value", "untried",
                 "amaf_wins", "amaf_visits",
                 "proven")

    def __init__(self, state, player, move=None, parent=None):
        self.state = state
        self.player = player        # whose turn it is AT this node
        self.move = move             # move that led here (from parent)
        self.parent = parent
        self.children = []
        self.visits = 0
        self.value = 0.0             # cumulative value from bot's perspective
        self.untried = None          # lazy-loaded
        self.amaf_wins = {}          # repr(move) -> float
        self.amaf_visits = {}        # repr(move) -> int
        self.proven = None           # None=unknown, True=proven win, False=proven loss


# ── Selection helpers ────────────────────────────────────────────────────────


def _ucb1_score(child, c, parent_log):
    """Standard UCB1."""
    if child.visits == 0:
        return _INF
    return (child.value / child.visits
            + c * math.sqrt(parent_log / child.visits))


def _grave_score(child, c, parent_log, amaf_w, amaf_v):
    """GRAVE score blending standard value with AMAF."""
    mk = repr(child.move)
    if child.visits == 0:
        av = amaf_v.get(mk, 0)
        if av > 0:
            return amaf_w.get(mk, 0.0) / av + c * 10
        return _INF

    exploit = child.value / child.visits
    explore = c * math.sqrt(parent_log / child.visits)
    ucb = exploit + explore

    av = amaf_v.get(mk, 0)
    if av == 0:
        return ucb

    amaf_val = amaf_w.get(mk, 0.0) / av
    beta = math.sqrt(_GRAVE_K / (3.0 * child.visits + _GRAVE_K))
    return (1.0 - beta) * ucb + beta * amaf_val


def _find_amaf_ancestor(node):
    """Walk up to find the nearest ancestor with >= _GRAVE_REF visits."""
    n = node
    while n is not None:
        if n.visits >= _GRAVE_REF:
            return n.amaf_wins, n.amaf_visits
        n = n.parent
    return {}, {}


# ── Bot ──────────────────────────────────────────────────────────────────────


class MCTSBot:
    """Game-agnostic MCTS bot with two difficulty levels.

    =========  ====  =======  ========  ==========  =========  ====
    Level      C     Loss     Playout   Evaluation  Solver     Time
                     check    policy    at cutoff
    =========  ====  =======  ========  ==========  =========  ====
    weak       —     off      —         —           off        0 s
    strong     0.2   3-ply    random    mobility    on         8 s
    =========  ====  =======  ========  ==========  =========  ====

    Weak is pure random — no MCTS at all.  Strong uses full MCTS with
    GRAVE selection, mobility evaluation at playout cutoff, MCTS-Solver,
    3-ply loss prevention, tree reuse, and progressive move ordering.
    Random playouts (not greedy) maximize iteration throughput; the
    mobility evaluation at the leaf provides all the strategic signal.
    """

    PRESETS = {
        "weak": {
            "time": 0, "c": 1.4, "random_only": True,
            "use_grave": False, "use_eval": False,
            "use_solver": False, "loss_ply": 0,
        },
        "strong": {
            "time": 8.0, "c": 0.2, "random_only": False,
            "use_grave": True, "use_eval": True,
            "use_solver": True, "loss_ply": 3,
        },
    }

    # Legacy aliases
    PRESETS["easy"] = PRESETS["normal"] = PRESETS["weak"]
    PRESETS["medium"] = PRESETS["hard"] = PRESETS["strong"]

    def __init__(self, difficulty="strong", max_iterations=None):
        p = self.PRESETS.get(difficulty, self.PRESETS["strong"])
        self.time_limit = p["time"]
        self.c = p["c"]
        self.random_only = p["random_only"]
        self.use_grave = p["use_grave"]
        self.use_eval = p["use_eval"]
        self.use_solver = p["use_solver"]
        self.loss_ply = p["loss_ply"]
        self.max_iterations = max_iterations
        self._reuse_root = None

    # ── Public API ────────────────────────────────────────────────────

    def choose_move(self, logic, state, player):
        """Choose the best move for *player* in *state*."""
        moves = logic._get_legal_moves(state, player)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # ── Weak: pure random ────────────────────────────────────────
        if self.random_only and not self.max_iterations:
            return random.choice(moves)

        # ── Immediate win ────────────────────────────────────────────
        for m in moves:
            ns = logic._apply_move(state, player, m)
            st = logic._get_game_status(ns)
            if st["is_over"] and st["winner"] == player:
                self._reuse_root = None
                return m

        # ── Loss prevention ──────────────────────────────────────────
        if self.loss_ply >= 1 and len(moves) <= 20:
            moves = self._loss_filter(logic, state, player, moves)

        # ── Tree reuse ───────────────────────────────────────────────
        root = self._try_reuse(state, player, moves)
        if root is None:
            root = _Node(state, player)
            root.untried = list(moves)

        # ── Progressive move ordering on first expansion ─────────────
        if self.use_eval and root.untried and not root.children:
            root.untried = self._order_moves(logic, state, player,
                                             root.untried)

        # ── MCTS main loop ───────────────────────────────────────────
        if self.max_iterations:
            for _ in range(self.max_iterations):
                self._iterate(root, logic, player)
        else:
            deadline = time.monotonic() + self.time_limit
            while time.monotonic() < deadline:
                self._iterate(root, logic, player)

        if not root.children:
            self._reuse_root = None
            return random.choice(moves)

        best = max(root.children, key=lambda n: n.visits)
        self._reuse_root = best
        return best.move

    # ── Loss prevention (1-ply and 3-ply) ────────────────────────────

    def _loss_filter(self, logic, state, player, moves):
        """Filter out moves that lead to immediate or forced opponent wins."""
        opp = 3 - player

        # 1-ply: remove moves where opponent wins next turn
        safe = []
        for m in moves:
            ns = logic._apply_move(state, player, m)
            st = logic._get_game_status(ns)
            if st["is_over"]:
                if st["winner"] == player:
                    return [m]
                continue
            np = logic._get_current_player(ns)
            opp_mvs = logic._get_legal_moves(ns, np)
            danger = False
            for om in opp_mvs:
                os_ = logic._apply_move(ns, np, om)
                ost = logic._get_game_status(os_)
                if ost["is_over"] and ost["winner"] == opp:
                    danger = True
                    break
            if not danger:
                safe.append(m)
        if safe and len(safe) < len(moves):
            moves = safe

        # 3-ply: check if opponent has a FORCED win
        if self.loss_ply >= 3 and len(moves) <= 15:
            safe3 = []
            for m in moves:
                ns = logic._apply_move(state, player, m)
                st = logic._get_game_status(ns)
                if st["is_over"]:
                    continue
                np = logic._get_current_player(ns)
                opp_mvs = logic._get_legal_moves(ns, np)
                forced_loss = False
                for om in opp_mvs:
                    os_ = logic._apply_move(ns, np, om)
                    ost = logic._get_game_status(os_)
                    if ost["is_over"] and ost["winner"] == opp:
                        continue
                    if ost["is_over"]:
                        continue
                    rp = logic._get_current_player(os_)
                    our_replies = logic._get_legal_moves(os_, rp)
                    if not our_replies:
                        forced_loss = True
                        break
                    all_lose = True
                    for r in our_replies:
                        rs = logic._apply_move(os_, rp, r)
                        rst = logic._get_game_status(rs)
                        if not (rst["is_over"] and rst["winner"] == opp):
                            all_lose = False
                            break
                    if all_lose:
                        forced_loss = True
                        break
                if not forced_loss:
                    safe3.append(m)
            if safe3 and len(safe3) < len(moves):
                moves = safe3

        return moves

    # ── Tree reuse ───────────────────────────────────────────────────

    def _try_reuse(self, state, player, moves):
        """Try to find a matching child in the saved tree root."""
        if self._reuse_root is None:
            return None
        for child in self._reuse_root.children:
            if child.state == state:
                child.parent = None
                self._reuse_root = None
                return child
        self._reuse_root = None
        return None

    # ── Progressive move ordering ────────────────────────────────────

    def _order_moves(self, logic, state, player, moves):
        """Order moves by opponent mobility (most restrictive first)."""
        if len(moves) <= 3:
            return moves
        sample_size = min(12, len(moves))
        sample = random.sample(moves, sample_size)
        rest = [m for m in moves if m not in sample]

        scored = []
        for m in sample:
            ns = logic._apply_move(state, player, m)
            st = logic._get_game_status(ns)
            if st["is_over"]:
                if st["winner"] == player:
                    return [m] + rest
                scored.append((m, 9999))
                continue
            np = logic._get_current_player(ns)
            opp_count = len(logic._get_legal_moves(ns, np))
            scored.append((m, opp_count))

        scored.sort(key=lambda x: x[1])
        ordered = [m for m, _ in scored]
        random.shuffle(rest)
        return ordered + rest

    # ── MCTS iteration ───────────────────────────────────────────────

    def _iterate(self, root, logic, bot_player):
        node = root
        sim = root.state
        path = [node]
        sim_moves = []

        # ── Selection ────────────────────────────────────────────────
        while (node.untried is not None
               and not node.untried
               and node.children):
            viable = [ch for ch in node.children if ch.proven is not True
                      ] if self.use_solver else node.children
            if not viable:
                viable = node.children

            parent_log = math.log(node.visits + 1)

            if self.use_grave:
                aw, av = (node.amaf_wins, node.amaf_visits) \
                    if node.visits >= _GRAVE_REF \
                    else _find_amaf_ancestor(node)
                node = max(viable,
                           key=lambda n: _grave_score(n, self.c, parent_log,
                                                      aw, av))
            else:
                node = max(viable,
                           key=lambda n: _ucb1_score(n, self.c, parent_log))

            if node.move is not None:
                sim_moves.append((repr(node.move), node.parent.player))
            path.append(node)
            sim = node.state

        # ── Expansion ────────────────────────────────────────────────
        if node.untried is None:
            st = logic._get_game_status(sim)
            if st["is_over"]:
                node.untried = []
                if self.use_solver:
                    if st["winner"] == bot_player:
                        node.proven = True
                    elif st["winner"] is not None:
                        node.proven = False
            else:
                mvs = logic._get_legal_moves(sim, node.player)
                node.untried = list(mvs)

        if node.untried:
            mv = node.untried.pop(random.randrange(len(node.untried)))
            ns = logic._apply_move(sim, node.player, mv)
            nst = logic._get_game_status(ns)
            next_player = node.player
            if not nst["is_over"]:
                next_player = logic._get_current_player(ns)

            child = _Node(ns, next_player, mv, node)
            node.children.append(child)
            sim_moves.append((repr(mv), node.player))
            path.append(child)
            node = child
            sim = ns

            if nst["is_over"] and self.use_solver:
                if nst["winner"] == bot_player:
                    child.proven = True
                elif nst["winner"] is not None:
                    child.proven = False

        # ── Simulation ───────────────────────────────────────────────
        if node.proven is True:
            result_val = 1.0
        elif node.proven is False:
            result_val = 0.0
        else:
            result_val = self._playout(sim, logic, bot_player, sim_moves)

        # ── Backpropagation ──────────────────────────────────────────
        for n in path:
            n.visits += 1
            n.value += result_val

        # ── AMAF update (GRAVE) ──────────────────────────────────────
        if self.use_grave:
            for i, n in enumerate(path):
                for j in range(i + 1, len(sim_moves)):
                    mk, mp = sim_moves[j]
                    if mp == n.player:
                        n.amaf_visits[mk] = n.amaf_visits.get(mk, 0) + 1
                        n.amaf_wins[mk] = n.amaf_wins.get(mk, 0.0) + result_val

        # ── MCTS-Solver propagation ──────────────────────────────────
        if self.use_solver:
            self._solver_backup(path)

    def _solver_backup(self, path):
        """Propagate proven results up the tree via minimax logic."""
        for i in range(len(path) - 1, -1, -1):
            node = path[i]
            if node.proven is not None:
                continue
            if not node.children or node.untried is None or node.untried:
                continue
            all_proven = True
            any_win = False
            for ch in node.children:
                if ch.proven is None:
                    all_proven = False
                    break
                if ch.proven is True:
                    any_win = True
            if not all_proven:
                continue
            if any_win:
                node.proven = True
            else:
                node.proven = False

    # ── Playout ──────────────────────────────────────────────────────

    def _playout(self, state, logic, bot_player, sim_moves):
        """Simulate random moves and return a value in [0, 1]."""
        for depth in range(_PLAYOUT_DEPTH):
            st = logic._get_game_status(state)
            if st["is_over"]:
                if st["winner"] == bot_player:
                    return 1.0
                elif st["winner"] is None:
                    return 0.5
                else:
                    return 0.0

            p = logic._get_current_player(state)
            mvs = logic._get_legal_moves(state, p)
            if not mvs:
                return 0.5

            mv = None

            # Immediate win check (first 2 playout moves — cheap)
            if depth < 2:
                for m in mvs:
                    ns = logic._apply_move(state, p, m)
                    s = logic._get_game_status(ns)
                    if s["is_over"] and s["winner"] == p:
                        mv = m
                        break

            if mv is None:
                mv = random.choice(mvs)

            sim_moves.append((repr(mv), p))
            state = logic._apply_move(state, p, mv)

        # ── Cutoff evaluation ────────────────────────────────────────
        if not self.use_eval:
            return 0.5

        return self._evaluate(state, logic, bot_player)

    # ── Position evaluation ──────────────────────────────────────────

    def _evaluate(self, state, logic, bot_player):
        """Game-agnostic evaluation via mobility ratio.

        Returns a value in [0, 1] where 1 = winning for bot_player.
        """
        st = logic._get_game_status(state)
        if st["is_over"]:
            if st["winner"] == bot_player:
                return 1.0
            elif st["winner"] is None:
                return 0.5
            else:
                return 0.0

        current = logic._get_current_player(state)
        opp = 3 - current
        my_moves = len(logic._get_legal_moves(state, current))
        opp_moves = len(logic._get_legal_moves(state, opp))

        total = my_moves + opp_moves
        if total == 0:
            return 0.5

        raw = (my_moves - opp_moves) / max(total, 1)

        if current != bot_player:
            raw = -raw

        return 1.0 / (1.0 + math.exp(-raw * _SIGMOID_TEMP))
