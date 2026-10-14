"""Week 4 Task 2: leak-proof splits (wpa/splits.py).

DEFINITIONS section 13: split by set, never by trajectory, game or player,
and inside each format (section 15). A leaky split does not announce itself;
it silently turns every calibration number into a false claim. These tests
are the contract. If one of them can only be made to pass by weakening it,
stop and report instead.

The data here is synthetic and hermetic. A "unit" is the thing that must
never be divided: a whole best-of-three set, or a single game.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from wpa.formats import FORMAT_MA, FORMAT_MB, UnknownFormatError, format_of
from wpa.splits import (
    DEFAULT_PROPORTIONS,
    SPLITS,
    CannotSplitError,
    GameFile,
    assign_splits,
    scan_game_file,
    split_directory,
)

MA_SINGLE = "gen9championsvgc2026regma"
MA_BO3 = "gen9championsvgc2026regmabo3"
MB_SINGLE = "gen9championsvgc2026regmb"
MB_BO3 = "gen9championsvgc2026regmbbo3"

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Synthetic corpus builders
# --------------------------------------------------------------------------


def team(n: int) -> tuple[str, ...]:
    """A six-species team, unique to n."""
    return tuple(sorted(f"team{n}mon{i}" for i in range(6)))


def _game(tag, set_id, a, b, n_states=5, no_set=0):
    """Both player perspectives of one game: p1 plays team a, p2 plays team b."""
    return [
        GameFile(tag, "p1", set_id, a, b, n_states, no_set),
        GameFile(tag, "p2", set_id, b, a, n_states, no_set),
    ]


def single(log, battle_id, a, b):
    return _game(f"{log}-{battle_id}", None, a, b)


def game_tag(log, set_number, game_number):
    return f"{log}-{set_number}{game_number}"


def bo3(log, set_number, game_numbers, a, b, swap_sides_in_game=None):
    """One best-of-three set. Game ids are separate from the set id, as in the
    real corpus. swap_sides_in_game puts team b on p1 for that game."""
    set_id = f"{log}-{set_number}"
    files = []
    for g in game_numbers:
        x, y = (b, a) if g == swap_sides_in_game else (a, b)
        files += _game(game_tag(log, set_number, g), set_id, x, y)
    return files


def corpus(n_ma_sets=300, n_ma_singles=300, n_mb_sets=60, n_mb_singles=60):
    """Every unit gets its own pair of teams, so nothing is shared by accident."""
    files, n = [], 0

    def next_pair():
        nonlocal n
        n += 2
        return team(n), team(n + 1)

    for i in range(n_ma_sets):
        files += bo3(MA_BO3, 1000 + i, (1, 2, 3)[: 2 + i % 2], *next_pair())
    for i in range(n_ma_singles):
        files += single(MA_SINGLE, 5000 + i, *next_pair())
    for i in range(n_mb_sets):
        files += bo3(MB_BO3, 7000 + i, (1, 2, 3)[: 2 + i % 2], *next_pair())
    for i in range(n_mb_singles):
        files += single(MB_SINGLE, 9000 + i, *next_pair())
    return files


def key(f):
    return (f.tag, f.role)


# --------------------------------------------------------------------------
# The five guarantees from the brief
# --------------------------------------------------------------------------


def test_no_set_id_appears_in_more_than_one_split():
    files = corpus()
    result = assign_splits(files)
    splits_of_set: dict[str, set[str]] = {}
    for f in files:
        if f.set_id is not None:
            splits_of_set.setdefault(f.set_id, set()).add(result.assignments[key(f)])
    assert len(splits_of_set) > 300  # the check actually saw many sets
    assert all(len(s) == 1 for s in splits_of_set.values())
    # ...and the sets are not all dumped into one split.
    assert {next(iter(s)) for s in splits_of_set.values()} == set(SPLITS)


def test_both_player_perspectives_of_every_game_land_on_the_same_side():
    files = corpus()
    result = assign_splits(files)
    by_tag: dict[str, set[str]] = {}
    for f in files:
        by_tag.setdefault(f.tag, set()).add(result.assignments[key(f)])
    assert len(by_tag) > 600
    assert all(len(s) == 1 for s in by_tag.values())


def test_no_exact_team_pairing_appears_in_more_than_one_split():
    # 80 team pairings, each played in 8 different sets and 4 single games.
    # A split by set alone would scatter these across splits.
    files, battle = [], 0
    for p in range(80):
        a, b = team(2 * p), team(2 * p + 1)
        for k in range(8):
            battle += 1
            files += bo3(MA_BO3, 100000 + battle, (1, 2), a, b)
        for k in range(4):
            battle += 1
            files += single(MA_SINGLE, 200000 + battle, a, b)
    result = assign_splits(files)
    splits_of_pairing: dict[frozenset, set[str]] = {}
    for f in files:
        pairing = frozenset([f.own_team, f.opp_team])
        splits_of_pairing.setdefault(pairing, set()).add(result.assignments[key(f)])
    assert len(splits_of_pairing) == 80
    assert all(len(s) == 1 for s in splits_of_pairing.values())
    assert {next(iter(s)) for s in splits_of_pairing.values()} == set(SPLITS)


def test_a_pairing_counts_the_same_whichever_player_sat_on_which_side():
    # The same two teams meet in two sets, with p1 and p2 swapped in the second.
    a, b = team(1), team(2)
    for trial in range(50):  # many salts' worth of luck cannot separate them
        s1, s2 = 500000 + 10 * trial + 1, 500000 + 10 * trial + 2
        files = bo3(MA_BO3, s1, (1, 2), a, b) + bo3(MA_BO3, s2, (1, 2), b, a)
        # pad the corpus so all three splits exist in the format
        files += corpus(60, 60, 0, 0)
        result = assign_splits(files, salt=f"trial-{trial}")
        first = result.assignments[(game_tag(MA_BO3, s1, 1), "p1")]
        second = result.assignments[(game_tag(MA_BO3, s2, 1), "p1")]
        assert first == second


def test_a_pairing_is_order_independent_even_with_one_perspective_on_disk():
    # Only the p1 file of each set exists. In one set the team is on p1, in the
    # other the same two teams meet with the sides swapped. They are the same
    # pairing and must stay together.
    a, b = team(1), team(2)
    for trial in range(50):
        s1, s2 = 700000 + 10 * trial + 1, 700000 + 10 * trial + 2
        files = [
            f for f in bo3(MA_BO3, s1, (1, 2), a, b) + bo3(MA_BO3, s2, (1, 2), b, a)
            if f.role == "p1"
        ]
        result = assign_splits(files + corpus(60, 60, 0, 0), salt=f"o{trial}")
        assert (
            result.assignments[(game_tag(MA_BO3, s1, 1), "p1")]
            == result.assignments[(game_tag(MA_BO3, s2, 1), "p1")]
        )


def test_grouping_is_transitive_through_shared_pairings():
    # S1 has games with pairing P and pairing Q; S2 only plays Q; S3 only P.
    # All three must sit together or P or Q would straddle a boundary.
    p = (team(1), team(2))
    q = (team(3), team(4))
    for trial in range(50):
        base = 500000 + 100 * trial
        s1 = _game(f"{MA_BO3}-{base + 11}", f"{MA_BO3}-{base + 1}", *p) + _game(
            f"{MA_BO3}-{base + 12}", f"{MA_BO3}-{base + 1}", *q
        )
        s2 = bo3(MA_BO3, base + 2, (1, 2), *q)
        s3 = bo3(MA_BO3, base + 3, (1, 2), *p)
        result = assign_splits(s1 + s2 + s3 + corpus(60, 60, 0, 0), salt=f"t{trial}")
        seen = {result.assignments[key(f)] for f in s1 + s2 + s3}
        assert len(seen) == 1


def test_the_split_is_identical_across_two_runs_and_input_orders():
    files = corpus()
    first = assign_splits(files)
    shuffled = list(files)
    random.Random(7).shuffle(shuffled)
    second = assign_splits(shuffled)
    assert first.assignments == second.assignments
    assert first.dropped_files == second.dropped_files


def test_the_split_does_not_depend_on_the_interpreter_hash_seed(tmp_path):
    # Python's built-in hash() changes between processes. A split built on it
    # would differ run to run. Run the command line twice with different seeds.
    data = tmp_path / "states"
    data.mkdir()
    _write_corpus(data, corpus(40, 40, 15, 15))
    outputs = []
    for seed in ("1", "2"):
        out = tmp_path / f"manifest-{seed}.json"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run(
            [sys.executable, "-m", "wpa.splits", "--dir", str(data), "--out", str(out),
             "--num_workers", "1"],
            cwd=REPO_ROOT, env=env, check=True, capture_output=True,
        )
        outputs.append(json.loads(out.read_text(encoding="utf-8")))
    assert outputs[0]["games"] == outputs[1]["games"]
    assert len(outputs[0]["games"]) > 100


# --------------------------------------------------------------------------
# Formats are strata (DEFINITIONS section 15)
# --------------------------------------------------------------------------


def test_each_format_has_its_own_non_empty_train_validation_and_test():
    files = corpus()
    result = assign_splits(files)
    for fmt in (FORMAT_MA, FORMAT_MB):
        used = {
            result.assignments[key(f)] for f in files if format_of(f.tag) == fmt
        }
        assert used == set(SPLITS), fmt
    counts = result.counts
    for fmt in (FORMAT_MA, FORMAT_MB):
        for split in SPLITS:
            assert counts[fmt][split].units > 0
            assert counts[fmt][split].states > 0


def test_a_format_too_small_to_fill_every_split_says_so_plainly():
    # M-B with a single set cannot have a train, a validation and a test set.
    files = corpus(100, 100, 0, 0) + bo3(MB_BO3, 1, (1, 2), team(900), team(901))
    with pytest.raises(CannotSplitError) as err:
        assign_splits(files)
    message = str(err.value)
    assert FORMAT_MB in message
    assert "cannot" in message.lower()
    assert FORMAT_MA not in message  # M-A is fine and is not blamed


def test_one_formats_data_never_changes_the_other_formats_assignments():
    ma_only = corpus(200, 200, 0, 0)
    both = corpus(200, 200, 80, 80)
    a = assign_splits(ma_only).assignments
    b = assign_splits(both).assignments
    for k, split in a.items():
        assert b[k] == split


def test_a_pairing_shared_across_formats_does_not_tie_the_formats_together():
    # Formats are separate strata; a shared pairing in M-A and M-B may land on
    # different sides, because the two formats are never modelled together.
    shared = (team(1), team(2))
    separated = 0
    for trial in range(60):
        n = 500000 + trial
        files = (
            bo3(MA_BO3, n, (1, 2), *shared)
            + bo3(MB_BO3, n, (1, 2), *shared)
            + corpus(60, 60, 60, 60)
        )
        r = assign_splits(files, salt=f"x{trial}")
        ma = r.assignments[(game_tag(MA_BO3, n, 1), "p1")]
        mb = r.assignments[(game_tag(MB_BO3, n, 1), "p1")]
        separated += ma != mb
    assert separated > 0


def test_a_set_whose_games_come_from_two_formats_is_rejected():
    set_id = f"{MA_BO3}-1"
    files = _game(f"{MA_BO3}-11", set_id, team(1), team(2)) + _game(
        f"{MB_BO3}-12", set_id, team(1), team(2)
    )
    with pytest.raises(ValueError, match="format"):
        assign_splits(files + corpus(60, 60, 60, 60))


def test_an_unrecognised_tag_raises_and_is_never_defaulted():
    files = corpus(60, 60, 60, 60) + _game("gen9ou-1234", None, team(1), team(2))
    with pytest.raises(UnknownFormatError):
        assign_splits(files)


# --------------------------------------------------------------------------
# Units: single games are their own unit, sets stay whole
# --------------------------------------------------------------------------


def test_single_games_are_independent_units_and_sets_stay_whole():
    files = corpus(0, 600, 0, 0)
    for i in range(100):
        files += bo3(MA_BO3, 30000 + i, (1, 2, 3), team(5000 + 2 * i), team(5001 + 2 * i))
    result = assign_splits(files)
    single_splits = {
        result.assignments[key(f)] for f in files if f.set_id is None
    }
    assert single_splits == set(SPLITS)  # singles are not tied to one another
    for i in range(100):
        sid = f"{MA_BO3}-{30000 + i}"
        assert len({result.assignments[key(f)] for f in files if f.set_id == sid}) == 1


def test_a_set_that_lives_in_the_single_log_files_is_still_a_set():
    # Real corpus: 1,281 best-of-three sets sit in the *single* log files and
    # carry a set id named after them. A file's kind is not whether it has a
    # set; the unit is the set id when there is one, the battle tag otherwise.
    sets = []
    for i in range(150):
        sets.append(bo3(MA_SINGLE, 800000 + i, (1, 2, 3), team(7000 + 2 * i), team(7001 + 2 * i)))
    files = corpus(60, 60, 60, 60) + [f for group in sets for f in group]
    result = assign_splits(files)
    for group in sets:
        assert len({result.assignments[key(f)] for f in group}) == 1
    assert result.dropped_files == []


def test_set_ids_with_a_private_room_password_are_ordinary_sets():
    pw_set = f"{MA_BO3}-5-q4mk6d2nr63emwdihwxco5c8fi1lnacpw"
    games = []
    for trial in range(40):
        sid = f"{MA_BO3}-{600000 + trial}-q4mk6d2nr63emwdihwxco5c8fi1lnacpw"
        games.append(
            _game(f"{MA_BO3}-{600000 + trial}1", sid, team(9000 + 2 * trial), team(9001 + 2 * trial))
            + _game(f"{MA_BO3}-{600000 + trial}2", sid, team(9000 + 2 * trial), team(9001 + 2 * trial))
        )
    result = assign_splits(corpus(60, 60, 60, 60) + [f for g in games for f in g])
    assert pw_set.endswith("pw")
    for g in games:
        assert len({result.assignments[key(f)] for f in g}) == 1


# --------------------------------------------------------------------------
# The 71 states with no set information
# --------------------------------------------------------------------------


def test_bo3_files_with_no_set_information_are_dropped_and_counted():
    # The best-of-5 match: three games, all states lack a set id, both roles.
    best_of_5 = []
    for game_id, n in ((2614987695, 24), (2614990439, 22), (2614996363, 25)):
        best_of_5 += _game(
            f"{MA_BO3}-{game_id}", None, team(1), team(2), n_states=n, no_set=n
        )
    files = corpus(100, 100, 30, 30) + best_of_5
    result = assign_splits(files)
    assert sorted(result.dropped_files) == sorted(key(f) for f in best_of_5)
    assert result.dropped_states == 2 * (24 + 22 + 25)
    assert all(key(f) not in result.assignments for f in best_of_5)
    # nothing else was dropped
    assert len(result.assignments) == len(files) - len(best_of_5)


def test_single_games_have_no_set_id_by_design_and_are_not_dropped():
    files = corpus(60, 60, 60, 60)
    singles = [f for f in files if f.set_id is None]
    assert singles
    result = assign_splits(files)
    assert result.dropped_files == []
    assert all(key(f) in result.assignments for f in singles)


def test_a_bo3_file_with_only_some_states_missing_a_set_id_is_kept_and_counted():
    mixed = _game(f"{MA_BO3}-77", f"{MA_BO3}-7", team(1), team(2), n_states=10, no_set=3)
    result = assign_splits(corpus(100, 100, 30, 30) + mixed)
    assert all(key(f) in result.assignments for f in mixed)
    assert result.dropped_files == []
    assert result.dropped_states == 6  # 3 states in each of the two files
    split = result.assignments[key(mixed[0])]
    # the kept file counts only the states that survive
    assert result.counts[FORMAT_MA][split].states >= 2 * (10 - 3)


# --------------------------------------------------------------------------
# Proportions are a parameter, and are recorded with the output
# --------------------------------------------------------------------------


def test_default_proportions_sum_to_one():
    assert set(DEFAULT_PROPORTIONS) == set(SPLITS)
    assert sum(DEFAULT_PROPORTIONS.values()) == pytest.approx(1.0)


def test_proportions_are_respected_and_recorded_with_the_output():
    files = corpus(0, 3000, 0, 0) + corpus(0, 0, 0, 200)
    props = {"train": 0.5, "validation": 0.25, "test": 0.25}
    result = assign_splits(files, proportions=props)
    assert result.proportions == props
    total = sum(result.counts[FORMAT_MA][s].units for s in SPLITS)
    for s in SPLITS:
        assert result.counts[FORMAT_MA][s].units / total == pytest.approx(
            props[s], abs=0.04
        )
    recorded = result.to_dict()
    assert recorded["proportions"] == props
    assert "salt" in recorded
    assert recorded["dropped_states"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"train": 0.5, "validation": 0.2, "test": 0.2},  # sums to 0.9
        {"train": 1.2, "validation": -0.1, "test": -0.1},  # negative
        {"train": 0.8, "validation": 0.2},  # a split missing
        {"train": 0.8, "validation": 0.1, "test": 0.1, "extra": 0.0},
    ],
)
def test_bad_proportions_are_rejected(bad):
    with pytest.raises(ValueError):
        assign_splits(corpus(60, 60, 60, 60), proportions=bad)


def test_changing_the_proportions_changes_the_split():
    files = corpus()
    a = assign_splits(files).assignments
    b = assign_splits(
        files, proportions={"train": 0.4, "validation": 0.3, "test": 0.3}
    ).assignments
    assert a != b


# --------------------------------------------------------------------------
# Reading the real file layout (wpa_states/<tag>-<role>.json)
# --------------------------------------------------------------------------


def _pokemon(species):
    return [
        {"species": s, "hp_fraction": 1.0, "fainted": False, "active": False,
         "gimmick": None}
        for s in species
    ]


def _write_game_file(directory: Path, f: GameFile):
    states = []
    for i in range(f.n_states):
        has_set = i >= f.n_states_without_set  # the first states lack a set id
        states.append(
            {
                "turn": i,
                "decision_index": 0,
                "outcome": None,
                "set_id": f.set_id if (has_set and f.set_id) else None,
                "game_index": 1 if f.set_id else None,
                "set_score_entering_game": [0, 0] if f.set_id else None,
                "our_pokemon": _pokemon(reversed(f.own_team)),  # order must not matter
                "opp_pokemon": _pokemon(f.opp_team),
                "observations": [],
            }
        )
    (directory / f"{f.tag}-{f.role}.json").write_text(
        json.dumps(states), encoding="utf-8"
    )


def _write_corpus(directory: Path, files):
    for f in files:
        _write_game_file(directory, f)


def test_scan_game_file_reads_set_id_teams_and_state_counts(tmp_path):
    f = GameFile(f"{MA_BO3}-11", "p2", f"{MA_BO3}-1", team(5), team(6), 8, 2)
    _write_game_file(tmp_path, f)
    scanned = scan_game_file(str(tmp_path / f"{f.tag}-{f.role}.json"))
    assert scanned == f  # teams come back as sorted tuples, whatever the file order


def test_scan_game_file_refuses_an_empty_file(tmp_path):
    path = tmp_path / f"{MA_SINGLE}-1-p1.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="no states"):
        scan_game_file(str(path))


def test_split_directory_matches_the_in_memory_split(tmp_path):
    files = corpus(50, 50, 20, 20)
    _write_corpus(tmp_path, files)
    from_disk = split_directory(tmp_path, num_workers=1)
    in_memory = assign_splits(files)
    assert from_disk.assignments == in_memory.assignments
    assert from_disk.counts == in_memory.counts


def test_split_directory_fails_loudly_on_an_unrecognised_file(tmp_path):
    _write_corpus(tmp_path, corpus(50, 50, 20, 20))
    (tmp_path / "gen9ou-1234-p1.json").write_text("[]", encoding="utf-8")
    with pytest.raises(UnknownFormatError):
        split_directory(tmp_path, num_workers=1)
