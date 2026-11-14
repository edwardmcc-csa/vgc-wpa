"""Tests for Week 11 (found while measuring Task 2): a choice the log does not
show is averaged only over the choices the log allows.

Reg M-A's biggest swing in Week 10 (game 2605342116, turn 5): Kingambit fell
before moving, so its choice was averaged over all its options, Protect
included. Had it chosen Protect it would have gone first and not been hit, so the
log rules that out; averaging over it put most of the swing in the dice.

- a switch or a Mega Evolution always shows in the log, before any move: never
  a hidden choice;
- a Pokemon knocked out before it moved did not choose a move with raised
  priority (it would have gone first): Protect, Fake Out, Sucker Punch...
"""

from __future__ import annotations

import pytest

from wpa import attribution as A
from wpa.choices import Action

PRIORITY = {
    "protect": 4,
    "fakeout": 3,
    "suckerpunch": 1,
    "kowtowcleave": 0,
    "swordsdance": 0,
}

PROTECT = Action(0, "move", move="protect")
SUCKER = Action(0, "move", move="suckerpunch", target=("foe", 0))
COWTOW = Action(0, "move", move="kowtowcleave", target=("foe", 0))
SD = Action(0, "move", move="swordsdance")
MEGA = Action(0, "move", move="kowtowcleave", target=("foe", 0), mega=True)
SWITCH = Action(0, "switch", switch_to=2)
OPTS = {0: [PROTECT, SUCKER, COWTOW, SD, MEGA, SWITCH]}
CH = {0: [0.4, 0.2, 0.15, 0.05, 0.1, 0.1]}


def _chances(mix):
    return {j[0]: p for j, p in mix}


def test_a_pokemon_knocked_out_before_moving_chose_no_priority_move_switch_or_mega():
    mix = A.taken_mixture({0: "fainted"}, set(), OPTS, CH, PRIORITY)
    got = _chances(mix)
    assert set(got) == {COWTOW, SD}
    assert got[COWTOW] == pytest.approx(0.15 / 0.2)


def test_any_hidden_choice_was_not_a_switch_or_a_mega_evolution():
    for reason in ("cant", "confused", None):
        taken = {0: reason} if reason else {}
        got = _chances(A.taken_mixture(taken, set(), OPTS, CH, PRIORITY))
        assert SWITCH not in got and MEGA not in got
        assert PROTECT in got  # it may have tried Protect and failed to move


def test_if_the_log_rules_everything_out_the_options_stand():
    opts = {0: [PROTECT, SWITCH]}
    got = _chances(
        A.taken_mixture({0: "fainted"}, set(), opts, {0: [0.5, 0.5]}, PRIORITY)
    )
    assert set(got) == {PROTECT, SWITCH}


def test_without_priorities_the_old_averaging_stays():
    got = _chances(A.taken_mixture({0: "fainted"}, set(), OPTS, CH))
    assert set(got) == {PROTECT, SUCKER, COWTOW, SD, MEGA, SWITCH}


def test_a_hidden_choice_that_cannot_go_with_the_shown_ones_is_left_out():
    """Game 2634478000 turn 4, the opponent's sheet hidden: Sinistcha fell
    before moving with no moves believed, so its options were a switch to
    Incineroar only, the Pokemon its partner switched to. No joint choice was
    left, and the turn failed (division by zero). The shown choice stands."""
    to_inc = Action(1, "switch", switch_to=0)
    partner = Action(3, "switch", switch_to=0)
    opts = {1: [to_inc], 3: [partner, Action(3, "move", move="protect")]}
    chances = {1: [1.0], 3: [0.5, 0.5]}
    mix = A.taken_mixture({1: "fainted", 3: partner}, set(), opts, chances, PRIORITY)
    assert mix == [((partner,), 1.0)]
