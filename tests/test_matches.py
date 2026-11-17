"""Week 16, Task 4: the teams and the matches. Both sides draw from one pool of
popular Reg M-C teams (rated 1500 and up, training split); each team is given
the stat points players most often run with its nature (sheets show natures,
not stat points). Every pairing is played from both sides. Results come with
95% intervals; crashes, illegal choices and timeouts are counted."""

from __future__ import annotations

import json

import pytest

from wpa import matches as M
from wpa import spreads as S
from wpa.team_sheets import sheets_from_log

PACKED = (
    "Gholdengo||LifeOrb|GoodasGold|MakeItRain,NastyPlot,Protect,ShadowBall|Timid|"
    "||||50|]Arcanine-Hisui||FocusSash|RockHead|ExtremeSpeed,FlareBlitz,HeadSmash,"
    "Protect|Jolly||F|||50|"
)


def test_each_pairing_is_played_from_both_sides():
    games = M.pairings(40, 200, seed=16)
    assert len(games) == 200
    assert all(a != b for a, b in games)
    for k in range(0, 200, 2):  # each pairing, then the same two swapped
        assert games[k + 1] == games[k][::-1]
    unordered = {frozenset(g) for g in games}
    assert len(unordered) == 100  # no pairing twice
    assert games == M.pairings(40, 200, seed=16)  # the same every run


def test_a_win_rate_has_its_95_percent_interval():
    lo, hi = M.wilson(180, 200)
    assert (round(lo, 3), round(hi, 3)) == (0.851, 0.934)
    assert M.wilson(0, 0) == (0.0, 1.0)


def test_a_team_gets_the_stat_points_players_most_often_run_with_its_nature():
    usage = {
        "gholdengo": [
            S.Spread("modest", (17, 0, 0, 17, 0, 32), 0.6),
            S.Spread("timid", (2, 0, 0, 32, 0, 32), 0.3),
            S.Spread("timid", (32, 0, 0, 2, 0, 32), 0.1),
        ],
        "arcaninehisui": [S.Spread("jolly", (2, 32, 0, 0, 0, 32), 1.0)],
    }
    got = M.with_usual_points(PACKED, usage, None)
    mons = sheets_from_log("|showteam|p1|" + got)["p1"]
    assert [m.sps for m in mons] == [(2, 0, 0, 32, 0, 32), (2, 32, 0, 0, 0, 32)]
    assert got.split("]")[0].split("|")[5] == "Timid"  # the rest as it was


def test_the_bots_game_is_kept_with_both_teams_exactly():
    from wpa.bot import paste_from_packed

    lines = [
        "|player|p1|A|1|",
        "|player|p2|B|2|",
        "|poke|p1|Gholdengo, L50|",
        "|poke|p1|Arcanine-Hisui, L50, F|",
        "|poke|p2|Gholdengo, L50|",
        "|poke|p2|Arcanine-Hisui, L50, F|",
        "|teampreview|2",
        "|start",
        "|switch|p1a: Gholdengo|Gholdengo, L50|162/162",
        "|turn|1",
    ]
    mine = M.with_usual_points(PACKED, {}, None)
    first, second = PACKED.split("]")
    f = first.split("|")
    f[5], f[6] = "Modest", "17,0,0,17,0,32"
    theirs = "|".join(f) + "]" + second
    log = M.kept_log(lines, "p1", mine, theirs)
    sheets = sheets_from_log(log)
    assert sheets["p2"][0].sps == (17, 0, 0, 17, 0, 32)
    assert sheets["p2"][0].nature == "Modest"
    assert "|switch|p1a: Gholdengo|Gholdengo, L50|100/100" in log
    assert paste_from_packed(mine)  # still a team the bot can play


def _row(**kw):
    row = dict(
        k=0,
        vs="random",
        won=True,
        turns=8,
        errors=[],
        inactive=None,
        crashed="",
        decisions=[{"kind": "turn", "seconds": 30.0, "why": "", "stopped": True}],
    )
    row.update(kw)
    return row


