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
