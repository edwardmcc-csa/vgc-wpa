"""Runs live VGC doubles battles against a local Showdown server.

Additive only: poke_env's Player classes and vgc_bench's own team/format
helpers are used as external dependencies here, exactly as vgc_bench's own
code uses them, without editing any vgc_bench module.

Run directly as a script: `python -m wpa.battle`.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

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


if __name__ == "__main__":
    result = play_one_battle()
    print(
        f"battle {result.battle_tag}: finished={result.finished}, "
        f"winner={result.winner}"
    )
