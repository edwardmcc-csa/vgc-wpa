# Week 17 Report: on time every turn, and fewer misplays

23 Nov 2026. Brief: Week 17 (Phase 3, part 2), approved 20 Nov.

## In short

**Phase 3's gate is met.** On the local server, Reg M-C, closed team sheets,
600 games:

| Against | Wins | 95% interval | Bar | Timeouts | Refused choices |
|---|---|---|---|---|---|
| Random choices | 196 of 200 (98%) | 95% to 99% | 90% or more: met | 0 | 0 |
| The strongest move | 151 of 200 (76%) | 69% to 81% | over 55%: met | 0 | 0 |
| The choice model | 189 of 200 (94%) | 90% to 97% | better than even: met | 0 | 0 |

Week 16 had 48 late turns and 211 refused choices; this week, none of either.
A typical turn now takes 36 seconds and the slowest 1% take 44; a typical game
uses 150 to 180 of its 420 seconds. No game crashed.

Beyond the clock, the week fixed what your games found: a bug that read
Electro Shot in rain as still charging, PP that was never counted, team
preview that never looked at your six, Fake Out offered after a Pokemon's
first turn, and late Tailwind. Two of your games are now tests the engine
must pass.

## What was built

All committed on your computer, from `d4ab5bf` to `5d20b30`.

- **A charge that goes off at once** (`d4ab5bf`). In rain, Electro Shot
  charges and hits in the same turn; the board kept the Pokemon "charging",
  so the engine thought Electro Shot was its only move. It was behind your
  9:34 pm game's turn 7 exactly. One Reg M-C game in five has such a turn.
- **On time, every turn** (`9e9b243`). The step that ran late (weighing your
  replies against one of the bot's plays, up to 145 seconds) now looks at the
  clock between pairs. With nothing valued, the likeliest play goes at once.
  A hard limit sends a legal choice 50 seconds into a turn whatever the
  advice is doing, and a choice for a request that has passed is never sent,
  so one late turn cannot put the bot out of step.
- **Shortcuts** (`d2eaaa5`, `d0d91d0`, `6a4d7fa`, `20ea0e8`). Fake Out and
  First Impression after a Pokemon's first turn out are left out, for both
  sides. Tailwind when the other side has one Pokemon left is valued last and
  loses a near tie (within a point of win chance) to any other play. Your
  cases (Sneasler's White Herb Close Combat, U-turn out of Perish Song,
  status into a Sucker Punch user, Yawn to punish a switch, Tailwind or a
  weather move to play around a switch-in) all stay possible.
- **PP** (`a548a33`). Counted on the board and in the resolver, from each
  format's own rule: Champions gives Protect 8 PP. A move with none left is
  not offered, and Encore fails on it.
- **Team preview against your six** (`49f2f12`). The back two are chosen with
  a matchup term: how often each Pokemon is brought against each of the
  opponent's species, from training games.
- **Two places to fill and one Pokemon left** (`b9bd8c4`): the bot sent a
  random switch-in 75 times in the weekend's 800 games; now it sends the one
  it has.
- **Your games as tests** (`5d20b30`): game 626 turn 7 and game 629 turn 15
  pass; game 626 turn 1 (Protect Sneasler against the Fake Out) is marked to
  fail until the Fake Out reading is fixed.
- **Runbook section 30.** Your computer's whole suite passed before the gate
  run (1,355 tests).

## Your calls this week, and what they found

- **The retrain** (your yes, 19 Nov): nothing to change. The win model's
  inputs came out byte for byte the same (the charge is not one of them), and
  the retrained choice model scored no better on the same validation games
  (30.0% against 30.2% for the likeliest option). Today's models stay; the
  fix matters during play.
- **The shortcuts' proof:** the bot with them against itself without, 93 of
  200 (46%, 40% to 53%): no difference 200 games can show. Without them the
  engine twice sent a late Fake Out, which Showdown refused. Your call: keep
  the late Fake Out removal; the general "value last" order is off.
- **Tailwind and weather moves** stay possible (your call, 20 Nov).
- **Late Tailwind** (your yes, 23 Nov): replayed on 8 of the gate's late
  Tailwinds, 7 now play something else, each within 0.2 points.

## Measured (Tasks 3 and 4)

On the bot's 600 gate games, against 1500+ players in 439 Reg M-C validation
games:

| | The bot | 1500+ players |
|---|---|---|
| Protect right after its own Protect | 12.3% of Protects | 12.4% |
| Electro Shot that charged (no rain) | 9% of its Electro Shots | 36% |
| Tailwind, with one foe left, as a share of moves | 2.4% (its usual rate) | 1.0% (their usual: 2.1%) |
| Fake Out on a first turn out (42 positions) | expected 33% | used 48% |

So the bot protects twice no more often than good players, and charges
Electro Shot without rain less; your examples were turns where it was wrong
in context. The gaps are late Tailwind (now fixed) and Fake Out, which the
opponent model under-expects and cannot tell apart from when it does not
come. In your two games the weighing step cut Fake Out further (to 6% and
22%); over the 42 positions it did not, on average.

Team preview: on 10,150 Reg M-C validation sides whose four the log shows,
the four rated likeliest is the one brought 17.8% of the time, against 9.7%
before (a guess: 6.7%); among the winners, 19.9% against 10.1%. In your mirror
game the back two become Raichu and Basculegion-F, where the bot brought
Pelipper and Basculegion-F.

## Quality control

- **Hard limit:** used 5 times in the 600 gate games (and 4 in the 200
  head-to-head), each a legal choice in time. Each time, the search's thread
  ran on to 70 to 75 seconds before it stopped: one step after the deadline
  ran about 25 seconds long. Not yet found which.
- **Choices replaced by a legal one:** 66 in the 600 games (about 1% of
  choices). 40 were a Pokemon that had to recharge after Hyper Beam (mostly
  Sylveon): the advice offered it moves, and Showdown's only choice was the
  recharge, so the turn played out the same, but the search was wasted.
  17 were the forced-switch error now fixed, and 5 the hard limit.
- **Its win chance runs low against these opponents:** when it rated itself
  50 to 60%, it won 94% against the choice model. Expected, since the
  opponents are weaker than the players it learned from.
- **Open from Week 16:** the damage estimate ran low on 27% of hits in the
  bot's games. Not looked at this week.

## Surprises

- **My own two mistakes cost a day.** The first gate run hung: the script
  started the server before the tests, and one test plays a live battle when
  it finds a server. Then the choice-model opponent failed on every turn: the
  clock fix changed how a turn is answered, and its own version was never
  updated (no test covered it). Both are fixed and tested, but the first 200
  choice-model games did not count.
- **The retrain changed nothing.** The bug was real, but the win model never
  saw the charge.
- **A simple matchup term doubled team preview's hit rate.** The bring model
  had only ever looked at the player's own six.
- **The bot's Protect habits are a good player's.** The rate of a second
  Protect matched 1500+ players almost exactly.

## Where the gate stands

Phase 3 is done: all three win-rate bars met, no timeouts, no refused choices,
no crashes. Not done this week: Reg M-D (Task 6), because Showdown has neither
the M-D format nor the December balance patch yet; it carries to Week 18. The
long-shot rule for nearly lost games also moves to Week 18.
