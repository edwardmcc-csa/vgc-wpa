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
import math
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
ALLOWED_POKEMON_FIELDS = ("species", "hp_fraction", "fainted", "active", "mega")
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


_F_SIDE = (
    "active_speed_max",
    "active_speed_min",
    "bench_speed_max",
    "unseen_speed_max",
    "unseen_speed_min",
    "scarf_active",
    "outspeeds",
    "first",
    "unseen_outspeeds",
)


def _cols_f() -> list[str]:
    return [f"f_{s}_{k}" for s in SIDES for k in _F_SIDE] + ["f_trickroom"]


# Group G, for each side, from that side's point of view as the attacker:
#   best_dmg      the best share of an opposing active's current hit points one
#                 of our actives can take with one move (capped at 1)
#   dmg_board     over the opposing actives, the best share each can lose
#   ko_n          opposing actives one of ours knocks out this turn (50%+)
#   2hko_n        ... in two hits of the same move (50%+)
#   spread_total  the best spread move's total over both opposing actives
#   bench_best    the best share from a Pokemon seen but not active
#   unseen_best   the best share from a sheet Pokemon not seen yet
#   unseen_ko_n   opposing actives an unseen sheet Pokemon knocks out (50%+)
_G_SIDE = (
    "best_dmg",
    "dmg_board",
    "ko_n",
    "2hko_n",
    "spread_total",
    "bench_best",
    "unseen_best",
    "unseen_ko_n",
)


def _cols_g() -> list[str]:
    return [f"g_{s}_{k}" for s in SIDES for k in _G_SIDE]


_BUILDERS = {
    "A": _cols_a,
    "B": _cols_b,
    "C": _cols_c,
    "D": _cols_d,
    "E": _cols_e,
    "F": _cols_f,
    "G": _cols_g,
    "H": lambda: _cols_h(),
    "I": lambda: _cols_i(),
    "J": lambda: _cols_j(),
}


def columns(groups: str) -> list[str]:
    out: list[str] = []
    for g in "ABCDEFGHIJ":
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


def _speeds(side, sheet, dex: Dex, tailwind: bool):
    """(where, effective speed, has Scarf) for each Pokemon on one side."""
    from wpa.team_sheets import form_of, match_to_state

    out = []
    for p, idx in zip(side, match_to_state(sheet, side)):
        if idx is None or p["fainted"] or not sheet[idx].species:
            continue
        mon = sheet[idx]
        entry = form_of(mon, dex) if p.get("mega") else dex.species.get(mon.species, {})
        base = float((entry.get("baseStats") or {}).get("spe", 0))
        scarf = mon.item == "choicescarf"
        v = base * (1.5 if scarf else 1.0) * (2.0 if tailwind else 1.0)
        where = (
            "active" if p["active"] else ("bench" if p["hp_fraction"] > 0 else "unseen")
        )
        out.append((where, v, scarf))
    return out


@dataclass
class DamageContext:
    """What real Speed (group F) and damage (group G) need at one decision: the
    damage calculator (`wpa.damage.Calc`) and each Pokemon's most likely spread
    there, keyed (role, sheet position from 0) (`wpa.spreads.GameBeliefs.at`)."""

    calc: object
    spreads: Mapping[tuple[str, int], object]
    # each side's odds that each sheet Pokemon was brought (`wpa.bring`), by role
    odds: Mapping[str, Sequence[float]] | None = None


_SCREENS = ("reflect", "lightscreen", "auroraveil")


def _board_state(p: Mapping) -> dict:
    """What the calculator needs of one Pokemon on the board (public fields)."""
    hp = p["hp_fraction"]
    return {
        "mega": bool(p.get("mega")),
        "item": p.get("item") or "",
        "boosts": dict(p.get("boosts") or {}),
        "status": p.get("status") or "",
        "hp": hp if hp > 0 else 1.0,
        "last_move": p.get("last_move") or "",
    }


def _where(p: Mapping) -> str:
    if p["active"]:
        return "active"
    return "bench" if p["hp_fraction"] > 0 else "unseen"


def _roster(side, sheet, sheet_role: str, dex: Dex, ctx: DamageContext):
    """(where, sheet Pokemon, board state, spread, key) for each one standing."""
    from wpa.spreads import default_spread
    from wpa.team_sheets import match_to_state

    out = []
    for p, idx in zip(side, match_to_state(sheet, side)):
        if idx is None or p["fainted"] or not sheet[idx].species:
            continue
        mon = sheet[idx]
        spread = ctx.spreads.get((sheet_role, idx))
        if spread is None:
            base = (dex.species.get(mon.species) or {}).get("baseStats")
            spread = default_spread(mon.nature, base)
        out.append((_where(p), mon, _board_state(p), spread, (sheet_role, idx)))
    return out


def _field(j: JoinedTimers) -> dict:
    from wpa.damage import TERRAIN, WEATHER

    out: dict = {"weather": None, "terrain": None}
    for eid, _t, lo, _hi in j.field:
        if lo > 0 and eid in WEATHER:
            out["weather"] = eid
        elif lo > 0 and eid in TERRAIN:
            out["terrain"] = eid
    return out


def _screens(spans) -> dict[str, bool]:
    return {
        e: any(x == e and t == "side" and lo > 0 for x, t, lo, _h in spans)
        for e in _SCREENS
    }


