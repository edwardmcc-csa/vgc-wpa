"""Which four of six each player brought (Week 8 Task 1, the plan's M4b).

With open team sheets both players see each other's six at team preview, and each
brings four. Until all four have appeared, which ones are in the back is unknown.
This module gives, at any decision, the chance that each sheet Pokemon was
brought:

- **its own odds** from a small logistic regression: how often its species is
  brought (training split, per format), its place on the sheet, and, in games 2
  and 3 of a set, whether the player brought it the game before;
- **the sets of four** consistent with what has been seen: each set's chance is
  the product of its members' odds, so every set of four always contains every
  Pokemon already seen.

The plan's test: at team preview it beats a uniform guess over the 15 sets.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

BRING, SHEET = 4, 6
SMOOTH = 20.0  # pseudo-games pulling a species' bring rate towards 4/6
FEATURES = ("rate_logit", "has_prev", "prev_brought", *(f"pos{k}" for k in range(1, 7)))


def players(log: str) -> dict[str, str]:
    """Each side's name, the first non-empty `|player|` line (reconnects repeat it)."""
    out: dict[str, str] = {}
    for line in log.split("\n"):
        if line.startswith("|player|"):
            p = line.split("|")
            if len(p) > 3 and p[2] in ("p1", "p2") and p[3] and p[2] not in out:
                out[p[2]] = p[3]
    return out


def sheets(log: str) -> dict[str, tuple[str, ...]]:
    """Each side's six species ids, in sheet order."""
    from wpa.decisions import to_id
    from wpa.sheets import parse_showteam_message

    out = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            role, mons = parse_showteam_message(line)
            out[role] = tuple(to_id(m.species) for m in mons)
    return out


def brought_from_log(log: str) -> dict[str, set[int]]:
    """Sheet positions of the Pokemon each side sent in at some point."""
    return {role: set(order) for role, order in _sent_in(log).items()}


def leads_from_log(log: str) -> dict[str, frozenset[int]]:
    """The two each side sent in first."""
    return {role: frozenset(order[:2]) for role, order in _sent_in(log).items()}


def _sent_in(log: str) -> dict[str, list[int]]:
    from wpa.decisions import _Board

    board = _Board()
    order: dict[str, list[int]] = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            board.sheet(line)
        elif line.startswith(("|switch|", "|drag|", "|replace|")):
            board.handle(line.split("|"))
            for role, mons in board.mons.items():
                for i, m in enumerate(mons):
                    if m["seen"] and i not in order.setdefault(role, []):
                        order[role].append(i)
    for role in board.mons:
        order.setdefault(role, [])
    return order


def set_chances(
    odds: Sequence[float], revealed: Iterable[int]
) -> dict[frozenset[int], float]:
    """Each set of four that contains every revealed Pokemon, with its chance
    (proportional to the product of its members' odds)."""
    seen = frozenset(revealed)
    sets = [frozenset(s) for s in combinations(range(len(odds)), BRING)]
    weights = {s: math.prod(odds[i] for i in s) for s in sets if seen <= s}
    total = sum(weights.values())
    if total <= 0:
        return {s: 1 / len(weights) for s in weights} if weights else {}
    return {s: w / total for s, w in weights.items()}


def marginals(odds: Sequence[float], revealed: Iterable[int]) -> list[float]:
    """The chance each sheet Pokemon was brought."""
    out = [0.0] * len(odds)
    for s, p in set_chances(odds, revealed).items():
        for i in s:
            out[i] += p
    return out


@dataclass(frozen=True)
class Example:
    """One side of one game: format, sheet species, who was brought, and who the
    player brought the game before in the same set (None in a set's first game)."""

    format: str
    sheet: tuple[str, ...]
    brought: frozenset[int]
    prev: frozenset[int] | None
    leads: frozenset[int] = frozenset()  # the two sent in first


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


