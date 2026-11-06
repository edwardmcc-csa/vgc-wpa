# Week 9 — Dispatch Brief (start M5: the choices, the opponent's likely reply, what can happen)

**Status:** drafted 5 Nov 2026 from the PO's decisions on the Week 8 report. The PO
answered its two questions on 6 Nov (decisions 6 and 7); started 6 Nov.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

v4 says how likely each side is to win at every decision point. The product needs
the next step (M5): for each choice a player made, how much it gained or cost, and
how much of the swing was the dice. `docs/DEFINITIONS.md` §3–§8 is the contract.

The project cannot do that yet. It needs three things it does not have:

- **The choices on offer** at each decision point: every move, target, switch and
  Mega Evolution the player could have picked.
- **What the opponent was likely to do.** DEFINITIONS §7 judges a choice against
  the opponent's likely replies, not the one they happened to make. Otherwise a good
  read that got punished counts as a mistake.
- **What can happen** when both sides' choices play out, with every damage roll,
  critical hit, miss and Speed tie kept as its own outcome. This is the plan's M3,
  with its "damage roll trap" (plan §5): never average two rolls into one.

With those three, a choice's expected win probability is v4's win probability
averaged over everything that could happen. Comparing that across the choices on
offer gives the decision part of the swing, and the rest is the dice.

This week builds the three pieces and runs a first decision-versus-luck split on a
sample. Week 10 runs it on everything and adds the other decision points.

## Decisions (PO, 5 Nov 2026, on the Week 8 report)

1. **The test split for v4** is opened once, on the model trained on every training
   game, on the PO's computer (runbook Section 17, step 9, then `v2-final`). It is
   the fifth opening. The results go into this week's report.
2. **The gate allows for sample size.** In a format with fewer than 500 sets, a
   calibration bin fails only when its whole 95% interval lies beyond 0.05. Done
   before the test opening (`c4b1ff1`). Under this rule v4 passes on validation.
3. **Blank sheets keep team preview.** The blank run shows all twelve species from
   team preview, as a real closed-sheet game does (Task 0).
4. **v4 on every training game** runs on the PO's computer (decision 1).
5. **Next milestone: M5,** decision versus luck, on v4.

**On this brief (PO, 6 Nov 2026):**

6. **The decision is measured against the win probability before the turn,** so
   the parts add up exactly. "Cost against best" and "cost against average" are
   reported beside it (§4).
7. **The swing is split three ways:** your decision, their decision, the dice.

DEFINITIONS §3 needed changing to match. The PO approved the wording at the end of
this brief on 6 Nov, and DEFINITIONS is now at revision 8.

## Tasks

### Task 0 — Carried over from Week 8
- [ ] **Blank sheets with team preview** (decision 3). With `--blank`, the
      opponent's six species are known from team preview. Their
      items, abilities and moves stay hidden until revealed, and their natures and
      spreads stay hidden. Tests first. Rebuild the blank table, retrain one-sided,
      and report the loss against full sheets beside Week 8's.
- [x] **The PO's full-data v4 and the test opening:** the results are folded into
      this week's report, per format, against Week 7's test numbers. *Done 6 Nov:
      both formats pass on test (Week 8 report, addendum).*

### Task 1 — The choices on offer
- [ ] At each move-selection decision point, for each of the player's active
      Pokemon, list:
      - each move on its sheet it can use, with each legal target. This respects
        Choice lock, Fake Out after the first turn, and anything else group H
        already tracks;
      - Protect, with its chance of working;
      - Mega Evolution, where available;
      - a switch to each brought Pokemon on the bench.

      A choice is one option per active Pokemon, with impossible pairs removed
      (both switching to the same Pokemon, for example).
- [ ] **Real-data check per format:** every choice the logs show a player making is
      in the list. Anything else is listed and explained. A Pokemon that fainted or
      flinched before moving shows no choice, so it is counted separately.
- [ ] Report how many choices a typical decision point offers.
- [ ] Tests first.

### Task 2 — What can happen this turn (M3: the turn resolver)
- [ ] Given a board, both sides' choices and the spread estimates, list every
      possible next board with its chance. The chances add up to 1.
- [ ] **Order:** priority, then Speed, including Tailwind, Trick Room, paralysis
      and stat stages. A Speed tie is 50/50, and it is luck (§8).
- [ ] **Damage** from the Smogon calculator:
      - all 16 rolls and the critical-hit branch kept separate;
      - spread moves at reduced damage;
      - accuracy;
      - a Pokemon knocked out before it moves does not act.
- [ ] **Protect** and its chance of working; **Fake Out** flinch.
- [ ] **Field moves** start their timers from the durations table: Tailwind, Trick
      Room, screens, weather and terrain.
