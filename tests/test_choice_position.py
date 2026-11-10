"""Tests for DEFINITIONS revision 10 (Week 11 Task 0): "your decision" split into
your choice, against the typical choice, and the position, credited to no one.

- your choice = E[WP | your choice] - E[WP | a typical choice];
- the position = E[WP | a typical choice] - WP(before);
- their decision and the dice as before; the four add up to the swing.
"""

from __future__ import annotations

import json

import pytest

from wpa import attribution as A
from wpa.choices import Action
from wpa.resolver import Field, Outcome

X = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
Y = (
    Action(0, "move", move="fakeout", target=("foe", 0)),
    Action(1, "move", move="protect"),
)
Z = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
R1 = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
R2 = (
    Action(0, "move", move="flareblitz", target=("foe", 0)),
    Action(1, "move", move="protect"),
)

TABLE = {
    (X, R1): 0.70,
    (X, R2): 0.50,
    (Y, R1): 0.60,
    (Y, R2): 0.65,
    (Z, R1): 0.40,
    (Z, R2): 0.30,
}


def value(o, t):
    return TABLE[(o, t)]


LIKELY = [(R1, 0.6), (R2, 0.4)]
TYPICAL = [(X, 0.5), (Y, 0.3), (Z, 0.2)]


def test_the_four_parts_are_what_revision_10_says_and_add_up():
    s = A.decompose(value, 0.55, 0.48, [(X, 1.0)], [(R2, 1.0)], LIKELY, typical=TYPICAL)
    e_typ = A.expected(value, TYPICAL, LIKELY)
    e_yours = A.expected(value, [(X, 1.0)], LIKELY)
    assert s.choice == pytest.approx(e_yours - e_typ)
    assert s.position == pytest.approx(e_typ - 0.55)
    assert s.yours == pytest.approx(s.choice + s.position)  # revision 8's sum
    assert s.theirs == pytest.approx(0.50 - e_yours)
    assert s.dice == pytest.approx(0.48 - 0.50)
    assert abs(s.choice + s.position + s.theirs + s.dice - s.swing) < 1e-12
    assert s.conserved()


def test_with_one_option_your_choice_is_exactly_zero():
    s = A.decompose(
        value, 0.55, 0.62, [(Y, 1.0)], [(R1, 1.0)], LIKELY, typical=[(Y, 1.0)]
    )
    assert s.choice == 0.0
    assert s.position == pytest.approx(s.yours)


def test_when_every_choice_is_worth_the_same_your_choice_is_zero():
    def same(o, t):
        return 0.9 if t == R1 else 0.7

    s = A.decompose(same, 0.5, 0.9, [(Z, 1.0)], [(R1, 1.0)], LIKELY, typical=TYPICAL)
    assert s.choice == pytest.approx(0.0)
    assert s.position == pytest.approx(0.6 * 0.9 + 0.4 * 0.7 - 0.5)


def test_a_turn_that_ends_the_game_whatever_anyone_chooses_goes_to_the_position():
    # Week 10's Perish Song turn: the game is over whatever is chosen, and the
    # model's WP before it was 34%
    class Ends:
        def resolve(self, sides, fld, actions):
            return [Outcome(1.0, {"p1": [], "p2": []}, Field(), winner="p1")]

    tv = A.TurnValues(
        Ends(), {"p1": [], "p2": []}, Field(), lambda outs: [0.5] * len(outs)
    )
    tv.prepare([(o, t) for o, _ in TYPICAL for t, _ in LIKELY])
    s = A.decompose(
        tv.for_role("p1"), 0.34, 1.0, [(X, 1.0)], [(R1, 1.0)], LIKELY, typical=TYPICAL
    )
    assert s.choice == 0.0 and s.theirs == 0.0 and s.dice == 0.0
    assert s.position == pytest.approx(0.66)


def test_without_a_typical_choice_the_split_stays_revision_8s():
    s = A.decompose(value, 0.55, 0.48, [(X, 1.0)], [(R2, 1.0)], LIKELY)
    assert s.choice is None and s.position is None and s.conserved()


def test_the_summary_leads_with_your_choice_and_shows_the_position(tmp_path):
    from tests.test_attribution import _rec

    recs = []
    for role, sign in (("p1", 1), ("p2", -1)):
        r = _rec("g1", 1, role, 0.5 if sign > 0 else 0.5, 0.5 + sign * 0.2, alt=True)
        r.update(kind="turn", point=2, result=1.0, after_board=r["after"])
        r.update(choice=sign * 0.04, position=r["yours"] - sign * 0.04)
        recs.append(r)
    path = tmp_path / "a.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    text = A.report(path)
    assert "your choice (against the typical choice): mean +0.0" in text
    assert "the position (credited to no one):" in text
    assert "your decision (revision 8: your choice + the position):" in text
    assert "a part of 3 points or more (the reporting threshold): choice 100%" in text
    assert "the 10 biggest choices (points; by your choice):" in text
