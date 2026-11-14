# Week 12 report: the resolver check, type changes, the stronger opponent model, spreads, hidden sheets (M5 part 4)

13 November 2026. Brief: `docs/WEEK12-DISPATCH.md`. Commits `8a4546a` to `50e3ba8`, plus this report (`5d13538` is Week 13 work done ahead). All numbers are per format and on the **validation split** unless a line says training. The test split was not opened this week (it has been opened 5 times, all logged).

**Every task's boxes are ticked.** The tests pass here (892, 12 skipped as slow). 15 test files need the battle harness's libraries, which only your computer's setup has; none of them changed this week. Step 2 ran at commit `5e4c442`. The fixes made beside it (`ddfab91`, `19e2ede`, `7df9b1d`) are not in its numbers; the resolver check below includes them.

## The headline

- **The resolver now finds the board that happened on 83% of Reg M-A turns and 86% of Reg M-B turns, up from 77% in both.** Turns it fully models and finds: 72% → 81% (Reg M-A), 72% → 85% (Reg M-B). This is the week's first new tool, the resolver check: it plays out each turn's actual choices and checks the result against the log, on the same 892 validation games every time.
- **Players choose better than the opponent model expected, by about 6 points a decision (training games).** Weighing each option also by how good it is for the one choosing closes most of that gap. One setting, learned on training games, fits both formats: 6.3 for Reg M-A, 6.8 for Reg M-B, 6.55 together. On validation, where the log shows the choice, players beat the typical choice by 3.0 points (Reg M-A) and 3.1 (Reg M-B) at strength 0, and by 1.2 and 1.3 at 6.55; their opponents' replies take back 2.4 and 2.6, then 0.6 and 0.7. **You approved it as DEFINITIONS revision 11** (13 Nov), with one correction found on the way (a choice the log hides).
- **The analysis can now run without the opponent's team sheet**, as in your app games: their sets are believed from the usage statistics and what the game shows. From team preview's species alone it gets 3.1 of 4 moves right, the item 63–65% of the time and the ability 88–89%. Each player is judged on what they could have known. **Checked on 160 games whose sheets we know, with them hidden:** where a part of the split is 3 points or more with whole sheets, it points the same way 84–87% of the time. The board found falls from 84% to 77% (Reg M-A) and from 85% to 78% (Reg M-B), and that goes into the dice.
- **Branching on spreads where they decide a knock-out** cut the resolver's knock-out misses by 14% (Reg M-A) and 19% (Reg M-B), for 33–40% more resolver time per turn. Most of its HP misses are not spreads.
- **The brief's sample again (your run): the dice shrank and more of the biggest swings are understood.** The dice are typically 10.8 points (Reg M-A) and 10.4 (Reg M-B), from 11.3 and 11.1. Of the turns with a swing over 40 points, fully understood: 77% in Reg M-A (70% in Week 11) and 82% in Reg M-B (81%).

## Task 1: the resolver check

`wpa.resolver_check` (commits `8a4546a`, `30ffe4d`; Runbook §22). It plays out
each turn's actual choices, as the log shows them, and checks the result
against the log. The sample is fixed: every game of the brief's 300 Reg M-A and
199 Reg M-B sets, 892 validation games, 3,628 and 2,614 turns. It needs no win
probability model and refuses any game in the test split. `--code COMMIT`
runs an earlier commit's code on the same games, so two runs compare turn by
turn.

- **Fully modelled:** nothing happened that the resolver models only in part.
- **Board found:** the board that happened is among the resolver's boards
  (the same Pokemon knocked out, every HP within 6 points).

| | Reg M-A, start | step 2's code | now | Reg M-B, start | step 2's code | now |
|---|---|---|---|---|---|---|
| fully modelled | 91.6% | 94.0% | **97.8%** | 91.0% | 96.5% | **98.9%** |
| board found | 77.3% | 82.2% | **83.0%** | 77.3% | 83.8% | **85.9%** |
| both | 72.1% | 77.9% | **81.4%** | 71.8% | 81.6% | **85.3%** |
| both, turns with a knock-out | 74.2% | 80.1% | 84.0% | 73.5% | 83.7% | 87.3% |
| misses: a knock-out differs | 125 | 98 | 94 | 87 | 57 | 42 |
| misses: HP only | 697 | 547 | 522 | 506 | 366 | 326 |
| resolver time per turn | 0.165 s | 0.320 s | 0.235 s | 0.107 s | 0.193 s | 0.148 s |

