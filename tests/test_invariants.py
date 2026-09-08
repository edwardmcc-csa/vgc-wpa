"""Property tests over parsed battles, checked against wpa.state.BattleState.

Runs against three real battle logs (tests/fixtures/sample_battles.json) so
the properties are checked on actual parser output, not synthetic data.
wpa/state.py does not exist yet; this test is written first and is expected
to fail on import.

Note on ordering: Week 1 relaxed "turn numbers strictly increase" to "turn
numbers never decrease", correctly, because DEFINITIONS #6 allows multiple
decision points per game turn (team preview, lead selection, a forced
switch after a faint) - the strict version would fail on those, which
aren't bugs. But "never decrease" alone can't catch a stuck counter: a
parser bug that repeats the same turn forever would still pass it. Week 3
Task 5 tightens this to what the dispatch actually wants: the pair
(turn, decision_index) strictly increases lexicographically - see
test_turn_decision_index_pair_strictly_increases.
"""

import pytest

from wpa.state import parse_battle_states

ROLES = ["p1", "p2"]


def _all_tag_role_pairs(sample_battles):
    return [(tag, role) for tag in sample_battles for role in ROLES]


@pytest.fixture(params=None)
def parsed_battle(request, sample_battles, reader_loop):
    tag, role = request.param
    _, log = sample_battles[tag]
    return parse_battle_states(tag, log, role, loop=reader_loop)


def pytest_generate_tests(metafunc):
    if "parsed_battle" in metafunc.fixturenames:
        import json
        from pathlib import Path

        fixture_path = Path(__file__).parent / "fixtures" / "sample_battles.json"
        sample_battles = json.loads(fixture_path.read_text(encoding="utf-8"))
        pairs = _all_tag_role_pairs(sample_battles)
        metafunc.parametrize(
            "parsed_battle",
            pairs,
            indirect=True,
            ids=[f"{tag}-{role}" for tag, role in pairs],
        )


def test_hp_never_negative(parsed_battle):
    for state in parsed_battle:
        for mon in [*state.our_pokemon, *state.opp_pokemon]:
            assert mon.hp_fraction >= 0.0


def test_turn_decision_index_pair_strictly_increases(parsed_battle):
    pairs = [(state.turn, state.decision_index) for state in parsed_battle]
    assert pairs == sorted(pairs)
    assert len(set(pairs)) == len(pairs), (
        "no two states may share a (turn, decision_index) pair"
    )


def test_no_fainted_pokemon_is_active(parsed_battle):
    for state in parsed_battle:
        for mon in [*state.our_pokemon, *state.opp_pokemon]:
            assert not (mon.fainted and mon.active)


def test_exactly_one_outcome_recorded(parsed_battle):
    outcomes = [state.outcome for state in parsed_battle if state.outcome is not None]
    assert len(outcomes) == 1
    assert outcomes[0] in (True, False)
