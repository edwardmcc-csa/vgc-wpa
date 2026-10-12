"""Full-corpus batch driver for wpa's own BattleState schema (Week 3 Task 8
- "the re-parse"). Run once Tasks 3, 4, 5 and 10 are merged and green.

Mirrors vgc_bench.logs2trajs's own worker-pool pattern - one asyncio event
loop per worker process, reused across battles (`_init_worker_loop`) - but
writes wpa's own, much smaller BattleState records instead of vgc-bench's
packed float Trajectory (see docs/DATA-FOOTPRINT.md for why that's a very
different size). Streams one battle's output to disk as soon as that
battle finishes, rather than accumulating a whole file's results in memory
first - vgc-bench's own documented memory ceiling (docs/RUNBOOK.md #3)
comes from doing exactly that with a format 80x larger than this one, and
this design doesn't reproduce it. Not a patch to vgc-bench's own code -
a different, smaller data shape, sidestepping the problem rather than
fixing it upstream.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread

from wpa.state import parse_battle_states

_LOOP: asyncio.AbstractEventLoop | None = None


def _init_worker_loop() -> None:
    global _LOOP
    _LOOP = asyncio.new_event_loop()
    Thread(target=_LOOP.run_forever, daemon=True).start()


@dataclass
class ParseResult:
    tag: str
    role: str
    states: list[dict] | None
    error_type: str | None
    error_message: str | None


def _parse_one(tag: str, log: str, role: str) -> ParseResult:
    assert _LOOP is not None
    try:
        states = parse_battle_states(tag, log, role, _LOOP)
        return ParseResult(tag, role, [s.to_dict() for s in states], None, None)
    except Exception as e:
        return ParseResult(tag, role, None, type(e).__name__, str(e))


@dataclass
class ReparseStats:
    attempted: int = 0
    succeeded: int = 0
    failed: list[tuple[str, str, str | None, str | None]] = field(default_factory=list)
    bo3_states_seen: int = 0
    bo3_missing_set_id: int = 0
    bo3_missing_game_index: int = 0
    bo3_missing_score: int = 0
    wall_clock_seconds: float = 0.0
    bytes_written: int = 0

    def merge(self, other: "ReparseStats") -> None:
        self.attempted += other.attempted
        self.succeeded += other.succeeded
        self.failed += other.failed
        self.bo3_states_seen += other.bo3_states_seen
        self.bo3_missing_set_id += other.bo3_missing_set_id
        self.bo3_missing_game_index += other.bo3_missing_game_index
        self.bo3_missing_score += other.bo3_missing_score
        self.bytes_written += other.bytes_written


def process_logs_dict(
    logs: dict[str, tuple[str, str]], executor: ProcessPoolExecutor, out_dir: Path
) -> ReparseStats:
    """Parse every (tag, role) pair in `logs` and write each successful
    result to `out_dir` immediately, one file per battle-role. Pure of the
    filesystem layout of battle_logs/ itself, so it's testable against a
    small in-memory dict instead of the full corpus.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = ReparseStats()
    futures = [
        executor.submit(_parse_one, tag, log, role)
        for tag, (_, log) in logs.items()
        for role in ("p1", "p2")
    ]
    for future in as_completed(futures):
        result = future.result()
        stats.attempted += 1
        if result.states is None:
            stats.failed.append(
                (result.tag, result.role, result.error_type, result.error_message)
            )
            continue
        stats.succeeded += 1
        if "bo3" in result.tag:
            for state_dict in result.states:
                stats.bo3_states_seen += 1
                if state_dict["set_id"] is None:
                    stats.bo3_missing_set_id += 1
                if state_dict["game_index"] is None:
                    stats.bo3_missing_game_index += 1
                if state_dict["set_score_entering_game"] is None:
                    stats.bo3_missing_score += 1
        out_path = out_dir / f"{result.tag}-{result.role}.json"
        text = json.dumps(result.states)
        out_path.write_text(text, encoding="utf-8")
        stats.bytes_written += len(text.encode("utf-8"))
    return stats


def run_reparse(battle_logs_dir: Path, out_dir: Path, num_workers: int) -> ReparseStats:
    total = ReparseStats()
    start = time.time()
    with ProcessPoolExecutor(
        max_workers=num_workers, initializer=_init_worker_loop
    ) as executor:
        for logs_file in sorted(battle_logs_dir.glob("*.json")):
            with logs_file.open(encoding="utf-8") as f:
                logs = json.load(f)
            print(f"parsing {len(logs)} {logs_file.stem} logs...", flush=True)
            file_stats = process_logs_dict(logs, executor, out_dir)
            total.merge(file_stats)
            print(
                f"  {file_stats.succeeded}/{file_stats.attempted} succeeded, "
                f"{len(file_stats.failed)} failed",
                flush=True,
            )
    total.wall_clock_seconds = time.time() - start
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--battle_logs_dir", type=Path, default=Path("battle_logs"))
    parser.add_argument("--out_dir", type=Path, default=Path("wpa_states"))
    args = parser.parse_args()

    stats = run_reparse(args.battle_logs_dir, args.out_dir, args.num_workers)

    print()
    print("=== wpa re-parse summary ===")
    print(f"attempted: {stats.attempted}")
    print(f"succeeded: {stats.succeeded}")
    print(f"failed: {len(stats.failed)}")
    for tag, role, error_type, message in stats.failed:
        print(f"  {tag} {role}: {error_type}: {message}")
    print(f"bo3 states seen: {stats.bo3_states_seen}")
    print(f"bo3 states missing set_id: {stats.bo3_missing_set_id}")
    print(f"bo3 states missing game_index: {stats.bo3_missing_game_index}")
    print(f"bo3 states missing score: {stats.bo3_missing_score}")
    print(f"wall clock: {stats.wall_clock_seconds:.1f}s")
    print(f"bytes written: {stats.bytes_written} ({stats.bytes_written / 1e9:.2f}GB)")


if __name__ == "__main__":
    main()
