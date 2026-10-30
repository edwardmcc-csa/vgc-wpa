"""The gradient-boosting library, behind one door (Week 5 Task 2).

scikit-learn's `HistGradientBoostingClassifier` is the chosen library. It is an
optional extra (`pip install -e ".[model]"`), pinned in pyproject.toml, so the
rest of the project installs and runs without it. Everything that needs it goes
through `make_classifier`, which gives a plain error message when it is missing.

Two settings matter for the rest of Week 5:

* `early_stopping=False`. The library's own early stopping holds out a random
  slice of the *training rows*, and rows from one game are not independent. The
  number of rounds is chosen on the validation split instead (Task 6).
* A fixed `random_state`. Training is deterministic for a given seed (tested).
"""

from __future__ import annotations

INSTALL_HINT = 'The model library is not installed. Run: pip install -e ".[model]"'

DEFAULTS = {
    "learning_rate": 0.1,
    "max_iter": 200,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 100,
    "l2_regularization": 1.0,
}


def make_classifier(seed: int, **params):
    """A gradient-boosted classifier, unfitted, with early stopping off."""
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
    except ImportError as err:
        raise ImportError(INSTALL_HINT) from err
    settings = {**DEFAULTS, **params}
    # scikit-learn annotates early_stopping as str (its default is "auto") but
    # documents False as valid, so the checker is told to look away on this line.
    return HistGradientBoostingClassifier(
        early_stopping=False,  # pyright: ignore[reportArgumentType]
        random_state=seed,
        **settings,
    )
