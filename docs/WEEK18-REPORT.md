# Week 18 Report: a team on M-C, Fake Out read right, and damage read right

26 Nov 2026. Brief: Week 18, approved 23 Nov ("Agreed"; "Yes, choose a team
now").

## In short

**Phase 4 has its first answer, on Reg M-C.** Eight candidate teams played 80
games each with the engine on both sides; the top four then played 200 each.
Only one team's 95% interval sits wholly above 50%:

| Pool team | Wins (200 games) | 95% interval | Pokemon |
|---|---|---|---|
| **40** | **115 (57%)** | **51% to 64%** | Archaludon, Basculegion, Froslass, Kingambit, Salamence, Sneasler |
| 3 | 110 (55%) | 48% to 62% | Basculegion, Dragonite, Froslass, Garchomp, Kingambit, Sneasler |
| 11 | 109 (55%) | 48% to 61% | Archaludon, Basculegion-F, Floette-Eternal, Golisopod, Pelipper, Sneasler (rain) |
| 28 | 84 (42%) | 35% to 49% | Basculegion, Dragonite, Floette-Eternal, Gholdengo, Incineroar, Sneasler |

Teams 40, 3 and 11 are within a few games of each other; 28 is clearly weaker
in the bot's hands. Phase 4's gate is for the regulation the ladder pilot will
play, so on M-D this reruns with M-D's teams.

Three fixes made the engine read the game better:
- **Fake Out:** the opponent model expected it 33% of the time on a Pokemon's
  first turn out, where players use it 47%. The cause was one fitting setting.
  It now expects 47%, and the model predicts every kind of choice better.
- **Damage:** the estimate ran more than 10% low on 21% of hits; now 5.7%.
  The cause was how near-identical boards are merged, not the spread rule.
- **The clock:** the step that ran past the hard limit is found and can now
  be stopped part way; a Pokemon that must recharge is no longer searched.

Two rules were measured first and, by your call, not built: Tailwind valued
only by next turn, and long shots in nearly lost games. Reg M-D is still not
on Showdown.

## What was built

All committed on your computer, from `64d99f0` to `cba15bb`.

- **Choosing the team** (`64d99f0`). `--vs engine --team N`: the bot always
  plays the pool's team N; the engine plays each pool team in turn. `--table`
  ranks the candidates with 95% intervals. `--format regmd` runs the same tool
  on another regulation.
- **The recharge** (`bad9a8d`). After Hyper Beam, Showdown allows only the
  recharge; the advice offered the Pokemon's moves (40 of Week 17's 66
  replaced choices). On a gate position, that turn's advice went from about
  40 seconds to 5.
- **The hard limit's late step** (`fc1b66e`). Replaying the gate's late turns
  found it: one pair of plays can take 15 seconds to resolve (Hyper Voice and
  Rock Slide against Follow Me and Heat Wave: 985 boards), and valuing a
  thousand boards takes seconds more. Both now stop when the time is up.
- **The choice model's ridge** (`9925d26`). See "Fake Out" below.
- **Merged boards at their mean** (`64214fc`). See "Damage" below.
- **The bot against its earlier self** (`cba15bb`). `--vs before` loads last
  week's choice model and strength for the opponent.
- **CI on GitHub, green again** (`bb05b24`, `dd184e5`, `882e1a2`; your
  `05908e8` and `c6df2b0`). See Quality control.
- **Runbook section 31.**

## Your calls this week, and what they found

- **"Choose a team now"** (23 Nov): done on M-C, above.
- **Your Tailwind rule** (23 Nov), measured first. Where Tailwind could be
  set, 1500+ players set it 24% of the time when it makes one of theirs
  outspeed a foe, 19% when theirs already outspeed both foes on the field,
  and 5% when it is too slow even with Tailwind. The bot: 28%, 17% and 0%. A
  rule that counts only next turn would remove Tailwinds good players make.
  Your call: not built; today's late-Tailwind rule stays.
- **Long shots** (Task 3), measured first. In 150 games of 1500+ players, a
  player the win model gave under 5% won 0 of 89 times (5% to 15%: 2 of 77).
  On 20 such positions, choosing by the best chance of a 50% board found a
  real chance twice, each at a cost of 1 to 2 points. Not built.
- **Fake Out fix adopted, and the strength measured again** (your "Agreed").
- **Spread moves** (24 Nov): you set out the rule (reduced into two or more
  targets, full power into one). The resolver had it right; the fault was
  elsewhere.
- **Reading app games from video**: kept for a future week's brief.
- **The team choice's second round**, and the head-to-head after it.

## Fake Out (Task 2)

