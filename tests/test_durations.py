"""Tests for wpa/durations.py (Week 4 Task 7).

Most tests read the pinned pokemon-showdown submodule through Node, exactly as
the generator does, and are skipped on a machine without Node or without the
built submodule (dist/). The turn arithmetic at the bottom needs neither.

Nothing here is a hand-copied table of durations that the generator could
silently disagree with: the numbers asserted are the ones the task brief says
to verify, and the generator is what verifies them against the source.
"""

from __future__ import annotations

import inspect
import re
import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from wpa import durations as D

ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"
FORMATS = ("regma", "regmb")

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)


@pytest.fixture(scope="module")
def data():
    return D.load_all(SHOWDOWN)


# --------------------------------------------------------------------------
# Which mod each format runs
# --------------------------------------------------------------------------


@needs_showdown
def test_format_to_mod_mapping_matches_showdown_config():
    text = (SHOWDOWN / "config" / "formats.ts").read_text(encoding="utf-8")
    for fmt, label in (("regma", "Reg M-A"), ("regmb", "Reg M-B")):
        pattern = (
            r'name: "\[Gen 9 Champions\] VGC 2026 %s",\s*mod: \'(\w+)\''
            % re.escape(label)
        )
        match = re.search(pattern, text)
        assert match is not None, label
        assert D.FORMAT_MODS[fmt] == match.group(1)


@needs_showdown
def test_load_all_returns_one_table_per_format(data):
    assert set(data) == set(FORMATS)
    for fmt in FORMATS:
        assert data[fmt].timed and data[fmt].counted


