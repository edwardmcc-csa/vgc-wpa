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


# --------------------------------------------------------------------------
# DEFINITIONS revision 15 (PO, 17 Nov 2026): the strength for a player's
# choices follows that player's rating where the log shows it
# --------------------------------------------------------------------------

LINE = {"s0": 8.7, "slope": 0.32, "center": 1200}


def _tools(**kw) -> A.Tools:
    base: dict = dict(
        dexes={},
        tables={},
        moves={},
        calc=None,
        store=None,
        bring=None,
        policy=None,
        predict={},
    )
    base.update(kw)
    return A.Tools(**base)


def test_the_strength_follows_the_rating_held_within_1000_to_1700():
    t = _tools(strength=9.6, rating_line=LINE)
    assert t.strength_at(1500) == pytest.approx(8.7 + 0.32 * 3)
    assert t.strength_at(1200) == pytest.approx(8.7)
    assert t.strength_at(1750) == pytest.approx(8.7 + 0.32 * 5)  # held at 1700
    assert t.strength_at(800) == pytest.approx(8.7 - 0.32 * 2)  # held at 1000
    assert t.strength_at(None) == pytest.approx(9.6)  # no rating: the format's own
    plain = _tools(strength=6.55)  # Reg M-A and M-B: not measured
    assert plain.strength_at(1500) == pytest.approx(6.55)
    assert _tools(strength=0.0, rating_line=LINE).strength_at(1500) == 0.0  # rev 10


def test_each_player_in_a_game_gets_the_strength_of_their_own_rating():
    t = _tools(strength=9.6, rating_line=LINE)
    g = t.for_game(_log(1500, ""))
    assert g.by_role == pytest.approx({"p1": 8.7 + 0.96, "p2": 9.6})
    assert g.strength == 9.6  # the format's own stays, for the records
    assert _tools(strength=6.55).for_game(_log(1500, 1100)).by_role is None


def test_the_rating_line_is_found_beside_the_formats_own_strength(tmp_path):
    shared = tmp_path / "models_v4"
    (shared / "regmc").mkdir(parents=True)
    (shared / "strength.json").write_text('{"strength": 6.55}', encoding="utf-8")
    (shared / "regmc" / "strength.json").write_text(
        '{"strength": 9.6}', encoding="utf-8"
    )
    (shared / "regmc" / "strength_by_rating.json").write_text(
        json.dumps(
            {
                "strength": 9.0,
                "center": 1200,
                "line": {"s0": 8.7, "slope_per_100": 0.32},
            }
        ),
        encoding="utf-8",
    )
    import argparse

    a = argparse.Namespace(policy=shared / "policy.json", strength="fitted")
    own = A.own_models(a)
    assert own["regmc"]["rating_line"] == pytest.approx(LINE)
    assert own["regmc"]["strength"] == pytest.approx(9.6)  # unrated: still 9.6
    b = argparse.Namespace(policy=shared / "policy.json", strength="0")
    assert "regmc" not in A.own_models(b)  # a strength by number holds for all


def test_each_side_is_weighed_at_its_own_strength():
    R = [(Action(0, "move", move=f"r{k}"),) for k in range(2)]

    def value(ours, theirs):  # option 1 is worth more to either side
        return 0.7 if ours == R[1] else 0.3

    class TV:
        def for_role(self, r):
            return value

    plain = {"p1": [(R[0], 0.5), (R[1], 0.5)], "p2": [(R[0], 0.5), (R[1], 0.5)]}
    got = A.strong_mixes(TV(), plain, {"p1": 0.0, "p2": 10.0})
    assert dict(got["p1"])[R[1]] == pytest.approx(0.5)  # strength 0: as it was
    assert dict(got["p2"])[R[1]] > 0.9  # strength 10: the better option
    same = A.strong_mixes(TV(), plain, 10.0)  # one number for both, as before
    assert dict(same["p1"])[R[1]] == pytest.approx(dict(got["p2"])[R[1]])


@pytest.mark.parametrize("entry", ["analyse_game", "turn_setups", "public_setups"])
def test_every_way_into_a_game_takes_its_players_ratings(entry, monkeypatch):
    seen = []

    def for_game(self, log):
        seen.append(log)
        raise LookupError("stop here")

    monkeypatch.setattr(A.Tools, "for_game", for_game)
    with pytest.raises(LookupError):
        out = getattr(A, entry)("tag", "the log", "regmc", _tools())
        list(out)  # a generator starts when read
    assert seen == ["the log"]


def test_the_advice_takes_the_players_ratings(monkeypatch):
    from wpa import advise as AD

    seen = []

    def for_game(self, log):
        seen.append(log)
        raise LookupError("stop here")

    monkeypatch.setattr(A.Tools, "for_game", for_game)
    for call in (
        lambda: AD.advise("tag", "the log", "regmc", _tools(), "p1"),
        lambda: AD.advise_preview("tag", "the log", "regmc", _tools(), "p1"),
        lambda: AD.advise_replacement("tag", "the log", "regmc", _tools(), "p1"),
    ):
        with pytest.raises(LookupError):
            call()
    assert seen == ["the log"] * 3


def test_a_game_analysed_without_the_rating_line_is_analysed_again(tmp_path):
    from wpa import replay as RP

    path = tmp_path / "g.jsonl"
    path.write_text(
        json.dumps({"kind": "turn", "strength": 9.6}) + "\n", encoding="utf-8"
    )
    assert not RP.stale(path, 9.6)
    assert RP.stale(path, 9.6, LINE)  # revision 15: by rating now
    path.write_text(
        json.dumps({"kind": "turn", "strength": 9.6, "strength_line": LINE}) + "\n",
        encoding="utf-8",
    )
    assert not RP.stale(path, 9.6, LINE)


def test_the_summary_says_the_strengths_follow_the_ratings(tmp_path):
    from tests.test_attribution import _rec

    rows = []
    for role, by in (("p1", 9.66), ("p2", 8.06)):
        r: dict = dict(_rec("regmc-g1", 3, role, 0.4, 0.6, True, ()), format="regmc")
        r.update(strength=9.6, strength_by_role={"p1": 9.66, "p2": 8.06})
        rows.append(r)
    path = tmp_path / "a.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    head = next(x for x in A.report(path).splitlines() if x.startswith("Reg M-C"))
    assert "by each player's rating: 8.06 to 9.66" in head
