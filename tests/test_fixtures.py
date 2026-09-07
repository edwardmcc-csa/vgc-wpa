"""wpa.fixtures saves/loads golden battle fixtures (raw log + per-turn
states) as one self-contained file - the mechanism the 20 curated battles in
tests/fixtures/battles/ (Week 2 Task 5) are built from, and what
docs/RUNBOOK.md documents for regenerating them.

wpa/fixtures.py doesn't exist yet; written first and expected to fail.
"""

from wpa.fixtures import build_fixture, load_fixture, save_fixture


def test_build_save_load_round_trips_a_fixture(sample_battles, reader_loop, tmp_path):
    tag, (ts, log) = next(iter(sample_battles.items()))

    fixture = build_fixture(tag, ts, "p1", log, reader_loop)
    assert fixture.states

    path = save_fixture(fixture, tmp_path, "example")
    restored = load_fixture(path)

    assert restored == fixture
