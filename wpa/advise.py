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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from wpa.choices import Action
from wpa.replay import ReplayError

Joint = tuple[Action, ...]
Mix = list[tuple[Joint, float]]


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


@dataclass
class Advice:
    tag: str
    turn: int
    role: str
    wp: float  # the player's win chance now
    choices: list[tuple[Joint, float, float]]  # best first: chance after, how often
    replies: list[tuple[Joint, float]]  # their likeliest replies, with chances
    kept: float  # the share of their replies' chance taken exactly
    hidden: bool  # the opponent's sheet hidden
    # the player's chance after a typical choice (their likely choices, as §3's
    # typical choice): what playing the turn out gives, whatever they choose
    typical: float = float("nan")


def advise(
    tag: str, log: str, fmt: str, tools, role: str, own_four: set[int] | None = None
) -> Advice:
    """The advice at the start of the last turn the log reaches (`up_to_turn`).
    `own_four`: the four the player brought, when known (the log shows only
    those that have come out)."""
    from wpa import attribution as A
    from wpa import choices as C
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
    from wpa.policy_data import _timers_by_turn, game_tools, turn_options
    from wpa.spreads import Belief, priors_for

    other = "p2" if role == "p1" else "p1"
    dex, table = tools.dexes[fmt], tools.tables[fmt]
    sheets, spreads, odds = game_tools(tag, log, fmt, tools.store, tools.bring, dex)
    if set(sheets) != {"p1", "p2"}:
        raise ReplayError("the log shows no team sheets")
    game = D.build_game(log, table)
    idx = {}
    for r in ("p1", "p2"):
        starts = [
            i for i, s in enumerate(game.states[r]) if s["moment"] == "turn_start"
        ]
        if not starts:
            raise ReplayError("the log has no turn's start to advise on")
        idx[r] = starts[-1]
    turn = game.states[role][idx[role]]["turn"]
    tt = {t.role: t for t in C.turns(log, dex) if t.turn == turn}
    if set(tt) != {"p1", "p2"}:
        raise ReplayError(f"turn {turn}: no choices to make")
    brought = brought_from_log(log)
    four = A.brought_four({r: brought.get(r, set()) for r in ("p1", "p2")})
    if own_four:
        four[role] = set(own_four)
    timers = {r: _timers_by_turn(game, r) for r in ("p1", "p2")}
    rates = (
        tools.policy.rates.get(fmt, {}) if isinstance(tools.policy.rates, dict) else {}
    )
    cols = columns(tools.groups)
    k1, kr = idx["p1"], idx[role]
    mine = game.states[role][kr]
    fld = R.field_from_timers(game.joined["p1"][k1], "p1")
    hidden = tools.hidden is not None
    if not hidden:
        ctx_all = damage_contexts(
            tag, log, game, sheets, dex, tools.calc, tools.store, tools.bring
        )
        view = dict(sheets)
        s1 = game.states["p1"][k1]
        sides = {
            "p1": [dict(m) for m in s1["our_pokemon"]],
            "p2": [dict(m) for m in s1["opp_pokemon"]],
        }
        rv_spreads, rv_dists = ctx_all["p1"][k1].spreads, ctx_all["p1"][k1].dists
        pol_spreads = spreads
        bw = A.BoardWP(
            tools.predict[fmt],
            game.states["p1"],
            k1,
            game.joined["p1"][k1],
            sheets,
            dex,
            table,
            tools.groups,
            ctx_all["p1"][k1],
            budget=tools.budget,
        )
        f = state_features(
            game.states[role],
            kr,
            role,
            game.joined[role][kr],
            sheets,
            dex,
            table,
            tools.groups,
            ctx_all[role][kr],
        )
        wp = float(tools.predict[fmt](np.array([[f[c] for c in cols]], np.float32))[0])
        theirs = None
    else:
        usage = tools.store.for_game(tag, log)
        sets = tools.hidden.for_game(tag, log)
        view, theirs = A.player_view(sheets, role, mine["opp_pokemon"], sets, dex)
        sides = {
            role: [dict(m) for m in mine["our_pokemon"]],
            other: [dict(m) for m in theirs],
        }
        sides = {"p1": sides["p1"], "p2": sides["p2"]}
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
        bw = A.BoardWP(
            predict,
            game.states[role],
            kr,
            game.joined[role][kr],
            pub,
            dex,
            table,
            tools.groups,
            context_for(kr, pub),
            budget=tools.budget,
            role=role,
            public=True,
        )
        f = state_features(
            [*game.states[role][:kr], blank_state(mine)],
            kr,
            role,
            game.joined[role][kr],
            pub,
            dex,
            table,
            tools.groups,
            context_for(kr, pub),
        )
        wp = float(predict(np.array([[f[c] for c in cols]], np.float32))[0])
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
        dists=rv_dists if tools.speed_beliefs or tools.spread_hits else None,
        spread_hits=tools.spread_hits,
        speed_beliefs=tools.speed_beliefs,
    )
    tv = A.TurnValues(rv, sides, fld, bw)
    full = {}
    for q in ("p1", "p2"):
        t = tt[q]
        if theirs is not None:  # the other's items as the player saw them
            t = (
                replace(t, ours=[dict(m) for m in theirs])
                if q == other
                else replace(t, theirs=[dict(m) for m in theirs])
            )
        feats = turn_options(
            t,
            timers[q].get(turn),
            view,
            pol_spreads,
            dex,
            tools.moves[fmt],
            rates,
            tools.calc,
            odds,
        )
        opts, chances = A.only_brought(
            *A.expand_pivots(
                {i: o for i, (o, _X) in feats.items()},
                {i: list(tools.policy.chances(X)) for i, (_o, X) in feats.items()},
            ),
            four[q],
        )
        full[q] = A.mixture({i: list(zip(opts[i], chances[i])) for i in opts})
    plain, kept = {}, 1.0
    for q in ("p1", "p2"):
        plain[q], k = A.likely(full[q], tools.top, tools.draws, f"{tag} {turn} {q}")
        if q == other:
            kept = k
    replies = A.strong_mixes(tv, plain, tools.strength)[other]
    choices, _ = A.trim(full[role], 1.0, tools.alternatives or 10)
    mine = A.strong_mixes(tv, plain, tools.strength)[role]
    tv.prepare(
        [
            (j, y) if role == "p1" else (y, j)
            for j, _p in [*choices, *mine]
            for y, _q in replies
        ]
    )
    value = tv.for_role(role)
    return Advice(
        tag,
        turn,
        role,
        wp,
        rank(value, choices, replies),
        sorted(replies, key=lambda x: -x[1]),
        kept,
        hidden,
        A.expected(value, mine, replies),
    )


