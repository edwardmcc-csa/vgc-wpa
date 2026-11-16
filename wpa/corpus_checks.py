"""Two checks on a format's corpus (Week 15 Task 4, raised in Week 14's report).

1. **A few accounts play a lot.** On Reg M-C the three busiest accounts are in
   about a tenth of the games. Do they shape the models? Each model is trained
   three ways on the same training split: on everything; without every set
   that has one of those accounts; and, as the control, without as many sets
   drawn at random. Leaving data out costs a little on its own, so the
   question is the second against the control, scored on the validation split
   (all of it, and its games with and without those accounts).
   - the win model: one model each, with the averaged model's settings (not
     the average of 10, which would take ten times as long);
   - the choice model: the same training games as `wpa.policy`, and the same
     move rates (the saved model's), so only the games fitted differ.
2. **By rating band.** The ladder is mostly below the bot's target. The win
   model (the average of 10) and the choice model, as saved, scored on the
   validation split by the rating its replay shows (about a third show one).

Accounts are named by number in the report, never by name. The test split is
never read: the busiest accounts are counted on training games.

Run (Runbook Section 28):
    python -m wpa.corpus_checks
        --raw battle_logs_mc\\logs_gen9championsvgc2026regmcbo3.jsonl
        --logs logs_mc --features features_v4b_mc --format regmc
        --policy models_v4\\regmc\\policy.json --bring models_v4\\regmc\\bring.json
        --work build\\w15\\checks --out reports\\corpus_checks_mc.txt
It keeps what it has trained in `--work`, so a rerun carries on.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np

from wpa.features import Table

BANDS = (
    (0, 1100, "under 1100"),
    (1100, 1300, "1100 to 1299"),
    (1300, 1500, "1300 to 1499"),
    (1500, 10**6, "1500 and up"),
)
UNRATED = "no rating shown"
SMALL = 100  # games: a band with fewer is marked a small sample


class Game(NamedTuple):
    players: tuple[str, ...]
    rating: int | None


# --------------------------------------------------------------------------
# The pieces (tested on their own)
# --------------------------------------------------------------------------


def player_id(name: str) -> str:
    """Showdown's id for an account: lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def read_games(path: Path | str) -> dict[str, Game]:
    """Each game's two accounts and the rating its replay shows (None when it
    shows none), from the download's `.jsonl` (`wpa.fetch_replays`)."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            rating = r.get("rating")
            out[r["id"]] = Game(
                tuple(player_id(p) for p in r.get("players") or ()),
                int(rating) if rating else None,
            )
    return out


def busiest(games: Mapping[str, Game], tags: Iterable[str], n: int) -> list:
    """The `n` accounts in most of these games, with their counts (ties by id)."""
    c: Counter = Counter()
    for t in tags:
        if t in games:
            c.update(set(games[t].players))
    return sorted(c.items(), key=lambda x: (-x[1], x[0]))[:n]


def with_players(games: Mapping[str, Game], players: Collection[str]) -> set:
    """The games any of these accounts played in."""
    ps = set(players)
    return {t for t, g in games.items() if ps & set(g.players)}


def band(rating: int | None) -> str:
    if not rating:
        return UNRATED
    return next(name for lo, hi, name in BANDS if lo <= rating < hi)


def ordered_bands(names: Iterable[str]) -> list[str]:
    order = [name for _lo, _hi, name in BANDS] + [UNRATED]
    present = set(names)
    return [b for b in order if b in present]


def units_with(table: Table, tags: Collection[str]) -> np.ndarray:
    """The sets (units) with a game among `tags`: a set leaves whole."""
    mask = np.isin(table.tag, np.array(sorted(tags), dtype=table.tag.dtype))
    return np.unique(table.unit[mask])


def drop_units(table: Table, units: np.ndarray) -> Table:
    from wpa.evaluate import subset

    return subset(table, ~np.isin(table.unit, units))


def control_units(units: np.ndarray, k: int, seed: int) -> np.ndarray:
    """`k` of these sets drawn at random (fixed by `seed`), for the control."""
    uniq = np.unique(units)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(uniq, size=min(k, len(uniq)), replace=False))


def _by_group(values: np.ndarray, groups: np.ndarray):
    _, inv = np.unique(groups, return_inverse=True)
    return np.bincount(inv, weights=values), np.bincount(inv).astype(np.float64)


def _boot(sums, counts, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(sums)
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, n, n)
        out[i] = sums[pick].sum() / counts[pick].sum()
    return out


def mean_ci(values, groups, draws: int = 500, seed: int = 0) -> tuple:
    """The mean, with a 95% interval from resampling whole groups (games)."""
    v = np.asarray(values, dtype=np.float64)
    boot = _boot(*_by_group(v, np.asarray(groups)), draws, seed)
    return (
        float(v.mean()),
        float(np.percentile(boot, 2.5)),
        float(np.percentile(boot, 97.5)),
    )


def paired_ci(a, b, groups, draws: int = 500, seed: int = 0) -> tuple:
    """mean(a - b), paired, with the same interval."""
    return mean_ci(np.asarray(a, float) - np.asarray(b, float), groups, draws, seed)


def verdict(diff: tuple, higher_is_better: bool = False) -> str:
    """Without the accounts against the control: a change only when the 95%
    interval leaves zero out. Brier: lower is better; log chance: higher."""
    _d, lo, hi = diff
    if lo <= 0 <= hi:
        return "no change beyond the noise"
    better = (lo > 0) == higher_is_better
    return "better without them" if better else "worse without them"


# --------------------------------------------------------------------------
# The runs (on the PO's computer)
# --------------------------------------------------------------------------


def _fmt_ci(t: tuple, digits: int = 4) -> str:
    v, lo, hi = t
    return f"{v:+.{digits}f} [{lo:+.{digits}f}, {hi:+.{digits}f}]"


def _win_models(a, heavy_tags: set, lines: list) -> None:  # pragma: no cover
    """The win model trained three ways; their validation Brier."""
    from wpa.evaluate import (
        V2_GRID_ENTRY,
        _train_until,
        brier_ci,
        difference_ci,
        load_table,
        select,
    )
    from wpa.model import GRID, load, save

    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    val = select(load_table(a.features, a.format, "validation"), a.groups)
    full = select(load_table(a.features, a.format, "train"), a.groups)
    heavy_units = units_with(full, heavy_tags)
    control = control_units(np.unique(full.unit), len(heavy_units), a.seed)
    n_units = len(np.unique(full.unit))
    del full
    arms = {"all": np.array([], dtype=str), "without": heavy_units, "control": control}
    preds = {}
    for name, drop in arms.items():
        pkl = work / f"win_{name}.pkl"
        if not pkl.exists():
            t = select(load_table(a.features, a.format, "train"), a.groups)
            t = drop_units(t, drop)
            print(f"win model, {name}: {len(np.unique(t.unit))} sets", flush=True)
            model, info = _train_until(
                t, val, GRID[V2_GRID_ENTRY], work / f"win_{name}.ckpt", 0.0
            )
            assert model is not None
            save(model, pkl)
            (work / f"win_{name}.ckpt").unlink(missing_ok=True)
            del t
        preds[name] = np.asarray(load(pkl, val.columns).predict(val.X), float)
    y, units = val.y, val.unit
    in_val = np.isin(val.tag, np.array(sorted(heavy_tags), dtype=val.tag.dtype))
    lines += [
        "  The win model: one model each, the averaged model's settings, on Reg "
        "M-C's validation split",
        f"    sets left out: {len(heavy_units)} of {n_units} with those accounts; "
        f"the control leaves out {len(control)} drawn at random",
    ]
    for label, m in (
        ("all validation games", np.ones_like(in_val)),
        ("validation games with one of them", in_val),
        ("validation games without them", ~in_val),
    ):
        if not m.any():
            continue
        b = {k: brier_ci(p[m], y[m], units[m]) for k, p in preds.items()}
        d = difference_ci(preds["without"][m], preds["control"][m], y[m], units[m])
        d_all = difference_ci(preds["control"][m], preds["all"][m], y[m], units[m])
        lines += [
            f"    {label} ({int(m.sum())} decision points):",
            f"      Brier: trained on all {b['all'][0]:.4f}, without them "
            f"{b['without'][0]:.4f}, control {b['control'][0]:.4f}",
            f"      without them against the control: {_fmt_ci(d)}; {verdict(d)}",
            f"      (what leaving that much out costs: control against all "
            f"{_fmt_ci(d_all)})",
        ]


def _choice_tools(a):  # pragma: no cover
    from wpa.durations import FORMAT_MODS, load_all, showdown_for
    from wpa.resolver import load_moves, load_moves_file
    from wpa.team_sheets import load_dexes

    dexes, tables = load_dexes(a.showdown), load_all(a.showdown)
    mod = FORMAT_MODS[a.format]
    saved = Path(a.moves_dir or ".") / f"moves_{a.format}.json"
    moves = (
        load_moves_file(saved)
        if a.moves_dir and saved.exists()
        else load_moves(showdown_for(a.format, a.showdown), mod)
    )
    return dexes[a.format], tables[a.format], moves


def _choice_models(a, games, heavy_tags: set, lines: list) -> dict:  # pragma: no cover
    """The choice model fitted three ways on the same training games, and every
    validation choice scored by them and by the saved model. Returns the saved
    model's per-choice scores for the rating bands."""
    from wpa.bring import BringModel
    from wpa.damage import Calc
    from wpa.formats import format_of
    from wpa.policy import PolicyModel, fit
    from wpa.policy_data import _iter_logs, examples_for_game
    from wpa.spreads import UsageStore

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    saved = PolicyModel.load(a.policy)
    rates = saved.rates[a.format]
    dex, table, moves = _choice_tools(a)
    store = UsageStore(a.usage)
    bring = BringModel.load(a.bring)
    train: list = []
    val_games: list = []
    for tag, log in _iter_logs(a.logs):
        split = splits.get(tag)
        try:
            if format_of(tag) != a.format:
                continue
        except Exception:
            continue
        if split == "train" and len(train) < a.choice_games:
            train.append((tag, log))
        elif split == "validation" and len(val_games) < (a.val_games or 10**9):
            val_games.append((tag, log))
    tags = [t for t, _ in train]
    drop = {t for t in tags if t in heavy_tags}
    control = set(control_units(np.array(tags), len(drop), a.seed))
    fits = {}
    with Calc() as calc:

        def examples(tag, log):
            return examples_for_game(
                tag, log, a.format, dex, moves, table, calc, store, bring, rates
            )

        ex = [(t, x) for t, log in train for x in examples(t, log)]
        print(
            f"choice model: {len(train)} training games, {len(ex)} choices", flush=True
        )
        for name, out in (("all", set()), ("without", drop), ("control", control)):
            fits[name] = fit([x for t, x in ex if t not in out])
        del ex
        rows = []
        for i, (tag, log) in enumerate(val_games):
            for X, c in examples(tag, log):
                rows.append(
                    (
                        tag,
                        *(
                            float(np.log(max(m.chances(X)[c], 1e-300)))
                            for m in (
                                fits["all"],
                                fits["without"],
                                fits["control"],
                                saved,
                            )
                        ),
                        float(np.log(1 / len(X))),
                        int(np.argmax(saved.chances(X)) == c),
                    )
                )
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{len(val_games)} validation games", flush=True)
    g = np.array([r[0] for r in rows])
    s = {
        k: np.array([r[j] for r in rows])
        for j, k in enumerate(
            ("all", "without", "control", "saved", "uniform", "top"), start=1
        )
    }
    in_val = np.isin(g, np.array(sorted(heavy_tags), dtype=g.dtype))
    lines += [
        "",
        "  The choice model: mean log chance of the option chosen (higher is "
        "better), on Reg M-C's validation split",
        f"    training games: {len(train)}; {len(drop)} with those accounts left "
        f"out, against {len(control)} drawn at random",
    ]
    for label, m in (
        ("all validation choices", np.ones_like(in_val)),
        ("choices in games with one of them", in_val),
        ("choices in games without them", ~in_val),
    ):
        if not m.any():
            continue
        d = paired_ci(s["without"][m], s["control"][m], g[m])
        d_all = paired_ci(s["control"][m], s["all"][m], g[m])
        lines += [
            f"    {label} ({int(m.sum())}):",
            f"      fitted on all {s['all'][m].mean():.4f}, without them "
            f"{s['without'][m].mean():.4f}, control {s['control'][m].mean():.4f} "
            f"(uniform {s['uniform'][m].mean():.4f})",
            f"      without them against the control: {_fmt_ci(d)}; "
            f"{verdict(d, higher_is_better=True)}",
            f"      (control against all {_fmt_ci(d_all)})",
        ]
    return {"games": g, **s}


