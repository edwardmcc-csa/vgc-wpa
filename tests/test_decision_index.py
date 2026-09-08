"""Tightens Week 1's relaxed "turn numbers never decrease" invariant to
what the dispatch actually wants: the pair (turn, decision_index) strictly
increases lexicographically. The relaxed version was correct given
DEFINITIONS #6 (a game turn can contain multiple decision points - team
preview, lead selection, a forced switch after a faint), but it can't
catch a stuck counter; decision_index is the missing dimension that lets
consecutive same-turn states still be ordered.

wpa/state.py doesn't yet have a decision_index field or
assign_decision_indices; written first and expected to fail.
"""

from tests.test_battle_completes import requires_server
from wpa.battle import capture_live_states
from wpa.state import BattleState, PokemonState, assign_decision_indices

_MON = PokemonState(species="pikachu", hp_fraction=1.0, fainted=False, active=True)


def _state(turn: int) -> BattleState:
    return BattleState(
        turn=turn, our_pokemon=(_MON,), opp_pokemon=(_MON,), outcome=None
    )


def test_decision_index_defaults_to_zero():
    assert _state(1).decision_index == 0


def test_decision_index_increments_within_a_repeated_turn():
    states = assign_decision_indices([_state(1), _state(1), _state(1)])
    assert [s.decision_index for s in states] == [0, 1, 2]


def test_decision_index_resets_when_turn_advances():
    states = assign_decision_indices([_state(1), _state(1), _state(2), _state(2)])
    assert [(s.turn, s.decision_index) for s in states] == [
        (1, 0),
        (1, 1),
        (2, 0),
        (2, 1),
    ]


def test_turn_decision_index_pair_strictly_increases_lexicographically():
    raw_turns = [1, 1, 1, 2, 3, 3]
    states = assign_decision_indices([_state(t) for t in raw_turns])
    pairs = [(s.turn, s.decision_index) for s in states]
    assert pairs == sorted(pairs)
    assert len(set(pairs)) == len(pairs), "no two states may share a (turn, index) pair"


@requires_server
def test_invariant_holds_on_live_captured_states_too():
    # Dispatch: "confirm the invariant holds on both the replay corpus and
    # the Week 2 live fixtures." A live bo3 set is the harder case - it's
    # where a same-turn forced switch is most likely to actually occur,
    # and where multiple trajectories (one per game) get assigned
    # decision_index independently before being combined into one list.
    states = capture_live_states(n_simple=3, n_bo3_sets=1, run_id=501)
    assert len(states) >= 4

    # Group consecutive states back into per-trajectory runs (a new
    # trajectory starts whenever decision_index resets to 0 at turn 1,
    # or more generally whenever the running pair would otherwise go
    # backwards) and check the invariant within each - concatenated
    # trajectories are expected to have unrelated (turn, decision_index)
    # sequences at their boundaries, so the pair only strictly increases
    # *within* one trajectory, not across all of them concatenated.
    trajectories: list[list[BattleState]] = []
    for state in states:
        if trajectories and state.turn == 1 and state.decision_index == 0:
            trajectories.append([state])
        elif trajectories:
            trajectories[-1].append(state)
        else:
            trajectories.append([state])

    assert len(trajectories) >= 2, "expected multiple separate trajectories"
    for trajectory in trajectories:
        pairs = [(s.turn, s.decision_index) for s in trajectory]
        assert pairs == sorted(pairs)
        assert len(set(pairs)) == len(pairs)