def _speeds_ctx(rows, dex: Dex, field: Mapping, tailwind: bool, ctx: DamageContext):
    """(where, final Speed from the calculator, has Scarf) for one side."""
    from wpa.spreads import speed_request

    reqs = [
        speed_request(m, st, sp, dex, field, tailwind) for _w, m, st, sp, _k in rows
    ]
    ans = ctx.calc.run(reqs) if reqs else []  # type: ignore[attr-defined]
    return [
        (w, float(a.get("speed", 0)), st["item"] == "choicescarf")
        for (w, _m, st, _sp, _k), a in zip(rows, ans)
    ]


def _group_f(
    s: Mapping,
    role: str,
    joined: JoinedTimers | None,
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    ctx: DamageContext | None = None,
) -> dict[str, float]:
    """Speed, and who acts first with Trick Room reversing it. Without a damage
    context: base Speed (Mega form once Mega Evolved), Choice Scarf x1.5,
    Tailwind x2. With one: the calculator's final Speed for the most likely
    spread, with stage, paralysis, item, Tailwind, and weather or terrain
    abilities. Priority is not included."""
    out = dict.fromkeys(_cols_f(), 0.0)
    other = "p2" if role == "p1" else "p1"
    j = joined or JoinedTimers()
    tw = {
        "our": any(e == "tailwind" and lo > 0 for e, _t, lo, _h in j.ours),
        "their": any(e == "tailwind" and lo > 0 for e, _t, lo, _h in j.theirs),
    }
    tr = any(e == "trickroom" and lo > 0 for e, _t, lo, _h in j.field)
    out["f_trickroom"] = float(tr)
    if ctx is None:
        sp = {
            "our": _speeds(s["our_pokemon"], sheets[role], dex, tw["our"]),
            "their": _speeds(s["opp_pokemon"], sheets[other], dex, tw["their"]),
        }
    else:
        fld = _field(j)
        sp = {
            "our": _speeds_ctx(
                _roster(s["our_pokemon"], sheets[role], role, dex, ctx),
                dex,
                fld,
                tw["our"],
                ctx,
            ),
            "their": _speeds_ctx(
                _roster(s["opp_pokemon"], sheets[other], other, dex, ctx),
                dex,
                fld,
                tw["their"],
                ctx,
            ),
        }

    def before(a: float, b: float) -> bool:
        return a < b if tr else a > b

    def best(vs: list[float]) -> float | None:
        if not vs:
            return None
        return min(vs) if tr else max(vs)

    act = {k: [v for w, v, _ in rows if w == "active"] for k, rows in sp.items()}
    for side, rival in (("our", "their"), ("their", "our")):
        rows = sp[side]
        a = act[side]
        bench = [v for w, v, _ in rows if w == "bench"]
        unseen = [v for w, v, _ in rows if w == "unseen"]
        if a:
            out[f"f_{side}_active_speed_max"] = max(a)
            out[f"f_{side}_active_speed_min"] = min(a)
        if bench:
            out[f"f_{side}_bench_speed_max"] = max(bench)
        if unseen:
            out[f"f_{side}_unseen_speed_max"] = max(unseen)
            out[f"f_{side}_unseen_speed_min"] = min(unseen)
        out[f"f_{side}_scarf_active"] = float(
            sum(1 for w, _v, sc in rows if w == "active" and sc)
        )
        out[f"f_{side}_outspeeds"] = float(
            sum(before(x, y) for x in a for y in act[rival])
        )
        mine, theirs = best(a), best(act[rival])
        if mine is not None and theirs is not None:
            out[f"f_{side}_first"] = float(before(mine, theirs))
        if theirs is not None:
            out[f"f_{side}_unseen_outspeeds"] = float(
                sum(before(x, theirs) for x in unseen)
            )
    return out


def _two_hits(rolls: Sequence[float], hp: float) -> float:
    """Chance two hits of the same move take `hp` (rolls independent)."""
    from bisect import bisect_left

    s = sorted(rolls)
    n = len(s)
    if not n:
        return 0.0
    return sum(n - bisect_left(s, hp - a) for a in s) / (n * n)


