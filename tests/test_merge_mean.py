"""Week 18 (the PO's call, 24 Nov): boards merged on the hit-point grid keep the
chance-weighted mean of their hit points, not the first board's.

Found by the damage estimate's check on the bot's own games: real damage was
over 10% above the estimate on 21% of clean hits, mostly spread moves. On a
5% grid, all 16 rolls of a hit usually fall in one cell, and the cell kept the
hit points of the first board to arrive: the lowest roll. So every hit read
as its smallest roll (Garchomp's Rock Slide into Mega Staraptor: 36 of 190 HP
on every board, where the rolls run 36 to 43 and the log showed 42)."""

from __future__ import annotations

import pytest

from tests.test_resolver import ROOT, SHEETS, SPREADS, board
from tests.test_resolver_pool import _mon
from wpa import resolver as R
from wpa.choices import Action


def _w(p: float, hp_a: float, hp_b: float = 1.0, status: str = "") -> R._World:
    sides = {"p1": [_mon(hp_a), _mon(1.0)], "p2": [_mon(hp_b, status), _mon(1.0)]}
    return R._World(p, sides, R.Field(), set())


def test_merged_boards_keep_the_chance_weighted_hit_points():
    out = R._merge([_w(0.25, 0.80), _w(0.75, 0.82)], 0.05)
    assert len(out) == 1
    assert out[0].p == pytest.approx(1.0)
    assert out[0].sides["p1"][0]["hp_fraction"] == pytest.approx(0.815)
    assert out[0].sides["p1"][1]["hp_fraction"] == 1.0


def test_the_pool_keeps_the_same_mean_as_one_merge():
    worlds = [_w(0.1 * (k + 1), 0.70 + 0.004 * k) for k in range(8)]
    pool = R._Pool(0.05)
    for w in worlds:
        pool.add([w.clone()])
    batch = R._merge([w.clone() for w in worlds], 0.05)
    assert len(pool.worlds()) == len(batch)
    for a, b in zip(pool.worlds(), batch):
        assert a.p == pytest.approx(b.p)
        assert a.sides["p1"][0]["hp_fraction"] == pytest.approx(
            b.sides["p1"][0]["hp_fraction"]
        )
    mean = sum(w.p * w.sides["p1"][0]["hp_fraction"] for w in worlds) / sum(
        w.p for w in worlds
    )
    total = sum(b.sides["p1"][0]["hp_fraction"] * b.p for b in batch) / sum(
        b.p for b in batch
    )
    assert total == pytest.approx(mean)


def test_merging_never_changes_another_board_that_shares_a_pokemon():
    a, b = _w(0.5, 0.80), _w(0.5, 0.84)
    other = R._World(
        0.3,
        {"p1": [a.sides["p1"][0], _mon(1.0)], "p2": [_mon(1.0, "par"), _mon(1.0)]},
        R.Field(),
        set(),
    )
    R._merge([a, b, other], 0.05)
    assert other.sides["p1"][0]["hp_fraction"] == 0.80


@pytest.fixture(scope="module")
def parts():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    if not (ROOT / "pokemon-showdown" / "dist").exists():
        pytest.skip("needs the pinned Showdown build")
    c = DM.Calc()
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    yield dex, R.load_moves(ROOT / "pokemon-showdown", "championsregma"), c
    c.close()


def _mean_hp(outs, role="p2", idx=0) -> float:
    tot = sum(o.prob for o in outs)
    return sum(o.prob * o.sides[role][idx]["hp_fraction"] for o in outs) / tot


@pytest.mark.parametrize("move", ["stoneedge", "rockslide"])
def test_on_the_grid_a_hit_does_as_much_on_average_as_without_one(parts, move):
    """The expected hit points after a hit (single or spread), on the 5% grid
    the advice uses, against the boards kept exact: the same, within half a
    point (the first board kept read about a third of the rolls' spread low)."""
    dex, moves, calc = parts
    acts = {
        "p1": (
            Action(0, "move", move=move, target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (Action(0, "move", move="protect"), Action(1, "move", move="tailwind")),
    }
    acts["p2"] = (Action(0, "move", move="swordsdance"), acts["p2"][1])
    exact = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(
        board(), R.Field(), acts
    )
    grid = R.Resolver(dex, moves, calc, SHEETS, SPREADS, resolution=0.05).resolve(
        board(), R.Field(), acts
    )
    assert _mean_hp(grid) == pytest.approx(_mean_hp(exact), abs=0.005)
