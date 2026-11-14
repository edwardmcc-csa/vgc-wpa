"""Tests for wpa/spreads.py (Week 7 Task 3): spread estimates.

Each Pokemon starts from the spreads Smogon's usage statistics (1500 cutoff)
show for it that month, grouped into a few investment profiles, and the
candidates are re-weighted by what the game shows: the hit points a hit takes
off (bulk and offence) and who moves first (speed). Only what happened before
a decision is used for it.
"""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from wpa import spreads as S
from wpa.team_sheets import SheetMon


def test_spreads_two_points_apart_are_one_profile():
    raw = {
        "Jolly:2/32/0/0/0/32": 30.0,
        "Jolly:0/32/0/0/2/32": 10.0,
        "Adamant:2/32/0/0/0/32": 40.0,
        "Adamant:32/0/28/0/0/6": 15.0,
        "Bold:32/0/32/0/2/0": 5.0,
    }
    c = S.profiles(raw, cover=0.9, most=10)
    assert [x.nature for x in c] == ["adamant", "jolly", "adamant"]
    assert c[1].sps == (2, 32, 0, 0, 0, 32)  # weighted mean, kept to 66 points
    assert sum(x.weight for x in c) == pytest.approx(1.0)
    assert c[0].weight == pytest.approx(40 / 95)


def test_at_most_ten_profiles():
    raw = {f"Hardy:{a}/{b}/0/0/0/0": 1.0 for a in (0, 12, 32) for b in (0, 12, 32)}
    raw.update({f"Bold:{a}/0/{b}/0/0/0": 1.0 for a in (0, 12, 32) for b in (0, 12, 32)})
    assert len(S.profiles(raw, cover=1.0, most=10)) == 10


def test_the_display_bucket_of_champions_hit_points():
    # Champions shows floor(100 * hp / max), at least 1 while standing
    assert S.hp_range(50, 150) == (75, 76)
    assert S.hp_range(100, 150) == (150, 150)
    assert S.hp_range(1, 150) == (1, 2)


def mon(species, nature="", item="", ability="x"):
    return SheetMon(1, species, item, ability, (), nature)


def test_the_prior_keeps_the_sheet_nature_and_has_a_default():
    usage = {
        "kingambit": [
            S.Spread("adamant", (32, 32, 0, 0, 2, 0), 0.7),
            S.Spread("brave", (32, 32, 2, 0, 0, 0), 0.3),
        ]
    }
    assert [s.nature for s in S.prior(usage, mon("kingambit", "Brave"), None)] == [
        "brave"
    ]
    assert len(S.prior(usage, mon("kingambit"), None)) == 2
    (d,) = S.prior(
        {}, mon("unknownmon", "Timid"), None, base_stats={"atk": 50, "spa": 120}
    )
    assert d.nature == "timid" and d.sps == (32, 0, 0, 32, 0, 2) and d.weight == 1.0


def test_a_form_the_statistics_count_under_its_species_takes_its_spreads():
    """Week 13 Task 1: the statistics count Sinistcha-Masterpiece as Sinistcha
    (96 of the resolver check's 892 games) and Maushold-Four as Maushold. Under
    its own name it got the default (full HP and Special Attack), where real
    Sinistchas put their points in the defences, so hits on it were too strong.
    A form the statistics list apart (Basculegion-F) keeps its own; a species
    not listed at all keeps the default."""
    from wpa.team_sheets import Dex

    tea = {"baseSpecies": "Sinistcha", "baseStats": {"atk": 60, "spa": 121}}
    dex = Dex(
        species={
            "sinistcha": {"name": "Sinistcha", **tea},
            "sinistchamasterpiece": {"name": "Sinistcha-Masterpiece", **tea},
            "basculegion": {"name": "Basculegion", "baseSpecies": "Basculegion"},
            "basculegionf": {"name": "Basculegion-F", "baseSpecies": "Basculegion"},
        },
        moves={},
        items={},
    )
    bulky = S.Spread("bold", (32, 0, 15, 0, 19, 0), 1.0)
    usage = {
        "sinistcha": [bulky],
        "basculegion": [S.Spread("adamant", (2, 32, 0, 0, 0, 32), 1.0)],
        "basculegionf": [S.Spread("modest", (2, 0, 0, 32, 0, 32), 1.0)],
    }
    assert S.prior(usage, mon("sinistchamasterpiece"), dex) == [bulky]
    assert S.prior(usage, mon("basculegionf"), dex)[0].nature == "modest"
    (d,) = S.prior({}, mon("sinistchamasterpiece"), dex)
    assert d.sps == (32, 0, 0, 32, 0, 2)