def _group_g(
    s: Mapping,
    role: str,
    joined: JoinedTimers | None,
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    ctx: DamageContext | None,
) -> dict[str, float]:
    """Damage, from the calculator, for each side attacking the other's active
    Pokemon (see `_G_SIDE`). Zero without a damage context."""
    out = dict.fromkeys(_cols_g(), 0.0)
    if ctx is None:
        return out
    from wpa.spreads import ALLY_BOOSTS, damage_request

    other = "p2" if role == "p1" else "p1"
    j = joined or JoinedTimers()
    fld = _field(j)
    rows = {
        "our": _roster(s["our_pokemon"], sheets[role], role, dex, ctx),
        "their": _roster(s["opp_pokemon"], sheets[other], other, dex, ctx),
    }
    screens = {"our": _screens(j.ours), "their": _screens(j.theirs)}
    active = {k: [r for r in v if r[0] == "active"] for k, v in rows.items()}
    auras = {r[1].ability for v in active.values() for r in v}
    jobs = []  # (side, where, target index, spread move, request)
    for side, rival in (("our", "their"), ("their", "our")):
        targets = active[rival]
        for where, a_mon, a_st, a_sp, a_key in rows[side]:
            ally = {r[1].ability for r in active[side] if r[4] != a_key}
            for t_i, (_w, d_mon, d_st, d_sp, d_key) in enumerate(targets):
                d_ally = {r[1].ability for r in targets if r[4] != d_key}
                f = {
                    **fld,
                    **screens[rival],
                    "friendguard": "friendguard" in d_ally,
                    "fairyaura": "fairyaura" in auras,
                    "darkaura": "darkaura" in auras,
                    **{k: k in ally for k in ALLY_BOOSTS},
                }
                for move in _usable_moves(a_mon, a_st):
                    m = dex.moves.get(move) or {}
                    if not m or m.get("category") == "Status":
                        continue
                    spread = (
                        m.get("target") in ("allAdjacent", "allAdjacentFoes")
                        and len(targets) == 2
                    )
                    req = damage_request(
                        a_mon,
                        a_st,
                        a_sp,
                        d_mon,
                        d_st,
                        d_sp,
                        move,
                        dex,
                        spread=spread,
                        field=f,
                    )
                    jobs.append((side, where, t_i, spread, move, a_key, req))
    answers = ctx.calc.run([x[-1] for x in jobs]) if jobs else []  # type: ignore[attr-defined]
    best: dict = {}  # (side, where, target) -> best share
    ko: dict = {}
    two: dict = {}
    spread_sum: dict = {}  # (side, attacker, move) -> total share
    for (side, where, t_i, spread, move, a_key, _r), ans in zip(jobs, answers):
        rolls = ans.get("rolls")
        if not rolls or "error" in ans or ans.get("unknown"):
            continue
        rival = "their" if side == "our" else "our"
        hp_now = active[rival][t_i][2]["hp"] * ans["max_hp"]
        share = min(1.0, (sum(rolls) / len(rolls)) / hp_now) if hp_now > 0 else 1.0
        k = (side, where, t_i)
        best[k] = max(best.get(k, 0.0), share)
        p_ko = sum(1 for r in rolls if r >= hp_now) / len(rolls)
        ko[k] = max(ko.get(k, 0.0), p_ko)
        two[k] = max(two.get(k, 0.0), _two_hits(rolls, hp_now))
        if spread:
            sk = (side, a_key, move)
            if where == "active":
                spread_sum[sk] = spread_sum.get(sk, 0.0) + share
    for side, rival in (("our", "their"), ("their", "our")):
        n = len(active[rival])
        act = [best.get((side, "active", i), 0.0) for i in range(n)]
        out[f"g_{side}_best_dmg"] = max(act, default=0.0)
        out[f"g_{side}_dmg_board"] = sum(act)
        out[f"g_{side}_ko_n"] = float(
            sum(ko.get((side, "active", i), 0.0) >= 0.5 for i in range(n))
        )
        out[f"g_{side}_2hko_n"] = float(
            sum(two.get((side, "active", i), 0.0) >= 0.5 for i in range(n))
        )
        out[f"g_{side}_spread_total"] = max(
            (v for (sd, _a, _m), v in spread_sum.items() if sd == side), default=0.0
        )
        out[f"g_{side}_bench_best"] = max(
            (best.get((side, "bench", i), 0.0) for i in range(n)), default=0.0
        )
        out[f"g_{side}_unseen_best"] = max(
            (best.get((side, "unseen", i), 0.0) for i in range(n)), default=0.0
        )
        out[f"g_{side}_unseen_ko_n"] = float(
            sum(ko.get((side, "unseen", i), 0.0) >= 0.5 for i in range(n))
        )
    return out


# --------------------------------------------------------------------------
# Week 8: this turn's options (H), the likely back (I), the whole board (J)
# --------------------------------------------------------------------------

_H_SIDE = (
    "fakeout_n",
    "locked_n",
    "protect_ready_n",
    "protect_risky_n",
    "mega_available",
    "mega_used",
)
_I_SIDE = (
    "back_entropy",
    "back_dmg_exp",
    "back_ko_exp",
    "back_speed_exp",
    "back_outspeeds_exp",
)
_J_SIDE = ("ko_targets_exp", "outko_targets_exp", "2hko_targets_exp", "outko_pairs_exp")


def _cols_h() -> list[str]:
    return [f"h_{s}_{k}" for s in SIDES for k in _H_SIDE]


def _cols_i() -> list[str]:
    return [f"i_{s}_{k}" for s in SIDES for k in _I_SIDE]


def _cols_j() -> list[str]:
    return [f"j_{s}_{k}" for s in SIDES for k in _J_SIDE]


def _usable_moves(mon: SheetMon, st: Mapping) -> tuple[str, ...]:
    """Its sheet moves, or only the locked one while a Choice item holds it."""
    from wpa.decisions import CHOICE_ITEMS

    locked = st.get("last_move") or ""
    if st.get("item") in CHOICE_ITEMS and locked in mon.moves:
        return (locked,)
    return mon.moves


def _has_own_stone(mon: SheetMon, dex: Dex) -> bool:
    stone = dex.items.get(mon.item, {}).get("megaStone") or {}
    if isinstance(stone, str):
        stone = {"": stone}
    return any(
        (not base or to_id(base) == mon.species) and to_id(mega) in dex.species
        for base, mega in stone.items()
    )


