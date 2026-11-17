"""Reg M-C's test split, opened once with the PO's approval (16 Nov 2026), for
Phase 2's final numbers: every model in use for the format, scored with the
gate's own checks. Nothing is fitted or tuned on it; each opening is logged."""

from __future__ import annotations

import json

import numpy as np
import pytest

from wpa import final_test as F


def test_it_will_not_open_the_test_split_without_the_pos_approval():
    with pytest.raises(SystemExit):
        F.parser().parse_args(["--format", "regmc"])
    a = F.parser().parse_args(["--format", "regmc", "--po-approved", "16 Nov 2026"])
    assert a.po_approved == "16 Nov 2026"


def test_each_opening_is_logged_with_what_was_scored_and_the_approval(tmp_path):
    path = tmp_path / "test_openings.json"
    path.write_text(json.dumps([{"formats": ["regma", "regmb"]}] * 5), encoding="utf-8")
    n = F.log_opening(path, "regmc", "16 Nov 2026", ["models_v4_avg ABCDEFGHIJ"])
    assert n == 6  # the sixth opening
    last = json.loads(path.read_text(encoding="utf-8"))[-1]
    assert last["formats"] == ["regmc"]
    assert last["approved"] == "PO, 16 Nov 2026"
    assert "models_v4_avg ABCDEFGHIJ" in last["model"]


class _Fixed:
    """A model whose chances are given: the first option twice as likely."""

    def chances(self, X):
        p = np.ones(len(X))
        p[0] = 2.0
        return p / p.sum()


def test_a_choice_model_is_scored_against_a_uniform_guess():
    groups = [(np.zeros((3, 2)), 0), (np.zeros((3, 2)), 2)]
    got = F.choice_scores(_Fixed().chances, groups)
    assert got["choices"] == 2
    assert got["model"] == pytest.approx((np.log(0.5) + np.log(0.25)) / 2)
    assert got["uniform"] == pytest.approx(np.log(1 / 3))
    assert got["top"] == pytest.approx(0.5)  # the likeliest was right once
    assert got["beats"] == (got["model"] > got["uniform"])


def test_a_choice_with_one_option_is_left_out():
    """Nothing to choose: as the forced-switch model's own report."""
    groups = [(np.zeros((1, 2)), 0), (np.zeros((3, 2)), 0)]
    assert F.choice_scores(_Fixed().chances, groups)["choices"] == 1


def test_a_trial_on_validation_opens_nothing_and_logs_nothing(tmp_path, monkeypatch):
    """`--try-on-validation` tries the command itself on the validation split."""
    path = tmp_path / "test_openings.json"
    a = F.parser().parse_args(
        [
            "--format",
            "regmc",
            "--po-approved",
            "x",
            "--try-on-validation",
            "--openings",
            str(path),
            "--features",
            str(tmp_path / "none"),
        ]
    )
    seen = []

    def load_table(features, fmt, split, sample=1.0):
        seen.append(split)
        raise LookupError("stop here")

    import wpa.evaluate as EV

    monkeypatch.setattr(EV, "load_table", load_table)
    with pytest.raises(LookupError):
        F.run(a)
    assert seen == ["validation"] and not path.exists()
