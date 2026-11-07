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
# moves whose power grows with the game so far (fainted allies, hits taken),
# which the calculator is not told
HISTORY_POWER = {"lastrespects", "ragefist"}
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
        )

    def key(self, resolution: float | None) -> tuple:
        def hp(x: float) -> float:
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
            self.dealt,
        )


def _merge(
    worlds: Sequence[_World], resolution: float | None, prune: float = 0.0
) -> list[_World]:
    """Identical boards merged (hit points to `resolution`, if given); boards
    less likely than `prune` dropped (the caller renormalises)."""
    out: dict[tuple, _World] = {}
    for w in worlds:
        if w.p <= prune:
            continue
        k = w.key(resolution)
        if k in out:
            out[k].p += w.p
        else:
            out[k] = w
    return list(out.values())


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
    ) -> None:
        self.dex, self.moves, self.calc = dex, moves, calc
        self.sheets, self.spreads = sheets, spreads
        self.resolution, self.prune, self.cap = resolution, prune, cap
        self.coarsest = resolution or 0.0  # the grid the last resolve needed
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
        return list(self.entry(role, idx, st).get("types") or [])

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
        worlds = self._switches(start, actions)
        worlds = [w2 for w in worlds for w2 in self._megas(w, actions)]
        out: list[_World] = []
        for w in worlds:
            for order, p in self._orders(w, actions):
                branch = [w.clone(w.p * p)]
                for role, act in order:
                    nxt: list[_World] = []
                    for b in branch:
                        nxt += self._act(b, role, act)
                    branch = self._capped(_merge(nxt, self.resolution, self.prune))
                out += branch
        out = _merge(
            [e for w in out for e in self._end_of_turn(w)], self.resolution, self.prune
        )
        total = sum(w.p for w in out)
        self.dropped = max(0.0, 1.0 - total)
        return [Outcome(w.p / total, w.sides, w.fld, frozenset(w.partial)) for w in out]

    def _capped(self, worlds: list[_World]) -> list[_World]:
        """Over `cap` boards: merge on a coarser hit-point grid until under it.
        Nothing is dropped; the grid used is kept in `coarsest`."""
        if self.cap is None or len(worlds) <= self.cap:
            return worlds
        res = max(self.resolution or 0.01, 0.01)
        while len(worlds) > self.cap and res < 0.5:
            res *= 2
            worlds = _merge(worlds, res)
        self.coarsest = max(self.coarsest, res)
        return worlds

    # ------------------------------------------------------------- switching

    def _speed(self, w: _World, role: str, idx: int) -> float:
        st = w.sides[role][idx]
        mon = self.sheets[role][idx]
        from wpa.features import _board_state

        key = (
            role,
            idx,
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
                self.spread(role, idx),
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

    def _switch(self, w: _World, role: str, old: int, new: int | None) -> None:
        if new is None or old is None:
            return
        o, n = w.sides[role][old], w.sides[role][new]
        if n["fainted"] or n["active"]:
            return
        o.update(active=False, boosts={}, moved=False, last_move="", protect_streak=0)
        if n["hp_fraction"] <= 0:
            n["hp_fraction"] = 1.0  # first time in
        n.update(active=True, boosts={}, moved=False, last_move="", protect_streak=0)
        w.replaced[(role, old)] = (role, new)
        self._on_entry(w, role, new)

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
        keyed = [
            ((-self._priority(w, r, a), sign * self._speed(w, r, a.user)), (r, a))
            for r, a in movers
        ]
        keyed.sort(key=lambda x: x[0])
        groups: list[list] = []
        for k, ra in keyed:
            if groups and groups[-1][0] == k:
                groups[-1][1].append(ra)
            else:
                groups.append([k, [ra]])
        perms = [list(permutations(g[1])) for g in groups]
        out = []
        for combo in product(*perms):
            p = 1.0
            for g in perms:
                p /= len(g)
            out.append(([ra for part in combo for ra in part], p))
        return out

    # ---------------------------------------------------------------- acting

    def _current(self, w: _World, who: tuple[str, int]) -> tuple[str, int]:
        while who in w.replaced:
            who = w.replaced[who]
        return who

    def _act(self, w: _World, role: str, a: Action) -> list[_World]:
        st = w.sides[role][a.user]
        if st["fainted"] or not st["active"]:
            return [w]
        if (role, a.user) in w.flinched:
            w.acted.add((role, a.user))
            return [w]
        # can it move at all?
        if st["status"] == "slp":
            w.partial.add("sleep")
            w.acted.add((role, a.user))
            return [w]
        if st["status"] == "frz":
            thaw, stay = w.clone(w.p * 0.2), w
            stay.p *= 0.8
            thaw.sides[role][a.user]["status"] = ""
            stay.acted.add((role, a.user))
            return [stay, *self._use(thaw, role, a)]
        if st["status"] == "par":
            stuck, go = w.clone(w.p * 0.25), w
            go.p *= 0.75
            stuck.acted.add((role, a.user))
            return [stuck, *self._use(go, role, a)]
        return self._use(w, role, a)

    def _use(self, w: _World, role: str, a: Action) -> list[_World]:
        mv = a.move
        m = self.move(mv)
        st = w.sides[role][a.user]
        protect_used = mv in PROTECT_LIKE
        first_turn = not st["moved"]
        st["moved"], st["last_move"] = True, mv
        w.hit, w.dealt = set(), 0
        if not protect_used:
            st["protect_streak"] = 0
        w.acted.add((role, a.user))
        if not m:
            w.partial.add(f"move:{mv}")
            return [w]
        if protect_used:
            return self._protect(w, role, a)
        if "charge" in (m.get("flags") or []):
            sunny = mv in {"solarbeam", "solarblade"} and w.fld.weather == "sunnyday"
            rainy = mv == "electroshot" and w.fld.weather == "raindance"
            if mv in {"electroshot", "meteorbeam"}:
                self._boost(st, {"spa": 1})
            if not (sunny or rainy or st.get("item") == "powerherb"):
                w.partial.add("charging")
                return [w]
            if st.get("item") == "powerherb" and not (sunny or rainy):
                st["item"] = ""
        if "semiinvulnerable" in (m.get("flags") or []) or mv in {
            "fly",
            "dig",
            "dive",
            "bounce",
            "phantomforce",
            "shadowforce",
        }:
            w.partial.add("semi-invulnerable")
            return [w]
        if mv in {"fakeout", "firstimpression"} and not first_turn:
            return [w]  # it works only on the Pokemon's first turn in
        if self._queenly(w, role, a, m):
            return [w]  # Armor Tail, Dazzling, Queenly Majesty: the move fails
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
            return [w]
        if m.get("terrain"):
            self._set_terrain(w, to_id(m["terrain"]), st.get("item") or "")
            return [w]
        if m.get("pseudoWeather") == "trickroom":
            w.fld.trickroom = 0 if w.fld.trickroom else 5
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
        )
        if not handled:
            w.partial.add(f"move:{mv}")
            return [w]
        out = [w]
        prankster = self.ability(role, a.user, st) == "prankster"
        for tgt in targets:
            nxt = []
            for b in out:
                if self._blocked(b, role, a, m, tgt, len(targets) > 1):
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
                    nxt.append(b)
                if m.get("status"):
                    self._inflict(hit, tgt, m["status"], mv)
                if m.get("boosts"):
                    self._drop(hit, tgt, m["boosts"])
                nxt.append(hit)
            out = nxt
        if m.get("selfSwitch"):
            out = [x for b in out for x in self._self_switch(b, role, a.user)]
        if m.get("forceSwitch"):
            # no target left (it fell earlier in the turn): the move fails, the
            # board stays
            out = [
                x for b in out for x in (self._drag(b, targets[0]) if targets else [b])
            ]
        return out

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

    def _drop(self, w: _World, tgt, boosts: Mapping[str, int]) -> None:
        t = w.sides[tgt[0]][tgt[1]]
        if t["fainted"]:
            return
        ab = self.ability(tgt[0], tgt[1], t)
        lowering = any(v < 0 for v in boosts.values())
        if lowering and (
            ab in DROP_BLOCK
            or t.get("item") == "clearamulet"
            or "mist" in w.fld.sides[tgt[0]]
        ):
            return
        self._boost(t, boosts)
        if lowering and ab == "defiant":
            self._boost(t, {"atk": 2})
        elif lowering and ab == "competitive":
            self._boost(t, {"spa": 2})

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

    def _self_switch(self, w: _World, role: str, idx: int) -> list[_World]:
        st = w.sides[role][idx]
        bench = self._bench(w, role)
        if st["fainted"] or not st["active"] or not bench:
            return [w]
        w.partial.add("switch-in after a pivot move")
        out = []
        for j in bench:
            b = w.clone(w.p / len(bench))
            self._switch(b, role, idx, j)
            out.append(b)
        return out

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
        )
        if key in self._dmg:
            return self._dmg[key]
        req = damage_request(
            self.sheets[role][a.user],
            _board_state(st),
            self.spread(role, a.user),
            self.sheets[tgt[0]][tgt[1]],
            _board_state(t),
            self.spread(*tgt),
            a.move,
            self.dex,
            spread=spread,
            crit=crit,
            field=f,
        )
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
        if mv in HISTORY_POWER:
            w.partial.add(f"power:{mv}")
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
        if m.get("selfSwitch"):
            out = [x for b in out for x in self._self_switch(b, role, a.user)]
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

    def _faint(self, w: _World, who) -> None:
        st = w.sides[who[0]][who[1]]
        st.update(hp_fraction=0.0, fainted=True, active=False, boosts={}, status="")

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
                if ab != "magicguard":
                    if st["status"] == "brn":
                        self._lose(w, (r, j), 1 / 16)
                    elif st["status"] == "psn" and ab != "poisonheal":
                        self._lose(w, (r, j), 1 / 8)
                    elif st["status"] == "tox" and ab != "poisonheal":
                        w.partial.add("toxic counter")
                        self._lose(w, (r, j), 1 / 8)
                if not st["fainted"] and ab == "speedboost":
                    self._boost(st, {"spe": 1})
                if not st["fainted"] and ab == "moody":
                    w.partial.add("moody")
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
        w.hit, w.dealt = set(), 0
        return [w]


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
