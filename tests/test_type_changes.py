"""Week 12 Task 2: type changes. Protean and Libero (Showdown's onPrepareHit:
once per switch-in, the user becomes the type of the move it uses, unless it is
that type already), and the moves that change types (Soak, Trick-or-Treat,
Forest's Curse, Reflect Type, Burn Up). The board keeps a changed type until the
Pokemon leaves the field; the resolver plays them out, and the damage
calculator is told the types, so type matchups and STAB follow them.

In Week 11's run, Reg M-A's two biggest "choices" (game 2616502323, turns 7
and 8) came from a Meowscarada made Dark by Protean that the resolver still
took for Grass/Dark: Camerupt's Earth Power knocked it out, and the resolver
had it resisting."""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from tests.test_board_effects import at_turn_start
from tests.test_more_mechanics import QUIET2, _mon, _turns, needs_showdown
from tests.test_resolver import ROOT, SHEETS, SPREADS, board, mon
from wpa import resolver as R
from wpa.choices import Action
from wpa.team_sheets import SheetMon


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


MEOW = SheetMon(
    1, "meowscarada", "", "protean", ("knockoff", "flowertrick", "protect", "uturn"), ""
)


# --- the board -----------------------------------------------------------------


def test_the_board_keeps_a_changed_type_until_the_pokemon_leaves():
    log = _turns(
        "|t:|1\n|move|p1a: Whim|Moonblast|p2a: Inci\n"
        "|-start|p1a: Whim|typechange|Fairy|[from] ability: Protean\n|-damage|p2a: Inci|60/100",
        "|t:|2\n|move|p2b: Fini|Soak|p1b: Rock\n|-start|p1b: Rock|typechange|Water\n"
        "|move|p2a: Inci|Trick-or-Treat|p1a: Whim\n"
        "|-start|p1a: Whim|typeadd|Ghost|[from] move: Trick-or-Treat",
        "|t:|3\n|switch|p1a: Back|Back, L50|100/100",
    )
    whim = _mon(at_turn_start(log, 2), 0)
    assert whim["types"] == ["Fairy"] and whim["protean"] == 1
    s3 = at_turn_start(log, 3)
    whim, rock = _mon(s3, 0), _mon(s3, 1)
    assert rock["types"] == ["Water"] and "protean" not in rock  # Soak
    assert whim["types"] == ["Fairy"] and whim["typeadd"] == "Ghost"
    whim = _mon(at_turn_start(log, 4), 0)
    assert not {"types", "typeadd", "protean"} & set(whim)  # it left the field


def test_a_type_copied_burnt_up_or_reset_by_mega_evolution():
    log = _turns(
        "|t:|1\n|move|p1a: Whim|Reflect Type|p2a: Inci\n"
        "|-start|p1a: Whim|typechange|[from] move: Reflect Type|[of] p2a: Inci\n"
        "|move|p1b: Rock|Burn Up|p2a: Inci\n|-damage|p2a: Inci|50/100\n"
        "|-start|p1b: Rock|typechange|???/Ghost|[from] move: Burn Up",
        "|t:|2\n|-mega|p1b: Rock|Rock|Rockite",
    )
    s2 = at_turn_start(log, 2)
    assert _mon(s2, 0)["types"] == []  # copied from another: not followed
    assert _mon(s2, 1)["types"] == ["???", "Ghost"]
    assert "types" not in _mon(at_turn_start(log, 3), 1)  # Mega Evolution resets it


# --- the resolver ----------------------------------------------------------------


def _meow_board():
    b = board()
    b["p1"][0] = mon("meowscarada")
    return b


@needs_showdown
def test_protean_makes_the_user_the_type_of_its_move_once_per_switch_in(tools):
    dex, moves, calc = tools
    sheets = {"p1": (MEOW, SHEETS["p1"][1]), "p2": SHEETS["p2"]}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    knock = (
        Action(0, "move", move="knockoff", target=("foe", 1)),
        Action(1, "move", move="protect"),
    )
    outs = rv.resolve(_meow_board(), R.Field(), {"p1": knock, "p2": QUIET2})
    for o in outs:
        m = o.sides["p1"][0]
        assert m["types"] == ["Dark"] and m["protean"] == 1
        assert not o.partial
    # used once since it came in: Flower Trick leaves it Dark
    b = _meow_board()
    b["p1"][0].update(types=["Dark"], protean=1)
    trick = (Action(0, "move", move="flowertrick", target=("foe", 1)), knock[1])
    for o in rv.resolve(b, R.Field(), {"p1": trick, "p2": QUIET2}):
        assert o.sides["p1"][0]["types"] == ["Dark"]
    # a move of the type it already is: no change, and Protean not used up
    b = _meow_board()
    b["p1"][0]["types"] = ["Dark"]
    for o in rv.resolve(b, R.Field(), {"p1": knock, "p2": QUIET2}):
        assert o.sides["p1"][0]["types"] == ["Dark"]
        assert "protean" not in o.sides["p1"][0]


