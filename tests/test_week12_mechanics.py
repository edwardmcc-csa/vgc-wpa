"""Rules the resolver check found missing in Week 12 (Task 1's reasons left). On
the 892 games, turns where these acted were missed far more often than the 19%
of all turns, and none was marked partly modelled:
- Hospitality: 228 turns, 64% missed (Sinistcha heals its ally a quarter on
  coming in);
- Regenerator: 10 turns, all missed (a third back on switching out);
- Infestation and the other binding moves: 18 turns, 94% missed (an eighth at
  each end of turn while bound);
- Solar Power: 4 turns, all missed (an eighth lost at each end of turn in sun)."""

# ruff: noqa: E501

from __future__ import annotations

import pytest

from tests.test_board_effects import at_turn_start
from tests.test_more_mechanics import _mon, _turns, needs_showdown
from tests.test_resolver import ROOT, SHEETS, SPREADS, board, mon
from wpa import resolver as R
from wpa.choices import Action
from wpa.team_sheets import SheetMon


@pytest.fixture(scope="module")
def tools():
    from wpa import damage as DM
    from wpa.team_sheets import load_dexes

    dex = load_dexes(ROOT / "pokemon-showdown")["regma"]
    moves = R.load_moves(ROOT / "pokemon-showdown", "championsregma")
    c = DM.Calc()
    yield dex, moves, c
    c.close()


SINISTCHA = SheetMon(3, "sinistcha", "", "hospitality", ("matchagotcha",), "")
QUIET1 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))


def _three(tools, p2_first=None):
    """p2 with a third Pokemon, Sinistcha, on the bench."""
    dex, moves, calc = tools
    first = p2_first or SHEETS["p2"][0]
    sheets = {"p1": SHEETS["p1"], "p2": (first, SHEETS["p2"][1], SINISTCHA)}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p2"].append(mon("sinistcha"))
    b["p2"][2].update(active=False, hp_fraction=1.0)
    return rv, b


