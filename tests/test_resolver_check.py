"""The resolver check (Week 12 Task 1): on a fixed, saved sample of validation
games, how often the resolver plays a turn out in full, and how often the board
that happened is among its boards. It runs on today's code or on an earlier
commit's, so a fix can be measured before and after on the same games."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from wpa import resolver_check as RC
from wpa.choices import Action


def mon(hp: float, fainted: bool = False) -> dict:
    return {"hp_fraction": hp, "fainted": fainted}


def out(p1, p2, partial=(), prob=1.0):
    return NS(sides={"p1": p1, "p2": p2}, partial=frozenset(partial), prob=prob)


class Fake:
    """A resolver that gives fixed boards for each pair of choices."""

    def __init__(self, boards):
        self.boards = boards
        self.asked = []

    def resolve(self, sides, fld, actions):
        self.asked.append((actions["p1"], actions["p2"]))
        return self.boards[(actions["p1"], actions["p2"])]


HIT = Action(0, "move", "tackle", ("foe", 0))
SLOW = Action(0, "move", "slam", ("foe", 0))
QUICK = Action(0, "move", "fakeout", ("foe", 0))
OUT = Action(0, "switch", switch_to=1)
PRIORITY = {"fakeout": 3}


def setup(resolver, taken, actual, before=None, opts=None, hidden=None):
    """A turn as `wpa.attribution.turn_setups` gives one: each side with one
    Pokemon in, sheet position 0."""
    opts = opts or {r: {0: [taken[r]]} for r in ("p1", "p2")}
    turns = {
        r: NS(taken={0: taken[r]}, hidden=(hidden or {}).get(r, set()))
        for r in ("p1", "p2")
    }
    return NS(
        base={"tag": "gen9championsvgc2026regma-1", "format": "regma", "turn": 3},
        turn=3,
        turns=turns,
        opts=opts,
        chances={r: {0: [1.0 / len(opts[r][0])] * len(opts[r][0])} for r in opts},
        tv=NS(
            resolver=resolver,
            sides=before or {"p1": [mon(1.0)], "p2": [mon(1.0)]},
            fld=None,
        ),
        actual=actual,
    )


def test_a_turn_is_found_when_one_of_its_boards_is_the_board_that_happened():
    fake = Fake(
        {
            ((HIT,), (HIT,)): [
                out([mon(0.81)], [mon(0.52)], prob=0.9),
                out([mon(0.81)], [mon(0.0, True)], prob=0.1),
            ]
        }
    )
    actual = {"p1": [mon(0.8)], "p2": [mon(0.5)]}
    rec = RC.check_turn(setup(fake, {"p1": HIT, "p2": HIT}, actual), PRIORITY)
    assert rec["found"] is True
    assert rec["partial"] == []
    assert rec["missed"] is None
    assert rec["ko"] is False
    assert (rec["pairs"], rec["boards"]) == (1, 2)
    assert (rec["tag"], rec["format"], rec["turn"]) == (
        "gen9championsvgc2026regma-1",
        "regma",
        3,
    )
    assert rec["seconds"] >= 0


def test_a_choice_the_log_hides_is_tried_over_every_choice_the_log_allows():
    """Knocked out before moving: any move without raised priority, never a
    switch (it would show), as the analysis takes it."""
    fake = Fake(
        {
            ((HIT,), (HIT,)): [out([mon(0.2)], [mon(0.0, True)])],
            ((HIT,), (SLOW,)): [out([mon(0.6)], [mon(0.0, True)])],
        }
    )
    actual = {"p1": [mon(0.6)], "p2": [mon(0.0, True)]}
    ts = setup(
        fake,
        {"p1": HIT, "p2": "fainted"},
        actual,
        opts={"p1": {0: [HIT]}, "p2": {0: [HIT, SLOW, QUICK, OUT]}},
    )
    rec = RC.check_turn(ts, PRIORITY)
    assert sorted(fake.asked, key=str) == sorted(
        [((HIT,), (HIT,)), ((HIT,), (SLOW,))], key=str
    )
    assert rec["pairs"] == 2
    assert rec["found"] is True
    assert rec["ko"] is True


def test_a_turn_partly_modelled_lists_every_reason_once():
    fake = Fake(
        {
            ((HIT,), (HIT,)): [
                out([mon(0.8)], [mon(0.5)], partial={"move:leechseed"}),
                out(
                    [mon(0.8)], [mon(0.4)], partial={"ability:static", "move:leechseed"}
                ),
            ]
        }
    )
    actual = {"p1": [mon(0.8)], "p2": [mon(0.5)]}
    rec = RC.check_turn(setup(fake, {"p1": HIT, "p2": HIT}, actual), PRIORITY)
    assert rec["partial"] == ["ability:static", "move:leechseed"]
    assert rec["found"] is True


def test_a_miss_says_whether_a_knock_out_differs_or_only_hp():
    actual_ko = {"p1": [mon(0.8)], "p2": [mon(0.0, True)]}
    fake = Fake({((HIT,), (HIT,)): [out([mon(0.8)], [mon(0.3)])]})
    rec = RC.check_turn(setup(fake, {"p1": HIT, "p2": HIT}, actual_ko), PRIORITY)
    assert (rec["found"], rec["missed"], rec["off"]) == (False, "knock-out", None)

    actual = {"p1": [mon(0.8)], "p2": [mon(0.5)]}
    fake = Fake(
        {
            ((HIT,), (HIT,)): [
                out([mon(0.8)], [mon(0.3)]),
                out([mon(0.8)], [mon(0.38)]),
                out([mon(0.8)], [mon(0.0, True)]),
            ]
        }
    )
    rec = RC.check_turn(setup(fake, {"p1": HIT, "p2": HIT}, actual), PRIORITY)
    assert (rec["found"], rec["missed"]) == (False, "hp")
    assert rec["off"] == pytest.approx(0.12)  # the closest board's largest gap


def test_a_decision_point_left_out_is_counted_once_with_its_reason():
    fake = Fake({((HIT,), (HIT,)): [out([mon(0.8)], [mon(0.5)])]})
    ts = setup(fake, {"p1": HIT, "p2": HIT}, {"p1": [mon(0.8)], "p2": [mon(0.5)]})
    left = [
        {
            "tag": "g",
            "format": "regma",
            "turn": 1,
            "role": r,
            "skipped": "forfeit or timer",
        }
        for r in ("p1", "p2")
    ]
    recs = RC.check_game([left, ts], PRIORITY)
    assert len(recs) == 2
    assert recs[0] == {
        "tag": "g",
        "format": "regma",
        "turn": 1,
        "skipped": "forfeit or timer",
    }
    assert recs[1]["found"] is True


def test_an_error_in_one_turn_is_kept_and_the_game_goes_on():
    class Broken:
        def resolve(self, sides, fld, actions):
            raise KeyError("nomove")

    good = Fake({((HIT,), (HIT,)): [out([mon(0.8)], [mon(0.5)])]})
    actual = {"p1": [mon(0.8)], "p2": [mon(0.5)]}
    recs = RC.check_game(
        [
            setup(Broken(), {"p1": HIT, "p2": HIT}, actual),
            setup(good, {"p1": HIT, "p2": HIT}, actual),
        ],
        PRIORITY,
    )
    assert recs[0]["skipped"].startswith("error: KeyError")
    assert recs[1]["found"] is True


def rec(fmt, found, partial=(), ko=False, missed=None, off=None, seconds=0.1):
    return {
        "tag": "g",
        "format": fmt,
        "turn": 1,
        "found": found,
        "partial": list(partial),
        "ko": ko,
        "missed": missed,
        "off": off,
        "pairs": 1,
        "boards": 1,
        "seconds": seconds,
    }


RUN = [
    rec("regma", True, ko=True),
    rec("regma", True, ["move:leechseed"]),
    rec("regma", False, missed="hp", off=0.1),
    rec(
        "regma",
        False,
        ["move:leechseed", "ability:protean"],
        ko=True,
        missed="knock-out",
    ),
    {"tag": "g", "format": "regma", "turn": 9, "skipped": "forfeit or timer"},
    rec("regmb", True),
]


def test_the_summary_gives_each_format_its_shares_reasons_and_misses():
    s = RC.summarise(RUN)
    a = s["regma"]
    assert a["turns"] == 4  # the point left out is not a turn checked
    assert a["skipped"] == {"forfeit or timer": 1}
    assert (a["full"], a["found"], a["both"]) == (2, 2, 1)
    assert (a["ko_turns"], a["ko_full"], a["ko_found"], a["ko_both"]) == (2, 1, 1, 1)
    assert a["reasons"] == {"move:leechseed": 2, "ability:protean": 1}
    assert a["missed"] == {"hp": 1, "knock-out": 1}
    assert a["seconds"] == pytest.approx(0.4)
    assert s["regmb"]["turns"] == 1


def test_the_summary_puts_runs_side_by_side_per_format():
    before = RUN
    after = [dict(r, partial=[]) if "found" in r else r for r in RUN]
    text = "\n".join(
        RC.summary_lines(
            {"9e9ef90": before, "today": after},
            {
                "9e9ef90": {"wall": 120.0, "workers": 6},
                "today": {"wall": 180.0, "workers": 6},
            },
        )
    )
    assert "Reg M-A" in text and "Reg M-B" in text
    head = next(x for x in text.splitlines() if "9e9ef90" in x and "today" in x)
    assert head.index("9e9ef90") < head.index("today")
    full = next(x for x in text.splitlines() if x.strip().startswith("fully modelled"))
    assert full.index("50.0%") < full.index("100.0%")
    assert "leechseed" in text  # the reasons, with each run's count
    assert "2 min" in text and "3 min" in text


def test_the_sample_is_saved_once_and_never_holds_a_test_game(tmp_path):
    path = tmp_path / "games.json"
    RC.save_sample(path, {"regma": ["a", "b"], "regmb": ["c"]}, "the brief's sample")
    assert RC.load_sample(path) == {"regma": ["a", "b"], "regmb": ["c"]}
    assert RC.load_sample(
        path, {"a": "validation", "b": "validation", "c": "validation"}
    )
    with pytest.raises(ValueError, match="test split"):
        RC.load_sample(path, {"a": "validation", "b": "test", "c": "validation"})
    with pytest.raises(FileExistsError):
        RC.save_sample(path, {"regma": ["d"]}, "again")


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_an_earlier_commit_is_set_up_beside_the_repo_with_the_check(tmp_path):
    root = tmp_path / "repo"
    (root / "wpa").mkdir(parents=True)
    (root / "calc").mkdir()
    (root / "scripts").mkdir()
    (root / "calc" / "bridge.js").write_text("// calc\n")
    (root / "scripts" / "dump_dex.js").write_text("// dex\n")
    (root / "wpa" / "__init__.py").write_text("")
    (root / "wpa" / "thing.py").write_text("WHEN = 'before'\n")

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "before")
    first = git("rev-parse", "--short", "HEAD")
    (root / "wpa" / "thing.py").write_text("WHEN = 'after'\n")
    git("commit", "-qam", "after")

    dest = RC.extract_code(first, root, tmp_path / "code")
    assert (dest / "wpa" / "thing.py").read_text() == "WHEN = 'before'\n"
    # this check itself goes with it, and the calculator and scripts it calls
    assert (dest / "wpa" / "resolver_check.py").read_text(encoding="utf-8") == Path(
        RC.__file__
    ).read_text(encoding="utf-8")
    assert (dest / "calc" / "bridge.js").exists()
    assert (dest / "scripts" / "dump_dex.js").exists()
    # the working copy is untouched
    assert (root / "wpa" / "thing.py").read_text() == "WHEN = 'after'\n"


def test_the_run_on_an_earlier_commit_uses_the_same_data_by_full_paths(tmp_path):
    a = RC.parse_args(["--code", "9e9ef90", "--workers", "3"])
    cmd = RC.child_command(a, tmp_path / "code", Path.cwd())
    assert cmd[:3] == [sys.executable, "-m", "wpa.resolver_check"]
    for flag in (
        "--sample",
        "--logs",
        "--showdown",
        "--usage",
        "--bring",
        "--policy",
        "--out-dir",
    ):
        value = Path(cmd[cmd.index(flag) + 1])
        assert value.is_absolute(), flag
    assert cmd[cmd.index("--label") + 1] == "9e9ef90"
    assert cmd[cmd.index("--workers") + 1] == "3"
    assert "--code" not in cmd  # the child runs the code it sits in
    assert "--expect-code" in cmd


def test_each_turn_record_is_one_line_of_json():
    fake = Fake({((HIT,), (HIT,)): [out([mon(0.8)], [mon(0.5)])]})
    ts = setup(fake, {"p1": HIT, "p2": HIT}, {"p1": [mon(0.8)], "p2": [mon(0.5)]})
    line = json.dumps(RC.check_turn(ts, PRIORITY))
    assert json.loads(line)["found"] is True


def test_a_long_reason_keeps_the_columns_in_line():
    runs = {
        "before": [rec("regmb", True, ["leech seed heals the Pokemon in its place"])],
        "after": [rec("regmb", True)],
    }
    rows = [
        x
        for x in RC.summary_lines(runs)
        if x.startswith("  ") and x.rstrip()[-1:].isdigit()
    ]
    assert len(rows) > 3
    assert len({len(x) for x in rows}) == 1


def test_a_run_stopped_mid_line_carries_on_from_its_last_whole_game(tmp_path):
    path = tmp_path / "run.jsonl"
    whole = [
        json.dumps({"tag": "a", "format": "regma", "turn": 1, "found": True}),
        json.dumps({"tag": "b", "format": "regma", "turn": 1, "found": True}),
    ]
    path.write_text("\n".join(whole) + '\n{"tag": "c", "form', encoding="utf-8")
    assert RC.done_tags(path) == {"a", "b"}
    assert path.read_text(encoding="utf-8") == "\n".join(whole) + "\n"
    assert RC.done_tags(tmp_path / "none.jsonl") == set()


def test_a_trial_run_can_stop_after_a_few_games():
    a = RC.parse_args(["--max-games", "20"])
    assert a.max_games == 20
    assert RC.parse_args([]).max_games is None
