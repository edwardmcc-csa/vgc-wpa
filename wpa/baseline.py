"""v0 heuristic baseline (Week 4 Task 5): hand-written, no machine learning.

WP_public from the fields a BattleState already carries, following
docs/DEFINITIONS.md sections 1 and 5. It is the bar a learned model must
clear, nothing more.

The rule
--------
Each side has a strength: the hit points of its Pokemon that have appeared
and are still alive, plus 1.0 for every brought Pokemon that has not appeared
yet (assumed at full health). Brought means BRING_SIZE (4) minus the fainted
count; see wpa/metrics.py for why it is not six minus fainted.

    WP = 1 / (1 + exp(-k * (our strength - their strength)))

and exactly 1.0 / 0.0 once the game is decided. k = BASELINE_K was set by
hand BEFORE any result was seen: one full Pokemon of lead is about 73%.

The information set (section 5)
-------------------------------
The prediction reads ONLY hp_fraction, fainted and active of each Pokemon,
and the state's outcome. tests/test_baseline.py enforces this with a guard
that raises on any other field. In particular:

* opp_pokemon lists all six opposing species from the open team sheet, in
  sheet order, from the first state. That is public. Until a Pokemon appears
  its hp_fraction is 0.0, fainted False, active False, whether or not it was
  brought, so nothing in those fields says which four were brought. The
  species, the order and the gimmick flag are NOT read (docs/OPP-POKEMON.md).
* hp_fraction 0.0 therefore means 'not on the field yet', not 'nearly
  fainted', and is never read as damage.
* The same rule is applied to our own side. The player knows their own
  bench hit points, but the record shows 0.0 for them too, so this is a loss
  of information, never a leak.

What it cannot do
-----------------
See LIMITATIONS. It is expected to get the docs/EXPERT-CLAIMS.md cases wrong,
and that is the point: those failures are the evidence for which state
features the learned model needs.

Run `python -m wpa.baseline --splits splits.json` for the per-format report
on the validation split.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from wpa.formats import FORMAT_MA, FORMAT_MB
from wpa.metrics import (
    LoadStats,
    MetricReport,
    evaluate,
    load_split,
    pokemon_remaining,
    score_states,
)

BASELINE_K = 1.0

LIMITATIONS = (
    "It cannot represent timers: Tailwind, Trick Room, screens, weather or terrain "
    "turns left, Encore, Disable, sleep or freeze counters.",
    "It cannot represent speed relationships, so it cannot tell a faster pair from a "
    "slower one.",
    "It knows nothing about the open team sheet: species, moves, items and abilities "
    "are not read, so team preview is always 50%.",
    "Hit-point percentages of different Pokemon are treated as equal; a bulky and a "
    "frail Pokemon at 50% count the same.",
    "It is therefore expected to get the docs/EXPERT-CLAIMS.md cases (EC-001, EC-002) "
    "wrong. That is the evidence for which features the learned model needs.",
)


def strength(side) -> float:
    """Revealed living Pokemon's hit points, plus 1.0 per unseen brought Pokemon."""
    seen_alive = [p for p in side if not p.fainted and (p.active or p.hp_fraction > 0)]
    unseen_alive = max(0, pokemon_remaining(side) - len(seen_alive))
    return sum(p.hp_fraction for p in seen_alive) + float(unseen_alive)


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def make_predictor(k: float):
    """The baseline with scale k (win-probability steepness per Pokemon of lead)."""
    if (
        isinstance(k, bool)
        or not isinstance(k, (int, float))
        or not math.isfinite(k)
        or k <= 0
    ):
        raise ValueError(f"the scale must be a positive number, got {k!r}")

    def predict(state) -> float:
        if state.outcome is True:
            return 1.0
        if state.outcome is False:
            return 0.0
        return _sigmoid(k * (strength(state.our_pokemon) - strength(state.opp_pokemon)))

    return predict


predict = make_predictor(BASELINE_K)


def report_split(
    directory,
    games,
    split: str = "validation",
    predictor=predict,
    formats=(FORMAT_MA, FORMAT_MB),
    **evaluate_kwargs,
) -> tuple[MetricReport, dict[str, LoadStats]]:
    """Score one split, per format. Formats with no games in the split are skipped."""
    loads: dict[str, LoadStats] = {}

    def rows():
        for fmt in formats:
            stats = loads[fmt] = LoadStats()
            yield from score_states(
                predictor, load_split(directory, games, split, fmt, stats)
            )

    report = evaluate(
        rows(), claims=evaluate_kwargs.pop("claims", []), **evaluate_kwargs
    )
    return report, {f: s for f, s in loads.items() if s.files or s.incomplete_files}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the v0 baseline on a split.")
    parser.add_argument("--dir", type=Path, default=Path("wpa_states"))
    parser.add_argument(
        "--splits",
        type=Path,
        help="manifest written by `python -m wpa.splits --out FILE` "
        "(computed if omitted)",
    )
    parser.add_argument("--split", default="validation")
    parser.add_argument("--k", type=float, default=BASELINE_K)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--min_count", type=int, default=100)
    parser.add_argument("--num_workers", type=int, default=4)
    args = parser.parse_args()

    if args.splits:
        games = json.loads(args.splits.read_text(encoding="utf-8"))["games"]
    else:
        from wpa.splits import split_directory

        games = split_directory(args.dir, num_workers=args.num_workers).to_dict()[
            "games"
        ]

    print("=== wpa v0 baseline ===")
    print(
        f"hand-written, no machine learning; scale k={args.k} per Pokemon of lead; "
        f"scored on the {args.split} split of {args.dir}"
    )
    print("what it cannot do:")
    for line in LIMITATIONS:
        print(f"  - {line}")
    report, loads = report_split(
        args.dir,
        games,
        args.split,
        make_predictor(args.k),
        tolerance=args.tolerance,
        min_count=args.min_count,
    )
    for fmt, s in sorted(loads.items()):
        print(
            f"{fmt}: read {s.games} games, {s.files} files, {s.states} states; "
            f"incomplete games dropped: {s.incomplete_files} files, "
            f"{s.incomplete_states} states"
        )
    print()
    print(report.describe())


if __name__ == "__main__":
    main()
