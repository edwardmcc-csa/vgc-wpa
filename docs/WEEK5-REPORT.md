# Week 5 report: the first learned win probability model (M4 v1)

30 October 2026. Brief: `docs/WEEK5-DISPATCH.md`. Commits `ff1cafe` (Task 1) to
`ca33e71` (Task 9). All numbers are per format. Reg M-B numbers carry their
sample size; read them with it.

## The headline

On the untouched **test split**, v1 beats the v0 baseline clearly in Reg M-A: Brier
0.2107 against 0.2192, a difference of -0.0086 (95% interval -0.0098 to -0.0074,
from resampling whole sets; 158,711 decision points in 5,108 sets). In Reg M-B the
model trained on Reg M-B alone **does not** beat v0 on test (0.2223 against 0.2226,
interval -0.0068 to +0.0058, 237 sets). The PO-approved secondary model, trained
on both formats with a format flag and scored on Reg M-B only, does: 0.2111 against
0.2226, -0.0114 (-0.0158 to -0.0068). That makes the Reg M-B decision below the most
important one this week.

The gate fails for Reg M-A on calibration (one bin, 0.7-0.8, off by 0.055 against a
0.05 tolerance). The cause is not the model. It is the second surprise below, and
on the decision points it does not affect, calibration is within 0.012 in every bin.

## What each state represents, and what leaks (Task 1)

A stored state is a snapshot taken when a player has to choose. Turn 0 holds team
preview and lead selection; each later turn has a decision at its start and one per
forced switch. The last state of every file is a terminal marker carrying the only
`outcome`, not a decision. **54% of Reg M-A decision points and 52% of Reg M-B carry
observations of events that happen after the decision**: the parser hangs a turn's
events on that turn's last decision, which is the one before the moves when there is
no forced switch. A separate hit-point check agrees. The rule adopted: a decision at
turn N uses observations from earlier turns only. `docs/STATE-TIMING.md`.

## The timer join (Task 3)

Each state is matched to the timers in force at its own moment, reproducing where
the log reader takes its snapshots. In the sample checked (2,930 Reg M-A and 880
Reg M-B state files) every file lined up exactly; in the full feature build, 4 files
in the whole corpus did not and were left out. Against the observations' own record of
weather, field and side conditions, **no disagreement is unexplained** in either
format; the explained ones are weather changed by a switch-in before the first
move. `docs/TIMER-JOIN.md`.

## Ablation: which feature groups earn their place (Task 7)

