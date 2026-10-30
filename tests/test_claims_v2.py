"""Tests for wpa/claims_v2.py (Week 6 Task 5): the expert claims, re-scored.

Week 5 built each claim's follow-up positions by editing feature rows, so the
Pokemon coming in were anonymous. Here the follow-ups are made by editing the
board itself (who faints, who comes in from the actual reserve, one turn off
every timer) and the features are computed again by the same code that builds
the training table, so speed, sheet and timer features follow the change.
Report only: nothing here gates.
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from wpa import claims_v2 as C
from wpa.team_sheets import Dex, SheetMon
from wpa.timer_join import JoinedTimers


def sp(spe):
    return {
        "baseStats": {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": spe},
        "types": ["Normal"],
        "abilities": {"0": "X"},
    }


DEX = Dex(
    species={"fast": sp(120), "mid": sp(90), "slow": sp(40), "zard": sp(100)},
    moves={},
    items={"choicescarf": {"megaStone": None}, "sitrusberry": {"megaStone": None}},
)


def mon(pos, species, item="sitrusberry"):
    return SheetMon(pos, species, item, "x", (), "")


SHEETS = {
    "p1": (
        mon(1, "fast"),
        mon(2, "slow"),
        mon(3, "mid"),
        mon(4, "zard"),
        mon(5, "slow"),
        mon(6, "slow"),
    ),
    "p2": (
        mon(1, "mid"),
        mon(2, "mid"),
        mon(3, "fast"),
        mon(4, "zard"),
        mon(5, "slow"),
        mon(6, "slow"),
    ),
}


def pk(species, hp, active=False, fainted=False):
    return {
        "species": species,
        "hp_fraction": hp,
        "active": active,
        "fainted": fainted,
        "mega": False,
    }


def state(our, their, turn=3, observations=()):
    return {
        "turn": turn,
        "decision_index": 0,
        "moment": "turn_start",
        "game_index": None,
        "set_score_entering_game": None,
        "observations": list(observations),
        "our_pokemon": our,
        "opp_pokemon": their,
    }


def their_side(*hp_active, revealed=()):
    """Their mid/mid active with these hit points; the rest unseen unless revealed."""
    side = [pk("mid", hp_active[0], True), pk("mid", hp_active[1], True)]
    side += [pk(s, 0.0) for s in ("fast", "zard", "slow", "slow")]
    for i in revealed:
        side[i] = pk(side[i]["species"], 1.0, True)
    return side


def our_side(hp_fast=1.0, hp_slow=1.0):
    return [pk("fast", hp_fast, True), pk("slow", hp_slow, True)] + [
        pk(s, 0.0) for s in ("mid", "zard", "slow", "slow")
    ]


def game():
    """Turn 3: their two mids are weak; later turns reveal their fast and zard,
    and our mid and zard, so all eight brought Pokemon are known."""
    later_their = their_side(0.0, 0.0)
    later_their[0] = pk("mid", 0.0, fainted=True)
    later_their[1] = pk("mid", 0.0, fainted=True)
    later_their[2] = pk("fast", 1.0, True)
    later_their[3] = pk("zard", 1.0, True)
    later_our = our_side()
    later_our[2] = pk("mid", 1.0)
    later_our[3] = pk("zard", 1.0)
    return [
        state(
            our_side(),
            their_side(0.3, 0.2),
            observations=[{"turn": 3, "weather": "RainDance"}],
        ),
        state(later_our, later_their, turn=5),
    ]


def TW(lo):
    return JoinedTimers(theirs=(("tailwind", "side", lo, lo),), moment="turn_start")


def test_a_turn_passing_ticks_every_timer_and_drops_finished_ones():
    j = JoinedTimers(
        ours=(("tailwind", "side", 2, 2),),
        theirs=(("tailwind", "side", 1, 1), ("taunt", "p2a: Mid", 1, 3)),
        field=(("trickroom", "field", 3, 3),),
        our_counters=(("protect", "p1a: Fast", 1),),
        moment="after_turn",
    )
    t = C.tick(j)
    assert t.ours == (("tailwind", "side", 1, 1),)
    assert t.theirs == (("taunt", "p2a: Mid", 0, 2),)
    assert t.field == (("trickroom", "field", 2, 2),)
    assert t.our_counters == () and t.moment == "turn_start"


def test_the_reserve_is_what_was_brought_but_not_yet_seen():
    g = game()
    assert C.reserve(g, 0, "opp_pokemon") == [2, 3]
    assert C.reserve(g, 0, "our_pokemon") == [2, 3]
    assert C.brought(g, "opp_pokemon") == {0, 1, 2, 3}


def test_a_follow_up_is_the_next_turn_start_and_leaves_the_game_untouched():
    g = game()
    states, j = C.follow_up(
        g, 0, TW(2), [("faint", "opp_pokemon", 0), ("bring_in", "opp_pokemon", 2)]
    )
    s = states[-1]
    assert s["turn"] == 4 and s["decision_index"] == 0 and s["moment"] == "turn_start"
    assert s["opp_pokemon"][0] == pk("mid", 0.0, fainted=True)
    assert s["opp_pokemon"][2] == pk("fast", 1.0, True)
    assert states[-2]["observations"] == []  # the decided turn's own end is not known
    assert g[0]["opp_pokemon"][0]["active"] and g[0]["observations"]
    assert j.theirs == (("tailwind", "side", 1, 1),)


def test_damage_never_knocks_out():
    g = game()
    states, _ = C.follow_up(g, 0, TW(2), [("damage", "our_pokemon", 0, 0.5)])
    assert states[-1]["our_pokemon"][0]["hp_fraction"] == pytest.approx(0.5)
    states, _ = C.follow_up(g, 0, TW(2), [("damage", "our_pokemon", 1, 5.0)])
    assert 0 < states[-1]["our_pokemon"][1]["hp_fraction"] < 0.05


def test_ec001_double_knockout_brings_the_reserve_in_under_their_tailwind():
    g = game()
    tree = C.ec001_tree(g, 0, "p1", TW(2), SHEETS, DEX, None, "ABCDEF")
    (dko,) = tree["double_ko"]
    assert dko[0]["f_their_active_speed_max"] == 240  # fast, Tailwind still up a turn
    assert dko[0]["a_their_fainted"] == 2 and dko[0]["a_their_active"] == 2
    (stall,) = tree["stall"]
    assert stall[0]["f_their_active_speed_max"] == 180  # mid x2
    # one knock-out: we choose which (outer), they choose who comes in (inner)
    assert len(tree["single_ko"]) == 2 and all(len(o) == 2 for o in tree["single_ko"])


def test_ec001_with_tailwind_ending_this_turn_the_reserve_comes_in_without_it():
    g = game()
    tree = C.ec001_tree(g, 0, "p1", TW(1), SHEETS, DEX, None, "F")
    assert tree["double_ko"][0][0]["f_their_active_speed_max"] == 120


def test_ec001_positions_need_their_tailwind_two_active_and_a_known_reserve_of_two():
    g = game()
    assert C.is_ec001(g, 0, TW(2))
    assert C.is_ec001(g, 0, TW(1))
    assert not C.is_ec001(g, 0, TW(3))
    assert not C.is_ec001(g, 0, JoinedTimers(moment="turn_start"))
    g2 = [g[0], state(our_side(), their_side(0.3, 0.2, revealed=(2,)), turn=5)]
    assert not C.is_ec001(g2, 0, TW(2))  # only one of their reserve is known


def test_ec002_sacrifice_brings_in_each_reserve_and_keep_hurts_the_strong_one():
    g = [state(our_side(1.0, 0.2), their_side(1.0, 1.0)), game()[1]]
    assert C.is_ec002(g, 0, JoinedTimers(moment="turn_start"))
    tree = C.ec002_tree(
        g, 0, "p1", JoinedTimers(moment="turn_start"), SHEETS, DEX, None, "ABCDEF"
    )
    assert len(tree["sacrifice"]) == 2  # we choose who comes in
    after = [o[0] for o in tree["sacrifice"]]
    assert {r["f_our_active_speed_min"] for r in after} == {
        90,
        100,
    }  # mid or zard beside fast
    (keep,) = tree["keep"]
    assert keep[0]["a_our_hp_active"] == pytest.approx(0.7)  # 0.5 + 0.2


def test_the_value_of_a_choice_tree_is_our_best_against_their_best_reply():
    tree = {"x": [[0.2, 0.9], [0.5, 0.6]]}
    assert C.value(tree["x"]) == 0.5


def faster_pair_game():
    """Our fast (120) and zard (100) face their two slows (40, 80 under
    Tailwind); their fast and zard wait in the back."""
    our = [
        pk("fast", 1.0, True),
        pk("slow", 0.0),
        pk("mid", 0.0),
        pk("zard", 1.0, True),
        pk("slow", 0.0),
        pk("slow", 0.0),
    ]
    their = [
        pk("mid", 0.0),
        pk("mid", 0.0),
        pk("fast", 0.0),
        pk("zard", 0.0),
        pk("slow", 0.3, True),
        pk("slow", 0.2, True),
    ]
    later = [dict(p) for p in their]
    later[2] = pk("fast", 1.0, True)
    later[3] = pk("zard", 1.0, True)
    later[4] = pk("slow", 0.0, fainted=True)
    later[5] = pk("slow", 0.0, fainted=True)
    later_our = [dict(p) for p in our]
    later_our[2] = pk("mid", 1.0)
    later_our[1] = pk("slow", 1.0)
    return [state(our, their), state(later_our, later, turn=5)]


def test_ec001_premise_our_pair_is_faster_now_and_their_reserve_is_faster_after():
    g = faster_pair_game()
    now = C.features_at(g, 0, "p1", TW(2), SHEETS, DEX, None, "F")
    assert now["f_our_outspeeds"] == 4
    tree = C.ec001_tree(g, 0, "p1", TW(2), SHEETS, DEX, None, "F")
    assert C.ec001_premise(now, tree)  # their fast comes in at 240 against our 120
    tree = C.ec001_tree(g, 0, "p1", TW(1), SHEETS, DEX, None, "F")
    assert not C.ec001_premise(now, tree)  # Tailwind is gone when they come in
    g0 = game()
    now = C.features_at(g0, 0, "p1", TW(2), SHEETS, DEX, None, "F")
    tree = C.ec001_tree(g0, 0, "p1", TW(2), SHEETS, DEX, None, "F")
    assert not C.ec001_premise(now, tree)  # our slow is not faster than their mids


def test_ec002_premise_a_sacrifice_that_gains_speed():
    g = [state(our_side(1.0, 0.2), their_side(1.0, 1.0)), game()[1]]
    tree = C.ec002_tree(
        g, 0, "p1", JoinedTimers(moment="turn_start"), SHEETS, DEX, None, "F"
    )
    assert C.ec002_premise(tree)  # zard (100) for slow (40) outspeeds their mids (90)
    g = [state(our_side(0.2, 1.0), their_side(1.0, 1.0)), game()[1]]
    tree = C.ec002_tree(
        g, 0, "p1", JoinedTimers(moment="turn_start"), SHEETS, DEX, None, "F"
    )
    assert not C.ec002_premise(tree)  # giving up the fast one gains no speed


def test_scoring_takes_each_position_through_its_choice_tree():
    import numpy as np

    records = [
        {
            "premise": True,
            "tree": {"a": [[[0.2], [0.9]], [[0.5], [0.6]]], "b": [[[0.4]]]},
        },
        {"premise": False, "tree": {"a": [[[0.1]]], "b": [[[0.3]]]}},
    ]
    values = C.score(records, lambda X: np.asarray(X)[:, 0])
    assert values == [
        pytest.approx({"a": 0.5, "b": 0.4}),
        pytest.approx({"a": 0.1, "b": 0.3}),
    ]
    s = C.summarise(records, values, ("a",), "b")
    assert s["all"]["positions"] == 2 and s["all"]["agrees"] == 0.5
    assert s["premise"]["positions"] == 1 and s["premise"]["agrees"] == 1.0


def test_the_ec001_threat_is_their_reserve_acting_first_after_a_double_knockout():
    g = faster_pair_game()
    assert C.ec001_threat(C.ec001_tree(g, 0, "p1", TW(2), SHEETS, DEX, None, "F"))
    assert not C.ec001_threat(C.ec001_tree(g, 0, "p1", TW(1), SHEETS, DEX, None, "F"))


def test_a_summary_can_report_extra_subsets():
    records = [{"premise": True, "tree": {}}, {"premise": False, "tree": {}}]
    values = [{"a": 0.5, "b": 0.4}, {"a": 0.1, "b": 0.3}]
    s = C.summarise(records, values, ("a",), "b", {"other": lambda r: not r["premise"]})
    assert s["other"]["positions"] == 1 and s["other"]["agrees"] == 0.0
