# Week 8 — Dispatch Brief (finish M4b: who was brought, Bo3 memory, what each side can do, the whole board)

**Status:** drafted 30 Oct 2026 from the PO's decisions after the Week 7 report.
Work starts when the PO says go.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

v3 knows how hard things hit. What it still gets wrong:

- **What could be in the back.** All of the opponent's unseen sheet Pokemon are
  treated as equally likely, including the two that were never brought.
- **Bo3 memory.** Each game of a set starts from nothing, although game 1 showed
  which four were brought and narrowed their spreads.
- **What can actually happen this turn.** Fake Out only works on a Pokemon's first
  turn in, a Choice item locks a Pokemon into one move, Protect gets riskier when
  repeated, and each side has one Mega Evolution.
- **Endgames.** Damage is known only between the active Pokemon.

The plan's M4b milestone also requires the pipeline to run with the opponent's
sheet blanked. That has never been tested.

## Decisions (PO, 30 Oct 2026)

1. **EC-001 is accepted as a niche case.** It is a caveat for positioning, not
   something the model must show on average.
2. **Reg M-B models are used as trained, never recalibrated.** Done in
   `wpa/evaluate.py` (`NEVER_RECALIBRATE`).
3. **Training rounds are capped at 1,000** (was 600). Done in `wpa/model.py`.
4. **v3 on every training game runs on the PO's computer** (runbook Section 16,
   step 8).
5. **This week's scope:** the four features below, plus the blank-sheet run.

## Tasks

### Task 1 — Which four they brought (M4b)
- [ ] For each side, at each decision: the chance that each sheet Pokemon was
      brought. It uses team preview (both sheets), what has appeared so far in this
      game, and earlier games of the set. Every set of four agrees with what has
      been seen.
- [ ] **Training labels:** the four that appear in a game. A game where fewer than
      four appeared is kept out of training and counted.
- [ ] **The plan's test, per format on validation:** at team preview it beats the
      uniform guess over the 15 possible sets of four.
- [ ] The unseen-Pokemon features (groups E, F and G) are weighted by this chance,
      instead of treating every unseen sheet Pokemon alike.
- [ ] Tests first. No look-ahead: cutting the game after a decision changes
      nothing.

### Task 2 — Bo3 memory
- [ ] In games 2 and 3 of a set, each side's spread estimates start from where the
      previous game left them, not from the usage statistics.
- [ ] What each player brought, and led with, in earlier games feeds Task 1.
- [ ] **The plan's test:** at the start of game 2, belief is narrower than at the
      start of game 1. Measure it, per format.
- [ ] Nothing from a later game of the set is ever used.

### Task 3 — What each side can do this turn (new group H)
- [ ] For each active Pokemon:
      - Fake Out still works (its first turn in, and not yet used since);
      - locked by a Choice item, and into which move. While locked, group G uses
        only that move;
      - the chance its next Protect works (from the Protect counter).
- [ ] For each side: Mega Evolution still available.
- [ ] Tests first.
- [ ] **Real-data check per format:** every Fake Out in the logs that worked was
      flagged as available; every move from a locked Pokemon was the locked move.
      Anything else is listed and explained.

### Task 4 — Damage across the whole board (extend group G)
- [ ] Between every remaining Pokemon on each side (seen, or likely in the back
      from Task 1), who knocks out whom in one hit and in two.
- [ ] **"Outspeeds and knocks out":** the pairs where one side's Pokemon moves
      first and knocks the other out.
- [ ] Short summaries for each side: how many of theirs we can remove this way, and
      how many of ours are exposed.
- [ ] **Build time** measured on one shard first. The full table must still build
      on the PO's computer in a sensible time (say so in the report if not).

### Task 5 — Blank sheets (M4b, non-negotiable)
- [ ] The whole pipeline runs with the opponent's sheet blanked:
      - species are known only as they appear;
      - items, abilities and moves are known only as revealed;
      - spreads come from the statistics alone.
- [ ] The result is a valid but less confident win probability (`WP_public`).
- [ ] On validation, per format, report how much is lost against full sheets. No
      gate this time.

### Task 6 — v4 models and evaluation
- [ ] Same settings (learning rate 0.05, 31 leaves); rounds chosen on validation,
      up to 1,000.
- [ ] Reg M-A on the 20% sample here and on the full set on the PO's computer.
      Reg M-B uses the pooled model, without recalibration.
- [ ] **Ablation:** v3 against each addition (Tasks 1–2, Task 3, Task 4) as paired
      differences per format. Gate on validation.
- [ ] The test split is opened once for v4 if the PO agrees. It would be the fifth
      opening, logged.
- [ ] Expert claims re-scored. EC-001's reserve threat now comes from the likely
      back two.

### Task 7 — Runbook and report

## Out of scope this week
- **Decision versus luck (M5).** This is next week, on v4.
- **Your own team's spreads, and re-scoring your games with other spreads** (the
  team-building use). This needs your team export first.

## For the PO before starting
1. **Test split for v4:** yes or no (it would be the fifth opening).
2. **The full v3 run on your computer:** start it whenever convenient. Week 8 does
   not wait for it.
