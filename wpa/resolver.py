"""What can happen this turn (Week 9 Task 2, the plan's M3).

Given a board at the start of a turn, both sides' choices (`wpa.choices.Action`)
and each Pokemon's spread, `Resolver.resolve` lists every board the turn can end
on, each with its chance. Every random event in DEFINITIONS §8 is its own
branch: each of the 16 damage rolls, critical hits, accuracy, secondary effects,
Speed ties, multi-hit counts, Protect's success chance, full paralysis, thawing.
Two rolls that leave different hit points give different boards; boards are only
merged when they are identical (plan §5, the damage roll trap). An optional
`resolution` merges hit points to a grid, for callers that only need
expectations (Task 4); the default keeps them exact.

The order of a turn:
1. switches, faster first, with Intimidate and weather or terrain on entry;
2. Mega Evolution (its ability takes effect, and Speed is the Mega's);
3. moves, by priority (Prankster, Gale Wings and Triage included), then Speed
   (Trick Room reverses it; ties are 50/50), as fixed at the start of the turn;
4. the end of the turn: sandstorm, Grassy Terrain, Leftovers, Black Sludge, burn
   and poison, Speed Boost, then every timer counts down by one.

What the board cannot hold, or the resolver does not model, is never ignored
silently: the outcome carries a reason in `partial` (an unmodelled move or
ability, sleep turns, confusion, a charging or semi-invulnerable move, a choice
of switch-in after U-turn, assumed to be any bench Pokemon alike). Speed is fixed
for the turn, so a Speed drop takes effect from the next turn.
"""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import permutations, product
from pathlib import Path

from wpa.choices import Action
from wpa.decisions import PROTECT_MOVES, STATS, to_id
from wpa.spreads import Spread, damage_request, default_spread, speed_request
from wpa.team_sheets import Dex, SheetMon, form_of

ROLES = ("p1", "p2")
PROTECT_LIKE = PROTECT_MOVES | {"wideguard", "quickguard", "endure"}
SCREENS = {"reflect": 5, "lightscreen": 5, "auroraveil": 5}
SIDE_TIMED = {"tailwind": 4, **SCREENS, "safeguard": 5, "mist": 5}
# abilities that stop the other side's priority moves aimed at their side
QUEENLY = {"armortail", "dazzling", "queenlymajesty"}
# move targets that are not aimed at a Pokemon of the other side
NOT_AIMED = {
    "self",
    "allySide",
    "foeSide",
    "all",
    "allies",
    "allyTeam",
    "adjacentAlly",
    "adjacentAllyOrSelf",
}
# single-target moves, which Lightning Rod and Storm Drain can draw
SINGLE = {"normal", "any", "adjacentFoe", "randomNormal"}
RODS = {"Electric": "lightningrod", "Water": "stormdrain"}
WEATHER_ROCKS = {
    "sunnyday": "heatrock",
    "raindance": "damprock",
    "sandstorm": "smoothrock",
    "snowscape": "icyrock",
}
WEATHER_ABILITIES = {
    "drought": "sunnyday",
    "drizzle": "raindance",
    "sandstream": "sandstorm",
    "snowwarning": "snowscape",
    "orichalcumpulse": "sunnyday",
}
TERRAIN_ABILITIES = {
    "electricsurge": "electricterrain",
    "psychicsurge": "psychicterrain",
    "grassysurge": "grassyterrain",
    "mistysurge": "mistyterrain",
    "hadronengine": "electricterrain",
}
INTIMIDATE_BLOCK = {
    "clearbody",
    "hypercutter",
    "whitesmoke",
    "fullmetalbody",
    "innerfocus",
    "oblivious",
    "owntempo",
    "scrappy",
}
DROP_BLOCK = {"clearbody", "whitesmoke", "fullmetalbody"}
CRIT_IMMUNE = {"battlearmor", "shellarmor"}
# Week 11 Task 3: the Champions rules (`data/mods/champions/conditions.ts`)
PARALYSED = 1 / 8  # the chance a paralysed Pokemon cannot move
SLEEP_WAKE = {1: 0.0, 2: 1 / 3}  # waking on the n-th try (third and later: sure)
CONFUSED_HIT = 0.33  # Showdown's randomChance(33, 100)
LEAVING = (
    "confused",
    "charging",
    "encore",
    "hits",
    "tox_n",
    "seeded",
    "taunt",
    "drowsy",
    "disabled",
    "types",
    "typeadd",
    "protean",
    "roost",
)
# what each status-move effect after Week 11 checks on its target
TAUNT_BLOCK = {"oblivious", "aromaveil"}
SLEEPLESS = {"insomnia", "vitalspirit", "sweetveil", "comatose", "purifyingsalt"}
# abilities that act by chance when hit with contact (not modelled: marked)
CONTACT_CHANCE = {"flamebody", "static", "poisonpoint", "effectspore", "cutecharm"}
# healing by the weather (Moonlight and the like; Shore Up in sand)
WEATHER_HEAL = {"moonlight", "morningsun", "synthesis"}
# status moves with a target, done in `_use`'s loop (after Week 11)
ON_TARGET = {"healpulse", "floralhealing", "psychup", "strengthsap"}
# Week 12 Task 2: type changes. Protean and Libero (once per switch-in);
# the status moves that change a target's types; the moves that cost their
# user a type (it fails without it)
PROTEAN = {"protean", "libero"}
RETYPE = {"soak", "trickortreat", "forestscurse", "reflecttype"}
LOSES_TYPE = {"burnup": "Fire", "doubleshock": "Electric"}
# abilities that ignore the target's ability (here: Good as Gold)
MOLD = {"moldbreaker", "teravolt", "turboblaze"}
# targets a single foe: an overridden move (Encore) picks one at random
ONE_FOE = {"normal", "any", "adjacentFoe", "randomNormal"}
OUT_OF_REACH = {"fly", "bounce", "dig", "dive", "phantomforce", "shadowforce"}
REACHES = {  # moves that still hit it there (not modelled: marked)
    "fly": {"gust", "twister", "thunder", "hurricane", "skyuppercut", "smackdown"},
    "bounce": {"gust", "twister", "thunder", "hurricane", "skyuppercut", "smackdown"},
    "dig": {"earthquake", "magnitude", "fissure"},
    "dive": {"surf", "whirlpool"},
}
FLINCH_IMMUNE = {"innerfocus", "shielddust"}
STATUS_TYPE_IMMUNE = {
    "brn": {"Fire"},
    "par": {"Electric"},
    "psn": {"Poison", "Steel"},
    "tox": {"Poison", "Steel"},
    "frz": {"Ice"},
}
MULTIHIT_2_5 = ((2, 0.35), (3, 0.35), (4, 0.15), (5, 0.15))


