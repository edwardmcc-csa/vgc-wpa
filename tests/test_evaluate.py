"""Tests for wpa/evaluate.py (Week 5 Task 7): evaluation, ablation and the gate.

The gate's own tests run on tiny synthetic tables, so CI never needs the data.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from wpa import evaluate as E
from wpa import features as F
from wpa.baseline import predict as v0_predict
from wpa.durations import Durations
from wpa.metrics import state_from_dict
from wpa.team_sheets import Dex, sheets_from_log
from wpa.timer_join import align
from wpa.timers import track_decisions

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
LOGS = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
EMPTY = Durations("e", timed={})
DEX = Dex(species={}, moves={}, items={})


def fixture_rows(groups="ABCDE"):
    rows, states_by_row = [], []
    for tag in sorted(LOGS):
        for role in ("p1", "p2"):
            states = json.loads(
                (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
            )
            joined = align(states, track_decisions(LOGS[tag], EMPTY)[role], role)
            got = F.rows_for_file(
                tag,
                role,
                states,
                joined,
                sheets_from_log(LOGS[tag]),
                DEX,
                EMPTY,
                groups,
            )
            rows += got
            states_by_row += states[: len(got)]
    return rows, states_by_row


def to_table(rows, groups="ABCDE"):
    cols = F.columns(groups)
    return F.Table(
        np.array([r.values for r in rows], dtype=np.float32),
        np.array([r.label for r in rows], dtype=np.int8),
        np.array([r.tag for r in rows]),
        np.array([r.role for r in rows]),
        np.array([r.unit for r in rows]),
        np.array([r.turn for r in rows], dtype=np.int16),
        cols,
    )


def test_v0_from_the_table_equals_the_v0_baseline_on_the_states():
    rows, states = fixture_rows()
    table = to_table(rows)
    got = E.v0_from_table(table)
    want = [v0_predict(state_from_dict({**s, "outcome": None})) for s in states]
    assert np.allclose(got, want)


def test_selecting_groups_keeps_their_columns_in_order():
    rows, _ = fixture_rows()
    t = E.select(to_table(rows), "AC")
    assert t.columns == F.columns("AC")
    assert t.X.shape[1] == len(F.columns("AC"))


def synthetic(n_units=2000, rows_per=5, seed=0):
    """Calibrated "good" predictions (the true chance per unit) and a coin flip."""
    rng = np.random.default_rng(seed)
    units = np.repeat([f"u{i}" for i in range(n_units)], rows_per)
    chance = np.repeat(rng.uniform(0.05, 0.95, n_units), rows_per)
    y = (rng.random(len(chance)) < chance).astype(np.int8)
    return units, y, chance, np.full(len(y), 0.5)


def test_unit_bootstrap_gives_an_interval_around_the_brier():
    units, y, p, _ = synthetic()
    b, lo, hi = E.brier_ci(p, y, units, draws=200, seed=1)
    assert lo <= b <= hi
    assert hi - lo < 0.05


def test_paired_difference_interval_excludes_zero_when_one_model_is_clearly_better():
    units, y, good, bad = synthetic()
    d, lo, hi = E.difference_ci(good, bad, y, units, draws=200, seed=1)
    assert d < 0 and hi < 0


def test_the_gate_passes_a_good_model_and_names_what_fails():
    units, y, good, bad = synthetic()
    ok = E.gate_failures({"regma": E.score(good, y, units, bad)})
    assert ok == []
    bad_fails = E.gate_failures({"regma": E.score(bad, y, units, good)})
    assert any("v0" in f for f in bad_fails)
    assert any("0.25" in f for f in bad_fails)


def test_the_gate_flags_a_calibration_bin_outside_the_tolerance():
    units, y, good, _ = synthetic()
    skewed = np.clip(good + 0.2, 0, 1)
    fails = E.gate_failures({"regma": E.score(skewed, y, units, np.full(len(y), 0.5))})
    assert any("calibration" in f for f in fails)


def test_opening_the_test_split_is_recorded_and_counted(tmp_path):
    log = tmp_path / "test_openings.json"
    assert E.record_test_opening(log, {"note": "first"}) == 1
    assert E.record_test_opening(log, {"note": "again"}) == 2
    records = json.loads(log.read_text(encoding="utf-8"))
    assert [r["note"] for r in records] == ["first", "again"]
    assert all("date" in r and "commit" in r for r in records)


def test_unit_sampling_keeps_whole_units():
    units = np.array(["a", "a", "b", "b", "c", "c", "d"] * 50)
    keep = E.sample_units(units, 0.5, seed="s")
    for u in set(units):
        assert len(set(keep[units == u])) == 1


def test_a_format_flag_column_is_added_and_never_mirrored():
    from wpa.features import mirror_permutation

    rows, _ = fixture_rows()
    t = E.with_format_flag(to_table(rows), 1.0)
    assert t.columns[-1] == "z_format_regmb"
    assert set(t.X[:, -1]) == {1.0}
    perm = mirror_permutation(t.columns)
    assert perm[-1] == len(t.columns) - 1


def _write_split(root, fmt, split, rows):
    d = root / fmt / split
    d.mkdir(parents=True)
    F.write_rows(d / "part-000.npz", rows, F.columns("ABCDE"))


def test_the_pooled_v2_model_trains_on_both_formats_and_is_judged_on_reg_mb(tmp_path):
    from argparse import Namespace

    rows, _ = fixture_rows()
    ma, mb = rows[: len(rows) // 2], rows[len(rows) // 2 :]
    for split in ("train", "validation"):
        _write_split(tmp_path, "regma", split, ma)
        _write_split(tmp_path, "regmb", split, mb)
    pooled = Namespace(format="pooled", features=tmp_path, sample=1.0)

    train = E._v2_tables(pooled, "A", "train")
    assert train.columns == [*F.columns("A"), "z_format_regmb"]
    assert list(train.X[:, -1]) == [0.0] * len(ma) + [1.0] * len(mb)

    val = E._v2_tables(pooled, "A", "validation")
    assert len(val.y) == len(mb)
    assert set(val.X[:, -1]) == {1.0}

    regma = Namespace(format="regma", features=tmp_path, sample=0.01)
    val = E._v2_tables(regma, "A", "validation")
    assert val.columns == F.columns("A")
    assert len(val.y) == len(ma)  # the sample applies to training only


def test_selecting_every_column_in_order_keeps_the_same_array():
    rows, _ = fixture_rows()
    t = to_table(rows)
    assert E.select(t, "ABCDE").X is t.X  # no copy of a large table


def test_training_converts_the_table_to_float64_once(tmp_path):
    # sklearn converts to float64 on every warm-start step; converting once up
    # front avoids holding a float32 and a float64 copy of the whole table
    rows, _ = fixture_rows()
    t, v = to_table(rows), to_table(rows)
    params = {
        "learning_rate": 0.1,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 5,
        "l2_regularization": 0.0,
    }
    E._train_until(t, v, params, tmp_path / "c.ckpt", 0)
    assert t.X.dtype == np.float64


def test_the_report_compares_with_the_model_one_group_smaller():
    assert E._base_groups("ABCDEF", None) == "ABCDE"
    assert E._base_groups("ABCDEFG", None) == "ABCDEF"
    assert E._base_groups("ABCDEFG", "ABCDE") == "ABCDE"
    assert E._group_names("ABCDEFG", "ABCDEF") == "damage (G)"
    assert E._group_names("ABCDEF", "ABCDE") == "speed (F)"


def test_reg_mb_is_never_recalibrated():
    # PO, 30 Oct 2026: recalibrating on Reg M-B's few validation sets overshot on test
    assert E.use_recalibration("regma")
    assert not E.use_recalibration("regmb")
