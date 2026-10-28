"""Leak-proof train / validation / test splits (Week 4 Task 2).

docs/DEFINITIONS.md section 13: split by set, never by trajectory, game or
player; section 15: inside each format. A leaky split does not announce
itself, it silently turns every calibration number into a false claim.

How a file is assigned
----------------------
* The unit that is never divided is the **set id** when a game has one, the
  **battle tag** when it does not. A file's kind (single or best-of-three)
  is not the test: 1,281 real best-of-three sets live in the single log
  files. Partial sets (one game on file) are still sets.
* Both player perspectives of a game are the same unit, so they always land
  together.
* Units that share an exact team pairing are grouped, transitively, and a
  group is never divided. A pairing is the unordered pair of the two
  six-species teams (taken from the first state of each file: the state
  carries species only, so this is coarser than a full team sheet, which
  can only group more together, never less). Without this, the same
  matchup played in several sets would sit on both sides of a boundary.
* Grouping happens inside each format. One format's data never changes
  another format's assignments.
* A group's split is a hash of (salt, format, the group's smallest unit id).
  It uses sha256, not Python's hash(), so it is identical across runs,
  machines, input orders and PYTHONHASHSEED. New data does not move a group
  that is unchanged. The cost: proportions are met on average, not exactly.
* Best-of-three files with no set information at all (the one best-of-5
  match in the corpus, 71 states) are dropped and counted, never guessed.

Run as `python -m wpa.splits` to print the split report for wpa_states/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from wpa.archetypes import DEFAULT_MIN_SHARED, build_archetypes, check_min_shared
from wpa.formats import KIND_BO3, format_of, kind_of, parse_state_filename

SPLITS = ("train", "validation", "test")
DEFAULT_PROPORTIONS = {"train": 0.8, "validation": 0.1, "test": 0.1}
DEFAULT_SALT = "wpa-splits-v1"


class CannotSplitError(ValueError):
    """A format has too little data to fill every split."""


@dataclass(frozen=True)
class GameFile:
    """What the splitter needs to know about one wpa_states file."""

    tag: str
    role: str
    set_id: str | None
    own_team: tuple[str, ...]
    opp_team: tuple[str, ...]
    n_states: int
    n_states_without_set: int
    """States lacking a set id in a best-of-three file; 0 for other kinds."""


@dataclass
class SplitCounts:
    units: int = 0
    games: int = 0
    files: int = 0
    states: int = 0


@dataclass
class GroupStats:
    groups: int = 0
    units: int = 0
    largest_group_units: int = 0


@dataclass
class ArchetypeStats:
    archetypes: int = 0
    held_out: int = 0
    sizes: list[int] = field(default_factory=list)
    """Units (sets or single games) touching each archetype, largest first."""
    largest: list[tuple[str, int]] = field(default_factory=list)
    """The five largest archetypes as (id, units)."""

    def top_share(self, n: int) -> float:
        total = sum(self.sizes)
        return sum(self.sizes[:n]) / total if total else 0.0

    def summary(self) -> dict:
        asc = sorted(self.sizes)
        return {
            "archetypes": self.archetypes,
            "held_out": self.held_out,
            "size_median": asc[len(asc) // 2] if asc else 0,
            "size_p90": asc[int(len(asc) * 0.9)] if asc else 0,
            "size_max": asc[-1] if asc else 0,
            "top5_share": self.top_share(5),
            "top20_share": self.top_share(20),
            "largest": [list(x) for x in self.largest],
        }


@dataclass
class SplitResult:
    proportions: dict[str, float]
    salt: str
    assignments: dict[tuple[str, str], str] = field(default_factory=dict)
    """(battle tag, role) -> 'train' | 'validation' | 'test'. Dropped files absent."""
    dropped_files: list[tuple[str, str]] = field(default_factory=list)
    dropped_states: int = 0
    counts: dict[str, dict[str, SplitCounts]] = field(default_factory=dict)
    group_stats: dict[str, GroupStats] = field(default_factory=dict)
    archetype_holdout: float | None = None
    min_shared: int | None = None
    held_out_archetypes: dict[str, frozenset[str]] = field(default_factory=dict)
    archetypes: dict[str, dict[tuple[str, ...], str]] = field(default_factory=dict)
    archetype_stats: dict[str, ArchetypeStats] = field(default_factory=dict)

    def to_dict(self) -> dict:
        games: dict[str, str] = {}
        for (tag, _role), split in sorted(self.assignments.items()):
            if games.setdefault(tag, split) != split:
                raise AssertionError(f"perspectives of {tag} were split apart")
        return {
            "proportions": self.proportions,
            "salt": self.salt,
            "dropped_files": [list(k) for k in sorted(self.dropped_files)],
            "dropped_states": self.dropped_states,
            "counts": {
                fmt: {s: vars(c) for s, c in by_split.items()}
                for fmt, by_split in self.counts.items()
            },
            "group_stats": {f: vars(g) for f, g in self.group_stats.items()},
            "archetype_holdout": self.archetype_holdout,
            "min_shared": self.min_shared,
            "archetype_stats": {
                f: a.summary() for f, a in self.archetype_stats.items()
            },
            "held_out_archetypes": {
                f: sorted(ids) for f, ids in self.held_out_archetypes.items()
            },
            "games": games,
        }

    def describe(self) -> str:
        props = ", ".join(f"{s} {self.proportions[s]:.2f}" for s in SPLITS)
        lines = [
            "=== wpa splits ===",
            f"proportions: {props} (salt {self.salt})",
            f"dropped: {len(self.dropped_files)} files, {self.dropped_states} states "
            "(best-of-three files with no set information)",
        ]
        for fmt in sorted(self.counts):
            lines.append(f"{fmt}:")
            total_units = sum(c.units for c in self.counts[fmt].values()) or 1
            for s in SPLITS:
                c = self.counts[fmt][s]
                lines.append(
                    f"  {s:<10} {c.units:>6} units ({c.units / total_units:5.1%}), "
                    f"{c.games:>6} games, {c.files:>6} files, {c.states:>8} states"
                )
            g = self.group_stats[fmt]
            lines.append(
                f"  independent groups: {g.groups} (of {g.units} units); "
                f"largest group: {g.largest_group_units} units"
            )
            a = self.archetype_stats.get(fmt)
            if a is not None:
                m = a.summary()
                lines.append(
                    f"  archetypes: {a.archetypes} (leader clustering, at least "
                    f"{self.min_shared} of 6 species shared); {a.held_out} held out "
                    f"({a.held_out / a.archetypes:.1%}); the test split is every "
                    "game touching a held-out archetype"
                )
                lines.append(
                    f"  archetype size in units: median {m['size_median']}, "
                    f"90th percentile {m['size_p90']}, largest {m['size_max']}; "
                    f"the 5 largest cover {m['top5_share']:.1%} and the 20 largest "
                    f"{m['top20_share']:.1%} of archetype appearances"
                )
        return "\n".join(lines)


def _validate_proportions(proportions: dict[str, float]) -> dict[str, float]:
    if set(proportions) != set(SPLITS):
        raise ValueError(f"proportions must have exactly the keys {list(SPLITS)}")
    if any(p < 0 for p in proportions.values()):
        raise ValueError("proportions must not be negative")
    if abs(sum(proportions.values()) - 1.0) > 1e-9:
        raise ValueError(f"proportions must sum to 1, got {sum(proportions.values())}")
    return dict(proportions)


def _bucket(salt: str, fmt: str, group_id: str) -> float:
    digest = hashlib.sha256(f"{salt}|{fmt}|{group_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _split_for(bucket: float, proportions: dict[str, float]) -> str:
    cumulative = 0.0
    for split in SPLITS:
        cumulative += proportions[split]
        if proportions[split] > 0 and bucket < cumulative:
            return split
    # float rounding at the very top of the range
    return [s for s in SPLITS if proportions[s] > 0][-1]


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def assign_splits(
    files,
    proportions: dict[str, float] | None = None,
    salt: str = DEFAULT_SALT,
    require_non_empty: bool = True,
    archetype_holdout: float | None = None,
    min_shared: int = DEFAULT_MIN_SHARED,
) -> SplitResult:
    """Assign every kept file to train, validation or test. See module docstring.

    With `archetype_holdout` (a fraction strictly between 0 and 1) the test
    split becomes the archetype hold-out: that fraction of each format's
    archetypes (chosen by hash) is held out, and every game touching one of
    them goes to test. Everything else is split into train and validation in
    the ratio of those two proportions; the test proportion is not used. A
    held-out archetype is therefore never seen in train or validation, while
    its opponent may be a familiar archetype. See wpa/archetypes.py for the
    (proposed) archetype definition.
    """
    props = _validate_proportions(
        DEFAULT_PROPORTIONS if proportions is None else proportions
    )
    remainder_props: dict[str, float] = {}
    if archetype_holdout is not None:
        if (
            isinstance(archetype_holdout, bool)
            or not isinstance(archetype_holdout, (int, float))
            or not 0 < archetype_holdout < 1
        ):
            raise ValueError(
                "archetype_holdout must be a fraction strictly between 0 and 1, "
                f"got {archetype_holdout!r}"
            )
        check_min_shared(min_shared)
        if props["train"] + props["validation"] <= 0:
            raise ValueError("train and validation proportions cannot both be zero")
        rest = props["train"] + props["validation"]
        remainder_props = {
            "train": props["train"] / rest,
            "validation": props["validation"] / rest,
            "test": 0.0,
        }
    result = SplitResult(proportions=props, salt=salt)
    if archetype_holdout is not None:
        result.archetype_holdout = archetype_holdout
        result.min_shared = min_shared

    kept: dict[str, list[GameFile]] = {}  # format -> files
    for f in files:
        fmt = format_of(f.tag)  # raises UnknownFormatError, never defaults
        if f.set_id is not None and format_of(f.set_id) != fmt:
            raise ValueError(
                f"set {f.set_id!r} has a game from a different format "
                f"({f.tag!r} is {fmt}); a set never spans formats"
            )
        if kind_of(f.tag) == KIND_BO3 and f.set_id is None:
            result.dropped_files.append((f.tag, f.role))
            result.dropped_states += f.n_states
            continue
        result.dropped_states += f.n_states_without_set
        kept.setdefault(fmt, []).append(f)

    too_small: dict[str, list[str]] = {}
    for fmt, fmt_files in sorted(kept.items()):
        unit_of = lambda f: f.set_id if f.set_id is not None else f.tag  # noqa: E731
        uf = _UnionFind()
        for f in fmt_files:
            pairing = tuple(sorted([f.own_team, f.opp_team]))
            uf.union(("unit", unit_of(f)), ("pairing", pairing))
        members: dict = {}
        for f in fmt_files:
            u = unit_of(f)
            members.setdefault(uf.find(("unit", u)), set()).add(u)
        group_id = {root: min(units) for root, units in members.items()}

        touches_held_out: set = set()
        if archetype_holdout is None:
            split_of_group = {
                root: _split_for(_bucket(salt, fmt, gid), props)
                for root, gid in group_id.items()
            }
        else:
            units_of_team: dict[tuple[str, ...], set[str]] = {}
            for f in fmt_files:
                for team in (f.own_team, f.opp_team):
                    units_of_team.setdefault(team, set()).add(unit_of(f))
            amap = build_archetypes(
                {t: len(u) for t, u in units_of_team.items()}, min_shared
            )
            ids = sorted(set(amap.values()))
            held = frozenset(
                a
                for a in ids
                if _bucket(salt, fmt, "archetype:" + a) < archetype_holdout
            )
            result.archetypes[fmt] = amap
            result.held_out_archetypes[fmt] = held
            units_of_arch: dict[str, set[str]] = {}
            for team, units in units_of_team.items():
                units_of_arch.setdefault(amap[team], set()).update(units)
            sizes = sorted((len(u) for u in units_of_arch.values()), reverse=True)
            result.archetype_stats[fmt] = ArchetypeStats(
                archetypes=len(ids),
                held_out=len(held),
                sizes=sizes,
                largest=sorted(
                    ((a, len(u)) for a, u in units_of_arch.items()),
                    key=lambda x: (-x[1], x[0]),
                )[:5],
            )
            for f in fmt_files:
                if {amap[f.own_team], amap[f.opp_team]} & held:
                    touches_held_out.add(uf.find(("unit", unit_of(f))))
            split_of_group = {
                root: "test"
                if root in touches_held_out
                else _split_for(_bucket(salt, fmt, gid), remainder_props)
                for root, gid in group_id.items()
            }

        by_split = {s: SplitCounts() for s in SPLITS}
        units_seen: set[str] = set()
        games_seen: set[str] = set()
        for f in fmt_files:
            u = unit_of(f)
            split = split_of_group[uf.find(("unit", u))]
            result.assignments[(f.tag, f.role)] = split
            c = by_split[split]
            c.files += 1
            c.states += f.n_states - f.n_states_without_set
            if u not in units_seen:
                units_seen.add(u)
                c.units += 1
            if f.tag not in games_seen:
                games_seen.add(f.tag)
                c.games += 1
        result.counts[fmt] = by_split
        result.group_stats[fmt] = GroupStats(
            groups=len(members),
            units=len(units_seen),
            largest_group_units=max(len(u) for u in members.values()),
        )
        if archetype_holdout is None:
            required = [s for s in SPLITS if props[s] > 0]
        else:
            required = ["test"] + [s for s in ("train", "validation") if props[s] > 0]
        empty = [s for s in required if by_split[s].units == 0]
        if empty:
            too_small[fmt] = empty

    if too_small and require_non_empty:
        what = "archetypes" if archetype_holdout is not None else "groups of games"
        parts = [
            f"{fmt}: {result.group_stats[fmt].groups} independent group(s) of games"
            + (
                f" in {result.archetype_stats[fmt].archetypes} archetype(s)"
                if archetype_holdout is not None
                else ""
            )
            + f", nothing landed in {', '.join(empty)}"
            for fmt, empty in too_small.items()
        ]
        raise CannotSplitError(
            "cannot give every format its own train, validation and test sets; "
            + "; ".join(parts)
            + f". Too few independent {what} in that format. Models and metrics "
            "for it would have no honest hold-out."
        )
    return result


def scan_game_file(path_str: str) -> GameFile:
    """Read one wpa_states file into a GameFile. Reads the whole file once."""
    path = Path(path_str)
    tag, role = parse_state_filename(path.name)
    kind = kind_of(tag)  # raises UnknownFormatError before any file is read
    states = json.loads(path.read_text(encoding="utf-8"))
    if not states:
        raise ValueError(f"{path.name}: file has no states")
    first = states[0]
    set_id = next((s["set_id"] for s in states if s["set_id"] is not None), None)
    without_set = (
        sum(1 for s in states if s["set_id"] is None) if kind == KIND_BO3 else 0
    )
    return GameFile(
        tag=tag,
        role=role,
        set_id=set_id,
        own_team=tuple(sorted(p["species"] for p in first["our_pokemon"])),
        opp_team=tuple(sorted(p["species"] for p in first["opp_pokemon"])),
        n_states=len(states),
        n_states_without_set=without_set,
    )


def split_directory(
    directory,
    proportions: dict[str, float] | None = None,
    num_workers: int = 4,
    salt: str = DEFAULT_SALT,
    require_non_empty: bool = True,
    archetype_holdout: float | None = None,
    min_shared: int = DEFAULT_MIN_SHARED,
) -> SplitResult:
    """Scan every state file in a directory and split them."""
    paths = sorted(
        str(Path(directory) / e.name)
        for e in os.scandir(directory)
        if e.name.endswith(".json")
    )
    if num_workers <= 1:
        scanned = list(map(scan_game_file, paths))
    else:
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            scanned = list(executor.map(scan_game_file, paths, chunksize=500))
    return assign_splits(
        scanned, proportions, salt, require_non_empty, archetype_holdout, min_shared
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--dir", type=Path, default=Path("wpa_states"))
    parser.add_argument("--num_workers", type=int, default=4)
    for s in SPLITS:
        parser.add_argument(f"--{s}", type=float, default=DEFAULT_PROPORTIONS[s])
    parser.add_argument("--salt", default=DEFAULT_SALT)
    parser.add_argument(
        "--archetype_holdout",
        type=float,
        help="hold out this fraction of team archetypes as the test split "
        "(PROPOSED definition; not for headline numbers until signed off)",
    )
    parser.add_argument("--min_shared", type=int, default=DEFAULT_MIN_SHARED)
    parser.add_argument("--out", type=Path, help="write the full assignment as JSON")
    args = parser.parse_args()

    result = split_directory(
        args.dir,
        {s: getattr(args, s) for s in SPLITS},
        args.num_workers,
        args.salt,
        archetype_holdout=args.archetype_holdout,
        min_shared=args.min_shared,
    )
    print(result.describe())
    if args.out:
        args.out.write_text(json.dumps(result.to_dict()), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
