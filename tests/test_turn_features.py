"""Tests for group H, what each side can do this turn (Week 8 Task 3).

For each side's active Pokemon: Fake Out still works (it has not moved since it
came in), locked by a Choice item into the move it used, Protect ready (or risky
after one that worked last turn); and whether the side still has its Mega
Evolution to use. Only public information: open team sheets and the board.
"""

# ruff: noqa: E501

from __future__ import annotations

from wpa import features as F
from wpa.team_sheets import Dex, SheetMon
from wpa.timer_join import JoinedTimers


def sp(spe):
    return {
        "baseStats": {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": spe},
        "types": ["Normal"],
        "abilities": {"0": "X"},
    }


DEX = Dex(
    species={
        "inci": sp(60),
        "fini": sp(85),
        "zard": sp(100),
        "zardmegay": sp(130),
        "back": sp(50),
        "slow": sp(40),
    },
    moves={},
    items={
        "choicescarf": {"megaStone": None},
        "sitrusberry": {"megaStone": None},
        "charizarditey": {"megaStone": {"Zard": "Zard-Mega-Y"}},
    },
)


def mon(pos, species, item, moves):
    return SheetMon(pos, species, item, "x", tuple(moves), "")


OUR = (
    mon(1, "inci", "sitrusberry", ["fakeout", "flareblitz", "protect", "partingshot"]),
    mon(
        2,
        "fini",
        "choicescarf",
        ["moonblast", "dazzlinggleam", "calmmind", "drainingkiss"],
    ),
    mon(3, "zard", "charizarditey", ["heatwave", "solarbeam", "protect", "airslash"]),
    mon(4, "back", "sitrusberry", ["protect", "tackle", "growl", "rest"]),
    mon(5, "slow", "sitrusberry", ["tackle", "growl", "rest", "protect"]),
    mon(6, "slow", "sitrusberry", ["tackle", "growl", "rest", "protect"]),
)


def pk(species, hp, active=False, **kw):
    return {
        "species": species,
        "hp_fraction": hp,
        "active": active,
        "fainted": False,
        "mega": kw.get("mega", False),
        "boosts": {},
        "status": "",
        "item": kw.get("item", ""),
        "moved": kw.get("moved", False),
        "last_move": kw.get("last_move", ""),
        "protect_streak": kw.get("streak", 0),
    }


def state(our):
    their = [pk(m.species, 0.0, item=m.item) for m in OUR]
    their[0] = pk("inci", 1.0, True, item="sitrusberry")
    their[1] = pk("fini", 1.0, True, item="choicescarf")
    return {
        "turn": 2,
        "decision_index": 0,
        "game_index": None,
        "set_score_entering_game": None,
        "observations": [],
        "our_pokemon": our,
        "opp_pokemon": their,
    }


def h(our):
    return F.state_features(
        [state(our)],
        0,
        "p1",
        JoinedTimers(moment="turn_start"),
        {"p1": OUR, "p2": OUR},
        DEX,
        None,
        "H",
    )


def base(**kw):
    our = [pk(m.species, 0.0, item=m.item) for m in OUR]
    our[0] = pk("inci", 1.0, True, item="sitrusberry", **kw.get("inci", {}))
    our[1] = pk("fini", 1.0, True, item="choicescarf", **kw.get("fini", {}))
    our[2] = pk("zard", 0.8, item="charizarditey", **kw.get("zard", {}))
    return our


def test_fake_out_works_until_the_pokemon_has_moved():
    assert h(base())["h_our_fakeout_n"] == 1
    assert h(base(inci={"moved": True}))["h_our_fakeout_n"] == 0
    assert h(base())["h_their_fakeout_n"] == 1  # their Inci just came in too


def test_a_choice_item_locks_after_the_first_move():
    assert h(base())["h_our_locked_n"] == 0
    assert (
        h(base(fini={"moved": True, "last_move": "moonblast"}))["h_our_locked_n"] == 1
    )


def test_protect_is_ready_or_risky_after_one_that_worked():
    row = h(base())
    assert (
        row["h_our_protect_ready_n"] == 1 and row["h_our_protect_risky_n"] == 0
    )  # only Inci has Protect
    row = h(base(inci={"streak": 1}))
    assert row["h_our_protect_ready_n"] == 0 and row["h_our_protect_risky_n"] == 1


def test_mega_evolution_is_available_until_used():
    row = h(base())
    assert row["h_our_mega_available"] == 1 and row["h_our_mega_used"] == 0
    our = base(zard={"mega": True})
    row = h(our)
    assert row["h_our_mega_available"] == 0 and row["h_our_mega_used"] == 1
    assert h(base())["h_their_mega_available"] == 1  # their Zard on the bench, unseen


def test_group_h_reads_only_public_fields():
    from tests.test_features import GuardedMon, GuardedState

    class Mon(GuardedMon):
        ALLOWED = GuardedMon.ALLOWED | {
            "mega",
            "boosts",
            "status",
            "item",
            "moved",
            "last_move",
            "protect_streak",
        }

    s = state(base())
    s = dict(
        s,
        our_pokemon=[Mon(p) for p in s["our_pokemon"]],
        opp_pokemon=[Mon(p) for p in s["opp_pokemon"]],
    )
    F.state_features(
        [GuardedState(s)],
        0,
        "p1",
        JoinedTimers(moment="turn_start"),
        {"p1": OUR, "p2": OUR},
        DEX,
        None,
        "H",
    )
    assert "h_our_fakeout_n" in F.columns("H")
    perm = F.mirror_permutation(F.columns("H"))
    cols = F.columns("H")
    assert cols[perm[cols.index("h_our_locked_n")]] == "h_their_locked_n"
