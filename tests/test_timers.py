"""Tests for wpa/timers.py (Week 4 Task 7): replaying battle logs against the
duration table of wpa/durations.py.

The logs here are small hand-written protocol snippets. The table is built by
hand too, so none of these tests need Node or the Showdown submodule.
"""

# ruff: noqa: E501  (battle-log fixture lines are long by nature)

from __future__ import annotations

import json

from wpa import timers as T
from wpa.durations import (
    ACTION,
    AFTER_RESIDUAL,
    Adjustment,
    Durations,
    Modifier,
    SourceRef,
    TimedEffect,
)

REF = SourceRef("x.ts", 1)


def eff(id, attach, base, mods=(), adj=(), rnd=None, name=None):
    return TimedEffect(
        "Moves",
        id,
        name or id,
        attach,
        base,
        tuple(mods),
        tuple(adj),
        rnd,
        "duration",
        REF,
    )


def mod(kind, name, duration):
    return Modifier(kind, name, duration, "", REF)


TABLE = Durations(
    "test",
    timed={
        "tailwind": eff(
            "tailwind", "sideCondition", 4, [mod("ability", "persistent", 6)]
        ),
        "lightscreen": eff(
            "lightscreen", "sideCondition", 5, [mod("item", "lightclay", 8)]
        ),
        "trickroom": eff(
            "trickroom", "pseudoWeather", 5, [mod("ability", "persistent", 7)]
        ),
        "raindance": eff("raindance", "weather", 5, [mod("item", "damprock", 8)]),
        "sunnyday": eff("sunnyday", "weather", 5, [mod("item", "heatrock", 8)]),
        "encore": eff(
            "encore",
            "volatileStatus",
            3,
            adj=[Adjustment("condition.onStart", 1, "", REF)],
        ),
        "taunt": eff(
            "taunt",
            "volatileStatus",
            3,
            adj=[Adjustment("condition.onStart", 1, "", REF)],
        ),
        "disable": eff(
            "disable",
            "volatileStatus",
            5,
            adj=[Adjustment("condition.onStart", -1, "", REF)],
        ),
        "healblock": eff(
            "healblock", "volatileStatus", 5, [mod("trigger", "Psychic Noise", 2)]
        ),
        "auroraveil": eff(
            "auroraveil", "sideCondition", 5, [mod("item", "lightclay", 8)]
        ),
        "partiallytrapped": eff(
            "partiallytrapped",
            "volatileStatus",
            5,
            [mod("item", "gripclaw", 8)],
            rnd=(5, 7),
        ),
    },
)


def team(side, *mons):
    """|showteam| line: each mon is (name, item, ability)."""
    packed = "]".join(f"{n}||{i}|{a}|Protect|Timid||||50|" for n, i, a in mons)
    return f"|showteam|{side}|{packed}"


def head(
    p1=(("Whim", "FocusSash", "Prankster"),), p2=(("Inci", "Sitrus", "Intimidate"),)
):
    return "\n".join(
        [
            "|player|p1|A|1|",
            "|player|p2|B|2|",
            team("p1", *p1),
            team("p2", *p2),
            "|start",
            f"|switch|p1a: {p1[0][0]}|{p1[0][0]}, L50|100/100",
            f"|switch|p2a: {p2[0][0]}|{p2[0][0]}, L50|100/100",
        ]
    )


def turns(**by_turn):
    """by_turn: t1="...lines...", t2="..." -> '|turn|1\\n...\\n|upkeep' blocks."""
    out = []
    for key, body in by_turn.items():
        n = int(key[1:])
        out.append(f"|turn|{n}")
        if body:
            out.append(body)
        out.append("|upkeep")
    return "\n".join(out)


def tailwind_log(end_in=4):
    blocks = {f"t{n}": "" for n in range(1, 6)}
    blocks["t1"] = (
        "|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind"
    )
    blocks[f"t{end_in}"] = "|-sideend|p1: A|move: Tailwind"
    return head() + "\n" + turns(**blocks)


