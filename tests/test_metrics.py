"""Week 4 Task 4: the metric harness (wpa/metrics.py).

Metrics are tests with thresholds. This module tests the HARNESS (that the
Brier score, calibration table, symmetry / terminal checks and the trend are
computed correctly); Task 5 applies them to the v0 baseline.

NO STRICT MONOTONICITY TEST, AND NONE SHOULD BE ADDED. "Removing an opposing
Pokemon never lowers your win probability" is false in real play: a weak
active Pokemon can be worth more to leave alive than the stronger one that
replaces it, and a running timer such as Tailwind can make a knockout costly
(docs/EXPERT-CLAIMS.md EC-001). The same holds for your own side: sacrificing
a spent Pokemon can raise your odds (EC-002). The trend over the number of
Pokemon remaining is therefore REPORTED over many states, never gated on any
one state. (DEFINITIONS section 11.2's "set win probability is monotone in
game win probability" is a different, valid property.)

Everything is computed per format (DEFINITIONS section 15). A pooled figure
exists only as a labelled secondary.
"""

import json
import math
import random
from pathlib import Path

import pytest

from wpa.formats import FORMAT_MA, FORMAT_MB
from wpa.metrics import (
    BRING_SIZE,
    COIN_FLIP_BRIER,
    ExpertClaim,
    LoadStats,
    PokemonView,
    Scored,
    StateView,
    brier_score,
    brier_skill,
    calibration_failures,
    calibration_table,
    complement_failures,
    evaluate,
    load_split,
    mirror_state,
    perfectly_mirrored,
    pokemon_remaining,
    remaining_trend,
    score_claims,
    score_states,
    state_from_dict,
    symmetry_failures,
    terminal_failures,
)

# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def mon(species="m", hp=1.0, fainted=False, active=False):
    return PokemonView(species=species, hp_fraction=hp, fainted=fainted, active=active)


def side(*hps, fainted=0):
    """Six Pokemon: the given HP fractions, then `fainted` fainted ones."""
    pokes = [mon(f"s{i}", hp) for i, hp in enumerate(hps)]
    pokes += [mon(f"f{i}", 0.0, fainted=True) for i in range(fainted)]
    return tuple(pokes)


def state(ours, theirs, outcome=None, score=None):
    return StateView(
        turn=3,
        our_pokemon=ours,
        opp_pokemon=theirs,
        outcome=outcome,
        set_score_entering_game=score,
    )


def hp_total(poke_side):
    return sum(p.hp_fraction for p in poke_side if not p.fainted)


def good_predictor(s):
    """A small, honest predictor: symmetric, complementary, exact at the end."""
    if s.outcome is True:
        return 1.0
    if s.outcome is False:
        return 0.0
    diff = hp_total(s.our_pokemon) - hp_total(s.opp_pokemon)
    return 1.0 / (1.0 + math.exp(-diff))


# --------------------------------------------------------------------------
# Brier score
# --------------------------------------------------------------------------


def test_brier_of_a_known_example():
    preds, labels = [0.9, 0.2, 0.6], [True, False, False]
    assert brier_score(preds, labels) == pytest.approx((0.01 + 0.04 + 0.36) / 3)


def test_brier_extremes_and_the_coin_flip_reference():
    assert brier_score([1.0, 0.0], [True, False]) == 0.0
    assert brier_score([0.0, 1.0], [True, False]) == 1.0
    assert COIN_FLIP_BRIER == 0.25
    rng = random.Random(1)
    labels = [rng.random() < 0.5 for _ in range(1000)]
    # always saying 0.5 scores exactly the coin-flip reference, whatever happens
    assert brier_score([0.5] * 1000, labels) == COIN_FLIP_BRIER


def test_brier_skill_is_relative_to_the_coin_flip():
    assert brier_skill(0.25) == 0.0
    assert brier_skill(0.0) == 1.0
    assert brier_skill(0.5) == pytest.approx(-1.0)  # worse than a coin flip


@pytest.mark.parametrize(
    "preds, labels",
    [
        ([], []),  # nothing to score is an error, not 0.0
        ([0.5], [True, False]),  # length mismatch
        ([1.2], [True]),
        ([-0.1], [True]),
        ([float("nan")], [True]),
        ([0.5], [None]),  # an undecided state has no label
    ],
)
def test_brier_refuses_inputs_it_cannot_score(preds, labels):
    with pytest.raises(ValueError):
        brier_score(preds, labels)


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------


