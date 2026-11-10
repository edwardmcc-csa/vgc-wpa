"""Tests for wpa/replace_model.py (Week 10 Task 6): the chance of each Pokemon a
player sends in after a faint, learned from the training split.

Each Pokemon that could come in gets a score from what the opponent sees of it:
its hit points (full if unseen), whether it is unseen and how likely it was
brought, how hard it hits the opposing Pokemon and they hit it, and Fake Out
or Intimidate on its sheet. Its chance is its share of the exponentiated
scores. Nothing from later in the game is used.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from tests.test_forced import END2, KO, QUIET, REPLACE, UPKEEP, game
from wpa import choices as C
from wpa import replace_model as M
from wpa.team_sheets import SheetMon

LOG = game(KO, UPKEEP, REPLACE, QUIET, END2)


def _sheet():
    return [
        SheetMon(1, "inci", "", "intimidate", ("fakeout", "flareblitz"), ""),
        SheetMon(2, "fini", "", "mistysurge", ("moonblast",), ""),
        SheetMon(3, "rime", "", "pressure", ("protect",), ""),
        SheetMon(4, "last", "", "intimidate", ("fakeout",), ""),
    ]


def test_each_pokemon_that_could_come_in_has_what_the_opponent_sees_of_it():
    (r,) = C.replacements(LOG)
    r.ours[2]["hp_fraction"] = 0.4  # Rime was seen at 40%
    bring = [0.9, 0.9, 0.5, 0.8, 0.2, 0.2]
    f = dict(zip(M.FEATURES, M.option_features(r, 2, _sheet(), None, bring)))
    assert f["hp"] == 0.4 and f["unseen"] == 0.0 and f["bring"] == 0.0
    f = dict(zip(M.FEATURES, M.option_features(r, 3, _sheet(), None, bring)))
    assert f["hp"] == 1.0 and f["unseen"] == 1.0
    assert f["bring"] == pytest.approx(math.log(0.8 / 0.2))
    assert f["fakeout"] == 1.0 and f["intimidate"] == 1.0
    assert f["best_dmg"] == 0.0 and f["threat"] == 0.0  # no calculator here


def test_the_chances_add_up_to_one_and_follow_the_weights():
    w = [0.0] * len(M.FEATURES)
    w[M.FEATURES.index("intimidate")] = 3.0
    model = M.ReplaceModel(w)
    X = np.zeros((3, len(M.FEATURES)))
    X[1, M.FEATURES.index("intimidate")] = 1.0
    p = model.chances(X)
    assert p.sum() == pytest.approx(1.0) and int(np.argmax(p)) == 1


def test_the_log_gives_one_example_per_slot_filled():
    from tests.test_resolver import ROOT
    from wpa.team_sheets import load_dexes

    if not (ROOT / "pokemon-showdown" / "dist").exists():
        pytest.skip("needs the pinned Showdown build")
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    from tests.test_decisions import EMPTY

    ex = M.examples_for_game("t", LOG, "regma", dex, EMPTY, None, None, None)
    (X, c) = ex[0]
    assert len(ex) == 1 and X.shape == (4, len(M.FEATURES))
    assert c == 1  # Last, the second of Rime, Last, Five, Six
    # cutting the game after the forced switch changes nothing
    cut = LOG[: LOG.index("|turn|2")] + "|turn|2\n|\n|win|A"
    (X2, c2) = M.examples_for_game("t", cut, "regma", dex, EMPTY, None, None, None)[0]
    assert c2 == c and np.allclose(X2, X)


def test_fitting_finds_a_preference_and_beats_a_uniform_guess():
    rng = random.Random(3)
    k = len(M.FEATURES)
    hp = M.FEATURES.index("hp")
    groups = []
    for _ in range(400):
        X = np.zeros((4, k))
        X[:, hp] = [rng.random() for _ in range(4)]
        z = 4 * X[:, hp]
        p = np.exp(z) / np.exp(z).sum()
        groups.append((X, int(rng.choices(range(4), weights=p)[0])))
    model = M.fit(groups)
    assert model.weights[hp] > 2.0
    ll, un = M.score(model, groups)
    assert ll > un