def one(log, id=None, table=TABLE):
    game = T.track_game(log, table)
    found = [t for t in game.timers if id is None or t.id == id]
    assert len(found) == 1, found
    return found[0]


# --------------------------------------------------------------------------
# Start, expected end, and what happened
# --------------------------------------------------------------------------


def test_tailwind_started_by_a_move_ends_where_the_table_says():
    t = one(tailwind_log(end_in=4))
    assert (t.id, t.kind, t.target) == ("tailwind", "sideCondition", "p1")
    assert (t.start_turn, t.start_phase, t.duration) == (1, ACTION, 4)
    assert t.expected_end == 4
    assert (t.end_turn, t.end_reason) == (4, "ended")
    assert T.classify(t) == "match"


def test_ending_early_without_a_cause_is_unexplained_and_late_too():
    assert T.classify(one(tailwind_log(end_in=3))) == "unexplained"
    assert T.classify(one(tailwind_log(end_in=5))) == "unexplained"


def test_removal_by_a_named_move_is_explained():
    log = tailwind_log(end_in=3).replace(
        "|-sideend|p1: A|move: Tailwind",
        "|-sideend|p1: A|move: Tailwind|[from] move: Defog|[of] p2a: Inci",
    )
    t = one(log)
    assert (t.end_reason, t.end_detail) == ("removed", "move: Defog")
    assert T.classify(t) == "explained"


def test_an_effect_with_no_end_event_is_censored_not_a_mismatch():
    log = tailwind_log(end_in=4).replace("|-sideend|p1: A|move: Tailwind\n", "")
    t = one(log)
    assert t.end_turn is None
    assert T.classify(t) == "censored"


def test_ability_and_item_of_the_source_change_the_expected_length():
    persistent = head(p1=(("Whim", "FocusSash", "Persistent"),))
    log = tailwind_log().replace(head(), persistent)
    t = one(log)
    assert t.duration == 6 and t.expected_end == 6
    assert t.extended_by == ("ability:persistent",)

    clay = head(p1=(("Whim", "LightClay", "Prankster"),))
    log = (
        clay
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Light Screen|p1a: Whim\n|-sidestart|p1: A|move: Light Screen"
        )
    )
    t = one(log, "lightscreen")
    assert t.duration == 8 and t.extended_by == ("item:lightclay",)


def test_an_item_lost_before_the_move_does_not_extend_it():
    clay = head(p1=(("Whim", "LightClay", "Prankster"),))
    log = (
        clay
        + "\n|turn|1\n|-enditem|p1a: Whim|Light Clay|[from] move: Knock Off|[of] p2a: Inci\n"
        + "|move|p1a: Whim|Light Screen|p1a: Whim\n|-sidestart|p1: A|move: Light Screen\n|upkeep"
    )
    t = one(log, "lightscreen")
    assert t.duration == 5 and t.extended_by == ()


def test_lead_weather_starts_on_turn_zero_and_loses_no_turn():
    log = (
        head()
        + "\n|-weather|RainDance|[from] ability: Drizzle|[of] p2a: Inci\n"
        + turns(
            t1="|-weather|RainDance|[upkeep]",
            t2="|-weather|RainDance|[upkeep]",
            t3="|-weather|RainDance|[upkeep]",
            t4="|-weather|RainDance|[upkeep]",
            t5="|-weather|none",
        )
    )
    t = one(log)
    assert (t.id, t.kind, t.start_turn) == ("raindance", "weather", 0)
    assert t.expected_end == 5 and t.end_turn == 5
    assert T.classify(t) == "match"
    assert t.source == "p2:Inci"  # side and name, so it survives slot changes


def test_weather_set_after_the_residual_loses_no_turn():
    log = (
        head()
        + "\n"
        + turns(t1="", t2="")
        + "\n|-weather|SunnyDay|[from] ability: Drought|[of] p2a: Inci\n"
        + turns(t3="", t4="", t5="", t6="", t7="|-weather|none")
    )
    t = one(log)
    assert (t.start_turn, t.start_phase) == (2, AFTER_RESIDUAL)
    assert t.expected_end == 7 and T.classify(t) == "match"