def test_a_hit_moves_belief_to_the_spread_it_fits():
    bulky, frail = (
        S.Spread("bold", (32, 0, 32, 0, 2, 0), 0.5),
        S.Spread("timid", (0, 0, 0, 32, 2, 32), 0.5),
    )
    # likelihoods: the observed hit fits only the bulky spread
    b = S.Belief([bulky, frail])
    b.update([1.0, 0.0])
    assert b.best() == bulky and b.weights == pytest.approx([1.0, 0.0])
    # an impossible hit under every candidate leaves the belief as it was
    b2 = S.Belief([bulky, frail])
    b2.update([0.0, 0.0])
    assert b2.weights == pytest.approx([0.5, 0.5])


def test_the_chance_of_what_the_log_shows_for_each_roll():
    # max 150 hit points, seen at 100% then 50%: 74 or 75 damage fits
    rolls = [70, 72, 74, 75] + [76] * 12
    assert S.observed_chance(rolls, 150, 100, 50, fainted=False) == pytest.approx(
        2 / 16
    )
    # knocked out from 20%: any roll of at least the hit points left fits
    assert S.observed_chance(
        [10] * 8 + [40] * 8, 150, 20, 0, fainted=True
    ) == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Hits read from the log
# --------------------------------------------------------------------------

from tests.test_decisions import HEAD, LEADS  # noqa: E402


def hits(*blocks):
    return S.hits_from_log("\n|\n".join([HEAD, LEADS, *blocks, "|win|A"]))


TURN = (
    "|t:|1\n|-weather|RainDance|[from] ability: Drizzle|[of] p2b: Fini\n"
    "|-sidestart|p2: B|Reflect\n"
    "|-singleturn|p1b: Rock|move: Helping Hand|[of] p1a: Whim\n"
    "|move|p1b: Rock|Rock Slide|p2a: Inci|[spread] p2a,p2b\n"
    "|-crit|p2b: Fini\n|-damage|p2a: Inci|60/100\n|-damage|p2b: Fini|40/100\n"
    "|move|p2b: Fini|Moonblast|p1b: Rock\n|-damage|p1b: Rock|30/100\n"
    "|-damage|p1b: Rock|25/100|[from] item: Rocky Helmet\n"
    "|move|p2a: Inci|Fake Out|p1a: Whim\n|-enditem|p1a: Whim|Focus Sash\n|-damage|p1a: Whim|1/100"
)


def test_hits_are_read_with_what_was_on_the_field():
    h = hits(TURN, "|upkeep", "|t:|2\n|turn|2")
    assert [(x.attacker, x.defender, x.move, x.before, x.after) for x in h] == [
        (("p1", 1), ("p2", 0), "rockslide", 100, 60),
        (("p1", 1), ("p2", 1), "rockslide", 100, 40),
        (("p2", 1), ("p1", 1), "moonblast", 100, 30),
    ]
    a, b, c = h
    assert a.spread and b.spread and not c.spread
    assert b.crit and not a.crit
    assert (
        a.field["weather"] == "raindance"
        and a.field["reflect"]
        and a.field["helpinghand"]
    )
    assert not c.field.get("reflect") and not c.field.get("helpinghand")
    assert all(x.block == 2 for x in h)  # the turn-1 block, after its decision


def test_hits_that_hide_the_damage_are_left_out():
    multi = "|t:|1\n|move|p1b: Rock|Rock Blast|p2a: Inci\n|-damage|p2a: Inci|80/100\n|-damage|p2a: Inci|60/100\n|-hitcount|p2a: Inci|2"
    sub = "|t:|1\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-activate|p2a: Inci|move: Substitute|[damage]"
    assert hits(multi, "|upkeep", "|t:|2\n|turn|2") == []
    assert hits(sub, "|upkeep", "|t:|2\n|turn|2") == []


def test_a_knock_out_is_kept_as_a_hit_that_took_everything():
    ko = "|t:|1\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|0 fnt\n|faint|p2a: Inci"
    (h,) = hits(ko, "|upkeep", "|t:|2\n|turn|2")
    assert h.fainted and h.after == 0 and h.before == 100
    assert h.att_state["boosts"] == {}


