"""Metric harness (Week 4 Task 4): Brier, calibration, symmetry, terminal,
trend, expert-claim cases, all per format.

Metrics are tests with thresholds (docs/WEEK4-DISPATCH.md Task 4). This module
is the measuring instrument; Task 5 points it at the v0 baseline. It uses the
standard library only, and works on any object with the BattleState fields it
reads (`our_pokemon`, `opp_pokemon`, `outcome`, ...), so it runs without the
project's ML dependencies. `StateView` is the light stand-in the loader
builds; a test checks it against the real BattleState schema where
`poke_env` is installed.

Conventions
-----------
* A prediction is WP_public for the side being analysed, in [0, 1].
* A state's label is its game's FINAL outcome from that side's perspective.
  The corpus stores an outcome only on a game's last state, so the loader
  labels every earlier state of the game with it. Games that never reach a
  decided last state are incomplete (DEFINITIONS section 9): dropped and
  counted, never scored.
* Decided states (the game is already over: outcome is True or False) are
  scored exactly by the terminal check, so they are set aside from the
  headline Brier, calibration and trend. Left in, they flatter every
  predictor: on the real validation data a coin flip that is exact once the
  game is over scores skill +0.097 only because ~5% of states are decided.
  The all-states Brier is still reported, labelled as including them.
* n counts states, not independent games. States within one game are
  correlated, so the effective sample is smaller than n; the report always
  prints the number of games next to it.
* Everything is reported per format (DEFINITIONS section 15). The pooled
  figure is a labelled secondary and is printed last.
* There is deliberately NO monotonicity gate (see tests/test_metrics.py).
  The number of Pokemon remaining is a reported trend only.
* BRING_SIZE is format configuration (section 12.5). hp_fraction is 0.0 for
  every Pokemon that is not on the field, including the two never brought,
  and the state does not say which two were left home, so "remaining" is
  BRING_SIZE minus the fainted count, never six minus it.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from wpa.formats import format_of, parse_state_filename

BRING_SIZE = 4
COIN_FLIP_BRIER = 0.25
SPLIT_NAMES = ("train", "validation", "test")

# --------------------------------------------------------------------------
# Light state view
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PokemonView:
    species: str
    hp_fraction: float
    fainted: bool
    active: bool
    gimmick: str | None = None


@dataclass(frozen=True)
class StateView:
    turn: int
    our_pokemon: tuple[PokemonView, ...]
    opp_pokemon: tuple[PokemonView, ...]
    outcome: bool | None
    set_id: str | None = None
    game_index: int | None = None
    set_score_entering_game: tuple[int, int] | None = None
    decision_index: int = 0


def state_from_dict(d: dict) -> StateView:
    """Build a StateView from a wpa_states record (BattleState.to_dict())."""
    score = d.get("set_score_entering_game")
    return StateView(
        turn=d["turn"],
        our_pokemon=tuple(PokemonView(**p) for p in d["our_pokemon"]),
        opp_pokemon=tuple(PokemonView(**p) for p in d["opp_pokemon"]),
        outcome=d["outcome"],
        set_id=d.get("set_id"),
        game_index=d.get("game_index"),
        set_score_entering_game=tuple(score) if score is not None else None,
        decision_index=d.get("decision_index", 0),
    )


Predictor = Callable[[object], float]


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------


def _check_pred(p) -> float:
    if isinstance(p, bool) or not isinstance(p, (int, float)) or math.isnan(p) or not 0.0 <= p <= 1.0:
        raise ValueError(f"a prediction must be a number in [0, 1], got {p!r}")
    return float(p)


def _check_label(y) -> bool:
    if not isinstance(y, bool):
        raise ValueError(f"a label must be True or False, got {y!r}")
    return y


def _check_bins(n_bins) -> int:
    if isinstance(n_bins, bool) or not isinstance(n_bins, int) or n_bins < 2:
        raise ValueError(f"n_bins must be a whole number of at least 2, got {n_bins!r}")
    return n_bins


def _check_thresholds(tolerance, min_count) -> None:
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0 <= tolerance <= 1:
        raise ValueError(f"tolerance must be in [0, 1], got {tolerance!r}")
    if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count < 1:
        raise ValueError(f"min_count must be a whole number of at least 1, got {min_count!r}")


# --------------------------------------------------------------------------
# Brier score
# --------------------------------------------------------------------------


def brier_score(preds: Sequence[float], labels: Sequence[bool]) -> float:
    """Mean squared error between predicted win probability and the outcome.
    0 is perfect; always saying 0.5 scores exactly COIN_FLIP_BRIER."""
    if len(preds) != len(labels):
        raise ValueError("preds and labels differ in length")
    if not preds:
        raise ValueError("nothing to score")
    total = 0.0
    for p, y in zip(preds, labels):
        p, y = _check_pred(p), _check_label(y)
        total += (p - (1.0 if y else 0.0)) ** 2
    return total / len(preds)


def brier_skill(brier: float) -> float:
    """1 minus the Brier score as a fraction of the coin-flip score.
    0 is a coin flip, 1 is perfect, negative is worse than a coin flip."""
    return 1.0 - brier / COIN_FLIP_BRIER


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    n: int
    mean_predicted: float | None
    observed_rate: float | None

    @property
    def gap(self) -> float | None:
        """|predicted - observed|, or None for an empty bin."""
        if self.n == 0:
            return None
        return abs(self.mean_predicted - self.observed_rate)

    @property
    def signed_gap(self) -> float | None:
        """predicted - observed: positive means over-confident in winning."""
        if self.n == 0:
            return None
        return self.mean_predicted - self.observed_rate


class _BinAcc:
    def __init__(self, n_bins: int) -> None:
        self.n_bins = _check_bins(n_bins)
        self.n = [0] * n_bins
        self.sum_pred = [0.0] * n_bins
        self.sum_pos = [0] * n_bins

    def add(self, p: float, y: bool) -> None:
        i = min(int(p * self.n_bins), self.n_bins - 1)  # 1.0 belongs in the last bin
        self.n[i] += 1
        self.sum_pred[i] += p
        self.sum_pos[i] += y

    def table(self) -> list[CalibrationBin]:
        k = self.n_bins
        return [
            CalibrationBin(
                low=i / k,
                high=(i + 1) / k,
                n=self.n[i],
                mean_predicted=self.sum_pred[i] / self.n[i] if self.n[i] else None,
                observed_rate=self.sum_pos[i] / self.n[i] if self.n[i] else None,
            )
            for i in range(k)
        ]


def calibration_table(
    preds: Sequence[float], labels: Sequence[bool], n_bins: int = 10
) -> list[CalibrationBin]:
    """Bucketed predicted versus observed win rate, with each bucket's count."""
    acc = _BinAcc(n_bins)
    if len(preds) != len(labels):
        raise ValueError("preds and labels differ in length")
    for p, y in zip(preds, labels):
        acc.add(_check_pred(p), _check_label(y))
    return acc.table()


