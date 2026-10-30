"""Tests for stat stages, status and items on the board (Week 7 Task 1).

The damage calculator needs what the board did not track in Week 6: each
Pokemon's stat stages (-6 to +6, reset when it switches out, kept through Mega
Evolution), its status (which stays through switching), and the item it still
holds (from the sheet, gone after it is used up or knocked off, changed by
Trick and similar).
"""

# ruff: noqa: E501

from __future__ import annotations

from tests.test_decisions import EMPTY, HEAD
from wpa import decisions as D

LEADS = """|start
|switch|p1a: Whim|Whim, L50|100/100
|switch|p1b: Rock|Rock, L50|100/100
|switch|p2a: Inci|Inci, L50|100/100
|switch|p2b: Fini|Fini, L50|100/100
|-ability|p2a: Inci|Intimidate|boost
|-unboost|p1a: Whim|atk|1
|-unboost|p1b: Rock|atk|1
|turn|1"""


def game(*blocks):
    return "\n|\n".join([HEAD, LEADS, *blocks, "|win|A"])


def at_turn_start(log, turn, role="p1"):
    g = D.build_game(log, EMPTY)
    (s,) = [
        s
        for s in g.states[role][:-1]
        if s["turn"] == turn and s["moment"] == "turn_start"
    ]
    return s


def mon(state, side, i):
    return state["our_pokemon" if side == "our" else "opp_pokemon"][i]


TURN1 = (
    "|t:|1\n|move|p1a: Whim|Swords Dance|p1a: Whim\n|-boost|p1a: Whim|atk|2\n"
    "|move|p1b: Rock|Rock Slide|p2a: Inci\n|-damage|p2a: Inci|40/100 brn\n"
    "|-enditem|p2a: Inci|Sitrus Berry|[eat]\n|-heal|p2a: Inci|65/100 brn|[from] item: Sitrus Berry\n"
    "|-status|p2b: Fini|par\n|-status|p1a: Whim|psn"
)


def test_intimidate_and_boosts_add_up_and_a_fresh_board_has_none():
    s = at_turn_start(game(TURN1, "|upkeep", "|t:|2\n|turn|2"), 1)
    assert mon(s, "our", 0)["boosts"] == {"atk": -1}
    assert mon(s, "our", 1)["boosts"] == {"atk": -1}
    assert mon(s, "their", 0)["boosts"] == {}
    s = at_turn_start(game(TURN1, "|upkeep", "|t:|2\n|turn|2"), 2)
    assert mon(s, "our", 0)["boosts"] == {"atk": 1}


def test_status_from_status_lines_and_from_hit_point_text():
    s = at_turn_start(game(TURN1, "|upkeep", "|t:|2\n|turn|2"), 2)
    assert mon(s, "their", 0)["status"] == "brn"  # from '40/100 brn'
    assert mon(s, "their", 1)["status"] == "par"
    assert mon(s, "our", 0)["status"] == "psn"
    assert mon(s, "our", 1)["status"] == ""


def test_items_come_from_the_sheet_and_go_when_used_or_knocked_off():
    knock = "|t:|2\n|move|p2a: Inci|Knock Off|p1b: Rock\n|-damage|p1b: Rock|50/100\n|-enditem|p1b: Rock|Leftovers|[from] move: Knock Off|[of] p2a: Inci\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", knock, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "our", 0)["item"] == "focussash"
    assert mon(s, "our", 1)["item"] == ""
    assert mon(s, "their", 0)["item"] == ""  # Sitrus eaten
    assert mon(s, "their", 1)["item"] == "sitrus"


def test_trick_changes_the_item():
    trick = "|t:|2\n|move|p1a: Whim|Trick|p2b: Fini\n|-item|p1a: Whim|Sitrus|[from] move: Trick\n|-item|p2b: Fini|Focus Sash|[from] move: Trick\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", trick, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "our", 0)["item"] == "sitrus"
    assert mon(s, "their", 1)["item"] == "focussash"


def test_switching_out_resets_stages_but_keeps_status():
    out = "|t:|2\n|switch|p1a: Back|Back, L50|100/100\n|turn|2"
    back_in = "|t:|3\n|switch|p1a: Whim|Whim, L50|100/100 psn\n|turn|3"
    log = game(TURN1, "|upkeep", out, "|upkeep", back_in, "|upkeep", "|t:|4\n|turn|4")
    s = at_turn_start(log, 3)
    assert mon(s, "our", 0)["boosts"] == {} and mon(s, "our", 0)["status"] == "psn"
    s = at_turn_start(log, 4)
    assert mon(s, "our", 0)["boosts"] == {}