def test_replacing_weather_ends_the_first_without_an_end_event():
    log = (
        head()
        + "\n|-weather|RainDance|[from] ability: Drizzle|[of] p2a: Inci\n"
        + turns(t1="", t2="|move|p1a: Whim|Sunny Day|p1a: Whim\n|-weather|SunnyDay")
    )
    game = T.track_game(log, TABLE)
    rain = next(t for t in game.timers if t.id == "raindance")
    assert (rain.end_reason, rain.end_turn) == ("replaced", 2)
    assert T.classify(rain) == "censored"


def test_leaving_the_field_ends_a_volatile_silently():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p2a: Inci|Flare Blitz|p1a: Whim\n"
            "|move|p1a: Whim|Encore|p2a: Inci\n|-start|p2a: Inci|Encore",
            t2="|switch|p2a: Other|Other, L50|100/100",
        )
    )
    t = one(log, "encore")
    assert t.end_reason == "switched" and T.classify(t) == "censored"


def test_fainting_ends_a_volatile():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Taunt|p2a: Inci\n|-start|p2a: Inci|move: Taunt",
            t2="|faint|p2a: Inci",
        )
    )
    t = one(log, "taunt")
    assert t.end_reason == "fainted" and T.classify(t) == "censored"


def test_encore_runs_one_turn_longer_if_the_target_has_already_moved():
    after = (
        head()
        + "\n"
        + turns(
            t1="|move|p2a: Inci|Flare Blitz|p1a: Whim\n"
            "|move|p1a: Whim|Encore|p2a: Inci\n|-start|p2a: Inci|Encore"
        )
    )
    before = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Encore|p2a: Inci\n|-start|p2a: Inci|Encore\n"
            "|move|p2a: Inci|Flare Blitz|p1a: Whim"
        )
    )
    t = one(after, "encore")
    assert t.duration == 4 and t.extended_by == ("ordering:+1",)
    t = one(before, "encore")
    assert t.duration == 3 and t.extended_by == ()


def test_disable_runs_one_turn_shorter_if_the_target_has_not_moved_yet():
    before = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Disable|p2a: Inci\n|-start|p2a: Inci|Disable|Flare Blitz"
        )
    )
    assert one(before, "disable").duration == 4
    after = (
        head()
        + "\n"
        + turns(
            t1="|move|p2a: Inci|Flare Blitz|p1a: Whim\n"
            "|move|p1a: Whim|Disable|p2a: Inci\n|-start|p2a: Inci|Disable|Flare Blitz"
        )
    )
    assert one(after, "disable").duration == 5


def test_using_trick_room_again_is_an_explained_early_end():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Trick Room|p1a: Whim\n|-fieldstart|move: Trick Room|[of] p1a: Whim",
            t2="|move|p2a: Inci|Trick Room|p2a: Inci\n|-fieldend|move: Trick Room",
        )
    )
    t = one(log)
    assert (t.kind, t.target, t.end_reason) == ("pseudoWeather", "field", "toggled")
    assert T.classify(t) == "explained"


def test_random_length_effects_accept_every_value_in_the_range():
    start = "|move|p1a: Whim|Fire Spin|p2a: Inci\n|-activate|p2a: Inci|move: Fire Spin|[of] p1a: Whim"
    # the log names the trap's start with -start in real games
    start = "|-start|p2a: Inci|Fire Spin"
    table = Durations(
        "t", timed={"firespin": eff("firespin", "volatileStatus", 5, rnd=(5, 7))}
    )
    for end_turn, expected in (
        (5, "match"),
        (6, "match"),
        (4, "unexplained"),
        (7, "unexplained"),
    ):
        blocks = {f"t{n}": "" for n in range(1, 9)}
        blocks["t1"] = start
        blocks[f"t{end_turn}"] = "|-end|p2a: Inci|Fire Spin"
        game = T.track_game(head() + "\n" + turns(**blocks), table)
        assert [T.classify(t) for t in game.timers] == [expected], end_turn


