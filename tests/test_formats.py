"""Week 4 Task 1: format tagging (wpa/formats.py).

DEFINITIONS section 15: Reg M-A and Reg M-B are two formats. Every battle
tag maps to exactly one, and a best-of-three set never spans formats.
"""

import json

import pytest

from wpa.formats import (
    FORMAT_MA,
    FORMAT_MB,
    KIND_BO3,
    KIND_SINGLE,
    UnknownFormatError,
    format_of,
    kind_of,
    parse_state_filename,
    summarize_directory,
)


@pytest.mark.parametrize(
    "tag, expected_format, expected_kind",
    [
        ("gen9championsvgc2026regma-2580291588", FORMAT_MA, KIND_SINGLE),
        ("gen9championsvgc2026regmabo3-2580300180", FORMAT_MA, KIND_BO3),
        ("gen9championsvgc2026regmb-1234", FORMAT_MB, KIND_SINGLE),
        ("gen9championsvgc2026regmbbo3-5678", FORMAT_MB, KIND_BO3),
    ],
)
def test_known_tags_map_to_one_format_and_kind(tag, expected_format, expected_kind):
    assert format_of(tag) == expected_format
    assert kind_of(tag) == expected_kind


def test_bo3_is_not_confused_with_its_single_game_prefix():
    # "regma" is a prefix of "regmabo3"; matching must be on the whole name.
    assert kind_of("gen9championsvgc2026regmabo3-1") == KIND_BO3
    assert kind_of("gen9championsvgc2026regma-1") == KIND_SINGLE


@pytest.mark.parametrize(
    "tag",
    [
        "gen9championsvgc2026regmc-1",
        "gen9ou-1234",
        "gen9championsvgc2026regma",
        "",
    ],
)
def test_unrecognised_tags_raise_and_are_never_defaulted(tag):
    with pytest.raises(UnknownFormatError):
        format_of(tag)


def test_state_filenames_split_into_tag_and_role():
    assert parse_state_filename("gen9championsvgc2026regmabo3-2580300180-p1.json") == (
        "gen9championsvgc2026regmabo3-2580300180",
        "p1",
    )
    assert parse_state_filename("gen9championsvgc2026regma-2580291588-p2.json") == (
        "gen9championsvgc2026regma-2580291588",
        "p2",
    )
    with pytest.raises(ValueError):
        parse_state_filename("not-a-state-file.txt")
    with pytest.raises(ValueError):
        parse_state_filename("gen9championsvgc2026regma-1-p3.json")


def _write(path, states):
    path.write_text(json.dumps(states), encoding="utf-8")


def _state(set_id=None):
    return {"turn": 1, "decision_index": 0, "set_id": set_id}


def test_summary_counts_battles_sets_and_states_per_format_and_kind(tmp_path):
    set_a = "gen9championsvgc2026regmabo3-100"
    set_b = "gen9championsvgc2026regmbbo3-200"
    # an M-A set: games 101 and 102, both players
    for tag in ("gen9championsvgc2026regmabo3-101", "gen9championsvgc2026regmabo3-102"):
        for role in ("p1", "p2"):
            _write(tmp_path / f"{tag}-{role}.json", [_state(set_a), _state(set_a)])
    # an M-B set: one game
    for role in ("p1", "p2"):
        _write(
            tmp_path / f"gen9championsvgc2026regmbbo3-201-{role}.json",
            [_state(set_b)],
        )
    # a single M-A game
    for role in ("p1", "p2"):
        _write(
            tmp_path / f"gen9championsvgc2026regma-300-{role}.json",
            [_state(), _state(), _state()],
        )

    summary = summarize_directory(tmp_path, num_workers=1)

    ma_bo3 = summary.counts[(FORMAT_MA, KIND_BO3)]
    assert (ma_bo3.battles, ma_bo3.files, ma_bo3.sets, ma_bo3.states) == (2, 4, 1, 8)
    mb_bo3 = summary.counts[(FORMAT_MB, KIND_BO3)]
    assert (mb_bo3.battles, mb_bo3.files, mb_bo3.sets, mb_bo3.states) == (1, 2, 1, 2)
    ma_single = summary.counts[(FORMAT_MA, KIND_SINGLE)]
    assert (ma_single.battles, ma_single.files, ma_single.sets, ma_single.states) == (
        1,
        2,
        0,
        6,
    )
    assert summary.spanning_sets == []
    assert summary.bo3_states_without_set == 0


