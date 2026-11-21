"""The bot's opponents on the local server (Week 16, Task 3).

- **Random:** poke_env's `RandomPlayer`, a legal choice at random.
- **The strongest move** (`StrongestMovePlayer`): each Pokemon's most damaging
  move, at the foe it damages most, by a rough estimate: power, the same-type
  bonus, the type matchup, the base attacking and defending stats, accuracy,
  and the spread reduction for a move that hits both foes. It Mega Evolves
  when it can, never protects, and switches only when it must (at random).
- **The choice model** (`TypicalBot`): choices drawn as players typically make
  them (the choice, lead, bring and forced-switch models), none valued.
- **The engine at strength 0** (`at_strength_zero`): the bot, with an opponent
  model that expects typical play.

Team preview: random for the strongest move (as for random); drawn from the
lead and bring models for the choice model."""

from __future__ import annotations

import dataclasses
import random
import time
from collections.abc import Sequence
from typing import Any

import numpy as np

from wpa.bot import EngineBot, legal_orders

# --------------------------------------------------------------------------
# The strongest move
# --------------------------------------------------------------------------

_SPREAD = {"allAdjacentFoes", "allAdjacent"}


def _target_name(move) -> str:
    t = getattr(move, "target", None)
    name = getattr(t, "name", str(t or ""))
    # poke_env's Target enum: ALL_ADJACENT_FOES -> allAdjacentFoes
    parts = name.lower().split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def damage_score(user, move, target) -> float:
    """A rough estimate of the damage `move` does to `target`: power, the
    same-type bonus, the type matchup, base attacking over base defending
    stat, accuracy. 0 for a status move."""
    from poke_env.battle import MoveCategory

    if move.category == MoveCategory.STATUS or not move.base_power or target is None:
        return 0.0
    physical = move.category == MoveCategory.PHYSICAL
    atk = user.base_stats["atk" if physical else "spa"]
    dfn = target.base_stats["def" if physical else "spd"]
    stab = 1.5 if move.type in user.types else 1.0
    acc = move.accuracy if isinstance(move.accuracy, float) else 1.0
    return move.base_power * stab * target.damage_multiplier(move) * atk / dfn * acc


def _score(battle, place: int, order) -> float:
    """One place's order: its estimated damage to the other side, less any to
    its own side (a move that hits everyone next to it)."""
    from poke_env.battle import Move

    move = order.order
    if not isinstance(move, Move):
        return -1.0
    user = battle.active_pokemon[place]
    foes = [
        m for m in battle.opponent_active_pokemon if m is not None and not m.fainted
    ]
    kind = _target_name(move)
    if kind in _SPREAD:
        hit = foes
        spread = 0.75 if len(hit) > 1 else 1.0
        total = sum(damage_score(user, move, m) for m in hit) * spread
        if kind == "allAdjacent":
            ally = battle.active_pokemon[1 - place]
            if ally is not None and not ally.fainted:
                total -= damage_score(user, move, ally) * spread
        return total
    if order.move_target in (1, 2):
        foe = battle.opponent_active_pokemon[order.move_target - 1]
        return damage_score(user, move, foe) if foe is not None else -1.0
    if order.move_target == 0 and move.base_power:  # one foe, chosen by Showdown
        return max((damage_score(user, move, m) for m in foes), default=0.0)
    return -1.0  # its own side, or nothing


def strongest_order(battle, rng: random.Random):
    """The strongest-move player's choice: each place's most damaging move at
    the foe it damages most (ties at random), with a Mega Evolution when one
    is allowed; a forced switch, a legal one at random."""
    from poke_env.player.battle_order import DoubleBattleOrder

    legal = legal_orders(battle)
    if any(battle.force_switch) or not legal:
        return rng.choice(legal) if legal else DoubleBattleOrder()
    allowed = {o.message for o in legal}
    valid = battle.valid_orders
    best: list[list] = [[], []]
    for place in (0, 1):
        scored = [(_score(battle, place, o), o) for o in valid[place]]
        top = max((s for s, _ in scored), default=-1.0)
        if top <= 0:  # nothing damaging: any legal choice
            best[place] = list(valid[place])
            continue
        keep = [o for s, o in scored if s >= top - 1e-9]
        megas = [o for o in keep if o.mega]
        best[place] = megas or keep
    pairs = [
        DoubleBattleOrder(a, b)
        for a in best[0]
        for b in best[1]
        if DoubleBattleOrder(a, b).message in allowed
    ]
    if not pairs:  # e.g. both would Mega Evolve: the first keeps it
        pairs = [o for o in legal if o.message.startswith(best[0][0].message)]
    return rng.choice(pairs or legal)


def _player():  # pragma: no cover - poke_env imported only to play
    from poke_env.player import Player

    return Player


