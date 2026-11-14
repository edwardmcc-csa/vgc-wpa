"""Tests for wpa/fetch_replays.py (Week 14 Task 2): Showdown's public Reg M-C
replays, newest first, saved as the existing logs are; no network here (the
pages are made up in the shape Showdown's replay search returns)."""

from __future__ import annotations

import json

import pytest

from wpa import fetch_replays as F

FMT = "gen9championsvgc2026regmcbo3"
DAY = 86_400
NOW = 1_794_700_000  # 14 Nov 2026


def _game(i: int, t: int) -> dict:
    return {
        "id": f"{FMT}-{i}",
        "uploadtime": t,
        "format": "[Gen 9 Champions] VGC 2026 Reg M-C (Bo3)",
        "players": ["a", "b"],
        "rating": 1300 + i % 7,
        "private": 0,
        "password": None,
    }


class FakeShowdown:
    """Showdown's replay search (51 a page, newest first, `before` an upload
    time) and each replay's JSON, over `n` games one hour apart."""

    def __init__(self, n: int, fail: dict[str, int] | None = None):
        self.games = [_game(i, NOW - 3600 * i) for i in range(n)]
        self.calls: list[str] = []
        self.fail = dict(fail or {})

    def __call__(self, url: str):
        self.calls.append(url)
        if self.fail.get(url, 0) > 0:
            self.fail[url] -= 1
            raise OSError("connection reset")
        if "search.json" in url:
            before = None
            if "before=" in url:
                before = int(url.split("before=")[1].split("&")[0])
            page = [g for g in self.games if before is None or g["uploadtime"] < before]
            return page[:51]
        gid = url.rsplit("/", 1)[1].removesuffix(".json")
        g = next(x for x in self.games if x["id"] == gid)
        log = f"|showteam|p1|X|\n|showteam|p2|Y|\n|win|a\n{gid}"
        return dict(g, log=log)


def _run(tmp_path, fake, **kw):
    kw.setdefault("since", NOW - 30 * DAY)
    kw.setdefault("max_games", 10_000)
    return F.fetch(FMT, tmp_path, get=fake, sleep=lambda s: None, **kw)


def _saved(tmp_path) -> list[dict]:
    path = tmp_path / f"logs_{FMT}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_it_saves_every_game_newest_first_back_to_the_start_date(tmp_path):
    fake = FakeShowdown(200)  # 200 hours: back past 8 days
    got = _run(tmp_path, fake, since=NOW - 5 * DAY)
    saved = _saved(tmp_path)
    times = [x["uploadtime"] for x in saved]
    assert times == sorted(times, reverse=True)
    assert len(saved) == got.saved == 5 * 24 + 1  # one an hour, both ends kept
    assert min(times) == NOW - 5 * DAY
    assert {x["id"] for x in saved} == {g["id"] for g in fake.games[: 5 * 24 + 1]}
    assert saved[0]["log"].endswith(fake.games[0]["id"])


def test_it_stops_at_the_cap(tmp_path):
    got = _run(tmp_path, FakeShowdown(200), max_games=60)
    assert got.saved == 60 and len(_saved(tmp_path)) == 60


def test_a_second_run_downloads_nothing_twice_and_picks_up_where_it_stopped(tmp_path):
    fake = FakeShowdown(300)
    _run(tmp_path, fake, max_games=100)
    fake.calls.clear()
    got = _run(tmp_path, fake, max_games=250)
    ids = [x["id"] for x in _saved(tmp_path)]
    assert len(ids) == len(set(ids)) == 250
    replays = [c for c in fake.calls if "search.json" not in c]
    assert len(replays) == 150 == got.saved  # only the new ones
    pages = [c for c in fake.calls if "search.json" in c]
    assert len(pages) <= 6  # it jumps to the oldest it has, not page by page


