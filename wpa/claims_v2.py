"""Expert claims re-scored on the decision table (Week 6 Task 5). REPORT ONLY.

Week 5 (`wpa/claims.py`) built each claim's follow-up positions by editing
feature rows, so a Pokemon coming in was anonymous and its speed unknown. Here
the follow-ups are made by editing the board: who faints, who comes in, one
turn off every timer. The features are then computed again by the code that
builds the training table, so the speed (F), sheet (D, E) and timer (C)
features follow the change.

Who can come in is taken from the game itself: the Pokemon a player brought
are the ones that appear at some point, and a position is used only when all
four of the side that changes are known. That reads later turns of the game,
which is fine here (it builds the positions the claim talks about, "strong
sweepers behind the actives"); the model only ever sees the public board of
each follow-up.

Choices are a small game tree: the outer level is our choice (we take the
best), the inner level is theirs (they take the worst for us). Approximations,
the same for every follow-up of a claim: nobody on the other side is damaged,
counters such as Protect's are reset, and the decided turn's own end-of-turn
field record is not used.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from itertools import combinations
from pathlib import Path

from wpa.timer_join import JoinedTimers

BRING = 4
OUR, THEIR = "our_pokemon", "opp_pokemon"


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------


def tick(j: JoinedTimers) -> JoinedTimers:
    """The next turn's start: one turn off every timer, finished ones gone,
    counters reset (nobody repeats Protect in the passing turn)."""

    def spans(xs):
        return tuple(
            (e, t, max(0, lo - 1), hi - 1) for e, t, lo, hi in xs if hi - 1 > 0
        )

    return JoinedTimers(
        ours=spans(j.ours),
        theirs=spans(j.theirs),
        field=spans(j.field),
        moment="turn_start",
    )


def _revealed(p: Mapping) -> bool:
    return bool(p["active"] or p["fainted"] or p["hp_fraction"] > 0)


def brought(states: Sequence[Mapping], key: str) -> set[int]:
    """Positions of one side that appear at any point of the game."""
    return {i for s in states for i, p in enumerate(s[key]) if _revealed(p)}


def reserve(states: Sequence[Mapping], k: int, key: str) -> list[int]:
    """Brought, alive and not active at decision k: who can come in."""
    s = states[k]
    return sorted(
        i
        for i in brought(states, key)
        if not s[key][i]["fainted"] and not s[key][i]["active"]
    )


def _active(s: Mapping, key: str) -> list[int]:
    return [i for i, p in enumerate(s[key]) if p["active"] and not p["fainted"]]


def _to_id(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


Edit = tuple


def follow_up(
    states: Sequence[dict], k: int, j: JoinedTimers, edits: Sequence[Edit]
) -> tuple[list[dict], JoinedTimers]:
    """The next turn's start after `edits` to the board at decision k:
    ("faint", side, i), ("bring_in", side, i), ("damage", side, i, amount)."""
    s = copy.deepcopy(states[k])
    s["observations"] = []
    s["turn"] += 1
    s["decision_index"] = 0
    s["moment"] = "turn_start"
    gone: dict[str, set[str]] = {OUR: set(), THEIR: set()}
    for e in edits:
        op, key, i = e[0], e[1], e[2]
        p = s[key][i]
        if op == "faint":
            p.update(hp_fraction=0.0, fainted=True, active=False, boosts={}, status="")
            gone[key].add(p["species"])
        elif op == "bring_in":
            p.update(active=True, hp_fraction=p["hp_fraction"] or 1.0, boosts={})
        elif op == "damage":
            p["hp_fraction"] = max(0.01, p["hp_fraction"] - e[3])
        else:
            raise ValueError(op)
    t = tick(j)

    def keep(spans, key):
        return tuple(
            x
            for x in spans
            if x[1] == "side" or _to_id(x[1].split(": ", 1)[-1]) not in gone[key]
        )

    t = JoinedTimers(
        ours=keep(t.ours, OUR),
        theirs=keep(t.theirs, THEIR),
        field=t.field,
        moment=t.moment,
    )
    before = [*states[:k], dict(states[k], observations=[])]
    return [*before, s], t


def features_at(
    states, k, role, j, sheets, dex, table, groups, ctx=None
) -> dict[str, float]:
    from wpa.features import state_features

    return state_features(states, k, role, j, sheets, dex, table, groups, ctx)


def _leaf(states, k, role, j, sheets, dex, table, groups, ctx=None) -> Callable:
    """Features of a follow-up; the spreads stay those at the decision."""

    def f(edits):
        ss, jj = follow_up(states, k, j, edits)
        return features_at(ss, len(ss) - 1, role, jj, sheets, dex, table, groups, ctx)

    return f


def value(tree: Sequence[Sequence[float]]) -> float:
    """Our best choice (outer) against their best reply (inner)."""
    return max(min(inner) for inner in tree)


# --------------------------------------------------------------------------
# EC-001: do not knock out both if it brings their sweepers in under Tailwind
# --------------------------------------------------------------------------


def _tailwind(spans) -> int:
    return max(
        (lo for e, t, lo, _hi in spans if e == "tailwind" and t == "side"), default=0
    )


def is_ec001(states: Sequence[Mapping], k: int, j: JoinedTimers) -> bool:
    """Turn start; their Tailwind has 1-2 turns left and ours is not up; their
    two active Pokemon are weakened (60% hit points or less between them) and
    nobody of theirs has fainted; all four of theirs are known, so exactly two
    wait in the back; we have three or more left."""
    s = states[k]
    if (
        j.moment != "turn_start"
        or _tailwind(j.theirs) not in (1, 2)
        or _tailwind(j.ours)
    ):
        return False
    act = _active(s, THEIR)
    return (
        len(act) == 2
        and not any(p["fainted"] for p in s[THEIR])
        and sum(s[THEIR][i]["hp_fraction"] for i in act) <= 0.6
        and len(brought(states, THEIR)) == BRING
        and len(reserve(states, k, THEIR)) == 2
        and sum(p["fainted"] for p in s[OUR]) <= 1
    )


def ec001_tree(states, k, role, j, sheets, dex, table, groups, ctx=None) -> dict:
    """double_ko: both of theirs faint and the reserve comes in; single_ko: we
    pick which one faints (outer), they pick who comes in (inner); stall."""
    f = _leaf(states, k, role, j, sheets, dex, table, groups, ctx)
    s = states[k]
    act, back = _active(s, THEIR), reserve(states, k, THEIR)
    faint_all = [("faint", THEIR, a) for a in act]
    return {
        "double_ko": [
            [
                f(faint_all + [("bring_in", THEIR, b) for b in pick])
                for pick in combinations(back, min(len(act), len(back)))
            ]
        ],
        "single_ko": [
            [f([("faint", THEIR, a), ("bring_in", THEIR, b)]) for b in back]
            for a in act
        ],
        "stall": [[f([])]],
    }


def ec001_threat(tree: Mapping) -> bool:
    """The danger the claim names: after a double knock-out, something of
    theirs acts before our fastest."""
    return all(r["f_their_first"] == 1 for r in tree["double_ko"][0])


def ec001_premise(now: Mapping[str, float], tree: Mapping) -> bool:
    """The claim's own situation: our pair outspeeds theirs now, and after a
    double knock-out something of theirs acts before our fastest."""
    return now["f_our_outspeeds"] == 4 and ec001_threat(tree)


# --------------------------------------------------------------------------
# EC-002: sacrifice the spent Pokemon to keep the strong one
# --------------------------------------------------------------------------


def _spent_strong(s: Mapping) -> tuple[int, int] | None:
    act = _active(s, OUR)
    if len(act) != 2:
        return None
    a, b = sorted(act, key=lambda i: s[OUR][i]["hp_fraction"])
    if 0 < s[OUR][a]["hp_fraction"] <= 0.3 and s[OUR][b]["hp_fraction"] >= 0.7:
        return a, b
    return None


def is_ec002(states: Sequence[Mapping], k: int, j: JoinedTimers) -> bool:
    """Turn start; we have two active, one spent (30% hit points or less) and
    one strong (70% or more); all four of ours are known, one or more in the back."""
    return (
        j.moment == "turn_start"
        and _spent_strong(states[k]) is not None
        and len(brought(states, OUR)) == BRING
        and len(reserve(states, k, OUR)) >= 1
    )


def ec002_tree(
    states, k, role, j, sheets, dex, table, groups, ctx=None, damage=0.5
) -> dict:
    """sacrifice: the spent one faints and we pick who comes in (outer);
    keep: the spent one lives and the strong one takes `damage`."""
    f = _leaf(states, k, role, j, sheets, dex, table, groups, ctx)
    pair = _spent_strong(states[k])
    assert pair is not None
    spent, strong = pair
    return {
        "sacrifice": [
            [f([("faint", OUR, spent), ("bring_in", OUR, b)])]
            for b in reserve(states, k, OUR)
        ],
        "keep": [[f([("damage", OUR, strong, damage)])]],
    }


def ec001_damage_premise(now: Mapping[str, float], tree: Mapping) -> bool:
    """The claim in damage terms (group G): their active pair cannot take 40% of
    either of ours, and after a double knock-out some way in for their reserve
    knocks one of ours out this turn."""
    return now["g_their_best_dmg"] < 0.4 and any(
        r["g_their_ko_n"] >= 1 for r in tree["double_ko"][0]
    )


def ec002_damage_premise(tree: Mapping) -> bool:
    """EC-002's advantage in damage terms (group G, which carries type match-ups):
    some sacrifice leaves us hitting their board harder than keeping does."""
    keep = tree["keep"][0][0]["g_our_dmg_board"]
    return any(o[0]["g_our_dmg_board"] > keep for o in tree["sacrifice"])


def ec002_premise(tree: Mapping) -> bool:
    """The claim's own condition: some sacrifice leaves us outspeeding more of
    their Pokemon than keeping does."""
    keep = tree["keep"][0][0]["f_our_outspeeds"]
    return any(o[0]["f_our_outspeeds"] > keep for o in tree["sacrifice"])


CLAIMS = {
    "EC-001": (is_ec001, ec001_tree, ("single_ko", "stall"), "double_ko"),
    "EC-002": (is_ec002, ec002_tree, ("sacrifice",), "keep"),
}


# --------------------------------------------------------------------------
# Finding the positions (validation split) and scoring them
# --------------------------------------------------------------------------

GROUPS = "ABCDEF"


def scan_shard(
    shard: int,
    *,
    logs_dir,
    splits: Mapping[str, str],
    dexes: Mapping,
    tables: Mapping,
    formats: Sequence[str],
    per_shard: int,
    groups: str = GROUPS,
    usage_dir=None,
) -> list[dict]:
    """Every EC-001 position and up to `per_shard` EC-002 positions per format
    in one shard of validation games, with their follow-ups' features. With
    `usage_dir`, each position has its damage context (real Speed, group G)."""
    import gzip
    import json

    from wpa.decisions import build_game
    from wpa.features import _worker_tools, columns, damage_contexts
    from wpa.formats import format_of
    from wpa.team_sheets import sheets_from_log

    cols = columns(groups)
    vec = lambda r: [round(r[c], 6) for c in cols]  # noqa: E731
    calc = store = None
    if usage_dir is not None:
        calc, store = _worker_tools(usage_dir)
    out: list[dict] = []
    ec002_count = dict.fromkeys(formats, 0)
    with gzip.open(
        logs_dir / f"part-{shard:03d}.jsonl.gz", "rt", encoding="utf-8"
    ) as fh:
        for line in fh:
            d = json.loads(line)
            tag, log = d["tag"], d["log"]
            fmt = format_of(tag)
            if fmt not in formats or splits.get(tag) != "validation":
                continue
            game = build_game(log, tables[fmt])
            sheets = sheets_from_log(log)
            contexts: dict | None = None  # worked out at the game's first position

            def context(role: str, k: int):
                nonlocal contexts
                if calc is None or len(sheets) != 2:
                    return None
                if contexts is None:
                    contexts = damage_contexts(
                        tag, log, game, sheets, dexes[fmt], calc, store
                    )
                return contexts[role][k]

            for role in ("p1", "p2"):
                states, joined = game.states[role], game.joined[role]
                if states[-1]["outcome"] is None:
                    continue
                for k in range(len(states) - 1):
                    j = joined[k] or JoinedTimers(moment=states[k].get("moment", ""))
                    for claim, (is_pos, build, _better, _worse) in CLAIMS.items():
                        if claim == "EC-002" and ec002_count[fmt] >= per_shard:
                            continue
                        if not is_pos(states, k, j):
                            continue
                        args = (
                            states,
                            k,
                            role,
                            j,
                            sheets,
                            dexes[fmt],
                            tables[fmt],
                            groups,
                            context(role, k),
                        )
                        now = features_at(*args)
                        tree = build(*args)
                        premise = (
                            ec001_premise(now, tree)
                            if claim == "EC-001"
                            else ec002_premise(tree)
                        )
                        damage = None
                        if "G" in groups and args[-1] is not None:
                            damage = (
                                ec001_damage_premise(now, tree)
                                if claim == "EC-001"
                                else ec002_damage_premise(tree)
                            )
                        if claim == "EC-002":
                            ec002_count[fmt] += 1
                        out.append(
                            {
                                "claim": claim,
                                "format": fmt,
                                "tag": tag,
                                "role": role,
                                "turn": states[k]["turn"],
                                "premise": premise,
                                "damage_premise": damage,
                                "now": vec(now),
                                "tree": {
                                    n: [[vec(r) for r in inner] for inner in outer]
                                    for n, outer in tree.items()
                                },
                            }
                        )
    return out


def _predictors(fmt: str, groups: str, models_v1, specs) -> dict[str, Callable]:
    """name -> predict(X with the columns of `groups`) for v0, v1 and each
    `NAME=FOLDER:GROUPS` in `specs` (the Reg M-A model, or the pooled one for
    Reg M-B, recalibrated if it was)."""
    import numpy as np

    from wpa.evaluate import v0_from_table, with_format_flag
    from wpa.features import Table, columns
    from wpa.model import load

    cols = columns(groups)

    def table(X, cs):
        n = len(X)
        z = np.zeros(n)
        return Table(
            X,
            z.astype(np.int8),
            z.astype(str),
            z.astype(str),
            z.astype(str),
            z.astype(np.int16),
            list(cs),
        )

    def subset(gs):
        return [cols.index(c) for c in columns(gs)]

    out: dict[str, Callable] = {"v0": lambda X: v0_from_table(table(X, cols))}
    v1 = load(models_v1 / fmt / "v1.pkl", columns("ABCDE"))
    s1 = subset("ABCDE")
    out["v1"] = lambda X: v1.predict(X[:, s1])
    which = "regma" if fmt == "regma" else "pooled"
    for spec in specs:
        name, _, rest = spec.partition("=")
        folder, _, gs = rest.partition(":")
        d = Path(folder) / which
        path = d / f"{gs}.recal.pkl"
        path = path if path.exists() else d / f"{gs}.pkl"
        sub = subset(gs)
        if which == "pooled":
            m = load(path, [*columns(gs), "z_format_regmb"])
            out[name] = lambda X, m=m, sub=sub, gs=gs: m.predict(
                with_format_flag(table(X[:, sub], columns(gs)), 1.0).X
            )
        else:
            m = load(path, columns(gs))
            out[name] = lambda X, m=m, sub=sub: m.predict(X[:, sub])
    return out


def score(records: Sequence[dict], predict: Callable) -> list[dict[str, float]]:
    """For each position, the value of each follow-up under one model."""
    import numpy as np

    leaves = [
        v
        for r in records
        for outer in r["tree"].values()
        for inner in outer
        for v in inner
    ]
    if not leaves:
        return []
    p = iter(predict(np.array(leaves, dtype=np.float32)).tolist())
    out = []
    for r in records:
        out.append(
            {
                n: value([[next(p) for _ in inner] for inner in outer])
                for n, outer in r["tree"].items()
            }
        )
    return out


def summarise(records, values, better, worse, subsets=None) -> dict:
    """Agreement and mean values: all positions, those where the claim's
    premise holds, and any `subsets` (name -> test on a record)."""
    import numpy as np

    def part(idx):
        if not idx:
            return {"positions": 0}
        agree = [max(values[i][b] for b in better) > values[i][worse] for i in idx]
        names = values[idx[0]].keys()
        return {
            "positions": len(idx),
            "agrees": float(np.mean(agree)),
            "mean": {n: float(np.mean([values[i][n] for i in idx])) for n in names},
        }

    every = list(range(len(records)))
    out = {
        "all": part(every),
        "premise": part([i for i in every if records[i]["premise"]]),
    }
    for name, test in (subsets or {}).items():
        out[name] = part([i for i in every if test(records[i])])
    return out


def main() -> None:
    import argparse
    import gzip
    import json
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    p = argparse.ArgumentParser(
        description="Expert claims on the decision table (report only)."
    )
    p.add_argument("command", choices=["scan", "report"])
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--out", type=Path, default=Path("claims_v2"))
    p.add_argument("--shards", type=int, default=64)
    p.add_argument("--only", type=str, help="scan only these shards, e.g. 0-15")
    p.add_argument(
        "--per-shard",
        type=int,
        default=12,
        help="EC-002 positions per shard and format",
    )
    p.add_argument("--formats", nargs="+", default=["regma", "regmb"])
    p.add_argument("--models-v1", type=Path, default=Path("models"))
    p.add_argument(
        "--model",
        action="append",
        help="NAME=FOLDER:GROUPS, e.g. v3=models_v3:ABCDEFG (repeatable; "
        "default v2=models_v2:ABCDEF)",
    )
    p.add_argument("--groups", default=GROUPS, help="feature groups to record")
    p.add_argument(
        "--usage",
        type=Path,
        help="Smogon usage statistics: spreads, real Speed and damage (G)",
    )
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.command == "scan":
        from wpa.durations import load_all
        from wpa.team_sheets import load_dexes

        dexes, tables = load_dexes(a.showdown), load_all(a.showdown)
        splits = json.loads(a.splits.read_text(encoding="utf-8"))["games"]
        wanted = range(a.shards)
        if a.only:
            lo, _, hi = a.only.partition("-")
            wanted = range(int(lo), int(hi or lo) + 1)
        for s in wanted:
            path = a.out / f"part-{s:03d}.jsonl.gz"
            if path.exists():
                continue
            got = scan_shard(
                s,
                logs_dir=a.logs,
                splits=splits,
                dexes=dexes,
                tables=tables,
                formats=a.formats,
                per_shard=a.per_shard,
                groups=a.groups,
                usage_dir=a.usage,
            )
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:
                for r in got:
                    fh.write(json.dumps(r) + "\n")
            tmp.replace(path)
            print(f"shard {s}: {len(got)} positions")
        return
    records = []
    for path in sorted(a.out.glob("part-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            records += [json.loads(line) for line in fh]
    summary: dict = {}
    scanned = len(list(a.out.glob("part-*.jsonl.gz")))
    lines = [f"Expert claims on the decision table ({scanned} shards scanned)"]
    from wpa.features import columns

    first = columns(a.groups).index("f_their_first")
    subsets: dict = {
        "EC-001": {
            "threat": lambda r: all(v[first] == 1 for v in r["tree"]["double_ko"][0])
        },
        "EC-002": {},
    }
    if "G" in a.groups:
        for claim in subsets:
            subsets[claim]["damage"] = lambda r: bool(r.get("damage_premise"))
    specs = a.model or ["v2=models_v2:ABCDEF"]
    for fmt in a.formats:
        models = _predictors(fmt, a.groups, a.models_v1, specs)
        for claim, (_is, _build, better, worse) in CLAIMS.items():
            rs = [r for r in records if r["format"] == fmt and r["claim"] == claim]
            for name, predict in models.items():
                s = summarise(rs, score(rs, predict), better, worse, subsets.get(claim))
                summary[f"{fmt} {claim} {name}"] = s
                for part, label in (
                    ("all", "all positions"),
                    ("premise", "claim's premise holds"),
                    ("threat", "their reserve acts first after a double knock-out"),
                    ("damage", "the claim's premise in damage terms"),
                ):
                    if part not in s:
                        continue
                    r = s[part]
                    if not r["positions"]:
                        lines.append(f"{fmt} {claim} {name} ({label}): no positions")
                        continue
                    means = ", ".join(
                        f"{k} {v:.3f}" for k, v in sorted(r["mean"].items())
                    )
                    lines.append(
                        f"{fmt} {claim} {name} ({label}): {r['positions']} positions; "
                        f"prefers the claim's choice in {r['agrees']:.0%}; mean {means}"
                    )
    text = "\n".join(lines) + "\n"
    print(text)
    (a.out / "report.txt").write_text(text, encoding="utf-8")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
