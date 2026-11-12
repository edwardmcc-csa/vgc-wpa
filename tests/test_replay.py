"""Tests for the replay report (M7, `wpa.replay`): paste a replay, get your
biggest win-probability swings, each split as DEFINITIONS §3 says, with both
baselines of §4 for your choice, what happened, and the best choice when yours
was not.

The analysis itself (`wpa.attribution.analyse_game`) is tested elsewhere; here
it is stood in for by records of the same shape.
"""

from __future__ import annotations

import json

import pytest

from wpa import attribution as A
from wpa import replay as RP
from wpa.choices import Action

TAG = "gen9championsvgc2026regma-2605147085"
URL = "https://replay.pokemonshowdown.com/" + TAG


# --------------------------------------------------------------------------
# Finding the replay
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        URL,
        URL + "?p2",
        URL + ".log",
        URL + ".json",
        URL + "#turn5",
        "replay.pokemonshowdown.com/" + TAG,
        "http://replay.pokemonshowdown.com/" + TAG,
        TAG,
        "  " + URL + "  ",
    ],
)
def test_a_replay_link_gives_the_battle_id(src):
    assert RP.replay_id(src) == TAG


def test_a_private_replays_password_is_kept():
    pid = "gen9championsvgc2026regmabo3-2604921266-q4mk6d2nr63emwdihwxco5c8fi1lnacpw"
    assert RP.replay_id("https://replay.pokemonshowdown.com/" + pid) == pid
    assert RP.download_url(pid) == f"https://replay.pokemonshowdown.com/{pid}.json"


@pytest.mark.parametrize(
    "src", ["https://example.com/hello", "hello", "https://replay.pokemonshowdown.com/"]
)
def test_a_link_that_is_not_a_replay_is_refused(src):
    with pytest.raises(RP.ReplayError):
        RP.replay_id(src)


SHEET1 = (
    "|showteam|p1|Kingambit||BlackGlasses|Defiant|SuckerPunch,IronHead,LowKick,"
    "Protect|||M|||50|]Dragonite||ChoiceBand|Multiscale|ExtremeSpeed,Hurricane,"
    "FirePunch,Protect|||F|||50|]Gholdengo||ChoiceSpecs|GoodasGold|MakeItRain,"
    "ShadowBall,FocusBlast,Trick||||||50|]Sneasler||WhiteHerb|Unburden|FakeOut,"
    "CloseCombat,DireClaw,Protect|||M|||50|]Garchomp||LifeOrb|RoughSkin|Earthquake,"
    "DragonClaw,RockSlide,Protect|||F|||50|]Sinistcha||Leftovers|Hospitality|"
    "MatchaGotcha,RagePowder,TrickRoom,Protect||||||50|"
)
SHEET2 = (
    "|showteam|p2|Basculegion||ChoiceScarf|Adaptability|WaveCrash,LastRespects,"
    "FlipTurn,AquaJet|||M|||50|]Incineroar||SitrusBerry|Intimidate|FakeOut,"
    "FlareBlitz,PartingShot,KnockOff|||M|||50|]Amoonguss||RockyHelmet|Regenerator|"
    "Spore,RagePowder,PollenPuff,Protect|||F|||50|]Archaludon||PowerHerb|Stamina|"
    "ElectroShot,FlashCannon,DracoMeteor,Protect|||M|||50|]Whimsicott||MentalHerb|"
    "Prankster|Tailwind,Encore,Moonblast,Protect|||M|||50|]Floette-Eternal||"
    "Floettite|FlowerVeil|LightofRuin,Moonblast,Protect,DazzlingGleam|||F|||50|"
)

