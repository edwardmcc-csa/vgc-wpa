# Week 8 report: who was brought, Bo3 memory, this turn, the whole board (M4b, v4)

5 November 2026. Brief: `docs/WEEK8-DISPATCH.md`. Commits `a5bb567` to `c8364e9`,
plus this report. All numbers are per format and on the **validation split**; the
test split was not opened (decision 1 below). Reg M-B numbers carry their sample
size; read them with it.

## The headline

v4 is better than v3 in both formats, and the paired intervals are below zero:

| validation | sets | v4 | v3 | v0 | v4 - v3 (95% interval) |
|---|---|---|---|---|---|
| Reg M-A | 5,167 | **0.1851** | 0.1870 | 0.2099 | -0.0020 (-0.0026 to -0.0014) |
| Reg M-B (pooled) | 199 | **0.1678** | 0.1734 | 0.2033 | -0.0056 (-0.0087 to -0.0024) |

Both were trained on the same 20% of Reg M-A's training sets and scored on the
same rows. In Reg M-A the gain is under a third of what damage added in Week 7
(-0.0071).

**Gate:** Reg M-A passes, with every calibration bin within 0.013. **Reg M-B fails
one bin**: 0.6-0.7, where it predicts 0.646 and 0.706 happened. That is with the
new correction (Task 6), which turned out to be almost nothing: a temperature of
0.980. The section on Reg M-B below explains why I think these 199 sets, not the
model, are the problem.

**Blank sheets (M4b):** the model now runs without the opponent's sheet and gives a
valid, less confident `WP_public`. It passes the calibration gate in both formats.
It loses 0.0036 in Reg M-A and 0.0104 in Reg M-B against full sheets. Getting there
took a fix to the model itself (Task 5).

## What each addition is worth

v4 against the same model without each addition (validation, paired). A positive
number means the model without it is worse:

| without | Reg M-A | Reg M-B (pooled) |
|---|---|---|
| H, I and J (= v3's groups on the v4 table) | +0.0014 (+0.0009 to +0.0020) | +0.0047 (+0.0020 to +0.0075) |
| J, the whole board | **+0.0011 (+0.0007 to +0.0016)** | not trained |
| H, this turn's options | +0.0003 (+0.0000 to +0.0006) | not trained |
| I, the likely back | -0.0001 (-0.0003 to +0.0002) | not trained |
| everything new (v3 itself) | +0.0020 (+0.0014 to +0.0026) | +0.0056 (+0.0024 to +0.0087) |

- **The whole board (J) is most of the gain.** Knowing who can knock out whom
  across both teams, not just between the actives, is what v3 was missing.
- **This turn's options (H)** add a little; the interval just touches zero.
- **The likely back (I) adds nothing measurable on its own.** Its information
  also reaches the model through J, which counts each unseen Pokemon by the
  chance it was brought. With J present, I adds nothing here.
- **The rest (about +0.0006 in Reg M-A, the gap between the first and last
  rows)** comes from the table itself: Bo3 memory's carried spreads, group G
  using only a Choice-locked Pokemon's locked move, and the round cap of 1,000.
- Only the without-H-I-J model was trained for Reg M-B. Single-group models for
  Reg M-B would each cost a pooled training run, and with 199 validation sets
  their intervals would not separate.

## Task 1: which four they brought

`wpa/bring.py`; details in `docs/BRING.md`. Each sheet Pokemon gets odds from a
small logistic regression on how often its species is brought, its place on the
sheet, and (in games 2 and 3) whether the same player brought it last game. A set
of four's chance is the product of its members' odds, over the sets that contain
everything seen so far.

**The plan's test** (validation, mean log chance given to the four actually
brought; the uniform guess over 15 sets is -2.708):

| | sides | at team preview | most likely set right | after the leads (uniform -1.792) | games 2-3: most likely set right |
|---|---|---|---|---|---|
| Reg M-A | 14,169 | **-2.471** | 24% (uniform 7%) | -1.627 | 41% |
| Reg M-B | 593 | **-2.390** | 28% | -1.562 | 40% |

It beats the uniform guess in both formats. Brought-last-game is the strongest
signal (+1.99 on the log-odds scale).

