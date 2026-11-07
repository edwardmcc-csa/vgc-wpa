# Week 9 report: the choices, the opponent's likely reply, what can happen, decision versus luck (start of M5)

6 November 2026. Brief: `docs/WEEK9-DISPATCH.md`. Commits `1b34a23` to
`92a9e20`, plus this report. All numbers are per format and on the **validation
split** unless a line says training. The test split was not opened this week
(it has been opened 5 times, all logged).

## The headline

**The split works, and the first look is interesting, but it is not ready to
judge a player yet.** Every turn's swing now splits into your decision, their
decision and the dice (DEFINITIONS rev 8, §3), with cost against the best and
against the average choice beside it (§4).

- **The parts add up exactly**, at every decision point (largest error
  1.1e-16, against the 0.001 allowed). The plan's M5 tests pass: a critical hit
  goes to the dice and not to the decisions, and an obviously losing switch
  costs a lot against the best choice.
- **First look** (62 Reg M-A and 112 Reg M-B games, 2,414 decision points): a
  turn's swing is typically 16 to 17 points. Your decision, their decision and
  the dice are each typically 11 to 13. In this model, choices move win
  probability as much as luck does. The two big turns I checked against their
  replays read sensibly, and one of them exposed a missing input (Last Respects,
  Task 5).
- **Three things stop me from calling the numbers a verdict on anyone's play:**
  1. **The opponent model is a weak opponent.** Real replies beat its average
     reply by about 5 points a turn. So "your decision" averages +5.0 (Reg M-A)
     and +4.9 (Reg M-B) instead of about zero, and "their decision" -5.0 and
     -4.9. The split still adds up; its middle is in the wrong place.
  2. **Wobble.** The model's own noise is about 3 points (Task 6), six times the
     0.5-point threshold. A part smaller than about 5 points is within it. That
     decision is still open (below).
  3. **One spread per Pokemon.** The brief asked for spreads we cannot see to be
     averaged over. Each Pokemon gets its single most likely spread instead, and
     what that misses lands in the dice.
- **On your computer, the brief's full sample fits in a night:** 300 Reg M-A
  sets and all 199 Reg M-B sets, with cost against the best in a third of the
  games, in about 5 to 7 hours with 6 workers. The whole validation split does
  not: two to three days.

## Task 0: blank sheets with team preview

With `--blank`, the opponent's six species are now kept from team preview, in sheet
order. Their items, abilities and moves stay hidden until revealed, and their
natures and spreads stay hidden. Each side's bring odds come from those species.
Tests first (commit `1b34a23`). I rebuilt the blank table and retrained one-sided:

| validation | sets | full sheets (v4) | blank, team preview | blank, Week 8 | loss with team preview |
|---|---|---|---|---|---|
| Reg M-A | 5,167 | 0.1851 | 0.1887 | 0.1886 | +0.0036 (+0.0029 to +0.0043) |
| Reg M-B | 199 | 0.1678 | 0.1775 | 0.1781 | +0.0097 (+0.0062 to +0.0129) |

- **Both pass the calibration gate.**
- **Team preview makes no measurable difference.** Against Week 8's blank run,
  paired on the same rows: Reg M-A -0.0001 (-0.0004 to +0.0002), Reg M-B +0.0007
  (-0.0011 to +0.0023). The twelve species add almost nothing to what the model
  already gets from the board and the bring odds. It matches Week 8, where the
  likely back (group I) added nothing on its own.
- **The loss against full sheets is the same as Week 8's.** In Reg M-A, a
  closed-sheet game costs the model about half of what damage added in Week 7
  (-0.0071). In Reg M-B it costs more.

## Task 1: the choices on offer

`wpa/choices.py`. At each move-selection decision point, each active Pokemon gets:
- every move on its sheet with each legal target;
- Protect, with its chance of working;
- Mega Evolution where it is still available;
- a switch to each Pokemon on the bench.

A Pokemon locked by a Choice item gets only its locked move. A choice is one
option per active Pokemon, with impossible pairs removed: two switches to the same
Pokemon, or two Mega Evolutions.

