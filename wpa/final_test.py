"""A format's test split, opened once with the PO's approval, for a phase's final
numbers (Week 15: Reg M-C, PO 16 Nov 2026).

Every model in use for the format is scored on the test split with the checks
its gate uses on validation:
- the averaged win model: calibration and Brier against v0 (DEFINITIONS §10.2);
- the win model with the opponent's sheet hidden, the same way;
- the bring, lead, choice and forced-switch models against a uniform guess.
Nothing is fitted, tuned or chosen on the test split. Each opening is logged in
`models/test_openings.json` with what was scored and the approval, and the
command refuses to run without `--po-approved`.

Run (Runbook Section 28):
    python -m wpa.final_test --format regmc --po-approved "16 Nov 2026"
        --features features_v4b_mc --preview-features features_v4_preview_mc
        --logs logs_mc --policy models_v4\\regmc\\policy.json
        --leads models_v4\\regmc\\leads.json --replace models_v4\\regmc\\replace.json
        --bring models_v4\\regmc\\bring.json --out reports\\test_regmc.txt
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

OPENINGS = Path("models") / "test_openings.json"


def log_opening(
    path: Path | str, fmt: str, approved: str, models: Sequence[str]
) -> int:
    """Record an opening of `fmt`'s test split; return how many there have been."""
    from wpa.evaluate import record_test_opening

    return record_test_opening(
        path,
        {"formats": [fmt], "model": "; ".join(models), "approved": f"PO, {approved}"},
    )


def choice_scores(
    chances: Callable[[np.ndarray], np.ndarray],
    groups: Sequence[tuple[np.ndarray, int]],
    skip_single: bool = True,
) -> dict:
    """Mean log chance of the option chosen, against a uniform guess, and how
    often the likeliest option was the one chosen. A choice with one option
    is left out unless `skip_single` is False (the choice model's own report
    keeps them)."""
    gs = [(X, c) for X, c in groups if len(X) > 1 or not skip_single]
    if not gs:
        return {"choices": 0, "model": 0.0, "uniform": 0.0, "top": 0.0, "beats": False}
    ll, un, top = [], [], []
    for X, c in gs:
        p = np.asarray(chances(X), dtype=float)
        ll.append(math.log(max(float(p[c]), 1e-300)))
        un.append(math.log(1 / len(X)))
        top.append(int(np.argmax(p) == c))
    out = {
        "choices": len(gs),
        "model": float(np.mean(ll)),
        "uniform": float(np.mean(un)),
        "top": float(np.mean(top)),
    }
    out["beats"] = out["model"] > out["uniform"]
    return out


def _choice_line(name: str, s: dict) -> str:
    return (
        f"  {name}: {s['choices']} choices; model {s['model']:.3f}, uniform "
        f"{s['uniform']:.3f} ({'beats' if s['beats'] else 'DOES NOT BEAT'} it); "
        f"likeliest right {100 * s['top']:.1f}%"
    )