def test_a_trigger_named_in_the_table_shortens_the_effect():
    # Psychic Noise's Heal Block lasts 2 turns, not 5. The log shows the cause as
    # the move used just before, not as a [from] tag.
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p2a: Inci|Psychic Noise|p1a: Whim\n|-start|p1a: Whim|move: Heal Block",
            t2="|-end|p1a: Whim|move: Heal Block",
        )
    )
    t = one(log, "healblock")
    assert t.duration == 2 and t.extended_by == ("trigger:Psychic Noise",)
    assert T.classify(t) == "match"


def test_mental_herb_ending_a_volatile_is_an_explained_removal():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Taunt|p2a: Inci\n|-start|p2a: Inci|move: Taunt\n"
            "|-enditem|p2a: Inci|Mental Herb\n|-end|p2a: Inci|move: Taunt"
        )
    )
    t = one(log, "taunt")
    assert (t.end_reason, t.end_detail) == ("removed", "item: Mental Herb")
    assert T.classify(t) == "explained"


def test_a_removal_move_or_ability_just_before_the_end_is_the_cause():
    base = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Aurora Veil|p1a: Whim\n|-sidestart|p1: A|move: Aurora Veil",
            t2="|move|p2a: Inci|Raging Bull|p1a: Whim\n|-sideend|p1: A|move: Aurora Veil",
        )
    )
    t = one(base, "auroraveil")
    assert (t.end_reason, t.end_detail) == ("removed", "move: Raging Bull")
    ability = base.replace(
        "|move|p2a: Inci|Raging Bull|p1a: Whim",
        "|switch|p2a: Rime|Rime, L50|100/100\n|-activate|p2a: Rime|ability: Screen Cleaner",
    )
    t = one(ability, "auroraveil")
    assert (t.end_reason, t.end_detail) == ("removed", "ability: Screen Cleaner")


def test_the_natural_end_in_the_residual_is_not_blamed_on_the_last_move():
    log = tailwind_log(end_in=4).replace(
        "|turn|4", "|turn|4\n|move|p2a: Inci|Flare Blitz|p1a: Whim\n|"
    )
    t = one(log)
    assert (t.end_reason, t.end_detail) == ("ended", "")


def test_the_cause_can_be_several_lines_back_within_the_same_block_of_actions():
    # Defog, then Defiant's unboost/boost lines, then the removal.
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Tailwind|p1a: Whim\n|-sidestart|p1: A|move: Tailwind",
            t2="|\n|t:|1\n|move|p2a: Inci|Defog|p1a: Whim\n|-unboost|p1a: Whim|evasion|1\n"
            "|-ability|p1a: Whim|Defiant|boost\n|-boost|p1a: Whim|atk|2\n"
            "|-sideend|p1: A|move: Tailwind",
        )
    )
    t = one(log)
    assert (t.end_reason, t.end_detail) == ("removed", "move: Defog")


# --------------------------------------------------------------------------
# What a decision point may know (the leakage rule)
# --------------------------------------------------------------------------


def snapshots(log):
    return T.track_game(log, TABLE).snapshots


def test_turns_remaining_at_each_decision_point_come_from_the_start_alone():
    snap = snapshots(tailwind_log(end_in=4))
    assert snap[1] == ()
    assert snap[2] == (("tailwind", "p1", 3),)
    assert snap[3] == (("tailwind", "p1", 2),)
    assert snap[4] == (("tailwind", "p1", 1),)
    assert snap[5] == ()


def test_snapshots_ignore_the_future_end_event():
    """Removing the end event, or moving it later, changes nothing before it."""
    base = snapshots(tailwind_log(end_in=4))
    without = snapshots(
        tailwind_log(end_in=4).replace("|-sideend|p1: A|move: Tailwind\n", "")
    )
    assert without == base  # nothing past the scheduled end differs either
    for end_in in (3, 4, 5):
        other = snapshots(tailwind_log(end_in=end_in))
        for turn in range(1, end_in + 1):
            assert other[turn] == base[turn], (end_in, turn)


