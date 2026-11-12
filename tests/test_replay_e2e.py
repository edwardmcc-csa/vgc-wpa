"""The replay report end to end (M7's test in the engineering plan): five
validation games from the corpus, saved as replays (`fixtures/replays/`),
through the same analysis `python -m wpa.replay` runs, with each player's three
biggest swings as recorded.

The swings themselves are the WP model's (before and after each decision
point), so a change to the resolver or the opponent model leaves them; a new WP
model may move them, and then they are recorded again on purpose.

It runs the models on five games (about ten minutes), so it runs only when
asked: `WPA_SLOW=1`. With `WPA_RECORD=1` as well, it records what it finds.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from wpa import replay as RP

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "replays"
EXPECTED = FIX / "expected.json"

slow = pytest.mark.skipif(
    os.environ.get("WPA_SLOW") != "1" or not (ROOT / "models_v4").exists(),
    reason="slow (the models on five games): set WPA_SLOW=1",
)


@pytest.fixture(scope="module")
def analysed(tmp_path_factory):
    games = []
    for p in sorted(FIX.glob("gen9*.json")):
        tag, log = RP.load(str(p))
        games.append((tag, log, RP.format_for(tag, log)))
    a = argparse.Namespace(
        out=tmp_path_factory.mktemp("replays"),
        fresh=True,
        workers=1,
        models=None,
        moves_dir=None,
        dex_tables=None,
    )
    recs = RP.analyse(games, a)
    return [(tag, log, r) for (tag, log, _f), r in zip(games, recs)]


def test_there_are_five_games_in_both_formats():
    tags = [p.stem for p in FIX.glob("gen9*.json")]
    assert len(tags) == 5
    assert {RP.format_for(t, "") for t in tags} == {"regma", "regmb"}


@slow
def test_each_players_three_biggest_swings_are_as_recorded(analysed):
    got = {
        tag: {
            role: [[r["kind"], r["turn"]] for r in RP.biggest(recs, role, 3)]
            for role in ("p1", "p2")
        }
        for tag, _log, recs in analysed
    }
    if os.environ.get("WPA_RECORD") == "1":
        EXPECTED.write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    assert got == json.loads(EXPECTED.read_text(encoding="utf-8"))


@slow
def test_every_split_adds_up_and_each_game_chains_to_its_result(analysed):
    for _tag, _log, recs in analysed:
        for role in ("p1", "p2"):
            t = RP.totals(recs, role)
            assert abs(t["gap"]) < 1e-3  # every decision point is covered
            assert t["end"] in (0.0, 1.0)  # the last one ends at the result
        for r in recs:
            if r.get("skipped") or r.get("choice") is None:
                continue
            parts = r["choice"] + r["position"] + r["theirs"] + r["dice"]
            assert abs(parts - (r["after"] - r["before"])) < 1e-3


@slow
def test_every_choice_shown_has_both_baselines(analysed):
    for tag, log, recs in analysed:
        for role in ("p1", "p2"):
            text = RP.game_report(tag, log, recs, role, top=10)
            lines = [x for x in text.splitlines() if "against the typical choice" in x]
            assert lines
            assert all("against the best" in x for x in lines)
