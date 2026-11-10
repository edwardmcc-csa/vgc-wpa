"""Forced switches (Week 10 Task 6): after a Pokemon faints, which Pokemon to
send in is a decision of its own, and a game's decision points chain (§2).

- the next decision point after a turn: the replacement, if one is needed,
  else the next turn's start, else the end of the game;
- the replacements the log shows, with the Pokemon that could have come in.
"""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_board_effects import LEADS
from tests.test_decisions import EMPTY, HEAD
from wpa import attribution as A
from wpa import choices as C
from wpa import decisions as D
from wpa.choices import Action

KO = (
    "|t:|1\n|move|p1b: Rock|Rock Slide|p2b: Fini|[spread] p2a,p2b\n"
    "|-damage|p2a: Inci|60/100\n|-damage|p2b: Fini|0 fnt\n|faint|p2b: Fini"
)
# as in real logs: the turn's end in a block of its own, the replacement in the next
UPKEEP = "|upkeep"
REPLACE = "|t:|1\n|switch|p2b: Last|Last, L50|100/100\n|t:|2\n|turn|2"
QUIET = "|t:|2\n|move|p1b: Rock|Rock Slide|p2a: Inci|[spread] p2a,p2b\n|-damage|p2a: Inci|30/100\n|-damage|p2b: Last|70/100"
END2 = "|upkeep\n|t:|3\n|turn|3"


def game(*blocks):
    return "\n|\n".join([HEAD, LEADS, *blocks, "|win|A"])


def test_the_next_decision_point_after_a_turn():
    g = D.build_game(game(KO, UPKEEP, REPLACE, QUIET, END2), EMPTY)
    s1 = [
        k
        for k, s in enumerate(g.states["p1"])
        if s["turn"] == 1 and s["moment"] == "turn_start"
    ][0]
    role, i = A.next_point(g, s1)
    assert role == "p2" and g.states["p2"][i]["moment"] == "after_turn"
    # after the replacement: the next turn's start, on p1's side
    role2, i2 = A.next_point(g, s1, after_replacement=True)
    assert role2 == "p1" and g.states["p1"][i2]["moment"] == "turn_start"
    assert g.states["p1"][i2]["turn"] == 2
    # a quiet turn: straight to the next turn's start
    s2 = [
        k
        for k, s in enumerate(g.states["p1"])
        if s["turn"] == 2 and s["moment"] == "turn_start"
    ][0]
    role3, i3 = A.next_point(g, s2)
    assert role3 == "p1" and g.states["p1"][i3]["turn"] == 3


def test_the_replacements_the_log_shows():
    reps = C.replacements(game(KO, UPKEEP, REPLACE, QUIET, END2))
    (r,) = reps
    assert r.turn == 1 and r.role == "p2"
    assert r.taken == {1: 3}  # Fini (second on the sheet) replaced by Last (fourth)
    assert set(r.bench) == {
        2,
        3,
        4,
        5,
    }  # every one not out: the log does not say which were brought
    opts = C.replacement_options(r)
    assert Action(1, "switch", switch_to=3) in opts[1] and len(opts[1]) == 4


# --- the board after a forced switch, and its split -------------------------

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
needs_showdown = __import__("pytest").mark.skipif(
    not (ROOT / "pokemon-showdown" / "dist").exists()
    or not (ROOT / "calc" / "node_modules").exists(),
    reason="needs the pinned Showdown build and the damage calculator",
)


def _mon(species, hp=1.0, active=True, fainted=False):
    return {
        "species": species,
        "hp_fraction": 0.0 if fainted else hp,
        "fainted": fainted,
        "active": active and not fainted,
        "mega": False,
        "boosts": {},
        "status": "",
        "item": "",
        "moved": False,
        "last_move": "",
        "protect_streak": 0,
    }


def _switch_in_resolver():
    from wpa import damage as DM
    from wpa import resolver as R
    from wpa.spreads import Spread
    from wpa.team_sheets import SheetMon, load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    sp = Spread("hardy", (0, 0, 0, 0, 0, 0), 1.0)
    sheets = {
        # Garchomp (faster) sets rain on entry, Incineroar (slower) sets sun
        "p1": (
            SheetMon(1, "kingambit", "", "defiant", ("protect",), ""),
            SheetMon(2, "sneasler", "", "unburden", ("protect",), ""),
            SheetMon(3, "garchomp", "", "drizzle", ("protect",), ""),
        ),
        "p2": (
            SheetMon(1, "whimsicott", "", "prankster", ("protect",), ""),
            SheetMon(2, "rotom", "", "levitate", ("protect",), ""),
            SheetMon(3, "incineroar", "", "drought", ("protect",), ""),
            SheetMon(4, "arcanine", "", "intimidate", ("protect",), ""),
        ),
    }
    spreads = {(r, i): sp for r in sheets for i in range(len(sheets[r]))}
    calc = DM.Calc()
    return R.Resolver(dex, moves, calc, sheets, spreads), calc


