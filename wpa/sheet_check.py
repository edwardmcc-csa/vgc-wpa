"""Week 12 Task 5's check: the analysis with the opponent's sheet hidden
(`attribution --hidden-sets`) against the one with both sheets whole, on the
same games, whose sheets we know.

Each player's turn is paired with itself. A turn followed by a forced switch is
left out: with the sheet hidden each player's turn ends at their own next
decision point, so the two runs can end it at different points. For each part
of the split (DEFINITIONS §3), and for WP at the turn's start and the turn's
swing: the averages with whole sheets and hidden, how far the part moves (the
average and median in points, and the share of turns it moves 3 points or
more, the reporting threshold), and, of the turns where it is 3 points or more
with whole sheets, the share where it keeps its direction. And how often the
board that happened is among the resolver's, each way.

    python -m wpa.sheet_check

reads `reports/attribution_week12.jsonl` (whole) and
`reports/attribution_hidden.jsonl` (hidden), prints the table and saves it as
`reports/sheet_check.txt`."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

PARTS = (
    ("before", "WP at the turn's start"),
    ("choice", "your choice"),
    ("position", "the position"),
    ("theirs", "their decision"),
    ("dice", "the dice"),
    ("swing", "the turn's swing"),
)
NAMES = {"regma": "Reg M-A", "regmb": "Reg M-B"}
THRESHOLD = 3.0  # points: the reporting threshold


def _value(r: Mapping, part: str) -> float:
    if part == "swing":
        return float(r["after"]) - float(r["before"])
    return float(r[part])


def _turns(records: Sequence[Mapping]) -> dict[tuple, Mapping]:
    return {
        (r["tag"], r["turn"], r["role"]): r
        for r in records
        if r.get("kind", "turn") == "turn"
        and "skipped" not in r
        and r.get("choice") is not None
    }


def compare(whole: Sequence[Mapping], hidden: Sequence[Mapping]) -> dict[str, dict]:
    """Per format: the turns paired, and each part's averages and moves."""
    w, h = _turns(whole), _turns(hidden)
    forced = {
        (r["tag"], r["turn"]) for r in whole if r.get("kind") == "replacement"
    } | {(r["tag"], r["turn"]) for r in hidden if r.get("kind") == "replacement"}
    out: dict[str, dict] = {}
    for key in sorted(set(w) & set(h), key=str):
        fmt = w[key]["format"]
        d = out.setdefault(
            fmt, {"pairs": [], "games": set(), "after_a_forced_switch": 0}
        )
        if key[:2] in forced:
            d["after_a_forced_switch"] += 1
            continue
        d["pairs"].append((w[key], h[key]))
        d["games"].add(key[0])
    for d in out.values():
        pairs = d.pop("pairs")
        d["turns"], d["games"] = len(pairs), len(d["games"])
        d["parts"] = {}
        for part, _name in PARTS:
            a = np.array([100 * _value(x, part) for x, _ in pairs], dtype=float)
            b = np.array([100 * _value(y, part) for _, y in pairs], dtype=float)
            moved = np.abs(b - a)
            big = np.abs(a) >= THRESHOLD - 1e-9
            d["parts"][part] = {
                "whole_mean": float(a.mean()) if len(a) else float("nan"),
                "hidden_mean": float(b.mean()) if len(b) else float("nan"),
                "moved_mean": float(moved.mean()) if len(a) else float("nan"),
                "moved_median": float(np.median(moved)) if len(a) else float("nan"),
                "moved_3": float(np.mean(moved >= THRESHOLD - 1e-9))
                if len(a)
                else float("nan"),
                "same_way": float(np.mean(np.sign(a[big]) == np.sign(b[big])))
                if big.any()
                else float("nan"),
            }
        d["found_whole"] = (
            float(np.mean([bool(x.get("found")) for x, _ in pairs]))
            if pairs
            else float("nan")
        )
        d["found_hidden"] = (
            float(np.mean([bool(y.get("found")) for _, y in pairs]))
            if pairs
            else float("nan")
        )
    return out


def _read(path: Path) -> list[dict]:
    return [
        json.loads(x)
        for x in Path(path).read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def report(whole_path: Path, hidden_path: Path) -> str:
    got = compare(_read(whole_path), _read(hidden_path))
    lines = [
        "The opponent's sheet hidden against both sheets whole (Week 12 Task 5)",
        "  the same turns, each player's own, in points",
        f"  moved by: mean | median | share of turns moved {THRESHOLD:g}+ points",
        f"  same way: of the turns where the part is {THRESHOLD:g}+ points with whole",
        "    sheets, the share where it keeps its direction with the sheet hidden",
        "",
    ]
    for fmt in sorted(got):
        d = got[fmt]
        n, g = d["turns"], d["games"]
        lines.append(
            f"{NAMES.get(fmt, fmt)}: {n} turn{'s' if n != 1 else ''} (each "
            f"player's) in {g} game{'s' if g != 1 else ''}; "
            f"{d['after_a_forced_switch']} left out (a forced switch after it)"
        )
        lines.append(
            f"  {'':24} {'whole':>8} {'hidden':>8}   {'moved by':<22} same way"
        )
        for part, name in PARTS:
            x = d["parts"][part]
            moved = (
                f"{x['moved_mean']:.1f} | {x['moved_median']:.1f} | "
                f"{100 * x['moved_3']:.0f}%"
            )
            same = "-"
            if part != "before" and x["same_way"] == x["same_way"]:  # not NaN
                same = f"{100 * x['same_way']:.0f}%"
            if part == "before":  # a chance, in points
                a, b = f"{x['whole_mean']:.1f}", f"{x['hidden_mean']:.1f}"
            else:
                a, b = f"{x['whole_mean']:+.1f}", f"{x['hidden_mean']:+.1f}"
            lines.append(f"  {name:<24} {a:>8} {b:>8}   {moved:<22} {same}")
        lines.append(
            f"  {'the board found':<24} {100 * d['found_whole']:>7.0f}% "
            f"{100 * d['found_hidden']:>7.0f}%"
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument(
        "--whole", type=Path, default=Path("reports/attribution_week12.jsonl")
    )
    p.add_argument(
        "--hidden", type=Path, default=Path("reports/attribution_hidden.jsonl")
    )
    p.add_argument("--out", type=Path, default=Path("reports/sheet_check.txt"))
    a = p.parse_args(argv)
    text = report(a.whole, a.hidden)
    print(text)
    a.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
