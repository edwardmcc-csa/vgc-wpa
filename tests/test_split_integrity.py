"""Splits parsed games into train/test buckets by best-of-3 set
(DEFINITIONS #13): every trajectory from a set goes to the same side, and
no exact team pairing crosses a split boundary either - a set-only split
still lets the identical matchup recur on both sides.

wpa/split.py doesn't exist yet; written first and expected to fail.
"""

import json
from pathlib import Path

from wpa.sets import reconstruct_sets
from wpa.split import GameRecord, split_by_set, team_pairing_from_log

FIXTURES = Path(__file__).parent / "fixtures"


def test_games_sharing_a_set_id_land_in_the_same_split():
    records = [
        GameRecord("g1", "set-A", _pairing("teamX", "teamY")),
        GameRecord("g2", "set-A", _pairing("teamX", "teamY")),
        GameRecord("g3", "set-A", _pairing("teamX", "teamY")),
        GameRecord("g4", "set-B", _pairing("teamP", "teamQ")),
    ]
    assignment = split_by_set(records, ratios={"train": 0.5, "test": 0.5}, seed=1)

    assert assignment["g1"] == assignment["g2"] == assignment["g3"]


def test_games_sharing_a_team_pairing_land_in_the_same_split_even_across_sets():
    # Same two teams meeting again in a *different* set - a set-only split
    # would happily put set-A in train and set-B in test even though it's
    # the identical matchup both times.
    records = [
        GameRecord("g1", "set-A", _pairing("teamX", "teamY")),
        GameRecord("g2", "set-B", _pairing("teamX", "teamY")),
    ]
    assignment = split_by_set(records, ratios={"train": 0.5, "test": 0.5}, seed=1)

    assert assignment["g1"] == assignment["g2"]


def test_split_respects_approximate_ratios():
    records = [
        GameRecord(f"g{i}", f"set-{i}", _pairing(f"team{i}a", f"team{i}b"))
        for i in range(200)
    ]
    assignment = split_by_set(records, ratios={"train": 0.8, "test": 0.2}, seed=7)

    train_fraction = sum(1 for v in assignment.values() if v == "train") / len(
        assignment
    )
    assert 0.65 <= train_fraction <= 0.95


def test_archetype_option_groups_beyond_exact_team_when_provided():
    # Two sets with *different* exact teams, but sharing an archetype under
    # a caller-supplied classifier, must land together when that option is
    # used. No archetype classifier is implemented here (that's modelling,
    # out of scope this week) - this only checks the extension point M4
    # will plug a real one into.
    def archetype(team: frozenset[str]) -> str:
        return "sun" if "Torkoal" in team else "other"

    records = [
        GameRecord("g1", "set-A", _pairing("Torkoal", "Volcarona")),
        GameRecord("g2", "set-B", _pairing("Torkoal", "Charizard")),
    ]
    assignment = split_by_set(
        records, ratios={"train": 0.5, "test": 0.5}, seed=3, archetype_fn=archetype
    )
    assert assignment["g1"] == assignment["g2"]


def _pairing(*teams: str) -> frozenset[frozenset[str]]:
    return frozenset(frozenset([t]) for t in teams)


def _load_sample(fname: str) -> dict:
    return json.loads((FIXTURES / fname).read_text(encoding="utf-8"))


def test_no_set_id_or_team_pairing_crosses_the_split_on_real_data():
    logs = _load_sample("bo3_sample_regmabo3.json")
    reconstruction = reconstruct_sets(logs)

    records = []
    set_id_by_tag = {}
    for set_id, games in reconstruction.sets.items():
        for game_index, tag in games.items():
            set_id_by_tag[tag] = set_id
            pairing = team_pairing_from_log(logs[tag][1])
            records.append(GameRecord(tag, set_id, pairing))

    assignment = split_by_set(records, ratios={"train": 0.8, "test": 0.2}, seed=42)

    # No set id split across buckets.
    bucket_by_set: dict[str, str] = {}
    for r in records:
        bucket = assignment[r.tag]
        if r.set_id in bucket_by_set:
            assert bucket_by_set[r.set_id] == bucket, (
                f"set {r.set_id} appears in both {bucket_by_set[r.set_id]} and {bucket}"
            )
        else:
            bucket_by_set[r.set_id] = bucket

    # No exact team pairing split across buckets.
    bucket_by_pairing: dict[frozenset, str] = {}
    for r in records:
        bucket = assignment[r.tag]
        if r.team_pairing in bucket_by_pairing:
            assert bucket_by_pairing[r.team_pairing] == bucket, (
                f"pairing {r.team_pairing} appears in both "
                f"{bucket_by_pairing[r.team_pairing]} and {bucket}"
            )
        else:
            bucket_by_pairing[r.team_pairing] = bucket

    assert len(records) > 10, "expected a real sample of games to check"