**One change from the brief.** The brief asked for groups E, F and G to be weighted
by these odds. I put the weighting in new groups instead: I (the likely back) and
J (the whole board, counting each unseen Pokemon by its chance). E, F and G are as
in v3. That keeps v3's groups comparable, and the ablation can price the
weighting on its own.

## Task 2: Bo3 memory

The logs are now sharded by set (`logs_sets/`), so a set's games are built
together and in order. In games 2 and 3, each Pokemon's spread estimate starts
where the previous game left it, and what each player brought feeds Task 1.
Nothing from a later game is used.

**The plan's test: is belief narrower at the start of game 2?** Mean entropy of
the spread estimate at the start of a later game:

| | Pokemon carried | fresh from the statistics | carried from the last game | narrower by |
|---|---|---|---|---|
| Reg M-A | 148,854 | 1.432 | 1.201 | 16.2% |
| Reg M-B | 22,884 | 0.925 | 0.764 | 17.5% |

Yes, in both formats, by about a sixth.

## Task 3: what each side can do this turn (group H)

For each active Pokemon: Fake Out still works, locked by a Choice item (and group
G then uses only the locked move), and whether its next Protect is the risky one.
For each side: Mega Evolution still available, or already used.

**The real-data check** (a quarter of all games: 21,208 Reg M-A, 1,027 Reg M-B):
- **Fake Out:** of 235 used after the Pokemon had already moved, 233 failed, as
  they should.
- **Choice lock:** locked Pokemon used the locked move 12,450 times, Struggle 79
  times (the locked move disabled), and another move 8 times. All 8 are Trick
  swaps and Magic Room. The Trick cases showed a real gap: a Choice item received
  by Trick must lock from the Pokemon's next move, not its last one. Fixed, with a
  test (`tests/test_board_actions.py`).

## Task 4: the whole board (group J)

Every Pokemon still standing on one side is matched against every one on the
other, with each unseen Pokemon counted by its chance of being brought. Per side:
how many of theirs we knock out in one hit, in one hit while moving first, in two
hits, and how many pairs move first and knock out.

**Build time:** about the same as v3, roughly 0.26 seconds per game per process.
The calculator's cache answers most of the new requests. The full table builds on
your computer in about the same time as v3's did.

## Task 5: blank sheets

`docs/BLANK-SHEETS.md` has the details. With `--blank`, at every decision the
opponent's species are known only once they have appeared, and their items,
abilities and moves only as revealed. Their sheet order and natures are hidden.
Spreads come from the statistics alone. Our own sheet stays whole, since a player
knows their own team.

**The first run was wrong, and the gate caught it.** Every model so far scores a
row from both sides and averages: p = (f(row) + 1 - f(mirrored row)) / 2. That
assumes both sides know the same kind of thing. With only their sheet blanked,
the mirrored row (their sheet whole, ours blanked) looks like nothing in training.
The model over-predicted the side with the sheet: a mean of 0.529 where 0.488
happened in Reg M-A, with three bins failing, and five bins failing in Reg M-B.
Recalibrating did not fix it.

**The fix: one-sided models** (`v2-train --one-sided`, test-first). They score
each row as it is. Training has rows from both players' points of view, so the
model learns each side's chance from what that side knows.

| validation | full sheets (v4) | opponent's sheet blanked (`WP_public`) | lost (95% interval) | v0 |
|---|---|---|---|---|
| Reg M-A | 0.1851 | **0.1886** | +0.0036 (+0.0028 to +0.0043) | 0.2099 |
| Reg M-B (pooled) | 0.1678 | **0.1781** | +0.0104 (+0.0066 to +0.0136) | 0.2033 |

- **Valid:** both formats pass the gate. Reg M-A's bins are all within 0.013.
- **Less confident, as the plan expects:** it keeps 85% of v4's gain over v0 in
  Reg M-A and 71% in Reg M-B.
- No gate was set for this run, so the Reg M-B figure has no cross-fitted
  correction.

**Both sheets blanked** (`--blank-both`) is also there, as someone watching a
replay with neither sheet would see it. Both sides then know the same kind of
thing, so the usual symmetric model works. It passes the gate and loses more:
+0.0055 in Reg M-A and +0.0138 in Reg M-B. It answers a different question from
the player's, so it is not the product number.

