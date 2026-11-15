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


# --------------------------------------------------------------------------
# What the first 6,129 Reg M-C best-of-three games (14 Nov) show is common:
# Emergency Exit on 13% of teams (Golisopod), Flash Fire on 4%; and the rest
# of the brief's list, rarer
# --------------------------------------------------------------------------


def _exit_rv(tools, chooser=True, p1=None, p2=None, p1_bench=False):
    """p2's first (Incineroar) with Emergency Exit and Sinistcha on p2's
    bench (third); with `p1_bench` on p1's too. The forced-switch model is a
    stand-in that names the one on the bench, and notes who asked."""
    dex, moves, calc = tools
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    sheets = {r: list(SHEETS[r]) for r in SHEETS}
    if p2 is None:
        p2 = {0: {"ability": "emergencyexit"}}
    for r, swaps in (("p1", p1 or {}), ("p2", p2)):
        for i, kw in swaps.items():
            sheets[r][i] = dataclasses.replace(sheets[r][i], **kw)
    sheets["p2"].append(sin)
    if p1_bench:
        sheets["p1"].append(sin)
    asked: list[str] = []

    def choose(sides, fld, role, bench):
        asked.append(role)
        return [1.0 / len(bench)] * len(bench)

    rv = R.Resolver(
        dex,
        moves,
        calc,
        {r: tuple(v) for r, v in sheets.items()},
        SPREADS,
        switch_in=choose if chooser else None,
    )
    b = board()
    b["p2"].append(dict(mon("sinistcha"), active=False))
    if p1_bench:
        b["p1"].append(dict(mon("sinistcha"), active=False))
    return rv, b, asked


@needs_mc
def test_emergency_exit_switches_out_once_a_hit_takes_it_to_half(tools):
    """Showdown's Champions rules: after the move, a Pokemon a hit took from
    above half to half or less switches out (`onEmergencyExit`); its player
    picks who comes in (the forced-switch model, as after Eject Button). The
    move it chose this turn is lost: Incineroar's Leer never comes."""
    rv, b, asked = _exit_rv(tools)
    b["p2"][0]["hp_fraction"] = 0.6
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert outs and _no_partial(outs) and set(asked) == {"p2"}
    for o in outs:
        inci, sin = o.sides["p2"][0], o.sides["p2"][2]
        assert inci["hp_fraction"] <= 0.5 and not inci["active"] and sin["active"]
        assert o.sides["p1"][0]["boosts"] == {"def": -1}  # Whimsicott's Leer only


@needs_mc
def test_emergency_exit_without_the_forced_switch_model_is_marked(tools):
    rv, b, _asked = _exit_rv(tools, chooser=False)
    b["p2"][0]["hp_fraction"] = 0.6
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert set().union(*(o.partial for o in outs)) == {"emergency exit"}


@needs_mc
def test_emergency_exit_not_when_it_was_at_half_already(tools):
    rv, b, asked = _exit_rv(tools)
    b["p2"][0]["hp_fraction"] = 0.45
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert not asked
    for o in outs:
        inci = o.sides["p2"][0]
        assert inci["fainted"] or inci["active"]


@needs_mc
def test_emergency_exit_at_the_end_of_the_turn(tools):
    """A burn takes it from 55% to below half: it switches out before the next
    turn (Showdown: the residual Pokemon's Emergency Exit)."""
    rv, b, asked = _exit_rv(tools)
    b["p2"][0].update(hp_fraction=0.55, status="brn")
    outs = _go(rv, b, QUIET, LEER)
    assert outs and _no_partial(outs) and set(asked) == {"p2"}
    for o in outs:
        assert not o.sides["p2"][0]["active"] and o.sides["p2"][2]["active"]


@needs_mc
def test_emergency_exit_from_the_users_own_life_orb(tools):
    rv, b, asked = _exit_rv(
        tools, p1={0: {"ability": "emergencyexit"}}, p2={}, p1_bench=True
    )
    b["p1"][0].update(hp_fraction=0.55, item="lifeorb")
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert outs and _no_partial(outs) and set(asked) == {"p1"}
    for o in outs:
        assert not o.sides["p1"][0]["active"] and o.sides["p1"][2]["active"]


