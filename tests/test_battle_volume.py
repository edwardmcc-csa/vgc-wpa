"""Volume and stability: batches of random-vs-random battles, checked against
the Week 2 dispatch's failure-rate threshold (stop and report if more than
2 of 100 fail).

A small 10-battle run executes by default so CI stays fast. The full
100-battle run is available behind the `volume_full` marker, run explicitly
with `pytest -m volume_full`.

wpa/battle.py's run_battles does not exist yet; written first and expected
to fail.
"""

import pytest

from tests.test_battle_completes import requires_server
from wpa.battle import run_battles


@requires_server
def test_ten_battles_complete_without_crashing():
    result = run_battles(n=10, run_id=101)

    assert result.attempted == 10
    assert result.completed == 10
    assert result.crashes == []


@requires_server
@pytest.mark.volume_full
def test_hundred_battles_stay_within_dispatch_failure_threshold():
    result = run_battles(n=100, run_id=201)

    assert len(result.crashes) <= 2, (
        f"{len(result.crashes)} of 100 battles failed "
        f"(dispatch threshold: 2): {result.crashes}"
    )