"Start" is `9e9ef90`, Week 11's code; "step 2's code" is `5fea43a` with Task
4's spread method; "now" is `7df9b1d`, with the fixes made beside step 2's run
(below and "Worked ahead"): 90 turns found that were not, 6 the other way. The time per turn is from my 2-core workspace and is noisy; Task 4 is
most of the rise.

**What the check found, and what was fixed** (each with a test, shown failing
first):
- Encore, Leech Seed, Disable, Taunt, Toxic's counter, Yawn and Strength Sap
  were modelled only in part; now in full.
- Leech Seed drained into an empty place: Showdown heals whoever is in the
  seeder's place, nothing when it is empty.
- Encore changed Gholdengo's move, though Good as Gold blocks it.
- End-of-turn damage ran after the game had ended.
- Hospitality, Regenerator, binding moves (Infestation and the like) and Solar
  Power were missing. Turns where they acted were missed 64% to 100% of the
  time.
- Fairy Aura, Dark Aura and Friend Guard were not passed to the calculator.
- Comparing two runs turn by turn caught my own regression: 14 turns found
  before and not after one change, 91 the other way. The 14 were the Leech
  Seed, Good as Gold and game-end cases above, and 3–4 turns just over the
  6-point line.

**Left, modelled in part, at `7df9b1d`** (turns, Reg M-A / Reg M-B): Skill
Swap 9 / 2, the Pokemon sent in after a pivot move 7 / 10, Gravity 7 / 0,
Imprison 7 / 0, Transform 7 / 2, a Substitute's hit points 7 / 0, Leech Seed
healing 7 / 1, Entrainment 6 / 0, Stockpile 5 / 4, Curse 5 / 1, Stealth Rock
5 / 0, and a few with 1 to 3 turns. Poison Touch, Moody, Cursed Body, Instruct,
Flame Body, Trick and Quash, the biggest earlier in the week, are now modelled
in full. Week 13 Task 2 takes the rest.

## Task 2: Protean, Libero and type changes

Commits `da0a820`, `f106eb2`, `599756c`. In the 79,934 games outside the test
split, Protean or Libero changed a type 3,235 times in 2,386 games; Soak 286
times, Trick-or-Treat 78, Burn Up 54, Reflect Type 9, Forest's Curse 7.

- **The board** keeps each Pokemon's types when they change, and whether
  Protean has acted. Mega Evolution resets both: game 2620833313's Greninja
  turned Normal with Protect, Mega Evolved, then turned Dark with Dark Pulse.
- **The resolver:** Protean and Libero act once per switch-in (Generation 9;
  the Champions rules do not change it), and Protect counts only when it
  works. Soak, Trick-or-Treat, Forest's Curse and Reflect Type change types;
  Burn Up and Double Shock fail without their type and lose it when they hit;
  Roost loses Flying for the turn.
- **The calculator** takes the types a Pokemon has now. It used to give a
  Protean user STAB on every move (the Generation 6–8 rule).
- **Week 11's two biggest "choices" were this.** Game 2616502323's Meowscarada:
  your choice at turn 7 was −53 points and is now +37; at turn 8, −56 and now
  +39. Its turn-8 dice are +31: its second Protect failed.
- The resolver check barely moves (both 75.7% → 75.6% in Reg M-A, 77.1% →
  77.2% in Reg M-B): it plays out the choices made, and Protean matters most
  for the choices not made.

## Task 3: the stronger opponent model

