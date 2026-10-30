"""Tests for wpa/team_sheets.py (Week 5 Task 4): the open team sheets as
features.

The sheet (six Pokemon, each with item, ability and four moves) is public
before the game starts. What a decision may also use is which of those six it
has *seen*, from the state. Which four were brought is never an input.
"""

# ruff: noqa: E501  (battle-log fixture lines are long by nature)

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wpa import team_sheets as S

FIXTURES = Path(__file__).parent / "fixtures" / "w5"
LOGS = json.loads((FIXTURES / "logs" / "logs.json").read_text(encoding="utf-8"))
ROOT = Path(__file__).resolve().parent.parent
SHOWDOWN = ROOT / "pokemon-showdown"

needs_showdown = pytest.mark.skipif(
    shutil.which("node") is None or not (SHOWDOWN / "dist" / "sim" / "dex.js").exists(),
    reason="needs Node and the built pokemon-showdown submodule",
)


def move(category="Physical", priority=0, target="normal", bp=80):
    return {
        "category": category,
        "priority": priority,
        "target": target,
        "basePower": bp,
    }


MINI = S.Dex(
    species={
        "charizard": {"name": "Charizard", "abilities": {"0": "Blaze"}},
        "charizardmegay": {"name": "Charizard-Mega-Y", "abilities": {"0": "Drought"}},
        "whimsicott": {"name": "Whimsicott", "abilities": {"0": "Prankster"}},
    },
    moves={
        "tailwind": move("Status"),
        "trickroom": move("Status", priority=-7),
        "fakeout": move(priority=3),
        "suckerpunch": move(priority=1),
        "heatwave": move("Special", target="allAdjacentFoes", bp=95),
        "ragepowder": move("Status", priority=2),
        "lightscreen": move("Status"),
        "protect": move("Status", priority=4),
        "flareblitz": move(),
    },
    items={
        "charizarditey": {
            "name": "Charizardite Y",
            "megaStone": {"Charizard": "Charizard-Mega-Y"},
        },
        "sitrusberry": {"name": "Sitrus Berry", "megaStone": None},
    },
)


def mon(pos, species, item="sitrusberry", ability="", moves=()):
    return S.SheetMon(pos, species, item, ability, tuple(moves), "")


# --------------------------------------------------------------------------
# Reading the sheets
# --------------------------------------------------------------------------


def test_sheets_from_a_real_log_give_six_pokemon_a_side_in_sheet_order():
    sheets = S.sheets_from_log(LOGS["gen9championsvgc2026regma-2580291588"])
    p1 = sheets["p1"]
    assert [m.position for m in p1] == [1, 2, 3, 4, 5, 6]
    assert p1[0].species == "talonflame"
    assert p1[0].ability == "galewings" and p1[0].item == "sharpbeak"
    assert "tailwind" in p1[0].moves
    assert p1[5].species == "rotomwash"
    assert p1[0].nature == ""  # never shown in Reg M-A


def test_nature_is_on_the_reg_m_b_sheet():
    sheets = S.sheets_from_log(LOGS["gen9championsvgc2026regmb-2634168141"])
    assert all(m.nature for m in sheets["p1"])


@pytest.mark.parametrize("tag", sorted(LOGS))
def test_the_states_list_each_side_in_sheet_order(tag):
    sheets = S.sheets_from_log(LOGS[tag])
    for role, other in (("p1", "p2"), ("p2", "p1")):
        states = json.loads(
            (FIXTURES / f"{tag}-{role}.json").read_text(encoding="utf-8")
        )
        first = states[0]
        assert S.match_to_state(sheets[role], first["our_pokemon"]) == [
            0,
            1,
            2,
            3,
            4,
            5,
        ]
        assert S.match_to_state(sheets[other], first["opp_pokemon"]) == [
            0,
            1,
            2,
            3,
            4,
            5,
        ]


