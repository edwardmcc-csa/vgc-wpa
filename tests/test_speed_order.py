"""Tests for Week 11 Task 2: Speed order from the hidden spreads.

Where two Pokemon's order depends on Speed spreads the game so far has not
settled, the resolver branches on the order, each with its chance from the
spread beliefs, instead of taking the likeliest spread's order. Beliefs are kept
at every decision point, not only the likeliest spread.
"""

from __future__ import annotations

import pytest

from tests.test_resolver import ROOT, SHEETS, SPREADS, board
from wpa import resolver as R
from wpa.choices import Action
from wpa.spreads import GameBeliefs, Spread

needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)

FAST = Spread("jolly", (0, 32, 0, 0, 0, 32), 0.7)
SLOW = Spread("brave", (32, 32, 0, 0, 0, 0), 0.3)
MID = Spread("adamant", (0, 32, 0, 0, 0, 16), 1.0)


def test_the_beliefs_are_kept_at_every_decision_not_only_the_likeliest():
    key = ("p1", 0)
    g = GameBeliefs({key: [FAST, SLOW]})
    assert g.dists_at(3)[key] == [(FAST, 0.7), (SLOW, 0.3)]
    g.dists.append((5, key, [(FAST, 0.2), (SLOW, 0.8)]))  # a move order seen at block 5
    assert g.dists_at(5)[key] == [
        (FAST, 0.7),
        (SLOW, 0.3),
    ]  # from before the block only
    assert g.dists_at(6)[key] == [(FAST, 0.2), (SLOW, 0.8)]
    assert g.at(6)[key] == FAST  # the likeliest is unchanged by this record alone


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


def _acts():
    # p1's Garchomp and p2's Incineroar both attack; nothing has priority
    return {
        "p1": (
            Action(0, "move", move="dragonclaw", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="flareblitz", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
    }


def _first_attacker(order) -> str:
    """The side whose attack (not Protect, which has priority) goes first."""
    return next(r for r, a in order if a.move != "protect")


def _sheets():
    # p2's first Pokemon is a Garchomp too, so that Speed is the only difference
    from wpa.team_sheets import SheetMon

    chomp = SheetMon(1, "garchomp", "", "roughskin", ("dragonclaw", "protect"), "")
    return dict(SHEETS, p2=(chomp, SHEETS["p2"][1]))


@needs_showdown
def test_an_unsettled_speed_gives_each_order_its_chance(tools):
    dex, moves, calc = tools
    b = board()
    b["p2"][0]["species"] = "garchomp"
    spreads = {**SPREADS, ("p1", 0): FAST, ("p2", 0): MID}
    dists = {("p1", 0): [(FAST, 0.7), (SLOW, 0.3)], ("p2", 0): [(MID, 1.0)]}
    rv = R.Resolver(dex, moves, calc, _sheets(), spreads, dists=dists)
    orders = rv.orders(b, R.Field(), _acts())
    assert sum(p for _, p in orders) == pytest.approx(1.0)
    first = {}
    for order, p in orders:
        r = _first_attacker(order)
        first[r] = first.get(r, 0.0) + p
    assert first["p1"] == pytest.approx(0.7) and first["p2"] == pytest.approx(0.3)
    # Trick Room turns it round
    tr = R.Field(trickroom=3)
    first_tr = {}
    for order, p in rv.orders(b, tr, _acts()):
        r = _first_attacker(order)
        first_tr[r] = first_tr.get(r, 0.0) + p
    assert first_tr["p1"] == pytest.approx(0.3)


@needs_showdown
def test_without_beliefs_the_likeliest_spread_decides_as_before(tools):
    dex, moves, calc = tools
    b = board()
    b["p2"][0]["species"] = "garchomp"
    spreads = {**SPREADS, ("p1", 0): FAST, ("p2", 0): MID}
    rv = R.Resolver(dex, moves, calc, _sheets(), spreads)
    (only,) = rv.orders(b, R.Field(), _acts())
    assert only[1] == 1.0 and _first_attacker(only[0]) == "p1"


@needs_showdown
def test_a_turn_resolved_with_beliefs_still_adds_up_to_one(tools):
    dex, moves, calc = tools
    b = board()
    b["p2"][0]["species"] = "garchomp"
    spreads = {**SPREADS, ("p1", 0): FAST, ("p2", 0): MID}
    dists = {("p1", 0): [(FAST, 0.7), (SLOW, 0.3)]}
    rv = R.Resolver(dex, moves, calc, _sheets(), spreads, dists=dists)
    outs = rv.resolve(b, R.Field(), _acts())
    assert sum(o.prob for o in outs) == pytest.approx(1.0)
