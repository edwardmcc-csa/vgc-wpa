"""The bot's matches on the local server (Week 16, Task 4).

Both sides draw from one pool of popular Reg M-C teams: the 40 commonest teams
of training games rated 1500 and up (`build/w15/team_pool_raw.json`), each
Pokemon given the stat points players most often run with its nature (sheets
show natures, not stat points). Every pairing is played from both sides, so
neither gets the better teams.

Each worker is two processes: the bot's side, which challenges, and the
opponent's, which accepts; each plays its share of the games one at a time,
the Showdown clock on. One row per game goes to `<out>/part-<w>.jsonl`; a run
stopped part way carries on where it was. Each game's log, with both teams
exactly, goes to `battle_logs_bot/<vs>/` for the resolver check.

    python -m wpa.matches --vs random --games 200 --workers 6
    python -m wpa.matches --vs random --summary"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

FORMAT = "gen9championsvgc2026regmc"
FMT = "regmc"
OPPONENTS = {
    "random": "random choices",
    "strongest": "the strongest move",
    "typical": "the choice model (as people typically play)",
    "engine0": "the engine at strength 0",
}
LIMITS = {"preview": 90, "turn": 55, "replacement": 55, "pivot": 55}
VS_CODE = {"random": 1, "strongest": 2, "typical": 3, "engine0": 4}


# --------------------------------------------------------------------------
# The teams
# --------------------------------------------------------------------------


def with_usual_points(packed: str, usage: Mapping, dex) -> str:
    """A packed team with each Pokemon's stat points the likeliest spread the
    usage statistics give it with its nature (`spreads.prior`)."""
    from wpa.spreads import prior
    from wpa.team_sheets import sheets_from_log

    mons = sheets_from_log("|showteam|p1|" + packed)["p1"]
    out = []
    for entry, mon in zip(packed.split("]"), mons):
        f = (entry.split("|") + [""] * 12)[:12]
        cands = prior(usage, mon, dex)
        if cands:
            best = max(cands, key=lambda c: c.weight)
            f[6] = ",".join(str(x) for x in best.sps)
        out.append("|".join(f))
    return "]".join(out)


def make_pool(raw: Sequence[Mapping], usage: Mapping, dex) -> list[dict]:
    """The pool: each popular team with the stat points players most often run."""
    return [
        {
            "species": t["species"],
            "count": t.get("count", 0),
            "packed": with_usual_points(t["packed"], usage, dex),
        }
        for t in raw
    ]


def pairings(n_teams: int, games: int, seed: int = 16) -> list[tuple[int, int]]:
    """`games` games: pairings of two different teams drawn without repeats,
    each played from both sides one after the other (the same every run)."""
    every = [(a, b) for a in range(n_teams) for b in range(a + 1, n_teams)]
    random.Random(seed).shuffle(every)
    out: list[tuple[int, int]] = []
    for a, b in every[: (games + 1) // 2]:
        out += [(a, b), (b, a)]
    return out[:games]


# --------------------------------------------------------------------------
# What is kept of each game
# --------------------------------------------------------------------------


def kept_log(lines: Iterable[str], role: str, mine: str, theirs: str) -> str:
    """The game as a spectator's log, with both players' sheets exactly (stat
    points too): what the resolver check reads (`wpa.resolver_check`)."""
    from wpa.bot import live_log

    log = live_log(lines, role)
    other = "p2" if role == "p1" else "p1"
    show = [f"|showteam|{role}|{mine}", f"|showteam|{other}|{theirs}"]
    out = []
    for x in log.split("\n"):
        out.append(x)
        if x.startswith("|teampreview"):
            out += show
    return "\n".join(out)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% interval of a win rate of k in n (Wilson's)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def done_games(folder: Path) -> set[int]:
    """The games a run has already played (its rows)."""
    out = set()
    for path in Path(folder).glob("part-*.jsonl"):
        for x in path.read_text(encoding="utf-8").splitlines():
            if x.strip():
                out.add(int(json.loads(x)["k"]))
    return out


def rows_of(folder: Path) -> list[dict]:
    return [
        json.loads(x)
        for path in sorted(Path(folder).glob("part-*.jsonl"))
        for x in path.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def calibration(rows: Sequence[Mapping]) -> dict:
    """The bot's own win chance at each turn's start (its engine's, with the
    opponent's sheet hidden) against the game's result: the Brier score, and
    by tenths of predicted chance how often it won. Games without a result, or
    left out of the win rate, are left out here too."""
    pts = [
        (float(d["wp"]), 1.0 if r.get("won") else 0.0)
        for r in rows
        if r.get("won") is not None
        and r.get("inactive") != "opponent"
        and not r.get("crashed")
        for d in r.get("decisions", [])
        if d.get("kind") == "turn" and d.get("wp") is not None
    ]
    if not pts:
        return {"turns": 0, "brier": float("nan"), "bins": []}
    bins = []
    for b in range(10):
        got = [(p, y) for p, y in pts if min(int(p * 10), 9) == b]
        if got:
            bins.append(
                {
                    "bin": f"{10 * b}% to {10 * b + 10}%",
                    "n": len(got),
                    "predicted": sum(p for p, _ in got) / len(got),
                    "won": sum(y for _, y in got) / len(got),
                }
            )
    brier = sum((p - y) ** 2 for p, y in pts) / len(pts)
    return {"turns": len(pts), "brier": brier, "bins": bins}


def pack_for_check(logs_root: Path, vs: str, out: Path) -> tuple[Path, Path]:
    """The bot's kept games as the resolver check reads games: a logs folder
    (one shard) and a sample naming them, each with a tag of its own
    ("<format>-9<opponent><game>")."""
    import gzip

    shards = Path(out) / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    tags = []
    with gzip.open(shards / "part-000.jsonl.gz", "wt", encoding="utf-8") as f:
        for path in sorted((Path(logs_root) / vs).glob("*.log")):
            tag = f"{FORMAT}-9{VS_CODE[vs]}{int(path.stem):07d}"
            tags.append(tag)
            log = path.read_text(encoding="utf-8")
            f.write(json.dumps({"tag": tag, "log": log}) + "\n")
    sample = Path(out) / "resolver_sample.json"
    sample.write_text(json.dumps({"games": {FMT: tags}}, indent=1), encoding="utf-8")
    return shards, sample


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def opponent_note(folder: Path) -> str:
    """For the engine opponents: how many of their choices were replaced by a
    legal one at random (their models failed, or the choice was not allowed)."""
    ds = [
        d
        for path in sorted(Path(folder).glob("opp-part-*.jsonl"))
        for x in path.read_text(encoding="utf-8").splitlines()
        if x.strip()
        for d in json.loads(x)["decisions"]
    ]
    if not ds:
        return ""
    n = sum(1 for d in ds if d.get("why"))
    return (
        f"  The opponent's choices replaced by a legal one at random: {n} of {len(ds)}"
    )


def summary(rows: Sequence[Mapping]) -> str:
    """The gate's numbers: the win rate with its 95% interval, and the counts
    of crashes, illegal choices and timeouts; how often the clock stopped the
    search. A game whose opponent's side stopped (it lost on time, or its
    process ended) is left out of the win rate."""
    by: dict[str, list[Mapping]] = {}
    for r in rows:
        by.setdefault(r["vs"], []).append(r)
    out = []
    for vs, rs in by.items():
        left_out = [r for r in rs if r.get("inactive") == "opponent"]
        counted = [r for r in rs if r not in left_out and not r.get("crashed")]
        wins = sum(1 for r in counted if r.get("won"))
        lo, hi = wilson(wins, len(counted))
        n = len(counted)
        rate = _pct(wins / n) if n else "-"
        name = vs.replace("-untimed", " (untimed: the full advice, no clock)")
        out.append(
            f"Against {name}: {wins} wins of {n} games ({rate}, 95% interval "
            f"{_pct(lo)} to {_pct(hi)})"
        )
        if left_out:
            s = "s" if len(left_out) > 1 else ""
            out.append(
                f"  {len(left_out)} game{s} left out: the opponent's side stopped"
            )
        every = [d for r in rs for d in r.get("decisions", [])]
        # Week 17: a choice dropped because its request had passed sent nothing
        decisions = [d for d in every if d["kind"] != "stale"]
        hard = sum(1 for d in decisions if d["kind"] == "late")
        dropped = len(every) - len(decisions)
        illegal = sum(
            1 for r in rs for e in r.get("errors", []) if "[Invalid choice]" in e
        )
        late = sum(
            1 for d in decisions if d["seconds"] > LIMITS.get(d["kind"], 55)
        ) + sum(1 for r in rs if r.get("inactive") == "bot")
        crashes = sum(1 for r in rs if r.get("crashed"))
        swapped = sum(1 for d in decisions if d.get("why"))
        turns = [d for d in decisions if d["kind"] == "turn"]
        stopped = sum(1 for d in turns if d.get("stopped"))
        out.append(
            f"  Crashes: {crashes}. Illegal choices: {illegal}. Timeouts: {late}."
        )
        if hard or dropped:
            out.append(
                f"  Answered by the hard limit: {hard}. "
                f"Dropped, their request passed: {dropped}"
            )
        out.append(
            f"  Choices not exactly the engine's (replaced by a legal one): "
            f"{swapped} of {len(decisions)}; searches stopped by the clock: "
            f"{stopped} of {len(turns)}"
        )
        cut = [d for d in turns if d.get("stopped") and d.get("compared")]
        if cut:
            left = [
                (d["compared"] - d.get("valued", 0) - d.get("screened", 0))
                / d["compared"]
                for d in cut
            ]
            full = [d.get("valued", 0) for d in cut]
            out.append(
                f"  When the clock stopped it: on average {_pct(sum(left) / len(left))}"
                f" of the plays left unvalued, and {sum(full) / len(full):.0f} valued "
                "against every reply"
            )
        if turns:
            secs = sorted(d["seconds"] for d in turns)
            mid = secs[len(secs) // 2]
            slow = secs[min(len(secs) - 1, int(0.99 * len(secs)))]
            out.append(f"  Seconds a turn: typical {mid:.0f}, slowest 1% {slow:.0f}")
            games = sorted(
                sum(d["seconds"] for d in r.get("decisions", [])) for r in rs
            )
            out.append(
                f"  Thinking in a whole game: typical {games[len(games) // 2]:.0f} s, "
                f"longest {games[-1]:.0f} s (the clock allows {420} s)"
            )
        cal = calibration(rs)
        if cal["turns"]:
            out.append(
                f"  Its win chance at each turn, against the results: Brier "
                f"{cal['brier']:.3f} over {cal['turns']} turns"
            )
            for b in cal["bins"]:
                out.append(
                    f"    predicted {b['bin']}: {b['n']} turns, won "
                    f"{_pct(b['won'])} (predicted {_pct(b['predicted'])})"
                )
    return "\n".join(out)


# --------------------------------------------------------------------------
# Playing
# --------------------------------------------------------------------------


async def _formats(port: int) -> str:  # pragma: no cover - asks the server
    import asyncio

    import websockets

    async with websockets.connect(f"ws://localhost:{port}/showdown/websocket") as ws:
        for _ in range(10):
            got = str(await asyncio.wait_for(ws.recv(), 5))
            if "|formats|" in got:
                return got
    return ""


def check_server(port: int) -> None:  # pragma: no cover - asks the server
    """Stop with a plain message unless a Showdown server with Reg M-C answers."""
    import asyncio

    try:
        formats = asyncio.run(_formats(port))
    except Exception:
        raise SystemExit(
            f"No Showdown server answers on port {port}: start the Reg M-C one "
            "(Runbook Section 29, step 1)"
        ) from None
    if "VGC 2026 Reg M-C" not in formats:
        raise SystemExit(
            f"The Showdown server on port {port} has no Reg M-C: close it and "
            "start the one in pokemon-showdown-mc (Runbook Section 29, step 1)"
        )


def _server(port: int):  # pragma: no cover
    from poke_env.ps_client import ServerConfiguration

    return ServerConfiguration(
        f"ws://localhost:{port}/showdown/websocket",
        "https://play.pokemonshowdown.com/action.php?",
    )


def _tools():  # pragma: no cover - loads the models
    from wpa import attribution as A
    from wpa import replay as RP

    ns = argparse.Namespace(
        dex_tables=None, moves_dir=None, models=None, hidden=True, public_models=None
    )
    return A._tools(RP._options(ns))


def run_name(a) -> str:
    """A run's folder: the opponent, and "-untimed" for the measuring run."""
    return a.vs + ("-untimed" if getattr(a, "untimed", False) else "")