def test_matching_by_species_when_the_order_differs():
    sheet = (mon(1, "charizard"), mon(2, "whimsicott"))
    side = [{"species": "whimsicott"}, {"species": "charizard"}]
    assert S.match_to_state(sheet, side) == [1, 0]


# --------------------------------------------------------------------------
# Capabilities, each a rule in code
# --------------------------------------------------------------------------


def test_capabilities_come_from_moves_and_abilities():
    whim = mon(
        1,
        "whimsicott",
        ability="prankster",
        moves=["tailwind", "lightscreen", "protect"],
    )
    assert S.capabilities(whim, MINI) == {"tailwind", "prankster", "screens"}
    cat = mon(
        2,
        "charizard",
        ability="blaze",
        moves=["fakeout", "suckerpunch", "heatwave", "ragepowder"],
    )
    assert S.capabilities(cat, MINI) == {"fakeout", "priority", "spread", "redirection"}
    tr = mon(3, "charizard", ability="intimidate", moves=["trickroom", "flareblitz"])
    assert S.capabilities(tr, MINI) == {"trickroom", "intimidate"}


def test_a_mega_stone_adds_the_mega_forms_ability():
    y = mon(1, "charizard", item="charizarditey", ability="blaze", moves=["flareblitz"])
    assert "sun" in S.capabilities(y, MINI)
    assert "sun" not in S.capabilities(mon(1, "charizard", ability="blaze"), MINI)


def test_trapping_counts_a_mega_stones_shadow_tag_and_perish_song_is_its_own():
    dex = S.Dex(
        species={
            **MINI.species,
            "gengar": {"name": "Gengar", "abilities": {"0": "Cursed Body"}},
            "gengarmega": {"name": "Gengar-Mega", "abilities": {"0": "Shadow Tag"}},
        },
        moves={**MINI.moves, "perishsong": move("Status"), "meanlook": move("Status")},
        items={
            **MINI.items,
            "gengarite": {"name": "Gengarite", "megaStone": {"Gengar": "Gengar-Mega"}},
        },
    )
    mega = mon(
        1,
        "gengar",
        item="gengarite",
        ability="cursedbody",
        moves=["perishsong", "protect"],
    )
    assert {"trapping", "perishsong"} <= S.capabilities(mega, dex)
    plain = mon(1, "gengar", ability="cursedbody", moves=["perishsong"])
    assert "trapping" not in S.capabilities(plain, dex)
    looker = mon(2, "gengar", ability="cursedbody", moves=["meanlook"])
    assert "trapping" in S.capabilities(looker, dex)


def test_fake_out_and_protect_are_not_counted_as_priority_attacks():
    caps = S.capabilities(mon(1, "charizard", moves=["fakeout", "protect"]), MINI)
    assert "priority" not in caps and "fakeout" in caps


# --------------------------------------------------------------------------
# Per-side features from the sheet and what the state shows
# --------------------------------------------------------------------------


def pk(species, hp, active=False, fainted=False):
    return {"species": species, "hp_fraction": hp, "active": active, "fainted": fainted}


SHEET = (
    mon(1, "whimsicott", ability="prankster", moves=["tailwind"]),
    mon(2, "charizard", ability="intimidate", moves=["fakeout"]),
    mon(3, "charizard", item="charizarditey", ability="blaze", moves=["heatwave"]),
    mon(4, "whimsicott", moves=["trickroom"]),
    mon(5, "whimsicott", moves=["ragepowder"]),
    mon(6, "whimsicott", moves=["lightscreen"]),
)


def side_state():
    return [
        pk("whimsicott", 0.5, active=True),  # seen, active
        pk("charizard", 0.0, fainted=True),  # seen, fainted
        pk("charizard", 0.8),  # seen, on the bench
        pk("whimsicott", 0.0),  # not seen
        pk("whimsicott", 0.0),  # not seen
        pk(
            "whimsicott", 0.0, active=True
        ),  # active at 0: just switched in? no: unseen rule
    ]


