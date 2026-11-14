"""Week 13 Task 3: the PO's team, loaded in. A team paste is checked against
the app's Stats screen (each Pokemon's six stats at level 50, from its stat
points and nature), and what the format's data has not seen is named, so the
advice can say its numbers are rough. The stats below are two Pokemon read off
an app Stats screen on 13 Nov, checked by hand that evening."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from tests.test_more_mechanics import needs_showdown
from tests.test_resolver import ROOT
from wpa import team_check as TC
from wpa.replay import parse_team

PASTE = """\
Garchomp (M) @ Life Orb
Ability: Rough Skin
Level: 50
EVs: 30 Atk / 4 Def / 32 Spe
Jolly Nature
- Protect

Sableye (F) @ Sitrus Berry
Ability: Prankster
Level: 50
EVs: 32 HP / 16 Def / 18 SpD
Careful Nature
- Protect
"""


@pytest.fixture(scope="module")
def dex():
    from wpa.team_sheets import load_dexes

    return load_dexes(ROOT / "pokemon-showdown")["regmb"]


@needs_showdown
def test_six_stats_at_level_50_from_stat_points_and_nature(dex):
    chomp, eye = parse_team(PASTE)
    want = (183, 180, 119, 90, 105, 169)
    assert TC.stats(chomp, dex) == dict(zip(TC.STATS, want, strict=True))
    want = (157, 95, 111, 76, 113, 70)
    assert TC.stats(eye, dex) == dict(zip(TC.STATS, want, strict=True))


def test_more_than_66_stat_points_or_32_in_a_stat_is_flagged():
    over = PASTE.replace("EVs: 30 Atk / 4 Def / 32 Spe", "EVs: 30 Atk / 8 Def / 33 Spe")
    chomp = parse_team(over)[0]
    assert TC.problems(chomp) == [
        "71 stat points (66 at most)",
        "33 in Spe (32 at most)",
    ]
    assert TC.problems(parse_team(PASTE)[0]) == []


def test_what_the_formats_statistics_have_not_seen():
    usage = {
        "sneasler": NS(count=300.0),
        "garchomp": NS(count=5694.0),
        "basculegionf": NS(count=6.0),
    }
    # 6,000 Pokemon in all is 1,000 teams: Basculegion-F is on 0.6% of them
    missing, rare = TC.unseen(["sneasler", "golisopod", "basculegionf"], usage)
    assert missing == ["golisopod"] and rare == ["basculegionf"]
    note = TC.rough_note(["Golisopod"], ["Basculegion-F"])
    assert note == (
        "Your Golisopod is not in this format's statistics, and your "
        "Basculegion-F is on under 1% of teams: the numbers for them are rough."
    )
    assert TC.rough_note([], []) == ""


def test_a_species_counts_its_mega_forms_too():
    """The statistics count each Mega form apart (Reg M-B, June: Raichu 1.9%,
    Raichu-Mega-X 2.0%, Raichu-Mega-Y 10.4%): a Raichu is on any of them.
    Raichu-Alola is another species."""
    usage = {
        "sneasler": NS(count=60000),
        "raichu": NS(count=60),  # 0.6% of teams on its own
        "raichumegax": NS(count=600),
        "raichualola": NS(count=600),
    }
    assert TC.unseen(["sneasler", "raichu"], usage) == ([], [])
    usage = {"sneasler": NS(count=60000), "raichualola": NS(count=600)}
    assert TC.unseen(["raichu"], usage) == (["raichu"], [])
    usage = {"sneasler": NS(count=60000), "raichumegax": NS(count=600)}
    assert TC.unseen(["raichu"], usage) == ([], [])


def test_my_team_txt_is_the_team_unless_another_is_given(tmp_path):
    assert TC.default_team(None, tmp_path) is None
    (tmp_path / "my_team.txt").write_text(PASTE)
    assert TC.default_team(None, tmp_path) == tmp_path / "my_team.txt"
    other = tmp_path / "other.txt"
    assert TC.default_team(other, tmp_path) == other


def test_the_check_reads_beside_the_apps_stats_screen(dex):
    text = TC.report(PASTE, dex)
    assert (
        "Garchomp: HP 183, Attack 180, Defense 119, Sp. Atk 90, Sp. Def 105, Speed 169"
        in text
    )
    assert "Sableye: HP 157" in text and "66 stat points" in text


def test_the_replay_report_asks_for_the_team_file_too():
    """A game with no sheets and no paste: the message names both ways."""
    from tests.test_replay_hidden import NO_SHEETS, TAG
    from wpa import replay as RP

    with pytest.raises(RP.ReplayError, match="my_team.txt"):
        RP.prepare([(TAG, NO_SHEETS, "regma")], "Ann", None)