@needs_mc
def test_flash_fire_takes_in_a_fire_move_then_powers_its_own(tools):
    """Flash Fire: immune to Fire, and its own Fire moves x1.5 from then on
    (Showdown: the `flashfire` volatile; the calculator's abilityOn)."""
    rv, outs = _hit_by(tools, "flamethrower", "flashfire")
    assert outs and _no_partial(outs)
    for o in outs:
        inci = o.sides["p2"][0]
        assert inci["hp_fraction"] == 0.5 and inci.get("flashfire") == 1
    plain, lit = board(), board()
    lit["p2"][0]["flashfire"] = 1
    a = Action(0, "move", move="flareblitz", target=("foe", 0))
    m = rv.move("flareblitz")
    w0 = R._World(1.0, plain, R.Field(), set())
    w1 = R._World(1.0, lit, R.Field(), set())
    d0 = max(d for _p, d in rv._rolls(w0, "p2", a, m, ("p1", 0), False))
    d1 = max(d for _p, d in rv._rolls(w1, "p2", a, m, ("p1", 0), False))
    assert d1 / d0 == pytest.approx(1.5, rel=0.03)


def test_the_board_keeps_flash_fire_and_an_eaten_berry_from_the_log():
    from tests.test_board_effects import at_turn_start
    from tests.test_more_mechanics import _mon, _turns

    log = _turns(
        "|t:|1\n|move|p2a: Inci|Flamethrower|p1a: Whim\n"
        "|-start|p1a: Whim|ability: Flash Fire\n"
        "|-enditem|p1b: Rock|Sitrus Berry|[eat]",
        "|t:|2\n|switch|p1a: Back|Back, L50|100/100",
        "|t:|3\n|move|p2a: Inci|Knock Off|p1a: Back\n"
        "|-enditem|p1a: Back|Sitrus Berry|[from] move: Knock Off|[of] p2a: Inci",
    )
    s2 = at_turn_start(log, 2)
    assert _mon(s2, 0)["flashfire"] == 1 and _mon(s2, 1)["eaten"] == "sitrusberry"
    s3 = at_turn_start(log, 3)
    assert "flashfire" not in _mon(s3, 0)  # it left the field
    assert _mon(s3, 1)["eaten"] == "sitrusberry"  # that stays (Harvest's lastItem)
    s4 = at_turn_start(log, 4)
    assert "eaten" not in _mon(s4, 2)  # knocked off: not eaten


@needs_mc
def test_stakeout_doubles_damage_on_one_that_came_in_this_turn(tools):
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    sw = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    p1 = (Action(0, "move", move="dragonpulse", target=("foe", 0)), QUIET[1])
    lost = {}
    for ab in ("stakeout", "roughskin"):
        rv = _rv(tools, p1={0: {"ability": ab}}, bench=sin)
        b = board()
        b["p2"].append(dict(mon("sinistcha"), active=False))
        outs = _go(rv, b, p1, sw)
        assert _no_partial(outs) and not any(o.sides["p2"][2]["fainted"] for o in outs)
        lost[ab] = sum(o.prob * (1 - o.sides["p2"][2]["hp_fraction"]) for o in outs)
    assert lost["stakeout"] / lost["roughskin"] == pytest.approx(2.0, rel=0.05)


