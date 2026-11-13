"""Week 12 Task 5: hidden opponent sets.

Without the opponent's team sheet, each of their Pokemon's set is a belief, as
a player in a closed-sheet game holds it:
- what the game has shown is kept: a move used, an item shown, an ability
  announced (`features.public_sheet` gives it at each decision);
- the rest is the likeliest from the usage statistics (chaos JSON: "Moves",
  "Items", "Abilities"): the likeliest moves to make four, the likeliest
  ability, and the likeliest item that no teammate holds (the Item Clause);
- team preview shows the six species, and a Pokemon with a Mega form may hold
  its stone. The statistics count each Mega form apart, so the Mega set and the
  rest are weighed against each other: by how often each is used, and by how
  often each holds what the game has shown.

The natures stay unknown. Spreads come from the statistics alone, as in the
blank-sheet model (`features._blank_contexts`)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from wpa.team_sheets import Dex, SheetMon, to_id

# a chance for what a set never shows in the statistics: small, not zero, so a
# rare set the game has shown is still believed over none
RARE = 1e-3


@dataclass(frozen=True)
class SetUsage:
    """One species (or Mega form) in the usage statistics: how many Pokemon
    (`count`), and the chance that one has each move, holds each item ("" for
    none) and has each ability."""

    count: float
    moves: dict[str, float]
    items: dict[str, float]
    abilities: dict[str, float]


def _share(
    weights: Mapping[str, float], total: float | None = None
) -> dict[str, float]:
    got: dict[str, float] = {}
    for k, w in weights.items():
        key = "" if to_id(k) == "nothing" else to_id(k)
        if w > 0 and (key or total is None):
            got[key] = got.get(key, 0.0) + float(w)
    n = total if total is not None else sum(got.values())
    return {k: min(1.0, w / n) for k, w in got.items()} if n > 0 else {}


def set_usage(entry: Mapping) -> SetUsage:
    """One species' entry of a chaos JSON file. Each Pokemon has one ability, so
    the abilities' weights add up to the number of Pokemon; a move's chance is
    its weight over that number."""
    abilities = entry.get("Abilities") or {}
    n = float(sum(abilities.values())) or float(entry.get("Raw count") or 0)
    return SetUsage(
        n,
        _share(entry.get("Moves") or {}, n) if n > 0 else {},
        _share(entry.get("Items") or {}),
        _share(abilities),
    )


def set_usages(data: Mapping[str, Mapping]) -> dict[str, SetUsage]:
    """A chaos JSON file's "data": species id -> its usage."""
    return {to_id(name): set_usage(entry) for name, entry in data.items()}


class SetStore:
    """The sets in `usage_stats/<YYYY-MM>-<format>-1500.json`, the file chosen as
    `spreads.UsageStore` chooses it, loaded when first needed."""

    def __init__(self, folder: Path | str = "usage_stats", cutoff: int = 1500) -> None:
        self.folder = Path(folder)
        self.cutoff = cutoff
        self._cache: dict[str, dict[str, SetUsage]] = {}

    def for_game(self, tag: str, log: str) -> dict[str, SetUsage]:
        from wpa.spreads import usage_key

        key = usage_key(self.folder, tag, log, self.cutoff)
        if key is None:
            return {}
        if key not in self._cache:
            src = self.folder / f"{key}-{self.cutoff}.json"
            data = json.loads(src.read_text(encoding="utf-8"))["data"]
            self._cache[key] = set_usages(data)
        return self._cache[key]


def megas_of(dex: Dex) -> dict[str, list[tuple[str, str]]]:
    """Species id -> its Mega forms, as (stone id, Mega form id)."""
    key = id(dex)
    if key not in _MEGAS:
        out: dict[str, list[tuple[str, str]]] = {}
        for item_id, it in dex.items.items():
            stone = it.get("megaStone") or {}
            if isinstance(stone, str):  # an older dex: the stone's own species
                mega = dex.species.get(to_id(stone), {})
                stone = {mega.get("baseSpecies", ""): stone}
            for base, mega in stone.items():
                if base:
                    out.setdefault(to_id(base), []).append((item_id, to_id(mega)))
        _MEGAS[key] = out
    return _MEGAS[key]


_MEGAS: dict[int, dict[str, list[tuple[str, str]]]] = {}


@dataclass(frozen=True)
class _Variant:
    usage: SetUsage | None
    stone: str = ""  # the Mega Stone this set holds, or ""