def test_snapshot_at_a_turn_is_the_same_whether_or_not_the_rest_of_the_log_exists():
    log = tailwind_log(end_in=4)
    full = snapshots(log)
    lines = log.split("\n")
    for turn in (2, 3, 4):
        cut = lines.index(f"|turn|{turn}")
        prefix = "\n".join(lines[: cut + 1])
        assert snapshots(prefix)[turn] == full[turn]


def test_a_past_removal_is_visible_to_later_decision_points():
    snap = snapshots(tailwind_log(end_in=2))
    assert snap[2] == (("tailwind", "p1", 3),)  # taken before the removal happens
    assert snap[3] == ()  # the removal has happened by now


# --------------------------------------------------------------------------
# Counted effects
# --------------------------------------------------------------------------


def counters(body, **head_kw):
    return T.track_game(head(**head_kw) + "\n" + turns(t1=body), TABLE).counters


def test_sleep_counts_the_attempts_it_prevented():
    c = counters(
        "|-status|p1a: Whim|slp\n|cant|p1a: Whim|slp\n|cant|p1a: Whim|slp\n"
        "|-curestatus|p1a: Whim|slp|[msg]"
    )
    assert [(x.id, x.attempts, x.completed, x.early_bird, x.variant) for x in c] == [
        ("slp", 2, True, False, None)
    ]


def test_early_bird_and_rest_are_flagged_so_they_are_not_mixed_in():
    body = "|-status|p1a: Whim|slp\n|-curestatus|p1a: Whim|slp|[msg]"
    c = counters(body, p1=(("Whim", "x", "EarlyBird"),))
    assert c[0].early_bird is True
    rest = "|-status|p1a: Whim|slp|[from] move: Rest\n|-curestatus|p1a: Whim|slp|[msg]"
    assert counters(rest)[0].variant == "rest"


def test_a_cure_from_outside_is_not_a_completed_countdown():
    c = counters(
        "|-status|p1a: Whim|frz\n|cant|p1a: Whim|frz\n"
        "|-curestatus|p1a: Whim|frz|[from] move: Flare Blitz|[of] p2a: Inci"
    )
    assert (c[0].id, c[0].attempts, c[0].completed) == ("frz", 1, False)
    natural = counters("|-status|p1a: Whim|frz\n|-curestatus|p1a: Whim|frz|[msg]")
    assert natural[0].completed is True


def test_confusion_counts_activations_and_stops_when_the_pokemon_leaves():
    c = counters(
        "|-start|p1a: Whim|confusion\n"
        + "|-activate|p1a: Whim|confusion\n" * 3
        + "|-end|p1a: Whim|confusion"
    )
    assert (c[0].id, c[0].attempts, c[0].completed) == ("confusion", 3, True)
    left = counters(
        "|-start|p1a: Whim|confusion\n|-activate|p1a: Whim|confusion\n"
        "|switch|p1a: Other|Other, L50|100/100"
    )
    assert (left[0].attempts, left[0].completed) == (1, False)


# --------------------------------------------------------------------------
# Reading the big log files, and tallying
# --------------------------------------------------------------------------


def test_iter_log_file_streams_the_same_games_json_would_load(tmp_path):
    games = {
        f"gen9championsvgc2026regmb-{i}": [1700000000 + i, "|x|" * (50 + i)]
        for i in range(40)
    }
    path = tmp_path / "logs.json"
    path.write_text(json.dumps(games), encoding="utf-8")
    streamed = {
        tag: [ts, log] for tag, (ts, log) in T.iter_log_file(path, chunk_size=64)
    }
    assert streamed == games