def test_calibration_bins_cover_zero_to_one_and_count_every_state():
    preds = [0.0, 0.05, 0.1, 0.55, 0.99, 1.0]
    labels = [False, False, False, True, True, True]
    table = calibration_table(preds, labels, n_bins=10)
    assert len(table) == 10
    assert table[0].low == 0.0 and table[-1].high == 1.0
    assert sum(b.n for b in table) == len(preds)
    assert table[0].n == 2  # 0.0 and 0.05
    assert table[1].n == 1  # 0.1
    assert table[5].n == 1  # 0.55
    assert table[9].n == 2  # 0.99 and exactly 1.0 belong in the last bin


def test_calibration_reports_predicted_and_observed_per_bin_with_counts():
    table = calibration_table(
        [0.62, 0.68, 0.64, 0.66], [True, True, False, True], n_bins=10
    )
    b = table[6]
    assert b.n == 4
    assert b.mean_predicted == pytest.approx(0.65)
    assert b.observed_rate == pytest.approx(0.75)
    assert b.gap == pytest.approx(0.10)
    empty = table[0]
    assert empty.n == 0 and empty.observed_rate is None and empty.gap is None


def _sample(n, seed, bias=0.0):
    rng = random.Random(seed)
    preds, labels = [], []
    for _ in range(n):
        p = rng.random()
        preds.append(p)
        labels.append(rng.random() < min(1.0, max(0.0, p + bias)))
    return preds, labels


def test_a_calibrated_predictor_passes_and_a_miscalibrated_one_fails():
    preds, labels = _sample(100_000, seed=2)
    ok = calibration_failures(
        calibration_table(preds, labels), tolerance=0.03, min_count=200
    )
    assert ok == []
    preds, labels = _sample(100_000, seed=3, bias=0.2)
    bad = calibration_failures(
        calibration_table(preds, labels), tolerance=0.03, min_count=200
    )
    assert len(bad) >= 5
    assert all(b.gap is not None and abs(b.gap) > 0.03 for b in bad)


def test_bins_with_too_few_states_are_reported_but_never_fail():
    # one wildly wrong state in a bin of one
    table = calibration_table([0.95], [False], n_bins=10)
    assert table[9].n == 1 and table[9].gap == pytest.approx(0.95 - 0.0)
    assert calibration_failures(table, tolerance=0.05, min_count=30) == []
    assert calibration_failures(table, tolerance=0.05, min_count=1) == table[9:10]


@pytest.mark.parametrize("n_bins", [0, 1, -3, 2.5, "10", True])
def test_calibration_needs_a_sensible_bin_count(n_bins):
    with pytest.raises(ValueError):
        calibration_table([0.5], [True], n_bins=n_bins)


@pytest.mark.parametrize(
    "tolerance, min_count", [(-0.1, 10), (1.5, 10), (0.1, 0), (0.1, -5)]
)
def test_calibration_failure_thresholds_are_validated(tolerance, min_count):
    table = calibration_table([0.5], [True])
    with pytest.raises(ValueError):
        calibration_failures(table, tolerance=tolerance, min_count=min_count)


# --------------------------------------------------------------------------
# Symmetry, complement and terminal checks (DEFINITIONS sections 1 and 5)
# --------------------------------------------------------------------------


def test_mirror_swaps_the_sides_flips_the_outcome_and_the_score():
    s = state(side(1.0, 0.5), side(0.2, fainted=2), outcome=True, score=(1, 0))
    m = mirror_state(s)
    assert m.our_pokemon == s.opp_pokemon and m.opp_pokemon == s.our_pokemon
    assert m.outcome is False
    assert m.set_score_entering_game == (0, 1)
    assert mirror_state(mirror_state(s)) == s
    assert mirror_state(state(side(1.0), side(1.0))).outcome is None
    assert mirror_state(state(side(1.0), side(1.0), outcome=False)).outcome is True


def test_a_perfectly_mirrored_state_has_equal_sides_and_is_undecided():
    s = state(side(1.0, 0.4), side(0.3), outcome=True, score=(1, 0))
    p = perfectly_mirrored(s)
    assert p.our_pokemon == p.opp_pokemon == s.our_pokemon
    assert p.outcome is None
    assert (
        p.set_score_entering_game is None
        or p.set_score_entering_game[0] == p.set_score_entering_game[1]
    )