def run(a) -> str:  # pragma: no cover - opens the test split
    from wpa import corpus_checks as K
    from wpa.bring import BringModel
    from wpa.bring import evaluate as bring_evaluate
    from wpa.bring import examples_from_logs as bring_examples
    from wpa.damage import Calc
    from wpa.ensemble import load_averaged
    from wpa.evaluate import (
        describe,
        gate_failures,
        load_table,
        score,
        select,
        v0_from_table,
    )
    from wpa.formats import format_of, model_for
    from wpa.lead_model import LeadModel, groups_for
    from wpa.lead_model import examples_from_logs as lead_examples
    from wpa.model import load
    from wpa.policy import PolicyModel
    from wpa.policy_data import _iter_logs, examples_for_game
    from wpa.replace_model import ReplaceModel
    from wpa.replace_model import examples_for_game as replace_examples
    from wpa.spreads import UsageStore

    fmt, g = a.format, a.groups
    split = "validation" if a.try_on_validation else "test"
    models = [
        f"{a.models.name} {g} (the average of 10)",
        f"{a.preview_models.name} {g} (sheets hidden)",
        f"{fmt} bring, leads, policy, replace",
    ]
    if a.try_on_validation:  # a trial of the command itself: nothing is opened
        lines = [
            f"{fmt}: a TRIAL on the validation split (the test split unopened)",
            "",
        ]
    else:
        n = log_opening(a.openings, fmt, a.po_approved, models)
        lines = [
            f"{fmt}: the test split, opened with the PO's approval ({a.po_approved}); "
            f"opening {n} in all (logged in {a.openings})",
            "",
        ]
    print(lines[0], flush=True)

    # the averaged win model
    raw = load_table(a.features, fmt, split)
    x = select(raw, g)
    model = load_averaged(a.models, model_for(fmt), g, x.columns)
    assert model is not None, "the averaged model first (wpa.ensemble finish)"
    win = score(model.predict(x.X), raw.y, raw.unit, v0_from_table(raw))
    lines += [
        describe(
            fmt, f"{a.models.name} (average of 10) on the {split.upper()} split", win
        )
    ]
    del raw, x
    # the win model with the opponent's sheet hidden
    raw = load_table(a.preview_features, fmt, split)
    x = select(raw, g)
    pm = load(a.preview_models / model_for(fmt) / f"{g}.pkl", list(x.columns))
    hidden = score(pm.predict(x.X), raw.y, raw.unit, v0_from_table(raw))
    lines += [
        "",
        describe(fmt, f"{a.preview_models.name} on the {split.upper()} split", hidden),
    ]
    del raw, x
    fails = gate_failures({fmt: win}) + gate_failures({f"{fmt} hidden": hidden})
    print("\n".join(lines), flush=True)

    # the bring, lead, choice and forced-switch models on the test games
    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    test_only = {t: "test" for t, s in splits.items() if s == split}
    logs = []
    for tag, log in _iter_logs(a.logs):
        try:
            if format_of(tag) == fmt:
                logs.append((tag, log))
        except Exception:
            continue
    bring = BringModel.load(a.bring)
    ex = bring_examples(logs, test_only).get("test", [])
    r = bring_evaluate(bring, ex).get(fmt, {})
    lines += [
        "",
        "The other models on the test games, against a uniform guess",
        f"  bring: {r.get('games', 0)} sides; the four brought, log chance "
        f"{r.get('log_chance', 0):.3f} (uniform {r.get('uniform', 0):.3f}); most "
        f"likely set right {100 * r.get('top_right', 0):.0f}%",
    ]
    leads = LeadModel.load(a.leads)
    lx = lead_examples(logs, test_only).get("test", [])
    lines.append(
        _choice_line(
            "leads", choice_scores(leads.chances_x, groups_for(lx, leads.rates))
        )
    )
    policy = PolicyModel.load(a.policy)
    replace = ReplaceModel.load(a.replace)
    dex, table, moves = K._choice_tools(a)
    store = UsageStore(a.usage)
    tests = [(t, log) for t, log in logs if test_only.get(t) == "test"]
    pg, rg = [], []
    with Calc() as calc:
        for i, (tag, log) in enumerate(tests):
            pg += examples_for_game(
                tag, log, fmt, dex, moves, table, calc, store, bring, policy.rates[fmt]
            )
            rg += replace_examples(tag, log, fmt, dex, table, calc, store, bring)
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{len(tests)} test games", flush=True)
    ps = choice_scores(policy.chances, pg, skip_single=False)
    lines.append(_choice_line(f"choices ({len(tests)} games)", ps))
    lines.append(_choice_line("forced switches", choice_scores(replace.chances, rg)))
    if not ps["beats"]:
        fails.append(f"{fmt}: the choice model does not beat a uniform guess")
    lines += [""] + [f"FAIL {f}" for f in fails]
    lines.append(f"Gate on the {split} split: " + ("FAILED" if fails else "passed"))
    text = "\n".join(lines) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    return text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--format", required=True)
    p.add_argument(
        "--po-approved",
        required=True,
        help="the date the PO approved this opening (it is logged)",
    )
    p.add_argument("--features", type=Path, default=Path("features_v4b_mc"))
    p.add_argument(
        "--preview-features", type=Path, default=Path("features_v4_preview_mc")
    )
    p.add_argument("--models", type=Path, default=Path("models_v4_avg"))
    p.add_argument("--preview-models", type=Path, default=Path("models_v4_preview"))
    p.add_argument("--groups", default="ABCDEFGHIJ")
    p.add_argument("--logs", type=Path, default=Path("logs_mc"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--policy", type=Path, default=Path("models_v4/regmc/policy.json"))
    p.add_argument("--leads", type=Path, default=Path("models_v4/regmc/leads.json"))
    p.add_argument("--replace", type=Path, default=Path("models_v4/regmc/replace.json"))
    p.add_argument("--bring", type=Path, default=Path("models_v4/regmc/bring.json"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--openings", type=Path, default=OPENINGS)
    p.add_argument("--out", type=Path, default=Path("reports/test_regmc.txt"))
    p.add_argument(
        "--try-on-validation",
        action="store_true",
        help="run the command on the validation split instead, to try it: the "
        "test split is not opened and nothing is logged",
    )
    return p


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    print(run(parser().parse_args(argv)))


if __name__ == "__main__":
    main()
