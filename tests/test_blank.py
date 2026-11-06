"""Tests for the run with the opponent's sheet blanked (Week 8 Task 5, the plan's
non-negotiable for M4b). Team preview shows the opponent's six species in sheet
order (PO, 5 Nov 2026: the blank run keeps them, as a real closed-sheet game
does); their moves, item and ability are known only as the log reveals them, and
their nature not at all. Our own sheet stays whole. Spreads come from the
statistics alone."""

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
    assert rime == SheetMon(3, "rime", "", "", (), "")  # seen at team preview only
    assert [m.position for m in pub] == [m.position for m in full]  # preview order
    assert all(m.nature == "" for m in pub)  # no nature


def test_the_blanked_board_keeps_preview_species_and_hides_unrevealed_items():
    lg = log(T1)
    s = at_turn_start(lg, 2)
    b = F.blank_state(s)
    opp = b["opp_pokemon"]
    assert opp[2]["species"] == s["opp_pokemon"][2]["species"] != ""
    assert opp[2]["item"] == ""  # never seen, so its item is unknown
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
    full = F.rows_for_file(
        "gen9championsvgc2026regma-1",
        "p1",
        g.states["p1"],
        g.joined["p1"],
        sheets,
        F.Dex(species={}, moves={}, items={}),
        EMPTY,
        "ADEH",
    )
    # their unseen sheet positions are known from team preview, as with full sheets
    pos = [cols.index(f"e_their_unseen_pos{k}") for k in range(1, 7)]
    assert [[r.values[i] for i in pos] for r in rows] == [
        [r.values[i] for i in pos] for r in full
    ]
    # but not what their Pokemon carry: Fake Out on their sheet is unknown at first
    fake = cols.index("h_their_fakeout_n")
    assert any(b.values[fake] < f.values[fake] for b, f in zip(rows, full))


# Both sheets blanked ("spectator"): blanking only theirs gives the two sides
# different information, so a row and its mirror are not alike and the symmetric
# model's average of the two is off (Week 8: the opponent-only run over-predicted).


def test_the_spectator_board_hides_our_unrevealed_items_too():
    lg = log(T1)
    s = at_turn_start(lg, 2)
    b = F.blank_state(s, both=True)
    ours = b["our_pokemon"]
    unseen = [i for i, p in enumerate(s["our_pokemon"]) if not F._revealed(p)]
    assert unseen and all(ours[i]["item"] == "" for i in unseen)
    assert [p["species"] for p in ours] == [p["species"] for p in s["our_pokemon"]]
    assert b["opp_pokemon"] == F.blank_state(s)["opp_pokemon"]


def test_spectator_rows_drop_our_unknowns_too():
    from tests.test_decisions import EMPTY
    from wpa import decisions as D

    lg = log(T1)
    g = D.build_game(lg, EMPTY)
    sheets = sheets_from_log(lg)
    args = (
        "gen9championsvgc2026regma-1",
        "p2",  # Inci, with Fake Out on its sheet, is p2's
        g.states["p2"],
        g.joined["p2"],
        sheets,
        F.Dex(species={}, moves={}, items={}),
        EMPTY,
        "ADEH",
    )
    one = F.rows_for_file_blank(*args)
    both = F.rows_for_file_blank(*args, both=True)
    cols = F.columns("ADEH")
    fake = cols.index("h_our_fakeout_n")  # our Fake Out, unknown to a spectator
    assert any(o.values[fake] > b.values[fake] for o, b in zip(one, both))


def test_blank_contexts_have_bring_odds_for_both_sides_from_team_preview():
    class Bring:
        def odds(self, fmt, species, prev):
            return {"x": 1.0}

    class Store:
        def for_game(self, tag, log):
            return {}

    lg = log(T1)
    sheets = sheets_from_log(lg)
    dex = F.Dex(species={}, moves={}, items={})
    tag = "gen9championsvgc2026regma-1"
    one = F._blank_contexts(tag, lg, "p1", sheets, dex, None, Store(), Bring())
    both = F._blank_contexts(
        tag, lg, "p1", sheets, dex, None, Store(), Bring(), both=True
    )
    assert set(one(0, sheets).odds) == set(both(0, sheets).odds) == {"p1", "p2"}
