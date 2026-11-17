"""The engine as a player (Week 16, Phase 3): it plays whole games on a
Showdown server, on its own.

At each choice it reads its own stream of the game (what Showdown sends that
player), turns it into the log a spectator sees (`live_log`), and asks the
advice for its best play by win chance (`wpa.advise`): the same engine as the
replay report. The opponent's sheet is hidden (the bot denies open team
sheets), so their sets are believed from the usage statistics and what the
game shows. Its own sets, stat points included, it knows.

Only choices Showdown's own request allows are sent: the engine's choice is
looked up among them (`order_for`); one it cannot find is replaced by a legal
choice at random, and the reason kept. The bot never stalls: if the advice
fails, a legal choice is sent and the failure kept.

This module needs poke_env (as `wpa.battle` does) but not vgc_bench."""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from wpa.advise import Pick

# --------------------------------------------------------------------------
# The log as a spectator sees it
# --------------------------------------------------------------------------

_HP = re.compile(r"(\d+)/(\d+)((?: \w+)?)")
_ROLE = re.compile(r"(p[12])[a-d]?: ")


def public_hp(token: str) -> str:
    """A hit-point token of the player's own stream ("37/175 par") as the other
    player and a replay show it. Champions shows floor(100 * hp / max), at
    least 1 while standing, marked at 20 (y over a fifth, r at or under) and
    at 50 (g over half, y at or under): Showdown's `Pokemon.getHealth`."""
    m = _HP.fullmatch(token)
    if not m:
        return token
    hp, top, status = int(m[1]), int(m[2]), m[3]
    if hp == 0:
        return token
    pct = 100 * hp // top or 1
    shown = f"{pct}/100"
    if pct == 20:
        shown += "y" if hp * 5 > top else "r"
    elif pct == 50:
        shown += "g" if hp * 2 > top else "y"
    return shown + status


def public_line(line: str, role: str) -> str | None:
    """One line of the player's stream as a spectator gets it, or None for a
    line only the player gets: a request, the open team sheet question and its
    answers, the private clock line. The player's own hit points are exact in
    its stream and shown as a spectator sees them (`public_hp`)."""
    if not line.startswith("|") or line.startswith("|request|"):
        return None
    if "otsrequest" in line or line.startswith("|inactive|Time left:"):
        return None
    p = line.split("|")
    who = _ROLE.match(p[2]) if len(p) > 3 else None
    if who and who.group(1) == role:
        p = p[:3] + [public_hp(x) for x in p[3:]]
    return "|".join(p)


def live_log(lines: Iterable[str], role: str) -> str:
    """The game so far as a replay's log shows it."""
    kept = (public_line(x, role) for x in lines)
    return "\n".join(x for x in kept if x is not None)


# --------------------------------------------------------------------------
# The bot's own team
# --------------------------------------------------------------------------

_SP_NAMES = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")


def paste_from_packed(packed: str) -> str:
    """A team in Showdown's packed form as a team paste (`replay.parse_team`
    reads it), stat points written as EVs, as Showdown exports them."""
    blocks = []
    for entry in packed.split("]"):
        f = (entry.split("|") + [""] * 12)[:12]
        name, species, item, ability, moves, nature, evs, gender = f[:8]
        head = f"{name} ({species})" if species and species != name else name
        head += f" ({gender})" if gender else ""
        head += f" @ {item}" if item else ""
        out = [head, f"Ability: {ability}", f"Level: {f[10] or 50}"]
        points = [int(x or 0) for x in evs.split(",")] if evs else []
        if any(points):
            out.append(
                "EVs: " + " / ".join(f"{n} {s}" for n, s in zip(points, _SP_NAMES) if n)
            )
        if nature:
            out.append(f"{nature} Nature")
        out += [f"- {m}" for m in moves.split(",") if m]
        blocks.append("\n".join(out))
    return "\n\n".join(blocks)


def team_message(pick: Pick) -> str:
    """Team preview's answer: the four by sheet position, the leads first."""
    return "/team " + "".join(str(i + 1) for i in (*pick.leads, *pick.back))


