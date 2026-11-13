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