def _after_ko():
    return {
        "p1": [
            _mon("kingambit"),
            _mon("sneasler", fainted=True),
            _mon("garchomp", active=False),
        ],
        "p2": [
            _mon("whimsicott"),
            _mon("rotom", fainted=True),
            _mon("incineroar", active=False),
            _mon("arcanine", active=False),
        ],
    }


@needs_showdown
def test_a_forced_switch_plays_the_incoming_pokemons_entry():
    from wpa import resolver as R

    rv, calc = _switch_in_resolver()
    try:
        b = _after_ko()
        (o,) = rv.replace(b, R.Field(), {"p2": (Action(1, "switch", switch_to=3),)})
        assert o.prob == 1.0
        assert o.sides["p2"][3]["active"] and not o.sides["p2"][1]["active"]
        assert o.sides["p1"][0]["boosts"] == {"atk": 1}  # Intimidate, then Defiant +2
        assert b["p1"][0]["boosts"] == {}  # the board given is not changed
        # both sides at once: entry effects in Speed order, so the slower one's
        # weather stays; under Trick Room the faster one's
        both = {
            "p1": (Action(1, "switch", switch_to=2),),
            "p2": (Action(1, "switch", switch_to=2),),
        }
        (o,) = rv.replace(_after_ko(), R.Field(), both)
        assert o.field.weather == "sunnyday"
        (o,) = rv.replace(_after_ko(), R.Field(trickroom=5), both)
        assert o.field.weather == "raindance"
    finally:
        calc.close()


def _stand_in(sides) -> float:
    """Pokemon left and hit points, those on the field counted again."""

    def side(r):
        return sum(
            0.0 if m["fainted"] else 1.0 + m["hp_fraction"] * (2 if m["active"] else 1)
            for m in sides[r]
        )

    return min(1.0, max(0.0, 0.5 + 0.1 * (side("p1") - side("p2"))))


@needs_showdown
def test_a_forced_switch_is_split_like_a_turn_and_theirs_is_zero_when_only_one_replaces():
    from wpa import resolver as R

    rv, calc = _switch_in_resolver()
    try:
        b = _after_ko()
        b["p2"][2]["hp_fraction"] = (
            0.2  # Incineroar is low: Arcanine is the better pick
        )
        b["p2"][2]["active"] = False
        tv = A.TurnValues(
            A.SwitchIns(rv),
            b,
            R.Field(),
            lambda outs: [_stand_in(o.sides) for o in outs],
        )
        opts = {1: [Action(1, "switch", switch_to=j) for j in (2, 3)]}
        p2_value = tv.for_role("p2")
        inci, arca = (
            (Action(1, "switch", switch_to=2),),
            (Action(1, "switch", switch_to=3),),
        )
        assert p2_value(arca, ()) > p2_value(inci, ())
        mix = A.mixture({1: list(zip(opts[1], (0.5, 0.5)))})
        none = [((), 1.0)]
        before = 1 - _stand_in(b)
        s = A.decompose(
            p2_value,
            before,
            p2_value(inci, ()),
            [(inci, 1.0)],
            none,
            none,
            [[(arca, 1.0)], [(inci, 1.0)]],
        )
        assert (
            s.conserved()
            and s.theirs == 0.0
            and s.dice == __import__("pytest").approx(0.0)
        )
        assert s.vs_best is not None and s.vs_best < 0  # Arcanine was better
        assert len(mix) == 2
    finally:
        calc.close()


def _r(tag, kind, turn, point, before, after, role="p1"):
    return {
        "tag": tag,
        "kind": kind,
        "turn": turn,
        "point": point,
        "role": role,
        "before": before,
        "after": after,
    }