def test_the_summary_counts_what_the_gate_asks():
    rows = [_row(k=k) for k in range(9)]
    rows.append(_row(k=9, won=False))
    rows.append(_row(k=10, won=True, inactive="opponent"))  # not counted
    rows.append(
        _row(
            k=11,
            won=False,
            errors=["|error|[Invalid choice] Can't move"],
            decisions=[{"kind": "turn", "seconds": 61.0, "why": "x", "stopped": True}],
        )
    )
    text = M.summary(rows)
    assert "Against random: 9 wins of 11 games (82%, 95% interval 52% to 95%)" in text
    assert "1 game left out: the opponent's side stopped" in text
    assert "Illegal choices: 1" in text and "Timeouts: 1" in text
    assert "Crashes: 0" in text
    assert "Thinking in a whole game: typical 30 s, longest 61 s" in text
    assert "searches stopped by the clock: 12 of 12" in text
    assert "When the clock stopped it" not in text  # no counts recorded here


def test_games_already_played_are_not_played_again(tmp_path):
    out = tmp_path / "part-0.jsonl"
    out.write_text(json.dumps(_row(k=3)) + "\n" + json.dumps(_row(k=5)) + "\n")
    assert M.done_games(tmp_path) == {3, 5}


@pytest.mark.parametrize("vs", ["random", "strongest", "typical", "engine0"])
def test_every_opponent_is_known(vs):
    assert vs in M.OPPONENTS


def test_the_bots_win_chance_is_checked_against_its_results():
    rows = [
        _row(k=0, won=True, decisions=[{"kind": "turn", "seconds": 1.0, "wp": 0.8}]),
        _row(k=1, won=False, decisions=[{"kind": "turn", "seconds": 1.0, "wp": 0.8}]),
        _row(k=2, won=False, decisions=[{"kind": "turn", "seconds": 1.0, "wp": 0.1}]),
    ]
    cal = M.calibration(rows)
    assert cal["turns"] == 3
    assert cal["brier"] == pytest.approx((0.04 + 0.64 + 0.01) / 3)
    by = {b["bin"]: b for b in cal["bins"]}
    assert by["80% to 90%"]["n"] == 2 and by["80% to 90%"]["won"] == 0.5
    assert by["10% to 20%"]["won"] == 0.0
    assert "Brier 0.230 over 3 turns" in M.summary(rows)


def test_the_bots_games_are_packed_for_the_resolver_check(tmp_path):
    import gzip

    logs = tmp_path / "logs" / "random"
    logs.mkdir(parents=True)
    (logs / "00003.log").write_text("|t:|1794939983\n|turn|1", encoding="utf-8")
    (logs / "00012.log").write_text("|t:|1794939983\n|turn|1", encoding="utf-8")
    shards, sample = M.pack_for_check(tmp_path / "logs", "random", tmp_path / "out")
    with gzip.open(shards / "part-000.jsonl.gz", "rt", encoding="utf-8") as f:
        games = [json.loads(x) for x in f]
    tags = [g["tag"] for g in games]
    assert tags == [
        "gen9championsvgc2026regmc-910000003",
        "gen9championsvgc2026regmc-910000012",
    ]
    assert json.loads(sample.read_text())["games"] == {"regmc": tags}


def test_what_the_clock_left_unvalued_is_reported():
    d = {"kind": "turn", "seconds": 45.0, "why": "", "stopped": True}
    d.update(compared=100, valued=10, screened=40)
    text = M.summary([_row(decisions=[d])])
    assert "on average 50% of the plays left unvalued, and 10 valued" in text


def test_the_engine_opponents_own_fallbacks_are_counted(tmp_path):
    rows = [{"k": 0, "decisions": [{"why": ""}, {"why": "the models failed"}]}]
    (tmp_path / "opp-part-0.jsonl").write_text(json.dumps(rows[0]) + "\n")
    assert M.opponent_note(tmp_path).endswith("1 of 2")
    assert M.done_games(tmp_path) == set()  # not the bot's rows
    assert M.opponent_note(tmp_path / "none") == ""
