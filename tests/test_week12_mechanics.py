"""Rules the resolver check found missing in Week 12 (Task 1's reasons left). On
the 892 games, turns where these acted were missed far more often than the 19%
of all turns, and none was marked partly modelled:
- Hospitality: 228 turns, 64% missed (Sinistcha heals its ally a quarter on
  coming in);
- Regenerator: 10 turns, all missed (a third back on switching out);
- Infestation and the other binding moves: 18 turns, 94% missed (an eighth at
  each end of turn while bound);
- Solar Power: 4 turns, all missed (an eighth lost at each end of turn in sun)."""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from tests.test_board_effects import at_turn_start
from tests.test_more_mechanics import _mon, _turns, needs_showdown
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


SINISTCHA = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
QUIET1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))


def _three(tools, p2_first=None):
    """p2 with a third Pokemon, Sinistcha, on the bench."""
    dex, moves, calc = tools
    first = p2_first or SHEETS["p2"][0]
    sheets = {"p1": SHEETS["p1"], "p2": (first, SHEETS["p2"][1], SINISTCHA)}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p2"].append(mon("sinistcha"))
    b["p2"][2].update(active=False, hp_fraction=1.0)
    return rv, b


@needs_showdown
def test_hospitality_heals_the_ally_a_quarter_on_coming_in(tools):
    rv, b = _three(tools)
    b["p2"][1]["hp_fraction"] = 0.5
    p2 = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 1)
        assert o.sides["p2"][1]["hp_fraction"] == pytest.approx(
            (round(0.5 * hp) + hp // 4) / hp, abs=1 / hp
        )


@needs_showdown
def test_regenerator_heals_a_third_on_switching_out(tools):
    regen = SheetMon(1, "incineroar", "", "regenerator", ("protect",), "")
    rv, b = _three(tools, regen)
    b["p2"][0]["hp_fraction"] = 0.4
    p2 = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 0)
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(
            (round(0.4 * hp) + hp // 3) / hp, abs=1 / hp
        )
        assert not o.sides["p2"][0]["active"]


@needs_showdown
def test_a_binding_move_costs_an_eighth_at_each_end_of_turn(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    # already bound: an eighth at the end of the turn
    b = board()
    b["p2"][0]["bound"] = 8
    p2 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 0)
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx((hp - hp // 8) / hp)
    # Infestation binds what it hits, and the first eighth comes the same turn
    p1 = (
        Action(0, "move", move="infestation", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    outs = rv.resolve(board(), R.Field(), {"p1": p1, "p2": p2})
    hit = [o for o in outs if o.sides["p2"][0].get("bound")]
    assert sum(o.prob for o in hit) == pytest.approx(1.0)  # it never misses
    assert not any(o.partial for o in outs)


@needs_showdown
def test_solar_power_costs_an_eighth_in_sun(tools):
    dex, moves, calc = tools
    sol = SheetMon(1, "garchomp", "", "solarpower", ("swordsdance", "protect"), "")
    rv = R.Resolver(
        dex, moves, calc, {"p1": (sol, SHEETS["p1"][1]), "p2": SHEETS["p2"]}, SPREADS
    )
    p2 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    sunny = R.Field(weather="sunnyday", weather_left=3)
    for o in rv.resolve(board(), sunny, {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p1", 0)
        assert o.sides["p1"][0]["hp_fraction"] == pytest.approx((hp - hp // 8) / hp)
    for o in rv.resolve(board(), R.Field(), {"p1": QUIET1, "p2": p2}):
        assert o.sides["p1"][0]["hp_fraction"] == 1.0


def test_the_board_keeps_a_binding_until_it_ends_or_the_pokemon_leaves():
    log = _turns(
        "|t:|1\n|move|p2a: Inci|Infestation|p1a: Whim\n|-damage|p1a: Whim|90/100\n"
        "|-activate|p1a: Whim|move: Infestation|[of] p2a: Inci\n"
        "|-damage|p1a: Whim|78/100|[from] move: Infestation|[partiallytrapped]",
        "|t:|2\n|-end|p1a: Whim|Infestation|[partiallytrapped]",
        "|t:|3\n|move|p2a: Inci|Infestation|p1b: Rock\n|-damage|p1b: Rock|90/100\n"
        "|-activate|p1b: Rock|move: Infestation|[of] p2a: Inci",
        "|t:|4\n|switch|p1b: Back|Back, L50|100/100",
    )
    assert _mon(at_turn_start(log, 2), 0)["bound"] == 8
    assert "bound" not in _mon(at_turn_start(log, 3), 0)  # it ended
    assert _mon(at_turn_start(log, 4), 1)["bound"] == 8
    assert "bound" not in _mon(at_turn_start(log, 5), 1)  # it left the field


def _mean_lost(rv, b, acts, side="p1", idx=0):
    outs = rv.resolve(b, R.Field(), acts)
    return sum(o.prob * (1 - o.sides[side][idx]["hp_fraction"]) for o in outs)


@needs_showdown
@pytest.mark.parametrize(
    ("holder", "ability", "ratio"),
    [
        # Fairy Aura on the field, whoever holds it: Fairy moves x 5448/4096
        (("p1", 1), "fairyaura", 5448 / 4096),
        # Friend Guard on the target's ally: x 0.75
        (("p1", 1), "friendguard", 0.75),
        # (Battery, Power Spot and the like on the attacker's ally are passed
        # too, but the calculator's Champions rules do not use them)
    ],
)
def test_auras_and_allies_change_the_damage(tools, holder, ability, ratio):
    """Found by the resolver check: Mega Floette's Fairy Aura (Light of Ruin in
    game 2608046888) was not passed to the calculator."""
    dex, moves, calc = tools
    acts = {
        "p1": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="moonblast", target=("foe", 0)),
        ),
    }
    plain = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    role, i = holder
    mons = list(SHEETS[role])
    old = mons[i]
    mons[i] = SheetMon(old.position, old.species, old.item, ability, old.moves, "")
    sheets = {**SHEETS, role: tuple(mons)}
    with_it = R.Resolver(dex, moves, calc, sheets, SPREADS)
    got = _mean_lost(with_it, board(), acts) / _mean_lost(plain, board(), acts)
    assert got == pytest.approx(ratio, rel=0.04)
