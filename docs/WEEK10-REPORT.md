# Week 10 report: the biggest swings made right, the averaged model, forced switches (M5 part 2)

10 November 2026. Brief: `docs/WEEK10-DISPATCH.md`. Commits `b794b8b` to
`43082c5`, plus this report. All numbers are per format and on the **validation
split** unless a line says training. The test split was not opened this week
(it has been opened 5 times, all logged).

## The headline

- **The top of Week 9's list is fixed.** Perish Song counts down and ends the
  game as Showdown does. Last Respects, Rage Fist and Supreme Overlord get their
  power from the game so far. Switching moves bring in the Pokemon the player
  chose. Of the turns with a swing over 40 points, the share fully understood
  rose from **39% to 58% in Reg M-A** and from **59% to 79% in Reg M-B**. No
  Perish Song, Last Respects or Rage Fist turn is left among them unmodelled.
- **The averaged model passed, and its own noise is under 1 point:** 0.96
  points in Reg M-A and 0.87 in Reg M-B, against about 3 for one model and the
  3-point threshold (DEFINITIONS §10.2, revision 9). It also scores slightly
  better than the single model.
- **Forced switches are decisions now, and every game adds up.** After a faint,
  the choice of Pokemon to send in is split like a turn. On your run, **all 387
  Reg M-A games and all 270 Reg M-B games** without a forfeit or timer chain
  from turn 1 to the result within 0.001 (DEFINITIONS §2).
- **The run was 29% faster than Week 9's** (29 core-hours against 41.5),
  although each turn does more. The slowest 5% of turns now take 26 to 29% of
  the time, down from about 40%.
- **The main finding: "your decision" is two things, and only one of them is the
  player.** It adds the player's choice against the average choice (typically
  11 to 12 points) to how far the model's WP before the turn is from what the
  turn held on average (typically 11 points, not a choice). Forced switches show
  it most plainly. 40% of them offer one Pokemon only, yet their "your decision"
  is typically 8.6 points. This is decision 1 below.
- **Spreads stopped at the stop rule** (your decision 9). Reg M-A's biggest swing
  shows what it leaves in the dice: a hidden Speed spread, not luck.

## Tasks 0 to 2: the turns at the top of Week 9's list

- **Task 0.** The summary now names each big swing's "partly modelled" reasons,
  counts the turns over 40 points by cause, and gives the share of parts at or
  above the 3-point threshold. A Perish Song count marked a turn partly
  modelled until Task 1.
- **Task 1, Perish Song.** The count never reached the board: the durations table
  had no attachment for it, so the timers dropped it. Now the resolver reads it,
  counts it down at the end of the turn in Speed order (Trick Room reverses it)
  and faints a Pokemon at 0. Perish Song starts the count on every active
  Pokemon except Soundproof ones. Switching out or fainting clears it, and Baton
  Pass passes it. **When both sides' last Pokemon reach 0 in the same turn,** the
  game ends as soon as one side has none left, as in Showdown. The faster
  side's count runs first, so the faster side loses (a test shows it). Week 9's
  three Perish Song turns at the top of Reg M-A now find their board, with dice 0.
- **Task 2.** Last Respects gets 50 power per fainted ally on top of its 50. Rage
  Fist gets 50 per hit the user has taken, up to 350. **Supreme Overlord was never
  passed** to the calculator by the bridge; now it is told the fainted allies, in
  the feature table and the resolver. Counts come from the log up to the decision
  only (tested). On 60 games, Task 1 changed only the Perish Song columns (36 of
  1,233 rows), and Task 2 changed 26 damage columns on 148 rows. That is why the
  table was rebuilt before Task 5.

## Task 3: moves that switch the user out

U-turn, Volt Switch, Flip Turn, Parting Shot, Baton Pass, Chilly Reception and
Shed Tail now bring in a Pokemon. For the choice taken it is the one the log
shows. For likely replies and alternatives, it is weighted by the opponent
model's chances of switching to each Pokemon. Each move adds its own rule: no
switch if the hit was blocked, Parting Shot's drops, Baton Pass's stat changes,
Chilly Reception's snow and Shed Tail's cost. **Substitute is modelled too**, as
Shed Tail and Baton Pass hand one over. Eject Button switches its holder out to
each Pokemon on the bench alike, and Eject Pack is noticed; both mark the turn
"partly modelled", as the brief allowed.

**The Week 9 resolver check again** (the same 150 Reg M-A and 200 Reg M-B games):