def test_tally_counts_by_format_and_effect_and_merges():
    a, b = T.Tally(), T.Tally()
    a.add_game("regma", T.track_game(tailwind_log(4), TABLE), "tagA")
    b.add_game("regma", T.track_game(tailwind_log(3), TABLE), "tagB")
    b.add_game("regmb", T.track_game(tailwind_log(4), TABLE), "tagC")
    a.merge(b)
    assert a.counts[("regma", "tailwind")] == {"match": 1, "unexplained": 1}
    assert a.counts[("regmb", "tailwind")] == {"match": 1}
    assert a.examples[("regma", "tailwind")][0][0] == "tagB"
    again = T.Tally.from_json(json.loads(json.dumps(a.to_json())))
    assert again.counts == a.counts


def test_hazard_estimates_count_censored_observations_only_while_they_were_at_risk():
    # 1 countdown ran 1 attempt and ended, 2 ran 2 and ended; 3 were cut off after 1.
    est = T.hazard_estimates({1: 1, 2: 2}, {1: 3})
    assert est[1] == (0, 6)  # nobody ended at attempt 1; all 6 reached it
    assert est[2] == (1, 3)  # one ended; the 3 cut off after 1 attempt never got here
    assert est[3] == (2, 2)


def test_the_tally_keeps_cut_off_countdowns_so_survivorship_does_not_bias_the_hazards():
    game = T.GameTimers(
        counters=[
            T.CounterObservation("slp", "p1a: A", 2, True, False, None),
            T.CounterObservation("slp", "p1a: B", 1, False, False, None),  # fainted
            T.CounterObservation("slp", "p1a: C", 0, True, True, None),  # Early Bird
            T.CounterObservation("slp", "p1a: D", 0, True, False, "rest"),  # excluded
        ]
    )
    tally = T.Tally()
    tally.add_game("regma", game, "tag")
    assert tally.attempts[("regma", "slp", "")] == {2: 1}
    assert tally.cut_off[("regma", "slp", "")] == {1: 1}
    assert tally.attempts[("regma", "slp", "earlybird")] == {0: 1}
    again = T.Tally.from_json(json.loads(json.dumps(tally.to_json())))
    assert again.cut_off == tally.cut_off


def test_the_tally_names_the_causes_of_explained_removals():
    log = tailwind_log(end_in=3).replace(
        "|-sideend|p1: A|move: Tailwind",
        "|-sideend|p1: A|move: Tailwind|[from] move: Defog",
    )
    tally = T.Tally()
    tally.add_game("regma", T.track_game(log, TABLE), "tag")
    assert tally.causes[("regma", "tailwind")] == {"move: Defog": 1}


# --------------------------------------------------------------------------
# The live path: one message at a time, same answers as replaying the log
# --------------------------------------------------------------------------

TERRAINS = Durations(
    "test",
    timed={
        **TABLE.timed,
        "electricterrain": eff(
            "electricterrain", "terrain", 5, [mod("item", "terrainextender", 8)]
        ),
        "grassyterrain": eff(
            "grassyterrain", "terrain", 5, [mod("item", "terrainextender", 8)]
        ),
    },
)


def terrain_swap_log():
    return (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Electric Terrain|p1a: Whim\n|-fieldstart|move: Electric Terrain",
            t2="|move|p2a: Inci|Grassy Terrain|p2a: Inci\n|-fieldend|move: Electric Terrain\n|-fieldstart|move: Grassy Terrain",
            t3="|move|p1a: Whim|Protect|p1a: Whim\n|\n|-fieldend|move: Grassy Terrain",
        )
    )


def fed_one_line_at_a_time(log, table=TABLE):
    tracker = T.TimerTracker(table)
    for line in log.split("\n"):
        tracker.feed(line)
    return tracker


def test_feeding_one_line_at_a_time_gives_the_same_result_as_replaying_the_log():
    for log in (tailwind_log(3), tailwind_log(4), tailwind_log(5), terrain_swap_log()):
        table = TERRAINS
        assert fed_one_line_at_a_time(log, table).result() == T.track_game(log, table)