Validation split. A state only; B field presence from earlier turns; C timers; D
team-sheet capabilities; E unseen sheet positions. Reg M-A trained on 20% of its
training sets (the development machine's limit), Reg M-B on all.

| | Reg M-A Brier | Reg M-B Brier |
|---|---|---|
| v0 | 0.2198 | 0.2143 |
| A | 0.2128 | 0.2088 |
| A+B | 0.2125 | 0.2075 |
| A+B+C | 0.2115 | 0.2057 |
| A+B+C+D | 0.2095 | 0.2052 |
| A+B+C+D+E (v1) | 0.2096 | 0.2045 |

Each step against the one before, paired, with its interval:

| Step | Reg M-A | Reg M-B (199 sets) |
|---|---|---|
| add B (field presence) | -0.0003 (-0.0005 to -0.0001) | -0.0013 (-0.0040 to +0.0010) |
| add C (timers) | -0.0010 (-0.0014 to -0.0007) | -0.0018 (-0.0031 to -0.0005) |
| add D (team sheet) | -0.0019 (-0.0027 to -0.0011) | -0.0005 (-0.0056 to +0.0046) |
| add E (unseen positions) | +0.0001 (-0.0002 to +0.0004) | -0.0007 (-0.0035 to +0.0020) |

The biggest gain is A itself: a learned model of the same board v0 sees. Timers
(C) and the team sheet (D) earn their place in Reg M-A beyond doubt; field presence
(B) adds little once timers are in, and unseen positions (E) add nothing measurable.
v1 (the last row) is the only one recalibrated, so the E step mixes in the
recalibration.

## v1 against v0, and calibration (Tasks 6 and 7)

The grid was fixed before any result; the validation split chose the same setting
in both formats (learning rate 0.05, 31 leaves): 500 rounds in Reg M-A, 250 in Reg
M-B. Both failed calibration on validation (Reg M-A two bins, Reg M-B four), so a
symmetric monotone recalibration was fitted on validation. That improved Reg M-B's
validation Brier from 0.2064 to 0.2045 and left Reg M-A at 0.2096-0.2098. The
validation figures are therefore optimistic, Reg M-B's especially: its 199 sets
chose the rounds, the setting and the calibration. The test split was opened twice:
once for v1 in both formats (logged, commit `d0993d6`) and once for the secondary
pooled model on Reg M-B. Nothing was chosen from it.

The model is symmetric by construction: a mirrored position gets exactly 0.5 and
the two players' predictions sum to 1. The trend of predicted win probability by
Pokemon left rises as the opponent loses Pokemon in every step (Reg M-A: 4 v 4
0.500, 4 v 3 0.689, 4 v 2 0.893, 4 v 1 0.986).

## Expert claims (Task 8)

Neither claim can be judged fairly yet. EC-001 (don't knock out both weakened
Pokemon while their Tailwind still runs) turns on who is faster, and no feature
carries speed: both models always prefer the double knock-out. For EC-002 (sacrifice
the spent Pokemon), v0 agrees only because it adds up hit points; v1 disagrees in
93% of positions because it values a Pokemon on the board. `docs/EXPERT-CLAIMS-RESULTS.md`.

## Is there anything the model needs that a side file cannot give?

**No. No second re-parse is needed**, and a re-parse with the same log reader would
not fix the biggest problem found (surprise 2). Everything v1 uses comes from the
stored states plus side files built from the logs (timers, team sheets). What the
next round needs is all public and all in the logs: base Speed and types (Showdown
data), stat boosts, items used up, the turn a Pokemon came in (for Fake Out). Each
is a side file.

## Surprises

1. **Observations leak the future** on half of all decision points (Task 1, above).
2. **The stored decision points are selected on what happens next.** The log reader
   skips a player's decision when one of their slots did nothing and one of their
   Pokemon fainted during that turn. Losers lose that turn more often, so winners
   have more rows (9.6 against 8.9 per file in Reg M-A), turn-start rows are won 56%
   of the time instead of 50%, and positions with one Pokemon left are won 43% of the
   time (they are recorded mostly when that Pokemon survived the turn). Every model
   trained on these rows overrates losing positions, and calibration on all rows
   cannot be fixed by any symmetric model. On the turn-start decisions both players
   have, the label rate is exactly 50% and v1 is within 0.012 of observed in every
   bin. The clean fix is a decision table built from the logs ourselves, every
   decision point, no skipping; it does not need poke-env or a re-parse.
3. **About 35% of games end by forfeit or timeout**, with the loser's Pokemon often
   healthy. The model partly predicts concessions.
4. **Reg M-B alone is too small for its own model.** The Reg M-B-only v1 looked good
   on validation (-0.0098) and fell to nothing on test; the pooled model with a
   format flag held up (-0.0114 on test).
5. **The play-style archetypes are mostly broad** (Balance half of all teams); only
   small ones can be held out (`docs/PLAYSTYLES.md`). They are not used in any number.

## Decisions for the product owner

1. **Reg M-B model**: adopt the pooled model with a format flag (trained on both
   formats, judged on Reg M-B only), or keep Reg M-B on its own model? The test
   result favours pooling; DEFINITIONS section 15 says per format, which a format
   flag can honour in evaluation but not in training.
2. **Decision-point selection**: approve building our own decision table from the
   logs (all decision points, no skipping) as Week 6's first task, before more
   modelling.
3. **The calibration gate**: keep failing on all rows until (2) is done, or gate on
   the turn-start decisions both players have in the meantime?
4. **Speed**: approve base Speed and types from the Showdown data, plus Tailwind /
   Trick Room interactions, as the next feature group. It is what EC-001 needs.
5. **Training on the full Reg M-A data** on your PC (`docs/RUNBOOK.md` section 14):
   the numbers here use 20% of the training sets.
