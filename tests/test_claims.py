"""Tests for wpa/claims.py (Week 5 Task 8): the expert-claim positions.

Report only: nothing here gates. These tests check that the follow-up
positions are built the way the claims describe.
"""

from __future__ import annotations

import numpy as np
import pytest

from wpa import claims as C
from wpa.features import columns

COLS = columns("ABCDE")
IX = {c: i for i, c in enumerate(COLS)}


def base_row():
    x = np.zeros(len(COLS), dtype=np.float32)
    for side, (fainted, active_hp, bench_hp, unseen) in {
        "our": (1, 1.6, 0.0, 1),
        "their": (0, 0.5, 0.0, 2),
    }.items():
        x[IX[f"a_{side}_fainted"]] = fainted
        x[IX[f"a_{side}_remaining"]] = 4 - fainted
        x[IX[f"a_{side}_active"]] = 2
        x[IX[f"a_{side}_hp_active"]] = active_hp
        x[IX[f"a_{side}_hp_seen"]] = active_hp + bench_hp
        x[IX[f"a_{side}_seen_alive"]] = 2
        x[IX[f"a_{side}_unseen"]] = unseen
    x[IX["c_their_tailwind"]] = 2
    x[IX["c_moment_turn_start"]] = 1
    x[IX["a_turn"]] = 5
    return x


def test_a_turn_passing_takes_one_turn_off_every_timer():
    x = C.pass_turn(base_row(), COLS)
    assert x[IX["c_their_tailwind"]] == 1
    assert x[IX["a_turn"]] == 6
    y = C.pass_turn(x, COLS)
    assert y[IX["c_their_tailwind"]] == 0


def test_knocking_out_both_their_actives_brings_in_two_unseen_pokemon():
    x = C.knock_out(base_row(), COLS, "their", 2)
    assert x[IX["a_their_fainted"]] == 2 and x[IX["a_their_remaining"]] == 2
    assert x[IX["a_their_unseen"]] == 0  # both replacements came in
    assert x[IX["a_their_active"]] == 2
    assert x[IX["a_their_hp_active"]] == pytest.approx(2.0)  # fresh replacements
    assert x[IX["a_their_hp_seen"]] == pytest.approx(2.0)


def test_one_knockout_brings_in_one():
    x = C.knock_out(base_row(), COLS, "their", 1, hp_lost=0.3)
    assert x[IX["a_their_fainted"]] == 1
    assert x[IX["a_their_unseen"]] == 1
    assert x[IX["a_their_hp_active"]] == pytest.approx(0.5 - 0.3 + 1.0)


def test_ec001_compares_single_knockout_and_stall_with_double_knockout():
    rows = C.ec001_follow_ups(base_row(), COLS)
    assert set(rows) == {"double_ko", "single_ko", "stall"}
    assert rows["double_ko"][IX["a_their_remaining"]] == 2
    assert rows["stall"][IX["a_their_remaining"]] == 4
    assert rows["stall"][IX["c_their_tailwind"]] == 1


def test_ec002_compares_sacrificing_the_spent_pokemon_with_keeping_it():
    x = base_row()
    rows = C.ec002_follow_ups(x, COLS, spent_hp=0.2, strong_hp=1.0, damage=0.5)
    assert rows["sacrifice"][IX["a_our_fainted"]] == 2
    assert rows["keep"][IX["a_our_fainted"]] == 1
    assert rows["keep"][IX["a_our_hp_active"]] == pytest.approx(1.6 - 0.5)


def test_candidate_positions_for_ec001_are_found_by_their_features():
    X = np.stack([base_row(), np.zeros(len(COLS), dtype=np.float32)])
    assert list(C.ec001_candidates(X, COLS)) == [0]
