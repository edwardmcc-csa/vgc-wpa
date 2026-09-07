# Week 3 — Dispatch Brief (M1b: Set Reconstruction)

**For:** Claude Code, or a contract engineer working unsupervised
**Prerequisite:** Week 2 complete, CI green, all six Week 2 tasks committed
**Time budget:** 5 days
**Definition of done:** every checkbox ticked, `pytest` green in CI, one clean re-parse completed

**Note on sequencing:** this milestone was originally week 2. It was deferred when the simulation harness ran first. Nothing was lost — M2 does not depend on M1b — but the full re-parse it requires has been waiting since week 1, so it lands this week.

---

## Context

Week 1 proved the pipeline runs. Week 2 proved we can run new battles on demand. Neither fixed the fact that the upstream parser is **game-scoped**: it throws away best-of-three structure, and our corpus uses open team sheets. Both change what a parsed state record must contain.

Week 2's Task 4 already added set ID, game index and set score to `wpa/state.py` for **live** battles. This week does the same for **replay** battles, populating those same fields from the log corpus. One schema, not two — that rule held for the live and replay round-trip in Week 2 and it holds here.

A full parse costs about an hour and 49GB. Every schema-affecting change lands before it, then we re-parse exactly once.

Read `docs/DEFINITIONS.md` §11, §12 and §13 before starting. They are the contract.

Still no modelling this week.

---

## Task 1 — Verify what the team sheets reveal

Cheap, and it sizes a later milestone, so it goes first.

- [ ] Parse a `|showteam|` string field by field
- [ ] Confirm across at least 20 logs drawn from different files, not one
- [ ] Write `docs/SHEET-FIELDS.md`: every field, populated or empty, with an example

Specifically settle: are EVs, natures, IVs and Tera type present or absent? Do not assume — the week 1 sample showed empty slots but was truncated.

**Report back:** the field list. This defines the entire scope of M4b, so getting it wrong sets that milestone's size wrong.

## Task 2 — The Terastallisation gap

Week 2's fixture corpus surfaced that Terastallisation is disabled in the simulation format we are using. The brief asked for at least one Tera battle among the golden fixtures and that requirement could not be met. This needs settling now, because M3 is next and Tera changes damage calculation.

- [ ] State plainly whether Tera is absent from the **simulation** path only, or also from the **replay corpus**. These are different problems with different costs
- [ ] Quantify it: what fraction of parsed replay battles contain a Terastallisation event?
- [ ] Establish whether a format string exists on the pinned Showdown version that enables Tera in VGC doubles, and if so what it is
- [ ] Write `docs/TERA-COVERAGE.md`: the finding, the numbers, and what it means for the fixture corpus

Investigate and document. **Do not** change the configured format or regenerate fixtures without raising it first — that is a decision for the product owner, not a fix to apply in passing.

## Task 3 — Reconstruct set structure from the replay corpus

The data is already there: each game log carries a parent set link (`game-bestof3-...`), the game index in plain text (`Game 3 of a best-of-3`), and the running set score in an HTML table where filled circles are games won. This is a grouping pass, not a re-scrape.

- [ ] Extract set ID, game index, and set score entering the game, for every game
- [ ] Populate the **existing** set fields added to `wpa/state.py` in Week 2 Task 4. Do not introduce a parallel representation for the replay path
- [ ] Tests first, as always:
  - every game maps to exactly one set
  - distinct set count is roughly a third of game count
  - game indices within a set are 1, 2, optionally 3, with no gaps
  - the reconstructed set score entering each game matches the score encoded in the log
  - a game-3 state carries evidence from games 1 and 2 (DEFINITIONS §11.3)
  - the replay path and the live path produce the same schema for an equivalent position

**Stop and report if** more than 2% of games cannot be assigned to a set.

## Task 4 — Data splitting rule

The parser emits two trajectories per game, one per player perspective. Up to three games share a set. Both players' teams persist across the set. A random split by trajectory would put the same game, and the same matchup, on both sides of train and test. Calibration would look excellent and mean nothing.

- [ ] Implement splitting **by set ID**. All six trajectories from a best-of-three go to the same side
- [ ] `tests/test_split_integrity.py` — assert no set ID, and no exact team pairing, appears in both train and test
- [ ] Expose an archetype-level holdout option for M4 (DEFINITIONS §13)

