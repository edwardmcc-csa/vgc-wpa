"""Validates the curated golden-case corpus in tests/fixtures/battles/
(Week 2 Task 5): 20 fixtures, loadable, collectively covering the required
variety - checked against the actual computed BattleState fields, not just
filenames, so a future fixture swap that quietly loses a required property
gets caught here rather than at M3.
"""

from pathlib import Path

from wpa.fixtures import load_fixture

BATTLES_DIR = Path(__file__).parent / "fixtures" / "battles"


def _load_all():
    paths = sorted(BATTLES_DIR.glob("*.json"))
    return {p.stem: load_fixture(p) for p in paths}


def test_corpus_has_twenty_fixtures():
    fixtures = _load_all()
    assert len(fixtures) == 20


def test_every_fixture_loads_with_states():
    for name, fx in _load_all().items():
        assert fx.states, f"{name} has no states"


def test_corpus_includes_an_early_forfeit():
    fixtures = _load_all()
    forfeits = [
        (name, fx)
        for name, fx in fixtures.items()
        if "forfeit" in fx.log.lower() and fx.states[-1].turn <= 3
    ]
    assert forfeits, "expected at least one battle forfeited within the first 3 turns"


def test_corpus_includes_a_turn_or_time_limit_battle():
    fixtures = _load_all()
    long_ones = [
        (name, fx)
        for name, fx in fixtures.items()
        if "inactivity" in fx.log.lower() or fx.states[-1].turn >= 20
    ]
    assert long_ones, "expected at least one battle that ran to the format's limit"


def test_corpus_includes_a_mega_evolution():
    fixtures = _load_all()
    has_mega = any(
        mon.gimmick == "mega"
        for fx in fixtures.values()
        for s in fx.states
        for mon in [*s.our_pokemon, *s.opp_pokemon]
    )
    assert has_mega, (
        "expected at least one Mega Evolution - the format's actual gimmick, "
        "since Terastallization is disabled in M-A/M-B/M-C (see the Week 2 "
        "Task 5 report)"
    )


def test_corpus_includes_a_weather_or_terrain_setter():
    fixtures = _load_all()
    weather_or_terrain = [
        name
        for name, fx in fixtures.items()
        if "|-weather|" in fx.log or "|-fieldstart|" in fx.log
    ]
    assert weather_or_terrain, "expected at least one weather or terrain setter"


def test_corpus_includes_bo3_set_context():
    fixtures = _load_all()
    has_bo3 = any(s.set_id is not None for fx in fixtures.values() for s in fx.states)
    assert has_bo3, "expected at least one fixture carrying bo3 set context"
