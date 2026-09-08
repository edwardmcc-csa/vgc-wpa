"""Spread-revealing observation capture (Week 3 Task 10 / Amendment 1,
docs/DEFINITIONS.md #14).

Two of the 20 golden fixtures (Week 2 Task 5) are hand-checked here by
eye against their raw logs, per the task's own test list: focus_sash.json
(a clean case with faints, a resisted hit, an ability trigger, and a
Focus Sash pop - no residual/indirect faints) and sitrus_berry.json (adds
recovery events and a couple of faints not directly caused by the
preceding damage line, exercising the survival category separately from
the damage category's own `fainted` flag).
"""

import dataclasses
from pathlib import Path

import pytest

from wpa.fixtures import load_fixture
from wpa.observations import Observation, extract_observations
from wpa.state import BattleState, PokemonState, parse_battle_states

BATTLES_DIR = Path(__file__).parent / "fixtures" / "battles"

_IDENTIFIER_RE = r"^p[12][ab]: .+$"


def _parse(name: str, reader_loop) -> list[BattleState]:
    fx = load_fixture(BATTLES_DIR / name)
    return parse_battle_states(fx.tag, fx.log, fx.role, reader_loop)


@pytest.mark.parametrize(
    "name", ["focus_sash.json", "sitrus_berry.json", "multi_hit_move.json"]
)
def test_every_observation_matches_a_real_decision_point(name, reader_loop):
    states = _parse(name, reader_loop)
    known_points = {(s.turn, s.decision_index) for s in states}
    for s in states:
        for o in s.observations:
            assert (o.turn, o.decision_index) in known_points


@pytest.mark.parametrize(
    "name", ["focus_sash.json", "sitrus_berry.json", "multi_hit_move.json"]
)
def test_actor_and_target_identifiers_are_unambiguous(name, reader_loop):
    import re

    states = _parse(name, reader_loop)
    for s in states:
        for o in s.observations:
            if o.actor is not None:
                assert re.match(_IDENTIFIER_RE, o.actor), o.actor
            if o.target is not None:
                assert re.match(_IDENTIFIER_RE, o.target), o.target


@pytest.mark.parametrize(
    "name", ["focus_sash.json", "sitrus_berry.json", "multi_hit_move.json"]
)
def test_hp_expression_populated_whenever_hp_present(name, reader_loop):
    states = _parse(name, reader_loop)
    saw_hp_bearing = False
    for s in states:
        for o in s.observations:
            if o.hp_after is not None:
                saw_hp_bearing = True
                assert o.hp_expression is not None
                # See module docstring / docs/PARSE-FAILURES.md-style honesty:
                # the corpus is percentage-only, exhaustively checked, not a
                # guess - this is what "populated" resolves to here.
                assert o.hp_expression == "percentage"
    assert saw_hp_bearing, f"{name} should have at least one HP-bearing observation"


def test_observation_round_trips_through_dict_unchanged():
    original = Observation(
        turn=3,
        decision_index=1,
        category="damage",
        actor="p1a: Blaziken",
        target="p2b: Kingambit",
        move="Heat Wave",
        priority=0,
        sequence_index=2,
        hp_after=42.0,
        hp_expression="percentage",
        fainted=False,
        hit_multiple_targets=True,
        weather="SunnyDay",
        fields=("Trick Room",),
        side_conditions=("p2:Tailwind", "p1:Reflect"),
        tera_type=None,
        note=None,
    )

    restored = Observation.from_dict(original.to_dict())

    assert restored == original


def test_battle_state_with_observations_round_trips():
    original = BattleState(
        turn=2,
        our_pokemon=(PokemonState("Incineroar", 0.5, False, True),),
        opp_pokemon=(PokemonState("Sinistcha", 1.0, False, False),),
        outcome=None,
        decision_index=0,
        observations=(
            Observation(
                turn=2,
                decision_index=0,
                category="tera_activation",
                actor="p1a: Incineroar",
                target=None,
                tera_type="Fire",
            ),
        ),
    )

    restored = BattleState.from_dict(original.to_dict())

    assert restored == original


