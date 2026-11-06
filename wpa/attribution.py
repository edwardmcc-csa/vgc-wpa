"""A choice's expected win probability (Week 9 Task 4) and each turn's swing
split three ways (Task 5, the plan's M5 part 1), as DEFINITIONS rev 8 §3 and §4
set out. From the analysed player's side:

- your decision = E[WP | your choice] - WP(before);
- their decision = E[WP | your choice, their choice] - E[WP | your choice];
- the dice = WP(after) - E[WP | your choice, their choice];

and beside them, never alone, cost against the best and against the average of
the choices compared.

E[WP | ...] averages v4's win probability of every board the turn can end on:
the opponent's replies weighted by the opponent choice model (`wpa.policy`,
Task 3: the likeliest taken exactly, the rest of the chance estimated from
replies drawn in proportion to it, so none is dropped), and every roll,
critical hit, miss and Speed tie weighted by the resolver (`wpa.resolver`,
Task 2). A choice the log does not show (a Pokemon that could not move or fell
first, a hidden target) is averaged with the same model. Each Pokemon's spread is
its most likely one at the decision (`wpa.spreads`), not a mixture: what that
misses lands in the dice (the Week 9 report says how often).

The core (`decompose`, `mixture`, `trim`, `taken_mixture`, `TurnValues`) is
kept apart from the model and the logs so that the plan's M5 tests can run on a
stand-in. `python -m wpa.attribution` runs it on a fixed sample of validation
sets and `--report` summarises the results. The test split is never read.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from wpa.choices import Action, joint

Joint = tuple[Action, ...]
Mix = list[tuple[Joint, float]]
REPLAY = "https://replay.pokemonshowdown.com/"


# --------------------------------------------------------------------------
# The split (DEFINITIONS §3, §4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Split:
    before: float
    after: float
    yours: float
    theirs: float
    dice: float
    vs_best: float | None = None
    vs_average: float | None = None
    kept: float = 1.0

    @property
    def swing(self) -> float:
        return self.after - self.before

    def conserved(self, tol: float = 1e-3) -> bool:
        return abs(self.yours + self.theirs + self.dice - self.swing) <= tol


def expected(value: Callable[[Joint, Joint], float], ours: Mix, theirs: Mix) -> float:
    """The chance-weighted average of `value(our choice, their choice)`."""
    num = den = 0.0
    for o, p in ours:
        for t, q in theirs:
            w = p * q
            if w > 0:
                num += w * value(o, t)
                den += w
    return num / den


def decompose(
    value: Callable[[Joint, Joint], float],
    before: float,
    after: float,
    ours: Mix,
    theirs: Mix,
    likely: Mix,
    alternatives: Sequence[Mix] | None = None,
    kept: float = 1.0,
) -> Split:
    """`value(ours, theirs)`: E[WP | both choices], from the analysed side.
    `ours`, `theirs`: the choices taken (a mixture where the log does not show
    one). `likely`: the opponent's likely replies. `alternatives`: our choices
    to compare with, for cost against the best and the average."""
    e_yours = expected(value, ours, likely)
    e_both = expected(value, ours, theirs)
    vs_best = vs_average = None
    if alternatives:
        es = [expected(value, alt, likely) for alt in alternatives]
        vs_best = e_yours - max(max(es), e_yours)
        vs_average = e_yours - float(np.mean(es))
    return Split(
        before,
        after,
        e_yours - before,
        e_both - e_yours,
        after - e_both,
        vs_best,
        vs_average,
        kept,
    )


# --------------------------------------------------------------------------
# Choices and their chances
# --------------------------------------------------------------------------


def mixture(per_mon: Mapping[int, Sequence[tuple[Action, float]]]) -> Mix:
    """One side's joint choices from each Pokemon's chances, taken as
    independent; pairs the game forbids (two switches to one Pokemon, two Mega
    Evolutions) dropped and the rest scaled back to 1."""
    per = {k: list(v) for k, v in per_mon.items() if v}
    if not per:
        return [((), 1.0)]
    keys = sorted(per)
    chance = {k: dict(per[k]) for k in keys}
    out = []
    for combo in joint({k: [a for a, _ in per[k]] for k in keys}):
        q = 1.0
        for k, a in zip(keys, combo):
            q *= chance[k][a]
        if q > 0:
            out.append((combo, q))
    s = sum(q for _, q in out)
    return [(c, q / s) for c, q in out] if s > 0 else []


def trim(mix: Mix, keep: float = 0.95, most: int | None = None) -> tuple[Mix, float]:
    """The likeliest joint choices until `keep` of the chance is covered (and
    at most `most`), scaled back to 1, with the share kept."""
    out: Mix = []
    s = 0.0
    for j, p in sorted(mix, key=lambda x: -x[1]):
        if s >= keep - 1e-12 or (most is not None and len(out) >= most):
            break
        out.append((j, p))
        s += p
    return [(j, p / s) for j, p in out], s


def likely(full: Mix, top: int, draws: int, seed: str) -> tuple[Mix, float]:
    """The opponent's replies for E[WP | your choice]: the `top` likeliest with
    their own chances, and the rest of the chance shared by `draws` replies
    drawn from the rest in proportion to theirs (the same draws for the same
    `seed`). Nothing is dropped; the drawn part is an estimate with no lean.
    Returns the mixture and the share taken exactly. With no draws: the top,
    scaled back to 1, as `trim`."""
    import hashlib

    order = sorted(full, key=lambda x: -x[1])
    head, rest = order[:top], order[top:]
    exact = sum(p for _, p in head)
    if not rest or draws <= 0 or exact >= 1 - 1e-12:
        return [(j, p / exact) for j, p in head], exact
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    ps = np.array([p for _, p in rest], dtype=float)
    picks = rng.choice(len(rest), size=draws, p=ps / ps.sum())
    share = (1.0 - exact) / draws
    return list(head) + [(rest[i][0], share) for i in picks], exact


def taken_mixture(
    taken: Mapping[int, Action | str],
    hidden: set[int],
    opts: Mapping[int, Sequence[Action]],
    chances: Mapping[int, Sequence[float]],
) -> Mix:
    """The choice a side took: what the log shows, and where it shows nothing
    (or a move but not its target) the model's chances over the options."""
    per: dict[int, list[tuple[Action, float]]] = {}
    for idx, o in opts.items():
        a = taken.get(idx)
        pairs = list(zip(o, chances[idx]))
        if isinstance(a, Action) and idx in hidden:
            same = [(x, p) for x, p in pairs if x.kind == a.kind and x.move == a.move]
            pairs = same or pairs
        elif isinstance(a, Action):
            pairs = [(a, 1.0)]
        s = sum(p for _, p in pairs)
        per[idx] = [(x, p / s) for x, p in pairs] if s > 0 else []
    return mixture(per)


