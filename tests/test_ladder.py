"""Week 19, Task 1 (Phase 5's tool): ladder mode. The bot searches the ladder
and plays one game at a time, on Showdown's own server as chasemunk or, for a
trial, on the local server. The password is read from a file the PO writes
outside the repo, and is never printed. Every game is kept with its decisions,
time and the rating after it; the run stops after the games asked, or at the
first crash, refused choice or timeout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wpa import ladder as L

# -- the password file -------------------------------------------------------


def test_the_password_is_the_files_first_line(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = tmp_path / "showdown_password.txt"
    f.write_bytes("﻿hunter2 \r\n".encode())  # as Notepad may save it
    assert L.read_password(f, repo=repo) == "hunter2"


def test_a_missing_password_file_says_how_to_make_it(tmp_path):
    f = tmp_path / "showdown_password.txt"
    with pytest.raises(SystemExit) as e:
        L.read_password(f, repo=tmp_path / "repo")
    assert str(f) in str(e.value) and "notepad" in str(e.value)


def test_an_empty_password_file_is_refused(tmp_path):
    f = tmp_path / "showdown_password.txt"
    f.write_text("\n\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        L.read_password(f, repo=tmp_path / "repo")


def test_a_password_file_inside_the_repo_is_refused_unread(tmp_path):
    repo = tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True)
    f = repo / "secrets" / "showdown_password.txt"
    f.write_text("hunter2\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        L.read_password(f, repo=repo)
    assert "outside" in str(e.value) and "hunter2" not in str(e.value)


def test_the_default_password_file_is_in_your_user_folder():
    assert L.default_password_file() == Path.home() / "showdown_password.txt"


def test_the_password_file_is_also_kept_out_of_git():
    ignored = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "showdown_password.txt" in ignored.splitlines()


# -- the options -------------------------------------------------------------


def test_the_trial_is_local_and_the_pilot_is_chasemunk():
    a = L.settings(L.parser().parse_args([]))
    assert (a.server, a.games, a.team, a.name) == ("local", 1, 40, "WPA Ladder")
    assert a.out == Path("reports/ladder_trial_regmc")
    a = L.settings(L.parser().parse_args(["--server", "showdown", "--games", "50"]))
    assert (a.server, a.games, a.name) == ("showdown", 50, "chasemunk")
    assert a.out == Path("reports/pilot_regmc")
    a = L.settings(L.parser().parse_args(["--server", "showdown", "--format", "regmd"]))
    assert a.out == Path("reports/pilot_regmd")


# -- the rating after a game ---------------------------------------------------

LINES = [
    "|win|chasemunk",
    "|raw|Someone&#39;s Alt's rating: 1104 &rarr; <strong>1088</strong>"
    "<br />(-16 for losing)",
    "|raw|Chasemunk's rating: 1000 &rarr; <strong>1023</strong><br />(+23 for winning)",
]


def test_the_ratings_are_read_from_the_end_of_the_game():
    got = L.ratings(LINES)
    assert got["chasemunk"] == (1000, 1023)
    assert got["someonesalt"] == (1104, 1088)
    assert L.ratings(["|win|chasemunk"]) == {}


# -- one game's row ------------------------------------------------------------


def _row(n=1, lines=LINES, **kw):
    base: dict[str, Any] = dict(
        me="chasemunk",
        opponent="Someone's Alt",
        won=True,
        finished=True,
        turns=7,
        seconds=300.0,
        decisions=[{"battle": "b", "kind": "turn", "seconds": 30.0}],
        crashed="",
        team=39,
    )
    base.update(kw)
    return L.game_row(n, "battle-x-1", lines, **base)


def test_a_games_row_keeps_the_result_time_decisions_and_rating():
    r = _row()
    assert (r["n"], r["tag"], r["won"], r["turns"]) == (1, "battle-x-1", True, 7)
    assert (r["rating_before"], r["rating"]) == (1000, 1023)
    assert r["opp_rating"] == 1104 and r["opponent"] == "Someone's Alt"
    assert r["vs"] == "the ladder" and r["bot_team"] == 39
    assert r["errors"] == [] and r["inactive"] is None and r["crashed"] == ""


def test_who_lost_on_time_is_kept():
    r = _row(lines=["|-message|chasemunk lost due to inactivity."])
    assert r["inactive"] == "bot" and r["rating"] is None
    r = _row(lines=["|-message|Someone's Alt lost due to inactivity."])
    assert r["inactive"] == "opponent"


# -- when the run stops ----------------------------------------------------------


def test_the_run_stops_at_a_crash_a_refused_choice_or_a_timeout():
    assert L.stop_reason(_row()) == ""
    assert "crash" in L.stop_reason(_row(crashed="KeyError('x')"))
    assert "crash" in L.stop_reason(_row(finished=False))
    refused = LINES + ["|error|[Invalid choice] Can't move: Kingambit can't use"]
    assert "refused" in L.stop_reason(_row(lines=refused))
    lost = ["|-message|chasemunk lost due to inactivity."]
    assert "timeout" in L.stop_reason(_row(lines=lost))
    slow = [{"battle": "b", "kind": "turn", "seconds": 80.0}]
    assert "timeout" in L.stop_reason(_row(decisions=slow))


def test_the_opponents_timeout_or_an_unavailable_choice_is_not_a_stop():
    lost = ["|-message|Someone's Alt lost due to inactivity."]
    assert L.stop_reason(_row(lines=lost)) == ""
    hidden = LINES + ["|error|[Unavailable choice] Can't move: disabled"]
    assert L.stop_reason(_row(lines=hidden)) == ""


# -- the pilot folder ------------------------------------------------------------


def test_a_new_run_carries_on_the_numbering(tmp_path):
    assert L.next_number(tmp_path) == 1
    rows = [_row(1), _row(2)]
    (tmp_path / "games.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    assert L.next_number(tmp_path) == 3


def test_the_summary_gives_the_record_and_the_rating():
    rows = [
        _row(1),
        {**_row(2, won=False), "rating_before": 1023, "rating": 1007},
        {**_row(3), "rating_before": 1007, "rating": 1031},
    ]
    text = L.pilot_summary(rows)
    assert "Against the ladder: 2 wins of 3 games" in text
    assert "Rating: 1000 before game 1, 1031 after game 3" in text
    assert "lowest 1007, highest 1031" in text
    assert "Crashes: 0. Illegal choices: 0. Timeouts: 0." in text
    stopped = rows + [_row(4, crashed="RuntimeError()")]
    assert "Stopped after game 4: a crash" in L.pilot_summary(stopped)


# -- the connection to Showdown ----------------------------------------------


def test_showdowns_connection_is_checked_against_certifis_list(monkeypatch):
    """On the PO's computer, Windows' store holds an expired Let's Encrypt
    cross-certificate (ISRG Root X2 by X1, to 15 Sep 2025) that Python uses
    for Showdown's battle server; certifi's list verifies it. Verification
    stays on; only where the trusted roots come from changes, and a caller
    that names its own stays as it was."""
    import ssl

    seen = []

    def fake(purpose=ssl.Purpose.SERVER_AUTH, **kw):
        seen.append(kw)
        return "context"

    monkeypatch.setattr(ssl, "create_default_context", fake)
    L.verify_with("bundle.pem")
    assert ssl.create_default_context() == "context"
    ssl.create_default_context(cafile="own.pem")
    assert seen == [
        {"cafile": "bundle.pem", "capath": None, "cadata": None},
        {"cafile": "own.pem", "capath": None, "cadata": None},
    ]
