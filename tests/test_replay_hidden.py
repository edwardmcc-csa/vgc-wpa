"""Week 12 Task 5: the replay report for a game without team sheets. Your own
team comes from a team paste (as Showdown exports it); the opponent's six
species from team preview, and the rest of their sheet is believed
(`wpa.hidden`). A game that shows the sheets can be read as if it did not
(`--hidden`), to see what you could have known."""

from __future__ import annotations

import pytest

from tests.test_replay import LOG, RECORDS, SHEET1, SHEET2, TAG
from wpa import replay as RP
from wpa.team_sheets import SheetMon, sheets_from_log

TEAM = """\
Gholdengo @ Choice Specs
Ability: Good as Gold
Level: 50
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Nite (Dragonite) (F) @ Choice Band
Ability: Multiscale
Adamant Nature
- Extreme Speed
- Hurricane
- Fire Punch
- Protect

Kingambit (M) @ Black Glasses
Ability: Defiant
- Sucker Punch
- Iron Head
- Low Kick
- Protect

Sneasler @ White Herb
Ability: Unburden
- Fake Out
- Close Combat
- Dire Claw
- Protect

Garchomp (F) @ Life Orb
Ability: Rough Skin
- Earthquake
- Dragon Claw
- Rock Slide
- Protect

Sinistcha
Ability: Hospitality
- Matcha Gotcha
- Rage Powder
- Trick Room
- Protect
"""

POKE = [
    "|poke|p1|Kingambit, L50, M|",
    "|poke|p1|Dragonite, L50, F|",
    "|poke|p1|Gholdengo, L50|",
    "|poke|p1|Sneasler, L50, M|",
    "|poke|p1|Garchomp, L50, F|",
    "|poke|p1|Sinistcha, L50|",
    "|poke|p2|Basculegion, L50, M|",
    "|poke|p2|Incineroar, L50, M|",
    "|poke|p2|Amoonguss, L50, F|",
    "|poke|p2|Archaludon, L50, M|",
    "|poke|p2|Whimsicott, L50, M|",
    "|poke|p2|Floette-Eternal, L50, F|",
]
# the game as a format without open team sheets shows it
NO_SHEETS = LOG.replace(SHEET1 + "\n" + SHEET2 + "\n", "").replace(
    "|teampreview|4", "\n".join([*POKE, "|teampreview|4"])
)


def test_a_team_paste_is_read_as_showdown_exports_it():
    team = RP.parse_team(TEAM)
    assert [m["species"] for m in team] == [
        "Gholdengo",
        "Dragonite",
        "Kingambit",
        "Sneasler",
        "Garchomp",
        "Sinistcha",
    ]
    nite = team[1]
    assert nite["name"] == "Nite"
    assert (nite["item"], nite["ability"], nite["nature"]) == (
        "Choice Band",
        "Multiscale",
        "Adamant",
    )
    assert nite["moves"] == ["Extreme Speed", "Hurricane", "Fire Punch", "Protect"]
    assert nite["gender"] == "F"
    assert team[0]["evs"] == {"hp": 2, "spa": 32, "spe": 32}
    assert team[5]["item"] == ""


def test_a_game_without_sheets_gets_yours_from_the_paste_and_their_species():
    assert RP.has_sheets(LOG) and not RP.has_sheets(NO_SHEETS)
    log = RP.with_sheets(NO_SHEETS, "p1", TEAM)
    assert RP.has_sheets(log)
    sheets = sheets_from_log(log)
    # yours in team preview's order, whatever the paste's
    assert [m.species for m in sheets["p1"]] == [
        "kingambit",
        "dragonite",
        "gholdengo",
        "sneasler",
        "garchomp",
        "sinistcha",
    ]
    assert sheets["p1"][1] == SheetMon(
        2,
        "dragonite",
        "choiceband",
        "multiscale",
        ("extremespeed", "hurricane", "firepunch", "protect"),
        "Adamant",
    )
    # theirs: the species team preview shows, and nothing else
    assert sheets["p2"][5] == SheetMon(6, "floetteeternal", "", "", (), "")
    assert RP.sheet_names(log)["p2"][0] == "Basculegion"
    # the lines go in after team preview starts, as Showdown puts them
    lines = log.split("\n")
    assert lines.index("|teampreview|4") < min(
        i for i, x in enumerate(lines) if x.startswith("|showteam|")
    )


def test_a_paste_that_is_not_the_team_in_the_game_is_refused():
    other = TEAM.replace("Sinistcha", "Amoonguss")
    with pytest.raises(RP.ReplayError, match="Sinistcha"):
        RP.with_sheets(NO_SHEETS, "p1", other)


def test_the_games_to_read_hidden():
    games = [(TAG, NO_SHEETS, "regma")]
    with pytest.raises(RP.ReplayError, match="--team"):
        RP.prepare(games, "Ann", None)
    got, hidden = RP.prepare(games, "Ann", TEAM)
    assert hidden and RP.has_sheets(got[0][1])
    got, hidden = RP.prepare([(TAG, LOG, "regma")], "Ann", None)
    assert not hidden and got[0][1] == LOG
    got, hidden = RP.prepare([(TAG, LOG, "regma")], "Ann", None, hidden=True)
    assert hidden and got[0][1] == LOG


def test_the_report_says_when_their_sheet_was_hidden():
    recs = [dict(r, sheets="hidden") for r in RECORDS]
    text = RP.game_report(TAG, LOG, recs, "p1", top=1)
    assert "Their team sheet was hidden" in text
    assert "Their team sheet was hidden" not in RP.game_report(
        TAG, LOG, RECORDS, "p1", top=1
    )