def test_a_set_spanning_two_formats_is_reported(tmp_path):
    bad_set = "gen9championsvgc2026regmabo3-900"
    _write(tmp_path / "gen9championsvgc2026regmabo3-901-p1.json", [_state(bad_set)])
    _write(tmp_path / "gen9championsvgc2026regmbbo3-902-p1.json", [_state(bad_set)])

    summary = summarize_directory(tmp_path, num_workers=1)

    assert [s for s, _ in summary.spanning_sets] == [bad_set]


def test_bo3_states_without_a_set_are_counted_not_hidden(tmp_path):
    # The one best-of-5 set in the corpus: bo3 file, no set information.
    _write(tmp_path / "gen9championsvgc2026regmabo3-777-p1.json", [_state(None)])
    summary = summarize_directory(tmp_path, num_workers=1)
    assert summary.bo3_states_without_set == 1


def test_an_unrecognised_file_fails_loudly(tmp_path):
    _write(tmp_path / "gen9championsvgc2026regmc-1-p1.json", [_state()])
    with pytest.raises(UnknownFormatError):
        summarize_directory(tmp_path, num_workers=1)


# --- Found on the real corpus (13 Oct re-run of Task 1) ---------------------
# 11 of 48,347 set ids end in a private-room password, e.g.
# 'gen9championsvgc2026regmabo3-2604921266-q4mk6d2nr63emwdihwxco5c8fi1lnacpw'.
# And 1,281 best-of-three sets (1,246 M-A, 35 M-B) live in the *single* log
# files: their set id carries the single log name. A file's kind is not
# whether it has a set.


@pytest.mark.parametrize(
    "set_id, expected_format, expected_kind",
    [
        (
            "gen9championsvgc2026regmabo3-2604921266-q4mk6d2nr63emwdihwxco5c8fi1lnacpw",
            FORMAT_MA,
            KIND_BO3,
        ),
        (
            "gen9championsvgc2026regma-2605947927-6ce64a9tbyfhi6lmnnt5gpm6hcsj7lspw",
            FORMAT_MA,
            KIND_SINGLE,
        ),
        ("gen9championsvgc2026regmbbo3-55-abc123pw", FORMAT_MB, KIND_BO3),
    ],
)
def test_set_ids_with_a_private_room_password_still_map_to_a_format(
    set_id, expected_format, expected_kind
):
    assert format_of(set_id) == expected_format
    assert kind_of(set_id) == expected_kind


@pytest.mark.parametrize(
    "tag",
    [
        "gen9championsvgc2026regmc-12-abcpw",  # unknown log name, with a password
        "gen9championsvgc2026regma-12-34-56",  # more than one suffix
        "gen9championsvgc2026regma-abc",  # id is not a number
        "gen9championsvgc2026regma-12-",  # empty password
    ],
)
def test_malformed_tags_still_raise_after_allowing_a_password(tag):
    with pytest.raises(UnknownFormatError):
        format_of(tag)


def test_sets_in_single_log_files_are_counted_as_sets(tmp_path):
    set_id = "gen9championsvgc2026regma-400"
    for tag in ("gen9championsvgc2026regma-401", "gen9championsvgc2026regma-402"):
        for role in ("p1", "p2"):
            _write(tmp_path / f"{tag}-{role}.json", [_state(set_id), _state(set_id)])
    # and one true single game with no set at all
    for role in ("p1", "p2"):
        _write(tmp_path / f"gen9championsvgc2026regma-500-{role}.json", [_state()])

    summary = summarize_directory(tmp_path, num_workers=1)

    single = summary.counts[(FORMAT_MA, KIND_SINGLE)]
    assert single.sets == 1
    assert (single.battles, single.files, single.states) == (3, 6, 10)
    # states without a set are only an anomaly in a bo3 file, not in a single one
    assert summary.bo3_states_without_set == 0
