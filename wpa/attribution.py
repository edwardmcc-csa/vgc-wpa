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
    # DEFINITIONS revision 10: `yours` (revision 8's "your decision") is your
    # choice against the typical choice plus the position
    choice: float | None = None
    position: float | None = None

    @property
    def swing(self) -> float:
        return self.after - self.before

    def conserved(self, tol: float = 1e-3) -> bool:
        ok = abs(self.yours + self.theirs + self.dice - self.swing) <= tol
        if self.choice is not None and self.position is not None:
            four = self.choice + self.position + self.theirs + self.dice
            ok = ok and abs(four - self.swing) <= tol
        return ok


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
    typical: Mix | None = None,
) -> Split:
    """`value(ours, theirs)`: E[WP | both choices], from the analysed side.
    `ours`, `theirs`: the choices taken (a mixture where the log does not show
    one). `likely`: the opponent's likely replies. `alternatives`: our choices
    to compare with, for cost against the best and the (unweighted) average.
    `typical`: what players typically choose here (DEFINITIONS §3, revision
    10); with it, your decision splits into your choice and the position."""
    e_yours = expected(value, ours, likely)
    e_both = expected(value, ours, theirs)
    vs_best = vs_average = None
    if alternatives:
        es = [expected(value, alt, likely) for alt in alternatives]
        vs_best = e_yours - max(max(es), e_yours)
        vs_average = e_yours - float(np.mean(es))
    choice = position = None
    if typical:
        e_typ = expected(value, typical, likely)
        same = len(typical) == 1 and len(ours) == 1 and typical[0][0] == ours[0][0]
        choice = 0.0 if same else e_yours - e_typ
        position = (e_yours - before) - choice
    return Split(
        before,
        after,
        e_yours - before,
        e_both - e_yours,
        after - e_both,
        vs_best,
        vs_average,
        kept,
        choice,
        position,
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


def expand_pivots(
    opts: Mapping[int, Sequence[Action]], chances: Mapping[int, Sequence[float]]
) -> tuple[dict, dict]:
    """Each switching move spread over the bench: the Pokemon it brings in is
    part of the choice (Week 10), weighted by the opponent model's chances for
    switching to each Pokemon. With nothing on the bench it stays as it is."""
    from dataclasses import replace

    from wpa.choices import PIVOT_MOVES

    o2: dict = {}
    c2: dict = {}
    for i, o in opts.items():
        ch = list(chances[i])
        sw = {a.switch_to: p for a, p in zip(o, ch) if a.kind == "switch"}
        total = sum(sw.values())
        no, nc = [], []
        for a, p in zip(o, ch):
            if a.kind == "move" and a.move in PIVOT_MOVES and sw:
                for j, q in sw.items():
                    no.append(replace(a, switch_to=j))
                    nc.append(p * (q / total if total > 0 else 1 / len(sw)))
            else:
                no.append(a)
                nc.append(p)
        o2[i], c2[i] = no, nc
    return o2, c2


def brought_four(brought: Mapping[str, set[int]]) -> dict[str, set[int] | None]:
    """Each side's four, where the log shows all four come out; else None (any
    Pokemon not seen could have been brought)."""
    from wpa.decisions import BRING

    return {r: (set(b) if len(b) >= BRING else None) for r, b in brought.items()}


def only_brought(
    opts: Mapping[int, Sequence[Action]],
    chances: Mapping[int, Sequence[float]],
    allowed: set[int] | None,
) -> tuple[dict, dict]:
    """A player's own options: no switch (or switching move) to a Pokemon they
    did not bring, the chances of the rest scaled back to 1. The opponent model
    offers such switches, as the opponent cannot tell; the player can."""
    if allowed is None:
        return dict(opts), dict(chances)
    o2, c2 = {}, {}
    for i, acts in opts.items():
        keep = [
            (a, p)
            for a, p in zip(acts, chances[i])
            if a.switch_to is None or a.switch_to in allowed
        ]
        tot = sum(p for _, p in keep)
        o2[i] = [a for a, _ in keep]
        c2[i] = [p / tot if tot > 0 else 1 / len(keep) for _, p in keep]
    return o2, c2


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
# The opponent model's sharpness (PO decision, 6 Nov)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SharpSample:
    """One decision point for fitting the sharpness: WP(before) from the analysed
    side, and each of the opponent's replies with its chance at sharpness 1 and
    E[WP | the choice taken, that reply]."""

    before: float
    chances: list[float]
    values: list[float]


def mean_yours(samples: Sequence[SharpSample], b: float) -> float:
    """ "Your decision" on average when the opponent model has sharpness `b`
    (each reply's chance to the power `b`, scaled back to 1)."""
    out = 0.0
    for x in samples:
        p = np.asarray(x.chances, dtype=float)
        logq = b * np.log(np.clip(p, 1e-300, None))
        q = np.exp(logq - logq.max())
        out += float((q * np.asarray(x.values)).sum() / q.sum()) - x.before
    return out / len(samples)


def fit_sharpness(
    samples: Sequence[SharpSample], lo: float = 0.25, hi: float = 16.0
) -> tuple[float, list[tuple[float, float]]]:
    """The sharpness at which "your decision" averages zero (DEFINITIONS §3), or
    the closest to it in [lo, hi]; with the curve (sharpness, average)."""
    grid = list(np.exp(np.linspace(np.log(lo), np.log(hi), 49)))
    curve = [(float(b), mean_yours(samples, b)) for b in grid]
    for (b0, m0), (b1, m1) in zip(curve, curve[1:]):
        if m0 == 0:
            return b0, curve
        if (m0 > 0) != (m1 > 0):
            for _ in range(60):  # bisection on the log scale
                mid = float(np.sqrt(b0 * b1))
                mm = mean_yours(samples, mid)
                if (mm > 0) == (m0 > 0):
                    b0, m0 = mid, mm
                else:
                    b1 = mid
            return float(np.sqrt(b0 * b1)), curve
    return min(curve, key=lambda x: abs(x[1]))[0], curve


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
        empty = [k for k in todo if not got[k]]
        if empty:
            raise ValueError(f"the resolver gave no boards for {empty[0]}")
        flat = [o for k in todo for o in got[k]]
        # a board where the game ended is worth its result; the rest, the model
        need = [o for o in flat if getattr(o, "winner", None) is None]
        rest = iter(np.asarray(self.board_wp(need), dtype=float) if need else ())
        wps = np.array(
            [
                next(rest)
                if getattr(o, "winner", None) is None
                else float(o.winner == "p1")
                for o in flat
            ],
            dtype=float,
        )
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


class SwitchIns:
    """A forced switch in the shape `TurnValues` asks of a resolver: the board
    after both sides' Pokemon come in (`Resolver.replace`). A side that does not
    replace passes an empty choice."""

    def __init__(self, resolver) -> None:
        self.resolver = resolver

    def resolve(self, sides, fld, actions):
        return self.resolver.replace(sides, fld, actions)


class Leads:
    """Team preview's leads in the shape `TurnValues` asks of a resolver: the
    board at turn 1's start after both sides' leads come in (`Resolver.lead`)."""

    def __init__(self, resolver) -> None:
        self.resolver = resolver

    def resolve(self, sides, fld, actions):
        return self.resolver.lead(sides, fld, actions)


def lead_joint(pair: Sequence[int]) -> Joint:
    """A pair of leads as a joint choice."""
    i, j = sorted(pair)
    return (Action(0, "switch", switch_to=i), Action(1, "switch", switch_to=j))


def chains(
    records: Sequence[Mapping], results: Mapping[str, float], tol: float = 1e-3
) -> list[dict]:
    """DEFINITIONS §2 on each game (Week 10 Task 6): its decision points in
    order, from p1's side, chain (each WP(after) is the next WP(before), within
    `tol`) and add up (the swings sum to the result minus WP at the first point).
    `results`: p1's result per game (1, 0, or 0.5 for a tie)."""
    games: dict[str, list[Mapping]] = {}
    for r in records:
        if r.get("role") == "p1":
            games.setdefault(r["tag"], []).append(r)
    out = []
    for tag, rs in games.items():
        rs = sorted(rs, key=lambda r: r.get("point", 0))
        forfeit = any(r.get("skipped") == "forfeit or timer" for r in rs)
        scored = [
            r for r in rs if r.get("before") is not None and r.get("after") is not None
        ]
        first_break, link = None, 0.0
        for i in range(1, len(rs)):
            a, b = rs[i - 1].get("after"), rs[i].get("before")
            gap = abs(a - b) if a is not None and b is not None else float("inf")
            link = max(link, gap)
            if gap > tol and first_break is None:
                first_break = i
        if len(scored) < len(rs) and first_break is None:
            first_break = next(i for i, r in enumerate(rs) if r not in scored)
        total = sum(r["after"] - r["before"] for r in scored)
        start = scored[0]["before"] if scored else float("nan")
        gap = total - (results.get(tag, float("nan")) - start)
        out.append(
            {
                "tag": tag,
                "points": len(rs),
                "chained": first_break is None,
                "first_break": first_break,
                "worst_link": link,
                "gap": gap,
                "adds_up": first_break is None and abs(gap) <= tol,
                "forfeit": forfeit,
            }
        )
    return out


# --------------------------------------------------------------------------
# The model's win probability of a board after the turn
# --------------------------------------------------------------------------


def wp_model(models: Path, fmt: str, groups: str):
    """v4's prediction as the Week 8 test opening used it: Reg M-A's model
    (recalibrated if it was), Reg M-B the pooled model with its temperature; or
    the averaged model, when `wpa.ensemble finish` has made one."""
    from wpa.ensemble import load_averaged
    from wpa.evaluate import _temperature, apply_temperature, use_recalibration
    from wpa.features import columns
    from wpa.model import load

    which = "pooled" if fmt == "regmb" else fmt
    d = Path(models) / which
    cols = columns(groups) + (["z_format_regmb"] if which == "pooled" else [])
    # the averaged model (Week 10, DEFINITIONS §10.2 revision 9) when there is
    # one: it carries its own Reg M-B temperature
    avg = load_averaged(Path(models), which, groups, cols)
    if avg is not None:
        model, temp = avg, None
    else:
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


def _board_key(
    p1: Sequence[Mapping], p2: Sequence[Mapping], fld, grid: float | None = None
) -> str:
    """A board's identity; with `grid`, hit points to the nearest cell of it."""

    def clean(side):
        out = []
        for m in side:
            d = {k: v for k, v in m.items() if not k.startswith("_")}
            if grid:
                d["hp_fraction"] = round(d["hp_fraction"] / grid)
            out.append(d)
        return out

    return json.dumps([clean(p1), clean(p2), fld.key()], sort_keys=True, default=str)


class BoardWP:
    """p1's win probability of a board the turn can end on: the decision's
    state with the new board and timers, at the next decision (after the turn
    if a Pokemon fell, else the next turn's start), from what was known at the
    decision (the turn's own end-of-turn observations left out).

    `same_point`: the board is valued as state `k` itself instead (a forced
    switch's boards, valued at the next turn's start they lead to).

    `budget` (Week 10 Task 7): at most this many boards valued at once. Over it,
    boards are grouped by hit points on a coarser grid (0.05, doubling) until
    the groups fit, and each group takes the value of its first board: nothing
    is dropped. The coarsest grid needed is kept in `grid`. Time per turn is
    almost all valuing boards (about 7 ms each in Week 9's run)."""

    def __init__(
        self,
        predict,
        states,
        k,
        joined,
        sheets,
        dex,
        table,
        groups,
        ctx,
        same_point: bool = False,
        budget: int | None = None,
    ) -> None:
        self.same_point = same_point
        self.budget = budget
        self.grid = 0.0
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

        board = {
            "our_pokemon": [dict(m) for m in ours],
            "opp_pokemon": [dict(m) for m in theirs],
            "observations": [],
        }
        if self.same_point:
            s = dict(self.s0, **board)
            rows = [*self.prior[: self.k], s]
        else:
            fell = sum(m["fainted"] for m in list(ours) + list(theirs)) > self.fell0
            s = dict(
                self.s0,
                **board,
                moment="after_turn" if fell else "turn_start",
                turn=self.turn if fell else self.turn + 1,
                decision_index=(self.s0["decision_index"] + 1) if fell else 0,
            )
            rows = [*self.prior, s]
        j = timers_for(fld, "p1", before=self.joined)
        f = state_features(
            rows,
            len(rows) - 1,
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
            groups = {key: [key] for key in todo}
            if self.budget is not None and len(todo) > self.budget:
                g = 0.05
                while True:
                    cells: dict[str, list[str]] = {}
                    for key, item in todo.items():
                        cells.setdefault(_board_key(*item, grid=g), []).append(key)
                    if len(cells) <= self.budget or g >= 0.5:
                        break
                    g *= 2
                groups = {ks[0]: ks for ks in cells.values()}
                self.grid = max(self.grid, g)
            X = np.array([self._row(*todo[k]) for k in groups], dtype=np.float32)
            for rep, p in zip(groups, self.predict(X)):
                for key in groups[rep]:
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


POINTS = ("turn_start", "after_turn")  # decision points that are split


def next_point(
    game, k: int, after_replacement: bool = False, role: str = "p1"
) -> tuple[str, int]:
    """The decision point after the one at `game.states[role][k]` (DEFINITIONS
    §2, Week 10 Task 6): the forced switch after a turn if either side must send
    a Pokemon in, else the next turn's start, else the end of the game (p1's
    terminal state). `after_replacement`: the forced switches after this turn
    passed over. As (role, index into `game.states[role]`): p1's state where p1
    decides, else p2's. A switching move's switch-in ("mid_turn") is part of the
    turn's choice (Task 3), not a point of its own."""
    s = game.states[role][k]
    pt0 = game.points[role][k]
    best = None
    for r in ("p1", "p2"):
        pts = game.points[r]
        for i, st in enumerate(game.states[r][: len(pts)]):
            if st["moment"] not in POINTS or pts[i] <= pt0:
                continue
            if (
                after_replacement
                and st["moment"] == "after_turn"
                and st["turn"] == s["turn"]
            ):
                continue
            cand = (pts[i], r != "p1", r, i)  # p1's state first at the same point
            if best is None or cand < best:
                best = cand
    if best is None:
        return "p1", len(game.states["p1"]) - 1
    return best[2], best[3]


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
    alternatives: int = 10
    # the forced-switch model (`wpa.replace_model`); without it forced switches
    # keep their WPs (so a game still chains) but are not split
    replace: Any = None
    # most boards valued at once per decision point (`BoardWP`); None: no limit
    budget: int | None = None
    # each player's typical choice (DEFINITIONS §3, revision 10); off only to
    # measure what it costs
    typical: bool = True
    # the lead model (`wpa.lead_model`); without it team preview keeps its WPs
    # (so a game still chains) but is not split
    leads: Any = None
    # move order from each Pokemon's spread belief (Week 11 Task 2); off only to
    # measure what it changes
    speed_beliefs: bool = True


@dataclass
class TurnSetup:
    """One turn of one game, ready to value: the resolver's values, both WPs
    from p1's side, and each player's options with the opponent model's chances.
    `after` is WP at the next decision point (DEFINITIONS §2); `after_board` is
    the turn's actual board valued as the resolver's boards are (a diagnostic:
    their difference is the model's, not the game's)."""

    base: dict
    turn: int
    tv: TurnValues
    bw: BoardWP
    before: float
    after: float
    actual: dict
    turns: dict  # role -> wpa.choices.Turn
    opts: dict  # role -> {Pokemon: options}
    chances: dict  # role -> {Pokemon: chances}
    t0: float
    after_board: float = float("nan")


@dataclass
class ReplacementSetup:
    """One forced switch of one game (both sides', when both replace), ready to
    value: the board after each pair of choices (`Resolver.replace`), valued at
    the next turn's start it leads to; both WPs from p1's side; each replacing
    side's options with the forced-switch model's chances."""

    base: dict
    turn: int
    tv: TurnValues
    bw: BoardWP
    before: float
    after: float
    actual: dict  # the board at the next turn's start
    taken: dict  # role -> {fainted: incoming}
    opts: dict  # role -> {slot: options}
    chances: dict  # role -> {slot: chances}
    t0: float


@dataclass
class PreviewSetup:
    """Team preview of one game (Week 11 Task 1), ready to value: the board at
    turn 1's start after each pair of leads (`Resolver.lead`), valued there;
    both WPs from p1's side; each side's 15 lead pairs with the lead model's
    chances. The back two are not scored: the model cannot see them."""

    base: dict
    tv: TurnValues
    bw: BoardWP
    before: float
    after: float
    actual: dict  # the board at turn 1's start
    taken: dict  # role -> joint (the leads)
    opts: dict  # role -> [joints]
    chances: dict  # role -> [chances]
    t0: float


def _error(base: dict, e: Exception) -> list[dict]:
    why = f"error: {type(e).__name__}: {str(e)[:80]}"
    return [dict(base, role=r, skipped=why) for r in ("p1", "p2")]


def _skipped(base: dict, why: str, before: float, after: float) -> list[dict]:
    """A decision point left out of the split, with its WPs kept (from each
    player's side) so the game still chains."""
    return [
        dict(base, role="p1", skipped=why, before=before, after=after),
        dict(base, role="p2", skipped=why, before=1 - before, after=1 - after),
    ]


def turn_setups(
    tag: str,
    log: str,
    fmt: str,
    tools: Tools,
    forced: bool = False,
    prev_leads: Mapping[str, frozenset[str]] | None = None,
):
    """Each decision point of one game: a TurnSetup for each turn, and with
    `forced` a PreviewSetup for team preview and a ReplacementSetup for each
    forced switch; or a list of records saying why a point is left out.
    `prev_leads`: each player's leads in the set's previous game (species)."""
    from wpa import choices as C
    from wpa import decisions as D
    from wpa import resolver as R
    from wpa.bring import brought_from_log
    from wpa.features import _field, columns, damage_contexts, state_features
    from wpa.policy_data import _timers_by_turn, game_tools, turn_options
    from wpa.state_timing import loser_has_pokemon_left

    dex, table = tools.dexes[fmt], tools.tables[fmt]
    sheets, spreads, odds = game_tools(tag, log, fmt, tools.store, tools.bring, dex)
    if set(sheets) != {"p1", "p2"}:
        return
    game = D.build_game(log, table)
    states, joined = game.states["p1"], game.joined["p1"]
    if not states or states[-1]["outcome"] is None:
        return
    ctx_all = damage_contexts(
        tag, log, game, sheets, dex, tools.calc, tools.store, tools.bring
    )
    ctxs = ctx_all["p1"]
    timers = {r: _timers_by_turn(game, r) for r in ("p1", "p2")}
    brought = brought_from_log(log)
    four = brought_four({r: brought.get(r, set()) for r in ("p1", "p2")})
    turns: dict[int, dict[str, C.Turn]] = {}
    for t in C.turns(log, dex):
        turns.setdefault(t.turn, {})[t.role] = t
    rates = (
        tools.policy.rates.get(fmt, {}) if isinstance(tools.policy.rates, dict) else {}
    )
    cols = columns(tools.groups)
    result = float(bool(states[-1]["outcome"]))
    wps: dict[tuple[str, int], float] = {}

    def wp_at(r: str, i: int) -> float:
        """p1's WP at a decision point: the model on that player's own row (one
        minus it for p2's), or the result at the end of the game."""
        if (r, i) not in wps:
            s = game.states[r][i]
            if s["moment"] == "terminal":
                v = result
            else:
                f = state_features(
                    game.states[r],
                    i,
                    r,
                    game.joined[r][i],
                    sheets,
                    dex,
                    table,
                    tools.groups,
                    ctx_all[r][i],
                )
                x = np.array([[f[c] for c in cols]], dtype=np.float32)
                v = float(tools.predict[fmt](x)[0])
                v = v if r == "p1" else 1.0 - v
            wps[(r, i)] = v
        return wps[(r, i)]

    def with_brought(sides: dict) -> dict:
        for r in ("p1", "p2"):
            for i in brought.get(r, ()):
                if i < len(sides[r]):
                    sides[r][i]["_brought"] = True
        return sides

    for k, s in enumerate(states[:-1]):
        if s["moment"] != "turn_start":
            continue
        base = {
            "tag": tag,
            "format": fmt,
            "turn": s["turn"],
            "kind": "turn",
            "point": game.points["p1"][k],
            "result": result,
        }
        tt = turns.get(s["turn"], {})
        if set(tt) != {"p1", "p2"}:
            try:
                yield _skipped(
                    base,
                    "choices not in the log",
                    wp_at("p1", k),
                    wp_at(*next_point(game, k)),
                )
            except Exception as e:  # pragma: no cover - reported, not hidden
                yield _error(base, e)
            continue
        end = end_of_turn(game, k)
        if end is None:
            continue
        if end[3] is not None and loser_has_pokemon_left(end[3]):
            yield [dict(base, role=r, skipped="forfeit or timer") for r in ("p1", "p2")]
            continue
        t0 = time.time()
        try:
            sides = with_brought(
                {
                    "p1": [dict(m) for m in s["our_pokemon"]],
                    "p2": [dict(m) for m in s["opp_pokemon"]],
                }
            )
            fld = R.field_from_timers(joined[k], "p1")
            rv = R.Resolver(
                dex,
                tools.moves[fmt],
                tools.calc,
                sheets,
                ctxs[k].spreads,
                resolution=tools.resolution,
                cap=tools.cap,
                dists=ctxs[k].dists if tools.speed_beliefs else None,
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
                budget=tools.budget,
            )
            before = wp_at("p1", k)
            after = wp_at(*next_point(game, k))
            a_p1, a_p2, a_j, _term = end
            after_board = float(
                bw.boards([(a_p1, a_p2, R.field_from_timers(a_j, "p1"))])[0]
            )
            opts, chances = {}, {}
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
                opts[r], chances[r] = only_brought(
                    *expand_pivots(
                        {i: o for i, (o, _X) in feats.items()},
                        {
                            i: list(tools.policy.chances(X))
                            for i, (_o, X) in feats.items()
                        },
                    ),
                    four[r],
                )
        except Exception as e:  # pragma: no cover - reported, not hidden
            yield _error(base, e)
            continue
        yield TurnSetup(
            base,
            s["turn"],
            TurnValues(rv, sides, fld, bw),
            bw,
            before,
            after,
            {"p1": a_p1, "p2": a_p2},
            tt,
            opts,
            chances,
            t0,
            after_board,
        )
    if not forced:
        return
    yield from _preview_setup(
        tag, log, fmt, tools, game, sheets, ctx_all, wp_at, with_brought, prev_leads
    )
    from wpa import replace_model as RM

    reps: dict[tuple[str, int], list] = {}
    for rep in C.replacements(log):
        reps.setdefault((rep.role, rep.turn), []).append(rep)
    at: dict[int, dict[str, int]] = {}  # point -> role -> its after-turn state
    for r in ("p1", "p2"):
        for i, st in enumerate(game.states[r][: len(game.points[r])]):
            if st["moment"] == "after_turn":
                at.setdefault(game.points[r][i], {})[r] = i
    nth: dict[tuple[str, int], int] = {}
    for pt in sorted(at):
        idx = at[pt]
        r0 = "p1" if "p1" in idx else "p2"
        i0 = idx[r0]
        s = game.states[r0][i0]
        t = s["turn"]
        base = {
            "tag": tag,
            "format": fmt,
            "turn": t,
            "kind": "replacement",
            "point": pt,
            "result": result,
        }
        mine = {}
        for r in idx:
            n = nth.get((r, t), 0)
            nth[(r, t)] = n + 1
            got = reps.get((r, t), [])
            if n < len(got):
                mine[r] = got[n]
        try:
            nr, ni = next_point(game, i0, role=r0)
            before, after = wp_at(r0, i0), wp_at(nr, ni)
        except Exception as e:  # pragma: no cover - reported, not hidden
            yield _error(base, e)
            continue
        if tools.replace is None:
            yield _skipped(base, "no forced-switch model", before, after)
            continue
        if not mine:
            yield _skipped(base, "forced switch not in the log", before, after)
            continue
        if nr != "p1" or game.states["p1"][ni]["moment"] != "turn_start":
            yield _skipped(base, "next point not a turn's start", before, after)
            continue
        t0 = time.time()
        try:
            ours, theirs = s["our_pokemon"], s["opp_pokemon"]
            if r0 == "p2":
                ours, theirs = theirs, ours
            sides = with_brought(
                {"p1": [dict(m) for m in ours], "p2": [dict(m) for m in theirs]}
            )
            fld = R.field_from_timers(game.joined[r0][i0], r0)
            rv = R.Resolver(
                dex,
                tools.moves[fmt],
                tools.calc,
                sheets,
                ctx_all[r0][i0].spreads,
                resolution=tools.resolution,
                cap=tools.cap,
            )
            bw = BoardWP(
                tools.predict[fmt],
                states,
                ni,
                joined[ni],
                sheets,
                dex,
                table,
                tools.groups,
                ctxs[ni],
                same_point=True,
                budget=tools.budget,
            )
            opts, chances, taken = {}, {}, {}
            for r, rep in mine.items():
                j = game.joined[r][idx[r]]
                got = RM.options(
                    rep,
                    sheets,
                    spreads,
                    dex,
                    tools.calc,
                    odds,
                    _field(j) if j else None,
                    four[r],
                )
                opts[r] = {slot: o for slot, (o, _X) in got.items()}
                chances[r] = {
                    slot: list(tools.replace.chances(X))
                    for slot, (_o, X) in got.items()
                }
                taken[r] = dict(rep.taken)
            nxt = states[ni]
            actual = {"p1": nxt["our_pokemon"], "p2": nxt["opp_pokemon"]}
        except Exception as e:  # pragma: no cover - reported, not hidden
            yield _error(base, e)
            continue
        yield ReplacementSetup(
            base,
            t,
            TurnValues(SwitchIns(rv), sides, fld, bw),
            bw,
            before,
            after,
            actual,
            taken,
            opts,
            chances,
            t0,
        )


def _preview_setup(
    tag, log, fmt, tools, game, sheets, ctx_all, wp_at, with_brought, prev_leads
):
    """Team preview's leads (Week 11 Task 1), as one decision point per game."""
    from wpa import resolver as R
    from wpa.bring import leads_from_log
    from wpa.lead_model import pairs

    states, joined = game.states["p1"], game.joined["p1"]
    k0 = next((k for k, s in enumerate(states) if s["moment"] == "preview"), None)
    if k0 is None or k0 >= len(game.points["p1"]):
        return
    base = {
        "tag": tag,
        "format": fmt,
        "turn": 0,
        "kind": "preview",
        "point": game.points["p1"][k0],
        "result": float(bool(states[-1]["outcome"])),
    }
    try:
        nr, k1 = next_point(game, k0)
        before, after = wp_at("p1", k0), wp_at(nr, k1)
    except Exception as e:  # pragma: no cover - reported, not hidden
        yield _error(base, e)
        return
    leads = leads_from_log(log)
    if tools.leads is None:
        yield _skipped(base, "no lead model", before, after)
        return
    if (
        nr != "p1"
        or states[k1]["moment"] != "turn_start"
        or any(len(sheets[r]) != 6 or len(leads.get(r, ())) != 2 for r in ("p1", "p2"))
    ):
        yield _skipped(base, "team preview not in the log", before, after)
        return
    t0 = time.time()
    try:
        s = states[k0]
        sides = with_brought(
            {
                "p1": [dict(m) for m in s["our_pokemon"]],
                "p2": [dict(m) for m in s["opp_pokemon"]],
            }
        )
        rv = R.Resolver(
            tools.dexes[fmt],
            tools.moves[fmt],
            tools.calc,
            sheets,
            ctx_all["p1"][k0].spreads,
            resolution=tools.resolution,
            cap=tools.cap,
        )
        bw = BoardWP(
            tools.predict[fmt],
            states,
            k1,
            joined[k1],
            sheets,
            tools.dexes[fmt],
            tools.tables[fmt],
            tools.groups,
            ctx_all["p1"][k1],
            same_point=True,
            budget=tools.budget,
        )
        opts, chances, taken = {}, {}, {}
        for r in ("p1", "p2"):
            prev = (prev_leads or {}).get(r)
            opts[r] = [lead_joint(p) for p in pairs(6)]
            chances[r] = list(tools.leads.chances(sheets[r], fmt, prev))
            taken[r] = lead_joint(sorted(leads[r]))
        nxt = states[k1]
        actual = {"p1": nxt["our_pokemon"], "p2": nxt["opp_pokemon"]}
    except Exception as e:  # pragma: no cover - reported, not hidden
        yield _error(base, e)
        return
    yield PreviewSetup(
        base,
        TurnValues(Leads(rv), sides, R.field_from_timers(joined[k0], "p1"), bw),
        bw,
        before,
        after,
        actual,
        taken,
        opts,
        chances,
        t0,
    )


def _analyse_preview(ps: PreviewSetup, tools: Tools) -> list[dict]:
    """Team preview's leads split as a turn is (DEFINITIONS §3): your choice
    against the typical pair, the position, their decision against their likely
    pairs, and the dice (nothing is random at team preview: only the model's
    own difference between a board and the next row)."""
    tv = ps.tv
    mixes = {r: list(zip(ps.opts[r], ps.chances[r])) for r in ("p1", "p2")}
    tv.prepare([(x, y) for x, _ in mixes["p1"] for y, _ in mixes["p2"]])
    t1, t2 = ps.taken["p1"], ps.taken["p2"]
    board = tv(t1, t2)
    recs = []
    for r, other in (("p1", "p2"), ("p2", "p1")):
        b, a = (ps.before, ps.after) if r == "p1" else (1 - ps.before, 1 - ps.after)
        sp = decompose(
            tv.for_role(r),
            b,
            a,
            [(ps.taken[r], 1.0)],
            [(ps.taken[other], 1.0)],
            mixes[other],
            [[(j, 1.0)] for j, _ in mixes[r]],
            typical=mixes[r],
        )
        recs.append(
            dict(
                ps.base,
                role=r,
                unknown=0,
                choices=len(mixes[r]),
                after_board=board if r == "p1" else 1 - board,
                **asdict(sp),
            )
        )
    outs = tv.outcomes.get((t1, t2), [])
    tol = max(0.03, tools.resolution + 0.01)
    found = any(_close(o.sides, ps.actual, tol) for o in outs)
    partial = sorted(set().union(*(o.partial for o in outs))) if outs else []
    secs = time.time() - ps.t0
    for rec in recs:
        rec.update(
            found=found,
            partial=partial,
            seconds=secs,
            resolves=len(tv.outcomes),
            boards=len(ps.bw._cache),
        )
    return recs


def analyse_game(
    tag: str,
    log: str,
    fmt: str,
    tools: Tools,
    with_alternatives: bool = True,
    prev_leads: Mapping[str, frozenset[str]] | None = None,
) -> list[dict]:
    """One record per decision point (team preview, each turn and each forced
    switch, each player) of one game."""
    out: list[dict] = []
    for ts in turn_setups(tag, log, fmt, tools, forced=True, prev_leads=prev_leads):
        if isinstance(ts, list):
            out += ts
            continue
        try:
            if isinstance(ts, PreviewSetup):
                out += _analyse_preview(ts, tools)
            elif isinstance(ts, ReplacementSetup):
                out += _analyse_replacement(ts, tools)
            else:
                out += _analyse_turn(ts, tools, with_alternatives)
        except Exception as e:  # pragma: no cover - reported, not hidden
            out += _error(ts.base, e)
    return out


def _analyse_turn(ts: TurnSetup, tools: Tools, with_alternatives: bool) -> list[dict]:
    tv = ts.tv
    mixes = {}
    for r in ("p1", "p2"):
        t, opts, ch = ts.turns[r], ts.opts[r], ts.chances[r]
        taken = taken_mixture(t.taken, t.hidden, opts, ch)
        full = mixture({i: list(zip(opts[i], ch[i])) for i in opts})
        seed = f"{ts.base['tag']} {ts.turn} {r}"
        lk, kept = likely(full, tools.top, tools.draws, seed)
        alts = None
        if with_alternatives and tools.alternatives:
            top, _ = trim(full, 1.0, tools.alternatives)
            alts = [[(j, 1.0)] for j, _ in top]
            if not (len(taken) == 1 and any(taken[0][0] == j for j, _ in top)):
                alts.append(taken)
        unknown = sum(
            1 for i in opts if not isinstance(t.taken.get(i), Action) or i in t.hidden
        )
        mixes[r] = (taken, lk, kept, alts, unknown)
    t1, l1, _k1, alts1, _u1 = mixes["p1"]
    t2, l2, _k2, alts2, _u2 = mixes["p2"]
    pairs = [(x, y) for x, _ in t1 for y, _ in l2 + t2]
    pairs += [(x, y) for x, _ in l1 for y, _ in t2]
    # each player's typical choice against the other's likely replies
    # (DEFINITIONS §3, revision 10): one block serves both players
    if tools.typical:
        pairs += [(x, y) for x, _ in l1 for y, _ in l2]
    for alt in alts1 or ():
        pairs += [(x, y) for x, _ in alt for y, _ in l2]
    for alt in alts2 or ():
        pairs += [(x, y) for x, _ in l1 for y, _ in alt]
    tv.prepare(pairs)
    recs = []
    for r, other in (("p1", "p2"), ("p2", "p1")):
        taken, _l, _k, alts, unknown = mixes[r]
        _t, lk, kept, _a, _u = mixes[other]
        b, a = (ts.before, ts.after) if r == "p1" else (1 - ts.before, 1 - ts.after)
        sp = decompose(
            tv.for_role(r),
            b,
            a,
            taken,
            mixes[other][0],
            lk,
            alts,
            kept,
            typical=mixes[r][1] if tools.typical else None,
        )
        board = ts.after_board if r == "p1" else 1 - ts.after_board
        recs.append(
            dict(ts.base, role=r, unknown=unknown, after_board=board, **asdict(sp))
        )
    pairs = [(x, y) for x, _ in t1 for y, _ in t2]
    outs = [o for key in pairs for o in tv.outcomes.get(key, ())]
    tol = max(0.03, tools.resolution + 0.01)
    found = any(_close(o.sides, ts.actual, tol) for o in outs)
    partial = sorted(set().union(*(o.partial for o in outs))) if outs else []
    secs = time.time() - ts.t0
    for rec in recs:
        rec.update(
            found=found,
            partial=partial,
            seconds=secs,
            resolves=len(tv.outcomes),
            boards=len(ts.bw._cache),
            valued_grid=ts.bw.grid,
        )
    return recs


def _analyse_replacement(rs: ReplacementSetup, tools: Tools) -> list[dict]:
    """A forced switch split as a turn is (DEFINITIONS §3): your decision and
    theirs (0 when only you replace), the dice whatever is random on entry and
    the model's own difference between the board and the next turn's row."""
    tv = rs.tv
    none: Mix = [((), 1.0)]
    mixes: dict[str, tuple[Mix, Mix, list[Mix] | None]] = {}
    for r in ("p1", "p2"):
        opts = rs.opts.get(r)
        if not opts:
            mixes[r] = (none, none, None)
            continue
        keys = sorted(opts)
        ch = rs.chances[r]
        taken = tuple(
            Action(i, "switch", switch_to=rs.taken[r][i])
            for i in keys
            if i in rs.taken[r]
        )
        full = mixture({i: list(zip(opts[i], ch[i])) for i in keys})
        mixes[r] = ([(taken, 1.0)], full, [[(j, 1.0)] for j, _ in full])
    one = [x for x, _ in [*mixes["p1"][0], *mixes["p1"][1]]]
    two = [y for y, _ in [*mixes["p2"][0], *mixes["p2"][1]]]
    tv.prepare([(x, y) for x in dict.fromkeys(one) for y in dict.fromkeys(two)])
    t1, t2 = mixes["p1"][0][0][0], mixes["p2"][0][0][0]
    board = tv(t1, t2)
    recs = []
    for r, other in (("p1", "p2"), ("p2", "p1")):
        taken, _full, alts = mixes[r]
        b, a = (rs.before, rs.after) if r == "p1" else (1 - rs.before, 1 - rs.after)
        sp = decompose(
            tv.for_role(r),
            b,
            a,
            taken,
            mixes[other][0],
            mixes[other][1],
            alts,
            typical=mixes[r][1],
        )
        recs.append(
            dict(
                rs.base,
                role=r,
                unknown=0,
                replacing=r in rs.opts,
                choices=len(mixes[r][1]) if r in rs.opts else 0,
                after_board=board if r == "p1" else 1 - board,
                **asdict(sp),
            )
        )
    outs = tv.outcomes.get((t1, t2), [])
    tol = max(0.03, tools.resolution + 0.01)
    found = any(_close(o.sides, rs.actual, tol) for o in outs)
    partial = sorted(set().union(*(o.partial for o in outs))) if outs else []
    secs = time.time() - rs.t0
    for rec in recs:
        rec.update(
            found=found,
            partial=partial,
            seconds=secs,
            resolves=len(tv.outcomes),
            boards=len(rs.bw._cache),
        )
    return recs


def sharp_samples(
    tag: str, log: str, fmt: str, tools: Tools, most: int = 150
) -> list[SharpSample]:
    """For fitting the sharpness: at each turn, for each player whose choice the
    log shows in full, E[WP | that choice, each reply] over the opponent's replies
    (the likeliest `most`), with each reply's chance at sharpness 1."""
    out: list[SharpSample] = []
    for ts in turn_setups(tag, log, fmt, tools):
        if not isinstance(ts, TurnSetup):
            continue
        try:
            want = {}
            for r, other in (("p1", "p2"), ("p2", "p1")):
                t, opts = ts.turns[r], ts.opts[r]
                if not opts or any(
                    not isinstance(t.taken.get(i), Action) or i in t.hidden
                    for i in opts
                ):
                    continue
                taken = taken_mixture(t.taken, t.hidden, opts, ts.chances[r])
                o_opts, o_ch = ts.opts[other], ts.chances[other]
                full = mixture({i: list(zip(o_opts[i], o_ch[i])) for i in o_opts})
                top = sorted(full, key=lambda x: -x[1])[:most]
                want[r] = (taken[0][0], top)
            pairs = []
            for r, (c, top) in want.items():
                pairs += [(c, j) if r == "p1" else (j, c) for j, _ in top]
            ts.tv.prepare(pairs)
            for r, (c, top) in want.items():
                v = ts.tv.for_role(r)
                before = ts.before if r == "p1" else 1 - ts.before
                out.append(
                    SharpSample(before, [p for _, p in top], [v(c, j) for j, _ in top])
                )
        except Exception:  # pragma: no cover - a turn left out of the fit
            continue
    return out


# --------------------------------------------------------------------------
# The run and the report
# --------------------------------------------------------------------------


def sample_sets(
    logs: Path,
    splits: Mapping[str, str],
    sets: Mapping[str, int],
    split: str = "validation",
) -> dict[str, list[tuple[str, str]]]:
    """A fixed sample of sets per format from `split` (by a hash of the set id,
    so the same sets every run), with all their games. Never the test split."""
    if split == "test":
        raise ValueError("the test split is never read here")
    import hashlib

    from wpa.features import unit_of
    from wpa.formats import format_of
    from wpa.policy_data import _iter_logs

    by_unit: dict[str, dict[str, list]] = {f: {} for f in sets}
    for tag, log in _iter_logs(logs):
        if splits.get(tag) != split:
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
    tools.budget = getattr(a, "budget", None) or None
    tools.typical = not getattr(a, "no_typical", False)
    tools.speed_beliefs = not getattr(a, "no_speed_beliefs", False)
    if getattr(a, "leads", None) and Path(a.leads).exists():
        from wpa.lead_model import LeadModel

        tools.leads = LeadModel.load(a.leads)
    if getattr(a, "replace", None) and Path(a.replace).exists():
        from wpa.replace_model import ReplaceModel

        tools.replace = ReplaceModel.load(a.replace)
    # one thread for the model, set once it is loaded (its thread pool comes
    # with it): on small batches the pool costs seconds per call
    from threadpoolctl import threadpool_limits

    threadpool_limits(1)
    return tools


_W: dict = {}


def _init(a) -> None:  # pragma: no cover
    _W["tools"] = _tools(a)
    if getattr(a, "fit_sharpness", False):
        _W["tools"].policy.sharpness = 1.0  # the fit starts from the plain model


def _one_sharp(job) -> list[SharpSample]:  # pragma: no cover
    tag, log, fmt, _alt = job
    return sharp_samples(tag, log, fmt, _W["tools"])


def fit_run(a) -> None:  # pragma: no cover - runs on the corpus
    """Fit the opponent model's sharpness on training sets (PO decision, 6 Nov)
    and save it into the policy file."""
    from multiprocessing import Pool

    from wpa.policy import PolicyModel

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    games = sample_sets(
        a.logs, splits, {"regma": a.sets[0], "regmb": a.sets[1]}, split="train"
    )
    jobs = [(tag, log, fmt, False) for fmt, gs in games.items() for tag, log in gs]
    print(f"{len(jobs)} training games", flush=True)
    samples: list[SharpSample] = []
    with Pool(a.workers, _init, (a,)) as pool:
        for i, got in enumerate(pool.imap_unordered(_one_sharp, jobs), 1):
            samples += got
            if i % 5 == 0:
                print(
                    f"{i}/{len(jobs)} games, {len(samples)} decision points", flush=True
                )
    fitted, curve = fit_sharpness(samples)
    # the PO's chosen setting, when given (6 Nov: 4; zero is out of reach)
    b = a.sharpness if a.sharpness is not None else fitted
    model = PolicyModel.load(a.policy)
    plain = mean_yours(samples, 1.0)
    model.sharpness = b
    model.save(a.policy)
    lines = [
        "Opponent model sharpness (PO decision, 6 Nov 2026), fitted on training sets",
        f"  {len(jobs)} games, {len(samples)} decision points",
        f"  your decision on average: {100 * plain:+.1f} points at sharpness 1",
        f"  closest to zero: sharpness {fitted:.2f}, "
        f"{100 * mean_yours(samples, fitted):+.1f} points",
        f"  saved: sharpness {b:.2f}, {100 * mean_yours(samples, b):+.1f} points",
        "  the curve (sharpness: your decision on average, points):",
    ]
    lines += [f"    {x:.2f}: {100 * m:+.1f}" for x, m in curve[::4]]
    text = "\n".join(lines)
    print(text)
    Path(a.policy).with_name("policy_sharpness.txt").write_text(
        text + "\n", encoding="utf-8"
    )


def _one(job) -> list[dict]:  # pragma: no cover
    tag, log, fmt, alt, prev = job
    t0 = time.time()
    recs = analyse_game(tag, log, fmt, _W["tools"], alt, prev)
    for r in recs:
        r["game_seconds"] = time.time() - t0
    return recs


def previous_leads(
    games: Sequence[tuple[str, str]],
) -> dict[str, dict[str, frozenset[str]]]:
    """For each game, each player's leads (species) in the set's previous game,
    from games in set order (as `sample_sets` gives them)."""
    from wpa.bring import leads_from_log, players
    from wpa.features import unit_of
    from wpa.team_sheets import sheets_from_log, to_id

    memory: dict[tuple[str, str], frozenset[str]] = {}
    out: dict[str, dict[str, frozenset[str]]] = {}
    for tag, log in games:
        unit, _n = unit_of(tag, log)
        names, sheets, leads = players(log), sheets_from_log(log), leads_from_log(log)
        here = {}
        for role, sheet in sheets.items():
            name = names.get(role, role)
            if (unit, name) in memory:
                here[role] = memory[(unit, name)]
            lead = leads.get(role, frozenset())
            if len(lead) == 2:
                memory[(unit, name)] = frozenset(to_id(sheet[i].species) for i in lead)
        out[tag] = here
    return out


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
        prev = previous_leads(gs)
        for n, (tag, log) in enumerate(gs[:cap] if cap else gs):
            if tag not in done:
                jobs.append(
                    (tag, log, fmt, n % a.alternatives_every == 0, prev.get(tag, {}))
                )
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


def _turn_line(pair: Mapping[str, Mapping]) -> str:
    """One turn, both players: p1's swing, then each player's split."""

    def pt(x: float) -> str:
        return f"{100 * x:+.0f}"

    r1 = pair.get("p1") or pair["p2"]
    sw = r1["after"] - r1["before"] if "p1" in pair else r1["before"] - r1["after"]
    text = f"    {REPLAY}{r1['tag']} turn {r1['turn']}: p1 {pt(sw)}"
    for role in ("p1", "p2"):
        r = pair.get(role)
        if r is None:
            continue
        if r.get("choice") is not None:
            text += (
                f"; {role} choice {pt(r['choice'])}, position {pt(r['position'])}, "
                f"theirs {pt(r['theirs'])}, dice {pt(r['dice'])}"
            )
            if r.get("vs_best") is not None:
                text += f" (vs best {pt(r['vs_best'])})"
            continue
        text += (
            f"; {role} yours {pt(r['yours'])}, theirs {pt(r['theirs'])}, "
            f"dice {pt(r['dice'])}"
        )
        if r.get("vs_best") is not None:
            text += f" (vs best {pt(r['vs_best'])}, vs average {pt(r['vs_average'])})"
    if not r1["found"]:
        text += "; the board that happened is not among the resolver's"
    if r1.get("partial"):
        text += "; partly modelled: " + ", ".join(_reason(x) for x in r1["partial"])
    return text


def _reason(code: str) -> str:
    """A resolver reason in plain words: "move:leechseed" -> "leechseed",
    "power:lastrespects" -> "lastrespects power"."""
    kind, _, what = code.partition(":")
    if not what:
        return code
    return f"{what} power" if kind == "power" else what


BIG = 0.40  # a swing over 40 points, for the table by cause
THRESHOLD = 0.03  # DEFINITIONS §10.2, revision 9: 3 points


def _by_cause(turns: Mapping) -> list[str]:
    """Turns with a swing over 40 points, by cause (Week 9's table, kept each
    week so progress can be compared), with the commonest reasons."""
    big = []
    for d in turns.values():
        r = next(iter(d.values()))
        if abs(r["after"] - r["before"]) > BIG:
            big.append(r)
    cause: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for r in big:
        key = ("found, " if r["found"] else "not found, ") + (
            "partly modelled" if r.get("partial") else "fully modelled"
        )
        cause[key] = cause.get(key, 0) + 1
        for x in r.get("partial") or ():
            reasons[_reason(x)] = reasons.get(_reason(x), 0) + 1
    order = (
        "found, fully modelled",
        "found, partly modelled",
        "not found, partly modelled",
        "not found, fully modelled",
    )
    lines = [
        f"  turns with a swing over 40 points: {len(big)}; "
        + "; ".join(f"{k} {cause.get(k, 0)}" for k in order)
    ]
    if reasons:
        top = sorted(reasons.items(), key=lambda x: -x[1])[:8]
        lines.append("    commonest reasons: " + ", ".join(f"{k} {n}" for k, n in top))
    return lines


def _format_lines(name: str, rs: Sequence[Mapping], top: int) -> list[str]:
    games = len({r["tag"] for r in rs})
    every = rs
    rs = [r for r in rs if r.get("kind", "turn") == "turn"]
    ok = [r for r in rs if "skipped" not in r]
    if not ok:
        return []
    skipped: dict[str, int] = {}
    for r in rs:
        if "skipped" in r:
            key = r["skipped"].split(":")[0]
            skipped[key] = skipped.get(key, 0) + 1
    split = _has_split(ok)
    parts = ("choice", "position", "theirs", "dice") if split else PARTS8
    err = max(abs(sum(r[k] for k in parts) - (r["after"] - r["before"])) for r in ok)
    turns = {(r["tag"], r["turn"]): r["seconds"] for r in ok}
    secs = np.array(list(turns.values()))
    head = f"{name}: {games} games, {len(ok)} decision points ({len(turns)} turns)"
    if skipped:
        head += f"; left out: {skipped}"
    lines = [
        head,
        f"  swing (after - before): {_pts([r['after'] - r['before'] for r in ok])}",
    ]
    if split:
        lines += [
            "  your choice (against the typical choice): "
            f"{_pts([r['choice'] for r in ok])}",
            f"  the position (credited to no one): {_pts([r['position'] for r in ok])}",
        ]
    else:
        lines.append(f"  your decision: {_pts([r['yours'] for r in ok])}")
    lines += [
        f"  their decision: {_pts([r['theirs'] for r in ok])}",
        f"  the dice: {_pts([r['dice'] for r in ok])}",
    ]
    if split:
        lines.append(
            "  your decision (revision 8: your choice + the position): "
            f"{_pts([r['yours'] for r in ok])}"
        )
    lines += [
        f"  the parts add up: largest error {err:.2e} (allowed 1e-3)",
        "  a part of 3 points or more (the reporting threshold): "
        + ", ".join(
            f"{PART_NAMES[k]} "
            f"{100 * np.mean([abs(r[k]) >= THRESHOLD for r in ok]):.0f}%"
            for k in parts
        ),
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
            f"  cost vs average{' (unweighted, as in Weeks 9 and 10)' if split else ''}"
            f": mean {100 * va.mean():+.1f} points",
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
        f"  the {top} biggest swings (points; p1's swing, then each player's split):",
    ]
    turns_: dict = {}
    for r in ok:
        turns_.setdefault((r["tag"], r["turn"]), {})[r["role"]] = r
    lines[-2:-2] = _by_cause(turns_)
    big = sorted(
        turns_.values(),
        key=lambda d: -abs(
            next(iter(d.values()))["after"] - next(iter(d.values()))["before"]
        ),
    )[:top]
    lines += [_turn_line(d) for d in big] + [""]
    if split:
        lines.append(f"  the {top} biggest choices (points; by your choice):")
        lines += [
            _choice_line(r) for r in sorted(ok, key=lambda r: -abs(r["choice"]))[:top]
        ]
        lines.append("")
    return (
        lines
        + _preview_lines(every, top)
        + _forced_lines(every, top)
        + _chain_lines(every)
    )


def _preview_lines(rs: Sequence[Mapping], top: int) -> list[str]:
    """Team preview's leads (Week 11 Task 1): the split and the biggest choices."""
    pv = [r for r in rs if r.get("kind") == "preview"]
    ok = [r for r in pv if "skipped" not in r]
    if not pv:
        return []
    skipped: dict[str, int] = {}
    for r in pv:
        if "skipped" in r and r["role"] == "p1":
            key = r["skipped"].split(":")[0]
            skipped[key] = skipped.get(key, 0) + 1
    head = (
        f"  team preview (the leads): {len({r['tag'] for r in pv})} games, "
        f"{len(ok)} decisions"
    )
    if skipped:
        head += f"; left out: {skipped}"
    lines = [head]
    if ok and _has_split(ok):
        vb = np.array([r["vs_best"] for r in ok if r.get("vs_best") is not None])
        lines += [
            "    your choice (against the typical pair): "
            f"{_pts([r['choice'] for r in ok])}",
            "    the position (credited to no one): "
            f"{_pts([r['position'] for r in ok])}",
            f"    their decision: {_pts([r['theirs'] for r in ok])}",
            f"    the dice: {_pts([r['dice'] for r in ok])}",
        ]
        if len(vb):
            lines.append(
                f"    cost vs best: mean {100 * vb.mean():.1f} points; best pair led "
                f"{100 * np.mean(vb > -1e-9):.0f}%"
            )
        lines.append(f"    the {top} biggest team-preview choices (points):")
        lines += [
            _choice_line(r) for r in sorted(ok, key=lambda r: -abs(r["choice"]))[:top]
        ]
    return lines + [""]


PARTS8 = ("yours", "theirs", "dice")
PART_NAMES = {
    "yours": "yours",
    "choice": "choice",
    "position": "position",
    "theirs": "theirs",
    "dice": "dice",
}


def _has_split(rs: Sequence[Mapping]) -> bool:
    """Whether the records carry revision 10's split (Week 11 on)."""
    return bool(rs) and all(r.get("choice") is not None for r in rs)


def _choice_line(r: Mapping) -> str:
    def pt(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:+.0f}"

    kind = r.get("kind", "turn")
    where = (
        f"turn {r['turn']}"
        if kind == "turn"
        else "team preview"
        if kind == "preview"
        else f"after turn {r['turn']}"
    )
    text = (
        f"    {REPLAY}{r['tag']} {where}: {r['role']} choice {pt(r['choice'])}, "
        f"position {pt(r['position'])}, theirs {pt(r['theirs'])}, dice {pt(r['dice'])}"
    )
    if r.get("vs_best") is not None:
        text += f" (vs best {pt(r['vs_best'])})"
    return text


def _forced_lines(rs: Sequence[Mapping], top: int) -> list[str]:
    """Forced switches (Week 10 Task 6): the split of the player replacing, and
    the biggest decisions."""
    reps = [r for r in rs if r.get("kind") == "replacement"]
    if not reps:
        return []

    def pt(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:+.0f}"

    skipped: dict[str, int] = {}
    for r in reps:
        if "skipped" in r and r["role"] == "p1":
            key = r["skipped"].split(":")[0]
            skipped[key] = skipped.get(key, 0) + 1
    mine = [r for r in reps if "skipped" not in r and r.get("replacing")]
    head = (
        f"  forced switches: {len({(r['tag'], r.get('point')) for r in reps})} "
        f"({len(mine)} decisions by the player replacing)"
    )
    if skipped:
        head += f"; left out: {skipped}"
    lines = [head]
    if mine:
        alt = [r for r in mine if r.get("vs_best") is not None]
        vb = np.array([r["vs_best"] for r in alt]) if alt else np.zeros(1)
        split = _has_split(mine)
        parts = ("choice", "position", "theirs", "dice") if split else PARTS8
        if split:
            lines += [
                "    your choice (against the typical choice): "
                f"{_pts([r['choice'] for r in mine])}",
                "    the position (credited to no one): "
                f"{_pts([r['position'] for r in mine])}",
            ]
        else:
            lines.append(f"    your decision: {_pts([r['yours'] for r in mine])}")
        lines += [
            f"    their decision (0 unless both replace): "
            f"{_pts([r['theirs'] for r in mine])}",
            f"    the dice: {_pts([r['dice'] for r in mine])}",
            f"    cost vs best: mean {100 * vb.mean():.1f} points; best choice taken "
            f"{100 * np.mean(vb > -1e-9):.0f}%",
            "    a part of 3 points or more: "
            + ", ".join(
                f"{PART_NAMES[k]} "
                f"{100 * np.mean([abs(r[k]) >= THRESHOLD for r in mine]):.0f}%"
                for k in parts
            ),
            f"    the {top} biggest forced-switch "
            f"{'choices' if split else 'decisions'} (points):",
        ]
        key = "choice" if split else "yours"
        big = sorted(mine, key=lambda r: -abs(r[key]))[:top]
        for r in big:
            head = f"      {REPLAY}{r['tag']} after turn {r['turn']}: {r['role']} "
            if split:
                head += f"choice {pt(r['choice'])}, position {pt(r['position'])}"
            else:
                head += f"yours {pt(r['yours'])}"
            lines.append(
                head + f", vs best {pt(r.get('vs_best'))}, dice {pt(r['dice'])}"
                f" ({r.get('choices', 0)} choices)"
            )
    return lines + [""]


def _chain_lines(rs: Sequence[Mapping]) -> list[str]:
    """DEFINITIONS §2 on every game (Week 10 Task 6), and how far the next
    point's WP is from the board as the resolver's boards are valued."""
    if not any("point" in r for r in rs):
        return []
    results = {r["tag"]: r["result"] for r in rs if "result" in r}
    cs = [c for c in chains(rs, results) if not c["forfeit"]]
    if not cs:
        return []
    lines = [
        f"  games whose decision points chain: {sum(c['chained'] for c in cs)} of "
        f"{len(cs)}; whose swings add up to the result: "
        f"{sum(c['adds_up'] for c in cs)} of {len(cs)} (within 0.001; "
        "games with no forfeit or timer)"
    ]
    gaps = [
        abs(r["after"] - r["after_board"])
        for r in rs
        if r.get("role") == "p1"
        and "skipped" not in r
        and r.get("after_board") is not None
        and r.get("kind", "turn") == "turn"
    ]
    if gaps:
        g = np.array(gaps)
        lines.append(
            "  WP at the next point vs the turn's board as the resolver's are "
            f"valued: median {100 * np.median(g):.1f} points, within 0.1 point "
            f"{100 * np.mean(g <= 0.001):.0f}% (in the dice)"
        )
    return lines + [""]


def report(path: Path, top: int = 10) -> str:
    """The Week 9 first look: per format, the parts, both costs, the checks,
    the time, and the biggest swings with their replay links."""
    text = Path(path).read_text(encoding="utf-8")
    recs = [json.loads(x) for x in text.splitlines() if x.strip()]
    lines = ["Decision versus luck (DEFINITIONS §3 and §4)", ""]
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
    p.add_argument(
        "--replace",
        type=Path,
        default=Path("models_v4/replace.json"),
        help="the forced-switch model (Week 10 Task 6); without it, not split",
    )
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
    p.add_argument(
        "--leads",
        type=Path,
        default=Path("models_v4/leads.json"),
        help="the lead model (Week 11 Task 1); without it, team preview not split",
    )
    p.add_argument(
        "--no-speed-beliefs",
        action="store_true",
        help="move order from the likeliest spreads only (Week 10); only to "
        "measure what the spread beliefs change",
    )
    p.add_argument(
        "--no-typical",
        action="store_true",
        help="leave out each player's typical choice (revision 8's split); "
        "only to measure what it costs",
    )
    p.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="most boards valued per decision point; over it, a coarser grid "
        "(0 for no limit)",
    )
    p.add_argument("--cap", type=int, default=300)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out", type=Path, default=Path("reports/attribution.jsonl"))
    p.add_argument("--report", action="store_true", help="summarise --out and stop")
    p.add_argument(
        "--fit-sharpness",
        action="store_true",
        help="fit the opponent model sharpness on training sets, into --policy",
    )
    p.add_argument(
        "--sharpness",
        type=float,
        default=None,
        help="with --fit-sharpness: save this setting instead of the fitted one",
    )
    a = p.parse_args()
    if a.fit_sharpness:
        fit_run(a)
        return
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
    "ReplacementSetup",
    "SharpSample",
    "SwitchIns",
    "TurnSetup",
    "Split",
    "TurnValues",
    "analyse_game",
    "brought_four",
    "chains",
    "decompose",
    "expand_pivots",
    "expected",
    "fit_sharpness",
    "likely",
    "mean_yours",
    "mixture",
    "next_point",
    "only_brought",
    "sharp_samples",
    "report",
    "taken_mixture",
    "trim",
    "wp_model",
]
