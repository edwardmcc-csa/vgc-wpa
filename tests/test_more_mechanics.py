"""Tests for the causes left among the partly modelled turns after Week 11
(worked ahead of Week 12), each checked against Showdown's code:

- Encore landing before its target moves: the target uses the encored move
  instead, at a random foe, keeping its place in the order
  (`sim/battle-actions.ts`, OverrideAction). Week 11's run marked 122 decision
  points "encore changes this turn's move", the most common reason left.
- The Toxic counter: badly poisoned, a Pokemon loses n/16 at the n-th end of
  turn (most 15/16), counted again from 1 after it switches out
  (`data/conditions.ts`, tox). 54 decision points.
- Leech Seed: at each end of turn the seeded Pokemon loses 1/8 and the
  Pokemon that seeded it (if still in) gains what it lost; Grass types cannot
  be seeded; switching out ends it. 67 decision points.
- Taunt: a taunted Pokemon cannot use a status move (it cannot choose one, and
  one already chosen fails). 37 decision points.
- Yawn: at the end of the next turn, the target falls asleep, unless it has a
  status or has switched out. 32 decision points.
- Mental Herb: it ends Taunt, Encore and Disable at once, and is used up.
- Disable: the target's last move cannot be chosen, and fails if already chosen.
- Spicy Spray burns whoever hits it; abilities that act only by chance when hit
  (Flame Body and the like, Cursed Body) or when hitting (Poison Touch) mark
  the turn partly modelled instead of passing in silence.
- Haze, Belly Drum, Moonlight and the like, Shore Up, Heal Pulse, Floral
  Healing, Psych Up and Strength Sap.
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from tests.test_board_effects import at_turn_start, game
from tests.test_resolver import ROOT, SHEETS, SPREADS, board, p_of
from wpa import choices as C
from wpa import resolver as R
from wpa.choices import Action

needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


def _mon(s, i):
    return s["our_pokemon"][i]


def _turns(*blocks):
    """Turn blocks, each ended by its upkeep and the next turn's start."""
    parts = []
    for n, b in enumerate(blocks, start=1):
        parts += [b, "|upkeep", f"|t:|{n + 1}\n|turn|{n + 1}"]
    return game(*parts)


# --- the board keeps what these need -----------------------------------------


def test_the_board_counts_the_toxic_turns_and_starts_again_after_a_switch():
    log = _turns(
        "|t:|1\n|move|p2a: Inci|Toxic|p1a: Whim\n|-status|p1a: Whim|tox\n"
        "|-damage|p1a: Whim|94/100 tox|[from] psn",
        "|t:|2\n|-damage|p1a: Whim|81/100 tox|[from] psn",
        "|t:|3\n|switch|p1a: Back|Back, L50|100/100",
        "|t:|4\n|switch|p1a: Whim|Whim, L50|81/100 tox\n"
        "|-damage|p1a: Whim|75/100 tox|[from] psn",
    )
    assert _mon(at_turn_start(log, 2), 0)["tox_n"] == 1
    assert _mon(at_turn_start(log, 3), 0)["tox_n"] == 2
    assert "tox_n" not in _mon(at_turn_start(log, 4), 0)  # it left the field
    assert _mon(at_turn_start(log, 5), 0)["tox_n"] == 1  # counted again from 1


def test_the_board_keeps_leech_seed_with_who_seeded_it_and_taunt_and_yawn():
    log = _turns(
        "|t:|1\n|move|p2a: Inci|Leech Seed|p1a: Whim\n|-start|p1a: Whim|move: Leech Seed\n"
        "|move|p2b: Fini|Taunt|p1b: Rock\n|-start|p1b: Rock|move: Taunt\n"
        "|move|p2a: Inci|Yawn|p1a: Whim\n|-start|p1a: Whim|move: Yawn",
        "|t:|2\n|-end|p1b: Rock|move: Taunt\n|-end|p1a: Whim|move: Yawn|[silent]\n"
        "|-status|p1a: Whim|slp|[from] move: Yawn",
        "|t:|3\n|switch|p1a: Back|Back, L50|100/100",
    )
    s2 = at_turn_start(log, 2)
    whim, rock = _mon(s2, 0), _mon(s2, 1)
    assert whim["seeded"] == 0  # Incineroar, first on p2's sheet
    assert rock["taunt"] == 1
    assert whim["drowsy"] == 1  # it falls asleep at the end of turn 2
    s3 = at_turn_start(log, 3)
    whim, rock = _mon(s3, 0), _mon(s3, 1)
    assert "taunt" not in rock and "drowsy" not in whim
    assert whim["status"] == "slp" and whim["seeded"] == 0
    assert "seeded" not in _mon(at_turn_start(log, 4), 0)  # switching out ends it