@needs_mc
@pytest.mark.parametrize("move", ["gigadrain", "drainpunch"])
def test_liquid_ooze_hurts_a_drainer_instead(tools, move):
    """Showdown: the heal a draining move would give is taken as damage."""
    rv = _rv(tools, p2={0: {"ability": "liquidooze"}})
    b = board()
    b["p1"][0]["hp_fraction"] = 0.6
    p1 = (Action(0, "move", move=move, target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    assert outs and _no_partial(outs)
    full_t, full_u = rv.max_hp("p2", 0), rv.max_hp("p1", 0)
    for o in outs:
        dealt = round((1.0 - o.sides["p2"][0]["hp_fraction"]) * full_t)
        lost = (0.6 - o.sides["p1"][0]["hp_fraction"]) * full_u
        assert dealt > 0 and lost == pytest.approx(round(dealt / 2), abs=1.5)


@needs_mc
def test_liquid_ooze_turns_leech_seed_on_the_seeder(tools):
    rv = _rv(tools, p2={0: {"ability": "liquidooze"}})
    b = board()
    b["p2"][0]["seeded"] = 0  # Garchomp's place
    b["p1"][0]["hp_fraction"] = 0.6
    outs = _go(rv, b, QUIET, LEER)
    full_t, full_u = rv.max_hp("p2", 0), rv.max_hp("p1", 0)
    for o in outs:
        lost = (0.6 - o.sides["p1"][0]["hp_fraction"]) * full_u
        assert lost == pytest.approx(full_t // 8, abs=1.5)


@needs_mc
def test_strength_sap_on_liquid_ooze_hurts_the_user(tools):
    rv = _rv(tools, p1={0: {"ability": "liquidooze"}})
    b = board()
    b["p2"][1]["hp_fraction"] = 0.5
    p2 = (
        Action(0, "move", move="leer"),
        Action(1, "move", move="strengthsap", target=("foe", 0)),
    )
    p1 = (Action(0, "move", move="leer"), QUIET[1])  # Garchomp does not protect
    outs = _go(rv, b, p1, p2)
    assert outs and _no_partial(outs)
    for o in outs:
        whim = o.sides["p2"][1]
        assert whim["fainted"] or whim["hp_fraction"] < 0.5


@needs_mc
@pytest.mark.parametrize(
    "ability, move, dragged",
    [
        ("guarddog", "roar", False),
        ("guarddog", "dragontail", False),
        ("suctioncups", "roar", False),
        ("intimidate", "roar", True),  # a control
        # Dragon Tail dragged no one before this week, and said nothing
        ("intimidate", "dragontail", True),
    ],
)
def test_guard_dog_and_suction_cups_cannot_be_forced_out(tools, ability, move, dragged):
    rv, b = _bench3(tools, p2={0: {"ability": ability}})
    p1 = (Action(0, "move", move=move, target=("foe", 0)), QUIET[1])
    outs = _go(rv, b, p1, LEER)
    hit = [o for o in outs if move == "roar" or o.sides["p2"][0]["hp_fraction"] < 1]
    assert hit
    for o in hit:
        assert o.sides["p2"][0]["active"] != dragged
        assert o.sides["p2"][2]["active"] == dragged


@needs_mc
def test_a_red_card_is_used_up_on_a_guard_dog_that_stays(tools):
    dex, moves, calc = tools
    sin = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
    sheets = {"p1": SHEETS["p1"] + (sin,), "p2": SHEETS["p2"]}
    sheets["p1"] = (dataclasses.replace(sheets["p1"][0], ability="guarddog"),) + sheets[
        "p1"
    ][1:]
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p1"].append(dict(mon("sinistcha"), active=False))
    b["p2"][0]["item"] = "redcard"
    p1 = (Action(0, "move", move="dragonclaw", target=("foe", 0)), QUIET[1])
    for o in _go(rv, b, p1, LEER):
        hit = o.sides["p2"][0]["hp_fraction"] < 1.0
        assert o.sides["p1"][0]["active"] and not o.sides["p1"][2]["active"]
        assert (o.sides["p2"][0]["item"] == "") == hit


@needs_mc
def test_harvest_brings_an_eaten_berry_back_half_the_time_always_in_sun(tools):
    rv = _rv(tools, p2={0: {"ability": "harvest"}})

    def eaten(hp=0.9, how="sitrusberry"):
        b = board()
        b["p2"][0].update(item="", rev_item="sitrusberry", hp_fraction=hp)
        if how:
            b["p2"][0]["eaten"] = how
        return b

    def back(outs):
        return p_of(outs, lambda o: o.sides["p2"][0]["item"] == "sitrusberry")

    sun = R.Field(weather="sunnyday", weather_left=3)
    assert back(_go(rv, eaten(), QUIET, LEER)) == pytest.approx(0.5)
    assert back(_go(rv, eaten(), QUIET, LEER, sun)) == pytest.approx(1.0)
    assert back(_go(rv, eaten(how=""), QUIET, LEER, sun)) == 0  # knocked off
    full = rv.max_hp("p2", 0)
    for o in _go(rv, eaten(hp=0.4), QUIET, LEER, sun):
        inci = o.sides["p2"][0]  # back, and eaten again at once
        assert inci["item"] == "" and inci["eaten"] == "sitrusberry"
        want = (round(0.4 * full) + full // 4) / full
        assert inci["hp_fraction"] == pytest.approx(want, abs=0.002)


# --------------------------------------------------------------------------
# The calculator's part (checked, not changed): Aura Guard, Punk Rock, Grass
# Pelt, Steely Spirit on the ally
# --------------------------------------------------------------------------


def _max_roll(rv, b, role, user, move, tgt, fld=None):
    a = Action(user, "move", move=move, target=("foe", tgt[1]))
    w = R._World(1.0, b, fld or R.Field(), set())
    return max(d for _p, d in rv._rolls(w, role, a, rv.move(move), tgt, False))


@needs_mc
@pytest.mark.parametrize(
    "side, at, ability, move, ratio, terrain",
    [
        ("defender", 0, "auraguard", "dragonclaw", 0.5, None),  # contact: half
        ("defender", 0, "auraguard", "dragonpulse", 1.0, None),  # no contact
        ("attacker", 0, "punkrock", "hypervoice", 1.3, None),
        ("defender", 0, "punkrock", "hypervoice", 0.5, None),
        ("defender", 0, "grasspelt", "dragonclaw", 1 / 1.5, "grassyterrain"),
        ("ally", 1, "steelyspirit", "ironhead", 1.5, None),
    ],
)
def test_the_calculator_has_the_new_damage_abilities(
    tools, side, at, ability, move, ratio, terrain
):
    """Garchomp (p1, first) at Incineroar (p2, first): the ability on the
    defender, the attacker, or the attacker's ally (Kingambit)."""
    where = {"defender": ("p2", 0), "attacker": ("p1", 0), "ally": ("p1", 1)}[side]
    fld = R.Field(terrain=terrain, terrain_left=3) if terrain else None
    base = _rv(tools)
    swapped = _rv(tools, **{where[0]: {where[1]: {"ability": ability}}})
    d0 = _max_roll(base, board(), "p1", 0, move, ("p2", 0), fld)
    d1 = _max_roll(swapped, board(), "p1", 0, move, ("p2", 0), fld)
    assert d1 / d0 == pytest.approx(ratio, rel=0.04)


@needs_mc
def test_grassy_glide_has_priority_on_grassy_terrain(tools):
    """Showdown: +1 on Grassy Terrain for a grounded user (`onModifyPriority`).
    Found in the dry run of 14 Nov: Rillaboom (on 32% of M-C teams) lost its
    first move to a slower Houndstone. Not modelled before, in any format."""
    rv = _rv(tools, p1={0: {"species": "rillaboom", "ability": "grassysurge"}})
    b = board()
    b["p1"][0]["species"] = "rillaboom"
    a = Action(0, "move", move="grassyglide", target=("foe", 0))
    grassy = R.Field(terrain="grassyterrain", terrain_left=3)
    assert rv._priority(R._World(1.0, b, grassy, set()), "p1", a) == 1
    assert rv._priority(R._World(1.0, b, R.Field(), set()), "p1", a) == 0
    b["p1"][0]["item"] = "airballoon"  # in the air: no
    assert rv._priority(R._World(1.0, b, grassy, set()), "p1", a) == 0


@needs_mc
def test_a_bind_ends_when_the_one_that_bound_it_is_gone(tools):
    """Showdown's partiallytrapped: no damage, and over, once its source has
    fainted or left (found by the M-C dry run: Toxapex's Infestation went on
    after Toxapex fainted, and knocked out a Basculegion that lived)."""
    rv = _rv(tools)
    full = rv.max_hp("p2", 0)
    for gone, lost in ((False, full // 8), (True, 0)):
        b = board()
        b["p2"][0].update(bound=8, bound_by=1)  # Kingambit bound it
        if gone:
            b["p1"][1].update(fainted=True, hp_fraction=0.0, active=False)
        outs = _go(rv, b, (QUIET[0],) if gone else QUIET, LEER)
        for o in outs:
            inci = o.sides["p2"][0]
            assert round((1 - inci["hp_fraction"]) * full) == lost
            assert ("bound" in inci) != gone


def test_the_board_keeps_who_bound_it_from_the_log():
    from tests.test_board_effects import at_turn_start
    from tests.test_more_mechanics import _mon, _turns

    log = _turns(
        "|t:|1\n|move|p2a: Inci|Infestation|p1a: Whim\n"
        "|-activate|p1a: Whim|move: Infestation|[of] p2a: Inci",
        "|t:|2\n|move|p2a: Inci|Protect|p2a: Inci",
    )
    s2 = at_turn_start(log, 2)
    assert _mon(s2, 0)["bound"] == 8 and _mon(s2, 0)["bound_by"] == 0


@needs_mc
def test_a_pokemon_back_in_the_same_turn_ends_the_chain_of_who_replaced_whom(tools):
    """Found when the overnight check hung on one game for hours: Golisopod
    left (Emergency Exit) and came back in the same turn, and the chain of
    who replaced whom went round in a circle (`_current` never ended)."""
    rv, b, _asked = _exit_rv(tools)
    w = R._World(1.0, b, R.Field(), set())
    assert rv._switch(w, "p2", 0, 2) and rv._switch(w, "p2", 2, 0)
    assert rv._current(w, ("p2", 0)) == ("p2", 0)
    assert rv._current(w, ("p2", 2)) == ("p2", 0)
    assert ("p2", 0) in w.replaced.values()  # it came in this turn (Stakeout)
