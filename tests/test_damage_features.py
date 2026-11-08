"""Tests for the damage features, group G, and real Speed (Week 7 Task 4).

With a damage context (the calculator and each Pokemon's most likely spread at
the decision), group G gives, for each side: the best damage an active Pokemon
can do to an opposing active one (as a share of its current hit points), how
much of the opposing board that adds up to, how many opposing actives it can
knock out this turn or in two hits, the best spread move's total, and the same
threat from the Pokemon not yet seen. Speed (group F) becomes the calculator's
final Speed for the spread, stage, status, item, Tailwind and field.
"""

# ruff: noqa: E501

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from wpa import damage as DM
from wpa import features as F
from wpa.spreads import Spread
from wpa.team_sheets import SheetMon, load_dexes
from wpa.timer_join import JoinedTimers

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    shutil.which("node") is None
    or not (ROOT / "calc" / "node_modules" / "@smogon" / "calc").exists()
    or not (ROOT / "pokemon-showdown" / "dist").exists(),
    reason="needs node, `npm ci --prefix calc` and the built Showdown data",
)


@pytest.fixture(scope="module")
def dex():
    return load_dexes(ROOT / "pokemon-showdown")["regma"]


@pytest.fixture(scope="module")
def calc():
    c = DM.Calc()
    yield c
    c.close()


def mon(pos, species, item, ability, moves):
    return SheetMon(pos, species, item, ability, tuple(moves), "")


SHEETS = {
    "p1": (
        mon(
            1,
            "kingambit",
            "blackglasses",
            "defiant",
            ["kowtowcleave", "suckerpunch", "ironhead", "protect"],
        ),
        mon(
            2,
            "garchomp",
            "",
            "roughskin",
            ["earthquake", "dragonclaw", "rockslide", "protect"],
        ),
        mon(
            3,
            "incineroar",
            "sitrusberry",
            "intimidate",
            ["fakeout", "flareblitz", "partingshot", "protect"],
        ),
        mon(
            4,
            "whimsicott",
            "focussash",
            "prankster",
            ["tailwind", "moonblast", "encore", "protect"],
        ),
        mon(
            5,
            "sneasler",
            "whiteherb",
            "unburden",
            ["closecombat", "direclaw", "fakeout", "protect"],
        ),
        mon(
            6,
            "pelipper",
            "",
            "drizzle",
            ["hurricane", "weatherball", "tailwind", "protect"],
        ),
    ),
    "p2": (
        mon(
            1,
            "floetteeternal",
            "",
            "flowerveil",
            ["moonblast", "lightofruin", "dazzlinggleam", "protect"],
        ),
        mon(
            2,
            "corviknight",
            "",
            "pressure",
            ["bravebird", "bodypress", "tailwind", "roost"],
        ),
        mon(
            3,
            "charizard",
            "charizarditey",
            "blaze",
            ["heatwave", "solarbeam", "weatherball", "protect"],
        ),
        mon(
            4,
            "basculegion",
            "choicescarf",
            "adaptability",
            ["wavecrash", "lastrespects", "aquajet", "flipturn"],
        ),
        mon(
            5,
            "sinistcha",
            "",
            "hospitality",
            ["matchagotcha", "ragepowder", "trickroom", "protect"],
        ),
        mon(
            6,
            "rotomwash",
            "",
            "levitate",
            ["hydropump", "voltswitch", "willowisp", "protect"],
        ),
    ),
}


def pk(species, hp, active=False, fainted=False, **kw):
    return {
        "species": species,
        "hp_fraction": hp,
        "active": active,
        "fainted": fainted,
        "mega": False,
        "boosts": kw.get("boosts", {}),
        "status": kw.get("status", ""),
        "item": kw.get("item", ""),
    }


def state(their_hp=(1.0, 1.0), our_boosts=None):
    our = [pk(m.species, 0.0, item=m.item) for m in SHEETS["p1"]]
    their = [pk(m.species, 0.0, item=m.item) for m in SHEETS["p2"]]
    our[0] = pk("kingambit", 1.0, True, item="blackglasses", boosts=our_boosts or {})
    our[1] = pk("garchomp", 1.0, True)
    their[0] = pk("floetteeternal", their_hp[0], True)
    their[1] = pk("corviknight", their_hp[1], True)
    return {
        "turn": 3,
        "decision_index": 0,
        "game_index": None,
        "set_score_entering_game": None,
        "observations": [],
        "our_pokemon": our,
        "opp_pokemon": their,
    }


