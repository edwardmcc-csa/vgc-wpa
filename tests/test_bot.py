"""Week 16, Task 1: the engine as a player on the local Showdown server.

The bot reads its own stream of the game (Showdown's messages to that player),
turns it into the log a spectator sees, asks the advice for its best play, and
sends Showdown only a choice taken from Showdown's own request. The fixture
`live_p1.log` is one recorded game on the local Reg M-C server, as player p1
saw it (its requests included)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from wpa import bot as B
from wpa.advise import Pick
from wpa.choices import Action

FIX = Path(__file__).parent / "fixtures" / "w16" / "live_p1.log"
STREAM = FIX.read_text(encoding="utf-8").split("\n")
# the team p1 played in it (as packed; no stat points)
TEAM = (
    "Arcanine-Hisui||FocusSash|RockHead|ExtremeSpeed,FlareBlitz,HeadSmash,Protect|Jolly||F|||50|]"
    "Gholdengo||LifeOrb|GoodasGold|MakeItRain,NastyPlot,Protect,ShadowBall|Timid|||||50|]"
    "Milotic||SitrusBerry|Competitive|Coil,Hypnosis,IceBeam,MuddyWater|Calm||F|||50|]"
    "Raichu||RaichuniteY|LightningRod|FakeOut,FocusBlast,Protect,ZapCannon|Timid||F|||50|]"
    "Rillaboom||MiracleSeed|GrassySurge|FakeOut,GrassyGlide,HighHorsepower,WoodHammer|Adamant||F|||50|]"
    "Staraptor||Staraptite|Intimidate|BraveBird,CloseCombat,Protect,Tailwind|Jolly||M|||50|"
)


def _log(lines) -> str:
    """The bot's log: its stream as a spectator sees it, with its own sheet."""
    from wpa.replay import with_sheets

    return with_sheets(B.live_log(lines, "p1"), "p1", B.paste_from_packed(TEAM))


# --------------------------------------------------------------------------
# The log as a spectator sees it
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mine, public",
    [
        ("162/162", "100/100"),
        ("37/175", "21/100"),  # Champions rounds down
        ("1/175", "1/100"),  # at least 1 while standing
        ("35/175", "20/100r"),  # a colour mark at 20: red at a fifth or under
        ("36/175", "20/100y"),
        ("88/175", "50/100g"),  # and at 50: green over half
        ("87/175", "49/100"),
        ("100/162 par", "61/100 par"),  # the status stays
        ("0 fnt", "0 fnt"),
    ],
)
def test_own_hit_points_are_shown_as_the_other_player_sees_them(mine, public):
    assert B.public_hp(mine) == public


def test_each_line_is_the_one_a_spectator_gets():
    assert (
        B.public_line("|switch|p1a: Gholdengo|Gholdengo, L50|162/162", "p1")
        == "|switch|p1a: Gholdengo|Gholdengo, L50|100/100"
    )
    assert (
        B.public_line("|-damage|p1a: Gholdengo|146/162|[from] item: Life Orb", "p1")
        == "|-damage|p1a: Gholdengo|90/100|[from] item: Life Orb"
    )
    foe = "|-damage|p2a: Sneasler|61/100"
    assert B.public_line(foe, "p1") == foe  # theirs: as Showdown sent it
    assert B.public_line(foe, "p2") == "|-damage|p2a: Sneasler|61/100"
    for private in (
        '|request|{"rqid":2}',
        "RandB2 rejected open team sheets.",
        "|uhtmlchange|otsrequest|",
        "",
    ):
        assert B.public_line(private, "p1") is None


def test_the_live_log_reads_as_a_replay_does():
    from wpa import decisions as D
    from wpa.advise import up_to_turn
    from wpa.durations import load_all

    log = _log(STREAM[:67])  # to turn 2's start
    assert "|request|" not in log and "otsrequest" not in log
    game = D.build_game(up_to_turn(log, 2), load_all(Path("pokemon-showdown"))["regmc"])
    start = [s for s in game.states["p1"] if s["moment"] == "turn_start"][-1]
    hp = {m["species"]: m["hp_fraction"] for m in start["our_pokemon"]}
    assert hp["gholdengo"] == pytest.approx(1.0)
    assert hp["rillaboom"] == 0.0  # fainted on turn 1


