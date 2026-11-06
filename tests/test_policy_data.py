"""Tests for wpa/policy_data.py (Week 9 Task 3): examples from a game's log."""

from __future__ import annotations

from collections import Counter

from tests.test_board_actions import T1, log
from tests.test_decisions import EMPTY
from tests.test_policy import DEX, MOVES
from wpa import policy_data as PD


def test_each_visible_choice_becomes_one_example_with_its_options():
    groups = PD.examples_for_game(
        "gen9championsvgc2026regma-1",
        log(T1),
        "regma",
        DEX,
        MOVES,
        EMPTY,
        calc=None,
        store=None,
        bring=None,
        rates={},
    )
    # turn 1: Rock's Rock Slide, Inci's Fake Out, Fini's Moonblast (Whim flinched)
    assert len(groups) == 3
    for X, chosen in groups:
        assert X.ndim == 2 and 0 <= chosen < len(X)


def test_moves_are_counted_when_offered_and_when_chosen():
    offered, chosen = Counter(), Counter()
    PD.count_moves(log(T1), DEX, (offered, chosen))
    assert chosen["fakeout"] == 1 and chosen["rockslide"] == 1
    assert offered["fakeout"] >= 1 and offered["moonblast"] >= 1
