"""Week 17, Task 2: shortcuts in the move list (the PO's request of 17 Nov).

Plays that cannot work are taken out of the bot's search, for both sides: Fake
Out or First Impression after a Pokemon's first turn out. Plays that rarely
make sense but sometimes do are valued last, never removed (the PO, 20 Nov:
Tailwind while its own is up, and a weather move in that weather, to play
around a switch-in or an opposing weather setter, are among them): a damaging
move into one's own partner (Sneasler's White Herb Close Combat for Unburden,
U-turn out of Perish Song), and a status move into a target that already has
one (into a Sucker Punch user; Yawn into a sleeping or drowsy target, which
makes the Pokemon switched in there drowsy). Each rule can be turned off and
is counted."""

from __future__ import annotations

from collections import Counter

import pytest

from wpa import shortcuts as S
from wpa.choices import Action

MOVES = {
    "fakeout": {"category": "Physical", "priority": 3},
    "firstimpression": {"category": "Physical", "priority": 2},
    "tailwind": {"category": "Status", "sideCondition": "tailwind"},
    "raindance": {"category": "Status", "weather": "RainDance"},
    "sunnyday": {"category": "Status", "weather": "sunnyday"},
    "chillyreception": {"category": "Status", "weather": "snowscape"},
    "closecombat": {"category": "Physical"},
    "uturn": {"category": "Physical"},
    "pollenpuff": {"category": "Special"},
    "thunderwave": {"category": "Status", "status": "par"},
    "yawn": {"category": "Status", "volatileStatus": "yawn"},
    "helpinghand": {"category": "Status"},
    "protect": {"category": "Status"},
}


def _mon(**kw):
    return {"active": True, "fainted": False, "moved": False, "status": "", **kw}


def _move(move, target=None, user=0):
    return Action(user, "move", move=move, target=target)


@pytest.mark.parametrize("move", ["fakeout", "firstimpression"])
def test_fake_out_and_first_impression_work_only_on_the_first_turn_out(move):
    ours = [_mon(moved=True), _mon()]
    a = _move(move, ("foe", 0))
    assert S.cannot_work(a, ours, set(), None, MOVES) == "first_turn_only"
    b = _move(move, ("foe", 0), user=1)
    assert S.cannot_work(b, ours, set(), None, MOVES) is None


def test_tailwind_while_its_own_is_up_is_valued_last_not_removed():
    """The PO, 20 Nov: kept possible (by Showdown's rules a second Tailwind
    fails unless the opponent's Court Change moves the first one away)."""
    ours = [_mon()]
    a = _move("tailwind")
    assert S.cannot_work(a, ours, {"tailwind"}, None, MOVES) is None
    assert S.value_last(a, [], MOVES, our_side={"tailwind"})
    assert not S.value_last(a, [], MOVES, our_side=set())


def test_a_weather_move_in_that_weather_is_valued_last_not_removed():
    """The PO, 20 Nov: a switch-in's weather ability, or a faster weather move,
    can change the weather before it goes off, so it stays possible."""
    ours = [_mon()]
    rain = _move("raindance")
    assert S.cannot_work(rain, ours, set(), "raindance", MOVES) is None
    assert S.value_last(rain, [], MOVES, weather="raindance")
    assert not S.value_last(_move("sunnyday"), [], MOVES, weather="raindance")
    assert S.value_last(_move("sunnyday"), [], MOVES, weather="primordialsea")
    # Chilly Reception also switches the user out: an ordinary play
    assert not S.value_last(_move("chillyreception"), [], MOVES, weather="snow")


def test_a_switch_is_never_removed():
    ours = [_mon(moved=True)]
    a = Action(0, "switch", switch_to=3)
    assert S.cannot_work(a, ours, set(), None, MOVES) is None


def test_attacks_into_ones_own_partner_are_valued_last_but_kept():
    theirs = [_mon(), _mon()]
    assert S.value_last(_move("closecombat", ("ally", 1)), theirs, MOVES)
    assert S.value_last(_move("uturn", ("ally", 1)), theirs, MOVES)
    assert not S.value_last(_move("closecombat", ("foe", 0)), theirs, MOVES)
    # Pollen Puff heals a partner; Helping Hand is for one
    assert not S.value_last(_move("pollenpuff", ("ally", 1)), theirs, MOVES)
    assert not S.value_last(_move("helpinghand", ("ally", 1)), theirs, MOVES)


