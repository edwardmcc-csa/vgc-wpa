"""Our own battle state schema, plus adapters to and from vgc-bench's formats.

This module is additive only: it imports vgc_bench/poke_env classes but never
edits them, so upstream fixes to the fork can be pulled cleanly. Two separate
adapters live here, because vgc-bench exposes two different "their format"s:

- WpaTrajectory adapts to/from imitation.data.types.Trajectory, the packed
  float-embedding format that vgc_bench.logs2trajs persists to trajs/*.pkl.
  That embedding does not retain raw turn numbers or win/loss outcome, so it
  is round-tripped as opaque arrays (see test_adapter.py).
- BattleState.from_battle adapts from the semantic DoubleBattle objects
  poke-env produces, live or replayed - the same object type either way, so
  the same method covers both (see test_live_roundtrip.py, which asserts
  this directly rather than assuming it). That is where HP, turn, fainted,
  and outcome actually live, so invariant checks run against this (see
  test_invariants.py). parse_battle_states adapts from a raw replay log via
  vgc-bench's own LogReader, before it embeds states into the packed format
  above; wpa/battle.py's capture_live_states adapts from a live connection.

BattleState also carries best-of-3 set context (set_id, game_index,
set_score_entering_game), per docs/DEFINITIONS.md #11.6 and #13. vgc-bench's
own parser does not surface this - it's sitting unused in every bo3 log's
`|uhtml|bestof|` message (replay) and the live best-of-message protocol hook
(live), extracted here rather than there.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, fields

import numpy as np
import numpy.typing as npt
from imitation.data.types import Trajectory
from poke_env.battle import DoubleBattle, Pokemon
from poke_env.ps_client import AccountConfiguration

from vgc_bench.logs2trajs import LogReader

_BESTOF_LOG_RE = re.compile(
    r"<strong>Game (\d+)</strong> of <a href=\"/game-bestof3-([^\"]+)\""
)


@dataclass(frozen=True)
class PokemonState:
    """Our schema for a single Pokemon at one decision point."""

    species: str
    hp_fraction: float
    fainted: bool
    active: bool

    @classmethod
    def from_pokemon(cls, pokemon: Pokemon, active: bool) -> "PokemonState":
        return cls(
            species=pokemon.species,
            hp_fraction=pokemon.current_hp_fraction,
            fainted=pokemon.fainted,
            active=active,
        )


@dataclass(frozen=True)
class BattleState:
    """Our schema for one decision point in a parsed battle."""

    turn: int
    our_pokemon: tuple[PokemonState, ...]
    opp_pokemon: tuple[PokemonState, ...]
    outcome: bool | None
    """True if this side won, False if it lost, None if not yet decided."""
    set_id: str | None = None
    """Identifies the best-of-3 set this game belongs to, or None outside
    bo3. Not a vgc-bench concept - derived here from the raw protocol (see
    module docstring)."""
    game_index: int | None = None
    """1, 2, or 3 within the set; None outside bo3."""
    set_score_entering_game: tuple[int, int] | None = None
    """(our wins, opponent wins) before this game started. Always known for
    games 1 (0, 0) and 3 (1, 1) - a bo3 only reaches a third game at 1-1.
    Game 2 requires knowing game 1's actual winner: always known live (we
    played it), not always known when replaying the historical corpus,
    where some sets are missing their earlier game's log - None in that
    case rather than a guess."""

    @classmethod
    def from_battle(
        cls,
        battle: DoubleBattle,
        *,
        set_id: str | None = None,
        game_index: int | None = None,
        set_score_entering_game: tuple[int, int] | None = None,
    ) -> "BattleState":
        our_actives = [p for p in battle.active_pokemon if p is not None]
        our = tuple(
            PokemonState.from_pokemon(p, active=any(p is a for a in our_actives))
            for p in battle.team.values()
        )
        opp_actives = [p for p in battle.opponent_active_pokemon if p is not None]
        opp = tuple(
            PokemonState.from_pokemon(p, active=any(p is a for a in opp_actives))
            for p in battle.opponent_team.values()
        )
        return cls(
            turn=battle.turn,
            our_pokemon=our,
            opp_pokemon=opp,
            outcome=battle.won,
            set_id=set_id,
            game_index=game_index,
            set_score_entering_game=set_score_entering_game,
        )

    def to_dict(self) -> dict:
        """Serialize to plain JSON-safe types."""
        return {
            "turn": self.turn,
            "our_pokemon": [
                {f.name: getattr(p, f.name) for f in fields(p)}
                for p in self.our_pokemon
            ],
            "opp_pokemon": [
                {f.name: getattr(p, f.name) for f in fields(p)}
                for p in self.opp_pokemon
            ],
            "outcome": self.outcome,
            "set_id": self.set_id,
            "game_index": self.game_index,
            "set_score_entering_game": (
                list(self.set_score_entering_game)
                if self.set_score_entering_game is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BattleState":
        score = d["set_score_entering_game"]
        return cls(
            turn=d["turn"],
            our_pokemon=tuple(PokemonState(**p) for p in d["our_pokemon"]),
            opp_pokemon=tuple(PokemonState(**p) for p in d["opp_pokemon"]),
            outcome=d["outcome"],
            set_id=d["set_id"],
            game_index=d["game_index"],
            set_score_entering_game=tuple(score) if score is not None else None,
        )


def extract_bo3_context(
    log: str,
) -> tuple[str | None, int | None, tuple[int, int] | None]:
    """
    Pull best-of-3 set id, game index, and (where derivable) the set score
    entering this game out of a raw replay log's `|uhtml|bestof|` banner.

    Set id and game index are recoverable from every bo3 log (verified
    against the full corpus - see docs/DEFINITIONS.md #11.6 investigation).
    Score entering the game is always derivable for game 1 (0, 0) and game
    3 (1, 1) - a bo3 only reaches a third game at 1-1 - but game 2 needs
    game 1's actual result, which a single log doesn't carry; None there.
    """
    match = _BESTOF_LOG_RE.search(log)
    if not match:
        return None, None, None
    game_index = int(match.group(1))
    set_id = match.group(2)
    if game_index == 1:
        score = (0, 0)
    elif game_index == 3:
        score = (1, 1)
    else:
        score = None
    return set_id, game_index, score


@dataclass
class WpaTrajectory:
    """Our schema wrapping vgc-bench's persisted Trajectory format."""

    observations: npt.NDArray[np.float32]
    actions: npt.NDArray[np.int64]
    terminal: bool

    @classmethod
    def from_vgc_bench(cls, traj: Trajectory) -> "WpaTrajectory":
        return cls(
            observations=np.array(traj.obs, dtype=np.float32, copy=True),
            actions=np.array(traj.acts, dtype=np.int64, copy=True),
            terminal=bool(traj.terminal),
        )

    def to_vgc_bench(self) -> Trajectory:
        return Trajectory(
            obs=np.array(self.observations, dtype=np.float32, copy=True),
            acts=np.array(self.actions, dtype=np.int64, copy=True),
            infos=None,
            terminal=self.terminal,
        )


def parse_battle_states(
    tag: str, log: str, role: str, loop: asyncio.AbstractEventLoop
) -> list[BattleState]:
    """
    Replay a raw Showdown battle log with vgc-bench's own LogReader
    (unmodified) and return the sequence of semantic snapshots, one per
    decision point, for invariant checking.

    Mirrors vgc_bench.logs2trajs.process_log's setup, but keeps the
    LogReader instance around afterwards to read its raw `states` list
    instead of the embedded Trajectory process_log returns.
    """
    start_index = log.index(f"|player|{role}|")
    end_index = log.index("\n", start_index)
    username = log[start_index:end_index].split("|")[3]

    set_id, game_index, score = extract_bo3_context(log)

    player = LogReader(
        account_configuration=AccountConfiguration(username, None),
        battle_format=tag.split("-")[0],
        log_level=51,
        accept_open_team_sheet=True,
        loop=loop,
    )
    future = asyncio.run_coroutine_threadsafe(player.follow_log(tag, log), loop)
    future.result()
    return [
        BattleState.from_battle(
            battle, set_id=set_id, game_index=game_index, set_score_entering_game=score
        )
        for battle in player.states
    ]
