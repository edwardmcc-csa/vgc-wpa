"""Evaluation, ablation and the gate for the v1 model (Week 5 Task 7).

Everything is per format. Every Brier comes with a confidence interval from
resampling whole *units* (a best-of-three set or a single game): the states of
one game are not independent, so resampling states would claim far more
certainty than the data holds.

The test split is opened by one command, which records the date and git commit
each time it is used (`record_test_opening`); it is never used to choose
anything.

Commands (all from the repository folder, after building the feature table):

    python -m wpa.evaluate train --format regma
    python -m wpa.evaluate ablation --format regma
    python -m wpa.evaluate check
    python -m wpa.evaluate final
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from wpa.features import Table, columns, concat, read_rows
from wpa.metrics import calibration_failures, calibration_table

COIN_FLIP = 0.25
TOLERANCE = 0.05  # calibration gap per bin (placeholder carried from Week 4)
MIN_BIN = 100
GROUP_STEPS = ("A", "AB", "ABC", "ABCD", "ABCDE")


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def load_table(
    features_dir: Path | str, fmt: str, split: str, sample: float = 1.0
) -> Table:
    """All parts of one format and split; `sample` keeps that fraction of units
    (whole), part by part, so a sample never needs the full table in memory."""
    parts = sorted((Path(features_dir) / fmt / split).glob("part-*.npz"))
    if not parts:
        raise FileNotFoundError(f"no feature files for {fmt}/{split} in {features_dir}")
    if sample >= 1.0:
        return concat(read_rows(p) for p in parts)
    return concat(
        subset(t, sample_units(t.unit, sample)) for t in map(read_rows, parts)
    )


def select(table: Table, groups: str) -> Table:
    """Only the columns of these feature groups, in the standard order."""
    wanted = columns(groups)
    if wanted == list(table.columns):
        return table  # nothing to drop: no copy of a large table
    index = {c: i for i, c in enumerate(table.columns)}
    idx = [index[c] for c in wanted]
    return Table(
        table.X[:, idx], table.y, table.tag, table.role, table.unit, table.turn, wanted
    )


def sample_units(
    units: np.ndarray, fraction: float, seed: str = "wpa-sample"
) -> np.ndarray:
    """Boolean mask keeping a fixed fraction of units, whole."""
    uniq, inverse = np.unique(units, return_inverse=True)
    keep = np.array(
        [
            int.from_bytes(hashlib.sha256(f"{seed}|{u}".encode()).digest()[:4], "big")
            / 2**32
            < fraction
            for u in uniq
        ]
    )
    return keep[inverse]


def subset(table: Table, mask: np.ndarray) -> Table:
    return Table(
        table.X[mask],
        table.y[mask],
        table.tag[mask],
        table.role[mask],
        table.unit[mask],
        table.turn[mask],
        table.columns,
    )


def with_format_flag(table: Table, value: float) -> Table:
    """Add a `z_format_regmb` column (1 for Reg M-B rows): for the secondary
    pooled model only. The headline models never see it."""
    flag = np.full((len(table.y), 1), value, dtype=np.float32)
    return Table(
        np.hstack([table.X, flag]),
        table.y,
        table.tag,
        table.role,
        table.unit,
        table.turn,
        [*table.columns, "z_format_regmb"],
    )


# --------------------------------------------------------------------------
# The v0 baseline, from the same rows
# --------------------------------------------------------------------------


def v0_from_table(table: Table) -> np.ndarray:
    """wpa.baseline's prediction, computed from group A columns.

    strength = hit points of revealed living Pokemon + 1 per unseen brought one
    (four brought, minus fainted, minus revealed living); p = sigmoid(diff).
    """
    c = {name: i for i, name in enumerate(table.columns)}

    def strength(side: str) -> np.ndarray:
        hp = table.X[:, c[f"a_{side}_hp_seen"]].astype(np.float64)
        remaining = table.X[:, c[f"a_{side}_remaining"]].astype(np.float64)
        seen = table.X[:, c[f"a_{side}_seen_alive"]].astype(np.float64)
        return hp + np.maximum(0.0, remaining - seen)

    d = strength("our") - strength("their")
    return 1.0 / (1.0 + np.exp(-d))


# --------------------------------------------------------------------------
# Brier with unit-bootstrap intervals
# --------------------------------------------------------------------------


def _per_unit(err: np.ndarray, units: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, inverse = np.unique(units, return_inverse=True)
    sums = np.bincount(inverse, weights=err)
    counts = np.bincount(inverse).astype(np.float64)
    return sums, counts


def _bootstrap(
    sums: np.ndarray, counts: np.ndarray, draws: int, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(sums)
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, n, n)
        out[i] = sums[pick].sum() / counts[pick].sum()
    return out


def brier_ci(
    p, y, units, draws: int = 500, seed: int = 0
) -> tuple[float, float, float]:
    err = (np.asarray(p, dtype=np.float64) - np.asarray(y, dtype=np.float64)) ** 2
    sums, counts = _per_unit(err, np.asarray(units))
    boot = _bootstrap(sums, counts, draws, seed)
    return (
        float(err.mean()),
        float(np.percentile(boot, 2.5)),
        float(np.percentile(boot, 97.5)),
    )


def difference_ci(
    p, q, y, units, draws: int = 500, seed: int = 0
) -> tuple[float, float, float]:
    """Brier(p) - Brier(q), paired, with a unit-bootstrap interval."""
    y = np.asarray(y, dtype=np.float64)
    diff = (np.asarray(p) - y) ** 2 - (np.asarray(q) - y) ** 2
    sums, counts = _per_unit(diff, np.asarray(units))
    boot = _bootstrap(sums, counts, draws, seed)
    return (
        float(diff.mean()),
        float(np.percentile(boot, 2.5)),
        float(np.percentile(boot, 97.5)),
    )


def score(p, y, units, v0, draws: int = 500) -> dict:
    """Everything the report and the gate need for one format and one model."""
    p = np.asarray(p, dtype=np.float64)
    b, lo, hi = brier_ci(p, y, units, draws)
    b0, lo0, hi0 = brier_ci(v0, y, units, draws)
    d, dlo, dhi = difference_ci(p, v0, y, units, draws)
    table = calibration_table(list(p), [bool(v) for v in y])
    fails = calibration_failures(table, TOLERANCE, MIN_BIN)
    return {
        "rows": int(len(y)),
        "units": int(len(np.unique(units))),
        "brier": b,
        "brier_ci": [lo, hi],
        "skill": 1 - b / COIN_FLIP,
        "v0_brier": b0,
        "v0_brier_ci": [lo0, hi0],
        "minus_v0": d,
        "minus_v0_ci": [dlo, dhi],
        "calibration": [
            {
                "low": c.low,
                "high": c.high,
                "n": c.n,
                "predicted": c.mean_predicted,
                "observed": c.observed_rate,
            }
            for c in table
        ],
        "calibration_failures": [[c.low, c.high] for c in fails],
    }


def gate_failures(results: dict[str, dict]) -> list[str]:
    """Why the gate fails, per format (empty: it passes)."""
    out = []
    for fmt, r in sorted(results.items()):
        if not r["brier"] < r["v0_brier"]:
            out.append(
                f"{fmt}: v1 Brier {r['brier']:.4f} does not beat v0 {r['v0_brier']:.4f}"
            )
        if not r["brier"] < COIN_FLIP:
            out.append(
                f"{fmt}: v1 Brier {r['brier']:.4f} does not beat the coin flip 0.25"
            )
        for low, high in r["calibration_failures"]:
            out.append(
                f"{fmt}: calibration bin {low:.1f}-{high:.1f} is outside the "
                f"tolerance {TOLERANCE}"
            )
    return out


def trend(p: np.ndarray, table: Table) -> list[tuple[int, int, int, float]]:
    """(our remaining, their remaining, rows, mean predicted): reported, not gated."""
    c = {n: i for i, n in enumerate(table.columns)}
    our = table.X[:, c["a_our_remaining"]].astype(int)
    their = table.X[:, c["a_their_remaining"]].astype(int)
    out = []
    for a in range(5):
        for b in range(5):
            m = (our == a) & (their == b)
            if m.sum() >= 30:
                out.append((a, b, int(m.sum()), float(p[m].mean())))
    return out


# --------------------------------------------------------------------------
# The test split's log
# --------------------------------------------------------------------------


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def record_test_opening(path: Path | str, info: dict) -> int:
    """Append a record of opening the test split; return how many times it has been."""
    path = Path(path)
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    records.append(
        {
            "date": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "commit": _commit(),
            **info,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=1), encoding="utf-8")
    return len(records)


def _fmt_ci(x: float, ci) -> str:
    return f"{x:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]"


def describe(fmt: str, name: str, r: dict) -> str:
    small = "  SMALL SAMPLE" if r["units"] < 500 else ""
    lines = [
        f"{fmt} {name}: {r['rows']} decision points in {r['units']} units{small}",
        f"  Brier {_fmt_ci(r['brier'], r['brier_ci'])}  skill {r['skill']:+.3f}",
        f"  v0    {_fmt_ci(r['v0_brier'], r['v0_brier_ci'])}",
        f"  model - v0 {_fmt_ci(r['minus_v0'], r['minus_v0_ci'])}",
    ]
    for c in r["calibration"]:
        if c["n"]:
            flag = (
                "  <-- outside tolerance"
                if [c["low"], c["high"]] in r["calibration_failures"]
                else ""
            )
            lines.append(
                f"  {c['low']:.1f}-{c['high']:.1f} n={c['n']:<7d} predicted "
                f"{c['predicted']:.3f} observed {c['observed']:.3f}{flag}"
            )
    return "\n".join(lines)


def _isnan(x) -> bool:
    return isinstance(x, float) and math.isnan(x)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _paths(models: Path, fmt: str) -> Path:
    d = models / fmt
    d.mkdir(parents=True, exist_ok=True)
    return d


def _train_until(train, val, params, ckpt: Path, seconds: float):
    import time

    from wpa.model import fit

    # sklearn would convert to float64 on every warm-start step; doing it once,
    # in place, means a float32 and a float64 copy are never both held
    train.X = np.ascontiguousarray(train.X, dtype=np.float64)
    start = time.time()
    while True:
        model, info = fit(train, val, params, checkpoint=ckpt, max_steps=1)
        if info["done"] or (seconds and time.time() - start > seconds):
            return model, info


def _cmd_train(a) -> None:
    import time

    from wpa.model import GRID, save

    if not hasattr(a, "deadline"):
        a.deadline = time.time() + a.seconds if a.seconds else 0.0

    d = _paths(a.models, a.format)
    train = select(load_table(a.features, a.format, "train", a.sample), a.groups)
    val = select(load_table(a.features, a.format, "validation"), a.groups)
    which = range(len(GRID)) if a.grid == "all" else [int(a.grid)]
    for i in which:
        name = f"grid{i}" if a.groups == "ABCDE" else f"ablation_{a.groups}"
        if (d / f"{name}.json").exists():
            print(f"{a.format} {name}: already done")
            continue
        params = GRID[i]
        left = a.deadline - time.time() if a.deadline else 0.0
        if a.deadline and left <= 0:
            print(f"{a.format} {name}: out of time; run the same command again")
            return
        model, info = _train_until(train, val, params, d / f"{name}.ckpt", left)
        if model is None:
            print(
                f"{a.format} {name}: not finished after {info['curve'][-1][0]} rounds; "
                "run the same command again to carry on"
            )
            return
        save(model, d / f"{name}.pkl")
        info.update(
            {
                "grid": i,
                "groups": a.groups,
                "sample": a.sample,
                "train_rows": int(len(train.y)),
                "train_units": int(len(np.unique(train.unit))),
            }
        )
        (d / f"{name}.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
        (d / f"{name}.ckpt").unlink(missing_ok=True)
        print(
            f"{a.format} {name}: validation Brier {info['best_validation_brier']:.4f} "
            f"after {info['n_iter']} rounds"
        )


def _cmd_select(a) -> None:
    from wpa.model import load, recalibrate, save

    d = _paths(a.models, a.format)
    runs = []
    for p in sorted(d.glob("grid*.json")):
        info = json.loads(p.read_text(encoding="utf-8"))
        runs.append((info["best_validation_brier"], p.stem, info))
    if not runs:
        raise SystemExit("no finished grid runs; run `train` first")
    runs.sort()
    brier, name, info = runs[0]
    val = select(load_table(a.features, a.format, "validation"), "ABCDE")
    model = load(d / f"{name}.pkl", val.columns)
    before = score(model.predict(val.X), val.y, val.unit, v0_from_table(val))
    chosen = {
        "from": name,
        "params": info["params"],
        "n_iter": info["n_iter"],
        "sample": info["sample"],
        "recalibrated": False,
        "grid": [(r[1], r[0]) for r in runs],
    }
    if before["calibration_failures"]:
        recal = recalibrate(model, val)
        after = score(recal.predict(val.X), val.y, val.unit, v0_from_table(val))
        if after["brier"] <= before["brier"] and len(
            after["calibration_failures"]
        ) <= len(before["calibration_failures"]):
            model, chosen["recalibrated"] = recal, True
            chosen["before_recalibration"] = {
                "brier": before["brier"],
                "failures": before["calibration_failures"],
            }
    save(model, d / "v1.pkl")
    (d / "v1.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    print(
        f"{a.format}: chose {name} (validation Brier {brier:.4f}); "
        f"recalibrated: {chosen['recalibrated']}"
    )


def _cmd_ablation(a) -> None:
    import time

    from wpa.model import GRID

    a.deadline = time.time() + a.seconds if a.seconds else 0.0
    d = _paths(a.models, a.format)
    chosen = json.loads((d / "v1.json").read_text(encoding="utf-8"))
    a.grid = str(GRID.index(chosen["params"]))
    for groups in a.steps:
        if groups == "ABCDE":
            continue
        a.groups = groups
        if a.deadline and time.time() > a.deadline:
            print(f"{a.format}: out of time; run the same command again")
            return
        _cmd_train(a)


def _validation_results(a, fmt: str) -> tuple[dict, list, tuple]:
    from wpa.model import load

    d = a.models / fmt
    val_full = load_table(a.features, fmt, "validation")
    v0 = v0_from_table(val_full)
    model = load(d / "v1.pkl", columns("ABCDE"))
    p = model.predict(select(val_full, "ABCDE").X)
    rows = [("v0", score(v0, val_full.y, val_full.unit, v0))]
    for groups in GROUP_STEPS:
        name = "v1.pkl" if groups == "ABCDE" else f"ablation_{groups}.pkl"
        if not (d / name).exists():
            continue
        m = load(d / name, columns(groups))
        q = p if groups == "ABCDE" else m.predict(select(val_full, groups).X)
        rows.append((groups, score(q, val_full.y, val_full.unit, v0)))
    return rows[-1][1] if rows[-1][0] == "ABCDE" else {}, rows, (p, val_full)


def _cmd_report(a) -> None:
    out = ["=== v1 on the validation split ==="]
    for fmt in a.formats:
        if not (a.models / fmt / "v1.pkl").exists():
            continue
        v1, rows, (p, val) = _validation_results(a, fmt)
        chosen = json.loads((a.models / fmt / "v1.json").read_text(encoding="utf-8"))
        out.append(
            f"\n{fmt}: model {chosen['from']}, {chosen['n_iter']} rounds, "
            f"training sample {chosen['sample']:.0%} of units, recalibrated "
            f"{chosen['recalibrated']}"
        )
        out.append("  ablation (validation Brier [95% interval by unit], minus v0):")
        for name, r in rows:
            out.append(
                f"    {name:6s} {_fmt_ci(r['brier'], r['brier_ci'])}  "
                f"minus v0 {_fmt_ci(r['minus_v0'], r['minus_v0_ci'])}"
            )
        if v1:
            out.append(describe(fmt, "v1 (ABCDE)", v1))
            out.append("  trend (our left, their left, rows, mean predicted):")
            for t in trend(p, select(val, "A")):
                out.append(f"    {t[0]} v {t[1]}: n={t[2]:<7d} {t[3]:.3f}")
    text = "\n".join(out) + "\n"
    print(text)
    (a.models / "report.txt").write_text(text, encoding="utf-8")


def _cmd_check(a) -> None:
    results = {}
    for fmt in a.formats:
        v1, _rows, _ = _validation_results(a, fmt)
        results[fmt] = v1
        print(describe(fmt, "v1", v1))
    fails = gate_failures(results)
    for f in fails:
        print("FAIL", f)
    print("gate: " + ("FAILED" if fails else "passed"))
    raise SystemExit(1 if fails else 0)


def _cmd_final(a) -> None:
    from wpa.model import load

    n = record_test_opening(a.models / "test_openings.json", {"formats": a.formats})
    if n > 1:
        print(f"NOTE: the test split has now been opened {n} times")
    out = []
    for fmt in a.formats:
        test = load_table(a.features, fmt, "test")
        model = load(a.models / fmt / "v1.pkl", columns("ABCDE"))
        r = score(
            model.predict(select(test, "ABCDE").X),
            test.y,
            test.unit,
            v0_from_table(test),
        )
        (a.models / fmt / "test.json").write_text(
            json.dumps(r, indent=1), encoding="utf-8"
        )
        out.append(describe(fmt, "v1 on the TEST split", r))
    print("\n".join(out))


def _pooled_tables(a):
    ma = with_format_flag(
        select(load_table(a.features, "regma", "train", a.sample), "ABCDE"), 0.0
    )
    mb = with_format_flag(
        select(load_table(a.features, "regmb", "train"), "ABCDE"), 1.0
    )
    val = with_format_flag(
        select(load_table(a.features, "regmb", "validation"), "ABCDE"), 1.0
    )
    return concat([ma, mb]), val


def _cmd_pooled(a) -> None:
    """SECONDARY (PO, 29 Oct): one model on Reg M-A + Reg M-B with a format
    flag, stopped on and scored on Reg M-B only. Same grid entry as M-B's v1."""
    from wpa.model import save

    d = _paths(a.models, "pooled")
    if (d / "pooled.json").exists():
        print("pooled: already trained")
    else:
        chosen = json.loads(
            (a.models / "regmb" / "v1.json").read_text(encoding="utf-8")
        )
        train, val = _pooled_tables(a)
        model, info = _train_until(
            train, val, chosen["params"], d / "pooled.ckpt", a.seconds
        )
        if model is None:
            print(
                f"pooled: not finished after {info['curve'][-1][0]} rounds; run again"
            )
            return
        save(model, d / "pooled.pkl")
        info.update({"sample_regma": a.sample, "train_rows": int(len(train.y))})
        (d / "pooled.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
        (d / "pooled.ckpt").unlink(missing_ok=True)
        print(
            f"pooled: M-B validation Brier {info['best_validation_brier']:.4f} "
            f"after {info['n_iter']} rounds"
        )
    from wpa.model import load

    model = load(d / "pooled.pkl", [*columns("ABCDE"), "z_format_regmb"])
    splits = ["validation"]
    if a.test:
        n = record_test_opening(
            a.models / "test_openings.json", {"formats": ["regmb"], "model": "pooled"}
        )
        print(f"NOTE: the test split has now been opened {n} times")
        splits.append("test")
    for split in splits:
        t = load_table(a.features, "regmb", split)
        x = with_format_flag(select(t, "ABCDE"), 1.0)
        r = score(model.predict(x.X), t.y, t.unit, v0_from_table(t))
        (d / f"regmb_{split}.json").write_text(
            json.dumps(r, indent=1), encoding="utf-8"
        )
        print(describe("regmb", f"POOLED model (secondary) on {split}", r))


# --------------------------------------------------------------------------
# Week 6: v2 on our own decision table
# --------------------------------------------------------------------------

V2_GRID_ENTRY = 2  # the Week 5 winner in both formats, fixed before any v2 result


def _v2_tables(a, groups: str, split: str):
    """(train-or-split table) for a v2 model: Reg M-A, or pooled for Reg M-B."""
    if a.format == "pooled":
        if split == "train":
            ma = with_format_flag(
                select(load_table(a.features, "regma", "train", a.sample), groups), 0.0
            )
            mb = with_format_flag(
                select(load_table(a.features, "regmb", "train"), groups), 1.0
            )
            return concat([ma, mb])
        return with_format_flag(
            select(load_table(a.features, "regmb", split), groups), 1.0
        )
    sample = a.sample if split == "train" else 1.0
    return select(load_table(a.features, a.format, split, sample), groups)


def _cmd_v2_train(a) -> None:
    from wpa.model import GRID, save

    d = _paths(a.models, a.format)
    name = a.groups
    if (d / f"{name}.json").exists():
        print(f"{a.format} {name}: already done")
        return
    train = _v2_tables(a, a.groups, "train")
    val = _v2_tables(a, a.groups, "validation")
    model, info = _train_until(
        train, val, GRID[V2_GRID_ENTRY], d / f"{name}.ckpt", a.seconds
    )
    if model is None:
        print(
            f"{a.format} {name}: not finished after {info['curve'][-1][0]} rounds; "
            "run the same command again to carry on"
        )
        return
    save(model, d / f"{name}.pkl")
    info.update(
        {
            "groups": a.groups,
            "sample": a.sample,
            "train_rows": int(len(train.y)),
            "train_units": int(len(np.unique(train.unit))),
        }
    )
    (d / f"{name}.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    (d / f"{name}.ckpt").unlink(missing_ok=True)
    print(
        f"{a.format} {name}: validation Brier {info['best_validation_brier']:.4f} "
        f"after {info['n_iter']} rounds"
    )


def _v2_predict(a, which: str, groups: str, split: str):
    """Predictions of a saved v2 model on one Reg M-A or Reg M-B split."""
    from wpa.model import load

    fmt = "regmb" if which == "pooled" else which
    raw = load_table(a.features, fmt, split)
    x = select(raw, groups)
    cols = list(x.columns)
    if which == "pooled":
        x = with_format_flag(x, 1.0)
        cols = x.columns
    model = load(a.models / which / f"{groups}.pkl", cols)
    return model, raw, x


GROUP_NAMES = {
    "A": "board",
    "B": "earlier field",
    "C": "timers",
    "D": "sheet capabilities",
    "E": "unseen positions",
    "F": "speed",
    "G": "damage",
    "H": "this turn's options",
    "I": "likely back",
    "J": "whole-board damage",
}


# PO, 30 Oct 2026: recalibrating on Reg M-B's 199 validation sets overshot on the
# test split (Week 7 report), so Reg M-B models are used as trained
NEVER_RECALIBRATE = {"regmb"}


def use_recalibration(fmt: str) -> bool:
    return fmt not in NEVER_RECALIBRATE


def _base_groups(full: str, base: str | None) -> str:
    """The model the report compares with: `base`, or `full` without its last group."""
    return base or full[:-1]


def _group_names(full: str, base: str) -> str:
    return ", ".join(f"{GROUP_NAMES[g]} ({g})" for g in full if g not in base)


def _cmd_v2_report(a) -> None:
    from wpa.model import recalibrate, save

    out = [
        f"=== {a.models.name} ({a.full}) on our decision table: validation split ==="
    ]
    results = {}
    for fmt, which in (("regma", "regma"), ("regmb", "pooled")):
        d = a.models / which
        if not (d / f"{a.full}.pkl").exists():
            continue
        model, raw, x = _v2_predict(a, which, a.full, "validation")
        v0 = v0_from_table(raw)
        p = model.predict(x.X)
        temp = _temperature(d, a.full) if fmt == "regmb" else None
        if temp is not None:
            p = apply_temperature(p, temp)
        r = score(p, raw.y, raw.unit, v0)
        note = "not recalibrated"
        if temp is not None:
            note = f"temperature {temp:.3f}, cross-fitted on training sets"
        if r["calibration_failures"] and not use_recalibration(fmt) and temp is None:
            note = "not recalibrated (never for this format)"
        if r["calibration_failures"] and use_recalibration(fmt):
            recal = recalibrate(model, x)
            r2 = score(recal.predict(x.X), raw.y, raw.unit, v0)
            if r2["brier"] <= r["brier"] and len(r2["calibration_failures"]) <= len(
                r["calibration_failures"]
            ):
                save(recal, d / f"{a.full}.recal.pkl")
                r, note = r2, "recalibrated on validation"
        results[fmt] = r
        out.append(f"\n{fmt} ({which} model, groups {a.full}, {note})")
        out.append(describe(fmt, a.models.name, r))
        base = _base_groups(a.full, a.base)
        if base != a.full and (d / f"{base}.pkl").exists():
            _m0, _raw0, x0 = _v2_predict(a, which, base, "validation")
            q = _m0.predict(x0.X)
            temp0 = _temperature(d, base) if fmt == "regmb" else None
            if temp0 is not None:
                q = apply_temperature(q, temp0)
            dd, lo, hi = difference_ci(p, q, raw.y, raw.unit)
            b0 = brier_ci(q, raw.y, raw.unit)
            added = _group_names(a.full, base)
            out.append(
                f"  base model {base}: Brier "
                f"{_fmt_ci(b0[0], b0[1:])}; adding {added} changes it by "
                f"{dd:+.4f} [{lo:+.4f}, {hi:+.4f}]"
            )
    fails = gate_failures(results)
    out += [f"FAIL {f}" for f in fails]
    out.append("gate: " + ("FAILED" if fails else "passed"))
    text = "\n".join(out) + "\n"
    print(text)
    (a.models / "report.txt").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# Week 8: Reg M-B's one-number correction (PO, 4 Nov), learned by cross-fitting
# --------------------------------------------------------------------------


def apply_temperature(p: np.ndarray, t: float) -> np.ndarray:
    """Sharpen (t < 1) or soften (t > 1) every prediction alike. A prediction and
    its mirror (1 - p) stay mirrors, so the model stays symmetric."""
    q = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    return 1 / (1 + np.exp(-np.log(q / (1 - q)) / t))


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """The temperature that minimises the log loss of `p` against `y`."""
    y = np.asarray(y, dtype=np.float64)

    def loss(log_t: float) -> float:
        q = np.clip(apply_temperature(p, math.exp(log_t)), 1e-9, 1 - 1e-9)
        return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))

    lo, hi = math.log(0.2), math.log(5.0)  # golden-section search on log t
    g = (math.sqrt(5) - 1) / 2
    for _ in range(60):
        a, b = hi - g * (hi - lo), lo + g * (hi - lo)
        if loss(a) < loss(b):
            hi = b
        else:
            lo = a
    return math.exp((lo + hi) / 2)


