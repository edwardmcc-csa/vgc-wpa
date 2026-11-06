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


def test_fake_out_is_still_offered_after_the_pokemon_has_moved_where_it_fails():
    # the game lets a player pick it; it fails (Week 8: 233 of 235 such uses did)
    lg = log(T1)
    s = at_turn_start(lg, 2, role="p2")
    sheet = sheets_from_log(lg)["p2"]
    opts = C.options(s["our_pokemon"], s["opp_pokemon"], sheet, DEX, brought={0, 1})
    assert any(a.move == "fakeout" for a in opts[0])


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


def test_a_target_is_the_pokemon_in_that_slot_when_the_turn_began():
    # p2 switches Inci out for Rime first; Rock's Moonblast at p2a lands on Rime,
    # but Rock chose Inci's slot when the turn began
    hit = "|t:|2\n|switch|p2a: Rime|Rime, L50|100/100\n|move|p1b: Rock|Moonblast|p2a: Rime\n"
    t2 = {t.role: t for t in C.turns(log(T1, hit), DEX) if t.turn == 2}
    assert t2["p2"].taken[0] == C.Action(0, "switch", switch_to=2)
    assert t2["p1"].taken[1] == C.Action(1, "move", move="moonblast", target=("foe", 0))


def _turn2(block, role):
    return {t.role: t for t in C.turns(log(T1, block), DEX) if t.turn == 2}[role]


def test_a_blocked_move_hides_its_target_and_does_not_stop_the_blocker():
    # Armor Tail: the log names the blocker in a |cant| line, [of] the attacker
    blocked = (
        "|t:|2\n|move|p2b: Fini|Moonblast||[still]\n"
        "|cant|p1a: Whim|ability: Armor Tail|Moonblast|[of] p2b: Fini\n"
        "|move|p1a: Whim|Tailwind|p1a: Whim"
    )
    p2 = _turn2(blocked, "p2")
    assert p2.taken[1] == C.Action(1, "move", move="moonblast") and 1 in p2.hidden
    assert _turn2(blocked, "p1").taken[0] == C.Action(0, "move", move="tailwind")


def test_an_animation_line_shows_the_hidden_target():
    shown = "|t:|2\n|move|p2b: Fini|Moonblast||[still]\n|-anim|p2b: Fini|Moonblast|p1b: Rock"
    p2 = _turn2(shown, "p2")
    assert p2.taken[1].target == ("foe", 1) and 1 not in p2.hidden


def test_struggle_is_forced_and_a_transformed_pokemon_uses_borrowed_moves():
    assert (
        _turn2("|t:|2\n|move|p2b: Fini|Struggle|p1a: Whim", "p2").taken[1] == "forced"
    )
    copied = (
        "|t:|2\n|-transform|p1a: Whim|p2a: Inci\n|move|p1a: Whim|Fake Out|p2a: Inci"
    )
    assert _turn2(copied, "p1").taken[0] == "transformed"


def test_the_check_counts_hidden_targets_apart():
    blocked = "|t:|2\n|move|p2b: Fini|Moonblast||[still]\n|-fail|p2b: Fini"
    counts = C.check(log(T1, blocked), DEX)
    assert counts["target_hidden"] == 1 and counts["out"] == 0


def test_curse_may_target_its_user_when_not_a_ghost():
    dex = Dex(
        species={},
        moves={"curse": {"target": "normal", "category": "Status"}},
        items={},
    )
    sheet = (SheetMon(1, "chesnaught", "", "", ("curse",), ""),)
    me = [
        {"species": "chesnaught", "active": True, "fainted": False, "hp_fraction": 1.0}
    ]
    foe = [{"species": "x", "active": True, "fainted": False, "hp_fraction": 1.0}]
    targets = {a.target for a in C.options(me, foe, sheet, dex, brought={0})[0]}
    assert targets == {("foe", 0), None}


def test_a_lead_transformed_by_imposter_uses_borrowed_moves_until_it_leaves():
    lg = log(T1, "|t:|2\n|move|p1a: Whim|Fake Out|p2a: Inci").replace(
        "|turn|1",
        "|-transform|p1a: Whim|p2a: Inci|[from] ability: Imposter\n|turn|1",
        1,
    )
    t2 = {t.role: t for t in C.turns(lg, DEX) if t.turn == 2}
    assert t2["p1"].taken[0] == "transformed"


def test_a_confusion_self_hit_hides_the_choice():
    hurt = "|t:|2\n|-activate|p1a: Whim|confusion\n|-damage|p1a: Whim|80/100|[from] confusion"
    assert _turn2(hurt, "p1").taken[0] == "confused"