def spreads():
    out = {}
    for role in ("p1", "p2"):
        for i, _ in enumerate(SHEETS[role]):
            out[(role, i)] = Spread("serious", (32, 32, 0, 0, 0, 2), 1.0)
    out[("p1", 1)] = Spread("jolly", (2, 32, 0, 0, 0, 32), 1.0)
    return out


def g(calc, dex, s=None, joined=None, groups="G"):
    ctx = F.DamageContext(calc, spreads())
    return F.state_features(
        [s or state()],
        0,
        "p1",
        joined or JoinedTimers(moment="turn_start"),
        SHEETS,
        dex,
        None,
        groups,
        ctx,
    )


def test_damage_columns_exist_and_mirror():
    cols = F.columns("G")
    assert "g_our_best_dmg" in cols and "g_their_unseen_ko_n" in cols
    perm = F.mirror_permutation(cols)
    assert cols[perm[cols.index("g_our_ko_n")]] == "g_their_ko_n"


def test_without_a_context_the_columns_are_zero(dex):
    row = F.state_features(
        [state()], 0, "p1", JoinedTimers(moment="turn_start"), SHEETS, dex, None, "G"
    )
    assert set(row.values()) == {0.0}


def test_damage_against_the_opposing_actives(calc, dex):
    row = g(calc, dex)
    assert 0 < row["g_our_best_dmg"] <= 1.0
    assert row["g_their_best_dmg"] > 0
    # a target at 5% falls to anything: one more knock-out this turn
    low = g(calc, dex, state(their_hp=(0.05, 1.0)))
    assert low["g_our_ko_n"] >= 1 and low["g_our_ko_n"] >= row["g_our_ko_n"]
    assert low["g_our_dmg_board"] >= row["g_our_dmg_board"]


def test_stages_and_screens_change_the_damage(calc, dex):
    base = g(calc, dex)["g_our_best_dmg"]
    hurt = g(calc, dex, state(their_hp=(1.0, 1.0)))["g_our_best_dmg"]
    assert hurt == base
    down = g(calc, dex, state(our_boosts={"atk": -2}))
    assert down["g_our_best_dmg"] <= base
    screens = JoinedTimers(
        theirs=(("reflect", "side", 3, 3), ("lightscreen", "side", 3, 3)),
        moment="turn_start",
    )
    assert g(calc, dex, joined=screens)["g_our_best_dmg"] < base


def test_the_threat_still_to_come(calc, dex):
    row = g(calc, dex)
    assert row["g_their_unseen_best"] > 0 and row["g_our_unseen_best"] > 0


def test_real_speed_comes_from_the_spread(calc, dex):
    row = g(calc, dex, groups="F")
    # Garchomp Jolly with 32 Speed points: (102 + 32 + 20) x 1.1
    assert row["f_our_active_speed_max"] == 169
    tw = JoinedTimers(ours=(("tailwind", "side", 2, 2),), moment="turn_start")
    assert g(calc, dex, joined=tw, groups="F")["f_our_active_speed_max"] == 338


def test_damage_features_read_only_public_fields(calc, dex):
    from tests.test_features import GuardedMon, GuardedState

    class Mon(GuardedMon):
        # hits taken (Rage Fist, Week 10) is public: both players see every hit
        ALLOWED = GuardedMon.ALLOWED | {
            "mega",
            "boosts",
            "status",
            "item",
            "last_move",
            "hits",
        }

    s = state()
    s = dict(
        s,
        our_pokemon=[Mon(p) for p in s["our_pokemon"]],
        opp_pokemon=[Mon(p) for p in s["opp_pokemon"]],
    )
    ctx = F.DamageContext(calc, spreads())
    F.state_features(
        [GuardedState(s)],
        0,
        "p1",
        JoinedTimers(moment="turn_start"),
        SHEETS,
        dex,
        None,
        "FG",
        ctx,
    )


# --------------------------------------------------------------------------
# Building rows with damage: the spreads at each decision
# --------------------------------------------------------------------------

LOGS = None


def _logs():
    import json

    global LOGS
    if LOGS is None:
        LOGS = json.loads(
            (ROOT / "tests" / "fixtures" / "w5" / "logs" / "logs.json").read_text(
                encoding="utf-8"
            )
        )
    return LOGS