def unit_folds(units: np.ndarray, k: int, seed: str = "wpa-folds") -> np.ndarray:
    """A fold number (0 to k-1) for each row, whole units (sets) in one fold."""
    uniq, inverse = np.unique(units, return_inverse=True)
    fold = np.array(
        [
            int.from_bytes(hashlib.sha256(f"{seed}|{u}".encode()).digest()[:4], "big")
            % k
            for u in uniq
        ]
    )
    return fold[inverse]


def _temperature(d: Path, groups: str) -> float | None:
    path = d / f"{groups}.temperature.json"
    if not path.exists():
        return None
    return float(json.loads(path.read_text(encoding="utf-8"))["temperature"])


def _cmd_v2_crossfit(a) -> None:
    """Reg M-B's temperature: train the pooled model k times, each without one
    fold of Reg M-B's training sets and to the main model's rounds, predict that
    fold, and fit one temperature on those out-of-fold predictions."""
    from wpa.model import GRID, fit

    if a.format != "pooled":
        raise SystemExit("the correction is for the pooled Reg M-B model")
    d = _paths(a.models, "pooled")
    rounds = int(json.loads((d / f"{a.groups}.json").read_text())["n_iter"])
    train = _v2_tables(a, a.groups, "train")
    val = _v2_tables(a, a.groups, "validation")
    mb = train.X[:, -1] == 1.0
    fold = np.full(len(train.y), -1)
    fold[mb] = unit_folds(train.unit[mb], a.folds)
    oof = np.full(len(train.y), np.nan)
    for f in range(a.folds):
        model, _info = fit(
            subset(train, fold != f), val, GRID[V2_GRID_ENTRY], max_iter=rounds
        )
        assert model is not None
        rows = fold == f
        oof[rows] = model.predict(train.X[rows])
        print(f"fold {f + 1} of {a.folds}: {int(rows.sum())} Reg M-B rows", flush=True)
    p, y = oof[mb], train.y[mb].astype(np.float64)
    temp = fit_temperature(p, y)
    q = apply_temperature(p, temp)
    info = {
        "temperature": temp,
        "folds": a.folds,
        "rounds": rounds,
        "rows": int(mb.sum()),
        "sets": int(len(np.unique(train.unit[mb]))),
        "brier_before": float(np.mean((p - y) ** 2)),
        "brier_after": float(np.mean((q - y) ** 2)),
    }
    (d / f"{a.groups}.temperature.json").write_text(
        json.dumps(info, indent=1), encoding="utf-8"
    )
    print(
        f"Reg M-B temperature {temp:.3f} from {info['sets']} training sets "
        f"(out-of-fold Brier {info['brier_before']:.4f} -> {info['brier_after']:.4f})"
    )


