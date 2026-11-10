"""Which two a player leads with (Week 11 Task 1, DEFINITIONS §6).

At team preview each player picks the four to bring and the two that lead,
without seeing the other's choice. The win probability model cannot see a
player's back two (both sides' backs are chances from `wpa.bring`, and Week 8
found they add nothing measurable), so the choice scored at team preview is the
leads: one of the 15 pairs of the six on the sheet.

This module gives each pair its chance, as the opponent would judge it: a
conditional logit over the 15 pairs (like `wpa.policy` and `wpa.replace_model`),
learned from the training split. The facts about a pair:

- how often each of its species leads in this format (training split, smoothed
  towards 2 in 6);
- Fake Out, Intimidate, speed control (Tailwind, Trick Room, Icy Wind,
  Electroweb) and redirection (Follow Me, Rage Powder) on their sheets;
- whether they are the first two on the sheet;
- in games 2 and 3 of a set, how many of them led the game before (players often
  lead the same way again).

`python -m wpa.lead_model` fits it on training games (logs in set order, so a
set's earlier games are known), scores it per format on validation games against
a uniform guess over the 15 pairs, and saves `models_v4/leads.json` and
`leads.txt`. The test split is never read.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

from wpa.team_sheets import SheetMon, to_id

FEATURES = (
    "lead_rate",
    "fakeout",
    "intimidate",
    "speed_control",
    "redirect",
    "first_two",
    "has_prev",
    "led_before",
)
PRIOR = 2 / 6  # two of six lead
SMOOTH = 20.0  # pseudo-games pulling a species' lead rate towards PRIOR
SPEED_CONTROL = {"tailwind", "trickroom", "icywind", "electroweb"}
REDIRECT = {"followme", "ragepowder"}


def pairs(n: int = 6) -> list[tuple[int, int]]:
    """Every pair of sheet positions, in a fixed order."""
    return list(combinations(range(n), 2))


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def pair_features(
    sheet: Sequence[SheetMon],
    pair: tuple[int, int],
    rates: Mapping[str, float],
    prev: set[str] | frozenset[str] | None,
) -> list[float]:
    """The facts about leading with `pair`, in FEATURES order. `rates`: each
    species' lead rate in this format; `prev`: the species that led the set's
    previous game for this player (None in a set's first game)."""
    f = dict.fromkeys(FEATURES, 0.0)
    for i in pair:
        m = sheet[i]
        sp = to_id(m.species)
        moves = {to_id(x) for x in m.moves}
        f["lead_rate"] += _logit(rates.get(sp, PRIOR))
        f["fakeout"] += float("fakeout" in moves)
        f["intimidate"] += float(to_id(m.ability) == "intimidate")
        f["speed_control"] += float(bool(moves & SPEED_CONTROL))
        f["redirect"] += float(bool(moves & REDIRECT))
        if prev is not None:
            f["led_before"] += float(sp in prev)
    f["first_two"] = float(tuple(pair) == (0, 1))
    f["has_prev"] = float(prev is not None)
    return [f[k] for k in FEATURES]


def features(
    sheet: Sequence[SheetMon],
    rates: Mapping[str, float],
    prev: set[str] | frozenset[str] | None,
) -> np.ndarray:
    return np.array(
        [pair_features(sheet, p, rates, prev) for p in pairs(len(sheet))], dtype=float
    )


@dataclass
class LeadModel:
    weights: list[float]
    rates: dict[str, dict[str, float]]  # format -> species -> lead rate

    def chances_x(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(X, dtype=float) @ np.asarray(self.weights, dtype=float)
        z = np.exp(z - z.max())
        return z / z.sum()

    def chances(
        self,
        sheet: Sequence[SheetMon],
        fmt: str,
        prev: set[str] | frozenset[str] | None,
    ) -> np.ndarray:
        """The chance of each pair in `pairs(len(sheet))`."""
        return self.chances_x(features(sheet, self.rates.get(fmt, {}), prev))

    def save(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "features": list(FEATURES),
                    "weights": self.weights,
                    "rates": self.rates,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> LeadModel:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d["features"] != list(FEATURES):
            raise ValueError("lead features changed since this model was saved")
        return cls(d["weights"], d["rates"])


def fit(
    groups: Sequence[tuple[np.ndarray, int]],
    rates: Mapping[str, Mapping[str, float]],
    l2: float = 1e-2,
) -> LeadModel:
    """Maximum likelihood (with a small ridge) over (pairs x features, chosen)."""
    from wpa.policy import fit as _fit

    w = _fit(groups, l2, k=len(FEATURES)).weights
    return LeadModel(list(w), {f: dict(r) for f, r in rates.items()})


def score(
    model: LeadModel, groups: Sequence[tuple[np.ndarray, int]]
) -> tuple[float, float]:
    """(mean log chance of the pair that led, the same for a uniform guess)."""
    ll = float(
        np.mean([math.log(max(model.chances_x(X)[c], 1e-12)) for X, c in groups])
    )
    un = float(np.mean([math.log(1 / len(X)) for X, _ in groups]))
    return ll, un


@dataclass(frozen=True)
class Example:
    """One side of one game: its sheet, the pair that led (`chosen`, an index
    into `pairs`), and the species that led the set's previous game."""

    tag: str
    format: str
    role: str
    sheet: tuple[SheetMon, ...]
    leads: frozenset[int]
    leads_species: frozenset[str]
    prev: frozenset[str] | None
    chosen: int


def examples_from_logs(
    logs: Iterable[tuple[str, str]], splits: Mapping[str, str]
) -> dict[str, list[Example]]:
    """Examples by split, from logs in set order (`logs_sets/`): each side of each
    game with a six-Pokemon sheet and two leads, with the leads of the same
    player's previous game in the set (matched by name)."""
    from wpa.bring import leads_from_log, players
    from wpa.features import unit_of
    from wpa.formats import format_of
    from wpa.team_sheets import sheets_from_log

    memory: dict[tuple[str, str], frozenset[str]] = {}
    out: dict[str, list[Example]] = {}
    for tag, log in logs:
        try:
            fmt = format_of(tag)
        except Exception:
            continue
        unit, _game = unit_of(tag, log)
        names, sheets, leads = players(log), sheets_from_log(log), leads_from_log(log)
        for role, sheet in sheets.items():
            name = names.get(role, role)
            lead = leads.get(role, frozenset())
            if len(sheet) != 6 or len(lead) != 2:
                continue
            species = frozenset(to_id(sheet[i].species) for i in lead)
            prev = memory.get((unit, name))
            if tag in splits:
                out.setdefault(splits[tag], []).append(
                    Example(
                        tag,
                        fmt,
                        role,
                        tuple(sheet),
                        frozenset(lead),
                        species,
                        prev,
                        pairs(6).index((min(lead), max(lead))),
                    )
                )
            memory[(unit, name)] = species
    return out


def lead_rates(examples: Iterable[Example]) -> dict[str, dict[str, float]]:
    """Each species' lead rate per format, smoothed towards 2 in 6."""
    seen: dict[str, dict[str, list[int]]] = {}
    for e in examples:
        per = seen.setdefault(e.format, {})
        for i, m in enumerate(e.sheet):
            c = per.setdefault(to_id(m.species), [0, 0])
            c[0] += int(i in e.leads)
            c[1] += 1
    return {
        f: {s: (n + SMOOTH * PRIOR) / (t + SMOOTH) for s, (n, t) in per.items()}
        for f, per in seen.items()
    }


def groups_for(
    examples: Iterable[Example], rates: Mapping[str, Mapping[str, float]]
) -> list[tuple[np.ndarray, int]]:
    return [
        (features(e.sheet, rates.get(e.format, {}), e.prev), e.chosen) for e in examples
    ]


def main() -> None:  # pragma: no cover - runs on the corpus
    from wpa.policy_data import _iter_logs

    p = argparse.ArgumentParser(description="Fit the lead model (Week 11 Task 1).")
    p.add_argument("--logs", type=Path, default=Path("logs_sets"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--out", type=Path, default=Path("models_v4/leads.json"))
    a = p.parse_args()
    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    kept = {t: s for t, s in splits.items() if s in ("train", "validation")}
    ex = examples_from_logs(_iter_logs(a.logs), kept)  # the test split is never read
    train, val = ex.get("train", []), ex.get("validation", [])
    rates = lead_rates(train)
    model = fit(groups_for(train, rates), rates)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(a.out)
    lines = [
        "Lead model (Week 11 Task 1), validation: mean log chance of the pair that "
        "led, against a uniform guess over the 15 pairs",
        f"  training: {len(train)} sides of games",
    ]
    for fmt in ("regma", "regmb"):
        v = groups_for([e for e in val if e.format == fmt], rates)
        if not v:
            continue
        ll, un = score(model, v)
        top = float(np.mean([int(np.argmax(model.chances_x(X)) == c) for X, c in v]))
        lines.append(
            f"  {fmt}: {len(v)} sides; model {ll:.3f}, uniform {un:.3f} "
            f"({'beats' if ll > un else 'DOES NOT BEAT'} it); its likeliest pair led "
            f"{100 * top:.1f}% (uniform {100 / 15:.1f}%)"
        )
    lines.append(
        "  weights: "
        + ", ".join(f"{k} {w:+.2f}" for k, w in zip(FEATURES, model.weights))
    )
    text = "\n".join(lines)
    print(text)
    a.out.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
