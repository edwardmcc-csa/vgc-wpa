"""Tests for wpa/gbm.py (Week 5 Task 2): the gradient-boosting library.

The model library (scikit-learn) is an optional extra, `pip install -e ".[model]"`.
Tests that need it are skipped where it is not installed; the missing-library
message is tested either way.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

from wpa import gbm

ROOT = Path(__file__).resolve().parent.parent


def synthetic(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 5))
    p = 1 / (1 + np.exp(-(1.5 * x[:, 0] - 1.0 * x[:, 1])))
    y = rng.random(n) < p
    return x, y


def test_a_missing_library_gives_an_instruction_not_a_traceback(monkeypatch):
    monkeypatch.setitem(sys.modules, "sklearn", None)
    monkeypatch.setitem(sys.modules, "sklearn.ensemble", None)
    with pytest.raises(ImportError) as err:
        gbm.make_classifier(seed=1)
    assert 'pip install -e ".[model]"' in str(err.value)


def test_the_extra_pins_scikit_learn_exactly():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'model\s*=\s*\[\s*"scikit-learn==\d+\.\d+\.\d+', text)


def test_ci_installs_the_extra_where_the_model_code_is_checked_or_tested():
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert text.count('pip install -e ".[dev,model]"') >= 2


@pytest.mark.skipif(sys.version_info < (3, 11), reason="the pin needs Python 3.11+")
def test_the_installed_version_is_the_pinned_one():
    sklearn = pytest.importorskip("sklearn")
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pinned = re.search(r'"scikit-learn==([\d.]+)', text)
    assert pinned is not None
    assert sklearn.__version__ == pinned.group(1)


def test_two_fits_with_the_same_seed_give_identical_predictions():
    pytest.importorskip("sklearn")
    x, y = synthetic()
    a = gbm.make_classifier(seed=7).fit(x, y).predict_proba(x)[:, 1]
    b = gbm.make_classifier(seed=7).fit(x, y).predict_proba(x)[:, 1]
    assert np.array_equal(a, b)


def test_the_classifier_learns_a_signal_and_does_not_stop_early_on_its_own():
    pytest.importorskip("sklearn")
    x, y = synthetic()
    clf = gbm.make_classifier(seed=7, max_iter=60).fit(x[:1500], y[:1500])
    # validation, not an internal split, chooses the number of rounds (Task 6)
    assert clf.n_iter_ == 60
    p = clf.predict_proba(x[1500:])[:, 1]
    brier = float(np.mean((p - y[1500:]) ** 2))
    assert brier < 0.20  # a coin flip scores 0.25
