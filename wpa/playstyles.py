"""Play-style archetypes as tags on a team sheet (Week 5 Task 4b). PROPOSAL.

The product owner's categories: Tailroom, Hard Trick Room, Hyper Offense,
Balance, Protect the Queen, Perish Trap, Sun, Rain, Sand and Snow. Each is a
rule over the six-Pokemon open team sheet (moves, abilities, items) and the
species' base stats and types from the pinned Showdown data. A team carries
every tag whose rule it meets; some carry none. No headline number may use these
until the product owner signs off the rules from the report
(`python -m wpa.playstyles`, docs/PLAYSTYLES.md).

Numbers that came from the product owner are marked PO. Every other cut-off is
a proposal, reported with its distribution so it can be moved.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from itertools import combinations

from wpa.team_sheets import Dex, SheetMon, abilities_of, capabilities, to_id

TAGS = (
    "tailroom",
    "hardtrickroom",
    "hyperoffense",
    "balance",
    "protectthequeen",
    "perishtrap",
    "sun",
    "rain",
    "sand",
    "snow",
)

# PO: Hyper Offense numbers (29 Oct 2026)
HO_ATTACK = 110  # base attacking stat, in the stat the Pokemon uses
HO_SPEED = 100  # base Speed of the damage dealers ...
HO_SPEED_WITH_PRIORITY_TAILWIND = 80  # ... or this, with a priority Tailwind user

# Proposals, to be moved by the PO from the report
HO_MIN_FAST_DAMAGE_DEALERS = 3
HO_MAX_DISRUPTERS = 2
HO_MAX_AVERAGE_BULK = 85.0  # mean of (HP + Def + SpD) / 3 over the six
HEAVY_SPREAD_POWER = 80  # Heat Wave 95, Hyper Voice 90; Rock Slide (75) is below
HARD_TR_MIN_SETTERS = 2
HARD_TR_MAX_AVERAGE_SPEED = 70.0
BALANCE_MIN_SIGNALS = 2
BALANCE_BULKY = 90.0  # (HP + Def + SpD) / 3 of at least one member
PIVOTS_FOR_BALANCE = 2

TRAPPING_ABILITIES = {"shadowtag", "arenatrap"}
TRAPPING_MOVES = {"meanlook", "block", "spiderweb"}
REDIRECTION = {"followme", "ragepowder"}
SETUP_MOVES = {
    "swordsdance",
    "dragondance",
    "nastyplot",
    "calmmind",
    "bulkup",
    "quiverdance",
    "shellsmash",
    "bellydrum",
    "coil",
    "shiftgear",
    "tidyup",
    "victorydance",
    "geomancy",
    "tailglow",
    "clangoroussoul",
    "filletaway",
}
PIVOT_MOVES = {
    "uturn",
    "voltswitch",
    "flipturn",
    "partingshot",
    "teleport",
    "batonpass",
    "chillyreception",
    "shedtail",
}
DISRUPTION_MOVES = {
    "fakeout",
    "taunt",
    "encore",
    "disable",
    "imprison",
    "quash",
    "willowisp",
    "thunderwave",
    "spore",
    "sleeppowder",
    "yawn",
    "hypnosis",
    "glare",
    "stunspore",
    "toxic",
    "confuseray",
    "nuzzle",
    "icywind",
    "electroweb",
    "snarl",
    "partingshot",
    "haze",
    "followme",
    "ragepowder",
    "meanlook",
    "block",
    "spiderweb",
}
DEFENSIVE_ITEMS = {"assaultvest", "eviolite", "rockyhelmet"}
CHOICE_ITEMS = {"choiceband", "choicespecs", "choicescarf"}
_SPREAD_TARGETS = {"allAdjacentFoes", "allAdjacent"}


# --------------------------------------------------------------------------
# Per-Pokemon facts
# --------------------------------------------------------------------------


def species_of(mon: SheetMon, dex: Dex) -> dict:
    """The species entry, as its Mega form when it holds its own Mega Stone."""
    stone = dex.items.get(mon.item, {}).get("megaStone") or {}
    if isinstance(stone, str):
        stone = {"": stone}
    for base, mega in stone.items():
        if (not base or to_id(base) == mon.species) and to_id(mega) in dex.species:
            return dex.species[to_id(mega)]
    return dex.species.get(mon.species, {})


def _stats(mon: SheetMon, dex: Dex) -> dict:
    return species_of(mon, dex).get("baseStats") or dict.fromkeys(
        ("hp", "atk", "def", "spa", "spd", "spe"), 0
    )


def attack_used(mon: SheetMon, dex: Dex) -> int:
    """Base Attack or Special Attack, whichever the move set mostly uses.

    Counted over damaging moves; a tie takes the higher stat; no damaging move
    gives 0 (a pure support Pokemon).
    """
    phys = spec = 0
    for mid in mon.moves:
        cat = dex.moves.get(mid, {}).get("category")
        phys += cat == "Physical"
        spec += cat == "Special"
    s = _stats(mon, dex)
    if phys == spec == 0:
        return 0
    if phys > spec:
        return s["atk"]
    if spec > phys:
        return s["spa"]
    return max(s["atk"], s["spa"])


def bulk(mon: SheetMon, dex: Dex) -> float:
    s = _stats(mon, dex)
    return (s["hp"] + s["def"] + s["spd"]) / 3


def _has_heavy_spread(mon: SheetMon, dex: Dex) -> bool:
    for mid in mon.moves:
        m = dex.moves.get(mid, {})
        if (
            m.get("category") in ("Physical", "Special")
            and m.get("target") in _SPREAD_TARGETS
            and m.get("basePower", 0) >= HEAVY_SPREAD_POWER
        ):
            return True
    return False


def _disrupts(mon: SheetMon, dex: Dex) -> bool:
    return bool(set(mon.moves) & DISRUPTION_MOVES) or bool(
        abilities_of(mon, dex) & ({"intimidate"} | TRAPPING_ABILITIES)
    )


def _types(team: Sequence[SheetMon], dex: Dex) -> set[str]:
    out: set[str] = set()
    for mon in team:
        out |= set(dex.species.get(mon.species, {}).get("types") or ())
    return out


# --------------------------------------------------------------------------
# Team measures and tags
# --------------------------------------------------------------------------


def measures(team: Sequence[SheetMon], dex: Dex) -> dict[str, float]:
    """The numbers behind the tags, for one team sheet."""
    caps = [capabilities(m, dex) for m in team]
    abil = [abilities_of(m, dex) for m in team]
    moves = [set(m.moves) for m in team]
    priority_tailwind = sum(
        1
        for c, a in zip(caps, abil)
        if "tailwind" in c and a & {"prankster", "galewings"}
    )
    speed_cut = HO_SPEED_WITH_PRIORITY_TAILWIND if priority_tailwind else HO_SPEED
    dealers = [m for m in team if attack_used(m, dex) >= HO_ATTACK]
    fast = [m for m in dealers if _stats(m, dex)["spe"] >= speed_cut]
    speeds = [_stats(m, dex)["spe"] for m in team]
    types = _types(team, dex)
    intimidate = sum(1 for a in abil if "intimidate" in a)
    pivots = sum(1 for mv in moves if mv & PIVOT_MOVES)
    redirectors = [i for i, mv in enumerate(moves) if mv & REDIRECTION]
    # the "queen": a damage dealer (PO attack number) that can set up
    setters = [
        i
        for i, mv in enumerate(moves)
        if mv & SETUP_MOVES and attack_used(team[i], dex) >= HO_ATTACK
    ]
    return {
        "damage_dealers": len(dealers),
        "fast_damage_dealers": len(fast),
        "priority_tailwind": priority_tailwind,
        "heavy_spread_users": sum(_has_heavy_spread(m, dex) for m in team),
        "disrupters": sum(_disrupts(m, dex) for m in team),
        "defensive_items": sum(m.item in DEFENSIVE_ITEMS for m in team),
        "choice_items": sum(m.item in CHOICE_ITEMS for m in team),
        "average_bulk": sum(bulk(m, dex) for m in team) / max(1, len(team)),
        "average_speed": sum(speeds) / max(1, len(speeds)),
        "trick_room_users": sum("trickroom" in c for c in caps),
        "tailwind_users": sum("tailwind" in c for c in caps),
        "core_fire_water_grass": float({"Fire", "Water", "Grass"} <= types),
        "core_steel_fairy_fighting": float({"Steel", "Fairy", "Fighting"} <= types),
        "intimidate_users": intimidate,
        "pivot_users": pivots,
        "intimidate_cycling": float(
            (intimidate >= 1 and pivots >= 1) or intimidate >= 2
        ),
        "bulky_members": sum(bulk(m, dex) >= BALANCE_BULKY for m in team),
        "queen_pairs": float(any(r != s for r in redirectors for s in setters)),
        "perish_song": float(any("perishsong" in mv for mv in moves)),
        "trappers": sum(
            bool(mv & TRAPPING_MOVES) or bool(a & TRAPPING_ABILITIES)
            for mv, a in zip(moves, abil)
        ),
    }


def _ho(s: Mapping[str, float]) -> bool:
    return (
        s["fast_damage_dealers"] >= HO_MIN_FAST_DAMAGE_DEALERS
        and s["heavy_spread_users"] >= 1
        and s["disrupters"] <= HO_MAX_DISRUPTERS
        and s["defensive_items"] == 0
        and s["average_bulk"] <= HO_MAX_AVERAGE_BULK
    )


def balance_signals(s: Mapping[str, float]) -> int:
    core = s["core_fire_water_grass"] or s["core_steel_fairy_fighting"]
    mix = s["damage_dealers"] >= 1 and s["disrupters"] >= 2 and s["bulky_members"] >= 1
    return (
        int(bool(core))
        + int(bool(s["intimidate_cycling"]))
        + int(s["pivot_users"] >= PIVOTS_FOR_BALANCE)
        + int(mix)
    )


def team_tags(team: Sequence[SheetMon], dex: Dex) -> frozenset[str]:
    """Every play-style tag this team sheet meets (possibly none)."""
    s = measures(team, dex)
    caps: set[str] = set()
    for m in team:
        caps |= capabilities(m, dex)
    tags: set[str] = set()
    if s["perish_song"] and s["trappers"]:
        tags.add("perishtrap")
    if (
        s["trick_room_users"] >= HARD_TR_MIN_SETTERS
        and s["average_speed"] <= HARD_TR_MAX_AVERAGE_SPEED
    ):
        tags.add("hardtrickroom")
    if s["tailwind_users"] and s["trick_room_users"]:
        tags.add("tailroom")
    if s["queen_pairs"]:
        tags.add("protectthequeen")
    for w in ("sun", "rain", "sand", "snow"):
        if w in caps:
            tags.add(w)
    ho = _ho(s)
    if ho:
        tags.add("hyperoffense")
    if not ho and balance_signals(s) >= BALANCE_MIN_SIGNALS:
        tags.add("balance")
    return frozenset(tags)


# --------------------------------------------------------------------------
# Hold-out with overlapping tags
# --------------------------------------------------------------------------


def unit_tags(
    games: Iterable[tuple[str, Mapping[str, frozenset[str]]]],
) -> dict[str, set[str]]:
    """A unit (a best-of-three set, or a single game) carries every tag of
    both players' teams in all its games."""
    out: dict[str, set[str]] = {}
    for unit, by_role in games:
        row = out.setdefault(unit, set())
        for tags in by_role.values():
            row |= set(tags)
    return out


