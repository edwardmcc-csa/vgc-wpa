"""Moves that switch the user out (Week 10 Task 3): which Pokemon came in is part
of the switching player's choice.

- the log's choice records the Pokemon a switching move brought in;
- for likely replies and alternatives, each switching option is spread over the
  bench by the opponent model's chances for switching to each Pokemon;
- two Pokemon cannot both bring in the same one.
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from tests.test_board_actions import log
from wpa import attribution as A
from wpa import choices as C
from wpa.choices import Action

UTURN = "|t:|1\n|move|p1a: Whim|U-turn|p2a: Inci\n|-damage|p2a: Inci|80/100\n|switch|p1a: Back|Back, L50|100/100"


def test_the_log_shows_which_pokemon_a_switching_move_brought_in():
    (t1,) = [t for t in C.turns(log(UTURN)) if t.turn == 1 and t.role == "p1"]
    act = t1.taken[0]
    assert isinstance(act, Action) and act.move == "uturn"
    assert act.switch_to == 2  # Back, third on the sheet
    assert C.base(act) == Action(0, "move", move="uturn", target=act.target)


def test_a_switching_option_is_spread_over_the_bench_by_the_switch_chances():
    u = Action(0, "move", move="uturn", target=("foe", 0))
    opts = {
        0: [
            u,
            Action(0, "move", move="protect"),
            Action(0, "switch", switch_to=2),
            Action(0, "switch", switch_to=3),
        ]
    }
    ch = {0: [0.4, 0.2, 0.3, 0.1]}
    o2, c2 = A.expand_pivots(opts, ch)
    got = dict(zip(o2[0], c2[0]))
    assert got[
        Action(0, "move", move="uturn", target=("foe", 0), switch_to=2)
    ] == pytest.approx(0.3)
    assert got[
        Action(0, "move", move="uturn", target=("foe", 0), switch_to=3)
    ] == pytest.approx(0.1)
    assert got[Action(0, "move", move="protect")] == pytest.approx(0.2)
    assert sum(c2[0]) == pytest.approx(1.0)
    # nothing on the bench: the option stays as it is
    o3, c3 = A.expand_pivots({0: [u]}, {0: [1.0]})
    assert o3[0] == [u] and c3[0] == [1.0]


def test_two_pokemon_cannot_both_bring_in_the_same_one():
    a = Action(0, "move", move="uturn", target=("foe", 0), switch_to=2)
    b = Action(1, "switch", switch_to=2)
    c = Action(1, "move", move="voltswitch", target=("foe", 1), switch_to=2)
    d = Action(1, "move", move="voltswitch", target=("foe", 1), switch_to=3)
    pairs = C.joint({0: [a], 1: [b, c, d]})
    assert pairs == [(a, d)]


SUB1 = "|t:|1\n|move|p1a: Whim|Substitute|p1a: Whim\n|-start|p1a: Whim|Substitute\n|-damage|p1a: Whim|75/100"
SUB2 = "|t:|2\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-activate|p1a: Whim|Substitute|[damage]"
SUB3 = "|t:|3\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-end|p1a: Whim|Substitute"


def test_the_board_knows_a_substitute_is_up_and_whether_it_was_hit():
    from tests.test_board_effects import at_turn_start

    s = at_turn_start(log(SUB1, SUB2, SUB3), 2)
    whim = s["our_pokemon"][0]
    assert whim["sub_up"] == "full"
    assert "hits" not in whim  # paying for a substitute is not being hit
    assert at_turn_start(log(SUB1, SUB2, SUB3), 3)["our_pokemon"][0]["sub_up"] == "hit"
    assert "sub_up" not in at_turn_start(log(SUB1, SUB2, SUB3), 4)["our_pokemon"][0]
