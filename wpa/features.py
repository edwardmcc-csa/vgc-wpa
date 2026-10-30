"""The feature table for the v1 model (Week 5 Task 5).

One row per decision point, from one player's side ("our" is the player whose
file it is). Five groups, each switchable, added in this order in the ablation:

* **A** state only: Pokemon fainted, remaining (each side brings four), seen and
  unseen, hit points, who is active, the turn, the game in the set and the score;
* **B** field presence from the observations of *earlier turns only*
  (docs/STATE-TIMING.md: a state's own observations can be the future);
* **C** timers at the decision (docs/TIMER-JOIN.md): turns left on each field,
  side and Pokemon effect, sleep/freeze/confusion with the chance of ending at
  the next attempt, and when in the turn the decision is;
* **D** team-sheet capabilities by where the Pokemon is (docs/TEAM-SHEETS.md);
* **E** which sheet positions are still unseen.

Columns are named `<group>_<our|their|field|...>_...`, so swapping every
`_our_` with `_their_` mirrors a row (`mirror_permutation`). Features read only
the state fields in `ALLOWED_STATE_FIELDS` and the Pokemon fields in
`ALLOWED_POKEMON_FIELDS`; `outcome` is the label and is read only by
`rows_for_file` (tests enforce both).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from wpa.durations import Durations, hazards
from wpa.state_timing import decision_indices, usable_observations
from wpa.team_sheets import Dex, SheetMon, feature_names, side_features, to_id
from wpa.timer_join import JoinedTimers

ALLOWED_STATE_FIELDS = (
    "turn",
    "decision_index",
    "our_pokemon",
    "opp_pokemon",
    "game_index",
    "set_score_entering_game",
    "observations",
)
ALLOWED_POKEMON_FIELDS = ("species", "hp_fraction", "fainted", "active")
SIDES = ("our", "their")
BRING = 4

FIELD_EFFECTS = (
    "trickroom",
    "gravity",
    "magicroom",
    "wonderroom",
    "raindance",
    "sunnyday",
    "sandstorm",
    "snowscape",
    "electricterrain",
    "grassyterrain",
    "psychicterrain",
    "mistyterrain",
)
SIDE_EFFECTS = ("tailwind", "reflect", "lightscreen", "auroraveil", "safeguard", "mist")
MON_EFFECTS = (
    "encore",
    "taunt",
    "disable",
    "healblock",
    "yawn",
    "perishsong",
    "partiallytrapped",
    "wish",
    "futuremove",
)
COUNTERS = ("slp", "frz", "confusion")
MOMENTS = ("preview", "turn_start", "mid_turn", "after_turn")
_TRAPS = {
    "bind",
    "clamp",
    "firespin",
    "infestation",
    "magmastorm",
    "sandtomb",
    "snaptrap",
    "thundercage",
    "whirlpool",
    "wrap",
}

B_WEATHER = {
    "raindance": "rain",
    "sunnyday": "sun",
    "sandstorm": "sand",
    "snowscape": "snow",
    "snow": "snow",
    "hail": "snow",
}
B_FIELDS = (
    "trickroom",
    "gravity",
    "magicroom",
    "wonderroom",
    "electricterrain",
    "grassyterrain",
    "psychicterrain",
    "mistyterrain",
)
B_SIDE = ("tailwind", "reflect", "lightscreen", "auroraveil")


# --------------------------------------------------------------------------
# Column names
# --------------------------------------------------------------------------


def _cols_a() -> list[str]:
    out = []
    for s in SIDES:
        out += [
            f"a_{s}_{k}"
            for k in (
                "fainted",
                "remaining",
                "seen_alive",
                "unseen",
                "hp_seen",
                "hp_active",
                "active",
            )
        ]
    return out + [
        "a_turn",
        "a_decision_index",
        "a_game_index",
        "a_bo3",
        "a_score_our",
        "a_score_their",
    ]


def _cols_b() -> list[str]:
    out = ["b_has_obs"]
    out += [f"b_weather_{w}" for w in ("rain", "sun", "sand", "snow")]
    out += [f"b_field_{f}" for f in B_FIELDS]
    out += [f"b_{s}_{e}" for s in SIDES for e in B_SIDE]
    return out


def _cols_c() -> list[str]:
    out = [f"c_moment_{m}" for m in MOMENTS]
    out += [f"c_field_{e}" for e in FIELD_EFFECTS]
    for s in SIDES:
        out += [f"c_{s}_{e}" for e in SIDE_EFFECTS]
        out += [f"c_{s}_{e}" for e in MON_EFFECTS]
        out += [f"c_{s}_partiallytrapped_max"]
        for c in COUNTERS:
            out += [f"c_{s}_{c}_n", f"c_{s}_{c}_end_next"]
    return out


def _cols_d() -> list[str]:
    out = []
    for s in SIDES:
        out += [
            f"d_{n}"
            for n in feature_names(s)
            if "_unseen_pos" not in n
            and not n.endswith(("_unseen_top4", "_unseen_bottom2"))
            and n != f"{s}_unseen"
        ]
    return out


def _cols_e() -> list[str]:
    out = []
    for s in SIDES:
        out += [f"e_{s}_unseen_pos{k}" for k in range(1, 7)]
        out += [f"e_{s}_unseen_top4", f"e_{s}_unseen_bottom2"]
    return out


_BUILDERS = {"A": _cols_a, "B": _cols_b, "C": _cols_c, "D": _cols_d, "E": _cols_e}


def columns(groups: str) -> list[str]:
    out: list[str] = []
    for g in "ABCDE":
        if g in groups:
            out += _BUILDERS[g]()
    return out


def mirror_permutation(cols: Sequence[str]) -> list[int]:
    """Index map that swaps every our/their column pair (others stay)."""
    index = {c: i for i, c in enumerate(cols)}
    out = []
    for c in cols:
        if "_our_" in c or c.endswith("_our"):
            other = c.replace("_our_", "_their_") if "_our_" in c else c[:-4] + "_their"
        elif "_their_" in c or c.endswith("_their"):
            other = c.replace("_their_", "_our_") if "_their_" in c else c[:-6] + "_our"
        else:
            other = c
        out.append(index[other])
    return out


# --------------------------------------------------------------------------
# Groups
# --------------------------------------------------------------------------


def _side_a(side: Sequence) -> dict[str, float]:
    fainted = seen_alive = unseen = active = 0
    hp_seen = hp_active = 0.0
    for p in side:
        hp = p["hp_fraction"]
        if p["fainted"]:
            fainted += 1
        elif p["active"]:
            active += 1
            seen_alive += 1
            hp_seen += hp
            hp_active += hp
        elif hp > 0:
            seen_alive += 1
            hp_seen += hp
        else:
            unseen += 1
    return {
        "fainted": fainted,
        "remaining": max(0, BRING - fainted),
        "seen_alive": seen_alive,
        "unseen": unseen,
        "hp_seen": hp_seen,
        "hp_active": hp_active,
        "active": active,
    }


def _group_a(s: Mapping) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, side in (("our", s["our_pokemon"]), ("their", s["opp_pokemon"])):
        for k, v in _side_a(side).items():
            out[f"a_{name}_{k}"] = float(v)
    gi = s.get("game_index")
    score = s.get("set_score_entering_game")
    out["a_turn"] = float(s["turn"])
    out["a_decision_index"] = float(s["decision_index"])
    out["a_game_index"] = float(gi or 0)
    out["a_bo3"] = float(gi is not None)
    out["a_score_our"] = float(score[0]) if score is not None else -1.0
    out["a_score_their"] = float(score[1]) if score is not None else -1.0
    return out


def _group_b(states: Sequence[dict], k: int, role: str) -> dict[str, float]:
    out = dict.fromkeys(_cols_b(), 0.0)
    obs = usable_observations(states, k)
    if not obs:
        return out
    last = obs[-1]
    out["b_has_obs"] = 1.0
    w = B_WEATHER.get(to_id(last.get("weather") or ""))
    if w:
        out[f"b_weather_{w}"] = 1.0
    for f in last.get("fields") or ():
        if to_id(f) in B_FIELDS:
            out[f"b_field_{to_id(f)}"] = 1.0
    for entry in last.get("side_conditions") or ():
        side, _, name = entry.partition(":")
        if to_id(name) in B_SIDE:
            who = "our" if side == role else "their"
            out[f"b_{who}_{to_id(name)}"] = 1.0
    return out


def _end_next(table: Durations | None, counter: str, attempts: int) -> float:
    if table is None or counter not in table.counted:
        return 0.0
    c = table.counted[counter]
    h = hazards(c.start_distribution, c.end_chance_per_attempt or Fraction(0))
    return float(h[attempts]) if attempts < len(h) else 1.0


def _group_c(j: JoinedTimers | None, table: Durations | None) -> dict[str, float]:
    out = dict.fromkeys(_cols_c(), 0.0)
    if j is None:
        return out
    if j.moment in MOMENTS:
        out[f"c_moment_{j.moment}"] = 1.0
    for eid, _t, lo, _hi in j.field:
        if eid in FIELD_EFFECTS:
            out[f"c_field_{eid}"] = max(out[f"c_field_{eid}"], float(lo))
    for side, spans, counters in (
        ("our", j.ours, j.our_counters),
        ("their", j.theirs, j.their_counters),
    ):
        for eid, target, lo, hi in spans:
            key = "partiallytrapped" if eid in _TRAPS else eid
            if target == "side" and key in SIDE_EFFECTS:
                out[f"c_{side}_{key}"] = max(out[f"c_{side}_{key}"], float(lo))
            elif key in MON_EFFECTS:
                out[f"c_{side}_{key}"] = max(out[f"c_{side}_{key}"], float(lo))
                if key == "partiallytrapped":
                    m = f"c_{side}_partiallytrapped_max"
                    out[m] = max(out[m], float(hi))
        for cid, _target, attempts in counters:
            if cid in COUNTERS:
                out[f"c_{side}_{cid}_n"] += 1.0
                out[f"c_{side}_{cid}_end_next"] += _end_next(table, cid, attempts)
    return out


def _group_de(
    s: Mapping,
    role: str,
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    groups: str,
) -> dict[str, float]:
    out: dict[str, float] = {}
    other = "p2" if role == "p1" else "p1"
    for name, side, r in (
        ("our", s["our_pokemon"], role),
        ("their", s["opp_pokemon"], other),
    ):
        f = side_features(sheets[r], side, dex, name)
        if "D" in groups:
            for c in _cols_d():
                if c.startswith(f"d_{name}_"):
                    out[c] = f[c[2:]]
        if "E" in groups:
            for c in _cols_e():
                if c.startswith(f"e_{name}_"):
                    out[c] = f[c[2:]]
    return out


def state_features(
    states: Sequence[dict],
    k: int,
    role: str,
    joined: JoinedTimers | None,
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    table: Durations | None,
    groups: str,
) -> dict[str, float]:
    """Features for the decision at states[k], from states[: k + 1] only."""
    s = states[k]
    row: dict[str, float] = {}
    if "A" in groups:
        row.update(_group_a(s))
    if "B" in groups:
        row.update(_group_b(states, k, role))
    if "C" in groups:
        row.update(_group_c(joined, table))
    if "D" in groups or "E" in groups:
        row.update(_group_de(s, role, sheets, dex, groups))
    return {c: float(row[c]) for c in columns(groups)}


# --------------------------------------------------------------------------
# Rows and files
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    tag: str
    role: str
    unit: str
    turn: int
    decision_index: int
    label: int
    values: tuple[float, ...]


def rows_for_file(
    tag: str,
    role: str,
    states: Sequence[dict],
    joined: Sequence[JoinedTimers | None],
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    table: Durations | None,
    groups: str,
) -> list[Row]:
    """One row per decision of one state file (the terminal state is the label)."""
    label = states[-1]["outcome"]
    if label is None:
        return []
    unit = states[0].get("set_id") or tag
    cols = columns(groups)
    out = []
    for k in decision_indices(states):
        f = state_features(states, k, role, joined[k], sheets, dex, table, groups)
        out.append(
            Row(
                tag,
                role,
                unit,
                states[k]["turn"],
                states[k]["decision_index"],
                int(bool(label)),
                tuple(f[c] for c in cols),
            )
        )
    return out


@dataclass
class Table:
    X: np.ndarray
    y: np.ndarray
    tag: np.ndarray
    role: np.ndarray
    unit: np.ndarray
    turn: np.ndarray
    columns: list[str]


def write_rows(path: Path | str, rows: Sequence[Row], cols: Sequence[str]) -> None:
    X = np.array([r.values for r in rows], dtype=np.float32).reshape(
        len(rows), len(cols)
    )
    np.savez_compressed(
        path,
        X=X,
        y=np.array([r.label for r in rows], dtype=np.int8),
        tag=np.array([r.tag for r in rows]),
        role=np.array([r.role for r in rows]),
        unit=np.array([r.unit for r in rows]),
        turn=np.array([r.turn for r in rows], dtype=np.int16),
        columns=np.array(list(cols)),
    )


def read_rows(path: Path | str) -> Table:
    with np.load(path, allow_pickle=False) as d:
        return Table(
            d["X"],
            d["y"],
            d["tag"],
            d["role"],
            d["unit"],
            d["turn"],
            [str(c) for c in d["columns"]],
        )


def concat(tables: Iterable[Table]) -> Table:
    ts = [t for t in tables if len(t.y)]
    if not ts:
        raise ValueError("no rows")
    cols = ts[0].columns
    for t in ts:
        if t.columns != cols:
            raise ValueError("feature columns differ between parts")
    return Table(
        np.concatenate([t.X for t in ts]),
        np.concatenate([t.y for t in ts]),
        np.concatenate([t.tag for t in ts]),
        np.concatenate([t.role for t in ts]),
        np.concatenate([t.unit for t in ts]),
        np.concatenate([t.turn for t in ts]),
        cols,
    )


def shard_of(tag: str, shards: int) -> int:
    digest = hashlib.sha256(tag.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % shards


# --------------------------------------------------------------------------
# Building from the data
# --------------------------------------------------------------------------


def build_shard(
    shard: int,
    shards: int,
    *,
    states_dir: Path,
    splits: Mapping[str, str],
    timers_path: Path,
    sheets_path: Path,
    dexes: Mapping[str, Dex],
    tables: Mapping[str, Durations],
    out_dir: Path,
    groups: str = "ABCDE",
) -> dict[str, int]:
    """Build one shard of games (by tag hash): one file per format and split."""
    from wpa.formats import format_of
    from wpa.team_sheets import iter_sheet_file
    from wpa.timer_join import align
    from wpa.timers import iter_timer_file

    sheets = {
        t: s
        for t, (_f, s) in iter_sheet_file(sheets_path)
        if shard_of(t, shards) == shard
    }
    cols = columns(groups)
    rows: dict[tuple[str, str], list[Row]] = {}
    counts = {"games": 0, "files": 0, "misaligned": 0, "unassigned": 0, "rows": 0}
    for tag, rec in iter_timer_file(timers_path):
        if shard_of(tag, shards) != shard:
            continue
        if tag not in splits:
            counts["unassigned"] += 1
            continue
        fmt = format_of(tag)
        counts["games"] += 1
        for role in ("p1", "p2"):
            path = states_dir / f"{tag}-{role}.json"
            if not path.exists():
                continue
            states = json.loads(path.read_text(encoding="utf-8"))
            counts["files"] += 1
            joined = align(states, rec.decisions.get(role, []), role)
            if joined is None:
                counts["misaligned"] += 1
                continue
            got = rows_for_file(
                tag, role, states, joined, sheets[tag], dexes[fmt], tables[fmt], groups
            )
            rows.setdefault((fmt, splits[tag]), []).extend(got)
            counts["rows"] += len(got)
    for (fmt, split), rs in rows.items():
        d = out_dir / fmt / split
        d.mkdir(parents=True, exist_ok=True)
        write_rows(d / f"part-{shard:03d}-of-{shards:03d}.npz", rs, cols)
    return counts


def _build_one(args: tuple) -> dict[str, int]:
    shard, shards, opts = args
    from wpa.durations import load_all
    from wpa.team_sheets import load_dexes

    dexes = load_dexes(opts["showdown"])
    tables = load_all(opts["showdown"])
    splits = json.loads(Path(opts["splits"]).read_text(encoding="utf-8"))["games"]
    return build_shard(
        shard,
        shards,
        states_dir=Path(opts["states"]),
        splits=splits,
        timers_path=Path(opts["timers"]),
        sheets_path=Path(opts["sheets"]),
        dexes=dexes,
        tables=tables,
        out_dir=Path(opts["out"]),
    )


def main() -> None:
    import argparse
    from concurrent.futures import ProcessPoolExecutor

    p = argparse.ArgumentParser(description="Build the feature table (Task 5).")
    p.add_argument("--states", default="wpa_states")
    p.add_argument("--splits", default="splits.json")
    p.add_argument("--timers", default="timers.jsonl.gz")
    p.add_argument("--sheets", default="sheets.jsonl.gz")
    p.add_argument("--showdown", default="pokemon-showdown")
    p.add_argument("--out", default="features")
    p.add_argument("--shards", type=int, default=64)
    p.add_argument("--only", type=str, help="build only these shards, e.g. 0-7")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    opts = vars(a)
    wanted = range(a.shards)
    if a.only:
        lo, _, hi = a.only.partition("-")
        wanted = range(int(lo), int(hi or lo) + 1)
    total: dict[str, int] = {}
    jobs = [(s, a.shards, opts) for s in wanted]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for s, counts in zip(wanted, pool.map(_build_one, jobs)):
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            print(f"shard {s}: {counts}", flush=True)
    print(f"total: {total}")


if __name__ == "__main__":
    main()