@needs_showdown
def test_hospitality_heals_the_ally_a_quarter_on_coming_in(tools):
    rv, b = _three(tools)
    b["p2"][1]["hp_fraction"] = 0.5
    p2 = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 1)
        assert o.sides["p2"][1]["hp_fraction"] == pytest.approx(
            (round(0.5 * hp) + hp // 4) / hp, abs=1 / hp
        )


@needs_showdown
def test_regenerator_heals_a_third_on_switching_out(tools):
    regen = SheetMon(1, "incineroar", "", "regenerator", ("protect",), "")
    rv, b = _three(tools, regen)
    b["p2"][0]["hp_fraction"] = 0.4
    p2 = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 0)
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx(
            (round(0.4 * hp) + hp // 3) / hp, abs=1 / hp
        )
        assert not o.sides["p2"][0]["active"]


@needs_showdown
def test_a_binding_move_costs_an_eighth_at_each_end_of_turn(tools):
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    # already bound: an eighth at the end of the turn
    b = board()
    b["p2"][0]["bound"] = 8
    p2 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p2", 0)
        assert o.sides["p2"][0]["hp_fraction"] == pytest.approx((hp - hp // 8) / hp)
    # Infestation binds what it hits, and the first eighth comes the same turn
    p1 = (
        Action(0, "move", move="infestation", target=("foe", 0)),
        Action(1, "move", move="protect"),
    )
    outs = rv.resolve(board(), R.Field(), {"p1": p1, "p2": p2})
    hit = [o for o in outs if o.sides["p2"][0].get("bound")]
    assert sum(o.prob for o in hit) == pytest.approx(1.0)  # it never misses
    assert not any(o.partial for o in outs)


@needs_showdown
def test_solar_power_costs_an_eighth_in_sun(tools):
    dex, moves, calc = tools
    sol = SheetMon(1, "garchomp", "", "solarpower", ("swordsdance", "protect"), "")
    rv = R.Resolver(
        dex, moves, calc, {"p1": (sol, SHEETS["p1"][1]), "p2": SHEETS["p2"]}, SPREADS
    )
    p2 = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    sunny = R.Field(weather="sunnyday", weather_left=3)
    for o in rv.resolve(board(), sunny, {"p1": QUIET1, "p2": p2}):
        hp = rv.max_hp("p1", 0)
        assert o.sides["p1"][0]["hp_fraction"] == pytest.approx((hp - hp // 8) / hp)
    for o in rv.resolve(board(), R.Field(), {"p1": QUIET1, "p2": p2}):
        assert o.sides["p1"][0]["hp_fraction"] == 1.0


def test_the_board_keeps_a_binding_until_it_ends_or_the_pokemon_leaves():
    log = _turns(
        "|t:|1\n|move|p2a: Inci|Infestation|p1a: Whim\n|-damage|p1a: Whim|90/100\n"
        "|-activate|p1a: Whim|move: Infestation|[of] p2a: Inci\n"
        "|-damage|p1a: Whim|78/100|[from] move: Infestation|[partiallytrapped]",
        "|t:|2\n|-end|p1a: Whim|Infestation|[partiallytrapped]",
        "|t:|3\n|move|p2a: Inci|Infestation|p1b: Rock\n|-damage|p1b: Rock|90/100\n"
        "|-activate|p1b: Rock|move: Infestation|[of] p2a: Inci",
        "|t:|4\n|switch|p1b: Back|Back, L50|100/100",
    )
    assert _mon(at_turn_start(log, 2), 0)["bound"] == 8
    assert "bound" not in _mon(at_turn_start(log, 3), 0)  # it ended
    assert _mon(at_turn_start(log, 4), 1)["bound"] == 8
    assert "bound" not in _mon(at_turn_start(log, 5), 1)  # it left the field


def _mean_lost(rv, b, acts, side="p1", idx=0):
    outs = rv.resolve(b, R.Field(), acts)
    return sum(o.prob * (1 - o.sides[side][idx]["hp_fraction"]) for o in outs)


@needs_showdown
@pytest.mark.parametrize(
    ("holder", "ability", "ratio"),
    [
        # Fairy Aura on the field, whoever holds it: Fairy moves x 5448/4096
        (("p1", 1), "fairyaura", 5448 / 4096),
        # Friend Guard on the target's ally: x 0.75
        (("p1", 1), "friendguard", 0.75),
        # (Battery, Power Spot and the like on the attacker's ally are passed
        # too, but the calculator's Champions rules do not use them)
    ],
)
def test_auras_and_allies_change_the_damage(tools, holder, ability, ratio):
    """Found by the resolver check: Mega Floette's Fairy Aura (Light of Ruin in
    game 2608046888) was not passed to the calculator."""
    dex, moves, calc = tools
    acts = {
        "p1": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="protect"),
        ),
        "p2": (
            Action(0, "move", move="swordsdance"),
            Action(1, "move", move="moonblast", target=("foe", 0)),
        ),
    }
    plain = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    role, i = holder
    mons = list(SHEETS[role])
    old = mons[i]
    mons[i] = SheetMon(old.position, old.species, old.item, ability, old.moves, "")
    sheets = {**SHEETS, role: tuple(mons)}
    with_it = R.Resolver(dex, moves, calc, sheets, SPREADS)
    got = _mean_lost(with_it, board(), acts) / _mean_lost(plain, board(), acts)
    assert got == pytest.approx(ratio, rel=0.04)


# Found by the resolver check (Week 12, the HP misses): on the 892 games, turns
# where White Herb acted were found 65% of the time, turns where a Contrary
# Pokemon's stats changed 67%, and an ally's hit under the user's own screen
# 64%, against 83% for all turns.

CC = (
    Action(0, "move", move="closecombat", target=("foe", 0)),
    Action(1, "move", move="protect"),
)
P2_QUIET = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))


def _with(sheets, role, i, **kw):
    mons = list(sheets[role])
    old = mons[i]
    mons[i] = SheetMon(
        old.position,
        kw.get("species", old.species),
        kw.get("item", old.item),
        kw.get("ability", old.ability),
        old.moves,
        "",
    )
    return {**sheets, role: tuple(mons)}


@needs_showdown
def test_white_herb_restores_the_stats_close_combat_lowered(tools):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p1", 0, item="whiteherb")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p1"][0]["item"] = "whiteherb"
    outs = rv.resolve(b, R.Field(), {"p1": CC, "p2": P2_QUIET})
    hit = [o for o in outs if o.sides["p2"][0]["hp_fraction"] < 1]
    assert hit
    for o in hit:
        me = o.sides["p1"][0]
        assert me["boosts"] == {}
        assert (me["item"], me["rev_item"]) == ("", "whiteherb")  # used up
    # without it, the drops stay
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    for o in rv.resolve(board(), R.Field(), {"p1": CC, "p2": P2_QUIET}):
        if o.sides["p2"][0]["hp_fraction"] < 1:
            assert o.sides["p1"][0]["boosts"] == {"def": -1, "spd": -1}


