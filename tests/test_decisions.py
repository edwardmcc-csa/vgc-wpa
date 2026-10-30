"""Tests for wpa/decisions.py (Week 6 Task 1): our own decision table.

Every decision point the game's structure creates, none dropped because of what
happens after it: team preview, every turn start (both players), a replacement
after the turn's residual, a switch during the turn (after U-turn and similar).
At each, the board as a stored state would show it, and the timers there.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wpa import decisions as D
from wpa.durations import Durations, Modifier, SourceRef, TimedEffect

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
LOGS = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
REF = SourceRef("x.ts", 1)
TABLE = Durations(
    "t",
    timed={
        "tailwind": TimedEffect(
            "Moves",
            "tailwind",
            "tailwind",
            "sideCondition",
            4,
            (Modifier("ability", "persistent", 6, "", REF),),
            (),
            None,
            "duration",
            REF,
        )
    },
)
EMPTY = Durations("e", timed={})

HEAD = """|player|p1|A|1|
|player|p2|B|2|
|showteam|p1|Whim||FocusSash|Prankster|Tailwind|Timid||||50|]Rock||Leftovers|Sturdy|RockSlide|Adamant||||50|]Back||Leftovers|Sturdy|Protect|Adamant||||50|]Bench||Leftovers|Sturdy|Protect|Adamant||||50|]Five||Leftovers|Sturdy|Protect|Adamant||||50|]Six||Leftovers|Sturdy|Protect|Adamant||||50|
|showteam|p2|Inci||Sitrus|Intimidate|FakeOut|Adamant||||50|]Fini||Sitrus|MistySurge|Moonblast|Calm||||50|]Rime||Sitrus|Pressure|Protect|Calm||||50|]Last||Sitrus|Pressure|Protect|Calm||||50|]Five||Sitrus|Pressure|Protect|Calm||||50|]Six||Sitrus|Pressure|Protect|Calm||||50|
|teampreview"""

LEADS = """|start
|switch|p1a: Whim|Whim, L50|100/100
|switch|p1b: Rock|Rock, L50|100/100
|switch|p2a: Inci|Inci, L50|100/100
|switch|p2b: Fini|Fini, L50|100/100
|turn|1"""


def game(*blocks):
    return "\n|\n".join([HEAD, LEADS, *blocks])


def skipped_by_logreader():
    # p1a faints before acting while p1b acts: LogReader drops p1's turn-1 start
    return game(
        "|t:|1\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-damage|p1a: Whim|0 fnt\n"
        "|faint|p1a: Whim\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|40/100\n"
        "|move|p2b: Fini|Moonblast|p1b: Rock\n|-damage|p1b: Rock|55/100",
        "|upkeep",
        "|t:|2\n|switch|p1a: Back|Back, L50|100/100\n|turn|2",
        "|t:|3\n|move|p1a: Back|Protect|p1a: Back\n|move|p1b: Rock|Rock Slide|p2a: Inci\n"
        "|move|p2a: Inci|Fake Out|p1b: Rock\n|move|p2b: Fini|Moonblast|p1a: Back",
        "|upkeep\n|turn|3",
        "|-message|B forfeited.",
        "|win|A",
    )


def keys(g, role):
    return [(s["turn"], s["decision_index"], s["moment"]) for s in g.states[role][:-1]]


def test_every_structural_decision_is_kept_even_when_logreader_drops_it():
    g = D.build_game(skipped_by_logreader(), EMPTY)
    assert keys(g, "p1") == [
        (0, 0, "preview"),
        (1, 0, "turn_start"),  # LogReader dropped this one
        (1, 1, "after_turn"),  # the replacement for Whim
        (2, 0, "turn_start"),
        (3, 0, "turn_start"),
    ]
    assert keys(g, "p2") == [
        (0, 0, "preview"),
        (1, 0, "turn_start"),
        (2, 0, "turn_start"),
        (3, 0, "turn_start"),
    ]
    # the last turn-start was followed by a forfeit, with no move: the old reader
    # took no snapshot there either
    assert g.recorded["p1"] == [True, False, True, True, False]


def test_regenerator_heals_a_third_on_switching_out():
    log = game(
        "|t:|1\n|move|p2a: Inci|Fake Out|p1b: Rock\n|-damage|p1b: Rock|40/100\n"
        "|move|p1a: Whim|Tailwind|p1a: Whim\n|move|p1b: Rock|Rock Slide|p2a: Inci\n"
        "|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|2",
        "|t:|2\n|switch|p1b: Back|Back, L50|100/100\n|move|p1a: Whim|Tailwind|p1a: Whim\n"
        "|move|p2a: Inci|Fake Out|p1a: Whim\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|3",
        "|win|A",
    ).replace("Rock||Leftovers|Sturdy|", "Rock||Leftovers|Regenerator|")
    g = D.build_game(log, EMPTY)
    start3 = [s for s in g.states["p1"] if s["turn"] == 3][0]
    assert start3["our_pokemon"][1]["hp_fraction"] == pytest.approx(0.40 + 1 / 3, abs=0.01)


def test_hit_points_parse_with_status_and_stray_characters():
    assert D._hp("55/100 par") == (0.55, False)
    assert D._hp("0 fnt") == (0.0, True)
    assert D._hp("20/100y") == (0.2, False)


def test_the_board_at_each_decision():
    g = D.build_game(skipped_by_logreader(), EMPTY)
    start1 = g.states["p1"][1]
    assert [p["active"] for p in start1["our_pokemon"]] == [
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert [p["hp_fraction"] for p in start1["our_pokemon"]][:3] == [1.0, 1.0, 0.0]
    replace = g.states["p1"][2]  # after turn 1
    ours = replace["our_pokemon"]
    assert ours[0]["fainted"] and not ours[0]["active"] and ours[0]["hp_fraction"] == 0
    assert ours[1]["hp_fraction"] == pytest.approx(0.55)
    assert replace["opp_pokemon"][0]["hp_fraction"] == pytest.approx(0.40)
    start2 = g.states["p1"][3]
    assert (
        start2["our_pokemon"][2]["active"]
        and start2["our_pokemon"][2]["hp_fraction"] == 1.0
    )
    assert [p["species"] for p in start2["our_pokemon"]] == [
        "whim",
        "rock",
        "back",
        "bench",
        "five",
        "six",
    ]


def test_the_label_comes_from_the_win_line_including_a_forfeit():
    g = D.build_game(skipped_by_logreader(), EMPTY)
    assert g.states["p1"][-1]["outcome"] is True
    assert g.states["p2"][-1]["outcome"] is False


def test_every_turn_start_has_one_decision_for_each_player():
    g = D.build_game(skipped_by_logreader(), EMPTY)
    starts = {
        r: [s["turn"] for s in g.states[r][:-1] if s["moment"] == "turn_start"]
        for r in ("p1", "p2")
    }
    assert starts["p1"] == starts["p2"] == [1, 2, 3]


def test_timers_are_joined_at_each_decision():
    log = game(
        "|t:|1\n|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind\n"
        "|move|p1b: Rock|Rock Slide|p2a: Inci\n|move|p2a: Inci|Fake Out|p1b: Rock\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|2",
        "|win|A",
    )
    g = D.build_game(log, TABLE)
    assert g.joined["p1"][2].ours == (("tailwind", "side", 3, 3),)
    assert g.joined["p2"][2].theirs == (("tailwind", "side", 3, 3),)


def test_decisions_never_depend_on_what_comes_after_them():
    from wpa.state_timing import usable_observations

    def without_obs(s):
        return {k: v for k, v in s.items() if k != "observations"}

    log = skipped_by_logreader()
    blocks = log.split("\n|\n")
    full = D.build_game(log, EMPTY)
    for cut in range(2, len(blocks)):
        part = D.build_game("\n|\n".join(blocks[: cut + 1]), EMPTY)
        for role in ("p1", "p2"):
            n = sum(1 for p in part.points[role] if p < cut)
            assert [without_obs(s) for s in part.states[role][:n]] == [
                without_obs(s) for s in full.states[role][:n]
            ]
            assert part.joined[role][:n] == full.joined[role][:n]
            # what a decision may use from the observations never changes
            for k in range(n):
                assert usable_observations(part.states[role], k) == usable_observations(
                    full.states[role], k
                )


def test_end_of_turn_conditions_are_offered_to_later_turns_as_observations():
    log = game(
        "|t:|1\n|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind\n"
        "|move|p1b: Rock|Rock Slide|p2a: Inci\n|move|p2a: Inci|Fake Out|p1b: Rock\n|move|p2b: Fini|Moonblast|p1a: Whim",
        "|upkeep\n|turn|2",
        "|win|A",
    )
    g = D.build_game(log, TABLE)
    obs = [o for s in g.states["p1"] for o in s["observations"]]
    assert {
        "turn": 1,
        "weather": None,
        "fields": [],
        "side_conditions": ["p1:tailwind"],
    } in obs


@pytest.mark.parametrize("tag", sorted(LOGS))
def test_on_real_games_the_boards_match_the_stored_states(tag):
    g = D.build_game(LOGS[tag], EMPTY)
    for role in ("p1", "p2"):
        stored = json.loads(
            (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
        )
        result = D.compare_with_stored(g, role, stored)
        assert result.compared > 0
        assert result.mismatched == 0, result.examples


@pytest.mark.parametrize("tag", sorted(LOGS))
def test_on_real_games_logreaders_decisions_are_a_subset_of_ours(tag):
    g = D.build_game(LOGS[tag], EMPTY)
    for role in ("p1", "p2"):
        stored = json.loads(
            (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
        )
        ours = [
            (s["turn"])
            for s, r in zip(g.states[role], g.recorded[role])
            if r and s["turn"] > 0
        ]
        theirs = [s["turn"] for s in stored[:-1] if s["turn"] > 0]
        assert ours == theirs
