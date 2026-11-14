"""How long each timed effect lasts, generated from the pinned Showdown data
(Week 4 Task 7; docs/DURATIONS.md).

Nothing in the table is typed by hand. ``scripts/dump_durations.js`` asks the
pinned Pokemon Showdown submodule, through its own mod inheritance, which
effects carry a duration or a counter and what their callbacks say. This
module parses that, finds the line of TypeScript source each fact comes from,
and renders the document. If the submodule moves, regenerate:

    python -m wpa.durations --out docs/DURATIONS.md

A test fails if the committed document no longer matches a fresh generation.

Turn arithmetic (checked against the battle logs by ``wpa.timers``):

* Showdown counts a duration down in the end-of-turn residual. An effect set
  by a move during turn T is in force on turns T .. T + D - 1 and is removed
  in the residual of turn T + D - 1.
* An effect set after the residual of turn T (a replacement switching in, a
  weather ability) loses no turn: it is removed in the residual of T + D.
* Leads switch in on turn 0, before any residual, so turn 0 behaves the same
  way.

Leakage rule: ``turns_remaining`` takes the start turn, the phase and the
duration. It has no argument that could carry the effect's end event; end
events are the future and are used only to *validate* this table.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

# Which Showdown mod each format runs (config/formats.ts, checked by a test),
# and which pinned copy of Showdown's code it comes from (DEFINITIONS §15,
# revision 12): Showdown's current code no longer has M-A's rules.
FORMAT_MODS: dict[str, str] = {
    "regma": "championsregma",
    "regmb": "champions",
    "regmc": "champions",
}
FORMAT_COPIES: dict[str, str] = {
    "regma": "pokemon-showdown",
    "regmb": "pokemon-showdown",
    "regmc": "pokemon-showdown-mc",
}


def showdown_for(fmt: str, showdown: Path | str) -> Path:
    """The copy of Showdown's code `fmt` reads, given the June copy's folder
    (the `--showdown` option): another copy sits beside it."""
    root = Path(showdown)
    copy = FORMAT_COPIES[fmt]
    return root if copy == FORMAT_COPIES["regma"] else root.parent / copy


ACTION = "action"  # set by a move or switch-in during the turn's actions
AFTER_RESIDUAL = "after_residual"  # set after the turn's residual (e.g. a replacement)
_PHASES = (ACTION, AFTER_RESIDUAL)

_TABLE_FILES = {
    "Conditions": "conditions.ts",
    "Moves": "moves.ts",
    "Abilities": "abilities.ts",
    "Items": "items.ts",
}
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "dump_durations.js"

# Status conditions and volatiles that count down or roll each attempt rather
# than carry a plain duration. Which of them exist is curated; every number is
# read from the source. The role says what a per-attempt chance does.
_COUNTED_SPECS: dict[str, dict[str, str]] = {
    "slp": {"chance_role": "none"},
    "frz": {"chance_role": "end"},
    "confusion": {"chance_role": "event", "event": "hits itself instead of moving"},
    "par": {"chance_role": "event", "event": "cannot move (full paralysis)"},
    "tox": {"chance_role": "none"},
}


# --------------------------------------------------------------------------
# Turn arithmetic
# --------------------------------------------------------------------------


def scheduled_end_turn(start_turn: int, start_phase: str, duration: int) -> int:
    """The turn whose residual removes an effect set at ``start_turn``."""
    if start_phase not in _PHASES:
        raise ValueError(f"start_phase must be one of {_PHASES}, got {start_phase!r}")
    if duration < 1:
        raise ValueError(f"duration must be at least 1, got {duration!r}")
    if start_phase == ACTION and start_turn >= 1:
        return start_turn + duration - 1
    return start_turn + duration


def turns_remaining(
    current_turn: int, start_turn: int, start_phase: str, duration: int
) -> int:
    """Turns the effect is still in force, counting ``current_turn`` itself.

    Computed only from facts known when the effect started. Never negative: an
    effect past its scheduled end has 0 turns left.
    """
    end = scheduled_end_turn(start_turn, start_phase, duration)
    return max(0, end - current_turn + 1)


def hazards(
    start_distribution: dict[int, Fraction],
    per_attempt_chance: Fraction | int = 0,
    decrement: int = 1,
) -> list[Fraction]:
    """Chance the effect ends at attempt k, given it has not ended before.

    ``start_distribution`` maps the initial count to its probability. Every
    attempt the count drops by ``decrement`` and the effect ends when it
    reaches zero, or earlier with ``per_attempt_chance``.
    """
    q = Fraction(per_attempt_chance)
    dist = {s: Fraction(w) for s, w in start_distribution.items()}
    out: list[Fraction] = []
    k = 1
    while True:
        before = sum(
            (w for s, w in dist.items() if s - decrement * (k - 1) > 0), Fraction(0)
        )
        if before == 0:
            break
        after = sum((w for s, w in dist.items() if s - decrement * k > 0), Fraction(0))
        h = 1 - (1 - q) * after / before
        out.append(h)
        if h == 1:
            break
        k += 1
    return out


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    file: str  # relative to the Showdown directory
    line: int  # 1-based

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass(frozen=True)
class Modifier:
    """A different length when the source holds an item or ability."""

    kind: str  # "item", "ability", "trigger" or "other"
    name: str
    duration: int
    when: str  # the condition, verbatim
    source: SourceRef


@dataclass(frozen=True)
class Adjustment:
    """One turn more or fewer, depending on ordering within the turn."""

    handler: str
    delta: int
    guard: str  # the condition under which it applies, verbatim
    source: SourceRef


@dataclass(frozen=True)
class TimedEffect:
    table: str
    id: str
    name: str
    attach: str | None  # the move field that attaches it, or the effect type
    base: int | None
    modifiers: tuple[Modifier, ...]
    adjustments: tuple[Adjustment, ...]
    random_range: tuple[int, int] | None  # this.random(a, b): a .. b - 1
    scheduled_by: str  # "duration" or "turn stamp"
    source: SourceRef


@dataclass(frozen=True)
class CountedEffect:
    id: str
    name: str
    start_distribution: dict[int, Fraction]
    variants: dict[str, dict[int, Fraction]]
    early_bird_decrement: int | None
    end_chance_per_attempt: Fraction | None
    event_chance_per_attempt: Fraction | None
    event: str
    notes: str
    source: SourceRef


@dataclass
class Durations:
    mod: str
    copy: str = "pokemon-showdown"  # the copy of Showdown's code it was read from
    timed: dict[str, TimedEffect] = field(default_factory=dict)
    counted: dict[str, CountedEffect] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Reading the Showdown source
# --------------------------------------------------------------------------


def showdown_commit(showdown_dir: Path | str) -> str:
    out = subprocess.run(
        ["git", "-C", str(showdown_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def showdown_commits(showdown: Path | str) -> dict[str, str]:
    """Each copy of Showdown's code the formats read, and its commit."""
    return {
        FORMAT_COPIES[f]: showdown_commit(showdown_for(f, showdown))
        for f in FORMAT_MODS
    }


