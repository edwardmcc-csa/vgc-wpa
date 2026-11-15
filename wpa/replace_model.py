"""Which Pokemon a player sends in after a faint (Week 10 Task 6, DEFINITIONS §6).

A forced switch is a decision of its own. Its split needs the chance of each
Pokemon the player could send in, as the opponent would judge it, the way a
turn's split needs the opponent model's chances (`wpa.policy`). This module
learns them from the training split: each Pokemon that could come in
(`wpa.choices.replacement_options`) gets a score from what the opponent sees
of it, and its chance is its share of the exponentiated scores (a conditional
logit, like `wpa.policy` and `wpa.bring`).

The facts: its hit points (full if not yet seen), whether it is unseen and how
likely it was brought (`wpa.bring`; the four a player brought are not public
until they appear), how hard it hits the opposing Pokemon on the field and how
hard they hit it (from the damage calculator and the spread estimates), and
Fake Out or Intimidate on its sheet. Two slots filled at once are taken as two
independent choices (as a turn's two Pokemon are). Nothing from later in the
game is used.

`python -m wpa.replace_model` fits it on training games, scores it per format on
validation games against a uniform guess over the Pokemon that could come in
(Task 6's test), and saves `models_v4/replace.json` and `replace.txt`. The test
split is never read.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wpa import choices as C
from wpa.policy import DamageInfo
from wpa.policy import fit as _fit
from wpa.policy import score as _score
from wpa.team_sheets import SheetMon, to_id

FEATURES = ("hp", "unseen", "bring", "best_dmg", "threat", "fakeout", "intimidate")


def option_features(
    r: C.Replacement,
    j: int,
    sheet: Sequence[SheetMon],
    ctx: DamageInfo | None,
    bring_p: Sequence[float] | None,
) -> list[float]:
    """The facts about sending Pokemon `j` in, in FEATURES order, from the
    replacing player's side of the board at the turn's end."""
    f = dict.fromkeys(FEATURES, 0.0)
    st = r.ours[j]
    unseen = not (st["active"] or st["fainted"] or st["hp_fraction"] > 0)
    f["hp"] = 1.0 if unseen else st["hp_fraction"]
    f["unseen"] = float(unseen)
    if unseen and bring_p is not None and j < len(bring_p):
        p = min(max(bring_p[j], 1e-4), 1 - 1e-4)
        f["bring"] = math.log(p / (1 - p))
    if ctx is not None:
        f["best_dmg"] = ctx.best(j)
        f["threat"] = ctx.threat(j)
    mon = sheet[j]
    f["fakeout"] = float("fakeout" in {to_id(m) for m in mon.moves})
    f["intimidate"] = float(to_id(mon.ability) == "intimidate")
    return [f[k] for k in FEATURES]


def options(
    r: C.Replacement,
    sheets: Mapping,
    spreads,
    dex,
    calc,
    odds: Mapping,
    fld: Mapping | None = None,
    brought: set[int] | None = None,
) -> dict[int, tuple[list, np.ndarray]]:
    """For each slot to fill: the switches on offer and their facts."""
    from wpa.bring import marginals

    s = {"our_pokemon": r.ours, "opp_pokemon": r.theirs}
    revealed = [
        i
        for i, p in enumerate(r.ours)
        if p["active"] or p["fainted"] or p["hp_fraction"] > 0
    ]
    bring_p = marginals(odds[r.role], revealed) if r.role in odds else None
    ctx = (
        DamageInfo(s, sheets, r.role, spreads, dex, calc, fld or {})
        if calc is not None
        else None
    )
    out = {}
    for slot, o in C.replacement_options(r, brought).items():
        X = np.array(
            [
                option_features(r, a.switch_to or 0, sheets[r.role], ctx, bring_p)
                for a in o
            ],
            dtype=float,
        )
        out[slot] = (list(o), X)
    return out


@dataclass
class ReplaceModel:
    weights: list[float]

    def chances(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(X, dtype=float) @ np.asarray(self.weights, dtype=float)
        z = np.exp(z - z.max())
        return z / z.sum()

    def save(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps({"features": list(FEATURES), "weights": self.weights}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> ReplaceModel:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d["features"] != list(FEATURES):
            raise ValueError("replacement features changed since this model was saved")
        return cls(d["weights"])


def fit(groups: Sequence[tuple[np.ndarray, int]], l2: float = 1e-2) -> ReplaceModel:
    """Maximum likelihood (with a small ridge) over (options x features, chosen)."""
    return ReplaceModel(_fit(groups, l2, k=len(FEATURES)).weights)


def score(
    model: ReplaceModel, groups: Sequence[tuple[np.ndarray, int]]
) -> tuple[float, float]:
    """(mean log chance of the Pokemon sent in, the same for a uniform guess)."""
    return _score(model, groups)  # type: ignore[arg-type]


def after_turn_timers(game, role: str) -> dict[int, list]:
    """Each turn's end-of-turn timers for `role`, one per forced switch, in order."""
    out: dict[int, list] = {}
    for s, j in zip(game.states[role], game.joined[role]):
        if s["moment"] == "after_turn":
            out.setdefault(s["turn"], []).append(j)
    return out


