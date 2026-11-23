"""Shortcuts in the move list (Week 17, Task 2; the PO's request of 17 Nov).

The bot's search compares every play the rules allow (DEFINITIONS §4, revision
13), likeliest first. Two kinds of shortcut:

* **Plays that cannot work** are taken out, for both sides (`cannot_work`):
  Fake Out or First Impression after a Pokemon's first turn out
  (`first_turn_only`). A Pokemon keeps all its options if every one would go.
* **Plays that rarely make sense but sometimes do** are valued last, never
  removed (`value_last`): a damaging move into one's own partner (Sneasler's
  White Herb Close Combat for Unburden, U-turn out of Perish Song; Pollen Puff,
  which heals a partner, is not one); a status move into a target that already
  has one (into a Sucker Punch user; Yawn into a sleeping or drowsy target,
  which makes the Pokemon switched in there drowsy); and (the PO, 20 Nov)
  Tailwind while its own is up, and a weather move in that weather (or any
  under a primal weather), to play around a switch-in's weather ability or an
  opposing weather setter. By Showdown's rules a second Tailwind fails unless
  the opponent's Court Change moves the first away. And (the PO, 23 Nov)
  Tailwind when the other side has one Pokemon left. Of these, only late
  Tailwind is on by default (`DEFAULT_LAST`, the PO's calls of 22 and 23
  Nov); the rest with `--value-last`.

They change only the order and the size of the search, never a play's value.
The replay report and the training tables do not use them: players do make
these plays, and their choices must stay in the list."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence

from wpa.choices import Action
from wpa.damage import WEATHER

RULES = ("first_turn_only",)
FIRST_TURN_ONLY = {"fakeout", "firstimpression"}
PRIMAL = {"desolateland", "primordialsea", "deltastream"}
# weather moves that do something else as well (Chilly Reception switches out)
WEATHER_PLUS = {"chillyreception"}
HEALS_ALLY = {"pollenpuff"}


def _weather_name(w: str | None) -> str | None:
    if not w:
        return None
    w = w.lower()
    return WEATHER.get(w, w)


def cannot_work(
    a: Action,
    ours: Sequence[Mapping],
    our_side: Collection[str],
    weather: str | None,
    moves: Mapping,
    rules: Collection[str] = RULES,
) -> str | None:
    """The rule that rules out action `a` (by the Pokemon `ours[a.user]`), or
    None. `our_side` and `weather` (the board's name, as
    `wpa.features._field` gives it) are kept for rules that need them."""
    if a.kind != "move":
        return None
    st = ours[a.user] if a.user < len(ours) else {}
    if "first_turn_only" in rules and a.move in FIRST_TURN_ONLY and st.get("moved"):
        return "first_turn_only"
    return None


def keep(
    opts: Sequence[Action],
    ours: Sequence[Mapping],
    our_side: Collection[str],
    weather: str | None,
    moves: Mapping,
    fired: Counter,
    rules: Collection[str] = RULES,
) -> list[bool]:
    """Which of one Pokemon's options stay; each removal counted in `fired`.
    If every option would go, all stay (the search must have something)."""
    why = [cannot_work(a, ours, our_side, weather, moves, rules) for a in opts]
    if all(w is not None for w in why):
        return [True] * len(opts)
    fired.update(w for w in why if w is not None)
    return [w is None for w in why]


def _same_weather(move: Mapping, weather: str | None) -> bool:
    if not move.get("weather") or not weather:
        return False
    return weather.lower() in PRIMAL or _weather_name(move["weather"]) == (
        _weather_name(weather)
    )


# the plays valued last, by rule; only late Tailwind is on unless asked for
# (the head-to-head of 21 Nov and the PO's calls of 22 and 23 Nov)
LAST_RULES = (
    "late_tailwind",
    "tailwind_up",
    "weather_set",
    "ally_attack",
    "status_again",
)
DEFAULT_LAST = ("late_tailwind",)


def last_kind(
    a: Action,
    theirs: Sequence[Mapping],
    moves: Mapping,
    our_side: Collection[str] = (),
    weather: str | None = None,
    foes_left: int | None = None,
) -> str | None:
    """The rule that has action `a` valued last, or None: Tailwind when the
    other side has one Pokemon left (`foes_left`, the PO's game 629 turn 17),
    or while its own side's is up (`our_side`); a weather move in that weather
    (`weather`, the field's), unless it does more (Chilly Reception); a
    damaging move into its own partner; a status move into a target that
    already has a status (Yawn: or is drowsy)."""
    if a.kind != "move":
        return None
    m = moves.get(a.move) or {}
    if m.get("sideCondition") == "tailwind":
        if "tailwind" in our_side:
            return "tailwind_up"
        if foes_left == 1:
            return "late_tailwind"
    if a.move not in WEATHER_PLUS and _same_weather(m, weather):
        return "weather_set"
    if a.target is None:
        return None
    if a.target[0] == "ally":
        hits = m.get("category") in ("Physical", "Special")
        return "ally_attack" if hits and a.move not in HEALS_ALLY else None
    t = theirs[a.target[1]] if a.target[1] < len(theirs) else {}
    if m.get("category") == "Status" and m.get("status"):
        return "status_again" if t.get("status") else None
    if m.get("volatileStatus") == "yawn":
        return "status_again" if t.get("status") or t.get("drowsy") else None
    return None


def value_last(
    a: Action,
    theirs: Sequence[Mapping],
    moves: Mapping,
    our_side: Collection[str] = (),
    weather: str | None = None,
    foes_left: int | None = None,
) -> bool:
    """Action `a` is one to value last by any rule (`last_kind`)."""
    return last_kind(a, theirs, moves, our_side, weather, foes_left) is not None


def last_play(
    j: Sequence[Action],
    theirs: Sequence[Mapping],
    moves: Mapping,
    our_side: Collection[str] = (),
    weather: str | None = None,
    foes_left: int | None = None,
    kinds: Collection[str] = LAST_RULES,
) -> bool:
    """A play (one action a Pokemon) is valued last if any of its actions is,
    by one of the rules `kinds`."""
    return any(
        last_kind(a, theirs, moves, our_side, weather, foes_left) in kinds for a in j
    )


# the averaged win model's noise, about a point of win chance (Week 10's
# measure: level 1.00, swing 1.06 for Reg M-C)
NOISE = 0.01


def prefer_over_last(
    ranked: list, lasts: Collection, margin: float = NOISE, valued: int | None = None
) -> list:
    """`ranked` ((play, value, chance), best first; unvalued plays last, NaN)
    with a play valued last not chosen over another valued within `margin` of
    it: that other play moves to the top (the PO, 23 Nov: replayed, the bot's
    late Tailwinds were within a point of other plays). `valued`: how many of
    the first are valued against every reply (the others only screened); only
    those are compared."""
    if not ranked or not lasts or ranked[0][0] not in lasts:
        return ranked
    best = ranked[0][1]
    if best != best:  # nothing valued
        return ranked
    end = len(ranked) if valued is None else min(len(ranked), valued)
    for k in range(1, end):
        j, v, _p = ranked[k]
        if v != v or best - v > margin:
            break
        if j not in lasts:
            return [ranked[k], *ranked[:k], *ranked[k + 1 :]]
    return ranked