def tag_holdout(
    units: Mapping[str, set[str]], held: set[str]
) -> tuple[set[str], set[str]]:
    """(kept, held out): a unit carrying any held-out tag is held out whole, so
    the model never trains or validates on a team with that tag."""
    out = {u for u, tags in units.items() if tags & held}
    return set(units) - out, out


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.teams: Counter = Counter()
        self.untagged: Counter = Counter()
        self.tag_teams: dict[str, Counter] = {}
        self.pairs: dict[str, Counter] = {}
        self.multi: Counter = Counter()
        self.units: dict[str, dict[str, set[str]]] = {}
        self.measure_hist: dict[str, dict[str, Counter]] = {}
        self.ho_conditions: dict[str, Counter] = {}
        self.weather_by: dict[str, Counter] = {}

    def add(self, fmt: str, unit: str, team: Sequence[SheetMon], dex: Dex) -> None:
        tags = team_tags(team, dex)
        s = measures(team, dex)
        self.teams[fmt] += 1
        if not tags:
            self.untagged[fmt] += 1
        if len(tags) >= 2:
            self.multi[fmt] += 1
        tt = self.tag_teams.setdefault(fmt, Counter())
        tt.update(tags)
        self.pairs.setdefault(fmt, Counter()).update(
            "+".join(p) for p in combinations(sorted(tags), 2)
        )
        self.units.setdefault(fmt, {}).setdefault(unit, set()).update(tags)
        hist = self.measure_hist.setdefault(fmt, {})
        for k in (
            "fast_damage_dealers",
            "damage_dealers",
            "heavy_spread_users",
            "disrupters",
            "defensive_items",
            "choice_items",
            "pivot_users",
            "intimidate_users",
        ):
            hist.setdefault(k, Counter())[int(s[k])] += 1
        hist.setdefault("average_bulk", Counter())[int(s["average_bulk"] // 5 * 5)] += 1
        hist.setdefault("average_speed", Counter())[
            int(s["average_speed"] // 10 * 10)
        ] += 1
        hist.setdefault("balance_signals", Counter())[balance_signals(s)] += 1
        ho = self.ho_conditions.setdefault(fmt, Counter())
        ho["fast_damage_dealers"] += (
            s["fast_damage_dealers"] >= HO_MIN_FAST_DAMAGE_DEALERS
        )
        ho["heavy_spread"] += s["heavy_spread_users"] >= 1
        ho["low_disruption"] += s["disrupters"] <= HO_MAX_DISRUPTERS
        ho["no_defensive_items"] += s["defensive_items"] == 0
        ho["low_bulk"] += s["average_bulk"] <= HO_MAX_AVERAGE_BULK
        ho["all"] += _ho(s)
        wb = self.weather_by.setdefault(fmt, Counter())
        for m in team:
            a = abilities_of(m, dex)
            caps = capabilities(m, dex)
            for w, ab in (
                ("rain", {"drizzle", "primordialsea"}),
                ("sun", {"drought", "orichalcumpulse", "desolateland"}),
                ("sand", {"sandstream"}),
                ("snow", {"snowwarning"}),
            ):
                if w in caps:
                    wb[f"{w}:{'ability' if a & ab else 'move'}"] += 1

    @property
    def tag_units(self) -> dict[str, Counter]:
        """Per format: how many units carry each tag (a unit's tags are those of
        every team in it)."""
        return {
            fmt: Counter(t for tags in units.values() for t in tags)
            for fmt, units in self.units.items()
        }

    def describe(self) -> str:
        out = ["=== play-style tags (PROPOSAL) ==="]
        for fmt in sorted(self.teams):
            n = self.teams[fmt]
            units = self.units.get(fmt, {})
            nu = len(units) or 1
            out.append(
                f"{fmt}: {n} team sheets in {len(units)} units (sets or single "
                f"games); untagged {self.untagged[fmt] / n:.1%}; two or more tags "
                f"{self.multi[fmt] / n:.1%}"
            )
            tu = self.tag_units[fmt]
            for t in TAGS:
                k = self.tag_teams.get(fmt, Counter())[t]
                out.append(
                    f"  {t:16s} {k:7d} teams ({k / n:5.1%}); held out, it would "
                    f"remove {tu[t]} units ({tu[t] / nu:.1%})"
                )
            top = self.pairs.get(fmt, Counter()).most_common(6)
            if top:
                out.append("  common pairs: " + ", ".join(f"{p} {c}" for p, c in top))
            ho = self.ho_conditions.get(fmt, Counter())
            out.append(
                "  hyper offense conditions met on their own: "
                + ", ".join(
                    f"{k} {ho[k] / n:.1%}"
                    for k in (
                        "fast_damage_dealers",
                        "heavy_spread",
                        "low_disruption",
                        "no_defensive_items",
                        "low_bulk",
                        "all",
                    )
                )
            )
            wb = self.weather_by.get(fmt, Counter())
            out.append(
                "  weather setters (Pokemon): "
                + ", ".join(f"{k} {v}" for k, v in sorted(wb.items()))
            )
            for k, hist in sorted(self.measure_hist.get(fmt, {}).items()):
                cells = ", ".join(f"{v}: {c / n:.1%}" for v, c in sorted(hist.items()))
                out.append(f"  {k}: {cells}")
        return "\n".join(out) + "\n"


def _set_id(log: str) -> str | None:
    import re

    m = re.search(
        r"<strong>Game (\d+)</strong> of <a href=\"/game-bestof3-([^\"]+)\"", log
    )
    return m.group(2) if m else None


def iter_units(logs_dir) -> Iterator[tuple[str, str]]:
    """(tag, unit id) for every game: the set id for best-of-three games."""
    from wpa.timers import iter_log_file

    for path in sorted(logs_dir.glob("logs_*.json")):
        for tag, (_ts, log) in iter_log_file(path):
            yield tag, _set_id(log) or tag


def main() -> None:
    import argparse
    from pathlib import Path

    from wpa.team_sheets import iter_sheet_file, load_dexes

    parser = argparse.ArgumentParser(description="Play-style tags (proposal).")
    parser.add_argument("--sheets", type=Path, default=Path("sheets.jsonl.gz"))
    parser.add_argument("--logs", type=Path, default=Path("battle_logs"))
    parser.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    args = parser.parse_args()
    dexes = load_dexes(args.showdown)
    units = dict(iter_units(args.logs))
    report = Report()
    for tag, (fmt, sheets) in iter_sheet_file(args.sheets):
        for team in sheets.values():
            report.add(fmt, units.get(tag, tag), team, dexes[fmt])
    print(report.describe())


if __name__ == "__main__":
    main()
