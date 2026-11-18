"""Play the bot yourself (Week 16): the bot waits on the local Reg M-C server
and accepts a challenge from anyone in Reg M-C, game after game.

    python -m wpa.play                # a team from the pool at random each game
    python -m wpa.play --team 5       # always the pool's fifth team

Open http://localhost:8000 in your browser (it opens Showdown's own page,
connected to your computer's server), pick any name, and challenge "WPA Bot"
to [Gen 9 Champions] VGC 2026 Reg M-C. The bot denies open team sheets and
thinks up to 45 seconds a turn. Each game is kept in `battle_logs_bot/you/`,
with the bot's own sheet, for the replay report. Close the window to stop."""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from wpa.matches import FMT, check_server


def pick_team(n_teams: int, team: int | None, rng: random.Random) -> int:
    """The pool's team the bot plays: the one asked for (counted from 1), or
    one at random."""
    if team is None:
        return rng.randrange(n_teams)
    if not 1 <= team <= n_teams:
        raise SystemExit(f"--team must be 1 to {n_teams}")
    return team - 1


def kept_game(lines: Iterable[str], role: str, packed: str) -> str:
    """The game as a spectator's log, with the bot's own sheet (and the
    other side's six as team preview showed them)."""
    from wpa.bot import live_log, paste_from_packed
    from wpa.replay import with_sheets

    return with_sheets(live_log(lines, role), role, paste_from_packed(packed))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Play the bot yourself.")
    p.add_argument("--team", type=int, default=None, help="the pool's team, 1 to 40")
    p.add_argument("--name", default="WPA Bot", help="the bot's name on the server")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--pool", type=Path, default=Path("reports/bot/pool_regmc.json"))
    p.add_argument("--logs", type=Path, default=Path("battle_logs_bot/you"))
    return p


async def _serve(a) -> None:  # pragma: no cover - plays on a server
    import asyncio
    import json

    from poke_env.ps_client import AccountConfiguration

    from wpa.bot import EngineBot
    from wpa.matches import _server, _tools

    pool = json.loads(Path(a.pool).read_text(encoding="utf-8"))
    rng = random.Random()
    k = pick_team(len(pool), a.team, rng)
    print("Loading the engine (about a minute) ...")
    bot = EngineBot(
        _tools(),
        pool[k]["packed"],
        FMT,
        account_configuration=AccountConfiguration(a.name, None),
        server_configuration=_server(a.port),
        log_level=40,
    )
    while not bot.ps_client.logged_in.is_set():
        await asyncio.sleep(0.2)
    a.logs.mkdir(parents=True, exist_ok=True)
    played = wins = 0
    while True:
        print(
            f"\nReady. In your browser (http://localhost:{a.port}), challenge "
            f'"{a.name}" to [Gen 9 Champions] VGC 2026 Reg M-C.\n'
            f"The bot plays team {k + 1}: {', '.join(pool[k]['species'])}"
        )
        before = set(bot.battles)
        await bot.accept_challenges(None, 1)
        new = [t for t in bot.battles if t not in before]
        if not new:
            continue
        battle = bot.battles[new[0]]
        played += 1
        wins += bool(battle.won)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = a.logs / f"{stamp}-{new[0]}.log"
        role = battle.player_role or "p1"
        text = kept_game(bot.lines.get(new[0], []), role, pool[k]["packed"])
        path.write_text(text, encoding="utf-8")
        result = "the bot won" if battle.won else "you won"
        print(f"Game {played}: {result} in {battle.turn} turns. Kept in {path}")
        print(f"So far: the bot {wins}, you {played - wins}")
        if a.team is None:
            k = pick_team(len(pool), None, rng)
            bot.set_team(pool[k]["packed"])


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    import asyncio

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    a = parser().parse_args(argv)
    check_server(a.port)
    asyncio.run(_serve(a))


if __name__ == "__main__":  # pragma: no cover
    main()