def _dump(showdown_dir: Path, mod: str) -> dict:
    try:
        out = subprocess.run(
            ["node", str(_SCRIPT), str(showdown_dir), mod],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
    except FileNotFoundError as e:
        raise RuntimeError("Node is needed to read the Showdown data") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"reading mod {mod!r} failed: {e.stderr.strip()}") from e
    return json.loads(out.stdout)


class _Source:
    """The TypeScript source behind one mod, most specific file first."""

    def __init__(self, root: Path, mod: str) -> None:
        self.root = root
        self.chain = self._chain(mod)
        self._lines: dict[str, list[str] | None] = {}

    def _chain(self, mod: str) -> list[str]:
        chain: list[str] = []
        current: str | None = mod
        while current:
            chain.append(current)
            script = self.root / "data" / "mods" / current / "scripts.ts"
            match = re.search(r"inherit:\s*'(\w+)'", script.read_text(encoding="utf-8"))
            current = match.group(1) if match else None
        return chain

    def files(self, table: str) -> list[str]:
        name = _TABLE_FILES[table]
        return [f"data/mods/{m}/{name}" for m in self.chain] + [f"data/{name}"]

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._lines:
            path = self.root / rel
            self._lines[rel] = (
                path.read_text(encoding="utf-8").split("\n") if path.exists() else None
            )
        return self._lines[rel]

    def blocks(self, table: str, effect_id: str):
        """Yield (file, lines, first, last) for each definition, most specific first."""
        key = re.compile(r"^\t(?:%s|'%s'|\"%s\"): \{" % ((re.escape(effect_id),) * 3))
        for rel in self.files(table):
            lines = self.lines(rel)
            if lines is None:
                continue
            for i, text in enumerate(lines):
                if key.match(text):
                    j = i + 1
                    while j < len(lines) and lines[j] not in ("\t},", "\t}"):
                        j += 1
                    yield rel, lines, i, j
                    break