# --------------------------------------------------------------------------
# One turn's values: the resolver and a win-probability function
# --------------------------------------------------------------------------


class TurnValues:
    """E[WP | p1's choice, p2's choice] from p1's side at one turn: every board
    the resolver gives, valued by `board_wp` (a list of outcomes in, p1's win
    probabilities out). Resolves are kept, so each pair is resolved once."""

    def __init__(self, resolver, sides: Mapping, fld, board_wp) -> None:
        self.resolver = resolver
        self.sides = sides
        self.fld = fld
        self.board_wp = board_wp
        self.outcomes: dict[tuple[Joint, Joint], list] = {}
        self._value: dict[tuple[Joint, Joint], float] = {}

    def prepare(self, pairs: Sequence[tuple[Joint, Joint]]) -> None:
        """Resolve every pair not yet resolved and value all their boards in one
        batch (the model is far quicker on one large batch than many small)."""
        todo = [k for k in dict.fromkeys(pairs) if k not in self._value]
        if not todo:
            return
        got = {}
        for p1, p2 in todo:
            got[(p1, p2)] = self.resolver.resolve(
                copy.deepcopy(dict(self.sides)),
                copy.deepcopy(self.fld),
                {"p1": p1, "p2": p2},
            )
        flat = [o for k in todo for o in got[k]]
        wps = np.asarray(self.board_wp(flat), dtype=float)
        i = 0
        for k in todo:
            outs = got[k]
            ps = np.array([o.prob for o in outs], dtype=float)
            w = wps[i : i + len(outs)]
            i += len(outs)
            self.outcomes[k] = outs
            self._value[k] = float((ps * w).sum() / ps.sum())

    def __call__(self, p1: Joint, p2: Joint) -> float:
        if (p1, p2) not in self._value:
            self.prepare([(p1, p2)])
        return self._value[(p1, p2)]

    def for_role(self, role: str) -> Callable[[Joint, Joint], float]:
        """The same values from `role`'s side: (its choice, the other's)."""
        if role == "p1":
            return self
        return lambda ours, theirs: 1.0 - self(theirs, ours)


