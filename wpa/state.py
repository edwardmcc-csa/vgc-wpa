"""Our own battle state schema, plus adapters to and from vgc-bench's formats.

This module is additive only: it imports vgc_bench/poke_env classes but never
edits them, so upstream fixes to the fork can be pulled cleanly. Two separate
adapters live here, because vgc-bench exposes two different "their format"s:

- WpaTrajectory adapts to/from imitation.data.types.Trajectory, the packed
  float-embedding format that vgc_bench.logs2trajs persists to trajs/*.pkl.
  That embedding does not retain raw turn numbers or win/loss outcome, so it
  is round-tripped as opaque arrays (see test_adapter.py).
- BattleState.from_battle / parse_battle_states adapt from the semantic
  DoubleBattle objects vgc_bench's own LogReader produces while replaying a
  raw log, before it embeds them. That is where HP, turn, fainted, and
  outcome actually live, so invariant checks run against this (see
  test_invariants.py).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from imitation.data.types import Trajectory
from poke_env.battle import DoubleBattle, Pokemon
from poke_env.ps_client import AccountConfiguration

from vgc_bench.logs2trajs import LogReader


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

    @classmethod
    def from_battle(cls, battle: DoubleBattle) -> "BattleState":
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
            turn=battle.turn, our_pokemon=our, opp_pokemon=opp, outcome=battle.won
        )


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

    player = LogReader(
        account_configuration=AccountConfiguration(username, None),
        battle_format=tag.split("-")[0],
        log_level=51,
        accept_open_team_sheet=True,
        loop=loop,
    )
    future = asyncio.run_coroutine_threadsafe(player.follow_log(tag, log), loop)
    future.result()
    return [BattleState.from_battle(battle) for battle in player.states]