def test_the_spreads_at_a_decision_never_depend_on_what_comes_after(
    calc, dex, tmp_path
):
    from wpa.decisions import build_game
    from wpa.durations import Durations
    from wpa.spreads import UsageStore
    from wpa.team_sheets import sheets_from_log

    empty = Durations("e", timed={})
    store = UsageStore(tmp_path)  # no statistics: every Pokemon on its default
    tag = max(_logs(), key=lambda k: len(_logs()[k]))
    log = _logs()[tag]
    full = build_game(log, empty)
    ctx_full = F.damage_contexts(tag, log, full, sheets_from_log(log), dex, calc, store)
    blocks = log.split("\n|\n")
    cut_at = len(blocks) // 2
    short_log = "\n|\n".join(blocks[:cut_at])
    short = build_game(short_log, empty)
    ctx_short = F.damage_contexts(
        tag, short_log, short, sheets_from_log(short_log), dex, calc, store
    )
    checked = 0
    for role in ("p1", "p2"):
        for k, point in enumerate(full.points[role]):
            if point < cut_at and k < len(ctx_short[role]):
                assert ctx_full[role][k].spreads == ctx_short[role][k].spreads
                checked += 1
    assert checked > 5


def test_rows_built_from_logs_carry_damage(calc, dex, tmp_path):
    import gzip
    import json

    from wpa.durations import Durations

    tag = sorted(_logs())[0]
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    with gzip.open(logs_dir / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"tag": tag, "log": _logs()[tag]}) + "\n")
    out = tmp_path / "out"
    counts = F.build_shard_from_logs(
        0,
        1,
        logs_dir=logs_dir,
        splits={tag: "train"},
        dexes={"regma": dex, "regmb": dex},
        tables={"regma": Durations("e", timed={}), "regmb": Durations("e", timed={})},
        out_dir=out,
        groups="FG",
        usage_dir=tmp_path / "usage",
    )
    t = F.read_rows(next(out.rglob("*.npz")))
    assert counts["rows"] == len(t.y) > 0
    assert (t.X[:, t.columns.index("g_our_best_dmg")] > 0).any()
    assert (t.X[:, t.columns.index("g_their_best_dmg")] > 0).any()


def test_a_training_sample_keeps_the_same_units_as_the_trainer():
    import numpy as np

    from wpa.evaluate import sample_units

    units = np.array([f"set-{i}" for i in range(400)])
    want = sample_units(units, 0.2)
    got = np.array([F.keep_unit(u, 0.2) for u in units])
    assert (want == got).all() and 40 < got.sum() < 120


def test_processed_usage_statistics_are_cached_on_disk(tmp_path):
    import json

    from wpa.spreads import UsageStore

    data = {
        "data": {
            "Garchomp": {
                "Raw count": 10,
                "Spreads": {"Jolly:0/32/0/0/2/32": 8.0, "Adamant:32/32/0/0/2/0": 2.0},
            }
        }
    }
    (tmp_path / "2026-05-gen9championsvgc2026regma-1500.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    log = "|t:|1778000000\n"
    first = UsageStore(tmp_path).for_game("gen9championsvgc2026regma-1", log)
    assert list(tmp_path.glob("*.cache.pkl"))
    (tmp_path / "2026-05-gen9championsvgc2026regma-1500.json").write_text(
        "not json", encoding="utf-8"
    )
    import os
    import time

    os.utime(
        tmp_path / "2026-05-gen9championsvgc2026regma-1500.json",
        (time.time() - 100, time.time() - 100),
    )
    again = UsageStore(tmp_path).for_game("gen9championsvgc2026regma-1", log)
    assert again == first and "garchomp" in first


def test_the_training_sample_is_taken_from_reg_ma_only_and_formats_can_be_picked(
    tmp_path, dex
):
    import gzip
    import json

    from wpa.durations import Durations

    tag = sorted(_logs())[0]  # a Reg M-A game
    mb_tag = tag.replace("regma", "regmb")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    with gzip.open(logs_dir / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        for t in (tag, mb_tag):
            f.write(json.dumps({"tag": t, "log": _logs()[tag]}) + "\n")
    common = dict(
        logs_dir=logs_dir,
        splits={tag: "train", mb_tag: "train"},
        dexes={"regma": dex, "regmb": dex},
        tables={"regma": Durations("e", timed={}), "regmb": Durations("e", timed={})},
        groups="A",
    )
    # a sample of almost nothing leaves Reg M-B's training games whole
    c = F.build_shard_from_logs(
        0, 1, out_dir=tmp_path / "a", train_sample=1e-9, **common
    )
    assert c["games"] == 1 and c["left_out"] == 1
    assert list((tmp_path / "a" / "regmb" / "train").glob("*.npz"))
    c = F.build_shard_from_logs(
        0, 1, out_dir=tmp_path / "b", formats=("regmb",), **common
    )
    assert c["games"] == 1 and not (tmp_path / "b" / "regma").exists()


def test_the_calculation_count_is_per_shard_not_running(calc, dex, tmp_path):
    import gzip
    import json

    from wpa.durations import Durations

    tag = sorted(_logs())[1]
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    with gzip.open(logs_dir / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"tag": tag, "log": _logs()[tag]}) + "\n")
    common = dict(
        logs_dir=logs_dir,
        splits={tag: "train"},
        dexes={"regma": dex, "regmb": dex},
        tables={"regma": Durations("e", timed={}), "regmb": Durations("e", timed={})},
        groups="FG",
        usage_dir=tmp_path / "usage",
    )
    first = F.build_shard_from_logs(0, 1, out_dir=tmp_path / "a", **common)
    again = F.build_shard_from_logs(0, 1, out_dir=tmp_path / "b", **common)
    assert first["calculations"] > 0
    assert again["calculations"] == 0  # every answer already in the worker's cache


