"""Damage that depends on the game so far (Week 10 Task 2).

- Last Respects: 50 power, plus 50 for each of the user's side that has fainted.
- Rage Fist: 50 power, plus 50 for each time the user was hit (at most 350); the
  count stays through switching.
- Supreme Overlord: the calculator's own boost, from the user's fainted allies.

The counts come from the log up to the decision, through the board.
"""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_board_actions import T1, T2, log
from tests.test_board_effects import at_turn_start
from wpa.spreads import Spread, damage_request
from wpa.team_sheets import SheetMon

ROOT = Path(__file__).resolve().parent.parent
FULL = Spread("adamant", (32, 32, 0, 0, 0, 2), 1.0)


def test_the_board_counts_each_pokemons_hits_and_not_indirect_damage():
    s = at_turn_start(log(T1, T2), 3)
    ours, theirs = s["our_pokemon"], s["opp_pokemon"]
    assert ours[0]["hits"] == 2  # Fake Out, then Flare Blitz
    assert ours[1]["hits"] == 1  # Moonblast
    assert theirs[0]["hits"] == 1  # Rock Slide
    assert "hits" not in theirs[1]  # only Rocky Helmet hurt Fini


class _Dex:
    moves = {
        "lastrespects": {"category": "Physical"},
        "ragefist": {"category": "Physical"},
        "kowtowcleave": {"category": "Physical"},
    }
    species: dict = {}


def _req(move, ability, **state):
    a = SheetMon(1, "kingambit", "", ability, (move,), "")
    d = SheetMon(1, "incineroar", "", "blaze", ("protect",), "")
    st = {"boosts": {}, "status": "", "item": "", "mega": False, "hp": 1.0, **state}
    dst = {"boosts": {}, "status": "", "item": "", "mega": False, "hp": 1.0}
    return damage_request(a, st, FULL, d, dst, FULL, move, _Dex())


def test_last_respects_and_rage_fist_get_their_power_from_the_counts():
    assert _req("lastrespects", "defiant", fainted=2)["bp"] == 150
    assert _req("lastrespects", "defiant")["bp"] == 50
    assert _req("ragefist", "defiant", hits=3)["bp"] == 200
    assert _req("ragefist", "defiant", hits=9)["bp"] == 350
    assert "bp" not in _req("kowtowcleave", "defiant", fainted=2, hits=3)


def test_supreme_overlord_is_told_the_fainted_allies_and_no_one_else_is():
    assert (
        _req("kowtowcleave", "supremeoverlord", fainted=3)["attacker"]["fainted"] == 3
    )
    assert "fainted" not in _req("kowtowcleave", "defiant", fainted=3)["attacker"]
    # nothing fainted: the request is the same as before, so the cache still answers
    assert "fainted" not in _req("kowtowcleave", "supremeoverlord")["attacker"]


needs_calc = pytest.mark.skipif(
    not (ROOT / "calc" / "node_modules").exists(), reason="needs the damage calculator"
)


@needs_calc
def test_the_calculator_uses_them():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    if not (ROOT / "pokemon-showdown" / "dist").exists():
        pytest.skip("needs the pinned Showdown build")
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    a = SheetMon(1, "kingambit", "", "supremeoverlord", ("kowtowcleave",), "")
    d = SheetMon(1, "incineroar", "", "blaze", ("protect",), "")
    st = {"boosts": {}, "status": "", "item": "", "mega": False, "hp": 1.0}

    def dmg(move, **extra):
        r = damage_request(a, {**st, **extra}, FULL, d, st, FULL, move, dex)
        with DM.Calc() as c:
            return sum(c.run([r])[0]["rolls"])

    assert dmg("kowtowcleave", fainted=3) > dmg("kowtowcleave")
    assert dmg("lastrespects", fainted=2) > 2.5 * dmg("lastrespects")
    assert dmg("ragefist", hits=2) > 2.5 * dmg("ragefist")


def test_the_damage_state_carries_the_sides_fainted_count_and_the_hits():
    from wpa.features import _board_state

    p = {
        "hp_fraction": 0.5,
        "boosts": {},
        "status": "",
        "item": "",
        "mega": False,
        "hits": 2,
    }
    st = _board_state(p, fainted=3)
    assert st["fainted"] == 3 and st["hits"] == 2
    assert _board_state({**p, "hits": 0})["fainted"] == 0