def calibration_failures(
    table: Sequence[CalibrationBin], tolerance: float, min_count: int = 100
) -> list[CalibrationBin]:
    """Bins whose |predicted - observed| exceeds `tolerance`. Bins with fewer
    than `min_count` states are reported in the table but never fail: a bin of
    ten states says nothing about calibration."""
    _check_thresholds(tolerance, min_count)
    return [b for b in table if b.n >= min_count and b.gap > tolerance]


# --------------------------------------------------------------------------
# Symmetry, complement, terminal (DEFINITIONS sections 1 and 5)
# --------------------------------------------------------------------------


def mirror_state(state):
    """The same position seen from the other side: sides swapped, outcome and
    set score flipped. Observations are left alone; the v0 baseline does not
    read them."""
    score = state.set_score_entering_game
    return replace(
        state,
        our_pokemon=state.opp_pokemon,
        opp_pokemon=state.our_pokemon,
        outcome=None if state.outcome is None else (not state.outcome),
        set_score_entering_game=None if score is None else (score[1], score[0]),
    )


def perfectly_mirrored(state):
    """A state where both sides are identical and the game is undecided. Any
    sane win probability for it is exactly 0.5."""
    return replace(
        state, opp_pokemon=state.our_pokemon, outcome=None, set_score_entering_game=None
    )


def symmetry_failures(predict: Predictor, states: Iterable, tolerance: float = 1e-6) -> list:
    """Perfectly mirrored versions of `states` that do not predict 0.5."""
    out = []
    for s in states:
        m = perfectly_mirrored(s)
        if abs(_check_pred(predict(m)) - 0.5) > tolerance:
            out.append(m)
    return out


