# Week 6 report: v2 on our own decision table, with speed (M4 v2)

30 October 2026. Brief: `docs/WEEK6-DISPATCH.md`. Commits `cb34a12` (Task 1) to
`f169005` (claims), plus this report. All numbers are per format. Reg M-B numbers
carry their sample size; read them with it.

## The headline

On the untouched **test split**, v2 beats v0 in both formats and **passes the gate
in both**, with no recalibration:

| test split | decision points | sets | v2 Brier | v0 Brier | v2 - v0 (95% interval) |
|---|---|---|---|---|---|
| Reg M-A (Reg M-A model) | 170,644 | 5,108 | 0.1952 | 0.2091 | -0.0139 (-0.0153 to -0.0125) |
| Reg M-B (pooled model) | 8,917 | 237 | 0.1959 | 0.2130 | -0.0170 (-0.0220 to -0.0120) |

Every calibration bin is within 0.024 of what happened in Reg M-A and within 0.023
in Reg M-B (tolerance 0.05). This was the third test opening in total, logged in
`models/test_openings.json` against commit `0ff1a4f`.

Week 5's gate failure was the selection bias in the old states, as suspected: once
every decision is kept, calibration comes right without any correction. The gain
over v0 is also larger than in Week 5 (-0.0086 in Reg M-A then, -0.0139 now).
The raw Brier values are not comparable across the two weeks, because the rows
are different. Week 6 keeps every decision, and v0 itself scores differently on
the new rows.

**One departure from the brief:** Reg M-A was trained on a 20% sample of its sets,
not all of them. The development machine does not have the memory for the full
set. The commands to run it on your computer are in the runbook, Section 15 step 7.
The features are already in your folder, so nothing needs rebuilding.

## Task 1: the decision table

Decision points now come from the game's own structure, never from what happens
next. Every turn start has one row per player. The checks are in
`docs/DECISION-TABLE.md`: the board matched the stored states in every one of
391,692 Pokemon compared. Over the full table:

| | sets | decision points | label rate, all rows | label rate, turn-start rows |
|---|---|---|---|---|
| Reg M-A train / validation / test | 40,502 / 5,167 / 5,108 | 1,354,653 / 173,070 / 170,644 | 0.488 / 0.488 / 0.488 | **0.5000** in each |
| Reg M-B train / validation / test | 1,824 / 199 / 237 | 67,150 / 7,477 / 8,917 | 0.487 / 0.483 / 0.487 | **0.5000** in each |

Turn-start rows are won exactly half the time, as they must be. Over all rows the
rate is a little under half because the side losing Pokemon has more replacement
decisions. That is the game's structure, not a look at the future.

## Task 2: speed (group F)

For each side, we record:
- base Speed of the active Pokemon (the Mega form once it has Mega Evolved);
- Choice Scarf ×1.5 and Tailwind ×2;
- the fastest Pokemon on the bench, and the fastest and slowest still unseen;
- who acts first, how many pairs each side outspeeds, and how many unseen Pokemon would outspeed the opponent's fastest.

Trick Room reverses the order. Priority moves, paralysis and stat stages are not
included. Only public information is read, and a test guards that.

## Tasks 4 and 5: v2 on the validation split

Settings were fixed before any v2 result: the Week 5 grid winner (learning rate
0.05, 31 leaves). The number of rounds was chosen on validation.

| validation split | sets | v2 Brier | v0 Brier | v2 - v0 | without speed | what speed adds |
|---|---|---|---|---|---|---|
| Reg M-A (20% sample, 575 rounds) | 5,167 | 0.1943 | 0.2099 | -0.0155 (-0.0169 to -0.0143) | 0.1964 | **-0.0020 (-0.0026 to -0.0014)** |
| Reg M-B (pooled, 325 rounds) | 199 | 0.1863 | 0.2033 | -0.0169 (-0.0239 to -0.0101) | 0.1873 | -0.0010 (-0.0035 to +0.0019) |

Speed earns its place in Reg M-A: the whole interval is below zero. In Reg M-B,
with 199 sets, the data cannot tell whether speed helps. The gate passed on
validation in both formats, so no recalibration was applied. In Reg M-A every bin
is within 0.012. In Reg M-B the 0.7-0.8 bin was off by 0.049 against the 0.05
tolerance (520 rows), which is close. On test the same bin is within 0.016.

## Expert claims, re-scored

Full write-up: `docs/EXPERT-CLAIMS-RESULTS.md` (Week 6 section). The follow-up
positions are now made by editing the board: the real reserve comes in, and a turn
comes off every timer. The features are then recomputed, so the speed of whoever
comes in is seen.

**EC-001 (don't knock out both if it brings their sweepers in under Tailwind).**
All three models still prefer the double knock-out in every position: 138 in
Reg M-A and 2 in Reg M-B. This includes the 105 Reg M-A positions where their
reserve does outspeed us after the double knock-out. The claim's full premise
(our pair faster now, their reserve faster after) never turns up in the validation
games. Speed alone does not make the claim true for these positions. The missing
piece is likely damage: nothing tells the model how hard the incoming Pokemon hit.

**EC-002 (sacrifice the spent Pokemon to keep the strong one).** v1 preferred keeping the spent
Pokemon (agreed with the claim 16-22% of the time). v2 agrees 35-37% overall.
Where the sacrifice gains speed, v2 agrees about half the time (49% of 182 Reg M-A
positions, 52% of 97 Reg M-B positions) and is nearly indifferent on average. That
is the claim's own condition at work.

## Surprises

1. **Calibration fixed itself.** Recalibration was built and ready, but the gate
   passed without it.
2. **Reg M-A reached the 600-round cap.** It was still improving, but only by
   0.0001 over its last 100 rounds, so on the 20% sample the cap costs almost
   nothing. With all the sets (step 7) it may matter more. Changing the cap would
   change the fixed settings, so it is yours to decide.
3. **EC-001's exact situation is rare.** In 138 Tailwind positions, the "our pair is
   faster, their reserve is faster still" case never occurs. Either the claim
   describes a narrower situation than these, or damage matters more than speed.

## Process notes

- Two tests came after the code they test, not before: the test of how the v2
  training tables are put together (`tests/test_evaluate.py`), and the test of
  scoring a claim's choice tree (`tests/test_claims_v2.py`). Everything else was
  written test-first.
- On the development machine: 440 tests pass and 3 are skipped. 15 test files
  cannot load there because they need the bot libraries; they are unchanged this
  week. ruff and pyright are clean.

## Decisions for the product owner

1. **Run full Reg M-A training on your computer** (runbook Section 15 step 7) and
   compare the two `report.txt` files. Scoring it on test would be a fourth
   logged opening; recommend only if it is clearly better on validation.
2. **Raise the 600-round cap for the full-data run?** Only if the full-data run
   also ends at the cap (its `models_v2_full\regma\ABCDEF.json` will show
   `"n_iter"` near 600). It is a one-line change (surprise 2).
3. **EC-001: add a damage feature, or narrow the claim?** A damage feature would
   be a rough estimate of how much the incoming Pokemon can take off our active
   Pokemon. Alternatively, rewrite the claim for the situation you have in mind.
   Examples of the 105 positions can be pulled for you to judge.
4. **Next milestone.** v2 is ready to be used for decision-level win probability
   added (M5): scoring the choice actually made against the alternatives.