def _bands_win(a, games, lines: list) -> None:  # pragma: no cover
    from wpa.ensemble import load_averaged
    from wpa.evaluate import (
        COIN_FLIP,
        brier_ci,
        difference_ci,
        load_table,
        select,
        v0_from_table,
    )
    from wpa.formats import model_for

    raw = load_table(a.features, a.format, "validation")
    v0 = v0_from_table(raw)
    x = select(raw, a.groups)
    model = load_averaged(a.models, model_for(a.format), a.groups, x.columns)
    assert model is not None, "the averaged model first (wpa.ensemble finish)"
    p = model.predict(x.X)
    names = np.array([band(games[t].rating if t in games else None) for t in x.tag])
    lines += [
        "",
        "2. By the rating a game's replay shows (validation split)",
        "",
        "  The win model (the average of 10): Brier [95%], v0's, the model against v0",
    ]
    for b in ordered_bands(names):
        m = names == b
        n_games = len(set(x.tag[m]))
        br = brier_ci(p[m], x.y[m], x.unit[m])
        b0 = brier_ci(v0[m], x.y[m], x.unit[m])
        d = difference_ci(p[m], v0[m], x.y[m], x.unit[m])
        small = "  SMALL SAMPLE" if n_games < SMALL else ""
        lines.append(
            f"    {b}: {n_games} games, {int(m.sum())} decision points; Brier "
            f"{br[0]:.4f} [{br[1]:.4f}, {br[2]:.4f}], "
            f"skill {1 - br[0] / COIN_FLIP:+.3f}; v0 {b0[0]:.4f}; "
            f"against v0 {_fmt_ci(d)}{small}"
        )


