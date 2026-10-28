"""Tests for the (a)/(b)/(c) classification of timed effects (Week 4 Task 7).

(a) fixed length given what a decision point can see, (b) random with a known
distribution given the observable count, (c) hidden from the observer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wpa import durations as D
from wpa import timers as T

ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)

REF = D.SourceRef("data/moves.ts", 1)


def effect(
    id: str,
    base: int,
    random_range: tuple[int, int] | None = None,
    modifiers: tuple[D.Modifier, ...] = (),
) -> D.TimedEffect:
    return D.TimedEffect(
        "Moves",
        id,
        id.title(),
        None,
        base,
        modifiers,
        (),
        random_range,
        "duration",
        REF,
    )


def test_a_fixed_length_effect_is_class_a_and_says_so():
    clay = D.Modifier("item", "lightclay", 8, "source.hasItem('lightclay')", REF)
    cls, note = T.length_class(effect("lightscreen", 5, modifiers=(clay,)))
    assert cls == "a"
    assert "5 turns" in note and "lightclay 8" in note


def test_an_effect_with_a_random_range_is_class_b():
    cls, note = T.length_class(effect("partiallytrapped", 5, random_range=(5, 7)))
    assert cls == "b"
    assert "5-6" in note


def test_rampage_length_is_random_even_though_the_table_shows_a_base():
    # lockedmove draws its length in onStart (this.random(2, 4)), not in a callback
    cls, note = T.length_class(effect("lockedmove", 2))
    assert cls == "b"
    assert "2-3" in note


def test_a_weather_with_no_length_is_permanent_not_hidden():
    cls, note = T.length_class(effect("deltastream", 0))
    assert cls == "a"
    assert "permanent" in note


def test_counted_effects_are_all_class_b_except_the_toxic_stage_counter():
    classes = {
        k: T.counted_class(k)[0] for k in ("slp", "frz", "confusion", "par", "tox")
    }
    assert classes == {"slp": "b", "frz": "b", "confusion": "b", "par": "b", "tox": "a"}


@needs_showdown
def test_every_effect_in_both_formats_is_classified_and_none_is_hidden():
    tables = D.load_all(SHOWDOWN)
    b_ids: set[str] = set()
    for table in tables.values():
        for id, e in table.timed.items():
            cls, _ = T.length_class(e)
            assert cls in ("a", "b"), id
            if cls == "b":
                b_ids.add(id)
        for id in table.counted:
            cls, _ = T.counted_class(id)
            if cls == "b":
                b_ids.add(id)
    assert b_ids == {"partiallytrapped", "lockedmove", "slp", "frz", "confusion", "par"}


@needs_showdown
def test_committed_timers_doc_carries_the_fresh_class_table():
    tables = D.load_all(SHOWDOWN)
    text = (ROOT / "docs" / "TIMERS.md").read_text(encoding="utf-8")
    start, end = "<!-- classes:start -->", "<!-- classes:end -->"
    assert start in text and end in text
    block = text.split(start, 1)[1].split(end, 1)[0].strip()
    assert block == T.render_classes(tables).strip()