def _condition_start(lines: list[str], first: int, last: int, table: str) -> int:
    if table == "Conditions":
        return first
    for i in range(first, last):
        if re.match(r"^\t\tcondition: \{", lines[i]):
            return i
    return first


def _find(lines: list[str], start: int, stop: int, pattern: str) -> int | None:
    rx = re.compile(pattern)
    for i in range(start, stop):
        if rx.search(lines[i]):
            return i
    return None


def _locate_duration(src: _Source, table: str, effect_id: str) -> SourceRef | None:
    for rel, lines, first, last in src.blocks(table, effect_id):
        start = _condition_start(lines, first, last, table)
        i = _find(lines, start, last, r"^\s*duration:\s*\d")
        if i is None:
            i = _find(lines, start, last, r"^\s*durationCallback\(")
        if i is not None:
            return SourceRef(rel, i + 1)
    return None


def _locate_text(
    src: _Source, table: str, effect_id: str, pattern: str, after: str | None = None
) -> SourceRef | None:
    """First line matching ``pattern`` (after one matching ``after``)."""
    for rel, lines, first, last in src.blocks(table, effect_id):
        start = _condition_start(lines, first, last, table)
        if after is not None:
            j = _find(lines, start, last, after)
            if j is None:
                continue
            start = j
        i = _find(lines, start, last, pattern)
        if i is not None:
            return SourceRef(rel, i + 1)
    return None


def _enclosing_condition(src: str, pos: int) -> str:
    """The text of the innermost ``if`` whose block contains ``pos``."""
    stack: list[str] = []
    header = 0
    for i, ch in enumerate(src[:pos]):
        if ch == "{":
            stack.append(src[header:i].strip())
            header = i + 1
        elif ch == "}":
            if stack:
                stack.pop()
            header = i + 1
        elif ch == ";":
            header = i + 1
    for h in reversed(stack):
        match = re.match(r"(?:else )?if \((.*)\)$", h, re.S)
        if match:
            guard = " ".join(match.group(1).split())
            # A bare variable is useless without what it stands for.
            for name in dict.fromkeys(re.findall(r"\b[a-z]\w*\b", guard)):
                if name in ("this", "true", "false", "null"):
                    continue
                m = re.search(
                    r"(?:const|let|var)\s+%s\s*=\s*([^;]+);" % re.escape(name),
                    src[:pos],
                )
                if m and re.fullmatch(r"!?%s" % name, guard):
                    guard += f"   [where {name} = {' '.join(m.group(1).split())}]"
            return guard
    return ""


def _modifiers(
    callback: str, src: _Source, table: str, effect_id: str
) -> tuple[list[Modifier], tuple[int, int] | None]:
    mods: list[Modifier] = []
    pattern = re.compile(
        r"if \((?P<cond>(?:[^()]|\([^()]*\))*)\)\s*(?:\{[^{}]*?)?return (?P<n>\d+);"
    )
    for m in pattern.finditer(callback):
        cond = " ".join(m.group("cond").split())
        item = re.search(r"hasItem\([\"'](\w+)[\"']\)", cond)
        ability = re.search(r"hasAbility\([\"'](\w+)[\"']\)", cond)
        trigger = re.search(r"effect\?\.name === [\"']([^\"']+)[\"']", cond)
        if item:
            kind, name = "item", item.group(1)
        elif ability:
            kind, name = "ability", ability.group(1)
        elif trigger:
            kind, name = "trigger", trigger.group(1)
        else:
            kind, name = "other", cond
        needle = (
            re.escape(name)
            if kind in ("item", "ability", "trigger")
            else re.escape(cond[:20])
        )
        ref = _locate_text(src, table, effect_id, needle, after=r"durationCallback\(")
        if ref is None:
            raise RuntimeError(f"no source line for modifier {name!r} of {effect_id!r}")
        mods.append(Modifier(kind, name, int(m.group("n")), cond, ref))
    rnd = re.search(r"return this\.random\((\d+), (\d+)\)", callback)
    return mods, ((int(rnd.group(1)), int(rnd.group(2))) if rnd else None)