def complement_failures(predict: Predictor, states: Iterable, tolerance: float = 1e-6) -> list:
    """States where WP(s) + WP(mirror(s)) is not 1 (DEFINITIONS section 1:
    'the other side is 1 - WP')."""
    return [
        s
        for s in states
        if abs(_check_pred(predict(s)) + _check_pred(predict(mirror_state(s))) - 1.0) > tolerance
    ]


def terminal_failures(predict: Predictor, states: Iterable, tolerance: float = 1e-12) -> list:
    """Decided states that are not exactly 1.0 (won) or 0.0 (lost)."""
    out = []
    for s in states:
        if s.outcome is None:
            continue
        want = 1.0 if s.outcome else 0.0
        if abs(_check_pred(predict(s)) - want) > tolerance:
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Pokemon remaining and the trend (reported, never gated)
# --------------------------------------------------------------------------


def pokemon_remaining(side: Sequence) -> int:
    """Pokemon a side still has: BRING_SIZE minus the fainted count."""
    return max(0, BRING_SIZE - sum(1 for p in side if p.fainted))


@dataclass(frozen=True)
class Scored:
    format: str
    game: str
    pred: float
    label: bool
    our_remaining: int
    opp_remaining: int
    decided: bool = False
    """True when the state itself is already decided (outcome known)."""


def score_states(
    predict: Predictor, labelled: Iterable[tuple[str, str, object, bool]]
) -> Iterator[Scored]:
    """Run a predictor over (format, game, state, label) rows."""
    for fmt, game, state, label in labelled:
        yield Scored(
            format=fmt,
            game=game,
            pred=_check_pred(predict(state)),
            label=_check_label(label),
            our_remaining=pokemon_remaining(state.our_pokemon),
            opp_remaining=pokemon_remaining(state.opp_pokemon),
            decided=state.outcome is not None,
        )


@dataclass(frozen=True)
class TrendCell:
    n: int
    mean_predicted: float


@dataclass
class Trend:
    cells: dict[tuple[int, int], TrendCell] = field(default_factory=dict)
    rising_fraction: float | None = None
    """Of the steps 'opponent loses one Pokemon, everything else equal' between
    two cells of at least min_count states, the fraction where the mean
    predicted win probability rose. None if there are no such steps."""
    steps: int = 0


class _TrendAcc:
    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0, 0.0])

    def add(self, our: int, opp: int, p: float) -> None:
        c = self.cells[(our, opp)]
        c[0] += 1
        c[1] += p

    def trend(self, min_count: int) -> Trend:
        cells = {k: TrendCell(n=int(v[0]), mean_predicted=v[1] / v[0]) for k, v in self.cells.items()}
        rising = steps = 0
        for (our, opp), cell in cells.items():
            lower = cells.get((our, opp - 1))
            if lower is not None and cell.n >= min_count and lower.n >= min_count:
                steps += 1
                rising += lower.mean_predicted > cell.mean_predicted
        return Trend(cells=cells, rising_fraction=(rising / steps if steps else None), steps=steps)


def remaining_trend(scored: Iterable[Scored], min_count: int = 30) -> dict[str, Trend]:
    """Mean predicted win probability by (our remaining, opponent remaining),
    per format, with sample sizes. Reported, never a pass or fail."""
    accs: dict[str, _TrendAcc] = defaultdict(_TrendAcc)
    for r in scored:
        accs[r.format].add(r.our_remaining, r.opp_remaining, r.pred)
    return {fmt: acc.trend(min_count) for fmt, acc in accs.items()}


# --------------------------------------------------------------------------
# Expert-claim cases (reported, never gated)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpertClaim:
    claim_id: str
    description: str
    better: object
    worse: object
    """Two labelled states: the one an expert says is better for the side
    analysed, and the one they say is worse."""


@dataclass(frozen=True)
class ClaimResult:
    claim_id: str
    p_better: float
    p_worse: float

    @property
    def agrees(self) -> bool:
        return self.p_better > self.p_worse  # a tie is not agreement


