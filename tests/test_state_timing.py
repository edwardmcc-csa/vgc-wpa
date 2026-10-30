"""Tests for wpa/state_timing.py (Week 5 Task 1): what a state knows.

A state is a snapshot taken when a player has to choose. Its `observations`
are the spread-revealing events of the *turn* it belongs to, hung on the last
decision of that turn. When a turn has only one decision (the start of the
turn), those events happen after the snapshot: they are the future.

These tests use plain dicts (the stored JSON form), so they need neither
poke_env nor the data folder. The three real games in tests/fixtures/w5 are
small copies of files from wpa_states/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wpa import state_timing as S

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
GAMES = sorted(FIXTURES.glob("*.json"))


def obs(turn, decision_index, category="move_order", **kw):
    return {
        "turn": turn,
        "decision_index": decision_index,
        "category": category,
        "actor": "p1a: A",
        "target": "p2a: B",
        "move": "Protect",
        **kw,
    }


def state(turn, d, observations=(), outcome=None, our=(1.0,), opp=(1.0,)):
    def side(hps):
        return [
            {
                "species": f"mon{i}",
                "hp_fraction": hp,
                "fainted": hp == 0,
                "active": True,
                "gimmick": None,
            }
            for i, hp in enumerate(hps)
        ]

    return {
        "turn": turn,
        "decision_index": d,
        "outcome": outcome,
        "our_pokemon": side(our),
        "opp_pokemon": side(opp),
        "observations": list(observations),
    }


def timeline():
    return [
        state(0, 0),
        state(0, 1, [obs(0, 1, "behavioral_tell")]),
        state(1, 0),  # start of turn 1
        state(1, 1, [obs(1, 1), obs(1, 1)]),  # forced switch after turn 1's moves
        state(2, 0, [obs(2, 0)]),  # start of turn 2, its only decision
        state(3, 0),
    ]


def test_turn_structure_lists_the_decisions_of_each_turn():
    assert S.turn_structure(timeline()) == {0: (0, 1), 1: (0, 1), 2: (0,), 3: (0,)}


def test_a_turn_with_one_decision_carries_events_from_after_that_decision():
    states = timeline()
    assert [S.carries_future_observations(states, k) for k in range(6)] == [
        False,  # no observations
        False,  # turn 0: leads were already chosen
        False,  # none attached
        False,  # forced switch, after the moves
        True,  # turn 2's moves are attached to the decision that precedes them
        False,
    ]


def test_usable_observations_come_from_earlier_turns_only():
    states = timeline()
    # the forced-switch decision of turn 1 may not use turn 1's own events
    assert S.usable_observations(states, 3) == [states[1]["observations"][0]]
    # turn 2's start sees everything from turns 0 and 1, none of turn 2
    got = S.usable_observations(states, 4)
    assert {(o["turn"]) for o in got} == {0, 1} and len(got) == 3
    # turn 3 sees turn 2's events too
    assert len(S.usable_observations(states, 5)) == 4


def test_usable_observations_ignore_everything_after_the_decision():
    states = timeline()
    for k in range(len(states)):
        assert S.usable_observations(states[: k + 1], k) == S.usable_observations(
            states, k
        )
        # and changing the future changes nothing
        altered = [dict(s) for s in states]
        for j in range(k + 1, len(altered)):
            altered[j]["observations"] = [obs(altered[j]["turn"], 0, move="Surf")]
        assert S.usable_observations(altered, k) == S.usable_observations(states, k)


def test_hp_evidence_says_whether_the_snapshot_is_after_the_events():
    after = state(
        1,
        1,
        [obs(1, 1, "damage", target="p2a: Mon0", hp_after=40.0, hp_expression="x")],
        opp=(0.4,),
    )
    before = state(
        2,
        0,
        [obs(2, 0, "damage", target="p2a: Mon0", hp_after=40.0, hp_expression="x")],
        opp=(1.0,),
    )
    assert S.hp_evidence(after, "p1") == "post"
    assert S.hp_evidence(before, "p1") == "pre"
    # the role decides which side "p2a: Mon0" is: from p2's file it is our own
    # Pokemon, still at full hit points in the snapshot
    assert S.hp_evidence(after, "p2") == "pre"
    assert S.hp_evidence(state(1, 0), "p1") is None


def test_decided_states_are_those_with_an_outcome():
    states = timeline() + [state(4, 0, outcome=True)]
    assert S.decided_indices(states) == [6]


def test_the_final_snapshot_is_a_terminal_marker_not_a_decision():
    states = timeline() + [state(4, 0, outcome=True)]
    assert S.terminal_index(states) == 6
    assert S.decision_indices(states) == [0, 1, 2, 3, 4, 5]


def test_a_loser_with_pokemon_left_means_the_game_ended_by_forfeit_or_timeout():
    won = state(4, 0, outcome=True, our=(0.5,), opp=(0.01, 0.0))
    lost = state(4, 0, outcome=False, our=(0.0, 0.0), opp=(1.0,))
    assert S.loser_has_pokemon_left(won)
    assert not S.loser_has_pokemon_left(lost)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def role_of(path):
    return path.stem.rsplit("-", 1)[1]


def test_three_real_games_are_available_for_these_checks():
    assert len(GAMES) == 6


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.name)
def test_on_real_games_snapshots_before_the_events_are_the_flagged_ones(path):
    states = load(path)
    role = role_of(path)
    for k, s in enumerate(states):
        if S.hp_evidence(s, role) == "pre":
            assert S.carries_future_observations(states, k), (path.name, k)


def test_real_games_do_contain_snapshots_taken_before_their_own_observations():
    seen = 0
    for path in GAMES:
        states = load(path)
        seen += sum(S.hp_evidence(s, role_of(path)) == "pre" for s in states)
    assert seen > 0


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.name)
def test_on_real_games_usable_observations_never_include_the_current_turn(path):
    states = load(path)
    for k, s in enumerate(states):
        assert all(o["turn"] < s["turn"] for o in S.usable_observations(states, k))


@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.name)
def test_on_real_games_outcome_is_set_only_on_the_final_snapshot(path):
    states = load(path)
    assert S.decided_indices(states) == [len(states) - 1]
    assert S.terminal_index(states) == len(states) - 1
    assert isinstance(states[-1]["outcome"], bool)
    assert S.decision_indices(states) == list(range(len(states) - 1))


def test_one_real_game_ended_by_forfeit_with_the_losers_pokemon_still_standing():
    # regmb-2634168141: "Cello L. forfeited" in the raw log; the loser's last
    # Pokemon is at 1% hit points in the final snapshot.
    for role in ("p1", "p2"):
        states = load(FIXTURES / f"gen9championsvgc2026regmb-2634168141-{role}.json")
        assert S.loser_has_pokemon_left(states[-1])


def test_the_audit_counts_what_the_fixtures_show():
    audit = S.audit_files(GAMES)
    assert audit.files == 6
    assert audit.files_with_one_terminal_last == 6
    assert audit.forfeit_like == 2
    assert audit.states == sum(len(load(p)) for p in GAMES)
    assert audit.decision_states == audit.states - 6
    # every decision state with observations is either flagged or not; the
    # hit-point evidence agrees with the flag in all fixture cases
    assert audit.flagged_states > 0
    assert audit.pre_but_unflagged == 0
    text = audit.describe()
    assert "regma" in text and "regmb" in text and "regmabo3" in text


def test_hash_sampling_is_deterministic_and_proportional():
    names = [f"gen9championsvgc2026regma-{i}-p1.json" for i in range(2000)]
    a = [n for n in names if S.in_sample(n, 10)]
    b = [n for n in names if S.in_sample(n, 10)]
    assert a == b and 100 < len(a) < 300
    # both players of one game are sampled together
    assert S.in_sample("gen9championsvgc2026regma-5-p1.json", 10) == S.in_sample(
        "gen9championsvgc2026regma-5-p2.json", 10
    )