def _adjustments(
    functions: dict[str, str], src: _Source, table: str, effect_id: str
) -> list[Adjustment]:
    out: list[Adjustment] = []
    for key, text in functions.items():
        owner, handler = key.split(".", 1)
        matches = list(re.finditer(r"effectState\.duration(\+\+|--)", text))
        for k, m in enumerate(matches):
            ref = None
            for rel, lines, first, last in src.blocks(table, effect_id):
                start = (
                    _condition_start(lines, first, last, table)
                    if owner == "condition"
                    else first
                )
                h = _find(lines, start, last, r"^\s*%s\(" % re.escape(handler))
                if h is None:
                    continue
                hits = [
                    i
                    for i in range(h, last)
                    if re.search(r"effectState\.duration!?(\+\+|--)", lines[i])
                ]
                # stop at the end of this handler: the next handler line
                nxt = _find(lines, h + 1, last, r"^\t\t\t?\w+\(") or last
                hits = [i for i in hits if i < nxt]
                if len(hits) > k:
                    ref = SourceRef(rel, hits[k] + 1)
                    break
            if ref is None:
                raise RuntimeError(f"no source line for {key} of {effect_id!r}")
            out.append(
                Adjustment(
                    key,
                    1 if m.group(1) == "++" else -1,
                    _enclosing_condition(text, m.start()),
                    ref,
                )
            )
    return out


def _turn_stamped(effect: dict, src: _Source) -> TimedEffect | None:
    """Future-attack and Wish style effects: set from the turn counter."""
    text = "\n".join(effect["functions"].values())
    end = re.search(r"endingTurn = \(?this\.turn - 1\)? \+ (\d+)", text)
    wish = re.search(
        r"getOverflowedTurnCount\(\) <= this\.effectState\.startingTurn", text
    )
    if end:
        # endingTurn is in getOverflowedTurnCount() units, i.e. turn - 1, so the
        # effect lands N turns after the one it was used on: duration N + 1.
        base, pattern = int(end.group(1)) + 1, r"endingTurn = "
    elif wish and "startingTurn = this.getOverflowedTurnCount()" in text:
        base, pattern = 2, r"startingTurn = "
    else:
        return None
    ref = _locate_text(src, effect["table"], effect["id"], pattern)
    if ref is None:
        return None
    attach = "slotCondition"
    return TimedEffect(
        effect["table"],
        effect["id"],
        effect["name"],
        attach,
        base,
        (),
        (),
        None,
        "turn stamp",
        ref,
    )


def _distribution(
    text: str,
) -> tuple[dict[int, Fraction], dict[str, dict[int, Fraction]]]:
    """The starting count a status rolls, read from its onStart."""
    variants: dict[str, dict[int, Fraction]] = {}
    sample = re.search(r"startTime = this\.sample\(\[([\d,\s]+)\]\)", text)
    const = re.search(r"startTime = (\d+);", text)
    rand = re.search(r"(?:startTime|time) = this\.random\((\w+), (\d+)\)", text)
    if sample:
        values = [int(v) for v in sample.group(1).split(",")]
        return {
            v: Fraction(values.count(v), len(values)) for v in sorted(set(values))
        }, variants
    if const:
        return {int(const.group(1)): Fraction(1)}, variants

    def uniform(low: int, high: int) -> dict[int, Fraction]:
        return {n: Fraction(1, high - low) for n in range(low, high)}

    if rand:
        high = int(rand.group(2))
        low_text = rand.group(1)
        if low_text.isdigit():
            return uniform(int(low_text), high), variants
        # `const min = sourceEffect?.id === "axekick" ? 3 : 2;`
        pick = re.search(
            r"const %s = .*?[\"'](\w+)[\"'] \? (\d+) : (\d+);" % re.escape(low_text),
            text,
        )
        if pick:
            variants[pick.group(1)] = uniform(int(pick.group(2)), high)
            return uniform(int(pick.group(3)), high), variants
    return {}, variants


