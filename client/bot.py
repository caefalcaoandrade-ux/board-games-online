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
    weak    — 3 s MCTS, selects the WORST move (lowest visit count)
    strong  — 12 s full MCTS, selects the BEST move (highest visit count)
"""

import math
import random
import time


# ── Constants ────────────────────────────────────────────────────────────────

_PLAYOUT_DEPTH = 15       # shorter playouts + evaluation = more iterations
_GRAVE_K = 1e-5           # GRAVE equivalence parameter (Cazenave IJCAI 2015)
_GRAVE_REF = 50           # min visits before node's own AMAF table is used
_SIGMOID_TEMP = 8.0       # sigmoid temperature for mobility evaluation
_PLAYOUT_EPSILON = 0.1    # ε for epsilon-greedy playout (10% random)
_REUSE_DECAY = 0.8        # visit/value decay factor on tree reuse
_FPU_OFFSET = 0.1         # First Play Urgency: unvisited = parent_Q - this
_PBIAS_C = 2.0            # progressive bias constant
_IM_ALPHA = 0.3           # implicit minimax blending weight
_STOP_INTERVAL = 500      # check early-stop condition every N iterations
_SECURE_A = 100           # Secure Child constant for root selection
_MAX_MOVE_TIME = 20.0     # absolute max time for any single move
_EARLY_CHECK = 5          # early termination check every N playout moves
_QUIESCE_DELTA = 0.3      # eval delta threshold for quiescence
_MAST_BLEND = 0.3         # MAST weight in blended playout scoring
_MAST_DECAY = 0.999       # MAST decay factor
_MAST_DECAY_INTERVAL = 100  # apply MAST decay every N simulations
_PW_K = 2.0               # progressive widening coefficient
_PW_ALPHA = 0.45           # progressive widening exponent
_PW_THRESHOLD = 15         # disable widening at or below this BF
_INF = float("inf")


# ── MCTS Node ────────────────────────────────────────────────────────────────


class _Node:
    """A node in the MCTS search tree with AMAF statistics."""
    __slots__ = ("state", "player", "move", "parent", "children",
                 "visits", "value", "untried",
                 "amaf_wins", "amaf_visits",
                 "proven",
                 # Future enhancement placeholders
                 "cached_eval", "implicit_minimax_value",
                 "mast_visits", "mast_wins")

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
        self.cached_eval = None      # cached evaluate_position result
        self.implicit_minimax_value = None  # for implicit minimax backup
        self.mast_visits = None      # MAST move statistics (visits)
        self.mast_wins = None        # MAST move statistics (wins)


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


# ── Tree decay ──────────────────────────────────────────────────────────────


def _decay_tree(node, factor):
    """Multiply visit/value counts by *factor* recursively (for tree reuse)."""
    stack = [node]
    while stack:
        n = stack.pop()
        n.visits = int(n.visits * factor)
        n.value *= factor
        for mk in n.amaf_visits:
            n.amaf_visits[mk] = int(n.amaf_visits[mk] * factor)
        for mk in n.amaf_wins:
            n.amaf_wins[mk] *= factor
        stack.extend(n.children)


# ── Q helpers ────────────────────────────────────────────────────────────────


def _q_combined_of(node):
    """Q_combined value for a visited node (from bot's perspective)."""
    if node.visits == 0:
        return 0.5
    if node.proven is True:
        return 1.0
    if node.proven is False:
        return 0.0
    qm = node.value / node.visits
    vim = node.implicit_minimax_value
    if vim is None:
        vim = qm
    return (1.0 - _IM_ALPHA) * qm + _IM_ALPHA * vim


# ── Bot ──────────────────────────────────────────────────────────────────────


class MCTSBot:
    """Game-agnostic MCTS bot with two difficulty levels.

    =========  ==========  ====  =======  ==========  =========  ======
    Level      Selection   C     Loss     Evaluation  Solver     Time
                                  check    at cutoff
    =========  ==========  ====  =======  ==========  =========  ======
    weak       worst       1.4   off      off         off         3 s
    strong     best        0.2   3-ply    on          on         12 s
    =========  ==========  ====  =======  ==========  =========  ======

    *Weak* runs simple MCTS but deliberately picks the **worst** move
    (lowest visit count among visited children).  It understands the
    game but actively avoids the best line.

    *Strong* runs full MCTS and picks the best move (highest visit count).
    """

    # Move-selection policies
    SELECT_BEST = "best"      # highest visit count (strongest play)
    SELECT_WORST = "worst"    # lowest visit count (deliberately bad)

    PRESETS = {
        "weak": {
            "time": 3.0, "c": 1.4, "select": "worst",
            "use_grave": False, "use_eval": False,
            "use_solver": False, "loss_ply": 0,
        },
        "strong": {
            "time": 12.0, "c": 0.2, "select": "best",
            "use_grave": True, "use_eval": True,
            "use_solver": True, "loss_ply": 3,
        },
    }

    def __init__(self, difficulty="strong", max_iterations=None):
        p = self.PRESETS.get(difficulty, self.PRESETS["strong"])
        self.time_limit = p["time"]
        self.c = p["c"]
        self.select = p["select"]
        self.use_grave = p["use_grave"]
        self.use_eval = p["use_eval"]
        self.use_solver = p["use_solver"]
        self.loss_ply = p["loss_ply"]
        self.max_iterations = max_iterations
        self._reuse_root = None
        self._has_game_eval = False
        self._time_bank = 0.0
        # LGRF tables: player → {key → reply_move}
        self._lgrf1 = {1: {}, 2: {}}
        self._lgrf2 = {1: {}, 2: {}}
        # MAST tables: player → {move_repr → [total_reward, count]}
        self._mast = {1: {}, 2: {}}
        self._sim_count = 0
        # Playout scratch (set by _playout, read by _iterate)
        self._po_moves = []      # [(move, player, move_repr), ...]
        self._po_lgrf_used = []  # [(order, key, player), ...]

    # ── Public API ────────────────────────────────────────────────────

    def choose_move(self, logic, state, player):
        """Choose a move for *player* in *state*."""
        moves = logic._get_legal_moves(state, player)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # ── Decisive: immediate win (Strong only) ─────────────────────
        if self.use_eval:
            for m in moves:
                ns = logic._apply_move(state, player, m)
                st = logic._get_game_status(ns)
                if st["is_over"] and st["winner"] == player:
                    self._reuse_root = None
                    return m

            # ── Decisive: forced move (≤5 legal, only 1 avoids opp win)
            if len(moves) <= 5:
                opp = 3 - player
                safe = []
                for m in moves:
                    ns = logic._apply_move(state, player, m)
                    st = logic._get_game_status(ns)
                    if st["is_over"]:
                        continue  # losing or draw (wins already caught)
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
                if len(safe) == 1:
                    self._reuse_root = None
                    return safe[0]

        # ── Loss prevention ──────────────────────────────────────────
        if self.loss_ply >= 1 and len(moves) <= 20:
            moves = self._loss_filter(logic, state, player, moves)
        if len(moves) == 1:
            self._reuse_root = None
            return moves[0]

        # ── Probe game-specific evaluation ─────────────────────────
        if self.use_eval:
            self._has_game_eval = logic.evaluate_position(state, player) is not None
        else:
            self._has_game_eval = False

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
        elif self.use_eval:
            self._timed_search(root, logic, player)
        else:
            deadline = time.monotonic() + self.time_limit
            while time.monotonic() < deadline:
                self._iterate(root, logic, player)

        if not root.children:
            self._reuse_root = None
            return random.choice(moves)

        # ── Move selection (difficulty-dependent) ─────────────────────
        chosen = self._select_move(root)
        self._reuse_root = chosen
        return chosen.move

    def _select_move(self, root):
        """Pick a child of *root* according to the selection policy."""
        visited = [ch for ch in root.children if ch.visits > 0]
        if not visited:
            return random.choice(root.children)

        if self.select == self.SELECT_WORST:
            return visited[0] if len(visited) == 1 else \
                   min(visited, key=lambda n: n.visits)

        # Secure Child: Q_combined + sqrt(A / (visits+1))
        if self.use_solver:
            return max(visited,
                       key=lambda n: _q_combined_of(n)
                       + math.sqrt(_SECURE_A / (n.visits + 1)))

        # SELECT_BEST fallback (highest visit count)
        return max(visited, key=lambda n: n.visits)

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
                _decay_tree(child, _REUSE_DECAY)
                return child
        self._reuse_root = None
        return None

    # ── Dynamic time management ──────────────────────────────────────

    def _timed_search(self, root, logic, player):
        """MCTS search with STOP early-termination and UNST/BEHIND extensions."""
        base = self.time_limit
        start = time.monotonic()
        iters = 0
        stop_fired = False

        # ── Base phase ─────────────────────────────────────────────
        base_deadline = start + base
        while time.monotonic() < base_deadline:
            self._iterate(root, logic, player)
            iters += 1
            if iters % _STOP_INTERVAL == 0:
                if self._check_stop(root, iters, start, base_deadline):
                    saved = max(0.0, base_deadline - time.monotonic())
                    self._time_bank += saved
                    stop_fired = True
                    break

        if stop_fired:
            return

        # ── Extension decision ─────────────────────────────────────
        ext = 0.0

        # UNST: most-visited ≠ highest Q_combined?
        visited = [ch for ch in root.children if ch.visits > 0]
        if len(visited) >= 2:
            by_visits = max(visited, key=lambda n: n.visits)
            by_q = max(visited, key=_q_combined_of)
            if by_visits.move != by_q.move:
                grant = min(3.6, self._time_bank)
                ext += grant
                self._time_bank -= grant

        # BEHIND: root mean Q < 0.35?
        if root.visits > 0 and root.value / root.visits < 0.35:
            grant = min(6.0, self._time_bank)
            ext += grant
            self._time_bank -= grant

        # Cap total move time at _MAX_MOVE_TIME
        elapsed_so_far = time.monotonic() - start
        ext = min(ext, _MAX_MOVE_TIME - elapsed_so_far)
        ext = max(ext, 0.0)

        # ── Extension phase ────────────────────────────────────────
        if ext > 0:
            ext_deadline = time.monotonic() + ext
            while time.monotonic() < ext_deadline:
                self._iterate(root, logic, player)
                iters += 1
                if iters % _STOP_INTERVAL == 0:
                    if self._check_stop(root, iters, start, ext_deadline):
                        break

    def _check_stop(self, root, iters, start, deadline):
        """Return True if the best move's lead is mathematically safe."""
        if len(root.children) < 2:
            return False
        now = time.monotonic()
        elapsed = now - start
        if elapsed < 0.5:
            return False
        remaining = deadline - now
        if remaining <= 0:
            return True
        ips = iters / elapsed
        remaining_sims = remaining * ips
        # Find top 2 by visits (O(n) scan)
        best_v = second_v = 0
        for ch in root.children:
            v = ch.visits
            if v > best_v:
                second_v = best_v
                best_v = v
            elif v > second_v:
                second_v = v
        return remaining_sims * 0.7 < (best_v - second_v)

    # ── Progressive move ordering ────────────────────────────────────

    def _order_moves(self, logic, state, player, moves):
        """Order moves by game evaluation or opponent mobility."""
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
                scored.append((m, -1.0 if self._has_game_eval else 9999))
                continue
            if self._has_game_eval:
                ev = logic.evaluate_position(ns, player)
                if ev is not None:
                    scored.append((m, ev))
                    continue
            np = logic._get_current_player(ns)
            opp_count = len(logic._get_legal_moves(ns, np))
            scored.append((m, opp_count))

        if self._has_game_eval:
            scored.sort(key=lambda x: -x[1])  # higher eval = better
        else:
            scored.sort(key=lambda x: x[1])   # fewer opp moves = better
        ordered = [m for m, _ in scored]
        random.shuffle(rest)
        return ordered + rest

    # ── MCTS iteration ───────────────────────────────────────────────

    def _iterate(self, root, logic, bot_player):
        node = root
        sim = root.state
        path = [node]
        sim_moves = []

        # ── Selection (with progressive widening for Strong) ─────────
        while True:
            # Lazy-init: load legal moves on first visit
            if node.untried is None:
                st = logic._get_game_status(sim)
                if st["is_over"]:
                    node.untried = []
                    if st["winner"] == bot_player:
                        node.implicit_minimax_value = 1.0
                    elif st["winner"] is not None:
                        node.implicit_minimax_value = 0.0
                    else:
                        node.implicit_minimax_value = 0.5
                    if self.use_solver:
                        if st["winner"] == bot_player:
                            node.proven = True
                        elif st["winner"] is not None:
                            node.proven = False
                    break
                else:
                    mvs = logic._get_legal_moves(sim, node.player)
                    if self.use_eval and len(mvs) > _PW_THRESHOLD:
                        node.untried = self._pw_sort(
                            logic, sim, node.player, mvs, bot_player)
                    else:
                        node.untried = list(mvs)
                    if not node.untried:
                        break

            # Determine if expansion is allowed
            can_expand = bool(node.untried) and self._pw_allow(node)

            if not node.children and not can_expand:
                break  # terminal or at capacity with no children

            if not node.children:
                break  # must expand (no children to select from)

            if self.use_grave:
                if can_expand:
                    # PW: FPU competes with children
                    pq = node.value / node.visits if node.visits > 0 else 0.5
                    fpu = pq - _FPU_OFFSET + _PBIAS_C * 0.5
                    sel = self._enhanced_select(node, bot_player,
                                                fpu_score=fpu)
                    if sel is None:
                        break  # FPU won → expand
                    node = sel
                else:
                    node = self._enhanced_select(node, bot_player)
            else:
                # Weak bot: original logic
                if node.untried:
                    break
                parent_log = math.log(node.visits + 1)
                node = max(node.children,
                           key=lambda n: _ucb1_score(n, self.c, parent_log))

            if node.move is not None:
                sim_moves.append((repr(node.move), node.parent.player))
            path.append(node)
            sim = node.state

        # ── Expansion ────────────────────────────────────────────────
        if node.untried and self._pw_allow(node):
            if self.use_eval:
                mv = node.untried.pop(0)  # best-first (sorted)
            else:
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

            # Cache evaluation & init implicit minimax at expansion
            if nst["is_over"]:
                if nst["winner"] == bot_player:
                    child.cached_eval = 1.0
                    child.implicit_minimax_value = 1.0
                elif nst["winner"] is not None:
                    child.cached_eval = 0.0
                    child.implicit_minimax_value = 0.0
                else:
                    child.cached_eval = 0.5
                    child.implicit_minimax_value = 0.5
                if self.use_solver:
                    if nst["winner"] == bot_player:
                        child.proven = True
                    elif nst["winner"] is not None:
                        child.proven = False
            elif self._has_game_eval:
                ev = logic.evaluate_position(ns, bot_player)
                if ev is not None:
                    child.cached_eval = ev
                    child.implicit_minimax_value = ev
                else:
                    child.implicit_minimax_value = 0.5
            else:
                child.implicit_minimax_value = 0.5

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

        # ── Implicit minimax backpropagation ─────────────────────────
        if self.use_eval:
            for i in range(len(path) - 1, -1, -1):
                n = path[i]
                if not n.children:
                    continue
                child_vals = [ch.implicit_minimax_value for ch in n.children
                              if ch.implicit_minimax_value is not None]
                if not child_vals:
                    continue
                if n.player == bot_player:
                    n.implicit_minimax_value = max(child_vals)
                else:
                    n.implicit_minimax_value = min(child_vals)

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

        # ── LGRF update ──────────────────────────────────────────────
        if self.use_eval and self._po_moves:
            if result_val > 0.7:
                # Winning playout — store good replies
                lb = {1: None, 2: None}
                pb = {1: None, 2: None}
                for mv, p, mv_repr in self._po_moves:
                    opp = 3 - p
                    ol = lb[opp]
                    op = pb[opp]
                    if ol is not None:
                        self._lgrf1[p][ol] = mv
                        if op is not None:
                            self._lgrf2[p][(op, ol)] = mv
                    pb[p] = lb[p]
                    lb[p] = mv_repr
            elif result_val < 0.3:
                # Losing playout — forget used LGRF entries
                for order, key, p in self._po_lgrf_used:
                    if order == 2:
                        self._lgrf2[p].pop(key, None)
                    else:
                        self._lgrf1[p].pop(key, None)

        # ── MAST update ──────────────────────────────────────────────
        if self.use_eval and self._po_moves:
            for _, p, mv_repr in self._po_moves:
                reward = result_val if p == bot_player else (1.0 - result_val)
                entry = self._mast[p].get(mv_repr)
                if entry is None:
                    self._mast[p][mv_repr] = [reward, 1]
                else:
                    entry[0] += reward
                    entry[1] += 1
            self._sim_count += 1
            if self._sim_count % _MAST_DECAY_INTERVAL == 0:
                for p_tbl in self._mast.values():
                    for e in p_tbl.values():
                        e[0] *= _MAST_DECAY
                        e[1] *= _MAST_DECAY

    def _solver_backup(self, path):
        """Propagate proven results up the tree via minimax logic.

        With progressive widening, a node cannot be proven as a loss
        while unexpanded moves remain — there might be a saving move.
        """
        for i in range(len(path) - 1, -1, -1):
            node = path[i]
            if node.proven is not None:
                continue
            if not node.children or node.untried is None:
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
            elif not node.untried:
                # All moves expanded AND all children proven loss
                node.proven = False
            # else: unexpanded moves remain — don't prove loss

    # ── Progressive widening helpers ──────────────────────────────────

    def _pw_allow(self, node):
        """True if progressive widening permits another expansion."""
        if not node.untried:
            return False
        if not self.use_eval:
            return True  # Weak: no widening restriction
        total = len(node.children) + len(node.untried)
        if total <= _PW_THRESHOLD:
            return True  # small BF — expand freely
        max_ch = max(2, int(_PW_K * (node.visits ** _PW_ALPHA)))
        return len(node.children) < max_ch

    def _pw_sort(self, logic, state, player, moves, bot_player):
        """Sort moves best-first for progressive widening."""
        moves = list(moves)
        if self._has_game_eval:
            k = min(8, len(moves))
            sample = random.sample(moves, k)
            rest = [m for m in moves if m not in sample]
            scored = []
            for m in sample:
                ns = logic._apply_move(state, player, m)
                st = logic._get_game_status(ns)
                if st["is_over"]:
                    scored.append((m, 1.0 if st["winner"] == player else -1.0))
                    continue
                ev = logic.evaluate_position(ns, bot_player)
                scored.append((m, ev if ev is not None else 0.5))
            scored.sort(key=lambda x: -x[1])
            random.shuffle(rest)
            return [m for m, _ in scored] + rest

        mast_p = self._mast.get(player, {})
        if mast_p:
            scored = []
            for m in moves:
                ms = mast_p.get(repr(m))
                scored.append((m, ms[0] / ms[1] if ms and ms[1] > 0 else 0.5))
            scored.sort(key=lambda x: -x[1])
            return [m for m, _ in scored]

        random.shuffle(moves)
        return moves

    # ── Enhanced selection (FPU + progressive bias + implicit minimax + adaptive C)

    def _enhanced_select(self, node, bot_player, fpu_score=None):
        """Select a child using all tree-policy enhancements.

        If *fpu_score* is given and exceeds the best child's score,
        returns ``None`` to signal that expansion should occur instead.
        """
        children = node.children

        # Filter proven-win subtrees (solver: don't re-explore solved wins)
        if self.use_solver:
            viable = [ch for ch in children if ch.proven is not True]
            if not viable:
                viable = children
        else:
            viable = children

        parent_q = node.value / node.visits if node.visits > 0 else 0.5
        parent_log = math.log(node.visits + 1)

        # AMAF tables for GRAVE
        if node.visits >= _GRAVE_REF:
            aw, av = node.amaf_wins, node.amaf_visits
        else:
            aw, av = _find_amaf_ancestor(node)

        # ── Adaptive C: std of Q_combined across visited children ────
        q_list = []
        for ch in viable:
            if ch.visits > 0:
                if ch.proven is True:
                    q_list.append(1.0)
                elif ch.proven is False:
                    q_list.append(0.0)
                else:
                    qm = ch.value / ch.visits
                    vim = ch.implicit_minimax_value
                    if vim is None:
                        vim = qm
                    q_list.append((1.0 - _IM_ALPHA) * qm + _IM_ALPHA * vim)

        if len(q_list) >= 3:
            mean_q = sum(q_list) / len(q_list)
            var_q = sum((q - mean_q) ** 2 for q in q_list) / len(q_list)
            c_eff = self.c * math.sqrt(var_q) if var_q > 0 else self.c
        else:
            c_eff = self.c

        # ── Score each child ─────────────────────────────────────────
        best = viable[0]
        best_score = -_INF

        for ch in viable:
            h = ch.cached_eval if ch.cached_eval is not None else 0.5

            # Proven-loss: never select unless all are proven losses
            if ch.proven is False:
                score = -1e6

            elif ch.visits == 0:
                # FPU: use cached eval if available, else parent_Q - offset
                if ch.cached_eval is not None:
                    score = ch.cached_eval
                else:
                    score = parent_q - _FPU_OFFSET
                # Progressive bias at N=0 (denominator=1)
                score += _PBIAS_C * h

            else:
                # Q_combined: blend MCTS Q with implicit minimax
                if ch.proven is True:
                    q_comb = 1.0
                else:
                    qm = ch.value / ch.visits
                    vim = ch.implicit_minimax_value
                    if vim is None:
                        vim = qm
                    q_comb = (1.0 - _IM_ALPHA) * qm + _IM_ALPHA * vim

                # UCB exploration with adaptive C
                explore = c_eff * math.sqrt(parent_log / ch.visits)
                ucb = q_comb + explore

                # GRAVE AMAF blending
                mk = repr(ch.move)
                a_v = av.get(mk, 0)
                if a_v > 0:
                    amaf_val = aw.get(mk, 0.0) / a_v
                    beta = math.sqrt(_GRAVE_K / (3.0 * ch.visits + _GRAVE_K))
                    score = (1.0 - beta) * ucb + beta * amaf_val
                else:
                    score = ucb

                # Progressive bias (decays with visits)
                score += _PBIAS_C * h / (ch.visits + 1)

            if score > best_score:
                best_score = score
                best = ch

        if fpu_score is not None and fpu_score >= best_score:
            return None  # expand instead of selecting existing child
        return best

    # ── Playout ──────────────────────────────────────────────────────

    def _playout(self, state, logic, bot_player, sim_moves):
        """Simulate moves with LGRF, MAST, early termination, quiescence."""
        po_moves = []
        lgrf_used = []
        last_mv = {1: None, 2: None}   # player → repr of last move
        prev_mv = {1: None, 2: None}   # player → repr of move before last
        prev_eval = None                # eval from last check (quiescence)
        result = None
        has_eval = self._has_game_eval

        for depth in range(_PLAYOUT_DEPTH):
            st = logic._get_game_status(state)
            if st["is_over"]:
                if st["winner"] == bot_player:
                    result = 1.0
                elif st["winner"] is None:
                    result = 0.5
                else:
                    result = 0.0
                break

            # ── Early termination with quiescence (every 5 moves) ──
            if has_eval and depth > 0 and depth % _EARLY_CHECK == 0:
                ev = logic.evaluate_position(state, bot_player)
                if ev is not None:
                    quiet = (prev_eval is None
                             or abs(ev - prev_eval) <= _QUIESCE_DELTA)
                    if quiet:
                        if ev > 0.9:
                            result = 1.0
                            break
                        if ev < 0.1:
                            result = 0.0
                            break
                    prev_eval = ev

            p = logic._get_current_player(state)
            mvs = logic._get_legal_moves(state, p)
            if not mvs:
                result = 0.5
                break

            mv = None
            opp = 3 - p

            # ── Priority 1: immediate win (depth < 2) ──────────────
            if depth < 2:
                for m in mvs:
                    ns = logic._apply_move(state, p, m)
                    s = logic._get_game_status(ns)
                    if s["is_over"] and s["winner"] == p:
                        mv = m
                        break

            # ── Priority 2: LGRF-2 / LGRF-1 ────────────────────────
            if mv is None and self.use_eval:
                ol = last_mv[opp]
                op = prev_mv[opp]
                if ol is not None and op is not None:
                    reply = self._lgrf2[p].get((op, ol))
                    if reply is not None and reply in mvs:
                        mv = reply
                        lgrf_used.append((2, (op, ol), p))
                if mv is None and ol is not None:
                    reply = self._lgrf1[p].get(ol)
                    if reply is not None and reply in mvs:
                        mv = reply
                        lgrf_used.append((1, ol, p))

            # ── Priority 3: ε-greedy with eval + MAST blending ─────
            if mv is None and len(mvs) > 1 and random.random() >= _PLAYOUT_EPSILON:
                use_ev = has_eval and depth < 3
                mast_p = self._mast[p]
                if use_ev or mast_p:
                    k = min(4, len(mvs))
                    sample = random.sample(mvs, k) if len(mvs) > k else mvs
                    best_mv = None
                    best_sc = -1.0
                    for sm in sample:
                        eval_sc = None
                        if use_ev:
                            ns = logic._apply_move(state, p, sm)
                            ev = logic.evaluate_position(ns, p)
                            if ev is not None:
                                eval_sc = ev
                        mk = repr(sm)
                        ms = mast_p.get(mk)
                        mast_sc = (ms[0] / ms[1]) if ms and ms[1] > 0 else None

                        if eval_sc is not None and mast_sc is not None:
                            sc = (1.0 - _MAST_BLEND) * eval_sc + _MAST_BLEND * mast_sc
                        elif eval_sc is not None:
                            sc = eval_sc
                        elif mast_sc is not None:
                            sc = mast_sc
                        else:
                            sc = 0.5

                        if sc > best_sc:
                            best_sc = sc
                            best_mv = sm
                    if best_mv is not None:
                        mv = best_mv

            # ── Priority 4: random ─────────────────────────────────
            if mv is None:
                mv = random.choice(mvs)

            # Track move for LGRF/MAST
            mv_repr = repr(mv)
            prev_mv[p] = last_mv[p]
            last_mv[p] = mv_repr
            po_moves.append((mv, p, mv_repr))
            sim_moves.append((mv_repr, p))
            state = logic._apply_move(state, p, mv)

        # ── Cutoff evaluation (depth limit reached) ────────────────
        if result is None:
            if not self.use_eval:
                result = 0.5
            elif has_eval:
                ev = logic.evaluate_position(state, bot_player)
                result = ev if ev is not None else \
                    self._evaluate(state, logic, bot_player)
            else:
                result = self._evaluate(state, logic, bot_player)

        self._po_moves = po_moves
        self._po_lgrf_used = lgrf_used
        return result

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
