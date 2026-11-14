# Week 13 report: damage over the spreads players run, the last rules, your team (M5 part 5)

14 November 2026. Brief: `docs/WEEK13-DISPATCH.md`. Commits `189aac7` to `fde5ac3`, plus this report. All numbers are per format and on the **validation split** (the resolver check's 892 games: 3,628 Reg M-A turns, 2,614 Reg M-B turns). The test split was not opened this week (it has been opened 5 times, all logged).

**Every task's boxes are ticked.** The tests pass (940, 12 skipped as slow; the 15 files that need the battle harness's libraries were not run, and none of them changed). **The gate is half met:** moves modelled in part are well under 0.5% of turns in both formats, but HP misses fell by a quarter, not a third.

## The headline

- **The resolver now finds the board that happened on 87.1% of Reg M-A turns and 89.9% of Reg M-B turns**, up from 83.0% and 85.9% at the start of the week. Fully modelled and found: 81.4% → 87.1% (Reg M-A), 85.3% → 89.9% (Reg M-B).
- **Gate, moves modelled in part: met.** 2.23% → 0.03% of turns (Reg M-A), 1.07% → 0.04% (Reg M-B). Every rule the brief listed is now modelled; one turn is left in each format, in two rules that came up after the brief.
- **Gate, HP misses down by a third: not met.** 522 → 387 (−26%) in Reg M-A, 326 → 231 (−29%) in Reg M-B; a third would be 348 and 217. Knock-out misses also fell: 94 → 80 and 42 → 32.
- **The damage estimate has no bias.** On 807 clean hits (ten times last week's sample), real damage is a median 1.00 of the estimate in both formats, and the misses are as often too low as too high. Last week's one-sided tail did not hold up. What is left of the HP misses is not a damage bias.
- **Every hit is weighed over the spreads players run** (your decision, 14 Nov): 2.1–2.2 more points of boards found and 15–18% fewer HP misses, for about twice the resolver's time per turn.
- **Your team is in the tool** (done ahead): the advice, the session and the replay report use it without `--team`, with your nicknames.

## The resolver check over the week

| | Reg M-A, start | rules | + spread damage | now | Reg M-B, start | rules | + spread damage | now |
|---|---|---|---|---|---|---|---|---|
| fully modelled | 97.77% | 99.72% | 99.72% | **99.94%** | 98.93% | 99.77% | 99.77% | **99.96%** |
| board found | 83.0% | 84.8% | 87.0% | **87.1%** | 85.9% | 87.8% | 89.9% | **89.9%** |
| both | 81.4% | 84.6% | 86.8% | **87.1%** | 85.3% | 87.7% | 89.7% | **89.9%** |
| both, turns with a knock-out | 84.0% | 87.0% | 88.2% | 88.4% | 87.3% | 89.6% | 90.8% | 90.9% |
| turns modelled in part | 81 | 10 | 10 | 2 | 28 | 6 | 6 | 1 |
| misses: HP only | 522 | 463 | 392 | **387** | 326 | 282 | 232 | **231** |
| misses: a knock-out differs | 94 | 88 | 80 | 80 | 42 | 37 | 33 | 32 |
| resolver time per turn | | 0.38 s | 0.80 s | 0.83 s | | 0.25 s | 0.53 s | 0.52 s |

"Start" is `7df9b1d`, Week 12's code. "Rules" is `62efc9e` without spread damage; "+ spread damage" the same code with it; "now" is `b0219dc`, with it (the last three rules, below). Times are from your computer's runs (6 workers); the start's were on my 2-core workspace and are not comparable, so they are left out. Over the week, 245 turns are found that were not (Reg M-A) and 96 the other way; 151 and 46 in Reg M-B.

The last commit (`fde5ac3`: Magic Bounce, and genders from team preview) came after your run; on the two games it touches, two more Reg M-B turns are found and Reg M-A's last Cute Charm mark is gone, so one turn is left in each format.

## Task 1: damage from the spreads players run

**First, the forms the statistics count under their species** (`8cadac6`, `50e3ba8`). Sinistcha-Masterpiece and Maushold-Four now take their species' spreads and sets, so a Sinistcha is Bold or Calm with points in its defences, as players run it. The resolver check: board found 83.0% → 83.2% (Reg M-A), 85.9% → 86.3% (Reg M-B); HP misses 522 → 517 and 326 → 318. The win model's estimates moved by a mean of 0.56 points (Reg M-A) and 0.75 (Reg M-B), with its score (Brier) unchanged; it takes the change for good at its next retraining (Reg M-C).

**The bias on more hits** (`541962d`). Every clean hit in the check's games: one move's hit on a Pokemon with nothing else changing its HP (no item, ability, weather, critical hit or second hit), on turns where both players' choices are shown whole. Real damage against the estimate:

| | hits | median | too high (real under 90%) | too low (over 110%) | middle 80% |
|---|---|---|---|---|---|
| Reg M-A | 444 (238 single-target, 206 spread) | 1.00 | 26% | 23% | 0.81 to 1.19 |
| Reg M-B | 363 (225, 138) | 1.00 | 21% | 20% | 0.82 to 1.17 |

(Measured at `62efc9e` with the likeliest spread. With every hit weighed over the spreads, the median is 0.98 and 0.99, the tails 29% and 22%, 25% and 19%.)

Last week's sample (84 hits) said the estimate was too high in 31% of hits and too low in 17%, and the brief's reasoning rested on that. On ten times the hits the two tails are even. The spread of real damage around the estimate is wide (the damage roll alone is ±8%), but it is not one-sided: the resolver does not hit too hard.

**Every hit weighed over the spreads players run** (`df54adf`, `afebb73`, `89b862a`). A hit's damage is averaged over the attacker's and the target's likely spreads (each with at least 10% of the belief, three at most), each pair weighed by its chance, instead of the likeliest spread alone. Week 12's branching where a spread decides a knock-out stays. A hit is now worked out once for every board that shares it (`afebb73`), which made it affordable.

**The cost and your decision.** It took 2.1 times the resolver's time per turn, over the brief's stop rule (1.5 times), so I reported it with the options and you turned it on (14 Nov). On the full check (`62efc9e`, on against off): board found +2.2 points (Reg M-A) and +2.1 (Reg M-B); HP misses −15% and −18%; knock-out misses 88 → 80 and 37 → 33. It is not all gain: 173 turns found that were not, but 94 the other way in Reg M-A (100 and 46 in Reg M-B). The ones lost are mostly HP just over the 6-point line (median 9 points off): averaging blurs a board the likeliest spread had exactly. `--no-spread-damage` turns it off (Runbook §26).

## Task 2: the rules still modelled in part

Each against Showdown's Champions data, each with a test first, shown failing (`189aac7`, `b908ade`, `52e0496`, `fc1e864`, `f86db4b`, `62efc9e`, `b0219dc`, `fde5ac3`):

- **Abilities that change hands:** Skill Swap, Entrainment, Simple Beam (the new ability starts, so a given Intimidate goes off).
- **Transform (Imposter):** the board keeps what Ditto copied (the foe, its form, moves, stat stages, a changed ability and types) and which place each Pokemon stands in. Its choices are the copied moves. It hits with the copied stats but its own HP and keeps its own item (Choice Scarf), and a Ditto coming in during a turn copies the foe opposite.
- **Gravity, Imprison, Curse, Stockpile, Salt Cure, Heal Block** (and Psychic Noise), **Power Swap, Destiny Bond, Focus Energy, Tidy Up, Magic Powder.**
- **Hazards:** Stealth Rock, Spikes, Toxic Spikes, Sticky Web on whoever comes in (the board keeps them; Heavy-Duty Boots stop them).
- **The Pokemon sent in after a pivot move:** chosen by the forced-switch model, as a forced switch is. A Prankster Parting Shot into a Dark type and a sound move into Soundproof fail without switching.
- **A Substitute hit before:** a quarter, a half or three quarters of it left, each as likely (the log never shows what is left).
- **Leech Seed** heals whoever stands in the seeder's place, and no one when the place is empty.
- **Ally Switch:** the two change places, so a move aimed at one's place lands on the other; a third of the time when used the turn before.
- **Magic Bounce:** a move with the reflectable flag aimed at its holder, or at its side (hazards), is used back at its user; a bounced Parting Shot switches the holder out. It was not modelled at all, with no mark (1 game in the check's sample).
- **Cute Charm:** a contact hit infatuates the attacker 30% of the time when their genders differ (the board takes each gender from team preview); an infatuated Pokemon cannot move half the time, until the one who caused it leaves.
- Found on the way: **Sitrus Berry** after any damage (recoil included), **Life Dew** heals the ally too, a **Mega Evolution** shows in the log even when its move is hidden, **weather** ends before its damage on its last turn.

The rules alone (before spread damage) found 73 turns that were not found (Reg M-A) and lost 8; 53 and 4 in Reg M-B.

**Left** (one turn in each format): **Wish** (1 turn, Reg M-A: it heals whoever is in the user's place at the end of the next turn, and the board does not keep it yet) and **Instruct** aimed by the move its target used last turn (1 turn, Reg M-B). Both came up after the brief; both are small.

## Task 3: your team (done ahead)

`5d13538`, `50e3ba8`, Runbook §25. The tool keeps your team in `my_team.txt` (outside git); the advice, the session and the replay report use it without `--team`, with your nicknames (End Game, Mia). `python -m wpa.team_check` shows each Pokemon's six stats at level 50 to set beside the app's Stats screen, and checks the stat points add up to 66 at most. When a team has what the format's data has not seen (Golisopod is in neither Reg M-A's nor Reg M-B's statistics), the advice says its numbers are rough.

## The gate, and what I suggest

**Moves modelled in part: met** in both formats. **HP misses down by a third: not met** (−26% and −29%).

What is left of the HP misses: a diagnosis of 300 of them earlier this week (at `52e0496`, before spread damage) put about a third of them on two Pokemon that are each within reach but on no single board together, a quarter inside the boards' range but with no board within 6 points (the resolver merges boards on a 5-point grid and keeps 300 at most), and the rest above or below every board. With no bias left in the damage, what remains is mostly unknowns the logs cannot settle (each player's real spread, which roll came up), and how finely the resolver keeps its boards.

**I suggest moving on to Reg M-C as planned** and carrying the HP gate as a known limit, for three reasons:
1. **The bot's own games are the better test.** In Phase 3 every spread is known, so an HP miss there is a rules gap, not a guessed spread. That separates the two causes these logs cannot.
2. **Reg M-C is the current regulation and the bot must play it** (official until 2 December). The HP misses do not block it.
3. **The engine is already right on 87–90% of turns**, and a miss is typically about 13 points of one Pokemon's HP.

The alternative is one more week on HP misses before Reg M-C: a new diagnosis at today's code, then the resolver's grid and cap. Keeping ten times the boards recovered 12 of 94 such misses in a quick test this week, so I would expect a few points, not a third.

**One cost to watch:** spread damage doubled the resolver's time. A turn's advice took about 14 seconds before; the bot has 55 seconds a turn and 7 minutes a game. Phase 3's clock work will measure it.

## Surprises

- **Last week's one-sided tail was noise.** The brief's reasoning (the resolver hits too hard when it misses) came from 84 hits; 807 say the estimate is unbiased. The spread fix still helped, by covering the spreads players run rather than correcting a bias.
- **Spread damage loses some found turns** (94 and 46) while finding more (173 and 100): a board the likeliest spread had exactly can move just over the line.
- **Two rules were wrong without saying so.** A Ditto coming in during a turn did not transform at all, and Magic Bounce did nothing; neither was marked. Game 2620366712 has four more turns found now.
- **Your computer ran the whole check in 21 minutes** (6 workers), not the hour I estimated.
- **The tests ran in a copy of the project in my cloud workspace** this week, so your computer was free for the timed runs.

## For you

1. **Decide the gate:** move on to Reg M-C with the HP gate carried as a known limit (my suggestion), or a week on HP misses first.
2. **Reg M-C's first step needs your approval:** updating the pinned Showdown code to a version with Reg M-C (`docs/REG-MC-GAPS.md`).
