"""Shared fixtures for wpa/ tests.

Mirrors the reader_loop pattern already used in unit_tests/test_logs2trajs.py
so LogReader (imported unmodified from vgc_bench.logs2trajs) can replay logs
outside of the multiprocessing worker pool it normally runs in.
"""

import asyncio
import json
from pathlib import Path
from threading import Thread

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_battles.json"


@pytest.fixture(scope="session")
def sample_battles() -> dict[str, tuple[str, str]]:
    """Three real battle logs (regmb) checked in for hermetic, offline tests."""
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def reader_loop():
    """Event loop for LogReader, mimicking vgc_bench.logs2trajs._init_worker_loop."""
    loop = asyncio.new_event_loop()
    thread = Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