STATES = [
    state(side(1.0, 1.0, 1.0, 1.0), side(1.0, 1.0, 1.0, 1.0)),
    state(side(0.3, 1.0, fainted=2), side(0.9, 0.4, 0.8, fainted=1)),
    state(side(1.0, fainted=3), side(0.2, 0.2, 0.2, 0.2)),
]


def test_symmetry_check_passes_an_honest_predictor_and_flags_a_biased_one():
    assert symmetry_failures(good_predictor, STATES) == []
    biased = lambda s: 0.6  # noqa: E731  "home advantage" for whoever is analysed
    failures = symmetry_failures(biased, STATES)
    assert len(failures) == len(STATES)


def test_symmetry_tolerance_is_respected():
    near = lambda s: 0.5 + 1e-9  # noqa: E731
    assert symmetry_failures(near, STATES, tolerance=1e-6) == []
    assert len(symmetry_failures(near, STATES, tolerance=1e-12)) == len(STATES)


def test_complement_check_requires_wp_of_the_other_side_to_be_one_minus_wp():
    assert complement_failures(good_predictor, STATES) == []
    lopsided = lambda s: min(1.0, good_predictor(s) + 0.1)  # noqa: E731
    assert complement_failures(lopsided, STATES)  # some state is off


def test_terminal_check_requires_exactly_one_for_won_and_zero_for_lost():
    won = state(side(1.0, fainted=1), side(fainted=4), outcome=True)
    lost = state(side(fainted=4), side(0.5), outcome=False)
    live = state(side(1.0), side(1.0))
    assert terminal_failures(good_predictor, [won, lost, live]) == []
    soft = lambda s: 0.99 if s.outcome else (0.01 if s.outcome is False else 0.5)  # noqa: E731
    assert terminal_failures(soft, [won, lost, live]) == [
        won,
        lost,
    ]  # the live one is ignored
    assert terminal_failures(lambda s: 0.5, [live]) == []


# --------------------------------------------------------------------------
# Pokemon remaining and the trend (reported, not gated)
# --------------------------------------------------------------------------


def test_bring_size_is_four_and_remaining_counts_from_it_not_from_six():
    # hp_fraction is 0.0 for anything off the field, including the two Pokemon
    # that were never brought, so "6 - fainted" would overstate what is left.
    assert BRING_SIZE == 4
    assert pokemon_remaining(side(1.0, 0.5, 0.0, 0.0, fainted=0)) == 4
    assert pokemon_remaining(side(1.0, 0.0, 0.0, 0.0, fainted=2)) == 2
    assert pokemon_remaining(side(fainted=4)) == 0
    assert (
        pokemon_remaining(tuple(mon(f"x{i}", 0.0, fainted=True) for i in range(6))) == 0
    )  # clamped


def _scored(fmt, our, opp, pred, label=True, game="g"):
    return Scored(
        format=fmt,
        game=game,
        pred=pred,
        label=label,
        our_remaining=our,
        opp_remaining=opp,
    )


def test_trend_table_counts_and_averages_each_cell_per_format():
    rows = [
        _scored(FORMAT_MA, 4, 4, 0.50),
        _scored(FORMAT_MA, 4, 4, 0.60),
        _scored(FORMAT_MA, 4, 3, 0.70),
        _scored(FORMAT_MB, 4, 4, 0.10),
    ]
    trend = remaining_trend(rows)
    cell = trend[FORMAT_MA].cells[(4, 4)]
    assert cell.n == 2 and cell.mean_predicted == pytest.approx(0.55)
    assert trend[FORMAT_MA].cells[(4, 3)].n == 1
    assert trend[FORMAT_MB].cells[(4, 4)].mean_predicted == pytest.approx(0.10)
    assert (4, 3) not in trend[FORMAT_MB].cells  # formats never mix


def test_trend_rising_fraction_is_one_when_wp_rises_as_the_opponent_loses_pokemon():
    rows = []
    for opp in (4, 3, 2, 1):
        rows += [_scored(FORMAT_MA, 4, opp, 0.4 + 0.1 * (4 - opp))] * 50
    t = remaining_trend(rows, min_count=30)[FORMAT_MA]
    assert t.rising_fraction == 1.0
    falling = [
        _scored(FORMAT_MA, 4, opp, 0.4 - 0.1 * (4 - opp))
        for opp in (4, 3, 2, 1)
        for _ in range(50)
    ]
    assert remaining_trend(falling, min_count=30)[FORMAT_MA].rising_fraction == 0.0


