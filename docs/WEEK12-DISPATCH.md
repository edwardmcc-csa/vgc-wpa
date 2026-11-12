# Week 12 — Dispatch Brief (M5 part 4: ironing out Reg M-A and Reg M-B)

**Status:** drafted 11 Nov 2026 from the PO's decisions on the Week 11 report
(agreed 11 Nov).
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

Week 11 split "your decision" into your choice and the position. It made every
game add up from team preview to its result, and raised the share of the
biggest swings fully understood to 70% (Reg M-A) and 81% (Reg M-B).

Checking the top of its lists against the logs found two things:
- a game-end bug, now fixed;
- **a type change the resolver does not track** (Protean). It produced Reg M-A's
  two biggest "choices".

Work done ahead of Week 12 is not yet measured. It modelled more of the Champions
rules and made the replay report (M7).

The PO wants Reg M-A and M-B solid before Reg M-C, with **live advice during a
match** as the goal. Live advice and analysing games played in the app both need
the analysis to work **without the opponent's team sheet**: the app shows species
only.

## Decisions (PO, 11 Nov 2026)

1. **Reg M-C waits** until Reg M-A and M-B are ironed out. What it needs is
   listed in `docs/REG-MC-GAPS.md`.
2. **Live advice during a match is the goal.**
   - The screen reader is built live-first: it reads the phone's screen,
     mirrored to the computer. The post-game reports come from the same work.
   - The phone is an iPhone: wireless mirroring to test, then a cable and
     capture card for real use.
   - Official tournaments forbid outside help during games; check the app's
     rules before using it in ranked.
   - The trial of reading a recorded game is in `docs/APP-CAPTURE-TRIAL.md`.
3. **Week 12, in this order:** measure the fixes; Protean and Libero; the
   stronger opponent model; a cheaper spread method; hidden opponent sets; the
   brief's sample again.

## Tasks

### Task 1 — Measure the fixes since Week 11's run (the resolver check)
- [x] **A command for the resolver check**, so it can be run again any week:
      `python -m wpa.resolver_check`. On a fixed sample of validation games per
      format (the list saved, so the same games every time), it gives:
      - the share of turns fully modelled;
      - the share where the board that happened was among the resolver's;
      - the share with both;
      - the reasons left;
      - the time.
- [x] **Before and after, on the PO's computer:** the code of Week 11's run
      (`9e9ef90`) and today's, on the same sample. It should take about an
      hour.
      Done 12 Nov in the Linux workspace on the PO's computer, 13 minutes
      per run on 2 workers (Runbook Section 22).
- [x] Tests first.

### Task 2 — Protean, Libero and other type changes
- [ ] **The board keeps a changed type** from the log, until the Pokemon leaves
      the field: Protean, Libero, and moves that change types.
- [ ] **The resolver:** a Pokemon with Protean or Libero becomes the type of the
      move it uses, as often as Showdown's Champions data allows. Damage after
      that uses the new type: the calculator is told the types.
- [ ] Other type changes the resolver cannot play out are marked "partly
      modelled", never passed in silence.
- [ ] **Check:** game 2616502323, turns 7 and 8 (Reg M-A's two biggest "choices"
      in Week 11), against its log.
- [ ] Tests first.

### Task 3 — The stronger opponent model
Today the opponent's likely replies come from a model of what players choose,
made sharper (sharpness 4). Their decision still averages about -2.2 points:
real players choose better than the model expects (Week 9 found this curve
flattens; sharpening cannot fix it).

- [ ] **Weigh each reply also by how good it is for the opponent**: its value
      against your likely choices, from the resolver. One strength setting is
      learned on training games.
- [ ] **Measure first,** on a sample:
      - how far their decision's average moves towards 0;
      - what happens to your choice;
      - the time it costs.
- [ ] **If it changes what DEFINITIONS §7 says** about the opponent's likely
      replies, a revision is drafted for the PO's approval before the code
      changes.
- [ ] Tests first.

### Task 4 — A cheaper spread method
Week 10 stopped averaging over spreads: two spreads each cost 14 to 19 times the
time per turn. Spreads are still most of the turns where the board is missed
("not found, fully modelled": 30 in Reg M-A among the biggest swings).

- [ ] **Branch on spreads only where they decide something:** the hits where
      another likely spread would change whether the target is knocked out.
- [ ] **Measure:** the cost, the share of boards found and the dice on the
      biggest swings, beside Week 10's table.
- [ ] **Stop rule:** if it more than doubles the time per turn for under 3
      points of boards found, stop and report.
- [ ] Tests first.

### Task 5 — Hidden opponent sets
- [ ] **The analysis without the opponent's team sheet:**
      - their moves, item and ability are beliefs from usage statistics,
        updated by what the game reveals (a move used, an item shown, an
        ability announced);
      - the player's own sheet is known;
      - the win probability model is the one trained with sheets hidden
        (Week 8).
- [ ] **Check on Reg M-A and M-B games whose sheets we know**, with them hidden:
      how far each part of the split moves, and the boards found.
- [ ] **The replay report** reads a game without team sheets.
- [ ] Tests first.

### Task 6 — The brief's sample again (the PO's computer)
- [ ] The same 300 Reg M-A and 199 Reg M-B sets, with this week's changes (Tasks
      2 to 4), the averaged model, and sharpness 4 or Task 3's setting.
- [ ] **Report beside Week 11's:** the four parts per format, the turns over 40
      points by cause, and the biggest swings and choices, each with its
      checks against the logs.

### Task 7 — Runbook and report
- [ ] Runbook sections for this week's commands. A report in prose, with a
      surprises section.

## Out of scope this week
- **Reg M-C** (decision 1): `docs/REG-MC-GAPS.md` lists what it needs.
- **The live screen reader** and the app-capture tool. Both come after M-C and
  hidden opponent sets.
- **Your own team's spreads**, and re-scoring your games with other spreads.

## For the PO before starting
1. **Try the replay report** on a game (Runbook Section 21). Record its
   end-to-end check once: about ten minutes, with the command in Section 21
   and `$env:WPA_RECORD=1`.
2. **Task 1 needs about an hour on your computer.** I will give you the command
   once it is written.
