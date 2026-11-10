"""Tests for Week 11 Task 3: the causes left among the biggest swings, and the
rules the Champions format changes (checked against `data/mods/champions`).

- Paralysis: a Pokemon cannot move 1 time in 8 (not 1 in 4).
- Sleep: it lasts 1 or 2 of the Pokemon's turns: it wakes on its second try with
  chance 1/3, on its third for sure.
- Freeze: it thaws with chance 1/4 on each try, and on its third for sure.
- Confusion: 2 to 5 tries; on each one still confused, it hits itself 33 times
  in 100 (a 40-power typeless hit) instead of moving.
- Rage Fist: the hits it counts reset when the user leaves the field.
- Charging moves: the turn after charging, the move goes off; a Pokemon in the
  air or underground is not hit in between.
- Encore: the Pokemon may only repeat the encored move (it may still switch).
"""

from __future__ import annotations

import pytest

from tests.test_board_effects import at_turn_start, game
from tests.test_resolver import ROOT, SHEETS, SPREADS, board, p_of
from wpa import choices as C
from wpa import resolver as R
from wpa.choices import Action

needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)

# --- the board keeps what these rules need ----------------------------------

T1 = """|t:|1
|move|p2a: Inci|Spore|p1a: Whim
|-status|p1a: Whim|slp
|move|p2b: Fini|Swagger|p1b: Rock
|-start|p1b: Rock|confusion
|-activate|p1b: Rock|confusion
|-prepare|p1b: Rock|Meteor Beam"""
T2 = """|t:|2
|cant|p1a: Whim|slp
|move|p1b: Rock|Meteor Beam|p2a: Inci
|-damage|p2a: Inci|60/100
|move|p2a: Inci|Encore|p1b: Rock
|-start|p1b: Rock|Encore"""
T3 = """|t:|3
|switch|p1b: Back|Back, L50|100/100
|move|p2a: Inci|Fake Out|p1a: Whim
|-damage|p1a: Whim|90/100"""


def _mon(s, i):
    return s["our_pokemon"][i]


def test_the_board_counts_sleep_tries_confusion_tries_and_a_charging_move():
    log = game(
        T1,
        "|upkeep",
        "|t:|2\n|turn|2",
        T2,
        "|upkeep",
        "|t:|3\n|turn|3",
        T3,
        "|upkeep",
        "|turn|4",
    )
    s2 = at_turn_start(log, 2)
    whim, rock = _mon(s2, 0), _mon(s2, 1)
    assert whim["status"] == "slp" and whim.get("slp_n", 0) == 0
    assert rock["confused"] == 1 and rock["charging"] == "meteorbeam"
    s3 = at_turn_start(log, 3)
    whim, rock = _mon(s3, 0), _mon(s3, 1)
    assert whim["slp_n"] == 1
    assert "charging" not in rock  # it went off
    assert rock["encore"] == "meteorbeam"
    s4 = at_turn_start(log, 4)
    rock = _mon(s4, 1)
    assert "encore" not in rock and "confused" not in rock  # switching out ends both
    assert _mon(s4, 0)["hits"] == 1


def test_rage_fists_hits_reset_when_the_user_leaves_the_field():
    hit = "|t:|1\n|move|p2a: Inci|Fake Out|p1b: Rock\n|-damage|p1b: Rock|90/100"
    out = "|t:|2\n|switch|p1b: Back|Back, L50|100/100"
    log = game(hit, "|upkeep", "|t:|2\n|turn|2", out, "|upkeep", "|turn|3")
    assert _mon(at_turn_start(log, 2), 1)["hits"] == 1
    assert "hits" not in _mon(at_turn_start(log, 3), 1)