def _counted(effect: dict, src: _Source) -> CountedEffect:
    spec = _COUNTED_SPECS[effect["id"]]
    funcs = effect["functions"]
    start_text = funcs.get("condition.onStart", "")
    before = funcs.get("condition.onBeforeMove", "")
    dist, variants = _distribution(start_text)
    chances = [
        Fraction(int(a), int(b))
        for a, b in re.findall(r"randomChance\((\d+), (\d+)\)", before)
    ]
    end_chance = event_chance = None
    role = spec["chance_role"]
    if role == "end" and chances:
        end_chance = chances[0]
    if role == "event" and chances:
        event_chance = chances[0]
    early_bird = 2 if re.search(r"hasAbility\([\"']earlybird[\"']\)", before) else None
    notes = ""
    if effect["id"] == "tox":
        notes = "the poison count rises by one each residual (see the source)"
    ref = _locate_text(src, "Conditions", effect["id"], r"onStart\(") or _locate_text(
        src, "Conditions", effect["id"], r"onBeforeMove\("
    )
    if ref is None:
        raise RuntimeError(f"no source line for counted effect {effect['id']!r}")
    # Point at the roll itself where there is one.
    rolled = _locate_text(
        src, "Conditions", effect["id"], r"startTime = |\.time = this\.random"
    )
    return CountedEffect(
        effect["id"],
        effect["name"],
        dist,
        variants,
        early_bird,
        end_chance,
        event_chance,
        spec.get("event", ""),
        notes,
        rolled or ref,
    )


def _load(showdown_dir: Path, mod: str) -> Durations:
    dump = _dump(showdown_dir, mod)
    src = _Source(showdown_dir, mod)
    result = Durations(mod)
    for effect in dump["effects"]:
        table, eid = effect["table"], effect["id"]
        if table == "Conditions" and eid in _COUNTED_SPECS:
            result.counted[eid] = _counted(effect, src)
            continue
        timed = effect["duration"] is not None or effect["durationCallback"]
        if not timed:
            stamped = _turn_stamped(effect, src)
            if stamped is not None:
                _add(result, stamped)
            continue
        ref = _locate_duration(src, table, eid)
        if ref is None:
            raise RuntimeError(
                f"no source line for the duration of {table}.{eid} in {mod}"
            )
        mods: list[Modifier] = []
        rnd = None
        if effect["durationCallback"]:
            mods, rnd = _modifiers(effect["durationCallback"], src, table, eid)
        if effect["attach"]:
            attach = next(iter(effect["attach"]))
        elif effect["effectType"]:
            attach = str(effect["effectType"]).lower()
        else:
            attach = None
        _add(
            result,
            TimedEffect(
                table,
                eid,
                effect["name"],
                attach,
                effect["duration"],
                tuple(mods),
                tuple(_adjustments(effect["functions"], src, table, eid)),
                rnd,
                "duration",
                ref,
            ),
        )
    return result


def _add(result: Durations, effect: TimedEffect) -> None:
    if effect.id in result.timed:
        raise RuntimeError(f"two timed effects share the id {effect.id!r}")
    result.timed[effect.id] = effect


def load_all(showdown_dir: Path | str) -> dict[str, Durations]:
    """The duration table for each format, keyed by format name."""
    out = {}
    for fmt, mod in FORMAT_MODS.items():
        out[fmt] = _load(showdown_for(fmt, showdown_dir), mod)
        out[fmt].copy = FORMAT_COPIES[fmt]
    return out


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def _turns(effect: TimedEffect) -> str:
    if effect.random_range is not None:
        low, high = effect.random_range
        return f"random {low}-{high - 1}"
    return "-" if effect.base is None else str(effect.base)


