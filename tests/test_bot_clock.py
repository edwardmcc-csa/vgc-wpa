"""Week 16, Task 2: within Showdown's clock. The bot's search goes the likeliest
plays first and stops when its time for the turn is up, playing the best it
has valued; with time to spare it plays what the advice plays (`rank_all`,
DEFINITIONS §4 revision 13). Its time for a turn is a share of what is left
of the game's clock, never over 45 seconds."""

from __future__ import annotations

import pytest

from wpa import advise as AD
from wpa import attribution as A
from wpa import bot as B
from wpa.choices import Action


def _j(k: int):
    return (Action(0, "move", move=f"m{k}"),)


def _y(k: int):
    return (Action(0, "move", move=f"r{k}"),)


def _value(j, y) -> float:  # a made-up board value: any fixed numbers do
    a = int(j[0].move[1:])
    b = int(y[0].move[1:])
    return ((a * 37 + b * 11) % 23) / 23


def _mix(n: int, make, seed: int = 1):
    import numpy as np

    p = np.random.default_rng(seed).dirichlet(np.ones(n))
    return [(make(k), float(x)) for k, x in enumerate(p)]


def _theirs(ours, theirs) -> float:  # the values from p2's side
    return 1 - _value(theirs, ours)


class Counting:
    """`prepare` that counts the pairs asked for; `stop` after `limit` calls."""

    def __init__(self, limit: int | None = None) -> None:
        self.calls, self.pairs, self.limit = 0, [], limit

    def prepare(self, pairs) -> None:
        self.calls += 1
        self.pairs.append(list(pairs))

    def stop(self) -> bool:
        return self.limit is not None and self.calls >= self.limit


@pytest.mark.parametrize("n", [15, 60])  # all valued at once, and two passes
def test_with_time_to_spare_the_search_ranks_as_the_advice_does(n):
    full = _mix(n, _j)
    replies = _mix(12, _y, seed=2)
    want, compared = AD.rank_all(_value, full, replies)
    got = AD.rank_within(_value, full, replies, Counting().prepare, lambda: False)
    assert [j for j, _v, _p in got.ranked] == [j for j, _v, _p in want]
    assert [v for _j, v, _p in got.ranked] == pytest.approx([v for _j, v, _p in want])
    assert got.compared == compared == n and not got.stopped
    assert got.full == (n if n <= A.USUAL + A.FINALISTS else len(want) - got.screened)


def test_when_time_runs_out_the_likeliest_plays_were_valued_first():
    full = _mix(60, _j)
    replies = _mix(12, _y, seed=2)
    c = Counting(limit=3)
    got = AD.rank_within(_value, full, replies, c.prepare, c.stop)
    assert got.stopped and got.full == 0
    likeliest = [j for j, _ in sorted(full, key=lambda x: -x[1])]
    asked = list(dict.fromkeys(j for batch in c.pairs for j, _y in batch))
    assert asked == likeliest[: len(asked)]  # the likeliest first
    assert got.screened == len(asked) < 60
    # nothing is dropped: those not valued follow, likeliest first
    assert len(got.ranked) == 60
    tail = [j for j, v, _p in got.ranked if v != v]  # not valued: NaN
    assert tail == likeliest[len(asked) :]
    # the best of those valued (against their likeliest replies) is played
    top = sorted(replies, key=lambda x: -x[1])[: A.SCREEN]
    best = max(asked, key=lambda j: A.expected(_value, [(j, 1.0)], top))
    assert got.ranked[0][0] == best


def test_plays_already_valued_against_every_reply_count_when_time_is_short():
    full = _mix(60, _j)
    replies = _mix(12, _y, seed=2)
    known = [_j(59)]  # valued in full already (the replies' weighing did)
    got = AD.rank_within(
        _value, full, replies, Counting().prepare, lambda: True, known=known
    )
    assert got.stopped and got.full == 1 and got.screened == 0
    assert got.ranked[0][0] == _j(59)