This is the single highest-consequence item this week. A leaky split will not announce itself; it will just make every later metric a lie. DEFINITIONS §13 makes this non-negotiable — it is not a performance trade-off.

## Task 5 — Tighten the ordering invariant

Week 1 relaxed "turn numbers strictly increase" to "never decrease," correctly, because DEFINITIONS §6 allows multiple decision points per game turn. That was an error in the original brief. But the relaxed version will not catch a stuck counter.

- [ ] Replace with: the pair *(turn, decision index)* strictly increases lexicographically
- [ ] Confirm the invariant holds on both the replay corpus and the Week 2 live fixtures

## Task 6 — Regression fixtures from the known failures

- [ ] Save the six battle IDs that fail at `logs2trajs.py:259` into a fixture file
- [ ] A test that records the current count and fails if it grows

Free regression coverage. If that assertion starts firing more often after this week's schema work, we want to know it is new rather than pre-existing. Note that Task 8 is expected to confirm the count is still exactly six.

## Task 7 — Account for the output size

601MB in, 49GB out is roughly 80×.

- [ ] Document in `docs/DATA-FOOTPRINT.md` what the expansion consists of
- [ ] Note whether a more compact representation is available without losing information

Investigate and report only. **Do not optimise this week.** The set fields added in Task 3 will grow this number; say by how much.

## Task 8 — The re-parse

- [ ] Once Tasks 3, 4 and 5 are merged and green, run one full parse with the new schema
- [ ] Use the batching workaround from week 1; do not patch upstream memory behaviour
- [ ] Confirm failure count is still 6 and nothing new appeared
- [ ] Confirm the set fields are populated throughout, not just on a sample

**Report back:** parse statistics, wall clock, disk used, and the populated-field confirmation.

## Task 9 — Runbook update

- [ ] Extend `docs/RUNBOOK.md` with how to run the re-parse and how to inspect a parsed record's set fields. Written for a non-developer, same standard as the Week 2 sections

---

## Rules of engagement

1. **Test first, always.** Failing test, then implementation. Show the failure.
2. **Additive only.** Do not edit VGC-Bench's own modules — everything in `wpa/`.
3. **No modelling.** No win probability, no evaluation function, no heuristics about who is ahead.
4. **No damage enumeration.** That is M3 and it has design constraints you have not been briefed on.
5. **One re-parse.** If you discover another schema change is needed, raise it before running Task 8, not after. This is the entire reason M1b is batched into a single week.
6. **Do not change the battle format string** or regenerate the Week 2 fixture corpus. Task 2 investigates; it does not act.
7. **Do not touch `docs/vgc-wpa-engineering-plan.md`.** The product owner has that file open.
8. **Stop and ask** on: licence questions, anything needing credentials or payment, >2% unassignable games, or if set reconstruction turns out to need upstream patches.
9. **One commit per task.**

## Carried-forward environment notes

- `open-spiel` was removed from `pyproject.toml`; VGC-Bench's own evaluation module will not run. Do not try to fix this.
- Running Python 3.14, at the top edge of VGC-Bench's stated support range. If you hit strange import or typing errors, suspect this first and report it — do not work around it silently.
- **Live connections accumulate.** Repeated simulation runs in one terminal session can hang, per the Week 2 Task 4 finding now documented in the runbook. Restart between runs.
- **Battles are not deterministic.** Week 2 established that seed control is not exposed on the pinned Showdown version. The 20-battle fixture corpus is our reproducibility mechanism, which is why it is not to be regenerated casually.
- Parse output is a build artifact. Keep the batching workaround documented. This week's re-parse is expected and budgeted.

## Decisions already taken

- **`vgc_bench.eval` stays dead.** Alpha-Rank and cross-evaluation rank populations of competing agents, which serves their benchmark paper, not our product. Do not replace open-spiel.
- **Do not fix the memory ceiling.** See above.

## Report format

Prose, not a status table. Cover: the sheet field list, the Tera finding with numbers, set reconstruction rates, re-parse statistics, and a link to the green CI run. Flag anything surprising — the surprises sections have been the most useful part of both reports so far.