**Real-data check** (a quarter of the logs, shards 0 to 15):

| | games | choices the log shows | in the list | not in the list |
|---|---|---|---|---|
| Reg M-A | 21,201 | 490,531 | 100.00% | 6 |
| Reg M-B | 1,021 | 24,399 | 100.00% | 0 |

The six misses are single cases: Volt Switch twice, then Hydro Pump, Thunder Wave,
Thunderbolt and Cotton Guard once each. I have not chased them; at 6 in 490,531
they change nothing this week.

A Pokemon that shows no choice is counted apart, not as a miss. In Reg M-A:
- 47,249 fainted before moving;
- 19,988 could not move (flinch, paralysis, sleep);
- 22,494 have no line at all, mostly because the game ended first;
- 6,209 show the move but not its target (it failed or was blocked);
- 1,366 were forced (Struggle, a locked move);
- 341 had transformed, 220 hit themselves in confusion, 488 had no target left.

**A typical decision point offers about 90 choices** (both active Pokemon
together): 90.3 in Reg M-A and 93.4 in Reg M-B on average.

## Task 2: what can happen this turn (M3, the resolver)

`wpa/resolver.py`. Given the board, both sides' choices and the spreads, it lists
every board the turn can end on, with its chance. The chances add up to 1.
- **Order:** switches, Mega Evolution, then priority (Prankster, Gale Wings and
  Triage included), then Speed. Speed includes Tailwind, Trick Room, paralysis,
  stat stages, and items and abilities through the calculator. A Speed tie is
  50/50.
- **Damage:** from the Smogon calculator. All 16 rolls and the critical hit are
  kept. Spread moves do reduced damage. Accuracy is included, and a Pokemon
  knocked out before it moves does not act. Rolls that leave the same hit points
  share one board.
- **Protect** works with chance 1/3 for each repeat. **Fake Out** makes its
  target flinch.
- **Field moves:** Tailwind, Trick Room, screens, weather and terrain start their
  timers as the durations table says.
- **Luck branches** for secondary effects: Speed drops, Snarl, burns, paralysis,
  flinches, multi-hit counts, and thawing.
- **Covered as well:** Intimidate on entry, Focus Sash, Sturdy, Sitrus Berry,
  Life Orb, recoil, drain, Follow Me and Rage Powder, Wide Guard and Quick Guard.
- **Added after the check below:** Armor Tail, Dazzling and Queenly Majesty stop
  priority moves; Psychic Terrain stops them at grounded targets; Lightning Rod
  and Storm Drain draw Electric and Water moves. Last Respects and Rage Fist mark
  the turn "partly modelled" (Task 5 shows why).

A turn that uses anything not modelled is marked "partly modelled" with the
reason. It is never treated as fully understood.

The plan's M3 tests pass: a known knock-out range, a 50/50 knock-out roll, an
accuracy check, a critical-hit branch, every list adding up to 1, and two rolls
that both leave the target standing giving two boards.

**Real-data check** (turns where the log shows every choice; 150 Reg M-A and 200
Reg M-B games):

| | turns | fully modelled | knock-outs right | board found |
|---|---|---|---|---|
| Reg M-A | 530 | **82.3%** | 92.5% | 56.8% |
| Reg M-B | 872 | **81.5%** | 95.2% | 66.5% |

- **The stop rule (70% of Reg M-A fully modelled) is passed.**
- **What is not modelled**, most common first: the switch-in after U-turn or
  Parting Shot, Encore, confusion, the Toxic counter, Leech Seed, Moody, sleep
  turns, Taunt and Substitute. Each is listed on the turn.
- **"Board found"** means every Pokemon's hit points are within 3 points of one
  of the resolver's boards. When a board is missed, the real hit points are
  higher than predicted twice as often as lower. That points to defenders being
  bulkier than the single most likely spread says. Refining spreads from the
  log's earlier hits barely changed it. A mixture over each Pokemon's likeliest
  spreads is the candidate fix (decision 3).
