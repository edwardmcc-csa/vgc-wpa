"""Tests for wpa/bring.py (Week 8 Task 1): which four of six each player brought.

At each decision, the chance that each sheet Pokemon was brought. It comes from
how often its species is brought, its place on the sheet, and (in games 2 and 3
of a set) whether the player brought it last game. The four always include
everything already seen. The plan's test: at team preview it beats a uniform
guess over the 15 possible sets of four.
"""

# ruff: noqa: E501

from __future__ import annotations

import math

import pytest

from tests.test_decisions import HEAD
from wpa import bring as B


def test_who_was_brought_is_who_appeared():
    log = "\n|\n".join(
        [
            HEAD,
            "|start\n|switch|p1a: Whim|Whim, L50|100/100\n|switch|p1b: Rock|Rock, L50|100/100\n"
            "|switch|p2a: Inci|Inci, L50|100/100\n|switch|p2b: Fini|Fini, L50|100/100\n|turn|1",
            "|t:|1\n|switch|p1a: Back|Back, L50|100/100\n|turn|2",
            "|win|A",
        ]
    )
    assert B.brought_from_log(log) == {"p1": {0, 1, 2}, "p2": {0, 1}}
    assert B.players(log) == {"p1": "A", "p2": "B"}


def test_with_even_odds_each_unseen_pokemon_is_equally_likely():
    p = B.marginals([1.0] * 6, revealed=set())
    assert p == pytest.approx([4 / 6] * 6)
    p = B.marginals([1.0] * 6, revealed={0, 1})
    assert p == pytest.approx([1.0, 1.0, 0.5, 0.5, 0.5, 0.5])
    sets = B.set_chances([1.0] * 6, revealed={0, 1})
    assert len(sets) == 6 and sum(sets.values()) == pytest.approx(1.0)
    assert all({0, 1} <= s for s in sets)


def test_higher_odds_mean_more_likely_and_the_set_chances_follow_the_odds():
    odds = [9.0, 1.0, 1.0, 1.0, 1.0, 0.1]
    p = B.marginals(odds, revealed=set())
    assert p[0] > p[1] > p[5]
    assert sum(p) == pytest.approx(4.0)
    sets = B.set_chances(odds, revealed=set())
    s = frozenset({0, 1, 2, 3})
    total = sum(math.prod(odds[i] for i in t) for t in sets)
    assert sets[s] == pytest.approx(9.0 / total)


def test_a_model_learns_who_gets_brought_and_beats_the_uniform_guess():
    # species "ace" always brought, "dud" never; the rest at random
    import random

    rnd = random.Random(0)
    games = []
    for _ in range(400):
        sheet = ["ace", "dud", "x1", "x2", "x3", "x4"]
        rnd.shuffle(sheet)
        others = [i for i, s in enumerate(sheet) if s not in ("ace", "dud")]
        brought = {sheet.index("ace"), *rnd.sample(others, 3)}
        games.append(B.Example("regma", tuple(sheet), frozenset(brought), None))
    model = B.fit(games)
    p = model.marginals_for(
        "regma", ("ace", "dud", "x1", "x2", "x3", "x4"), set(), None
    )
    assert p[0] > 0.9 and p[1] < 0.1
    r = B.evaluate(model, games)
    assert r["regma"]["log_chance"] > math.log(1 / 15) + 0.5


def test_last_games_four_count_in_game_two():
    import random

    rnd = random.Random(1)
    games = []
    for _ in range(400):
        sheet = ("a", "b", "c", "d", "e", "f")
        prev = frozenset(rnd.sample(range(6), 4))
        same = rnd.random() < 0.9
        brought = prev if same else frozenset(rnd.sample(range(6), 4))
        games.append(B.Example("regma", sheet, brought, prev))
    model = B.fit(games)
    prev = frozenset({0, 1, 2, 3})
    p = model.marginals_for("regma", ("a", "b", "c", "d", "e", "f"), set(), prev)
    assert min(p[:4]) > 0.8 and max(p[4:]) < 0.3


def _game(set_id, game, p1_second):
    from tests.test_sets import bo3_log

    body = "\n|\n".join(
        [
            HEAD,
            f"|start\n|switch|p1a: Whim|Whim, L50|100/100\n|switch|p1b: {p1_second}|{p1_second}, L50|100/100\n"
            "|switch|p2a: Inci|Inci, L50|100/100\n|switch|p2b: Fini|Fini, L50|100/100\n|turn|1",
            "|t:|1\n|switch|p1a: Bench|Bench, L50|100/100\n|switch|p1b: Five|Five, L50|100/100\n"
            "|switch|p2a: Rime|Rime, L50|100/100\n|switch|p2b: Last|Last, L50|100/100\n|turn|2",
            "|win|A",
        ]
    )
    return bo3_log(set_id, game, body)


def test_examples_carry_last_games_four_by_player_within_a_set():
    t1, t2 = "gen9championsvgc2026regmabo3-1", "gen9championsvgc2026regmabo3-2"
    logs = [(t1, _game("set9", 1, "Rock")), (t2, _game("set9", 2, "Back"))]
    ex = B.examples_from_logs(logs, {t1: "train", t2: "train"})["train"]
    g1 = [e for e in ex if e.prev is None]
    g2 = [e for e in ex if e.prev is not None]
    assert len(g1) == 2 and len(g2) == 2
    p1_g2 = next(e for e in g2 if 2 in e.brought)  # Back came in this game
    assert p1_g2.brought == frozenset({0, 2, 3, 4})
    assert p1_g2.prev == frozenset({0, 1, 3, 4})  # Whim, Rock, Bench, Five last game
    assert p1_g2.leads == frozenset({0, 2})
