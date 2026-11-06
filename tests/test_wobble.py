"""Tests for wpa/wobble.py (Week 9 Task 6, DEFINITIONS §10.2): how much win
probability moves when the model is retrained on resamples of the training sets."""

from __future__ import annotations

import numpy as np

from wpa import wobble as W
from wpa.features import Table


def table(units, turns=None):
    n = len(units)
    return Table(
        X=np.arange(n, dtype=np.float32).reshape(n, 1),
        y=np.zeros(n, dtype=np.int8),
        tag=np.array([u.split("/")[0] for u in units]),
        role=np.array([u.split("/")[1] if "/" in u else "p1" for u in units]),
        unit=np.array([u.split("/")[0] for u in units]),
        turn=np.array(turns if turns is not None else range(n), dtype=np.int16),
        columns=["a"],
    )


def test_a_resample_draws_whole_sets_with_replacement_and_repeats_by_seed():
    t = table(["s1", "s1", "s2", "s3", "s3", "s3"])
    a = W.resample_units(t, seed=1)
    b = W.resample_units(t, seed=1)
    assert np.array_equal(a.X, b.X)
    sizes = {"s1": 2, "s2": 1, "s3": 3}
    for u in np.unique(a.unit):  # every drawn set comes with all its rows
        assert (a.unit == u).sum() % sizes[str(u)] == 0
    draws = [W.resample_units(t, seed=s).unit.tolist() for s in range(20)]
    assert len({tuple(d) for d in draws}) > 1


def test_identical_predictions_do_not_wobble():
    t = table(["s1/p1", "s1/p1", "s2/p1"])
    preds = np.tile([0.2, 0.5, 0.9], (3, 1))
    w = W.wobble(preds, t)
    assert w["level_median"] == 0 and w["swing_median"] == 0
    assert w["level_share_over_threshold"] == 0


def test_wobble_is_the_spread_across_retrained_models_in_points():
    t = table(["s1/p1", "s1/p1"], turns=[1, 2])
    preds = np.array([[0.40, 0.50], [0.42, 0.50], [0.44, 0.50]])
    w = W.wobble(preds, t)
    # position 1 spreads by a standard deviation of 2 points; position 2 by 0
    assert abs(w["levels"][0] - 2.0) < 1e-9 and w["levels"][1] == 0
    # the one swing (turn 1 -> turn 2) is 10, 8 and 6 points: also 2 points apart
    assert len(w["swings"]) == 1 and abs(w["swings"][0] - 2.0) < 1e-9


def test_swings_are_taken_within_one_side_of_one_game_in_turn_order():
    t = table(["g1/p1", "g1/p2", "g1/p1", "g2/p1"], turns=[2, 1, 1, 1])
    preds = np.array([[0.6, 0.5, 0.5, 0.5], [0.7, 0.5, 0.5, 0.5]])
    w = W.wobble(preds, t)
    assert len(w["swings"]) == 1  # only g1/p1 has two decision points
