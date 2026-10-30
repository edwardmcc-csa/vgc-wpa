"""Tests for the timer join (Week 5 Task 3).

A stored state is a snapshot taken where `vgc_bench`'s LogReader asks a
player to choose: before each block of the log (blocks are separated by a
blank `|` line) that holds a move or switch, when that player acts in it.
`track_decisions` reproduces those points from the log and gives the timers in
force at each, so a state at (turn, decision_index) gets the timers of exactly
its own moment: the start of a turn, or after the turn's residual for a forced
switch, or mid-turn.
"""

# ruff: noqa: E501  (battle-log fixture lines are long by nature)

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wpa import timer_join as J
from wpa import timers as T
from wpa.durations import Durations, Modifier, SourceRef, TimedEffect

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"
REF = SourceRef("x.ts", 1)

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)


def eff(id, attach, base, mods=()):
    return TimedEffect(
        "Moves", id, id, attach, base, tuple(mods), (), None, "duration", REF
    )


TABLE = Durations(
    "test",
    timed={
        "tailwind": eff(
            "tailwind",
            "sideCondition",
            4,
            [Modifier("ability", "persistent", 6, "", REF)],
        ),
        "trickroom": eff("trickroom", "pseudoWeather", 5),
        "raindance": eff("raindance", "weather", 5),
    },
)

HEAD = """|player|p1|A|1|
|player|p2|B|2|
|showteam|p1|Whim||FocusSash|Prankster|Tailwind|Timid||||50|]Rock||Leftovers|Sturdy|Rock Slide|Adamant||||50|]Back||Leftovers|Sturdy|Protect|Adamant||||50|]Bench||Leftovers|Sturdy|Protect|Adamant||||50|
|showteam|p2|Inci||Sitrus|Intimidate|Fake Out|Adamant||||50|]Fini||Sitrus|Misty Surge|Moonblast|Calm||||50|]Rime||Sitrus|Pressure|Protect|Calm||||50|]Last||Sitrus|Pressure|Protect|Calm||||50|
|teampreview"""

LEADS = """|start
|switch|p1a: Whim|Whim, L50|100/100
|switch|p1b: Rock|Rock, L50|100/100
|switch|p2a: Inci|Inci, L50|100/100
|switch|p2b: Fini|Fini, L50|100/100
|turn|1"""


def game(*blocks):
    """Blocks of a log, joined with the blank `|` line Showdown puts between them."""
    return "\n|\n".join([HEAD, LEADS, *blocks])


def tailwind_game():
    return game(
        # turn 1: p1 sets Tailwind
        "|t:|1\n|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind\n"
        "|move|p1b: Rock|Rock Slide|p2a: Inci\n|move|p2a: Inci|Fake Out|p1b: Rock\n"
        "|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|2",
        # turn 2: p2a acts, then faints; p2 must replace it after the residual
        "|t:|2\n|move|p2a: Inci|Fake Out|p1b: Rock\n|move|p1a: Whim|Moonblast|p2a: Inci\n"
        "|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|0 fnt\n"
        "|faint|p2a: Inci\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep",
        "|t:|3\n|switch|p2a: Rime|Rime, L50|100/100\n|turn|3",
        "|t:|4\n|move|p1a: Whim|Moonblast|p2a: Rime\n|move|p1b: Rock|Rock Slide|p2a: Rime\n"
        "|move|p2a: Rime|Protect|p2a: Rime\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|4",
        "|t:|5\n|move|p1a: Whim|Moonblast|p2a: Rime\n|move|p1b: Rock|Rock Slide|p2a: Rime\n"
        "|move|p2a: Rime|Protect|p2a: Rime\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|-sideend|p1: A|move: Tailwind\n|upkeep\n|turn|5",
        "|t:|6\n|move|p1a: Whim|Moonblast|p2a: Rime\n|move|p1b: Rock|Rock Slide|p2a: Rime\n"
        "|move|p2a: Rime|Protect|p2a: Rime\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|6",
        "|win|A",
    )


def keys(decisions):
    return [(d.turn, d.decision_index) for d in decisions]


def test_decision_points_follow_who_has_to_act():
    got = T.track_decisions(tailwind_game(), TABLE)
    assert keys(got["p1"]) == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)]
    # p2 also replaces its fainted Pokemon after turn 2's residual
    assert keys(got["p2"]) == [(0, 0), (1, 0), (2, 0), (2, 1), (3, 0), (4, 0), (5, 0)]


def test_turns_left_at_each_decision_from_both_sides():
    got = T.track_decisions(tailwind_game(), TABLE)
    p1 = {(d.turn, d.decision_index): J.orient(d, "p1") for d in got["p1"]}
    p2 = {(d.turn, d.decision_index): J.orient(d, "p2") for d in got["p2"]}
    # set in turn 1, lasts 4 turns: in force for turns 1 to 4
    assert p1[(1, 0)].ours == ()  # before the move that sets it
    assert p1[(2, 0)].ours == (("tailwind", "side", 3, 3),)
    assert p1[(3, 0)].ours == (("tailwind", "side", 2, 2),)
    assert p1[(4, 0)].ours == (("tailwind", "side", 1, 1),)
    assert p1[(5, 0)].ours == ()
    assert p2[(2, 0)].theirs == (("tailwind", "side", 3, 3),)
    assert p2[(2, 0)].ours == ()
    # the forced switch comes after turn 2 is over: turns 3 and 4 remain
    assert p2[(2, 1)].theirs == (("tailwind", "side", 2, 2),)


