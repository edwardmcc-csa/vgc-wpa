"""Reconstructs best-of-3 set structure from the replay corpus: set ID,
game index, and set score entering the game, for every game - populating
the existing wpa/state.py fields added in Week 2 Task 4, not a parallel
representation.

The set score is not derived from the universal rules alone (game 1 always
0-0, game 3 always 1-1) - Week 2's extract_bo3_context left game 2 as None
because a single log in isolation can't see game 1's result via the
|win| line. This task corrects that: every bo3 game's own log carries the
running score directly, as an HTML circle table
(`<i class="fa fa-circle">` = won, `fa fa-circle-o` = not yet) shown right
before the "Game N of a best-of-3" banner. This closes Week 1/2's
"~4.8% of game-2 records have an unknowable score" finding - that gap
doesn't actually exist; every log carries its own answer.

Note on "no gaps" and "roughly a third": Week 1's investigation already
found real sets with gaps (game 1 missing from the corpus while 2/3 are
present) and a large fraction of single-game (forfeited) sets - both
legitimate, not extraction bugs. So the corpus-wide tests here check what
is actually true of the data (duplicate-free assignment, a bounded
unassignable rate, valid game-index values) rather than asserting the
dispatch's "roughly a third" and "no gaps" as literal hard invariants that
real, partially-scraped data would fail. Measured on the full corpus
(both bo3 files, 81,676 games): the real games/sets ratio is 1.74, not 3 -
most sets don't go the distance (forfeits, 2-0 sweeps) - documented in the
Week 3 Task 3 report rather than silently forced to match the assumption.

wpa/state.py's extract_bo3_context doesn't yet read the score table, and
wpa/sets.py (the corpus-level grouping pass) doesn't exist yet; written
first and expected to fail.
"""

import json
from pathlib import Path

import pytest

from wpa.sets import reconstruct_sets
from wpa.state import extract_bo3_context

BATTLE_LOGS = Path(__file__).parent.parent / "battle_logs"
BO3_FILES = [
    "logs_gen9championsvgc2026regmabo3.json",
    "logs_gen9championsvgc2026regmbbo3.json",
]

# A real, hand-verified 3-game set from logs_gen9championsvgc2026regmabo3.json:
# game 1 (0-0) -> Glimme wins -> game 2 (0-1) -> RandomDuVGCFR wins -> game 3 (1-1).
KNOWN_SET_ID = "gen9championsvgc2026regmabo3-2600683599"
KNOWN_GAME_TAGS = {
    1: "gen9championsvgc2026regmabo3-2600683600",
    2: "gen9championsvgc2026regmabo3-2600684455",
    3: "gen9championsvgc2026regmabo3-2600685894",
}
KNOWN_SCORES = {1: (0, 0), 2: (0, 1), 3: (1, 1)}


def _load(tag: str) -> str:
    logs = json.loads(
        (BATTLE_LOGS / "logs_gen9championsvgc2026regmabo3.json").read_text(
            encoding="utf-8"
        )
    )
    return logs[tag][1]


def test_score_extracted_from_the_logs_own_circle_table_not_just_universal_rules():
    for game_index, tag in KNOWN_GAME_TAGS.items():
        log = _load(tag)
        set_id, extracted_index, score = extract_bo3_context(log)

        assert set_id == KNOWN_SET_ID
        assert extracted_index == game_index
        assert score == KNOWN_SCORES[game_index], (
            f"game {game_index}: expected {KNOWN_SCORES[game_index]}, got {score}"
        )


def test_game_2_score_no_longer_none():
    # The Week 2 gap this task closes: game 2's score used to be None
    # because a single log couldn't see game 1's result via |win|. It's
    # encoded directly in the log's own circle table instead.
    log = _load(KNOWN_GAME_TAGS[2])
    _, _, score = extract_bo3_context(log)
    assert score is not None
    assert score == (0, 1)


def test_game_3_score_carries_evidence_from_games_1_and_2():
    # DEFINITIONS #11.3: a game-3 state is not a fresh start. Its score
    # entering the game (1, 1) is itself evidence that both prior games
    # were played and split - not a placeholder or a universal default
    # applied blindly.
    log = _load(KNOWN_GAME_TAGS[3])
    _, game_index, score = extract_bo3_context(log)
    assert game_index == 3
    assert score is not None
    assert score == (1, 1)
    assert sum(score) == 2, "two prior games must have been decided"


