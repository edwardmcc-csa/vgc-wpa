"""Week 14 Task 4: the rules Reg M-C adds to the resolver, each against
Showdown's Champions data in the November copy (`pokemon-showdown-mc`), with
M-C's dex and moves; rules that act in every format are also checked there.
"""

from __future__ import annotations

import dataclasses
import shutil

import pytest

from tests.test_resolver import ROOT, SHEETS, SPREADS, board, mon, p_of
from wpa import resolver as R
from wpa.choices import Action
from wpa.team_sheets import SheetMon

MC = ROOT / "pokemon-showdown-mc"
needs_mc = pytest.mark.skipif(
    shutil.which("node") is None or not (MC / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built Reg M-C copy of Showdown's code",
)

RILLABOOM = SheetMon(3, "rillaboom", "", "grassysurge", ("fakeout", "woodhammer"), "")
INDEEDEE = SheetMon(3, "indeedeef", "", "psychicsurge", ("followme", "protect"), "")
QUIET = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
DANCE = (Action(0, "move", move="swordsdance"), Action(1, "move", move="swordsdance"))


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regmc"]
    moves = R.load_moves(MC, "champions")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


def _rv(tools, p1=None, p2=None, bench=None, spreads=None):
    """A resolver on the test sheets (some Pokemon replaced), with `bench`
    as p2's third."""
    dex, moves, calc = tools
    sheets = {r: list(SHEETS[r]) for r in SHEETS}
    for r, swaps in (("p1", p1 or {}), ("p2", p2 or {})):
        for i, kw in swaps.items():
            sheets[r][i] = dataclasses.replace(sheets[r][i], **kw)
    if bench is not None:
        sheets["p2"].append(bench)
    return R.Resolver(
        dex, moves, calc, {r: tuple(v) for r, v in sheets.items()}, spreads or SPREADS
    )


def _go(rv, b, p1, p2, fld=None):
    return rv.resolve(b, fld or R.Field(), {"p1": p1, "p2": p2})


def _no_partial(outs):
    return set().union(*(o.partial for o in outs)) == set()


# --------------------------------------------------------------------------
# Terrain Seeds (Grassy Seed on 13% of October's best-of-three teams, Psychic
# Seed 10%, Electric Seed 4%)
# --------------------------------------------------------------------------


@needs_mc
def test_a_seed_is_used_when_its_terrain_starts(tools):
    """Rillaboom comes in (Grassy Surge): every Pokemon on the field holding a
    Grassy Seed gets +1 Defense and the seed is used up (Showdown:
    onTerrainChange)."""
    rv = _rv(tools, bench=RILLABOOM)
    b = board()
    b["p1"][0]["item"] = "grassyseed"  # Garchomp
    b["p1"][1]["item"] = "psychicseed"  # Kingambit: not this terrain
    b["p2"].append(dict(mon("rillaboom"), active=False))
    sw = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    outs = _go(rv, b, QUIET, sw)
    assert outs and _no_partial(outs)
    for o in outs:
        g, k = o.sides["p1"]
        assert g["boosts"] == {"def": 1} and g["item"] == ""
        assert g["rev_item"] == "grassyseed"
        assert k["boosts"] == {} and k["item"] == "psychicseed"
        assert o.field.terrain == "grassyterrain"


@needs_mc
def test_a_seed_is_used_on_coming_in_to_its_terrain(tools):
    sheets_p2_2 = dataclasses.replace(RILLABOOM, ability="overgrow")
    rv = _rv(tools, bench=sheets_p2_2)
    b = board()
    b["p2"].append(dict(mon("rillaboom"), active=False, item="psychicseed"))
    sw = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    fld = R.Field(terrain="psychicterrain", terrain_left=3)
    outs = _go(rv, b, QUIET, sw, fld)
    assert _no_partial(outs)
    for o in outs:
        r = o.sides["p2"][2]
        assert r["active"] and r["boosts"] == {"spd": 1} and r["item"] == ""


@needs_mc
def test_a_seed_used_up_turns_on_unburden(tools):
    """Sneasler (Unburden, 36% of teams) with a Grassy Seed: Speed doubles
    once the seed is used, so it moves before a faster foe it was slower
    than."""
    rv = _rv(
        tools,
        p1={1: {"species": "sneasler", "ability": "unburden", "item": "grassyseed"}},
    )
    b = board()
    b["p1"][1].update(species="sneasler", item="grassyseed")
    fld = R.Field(terrain="grassyterrain", terrain_left=3)
    slow = rv._speed(R._World(1.0, b, fld, set()), "p1", 1)
    b["p1"][1].update(item="", rev_item="grassyseed")
    fast = rv._speed(R._World(1.0, b, fld, set()), "p1", 1)
    assert fast == pytest.approx(2 * slow, rel=0.01)


# --------------------------------------------------------------------------
# Abilities a hit sets off (in every format; neither modelled nor marked before)
# --------------------------------------------------------------------------

LEER = (Action(0, "move", move="leer"), Action(1, "move", move="leer"))


def _hit_by(tools, move, ability, hp=0.5, at=0):
    """Garchomp (p1, first) uses `move` at Incineroar (p2, first; or
    Whimsicott, `at` 1), whose ability is `ability`; both use Leer, Kingambit
    protects. Only abilities Champions has: the calculator knows no other."""
    rv = _rv(tools, p2={at: {"ability": ability}})
    b = board()
    b["p2"][at]["hp_fraction"] = hp
    p1 = (Action(0, "move", move=move, target=("foe", at)), QUIET[1])
    return rv, _go(rv, b, p1, LEER)


@needs_mc
@pytest.mark.parametrize(
    "ability, move, heal, boosts",
    [
        ("voltabsorb", "thunderbolt", True, {}),
        ("voltabsorb", "thunderwave", True, {}),  # a status move too
        ("waterabsorb", "hydropump", True, {}),  # before its accuracy check
        ("eartheater", "earthquake", True, {}),
        ("sapsipper", "woodhammer", False, {"atk": 1}),
        ("sapsipper", "spore", False, {"atk": 1}),
        ("motordrive", "thunderbolt", False, {"spe": 1}),
        ("lightningrod", "thunderbolt", False, {"spa": 1}),
    ],
)
def test_an_ability_that_takes_in_a_move_heals_or_raises_a_stat(
    tools, ability, move, heal, boosts
):
    rv, outs = _hit_by(tools, move, ability)
    assert outs and _no_partial(outs)
    full = rv.max_hp("p2", 0)
    want = 0.5 + (full // 4) / full if heal else 0.5  # a quarter, rounded down
    for o in outs:
        inci = o.sides["p2"][0]
        assert inci["hp_fraction"] == pytest.approx(want, abs=0.002)
        assert inci["boosts"] == boosts and inci["status"] == ""
        assert o.sides["p1"][0]["hp_fraction"] == 1.0  # no recoil either


@needs_mc
@pytest.mark.parametrize(
    "ability, move, boosts",
    [
        ("justified", "darkpulse", {"atk": 1}),
        ("rattled", "darkpulse", {"spe": 1}),
        ("thermalexchange", "firepunch", {"atk": 1}),
        ("stamina", "dragonclaw", {"def": 1}),
        ("weakarmor", "dragonclaw", {"def": -1, "spe": 2}),
    ],
)
def test_an_ability_a_damaging_hit_sets_off_changes_its_stages(
    tools, ability, move, boosts
):
    _rv0, outs = _hit_by(tools, move, ability, hp=1.0)
    hit = [o for o in outs if 0 < o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit and _no_partial(outs)
    for o in hit:
        assert o.sides["p2"][0]["boosts"] == boosts


@needs_mc
def test_thermal_exchange_cannot_be_burned(tools):
    rv, outs = _hit_by(tools, "willowisp", "thermalexchange", hp=1.0, at=1)
    assert outs and not any(o.sides["p2"][1]["status"] for o in outs)


@needs_mc
def test_moxie_raises_attack_on_a_knock_out(tools):
    """Salamence (Moxie): +1 Attack when its move knocks a Pokemon out."""
    rv = _rv(tools, p1={0: {"ability": "moxie"}})
    b = board()
    b["p2"][0]["hp_fraction"] = 0.05
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert _no_partial(outs)
    ko = [o for o in outs if o.sides["p2"][0]["fainted"]]
    assert ko and all(o.sides["p1"][0]["boosts"].get("atk") == 1 for o in ko)


@needs_mc
def test_seed_sower_sets_grassy_terrain_when_hit(tools):
    """Arboliva (Seed Sower, Reg M-C)."""
    _rv0, outs = _hit_by(tools, "dragonclaw", "seedsower", hp=1.0)
    for o in outs:
        hit = o.sides["p2"][0]["hp_fraction"] < 1.0
        assert (o.field.terrain == "grassyterrain") == hit


@needs_mc
@pytest.mark.parametrize(
    "ability, move, at",
    [
        ("limber", "thunderwave", 0),
        ("insomnia", "spore", 0),
        ("purifyingsalt", "willowisp", 1),
        ("leafguard", "willowisp", 1),  # in the sun
        ("magmaarmor", "willowisp", 1),  # not burn: a control, below
    ],
)
def test_an_ability_that_keeps_a_status_off(tools, ability, move, at):
    """Not modelled in any format before (found writing Thermal Exchange)."""
    rv = _rv(tools, p2={at: {"ability": ability}})
    b = board()
    p1 = (Action(0, "move", move=move, target=("foe", at)), QUIET[1])
    sun = R.Field(weather="sunnyday", weather_left=3)
    outs = _go(rv, b, p1, LEER, sun if ability == "leafguard" else None)
    got = p_of(outs, lambda o: o.sides["p2"][at]["status"] != "")
    assert got == (pytest.approx(0.85, abs=0.001) if ability == "magmaarmor" else 0)


# --------------------------------------------------------------------------
# Items and moves Reg M-C adds (or makes common)
# --------------------------------------------------------------------------


def _bench3(tools, p2=None):
    """p2 with Sinistcha on the bench (third)."""
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    rv = _rv(tools, p2=p2, bench=sin)
    b = board()
    b["p2"].append(dict(mon("sinistcha"), active=False))
    return rv, b


@needs_mc
def test_an_air_balloon_pops_when_hit(tools):
    rv = _rv(tools)
    b = board()
    b["p2"][0]["item"] = "airballoon"
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    for o in _go(rv, b, p1, LEER):
        hit = o.sides["p2"][0]["hp_fraction"] < 1.0
        assert (o.sides["p2"][0]["item"] == "") == hit


@needs_mc
def test_a_red_card_sends_the_attacker_out_for_a_random_one(tools):
    """Red Card: the attacker that hit it is dragged out, replaced at random
    (Showdown: dragIn), and the card is used."""
    dex, moves, calc = tools
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    sheets = {"p1": SHEETS["p1"] + (sin,), "p2": SHEETS["p2"]}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p1"].append(dict(mon("sinistcha"), active=False))
    b["p2"][0]["item"] = "redcard"
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert _no_partial(outs)
    for o in outs:
        hit = o.sides["p2"][0]["hp_fraction"] < 1.0
        assert o.sides["p1"][0]["active"] != hit and o.sides["p1"][2]["active"] == hit
        assert (o.sides["p2"][0]["item"] == "") == hit


@needs_mc
def test_an_eject_button_switch_in_comes_from_the_forced_switch_model(tools):
    dex, moves, calc = tools
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    sheets = {"p1": SHEETS["p1"], "p2": SHEETS["p2"] + (sin,)}
    asked = []

    def chooser(sides, fld, role, bench):
        asked.append(role)
        return [1.0]

    rv = R.Resolver(dex, moves, calc, sheets, SPREADS, switch_in=chooser)
    b = board()
    b["p2"].append(dict(mon("sinistcha"), active=False))
    b["p2"][0]["item"] = "ejectbutton"
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert asked and set(asked) == {"p2"} and _no_partial(outs)


@needs_mc
def test_a_normal_gem_is_used_up_by_a_normal_move(tools):
    rv = _rv(tools)
    b = board()
    b["p1"][0]["item"] = "normalgem"
    p1 = (Action(0, "move", move="bodyslam", target=("foe", 0)), QUIET[1])
    for o in _go(rv, b, p1, LEER):
        hit = o.sides["p2"][0]["hp_fraction"] < 1.0
        assert (o.sides["p1"][0]["item"] == "") == hit


@needs_mc
def test_leek_raises_farfetchds_critical_hit_chance(tools):
    rv = _rv(tools, p1={0: {"species": "sirfetchd", "ability": "steadfast"}})
    b = board()
    b["p1"][0].update(species="sirfetchd", item="leek")
    a = Action(0, "move", move="closecombat", target=("foe", 0))
    w = R._World(1.0, b, R.Field(), set())
    assert rv._crit_chance("p1", a, rv.move("closecombat"), w, ("p2", 0)) == 0.5


@needs_mc
def test_meteor_assault_needs_a_turn_to_recharge(tools):
    rv = _rv(tools)
    b = board()
    p1 = (Action(0, "move", move="meteorassault", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit and all(o.sides["p1"][0].get("recharge") for o in hit)
    b2 = board()
    b2["p1"][0]["recharge"] = 1
    again = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    for o in _go(rv, b2, again, LEER):
        assert o.sides["p2"][0]["hp_fraction"] == 1.0  # it could not move
        assert "recharge" not in o.sides["p1"][0]


@needs_mc
def test_after_glaive_rush_moves_at_the_user_never_miss_and_hit_twice_as_hard(tools):
    """Until it moves again (Showdown: onAccuracy true, onSourceModifyDamage
    x2); the board keeps it from the log's silent line."""
    rv = _rv(tools)
    plain, rushed = board(), board()
    rushed["p1"][0]["glaiverush"] = 1
    a = Action(0, "move", move="hydropump", target=("foe", 0))
    m = rv.move("hydropump")
    w0 = R._World(1.0, plain, R.Field(), set())
    w1 = R._World(1.0, rushed, R.Field(), set())
    assert rv._accuracy(w0, "p2", a, m, ("p1", 0)) == pytest.approx(0.8)
    assert rv._accuracy(w1, "p2", a, m, ("p1", 0)) == 1.0
    base = rv._rolls(w0, "p2", a, m, ("p1", 0), False)
    two = rv._rolls(w1, "p2", a, m, ("p1", 0), False)
    assert [d for _p, d in two] == [2 * d for _p, d in base]
    p1 = (Action(0, "move", move="swordsdance"), QUIET[1])
    for o in _go(rv, rushed, p1, LEER):
        assert "glaiverush" not in o.sides["p1"][0]  # it moved: over


@needs_mc
def test_revival_blessing_brings_back_the_one_fainted_at_half(tools):
    rv, b = _bench3(tools)
    b["p2"][2].update(fainted=True, hp_fraction=0.0)
    p2 = (Action(0, "move", move="revivalblessing"), Action(1, "move", move="protect"))
    outs = _go(rv, b, QUIET, p2)
    assert _no_partial(outs)
    for o in outs:
        s = o.sides["p2"][2]
        assert not s["fainted"] and s["hp_fraction"] == pytest.approx(0.5, abs=0.01)


@needs_mc
def test_milk_drink_can_heal_the_ally_in_champions(tools):
    rv = _rv(tools)
    b = board()
    b["p2"][1]["hp_fraction"] = 0.3
    p2 = (
        Action(0, "move", move="milkdrink", target=("ally", 1)),
        Action(1, "move", move="protect"),
    )
    outs = _go(rv, b, QUIET, p2)
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p2"][1]["hp_fraction"] == pytest.approx(0.8, abs=0.01)


@needs_mc
def test_court_change_swaps_the_two_sides_conditions(tools):
    rv = _rv(tools)
    fld = R.Field(sides={"p1": {"stealthrock": 1}, "p2": {"tailwind": 3}})
    p2 = (Action(0, "move", move="courtchange"), Action(1, "move", move="protect"))
    outs = _go(rv, board(), QUIET, p2, fld)
    assert _no_partial(outs)
    for o in outs:
        assert o.field.sides["p2"].get("stealthrock") == 1
        assert o.field.sides["p1"].get("tailwind")


def test_the_board_keeps_a_recharge_and_glaive_rush_from_the_log():
    from tests.test_board_effects import at_turn_start
    from tests.test_more_mechanics import _mon, _turns

    log = _turns(
        "|t:|1\n|move|p1a: Whim|Meteor Assault|p2a: Inci\n|-damage|p2a: Inci|40/100\n"
        "|-mustrecharge|p1a: Whim\n"
        "|move|p1b: Rock|Glaive Rush|p2b: Fini\n|-damage|p2b: Fini|50/100\n"
        "|-singlemove|p1b: Rock|Glaive Rush|[silent]",
        "|t:|2\n|cant|p1a: Whim|recharge\n|move|p1b: Rock|Protect|p1b: Rock",
        "|t:|3\n|move|p1a: Whim|Tailwind|p1a: Whim",
    )
    s2 = at_turn_start(log, 2)
    assert _mon(s2, 0)["recharge"] == 1 and _mon(s2, 1)["glaiverush"] == 1
    s3 = at_turn_start(log, 3)
    assert "recharge" not in _mon(s3, 0) and "glaiverush" not in _mon(s3, 1)
