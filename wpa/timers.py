"""Replay battle logs against the duration table (Week 4 Task 7).

``wpa.durations`` says how long each timed effect should last, from the
Showdown source. This module reads the logs and answers two questions.

1. *Is the table right?* Every effect that starts and later ends in a log is
   compared with the length the table predicts for it. The end event is used
   for this comparison and nothing else.
2. *What would a decision point know?* ``GameTimers.snapshots`` lists, at the
   start of each turn, the timers in force and how many turns each has left.
   That is computed from the start turn and the table alone. A test proves the
   result does not change when the end event is moved or deleted.

It also counts how many attempts a sleep, freeze or confusion lasted, to
check the distributions in the table.

Run as ``python -m wpa.timers --logs battle_logs`` (several minutes on the
full corpus); ``--shard i/n`` and ``--out`` split a run into parts and
``--merge`` joins them.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from wpa.durations import (
    ACTION,
    AFTER_RESIDUAL,
    CountedEffect,
    Durations,
    TimedEffect,
    hazards,
    load_all,
    scheduled_end_turn,
    turns_remaining,
)

# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Timer:
    """One timed effect, from its start to whatever ended it.

    This is also the shape proposed for ``BattleState`` (docs/TIMERS.md).
    """

    id: str
    kind: str  # the move field that attaches it
    target: str  # "p1" / "p2" for a side, "field", or the Pokemon's ident
    source: str | None
    start_turn: int
    start_phase: str
    durations: tuple[int, ...]  # possible lengths given what is known at the start
    extended_by: tuple[
        str, ...
    ]  # "item:lightclay", "ability:persistent", "ordering:+1"
    end_turn: int | None
    end_reason: str  # ended, removed, toggled, switched, fainted, replaced, game_over
    end_detail: str

    @property
    def duration(self) -> int | None:
        return self.durations[0] if len(self.durations) == 1 else None

    @property
    def expected_ends(self) -> tuple[int, ...]:
        return tuple(
            scheduled_end_turn(self.start_turn, self.start_phase, d)
            for d in self.durations
        )

    @property
    def expected_end(self) -> int | None:
        return self.expected_ends[0] if len(self.expected_ends) == 1 else None


@dataclass(frozen=True)
class CounterObservation:
    id: str  # slp, frz or confusion
    target: str
    attempts: int  # attempts the status prevented (sleep, freeze) or activations
    completed: bool  # ended by its own countdown, not removed from outside
    early_bird: bool
    variant: str | None  # "rest", "axekick"


@dataclass
class GameTimers:
    timers: list[Timer] = field(default_factory=list)
    counters: list[CounterObservation] = field(default_factory=list)
    # turn -> ((id, target, turns remaining), ...) as known at the start of that turn
    snapshots: dict[int, tuple[tuple[str, str, int], ...]] = field(default_factory=dict)
    # turn -> ((id, target, fewest turns left, most turns left), ...); the two
    # differ only for random lengths (trap moves, rampage moves)
    ranges: dict[int, tuple[tuple[str, str, int, int], ...]] = field(
        default_factory=dict
    )
    # turn -> ((counter id, target, attempts prevented so far), ...)
    counter_state: dict[int, tuple[tuple[str, str, int], ...]] = field(
        default_factory=dict
    )


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _strip(name: str) -> str:
    return re.sub(r"^(move|ability|item): ", "", name)


def classify(timer: Timer) -> str:
    """match, explained, unexplained, or censored (no end event to judge)."""
    if timer.end_turn is None or timer.end_reason in (
        "switched",
        "fainted",
        "replaced",
        "game_over",
    ):
        return "censored"
    if timer.end_turn in timer.expected_ends:
        return "match"
    if timer.end_reason in ("removed", "toggled"):
        return "explained"
    return "unexplained"


# --------------------------------------------------------------------------
# Walking one log
# --------------------------------------------------------------------------

_ATTACH_BY_EVENT = {
    "sidestart": ("sideCondition",),
    "fieldstart": ("pseudoWeather", "terrain"),
    "weather": ("weather",),
    "start": ("volatileStatus", "slotCondition"),
}
_ALIASES = {"futuresight": "futuremove", "doomdesire": "futuremove"}
# effects Showdown attaches in a move's code, so the durations table has no
# attachment for them (Week 10: Perish Song's count never reached the timers)
_ATTACH = {"perishsong": "volatileStatus"}
# How the order of play inside the turn changes a length. The signs come from
# the table; wpa.durations has the guard text, tests/test_durations.py pins them.
_ORDERING = {"encore", "taunt", "disable"}


@dataclass
class _Active:
    effect: TimedEffect
    key: tuple[str, ...]
    target: str  # as shown
    target_key: str  # the Pokemon's key for volatiles, else the same as target
    source: str | None
    start_turn: int
    start_phase: str
    durations: tuple[int, ...]
    extended_by: tuple[str, ...]


@dataclass
class _Counter:
    id: str
    target: str
    early_bird: bool
    variant: str | None
    attempts: int = 0


def _mon_key(ident: str) -> str:
    side = ident[:2]
    name = ident.split(": ", 1)[1] if ": " in ident else ident
    return f"{side}:{name}"


# Protocol lines that do not move the battle on: a decision right after |turn|
# followed only by these is still at the start of the turn.
_QUIET = {
    "",
    "t:",
    "inactive",
    "inactiveoff",
    "c",
    "c:",
    "j",
    "J",
    "l",
    "L",
    "n",
    "N",
    "raw",
    "html",
    "uhtml",
    "uhtmlchange",
    "-message",
    "-hint",
    "chat",
    "timer",
    "message",
}


def _moment(walker: "_Walker") -> str:
    if walker.turn == 0:
        return "preview"
    if walker.phase == AFTER_RESIDUAL:
        return "after_turn"
    return "turn_start" if walker.at_turn_start else "mid_turn"


class _Walker:
    def __init__(self, table: Durations) -> None:
        self.table = table
        self.turn = 0
        self.phase = ACTION
        self.moved: set[str] = set()
        self.entered: set[str] = set()
        self.sheet: dict[str, dict[str, tuple[str, str]]] = {"p1": {}, "p2": {}}
        self.species: dict[str, str] = {}
        self.items: dict[str, str | None] = {}
        self.abilities: dict[str, str] = {}
        self.occupant: dict[str, str] = {}
        self.active: dict[tuple[str, ...], _Active] = {}
        self.weather: str | None = None
        self.last_move: tuple[str, str] | None = None  # (mon key, move id)
        self.line = 0
        self.lines: list[str] = []
        self.counters: dict[tuple[str, str], _Counter] = {}
        self.pending_field_end: int | None = None
        # nothing but chat or timer lines since the last |turn| line
        self.at_turn_start = False
        self.out = GameTimers()

    # --- bookkeeping -----------------------------------------------------

    def close(self, key: tuple[str, ...], reason: str, detail: str = "") -> None:
        a = self.active.pop(key, None)
        if a is None:
            return
        self.out.timers.append(
            Timer(
                a.effect.id,
                a.effect.attach or "",
                a.target,
                a.source,
                a.start_turn,
                a.start_phase,
                a.durations,
                a.extended_by,
                None if reason == "game_over" else self.turn,
                reason,
                detail,
            )
        )

    def close_where(self, pred, reason: str) -> None:
        for key in [k for k, a in self.active.items() if pred(a)]:
            self.close(key, reason)

    def snapshot(self) -> None:
        rows = []
        spans = []
        for a in self.active.values():
            left = [
                turns_remaining(self.turn, a.start_turn, a.start_phase, d)
                for d in a.durations
            ]
            if min(left) > 0:
                rows.append((a.effect.id, a.target, min(left)))
                spans.append((a.effect.id, a.target, min(left), max(left)))
        self.out.snapshots[self.turn] = tuple(sorted(rows))
        self.out.ranges[self.turn] = tuple(sorted(spans))
        self.out.counter_state[self.turn] = tuple(
            sorted((c.id, c.target, c.attempts) for c in self.counters.values())
        )

    def now(
        self,
    ) -> tuple[tuple[tuple[str, str, int, int], ...], tuple[tuple[str, str, int], ...]]:
        """Timers and counters at this point of the log, for a decision here.

        After the turn's residual (`|upkeep|`) the turn is over, so turns left
        are counted from the next turn. An effect that is still active (its end
        message has not been broadcast) has at least one turn left, which
        settles a random length that has run past its shortest value.
        """
        current = self.turn + (1 if self.phase == AFTER_RESIDUAL else 0)
        spans = []
        for a in self.active.values():
            left = [
                turns_remaining(current, a.start_turn, a.start_phase, d)
                for d in a.durations
            ]
            if max(left) > 0:
                spans.append((a.effect.id, a.target, max(1, min(left)), max(left)))
        counters = tuple(
            sorted((c.id, c.target, c.attempts) for c in self.counters.values())
        )
        return tuple(sorted(spans)), counters

    def source_of(self, effect_id: str, fields: list[str]) -> str | None:
        for f in fields:
            if f.startswith("[of] "):
                return _mon_key(f[5:])
        if (
            self.last_move is not None
            and _ALIASES.get(self.last_move[1], self.last_move[1]) == effect_id
        ):
            return self.last_move[0]
        return None

    def lengths(
        self,
        effect: TimedEffect,
        source: str | None,
        fields: list[str],
        target_key: str,
    ):
        """Possible lengths of this effect, given what is known right now."""
        base = effect.base
        durations: list[int] = []
        extended: list[str] = []
        if effect.random_range is not None:
            durations = list(range(effect.random_range[0], effect.random_range[1]))
        elif base is not None:
            durations = [base]
        for m in effect.modifiers:
            holds = False
            if m.kind == "item" and source is not None:
                holds = self.items.get(source) == m.name
            elif m.kind == "ability" and source is not None:
                holds = self.abilities.get(source) == m.name
            elif m.kind == "trigger":
                holds = any(f.endswith(f"move: {m.name}") for f in fields) or (
                    self.last_move is not None and self.last_move[1] == to_id(m.name)
                )
            if holds:
                durations = [m.duration]
                extended.append(f"{m.kind}:{m.name}")
                break
        if effect.adjustments:
            if effect.id not in _ORDERING:
                raise ValueError(f"no ordering rule for {effect.id!r}")
            delta = sum(a.delta for a in effect.adjustments)
            moved = target_key in self.moved
            applies = {
                "encore": moved,
                "taunt": moved and target_key not in self.entered,
                "disable": (not moved) or any("Cursed Body" in f for f in fields),
            }[effect.id]
            if applies:
                durations = [d + delta for d in durations]
                extended.append(f"ordering:{delta:+d}")
        return tuple(durations), tuple(extended)

    def start(
        self, event: str, name: str, display: str, target_key: str, fields: list[str]
    ) -> None:
        effect_id = _ALIASES.get(to_id(_strip(name)), to_id(_strip(name)))
        effect = self.table.timed.get(effect_id)
        if effect is None:
            return
        attach = effect.attach or _ATTACH.get(effect_id)
        if attach not in _ATTACH_BY_EVENT[event]:
            return
        if attach == "sideCondition":
            key = ("side", effect_id, display)
        elif attach == "weather":
            key = ("weather", effect_id)
        elif attach in ("pseudoWeather", "terrain"):
            key = ("field", effect_id)
        elif attach == "slotCondition":
            key = ("slot", effect_id, target_key[:2])
        else:
            key = ("mon", effect_id, target_key)
        if key in self.active:
            return
        source = self.source_of(effect_id, fields)
        durations, extended = self.lengths(effect, source, fields, target_key)
        if not durations:
            return
        self.active[key] = _Active(
            effect,
            key,
            display,
            target_key,
            source,
            self.turn,
            self.phase,
            durations,
            extended,
        )

    # --- the log ---------------------------------------------------------

    def read_sheet(self, parts: list[str]) -> None:
        side = parts[2]
        packed = "|".join(parts[3:])
        for mon in packed.split("]"):
            f = mon.split("|")
            if len(f) < 4:
                continue
            species = f[1] or f[0]
            self.sheet[side][to_id(species)] = (to_id(f[2]), to_id(f[3]))

    def enter(self, parts: list[str]) -> None:
        ident = parts[2]
        slot, key = ident[:3], _mon_key(ident)
        previous = self.occupant.get(slot)
        if previous is not None and previous != key:
            self.close_where(
                lambda a: a.target_key == previous and a.key[0] == "mon", "switched"
            )
            self._drop_counters(previous, "confusion")
        if previous is not None and previous == key:
            pass
        self.occupant[slot] = key
        self.entered.add(key)
        species = to_id(parts[3].split(",")[0])
        self.species[key] = species
        item, ability = self.sheet[ident[:2]].get(species, (None, ""))
        self.items[key] = item
        self.abilities[key] = ability

    def _drop_counters(self, mon_key: str, only: str | None = None) -> None:
        for k in [
            k
            for k in self.counters
            if k[1] == mon_key and (only is None or k[0] == only)
        ]:
            self._finish_counter(k, completed=False)

    def _finish_counter(self, k: tuple[str, str], completed: bool) -> None:
        c = self.counters.pop(k)
        self.out.counters.append(
            CounterObservation(
                c.id, c.target, c.attempts, completed, c.early_bird, c.variant
            )
        )

    def run(self, log: str) -> GameTimers:
        for line in log.split("\n"):
            self.feed(line)
        return self.result()

    def feed(self, line: str) -> None:
        """Take the next line of the battle, as the live path does.

        A field ending is held back one line, because whether it was *replaced*
        (another terrain starts straight after) is only known from the next line.
        Everything else is handled at once, so a decision point sees the timers
        as of the `|turn|` line it follows.
        """
        self.lines.append(line)
        index = len(self.lines) - 1
        if self.pending_field_end is not None:
            held = self.pending_field_end
            self.pending_field_end = None
            self.handle(held, line)
        if line.startswith("|-fieldend|"):
            self.pending_field_end = index
            return
        self.handle(index, None)

    def flush(self) -> None:
        if self.pending_field_end is not None:
            held = self.pending_field_end
            self.pending_field_end = None
            self.handle(held, None)

    def result(self) -> GameTimers:
        self.flush()
        self.finish("game_over")
        for k in list(self.counters):
            self._finish_counter(k, completed=False)
        return self.out

    def handle(self, i: int, nxt: str | None) -> None:
        line = self.lines[i]
        self.line = i
        if not line.startswith("|"):
            return
        p = line.split("|")
        if len(p) < 2:
            return
        t = p[1]
        if t not in _QUIET:
            self.at_turn_start = t == "turn"
        if t == "showteam" and len(p) > 3:
            self.read_sheet(p)
        elif t in ("switch", "drag") and len(p) > 3:
            self.enter(p)
        elif t == "turn" and len(p) > 2:
            self.turn = int(p[2])
            self.phase = ACTION
            self.moved.clear()
            self.entered.clear()
            self.snapshot()
        elif t == "upkeep":
            self.phase = AFTER_RESIDUAL
        elif t == "move" and len(p) > 3:
            key = _mon_key(p[2])
            self.moved.add(key)
            self.last_move = (key, to_id(p[3]))
            if to_id(p[3]) == "wish":
                self.start("start", "Wish", p[2], key, p[4:])
        elif t == "cant" and len(p) > 3:
            self.moved.add(_mon_key(p[2]))
            c = self.counters.get((p[3], _mon_key(p[2])))
            if c is not None and p[3] in ("slp", "frz"):
                c.attempts += 1
        elif t == "faint" and len(p) > 2:
            key = _mon_key(p[2])
            self.close_where(
                lambda a: a.target_key == key and a.key[0] == "mon", "fainted"
            )
            self._drop_counters(key)
        elif t == "-sidestart" and len(p) > 3:
            self.start("sidestart", p[3], p[2].split(":")[0], p[2].split(":")[0], p[4:])
        elif t == "-sideend" and len(p) > 3:
            self.end_event(("side", to_id(_strip(p[3])), p[2].split(":")[0]), p[4:])
        elif t == "-fieldstart" and len(p) > 2:
            self.start("fieldstart", p[2], "field", "field", p[3:])
        elif t == "-fieldend" and len(p) > 2:
            fid = to_id(_strip(p[2]))
            after = nxt.split("|") if nxt is not None else []
            replaced = (
                len(after) > 2
                and after[1] == "-fieldstart"
                and to_id(_strip(after[2])) != fid
            )
            self.end_event(("field", fid), p[3:], replaced=replaced)
        elif t == "-weather" and len(p) > 2:
            self.weather_event(p)
        elif t == "-start" and len(p) > 3:
            self.start_event(p)
        elif t == "-end" and len(p) > 3:
            self.end_volatile(p)
        elif t == "-activate" and len(p) > 3 and p[3] == "confusion":
            c = self.counters.get(("confusion", _mon_key(p[2])))
            if c is not None:
                c.attempts += 1
        elif t == "-status" and len(p) > 3:
            self.status_event(p)
        elif t == "-curestatus" and len(p) > 3:
            k = (p[3], _mon_key(p[2]))
            if k in self.counters:
                natural = "[msg]" in p[4:] and not any(
                    f.startswith("[from]") for f in p[4:]
                )
                self._finish_counter(k, completed=natural)
        elif t == "-enditem" and len(p) > 2:
            self.items[_mon_key(p[2])] = None
        elif t == "-heal" and any(f == "[from] move: Wish" for f in p[4:]):
            self.end_slot("wish", p[2][:2])
        elif t == "win":
            self.finish("game_over")

    def finish(self, reason: str) -> None:
        for key in list(self.active):
            self.close(key, reason)

    # --- events ----------------------------------------------------------

    def context_cause(self, effect_id: str) -> str:
        """What the log shows just before an end event that names no cause.

        Looks back up to ten lines, but never past the blank line that separates
        the actions of a turn from its residual. Other lines can sit between a
        removing move and the end (Defiant's boost after Defog, damage lines
        after Steel Roller, Screen Cleaner removing several sides at once). A
        natural end comes in the residual, after a blank line, so nothing is
        found for it.
        """
        for j in range(self.line - 1, max(-1, self.line - 11), -1):
            p = self.lines[j].split("|")
            if len(p) < 2 or p[1] in ("", "turn", "upkeep"):
                break
            if p[1] == "move" and len(p) > 3 and to_id(p[3]) != effect_id:
                return f"move: {p[3]}"
            if (
                p[1] == "-activate"
                and len(p) > 3
                and p[3].startswith(("ability: ", "move: "))
            ):
                return p[3]
            if p[1] == "-enditem" and len(p) > 3 and p[3] == "Mental Herb":
                return "item: Mental Herb"
        return ""

    def end_event(
        self, key: tuple[str, ...], fields: list[str], replaced: bool = False
    ) -> None:
        if key not in self.active:
            return
        cause = next((f[7:] for f in fields if f.startswith("[from] ")), "")
        if not cause and not replaced:
            cause = self.context_cause(key[1])
        if replaced:
            self.close(key, "replaced", cause)
            return
        name = key[1]
        moved_by = self.last_move
        toggled = key[0] == "field" and moved_by is not None and moved_by[1] == name
        if toggled:
            self.close(key, "toggled", cause)
        elif cause:
            self.close(key, "removed", cause)
        else:
            self.close(key, "ended", cause)

    def weather_event(self, p: list[str]) -> None:
        if len(p) > 3 and p[3] == "[upkeep]":
            return
        name = p[2]
        if name == "none":
            if self.weather is not None:
                self.close(("weather", self.weather), "ended")
            self.weather = None
            return
        wid = to_id(name)
        if self.weather is not None and self.weather != wid:
            self.close(("weather", self.weather), "replaced")
        if self.weather != wid:
            fields = p[3:]
            self.start("weather", name, "field", "field", fields)
        self.weather = wid

    def start_event(self, p: list[str]) -> None:
        ident, name = p[2], _strip(p[3])
        key = _mon_key(ident)
        perish = re.fullmatch(r"perish(\d)", name)
        if perish:
            if perish.group(1) == "3":
                self.start("start", "Perish Song", ident, key, p[4:])
            elif perish.group(1) == "0":
                self.end_event(("mon", "perishsong", key), [])
            return
        if name == "confusion":
            variant = (
                "axekick" if self.last_move and self.last_move[1] == "axekick" else None
            )
            self.counters[("confusion", key)] = _Counter(
                "confusion", ident, False, variant
            )
            return
        self.start("start", name, ident, key, p[4:])

    def end_volatile(self, p: list[str]) -> None:
        ident, name = p[2], _strip(p[3])
        key = _mon_key(ident)
        if name == "confusion":
            k = ("confusion", key)
            if k in self.counters:
                self._finish_counter(k, completed=len(p) == 4)
            return
        effect_id = _ALIASES.get(to_id(name), to_id(name))
        effect = self.table.timed.get(effect_id)
        if effect is not None and effect.attach == "slotCondition":
            self.end_slot(effect_id, "p2" if ident[:2] == "p1" else "p1")
            return
        self.end_event(("mon", effect_id, key), p[4:])

    def end_slot(self, effect_id: str, source_side: str) -> None:
        key = ("slot", effect_id, source_side)
        if key in self.active:
            self.close(key, "ended")

    def status_event(self, p: list[str]) -> None:
        status = p[3]
        if status not in ("slp", "frz"):
            return
        key = _mon_key(p[2])
        variant = "rest" if "[from] move: Rest" in p[4:] else None
        self.counters[(status, key)] = _Counter(
            status, p[2], self.abilities.get(key) == "earlybird", variant
        )


def track_game(log: str, table: Durations) -> GameTimers:
    """Replay one battle log: every timed effect, counted status, and snapshot."""
    return _Walker(table).run(log)


class TimerTracker:
    """The same tracker, fed one protocol line at a time (the live path).

    ``feed`` takes the lines of the battle in order, as they arrive. After the
    ``|turn|N`` line, ``current()`` is what a decision at turn N may know: built
    from the start turns and the duration table only. ``result()`` ends the game
    and gives exactly what ``track_game`` gives for the same lines.
    """

    def __init__(self, table: Durations) -> None:
        self._walker = _Walker(table)

    def feed(self, line: str) -> None:
        self._walker.feed(line)

    def feed_text(self, text: str) -> None:
        for line in text.split("\n"):
            self._walker.feed(line)

    def current(self) -> tuple[tuple[str, str, int], ...]:
        """(effect id, target, turns left counting this turn), as of the last turn."""
        w = self._walker
        return w.out.snapshots.get(w.turn, ())

    def current_ranges(self) -> tuple[tuple[str, str, int, int], ...]:
        w = self._walker
        return w.out.ranges.get(w.turn, ())

    def current_counters(self) -> tuple[tuple[str, str, int], ...]:
        w = self._walker
        return w.out.counter_state.get(w.turn, ())

    def result(self) -> GameTimers:
        return self._walker.result()


@dataclass(frozen=True)
class DecisionTimers:
    """Timers in force at one stored decision point of one player."""

    turn: int
    decision_index: int
    # (effect id, target, fewest turns left, most turns left)
    timers: tuple[tuple[str, str, int, int], ...] = ()
    # (counter id, target, attempts prevented so far)
    counters: tuple[tuple[str, str, int], ...] = ()
    # preview, turn_start, mid_turn (a switch during the turn, such as after
    # U-turn) or after_turn (a replacement after the turn's residual)
    moment: str = "turn_start"


def _acts(lines: list[str], role: str) -> tuple[bool, bool]:
    """Whether each of the player's two slots acts in this block of the log.

    Mirrors `vgc_bench.logs2trajs.LogReader.get_order`: a slot acts when it has
    a move line (not one called by another effect, `[from]`), or a switch or
    drag line; a `|swap|` line sends the search to the other slot.
    """
    acted = []
    for start in ("a", "b"):
        slot = start
        found = False
        for line in lines:
            if line.startswith(f"|move|{role}{slot}: ") and "[from]" not in line:
                found = True
            elif line.startswith((f"|switch|{role}{slot}: ", f"|drag|{role}{slot}: ")):
                found = True
            elif line.startswith(f"|swap|{role}{slot}: "):
                slot = "b" if slot == "a" else "a"
        acted.append(found)
    return acted[0], acted[1]


def track_decisions(log: str, table: Durations) -> dict[str, list[DecisionTimers]]:
    """Timers at every decision point stored for each player, in stored order.

    Reproduces where `vgc_bench.logs2trajs.LogReader.follow_log` takes its
    snapshots, so the result lines up one to one with the files in
    `wpa_states/` (checked by `wpa.timer_join.align`):

    * the log is cut into blocks at its blank `|` lines;
    * block 1 is team preview: a snapshot for both players (turn 0);
    * every later block with a move or switch line is a snapshot, taken before
      the block, for each player who acts in it, unless one of the player's
      slots did nothing and one of their Pokemon fainted in the block
      (`LogReader.choose_move` skips those);
    * a second turn-0 snapshot is added when both of a player's back-line
      Pokemon appear during the game.

    The timers come from the log before the snapshot only: nothing after it is
    read to compute them (tested).
    """
    roles = ("p1", "p2")
    walker = _Walker(table)
    raw: dict[str, list[tuple]] = {r: [] for r in roles}
    leads: dict[str, set[str]] = {r: set() for r in roles}
    seen: dict[str, set[str]] = {r: set() for r in roles}
    for i, block in enumerate(log.split("\n|\n")):
        if i > 0:
            walker.feed("|")
        lines = block.split("\n")
        if i == 1:
            snap = walker.now()
            for r in roles:
                raw[r].append((walker.turn, *snap, _moment(walker)))
        elif i >= 2 and ("|switch|" in block or "|move|" in block):
            snap = None
            for r in roles:
                a, b = _acts(lines, r)
                if (a and b) or ((a or b) and f"|faint|{r}" not in block):
                    snap = snap or walker.now()
                    raw[r].append((walker.turn, *snap, _moment(walker)))
        for line in lines:
            for r in roles:
                if line.startswith((f"|switch|{r}", f"|drag|{r}")):
                    name = line.split("|")[2].split(": ", 1)[-1]
                    seen[r].add(name)
                    if i == 1:
                        leads[r].add(name)
            walker.feed(line)
    out: dict[str, list[DecisionTimers]] = {}
    for r in roles:
        rows = raw[r]
        if rows and len(seen[r] - leads[r]) > 1:
            rows.insert(1, rows[0])
        decisions = []
        last_turn, index = None, 0
        for turn, timers, counters, moment in rows:
            index = index + 1 if turn == last_turn else 0
            last_turn = turn
            decisions.append(DecisionTimers(turn, index, timers, counters, moment))
        out[r] = decisions
    return out


# --------------------------------------------------------------------------
# The side file: timers per game and turn, written once, read in training
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnTimers:
    # (effect id, target, fewest turns left, most turns left)
    timers: tuple[tuple[str, str, int, int], ...] = ()
    # (counter id, target, attempts prevented so far)
    counters: tuple[tuple[str, str, int], ...] = ()


@dataclass(frozen=True)
class TimerRecord:
    format: str
    turns: dict[int, TurnTimers]
    # role -> timers at each stored decision point, in stored order
    decisions: dict[str, list[DecisionTimers]] = field(default_factory=dict)

    def at(self, turn: int) -> TurnTimers:
        return self.turns.get(turn, TurnTimers())


def _record_of(game: GameTimers) -> dict[int, TurnTimers]:
    out: dict[int, TurnTimers] = {}
    for turn in sorted(game.ranges):
        row = TurnTimers(game.ranges[turn], game.counter_state.get(turn, ()))
        if row.timers or row.counters:
            out[turn] = row
    return out


def write_timer_file(path: Path | str, games: Iterable[tuple]) -> int:
    """Write one JSON line per game: only the facts known at each turn.

    Each item is (tag, format, GameTimers) or (tag, format, GameTimers,
    decisions), where decisions is `track_decisions`' result. No end turn and no
    end reason is written, so nothing in the file can leak the future into a
    decision point.
    """
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for item in games:
            tag, fmt, game = item[0], item[1], item[2]
            decisions = item[3] if len(item) > 3 else {}
            turns = {
                str(t): {
                    "t": [list(r) for r in row.timers],
                    "c": [list(c) for c in row.counters],
                }
                for t, row in _record_of(game).items()
            }
            per_role = {
                role: [
                    [
                        d.turn,
                        d.decision_index,
                        [list(r) for r in d.timers],
                        [list(c) for c in d.counters],
                        d.moment,
                    ]
                    for d in rows
                ]
                for role, rows in decisions.items()
            }
            record = {"tag": tag, "format": fmt, "turns": turns, "decisions": per_role}
            f.write(json.dumps(record) + "\n")
            n += 1
    return n


def iter_timer_file(path: Path | str) -> Iterator[tuple[str, TimerRecord]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            turns = {
                int(t): TurnTimers(
                    tuple((a, b, int(lo), int(hi)) for a, b, lo, hi in row["t"]),
                    tuple((a, b, int(n)) for a, b, n in row["c"]),
                )
                for t, row in d["turns"].items()
            }
            decisions = {
                role: [
                    DecisionTimers(
                        int(row[0]),
                        int(row[1]),
                        tuple((a, b, int(lo), int(hi)) for a, b, lo, hi in row[2]),
                        tuple((a, b, int(n)) for a, b, n in row[3]),
                        row[4] if len(row) > 4 else "turn_start",
                    )
                    for row in rows
                ]
                for role, rows in d.get("decisions", {}).items()
            }
            yield d["tag"], TimerRecord(d["format"], turns, decisions)


def read_timer_file(path: Path | str) -> dict[str, TimerRecord]:
    return dict(iter_timer_file(path))


def write_timers_from_logs(
    logs_dir: Path,
    tables: dict[str, Durations],
    out: Path | str,
    shard: tuple[int, int] = (0, 1),
) -> int:
    from wpa.formats import format_of

    def games() -> Iterator[tuple]:
        index = 0
        for path in sorted(logs_dir.glob("logs_*.json")):
            for tag, (_ts, log) in iter_log_file(path):
                index += 1
                if (index - 1) % shard[1] != shard[0]:
                    continue
                fmt = format_of(tag)
                table = tables[fmt]
                yield tag, fmt, track_game(log, table), track_decisions(log, table)

    return write_timer_file(out, games())


# --------------------------------------------------------------------------
# Reading the big log files
# --------------------------------------------------------------------------


def iter_log_file(
    path: Path | str, chunk_size: int = 1 << 22
) -> Iterator[tuple[str, list]]:
    """Stream ``{tag: [timestamp, log]}`` without loading the whole file.

    The largest corpus file is 550MB; ``json.load`` of it can exhaust memory.
    """
    decoder = json.JSONDecoder()
    ws = " \t\r\n"
    with open(path, encoding="utf-8") as f:
        buf = ""
        pos = 0
        eof = False
        started = False

        def more() -> bool:
            nonlocal buf, pos, eof
            chunk = f.read(chunk_size)
            if not chunk:
                eof = True
                return False
            buf = buf[pos:] + chunk
            pos = 0
            return True

        while True:
            while pos < len(buf) and buf[pos] in ws:
                pos += 1
            if pos >= len(buf):
                if not more():
                    return
                continue
            if not started:
                if buf[pos] != "{":
                    raise ValueError(f"{path}: expected a JSON object")
                started = True
                pos += 1
                continue
            if buf[pos] in ",":
                pos += 1
                continue
            if buf[pos] == "}":
                return
            try:
                tag, end = decoder.raw_decode(buf, pos)
                colon = end
                while colon < len(buf) and buf[colon] in ws:
                    colon += 1
                if colon >= len(buf) or buf[colon] != ":":
                    raise json.JSONDecodeError("need more", buf, end)
                colon += 1
                while colon < len(buf) and buf[colon] in ws:
                    colon += 1
                value, end = decoder.raw_decode(buf, colon)
            except json.JSONDecodeError:
                if eof or not more():
                    raise
                continue
            pos = end
            yield tag, value


# --------------------------------------------------------------------------
# Tally and report
# --------------------------------------------------------------------------

_MAX_EXAMPLES = 8


@dataclass
class Tally:
    # (format, effect id) -> class -> count
    counts: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)
    # (format, effect id) -> [(tag, start turn, end turn, expected ends, cause)]
    examples: dict[tuple[str, str], list[tuple]] = field(default_factory=dict)
    # (format, counter id, flavour) -> attempts -> number of completed countdowns
    attempts: dict[tuple[str, str, str], dict[int, int]] = field(default_factory=dict)
    # (format, counter id, flavour) -> attempts so far -> countdowns cut off there
    cut_off: dict[tuple[str, str, str], dict[int, int]] = field(default_factory=dict)
    # (format, effect id) -> named cause -> explained early ends
    causes: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)
    games: dict[str, int] = field(default_factory=dict)

    def add_game(self, fmt: str, game: GameTimers, tag: str) -> None:
        self.games[fmt] = self.games.get(fmt, 0) + 1
        for t in game.timers:
            cls = classify(t)
            row = self.counts.setdefault((fmt, t.id), {})
            row[cls] = row.get(cls, 0) + 1
            if cls == "explained":
                named = self.causes.setdefault((fmt, t.id), {})
                named[t.end_detail] = named.get(t.end_detail, 0) + 1
            if cls == "unexplained":
                ex = self.examples.setdefault((fmt, t.id), [])
                if len(ex) < _MAX_EXAMPLES:
                    ex.append(
                        (
                            tag,
                            t.start_turn,
                            t.end_turn,
                            list(t.expected_ends),
                            t.end_detail,
                        )
                    )
        for c in game.counters:
            if c.variant == "rest":
                continue
            flavour = "earlybird" if c.early_bird else (c.variant or "")
            book = self.attempts if c.completed else self.cut_off
            row2 = book.setdefault((fmt, c.id, flavour), {})
            row2[c.attempts] = row2.get(c.attempts, 0) + 1

    def merge(self, other: Tally) -> None:
        for k, row in other.counts.items():
            mine = self.counts.setdefault(k, {})
            for cls, n in row.items():
                mine[cls] = mine.get(cls, 0) + n
        for k, ex in other.examples.items():
            mine_ex = self.examples.setdefault(k, [])
            mine_ex.extend(ex[: max(0, _MAX_EXAMPLES - len(mine_ex))])
        for k, row2 in other.attempts.items():
            mine2 = self.attempts.setdefault(k, {})
            for a, n in row2.items():
                mine2[a] = mine2.get(a, 0) + n
        for k, row3 in other.cut_off.items():
            mine3 = self.cut_off.setdefault(k, {})
            for a, n in row3.items():
                mine3[a] = mine3.get(a, 0) + n
        for k, row4 in other.causes.items():
            mine4 = self.causes.setdefault(k, {})
            for name, n in row4.items():
                mine4[name] = mine4.get(name, 0) + n
        for fmt, n in other.games.items():
            self.games[fmt] = self.games.get(fmt, 0) + n

    def to_json(self) -> dict:
        return {
            "counts": {"|".join(k): v for k, v in self.counts.items()},
            "examples": {"|".join(k): v for k, v in self.examples.items()},
            "attempts": {
                "|".join(k): {str(a): n for a, n in v.items()}
                for k, v in self.attempts.items()
            },
            "cut_off": {
                "|".join(k): {str(a): n for a, n in v.items()}
                for k, v in self.cut_off.items()
            },
            "causes": {"|".join(k): v for k, v in self.causes.items()},
            "games": self.games,
        }

    @classmethod
    def from_json(cls, data: dict) -> Tally:
        t = cls()
        t.counts = {tuple(k.split("|")): v for k, v in data["counts"].items()}  # type: ignore[misc]
        t.examples = {
            tuple(k.split("|")): [tuple(e) for e in v]
            for k, v in data["examples"].items()
        }  # type: ignore[misc]
        t.attempts = {
            tuple(k.split("|")): {int(a): n for a, n in v.items()}  # type: ignore[misc]
            for k, v in data["attempts"].items()
        }
        t.cut_off = {
            tuple(k.split("|")): {int(a): n for a, n in v.items()}  # type: ignore[misc]
            for k, v in data.get("cut_off", {}).items()
        }
        t.causes = {tuple(k.split("|")): v for k, v in data.get("causes", {}).items()}  # type: ignore[misc]
        t.games = dict(data["games"])
        return t

    # --- the report ------------------------------------------------------

    def describe(self, tables: dict[str, Durations]) -> str:
        out = [
            "# Duration table checked against the battle logs",
            "",
            "**Generated** by `python -m wpa.timers`. For every timed effect that",
            "starts",
            "and later ends in a log, the observed end turn is compared with the",
            "turn the",
            "table predicts from the start alone. Effects with no end event (the game",
            "ended, the Pokemon left or fainted, weather replaced by other",
            "weather) are",
            "*censored*: they say nothing about the table and are counted separately.",
            "",
            "- **match**: ended on the predicted turn.",
            "- **explained**: ended early, with a named cause in the log (Defog, Brick",
            "  Break and so on) or by using Trick Room again.",
            "- **unexplained**: ended on a different turn with no cause given.",
            "  This is the",
            "  mismatch rate to watch.",
            "",
            "Games read: "
            + ", ".join(f"{f} {n}" for f, n in sorted(self.games.items())),
        ]
        for fmt in sorted(tables):
            out += ["", f"## {fmt}", ""]
            out += [
                "| Effect | Started with an end event | Match | Explained "
                "| Unexplained | Mismatch rate | Censored |",
                "|---|---|---|---|---|---|---|",
            ]
            rows = sorted(k for k in self.counts if k[0] == fmt)
            for k in rows:
                c = self.counts[k]
                judged = (
                    c.get("match", 0) + c.get("explained", 0) + c.get("unexplained", 0)
                )
                rate = f"{c.get('unexplained', 0) / judged:.1%}" if judged else "-"
                name = (
                    tables[fmt].timed[k[1]].name if k[1] in tables[fmt].timed else k[1]
                )
                out.append(
                    f"| {name} | {judged} | {c.get('match', 0)} "
                    f"| {c.get('explained', 0)} "
                    f"| {c.get('unexplained', 0)} | {rate} | {c.get('censored', 0)} |"
                )
            out += [
                "",
                "### Unexplained examples "
                "(tag, start turn, end turn, predicted end turns, cause)",
                "",
            ]
            for k in rows:
                for ex in self.examples.get(k, [])[:3]:
                    out.append(f"- {k[1]}: {tuple(ex)}")
            out += ["", "### Named causes of early ends", ""]
            for k in rows:
                named = self.causes.get(k, {})
                if named:
                    top3 = sorted(named.items(), key=lambda kv: -kv[1])[:6]
                    out.append(f"- {k[1]}: " + ", ".join(f"{c} ({n})" for c, n in top3))
            out += ["", "### Counted effects", ""]
            for cid in ("slp", "frz", "confusion"):
                counted = tables[fmt].counted.get(cid)
                for flavour in ("", "earlybird", "axekick"):
                    obs = self.attempts.get((fmt, cid, flavour))
                    if counted is None or not obs:
                        continue
                    out += _counter_block(
                        counted, flavour, obs, self.cut_off.get((fmt, cid, flavour))
                    )
        return "\n".join(out).rstrip() + "\n"


def expected_attempts(counted: CountedEffect, flavour: str) -> dict[int, Fraction]:
    """Chance that a countdown prevents/activates exactly k attempts."""
    dist = counted.variants.get(flavour, counted.start_distribution)
    decrement = (
        counted.early_bird_decrement
        if flavour == "earlybird" and counted.early_bird_decrement
        else 1
    )
    h = hazards(dist, counted.end_chance_per_attempt or 0, decrement)
    survive = Fraction(1)
    out: dict[int, Fraction] = {}
    for k, hk in enumerate(h, start=1):
        out[k - 1] = survive * hk
        survive *= 1 - hk
    return out


def hazard_estimates(
    completed: dict[int, int], cut_off: dict[int, int]
) -> dict[int, tuple[int, int]]:
    """Observed chance that a countdown ends at attempt k, given it reached k.

    `completed` maps attempts prevented to countdowns that then ended by their own
    countdown (so they ended at attempt prevented + 1). `cut_off` maps attempts
    prevented to countdowns removed from outside (switch, faint, game over): those
    were at risk for attempts 1..prevented and no further. Counting only the
    finished ones would bias the estimate towards short sleeps. Returns
    k -> (ended at k, at risk at k).
    """
    top = max([*(a + 1 for a in completed), *cut_off, 0])
    out: dict[int, tuple[int, int]] = {}
    for k in range(1, top + 1):
        ended = completed.get(k - 1, 0)
        at_risk = sum(n for a, n in completed.items() if a + 1 >= k)
        at_risk += sum(n for a, n in cut_off.items() if a >= k)
        out[k] = (ended, at_risk)
    return out


def _counter_block(
    counted: CountedEffect,
    flavour: str,
    obs: dict[int, int],
    cut: dict[int, int] | None = None,
) -> list[str]:
    total = sum(obs.values())
    exp = expected_attempts(counted, flavour)
    label = counted.name + (f" ({flavour})" if flavour else "")
    out = [
        f"**{label}**: {total} countdowns that ran their course",
        "",
        "| Attempts | Expected | Observed |",
        "|---|---|---|",
    ]
    for k in sorted(set(exp) | set(obs)):
        e = float(exp.get(k, 0))
        o = obs.get(k, 0) / total
        out.append(f"| {k} | {e:.1%} | {o:.1%} ({obs.get(k, 0)}) |")
    out.append("")
    dist = counted.variants.get(flavour, counted.start_distribution)
    decrement = (
        counted.early_bird_decrement
        if flavour == "earlybird" and counted.early_bird_decrement
        else 1
    )
    expected_h = hazards(dist, counted.end_chance_per_attempt or 0, decrement)
    out += [
        f"Chance it ends at attempt k, given it got that far "
        f"({sum((cut or {}).values())} cut-off countdowns counted while at risk):",
        "",
        "| Attempt k | Expected | Observed (ended / at risk) |",
        "|---|---|---|",
    ]
    for k, (ended, at_risk) in hazard_estimates(obs, cut or {}).items():
        e_h = float(expected_h[k - 1]) if k - 1 < len(expected_h) else 1.0
        seen = f"{ended / at_risk:.1%} ({ended} / {at_risk})" if at_risk else "-"
        out.append(f"| {k} | {e_h:.1%} | {seen} |")
    out.append("")
    return out


# --------------------------------------------------------------------------
# (a) / (b) / (c): what a decision point can know about each length
# --------------------------------------------------------------------------

# Lengths drawn in a start handler rather than in a duration callback, so the
# table's `base` is only a floor: lockedmove (Outrage, Thrash, Petal Dance...)
# sets trueDuration = this.random(2, 4) in onStart (checked in the dump).
_DRAWN_ON_START = {"lockedmove": (2, 4)}

# Counted effects. par has no countdown at all, only a 1/8 chance per attempt.
_COUNTED_CLASSES = {
    "slp": ("b", "prevents 1 attempt (1/3) or 2 (2/3); wakes at the 2nd or 3rd"),
    "frz": ("b", "1/4 chance to thaw per attempt, certain at the 3rd"),
    "confusion": (
        "b",
        "ends at attempt 2-5 (25-50% each, given it got there); 33% self-hit",
    ),
    "par": ("b", "no length: 1/8 chance of full paralysis per attempt"),
    "tox": ("a", "stage counter, +1 per turn, resets on switching out"),
}


def length_class(effect: TimedEffect) -> tuple[str, str]:
    """Class of a timed effect and a one-line note on how its length is known.

    (a) fixed given what the observer sees: the start turn, the phase it began in,
        and the items and abilities on the open team sheet.
    (b) random, with a known distribution given the observable count.
    (c) hidden: none among the timed effects (see docs/TIMERS.md).
    """
    drawn = _DRAWN_ON_START.get(effect.id)
    rng = effect.random_range or drawn
    if rng is not None:
        low, high = rng[0], rng[1] - 1
        note = f"random {low}-{high} turns, equally likely"
        for m in effect.modifiers:
            note += f"; {m.name} {m.duration}"
        return "b", note
    if not effect.base:
        return "a", "permanent while the source stays in (no timer)"
    note = (
        f"{effect.base} turns"
        if effect.base != 1
        else "1 turn (gone before the next decision)"
    )
    if effect.modifiers:
        note += "; " + ", ".join(f"{m.name} {m.duration}" for m in effect.modifiers)
    if effect.adjustments:
        note += "; start order " + ", ".join(
            f"{a.delta:+d}" for a in effect.adjustments
        )
    return "a", note


def counted_class(counted_id: str) -> tuple[str, str]:
    return _COUNTED_CLASSES[counted_id]


def render_classes(tables: dict[str, Durations]) -> str:
    """The class table written into docs/TIMERS.md (between its markers)."""
    rows: dict[str, dict[str, tuple[str, str, str]]] = {}
    for fmt, table in tables.items():
        for id, e in table.timed.items():
            cls, note = length_class(e)
            rows.setdefault(id, {})[fmt] = (cls, note, e.name)
        for id, c in table.counted.items():
            cls, note = counted_class(id)
            rows.setdefault(id, {})[fmt] = (cls, note, c.name)
    out = ["| Effect | id | Class | Length and how it is known |", "|---|---|---|---|"]
    for id in sorted(rows):
        per_fmt = rows[id]
        distinct = {(c, n) for c, n, _ in per_fmt.values()}
        name = next(iter(per_fmt.values()))[2]
        if len(distinct) == 1:
            cls, note = next(iter(distinct))
            out.append(f"| {name} | `{id}` | ({cls}) | {note} |")
        else:
            cls = "/".join(sorted({c for c, _ in distinct}))
            note = "; ".join(f"{f}: {per_fmt[f][1]}" for f in sorted(per_fmt))
            out.append(f"| {name} | `{id}` | ({cls}) | {note} |")
    return "\n".join(out) + "\n"


def write_classes(path: Path, tables: dict[str, Durations]) -> None:
    start, end = "<!-- classes:start -->", "<!-- classes:end -->"
    text = path.read_text(encoding="utf-8")
    head = text.split(start, 1)[0]
    tail = text.split(end, 1)[1]
    path.write_text(
        f"{head}{start}\n{render_classes(tables)}{end}{tail}", encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def run_logs(
    logs_dir: Path, tables: dict[str, Durations], shard: tuple[int, int] = (0, 1)
) -> Tally:
    from wpa.formats import format_of

    tally = Tally()
    index = 0
    for path in sorted(logs_dir.glob("logs_*.json")):
        for tag, (_ts, log) in iter_log_file(path):
            index += 1
            if (index - 1) % shard[1] != shard[0]:
                continue
            fmt = format_of(tag)
            tally.add_game(fmt, track_game(log, tables[fmt]), tag)
    return tally


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check the duration table against battle logs."
    )
    parser.add_argument("--logs", type=Path, default=Path("battle_logs"))
    parser.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    parser.add_argument("--shard", default="0/1", help="i/n: read every n-th game")
    parser.add_argument(
        "--out", type=Path, help="save the counts as JSON (for --merge)"
    )
    parser.add_argument(
        "--merge",
        nargs="+",
        type=Path,
        help="join saved counts instead of reading logs",
    )
    parser.add_argument("--markdown", type=Path, help="write the report here")
    parser.add_argument(
        "--timers-out",
        type=Path,
        help="write the per-game, per-turn timer side file (.jsonl.gz) from the logs",
    )
    parser.add_argument(
        "--classes",
        type=Path,
        help="rewrite the (a)/(b)/(c) table between the markers of this file",
    )
    args = parser.parse_args()
    tables = load_all(args.showdown)
    if args.classes:
        write_classes(args.classes, tables)
        print(f"wrote {args.classes}")
        return
    if args.timers_out:
        i, n = (int(x) for x in args.shard.split("/"))
        count = write_timers_from_logs(args.logs, tables, args.timers_out, (i, n))
        print(f"wrote {count} games to {args.timers_out}")
        return
    if args.merge:
        tally = Tally()
        for p in args.merge:
            tally.merge(Tally.from_json(json.loads(p.read_text(encoding="utf-8"))))
    else:
        i, n = (int(x) for x in args.shard.split("/"))
        tally = run_logs(args.logs, tables, (i, n))
    if args.out:
        args.out.write_text(json.dumps(tally.to_json()), encoding="utf-8")
        print(f"wrote {args.out}")
    report = tally.describe(tables)
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")
        print(f"wrote {args.markdown}")
    elif not args.out:
        print(report)


if __name__ == "__main__":
    main()
