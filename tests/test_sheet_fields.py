"""Regression guard for the Week 3 Task 1 finding: which |showteam| fields
are populated is regulation-dependent, not a fixed format property.
See docs/SHEET-FIELDS.md for the full investigation (40 logs, both
regulations, verified before this was written down).

Uses fixtures already checked into the repo rather than new large files:
tests/fixtures/sample_battles.json (Reg M-B) and a Reg M-A battle from
tests/fixtures/battles/ (Week 2's fixture corpus).
"""

import json
from pathlib import Path

from wpa.fixtures import load_fixture
from wpa.sheets import parse_showteam_message

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _showteam_lines(log: str) -> list[str]:
    return [line for line in log.split("\n") if line.startswith("|showteam|")]


def test_reg_ma_never_reveals_nature_evs_ivs_shiny_or_tera():
    fixture = load_fixture(FIXTURES_DIR / "battles" / "early_forfeit.json")
    assert "regma-" in fixture.tag and "regmabo3" not in fixture.tag

    lines = _showteam_lines(fixture.log)
    assert lines, "expected at least one |showteam| line"

    for line in lines:
        _, sheets = parse_showteam_message(line)
        for mon in sheets:
            assert mon.species and mon.item and mon.ability and mon.moves
            assert mon.level
            assert mon.nature == ""
            assert mon.evs is None
            assert mon.ivs is None
            assert mon.shiny is False
            assert mon.tera_type is None


def test_reg_mb_reveals_nature_but_not_evs_ivs_shiny_or_tera():
    logs = json.loads(
        (FIXTURES_DIR / "sample_battles.json").read_text(encoding="utf-8")
    )
    tag, (_, log) = next(iter(logs.items()))
    assert "regmb-" in tag

    lines = _showteam_lines(log)
    assert lines, "expected at least one |showteam| line"

    for line in lines:
        _, sheets = parse_showteam_message(line)
        for mon in sheets:
            assert mon.species and mon.item and mon.ability and mon.moves
            assert mon.level
            assert mon.nature != ""
            assert mon.evs is None
            assert mon.ivs is None
            assert mon.shiny is False
            assert mon.tera_type is None