def score_claims(predict: Predictor, claims: Sequence[ExpertClaim]) -> list[ClaimResult]:
    return [
        ClaimResult(c.claim_id, _check_pred(predict(c.better)), _check_pred(predict(c.worse)))
        for c in claims
    ]


# --------------------------------------------------------------------------
# Per-format evaluation
# --------------------------------------------------------------------------


@dataclass
class FormatMetrics:
    format: str
    pooled: bool
    n_states: int
    n_games: int
    n_decided: int
    brier: float
    brier_skill: float
    brier_with_decided: float
    calibration: list[CalibrationBin]
    calibration_failures: list[CalibrationBin]
    trend: Trend


class _FormatAcc:
    def __init__(self, n_bins: int) -> None:
        self.n = 0
        self.sq = 0.0
        self.n_decided = 0
        self.sq_decided = 0.0
        self.games: set[str] = set()
        self.bins = _BinAcc(n_bins)
        self.trend = _TrendAcc()

    def add(self, r: Scored) -> None:
        self.games.add(r.game)
        err = (r.pred - (1.0 if r.label else 0.0)) ** 2
        if r.decided:
            self.n_decided += 1
            self.sq_decided += err
            return
        self.n += 1
        self.sq += err
        self.bins.add(r.pred, r.label)
        self.trend.add(r.our_remaining, r.opp_remaining, r.pred)

    def metrics(self, fmt, pooled, tolerance, min_count, trend_min_count) -> FormatMetrics:
        if self.n == 0:
            raise ValueError(f"{fmt}: no undecided states to score")
        brier = self.sq / self.n
        table = self.bins.table()
        return FormatMetrics(
            format=fmt,
            pooled=pooled,
            n_states=self.n,
            n_games=len(self.games),
            n_decided=self.n_decided,
            brier=brier,
            brier_skill=brier_skill(brier),
            brier_with_decided=(self.sq + self.sq_decided) / (self.n + self.n_decided),
            calibration=table,
            calibration_failures=calibration_failures(table, tolerance, min_count),
            trend=self.trend.trend(trend_min_count),
        )


SMALL_SAMPLE_GAMES = 500


@dataclass
class MetricReport:
    per_format: dict[str, FormatMetrics]
    pooled: FormatMetrics
    tolerance: float
    min_count: int
    claims: list[ClaimResult] | None = None

    def describe(self) -> str:
        lines = [
            "=== wpa metrics (per format) ===",
            f"calibration tolerance {self.tolerance:.3f}; bins under {self.min_count} states "
            "are listed but not judged; n counts states (correlated within a game)",
        ]
        for fmt in sorted(self.per_format):
            m = self.per_format[fmt]
            lines.append(
                f"{fmt}: {m.n_states} undecided states in {m.n_games} games "
                f"({m.n_decided} decided states set aside)"
            )
            if m.n_games < SMALL_SAMPLE_GAMES:
                lines.append(f"  SMALL SAMPLE: only {m.n_games} games; read every number with that in mind")
            lines.append(
                f"  Brier {m.brier:.4f} (coin flip {COIN_FLIP_BRIER:.2f}; skill {m.brier_skill:+.3f})"
                f"; including decided states {m.brier_with_decided:.4f}"
            )
            failing = {id(b) for b in m.calibration_failures}
            for b in m.calibration:
                if b.n == 0:
                    lines.append(f"  {b.low:.1f}-{b.high:.1f}  n=0")
                    continue
                flag = "  <-- outside tolerance" if id(b) in failing else (
                    "  (too few to judge)" if b.n < self.min_count else ""
                )
                lines.append(
                    f"  {b.low:.1f}-{b.high:.1f}  n={b.n:<8} predicted {b.mean_predicted:.3f}  "
                    f"observed {b.observed_rate:.3f}  gap {b.gap:.3f}{flag}"
                )
            lines.append(f"  calibration bins outside tolerance: {len(m.calibration_failures)}")
            t = m.trend
            lines.append(
                "  trend (reported, not a gate): mean predicted WP by Pokemon remaining "
                "(ours/theirs: mean, n)"
            )
            for (our, opp), cell in sorted(t.cells.items(), reverse=True):
                lines.append(f"    {our}/{opp}: {cell.mean_predicted:.3f}  n={cell.n}")
            if t.rising_fraction is None:
                lines.append("  trend: no pair of cells large enough to compare")
            else:
                lines.append(
                    f"  trend: WP rose in {t.rising_fraction:.0%} of {t.steps} "
                    "'opponent loses one Pokemon' steps"
                )
        if self.claims is not None:
            if not self.claims:
                lines.append(
                    "expert-claim cases: 0 labelled positions (docs/EXPERT-CLAIMS.md has claims "
                    "written as specification only)"
                )
            else:
                agree = sum(c.agrees for c in self.claims)
                lines.append(f"expert-claim cases (reported, not gated): baseline agrees with {agree} of {len(self.claims)}")
                for c in self.claims:
                    lines.append(
                        f"  {c.claim_id}: better {c.p_better:.3f} vs worse {c.p_worse:.3f} "
                        f"-> {'agrees' if c.agrees else 'DISAGREES'}"
                    )
        p = self.pooled
        lines.append("")
        lines.append("POOLED (secondary, not a headline)")
        lines.append(
            f"  {p.n_states} undecided states in {p.n_games} games "
            f"({p.n_decided} decided set aside); Brier {p.brier:.4f} "
            f"(coin flip {COIN_FLIP_BRIER:.2f})"
        )
        return "\n".join(lines)


