"""Week 18, Task 5 (Phase 4 begins): choosing the bot's team. Each candidate is
the bot's team in every game of its run, against the pool's teams in turn,
played by the engine itself (the same strength on both sides, so the team is
what differs). A table across the runs gives each candidate's win rate with its
95% interval. The format is a switch, so the same tool reruns on Reg M-D."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from wpa import matches as M


def test_the_candidate_plays_every_game_against_each_pool_team_in_turn():
    games = M.team_games(13, 40, 80, seed=18)
    assert len(games) == 80
    assert all(mine == 13 for mine, _ in games)
    # each of the 40 once in the first 40 games, then each once more
    assert sorted(t for _, t in games[:40]) == list(range(40))
    assert Counter(t for _, t in games) == Counter({t: 2 for t in range(40)})
    assert games == M.team_games(13, 40, 80, seed=18)  # the same every run
    assert [t for _, t in games[:40]] != list(range(40))  # in a shuffled order


def test_a_short_run_still_spreads_over_the_pool():
    games = M.team_games(0, 40, 30, seed=18)
    assert len(games) == 30 and len({t for _, t in games}) == 30


def test_the_engine_with_its_shortcuts_is_an_opponent():
    assert "engine" in M.OPPONENTS and "engine" in M.VS_CODE
    assert len(set(M.VS_CODE.values())) == len(M.VS_CODE)


def test_each_candidate_has_its_own_folder():
    a = argparse.Namespace(vs="engine", untimed=False, team=14)
    assert M.run_name(a) == "engine-team14"
    assert M.run_name(argparse.Namespace(vs="random", untimed=False)) == "random"


def test_the_options_for_a_candidate_and_a_format():
    a = M.parser().parse_args(["--vs", "engine", "--team", "14", "--format", "regmd"])
    assert (a.vs, a.team, a.format) == ("engine", 14, "regmd")
    a = M.parser().parse_args([])
    assert (a.team, a.format) == (None, "regmc")


def test_the_format_names_follow_the_regulation():
    assert M.format_id("regmc") == "gen9championsvgc2026regmc"
    assert M.format_id("regmd") == "gen9championsvgc2026regmd"
    assert M.format_label("regmc") == "Reg M-C"
    assert M.format_label("regmd") == "Reg M-D"


def _rows(folder, team, results):
    folder.mkdir(parents=True)
    rows = [
        {
            "k": k,
            "vs": folder.name,
            "bot_team": team - 1,
            "opp_team": k % 40,
            "won": won,
            "inactive": None,
            "crashed": "",
            "decisions": [],
        }
        for k, won in enumerate(results)
    ]
    (folder / "part-0.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def test_the_round_robin_table_ranks_the_candidates(tmp_path):
    pool = [{"species": [f"Mon{i}a", f"Mon{i}b"], "count": 1} for i in range(40)]
    _rows(tmp_path / "engine-team14", 14, [True] * 60 + [False] * 20)
    _rows(tmp_path / "engine-team2", 2, [True] * 30 + [False] * 50)
    _rows(tmp_path / "random-team5", 5, [True] * 10)  # another opponent: not here
    text = M.round_robin(tmp_path, pool, "engine")
    lines = text.splitlines()
    first = next(i for i, x in enumerate(lines) if "Mon13a" in x)
    second = next(i for i, x in enumerate(lines) if "Mon1a" in x)
    assert first < second  # the better win rate first
    assert "60 of 80 (75%, 95% interval 65% to 83%)" in lines[first]
    assert "30 of 80 (38%" in lines[second]
    assert "Mon4a" not in text


def test_a_game_whose_opponent_stopped_is_left_out_of_the_table(tmp_path):
    pool = [{"species": ["A"], "count": 1}] * 40
    _rows(tmp_path / "engine-team1", 1, [True, False])
    path = tmp_path / "engine-team1" / "part-0.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["inactive"] = "opponent"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert "0 of 1 (0%" in M.round_robin(tmp_path, pool, "engine")