| | Week 9 | Week 10 |
|---|---|---|
| Reg M-A, turns fully modelled | 78% | **87%** |
| Reg M-A, board found and fully modelled | 59% | 66% |
| Reg M-A, turns with a switching move, fully modelled | 7% | **96%** |
| Reg M-B, turns fully modelled | 76% | **88%** |
| Reg M-B, board found and fully modelled | 56% | 65% |
| Reg M-B, turns with a switching move, fully modelled | 0% | **88%** |

The board found overall moved less (71% to 72%): when it is missed, the real
Pokemon is mostly bulkier than predicted, which is spreads (Task 4).

## Task 4: spreads (stopped at the stop rule)

I measured 120 real turns with every combination of the active Pokemon's
likeliest spreads:

| | Reg M-A | Reg M-B |
|---|---|---|
| Time per turn, 2 spreads each | 14 times | 19 times |
| Time per turn, 3 spreads each | 96 times | 97 times |
| Board found, 1 / 2 / 3 spreads | 73% / 78% / 85% | 68% / 78% / 82% |
| Chance the resolver gives the board that happened, 1 to 3 spreads | 45.3% to 46.7% | 47.0% to 48.2% |

The brief's sample would have taken weeks on your computer. The board that
happened turns up more often, but the chance it gets barely moves. **You chose
one spread for now** (decision 9, 9 Nov). A cheaper method is for Week 11; Task 7
below suggests where to start (Speed).

## Task 5: the averaged model (your computer)

Ten models per format, each trained on a resample of whole training sets, on the
rebuilt table (`features_v4b_full`). They took **one night**, not several:
about 22 minutes per Reg M-A model and 13 per pooled one.

| | Brier, average of 10 | against `models_v4_full`, paired | noise of the average (level, swing) | gate |
|---|---|---|---|---|
| Reg M-A | 0.1807 | **-0.0004** (-0.0007 to -0.0002) | 0.96, 0.99 points | passed |
| Reg M-B | 0.1652 | -0.0006 (-0.0019 to +0.0006) | 0.87, 0.92 points | passed |

- **The noise fell as expected:** about 3 points for one model, under 1 for
  the average of 10, measured directly from its two halves. **No blocker.**
- **Averaging did not soften the predictions**, which the brief warned it
  might. The score is slightly better, and calibration stays within the gate.
  Reg M-B's 0.2–0.3 and 0.7–0.8 bins are off by more than 0.05, but their
  intervals reach back within it (199 sets).
- The Reg M-B correction was fitted on out-of-bag predictions (66,394 training
  rows): temperature 0.943.

## Task 6: forced switches

- **The decision:** after a faint, which Pokemon to send in. The resolver plays
  the entry: both sides' Pokemon come in at once, then Intimidate, weather and
  terrain in Speed order. The board is valued at the next turn's start it
  leads to. When both sides replace, each choice is made without seeing the
  other's, so it is split exactly like a turn.
- **A model of which Pokemon is sent in** (`wpa/replace_model.py`), learned from
  1,500 Reg M-A and 2,000 Reg M-B training games. **It beats a uniform guess in
  both formats** (validation):

  | | forced switches | model | uniform | its likeliest is the one sent in |
  |---|---|---|---|---|
  | Reg M-A | 3,091 | -0.931 | -1.277 | 54% (uniform 28%) |
  | Reg M-B | 1,090 | -0.891 | -1.281 | 56% (uniform 28%) |

  (Mean log chance of the Pokemon sent in.) What weighs most: how likely an
  unseen Pokemon was brought, and how hard it hits the Pokemon on the field.
  Its own hit points barely matter.
- **A game's swings chain.** Each decision point's WP(after) is now the next
  one's WP(before): a turn, a forced switch or the result. Before, it was the
  turn's own board as the resolver valued it. The two agree to within 0.1 point
  at about 61–66% of turns. The rest of the difference goes to the dice, where
  a game's swings can add up.
- **On your run:** 1,418 forced switches in Reg M-A and 965 in Reg M-B. All games
  without a forfeit chain and add up. The player chose the best Pokemon (by the
  model) 76% of the time, and 60% where there was a real choice. 53 and 52 were
  left out because the log does not show the switch, typically when the game
  ended first. They keep their WPs, so the chain holds.

## Task 7: the brief's sample again (your computer)

The same 300 Reg M-A and 199 Reg M-B sets (526 and 366 games), with the averaged
model, sharpness 4 and everything above. Each choice was compared with the
player's 10 likeliest in every third game. "Typical size" is the root mean square,
in points.

