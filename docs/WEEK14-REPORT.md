# Week 14 report: Reg M-C, part 1 (the rules, the data, the format)

15 November 2026. Brief: `docs/WEEK14-DISPATCH.md`. Commits `055b4b0` to `29ba7da`, plus this report. All numbers are per format and on the **validation split**: the resolver check's 1,567 games, of which 675 Reg M-C games are new this week. The test split was not opened this week; it has been opened 5 times, all logged.

**Every task's boxes are ticked.** One decision is yours (the cap, below). The tests pass: 1,053, with 12 skipped as slow. The 15 files that need the battle harness's libraries were not run, and none of them changed.

## The headline

- **Reg M-C is in, as a third format.**
  - 60,000 best-of-three games came from Showdown's public replays, 8 Oct to 14 Nov, with both team sheets in all of them.
  - Smogon's September and October statistics came with them.
  - The games were parsed and split by set inside the format. **No Reg M-A or Reg M-B game moved**: 0 of 88,901.
- **The resolver check on Reg M-C, at the first try:**
  - **99.9% of turns are fully modelled.** 4 turns of 4,984 are modelled in part.
  - **The board that happened is found on 90.0% of turns.** Reg M-A is at 87.1% and Reg M-B at 90.1%.
  - This is the same check as the other two formats, on 300 of M-C's validation sets.
- **Half of all HP misses come from the resolver's cap, in every format** (found this week). Above 300 boards, the resolver merges them on a coarser grid, and a miss there can be the grid rather than a rule.
  - The turns it touches are 14–17% of all turns. **Only 66–68% of them are found, against 91–94% of the rest.**
  - **With a cap of 3,000, found goes up 3–4 points in every format**: 87.1% → 91.0% (M-A), 90.1% → 93.1% (M-B), 90.0% → 92.9% (M-C).
  - HP misses fall by a third: 387 → 249, 227 → 148, 424 → 280.
  - The resolver takes 30–59% more time per turn.
  - **With it, Week 13's HP gate is met:** HP misses are down 52% and 55% from Week 13's start, against a third asked.
- **Three rules were missing in every format, and none was marked.** All are now modelled:
  - Dragon Tail and Circle Throw dragged no one.
  - Grassy Glide had no priority on Grassy Terrain.
  - A bind went on after the Pokémon that bound it had fainted.
- **One game hung the overnight check for hours.** A Pokémon left and came back in the same turn, and the map of who replaced whom went in a circle. It is fixed (`034f773`), with a test that hung before the fix.

## The resolver check

Code `60b8665`, every hit weighed over the spreads players run (as since Week 13), on your computer overnight with 6 workers. Reg M-A and Reg M-B are set against Week 13's last full run (`b0219dc`).

| | Reg M-A, Week 13 | Reg M-A, now | Reg M-B, Week 13 | Reg M-B, now | **Reg M-C, now** |
|---|---|---|---|---|---|
| turns checked | 3,628 | 3,628 | 2,614 | 2,614 | **4,984** |
| fully modelled | 99.9% | 100.0% | 100.0% | 100.0% | **99.9%** |
| board found | 87.1% | 87.1% | 89.9% | 90.1% | **90.0%** |
| both | 87.1% | 87.1% | 89.9% | 90.1% | **89.9%** |
| both, turns with a knock-out | 88.4% | 88.5% | 90.9% | 91.0% | **90.6%** |
| misses: HP only | 387 | 387 | 231 | 227 | **424** |
| on the cap's coarser grid | – | 200 | – | 111 | **222** |
| misses: a knock-out differs | 80 | 80 | 32 | 31 | **75** |
| real damage / estimate, median (clean hits) | 0.98 | 0.98 | 0.99 | 0.99 | **0.99** (547 hits) |
| resolver time per turn | 0.83 s | 0.90 s | 0.52 s | 0.57 s | **0.68 s** |

The table leaves out 1 Reg M-C game (the one that hung, below).

