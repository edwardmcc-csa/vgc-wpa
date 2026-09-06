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

from poke_env.player import RandomPlayer
from poke_env.ps_client import ServerConfiguration

from vgc_bench.src.teams import RandomTeamBuilder, get_available_regs
from vgc_bench.src.utils import format_map

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
