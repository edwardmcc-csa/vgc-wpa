"""Week 12 Task 3: the stronger opponent model, measured before DEFINITIONS §7
changes. Today each side's likely choices come from a model of what players
choose (sharpness 4), and real players choose better than it expects: their
decision averages about -2 points. The stronger model also weighs each choice by
how good it is for the one choosing, against the other side's likely choices:

    chance x exp(strength x worth), scaled back to 1.

One strength, learned on training games: the one that makes the choices players
made likeliest. For this model that is also the strength at which a player's
choice, against the model's, averages zero. Off (strength 0) unless asked for,
until the PO approves a revision of §7."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from wpa import attribution as A
from wpa.choices import Action

a, b, c, x, y = (Action(0, "move", move=m) for m in ("a", "b", "c", "x", "y"))


def test_strength_zero_leaves_the_chances_as_they_are():
    mix = [((a,), 0.5), ((b,), 0.3), ((c,), 0.2)]
    assert A.strengthen(mix, [0.9, 0.1, 0.5], 0.0) == mix


def test_a_choice_weighs_more_the_more_it_is_worth():
    mix = [((a,), 0.5), ((b,), 0.3), ((c,), 0.2)]
    worth = [0.2, 0.6, 0.6]
    out = A.strengthen(mix, worth, 10.0)
    assert sum(p for _, p in out) == pytest.approx(1.0)
    assert [j for j, _ in out] == [j for j, _ in mix]  # same choices, same order
    p = dict(out)
    assert p[(b,)] / p[(a,)] == pytest.approx(0.3 / 0.5 * math.exp(10 * 0.4))
    assert p[(b,)] / p[(c,)] == pytest.approx(0.3 / 0.2)  # equal worth: as before


def test_worth_is_against_the_other_sides_likely_choices():
    v = {(a, x): 0.6, (a, y): 0.2, (b, x): 0.9, (b, y): 0.5}

    def value(ours, theirs):
        return v[(ours[0], theirs[0])]

    mine = [((a,), 0.5), ((b,), 0.5)]
    theirs = [((x,), 0.75), ((y,), 0.25)]
    worth = A.worth(value, mine, theirs)
    assert worth == pytest.approx([0.75 * 0.6 + 0.25 * 0.2, 0.75 * 0.9 + 0.25 * 0.5])
    strong = A.strengthened(value, mine, theirs, 5.0)
    assert dict(strong)[(b,)] > dict(strong)[(a,)]


class _Values:
    """Turn values in the shape `TurnValues` gives: p1's side, and for_role."""

    def __init__(self, v):
        self.v = v

    def __call__(self, p1, p2):
        return self.v[(p1[0], p2[0])]

    def for_role(self, role):
        if role == "p1":
            return self
        return lambda ours, theirs: 1.0 - self(theirs, ours)


def test_both_sides_are_weighed_against_the_others_plain_choices():
    v = {(a, x): 0.6, (a, y): 0.2, (b, x): 0.9, (b, y): 0.5}
    tv = _Values(v)
    l1 = [((a,), 0.5), ((b,), 0.5)]
    l2 = [((x,), 0.5), ((y,), 0.5)]
    strong = A.strong_mixes(tv, {"p1": l1, "p2": l2}, 8.0)
    # p1: b is better against x and y; p2: y is better (worse for p1)
    assert dict(strong["p1"])[(b,)] > 0.5
    assert dict(strong["p2"])[(y,)] > 0.5
    assert strong["p2"] == A.strengthened(tv.for_role("p2"), l2, l1, 8.0)
    assert A.strong_mixes(tv, {"p1": l1, "p2": l2}, 0.0) == {"p1": l1, "p2": l2}