# --------------------------------------------------------------------------
# The durations the brief says to verify, in both formats
# --------------------------------------------------------------------------


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_tailwind_is_four_turns_six_with_persistent(data, fmt):
    t = data[fmt].timed["tailwind"]
    assert t.base == 4
    assert t.attach == "sideCondition"
    assert {(m.kind, m.name): m.duration for m in t.modifiers} == {
        ("ability", "persistent"): 6
    }


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("move", ["lightscreen", "reflect", "auroraveil"])
def test_screens_are_five_turns_eight_with_light_clay(data, fmt, move):
    t = data[fmt].timed[move]
    assert t.base == 5
    assert {(m.kind, m.name): m.duration for m in t.modifiers} == {
        ("item", "lightclay"): 8
    }


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    "move", ["trickroom", "wonderroom", "magicroom", "safeguard", "gravity"]
)
def test_rooms_are_five_turns_seven_with_persistent(data, fmt, move):
    t = data[fmt].timed[move]
    assert t.base == 5
    assert {(m.kind, m.name): m.duration for m in t.modifiers} == {
        ("ability", "persistent"): 7
    }


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    "effect, item",
    [
        ("raindance", "damprock"),
        ("sunnyday", "heatrock"),
        ("sandstorm", "smoothrock"),
        ("snowscape", "icyrock"),
        ("electricterrain", "terrainextender"),
        ("grassyterrain", "terrainextender"),
        ("mistyterrain", "terrainextender"),
        ("psychicterrain", "terrainextender"),
    ],
)
def test_weather_and_terrain_are_five_turns_eight_with_their_item(
    data, fmt, effect, item
):
    t = data[fmt].timed[effect]
    assert t.base == 5
    assert {(m.kind, m.name): m.duration for m in t.modifiers} == {("item", item): 8}


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_ordering_within_the_turn_adjusts_encore_taunt_and_disable(data, fmt):
    encore, taunt, disable = (
        data[fmt].timed[k] for k in ("encore", "taunt", "disable")
    )
    assert (encore.base, taunt.base, disable.base) == (3, 3, 5)
    assert [(a.handler, a.delta) for a in encore.adjustments] == [
        ("condition.onStart", 1)
    ]
    assert [(a.handler, a.delta) for a in taunt.adjustments] == [
        ("condition.onStart", 1)
    ]
    assert [(a.handler, a.delta) for a in disable.adjustments] == [
        ("condition.onStart", -1)
    ]
    # The Champions mod overrides Encore's start behaviour (brief: "verify").
    assert encore.adjustments[0].source.file == "data/mods/champions/moves.ts"
    assert taunt.adjustments[0].source.file == "data/moves.ts"
    # The condition under which the length changes is kept verbatim.
    assert "willMove" in encore.adjustments[0].guard
    assert "willMove" in disable.adjustments[0].guard


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_random_length_effects_are_marked_random(data, fmt):
    trapped = data[fmt].timed["partiallytrapped"]
    assert trapped.random_range == (5, 7)  # this.random(5, 7): 5 or 6
    assert {(m.kind, m.name): m.duration for m in trapped.modifiers} == {
        ("item", "gripclaw"): 8
    }
    assert data[fmt].timed["tailwind"].random_range is None


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_future_attacks_and_wish_are_set_from_the_turn_counter(data, fmt):
    # Future Sight / Doom Desire (slot condition futuremove) and Wish have no
    # duration field. Showdown compares against getOverflowedTurnCount(), which
    # is the turn number minus one, so a future attack used on turn T lands in
    # the residual of T + 2 (equivalent duration 3) and Wish heals in the
    # residual of T + 1 (equivalent duration 2). The battle logs confirm both.
    for key, base in (("futuremove", 3), ("wish", 2)):
        t = data[fmt].timed[key]
        assert t.scheduled_by == "turn stamp"
        assert t.base == base


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_every_counter_in_the_condition_table_is_accounted_for(data, fmt):
    # If Showdown ever adds another counted status, the generator must not
    # silently skip it: it is either timed, in the counted list, or listed here.
    import json
    import subprocess

    dump = json.loads(
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts" / "dump_durations.js"),
                str(SHOWDOWN),
                D.FORMAT_MODS[fmt],
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    counters = re.compile(
        r"startTime|effectState\.(time|counter|stage)|statusState\.(time|stage)"
    )
    unaccounted = [
        e["id"]
        for e in dump["effects"]
        if e["table"] == "Conditions"
        and any(counters.search(src) for src in e["functions"].values())
        and e["id"] not in data[fmt].counted
        and e["id"] not in data[fmt].timed
    ]
    assert unaccounted == []


# --------------------------------------------------------------------------
# Every effect carries a real source file and line
# --------------------------------------------------------------------------


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_every_source_reference_points_at_the_text_it_describes(data, fmt):
    checked = 0
    for effect in data[fmt].timed.values():
        own = ("duration", "durationCallback")
        if effect.scheduled_by == "turn stamp":
            own = ("endingTurn", "startingTurn")
        refs = [(effect.source, own)]
        refs += [(m.source, (m.name,)) for m in effect.modifiers]
        refs += [(a.source, ("duration",)) for a in effect.adjustments]
        for ref, needles in refs:
            lines = (SHOWDOWN / ref.file).read_text(encoding="utf-8").split("\n")
            assert 1 <= ref.line <= len(lines), (effect.id, ref)
            assert any(n in lines[ref.line - 1] for n in needles), (
                effect.id,
                ref,
                needles,
            )
            checked += 1
    assert checked > 100


# --------------------------------------------------------------------------
# Counted effects: sleep, freeze, confusion, paralysis
# --------------------------------------------------------------------------


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_sleep_is_sample_2_3_3_in_champions(data, fmt):
    slp = data[fmt].counted["slp"]
    assert slp.start_distribution == {2: Fraction(1, 3), 3: Fraction(2, 3)}
    assert slp.early_bird_decrement == 2
    assert slp.source.file == "data/mods/champions/conditions.ts"
    # first turn asleep is certain, second wakes with 1/3, third is guaranteed
    assert D.hazards(slp.start_distribution) == [0, Fraction(1, 3), 1]
    # Early Bird takes two off the count per attempt
    assert D.hazards(slp.start_distribution, decrement=2) == [Fraction(1, 3), 1]


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_freeze_thaws_one_in_four_and_is_guaranteed_on_the_third_attempt(data, fmt):
    frz = data[fmt].counted["frz"]
    assert frz.start_distribution == {3: Fraction(1)}
    assert frz.end_chance_per_attempt == Fraction(1, 4)
    assert D.hazards(frz.start_distribution, frz.end_chance_per_attempt) == [
        Fraction(1, 4),
        Fraction(1, 4),
        1,
    ]


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_confusion_keeps_the_base_rule_of_two_to_five(data, fmt):
    conf = data[fmt].counted["confusion"]
    assert conf.start_distribution == {n: Fraction(1, 4) for n in (2, 3, 4, 5)}
    assert conf.variants == {"axekick": {n: Fraction(1, 3) for n in (3, 4, 5)}}
    assert D.hazards(conf.start_distribution) == [
        0,
        Fraction(1, 4),
        Fraction(1, 3),
        Fraction(1, 2),
        1,
    ]
    # The 33% self-hit chance is recorded as an event, not a length.
    assert conf.end_chance_per_attempt is None
    assert conf.event_chance_per_attempt == Fraction(33, 100)


@needs_showdown
@pytest.mark.parametrize("fmt", FORMATS)
def test_full_paralysis_is_one_in_eight_and_has_no_length(data, fmt):
    par = data[fmt].counted["par"]
    assert par.event_chance_per_attempt == Fraction(1, 8)
    assert par.end_chance_per_attempt is None
    assert par.start_distribution == {}


# --------------------------------------------------------------------------
# The document is generated, not typed
# --------------------------------------------------------------------------


@needs_showdown
def test_markdown_is_deterministic_and_names_each_effect_with_its_source(data):
    text = D.render_markdown(data, commit="0" * 40)
    assert text == D.render_markdown(data, commit="0" * 40)
    assert "Tailwind" in text
    assert "data/moves.ts:" in text
    assert "data/mods/champions/conditions.ts:" in text
    for fmt in FORMATS:
        assert D.FORMAT_MODS[fmt] in text


@needs_showdown
def test_committed_document_matches_a_fresh_generation(data):
    committed = ROOT / "docs" / "DURATIONS.md"
    assert committed.exists(), "run: python -m wpa.durations --out docs/DURATIONS.md"
    fresh = D.render_markdown(data, commit=D.showdown_commit(SHOWDOWN))
    assert committed.read_text(encoding="utf-8") == fresh


# --------------------------------------------------------------------------
# Turn arithmetic (no Showdown needed)
# --------------------------------------------------------------------------


def test_mid_turn_start_ends_on_the_residual_of_start_plus_duration_minus_one():
    # Tailwind (4 turns) set by a move on turn 3: in force turns 3, 4, 5, 6
    assert D.scheduled_end_turn(3, D.ACTION, 4) == 6


def test_start_after_residual_or_before_turn_one_loses_no_turn():
    # A replacement switching in after the turn's residual: first residual is next turn.
    assert D.scheduled_end_turn(3, D.AFTER_RESIDUAL, 5) == 8
    # Leads switch in at turn 0, before any residual, even if marked as an action.
    assert D.scheduled_end_turn(0, D.ACTION, 5) == 5


def test_turns_remaining_counts_the_decision_turn_itself():
    # Tailwind from turn 3 is in force on turns 3-6.
    assert D.turns_remaining(4, 3, D.ACTION, 4) == 3
    assert D.turns_remaining(6, 3, D.ACTION, 4) == 1
    assert D.turns_remaining(7, 3, D.ACTION, 4) == 0  # gone: never negative
    assert D.turns_remaining(3, 3, D.ACTION, 4) == 4


def test_turns_remaining_takes_no_end_event():
    """Leakage rule: the function cannot even be handed the future."""
    names = set(inspect.signature(D.turns_remaining).parameters)
    assert names == {"current_turn", "start_turn", "start_phase", "duration"}
    assert not any("end" in n for n in names)
