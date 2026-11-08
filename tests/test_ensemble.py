"""Tests for wpa/ensemble.py (Week 10 Task 5; DEFINITIONS §10.2, revision 9): the
win probability the report shows is the average of 10 models, each trained on a
resample of the training sets.

- the average and its two halves;
- each member's resample is fixed by its number, and which sets it left out
  (out of bag) can be recovered from it;
- Reg M-B's correction is fitted on out-of-bag predictions only;
- the averaged model's own noise, measured from its two halves.
"""

from __future__ import annotations

import numpy as np
import pytest

from wpa import ensemble as E
from wpa.evaluate import apply_temperature
from wpa.features import Table


class Const:
    def __init__(self, p):
        self.p = np.asarray(p, dtype=float)

    def predict(self, X):
        return self.p[: len(X)]


def test_the_average_of_the_members_and_its_halves():
    members = [
        Const([0.2, 0.4]),
        Const([0.4, 0.6]),
        Const([0.6, 0.8]),
        Const([0.8, 0.2]),
    ]
    m = E.AveragedModel(members)
    X = np.zeros((2, 3))
    assert m.predict(X) == pytest.approx([0.5, 0.5])
    a, b = m.halves(X)
    assert a == pytest.approx([0.3, 0.5]) and b == pytest.approx([0.7, 0.5])
    hot = E.AveragedModel(members, temperature=0.5)
    assert hot.predict(X) == pytest.approx(apply_temperature(np.array([0.5, 0.5]), 0.5))


def _table(units, y=None):
    n = len(units)
    return Table(
        np.zeros((n, 2), dtype=np.float32),
        np.asarray(y if y is not None else [0] * n),
        np.array([f"g{i}" for i in range(n)]),
        np.array(["p1"] * n),
        np.asarray(units),
        np.zeros(n, dtype=int),
        ["a", "b"],
    )


def test_each_member_resample_is_fixed_by_its_number_and_knows_what_it_left_out():
    t = _table(["s1", "s1", "s2", "s3", "s4", "s5", "s6", "s7"])
    r1, bag1 = E.member_resample(t, 1)
    r1b, bag1b = E.member_resample(t, 1)
    _r2, bag2 = E.member_resample(t, 2)
    assert bag1 == bag1b and list(r1.unit) == list(r1b.unit)
    assert bag1 != bag2  # different members, different resamples
    assert set(r1.unit) == bag1  # every row of the resample is in the bag
    assert len(r1.unit) >= 7  # whole sets: s1 brings both its rows each time


def test_reg_mb_correction_uses_only_out_of_bag_predictions():
    rng = np.random.default_rng(0)
    n = 4000
    units = np.array([f"s{i}" for i in range(n)])
    z = rng.normal(size=n) * 1.5
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    over = 1 / (1 + np.exp(-2 * z))  # every member twice as confident as it should be
    preds = [over.copy() for _ in range(10)]
    # members that saw a set predict it perfectly; that must not reach the fit
    bags = []
    for k in range(10):
        bag = set(units[rng.random(n) < 0.63])
        bags.append(bag)
        seen = np.isin(units, list(bag))
        preds[k][seen] = y[seen]
    t, used = E.oob_temperature(np.array(preds), bags, units, y)
    assert t == pytest.approx(2.0, rel=0.15)  # softens the overconfidence
    # with 10 members, about 1% of sets are in every bag (0.63 ** 10)
    assert 0.97 < used / n <= 1.0


def test_the_noise_of_the_average_is_measured_from_its_two_halves():
    rng = np.random.default_rng(1)
    t = _table([f"s{i // 4}" for i in range(4000)])
    t = Table(
        t.X,
        t.y,
        np.array([f"g{i // 4}" for i in range(4000)]),
        t.role,
        t.unit,
        np.tile(np.arange(4), 1000),
        t.columns,
    )
    truth = rng.random(4000) * 0.8 + 0.1
    sigma = 0.03  # one model's noise: 3 points
    preds = truth + rng.normal(scale=sigma, size=(10, 4000))
    out = E.noise(preds, t)
    # the 10-model average: 3 / sqrt(10), about 0.95 points
    assert out["average_level"] == pytest.approx(100 * sigma / np.sqrt(10), rel=0.1)
    assert out["single_level"] == pytest.approx(100 * sigma, rel=0.1)
    assert (
        out["average_swing"] > out["average_level"]
    )  # a swing holds two levels' noise
    assert out["halves_level"] == pytest.approx(out["average_level"], rel=0.15)


def test_the_split_uses_the_averaged_model_when_there_is_one(tmp_path):
    import json

    from wpa import attribution as A
    from wpa.features import columns
    from wpa.model import GRID, fit, save

    cols = columns("A")
    rng = np.random.default_rng(2)
    X = rng.random((300, len(cols))).astype(np.float32)
    y = (X[:, 0] + 0.3 * rng.random(300) > 0.6).astype(int)
    t = Table(
        X,
        y,
        np.array([f"g{i // 6}" for i in range(300)]),
        np.array(["p1"] * 300),
        np.array([f"s{i // 12}" for i in range(300)]),
        np.zeros(300, dtype=int),
        cols,
    )
    members = []
    for k in range(1, E.COUNT + 1):
        m, _info = fit(E.member_resample(t, k)[0], t, GRID[2], max_iter=10)
        assert m is not None
        members.append(m)
        save(m, tmp_path / "regma" / f"A.r{k:02d}.pkl")
    (tmp_path / "regma" / "A.ensemble.json").write_text(
        json.dumps({"members": E.COUNT, "temperature": None}), encoding="utf-8"
    )
    predict = A.wp_model(tmp_path, "regma", "A")  # no plain A.pkl is needed
    want = np.mean([m.predict(X[:7]) for m in members], axis=0)
    assert predict(X[:7]) == pytest.approx(want)
