"""Week 12 Task 5: hidden opponent sets. Without the opponent's team sheet, each
of their Pokemon's set is a belief: what the game has shown (a move used, an
item shown, an ability announced) is kept, and the rest is the likeliest from
the usage statistics. Team preview shows the six species; a Pokemon with a
Mega form may be holding its stone, which the statistics count apart. No two
Pokemon on a team hold the same item (the Item Clause)."""

from __future__ import annotations

import json

import pytest

from wpa import hidden as H
from wpa.team_sheets import Dex, SheetMon

DEX = Dex(
    species={
        "incineroar": {"name": "Incineroar", "abilities": {"0": "Blaze"}},
        "rillaboom": {"name": "Rillaboom", "abilities": {"0": "Overgrow"}},
        "garchomp": {"name": "Garchomp", "abilities": {"0": "Sand Veil"}},
        "floetteeternal": {
            "name": "Floette-Eternal",
            "abilities": {"0": "Flower Veil", "H": "Symbiosis"},
        },
        "floettemega": {
            "name": "Floette-Mega",
            "isMega": True,
            "abilities": {"0": "Fairy Aura"},
        },
    },
    moves={},
    items={
        "floettite": {
            "name": "Floettite",
            "megaStone": {"Floette-Eternal": "Floette-Mega"},
        },
        "sitrusberry": {"name": "Sitrus Berry", "megaStone": None},
    },
)

DATA = {
    "Incineroar": {
        "Raw count": 1000,
        "Abilities": {"intimidate": 990, "blaze": 10},
        "Items": {"sitrusberry": 500, "safetygoggles": 300, "nothing": 5},
        "Moves": {
            "fakeout": 950,
            "partingshot": 900,
            "flareblitz": 800,
            "knockoff": 500,
            "protect": 300,
            "": 10,
        },
    },
    "Rillaboom": {
        "Raw count": 800,
        "Abilities": {"grassysurge": 800},
        "Items": {"sitrusberry": 300, "assaultvest": 200, "miracleseed": 100},
        "Moves": {
            "grassyglide": 780,
            "fakeout": 760,
            "woodhammer": 600,
            "uturn": 500,
            "highhorsepower": 300,
        },
    },
    "Floette-Eternal": {
        "Raw count": 10,
        "Abilities": {"flowerveil": 10},
        "Items": {"choicescarf": 6, "leftovers": 4},
        "Moves": {
            "lightofruin": 10,
            "dazzlinggleam": 8,
            "trick": 7,
            "moonblast": 6,
            "protect": 5,
        },
    },
    "Floette-Mega": {
        "Raw count": 900,
        "Abilities": {"fairyaura": 900},
        "Items": {"floettite": 900},
        "Moves": {
            "lightofruin": 880,
            "dazzlinggleam": 850,
            "protect": 800,
            "calmmind": 400,
            "moonblast": 300,
        },
    },
}
SETS = H.set_usages(DATA)


def shown(pos, species, moves=(), item="", ability=""):
    """A Pokemon as `features.public_sheet` gives it: what the game showed."""
    return SheetMon(pos, species, item, ability, tuple(moves), "")


def test_what_the_game_showed_is_kept_and_the_rest_is_the_likeliest():
    (inc,) = H.belief_sheet([shown(1, "incineroar", ["knockoff"])], SETS, DEX)
    assert inc == SheetMon(
        1,
        "incineroar",
        "sitrusberry",
        "intimidate",
        ("knockoff", "fakeout", "partingshot", "flareblitz"),
        "",
    )
    (inc,) = H.belief_sheet(
        [shown(1, "incineroar", item="safetygoggles", ability="blaze")], SETS, DEX
    )
    assert (inc.item, inc.ability) == ("safetygoggles", "blaze")
    assert inc.moves == ("fakeout", "partingshot", "flareblitz", "knockoff")


def test_no_two_pokemon_on_a_team_hold_the_same_item():
    # Incineroar holds Sitrus Berry more often (62% against 50%): it gets it
    inc, ril = H.belief_sheet(
        [shown(1, "incineroar"), shown(2, "rillaboom")], SETS, DEX
    )
    assert (inc.item, ril.item) == ("sitrusberry", "assaultvest")
    # unless the game has shown Rillaboom's
    inc, ril = H.belief_sheet(
        [shown(1, "incineroar"), shown(2, "rillaboom", item="sitrusberry")], SETS, DEX
    )
    assert (inc.item, ril.item) == ("safetygoggles", "sitrusberry")


