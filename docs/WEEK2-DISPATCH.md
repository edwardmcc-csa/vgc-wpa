# Week 2 — Dispatch Brief (M1b: Set Reconstruction)

**For:** Claude Code, or a contract engineer working unsupervised
**Prerequisite:** Week 1 complete, CI green
**Time budget:** 5 days
**Definition of done:** every checkbox ticked, `pytest` green in CI, one clean re-parse completed

**Resequenced:** this was going to be M2, the simulation harness. It has moved to week 3. Everything that changes the parsed schema is being batched into this week so the expensive full re-parse happens exactly once.

---

## Context

Week 1 proved the pipeline runs. It also showed the upstream parser is game-scoped and throws away best-of-three structure, and that our corpus uses open team sheets. Both change what a state record must contain. A full parse costs about an hour and 49GB, so all schema work lands this week, then we re-parse once.

Read `docs/DEFINITIONS.md` §11 and §12 before starting. They are the contract.

Still no modelling this week.

---

## Task 1 — Verify what the team sheets reveal

Cheap, and it sizes a later milestone, so it goes first.

- [ ] Parse a `|showteam|` string field by field
- [ ] Confirm across at least 20 logs from different files, not one
- [ ] Write `docs/SHEET-FIELDS.md`: every field, populated or empty, with an example

Specifically settle: are EVs, natures, IVs and Tera type present or absent? Do not assume — the week 1 sample showed empty slots but was truncated.

**Report back:** the field list. This defines the entire scope of M4b, so getting it wrong sets that milestone's size wrong.

## Task 2 — Reconstruct set structure

The data is already in the corpus: each game log carries a parent set link (`game-bestof3-...`), the game index in plain text (`Game 3 of a best-of-3`), and the running set score in an HTML table where filled circles are games won. This is a grouping pass, not a re-scrape.

- [ ] Extract set ID, game index, and set score entering the game, for every game
- [ ] Add all three to our state schema in `wpa/state.py`
- [ ] Tests first, as always:
  - every game maps to exactly one set
  - distinct set count is roughly a third of game count
  - game indices within a set are 1, 2, optionally 3, with no gaps
  - the reconstructed set score entering each game matches the score encoded in the log
  - a game-3 state carries evidence from games 1 and 2 (DEFINITIONS §11.3)

**Stop and report if** more than 2% of games cannot be assigned to a set.

## Task 3 — Data splitting rule (new, and it matters)

Week 1 revealed two trajectories per battle — one per player perspective. Three games share a set. Both players' teams persist across the set. A random split by trajectory would put the same game, and the same matchup, on both sides of train and test. Calibration would look excellent and mean nothing.

- [ ] Implement splitting **by set ID**. All six trajectories from a best-of-three go to the same side
- [ ] `tests/test_split_integrity.py` — assert no set ID, and no exact team pairing, appears in both train and test
- [ ] Expose an archetype-level holdout option for M4 (DEFINITIONS §13, being added)

This is the single highest-consequence item this week. A leaky split will not announce itself; it will just make every later metric a lie.

## Task 4 — Tighten the ordering invariant

Week 1 correctly relaxed "turn numbers strictly increase" to "never decrease," because DEFINITIONS §6 allows multiple decision points per game turn. That was my error in the brief. But the relaxed version will not catch a stuck counter.

- [ ] Replace with: the pair *(turn, decision index)* strictly increases lexicographically

## Task 5 — Regression fixtures from the known failures

- [ ] Save the six battle IDs that fail at `logs2trajs.py:259` into a fixture file
- [ ] A test that records the current count and fails if it grows

Free regression coverage. If that assertion starts firing more often after this week's schema work, we want to know it is new rather than pre-existing.

## Task 6 — Account for the output size

601MB in, 49GB out is roughly 80×.

- [ ] Document in `docs/DATA-FOOTPRINT.md` what the expansion consists of
- [ ] Note whether a more compact representation is available without losing information

Investigate and report only. Do not optimise this week.

## Task 7 — The re-parse

- [ ] Once tasks 1 through 4 are merged and green, run one full parse with the new schema
- [ ] Use the batching workaround from week 1; do not patch upstream memory behaviour
- [ ] Confirm failure count is still 6 and nothing new appeared

**Report back:** parse statistics, wall clock, disk used, and confirmation the set fields are populated throughout.

---

## Rules of engagement

1. **Test first, always.** Failing test, then implementation. Show the failure.
2. **Additive only.** Do not edit VGC-Bench's own modules — everything in `wpa/`.
3. **No modelling.** No win probability, no evaluation function, no heuristics about who is ahead.
4. **No damage enumeration.** That is M3 and it has design constraints you have not been briefed on.
5. **One re-parse.** If you discover another schema change is needed, raise it before running task 7, not after.
6. **Stop and ask** on: licence questions, anything needing credentials or payment, >2% unassignable games, or if set reconstruction needs upstream patches.
7. **One commit per task.**

## Decisions taken since your last report

- **`vgc_bench.eval` stays dead.** Alpha-Rank and cross-evaluation rank populations of competing agents, which serves their benchmark paper, not our product. Do not replace open-spiel. If M6 later needs it, WSL is the route.
- **Do not fix the memory ceiling.** Parse output is a build artifact. Keep the batching workaround documented in the runbook. This week's re-parse is expected and budgeted.

## Report format

Prose, not a status table. Cover: the sheet field list, set reconstruction rates, re-parse statistics, and a link to the green CI run. Flag anything surprising — last week's surprises section was the most useful part of the report.