@needs_showdown
def test_contrary_turns_each_stat_change_around(tools):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p1", 0, ability="contrary")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    charm = (
        Action(0, "move", move="swordsdance"),
        Action(1, "move", move="charm", target=("foe", 0)),
    )
    for o in rv.resolve(board(), R.Field(), {"p1": CC, "p2": charm}):
        if o.sides["p2"][0]["hp_fraction"] < 1:
            # Close Combat raises; Charm (Attack -2) raises it 2
            assert o.sides["p1"][0]["boosts"] == {"def": 1, "spd": 1, "atk": 2}


@needs_showdown
def test_mega_staraptor_has_contrary(tools):
    """Staraptor-Mega (Reg M-B): Intimidate on its sheet, Contrary once it Mega
    Evolves."""
    dex, moves, calc = tools
    sheets = _with(
        SHEETS, "p1", 0, species="staraptor", item="staraptite", ability="intimidate"
    )
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p1"][0].update(species="staraptor", item="staraptite", mega=True)
    assert rv.ability("p1", 0, b["p1"][0]) == "contrary"
    for o in rv.resolve(b, R.Field(), {"p1": CC, "p2": P2_QUIET}):
        if o.sides["p2"][0]["hp_fraction"] < 1:
            assert o.sides["p1"][0]["boosts"] == {"def": 1, "spd": 1}


@needs_showdown
def test_a_screen_weakens_an_allys_hit_too(tools):
    """Showdown's Reflect: any hit on its side's Pokemon but the user's own."""
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    quake = (
        Action(0, "move", move="earthquake"),
        Action(1, "move", move="swordsdance"),
    )
    acts = {"p1": quake, "p2": P2_QUIET}

    def lost(fld):
        outs = rv.resolve(board(), fld, acts)
        return sum(o.prob * (1 - o.sides["p1"][1]["hp_fraction"]) for o in outs)

    screened = R.Field()
    screened.sides["p1"]["reflect"] = 5
    assert lost(screened) / lost(R.Field()) == pytest.approx(2732 / 4096, rel=0.04)


@needs_showdown
def test_defiant_answers_intimidate_before_white_herb(tools):
    """Intimidate's -1, then Defiant's +2: nothing is left below 0, so the herb
    stays (Showdown checks it after the switch-in)."""
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p1", 1, item="whiteherb")  # Kingambit, Defiant
    inci = SheetMon(3, "incineroar", "", "intimidate", ("fakeout",), "")
    sheets = {**sheets, "p2": (*sheets["p2"], inci)}
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    b = board()
    b["p1"][1]["item"] = "whiteherb"
    b["p2"].append(mon("incineroar"))
    b["p2"][2].update(active=False)
    p2 = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
    quiet = (Action(0, "move", move="swordsdance"), Action(1, "move", move="protect"))
    for o in rv.resolve(b, R.Field(), {"p1": quiet, "p2": p2}):
        assert o.sides["p1"][1]["boosts"] == {"atk": 1}
        assert o.sides["p1"][1]["item"] == "whiteherb"


@needs_showdown
def test_a_tailwind_set_this_turn_speeds_its_side_at_once(tools):
    """Generation 8 on (Showdown's `runAction`): after each action the moves
    still to come are sorted again by priority and Speed as they are now. Found
    by the resolver check: turns where Tailwind was set and moves came after
    it were found 78% of the time, against 83% for all turns."""
    dex, moves, calc = tools
    rv = R.Resolver(dex, moves, calc, SHEETS, SPREADS)
    b = board(0.1)  # Incineroar: one hit from Kingambit knocks it out
    p1 = (
        Action(0, "move", move="tailwind"),
        Action(1, "move", move="kowtowcleave", target=("foe", 0)),
    )
    p2 = (
        Action(0, "move", move="flareblitz", target=("foe", 1)),
        Action(1, "move", move="protect"),
    )
    # at the turn's start: Tailwind, then Incineroar, then Kingambit
    ((order, _p),) = rv.orders(b, R.Field(), {"p1": p1, "p2": p2})
    moves_in_order = [a.move for _r, a in order]
    assert moves_in_order.index("flareblitz") < moves_in_order.index("kowtowcleave")
    outs = rv.resolve(b, R.Field(), {"p1": p1, "p2": p2})
    out = [o for o in outs if o.sides["p2"][0]["fainted"]]
    assert sum(o.prob for o in out) > 0.9
    for o in out:  # Kingambit moved first: no Flare Blitz
        assert o.sides["p1"][1]["hp_fraction"] == 1.0


