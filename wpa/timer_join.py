"""Timers joined to stored states, from one player's side (Week 5 Task 3).

`wpa.timers.track_decisions` gives the timers in force at every decision point
a player has in `wpa_states/`, computed from the log before that point only.
This module turns them round to "ours" and "theirs" for the player whose file
it is, lines them up with the states in the file, and cross-checks them against
the conditions the states' own observations list.

Lining up is strict: the (turn, decision_index) of every non-terminal state must
match the decision points found in the log, one to one, or `align` returns None.
A mismatch is counted and reported; it is never patched over.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from wpa.timers import DecisionTimers, TimerRecord, iter_timer_file

Span = tuple[str, str, int, int]  # (effect id, target, fewest left, most left)
Count = tuple[str, str, int]  # (counter id, target, attempts so far)


@dataclass(frozen=True)
class JoinedTimers:
    """Timers at one decision, from the side of the player who decides.

    Side conditions carry the target "side"; effects on one Pokemon carry its
    identifier as the log names it ("p1a: Whimsicott").
    """

    ours: tuple[Span, ...] = ()
    theirs: tuple[Span, ...] = ()
    field: tuple[Span, ...] = ()
    our_counters: tuple[Count, ...] = ()
    their_counters: tuple[Count, ...] = ()
    # when in the turn the decision was taken (see DecisionTimers.moment)
    moment: str = ""

    def is_empty(self) -> bool:
        return not (
            self.ours
            or self.theirs
            or self.field
            or self.our_counters
            or self.their_counters
        )


def orient(decision: DecisionTimers, role: str) -> JoinedTimers:
    """Split a decision's timers into ours, theirs and the field, for `role`."""
    ours: list[Span] = []
    theirs: list[Span] = []
    field: list[Span] = []
    for eid, target, lo, hi in decision.timers:
        if target == "field":
            field.append((eid, "field", lo, hi))
        elif target in ("p1", "p2"):
            (ours if target == role else theirs).append((eid, "side", lo, hi))
        else:
            (ours if target[:2] == role else theirs).append((eid, target, lo, hi))
    our_c = tuple(c for c in decision.counters if c[1][:2] == role)
    their_c = tuple(c for c in decision.counters if c[1][:2] != role)
    return JoinedTimers(
        tuple(ours), tuple(theirs), tuple(field), our_c, their_c, decision.moment
    )


def align(
    states: Sequence[dict], decisions: Sequence[DecisionTimers], role: str
) -> list[JoinedTimers | None] | None:
    """One JoinedTimers per stored state (None for the terminal one).

    Returns None when the states' (turn, decision_index) sequence does not
    match the decision points found in the log.
    """
    if not states or states[-1].get("outcome") is None:
        return None
    wanted = [(s["turn"], s["decision_index"]) for s in states[:-1]]
    found = [(d.turn, d.decision_index) for d in decisions]
    if wanted != found:
        return None
    return [orient(d, role) for d in decisions] + [None]


class TimerIndex:
    """The side file, loaded for look-ups by game."""

    def __init__(self, records: dict[str, TimerRecord]) -> None:
        self.records = records

    @classmethod
    def load(cls, path: Path | str) -> TimerIndex:
        return cls(dict(iter_timer_file(path)))

    def for_file(
        self, tag: str, role: str, states: Sequence[dict]
    ) -> list[JoinedTimers | None] | None:
        rec = self.records.get(tag)
        if rec is None or role not in rec.decisions:
            return None
        return align(states, rec.decisions[role], role)


# --------------------------------------------------------------------------
# Cross-check against the observations' own context
# --------------------------------------------------------------------------


