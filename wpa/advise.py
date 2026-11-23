"""Live advice, the first step (worked ahead in Week 12, toward advice during a
match). At a turn's start: your likely choices, ranked by your win chance
against the opponent's likely replies, valued as the analysis values them
(DEFINITIONS §3, §4 and §7): the same resolver, opponent model and win
probability model as the replay report.

It reads a game so far: a log that ends at a turn's start, or a finished game
at a turn you name (`--turn`), as if that turn had not been played. With the
opponent's sheet hidden (a game that shows none, or `--hidden`), their sets are
believed from the usage statistics and what the game had shown (`wpa.hidden`).

    python -m wpa.advise LINK --player "your name" --turn 3

The best of your likely choices is the model's, against the replies it expects:
a coaching number, not a solver's answer (as in the replay report)."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from wpa.choices import Action
from wpa.replay import ReplayError

Joint = tuple[Action, ...]
Mix = list[tuple[Joint, float]]


def _own(tools, fmt: str, log: str | None = None):
    """The tools with `fmt`'s own models where it has them (Week 15), and each
    player's strength by the rating the log shows (revision 15); tools without
    formats of their own (a stand-in) as they are."""
    if hasattr(tools, "for_format"):
        tools = tools.for_format(fmt)
    if log is not None and hasattr(tools, "for_game"):
        tools = tools.for_game(log)
    return tools


def up_to_turn(log: str, turn: int | None) -> str:
    """The log up to the start of `turn` (its `|turn|` line), or of the last turn
    the log reaches when None; it then ends with an empty block, so the turn's
    start is a decision point (`decisions.build_game` takes one after it)."""
    lines = log.rstrip("\n").split("\n")
    while lines and lines[-1] == "|":
        lines.pop()
    starts = [i for i, x in enumerate(lines) if x.startswith("|turn|")]
    if turn is None:
        if any(x.startswith("|win|") or x.split("|")[1:2] == ["tie"] for x in lines):
            raise ReplayError(
                "this game is over: name the turn to advise on with --turn"
            )
        if not starts:
            raise ReplayError("the log has not reached turn 1 yet")
        i = starts[-1]
    else:
        i = next((k for k in starts if lines[k] == f"|turn|{turn}"), -1)
        if i < 0:
            raise ReplayError(f"this game never reached turn {turn}")
    return "\n".join(lines[: i + 1]) + "\n|\n"


def rank(
    value: Callable[[Joint, Joint], float], choices: Mix, replies: Mix
) -> list[tuple[Joint, float, float]]:
    """Each choice with its expected win chance against the replies (and how
    often players choose it), best first."""
    from wpa.attribution import expected

    got = [(j, expected(value, [(j, 1.0)], replies), p) for j, p in choices]
    return sorted(got, key=lambda x: -x[1])


def rank_all(
    value: Callable[[Joint, Joint], float],
    full: Mix,
    replies: Mix,
    prepare: Callable[[list], Any] | None = None,
    screen: int = 3,
    finalists: int = 12,
) -> tuple[list[tuple[Joint, float, float]], int]:
    """Every choice the rules allow (`full`, with how often players make each),
    ranked by win chance against the replies, best first (DEFINITIONS §4,
    revision 13). With more than the ones players usually make and `finalists`
    together, a first pass values each choice against the `screen` likeliest
    replies; its best `finalists`, with the ones players usually make, are then
    valued against every reply. The choice model only orders the search: no
    choice is dropped for being unusual. Choices valued in the first pass only
    follow the others, by that value. `prepare` is given each pass's pairs
    (yours, theirs) before it is valued. Returns the ranking (choice, win
    chance, how often players make it) and how many choices were compared."""
    from wpa.attribution import USUAL, expected

    def ask(pairs: list) -> None:
        if prepare is not None:
            prepare(pairs)

    order = sorted(full, key=lambda x: -x[1])
    chance = dict(order)
    if len(order) <= USUAL + finalists:
        ask([(j, y) for j, _ in order for y, _ in replies])
        got = [(j, expected(value, [(j, 1.0)], replies), p) for j, p in order]
        return sorted(got, key=lambda x: -x[1]), len(order)
    top = sorted(replies, key=lambda x: -x[1])[:screen]
    total = sum(q for _, q in top)
    top = [(y, q / total) for y, q in top]
    ask([(j, y) for j, _ in order for y, _ in top])
    first = {j: expected(value, [(j, 1.0)], top) for j, _ in order}
    best = sorted(first, key=lambda j: -first[j])[:finalists]
    final = list(dict.fromkeys([*(j for j, _ in order[:USUAL]), *best]))
    ask([(j, y) for j in final for y, _ in replies])
    got = sorted(
        ((j, expected(value, [(j, 1.0)], replies), chance[j]) for j in final),
        key=lambda x: -x[1],
    )
    done = set(final)
    rest = sorted((j for j, _ in order if j not in done), key=lambda j: -first[j])
    return got + [(j, first[j], chance[j]) for j in rest], len(order)


@dataclass
class Search:
    """`rank_within`'s ranking and what it valued."""

    ranked: list[tuple[Joint, float, float]]  # best first, as `rank_all`
    compared: int  # every choice the rules allow
    full: int  # valued against every reply
    screened: int  # valued against the likeliest replies only
    stopped: bool  # the time ran out before the search was done