def _bands_choice(s: dict, games, lines: list) -> None:  # pragma: no cover
    names = np.array(
        [band(games[t].rating if t in games else None) for t in s["games"]]
    )
    lines += [
        "",
        "  The choice model (as saved): mean log chance of the option chosen "
        "[95%], uniform's, the likeliest option right",
    ]
    for b in ordered_bands(names):
        m = names == b
        n_games = len(set(s["games"][m]))
        ll = mean_ci(s["saved"][m], s["games"][m])
        small = "  SMALL SAMPLE" if n_games < SMALL else ""
        lines.append(
            f"    {b}: {n_games} games, {int(m.sum())} choices; model {ll[0]:.3f} "
            f"[{ll[1]:.3f}, {ll[2]:.3f}], uniform {s['uniform'][m].mean():.3f}; "
            f"likeliest right {100 * s['top'][m].mean():.1f}%{small}"
        )


def run(a) -> str:  # pragma: no cover - about an hour on the corpus
    games = read_games(a.raw)
    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    train_tags = [t for t in games if splits.get(t) == "train"]
    val_tags = [t for t in games if splits.get(t) == "validation"]
    top = busiest(games, train_tags, a.busiest)
    heavy = with_players(games, [p for p, _ in top])
    name = {"regma": "Reg M-A", "regmb": "Reg M-B", "regmc": "Reg M-C"}.get(
        a.format, a.format
    )
    lines = [
        f"Two checks on the {name} corpus (Week 15 Task 4)",
        "",
        f"1. A few accounts play a lot: the {a.busiest} busiest in training",
        "  "
        + "; ".join(
            f"account {i + 1}: {c} training games" for i, (_p, c) in enumerate(top)
        ),
        f"  games with one of them: {len(heavy & set(train_tags))} of "
        f"{len(train_tags)} training games, {len(heavy & set(val_tags))} of "
        f"{len(val_tags)} validation games",
        "",
    ]
    # the quick parts first, so a problem shows early; the report in order
    bands: list = []
    _bands_win(a, games, bands)
    choice: list = []
    s = _choice_models(a, games, heavy, choice)
    _bands_choice(s, games, bands)
    win: list = []
    _win_models(a, heavy, win)
    text = "\n".join(lines + win + choice + bands) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    return text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--raw", type=Path, required=True, help="the download's .jsonl")
    p.add_argument("--logs", type=Path, required=True)
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--format", required=True)
    p.add_argument("--groups", default="ABCDEFGHIJ")
    p.add_argument("--models", type=Path, default=Path("models_v4_avg"))
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--bring", type=Path, required=True)
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--busiest", type=int, default=3)
    p.add_argument(
        "--choice-games",
        type=int,
        default=2000,
        help="training games for the choice model (as `wpa.policy`)",
    )
    p.add_argument(
        "--val-games",
        type=int,
        default=None,
        help="at most this many validation games for the choice model (a quick try)",
    )
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    print(run(parser().parse_args(argv)))


if __name__ == "__main__":
    main()