def test_a_taunted_pokemon_has_no_status_moves_to_choose():
    from tests.test_attribution import _setup
    from wpa.team_sheets import load_dexes

    sheets, _spreads, sides = _setup()
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    ours = [dict(m) for m in sides["p1"]]
    ours[0]["taunt"] = 1
    opts = C.options(ours, sides["p2"], sheets["p1"], dex)
    moves = {a.move for a in opts[0] if a.kind == "move"}
    assert moves == {"stoneedge", "dragonclaw"}  # no Protect
    assert any(a.kind == "switch" for a in opts[0])


# --- the resolver ------------------------------------------------------------


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


def _run(tools, b, p1, p2, fld=None):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    return rv, rv.resolve(b, fld or R.Field(), {"p1": p1, "p2": p2})


QUIET1 = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
QUIET2 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))


@needs_showdown
def test_encore_before_its_target_moves_changes_the_move_at_a_random_foe(tools):
    b = board()
    b["p1"][0].update(last_move="dragonclaw", boosts={"spe": -6})  # it moves last
    p1 = (
        Action(0, "move", move="stoneedge", target=("foe", 0)),  # 80% to hit
        Action(1, "move", move="protect"),
    )
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="encore", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, p1, p2)
    # Dragon Claw instead, at a random foe: Incineroar half the time, and
    # Whimsicott (a Fairy) takes nothing
    assert p_of(outs, lambda o: o.sides["p2"][0]["hp_fraction"] < 1.0) == pytest.approx(
        0.5
    )
    assert all(o.sides["p2"][1]["hp_fraction"] == 1.0 for o in outs)
    assert all(o.sides["p1"][0]["encore"] == "dragonclaw" for o in outs)
    assert not any("encore changes this turn's move" in o.partial for o in outs)


