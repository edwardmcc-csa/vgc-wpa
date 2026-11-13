"""Spread estimates: what each Pokemon has invested (Week 7 Task 3).

Champions spreads are stat points (at most 32 in a stat, 66 in all) and a
nature. Nobody's are in the logs, so each Pokemon starts from Smogon's usage
statistics for its format and month (1500 cutoff), and the game refines that:
a hit's damage shows the defender's bulk and the attacker's offence, and who
moves first shows Speed. Only what happened before a decision is used for it.

Raw spreads are too many to use one by one: they differ by a point or two (it
takes a median of 123 of them to cover 90% of a Pokemon's usage). So they are
grouped into investment profiles: same nature, and each stat read as none
(0-7 points), some (8-23) or full (24-32). A profile's stat points are the
usage-weighted mean of its spreads. The candidates for a Pokemon are its most
used profiles covering 90% of its usage, at most 10.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
# share of hits taken as unexplained by any spread; chosen on the validation
# split (docs/SPREADS.md): 0, 0.02, 0.05 and 0.1 tried, 0.02 best
EPSILON = 0.02
TOTAL = 66
CAP = 32


@dataclass(frozen=True)
class Spread:
    nature: str  # id, e.g. "adamant"
    sps: tuple[int, int, int, int, int, int]  # hp atk def spa spd spe
    weight: float

    def as_dict(self) -> dict[str, int]:
        return {k: v for k, v in zip(STATS, self.sps) if v}


def _bucket(n: int) -> int:
    return 0 if n <= 7 else (2 if n >= 24 else 1)


def _legal_mean(rows: list[tuple[tuple[int, ...], float]]) -> tuple[int, ...]:
    """Usage-weighted mean stat points, floored, then the points left over given
    to the largest remainders (so the total stays what the spreads add up to)."""
    w = sum(x for _, x in rows)
    mean = [sum(s[i] * x for s, x in rows) / w for i in range(6)]
    out = [min(CAP, math.floor(m)) for m in mean]
    target = min(TOTAL, round(sum(mean)))
    order = sorted(range(6), key=lambda i: (-(mean[i] - math.floor(mean[i])), i))
    for i in order:
        if sum(out) >= target:
            break
        if out[i] < CAP and mean[i] > out[i]:
            out[i] += 1
    return tuple(out)


def profiles(
    spreads: Mapping[str, float], cover: float = 0.9, most: int = 10
) -> list[Spread]:
    """Usage statistics' "Spreads" ("Adamant:32/32/0/0/2/0" -> weight) as up to
    `most` profiles covering `cover` of the weight, weights summing to 1."""
    groups: dict[tuple, list[tuple[tuple[int, ...], float]]] = {}
    total = 0.0
    for key, w in spreads.items():
        if w <= 0:
            continue
        nature, _, nums = key.partition(":")
        sps = tuple(int(x) for x in nums.split("/"))
        if len(sps) != 6:
            continue
        nat = nature.lower()
        groups.setdefault((nat, tuple(_bucket(s) for s in sps)), []).append((sps, w))
        total += w
    ranked = sorted(
        groups.items(), key=lambda kv: (-sum(w for _, w in kv[1]), kv[0][0], kv[0][1])
    )
    out: list[tuple[str, tuple[int, ...], float]] = []
    got = 0.0
    for (nature, _), rows in ranked:
        w = sum(x for _, x in rows)
        out.append((nature, _legal_mean(rows), w))
        got += w
        if got >= cover * total or len(out) >= most:
            break
    s = sum(w for _, _, w in out)
    return [Spread(n, sps, w / s) for n, sps, w in out]  # type: ignore[arg-type]


def _id(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def load_usage(
    path: Path | str, cover: float = 0.9, most: int = 10
) -> dict[str, list[Spread]]:
    """One usage statistics file (chaos JSON) -> species id -> candidates."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))["data"]
    out = {}
    for name, entry in data.items():
        c = profiles(entry.get("Spreads") or {}, cover, most)
        if c:
            out[_id(name)] = c
    return out


def default_spread(nature: str, base_stats: Mapping[str, int] | None) -> Spread:
    """For a Pokemon the statistics do not list: full HP, full in its higher
    attacking stat, the last 2 points in Speed."""
    b = base_stats or {}
    attack = "spa" if b.get("spa", 0) > b.get("atk", 0) else "atk"
    sps: dict[str, int] = dict.fromkeys(STATS, 0)
    sps["hp"], sps["spe"], sps[attack] = 32, 2, 32
    return Spread(_id(nature) or "serious", tuple(sps[k] for k in STATS), 1.0)  # type: ignore[arg-type]