def test_side_features_split_each_capability_by_active_bench_and_unseen():
    side = side_state()
    side[5] = pk("whimsicott", 1.0, active=True)
    f = S.side_features(SHEET, side, MINI, "their")
    assert f["their_tailwind_active"] == 1
    assert f["their_intimidate_active"] == 0  # the Intimidate user has fainted
    assert f["their_intimidate_bench"] == 0
    assert f["their_sun_bench"] == 1 and f["their_spread_bench"] == 1
    assert f["their_trickroom_unseen"] == 1
    assert f["their_redirection_unseen"] == 1
    assert f["their_screens_active"] == 1
    assert f["their_unseen"] == 2
    assert f["their_unseen_pos4"] == 1 and f["their_unseen_pos5"] == 1
    assert f["their_unseen_pos1"] == 0
    assert f["their_unseen_bottom2"] == 1


def test_every_feature_name_is_present_even_when_zero():
    f = S.side_features(SHEET, side_state(), MINI, "our")
    assert set(f) == set(S.feature_names("our"))


class Guarded(dict):
    """A Pokemon record that fails on any field the features may not read."""

    ALLOWED = {"species", "hp_fraction", "fainted", "active"}

    def __getitem__(self, key):
        if key not in self.ALLOWED:
            raise AssertionError(f"side_features read {key!r}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in self.ALLOWED:
            raise AssertionError(f"side_features read {key!r}")
        return super().get(key, default)


def test_features_read_only_what_the_player_can_see():
    side = [
        Guarded({**p, "gimmick": "mega", "brought": True, "outcome": True})
        for p in side_state()
    ]
    S.side_features(SHEET, side, MINI, "their")  # raises if anything else is read


def test_which_unseen_pokemon_were_brought_changes_nothing():
    # Two games identical so far; in one, sheet slots 4 and 5 were brought, in the
    # other slots 5 and 6. The state shows neither, so the features must agree.
    a = side_state()
    b = side_state()
    b[3] = pk("whimsicott", 0.0)
    assert S.side_features(SHEET, a, MINI, "their") == S.side_features(
        SHEET, b, MINI, "their"
    )


# --------------------------------------------------------------------------
# The side file
# --------------------------------------------------------------------------


def test_the_sheet_file_round_trips(tmp_path):
    path = tmp_path / "sheets.jsonl.gz"
    games = [
        (tag, tag.split("-")[0][20:].removesuffix("bo3"), S.sheets_from_log(log))
        for tag, log in LOGS.items()
    ]
    assert S.write_sheet_file(path, games) == 3
    back = S.read_sheet_file(path)
    for tag, fmt, sheets in games:
        assert back[tag] == (fmt, sheets)


# --------------------------------------------------------------------------
# With the real Showdown data
# --------------------------------------------------------------------------


@needs_showdown
def test_real_capabilities_of_two_fixture_teams():
    dex = S.load_dexes(SHOWDOWN)["regma"]
    sheets = S.sheets_from_log(LOGS["gen9championsvgc2026regma-2580291588"])
    by_species = {
        m.species: S.capabilities(m, dex) for m in sheets["p1"] + sheets["p2"]
    }
    assert "tailwind" in by_species["talonflame"]
    assert {"fakeout", "priority"} <= by_species["kangaskhan"]
    assert "spread" in by_species["sylveon"]  # Hyper Voice
    assert "rain" in by_species["pelipper"]  # Drizzle
    assert "intimidate" in by_species["arcaninehisui"]


def test_the_prevalence_report_counts_teams_with_each_capability_by_format():
    report = S.Prevalence()
    for tag, log in LOGS.items():
        fmt = tag.split("-")[0][20:].removesuffix("bo3")
        report.add(fmt, S.sheets_from_log(log), MINI)
    assert report.teams == {"regma": 4, "regmb": 2}
    text = report.describe()
    assert "regma: 4 team sheets" in text and "regmb: 2 team sheets" in text