**Stricter than a real game.** In a real game without open sheets, team preview
still shows all six species of both teams. The brief hides species until they
appear. That is decision 3.

## Task 6: Reg M-B's correction

As decided (decision 6 of the brief), the pooled model was trained five more
times on Reg M-B's 1,824 training sets, each time leaving out a fifth. One
temperature was fitted to the out-of-fold predictions. It came out at **0.980**:
the model is almost exactly calibrated on sets it has not seen, as long as those
sets come from training.

On the 199 validation sets it is not. Observed minus predicted, by bin, with 95%
intervals from resampling sets:

| bin | 0.0-0.1 | 0.1-0.2 | 0.2-0.3 | 0.3-0.4 | 0.4-0.5 | 0.5-0.6 | 0.6-0.7 | 0.7-0.8 | 0.8-0.9 | 0.9-1.0 |
|---|---|---|---|---|---|---|---|---|---|---|
| v4 | -0.023* | -0.019 | -0.044 | -0.048* | -0.016 | +0.009 | **+0.060*** | +0.045 | +0.016 | +0.020 |

\* the interval excludes zero. The failing bin's interval is +0.009 to +0.104.

The pattern is the one v3 showed on these sets: every bin below 0.5 negative,
every bin above positive. So:
- on 1,824 training sets, predicted out of fold, the model needs no correction;
- on these 199 sets it looks underconfident, in the same pattern for v3 and v4;
- in Week 6 the same kind of model passed on Reg M-B's 237 test sets.

The likeliest reading is that these 199 validation sets are unusual, and a gate
that fails on any bin past 0.05 is too strict for 199 sets. That is decision 2.

## Expert claims

Re-scored on the same 64-shard scan, now with groups H, I and J. "v3 groups" is
the model trained on the v4 table without H, I and J.

| Reg M-A | v0 | v1 | v3 groups | v4 |
|---|---|---|---|---|
| EC-001, all (138) | 0% | 0% | 4% | **12%** |
| EC-001, their reserve acts first after a double KO (104) | 0% | 0% | 5% | **14%** |
| EC-001, premise in damage terms (1) | 0% | 0% | 100% | 0% |
| EC-002, all (768) | 100% | 22% | 48% | 49% |
| EC-002, the sacrifice gains speed (204) | 100% | 24% | 62% | 61% |
| EC-002, the sacrifice hits harder (312) | 100% | 21% | 59% | 59% |

| Reg M-B | v0 | v1 | v3 groups | v4 |
|---|---|---|---|---|
| EC-001, all (2) | 0% | 0% | 0% | 0% |
| EC-002, all (399) | 100% | 16% | 46% | 47% |
| EC-002, the sacrifice gains speed (76) | 100% | 7% | 67% | 66% |
| EC-002, the sacrifice hits harder (159) | 100% | 25% | 61% | 60% |

- **EC-001 moves.** With the whole board and the likely back, v4 sides with the
  claim (one knock-out or a stall, rather than the double knock-out) in 12% of
  Reg M-A positions, up from 4%, and 14% where their reserve acts first. It still
  prefers the double knock-out on average (0.78, against 0.69 for one knock-out
  and 0.56 for a stall). That fits your decision: the claim holds in particular
  positions, not in general. Reg M-B has only two positions.
- **EC-002 is unchanged.** The damage groups already carried it in Week 7.

## What went wrong, and was caught

- **The first blank-sheet run was miscalibrated** (Task 5): the symmetric model
  cannot handle sides that know different things. The gate caught it, and
  one-sided models fixed it.
- **The report crashed on the new groups.** The report names each added group,
  and H, I and J had no names. Fixed test-first; the label of the comparison line
  is plainer too.
- **A figure in `docs/BRING.md` came from a partial build.** It said 161,106
  Pokemon carried into a later game; the full build carried 171,738. Corrected,
  and split by format above.
- **One comparison file was overwritten** by a later comparison run. All
  comparisons now run in one call, and the file holds them all.
- **Git left lock files on your computer** while deletion was off. With the
  deletion permission you granted I removed them; nothing else was touched.

## Process notes