@lru_cache(maxsize=4)
def load_moves(showdown: Path | str, mod: str) -> dict:
    """The move facts the resolver needs, from the pinned Showdown build."""
    script = Path(__file__).resolve().parent.parent / "scripts" / "dump_moves.js"
    out = subprocess.run(
        ["node", str(script), str(showdown), mod],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return json.loads(out)["moves"]


def load_moves_file(path: Path | str) -> dict:
    """The same facts from a saved dump (`node scripts/dump_moves.js ... > FILE`)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["moves"]


@dataclass
class Field:
    """Weather, terrain, Trick Room and side conditions, with turns left. A turn
    left of n means the effect is in force this turn and n - 1 more."""

    weather: str = ""
    weather_left: int = 0
    terrain: str = ""
    terrain_left: int = 0
    trickroom: int = 0
    sides: dict[str, dict[str, int]] = field(
        default_factory=lambda: {"p1": {}, "p2": {}}
    )

    def key(self) -> tuple:
        return (
            self.weather,
            self.weather_left,
            self.terrain,
            self.terrain_left,
            self.trickroom,
            tuple(tuple(sorted(self.sides[r].items())) for r in ROLES),
        )


def field_from_timers(joined, role: str) -> Field:
    """A Field from a decision's timers (`wpa.timer_join.JoinedTimers`)."""
    from wpa.damage import TERRAIN, WEATHER

    other = "p2" if role == "p1" else "p1"
    f = Field()
    if joined is None:
        return f
    for eid, _t, lo, _hi in joined.field:
        if eid in WEATHER:
            f.weather, f.weather_left = eid, lo
        elif eid in TERRAIN:
            f.terrain, f.terrain_left = eid, lo
        elif eid == "trickroom":
            f.trickroom = lo
    for r, spans in ((role, joined.ours), (other, joined.theirs)):
        for eid, target, lo, _hi in spans:
            if target == "side" and eid in SIDE_TIMED:
                f.sides[r][eid] = lo
    return f


@dataclass
class Outcome:
    prob: float
    sides: dict[str, list[dict]]
    field: Field
    partial: frozenset[str] = frozenset()
    # set when the turn ended the game before the board says so (Perish Song)
    winner: str | None = None


def _staged(stat: int, stage: int) -> int:
    """A stat at a stage, as Showdown's calculateStat."""
    table = (1, 1.5, 2, 2.5, 3, 3.5, 4)
    stage = max(-6, min(6, stage))
    return int(stat * table[stage]) if stage >= 0 else int(stat / table[-stage])


@dataclass
class _World:
    p: float
    sides: dict[str, list[dict]]
    fld: Field
    partial: set[str]
    # this turn only
    protected: set = field(default_factory=set)
    guards: set = field(default_factory=set)  # (role, "wideguard"|"quickguard")
    flinched: set = field(default_factory=set)
    acted: set = field(default_factory=set)
    # a side's redirector (Follow Me, Rage Powder): side -> (role, idx, move)
    redirect: dict = field(default_factory=dict)
    helped: set = field(default_factory=set)
    replaced: dict = field(default_factory=dict)  # (role, idx) -> (role, idx)
    # this action only: targets hit, damage dealt by the user
    hit: set = field(default_factory=set)
    dealt: int = 0
    subbed: set = field(default_factory=set)  # targets whose substitute took it
    winner: str | None = None  # the game ended this turn (Perish Song's order)
    # this action only: a Pokemon Encore just changed the move of, before it
    # moved (its place in the order is then found again: `_requeued`)
    requeue: tuple[str, int] | None = None

    def clone(self, p: float | None = None) -> _World:
        f = self.fld
        return _World(
            self.p if p is None else p,
            {
                r: [dict(m, boosts=dict(m["boosts"])) for m in ms]
                for r, ms in self.sides.items()
            },
            Field(
                f.weather,
                f.weather_left,
                f.terrain,
                f.terrain_left,
                f.trickroom,
                {r: dict(v) for r, v in f.sides.items()},
            ),
            set(self.partial),
            set(self.protected),
            set(self.guards),
            set(self.flinched),
            set(self.acted),
            dict(self.redirect),
            set(self.helped),
            dict(self.replaced),
            set(self.hit),
            self.dealt,
            set(self.subbed),
            self.winner,
            self.requeue,
        )

    def key(self, resolution: float | None, coarsen: int = 0) -> tuple:
        """The board's identity, hit points on the `resolution` grid. `coarsen`
        k > 0 is the cap's grid: 2**k whole cells of the base grid (the
        resolution, or 0.01) per cell, so each grid nests in the next."""
        base = resolution or 0.01

        def hp(x: float) -> float:
            if coarsen:
                return round(x / base) >> coarsen
            return round(x / resolution) * resolution if resolution else round(x, 12)

        mons = tuple(
            (
                hp(m["hp_fraction"]),
                m["fainted"],
                m["active"],
                m["status"],
                tuple(sorted(m["boosts"].items())),
                m["item"],
                m["mega"],
                m["moved"],
                m["last_move"],
                m["protect_streak"],
                m.get("perish", 0),
                m.get("sub", 0),
                m.get("confused", -1),
                m.get("charging", ""),
                m.get("encore", ""),
                m.get("slp_n", 0),
                m.get("frz_n", 0),
                m.get("tox_n", 0),
                m.get("seeded", -2),
                m.get("taunt", 0),
                m.get("drowsy", -1),
                m.get("disabled", ""),
                tuple(m.get("types") or ()),
                m.get("typeadd", ""),
                m.get("protean", 0),
                m.get("roost", 0),
            )
            for r in ROLES
            for m in self.sides[r]
        )
        return (
            mons,
            self.fld.key(),
            tuple(sorted(self.partial)),
            tuple(sorted(self.protected)),
            tuple(sorted(self.guards)),
            tuple(sorted(self.flinched)),
            tuple(sorted(self.acted)),
            tuple(sorted(self.redirect.items())),
            tuple(sorted(self.helped)),
            tuple(sorted(self.replaced.items())),
            tuple(sorted(self.hit)),
            self.winner or "",
            self.dealt,
        )


def _merge(
    worlds: Sequence[_World],
    resolution: float | None,
    prune: float = 0.0,
    coarsen: int = 0,
) -> list[_World]:
    """Identical boards merged (hit points to `resolution`, if given, or to the
    cap's grid `coarsen`); boards less likely than `prune` dropped (the caller
    renormalises)."""
    out: dict[tuple, _World] = {}
    for w in worlds:
        if w.p <= prune:
            continue
        k = w.key(resolution, coarsen)
        if k in out:
            out[k].p += w.p
        else:
            out[k] = w
    return list(out.values())


class _Pool:
    """Boards merged as they arrive: the same boards and chances as `_merge` over
    all of them at once, without holding them all (two real turns made about
    89,000 boards in one step before the merge at its end).

    With a `cap`, the grid is coarsened as the pool grows, as `Resolver._capped`
    does at the end, and lands on the same grid with the same boards: the cap's
    grids nest, so merging on a grid and then on the next is merging on the next
    (the first board in each cell is kept, the chances add), and a pool that is
    over the cap on a grid means every board together is over it too."""

    def __init__(
        self, resolution: float | None, prune: float = 0.0, cap: int | None = None
    ) -> None:
        self.resolution, self.prune, self.cap = resolution, prune, cap
        self.level = 0  # the cap's grid boards are keyed on now (0: none)
        self.coarsest = 0.0  # the coarser grid the cap needed (0: none)
        self.peak = 0  # the most boards held at once: the pool and one arrival
        self._out: dict[tuple, _World] = {}

    def add(self, worlds: Sequence[_World]) -> None:
        out = self._out
        self.peak = max(self.peak, len(out) + len(worlds))
        for w in worlds:
            if w.p <= self.prune:
                continue
            k = w.key(self.resolution, self.level)
            if k in out:
                out[k].p += w.p
            else:
                out[k] = w
        if self.cap is not None and len(out) > self.cap:
            self._coarsen()

    def _coarsen(self) -> None:
        assert self.cap is not None
        base = self.resolution or 0.01
        while len(self._out) > self.cap and base * 2**self.level < 0.5:
            self.level += 1
            new: dict[tuple, _World] = {}
            for w in self._out.values():
                k = w.key(self.resolution, self.level)
                if k in new:
                    new[k].p += w.p
                else:
                    new[k] = w
            self._out = new
        self.coarsest = base * 2**self.level

    def worlds(self) -> list[_World]:
        return list(self._out.values())


def _other(role: str) -> str:
    return "p2" if role == "p1" else "p1"


def _mon_key(st: Mapping) -> tuple:
    """What of one Pokemon can change a damage answer (hit points as the
    calculator request coarsens them, with a margin)."""
    return (
        round(st["hp_fraction"], 2),
        tuple(sorted(st["boosts"].items())),
        st["status"],
        st["item"],
        st["mega"],
        st.get("last_move", ""),
        tuple(st.get("types") or ()),
        st.get("typeadd", ""),
        st.get("roost", 0),
    )


class Resolver:
    """One game's resolver: the format's data, the calculator, both sheets and
    each Pokemon's spread, keyed (role, sheet position from 0)."""

    def __init__(
        self,
        dex: Dex,
        moves: Mapping,
        calc,
        sheets: Mapping[str, Sequence[SheetMon]],
        spreads: Mapping[tuple[str, int], Spread],
        resolution: float | None = None,
        prune: float = 0.0,
        cap: int | None = None,
        dists: Mapping[tuple[str, int], Sequence[tuple[Spread, float]]] | None = None,
    ) -> None:
        self.dex, self.moves, self.calc = dex, moves, calc
        self.sheets, self.spreads = sheets, spreads
        # each Pokemon's whole spread belief (Week 11 Task 2): move order then
        # branches on the Speeds the evidence has not settled
        self.dists = dists or {}
        self.resolution, self.prune, self.cap = resolution, prune, cap
        self.coarsest = resolution or 0.0  # the grid the last resolve needed
        self.held = 0  # the most boards the last resolve held at once in a step
        self._hp: dict = {}
        self._dmg: dict = {}  # damage answers by what changes them
        self._spe: dict = {}
        self.dropped = 0.0  # chance dropped by `prune` in the last resolve

    # ------------------------------------------------------------------ facts

    def spread(self, role: str, idx: int) -> Spread:
        sp = self.spreads.get((role, idx))
        if sp is None:
            mon = self.sheets[role][idx]
            sp = default_spread(
                mon.nature, (self.dex.species.get(mon.species) or {}).get("baseStats")
            )
        return sp

    def entry(self, role: str, idx: int, st: Mapping) -> dict:
        mon = self.sheets[role][idx]
        if st.get("mega"):
            return form_of(mon, self.dex)
        return self.dex.species.get(mon.species, {})

    def ability(self, role: str, idx: int, st: Mapping) -> str:
        mon = self.sheets[role][idx]
        e = self.entry(role, idx, st)
        if st.get("mega") and e.get("isMega"):
            return to_id((e.get("abilities") or {}).get("0", mon.ability))
        return mon.ability

    def types(self, role: str, idx: int, st: Mapping) -> list[str]:
        """Its types now: a change the board or this turn made (Protean,
        Soak, Burn Up ...), else its form's, with a type added by
        Trick-or-Treat or Forest's Curse; after Roost this turn, without
        Flying (Normal if nothing is left, as in Showdown)."""
        if st.get("types"):
            out = list(st["types"])
        else:
            out = list(self.entry(role, idx, st).get("types") or [])
            add = st.get("typeadd")
            if add and add not in out:
                out.append(add)
        if st.get("roost") and "Flying" in out:
            out = [t for t in out if t != "Flying"] or ["Normal"]
        return out

    def max_hp(self, role: str, idx: int) -> int:
        key = (role, idx)
        if key not in self._hp:
            from wpa.spreads import _damage_mon

            m = _damage_mon(
                self.sheets[role][idx],
                {},
                self.spread(role, idx),
                self.dex,
                ("hp",),
                lambda h: 1.0,
            )
            ans = self.calc.run([{"op": "stats", "mon": m}])[0]
            self._hp[key] = int(ans["stats"]["hp"])
        return self._hp[key]

    def move(self, move: str) -> dict:
        return self.moves.get(move) or {}

    # ------------------------------------------------------------------ public

    def resolve(
        self,
        sides: Mapping[str, Sequence[Mapping]],
        fld: Field,
        actions: Mapping[str, Sequence[Action]],
    ) -> list[Outcome]:
        self.coarsest = self.resolution or 0.0
        self._pending = {
            (r, a.user): a.move
            for r in ROLES
            for a in actions.get(r, ())
            if a.kind == "move"
        }
        start = _World(
            1.0,
            {
                r: [dict(m, boosts=dict(m.get("boosts") or {})) for m in sides[r]]
                for r in ROLES
            },
            copy.deepcopy(fld),
            set(),
        )
        for r in ROLES:
            for j, x in enumerate(start.sides[r]):
                # a substitute the board says is up: a quarter of the hit points,
                # unless it has been hit (the log never shows what is left)
                up = x.pop("sub_up", None)
                if up and not x.get("sub") and x["active"]:
                    x["sub"] = self.max_hp(r, j) // 4
                    if up == "hit":
                        start.partial.add("substitute hit points")
                # a type copied by Reflect Type: the log does not say it
                if x["active"] and "types" in x and not x["types"]:
                    start.partial.add("type copied by Reflect Type")
        worlds = self._switches(start, actions)
        worlds = [w2 for w in worlds for w2 in self._megas(w, actions)]
        end = _Pool(self.resolution, self.prune)
        self.held = 0
        for w in worlds:
            for order, p in self._orders(w, actions):
                # the boards so far, by the moves still to come (Encore can
                # change those on some boards: `_requeued`)
                groups = {tuple(order): [w.clone(w.p * p)]}
                while groups:
                    pools: dict[tuple, _Pool] = {}
                    for rest, branch in groups.items():
                        if not rest:
                            for b in branch:
                                end.add([b] if b.winner else self._end_of_turn(b))
                            continue
                        (role, act), tail = rest[0], rest[1:]
                        for b in branch:
                            for x in self._act(b, role, act):
                                if x.winner is not None:
                                    # the game is over: Showdown ends the
                                    # battle at the faint, so neither the
                                    # moves still to come nor the end of
                                    # the turn happen
                                    end.add([x])
                                    continue
                                t = tail
                                if x.requeue is not None:
                                    t = self._requeued(x, tail)
                                    x.requeue = None
                                # merged, and capped, as they arrive: a step
                                # never holds every board it makes at once
                                if t not in pools:
                                    pools[t] = _Pool(
                                        self.resolution, self.prune, self.cap
                                    )
                                pools[t].add([x])
                    groups = {}
                    for t, pool in pools.items():
                        groups[t] = pool.worlds()
                        self.coarsest = max(self.coarsest, pool.coarsest)
                        self.held = max(self.held, pool.peak)
        out = end.worlds()
        total = sum(w.p for w in out)
        self.dropped = max(0.0, 1.0 - total)
        return [
            Outcome(w.p / total, w.sides, w.fld, frozenset(w.partial), w.winner)
            for w in out
        ]

    def _capped(self, worlds: list[_World]) -> list[_World]:
        """Over `cap` boards: merge on a coarser hit-point grid until under it.
        Nothing is dropped; the grid used is kept in `coarsest`."""
        if self.cap is None or len(worlds) <= self.cap:
            return worlds
        base, level = self.resolution or 0.01, 0
        while len(worlds) > self.cap and base * 2**level < 0.5:
            level += 1
            worlds = _merge(worlds, self.resolution, 0.0, level)
        self.coarsest = max(self.coarsest, base * 2**level)
        return worlds

    # ------------------------------------------------------------- switching

    def _speed_dist(self, w: _World, role: str, idx: int) -> list[tuple[float, float]]:
        """The Speeds this Pokemon may have, each with its chance: from its
        spread belief where there is one, else the likeliest spread's."""
        d = self.dists.get((role, idx))
        if not d or len(d) < 2:
            return [(self._speed(w, role, idx), 1.0)]
        by: dict[float, float] = {}
        for sp, p in d:
            if p > 0:
                v = self._speed(w, role, idx, sp)
                by[v] = by.get(v, 0.0) + p
        tot = sum(by.values())
        if tot <= 0:
            return [(self._speed(w, role, idx), 1.0)]
        return [(v, p / tot) for v, p in by.items()]

    def _speed(
        self, w: _World, role: str, idx: int, spread: Spread | None = None
    ) -> float:
        st = w.sides[role][idx]
        mon = self.sheets[role][idx]
        sp = spread or self.spread(role, idx)
        from wpa.features import _board_state

        key = (
            role,
            idx,
            sp,
            w.fld.weather,
            w.fld.terrain,
            bool(w.fld.sides[role].get("tailwind")),
            tuple(sorted(st["boosts"].items())),
            st["status"],
            st["item"],
            st["mega"],
        )
        if key not in self._spe:
            req = speed_request(
                mon,
                _board_state(st),
                sp,
                self.dex,
                {"weather": w.fld.weather, "terrain": w.fld.terrain},
                bool(w.fld.sides[role].get("tailwind")),
            )
            self._spe[key] = float(self.calc.run([req])[0].get("speed", 0))
        return self._spe[key]

    def _switches(self, w: _World, actions) -> list[_World]:
        sw = [(r, a) for r in ROLES for a in actions.get(r, ()) if a.kind == "switch"]
        sw.sort(key=lambda ra: -self._speed(w, ra[0], ra[1].user))
        for role, a in sw:
            self._switch(w, role, a.user, a.switch_to)
        return [w]

    def replace(
        self,
        sides: Mapping[str, Sequence[Mapping]],
        fld: Field,
        actions: Mapping[str, Sequence[Action]],
    ) -> list[Outcome]:
        """A forced switch after a turn (Week 10 Task 6): each fainted Pokemon an
        action names is replaced by the one it brings in, both sides at once;
        then the newcomers' entry effects (Intimidate, weather, terrain) in Speed
        order, as Showdown runs them (Trick Room reverses it). Nothing on entry
        is random yet, so one outcome."""
        w = _World(
            1.0,
            {
                r: [dict(m, boosts=dict(m.get("boosts") or {})) for m in sides[r]]
                for r in ROLES
            },
            copy.deepcopy(fld),
            set(),
        )
        ins = [
            (r, a.user, a.switch_to)
            for r in ROLES
            for a in actions.get(r, ())
            if a.kind == "switch" and a.switch_to is not None
        ]
        came = []
        for r, old, new in ins:
            if self._switch(w, r, old, new, entry=False):
                came.append((r, new))
        sign = 1 if w.fld.trickroom else -1
        came.sort(key=lambda x: sign * self._speed(w, x[0], x[1]))
        for r, new in came:
            self._on_entry(w, r, new)
        return [Outcome(1.0, w.sides, w.fld, frozenset(w.partial), w.winner)]

    def lead(
        self,
        sides: Mapping[str, Sequence[Mapping]],
        fld: Field,
        actions: Mapping[str, Sequence[Action]],
    ) -> list[Outcome]:
        """Team preview's leads (Week 11 Task 1): the Pokemon each side's switch
        actions name come in, both sides at once, then their entry effects in
        Speed order, as at the start of a game. One outcome."""
        w = _World(
            1.0,
            {
                r: [dict(m, boosts=dict(m.get("boosts") or {})) for m in sides[r]]
                for r in ROLES
            },
            copy.deepcopy(fld),
            set(),
        )
        came = []
        for r in ROLES:
            for a in actions.get(r, ()):
                j = a.switch_to
                if a.kind != "switch" or j is None:
                    continue
                m = w.sides[r][j]
                if m["fainted"] or m["active"]:
                    continue
                if m["hp_fraction"] <= 0:
                    m["hp_fraction"] = 1.0  # first time in
                m.update(active=True, boosts={}, moved=False, last_move="")
                m["protect_streak"] = 0
                came.append((r, j))
        sign = 1 if w.fld.trickroom else -1
        came.sort(key=lambda x: sign * self._speed(w, x[0], x[1]))
        for r, j in came:
            self._on_entry(w, r, j)
        return [Outcome(1.0, w.sides, w.fld, frozenset(w.partial), w.winner)]

    def _switch(
        self, w: _World, role: str, old: int, new: int | None, entry: bool = True
    ) -> bool:
        if new is None or old is None:
            return False
        o, n = w.sides[role][old], w.sides[role][new]
        if n["fainted"] or n["active"]:
            return False
        o.update(active=False, boosts={}, moved=False, last_move="", protect_streak=0)
        o.pop("perish", None)  # switching out ends the count
        for k in LEAVING:  # and confusion, a charging move, Encore, Rage Fist's hits
            o.pop(k, None)
        n.pop("perish", None)
        o.pop("sub", None)  # and a substitute
        n.pop("sub", None)
        if n["hp_fraction"] <= 0:
            n["hp_fraction"] = 1.0  # first time in
        n.update(active=True, boosts={}, moved=False, last_move="", protect_streak=0)
        w.replaced[(role, old)] = (role, new)
        if entry:
            self._on_entry(w, role, new)
        return True

    def _on_entry(self, w: _World, role: str, idx: int) -> None:
        st = w.sides[role][idx]
        ab = self.ability(role, idx, st)
        if ab == "intimidate":
            for j, m in enumerate(w.sides[_other(role)]):
                if m["active"] and not m["fainted"]:
                    self._intimidate(w, _other(role), j)
        elif ab in WEATHER_ABILITIES:
            self._set_weather(w, WEATHER_ABILITIES[ab], st.get("item") or "")
        elif ab in TERRAIN_ABILITIES:
            self._set_terrain(w, TERRAIN_ABILITIES[ab], st.get("item") or "")

    def _intimidate(self, w: _World, role: str, idx: int) -> None:
        st = w.sides[role][idx]
        ab = self.ability(role, idx, st)
        if ab in INTIMIDATE_BLOCK or st.get("item") == "clearamulet":
            return
        if ab == "mirrorarmor":
            return  # reflected; the user's side is not tracked here
        self._boost(st, {"atk": -1})
        if st.get("item") == "ejectpack":
            w.partial.add("eject pack")
        if ab == "defiant":
            self._boost(st, {"atk": 2})
        elif ab == "competitive":
            self._boost(st, {"spa": 2})
        elif ab == "guarddog":
            self._boost(st, {"atk": 2})  # Guard Dog: +1 on top of cancelling the drop
        elif ab == "rattled":
            self._boost(st, {"spe": 1})

    def _set_weather(self, w: _World, weather: str, item: str) -> None:
        if w.fld.weather == weather:
            return
        w.fld.weather = weather
        w.fld.weather_left = 8 if WEATHER_ROCKS.get(weather) == item else 5

    def _set_terrain(self, w: _World, terrain: str, item: str) -> None:
        if w.fld.terrain == terrain:
            return
        w.fld.terrain = terrain
        w.fld.terrain_left = 8 if item == "terrainextender" else 5

    @staticmethod
    def _boost(st: dict, changes: Mapping[str, int]) -> None:
        b = st["boosts"]
        for k, v in changes.items():
            n = max(-6, min(6, b.get(k, 0) + v))
            if n:
                b[k] = n
            else:
                b.pop(k, None)

    def _megas(self, w: _World, actions) -> list[_World]:
        for r in ROLES:
            for a in actions.get(r, ()):
                if a.kind == "move" and a.mega and not w.sides[r][a.user]["mega"]:
                    w.sides[r][a.user]["mega"] = True
                    # its new form's types, and its ability afresh (Protean
                    # can act again)
                    for k in ("types", "typeadd", "protean"):
                        w.sides[r][a.user].pop(k, None)
                    self._on_entry(w, r, a.user)
        return [w]

    # ----------------------------------------------------------------- order

    def _priority(self, w: _World, role: str, a: Action) -> int:
        m = self.move(a.move)
        pr = int(m.get("priority") or 0)
        st = w.sides[role][a.user]
        ab = self.ability(role, a.user, st)
        if ab == "prankster" and m.get("category") == "Status":
            pr += 1
        elif ab == "galewings" and m.get("type") == "Flying" and st["hp_fraction"] >= 1:
            pr += 1
        elif ab == "triage" and "heal" in (m.get("flags") or []):
            pr += 3
        return pr

    def _orders(self, w: _World, actions) -> list[tuple[list, float]]:
        movers = [
            (r, a)
            for r in ROLES
            for a in actions.get(r, ())
            if a.kind == "move" and w.sides[r][a.user]["active"]
        ]
        sign = 1 if w.fld.trickroom else -1
        pri = [-self._priority(w, r, a) for r, a in movers]
        speeds = [self._speed_dist(w, r, a.user) for r, a in movers]
        out: dict[tuple, float] = {}
        for drawn in product(*speeds):
            q = 1.0
            for _v, p in drawn:
                q *= p
            if q <= 0:
                continue
            keyed = [
                ((pri[i], sign * drawn[i][0]), movers[i]) for i in range(len(movers))
            ]
            keyed.sort(key=lambda x: x[0])
            groups: list[list] = []
            for k, ra in keyed:
                if groups and groups[-1][0] == k:
                    groups[-1][1].append(ra)
                else:
                    groups.append([k, [ra]])
            perms = [list(permutations(g[1])) for g in groups]
            for combo in product(*perms):
                p = q
                for g in perms:
                    p /= len(g)
                order = tuple(ra for part in combo for ra in part)
                out[order] = out.get(order, 0.0) + p
        return [(list(o), p) for o, p in out.items()]

    def orders(
        self,
        sides: Mapping[str, Sequence[Mapping]],
        fld: Field,
        actions: Mapping[str, Sequence[Action]],
    ) -> list[tuple[list, float]]:
        """The order the moves can go in, each with its chance (priority, then
        Speed; Speed ties 50/50; with spread beliefs, each Speed the evidence
        has not settled)."""
        w = _World(
            1.0,
            {r: [dict(m) for m in sides[r]] for r in ROLES},
            copy.deepcopy(fld),
            set(),
        )
        return self._orders(w, actions)

    # ---------------------------------------------------------------- acting

    def _current(self, w: _World, who: tuple[str, int]) -> tuple[str, int]:
        while who in w.replaced:
            who = w.replaced[who]
        return who

    def _act(self, w: _World, role: str, a: Action) -> list[_World]:
        st = w.sides[role][a.user]
        if st["fainted"] or not st["active"]:
            return [w]
        enc = st.get("encore")
        if enc and a.kind == "move" and a.move != enc:
            # Encore landed before it moved: the encored move instead, at a
            # random foe (Champions' Encore changes the queued action with no
            # target: Showdown draws one), in its new place (`_requeued`)
            return [
                x
                for b, a2 in self._encored(w, role, a, enc)
                for x in self._act(b, role, a2)
            ]
        # can it move at all? In Showdown's order: sleep and freeze, flinch,
        # confusion, paralysis; with the Champions rules (`data/mods/champions`)
        if st["status"] in ("slp", "frz"):
            return self._asleep_or_frozen(w, role, a)
        if (role, a.user) in w.flinched:
            w.acted.add((role, a.user))
            return [w]
        return self._confused_then(w, role, a)

    def _requeued(self, w: _World, tail: tuple) -> tuple:
        """Encore in Champions (`data/mods/champions/moves.ts`) changes the
        target's queued action to the encored move, with that move's priority,
        and the queue is sorted again: its place among the moves still to come
        is by the new move's priority, then Speed (Trick Room reversed). Its
        target is drawn when it moves (`_encored`)."""
        assert w.requeue is not None
        role, idx = w.requeue
        i = next(
            (k for k, (r, a) in enumerate(tail) if r == role and a.user == idx), None
        )
        enc = w.sides[role][idx].get("encore")
        if i is None or not enc:
            return tail
        mine = tail[i]
        rest = tail[:i] + tail[i + 1 :]
        pri = self._priority(w, role, Action(idx, "move", move=enc))
        spe = self._speed(w, role, idx)
        slow_first = bool(w.fld.trickroom)

        def goes_first(other) -> bool:
            r2, a2 = other
            p2 = self._priority(w, r2, a2)
            if pri != p2:
                return pri > p2
            s2 = self._speed(w, r2, a2.user)
            return spe < s2 if slow_first else spe > s2

        k = next((n for n, o in enumerate(rest) if goes_first(o)), len(rest))
        return rest[:k] + (mine,) + rest[k:]

    def _encored(
        self, w: _World, role: str, a: Action, enc: str
    ) -> list[tuple[_World, Action]]:
        kind = self.move(enc).get("target", "normal")
        new = Action(a.user, "move", move=enc)
        if kind not in ONE_FOE:
            return [(w, new)]
        foes = [
            j
            for j, x in enumerate(w.sides[_other(role)])
            if x["active"] and not x["fainted"]
        ]
        if not foes:
            return [(w, new)]
        out = []
        for n, j in enumerate(foes):
            b = w if n == len(foes) - 1 else w.clone(w.p / len(foes))
            out.append((b, Action(a.user, "move", move=enc, target=("foe", j))))
        w.p /= len(foes)
        return out

    def _asleep_or_frozen(self, w: _World, role: str, a: Action) -> list[_World]:
        """Champions: sleep ends on the second try with chance 1/3, on the third
        for sure (Early Bird counts each try twice); freeze thaws with chance 1/4
        a try, on the third for sure, and at once for a move that thaws."""
        st = w.sides[role][a.user]
        status = st["status"]
        n = st.get(status + "_n", 0) + 1
        if status == "slp":
            if self.ability(role, a.user, st) == "earlybird":
                n = 2 * n
            free = SLEEP_WAKE.get(n, 1.0)
            if self.move(a.move).get("sleepUsable"):
                w.partial.add("sleep talk")
        else:
            thaws = "defrost" in (self.move(a.move).get("flags") or [])
            free = 1.0 if thaws or n >= 3 else 0.25
        out = []
        if free < 1:
            stay = w.clone(w.p * (1 - free)) if free > 0 else w
            stay.sides[role][a.user][status + "_n"] = n
            stay.acted.add((role, a.user))
            out.append(stay)
        if free > 0:
            go = w
            go.p *= free
            x = go.sides[role][a.user]
            x["status"] = ""
            x.pop(status + "_n", None)
            if (role, a.user) in go.flinched:
                go.acted.add((role, a.user))
                out.append(go)
            else:
                out += self._confused_then(go, role, a)
        return out

    def _confused_then(self, w: _World, role: str, a: Action) -> list[_World]:
        """Confusion (Showdown, unchanged in Champions): 2 to 5 tries; on the
        n-th it snaps out with chance 1/(6 - n), else it hits itself 33 times in
        100 instead of moving. Then paralysis: 1 time in 8 it cannot move."""
        st = w.sides[role][a.user]
        if "confused" not in st:
            return self._paralysed_then(w, role, a)
        n = st["confused"] + 1
        snap = 0.0 if n < 2 else (1.0 if n >= 5 else 1 / (6 - n))
        out = []
        if snap > 0:
            free = w.clone(w.p * snap) if snap < 1 else w
            free.sides[role][a.user].pop("confused", None)
            out += self._paralysed_then(free, role, a)
            if snap >= 1:
                return out
            w.p *= 1 - snap
        w.sides[role][a.user]["confused"] = n
        hurt = w.clone(w.p * CONFUSED_HIT)
        w.p *= 1 - CONFUSED_HIT
        out += self._hits_itself(hurt, role, a.user)
        out += self._paralysed_then(w, role, a)
        return out

    def _paralysed_then(self, w: _World, role: str, a: Action) -> list[_World]:
        if w.sides[role][a.user]["status"] == "par":
            stuck, go = w.clone(w.p * PARALYSED), w
            go.p *= 1 - PARALYSED
            stuck.acted.add((role, a.user))
            return [stuck, *self._use(go, role, a)]
        return self._use(w, role, a)

    def _hits_itself(self, w: _World, role: str, idx: int) -> list[_World]:
        """Confusion's self-hit: Showdown's getConfusionDamage, a 40-power
        typeless physical hit with its own Attack and Defense and their stages,
        16 rolls; Focus Sash and Sturdy hold at full hit points."""
        st = w.sides[role][idx]
        w.acted.add((role, idx))
        b = st.get("boosts") or {}
        key = ("confused", role, idx, b.get("atk", 0), b.get("def", 0))
        if key not in self._dmg:
            atk, dfn = self._stats(role, idx, ("atk", "def"))
            atk, dfn = _staged(atk, b.get("atk", 0)), _staged(dfn, b.get("def", 0))
            base = ((2 * 50 // 5 + 2) * 40 * atk // dfn) // 50 + 2
            self._dmg[key] = [max(1, base * (100 - r) // 100) for r in range(16)]
        max_hp = self.max_hp(role, idx)
        hp = round(st["hp_fraction"] * max_hp)
        groups: dict[int, float] = {}
        for dmg in self._dmg[key]:
            new = max(0, hp - dmg)
            if (
                new == 0
                and hp == max_hp
                and (
                    st.get("item") == "focussash"
                    or self.ability(role, idx, st) == "sturdy"
                )
            ):
                new = 1
            groups[new] = groups.get(new, 0.0) + 1 / 16
        out = []
        for new, p in groups.items():
            x = w.clone(w.p * p)
            y = x.sides[role][idx]
            if new == 1 and hp == max_hp and y.get("item") == "focussash":
                y["item"], y["rev_item"] = "", "focussash"
            y["hp_fraction"] = new / max_hp
            if new == 0:
                self._faint(x, (role, idx))
            out.append(x)
        return out

    def _stats(self, role: str, idx: int, which: tuple[str, ...]) -> tuple[int, ...]:
        key = ("stats", role, idx, which)
        if key not in self._dmg:
            from wpa.spreads import _damage_mon

            m = _damage_mon(
                self.sheets[role][idx],
                {},
                self.spread(role, idx),
                self.dex,
                which,
                lambda h: 1.0,
            )
            ans = self.calc.run([{"op": "stats", "mon": m}])[0]["stats"]
            self._dmg[key] = tuple(int(ans[k]) for k in which)
        return self._dmg[key]

    def _use(self, w: _World, role: str, a: Action) -> list[_World]:
        mv = a.move
        m = self.move(mv)
        st = w.sides[role][a.user]
        protect_used = mv in PROTECT_LIKE
        first_turn = not st["moved"]
        st["moved"], st["last_move"] = True, mv
        w.hit, w.dealt, w.subbed = set(), 0, set()
        if not protect_used:
            st["protect_streak"] = 0
        w.acted.add((role, a.user))
        if not m:
            w.partial.add(f"move:{mv}")
            return [w]
        if st.get("taunt") and m.get("category") == "Status":
            return [w]  # taunted: it cannot use a status move
        if st.get("disabled") == mv:
            return [w]  # disabled
        if protect_used:
            return self._protect(w, role, a)
        if "charge" in (m.get("flags") or []):
            if st.get("charging") == mv:
                st.pop("charging")  # the turn after charging: it goes off
            else:
                sunny = (
                    mv in {"solarbeam", "solarblade"} and w.fld.weather == "sunnyday"
                )
                rainy = mv == "electroshot" and w.fld.weather == "raindance"
                if mv in {"electroshot", "meteorbeam"}:
                    self._boost(st, {"spa": 1})
                elif mv == "skullbash":
                    self._boost(st, {"def": 1})
                if not (sunny or rainy or st.get("item") == "powerherb"):
                    # it charges; in the air or underground, out of reach
                    # until it moves next turn (`_targets`)
                    st["charging"] = mv
                    return [w]
                if st.get("item") == "powerherb" and not (sunny or rainy):
                    st["item"] = ""
        if mv in {"fakeout", "firstimpression"} and not first_turn:
            return [w]  # it works only on the Pokemon's first turn in
        if self._queenly(w, role, a, m):
            return [w]  # Armor Tail, Dazzling, Queenly Majesty: the move fails
        if mv in LOSES_TYPE and LOSES_TYPE[mv] not in self.types(role, a.user, st):
            return [w]  # Burn Up without Fire, Double Shock without Electric
        self._protean(w, role, a.user, m)
        if m.get("category") == "Status":
            return self._status(w, role, a, m)
        return self._attack(w, role, a, m)

    def _protect(self, w: _World, role: str, a: Action) -> list[_World]:
        st = w.sides[role][a.user]
        streak = st["protect_streak"]
        p_ok = 1.0 / (3**streak)
        out = []
        if p_ok > 0:
            ok = w.clone(w.p * p_ok) if p_ok < 1 else w
            s2 = ok.sides[role][a.user]
            s2["protect_streak"] = streak + 1
            # Protean: only when it works (Protect's own check comes first)
            self._protean(ok, role, a.user, self.move(a.move))
            if a.move == "wideguard":
                ok.guards.add((role, "wideguard"))
            elif a.move == "quickguard":
                ok.guards.add((role, "quickguard"))
            elif a.move != "endure":
                ok.protected.add((role, a.user))
            else:
                ok.partial.add("move:endure")
            out.append(ok)
        if p_ok < 1:
            fail = w.clone(w.p * (1 - p_ok)) if out else w
            fail.sides[role][a.user]["protect_streak"] = 0
            out.append(fail)
        return out

    # -------------------------------------------------------------- targets

    def _targets(
        self, w: _World, role: str, a: Action, m: Mapping
    ) -> list[tuple[str, int]]:
        """Who the move hits; a Pokemon in the air, underground or vanished
        (charging Fly, Dig, Phantom Force...) is out of reach (Week 11)."""
        out = self._targets_all(w, role, a, m)
        kept = []
        for t in out:
            away = w.sides[t[0]][t[1]].get("charging")
            if t != (role, a.user) and away in OUT_OF_REACH:
                if a.move in REACHES.get(away, ()):
                    w.partial.add(f"{a.move} reaches {away}")
                    kept.append(t)
                continue
            kept.append(t)
        return kept

    def _targets_all(
        self, w: _World, role: str, a: Action, m: Mapping
    ) -> list[tuple[str, int]]:
        kind = m.get("target", "normal")
        foe = _other(role)
        foes = [
            (foe, j)
            for j, x in enumerate(w.sides[foe])
            if x["active"] and not x["fainted"]
        ]
        allies = [
            (role, j)
            for j, x in enumerate(w.sides[role])
            if x["active"] and not x["fainted"] and j != a.user
        ]
        if kind == "allAdjacentFoes":
            return foes
        if kind == "allAdjacent":
            return foes + allies
        if kind in ("self", "allySide", "foeSide", "all", "allies", "allyTeam"):
            return [(role, a.user)]
        if a.target is None:
            if kind == "adjacentAllyOrSelf" or a.move == "curse":
                return [(role, a.user)]
            if kind == "randomNormal":
                return foes[:1] if len(foes) <= 1 else foes  # handled as a split below
            return foes[:1]
        side = foe if a.target[0] == "foe" else role
        who = self._current(w, (side, a.target[1]))
        tgt = w.sides[who[0]][who[1]]
        rod = self._rod(w, role, a, m)
        if side == foe:
            red = w.redirect.get(foe)
            if red is not None and self._redirectable(w, role, a, red):
                return [(red[0], red[1])]
        if rod is not None and rod != who:
            return [rod]
        if side == foe:
            if tgt["fainted"] or not tgt["active"]:
                return foes[:1]  # retarget the other opposing Pokemon
            return [who]
        if tgt["fainted"] or not tgt["active"]:
            return []
        return [who]

    def _redirectable(self, w: _World, role: str, a: Action, red) -> bool:
        st = w.sides[red[0]][red[1]]
        if st["fainted"] or not st["active"]:
            return False
        user = w.sides[role][a.user]
        if (
            self.ability(role, a.user, user) in {"stalwart", "propellertail"}
            or a.move == "snipeshot"
        ):
            return False
        if red[2] == "ragepowder":
            if (
                "Grass" in self.types(role, a.user, user)
                or user.get("item") == "safetygoggles"
                or self.ability(role, a.user, user) == "overcoat"
            ):
                return False
        return True

    def _blocked(
        self,
        w: _World,
        role: str,
        a: Action,
        m: Mapping,
        tgt: tuple[str, int],
        spread: bool,
    ) -> bool:
        if tgt[0] == role:
            return False
        flags = m.get("flags") or []
        if tgt in w.protected and "protect" in flags and not m.get("breaksProtect"):
            return True
        if spread and (tgt[0], "wideguard") in w.guards:
            return True
        if (tgt[0], "quickguard") in w.guards and self._priority(w, role, a) > 0:
            return True
        if (
            w.fld.terrain == "psychicterrain"
            and self._priority(w, role, a) > 0
            and self._grounded(tgt, w.sides[tgt[0]][tgt[1]])
        ):
            return True
        return False

    def _protean(self, w: _World, role: str, idx: int, m: Mapping) -> None:
        """Protean and Libero (Showdown's onPrepareHit): once each time it
        comes in, the user becomes the type of the move it uses, unless that
        is its type already (then it is not used up)."""
        st = w.sides[role][idx]
        if st.get("protean") or self.ability(role, idx, st) not in PROTEAN:
            return
        t = m.get("type") or ""
        if not t or t == "???" or self.types(role, idx, st) == [t]:
            return
        st["types"] = [t]
        st.pop("typeadd", None)
        st["protean"] = 1

    def _retype(self, w: _World, role: str, a: Action, tgt) -> None:
        """Soak (pure Water), Trick-or-Treat and Forest's Curse (a type
        added), Reflect Type (the user takes the target's types), as in
        Showdown; each fails where it would change nothing."""
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"]:
            return
        now = self.types(tgt[0], tgt[1], x)
        if a.move == "soak":
            if now != ["Water"]:
                x["types"] = ["Water"]
                x.pop("typeadd", None)
        elif a.move in ("trickortreat", "forestscurse"):
            add = "Ghost" if a.move == "trickortreat" else "Grass"
            if add not in now:
                x["typeadd"] = add
        elif a.move == "reflecttype":
            here = self.entry(tgt[0], tgt[1], x).get("types")
            base = list(x.get("types") or here or [])
            base = [t for t in base if t != "???"]
            if not base and x.get("typeadd"):
                base = ["Normal"]
            if base:
                me = w.sides[role][a.user]
                me["types"] = base
                me.pop("typeadd", None)
                if x.get("typeadd"):
                    me["typeadd"] = x["typeadd"]

    def _good_as_gold(
        self, w: _World, role: str, a: Action, m: Mapping, tgt: tuple[str, int]
    ) -> bool:
        """Good as Gold: a status move a foe aims at it fails (Showdown's
        onTryHit), unless the user's ability ignores it (Mold Breaker and the
        like)."""
        if tgt[0] == role or m.get("category") != "Status":
            return False
        x = w.sides[tgt[0]][tgt[1]]
        if self.ability(tgt[0], tgt[1], x) != "goodasgold":
            return False
        return self.ability(role, a.user, w.sides[role][a.user]) not in MOLD

    def _grounded(self, who: tuple[str, int], st: Mapping) -> bool:
        return (
            "Flying" not in self.types(who[0], who[1], st)
            and self.ability(who[0], who[1], st) != "levitate"
            and st.get("item") != "airballoon"
        )

    def _queenly(self, w: _World, role: str, a: Action, m: Mapping) -> bool:
        """A priority move aimed at a side with Armor Tail, Dazzling or Queenly
        Majesty fails (Showdown's onFoeTryMove; moves aimed at a whole side or the
        whole field are not stopped)."""
        if m.get("target") in NOT_AIMED or self._priority(w, role, a) <= 0:
            return False
        if a.target is not None and a.target[0] != "foe":
            return False
        foe = _other(role)
        return any(
            x["active"] and not x["fainted"] and self.ability(foe, j, x) in QUEENLY
            for j, x in enumerate(w.sides[foe])
        )

    def _rod(self, w: _World, role: str, a: Action, m: Mapping):
        """Lightning Rod or Storm Drain draws a single-target Electric or Water
        move from any other Pokemon on the field (Stalwart, Propeller Tail and
        Snipe Shot ignore it)."""
        want = RODS.get(m.get("type", ""))
        if want is None or m.get("target") not in SINGLE:
            return None
        user = w.sides[role][a.user]
        if (
            self.ability(role, a.user, user) in {"stalwart", "propellertail"}
            or a.move == "snipeshot"
        ):
            return None
        for r in (_other(role), role):
            for j, x in enumerate(w.sides[r]):
                if (r, j) == (role, a.user) or not x["active"] or x["fainted"]:
                    continue
                if self.ability(r, j, x) == want:
                    return (r, j)
        return None

    # ---------------------------------------------------------------- status

    def _status(self, w: _World, role: str, a: Action, m: Mapping) -> list[_World]:
        mv = a.move
        st = w.sides[role][a.user]
        if mv == "roost":
            st["roost"] = 1  # no Flying type until the end of the turn
        if mv == "perishsong":
            # every Pokemon on the field not already counting; through Protect,
            # not through Soundproof. 4 now, so 3 shows after this turn
            for r in ROLES:
                for j, x in enumerate(w.sides[r]):
                    if (
                        x["active"]
                        and not x["fainted"]
                        and not x.get("perish")
                        and self.ability(r, j, x) != "soundproof"
                    ):
                        x["perish"] = 4
            return [w]
        vol = m.get("volatileStatus")
        if vol in ("followme", "ragepowder"):
            w.redirect[role] = (role, a.user, vol)
            return [w]
        if vol == "helpinghand":
            for j, x in enumerate(w.sides[role]):
                if (
                    j != a.user
                    and x["active"]
                    and not x["fainted"]
                    and (role, j) not in w.acted
                ):
                    w.helped.add((role, j))
            return [w]
        sc = m.get("sideCondition")
        if sc in SIDE_TIMED:
            if sc == "auroraveil" and w.fld.weather != "snowscape":
                return [w]
            sides = w.fld.sides[role]
            if sc in SCREENS and st.get("item") == "lightclay":
                sides[sc] = 8
            elif sc not in sides:
                sides[sc] = SIDE_TIMED[sc]
            return [w]
        if m.get("weather"):
            self._set_weather(w, to_id(m["weather"]), st.get("item") or "")
            if m.get("selfSwitch"):  # Chilly Reception
                return self._self_switch(w, role, a.user, a.switch_to)
            return [w]
        if mv in ("substitute", "shedtail"):
            return self._substitute(w, role, a, m)
        if m.get("terrain"):
            self._set_terrain(w, to_id(m["terrain"]), st.get("item") or "")
            return [w]
        if m.get("pseudoWeather") == "trickroom":
            w.fld.trickroom = 0 if w.fld.trickroom else 5
            return [w]
        if mv == "haze":
            for r in ROLES:
                for x in w.sides[r]:
                    if x["active"]:
                        x["boosts"] = {}
            return [w]
        if mv == "bellydrum":
            max_hp = self.max_hp(role, a.user)
            hp = round(st["hp_fraction"] * max_hp)
            if hp > max_hp // 2 and st["boosts"].get("atk", 0) < 6:
                st["hp_fraction"] = (hp - max_hp // 2) / max_hp
                self._boost(st, {"atk": 12})
            return [w]
        if mv in WEATHER_HEAL or mv == "shoreup":
            weather = w.fld.weather
            if mv == "shoreup":
                gain = 2 / 3 if weather == "sandstorm" else 1 / 2
            elif weather == "sunnyday":
                gain = 2 / 3
            elif weather in ("raindance", "sandstorm", "hail", "snowscape"):
                gain = 1 / 4
            else:
                gain = 1 / 2
            self._heal(w, role, a.user, gain)
            return [w]
        targets = self._targets(w, role, a, m)
        if m.get("heal") and m.get("target") in ("self", "allies", "allySide"):
            n, d = m["heal"]
            self._heal(w, role, a.user, n / d)
            return [w]
        if m.get("boosts") and m.get("target") == "self":
            self._boost(st, m["boosts"])
            return [w]
        if m.get("boosts") and m.get("target") in ("allies", "allySide"):
            for x in w.sides[role]:
                if x["active"] and not x["fainted"]:
                    self._boost(x, m["boosts"])
            return [w]
        handled = bool(
            m.get("status")
            or m.get("boosts")
            or m.get("selfSwitch")
            or m.get("forceSwitch")
            or vol in ("confusion", "encore", "leechseed", "taunt", "yawn", "disable")
            or mv in ON_TARGET
            or mv in RETYPE
        )
        if not handled:
            w.partial.add(f"move:{mv}")
            return [w]
        out = [w]
        prankster = self.ability(role, a.user, st) == "prankster"
        failed: set[int] = set()  # boards where the move did nothing (no switch)
        # Parting Shot lowers both attacks in the move's code, not its data
        drops = m.get("boosts") or (
            {"atk": -1, "spa": -1} if mv == "partingshot" else None
        )
        for tgt in targets:
            nxt = []
            for b in out:
                if (
                    self._blocked(b, role, a, m, tgt, len(targets) > 1)
                    or self._behind_sub(b, role, a, m, tgt)
                    or self._good_as_gold(b, role, a, m, tgt)
                ):
                    failed.add(id(b))
                    nxt.append(b)
                    continue
                if (
                    prankster
                    and tgt[0] != role
                    and "Dark" in self.types(*tgt, b.sides[tgt[0]][tgt[1]])
                ):
                    nxt.append(b)
                    continue
                acc = self._accuracy(b, role, a, m, tgt)
                hit = b.clone(b.p * acc) if acc < 1 else b
                if acc < 1:
                    b.p *= 1 - acc
                    failed.add(id(b))
                    nxt.append(b)
                if m.get("status"):
                    self._inflict(hit, tgt, m["status"], mv)
                if vol == "confusion":
                    self._confuse(hit, tgt)
                elif vol == "encore":
                    self._encore(hit, tgt)
                elif vol == "leechseed":
                    self._seed(hit, tgt, a.user)
                elif vol == "taunt":
                    self._taunt(hit, tgt)
                elif vol == "yawn":
                    self._yawn(hit, tgt)
                elif vol == "disable":
                    self._disable(hit, tgt)
                if mv in ON_TARGET:
                    self._on_target(hit, role, a, tgt)
                if mv in RETYPE:
                    self._retype(hit, role, a, tgt)
                if drops and not self._drop(hit, tgt, drops):
                    if tgt[0] != role:
                        failed.add(id(hit))  # Parting Shot: no drop, no switch
                nxt.append(hit)
            out = nxt
        if m.get("selfSwitch"):
            out = [
                x
                for b in out
                for x in (
                    [b]
                    if id(b) in failed
                    else self._self_switch(
                        b, role, a.user, a.switch_to, m["selfSwitch"]
                    )
                )
            ]
        if m.get("forceSwitch"):
            # no target left (it fell earlier in the turn): the move fails, the
            # board stays
            out = [
                x for b in out for x in (self._drag(b, targets[0]) if targets else [b])
            ]
        return out

    def _confuse(self, w: _World, tgt: tuple[str, int]) -> None:
        """Confused from now: its next try is the first (Own Tempo, and Misty
        Terrain for a grounded Pokemon, prevent it)."""
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"] or "confused" in x:
            return
        if self.ability(tgt[0], tgt[1], x) == "owntempo":
            return
        if w.fld.terrain == "mistyterrain" and self._grounded(tgt, x):
            return
        x["confused"] = 0

    def _encore(self, w: _World, tgt: tuple[str, int]) -> None:
        """Encore locks the target into the move it used last. If it has not
        moved yet this turn, it uses that move instead (`_act`), in the place
        that move's priority gives it (`_requeued`). A Mental Herb ends it at
        once, and is used up."""
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"] or x.get("encore") or not x.get("last_move"):
            return
        if "failencore" in (self.move(x["last_move"]).get("flags") or []):
            return
        if self._mental_herb(x):
            return
        x["encore"] = x["last_move"]
        if tgt not in w.acted:
            w.requeue = tgt

    @staticmethod
    def _mental_herb(x: dict) -> bool:
        """A Mental Herb ends Taunt, Encore and Disable as they start."""
        if x.get("item") != "mentalherb":
            return False
        x["item"], x["rev_item"] = "", "mentalherb"
        return True

    def _taunt(self, w: _World, tgt: tuple[str, int]) -> None:
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"] or x.get("taunt"):
            return
        if self.ability(tgt[0], tgt[1], x) in TAUNT_BLOCK or self._mental_herb(x):
            return
        x["taunt"] = 1

    def _on_target(self, w: _World, role: str, a: Action, tgt) -> None:
        """Heal Pulse and Floral Healing (half, Mega Launcher three quarters,
        Floral Healing two thirds on Grassy Terrain), Psych Up (the target's
        stat changes copied) and Strength Sap (heals by the target's Attack, as
        changed so far, then lowers it; nothing if it is at -6)."""
        x = w.sides[tgt[0]][tgt[1]]
        st = w.sides[role][a.user]
        if x["fainted"]:
            return
        if a.move == "healpulse":
            mega = self.ability(role, a.user, st) == "megalauncher"
            self._heal(w, tgt[0], tgt[1], 3 / 4 if mega else 1 / 2)
        elif a.move == "floralhealing":
            grassy = w.fld.terrain == "grassyterrain"
            self._heal(w, tgt[0], tgt[1], 2 / 3 if grassy else 1 / 2)
        elif a.move == "psychup":
            st["boosts"] = dict(x["boosts"])
        elif a.move == "strengthsap":
            stage = x["boosts"].get("atk", 0)
            if stage <= -6:
                return
            atk = self._stats(tgt[0], tgt[1], ("atk",))[0]
            atk *= (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)
            self._drop(w, tgt, {"atk": -1})
            self._heal(w, role, a.user, int(atk) / self.max_hp(role, a.user))

    def _disable(self, w: _World, tgt: tuple[str, int]) -> None:
        """Disable: the target's last move, until it leaves the field (the log
        shows when it ends)."""
        x = w.sides[tgt[0]][tgt[1]]
        last = x.get("last_move")
        if x["fainted"] or x.get("disabled") or not last or last == "struggle":
            return
        if self._mental_herb(x):
            return
        x["disabled"] = last

    def _seed(self, w: _World, tgt: tuple[str, int], user: int) -> None:
        """Leech Seed: not on a Grass type, nor twice; `seeded` is the sheet
        position of the Pokemon in the seeder's place, on the other side (-1
        while it is empty)."""
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"] or "seeded" in x:
            return
        if "Grass" in self.types(tgt[0], tgt[1], x):
            return
        x["seeded"] = user

    def _yawn(self, w: _World, tgt: tuple[str, int]) -> None:
        """Yawn: asleep at the end of the next turn (`_end_of_turn`), if it can
        fall asleep then. It fails on a Pokemon with a status."""
        x = w.sides[tgt[0]][tgt[1]]
        if x["fainted"] or x["status"] or "drowsy" in x:
            return
        if self.ability(tgt[0], tgt[1], x) in SLEEPLESS:
            return
        x["drowsy"] = 0

    def _accuracy(self, w: _World, role: str, a: Action, m: Mapping, tgt) -> float:
        acc = m.get("accuracy", True)
        if acc is True:
            return 1.0
        weather = w.fld.weather
        if a.move in {"thunder", "hurricane"}:
            if weather == "raindance":
                return 1.0
            if weather == "sunnyday":
                acc = 50
        if a.move == "blizzard" and weather == "snowscape":
            return 1.0
        st = w.sides[role][a.user]
        t = w.sides[tgt[0]][tgt[1]]
        stage = st["boosts"].get("accuracy", 0) - t["boosts"].get("evasion", 0)
        stage = max(-6, min(6, stage))
        mult = (3 + stage) / 3 if stage >= 0 else 3 / (3 - stage)
        ab = self.ability(role, a.user, st)
        if ab == "compoundeyes":
            mult *= 1.3
        elif ab == "hustle" and m.get("category") == "Physical":
            mult *= 0.8
        if st.get("item") == "widelens":
            mult *= 1.1
        if t.get("item") == "brightpowder":
            mult *= 0.9
        return max(0.0, min(1.0, acc / 100 * mult))

    def _inflict(self, w: _World, tgt, status: str, move: str) -> None:
        t = w.sides[tgt[0]][tgt[1]]
        if t["status"] or t["fainted"]:
            return
        types = set(self.types(tgt[0], tgt[1], t))
        if "powder" in (self.move(move).get("flags") or []) and (
            "Grass" in types
            or t.get("item") == "safetygoggles"
            or self.ability(tgt[0], tgt[1], t) == "overcoat"
        ):
            return
        if types & STATUS_TYPE_IMMUNE.get(status, set()):
            return
        if move == "thunderwave" and "Ground" in types:
            return
        if status == "slp" and w.fld.terrain == "electricterrain":
            return
        if w.fld.terrain == "mistyterrain":
            return
        if "safeguard" in w.fld.sides[tgt[0]]:
            return
        t["status"] = status
        for k in ("slp_n", "frz_n", "tox_n", "drowsy"):
            t.pop(k, None)  # a new status: its counts start, and Yawn ends

    def _drop(self, w: _World, tgt, boosts: Mapping[str, int]) -> bool:
        """Stat changes from another Pokemon's move; False if none took."""
        t = w.sides[tgt[0]][tgt[1]]
        if t["fainted"]:
            return False
        ab = self.ability(tgt[0], tgt[1], t)
        lowering = any(v < 0 for v in boosts.values())
        if lowering and (
            ab in DROP_BLOCK
            or t.get("item") == "clearamulet"
            or "mist" in w.fld.sides[tgt[0]]
        ):
            return False
        before = dict(t["boosts"])
        self._boost(t, boosts)
        if t["boosts"] == before:
            return False  # already at the limit
        if lowering and t.get("item") == "ejectpack":
            w.partial.add("eject pack")  # it would switch out; not modelled
        if lowering and ab == "defiant":
            self._boost(t, {"atk": 2})
        elif lowering and ab == "competitive":
            self._boost(t, {"spa": 2})
        return True

    def _heal(self, w: _World, role: str, idx: int, frac: float) -> None:
        st = w.sides[role][idx]
        if not st["fainted"]:
            st["hp_fraction"] = min(1.0, st["hp_fraction"] + frac)

    def _bench(self, w: _World, role: str) -> list[int]:
        return [
            j
            for j, x in enumerate(w.sides[role])
            if not x["active"]
            and not x["fainted"]
            and (x["hp_fraction"] > 0 or x.get("_brought"))
        ]

    def _self_switch(
        self,
        w: _World,
        role: str,
        idx: int,
        to: int | None = None,
        how: object = True,
        sub: int | None = None,
    ) -> list[_World]:
        """The user switches out to `to` (the Pokemon its choice brings in);
        without one, each Pokemon on the bench alike, marked partly modelled.
        Baton Pass (`how` "copyvolatile") hands over stat changes, the Perish
        count and a substitute; Shed Tail hands over a new substitute (`sub`)."""
        st = w.sides[role][idx]
        bench = self._bench(w, role)
        if st["fainted"] or not st["active"] or not bench:
            return [w]
        passed: dict = {}
        if how == "copyvolatile":
            passed = {
                "boosts": dict(st["boosts"]),
                "perish": st.get("perish"),
                "sub": st.get("sub"),
            }
        elif how == "shedtail":
            passed = {"sub": sub}
        if to in bench:
            picks = [to]
        else:
            w.partial.add("switch-in after a pivot move")
            picks = bench
        out = []
        for j in picks:
            b = w.clone(w.p / len(picks))
            self._switch(b, role, idx, j)
            new = b.sides[role][j]
            for k, v in passed.items():
                if v:
                    new[k] = dict(v) if isinstance(v, dict) else v
            out.append(b)
        return out

    def _eject_button(self, w: _World, role: str) -> list[_World]:
        """A Pokemon holding an Eject Button that this move hit switches out. Its
        player picks the Pokemon; here each on the bench alike, marked partly
        modelled. Only the first one hit goes."""
        for tgt in sorted(w.hit):
            t = w.sides[tgt[0]][tgt[1]]
            if tgt[0] == role or t["fainted"] or t.get("item") != "ejectbutton":
                continue
            bench = self._bench(w, tgt[0])
            if not bench:
                continue
            w.partial.add("eject button")
            t["item"] = ""
            out = []
            for j in bench:
                b = w.clone(w.p / len(bench))
                self._switch(b, tgt[0], tgt[1], j)
                out.append(b)
            return out
        return [w]

    def _drag(self, w: _World, tgt) -> list[_World]:
        bench = self._bench(w, tgt[0])
        t = w.sides[tgt[0]][tgt[1]]
        if t["fainted"] or not t["active"] or not bench:
            return [w]
        out = []
        for j in bench:
            b = w.clone(w.p / len(bench))
            self._switch(b, tgt[0], tgt[1], j)
            out.append(b)
        return out

    # ---------------------------------------------------------------- attack

    def _crit_chance(self, role: str, a: Action, m: Mapping, w: _World, tgt) -> float:
        if m.get("willCrit"):
            return 1.0
        t = w.sides[tgt[0]][tgt[1]]
        if self.ability(tgt[0], tgt[1], t) in CRIT_IMMUNE:
            return 0.0
        st = w.sides[role][a.user]
        stage = int(m.get("critRatio") or 1) - 1
        if self.ability(role, a.user, st) == "superluck":
            stage += 1
        if st.get("item") in {"scopelens", "razorclaw"}:
            stage += 1
        return [1 / 24, 1 / 8, 1 / 2][stage] if stage < 3 else 1.0

    def _damage(
        self, w: _World, role: str, a: Action, tgt, spread: bool, crit: bool
    ) -> dict:
        from wpa.features import _board_state

        st = w.sides[role][a.user]
        t = w.sides[tgt[0]][tgt[1]]
        f: dict[str, object] = {
            "weather": w.fld.weather or None,
            "terrain": w.fld.terrain or None,
        }
        for s in SCREENS:
            f[s] = bool(w.fld.sides[tgt[0]].get(s)) and tgt[0] != role
        f["helpinghand"] = (role, a.user) in w.helped
        down = {r: sum(bool(x["fainted"]) for x in w.sides[r]) for r in ROLES}
        key = (
            role,
            a.user,
            tgt,
            a.move,
            spread,
            crit,
            tuple(sorted(f.items())),
            _mon_key(st),
            _mon_key(t),
            down[role],
            down[tgt[0]],
            st.get("hits", 0),
        )
        if key in self._dmg:
            return self._dmg[key]
        req = damage_request(
            self.sheets[role][a.user],
            _board_state(st, down[role]),
            self.spread(role, a.user),
            self.sheets[tgt[0]][tgt[1]],
            _board_state(t, down[tgt[0]]),
            self.spread(*tgt),
            a.move,
            self.dex,
            spread=spread,
            crit=crit,
            field=f,
        )
        # Week 12: the types each has now, when changed (and always for a
        # Protean or Libero user: the calculator gives those STAB on any move)
        for side, s, who in (("attacker", st, (role, a.user)), ("defender", t, tgt)):
            if (
                s.get("types")
                or s.get("typeadd")
                or s.get("roost")
                or (side == "attacker" and self.ability(who[0], who[1], s) in PROTEAN)
            ):
                req[side]["types"] = self.types(who[0], who[1], s)
        self._dmg[key] = self.calc.run([req])[0]
        return self._dmg[key]

    def _hit_distribution(
        self, w: _World, role: str, a: Action, m: Mapping, tgt, spread: bool
    ) -> list[tuple[float, int]]:
        """(chance, damage) over crit, multi-hit count and roll; the accuracy
        check is separate."""
        c = self._crit_chance(role, a, m, w, tgt)
        out: dict[int, float] = {}
        st = w.sides[role][a.user]
        for crit, pc in ((False, 1 - c), (True, c)):
            if pc <= 0:
                continue
            ans = self._damage(w, role, a, tgt, spread, crit)
            rolls = ans.get("rolls")
            if not rolls or "error" in ans:
                w.partial.add(f"damage:{a.move}")
                continue
            hits = [(1, 1.0)]
            if m.get("multihit") == [2, 5] or m.get("multihit") == (2, 5):
                first = ans.get("first_hit") or rolls
                if self.ability(role, a.user, st) == "skilllink":
                    hits = [(5, 1.0)]
                elif st.get("item") == "loadeddice":
                    hits = [(4, 0.5), (5, 0.5)]
                else:
                    hits = list(MULTIHIT_2_5)
                for k, pk in hits:
                    for r in first:
                        d = int(r) * k
                        out[d] = out.get(d, 0.0) + pc * pk / len(first)
                continue
            for r in rolls:
                out[int(r)] = out.get(int(r), 0.0) + pc / len(rolls)
        return sorted((p, d) for d, p in out.items())

    def _attack(self, w: _World, role: str, a: Action, m: Mapping) -> list[_World]:
        mv = a.move
        if mv in {"suckerpunch", "thunderclap"} and not self._sucker_ok(w, role, a):
            return [w]
        if m.get("target") == "randomNormal" and a.target is None:
            foe = _other(role)
            foes = [
                j
                for j, x in enumerate(w.sides[foe])
                if x["active"] and not x["fainted"]
            ]
            if len(foes) == 2:  # a random opposing target: luck
                out = []
                for j in foes:
                    b = w.clone(w.p / 2)
                    out += self._attack(
                        b, role, Action(a.user, "move", move=mv, target=("foe", j)), m
                    )
                return out
        targets = self._targets(w, role, a, m)
        spread = len(targets) > 1
        out = [w]
        for tgt in targets:
            nxt = []
            for b in out:
                tt = b.sides[tgt[0]][tgt[1]]
                if (
                    tt["fainted"]
                    or not tt["active"]
                    or self._blocked(b, role, a, m, tgt, spread)
                ):
                    nxt.append(b)
                    continue
                if self._absorbs(b, role, a, m, tgt):
                    self._boost(tt, {"spa": 1})
                    nxt.append(b)
                    continue
                acc = self._accuracy(b, role, a, m, tgt)
                if acc < 1:
                    miss = b.clone(b.p * (1 - acc))
                    nxt.append(miss)
                for pd, dmg in self._grouped(b, role, a, m, tgt, spread):
                    h = b.clone(b.p * acc * pd)
                    self._apply_hit(h, role, a, m, tgt, dmg)
                    nxt.append(h)
            out = self._capped(_merge(nxt, self.resolution, self.prune))
        for b in out:
            self._after_attack(b, role, a, m)
        out = [x for b in out for x in self._secondaries(b, role, a, m)]
        out = [x for b in out for x in self._eject_button(b, role)]
        if m.get("selfSwitch"):
            out = [
                x
                for b in out
                for x in (
                    self._self_switch(b, role, a.user, a.switch_to, m["selfSwitch"])
                    if b.hit or b.subbed
                    else [b]
                )
            ]
        return out

    def _grouped(
        self, w: _World, role: str, a: Action, m: Mapping, tgt, spread: bool
    ) -> list[tuple[float, int]]:
        """The hit distribution with damage values that leave the target on the
        same hit points merged (on the `resolution` grid, if any): one board each
        instead of one per roll. Exact by default, since equal hit points are an
        equal board."""
        t = w.sides[tgt[0]][tgt[1]]
        max_hp = self.max_hp(*tgt)
        hp = round(t["hp_fraction"] * max_hp)
        groups: dict[tuple, list] = {}
        for pd, dmg in self._hit_distribution(w, role, a, m, tgt, spread):
            new = max(0, hp - dmg)
            if new == 0 and hp == max_hp and dmg > 0:
                new = (
                    1
                    if t.get("item") == "focussash"
                    or self.ability(tgt[0], tgt[1], t) == "sturdy"
                    else 0
                )
            frac = new / max_hp
            res = self.resolution
            key = (new == 0, round(frac / res) if res else new)
            g = groups.setdefault(key, [0.0, dmg])
            g[0] += pd
        return [(p, dmg) for p, dmg in groups.values()]

    def _absorbs(self, w: _World, role: str, a: Action, m: Mapping, tgt) -> bool:
        want = RODS.get(m.get("type", ""))
        if want is None or tgt == (role, a.user):
            return False
        st = w.sides[tgt[0]][tgt[1]]
        return self.ability(tgt[0], tgt[1], st) == want

    def _sucker_ok(self, w: _World, role: str, a: Action) -> bool:
        tgt = self._targets(w, role, a, self.move(a.move))
        if not tgt:
            return False
        t = tgt[0]
        if t in w.acted:
            return False
        nxt = self._pending.get(t)  # a Pokemon that just switched in chose nothing
        return nxt is not None and self.move(nxt).get("category") != "Status"

    def _apply_hit(
        self, w: _World, role: str, a: Action, m: Mapping, tgt, dmg: int
    ) -> None:
        t = w.sides[tgt[0]][tgt[1]]
        if t.get("sub") and tgt != (role, a.user) and not self._bypasses(role, a, m):
            took = min(dmg, t["sub"])  # the substitute takes it, the Pokemon none
            t["sub"] -= took
            if t["sub"] <= 0:
                t.pop("sub")
            w.dealt += took
            if dmg > 0:
                w.subbed.add(tgt)
            return
        max_hp = self.max_hp(*tgt)
        hp = round(t["hp_fraction"] * max_hp)
        new = max(0, hp - dmg)
        if new == 0 and hp == max_hp and dmg > 0:
            ab = self.ability(tgt[0], tgt[1], t)
            if t.get("item") == "focussash":
                new, t["item"] = 1, ""
                t["rev_item"] = "focussash"
            elif ab == "sturdy":
                new = 1
        dealt = hp - new
        t["hp_fraction"] = new / max_hp
        w.dealt += dealt
        if dmg > 0:
            w.hit.add(tgt)
            t["hits"] = t.get("hits", 0) + 1  # Rage Fist counts it
        if new == 0:
            self._faint(w, tgt)
        elif t.get("item") == "sitrusberry" and new <= max_hp / 2:
            t["hp_fraction"] = min(1.0, (new + max_hp // 4) / max_hp)
            t["item"], t["rev_item"] = "", "sitrusberry"
        # contact punishment
        if dealt > 0 and "contact" in (m.get("flags") or []):
            st = w.sides[role][a.user]
            ab = self.ability(tgt[0], tgt[1], t)
            if (
                self.ability(role, a.user, st) != "magicguard"
                and st.get("item") != "protectivepads"
            ):
                frac = (1 / 6 if t.get("item") == "rockyhelmet" else 0) + (
                    1 / 8 if ab in {"roughskin", "ironbarbs"} else 0
                )
                if frac:
                    self._lose(w, (role, a.user), frac)
        # what an ability does on a damaging hit (after Week 11): Spicy Spray
        # burns the attacker every time; the ones that act by chance are not
        # modelled, and say so
        if dealt > 0 and tgt != (role, a.user):
            st = w.sides[role][a.user]
            ab = self.ability(tgt[0], tgt[1], t)
            contact = (
                "contact" in (m.get("flags") or [])
                and st.get("item") != "protectivepads"
                and self.ability(role, a.user, st) != "longreach"
            )
            if ab == "spicyspray":
                self._inflict(w, (role, a.user), "brn", a.move)
            elif ab == "cursedbody" or (contact and ab in CONTACT_CHANCE):
                w.partial.add(f"ability:{ab}")
            if contact and self.ability(role, a.user, st) == "poisontouch":
                w.partial.add("ability:poisontouch")

    def _leech(self, w: _World, r: str, j: int) -> None:
        """Leech Seed at the end of the turn: an eighth of the seeded Pokemon's
        hit points, to the Pokemon in the seeder's place (Showdown's
        `getAtSlot`). Nothing while that place is empty: it fainted, this turn
        or before (-1). When it switched out this turn, the Pokemon that came
        in is healed; which one is not followed here, so marked."""
        st = w.sides[r][j]
        o, k = _other(r), st["seeded"]
        seeder = w.sides[o][k] if 0 <= k < len(w.sides[o]) else None
        if seeder is None or seeder["fainted"]:
            return
        before = st["hp_fraction"]
        self._lose(w, (r, j), 1 / 8)
        lost = (before - st["hp_fraction"]) * self.max_hp(r, j)
        if seeder["active"]:
            self._heal(w, o, k, lost / self.max_hp(o, k))
        else:
            w.partial.add("leech seed heals the Pokemon in its place")

    def _drowsy(self, w: _World) -> None:
        """Yawn: asleep at the end of the turn after it landed."""
        for r in ROLES:
            for j, st in enumerate(w.sides[r]):
                if "drowsy" not in st:
                    continue
                if st["fainted"] or not st["active"]:
                    st.pop("drowsy")
                elif st["drowsy"] >= 1:
                    st.pop("drowsy")
                    self._inflict(w, (r, j), "slp", "yawn")
                else:
                    st["drowsy"] = 1

    def _lose(self, w: _World, who, frac: float) -> None:
        st = w.sides[who[0]][who[1]]
        if st["fainted"]:
            return
        max_hp = self.max_hp(*who)
        hp = round(st["hp_fraction"] * max_hp)
        new = max(0, hp - max(1, int(max_hp * frac)))
        st["hp_fraction"] = new / max_hp
        if new == 0:
            self._faint(w, who)

    def _perish(self, w: _World) -> None:
        """Perish Song counts down after the other end-of-turn effects, in Speed
        order (Trick Room reverses it); a Pokemon reaching 0 faints. As in
        Showdown, the game ends as soon as one side has no Pokemon left, so a
        later count does not run. Speed ties keep the order of the sides."""
        counting = [
            (r, j)
            for r in ROLES
            for j, x in enumerate(w.sides[r])
            if x["active"] and not x["fainted"] and x.get("perish")
        ]
        if not counting or w.winner:
            return
        sign = 1 if w.fld.trickroom else -1
        counting.sort(key=lambda rj: sign * self._speed(w, rj[0], rj[1]))
        for r, j in counting:
            x = w.sides[r][j]
            x["perish"] -= 1
            if x["perish"] > 0:
                continue
            self._faint(w, (r, j))
            if not _left(w, r):
                w.winner = _other(r)
                return

    def _bypasses(self, role: str, a: Action, m: Mapping) -> bool:
        """Sound moves (and others flagged so) and Infiltrator get past a
        substitute."""
        flags = m.get("flags") or []
        user = self.sheets[role][a.user]
        return "bypasssub" in flags or "sound" in flags or user.ability == "infiltrator"

    def _behind_sub(self, w: _World, role: str, a: Action, m: Mapping, tgt) -> bool:
        """A status move aimed at another Pokemon's substitute does nothing."""
        t = w.sides[tgt[0]][tgt[1]]
        return (
            tgt != (role, a.user)
            and bool(t.get("sub"))
            and not self._bypasses(role, a, m)
        )

    def _substitute(self, w: _World, role: str, a: Action, m: Mapping) -> list[_World]:
        """Substitute: a quarter of the user's hit points into a substitute; fails
        at a quarter or less. Shed Tail: half of them, fails at half or less, and
        the substitute (a quarter) goes to the Pokemon that comes in."""
        import math

        st = w.sides[role][a.user]
        max_hp = self.max_hp(role, a.user)
        hp = round(st["hp_fraction"] * max_hp)
        quarter = max_hp // 4
        if a.move == "shedtail":
            cost = math.ceil(max_hp / 2)
            if st.get("sub") or hp <= cost or not self._bench(w, role):
                return [w]
            st["hp_fraction"] = (hp - cost) / max_hp
            return self._self_switch(w, role, a.user, a.switch_to, "shedtail", quarter)
        if st.get("sub") or hp <= quarter:
            return [w]
        st["hp_fraction"] = (hp - quarter) / max_hp
        st["sub"] = quarter
        return [w]

    def _faint(self, w: _World, who) -> None:
        """A Pokemon faints. If its side has none left, the game is over (Week 11;
        Showdown's checkWin): the other side wins. If both run out together, the
        last to faint wins its side the game, which is the side the first win
        went to, so that one stands."""
        st = w.sides[who[0]][who[1]]
        st.update(hp_fraction=0.0, fainted=True, active=False, boosts={}, status="")
        st.pop("perish", None)
        if w.winner is None and not _left(w, who[0]):
            w.winner = _other(who[0])

    def _after_attack(self, w: _World, role: str, a: Action, m: Mapping) -> None:
        st = w.sides[role][a.user]
        dealt = w.dealt
        if st["fainted"]:
            return
        max_hp = self.max_hp(role, a.user)
        ab = self.ability(role, a.user, st)
        if dealt > 0:
            if m.get("drain"):
                n, d = m["drain"]
                heal = dealt * n / d * (1.3 if st.get("item") == "bigroot" else 1)
                st["hp_fraction"] = min(1.0, st["hp_fraction"] + round(heal) / max_hp)
            if m.get("recoil") and ab not in {"rockhead", "magicguard"}:
                n, d = m["recoil"]
                self._lose(w, (role, a.user), max(1, round(dealt * n / d)) / max_hp)
            if st.get("item") == "lifeorb" and ab not in {"magicguard", "sheerforce"}:
                self._lose(w, (role, a.user), 0.1)
            if st.get("item") == "shellbell":
                st["hp_fraction"] = min(1.0, st["hp_fraction"] + (dealt // 8) / max_hp)
        if m.get("self") and m["self"].get("boosts") and w.hit and not st["fainted"]:
            self._boost(st, m["self"]["boosts"])
        if a.move in LOSES_TYPE and w.hit and not st["fainted"]:
            # Burn Up, Double Shock: the type is lost ("???" in its place)
            lose = LOSES_TYPE[a.move]
            base = st.get("types") or self.entry(role, a.user, st).get("types")
            st["types"] = ["???" if t == lose else t for t in base or []]
            st.pop("typeadd", None)
        if m.get("selfdestruct"):
            self._faint(w, (role, a.user))

    def _secondaries(self, w: _World, role: str, a: Action, m: Mapping) -> list[_World]:
        """Each secondary effect, with its chance, on each target this move hit
        (and the user's own boosts, once, if it hit anything)."""
        secs = [s for s in (m.get("secondaries") or []) if s]
        st = w.sides[role][a.user]
        ab = self.ability(role, a.user, st)
        if not secs or not w.hit or ab == "sheerforce":
            return [w]
        jobs: list[tuple] = []
        for s in secs:
            if s.get("self"):
                jobs.append((s, None))
            else:
                jobs += [(s, tgt) for tgt in sorted(w.hit)]
        out = [w]
        for s, tgt in jobs:
            chance = (
                min(100, (s.get("chance") or 100) * (2 if ab == "serenegrace" else 1))
                / 100
            )
            nxt = []
            for b in out:
                if tgt is not None:
                    bt = b.sides[tgt[0]][tgt[1]]
                    immune = (
                        self.ability(tgt[0], tgt[1], bt) == "shielddust"
                        or bt.get("item") == "covertcloak"
                    )
                    if bt["fainted"] or immune:
                        nxt.append(b)
                        continue
                yes = b.clone(b.p * chance) if chance < 1 else b
                if chance < 1:
                    b.p *= 1 - chance
                    nxt.append(b)
                if tgt is None:
                    if (s["self"] or {}).get("boosts") and not yes.sides[role][a.user][
                        "fainted"
                    ]:
                        self._boost(yes.sides[role][a.user], s["self"]["boosts"])
                else:
                    if s.get("status"):
                        self._inflict(yes, tgt, s["status"], a.move)
                    if s.get("boosts"):
                        self._drop(yes, tgt, s["boosts"])
                    vol = s.get("volatileStatus")
                    yt = yes.sides[tgt[0]][tgt[1]]
                    if vol == "flinch":
                        if (
                            tgt not in yes.acted
                            and self.ability(tgt[0], tgt[1], yt) not in FLINCH_IMMUNE
                        ):
                            yes.flinched.add(tgt)
                    elif vol == "confusion":
                        self._confuse(yes, tgt)
                    elif vol:
                        yes.partial.add(vol)
                nxt.append(yes)
            out = _merge(nxt, self.resolution, self.prune)
        return out

    # ----------------------------------------------------------- end of turn

    def _end_of_turn(self, w: _World) -> list[_World]:
        fld = w.fld
        for r in ROLES:
            for j, st in enumerate(w.sides[r]):
                if not st["active"] or st["fainted"]:
                    continue
                types = set(self.types(r, j, st))
                ab = self.ability(r, j, st)
                if (
                    fld.weather == "sandstorm"
                    and not types & {"Rock", "Ground", "Steel"}
                    and ab
                    not in {
                        "overcoat",
                        "sandveil",
                        "sandrush",
                        "sandforce",
                        "magicguard",
                    }
                    and st.get("item") != "safetygoggles"
                ):
                    self._lose(w, (r, j), 1 / 16)
                if st["fainted"]:
                    continue
                if (
                    fld.terrain == "grassyterrain"
                    and "Flying" not in types
                    and ab != "levitate"
                ):
                    self._heal(w, r, j, 1 / 16)
                if st.get("item") == "leftovers":
                    self._heal(w, r, j, 1 / 16)
                elif st.get("item") == "blacksludge":
                    if "Poison" in types:
                        self._heal(w, r, j, 1 / 16)
                    else:
                        self._lose(w, (r, j), 1 / 8)
                if st["fainted"]:
                    continue
                if "seeded" in st and ab != "magicguard":
                    self._leech(w, r, j)
                if st["fainted"]:
                    continue
                if ab != "magicguard":
                    if st["status"] == "brn":
                        self._lose(w, (r, j), 1 / 16)
                    elif st["status"] == "psn" and ab != "poisonheal":
                        self._lose(w, (r, j), 1 / 8)
                    elif st["status"] == "tox" and ab != "poisonheal":
                        # n/16 at the n-th end of turn, most 15/16 (`tox`)
                        n = min(15, st.get("tox_n", 0) + 1)
                        st["tox_n"] = n
                        self._lose(w, (r, j), n / 16)
                if not st["fainted"] and ab == "speedboost":
                    self._boost(st, {"spe": 1})
                if not st["fainted"] and ab == "moody":
                    w.partial.add("moody")
        self._drowsy(w)
        self._perish(w)
        # every timer counts down one
        if fld.weather:
            fld.weather_left -= 1
            if fld.weather_left <= 0:
                fld.weather, fld.weather_left = "", 0
        if fld.terrain:
            fld.terrain_left -= 1
            if fld.terrain_left <= 0:
                fld.terrain, fld.terrain_left = "", 0
        if fld.trickroom:
            fld.trickroom -= 1
        for r in ROLES:
            fld.sides[r] = {k: v - 1 for k, v in fld.sides[r].items() if v - 1 > 0}
        w.protected, w.guards, w.flinched, w.acted = set(), set(), set(), set()
        w.redirect, w.helped, w.replaced = {}, set(), {}
        w.hit, w.dealt, w.subbed = set(), 0, set()
        for r in ROLES:
            for x in w.sides[r]:
                x.pop("roost", None)
        return [w]


def _left(w: _World, role: str) -> bool:
    """Whether `role` still has a Pokemon: on the field, seen on the bench, or
    brought and not yet seen. Every player brings four (or the whole sheet, if
    shorter), so while fewer have been seen, one not yet seen is still to come:
    it cannot have fainted."""
    from wpa.decisions import BRING

    side = w.sides[role]
    known = sum(
        1
        for x in side
        if x["fainted"] or x["active"] or x["hp_fraction"] > 0 or x.get("_brought")
    )
    if known < min(BRING, len(side)):
        return True
    return any(
        not x["fainted"] and (x["active"] or x["hp_fraction"] > 0 or x.get("_brought"))
        for x in side
    )


def timers_for(f: Field, role: str, before=None):
    """The JoinedTimers a board after the turn would carry, for `role`: the
    field's timers from `f`, and the Pokemon timers of `before` counted down."""
    from wpa.timer_join import JoinedTimers

    other = _other(role)
    fld = []
    if f.weather:
        fld.append((f.weather, "field", f.weather_left, f.weather_left))
    if f.terrain:
        fld.append((f.terrain, "field", f.terrain_left, f.terrain_left))
    if f.trickroom:
        fld.append(("trickroom", "field", f.trickroom, f.trickroom))
    ours = [(k, "side", v, v) for k, v in sorted(f.sides[role].items())]
    theirs = [(k, "side", v, v) for k, v in sorted(f.sides[other].items())]
    if before is not None:
        for spans, out in ((before.ours, ours), (before.theirs, theirs)):
            for eid, target, lo, hi in spans:
                if target != "side" and lo - 1 > 0:
                    out.append((eid, target, lo - 1, hi - 1))
    return JoinedTimers(
        tuple(ours),
        tuple(theirs),
        tuple(fld),
        before.our_counters if before is not None else (),
        before.their_counters if before is not None else (),
        "turn_start",
    )


__all__ = [
    "Field",
    "Outcome",
    "Resolver",
    "field_from_timers",
    "load_moves",
    "timers_for",
    "STATS",
]
