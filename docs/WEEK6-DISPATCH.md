# Week 6 — Dispatch Brief (M4 v2: an unbiased decision table, speed, full training)

**Status:** decisions taken by the PO on 30 Oct 2026 after the Week 5 report; work
started the same day.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report in prose.

## Decisions (PO, 30 Oct 2026)

1. **Speed is the next feature group.** Base Speed and types from the pinned
   Showdown data, combined with Tailwind and Trick Room.
2. **Reg M-B uses the pooled model**: trained on both formats with a format flag,
   judged on Reg M-B only. Every metric stays per format.
3. **Build our own decision table from the logs first**: every decision point, no
   skipping, so no row exists or not depending on what happens next (Week 5 report,
   surprise 2).
4. **The calibration gate stays as defined** (all decision rows of the validation
   split). It should pass once (3) removes the selection bias; if it does not, that
   is a finding about the model.
5. **Train Reg M-A on its full training set.**

## Tasks

### Task 1 — Decision table from the logs
- [ ] Decision points defined by the game's own structure, never by what happens
      after them: team preview; the start of every turn (both players); a forced
      replacement after the turn's residual (a player with a fainted active and a
      Pokemon left); a switch during the turn (after U-turn, Eject Button and so on)
- [ ] At each, the board as a stored state shows it (species, hit points, fainted,
      active, sheet order), from our own tracker of the log, plus the timers there
- [ ] Tests first; validated against the stored states wherever both exist (same
      hit points, fainted and active flags), with the agreement rate reported
- [ ] Label balance: per format, the label rate over all decision rows; the
      turn-start rows must be won exactly 50% of the time

### Task 2 — Speed features (group F)
- [ ] Base Speed (Mega form when holding its stone) of each side's active Pokemon,
      Choice Scarf ×1.5, Tailwind ×2, and who is faster with Trick Room reversing it
- [ ] The same for the bench and the unseen Pokemon (fastest still to come)
- [ ] Tests first, and a guard that only public information is read

### Task 3 — Rebuild the feature table on the decision table

### Task 4 — v2 models
- [ ] Reg M-A on its full training set; Reg M-B pooled (both formats, flag)
- [ ] Hyperparameters: the Week 5 grid winner in both formats (learning rate 0.05,
      31 leaves), fixed before any v2 result; rounds chosen on validation

### Task 5 — Evaluation
- [ ] Ablation adding F; gate on validation; the test split opened once for v2
      (logged; it will be the third opening in total); expert claims re-scored

### Task 6 — Runbook and report
