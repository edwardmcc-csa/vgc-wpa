"""The PO, 16 Nov 2026: "If the opponents ELO is known, we should scale up/down
accordingly." Measured before any change to DEFINITIONS §7: the opponent
model's strength learned by the rating of the player choosing, per rating band
and as a line, on training games sampled band by band (most ladder games are
below the bot's target, so the higher bands are filled on purpose)."""

from __future__ import annotations

import gzip
import json

import numpy as np
import pytest

from wpa import attribution as A
from wpa import ratings as R
from wpa.choices import Action


def _log(r1, r2, extra=""):
    return f"|j|x\n|player|p1|A|1|{r1}\n|player|p2|B|2|{r2}\n{extra}|turn|1\n"


def test_each_players_rating_is_read_from_the_log():
    assert R.ratings_from_log(_log(1123, 1027)) == (1123, 1027)
    assert R.ratings_from_log(_log("", 1027)) == (None, 1027)
    assert R.ratings_from_log("|player|p1|A|1\n") == (None, None)  # not rated
    assert R.game_rating((1123, 1027)) == 1075
    assert R.game_rating((1123, None)) is None
    assert R.band(1299) == "1100 to 1299" and R.band(None) == R.UNRATED


def test_a_sample_keeps_whose_choice_it_was():
    s = A.StrengthSample([0.6, 0.4], [0.5, 0.7], 1, "p2")
    assert A.sample_from_row(A.sample_row(s)) == s
    old = A.sample_from_row([[0.6, 0.4], [0.5, 0.7], 1])  # saved before 16 Nov
    assert old.role is None and old.taken == 1


def _write_logs(tmp_path, games):
    d = tmp_path / "logs"
    d.mkdir()
    with gzip.open(d / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        for tag, log in games:
            f.write(json.dumps({"tag": tag, "log": log}) + "\n")
    return d


def _bo3(n, set_id):
    return (
        f'|uhtml|bestof|<h2><strong>Game {n}</strong> of <a href="/game-bestof3-'
        f'{set_id}">a best-of-3</a></h2>\n'
    )


def test_training_sets_are_sampled_band_by_band(tmp_path):
    t = "gen9championsvgc2026regmcbo3-"
    games = [
        (t + "1", _log(1050, 1070, _bo3(1, "s1"))),  # under 1100, a set of two
        (t + "2", _log(1060, 1080, _bo3(2, "s1"))),
        (t + "3", _log(1550, 1600, _bo3(1, "s3"))),  # 1500 and up
        (t + "4", _log(1050, "", _bo3(1, "s4"))),  # one side unrated: left out
        (t + "5", _log(1550, 1600, _bo3(1, "s5"))),  # validation: never sampled
        (t + "6", _log(1040, 1050, _bo3(1, "s6"))),
        (t + "7", _log(1560, 1600, _bo3(1, "s7"))),  # test: never read
    ]
    splits = {g: "train" for g, _ in games}
    splits[t + "5"] = "validation"
    splits[t + "7"] = "test"
    got = A.sample_by_rating(_write_logs(tmp_path, games), splits, "regmc", 2)
    under = {g for g, _ in got["under 1100"]}
    # sets in a fixed order until the band holds 2 games: set s1 (two games)
    # fills it at once; set s6 (one game) first leaves room for s1 after it
    assert under in ({t + "1", t + "2"}, {t + "1", t + "2", t + "6"})
    assert [g for g, _ in got["1500 and up"]] == [t + "3"]
    everything = {g for gs in got.values() for g, _ in gs}
    assert not {t + "4", t + "5", t + "7"} & everything


def _synthetic(n: int, strength_of, seed: int = 0):
    """Choices made by players whose strength depends on their rating."""
    rng = np.random.default_rng(seed)
    samples, ratings = [], []
    for _ in range(n):
        r = int(rng.integers(1000, 1700))
        p = rng.dirichlet(np.ones(12))
        w = [float(v) for v in rng.uniform(0.3, 0.7, 12)]
        q = A.strengthen(
            [((Action(0, "move", move=str(i)),), x) for i, x in enumerate(p)],
            w,
            strength_of(r),
        )
        k = int(rng.choice(12, p=np.array([v for _, v in q])))
        samples.append(A.StrengthSample(list(p), list(w), k, "p1"))
        ratings.append(r)
    return samples, ratings


def test_the_strength_by_band_rises_with_the_rating_when_players_do():
    samples, ratings = _synthetic(4000, lambda r: 4.0 + 3.0 * (r - 1200) / 100)
    by = A.fit_strength_by_band(samples, ratings)
    s = [
        by[b][0] for b in ("under 1100", "1100 to 1299", "1300 to 1499", "1500 and up")
    ]
    assert s == sorted(s)  # rising
    s0, slope = A.fit_strength_line(samples, ratings)
    assert s0 == pytest.approx(4.0, abs=1.0)
    assert slope == pytest.approx(3.0, abs=1.0)  # per 100 rating points


def test_no_slope_is_found_when_there_is_none():
    samples, ratings = _synthetic(3000, lambda r: 8.0, seed=1)
    s0, slope = A.fit_strength_line(samples, ratings)
    assert s0 == pytest.approx(8.0, abs=1.5)
    assert abs(slope) < 1.0


def test_the_measurement_never_overwrites_the_strength_in_use():
    a = A.parser().parse_args(["--fit-strength", "--rating-bands", "150"])
    assert a.rating_bands == 150
    with pytest.raises(SystemExit, match="strength-out"):
        A.fit_strength_run(a)  # without its own --strength-out: refused
