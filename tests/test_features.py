"""Tests for wpa/features.py (Week 5 Task 5): the feature table.

Groups, each switchable: A state only; B field presence from earlier turns'
observations; C timers; D team-sheet capabilities; E sheet position of unseen
Pokemon. A row is one decision point from one player's side.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import shutil
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from wpa import features as F
from wpa.durations import CountedEffect, Durations, SourceRef
from wpa.team_sheets import Dex, sheets_from_log
from wpa.timer_join import align
from wpa.timers import track_decisions

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
LOGS = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"
REF = SourceRef("x", 1)

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)

SLEEP = CountedEffect(
    "slp",
    "slp",
    {2: Fraction(1, 3), 3: Fraction(2, 3)},
    {},
    None,
    None,
    None,
    "",
    "",
    REF,
)
TABLE = Durations("t", timed={}, counted={"slp": SLEEP})
DEX = Dex(species={}, moves={}, items={})


def load(tag, role):
    return json.loads((FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8"))


def game_inputs(tag, role, table=TABLE):
    states = load(tag, role)
    joined = align(states, track_decisions(LOGS[tag], table)[role], role)
    assert joined is not None
    return states, joined, sheets_from_log(LOGS[tag])


TAG = "gen9championsvgc2026regma-2580291588"


def test_columns_are_fixed_and_grouped_by_prefix():
    cols = F.columns("ABCDE")
    assert len(cols) == len(set(cols))
    for g in "ABCDE":
        assert all(c.startswith(g.lower() + "_") for c in F.columns(g))
    assert F.columns("A") == [c for c in cols if c.startswith("a_")]


def test_every_column_is_filled_for_every_decision_of_a_real_game():
    states, joined, sheets = game_inputs(TAG, "p1")
    for k in range(len(states) - 1):
        row = F.state_features(states, k, "p1", joined[k], sheets, DEX, TABLE, "ABCDE")
        assert list(row) == F.columns("ABCDE")
        assert all(isinstance(v, float) for v in row.values())


def test_group_a_counts_what_the_state_shows():
    states, joined, sheets = game_inputs(TAG, "p1")
    row = F.state_features(states, 3, "p1", joined[3], sheets, DEX, TABLE, "A")
    # state (1, 1): our Talonflame fainted, their Arcanine fainted in turn 1
    assert row["a_our_fainted"] == 1 and row["a_their_fainted"] == 1
    assert row["a_our_remaining"] == 3 and row["a_their_remaining"] == 3
    assert row["a_turn"] == 1
    assert row["a_their_hp_seen"] == pytest.approx(0.01)


def test_group_b_uses_only_observations_from_earlier_turns():
    states, joined, sheets = game_inputs(TAG, "p1")
    # turn 2's start carries turn 2's own Protects; only turns 0-1 may be used
    k = next(i for i, s in enumerate(states) if s["turn"] == 2)
    row = F.state_features(states, k, "p1", joined[k], sheets, DEX, TABLE, "B")
    assert row["b_has_obs"] == 1.0
    assert (
        row["b_weather_rain"] == 0.0
    )  # Drizzle came at turn 2's start, after the decision
    k3 = next(i for i, s in enumerate(states) if s["turn"] == 3)
    row3 = F.state_features(states, k3, "p1", joined[k3], sheets, DEX, TABLE, "B")
    assert row3["b_weather_rain"] == 1.0


def test_group_c_moment_and_counters():
    states, joined, sheets = game_inputs(TAG, "p1")
    row = F.state_features(states, 3, "p1", joined[3], sheets, DEX, TABLE, "C")
    assert row["c_moment_after_turn"] == 1.0
    from wpa.timer_join import JoinedTimers

    asleep = JoinedTimers(
        their_counters=(("slp", "p2a: Inci", 1),), moment="turn_start"
    )
    row = F.state_features(states, 2, "p1", asleep, sheets, DEX, TABLE, "C")
    assert row["c_their_slp_n"] == 1.0
    assert row["c_their_slp_end_next"] == pytest.approx(1 / 3)  # one attempt prevented


class GuardedState(dict):
    ALLOWED = {
        "turn",
        "decision_index",
        "our_pokemon",
        "opp_pokemon",
        "game_index",
        "set_score_entering_game",
        "observations",
    }

    def __getitem__(self, key):
        if key not in self.ALLOWED:
            raise AssertionError(f"features read state field {key!r}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in self.ALLOWED:
            raise AssertionError(f"features read state field {key!r}")
        return super().get(key, default)


class GuardedMon(dict):
    ALLOWED = {"species", "hp_fraction", "fainted", "active"}

    def __getitem__(self, key):
        if key not in self.ALLOWED:
            raise AssertionError(f"features read Pokemon field {key!r}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in self.ALLOWED:
            raise AssertionError(f"features read Pokemon field {key!r}")
        return super().get(key, default)


def guarded(s):
    s = dict(s)
    s["our_pokemon"] = [GuardedMon(p) for p in s["our_pokemon"]]
    s["opp_pokemon"] = [GuardedMon(p) for p in s["opp_pokemon"]]
    return GuardedState(s)


def test_features_never_read_the_outcome_or_any_field_outside_the_allow_list():
    states, joined, sheets = game_inputs(TAG, "p1")
    wrapped = [guarded(s) for s in states]
    for k in range(len(states) - 1):
        F.state_features(wrapped, k, "p1", joined[k], sheets, DEX, TABLE, "ABCDE")


def test_features_up_to_a_decision_ignore_the_rest_of_the_game():
    states, joined, sheets = game_inputs(TAG, "p1")
    for k in range(len(states) - 1):
        whole = F.state_features(
            states, k, "p1", joined[k], sheets, DEX, TABLE, "ABCDE"
        )
        cut = F.state_features(
            states[: k + 1], k, "p1", joined[k], sheets, DEX, TABLE, "ABCDE"
        )
        assert whole == cut


def test_mirroring_swaps_our_and_their_columns():
    cols = F.columns("ABCDE")
    perm = F.mirror_permutation(cols)
    assert sorted(perm) == list(range(len(cols)))
    i = cols.index("a_our_fainted")
    assert cols[perm[i]] == "a_their_fainted"
    j = cols.index("c_field_trickroom")
    assert perm[j] == j


def test_rows_for_a_game_carry_label_unit_and_both_perspectives():
    rows = []
    for role in ("p1", "p2"):
        states, joined, sheets = game_inputs(TAG, role)
        rows += F.rows_for_file(TAG, role, states, joined, sheets, DEX, TABLE, "ABCDE")
    p1 = [r for r in rows if r.role == "p1"]
    p2 = [r for r in rows if r.role == "p2"]
    assert {r.label for r in p1} == {1} and {r.label for r in p2} == {0}
    assert len(p1) == len(load(TAG, "p1")) - 1
    assert {r.unit for r in rows} == {TAG}  # a single game is its own unit
    bo3 = "gen9championsvgc2026regmabo3-2580300474"
    states, joined, sheets = game_inputs(bo3, "p1")
    r = F.rows_for_file(bo3, "p1", states, joined, sheets, DEX, TABLE, "A")[0]
    assert r.unit == states[0]["set_id"]


def test_shard_files_round_trip(tmp_path):
    rows = []
    for role in ("p1", "p2"):
        states, joined, sheets = game_inputs(TAG, role)
        rows += F.rows_for_file(TAG, role, states, joined, sheets, DEX, TABLE, "ABCDE")
    path = tmp_path / "part.npz"
    F.write_rows(path, rows, F.columns("ABCDE"))
    table = F.read_rows(path)
    assert table.X.shape == (len(rows), len(F.columns("ABCDE")))
    assert table.X.dtype == np.float32
    assert list(table.y) == [r.label for r in rows]
    assert list(table.unit) == [r.unit for r in rows]
    assert table.columns == F.columns("ABCDE")


def test_shards_are_by_game_so_both_perspectives_land_together():
    for tag in LOGS:
        assert F.shard_of(tag, 16) == F.shard_of(tag, 16)
    shards = {F.shard_of(f"gen9championsvgc2026regma-{i}", 8) for i in range(200)}
    assert shards == set(range(8))


@needs_showdown
def test_real_timers_show_up_in_group_c():
    from wpa.durations import load_all

    table = load_all(SHOWDOWN)["regma"]
    states, joined, sheets = game_inputs(TAG, "p1", table)
    k3 = next(i for i, s in enumerate(states) if s["turn"] == 3)
    row = F.state_features(states, k3, "p1", joined[k3], sheets, DEX, table, "C")
    assert row["c_field_raindance"] >= 1  # Drizzle at turn 2, five turns


def test_building_from_the_logs_writes_rows_from_our_decision_table(tmp_path):
    from wpa import decisions as Dn

    splits = {tag: "train" for tag in LOGS}
    logs_dir = tmp_path / "logs"
    F.split_logs_into_shards(
        [(tag, log) for tag, log in LOGS.items()], splits, logs_dir, shards=2
    )
    assert sorted(p.name for p in logs_dir.iterdir()) == [
        "part-000.jsonl.gz",
        "part-001.jsonl.gz",
    ]
    out = tmp_path / "features"
    total = 0
    for shard in range(2):
        counts = F.build_shard_from_logs(
            shard,
            2,
            logs_dir=logs_dir,
            splits=splits,
            dexes={"regma": DEX, "regmb": DEX},
            tables={"regma": TABLE, "regmb": TABLE},
            out_dir=out,
            groups="ABCDEF",
        )
        total += counts["rows"]
    want = 0
    for tag, log in LOGS.items():
        g = Dn.build_game(log, TABLE)
        want += sum(len(g.states[r]) - 1 for r in ("p1", "p2"))
    assert total == want
    parts = list(out.glob("*/train/*.npz"))
    t = F.concat(F.read_rows(p) for p in parts)
    assert t.columns == F.columns("ABCDEF")
    assert len(t.y) == want