- **Speed:** median under 0.01 seconds a turn; a few turns with many luck
  branches take seconds. A cap merges boards on a coarser grid when there are too
  many, never dropping any chance.

## Task 3: what the opponent was likely to do

`wpa/policy.py`. For each active Pokemon it gives a chance to each of its options.
It is a conditional logit (like the bring model), learned from 1,500 Reg M-A and
2,000 Reg M-B training games (81,697 choices). It uses 22 facts per option:
- what kind of action it is (switch, Protect, status move, spread move, Mega
  Evolution, a Fake Out on the first turn or later);
- damage and knock-out chance against the target, and the target's hit points;
- how often that move is picked when it is on a sheet;
- whether the field effect is already up;
- for a switch: the hit points of the Pokemon coming in, whether it has been seen,
  how likely it was brought, and whether the one leaving is threatened.

**Validation, against a uniform guess over the legal options:**

| | choices | model | uniform | the choice made gets |
|---|---|---|---|---|
| Reg M-A | 23,561 | -1.888 | -2.440 | 1.74 times the uniform chance |
| Reg M-B | 8,826 | -1.922 | -2.461 | 1.71 times the uniform chance |

The figures are the mean log chance of the option actually chosen. The model's
likeliest option is the one chosen 31.3% of the time in both formats.

It beats a uniform guess clearly, but it is not a strong player. That matters in
Task 5. It learns, for example, that Protect, status moves, a first-turn Fake
Out and high damage are picked often, and that attacking your own ally is not.

It uses nothing from later in the game: cutting a game after a turn changes none
of the examples before it (tested).

## Tasks 4 and 5: decision versus luck, a first look

`wpa/attribution.py`. For each turn and each player:

- **E[WP | a choice]** is v4's win probability of every board the turn can end
  on. Their replies are weighted by the opponent model, and the rolls, critical
  hits, misses and Speed ties by the resolver.
- **The opponent's replies.** The brief allowed dropping the least likely
  replies while keeping 95% of the chance. **That does not work:** the opponent
  model spreads its chance thinly over about 90 pairs. In the first look, the
  likeliest 6 cover only 36% of it on average, and as little as 9%. So I took
  the likeliest 6 exactly and drew 6 more from the rest, in proportion to their
  chances. Nothing is dropped, and the drawn part has no lean (tested), only
  some noise.
- **A choice the log does not show** (a Pokemon that could not move or fell
  first, or a hidden target) is averaged with the opponent model.
- **Cost against the best and the average** compares the choice made with the
  player's 5 likeliest choices, in every third game.

The split is computed for both players at every turn; each player's three parts
add up to their own swing.

