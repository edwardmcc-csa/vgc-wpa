"""Expert-claim positions, scored by v0 and v1 (Week 5 Task 8). REPORT ONLY.

`docs/EXPERT-CLAIMS.md` turns things strong players know into labelled
positions. This module finds real decision points that look like each claim's
starting position, builds the follow-up positions the claim compares by editing
the feature row, and reports how often each model prefers the follow-up the
claim says is better. Nothing here gates.

The follow-ups are approximations built from features, not simulated games:
a replacement Pokemon comes in at full hit points, a turn passing takes one turn
off every timer, and the team-sheet features (groups D and E) are left as they
were because which Pokemon comes in is not known. Neither model has any feature
for speed, so a claim that turns on who is faster cannot be represented; that is
the finding the brief asks for.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

_TIMER_PREFIXES = ("c_field_", "c_our_", "c_their_")
_NOT_TIMERS = ("_n", "_end_next")


def _idx(cols: Sequence[str]) -> dict[str, int]:
    return {c: i for i, c in enumerate(cols)}


def pass_turn(x: np.ndarray, cols: Sequence[str]) -> np.ndarray:
    """One turn later: every turns-left timer one lower, the turn number up."""
    y = x.copy()
    for i, c in enumerate(cols):
        if c.startswith(_TIMER_PREFIXES) and not c.endswith(_NOT_TIMERS):
            y[i] = max(0.0, y[i] - 1.0)
    IX = _idx(cols)
    if "a_turn" in IX:
        y[IX["a_turn"]] += 1
    return y


def knock_out(
    x: np.ndarray, cols: Sequence[str], side: str, n: int, hp_lost: float | None = None
) -> np.ndarray:
    """`n` of `side`'s active Pokemon faint; unseen ones replace them at full hit
    points (as many as there are). `hp_lost`: the hit points the fainted ones
    had (default: all of the active hit points)."""
    y = x.copy()
    IX = _idx(cols)
    a = lambda k: IX[f"a_{side}_{k}"]  # noqa: E731
    lost = y[a("hp_active")] if hp_lost is None else hp_lost
    y[a("fainted")] += n
    y[a("remaining")] = max(0.0, y[a("remaining")] - n)
    y[a("seen_alive")] = max(0.0, y[a("seen_alive")] - n)
    y[a("hp_active")] = max(0.0, y[a("hp_active")] - lost)
    y[a("hp_seen")] = max(0.0, y[a("hp_seen")] - lost)
    y[a("active")] = max(0.0, y[a("active")] - n)
    incoming = min(float(n), float(y[a("unseen")]))
    y[a("unseen")] -= incoming
    y[a("seen_alive")] += incoming
    y[a("active")] += incoming
    y[a("hp_active")] += incoming
    y[a("hp_seen")] += incoming
    return y


def ec001_candidates(
    X: np.ndarray, cols: Sequence[str], limit: int = 500
) -> np.ndarray:
    """Turn-start decisions where the opponent has Tailwind with 1-2 turns left,
    two weakened Pokemon active (at most 60% hit points between them), nobody
    fainted and nobody seen in the back (so two unseen are to come), and we have
    three or more left."""
    IX = _idx(cols)
    m = (
        (X[:, IX["c_moment_turn_start"]] == 1)
        & np.isin(X[:, IX["c_their_tailwind"]], (1.0, 2.0))
        & (X[:, IX["c_our_tailwind"]] == 0)
        & (X[:, IX["a_their_active"]] == 2)
        & (X[:, IX["a_their_seen_alive"]] == 2)  # nobody seen on their bench
        & (X[:, IX["a_their_hp_active"]] <= 0.6)
        & (X[:, IX["a_their_unseen"]] >= 2)
        & (X[:, IX["a_their_fainted"]] == 0)
        & (X[:, IX["a_our_remaining"]] >= 3)
    )
    return np.flatnonzero(m)[:limit]


def ec001_follow_ups(x: np.ndarray, cols: Sequence[str]) -> dict[str, np.ndarray]:
    """After this turn: knock out both, knock out one, or stall (no knock-out)."""
    IX = _idx(cols)
    hp = float(x[IX["a_their_hp_active"]])
    return {
        "double_ko": pass_turn(knock_out(x, cols, "their", 2), cols),
        "single_ko": pass_turn(knock_out(x, cols, "their", 1, hp_lost=hp / 2), cols),
        "stall": pass_turn(x, cols),
    }


def ec002_candidates(
    X: np.ndarray, cols: Sequence[str], limit: int = 500
) -> np.ndarray:
    """Turn-start decisions where we have two active Pokemon, one of them nearly
    spent: our active hit points total 1.0-1.3 (a healthy one and one at 30% or
    less, roughly), and we still have someone in the back."""
    IX = _idx(cols)
    m = (
        (X[:, IX["c_moment_turn_start"]] == 1)
        & (X[:, IX["a_our_active"]] == 2)
        & (X[:, IX["a_our_seen_alive"]] == 2)
        & (X[:, IX["a_our_hp_active"]] >= 1.0)
        & (X[:, IX["a_our_hp_active"]] <= 1.3)
        & (X[:, IX["a_our_remaining"]] >= 3)
    )
    return np.flatnonzero(m)[:limit]


def ec002_follow_ups(
    x: np.ndarray,
    cols: Sequence[str],
    spent_hp: float = 0.2,
    strong_hp: float = 1.0,
    damage: float = 0.5,
) -> dict[str, np.ndarray]:
    """Sacrifice the spent Pokemon (it faints, the strong one is untouched), or
    keep it alive while the strong one takes `damage`."""
    IX = _idx(cols)
    sacrifice = knock_out(x, cols, "our", 1, hp_lost=spent_hp)
    keep = x.copy()
    keep[IX["a_our_hp_active"]] = max(0.0, keep[IX["a_our_hp_active"]] - damage)
    keep[IX["a_our_hp_seen"]] = max(0.0, keep[IX["a_our_hp_seen"]] - damage)
    return {"sacrifice": pass_turn(sacrifice, cols), "keep": pass_turn(keep, cols)}


def preference(
    predict,
    X: np.ndarray,
    cols: Sequence[str],
    build,
    better: tuple[str, ...],
    worse: str,
) -> dict:
    """How often `predict` scores any of `better` above `worse` (claim agrees)."""
    agree = 0
    means: dict[str, list[float]] = {}
    for x in X:
        rows = build(x, cols)
        p = {k: float(predict(v[None, :])[0]) for k, v in rows.items()}
        for k, v in p.items():
            means.setdefault(k, []).append(v)
        agree += max(p[b] for b in better) > p[worse]
    n = len(X)
    return {
        "positions": n,
        "agrees": agree / n if n else float("nan"),
        "mean": {k: float(np.mean(v)) for k, v in means.items()},
    }


def main() -> None:
    """Score EC-001 and EC-002 on validation decision points, v0 and v1."""
    import argparse
    from pathlib import Path

    from wpa.evaluate import load_table, select, v0_from_table
    from wpa.features import Table, columns
    from wpa.model import load

    p = argparse.ArgumentParser(description="Expert-claim positions (report only).")
    p.add_argument("--features", type=Path, default=Path("features"))
    p.add_argument("--models", type=Path, default=Path("models"))
    p.add_argument("--formats", nargs="+", default=["regma", "regmb"])
    a = p.parse_args()
    cols = columns("ABCDE")
    for fmt in a.formats:
        val = select(load_table(a.features, fmt, "validation"), "ABCDE")
        model = load(a.models / fmt / "v1.pkl", cols)

        def v0(X: np.ndarray) -> np.ndarray:
            n = len(X)
            t = Table(
                X,
                np.zeros(n, np.int8),
                np.array([""] * n),
                np.array([""] * n),
                np.array([""] * n),
                np.zeros(n, np.int16),
                cols,
            )
            return v0_from_table(t)

        for claim, cands, build, better, worse in (
            (
                "EC-001",
                ec001_candidates,
                ec001_follow_ups,
                ("single_ko", "stall"),
                "double_ko",
            ),
            ("EC-002", ec002_candidates, ec002_follow_ups, ("sacrifice",), "keep"),
        ):
            X = val.X[cands(val.X, cols)]
            for name, predict in (("v0", v0), ("v1", model.predict)):
                r = preference(predict, X, cols, build, better, worse)
                means = ", ".join(f"{k} {v:.3f}" for k, v in sorted(r["mean"].items()))
                print(
                    f"{fmt} {claim} {name}: {r['positions']} positions; prefers the "
                    f"claim's choice in {r['agrees']:.0%}; mean win probability {means}"
                )


if __name__ == "__main__":
    main()