@needs_showdown
def test_encore_puts_its_target_where_the_new_moves_priority_puts_it(tools):
    # Champions (`data/mods/champions/moves.ts`): Encore changes the target's
    # queued action to the encored move, with that move's priority. Garchomp
    # chose Stone Edge but used Protect last turn: encored by Whimsicott, it
    # protects at once (+4), before Incineroar's Flare Blitz, which was ahead
    # of it in the order it chose.
    b = board()
    b["p1"][0].update(last_move="protect", boosts={"spe": -6})
    p1 = (
        Action(0, "move", move="stoneedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    p2 = (
        Action(0, "move", move="flareblitz", target=("foe", 0)),
        Action(1, "move", move="encore", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, p1, p2)
    assert all(o.sides["p1"][0]["hp_fraction"] == 1.0 for o in outs)  # protected
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)  # no recoil
    assert all(o.sides["p1"][0]["encore"] == "protect" for o in outs)


@needs_showdown
def test_a_mental_herb_ends_encore_and_taunt_at_once(tools):
    b = board()
    b["p1"][0].update(last_move="dragonclaw", boosts={"spe": -6}, item="mentalherb")
    p1 = (
        Action(0, "move", move="stoneedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="encore", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, p1, p2)
    assert p_of(outs, lambda o: o.sides["p2"][0]["hp_fraction"] < 1.0) == pytest.approx(
        0.8
    )  # Stone Edge, as chosen
    assert all("encore" not in o.sides["p1"][0] for o in outs)
    assert all(o.sides["p1"][0]["item"] == "" for o in outs)
    b = board()
    b["p1"][0].update(boosts={"spe": -6}, item="mentalherb")
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="taunt", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, p1, p2)
    assert all(o.sides["p1"][0]["boosts"].get("atk") == 2 for o in outs)
    assert all("taunt" not in o.sides["p1"][0] for o in outs)


@needs_showdown
@pytest.mark.parametrize("n, lost", [(None, 1), (2, 3), (14, 15), (15, 15)])
def test_the_toxic_counter(tools, n, lost):
    b = board()
    b["p1"][0]["status"] = "tox"
    if n is not None:
        b["p1"][0]["tox_n"] = n
    _rv, outs = _run(tools, b, QUIET1, QUIET2)
    for o in outs:
        g = o.sides["p1"][0]
        assert g["hp_fraction"] == pytest.approx(1 - lost / 16, abs=0.01)
        assert g["tox_n"] == lost
        assert "toxic counter" not in o.partial


@needs_showdown
def test_leech_seed_drains_an_eighth_to_the_pokemon_that_seeded(tools):
    b = board()
    b["p2"][1]["hp_fraction"] = 0.5
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="leechseed", target=("foe", 0)),
    )
    rv, outs = _run(tools, b, QUIET1, p2)
    # Garchomp protects: nothing lands
    assert all("seeded" not in o.sides["p1"][0] for o in outs)
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    rv, outs = _run(tools, b, p1, p2)
    assert p_of(outs, lambda o: "seeded" in o.sides["p1"][0]) == pytest.approx(0.9)
    gained = rv.max_hp("p1", 0) / 8 / rv.max_hp("p2", 1)
    for o in outs:
        g, w = o.sides["p1"][0], o.sides["p2"][1]
        if "seeded" in g:
            assert g["seeded"] == 1
            assert g["hp_fraction"] == pytest.approx(7 / 8, abs=0.01)
            assert w["hp_fraction"] == pytest.approx(0.5 + gained, abs=0.01)
        else:
            assert g["hp_fraction"] == 1.0 and w["hp_fraction"] == 0.5
        assert "move:leechseed" not in o.partial


@needs_showdown
def test_a_grass_type_cannot_be_seeded(tools):
    b = board()
    p1 = (
        Action(0, "move", move="protect"),
        Action(1, "move", move="leechseed", target=("foe", 1)),  # Whimsicott
    )
    _rv, outs = _run(tools, b, p1, QUIET2)
    assert all("seeded" not in o.sides["p2"][1] for o in outs)


@needs_showdown
def test_a_taunted_pokemons_status_move_fails(tools):
    b = board()
    b["p1"][0]["taunt"] = 1
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    _rv, outs = _run(tools, b, p1, QUIET2)
    assert all(o.sides["p1"][0]["boosts"] == {} for o in outs)
    # and Taunt landing before it moves does the same
    b = board()
    b["p1"][0]["boosts"] = {"spe": -6}
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="taunt", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, p1, p2)
    assert all(o.sides["p1"][0]["boosts"] == {"spe": -6} for o in outs)
    assert all(o.sides["p1"][0]["taunt"] for o in outs)
    assert not any("move:taunt" in o.partial for o in outs)


@needs_showdown
def test_yawn_puts_its_target_to_sleep_at_the_end_of_the_next_turn(tools):
    b = board()
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="yawn", target=("foe", 0)),
    )
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    _rv, outs = _run(tools, b, p1, p2)
    for o in outs:
        g = o.sides["p1"][0]
        assert g["drowsy"] == 1 and g["status"] == ""
        assert "move:yawn" not in o.partial
    b = board()
    b["p1"][0]["drowsy"] = 1
    _rv, outs = _run(tools, b, p1, QUIET2)
    for o in outs:
        g = o.sides["p1"][0]
        assert g["status"] == "slp" and "drowsy" not in g
    b = board()
    b["p1"][0].update(drowsy=1, status="par")
    _rv, outs = _run(tools, b, QUIET1, QUIET2)
    assert all(o.sides["p1"][0]["status"] == "par" for o in outs)


