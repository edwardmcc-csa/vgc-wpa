"""Tests for what the board knows about each Pokemon's actions (Week 8 Task 3)
and what the log has revealed about it (Task 5).

- `moved`: it has used a move since it last came in (Fake Out works only before);
- `last_move`: its last move since coming in (a Choice item locks it to this);
- `protect_streak`: Protect-type moves in a row that worked (each one after the
  first works a third as often);
- `rev_moves`, `rev_item`, `rev_ability`: what the log has shown of its set, for
  the run with the opponent's sheet blanked.
"""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_board_effects import LEADS, at_turn_start, mon
from tests.test_decisions import HEAD


def game(*blocks):
    return "\n|\n".join([HEAD, LEADS, *blocks, "|win|A"])


T1 = (
    "|t:|1\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-damage|p1a: Whim|90/100\n|cant|p1a: Whim|flinch\n"
    "|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|40/100\n"
    "|-enditem|p2a: Inci|Sitrus Berry|[eat]\n|-heal|p2a: Inci|65/100|[from] item: Sitrus Berry\n"
    "|move|p2b: Fini|Moonblast|p1b: Rock\n|-damage|p1b: Rock|60/100\n"
    "|-damage|p2b: Fini|90/100|[from] item: Rocky Helmet|[of] p1b: Rock"
)
T2 = (
    "|t:|2\n|move|p1b: Rock|Protect|p1b: Rock\n|-singleturn|p1b: Rock|Protect\n"
    "|move|p2a: Inci|Flare Blitz|p1a: Whim\n|-damage|p1a: Whim|30/100"
)
T3_AGAIN = "|t:|3\n|move|p1b: Rock|Protect|p1b: Rock\n|-fail|p1b: Rock"
T3_OTHER = "|t:|3\n|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|20/100"


def log(*turn_blocks):
    blocks = []
    for i, b in enumerate(turn_blocks, start=1):
        blocks += [b, "|upkeep", f"|t:|{i + 1}\n|turn|{i + 1}"]
    return game(*blocks)


def test_a_lead_has_not_moved_and_a_move_is_remembered_until_it_switches():
    s1 = at_turn_start(log(T1), 1)
    assert mon(s1, "their", 0)["moved"] is False  # Fake Out still works
    s2 = at_turn_start(log(T1), 2)
    inci = mon(s2, "their", 0)
    assert inci["moved"] is True and inci["last_move"] == "fakeout"
    assert mon(s2, "our", 0)["moved"] is False  # flinched: no move used
    back = "|t:|2\n|switch|p2a: Rime|Rime, L50|100/100\n|move|p1b: Rock|Rock Slide|p2b: Fini"
    s3 = at_turn_start(log(T1, back), 3)
    assert (
        mon(s3, "their", 0)["moved"] is False and mon(s3, "their", 0)["last_move"] == ""
    )
    assert mon(s3, "their", 2)["moved"] is False  # Rime just came in


def test_protect_in_a_row_counts_up_and_a_failure_or_another_move_resets_it():
    assert mon(at_turn_start(log(T1, T2), 3), "our", 1)["protect_streak"] == 1
    assert mon(at_turn_start(log(T1, T2, T3_AGAIN), 4), "our", 1)["protect_streak"] == 0
    assert mon(at_turn_start(log(T1, T2, T3_OTHER), 4), "our", 1)["protect_streak"] == 0


def test_what_the_log_reveals_of_each_set():
    s = at_turn_start(log(T1), 2)
    inci, fini, rock = mon(s, "their", 0), mon(s, "their", 1), mon(s, "our", 1)
    assert inci["rev_moves"] == ["fakeout"]
    assert inci["rev_item"] == "sitrusberry"  # eaten, so shown
    assert fini["rev_moves"] == ["moonblast"] and fini["rev_item"] == ""
    assert rock["rev_item"] == "rockyhelmet"  # the [of] Pokemon holds it
    assert inci["rev_ability"] == "intimidate"  # from the -ability line at the lead
    assert mon(s, "their", 2)["rev_moves"] == []  # never seen


def test_the_real_data_check_counts_fake_outs_and_choice_locks():
    from tests.test_decisions import EMPTY
    from wpa import decisions as D

    again = "|t:|2\n|move|p2a: Inci|Fake Out|p1a: Whim\n|-fail|p2a: Inci"
    g = D.build_game(log(T1, again), EMPTY)
    assert g.effects["fakeout_available_used"] == 1
    assert g.effects["fakeout_not_available_used"] == 1
    assert g.effects["fakeout_not_available_failed"] == 1


def test_a_choice_item_received_by_trick_locks_from_the_next_move():
    trick = (
        "|t:|2\n|move|p1b: Rock|Rock Slide|p2a: Inci\n"
        "|move|p2b: Fini|Trick|p1b: Rock\n|-item|p1b: Rock|Choice Scarf|[from] move: Trick"
    )
    s = at_turn_start(log(T1, trick), 3)
    assert (
        mon(s, "our", 1)["item"] == "choicescarf"
        and mon(s, "our", 1)["last_move"] == ""
    )
