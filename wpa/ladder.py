"""Ladder mode (Week 19, Phase 5): the bot searches the ladder and plays one
game at a time, on Showdown's own server or, for a trial, on your local one.

    python -m wpa.ladder --server local --games 20        # the trial
    python -m wpa.ladder --server showdown --games 50     # the pilot

On Showdown it logs in as chasemunk with the password in your password file:
one line, the password, in `showdown_password.txt` in your user folder (make
it with `notepad %USERPROFILE%\\showdown_password.txt`). The file is read, never
printed, and refused if it is inside the repo. On the local server (started
as for the local runs) a sparring partner searches the ladder too, with the
pool's teams in turn, so the same code is tried before any real game.

The bot plays the pool's team 40 unless `--team` says otherwise, denies open
team sheets, and plays on Showdown's timer. Each game is kept in the pilot
folder (`reports/pilot_regmc`, or `reports/ladder_trial_regmc` for the trial):
`games.jsonl` (the result, the rating after it, the bot's decisions and time)
and the game's log in `logs/`, with the bot's own sheet. The run stops after
the games asked, or at the first crash, refused choice or timeout; running it
again carries on the numbering, and `summary.txt` covers every game so far."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from wpa.matches import LIMITS, summary

REPO = Path(__file__).resolve().parents[1]
VS = "the ladder"
RATING = re.compile(r"^\|raw\|(.+?)'s rating: (\d+) &rarr; <strong>(\d+)</strong>")


def default_password_file() -> Path:
    return Path.home() / "showdown_password.txt"


def read_password(path: Path, repo: Path = REPO) -> str:
    """The password: the file's first line. The file must be outside the repo
    (so it can never be committed); it is not read if it is inside. Messages
    name the file, never what is in it."""
    path = Path(path)
    if path.resolve().is_relative_to(Path(repo).resolve()):
        raise SystemExit(
            f"The password file {path} is inside the repo: move it outside "
            "(your user folder is the default) and run this again."
        )
    if not path.exists():
        raise SystemExit(
            f"No password file at {path}. Make it with: notepad {path}\n"
            "Type the password on the first line, save, close, and run this again."
        )
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    first = next((x.strip() for x in lines if x.strip()), "")
    if not first:
        raise SystemExit(f"The password file {path} is empty.")
    return first


def to_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def ratings(lines: Iterable[str]) -> dict[str, tuple[int, int]]:
    """Each player's rating before and after the game, from the lines the
    server sends when a rated game ends; by the player's id."""
    out = {}
    for x in lines:
        m = RATING.match(x)
        if m:
            out[to_id(html.unescape(m.group(1)))] = (int(m.group(2)), int(m.group(3)))
    return out


def game_row(
    n: int,
    tag: str,
    lines: Sequence[str],
    *,
    me: str,
    opponent: str,
    won,
    finished: bool,
    turns: int,
    seconds: float,
    decisions: Sequence[Mapping],
    crashed: str,
    team: int,
) -> dict:
    """One game in the pilot folder, in the local runs' shape (so their
    summary reads it), with the ratings and the opponent's name."""
    quit_ = [x for x in lines if "lost due to inactivity" in x]
    inactive = None
    if quit_:
        inactive = "bot" if to_id(me) in to_id(quit_[0]) else "opponent"
    got = ratings(lines)
    mine, theirs = got.get(to_id(me)), got.get(to_id(opponent))
    return {
        "n": n,
        "k": n - 1,
        "vs": VS,
        "tag": tag,
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "bot_team": team,
        "opponent": opponent,
        "won": won,
        "turns": turns,
        "seconds": seconds,
        "rating_before": mine[0] if mine else None,
        "rating": mine[1] if mine else None,
        "opp_rating": theirs[0] if theirs else None,
        "decisions": list(decisions),
        "errors": [x for x in lines if x.startswith("|error|")],
        "inactive": inactive,
        "crashed": crashed or ("" if finished else "unfinished"),
    }


