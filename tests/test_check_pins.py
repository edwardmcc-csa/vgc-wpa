"""Tests for scripts/check_pins.py's pin-parsing and drift-detection logic.

scripts/check_pins.py does not exist yet; written first and expected to fail.
"""

import pytest

from scripts.check_pins import check_drift, parse_pin

SAMPLE_PINS = """\
# Pinned versions

Recorded: 2026-09-05T16:30:49Z

- fork commit: d79f9532947ac114dce1dda2456a590afcd375b2
- pokemon-showdown submodule: 913da3602a3aa1db79f9fdc5d5222eaf8d39569d
- poke-env: 379a04628e42b2a2c94790c0788204b652f7ae1b
- python: Python 3.14.3
- node: v26.7.0
"""


def test_parse_pin_finds_recorded_sha():
    assert (
        parse_pin(SAMPLE_PINS, "pokemon-showdown submodule")
        == "913da3602a3aa1db79f9fdc5d5222eaf8d39569d"
    )
    assert (
        parse_pin(SAMPLE_PINS, "poke-env") == "379a04628e42b2a2c94790c0788204b652f7ae1b"
    )


def test_parse_pin_missing_name_raises():
    with pytest.raises(ValueError):
        parse_pin(SAMPLE_PINS, "something-not-recorded")


def test_check_drift_matching_shas_returns_none():
    sha = "913da3602a3aa1db79f9fdc5d5222eaf8d39569d"
    assert check_drift("pokemon-showdown submodule", expected=sha, actual=sha) is None


def test_check_drift_mismatched_shas_returns_message():
    message = check_drift(
        "poke-env",
        expected="379a04628e42b2a2c94790c0788204b652f7ae1b",
        actual="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    assert message is not None
    assert "poke-env" in message
    assert "379a04628e42b2a2c94790c0788204b652f7ae1b" in message
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in message


def test_the_damage_calculator_version_is_pinned_too(tmp_path):
    from scripts.check_pins import calc_version, parse_version

    pins = SAMPLE_PINS + "- @smogon/calc: 0.12.0\n"
    assert parse_version(pins, "@smogon/calc") == "0.12.0"
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        '{"packages": {"node_modules/@smogon/calc": {"version": "0.12.0"}}}',
        encoding="utf-8",
    )
    assert calc_version(lock) == "0.12.0"


def test_both_pinned_showdown_copies_are_checked_for_drift():
    """Week 14: a second copy of Showdown's code for Reg M-C (Showdown's current
    code dropped M-A's rules). Both copies have a recorded commit, and the
    drift check reads each from its own folder."""
    from scripts.check_pins import PINS_FILE, SHOWDOWN_COPIES

    assert SHOWDOWN_COPIES == {
        "pokemon-showdown submodule": "pokemon-showdown",
        "pokemon-showdown-mc submodule": "pokemon-showdown-mc",
    }
    text = PINS_FILE.read_text(encoding="utf-8")
    for name in SHOWDOWN_COPIES:
        assert len(parse_pin(text, name)) == 40
