"""Tests for wpa/attribution.py (Week 9 Tasks 4 and 5, the plan's M5 part 1):
each turn's swing split three ways (DEFINITIONS rev 8, §3), with cost against
the best and the average choice beside it (§4).

The plan's M5 tests: the parts add up to the whole swing at every decision point
(within 0.001); a turn where only a critical hit differs gives the difference to
the dice, none to the decisions; an obviously losing switch costs a lot against
the best choice. The last two use the real resolver with a simple stand-in for
the win-probability model, so they check the split, not the model.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from wpa import attribution as A
from wpa.choices import Action

ROOT = Path(__file__).resolve().parent.parent

SD = Action(0, "move", move="swordsdance")
PR = Action(1, "move", move="protect")


def _rand_mix(rng, n):
    acts = [Action(0, "move", move=f"m{i}") for i in range(n)]
    w = [rng.random() for _ in acts]
    s = sum(w)
    return [((a,), x / s) for a, x in zip(acts, w)]


# ---------------------------------------------------------------- the split


def test_the_parts_add_up_to_the_swing_every_time():
    rng = random.Random(7)
    for _ in range(300):
        table: dict = {}

        def value(ours, theirs):
            return table.setdefault((ours, theirs), rng.random())

        ours, theirs, likely = (_rand_mix(rng, rng.randint(1, 4)) for _ in range(3))
        alts = [[(j, 1.0)] for j, _ in _rand_mix(rng, 5)]
        before, after = rng.random(), rng.random()
        s = A.decompose(value, before, after, ours, theirs, likely, alts)
        assert abs(s.yours + s.theirs + s.dice - (after - before)) < 1e-9
        assert s.conserved()
        assert s.vs_best is not None and s.vs_best <= 1e-12
        assert s.vs_average is not None


def test_each_part_is_what_definitions_section_3_says():
    a, b, x, y = (Action(0, "move", move=m) for m in "abxy")
    v = {(a, x): 0.6, (a, y): 0.2, (b, x): 0.9, (b, y): 0.5}

    def value(ours, theirs):
        return v[(ours[0], theirs[0])]

    ours = [((a,), 1.0)]
    likely = [((x,), 0.75), ((y,), 0.25)]
    s = A.decompose(value, 0.5, 0.0, ours, [((y,), 1.0)], likely, [[((b,), 1.0)], ours])
    e_yours = 0.75 * 0.6 + 0.25 * 0.2  # 0.5
    assert s.yours == pytest.approx(e_yours - 0.5)
    assert s.theirs == pytest.approx(0.2 - e_yours)  # they read us well: negative
    assert s.dice == pytest.approx(0.0 - 0.2)
    e_b = 0.75 * 0.9 + 0.25 * 0.5  # 0.8
    assert s.vs_best == pytest.approx(e_yours - e_b)
    assert s.vs_average == pytest.approx(e_yours - (e_b + e_yours) / 2)


def test_their_decision_is_zero_when_they_play_their_likely_replies():
    rng = random.Random(3)
    table: dict = {}

    def value(ours, theirs):
        return table.setdefault((ours, theirs), rng.random())

    likely = _rand_mix(rng, 3)
    s = A.decompose(value, 0.4, 0.7, _rand_mix(rng, 2), likely, likely)
    assert s.theirs == pytest.approx(0.0, abs=1e-12)
    assert s.vs_best is None and s.vs_average is None


# ------------------------------------------------------- choices and chances


def test_joint_choices_multiply_and_drop_pairs_the_game_forbids():
    to2 = (Action(0, "switch", switch_to=2), 0.5)
    to2b = (Action(1, "switch", switch_to=2), 0.5)
    mix = A.mixture({0: [to2, (SD, 0.5)], 1: [to2b, (PR, 0.5)]})
    assert len(mix) == 3  # both switching to the same Pokemon is not allowed
    assert sum(p for _, p in mix) == pytest.approx(1.0)
    assert all(p == pytest.approx(1 / 3) for _, p in mix)
    assert A.mixture({}) == [((), 1.0)]


def test_trim_keeps_the_likeliest_replies_and_says_how_much():
    mix = [
        ((SD,), 0.5),
        ((PR,), 0.3),
        ((Action(0, "move", move="x"),), 0.15),
        ((Action(0, "move", move="y"),), 0.05),
    ]
    kept, share = A.trim(mix, keep=0.9)
    assert [j for j, _ in kept] == [(SD,), (PR,), (Action(0, "move", move="x"),)]
    assert share == pytest.approx(0.95)
    assert sum(p for _, p in kept) == pytest.approx(1.0)
    kept, share = A.trim(mix, keep=0.99, most=2)
    assert len(kept) == 2 and share == pytest.approx(0.8)


def test_likely_replies_keep_the_top_exactly_and_draw_the_rest():
    rng = random.Random(11)
    full = _rand_mix(rng, 30)
    mix, exact = A.likely(full, top=5, draws=8, seed="g1 turn 3 p2")
    head = sorted(full, key=lambda x: -x[1])[:5]
    assert exact == pytest.approx(sum(p for _, p in head))
    assert mix[:5] == head  # the likeliest, with their own chances
    assert len(mix) == 13
    assert sum(p for _, p in mix) == pytest.approx(1.0)  # nothing is dropped
    assert mix == A.likely(full, top=5, draws=8, seed="g1 turn 3 p2")[0]  # repeatable
    # with no draws it is the top, scaled back to 1, like trim
    assert A.likely(full, top=5, draws=0, seed="x") == A.trim(full, 1.0, 5)
    # the draws make an estimate of the whole average with no lean
    vals = {j: rng.random() for j, _ in full}
    truth = sum(p * vals[j] for j, p in full)
    est = [
        sum(p * vals[j] for j, p in A.likely(full, 5, 8, seed=str(s))[0])
        for s in range(2000)
    ]
    assert sum(est) / len(est) == pytest.approx(truth, abs=0.005)


def test_a_choice_the_log_does_not_show_is_averaged_with_the_model():
    opts = {0: [SD, Action(0, "move", move="x")], 1: [PR, Action(1, "move", move="y")]}
    chances = {0: [0.25, 0.75], 1: [0.4, 0.6]}
    taken = {0: SD, 1: "cant"}
    mix = A.taken_mixture(taken, set(), opts, chances)
    assert {j: p for j, p in mix} == pytest.approx(
        {(SD, PR): 0.4, (SD, opts[1][1]): 0.6}
    )
    # a move whose target is hidden: its own move, any target
    hid = {
        0: [
            Action(0, "move", move="x", target=("foe", 0)),
            Action(0, "move", move="x", target=("foe", 1)),
            SD,
        ]
    }
    mix = A.taken_mixture({0: hid[0][0]}, {0}, hid, {0: [0.1, 0.3, 0.6]})
    assert {j: p for j, p in mix} == pytest.approx(
        {(hid[0][0],): 0.25, (hid[0][1],): 0.75}
    )


# --------------------------------------------- with the resolver (the plan's M5)

needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa import resolver as R
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


def _setup():
    from wpa.spreads import Spread
    from wpa.team_sheets import SheetMon

    full = Spread("adamant", (32, 32, 0, 0, 0, 2), 1.0)
    bulk = Spread("careful", (32, 0, 32, 0, 0, 2), 1.0)
    sheets = {
        "p1": (
            SheetMon(
                1,
                "garchomp",
                "",
                "roughskin",
                ("stoneedge", "dragonclaw", "protect"),
                "",
            ),
            SheetMon(2, "kingambit", "", "defiant", ("protect", "suckerpunch"), ""),
            SheetMon(3, "sneasler", "", "unburden", ("closecombat", "protect"), ""),
        ),
        "p2": (
            SheetMon(
                1,
                "incineroar",
                "",
                "blaze",
                ("swordsdance", "protect", "flareblitz"),
                "",
            ),
            SheetMon(2, "whimsicott", "", "infiltrator", ("protect", "moonblast"), ""),
        ),
    }
    spreads = {
        ("p1", 0): full,
        ("p1", 1): full,
        ("p1", 2): bulk,
        ("p2", 0): bulk,
        ("p2", 1): bulk,
    }

    def mon(species, hp=1.0, active=True):
        return {
            "species": species,
            "hp_fraction": hp,
            "fainted": False,
            "active": active,
            "mega": False,
            "boosts": {},
            "status": "",
            "item": "",
            "moved": False,
            "last_move": "",
            "protect_streak": 0,
            "rev_moves": [],
            "rev_item": "",
            "rev_ability": "",
        }

    sides = {
        "p1": [mon("garchomp"), mon("kingambit"), mon("sneasler", 0.05, active=False)],
        "p2": [mon("incineroar"), mon("whimsicott")],
    }
    return sheets, spreads, sides


def stand_in(sides) -> float:
    """A stand-in for the model, from p1's side: Pokemon left and hit points."""

    def side(r):
        return sum(0.0 if m["fainted"] else 1.0 + m["hp_fraction"] for m in sides[r])

    return min(1.0, max(0.0, 0.5 + 0.1 * (side("p1") - side("p2"))))


