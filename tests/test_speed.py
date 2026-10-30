"""Tests for the speed features, group F (Week 6 Task 2).

Base Speed from the pinned Showdown data (the Mega form's once a Pokemon has Mega
Evolved), Choice Scarf x1.5, Tailwind x2 on its side, and Trick Room reversing who
acts first. Priority moves, paralysis and stat stages are not included.
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from wpa import features as F
from wpa.team_sheets import Dex, SheetMon
from wpa.timer_join import JoinedTimers


def sp(spe):
    return {
        "baseStats": {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": spe},
        "types": ["Normal"],
        "abilities": {"0": "X"},
    }


DEX = Dex(
    species={
        "fast": sp(120),
        "mid": sp(90),
        "slow": sp(40),
        "zard": sp(100),
        "zardmegay": sp(130),
    },
    moves={},
    items={
        "choicescarf": {"megaStone": None},
        "sitrusberry": {"megaStone": None},
        "charizarditey": {"megaStone": {"Zard": "Zard-Mega-Y"}},
    },
)


def mon(pos, species, item="sitrusberry"):
    return SheetMon(pos, species, item, "x", (), "")


def pk(species, hp, active=False, fainted=False, mega=False):
    return {
        "species": species,
        "hp_fraction": hp,
        "active": active,
        "fainted": fainted,
        "mega": mega,
    }


OUR = (
    mon(1, "fast"),
    mon(2, "slow"),
    mon(3, "mid"),
    mon(4, "zard", "charizarditey"),
    mon(5, "slow"),
    mon(6, "slow"),
)
THEIR = (
    mon(1, "mid"),
    mon(2, "mid", "choicescarf"),
    mon(3, "fast"),
    mon(4, "slow"),
    mon(5, "slow"),
    mon(6, "slow"),
)


def state(our=None, their=None):
    return {
        "turn": 3,
        "decision_index": 0,
        "game_index": None,
        "set_score_entering_game": None,
        "observations": [],
        "our_pokemon": our
        or [
            pk("fast", 1, True),
            pk("slow", 1, True),
            pk("mid", 0.5),
            pk("zard", 0),
            pk("slow", 0),
            pk("slow", 0),
        ],
        "opp_pokemon": their
        or [
            pk("mid", 1, True),
            pk("mid", 1, True),
            pk("fast", 0),
            pk("slow", 0),
            pk("slow", 0),
            pk("slow", 0),
        ],
    }


def f(joined=None, s=None):
    sheets = {"p1": OUR, "p2": THEIR}
    return F.state_features(
        [s or state()],
        0,
        "p1",
        joined or JoinedTimers(moment="turn_start"),
        sheets,
        DEX,
        None,
        "F",
    )


def test_active_speeds_with_choice_scarf():
    row = f()
    assert row["f_our_active_speed_max"] == 120 and row["f_our_active_speed_min"] == 40
    assert row["f_their_active_speed_max"] == pytest.approx(135)  # 90 x 1.5 Scarf
    assert row["f_our_bench_speed_max"] == 90


def test_who_moves_first_and_pairs_outsped():
    row = f()
    # our 120 beats their 90 and 135? no: 120 < 135. our 40 beats nobody
    assert row["f_our_outspeeds"] == 1  # 120 > 90
    assert row["f_their_outspeeds"] == 3  # 90 > 40, 135 > 40, 135 > 120
    assert row["f_their_first"] == 1 and row["f_our_first"] == 0


def test_tailwind_doubles_its_sides_speed():
    row = f(JoinedTimers(ours=(("tailwind", "side", 2, 2),), moment="turn_start"))
    assert row["f_our_active_speed_max"] == 240
    assert row["f_our_first"] == 1
    assert (
        row["f_our_outspeeds"] == 2
    )  # 240 beats both of theirs; 80 (40x2) beats nobody


def test_trick_room_reverses_the_order():
    row = f(JoinedTimers(field=(("trickroom", "field", 3, 3),), moment="turn_start"))
    assert row["f_our_first"] == 1  # our 40 acts first under Trick Room
    assert row["f_our_outspeeds"] == 3  # 40 under 90 and 135; 120 under 135
    assert row["f_trickroom"] == 1


def test_a_mega_evolved_pokemon_uses_its_mega_speed():
    s = state(
        our=[
            pk("zard", 1, True, mega=True),
            pk("slow", 1, True),
            pk("mid", 0.5),
            pk("fast", 0),
            pk("slow", 0),
            pk("slow", 0),
        ]
    )
    sheets_our = (mon(1, "zard", "charizarditey"), *OUR[1:3], mon(4, "fast"), *OUR[4:])
    row = F.state_features(
        [s],
        0,
        "p1",
        JoinedTimers(moment="turn_start"),
        {"p1": sheets_our, "p2": THEIR},
        DEX,
        None,
        "F",
    )
    assert row["f_our_active_speed_max"] == 130


def test_unseen_threats_that_would_act_before_our_fastest():
    row = f()
    assert row["f_their_unseen_speed_max"] == 120
    assert row["f_their_unseen_outspeeds"] == 0  # 120 does not beat our 120 (a tie)
    assert row["f_our_unseen_speed_max"] == 100  # zard, not mega yet


def test_speed_columns_mirror_our_and_their():
    cols = F.columns("F")
    perm = F.mirror_permutation(cols)
    i = cols.index("f_our_first")
    assert cols[perm[i]] == "f_their_first"
    assert cols[perm[cols.index("f_trickroom")]] == "f_trickroom"
