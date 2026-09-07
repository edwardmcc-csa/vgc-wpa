"""Parses a |showteam| protocol line field by field, per pokemon-showdown's
own packed-team spec (pokemon-showdown/sim/teams.ts's Team.unpack), read
directly rather than guessed from a few examples. See docs/SHEET-FIELDS.md
for the confirmed findings across 20 real logs.

wpa/sheets.py doesn't exist yet; written first and expected to fail.
"""

from wpa.sheets import parse_showteam_message

# A real |showteam| line from battle_logs/logs_gen9championsvgc2026regma.json
REAL_SHOWTEAM_LINE = (
    "|showteam|p1|Golurk||Golurkite|IronFist|"
    "Poltergeist,HeadlongRush,Protect,PhantomForce||||||50|"
    "]Torkoal||Charcoal|Drought|Eruption,HeatWave,Protect,EarthPower|||M|||50|"
)


def test_parses_role_and_all_pokemon():
    role, sheets = parse_showteam_message(REAL_SHOWTEAM_LINE)

    assert role == "p1"
    assert len(sheets) == 2


def test_parses_core_fields():
    _, sheets = parse_showteam_message(REAL_SHOWTEAM_LINE)
    golurk = sheets[0]

    assert golurk.species == "Golurk"
    assert golurk.item == "Golurkite"
    assert golurk.ability == "IronFist"
    assert golurk.moves == ["Poltergeist", "HeadlongRush", "Protect", "PhantomForce"]
    assert golurk.level == 50


def test_genderless_species_has_no_gender():
    _, sheets = parse_showteam_message(REAL_SHOWTEAM_LINE)
    assert sheets[0].gender == ""


def test_gendered_species_has_gender():
    _, sheets = parse_showteam_message(REAL_SHOWTEAM_LINE)
    assert sheets[1].gender == "M"


def test_ev_nature_iv_shiny_tera_are_absent_in_this_sample():
    _, sheets = parse_showteam_message(REAL_SHOWTEAM_LINE)
    for mon in sheets:
        assert mon.nature == ""
        assert mon.evs is None
        assert mon.ivs is None
        assert mon.shiny is False
        assert mon.tera_type is None