class StrongestMovePlayer(_player()):  # type: ignore[misc]  # pragma: no cover
    def __init__(self, *a, seed: int = 0, **kw) -> None:
        super().__init__(*a, **kw)
        self.rng = random.Random(seed)

    def choose_move(self, battle):
        return strongest_order(battle, self.rng)


# --------------------------------------------------------------------------
# The choice model
# --------------------------------------------------------------------------


def draw(mix: Sequence[tuple[Any, float]], rng: np.random.Generator) -> Any:
    """One choice drawn by its chance."""
    p = np.array([q for _, q in mix], dtype=float)
    return mix[int(rng.choice(len(mix), p=p / p.sum()))][0]


class TypicalBot(EngineBot):  # pragma: no cover - plays on a server
    """Plays as players typically do: at team preview the leads drawn from the
    lead model and the back two from the bring model; each turn a choice drawn
    from the choice model's chances over every choice the rules allow; each
    forced switch from the forced-switch model's. Nothing is valued."""

    def __init__(self, *a, seed: int = 0, **kw) -> None:
        kw.setdefault("timed", False)
        super().__init__(*a, **kw)
        self.rng = np.random.default_rng(seed)

    def _preview(self, battle) -> str:
        from wpa.advise import Pick, _own, draw_bring
        from wpa.bot import sheet_idents, team_message
        from wpa.team_sheets import sheets_from_log

        tag = battle.battle_tag
        self.idents[tag] = sheet_idents(battle.last_request)
        start, why = time.monotonic(), ""
        try:
            from wpa.advise import preview_log
            from wpa.bot import their_species

            role = battle.player_role or "p1"
            ptag, plog = preview_log(
                self.paste, their_species(self.lines.get(tag, []), role), self.fmt
            )
            tools = _own(self.tools, self.fmt, plog)
            pick = draw_bring(
                tools.leads,
                tools.bring,
                self.fmt,
                sheets_from_log(plog)["p1"],
                self.rng,
            )
        except Exception as e:
            pick, why = Pick((0, 1), (2, 3)), f"the models failed: {e!r}"
        self.four[tag] = {*pick.leads, *pick.back}
        team = list(battle.team.values())
        for i in self.four[tag]:
            if i < len(team):
                team[i]._selected_in_teampreview = True
        msg = team_message(pick)
        self._record(battle, "preview", start, msg, why)
        return msg

    def _decide(self, battle, token=None):
        from wpa.advise import (
            typical_replacement,
            typical_turn,
            up_to_switch,
            up_to_turn,
        )
        from wpa.bot import (
            decision_kind,
            engine_tag,
            foe_targets,
            live_log,
            order_for,
            pivot_order,
            random_order,
        )
        from wpa.replay import with_sheets

        tag, role = battle.battle_tag, battle.player_role
        idents = self.idents.get(tag) or []
        start, why, joint, kind, log = time.monotonic(), "", None, "turn", ""
        try:
            log = with_sheets(live_log(self.lines.get(tag, []), role), role, self.paste)
            kind = decision_kind(log, battle.force_switch)
            etag, four = engine_tag(tag), self.four.get(tag)
            if kind == "turn":
                mix = typical_turn(
                    etag, up_to_turn(log, None), self.fmt, self.tools, role, four
                )
                joint = draw(mix, self.rng)
            elif kind == "replacement":
                mix = typical_replacement(
                    etag, up_to_switch(log, None), self.fmt, self.tools, role, four
                )
                joint = draw(mix, self.rng)
        except Exception as e:
            why = f"the models failed: {e!r}"
        if kind == "pivot":
            order, w = pivot_order(battle, self.plan.get(tag, {}), idents)
        elif joint is not None:
            foes = (
                foe_targets(log, role, self.tools.tables[self.fmt])
                if kind == "turn"
                else {}
            )
            order, w = order_for(joint, battle, idents, foes)
        else:
            order, w = random_order(battle), ""
        why = "; ".join(x for x in (why, w) if x)
        if not self._live(tag, token, battle):  # its request has passed
            from wpa.bot import Requests

            self._record(battle, "stale", start, "", "the request passed")
            return Requests.NOTHING
        self._record(battle, kind, start, order.message, why)
        return order


# --------------------------------------------------------------------------
# The engine at strength 0
# --------------------------------------------------------------------------


def at_strength_zero(tools):
    """The engine's tools with an opponent model that expects typical play
    (DEFINITIONS §7 at strength 0), in every format and at every rating."""
    by = {
        f: {**own, "strength": 0.0, "rating_line": None}
        for f, own in (tools.by_format or {}).items()
    }
    return dataclasses.replace(tools, strength=0.0, by_format=by, by_role=None)