def stop_reason(row: Mapping) -> str:
    """Why the run stops after this game: a crash, a choice the server
    refused, or a timeout (the bot lost on time, or a choice took longer than
    the local runs allow); empty to carry on. The opponent's timeout, and a
    choice the server could not take for what the bot could not know (a
    disabled move), do not stop it."""
    if row.get("crashed"):
        return f"a crash ({row['crashed']})"
    if any("[Invalid choice]" in e for e in row.get("errors", [])):
        return "a refused choice (see the game's log)"
    if row.get("inactive") == "bot":
        return "a timeout: the bot lost on time"
    for d in row.get("decisions", []):
        if d.get("kind") != "stale" and d["seconds"] > LIMITS.get(d["kind"], 55):
            return f"a timeout: a {d['kind']} choice took {d['seconds']:.0f} s"
    return ""


def pilot_rows(folder: Path) -> list[dict]:
    path = Path(folder) / "games.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def next_number(folder: Path) -> int:
    return 1 + len(pilot_rows(folder))


def pilot_summary(rows: Sequence[Mapping]) -> str:
    """The local runs' summary (record, crashes, illegal choices, timeouts,
    the clock), then the rating and why the last run stopped, if it did."""
    out = [summary(rows)]
    rated = [r for r in rows if r.get("rating") is not None]
    if rated:
        first, last = rated[0], rated[-1]
        seen = [r["rating"] for r in rated]
        out.append(
            f"Rating: {first['rating_before']} before game {first['n']}, "
            f"{last['rating']} after game {last['n']} "
            f"(lowest {min(seen)}, highest {max(seen)})"
        )
    if rows and stop_reason(rows[-1]):
        out.append(f"Stopped after game {rows[-1]['n']}: {stop_reason(rows[-1])}")
    return "\n".join(out)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="The bot on the ladder.")
    p.add_argument("--server", choices=["local", "showdown"], default="local")
    p.add_argument("--games", type=int, default=1, help="games to play this run")
    p.add_argument("--team", type=int, default=40, help="the pool's team, 1 to 40")
    p.add_argument("--format", default="regmc", help="regmc or regmd")
    p.add_argument("--name", default=None, help="chasemunk on Showdown")
    p.add_argument("--password-file", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="the pilot folder")
    p.add_argument("--port", type=int, default=8000, help="the local server's")
    p.add_argument(
        "--search-minutes", type=float, default=15, help="stop if no game starts"
    )
    return p


def settings(a: argparse.Namespace) -> argparse.Namespace:
    """The options with their defaults filled in for the server chosen."""
    live = a.server == "showdown"
    if a.name is None:
        a.name = "chasemunk" if live else "WPA Ladder"
    if a.password_file is None:
        a.password_file = default_password_file()
    if a.out is None:
        kind = "pilot" if live else "ladder_trial"
        a.out = Path(f"reports/{kind}_{a.format}")
    return a


async def _on(player, name: str, seconds: float = 60) -> None:  # pragma: no cover
    import asyncio

    for _ in range(int(seconds * 5)):
        if player.ps_client.logged_in.is_set():
            return
        await asyncio.sleep(0.2)
    raise SystemExit(
        f"Could not log in as {name} within {seconds:.0f} s. On Showdown, check "
        "the password file and that the name is right."
    )


async def _game(bot, sparring, limit: float):  # pragma: no cover
    """One ladder search and its game. The tag of the game, or "" if none
    started within the search limit."""
    import asyncio

    before = set(bot.battles)
    plays = [bot.ladder(1)] + ([sparring.ladder(1)] if sparring else [])
    task = asyncio.ensure_future(asyncio.gather(*plays))
    start = time.time()
    while not task.done():
        if not [t for t in bot.battles if t not in before]:
            if time.time() - start > limit * 60:
                task.cancel()
                return ""
        await asyncio.sleep(1)
    task.result()  # a crash in either side is raised here
    new = [t for t in bot.battles if t not in before]
    return new[0] if new else ""