LOG = "\n".join(
    [
        "|j|☆Ann",
        "|j|☆Bob",
        "|gametype|doubles",
        "|player|p1|Ann|1|",
        "|player|p2|Bob B|2|",
        "|gen|9",
        "|tier|[Gen 9 Champions] VGC 2026 Reg M-A",
        "|teampreview|4",
        SHEET1,
        SHEET2,
        "|start",
        "|switch|p1a: Kingambit|Kingambit, L50, M|100/100",
        "|switch|p1b: Nite|Dragonite, L50, F|100/100",
        "|switch|p2a: Basky|Basculegion, L50, M|100/100",
        "|switch|p2b: Incineroar|Incineroar, L50, M|100/100",
        "|turn|1",
        "|",
        "|move|p2b: Incineroar|Fake Out|p1b: Nite",
        "|-damage|p1b: Nite|90/100",
        "|cant|p1b: Nite|flinch",
        "|move|p2a: Basky|Wave Crash|p1a: Kingambit",
        "|-crit|p1a: Kingambit",
        "|-damage|p1a: Kingambit|0 fnt",
        "|faint|p1a: Kingambit",
        "|-damage|p2a: Basky|80/100|[from] Recoil",
        "|",
        "|upkeep",
        "|",
        "|switch|p1a: Gholdengo|Gholdengo, L50|100/100",
        "|turn|2",
        "|",
        "|switch|p2b: Amoonguss|Amoonguss, L50, F|100/100",
        "|cant|p2a: Basky|par",
        "|move|p1a: Gholdengo|Make It Rain|p2a: Basky|[spread] p2a,p2b",
        "|-damage|p2a: Basky|20/100",
        "|-damage|p2b: Amoonguss|70/100",
        "|move|p1b: Nite|Extreme Speed|p2b: Amoonguss",
        "|-activate|p2b: Amoonguss|move: Protect",
        "|",
        "|upkeep",
        "|turn|3",
        "|",
        "|move|p1b: Nite|Hurricane|p2b: Amoonguss|[miss]",
        "|-miss|p1b: Nite|p2b: Amoonguss",
        "|move|p2b: Amoonguss|Pollen Puff|p1a: Gholdengo",
        "|-damage|p1a: Gholdengo|0 fnt",
        "|faint|p1a: Gholdengo",
        "|move|p2a: Basky|Aqua Jet|p1b: Nite",
        "|-damage|p1b: Nite|0 fnt",
        "|faint|p1b: Nite",
        "|",
        "|win|Bob B",
    ]
)


def test_the_player_is_found_by_name_whatever_the_spacing_or_case():
    assert RP.side_of(LOG, "Ann") == "p1"
    assert RP.side_of(LOG, "bobb") == "p2"
    assert RP.side_of(LOG, " BOB B ") == "p2"


def test_a_player_not_in_the_game_says_who_is():
    with pytest.raises(RP.ReplayError, match="Ann.*Bob B"):
        RP.side_of(LOG, "Carl")


def test_a_saved_replay_page_or_its_json_or_its_log_all_read_the_same(tmp_path):
    js = tmp_path / "x.json"
    js.write_text(json.dumps({"id": TAG, "log": LOG}), encoding="utf-8")
    page = tmp_path / "Replay.html"
    page.write_text(
        '<html><body><script type="text/plain" class="battle-log-data">'
        + LOG.replace("</", "<\\/")
        + "</script></body></html>",
        encoding="utf-8",
    )
    raw = tmp_path / f"{TAG}.log"
    raw.write_text(LOG, encoding="utf-8")
    assert RP.load(str(js)) == (TAG, LOG)
    assert RP.load(str(raw)) == (TAG, LOG)
    tag, log = RP.load(str(page))
    assert log == LOG
    # a page saved under another name: the format comes from the log's tier
    assert tag.startswith("gen9championsvgc2026regma-")


def test_a_log_with_no_battle_id_is_given_one_from_its_tier():
    assert RP.tag_from_log(LOG).startswith("gen9championsvgc2026regma-")
    bo3 = LOG.replace("Reg M-A", "Reg M-A (Bo3)")
    assert RP.tag_from_log(bo3).startswith("gen9championsvgc2026regmabo3-")


