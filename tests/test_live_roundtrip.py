"""Live poke-env battle states convert into our schema, round-trip through
serialization unchanged, and share exactly the same schema the replay path
(Week 1) uses - one representation, not two.

Also exercises the best-of-3 set/game/score schema fields folded in from the
DEFINITIONS.md #11.6 / #13 investigation: captures a full bo3 set live,
where score-entering-the-game is always fully derivable (no historical gaps
like the scraped corpus has).

Deliberately one live capture, not several: repeated top-level live-battle
calls within one process were found to hang indefinitely (near-zero CPU, no
exception raised) after the second or third such call, even though each
succeeds every time run in isolation - reproduced directly before writing
this around it, and reported as a real finding rather than worked around
silently (see the Week 2 Task 4 report). Consolidating into one call here
both avoids that and is simply less wasteful than four separate connections
for what one battle set already covers.

wpa/state.py doesn't yet capture live battle state or bo3 set context, and
wpa/battle.py doesn't yet have capture_live_states; written first and
expected to fail.
"""

import dataclasses

from tests.test_battle_completes import requires_server
from wpa.battle import capture_live_states
from wpa.state import BattleState, PokemonState, parse_battle_states


@requires_server
def test_live_capture_covers_simple_and_bo3_battles():
    states = capture_live_states(n_simple=8, n_bo3_sets=1, run_id=401)

    assert len(states) >= 10
    assert all(isinstance(s, BattleState) for s in states)

    simple_states = [s for s in states if s.set_id is None]
    bo3_states = [s for s in states if s.set_id is not None]
    assert simple_states, "expected some simple-battle states"
    assert bo3_states, "expected some bo3 states"

    for s in simple_states:
        assert s.game_index is None
        assert s.set_score_entering_game is None

    set_ids = {s.set_id for s in bo3_states}
    assert len(set_ids) == 1, "one bo3 set should carry exactly one set id"

    for s in bo3_states:
        assert s.game_index in (1, 2, 3)
        # Live: we play the whole set ourselves, so unlike the historical
        # corpus (see docs/DEFINITIONS.md #11.6 investigation), the score
        # entering every game is always known - no gaps.
        assert s.set_score_entering_game is not None
        if s.game_index == 1:
            assert s.set_score_entering_game == (0, 0)
        if s.game_index == 3:
            assert s.set_score_entering_game == (1, 1)


def test_state_round_trips_through_dict_unchanged():
    original = BattleState(
        turn=5,
        our_pokemon=(PokemonState("Incineroar", 0.42, False, True),),
        opp_pokemon=(PokemonState("Sinistcha", 1.0, False, False),),
        outcome=None,
        set_id="gen9championsvgc2026regmabo3-1234",
        game_index=2,
        set_score_entering_game=(0, 1),
    )

    restored = BattleState.from_dict(original.to_dict())

    assert restored == original


def test_live_and_replay_paths_produce_the_same_schema(sample_battles, reader_loop):
    tag, (_, log) = next(iter(sample_battles.items()))
    replay_states = parse_battle_states(tag, log, "p1", reader_loop)

    assert replay_states
    replay_state = replay_states[0]

    assert type(replay_state) is BattleState
    # Same field set means the same schema - a live-captured BattleState and
    # a replay-captured one are structurally interchangeable, not two
    # divergent representations that happen to share a name.
    assert {f.name for f in dataclasses.fields(replay_state)} == {
        "turn",
        "our_pokemon",
        "opp_pokemon",
        "outcome",
        "set_id",
        "game_index",
        "set_score_entering_game",
        "decision_index",
    }