def test_each_decision_says_when_in_the_turn_it_was_taken():
    got = T.track_decisions(tailwind_game(), TABLE)
    moments = {(d.turn, d.decision_index): d.moment for d in got["p2"]}
    assert moments[(0, 0)] == "preview"
    assert moments[(1, 0)] == "turn_start"
    assert moments[(2, 1)] == "after_turn"  # the forced switch
    assert J.orient(got["p2"][3], "p2").moment == "after_turn"


def test_a_skipped_turn_start_makes_the_forced_switch_decision_zero():
    # p1a faints before acting while p1b acts: LogReader does not record p1's
    # turn-1 start, so p1's next decision (the replacement) is (1, 0)
    log = game(
        "|t:|1\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-damage|p1a: Whim|0 fnt\n"
        "|faint|p1a: Whim\n|move|p1b: Rock|Rock Slide|p2a: Inci\n"
        "|move|p2b: Fini|Moonblast|p1b: Rock",
        "|upkeep",
        "|t:|2\n|switch|p1a: Back|Back, L50|100/100\n|turn|2",
        "|win|B",
    )
    got = T.track_decisions(log, TABLE)["p1"]
    assert [(d.turn, d.decision_index, d.moment) for d in got] == [
        (0, 0, "preview"),
        (1, 0, "after_turn"),
    ]


def test_a_decision_with_no_timer_gets_an_empty_result_not_an_error():
    got = T.track_decisions(tailwind_game(), TABLE)
    first = J.orient(got["p1"][0], "p1")
    assert first == J.JoinedTimers(moment="preview")
    assert first.is_empty()


def test_timers_at_a_decision_never_depend_on_what_comes_after_it():
    log = tailwind_game()
    full = T.track_decisions(log, TABLE)
    blocks = log.split("\n|\n")
    for cut in range(3, len(blocks) + 1):
        part = T.track_decisions("\n|\n".join(blocks[:cut]), TABLE)
        for role in ("p1", "p2"):
            n = len(part[role])
            assert part[role] == full[role][:n], (cut, role)
    # removing the future end event changes nothing before it either
    no_end = T.track_decisions(
        log.replace("|-sideend|p1: A|move: Tailwind\n", ""), TABLE
    )
    assert no_end["p1"][:5] == full["p1"][:5]


def test_both_backline_pokemon_seen_adds_the_second_team_preview_decision():
    log = game(
        "|t:|1\n|switch|p1a: Back|Back, L50|100/100\n|switch|p1b: Bench|Bench, L50|100/100\n"
        "|move|p2a: Inci|Fake Out|p1b: Bench\n|move|p2b: Fini|Moonblast|p1a: Back",
        "|upkeep\n|turn|2",
        "|win|B",
    )
    got = T.track_decisions(log, TABLE)
    assert keys(got["p1"]) == [(0, 0), (0, 1), (1, 0)]
    assert keys(got["p2"]) == [(0, 0), (1, 0)]


def test_a_player_whose_only_active_pokemon_fainted_in_the_block_is_not_recorded():
    # LogReader skips a block where one slot passed and the player's own Pokemon fainted
    log = game(
        "|t:|1\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-damage|p1a: Whim|0 fnt\n"
        "|faint|p1a: Whim\n|move|p1b: Rock|Rock Slide|p2a: Inci\n"
        "|move|p2b: Fini|Moonblast|p1b: Rock",
        "|upkeep\n|turn|2",
        "|win|B",
    )
    got = T.track_decisions(log, TABLE)
    assert keys(got["p1"]) == [(0, 0)]
    assert keys(got["p2"]) == [(0, 0), (1, 0)]


def state(turn, d, outcome=None):
    return {"turn": turn, "decision_index": d, "outcome": outcome}


def test_align_gives_one_result_per_state_and_none_for_the_terminal_one():
    got = T.track_decisions(tailwind_game(), TABLE)["p1"]
    states = [state(d.turn, d.decision_index) for d in got] + [state(5, 1, True)]
    joined = J.align(states, got, "p1")
    assert joined is not None
    assert len(joined) == len(states) and joined[-1] is None
    assert joined[2] == J.orient(got[2], "p1")


def test_align_refuses_when_the_decision_points_do_not_match():
    got = T.track_decisions(tailwind_game(), TABLE)["p1"]
    states = [state(d.turn, d.decision_index) for d in got[:-1]] + [state(9, 0, True)]
    assert J.align(states, got, "p1") is None