def test_a_format_the_models_do_not_know_is_refused():
    other = LOG.replace("[Gen 9 Champions] VGC 2026 Reg M-A", "[Gen 9] VGC 2025 Reg I")
    with pytest.raises(RP.ReplayError, match="Reg M-A"):
        RP.format_for(RP.tag_from_log(other), other)


# --------------------------------------------------------------------------
# What happened, from the log
# --------------------------------------------------------------------------


def test_team_preview_shows_the_leads():
    m = RP.moments(LOG)[("preview", 0)]
    assert m.actions["p1"] == ["led Kingambit and Dragonite"]
    assert m.actions["p2"] == ["led Basculegion and Incineroar"]


def test_a_turn_shows_the_moves_with_their_targets_and_what_went_with_them():
    m = RP.moments(LOG)[("turn", 1)]
    assert m.actions["p2"] == [
        "Incineroar Fake Out → Dragonite",
        "Basculegion Wave Crash → Kingambit (critical hit)",
    ]
    assert m.actions["p1"] == []  # Kingambit fell first, Dragonite flinched
    assert m.fainted == {"p1": ["Kingambit"], "p2": []}
    assert ("p2", "Basculegion landed a critical hit") in m.luck
    # Fake Out always makes its target flinch: that is not luck
    assert not any("flinched" in text for _, text in m.luck)


def test_a_flinch_from_a_move_that_only_sometimes_flinches_is_luck():
    log = LOG.replace(
        "|move|p2b: Incineroar|Fake Out|p1b: Nite",
        "|move|p2b: Incineroar|Rock Slide|p1b: Nite|[spread] p1a,p1b",
    )
    m = RP.moments(log)[("turn", 1)]
    assert ("p1", "Dragonite flinched") in m.luck
    assert m.actions["p2"][0] == "Incineroar Rock Slide (both foes)"


def test_switches_spread_moves_protect_and_full_paralysis():
    m = RP.moments(LOG)[("turn", 2)]
    assert m.actions["p2"] == ["Incineroar switched out for Amoonguss"]
    assert m.actions["p1"] == [
        "Gholdengo Make It Rain (both foes)",
        "Dragonite Extreme Speed → Amoonguss (protected)",
    ]
    assert ("p2", "Basculegion was fully paralysed") in m.luck


def test_a_miss_is_luck_and_the_switch_ins_after_a_turn_are_their_own_moment():
    ms = RP.moments(LOG)
    assert ms[("replacement", 1)].actions["p1"] == ["sent in Gholdengo"]
    m = ms[("turn", 3)]
    assert m.actions["p1"] == ["Dragonite Hurricane → Amoonguss (missed)"]
    assert ("p1", "Dragonite's Hurricane missed") in m.luck
    assert m.fainted["p1"] == ["Gholdengo", "Dragonite"]


def test_a_mega_evolution_is_told_with_the_move_after_it():
    log = LOG.replace(
        "|move|p1b: Nite|Hurricane|p2b: Amoonguss|[miss]",
        "|-mega|p1b: Nite|Dragonite|Dragoninite\n"
        "|move|p1b: Nite|Hurricane|p2b: Amoonguss|[miss]",
    )
    m = RP.moments(log)[("turn", 3)]
    assert m.actions["p1"] == ["Dragonite Mega Evolved, Hurricane → Amoonguss (missed)"]


def test_what_happened_is_told_from_the_players_side():
    m = RP.moments(LOG)[("turn", 1)]
    lines = RP.describe(m, "p1")
    assert lines[0].startswith("You: ")
    assert "nothing shown" in lines[0]
    assert lines[1] == (
        "They: Incineroar Fake Out → Dragonite; "
        "Basculegion Wave Crash → Kingambit (critical hit)"
    )
    assert "Fainted: your Kingambit" in lines
    luck = next(x for x in lines if x.startswith("Luck: "))
    assert luck == "Luck: their Basculegion landed a critical hit"
    # and from the other side
    assert RP.describe(m, "p2")[2] == "Fainted: their Kingambit"