# --- abilities that act when hit -----------------------------------------------
# Spicy Spray (Champions, 405 of 9,060 validation games): any damaging hit burns
# the attacker, every time. The abilities that act only by chance when hit
# (Flame Body, Static, Poison Point, Effect Spore and Cute Charm on contact;
# Cursed Body on any hit) or when hitting (Poison Touch) are not modelled: the
# turn says so instead of passing in silence.


def _with_ability(ability, role="p2", idx=0):
    from dataclasses import replace

    sheets = {r: list(v) for r, v in SHEETS.items()}
    sheets[role][idx] = replace(sheets[role][idx], ability=ability)
    return {r: tuple(v) for r, v in sheets.items()}


def _hit(tools, sheets, move):
    dex, moves, calc = tools
    p1 = (
        Action(0, "move", move=move, target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    return rv.resolve(board(), R.Field(), {"p1": p1, "p2": QUIET2})


@needs_showdown
def test_spicy_spray_burns_whoever_hits_it(tools):
    outs = _hit(tools, _with_ability("spicyspray"), "dragonclaw")
    assert all(o.sides["p1"][0]["status"] == "brn" for o in outs)
    outs = _hit(tools, _with_ability("blaze"), "dragonclaw")
    assert all(o.sides["p1"][0]["status"] == "" for o in outs)


@needs_showdown
@pytest.mark.parametrize(
    "ability, move, marked",
    [
        ("flamebody", "dragonclaw", True),  # contact
        ("flamebody", "stoneedge", False),  # no contact
        ("static", "dragonclaw", True),
        ("cursedbody", "stoneedge", True),  # any hit
        ("blaze", "dragonclaw", False),
    ],
)
def test_a_chance_ability_when_hit_marks_the_turn(tools, ability, move, marked):
    outs = _hit(tools, _with_ability(ability), move)
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit
    assert all((f"ability:{ability}" in o.partial) == marked for o in hit)


@needs_showdown
def test_poison_touch_on_the_attacker_marks_the_turn(tools):
    outs = _hit(tools, _with_ability("poisontouch", "p1", 0), "dragonclaw")
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit and all("ability:poisontouch" in o.partial for o in hit)


# --- Disable (32 decision points in Week 11's run) ------------------------------
# The target's last move cannot be chosen, and fails if it was chosen already
# this turn; a Mental Herb ends it; switching out ends it.


def test_the_board_keeps_the_disabled_move_and_a_disabled_move_is_not_on_offer():
    log = _turns(
        "|t:|1\n|move|p2a: Inci|Disable|p1a: Whim\n|-start|p1a: Whim|Disable|Tailwind",
        "|t:|2\n|-end|p1a: Whim|Disable",
    )
    assert _mon(at_turn_start(log, 2), 0)["disabled"] == "tailwind"
    assert "disabled" not in _mon(at_turn_start(log, 3), 0)
    from tests.test_attribution import _setup
    from wpa.team_sheets import load_dexes

    sheets, _spreads, sides = _setup()
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    ours = [dict(m) for m in sides["p1"]]
    ours[0]["disabled"] = "dragonclaw"
    opts = C.options(ours, sides["p2"], sheets["p1"], dex)
    assert {a.move for a in opts[0] if a.kind == "move"} == {"stoneedge", "protect"}


@needs_showdown
def test_a_disabled_move_fails_and_disable_before_it_moves_stops_it(tools):
    claw = (
        Action(0, "move", move="dragonclaw", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    b = board()
    b["p1"][0]["disabled"] = "dragonclaw"
    _rv, outs = _run(tools, b, claw, QUIET2)
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)
    b = board()
    b["p1"][0].update(last_move="dragonclaw", boosts={"spe": -6})
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="disable", target=("foe", 0)),
    )
    _rv, outs = _run(tools, b, claw, p2)
    assert all(o.sides["p2"][0]["hp_fraction"] == 1.0 for o in outs)
    assert all(o.sides["p1"][0]["disabled"] == "dragonclaw" for o in outs)
    assert not any("move:disable" in o.partial for o in outs)
    b["p1"][0]["item"] = "mentalherb"
    _rv, outs = _run(tools, b, claw, p2)
    assert all(o.sides["p2"][0]["hp_fraction"] < 1.0 for o in outs)
    assert all("disabled" not in o.sides["p1"][0] for o in outs)


# --- simple status moves left unmodelled after Week 11 --------------------------
# Haze, Belly Drum, Moonlight and the like, Shore Up, Heal Pulse, Floral
# Healing, Psych Up and Strength Sap, each as Showdown's `data/moves.ts` has it.

GUARD2 = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))