def test_new_games_since_the_last_run_are_fetched_too(tmp_path):
    fake = FakeShowdown(120)
    _run(tmp_path, fake)
    fake.games = [_game(1000 + i, NOW + 600 * (i + 1)) for i in range(5)] + fake.games
    got = _run(tmp_path, fake)
    assert got.saved == 5
    assert len(_saved(tmp_path)) == 125


def test_a_failed_request_is_tried_again_then_skipped(tmp_path):
    fake = FakeShowdown(10)
    flaky = f"{F.REPLAYS}/{FMT}-3.json"
    dead = f"{F.REPLAYS}/{FMT}-4.json"
    fake.fail = {flaky: 1, dead: 99}
    got = _run(tmp_path, fake)
    ids = {x["id"] for x in _saved(tmp_path)}
    assert f"{FMT}-3" in ids and f"{FMT}-4" not in ids
    assert got.saved == 9 and got.failed == [f"{FMT}-4"]


def test_it_waits_between_requests_to_keep_to_the_rate():
    clock = [0.0]
    waited = []

    def sleep(s):
        waited.append(s)
        clock[0] += s

    pace = F.Pace(rate=3.0, now=lambda: clock[0], sleep=sleep)
    for _ in range(7):
        pace.wait()
    assert clock[0] == pytest.approx(2.0)  # 7 requests at 3 a second


def test_a_game_without_both_sheets_is_not_kept(tmp_path):
    fake = FakeShowdown(4)
    real = fake.__call__

    def no_sheet(url):
        out = real(url)
        if url.endswith("-2.json"):
            out = dict(out, log="|win|a")
        return out

    got = F.fetch(FMT, tmp_path, get=no_sheet, sleep=lambda s: None, since=NOW - DAY)
    assert got.saved == 3 and got.no_sheets == 1


def test_the_saved_games_become_a_log_file_like_the_others(tmp_path):
    _run(tmp_path, FakeShowdown(30))
    out = F.finish(FMT, tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert out.name == f"logs_{FMT}.json" and len(data) == 30
    first = data[f"{FMT}-0"]
    assert first[0] == NOW and first[1].startswith("|showteam|")


def test_the_usage_statistics_come_from_smogon_by_month_and_format(tmp_path):
    seen = []

    def get_bytes(url):
        seen.append(url)
        return b'{"info": {}, "data": {}}'

    paths = F.fetch_usage(
        ["2026-09", "2026-10"],
        ["gen9championsvgc2026regmc", FMT],
        tmp_path,
        get_bytes=get_bytes,
    )
    assert seen[0] == (
        "https://www.smogon.com/stats/2026-09/chaos/gen9championsvgc2026regmc-1500.json"
    )
    assert sorted(p.name for p in paths) == [
        "2026-09-gen9championsvgc2026regmc-1500.json",
        f"2026-09-{FMT}-1500.json",
        "2026-10-gen9championsvgc2026regmc-1500.json",
        f"2026-10-{FMT}-1500.json",
    ]


def test_a_line_cut_off_by_a_stopped_run_is_dropped_and_fetched_again(tmp_path):
    fake = FakeShowdown(20)
    _run(tmp_path, fake, max_games=5)
    path = tmp_path / f"logs_{FMT}.jsonl"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + text.splitlines()[0][:40], encoding="utf-8")  # cut off
    _run(tmp_path, fake)
    saved = _saved(tmp_path)
    assert len(saved) == 20 == len({x["id"] for x in saved})


def test_the_connection_trusts_mozillas_certificate_authorities():
    """Your computer's Windows store failed Smogon's certificate as expired
    (14 Nov); certifi's bundle (installed with requests) is used instead."""
    certifi = pytest.importorskip("certifi")
    ctx = F._context()
    assert ctx.verify_mode.name == "CERT_REQUIRED" and ctx.check_hostname
    import ssl

    want = ssl.create_default_context(cafile=certifi.where()).cert_store_stats()
    assert ctx.cert_store_stats() == want