# --------------------------------------------------------------------------
# Week 8: Choice lock in G, the likely back (I), the whole board (J)
# --------------------------------------------------------------------------


def g8(calc, dex, s=None, odds=None, groups="GIJ", joined=None):
    ctx = F.DamageContext(calc, spreads(), odds)
    return F.state_features(
        [s or state()],
        0,
        "p1",
        joined or JoinedTimers(moment="turn_start"),
        SHEETS,
        dex,
        None,
        groups,
        ctx,
    )


def solo_kingambit(**kw):
    s = state()
    s["our_pokemon"][1] = pk("garchomp", 1.0, False)  # on the bench
    s["our_pokemon"][0] = pk(
        "kingambit", 1.0, True, item=kw.get("item", "blackglasses")
    )
    s["our_pokemon"][0]["last_move"] = kw.get("last_move", "")
    return s


def test_a_choice_locked_pokemon_only_has_its_locked_move(calc, dex):
    free = g8(calc, dex, solo_kingambit(item="choicescarf"), groups="G")[
        "g_our_best_dmg"
    ]
    locked = g8(
        calc,
        dex,
        solo_kingambit(item="choicescarf", last_move="suckerpunch"),
        groups="G",
    )["g_our_best_dmg"]
    assert locked < free
    not_choice = g8(
        calc,
        dex,
        solo_kingambit(item="blackglasses", last_move="suckerpunch"),
        groups="G",
    )["g_our_best_dmg"]
    assert not_choice > locked


def test_the_likely_back_follows_the_bring_odds(calc, dex):
    even = g8(calc, dex, groups="I")
    bascu = g8(calc, dex, odds={"p2": [1, 1, 0.01, 50, 0.01, 0.01]}, groups="I")
    sinis = g8(calc, dex, odds={"p2": [1, 1, 0.01, 0.01, 50, 0.01]}, groups="I")
    assert bascu["i_their_back_entropy"] < even["i_their_back_entropy"]
    assert bascu["i_their_back_dmg_exp"] > sinis["i_their_back_dmg_exp"]
    assert even["i_their_back_speed_exp"] > 0 and even["i_our_back_dmg_exp"] > 0


def test_the_whole_board_counts_knock_outs_and_who_moves_first(calc, dex):
    full = g8(calc, dex, groups="J")
    low = g8(calc, dex, state(their_hp=(0.05, 0.05)), groups="J")
    assert low["j_our_ko_targets_exp"] > full["j_our_ko_targets_exp"]
    assert low["j_our_ko_targets_exp"] >= 2 - 1e-9  # both of theirs at 5%
    assert low["j_our_outko_pairs_exp"] >= low["j_our_outko_targets_exp"] - 1e-9
    assert full["j_their_ko_targets_exp"] >= 0


def test_groups_i_and_j_are_zero_without_a_context(dex):
    row = F.state_features(
        [state()], 0, "p1", JoinedTimers(moment="turn_start"), SHEETS, dex, None, "IJ"
    )
    assert set(row.values()) == {0.0}