- [ ] **Common secondary effects as luck branches:**
      - Speed drops (Icy Wind, Electroweb);
      - Snarl;
      - Intimidate on switching in;
      - burn and paralysis chances;
      - flinch chances.

      Anything not modelled is listed. A turn that uses it is marked "partly
      modelled", never silently treated as fully understood.
- [ ] Identical next boards are merged. Different HP from different rolls are
      different boards.
- [ ] **The plan's M3 tests,** checked against the calculator run on its own:
      - a known knock-out range;
      - a 50/50 knock-out roll;
      - an accuracy check;
      - a critical-hit branch;
      - every list adds up to 1;
      - two different rolls that both leave the target standing give two
        different boards, never one averaged board.
- [ ] **Real-data check per format:** for real turns, the board that actually came
      next is among the resolver's outcomes: hit points within the roll range,
      the same knock-outs, the same order. Report the share of turns fully
      modelled, and the share where the real outcome is found.
- [ ] **Stop rule:** if fewer than 70% of Reg M-A turns are fully modelled, stop and
      report before Task 4.

### Task 3 — What the opponent was likely to do (§7)
- [ ] A model of the choice each Pokemon makes, learned from the training split,
      like the bring model. It uses the board and each option's own features:
      expected damage, knock-out chance, Protect, switching.
- [ ] **Test per format on validation:** it beats a uniform guess over the legal
      options (the mean log chance of the choice actually made).
- [ ] It uses nothing from later in the game. Cutting a game after a decision
      changes nothing.

### Task 4 — A choice's expected win probability
- [ ] For a decision point and one of our choices: v4's win probability of each
      possible next board, averaged with the opponent model's chances (Task 3) and
      the resolver's chances (Task 2).
- [ ] The opponent's least likely replies may be dropped to save time, keeping at
      least 95% of the chance. The report says how much was kept.
- [ ] **This is `WP_public`.** Spreads we cannot see are averaged over as hidden
      information. They are not luck.
- [ ] **Time per decision point is measured.** The report says whether the whole
      validation split fits in a night on the PO's computer.

### Task 5 — Decision versus luck, a first look (M5, part 1)
- [ ] On a fixed sample of validation games (300 Reg M-A sets, and all 199 Reg M-B
      sets), at each move-selection decision point, split the swing as the PO
      decides below. Report it with **cost against the best choice** and **cost
      against the average choice** (§4), always both.
- [ ] **The plan's M5 tests:**
      - the parts add up to the whole swing at every decision point, within 0.001;
      - a scripted turn where only a critical hit differs: the dice get it, and
        the decision part is about 0;
      - a scripted turn with an obviously losing switch: the decision part is
        strongly negative.
- [ ] **For the PO to judge:** the 10 biggest swings per format, each with its
      split and the replay link.

### Task 6 — How much does win probability wobble? (§10.2)
- [ ] DEFINITIONS §10.2 requires this before M7: if the model's own noise is above
      0.5 points, the report would show noise as insight. Training is
      deterministic, so the honest measure is to retrain v4 on three resamples of
      the training sets. Then measure how much win probability moves on the same
      validation positions, per format, against the 0.5-point threshold.

### Task 7 — Runbook and report
- [ ] Runbook section for this week's commands. A report in prose, with a
      surprises section.

## Out of scope this week
- **The other decision points** (§6): team preview, leads and forced switches.
  These are Week 10, with the full validation run.
- **The M7 report** (paste a replay, get its biggest swings).
- **Your own team's spreads** and re-scoring your games with other spreads.

## DEFINITIONS §3 as approved (PO, 6 Nov 2026)

> ## 3. The split: your decision, their decision, the dice
>
> Every `WPA` decomposes into exactly three components. All three are from the
> analysed player's side. Write:
> - `WP(before)` for the win probability at the decision point;
> - `E[WP | your choice]` for the expected `WP` after the turn, averaged over the
>   opponent's likely replies (§7) and every random outcome (§8);
> - `E[WP | your choice, their choice]` for the same, averaged over random outcomes
>   only.
>
> The three components are:
> - **Your decision** = `E[WP | your choice] − WP(before)`. *Did you choose well,
>   compared with what this position usually gives?* Over typical play it averages
>   to about zero.
> - **Their decision** = `E[WP | your choice, their choice] − E[WP | your choice]`.
>   *Did their actual reply do better or worse than their likely replies?* It is
>   negative when they read you well.
> - **The dice** = `WP(after) − E[WP | your choice, their choice]`. *Did the random
>   outcomes in §8 cooperate?*
>
> **Conservation:** your decision + their decision + the dice = `WPA`, at every
> decision point, in every game, with no exceptions. Tolerance ±0.001 for floating
> point only. A conservation failure is a P1 bug, not a rounding note.

And §4's first line becomes: "Beside the split in §3 we report two more numbers,
always both, never one alone." The rest of §4 is unchanged. These two numbers are
not part of the split, and they do not need to add up.
