"""Runs live VGC doubles battles against a local Showdown server.

Additive only: poke_env's Player classes and vgc_bench's own team/format
helpers are used as external dependencies here, exactly as vgc_bench's own
code uses them, without editing any vgc_bench module.

Run directly as a script: `python -m wpa.battle`.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

from poke_env.battle import AbstractBattle, DoubleBattle
from poke_env.player import BattleOrder, RandomPlayer
from poke_env.ps_client import AccountConfiguration, ServerConfiguration

from vgc_bench.src.teams import RandomTeamBuilder, get_available_regs
from vgc_bench.src.utils import format_map
from wpa.state import BattleState, assign_decision_indices

CURRENT_REG = os.environ.get("VGC_WPA_REG", "ma")
"""The regulation this project currently targets. Per docs/DEFINITIONS.md
§12.5, format is configuration, never hardcoded; our corpus (and therefore
this default) is Regulation M-A. Override with the VGC_WPA_REG env var."""

SHOWDOWN_PORT = int(os.environ.get("VGC_WPA_SHOWDOWN_PORT", "8000"))

_SERVER_CONFIGURATION = ServerConfiguration(
    f"ws://localhost:{SHOWDOWN_PORT}/showdown/websocket",
    "https://play.pokemonshowdown.com/action.php?",
)


def get_current_format(bo3: bool = False) -> str:
    """Showdown format string for the project's current regulation.

    Built from vgc_bench's own format_map, never a hardcoded literal, and
    checked against the regulations that actually have team data
    (get_available_regs(), which reads the teams/ directory) so a stale or
    unavailable pick fails loudly instead of silently connecting with no
    legal teams to draw from.
    """
    available = get_available_regs()
    if CURRENT_REG not in available:
        raise ValueError(
            f"configured regulation {CURRENT_REG!r} has no team data under "
            f"teams/ (available: {available}); set VGC_WPA_REG to one of those"
        )
    fmt = format_map[CURRENT_REG]
    return f"{fmt}bo3" if bo3 else fmt


def _make_random_player(battle_format: str, run_id: int) -> RandomPlayer:
    """A baseline random-move agent, playing a real legal team for the format."""
    return RandomPlayer(
        battle_format=battle_format,
        server_configuration=_SERVER_CONFIGURATION,
        team=RandomTeamBuilder(run_id, None, CURRENT_REG),
        accept_open_team_sheet=True,
        log_level=51,
    )


_BESTOF_ROOM_PREFIX = "game-bestof3-"


class _StateCapturingPlayer(RandomPlayer):
    """RandomPlayer that captures a BattleState at every decision point.

    Also derives best-of-3 set context (set_id, game_index,
    set_score_entering_game - see docs/DEFINITIONS.md #11.6/#13) from the
    live protocol, the same fields parse_battle_states derives from a raw
    replay log, via wpa.state.BattleState's single shared schema.

    set_id comes from _handle_bestof_message's room tag - a public,
    documented extension point already used the same way by vgc_bench's own
    PolicyPlayer (see vgc_bench/src/policy_player.py). Score entering each
    game is always fully known here (unlike replaying the historical
    corpus): we play every game of the set ourselves, so self.battles
    always holds every prior game's real result.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keyed by battle_tag, not one flat list: battle_against(n_battles=N)
        # plays N separate battles with this same player object, and
        # decision_index (assigned afterwards, per trajectory) must reset
        # at each battle's own start, not continue across a coincidental
        # matching turn number at the boundary between two battles.
        self.captured_states: dict[str, list[BattleState]] = {}
        self._set_id: str | None = None

    async def _handle_bestof_message(self, split_messages):
        room_tag = split_messages[0][0][1:]  # strip leading '>'
        if room_tag.startswith(_BESTOF_ROOM_PREFIX):
            self._set_id = room_tag[len(_BESTOF_ROOM_PREFIX) :]
        await super()._handle_bestof_message(split_messages)

    def _bo3_context(
        self, battle: AbstractBattle
    ) -> tuple[int | None, tuple[int, int] | None]:
        if self._set_id is None:
            return None, None
        tags = list(self.battles.keys())
        game_index = (
            tags.index(battle.battle_tag) + 1
            if battle.battle_tag in tags
            else len(tags) + 1
        )
        wins_ours = wins_opp = 0
        for prior_tag in tags[: game_index - 1]:
            prior = self.battles[prior_tag]
            if prior.won is True:
                wins_ours += 1
            elif prior.won is False:
                wins_opp += 1
        return game_index, (wins_ours, wins_opp)

    def choose_move(self, battle: AbstractBattle) -> BattleOrder:
        assert isinstance(battle, DoubleBattle)
        game_index, score = self._bo3_context(battle)
        state = BattleState.from_battle(
            battle,
            set_id=self._set_id,
            game_index=game_index,
            set_score_entering_game=score,
        )
        self.captured_states.setdefault(battle.battle_tag, []).append(state)
        return self.choose_random_move(battle)


def _make_state_capturing_player(
    battle_format: str, run_id: int
) -> _StateCapturingPlayer:
    # An explicit account_configuration, not poke-env's default naming from
    # the class name: that default produced "_StateCapturingP 1" for this
    # class (leading underscore, truncated), which Showdown's login rejects
    # outright - the connection then hangs forever awaiting a login
    # confirmation that never arrives, rather than failing loudly. Confirmed
    # by reproducing it in isolation before applying this fix.
    return _StateCapturingPlayer(
        account_configuration=AccountConfiguration(f"WpaCapture{run_id}", None),
        battle_format=battle_format,
        server_configuration=_SERVER_CONFIGURATION,
        team=RandomTeamBuilder(run_id, None, CURRENT_REG),
        accept_open_team_sheet=True,
        log_level=51,
    )


async def _capture_live_states(
    n_simple: int, n_bo3_sets: int, run_id: int
) -> list[BattleState]:
    states: list[BattleState] = []

    if n_simple:
        p1 = _make_state_capturing_player(get_current_format(bo3=False), run_id)
        p2 = _make_state_capturing_player(get_current_format(bo3=False), run_id + 1)
        await p1.battle_against(p2, n_battles=n_simple)
        for trajectory in p1.captured_states.values():
            states.extend(assign_decision_indices(trajectory))

    for i in range(n_bo3_sets):
        b1 = _make_state_capturing_player(
            get_current_format(bo3=True), run_id + 10 + i * 2
        )
        b2 = _make_state_capturing_player(
            get_current_format(bo3=True), run_id + 11 + i * 2
        )
        await b1.battle_against(b2, n_battles=1)
        # Each game of the set has its own battle_tag (its own turn
        # counter, starting fresh at 1), so decision_index is assigned per
        # game here too, not per whole set.
        for trajectory in b1.captured_states.values():
            states.extend(assign_decision_indices(trajectory))

    return states


def capture_live_states(
    n_simple: int, n_bo3_sets: int, run_id: int = 1
) -> list[BattleState]:
    """Play n_simple ordinary battles plus n_bo3_sets full best-of-3 sets
    live, and return every captured BattleState across all of them.

    One asyncio.run() for the whole call (not one per battle/set): repeated
    asyncio.run() cycles within one long-lived process were observed to hang
    a later call indefinitely (near-zero CPU, no exception) - reproduced by
    isolating an identical call that succeeded standalone but hung after two
    prior capture_live_states calls in the same pytest session.
    """
    return asyncio.run(_capture_live_states(n_simple, n_bo3_sets, run_id))


@dataclass(frozen=True)
class BattleResult:
    """Outcome of one played battle."""

    finished: bool
    winner: str | None
    p1_username: str
    p2_username: str
    battle_tag: str


def play_one_battle(battle_format: str | None = None) -> BattleResult:
    """Connect two baseline random agents to the local server and play one
    VGC doubles battle to completion."""
    fmt = battle_format or get_current_format()
    p1 = _make_random_player(fmt, run_id=1)
    p2 = _make_random_player(fmt, run_id=2)
    asyncio.run(p1.battle_against(p2, n_battles=1))
    battle = list(p1.battles.values())[-1]
    if battle.won is True:
        winner = p1.username
    elif battle.won is False:
        winner = p2.username
    else:
        winner = None
    return BattleResult(
        finished=battle.finished,
        winner=winner,
        p1_username=p1.username,
        p2_username=p2.username,
        battle_tag=battle.battle_tag,
    )


@dataclass(frozen=True)
class CrashRecord:
    """One battle that failed to complete, and why."""

    battle_index: int
    error: str


@dataclass(frozen=True)
class BattleRunResult:
    """Outcome of running a batch of battles."""

    attempted: int
    completed: int
    crashes: list[CrashRecord] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    battles_per_minute: float = 0.0


async def _run_pair(
    p1: RandomPlayer, p2: RandomPlayer, n: int, start_index: int
) -> tuple[int, list[CrashRecord]]:
    """Play n battles between one pair of agents, one at a time.

    One at a time, not a single `n_battles=n` call, so a single connection
    hiccup doesn't abort the whole batch - each failure is caught and
    recorded individually instead.
    """
    completed = 0
    crashes: list[CrashRecord] = []
    for i in range(n):
        try:
            await p1.battle_against(p2, n_battles=1)
            completed += 1
        except Exception as e:
            crashes.append(
                CrashRecord(
                    battle_index=start_index + i, error=f"{type(e).__name__}: {e}"
                )
            )
    return completed, crashes


def run_battles(n: int, run_id: int = 1) -> BattleRunResult:
    """Run n battles sequentially, one pair of agents, one process."""
    fmt = get_current_format()
    p1 = _make_random_player(fmt, run_id)
    p2 = _make_random_player(fmt, run_id + 1)
    start = time.monotonic()
    completed, crashes = asyncio.run(_run_pair(p1, p2, n, start_index=0))
    elapsed = time.monotonic() - start
    return BattleRunResult(
        attempted=n,
        completed=completed,
        crashes=crashes,
        elapsed_seconds=elapsed,
        battles_per_minute=(completed / elapsed * 60) if elapsed > 0 else 0.0,
    )


async def _run_parallel(
    n: int, concurrency: int, run_id_base: int
) -> tuple[int, list[CrashRecord]]:
    fmt = get_current_format()
    per_pair, remainder = divmod(n, concurrency)
    tasks = []
    assigned = 0
    for i in range(concurrency):
        count = per_pair + (1 if i < remainder else 0)
        if count == 0:
            continue
        run_id = run_id_base + i * 2
        p1 = _make_random_player(fmt, run_id)
        p2 = _make_random_player(fmt, run_id + 1)
        tasks.append(_run_pair(p1, p2, count, start_index=assigned))
        assigned += count
    results = await asyncio.gather(*tasks)
    completed = sum(c for c, _ in results)
    crashes = [c for _, crs in results for c in crs]
    return completed, crashes


def run_battles_parallel(
    n: int, concurrency: int, run_id_base: int = 1000
) -> BattleRunResult:
    """Run n battles split across `concurrency` independent agent pairs, all
    connected to the local server concurrently within one process."""
    start = time.monotonic()
    completed, crashes = asyncio.run(_run_parallel(n, concurrency, run_id_base))
    elapsed = time.monotonic() - start
    return BattleRunResult(
        attempted=n,
        completed=completed,
        crashes=crashes,
        elapsed_seconds=elapsed,
        battles_per_minute=(completed / elapsed * 60) if elapsed > 0 else 0.0,
    )


if __name__ == "__main__":
    result = play_one_battle()
    print(
        f"battle {result.battle_tag}: finished={result.finished}, "
        f"winner={result.winner}"
    )
