"""The averaged model (Week 10 Task 5; DEFINITIONS §10.2, revision 9).

The win probability the report shows is the average of 10 models, each trained
with v4's settings on a resample of the training sets: whole sets drawn with
replacement, as many as there are, the draw fixed by the member's number.
Averaging brings the model's own noise down, roughly with the square root of the
number of models (Week 9 measured about 3 points for one model).

- **Reg M-B's correction** (a temperature, as in Week 8) is fitted on
  out-of-bag predictions: each Reg M-B training set is predicted only by the
  members whose resample left it out, so no extra training is needed.
- **The averaged model's own noise is measured directly** (revision 9): the
  average of members 1 to 5 against the average of 6 to 10, on the same
  validation positions, scaled to the average of all 10. It is checked against
  the 3-point threshold, with a blocker, not a quiet change, if it is over.

The commands are in the runbook (Section 19). `train` makes the members still
missing, one at a time; it can be stopped and run again. `finish` writes each
format's `ensemble.json`, the gate on validation and the noise, beside the base
model's score (paired). The test split is never read.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from wpa.features import Table

COUNT = 10  # PO, 7 Nov 2026 (Week 10 brief, decision 7)
SEED = 1000  # member k draws its resample with seed SEED + k (wobble used 0 to 2)
THRESHOLD = 3.0  # points (DEFINITIONS §10.2, revision 9)


# --------------------------------------------------------------------------
# The pieces (tested on their own)
# --------------------------------------------------------------------------


class AveragedModel:
    """The average of the members' win probabilities, then Reg M-B's
    temperature if it has one."""

    def __init__(self, members: Sequence, temperature: float | None = None) -> None:
        self.members = list(members)
        self.temperature = temperature

    def _mean(self, X, members) -> np.ndarray:
        return np.mean(
            [np.asarray(m.predict(X), dtype=np.float64) for m in members], axis=0
        )

    def predict(self, X) -> np.ndarray:
        from wpa.evaluate import apply_temperature

        p = self._mean(X, self.members)
        return apply_temperature(p, self.temperature) if self.temperature else p

    def halves(self, X) -> tuple[np.ndarray, np.ndarray]:
        """The average of the first half of the members and of the second."""
        k = len(self.members) // 2
        return self._mean(X, self.members[:k]), self._mean(X, self.members[k:])


def member_resample(table: Table, k: int) -> tuple[Table, set]:
    """Member `k`'s training table: sets drawn with replacement, as many as
    there are, each bringing all its rows; and the sets it drew (its bag)."""
    rng = np.random.default_rng(SEED + k)
    units, inverse = np.unique(table.unit, return_inverse=True)
    picks = rng.integers(0, len(units), len(units))
    order = np.argsort(inverse, kind="stable")
    starts = np.searchsorted(inverse[order], np.arange(len(units) + 1))
    idx = np.concatenate([order[starts[i] : starts[i + 1]] for i in picks])
    out = Table(
        table.X[idx],
        table.y[idx],
        table.tag[idx],
        table.role[idx],
        table.unit[idx],
        table.turn[idx],
        table.columns,
    )
    return out, {str(u) for u in units[np.unique(picks)]}


def oob_temperature(
    preds: np.ndarray, bags: Sequence[set], units: np.ndarray, y: np.ndarray
) -> tuple[float, int]:
    """The temperature fitted on out-of-bag predictions: each row averaged over
    the members whose bag left its set out; rows no member left out are not
    used. Returns the temperature and the number of rows used."""
    from wpa.evaluate import fit_temperature

    preds = np.asarray(preds, dtype=np.float64)
    units = np.asarray(units).astype(str)
    out = np.array([~np.isin(units, sorted(bag)) for bag in bags])  # member x row
    n = out.sum(axis=0)
    used = n > 0
    avg = (preds * out).sum(axis=0)[used] / n[used]
    return fit_temperature(avg, np.asarray(y)[used]), int(used.sum())


def noise(preds: np.ndarray, table: Table) -> dict:
    """The averaged model's own noise on the positions of `table`, in points.
    `preds`: one row per member. Each figure is the root mean square:
    - single_level, single_swing: one member, from the spread across members;
    - average_level, average_swing: the average of all members, the same spread
      divided by the square root of their number;
    - halves_level, halves_swing: measured directly, the first half's average
      against the second's, scaled to the average of all (half the difference).
    Also the median and 90th percentile of the average's level noise."""
    from wpa.wobble import _swing_pairs

    preds = np.asarray(preds, dtype=np.float64)
    k = len(preds)
    a, b = _swing_pairs(table)
    sw = preds[:, b] - preds[:, a]

    def rms(v) -> float:
        return float(np.sqrt(np.mean(np.square(v)))) * 100

    lvl_sd = preds.std(axis=0, ddof=1)
    sw_sd = sw.std(axis=0, ddof=1)
    h = k // 2
    d_lvl = preds[:h].mean(axis=0) - preds[h:].mean(axis=0)
    d_sw = sw[:h].mean(axis=0) - sw[h:].mean(axis=0)
    per = lvl_sd / np.sqrt(k) * 100
    return {
        "members": k,
        "positions": int(preds.shape[1]),
        "single_level": rms(lvl_sd),
        "single_swing": rms(sw_sd),
        "average_level": rms(lvl_sd) / np.sqrt(k),
        "average_swing": rms(sw_sd) / np.sqrt(k),
        "halves_level": rms(d_lvl) / 2,
        "halves_swing": rms(d_sw) / 2,
        "average_level_median": float(np.median(per)),
        "average_level_p90": float(np.percentile(per, 90)),
    }