def examples_for_game(
    tag: str, log: str, fmt: str, dex, table, calc, store, bring
) -> list[tuple[np.ndarray, int]]:
    """Every forced switch the log shows: for each slot filled, its options'
    facts and which one came in."""
    from wpa import decisions as D
    from wpa.features import _field
    from wpa.policy_data import game_tools

    sheets, spreads, odds = game_tools(tag, log, fmt, store, bring, dex)
    if set(sheets) != {"p1", "p2"}:
        return []
    game = D.build_game(log, table)
    timers = {r: after_turn_timers(game, r) for r in ("p1", "p2")}
    seen: dict[tuple[str, int], int] = {}
    out = []
    for r in C.replacements(log):
        n = seen.get((r.role, r.turn), 0)
        seen[(r.role, r.turn)] = n + 1
        js = timers[r.role].get(r.turn, [])
        j = js[n] if n < len(js) else None
        opts = options(r, sheets, spreads, dex, calc, odds, _field(j) if j else None)
        for slot, new in r.taken.items():
            if slot not in opts:
                continue
            o, X = opts[slot]
            picks = [a.switch_to for a in o]
            if new in picks:
                out.append((X, picks.index(new)))
    return out


def collect(a) -> None:  # pragma: no cover - runs on the corpus
    from wpa.bring import BringModel
    from wpa.damage import Calc
    from wpa.formats import format_of
    from wpa.policy_data import _iter_logs
    from wpa.spreads import UsageStore

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    if getattr(a, "dex_tables", None):
        dexes, tables = pickle.load(open(a.dex_tables, "rb"))
    else:
        from wpa.durations import load_all
        from wpa.team_sheets import load_dexes

        dexes, tables = load_dexes(a.showdown), load_all(a.showdown)
    from wpa.policy_data import format_caps

    fmts = tuple(getattr(a, "formats", None) or ("regma", "regmb"))
    caps, vcaps = format_caps(fmts, a.games, a.val_games)
    picked: dict[str, dict[str, list]] = {
        "train": {f: [] for f in fmts},
        "validation": {f: [] for f in fmts},
    }
    for tag, log in _iter_logs(a.logs):
        split = splits.get(tag)
        if split not in picked:
            continue  # the test split is never read
        try:
            fmt = format_of(tag)
        except Exception:
            continue
        if fmt not in fmts:
            continue
        cap = caps[fmt] if split == "train" else vcaps[fmt]
        if len(picked[split][fmt]) < cap:
            picked[split][fmt].append((tag, log))
    store = UsageStore(a.usage)
    bring = BringModel.load(a.bring) if a.bring and Path(a.bring).exists() else None
    groups: dict[str, dict[str, list]] = {"train": {}, "validation": {}}
    with Calc() as calc:
        for split in groups:
            for fmt in fmts:
                g = []
                for tag, log in picked[split][fmt]:
                    g += examples_for_game(
                        tag, log, fmt, dexes[fmt], tables[fmt], calc, store, bring
                    )
                groups[split][fmt] = g
                print(
                    f"{split} {fmt}: {len(picked[split][fmt])} games, "
                    f"{len(g)} forced switches",
                    flush=True,
                )
    model = fit([g for f in fmts for g in groups["train"][f]])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(a.out)
    lines = [
        "Forced-switch model (Week 10 Task 6), validation: mean log chance of the "
        "Pokemon sent in, against a uniform guess over those that could come in"
    ]
    for fmt in fmts:
        v = [(X, c) for X, c in groups["validation"][fmt] if len(X) > 1]
        ll, un = score(model, v)
        top = float(np.mean([int(np.argmax(model.chances(X)) == c) for X, c in v]))
        guess = float(np.mean([1 / len(X) for X, _ in v]))
        lines.append(
            f"  {fmt}: {len(v)} forced switches with a choice; model {ll:.3f}, "
            f"uniform {un:.3f} ({'beats' if ll > un else 'DOES NOT BEAT'} it); "
            f"most likely Pokemon right {100 * top:.1f}% (uniform {100 * guess:.1f}%)"
        )
    lines.append(
        "  weights: "
        + ", ".join(f"{k} {w:+.2f}" for k, w in zip(FEATURES, model.weights))
    )
    text = "\n".join(lines)
    print(text)
    Path(a.out).with_suffix(".txt").write_text(text + "\n", encoding="utf-8")


def main() -> None:  # pragma: no cover - runs on the corpus
    p = argparse.ArgumentParser(
        description="Fit the forced-switch model (Week 10 Task 6)."
    )
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--bring", type=Path, default=Path("models_v4/bring.json"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument(
        "--dex-tables",
        type=Path,
        default=None,
        help="a pickled (dexes, tables) pair, instead of reading Showdown",
    )
    p.add_argument(
        "--formats",
        nargs="+",
        default=["regma", "regmb"],
        help="the formats fitted together (Reg M-C: alone, into its own file)",
    )
    p.add_argument(
        "--games",
        type=int,
        nargs="+",
        default=[1500, 2000],
        help="training games, one count per format",
    )
    p.add_argument("--val-games", type=int, nargs="+", default=[1000, 400])
    p.add_argument("--out", type=Path, default=Path("models_v4/replace.json"))
    collect(p.parse_args())


if __name__ == "__main__":
    main()