def test_stages_stay_within_six_and_setboost_sets_them():
    up = "|t:|2\n|-boost|p1a: Whim|atk|6\n|-setboost|p1b: Rock|atk|6\n|-unboost|p2a: Inci|spe|6\n|-unboost|p2a: Inci|spe|2\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", up, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "our", 0)["boosts"] == {"atk": 6}
    assert mon(s, "our", 1)["boosts"] == {"atk": 6}
    assert mon(s, "their", 0)["boosts"] == {"spe": -6}


def test_clearing_inverting_copying_and_swapping_stages():
    setup = "|t:|2\n|-boost|p2a: Inci|def|2\n|-unboost|p2a: Inci|spe|1\n|-boost|p2b: Fini|spa|1\n|turn|2"
    moves = (
        "|t:|3\n|-clearnegativeboost|p1b: Rock|[silent]\n"  # Rock had atk -1
        "|-invertboost|p2a: Inci|[from] move: Topsy-Turvy\n"  # def -2, spe +1
        "|-copyboost|p1a: Whim|p2b: Fini|[from] move: Psych Up\n"  # Whim copies Fini
        "|-swapboost|p2b: Fini|p2a: Inci|atk, spa|[from] move: Power Swap\n|turn|3"
    )
    s = at_turn_start(
        game(TURN1, "|upkeep", setup, "|upkeep", moves, "|upkeep", "|t:|4\n|turn|4"), 4
    )
    assert mon(s, "our", 1)["boosts"] == {}
    assert mon(s, "their", 0)["boosts"] == {"def": -2, "spe": 1, "spa": 1}
    assert mon(s, "their", 1)["boosts"] == {}
    assert mon(s, "our", 0)["boosts"] == {"spa": 1}
    haze = "|t:|4\n|-clearallboost\n|-clearboost|p1a: Whim\n|turn|4"
    log = game(TURN1, "|upkeep", setup, "|upkeep", haze, "|upkeep", "|t:|5\n|turn|5")
    s = at_turn_start(log, 5)
    assert all(m["boosts"] == {} for m in s["our_pokemon"] + s["opp_pokemon"])


def test_curing_one_pokemon_or_the_whole_team():
    cure = "|t:|2\n|-curestatus|p2b: Fini|par|[msg]\n|-cureteam|p1a: Whim|[from] move: Aromatherapy\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", cure, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "their", 1)["status"] == "" and mon(s, "their", 0)["status"] == "brn"
    assert mon(s, "our", 0)["status"] == ""


def test_fainting_clears_stages_and_status_and_mega_keeps_stages():
    faint = "|t:|2\n|-mega|p1a: Whim|Whim|Whimite\n|-damage|p1b: Rock|0 fnt\n|faint|p1b: Rock\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", faint, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "our", 0)["boosts"] == {"atk": 1} and mon(s, "our", 0)["mega"]
    assert mon(s, "our", 1)["boosts"] == {} and mon(s, "our", 1)["status"] == ""


def test_the_real_data_check_counts_intimidates_that_did_not_lower_everyone():
    g = D.build_game(game(TURN1, "|upkeep", "|t:|2\n|turn|2"), EMPTY)
    assert g.effects["intimidate_all_lowered"] == 1
    leads = LEADS.replace(
        "|-unboost|p1b: Rock|atk|1",
        "|-fail|p1b: Rock|unboost|Attack|[from] item: Clear Amulet",
    )
    log = "\n|\n".join([HEAD, leads, TURN1, "|win|A"])
    e = D.build_game(log, EMPTY).effects
    assert e["intimidate_not_all_lowered"] == 1
    assert e["  because [from] item: Clear Amulet"] == 1
    assert e["-boost"] == 1 and e["-unboost"] == 1 and e["stage_outside_6"] == 0


def test_baton_pass_hands_the_stages_to_the_pokemon_coming_in():
    bp = "|t:|2\n|move|p1a: Whim|Baton Pass|p1a: Whim\n|\n|t:|2\n|switch|p1a: Back|Back, L50|100/100|[from] Baton Pass\n|turn|2"
    s = at_turn_start(game(TURN1, "|upkeep", bp, "|upkeep", "|t:|3\n|turn|3"), 3)
    assert mon(s, "our", 2)["boosts"] == {"atk": 1} and mon(s, "our", 2)["active"]
    assert mon(s, "our", 0)["boosts"] == {}
