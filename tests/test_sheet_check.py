"""Week 12 Task 5's check: on games whose sheets we know, the analysis with the
opponent's sheet hidden against the one with both sheets whole, turn by turn
and player by player: how far each part of the split moves, and how often the
board that happened is among the resolver's."""

from __future__ import annotations

import json

import pytest

from wpa import sheet_check as SC


def rec(tag, turn, role, choice, theirs, dice, before=0.5, fmt="regma", **kw):
    position = 0.01
    after = before + choice + position + theirs + dice
    return {
        "tag": tag,
        "format": fmt,
        "kind": kw.pop("kind", "turn"),
        "turn": turn,
        "role": role,
        "before": before,
        "after": after,
        "choice": choice,
        "position": position,
        "theirs": theirs,
        "dice": dice,
        "found": kw.pop("found", True),
        **kw,
    }


WHOLE = [
    rec("g1", 1, "p1", 0.04, -0.02, 0.01),
    rec("g1", 1, "p2", -0.01, 0.0, 0.0, before=0.5),
    rec("g1", 2, "p1", 0.10, 0.0, -0.05, found=False),
    rec("g1", 3, "p1", 0.0, 0.0, 0.2),  # a forced switch after it
    rec("g1", 3, "p1", 0.0, 0.0, 0.0, kind="replacement"),
    rec("g2", 1, "p1", 0.0, 0.0, 0.0, fmt="regmb"),
    rec("g1", 4, "p1", 0.0, 0.0, 0.0, skipped="choices not in the log"),
]
HIDDEN = [
    rec("g1", 1, "p1", 0.01, -0.02, 0.04, before=0.48, sheets="hidden"),
    rec("g1", 1, "p2", -0.01, 0.0, 0.0, before=0.53, sheets="hidden", found=False),
    rec("g1", 2, "p1", 0.06, 0.0, -0.01, sheets="hidden", found=False),
    rec("g1", 3, "p1", 0.0, 0.0, 0.1, sheets="hidden"),
    rec("g2", 1, "p1", 0.0, 0.0, 0.0, fmt="regmb", sheets="hidden"),
    rec("g1", 4, "p1", 0.0, 0.0, 0.0, sheets="hidden"),
]


def test_each_players_turn_is_paired_with_itself():
    got = SC.compare(WHOLE, HIDDEN)
    a = got["regma"]
    assert a["turns"] == 3  # g1 turn 1 (both players) and turn 2
    assert a["games"] == 1
    assert a["after_a_forced_switch"] == 1  # the two runs end it at different points
    assert got["regmb"]["turns"] == 1


def test_how_far_each_part_moves():
    a = SC.compare(WHOLE, HIDDEN)["regma"]
    choice = a["parts"]["choice"]
    # moved by 3, 0 and 4 points
    assert choice["moved_mean"] == pytest.approx(100 * 0.07 / 3)
    assert choice["moved_median"] == pytest.approx(3.0)
    assert choice["moved_3"] == pytest.approx(2 / 3)
    assert choice["whole_mean"] == pytest.approx(100 * 0.13 / 3)
    assert choice["hidden_mean"] == pytest.approx(100 * 0.06 / 3)
    # of the turns where the part is 3 points or more with whole sheets, the
    # share where it keeps its direction with the sheet hidden
    assert choice["same_way"] == pytest.approx(1.0)
    before = a["parts"]["before"]
    assert before["moved_median"] == pytest.approx(2.0)
    assert (a["found_whole"], a["found_hidden"]) == pytest.approx((2 / 3, 1 / 3))


def test_the_report_says_it_per_format(tmp_path):
    w, h = tmp_path / "w.jsonl", tmp_path / "h.jsonl"
    w.write_text("".join(json.dumps(r) + "\n" for r in WHOLE), encoding="utf-8")
    h.write_text("".join(json.dumps(r) + "\n" for r in HIDDEN), encoding="utf-8")
    text = SC.report(w, h)
    assert "Reg M-A: 3 turns (each player's) in 1 game" in text
    assert "Reg M-B: 1 turn (each player's) in 1 game" in text
    line = next(x for x in text.splitlines() if x.strip().startswith("your choice"))
    assert "+4.3" in line and "+2.0" in line  # the means, whole then hidden
    assert "board found" in text
