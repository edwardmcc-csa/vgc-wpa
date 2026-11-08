"""Tests for the resolver's pool of boards (Week 10, found by Task 3's real-data
check): boards are merged as they arrive, and the cap is applied as the pool
grows, so a turn never holds every board of a step at once.

Two real Reg M-A turns (Discharge and Heat Wave; Matcha Gotcha and Rock Slide)
held about 89,000 boards before the one merge at the end of the step and ran
out of memory, in Week 9's code as in Week 10's. The pool must give exactly the
boards, chances and grid that merging (and capping) at the end gives. For that,
each coarser grid's cells are two whole cells of the one before (a turn under the
cap is untouched): merging on one grid and then the next is merging on the next.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

from wpa import resolver as R


def _mon(hp: float, status: str = "") -> dict:
    return {
        "species": "garchomp",
        "hp_fraction": hp,
        "fainted": hp == 0,
        "active": True,
        "mega": False,
        "boosts": {},
        "status": status,
        "item": "",
        "moved": False,
        "last_move": "",
        "protect_streak": 0,
    }


def _worlds(n: int, seed: int) -> list:
    """`n` boards: hit points on a 0.001 grid (many fall in one 0.02 cell), a
    status on some (never merged away), a few below the prune line."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        sides = {
            "p1": [_mon(rng.randrange(1001) / 1000), _mon(1.0)],
            "p2": [
                _mon(rng.randrange(1001) / 1000, rng.choice(["", "", "", "par"])),
                _mon(rng.randrange(1001) / 1000),
            ],
        }
        p = rng.random() * (1e-9 if rng.random() < 0.05 else 1.0)
        out.append(R._World(p, sides, R.Field(), set()))
    return out


def _copy(worlds: list) -> list:
    return [w.clone() for w in worlds]


def _chunks(worlds: list, seed: int) -> list[list]:
    rng = random.Random(seed)
    out, i = [], 0
    while i < len(worlds):
        k = rng.randrange(1, 40)
        out.append(worlds[i : i + k])
        i += k
    return out


def _same(a: list, b: list) -> None:
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x.sides == y.sides  # the same board kept for each cell
        assert abs(x.p - y.p) < 1e-12


def test_a_pool_merges_boards_as_they_arrive_exactly_as_one_merge_would():
    base = _worlds(3000, seed=1)
    for resolution, prune in ((None, 0.0), (0.02, 0.0), (0.02, 1e-6)):
        batch = R._merge(_copy(base), resolution, prune)
        pool = R._Pool(resolution, prune)
        for part in _chunks(_copy(base), seed=2):
            pool.add(part)
        _same(pool.worlds(), batch)
        assert pool.coarsest == 0.0


def test_coarser_grids_nest_so_merging_twice_is_merging_once():
    base = _worlds(3000, seed=7)
    for resolution in (None, 0.02):
        for k in range(1, 6):
            once = R._merge(_copy(base), resolution, coarsen=k)
            twice = R._merge(
                R._merge(_copy(base), resolution, coarsen=k - 1), resolution, coarsen=k
            )
            _same(twice, once)
    # level 0 is the resolver's own grid, as before
    _same(R._merge(_copy(base), 0.02, coarsen=0), R._merge(_copy(base), 0.02))


def _capped(worlds: list, resolution, cap: int):
    """What the resolver did before: one merge, then the cap."""
    stub = SimpleNamespace(cap=cap, resolution=resolution, coarsest=resolution or 0.0)
    out = R.Resolver._capped(stub, R._merge(worlds, resolution, 0.0))
    return out, stub.coarsest


def test_a_capped_pool_gives_the_boards_and_grid_that_capping_at_the_end_gives():
    base = _worlds(6000, seed=3)
    for cap in (40, 200, 900, 20000):
        want, grid = _capped(_copy(base), 0.02, cap)
        pool = R._Pool(0.02, 0.0, cap)
        for part in _chunks(_copy(base), seed=4):
            pool.add(part)
        _same(pool.worlds(), want)
        assert max(pool.coarsest, 0.02) == grid
        assert abs(sum(w.p for w in pool.worlds()) - sum(w.p for w in base)) < 1e-9


def test_a_capped_pool_never_holds_more_than_the_cap_plus_one_arrival():
    base = _worlds(6000, seed=5)
    parts = _chunks(_copy(base), seed=6)
    pool = R._Pool(0.02, 0.0, 200)
    for part in parts:
        pool.add(part)
    assert pool.peak <= 200 + max(len(p) for p in parts)
    assert len(pool.worlds()) <= 200