def _names(run: str, w: int) -> tuple[str, str]:
    return f"wpabot{run}w{w}", f"wpaopp{run}w{w}"


def _opponent(vs: str, packed: str, name: str, port: int, w: int):  # pragma: no cover
    from poke_env.player import RandomPlayer
    from poke_env.ps_client import AccountConfiguration

    kw: dict[str, Any] = dict(
        account_configuration=AccountConfiguration(name, None),
        battle_format=FORMAT,
        server_configuration=_server(port),
        accept_open_team_sheet=False,
        log_level=40,
    )
    if vs == "random":
        return RandomPlayer(team=packed, **kw)
    from wpa import opponents as O

    if vs == "strongest":
        return O.StrongestMovePlayer(team=packed, seed=w, **kw)
    tools = _tools()
    if vs == "typical":
        return O.TypicalBot(tools, packed, FMT, seed=w, **kw)
    return O.EngineBot(O.at_strength_zero(tools), packed, FMT, **kw)


def _ready(a, w: int) -> Path:
    """The file the opponent's side makes once it is on the server: the bot's
    side waits for it before its first challenge."""
    return Path(a.out) / run_name(a) / f"ready-{a.run}-{w}"


async def _play_opponent(a, w: int, games, pool, done) -> None:  # pragma: no cover
    import asyncio

    bot_name, opp_name = _names(a.run, w)
    player = None
    for k, (_mine, theirs) in games:
        if k in done:
            continue
        packed = pool[theirs]["packed"]
        if player is None:
            player = _opponent(a.vs, packed, opp_name, a.port, w)
            # poke_env logs in on its own loop: its event is read, not awaited
            while not player.ps_client.logged_in.is_set():
                await asyncio.sleep(0.2)
            _ready(a, w).write_text("on the server\n", encoding="utf-8")
        else:
            player.update_team(packed)
            set_team = getattr(player, "set_team", None)
            if set_team is not None:  # the engine's own copy of its team
                set_team(packed)
        await player.accept_challenges(bot_name, 1)
        got = getattr(player, "records", None)  # the engine opponents' choices
        if got:
            out = Path(a.out) / run_name(a) / f"opp-part-{w}.jsonl"
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"k": k, "decisions": list(got)}) + "\n")
            got.clear()


