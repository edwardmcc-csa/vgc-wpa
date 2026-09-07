"""Parses `|showteam|` protocol lines field by field.

Additive only: field order and semantics are taken directly from
pokemon-showdown's own packed-team spec
(pokemon-showdown/sim/teams.ts's `Team.unpack`), not guessed or reverse
engineered from examples - that file is read, never edited. See
docs/SHEET-FIELDS.md for what the confirmed-populated/confirmed-empty
fields are across the real corpus.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PokemonSheet:
    """One Pokemon's open-team-sheet entry, per Team.unpack's field order."""

    name: str
    species: str
    item: str
    ability: str
    moves: list[str]
    nature: str
    evs: dict[str, int] | None
    gender: str
    ivs: dict[str, int] | None
    shiny: bool
    level: int
    happiness: int | None
    hp_type: str | None
    pokeball: str | None
    gigantamax: bool
    dynamax_level: int | None
    tera_type: str | None


_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")


def _parse_one(entry: str) -> PokemonSheet:
    """Parse one Pokemon's packed-team block (the part of `|showteam|`
    between `]` separators), field by field per Team.unpack in
    pokemon-showdown/sim/teams.ts.
    """
    fields = entry.split("|")
    name = fields[0]
    species = fields[1] or name
    item = fields[2]
    ability = fields[3]
    moves = fields[4].split(",") if fields[4] else []
    nature = fields[5]
    evs = None
    if len(fields) > 6 and fields[6]:
        parts = fields[6].split(",")
        evs = {k: (int(v) if v else 0) for k, v in zip(_STAT_KEYS, parts)}
    gender = fields[7] if len(fields) > 7 else ""
    ivs = None
    if len(fields) > 8 and fields[8]:
        parts = fields[8].split(",")
        ivs = {k: (int(v) if v else 31) for k, v in zip(_STAT_KEYS, parts)}
    shiny = bool(fields[9]) if len(fields) > 9 else False
    level = int(fields[10]) if len(fields) > 10 and fields[10] else 100

    happiness = hp_type = pokeball = dynamax_level = tera_type = None
    gigantamax = False
    if len(fields) > 11 and fields[11]:
        misc = fields[11].split(",")
        happiness = int(misc[0]) if len(misc) > 0 and misc[0] else 255
        hp_type = misc[1] if len(misc) > 1 and misc[1] else None
        pokeball = misc[2] if len(misc) > 2 and misc[2] else None
        gigantamax = bool(misc[3]) if len(misc) > 3 else False
        dynamax_level = int(misc[4]) if len(misc) > 4 and misc[4] else 10
        tera_type = misc[5] if len(misc) > 5 and misc[5] else None

    return PokemonSheet(
        name=name,
        species=species,
        item=item,
        ability=ability,
        moves=moves,
        nature=nature,
        evs=evs,
        gender=gender,
        ivs=ivs,
        shiny=shiny,
        level=level,
        happiness=happiness,
        hp_type=hp_type,
        pokeball=pokeball,
        gigantamax=gigantamax,
        dynamax_level=dynamax_level,
        tera_type=tera_type,
    )


def parse_showteam_message(line: str) -> tuple[str, list[PokemonSheet]]:
    """Parse one `|showteam|ROLE|<packed team>` protocol line.

    Returns (role, sheets) - one PokemonSheet per Pokemon on that side.
    """
    _, _, role, packed = line.split("|", 3)
    entries = packed.split("]")
    return role, [_parse_one(e) for e in entries]