def engine_tag(battle_tag: str) -> str:
    """The engine's name for a live game: its room without "battle-"."""
    return battle_tag.removeprefix("battle-")


def their_species(lines: Iterable[str], role: str) -> list[str]:
    """The other side's six, as team preview shows them."""
    other = "p2" if role == "p1" else "p1"
    out = []
    for x in lines:
        p = x.split("|")
        if x.startswith("|poke|") and len(p) > 3 and p[2] == other:
            out.append(p[3].split(",")[0].strip())
    return out


def sheet_idents(request: Mapping) -> list[str]:
    """The player's six as Showdown names them ("p1: Arcanine"), in sheet
    order: team preview's request lists them so."""
    return [p["ident"] for p in request["side"]["pokemon"]]


def _name(ident: str) -> str:
    return ident.split(": ", 1)[-1]


# --------------------------------------------------------------------------
# What the bot says to Showdown
# --------------------------------------------------------------------------


def decision_kind(log: str, force_switch: Sequence[bool]) -> str:
    """ "turn" (a turn's start), "replacement" (a switch after something fell,
    at the turn's end) or "pivot" (a switch asked for during the turn: a
    switching move, an Eject Button)."""
    if not any(force_switch):
        return "turn"
    lines = log.rstrip("\n").split("\n")
    starts = [i for i, x in enumerate(lines) if x.startswith("|turn|")]
    after = lines[starts[-1] + 1 :] if starts else lines
    return "replacement" if "|upkeep" in after else "pivot"


def own_places(request: Mapping, idents: Sequence[str]) -> dict[int, int]:
    """Each of the player's Pokemon on the field (sheet position) and its place
    (0: a, 1: b), from Showdown's request: its first two listed are there."""
    out = {}
    for place, p in enumerate(request.get("side", {}).get("pokemon", [])[:2]):
        if p.get("active") and p["ident"] in idents:
            out[idents.index(p["ident"])] = place
    return out


def foe_targets(log: str, role: str, table) -> dict[int, int]:
    """The other side's Pokemon on the field (their sheet position) and
    Showdown's target number for each (1: place a, 2: place b), from the
    engine's own board, so the bot aims where the engine meant."""
    from wpa import decisions as D

    game = D.build_game(log.rstrip("\n") + "\n|\n", table)
    states = game.states.get(role) or []
    if not states:
        return {}
    out = {}
    for j, m in enumerate(states[-1]["opp_pokemon"]):
        if m.get("active") and not m.get("fainted") and m.get("slot") in ("a", "b"):
            out[j] = 1 if m["slot"] == "a" else 2
    return out


def legal_orders(battle) -> list:
    """Every choice Showdown's request allows now, as poke_env reads it."""
    from poke_env.player.battle_order import DoubleBattleOrder

    return DoubleBattleOrder.join_orders(*battle.valid_orders)


def _describe(a, idents: Sequence[str]) -> str:
    def who(i: int | None) -> str:
        if i is not None and 0 <= i < len(idents):
            return _name(idents[i])
        return f"#{i}"

    if a.kind == "switch":
        return f"{who(a.user)} switching to {who(a.switch_to)}"
    aim = f" at {a.target[0]} {a.target[1]}" if a.target else ""
    return f"{who(a.user)} using {a.move}{aim}" + (" with Mega" if a.mega else "")


def _single(a, place: int, options: Sequence, foes, places, idents):
    """The order among `options` (one place's) that is action `a`, or None."""
    from poke_env.battle import Move, Pokemon

    if a.kind == "switch":
        if a.switch_to is None or a.switch_to >= len(idents):
            return None
        name = _name(idents[a.switch_to])
        return next(
            (
                o
                for o in options
                if isinstance(o.order, Pokemon) and o.order.name == name
            ),
            None,
        )
    if a.target is None:  # no target to choose, or itself
        aims: tuple[int, ...] = (0, -(place + 1))
    elif a.target[0] == "foe":
        aims = (foes[a.target[1]],) if a.target[1] in foes else ()
    else:
        ally = places.get(a.target[1])
        aims = (-(ally + 1),) if ally is not None else ()
    for aim in aims:
        for o in options:
            if (
                isinstance(o.order, Move)
                and o.order.id == a.move
                and o.move_target == aim
                and bool(o.mega) == bool(a.mega)
            ):
                return o
    return None