def test_a_flat_trend_is_not_counted_as_rising():
    flat = [_scored(FORMAT_MA, 4, opp, 0.5) for opp in (4, 3, 2) for _ in range(40)]
    t = remaining_trend(flat, min_count=30)[FORMAT_MA]
    assert t.steps == 2 and t.rising_fraction == 0.0


def test_trend_ignores_cells_below_the_minimum_count_and_is_never_a_gate():
    rows = [_scored(FORMAT_MA, 4, 4, 0.5)] * 50 + [_scored(FORMAT_MA, 4, 3, 0.1)] * 2
    t = remaining_trend(rows, min_count=30)[FORMAT_MA]
    assert t.rising_fraction is None  # only one cell is big enough: no steps to judge
    assert (4, 3) in t.cells  # still reported, with its count
    # a perverse trend is reported, not raised
    perverse = [
        _scored(FORMAT_MA, 4, o, 0.9 - 0.2 * (4 - o))
        for o in (4, 3, 2)
        for _ in range(40)
    ]
    remaining_trend(perverse, min_count=30)


# --------------------------------------------------------------------------
# Per-format evaluation; pooled only as a labelled secondary
# --------------------------------------------------------------------------


def _scored_set(fmt, n, seed, bias=0.0, games=20):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = rng.random()
        out.append(
            Scored(
                fmt,
                f"{fmt}-{i % games}",
                p,
                rng.random() < min(1, max(0, p + bias)),
                4,
                4,
            )
        )
    return out


def test_evaluate_scores_each_format_from_only_its_own_states():
    ma = _scored_set(FORMAT_MA, 6000, 1)
    mb = _scored_set(FORMAT_MB, 6000, 2, bias=0.3)
    report = evaluate(ma + mb, tolerance=0.05, min_count=100)
    assert set(report.per_format) == {FORMAT_MA, FORMAT_MB}
    assert report.per_format[FORMAT_MA].brier == pytest.approx(
        brier_score([r.pred for r in ma], [r.label for r in ma])
    )
    assert report.per_format[FORMAT_MB].brier == pytest.approx(
        brier_score([r.pred for r in mb], [r.label for r in mb])
    )
    assert report.per_format[FORMAT_MA].calibration_failures == []
    assert report.per_format[
        FORMAT_MB
    ].calibration_failures  # M-B is miscalibrated here
    assert report.per_format[FORMAT_MA].n_states == 6000
    assert report.per_format[FORMAT_MA].n_games == 20


def test_the_pooled_figure_exists_but_is_labelled_secondary():
    ma = _scored_set(FORMAT_MA, 3000, 4)
    mb = _scored_set(FORMAT_MB, 300, 5, bias=0.3)
    report = evaluate(ma + mb, min_count=50)
    assert report.pooled.pooled is True
    assert all(m.pooled is False for m in report.per_format.values())
    assert report.pooled.n_states == 3300
    text = report.describe()
    assert text.index(FORMAT_MA) < text.index(FORMAT_MB) < text.upper().index("POOLED")
    pooled_part = text[text.upper().index("POOLED") :]
    assert "secondary" in pooled_part.lower()
    assert "not a headline" in pooled_part.lower()


def test_the_report_carries_sample_sizes_the_coin_flip_and_every_bin_count():
    report = evaluate(_scored_set(FORMAT_MB, 500, 6, games=7), min_count=20)
    text = report.describe()
    assert "500" in text and "7 games" in text
    assert "0.25" in text  # the coin-flip reference sits next to the score
    assert text.count("n=") >= 10  # a count for each of the 10 calibration bins


def test_a_record_without_a_format_is_an_error():
    with pytest.raises(ValueError):
        evaluate([Scored("", "g", 0.5, True, 4, 4)])
    with pytest.raises(ValueError):
        evaluate([])


def test_score_states_runs_the_predictor_and_derives_remaining_counts():
    s = state(side(1.0, 1.0, fainted=2), side(0.5, fainted=3))
    rows = list(score_states(lambda x: 0.7, [(FORMAT_MA, "game-1", s, True)]))
    assert rows == [Scored(FORMAT_MA, "game-1", 0.7, True, 2, 1)]


def test_score_states_refuses_a_prediction_outside_zero_to_one():
    s = state(side(1.0), side(1.0))
    with pytest.raises(ValueError):
        list(score_states(lambda x: 1.5, [(FORMAT_MA, "g", s, True)]))
    with pytest.raises(ValueError):
        list(score_states(lambda x: float("nan"), [(FORMAT_MA, "g", s, True)]))


