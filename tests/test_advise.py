"""Live advice, the first step: at a turn's start, your likely choices ranked by
your win chance against the opponent's likely replies, valued as the analysis
values them (DEFINITIONS §3, §4 and §7). It reads a game so far (a log that
ends at a turn's start), or a finished game at a turn you name, as if the turn
had not been played."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from tests.test_replay import LOG, TAG
from wpa import advise as AD
from wpa import replay as RP
from wpa.choices import Action

X = (Action(0, "move", move="protect"), Action(1, "move", move="protect"))
Y = (
    Action(0, "move", move="suckerpunch", target=("foe", 0)),
    Action(1, "move", move="extremespeed", target=("foe", 0)),
)
Z = (Action(0, "switch", switch_to=2), Action(1, "move", move="protect"))
R1 = (Action(0, "move", move="wavecrash", target=("foe", 0)),)
R2 = (Action(0, "move", move="aquajet", target=("foe", 1)),)
TABLE = {
    (X, R1): 0.50,
    (X, R2): 0.40,
    (Y, R1): 0.75,
    (Y, R2): 0.70,
    (Z, R1): 0.30,
    (Z, R2): 0.45,
}


def value(o, t):
    return TABLE[(o, t)]


def test_a_game_so_far_ends_at_a_turns_start():
    log = AD.up_to_turn(LOG, 2)
    lines = log.split("\n")
    assert "|turn|2" in lines and "|turn|3" not in lines
    assert "Make It Rain" not in log  # turn 2's moves are not in it
    assert log.endswith("|turn|2\n|\n")  # so the turn's start is a decision point
    # a log that already ends at a turn's start is taken as it is
    assert AD.up_to_turn(log, None) == log
    assert AD.up_to_turn(log.removesuffix("\n|\n"), None) == log


def test_a_turn_the_game_never_reached_or_a_finished_game_is_refused():
    with pytest.raises(RP.ReplayError, match="turn 9"):
        AD.up_to_turn(LOG, 9)
    with pytest.raises(RP.ReplayError, match="--turn"):
        AD.up_to_turn(LOG, None)  # it ended: which turn?


def test_your_choices_are_ranked_by_your_chance_against_their_replies():
    replies = [(R1, 0.5), (R2, 0.5)]
    got = AD.rank(value, [(X, 0.6), (Y, 0.3), (Z, 0.1)], replies)
    assert [j for j, _v, _p in got] == [Y, X, Z]
    assert got[0][1] == pytest.approx(0.725)
    assert got[0][2] == pytest.approx(0.3)  # how often players choose it


def test_the_advice_reads_in_words():
    adv = AD.Advice(
        tag=TAG,
        turn=2,
        role="p1",
        wp=0.58,
        choices=[(Y, 0.73, 0.3), (X, 0.45, 0.6)],
        replies=[(R1, 0.6), (R2, 0.4)],
        kept=0.9,
        hidden=False,
        typical=0.62,
    )
    text = AD.advice_text(adv, LOG)
    assert "Turn 2. Your win chance now: 58%;" in text
    # against the typical choice, as DEFINITIONS §3 measures your choice: the
    # turn played out moves everyone's chance (the position), whatever you choose
    assert "after a typical choice: 62%" in text
    first = next(x for x in text.splitlines() if x.strip().startswith("1."))
    assert "Kingambit Sucker Punch → Basculegion" in first
    assert "73% (+11 against a typical choice)" in first
    assert "players choose it 30%" in first
    assert "Basculegion Wave Crash → Kingambit" in text  # their likeliest reply
    assert "60%" in text
    assert RP.HIDDEN_NOTE not in text
    hidden = AD.advice_text(
        AD.Advice(TAG, 2, "p1", 0.58, adv.choices, adv.replies, 0.9, True, 0.62), LOG
    )
    assert RP.HIDDEN_NOTE.split(":")[0] in hidden


ROOT = Path(__file__).resolve().parent.parent
NEEDS = [
    ROOT / "pokemon-showdown" / "dist",
    ROOT / "calc" / "node_modules",
    ROOT / "usage_stats",
    ROOT / "models_v4" / "policy.json",
]


@pytest.mark.skipif(
    not all(p.exists() for p in NEEDS) or not os.environ.get("WPA_SLOW"),
    reason="about a minute; needs the pinned Showdown build, the calculator, the "
    "usage statistics and the opponent model (set WPA_SLOW=1)",
)
@pytest.mark.parametrize("hidden", [False, True])
def test_advice_at_a_turn_of_a_real_game(monkeypatch, hidden):
    import argparse
    import json

    from wpa import attribution as A

    def model(models, fmt, groups):
        return lambda X: 1 / (1 + np.exp(-np.asarray(X, float).mean(axis=1) / 50))

    monkeypatch.setattr(A, "wp_model", model)
    moves = ROOT / "build"
    a = argparse.Namespace(
        dex_tables=None,
        showdown=ROOT / "pokemon-showdown",
        moves_dir=moves if (moves / "moves_regma.json").exists() else None,
        usage=ROOT / "usage_stats",
        bring=ROOT / "models_v4" / "bring.json",
        policy=ROOT / "models_v4" / "policy.json",
        models=None,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        hidden_sets=hidden,
        public_models=None,
    )
    tools = A._tools(a)
    tag = "gen9championsvgc2026regma-2599935271"
    path = ROOT / "tests" / "fixtures" / "replays" / f"{tag}.json"
    log = AD.up_to_turn(json.loads(path.read_text(encoding="utf-8"))["log"], 3)
    adv = AD.advise(tag, log, "regma", tools, "p2")
    assert adv.turn == 3 and adv.role == "p2" and adv.hidden == hidden
    assert 0 < adv.wp < 1
    assert 3 <= len(adv.choices) <= 10
    vals = [v for _j, v, _p in adv.choices]
    assert vals == sorted(vals, reverse=True)
    assert 0 < adv.typical < 1  # your likely choices on average
    assert sum(p for _j, p in adv.replies) == pytest.approx(1.0)
    assert "Your win chance now" in AD.advice_text(adv, log)


# --------------------------------------------------------------------------
# Team preview: which two to lead, from your team paste and their six species
# --------------------------------------------------------------------------

from tests.test_replay_hidden import TEAM  # noqa: E402

THEIRS = [
    "Basculegion",
    "Incineroar",
    "Amoonguss",
    "Archaludon",
    "Whimsicott",
    "Floette-Eternal",
]


def test_team_preview_from_your_paste_and_their_six_species():
    from wpa.team_sheets import sheets_from_log

    tag, log = AD.preview_log(TEAM, THEIRS, "regma", now=1781792080)
    assert RP.format_for(tag, log) == "regma"
    sheets = sheets_from_log(log)
    assert [m.species for m in sheets["p1"]][:2] == ["gholdengo", "dragonite"]
    assert sheets["p1"][1].item == "choiceband"
    assert [m.species for m in sheets["p2"]] == [
        "basculegion",
        "incineroar",
        "amoonguss",
        "archaludon",
        "whimsicott",
        "floetteeternal",
    ]
    assert sheets["p2"][0].moves == ()  # only the species: their sheet is hidden
    lines = log.split("\n")
    assert (
        lines.index("|teampreview|4") < lines.index("|start") < lines.index("|turn|1")
    )
    assert log.endswith("|turn|1\n|\n")  # turn 1's start, the leads' board
    assert RP.players(log) == {"p1": "You", "p2": "Opponent"}


def test_six_species_are_needed():
    with pytest.raises(RP.ReplayError, match="six"):
        AD.preview_log(TEAM, THEIRS[:5], "regma")


def test_lead_advice_reads_in_words():
    from wpa.attribution import lead_joint

    adv = AD.Advice(
        tag=TAG,
        turn=0,
        role="p1",
        wp=0.5,
        choices=[(lead_joint((0, 1)), 0.56, 0.2), (lead_joint((2, 3)), 0.49, 0.1)],
        replies=[(lead_joint((0, 1)), 0.4)],
        kept=1.0,
        hidden=True,
        typical=0.52,
    )
    text = AD.advice_text(adv, LOG)
    assert "Team preview. Your win chance now: 50%; after typical leads: 52%." in text
    first = next(x for x in text.splitlines() if x.strip().startswith("1."))
    assert "lead Kingambit and Dragonite: 56% (+4 against typical leads)" in first
    assert "players lead them 20%" in first
    assert "lead Basculegion and Incineroar: 40%" in text  # their likeliest leads


@pytest.mark.skipif(
    not all(p.exists() for p in NEEDS) or not os.environ.get("WPA_SLOW"),
    reason="about a minute (set WPA_SLOW=1)",
)
def test_lead_advice_from_team_preview_alone(monkeypatch):
    import argparse

    from wpa import attribution as A

    def model(models, fmt, groups):
        return lambda X: 1 / (1 + np.exp(-np.asarray(X, float).mean(axis=1) / 50))

    monkeypatch.setattr(A, "wp_model", model)
    moves = ROOT / "build"
    a = argparse.Namespace(
        dex_tables=None,
        showdown=ROOT / "pokemon-showdown",
        moves_dir=moves if (moves / "moves_regma.json").exists() else None,
        usage=ROOT / "usage_stats",
        bring=ROOT / "models_v4" / "bring.json",
        policy=ROOT / "models_v4" / "policy.json",
        models=None,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        hidden_sets=True,
        public_models=None,
        leads=ROOT / "models_v4" / "leads.json",
    )
    tools = A._tools(a)
    tag, log = AD.preview_log(TEAM, THEIRS, "regma", now=1781792080)
    adv = AD.advise_preview(tag, log, "regma", tools, "p1")
    assert adv.turn == 0 and adv.hidden
    assert len(adv.choices) == 15  # every pair of six
    vals = [v for _j, v, _p in adv.choices]
    assert vals == sorted(vals, reverse=True)
    assert sum(p for _j, _v, p in adv.choices) == pytest.approx(1.0)
    assert sum(q for _j, q in adv.replies) == pytest.approx(1.0)
    assert "Team preview" in AD.advice_text(adv, log)


# --------------------------------------------------------------------------
# Team preview as the app asks it: pick four, the first two you pick lead
# --------------------------------------------------------------------------


def test_the_back_two_are_the_two_players_bring_most_with_those_leads():
    # the bring model's odds: Sneasler (3) and Sinistcha (5) brought most
    odds = [0.5, 0.5, 0.6, 0.9, 0.2, 0.8]
    assert AD.usual_back(odds, (0, 1)) == (3, 5)
    assert AD.usual_back(odds, (3, 5)) == (0, 2)  # a tie: the earlier position


def test_pick_advice_keeps_the_leads_ranking_and_adds_the_usual_back(monkeypatch):
    """The model's value of a back two did not predict results (Week 12: 892
    validation games), so the leads are ranked and the back two are the usual."""
    from types import SimpleNamespace as NS

    from wpa.attribution import lead_joint

    leads = AD.Advice(
        TAG,
        0,
        "p1",
        0.5,
        [(lead_joint((0, 1)), 0.56, 0.2), (lead_joint((3, 5)), 0.49, 0.1)],
        [(lead_joint((0, 1)), 0.4)],
        1.0,
        True,
        0.52,
        "preview",
    )
    monkeypatch.setattr(AD, "advise_preview", lambda *a, **k: leads)
    odds = [0.5, 0.5, 0.6, 0.9, 0.2, 0.8]
    tools = NS(bring=NS(odds=lambda fmt, species, prev: odds))
    adv = AD.advise_bring(TAG, LOG, "regma", tools, "p1")
    assert adv.kind == "bring" and adv.typical == 0.52
    assert [c for c, _v, _p in adv.choices] == [
        AD.Pick((0, 1), (3, 5)),
        AD.Pick((3, 5), (0, 2)),
    ]
    assert [(v, p) for _c, v, p in adv.choices] == [(0.56, 0.2), (0.49, 0.1)]
    assert adv.replies == leads.replies


def test_the_pick_reads_in_words():
    from wpa.attribution import lead_joint

    adv = AD.Advice(
        tag=TAG,
        turn=0,
        role="p1",
        wp=0.5,
        choices=[
            (AD.Pick((0, 1), (2, 3)), 0.56, 0.2),
            (AD.Pick((2, 4), (0, 5)), 0.49, 0.05),
        ],
        replies=[(lead_joint((0, 1)), 0.4)],
        kept=1.0,
        hidden=True,
        typical=0.52,
        kind="bring",
    )
    text = AD.advice_text(adv, LOG)
    assert "Team preview. Your win chance now: 50%; after typical leads: 52%." in text
    assert "the first two you pick lead" in text
    assert "the two players most often bring with those leads" in text
    first = next(x for x in text.splitlines() if x.strip().startswith("1."))
    assert (
        "pick Kingambit and Dragonite (they lead), then Gholdengo and Sneasler: "
        "56% (+4 against typical leads)" in first
    )
    assert "players lead them 20%" in first
    assert "lead Basculegion and Incineroar: 40%" in text  # their likeliest leads


@pytest.mark.skipif(
    not all(p.exists() for p in NEEDS) or not os.environ.get("WPA_SLOW"),
    reason="about a minute (set WPA_SLOW=1)",
)
def test_pick_advice_from_team_preview_alone(monkeypatch):
    import argparse

    from wpa import attribution as A

    def model(models, fmt, groups):
        return lambda X: 1 / (1 + np.exp(-np.asarray(X, float).mean(axis=1) / 50))

    monkeypatch.setattr(A, "wp_model", model)
    moves = ROOT / "build"
    a = argparse.Namespace(
        dex_tables=None,
        showdown=ROOT / "pokemon-showdown",
        moves_dir=moves if (moves / "moves_regma.json").exists() else None,
        usage=ROOT / "usage_stats",
        bring=ROOT / "models_v4" / "bring.json",
        policy=ROOT / "models_v4" / "policy.json",
        models=None,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        hidden_sets=True,
        public_models=None,
        leads=ROOT / "models_v4" / "leads.json",
    )
    tools = A._tools(a)
    tag, log = AD.preview_log(TEAM, THEIRS, "regma", now=1781792080)
    adv = AD.advise_bring(tag, log, "regma", tools, "p1")
    assert adv.kind == "bring" and adv.hidden
    assert len(adv.choices) == 15  # every pair of leads, with its usual back two
    for c, _v, _p in adv.choices:
        assert len(set(c.leads + c.back)) == 4
    vals = [v for _j, v, _p in adv.choices]
    assert vals == sorted(vals, reverse=True)
    assert sum(p for _j, _v, p in adv.choices) == pytest.approx(1.0)
    assert sum(q for _j, q in adv.replies) == pytest.approx(1.0)
    assert "(they lead)" in AD.advice_text(adv, log)
    # from the app: their six as typed, the names the format's statistics know
    six = ["Incineroar", "Sneasler", "Floette", "Garchomp", "Kingambit", "Basculegion"]
    assert "(they lead)" in AD.pick_advice(TEAM, six, "regma", tools)


def test_their_species_as_you_type_them():
    from tests.test_hidden import DEX

    known = {"incineroar", "floetteeternal", "floettemega", "rillaboom"}
    assert AD.species_name("incineroar", DEX, known) == "Incineroar"
    # the app's name for a form the format allows only one way
    assert AD.species_name("Floette", DEX, known) == "Floette-Eternal"
    with pytest.raises(RP.ReplayError, match="Pikachuu"):
        AD.species_name("Pikachuu", DEX, known)
    with pytest.raises(RP.ReplayError, match="did you mean Rillaboom"):
        AD.species_name("Rilaboom", DEX, known)


# --------------------------------------------------------------------------
# A forced switch: which Pokemon to send in after a knock-out
# --------------------------------------------------------------------------


def test_a_game_so_far_ends_at_a_forced_switch():
    log = AD.up_to_switch(LOG, 1)  # Kingambit fell in turn 1
    assert log.endswith("|upkeep\n|\n")
    assert "|switch|p1a: Gholdengo" not in log  # the choice not yet made
    with pytest.raises(RP.ReplayError, match="turn 2"):
        AD.up_to_switch(LOG, 2)  # nothing fell at the end of turn 2


def test_switch_advice_reads_in_words():
    sw = (Action(0, "switch", switch_to=2),)
    alt = (Action(0, "switch", switch_to=4),)
    adv = AD.Advice(
        tag=TAG,
        turn=1,
        role="p1",
        wp=0.4,
        choices=[(sw, 0.45, 0.7), (alt, 0.38, 0.3)],
        replies=[((), 1.0)],
        kept=1.0,
        hidden=False,
        typical=0.43,
        kind="replacement",
    )
    text = AD.advice_text(adv, LOG)
    assert "After turn 1: a forced switch. Your win chance now: 40%" in text
    first = next(x for x in text.splitlines() if x.strip().startswith("1."))
    assert "send in Gholdengo: 45% (+2 against a typical choice)" in first
    assert "They have no forced switch." in text


@pytest.mark.skipif(
    not all(p.exists() for p in NEEDS) or not os.environ.get("WPA_SLOW"),
    reason="about a minute (set WPA_SLOW=1)",
)
@pytest.mark.parametrize("hidden", [False, True])
def test_switch_advice_after_a_knock_out(monkeypatch, hidden):
    import argparse
    import json

    from wpa import attribution as A

    def model(models, fmt, groups):
        return lambda X: 1 / (1 + np.exp(-np.asarray(X, float).mean(axis=1) / 50))

    monkeypatch.setattr(A, "wp_model", model)
    moves = ROOT / "build"
    a = argparse.Namespace(
        dex_tables=None,
        showdown=ROOT / "pokemon-showdown",
        moves_dir=moves if (moves / "moves_regma.json").exists() else None,
        usage=ROOT / "usage_stats",
        bring=ROOT / "models_v4" / "bring.json",
        policy=ROOT / "models_v4" / "policy.json",
        models=None,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        hidden_sets=hidden,
        public_models=None,
        replace=ROOT / "models_v4" / "replace.json",
    )
    tools = A._tools(a)
    tag = "gen9championsvgc2026regma-2599935271"
    path = ROOT / "tests" / "fixtures" / "replays" / f"{tag}.json"
    # p1's Skarmory fell in turn 4; the bench: Liepard, Dragapult, Incineroar,
    # Milotic (p1 sent in Milotic)
    log = AD.up_to_switch(json.loads(path.read_text(encoding="utf-8"))["log"], 4)
    adv = AD.advise_replacement(tag, log, "regma", tools, "p1")
    assert adv.kind == "replacement" and adv.turn == 4
    ins = sorted(j[0].switch_to or 0 for j, _v, _p in adv.choices)
    assert ins == [1, 2, 3, 4]
    assert all(j[0].user == 5 for j, _v, _p in adv.choices)
    vals = [v for _j, v, _p in adv.choices]
    assert vals == sorted(vals, reverse=True)
    assert adv.replies == [((), 1.0)]  # p2 had no forced switch
    assert "send in" in AD.advice_text(adv, log)


def test_a_session_answers_each_team_preview_until_you_stop():
    """Loading takes about 20 seconds, a team preview's advice about 1, so a
    session loads once and answers each game's team preview as it comes."""
    asked = iter(
        [
            "Incineroar, Sneasler, Floette, Garchomp, Kingambit, Basculegion",
            "Incineroar, Sneasler",  # five short: said, and the session goes on
            "",
            "q",
            "never read",
        ]
    )
    said: list[str] = []

    def answer(theirs):
        if len(theirs) != 6:
            raise RP.ReplayError("give their six species, as team preview shows them")
        return "advice for " + " / ".join(theirs)

    AD.run_session(lambda: next(asked), answer, said.append)
    text = "\n".join(said)
    assert "advice for Incineroar / Sneasler / Floette" in text
    assert "Sorry: give their six species" in text
    assert "never read" not in text
    # the end of the input ends it too
    said.clear()
    AD.run_session(lambda: next(iter(())), answer, said.append)