# --------------------------------------------------------------------------
# The model's win probability of a board after the turn
# --------------------------------------------------------------------------


def wp_model(models: Path, fmt: str, groups: str):
    """v4's prediction as the Week 8 test opening used it: Reg M-A's model
    (recalibrated if it was), Reg M-B the pooled model with its temperature."""
    from wpa.evaluate import _temperature, apply_temperature, use_recalibration
    from wpa.features import columns
    from wpa.model import load

    which = "pooled" if fmt == "regmb" else fmt
    d = Path(models) / which
    cols = columns(groups) + (["z_format_regmb"] if which == "pooled" else [])
    model = load(d / f"{groups}.pkl", cols)
    recal = d / f"{groups}.recal.pkl"
    if recal.exists() and use_recalibration(fmt):
        model = load(recal, cols)
    temp = _temperature(d, groups) if fmt == "regmb" else None

    def predict(X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        if which == "pooled":
            X = np.hstack([X, np.ones((len(X), 1), dtype=np.float32)])
        p = model.predict(X)
        return apply_temperature(p, temp) if temp is not None else p

    return predict


def _board_key(p1: Sequence[Mapping], p2: Sequence[Mapping], fld) -> str:
    def clean(side):
        return [{k: v for k, v in m.items() if not k.startswith("_")} for m in side]

    return json.dumps([clean(p1), clean(p2), fld.key()], sort_keys=True, default=str)


class BoardWP:
    """p1's win probability of a board the turn can end on: the decision's
    state with the new board and timers, at the next decision (after the turn
    if a Pokemon fell, else the next turn's start), from what was known at the
    decision (the turn's own end-of-turn observations left out)."""

    def __init__(
        self, predict, states, k, joined, sheets, dex, table, groups, ctx
    ) -> None:
        s0 = states[k]
        self.turn = s0["turn"]
        self.prior = [
            dict(s, observations=[]) if s["turn"] >= self.turn else s
            for s in states[: k + 1]
        ]
        self.s0, self.k, self.joined = s0, k, joined
        self.sheets, self.dex, self.table, self.groups, self.ctx = (
            sheets,
            dex,
            table,
            groups,
            ctx,
        )
        self.predict = predict
        self.fell0 = sum(m["fainted"] for m in s0["our_pokemon"] + s0["opp_pokemon"])
        self._cache: dict[str, float] = {}

    def _row(self, ours, theirs, fld) -> list[float]:
        from wpa.features import columns, state_features
        from wpa.resolver import timers_for

        fell = sum(m["fainted"] for m in list(ours) + list(theirs)) > self.fell0
        s = dict(
            self.s0,
            our_pokemon=[dict(m) for m in ours],
            opp_pokemon=[dict(m) for m in theirs],
            moment="after_turn" if fell else "turn_start",
            turn=self.turn if fell else self.turn + 1,
            decision_index=(self.s0["decision_index"] + 1) if fell else 0,
            observations=[],
        )
        j = timers_for(fld, "p1", before=self.joined)
        f = state_features(
            [*self.prior, s],
            self.k + 1,
            "p1",
            j,
            self.sheets,
            self.dex,
            self.table,
            self.groups,
            self.ctx,
        )
        return [f[c] for c in columns(self.groups)]

    def boards(self, items: Sequence[tuple[Sequence, Sequence, object]]) -> np.ndarray:
        keys = [_board_key(a, b, f) for a, b, f in items]
        todo = {}
        for key, item in zip(keys, items):
            if key not in self._cache and key not in todo:
                todo[key] = item
        if todo:
            X = np.array([self._row(*item) for item in todo.values()], dtype=np.float32)
            for key, p in zip(todo, self.predict(X)):
                self._cache[key] = float(p)
        return np.array([self._cache[k] for k in keys])

    def __call__(self, outs) -> np.ndarray:
        return self.boards([(o.sides["p1"], o.sides["p2"], o.field) for o in outs])


# --------------------------------------------------------------------------
# One game
# --------------------------------------------------------------------------


def _mirror(j):
    from wpa.timer_join import JoinedTimers

    if j is None:
        return None
    return JoinedTimers(
        j.theirs, j.ours, j.field, j.their_counters, j.our_counters, j.moment
    )


def end_of_turn(game, k: int):
    """The board turn `states[k]["turn"]` ended on, from p1's side, before any
    replacement: the first after-turn snapshot of that turn on either side, else
    p1's next turn start or the end of the game. (board p1, board p2, timers,
    terminal state or None)."""
    states = game.states["p1"]
    t = states[k]["turn"]
    best = None
    for r in ("p1", "p2"):
        for i, s in enumerate(game.states[r]):
            if (
                s["turn"] == t
                and s["moment"] == "after_turn"
                and i < len(game.points[r])
            ):
                pt = game.points[r][i]
                if best is None or pt < best[0]:
                    best = (pt, r, i)
    if best is not None:
        _, r, i = best
        s, j = game.states[r][i], game.joined[r][i]
        if r == "p1":
            return s["our_pokemon"], s["opp_pokemon"], j, None
        return s["opp_pokemon"], s["our_pokemon"], _mirror(j), None
    for i in range(k + 1, len(states)):
        s = states[i]
        if s["moment"] == "terminal":
            return s["our_pokemon"], s["opp_pokemon"], game.joined["p1"][i], s
        if s["turn"] > t:
            return s["our_pokemon"], s["opp_pokemon"], game.joined["p1"][i], None
    return None


def _close(a: Mapping, b: Mapping, tol: float) -> bool:
    for r in ("p1", "p2"):
        for x, y in zip(a[r], b[r]):
            if bool(x["fainted"]) != bool(y["fainted"]):
                return False
            if not x["fainted"] and abs(x["hp_fraction"] - y["hp_fraction"]) > tol:
                return False
    return True


@dataclass
class Tools:
    """What a run shares across games (one per worker)."""

    dexes: dict
    tables: dict
    moves: dict
    calc: Any
    store: Any
    bring: Any
    policy: Any
    predict: dict
    groups: str = "ABCDEFGHIJ"
    resolution: float = 0.05
    cap: int = 300
    top: int = 6
    draws: int = 6
    alternatives: int = 5


def analyse_game(
    tag: str, log: str, fmt: str, tools: Tools, with_alternatives: bool = True
) -> list[dict]:
    """One record per decision point (each turn, each player) of one game."""
    from wpa import choices as C
    from wpa import decisions as D
    from wpa import resolver as R
    from wpa.bring import brought_from_log
    from wpa.features import columns, damage_contexts, state_features
    from wpa.policy_data import _timers_by_turn, game_tools, turn_options
    from wpa.state_timing import loser_has_pokemon_left

    dex, table = tools.dexes[fmt], tools.tables[fmt]
    sheets, spreads, odds = game_tools(tag, log, fmt, tools.store, tools.bring, dex)
    if set(sheets) != {"p1", "p2"}:
        return []
    game = D.build_game(log, table)
    states, joined = game.states["p1"], game.joined["p1"]
    if not states or states[-1]["outcome"] is None:
        return []
    ctxs = damage_contexts(
        tag, log, game, sheets, dex, tools.calc, tools.store, tools.bring
    )["p1"]
    timers = {r: _timers_by_turn(game, r) for r in ("p1", "p2")}
    brought = brought_from_log(log)
    turns: dict[int, dict[str, C.Turn]] = {}
    for t in C.turns(log, dex):
        turns.setdefault(t.turn, {})[t.role] = t
    rates = (
        tools.policy.rates.get(fmt, {}) if isinstance(tools.policy.rates, dict) else {}
    )
    cols = columns(tools.groups)
    out: list[dict] = []
    for k, s in enumerate(states[:-1]):
        if s["moment"] != "turn_start" or s["turn"] not in turns:
            continue
        tt = turns[s["turn"]]
        if set(tt) != {"p1", "p2"}:
            continue
        end = end_of_turn(game, k)
        base = {"tag": tag, "format": fmt, "turn": s["turn"]}
        if end is None:
            continue
        if end[3] is not None and loser_has_pokemon_left(end[3]):
            out += [
                dict(base, role=r, skipped="forfeit or timer") for r in ("p1", "p2")
            ]
            continue
        t0 = time.time()
        try:
            sides = {
                "p1": [dict(m) for m in s["our_pokemon"]],
                "p2": [dict(m) for m in s["opp_pokemon"]],
            }
            for r in ("p1", "p2"):
                for i in brought.get(r, ()):
                    if i < len(sides[r]):
                        sides[r][i]["_brought"] = True
            fld = R.field_from_timers(joined[k], "p1")
            rv = R.Resolver(
                dex,
                tools.moves[fmt],
                tools.calc,
                sheets,
                ctxs[k].spreads,
                resolution=tools.resolution,
                cap=tools.cap,
            )
            bw = BoardWP(
                tools.predict[fmt],
                states,
                k,
                joined[k],
                sheets,
                dex,
                table,
                tools.groups,
                ctxs[k],
            )
            tv = TurnValues(rv, sides, fld, bw)
            f0 = state_features(
                states, k, "p1", joined[k], sheets, dex, table, tools.groups, ctxs[k]
            )
            before = float(
                tools.predict[fmt](np.array([[f0[c] for c in cols]], dtype=np.float32))[
                    0
                ]
            )
            a_p1, a_p2, a_j, _term = end
            after = float(bw.boards([(a_p1, a_p2, R.field_from_timers(a_j, "p1"))])[0])
            mixes = {}
            for r in ("p1", "p2"):
                t = tt[r]
                feats = turn_options(
                    t,
                    timers[r].get(t.turn),
                    sheets,
                    spreads,
                    dex,
                    tools.moves[fmt],
                    rates,
                    tools.calc,
                    odds,
                )
                opts = {i: o for i, (o, _X) in feats.items()}
                ch = {i: list(tools.policy.chances(X)) for i, (_o, X) in feats.items()}
                taken = taken_mixture(t.taken, t.hidden, opts, ch)
                full = mixture({i: list(zip(opts[i], ch[i])) for i in opts})
                seed = f"{tag} {s['turn']} {r}"
                lk, kept = likely(full, tools.top, tools.draws, seed)
                alts = None
                if with_alternatives and tools.alternatives:
                    top, _ = trim(full, 1.0, tools.alternatives)
                    alts = [[(j, 1.0)] for j, _ in top]
                    if not (len(taken) == 1 and any(taken[0][0] == j for j, _ in top)):
                        alts.append(taken)
                unknown = sum(
                    1
                    for i in opts
                    if not isinstance(t.taken.get(i), Action) or i in t.hidden
                )
                mixes[r] = (taken, lk, kept, alts, unknown)
            t1, l1, _k1, alts1, _u1 = mixes["p1"]
            t2, l2, _k2, alts2, _u2 = mixes["p2"]
            pairs = [(x, y) for x, _ in t1 for y, _ in l2 + t2]
            pairs += [(x, y) for x, _ in l1 for y, _ in t2]
            for alt in alts1 or ():
                pairs += [(x, y) for x, _ in alt for y, _ in l2]
            for alt in alts2 or ():
                pairs += [(x, y) for x, _ in l1 for y, _ in alt]
            tv.prepare(pairs)
            recs = []
            for r, other in (("p1", "p2"), ("p2", "p1")):
                taken, _l, _k, alts, unknown = mixes[r]
                _t, lk, kept, _a, _u = mixes[other]
                b, a = (before, after) if r == "p1" else (1 - before, 1 - after)
                sp = decompose(
                    tv.for_role(r), b, a, taken, mixes[other][0], lk, alts, kept
                )
                recs.append(dict(base, role=r, unknown=unknown, **asdict(sp)))
            pairs = [(x, y) for x, _ in mixes["p1"][0] for y, _ in mixes["p2"][0]]
            outs = [o for key in pairs for o in tv.outcomes.get(key, ())]
            actual = {"p1": a_p1, "p2": a_p2}
            tol = max(0.03, tools.resolution + 0.01)
            found = any(_close(o.sides, actual, tol) for o in outs)
            partial = sorted(set().union(*(o.partial for o in outs))) if outs else []
            secs = time.time() - t0
            for rec in recs:
                rec.update(
                    found=found,
                    partial=partial,
                    seconds=secs,
                    resolves=len(tv.outcomes),
                    boards=len(bw._cache),
                )
            out += recs
        except Exception as e:  # pragma: no cover - reported, not hidden
            out += [
                dict(base, role=r, skipped=f"error: {type(e).__name__}: {str(e)[:80]}")
                for r in ("p1", "p2")
            ]
    return out


# --------------------------------------------------------------------------
# The run and the report
# --------------------------------------------------------------------------


def sample_sets(
    logs: Path, splits: Mapping[str, str], sets: Mapping[str, int]
) -> dict[str, list[tuple[str, str]]]:
    """A fixed sample of validation sets per format (by a hash of the set id,
    so the same sets every run), with all their games."""
    import hashlib

    from wpa.features import unit_of
    from wpa.formats import format_of
    from wpa.policy_data import _iter_logs

    by_unit: dict[str, dict[str, list]] = {f: {} for f in sets}
    for tag, log in _iter_logs(logs):
        if splits.get(tag) != "validation":
            continue  # the test split is never read
        try:
            fmt = format_of(tag)
        except Exception:
            continue
        if fmt not in sets:
            continue
        unit, n = unit_of(tag, log)
        by_unit[fmt].setdefault(unit, []).append((n, tag, log))
    out = {}
    for fmt, units in by_unit.items():
        order = sorted(
            units,
            key=lambda u: hashlib.sha256(f"wpa-attribution:{u}".encode()).hexdigest(),
        )
        out[fmt] = [
            (tag, log) for u in order[: sets[fmt]] for _n, tag, log in sorted(units[u])
        ]
    return out


def _tools(a) -> Tools:  # pragma: no cover - runs on the corpus
    import pickle

    from wpa.bring import BringModel
    from wpa.damage import Calc
    from wpa.policy import PolicyModel
    from wpa.resolver import load_moves, load_moves_file
    from wpa.spreads import UsageStore

    if a.dex_tables:
        dexes, tables = pickle.load(open(a.dex_tables, "rb"))
    else:
        from wpa.durations import load_all
        from wpa.team_sheets import load_dexes

        dexes, tables = load_dexes(a.showdown), load_all(a.showdown)
    mods = {"regma": "championsregma", "regmb": "champions"}
    moves = {
        f: load_moves_file(Path(a.moves_dir) / f"moves_{f}.json")
        if a.moves_dir
        else load_moves(a.showdown, mods[f])
        for f in mods
    }
    tools = Tools(
        dexes,
        tables,
        moves,
        Calc(),
        UsageStore(a.usage),
        BringModel.load(a.bring) if Path(a.bring).exists() else None,
        PolicyModel.load(a.policy),
        {f: wp_model(a.models, f, a.groups) for f in mods},
        a.groups,
        a.resolution,
        a.cap,
        a.top,
        a.draws,
        a.alternatives,
    )
    # one thread for the model, set once it is loaded (its thread pool comes
    # with it): on small batches the pool costs seconds per call
    from threadpoolctl import threadpool_limits

    threadpool_limits(1)
    return tools


_W: dict = {}


def _init(a) -> None:  # pragma: no cover
    _W["tools"] = _tools(a)


def _one(job) -> list[dict]:  # pragma: no cover
    tag, log, fmt, alt = job
    t0 = time.time()
    recs = analyse_game(tag, log, fmt, _W["tools"], alt)
    for r in recs:
        r["game_seconds"] = time.time() - t0
    return recs


def run(a) -> None:  # pragma: no cover - runs on the corpus
    from multiprocessing import Pool

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    games = sample_sets(a.logs, splits, {"regma": a.sets[0], "regmb": a.sets[1]})
    done = set()
    if a.out.exists():
        for line in a.out.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["tag"])
    jobs = []
    for fmt, gs in games.items():
        cap = a.max_games[{"regma": 0, "regmb": 1}[fmt]] if a.max_games else None
        for n, (tag, log) in enumerate(gs[:cap] if cap else gs):
            if tag not in done:
                jobs.append((tag, log, fmt, n % a.alternatives_every == 0))
    print(f"{len(jobs)} games to do ({len(done)} done before)", flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "a", encoding="utf-8") as f, Pool(a.workers, _init, (a,)) as pool:
        for i, recs in enumerate(pool.imap_unordered(_one, jobs), 1):
            if not recs:
                recs = [{"tag": "", "skipped": "no usable game"}]
            for r in recs:
                f.write(json.dumps(r) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"{i}/{len(jobs)} games", flush=True)


