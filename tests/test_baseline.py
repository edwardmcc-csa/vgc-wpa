"""Week 4 Task 5: the v0 hand-written baseline (wpa/baseline.py).

The baseline turns the fields a BattleState already carries (hit points,
Pokemon remaining) into WP_public. It is deliberately simple, uses no machine
learning, and is the bar a learned model must clear.

WHAT IT CANNOT DO, STATED PLAINLY: it cannot represent timers (Tailwind turns
left, Trick Room, screens, Encore, ...) or speed relationships, so it is
EXPECTED to get the docs/EXPERT-CLAIMS.md cases wrong. That is the evidence
for which state features the learned model needs.

These tests apply the Task 4 checks (symmetry, complement, terminal) to the
baseline, and add what only the baseline can be held to:

* the information set (DEFINITIONS section 5): the prediction reads only
  hp_fraction, fainted, active and outcome, enforced here with a guard that
  raises on any other field, so nothing unrevealed can leak in;
* how unrevealed Pokemon are handled (hit points are 0.0 for anything not on
  the field, brought or not, so they must not be read as 'nearly fainted').

There is no monotonicity test: see tests/test_metrics.py for why.
"""

import json
import math
import random
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from wpa.formats import FORMAT_MA, FORMAT_MB
from wpa.metrics import (
    PokemonView,
    StateView,
    complement_failures,
    mirror_state,
    perfectly_mirrored,
    symmetry_failures,
    terminal_failures,
)
from wpa.baseline import (
    BASELINE_K,
    LIMITATIONS,
    main,
    make_predictor,
    predict,
    report_split,
    strength,
)

MA = "gen9championsvgc2026regma"
MB = "gen9championsvgc2026regmb"


# --------------------------------------------------------------------------
# Builders: states as the corpus really has them
# --------------------------------------------------------------------------


def mon(hp=0.0, fainted=False, active=False, species="x", gimmick=None):
    return PokemonView(species, hp, fainted, active, gimmick)


def side(revealed=(), fainted=0, unrevealed=2, active=()):
    """Six Pokemon the way the corpus lists them: `revealed` alive hit-point
    fractions, `fainted` fainted ones, then Pokemon never seen (hp 0.0, not
    fainted, not active). Pokemon at indexes in `active` are on the field."""
    pokes = [mon(hp, active=(i in active), species=f"r{i}") for i, hp in enumerate(revealed)]
    pokes += [mon(0.0, True, species=f"f{i}") for i in range(fainted)]
    pokes += [mon(0.0, species=f"u{i}") for i in range(unrevealed)]
    assert len(pokes) == 6, len(pokes)
    return tuple(pokes)


def state(ours, theirs, outcome=None, **kw):
    return StateView(turn=3, our_pokemon=ours, opp_pokemon=theirs, outcome=outcome, **kw)


def random_state(rng, outcome=None):
    """A plausible mid-game state: each side brought four, two stayed home."""
    def one_side():
        fainted = rng.randint(0, 4)
        alive_brought = 4 - fainted
        seen = rng.randint(0, alive_brought)
        hps = [round(rng.uniform(0.01, 1.0), 2) for _ in range(seen)]
        active = tuple(range(min(2, seen)))
        # 2 never brought + (alive_brought - seen) brought but not yet seen
        return side(hps, fainted, unrevealed=6 - seen - fainted, active=active)

    return state(one_side(), one_side(), outcome=outcome)


def expected(diff, k=BASELINE_K):
    return 1.0 / (1.0 + math.exp(-k * diff))


# --------------------------------------------------------------------------
# The Task 4 checks, applied to the baseline
# --------------------------------------------------------------------------

RNG = random.Random(2026)
STATES = [random_state(RNG) for _ in range(300)]


def test_a_perfectly_mirrored_state_returns_exactly_one_half():
    assert symmetry_failures(predict, STATES, tolerance=1e-12) == []


def test_the_other_side_of_any_state_is_one_minus_wp():
    assert complement_failures(predict, STATES, tolerance=1e-12) == []


def test_a_won_state_returns_one_and_a_lost_state_returns_zero():
    won = [random_state(random.Random(i), outcome=True) for i in range(30)]
    lost = [random_state(random.Random(i), outcome=False) for i in range(30)]
    assert terminal_failures(predict, won + lost, tolerance=0.0) == []
    assert predict(won[0]) == 1.0 and predict(lost[0]) == 0.0


def test_an_undecided_state_is_never_exactly_zero_or_one():
    for s in STATES:
        assert 0.0 < predict(s) < 1.0
    # even the most lopsided legal position
    worst = state(side(fainted=4, unrevealed=2), side([1.0] * 4, unrevealed=2, active=(0, 1)))
    best = mirror_state(worst)
    assert 0.0 < predict(worst) < 0.5 < predict(best) < 1.0


