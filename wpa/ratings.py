"""Ladder ratings, as a game's log shows them (Week 15).

A rated ladder game's log names each player with their rating:
`|player|p1|NAME|AVATAR|RATING`. Most Reg M-C games show both (about 85%);
the replay page's one number is shown on about a third. The rating bands are
the ones every report uses.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

BANDS = (
    (0, 1100, "under 1100"),
    (1100, 1300, "1100 to 1299"),
    (1300, 1500, "1300 to 1499"),
    (1500, 10**6, "1500 and up"),
)
UNRATED = "no rating shown"

_PLAYER = re.compile(r"^\|player\|(p[12])\|[^|\n]*\|[^|\n]*\|(\d+)[ \t\r]*$", re.M)


def ratings_from_log(log: str) -> tuple[int | None, int | None]:
    """p1's and p2's ladder ratings, from the log's `|player|` lines."""
    got = {m.group(1): int(m.group(2)) for m in _PLAYER.finditer(log)}
    return got.get("p1"), got.get("p2")


def game_rating(ratings: tuple[int | None, int | None]) -> int | None:
    """A game's rating: its two players' average, when the log shows both."""
    a, b = ratings
    return None if a is None or b is None else round((a + b) / 2)


def band(rating: int | None) -> str:
    if not rating:
        return UNRATED
    return next(name for lo, hi, name in BANDS if lo <= rating < hi)


def ordered_bands(names: Iterable[str]) -> list[str]:
    order = [name for _lo, _hi, name in BANDS] + [UNRATED]
    present = set(names)
    return [b for b in order if b in present]