def test_an_encored_or_charging_pokemon_has_only_its_move():
    from tests.test_attribution import _setup

    sheets, _spreads, sides = _setup()
    ours, theirs = sides["p1"], sides["p2"]
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    ours = [dict(m) for m in ours]
    ours[0]["encore"] = "dragonclaw"
    opts = C.options(ours, theirs, sheets["p1"], dex)
    moves = {a.move for a in opts[0] if a.kind == "move"}
    assert moves == {"dragonclaw"} and any(a.kind == "switch" for a in opts[0])
    ours[0].pop("encore")
    ours[0]["charging"] = "stoneedge"
    opts = C.options(ours, theirs, sheets["p1"], dex)
    assert {a.move for a in opts[0]} == {"stoneedge"}  # no switch either


# --- the resolver ------------------------------------------------------------


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


def _claw(**chomp):
    b = board()
    b["p1"][0].update(chomp)
    acts = {
        "p1": (
            Action(0, "move", move="dragonclaw", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
    }
    return b, acts


def _untouched(outs):
    return p_of(outs, lambda o: o.sides["p2"][0]["hp_fraction"] == 1.0)


@needs_showdown
@pytest.mark.parametrize(
    "state, chance",
    [
        ({"status": "par"}, 1 / 8),
        ({"status": "slp"}, 1.0),  # its first try: still asleep
        ({"status": "slp", "slp_n": 1}, 2 / 3),  # second try: wakes 1 in 3
        ({"status": "slp", "slp_n": 2}, 0.0),  # third: wakes for sure
        ({"status": "frz"}, 3 / 4),
        ({"status": "frz", "frz_n": 2}, 0.0),
    ],
)
def test_the_champions_rules_for_paralysis_sleep_and_freeze(tools, state, chance):
    dex, moves, calc = tools
    b, acts = _claw(**state)
    outs = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(b, R.Field(), acts)
    assert _untouched(outs) == pytest.approx(chance)
    assert not any("sleep" in o.partial for o in outs)


@needs_showdown
def test_a_confused_pokemon_hits_itself_33_times_in_100(tools):
    dex, moves, calc = tools
    b, acts = _claw(confused=0)  # its first try while confused: it cannot snap out
    outs = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(b, R.Field(), acts)
    assert _untouched(outs) == pytest.approx(0.33)
    assert p_of(outs, lambda o: o.sides["p1"][0]["hp_fraction"] < 1.0) == pytest.approx(
        0.33
    )
    b, acts = _claw(confused=1)  # second try: snaps out 1 time in 4
    outs = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(b, R.Field(), acts)
    assert _untouched(outs) == pytest.approx(0.75 * 0.33)
    assert not any("confusion" in o.partial for o in outs)


@needs_showdown
def test_a_charging_move_goes_off_the_turn_after(tools):
    dex, moves, calc = tools
    b = board()
    acts = {
        "p1": (
            Action(0, "move", move="solarbeam", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
    }
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    outs = rv.resolve(b, R.Field(), acts)  # no sun: it charges
    assert _untouched(outs) == pytest.approx(1.0)
    assert all(o.sides["p1"][0]["charging"] == "solarbeam" for o in outs)
    assert not any("charging" in o.partial for o in outs)
    b["p1"][0]["charging"] = "solarbeam"  # the next turn: it fires
    outs = rv.resolve(b, R.Field(), acts)
    assert _untouched(outs) == pytest.approx(0.0)
    assert all("charging" not in o.sides["p1"][0] for o in outs)


@needs_showdown
def test_a_pokemon_underground_is_not_hit(tools):
    dex, moves, calc = tools
    b = board()
    acts = {
        "p1": (
            Action(0, "move", move="dig", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="flareblitz", target=("foe", 0)),
            Action(1, "move", move="protect"),
        ),
    }
    # Garchomp is faster: it digs first, and Flare Blitz misses it
    outs = R.Resolver(dex, moves, calc, SHEETS, SPREADS).resolve(b, R.Field(), acts)
    assert all(o.sides["p1"][0]["hp_fraction"] == 1.0 for o in outs)
    assert all(o.sides["p1"][0]["charging"] == "dig" for o in outs)
