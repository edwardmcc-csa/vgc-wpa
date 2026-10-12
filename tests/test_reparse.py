"""Week 3 Task 8: the full-corpus re-parse driver (wpa/reparse.py).

Exercised here against small, committed fixtures rather than the real
601MB battle_logs/ corpus - hermetic, like every other test this week.
The actual full-corpus run is a one-time operational step (see the Task 8
report), not something CI re-runs.
"""

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from wpa.reparse import _init_worker_loop, process_logs_dict

SAMPLE_BATTLES = Path(__file__).parent / "fixtures" / "sample_battles.json"
KNOWN_FAILURES = Path(__file__).parent / "fixtures" / "known_parser_failures.json"
BO3_SAMPLE = Path(__file__).parent / "fixtures" / "bo3_sample_regmabo3.json"


@pytest.fixture
def executor():
    with ProcessPoolExecutor(max_workers=2, initializer=_init_worker_loop) as ex:
        yield ex


def _load(path: Path, limit: int | None = None) -> dict[str, tuple[str, str]]:
    with path.open(encoding="utf-8") as f:
        d = json.load(f)
    if limit is not None:
        d = dict(list(d.items())[:limit])
    return d


def test_successful_battles_are_written_to_disk(executor, tmp_path):
    logs = _load(SAMPLE_BATTLES)
    stats = process_logs_dict(logs, executor, tmp_path)

    assert stats.attempted == len(logs) * 2
    assert stats.succeeded == stats.attempted
    assert not stats.failed

    written = list(tmp_path.glob("*.json"))
    assert len(written) == stats.succeeded
    for path in written:
        states = json.loads(path.read_text(encoding="utf-8"))
        assert states, f"{path} has no states"


def test_known_failures_are_reported_not_crashed(executor, tmp_path):
    with KNOWN_FAILURES.open(encoding="utf-8") as f:
        fixture = json.load(f)
    logs = {tag: (info["timestamp"], info["log"]) for tag, info in fixture.items()}

    stats = process_logs_dict(logs, executor, tmp_path)

    assert stats.attempted == len(logs) * 2
    # Unlike vgc_bench.logs2trajs.process_log (Task 6), parse_battle_states
    # never calls the |win|-line lookup that 4 of the 6 known failures trip
    # - it doesn't do winner/rating filtering at all. So only the 2
    # AssertionError-at-follow_log cases apply here; this is a real,
    # narrower number than Task 6's fixture, not a bug in either.
    failed_tags = {(tag, role) for tag, role, _, _ in stats.failed}
    assert failed_tags == {
        ("gen9championsvgc2026regma-2617076884", "p1"),
        ("gen9championsvgc2026regma-2617076884", "p2"),
    }
    assert all(error_type == "AssertionError" for _, _, error_type, _ in stats.failed)
    assert stats.succeeded == stats.attempted - 2


def test_bo3_fields_populated_throughout_a_sample(executor, tmp_path):
    logs = _load(BO3_SAMPLE, limit=20)
    stats = process_logs_dict(logs, executor, tmp_path)

    assert stats.succeeded > 0
    assert stats.bo3_states_seen > 0
    assert stats.bo3_missing_set_id == 0
    assert stats.bo3_missing_game_index == 0
    # Game 2's score can be legitimately unrecoverable if that set's game 1
    # log is missing from the corpus (documented in BattleState's own
    # docstring) - not expected in a random 20-battle sample this small,
    # but not asserted to zero either, since it's a documented real gap.
