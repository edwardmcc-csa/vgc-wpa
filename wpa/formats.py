"""Format tagging (Week 4 Task 1; docs/DEFINITIONS.md section 15).

Regulation M-A and Regulation M-B are two formats. Every battle tag maps to
exactly one format and one kind (a single game, or a game from a
best-of-three). Matching is on the whole log-file name, never a prefix:
"regma" is a prefix of "regmabo3" and they are different kinds.

The mapping is configuration (LOG_NAMES). Adding a third format is an edit
to that table, not to any model code. An unrecognised tag raises
UnknownFormatError; it is never defaulted to a format, because a silently
mis-tagged battle would put the wrong data in a format's training or test
set.

Run as `python -m wpa.formats` to print battles, sets and states per format
and kind for the re-parse output in wpa_states/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

FORMAT_MA = "regma"
FORMAT_MB = "regmb"
KIND_SINGLE = "single"
KIND_BO3 = "bo3"

# Log-file name (the part of a tag before the final "-<battle id>") ->
# (format, kind). Configuration, not logic.
LOG_NAMES: dict[str, tuple[str, str]] = {
    "gen9championsvgc2026regma": (FORMAT_MA, KIND_SINGLE),
    "gen9championsvgc2026regmabo3": (FORMAT_MA, KIND_BO3),
    "gen9championsvgc2026regmb": (FORMAT_MB, KIND_SINGLE),
    "gen9championsvgc2026regmbbo3": (FORMAT_MB, KIND_BO3),
}


class UnknownFormatError(ValueError):
    """A battle tag does not belong to any configured format."""


# '<log name>-<numeric id>', optionally followed by '-<password>'. Set ids of
# private-room games end in a password (11 of 48,347 in the corpus), e.g.
# 'gen9championsvgc2026regmabo3-2604921266-q4mk6d2nr63emwdihwxco5c8fi1lnacpw'.
# Nothing else is accepted, so a malformed tag still raises.
_TAG_RE = re.compile(r"^(?P<name>[a-z0-9]+)-\d+(?:-[a-z0-9]+)?$")


def _lookup(tag: str) -> tuple[str, str]:
    match = _TAG_RE.match(tag)
    if match is None or match.group("name") not in LOG_NAMES:
        raise UnknownFormatError(f"unrecognised battle tag: {tag!r}")
    return LOG_NAMES[match.group("name")]


def format_of(tag: str) -> str:
    """The format ('regma' or 'regmb') a battle tag or set id belongs to."""
    return _lookup(tag)[0]


def kind_of(tag: str) -> str:
    """'single' for a standalone game, 'bo3' for a best-of-three game."""
    return _lookup(tag)[1]


def parse_state_filename(filename: str) -> tuple[str, str]:
    """Split '<tag>-<role>.json' into (tag, role). Raises ValueError otherwise."""
    if not filename.endswith(".json"):
        raise ValueError(f"not a state file: {filename!r}")
    tag, sep, role = filename[: -len(".json")].rpartition("-")
    if not sep or role not in ("p1", "p2") or not tag:
        raise ValueError(f"not a state file: {filename!r}")
    return tag, role


@dataclass
class FormatCounts:
    battles: int = 0
    files: int = 0
    sets: int = 0
    states: int = 0


@dataclass
class FormatSummary:
    counts: dict[tuple[str, str], FormatCounts] = field(default_factory=dict)
    spanning_sets: list[tuple[str, list[str]]] = field(default_factory=list)
    bo3_states_without_set: int = 0


def _scan_file(path_str: str) -> tuple[str, str, int, str | None, int]:
    """(tag, kind, n_states, set_id, n_states_without_set) for one file."""
    path = Path(path_str)
    tag, _role = parse_state_filename(path.name)
    kind = kind_of(tag)  # raises UnknownFormatError before any file is read
    states = json.loads(path.read_text(encoding="utf-8"))
    set_id = next((s["set_id"] for s in states if s["set_id"] is not None), None)
    no_set = sum(1 for s in states if s["set_id"] is None)
    return tag, kind, len(states), set_id, no_set


def summarize_directory(directory: Path, num_workers: int = 4) -> FormatSummary:
    paths = sorted(
        str(Path(directory) / e.name)
        for e in os.scandir(directory)
        if e.name.endswith(".json")
    )
    if num_workers <= 1:
        results = map(_scan_file, paths)
    else:
        executor = ProcessPoolExecutor(max_workers=num_workers)
        results = executor.map(_scan_file, paths, chunksize=500)

    tags: dict[tuple[str, str], set[str]] = {}
    set_ids: dict[tuple[str, str], set[str]] = {}
    set_member_formats: dict[str, set[str]] = {}
    summary = FormatSummary()
    for tag, kind, n_states, set_id, no_set in results:
        key = (format_of(tag), kind)
        counts = summary.counts.setdefault(key, FormatCounts())
        counts.files += 1
        counts.states += n_states
        tags.setdefault(key, set()).add(tag)
        if kind == KIND_BO3:
            summary.bo3_states_without_set += no_set
        # A file's kind is not whether it has a set: 1,281 best-of-three sets
        # live in the single-game log files, so count sets for every kind.
        if set_id is not None:
            set_ids.setdefault(key, set()).add(set_id)
            formats = set_member_formats.setdefault(set_id, set())
            formats.add(format_of(tag))
            formats.add(format_of(set_id))
    for key, counts in summary.counts.items():
        counts.battles = len(tags[key])
        counts.sets = len(set_ids.get(key, ()))
    summary.spanning_sets = sorted(
        (sid, sorted(f)) for sid, f in set_member_formats.items() if len(f) > 1
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("wpa_states"))
    parser.add_argument("--num_workers", type=int, default=4)
    args = parser.parse_args()

    summary = summarize_directory(args.dir, args.num_workers)
    print("=== wpa formats ===")
    for (fmt, kind), c in sorted(summary.counts.items()):
        print(
            f"{fmt} {kind}: {c.battles} battles, {c.files} files, "
            f"{c.sets} sets, {c.states} states"
        )
    print(f"sets spanning more than one format: {len(summary.spanning_sets)}")
    for set_id, formats in summary.spanning_sets[:20]:
        print(f"  {set_id}: {formats}")
    print(f"bo3 states without set information: {summary.bo3_states_without_set}")


if __name__ == "__main__":
    main()