# --------------------------------------------------------------------------
# The bot's own team: its sheet, with its stat points, is known to it
# --------------------------------------------------------------------------

PACKED = (
    "Gholdengo||LifeOrb|GoodasGold|MakeItRain,NastyPlot,Protect,ShadowBall|Timid|"
    "2,0,0,32,0,32||||50|]Arcanine-Hisui||FocusSash|RockHead|ExtremeSpeed,"
    "FlareBlitz,HeadSmash,Protect|Jolly|2,32,0,0,0,32|F|||50|"
)


def test_a_packed_team_becomes_a_team_paste_with_its_stat_points():
    from wpa.replay import parse_team

    mons = parse_team(B.paste_from_packed(PACKED))
    assert [m["species"] for m in mons] == ["Gholdengo", "Arcanine-Hisui"]
    assert mons[0]["evs"] == {"hp": 2, "spa": 32, "spe": 32}
    assert mons[0]["nature"] == "Timid" and mons[1]["gender"] == "F"
    assert mons[1]["moves"] == ["ExtremeSpeed", "FlareBlitz", "HeadSmash", "Protect"]


def test_the_players_own_stat_points_are_known_not_guessed():
    from wpa import spreads as S
    from wpa.team_sheets import sheets_from_log

    sheet = "|showteam|p1|" + PACKED
    gh = sheets_from_log(sheet)["p1"][0]
    assert gh.sps == (2, 0, 0, 32, 0, 32)
    usage = {"gholdengo": [S.Spread("timid", (17, 0, 0, 17, 0, 32), 1.0)]}
    assert S.prior(usage, gh, None) == [S.Spread("timid", (2, 0, 0, 32, 0, 32), 1.0)]
    # an open team sheet shows no stat points: believed from usage, as before
    ots = "|showteam|p1|Gholdengo||LifeOrb|GoodasGold|MakeItRain|Timid|||||50|"
    shown = sheets_from_log(ots)["p1"][0]
    assert shown.sps is None
    assert S.prior(usage, shown, None) == usage["gholdengo"]


# --------------------------------------------------------------------------
# What the bot says to Showdown
# --------------------------------------------------------------------------


def test_team_preview_sends_the_four_with_the_leads_first():
    assert B.team_message(Pick((1, 0), (3, 4))) == "/team 2145"


def test_the_engines_name_for_a_live_game():
    assert B.engine_tag("battle-gen9championsvgc2026regmc-12") == (
        "gen9championsvgc2026regmc-12"
    )


def _battle_until(n_requests: int):
    """poke_env's battle as the player had it at its n-th request."""
    pytest.importorskip("poke_env")
    from poke_env.battle import DoubleBattle
    from poke_env.player import Player

    b = DoubleBattle(
        "battle-gen9championsvgc2026regmc-1", "RecA1", logging.getLogger("t"), gen=9
    )
    seen, lines = 0, []
    for x in STREAM:
        lines.append(x)
        p = x.split("|")
        if len(p) < 2:
            continue
        if p[1] == "request":
            r = json.loads(p[2])
            if r.get("teamPreview"):
                for m in r["side"]["pokemon"]:
                    m["active"] = False
            b.parse_request(r)
            seen += 1
            if seen == n_requests:
                return b, lines
        elif p[1] not in Player.MESSAGES_TO_IGNORE:
            b.parse_message(p)
    raise AssertionError("not that many requests")


IDENTS = ["p1: Arcanine", "p1: Gholdengo", "p1: Milotic", "p1: Raichu"]
IDENTS += ["p1: Rillaboom", "p1: Staraptor"]


def test_the_sheet_order_comes_from_the_team_preview_request():
    b, _ = _battle_until(1)
    assert B.sheet_idents(b.last_request) == IDENTS


