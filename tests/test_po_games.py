"""Week 17, Task 3: the PO's games against the bot (17 Nov 2026). Each clear
misplay he named is a test the engine must pass: the full advice (no clock),
from the bot's side (p2), with the four it brought. His name is taken out of
the logs (`fixtures/po_games/`).

Needs the engine's models and the pinned Showdown builds (skipped without
them), and takes about a minute."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GAMES = ROOT / "tests" / "fixtures" / "po_games"

pytestmark = pytest.mark.skipif(
    not (ROOT / "models_v4" / "regmc" / "policy.json").exists()
    or not (ROOT / "models_v4_avg" / "regmc").exists()
    or not (ROOT / "pokemon-showdown-mc" / "dist").exists(),
    reason="needs the engine's Reg M-C models and the pinned Showdown builds",
)


@pytest.fixture(scope="module")
def tools():
    pytest.importorskip("sklearn")  # the models' calibration (not on Python 3.10)
    from wpa import matches as M

    return M._tools()


def _four(log: str, role: str) -> set[int]:
    """The bot's four: those of its sheet that came out."""
    sheet = next(x for x in log.split("\n") if x.startswith(f"|showteam|{role}|"))
    six = [e.split("|")[0] for e in sheet[len(f"|showteam|{role}|") :].split("]")]
    came = {
        x.split("|")[3].split(",")[0]
        for x in log.split("\n")
        if x.startswith((f"|switch|{role}", f"|drag|{role}"))
    }
    return {i for i, n in enumerate(six) if n in came}


def _advice(tools, game: str, turn: int):
    from wpa import advise as AD

    log = (GAMES / f"{game}.log").read_text(encoding="utf-8")
    cut = AD.up_to_turn(log, turn)
    tag = f"gen9championsvgc2026regmc-{game}"
    return AD.advise(tag, cut, "regmc", tools, "p2", _four(log, "p2"))


def test_626_turn_7_archaludon_is_not_locked_into_electro_shot(tools):
    """The 9:34 pm game: Archaludon's Electro Shot had gone off at once in the
    rain on turn 5; the board still had it charging, so the bot played
    Electro Shot and Kingambit's second Protect (the charging bug, d4ab5bf)."""
    adv = _advice(tools, "626", 7)
    best = {a.move for a in adv.choices[0][0]}
    assert not {"electroshot", "protect"} <= best
    shooter = {
        a.user for j, _v, _p in adv.choices for a in j if a.move == "electroshot"
    }
    assert any(
        a.user in shooter and a.move != "electroshot"
        for j, _v, _p in adv.choices
        for a in j
    )


def test_629_turn_15_no_encore_on_a_move_with_no_pp(tools):
    """Game 629: the PO's Archaludon had used its eighth and last Protect, so
    Encore could only fail; Moonblast (for the crits) was the bot's chance."""
    adv = _advice(tools, "629", 15)
    assert all(a.move != "encore" for a in adv.choices[0][0])


@pytest.mark.xfail(
    strict=True,
    reason="the engine now expects the Fake Out (Week 18) but still values "
    "attacking higher: what Sneasler surviving is worth shows only later",
)
def test_626_turn_1_sneasler_protects_against_the_fake_out(tools):
    """The 9:34 pm game, turn 1: the PO's Raichu Fake Outs Sneasler, which
    needed to survive to Close Combat his Archaludon. Protect is the answer.
    Week 17: the engine attacked, not expecting the Fake Out (7% among its
    likeliest replies). Week 18, with the choice model's ridge fixed: it
    expects it (55%), and still attacks (Protect 5th, 4 points behind)."""
    adv = _advice(tools, "626", 1)
    best = adv.choices[0][0]
    sneasler = 0  # the bot's sheet: Sneasler first
    assert any(a.user == sneasler and a.move == "protect" for a in best)
