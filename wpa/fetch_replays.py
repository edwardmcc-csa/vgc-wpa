"""Showdown's public replays and Smogon's usage statistics (Week 14 Task 2).

Reg M-C's games are not in the corpus we started from (the vgc-bench logs on
Hugging Face stop at M-B), so they come from Showdown's own replay search:
newest first, back to a start date, each replay's log saved as one line of
`<out>/logs_<format>.jsonl` as it arrives, so a run can stop at any time and
the next one picks up where it stopped. Polite: one request at a time, at most
`--rate` a second, a few tries with a pause on an error, then that game is
skipped and named. Only games where both team sheets are shown are kept (every
best-of-three game shows them).

`--finish` turns the saved lines into `logs_<format>.json`, the shape of the
existing logs ({battle tag: [upload time, log]}); `--usage` saves Smogon's
monthly statistics next to the others in `usage_stats/`.

    python -m wpa.fetch_replays
    python -m wpa.fetch_replays --finish
    python -m wpa.fetch_replays --usage 2026-09 2026-10
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SEARCH = "https://replay.pokemonshowdown.com/search.json"
REPLAYS = "https://replay.pokemonshowdown.com"
STATS = "https://www.smogon.com/stats"
AGENT = "vgc-wpa research (win probability; one request at a time, 3 a second)"
FORMAT = "gen9championsvgc2026regmcbo3"
USAGE_FORMATS = ("gen9championsvgc2026regmc", "gen9championsvgc2026regmcbo3")


@dataclass
class Result:
    saved: int = 0  # new games kept this run
    no_sheets: int = 0  # games without both team sheets (not kept)
    failed: list[str] = field(default_factory=list)  # gave up after the tries
    total: int = 0  # games in the file now


class Pace:
    """At most `rate` requests a second: each waits until 1/rate after the one
    before."""

    def __init__(
        self,
        rate: float,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.gap = 1.0 / rate
        self.now, self.sleep = now, sleep
        self.next: float | None = None

    def wait(self) -> None:
        t = self.now()
        if self.next is not None and t < self.next:
            self.sleep(self.next - t)
            t = self.next
        self.next = t + self.gap


def _context() -> ssl.SSLContext:
    """Mozilla's certificate authorities (certifi) when installed, else the
    computer's own. On the PO's computer the Windows store failed Smogon's
    certificate chain as expired (14 Nov); certifi's does not."""
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi comes with requests
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _get_json(url: str):  # pragma: no cover - the network
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=30, context=_context()) as r:
        return json.loads(r.read())


def _get_bytes(url: str) -> bytes:  # pragma: no cover - the network
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=120, context=_context()) as r:
        return r.read()


def _try(get, url: str, pace: Pace, sleep, tries: int):
    """The answer, or None after `tries` failures (a pause between them)."""
    for k in range(tries):
        pace.wait()
        try:
            return get(url)
        except (OSError, ValueError):  # network errors, HTTP errors, bad JSON
            if k + 1 < tries:
                sleep(min(60.0, 2.0 * 2**k))
    return None