@needs_showdown
def test_haze_clears_every_stat_change(tools):
    b = board()
    b["p1"][0]["boosts"] = {"atk": 2}
    b["p2"][1]["boosts"] = {"spe": -1}
    p2 = (Action(0, "move", move="haze"), Action(1, "move", move="protect"))
    _rv, outs = _run(tools, b, QUIET1, p2)
    for o in outs:
        assert all(x["boosts"] == {} for r in ("p1", "p2") for x in o.sides[r])
        assert "move:haze" not in o.partial


@needs_showdown
@pytest.mark.parametrize("hp, after, atk", [(1.0, 0.5, 6), (0.4, 0.4, None)])
def test_belly_drum_costs_half_and_maxes_attack(tools, hp, after, atk):
    b = board()
    b["p1"][0]["hp_fraction"] = hp
    p1 = (Action(0, "move", move="bellydrum"), Action(1, "move", move="protect"))
    _rv, outs = _run(tools, b, p1, GUARD2)
    for o in outs:
        g = o.sides["p1"][0]
        assert g["hp_fraction"] == pytest.approx(after, abs=0.01)
        assert g["boosts"].get("atk") == atk


@needs_showdown
@pytest.mark.parametrize(
    "weather, gain", [("", 1 / 2), ("sunnyday", 2 / 3), ("raindance", 1 / 4)]
)
def test_moonlight_heals_by_the_weather(tools, weather, gain):
    b = board()
    b["p1"][0]["hp_fraction"] = 0.2
    p1 = (Action(0, "move", move="moonlight"), Action(1, "move", move="protect"))
    fld = R.Field(weather=weather, weather_left=3 if weather else 0)
    _rv, outs = _run(tools, b, p1, GUARD2, fld)
    for o in outs:
        assert o.sides["p1"][0]["hp_fraction"] == pytest.approx(0.2 + gain, abs=0.01)
        assert "move:moonlight" not in o.partial


@needs_showdown
def test_heal_pulse_heals_its_target_by_half(tools):
    b = board()
    b["p1"][1]["hp_fraction"] = 0.3
    p1 = (
        Action(0, "move", move="healpulse", target=("ally", 1)),
        Action(1, "move", move="swordsdance"),
    )
    _rv, outs = _run(tools, b, p1, GUARD2)
    for o in outs:
        assert o.sides["p1"][1]["hp_fraction"] == pytest.approx(0.8, abs=0.01)


@needs_showdown
def test_psych_up_copies_the_targets_stat_changes(tools):
    b = board()
    b["p2"][0]["boosts"] = {"atk": 2, "def": -1}
    p1 = (
        Action(0, "move", move="psychup", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    _rv, outs = _run(tools, b, p1, GUARD2)
    assert all(o.sides["p1"][0]["boosts"] == {"atk": 2, "def": -1} for o in outs)


@needs_showdown
def test_strength_sap_heals_by_the_targets_attack_and_lowers_it(tools):
    b = board()
    b["p1"][1]["hp_fraction"] = 0.2
    p1 = (
        Action(0, "move", move="protect"),
        Action(1, "move", move="strengthsap", target=("foe", 0)),
    )
    p2 = (Action(0, "move", move="tailwind"), Action(1, "move", move="protect"))
    rv, outs = _run(tools, b, p1, p2)
    atk = rv._stats("p2", 0, ("atk",))[0]  # Incineroar's Attack, unchanged so far
    for o in outs:
        assert o.sides["p2"][0]["boosts"] == {"atk": -1}
        want = min(1.0, 0.2 + atk / rv.max_hp("p1", 1))
        assert o.sides["p1"][1]["hp_fraction"] == pytest.approx(want, abs=0.01)
        assert "move:strengthsap" not in o.partial