def test_the_best_play_becomes_showdowns_choice():
    from wpa.durations import load_all

    b, lines = _battle_until(4)  # turn 2's start
    foes = B.foe_targets(_log(lines), "p1", load_all(Path("pokemon-showdown"))["regmc"])
    assert foes == {4: 1, 3: 2}  # Sneasler in place a, Basculegion in b
    best = (
        Action(0, "move", move="headsmash", target=("foe", 3)),
        Action(1, "move", move="makeitrain"),
    )
    order, why = B.order_for(best, b, IDENTS, foes)
    assert why == ""
    # Gholdengo is in place a, Arcanine in b
    assert order.message == "/choose move makeitrain, move headsmash 2"
    ally = (
        Action(1, "move", move="shadowball", target=("ally", 0)),
        Action(0, "switch", switch_to=3),
    )
    order, why = B.order_for(ally, b, IDENTS, foes)
    assert (order.message, why) == ("/choose move shadowball -2, switch Raichu", "")


def test_a_choice_showdown_does_not_offer_is_never_sent():
    from wpa.durations import load_all

    b, lines = _battle_until(4)
    foes = B.foe_targets(_log(lines), "p1", load_all(Path("pokemon-showdown"))["regmc"])
    valid = {o.message for o in B.legal_orders(b)}
    bad = (
        Action(1, "move", move="hypnosis", target=("foe", 4)),  # not its move
        Action(0, "switch", switch_to=4),  # Rillaboom has fainted
    )
    order, why = B.order_for(bad, b, IDENTS, foes)
    assert order.message in valid
    assert "hypnosis" in why and "Rillaboom" in why
    # one place wrong: the other keeps the engine's choice
    half = (
        Action(1, "move", move="makeitrain"),
        Action(0, "move", move="hypnosis", target=("foe", 4)),
    )
    order, why = B.order_for(half, b, IDENTS, foes)
    assert order.message.startswith("/choose move makeitrain, ")
    assert order.message in valid and "hypnosis" in why


def test_a_forced_switch_sends_the_newcomer_and_passes_the_other_place():
    b, _ = _battle_until(3)  # Rillaboom fell in place a on turn 1
    pick = (Action(4, "switch", switch_to=1),)
    order, why = B.order_for(pick, b, IDENTS, {})
    assert (order.message, why) == ("/choose switch Gholdengo, pass", "")


def test_the_last_one_left_for_two_places_is_not_a_replaced_choice():
    """Week 19, Task 4: both places empty and one Pokemon left: the other
    place can only pass, so nothing was chosen at random (13 of the 20
    choices counted as replaced in Week 18's head-to-head)."""
    b, _ = _battle_until(3)
    r = json.loads(json.dumps(b.last_request))
    r["forceSwitch"] = [True, True]
    for m in r["side"]["pokemon"]:
        if m["ident"] in ("p1: Arcanine", "p1: Raichu"):
            m["condition"] = "0 fnt"
    b.parse_request(r)
    order, why = B.order_for((Action(4, "switch", switch_to=1),), b, IDENTS, {})
    assert (order.message, why) == ("/choose switch Gholdengo, pass", "")


def test_a_switching_move_brings_in_the_one_it_planned():
    b, _ = _battle_until(3)  # a switch asked for in place a
    plan = {0: 3}  # place a's move was to bring in Raichu
    assert B.pivot_order(b, plan, IDENTS)[0].message == ("/choose switch Raichu, pass")
    order, why = B.pivot_order(b, {}, IDENTS)  # no plan: still a legal choice
    assert order.message in {o.message for o in B.legal_orders(b)} and why


def test_what_kind_of_choice_a_request_asks_for():
    assert B.decision_kind(B.live_log(STREAM[:66], "p1"), [False, False]) == "turn"
    assert B.decision_kind(B.live_log(STREAM[:62], "p1"), [True, False]) == (
        "replacement"
    )
    mid = B.live_log(STREAM[:52], "p1")  # turn 1, before its end
    assert B.decision_kind(mid, [True, False]) == "pivot"
