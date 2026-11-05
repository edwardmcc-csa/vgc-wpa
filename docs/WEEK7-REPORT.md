# Week 7 report: damage, stat changes and spreads (M4 v3)

30 October 2026. Brief: `docs/WEEK7-DISPATCH.md`. Commits `49e2ec0` (Task 1) to
`5da69df`, plus this report. All numbers are per format. Reg M-B numbers carry
their sample size; read them with it.

## The headline

Damage is the biggest single gain since the first model. On the **test split**
(the fourth opening, logged against `5da69df`):

| test split | decision points | sets | v3 | v2 (Week 6) | v0 | v3 - v0 (95% interval) |
|---|---|---|---|---|---|---|
| Reg M-A | 170,644 | 5,108 | **0.1874** | 0.1952 | 0.2091 | -0.0217 (-0.0232 to -0.0202) |
| Reg M-B (pooled) | 8,917 | 237 | **0.1905** | 0.1959 | 0.2130 | -0.0225 (-0.0305 to -0.0147) |

Both v3 and v2 were trained on the same 20% of Reg M-A's training sets and
scored on the same rows. **Reg M-A passes the gate on test**: every calibration
bin is within 0.013.

**Reg M-B does not.** Four bins are off by more than 0.05: it predicts 0.15
where 0.21 happened, and 0.85 where 0.78 happened. On validation the raw pooled
model missed by 0.051 in one bin, so it was recalibrated, as the gate says. That
correction was fitted on only 199 sets, and it overshot: the model became
overconfident on new games. Week 6's v2 had no recalibration and passed on test.
That is decision 1 below.

On validation, adding damage (group G) improves the paired difference in both
formats, with the whole interval below zero:

| validation | v3 | v3 without damage | what damage adds |
|---|---|---|---|
| Reg M-A (5,167 sets) | 0.1870 | 0.1941 | **-0.0071 (-0.0081 to -0.0062)** |
| Reg M-B, pooled (199 sets, before recalibration) | 0.1734 | 0.1846 | **-0.0112 (-0.0150 to -0.0074)** |

For scale: in Reg M-A, damage is worth more than three times what using every
training game was worth to v2 (below).

## Task 1: stat changes, status and items on the board

The board now carries:
- **stat stages:** from every boost line; reset on switching out, passed on by
  Baton Pass, kept through Mega Evolution;
- **status:** from status lines and the hit-point text;
- **items:** from the sheet, changed by `-enditem` and `-item`.

Checked on real logs (`docs/DECISION-TABLE.md`):
- the board still matches the stored states with 0 differences;
- no stage is ever pushed past ±6;
- every Intimidate that did not lower everyone has a reason in the log (638 of
  697 lowered everyone in Reg M-A, 36 of 49 in Reg M-B).

## Task 2: the Smogon damage calculator

`@smogon/calc` 0.12.0 is pinned in `calc/` and has the Champions rules. Against
Showdown's own damage code, on 1,299 cases from real team sheets with randomised
spreads, stages, field and crits: **all 16 rolls are the same in 1,290**. The other
9 are explained (`docs/DAMAGE-CALC.md`). There are 0 unexplained differences.

## Task 3: spread estimates

Each Pokemon starts from Smogon's 1500 statistics for its format and month,
grouped into up to 10 profiles (`docs/SPREADS.md` explains why profiles and not
raw spreads). It is then refined by the hits and move orders in the log before
each decision.

Predicting each event from the events before it only, refining helps:

| | starting spread fits | refined fits |
|---|---|---|
| Reg M-A hits | 69.0% | 73.6% |
| Reg M-B hits | 66.5% | 71.3% |
| Reg M-A move orders | 89.8% | 91.8% |

Reg M-B move orders tie at 89.2%, but the log chance still improves. So
refinement went into the features, as the brief required.

## Task 4: damage features and real Speed

Group G gives each side:
- its best damage against the opposing actives;
- the board total;
- knock-outs this turn and in two hits;
- the best spread move;
- the threat from the bench and from the unseen sheet Pokemon.

Group F now uses the calculator's final Speed for the estimated spread.
`docs/DAMAGE-FEATURES.md` has the definitions.

A real-data check: the more knock-outs the feature says are on the board, the
more happen that turn. In Reg M-A at least one opposing Pokemon fainted in 10% of
turns with none on offer, 29% with one and 47% with two. Reg M-B shows the same
shape (8%, 28%, 46%).

**Real Speed alone adds nothing measurable.** On validation it changes Reg M-A by
-0.0002 (-0.0008 to +0.0003) against base Speed. The gain comes from damage.

**Build time.** About 0.26 seconds per game per worker process. The 20% table
(about 35,000 games) took about 2.5 hours of computing, split across four
processes. The full table is estimated at 1.6 hours with 4 workers; this is not
measured on your computer.

## Week 6 carry-over: v2 on every training game

I ran this in the cloud workspace, so you did not need to. On validation:

| v2 | 20% sample | all training games |
|---|---|---|
| Reg M-A | 0.1943 | **0.1921** |
| Reg M-A without speed | 0.1964 | 0.1941 |
| Reg M-B (pooled) | 0.1863 | **0.1839** |
| Reg M-B without speed | 0.1873 | 0.1875 |

