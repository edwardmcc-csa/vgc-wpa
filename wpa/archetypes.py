"""Team archetypes by leader clustering (Week 4 Task 3, PROPOSAL).

DEFINITIONS section 13 requires holding out whole team archetypes. No
definition existed. This is a proposal for the product owner to sign off;
no headline number may use it until then.

Definition
----------
Within one format, rank the teams by how many units (sets or single games)
use them, most used first, ties broken by the species list. Walk that list:
a team joins the earliest leader it shares at least `min_shared` species
with (default 4 of 6); otherwise it becomes a new leader. The archetype is
named after its leader's species.

Why leader clustering and not "link any two teams that share species"
(single linkage): the top species appear on about a third of all teams, so
linking chains teams together. Measured on the real corpus, single linkage
puts 73% of M-A team appearances in one archetype at 5 shared species and
95% at 4. Leader clustering bounds how far a team can be from its archetype:
every member shares at least `min_shared` species with its leader. The
price is that two members of one archetype can share as few as
2 * min_shared - 6 species with each other, and that the result depends on
the usage ranking, so it is a function of the whole corpus.

The species are the only team information in a BattleState, so items, moves
and play style (Trick Room, Tailwind, ...) are not part of this definition.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping

DEFAULT_MIN_SHARED = 4
TEAM_SIZE = 6


def archetype_id(leader_team: tuple[str, ...]) -> str:
    """The archetype's name: its leader's species, joined."""
    return "+".join(leader_team)


def check_min_shared(min_shared) -> int:
    if (
        isinstance(min_shared, bool)
        or not isinstance(min_shared, int)
        or not 1 <= min_shared <= TEAM_SIZE
    ):
        raise ValueError(
            f"min_shared must be a whole number from 1 to {TEAM_SIZE}, "
            f"got {min_shared!r}"
        )
    return min_shared


def build_archetypes(
    usage: Mapping[tuple[str, ...], int], min_shared: int = DEFAULT_MIN_SHARED
) -> dict[tuple[str, ...], str]:
    """Map every team (a sorted tuple of six species) to its archetype id.

    `usage` is how many units use each team. Deterministic: independent of
    the order the teams are supplied in.
    """
    check_min_shared(min_shared)
    for team in usage:
        if len(team) != TEAM_SIZE or len(set(team)) != TEAM_SIZE:
            raise ValueError(f"a team is {TEAM_SIZE} different species, got {team!r}")

    leaders: list[tuple[str, ...]] = []
    leaders_with: dict[str, list[int]] = defaultdict(list)
    result: dict[tuple[str, ...], str] = {}
    for team in sorted(usage, key=lambda t: (-usage[t], t)):
        shared: Counter[int] = Counter()
        for species in team:
            for index in leaders_with[species]:
                shared[index] += 1
        joined = min((i for i, n in shared.items() if n >= min_shared), default=None)
        if joined is None:
            joined = len(leaders)
            leaders.append(team)
            for species in team:
                leaders_with[species].append(joined)
        result[team] = archetype_id(leaders[joined])
    return result
