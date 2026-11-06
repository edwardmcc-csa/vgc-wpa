"""Tests for wpa/resolver.py (Week 9 Task 2, the plan's M3): everything that can
happen when both sides' choices play out, each with its chance.

The plan's golden cases are checked against the Smogon calculator run on its
own: a known knock-out range, a 50/50 knock-out roll, an accuracy check, a
critical-hit branch; every list adds up to 1; two different rolls that both leave
the target standing give two different boards, never one averaged board.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from wpa import damage as DM
from wpa import resolver as R
from wpa.choices import Action
from wpa.features import _board_state
from wpa.spreads import Spread, damage_request
from wpa.team_sheets import SheetMon, load_dexes

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


@pytest.fixture(scope="module")
def dex():
    return load_dexes(ROOT / "pokemon-showdown")["regma"]


@pytest.fixture(scope="module")
def moves():
    return R.load_moves(ROOT / "pokemon-showdown", "championsregma")


@pytest.fixture(scope="module")
def calc():
    c = DM.Calc()
    yield c
    c.close()


FULL = Spread("adamant", (32, 32, 0, 0, 0, 2), 1.0)
BULK = Spread("careful", (32, 0, 32, 0, 0, 2), 1.0)

# p1: Garchomp (attacker) and Kingambit; p2: Incineroar (target) and Whimsicott
SHEETS = {
    "p1": (
        SheetMon(
            1,
            "garchomp",
            "",
            "roughskin",
            ("stoneedge", "dragonclaw", "earthquake", "protect"),
            "",
        ),
        SheetMon(
            2,
            "kingambit",
            "",
            "defiant",
            ("protect", "swordsdance", "kowtowcleave", "suckerpunch"),
            "",
        ),
    ),
    "p2": (
        SheetMon(
            1,
            "incineroar",
            "",
            "blaze",
            ("swordsdance", "protect", "flareblitz", "fakeout"),
            "",
        ),
        SheetMon(
            2,
            "whimsicott",
            "",
            "infiltrator",
            ("protect", "moonblast", "tailwind", "encore"),
            "",
        ),
    ),
}
SPREADS = {("p1", 0): FULL, ("p1", 1): FULL, ("p2", 0): BULK, ("p2", 1): BULK}


def mon(species, hp=1.0):
    return {
        "species": species,
        "hp_fraction": hp,
        "fainted": False,
        "active": True,
        "mega": False,
        "boosts": {},
        "status": "",
        "item": "",
        "moved": False,
        "last_move": "",
        "protect_streak": 0,
        "rev_moves": [],
        "rev_item": "",
        "rev_ability": "",
    }


def board(target_hp=1.0):
    return {
        "p1": [mon("garchomp"), mon("kingambit")],
        "p2": [mon("incineroar", target_hp), mon("whimsicott")],
    }


def resolver(dex, moves, calc):
    return R.Resolver(dex, moves, calc, SHEETS, SPREADS)


def attack(move, target_hp=1.0, *, dex, moves, calc):
    acts = {
        "p1": (
            Action(0, "move", move=move, target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
    }
    return resolver(dex, moves, calc).resolve(board(target_hp), R.Field(), acts)


def rolls(calc, dex, move, crit=False, target_hp=1.0):
    st = _board_state(mon("incineroar", target_hp))
    req = damage_request(
        SHEETS["p1"][0],
        _board_state(mon("garchomp")),
        FULL,
        SHEETS["p2"][0],
        st,
        BULK,
        move,
        dex,
        crit=crit,
    )
    ans = calc.run([req])[0]
    return ans["rolls"], ans["max_hp"]


def p_of(outcomes, pred):
    return sum(o.prob for o in outcomes if pred(o))


def test_every_list_of_outcomes_adds_up_to_one(dex, moves, calc):
    for move in ("stoneedge", "dragonclaw", "earthquake"):
        outs = attack(move, dex=dex, moves=moves, calc=calc)
        assert abs(sum(o.prob for o in outs) - 1) < 1e-9


def test_an_accuracy_check_misses_as_often_as_the_move_says(dex, moves, calc):
    # Stone Edge: 80% accurate; Incineroar starts at full, so any hit damages it
    outs = attack("stoneedge", dex=dex, moves=moves, calc=calc)
    untouched = p_of(outs, lambda o: o.sides["p2"][0]["hp_fraction"] == 1.0)
    assert abs(untouched - 0.2) < 1e-9


def test_the_critical_hit_branch_has_its_chance_and_its_own_damage(dex, moves, calc):
    # Stone Edge has a high critical-hit ratio: 1 in 8, on the 80% that hit
    normal, max_hp = rolls(calc, dex, "stoneedge")
    crit, _ = rolls(calc, dex, "stoneedge", crit=True)
    assert min(crit) > max(normal)  # the two sets of boards do not overlap
    crit_hp = {round((max_hp - d) / max_hp, 9) for d in crit}
    outs = attack("stoneedge", dex=dex, moves=moves, calc=calc)
    p_crit = p_of(outs, lambda o: round(o.sides["p2"][0]["hp_fraction"], 9) in crit_hp)
    assert abs(p_crit - 0.8 / 8) < 1e-9


def test_a_known_knock_out_range_and_a_50_50_roll(dex, moves, calc):
    # Dragon Claw never misses; put Incineroar where exactly 8 of the 16 rolls
    # knock it out, so a normal hit is a coin flip and a critical hit always does
    normal, max_hp = rolls(calc, dex, "dragonclaw")
    assert normal[7] < normal[8]
    hp = Fraction(normal[8], max_hp)
    outs = attack("dragonclaw", float(hp), dex=dex, moves=moves, calc=calc)
    crit, _ = rolls(calc, dex, "dragonclaw", crit=True, target_hp=float(hp))
    assert min(crit) >= normal[8]
    p_ko = p_of(outs, lambda o: o.sides["p2"][0]["fainted"])
    assert abs(p_ko - (Fraction(23, 24) * Fraction(1, 2) + Fraction(1, 24))) < 1e-9


def test_two_different_rolls_leave_two_different_boards(dex, moves, calc):
    normal, _ = rolls(calc, dex, "dragonclaw")
    outs = attack("dragonclaw", dex=dex, moves=moves, calc=calc)
    standing = {
        o.sides["p2"][0]["hp_fraction"] for o in outs if not o.sides["p2"][0]["fainted"]
    }
    assert len(standing) >= len(set(normal))  # never averaged into one


def test_protect_blocks_the_attack_and_counts_up(dex, moves, calc):
    acts = {
        "p1": (
            Action(0, "move", move="dragonclaw", target=("foe", 0)),
            Action(1, "move", move="swordsdance"),
        ),
        "p2": (Action(0, "move", move="protect"), Action(1, "move", move="protect")),
    }
    outs = resolver(dex, moves, calc).resolve(board(), R.Field(), acts)
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)
    assert all(o.sides["p2"][0]["protect_streak"] == 1 for o in outs)
    assert all(o.sides["p1"][1]["boosts"] == {"atk": 2} for o in outs)


def test_a_second_protect_in_a_row_works_a_third_of_the_time(dex, moves, calc):
    b = board()
    b["p2"][0]["protect_streak"] = 1
    acts = {
        "p1": (
            Action(0, "move", move="dragonclaw", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (Action(0, "move", move="protect"), Action(1, "move", move="protect")),
    }
    outs = resolver(dex, moves, calc).resolve(b, R.Field(), acts)
    safe = p_of(outs, lambda o: o.sides["p2"][0]["hp_fraction"] == 1.0)
    assert abs(safe - 1 / 3) < 1e-9


def test_tailwind_lasts_four_turns_counting_this_one(dex, moves, calc):
    acts = {
        "p1": (Action(0, "move", move="protect"), Action(1, "move", move="protect")),
        "p2": (Action(0, "move", move="protect"), Action(1, "move", move="tailwind")),
    }
    outs = resolver(dex, moves, calc).resolve(board(), R.Field(), acts)
    assert {o.field.sides["p2"].get("tailwind") for o in outs} == {3}


def test_a_faster_pokemon_knocked_out_first_does_not_act(dex, moves, calc):
    # Incineroar at 1% is knocked out by Sucker Punch (priority) before Flare Blitz
    b = board(0.01)
    acts = {
        "p1": (
            Action(0, "move", move="protect"),
            Action(1, "move", move="suckerpunch", target=("foe", 0)),
        ),
        "p2": (
            Action(0, "move", move="flareblitz", target=("foe", 1)),
            Action(1, "move", move="protect"),
        ),
    }
    outs = resolver(dex, moves, calc).resolve(b, R.Field(), acts)
    assert all(o.sides["p2"][0]["fainted"] for o in outs)
    assert all(o.sides["p1"][1]["hp_fraction"] == 1.0 for o in outs)


def test_a_cap_merges_boards_on_a_coarser_grid_and_keeps_every_chance(dex, moves, calc):
    acts = {
        "p1": (Action(0, "move", move="earthquake"), Action(1, "move", move="protect")),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="moonblast", target=("foe", 0)),
        ),
    }
    full = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(
        board(), R.Field(), acts
    )
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS, resolution=0.01, cap=4)
    small = rv.resolve(board(), R.Field(), acts)
    assert len(small) < len(full) and rv.coarsest > 0.01
    assert abs(sum(o.prob for o in small) - 1) < 1e-9

    def ko(outs):
        return p_of(outs, lambda o: o.sides["p1"][0]["fainted"])

    assert abs(ko(small) - ko(full)) < 1e-9  # knock-outs are never merged away


def _with(sheets_p2_0):
    sheets = dict(SHEETS, p2=(sheets_p2_0, SHEETS["p2"][1]))
    return sheets


def test_armor_tail_blocks_priority_moves_at_its_side(dex, moves, calc):
    fari = SheetMon(1, "farigiraf", "", "armortail", ("protect", "swordsdance"), "")
    sheets = _with(fari)
    b = board()
    b["p2"][0]["species"] = "farigiraf"
    acts = {
        "p1": (
            Action(0, "move", move="protect"),
            Action(1, "move", move="suckerpunch", target=("foe", 1)),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="moonblast", target=("foe", 1)),
        ),
    }
    outs = R.Resolver(dex, moves, calc, sheets, SPREADS).resolve(b, R.Field(), acts)
    assert all(
        o.sides["p2"][1]["hp_fraction"] == 1.0 for o in outs
    )  # Whimsicott untouched


def test_psychic_terrain_blocks_priority_moves_at_grounded_targets(dex, moves, calc):
    acts = {
        "p1": (
            Action(0, "move", move="protect"),
            Action(1, "move", move="suckerpunch", target=("foe", 0)),
        ),
        "p2": (
            Action(0, "move", move="knockoff", target=("foe", 1)),
            Action(1, "move", move="protect"),
        ),
    }
    plain = resolver(dex, moves, calc).resolve(board(), R.Field(), acts)
    assert any(o.sides["p2"][0]["hp_fraction"] < 1.0 for o in plain)
    fld = R.Field(terrain="psychicterrain", terrain_left=3)
    outs = resolver(dex, moves, calc).resolve(board(), fld, acts)
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)  # grounded


def test_lightning_rod_draws_single_target_electric_moves(dex, moves, calc):
    rod = SheetMon(2, "raichu", "", "lightningrod", ("protect",), "")
    sheets = dict(SHEETS, p2=(SHEETS["p2"][0], rod))
    spreads = dict(SPREADS)
    b = board()
    b["p2"][1]["species"] = "raichu"
    sheets = dict(
        sheets,
        p1=(
            SheetMon(
                1, "archaludon", "", "stamina", ("electroshot", "thunderbolt"), ""
            ),
            SHEETS["p1"][1],
        ),
    )
    b["p1"][0]["species"] = "archaludon"
    acts = {
        "p1": (
            Action(0, "move", move="thunderbolt", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="swordsdance"),
        ),
    }
    outs = R.Resolver(dex, moves, calc, sheets, spreads).resolve(b, R.Field(), acts)
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)  # drawn to Raichu
    assert all(o.sides["p2"][1]["hp_fraction"] == 1.0 for o in outs)  # which absorbs it
