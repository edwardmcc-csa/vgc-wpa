"""A team paste checked against the app's Stats screen (Week 13 Task 3).

    python -m wpa.team_check [my_team.txt] [--format regmb]

For each Pokemon, its six stats at level 50 from its stat points and nature,
to set beside the app's Stats screen, and anything the Champions rules do not
allow (66 stat points in all, 32 in a stat). Then what the format's usage
statistics have not seen: the advice's numbers for those are rough.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
LABELS = {
    "hp": "HP",
    "atk": "Attack",
    "def": "Defense",
    "spa": "Sp. Atk",
    "spd": "Sp. Def",
    "spe": "Speed",
}
SHORT = {
    "hp": "HP",
    "atk": "Atk",
    "def": "Def",
    "spa": "SpA",
    "spd": "SpD",
    "spe": "Spe",
}
MAX_TOTAL, MAX_STAT = 66, 32
RARE = 0.01  # on fewer teams than this: rough
TEAM_FILE = "my_team.txt"  # the PO's team, kept out of git


def default_team(
    path: Path | str | None, folder: Path | str | None = None
) -> Path | None:
    """The team paste to use: the one given, else `my_team.txt` in `folder`
    (the repo, where the commands run) if it is there."""
    if path is not None:
        return Path(path)
    mine = Path(folder or ".") / TEAM_FILE
    return mine if mine.exists() else None


def stats(mon: Mapping, dex) -> dict[str, int]:
    """Its six stats at level 50 (Champions: each stat point adds 1; perfect
    individual values; the nature's 10% up and down, rounded down)."""
    from wpa.spreads import NATURES
    from wpa.team_sheets import to_id

    base = dex.species[to_id(mon["species"])]["baseStats"]
    up, down = NATURES.get((mon.get("nature") or "").lower(), (None, None))
    points = mon.get("evs") or {}
    out = {}
    for k in STATS:
        b = (2 * base[k] + 31) // 2
        s = int(points.get(k, 0))
        if k == "hp":
            out[k] = b + 60 + s
        else:
            m = 11 if k == up else 9 if k == down else 10
            out[k] = (b + 5 + s) * m // 10
    return out


def problems(mon: Mapping) -> list[str]:
    """What the Champions rules do not allow in its stat points."""
    points = mon.get("evs") or {}
    out = []
    total = sum(int(v) for v in points.values())
    if total > MAX_TOTAL:
        out.append(f"{total} stat points ({MAX_TOTAL} at most)")
    out += [
        f"{points[k]} in {SHORT[k]} ({MAX_STAT} at most)"
        for k in STATS
        if int(points.get(k, 0)) > MAX_STAT
    ]
    return out


def unseen(
    species: Sequence[str], usage: Mapping, dex=None
) -> tuple[list[str], list[str]]:
    """Of these species ids, those not in the format's usage statistics, and
    those on under 1% of its teams (each team has six Pokemon). A species
    counts its Mega forms, which the statistics count apart (`raichumegax`);
    a regional form (`raichualola`) is another species. With the `dex`, a form
    the statistics count under its species (Sinistcha-Masterpiece) is that
    species."""
    teams = sum(float(u.count) for u in usage.values()) / 6 or 1.0

    def count(s: str) -> float:
        return sum(
            float(u.count)
            for k, u in usage.items()
            if k == s or k.startswith(s + "mega")
        )

    def base(s: str) -> str:
        from wpa.team_sheets import to_id

        b = (dex.species.get(s, {}) if dex is not None else {}).get("baseSpecies", "")
        return to_id(b) or s

    seen = {s: count(s) or count(base(s)) for s in species}
    missing = [s for s in species if not seen[s]]
    rare = [s for s in species if 0 < seen[s] / teams < RARE]
    return missing, rare


def _join(names: Sequence[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def rough_note(missing: Sequence[str], rare: Sequence[str]) -> str:
    """The advice's warning, or "" when the data has seen the whole team."""
    parts = []
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        parts.append(f"your {_join(missing)} {verb} not in this format's statistics")
    if rare:
        verb = "is" if len(rare) == 1 else "are"
        parts.append(f"your {_join(rare)} {verb} on under 1% of teams")
    if not parts:
        return ""
    it = "it" if len(missing) + len(rare) == 1 else "them"
    text = ", and ".join(parts)
    return text[0].upper() + text[1:] + f": the numbers for {it} are rough."


def report(team: str, dex, usage: Mapping | None = None) -> str:
    """Each Pokemon's stats, to set beside the app's Stats screen."""
    from wpa.replay import parse_team
    from wpa.team_sheets import to_id

    mons = parse_team(team)
    lines = []
    for m in mons:
        st = stats(m, dex)
        total = sum(int(v) for v in (m.get("evs") or {}).values())
        name = m.get("name") or m["species"]
        line = f"{name}: " + ", ".join(f"{LABELS[k]} {st[k]}" for k in STATS)
        line += f" ({total} stat points"
        bad = problems(m)
        line += ("; " + "; ".join(bad)) if bad else ""
        lines.append(line + ")")
    if usage is not None:
        missing, rare = unseen([to_id(m["species"]) for m in mons], usage, dex)
        by_id = {to_id(m["species"]): m["species"] for m in mons}
        note = rough_note([by_id[s] for s in missing], [by_id[s] for s in rare])
        if note:
            lines += ["", note]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    import json

    from wpa.hidden import set_usages
    from wpa.team_sheets import load_dexes

    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("team", nargs="?", type=Path, default=None)
    p.add_argument("--format", default="regmb", choices=("regma", "regmb"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    a = p.parse_args(argv)
    path = default_team(a.team)
    if path is None:
        raise SystemExit(f"Sorry: no team paste given, and no {TEAM_FILE} here.")
    dex = load_dexes(a.showdown)[a.format]
    files = sorted(a.usage.glob(f"*-gen9championsvgc2026{a.format}-1500.json"))
    usage = (
        set_usages(json.loads(files[-1].read_text(encoding="utf-8"))["data"])
        if files
        else None
    )
    print(report(path.read_text(encoding="utf-8"), dex, usage))


if __name__ == "__main__":  # pragma: no cover
    main()
