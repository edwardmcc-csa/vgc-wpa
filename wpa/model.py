"""The v1 win probability model (Week 5 Task 6).

One gradient-boosted classifier per format, trained on that format's train
split only (`wpa/gbm.py` for the library). Three rules from the brief:

* **The number of boosting rounds is chosen on the validation split**, never on
  training rows or the test split. Training grows the model in steps
  (`warm_start`) and keeps the copy with the best validation Brier.
* **Symmetric by construction.** The model scores a position from both sides
  and averages: p = (f(x) + 1 - f(mirror(x))) / 2. A mirrored position gets
  exactly 0.5 and the two players' predictions sum to 1. A side with no Pokemon
  left has lost (0.0), the other has won (1.0).
* **One-sided, where the two sides know different things** (Week 8: our sheet
  whole, the opponent's blanked). The mirrored row is then unlike any real row,
  so the average is pulled off. Such a model scores the row as it is: p = f(x).
* **The hyperparameter grid below was written down before any result.** The
  validation split picks one setting per format.

A model is saved with its exact feature list; loading it against a different
list is refused.
"""

from __future__ import annotations

import copy
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from wpa.features import Table, mirror_permutation
from wpa.gbm import make_classifier

# Fixed before any result (Week 5 Task 6). min_samples_leaf is large because
# rows from one game are not independent.
GRID: list[dict[str, Any]] = [
    {
        "learning_rate": 0.1,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 200,
        "l2_regularization": 1.0,
    },
    {
        "learning_rate": 0.1,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 200,
        "l2_regularization": 1.0,
    },
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 200,
        "l2_regularization": 1.0,
    },
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 200,
        "l2_regularization": 1.0,
    },
]
MAX_ITER = 1000  # PO, 30 Oct 2026 (was 600: every full-data and v3 model hit it)
STEP = 25
PATIENCE = 3  # steps without improvement before stopping


