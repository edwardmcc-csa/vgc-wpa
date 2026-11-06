"""Tests for wpa/choices.py (Week 9 Task 1): the choices on offer at a
move-selection decision point, and the choices the log shows players making."""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_board_actions import T1, log
from tests.test_board_effects import at_turn_start
from wpa import choices as C
from wpa.team_sheets import Dex, SheetMon, sheets_from_log

MOVES = {
    "tailwind": {"target": "allySide", "category": "Status"},
    "rockslide": {"target": "allAdjacentFoes", "category": "Physical"},
    "protect": {"target": "self", "category": "Status"},
    "fakeout": {"target": "normal", "category": "Physical"},
    "moonblast": {"target": "normal", "category": "Special"},
    "flareblitz": {"target": "normal", "category": "Physical"},
    "helpinghand": {"target": "adjacentAlly", "category": "Status"},
}
DEX = Dex(species={}, moves=MOVES, items={})


def test_each_active_pokemon_gets_its_moves_and_targets_and_switches():
    lg = log(T1)
    s = at_turn_start(lg, 1, role="p2")
    sheet = sheets_from_log(lg)["p2"]
    opts = C.options(
        s["our_pokemon"], s["opp_pokemon"], sheet, DEX, brought={0, 1, 2, 3}
    )
    inci = opts[0]
    moves = {(a.move, a.target) for a in inci if a.kind == "move"}
    # Fake Out at either foe or at its ally Fini
    assert moves == {
        ("fakeout", ("foe", 0)),
        ("fakeout", ("foe", 1)),
        ("fakeout", ("ally", 1)),
    }
    assert {a.switch_to for a in inci if a.kind == "switch"} == {2, 3}
    fini = opts[1]
    assert {a.target for a in fini if a.kind == "move"} == {
        ("foe", 0),
        ("foe", 1),
        ("ally", 0),
    }


def test_moves_without_a_target_choice_have_none():
    lg = log(T1)
    s = at_turn_start(lg, 1, role="p1")
    sheet = sheets_from_log(lg)["p1"]
    opts = C.options(s["our_pokemon"], s["opp_pokemon"], sheet, DEX, brought={0, 1})
    assert [(a.move, a.target) for a in opts[0]] == [("tailwind", None)]
    assert [(a.move, a.target) for a in opts[1]] == [("rockslide", None)]


def test_fake_out_is_offered_only_before_the_pokemon_has_moved():
    lg = log(T1)
    s = at_turn_start(lg, 2, role="p2")
    sheet = sheets_from_log(lg)["p2"]
    opts = C.options(s["our_pokemon"], s["opp_pokemon"], sheet, DEX, brought={0, 1})
    assert not any(a.move == "fakeout" for a in opts[0])


def test_a_choice_is_one_option_per_active_and_two_cannot_switch_to_the_same_one():
    a = C.Action(0, "switch", switch_to=2)
    b = C.Action(1, "switch", switch_to=2)
    c = C.Action(1, "switch", switch_to=3)
    m = C.Action(1, "move", move="protect")
    pairs = C.joint({0: [a], 1: [b, c, m]})
    assert (a, b) not in pairs and (a, c) in pairs and (a, m) in pairs
    assert len(pairs) == 2


def test_only_one_pokemon_a_side_mega_evolves():
    x = C.Action(0, "move", move="protect", mega=True)
    y = C.Action(1, "move", move="protect", mega=True)
    z = C.Action(1, "move", move="protect")
    assert C.joint({0: [x], 1: [y, z]}) == [(x, z)]


def test_a_mega_stone_holder_that_can_still_mega_evolve_gets_each_move_both_ways():
    dex = Dex(
        species={"charizard": {}, "charizardmegay": {}},
        moves={"heatwave": {"target": "allAdjacentFoes", "category": "Special"}},
        items={"charizarditey": {"megaStone": {"Charizard": "Charizard-Mega-Y"}}},
    )
    sheet = (SheetMon(1, "charizard", "charizarditey", "blaze", ("heatwave",), ""),)
    me = [
        {
            "species": "charizard",
            "active": True,
            "fainted": False,
            "hp_fraction": 1.0,
            "mega": False,
            "item": "charizarditey",
            "moved": False,
            "last_move": "",
        }
    ]
    foe = [{"species": "x", "active": True, "fainted": False, "hp_fraction": 1.0}]
    opts = C.options(me, foe, sheet, dex, brought={0})
    assert {a.mega for a in opts[0]} == {True, False}
    me[0]["mega"] = True  # already Mega Evolved
    assert {a.mega for a in C.options(me, foe, sheet, dex, brought={0})[0]} == {False}


def test_the_log_shows_each_choice_made_and_why_some_cannot_be_seen():
    turns = C.turns(log(T1), DEX)
    t1 = {t.role: t for t in turns if t.turn == 1}
    assert t1["p1"].taken[0] == "cant"  # Whim flinched
    assert t1["p1"].taken[1] == C.Action(1, "move", move="rockslide")
    assert t1["p2"].taken[0] == C.Action(0, "move", move="fakeout", target=("foe", 0))
    assert t1["p2"].taken[1] == C.Action(1, "move", move="moonblast", target=("foe", 1))


def test_a_switch_before_any_move_is_the_choice_of_the_pokemon_it_replaces():
    back = "|t:|2\n|switch|p2a: Rime|Rime, L50|100/100\n|move|p1b: Rock|Rock Slide|p2b: Fini"
    turns = C.turns(log(T1, back), DEX)
    t2 = {t.role: t for t in turns if t.turn == 2}
    assert t2["p2"].taken[0] == C.Action(0, "switch", switch_to=2)


def test_the_real_data_check_finds_every_choice_in_the_list():
    lg = log(T1)
    counts = C.check(lg, DEX)
    assert counts["in"] == 3 and counts["out"] == 0 and counts["cant"] == 1