**First look.** Run here on the first 62 Reg M-A games (of the 300 sets' 526)
and 112 Reg M-B games (of 366), in the fixed order your full run will use. It
used the v4 models trained here on 20% of Reg M-A's training sets; your run uses
`models_v4_full`. "Typical size" is the root mean square, in points.

| | games | decision points | swing | your decision | their decision | the dice |
|---|---|---|---|---|---|---|
| Reg M-A | 62 | 886 | 16.0 | mean +5.0, typical 12.5 | mean -5.0, typical 11.5 | mean 0.0, typical 12.1 |
| Reg M-B | 112 | 1,528 | 17.1 | mean +4.9, typical 13.0 | mean -4.9, typical 12.6 | mean 0.0, typical 11.4 |

| | decision points compared | cost vs best, median | best choice taken | cost of 5+ points vs best | cost vs average, mean |
|---|---|---|---|---|---|
| Reg M-A | 318 | -4.7 | 14% | 49% | +1.3 |
| Reg M-B | 450 | -4.9 | 18% | 50% | +1.7 |

- **The parts add up** at every decision point: largest error 1.1e-16.
- **Choices move win probability as much as the dice do.** All three parts are
  typically 11 to 13 points; a turn's whole swing, 16 to 17.
- **"Your decision" is positive at about two-thirds of decision points**, and
  averages +5 points in both formats. "Their decision" mirrors it. By DEFINITIONS
  §3 it should average about zero. The reason is the opponent model: real replies
  are better than its average reply (decision 2).
- **Cost against the best is not believable yet.** Half of all choices would cost
  5 points or more against the best of the player's 5 likeliest. Two things inflate
  it. The best alternative is judged against the weak opponent model, and 5 points
  is under twice the model's wobble. Against the average, choices come out ahead
  (+1.3 and +1.7), which is the expected direction.
- **Their replies taken exactly:** 37% of the chance on average (lowest 10%) in
  Reg M-A, 36% (lowest 9%) in Reg M-B; the rest was drawn.
- **The board that happened was among the resolver's** in 77% (Reg M-A) and 76%
  (Reg M-B) of turns, to within 6 points of hit points. Where it was not, the
  dice are much bigger: typically 18.6 points against 9.3 in Reg M-A, and 14.7
  against 10.2 in Reg M-B. Part of the dice is the resolver missing, mostly on
  spreads, not luck.
- **A choice the log does not show** was averaged at 24% of decision points.
- **Left out:** 36 Reg M-A and 42 Reg M-B decision points, where the game ended
  by forfeit or on the timer during the turn.

**The 10 biggest swings per format**, for you to judge. Each turn appears once.
The first number is p1's swing; p2's is its opposite. Each player's split is
yours / theirs / dice, from their own side. "vs best" appears in the games with
alternatives.

**Reg M-A:**

| replay | turn | p1 swing | p1 | p2 | board found |
|---|---|---|---|---|---|
| [2631109433](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631109433) | 8 | -67 | -16 / -36 / -15 | +44 / +9 / +15 | no |
| [2622429388](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2622429388) | 7 | +58 | +34 / +15 / +9 | -11 / -38 / -9 | no |
| [2590847741](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590847741) | 4 | -57 | +1 / -53 / -4 | +64 / -11 / +4 | no |
| [2631109433](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631109433) | 6 | +54 | +23 / -0 / +31 | -2 / -21 / -31 | yes |
| [2619891782](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2619891782) | 5 | +51 | -0 / -4 / +55 (vs best -23) | +7 / -3 / -55 (vs best -13) | yes |
| [2610174008](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2610174008) | 6 | +49 | +15 / +33 / +1 | -29 / -19 / -1 | yes |
| [2590437251](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590437251) | 6 | -49 | -21 / -28 / +1 (vs best -45) | +37 / +13 / -1 (vs best +0) | yes |
| [2616594736](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2616594736) | 5 | +48 | +35 / -18 / +31 (vs best +0) | -5 / -13 / -31 (vs best -14) | yes |
| [2631247508](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631247508) | 18 | +48 | -7 / +0 / +55 | +10 / -3 / -55 | yes |
| [2631108243](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631108243) | 7 | +47 | +31 / +17 / -0 (vs best -2) | +21 / -69 / +0 (vs best -2) | yes |

**Reg M-B:**

| replay | turn | p1 swing | p1 | p2 | board found |
|---|---|---|---|---|---|
| [2635540746](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635540746) | 11 | +70 | -6 / +0 / +77 | +6 / -0 / -77 | yes |
| [2635761330](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635761330) | 9 | -67 | -11 / -33 / -23 | +48 / -3 / +23 | yes |
| [2635245550](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635245550) | 4 | +64 | +57 / -5 / +11 (vs best -1) | -33 / -19 / -11 (vs best -33) | yes |
| [2635487694](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635487694) | 8 | -62 | +18 / +8 / -87 | -16 / -10 / +87 | no |
| [2634644603](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634644603) | 7 | -61 | -3 / -5 / -53 | +31 / -23 / +53 | yes |
| [2635761330](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635761330) | 8 | +59 | +24 / +28 / +7 | -68 / +16 / -7 | yes |
| [2635191518](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635191518) | 12 | +59 | +22 / +0 / +37 | -1 / -21 / -37 | yes |
| [2635849694](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635849694) | 6 | +55 | -1 / -17 / +73 (vs best -18) | +20 / -2 / -73 (vs best -1) | yes |
| [2635059618](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635059618) | 5 | -55 | +2 / -22 / -34 | -9 / +29 / +34 | yes |
| [2634539446](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634539446) | 4 | -54 | -25 / -17 / -11 | +50 / -8 / +11 | yes |

**Time.** Measured per turn, both players together. One core here and one core
of your computer took about the same time on the same turns.

| | per turn, no comparison | per turn, with cost against the best |
|---|---|---|
| Reg M-A | 8.2 s | 16.3 s |
| Reg M-B | 5.4 s | 23.6 s |

- **The brief's sample on your computer** (300 Reg M-A sets and 199 Reg M-B sets,
  about 6,300 turns, the comparison in a third of the games): about 19 hours of
  one core. With 6 workers that is about 3 hours in theory. Allowing for a laptop
  slowing when all its cores are busy, it is **5 to 7 hours: it fits in a night.**