def aligned(a: Table, b: Table) -> tuple[np.ndarray, np.ndarray]:
    """Row indices of `a` and `b` for the same decisions: a row is keyed by its
    game, its side and its place among that side's rows (tables built from
    differently sharded logs list the same decisions in a different order)."""

    def keys(t: Table) -> dict[str, int]:
        seen: dict[tuple[str, str], int] = {}
        out = {}
        for i, (tag, role) in enumerate(zip(t.tag, t.role)):
            n = seen.get((tag, role), 0)
            seen[(tag, role)] = n + 1
            out[f"{tag}|{role}|{n}"] = i
        return out

    ka, kb = keys(a), keys(b)
    common = [k for k in ka if k in kb]
    return np.array([ka[k] for k in common], dtype=int), np.array(
        [kb[k] for k in common], dtype=int
    )


def _cmd_v2_compare(a) -> None:
    """Paired differences on validation: the `--full` model against each model
    in `--others` (`GROUPS` or `GROUPS@FEATURES@MODELS`, e.g. a model trained
    without one group, or the blanked-sheet model), per format."""
    from argparse import Namespace

    out = [f"=== {a.models.name} ({a.full}) against other models: validation ==="]
    for fmt, which in (("regma", "regma"), ("regmb", "pooled")):
        m, raw, x = _v2_predict(a, which, a.full, "validation")
        p = m.predict(x.X)
        temp = _temperature(a.models / which, a.full) if fmt == "regmb" else None
        if temp is not None:
            p = apply_temperature(p, temp)
        for other in a.others:
            groups, _, rest = other.partition("@")
            feats, _, models = rest.partition("@")
            b = Namespace(
                features=Path(feats) if feats else a.features,
                models=Path(models) if models else a.models,
            )
            if not (b.models / which / f"{groups}.pkl").exists():
                continue
            m2, raw2, x2 = _v2_predict(b, which, groups, "validation")
            q = m2.predict(x2.X)
            temp2 = _temperature(b.models / which, groups) if fmt == "regmb" else None
            if temp2 is not None:
                q = apply_temperature(q, temp2)
            ia, ib = aligned(raw, raw2)
            if len(ia) == 0 or not np.array_equal(raw.y[ia], raw2.y[ib]):
                out.append(f"{fmt}: {other}: rows do not line up")
                continue
            d, lo, hi = difference_ci(q[ib], p[ia], raw.y[ia], raw.unit[ia])
            bq = brier_ci(q[ib], raw.y[ia], raw.unit[ia])
            out.append(
                f"{fmt} {other}: Brier {_fmt_ci(bq[0], bq[1:])} on {len(ia)} rows; "
                f"minus {a.full}: {d:+.4f} [{lo:+.4f}, {hi:+.4f}]"
            )
    text = "\n".join(out) + "\n"
    print(text)
    (a.models / "compare.txt").write_text(text, encoding="utf-8")