def test_the_checks_have_teeth_against_an_empty_implementation():
    # An 'empty' baseline that always says 0.5 sails through symmetry and
    # complement, which is exactly why terminal and the formula tests exist.
    empty = lambda s: 0.5  # noqa: E731
    assert symmetry_failures(empty, STATES) == []
    assert complement_failures(empty, STATES) == []
    won = state(side(fainted=1, unrevealed=2, revealed=[1.0, 0.5, 0.2]), side(fainted=4, unrevealed=2), outcome=True)
    assert terminal_failures(empty, [won]) == [won]
    assert abs(empty(STATES[0]) - predict(STATES[0])) > 1e-6 or abs(empty(STATES[1]) - predict(STATES[1])) > 1e-6


# --------------------------------------------------------------------------
# The formula
# --------------------------------------------------------------------------


def test_equal_sides_are_even_and_a_known_lead_has_a_known_value():
    even = state(side([1.0, 1.0], unrevealed=2, fainted=2), side([1.0, 1.0], unrevealed=2, fainted=2))
    assert predict(even) == 0.5
    # we have all four (strength 4.0), they have lost one (strength 3.0)
    ahead = state(side([1.0, 1.0], unrevealed=4), side([1.0, 1.0], fainted=1, unrevealed=3))
    assert predict(ahead) == pytest.approx(expected(1.0))


def test_strength_adds_revealed_hit_points_and_counts_unrevealed_brought_as_full():
    # 1 fainted -> 3 remain; two seen alive (0.5, 0.3); so one brought Pokemon
    # has not appeared yet and is counted as full health.
    s = side([0.5, 0.3], fainted=1, unrevealed=3, active=(0, 1))
    assert strength(s) == pytest.approx(0.5 + 0.3 + 1.0)
    # nothing revealed: all four brought are assumed full
    assert strength(side(unrevealed=6)) == pytest.approx(4.0)
    # everything gone
    assert strength(side(fainted=4, unrevealed=2)) == 0.0


def test_hit_points_of_zero_are_unrevealed_not_nearly_fainted():
    # The corpus shows hp 0.0 for every Pokemon off the field, brought or not.
    fresh = state(side(unrevealed=6), side(unrevealed=6))
    assert predict(fresh) == 0.5
    # A Pokemon on the field at hp 0.0 that has not fainted is revealed and contributes 0
    low = side([0.0, 1.0], unrevealed=4, active=(0, 1))
    assert strength(low) == pytest.approx(0.0 + 1.0 + 2.0)  # 4 remain: 2 seen, 2 unseen


def test_the_scale_constant_is_part_of_the_record():
    p = make_predictor(2.0)
    s = state(side([1.0, 1.0], unrevealed=4), side([1.0, 1.0], fainted=1, unrevealed=3))
    assert p(s) == pytest.approx(expected(1.0, 2.0))
    assert make_predictor(BASELINE_K)(s) == predict(s)
    for bad in (0, -1.0, float("nan"), "1"):
        with pytest.raises(ValueError):
            make_predictor(bad)


def test_the_limits_are_stated_in_the_code_not_only_in_the_report():
    text = " ".join(LIMITATIONS).lower()
    for must in ("timer", "speed", "expert"):
        assert must in text


# --------------------------------------------------------------------------
# The information set (DEFINITIONS section 5): nothing unrevealed gets in
# --------------------------------------------------------------------------

ALLOWED_STATE = {"our_pokemon", "opp_pokemon", "outcome"}
ALLOWED_MON = {"hp_fraction", "fainted", "active"}


class _GuardedMon:
    def __init__(self, m):
        self._m = m

    def __getattr__(self, name):
        if name in ALLOWED_MON:
            return getattr(self._m, name)
        raise AssertionError(f"the baseline read forbidden Pokemon field {name!r}")


class _GuardedState:
    def __init__(self, s):
        self._s = s

    def __getattr__(self, name):
        if name in ("our_pokemon", "opp_pokemon"):
            return tuple(_GuardedMon(m) for m in getattr(self._s, name))
        if name in ALLOWED_STATE:
            return getattr(self._s, name)
        raise AssertionError(f"the baseline read forbidden state field {name!r}")


def test_the_baseline_reads_only_hit_points_fainted_active_and_outcome():
    for s in STATES[:50] + [replace(STATES[0], outcome=True), replace(STATES[0], outcome=False)]:
        assert predict(_GuardedState(s)) == predict(s)


def test_the_guard_itself_catches_a_forbidden_read():
    with pytest.raises(AssertionError):
        _GuardedState(STATES[0]).turn
    with pytest.raises(AssertionError):
        _GuardedState(STATES[0]).our_pokemon[0].species


def test_which_unrevealed_pokemon_were_brought_cannot_change_the_prediction():
    # Swapping the identities, order and mega flags of unrevealed Pokemon (the
    # corpus gives 'mega' to an unrevealed holder of any '...ite' item) must
    # change nothing: there is nothing to learn from them.
    rng = random.Random(7)
    for s in STATES[:100]:
        def scramble(poke_side):
            seen = [m for m in poke_side if m.hp_fraction > 0 or m.fainted or m.active]
            hidden = [m for m in poke_side if m not in seen]
            rng.shuffle(hidden)
            hidden = [replace(m, species=f"zz{rng.random()}", gimmick=rng.choice([None, "mega"])) for m in hidden]
            return tuple(seen + hidden)

        s2 = replace(s, opp_pokemon=scramble(s.opp_pokemon), our_pokemon=scramble(s.our_pokemon))
        assert predict(s2) == predict(s)