def test_status_into_a_target_that_already_has_one_is_valued_last():
    theirs = [_mon(status="slp"), _mon(drowsy=1), _mon()]
    assert S.value_last(_move("thunderwave", ("foe", 0)), theirs, MOVES)
    assert not S.value_last(_move("thunderwave", ("foe", 2)), theirs, MOVES)
    # Yawn into a sleeping or drowsy target: kept, for a switch-in there
    assert S.value_last(_move("yawn", ("foe", 0)), theirs, MOVES)
    assert S.value_last(_move("yawn", ("foe", 1)), theirs, MOVES)
    assert not S.value_last(_move("yawn", ("foe", 2)), theirs, MOVES)
    assert not S.value_last(_move("protect"), theirs, MOVES)


def test_a_play_is_valued_last_if_either_pokemon_s_action_is():
    theirs = [_mon(status="par"), _mon()]
    j = (_move("closecombat", ("foe", 1)), _move("thunderwave", ("foe", 0), user=1))
    assert S.last_play(j, theirs, MOVES)
    j = (_move("closecombat", ("foe", 1)), _move("thunderwave", ("foe", 1), user=1))
    assert not S.last_play(j, theirs, MOVES)


def test_the_filter_removes_counts_and_can_be_turned_off():
    ours = [_mon(moved=True), _mon()]
    opts = [
        _move("fakeout", ("foe", 0)),
        _move("closecombat", ("foe", 0)),
        Action(0, "switch", switch_to=2),
    ]
    fired: Counter = Counter()
    kept = S.keep(opts, ours, set(), None, MOVES, fired)
    assert kept == [False, True, True]
    assert fired == Counter({"first_turn_only": 1})
    assert S.keep(opts, ours, set(), None, MOVES, fired, rules=()) == [True] * 3
    # never all of a Pokemon's options: if every one is ruled out, all stay
    only = [_move("fakeout", ("foe", 0))]
    assert S.keep(only, ours, set(), None, MOVES, Counter()) == [True]


def test_the_bots_search_leaves_out_a_fake_out_that_cannot_work():
    """The options as the bot's search sees them (`turn_options` with the
    shortcuts on); without them, unchanged (the replay report and the training
    tables keep every play, since players do make them)."""
    from tests.test_board_actions import T1, log
    from tests.test_policy import DEX
    from tests.test_policy import MOVES as PMOVES
    from wpa import choices as C
    from wpa import policy_data as PD
    from wpa.team_sheets import sheets_from_log

    lg = log(T1)
    sheets = sheets_from_log(lg)
    t = next(x for x in C.turns(lg, DEX) if x.turn == 2 and x.role == "p2")
    args = (t, None, sheets, {}, DEX, PMOVES, {}, None, {})
    every = PD.turn_options(*args)
    fired: Counter = Counter()
    cut = PD.turn_options(*args, shortcuts=fired)
    assert any(a.move == "fakeout" for a in every[0][0])  # Inci moved on turn 1
    assert not any(a.move == "fakeout" for a in cut[0][0])
    assert len(cut[0][1]) == len(cut[0][0])  # each option keeps its facts
    assert fired["first_turn_only"] == sum(a.move == "fakeout" for a in every[0][0])
    assert PD.turn_options(*args, shortcuts=Counter(), rules=()).keys() == every.keys()


def test_plays_valued_last_are_searched_last_whatever_their_odds():
    from tests.test_bot_clock import Counting, _j, _mix, _value, _y
    from wpa import advise as AD

    full = _mix(30, _j)
    replies = _mix(12, _y, seed=2)
    likeliest = max(full, key=lambda x: x[1])[0]
    c = Counting(limit=1)
    got = AD.rank_within(_value, full, replies, c.prepare, c.stop, last={likeliest})
    asked = list(dict.fromkeys(j for batch in c.pairs for j, _y2 in batch))
    assert likeliest not in asked  # left for last
    assert got.ranked[-1][0] == likeliest  # not valued: at the end, still listed


def test_the_bot_keeps_only_the_late_fake_out_removal_by_default():
    """The PO, 22 Nov, after the head-to-head (93 of 200, 40% to 53%): keep
    the removal of plays that cannot work; the order that values some plays
    last is off unless asked for (`--value-last`)."""
    import inspect

    from wpa import advise as AD
    from wpa import matches as M
    from wpa.bot import EngineBot

    bot = inspect.signature(EngineBot.__init__).parameters
    assert bot["shortcuts"].default is True
    assert bot["value_last"].default is False
    assert inspect.signature(AD.advise).parameters["value_last"].default is False
    assert M.parser().parse_args(["--vs", "random"]).value_last is False
    assert M.parser().parse_args(["--vs", "random", "--value-last"]).value_last
