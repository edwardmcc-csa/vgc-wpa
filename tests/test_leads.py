"""Tests for team preview's leads (Week 11 Task 1, DEFINITIONS §6).

At team preview each player picks four and the two that lead, without seeing the
other's choice. The win probability model cannot see a player's back two (both
sides' backs are chances from the bring model), so the choice scored is the
leads: one of the 15 pairs of the six on the sheet.

- the resolver puts both sides' leads in, then their entry effects in Speed order;
- a model of which two lead, learned from the training split, using the leads of
  the set's previous game;
- the split as in §3, valued at turn 1's start; a game then adds up from team
  preview to its result.
"""

from __future__ import annotations

import json
import math
import random

import numpy as np
import pytest

from tests.test_forced import _mon, _switch_in_resolver, needs_showdown
from wpa import attribution as A
from wpa import lead_model as L
from wpa.choices import Action
from wpa.team_sheets import SheetMon


def _preview():
    return {
        "p1": [
            _mon(s, hp=0.0, active=False) for s in ("kingambit", "sneasler", "garchomp")
        ],
        "p2": [
            _mon(s, hp=0.0, active=False)
            for s in ("whimsicott", "rotom", "incineroar", "arcanine")
        ],
    }


def _pair(i, j):
    return (Action(0, "switch", switch_to=i), Action(1, "switch", switch_to=j))


@needs_showdown
def test_the_leads_come_in_and_their_entry_effects_follow_in_speed_order():
    from wpa import resolver as R

    rv, calc = _switch_in_resolver()
    try:
        (o,) = rv.lead(_preview(), R.Field(), {"p1": _pair(0, 2), "p2": _pair(2, 3)})
        assert o.prob == 1.0
        assert [m["active"] for m in o.sides["p1"]] == [True, False, True]
        assert o.sides["p1"][0]["hp_fraction"] == 1.0
        assert not o.sides["p2"][0]["active"] and o.sides["p2"][3]["active"]
        # Garchomp (faster) sets rain, Incineroar (slower) sun: sun stays
        assert o.field.weather == "sunnyday"
        # Arcanine's Intimidate: Kingambit's Defiant answers it (-1, +2)
        assert o.sides["p1"][0]["boosts"] == {"atk": 1}
        assert _preview()["p1"][0]["active"] is False  # the board given is unchanged
    finally:
        calc.close()


def _sheet(*specs):
    return tuple(
        SheetMon(i + 1, sp, "", ab, mv, "") for i, (sp, ab, mv) in enumerate(specs)
    )


SHEET = _sheet(
    ("incineroar", "intimidate", ("fakeout", "flareblitz")),
    ("whimsicott", "prankster", ("tailwind", "moonblast")),
    ("amoonguss", "regenerator", ("ragepowder", "spore")),
    ("garchomp", "roughskin", ("earthquake",)),
    ("kingambit", "defiant", ("suckerpunch",)),
    ("sneasler", "unburden", ("closecombat",)),
)


def test_each_lead_pair_has_the_facts_the_model_uses():
    rates = {"incineroar": 0.8, "whimsicott": 0.6}
    pairs = L.pairs(6)
    assert len(pairs) == 15 and pairs[0] == (0, 1)
    f = dict(zip(L.FEATURES, L.pair_features(SHEET, (0, 1), rates, None)))
    assert f["lead_rate"] == pytest.approx(math.log(0.8 / 0.2) + math.log(0.6 / 0.4))
    assert f["fakeout"] == 1.0 and f["intimidate"] == 1.0
    assert f["speed_control"] == 1.0 and f["redirect"] == 0.0
    assert f["first_two"] == 1.0 and f["has_prev"] == 0.0 and f["led_before"] == 0.0
    # the set's previous game: Incineroar and Amoonguss led
    f = dict(
        zip(
            L.FEATURES,
            L.pair_features(SHEET, (0, 2), rates, {"incineroar", "amoonguss"}),
        )
    )
    assert f["has_prev"] == 1.0 and f["led_before"] == 2.0 and f["redirect"] == 1.0
    assert f["first_two"] == 0.0


def test_the_chances_over_the_15_pairs_add_up_to_one_and_follow_the_weights():
    w = [0.0] * len(L.FEATURES)
    w[L.FEATURES.index("led_before")] = 3.0
    model = L.LeadModel(w, {})
    p = model.chances(SHEET, "regma", {"incineroar", "amoonguss"})
    assert len(p) == 15 and sum(p) == pytest.approx(1.0)
    assert L.pairs(6)[int(np.argmax(p))] == (0, 2)


def test_fitting_finds_a_preference_and_beats_a_uniform_guess():
    rng = random.Random(4)
    k = len(L.FEATURES)
    i = L.FEATURES.index("first_two")
    groups = []
    for _ in range(300):
        X = np.zeros((15, k))
        X[0, i] = 1.0
        z = 2.5 * X[:, i]
        p = np.exp(z) / np.exp(z).sum()
        groups.append((X, int(rng.choices(range(15), weights=p)[0])))
    model = L.fit(groups, {})
    assert model.weights[i] > 1.5
    ll, un = L.score(model, groups)
    assert ll > un and un == pytest.approx(math.log(1 / 15))