def _id(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _listed(obs: dict, role: str) -> set[tuple[str, str]]:
    """(side, effect id) for every condition an observation lists as in force."""
    out: set[tuple[str, str]] = set()
    if obs.get("weather"):
        out.add(("field", _id(obs["weather"])))
    for name in obs.get("fields") or ():
        out.add(("field", _id(name)))
    for entry in obs.get("side_conditions") or ():
        side, _, name = entry.partition(":")
        out.add(("ours" if side == role else "theirs", _id(name)))
    return out


def _present(j: JoinedTimers) -> set[tuple[str, str]]:
    return (
        {("ours", s[0]) for s in j.ours if s[1] == "side"}
        | {("theirs", s[0]) for s in j.theirs if s[1] == "side"}
        | {("field", s[0]) for s in j.field}
    )


def cross_check(
    states: Sequence[dict],
    joined: Sequence[JoinedTimers | None],
    role: str,
    timed_ids: set[str],
    starts: set[tuple[str, str, int]] | None = None,
    ends: set[tuple[str, str, int]] | None = None,
) -> Counter:
    """Compare turn-start timers with what the turn's first observation lists.

    The observations carry their own record of the conditions in force, kept by
    separate code (`wpa.observations`). For every turn N that has both a
    decision at the start of the turn and at least one observation, the timers
    at that decision are compared with the conditions listed by the turn's first
    observation. Counted once per (turn, side, effect), for effects with a
    duration only (hazards such as Stealth Rock have none):

    * ``(id, "agree")``: listed, and a timer shows it;
    * ``(id, "started_this_turn")``: listed but not at the turn's start, and the
      log shows it starting in turn N (a switch-in's weather before the first
      move, for example). ``starts`` holds (p1/p2/field, id, start turn);
    * ``(id, "listed_not_at_turn_start")``: listed, no timer, no start this turn;
    * ``(id, "ended_this_turn")``: a timer at the turn's start that the first
      observation does not list, and the log shows it ending in turn N (weather
      replaced by a switch-in before the first move, for example). ``ends``
      holds (p1/p2/field, id, end turn);
    * ``(id, "timer_not_listed")``: a timer at the turn's start that the turn's
      first observation does not list, with no end this turn.
    """
    other = "p2" if role == "p1" else "p1"
    absolute = {"ours": role, "theirs": other, "field": "field"}
    starts = starts or set()
    ends = ends or set()
    turn_start: dict[int, JoinedTimers] = {}
    for s, j in zip(states, joined):
        if j is not None and j.moment == "turn_start":
            turn_start.setdefault(s["turn"], j)
    first_obs: dict[int, dict] = {}
    for s in states:
        for o in s.get("observations") or ():
            first_obs.setdefault(o["turn"], o)
    counts: Counter = Counter()
    for turn, j in turn_start.items():
        if turn not in first_obs:
            continue
        listed = {x for x in _listed(first_obs[turn], role) if x[1] in timed_ids}
        present = _present(j)
        for side, eid in listed:
            if (side, eid) in present:
                counts[(eid, "agree")] += 1
            elif (absolute[side], eid, turn) in starts:
                counts[(eid, "started_this_turn")] += 1
            else:
                counts[(eid, "listed_not_at_turn_start")] += 1
        for side, eid in present - listed:
            if (absolute[side], eid, turn) in ends:
                counts[(eid, "ended_this_turn")] += 1
            else:
                counts[(eid, "timer_not_listed")] += 1
    return counts


# --------------------------------------------------------------------------
# Checking a sample of the real data
# --------------------------------------------------------------------------


def _format_of_tag(tag: str) -> str:
    kind = tag.split("-", 1)[0].removeprefix("gen9championsvgc2026")
    return kind.removesuffix("bo3")


class CheckReport:
    """Alignment and cross-check counts, per format."""

    def __init__(self) -> None:
        self.files: Counter = Counter()
        self.aligned: Counter = Counter()
        self.decisions: Counter = Counter()
        self.with_timer: Counter = Counter()
        self.counts: dict[str, Counter] = {}
        self.misaligned_examples: list[str] = []

    def add(
        self, tag: str, log: str, states_by_role: dict[str, list[dict]], table
    ) -> None:
        from wpa.timers import track_decisions, track_game

        fmt = _format_of_tag(tag)
        decisions = track_decisions(log, table)
        game = track_game(log, table)
        starts = {
            ("field" if tm.target == "field" else tm.target[:2], tm.id, tm.start_turn)
            for tm in game.timers
        }
        ends = {
            ("field" if tm.target == "field" else tm.target[:2], tm.id, tm.end_turn)
            for tm in game.timers
            if tm.end_turn is not None
        }
        timed = set(table.timed)
        for role, states in states_by_role.items():
            self.files[fmt] += 1
            joined = align(states, decisions[role], role)
            if joined is None:
                if len(self.misaligned_examples) < 10:
                    self.misaligned_examples.append(f"{tag}-{role}")
                continue
            self.aligned[fmt] += 1
            for j in joined[:-1]:
                self.decisions[fmt] += 1
                self.with_timer[fmt] += j is not None and not j.is_empty()
            if role == "p1":  # observations are the same in both files
                self.counts.setdefault(fmt, Counter()).update(
                    cross_check(states, joined, role, timed, starts, ends)
                )

    def describe(self) -> str:
        out = ["=== timer join check ==="]
        for fmt in sorted(self.files):
            n, a = self.files[fmt], self.aligned[fmt]
            d = self.decisions[fmt] or 1
            out.append(
                f"{fmt}: aligned {a} of {n} state files ({a / n:.2%}); "
                f"{self.decisions[fmt]} decision points, {self.with_timer[fmt]} "
                f"({self.with_timer[fmt] / d:.1%}) with at least one timer or counter"
            )
            c = self.counts.get(fmt, Counter())
            ids = sorted({k[0] for k in c})
            if ids:
                out.append(
                    "  effect: agree / started this turn / ended this turn / "
                    "listed, no timer / timer, not listed"
                )
            for eid in ids:
                agree = c[(eid, "agree")]
                started = c[(eid, "started_this_turn")]
                ended = c[(eid, "ended_this_turn")]
                miss = c[(eid, "listed_not_at_turn_start")]
                extra = c[(eid, "timer_not_listed")]
                judged = (agree + started + ended + miss + extra) or 1
                out.append(
                    f"  {eid}: {agree} / {started} / {ended} / {miss} / {extra} "
                    f"(unexplained {(miss + extra) / judged:.1%})"
                )
        if self.misaligned_examples:
            out.append("misaligned examples: " + ", ".join(self.misaligned_examples))
        return "\n".join(out) + "\n"


def main() -> None:
    import argparse
    import json

    from wpa.durations import load_all
    from wpa.state_timing import in_sample
    from wpa.timers import iter_log_file

    parser = argparse.ArgumentParser(description="Check the timer join (Task 3).")
    parser.add_argument("--logs", type=Path, default=Path("battle_logs"))
    parser.add_argument("--states", type=Path, default=Path("wpa_states"))
    parser.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    parser.add_argument("--one-in", type=int, default=100)
    parser.add_argument("--files", nargs="*", help="only these log files (names)")
    args = parser.parse_args()
    tables = load_all(args.showdown)
    report = CheckReport()
    paths = sorted(args.logs.glob("logs_*.json"))
    if args.files:
        paths = [p for p in paths if p.name in args.files]
    for path in paths:
        for tag, (_ts, log) in iter_log_file(path):
            if not in_sample(f"{tag}-p1.json", args.one_in):
                continue
            states = {}
            for role in ("p1", "p2"):
                f = args.states / f"{tag}-{role}.json"
                if f.exists():
                    states[role] = json.loads(f.read_text(encoding="utf-8"))
            if states:
                report.add(tag, log, states, tables[_format_of_tag(tag)])
    print(report.describe())


if __name__ == "__main__":
    main()