# --------------------------------------------------------------------------
# Expert-claim cases: reported, never gated
# --------------------------------------------------------------------------


def test_expert_claims_are_scored_and_reported_without_gating():
    better = state(side(1.0, 1.0, 1.0, 1.0), side(0.2, fainted=3))
    worse = state(side(0.1, fainted=3), side(1.0, 1.0, 1.0, 1.0))
    claims = [
        ExpertClaim("EC-T1", "more health is better", better, worse),
        ExpertClaim("EC-T2", "a claim the baseline cannot see", better, better),
    ]
    results = score_claims(good_predictor, claims)
    assert [r.claim_id for r in results] == ["EC-T1", "EC-T2"]
    assert results[0].agrees is True and results[0].p_better > results[0].p_worse
    assert results[1].agrees is False  # a tie is not agreement
    assert score_claims(good_predictor, []) == []


def test_the_report_says_plainly_when_there_are_no_labelled_positions():
    report = evaluate(_scored_set(FORMAT_MA, 400, 8), min_count=20, claims=[])
    assert "0 labelled" in report.describe()


# --------------------------------------------------------------------------
# Loading states and labels from wpa_states/
# --------------------------------------------------------------------------


def _pk(species, hp=1.0, fainted=False, active=False):
    return {
        "species": species,
        "hp_fraction": hp,
        "fainted": fainted,
        "active": active,
        "gimmick": None,
    }


def _state_dict(turn, outcome, set_id=None):
    return {
        "turn": turn,
        "our_pokemon": [_pk("a"), _pk("b", 0.0, True)],
        "opp_pokemon": [_pk("c"), _pk("d")],
        "outcome": outcome,
        "set_id": set_id,
        "game_index": 1 if set_id else None,
        "set_score_entering_game": [0, 0] if set_id else None,
        "decision_index": 0,
        "observations": [],
    }


def _write(directory: Path, tag, role, outcomes):
    states = [_state_dict(i, o) for i, o in enumerate(outcomes)]
    (directory / f"{tag}-{role}.json").write_text(json.dumps(states), encoding="utf-8")


MA = "gen9championsvgc2026regma"
MB = "gen9championsvgc2026regmb"


def test_state_from_dict_builds_the_light_view():
    s = state_from_dict(_state_dict(2, True))
    assert s.turn == 2 and s.outcome is True
    assert s.our_pokemon[1].fainted is True and s.opp_pokemon[0].species == "c"


def test_the_light_view_matches_the_real_battlestate_schema():
    pytest.importorskip("poke_env")
    from dataclasses import fields

    from wpa.state import BattleState, PokemonState

    assert {f.name for f in fields(PokemonView)} == {
        f.name for f in fields(PokemonState)
    }
    needed = {f.name for f in fields(StateView)}
    assert needed <= {f.name for f in fields(BattleState)}


def test_load_split_yields_the_chosen_split_and_format_with_the_games_label(tmp_path):
    _write(tmp_path, f"{MA}-1", "p1", [None, None, True])
    _write(tmp_path, f"{MA}-1", "p2", [None, None, False])
    _write(tmp_path, f"{MA}-2", "p1", [None, False])  # in another split
    _write(tmp_path, f"{MB}-3", "p1", [None, True])  # in another format
    games = {f"{MA}-1": "validation", f"{MA}-2": "train", f"{MB}-3": "validation"}
    stats = LoadStats()
    rows = list(load_split(tmp_path, games, "validation", FORMAT_MA, stats))
    assert len(rows) == 6  # 3 states x 2 perspectives
    labels = {(game, label) for _fmt, game, _s, label in rows}
    assert labels == {(f"{MA}-1", True), (f"{MA}-1", False)}
    assert {fmt for fmt, *_ in rows} == {FORMAT_MA}
    assert stats.games == 1 and stats.files == 2 and stats.states == 6


def test_every_state_of_a_game_gets_the_games_final_outcome_as_its_label(tmp_path):
    _write(tmp_path, f"{MA}-1", "p1", [None, None, None, True])
    rows = list(
        load_split(tmp_path, {f"{MA}-1": "test"}, "test", FORMAT_MA, LoadStats())
    )
    assert [label for *_x, label in rows] == [True] * 4
    assert [s.outcome for _f, _g, s, _l in rows] == [
        None,
        None,
        None,
        True,
    ]  # states keep theirs