def _group_h(
    s: Mapping, role: str, sheets: Mapping[str, Sequence[SheetMon]], dex: Dex
) -> dict[str, float]:
    """For each side's active Pokemon: Fake Out still works, Choice-locked,
    Protect ready or risky (one that worked last turn); and the side's Mega
    Evolution still to use, or used."""
    from wpa.decisions import CHOICE_ITEMS, PROTECT_MOVES
    from wpa.team_sheets import match_to_state

    out = dict.fromkeys(_cols_h(), 0.0)
    other = "p2" if role == "p1" else "p1"
    for side, mons, r in (
        ("our", s["our_pokemon"], role),
        ("their", s["opp_pokemon"], other),
    ):
        sheet = sheets[r]
        used = any(p.get("mega") for p in mons)
        out[f"h_{side}_mega_used"] = float(used)
        for p, idx in zip(mons, match_to_state(sheet, mons)):
            if idx is None or p["fainted"]:
                continue
            m = sheet[idx]
            if not used and (p.get("item") or "") == m.item and _has_own_stone(m, dex):
                out[f"h_{side}_mega_available"] = 1.0
            if not p["active"]:
                continue
            moves = set(m.moves)
            if "fakeout" in moves and not p.get("moved"):
                out[f"h_{side}_fakeout_n"] += 1
            if p.get("item") in CHOICE_ITEMS and p.get("last_move"):
                out[f"h_{side}_locked_n"] += 1
            if moves & PROTECT_MOVES:
                key = (
                    "protect_risky_n" if p.get("protect_streak") else "protect_ready_n"
                )
                out[f"h_{side}_{key}"] += 1
    return out


def _speed_of(rows, dex: Dex, field: Mapping, tailwind: bool, ctx) -> dict:
    from wpa.spreads import speed_request

    reqs = [
        speed_request(m, st, sp, dex, field, tailwind) for _w, m, st, sp, _k in rows
    ]
    ans = ctx.calc.run(reqs) if reqs else []
    return {r[4]: float(a.get("speed", 0)) for r, a in zip(rows, ans)}


def _matchups(attackers, defenders, dex: Dex, field: Mapping, screens, ctx) -> dict:
    """(attacker key, defender key) -> (best share of the defender's current hit
    points, best chance to knock it out in one hit, in two hits); single target."""
    from wpa.spreads import damage_request

    jobs = []
    for _w, a_mon, a_st, a_sp, a_key in attackers:
        for _w2, d_mon, d_st, d_sp, d_key in defenders:
            for move in _usable_moves(a_mon, a_st):
                m = dex.moves.get(move) or {}
                if not m or m.get("category") == "Status":
                    continue
                req = damage_request(
                    a_mon,
                    a_st,
                    a_sp,
                    d_mon,
                    d_st,
                    d_sp,
                    move,
                    dex,
                    field={**field, **screens},
                )
                jobs.append((a_key, d_key, d_st["hp"], req))
    answers = ctx.calc.run([j[-1] for j in jobs]) if jobs else []
    out: dict = {}
    for (a_key, d_key, hp, _r), ans in zip(jobs, answers):
        rolls = ans.get("rolls")
        if not rolls or "error" in ans or ans.get("unknown"):
            continue
        hp_now = hp * ans["max_hp"]
        share = min(1.0, (sum(rolls) / len(rolls)) / hp_now) if hp_now > 0 else 1.0
        ko = sum(1 for r in rolls if r >= hp_now) / len(rolls)
        two = _two_hits(rolls, hp_now)
        b = out.get((a_key, d_key), (0.0, 0.0, 0.0))
        out[(a_key, d_key)] = (max(b[0], share), max(b[1], ko), max(b[2], two))
    return out


def _side_setup(s, role, joined, sheets, dex, ctx):
    from wpa.bring import marginals, set_chances
    from wpa.team_sheets import match_to_state

    other = "p2" if role == "p1" else "p1"
    j = joined or JoinedTimers()
    info = {}
    for side, mons, r in (
        ("our", s["our_pokemon"], role),
        ("their", s["opp_pokemon"], other),
    ):
        sheet = sheets[r]
        revealed = {
            idx
            for p, idx in zip(mons, match_to_state(sheet, mons))
            if idx is not None and (p["active"] or p["fainted"] or p["hp_fraction"] > 0)
        }
        odds = list((ctx.odds or {}).get(r) or [1.0] * len(sheet))
        if len(odds) != len(sheet):
            odds = [1.0] * len(sheet)
        info[side] = {
            "role": r,
            "rows": _roster(mons, sheet, r, dex, ctx),
            "sets": set_chances(odds, revealed),
            "p": marginals(odds, revealed),
            "tailwind": any(
                e == "tailwind" and lo > 0
                for e, _t, lo, _h in (j.ours if side == "our" else j.theirs)
            ),
            "screens": _screens(j.ours if side == "our" else j.theirs),
        }
    tr = any(e == "trickroom" and lo > 0 for e, _t, lo, _h in j.field)
    return info, _field(j), tr


def _group_i(s, role, joined, sheets, dex, ctx) -> dict[str, float]:
    """Each side's likely back (`wpa.bring`): how uncertain it is, and what it
    brings against the other side's active Pokemon, as expectations over the sets
    of four still possible."""
    out = dict.fromkeys(_cols_i(), 0.0)
    if ctx is None:
        return out
    info, fld, tr = _side_setup(s, role, joined, sheets, dex, ctx)
    for side, rival in (("our", "their"), ("their", "our")):
        me, you = info[side], info[rival]
        sets = me["sets"]
        out[f"i_{side}_back_entropy"] = -sum(
            p * math.log(p) for p in sets.values() if p > 0
        )
        unseen = [r for r in me["rows"] if r[0] == "unseen"]
        targets = [r for r in you["rows"] if r[0] == "active"]
        if not unseen or not sets:
            continue
        mu = _matchups(unseen, targets, dex, fld, you["screens"], ctx)
        spd = _speed_of(unseen, dex, fld, me["tailwind"], ctx)
        rival_spd = _speed_of(targets, dex, fld, you["tailwind"], ctx)
        fastest = (min if tr else max)(rival_spd.values(), default=None)
        per = {}
        for r in unseen:
            k = r[4]
            dm = max((mu.get((k, t[4]), (0, 0, 0))[0] for t in targets), default=0.0)
            kos = {t[4] for t in targets if mu.get((k, t[4]), (0, 0, 0))[1] >= 0.5}
            out_ = fastest is not None and (
                spd[k] < fastest if tr else spd[k] > fastest
            )
            per[k[1]] = (dm, kos, spd[k], float(out_))
        for members, p in sets.items():
            here = [per[i] for i in members if i in per]
            if not here:
                continue
            out[f"i_{side}_back_dmg_exp"] += p * max(x[0] for x in here)
            out[f"i_{side}_back_ko_exp"] += p * len(set().union(*(x[1] for x in here)))
            out[f"i_{side}_back_speed_exp"] += p * max(x[2] for x in here)
            out[f"i_{side}_back_outspeeds_exp"] += p * sum(x[3] for x in here)
    return out


