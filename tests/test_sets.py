"""Tests for keeping a Bo3 set together (Week 8 Task 2): the logs are sharded by
set, so all games of a set are built in one place and in game order."""

from __future__ import annotations

import gzip
import json

from wpa import features as F


def bo3_log(set_id: str, game: int, body: str = "|start") -> str:
    return (
        f"|html|<strong>Game {game}</strong> of "
        f'<a href="/game-bestof3-{set_id}">a best-of-3</a>\n'
        f"{body}"
    )


def test_a_games_unit_is_its_set_or_itself():
    assert F.unit_of("gen9x-2", bo3_log("gen9x-1", 2)) == ("gen9x-1", 2)
    assert F.unit_of("gen9x-5", "|start\n|turn|1") == ("gen9x-5", 1)


def test_the_logs_of_a_set_land_in_one_shard_in_game_order(tmp_path):
    games = []
    for s in range(30):
        for g in (3, 1, 2):  # out of order on purpose
            games.append((f"gen9x-{s}-{g}", bo3_log(f"gen9x-{s}", g)))
    splits = {tag: "train" for tag, _ in games}
    F.split_logs_into_shards(games, splits, tmp_path, shards=4)
    seen: dict[str, int] = {}
    for part in sorted(tmp_path.glob("part-*.jsonl.gz")):
        with gzip.open(part, "rt", encoding="utf-8") as f:
            order = [json.loads(line)["tag"] for line in f]
        for tag in order:
            set_id = tag.rsplit("-", 1)[0]
            assert seen.setdefault(set_id, part.name.__hash__()) == part.name.__hash__()
        # within the shard, each set's games come in order
        for s in {t.rsplit("-", 1)[0] for t in order}:
            mine = [t for t in order if t.startswith(s + "-")]
            assert mine == [f"{s}-1", f"{s}-2", f"{s}-3"]
    assert len(seen) == 30