def test_the_examples_carry_the_previous_games_leads_in_a_set():
    from tests.test_decisions import HEAD, LEADS

    def game(n):
        return "\n|\n".join(
            [
                HEAD,
                f"|uhtml|bestof|<h2><strong>Game {n}</strong> of "
                '<a href="/game-bestof3-gen9championsvgc2026regmabo3-1">'
                "a best-of-3</a></h2>",
                LEADS,
                "|turn|1",
                "|win|A",
            ]
        )

    logs = [
        ("gen9championsvgc2026regmabo3-11", game(1)),
        ("gen9championsvgc2026regmabo3-12", game(2)),
    ]
    ex = L.examples_from_logs(logs, {t: "train" for t, _ in logs})["train"]
    first = [e for e in ex if e.tag.endswith("11")]
    second = [e for e in ex if e.tag.endswith("12")]
    assert first and second
    assert all(e.prev is None for e in first)
    assert all(e.prev == e.leads_species for e in second)  # the same two led again
    for e in ex:
        assert L.pairs(6)[e.chosen] == tuple(sorted(e.leads))


def test_team_preview_is_a_decision_point_and_the_game_adds_up_from_it():
    from tests.test_board_effects import LEADS
    from tests.test_decisions import EMPTY
    from tests.test_forced import END2, KO, QUIET, REPLACE, UPKEEP, game
    from wpa import decisions as D

    g = D.build_game(game(KO, UPKEEP, REPLACE, QUIET, END2), EMPTY)
    k0 = [k for k, s in enumerate(g.states["p1"]) if s["moment"] == "preview"][0]
    role, i = A.next_point(g, k0)
    assert role == "p1" and g.states["p1"][i]["moment"] == "turn_start"
    assert g.states["p1"][i]["turn"] == 1
    recs = []
    for kind, turn, pt, b, a in (
        ("preview", 0, 1, 0.5, 0.55),
        ("turn", 1, 2, 0.55, 1.0),
    ):
        recs.append(
            {
                "tag": "g",
                "kind": kind,
                "turn": turn,
                "point": pt,
                "role": "p1",
                "before": b,
                "after": a,
            }
        )
    (c,) = A.chains(recs, results={"g": 1.0})
    assert c["chained"] and c["adds_up"]
    assert LEADS  # the fixture's leads exist


@needs_showdown
def test_the_leads_are_split_like_a_turn():
    from wpa import resolver as R

    rv, calc = _switch_in_resolver()
    try:

        def stand_in(outs):
            # p1 likes having Garchomp out, and sun
            return [
                0.5
                + 0.2 * o.sides["p1"][2]["active"]
                + 0.1 * (o.field.weather == "sunnyday")
                for o in outs
            ]

        tv = A.TurnValues(A.Leads(rv), _preview(), R.Field(), stand_in)
        mine = [(_pair(0, 1), 0.5), (_pair(0, 2), 0.3), (_pair(1, 2), 0.2)]
        theirs = [(_pair(0, 1), 0.7), (_pair(2, 3), 0.3)]
        tv.prepare([(x, y) for x, _ in mine for y, _ in theirs])
        s = A.decompose(
            tv.for_role("p1"),
            0.5,
            0.75,
            [(_pair(0, 2), 1.0)],
            [(_pair(2, 3), 1.0)],
            theirs,
            [[(x, 1.0)] for x, _ in mine],
            typical=mine,
        )
        assert s.conserved() and s.choice > 0  # leading Garchomp beats the typical pair
        assert s.vs_best == pytest.approx(0.0)
    finally:
        calc.close()


def test_the_summary_reports_team_preview(tmp_path):
    from tests.test_attribution import _rec

    recs = []
    for role, sign in (("p1", 1), ("p2", -1)):
        r = _rec("g1", 0, role, 0.5, 0.5 + sign * 0.1, alt=True)
        r.update(
            kind="preview",
            point=1,
            result=1.0,
            after_board=r["after"],
            choice=sign * 0.05,
            position=sign * 0.0,
            choices=15,
        )
        recs.append(r)
        t = _rec("g1", 1, role, 0.5 + sign * 0.1, 0.5 + sign * 0.5, alt=True)
        t.update(
            kind="turn",
            point=2,
            result=1.0,
            after_board=t["after"],
            choice=0.0,
            position=t["yours"],
        )
        recs.append(t)
    path = tmp_path / "a.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    text = A.report(path)
    assert "team preview (the leads): 1 games, 2 decisions" in text
    assert "the 10 biggest team-preview choices" in text
    assert "games whose decision points chain: 1 of 1" in text