async def _play_bot(
    a, w: int, games, pool, done, out: Path
) -> None:  # pragma: no cover
    import asyncio

    from poke_env.ps_client import AccountConfiguration

    from wpa.bot import EngineBot

    bot_name, opp_name = _names(a.run, w)
    tools = _tools()
    logs = Path(a.logs) / run_name(a)
    logs.mkdir(parents=True, exist_ok=True)
    bot = None
    for k, (mine, theirs) in games:
        if k in done:
            continue
        packed = pool[mine]["packed"]
        if bot is None:
            bot = EngineBot(
                tools,
                packed,
                FMT,
                account_configuration=AccountConfiguration(bot_name, None),
                server_configuration=_server(a.port),
                start_timer_on_battle_start=not a.untimed,
                timed=not a.untimed,
                log_level=40,
            )
        else:
            bot.set_team(packed)
        before, start, crashed = set(bot.battles), time.time(), ""
        for _ in range(1200):  # its opponent on the server first (10 minutes)
            if _ready(a, w).exists():
                break
            await asyncio.sleep(0.5)
        try:
            await bot.send_challenges(opp_name, 1)
        except Exception as e:  # kept, and the run goes on
            crashed = repr(e)
        new = [t for t in bot.battles if t not in before]
        tag = new[0] if new else ""
        battle = bot.battles.get(tag)
        lines = bot.lines.get(tag, [])
        quit_ = [x for x in lines if "lost due to inactivity" in x]
        inactive = None
        if quit_:
            inactive = "bot" if bot.username in quit_[0] else "opponent"
        row = {
            "k": k,
            "vs": run_name(a),
            "tag": tag,
            "bot_team": mine,
            "opp_team": theirs,
            "role": battle.player_role if battle else None,
            "won": battle.won if battle else None,
            "turns": battle.turn if battle else 0,
            "seconds": round(time.time() - start, 1),
            "decisions": [d for d in bot.records if d["battle"] == tag],
            "errors": [x for x in lines if x.startswith("|error|")],
            "inactive": inactive,
            "crashed": crashed or ("" if battle and battle.finished else "unfinished"),
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        if battle is not None:
            role = battle.player_role or "p1"
            text = kept_log(lines, role, packed, pool[theirs]["packed"])
            (logs / f"{k:05d}.log").write_text(text, encoding="utf-8")
        won = {True: "won", False: "lost", None: "no result"}[row["won"]]
        print(f"game {k + 1}: {won} in {row['turns']} turns ({row['seconds']:.0f} s)")


def _worker(a, w: int, side: str) -> None:  # pragma: no cover
    import asyncio

    pool = json.loads(Path(a.pool).read_text(encoding="utf-8"))
    every = list(enumerate(pairings(len(pool), a.games, a.seed)))
    mine = [g for g in every if g[0] % a.workers == w]
    out = Path(a.out) / run_name(a)
    out.mkdir(parents=True, exist_ok=True)
    done = done_games(out)
    if side == "bot":
        asyncio.run(_play_bot(a, w, mine, pool, done, out / f"part-{w}.jsonl"))
    else:
        asyncio.run(_play_opponent(a, w, mine, pool, done))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="The bot's matches on the local server.")
    p.add_argument("--vs", choices=sorted(OPPONENTS), default="random")
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--seed", type=int, default=16)
    p.add_argument("--pool", type=Path, default=Path("reports/bot/pool_regmc.json"))
    p.add_argument("--out", type=Path, default=Path("reports/bot"))
    p.add_argument("--logs", type=Path, default=Path("battle_logs_bot"))
    p.add_argument("--summary", action="store_true", help="the results so far")
    p.add_argument(
        "--untimed",
        action="store_true",
        help="the full advice at every turn, the clock off: to measure its time",
    )
    p.add_argument(
        "--for-resolver-check",
        action="store_true",
        help="pack the kept games for the resolver check (Task 5)",
    )
    p.add_argument(
        "--make-pool",
        type=Path,
        default=None,
        help="make the pool from the popular teams (build/w15/team_pool_raw.json)",
    )
    p.add_argument("--run", default=None, help=argparse.SUPPRESS)
    p.add_argument("--side", choices=("bot", "opponent"), help=argparse.SUPPRESS)
    p.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    return p


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    import subprocess

    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    a = parser().parse_args(argv)
    if a.make_pool:
        from wpa.spreads import UsageStore
        from wpa.team_sheets import load_dexes

        raw = json.loads(a.make_pool.read_text(encoding="utf-8"))
        usage = UsageStore("usage_stats").for_game(
            f"{FORMAT}-0", f"|t:|{int(time.time())}\n"
        )
        dex = load_dexes(Path("pokemon-showdown"))[FMT]
        a.pool.parent.mkdir(parents=True, exist_ok=True)
        a.pool.write_text(
            json.dumps(make_pool(raw, usage, dex), indent=1), encoding="utf-8"
        )
        print(f"The pool: {len(raw)} teams, in {a.pool}")
        return
    if a.summary:
        folder = Path(a.out) / run_name(a)
        print(summary(rows_of(folder)) or "No games played yet.")
        if note := opponent_note(folder):
            print(note)
        return
    if a.for_resolver_check:
        out = Path(a.out) / a.vs / "resolver"
        shards, sample = pack_for_check(a.logs, a.vs, out)
        n = len(json.loads(sample.read_text(encoding="utf-8"))["games"][FMT])
        print(f"{n} games packed. The check:")
        print(
            f"  python -m wpa.resolver_check --logs {shards} --sample {sample} "
            f"--out-dir {out / 'check'}"
        )
        return
    if a.side:  # one worker's side
        _worker(a, a.worker, a.side)
        return
    check_server(a.port)
    run = a.run or str(int(time.time()) % 100000)
    left = a.games - len(done_games(Path(a.out) / run_name(a)))
    print(
        f"Playing {left} games against {OPPONENTS[a.vs]} on {a.workers} workers "
        f"(each game a few minutes; a stopped run carries on where it was)."
    )
    base = [sys.executable, "-m", "wpa.matches", *(argv or sys.argv[1:]), "--run", run]
    procs = []
    for w in range(a.workers):
        for side in ("opponent", "bot"):
            procs.append(subprocess.Popen([*base, "--side", side, "--worker", str(w)]))
            time.sleep(1)
    for p in procs:
        p.wait()
    print(summary(rows_of(Path(a.out) / run_name(a))))


if __name__ == "__main__":  # pragma: no cover
    main()