def test_nothing_about_the_set_or_the_turn_changes_the_prediction():
    s = STATES[3]
    for variant in (
        replace(s, turn=99, decision_index=4),
        replace(s, set_id="gen9championsvgc2026regmabo3-1", game_index=3, set_score_entering_game=(1, 1)),
    ):
        assert predict(variant) == predict(s)


def test_it_works_on_the_real_battlestate_too():
    pytest.importorskip("poke_env")
    from wpa.state import BattleState, PokemonState

    ours = tuple(PokemonState("a", 1.0, False, True) for _ in range(2)) + tuple(
        PokemonState("b", 0.0, False, False) for _ in range(4)
    )
    theirs = tuple(PokemonState("c", 0.0, True, False) for _ in range(1)) + tuple(
        PokemonState("d", 0.0, False, False) for _ in range(5)
    )
    real = BattleState(turn=2, our_pokemon=ours, opp_pokemon=theirs, outcome=None)
    assert 0.5 < predict(real) < 1.0


# --------------------------------------------------------------------------
# The report: validation split, per format
# --------------------------------------------------------------------------


def _pk(hp, fainted=False, active=False):
    return {"species": "x", "hp_fraction": hp, "fainted": fainted, "active": active, "gimmick": None}


def _state_dict(turn, outcome, ours, theirs):
    return {
        "turn": turn,
        "our_pokemon": ours,
        "opp_pokemon": theirs,
        "outcome": outcome,
        "set_id": None,
        "game_index": None,
        "set_score_entering_game": None,
        "decision_index": 0,
        "observations": [],
    }


def _write_game(directory: Path, tag, we_win: bool):
    """A tiny three-state game, written for both perspectives."""
    full = [_pk(1.0, active=True), _pk(1.0, active=True)] + [_pk(0.0)] * 4
    ko = [_pk(0.0, True)] * 2 + [_pk(0.6, active=True)] + [_pk(0.0)] * 3
    gone = [_pk(0.0, True)] * 4 + [_pk(0.0)] * 2
    for role, wins in (("p1", we_win), ("p2", not we_win)):
        mine, theirs = (full, ko) if wins else (ko, full)
        states = [
            _state_dict(0, None, full, full),
            _state_dict(2, None, mine, theirs),
            _state_dict(3, wins, mine if wins else gone, gone if wins else theirs),
        ]
        (directory / f"{tag}-{role}.json").write_text(json.dumps(states), encoding="utf-8")


def _corpus(tmp_path, n_ma=6, n_mb=3):
    games = {}
    for i in range(n_ma):
        tag = f"{MA}-{i}"
        _write_game(tmp_path, tag, we_win=i % 2 == 0)
        games[tag] = "validation"
    for i in range(n_mb):
        tag = f"{MB}-{i}"
        _write_game(tmp_path, tag, we_win=i % 2 == 0)
        games[tag] = "validation"
    _write_game(tmp_path, f"{MA}-900", we_win=True)
    games[f"{MA}-900"] = "train"
    return games


def test_report_split_scores_each_format_from_the_chosen_split_only(tmp_path):
    games = _corpus(tmp_path)
    report, load = report_split(tmp_path, games, "validation")
    assert set(report.per_format) == {FORMAT_MA, FORMAT_MB}
    assert report.per_format[FORMAT_MA].n_games == 6
    assert report.per_format[FORMAT_MB].n_games == 3
    assert report.per_format[FORMAT_MA].n_decided == 12  # the last state of each file
    assert load[FORMAT_MA].games == 6 and load[FORMAT_MB].games == 3
    for m in report.per_format.values():
        assert 0.0 <= m.brier <= 1.0


def test_report_split_skips_a_format_with_no_games_in_the_split(tmp_path):
    games = _corpus(tmp_path, n_ma=4, n_mb=0)
    report, _ = report_split(tmp_path, games, "validation")
    assert set(report.per_format) == {FORMAT_MA}


def test_report_split_with_nothing_to_score_says_so(tmp_path):
    with pytest.raises(ValueError, match="nothing"):
        report_split(tmp_path, {}, "validation")


def test_the_command_line_prints_the_limits_the_counts_and_a_per_format_report(
    tmp_path, monkeypatch, capsys
):
    data = tmp_path / "states"
    data.mkdir()
    games = _corpus(data)
    manifest = tmp_path / "splits.json"  # outside the data folder: a stray .json there is an error
    manifest.write_text(json.dumps({"games": games}), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["wpa.baseline", "--dir", str(data), "--splits", str(manifest)]
    )
    main()
    out = capsys.readouterr().out
    assert "v0 baseline" in out and "timers" in out.lower()
    assert FORMAT_MA in out and FORMAT_MB in out
    assert "Brier" in out
    assert out.upper().index("POOLED") > out.index(FORMAT_MB)
    assert "incomplete" in out.lower()


def test_a_stray_json_file_in_the_states_folder_is_an_error_not_ignored(tmp_path):
    games = _corpus(tmp_path)
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not a state file"):
        report_split(tmp_path, games, "validation")
