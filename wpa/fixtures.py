"""Saves and loads golden battle fixtures: a raw replay log plus its
per-turn states, packaged as one self-contained file.

Additive only: reuses wpa.state's existing replay adapter, no vgc-bench code
touched. Backs tests/fixtures/battles/ (Week 2 Task 5) and the "regenerate
fixtures" section of docs/RUNBOOK.md.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from wpa.state import BattleState, parse_battle_states


@dataclass(frozen=True)
class BattleFixture:
    """One golden battle: its raw log, and the states parsed from it."""

    tag: str
    timestamp: int
    role: str
    log: str
    states: tuple[BattleState, ...]

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "timestamp": self.timestamp,
            "role": self.role,
            "log": self.log,
            "states": [s.to_dict() for s in self.states],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BattleFixture":
        return cls(
            tag=d["tag"],
            timestamp=d["timestamp"],
            role=d["role"],
            log=d["log"],
            states=tuple(BattleState.from_dict(s) for s in d["states"]),
        )


def build_fixture(
    tag: str, timestamp: int, role: str, log: str, loop: asyncio.AbstractEventLoop
) -> BattleFixture:
    """Compute per-turn states for a raw log via the same replay adapter
    Week 1's invariant tests use, and package it with the log as one
    self-contained fixture."""
    states = parse_battle_states(tag, log, role, loop)
    return BattleFixture(
        tag=tag, timestamp=timestamp, role=role, log=log, states=tuple(states)
    )


def save_fixture(fixture: BattleFixture, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(fixture.to_dict()), encoding="utf-8")
    return path


def load_fixture(path: Path) -> BattleFixture:
    return BattleFixture.from_dict(json.loads(path.read_text(encoding="utf-8")))