# --------------------------------------------------------------------------
# Refining from hits
# --------------------------------------------------------------------------

from wpa.team_sheets import Dex  # noqa: E402

DEX = Dex(
    species={
        "rock": {"name": "Rock", "baseStats": {"atk": 100, "spa": 50}},
        "inci": {"name": "Inci", "baseStats": {"atk": 100, "spa": 50}},
    },
    moves={"rockslide": {"category": "Physical"}, "moonblast": {"category": "Special"}},
    items={},
)
SHEETS = {
    "p1": [
        SheetMon(1, "whim", "", "prankster", (), ""),
        SheetMon(2, "rock", "leftovers", "sturdy", ("rockslide",), ""),
    ],
    "p2": [
        SheetMon(1, "inci", "sitrus", "intimidate", ("fakeout",), ""),
        SheetMon(2, "fini", "sitrus", "mistysurge", (), ""),
    ],
}


def test_requests_ignore_what_does_not_change_the_damage():
    h = hits(
        "|t:|1\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|60/100",
        "|upkeep",
        "|t:|2\n|turn|2",
    )[0]
    fast = S.Spread("jolly", (0, 32, 2, 0, 0, 32), 1.0)
    slow = S.Spread("adamant", (0, 32, 0, 0, 2, 0), 1.0)
    bulky = S.Spread("impish", (32, 0, 32, 0, 2, 0), 1.0)
    r1 = S.request_for(h, SHEETS, DEX, fast, bulky)
    r2 = S.request_for(
        h, SHEETS, DEX, S.Spread("adamant", (0, 32, 0, 0, 0, 34), 1.0), bulky
    )
    assert (
        r1["attacker"]["sps"] == {"atk": 32} and r1["attacker"]["nature"] == "serious"
    )
    assert r2["attacker"]["nature"] == "adamant"
    assert (
        r1["defender"]["sps"] == {"hp": 32, "def": 32}
        and r1["defender"]["nature"] == "bold"
    )
    assert S.request_for(h, SHEETS, DEX, slow, bulky)["attacker"] == r2["attacker"]


class StubCalc:
    """150 max hit points with full HP investment, 110 without; 50 damage."""

    def __init__(self):
        self.calls = 0

    def run(self, requests):
        self.calls += len(requests)
        return [
            {
                "rolls": [50] * 16,
                "max_hp": 150 if r["defender"]["sps"].get("hp") else 110,
            }
            for r in requests
        ]


def test_a_hit_refines_the_defender_for_later_decisions_only():
    h = hits(
        "|t:|1\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|66/100",
        "|upkeep",
        "|t:|2\n|turn|2",
    )
    bulky = S.Spread("serious", (32, 0, 0, 0, 0, 2), 0.3)
    frail = S.Spread("serious", (0, 32, 0, 0, 0, 32), 0.7)
    priors = {
        ("p1", 1): [S.Spread("adamant", (0, 32, 0, 0, 2, 32), 1.0)],
        ("p2", 0): [bulky, frail],
    }
    g, records = S.refine(h, SHEETS, DEX, priors, StubCalc(), measure=True)
    assert g.at(2)[("p2", 0)] == frail  # the decision before the hit: the prior
    assert g.at(3)[("p2", 0)] == bulky  # after it
    (rec,) = records
    assert (
        rec["prior_fits"] is False and rec["refined_fits"] is False
    )  # the first hit: same belief
    assert rec["logp_prior"] == pytest.approx(rec["logp_refined"])


def test_the_defender_is_read_as_it_was_when_the_move_started():
    # a resist berry is eaten before the damage line; Stance Change shows the form
    berry = (
        "|t:|1\n|-formechange|p2a: Inci|Inci-Blade|[from] ability: Stance Change\n"
        "|-ability|p2b: Fini|Fairy Aura\n"
        "|move|p1b: Rock|Rock Slide|p2a: Inci\n|-enditem|p2a: Inci|Sitrus Berry|[eat]\n"
        "|-damage|p2a: Inci|70/100"
    )
    (h,) = hits(berry, "|upkeep", "|t:|2\n|turn|2")
    assert h.def_state["item"] == "sitrus"
    assert h.def_state["form"] == "inciblade"
    assert h.field["fairyaura"]


