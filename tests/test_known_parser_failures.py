"""Regression coverage for the known logs2trajs.py parse failures.

Week 1 found 6 (battle, role) pairs across the 88,905-battle corpus that
raise an exception in vgc_bench.logs2trajs.process_log (0.0034%). Week 1's
report claimed all six tripped the same assertion at logs2trajs.py:259.
This turned out to be inaccurate: only 2 of the 6 do. The other 4 come from
two separate battles (2 roles each) that raise ValueError at line 378
because log.index("|win|") fails - one is a genuine mutual-timeout tie
(no winner, so no |win| line), the other is a log that appears to be
truncated mid-battle.

This test locks in that corrected count and both failure modes as a
regression guard: if a future logs2trajs.py change fixes one of these,
or a future corpus re-parse finds new failures, this test will need a
deliberate update rather than silently drifting.
"""

import json
from pathlib import Path

import pytest

import vgc_bench.logs2trajs as logs2trajs
from vgc_bench.logs2trajs import process_log

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "known_parser_failures.json"

with open(FIXTURE_PATH, encoding="utf-8") as f:
    _KNOWN_FAILURES: dict[str, dict] = json.load(f)

_EXPECTED_ERROR_TYPES = {"AssertionError": AssertionError, "ValueError": ValueError}

_CASES = [
    (tag, role, info["error_type"])
    for tag, info in _KNOWN_FAILURES.items()
    for role in info["roles"]
]


def test_known_failure_count_is_exactly_six() -> None:
    assert len(_CASES) == 6
    assert len(_KNOWN_FAILURES) == 3


def test_known_failures_are_not_all_the_same_error_type() -> None:
    error_types = {info["error_type"] for info in _KNOWN_FAILURES.values()}
    assert error_types == {"AssertionError", "ValueError"}


@pytest.mark.parametrize("tag,role,error_type", _CASES)
def test_known_failure_still_fails_the_same_way(
    tag: str, role: str, error_type: str, reader_loop
) -> None:
    log = _KNOWN_FAILURES[tag]["log"]
    expected_exception = _EXPECTED_ERROR_TYPES[error_type]
    logs2trajs._READER_LOOP = reader_loop
    try:
        with pytest.raises(expected_exception):
            process_log(tag, log, role, min_rating=None, only_winner=False)
    finally:
        del logs2trajs._READER_LOOP
