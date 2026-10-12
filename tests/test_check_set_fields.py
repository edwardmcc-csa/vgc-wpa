"""Post-re-parse check (wpa/check_set_fields.py): finds bo3 states whose
set fields were not populated, so the Week 3 Task 8 "populated throughout,
not just on a sample" confirmation is a measurement, not a hope.
"""

import json

from wpa.check_set_fields import scan_directory


def _state(set_id="s1", game_index=1, score=(0, 0)):
    return {
        "turn": 1,
        "decision_index": 0,
        "set_id": set_id,
        "game_index": game_index,
        "set_score_entering_game": list(score) if score is not None else None,
    }


def _write(path, states):
    path.write_text(json.dumps(states), encoding="utf-8")


def test_clean_directory_reports_nothing_missing(tmp_path):
    _write(tmp_path / "gen9x-bo3-1-p1.json", [_state(), _state()])
    result = scan_directory(tmp_path, num_workers=1)
    assert result.bo3_files == 1
    assert result.bo3_states == 2
    assert result.missing_set_id == 0
    assert result.missing_game_index == 0
    assert result.missing_score == 0
    assert result.affected == []


def test_missing_fields_are_counted_and_attributed_to_their_file(tmp_path):
    _write(tmp_path / "gen9x-bo3-1-p1.json", [_state(), _state()])
    _write(
        tmp_path / "gen9x-bo3-2-p1.json",
        [_state(set_id=None, game_index=None, score=None), _state(score=None)],
    )
    result = scan_directory(tmp_path, num_workers=1)
    assert result.bo3_states == 4
    assert result.missing_set_id == 1
    assert result.missing_game_index == 1
    assert result.missing_score == 2
    assert [a.file for a in result.affected] == ["gen9x-bo3-2-p1.json"]
    assert result.affected[0].states_missing_any == 2


def test_single_game_files_are_not_expected_to_have_set_fields(tmp_path):
    _write(
        tmp_path / "gen9x-123-p1.json",
        [_state(set_id=None, game_index=None, score=None)],
    )
    result = scan_directory(tmp_path, num_workers=1)
    assert result.bo3_files == 0
    assert result.affected == []
