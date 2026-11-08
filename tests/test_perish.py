"""Perish Song (Week 10 Task 1): the count reaches the timers and the board, and
the resolver counts it down.

Week 9 found Reg M-A's two biggest swings were Perish Song, scored as luck. The
count never reached the timers (Showdown attaches Perish Song in the move's code,
so the durations table has no attachment for it), and the resolver did not count
it down.
"""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_board_effects import LEADS
from tests.test_decisions import HEAD, REF
from wpa import decisions as D
from wpa.durations import Durations, TimedEffect

# as the durations table has it: no attachment (wpa.durations reads Showdown's data)
PERISH = TimedEffect(
    "Moves", "perishsong", "Perish Song", None, 4, (), (), None, "duration", REF
)
TABLE = Durations("t", timed={"perishsong": PERISH})

SONG = (
    "|t:|1\n|move|p1a: Whim|Perish Song|p1a: Whim\n"
    "|-start|p1a: Whim|perish3|[silent]\n|-start|p1b: Rock|perish3|[silent]\n"
    "|-start|p2a: Inci|perish3|[silent]\n|-start|p2b: Fini|perish3|[silent]\n"
    "|-fieldactivate|move: Perish Song"
)
END1 = "|upkeep\n|-start|p1a: Whim|perish3\n|-start|p1b: Rock|perish3\n|-start|p2a: Inci|perish3\n|-start|p2b: Fini|perish3\n|t:|2\n|turn|2"
QUIET2 = "|t:|2\n|move|p1b: Rock|Protect|p1b: Rock"
END2 = "|upkeep\n|-start|p1a: Whim|perish2\n|-start|p1b: Rock|perish2\n|-start|p2a: Inci|perish2\n|-start|p2b: Fini|perish2\n|t:|3\n|turn|3"
SWAP3 = "|t:|3\n|switch|p2b: Rime|Rime, L50|100/100"
END3 = "|upkeep\n|-start|p1a: Whim|perish1\n|-start|p1b: Rock|perish1\n|-start|p2a: Inci|perish1\n|t:|4\n|turn|4"


def game(*blocks):
    return "\n|\n".join([HEAD, LEADS, *blocks, "|win|A"])


def at(g, turn, role="p1"):
    (k,) = [
        i
        for i, s in enumerate(g.states[role][:-1])
        if s["turn"] == turn and s["moment"] == "turn_start"
    ]
    return g.states[role][k], g.joined[role][k]


def test_the_count_reaches_the_timers():
    g = D.build_game(game(SONG, END1, QUIET2, END2), TABLE)
    _s, j = at(g, 2)
    ours = sorted(lo for eid, _t, lo, _h in j.ours if eid == "perishsong")
    theirs = sorted(lo for eid, _t, lo, _h in j.theirs if eid == "perishsong")
    assert ours == [3, 3] and theirs == [3, 3]
    _s, j = at(g, 3)
    assert sorted(lo for eid, _t, lo, _h in j.ours if eid == "perishsong") == [2, 2]


def test_the_board_carries_each_pokemons_count_and_a_switch_clears_it():
    g = D.build_game(game(SONG, END1, QUIET2, END2, SWAP3, END3), TABLE)
    s, _j = at(g, 2)
    assert [m.get("perish") for m in s["our_pokemon"][:2]] == [3, 3]
    s, _j = at(g, 4)
    assert [m.get("perish") for m in s["our_pokemon"][:2]] == [1, 1]
    theirs = s["opp_pokemon"]
    assert theirs[0].get("perish") == 1  # Inci stayed in
    assert "perish" not in theirs[1]  # Fini switched out: the count is gone
    assert "perish" not in theirs[2]  # Rime came in fresh