# --------------------------------------------------------------------------
# The best choice, named
# --------------------------------------------------------------------------

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
LIKELY = [(R1, 0.5), (R2, 0.5)]


def value(o, t):
    return TABLE[(o, t)]


def test_the_best_of_your_likely_choices_is_found_when_it_beats_yours():
    alts = [[(X, 1.0)], [(Y, 1.0)], [(Z, 1.0)]]
    e_x = A.expected(value, [(X, 1.0)], LIKELY)
    assert A.best_choice(value, alts, LIKELY, e_x) == Y
    e_y = A.expected(value, [(Y, 1.0)], LIKELY)
    assert A.best_choice(value, alts, LIKELY, e_y) is None  # yours was the best


def test_a_choice_survives_the_records_json():
    back = A.joint_from_json(json.loads(json.dumps(A.joint_json(Y))))
    assert back == Y


SHEETS = RP.sheet_names(LOG)
# the format's move data names the moves; without it, the log and the sheets do
NAMES = RP.move_names(LOG, {"lightofruin": {"name": "Light of Ruin"}})


def test_sheets_and_move_names_come_from_the_log():
    assert SHEETS["p1"][:2] == ["Kingambit", "Dragonite"]
    assert SHEETS["p2"][5] == "Floette-Eternal"
    assert NAMES["extremespeed"] == "Extreme Speed"  # from a |move| line
    assert NAMES["matchagotcha"] == "Matcha Gotcha"  # from the sheet only
    assert NAMES["lightofruin"] == "Light of Ruin"  # from the move data


def test_a_turns_choice_is_said_in_words():
    said = RP.say_choice(A.joint_json(Y), "turn", "p1", SHEETS, NAMES)
    assert (
        said
        == "Kingambit Sucker Punch → Basculegion; Dragonite Extreme Speed → Basculegion"
    )
    said = RP.say_choice(A.joint_json(Z), "turn", "p1", SHEETS, NAMES)
    assert said == "Kingambit switch to Gholdengo; Dragonite Protect"
    pivot = (Action(0, "move", move="flipturn", target=("foe", 1), switch_to=2),)
    assert RP.say_choice(A.joint_json(pivot), "turn", "p2", SHEETS, NAMES) == (
        "Basculegion Flip Turn → Dragonite, bringing in Amoonguss"
    )
    ally = (
        Action(5, "move", move="ragepowder"),
        Action(4, "move", move="dragonclaw", target=("ally", 5)),
    )
    assert "Garchomp Dragon Claw → Sinistcha (ally)" in RP.say_choice(
        A.joint_json(ally), "turn", "p1", SHEETS, NAMES
    )
    mega = (Action(5, "move", move="lightofruin", target=("foe", 0), mega=True),)
    assert RP.say_choice(A.joint_json(mega), "turn", "p2", SHEETS, NAMES) == (
        "Floette-Eternal Mega Evolves, Light of Ruin → Kingambit"
    )


def test_leads_and_switch_ins_are_said_in_words():
    assert (
        RP.say_choice(
            A.joint_json(A.lead_joint((4, 1))), "preview", "p1", SHEETS, NAMES
        )
        == "lead Dragonite and Garchomp"
    )
    rep = (Action(0, "switch", switch_to=3),)
    assert (
        RP.say_choice(A.joint_json(rep), "replacement", "p1", SHEETS, NAMES)
        == "send in Sneasler"
    )


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def rec(kind, turn, point, before, after, choice, position, theirs, role="p1", **kw):
    dice = (after - before) - choice - position - theirs
    r = dict(
        tag=TAG,
        format="regma",
        kind=kind,
        turn=turn,
        point=point,
        role=role,
        before=before,
        after=after,
        choice=choice,
        position=position,
        theirs=theirs,
        dice=dice,
        yours=choice + position,
        vs_best=kw.pop("vs_best", 0.0),
        result=0.0,
    )
    r.update(kw)
    return r


