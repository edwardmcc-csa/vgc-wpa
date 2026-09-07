"""Splits parsed games into named buckets (train/test/etc.) by best-of-3
set, per DEFINITIONS.md #13: all trajectories from a set go to the same
side, and no exact team pairing crosses a split boundary either - a
set-only split still lets the identical matchup recur on both sides.

Additive only: grouping-key logic, no modelling. `archetype_fn` is an
extension point for M4's archetype-level holdout (DEFINITIONS #13), not an
implementation of one - no archetype classifier exists yet, and building
one is a modelling decision out of scope this week.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from wpa.sheets import parse_showteam_message

TeamPairing = frozenset[frozenset[str]]


@dataclass(frozen=True)
class GameRecord:
    """One game: which set it belongs to, and the (order-independent) pair
    of team compositions that played it."""

    tag: str
    set_id: str
    team_pairing: TeamPairing


def team_pairing_from_log(log: str) -> TeamPairing:
    """Extract the order-independent pair of team compositions from a
    battle log's two `|showteam|` lines."""
    sides = []
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            _role, sheets = parse_showteam_message(line)
            sides.append(frozenset(s.species for s in sheets))
    if len(sides) != 2:
        raise ValueError(f"expected exactly 2 |showteam| lines, found {len(sides)}")
    return frozenset(sides)


def _grouping_key(
    pairing: TeamPairing, archetype_fn: Callable[[frozenset[str]], str] | None
) -> str:
    if archetype_fn is None:
        teams = pairing
    else:
        teams = frozenset(frozenset([archetype_fn(team)]) for team in pairing)
    # Canonical, order-independent string so the same pairing/archetype
    # pair always hashes to the same bucket regardless of set membership.
    return "|".join(sorted("+".join(sorted(team)) for team in teams))


def _bucket_for(key: str, ratios: dict[str, float], seed: int) -> str:
    """Deterministic seeded assignment of `key` to one of ratios' buckets."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    names = list(ratios.keys())
    cumulative = 0.0
    for name in names[:-1]:
        cumulative += ratios[name]
        if fraction < cumulative:
            return name
    return names[-1]


class _UnionFind:
    """Merges groups that must land in the same split bucket. Not just a
    convenience: set id and team pairing are two independent grouping
    requirements that happen to coincide in real data (teams persist
    across a set), but nothing here should rely on that coincidence."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def _find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[ra] = rb

    def group_key(self, x: str) -> str:
        return self._find(x)


def split_by_set(
    records: list[GameRecord],
    ratios: dict[str, float],
    seed: int = 0,
    *,
    archetype_fn: Callable[[frozenset[str]], str] | None = None,
) -> dict[str, str]:
    """Assign every game's tag to a split bucket.

    Every game sharing a set id, or sharing an exact team pairing (even
    across different sets - the same matchup recurring), lands in the same
    bucket - enforced by union-find over both keys jointly, not by relying
    on set id and team pairing happening to coincide. If `archetype_fn` is
    given, games are additionally grouped whenever both sides' archetypes
    match (M4's archetype-level holdout extension point - see module
    docstring).
    """
    uf = _UnionFind()
    pairing_key_of: dict[str, str] = {}
    for record in records:
        set_key = f"set:{record.set_id}"
        pairing_key = f"pairing:{_grouping_key(record.team_pairing, archetype_fn)}"
        pairing_key_of[record.tag] = pairing_key
        uf.union(set_key, pairing_key)

    tags_by_group: dict[str, list[str]] = {}
    for record in records:
        group = uf.group_key(pairing_key_of[record.tag])
        tags_by_group.setdefault(group, []).append(record.tag)

    assignment: dict[str, str] = {}
    for group, tags in tags_by_group.items():
        bucket = _bucket_for(group, ratios, seed)
        for tag in tags:
            assignment[tag] = bucket
    return assignment