def test_same_schema_across_fixtures(reader_loop):
    # Same extraction code, same Observation dataclass, regardless of which
    # fixture (or which week it was recorded for) the log came from - one
    # representation, not per-battle special-casing.
    all_fields = None
    for name in ["focus_sash.json", "sitrus_berry.json", "bo3_game1.json"]:
        states = _parse(name, reader_loop)
        for s in states:
            for o in s.observations:
                fields = {f.name for f in dataclasses.fields(o)}
                if all_fields is None:
                    all_fields = fields
                assert fields == all_fields
    assert all_fields is not None


def test_tera_activation_is_extracted_even_though_absent_from_this_corpus():
    # Task 2 found Terastallization disabled format-wide (0/88,905 battles) -
    # so this category can't be hand-checked against a real fixture. Checked
    # directly against a synthetic snippet of real protocol syntax instead.
    log = "|turn|1\n|-terastallize|p1a: Incineroar|Fire\n|turn|2\n"
    states = [
        BattleState(
            turn=1, our_pokemon=(), opp_pokemon=(), outcome=None, decision_index=0
        )
    ]
    observations = extract_observations(log, states)
    tera_obs = [o for o in observations if o.category == "tera_activation"]
    assert len(tera_obs) == 1
    assert tera_obs[0].actor == "p1a: Incineroar"
    assert tera_obs[0].tera_type == "Fire"
    assert tera_obs[0].turn == 1
    assert tera_obs[0].decision_index == 0


def test_multi_target_move_flagged_but_multi_hit_single_target_move_is_not(reader_loop):
    # Clanging Scales|[spread] p1a,p1b hits two distinct Pokemon; Population
    # Bomb hits one Pokemon six times. Only the former should be flagged.
    states = _parse("multi_hit_move.json", reader_loop)
    observations = [o for s in states for o in s.observations]

    spread_hits = [o for o in observations if o.move == "Clanging Scales"]
    assert spread_hits
    assert all(o.hit_multiple_targets for o in spread_hits)

    multi_hit_same_target = [o for o in observations if o.move == "Population Bomb"]
    assert multi_hit_same_target
    assert all(o.hit_multiple_targets is False for o in multi_hit_same_target)


def test_focus_sash_hand_checked_counts(reader_loop):
    """Hand-verified against the raw log: 15 move_order (one per |move| line
    across 5 turns), 12 damage events, 2 behavioral tells (Stamina boost
    trigger, Focus Sash pop) - no recovery or standalone survival events in
    this battle (every faint is directly preceded by its own 0-fnt damage
    line, so it's covered by that damage observation's `fainted` flag, not
    a separate survival record)."""
    states = _parse("focus_sash.json", reader_loop)
    observations = [o for s in states for o in s.observations]

    by_category = {}
    for o in observations:
        by_category.setdefault(o.category, []).append(o)

    assert len(observations) == 29
    assert len(by_category.get("move_order", [])) == 15
    assert len(by_category.get("damage", [])) == 12
    assert len(by_category.get("behavioral_tell", [])) == 2
    assert "recovery" not in by_category
    assert "survival" not in by_category

    tells = {o.note for o in by_category["behavioral_tell"]}
    assert tells == {"ability_trigger:Stamina", "enditem:Focus Sash"}

    faints = [o for o in by_category["damage"] if o.fainted]
    assert len(faints) == 6


def test_sitrus_berry_hand_checked_counts(reader_loop):
    """Hand-verified against the raw log: adds recovery (Leftovers/Sitrus
    Berry/Hospitality heals) and 2 survival events - faints not directly
    caused by the immediately preceding damage line."""
    states = _parse("sitrus_berry.json", reader_loop)
    observations = [o for s in states for o in s.observations]

    by_category = {}
    for o in observations:
        by_category.setdefault(o.category, []).append(o)

    assert len(observations) == 66
    assert len(by_category.get("move_order", [])) == 32
    assert len(by_category.get("damage", [])) == 21
    assert len(by_category.get("recovery", [])) == 6
    assert len(by_category.get("survival", [])) == 2
    assert len(by_category.get("behavioral_tell", [])) == 5
