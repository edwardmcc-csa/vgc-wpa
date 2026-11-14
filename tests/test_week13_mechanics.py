"""Week 13 Task 2: rules the resolver check found missing or modelled in part.

- Sitrus Berry: eaten whenever the holder falls to half or less, from any
  damage (recoil, Rough Skin, Life Orb, the end of the turn), not only a hit
  (resolver check, 13 Nov: 25 of 300 sampled HP misses).
- Life Dew heals the user and its ally a quarter each (97 uses in the check's
  892 games; the ally was left out).
- Leech Seed drains into whoever stands in the seeder's place: when the
  seeder switches out this turn, the Pokemon that comes in is healed.
"""

from __future__ import annotations

import pytest

from tests.test_more_mechanics import _mon, _turns, needs_showdown
from tests.test_board_effects import at_turn_start
from tests.test_resolver import ROOT, SHEETS, SPREADS, board
from tests.test_week12_mechanics import P1_QUIET, _bench
from wpa import resolver as R
from wpa.choices import Action


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


@needs_showdown
def test_sitrus_berry_is_eaten_after_recoil_takes_the_holder_to_half(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    b = board()
    b["p1"][0].update(hp_fraction=0.52, item="sitrusberry")
    edge = (
        Action(0, "move", move="doubleedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    quiet = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    outs = rv.resolve(b, R.Field(), {"p1": edge, "p2": quiet})
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit
    for o in hit:
        g = o.sides["p1"][0]
        assert g["item"] == "" and g["rev_item"] == "sitrusberry"
        assert g["hp_fraction"] > 0.5  # recoil took it under half, then a quarter back


@needs_showdown
def test_life_dew_heals_the_user_and_its_ally(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    b = board()
    b["p2"][0]["hp_fraction"] = 0.5
    b["p2"][1]["hp_fraction"] = 0.6
    dew = (Action(0, "move", move="swordsdance"), Action(1, "move", move="lifedew"))
    outs = rv.resolve(b, R.Field(), {"p1": P1_QUIET, "p2": dew})
    for o in outs:
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(0.75, abs=0.01)
        assert o.sides["p2"][1]["hp_fraction"] == pytest.approx(0.85, abs=0.01)
        assert "move:lifedew" not in o.partial


@needs_showdown
def test_leech_seed_heals_the_pokemon_that_took_the_seeders_place(tools):
    """Game 2635937395 turn 3: the seeder switched out and its place was healed;
    the resolver marked it partly modelled."""
    rv, b = _bench(tools)
    b["p1"][0]["seeded"] = 1  # Whimsicott seeded Garchomp
    b["p2"][2]["hp_fraction"] = 0.5  # Sinistcha, on the bench
    out = (Action(0, "move", move="protect"), Action(1, "switch", switch_to=2))
    outs = rv.resolve(b, R.Field(), {"p1": P1_QUIET, "p2": out})
    gained = rv.max_hp("p1", 0) // 8 / rv.max_hp("p2", 2)
    for o in outs:
        assert "leech seed heals the Pokemon in its place" not in o.partial
        assert o.sides["p1"][0]["seeded"] == 2
        assert o.sides["p2"][2]["hp_fraction"] == pytest.approx(0.5 + gained, abs=0.01)


# --------------------------------------------------------------------------
# The rules the resolver check still marks partly modelled (at 541962d)
# --------------------------------------------------------------------------


def _with(tools, p1=None, p2=None):
    """A resolver on the test sheets, with some Pokemon replaced."""
    import dataclasses

    dex, moves, calc = tools
    sheets = {r: list(SHEETS[r]) for r in SHEETS}
    for r, swaps in (("p1", p1 or {}), ("p2", p2 or {})):
        for i, kw in swaps.items():
            sheets[r][i] = dataclasses.replace(sheets[r][i], **kw)
    return R.Resolver(
        dex, moves, calc, {r: tuple(v) for r, v in sheets.items()}, SPREADS
    )


def _go(rv, b, p1, p2, fld=None):
    return rv.resolve(b, fld or R.Field(), {"p1": p1, "p2": p2})


SD_PROTECT = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
SD2 = (Action(0, "move", move="protect"), Action(1, "move", move="swordsdance"))


def _no_partial(outs):
    return set().union(*(o.partial for o in outs)) == set()


@needs_showdown
def test_skill_swap_trades_abilities_and_the_new_one_starts(tools):
    """Game 2618889364 (Wyrdeer, Intimidate, swapped with Scovillain): the
    Intimidate it gave away went off at once."""
    rv = _with(tools, p2={0: {"ability": "intimidate"}})
    swap = (
        Action(0, "move", move="skillswap", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    outs = _go(rv, board(), swap, SD_PROTECT)
    assert outs and _no_partial(outs)
    for o in outs:
        assert o.sides["p1"][0]["ability"] == "intimidate"
        assert o.sides["p2"][0]["ability"] == "roughskin"
        assert o.sides["p2"][1]["boosts"].get("atk") == -1  # Intimidate went off
        assert rv.ability("p1", 0, o.sides["p1"][0]) == "intimidate"


@needs_showdown
def test_entrainment_and_simple_beam_replace_the_targets_ability(tools):
    rv = _with(tools)
    for move, want in (("entrainment", "defiant"), ("simplebeam", "simple")):
        p1 = (
            Action(0, "move", move="protect"),
            Action(1, "move", move=move, target=("foe", 0)),
        )
        outs = _go(rv, board(), p1, SD_PROTECT)
        assert _no_partial(outs)
        assert {o.sides["p2"][0].get("ability") for o in outs} == {want}


@needs_showdown
def test_curse_boosts_a_non_ghost_and_a_ghost_curses_its_target(tools):
    rv = _with(tools, p1={1: {"species": "sinistcha", "ability": "hospitality"}})
    b = board()
    b["p1"][1]["species"] = "sinistcha"
    gambit = _with(tools)
    p1 = (Action(0, "move", move="protect"), Action(1, "move", move="curse"))
    outs = _go(gambit, board(), p1, SD_PROTECT)
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p1"][1]["boosts"] == {"atk": 1, "def": 1, "spe": -1}
    ghost = (
        Action(0, "move", move="protect"),
        Action(1, "move", move="curse", target=("foe", 0)),
    )
    outs = _go(rv, b, ghost, SD_PROTECT)
    assert _no_partial(outs)
    half = rv.max_hp("p1", 1) // 2 / rv.max_hp("p1", 1)
    for o in outs:
        assert o.sides["p1"][1]["hp_fraction"] == pytest.approx(1 - half, abs=0.01)
        assert o.sides["p2"][0]["cursed"] == 1
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(0.75, abs=0.01)


@needs_showdown
def test_stockpile_raises_both_defences_three_times_at_most(tools):
    rv = _with(tools)
    p1 = (Action(0, "move", move="protect"), Action(1, "move", move="stockpile"))
    outs = _go(rv, board(), p1, SD_PROTECT)
    assert _no_partial(outs)
    for o in outs:
        k = o.sides["p1"][1]
        assert k["stockpile"] == 1 and k["boosts"] == {"def": 1, "spd": 1}
    b = board()
    b["p1"][1].update(stockpile=3, boosts={"def": 3, "spd": 3})
    for o in _go(rv, b, p1, SD_PROTECT):
        assert o.sides["p1"][1]["boosts"] == {"def": 3, "spd": 3}


@needs_showdown
def test_salt_cure_takes_an_eighth_each_end_of_turn_a_quarter_from_water_or_steel(
    tools,
):
    rv = _with(tools)
    b = board()
    b["p2"][0]["saltcure"] = 1  # Incineroar: Fire/Dark
    b["p1"][1]["saltcure"] = 1  # Kingambit: Dark/Steel
    outs = _go(rv, b, SD2, SD_PROTECT)
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(7 / 8, abs=0.01)
        assert o.sides["p1"][1]["hp_fraction"] == pytest.approx(3 / 4, abs=0.01)
    hit = (
        Action(0, "move", move="saltcure", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    outs = _go(rv, board(), hit, SD_PROTECT)
    assert _no_partial(outs)
    assert any(o.sides["p2"][0].get("saltcure") for o in outs)


@needs_showdown
def test_heal_block_stops_leftovers_and_psychic_noise_gives_it(tools):
    rv = _with(tools)
    b = board()
    b["p2"][0].update(item="leftovers", hp_fraction=0.5, healblock=1)
    for o in _go(rv, b, SD2, SD_PROTECT):
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(0.5, abs=1e-9)
    noise = (
        Action(0, "move", move="psychicnoise", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    outs = _go(rv, board(), noise, SD_PROTECT)
    assert _no_partial(outs)
    assert all(
        o.sides["p2"][0].get("healblock")
        for o in outs
        if o.sides["p2"][0]["hp_fraction"] < 1
    )


@needs_showdown
def test_power_swap_trades_attack_and_special_attack_changes(tools):
    rv = _with(tools)
    b = board()
    b["p1"][0]["boosts"] = {"atk": 2, "def": 1}
    b["p2"][0]["boosts"] = {"spa": -1}
    p1 = (
        Action(0, "move", move="powerswap", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    quiet = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
    b["p2"][0]["protect_streak"] = 0
    outs = _go(
        rv,
        b,
        p1,
        (Action(0, "move", move="tailwind"), Action(1, "move", move="protect")),
    )
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p1"][0]["boosts"] == {"def": 1, "spa": -1}
        assert o.sides["p2"][0]["boosts"] == {"atk": 2}
    assert quiet


@needs_showdown
def test_destiny_bond_takes_the_attacker_down_with_it(tools):
    rv = _with(tools)
    b = board()
    b["p2"][1]["hp_fraction"] = 0.01
    p1 = (
        Action(0, "move", move="stoneedge", target=("foe", 1)),
        Action(1, "move", move="protect"),
    )
    p2 = (Action(0, "move", move="protect"), Action(1, "move", move="destinybond"))
    outs = _go(rv, b, p1, p2)
    assert _no_partial(outs)
    ko = [o for o in outs if o.sides["p2"][1]["fainted"]]
    assert ko and all(o.sides["p1"][0]["fainted"] for o in ko)


@needs_showdown
def test_magic_powder_makes_the_target_psychic(tools):
    rv = _with(tools)
    p2 = (
        Action(0, "move", move="protect"),
        Action(1, "move", move="magicpowder", target=("foe", 1)),
    )
    outs = _go(rv, board(), SD2, p2)
    assert _no_partial(outs)
    assert {tuple(o.sides["p1"][1]["types"]) for o in outs} == {("Psychic",)}


@needs_showdown
def test_focus_energy_raises_the_critical_hit_chance(tools):
    rv = _with(tools)
    p1 = (Action(0, "move", move="focusenergy"), Action(1, "move", move="protect"))
    outs = _go(rv, board(), p1, SD_PROTECT)
    assert _no_partial(outs)
    o = outs[0]
    assert o.sides["p1"][0]["focusenergy"] == 1
    w = R._World(1.0, o.sides, R.Field(), set())
    claw = Action(0, "move", move="dragonclaw", target=("foe", 0))
    assert rv._crit_chance("p1", claw, rv.move("dragonclaw"), w, ("p2", 0)) == 0.5


@needs_showdown
def test_tidy_up_raises_attack_and_speed_and_clears_substitutes(tools):
    rv = _with(tools)
    b = board()
    b["p2"][0]["sub"] = 20
    p1 = (Action(0, "move", move="protect"), Action(1, "move", move="tidyup"))
    outs = _go(rv, b, p1, SD_PROTECT)
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p1"][1]["boosts"] == {"atk": 1, "spe": 1}
        assert not o.sides["p2"][0].get("sub")


@needs_showdown
def test_imprison_stops_the_foes_using_the_users_moves(tools):
    """Garchomp knows Earthquake: imprisoned, Incineroar's fails."""
    rv = _with(tools)
    p1 = (Action(0, "move", move="imprison"), Action(1, "move", move="swordsdance"))
    p2 = (Action(0, "move", move="earthquake"), Action(1, "move", move="protect"))
    outs = _go(rv, board(), p1, p2)
    assert _no_partial(outs)
    for o in outs:
        assert o.sides["p1"][0]["imprison"] == 1
        assert o.sides["p1"][1]["hp_fraction"] == 1.0  # no Earthquake


@needs_showdown
def test_gravity_grounds_flying_types_for_five_turns(tools):
    rv = _with(tools, p2={1: {"species": "corviknight", "ability": "pressure"}})
    b = board()
    b["p2"][1]["species"] = "corviknight"
    p1 = (
        Action(0, "move", move="gravity"),
        Action(1, "move", move="highhorsepower", target=("foe", 1)),
    )
    outs = _go(
        rv,
        b,
        p1,
        (Action(0, "move", move="swordsdance"), Action(1, "move", move="bulkup")),
    )
    assert _no_partial(outs)
    assert any(o.sides["p2"][1]["hp_fraction"] < 1.0 for o in outs)
    assert {o.field.gravity for o in outs} == {4}


def _theirs(s, i):
    return s["opp_pokemon"][i]


def test_the_board_keeps_abilities_changed_and_the_new_volatiles():
    """From the log: Skill Swap (each takes the other's), Entrainment and Simple
    Beam, Curse, Stockpile, Salt Cure, Heal Block, Focus Energy, Imprison and
    Destiny Bond; each ends when the Pokemon leaves the field."""
    log = _turns(
        "|t:|1\n|move|p1a: Whim|Skill Swap|p2a: Inci\n"
        "|-activate|p1a: Whim|Skill Swap|Intimidate|Prankster|[of] p2a: Inci\n"
        "|move|p2b: Fini|Entrainment|p1b: Rock\n"
        "|-ability|p1b: Rock|Misty Surge|Sturdy|[from] move: Entrainment"
        "|[of] p2b: Fini",
        "|t:|2\n|move|p1a: Whim|Curse|p2a: Inci\n"
        "|-start|p2a: Inci|Curse|[of] p1a: Whim\n"
        "|move|p1b: Rock|Stockpile|p1b: Rock\n|-start|p1b: Rock|stockpile1\n"
        "|move|p2b: Fini|Salt Cure|p1a: Whim\n|-damage|p1a: Whim|90/100\n"
        "|-start|p1a: Whim|Salt Cure\n"
        "|move|p2a: Inci|Psychic Noise|p1b: Rock\n|-damage|p1b: Rock|80/100\n"
        "|-start|p1b: Rock|move: Heal Block",
        "|t:|3\n|move|p1b: Rock|Stockpile|p1b: Rock\n|-start|p1b: Rock|stockpile2\n"
        "|move|p2b: Fini|Focus Energy|p2b: Fini\n"
        "|-start|p2b: Fini|move: Focus Energy\n"
        "|move|p1a: Whim|Imprison|p1a: Whim\n|-start|p1a: Whim|move: Imprison\n"
        "|move|p2a: Inci|Destiny Bond|p2a: Inci\n|-singlemove|p2a: Inci|Destiny Bond\n"
        "|-end|p1b: Rock|move: Heal Block",
        "|t:|4\n|switch|p1a: Back|Back, L50|100/100\n"
        "|move|p2a: Inci|Fake Out|p1b: Rock\n"
        "|-damage|p1b: Rock|70/100",
    )
    s2 = at_turn_start(log, 2)
    assert _mon(s2, 0)["ability"] == "intimidate"
    assert _theirs(s2, 0)["ability"] == "prankster"
    assert _mon(s2, 1)["ability"] == "mistysurge"
    s3 = at_turn_start(log, 3)
    assert _theirs(s3, 0)["cursed"] == 1
    assert _mon(s3, 1)["stockpile"] == 1 and _mon(s3, 1)["healblock"] == 1
    assert _mon(s3, 0)["saltcure"] == 1
    s4 = at_turn_start(log, 4)
    assert _mon(s4, 1)["stockpile"] == 2 and "healblock" not in _mon(s4, 1)
    assert _theirs(s4, 1)["focusenergy"] == 1
    assert _mon(s4, 0)["imprison"] == 1
    assert _theirs(s4, 0)["destinybond"] == 1
    s5 = at_turn_start(log, 5)
    whim = _mon(s5, 0)  # it left the field: all of it ends
    assert not {"ability", "saltcure", "imprison"} & set(whim)
    assert "destinybond" not in _theirs(s5, 0)  # Inci moved again


# --------------------------------------------------------------------------
# Found diagnosing 300 HP-only misses at 52e0496
# --------------------------------------------------------------------------


def test_a_pokemon_that_mega_evolved_and_could_not_move_chose_a_mega_move():
    """Game 2629496303 turn 4: Tyranitar Mega Evolved (its Sand Stream ended
    the snow) and was frozen, so its move was hidden; averaged over its
    moves without Mega Evolution, the snow stayed and Blizzard never
    missed."""
    from tests.test_hidden_choices import CH, MEGA, OPTS, PRIORITY
    from wpa import attribution as A

    mix = A.taken_mixture({0: "cant"}, set(), OPTS, CH, PRIORITY, megas={0})
    assert {j[0] for j, _p in mix} == {MEGA}
    mix = A.taken_mixture({0: "cant"}, set(), OPTS, CH, PRIORITY)
    assert MEGA not in {j[0] for j, _p in mix}


def test_the_turn_records_who_mega_evolved():
    from tests.test_board_effects import game
    from wpa import choices as C

    log = game(
        "|t:|1\n|detailschange|p2a: Inci|Inci-Mega, L50\n"
        "|-mega|p2a: Inci|Inci|Incinite\n"
        "|cant|p2a: Inci|frz\n|upkeep",
        "|t:|2\n|turn|2",
    )
    (t,) = [t for t in C.turns(log) if t.turn == 1 and t.role == "p2"]
    assert t.megas == {0} and t.taken[0] == "cant"


@needs_showdown
def test_no_weather_damage_on_the_turn_the_weather_ends(tools):
    """Showdown counts the weather down first and skips its residual on the
    turn it ends (game 2630300340 turn 5: no Sandstorm damage with the
    weather's last turn)."""
    rv = _with(tools)
    b = board()  # Garchomp and Kingambit are immune; Incineroar is not
    sand = R.Field(weather="sandstorm", weather_left=2)
    for o in _go(rv, b, SD2, SD_PROTECT, sand):
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(15 / 16, abs=0.01)
        assert o.field.weather == "sandstorm"
    last = R.Field(weather="sandstorm", weather_left=1)
    for o in _go(rv, b, SD2, SD_PROTECT, last):
        assert o.sides["p2"][0]["hp_fraction"] == 1.0
        assert o.field.weather == ""


# --------------------------------------------------------------------------
# Hazards: Stealth Rock, Spikes, Toxic Spikes, Sticky Web
# --------------------------------------------------------------------------


@needs_showdown
def test_stealth_rock_goes_on_the_foes_side_and_hurts_whoever_comes_in(tools):
    rv, b = _bench(tools)
    p1 = (Action(0, "move", move="stealthrock"), Action(1, "move", move="protect"))
    outs = rv.resolve(b, R.Field(), {"p1": p1, "p2": SD_PROTECT})
    assert _no_partial(outs)
    assert {o.field.sides["p2"].get("stealthrock") for o in outs} == {1}
    # under rocks, Sinistcha (Grass/Ghost: neutral) loses an eighth coming in
    rocks = R.Field()
    rocks.sides["p2"]["stealthrock"] = 1
    out = (Action(0, "move", move="protect"), Action(1, "switch", switch_to=2))
    for o in rv.resolve(b, rocks, {"p1": P1_QUIET, "p2": out}):
        assert o.sides["p2"][2]["hp_fraction"] == pytest.approx(7 / 8, abs=0.01)
        assert o.field.sides["p2"]["stealthrock"] == 1  # it stays


def test_the_board_keeps_the_hazards_on_each_side():
    """The timers do not keep hazards (they have no length): the board adds
    them, so the resolver starts with them."""
    from tests.test_decisions import EMPTY
    from wpa import decisions as D

    log = _turns(
        "|t:|1\n|move|p2a: Inci|Stealth Rock|p1a: Whim\n"
        "|-sidestart|p1: A|move: Stealth Rock\n"
        "|move|p2b: Fini|Spikes|p1a: Whim\n|-sidestart|p1: A|Spikes\n"
        "|move|p1b: Rock|Spikes|p2a: Inci\n|-sidestart|p2: B|Spikes",
        "|t:|2\n|move|p2b: Fini|Spikes|p1a: Whim\n|-sidestart|p1: A|Spikes\n"
        "|-sideend|p2: B|Spikes|[from] move: Tidy Up",
    )
    g = D.build_game(log, EMPTY)
    by_turn = {
        s["turn"]: i
        for i, s in enumerate(g.states["p1"])
        if s["moment"] == "turn_start"
    }
    f2 = R.field_from_timers(g.joined["p1"][by_turn[2]], "p1")
    assert f2.sides["p1"] == {"stealthrock": 1, "spikes": 1}
    assert f2.sides["p2"] == {"spikes": 1}
    f3 = R.field_from_timers(g.joined["p1"][by_turn[3]], "p1")
    assert f3.sides["p1"] == {"stealthrock": 1, "spikes": 2}
    assert f3.sides["p2"] == {}