# --------------------------------------------------------------------------
# Training and finishing (on the PO's computer)
# --------------------------------------------------------------------------


def _paths(models: Path, fmt: str, groups: str, k: int) -> tuple[Path, Path, Path]:
    d = Path(models) / fmt
    stem = f"{groups}.r{k:02d}"
    return d / f"{stem}.pkl", d / f"{stem}.json", d / f"{stem}.ckpt"


def train(a) -> None:  # pragma: no cover - hours on the full table
    from wpa.evaluate import V2_GRID_ENTRY, _train_until, _v2_tables
    from wpa.model import GRID, save

    args = argparse.Namespace(features=a.features, format=a.format, sample=1.0)
    for k in range(1, COUNT + 1):
        pkl, info_path, ckpt = _paths(a.models, a.format, a.groups, k)
        if pkl.exists():
            continue
        t0 = time.time()
        full = _v2_tables(args, a.groups, "train")
        train_t, bag = member_resample(full, k)
        del full  # one table in memory, not two
        val = _v2_tables(args, a.groups, "validation")
        pkl.parent.mkdir(parents=True, exist_ok=True)
        model, info = _train_until(train_t, val, GRID[V2_GRID_ENTRY], ckpt, 0.0)
        assert model is not None
        save(model, pkl)
        regmb = sorted(u for u in bag if "regmb" in u) if a.format == "pooled" else []
        info.update(
            {
                "member": k,
                "seed": SEED + k,
                "groups": a.groups,
                "train_rows": int(len(train_t.y)),
                "sets_in_bag": len(bag),
                "regmb_bag": regmb,
                "seconds": round(time.time() - t0),
            }
        )
        info_path.write_text(json.dumps(info, indent=1), encoding="utf-8")
        ckpt.unlink(missing_ok=True)
        print(
            f"{a.format} member {k} of {COUNT}: validation Brier "
            f"{info['best_validation_brier']:.4f} after {info['n_iter']} rounds, "
            f"{info['seconds'] / 3600:.1f} hours",
            flush=True,
        )


def load_members(models: Path, fmt: str, groups: str, columns) -> list:
    from wpa.model import load

    out = []
    for k in range(1, COUNT + 1):
        pkl, _info, _ckpt = _paths(models, fmt, groups, k)
        if pkl.exists():
            out.append(load(pkl, list(columns)))
    return out


def load_averaged(
    models: Path, which: str, groups: str, columns
) -> AveragedModel | None:
    """The averaged model in `models/which`, if `finish` has made one."""
    path = Path(models) / which / f"{groups}.ensemble.json"
    if not path.exists():
        return None
    info = json.loads(path.read_text(encoding="utf-8"))
    members = load_members(models, which, groups, columns)
    if len(members) != info["members"]:
        raise ValueError(
            f"{path}: {info['members']} members expected, {len(members)} found"
        )
    return AveragedModel(members, info.get("temperature"))