def _frac(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _dist(d: dict[int, Fraction]) -> str:
    return ", ".join(f"{k}: {_frac(v)}" for k, v in sorted(d.items())) or "none"


def render_markdown(data: dict[str, Durations], commit: str | Mapping[str, str]) -> str:
    """The document. `commit`: each copy of Showdown's code and its commit
    (one commit alone: the June copy's)."""
    commits = {"pokemon-showdown": commit} if isinstance(commit, str) else commit
    source = "; ".join(f"`{c}` at `{sha}`" for c, sha in commits.items())
    out = [
        "# Durations of timed effects",
        "",
        "**Generated. Do not edit by hand.** Regenerate with "
        "`python -m wpa.durations --out docs/DURATIONS.md`; a test fails if this file "
        "differs from a fresh generation.",
        "",
        f"Source: the pinned copies of Showdown's code, {source}, read through "
        "Showdown's own mod inheritance by `scripts/dump_durations.js`. Every row "
        "gives the file and line the number comes from.",
        "",
        "## How to read the turn numbers",
        "",
        "- **Base** is the duration in turns. An effect set by a move during turn T is "
        "in force on turns T to T + base - 1 and is removed in that turn's end-of-turn "
        "residual.",
        "- An effect set *after* the residual of turn T (a replacement switching in, "
        "or a weather ability) loses no turn: it ends in the residual of T + base. "
        "Leads switch in on turn 0, before any residual, so turn 0 behaves the "
        "same way.",
        "- **Modifiers** replace the base when the user holds the item or ability. "
        "With open team sheets both are known from the first state.",
        "- **Ordering** adjustments add or remove a turn depending on whether the "
        "target has already moved this turn. That is visible in the log at the moment "
        "the effect starts.",
        "- An **attempt** (counted effects below) is a turn on which the Pokemon is "
        "about to act. Turns on which it is switched out or has fainted are not "
        "attempts.",
        "- The turns remaining at a decision point are computed from the start turn "
        "and this table only, never from the end event "
        "(`wpa.durations.turns_remaining`).",
        "",
        "## Formats and mods",
        "",
        "| Format | Copy of Showdown's code | Showdown mod | Inherits |",
        "|---|---|---|---|",
    ]
    for fmt, mod in FORMAT_MODS.items():
        out.append(f"| {fmt} | `{data[fmt].copy}` | `{mod}` | {_inherits(data, fmt)} |")
    for fmt, d in data.items():
        out += ["", f"## {fmt} (`{d.copy}`, `{d.mod}`)", "", "### Timed effects", ""]
        out += [
            "| Effect | Attached as | Turns | Modifiers | Ordering | Source |",
            "|---|---|---|---|---|---|",
        ]
        for e in sorted(d.timed.values(), key=lambda x: (x.name.lower(), x.id)):
            mods = (
                "; ".join(
                    f"{m.kind} `{m.name}`: {m.duration} ({m.source})"
                    for m in e.modifiers
                )
                or "-"
            )
            adj = (
                "; ".join(
                    f"{a.delta:+d} if `{a.guard or 'always'}` ({a.source})"
                    for a in e.adjustments
                )
                or "-"
            )
            out.append(
                f"| {e.name} | {e.attach or '-'} | {_turns(e)} | {mods} | {adj} "
                f"| {e.source} |"
            )
        out += ["", "### Counted effects (status and volatile counters)", ""]
        for c in d.counted.values():
            out.append(f"**{c.name}** (`{c.id}`, {c.source})")
            out.append("")
            if c.start_distribution:
                out.append(f"- Starting count: {_dist(c.start_distribution)}.")
                for name, dist in c.variants.items():
                    out.append(
                        f"- Starting count when caused by `{name}`: {_dist(dist)}."
                    )
                h = hazards(c.start_distribution, c.end_chance_per_attempt or 0)
                out.append(
                    "- Chance it ends at each attempt, given it has not ended: "
                    + ", ".join(_frac(x) for x in h)
                    + "."
                )
                if c.early_bird_decrement:
                    he = hazards(c.start_distribution, 0, c.early_bird_decrement)
                    out.append(
                        "- With Early Bird the count drops by "
                        f"{c.early_bird_decrement} per attempt: "
                        + ", ".join(_frac(x) for x in he)
                        + "."
                    )
            if c.end_chance_per_attempt is not None:
                out.append(
                    "- Ends early with chance "
                    f"{_frac(c.end_chance_per_attempt)} each attempt."
                )
            if c.event_chance_per_attempt is not None:
                out.append(
                    f"- Chance {_frac(c.event_chance_per_attempt)} each attempt "
                    "that the Pokemon "
                    f"{c.event}. This is not a length."
                )
            if c.notes:
                out.append(f"- {c.notes}.")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _inherits(data: dict[str, Durations], fmt: str) -> str:
    return ", ".join(f"`{m}`" for m in _chain_names(data, fmt))


def _chain_names(data: dict[str, Durations], fmt: str) -> list[str]:
    # The chain is a property of the source tree; recompute it from the mod names.
    names = [data[fmt].mod]
    if data[fmt].mod == "championsregma":
        names.append("champions")
    return names


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate docs/DURATIONS.md from Showdown."
    )
    parser.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    parser.add_argument(
        "--out", type=Path, help="write the document here (default: print)"
    )
    args = parser.parse_args()
    data = load_all(args.showdown)
    text = render_markdown(data, showdown_commits(args.showdown))
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