- **The whole validation split** (about 64,000 turns, nearly all Reg M-A) is about
  145 core-hours without the comparison, and 200 with it in a third of the games.
  That is **two to three days on your computer; it does not fit in a night.** A
  sample of the Reg M-A sets would.
- **A few turns are slow:** the slowest took about 5 minutes, when many luck
  branches meet many choices.

### How to read a line

Reg M-B, [game 2635182603, turn 10](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635182603),
from the first look (not in the top 10 above). p1 went from 52% to 6%:

- **What happened:** p2's Kingambit used Sucker Punch, scored a critical hit and
  knocked out p1's Swampert. p2's Lycanroc used Rock Slide on Venusaur, and
  Venusaur's Sleep Powder missed Lycanroc.
- **p1: yours -6, theirs -26, dice -13.** p1's choice was a little below what
  the position usually gives. Swampert fell before moving, so its choice was
  averaged. p2's actual reply was 26 points better for p2 than its likely
  replies: they read the turn well. The critical hit and the miss cost p1 13
  points.
- **p2: yours +32, theirs +1, dice +13.** The same turn from p2's side: most of
  its gain is its own choice.

And the top Reg M-B line shows why the dice need care. In game 2635540746, turn
11, p1's Basculegion used Last Respects and won, and the dice got +77 points. That
was not luck: Last Respects gains power for every fainted ally, and the calculator
was not told how many had fallen. The resolver gave the knock-out a 23% chance
when it was certain. Such turns are now marked "partly modelled" (commit
`92a9e20`). Passing the count to the calculator is a Week 10 fix.

## Task 6: how much win probability wobbles

`wpa/wobble.py`. v4 retrained on three resamples of the training sets. Then I
measured how far win probability moves on the same validation positions:

| | positions | level, median | level, 90th percentile | swing, median | swings over 0.5 points |
|---|---|---|---|---|---|
| Reg M-A | 173,070 | 3.2 points | 7.4 | 3.2 points | 95% |
| Reg M-B | 7,477 | 3.1 points | 7.5 | 3.0 points | 96% |

"Level" is win probability at a position; "swing" is the change from one
decision point to the next, which is what the report would show. Both are about
six times the 0.5-point threshold in DEFINITIONS §10.2. As things stand, the
report would show noise as insight. This is decision 1 below.

## Surprises

- **The opponent model is the weak link in the split.** I expected the dice to
  be the noisy part. Instead, "your decision" leans positive at about two-thirds of
  decision points, because real replies are better than the model's average
  reply. The split adds up, but where its middle sits depends on how good the
  opponent model is.
- **The opponent's chance is spread thin.** With about 90 pairs on offer and the
  likeliest 6 covering about a third of the chance, "keep 95%" would have meant
  resolving most of them. Drawing the rest was the way through.
- **A thread pool cost seconds a call.** The win-probability model started its
  thread pool for every small batch: 3.7 seconds a call on a busy machine,
  against 9 milliseconds on one thread. Fixed by using one thread and one batch
  per turn. Remembering repeated damage questions halved the rest (the same
  feature rows, checked on 822 rows).
- **The board after a turn matches the next turn exactly.** Where no Pokemon
  fell, v4's value of the resolved board equals its value at the next turn's
  start. The resolver and the decision table describe a board the same way.
