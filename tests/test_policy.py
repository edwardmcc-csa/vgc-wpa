"""Tests for wpa/policy.py (Week 9 Task 3): how likely each Pokemon is to pick
each of its options, learned from the training split (DEFINITIONS §7: a choice is
judged against the opponent's likely replies)."""

# ruff: noqa: E501

from __future__ import annotations

import math

import numpy as np

from tests.test_board_actions import T1, log
from tests.test_board_effects import at_turn_start
from wpa import choices as C
from wpa import policy as P
from wpa.team_sheets import Dex, sheets_from_log

MOVES = {
    "tailwind": {
        "target": "allySide",
        "category": "Status",
        "sideCondition": "tailwind",
        "priority": 0,
    },
    "rockslide": {
        "target": "allAdjacentFoes",
        "category": "Physical",
        "priority": 0,
        "basePower": 75,
    },
    "protect": {"target": "self", "category": "Status", "priority": 4},
    "fakeout": {
        "target": "normal",
        "category": "Physical",
        "priority": 3,
        "basePower": 40,
    },
    "moonblast": {
        "target": "normal",
        "category": "Special",
        "priority": 0,
        "basePower": 95,
    },
}
DEX = Dex(species={}, moves=MOVES, items={})


def opts_at(turn, role):
    lg = log(T1)
    s = at_turn_start(lg, turn, role=role)
    sheet = sheets_from_log(lg)[role]
    return s, C.options(
        s["our_pokemon"], s["opp_pokemon"], sheet, DEX, brought={0, 1, 2, 3}
    )


def feats(s, a):
    return dict(zip(P.FEATURES, P.option_features(s, a, MOVES, rates={}, ctx=None)))


def test_option_features_say_what_kind_of_action_it_is():
    s, opts = opts_at(1, "p2")
    by = {(a.kind, a.move, a.target): feats(s, a) for a in opts[0]}
    fake = by[("move", "fakeout", ("foe", 0))]
    assert (
        fake["fakeout_first"] == 1
        and fake["fakeout_late"] == 0
        and fake["priority"] == 1
    )
    assert by[("move", "fakeout", ("ally", 1))]["targets_ally"] == 1
    sw = (
        by[("switch", "", None)]
        if ("switch", "", None) in by
        else next(v for k, v in by.items() if k[0] == "switch")
    )
    assert sw["is_switch"] == 1 and sw["is_status"] == 0


def test_fake_out_after_the_first_turn_is_marked_as_late():
    s, opts = opts_at(2, "p2")
    fake = next(a for a in opts[0] if a.move == "fakeout")
    f = feats(s, fake)
    assert f["fakeout_late"] == 1 and f["fakeout_first"] == 0


def test_a_tailwind_already_blowing_is_marked_redundant():
    s, opts = opts_at(1, "p1")
    tw = next(a for a in opts[0] if a.move == "tailwind")
    assert feats(s, tw)["redundant_field"] == 0
    assert (
        P.option_features(s, tw, MOVES, rates={}, ctx=None, our_side={"tailwind"})[
            P.FEATURES.index("redundant_field")
        ]
        == 1
    )


def test_the_model_turns_scores_into_chances_that_add_up_per_pokemon():
    m = P.PolicyModel(weights=[1.0] + [0.0] * (len(P.FEATURES) - 1))
    X = np.zeros((3, len(P.FEATURES)))
    X[0, 0] = 1.0
    p = m.chances(X)
    assert abs(p.sum() - 1) < 1e-12 and p[0] > p[1] == p[2]


def test_fitting_recovers_a_clear_preference():
    rng = np.random.default_rng(0)
    groups = []
    for _ in range(400):
        X = rng.normal(size=(4, len(P.FEATURES)))
        logits = 2.0 * X[:, 0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        groups.append((X, int(rng.choice(4, p=p))))
    m = P.fit(groups, l2=1e-3)
    assert m.weights[0] > 1.0
    ll, uniform = P.score(m, groups)
    assert ll > uniform and abs(uniform - math.log(1 / 4)) < 1e-12