class SymmetricModel:
    def __init__(
        self,
        clf,
        columns: list[str],
        n_iter: int,
        params: dict,
        one_sided: bool = False,
    ) -> None:
        self.clf = clf
        self.one_sided = one_sided
        self.columns = list(columns)
        self.mirror = np.array(mirror_permutation(columns))
        self.n_iter = n_iter
        self.params = dict(params)
        self.calibration: tuple[np.ndarray, np.ndarray] | None = None
        self._our = (
            columns.index("a_our_remaining") if "a_our_remaining" in columns else None
        )
        self._their = (
            columns.index("a_their_remaining")
            if "a_their_remaining" in columns
            else None
        )

    def is_one_sided(self) -> bool:
        # models saved before one-sided models existed have no such attribute
        return bool(getattr(self, "one_sided", False))

    def raw(self, X: np.ndarray) -> np.ndarray:
        """The symmetric average (or, one-sided, the row's own score), before
        recalibration and the wiped-side rule."""
        f = self.clf.predict_proba(X)[:, 1]
        if self.is_one_sided():
            return f
        g = self.clf.predict_proba(X[:, self.mirror])[:, 1]
        return (f + 1.0 - g) / 2.0

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        p = self.raw(X)
        if self.calibration is not None:
            xs, ys = self.calibration

            def h(q: np.ndarray) -> np.ndarray:
                return np.interp(q, xs, ys)

            p = h(p) if self.is_one_sided() else (h(p) + 1.0 - h(1.0 - p)) / 2.0
        if self._our is not None and self._their is not None:
            p = np.where(X[:, self._their] <= 0, 1.0, p)
            p = np.where(X[:, self._our] <= 0, 0.0, p)
        return p


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def fit(
    train: Table,
    val: Table,
    params: dict,
    seed: int = 0,
    max_iter: int = MAX_ITER,
    step: int = STEP,
    patience: int = PATIENCE,
    checkpoint: Path | str | None = None,
    max_steps: int | None = None,
    one_sided: bool = False,
) -> tuple[SymmetricModel | None, dict]:
    """Train on `train`, stopping on `val`'s symmetric Brier. Returns the best.

    With `checkpoint`, progress is saved after every step and a later call with
    the same arguments carries on from it, giving the same result as one
    uninterrupted run. `max_steps` limits the steps taken in this call; if the
    run is not finished the model returned is None and info["done"] is False.
    `one_sided`: the model scores each row as it is (no mirror average), and its
    rounds are chosen on that score.
    """
    if train.columns != val.columns:
        raise ValueError("train and validation have different feature columns")
    state = None
    if checkpoint is not None and Path(checkpoint).exists():
        with open(checkpoint, "rb") as f:
            state = pickle.load(f)
        if (
            state["params"] != params
            or state["seed"] != seed
            or state.get("one_sided", False) != one_sided
        ):
            raise ValueError("checkpoint is from a different run; delete it to restart")
    if state is None:
        state = {
            "clf": make_classifier(seed, max_iter=step, warm_start=True, **params),
            "best_clf": None,
            "best_n": 0,
            "best_brier": float("inf"),
            "curve": [],
            "since": 0,
            "n": 0,
            "done": False,
            "params": params,
            "seed": seed,
            "one_sided": one_sided,
        }
    clf = state["clf"]
    yv = val.y.astype(np.float64)
    taken = 0
    while not state["done"]:
        if max_steps is not None and taken >= max_steps:
            break
        state["n"] = min(max_iter, state["n"] + step)
        clf.set_params(max_iter=state["n"])
        clf.fit(train.X, train.y)
        b = _brier(
            SymmetricModel(clf, train.columns, state["n"], params, one_sided).predict(
                val.X
            ),
            yv,
        )
        state["curve"].append((state["n"], b))
        taken += 1
        if b < state["best_brier"] - 1e-6:
            state["best_brier"] = b
            state["best_clf"] = copy.deepcopy(clf)
            state["best_n"] = state["n"]
            state["since"] = 0
        else:
            state["since"] += 1
        if state["since"] >= patience or state["n"] >= max_iter:
            state["done"] = True
        if checkpoint is not None:
            # write then rename, so a run stopped mid-write never leaves a
            # broken checkpoint behind
            ck = Path(checkpoint)
            ck.parent.mkdir(parents=True, exist_ok=True)
            tmp = ck.with_suffix(ck.suffix + ".tmp")
            with open(tmp, "wb") as f:
                pickle.dump(state, f)
            tmp.replace(ck)
    info = {
        "curve": state["curve"],
        "best_validation_brier": state["best_brier"],
        "params": params,
        "done": state["done"],
        "n_iter": state["best_n"],
    }
    if not state["done"]:
        return None, info
    best = SymmetricModel(
        state["best_clf"], train.columns, state["best_n"], params, one_sided
    )
    return best, info


def recalibrate(model: SymmetricModel, val: Table) -> SymmetricModel:
    """Fit a monotone map on the validation split, kept symmetric (unless the
    model is one-sided)."""
    from sklearn.isotonic import IsotonicRegression

    p = model.raw(np.asarray(val.X, dtype=np.float32))
    if model.is_one_sided():
        xs, ys = p, val.y.astype(np.float64)
    else:
        # fit on both sides of every row so the map is symmetric about 0.5
        xs = np.concatenate([p, 1.0 - p])
        ys = np.concatenate([val.y, 1 - val.y]).astype(np.float64)
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(xs, ys)
    grid = np.linspace(0.0, 1.0, 1001)
    out = copy.copy(model)
    out.calibration = (grid, iso.predict(grid))
    return out


def save(model: SymmetricModel, path: Path | str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load(path: Path | str, columns: list[str]) -> SymmetricModel:
    with open(path, "rb") as f:
        model = pickle.load(f)
    if list(columns) != model.columns:
        raise ValueError(
            "the feature columns differ from those the model was trained on; "
            "rebuild the feature table or retrain"
        )
    return model
