"""The open team sheets as features (Week 5 Task 4).

Every game in this corpus shows both open team sheets (`|showteam|`): six
Pokemon a side, each with item, ability and four moves (nature too in Reg M-B).
That is public before the first decision. This module

* reads the sheets from a log (`sheets_from_log`) into `SheetMon` records, in
  sheet order, and writes them to a side file keyed by game
  (`python -m wpa.team_sheets --out sheets.jsonl.gz`);
* turns each Pokemon into a set of *capabilities* (Tailwind, Trick Room, a
  weather, Fake Out ...) by rules written out below, using the pinned Showdown
  data for move priority and target and for Mega Evolution abilities;
* counts, for one side at one decision, how many Pokemon with each capability
  are active, seen and still standing on the bench, or not yet seen
  (`side_features`). Seen-ness comes from the state's own fields only.

Which four Pokemon a player brought is never an input: an unseen Pokemon may or
may not have been brought, and the features treat all unseen alike. Speed and
bulk numbers (EVs, IVs, and nature in Reg M-A) are not on the sheet and are not
guessed here.
"""

from __future__ import annotations

import gzip
import json
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from wpa.durations import FORMAT_MODS, showdown_for
from wpa.sheets import parse_showteam_message


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# --------------------------------------------------------------------------
# Showdown data
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Dex:
    species: dict
    moves: dict
    items: dict
    abilities: dict = field(default_factory=dict)


