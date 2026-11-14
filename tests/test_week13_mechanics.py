"""Week 13 Task 2: rules the resolver check found missing or modelled in part.

- Sitrus Berry: eaten whenever the holder falls to half or less, from any
  damage (recoil, Rough Skin, Life Orb, the end of the turn), not only a hit
  (resolver check, 13 Nov: 25 of 300 sampled HP misses).
- Life Dew heals the user and its ally a quarter each (97 uses in the check's
  892 games; the ally was left out).
- Leech Seed drains into whoever stands in the seeder's place: when the
  seeder switches out this turn, the Pokemon that comes in is healed.
"""

from __future__ import annotations

import pytest

from tests.test_more_mechanics import needs_showdown
from tests.test_resolver import ROOT, SHEETS, SPREADS, board, mon
from tests.test_week12_mechanics import P1_QUIET, SINISTCHA, _bench
from wpa import resolver as R
from wpa.choices import Action


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


QUIET2 = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))


@needs_showdown
def test_sitrus_berry_is_eaten_after_recoil_takes_the_holder_to_half(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    b = board()
    b["p1"][0].update(hp_fraction=0.52, item="sitrusberry")
    edge = (
        Action(0, "move", move="doubleedge", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    quiet = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    outs = rv.resolve(b, R.Field(), {"p1": edge, "p2": quiet})
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1.0]
    assert hit
    for o in hit:
        g = o.sides["p1"][0]
        assert g["item"] == "" and g["rev_item"] == "sitrusberry"
        assert g["hp_fraction"] > 0.5  # recoil took it under half, then a quarter back


@needs_showdown
def test_life_dew_heals_the_user_and_its_ally(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    b = board()
    b["p2"][0]["hp_fraction"] = 0.5
    b["p2"][1]["hp_fraction"] = 0.6
    dew = (Action(0, "move", move="swordsdance"), Action(1, "move", move="lifedew"))
    outs = rv.resolve(b, R.Field(), {"p1": P1_QUIET, "p2": dew})
    for o in outs:
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(0.75, abs=0.01)
        assert o.sides["p2"][1]["hp_fraction"] == pytest.approx(0.85, abs=0.01)
        assert "move:lifedew" not in o.partial


@needs_showdown
def test_leech_seed_heals_the_pokemon_that_took_the_seeders_place(tools):
    """Game 2635937395 turn 3: the seeder switched out and its place was healed;
    the resolver marked it partly modelled."""
    rv, b = _bench(tools)
    b["p1"][0]["seeded"] = 1  # Whimsicott seeded Garchomp
    b["p2"][2]["hp_fraction"] = 0.5  # Sinistcha, on the bench
    out = (Action(0, "move", move="protect"), Action(1, "switch", switch_to=2))
    outs = rv.resolve(b, R.Field(), {"p1": P1_QUIET, "p2": out})
    gained = rv.max_hp("p1", 0) // 8 / rv.max_hp("p2", 2)
    for o in outs:
        assert "leech seed heals the Pokemon in its place" not in o.partial
        assert o.sides["p1"][0]["seeded"] == 2
        assert o.sides["p2"][2]["hp_fraction"] == pytest.approx(0.5 + gained, abs=0.01)
    assert SINISTCHA.species == "sinistcha"
