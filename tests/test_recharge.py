"""Week 18, Task 4: a Pokemon that must recharge (Hyper Beam, Meteor Assault)
has one choice, the recharge, and cannot switch: Showdown's request shows only
"Recharge" and marks it trapped. In the Week 17 gate the advice offered it its
moves; 40 of the 66 choices replaced by a legal one were this."""

from __future__ import annotations

import json

import pytest

from tests.test_resolver import ROOT
from wpa import choices as C
from wpa.choices import Action

pytestmark = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists(),
    reason="needs the pinned Showdown build",
)


def test_a_pokemon_that_must_recharge_has_only_the_recharge():
    from tests.test_attribution import _setup
    from wpa.team_sheets import load_dexes

    sheets, _spreads, sides = _setup()
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    ours = [dict(m) for m in sides["p1"]]
    ours[0]["recharge"] = 1
    opts = C.options(ours, sides["p2"], sheets["p1"], dex)
    assert opts[0] == [Action(0, "move", move="recharge")]
    others = [i for i in opts if i != 0]
    assert all(len(opts[i]) > 1 for i in others)  # its partner as before


def test_the_recharge_is_sent_as_showdowns_choice():
    from tests.test_bot import IDENTS, _battle_until
    from wpa import bot as B

    b, _lines = _battle_until(4)  # Gholdengo in place a, Arcanine in place b
    r = json.loads(json.dumps(b.last_request))
    r["active"][0] = {
        "moves": [{"move": "Recharge", "id": "recharge"}],
        "trapped": True,
    }
    b.parse_request(r)
    pick = (Action(0, "move", move="protect"), Action(1, "move", move="recharge"))
    order, why = B.order_for(pick, b, IDENTS, {4: 1, 3: 2})
    assert why == ""
    assert order.message == "/choose move 1, move protect"