def _fill(chosen: list, valid: Sequence[Sequence]) -> Any:
    """The order with each place left empty filled by a legal choice at
    random that goes with the other; None when none does."""
    from poke_env.player.battle_order import DoubleBattleOrder

    allowed = {
        o.message for o in DoubleBattleOrder.join_orders(list(valid[0]), list(valid[1]))
    }
    firsts = (
        [chosen[0]] if chosen[0] is not None else random.sample(valid[0], len(valid[0]))
    )
    seconds = (
        [chosen[1]] if chosen[1] is not None else random.sample(valid[1], len(valid[1]))
    )
    for x in firsts:
        for y in seconds:
            order = DoubleBattleOrder(x, y)
            if order.message in allowed:
                return order
    return None


def order_for(joint, battle, idents: Sequence[str], foes: Mapping[int, int]):
    """The engine's choice (a joint of `wpa.choices.Action`, sheet positions)
    as one of the choices Showdown's request allows, and why it is not exactly
    the engine's ("" when it is). A place whose action is not among Showdown's
    choices gets a legal one at random; the other place keeps the engine's."""
    from poke_env.player.battle_order import DoubleBattleOrder

    valid = battle.valid_orders
    places = own_places(battle.last_request, idents)
    chosen: list = [None, None]
    why = []
    for a in joint:
        place = places.get(a.user)
        o = None
        if place is not None:
            o = _single(a, place, valid[place], foes, places, idents)
        if o is None or place is None:
            why.append(f"{_describe(a, idents)} is not among Showdown's choices")
        else:
            chosen[place] = o
    for place in (0, 1):  # a place the engine gave nothing: pass, if allowed
        if chosen[place] is None and all(
            o.message == "/choose pass" for o in valid[place]
        ):
            chosen[place] = valid[place][0]
    order = _fill(chosen, valid)
    if order is None:  # the engine's two do not go together
        why.append("its two choices do not go together")
        order = _fill([None, None], valid)
    if order is None:
        return (
            DoubleBattleOrder(),
            "Showdown's request allows nothing",
        )  # pragma: no cover
    if any(c is None for c in chosen) and not why:
        why.append("a place without an action was given one at random")
    return order, "; ".join(why)


def pivot_order(battle, plan: Mapping[int, int], idents: Sequence[str]):
    """A switch asked for during a turn: each place asked brings in the one its
    switching move planned (`plan`: place to sheet position) when Showdown
    allows it; otherwise a legal one at random, with why."""
    from poke_env.battle import Pokemon

    valid = battle.valid_orders
    chosen: list = [None, None]
    why = []
    for place in (0, 1):
        if not battle.force_switch[place]:
            continue
        want = plan.get(place)
        if want is None:
            why.append(f"no planned switch for place {'ab'[place]}")
            continue
        name = _name(idents[want])
        o = next(
            (
                x
                for x in valid[place]
                if isinstance(x.order, Pokemon) and x.order.name == name
            ),
            None,
        )
        if o is None:
            why.append(f"{name} cannot come in")
        chosen[place] = o
    order = _fill(chosen, valid)
    return order, "; ".join(why)


def random_order(battle):
    from poke_env.player import Player

    return Player.choose_random_doubles_move(battle)


# --------------------------------------------------------------------------
# The clock (Week 16 Task 2)
# --------------------------------------------------------------------------

# Showdown's VGC Timer (its data/rulesets.ts): 7 minutes in all for a player's
# choices, at most 55 seconds a turn and 90 for team preview, taken in ticks
# of 5 seconds (server/room-battle.ts) while a choice is awaited
BANK, TURN_MAX, PREVIEW_MAX, TICK = 420, 55, 90, 5
MAX_THINK = 45  # the brief: never over 45 seconds a turn
SHARE = 6  # a turn's time is at most a sixth of what is left
MARGIN = 10  # seconds kept for the setup, the last batch and the message