def test_with_an_allowance_one_odd_hit_does_not_rule_a_spread_out():
    h = hits(
        "|t:|1\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|66/100",
        "|upkeep",
        "|t:|2\n|turn|2",
    )
    bulky = S.Spread("serious", (32, 0, 0, 0, 0, 2), 0.3)
    frail = S.Spread("serious", (0, 32, 0, 0, 0, 32), 0.7)
    priors = {
        ("p1", 1): [S.Spread("adamant", (0, 32, 0, 0, 2, 32), 1.0)],
        ("p2", 0): [bulky, frail],
    }
    beliefs = {}
    S.refine(h, SHEETS, DEX, priors, StubCalc(), epsilon=0.02, beliefs_out=beliefs)
    w = beliefs[("p2", 0)].weights
    assert w[0] > 0.9 and w[1] > 0  # frail is unlikely now, not impossible
    assert S.EPSILON == 0.02


# --------------------------------------------------------------------------
# Who moved first
# --------------------------------------------------------------------------

DEX2 = Dex(
    species=DEX.species,
    moves={
        "fakeout": {
            "category": "Physical",
            "priority": 3,
            "type": "Normal",
            "flags": [],
        },
        "tailwind": {
            "category": "Status",
            "priority": 0,
            "type": "Flying",
            "flags": [],
        },
        "moonblast": {
            "category": "Special",
            "priority": 0,
            "type": "Fairy",
            "flags": [],
        },
        "rockslide": {
            "category": "Physical",
            "priority": 0,
            "type": "Rock",
            "flags": [],
        },
    },
    items={},
)
ORDER_TURN = (
    "|t:|1\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-damage|p1a: Whim|90/100\n"
    "|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind\n"
    "|move|p2b: Fini|Moonblast|p1b: Rock\n|-damage|p1b: Rock|60/100\n"
    "|move|p1b: Rock|Rock Slide|p2a: Inci|[spread] p2a,p2b\n|-damage|p2a: Inci|80/100\n|-damage|p2b: Fini|80/100"
)


def orders(*blocks):
    log = "\n|\n".join([HEAD, LEADS, *blocks, "|win|A"])
    return S.events_from_log(log, DEX2)[1]


def test_only_moves_in_the_same_priority_bracket_give_an_order():
    (o,) = orders(ORDER_TURN, "|upkeep\n|turn|2")
    # Fake Out (+3) and Prankster Tailwind (+1) are in brackets of their own
    assert (o.first, o.second) == (("p2", 1), ("p1", 1))
    assert o.tailwind == {"p1": True, "p2": False} and not o.trickroom


def test_a_turn_with_quick_claw_gives_no_order():
    claw = ORDER_TURN.replace(
        "|move|p2b: Fini", "|-activate|p2b: Fini|item: Quick Claw\n|move|p2b: Fini"
    )
    assert orders(claw, "|upkeep\n|turn|2") == []


class SpeedCalc(StubCalc):
    """Speed 150 with Speed points, 100 without; Rock is always 120."""

    def run(self, requests):
        out = []
        for r in requests:
            if r.get("op") == "speed":
                m = r["mon"]
                out.append(
                    {
                        "speed": 120
                        if m["species"] == "rock"
                        else (150 if m["sps"].get("spe") else 100)
                    }
                )
            else:
                out.append({"rolls": [50] * 16, "max_hp": 150})
        return out


def test_moving_first_shows_speed():
    log = "\n|\n".join([HEAD, LEADS, ORDER_TURN, "|upkeep\n|turn|2", "|win|A"])
    hits_, orders_ = S.events_from_log(log, DEX2)
    fast = S.Spread("timid", (0, 0, 0, 32, 2, 32), 0.4)
    slow = S.Spread("modest", (32, 0, 2, 32, 0, 0), 0.6)
    priors = {
        pos: [S.Spread("serious", (32, 32, 0, 0, 0, 2), 1.0)]
        for pos in [("p1", 0), ("p1", 1), ("p2", 0)]
    }
    priors[("p2", 1)] = [fast, slow]
    beliefs = {}
    S.refine([*hits_, *orders_], SHEETS, DEX2, priors, SpeedCalc(), beliefs_out=beliefs)
    assert beliefs[("p2", 1)].best() == fast