| | Week 9 | Week 10 |
|---|---|---|
| **Reg M-A** swing | 17.2 | 16.9 |
| your decision | +2.2, typical 13.7 | +2.3, typical 14.0 |
| their decision | -2.2, typical 12.3 | -2.3, typical 12.5 |
| the dice | typical 12.6 | typical 11.8 |
| cost vs best (mean) / best taken | -8.8 / 22% | -7.7 / 25% |
| cost vs average (mean) | +3.5 | +4.0 |
| a part of 3 points or more: yours / theirs / dice | 74% / 58% / 42% | 74% / 58% / 45% |
| **Reg M-B** swing | 16.4 | 16.3 |
| your decision | +2.2, typical 14.2 | +2.3, typical 14.3 |
| their decision | -2.2, typical 12.6 | -2.3, typical 12.7 |
| the dice | typical 11.9 | typical 11.5 |
| cost vs best (mean) / best taken | -8.8 / 23% | -7.7 / 25% |
| cost vs average (mean) | +3.6 | +4.0 |
| a part of 3 points or more: yours / theirs / dice | 75% / 60% / 41% | 74% / 60% / 42% |

- **The parts add up** at every decision point (largest error 1.1e-16).
- **The dice are smaller**, and smaller still where the board is found:
  typically 9.9 points (Reg M-A) where it is found, and 16.6 where it is not
  (18.6 in Week 9).
- **Cost against the best is less harsh** (-7.7 against -8.8). Partly this is a
  fix: alternatives could include Pokemon the player had not brought (below).
- **The board that happened was among the resolver's** in 77% of turns in both
  formats (75% in Week 9).

**Every turn with a swing over 40 points, by cause:**

| | turns | found, fully modelled | found, partly modelled | not found, partly modelled | not found, fully modelled |
|---|---|---|---|---|---|
| Reg M-A, Week 9 | 132 | 52 (39%) | 35 | 16 | 29 |
| Reg M-A, Week 10 | 132 | **77 (58%)** | 23 | 2 | 30 |
| Reg M-B, Week 9 | 79 | 47 (59%) | 15 | 8 | 9 |
| Reg M-B, Week 10 | 62 | **49 (79%)** | 3 | 2 | 8 |

The reasons left among them are confusion (6), Encore (6), sleep (4), charging
moves (3), Trick (2) and Leech Seed (2). "Not found, fully modelled" stays at
30 in Reg M-A: that is mostly spreads.

### The 10 biggest swings, with reasons

Each turn once; p1's swing, then each player's split (yours / theirs / dice, from
their own side). "vs best" appears in the games with alternatives.

**Reg M-A:**

| replay | turn | p1 swing | p1 | p2 | note |
|---|---|---|---|---|---|
| [2605342116](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2605342116) | 5 | -82 | +9 / -23 / -69 | +6 / +7 / +69 | a hidden Speed spread (below) |
| [2618304355](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2618304355) | 8 | +80 | +63 / +6 / +11 (vs best +0) | -63 / -7 / -11 (vs best -56) | |
| [2592257334](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2592257334) | 6 | +75 | -10 / +0 / +85 | +12 / -2 / -85 | partly modelled: charging |
| [2601775859](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2601775859) | 7 | -75 | -38 / -28 / -9 | +66 / +0 / +9 | |
| [2625184370](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2625184370) | 10 | +71 | +16 / -1 / +56 (vs best +0) | -0 / -15 / -56 (vs best -8) | |
| [2612055074](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2612055074) | 5 | +70 | +62 / +5 / +2 (vs best -13) | -67 / -0 / -2 (vs best -31) | |
| [2632898552](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2632898552) | 6 | +68 | -11 / +77 / +2 | -47 / -19 / -2 | |
| [2631109433](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631109433) | 8 | -68 | -38 / -19 / -10 | -7 / +65 / +10 | |
| [2590847741](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590847741) | 4 | -67 | +9 / -68 / -8 | +68 / -8 / +8 | board not found |
| [2631650207](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631650207) | 10 | +66 | +66 / +0 / +0 (vs best +0, vs average +0) | -66 / +0 / +0 | Perish Song ends the game (below) |

**Reg M-B:**