def test_a_mega_is_believed_when_the_statistics_say_it_is_likelier():
    (flo,) = H.belief_sheet([shown(3, "floetteeternal")], SETS, DEX)
    assert flo.item == "floettite"
    assert flo.moves == ("lightofruin", "dazzlinggleam", "protect", "calmmind")
    assert flo.ability == "flowerveil"  # the sheet's ability is before Mega Evolving
    # an item shown that is not its stone: the statistics' Floette-Eternal
    (flo,) = H.belief_sheet([shown(3, "floetteeternal", item="choicescarf")], SETS, DEX)
    assert flo.item == "choicescarf"
    assert flo.moves == ("lightofruin", "dazzlinggleam", "trick", "moonblast")


def test_moves_shown_weigh_the_mega_against_the_rest():
    # Trick: in the non-Mega sets only, so the non-Mega set is likelier
    (flo,) = H.belief_sheet([shown(3, "floetteeternal", ["trick"])], SETS, DEX)
    assert flo.item == "choicescarf"
    assert flo.moves[0] == "trick"


def test_a_species_the_statistics_do_not_list_keeps_what_was_shown():
    (gar,) = H.belief_sheet([shown(4, "garchomp", ["earthquake"])], SETS, DEX)
    assert gar == SheetMon(4, "garchomp", "", "sandveil", ("earthquake",), "")


def test_a_form_the_statistics_count_under_its_species_takes_its_set():
    """The statistics count Sinistcha-Masterpiece as Sinistcha (and Maushold-
    Four as Maushold). With no entry of its own, a form takes its species' set.
    Game 2634478000 turn 4 failed on this: no moves were believed for it, so
    a Sinistcha knocked out before moving had no choice to average over."""
    tea = {"abilities": {"0": "Hospitality"}, "baseSpecies": "Sinistcha"}
    dex = Dex(
        species={
            **DEX.species,
            "sinistcha": {"name": "Sinistcha", **tea},
            "sinistchamasterpiece": {"name": "Sinistcha-Masterpiece", **tea},
        },
        moves={},
        items=DEX.items,
    )
    sets = H.set_usages(
        {
            "Sinistcha": {
                "Raw count": 500,
                "Abilities": {"hospitality": 500},
                "Items": {"sitrusberry": 300, "rockyhelmet": 200},
                "Moves": {
                    "matchagotcha": 480,
                    "ragepowder": 450,
                    "trickroom": 300,
                    "strengthsap": 250,
                    "protect": 100,
                },
            }
        }
    )
    (sin,) = H.belief_sheet([shown(2, "sinistchamasterpiece")], sets, dex)
    assert sin == SheetMon(
        2,
        "sinistchamasterpiece",
        "sitrusberry",
        "hospitality",
        ("matchagotcha", "ragepowder", "trickroom", "strengthsap"),
        "",
    )


def test_a_move_used_this_turn_takes_the_place_of_the_least_likely_one():
    pub = shown(1, "incineroar", ["knockoff"])
    (inc,) = H.belief_sheet([pub], SETS, DEX)
    got = H.with_used(inc, pub, ["willowisp"])
    assert got.moves == ("knockoff", "fakeout", "partingshot", "willowisp")
    assert H.with_used(inc, pub, ["fakeout"]) == inc  # already believed
    two = H.with_used(inc, pub, ["willowisp", "taunt"])
    assert two.moves == ("knockoff", "fakeout", "willowisp", "taunt")


def test_the_board_holds_the_believed_item_until_the_game_shows_one():
    side = [
        {"species": "incineroar", "item": "safetygoggles", "rev_item": ""},
        {"species": "rillaboom", "item": "", "rev_item": "sitrusberry"},  # eaten
    ]
    belief = H.belief_sheet([shown(1, "incineroar"), shown(2, "rillaboom")], SETS, DEX)
    got = H.hidden_side(side, belief)
    assert [m["item"] for m in got] == ["sitrusberry", ""]
    assert side[0]["item"] == "safetygoggles"  # the board itself is left alone


def test_the_statistics_file_gives_each_species_chances(tmp_path):
    name = "2026-06-gen9championsvgc2026regma-1500.json"
    (tmp_path / name).write_text(json.dumps({"data": DATA}), encoding="utf-8")
    store = H.SetStore(tmp_path)
    log = "|t:|1781000000\n|turn|1\n"  # June 2026
    sets = store.for_game("gen9championsvgc2026regma-1", log)
    inc = sets["incineroar"]
    assert inc.count == pytest.approx(1000)
    assert inc.moves["fakeout"] == pytest.approx(0.95)
    assert "" not in inc.moves
    assert inc.items[""] == pytest.approx(5 / 805)  # "nothing": no item
    assert inc.abilities["intimidate"] == pytest.approx(0.99)
    assert store.for_game("gen9championsvgc2026regmb-1", log) == {}