def evaluate(
    scored: Iterable[Scored],
    tolerance: float = 0.05,
    min_count: int = 100,
    n_bins: int = 10,
    trend_min_count: int = 30,
    claims: list[ClaimResult] | None = None,
) -> MetricReport:
    """Per-format Brier, calibration and trend, plus a labelled pooled figure."""
    _check_thresholds(tolerance, min_count)
    _check_bins(n_bins)
    per: dict[str, _FormatAcc] = {}
    pooled = _FormatAcc(n_bins)
    for r in scored:
        if not r.format:
            raise ValueError("every scored state needs a format")
        _check_pred(r.pred)
        _check_label(r.label)
        per.setdefault(r.format, _FormatAcc(n_bins)).add(r)
        pooled.add(r)
    if not per:
        raise ValueError("nothing to evaluate")
    return MetricReport(
        per_format={
            fmt: acc.metrics(fmt, False, tolerance, min_count, trend_min_count)
            for fmt, acc in sorted(per.items())
        },
        pooled=pooled.metrics("pooled", True, tolerance, min_count, trend_min_count),
        tolerance=tolerance,
        min_count=min_count,
        claims=claims,
    )


# --------------------------------------------------------------------------
# Loading states and labels from wpa_states/
# --------------------------------------------------------------------------


@dataclass
class LoadStats:
    files: int = 0
    states: int = 0
    incomplete_files: int = 0
    incomplete_states: int = 0
    unassigned_files: int = 0
    _tags: set[str] = field(default_factory=set, repr=False)

    @property
    def games(self) -> int:
        return len(self._tags)


def load_split(
    directory,
    games: Mapping[str, str],
    split: str,
    fmt: str,
    stats: LoadStats,
) -> Iterator[tuple[str, str, StateView, bool]]:
    """Stream (format, game, state, label) for one split of one format.

    `games` maps battle tag -> split (SplitResult.to_dict()["games"]). Files
    are read one at a time. A game's label is its last state's outcome; a
    file whose last state is undecided is incomplete (DEFINITIONS section 9):
    dropped and counted. Files whose game has no assignment (for example the
    dropped best-of-5 match) are skipped and counted.
    """
    if split not in SPLIT_NAMES:
        raise ValueError(f"split must be one of {SPLIT_NAMES}, got {split!r}")
    directory = Path(directory)
    names = sorted(e.name for e in os.scandir(directory) if e.name.endswith(".json"))
    for name in names:
        tag, _role = parse_state_filename(name)
        if tag not in games:
            stats.unassigned_files += 1
            continue
        if games[tag] != split or format_of(tag) != fmt:
            continue
        records = json.loads((directory / name).read_text(encoding="utf-8"))
        if not records:
            raise ValueError(f"{name}: file has no states")
        label = records[-1]["outcome"]
        if label is None:
            stats.incomplete_files += 1
            stats.incomplete_states += len(records)
            continue
        stats.files += 1
        stats.states += len(records)
        stats._tags.add(tag)
        for record in records:
            yield fmt, tag, state_from_dict(record), bool(label)