- **With this week's rules, Reg M-C is as well modelled as the other two formats from its first run.** The rules this week touched M-A and M-B only a little: M-B gained 0.2 points.
- **Modelled in part on Reg M-C:** Acupressure (2 turns), Healing Wish, Pain Split, and a move aimed at an Ally Switch user's place (1 turn each). In M-A, one Wish turn; in M-B, one Instruct turn.
- **The damage estimate has no bias on Reg M-C either.** On 547 clean hits, the median of real damage against the estimate is 0.99. The estimate is too high by over 10% in 25% of hits and too low by over 10% in 24%.

## The cap

**What it is.** The resolver keeps at most 300 boards a turn. Above that, it merges boards on a coarser hit-point grid (up to 40 points wide), keeping the first board's hit points in each cell. The cap is there to keep the check and the advice fast. The check now records which turns the cap coarsened (`60b8665`), and the table counts the misses on them.

| | turns | coarsened by the cap | found, coarsened | found, the rest | HP misses on coarsened turns |
|---|---|---|---|---|---|
| Reg M-A | 3,628 | 610 (16.8%) | 66.1% | 91.4% | 200 of 387 |
| Reg M-B | 2,614 | 366 (14.0%) | 68.0% | 93.7% | 111 of 227 |
| Reg M-C | 4,984 | 695 (13.9%) | 67.1% | 93.7% | 222 of 424 |

**A test of a larger cap.** I took 23 of Reg M-C's HP misses on coarsened turns at random and checked them again with a cap of 3,000. 16 were found. Of the 7 left, 2 were still coarsened, and 5 were real misses that a finer grid does not reach.