def _load(path: Path) -> dict[str, int]:
    """The games already saved (id -> upload time). A last line cut off by a
    stopped run is dropped, so the next line starts clean."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    have: dict[str, int] = {}
    good: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        have[rec["id"]] = int(rec["uploadtime"])
        good.append(line)
    cut = bool(text) and not text.endswith("\n")
    if cut or len(good) != sum(1 for x in lines if x):
        path.write_text("".join(x + "\n" for x in good), encoding="utf-8")
    return have


def fetch(
    fmt: str,
    out_dir: Path,
    *,
    since: int,
    max_games: int = 60_000,
    rate: float = 3.0,
    tries: int = 4,
    get=_get_json,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = lambda s: None,
) -> Result:
    """Save `fmt`'s public replays uploaded since `since` (a Unix time), newest
    first, until the file holds `max_games`. Games already saved are not
    fetched again: once a page holds nothing new, the search jumps to the
    oldest game saved and carries on from there."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"logs_{fmt}.jsonl"
    have = _load(path)
    res = Result(total=len(have))
    pace = Pace(rate, sleep=sleep)
    before: int | None = None
    jumped = False
    t0 = time.time()
    with open(path, "a", encoding="utf-8", newline="\n") as out:
        while res.total < max_games:
            url = f"{SEARCH}?format={fmt}" + (f"&before={before}" if before else "")
            page = _try(get, url, pace, sleep, tries)
            if not page:
                break  # the end, or the search failed: stop (a rerun resumes)
            done = False
            fresh = False
            for g in page:
                if int(g["uploadtime"]) < since:
                    done = True
                    break
                if g["id"] in have:
                    continue
                fresh = True
                if res.total >= max_games:
                    break
                replay = _try(get, f"{REPLAYS}/{g['id']}.json", pace, sleep, tries)
                if replay is None:
                    res.failed.append(g["id"])
                    continue
                log = replay.get("log") or ""
                if log.count("|showteam|") < 2:
                    res.no_sheets += 1
                    continue
                rec = {
                    "id": g["id"],
                    "uploadtime": int(g["uploadtime"]),
                    "rating": g.get("rating"),
                    "players": g.get("players"),
                    "log": log,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                have[g["id"]] = rec["uploadtime"]
                res.saved += 1
                res.total += 1
                if res.saved % 500 == 0:
                    day = datetime.fromtimestamp(rec["uploadtime"], timezone.utc)
                    say(
                        f"  {res.total:,} games saved ({res.saved:,} this run), "
                        f"back to {day:%d %b %H:%M} UTC, "
                        f"{round((time.time() - t0) / 60)} min"
                    )
            if done:
                break
            before = int(page[-1]["uploadtime"])
            if not fresh and not jumped and have:
                before = min(min(have.values()), before)  # resume past what we have
                jumped = True
    return res


def finish(fmt: str, out_dir: Path) -> Path:
    """`logs_<format>.json` from the saved lines, newest first: {battle tag:
    [upload time, log]}, the shape of the vgc-bench logs."""
    out_dir = Path(out_dir)
    src = out_dir / f"logs_{fmt}.jsonl"
    recs = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x]
    recs.sort(key=lambda r: -int(r["uploadtime"]))
    data = {r["id"]: [int(r["uploadtime"]), r["log"]] for r in recs}
    dest = out_dir / f"logs_{fmt}.json"
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return dest


def fetch_usage(
    months: Sequence[str],
    formats: Sequence[str],
    out_dir: Path,
    get_bytes: Callable[[str], bytes] = _get_bytes,
) -> list[Path]:
    """Smogon's monthly usage statistics (the 1500 cutoff, as for M-A and M-B)
    as `<month>-<format>-1500.json`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for m in months:
        for f in formats:
            dest = out_dir / f"{m}-{f}-1500.json"
            dest.write_bytes(get_bytes(f"{STATS}/{m}/chaos/{f}-1500.json"))
            paths.append(dest)
    return paths


def _date(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--format", default=FORMAT)
    p.add_argument("--since", default="2026-09-09", help="first day (UTC)")
    p.add_argument("--max", type=int, default=60_000, help="games in the file")
    p.add_argument("--rate", type=float, default=3.0, help="requests a second")
    p.add_argument("--out", type=Path, default=Path("battle_logs_mc"))
    p.add_argument("--finish", action="store_true", help="write logs_<format>.json")
    p.add_argument("--usage", nargs="+", metavar="MONTH", help="e.g. 2026-09 2026-10")
    p.add_argument("--usage-dir", type=Path, default=Path("usage_stats"))
    a = p.parse_args(argv)
    if a.usage:
        for path in fetch_usage(a.usage, USAGE_FORMATS, a.usage_dir):
            print(f"saved {path} ({path.stat().st_size:,} bytes)")
        return
    if a.finish:
        dest = finish(a.format, a.out)
        n = len(json.loads(dest.read_text(encoding="utf-8")))
        print(f"wrote {dest}: {n:,} games")
        return
    print(
        f"Saving {a.format} replays since {a.since}, newest first, up to "
        f"{a.max:,} games, {a.rate:g} requests a second, into {a.out} ...",
        flush=True,
    )
    res = fetch(
        a.format,
        a.out,
        since=_date(a.since),
        max_games=a.max,
        rate=a.rate,
        say=lambda s: print(s, flush=True),
    )
    print(
        f"Done: {res.saved:,} new games saved, {res.total:,} in the file; "
        f"{res.no_sheets} without both sheets (not kept); "
        f"{len(res.failed)} could not be fetched"
        + (f" (first: {res.failed[0]})" if res.failed else ""),
        flush=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