def test_their_replies_are_weighed_as_the_advice_weighs_them():
    plain = {"p1": _mix(8, _j), "p2": _mix(8, _y, seed=3)}

    class TV:
        def prepare(self, pairs, stop=None):
            pass

        def __call__(self, p1, p2):
            return _value(p1, p2)

        def for_role(self, r):
            return self if r == "p1" else _theirs

    want = A.strong_mixes(TV(), plain, 9.6)["p2"]
    got, used = AD.strong_within(TV(), plain, 9.6, "p1", lambda: False)
    assert used is not None and len(used) == 8
    assert AD.strong_within(TV(), plain, 0.0, "p1", lambda: False)[1] is None
    assert [j for j, _ in got] == [j for j, _ in want]
    assert [q for _, q in got] == pytest.approx([q for _, q in want])


def test_short_of_time_their_replies_are_weighed_against_what_was_valued():
    plain = {"p1": _mix(8, _j), "p2": _mix(8, _y, seed=3)}
    asked = []

    class TV:
        def prepare(self, pairs, stop=None):
            asked.append(list(pairs))

        def __call__(self, p1, p2):
            return _value(p1, p2)

        def for_role(self, r):
            return self if r == "p1" else _theirs

    got, used = AD.strong_within(TV(), plain, 9.6, "p1", lambda: len(asked) >= 2)
    ours = [j for j, _ in sorted(plain["p1"], key=lambda x: -x[1])][:2]
    assert used == ours  # our two likeliest choices
    assert [b[0][0] for b in asked] == ours
    part = [x for x in plain["p1"] if x[0] in ours]
    want = A.strengthened(TV().for_role("p2"), plain["p2"], part, 9.6)
    assert [q for _, q in got] == pytest.approx([q for _, q in want])


# --------------------------------------------------------------------------
# The time for a turn
# --------------------------------------------------------------------------


def test_a_turns_time_is_a_share_of_what_is_left_never_over_45_seconds():
    assert B.think_time(420) == 45  # the cap
    assert B.think_time(120) == pytest.approx(20)  # a sixth of what is left
    assert B.think_time(3) == 1.0  # always a moment
    assert B.think_time(420, preview=True) == 45


def test_the_clock_left_is_read_from_showdowns_own_line():
    lines = [
        "|inactive|Time left: 55 sec this turn | 420 sec total",
        "|turn|2",
        "|inactive|Time left: 55 sec this turn | 385 sec total | 30 sec grace",
    ]
    assert B.clock_left(lines) == 385
    assert B.clock_left(["|turn|1"]) is None


def test_the_bank_counts_showdowns_ticks():
    # Showdown takes the time in 5-second ticks while a choice is awaited
    assert B.ticks(0.4) == 0 and B.ticks(4.9) == 0 and B.ticks(12.0) == 10
    clock = B.Clock()
    clock.spend(12.0)
    clock.spend(31.0)
    assert clock.left() == 420 - 10 - 30
    assert clock.left(["|inactive|Time left: 55 sec this turn | 300 sec total"]) == 300


def test_the_search_stops_before_a_batch_that_would_run_past_the_time():
    now = [0.0]
    stop = B.Deadline(45.0, clock=lambda: now[0])
    assert not stop()  # at 0: the first batch
    now[0] = 10.0
    assert not stop()  # a batch takes 10 s: one half as long again ends at 25
    now[0] = 20.0
    assert not stop()  # 20 + 15 = 35 < 45
    now[0] = 32.0
    assert stop()  # that one took 12 s: 32 + 18 = 50, past 45
    late = B.Deadline(5.0, clock=lambda: now[0])
    now[0] = 50.0
    assert late()  # already past its time


# --------------------------------------------------------------------------
# Week 17, Task 1: on time, every turn
# --------------------------------------------------------------------------


def test_the_replies_weighing_stops_between_pairs_inside_one_choice():
    """Week 16's late turns: weighing their replies against our likeliest
    choice was one call of every pair (60 to 145 s on some opening turns), and
    the clock was looked at only between our choices. Now it is looked at
    between small batches of pairs, and before the first one too."""
    plain = {"p1": _mix(3, _j), "p2": _mix(40, _y, seed=3)}
    asked: list[list] = []

    class TV:
        def prepare(self, pairs, stop=None):
            asked.append(list(pairs))

        def __call__(self, p1, p2):
            return _value(p1, p2)

        def for_role(self, r):
            return self if r == "p1" else _theirs

    def stop() -> bool:
        return sum(map(len, asked)) >= 20

    got, used = AD.strong_within(TV(), plain, 9.6, "p1", stop)
    assert max(map(len, asked)) <= 12  # small batches
    assert sum(map(len, asked)) <= 24  # stopped soon after the time was up
    assert used == []  # our likeliest choice was not weighed against all 40
    assert got == list(plain["p2"])  # so their replies are taken as they come
    assert AD.strong_within(TV(), plain, 9.6, "p1", lambda: True) == (
        list(plain["p2"]),
        [],
    )