**The whole check with a cap of 3,000** ran on your computer this morning (`034f773`: today's code, whose one change is the fix for the hang). The table leaves out the game that hung, so both runs cover the same 674 Reg M-C games.

| | Reg M-A, 300 | Reg M-A, 3,000 | Reg M-B, 300 | Reg M-B, 3,000 | Reg M-C, 300 | Reg M-C, 3,000 |
|---|---|---|---|---|---|---|
| board found | 87.1% | **91.0%** | 90.1% | **93.1%** | 90.0% | **92.9%** |
| both, turns with a knock-out | 88.5% | 91.9% | 91.0% | 93.7% | 90.6% | 93.5% |
| misses: HP only | 387 | **249** | 227 | **148** | 424 | **280** |
| on the cap's coarser grid | 200 | 30 | 111 | 17 | 222 | 39 |
| misses: a knock-out differs | 80 | 77 | 31 | 32 | 75 | 72 |
| turns found / lost against 300 | | +141 / −0 | | +82 / −4 | | +150 / −3 |
| turns still coarsened | 16.8% | 4.5% | 14.0% | 2.9% | 13.9% | 3.6% |
| resolver time per turn, mean | 0.90 s | 1.43 s | 0.57 s | 0.74 s | 0.68 s | 1.00 s |
| the slowest 1% of turns, from | 13.5 s | 19.9 s | 9.7 s | 14.2 s | 10.7 s | 17.2 s |

- **The whole check took 39 minutes, against 25.** The time is in the few turns the cap touches. The median turn takes 0.04 seconds either way. One Reg M-A turn took 14 minutes at 3,000 (7 minutes at 300).
- **The damage estimate is still unbiased:** the median real damage against the estimate is 0.99–1.00 in every format.
- **Week 13's gate on HP misses.** It asked for a third fewer than at Week 13's start, which would be 348 or fewer in M-A and 217 or fewer in M-B.
  - At a cap of 3,000 it is met: 522 → 249 (−52%) in M-A, 326 → 148 (−55%) in M-B.
  - At 300 it is not: 387 and 227.

**What the cap is for.** The resolver check measures whether the rules are right. A coarse grid hides that, so the check should use the larger cap. The bot's advice is different: it runs many of these per turn against a clock of 55 seconds a turn and 7 minutes a game. Its cap belongs to Phase 3's work on the clock. Nothing changes until you decide (below).

## Task 1: Showdown's code for Reg M-C

- **A second pinned copy, `pokemon-showdown-mc`** (Showdown's own, `7e74376`, 13 Nov), beside the June copy. `055b4b0`.
  - M-A and M-B keep the rules their games were played under. Showdown's current code dropped M-A's on 9 September.
  - The version check covers both copies. It was built on your computer on 14 Nov.
- **Each format reads its rules from its own copy:** the dex, the moves, and the durations of timed effects (`b93f0ad`, DEFINITIONS revision 12, which you approved on 14 Nov).
- **The damage calculator** knows every Reg M-C species, Mega, ability, item and move seen on the sheets. Two gaps are now handled beside it, with tests (`f7d173d`):
  - Flash Fire's and Stakeout's boosts have to be switched on per hit. They are now passed.
  - Its Champions rules leave out an ally's Steely Spirit. The bridge now does it on the move's power, as Showdown does.
- **Runbook §27:** the steps for Reg M-C and a checklist for the next regulation (`ebdbec4`, `4007c0a`).

## Task 2: what we got

**The download** (`5de4c1c`, `7163913`): 60,000 Reg M-C best-of-three games from Showdown's public replays, newest first.

- **Time:** 9 hours on your computer, at 3 requests a second.
- **Failures:** no request failed, and 12 games without both sheets were left out.
- **Statistics:** Smogon's September and October statistics for Reg M-C and its best-of-three came in the same run.

| | |
|---|---|
| dates | 8 Oct to 14 Nov 2026 (the cap of 60,000 was reached before September) |
| games per week | 7,115 (part of the week of 5 Oct), 14,555, 11,042, 9,197, 8,740, 9,351 (to 14 Nov) |
| sets | 27,120: 9,543 with three games, 13,794 with two, 3,783 with one (the rest not uploaded, or outside the dates) |
| players | 8,851. The median player has 4 games; 965 have 1. The three busiest have 3,183, 2,312 and 2,163 games: together, about 13% of all games. |
| ratings | Only 21,882 games (36%) carry one. Median 1,174; 10% are under 1,035, 10% over 1,371; 308 games at 1,500 or more, 5 at 1,700 or more. |
| from Smogon's tournament server | 76 games (the parser cannot read their tags) |

**The rules checks**, on all 120,006 team sheets:
- **All pass:** six Pokémon on each sheet, all at level 50, no species twice, no item twice.
- **The bring:** every one of the 120,000 sides brought at most four.

**What M-C teams run** (share of teams):

| | |
|---|---|
| Sneasler | 41.0% |
| Rillaboom | 36.6% |
| Incineroar | 33.1% |
| Garchomp | 31.3% |
| Kingambit | 27.9% |
| Raichu | 26.1% |
| Archaludon | 21.5% |
| Charizard | 21.2% |
| a terrain Seed | 46.0% |
| Golisopod (Emergency Exit) | 14.9% |
| a Flash Fire Pokémon | 3.6% |

**Two things to keep in mind for Week 15:**
- **The ladder these games come from is mostly below your target.** Few rated games are near 1,750.
- **A few accounts play a large share of the games.** The models should be checked for leaning on them.

## Task 3: Reg M-C as a third format

- **DEFINITIONS revision 12**, approved 14 Nov (`5d285c1`):
  - three formats;
  - adding a format never moves another format's sets;
  - each format's rules from one pinned copy.
- **The parse:** 118,702 of 120,000 game-sides (98.9%). The 1,298 that failed are all in the battle harness's own parser, which we do not change:
  - 848 are forfeits before turn 1, which have no turns to analyse.
  - 295 are Zoroark-Hisui's Illusion: a move shows under the Pokémon it is disguised as.
  - 152 are the 76 games from Smogon's tournament server, whose tag the parser cannot read.
  - 3 are other errors.
- **The splits**, by set inside the format (`b114bbe`):

  | | sets | games |
  |---|---|---|
  | train | 21,573 | 47,621 |
  | validation | 2,733 | 6,061 |
  | test | 2,621 | 5,789 |

  Checked against a copy taken before: **0 of 88,901 Reg M-A and Reg M-B games moved.**
- **What an M-C sheet shows:** nature, as in M-B (`b14f672`, `docs/SHEET-FIELDS.md`).
- **The check's sample:** every game of 300 Reg M-C validation sets (675 games), added to the saved sample with M-A's and M-B's unchanged (`29ba7da`).

## Task 4: the rules Reg M-C adds

Each rule is checked against Showdown's Champions data, with a test first, shown failing (`3760d8f`, `2671ff9`, `f7d173d`, `60b8665`, `034f773`). The order followed what the first 6,129 downloaded games showed was common.

- **Emergency Exit** (Golisopod, on 15% of teams). When a hit or the end of the turn takes it from above half its HP to half or less, it switches out. The forced-switch model picks who comes in, as after Eject Button, and its own move that turn is lost. It was marked before.
- **Abilities:**
  - Thermal Exchange; Seed Sower; Moxie; Stakeout; Flash Fire's boost.
  - Those that take in a move: Volt Absorb, Water Absorb, Sap Sipper, Earth Eater, Motor Drive and Lightning Rod's boost.
  - Those that keep a status off; Liquid Ooze; Guard Dog and Suction Cups; Harvest.
  - Aura Guard, Punk Rock and Grass Pelt were already in the calculator; I checked each.
- **Items:** Air Balloon popping; the four terrain Seeds (on 46% of teams); Red Card; Eject Button's switch-in; Normal Gem; Leek.
- **Moves:** Meteor Assault's recharge, Glaive Rush, Revival Blessing, Milk Drink on an ally and Court Change.
- **Not needed or left marked:**
  - Run Away and Jaw Lock's trap need nothing, since the resolver takes each switch as chosen.
  - Octolock stays marked: 2 of 12,258 sets.
- **Found on the way, in every format:**
  - Dragon Tail and Circle Throw now drag the target out.
  - Grassy Glide has +1 priority on Grassy Terrain for a grounded user.
  - A bind ends, with no damage, once the one that bound it has fainted or left. The board keeps who bound it.
- **The hang** (`034f773`). On one Reg M-C game, Golisopod left by Emergency Exit and came back in the same turn. The map of who replaced whom went in a circle, and the check waited on that game for hours.
  - The other 1,566 games were done by 11:38 PM. The fixed code checks that game's 6 turns in 3 seconds.
  - Two pivots in one turn could do the same in M-A or M-B.

## Surprises

- **The cap, not the rules, was the largest single cause of HP misses**, in all three formats. Week 13 put about a quarter of HP misses on "the grid and the cap"; recording it per turn shows half. Week 13's quick test of ten times the boards found 12 of 94 misses. It picked misses by where the boards fell, not by whether the cap had touched the turn.
- **Reg M-C needed no new kind of work.** It came in at 90% found on its first run. The engine and the per-format setup carried over, and the runbook's steps ran unattended overnight.
- **Three rules were missing in every format for weeks, and none was marked:** Dragon Tail, Grassy Glide's priority, and a bind outliving its source.
  - Dragon Tail turned up while I wrote Guard Dog's test.
  - The other two turned up in a dry run of the overnight steps on 300 real M-C games.
- **The download stopped at 8 October.** It ran 9 hours without a failure, and the 60,000-game cap was reached before September, so September is not in the corpus.
- **A dry run caught nothing broken in the overnight steps.** It did find two of the three rules above. It did not catch the hang: that needed one game in 60,000.
- **Terrain is everywhere in Reg M-C.** 46% of teams hold a terrain Seed and 37% bring Rillaboom, which is why Grassy Glide's priority mattered.

## For you

1. **Decide the resolver check's cap:**
   - **(a) 3,000 from now on.** This is my suggestion. The check then measures the rules rather than the grid, the HP gate is met, and the check takes 39 minutes instead of 25.
   - **(b) Keep 300.**

   Either way, the bot's advice keeps 300 until Phase 3 measures its clock.
2. **Close the overnight PowerShell window** of the Reg M-C steps. It is still waiting on the game that hung, which keeps one core busy. Closing it loses nothing: everything else it did is saved, and I made its last step (the table) myself.
3. **Next, Week 15:** the models retrained on Reg M-C (win probability with sheets shown and hidden, choices, bring, leads, replacement, the opponent's strength) and Phase 2's gate.