def prior(usage: Mapping[str, list[Spread]], mon, dex, base_stats=None) -> list[Spread]:
    """Candidates for one sheet Pokemon. Its Mega form's entry when it holds its
    stone (the statistics list Megas apart), else its own. A nature shown on the
    sheet (Reg M-B) keeps only spreads with that nature."""
    from wpa.team_sheets import form_of

    keys = [mon.species]
    entry = None
    if dex is not None:
        entry = form_of(mon, dex)
        if entry.get("isMega"):
            keys.insert(0, _id(entry["name"]))
    cands = next((usage[k] for k in keys if k in usage), [])
    nature = _id(mon.nature)
    if nature:
        cands = [c for c in cands if c.nature == nature]
    if not cands:
        if base_stats is None and dex is not None:
            base_stats = dex.species.get(mon.species, {}).get("baseStats")
        return [default_spread(nature, base_stats)]
    s = sum(c.weight for c in cands)
    return [Spread(c.nature, c.sps, c.weight / s) for c in cands]


# --------------------------------------------------------------------------
# What the log shows, and belief
# --------------------------------------------------------------------------


def hp_range(shown: int, max_hp: int) -> tuple[int, int]:
    """Hit points that Champions shows as `shown`/100: floor(100 * hp / max),
    at least 1 while standing."""
    lo = next(h for h in range(1, max_hp + 1) if max(1, 100 * h // max_hp) >= shown)
    hi = max(h for h in range(lo, max_hp + 1) if max(1, 100 * h // max_hp) <= shown)
    return lo, hi


def observed_chance(
    rolls: Sequence[int], max_hp: int, before: int, after: int, fainted: bool
) -> float:
    """How likely the log's before/after percentages are, over the 16 rolls and
    the hit points the 'before' percentage allows."""
    lo, hi = hp_range(before, max_hp)
    if not fainted:
        alo, ahi = hp_range(after, max_hp)
    hits = 0
    for h in range(lo, hi + 1):
        for d in rolls:
            left = h - d
            if fainted:
                hits += left <= 0
            else:
                hits += alo <= left <= ahi  # type: ignore[possibly-undefined]
    return hits / ((hi - lo + 1) * len(rolls))


class Belief:
    """Weights over one Pokemon's candidate spreads."""

    def __init__(self, candidates: Sequence[Spread]) -> None:
        self.candidates = list(candidates)
        self.weights = [c.weight for c in self.candidates]

    def update(self, likelihoods: Sequence[float]) -> None:
        new = [w * x for w, x in zip(self.weights, likelihoods)]
        s = sum(new)
        if s > 0:  # a hit no candidate explains changes nothing
            self.weights = [x / s for x in new]

    def best(self) -> Spread:
        i = max(range(len(self.weights)), key=lambda k: self.weights[k])
        return self.candidates[i]


# --------------------------------------------------------------------------
# Hits read from a log
# --------------------------------------------------------------------------

# moves whose damage does not come from the attacker's and defender's usual
# stats, or depends on what the log does not show: not used to refine
NOT_INFORMATIVE = {
    "superfang",
    "ruination",
    "naturesmadness",
    "endeavor",
    "seismictoss",
    "nightshade",
    "finalgambit",
    "counter",
    "mirrorcoat",
    "metalburst",
    "comeuppance",
    "bide",
    "beatup",
    "bodypress",
    "foulplay",
    "lastrespects",
    "ragefist",
    "psywave",
    "gyroball",
    "electroball",
    "heavyslam",
    "heatcrash",
}
SCREENS = {"reflect", "lightscreen", "auroraveil"}
# the hit's real damage is hidden (survived at 1 hit point, or taken by something else)
HIDING = {
    "focussash",
    "focusband",
    "substitute",
    "movesubstitute",
    "abilitysturdy",
    "moveendure",
    "abilitydisguise",
    "abilityiceface",
}
TERRAINS = {"electricterrain", "grassyterrain", "psychicterrain", "mistyterrain"}
ALLY_BOOSTS = {
    "battery",
    "powerspot",
    "steelyspirit",
    "flowergift",
}  # the attacker's ally


@dataclass
class Hit:
    block: int  # the block of the log it happened in (decisions there come first)
    attacker: tuple[str, int]  # (role, position on the sheet, from 0)
    defender: tuple[str, int]
    move: str
    crit: bool
    spread: bool
    before: int  # percent shown before the hit
    after: int  # percent shown after it (0 if knocked out)
    fainted: bool
    att_state: dict  # boosts, status, item, mega, hp, at the move
    def_state: dict
    # weather, terrain, screens on the defender's side, helpinghand, friendguard
    field: dict
    seq: int = 0  # line number in the log


@dataclass
class Order:
    """Two Pokemon that moved one after the other in the same priority bracket:
    the first was at least as fast then (slower, under Trick Room)."""

    block: int
    seq: int
    first: tuple[str, int]
    second: tuple[str, int]
    first_state: dict
    second_state: dict
    field: dict  # weather, terrain
    tailwind: dict  # role -> bool
    trickroom: bool


# anything that lets a Pokemon move out of its Speed order this turn
OUT_OF_ORDER = (
    "Quick Claw",
    "Quick Draw",
    "Custap",
    "After You",
    "Quash",
    "Instruct",
    "Dancer",
    "Lagging Tail",
    "Full Incense",
)
UNKNOWN_PRIORITY = {"stall", "myceliummight"}


def _shown(text: str) -> int:
    num = text.split()[0].split("/")[0]
    digits = "".join(c for c in num if c.isdigit() or c == ".")
    return int(float(digits)) if digits else 0


def hits_from_log(log: str) -> list[Hit]:
    return events_from_log(log, None)[0]


def events_from_log(log: str, dex) -> tuple[list[Hit], list[Order]]:
    """Every direct hit of a damaging move whose damage the log shows: the
    percent before and after, with the board and field at the move. Left out:
    hits that end on Focus Sash, a Substitute, Disguise or Ice Face, moves that
    hit several times, and damage from anything but the move itself.

    With `dex`, also every pair of Pokemon that moved one after the other in the
    same priority bracket, in turns where nothing lets a Pokemon move out of
    order; the Pokemon's ability and item are checked for priority changes."""
    import copy

    from wpa.decisions import _Board

    board = _Board()
    weather: str | None = None
    terrain: str | None = None
    screens: dict[str, set[str]] = {"p1": set(), "p2": set()}
    helped: set[tuple[str, int]] = set()
    forms: dict[tuple[str, int], str] = {}  # temporary forms (Stance Change)
    auras: dict[tuple[str, int], str] = {}  # Fairy Aura, Dark Aura on the field
    out: list[Hit] = []
    orders: list[Order] = []
    cur: dict | None = None
    tailwind = {"p1": False, "p2": False}
    trickroom = False
    turn_moves: list[dict] = []
    turn_text: list[str] = []
    seq = 0

    def bracket(pos: tuple[str, int], move: str) -> int | None:
        info = dex.moves.get(move) if dex is not None else None
        if info is None:
            return None
        abil = board.abilities.get(pos[0], [""] * 6)[pos[1]]
        item = board.mons[pos[0]][pos[1]]["item"]
        if abil in UNKNOWN_PRIORITY or item in (
            "quickclaw",
            "custapberry",
            "laggingtail",
            "fullincense",
        ):
            return None
        pr = int(info.get("priority", 0))
        if abil == "prankster" and info.get("category") == "Status":
            pr += 1
        elif abil == "galewings" and info.get("type") == "Flying":
            pr += board.mons[pos[0]][pos[1]]["hp"] >= 1.0
        elif abil == "triage" and "heal" in info.get("flags", []):
            pr += 3
        if move == "grassyglide" and terrain == "grassyterrain":
            pr += 1
        return pr

    def end_turn() -> None:
        if not any(x in line for line in turn_text for x in OUT_OF_ORDER):
            for a, b in zip(turn_moves, turn_moves[1:]):
                if (
                    a["pos"] != b["pos"]
                    and a["bracket"] is not None
                    and a["bracket"] == b["bracket"]
                ):
                    orders.append(
                        Order(
                            block=a["block"],
                            seq=a["seq"],
                            first=a["pos"],
                            second=b["pos"],
                            first_state=a["snap"][a["pos"]],
                            second_state=a["snap"][b["pos"]],
                            field=a["field"],
                            tailwind=a["tailwind"],
                            trickroom=a["trickroom"],
                        )
                    )
        turn_moves.clear()
        turn_text.clear()

    def finish() -> None:
        nonlocal cur
        if cur is not None and not cur["multi"]:
            for h in cur["hits"]:
                if h.defender not in cur["hidden"]:
                    h.crit = h.defender in cur["crit"]
                    out.append(h)
        cur = None

    def where(ident: str) -> tuple[str, int] | None:
        role = ident[:2]
        if role not in board.mons:
            return None
        idx = board._index(role, ident)
        return None if idx is None else (role, idx)

    def state(pos: tuple[str, int]) -> dict:
        m = board.mons[pos[0]][pos[1]]
        return {
            "boosts": dict(m["boosts"]),
            "status": m["status"],
            "item": m["item"],
            "mega": m["mega"],
            "hp": m["hp"],
            "form": forms.get(pos, ""),
            # the game so far (Week 10): Supreme Overlord, Last Respects, Rage Fist
            "fainted": sum(x["fainted"] for x in board.mons[pos[0]]),
            "hits": m.get("hits", 0),
        }

    def ally_abilities(pos: tuple[str, int]) -> set[str]:
        abil = board.abilities.get(pos[0], [])
        return {
            abil[i]
            for i, x in enumerate(board.mons[pos[0]])
            if x["active"] and not x["fainted"] and i != pos[1] and i < len(abil)
        }

    for block_i, block in enumerate(log.split("\n|\n")):
        for line in block.split("\n"):
            seq += 1
            p = line.split("|")
            if len(p) < 2:
                continue
            t = p[1]
            turn_text.append(line)
            if t in ("turn", "win"):
                end_turn()
            elif t in ("-sidestart", "-sideend") and len(p) > 3:
                if (
                    _id(p[3].removeprefix("move: ")) == "tailwind"
                    and p[2][:2] in tailwind
                ):
                    tailwind[p[2][:2]] = t == "-sidestart"
            elif t in ("-fieldstart", "-fieldend") and len(p) > 2:
                if _id(p[2].removeprefix("move: ")) == "trickroom":
                    trickroom = t == "-fieldstart"
            if t == "move" and len(p) > 3 and dex is not None:
                pos = where(p[2])
                if pos is not None and not any(x.startswith("[from]") for x in p[4:]):
                    turn_moves.append(
                        {
                            "pos": pos,
                            "bracket": bracket(pos, _id(p[3])),
                            "block": block_i,
                            "seq": seq,
                            "snap": {
                                (r, i): state((r, i))
                                for r in board.mons
                                for i in range(len(board.mons[r]))
                            },
                            "field": {"weather": weather, "terrain": terrain},
                            "tailwind": dict(tailwind),
                            "trickroom": trickroom,
                        }
                    )
            if t == "showteam":
                board.sheet(line)
            elif t in (
                "move",
                "switch",
                "drag",
                "cant",
                "turn",
                "upkeep",
                "faint",
                "-hitcount",
                "win",
            ):
                if t == "-hitcount" and cur is not None:
                    cur["multi"] = True
                if t != "faint":
                    finish()
            if t in ("switch", "drag") and len(p) > 2 and p[2][:2] in board.slots:
                old = board.slots[p[2][:2]].get(p[2][2:3])
                if old is not None:
                    forms.pop((p[2][:2], old), None)
                    auras.pop((p[2][:2], old), None)
            elif t == "faint" and len(p) > 2:
                pos = where(p[2])
                if pos:
                    forms.pop(pos, None)
                    auras.pop(pos, None)
            elif t == "-formechange" and len(p) > 3:
                pos = where(p[2])
                if pos:
                    forms[pos] = _id(p[3])
            elif (
                t == "-ability"
                and len(p) > 3
                and _id(p[3]) in ("fairyaura", "darkaura")
            ):
                pos = where(p[2])
                if pos:
                    auras[pos] = _id(p[3])
            if t == "turn":
                helped.clear()
            elif t == "-weather" and len(p) > 2:
                if "[upkeep]" not in p:
                    weather = None if p[2] == "none" else _id(p[2])
            elif t == "-fieldstart" and len(p) > 2:
                f = _id(p[2].removeprefix("move: "))
                if f in TERRAINS:
                    terrain = f
            elif t == "-fieldend" and len(p) > 2:
                if _id(p[2].removeprefix("move: ")) == terrain:
                    terrain = None
            elif t in ("-sidestart", "-sideend") and len(p) > 3:
                s = _id(p[3].removeprefix("move: "))
                role = p[2][:2]
                if s in SCREENS and role in screens:
                    (screens[role].add if t == "-sidestart" else screens[role].discard)(
                        s
                    )
            elif t == "-singleturn" and len(p) > 3 and "Helping Hand" in p[3]:
                pos = where(p[2])
                if pos:
                    helped.add(pos)
            elif t == "move" and len(p) > 3:
                pos = where(p[2])
                move = _id(p[3])
                if pos is not None and move not in NOT_INFORMATIVE:
                    spread = any(x.startswith("[spread]") for x in p[4:])
                    cur = {
                        "attacker": pos,
                        "move": move,
                        "spread": spread,
                        "att_state": state(pos),
                        # everyone as they were when the move started (a resist
                        # berry is eaten before the damage line)
                        "snap": {
                            (r, i): state((r, i))
                            for r in board.mons
                            for i in range(len(board.mons[r]))
                        },
                        "hits": [],
                        "crit": set(),
                        "hidden": set(),
                        "multi": False,
                    }
            elif cur is not None and t == "-crit" and len(p) > 2:
                pos = where(p[2])
                if pos:
                    cur["crit"].add(pos)
            elif cur is not None and t in ("-enditem", "-activate") and len(p) > 3:
                what = _id(p[3])
                if what in HIDING:
                    pos = where(p[2])
                    if pos:
                        cur["hidden"].add(pos)
            elif cur is not None and t == "-damage" and len(p) > 3:
                if any(x.startswith("[from]") for x in p[4:]):
                    pass
                else:
                    pos = where(p[2])
                    if pos and pos[0] != cur["attacker"][0]:
                        m = board.mons[pos[0]][pos[1]]
                        ally = [
                            i
                            for i, x in enumerate(board.mons[pos[0]])
                            if x["active"] and not x["fainted"] and i != pos[1]
                        ]
                        abil = board.abilities.get(pos[0], [])
                        cur["hits"].append(
                            Hit(
                                block=block_i,
                                attacker=cur["attacker"],
                                defender=pos,
                                move=cur["move"],
                                crit=False,
                                spread=cur["spread"],
                                seq=seq,
                                before=max(1, round(m["hp"] * 100)),
                                after=_shown(p[3]),
                                fainted="fnt" in p[3],
                                att_state=copy.deepcopy(cur["att_state"]),
                                def_state={**cur["snap"][pos], "hp": m["hp"]},
                                field={
                                    "weather": weather,
                                    "terrain": terrain,
                                    **{s: True for s in screens[pos[0]]},
                                    "helpinghand": cur["attacker"] in helped,
                                    "friendguard": any(
                                        abil[i] == "friendguard"
                                        for i in ally
                                        if i < len(abil)
                                    ),
                                    "fairyaura": "fairyaura" in auras.values(),
                                    "darkaura": "darkaura" in auras.values(),
                                    **{
                                        a: True
                                        for a in ally_abilities(cur["attacker"])
                                        & ALLY_BOOSTS
                                    },
                                },
                            )
                        )
            board.handle(p)
    finish()
    return out, orders


# --------------------------------------------------------------------------
# Refining from hits
# --------------------------------------------------------------------------

NATURES = {  # nature -> (raised, lowered)
    "lonely": ("atk", "def"),
    "brave": ("atk", "spe"),
    "adamant": ("atk", "spa"),
    "naughty": ("atk", "spd"),
    "bold": ("def", "atk"),
    "relaxed": ("def", "spe"),
    "impish": ("def", "spa"),
    "lax": ("def", "spd"),
    "timid": ("spe", "atk"),
    "hasty": ("spe", "def"),
    "jolly": ("spe", "spa"),
    "naive": ("spe", "spd"),
    "modest": ("spa", "atk"),
    "mild": ("spa", "def"),
    "quiet": ("spa", "spe"),
    "rash": ("spa", "spd"),
    "calm": ("spd", "atk"),
    "gentle": ("spd", "def"),
    "sassy": ("spd", "spe"),
    "careful": ("spd", "spa"),
}
# a nature that raises / lowers one stat (its other effect does not matter here)
_RAISES = {
    "atk": "adamant",
    "spa": "modest",
    "def": "bold",
    "spd": "calm",
    "spe": "jolly",
}
_LOWERS = {
    "atk": "modest",
    "spa": "adamant",
    "def": "lonely",
    "spd": "naughty",
    "spe": "brave",
}
USES_DEFENSE = {"psyshock", "psystrike", "secretsword"}
HP_MOVES = {"eruption", "waterspout", "dragonenergy", "flail", "reversal"}
STATUS_MOVES = {
    "hex",
    "infernalparade",
    "bittermalice",
}  # stronger on a statused target
WHOLE_SPREAD = {"protosynthesis", "quarkdrive"}  # boost whichever stat is highest


def _nature_for(nature: str, stat: str) -> str:
    up, down = NATURES.get(nature, ("", ""))
    if up == stat:
        return _RAISES[stat]
    if down == stat:
        return _LOWERS[stat]
    return "serious"


def _damage_mon(
    mon, st: Mapping, spread: Spread, dex, stats: tuple[str, ...], keep_hp
) -> dict:
    """One side of a damage request, keeping only what changes this damage, so
    the calculator's cache answers spreads that differ elsewhere."""
    from wpa.team_sheets import form_of

    species, ability = st.get("form") or mon.species, mon.ability
    if st.get("mega") and dex is not None:
        entry = form_of(mon, dex)
        if entry.get("isMega"):
            species = _id(entry["name"])
            ability = _id((entry.get("abilities") or {}).get("0", ability))
    if ability in WHOLE_SPREAD:
        sps, nature = spread.as_dict(), spread.nature
    else:
        sps = {k: v for k, v in spread.as_dict().items() if k in stats and v}
        nature = "serious"
        for s in stats:
            if s != "hp" and _nature_for(spread.nature, s) != "serious":
                nature = _nature_for(spread.nature, s)
    out = {
        "species": species,
        "nature": nature,
        "sps": sps,
        "item": st.get("item") or "",
        "ability": ability,
        "boosts": {k: v for k, v in (st.get("boosts") or {}).items() if k in stats},
        "status": st.get("status") or "",
        "hp": keep_hp(st.get("hp", 1.0)),
    }
    if ability == "supremeoverlord" and st.get("fainted"):
        out["fainted"] = min(5, int(st["fainted"]))  # the calculator's boost
    return out


def history_power(move: str, state: Mapping) -> int | None:
    """The power of a move the game so far decides (Week 10 Task 2), from the
    user's side's fainted count and the user's hits taken; None for the rest."""
    if move == "lastrespects":
        return 50 + 50 * int(state.get("fainted") or 0)
    if move == "ragefist":
        return min(350, 50 + 50 * int(state.get("hits") or 0))
    return None


def damage_request(
    a_mon,
    a_state: Mapping,
    a_spread: Spread,
    d_mon,
    d_state: Mapping,
    d_spread: Spread,
    move: str,
    dex,
    *,
    spread: bool = False,
    crit: bool = False,
    field: Mapping | None = None,
) -> dict:
    """One damage request, keeping only what changes this damage."""
    from wpa.damage import request

    cat = dex.moves.get(move, {}).get("category", "Physical")
    attack = "atk" if cat == "Physical" else "spa"
    defense = "def" if cat == "Physical" or move in USES_DEFENSE else "spd"

    def a_hp(h: float) -> float:
        return round(h, 2) if move in HP_MOVES else (1.0 if h > 1 / 3 else 0.33)

    def d_hp(h: float) -> float:
        return 1.0 if h >= 1.0 else 0.5

    a = _damage_mon(a_mon, a_state, a_spread, dex, (attack,), a_hp)
    d = _damage_mon(d_mon, d_state, d_spread, dex, ("hp", defense), d_hp)
    if a["status"] != "brn" and a["ability"] != "guts" and move != "facade":
        a["status"] = ""
    if move not in STATUS_MOVES:
        d["status"] = ""
    f = field or {}
    return request(
        a,
        d,
        move,
        bp=history_power(move, a_state),
        spread=spread,
        crit=crit,
        field={
            "weather": f.get("weather"),
            "terrain": f.get("terrain"),
            "reflect": f.get("reflect") and cat == "Physical",
            "lightscreen": f.get("lightscreen") and cat == "Special",
            "auroraveil": f.get("auroraveil"),
            "friendguard": f.get("friendguard"),
            "helpinghand": f.get("helpinghand"),
            **{k: f.get(k) for k in ("fairyaura", "darkaura", *sorted(ALLY_BOOSTS))},
        },
    )


def request_for(hit: Hit, sheets, dex, a_spread: Spread, d_spread: Spread) -> dict:
    return damage_request(
        sheets[hit.attacker[0]][hit.attacker[1]],
        hit.att_state,
        a_spread,
        sheets[hit.defender[0]][hit.defender[1]],
        hit.def_state,
        d_spread,
        hit.move,
        dex,
        spread=hit.spread,
        crit=hit.crit,
        field=hit.field,
    )


class GameBeliefs:
    """Each Pokemon's most likely spread, and its whole belief (each candidate
    with its weight, Week 11 Task 2), at each point of one game."""

    def __init__(self, priors: Mapping[tuple[str, int], Sequence[Spread]]) -> None:
        self.prior = {k: Belief(v).best() for k, v in priors.items() if v}
        self.prior_dists = {
            k: [(c, c.weight) for c in v] for k, v in priors.items() if v
        }
        self.changes: list[
            tuple[int, tuple[str, int], Spread]
        ] = []  # (block, mon, best)
        self.dists: list[
            tuple[int, tuple[str, int], list[tuple[Spread, float]]]
        ] = []  # (block, mon, every candidate with its weight)

    def at(self, block: int) -> dict[tuple[str, int], Spread]:
        """The most likely spreads for a decision at `block`: hits before it."""
        out = dict(self.prior)
        for b, k, s in self.changes:
            if b < block:
                out[k] = s
        return out

    def dists_at(self, block: int) -> dict[tuple[str, int], list[tuple[Spread, float]]]:
        """Each Pokemon's belief for a decision at `block`: events before it."""
        out = dict(self.prior_dists)
        for b, k, d in self.dists:
            if b < block:
                out[k] = d
        return out


def speed_request(
    mon, st: Mapping, spread: Spread, dex, field: Mapping, tailwind: bool
) -> dict:
    """The calculator's final Speed for one candidate: stat points and nature
    for Speed, stage, paralysis, Choice Scarf, Tailwind, weather and terrain
    abilities, Unburden once the item is gone."""
    from wpa.damage import TERRAIN, WEATHER

    m = _damage_mon(mon, st, spread, dex, ("spe",), lambda h: 1.0)
    m["ability_on"] = (
        m["ability"] == "unburden" and bool(mon.item) and not st.get("item")
    )
    return {
        "op": "speed",
        "mon": m,
        "field": {
            "weather": WEATHER.get(field.get("weather") or ""),
            "terrain": TERRAIN.get(field.get("terrain") or ""),
        },
        "tailwind": bool(tailwind),
    }


def _pair_matrix(ev, A: Belief, B: Belief, sheets, dex, calc):
    """P[i][j]: how likely the event is with candidate i and candidate j."""
    if isinstance(ev, Order):
        ma = sheets[ev.first[0]][ev.first[1]]
        mb = sheets[ev.second[0]][ev.second[1]]
        reqs = [
            speed_request(
                ma, ev.first_state, c, dex, ev.field, ev.tailwind[ev.first[0]]
            )
            for c in A.candidates
        ] + [
            speed_request(
                mb, ev.second_state, c, dex, ev.field, ev.tailwind[ev.second[0]]
            )
            for c in B.candidates
        ]
        ans = calc.run(reqs)
        if any("speed" not in x for x in ans):
            return None
        sa = [x["speed"] for x in ans[: len(A.candidates)]]
        sb = [x["speed"] for x in ans[len(A.candidates) :]]
        sign = -1 if ev.trickroom else 1
        return [
            [1.0 if sign * (x - y) > 0 else (0.5 if x == y else 0.0) for y in sb]
            for x in sa
        ]
    reqs = [
        request_for(ev, sheets, dex, a, d) for a in A.candidates for d in B.candidates
    ]
    answers = calc.run(reqs)
    nd = len(B.candidates)
    P = [[0.0] * nd for _ in A.candidates]
    for k, ans in enumerate(answers):
        if "error" in ans or ans.get("unknown"):
            return None
        P[k // nd][k % nd] = observed_chance(
            ans["rolls"], ans["max_hp"], ev.before, ev.after, ev.fainted
        )
    return P


def refine(
    events: Sequence,
    sheets,
    dex,
    priors,
    calc,
    measure: bool = False,
    epsilon: float = EPSILON,
    beliefs_out: dict | None = None,
):
    """Re-weight every Pokemon's candidates, event by event in the order of the
    log. A hit updates the defender (bulk) and the attacker (offence); a move
    order updates both movers (Speed); each averaged over the other's current
    weights. `epsilon` is the share of events taken as unexplained by any spread
    (something the log does not show), so that one odd event cannot rule a
    spread out. With `measure`, also scores each event from those before it:
    does the most likely pair of spreads allow it, and how likely the mixture
    makes it, starting spreads against refined ones."""
    beliefs = {k: Belief(v) for k, v in priors.items() if v}
    if beliefs_out is not None:
        beliefs_out.update(beliefs)
    g = GameBeliefs(priors)
    records = []
    for ev in sorted(events, key=lambda e: (e.block, e.seq)):
        a_key, b_key = (
            (ev.first, ev.second)
            if isinstance(ev, Order)
            else (ev.attacker, ev.defender)
        )
        if a_key not in beliefs or b_key not in beliefs:
            continue
        A, B = beliefs[a_key], beliefs[b_key]
        P = _pair_matrix(ev, A, B, sheets, dex, calc)
        if P is None:
            continue
        if measure:
            r = _score(P, A, B, priors[a_key], priors[b_key], ev)
            r["kind"] = "order" if isinstance(ev, Order) else "hit"
            records.append(r)
        nb = len(B.candidates)
        la = [sum(B.weights[j] * P[i][j] for j in range(nb)) for i in range(len(P))]
        lb = [sum(A.weights[i] * P[i][j] for i in range(len(P))) for j in range(nb)]
        la = [(1 - epsilon) * x + epsilon for x in la]
        lb = [(1 - epsilon) * x + epsilon for x in lb]
        before = (A.best(), B.best())
        A.update(la)
        B.update(lb)
        for key, b, old in ((a_key, A, before[0]), (b_key, B, before[1])):
            if b.best() != old:
                g.changes.append((ev.block, key, b.best()))
            g.dists.append((ev.block, key, list(zip(b.candidates, b.weights))))
    return g, records


def _score(P, A: Belief, D: Belief, a_prior, d_prior, h) -> dict:
    def mix(wa, wd):
        return sum(
            wa[i] * wd[j] * P[i][j] for i in range(len(wa)) for j in range(len(wd))
        )

    def best(ws):
        return max(range(len(ws)), key=lambda k: ws[k])

    pa, pd = [c.weight for c in a_prior], [c.weight for c in d_prior]
    floor = 1e-4
    return {
        "prior_fits": P[best(pa)][best(pd)] > 0.5
        if isinstance(h, Order)
        else P[best(pa)][best(pd)] > 0,
        "refined_fits": P[best(A.weights)][best(D.weights)] > 0.5
        if isinstance(h, Order)
        else P[best(A.weights)][best(D.weights)] > 0,
        "logp_prior": math.log(max(floor, mix(pa, pd))),
        "logp_refined": math.log(max(floor, mix(A.weights, D.weights))),
    }


# --------------------------------------------------------------------------
# Usage statistics on disk, and the measure
# --------------------------------------------------------------------------


def usage_key(folder: Path, tag: str, log: str, cutoff: int = 1500) -> str | None:
    """The usage statistics file for a game ("<YYYY-MM>-<format>"): the game's
    own format (Bo3 apart) and month; the nearest earlier month on file if that
    month is missing, then the nearest later one. None when there is none."""
    import datetime as dt

    fmt = tag.split("-")[0]
    i = log.find("|t:|")
    month = ""
    if i >= 0:
        ts = int(log[i + 4 : log.index("\n", i)])
        month = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m")
    files = sorted(Path(folder).glob(f"*-{fmt}-{cutoff}.json"))
    if not files:
        return None
    months = [f.name[:7] for f in files]
    earlier = [m for m in months if m <= month]
    pick = earlier[-1] if earlier else months[0]
    return f"{pick}-{fmt}"


class UsageStore:
    """`usage_stats/<YYYY-MM>-<format>-1500.json`, loaded when first needed."""

    def __init__(self, folder: Path | str = "usage_stats", cutoff: int = 1500) -> None:
        self.folder = Path(folder)
        self.cutoff = cutoff
        self._cache: dict[str, dict[str, list[Spread]]] = {}

    def for_game(self, tag: str, log: str) -> dict[str, list[Spread]]:
        """The game's own format (Bo3 apart) and month (`usage_key`)."""
        key = usage_key(self.folder, tag, log, self.cutoff)
        if key is None:
            return {}
        if key not in self._cache:
            self._cache[key] = self._load(key)
        return self._cache[key]

    def _load(self, key: str) -> dict[str, list[Spread]]:
        """The candidates of one file, kept beside it as `.cache.pkl` once
        worked out (doing it takes seconds per file); remade if the file is newer."""
        import pickle

        src = self.folder / f"{key}-{self.cutoff}.json"
        cache = self.folder / f"{key}-{self.cutoff}.cache.pkl"
        if cache.exists() and cache.stat().st_mtime >= src.stat().st_mtime:
            with cache.open("rb") as f:
                return pickle.load(f)
        out = load_usage(src)
        tmp = cache.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(out, f)
        tmp.replace(cache)
        return out


def priors_for(sheets, usage, dex) -> dict[tuple[str, int], list[Spread]]:
    return {
        (role, i): prior(usage, mon, dex)
        for role, mons in sheets.items()
        for i, mon in enumerate(mons)
    }


def main() -> None:
    import argparse
    import gzip
    import hashlib
    import sys
    import time
    from collections import defaultdict

    from wpa.damage import Calc
    from wpa.formats import format_of
    from wpa.team_sheets import load_dexes, sheets_from_log

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    p = argparse.ArgumentParser(description="Spread estimates: the measure (Task 3).")
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--one-in", type=int, default=20)
    p.add_argument("--shards", type=str, default="0-63")
    p.add_argument("--out", type=Path, default=Path("spreads_measure.jsonl"))
    p.add_argument("--epsilon", type=float, default=EPSILON)
    a = p.parse_args()
    splits = json.loads(a.splits.read_text(encoding="utf-8"))["games"]
    dexes = load_dexes(a.showdown)
    store = UsageStore(a.usage)
    lo, _, hi = a.shards.partition("-")
    done = set()
    if a.out.exists():
        done = {json.loads(x)["shard"] for x in a.out.read_text().splitlines() if x}
    start = time.time()
    with Calc() as calc, a.out.open("a", encoding="utf-8") as out:
        for shard in range(int(lo), int(hi or lo) + 1):
            if shard in done:
                continue
            agg: dict[str, dict] = defaultdict(lambda: defaultdict(float))
            path = a.logs / f"part-{shard:03d}.jsonl.gz"
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    tag = d["tag"]
                    if splits.get(tag) != "validation":
                        continue
                    if int(hashlib.sha1(tag.encode()).hexdigest(), 16) % a.one_in:
                        continue
                    fmt = format_of(tag)
                    sheets = sheets_from_log(d["log"])
                    if len(sheets) != 2:
                        continue
                    pri = priors_for(sheets, store.for_game(tag, d["log"]), dexes[fmt])
                    hits_, orders_ = events_from_log(d["log"], dexes[fmt])
                    _, recs = refine(
                        [*hits_, *orders_],
                        sheets,
                        dexes[fmt],
                        pri,
                        calc,
                        measure=True,
                        epsilon=a.epsilon,
                    )
                    s = agg[fmt]
                    s["games"] += 1
                    for r in recs:
                        k = r["kind"]
                        s[f"{k}s"] += 1
                        s[f"{k}_prior_fits"] += r["prior_fits"]
                        s[f"{k}_refined_fits"] += r["refined_fits"]
                        s[f"{k}_logp_prior"] += r["logp_prior"]
                        s[f"{k}_logp_refined"] += r["logp_refined"]
            out.write(json.dumps({"shard": shard, "formats": agg}) + "\n")
            out.flush()
            took = time.time() - start
            print(f"shard {shard}: {dict(agg)}; {calc.calls} calculations, {took:.0f}s")


def report(path: Path | str = "spreads_measure.jsonl") -> str:
    from collections import defaultdict

    tot: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for line in Path(path).read_text().splitlines():
        for fmt, s in json.loads(line)["formats"].items():
            for k, v in s.items():
                tot[fmt][k] += v
    lines = []
    for fmt, s in sorted(tot.items()):
        lines.append(f"{fmt}: {int(s['games'])} games")
        for k, what in (("hit", "allow the damage"), ("order", "put them in order")):
            n = s[f"{k}s"] or 1
            lines.append(
                f"  {int(s[f'{k}s'])} {k}s: the most likely spreads {what} in "
                f"{s[f'{k}_prior_fits'] / n:.1%} (starting) vs "
                f"{s[f'{k}_refined_fits'] / n:.1%} (refined); mean log chance "
                f"{s[f'{k}_logp_prior'] / n:.3f} vs {s[f'{k}_logp_refined'] / n:.3f}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
