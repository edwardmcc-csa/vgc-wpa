# Week 10 — Dispatch Brief (M5 part 2: make the biggest swings right, average the models, add forced switches)

**Status:** drafted 7 Nov 2026 from the PO's decisions on the Week 9 report and
the full-sample run of 7 Nov. Waiting for the PO's answers to the two questions at
the end.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

Week 9 built decision versus luck and ran it on the brief's whole sample: 526 Reg
M-A games and 366 Reg M-B games. The split adds up everywhere. But the turns a
report would lead with, the biggest swings, are mostly not right yet:

- **Perish Song** is Reg M-A's first, second and tenth biggest swing. Both of one
  side's Pokemon reached the end of their count and fainted. That was certain, but
  the resolver does not count Perish Song down, so the dice took up to +99 points.
  Those turns were not even marked "partly modelled".
- **Last Respects and Rage Fist** are four more of the top 20. Their power grows
  with fainted allies and hits taken, which the damage calculator is not told.
- **Of the turns with a swing over 40 points, only 39% in Reg M-A (59% in Reg M-B)
  are fully understood.** The rest involve a gap like these, or the board that
  happened is not among the resolver's. The switch-in after U-turn or Parting Shot
  is the most common reason a board is missed.
- **The model's own noise is about 3 points** (Week 9, Task 6). DEFINITIONS
  revision 9 answers it with an average of 5 to 10 models.
- **Each Pokemon gets one spread**, its likeliest. Where the real Pokemon is
  bulkier, the miss lands in the dice.

The split also stops at the end of each turn. When a Pokemon faints, the choice of
replacement is a decision of its own, not yet scored. So a game's swings do not
yet add up to its result.

This week fixes the top of the list first, then the model's noise, then adds
forced switches so that a game's swings add up from turn 1 to the end.

## Decisions (PO, 6 Nov 2026, on the Week 9 report)

1. **Wobble: both.** Win probability is the average of 5 to 10 models trained on
   resamples of the training sets, and the reporting threshold is 3 points.
   DEFINITIONS §10.2 is now revision 9 (approved and committed 6 Nov).
2. **The opponent model: sharper now.** "Your decision" could not be brought to an
   average of zero. Sharpening flattens at about +2 points. **The PO chose
   sharpness 4.** The stronger opponent model (weighing each reply by how good it
   is for them) comes later; not this week.
3. **Spreads: yes.** Average over each Pokemon's 2 or 3 likeliest spreads, after
   measuring what it costs.
4. **The full sample on the PO's computer:** done 7 Nov (Week 9 report, second
   addendum).
5. **The replies method stays:** the likeliest 6 replies exactly, the rest drawn
   in proportion to their chances.

## Tasks

### Task 0 — Say "partly modelled" everywhere it applies
- [ ] **A Perish Song count** on any active Pokemon at the start of a turn marks
      the turn "partly modelled" until Task 1 models it.
- [ ] **The summary shows each big swing's reasons** next to it, such as "partly
      modelled: Perish Song", so a reader can tell a modelling gap from luck.
- [ ] **The summary reports the Week 9 table** of turns with a swing over 40
      points, by cause, per format, so each week's progress can be compared.
- [ ] Tests first.

### Task 1 — Perish Song
- [ ] The resolver reads each Pokemon's Perish Song count from the turn's timers.
      At the end of the turn it counts down, and a Pokemon reaching 0 faints.
- [ ] **Perish Song used this turn** starts the count on every active Pokemon it
      affects. Soundproof is immune.
- [ ] **Switching out clears the count.** So does fainting first.
- [ ] **Order at the end of the turn:** Perish Song comes after weather and other
      residual damage. If both sides lose their last Pokemon in the same turn,
      the result follows Showdown's rule, and a test shows which.
- [ ] **Tests first,** including both of a side's Pokemon fainting at 0, and the
      win that follows. Check them against Week 9's three top Reg M-A turns:
      those boards must now be among the resolver's.

### Task 2 — Damage that depends on the game so far
- [ ] **Last Respects:** the calculator is told how many of the user's side have
      fainted so far.