@dataclass
class BringModel:
    rates: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    coef: list[float] = field(default_factory=list)
    intercept: float = 0.0

    def rate(self, fmt: str, species: str) -> float:
        b, n = self.rates.get(fmt, {}).get(species, (0.0, 0.0))
        return (b + SMOOTH * BRING / SHEET) / (n + SMOOTH)

    def features(
        self, fmt: str, sheet: Sequence[str], prev: frozenset[int] | None
    ) -> list[list[float]]:
        rows = []
        for i, sp in enumerate(sheet):
            pos = [0.0] * SHEET
            pos[min(i, SHEET - 1)] = 1.0
            rows.append(
                [
                    _logit(self.rate(fmt, sp)),
                    float(prev is not None),
                    float(prev is not None and i in prev),
                    *pos,
                ]
            )
        return rows

    def odds(
        self, fmt: str, sheet: Sequence[str], prev: frozenset[int] | None
    ) -> list[float]:
        out = []
        for row in self.features(fmt, sheet, prev):
            z = self.intercept + sum(c * x for c, x in zip(self.coef, row))
            out.append(math.exp(max(-30.0, min(30.0, z))))
        return out

    def marginals_for(
        self,
        fmt: str,
        sheet: Sequence[str],
        revealed: Iterable[int],
        prev: frozenset[int] | None,
    ) -> list[float]:
        return marginals(self.odds(fmt, sheet, prev), revealed)

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "features": list(FEATURES),
                    "coef": self.coef,
                    "intercept": self.intercept,
                    "rates": self.rates,
                },
                indent=1,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> BringModel:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d["features"] != list(FEATURES):
            raise ValueError("bring model saved with different features")
        return cls(rates=d["rates"], coef=d["coef"], intercept=d["intercept"])