def _group_j(s, role, joined, sheets, dex, ctx) -> dict[str, float]:
    """Damage across the whole board: every Pokemon still standing on each side
    (an unseen one counted by the chance it was brought) against every one on
    the other: knock-outs in one hit, in two, and while moving first."""
    out = dict.fromkeys(_cols_j(), 0.0)
    if ctx is None:
        return out
    info, fld, tr = _side_setup(s, role, joined, sheets, dex, ctx)
    speeds = {
        side: _speed_of(info[side]["rows"], dex, fld, info[side]["tailwind"], ctx)
        for side in info
    }
    for side, rival in (("our", "their"), ("their", "our")):
        me, you = info[side], info[rival]
        if not me["rows"] or not you["rows"]:
            continue
        mu = _matchups(me["rows"], you["rows"], dex, fld, you["screens"], ctx)
        w = {r[4]: me["p"][r[4][1]] for r in me["rows"]}
        wd = {r[4]: you["p"][r[4][1]] for r in you["rows"]}
        for d in you["rows"]:
            dk = d[4]
            miss_ko = miss_out = miss_two = 1.0
            for a in me["rows"]:
                ak = a[4]
                _share, ko, two = mu.get((ak, dk), (0.0, 0.0, 0.0))
                first = (
                    speeds[side][ak] < speeds[rival][dk]
                    if tr
                    else speeds[side][ak] > speeds[rival][dk]
                )
                miss_ko *= 1 - w[ak] * (ko >= 0.5)
                miss_two *= 1 - w[ak] * (two >= 0.5)
                miss_out *= 1 - w[ak] * (ko >= 0.5 and first)
                out[f"j_{side}_outko_pairs_exp"] += (
                    w[ak] * wd[dk] * (ko >= 0.5 and first)
                )
            out[f"j_{side}_ko_targets_exp"] += wd[dk] * (1 - miss_ko)
            out[f"j_{side}_2hko_targets_exp"] += wd[dk] * (1 - miss_two)
            out[f"j_{side}_outko_targets_exp"] += wd[dk] * (1 - miss_out)
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
    ctx: DamageContext | None = None,
) -> dict[str, float]:
    """Features for the decision at states[k], from states[: k + 1] only.
    `ctx` (the calculator and the spreads at this decision) turns on real Speed
    in group F and the damage of group G; without it G is all zero."""
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
    if "F" in groups:
        row.update(_group_f(s, role, joined, sheets, dex, ctx))
    if "G" in groups:
        row.update(_group_g(s, role, joined, sheets, dex, ctx))
    if "H" in groups:
        row.update(_group_h(s, role, sheets, dex))
    if "I" in groups:
        row.update(_group_i(s, role, joined, sheets, dex, ctx))
    if "J" in groups:
        row.update(_group_j(s, role, joined, sheets, dex, ctx))
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
    contexts: Sequence[DamageContext | None] | None = None,
) -> list[Row]:
    """One row per decision of one state file (the terminal state is the label).
    `contexts`: a damage context per state, for real Speed and group G."""
    label = states[-1]["outcome"]
    if label is None:
        return []
    unit = states[0].get("set_id") or tag
    cols = columns(groups)
    out = []
    for k in decision_indices(states):
        ctx = contexts[k] if contexts is not None else None
        f = state_features(states, k, role, joined[k], sheets, dex, table, groups, ctx)
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


# --------------------------------------------------------------------------
# Week 8 Task 5: the opponent's sheet blanked
# --------------------------------------------------------------------------

_HIDDEN = SheetMon(0, "", "", "", (), "")


def _revealed(p: Mapping) -> bool:
    return bool(p["active"] or p["fainted"] or p["hp_fraction"] > 0)


def public_sheet(sheet: Sequence[SheetMon], side: Sequence[Mapping]) -> tuple:
    """The opponent's sheet as the log has shown it so far: a Pokemon's species
    once it has appeared, and only the moves, item and ability revealed; no
    sheet order and no nature. Unseen ones are blank."""
    out = []
    for mon, p in zip(sheet, side):
        if not _revealed(p):
            out.append(_HIDDEN)
            continue
        out.append(
            SheetMon(
                0,
                mon.species,
                p.get("rev_item") or "",
                p.get("rev_ability") or "",
                tuple(p.get("rev_moves") or ()),
                "",
            )
        )
    return tuple(out)


def _blank_side(side: Sequence[Mapping]) -> list[dict]:
    out = []
    for p in side:
        q = dict(p)
        if not _revealed(p):
            q.update(species="", item="")
        elif not (p.get("item") and p.get("item") == p.get("rev_item")):
            q["item"] = ""
        out.append(q)
    return out