def rank_within(
    value: Callable[[Joint, Joint], float],
    full: Mix,
    replies: Mix,
    prepare: Callable[[list], Any],
    stop: Callable[[], bool],
    known: Sequence[Joint] = (),
    screen: int | None = None,
    finalists: int | None = None,
    pairs: int = 12,
    last: Collection[Joint] = (),
) -> Search:
    """`rank_all` within a time (the bot, Week 16 Task 2): the same passes,
    each going the likeliest choices first (the second, the best of the first
    pass first) in batches of about `pairs` pairs, and stopping when `stop()`
    says the time is up (looked at before every batch, the first too, and by
    `prepare` between pairs: a batch it cuts short, saying False, is not
    counted). With nothing valued, the likeliest play comes first (Week 17).
    With time to spare, the ranking is `rank_all`'s. When the
    time runs out: the choices valued against every reply first (with `known`,
    choices already valued so: the replies' weighing values the likely ones),
    then those valued against the likeliest replies, then the rest, likeliest
    first, with no value (NaN). Nothing is dropped."""
    from wpa.attribution import FINALISTS, SCREEN, USUAL, expected

    screen = SCREEN if screen is None else screen
    finalists = FINALISTS if finalists is None else finalists
    # plays to value last (`wpa.shortcuts.value_last`, Week 17) go after the
    # rest, whatever their odds
    order = sorted(full, key=lambda x: (x[0] in last, -x[1]))
    chance = dict(order)
    stopped = False

    def batches(js: list[Joint], ys: Mix) -> list[Joint]:
        nonlocal stopped
        done: list[Joint] = []
        step = max(1, pairs // max(1, len(ys)))
        for k in range(0, len(js), step):
            if stop():  # nothing valued yet: the likeliest play (Week 17)
                stopped = True
                break
            part = js[k : k + step]
            if prepare([(j, y) for j in part for y, _ in ys]) is False:
                stopped = True  # cut short between pairs: not counted
                break
            done += part
        return done

    def full_value(j: Joint) -> float:
        return expected(value, [(j, 1.0)], replies)

    if len(order) <= USUAL + finalists:
        first: dict[Joint, float] = {}
        vals = {j: full_value(j) for j in batches([j for j, _ in order], replies)}
    else:
        top = sorted(replies, key=lambda x: -x[1])[:screen]
        total = sum(q for _, q in top)
        top = [(y, q / total) for y, q in top]
        done = batches([j for j, _ in order], top)
        first = {j: expected(value, [(j, 1.0)], top) for j in done}
        best = sorted(first, key=lambda j: -first[j])[:finalists]
        final = list(dict.fromkeys([*(j for j, _ in order[:USUAL]), *best]))
        final = [j for j in sorted(final, key=lambda j: -first.get(j, -1.0))]
        vals = {}
        if not stopped:
            vals = {j: full_value(j) for j in batches(final, replies)}
    if stopped:  # every play already valued against every reply counts
        vals.update({j: full_value(j) for j in known if j in chance and j not in vals})
    got = sorted(((j, vals[j], chance[j]) for j in vals), key=lambda x: -x[1])
    rest = sorted((j for j in first if j not in vals), key=lambda j: -first[j])
    got += [(j, first[j], chance[j]) for j in rest]
    seen = set(vals) | set(first)
    got += [(j, float("nan"), p) for j, p in order if j not in seen]
    return Search(got, len(order), len(vals), len(rest), stopped)


def strong_within(
    tv,
    plain: Mapping[str, Mix],
    strength,
    role: str,
    stop: Callable[[], bool],
    pairs: int = 12,
) -> tuple[Mix, list[Joint] | None]:
    """The other side's likely replies weighed by their worth (`strong_mixes`),
    within a time: against the player's likely choices, likeliest first, each
    against every one of their replies; when `stop()` says the time is up,
    against those valued so far. The time is looked at before each batch of
    about `pairs` pairs and between pairs (Week 17: one choice against every
    reply took up to 145 s); with none weighed, their replies are taken as
    they come. With time to spare, `strong_mixes`'s. Returns
    their weighed replies and the player's likely choices they were weighed
    against, each now valued against every one of them (None at strength 0:
    nothing to weigh)."""
    from wpa.attribution import _none, _side, strengthened

    other = "p2" if role == "p1" else "p1"
    theirs, ours = plain[other], plain[role]
    s = 0.0 if _none(strength) else _side(strength, other)
    if not s:
        return list(theirs), None
    used: list[int] = []
    for i in sorted(range(len(ours)), key=lambda k: -ours[k][1]):
        j = ours[i][0]
        asks = [(j, y) if role == "p1" else (y, j) for y, _ in theirs]
        whole = True
        for k in range(0, len(asks), pairs):
            if stop() or tv.prepare(asks[k : k + pairs], stop) is False:
                whole = False
                break
        if not whole:
            break
        used.append(i)
    if not used:  # nothing weighed in time: their replies as they come
        return list(theirs), []
    part = [x for i, x in enumerate(ours) if i in set(used)]
    return strengthened(tv.for_role(other), theirs, part, s), [ours[i][0] for i in used]


@dataclass
class Advice:
    tag: str
    turn: int
    role: str
    wp: float  # the player's win chance now
    # best first: the choice (a joint, or a `Pick` at "bring"), chance after,
    # how often players make it
    choices: list[tuple[Any, float, float]]
    replies: list[tuple[Joint, float]]  # their likeliest replies, with chances
    kept: float  # the share of their replies' chance taken exactly
    hidden: bool  # the opponent's sheet hidden
    # the player's chance after a typical choice (their likely choices, as §3's
    # typical choice): what playing the turn out gives, whatever they choose
    typical: float = float("nan")
    # "turn", "preview" (the leads), "bring" (team preview as the app asks it:
    # four to pick, the first two lead) or "replacement" (a forced switch)
    kind: str = "turn"
    note: str = ""  # a warning shown at the top (`team_check.rough_note`)
    # how many choices were compared: at a turn, every one the rules allow
    # (DEFINITIONS §4, revision 13); 0 when not counted
    compared: int = 0
    # within a time (the bot, Week 16): how many were valued against every
    # reply, how many against the likeliest replies only, whether the time ran
    # out, and how many of the player's likely choices their replies were
    # weighed against (all of them, unless the time ran out first)
    valued: int = 0
    screened: int = 0
    stopped: bool = False
    weighed: int = 0
    # the shortcuts (Week 17): plays left out by rule, both sides; how many of
    # the player's plays were valued last
    removed: dict = field(default_factory=dict)
    last: int = 0


@dataclass
class _Point:
    """What a decision point gives the advice: the sheets as the player sees
    them (`view`), the board and its field, the resolver, the board values from
    the player's side as p1's chances (`bw`), and the player's chance now."""

    game: Any
    sheets: dict
    view: dict
    sides: dict
    theirs: list | None  # the other's side with believed items (sheet hidden)
    fld: object
    rv: object
    bw: Any
    wp: float
    pol_spreads: dict
    odds: Any
    brought: dict
    idx: int  # the player's own state for the board
    hidden: bool


def _point(tag: str, log: str, fmt: str, tools, role: str, at: str) -> _Point:
    """The decision point the log ends at, from `role`'s side: `at` "turn" (the
    last turn's start), "preview" (team preview; the log reaches turn 1's
    start, whose board is the template the leads are put on) or "replacement"
    (a forced switch after the last turn). The boards are valued from the
    player's own row, and given back as p1's chances."""
    from wpa import attribution as A
    from wpa import decisions as D
    from wpa import resolver as R
    from wpa.bring import brought_from_log
    from wpa.features import (
        _blank_contexts,
        blank_state,
        columns,
        damage_contexts,
        public_sheet,
        state_features,
    )
    from wpa.policy_data import game_tools
    from wpa.spreads import Belief, priors_for

    other = "p2" if role == "p1" else "p1"
    dex, table = tools.dexes[fmt], tools.tables[fmt]
    sheets, spreads, odds = game_tools(tag, log, fmt, tools.store, tools.bring, dex)
    if set(sheets) != {"p1", "p2"}:
        raise ReplayError("the log shows no team sheets")
    game = D.build_game(log, table)
    states, joined = game.states[role], game.joined[role]

    def last(moment: str) -> int:
        got = [i for i, s in enumerate(states) if s["moment"] == moment]
        if not got:
            what = {"after_turn": "a forced switch of yours"}.get(
                moment, "a turn's start"
            )
            raise ReplayError(f"the log has no {what} to advise on")
        return got[-1]

    moment = {"turn": "turn_start", "preview": "preview", "replacement": "after_turn"}
    kb = last(moment[at])
    kv = last("turn_start") if at == "preview" else kb  # the boards valued
    mine = states[kb]
    fld = R.field_from_timers(joined[kb], role)
    cols = columns(tools.groups)
    hidden = tools.hidden is not None
    theirs = None
    if not hidden:
        ctx_all = damage_contexts(
            tag, log, game, sheets, dex, tools.calc, tools.store, tools.bring
        )
        view = dict(sheets)
        sides = {
            role: [dict(m) for m in mine["our_pokemon"]],
            other: [dict(m) for m in mine["opp_pokemon"]],
        }
        ctx = ctx_all[role][kb]
        rv_spreads, rv_dists = ctx.spreads, ctx.dists
        pol_spreads = spreads
        predict = tools.predict[fmt]
        pub, ctx_v, rows = sheets, ctx_all[role][kv], states
    else:
        usage = tools.store.for_game(tag, log)
        sets = tools.hidden.for_game(tag, log)
        view, theirs = A.player_view(sheets, role, mine["opp_pokemon"], sets, dex)
        sides = {
            role: [dict(m) for m in mine["our_pokemon"]],
            other: [dict(m) for m in theirs],
        }
        pri = priors_for(view, usage, dex)
        rv_spreads = {key: Belief(v).best() for key, v in pri.items() if v}
        rv_dists = {key: [(c, c.weight) for c in v] for key, v in pri.items() if v}
        pol_spreads = rv_spreads
        context_for = _blank_contexts(
            tag, log, "p1", sheets, dex, tools.calc, tools.store, tools.bring
        )
        pub = {
            role: sheets[role],
            other: public_sheet(sheets[other], mine["opp_pokemon"]),
        }
        predict = tools.predict_public[fmt]
        ctx, ctx_v = context_for(kb, pub), context_for(kv, pub)
        rows = [*states[:kb], blank_state(mine)]
    sides = {"p1": sides["p1"], "p2": sides["p2"]}
    bw = A.BoardWP(
        predict,
        states,
        kv,
        joined[kv],
        pub,
        dex,
        table,
        tools.groups,
        ctx_v,
        same_point=at == "preview",
        budget=tools.budget,
        role=role,
        public=hidden,
    )
    f = state_features(rows, kb, role, joined[kb], pub, dex, table, tools.groups, ctx)
    wp = float(predict(np.array([[f[c] for c in cols]], np.float32))[0])
    brought = brought_from_log(log)
    if at != "preview":
        for r in ("p1", "p2"):
            for i in brought.get(r, ()):
                if i < len(sides[r]):
                    sides[r][i]["_brought"] = True
    rv = R.Resolver(
        dex,
        tools.moves[fmt],
        tools.calc,
        view,
        rv_spreads,
        resolution=tools.resolution,
        cap=tools.cap,
        dists=rv_dists
        if tools.speed_beliefs or tools.spread_hits or tools.spread_damage
        else None,
        spread_hits=tools.spread_hits,
        spread_damage=tools.spread_damage,
        switch_in=A.pivot_chooser(tools, view, rv_spreads, dex, odds),
        speed_beliefs=tools.speed_beliefs,
    )
    return _Point(
        game,
        sheets,
        view,
        sides,
        theirs,
        fld,
        rv,
        bw,
        wp,
        pol_spreads,
        odds,
        brought,
        kb,
        hidden,
    )


def _turn_mixes(
    tag: str,
    log: str,
    fmt: str,
    tools,
    role: str,
    own_four,
    fired: Counter | None = None,
    lasts: set | None = None,
):
    """A turn's start from `role`'s side: the decision point, its values (not
    yet resolved), the turn, each side's every choice with the choice model's
    chances (`full`), their likely ones (`plain`), and the share of the other
    side's chance taken exactly. `tools` already the format's own. With
    `fired` (the bot's shortcuts, Week 17): plays that cannot work are left
    out on both sides and counted in it by rule, and `role`'s plays to value
    last are put in `lasts`."""
    from wpa import attribution as A
    from wpa import choices as C
    from wpa.policy_data import _timers_by_turn, turn_options

    other = "p2" if role == "p1" else "p1"
    dex = tools.dexes[fmt]
    pt = _point(tag, log, fmt, tools, role, "turn")
    game = pt.game
    turn = game.states[role][pt.idx]["turn"]
    tt = {t.role: t for t in C.turns(log, dex) if t.turn == turn}
    if set(tt) != {"p1", "p2"}:
        raise ReplayError(f"turn {turn}: no choices to make")
    four = A.brought_four({r: pt.brought.get(r, set()) for r in ("p1", "p2")})
    if own_four:
        four[role] = set(own_four)
    timers = {r: _timers_by_turn(game, r) for r in ("p1", "p2")}
    rates = (
        tools.policy.rates.get(fmt, {}) if isinstance(tools.policy.rates, dict) else {}
    )
    tv = A.TurnValues(pt.rv, pt.sides, pt.fld, pt.bw)
    full = {}
    for q in ("p1", "p2"):
        t = tt[q]
        if pt.theirs is not None:  # the other's items as the player saw them
            t = (
                replace(t, ours=[dict(m) for m in pt.theirs])
                if q == other
                else replace(t, theirs=[dict(m) for m in pt.theirs])
            )
        feats = turn_options(
            t,
            timers[q].get(turn),
            pt.view,
            pt.pol_spreads,
            dex,
            tools.moves[fmt],
            rates,
            tools.calc,
            pt.odds,
            shortcuts=fired,
        )
        opts, chances = A.only_brought(
            *A.expand_pivots(
                {i: o for i, (o, _X) in feats.items()},
                {i: list(tools.policy.chances(X)) for i, (_o, X) in feats.items()},
            ),
            four[q],
        )
        full[q] = A.mixture({i: list(zip(opts[i], chances[i])) for i in opts})
    if lasts is not None:
        from wpa.policy_data import side_and_weather
        from wpa.shortcuts import last_play

        theirs = tt[role].theirs
        side, weather = side_and_weather(timers[role].get(turn))
        lasts.update(
            j
            for j, _ in full[role]
            if last_play(j, theirs, tools.moves[fmt], side, weather)
        )
    plain, kept = {}, 1.0
    for q in ("p1", "p2"):
        plain[q], k = A.likely(full[q], tools.top, tools.draws, f"{tag} {turn} {q}")
        if q == other:
            kept = k
    return pt, tv, turn, full, plain, kept


def typical_turn(
    tag: str, log: str, fmt: str, tools, role: str, own_four: set[int] | None = None
) -> Mix:
    """How players typically choose at the turn's start: the choice model's
    chances over every choice the rules allow, none valued (the bot's opponent
    "the choice model", Week 16 Task 3)."""
    tools = _own(tools, fmt, log)
    return _turn_mixes(tag, log, fmt, tools, role, own_four)[3][role]


def advise(
    tag: str,
    log: str,
    fmt: str,
    tools,
    role: str,
    own_four: set[int] | None = None,
    stop: Callable[[], bool] | None = None,
    shortcuts: bool = False,
    value_last: bool = False,
) -> Advice:
    """The advice at the start of the last turn the log reaches (`up_to_turn`).
    `own_four`: the four the player brought, when known (the log shows only
    those that have come out). `stop`: within a time (the bot, Week 16), the
    search goes the likeliest plays first and ends when it says the time is up
    (`strong_within`, `rank_within`); the typical choice is not valued.
    `shortcuts` (the bot, Week 17): plays that cannot work left out on both
    sides (`wpa.shortcuts`); `value_last` as well: plays that rarely make
    sense valued last (off since the head-to-head of 21 Nov, the PO's call)."""
    tools = _own(tools, fmt, log)  # own models (Week 15); by rating (rev 15)
    from wpa import attribution as A

    other = "p2" if role == "p1" else "p1"
    fired: Counter | None = Counter() if shortcuts else None
    lasts: set | None = set() if shortcuts and value_last else None
    pt, tv, turn, full, plain, kept = _turn_mixes(
        tag, log, fmt, tools, role, own_four, fired, lasts
    )
    strength = getattr(tools, "main_strength", tools.strength)
    if stop is not None:  # within a time (Week 16 Task 2)
        replies, used = strong_within(tv, plain, strength, role, stop)
        weighed = len(plain[role]) if used is None else len(used)

        def prepare(pairs) -> bool:  # the resolver takes (p1's, p2's)
            return tv.prepare(
                [(j, y) if role == "p1" else (y, j) for j, y in pairs], stop
            )

        s = rank_within(
            tv.for_role(role),
            full[role],
            replies,
            prepare,
            stop,
            known=used or (),
            last=lasts or (),
        )
        return Advice(
            tag,
            turn,
            role,
            pt.wp,
            s.ranked,
            sorted(replies, key=lambda x: -x[1]),
            kept,
            pt.hidden,
            compared=s.compared,
            valued=s.full,
            screened=s.screened,
            stopped=s.stopped or weighed < len(plain[role]),
            weighed=weighed,
            removed=dict(fired or {}),
            last=len(lasts or ()),
        )
    strong = A.strong_mixes(tv, plain, strength)
    replies, mine = strong[other], strong[role]
    if tools.alternatives is None:  # every choice the rules allow (rev 13)
        return _advice(
            tag, turn, role, pt, tv, full[role], mine, replies, kept, every=True
        )
    choices, _ = A.trim(full[role], 1.0, tools.alternatives)  # the old way
    return _advice(tag, turn, role, pt, tv, choices, mine, replies, kept)


def advise_preview(
    tag: str,
    log: str,
    fmt: str,
    tools,
    role: str,
    prev: Mapping[str, frozenset[str]] | None = None,
) -> Advice:
    """Team preview: each pair of leads, valued at turn 1's start after both
    sides' leads come in (`Resolver.lead`), against their likely leads (the
    lead model, Week 11). The log reaches turn 1's start (`preview_log`, or a
    game cut there). The back two are not valued. `prev`: each player's leads
    in the set's previous game (species)."""
    tools = _own(tools, fmt, log)  # own models (Week 15); by rating (rev 15)
    from wpa import attribution as A
    from wpa.lead_model import pairs

    if tools.leads is None:
        raise ReplayError(
            "lead advice needs the lead model (models_v4/leads.json, Runbook "
            "Section 20, step 1)"
        )
    other = "p2" if role == "p1" else "p1"
    pt = _point(tag, log, fmt, tools, role, "preview")
    if any(len(pt.view[q]) != 6 for q in ("p1", "p2")):
        raise ReplayError("team preview needs six Pokemon on each side")
    tv = A.TurnValues(A.Leads(pt.rv), pt.sides, pt.fld, pt.bw)
    opts = [A.lead_joint(p) for p in pairs(6)]
    mixes = {
        q: list(zip(opts, tools.leads.chances(pt.view[q], fmt, (prev or {}).get(q))))
        for q in ("p1", "p2")
    }
    mixes = {q: [(j, float(p)) for j, p in m] for q, m in mixes.items()}
    return _advice(
        tag, 0, role, pt, tv, mixes[role], mixes[role], mixes[other], 1.0, "preview"
    )


def shown_names(log: str) -> dict[str, list[str]]:
    """Each side's six as the player knows them, in sheet order: the nickname
    where there is one (End Game, Mia), else the species."""
    from wpa.sheets import parse_showteam_message

    out: dict[str, list[str]] = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            role, mons = parse_showteam_message(line)
            out[role] = [m.name or m.species for m in mons]
    return out


class Pick(NamedTuple):
    """Team preview as the app asks it: four Pokemon (sheet positions) in the
    order you pick them; the first two lead."""

    leads: tuple[int, ...]
    back: tuple[int, ...]


def usual_back(odds: Sequence[float], leads: Iterable[int]) -> tuple[int, ...]:
    """The two players most often bring with these leads: the likeliest four
    that holds them by the bring model's odds (`wpa.bring.set_chances`), less
    the leads. A tie goes to the earlier sheet positions."""
    from wpa.bring import set_chances

    chances = set_chances(list(odds), set(leads))
    four = max(sorted(chances, key=sorted), key=lambda f: chances[f])
    return tuple(sorted(four - set(leads)))


def advise_bring(
    tag: str,
    log: str,
    fmt: str,
    tools,
    role: str,
    prev: Mapping[str, frozenset[str]] | None = None,
) -> Advice:
    """Team preview as the app asks it: four to pick, the first two leading.
    The leads are ranked as `advise_preview` ranks them. With each pair of
    leads, the back two players most often bring with them (the bring model,
    and since Week 17 against the opponent's six: `bring_odds`); the win
    model does not rank back twos. On the 892 games of the resolver check's
    sample (validation, Week 12), its win chance at turn 1's start moved 6 to 8
    points between fours with the same leads, but for the four actually brought
    it predicted the result no better than for the others (it did better in
    50% of comparisons, in each format)."""
    tools = _own(tools, fmt, log)  # own models (Week 15); by rating (rev 15)
    from wpa.team_sheets import sheets_from_log

    adv = advise_preview(tag, log, fmt, tools, role, prev)
    sh = sheets_from_log(log)
    mons = sh[role]
    theirs = [m.species for m in sh.get("p2" if role == "p1" else "p1", [])]
    odds = bring_odds(tools, fmt, [m.species for m in mons], theirs)
    choices: list[tuple[Any, float, float]] = []
    for j, v, p in adv.choices:
        leads = tuple(sorted(int(a.switch_to or 0) for a in j))
        choices.append((Pick(leads, usual_back(odds, leads)), v, p))
    return replace(adv, choices=choices, kind="bring")


def bring_odds(
    tools, fmt: str, mine: Sequence[str], theirs: Sequence[str]
) -> list[float]:
    """Each of the player's six's odds of being brought (the bring model), moved
    by the opponent's six where the format has the matchup term and all six
    are known (Week 17, Task 5: `wpa.bring.MatchupTerm`)."""
    odds = (
        tools.bring.odds(fmt, tuple(mine), None)
        if tools.bring is not None
        else [1.0] * len(mine)
    )
    term = getattr(tools, "bring_pairs", None)
    if term is not None and len(theirs) == 6:
        odds = term.adjust(odds, mine, theirs)
    return odds


def draw_bring(leads, bring, fmt: str, sheet: Sequence, rng) -> Pick:
    """Team preview as players typically choose it (the bot's opponent "the
    choice model", Week 16 Task 3): the leads drawn from the lead model's
    chances, and the back two from the bring model's chances for the fours
    that hold them. `sheet`: the player's sheet (`SheetMon`s)."""
    from wpa.bring import set_chances
    from wpa.lead_model import pairs

    n = len(sheet)
    ps = np.asarray(leads.chances(sheet, fmt, None), dtype=float)
    lead = pairs(n)[int(rng.choice(len(ps), p=ps / ps.sum()))]
    species = tuple(getattr(m, "species", m) for m in sheet)
    odds = bring.odds(fmt, species, None) if bring is not None else [1.0] * n
    fours = sorted(
        set_chances(list(odds), set(lead)).items(), key=lambda x: sorted(x[0])
    )
    w = np.array([q for _, q in fours], dtype=float)
    four = fours[int(rng.choice(len(fours), p=w / w.sum()))][0]
    return Pick(tuple(lead), tuple(sorted(four - set(lead))))


def up_to_switch(log: str, turn: int | None) -> str:
    """The log up to the forced switch after `turn` (or after the last turn the
    log reaches, when None): its end of turn (`|upkeep`), with an empty block
    after it so the forced switch is a decision point. A turn in which nothing
    fell is refused."""
    lines = log.rstrip("\n").split("\n")
    while lines and lines[-1] == "|":
        lines.pop()
    starts = [i for i, x in enumerate(lines) if x.startswith("|turn|")]
    if turn is None:
        if not starts:
            raise ReplayError("the log has not reached turn 1 yet")
        turn = int(lines[starts[-1]].split("|")[2])
    i = next((k for k in starts if lines[k] == f"|turn|{turn}"), -1)
    if i < 0:
        raise ReplayError(f"this game never reached turn {turn}")
    end = next((k for k in starts if k > i), len(lines))
    up = next((k for k in range(i, end) if lines[k] == "|upkeep"), -1)
    if up < 0 or not any(x.startswith("|faint|") for x in lines[i:up]):
        raise ReplayError(f"nothing fell at the end of turn {turn}: no forced switch")
    return "\n".join(lines[: up + 1]) + "\n|\n"


def advise_replacement(
    tag: str, log: str, fmt: str, tools, role: str, own_four: set[int] | None = None
) -> Advice:
    """A forced switch after a turn (Week 10's model of who is sent in): each
    Pokemon the player could send in, valued at the next turn's start after
    both sides' newcomers come in (`Resolver.replace`), against the other's
    likely ones when they replace too. The log ends at the forced switch
    (`up_to_switch`)."""
    tools = _own(tools, fmt, log)  # own models (Week 15); by rating (rev 15)
    from wpa import attribution as A

    pt, turn, full = _replacement_mixes(tag, log, fmt, tools, role, own_four)
    tv = A.TurnValues(A.SwitchIns(pt.rv), pt.sides, pt.fld, pt.bw)
    other = "p2" if role == "p1" else "p1"
    return _advice(
        tag, turn, role, pt, tv, full[role], full[role], full[other], 1.0, "replacement"
    )


def typical_replacement(
    tag: str, log: str, fmt: str, tools, role: str, own_four: set[int] | None = None
) -> Mix:
    """Who players typically send in at a forced switch: the forced-switch
    model's chances, none valued (the bot's opponent "the choice model")."""
    tools = _own(tools, fmt, log)
    return _replacement_mixes(tag, log, fmt, tools, role, own_four)[2][role]


def _replacement_mixes(tag: str, log: str, fmt: str, tools, role: str, own_four):
    """A forced switch from `role`'s side: the decision point, the turn, and
    each side's choices with the forced-switch model's chances (a side that
    does not replace: one empty choice). `tools` already the format's own."""
    from wpa import attribution as A
    from wpa import choices as C
    from wpa import replace_model as RM
    from wpa.features import _field

    if tools.replace is None:
        raise ReplayError(
            "switch advice needs the forced-switch model (models_v4/replace.json, "
            "Runbook Section 19)"
        )
    other = "p2" if role == "p1" else "p1"
    pt = _point(tag, log, fmt, tools, role, "replacement")
    game = pt.game
    turn = game.states[role][pt.idx]["turn"]
    four = A.brought_four({r: pt.brought.get(r, set()) for r in ("p1", "p2")})
    if own_four:
        four[role] = set(own_four)
    full: dict[str, list] = {}
    for q in ("p1", "p2"):
        after = [
            i
            for i, s in enumerate(game.states[q])
            if s["moment"] == "after_turn" and s["turn"] == turn
        ]
        start = [
            i
            for i, s in enumerate(game.states[q])
            if s["moment"] == "turn_start" and s["turn"] == turn
        ]
        if not after:
            full[q] = [((), 1.0)]  # no forced switch on this side
            continue
        s = game.states[q][after[-1]]
        ours, theirs = s["our_pokemon"], s["opp_pokemon"]
        if pt.theirs is not None:  # the other's items as the player saw them
            if q == other:
                ours = pt.theirs
            else:
                theirs = pt.theirs
        before = game.states[q][start[-1]]["our_pokemon"] if start else ours
        slots = [
            j
            for j, (m, b) in enumerate(zip(ours, before))
            if m["fainted"] and not b["fainted"]
        ]
        bench = [j for j, m in enumerate(ours) if not m["active"] and not m["fainted"]]
        rep = C.Replacement(turn, q, ours, theirs, slots, {}, bench)
        j = game.joined[q][after[-1]]
        got = RM.options(
            rep,
            pt.view,
            pt.pol_spreads,
            tools.dexes[fmt],
            tools.calc,
            pt.odds,
            _field(j) if j else None,
            four[q],
        )
        if not got:
            full[q] = [((), 1.0)]
            continue
        full[q] = A.mixture(
            {
                slot: list(zip(o, tools.replace.chances(X)))
                for slot, (o, X) in got.items()
            }
        )
        full[q] = [(jn, float(p)) for jn, p in full[q]]
    if full[role] == [((), 1.0)]:
        raise ReplayError(f"you had no Pokemon to send in after turn {turn}")
    return pt, turn, full


def _advice(
    tag, turn, role, pt, tv, choices, mine, replies, kept, kind="turn", every=False
) -> Advice:
    """The choices ranked against the replies, and a typical choice (`mine`).
    `every`: `choices` is every choice the rules allow, ranked by `rank_all`
    (DEFINITIONS §4, revision 13)."""
    from wpa.attribution import expected

    def prepare(pairs) -> None:  # the resolver takes (p1's, p2's)
        tv.prepare([(j, y) if role == "p1" else (y, j) for j, y in pairs])

    value = tv.for_role(role)
    if every:
        ranked, compared = rank_all(value, choices, replies, prepare)
        prepare([(j, y) for j, _p in mine for y, _q in replies])
    else:
        prepare([(j, y) for j, _p in [*choices, *mine] for y, _q in replies])
        ranked, compared = rank(value, choices, replies), len(choices)
    return Advice(
        tag,
        turn,
        role,
        pt.wp,
        ranked,
        sorted(replies, key=lambda x: -x[1]),
        kept,
        pt.hidden,
        expected(value, mine, replies),
        kind,
        compared=compared,
    )


def species_name(name: str, dex, known: set[str]) -> str:
    """A species as typed (any case and spacing), as the format's data names it.
    A name that is the start of only one species the format's statistics list
    (not a Mega form) is that species: "Floette" is Floette-Eternal."""
    from wpa.team_sheets import to_id

    sp = to_id(name)
    if sp in dex.species and (not known or sp in known):
        return dex.species[sp].get("name", name.strip())
    hits = sorted(
        k
        for k in known
        if k.startswith(sp) and k in dex.species and not dex.species[k].get("isMega")
    )
    if len(hits) == 1:
        return dex.species[hits[0]].get("name", hits[0])
    if not hits:  # a typo: the nearest names
        import difflib

        hits = difflib.get_close_matches(sp, sorted(known), n=3, cutoff=0.75)
    names = " or ".join(dex.species.get(k, {}).get("name", k) for k in hits)
    raise ReplayError(
        f"{name.strip()!r} is not a species this format's statistics know"
        + (f" (did you mean {names}?)" if hits else "")
    )


TIERS = {
    "regma": "[Gen 9 Champions] VGC 2026 Reg M-A",
    "regmb": "[Gen 9 Champions] VGC 2026 Reg M-B",
    "regmc": "[Gen 9 Champions] VGC 2026 Reg M-C",
}


def preview_log(
    team: str, theirs: Sequence[str], fmt: str, now: float | None = None
) -> tuple[str, str]:
    """A game at team preview, as the app shows it: your team paste and the six
    species of theirs. It reaches turn 1's start, with the first two of each
    side in as a template (the advice puts each pair of leads on it); their
    sheet shows only the species (`replay.with_sheets`)."""
    import time

    from wpa.replay import parse_team, with_sheets

    if len(theirs) != 6:
        raise ReplayError("give their six species, as team preview shows them")
    mine = parse_team(team)
    if len(mine) != 6:
        raise ReplayError("your team paste needs six Pokemon")
    theirs = [s.strip() for s in theirs]

    def details(species: str, level: int = 50, gender: str = "") -> str:
        return f"{species}, L{level}" + (f", {gender}" if gender else "")

    head = [
        "|player|p1|You|",
        "|player|p2|Opponent|",
        "|gametype|doubles",
        "|gen|9",
        f"|tier|{TIERS[fmt]}",
        "|clearpoke",
        *(f"|poke|p1|{details(m['species'], m['level'], m['gender'])}|" for m in mine),
        *(f"|poke|p2|{details(s)}|" for s in theirs),
        "|teampreview|4",
    ]
    log = with_sheets("\n".join(head), "p1", team)
    start = ["|", f"|t:|{int(now if now is not None else time.time())}", "|start"]
    for r, mons in (
        ("p1", [(m["name"], details(m["species"], m["level"])) for m in mine]),
        ("p2", [(s, details(s)) for s in theirs]),
    ):
        for slot, (name, det) in zip("ab", mons[:2]):
            start.append(f"|switch|{r}{slot}: {name}|{det}|100/100")
    start += ["|turn|1", "|", ""]
    return f"gen9championsvgc2026{fmt}-0", log + "\n" + "\n".join(start)


def advice_text(
    adv: Advice, log: str, dex_moves: Mapping | None = None, top: int = 5
) -> str:
    """The advice in words."""
    from wpa.attribution import joint_json
    from wpa.replay import HIDDEN_NOTE, move_names, pct, players, say_choice, shown

    sheets = shown_names(log)
    names = move_names(log, dex_moves)
    who = players(log)
    other = "p2" if adv.role == "p1" else "p1"
    kind = "preview" if adv.kind == "turn" and adv.turn == 0 else adv.kind
    pre = kind in ("preview", "bring")  # their side: likely leads
    typical = "typical leads" if pre else "a typical choice"
    head = {
        "preview": "Team preview.",
        "bring": "Team preview.",
        "turn": f"Turn {adv.turn}.",
        "replacement": f"After turn {adv.turn}: a forced switch.",
    }[kind]
    intro = {
        "preview": "Your leads, best first: your win chance at turn 1's start, on "
        "average over their likely leads, and against typical leads.",
        "bring": "Which four to pick (the first two you pick lead), best leads "
        "first: your win chance at turn 1's start, on average over their likely "
        "leads, and against typical leads. The back two are the two players most "
        "often bring with those leads: the model cannot yet tell which back two "
        "win more.",
        "turn": (
            f"Your choices, best first, of the {adv.compared} the rules allow: "
            if adv.compared
            else "Your likely choices, best first: "
        )
        + "your win chance after this turn, on average over their likely replies, "
        "and against a typical choice.",
        "replacement": "Who to send in, best first: your win chance at the next "
        "turn's start, on average over their likely switch-ins, and against a "
        "typical choice.",
    }[kind]
    theirs = {
        "preview": "Their likeliest leads (the model's chances):",
        "bring": "Their likeliest leads (the model's chances):",
        "turn": "Their likeliest replies (the model's chances):",
        "replacement": "Their likeliest switch-ins (the model's chances):",
    }[kind]
    me = who.get(adv.role, adv.role)
    lines = [
        ("You" if me == "You" else f"{me} (you)") + f" vs {who.get(other, other)}.",
        f"{head} Your win chance now: {pct(adv.wp)}; after {typical}: "
        f"{pct(adv.typical)}.",
        "",
    ]
    if adv.hidden:
        lines[-1:] = [HIDDEN_NOTE.split(" Team preview")[0], ""]
    if adv.note:
        lines += [adv.note, ""]
    lines.append(intro)
    for n, (j, v, p) in enumerate(adv.choices[:top], 1):
        if kind == "bring":
            mine = sheets[adv.role]
            a, b = (mine[i] for i in j.leads)
            c, d = (mine[i] for i in j.back)
            words = f"pick {a} and {b} (they lead), then {c} and {d}"
            often = f"players lead them {pct(p)}"
        else:
            words = say_choice(joint_json(j), kind, adv.role, sheets, names)
            often = (
                f"players lead them {pct(p)}" if pre else f"players choose it {pct(p)}"
            )
        lines.append(
            f"  {n}. {words}: {pct(v)} ({shown(adv.typical, v)} against {typical}); "
            + often
        )
    if kind == "replacement" and adv.replies == [((), 1.0)]:
        lines += ["", "They have no forced switch."]
    else:
        lines += ["", theirs]
        for j, q in adv.replies[:top]:
            words = say_choice(
                joint_json(j), "preview" if pre else kind, other, sheets, names
            )
            lines.append(f"  {words}: {pct(q)}")
    lines += [
        "",
        "The best here is the model's, against the replies it expects: a coaching "
        "number, not a solver's answer.",
    ]
    return "\n".join(lines)


def lead_advice(team: str, theirs: Sequence[str], fmt: str, tools, top: int = 5) -> str:
    """Team preview's advice in words, from your team paste and their six
    species as typed (`species_name`), their sheet hidden."""
    tag, log = preview_log(team, theirs, fmt)  # checks there are six
    dex = tools.dexes[fmt]
    known = set(tools.hidden.for_game(tag, log))
    names = [species_name(s, dex, known) for s in theirs]
    tag, log = preview_log(team, names, fmt)
    adv = advise_preview(tag, log, fmt, tools, "p1")
    return advice_text(adv, log, dex.moves, top)


def pick_advice(team: str, theirs: Sequence[str], fmt: str, tools, top: int = 5) -> str:
    """Team preview as the app asks it, in words: which four to pick and which
    two lead, from your team paste and their six species as typed, their sheet
    hidden."""
    tag, log = preview_log(team, theirs, fmt)  # checks there are six
    dex = tools.dexes[fmt]
    known = set(tools.hidden.for_game(tag, log))
    names = [species_name(s, dex, known) for s in theirs]
    tag, log = preview_log(team, names, fmt)
    note = rough_team_note(team, tools.hidden.for_game(tag, log), dex)
    adv = replace(advise_bring(tag, log, fmt, tools, "p1"), note=note)
    return advice_text(adv, log, dex.moves, top)


def rough_team_note(team: str, usage, dex=None) -> str:
    """The warning for your Pokemon the format's statistics have not seen, or
    have seen on under 1% of teams ("" when it has seen them all)."""
    from wpa import team_check as TC
    from wpa.replay import parse_team
    from wpa.team_sheets import to_id

    species = [m["species"] for m in parse_team(team)]
    by_id = {to_id(s): s for s in species}
    missing, rare = TC.unseen(list(by_id), usage, dex)
    return TC.rough_note([by_id[s] for s in missing], [by_id[s] for s in rare])


def run_session(
    ask: Callable[[], str],
    answer: Callable[[list[str]], str],
    say: Callable[[str], None],
) -> None:
    """Team preview after team preview, from one load: each line their six
    species, separated by commas; an empty line asks again; "q" (or the end of
    the input) ends it. A line it cannot use is said, and the session goes on."""
    say("Their six species, separated by commas (q to stop):")
    while True:
        try:
            line = ask().strip()
        except (EOFError, StopIteration, KeyboardInterrupt):
            return
        if line.lower() in ("q", "quit", "exit"):
            return
        if not line:
            continue
        theirs = [s.strip() for s in line.split(",") if s.strip()]
        try:
            say(answer(theirs))
        except ReplayError as e:
            say(f"Sorry: {e}.")
        say("")
        say("Their six species (q to stop):")


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    from wpa import attribution as A
    from wpa import replay as RP
    from wpa.bring import brought_from_log

    p = argparse.ArgumentParser(
        description="Your best choice at a turn's start, your best four and leads "
        "at team preview, or who to send in, against their likely replies."
    )
    p.add_argument("game", nargs="?", help="a replay link, or a saved replay or log")
    p.add_argument("--player", help="your name in the game")
    p.add_argument("--turn", type=int, default=None, help="the turn to advise on")
    p.add_argument("--preview", action="store_true", help="the leads, at team preview")
    p.add_argument(
        "--switch",
        action="store_true",
        help="the forced switch after the turn (--turn), or after the last turn",
    )
    p.add_argument(
        "--vs",
        help="team preview from the app: their six species, separated by commas "
        "(with --team and --format); which four to pick, the first two leading",
    )
    p.add_argument(
        "--session",
        action="store_true",
        help="team preview after team preview, loading once (with --team)",
    )
    p.add_argument("--format", choices=sorted(TIERS), default="regma")
    p.add_argument("--top", type=int, default=5, help="how many choices to show")
    p.add_argument(
        "--team",
        type=Path,
        default=None,
        help="your team paste (default: my_team.txt, if it is in this folder)",
    )
    p.add_argument("--hidden", action="store_true", help="their sheet hidden")
    p.add_argument("--public-models", type=Path, default=Path("models_v4_preview"))
    p.add_argument("--models", type=Path, default=None)
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--dex-tables", type=Path, default=None)
    a = p.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    own = None
    try:
        from wpa.team_check import TEAM_FILE, default_team

        path = default_team(a.team)
        team = path.read_text(encoding="utf-8") if path else None
        if a.session or a.vs:
            if not team:
                raise ReplayError(
                    f"team preview needs your team paste (--team, or {TEAM_FILE} "
                    "in this folder)"
                )
            if not (a.public_models / "regma").exists():
                raise ReplayError(
                    "their sheet hidden needs the model trained that way, in "
                    f"{a.public_models} (Runbook Section 23, step 3)"
                )
            a.hidden = True
    except (ReplayError, OSError) as e:
        sys.exit(f"Sorry: {e}.")
    if a.session or a.vs:
        assert team is not None
        print("Loading (about 20 seconds)...", flush=True)
        A._init(RP._options(a))
        tools = A._W["tools"]

        def answer(names: list[str]) -> str:  # the four to pick, as the app asks
            return pick_advice(team, names, a.format, tools, a.top)

        if a.session:
            run_session(input, answer, print)
            return
        try:
            print(answer([s.strip() for s in a.vs.split(",") if s.strip()]))
        except ReplayError as e:
            sys.exit(f"Sorry: {e}.")
        return
    try:
        if not a.game or not a.player:
            raise ReplayError("give a game and your name (--player), or --vs")
        tag, full_log = RP.load(a.game)
        fmt = RP.format_for(tag, full_log)
        role = RP.side_of(full_log, a.player)
        games, a.hidden = RP.prepare([(tag, full_log, fmt)], a.player, team, a.hidden)
        full_log = games[0][1]  # with the sheets put in, for a game showing none
        if a.switch:
            log = up_to_switch(full_log, a.turn)
        else:
            log = up_to_turn(full_log, 1 if a.preview else a.turn)
        # the four you brought, when the whole game shows them (you know them)
        seen = brought_from_log(full_log).get(role, set())
        if a.turn is not None and len(seen) >= 4:
            own = seen
        if a.hidden and not (a.public_models / "regma").exists():
            raise ReplayError(
                "their sheet hidden needs the model trained that way, in "
                f"{a.public_models} (Runbook Section 23, step 3)"
            )
    except (ReplayError, OSError) as e:
        sys.exit(f"Sorry: {e}.")
    print("Thinking (about half a minute)...", flush=True)
    A._init(RP._options(a))
    tools = A._W["tools"]
    try:
        if a.preview:
            adv = advise_preview(tag, log, fmt, tools, role)
        elif a.switch:
            adv = advise_replacement(tag, log, fmt, tools, role, own_four=own)
        else:
            adv = advise(tag, log, fmt, tools, role, own_four=own)
    except ReplayError as e:
        sys.exit(f"Sorry: {e}.")
    print(advice_text(adv, log, tools.dexes[fmt].moves, a.top))


if __name__ == "__main__":
    main()