def test_a_sets_second_game_starts_from_the_firsts_spreads_and_four(
    calc, dex, tmp_path
):
    from tests.test_sets import bo3_log
    from wpa.bring import BringModel, brought_from_log
    from wpa.decisions import build_game
    from wpa.durations import Durations
    from wpa.spreads import UsageStore
    from wpa.team_sheets import sheets_from_log

    tag = max(_logs(), key=lambda k: len(_logs()[k]))
    body = _logs()[tag]
    g1, g2 = bo3_log("setx", 1, body), bo3_log("setx", 2, body)
    t1, t2 = "gen9championsvgc2026regmabo3-91", "gen9championsvgc2026regmabo3-92"
    # odds: only "brought last game" counts
    bring = BringModel(rates={}, coef=[0, 0, 3.0, 0, 0, 0, 0, 0, 0], intercept=0.0)
    store = UsageStore(tmp_path)
    memory: dict = {}
    empty = Durations("e", timed={})
    stats: dict = {}
    first = F.damage_contexts(
        t1,
        g1,
        build_game(g1, empty),
        sheets_from_log(g1),
        dex,
        calc,
        store,
        bring,
        memory,
        stats,
    )
    second = F.damage_contexts(
        t2,
        g2,
        build_game(g2, empty),
        sheets_from_log(g2),
        dex,
        calc,
        store,
        bring,
        memory,
        stats,
    )
    # game 2 starts where game 1 ended: each Pokemon's most likely spread after
    # all of game 1, as kept in the set's memory
    from wpa.bring import players

    sheets = sheets_from_log(g2)
    for role, name in players(g2).items():
        kept = memory[("setx", name)]["spreads"]
        for i, mon in enumerate(sheets[role]):
            if mon.species in kept:
                best = max(kept[mon.species], key=lambda c: c.weight)
                assert (
                    second["p1"][0].spreads[(role, i)].nature,
                    second["p1"][0].spreads[(role, i)].sps,
                ) == (best.nature, best.sps)
    assert first["p1"][0].odds["p1"] == [1.0] * 6  # nothing known before game 1
    got = brought_from_log(body)["p1"]
    odds2 = second["p1"][0].odds["p1"]
    assert all(odds2[i] > 1.0 for i in got) and all(
        odds2[i] == 1.0 for i in range(6) if i not in got
    )
    assert (
        stats["carried"] > 0 and stats["entropy_carried"] <= stats["entropy_start"]
    )  # no statistics here: one candidate each


def test_a_blank_sheet_build_runs_and_knows_less(calc, dex, tmp_path):
    import gzip
    import json

    from wpa.durations import Durations

    tag = sorted(_logs())[0]
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    with gzip.open(logs_dir / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"tag": tag, "log": _logs()[tag]}) + "\n")
    common = dict(
        logs_dir=logs_dir,
        splits={tag: "validation"},
        dexes={"regma": dex, "regmb": dex},
        tables={"regma": Durations("e", timed={}), "regmb": Durations("e", timed={})},
        groups="EFG",
        usage_dir=tmp_path / "usage",
    )
    F.build_shard_from_logs(0, 1, out_dir=tmp_path / "full", **common)
    F.build_shard_from_logs(0, 1, out_dir=tmp_path / "blank", blank=True, **common)
    full = F.read_rows(next((tmp_path / "full").rglob("*.npz")))
    blank = F.read_rows(next((tmp_path / "blank").rglob("*.npz")))
    assert len(full.y) == len(blank.y) > 0
    pos = [full.columns.index(f"e_their_unseen_pos{k}") for k in range(1, 7)]
    assert full.X[:, pos].sum() > 0  # positions are public at team preview
    assert (full.X[:, pos] == blank.X[:, pos]).all()
    their = [i for i, c in enumerate(full.columns) if c.startswith("g_their")]
    assert blank.X[:, their].sum() < full.X[:, their].sum()  # fewer moves known
    F.build_shard_from_logs(0, 1, out_dir=tmp_path / "both", blank_both=True, **common)
    both = F.read_rows(next((tmp_path / "both").rglob("*.npz")))
    ours = [i for i, c in enumerate(full.columns) if c.startswith("g_our")]
    assert len(both.y) == len(full.y)
    assert both.X[:, ours].sum() < blank.X[:, ours].sum()  # our moves hidden too