- Tests came first for most of this week's code, including the one-sided models
  and the both-blanked mode. **Two exceptions:** the tests for groups I and J were
  written after the code, and the build test for the both-blanked mode was added
  after its wiring. All of them pass, and they check the behaviour the brief
  describes.
- The full suite: 537 passed, 3 skipped. 15 test files cannot load on the
  development machine (bot libraries) and are unchanged. ruff is clean. pyright is
  clean apart from imports of those same bot libraries.
- Models trained in the cloud workspace (newer scikit-learn) give identical
  predictions on your machine's version.
- The test split has been opened 4 times, all logged in
  `models/test_openings.json`. Not opened this week.

## Decisions for the product owner

1. **The test split for v4 (the fifth opening).** Options:
   - **(a)** Open it now, on the 20% models here.
   - **(b)** First run v4 on every training game on your computer (runbook
     Section 17, step 9), then open it once on that model.

   I recommend (b): spend the opening on the model you would use. It also judges
   the Reg M-B correction on sets it has never seen.
2. **Should the gate allow for sample size?** Today a bin fails if it is more than
   0.05 off, whatever the sample. For a format marked SMALL SAMPLE, it could fail
   only when the whole 95% interval lies beyond 0.05. Under that rule v4 passes
   (the failing bin's interval starts at +0.009). Reg M-A, with 5,167 sets, is
   unaffected. I recommend it, decided now and before any test opening.
3. **Blank sheets with team preview.** Should the blank run keep the twelve
   species shown at team preview, as a real closed-sheet game does? It is a small
   change, and it would make `WP_public` match what a player actually sees. I
   recommend it.
4. **v4 on every training game** on your computer: runbook Section 17, step 9.
   Building takes about as long as v3's full table.
5. **Next milestone: M5, decision versus luck,** on v4: scoring the choice actually
   made against the alternatives.

---

## Addendum, 6 November: v4 on every training game, and the test split

The PO ran runbook Section 17, step 9, on his own computer:
- the full table, 88,901 games in about 2½ hours at 4 workers;
- training, with the Reg M-B correction cross-fitted on 1,824 training sets
  (temperature 0.957, which leaves the out-of-fold score unchanged);
- then the fifth test opening, logged against `ea43fcb`.

Before the opening, the gate was changed to allow for sample size, as the PO
decided (`c4b1ff1`).

**Validation:**

| | v4, every game | v3, every game |
|---|---|---|
| Reg M-A | **0.1816** | 0.1839 |
| Reg M-B (pooled) | **0.1663** | 0.1703 |

The gate passes in both formats. Reg M-B has two bins more than 0.05 off, with
the same lean these 199 sets always show. Under the new rule both are reported,
not failed, because their intervals reach back within 0.05.

**Test split (the fifth opening):**

| test split | decision points | sets | v4, every game | v3 (Week 7, 20% sample) | v0 | v4 - v0 (95% interval) |
|---|---|---|---|---|---|---|
| Reg M-A | 170,644 | 5,108 | **0.1826** | 0.1874 | 0.2091 | -0.0265 (-0.0281 to -0.0249) |
| Reg M-B (pooled) | 8,917 | 237 | **0.1810** | 0.1905 | 0.2130 | -0.0320 (-0.0388 to -0.0252) |

- **Both formats pass on test.** Every calibration bin is within 0.013 in Reg M-A
  and within 0.031 in Reg M-B. Reg M-B would pass even under the old strict rule.
  In Week 7 it failed four bins on test.
- **The Reg M-B question is settled.** The correction learned from the training
  sets is almost none. On 237 sets the model has never seen, it is well
  calibrated. So the lean seen at every validation run belongs to those 199
  validation sets, not to the model.
- **Validation and test agree in Reg M-A** (0.1816 and 0.1826). The Reg M-B test
  sets are harder for every model, v0 included. Measured against v0, the gain is
  similar in both: -0.0370 on validation, -0.0320 on test.
- **Against Week 7's test numbers** the improvement mixes two changes: v4's new
  features and training on every game. The Week 8 ablation priced the features on
  their own. This opening is the check that the whole thing holds up on new
  games.

The test split has now been opened 5 times, all logged in
`models/test_openings.json`.