def _variant(shown: SheetMon, sets: Mapping[str, SetUsage], dex: Dex) -> _Variant:
    """The likeliest of the species' sets in the statistics (its own, or one of
    its Mega forms') given what the game has shown."""
    cands = [_Variant(sets.get(shown.species))]
    cands += [
        _Variant(sets[mega], stone)
        for stone, mega in megas_of(dex).get(shown.species, ())
        if mega in sets
    ]
    cands = [c for c in cands if c.usage is not None and c.usage.count > 0]
    if not cands:
        return _Variant(None)

    def weight(c: _Variant) -> float:
        u = c.usage
        assert u is not None
        w = u.count
        for m in shown.moves:
            w *= max(u.moves.get(m, 0.0), RARE)
        if shown.item:
            w *= max(u.items.get(shown.item, 0.0), RARE)
        return w

    return max(cands, key=weight)


def _ability(shown: SheetMon, v: _Variant, sets, dex: Dex) -> str:
    """The ability the sheet would show: before Mega Evolving, so a Mega set's
    is the species' own."""
    if shown.ability:
        return shown.ability
    own = v.usage if not v.stone else sets.get(shown.species)
    if own is not None and own.abilities:
        return max(own.abilities, key=lambda a: own.abilities[a])
    abilities = dex.species.get(shown.species, {}).get("abilities") or {}
    return to_id(abilities.get("0", ""))


def _moves(shown: SheetMon, v: _Variant) -> tuple[str, ...]:
    out = list(shown.moves)
    u = v.usage
    if u is not None:
        ranked = sorted(u.moves, key=lambda m: -u.moves[m])
        out += [m for m in ranked if m not in out][: max(0, 4 - len(out))]
    return tuple(out)


def _items(v: _Variant) -> list[tuple[str, float]]:
    """The set's items, likeliest first; a Mega set holds its stone."""
    if v.stone:
        return [(v.stone, 1.0)]
    if v.usage is None:
        return []
    return sorted(v.usage.items.items(), key=lambda kv: -kv[1])


def belief_sheet(
    public: Sequence[SheetMon], sets: Mapping[str, SetUsage], dex: Dex
) -> tuple[SheetMon, ...]:
    """The likeliest sheet given what the game has shown of it (`public`, as
    `features.public_sheet` gives it): what was shown kept, the rest from the
    statistics. Items: each Pokemon whose item the game has not shown takes its
    likeliest item that no teammate holds, the surest first."""
    variants = [_variant(m, sets, dex) for m in public]
    taken = {m.item for m in public if m.item}
    items = {i: m.item for i, m in enumerate(public)}
    todo = [i for i, m in enumerate(public) if not m.item]
    todo.sort(key=lambda i: -(_items(variants[i]) or [("", 0.0)])[0][1])
    for i in todo:
        pick = next(
            (it for it, _p in _items(variants[i]) if not it or it not in taken), ""
        )
        items[i] = pick
        if pick:
            taken.add(pick)
    return tuple(
        SheetMon(
            m.position,
            m.species,
            items[i],
            _ability(m, variants[i], sets, dex),
            _moves(m, variants[i]),
            m.nature,
        )
        for i, m in enumerate(public)
    )


def with_used(belief: SheetMon, public: SheetMon, used: Iterable[str]) -> SheetMon:
    """The belief with moves the Pokemon used this turn put in, so the turn can
    be played out: the moves the game had shown, then the believed moves that
    stay, then the used ones; each used move takes the place of the least
    likely believed move."""
    used = [m for m in dict.fromkeys(used) if m and m not in belief.moves]
    if not used:
        return belief
    shown = [m for m in belief.moves if m in public.moves]
    guessed = [m for m in belief.moves if m not in public.moves]
    keep = guessed[: max(0, len(guessed) - len(used))]
    return replace(belief, moves=tuple(shown + keep + used))


def hidden_side(side: Sequence[Mapping], belief: Sequence[SheetMon]) -> list[dict]:
    """The opponent's board as the player sees it: an item the game has not
    shown is the believed one; one shown stays as the board has it (held, or
    gone)."""
    out = []
    for p, mon in zip(side, belief):
        q = dict(p)
        if not p.get("rev_item"):
            q["item"] = mon.item
        out.append(q)
    return out


__all__ = [
    "RARE",
    "SetStore",
    "SetUsage",
    "belief_sheet",
    "hidden_side",
    "megas_of",
    "set_usage",
    "set_usages",
    "with_used",
]
