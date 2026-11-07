"""How much win probability wobbles (Week 9 Task 6, DEFINITIONS §10.2).

Before M7 ships, §10.2 asks how far `WP` moves on identical positions from run to
run. If that is more than the reporting threshold (3 points since revision 9; it
was 0.5 when this was first measured), the report would show noise as insight.
Training here is deterministic, so a rerun gives the same model.
The honest measure of the model's own noise is to retrain it on resamples of the
training sets: draw whole sets with replacement, as many as there are, and train
with the same settings and the same number of rounds as the real model. Then see
how far its win probability moves on the same validation positions.

Two numbers per format, both in percentage points:
- **level:** how far `WP` at a position moves between retrained models;
- **swing:** how far the change between one decision point and the next (the
  WPA the report would show) moves.
"""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

import numpy as np

from wpa.features import Table

THRESHOLD = 3.0  # percentage points (DEFINITIONS §10.2, revision 9)


def resample_units(table: Table, seed: int) -> Table:
    """A bootstrap resample of `table` by unit (set): units drawn with
    replacement, each drawn unit bringing all of its rows."""
    rng = np.random.default_rng(seed)
    units, inverse = np.unique(table.unit, return_inverse=True)
    rows_of = [np.flatnonzero(inverse == i) for i in range(len(units))]
    picks = rng.integers(0, len(units), len(units))
    idx = np.concatenate([rows_of[i] for i in picks])
    return Table(
        table.X[idx],
        table.y[idx],
        table.tag[idx],
        table.role[idx],
        table.unit[idx],
        table.turn[idx],
        table.columns,
    )


def _swing_pairs(table: Table) -> tuple[np.ndarray, np.ndarray]:
    """Index pairs (earlier, later) of consecutive decision points of the same
    side of the same game, in turn order."""
    order = np.lexsort((np.arange(len(table.turn)), table.turn, table.role, table.tag))
    tag, role = table.tag[order], table.role[order]
    same = (tag[1:] == tag[:-1]) & (role[1:] == role[:-1])
    return order[:-1][same], order[1:][same]


def wobble(preds: np.ndarray, table: Table) -> dict:
    """`preds`: one row of win probabilities per retrained model, one column per
    position of `table`. The spread across models (standard deviation), per
    position and per swing, in percentage points (the sample standard deviation,
    since the models are a sample of the ones the data could have given)."""
    preds = np.asarray(preds, dtype=np.float64)
    ddof = 1 if len(preds) > 1 else 0
    levels = preds.std(axis=0, ddof=ddof) * 100
    a, b = _swing_pairs(table)
    swings = (preds[:, b] - preds[:, a]).std(axis=0, ddof=ddof) * 100
    out = {"levels": levels, "swings": swings}
    for name, v in (("level", levels), ("swing", swings)):
        out[f"{name}_median"] = float(np.median(v)) if len(v) else 0.0
        out[f"{name}_p90"] = float(np.percentile(v, 90)) if len(v) else 0.0
        out[f"{name}_share_over_threshold"] = (
            float((v > THRESHOLD).mean()) if len(v) else 0.0
        )
    return out


def describe(fmt: str, w: dict, k: int) -> str:
    return "\n".join(
        [
            f"{fmt}: {len(w['levels'])} positions, {len(w['swings'])} swings, "
            f"{k} retrained models",
            f"  level: median {w['level_median']:.2f} points, 90th percentile "
            f"{w['level_p90']:.2f}, over {THRESHOLD} points "
            f"{100 * w['level_share_over_threshold']:.1f}%",
            f"  swing: median {w['swing_median']:.2f} points, 90th percentile "
            f"{w['swing_p90']:.2f}, over {THRESHOLD} points "
            f"{100 * w['swing_share_over_threshold']:.1f}%",
        ]
    )


def main() -> None:  # pragma: no cover - runs for hours on real data
    from wpa.evaluate import V2_GRID_ENTRY, _temperature, _v2_tables, apply_temperature
    from wpa.model import GRID, fit

    p = argparse.ArgumentParser(description="How much win probability wobbles (§10.2)")
    p.add_argument("--features", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True, help="the real models")
    p.add_argument("--groups", required=True)
    p.add_argument("--format", choices=["regma", "pooled"], required=True)
    p.add_argument("--resamples", type=int, default=3)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    args = Namespace(features=a.features, format=a.format, sample=1.0)
    rounds = json.loads(
        (a.models / a.format / f"{a.groups}.json").read_text(encoding="utf-8")
    )["n_iter"]
    train = _v2_tables(args, a.groups, "train")
    val = _v2_tables(args, a.groups, "validation")
    temp = _temperature(a.models / a.format, a.groups) if a.format == "pooled" else None
    a.out.mkdir(parents=True, exist_ok=True)
    preds = []
    for k in range(a.resamples):
        path = a.out / f"{a.format}-{a.groups}-{k}.npy"
        if not path.exists():
            model, _ = fit(
                resample_units(train, seed=k), val, GRID[V2_GRID_ENTRY], max_iter=rounds
            )
            assert model is not None
            p_k = model.predict(val.X)
            if temp is not None:
                p_k = apply_temperature(p_k, temp)
            np.save(path, p_k)
            print(f"resample {k + 1} of {a.resamples} done", flush=True)
        preds.append(np.load(path))
    fmt = "regmb" if a.format == "pooled" else "regma"
    text = describe(fmt, wobble(np.array(preds), val), a.resamples)
    print(text)
    (a.out / f"{a.format}-{a.groups}.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