- **Where a Pokemon fell, they do not.** The board after the turn has an empty
  slot, and the value moves again when the replacement comes in. That move is
  the forced-switch decision, out of scope this week (Week 10), so per-turn
  swings do not yet add up to a whole game.
- **The biggest "luck" in Reg M-B was a missing input.** Last Respects' power
  depends on fainted allies, which the calculator is not told (Task 5).
- **The calculator does not know Amoonguss in Champions.** It turned up in a
  test, not in the data.

## What went wrong, and was caught

- **Two test fixtures were wrong, not the code.** The Psychic Terrain test first
  used Flare Blitz, whose recoil hurt the attacker the test watched. The losing
  switch test first used Amoonguss, which the calculator does not know. Both
  were fixed in the tests; the code was unchanged.
- **A blank in the split.** Four Reg M-A decision points came out as "not a
  number". The cause: Roar aimed at the user's own ally after that ally had
  fallen earlier in the turn. Roar moves last, so it had no target, and the
  resolver dropped the board instead of keeping it. Fixed test-first; those two
  games were redone. The split now stops with an error, never a blank, if a
  pair has no boards.
- **The first timing run did not finish 2 turns in 10 minutes.** The cause was
  the thread pool above.
- **A background job hit the 2-hour limit** in the middle of training the
  team-preview model. Training saves its progress, and it carried on.

## Process notes

- Tests came first for most of this week's code: the choices, the resolver's
  golden cases and mechanics, the opponent model, and the split. **Three
  exceptions:** the resolver's board-merging and cap test, the opponent model's
  example tests, and its cut-the-game test were all written after the code. All
  pass.
- **How I read one M5 test.** "Only a critical hit differs: the decision part is
  about 0." The test plays the same turn twice, with and without the critical
  hit. Your decision and their decision come out identical both times, and the
  difference goes wholly to the dice. The choice's cost against the best is 0,
  because it was the best choice. Your decision itself is not 0 there: it also
  measures the choice against what the position usually gives.
- One of the opponent model's 22 facts, the hit points of the Pokemon choosing,
  is the same for all of that Pokemon's options, so it cannot change any chance.
  The fit gave it a weight of 0. It is harmless, and it should be combined with
  the option type next time.
- The full suite: 595 passed, 3 skipped. The same 15 test files cannot load on
  the development machine (bot libraries). ruff and pyright are clean on this
  week's files.
- The test split has been opened 5 times. Not opened this week.

## Decisions for the product owner

1. **Wobble** (Task 6; asked earlier, still open). Options:
   - **(a)** Average 5 to 10 models trained on resamples. Noise falls roughly
     with the square root of their number (about 1 to 1.4 points). It costs 5
     to 10 times the training and the scoring.
   - **(b)** Raise the reporting threshold to about 3 points.
   - **(c)** Both.

   I recommend (c). Use (a) for the numbers we show, and (b) as the rule for
   what is worth showing.
2. **The opponent model is too weak an opponent.** Options:
   - **(a)** Make it sharper, with one setting fitted on training games so that
     "your decision" averages about zero, as DEFINITIONS §3 expects.
   - **(b)** Let it weigh each reply by how good the reply is for the opponent.
     This is better, but each turn costs several times more.
   - **(c)** Leave it, and say in the report that "their decision" is measured
     against an average opponent, not a strong one.

   I recommend (a) now and (b) later.
3. **Spreads.** Today each Pokemon gets its single most likely spread. Should
   Week 10 average over the 2 or 3 likeliest, as the brief asked? Each one
   multiplies the time per turn. I recommend it for the resolver, where misses
   come from bulk, and measuring the cost first.
4. **The full sample on your computer** (runbook Section 18, step 2): one command,
   overnight. Then the 10 biggest swings per format come from the brief's whole
   sample, scored with `models_v4_full`.
5. **The replies method.** The brief allowed dropping up to 5% of the chance; I
   drop none and draw instead. I recommend keeping this. It is the default
   (`--top 6 --draws 6`).