def _pts(xs) -> str:
    xs = np.asarray(xs, dtype=float)
    return (
        f"mean {100 * xs.mean():+.1f}, typical size {100 * np.sqrt((xs**2).mean()):.1f}"
    )


def _swing_line(r: Mapping) -> str:
    def pt(x: float) -> str:
        return f"{100 * x:+.0f}"

    text = (
        f"    {REPLAY}{r['tag']} turn {r['turn']} {r['role']}: "
        f"swing {pt(r['after'] - r['before'])} = yours {pt(r['yours'])}, "
        f"theirs {pt(r['theirs'])}, dice {pt(r['dice'])}"
    )
    if r.get("vs_best") is not None:
        text += f"; vs best {pt(r['vs_best'])}, vs average {pt(r['vs_average'])}"
    if not r["found"]:
        text += " (board not among the resolver's)"
    return text


def _format_lines(name: str, rs: Sequence[Mapping], top: int) -> list[str]:
    ok = [r for r in rs if "skipped" not in r]
    if not ok:
        return []
    games = len({r["tag"] for r in rs})
    skipped: dict[str, int] = {}
    for r in rs:
        if "skipped" in r:
            key = r["skipped"].split(":")[0]
            skipped[key] = skipped.get(key, 0) + 1
    err = max(
        abs(r["yours"] + r["theirs"] + r["dice"] - (r["after"] - r["before"]))
        for r in ok
    )
    turns = {(r["tag"], r["turn"]): r["seconds"] for r in ok}
    secs = np.array(list(turns.values()))
    head = f"{name}: {games} games, {len(ok)} decision points ({len(turns)} turns)"
    if skipped:
        head += f"; left out: {skipped}"
    lines = [
        head,
        f"  swing (after - before): {_pts([r['after'] - r['before'] for r in ok])}",
        f"  your decision: {_pts([r['yours'] for r in ok])}",
        f"  their decision: {_pts([r['theirs'] for r in ok])}",
        f"  the dice: {_pts([r['dice'] for r in ok])}",
        f"  the parts add up: largest error {err:.2e} (allowed 1e-3)",
    ]
    alt = [r for r in ok if r.get("vs_best") is not None]
    if alt:
        vb = np.array([r["vs_best"] for r in alt])
        va = np.array([r["vs_average"] for r in alt])
        lines += [
            f"  cost vs best ({len(alt)} decision points compared): "
            f"mean {100 * vb.mean():.1f} points; best choice taken "
            f"{100 * np.mean(vb > -1e-9):.0f}%; cost of 5+ points "
            f"{100 * np.mean(vb < -0.05):.0f}%",
            f"  cost vs average: mean {100 * va.mean():+.1f} points",
        ]
    kept = np.array([r["kept"] for r in ok])
    found = 100 * np.mean([r["found"] for r in ok])
    unknown = 100 * np.mean([r["unknown"] > 0 for r in ok])
    lines += [
        f"  their replies taken exactly (the rest drawn): mean {100 * kept.mean():.0f}%"
        f" of the chance, lowest {100 * kept.min():.0f}%",
        f"  the board that happened was among the resolver's: {found:.0f}%",
        f"  a choice the log does not show (averaged): {unknown:.0f}%",
        f"  time per turn: median {np.median(secs):.1f} s, mean {secs.mean():.1f} s, "
        f"slowest {secs.max():.0f} s",
        "",
        f"  the {top} biggest swings (points, from the player's side):",
    ]
    big = sorted(ok, key=lambda r: -abs(r["after"] - r["before"]))[:top]
    return lines + [_swing_line(r) for r in big] + [""]


