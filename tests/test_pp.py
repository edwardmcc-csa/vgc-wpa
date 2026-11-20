"""Week 17, Task 3: PP (the PO's game 629). A move's PP runs out: the board
counts each use, a move with none left cannot be chosen, and Encore fails on a
target whose last move has none left (Showdown's Encore `onTry`). Champions
gives Protect 8 PP: (5 / 5 + 1) x 4 (`data/mods/champions/scripts.ts`), which
is what ended the bot's Encore on the PO's Archaludon after its eighth Protect.

Not counted: Pressure's extra PP (none in the pool's teams), and Struggle when
every move is out (the moves stay offered then)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_board_effects import at_turn_start, game
from wpa import choices as C
from wpa.team_sheets import Dex, SheetMon

ROOT = Path(__file__).resolve().parent.parent

B1 = """|t:|1
|move|p1b: Rock|Protect|p1b: Rock
|-singleturn|p1b: Rock|Protect"""
B2 = """|t:|2
|move|p1b: Rock|Protect||[still]
|-fail|p1b: Rock"""
B3 = """|t:|3
|move|p1b: Rock|Meteor Beam||[still]
|-prepare|p1b: Rock|Meteor Beam"""
B4 = """|t:|4
|move|p1b: Rock|Meteor Beam|p2a: Inci
|-damage|p2a: Inci|50/100"""


def test_the_board_counts_each_move_s_pp_as_it_is_used():
    log = game(
        B1,
        "|upkeep",
        "|t:|2\n|turn|2",
        B2,
        "|upkeep",
        "|t:|3\n|turn|3",
        B3,
        "|upkeep",
        "|t:|4\n|turn|4",
        B4,
        "|upkeep",
        "|t:|5\n|turn|5",
    )
    rock = at_turn_start(log, 5)["our_pokemon"][1]
    # a Protect that fails still uses PP; a charged move uses it once
    assert rock["pp_used"] == {"protect": 2, "meteorbeam": 1}
    early = at_turn_start(log, 2)["our_pokemon"][1]
    assert early["pp_used"] == {"protect": 1}  # each turn's own count


DEX = Dex(
    species={},
    moves={
        "protect": {"target": "self", "category": "Status", "pp": 8},
        "moonblast": {"target": "normal", "category": "Special", "pp": 12},
    },
    items={},
)
WHIM = SheetMon(1, "whimsicott", "", "prankster", ("protect", "moonblast"), "")


def _st(**kw):
    return {"active": True, "fainted": False, "moved": False, "status": "", **kw}


def test_a_move_with_no_pp_left_cannot_be_chosen():
    foes = [_st()]
    ours = [_st(pp_used={"protect": 8, "moonblast": 3})]
    got = {a.move for a in C.options(ours, foes, [WHIM], DEX)[0]}
    assert got == {"moonblast"}
    ours = [_st(pp_used={"protect": 7})]
    assert "protect" in {a.move for a in C.options(ours, foes, [WHIM], DEX)[0]}
    # every move out: they stay offered (Struggle is not modelled)
    ours = [_st(pp_used={"protect": 8, "moonblast": 12})]
    assert {a.move for a in C.options(ours, foes, [WHIM], DEX)[0]} == {
        "protect",
        "moonblast",
    }


needs_showdown = pytest.mark.skipif(
    not (ROOT / "pokemon-showdown-mc" / "dist").exists()
    or not (ROOT / "pokemon-showdown" / "dist").exists(),
    reason="needs the pinned Showdown builds",
)


@needs_showdown
def test_each_move_s_pp_in_battle_comes_from_showdown_s_own_rule():
    from wpa import resolver as R
    from wpa.team_sheets import load_dexes

    moves = R.load_moves(ROOT / "pokemon-showdown-mc", "champions")
    assert moves["protect"]["pp"] == 8  # Champions: (5 / 5 + 1) x 4
    assert moves["moonblast"]["pp"] == 16  # 15 base: (3 + 1) x 4
    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    assert dex.moves["protect"]["pp"] == 8


@needs_showdown
def test_encore_fails_on_a_move_with_no_pp_left():
    from tests.test_resolver import SHEETS, SPREADS, board
    from wpa import damage as DM
    from wpa import resolver as R
    from wpa.choices import Action
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    acts = {
        "p1": (Action(0, "move", move="stoneedge", target=("foe", 1)),),
        "p2": (Action(1, "move", move="encore", target=("foe", 0)),),
    }
    with DM.Calc() as calc:
        rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
        for used, works in ((8, False), (3, True)):
            sides = board()
            sides["p1"][1]["active"] = False
            g = sides["p1"][0]
            g.update(last_move="protect", pp_used={"protect": used})
            outs = rv.resolve(sides, R.Field(), acts)
            got = any(o.sides["p1"][0].get("encore") for o in outs)
            assert got == works