RECORDS = [
    rec("preview", 0, 0, 0.50, 0.48, -0.03, 0.01, 0.00),
    rec(
        "turn",
        1,
        1,
        0.48,
        0.20,
        -0.02,
        0.00,
        -0.06,
        vs_best=-0.14,
        best=A.joint_json(Y),
    ),
    rec("replacement", 1, 2, 0.20, 0.22, 0.00, 0.02, 0.00),
    rec("turn", 2, 3, 0.22, 0.30, 0.05, 0.01, 0.00),
    dict(
        rec("turn", 3, 4, 0.30, 0.0, 0, 0, 0),
        skipped="choices not in the log",
        choice=None,
        position=None,
        theirs=None,
        dice=None,
    ),
    # the other player's records are not this player's
    rec("turn", 1, 1, 0.52, 0.80, 0.0, 0.0, 0.0, role="p2"),
]


def test_the_biggest_swings_come_first_and_are_the_players_own():
    got = RP.biggest(RECORDS, "p1", top=3)
    assert [(r["kind"], r["turn"]) for r in got] == [
        ("turn", 3),
        ("turn", 1),
        ("turn", 2),
    ]


def test_each_swing_says_which_part_mostly_made_it():
    r = RECORDS[1]  # dice -0.20
    assert RP.mostly(r) == "the dice"
    assert RP.mostly(RECORDS[3]) == "your choice"
    assert RP.mostly(RECORDS[4]) == "not split (choices not in the log)"


def test_labels():
    assert RP.label(RECORDS[0]) == "Team preview"
    assert RP.label(RECORDS[1]) == "Turn 1"
    assert RP.label(RECORDS[2]) == "After turn 1 (switch-ins)"


def test_the_game_adds_up_from_team_preview_to_the_result():
    t = RP.totals(RECORDS, "p1")
    assert t["start"] == pytest.approx(0.50)
    assert t["end"] == pytest.approx(0.0)
    assert t["choice"] == pytest.approx(-0.03 - 0.02 + 0.05)
    assert t["unsplit"] == pytest.approx(-0.30)
    parts = t["choice"] + t["position"] + t["theirs"] + t["dice"] + t["unsplit"]
    assert parts == pytest.approx(t["end"] - t["start"])


def test_the_costliest_choices_are_against_the_best():
    got = RP.costliest(RECORDS, "p1", top=3)
    assert [(r["kind"], r["turn"]) for r in got] == [("turn", 1)]


def test_the_report_reads_as_the_product_owner_asked():
    text = RP.game_report(TAG, LOG, RECORDS, "p1", top=3)
    assert URL in text
    assert "Ann (you) vs Bob B" in text
    assert "You lost" in text
    # the biggest swing first, with what happened
    first = text.index("1. Turn 3")
    assert first < text.index("2. Turn 1") < text.index("3. Turn 2")
    assert "Dragonite Hurricane → Amoonguss (missed)" in text
    # your choice against both baselines, always together (DEFINITIONS §4)
    assert "-2 against the typical choice, -14 against the best" in text
    assert (
        "Best: Kingambit Sucker Punch → Basculegion; "
        "Dragonite Extreme Speed → Basculegion" in text
    )
    # the whole game's sum
    assert "Over the game" in text
    assert "your choices" in text and "the dice" in text


def test_team_preview_is_always_shown_with_the_best_leads():
    recs = [dict(r) for r in RECORDS]
    recs[0].update(vs_best=-0.06, best=A.joint_json(A.lead_joint((2, 4))))
    text = RP.game_report(TAG, LOG, recs, "p1", top=1)
    assert "Team preview: you led Kingambit and Dragonite." in text
    assert "-3 against the typical choice, -6 against the best" in text
    assert "Best: lead Gholdengo and Garchomp" in text
    # shown even when it is not among the biggest swings
    assert "1. Turn 3" in text and "2. Turn 1" not in text