@pytest.fixture(scope="module", params=BO3_FILES)
def bo3_corpus(request):
    """(logs, reconstruction result) for one full bo3 corpus file. Session-
    shared per file so the ~78k/~4k-entry JSON isn't reloaded per test."""
    logs = json.loads((BATTLE_LOGS / request.param).read_text(encoding="utf-8"))
    return logs, reconstruct_sets(logs)


def _winner_role(log: str) -> str | None:
    win_idx = log.find("|win|")
    if win_idx < 0:
        return None
    winner = log[win_idx : log.find("\n", win_idx)].split("|")[2]
    for role in ("p1", "p2"):
        pidx = log.find(f"|player|{role}|")
        name = log[pidx : log.find("\n", pidx)].split("|")[3]
        if name == winner:
            return role
    return None


def test_every_game_maps_to_at_most_one_set(bo3_corpus):
    logs, result = bo3_corpus

    assigned_tags = set()
    for set_id, games in result.sets.items():
        for game_index, tag in games.items():
            assert tag not in assigned_tags, f"{tag} assigned to multiple sets"
            assigned_tags.add(tag)
    assert len(assigned_tags) + len(result.unassignable) == len(logs)


def test_unassignable_fraction_is_at_most_two_percent(bo3_corpus):
    # "Unassignable" = a bo3-format game whose set id and game index could
    # not be extracted at all (no bestof banner, or malformed). This is
    # different from a set being *incomplete* in our corpus (a sibling
    # game missing) - a game is still fully assignable to its own set
    # even when its siblings aren't in the corpus. In the full corpus this
    # is 3 games out of 81,676 (0.0037%), and all 3 turned out to be a
    # real best-of-5 match (a "-bestof5-" link, not "-bestof3-") sitting
    # in the bo3-named file - correctly excluded, not a parsing failure.
    logs, result = bo3_corpus

    fraction = len(result.unassignable) / len(logs)
    assert fraction <= 0.02, (
        f"{fraction:.2%} of games could not be assigned to a set "
        f"(dispatch threshold: 2%)"
    )


def test_game_index_is_always_one_two_or_three(bo3_corpus):
    _logs, result = bo3_corpus

    for set_id, games in result.sets.items():
        assert set(games.keys()) <= {1, 2, 3}, f"{set_id}: {sorted(games.keys())}"


def test_a_complete_three_game_set_has_no_gaps(bo3_corpus):
    _logs, result = bo3_corpus

    complete = [g for g in result.sets.values() if len(g) == 3]
    assert complete, "expected at least one complete 3-game set in the corpus"
    for games in complete:
        assert sorted(games.keys()) == [1, 2, 3]


def test_games_per_set_ratio_is_measured_not_assumed(bo3_corpus):
    _logs, result = bo3_corpus

    n_games = sum(len(g) for g in result.sets.values())
    n_sets = len(result.sets)
    ratio = n_games / n_sets
    # Real range observed on the full corpus: ~1.7. Wide bounds here as a
    # sanity check against a gross regression, not a claim that ~3 (the
    # dispatch's "roughly a third") is correct - it measurably isn't.
    assert 1.0 < ratio <= 3.0


def test_reconstructed_score_matches_independently_computed_score(bo3_corpus):
    # Cross-validation, not just internal consistency: for every complete
    # 3-game set, recompute the score entering games 2 and 3 from each
    # prior game's own |win| line, independent of the circle-table
    # extraction, and confirm they agree.
    logs, result = bo3_corpus

    complete = [g for g in result.sets.values() if sorted(g.keys()) == [1, 2, 3]]
    checked = 0
    for games in complete:
        g1_log, g2_log, g3_log = (logs[games[i]][1] for i in (1, 2, 3))
        w1, w2 = _winner_role(g1_log), _winner_role(g2_log)
        if w1 is None or w2 is None:
            continue  # unresolved winner (e.g. a name-matching edge case)

        _, _, score2 = extract_bo3_context(g2_log)
        _, _, score3 = extract_bo3_context(g3_log)
        expected2 = (1, 0) if w1 == "p1" else (0, 1)
        wins = {"p1": 0, "p2": 0}
        wins[w1] += 1
        wins[w2] += 1
        expected3 = (wins["p1"], wins["p2"])

        assert score2 == expected2, f"{games[2]}: {score2} != {expected2}"
        assert score3 == expected3, f"{games[3]}: {score3} != {expected3}"
        checked += 1

    assert checked > 0, "expected at least one cross-validatable complete set"
