"""Tests for wpa/model.py (Week 5 Task 6): the v1 gradient-boosted model.

Needs the model extra (scikit-learn); skipped where it is not installed.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sklearn")

from wpa import model as M  # noqa: E402
from wpa.features import Table  # noqa: E402

COLS = [
    "a_our_hp",
    "a_their_hp",
    "a_our_remaining",
    "a_their_remaining",
    "c_field_trickroom",
    "a_score_our",
    "a_score_their",
]


def table(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    X = np.zeros((n, len(COLS)), dtype=np.float32)
    X[:, 0] = rng.uniform(0, 4, n)
    X[:, 1] = rng.uniform(0, 4, n)
    X[:, 2] = rng.integers(1, 5, n)
    X[:, 3] = rng.integers(1, 5, n)
    X[:, 4] = rng.integers(0, 4, n)
    p = 1 / (1 + np.exp(-(X[:, 0] - X[:, 1] + 0.5 * (X[:, 2] - X[:, 3]))))
    y = (rng.random(n) < p).astype(np.int8)
    units = np.array([f"u{i // 10}" for i in range(n)])
    return Table(
        X, y, units, np.array(["p1"] * n), units, np.zeros(n, np.int16), list(COLS)
    )


def fit(seed=3, **kw):
    return M.fit(
        table(seed=0), table(seed=1), M.GRID[0], seed=seed, max_iter=60, step=10, **kw
    )


def test_a_mirrored_position_gets_exactly_one_half():
    model, _ = fit()
    x = np.array([[2.0, 2.0, 3, 3, 1, 1, 1]], dtype=np.float32)
    assert model.predict(x)[0] == pytest.approx(0.5, abs=1e-12)


def test_the_two_sides_of_one_position_sum_to_one():
    model, _ = fit()
    X = table(200, seed=5).X
    mirrored = X[:, model.mirror]
    assert np.allclose(model.predict(X) + model.predict(mirrored), 1.0)


def test_a_side_with_nothing_left_has_lost():
    model, _ = fit()
    lost = np.array([[1.0, 2.0, 0, 3, 0, 0, 0]], dtype=np.float32)
    won = np.array([[1.0, 0.0, 2, 0, 0, 0, 0]], dtype=np.float32)
    assert model.predict(lost)[0] == 0.0 and model.predict(won)[0] == 1.0


def test_training_is_deterministic_for_a_seed():
    a, _ = fit(seed=7)
    b, _ = fit(seed=7)
    X = table(300, seed=9).X
    assert np.array_equal(a.predict(X), b.predict(X))


def test_the_number_of_rounds_is_chosen_on_validation_and_recorded():
    model, info = fit()
    assert 0 < model.n_iter <= 60
    assert info["curve"] and all(len(step) == 2 for step in info["curve"])
    assert info["best_validation_brier"] < 0.25


def test_the_saved_model_refuses_other_features(tmp_path):
    model, _ = fit()
    path = tmp_path / "m.pkl"
    M.save(model, path)
    again = M.load(path, COLS)
    X = table(50, seed=4).X
    assert np.array_equal(again.predict(X), model.predict(X))
    with pytest.raises(ValueError):
        M.load(path, COLS[:-1])


def test_recalibration_keeps_the_symmetry():
    model, _ = fit()
    val = table(seed=1)
    model = M.recalibrate(model, val)
    x = np.array([[2.0, 2.0, 3, 3, 1, 1, 1]], dtype=np.float32)
    assert model.predict(x)[0] == pytest.approx(0.5, abs=1e-12)
    X = table(200, seed=5).X
    assert np.allclose(model.predict(X) + model.predict(X[:, model.mirror]), 1.0)


def test_the_grid_is_fixed_before_any_result():
    assert len(M.GRID) == 4
    assert {g["learning_rate"] for g in M.GRID} == {0.05, 0.1}


def test_training_can_stop_and_resume_with_the_same_result(tmp_path):
    ckpt = tmp_path / "ckpt.pkl"
    whole, info_whole = fit(seed=5)
    part, info = M.fit(
        table(seed=0),
        table(seed=1),
        M.GRID[0],
        seed=5,
        max_iter=60,
        step=10,
        checkpoint=ckpt,
        max_steps=2,
    )
    assert info["done"] is False and part is None
    rest, info2 = M.fit(
        table(seed=0),
        table(seed=1),
        M.GRID[0],
        seed=5,
        max_iter=60,
        step=10,
        checkpoint=ckpt,
    )
    assert info2["done"] is True
    X = table(100, seed=8).X
    assert rest is not None
    assert np.array_equal(rest.predict(X), whole.predict(X))
    assert info2["curve"] == info_whole["curve"]


def test_the_round_cap_is_1000():
    # PO, 30 Oct 2026: every full-data and v3 model stopped at the old cap of 600
    assert M.MAX_ITER == 1000