Commits `32c8aa6`, `c561a33`, `7df9b1d`, `bdfa065`; Runbook §23 steps 1–2. Each likely choice's chance is the choice
model's, weighed by its worth to the one choosing: `chance × exp(strength ×
worth)`, its worth being E[WP] against the other side's plain likely choices
(one step of reasoning). Both sides are weighed. Off (strength 0, revision 10)
unless asked for; your run measured strength 0 and the learned strength side by
side, with strength 0 the main split.

**Learned on training games** (115 games, 1,178 choices, 56% of them among the
12 candidates the fit can weigh): 6.3 Reg M-A, 6.8 Reg M-B, **6.55 together**.
At strength 0 the choices players made were worth 6.2 points more than the
model expected; at the learned strength, 0 (by construction). Log likelihood
−1,954 → −1,846.

**On validation (your run, the brief's sample):**

| | Reg M-A, strength 0 | 6.55 | Reg M-B, strength 0 | 6.55 |
|---|---|---|---|---|
| your choice, where the log shows it | +3.0, typical 12.4 | +1.2, typical 12.3 | +3.1, typical 12.3 | +1.3, typical 12.0 |
| your choice, all | +2.4, typical 11.5 | +0.6, typical 11.6 | +2.6, typical 11.7 | +0.7, typical 11.5 |
| their decision | −2.4, typical 12.4 | −0.6, typical 12.1 | −2.6, typical 12.6 | −0.7, typical 12.1 |
| cost vs best | −7.5 | −7.2 | −7.4 | −7.4 |
| choices of 40 points or more | 91 | 103 | 58 | 60 |

(Reg M-A: 526 games, 7,256 decision points, 5,436 where the log shows the
choice; Reg M-B: 366 games, 5,228 and 4,082.)

- **The two formats agree.** It closes about 60–75% of the gap on validation,
  not all of it as on training: players still beat the typical choice by
  about a point where the log shows their choice.
- **It moves the big choices rather than removing them.** Choices of 40 points
  or more: 91 at strength 0, 103 at 6.55. What changes is which ones:
  - Game 2605465902 turn 8, Reg M-A's biggest choices at strength 0 (p2 +81,
    p1 −74), are the plain model's naivety. It expected p2's Garchomp to
    Earthquake (98%) into a faster Ninetales-Alola's Blizzard, 4× effective in
    snow. Both players protected instead, as a strong player would. At 6.55
    they are +1 and +7.
  - Game 2613511446 turn 8 becomes the biggest (−31 → −99). p1 used Coaching
    with Sneasler instead of attacking Floette, and Floette's Dazzling Gleam
    then knocked out both. The model's best (both attacking Floette) wins; the
    choice made loses. A real mistake, sized better by the stronger model.
  - Game 2615562713 turn 7: at 6.55 the blame moves from p2 (−78 → +20) to p1
    (−5 → −78). p1's Meowscarada (29%) used Flower Trick into a faster Garchomp
    whose likely move, Earthquake, would have knocked it out first; Protect was
    safe. p2 instead used Scale Shot on the other Garchomp, and lost. The
    stronger model calls p1's play a gamble that paid off (their decision +96
    for p1); the plain model called it typical, because 85% of players make it.
- **A correction it needs (found checking these):** where the log hides a
  choice (a Pokemon knocked out before it moved: 25% of decision points), the
  choice is averaged over the options the log allows. Your run averaged it
  with the plain chances, while the typical choice was weighed by worth, so at
  6.55 a player whose choice was hidden was judged against a smarter typical
  choice than their own average. In game 2585454640 that gave −46 and −31 to
  p2's hidden choices; weighed the same way, +1 and 0. Fixed beside your run
  with a test (shown failing first), applied after it. It does not change the
  "log shows it" row above; the "all" row at 6.55 is low by an amount I can
  only measure with the next run (hidden choices average −1.0 in Reg M-A and
  −1.1 in Reg M-B there). Committed as `7df9b1d`; strength 0 is unchanged.

## Task 4: a cheaper spread method

Commit `30ffe4d`; `--spread-hits`. A hit branches on the target's (or the
attacker's) likely spreads (chance 10% or more, at most 3 each) only where one
of them moves the chance of a knock-out by a quarter or more; elsewhere the
likeliest spread alone, as before. Damage on another spread is put in the
likeliest spread's hit points, so the board keeps one scale.

On the resolver check, the same code with and without it:

| | Reg M-A off | on | Reg M-B off | on |
|---|---|---|---|---|
| board found | 79.9% | 80.5% | 79.5% | 80.6% |
| misses: a knock-out differs | 120 | 103 (−14%) | 85 | 69 (−19%) |
| misses: HP only | 610 | 603 | 452 | 438 |
| resolver time per turn | 0.200 s | 0.279 s (+40%) | 0.129 s | 0.171 s (+33%) |

- **The stop rule is not triggered:** under double the time.
- **It gains under a point of boards found,** because by design it only
  branches where a knock-out depends on the spread. The HP misses are mostly
  not spreads (see "Worked ahead").
- Step 2's run uses it. In the analysis it added little time (three short
  games: the same to within a second).

## Task 5: hidden opponent sets

Commits `239185c`, `c09c521`, `89f7d7f`, `5e4c442`. The analysis can now run as a
player in a closed-sheet game knows it, as in your app games.

- **Their sets are beliefs** (`wpa/hidden.py`). What the game has shown is kept
  (a move used, an item shown, an ability announced); the rest is the likeliest
  from the usage statistics: the likeliest moves to make four, the likeliest
  ability, and the likeliest item no teammate holds (the Item Clause), the
  surest first. A species with a Mega form: the statistics count the Mega set
  apart, so the two are weighed by use and by how often each holds what the
  game has shown.
- **How good the beliefs are** from team preview's species alone (400
  validation games, every Pokemon): 3.1 of 4 moves right, the item 63% (Reg
  M-A) and 65% (Reg M-B), the ability 88–89%, Mega or not 95–96%.
- **Each player is judged on what they could know** (`--hidden-sets`): their
  own sheet whole, the opponent's believed, the win probability from the model
  trained with the opponent's sheet blanked (Week 8, with team preview's
  species: Week 9). The two players know different things, so each turn is
  analysed twice, once from each side, with each player's own WPs. A game
  costs about 1.5 times as much.
- **Not split with the sheet hidden:** team preview and forced switches keep
  each player's WPs, so each game still adds up, but are not split.
- **The replay report reads a game without team sheets** (`--team`, Runbook
  §21 step 5): your team from a team paste, theirs from team preview.
- **The win model trained with the opponent's sheet blanked** (Runbook §23
  step 3, `models_v4_preview`, your computer, 13 Nov). On validation: Brier
  0.188 against the v0 baseline's 0.210 in Reg M-A (skill +0.25), and 0.178
  against 0.203 in Reg M-B (skill +0.29, a small sample of 199 sets).
  Calibrated within a few points in every band; the gate passed.
- **Limits:** which four they brought is taken from the log (a player cannot
  know their back two); your own spreads are taken from the statistics, not
  your paste.

**The check** (Runbook §23 step 4, your computer, 13 Nov, 6:08–9:54 pm).
The first 100 Reg M-A and 60 Reg M-B games of the brief's sample, at
strength 6.55, analysed twice: with both sheets, and with each player's
opponent's sheet hidden. Compared turn by turn, each player's own. Turns
followed by a forced switch are left out, since the hidden reading does not
split forced switches.

| | Reg M-A whole | hidden | moved by | same way | Reg M-B whole | hidden | moved by | same way |
|---|---|---|---|---|---|---|---|---|
| WP at the turn's start | 50.0 | 49.7 | 6.8 / 5.2 / 66% | | 50.0 | 50.9 | 6.8 / 4.4 / 66% | |
| your choice | +1.0 | +0.7 | 5.1 / 2.5 / 46% | 84% | +1.0 | +0.7 | 4.3 / 2.4 / 42% | 86% |
| the position | +0.0 | +0.9 | 6.2 / 3.8 / 55% | 86% | −0.0 | +0.6 | 6.9 / 4.3 / 62% | 85% |
| their decision | −1.0 | −0.6 | 5.6 / 2.9 / 49% | 85% | −1.0 | −0.6 | 5.3 / 2.8 / 48% | 85% |
| the dice | −0.0 | −0.7 | 3.9 / 1.7 / 37% | 86% | −0.0 | −0.9 | 3.9 / 1.6 / 34% | 86% |
| the turn's swing | −0.0 | +0.3 | 6.6 / 4.8 / 64% | 87% | +0.0 | −0.2 | 6.7 / 4.2 / 60% | 87% |
| the board found | 84% | 77% | | | 85% | 78% | | |

(864 turns in 96 games for Reg M-A; 496 in 57 for Reg M-B. "Moved by": the
mean, the median, and the share of turns moved 3 points or more. "Same way":
of the turns where the part is 3 points or more with whole sheets, the share
where it points the same way with the sheet hidden.)

- **The direction holds.** A part that matters (3 points or more) points the
  same way 84–87% of the time in both formats.
- **The size moves.** A typical turn's part moves by about 2.5 points, and
  some move a lot: the mean is 4 to 7 points.
- **The board is found less often** (7 points fewer in both formats): the
  believed sets miss some moves and items. Analysed whole and hidden, the
  dice are typically 10.1 and 12.7 points in Reg M-A, 9.8 and 10.8 in Reg M-B.
- **For your app games:** the replay report reads the turns that matter the
  same way about 6 times in 7, with bigger dice.
- One turn failed with the sheet hidden, 2 of 2,179 decision points. It is
  fixed (see "What went wrong").

## Task 6: the brief's sample again (your computer)

The same 300 Reg M-A and 199 Reg M-B sets (526 and 366 games), at commit
`5e4c442`, with the averaged model, sharpness 4, the spread method of Task 4 and
strength 0 (6.55 measured beside). It finished on 13 November at 3:45 pm.

| | Reg M-A, Week 11 | Week 12 | Reg M-B, Week 11 | Week 12 |
|---|---|---|---|---|
| swing | 16.9 | 16.9 | 16.3 | 16.3 |
| your choice (against the typical choice) | +2.2, typical 11.9 | +2.4, typical 11.5 | +2.3, typical 11.9 | +2.6, typical 11.7 |
| the position | +0.0, typical 11.9 | +0.0, typical 11.6 | +0.0, typical 12.3 | +0.0, typical 12.0 |
| their decision | −2.2, typical 12.7 | −2.4, typical 12.4 | −2.3, typical 12.9 | −2.6, typical 12.6 |
| the dice | typical 11.3 | **typical 10.8** | typical 11.1 | **typical 10.4** |
| cost vs best (mean) / best taken | −7.8 / 25% | −7.5 / 26% | −7.8 / 25% | −7.4 / 26% |
| a part of 3 points or more | choice 59%, position 71%, theirs 59%, dice 43% | choice 59%, position 70%, theirs 58%, dice 42% | choice 59%, position 73%, theirs 61%, dice 41% | choice 58%, position 72%, theirs 60%, dice 40% |
| the board that happened among the resolver's | 77% | **82%** | 77% | **84%** |
| turns over 40 points: found, fully modelled | 92 of 132 (70%) | **101 of 132 (77%)** | 50 of 62 (81%) | **51 of 62 (82%)** |
| team preview: your choice / cost vs best / best pair led | +0.9, typical 3.8 / −5.3 / 10% | the same | +1.1, typical 4.0 / −5.8 / 10% | the same |
| forced switches: your choice / cost vs best / best taken | +0.5, typical 3.6 / −1.4 / 76% | +0.6, typical 3.6 / −1.4 / 76% | +0.5, typical 3.8 / −1.6 / 76% | +0.5, typical 3.9 / −1.6 / 76% |
| median time per turn / core-hours | 16.1 s / 19.6 | 25.0 s / 33.5 | 21.3 s / 33.4 | 22.4 s / 20.8 |

- **The four parts add up** at every decision point (largest error 1.1e-16), and
  every game without a forfeit or timer chains from team preview to its result
  (387 Reg M-A, 270 Reg M-B).
- **The dice are smaller** (11.3 → 10.8, 11.1 → 10.4): more of each turn is
  modelled (Tasks 1, 2 and 4). The board that happened was among the
  resolver's in 82% and 84% of turns, from 77%.
- **Turns over 40 points:** of the 132, not found and fully modelled 24 (30 in
  Week 11); partly modelled 7. The causes left among them: Trick 2, Flame Body,
  Quash, Poison Touch, Cursed Body and Leech Seed 1 each. Flame Body, Poison
  Touch and Cursed Body are modelled beside your run. Reg M-B: not found and
  fully modelled 8 (as in Week 11); partly modelled 3 (Trick, Tidy Up, Poison
  Touch).
- **Time:** Reg M-A's core-hours are up 70%: the spread method (Task 4, about
  35%), the resolver's new rules, and probably my checks sharing your computer
  during that part of the run. Reg M-B's 20.8 are below Week 11's 33.4, which
  had the sleeping-computer stalls; the median turn is about the same (22.4 s
  against 21.3). It finished on the afternoon of 13 November, not the extra
  night I expected (I had assumed Reg M-B would run as slowly as in Week 11).

## Task 7: the Runbook

New this week: Section 22 (the resolver check), Section 23 (learning the
strength, the brief's sample again, the model with the opponent's sheet
blanked and the check with sheets hidden), Section 21 step 5 (a game without
team sheets). Done ahead: Section 24 (advice at team preview, a turn's start
and a forced switch) and Section 25 (your team).

## Surprises

- **Mega Staraptor has Contrary.** Every stat change on it goes the other way: its own Close Combat raises its defences, and its partner's Charm (Attack −2) is a +2. The resolver had no Contrary; turns where its stats changed were found 67% of the time against 83%.
- **White Herb was missing from the resolver**, though the board tracked it. Sneasler's Close Combat drops were kept for the rest of the turn, so later hits on it were too strong (65% found).
- **A screen also weakens an ally's spread move.** The resolver skipped screens when the attacker was on the same side; Showdown applies them to any hit on that side but the user's own.
- **Turn order changes during a turn in Generation 9.** After each move the order is sorted again, so a Tailwind set this turn speeds up its side's later movers at once. The resolver orders the turn once at the start. Turns where Tailwind was set and moves followed were found 78% of the time.
- **Two of the turns the resolver "found" before these fixes were found by two errors cancelling out**: the Attack drop too big and the damage too high. They are lost now, for 45 gained.
- **The statistics count Sinistcha-Masterpiece as Sinistcha.** It is in 96 of the resolver check's 892 games. Looked up under its own name it has no entry. So with the sheet hidden it had no believed set (fixed, below). And in every analysis, whole sheets too, it gets the spread used for a Pokemon the statistics do not list: full HP and full Special Attack. Real Sinistchas are Bold or Calm with their points in the defences, so hits on it are valued too strong. Maushold-Four (46 games) is the same. This is one concrete cause of the resolver hitting too hard, and the first thing Week 13 Task 1 fixes.

## What went wrong, and was caught

- **Week 11 blamed the wrong cause for a Perish Song turn.** Game 2631650207
  turn 10 (+67 dice) was listed as "wrong: the game-end bug". It is real luck.
  p1's last Pokemon, Incineroar, used Protect a second turn in a row, which
  works 1 time in 3. It held, and p2's two perishing Pokemon fainted. Had it
  failed, Hurricane and a rain Weather Ball would have knocked Incineroar out
  first and p2 would have won. The game-end fix made this right; the earlier
  "+66 position" was the error.
- **The stronger model's hidden-choice weighing** (Task 3 above): found when a
  top choice looked wrong, before it reached a definition.
- **One turn failed in the check with the sheet hidden** (game 2634478000 turn
  4, both players: division by zero). Its Sinistcha-Masterpiece had no
  believed moves (see Surprises). Knocked out before moving, its only option
  was a switch to the Pokemon its partner had switched to, so no joint choice
  was left. Fixed with three tests (`50e3ba8`): a form takes its species' set,
  and a hidden choice that cannot go with the shown ones is left out instead
  of failing.
- **My time estimate for step 4 was wrong:** I said 6 or 7 in the morning. It
  finished at 9:54 pm.

## Worked ahead while your run went (not in its numbers)

- **The resolver's HP misses, diagnosed.** In a sample of 160 missed turns, the resolver hit too hard 2 times in 3. Three causes were rules the resolver lacked: White Herb, Contrary, and screens on an ally's hit. All three are fixed with tests (five new), written beside your run and applied after it. On the 224 games where they act: boards found +45 turns, −2.
- **Quash, After You, Trick and Instruct in the resolver** (beside your run, tests first). Quash sends the target's move to the end of the turn and keeps it there when the order is sorted again; After You brings it next; Trick and Switcheroo swap items (not a Mega Stone, not against Sticky Hold); Instruct has the target use its last move again at once, unless it charges. On the 36 validation games where they were used (279 turns): boards found 205 → 214, none lost; found and fully modelled 159 → 208. Instruct's 29 turns: found 11 → 19. Left: Ally Switch (2 turns), and Instruct on a one-target move used the turn before (1), whose target the board does not keep.
- **The replay report for a game without team sheets** (`--team`, Runbook §21 step 5). Your team comes from a team paste; the opponent's species from team preview.
- **Reading the app's team preview** (a Switch Single Battle screenshot, 13 Nov). Your side shows names and held items; theirs shows only a picture, two type icons and the gender, with a 90-second timer. Type icons alone are not enough: the most-used Pokemon with those types is right 83% of the time in Reg M-A and 86% in Reg M-B (June statistics), so about one of their six would be wrong per team (Sylveon or Floette, Milotic or Politoed, Charizard or Talonflame). Read from the picture, all six were named (Gardevoir, Heracross, Drampa, Azumarill, Corviknight, Abomasnow); all are in the Reg M-A and M-B statistics, some on under 0.2% of teams.
- **Team preview advice now gives four to pick, as the app asks** (commit `4d74bf6`, Runbook §24). The app takes four in pick order, the first two leading. The leads are ranked by the model as before; with each pair come the two players most often bring with those leads (the bring model). About a second once loaded.
- **The model cannot rank back twos (checked before trusting it).** On the resolver check's 892 validation games, every side whose four all came out (865 Reg M-A, 593 Reg M-B): the win chance at turn 1's start with the four actually brought, against each other four with the same leads. The values moved 6.1 (Reg M-A) and 7.6 (Reg M-B) points between those fours, but the actual four predicted the result better in only 49.9% and 50.7% of comparisons; log loss 0.0021 (SE 0.0020) and 0.0047 (SE 0.0029) better. So the back features move the number without carrying the result. A question for the model work: at turn 1's start the model's log loss is 0.688 (Reg M-A) and 0.662 (Reg M-B), against 0.693 for a coin.
- **Your own team from the app's summary screens.** Moves & More gives species, ability, item, moves and gender; Stats gives the stat points and, by its arrows, the nature. Read off one Stats screen, all 36 stats matched what base stats, points and nature give. The app's "Rotom" and "Floette" need their form: the type icons settle Rotom's (Electric/Water is Wash), the format has only Floette-Eternal.

- **Two more resolver rules** (`189aac7`, tests first). A Prankster status move aimed at a Dark type fails, so a blocked Parting Shot no longer switches. Soundproof blocks sound moves aimed at its holder. On the resolver check's pivot games these were 5 of the turns marked "pivot switch-in".
- **Your team, loaded in** (Week 13 Task 3, done ahead: `5d13538`, Runbook §25). Save your paste as `my_team.txt` in the repo folder (never committed). The advice and the replay report then use it without `--team`. `python -m wpa.team_check` prints each Pokemon's six stats at level 50, to set beside the app's Stats screen, and flags more than 66 stat points in all or more than 32 in one stat. The advice uses your nicknames (End Game, Mia). It warns when your team has a Pokemon the format's statistics have not seen or have seen on under 1% of teams. For your current team that is Golisopod (in neither format's statistics) and female Basculegion (0.4% in Reg M-B, 0.5% in Reg M-A).

## Decisions for the product owner

1. **DEFINITIONS revision 11 (§7, the opponent model): approved 13 Nov.** Strength 6.55 for both sides from the next run on (`bdfa065`).
2. **Week 13 (the brief is drafted from your directions of 13 Nov):** spread-weighted damage, the remaining partly-modelled moves, and your team (already done ahead). Then Reg M-C, then the bot. Say go and it starts.