def blank_state(s: Mapping, both: bool = False) -> dict:
    """The board with the opponent's unseen species hidden, and any item of theirs
    the log has not shown (or that is gone) left out. `both`: our side too, as a
    spectator sees it."""
    out = {**s, "opp_pokemon": _blank_side(s["opp_pokemon"])}
    if both:
        out["our_pokemon"] = _blank_side(s["our_pokemon"])
    return out


def rows_for_file_blank(
    tag: str,
    role: str,
    states: Sequence[dict],
    joined: Sequence[JoinedTimers | None],
    sheets: Mapping[str, Sequence[SheetMon]],
    dex: Dex,
    table: Durations | None,
    groups: str,
    context_for=None,
    both: bool = False,
) -> list[Row]:
    """Like `rows_for_file`, with the opponent's sheet blanked at every decision
    (`public_sheet`, `blank_state`). `context_for(k, sheets)` gives the damage
    context for decision k from the sheets as they stand then. `both`: our sheet
    blanked too (a spectator's view), so both sides know the same kind of thing
    and a row's mirror looks like a real row."""
    label = states[-1]["outcome"]
    if label is None:
        return []
    other = "p2" if role == "p1" else "p1"
    unit = states[0].get("set_id") or tag
    cols = columns(groups)
    out = []
    for k in decision_indices(states):
        public = {
            role: public_sheet(sheets[role], states[k]["our_pokemon"])
            if both
            else sheets[role],
            other: public_sheet(sheets[other], states[k]["opp_pokemon"]),
        }
        board = [*states[:k], blank_state(states[k], both)]
        ctx = context_for(k, public) if context_for is not None else None
        f = state_features(board, k, role, joined[k], public, dex, table, groups, ctx)
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


# --------------------------------------------------------------------------
# Building from our own decision table (Week 6)
# --------------------------------------------------------------------------


def unit_of(tag: str, log: str) -> tuple[str, int]:
    """(set id, game number) for a Bo3 game; (its own tag, 1) for a single game."""
    from wpa.decisions import _BESTOF

    m = _BESTOF.search(log)
    return (m.group(2), int(m.group(1))) if m else (tag, 1)


def split_logs_into_shards(
    games: Iterable[tuple[str, str]],
    splits: Mapping[str, str],
    out_dir: Path,
    shards: int,
) -> dict[str, int]:
    """Write the logs of games that have a split into `shards` files by set (a Bo3
    set's games together, in game order), so each shard can be built on its own
    without reading every log again, and a set's later games can use its earlier
    ones."""
    import gzip

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"part-{i:03d}.jsonl.gz" for i in range(shards)]
    files = [gzip.open(p, "wt", encoding="utf-8") for p in paths]
    counts = {"games": 0, "unassigned": 0}
    try:
        for tag, log in games:
            if tag not in splits:
                counts["unassigned"] += 1
                continue
            unit, _ = unit_of(tag, log)
            files[shard_of(unit, shards)].write(
                json.dumps({"tag": tag, "log": log}) + "\n"
            )
            counts["games"] += 1
    finally:
        for f in files:
            f.close()
    for p in paths:  # each set's games in order, sets in order of first game
        with gzip.open(p, "rt", encoding="utf-8") as f:
            lines = f.readlines()
        keyed = []
        first: dict[str, int] = {}
        for i, line in enumerate(lines):
            d = json.loads(line)
            unit, game = unit_of(d["tag"], d["log"])
            first.setdefault(unit, i)
            keyed.append((first[unit], game, i, line))
        keyed.sort()
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.writelines(x[3] for x in keyed)
    return counts


