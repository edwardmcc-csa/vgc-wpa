"""Tests for the run with the opponent's sheet blanked (Week 8 Task 5, the plan's
non-negotiable for M4b): the opponent's species are known only once they appear,
and their moves, item and ability only as the log reveals them. Our own sheet
stays whole. Spreads come from the statistics alone."""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_board_actions import T1, log
from tests.test_board_effects import at_turn_start
from wpa import features as F
from wpa.team_sheets import SheetMon, sheets_from_log


def test_the_opponents_sheet_shows_only_what_the_log_revealed():
    lg = log(T1)
    s = at_turn_start(lg, 2)
    full = sheets_from_log(lg)["p2"]
    pub = F.public_sheet(full, s["opp_pokemon"])
    inci, fini, rime = pub[0], pub[1], pub[2]
    assert (
        inci.species == "inci"
        and inci.moves == ("fakeout",)
        and inci.item == "sitrusberry"
    )
    assert inci.ability == "intimidate"
    assert (
        fini.species == "fini"
        and fini.moves == ("moonblast",)
        and fini.item == ""
        and fini.ability == ""
    )
    assert rime == SheetMon(0, "", "", "", (), "")  # never seen
    assert all(
        m.position == 0 and m.nature == "" for m in pub
    )  # no sheet order or nature


def test_the_blanked_board_hides_unseen_species_and_unrevealed_items():
    lg = log(T1)
    s = at_turn_start(lg, 2)
    b = F.blank_state(s)
    opp = b["opp_pokemon"]
    assert opp[2]["species"] == "" and opp[0]["species"] == "inci"
    assert opp[1]["item"] == ""  # Fini's Sitrus Berry was never shown
    assert b["our_pokemon"] == s["our_pokemon"]  # our own side is whole


def test_features_run_on_a_blanked_board_and_drop_what_is_unknown():
    from tests.test_decisions import EMPTY
    from wpa import decisions as D

    lg = log(T1)
    g = D.build_game(lg, EMPTY)
    sheets = sheets_from_log(lg)
    rows = F.rows_for_file_blank(
        "gen9championsvgc2026regma-1",
        "p1",
        g.states["p1"],
        g.joined["p1"],
        sheets,
        F.Dex(species={}, moves={}, items={}),
        EMPTY,
        "ADEH",
    )
    assert rows and all(len(r.values) == len(F.columns("ADEH")) for r in rows)
    cols = F.columns("ADEH")
    # their unseen sheet positions are not known any more
    for r in rows:
        assert all(
            r.values[cols.index(f"e_their_unseen_pos{k}")] == 0 for k in range(1, 7)
        )
