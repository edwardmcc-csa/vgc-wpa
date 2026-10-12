"""Check that best-of-three set fields are populated across a re-parse's
output (Week 3 Task 8, "populated throughout, not just on a sample").

Run after `python -m wpa.reparse`:

    python -m wpa.check_set_fields

Reads every `*bo3*` file in `wpa_states/`, counts states missing `set_id`,
`game_index` or `set_score_entering_game`, and lists the affected files.
Read-only: it never modifies the re-parse output. Files that are not bo3
are single games and are not expected to carry set fields.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AffectedFile:
    file: str
    states_missing_any: int
    states_total: int
    missing_set_id: int
    missing_game_index: int
    missing_score: int


@dataclass
class ScanResult:
    bo3_files: int = 0
    bo3_states: int = 0
    missing_set_id: int = 0
    missing_game_index: int = 0
    missing_score: int = 0
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    affected: list[AffectedFile] = field(default_factory=list)


def _scan_file(path_str: str) -> tuple[str, int, AffectedFile | None, str | None]:
    path = Path(path_str)
    try:
        states = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # report, do not crash the whole scan
        return path.name, 0, None, f"{type(e).__name__}: {e}"
    no_set = sum(1 for s in states if s["set_id"] is None)
    no_game = sum(1 for s in states if s["game_index"] is None)
    no_score = sum(1 for s in states if s["set_score_entering_game"] is None)
    any_missing = sum(
        1
        for s in states
        if s["set_id"] is None
        or s["game_index"] is None
        or s["set_score_entering_game"] is None
    )
    affected = None
    if any_missing:
        affected = AffectedFile(
            path.name, any_missing, len(states), no_set, no_game, no_score
        )
    return path.name, len(states), affected, None


def scan_directory(directory: Path, num_workers: int = 4) -> ScanResult:
    result = ScanResult()
    paths = sorted(
        str(Path(directory) / e.name)
        for e in os.scandir(directory)
        if "bo3" in e.name and e.name.endswith(".json")
    )
    result.bo3_files = len(paths)
    if num_workers <= 1:
        outcomes = map(_scan_file, paths)
    else:
        executor = ProcessPoolExecutor(max_workers=num_workers)
        outcomes = executor.map(_scan_file, paths, chunksize=500)
    for name, n_states, affected, error in outcomes:
        if error:
            result.unreadable.append((name, error))
            continue
        result.bo3_states += n_states
        if affected:
            result.affected.append(affected)
            result.missing_set_id += affected.missing_set_id
            result.missing_game_index += affected.missing_game_index
            result.missing_score += affected.missing_score
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("wpa_states"))
    parser.add_argument("--num_workers", type=int, default=4)
    args = parser.parse_args()

    r = scan_directory(args.dir, args.num_workers)
    print("=== wpa set-field check ===")
    print(f"bo3 files scanned: {r.bo3_files}")
    print(f"bo3 states scanned: {r.bo3_states}")
    print(f"missing set_id: {r.missing_set_id}")
    print(f"missing game_index: {r.missing_game_index}")
    print(f"missing set_score_entering_game: {r.missing_score}")
    print(f"files with any missing field: {len(r.affected)}")
    print(f"unreadable files: {len(r.unreadable)}")
    for a in r.affected[:40]:
        print(
            f"  {a.file}: {a.states_missing_any}/{a.states_total} states "
            f"(set_id {a.missing_set_id}, game_index {a.missing_game_index}, "
            f"score {a.missing_score})"
        )
    if len(r.affected) > 40:
        print(f"  ... and {len(r.affected) - 40} more")
    for name, err in r.unreadable[:10]:
        print(f"  UNREADABLE {name}: {err}")


if __name__ == "__main__":
    main()