A control rerun of the 20% model on the cloud's newer library version gave
0.1943 again. So the gain is the data, not the library. With all the data, speed
also helps measurably in Reg M-B: -0.0036 (-0.0061 to -0.0009).

**Every full-data model and every v3 model stopped at the 600-round cap.** That
is decision 2.

## Expert claims

Full write-up: `docs/EXPERT-CLAIMS-RESULTS.md` (Week 7 section).

**EC-001 is still not supported.** v3 prefers the double knock-out in 97% of
positions. The claim's situation, written in damage terms (their pair is harmless,
their reserve can knock one of ours out), turns up once in about 9,000 validation
games.

**EC-002 is where damage shows.** Where the sacrifice brings in something that
hits harder, v3 agrees with the claim 58% of the time in Reg M-A and 53% in
Reg M-B. Without damage it agrees 36% and 43% of the time.

## What went wrong, and was caught

The first v3 build applied the 20% training sample to Reg M-B too. The pooled
model is meant to use all of Reg M-B. A row count caught it before any result was
read: 13,403 Reg M-B training rows instead of 67,150.

I fixed it test-first: the sample now applies to Reg M-A only. I rebuilt
Reg M-B, deleted the pooled model trained on the short table without using it,
and retrained.

## Process notes

- Tests came first throughout this week's code, except the one-line change of
  report labels.
- The full suite: 496 passed, 3 skipped. 15 test files cannot load on the
  development machine (bot libraries) and are unchanged. ruff and pyright are
  clean.
- Models trained in the cloud use a newer scikit-learn. I checked that they give
  identical predictions on your machine's version: the validation report was
  reproduced exactly there.
- The test split has now been opened 4 times, all logged in
  `models/test_openings.json`.

## Decisions for the product owner

1. **Reg M-B calibration.** Recalibrating on 199 validation sets overshot. Two
   options:
   - **(a)** Stop recalibrating Reg M-B; the raw model passed on test in Week 6.
   - **(b)** Recalibrate with a method that does not fit and judge on the same
     sets, such as cross-fitting.

   I recommend (a) for now, and (b) when there is more Reg M-B data. Choosing
   between them by looking at the test split would spoil it. So whichever you
   choose is judged at the next opening.
2. **Raise the round cap from 600 to 1,000?** Every full-data and v3 model hit it.
   Recommended. It is a one-line change in the fixed settings.
3. **v3 on every training game.** I can build the full table and train in the
   cloud workspace: about 3 hours of building there, then about an hour of
   training. Or you can run runbook Section 16 without `--train-sample` on your
   computer. I recommend the cloud.
4. **EC-001: rewrite it or set it aside.** I can pull the 104 positions where
   their reserve outspeeds us after a double knock-out for you to judge, if you
   want to refine the claim.
5. **Next milestone.** v3 is ready for decision-level win probability added (M5),
   scoring the choice actually made against the alternatives.

---

## Addendum, 4 November: v3 on every training game

The PO ran runbook Section 16, step 8, on his own computer: the full table (88,901
games), then training with the new cap of 1,000 rounds and no recalibration for
Reg M-B. On validation:

| | 20% sample, 600 rounds | every game, up to 1,000 rounds |
|---|---|---|
| Reg M-A, v3 | 0.1870 | **0.1839** |
| Reg M-A, without damage | 0.1941 | 0.1908 |
| Reg M-B (pooled), v3 | 0.1734 | **0.1703** |
| Reg M-B (pooled), without damage | 0.1846 | 0.1826 |

- **Damage adds the same as before:** -0.0069 (-0.0079 to -0.0060) in Reg M-A
  and -0.0122 (-0.0158 to -0.0082) in Reg M-B.
- **More data and more rounds both changed at once,** so their gains cannot be
  told apart. Together they are worth about -0.003 in each format.
- **The round cap no longer matters.** Three of the four models reached 1,000
  rounds, but their last 100 rounds improved validation by about 0.0001.

**Gate:** Reg M-A passes, with every bin within 0.017. **Reg M-B fails**: without
recalibration, the 0.2-0.3 and 0.7-0.8 bins are off by 0.063.

For each bin, observed minus predicted, with a 95% interval from resampling sets:

| bin | 0.0-0.1 | 0.1-0.2 | 0.2-0.3 | 0.3-0.4 | 0.4-0.5 | 0.5-0.6 | 0.6-0.7 | 0.7-0.8 | 0.8-0.9 | 0.9-1.0 |
|---|---|---|---|---|---|---|---|---|---|---|
| v3, every game | -0.036* | -0.037 | -0.063* | -0.034 | -0.016 | +0.014 | +0.027 | +0.063* | +0.028 | +0.034* |

\* the interval excludes zero.

Every bin below 0.5 is negative and every bin above is positive. On these 199
validation sets the pooled model is **underconfident**: games are more decided than
it says. v2 on every game shows the same pattern.

The same kind of model was well calibrated on Reg M-B's test split in Week 6. And
correcting it on these 199 sets overshot on test in Week 7. So it is probably part
model (Reg M-B is 5% of the pooled training data) and part these particular sets.

The test split was not opened for this model; it would be the fifth opening.