def build_shard_from_logs(
    shard: int,
    shards: int,
    *,
    logs_dir: Path,
    splits: Mapping[str, str],
    dexes: Mapping[str, Dex],
    tables: Mapping[str, Durations],
    out_dir: Path,
    groups: str = "ABCDEF",
    usage_dir: Path | None = None,
    train_sample: float = 1.0,
    formats: Sequence[str] | None = None,
    bring_path: Path | None = None,
    blank: bool = False,
    blank_both: bool = False,
) -> dict[str, float]:
    """One shard of games, from our decision table (`wpa.decisions`). With
    `usage_dir` (Smogon usage statistics), each decision gets a damage context:
    real Speed in group F and the damage of group G. `train_sample` keeps that
    fraction of Reg M-A's training units (sets), the ones `wpa.evaluate --sample`
    would; Reg M-B's training games stay whole, as the pooled model uses them all.
    `formats`: build only these formats. `bring_path`: the bring model
    (`wpa.bring`), for groups I and J and a Bo3 set's memory of what each player
    brought; the logs must then be sharded by set (`logs_sets/`). `blank`: the
    opponent's sheet blanked at every decision (`rows_for_file_blank`), spreads
    from the statistics alone, no Bo3 memory. `blank_both`: both sheets blanked
    (a spectator's view)."""
    import gzip
    import time

    from wpa.decisions import _set_fields, build_game
    from wpa.formats import format_of
    from wpa.team_sheets import sheets_from_log

    cols = columns(groups)
    rows: dict[tuple[str, str], list[Row]] = {}
    counts: dict[str, float] = {"games": 0, "rows": 0, "no_result": 0}
    calc = store = None
    calls_before = 0
    if usage_dir is not None:
        calc, store = _worker_tools(usage_dir)
        calls_before = calc.calls  # type: ignore[attr-defined]
    bring = None
    if bring_path is not None:
        from wpa.bring import BringModel

        if _WORKER.get("bring_path") != str(bring_path):
            _WORKER.update(
                bring=BringModel.load(bring_path), bring_path=str(bring_path)
            )
        bring = _WORKER["bring"]
    memory: dict = {}  # a Bo3 set's memory, kept while its games come in order
    stats: dict = {}
    start = time.time()
    with gzip.open(
        logs_dir / f"part-{shard:03d}.jsonl.gz", "rt", encoding="utf-8"
    ) as f:
        for line in f:
            d = json.loads(line)
            tag, log = d["tag"], d["log"]
            fmt = format_of(tag)
            table = tables[fmt]
            if formats is not None and fmt not in formats:
                continue
            if train_sample < 1.0 and fmt == "regma" and splits.get(tag) == "train":
                unit = _set_fields(log, "p1")[0] or tag
                if not keep_unit(unit, train_sample):
                    counts["left_out"] = counts.get("left_out", 0) + 1
                    continue
            game = build_game(log, table)
            sheets = sheets_from_log(log)
            counts["games"] += 1
            contexts = None
            if blank or blank_both:
                for role in ("p1", "p2"):
                    states = game.states[role]
                    if states[-1]["outcome"] is None:
                        counts["no_result"] += 1
                        continue
                    got = rows_for_file_blank(
                        tag,
                        role,
                        states,
                        game.joined[role],
                        sheets,
                        dexes[fmt],
                        table,
                        groups,
                        _blank_contexts(
                            tag,
                            log,
                            role,
                            sheets,
                            dexes[fmt],
                            calc,
                            store,
                            bring,
                            blank_both,
                        )
                        if calc is not None and len(sheets) == 2
                        else None,
                        blank_both,
                    )
                    rows.setdefault((fmt, splits[tag]), []).extend(got)
                    counts["rows"] += len(got)
                continue
            if calc is not None and len(sheets) == 2:
                contexts = damage_contexts(
                    tag,
                    log,
                    game,
                    sheets,
                    dexes[fmt],
                    calc,
                    store,
                    bring,
                    memory if bring is not None else None,
                    stats,
                )
            for role in ("p1", "p2"):
                states = game.states[role]
                if states[-1]["outcome"] is None:
                    counts["no_result"] += 1
                    continue
                got = rows_for_file(
                    tag,
                    role,
                    states,
                    game.joined[role],
                    sheets,
                    dexes[fmt],
                    table,
                    groups,
                    contexts[role] if contexts else None,
                )
                rows.setdefault((fmt, splits[tag]), []).extend(got)
                counts["rows"] += len(got)
    if calc is not None:
        # sent to the calculator for this shard (the rest came from the cache)
        counts["calculations"] = calc.calls - calls_before  # type: ignore[attr-defined]
    counts["seconds"] = round(time.time() - start)
    for k, v in stats.items():
        counts[k] = round(v, 3) if isinstance(v, float) else v
    for (fmt, split), rs in rows.items():
        d = out_dir / fmt / split
        d.mkdir(parents=True, exist_ok=True)
        write_rows(d / f"part-{shard:03d}-of-{shards:03d}.npz", rs, cols)
    return counts


def keep_unit(unit: str, fraction: float, seed: str = "wpa-sample") -> bool:
    """The same choice `wpa.evaluate.sample_units` makes for one unit."""
    h = int.from_bytes(hashlib.sha256(f"{seed}|{unit}".encode()).digest()[:4], "big")
    return h / 2**32 < fraction


_WORKER: dict = {}
CACHE_CAP = 300_000  # answers kept per worker process (about 0.5 GB)


def _worker_tools(usage_dir: Path):
    """One calculator and usage store per process, kept across shards so the
    calculator's cache carries over; the cache is emptied when it gets large."""
    from wpa.damage import Calc
    from wpa.spreads import UsageStore

    if _WORKER.get("usage") != str(usage_dir):
        if "calc" in _WORKER:
            _WORKER["calc"].close()
        _WORKER.update(calc=Calc(), store=UsageStore(usage_dir), usage=str(usage_dir))
    calc = _WORKER["calc"]
    if len(calc.cache) > CACHE_CAP:
        calc.cache.clear()
    return calc, _WORKER["store"]


def damage_contexts(
    tag, log, game, sheets, dex, calc, store, bring=None, memory=None, stats=None
) -> dict[str, list]:
    """A damage context for every decision of one game: each Pokemon's most
    likely spread from the usage statistics, refined by the hits and move
    orders the log shows before the decision's block (`wpa.spreads`).

    `bring` (`wpa.bring.BringModel`) adds each side's odds that each sheet
    Pokemon was brought. `memory` is a Bo3 set's memory (a dict kept across the
    set's games, which come in order): a later game starts each player's spreads
    where the set's previous game left them, and counts what the player brought
    then. `stats` collects how much narrower the carried spreads are."""
    from wpa.bring import brought_from_log, players
    from wpa.formats import format_of
    from wpa.spreads import Spread, events_from_log, priors_for, refine

    priors = priors_for(sheets, store.for_game(tag, log), dex)
    unit, _ = unit_of(tag, log)
    names = players(log)
    prev: dict[str, frozenset[int]] = {}
    if memory is not None:
        for role, mons in sheets.items():
            mem = memory.get((unit, names.get(role, role)))
            if not mem:
                continue
            for i, mon in enumerate(mons):
                kept = mem["spreads"].get(mon.species)
                if not kept:
                    continue
                if stats is not None:
                    stats["carried"] = stats.get("carried", 0) + 1
                    stats["entropy_start"] = stats.get("entropy_start", 0.0) + _entropy(
                        [c.weight for c in priors.get((role, i)) or ()]
                    )
                    stats["entropy_carried"] = stats.get(
                        "entropy_carried", 0.0
                    ) + _entropy([c.weight for c in kept])
                priors[(role, i)] = kept
            prev[role] = frozenset(
                i for i, m in enumerate(mons) if m.species in mem["brought"]
            )
    hits, orders = events_from_log(log, dex)
    final: dict = {}
    beliefs, _ = refine([*hits, *orders], sheets, dex, priors, calc, beliefs_out=final)
    odds = None
    if bring is not None:
        fmt = format_of(tag)
        odds = {
            role: bring.odds(fmt, tuple(m.species for m in mons), prev.get(role))
            for role, mons in sheets.items()
        }
    if memory is not None:
        got = brought_from_log(log)
        for role, mons in sheets.items():
            memory[(unit, names.get(role, role))] = {
                "spreads": {
                    mons[i].species: [
                        Spread(c.nature, c.sps, w)
                        for c, w in zip(b.candidates, b.weights)
                    ]
                    for (r, i), b in final.items()
                    if r == role
                },
                "brought": {mons[i].species for i in got.get(role, set())},
            }
    return {
        role: [
            DamageContext(calc, beliefs.at(point), odds) for point in game.points[role]
        ]
        for role in game.points
    }