def finish(a) -> None:  # pragma: no cover - on the full table
    from wpa.evaluate import (
        _v2_predict,
        _v2_tables,
        describe,
        difference_ci,
        gate_failures,
        load_table,
        score,
        select,
        v0_from_table,
        with_format_flag,
    )

    lines = ["The averaged model (Week 10 Task 5; DEFINITIONS §10.2, revision 9)", ""]
    results = {}
    for fmt, which in (("regma", "regma"), ("regmb", "pooled")):
        raw = load_table(a.features, fmt, "validation")
        x = select(raw, a.groups)
        if which == "pooled":
            x = with_format_flag(x, 1.0)
        members = load_members(a.models, which, a.groups, x.columns)
        if len(members) < COUNT:
            lines.append(
                f"{fmt}: {len(members)} of {COUNT} members; train the rest first"
            )
            continue
        preds = np.array([m.predict(x.X) for m in members])
        temp = None
        if which == "pooled":
            args = argparse.Namespace(features=a.features, format="pooled", sample=1.0)
            tr = _v2_tables(args, a.groups, "train")
            mb = np.array(["regmb" in str(u) for u in tr.unit])
            bags = []
            for k in range(1, COUNT + 1):
                _p, info_path, _c = _paths(a.models, which, a.groups, k)
                bags.append(
                    set(json.loads(info_path.read_text(encoding="utf-8"))["regmb_bag"])
                )
            tr_preds = np.array([m.predict(tr.X[mb]) for m in members])
            temp, used = oob_temperature(tr_preds, bags, tr.unit[mb], tr.y[mb])
            lines.append(
                f"Reg M-B temperature {temp:.3f}, fitted on out-of-bag predictions "
                f"of {used} Reg M-B training rows"
            )
        model = AveragedModel(members, temp)
        p = model.predict(x.X)
        r = score(p, raw.y, raw.unit, v0_from_table(raw))
        results[fmt] = r
        lines.append(describe(fmt, f"{a.models.name} (average of {COUNT})", r))
        if a.base:
            base_args = argparse.Namespace(features=a.features, models=a.base)
            try:
                base, _raw, bx = _v2_predict(base_args, which, a.groups, "validation")
                q = base.predict(bx.X)
                from wpa.evaluate import _temperature, apply_temperature

                t_base = (
                    _temperature(Path(a.base) / which, a.groups)
                    if fmt == "regmb"
                    else None
                )
                if t_base is not None:
                    q = apply_temperature(q, t_base)
                d, lo, hi = difference_ci(p, q, raw.y, raw.unit)
                lines.append(
                    f"  against {Path(a.base).name}: {d:+.4f} "
                    f"({lo:+.4f} to {hi:+.4f}), negative is better"
                )
            except Exception as e:
                lines.append(f"  against {Path(a.base).name}: not compared ({e})")
        nz = noise(preds, raw)
        verdict = (
            "under"
            if nz["halves_level"] < THRESHOLD and nz["halves_swing"] < THRESHOLD
            else "OVER"
        )
        lines += [
            f"  noise of the average of {COUNT}, measured from its two halves: "
            f"level {nz['halves_level']:.2f} points, swing {nz['halves_swing']:.2f} "
            f"({verdict} the {THRESHOLD:g}-point threshold)",
            f"  from the spread across members: one model {nz['single_level']:.2f} "
            f"(swing {nz['single_swing']:.2f}); the average {nz['average_level']:.2f} "
            f"(swing {nz['average_swing']:.2f}); per position median "
            f"{nz['average_level_median']:.2f}, "
            f"90th percentile {nz['average_level_p90']:.2f}",
            "",
        ]
        if verdict == "OVER":
            lines.append(
                f"  BLOCKER: {fmt}'s averaged model is noisier than the threshold"
            )
        d = Path(a.models) / which
        (d / f"{a.groups}.ensemble.json").write_text(
            json.dumps({"members": COUNT, "temperature": temp, "noise": nz}, indent=1),
            encoding="utf-8",
        )
    fails = gate_failures(results)
    lines.append("Gate: " + ("passed" if not fails else "FAILED: " + "; ".join(fails)))
    text = "\n".join(lines)
    print(text)
    (Path(a.models) / "report.txt").write_text(text + "\n", encoding="utf-8")


def main() -> None:  # pragma: no cover
    p = argparse.ArgumentParser(description="The averaged model (DEFINITIONS §10.2)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("train", "finish"):
        s = sub.add_parser(name)
        s.add_argument("--features", type=Path, required=True)
        s.add_argument("--models", type=Path, required=True)
        s.add_argument("--groups", default="ABCDEFGHIJ")
        if name == "train":
            s.add_argument("--format", choices=["regma", "pooled"], required=True)
        else:
            s.add_argument(
                "--base", type=Path, default=None, help="the model to compare with"
            )
    a = p.parse_args()
    train(a) if a.cmd == "train" else finish(a)


if __name__ == "__main__":
    main()
