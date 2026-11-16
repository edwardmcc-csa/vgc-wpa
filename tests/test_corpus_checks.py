"""Week 15 Task 4: two checks on the Reg M-C corpus. Do the few accounts that
play a lot change the models (trained without their games, against dropping as
many sets at random)? And how do the models score by the rating a game shows?"""

from __future__ import annotations

import json

import numpy as np
import pytest

from wpa import corpus_checks as K
from wpa.features import Table


def _log(r1, r2):
    return f"|j|x\n|player|p1|A|1|{r1}\n|player|p2|B|2|{r2}\n|turn|1\n"


def _games(tmp_path):
    rows = [
        {
            "id": "g1",
            "rating": 1073,
            "players": ["Ash K", "misty"],
            "log": _log(1123, 1027),
        },
        {"id": "g2", "rating": 0, "players": ["ASH-K", "Brock"], "log": _log("", "")},
        {
            "id": "g3",
            "rating": None,
            "players": ["ashk", "Misty"],
            "log": _log(1210, ""),
        },
        {
            "id": "g4",
            "rating": 1520,
            "players": ["gary", "brock"],
            "log": _log(1530, 1490),
        },
    ]
    p = tmp_path / "logs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return K.read_games(p)


def test_each_games_players_and_ratings_are_read(tmp_path):
    g = _games(tmp_path)
    assert g["g1"] == K.Game(("ashk", "misty"), (1123, 1027))
    assert g["g3"].players == ("ashk", "misty")  # the same account, however written
    # each player's own rating, from the log's player lines (the replay page's
    # one number is shown on far fewer games)
    assert g["g2"].ratings == (None, None)
    assert g["g3"].ratings == (1210, None)


def test_a_games_rating_is_its_two_players_average_when_both_are_shown(tmp_path):
    g = _games(tmp_path)
    assert K.game_rating(g["g1"]) == 1075
    assert K.game_rating(g["g3"]) is None  # one side only: not banded
    assert K.ratings_from_log(_log(1500, 1400)) == (1500, 1400)


def test_the_busiest_accounts_are_counted_on_the_games_given(tmp_path):
    g = _games(tmp_path)
    assert K.busiest(g, ["g1", "g2", "g3", "g4"], 2) == [("ashk", 3), ("brock", 2)]
    # training games only: a game outside them does not count
    assert K.busiest(g, ["g4"], 1) == [("brock", 1)]
    assert K.with_players(g, ["ashk"]) == {"g1", "g2", "g3"}


@pytest.mark.parametrize(
    "rating, name",
    [
        (None, "no rating shown"),
        (1099, "under 1100"),
        (1100, "1100 to 1299"),
        (1499, "1300 to 1499"),
        (1500, "1500 and up"),
    ],
)
def test_a_games_rating_band(rating, name):
    assert K.band(rating) == name


def _table():
    tags = np.array(["g1", "g1", "g2", "g3", "g3", "g4"])
    units = np.array(["s1", "s1", "s1", "s2", "s2", "s3"])
    n = len(tags)
    return Table(
        np.arange(n, dtype=np.float32).reshape(n, 1),
        np.array([1, 0, 1, 0, 1, 1], dtype=np.int8),
        tags,
        np.array(["p1"] * n),
        units,
        np.zeros(n, dtype=np.int16),
        ["x"],
    )


def test_a_dropped_game_takes_its_whole_set_with_it():
    t = _table()
    units = K.units_with(t, {"g2"})
    assert list(units) == ["s1"]  # g1 is in the same set: both go
    kept = K.drop_units(t, units)
    assert list(kept.tag) == ["g3", "g3", "g4"]


def test_the_control_drops_as_many_sets_at_random_and_the_same_each_time():
    units = np.array([f"s{i}" for i in range(100)])
    a = K.control_units(units, 10, seed=1)
    assert len(a) == 10 and len(set(a)) == 10 and set(a) <= set(units)
    assert list(a) == list(K.control_units(units, 10, seed=1))
    assert list(a) != list(K.control_units(units, 10, seed=2))
    assert len(K.control_units(units[:3], 10, seed=1)) == 3  # never more than there are


def test_a_mean_and_a_paired_difference_with_intervals_by_game():
    vals = np.array([1.0, 1.0, 3.0, 3.0])
    games = np.array(["a", "a", "b", "b"])
    m, lo, hi = K.mean_ci(vals, games, draws=200)
    assert m == pytest.approx(2.0) and lo <= m <= hi
    assert 1.0 <= lo and hi <= 3.0
    d, dlo, dhi = K.paired_ci(vals + 0.5, vals, games, draws=200)
    assert d == pytest.approx(0.5) and dlo == pytest.approx(0.5)
    assert dhi == pytest.approx(0.5)


def test_the_verdict_names_a_change_only_beyond_the_noise():
    assert K.verdict((0.0004, -0.0002, 0.0010)) == "no change beyond the noise"
    assert K.verdict((0.0030, 0.0010, 0.0050)) == "worse without them"
    assert K.verdict((-0.0030, -0.0050, -0.0010)) == "better without them"
    # for the log chance, higher is better
    assert K.verdict((0.02, 0.01, 0.03), higher_is_better=True) == "better without them"


def test_bands_come_in_order_with_the_unrated_last():
    got = K.ordered_bands(["1500 and up", "no rating shown", "under 1100"])
    assert got == ["under 1100", "1500 and up", "no rating shown"]