def advice_text(
    adv: Advice, log: str, dex_moves: Mapping | None = None, top: int = 5
) -> str:
    """The advice in words."""
    from wpa.attribution import joint_json
    from wpa.replay import (
        HIDDEN_NOTE,
        move_names,
        pct,
        players,
        say_choice,
        sheet_names,
        shown,
    )

    sheets = sheet_names(log)
    names = move_names(log, dex_moves)
    who = players(log)
    other = "p2" if adv.role == "p1" else "p1"
    lines = [
        f"{who.get(adv.role, adv.role)} (you) vs {who.get(other, other)}.",
        f"Turn {adv.turn}. Your win chance now: {pct(adv.wp)}; after a typical "
        f"choice: {pct(adv.typical)}.",
        "",
    ]
    if adv.hidden:
        lines[-1:] = [HIDDEN_NOTE.split(" Team preview")[0], ""]
    lines.append(
        "Your likely choices, best first: your win chance after this turn, on "
        "average over their likely replies, and against a typical choice."
    )
    for n, (j, v, p) in enumerate(adv.choices[:top], 1):
        words = say_choice(joint_json(j), "turn", adv.role, sheets, names)
        lines.append(
            f"  {n}. {words}: {pct(v)} ({shown(adv.typical, v)} against a typical "
            f"choice); players choose it {pct(p)}"
        )
    lines += ["", "Their likeliest replies (the model's chances):"]
    for j, q in adv.replies[:top]:
        words = say_choice(joint_json(j), "turn", other, sheets, names)
        lines.append(f"  {words}: {pct(q)}")
    lines += [
        "",
        "The best here is the model's, against the replies it expects: a coaching "
        "number, not a solver's answer.",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    from wpa import attribution as A
    from wpa import replay as RP
    from wpa.bring import brought_from_log

    p = argparse.ArgumentParser(
        description="Your best choice at a turn's start, against their likely "
        "replies: a game so far, or a finished game at a turn you name."
    )
    p.add_argument("game", help="a replay link, or a saved replay or log")
    p.add_argument("--player", required=True, help="your name in the game")
    p.add_argument("--turn", type=int, default=None, help="the turn to advise on")
    p.add_argument("--top", type=int, default=5, help="how many choices to show")
    p.add_argument("--team", type=Path, default=None, help="your team paste")
    p.add_argument("--hidden", action="store_true", help="their sheet hidden")
    p.add_argument("--public-models", type=Path, default=Path("models_v4_preview"))
    p.add_argument("--models", type=Path, default=None)
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--dex-tables", type=Path, default=None)
    a = p.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    try:
        tag, full_log = RP.load(a.game)
        fmt = RP.format_for(tag, full_log)
        role = RP.side_of(full_log, a.player)
        team = a.team.read_text(encoding="utf-8") if a.team else None
        games, a.hidden = RP.prepare([(tag, full_log, fmt)], a.player, team, a.hidden)
        full_log = games[0][1]  # with the sheets put in, for a game that shows none
        log = up_to_turn(full_log, a.turn)
        if a.hidden and not (a.public_models / "regma").exists():
            raise ReplayError(
                "their sheet hidden needs the model trained that way, in "
                f"{a.public_models} (Runbook Section 23, step 3)"
            )
    except (ReplayError, OSError) as e:
        sys.exit(f"Sorry: {e}.")
    print("Thinking (about half a minute)...", flush=True)
    A._init(RP._options(a))
    # the four you brought, when the whole game shows them (you know them)
    seen = brought_from_log(full_log).get(role, set())
    own = seen if a.turn is not None and len(seen) >= 4 else None
    adv = advise(tag, log, fmt, A._W["tools"], role, own_four=own)
    dex_moves = A._W["tools"].dexes[fmt].moves
    print(advice_text(adv, log, dex_moves, a.top))


if __name__ == "__main__":
    main()
