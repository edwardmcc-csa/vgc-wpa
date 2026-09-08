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
from dataclasses import dataclass, fields, replace

import numpy as np
import numpy.typing as npt
from imitation.data.types import Trajectory
from poke_env.battle import DoubleBattle, Pokemon
from poke_env.ps_client import AccountConfiguration

from vgc_bench.logs2trajs import LogReader

_BESTOF_LOG_RE = re.compile(
    r"<strong>Game (\d+)</strong> of <a href=\"/game-bestof3-([^\"]+)\""
)

# The scoreboard table shown at the start of every bo3 game. Real markup
# (from pokemon-showdown itself) omits the closing </td> before the </tr>
# on the name row - matched as-is rather than "corrected".
_SCORE_TABLE_RE = re.compile(
    r'<table width="100%"><tr><td align="left">[^<]*</td>'
    r'<td align="right">[^<]*</tr>'
    r'<tr><td align="left">(?P<p1_circles>.*?)</td>'
    r'<td align="right">(?P<p2_circles>.*?)</tr></table>'
)


@dataclass(frozen=True)
class PokemonState:
    """Our schema for a single Pokemon at one decision point."""

    species: str
    hp_fraction: float
    fainted: bool
    active: bool
    gimmick: str | None = None
    """Which format gimmick this Pokemon is currently using, if any: "mega",
    "tera", or "dynamax". Which gimmick(s) a format allows is a fact about
    the format (config), not this schema - e.g. M-A/M-B/M-C disable
    Terastallization entirely and use Mega Evolution instead (see the Week
    2 Task 5 report), but a future regulation may differ. Kept generic so
    that needs no schema change."""

    @classmethod
    def from_pokemon(
        cls, pokemon: Pokemon, active: bool, side_used_mega_evolve: bool = False
    ) -> "PokemonState":
        # Mega Evolution deliberately does not change poke-env's `species`
        # (Pokemon.forme_change/mega_evolve both call _update_from_pokedex
        # with store_species=False - species is a stable identity across
        # forme changes by design). So this can't be species-string matching
        # - confirmed empirically: replaying a real mega-evolution log left
        # `species` as the base form on every subsequent turn, while
        # `ability` visibly changed to the Mega's signature ability. The
        # reliable per-side signal is the same public flag vgc_bench's own
        # PolicyPlayer.embed_side already uses (battle.used_mega_evolve /
        # .opponent_used_mega_evolve); combined with holding a Mega Stone
        # (real Mega Stones are always named "<species>ite") to attribute it
        # to the right Pokemon on that side.
        if pokemon.is_terastallized:
            gimmick = "tera"
        elif pokemon.is_dynamaxed:
            gimmick = "dynamax"
        elif (
            side_used_mega_evolve
            and pokemon.item is not None
            and pokemon.item.endswith("ite")
        ):
            gimmick = "mega"
        else:
            gimmick = None
        return cls(
            species=pokemon.species,
            hp_fraction=pokemon.current_hp_fraction,
            fainted=pokemon.fainted,
            active=active,
            gimmick=gimmick,
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
    decision_index: int = 0
    """Position of this decision point among others sharing the same turn
    number - 0 for the first, 1 for the second, and so on. A game turn can
    hold multiple decision points (DEFINITIONS #6: team preview, lead
    selection, a forced switch after a faint), so `turn` alone doesn't
    order them. The pair (turn, decision_index) strictly increases across
    a whole game - assign_decision_indices computes it; not populated by
    from_battle directly, since a single state has no notion of its
    neighbours."""

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
            PokemonState.from_pokemon(
                p,
                active=any(p is a for a in our_actives),
                side_used_mega_evolve=battle.used_mega_evolve,
            )
            for p in battle.team.values()
        )
        opp_actives = [p for p in battle.opponent_active_pokemon if p is not None]
        opp = tuple(
            PokemonState.from_pokemon(
                p,
                active=any(p is a for a in opp_actives),
                side_used_mega_evolve=battle.opponent_used_mega_evolve,
            )
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
            "decision_index": self.decision_index,
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
            decision_index=d.get("decision_index", 0),
        )


def assign_decision_indices(states: list[BattleState]) -> list[BattleState]:
    """Populate decision_index over one trajectory's states, in order.

    Must be called on a single trajectory's states only - concatenating
    states from unrelated battles first would let a coincidental turn
    match at the boundary continue the previous battle's counter instead
    of resetting it.
    """
    result = []
    last_turn = None
    index = 0
    for state in states:
        if state.turn != last_turn:
            index = 0
            last_turn = state.turn
        else:
            index += 1
        result.append(replace(state, decision_index=index))
    return result


def extract_bo3_context(
    log: str,
) -> tuple[str | None, int | None, tuple[int, int] | None]:
    """
    Pull best-of-3 set id, game index, and the set score entering this game
    out of a raw replay log.

    Set id and game index come from the `|uhtml|bestof|` banner and are
    recoverable from every bo3 log (verified against the full corpus - see
    docs/DEFINITIONS.md #11.6 investigation).

    Score entering the game comes from the log's own scoreboard table -
    `<i class="fa fa-circle">` per game won, `fa fa-circle-o` per game not
    yet won, in (p1, p2) column order (verified: the left column is always
    p1, confirmed against 200 logs; the one apparent exception found was an
    HTML-escaped apostrophe in a username, not a column swap). This covers
    every game index, including 2: earlier revisions of this function
    derived score from universal rules alone (game 1 is always 0-0, game 3
    is always 1-1, since a bo3 only reaches a third game at 1-1) and left
    game 2 as None, since a single log in isolation can't see game 1's
    result via its own |win| line. That gap doesn't actually exist - the
    running score is encoded directly in every game's own log, game 2
    included, so the universal rules are no longer needed except as a
    cross-check.
    """
    match = _BESTOF_LOG_RE.search(log)
    if not match:
        return None, None, None
    game_index = int(match.group(1))
    set_id = match.group(2)

    score = None
    score_match = _SCORE_TABLE_RE.search(log)
    if score_match:
        p1_wins = score_match.group("p1_circles").count('fa fa-circle"')
        p2_wins = score_match.group("p2_circles").count('fa fa-circle"')
        score = (p1_wins, p2_wins)
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
    # extract_bo3_context returns (p1, p2) order; BattleState.set_score_
    # entering_game is documented as (our wins, opponent wins) - flip for
    # p2's perspective. (Never observable from game 1's or game 3's score
    # alone, since (0, 0) and (1, 1) are symmetric either way - only
    # visible now that game 2's real, possibly-asymmetric score is
    # extracted too.)
    if score is not None and role == "p2":
        score = (score[1], score[0])

    player = LogReader(
        account_configuration=AccountConfiguration(username, None),
        battle_format=tag.split("-")[0],
        log_level=51,
        accept_open_team_sheet=True,
        loop=loop,
    )
    future = asyncio.run_coroutine_threadsafe(player.follow_log(tag, log), loop)
    future.result()
    states = [
        BattleState.from_battle(
            battle, set_id=set_id, game_index=game_index, set_score_entering_game=score
        )
        for battle in player.states
    ]
    return assign_decision_indices(states)
