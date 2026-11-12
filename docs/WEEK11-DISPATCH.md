# Week 11 — Dispatch Brief (M5 part 3: your choice and the position, team preview and leads)

**Status:** drafted 10 Nov 2026 from the PO's decisions on the Week 10 report.
The PO approved DEFINITIONS revision 10 and started it on 10 Nov.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

Week 10 made the biggest swings right and made every game add up from turn 1
to its result. It also showed that **"your decision" is two things.** One is the
player's choice against what players typically choose in that position. The
other, "the position", is the gap between the model's win probability before
the turn and what the turn held whatever anyone chose. On the brief's sample the
position is as big as the choice: typically about 11 points each in a turn. In
a forced switch the position is twice the choice. A forced switch with one
Pokemon left still showed a "decision" of about 9 points.

The PO chose to split them (decision 1 below). This week does that, then adds
the last decision points of DEFINITIONS §6 that are not scored yet: **team
preview and leads**. Then it fixes the causes left at the top of the list: a
hidden Speed spread (Reg M-A's biggest swing), charging moves, confusion, Encore
and sleep.

## Decisions (PO, 10 Nov 2026, on the Week 10 report)

1. **Split "your decision": (a).** "Your choice" (against the typical choice) is
   the decision credited to the player. "The position" is shown beside it,
   credited to no one. The parts still add up to the swing. This is DEFINITIONS
   revision 10, drafted below for approval.
2. **Week 11 in this order:** the split, team preview and leads, Speed order from
   the hidden spreads, then charging moves, confusion, Encore and sleep. The
   stronger opponent model and the full spread method wait for Week 12.

## DEFINITIONS §3 and §4, revision 10 (approved 10 Nov 2026, committed)

> ## 3. The split: your choice, the position, their decision, the dice
>
> Every `WPA` decomposes into exactly four components. All four are from the
> analysed player's side. Write:
>
> - `WP(before)` for the win probability at the decision point;
> - `E[WP | a typical choice]` for the expected `WP` after the decision when your
>   choice is drawn from what players typically choose in this position (the same
>   choice model §7 uses for the opponent), averaged over the opponent's likely
>   replies (§7) and every random outcome (§8);
> - `E[WP | your choice]` for the same with your actual choice;
> - `E[WP | your choice, their choice]` for the same, averaged over random
>   outcomes only.
>
> The four components are:
>
> - **Your choice** = `E[WP | your choice] − E[WP | a typical choice]`. *Did you
>   choose better than players typically do here?* This is the decision credited
>   to you. With only one option it is exactly 0.
> - **The position** = `E[WP | a typical choice] − WP(before)`. *What did this
>   decision point hold, whatever you chose?* It is credited to no one. It carries
>   what playing the turn out reveals that the single `WP` estimate did not: a
>   game that ends whatever anyone chooses, a Pokemon about to come in.
> - **Their decision** = `E[WP | your choice, their choice] − E[WP | your choice]`.
>   *Did their actual reply do better or worse than their likely replies?* It is
>   negative when they read you well.
> - **The dice** = `WP(after) − E[WP | your choice, their choice]`. *Did the random
>   outcomes in §8 cooperate?*
>
> **Conservation:** your choice + the position + their decision + the dice =
> `WPA`, at every decision point, in every game, with no exceptions. Tolerance
> ±0.001 for floating point only. A conservation failure is a P1 bug, not a
> rounding note.
>
> Rationale (rev 10, PO, 10 Nov 2026): revision 8 called your choice plus the
> position "your decision". On the Week 10 sample the position was typically
> about 11 points a turn, as big as the choice itself, so "your decision"
> credited players with what no choice of theirs moved.
>
> ## 4. Baseline for Decision WPA
>
> Beside the split in §3 we report the choice against two baselines, always both,
> never one alone:
>
> - **Cost vs. best** — against the best of the player's likely choices. This is
>   the coaching number: "that switch cost you 14%."
> - **Cost vs. typical** — against the typical choice: this is **your choice** in
>   §3. It is the fairness number, and it stops the tool telling a competent
>   player they misplayed every single turn because they weren't a solver.
>
> Rationale: "vs. best" alone is demoralising and makes good players look bad.
> "Vs. typical" alone hides real errors. Shipping both is a product requirement,
> not an implementation detail.

(Today's "cost vs average" is an unweighted mean of the player's 10 likeliest
choices. Revision 10 weights each choice by how often players make it, the same
way the opponent's likely replies are weighted.)

## Tasks

### Task 0 — Your choice and the position (DEFINITIONS revision 10, once approved)
- [x] **The typical choice:** the player's own likely choices (the likeliest 6
      exactly, the rest drawn in proportion, as for the opponent's replies) against
      the opponent's likely replies, at every decision point: turns and forced
      switches, both players.
- [x] **Records and summary:** your choice, the position, their decision and the
      dice, adding up to the swing. "Your decision" (their sum) stays in the
      records for comparison with Weeks 9 and 10. The summary leads with your
      choice and shows the position beside it.
- [x] **Cost vs best** stays in every third game; cost vs typical is your choice,
      so it is everywhere.
- [x] **Measure first:** the time per turn on a sample, before Task 4 runs.
      Week 10's estimate is 2 to 3 times longer.
- [x] **Tests first,** including: a forced switch with one Pokemon gives your
      choice 0; a turn where every choice is worth the same gives your choice 0;
      the turn where Perish Song ends the game puts the swing in the position.

### Task 1 — Team preview and leads (DEFINITIONS §6)
- [x] *(the leads; the back two are not scored: the model cannot see them)*
      **The decision:** which four to bring and which two lead. Showdown takes
      both in one choice at team preview, so it is one decision point for each
      player, made without seeing the other's (§7).
- [x] **A model of the choice,** learned from the training split: the bring model
      (Week 8) extended with the leads. **The test per format on validation:** it
      beats a uniform guess on what the log shows (the leads always; the four
      where all four appear).
- [x] **The split** as in §3: each pair of choices is valued at turn 1's start,
      from what each player knew at team preview. A player knows their own back
      two; the opponent does not (§5). No dice at team preview, except the
      model's own difference between a board and the next row.
- [x] **Games 2 and 3 of a set** use what earlier games revealed (§11.3).
- [x] **A game's swings add up from team preview to its result** (§2), within
      0.001, for every game with no forfeit or timer.
- [x] Tests first.

### Task 2 — Speed order from the hidden spreads
- [x] *(opt-in: `--speed-beliefs`; 2.6 times slower, no change measured)*
      **Where two Pokemon's order depends on Speed spreads** that the evidence
      does not settle, the resolver branches on the order, with each order's
      chance from the spread beliefs (refined from the game so far), instead of
      taking the likeliest spread's order. Items and abilities on the sheet are
      known and stay as they are.
- [x] **Measure:** the time it costs, the share of boards found, and how much of
      the dice it explains on Week 10's biggest swings (Reg M-A's first among
      them).
- [x] Tests first.

### Task 3 — The causes left among the biggest swings
- [x] **Charging moves** (two-turn moves, and Power Herb).
- [x] **Confusion:** the chance of hitting itself, and how long it lasts.
- [x] **Encore:** the locked move limits the options and their chances.
- [x] **Sleep:** the turns until waking up.
- [x] Each is modelled in the resolver or, where it is not cheap, stays marked
      "partly modelled". **Tests first**, one per mechanic at least. Rerun the
      resolver check per format beside Week 10's.

### Task 4 — The brief's sample again (the PO's computer)
- [x] The same 300 Reg M-A sets and 199 Reg M-B sets, with Tasks 0 to 3, the
      averaged model and sharpness 4. *(run of 11 Nov, code at `9e9ef90`)*
- [x] **Report beside Week 10's:** the four parts per format, the share of
      decision points with a part of 3 points or more, and the turns over 40
      points by cause.
- [x] **For the PO to judge:** the 10 biggest swings per format with your choice
      and the position, the 10 biggest choices (by your choice), and the 10
      biggest team-preview decisions.
- [x] *(a long day: 53 core-hours, 7 of them a stall)* **Time:** expected to need a weekend. Task 0's measurement says how long
      before it starts.

### Task 5 — Runbook and report
- [x] Runbook section for this week's commands. A report in prose, with a
      surprises section. *(Section 20; `docs/WEEK11-REPORT.md`)*

## Out of scope this week
- **The stronger opponent model** (Week 10 decision 2's second step): Week 12.
- **The full spread method** (decision 9 of Week 10): Week 12.
- **The M7 report** (paste a replay, get its biggest swings).
- **Showing hidden information revealed apart from luck.** Today the dice also
  carry what a hidden spread reveals (Task 2 narrows it). Splitting that out
  would be another revision of §3 and §8; to raise with the PO after Task 2's
  measurement.

## For the PO before starting
1. ~~Approve DEFINITIONS revision 10~~ **Approved 10 Nov.**
2. **Task 4 will likely need a weekend** on your computer rather than a night.
   Task 0 measures it first.
