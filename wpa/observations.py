"""Spread-revealing observations, per docs/DEFINITIONS.md #14 (Week 3
Amendment 1).

Open team sheets remove composition uncertainty (species, item, ability,
moves, Tera type) but not stat uncertainty (EVs, IVs, nature - and
therefore speed tier and effective bulk). Those are exactly the quantities
that decide whether a line of play was correct, so the parsed record needs
to carry what has been revealed about them, at the (turn, decision_index)
where it was revealed. This module captures that evidence. It does not
interpret it: no bounds, no speed-tier solving, no spread fitting. That is
M4b's job, and it must be reproducible from what's captured here alone.

**Before reading further:** the corpus's HP is percentage-only. Every
`|-damage|` and `|-heal|` figure in all 88,905 battles is expressed as a
percentage of max HP (denominator always 100, checked exhaustively, not
sampled) - never the exact remaining HP a real client sometimes shows its
own side. This is exactly the stop condition the amendment names: "if the
HP expression turns out to be percentage-only on both sides throughout the
corpus... a decision for the product owner, not something to work around."
Flagged and the product owner chose to proceed with `hp_expression`
hardcoded to `"percentage"` rather than narrowing scope - see the Task 10
report. It is not computed per event because there is nothing to compute:
the corpus has no exact figures to distinguish it from.

Every event type below is extracted from literal, single-purpose protocol
messages (`|-damage|`, `|-heal|`, `|faint|`, `|-weather|`, `|-fieldstart|`,
`|-sidestart|`, `|-terastallize|`, `|-enditem|`, `|-ability|...|boost`) -
each a direct broadcast of something that happened, not a derived
quantity. Context fields (weather/fields/side_conditions) are tracked by
replaying those same broadcast messages in log order, not by reading
poke-env's battle object - this keeps extraction a pure function of the
text, independent of vgc_bench's own state machine.

Not implemented this pass, flagged rather than silently skipped: per-event
active stat boosts and a running "items/abilities revealed so far" set.
Both are watchable the same way (they're broadcast messages too) but
weren't in this task's critical path; a real gap if M4b needs them, not a
correctness bug in what is captured.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, replace

from poke_env import to_id_str
from poke_env.battle import Move

from wpa.state import BattleState

_DAMAGE_CATEGORY = "damage"
_MOVE_ORDER_CATEGORY = "move_order"
_SURVIVAL_CATEGORY = "survival"
_RECOVERY_CATEGORY = "recovery"
_BEHAVIORAL_TELL_CATEGORY = "behavioral_tell"
_TERA_ACTIVATION_CATEGORY = "tera_activation"

_PERCENTAGE = "percentage"


@dataclass(frozen=True)
class Observation:
    """One spread-revealing event, attached to the (turn, decision_index)
    of the BattleState it occurred alongside - see docs/DEFINITIONS.md #14.
    """

    turn: int
    decision_index: int
    category: str
    actor: str | None
    target: str | None
    move: str | None = None
    priority: int | None = None
    sequence_index: int | None = None
    """0-indexed order this event's move was chosen among others in the
    same turn, in log order - log order is execution order, so this is
    the primary directly-observed speed-tier signal (DEFINITIONS #14)."""
    hp_after: float | None = None
    hp_expression: str | None = None
    """"percentage" or "exact" - populated whenever hp_after is not None,
    never left null (DEFINITIONS #14). Always "percentage" in this corpus;
    see module docstring."""
    fainted: bool | None = None
    hit_multiple_targets: bool | None = None
    weather: str | None = None
    fields: tuple[str, ...] = ()
    side_conditions: tuple[str, ...] = ()
    tera_type: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "decision_index": self.decision_index,
            "category": self.category,
            "actor": self.actor,
            "target": self.target,
            "move": self.move,
            "priority": self.priority,
            "sequence_index": self.sequence_index,
            "hp_after": self.hp_after,
            "hp_expression": self.hp_expression,
            "fainted": self.fainted,
            "hit_multiple_targets": self.hit_multiple_targets,
            "weather": self.weather,
            "fields": list(self.fields),
            "side_conditions": list(self.side_conditions),
            "tera_type": self.tera_type,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        return cls(
            turn=d["turn"],
            decision_index=d["decision_index"],
            category=d["category"],
            actor=d["actor"],
            target=d["target"],
            move=d["move"],
            priority=d["priority"],
            sequence_index=d["sequence_index"],
            hp_after=d["hp_after"],
            hp_expression=d["hp_expression"],
            fainted=d["fainted"],
            hit_multiple_targets=d["hit_multiple_targets"],
            weather=d["weather"],
            fields=tuple(d["fields"]),
            side_conditions=tuple(d["side_conditions"]),
            tera_type=d["tera_type"],
            note=d["note"],
        )


def _parse_hp(hp_field: str) -> tuple[float | None, bool]:
    """Returns (hp_value, fainted). hp_field is like "94/100" or "0 fnt" -
    a faint always reports bare "0", never "0/100"."""
    fainted = hp_field.endswith("fnt")
    numeric = hp_field.split(" ")[0]
    if numeric == "0":
        return 0.0, fainted
    if "/" not in numeric:
        return None, fainted
    num, _, _ = numeric.partition("/")
    try:
        return float(num), fainted
    except ValueError:
        return None, fainted


def _move_priority(move_name: str) -> int | None:
    try:
        return Move(to_id_str(move_name), gen=9).priority
    except Exception:
        return None


def _short_field_name(tag: str) -> str:
    # "move: Electric Terrain" -> "Electric Terrain"; already-bare names
    # (e.g. a plain condition id) pass through unchanged.
    return tag.split(": ", 1)[-1] if ": " in tag else tag


def _side_key(side_field: str) -> str:
    # "p1: username" -> "p1"
    return side_field.split(":", 1)[0].strip()


def extract_observations(log: str, states: list[BattleState]) -> list[Observation]:
    """
    Replay the raw protocol log's own broadcast messages (not vgc-bench's
    battle object) to extract spread-revealing observations, each attached
    to the (turn, decision_index) of the state it occurred alongside.

    `states` must already have decision_index assigned (i.e. have been
    through assign_decision_indices) - used only to build the turn ->
    decision_index lookup, not otherwise consulted.
    """
    turn_to_decision_index: dict[int, int] = {}
    for state in states:
        turn_to_decision_index[state.turn] = max(
            turn_to_decision_index.get(state.turn, state.decision_index),
            state.decision_index,
        )
    known_turns = sorted(turn_to_decision_index)

    def decision_index_for(turn: int) -> int:
        if not known_turns:
            return 0
        i = bisect.bisect_right(known_turns, turn)
        matched_turn = known_turns[i - 1] if i > 0 else known_turns[0]
        return turn_to_decision_index[matched_turn]

    observations: list[Observation] = []
    current_turn = 0
    sequence_index = 0
    current_weather: str | None = None
    current_fields: set[str] = set()
    current_side_conditions: dict[str, set[str]] = {"p1": set(), "p2": set()}
    last_move: dict | None = None
    last_damage_fainted_target: str | None = None

    def emit(**kwargs) -> None:
        observations.append(
            Observation(
                turn=current_turn,
                decision_index=decision_index_for(current_turn),
                weather=current_weather,
                fields=tuple(sorted(current_fields)),
                side_conditions=tuple(
                    f"{side}:{cond}"
                    for side, conds in current_side_conditions.items()
                    for cond in sorted(conds)
                ),
                **kwargs,
            )
        )

    for line in log.split("\n"):
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        msg_type = parts[1]

        if msg_type == "turn":
            current_turn = int(parts[2])
            sequence_index = 0

        elif msg_type == "move":
            actor = parts[2]
            move_name = parts[3]
            target = parts[4] if len(parts) > 4 and parts[4] else None
            spread_slots = next(
                (p[len("[spread] ") :] for p in parts[5:] if p.startswith("[spread]")),
                None,
            )
            hit_multiple_targets = (
                spread_slots is not None and "," in spread_slots.strip(", ")
            )
            last_move = {
                "actor": actor,
                "move": move_name,
                "hit_multiple_targets": hit_multiple_targets,
            }
            emit(
                category=_MOVE_ORDER_CATEGORY,
                actor=actor,
                target=target,
                move=move_name,
                priority=_move_priority(move_name),
                sequence_index=sequence_index,
                hit_multiple_targets=hit_multiple_targets,
            )
            sequence_index += 1

        elif msg_type == "-damage":
            target = parts[2]
            hp_value, fainted = _parse_hp(parts[3])
            from_tag = next((p for p in parts[4:] if p.startswith("[from]")), None)
            if from_tag is None and last_move is not None:
                actor = last_move["actor"]
                move_name = last_move["move"]
                hit_multiple_targets = last_move["hit_multiple_targets"]
                note = None
            else:
                actor = None
                move_name = None
                hit_multiple_targets = None
                note = from_tag[len("[from] ") :] if from_tag else None
            emit(
                category=_DAMAGE_CATEGORY,
                actor=actor,
                target=target,
                move=move_name,
                hp_after=hp_value,
                hp_expression=_PERCENTAGE if hp_value is not None else None,
                fainted=fainted,
                hit_multiple_targets=hit_multiple_targets,
                note=note,
            )
            last_damage_fainted_target = target if fainted else None

        elif msg_type == "-heal":
            target = parts[2]
            hp_value, _ = _parse_hp(parts[3])
            from_tag = next((p for p in parts[4:] if p.startswith("[from]")), None)
            of_tag = next((p for p in parts[4:] if p.startswith("[of]")), None)
            emit(
                category=_RECOVERY_CATEGORY,
                actor=of_tag[len("[of] ") :] if of_tag else None,
                target=target,
                hp_after=hp_value,
                hp_expression=_PERCENTAGE if hp_value is not None else None,
                note=from_tag[len("[from] ") :] if from_tag else None,
            )

        elif msg_type == "faint":
            pokemon = parts[2]
            if pokemon != last_damage_fainted_target:
                emit(
                    category=_SURVIVAL_CATEGORY,
                    actor=None,
                    target=pokemon,
                    hp_after=0.0,
                    hp_expression=_PERCENTAGE,
                    fainted=True,
                )
            last_damage_fainted_target = None

        elif msg_type == "-weather":
            weather_name = parts[2]
            if any(p.startswith("[upkeep]") for p in parts[3:]):
                continue
            current_weather = None if weather_name == "none" else weather_name

        elif msg_type == "-fieldstart":
            current_fields.add(_short_field_name(parts[2]))

        elif msg_type == "-fieldend":
            current_fields.discard(_short_field_name(parts[2]))

        elif msg_type == "-sidestart":
            side = _side_key(parts[2])
            current_side_conditions[side].add(_short_field_name(parts[3]))

        elif msg_type == "-sideend":
            side = _side_key(parts[2])
            current_side_conditions[side].discard(_short_field_name(parts[3]))

        elif msg_type == "-terastallize":
            actor = parts[2]
            tera_type = parts[3]
            emit(
                category=_TERA_ACTIVATION_CATEGORY,
                actor=actor,
                target=None,
                tera_type=tera_type,
            )

        elif msg_type == "-enditem":
            actor = parts[2]
            item = parts[3]
            emit(
                category=_BEHAVIORAL_TELL_CATEGORY,
                actor=actor,
                target=None,
                note=f"enditem:{item}",
            )

        elif msg_type == "-ability" and len(parts) > 4 and parts[4]:
            actor = parts[2]
            ability = parts[3]
            emit(
                category=_BEHAVIORAL_TELL_CATEGORY,
                actor=actor,
                target=None,
                note=f"ability_trigger:{ability}",
            )

    return observations


def attach_observations(
    states: list[BattleState], observations: list[Observation]
) -> list[BattleState]:
    """Group observations onto the state sharing their (turn, decision_index).

    Observations hang off the existing state record rather than forming a
    parallel structure - the same rule that governs the live/replay path
    (DEFINITIONS #14, Week 3 Amendment 1).
    """
    by_key: dict[tuple[int, int], list[Observation]] = {}
    for obs in observations:
        by_key.setdefault((obs.turn, obs.decision_index), []).append(obs)
    return [
        replace(
            state,
            observations=tuple(by_key.get((state.turn, state.decision_index), ())),
        )
        for state in states
    ]