def test_with_nothing_valued_the_likeliest_play_is_played_at_once():
    """No time left and nothing valued: the choice model's likeliest play, with
    no batch valued first (Week 16 always valued one)."""
    full = _mix(60, _j)
    replies = _mix(12, _y, seed=2)
    c = Counting()
    got = AD.rank_within(_value, full, replies, c.prepare, lambda: True)
    assert c.calls == 0
    assert got.stopped and got.full == 0 and got.screened == 0
    likeliest = max(full, key=lambda x: x[1])[0]
    assert got.ranked[0][0] == likeliest
    assert len(got.ranked) == 60


def test_a_batch_cut_short_is_not_counted_as_valued():
    """`prepare` may stop part way (it says False): those plays are left
    unvalued, and the search ends."""
    full = _mix(60, _j)
    replies = _mix(12, _y, seed=2)
    calls = []

    def prepare(pairs):
        calls.append(list(pairs))
        return len(calls) < 2  # the second batch is cut short

    got = AD.rank_within(_value, full, replies, prepare, lambda: False)
    assert got.stopped and len(calls) == 2
    first = list(dict.fromkeys(j for j, _y in calls[0]))
    assert got.screened == len(first)  # only the first batch's plays


class _Out:
    def __init__(self) -> None:
        self.prob, self.winner = 1.0, None


class _Resolver:
    def __init__(self) -> None:
        self.n = 0

    def resolve(self, sides, fld, choices):
        self.n += 1
        return [_Out()]


def test_the_resolver_batch_looks_at_the_clock_between_pairs():
    """Inside one batch the clock is looked at between pairs: once it is up, the
    pairs resolved so far are valued and kept, the rest left for later."""
    r = _Resolver()
    tv = A.TurnValues(r, {}, None, lambda outs: [0.5] * len(outs))
    pairs = [(_j(k), _y(0)) for k in range(10)]
    assert tv.prepare(pairs, stop=lambda: r.n >= 3) is False
    assert r.n == 3
    assert len(tv._value) == 3 and tv(pairs[0][0], pairs[0][1]) == 0.5
    assert tv.prepare(pairs) is True  # the rest, with no clock
    assert r.n == 10


def test_a_choice_for_a_request_that_has_passed_is_not_sent():
    """Back in step: each choice is for one request. When a newer one has come
    (Showdown chose for the bot after a late turn, or asked again), the old
    choice is dropped, and the old search stops at its next look at the clock."""
    t = B.Requests()
    a = t.begin("battle-1", {"rqid": 5})
    assert t.current("battle-1", a, {"rqid": 5})
    b = t.begin("battle-1", {"rqid": 6})
    assert not t.current("battle-1", a, {"rqid": 6})  # superseded
    assert t.current("battle-1", b, {"rqid": 6})
    assert not t.current("battle-1", b, {"rqid": 7})  # the request moved on
    t.abandon("battle-1")
    assert not t.current("battle-1", b, {"rqid": 6})  # given up (the hard limit)
    assert B.Requests.NOTHING.message == ""  # poke_env sends nothing


def test_the_hard_limit_sends_a_legal_choice_if_the_advice_has_not_answered():
    import asyncio
    import time as T

    def slow():
        T.sleep(0.5)
        return "the advice"

    def fast():
        return "the advice"

    async def run(work, limit):
        return await B.answer_within(work, limit, lambda: "a legal choice")

    assert asyncio.run(run(slow, 0.1)) == ("a legal choice", True)
    assert asyncio.run(run(fast, 5.0)) == ("the advice", False)
    assert B.HARD_LIMIT == 50
