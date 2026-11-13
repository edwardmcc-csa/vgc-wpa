"""Week 12 Task 5: the analysis with the opponent's sheet hidden. Each player's
turn is valued from what that player knew: their own sheet whole, the
opponent's believed (`wpa.hidden`), and the win probability from the model
trained that way (one-sided, the opponent's sheet blanked: Week 8, with team
preview's species: Week 9). The two players know different things, so each is
analysed apart, with their own win probabilities."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from tests.test_hidden import DEX, SETS
from wpa import attribution as A
from wpa import features as F
from wpa import resolver as R
from wpa.choices import Action
from wpa.team_sheets import Dex, SheetMon


def _mon(species, item="", rev_item="", active=True, hp=1.0):
    return {
        "species": species,
        "hp_fraction": hp,
        "fainted": False,
        "active": active,
        "item": item,
        "rev_item": rev_item,
        "rev_moves": [],
        "rev_ability": "",
    }


def test_a_board_is_valued_from_the_players_own_side_with_what_they_knew(monkeypatch):
    seen = []

    def features(rows, i, role, j, sheets, dex, table, groups, ctx):
        seen.append((rows[i], role, j, sheets, ctx))
        return {"x": 1.0}

    monkeypatch.setattr(F, "state_features", features)
    monkeypatch.setattr(F, "columns", lambda groups: ["x"])
    p1 = [_mon("incineroar", "sitrusberry"), _mon("rillaboom", "assaultvest")]
    p2 = [_mon("garchomp", "lifeorb"), _mon("floetteeternal", "floettite")]
    s0 = {
        "turn": 3,
        "moment": "turn_start",
        "decision_index": 0,
        "our_pokemon": p2,
        "opp_pokemon": p1,
        "observations": [],
    }
    public = {"p1": ("public p1",), "p2": ("whole p2",)}
    bw = A.BoardWP(
        lambda X: np.full(len(X), 0.8),  # p2's own chance, from its own row
        [s0],
        0,
        None,
        public,
        None,
        None,
        "x",
        "ctx",
        role="p2",
        public=True,
    )
    after = {
        "p1": [_mon("incineroar", "sitrusberry"), _mon("rillaboom", "", "assaultvest")],
        "p2": [_mon("garchomp", "lifeorb"), _mon("floetteeternal", "floettite")],
    }
    out = NS(sides=after, field=R.Field())
    assert bw([out])[0] == pytest.approx(0.2)  # as p1's: 1 - p2's own
    row, role, j, sheets, ctx = seen[0]
    assert role == "p2"
    assert [m["species"] for m in row["our_pokemon"]] == ["garchomp", "floetteeternal"]
    assert [m["item"] for m in row["our_pokemon"]] == ["lifeorb", "floettite"]
    # p1's items as p2 knew them: one shown (and gone), one not
    assert [m["item"] for m in row["opp_pokemon"]] == ["", ""]
    assert row["turn"] == 4  # nothing fell: the next turn's start
    assert (sheets, ctx) == (public, "ctx")


def test_a_player_knows_their_sheet_and_believes_the_others():
    true = {
        "p1": (
            SheetMon(1, "rillaboom", "assaultvest", "grassysurge", ("fakeout",), ""),
        ),
        "p2": (
            SheetMon(
                1,
                "incineroar",
                "safetygoggles",
                "intimidate",
                ("fakeout", "partingshot", "knockoff", "taunt"),
                "",
            ),
            SheetMon(
                2,
                "floetteeternal",
                "floettite",
                "flowerveil",
                ("lightofruin", "moonblast", "protect", "calmmind"),
                "",
            ),
        ),
    }
    theirs = [
        dict(_mon("incineroar", "safetygoggles"), rev_moves=["knockoff"]),
        _mon("floetteeternal", "floettite"),
    ]
    # Incineroar uses Taunt this turn; Floette Mega Evolves
    taken = {
        0: Action(0, "move", "taunt", ("foe", 0)),
        1: Action(1, "move", "moonblast", ("foe", 0), mega=True),
    }
    view, board = A.player_view(true, "p1", theirs, SETS, DEX, taken)
    assert view["p1"] == true["p1"]
    inc, flo = view["p2"]
    # what p1 could expect before the turn: Knock Off shown, the rest believed
    assert inc.moves == ("knockoff", "fakeout", "partingshot", "flareblitz")
    assert inc.item == "sitrusberry"
    assert flo.item == "floettite"  # a Mega Evolution shows the stone first
    assert [m["item"] for m in board] == ["sitrusberry", "floettite"]
    assert theirs[0]["item"] == "safetygoggles"  # the board itself is left alone


class _Values:
    """`TurnValues` as `_analyse_turn` uses it, with the pairs it was asked."""

    def __init__(self):
        self.asked = []
        self.outcomes = {}

    def prepare(self, pairs):
        self.asked += pairs

    def __call__(self, p1, p2):
        return 0.5 + 0.1 * (p1[0].move == "a") - 0.1 * (p2[0].move == "y")

    def for_role(self, role):
        if role == "p1":
            return self
        return lambda ours, theirs: 1.0 - self(theirs, ours)


A_, B_ = (Action(0, "move", m, ("foe", 0)) for m in ("a", "b"))
X_, Y_ = (Action(0, "move", m, ("foe", 0)) for m in ("x", "y"))


def _turn(only):
    tv = _Values()
    ts = A.TurnSetup(
        {"tag": "gen9championsvgc2026regma-1", "format": "regma", "turn": 2},
        2,
        tv,  # type: ignore[arg-type]
        NS(_cache={}, grid=0.0),  # type: ignore[arg-type]
        0.6,
        0.7,
        {},
        {"p1": NS(taken={0: B_}, hidden=set()), "p2": NS(taken={0: Y_}, hidden=set())},
        {"p1": {0: [A_, B_]}, "p2": {0: [X_, Y_]}},
        {"p1": {0: [0.9, 0.1]}, "p2": {0: [0.6, 0.4]}},
        0.0,
        only=only,
    )
    tools = NS(
        dexes={"regma": Dex({}, {}, {})},
        top=1,
        draws=0,
        alternatives=0,
        typical=True,
        strength=0.0,
        measure_strengths=(),
        resolution=0.05,
    )
    return tv, A._analyse_turn(ts, tools, False)  # type: ignore[arg-type]


def test_one_players_turn_is_analysed_alone_from_their_own_side():
    tv, recs = _turn("p2")
    assert [r["role"] for r in recs] == ["p2"]
    assert recs[0]["before"] == pytest.approx(0.4)  # p2's own
    assert recs[0]["after"] == pytest.approx(0.3)
    # p2's split needs p1's likely and taken choices against p2's choice ...
    assert ((A_,), (Y_,)) in tv.asked and ((B_,), (Y_,)) in tv.asked
    # ... and not p1's taken choice against p2's likely reply, which p1's needs
    assert ((B_,), (X_,)) not in tv.asked
    tv, recs = _turn("p1")
    assert [r["role"] for r in recs] == ["p1"]
    assert ((B_,), (X_,)) in tv.asked
    tv, recs = _turn(None)  # as before: both, from one set of values
    assert [r["role"] for r in recs] == ["p1", "p2"]


def test_each_player_moves_on_to_their_own_next_decision_point():
    states = [
        {"moment": m}
        for m in ("preview", "turn_start", "mid_turn", "after_turn", "turn_start")
    ] + [{"moment": "terminal"}]
    assert A.next_own(states, 0) == 1
    assert A.next_own(states, 1) == 3  # past a switch-in mid-turn
    assert A.next_own(states, 3) == 4
    assert A.next_own(states, 4) == 5
    assert A.next_own(states, 5) == 5


ROOT = Path(__file__).resolve().parent.parent
NEEDS = [
    ROOT / "pokemon-showdown" / "dist",
    ROOT / "calc" / "node_modules",
    ROOT / "usage_stats",
    ROOT / "models_v4" / "policy.json",
]


@pytest.mark.skipif(
    not all(p.exists() for p in NEEDS) or not os.environ.get("WPA_SLOW"),
    reason="about a minute; needs the pinned Showdown build, the calculator, the "
    "usage statistics and the opponent model (set WPA_SLOW=1)",
)
def test_a_whole_game_with_the_sheet_hidden_chains_for_each_player(monkeypatch):
    """A Reg M-B game (natures on the sheet, hidden too), with a stand-in for
    the model that depends on the row: each player's points chain from team
    preview to the result, from their own side."""
    import argparse
    import json

    def model(models, fmt, groups):
        return lambda X: 1 / (1 + np.exp(-np.asarray(X, float).mean(axis=1) / 50))

    monkeypatch.setattr(A, "wp_model", model)
    moves = ROOT / "build"
    a = argparse.Namespace(
        dex_tables=None,
        showdown=ROOT / "pokemon-showdown",
        moves_dir=moves if (moves / "moves_regmb.json").exists() else None,
        usage=ROOT / "usage_stats",
        bring=ROOT / "models_v4" / "bring.json",
        policy=ROOT / "models_v4" / "policy.json",
        models=None,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        hidden_sets=True,
        public_models=None,
    )
    tools = A._tools(a)
    tag = "gen9championsvgc2026regmb-2634495132"
    path = ROOT / "tests" / "fixtures" / "replays" / f"{tag}.json"
    log = json.loads(path.read_text(encoding="utf-8"))["log"]
    recs = A.analyse_game(tag, log, "regmb", tools, with_alternatives=False)
    assert recs and all(r["sheets"] == "hidden" for r in recs)
    assert not [r for r in recs if str(r.get("skipped", "")).startswith("error")]
    for role in ("p1", "p2"):
        mine = sorted((r for r in recs if r["role"] == role), key=lambda r: r["point"])
        assert mine[0]["kind"] == "preview"
        for x, y in zip(mine, mine[1:]):
            assert x["after"] == pytest.approx(y["before"], abs=1e-9)
        result = mine[0]["result"] if role == "p1" else 1 - mine[0]["result"]
        assert mine[-1]["after"] == result
        turns = [r for r in mine if r["kind"] == "turn" and "skipped" not in r]
        assert len(turns) >= 5
        for r in turns:
            assert r["choice"] + r["position"] + r["theirs"] + r["dice"] == (
                pytest.approx(r["after"] - r["before"], abs=1e-9)
            )
    # the two players knew different things: their chances are not one minus
    # the other's
    by = {(r["turn"], r["role"]): r for r in recs if r["kind"] == "turn"}
    assert any(
        abs(by[(t, "p1")]["before"] + by[(t, "p2")]["before"] - 1) > 1e-6
        for t, role in by
        if role == "p1" and (t, "p2") in by
    )