def _cmd_v2_final(a) -> None:
    from wpa.model import load

    n = record_test_opening(
        a.models.parent / "models" / "test_openings.json",
        {"formats": ["regma", "regmb"], "model": f"{a.models.name} {a.full}"},
    )
    print(f"NOTE: the test split has now been opened {n} times in total")
    for fmt, which in (("regma", "regma"), ("regmb", "pooled")):
        d = a.models / which
        model, raw, x = _v2_predict(a, which, a.full, "test")
        recal = d / f"{a.full}.recal.pkl"
        if recal.exists() and use_recalibration(fmt):
            model = load(recal, list(x.columns))
        p = model.predict(x.X)
        temp = _temperature(d, a.full) if fmt == "regmb" else None
        if temp is not None:
            p = apply_temperature(p, temp)
        r = score(p, raw.y, raw.unit, v0_from_table(raw))
        (d / "test.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(describe(fmt, f"{a.models.name} ({which}) on the TEST split", r))


def main() -> None:
    import argparse
    import sys

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]

    p = argparse.ArgumentParser(description="Train and evaluate the v1 model.")
    p.add_argument(
        "command",
        choices=[
            "train",
            "select",
            "ablation",
            "report",
            "check",
            "final",
            "pooled",
            "v2-train",
            "v2-report",
            "v2-final",
            "v2-crossfit",
            "v2-compare",
        ],
    )
    p.add_argument("--format", default="regma")
    p.add_argument("--formats", nargs="+", default=["regma", "regmb"])
    p.add_argument("--features", type=Path, default=Path("features"))
    p.add_argument("--models", type=Path, default=Path("models"))
    p.add_argument("--grid", default="all", help="grid entry to train, or all")
    p.add_argument("--groups", default="ABCDE")
    p.add_argument("--full", default="ABCDEF", help="v2: the headline feature groups")
    p.add_argument("--folds", type=int, default=5, help="v2-crossfit: folds")
    p.add_argument(
        "--others",
        nargs="+",
        default=[],
        help="v2-compare: GROUPS or GROUPS@FEATURES@MODELS to compare with --full",
    )
    p.add_argument(
        "--base",
        default=None,
        help="v2-report: the model to compare with (default: --full without its "
        "last group)",
    )
    p.add_argument("--steps", nargs="+", default=list(GROUP_STEPS))
    p.add_argument(
        "--sample",
        type=float,
        default=1.0,
        help="fraction of training units to use (1.0 = all)",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=0,
        help="stop after this long and carry on next time (0 = run to the end)",
    )
    p.add_argument(
        "--test", action="store_true", help="pooled: also score the test split"
    )
    a = p.parse_args()
    {
        "train": _cmd_train,
        "select": _cmd_select,
        "ablation": _cmd_ablation,
        "report": _cmd_report,
        "check": _cmd_check,
        "final": _cmd_final,
        "pooled": _cmd_pooled,
        "v2-train": _cmd_v2_train,
        "v2-report": _cmd_v2_report,
        "v2-final": _cmd_v2_final,
        "v2-crossfit": _cmd_v2_crossfit,
        "v2-compare": _cmd_v2_compare,
    }[a.command](a)


if __name__ == "__main__":
    main()