def test_a_games_swings_chain_and_add_up_to_its_result():
    recs = [
        _r("g", "turn", 1, 2, 0.50, 0.70),
        _r("g", "replacement", 1, 3, 0.70, 0.65),
        _r("g", "turn", 2, 4, 0.65, 1.00),
    ]
    recs += [
        dict(r, role="p2", before=1 - r["before"], after=1 - r["after"]) for r in recs
    ]
    (c,) = A.chains(recs, results={"g": 1.0})
    assert c["chained"] and c["adds_up"] and abs(c["gap"]) < 1e-9
    # a point left out breaks the chain, and the check says where
    (c,) = A.chains([recs[0], recs[2]], results={"g": 1.0})
    assert not c["chained"] and c["first_break"] == 1
    (c,) = A.chains(recs, results={"g": 0.0})
    assert c["chained"] and not c["adds_up"]


def test_the_summary_reports_forced_switches_and_whether_games_chain(tmp_path):
    import json

    from tests.test_attribution import _rec

    def rec(kind, turn, point, role, before, after, **kw):
        r = _rec("g1", turn, role, before, after, alt=True)
        r.update(kind=kind, point=point, result=1.0, after_board=after, **kw)
        return r

    recs = []
    for role, flip in (("p1", False), ("p2", True)):

        def f(x, flip=flip):
            return 1 - x if flip else x

        recs += [
            rec("turn", 1, 2, role, f(0.5), f(0.7)),
            rec(
                "replacement",
                1,
                3,
                role,
                f(0.7),
                f(0.6),
                replacing=role == "p2",
                choices=3,
            ),
            rec("turn", 2, 4, role, f(0.6), f(1.0)),
        ]
    path = tmp_path / "a.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    text = A.report(path)
    assert "Reg M-A: 1 games, 4 decision points (2 turns)" in text  # turns alone
    assert "forced switches: 1 (1 decisions by the player replacing)" in text
    assert "the 10 biggest forced-switch decisions" in text
    assert "g1 after turn 1: p2 yours" in text
    assert "games whose decision points chain: 1 of 1" in text
    assert "swings add up to the result: 1 of 1" in text


def test_a_player_cannot_send_in_a_pokemon_they_did_not_bring():
    move = Action(0, "move", move="protect")
    to2, to3 = Action(0, "switch", switch_to=2), Action(0, "switch", switch_to=3)
    pivot3 = Action(0, "move", move="uturn", target=("foe", 0), switch_to=3)
    opts = {0: [move, to2, to3, pivot3]}
    ch = {0: [0.4, 0.3, 0.2, 0.1]}
    o, c = A.only_brought(opts, ch, {0, 1, 2, 5})  # the four the log shows
    assert o == {0: [move, to2]}
    assert c[0] == __import__("pytest").approx([0.4 / 0.7, 0.3 / 0.7])
    # fewer than four seen: any of the rest could have been brought
    assert A.only_brought(opts, ch, None) == (opts, ch)
    assert A.brought_four({"p1": {0, 1, 2}, "p2": {0, 1, 2, 5}}) == {
        "p1": None,
        "p2": {0, 1, 2, 5},
    }


def test_a_turn_over_its_budget_values_boards_on_a_coarser_grid_and_drops_none():
    import numpy as np

    from wpa.resolver import Field

    s0 = {"turn": 1, "decision_index": 0, "our_pokemon": [], "opp_pokemon": []}
    rows = []

    def make(budget):
        bw = A.BoardWP(
            lambda X: np.asarray(X)[:, 0],
            [dict(s0, observations=[])],
            0,
            None,
            {},
            None,
            None,
            "A",
            None,
            budget=budget,
        )

        def row(ours, theirs, fld):
            rows.append(1)
            return [ours[0]["hp_fraction"]]

        bw._row = row  # a stand-in for the feature row: p1's first hit points
        return bw

    items = [([_mon("a", hp=i / 1000)], [_mon("b")], Field()) for i in range(1, 400)]
    rows.clear()
    full = make(None).boards(items)
    assert len(rows) == 399 and full[0] == __import__("pytest").approx(0.001)
    rows.clear()
    bw = make(5)
    got = bw.boards(items)
    assert len(rows) <= 5 and len(got) == 399  # every board valued, few rows
    assert bw.grid > 0.05  # the grid it needed is kept
    assert max(abs(got - full)) <= bw.grid  # each board valued within its cell
    rows.clear()
    assert (bw.boards(items) == got).all() and not rows  # kept, not valued again