def report(path: Path, top: int = 10) -> str:
    """The Week 9 first look: per format, the parts, both costs, the checks,
    the time, and the biggest swings with their replay links."""
    text = Path(path).read_text(encoding="utf-8")
    recs = [json.loads(x) for x in text.splitlines() if x.strip()]
    lines = ["Decision versus luck, a first look (DEFINITIONS rev 8, §3 and §4)", ""]
    for fmt, name in (("regma", "Reg M-A"), ("regmb", "Reg M-B")):
        lines += _format_lines(name, [r for r in recs if r.get("format") == fmt], top)
    return "\n".join(lines)


def main() -> None:  # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--bring", type=Path, default=Path("models_v4/bring.json"))
    p.add_argument("--policy", type=Path, default=Path("models_v4/policy.json"))
    p.add_argument("--models", type=Path, default=Path("models_v4"))
    p.add_argument("--groups", default="ABCDEFGHIJ")
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--dex-tables", type=Path, default=None)
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument(
        "--sets",
        type=int,
        nargs=2,
        default=(300, 199),
        help="validation sets: Reg M-A, Reg M-B",
    )
    p.add_argument(
        "--max-games",
        type=int,
        nargs=2,
        default=None,
        help="at most this many games (a timing run)",
    )
    p.add_argument(
        "--alternatives",
        type=int,
        default=10,
        help="our likeliest choices to compare with",
    )
    p.add_argument(
        "--alternatives-every",
        type=int,
        default=1,
        help="compare in every n-th game only",
    )
    p.add_argument(
        "--top", type=int, default=6, help="their likeliest replies, exactly"
    )
    p.add_argument("--draws", type=int, default=6, help="replies drawn from the rest")
    p.add_argument("--resolution", type=float, default=0.05)
    p.add_argument("--cap", type=int, default=300)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out", type=Path, default=Path("reports/attribution.jsonl"))
    p.add_argument("--report", action="store_true", help="summarise --out and stop")
    a = p.parse_args()
    if a.report:
        text = report(a.out)
        print(text)
        a.out.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")
        return
    run(a)
    text = report(a.out)
    print(text)
    a.out.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


__all__ = [
    "BoardWP",
    "Split",
    "TurnValues",
    "analyse_game",
    "decompose",
    "expected",
    "likely",
    "mixture",
    "report",
    "taken_mixture",
    "trim",
    "wp_model",
]
