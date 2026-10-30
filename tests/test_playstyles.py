"""Tests for wpa/playstyles.py (Week 5 Task 4b): the product owner's
play-style archetypes as tags over the open team sheet. PROPOSAL: no headline
number uses these until the PO signs off the rules.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wpa import playstyles as P
from wpa.team_sheets import Dex, SheetMon, sheets_from_log

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)


def sp(atk=80, spa=80, spe=80, hp=80, de=80, sd=80, types=("Normal",), mega=None):
    return {
        "baseStats": {
            "hp": hp,
            "atk": atk,
            "def": de,
            "spa": spa,
            "spd": sd,
            "spe": spe,
        },
        "types": list(types),
        "abilities": {"0": "X"},
    }


def mv(category="Physical", bp=80, target="normal", priority=0):
    return {
        "category": category,
        "basePower": bp,
        "target": target,
        "priority": priority,
    }


DEX = Dex(
    species={
        "fastphys": sp(atk=130, spe=110),
        "fastspec": sp(spa=125, spe=105),
        "midspec": sp(spa=120, spe=85),
        "slowbulk": sp(atk=120, spe=30, hp=110, de=110, sd=100),
        "slowtr": sp(spa=110, spe=40, hp=100, de=90, sd=90),
        "support": sp(atk=60, spe=60),
        "whim": sp(atk=67, spa=77, spe=116, types=("Grass", "Fairy")),
        "fire": sp(types=("Fire",)),
        "water": sp(types=("Water",)),
        "grass": sp(types=("Grass",)),
        "zard": sp(atk=84, spa=109, spe=100, types=("Fire", "Flying")),
        "zardmegay": sp(atk=104, spa=159, spe=100, types=("Fire", "Flying")),
    },
    moves={
        "closecombat": mv(),
        "rockslide": mv(bp=75, target="allAdjacentFoes"),
        "heatwave": mv("Special", 95, "allAdjacentFoes"),
        "hypervoice": mv("Special", 90, "allAdjacentFoes"),
        "moonblast": mv("Special", 95),
        "protect": mv("Status", 0, "self", 4),
        "tailwind": mv("Status", 0, "allySide"),
        "trickroom": mv("Status", 0, "all", -7),
        "perishsong": mv("Status", 0, "all"),
        "meanlook": mv("Status", 0, "normal"),
        "followme": mv("Status", 0, "self", 2),
        "swordsdance": mv("Status", 0, "self"),
        "fakeout": mv(bp=40, priority=3),
        "taunt": mv("Status", 0, "normal"),
        "uturn": mv(bp=70),
        "partingshot": mv("Status", 0, "normal"),
        "sunnyday": mv("Status", 0, "all"),
        "snowscape": mv("Status", 0, "all"),
    },
    items={
        "choicespecs": {"megaStone": None},
        "choiceband": {"megaStone": None},
        "assaultvest": {"megaStone": None},
        "sitrusberry": {"megaStone": None},
        "charizarditey": {"megaStone": {"Zard": "Zard-Mega-Y"}},
    },
)


def mon(pos, species, moves, ability="x", item="sitrusberry"):
    return SheetMon(pos, species, item, ability, tuple(moves), "")


def team(*mons):
    return tuple(SheetMon(i, *m[1:]) for i, m in enumerate(mons, start=1))


def m(species, moves, ability="x", item="sitrusberry"):
    return (0, species, item, ability, tuple(moves), "")


HO = team(
    m("fastphys", ["closecombat", "rockslide", "protect"], item="choiceband"),
    m("fastspec", ["heatwave", "moonblast", "protect"], item="choicespecs"),
    m("fastphys", ["closecombat", "protect"]),
    m("whim", ["tailwind", "moonblast", "protect"], ability="prankster"),
    m("fastspec", ["hypervoice", "protect"]),
    m("support", ["protect"]),
)


def test_hyper_offense_uses_the_product_owners_numbers():
    tags = P.team_tags(HO, DEX)
    assert "hyperoffense" in tags
    measures = P.measures(HO, DEX)
    assert measures["damage_dealers"] == 4  # 110+ in the attacking stat they use
    assert measures["fast_damage_dealers"] == 4
    assert measures["priority_tailwind"] == 1
    assert measures["choice_items"] == 2


def test_eighty_speed_is_enough_only_with_a_priority_tailwind_user():
    slow = team(
        m("midspec", ["heatwave", "moonblast"]),
        m("midspec", ["heatwave", "moonblast"]),
        m("midspec", ["hypervoice", "moonblast"]),
        m("whim", ["tailwind", "moonblast"], ability="prankster"),
        m("support", ["protect"]),
        m("support", ["protect"]),
    )
    assert P.measures(slow, DEX)["fast_damage_dealers"] == 3
    assert "hyperoffense" in P.team_tags(slow, DEX)
    no_prankster = tuple(
        SheetMon(x.position, x.species, x.item, "x", x.moves, x.nature) for x in slow
    )
    assert P.measures(no_prankster, DEX)["fast_damage_dealers"] == 0
    assert "hyperoffense" not in P.team_tags(no_prankster, DEX)


def test_defensive_items_or_heavy_disruption_rule_out_hyper_offense():
    vest = tuple(
        SheetMon(
            x.position,
            x.species,
            "assaultvest" if x.position == 1 else x.item,
            x.ability,
            x.moves,
            x.nature,
        )
        for x in HO
    )
    assert "hyperoffense" not in P.team_tags(vest, DEX)
    disruptive = HO[:3] + (
        mon(4, "support", ["fakeout", "taunt"]),
        mon(5, "support", ["fakeout", "followme"]),
        mon(6, "support", ["taunt", "partingshot"]),
    )
    assert "hyperoffense" not in P.team_tags(disruptive, DEX)


def test_trick_room_tags():
    hard = team(
        m("slowtr", ["trickroom", "heatwave"]),
        m("slowtr", ["trickroom", "moonblast"]),
        m("slowbulk", ["closecombat"]),
        m("slowbulk", ["rockslide"]),
        m("slowtr", ["hypervoice"]),
        m("support", ["protect"]),
    )
    assert "hardtrickroom" in P.team_tags(hard, DEX)
    one_setter = hard[:1] + (mon(2, "slowtr", ["moonblast"]),) + hard[2:]
    assert "hardtrickroom" not in P.team_tags(one_setter, DEX)
    tailroom = hard[:5] + (mon(6, "whim", ["tailwind"], ability="prankster"),)
    tags = P.team_tags(tailroom, DEX)
    assert {"tailroom", "hardtrickroom"} <= tags  # a team carries every tag it meets


def test_perish_trap_and_protect_the_queen():
    perish = HO[:4] + (
        mon(5, "support", ["perishsong"]),
        mon(6, "support", ["meanlook"]),
    )
    assert "perishtrap" in P.team_tags(perish, DEX)
    assert "perishtrap" not in P.team_tags(HO, DEX)
    queen = HO[:4] + (
        mon(5, "support", ["followme"]),
        mon(6, "fastphys", ["swordsdance", "closecombat"]),
    )
    assert "protectthequeen" in P.team_tags(queen, DEX)
    # the "queen" must be a damage dealer: a weak setup user is not one
    weak = HO[:4] + (
        mon(5, "support", ["followme"]),
        mon(6, "support", ["swordsdance", "closecombat"]),
    )
    assert "protectthequeen" not in P.team_tags(weak, DEX)


def test_weather_tags_come_from_a_setter_including_a_mega_ability():
    sun = HO[:5] + (
        mon(6, "zard", ["heatwave"], ability="blaze", item="charizarditey"),
    )
    dex = Dex({**DEX.species}, DEX.moves, DEX.items)
    dex.species["zardmegay"]["abilities"] = {"0": "Drought"}
    assert "sun" in P.team_tags(sun, dex)
    snow = HO[:5] + (mon(6, "support", ["snowscape"]),)
    assert "snow" in P.team_tags(snow, DEX)


def test_balance_signals_and_tag():
    bal = team(
        m("fire", ["uturn", "fakeout"], ability="intimidate"),
        m("water", ["moonblast", "protect"]),
        m("grass", ["followme", "protect"]),
        m("slowbulk", ["closecombat", "protect"]),
        m("fastspec", ["hypervoice", "partingshot"]),
        m("support", ["taunt"]),
    )
    s = P.measures(bal, DEX)
    assert s["core_fire_water_grass"] == 1
    assert s["intimidate_cycling"] == 1
    assert s["pivot_users"] == 2
    tags = P.team_tags(bal, DEX)
    assert "balance" in tags and "hyperoffense" not in tags


def test_a_team_can_carry_no_tag():
    plain = tuple(mon(i, "support", ["protect"]) for i in range(1, 7))
    assert P.team_tags(plain, DEX) == frozenset()


# --------------------------------------------------------------------------
# Hold-out with overlapping tags
# --------------------------------------------------------------------------


def test_a_held_out_tag_removes_every_unit_that_carries_it_from_training():
    unit_tags = {
        "u1": {"sun"},
        "u2": {"sun", "tailroom"},
        "u3": {"tailroom"},
        "u4": set(),
    }
    kept, held = P.tag_holdout(unit_tags, {"sun"})
    assert held == {"u1", "u2"}
    assert kept == {"u3", "u4"}
    for u in kept:
        assert not unit_tags[u] & {"sun"}


def test_a_unit_carries_the_tags_of_both_players_in_every_game():
    games = [
        ("set1", {"p1": frozenset({"sun"}), "p2": frozenset({"rain"})}),
        ("set1", {"p1": frozenset({"sun"}), "p2": frozenset({"tailroom"})}),
        ("g9", {"p1": frozenset(), "p2": frozenset()}),
    ]
    assert P.unit_tags(games) == {"set1": {"sun", "rain", "tailroom"}, "g9": set()}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def test_the_report_counts_tags_pairs_and_untagged_by_format():
    report = P.Report()
    report.add("regma", "set1", HO, DEX)
    report.add("regma", "set1", HO[:5] + (mon(6, "zard", ["sunnyday"]),), DEX)
    report.add(
        "regmb", "g2", tuple(mon(i, "support", ["protect"]) for i in range(1, 7)), DEX
    )
    assert report.teams["regma"] == 2 and report.teams["regmb"] == 1
    assert report.tag_teams["regma"]["hyperoffense"] == 2
    assert report.tag_units["regma"]["hyperoffense"] == 1
    assert report.untagged["regmb"] == 1
    text = report.describe()
    assert "regma: 2 team sheets" in text and "hyperoffense" in text


@needs_showdown
def test_real_fixture_team_with_pelipper_is_rain():
    from wpa.team_sheets import load_dexes

    dex = load_dexes(SHOWDOWN)["regma"]
    logs = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
    sheets = sheets_from_log(logs["gen9championsvgc2026regma-2580291588"])
    assert "rain" in P.team_tags(sheets["p2"], dex)