def _samples(strength, n=4000, seed=3):
    """Choices drawn from the stronger model with a known strength."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        k = int(rng.integers(2, 8))
        p = rng.dirichlet(np.ones(k))
        w = rng.uniform(0.2, 0.8, k)
        q = p * np.exp(strength * (w - w.max()))
        q /= q.sum()
        out.append(A.StrengthSample(list(p), list(w), int(rng.choice(k, p=q))))
    return out


def test_the_learned_strength_makes_the_choices_made_likeliest():
    samples = _samples(12.0)
    s, curve = A.fit_strength(samples)
    assert s == pytest.approx(12.0, rel=0.15)
    # at that strength the choice made is, on average, worth what the model expects
    assert abs(A.mean_choice(samples, s)) < 1e-4
    assert A.mean_choice(samples, 0.0) > 0  # the plain model expects too little
    assert curve and all(len(t) == 2 for t in curve)
    # the likelihood is highest there
    ll = [A.log_likelihood(samples, t) for t in (0.5 * s, s, 1.5 * s)]
    assert ll[1] > ll[0] and ll[1] > ll[2]


def test_a_choice_outside_the_candidates_is_left_out_of_the_fit():
    samples = _samples(6.0, n=1500) + [A.StrengthSample([0.5, 0.5], [0.1, 0.9], -1)]
    s, _ = A.fit_strength(samples)
    assert s == pytest.approx(A.fit_strength(samples[:-1])[0])


def test_no_strength_when_players_choose_no_better_than_the_plain_model():
    rng = random.Random(1)
    samples = []
    for _ in range(500):
        w = [rng.random() for _ in range(3)]
        samples.append(A.StrengthSample([1 / 3] * 3, w, w.index(min(w))))
    s, _ = A.fit_strength(samples)
    assert s == 0.0


def test_the_strength_is_a_number_or_the_fitted_one(tmp_path):
    import argparse
    import json

    policy = tmp_path / "policy.json"
    (tmp_path / "strength.json").write_text(json.dumps({"strength": 17.5}))
    assert A.strength_value(argparse.Namespace(strength="0", policy=policy)) == 0.0
    assert A.strength_value(argparse.Namespace(strength="12", policy=policy)) == 12.0
    assert (
        A.strength_value(argparse.Namespace(strength="fitted", policy=policy)) == 17.5
    )
    assert A.strength_value(argparse.Namespace(policy=policy)) == 0.0  # replay's


def _measured(choice, theirs):
    return {
        "choice": choice,
        "position": 0.0,
        "theirs": theirs,
        "dice": 0.0,
        "vs_best": None,
    }


def test_the_summary_shows_each_measured_strength(tmp_path):
    import json

    recs = []
    for i, (c0, t0, c1, t1) in enumerate(
        [(0.04, -0.04, 0.01, -0.01), (0.02, -0.02, 0.0, 0.0)]
    ):
        sw = 0.1
        recs.append(
            {
                "tag": f"g{i}",
                "format": "regma",
                "turn": 1,
                "kind": "turn",
                "role": "p1",
                "before": 0.5,
                "after": 0.5 + sw,
                "yours": sw,
                "choice": sw,
                "position": 0.0,
                "theirs": 0.0,
                "dice": 0.0,
                "vs_best": None,
                "vs_average": None,
                "kept": 1.0,
                "unknown": 0,
                "found": True,
                "partial": [],
                "seconds": 1.0,
                "at_strength": {"0": _measured(c0, t0), "20": _measured(c1, t1)},
            }
        )
    path = tmp_path / "a.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    text = A.report(path)
    assert "opponent model's strength" in text
    line0 = next(x for x in text.splitlines() if x.strip().startswith("strength 0:"))
    line20 = next(x for x in text.splitlines() if x.strip().startswith("strength 20:"))
    assert "their decision mean -3.0" in line0 and "their decision mean -0.5" in line20
    assert "your choice mean +3.0" in line0


def test_the_strengths_to_measure_may_name_the_fitted_one(tmp_path):
    import argparse
    import json

    policy = tmp_path / "policy.json"
    (tmp_path / "strength.json").write_text(json.dumps({"strength": 17.5}))
    a = argparse.Namespace(measure_strengths=["0", "fitted", "40"], policy=policy)
    assert A.measure_values(a) == (0.0, 17.5, 40.0)
    assert A.measure_values(argparse.Namespace(policy=policy)) == ()


def test_fitted_before_the_fit_says_what_to_run(tmp_path):
    import argparse

    a = argparse.Namespace(strength="fitted", policy=tmp_path / "policy.json")
    with pytest.raises(SystemExit, match="--fit-strength"):
        A.strength_value(a)


def test_the_run_stops_before_it_starts_without_the_fitted_strength(
    tmp_path, monkeypatch
):
    """Checked before the workers start: a worker that stops as it starts is
    started again, over and over."""
    import sys

    def started(_a):
        raise AssertionError("the run started")

    monkeypatch.setattr(A, "run", started)
    argv = ["attribution", "--policy", str(tmp_path / "policy.json")]
    monkeypatch.setattr(sys, "argv", [*argv, "--measure-strengths", "0", "fitted"])
    with pytest.raises(SystemExit, match="--fit-strength"):
        A.main()


def test_a_learned_strength_shows_rounded():
    m = _measured(0.01, -0.01)
    lines = A._strength_lines([{"at_strength": {"0": m, "6.87554": m}}])
    assert lines[1].startswith("    strength 0: ")
    assert lines[2].startswith("    strength 6.88: ")