def _values(tools, sides):
    from wpa import resolver as R

    dex, moves, calc = tools
    sheets, spreads, _ = _setup()
    rv = R.Resolver(dex, moves, calc, sheets, spreads)
    tv = A.TurnValues(
        rv, sides, R.Field(), lambda outs: [stand_in(o.sides) for o in outs]
    )
    return rv, tv


@needs_showdown
def test_a_critical_hit_goes_to_the_dice_not_the_decisions(tools):
    from wpa import resolver as R

    _, _, sides = _setup()
    rv, tv = _values(tools, sides)
    edge = (
        Action(0, "move", move="stoneedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    claw = (
        Action(0, "move", move="dragonclaw", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    guard = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
    theirs = (SD, PR)
    outs = rv.resolve(sides, R.Field(), {"p1": edge, "p2": theirs})
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    plain, crit = (
        max(hit, key=lambda o: o.sides["p2"][0]["hp_fraction"]),
        min(hit, key=lambda o: o.sides["p2"][0]["hp_fraction"]),
    )
    value = tv.for_role("p1")
    before = stand_in(sides)
    alts = [[(edge, 1.0)], [(claw, 1.0)], [(guard, 1.0)]]
    one = [(theirs, 1.0)]
    a = A.decompose(value, before, stand_in(plain.sides), [(edge, 1.0)], one, one, alts)
    b = A.decompose(value, before, stand_in(crit.sides), [(edge, 1.0)], one, one, alts)
    assert a.conserved() and b.conserved()
    # the same choices: the decision parts do not change, the dice take it all
    assert (a.yours, a.theirs, a.vs_best, a.vs_average) == (
        b.yours,
        b.theirs,
        b.vs_best,
        b.vs_average,
    )
    assert b.dice - a.dice == pytest.approx(
        stand_in(crit.sides) - stand_in(plain.sides)
    )
    assert b.dice > a.dice
    assert a.vs_best == 0.0  # Stone Edge was the best choice here


@needs_showdown
def test_an_obviously_losing_switch_costs_a_lot(tools):
    _, _, sides = _setup()
    _, tv = _values(tools, sides)
    edge = (
        Action(0, "move", move="stoneedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    out = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    blitz = (Action(0, "move", move="flareblitz", target=("foe", 0)), PR)
    value = tv.for_role("p1")
    one = [(blitz, 1.0)]
    s = A.decompose(
        value,
        stand_in(sides),
        stand_in(sides),
        [(out, 1.0)],
        one,
        one,
        [[(edge, 1.0)], [(out, 1.0)]],
    )
    assert s.conserved()
    assert s.vs_best is not None and s.vs_best < -0.1  # strongly negative
    assert s.yours < -0.1
    # the other player's view of the same turn is its mirror
    them = tv.for_role("p2")
    assert them(blitz, out) == pytest.approx(1 - value(out, blitz))