- [ ] **Rage Fist:** the calculator is told how many times the user has been hit.
- [ ] **Supreme Overlord** (Kingambit's ability) also counts fainted allies.
      Check whether the feature table and the resolver already pass it. If not,
      pass it in both, and say what it changes in the feature table.
- [ ] Counts come from the log up to the decision point only. Cutting a game after
      a decision changes nothing.
- [ ] **Tests first,** checked against the calculator run on its own. Once a move
      is handled, its "partly modelled" mark from Week 9 goes.

### Task 3 — The switch-in after U-turn, Volt Switch, Flip Turn and Parting Shot
- [ ] The resolver plays the pivot through: the Pokemon that comes in, then the
      rest of the turn with it on the field (Intimidate on entry included).
- [ ] **Which Pokemon comes in is part of the pivoting player's choice.** For the
      choice taken it is the one the log shows. For likely replies and for
      alternatives it is weighted by the opponent model's chances for switching
      to each Pokemon.
- [ ] Eject Button and Eject Pack, if cheap to add the same way. If not, they stay
      "partly modelled".
- [ ] **Tests first.** Rerun the Week 9 resolver check per format and report the
      share of turns fully modelled and the share where the board is found,
      beside Week 9's.

### Task 4 — Spreads (decision 3)
- [ ] **Measure first.** On a sample of turns, the time per turn with each
      Pokemon's 2 or 3 likeliest spreads instead of 1.
- [ ] **Hidden spreads are averaged as hidden information, not luck**
      (`WP_public`, as Week 9's brief asked). Each combination of spreads is
      weighted by its chance, and the board is valued with the spreads it assumes.
- [ ] Report the share of boards found and the size of the dice beside Week 9's.
- [ ] **Stop rule:** if the brief's sample would no longer fit in a night on the
      PO's computer, report the cost and the options before Task 7 runs.

### Task 5 — The averaged model (decision 1, DEFINITIONS §10.2 revision 9)
- [ ] **10 models per format** (Reg M-A, and the pooled model for Reg M-B), each
      trained on the full table with v4's settings, on a resample of the training
      sets: whole sets drawn with replacement, as many as there are. They run on
      the PO's computer.
- [ ] **WP is the average of the 10.**
- [ ] **The Reg M-B correction for the average** is fitted on out-of-bag
      predictions. Each training set is predicted only by the models whose
      resample left it out. No extra training is needed.
- [ ] **The averaged model's own noise is measured directly,** as revision 9
      requires. Compare the average of models 1 to 5 with the average of 6 to 10
      on the same validation positions, then scale to the average of all 10. It
      must be under 3 points. If not, raise a blocker, not a quiet change.
- [ ] **Gate on validation:** the averaged model passes, per format, and its score
      is reported beside v4's (paired). Averaging can soften predictions.
- [ ] The test split is not opened this week.
- [ ] The first model is timed. The report says how many nights the rest took.

### Task 6 — Forced switches (DEFINITIONS §6)
- [ ] **The decision:** after a Pokemon faints, which Pokemon to send in. When both
      sides replace at once, each side's choice is made without seeing the
      other's, so it is split the same way as a turn.
- [ ] **A model of which Pokemon is sent in,** learned from the training split.
      **The test per format on validation:** it beats a uniform guess over the
      Pokemon that could come in.
- [ ] **The split:** your decision and their decision as in §3. The dice are
      whatever is random on entry. Their decision is 0 when only one side
      replaces.
- [ ] **A game's swings chain:** each decision point's WP(after) is the next one's
      WP(before), within 0.001.
- [ ] **A game's swings add up** to its result minus WP at turn 1's start (§2),
      within 0.001, for every game with no forfeit or timer.
- [ ] Tests first.

### Task 7 — The brief's sample again (the PO's computer)
- [ ] The same 300 Reg M-A sets and 199 Reg M-B sets, with Tasks 0 to 6, the
      averaged model and sharpness 4.
- [ ] **Report beside Week 9's:**
      - the three parts and both costs, per format;
      - the share of decision points with a part of 3 points or more (the new
        threshold);
      - the turns over 40 points by cause.
- [ ] **For the PO to judge:** the 10 biggest swings per format, now with their
      reasons, and the 10 biggest forced-switch decisions.
- [ ] **Time:** the slowest 5% of turns took 40% of Week 9's run (the slowest 1%,
      18%). Make them faster, or give each turn a time budget that coarsens the
      grid rather than dropping anything. Report the total, and whether the whole
      validation split now fits in a weekend.

### Task 8 — Runbook and report
- [ ] Runbook section for this week's commands. A report in prose, with a
      surprises section.

## Out of scope this week
- **Team preview and leads** (the rest of §6): Week 11.
- **The stronger opponent model** (decision 2's second step).
- **The M7 report** (paste a replay, get its biggest swings).
- **Your own team's spreads** and re-scoring your games with other spreads.
- **The whole validation split** (about three days at Week 9's speed). Task 7
  says whether it fits after this week's changes.

## For the PO before starting
1. **Forced switches this week, team preview and leads in Week 11?** Forced
   switches make a game's swings add up from turn 1 to the end, which Week 9
   could not do. Team preview and leads are a larger piece, built on the bring
   model. I recommend this order.
2. **20 trainings on your computer for the averaged model** (Task 5: 10 per
   format, on the full table). Ten per format lets the noise be measured
   directly, as revision 9 asks. The alternative is 5 per format, in about half
   the time: the noise would then be estimated from Week 9's single-model
   measure divided by √5, not measured. I recommend 10. The first model's time
   will say how many nights it takes.