# The abilities that act by chance (after Week 12's check: Poison Touch 54 and
# 22 turns partly modelled, Cursed Body 21, Flame Body 10): each a branch with
# Showdown's chance (`data/abilities.ts`).

CLAW = (
    Action(0, "move", move="dragonclaw", target=("foe", 0)),
    Action(1, "move", move="protect"),
)


def _status_chances(outs, role, idx):
    got: dict[str, float] = {}
    for o in outs:
        s = o.sides[role][idx]["status"] or "none"
        got[s] = got.get(s, 0.0) + o.prob
    return got


@needs_showdown
@pytest.mark.parametrize(
    ("ability", "status"),
    [("flamebody", "brn"), ("static", "par"), ("poisonpoint", "psn")],
)
def test_a_contact_hit_on_these_abilities_gives_a_status_30_percent(
    tools, ability, status
):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p2", 0, ability=ability)
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    outs = rv.resolve(board(), R.Field(), {"p1": CLAW, "p2": P2_QUIET})
    assert _status_chances(outs, "p1", 0).get(status, 0) == pytest.approx(0.3)
    assert not any(o.partial for o in outs)
    # not without contact
    quake = (Action(0, "move", move="earthquake"), Action(1, "move", move="protect"))
    outs = rv.resolve(board(), R.Field(), {"p1": quake, "p2": P2_QUIET})
    assert _status_chances(outs, "p1", 0) == {"none": pytest.approx(1.0)}


@needs_showdown
def test_poison_touch_poisons_what_it_hits_30_percent(tools):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p1", 0, ability="poisontouch")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    outs = rv.resolve(board(), R.Field(), {"p1": CLAW, "p2": P2_QUIET})
    assert _status_chances(outs, "p2", 0).get("psn", 0) == pytest.approx(0.3)
    assert not any(o.partial for o in outs)
    b = board()  # Covert Cloak keeps it off, as Shield Dust does
    b["p2"][0]["item"] = "covertcloak"
    outs = rv.resolve(b, R.Field(), {"p1": CLAW, "p2": P2_QUIET})
    assert _status_chances(outs, "p2", 0).get("psn", 0) == 0


@needs_showdown
def test_effect_spore_puts_to_sleep_paralyses_or_poisons(tools):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p2", 0, ability="effectspore")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    outs = rv.resolve(board(), R.Field(), {"p1": CLAW, "p2": P2_QUIET})
    got = _status_chances(outs, "p1", 0)
    assert got.get("slp", 0) == pytest.approx(0.11)
    assert got.get("par", 0) == pytest.approx(0.10)
    assert got.get("psn", 0) == pytest.approx(0.09)


@needs_showdown
def test_cursed_body_disables_the_move_that_hit_it_30_percent(tools):
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p2", 0, ability="cursedbody")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    outs = rv.resolve(board(), R.Field(), {"p1": CLAW, "p2": P2_QUIET})
    off = sum(o.prob for o in outs if o.sides["p1"][0].get("disabled") == "dragonclaw")
    assert off == pytest.approx(0.3)
    assert not any(o.partial for o in outs)


@needs_showdown
def test_moody_raises_one_stat_and_lowers_another_at_random(tools):
    """Showdown (Generation 8 on): one stat of five not at +6 rises 2, then
    another not at -6 falls 1, each chosen evenly (25 Reg M-A turns were
    partly modelled for it)."""
    dex, moves, calc = tools
    sheets = _with(SHEETS, "p1", 0, ability="moody")
    rv = R.Resolver(dex, moves, calc, sheets, SPREADS)
    quiet = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
    outs = rv.resolve(board(), R.Field(), {"p1": quiet, "p2": P2_QUIET})
    assert not any(o.partial for o in outs)
    got: dict[tuple, float] = {}
    for o in outs:
        b = o.sides["p1"][0]["boosts"]
        got[tuple(sorted(b.items()))] = got.get(tuple(sorted(b.items())), 0) + o.prob
    assert len(got) == 20
    for key, prob in got.items():
        assert sorted(v for _k, v in key) == [-1, 2]
        assert prob == pytest.approx(1 / 20)