async def _run(a) -> None:  # pragma: no cover - plays on a server
    import asyncio

    from poke_env.ps_client import AccountConfiguration, ShowdownServerConfiguration

    from wpa import matches as M
    from wpa.bot import EngineBot
    from wpa.play import kept_game

    M._use_format(a.format)
    pool = json.loads(Path(f"reports/bot/pool_{a.format}.json").read_text("utf-8"))
    if not 1 <= a.team <= len(pool):
        raise SystemExit(f"--team must be 1 to {len(pool)}")
    packed = pool[a.team - 1]["packed"]
    if a.server == "showdown":
        account = AccountConfiguration(a.name, read_password(a.password_file))
        server = ShowdownServerConfiguration
    else:  # the local server was checked before this
        account = AccountConfiguration(a.name, None)
        server = M._server(a.port)
    print("Loading the engine (about a minute) ...")
    bot = EngineBot(
        M._tools(),
        packed,
        a.format,
        account_configuration=account,
        server_configuration=server,
        start_timer_on_battle_start=True,
        log_level=30,  # Showdown's popups (a team refused) are shown
    )
    del account
    await _on(bot, a.name)
    sparring = None
    if a.server == "local":
        from wpa.opponents import StrongestMovePlayer

        sparring = StrongestMovePlayer(
            team=pool[0]["packed"],
            seed=19,
            account_configuration=AccountConfiguration("WPA Sparring", None),
            battle_format=M.format_id(a.format),
            server_configuration=server,
            accept_open_team_sheet=False,
            log_level=40,
        )
        await _on(sparring, "WPA Sparring")
    logs = a.out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    n = next_number(a.out)
    print(
        f"Logged in as {a.name}. The bot plays team {a.team}: "
        f"{', '.join(pool[a.team - 1]['species'])}"
    )
    for _ in range(a.games):
        if sparring is not None:
            sparring.update_team(pool[(n - 1) % len(pool)]["packed"])
        print(f"Game {n}: searching the ladder ...")
        start, crashed, tag = time.time(), "", ""
        try:
            tag = await _game(bot, sparring, a.search_minutes)
        except Exception as e:  # kept, and the run stops
            crashed = repr(e)
        if not tag and not crashed:
            print(f"No game started within {a.search_minutes:.0f} minutes: stopped.")
            break
        battle = bot.battles.get(tag)
        for _ in range(40):  # the rating comes a moment after the game ends
            if any("s rating: " in x for x in bot.lines.get(tag, [])):
                break
            await asyncio.sleep(0.5)
        lines = list(bot.lines.get(tag, []))
        row = game_row(
            n,
            tag,
            lines,
            me=bot.username,
            opponent=(battle.opponent_username or "") if battle else "",
            won=battle.won if battle else None,
            finished=bool(battle and battle.finished),
            turns=battle.turn if battle else 0,
            seconds=round(time.time() - start, 1),
            decisions=[d for d in bot.records if d["battle"] == tag],
            crashed=crashed,
            team=a.team - 1,
        )
        with (a.out / "games.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        if battle is not None:
            text = kept_game(lines, battle.player_role or "p1", packed)
            (logs / f"{n:05d}-{tag}.log").write_text(text, encoding="utf-8")
        won = {True: "won", False: "lost", None: "no result"}[row["won"]]
        rating = f", rating {row['rating']}" if row["rating"] is not None else ""
        print(
            f"Game {n}: {won} against {row['opponent']} in {row['turns']} turns "
            f"({row['seconds']:.0f} s){rating}"
        )
        why = stop_reason(row)
        if why:
            print(f"Stopped: {why}")
            break
        n += 1
    text = pilot_summary(pilot_rows(a.out))
    (a.out / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print("\n" + text)


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    import asyncio

    from wpa.matches import _use_format, check_server

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    a = settings(parser().parse_args(argv))
    if a.server == "local":
        _use_format(a.format)
        check_server(a.port)
    asyncio.run(_run(a))


if __name__ == "__main__":  # pragma: no cover
    main()