_LEFT = re.compile(r"\|inactive\|Time left: \d+ sec this turn \| (\d+) sec total")


def think_time(left: float, preview: bool = False) -> float:
    """The time for one choice: a share of the game's clock left, never over
    45 seconds nor so long that the turn's own limit is near; always a moment."""
    limit = (PREVIEW_MAX if preview else TURN_MAX) - MARGIN
    return max(1.0, min(MAX_THINK, limit, left / SHARE))


def clock_left(lines: Iterable[str]) -> int | None:
    """The player's time left in all, as Showdown last told it (a line only the
    player gets, with the timer on); None when it has not."""
    got = None
    for x in lines:
        m = _LEFT.match(x)
        if m:
            got = int(m.group(1))
    return got


def ticks(seconds: float) -> int:
    """What Showdown takes from the clock for a choice made in `seconds`."""
    return int(seconds // TICK) * TICK


class Deadline:
    """The search's stop for one choice (`advise`'s `stop`), called before each
    batch: true once the time is up, or when one more batch half as long
    again as the longest so far would end past it (batches vary)."""

    def __init__(self, budget: float, clock=time.monotonic) -> None:
        self.clock = clock
        self.end = clock() + budget
        self.last: float | None = None
        self.longest = 0.0

    def __call__(self) -> bool:
        now = self.clock()
        if self.last is not None:
            self.longest = max(self.longest, now - self.last)
        self.last = now
        return now + 1.5 * self.longest > self.end


class Clock:
    """One game's clock as the bot counts it, and as Showdown last told it."""

    def __init__(self, bank: int = BANK) -> None:
        self.bank, self.spent = bank, 0

    def spend(self, seconds: float) -> None:
        self.spent += ticks(seconds)

    def left(self, lines: Iterable[str] = ()) -> int:
        own = self.bank - self.spent
        told = clock_left(lines)
        return own if told is None else min(own, told)


# --------------------------------------------------------------------------
# The player
# --------------------------------------------------------------------------


def _player_base():  # pragma: no cover - poke_env imported only to play
    from poke_env.player import Player

    return Player


class EngineBot(_player_base()):  # type: ignore[misc]  # pragma: no cover
    """The engine on a Showdown server. Each choice is worked out in a thread,
    so the connection is answered while it thinks. `timed`: each turn's search
    stops at its time (`think_time`; untimed, the full advice, as measured
    first). `records` gets one row per choice: the game, the kind, seconds, the
    time it had and the clock left, how many plays were compared, valued
    against every reply and against the likeliest only, whether the time ran
    out, and why the choice sent is not exactly the engine's (empty when it
    is)."""

    def __init__(
        self,
        tools,
        packed: str,
        fmt: str = "regmc",
        *,
        records=None,
        timed: bool = True,
        **kw,
    ):
        kw.setdefault("battle_format", f"gen9championsvgc2026{fmt}")
        kw.setdefault("accept_open_team_sheet", False)  # it denies them
        super().__init__(team=packed, **kw)
        self.tools, self.fmt, self.paste = tools, fmt, paste_from_packed(packed)
        self.timed = timed
        self.records: list[dict] = records if records is not None else []
        self.lines: dict[str, list[str]] = {}
        self.idents: dict[str, list[str]] = {}
        self.four: dict[str, set[int]] = {}
        self.plan: dict[str, dict[int, int]] = {}
        self.clocks: dict[str, Clock] = {}

    def set_team(self, packed: str) -> None:
        """The team for its next game."""
        self.update_team(packed)
        self.paste = paste_from_packed(packed)

    async def _handle_battle_message(self, split_messages):
        tag = split_messages[0][0].lstrip(">")
        if tag.startswith("battle-"):
            got = self.lines.setdefault(tag, [])
            got.extend("|".join(m) for m in split_messages[1:] if m)
        await super()._handle_battle_message(split_messages)

    # team preview ---------------------------------------------------------

    def teampreview(self, battle):
        return asyncio.to_thread(self._preview, battle)

    def _preview(self, battle) -> str:
        from wpa.advise import advise_bring, preview_log

        tag, role = battle.battle_tag, battle.player_role or "p1"
        self.idents[tag] = sheet_idents(battle.last_request)
        start, why, compared = time.monotonic(), "", 0
        clock = self.clocks.setdefault(tag, Clock())
        left = clock.left(self.lines.get(tag, []))
        try:
            ptag, plog = preview_log(
                self.paste, their_species(self.lines.get(tag, []), role), self.fmt
            )
            adv = advise_bring(ptag, plog, self.fmt, self.tools, "p1")
            pick, compared = adv.choices[0][0], len(adv.choices)
        except Exception as e:  # never stall: the first four, as listed
            pick, why = Pick((0, 1), (2, 3)), f"the advice failed: {e!r}"
        self.four[tag] = {*pick.leads, *pick.back}
        team = list(battle.team.values())
        for i in self.four[tag]:
            if i < len(team):
                team[i]._selected_in_teampreview = True
        msg = team_message(pick)
        self._record(battle, "preview", start, msg, why, compared=compared, left=left)
        clock.spend(time.monotonic() - start)
        return msg

    # turns and switches ---------------------------------------------------

    def choose_move(self, battle):
        return asyncio.to_thread(self._decide, battle)

    def _decide(self, battle):
        from wpa.advise import advise, advise_replacement, up_to_switch, up_to_turn
        from wpa.replay import with_sheets

        tag, role = battle.battle_tag, battle.player_role
        idents = self.idents.get(tag) or []
        start, joint, why, adv, log = time.monotonic(), None, "", None, ""
        kind = "turn"
        lines = list(self.lines.get(tag, []))
        clock = self.clocks.setdefault(tag, Clock())
        left = clock.left(lines)
        budget = think_time(left) if self.timed else None
        stop = Deadline(budget - (time.monotonic() - start)) if budget else None
        try:
            log = with_sheets(live_log(lines, role), role, self.paste)
            kind = decision_kind(log, battle.force_switch)
            etag = engine_tag(tag)
            if kind == "turn":
                adv = advise(
                    etag,
                    up_to_turn(log, None),
                    self.fmt,
                    self.tools,
                    role,
                    self.four.get(tag),
                    stop=stop,
                )
            elif kind == "replacement":
                adv = advise_replacement(
                    etag,
                    up_to_switch(log, None),
                    self.fmt,
                    self.tools,
                    role,
                    self.four.get(tag),
                )
            if adv is not None:
                joint = adv.choices[0][0]
        except Exception as e:
            why = f"the advice failed: {e!r}"
        if kind == "pivot":
            order, w = pivot_order(battle, self.plan.get(tag, {}), idents)
        elif joint is not None:
            foes = (
                foe_targets(log, role, self.tools.tables[self.fmt])
                if kind == "turn"
                else {}
            )
            order, w = order_for(joint, battle, idents, foes)
            if kind == "turn":
                places = own_places(battle.last_request, idents)
                self.plan[tag] = {
                    places[a.user]: a.switch_to
                    for a in joint
                    if a.kind == "move" and a.switch_to is not None and a.user in places
                }
        else:
            order, w = random_order(battle), ""
        why = "; ".join(x for x in (why, w) if x)
        if order is None:  # pragma: no cover - nothing fits: Showdown's default
            order, why = random_order(battle), why or "no legal choice was found"
        self._record(
            battle,
            kind,
            start,
            order.message,
            why,
            left=left,
            budget=budget,
            compared=adv.compared or len(adv.choices) if adv else 0,
            valued=adv.valued if adv else 0,
            screened=adv.screened if adv else 0,
            stopped=adv.stopped if adv else False,
            weighed=adv.weighed if adv else 0,
            wp=round(adv.wp, 4) if adv else None,
        )
        clock.spend(time.monotonic() - start)
        return order

    def _record(self, battle, kind, start, message, why, **more) -> None:
        self.records.append(
            {
                "battle": battle.battle_tag,
                "turn": battle.turn,
                "kind": kind,
                "seconds": round(time.monotonic() - start, 2),
                "choice": message,
                "why": why,
                **more,
            }
        )
