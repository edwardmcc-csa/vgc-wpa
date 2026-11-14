"""Week 12 Task 4: a cheaper spread method. Week 10 averaged every turn over two
spreads and it cost 14 to 19 times the time. Here a hit branches on a Pokemon's
likely spreads only where one of them changes the chance of a knock-out by a
quarter or more; elsewhere the likeliest spread alone, as before. Damage on
another spread is put in the likeliest spread's hit points, so the board keeps
one scale."""

from __future__ import annotations

import pytest

from tests.test_resolver import BULK, FULL, ROOT, SHEETS, SPREADS, board
from wpa import resolver as R
from wpa.choices import Action
from wpa.spreads import Spread

FRAIL = Spread("timid", (0, 0, 0, 32, 0, 32), 1.0)

pytestmark = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


CLAW = (
    Action(0, "move", move="dragonclaw", target=("foe", 0)),
    Action(1, "move", move="protect"),
)
QUIET = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))


def _ko(outs):
    return sum(o.prob for o in outs if o.sides["p2"][0]["fainted"])


def _fraction_range(rv, spread):
    """Dragon Claw's damage on Incineroar with `spread`, as a share of its hit
    points (no critical hit)."""
    b = board()
    w = R._World(1.0, {r: [dict(m) for m in b[r]] for r in b}, R.Field(), set())
    ans = rv._damage(w, "p1", CLAW[0], ("p2", 0), False, False, (None, spread))
    hp = rv.max_hp("p2", 0, spread)
    return min(ans["rolls"]) / hp, max(ans["rolls"]) / hp


def _between(dex, moves, calc):
    """A hit-point share that the bulky spread always survives and the frail one
    never does."""
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    bulk_hi = _fraction_range(rv, BULK)[1]
    frail_lo = _fraction_range(rv, FRAIL)[0]
    assert bulk_hi < frail_lo
    return (bulk_hi + frail_lo) / 2


def test_a_hit_branches_on_the_spreads_that_decide_the_knock_out(tools):
    dex, moves, calc = tools
    hp = _between(dex, moves, calc)
    dists = {("p2", 0): [(BULK, 0.6), (FRAIL, 0.4)]}
    plain = R.Resolver(
        dex, moves, calc, SHEETS, SPREADS, dists=dists, speed_beliefs=False
    )
    branch = R.Resolver(
        dex,
        moves,
        calc,
        SHEETS,
        SPREADS,
        dists=dists,
        spread_hits=True,
        speed_beliefs=False,
    )
    before = _ko(plain.resolve(board(hp), R.Field(), {"p1": CLAW, "p2": QUIET}))
    after = _ko(branch.resolve(board(hp), R.Field(), {"p1": CLAW, "p2": QUIET}))
    assert before < 0.1  # the likeliest (bulky) spread survives but for a crit
    assert after == pytest.approx(0.4 + 0.6 * before, abs=0.03)


def test_no_branch_where_no_likely_spread_changes_the_knock_out(tools):
    dex, moves, calc = tools
    dists = {("p2", 0): [(BULK, 0.6), (FRAIL, 0.4)]}
    plain = R.Resolver(
        dex, moves, calc, SHEETS, SPREADS, dists=dists, speed_beliefs=False
    )
    branch = R.Resolver(
        dex,
        moves,
        calc,
        SHEETS,
        SPREADS,
        dists=dists,
        spread_hits=True,
        speed_beliefs=False,
    )
    a = plain.resolve(board(1.0), R.Field(), {"p1": CLAW, "p2": QUIET})
    b = branch.resolve(board(1.0), R.Field(), {"p1": CLAW, "p2": QUIET})
    key = sorted((round(o.prob, 9), o.sides["p2"][0]["hp_fraction"]) for o in a)
    assert sorted((round(o.prob, 9), o.sides["p2"][0]["hp_fraction"]) for o in b) == key


def test_the_attackers_spread_counts_too(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    weak = Spread("modest", (0, 0, 0, 32, 0, 32), 1.0)
    b = board()
    w = R._World(1.0, {r: [dict(m) for m in b[r]] for r in b}, R.Field(), set())
    strong = rv._damage(w, "p1", CLAW[0], ("p2", 0), False, False)
    soft = rv._damage(w, "p1", CLAW[0], ("p2", 0), False, False, (weak, None))
    assert max(soft["rolls"]) < min(strong["rolls"])  # and kept apart in the cache
    hp = (max(soft["rolls"]) + min(strong["rolls"])) / 2 / rv.max_hp("p2", 0)
    dists = {("p1", 0): [(FULL, 0.5), (weak, 0.5)]}
    branch = R.Resolver(
        dex,
        moves,
        calc,
        SHEETS,
        SPREADS,
        dists=dists,
        spread_hits=True,
        speed_beliefs=False,
    )
    ko = _ko(branch.resolve(board(hp), R.Field(), {"p1": CLAW, "p2": QUIET}))
    assert ko == pytest.approx(0.5, abs=0.05)


def test_spread_beliefs_alone_do_not_change_move_order_or_damage(tools):
    """Week 11's Speed branching stays with its own setting."""
    dex, moves, calc = tools
    dists = {("p2", 0): [(BULK, 0.6), (FRAIL, 0.4)]}
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS, dists=dists)
    assert rv.speed_beliefs is True  # as before: dists given, Speeds branch
    rv = R.Resolver(
        dex,
        moves,
        calc,
        SHEETS,
        SPREADS,
        dists=dists,
        spread_hits=True,
        speed_beliefs=False,
    )
    assert rv.speed_beliefs is False


# --------------------------------------------------------------------------
# Week 13 Task 1: every hit weighed over the spreads players run
# --------------------------------------------------------------------------


def _mean_lost(outs, scale=1.0):
    tot = sum(o.prob for o in outs)
    return (
        sum(o.prob * (1 - o.sides["p2"][0]["hp_fraction"]) for o in outs) * scale / tot
    )


def test_with_spread_damage_every_hit_weighs_the_likely_spreads(tools):
    """A hit that knocks out on no likely spread did not branch (Week 12 Task 4):
    the likeliest spread alone set its damage, so a bulkier player's Pokemon
    took too much. With `spread_damage`, the damage is weighed over the likely
    spreads by their chances, in the likeliest spread's hit points."""
    dex, moves, calc = tools
    dists = {("p2", 0): [(FULL, 0.6), (BULK, 0.4)]}
    frail = {**SPREADS, ("p2", 0): FULL}
    one = {"p1": CLAW, "p2": QUIET}

    def lost(spreads, **kw):
        rv = R.Resolver(
            dex, moves, calc, SHEETS, spreads, dists=dists, speed_beliefs=False, **kw
        )
        return rv, rv.resolve(board(1.0), R.Field(), one)

    rv, outs = lost(frail)
    on_full = _mean_lost(outs)
    rv_b, outs_b = lost(SPREADS)
    on_bulk = _mean_lost(outs_b, rv_b.max_hp("p2", 0, BULK) / rv.max_hp("p2", 0, FULL))
    assert on_bulk < on_full - 0.03  # the bulky spread takes less
    _rv, outs = lost(frail, spread_hits=True)
    assert _mean_lost(outs) == pytest.approx(
        on_full, abs=1e-9
    )  # no knock-out: no branch
    _rv, outs = lost(frail, spread_hits=True, spread_damage=True)
    assert _mean_lost(outs) == pytest.approx(0.6 * on_full + 0.4 * on_bulk, abs=0.01)