def _blank_contexts(tag, log, role, sheets, dex, calc, store, bring, both=False):
    """For the blanked run: spreads from the statistics alone (no refining), for
    the sheets as they stand at each decision; bring odds for our own side only,
    and none when `both` sheets are blanked."""
    from wpa.formats import format_of
    from wpa.spreads import Belief, priors_for

    usage = store.for_game(tag, log)
    odds = None
    if bring is not None and not both:
        own = tuple(m.species for m in sheets[role])
        odds = {role: bring.odds(format_of(tag), own, None)}
    cache: dict = {}

    def context_for(_k, public):
        key = tuple(public[r] for r in sorted(public))
        if key not in cache:
            pri = priors_for(public, usage, dex)
            cache[key] = DamageContext(
                calc, {k: Belief(v).best() for k, v in pri.items() if v}, odds
            )
        return cache[key]

    return context_for


def _entropy(weights) -> float:
    s = sum(weights)
    return -sum(w / s * math.log(w / s) for w in weights if w > 0) if s > 0 else 0.0


def _build_one(args: tuple) -> dict[str, float]:
    shard, shards, opts = args
    from wpa.durations import load_all
    from wpa.team_sheets import load_dexes

    dexes = load_dexes(opts["showdown"])
    tables = load_all(opts["showdown"])
    splits = json.loads(Path(opts["splits"]).read_text(encoding="utf-8"))["games"]
    if opts.get("from_logs"):
        return build_shard_from_logs(
            shard,
            shards,
            logs_dir=Path(opts["from_logs"]),
            splits=splits,
            dexes=dexes,
            tables=tables,
            out_dir=Path(opts["out"]),
            groups=opts.get("groups") or "ABCDEF",
            usage_dir=Path(opts["usage"]) if opts.get("usage") else None,
            train_sample=opts.get("train_sample") or 1.0,
            formats=opts.get("formats"),
            bring_path=Path(opts["bring"]) if opts.get("bring") else None,
            blank=bool(opts.get("blank")),
            blank_both=bool(opts.get("blank_both")),
        )
    return build_shard(  # type: ignore[return-value]
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
    p.add_argument(
        "--split-logs",
        type=str,
        help="write the logs into shard files in this folder, then stop",
    )
    p.add_argument("--logs", default="battle_logs")
    p.add_argument(
        "--from-logs",
        type=str,
        help="build from our decision table, reading shard files from here",
    )
    p.add_argument("--groups", default="")
    p.add_argument(
        "--usage",
        type=str,
        help="with --from-logs: Smogon usage statistics folder; turns on real "
        "Speed and the damage features (group G)",
    )
    p.add_argument(
        "--train-sample",
        type=float,
        default=1.0,
        help="with --from-logs: keep this fraction of Reg M-A's training sets "
        "(the ones `wpa.evaluate --sample` keeps); everything else stays whole",
    )
    p.add_argument(
        "--formats",
        nargs="+",
        help="with --from-logs: build only these formats (regma, regmb)",
    )
    p.add_argument(
        "--bring",
        type=str,
        help="with --usage: the bring model (models_v4/bring.json) for groups I "
        "and J and Bo3 memory; read the logs from logs_sets",
    )
    p.add_argument(
        "--blank",
        action="store_true",
        help="with --from-logs: the opponent's sheet blanked (Week 8 Task 5)",
    )
    p.add_argument(
        "--blank-both",
        action="store_true",
        help="with --from-logs: both sheets blanked, as a spectator sees the game",
    )
    a = p.parse_args()
    if a.split_logs:
        from wpa.timers import iter_log_file

        splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]

        def games() -> Iterable[tuple[str, str]]:
            for path in sorted(Path(a.logs).glob("logs_*.json")):
                for tag, (_ts, log) in iter_log_file(path):
                    yield tag, log

        print(split_logs_into_shards(games(), splits, Path(a.split_logs), a.shards))
        return
    opts = vars(a)
    wanted = range(a.shards)
    if a.only:
        lo, _, hi = a.only.partition("-")
        wanted = range(int(lo), int(hi or lo) + 1)
    total: dict[str, float] = {}
    jobs = [(s, a.shards, opts) for s in wanted]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for s, counts in zip(wanted, pool.map(_build_one, jobs)):
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            print(f"shard {s}: {counts}", flush=True)
    print(f"total: {total}")


if __name__ == "__main__":
    main()