def test_a_terrain_replaced_by_another_is_seen_as_replaced_when_fed_live():
    game = fed_one_line_at_a_time(terrain_swap_log(), TERRAINS).result()
    by_id = {t.id: t for t in game.timers}
    assert by_id["electricterrain"].end_reason == "replaced"
    assert by_id["grassyterrain"].end_reason == "ended"


def test_a_live_tracker_knows_the_timers_at_a_decision_before_the_game_ends():
    log = tailwind_log(end_in=4)
    full = T.track_game(log, TABLE)
    tracker = T.TimerTracker(TABLE)
    for line in log.split("\n"):
        tracker.feed(line)
        if line == "|turn|3":
            break
    assert tracker.current() == full.snapshots[3]
    assert tracker.current() == (("tailwind", "p1", 2),)


def test_a_field_end_waiting_for_its_next_line_does_not_hide_a_decision_point():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Trick Room|p1a: Whim\n|-fieldstart|move: Trick Room|[of] p1a: Whim",
            t2="|move|p2a: Inci|Trick Room|p2a: Inci\n|-fieldend|move: Trick Room",
            t3="",
        )
    )
    tracker = T.TimerTracker(TABLE)
    lines = log.split("\n")
    for line in lines[: lines.index("|turn|3") + 1]:
        tracker.feed(line)
    assert tracker.current() == ()


def test_ranges_give_the_shortest_and_longest_for_random_lengths():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Fire Spin|p2a: Inci\n|-start|p2a: Inci|Fire Spin", t2=""
        )
    )
    table = Durations(
        "t", timed={"firespin": eff("firespin", "volatileStatus", 5, rnd=(5, 7))}
    )
    game = T.track_game(log, table)
    # started turn 1, lasts 5 or 6: at turn 2, 4 or 5 turns remain
    assert game.ranges[2] == (("firespin", "p2a: Inci", 4, 5),)
    assert game.snapshots[2] == (("firespin", "p2a: Inci", 4),)


def test_counter_state_at_each_turn_carries_attempts_so_far():
    log = (
        head()
        + "\n"
        + turns(
            t1="|move|p1a: Whim|Spore|p2a: Inci\n|-status|p2a: Inci|slp|[from] move: Spore",
            t2="|cant|p2a: Inci|slp",
            t3="|cant|p2a: Inci|slp",
            t4="",
        )
    )
    game = T.track_game(log, TABLE)
    assert game.counter_state[2] == (("slp", "p2a: Inci", 0),)
    assert game.counter_state[3] == (("slp", "p2a: Inci", 1),)
    assert game.counter_state[4] == (("slp", "p2a: Inci", 2),)


def test_the_timer_file_round_trips_and_holds_nothing_from_the_future(tmp_path):
    game = T.track_game(tailwind_log(end_in=4), TABLE)
    path = tmp_path / "timers.jsonl.gz"
    T.write_timer_file(path, [("gen9championsvgc2026regma-1", "regma", game)])
    records = T.read_timer_file(path)
    rec = records["gen9championsvgc2026regma-1"]
    assert rec.format == "regma"
    assert rec.at(3).timers == (("tailwind", "p1", 2, 2),)
    assert rec.at(4).timers == (("tailwind", "p1", 1, 1),)
    assert rec.at(5).timers == ()  # the end turn leaks nothing: it is simply gone
    assert rec.at(99).timers == ()
    import gzip

    raw = gzip.open(path, "rt", encoding="utf-8").read()
    assert "end_turn" not in raw and "end_reason" not in raw


def test_the_command_writes_a_timer_file_from_a_log_directory(tmp_path):
    logs = tmp_path / "battle_logs"
    logs.mkdir()
    tag = "gen9championsvgc2026regmabo3-1"
    (logs / "logs_x.json").write_text(
        json.dumps({tag: [1700000000, tailwind_log(4)]}), encoding="utf-8"
    )
    out = tmp_path / "t.jsonl.gz"
    T.write_timers_from_logs(logs, {"regma": TABLE, "regmb": TABLE}, out)
    assert T.read_timer_file(out)[tag].at(2).timers == (("tailwind", "p1", 3, 3),)