The choice model is a logistic model fitted with a ridge: a penalty that
pulls every weight towards zero. It was 0.01 for every choice, which is
strong for a play that appears in few choices: Fake Out's weight was held
down. At 1e-4, refitted on the same 2,000 training games:

| | Before | After |
|---|---|---|
| Fake Out on a first turn out: expected (1,430 validation choices) | 33% | 47% (used: 47%) |
| Mean log chance of the choice made (23,563 validation choices) | -1.915 | -1.875 |
| Likeliest option right | 30.0% | 29.8% |

The strength was measured again with it: 9.6 became 10.2, then 10.0 after the
damage fix. The strength by rating: 9.1 (9.0 before); by band, 8.3 under 1100,
7.9 from 1100 to 1299, 10.4 from 1300 to 1499, 9.9 at 1500 and up.

**In play:** the bot with the new model against itself with last week's, 200
games: **106 wins (53%, 95% interval 46% to 60%).** No difference 200 games
can show, and no sign of harm.

**Your game 626, turn 1:** the engine now expects the Fake Out (55% among its
likeliest replies, from 7%), and still prefers attacking: Protect is fifth, 4
points behind. What Sneasler surviving is worth shows only later in the game,
so the test stays marked to fail.

## Damage (Task 4)

On the 5% grid the advice uses, boards whose hit points share a cell are one
board, and the cell kept the first board's hit points. A hit's 16 damage rolls
mostly share a cell, so a hit read as one roll, most often the lowest:
Garchomp's Rock Slide into Mega Staraptor read 36 of 190 HP on every board,
where the rolls run 36 to 43 and the game showed 42. Merged boards now keep the
chance-weighted mean. On the bot's 200 games against the strongest move (both
sheets known):

| | Before | After |
|---|---|---|
| Estimate more than 10% too low | 21.3% of hits | **5.7%** |
| Estimate more than 10% too high | 9.8% | 7.4% |
| Real damage / estimate, typical | 1.01 | 1.00 |
| The board that happened among the engine's | 96.7% of turns | 96.6% |

## Quality control

- **The head-to-head's 200 games:** no crashes, illegal choices or timeouts;
  the hard limit once. A typical turn takes 34 seconds and the slowest 1% take
  45; a game uses about 187 of its 420 seconds.
- **The team runs' 1,440 games:** no crashes or timeouts. The hard limit
  answered 21 times in round 1's 640 games, before the late-step fix, and 5
  times in round 2's 800, after it (with six engines thinking at once).
- **Choices replaced by a legal one:** 20 of 1,905 in the head-to-head (1%).
  Not yet broken down now that the recharge is gone.
- **CI on GitHub** had not run since 6 November and failed on the first push.
  Five causes, one at a time: a missing space and three type-check complaints;
  the Champions Showdown never built in CI (your step); its Node version (your
  change to 22); five tests needing scikit-learn, which Python 3.10 does not
  install; and a timeout error on Python 3.10, where asyncio's is not yet the
  built-in one. That last was a real bug: on Python 3.10 the hard limit would
  have crashed. Your computer runs 3.14, so the bot never met it. **Two commits
  wait for your push** (`882e1a2`, `cba15bb`); then CI should be green.
- **The whole test suite on your computer** (26 Nov): 1,390 passed, 19
  skipped, and your game 626 turn 1 marked to fail, as expected.

## Surprises

- **Both "reading" bugs were in the plumbing, not the rules.** Fake Out was a
  fitting setting, and the low damage estimates came from merging boards. Each
  was a few lines, and each improved the engine's reading everywhere.
- **The best record among players was the worst team in the bot's hands.**
  Pool team 14 (1500+ players won 80% with it) came last in round 1, at 42%.
  Teams suit the bot differently; team choice has to be measured with the bot.
- **80 games a team was too few.** Team 28 looked tied for second at 55% after
  80 games and finished at 42% after 200.
- **Python 3.10 hid a real bug** behind a CI run nobody was watching.
- **The strength by rating took 14 hours,** not 9.

## Where the gates stand

- **Phase 3** is done (Week 17).
- **Phase 4:** on M-C, team 40 is the bot's team, with 3 and 11 close behind.
  The gate (the team chosen beats the field of top teams) is met on M-C by
  team 40 alone. It is for the pilot's regulation: if that is M-D, it reruns
  with M-D's teams.
- **Reg M-D** (carried again): checked 24 Nov, not on Showdown. M-D starts
  2 December.
- **This week's brief:** Tasks 1 and 3 measured and not built (your calls),
  Tasks 2, 4 and 5 done, Task 6 waiting for Showdown, Task 7 this report and
  runbook section 31.