def test_incomplete_games_are_dropped_and_counted_not_scored(tmp_path):
    _write(tmp_path, f"{MA}-1", "p1", [None, None])  # never decided
    _write(tmp_path, f"{MA}-2", "p1", [None, True])
    games = {f"{MA}-1": "test", f"{MA}-2": "test"}
    stats = LoadStats()
    rows = list(load_split(tmp_path, games, "test", FORMAT_MA, stats))
    assert {g for _f, g, _s, _l in rows} == {f"{MA}-2"}
    assert stats.incomplete_files == 1 and stats.incomplete_states == 2


def test_files_with_no_assignment_are_skipped_and_counted(tmp_path):
    _write(tmp_path, f"{MA}-1", "p1", [None, True])
    _write(tmp_path, f"{MA}-9", "p1", [None, True])  # e.g. the dropped best-of-5
    stats = LoadStats()
    list(load_split(tmp_path, {f"{MA}-1": "test"}, "test", FORMAT_MA, stats))
    assert stats.unassigned_files == 1


def test_load_split_rejects_an_unknown_split_name(tmp_path):
    with pytest.raises(ValueError):
        list(load_split(tmp_path, {}, "holdout", FORMAT_MA, LoadStats()))


def test_load_split_streams_one_file_at_a_time(tmp_path):
    _write(tmp_path, f"{MA}-1", "p1", [None, True])
    _write(tmp_path, f"{MA}-2", "p1", [None, True])
    gen = load_split(
        tmp_path, {f"{MA}-1": "test", f"{MA}-2": "test"}, "test", FORMAT_MA, LoadStats()
    )
    next(gen)  # a generator, not a list: nothing else has been read into memory yet
    assert hasattr(gen, "__next__")


# --------------------------------------------------------------------------
# Decided states are scored by a separate test, not by the headline Brier
# (found on the real validation data: a coin flip that is exact once the game
# is over scores skill +0.097 only because ~5% of states are already decided)
# --------------------------------------------------------------------------


def _mixed_rows(fmt=FORMAT_MA, n_open=100, n_decided=50):
    rows = [
        Scored(fmt, f"{fmt}-{i % 10}", 0.5, i % 2 == 0, 4, 4) for i in range(n_open)
    ]
    rows += [
        Scored(
            fmt,
            f"{fmt}-{i % 10}",
            1.0 if i % 2 == 0 else 0.0,
            i % 2 == 0,
            2,
            0,
            decided=True,
        )
        for i in range(n_decided)
    ]
    return rows


def test_scored_marks_decided_states_and_defaults_to_undecided():
    assert Scored(FORMAT_MA, "g", 0.5, True, 4, 4).decided is False
    s = state(side(1.0), side(1.0), outcome=True)
    row = list(score_states(lambda x: 1.0, [(FORMAT_MA, "g", s, True)]))[0]
    assert row.decided is True
    row = list(
        score_states(
            lambda x: 0.5, [(FORMAT_MA, "g", state(side(1.0), side(1.0)), True)]
        )
    )[0]
    assert row.decided is False


def test_the_headline_brier_calibration_and_trend_use_undecided_states_only():
    m = evaluate(_mixed_rows(), min_count=10).per_format[FORMAT_MA]
    assert m.n_states == 100 and m.n_decided == 50
    assert m.brier == pytest.approx(0.25)
    assert m.brier_skill == pytest.approx(0.0)
    assert sum(b.n for b in m.calibration) == 100
    assert (2, 0) not in m.trend.cells  # decided positions would inflate the trend
    # the all-states figure is still available, labelled as such
    assert m.brier_with_decided == pytest.approx(100 * 0.25 / 150)


def test_the_pooled_figure_follows_the_same_rule():
    rows = _mixed_rows(FORMAT_MA) + _mixed_rows(FORMAT_MB, 30, 10)
    p = evaluate(rows, min_count=5).pooled
    assert p.n_states == 130 and p.n_decided == 60


def test_the_report_says_how_many_decided_states_were_set_aside():
    text = evaluate(_mixed_rows(), min_count=10).describe()
    assert "50 decided states set aside" in text
    assert "including decided states" in text.lower()


def test_a_format_with_only_decided_states_cannot_be_scored():
    only_decided = [r for r in _mixed_rows() if r.decided]
    with pytest.raises(ValueError, match="undecided"):
        evaluate(only_decided)
