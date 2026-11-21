"""Week 16, Task 3: the bot's opponents. Random (poke_env's) needs no code here.
"The strongest move": each Pokemon's most damaging move, at the foe it
damages most, by a rough damage estimate (power, same-type bonus, type
matchup, the base attacking and defending stats, accuracy, the spread
reduction). "The choice model": choices drawn as players typically make them.
"The engine at strength 0": the bot, expecting typical play of its opponent."""

from __future__ import annotations

import json
import random

import numpy as np
import pytest

from tests.test_bot import _battle_until
from wpa import advise as AD
from wpa import opponents as O


def test_the_strongest_move_is_the_most_damaging_at_its_best_target():
    b, _ = _battle_until(4)  # turn 2: Gholdengo and Arcanine-H against
    order = O.strongest_order(b, random.Random(0))  # Sneasler and Basculegion-F
    first, second = order.message.split(", ")
    # Gholdengo (SpA 133): Shadow Ball (80, Ghost, its type) at Basculegion-F
    # (Water/Ghost: twice the damage; SpD 75) scores 80 x 1.5 x 2 x 133/75 =
    # 426, over Make It Rain on both (120 x 1.5 x 0.75 x (1 x 133/80 + 0.5 x
    # 133/75) = 344)
    assert first == "/choose move shadowball 2"
    # Arcanine-H (Atk 115): Flare Blitz (120, Fire) at Sneasler (Def 60) scores
    # 120 x 1.5 x 115/60 = 345, over Head Smash (150, Rock, 80% sure) at
    # Basculegion-F (Def 65): 150 x 1.5 x 0.8 x 115/65 = 318
    assert second == "move flareblitz 1"


def test_the_strongest_move_never_hits_its_own_side_and_never_protects():
    b, _ = _battle_until(4)
    for seed in range(20):
        msg = O.strongest_order(b, random.Random(seed)).message
        assert "protect" not in msg and " -1" not in msg and " -2" not in msg


def test_a_forced_switch_is_a_legal_one():
    from wpa.bot import legal_orders

    b, _ = _battle_until(3)
    msg = O.strongest_order(b, random.Random(1)).message
    assert msg in {o.message for o in legal_orders(b)}


def test_team_preview_as_players_typically_choose():
    class Leads:
        def chances(self, sheet, fmt, prev):
            p = np.zeros(15)
            p[3] = 1.0  # pairs(6)[3] == (0, 4)
            return p

    class Bring:
        def odds(self, fmt, sheet, prev):
            return [1.0, 0.1, 0.1, 9.0, 1.0, 0.1]

    pick = AD.draw_bring(Leads(), Bring(), "regmc", _SHEET, np.random.default_rng(0))
    assert pick.leads == (0, 4)
    assert len(pick.back) == 2 and set(pick.back).isdisjoint(pick.leads)
    picks = [
        AD.draw_bring(Leads(), Bring(), "regmc", _SHEET, np.random.default_rng(s))
        for s in range(200)
    ]
    assert sum(3 in p.back for p in picks) > 150  # the likeliest is brought most


def test_a_typical_choice_is_drawn_by_its_chance():
    mix = [("a", 0.7), ("b", 0.2), ("c", 0.1)]
    got = [O.draw(mix, np.random.default_rng(s)) for s in range(1000)]
    assert 600 < got.count("a") < 800 and got.count("c") < 200


def test_the_engine_at_strength_0_expects_typical_play():
    from wpa import attribution as A

    base: dict = dict(
        dexes={},
        tables={},
        moves={},
        calc=None,
        store=None,
        bring=None,
        policy=None,
        predict={},
    )
    t = A.Tools(**base, strength=6.55)
    t.by_format = {
        "regmc": {
            "strength": 9.6,
            "rating_line": {"s0": 8.7, "slope": 0.32, "center": 1200},
        }
    }
    z = O.at_strength_zero(t)
    g = z.for_format("regmc").for_game("|player|p1|A|1|1500\n|player|p2|B|2|1500\n")
    assert g.main_strength == 0.0
    assert t.for_format("regmc").strength == 9.6  # the bot's own tools unchanged


_SHEET = tuple(json.loads('["a", "b", "c", "d", "e", "f"]'))


@pytest.fixture(autouse=True)
def _poke_env():
    pytest.importorskip("poke_env")


def test_every_bot_takes_its_request_s_token():
    """Week 17: the bot answers each request through one door (`_answer`),
    which hands `_decide` the request's token. The choice-model opponent had
    its own `_decide` without it, and failed on every request in the first
    gate run (20 Nov): 63 of its 200 games stopped and the rest were won on
    its time."""
    import inspect

    for cls in (O.EngineBot, O.TypicalBot):
        assert "token" in inspect.signature(cls._decide).parameters, cls
