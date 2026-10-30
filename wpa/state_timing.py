"""What a stored state knows, and when (Week 5 Task 1).

A `BattleState` is a snapshot of the battle taken at the moment a player has to
choose (`vgc_bench.logs2trajs.LogReader.choose_move` copies the battle there).
So the snapshot holds only what had been broadcast up to that choice. Three
facts follow, each checked in tests/test_state_timing.py and measured over a
sample of the real data (docs/STATE-TIMING.md):

1. **Decision points.** Turn 0 holds team preview and the lead choice. Each
   later turn holds one decision at its start (decision_index 0) and one more
   for every forced switch after a knock-out. Those later decisions come *after*
   the turn's moves, so their snapshot already shows the damage.
2. **Observations describe a turn, but hang on its last decision.** The
   parser (`wpa.observations.attach_observations`) puts every event of turn N
   on the state with the highest decision_index of turn N. When turn N has a
   forced switch, that state is after the events, so they are the past. When
   turn N has only its starting decision, the events are attached to the
   snapshot taken *before* them: the future. A model that reads
   `state.observations` there reads the answer.
3. **`outcome` is set only on the final snapshot**, a terminal marker appended
   after the game ends, not a choice anyone made. It is the label and never a
   feature. (A game that ended by forfeit or timeout can have the loser's Pokemon
   still standing in it.)

The rule this module defines for features: a decision at turn N may use
observations from turns before N, and from the snapshot itself. Nothing carried
by a state of turn N. That loses the same-turn events at a forced-switch
decision, which are public then, but the snapshot's own hit points already show
their effect, and the rule can be checked mechanically.

Everything here works on the stored JSON form (plain dicts), so it needs neither
poke_env nor the data folder. Hit points in observations are percentages
(87.0); in the snapshot they are fractions (0.87).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

State = dict
Observation = dict


def load_states(path: Path | str) -> list[State]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def turn_structure(states: Sequence[State]) -> dict[int, tuple[int, ...]]:
    """Turn -> the decision indices recorded in it, in order."""
    out: dict[int, list[int]] = {}
    for s in states:
        out.setdefault(s["turn"], []).append(s["decision_index"])
    return {t: tuple(v) for t, v in out.items()}


def carries_future_observations(states: Sequence[State], k: int) -> bool:
    """True when state k's observations describe events after its snapshot.

    That is the case for a state that has observations and is the only decision
    of its turn: the observations of turn N hang on the last decision of turn N,
    and here the last decision is the one taken before the turn's moves.
    """
    s = states[k]
    if not s.get("observations"):
        return False
    if s["turn"] == 0:
        return False  # leads are already chosen; nothing resolves in turn 0
    return len(turn_structure(states)[s["turn"]]) == 1


def usable_observations(states: Sequence[State], k: int) -> list[Observation]:
    """Observations a decision at state k may use: those of earlier turns.

    Computed from the states up to and including k only, so cutting the game
    after k changes nothing (tested).
    """
    turn = states[k]["turn"]
    out: list[Observation] = []
    for s in states[: k + 1]:
        if s["turn"] < turn:
            out.extend(s.get("observations", ()))
    return out


def _species_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def hp_evidence(state: State, role: str) -> str | None:
    """Does this snapshot already show the hit points its observations report?

    For each Pokemon with an hp-bearing observation (damage, recovery) on this
    state, compare the last reported figure with the snapshot's. "post" if every
    matched Pokemon agrees (the snapshot was taken after the events), "pre" if
    any differs (before them), None if nothing can be matched. `role` is the
    side the snapshot belongs to (p1 or p2).
    """
    last: dict[str, float] = {}
    for o in state.get("observations", ()):
        if o.get("hp_after") is not None and o.get("target"):
            last[o["target"]] = o["hp_after"] / 100.0
    verdicts: list[bool] = []
    for target, hp in last.items():
        side, _, name = target.partition(": ")
        mons = state["our_pokemon"] if side[:2] == role else state["opp_pokemon"]
        wanted = _species_id(name)
        matches = [m for m in mons if m["species"].startswith(wanted)]
        if len(matches) != 1:
            continue
        verdicts.append(abs(matches[0]["hp_fraction"] - hp) < 0.006)
    if not verdicts:
        return None
    return "post" if all(verdicts) else "pre"


def decided_indices(states: Sequence[State]) -> list[int]:
    """Indices of the states whose game is already decided (outcome set)."""
    return [k for k, s in enumerate(states) if s["outcome"] is not None]


def terminal_index(states: Sequence[State]) -> int | None:
    """Index of the terminal snapshot: the one state with an outcome.

    It is appended after the game ends, is not a choice anyone made, and carries
    the final turn's observations. Models are never asked to score it (the v0
    baseline sets the same states aside as "decided").
    """
    decided = decided_indices(states)
    return decided[0] if len(decided) == 1 else None


def decision_indices(states: Sequence[State]) -> list[int]:
    """The states a model is asked to score: every snapshot except the terminal."""
    end = terminal_index(states)
    return [k for k in range(len(states)) if k != end]


def loser_has_pokemon_left(state: State) -> bool:
    """True when the side that lost still shows a Pokemon with hit points.

    Only possible when the game ended by forfeit or timeout. The label is still
    the real result; this is for counting how often it happens.
    """
    if state["outcome"] is None:
        raise ValueError("not a terminal snapshot")
    loser = state["opp_pokemon"] if state["outcome"] else state["our_pokemon"]
    return any(p["hp_fraction"] > 0 for p in loser)


# --------------------------------------------------------------------------
# Audit over many files
# --------------------------------------------------------------------------

import hashlib  # noqa: E402
from collections import Counter  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402


def kind_of_name(name: str) -> str:
    """'gen9championsvgc2026regmabo3-123-p1.json' -> 'regmabo3'."""
    return name.split("-", 1)[0].removeprefix("gen9championsvgc2026")


def in_sample(name: str, one_in: int) -> bool:
    """Deterministic sample of games: both players of a game go together."""
    stem = name.removesuffix(".json").rsplit("-", 1)[0]
    digest = hashlib.sha256(stem.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % one_in == 0


@dataclass
class Audit:
    by_kind: dict[str, Counter] = field(default_factory=dict)

    def _total(self, key: str) -> int:
        return sum(c[key] for c in self.by_kind.values())

    files = property(lambda self: self._total("files"))
    states = property(lambda self: self._total("states"))
    decision_states = property(lambda self: self._total("decision_states"))
    flagged_states = property(lambda self: self._total("flagged_states"))
    forfeit_like = property(lambda self: self._total("forfeit_like"))
    pre_but_unflagged = property(lambda self: self._total("pre_but_unflagged"))
    files_with_one_terminal_last = property(
        lambda self: self._total("one_terminal_last")
    )

    def add(self, kind: str, role: str, states: Sequence[State]) -> None:
        c = self.by_kind.setdefault(kind, Counter())
        c["files"] += 1
        c["states"] += len(states)
        end = terminal_index(states)
        if end == len(states) - 1:
            c["one_terminal_last"] += 1
            if loser_has_pokemon_left(states[-1]):
                c["forfeit_like"] += 1
        structure = turn_structure(states)
        for turn, ds in structure.items():
            if turn == 0:
                continue
            c["turns_one_decision" if len(ds) == 1 else "turns_several_decisions"] += 1
        for k in decision_indices(states):
            s = states[k]
            c["decision_states"] += 1
            if s["turn"] > 0 and s["decision_index"] > 0:
                c["later_decisions_in_a_turn"] += 1
            has_obs = bool(s.get("observations"))
            c["decision_states_with_obs"] += has_obs
            flagged = carries_future_observations(states, k)
            c["flagged_states"] += flagged
            if flagged:
                c["flagged_obs_events"] += len(s["observations"])
            ev = hp_evidence(s, role)
            if ev is not None:
                c["evidence_" + ev] += 1
                c["evidence_" + ev + ("_flagged" if flagged else "_unflagged")] += 1
                if ev == "pre" and not flagged:
                    c["pre_but_unflagged"] += 1

    def describe(self) -> str:
        out = ["=== state timing audit ==="]
        by_format: dict[str, Counter] = {}
        for kind, c in self.by_kind.items():
            by_format.setdefault(kind.removesuffix("bo3"), Counter()).update(c)
        for title, groups in (("by format", by_format), ("by file kind", self.by_kind)):
            out.append(f"-- {title}")
            for name in sorted(groups):
                c = groups[name]
                d = c["decision_states"] or 1
                ev = (c["evidence_post"] + c["evidence_pre"]) or 1
                out += [
                    f"{name}: {c['files']} files, {c['states']} states "
                    f"({c['decision_states']} decision points, "
                    f"{c['files'] - c['one_terminal_last']} files without exactly "
                    f"one terminal state last)",
                    f"  decision points with observations: "
                    f"{c['decision_states_with_obs']} "
                    f"({c['decision_states_with_obs'] / d:.1%}); of those, "
                    f"carrying events from AFTER the decision: "
                    f"{c['flagged_states']} ({c['flagged_states'] / d:.1%} of all "
                    f"decision points; {c['flagged_obs_events']} events)",
                    f"  hit-point evidence: snapshot after its events "
                    f"{c['evidence_post']}, before {c['evidence_pre']} "
                    f"({c['evidence_pre'] / ev:.1%} before); "
                    f"before-but-not-flagged: {c['pre_but_unflagged']}",
                    f"  turns with one decision: {c['turns_one_decision']}, "
                    f"with several: {c['turns_several_decisions']}; "
                    f"later decisions within a turn: {c['later_decisions_in_a_turn']}",
                    f"  games ended with the loser's Pokemon still standing "
                    f"(forfeit or timeout): {c['forfeit_like']} files "
                    f"({c['forfeit_like'] / (c['files'] or 1):.1%})",
                ]
        return "\n".join(out) + "\n"


def audit_files(paths: Iterable[Path | str]) -> Audit:
    audit = Audit()
    for path in paths:
        p = Path(path)
        role = p.stem.rsplit("-", 1)[1]
        audit.add(kind_of_name(p.name), role, load_states(p))
    return audit


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Audit what stored states know (Week 5 Task 1)."
    )
    parser.add_argument("--states", type=Path, default=Path("wpa_states"))
    parser.add_argument(
        "--one-in", type=int, default=100, help="read one game in this many"
    )
    args = parser.parse_args()
    names = []
    with os.scandir(args.states) as it:
        for e in it:
            if e.name.endswith(".json") and in_sample(e.name, args.one_in):
                names.append(e.name)
    names.sort()
    print(audit_files(args.states / n for n in names).describe())


if __name__ == "__main__":
    main()