| replay | turn | p1 swing | p1 | p2 | note |
|---|---|---|---|---|---|
| [2635336050](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635336050) | 7 | -78 | -33 / -42 / -3 | +75 / +0 / +3 | |
| [2635245550](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635245550) | 4 | +73 | +80 / +0 / -7 (vs best -0) | -39 / -41 / +7 (vs best -48) | |
| [2635918014](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635918014) | 15 | -69 | -61 / -8 / -0 | -0 / +69 / +0 | |
| [2635850384](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635850384) | 5 | +67 | +47 / +11 / +8 | -6 / -52 / -8 | board not found |
| [2634409842](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2634409842) | 8 | +66 | +54 / +5 / +7 (vs best +0) | -27 / -32 / -7 (vs best -20) | |
| [2635847687](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635847687) | 6 | +64 | +32 / +1 / +30 | -33 / -0 / -30 | |
| [2635761330](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635761330) | 9 | -63 | -0 / -41 / -22 | +42 / -0 / +22 | |
| [2635349372](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2635349372) | 6 | +62 | +0 / -0 / +61 | +8 / -9 / -61 | real luck: a critical hit and a double flinch |
| [2634508987](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634508987) | 6 | -61 | +9 / -62 / -8 (vs best -5) | +51 / +2 / +8 (vs best +0) | |
| [2634666109](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634666109) | 6 | -61 | +14 / -75 / +1 | +61 / +0 / -1 | |

**Three I checked against the logs:**

- **Reg M-A #1 is a hidden spread, not luck.** p2's Basculegion used Wave Crash,
  breaking Kingambit's Focus Sash, and Dragonite's Flamethrower knocked it out.
  Nothing random happened. But the spreads refined from the game so far made
  Dragonite the faster of the two. Flamethrower first would leave Kingambit
  standing, and the resolver gave that about three chances in four. Basculegion
  was faster. That is hidden information that the dice took, which is decision 9's
  open question. Speed order alone is cheap to branch on, so it is the first
  place to start in Week 11.
- **Reg M-B #8 is what the dice are for:** Hyper Voice's critical hit and a
  double flinch from Rock Slide.
- **Reg M-A #10 is Perish Song ending the game, and it shows the main finding.**
  Both of p2's Pokemon reached 0 at the end of the turn. The resolver knows the
  game is over whatever anyone chooses: every choice is worth the same (vs best
  +0, vs average +0). But the model's WP before the turn was 34%, so the whole
  +66 lands in p1's "your decision". No choice made it.

### The 10 biggest forced-switch "decisions" are not decisions

All ten in both formats had one or two Pokemon to choose from, with "vs best +0".
Two examples: in Reg M-A game
[2584502188](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2584502188),
after turn 3, p1 had only Torkoal left and p2 only Garchomp. Each player's "your
decision" is 36 points. The cause is the same as above: the model's WP just
after the turn, with a slot empty, is far from its WP at the next turn's start.

### Time

| | Week 9 | Week 10 |
|---|---|---|
| Reg M-A, core-hours | 26.0 | 18.4 |
| Reg M-B, core-hours | 15.5 | 10.9 |
| slowest 5% of turns, share of the time | 43% / 37% | 29% / 26% |
| slowest 1% of turns, share of the time | 20% / 14% | 13% / 10% |

- **Why the slow turns were slow:** time is almost exactly the number of boards
  valued, about 7 ms each. The slowest 5% valued a median of 15,872 boards each,
  against 1,064 for a typical turn.
- **The budget:** each decision point now values at most 4,000 boards. Over that,
  boards are grouped on a coarser hit-point grid, and each group takes one value.
  Nothing is dropped. It applied to about a fifth of turns. I checked it on two
  of the heaviest games, valuing every decision point with and without it. The
  parts moved by a median of 0.1 point, at most 1 point, under the averaged
  model's own noise. Those games ran 32% faster.
- Forced switches cost almost nothing (0.17 core-hours in all).
- **The whole validation split** would now take about two days with 6 workers.
  It fits in a weekend if started on a Friday evening.

## The main finding: "your decision" is two things

DEFINITIONS §3 defines your decision as E[WP | your choice] - WP(before). It
can be written exactly as the sum of two parts:

- **your choice against the average choice:** E[WP | your choice] - E[WP | the
  average choice]. This is "cost vs average", already computed in the games
  with alternatives;
- **the position:** E[WP | the average choice] - WP(before). It is what the turn
  held for any choice, against the model's WP before it. No choice of the
  player's moves it.

On your run, in the games with alternatives:

| | your decision | your choice vs the average | the position |
|---|---|---|---|
| Reg M-A turns | +2.3, typical 14.2 | +4.0, typical 11.6 | -1.7, typical 10.6 |
| Reg M-B turns | +2.5, typical 14.2 | +4.0, typical 11.3 | -1.5, typical 10.9 |
| Reg M-A forced switches | -0.4, typical 7.8 | +0.5, typical 3.5 | -0.9, typical 7.1 |
| Reg M-B forced switches | +0.1, typical 8.2 | +0.5, typical 3.8 | -0.4, typical 7.4 |

- **The position is as big as the choice** in turns, and twice as big in forced
  switches. It is where the Perish Song turn above lands. It also explains why
  "your decision" never reached an average of zero: players beat the average
  choice by 4 points, and the position takes back about 1.7.
- **The position is real information, not noise**, but it is not the player's.
  It is the gap between the model's single WP and what the resolver and the
  opponent model expect: the Perish count the model did not weigh, a slot about
  to be filled, a board the model reads differently once the turn is played.
- Splitting it out needs the average choice at every decision point, not just
  every third game. That would make the run about 2 to 3 times longer: a
  weekend instead of a night. This is decision 1.

## Surprises

- **Week 9's resolver ran out of memory too, quietly.** Two Reg M-A turns
  (Discharge with Heat Wave; Matcha Gotcha with Rock Slide) held about 89,000
  boards at once and needed over 3 GB. Week 9's run had no limit, so they got
  through. Now boards are merged as they arrive and peak at about 200 MB, with
  exactly the same result. Making that exact needed the coarser grids to fit
  inside one another, which they did not before. That change touches only turns
  over the cap.
- **A player's alternatives included Pokemon they had not brought.** The options
  offered every Pokemon not yet seen, which is right for the opponent's guess
  but not for the player's own choice. Where the log shows all four, the player's
  options now leave the other two out. It lowered cost vs best.
- **The averaged model took one night,** not the several I planned for.
- **Choosing a forced switch matters less than I expected.** By the model, the
  choice against the average is typically 3.5 to 3.8 points, a third of a turn's.
- **Valuing boards is the whole cost of a turn.** Neither the resolver nor the
  model's prediction is: it is building each board's feature row.

## What went wrong, and was caught

- **The first Week 10 resolver check was killed for memory.** I ran Week 9's code
  and Week 10's at the same time. Running them one at a time showed that the
  heavy turns were the cause in both.
- **Writes to your computer arrived late, and one landed out of order,** putting
  an older file back over a newer one for a few minutes. I now check each file's
  checksum before running or committing. Nothing wrong was committed.
- **Eight test fixtures were wrong, not the code.** Among them: a replacement
  in the same block as the turn's end (real logs separate them), a stand-in
  value that ignored which Pokemon is on the field, Incineroar resisting Last
  Respects, too few models for the out-of-bag test, and Snarl, which is not in
  Champions. Each was fixed in the test; the code was unchanged.
- **Two of four games did not match** in the budget check (their tags were not
  in the sample in the form I gave). The two that ran are enough for the
  conclusion, not for a precise number.

## Process notes

- Tests first throughout, each shown failing before the code. The suite grew
  from 595 to 647 passing tests.
- The full suite: **647 passed, 3 skipped.** The same 15 test files cannot load on
  the development machine (bot libraries). ruff and pyright are clean.
- The test split was not opened. It has been opened 5 times.
- Runbook Section 19 covers this week's commands (steps 1 to 5).

## Decisions for the product owner

1. **Split "your decision" into your choice and the position** (DEFINITIONS §3,
   needs your approval). Options:
   - **(a)** Report "your choice" (against the average choice) as the decision,
     and "the position" beside it, not credited to anyone. The three parts still
     add up to the swing. It needs the average choice everywhere: about 2 to 3
     times the run time (a weekend for the brief's sample).
   - **(b)** Keep §3 as it is, but have the M7 report lead with cost against the
     average and the best, and show "your decision" only as context. No extra
     time, but only every third game has those numbers.
   - **(c)** Leave it as it is.

   I recommend (a). The report's whole promise is "what was your decision and
   what wasn't", and today a third of "your decision" is neither.
2. **Week 11.** The brief planned team preview and leads (the rest of §6). I
   would add, in this order:
   - the split from decision 1, if you approve it;
   - Speed order from the hidden spreads, the cheapest part of decision 9 and the
     cause of Reg M-A's biggest swing;
   - charging moves, confusion, Encore and sleep, the reasons left among the
     biggest swings.

   The stronger opponent model and the full spread method would wait for Week 12.
   Agree, or reorder?