def fit(examples: Sequence[Example]) -> BringModel:
    """Species rates from the examples, then the regression on every sheet
    Pokemon of every example (brought or not)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    rates: dict[str, dict[str, list[float]]] = {}
    for ex in examples:
        r = rates.setdefault(ex.format, {})
        for i, sp in enumerate(ex.sheet):
            c = r.setdefault(sp, [0.0, 0.0])
            c[0] += i in ex.brought
            c[1] += 1
    model = BringModel(rates=rates)
    X, y = [], []
    for ex in examples:
        X += model.features(ex.format, ex.sheet, ex.prev)
        y += [int(i in ex.brought) for i in range(len(ex.sheet))]
    lr = LogisticRegression(C=1.0, max_iter=1000)
    lr.fit(np.array(X), np.array(y))
    model.coef = [float(c) for c in np.ravel(lr.coef_)]
    model.intercept = float(np.ravel(lr.intercept_)[0])
    return model


def evaluate(model: BringModel, examples: Sequence[Example]) -> dict[str, dict]:
    """Per format: the mean log chance of the four actually brought, at team
    preview (against log 1/15 for a uniform guess) and once the two leads are
    known (against log 1/6), and how often the most likely set is right."""
    out: dict[str, dict] = {}
    for ex in examples:
        r = out.setdefault(
            ex.format,
            {"games": 0, "log_chance": 0.0, "top_right": 0, "after_leads": 0.0},
        )
        odds = model.odds(ex.format, ex.sheet, ex.prev)
        sets = set_chances(odds, ())
        r["games"] += 1
        r["log_chance"] += math.log(max(sets.get(ex.brought, 0.0), 1e-12))
        r["top_right"] += max(sets, key=lambda s: sets[s]) == ex.brought
        if ex.leads:
            after = set_chances(odds, ex.leads)
            r["after_leads"] += math.log(max(after.get(ex.brought, 0.0), 1e-12))
    for r in out.values():
        n = max(1, r["games"])
        r["log_chance"] /= n
        r["after_leads"] /= n
        r["top_right"] /= n
        r["uniform"] = math.log(1 / 15)
        r["uniform_after_leads"] = math.log(1 / 6)
    return out


# --------------------------------------------------------------------------
# Week 17, Task 5: the four against the opponent's six
# --------------------------------------------------------------------------

Matchup = tuple[tuple[str, ...], tuple[str, ...], frozenset[int]]


@dataclass
class MatchupTerm:
    """How the opponent's six move each Pokemon's odds of being brought: its
    odds times exp(beta x the mean, over their six, of log(how often it is
    brought against that species / how often it is brought at all)), the
    rates from training games (smoothed toward its own rate by `smooth`
    sides). On Reg M-C's validation games (Week 17) it picks the four brought
    twice as often as the bring model alone (18% against 10%; among the
    winners 20% against 10%)."""

    pairs: dict[str, list[float]]  # "own|theirs" -> [brought, on the sheet]
    own: dict[str, list[float]]  # "own" -> [brought, on the sheet]
    beta: float = 0.0
    smooth: float = 20.0

    def term(self, a: str, theirs: Sequence[str]) -> float:
        took, on = self.own.get(a, (0.0, 0.0))
        base = (took + 1) / (on + 3)
        logs = []
        for b in theirs:
            t, n = self.pairs.get(f"{a}|{b}", (0.0, 0.0))
            logs.append(math.log((t + self.smooth * base) / (n + self.smooth) / base))
        return sum(logs) / len(logs) if logs else 0.0

    def adjust(
        self, odds: Sequence[float], mine: Sequence[str], theirs: Sequence[str]
    ) -> list[float]:
        return [
            o * math.exp(self.beta * self.term(a, theirs)) for o, a in zip(odds, mine)
        ]

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "pairs": self.pairs,
                    "own": self.own,
                    "beta": self.beta,
                    "smooth": self.smooth,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> MatchupTerm:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["pairs"], d["own"], d["beta"], d["smooth"])


def _four_log_chance(odds: Sequence[float], four: frozenset[int]) -> float:
    return math.log(max(set_chances(odds, ()).get(four, 0.0), 1e-12))


def fit_matchup(
    rows: Sequence[Matchup],
    tune: Sequence[Matchup],
    betas: Sequence[float] = (0, 1, 2, 3, 4, 6, 8, 12),
    base=None,
) -> MatchupTerm:
    """The rates from `rows` (sheet, their sheet, the four brought), and beta
    the one of `betas` that gives `tune`'s fours the highest mean log chance
    (on top of `base`'s odds, `fmt, sheet -> odds`; even odds without one)."""
    pairs: dict[str, list[float]] = {}
    own: dict[str, list[float]] = {}
    for mine, theirs, four in rows:
        for i, a in enumerate(mine):
            o = own.setdefault(a, [0.0, 0.0])
            o[0] += i in four
            o[1] += 1
            for b in set(theirs):
                q = pairs.setdefault(f"{a}|{b}", [0.0, 0.0])
                q[0] += i in four
                q[1] += 1
    term = MatchupTerm(pairs, own)

    def score(beta: float) -> float:
        term.beta = beta
        total = 0.0
        for mine, theirs, four in tune:
            odds = base(mine) if base else [1.0] * len(mine)
            total += _four_log_chance(term.adjust(odds, mine, theirs), four)
        return total

    term.beta = max(betas, key=score)
    return term


def matchup_rows(
    logs: Iterable[tuple[str, str]], splits: dict[str, str]
) -> dict[str, list[Matchup]]:
    """By split, each side of each game whose four all appeared: its sheet, the
    opponent's sheet, and the four."""
    out: dict[str, list[Matchup]] = {}
    for tag, log in logs:
        if tag not in splits:
            continue
        sh, got = sheets(log), brought_from_log(log)
        for role, sheet in sh.items():
            other = sh.get("p2" if role == "p1" else "p1")
            mine = got.get(role, set())
            if (
                len(sheet) == SHEET
                and other
                and len(other) == SHEET
                and len(mine) == BRING
            ):
                out.setdefault(splits[tag], []).append(
                    (tuple(sheet), tuple(other), frozenset(mine))
                )
    return out


def main_matchup(a) -> None:
    """`--matchup`: the term for one format's games (`--format`), saved at
    `--out` beside that format's bring model (`bring.json`)."""
    splits = json.loads(a.splits.read_text(encoding="utf-8"))["games"]
    rows = matchup_rows(_iter_logs(a.logs), splits)
    train, val = rows.get("train", []), rows.get("validation", [])
    fmt = a.format
    bring = BringModel.load(a.out.parent / "bring.json")

    def base(mine):
        return bring.odds(fmt, tuple(mine), None)

    cut = len(train) * 9 // 10
    term = fit_matchup(train[:cut], train[cut:], base=base)
    term = fit_matchup(train, (), betas=(term.beta,))
    term.save(a.out)
    lines = [
        f"matchup term ({fmt}): {len(train)} training sides; beta {term.beta} "
        f"(chosen on training's last tenth)"
    ]
    for name, rs in (("validation", val),):
        for label, t in (("bring model", None), ("with their six", term)):
            ll = hit = 0.0
            for mine, theirs, four in rs:
                odds = base(mine)
                if t is not None:
                    odds = t.adjust(odds, mine, theirs)
                sets = set_chances(odds, ())
                ll += math.log(max(sets.get(four, 0.0), 1e-12))
                hit += max(sets, key=lambda k: sets[k]) == four
            n = max(1, len(rs))
            lines.append(
                f"{name} ({len(rs)} sides): {label}: mean log chance of the four "
                f"brought {ll / n:.3f}; likeliest four right {hit / n:.1%}"
            )
    text = "\n".join(lines) + "\n"
    print(text)
    a.out.with_suffix(".txt").write_text(text, encoding="utf-8")


def examples_from_logs(
    logs: Iterable[tuple[str, str]], splits: dict[str, str]
) -> dict[str, list[Example]]:
    """Examples by split, from logs in set order (`logs_sets/`): each side of each
    game whose four all appeared, with what the same player brought in the set's
    previous game (matched by player name and species)."""
    from wpa.features import unit_of
    from wpa.formats import format_of

    memory: dict[tuple[str, str], set[str]] = {}
    out: dict[str, list[Example]] = {}
    for tag, log in logs:
        unit, _game = unit_of(tag, log)
        sh, names = sheets(log), players(log)
        got, leads = brought_from_log(log), leads_from_log(log)
        for role, sheet in sh.items():
            name = names.get(role, role)
            before = memory.get((unit, name))
            prev = (
                None
                if before is None
                else frozenset(i for i, s in enumerate(sheet) if s in before)
            )
            mine = got.get(role, set())
            if len(sheet) == SHEET and len(mine) == BRING and tag in splits:
                out.setdefault(splits[tag], []).append(
                    Example(
                        format_of(tag),
                        sheet,
                        frozenset(mine),
                        prev,
                        leads.get(role, frozenset()),
                    )
                )
            memory[(unit, name)] = {sheet[i] for i in mine}
    return out


def _iter_logs(folder: Path):
    import gzip

    for path in sorted(folder.glob("part-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                yield d["tag"], d["log"]


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Which four each player brought.")
    p.add_argument("--logs", type=Path, default=Path("logs_sets"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--out", type=Path, default=Path("models_v4") / "bring.json")
    p.add_argument(
        "--matchup",
        action="store_true",
        help="the term for the opponent's six (Week 17), saved at --out, beside "
        "the format's bring.json",
    )
    p.add_argument("--format", default="regmc", help="with --matchup: the format")
    a = p.parse_args()
    if a.matchup:
        main_matchup(a)
        return
    splits = json.loads(a.splits.read_text(encoding="utf-8"))["games"]
    ex = examples_from_logs(_iter_logs(a.logs), splits)
    model = fit(ex["train"])
    model.save(a.out)
    lines = [f"bring model: trained on {len(ex['train'])} sides of training games"]
    for split in ("train", "validation"):
        for fmt, r in sorted(evaluate(model, ex.get(split, [])).items()):
            later = [e for e in ex.get(split, []) if e.format == fmt and e.prev]
            r2 = evaluate(model, later).get(fmt, {})
            lines.append(
                f"{split} {fmt}: {r['games']} sides; at team preview mean log chance "
                f"of the four brought {r['log_chance']:.3f} (uniform "
                f"{r['uniform']:.3f}); most likely set right {r['top_right']:.0%}; "
                f"after the leads {r['after_leads']:.3f} (uniform "
                f"{r['uniform_after_leads']:.3f}); games 2-3 of a set: "
                f"{r2.get('games', 0)} sides, log chance "
                f"{r2.get('log_chance', 0):.3f}, "
                f"most likely set right {r2.get('top_right', 0):.0%}"
            )
    text = "\n".join(lines) + "\n"
    print(text)
    a.out.with_suffix(".txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
