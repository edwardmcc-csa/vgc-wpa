"""Week 18, Task 4: the step that ran past the deadline. In the Week 17 gate,
the hard limit answered 9 times, and each time the search ran on 20 to 25
seconds after it. Replaying those positions found the step: one pair of plays
resolved can take 15 seconds (here; longer on a busy computer), and the clock
was only looked at between pairs. Now the resolver looks at a hard stop (the
time is up, or the request has passed) as it goes; a pair cut short is left
unvalued, like the pairs after it."""

from __future__ import annotations

import pytest

from tests.test_resolver import ROOT, SHEETS, SPREADS, board
from wpa import attribution as A
from wpa import bot as B
from wpa import resolver as R
from wpa.choices import Action

needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


@pytest.fixture(scope="module")
def parts():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    c = DM.Calc()
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    yield dex, R.load_moves(ROOT / "pokemon-showdown", "championsregma"), c
    c.close()


def _rv(parts):
    dex, moves, calc = parts
    return R.Resolver(dex, moves, calc, SHEETS, SPREADS)


def _acts():
    return {
        "p1": (
            Action(0, "move", move="stoneedge", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
    }


@needs_showdown
def test_a_resolve_stops_part_way_when_told(parts):
    rv = _rv(parts)
    looks = []

    def hard():
        looks.append(1)
        return len(looks) > 2

    with pytest.raises(R.Stopped):
        rv.resolve(board(), R.Field(), _acts(), stop=hard)
    assert len(looks) == 3  # it looked as it went, and stopped at once


@needs_showdown
def test_a_resolve_not_told_to_stop_is_as_before(parts):
    got = _rv(parts).resolve(board(), R.Field(), _acts(), stop=lambda: False)
    before = _rv(parts).resolve(board(), R.Field(), _acts())
    assert sorted(round(o.prob, 12) for o in got) == sorted(
        round(o.prob, 12) for o in before
    )


class _Out:
    def __init__(self) -> None:
        self.prob, self.winner = 1.0, None


class _SlowResolver:
    """The third pair's resolve is cut short by the hard stop."""

    def __init__(self) -> None:
        self.n = 0

    def resolve(self, sides, fld, choices, stop=None):
        self.n += 1
        if self.n == 3 and stop is not None and stop():
            raise R.Stopped()
        return [_Out()]


def _j(k):
    return (Action(0, "move", move=f"m{k}"),)


def test_a_pair_cut_short_is_left_unvalued_with_the_rest():
    r = _SlowResolver()
    tv = A.TurnValues(r, {}, None, lambda outs: [0.5] * len(outs))
    pairs = [(_j(k), _j(0)) for k in range(6)]

    def stop():
        return False

    stop.hard = lambda: True  # the time is up inside the third pair
    assert tv.prepare(pairs, stop) is False
    assert len(tv._value) == 2  # the first two, valued; the third and on, not
    assert tv.prepare(pairs) is True  # with no clock, every pair
    assert len(tv._value) == 6


def test_without_a_hard_stop_a_pair_is_never_cut_short():
    r = _SlowResolver()
    tv = A.TurnValues(r, {}, None, lambda outs: [0.5] * len(outs))
    assert tv.prepare([(_j(k), _j(0)) for k in range(4)], lambda: False) is True


def test_the_deadline_has_a_hard_stop_that_keeps_no_count():
    now = [0.0]
    d = B.Deadline(10.0, clock=lambda: now[0])
    now[0] = 4.0
    assert d() is False and d.longest == 0.0
    now[0] = 9.0
    assert d.over() is False and d.longest == 0.0 and d.last == 4.0
    now[0] = 10.5
    assert d.over() is True


class _ManyBoards:
    """Each pair resolves to 100 boards."""

    def resolve(self, sides, fld, choices, stop=None):
        return [_Out() for _ in range(100)]


def test_the_boards_are_valued_in_parts_and_stop_when_the_time_is_up():
    """Replaying the gate's late turns: after a long resolve, valuing a
    thousand boards took seconds more. They are valued in parts, the hard stop
    looked at between parts; pairs whose boards were not valued are left."""
    calls = []

    def board_wp(outs):
        calls.append(len(outs))
        return [0.5] * len(outs)

    tv = A.TurnValues(_ManyBoards(), {}, None, board_wp)
    pairs = [(_j(k), _j(0)) for k in range(10)]

    def stop():
        return False

    stop.hard = lambda: len(calls) >= 1  # the time is up after the first part
    assert tv.prepare(pairs, stop) is False
    assert len(calls) == 1 and calls[0] >= A.BOARDS_AT_ONCE
    assert len(tv._value) == calls[0] // 100  # only the pairs of that part
    assert tv.prepare(pairs) is True and len(tv._value) == 10


def test_without_a_clock_the_boards_are_still_valued_in_large_parts():
    calls = []

    def board_wp(outs):
        calls.append(len(outs))
        return [0.5] * len(outs)

    tv = A.TurnValues(_ManyBoards(), {}, None, board_wp)
    assert tv.prepare([(_j(k), _j(0)) for k in range(10)]) is True
    assert sum(calls) == 1000 and len(tv._value) == 10