@needs_showdown
def test_damage_follows_the_changed_type(tools):
    """Earthquake on a Meowscarada made Dark: neutral, not resisted as on a
    Grass/Dark one (game 2616502323, turn 8)."""
    dex, moves, calc = tools
    sheets = {"p1": SHEETS["p1"], "p2": (MEOW, SHEETS["p2"][1])}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    p1 = (Action(0, "move", move="earthquake"), Action(1, "move", move="protect"))
    p2 = (
        Action(0, "move", move="knockoff", target=("foe", 1)),
        Action(1, "move", move="protect"),
    )

    def lost(types):
        b = board()
        b["p2"][0] = mon("meowscarada")
        b["p2"][0].update(boosts={"spe": -6}, protean=1)  # it moves last
        if types:
            b["p2"][0]["types"] = types
        outs = rv.resolve(b, R.Field(), {"p1": p1, "p2": p2})
        return sum(o.prob * (1 - o.sides["p2"][0]["hp_fraction"]) for o in outs)

    assert lost(["Dark"]) / lost(None) == pytest.approx(2.0, rel=0.15)


@needs_showdown
def test_the_calculator_takes_stab_from_the_types_it_has_now(tools):
    """The calculator gives Protean STAB on every move (as before Gen 9); told
    the types, it gives STAB as Showdown does: on the types the user has now."""
    from wpa.damage import request

    _dex, _moves, calc = tools
    a = {
        "species": "meowscarada",
        "nature": "adamant",
        "sps": {"atk": 32},
        "item": "",
        "ability": "protean",
        "boosts": {},
        "status": "",
        "hp": 1.0,
    }
    d = {
        "species": "kingambit",
        "nature": "serious",
        "sps": {},
        "item": "",
        "ability": "defiant",
        "boosts": {},
        "status": "",
        "hp": 1.0,
    }
    plain = calc.run([request(dict(a), d, "flowertrick")])[0]["rolls"]
    dark = calc.run([request(dict(a, types=["Dark"]), d, "flowertrick")])[0]["rolls"]
    assert sum(dark) / sum(plain) == pytest.approx(1 / 1.5, rel=0.03)
    # the defender's types: Kingambit made Water takes Flower Trick super effectively
    wet = calc.run([request(dict(a), dict(d, types=["Water"]), "flowertrick")])[0]
    assert sum(wet["rolls"]) / sum(plain) == pytest.approx(4.0, rel=0.05)


@needs_showdown
@pytest.mark.parametrize(
    ("move", "key", "value"),
    [
        ("soak", "types", ["Water"]),
        ("trickortreat", "typeadd", "Ghost"),
        ("forestscurse", "typeadd", "Grass"),
    ],
)
def test_moves_that_change_the_targets_type(tools, move, key, value):
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    p2 = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move=move, target=("foe", 0)),
    )
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    outs = rv.resolve(board(), R.Field(), {"p1": p1, "p2": p2})
    for o in outs:
        assert o.sides["p1"][0][key] == value
        assert f"move:{move}" not in o.partial
    assert rv.types("p1", 0, outs[0].sides["p1"][0]) == (
        value if key == "types" else ["Dragon", "Ground", value]
    )


@needs_showdown
def test_reflect_type_and_burn_up(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    p1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    p2 = (
        Action(0, "move", move="burnup", target=("foe", 0)),
        Action(1, "move", move="reflecttype", target=("foe", 0)),
    )
    outs = rv.resolve(board(), R.Field(), {"p1": p1, "p2": p2})
    for o in outs:
        assert o.sides["p2"][1]["types"] == ["Dragon", "Ground"]  # Garchomp's
        assert o.sides["p2"][0]["types"] == ["???", "Dark"]  # Fire burnt up
        assert not {"move:reflecttype", "move:burnup"} & o.partial
