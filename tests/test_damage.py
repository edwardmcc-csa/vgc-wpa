"""Tests for wpa/damage.py (Week 7 Task 2): the Smogon damage calculator.

The calculator itself is `@smogon/calc` 0.12.0, pinned in `calc/`, with its
Champions rules (level 50, stat points instead of EVs). These tests check that
our bridge hands it the right inputs: ids resolved to names, stat stages,
status, hit points, field conditions, spread moves and critical hits.
"""

# ruff: noqa: E501

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wpa import damage as DM

CALC = Path(__file__).resolve().parent.parent / "calc"
pytestmark = pytest.mark.skipif(
    shutil.which("node") is None
    or not (CALC / "node_modules" / "@smogon" / "calc").exists(),
    reason="needs node and `npm ci --prefix calc`",
)

GAMBIT = {
    "species": "kingambit",
    "nature": "adamant",
    "sps": {"hp": 32, "atk": 32, "spd": 2},
    "item": "blackglasses",
    "ability": "defiant",
}
FLOETTE = {
    "species": "floetteeternal",
    "nature": "modest",
    "sps": {"hp": 32, "spa": 32, "def": 2},
    "item": "",
    "ability": "flowerveil",
}
GARCHOMP = {
    "species": "garchomp",
    "nature": "jolly",
    "sps": {"atk": 32, "spe": 32, "hp": 2},
    "item": "",
    "ability": "roughskin",
}
CORV = {
    "species": "corviknight",
    "nature": "impish",
    "sps": {"hp": 32, "def": 32, "spd": 2},
    "item": "",
    "ability": "pressure",
}


@pytest.fixture(scope="module")
def calc():
    c = DM.Calc(CALC)
    yield c
    c.close()


def one(calc, attacker, defender, move, **kw):
    (r,) = calc.run([DM.request(attacker, defender, move, **kw)])
    assert "error" not in r, r
    return r


def test_sixteen_rolls_from_85_to_100_percent(calc):
    r = one(calc, GAMBIT, FLOETTE, "kowtowcleave")
    rolls = r["rolls"]
    assert len(rolls) == 16 and rolls == sorted(rolls)
    assert 0.83 < rolls[0] / rolls[-1] < 0.87
    assert r["max_hp"] > 150  # level 50 with 32 stat points in HP


def test_type_immunity_gives_no_damage(calc):
    assert one(calc, GARCHOMP, CORV, "earthquake")["rolls"] == [0] * 16


def test_stages_status_and_screens_change_damage(calc):
    base = one(calc, GAMBIT, FLOETTE, "kowtowcleave")["rolls"][-1]
    up = one(calc, {**GAMBIT, "boosts": {"atk": 1}}, FLOETTE, "kowtowcleave")["rolls"][
        -1
    ]
    burned = one(calc, {**GAMBIT, "status": "brn"}, FLOETTE, "kowtowcleave")["rolls"][
        -1
    ]
    screen = one(calc, GAMBIT, FLOETTE, "kowtowcleave", field={"reflect": True})[
        "rolls"
    ][-1]
    assert up == pytest.approx(base * 1.5, rel=0.03)
    assert burned == pytest.approx(base * 0.5, rel=0.03)
    assert screen == pytest.approx(base * 2732 / 4096, rel=0.03)


def test_spread_moves_lose_a_quarter_only_when_they_hit_two(calc):
    two = one(calc, GARCHOMP, FLOETTE, "earthquake", spread=True)["rolls"][-1]
    single = one(calc, GARCHOMP, FLOETTE, "earthquake", spread=False)["rolls"][-1]
    assert two == pytest.approx(single * 0.75, rel=0.03)


def test_critical_hits_and_weather(calc):
    base = one(calc, FLOETTE, GAMBIT, "moonblast")["rolls"][-1]
    crit = one(calc, FLOETTE, GAMBIT, "moonblast", crit=True)["rolls"][-1]
    assert crit == pytest.approx(base * 1.5, rel=0.03)
    fire = one(calc, FLOETTE, GAMBIT, "flamethrower")["rolls"][-1]
    sun = one(calc, FLOETTE, GAMBIT, "flamethrower", field={"weather": "sunnyday"})[
        "rolls"
    ][-1]
    assert sun == pytest.approx(fire * 1.5, rel=0.03)


def test_current_hit_points_are_returned_and_requests_are_cached(calc):
    r = one(calc, GAMBIT, {**FLOETTE, "hp": 0.5}, "kowtowcleave")
    assert r["cur_hp"] == pytest.approx(r["max_hp"] / 2, abs=1)
    before = calc.calls
    one(calc, GAMBIT, {**FLOETTE, "hp": 0.5}, "kowtowcleave")
    assert calc.calls == before


def test_raw_stats_for_speed(calc):
    (r,) = calc.run([{"op": "stats", "mon": GARCHOMP}])
    # Champions: base 102 + 32 stat points + 20, Jolly x1.1
    assert r["stats"]["spe"] == int((102 + 32 + 20) * 1.1)


def test_an_unknown_name_is_an_error_not_a_crash(calc):
    (r,) = calc.run(
        [DM.request({**GAMBIT, "species": "notapokemon"}, FLOETTE, "kowtowcleave")]
    )
    assert "error" in r
    assert one(calc, GAMBIT, FLOETTE, "kowtowcleave")["rolls"]  # still alive


MAUSHOLD = {
    "species": "maushold",
    "nature": "jolly",
    "sps": {"hp": 32, "spe": 32},
    "item": "",
    "ability": "friendguard",
}
SABLEYE = {
    "species": "sableye",
    "nature": "careful",
    "sps": {"hp": 32},
    "item": "",
    "ability": "prankster",
}


def test_super_fang_takes_half_the_current_hit_points_and_misses_ghosts(calc):
    r = one(calc, MAUSHOLD, {**GAMBIT, "hp": 0.5}, "superfang")
    assert r["rolls"] == [max(1, r["cur_hp"] // 2)] * 16
    assert one(calc, MAUSHOLD, SABLEYE, "superfang")["rolls"] == [0] * 16
    assert one(calc, GAMBIT, FLOETTE, "seismictoss")["rolls"] == [50] * 16  # level 50
    assert one(calc, GAMBIT, SABLEYE, "seismictoss")["rolls"] == [0] * 16  # Ghost
    assert one(calc, GAMBIT, FLOETTE, "counter").get("unknown")


def test_final_speed_with_tailwind_paralysis_and_scarf(calc):
    def speed(**kw):
        m = {**GARCHOMP, **kw.pop("mon", {})}
        (r,) = calc.run([{"op": "speed", "mon": m, "field": {}, **kw}])
        return r["speed"]

    assert speed() == 169
    assert speed(tailwind=True) == 338
    assert speed(mon={"status": "par"}) == 84
    assert speed(mon={"item": "choicescarf"}) == 253
    assert speed(mon={"boosts": {"spe": 1}}) == 253