@lru_cache(maxsize=8)
def load_dex(showdown: Path, mod: str) -> Dex:
    script = Path(__file__).resolve().parent.parent / "scripts" / "dump_dex.js"
    out = subprocess.run(
        ["node", str(script), str(showdown), mod],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    d = json.loads(out)
    return Dex(d["species"], d["moves"], d["items"], d["abilities"])


def load_dexes(showdown: Path) -> dict[str, Dex]:
    """One Dex per format, from that format's Showdown mod, in that format's
    copy of Showdown's code (`showdown` is the June copy's folder)."""
    return {
        fmt: load_dex(showdown_for(fmt, showdown), mod)
        for fmt, mod in FORMAT_MODS.items()
    }


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SheetMon:
    position: int  # 1 to 6, sheet order
    species: str  # Showdown id, e.g. "rotomwash"
    item: str  # id
    ability: str  # id
    moves: tuple[str, ...]  # ids
    nature: str  # "" when the sheet does not show it (Reg M-A)
    # its stat points (hp atk def spa spd spe), when the sheet shows them: a
    # player's own team paste does (Week 16); an open team sheet does not
    sps: tuple[int, ...] | None = None


def _points(evs: Mapping[str, int] | None) -> tuple[int, ...] | None:
    """A sheet's stat points in stat order, or None when it shows none."""
    if not evs or not any(evs.values()):
        return None
    return tuple(int(evs.get(k, 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe"))


def sheets_from_log(log: str) -> dict[str, tuple[SheetMon, ...]]:
    """Both players' sheets from a log's `|showteam|` lines."""
    out: dict[str, tuple[SheetMon, ...]] = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            role, mons = parse_showteam_message(line)
            out[role] = tuple(
                SheetMon(
                    i,
                    to_id(m.species),
                    to_id(m.item),
                    to_id(m.ability),
                    tuple(to_id(x) for x in m.moves),
                    m.nature,
                    _points(m.evs),
                )
                for i, m in enumerate(mons, start=1)
            )
    return out


def match_to_state(sheet: Sequence[SheetMon], side: Sequence) -> list[int | None]:
    """For each Pokemon in a state's side list, its index in the sheet.

    The states list each side in sheet order, so this is normally 0..5; when
    the order differs the match is made by species.
    """
    ids = [m.species for m in sheet]
    if [p["species"] for p in side] == ids:
        return list(range(len(ids)))
    out: list[int | None] = []
    for p in side:
        hits = [i for i, s in enumerate(ids) if s == p["species"]]
        out.append(hits[0] if len(hits) == 1 else None)
    return out


# --------------------------------------------------------------------------
# Capabilities: the rules
# --------------------------------------------------------------------------

CAPABILITIES = (
    "tailwind",
    "trickroom",
    "rain",
    "sun",
    "sand",
    "snow",
    "redirection",
    "fakeout",
    "priority",
    "prankster",
    "intimidate",
    "screens",
    "spread",
    "trapping",
    "perishsong",
    "pivot",
    "escape",
)

# capability -> moves that give it
_BY_MOVE = {
    "tailwind": {"tailwind"},
    "trickroom": {"trickroom"},
    "rain": {"raindance"},
    "sun": {"sunnyday"},
    "sand": {"sandstorm"},
    "snow": {"snowscape", "chillyreception"},
    "redirection": {"followme", "ragepowder", "spotlight"},
    "fakeout": {"fakeout"},
    "screens": {"lightscreen", "reflect", "auroraveil"},
    "trapping": {"meanlook", "block", "spiderweb"},
    "perishsong": {"perishsong"},
    "pivot": {
        "uturn",
        "voltswitch",
        "flipturn",
        "partingshot",
        "teleport",
        "batonpass",
        "shedtail",
        "chillyreception",
    },
}
# capability -> abilities that give it
_BY_ABILITY = {
    "rain": {"drizzle", "primordialsea"},
    "sun": {"drought", "orichalcumpulse", "desolateland"},
    "sand": {"sandstream"},
    "snow": {"snowwarning"},
    "prankster": {"prankster"},
    "intimidate": {"intimidate"},
    "trapping": {"shadowtag", "arenatrap"},
}
_SPREAD_TARGETS = {"allAdjacentFoes", "allAdjacent"}


def form_of(mon: SheetMon, dex: Dex) -> dict:
    """The species entry, as its Mega form when it holds its own Mega Stone."""
    stone = dex.items.get(mon.item, {}).get("megaStone") or {}
    if isinstance(stone, str):
        stone = {"": stone}
    for base, mega in stone.items():
        if (not base or to_id(base) == mon.species) and to_id(mega) in dex.species:
            return dex.species[to_id(mega)]
    return dex.species.get(mon.species, {})


def abilities_of(mon: SheetMon, dex: Dex) -> set[str]:
    """The sheet ability, plus the Mega form's ability if it holds its stone."""
    out = {mon.ability}
    stone = dex.items.get(mon.item, {}).get("megaStone") or {}
    if isinstance(stone, str):
        stone = {"": stone}
    for base, mega in stone.items():
        if base and to_id(base) != mon.species:
            continue
        info = dex.species.get(to_id(mega), {})
        out |= {to_id(a) for a in (info.get("abilities") or {}).values()}
    return out


_CAP_CACHE: dict[tuple[SheetMon, int], frozenset[str]] = {}


def capabilities(mon: SheetMon, dex: Dex) -> set[str]:
    """Cached wrapper: the same Pokemon is asked about at every decision."""
    key = (mon, id(dex))
    hit = _CAP_CACHE.get(key)
    if hit is None:
        if len(_CAP_CACHE) > 200_000:
            _CAP_CACHE.clear()
        hit = _CAP_CACHE[key] = frozenset(_capabilities(mon, dex))
    return set(hit)


def _capabilities(mon: SheetMon, dex: Dex) -> set[str]:
    """What this Pokemon can do that matters to the doubles game, by rule.

    * moves: Tailwind; Trick Room; Rain Dance, Sunny Day, Sandstorm, Snowscape
      or Chilly Reception (a weather); Follow Me, Rage Powder or Spotlight
      (redirection); Fake Out; Light Screen, Reflect or Aurora Veil (screens);
    * priority: a damaging move with priority above 0, other than Fake Out;
    * spread: a damaging move that hits both foes (or everyone adjacent);
    * abilities, including a held Mega Stone's form: Drizzle or Primordial Sea
      (rain), Drought, Orichalcum Pulse or Desolate Land (sun), Sand Stream,
      Snow Warning, Prankster, Intimidate;
    * trapping: Shadow Tag or Arena Trap (Gengarite gives Mega Gengar's Shadow
      Tag), Mean Look, Block or Spider Web; Perish Song is its own capability;
    * pivot: U-turn, Volt Switch, Flip Turn, Parting Shot, Teleport, Baton Pass,
      Shed Tail, Chilly Reception;
    * escape: can leave a trap: a pivot move, a Ghost type (never trapped), or
      Shed Shell. (Arena Trap also misses Flying types and Levitate; not counted.)
    """
    caps: set[str] = set()
    moves = set(mon.moves)
    for cap, names in _BY_MOVE.items():
        if moves & names:
            caps.add(cap)
    for mid in moves:
        m = dex.moves.get(mid)
        if not m or m.get("category") == "Status":
            continue
        if m.get("priority", 0) > 0 and mid != "fakeout":
            caps.add("priority")
        if m.get("target") in _SPREAD_TARGETS:
            caps.add("spread")
    abilities = abilities_of(mon, dex)
    for cap, names in _BY_ABILITY.items():
        if abilities & names:
            caps.add(cap)
    # a way out of a trap (PO, 29 Oct): a pivot move, being a Ghost type (never
    # trapped, Mega form included), or Shed Shell
    types = set(dex.species.get(mon.species, {}).get("types") or ())
    types |= set(form_of(mon, dex).get("types") or ())
    if "pivot" in caps or "Ghost" in types or mon.item == "shedshell":
        caps.add("escape")
    return caps


# --------------------------------------------------------------------------
# Per-side features at one decision
# --------------------------------------------------------------------------


def feature_names(prefix: str) -> list[str]:
    names = [
        f"{prefix}_{c}_{w}" for c in CAPABILITIES for w in ("active", "bench", "unseen")
    ]
    names += [f"{prefix}_unseen"]
    names += [f"{prefix}_unseen_pos{k}" for k in range(1, 7)]
    names += [f"{prefix}_unseen_top4", f"{prefix}_unseen_bottom2"]
    return names


def _where(p) -> str:
    """active, bench (seen, standing, not active), unseen, or fainted."""
    if p["fainted"]:
        return "fainted"
    if p["active"]:
        return "active"
    if p["hp_fraction"] > 0:
        return "bench"
    return "unseen"


def side_features(
    sheet: Sequence[SheetMon], side: Sequence, dex: Dex, prefix: str
) -> dict[str, float]:
    """Counts for one side: capabilities by where the Pokemon is, and which
    sheet positions are still unseen.

    Reads only `species`, `hp_fraction`, `fainted` and `active` from the
    state's Pokemon records (tested). An unseen Pokemon is one the state shows
    at 0 hit points, not fainted and not active.
    """
    f = dict.fromkeys(feature_names(prefix), 0.0)
    order = match_to_state(sheet, side)
    for p, idx in zip(side, order):
        if idx is None:
            continue
        mon = sheet[idx]
        where = _where(p)
        if where == "fainted":
            continue
        for cap in capabilities(mon, dex):
            f[f"{prefix}_{cap}_{where}"] += 1
        if where == "unseen":
            f[f"{prefix}_unseen"] += 1
            if 1 <= mon.position <= 6:  # 0: sheet order not known (blanked sheet)
                f[f"{prefix}_unseen_pos{mon.position}"] = 1.0
                key = "top4" if mon.position <= 4 else "bottom2"
                f[f"{prefix}_unseen_{key}"] += 1
    return f


# --------------------------------------------------------------------------
# The side file
# --------------------------------------------------------------------------


def write_sheet_file(
    path: Path | str, games: Iterable[tuple[str, str, dict[str, tuple[SheetMon, ...]]]]
) -> int:
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for tag, fmt, sheets in games:
            rec = {
                "tag": tag,
                "format": fmt,
                "sheets": {
                    role: [
                        [
                            m.position,
                            m.species,
                            m.item,
                            m.ability,
                            list(m.moves),
                            m.nature,
                        ]
                        for m in mons
                    ]
                    for role, mons in sheets.items()
                },
            }
            f.write(json.dumps(rec) + "\n")
            n += 1
    return n


def iter_sheet_file(
    path: Path | str,
) -> Iterator[tuple[str, tuple[str, dict[str, tuple[SheetMon, ...]]]]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            sheets = {
                role: tuple(
                    SheetMon(int(pos), sp, it, ab, tuple(mv), nat)
                    for pos, sp, it, ab, mv, nat in rows
                )
                for role, rows in d["sheets"].items()
            }
            yield d["tag"], (d["format"], sheets)


def read_sheet_file(
    path: Path | str,
) -> dict[str, tuple[str, dict[str, tuple[SheetMon, ...]]]]:
    return dict(iter_sheet_file(path))


# --------------------------------------------------------------------------
# Report and command line
# --------------------------------------------------------------------------


class Prevalence:
    """How many team sheets have each capability, per format."""

    def __init__(self) -> None:
        self.teams: dict[str, int] = {}
        self.with_cap: dict[str, dict[str, int]] = {}
        self.users: dict[str, dict[str, int]] = {}

    def add(self, fmt: str, sheets: dict[str, tuple[SheetMon, ...]], dex: Dex) -> None:
        for mons in sheets.values():
            self.teams[fmt] = self.teams.get(fmt, 0) + 1
            row = self.with_cap.setdefault(fmt, {})
            users = self.users.setdefault(fmt, {})
            team_caps: set[str] = set()
            for m in mons:
                caps = capabilities(m, dex)
                team_caps |= caps
                for c in caps:
                    users[c] = users.get(c, 0) + 1
            for c in team_caps:
                row[c] = row.get(c, 0) + 1

    def describe(self) -> str:
        out = ["=== team sheet capabilities ==="]
        for fmt in sorted(self.teams):
            n = self.teams[fmt]
            out.append(f"{fmt}: {n} team sheets (two per game)")
            for c in CAPABILITIES:
                k = self.with_cap.get(fmt, {}).get(c, 0)
                u = self.users.get(fmt, {}).get(c, 0)
                out.append(
                    f"  {c:12s} on {k / n:6.1%} of teams; "
                    f"{u / n:.2f} Pokemon per team have it"
                )
        return "\n".join(out) + "\n"


def main() -> None:
    import argparse

    from wpa.formats import format_of
    from wpa.timers import iter_log_file

    parser = argparse.ArgumentParser(description="Write the team-sheet side file.")
    parser.add_argument("--logs", type=Path, default=Path("battle_logs"))
    parser.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    parser.add_argument("--out", type=Path, default=Path("sheets.jsonl.gz"))
    args = parser.parse_args()
    dexes = load_dexes(args.showdown)
    report = Prevalence()

    def games() -> Iterator[tuple[str, str, dict[str, tuple[SheetMon, ...]]]]:
        for path in sorted(args.logs.glob("logs_*.json")):
            for tag, (_ts, log) in iter_log_file(path):
                fmt = format_of(tag)
                sheets = sheets_from_log(log)
                report.add(fmt, sheets, dexes[fmt])
                yield tag, fmt, sheets

    n = write_sheet_file(args.out, games())
    print(report.describe())
    print(f"wrote {n} games to {args.out}")


if __name__ == "__main__":
    main()