def test_the_side_file_carries_decisions_and_reads_back(tmp_path):
    log = tailwind_game()
    path = tmp_path / "t.jsonl.gz"
    T.write_timer_file(
        path,
        [
            (
                "gen9championsvgc2026regma-1",
                "regma",
                T.track_game(log, TABLE),
                T.track_decisions(log, TABLE),
            )
        ],
    )
    rec = T.read_timer_file(path)["gen9championsvgc2026regma-1"]
    assert rec.decisions["p2"] == T.track_decisions(log, TABLE)["p2"]
    assert rec.at(2).timers == (("tailwind", "p1", 3, 3),)


def test_cross_check_compares_turn_start_timers_with_the_turns_first_observation():
    got = T.track_decisions(tailwind_game(), TABLE)["p1"]

    def observed(turn):
        listed = ["p1:Tailwind"] if turn in (2, 3, 4) else []
        if turn == 4:
            listed = []  # pretend the observations missed it on turn 4
        return [
            {"turn": turn, "weather": None, "fields": [], "side_conditions": listed}
        ]

    states = [
        {**state(d.turn, d.decision_index), "observations": observed(d.turn)}
        for d in got
    ] + [state(5, 1, True)]
    joined = J.align(states, got, "p1")
    assert joined is not None
    counts = J.cross_check(states, joined, "p1", {"tailwind", "trickroom", "raindance"})
    assert counts[("tailwind", "agree")] == 2  # turns 2 and 3
    assert counts[("tailwind", "timer_not_listed")] == 1  # turn 4
    assert counts[("tailwind", "listed_not_at_turn_start")] == 0


def test_cross_check_explains_a_listing_that_started_during_the_turn():
    got = T.track_decisions(tailwind_game(), TABLE)["p1"]
    states = [
        {
            **state(d.turn, d.decision_index),
            "observations": [
                {
                    "turn": d.turn,
                    "weather": None,
                    "fields": [],
                    "side_conditions": ["p1:Tailwind"],
                }
            ]
            if d.turn == 1
            else [],
        }
        for d in got
    ] + [state(5, 1, True)]
    joined = J.align(states, got, "p1")
    assert joined is not None
    starts = {("p1", "tailwind", 1)}
    counts = J.cross_check(states, joined, "p1", {"tailwind"}, starts=starts)
    assert counts[("tailwind", "started_this_turn")] == 1
    assert counts[("tailwind", "listed_not_at_turn_start")] == 0


def test_cross_check_explains_a_timer_that_ended_before_the_turns_first_event():
    got = T.track_decisions(tailwind_game(), TABLE)["p1"]
    states = [
        {
            **state(d.turn, d.decision_index),
            "observations": [
                {"turn": d.turn, "weather": None, "fields": [], "side_conditions": []}
            ]
            if d.turn == 3
            else [],
        }
        for d in got
    ] + [state(5, 1, True)]
    joined = J.align(states, got, "p1")
    assert joined is not None
    ends = {("p1", "tailwind", 3)}  # say a switch-in removed it at turn 3's start
    counts = J.cross_check(states, joined, "p1", {"tailwind"}, ends=ends)
    assert counts[("tailwind", "ended_this_turn")] == 1
    assert counts[("tailwind", "timer_not_listed")] == 0


# --------------------------------------------------------------------------
# The three real games in tests/fixtures/w5
# --------------------------------------------------------------------------

LOGS = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
EMPTY = Durations("empty", timed={})


@pytest.mark.parametrize("tag", sorted(LOGS))
def test_decision_points_match_the_stored_states_of_real_games(tag):
    decisions = T.track_decisions(LOGS[tag], EMPTY)
    for role in ("p1", "p2"):
        states = json.loads(
            (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
        )
        assert keys(decisions[role]) == [
            (s["turn"], s["decision_index"]) for s in states[:-1]
        ], role
        assert J.align(states, decisions[role], role) is not None


@needs_showdown
def test_real_weather_shows_up_where_the_observations_list_it():
    from wpa.durations import load_all

    table = load_all(SHOWDOWN)["regma"]
    tag = "gen9championsvgc2026regma-2580291588"  # Pelipper's Drizzle, turn 2
    decisions = T.track_decisions(LOGS[tag], table)
    states = json.loads((FIXTURES / f"{tag}-p1.json").read_text(encoding="utf-8"))
    joined = J.align(states, decisions["p1"], "p1")
    assert joined is not None
    starts = {
        ("field" if tm.target == "field" else tm.target[:2], tm.id, tm.start_turn)
        for tm in T.track_game(LOGS[tag], table).timers
    }
    counts = J.cross_check(states, joined, "p1", set(table.timed), starts)
    assert counts[("raindance", "agree")] > 0
    assert counts[("raindance", "listed_not_at_turn_start")] == 0
    assert counts[("raindance", "timer_not_listed")] == 0


def test_the_check_report_counts_alignment_and_cross_check_by_format():
    report = J.CheckReport()
    for tag, log in sorted(LOGS.items()):
        states = {
            role: json.loads(
                (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
            )
            for role in ("p1", "p2")
        }
        report.add(tag, log, states, EMPTY)
    assert report.files["regma"] == 4 and report.aligned["regma"] == 4
    assert report.files["regmb"] == 2 and report.aligned["regmb"] == 2
    text = report.describe()
    assert "regma" in text and "aligned 4 of 4" in text
