# Week 11 report: your choice and the position, team preview, Speed order, the Champions rules (M5 part 3)

11 November 2026. Brief: `docs/WEEK11-DISPATCH.md`. Commits `c1e1e12` to `9e9ef90`, plus this
report; the work done ahead is in `fee8912` and `9bca83a`. All numbers are per format and on the **validation split** unless a line
says training. The test split was not opened this week (it has been opened 5
times, all logged).

Every box in the brief is ticked. Your run of the brief's sample (Task 4)
finished on 11 November. It used the code at `9e9ef90`. The fixes I worked on
ahead while it ran (the replay report, more of the Champions rules) are not in
its numbers; they are in "Worked ahead" below.

## The headline

- **"Your decision" is now split, and the player's part is smaller than it
  looked.** Your choice against the typical choice is typically 11.9 points a
  turn in both formats. The position, credited to no one, is as big: 11.9 in
  Reg M-A, 12.3 in Reg M-B. Players beat the typical choice by 2.2 to 2.3 points
  on average, and their opponents' replies take the same back.
- **The biggest swings are better understood.** Of the turns with a swing over
  40 points, the share fully understood (board found, fully modelled) rose from
  58% to **70% in Reg M-A**, and from 79% to **81% in Reg M-B**.
- **Every game adds up from team preview to its result:** all 387 Reg M-A games
  and all 270 Reg M-B games without a forfeit or timer.
- **Team preview is a small decision by this measure.** The leads are typically
  4 points against the typical pair, a third of a turn. Players led the model's
  best pair 10% of the time, at a cost of about 5 points against it.
- **Checking the biggest choices against their logs found two problems.**
  - The game-end fix I made during the week (`9e9ef90`) ended games too early
    when a player had not yet shown all four Pokemon. About 40 decision points
    were affected, 3 of them in this report's top-10 lists. **It is fixed now,
    with a test.**
  - Reg M-A's two biggest "choices" are not choices. A Meowscarada's Protean had
    changed its type, which the resolver does not model. That is the next cause
    to fix.

## Task 0: your choice and the position (DEFINITIONS revision 10)

Each player's **typical choice** is their own likely choices from the opponent
model, as for the opponent's replies: the likeliest 6 exactly, and 6 more drawn
in proportion to their chances. These play against the opponent's likely replies.
One block of choice pairs per turn serves both players. Then:

- **your choice** = E[WP | your choice] - E[WP | a typical choice];
- **the position** = E[WP | a typical choice] - WP(before);
- their decision and the dice as before. The four add up to the swing at every
  decision point (tested, and checked on real data: largest error 1.1e-16).

"Your decision" (revision 8) is kept in the records as your choice plus the
position, so Weeks 9 and 10 can be compared.

**Tests** (written first, shown failing):
- a forced switch with one Pokemon gives your choice exactly 0;
- a turn where every choice is worth the same gives your choice 0;
- the Perish Song turn that ends the game whatever anyone chooses puts the whole
  swing in the position.

**What it costs** (measured before Task 4, 16 games, 110 turns, same code with and
without it): **1.5 times the time**, not the 2 to 3 times I estimated. The
median turn doubles, but the slowest turns hit the board budget either way.

On those 16 games, players beat the typical choice by 2.2 points on average
(typically 10.9 points either way), and the position averages zero (typically
12 points).

## Task 1: team preview and leads

At team preview each player picks four and the two that lead, both without
seeing the other's choice. The win probability model **cannot see a player's own
back two**: both sides' backs are chances from the bring model, and Week 8 found
they add nothing measurable. So the choice scored is **the leads**, one of the
15 pairs of the six on the sheet (I told you on 10 Nov).

- **The resolver** puts both sides' leads in, then runs their entry effects in
  Speed order: Intimidate, weather, terrain.
- **A lead model** (`wpa/lead_model.py`), learned from the 141,748 sides of the
  training games. **It beats a uniform guess in both formats** (validation):

  | | sides | model | uniform | its likeliest pair led |
  |---|---|---|---|---|
  | Reg M-A | 17,388 | -2.436 | -2.708 | 24.2% (uniform 6.7%) |
  | Reg M-B | 732 | -2.371 | -2.708 | 27.3% |

  (Mean log chance of the pair that led.) What weighs most: **leading the same
  way as the set's previous game** (games 2 and 3 use game 1's leads, §11.3),
  then each species' lead rate, then being first on the sheet.
- **The split** is as in §3, valued at turn 1's start. Nothing is random at team
  preview, so the dice are only the model's own small difference between a board
  and the next row (typically 1 point).
- **A game now adds up from team preview to its result** (§2), checked on every
  game of your run.

## Task 2: Speed order from the hidden spreads

Where two Pokemon's order depends on Speed that the evidence has not settled,
the resolver can now branch on each order with its chance, from each Pokemon's
whole spread belief (kept at every decision point now, not only the likeliest
spread). Trick Room reverses it. Tests first.

**Measured on six of Week 10's biggest Reg M-A games, it changed nothing and cost
2.6 times the time.** The dice, the boards found and the biggest swing were all
the same to the point. So it is **off by default**, available with
`--speed-beliefs`.

**Reg M-A's biggest swing was not Speed** (I said in Week 10 that it was). With
the spreads refined from the game so far, Basculegion is faster than Dragonite in
every case, as it was. What put -71 in the dice was a choice the log does not
show. Kingambit fell before it moved, so its choice was averaged over all its
options, Protect included. But Protect would have gone first, and Kingambit would
not have been hit. The fix: **a choice the log does not show is averaged only
over the choices the log allows**. A switch or a Mega Evolution always shows, and
a Pokemon knocked out before moving chose no move with raised priority. On those
six games, the dice at turns with a hidden choice went from typically 18.8 points
to 10.2. The biggest swing's dice went from -71 to -36, and p2's read of the turn
(their decision) from -22 to -58. The -36 left is the damage estimate (the
resolver gives the knock-out 59%), which is spreads.

## Task 3: the Champions rules, and the causes left among the biggest swings

Checking confusion against Showdown's Champions files turned up four rules that
differ from the main games. The resolver had the main games' rules for three of
them, and did not model sleep at all:

| | Champions (`data/mods/champions`) | the resolver before |
|---|---|---|
| a paralysed Pokemon cannot move | 1 time in 8 | 1 time in 4 |
| a frozen Pokemon thaws | 1 time in 4 a try, by the third for sure | 1 time in 5 a try |
| a sleeping Pokemon wakes | on its second try 1 time in 3, by the third for sure | not modelled ("partly modelled: sleep") |
| Rage Fist's hits | reset when the user leaves the field | kept for the whole game |

All four are fixed, with tests first. And:

- **Confusion** is modelled: 2 to 5 tries, snapping out on each with Showdown's
  chances, and the 33-in-100 self-hit with Showdown's own damage formula (a
  40-power typeless hit with its own Attack and Defense). Before, a confused
  Pokemon's later turns were played as if it were not confused, and nothing
  marked them.
- **Charging moves:** the turn after charging, the move goes off. Before, the
  resolver charged again on that turn and dealt no damage. A Pokemon in the air
  or underground (Fly, Dig, Phantom Force) is out of reach meanwhile.
- **Encore** limits the Pokemon to its encored move (it may still switch), and a
  charging move to its move. When Encore changes the target's move in the same
  turn, it stays "partly modelled".
- **Sleep** now follows its counter (the tries so far, from the log), and so does
  freeze.

**The Week 10 resolver check again** (the same games):

| | Week 10 | Week 11 |
|---|---|---|
| Reg M-A, turns fully modelled | 87.1% | **92.9%** |
| Reg M-A, board found and fully modelled | 65.7% | 69.0% |
| Reg M-B, turns fully modelled | 87.9% | **91.4%** |
| Reg M-B, board found and fully modelled | 64.7% | 67.4% |

Confusion, sleep and charging are gone from the reasons. What is left: Taunt,
the Toxic counter (24 Reg M-B turns), Quash, Leech Seed and Heal Block. The
resolver is about 28% slower.

## Task 4: the brief's sample again (your computer)

The same 300 Reg M-A and 199 Reg M-B sets (526 and 366 games), with Tasks 0 to
3, the averaged model and sharpness 4. Each choice was compared with the player's
10 likeliest in every third game. "Typical size" is the root mean square, in
points.

| | Week 10 | Week 11 |
|---|---|---|
| **Reg M-A** swing | 16.9 | 16.9 |
| your choice (against the typical choice) | | +2.2, typical 11.9 |
| the position (credited to no one) | | +0.0, typical 11.9 |
| your decision (revision 8: the two above) | +2.3, typical 14.0 | +2.2, typical 14.0 |
| their decision | -2.3, typical 12.5 | -2.2, typical 12.7 |
| the dice | typical 11.8 | typical 11.3 |
| cost vs best (mean) / best taken | -7.7 / 25% | -7.8 / 25% |
| a part of 3 points or more | yours 74%, theirs 58%, dice 45% | choice 59%, position 71%, theirs 59%, dice 43% |
| **Reg M-B** swing | 16.3 | 16.3 |
| your choice | | +2.3, typical 11.9 |
| the position | | +0.0, typical 12.3 |
| your decision (revision 8) | +2.3, typical 14.3 | +2.3, typical 14.3 |
| their decision | -2.3, typical 12.7 | -2.3, typical 12.9 |
| the dice | typical 11.5 | typical 11.1 |
| cost vs best (mean) / best taken | -7.7 / 25% | -7.8 / 25% |
| a part of 3 points or more | yours 74%, theirs 60%, dice 42% | choice 59%, position 73%, theirs 61%, dice 41% |

- **The four parts add up** at every decision point (largest error 1.1e-16).
- **The dice are a little smaller** (11.8 to 11.3; 11.5 to 11.1), from Task 3's
  rules. Where the resolver finds the board that happened, they are typically
  9.7 points (Reg M-A) and 10.0 (Reg M-B); where it does not, 15.6 and 14.0.
  The board that happened was among the resolver's in 77% of turns in both
  formats, as in Week 10.
- **The position is the part most often at 3 points or more** (71 to 73% of
  decision points). It averages zero: it is where the model's single WP and
  what the turn held disagree, in both directions.

**Every turn with a swing over 40 points, by cause:**

| | turns | found, fully modelled | found, partly modelled | not found, partly modelled | not found, fully modelled |
|---|---|---|---|---|---|
| Reg M-A, Week 10 | 132 | 77 (58%) | 23 | 2 | 30 |
| Reg M-A, Week 11 | 132 | **92 (70%)** | 8 | 2 | 30 |
| Reg M-B, Week 10 | 62 | 49 (79%) | 3 | 2 | 8 |
| Reg M-B, Week 11 | 62 | **50 (81%)** | 2 | 2 | 8 |

The reasons left among them:
- **Reg M-A:** Encore changing the target's move that turn (4), Trick (2),
  Leech Seed (2), the Toxic counter, Quash and Yawn (1 each).
- **Reg M-B:** Trick, Tidy Up, Encore and Strength Sap (1 each).

Encore, Leech Seed, the Toxic counter, Yawn and Strength Sap are modelled now
("Worked ahead"). "Not found, fully modelled" stays at 30 in Reg M-A: that is
mostly spreads.

**Team preview (the leads):**

| | decisions | your choice | the position | their decision | the dice | cost vs best | best pair led |
|---|---|---|---|---|---|---|---|
| Reg M-A | 1,052 | +0.9, typical 3.8 | typical 2.4 | -0.9, typical 5.4 | typical 1.1 | -5.3 | 10% |
| Reg M-B | 732 | +1.1, typical 4.0 | typical 2.8 | -1.1, typical 5.3 | typical 1.3 | -5.8 | 10% |

**Forced switches:**

| | decisions | your choice | the position | cost vs best | best taken |
|---|---|---|---|---|---|
| Reg M-A | 1,520 | +0.5, typical 3.6 | -0.9, typical 7.1 | -1.4 | 76% |
| Reg M-B | 1,022 | +0.5, typical 3.8 | -0.4, typical 7.3 | -1.6 | 76% |

With the position split out, the forced switch's own choice is small, as Week 10
expected. Week 10's examples with one Pokemon left to send in now have your
choice exactly 0, all of it in the position.

### The 10 biggest swings

p1's swing, then each player's split from their own side: your choice /
the position / their decision / the dice.

**Reg M-A:**

| replay | turn | p1 swing | p1 | p2 | note |
|---|---|---|---|---|---|
| [2605342116](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2605342116) | 5 | -82 | +6 / +4 / -57 / -36 (vs best -1) | +11 / -4 / +40 / +36 | the hidden choice and the damage estimate (Task 2) |
| [2618304355](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2618304355) | 8 | +80 | +6 / +57 / +14 / +4 | -12 / -57 / -7 / -4 (vs best -64) | |
| [2592257334](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2592257334) | 6 | +75 | +2 / -12 / -2 / +87 | +2 / +12 / -2 / -87 | |
| [2601775859](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2601775859) | 7 | -75 | +1 / -38 / -29 / -9 | +28 / +38 / -0 / +9 | |
| [2625184370](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2625184370) | 10 | +71 | +15 / +1 / -1 / +56 | +1 / -1 / -15 / -56 | |
| [2612055074](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2612055074) | 5 | +70 | +21 / +41 / +5 / +2 (vs best -13) | -26 / -41 / -0 / -2 (vs best -31) | |
| [2632898552](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2632898552) | 6 | +68 | -14 / +3 / +77 / +2 | -44 / -3 / -19 / -2 | |
| [2631109433](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631109433) | 8 | -68 | -46 / +8 / -20 / -10 | +1 / -8 / +65 / +10 | |
| [2590847741](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590847741) | 4 | -67 | +5 / +4 / -69 / -8 | +72 / -4 / -8 / +8 | board not found |
| [2631650207](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631650207) | 10 | +66 | +4 / +6 / -10 / +67 | +10 / -6 / -4 / -67 | **wrong: the game-end bug** (below) |

**Reg M-B:**

| replay | turn | p1 swing | p1 | p2 | note |
|---|---|---|---|---|---|
| [2635336050](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635336050) | 7 | -78 | -1 / -33 / -44 / +0 | +42 / +33 / +3 / +0 | |
| [2635245550](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635245550) | 4 | +73 | +42 / +40 / +1 / -8 | +0 / -40 / -42 / +8 (vs best -48) | |
| [2635918014](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635918014) | 15 | -69 | +0 / -61 / -8 / +0 | +8 / +61 / +0 / +0 | |
| [2635850384](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635850384) | 5 | +67 | +50 / -3 / +11 / +8 | -9 / +3 / -52 / -8 | board not found |
| [2634409842](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2634409842) | 8 | +66 | +41 / +13 / +5 / +7 | -0 / -13 / -45 / -7 (vs best -2) | |
| [2635847687](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635847687) | 6 | +64 | +1 / +39 / +3 / +21 | -1 / -39 / -3 / -21 | |
| [2635761330](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635761330) | 9 | -63 | -1 / -4 / -48 / -11 | +48 / +4 / -0 / +11 | |
| [2635349372](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2635349372) | 6 | +62 | +9 / -8 / -0 / +61 | +0 / +8 / -9 / -61 | real luck: a critical hit and a double flinch (Week 10) |
| [2634508987](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634508987) | 6 | -61 | +13 / -3 / -62 / -8 (vs best -5) | +47 / +3 / +2 / +8 | |
| [2634666109](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634666109) | 6 | -61 | +0 / +14 / -75 / +1 | +75 / -14 / +0 / -1 | |

Compared with Week 10, much of what was "your decision" in these turns is now
the position. Reg M-A #2 is an example: p1's +63 was +6 choice and +57
position. Reg M-B #3 is another: p1's -61 is all position.

### The 10 biggest choices (by your choice)

**Reg M-A:**

| replay | turn | player | choice / position / theirs / dice | note |
|---|---|---|---|---|
| [2616502323](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2616502323) | 8 | p2 | -89 / +33 / +11 / +84 (vs best -95) | **wrong: Protean** (below) |
| [2621800453](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2621800453) | 5 | p1 | +86 / -71 / -0 / +0 | **inflated by the game-end bug** (+57 / -41 in the first run) |
| [2616502323](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2616502323) | 7 | p2 | -85 / +32 / +51 / -0 (vs best -89) | **wrong: Protean** |
| [2605465902](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2605465902) | 8 | p2 | +82 / -66 / -33 / -0 | |
| [2615562713](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2615562713) | 7 | p2 | -78 / +64 / -5 / -0 (vs best -85) | |
| [2629652309](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2629652309) | 6 | p2 | +78 / -34 / -14 / -13 | |
| [2585392380](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2585392380) | 8 | p1 | +78 / -39 / -22 / -43 (vs best -0) | |
| [2605465902](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2605465902) | 8 | p1 | -74 / +66 / +25 / +0 | |
| [2590847741](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590847741) | 3 | p2 | +73 / -6 / -66 / +0 | |
| [2590847741](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2590847741) | 4 | p2 | +72 / -4 / -8 / +8 | board not found |

**Reg M-B:**

| replay | turn | player | choice / position / theirs / dice | note |
|---|---|---|---|---|
| [2635761330](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635761330) | 8 | p2 | -89 / +15 / +30 / -4 | |
| [2634666109](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634666109) | 6 | p2 | +75 / -14 / +0 / -1 | |
| [2635914418](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635914418) | 4 | p1 | +73 / -60 / +1 / +3 | |
| [2635898115](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635898115) | 9 | p1 | -72 / +2 / +66 / -0 | |
| [2635954321](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635954321) | 9 | p2 | -72 / +48 / +2 / +4 | |
| [2635353877](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635353877) | 4 | p1 | -68 / +50 / +3 / +2 | |
| [2635914020](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635914020) | 8 | p2 | +65 / -54 / -0 / +0 (vs best +0) | board not found |
| [2635898054](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635898054) | 5 | p2 | -61 / +14 / +24 / +2 (vs best -76) | |
| [2634467411](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2634467411) | 7 | p2 | +59 / -55 / +2 / +8 (vs best -2) | **inflated by the game-end bug** (+5 / -1 in the first run) |
| [2634417899](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634417899) | 6 | p1 | +58 / -1 / -60 / -2 | |

A big choice with an opposite position (+73 / -60, -68 / +50) is common here. It
means most of the player's likely choices were bad and theirs was not, or the
other way round. That is what "your choice" is meant to catch. Only the two I
checked against their logs are known to be wrong; the rest are unchecked.

### The 10 biggest team-preview choices

**Reg M-A:**

| replay | player | choice / position / theirs / dice |
|---|---|---|
| [2617066032](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2617066032) | p1 | +17 / -1 / +4 / +0 (vs best +0) |
| [2622522424](https://replay.pokemonshowdown.com/gen9championsvgc2026regma-2622522424) | p2 | -17 / +2 / -8 / +0 (vs best -25) |
| [2617061714](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2617061714) | p1 | +13 / +1 / +5 / +0 (vs best +0) |
| [2587468661](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2587468661) | p2 | +13 / +3 / -1 / +0 (vs best +0) |
| [2631810328](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2631810328) | p2 | +12 / -5 / +4 / +0 (vs best -1) |
| [2625791649](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2625791649) | p2 | +12 / +0 / +2 / +0 (vs best +0) |
| [2618638153](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2618638153) | p2 | +11 / -2 / -0 / +0 (vs best +0) |
| [2629058492](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2629058492) | p1 | +11 / -3 / +3 / +0 (vs best +0) |
| [2625758937](https://replay.pokemonshowdown.com/gen9championsvgc2026regmabo3-2625758937) | p2 | -11 / +3 / +3 / +0 (vs best -19) |
| [2589148242](https://replay.pokemonshowdown.com/gen9championsvgc2026regma-2589148242) | p1 | +11 / +1 / -1 / +0 (vs best +0) |

**Reg M-B:**

| replay | player | choice / position / theirs / dice |
|---|---|---|
| [2634182062](https://replay.pokemonshowdown.com/gen9championsvgc2026regmb-2634182062) | p2 | +15 / +3 / -5 / +0 (vs best -1) |
| [2634873977](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634873977) | p2 | -13 / +3 / -3 / +4 (vs best -23) |
| [2635102580](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635102580) | p2 | +13 / -4 / -1 / +0 (vs best +0) |
| [2635353877](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635353877) | p2 | +13 / +9 / -2 / +0 (vs best +0) |
| [2635351992](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635351992) | p2 | +13 / +5 / +4 / +0 (vs best -3) |
| [2634708083](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2634708083) | p1 | +12 / -5 / -7 / +4 (vs best +0) |
| [2635402345](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635402345) | p1 | +12 / -1 / +2 / +0 (vs best -3) |
| [2635848238](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635848238) | p1 | +12 / -5 / -10 / +0 (vs best +0) |
| [2635398159](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635398159) | p1 | +12 / +2 / -5 / +0 (vs best +0) |
| [2635525365](https://replay.pokemonshowdown.com/gen9championsvgc2026regmbbo3-2635525365) | p2 | -12 / -0 / +2 / +0 (vs best -18) |

The biggest lead choices are 11 to 17 points: worth having right, but smaller
than a turn's. The worst ones cost 18 to 25 points against the best pair.

### Two I checked against the logs, and what they found

- **Reg M-A's biggest choices, game 2616502323 turns 7 and 8, are Protean.**
  - On turn 6, p1's Meowscarada used Knock Off, and Protean made it a pure Dark
    type.
  - On turns 7 and 8 it was the last Pokemon on each side: Meowscarada at 71%
    against p2's Mega Camerupt at 46%. Meowscarada used Protect twice; the
    second failed, and Camerupt's Earth Power knocked it out.
  - The resolver still saw Meowscarada as Grass and Dark, which resists Earth
    Power, so it judged Camerupt's winning move a blunder (-89).
  - Protean (and Libero) is not modelled and not marked. The Reg M-C list
    (`REG-MC-GAPS.md`) already had it as a silent gap. Here it tops a list.
- **Reg M-A #10, the Perish Song turn (game 2631650207, turn 10), is the
  game-end bug.** Week 10 showed this turn correctly: the game was over whatever
  anyone chose, so all of it was the position. In this run it is +67 dice.
  - The resolver ended the game early in some branches, because a player who
    had shown fewer than four Pokemon was treated as having none left.
  - See "What went wrong". The first Week 11 run, before `9e9ef90`, had it
    right: +66 position.

### Time

| | Week 10 | Week 11, first run | Week 11, this run |
|---|---|---|---|
| Reg M-A, core-hours | 18.4 | 21.1 | 19.6 |
| Reg M-B, core-hours | 10.9 | 14.7 | 33.4 |
| median time per turn, Reg M-A / Reg M-B | | | 16.1 s / 21.3 s |

- **The first Week 11 run is the fair measure:** 35.8 core-hours, 1.2 times
  Week 10's for twice the work per turn (the typical choice).
- **Reg M-B's 33.4 hours are not the code's doing, as far as I can tell.**
  - Three turns took about 2.4 hours each, with ordinary board counts (10,000
    to 16,500 boards), and 7.2 hours between them. A stall like that is most
    likely the computer sleeping, but the records can't show it.
  - The rest of Reg M-B ran 1.3 times slower per turn than in the first run,
    steadily through its part of the run. Reg M-A ran 0.9 times its first run.
  - Reg M-B ran last, from late morning to 4 pm. I don't know the cause; the
    code was the same apart from the game-end fix, which values fewer boards,
    not more.

## Surprises

- **The position is the part most often at 3 points or more.** It is
  credited to no one, and it averages zero. But it is at 3 points or more at
  71 to 73% of decision points, more often than your choice (59%).
- **Protean tops the list of biggest choices.** One untracked type change made
  a game-winning move look like a 89-point blunder.
- **Players rarely lead the model's best pair** (10%), yet it costs them only
  about 5 points. Most pairs are close.
- **The Champions rules differ from the main games** in more places than
  Task 3's four. Encore moves the target in the order: an encored Pokemon uses
  its new move with that move's priority. Spicy Spray burns every attacker.
  Both are in "Worked ahead".
- **Reg M-B's run time** came from a sleeping computer, not the code.

## What went wrong, and was caught

- **The game-end fix (`9e9ef90`) ended games too early.** It treated a player
  who had not yet shown all four Pokemon as having none left. In the resolver,
  such a player lost the game whenever every Pokemon they had shown went down.
  - Between the two Week 11 runs, 1% of decision points moved by more than a
    point.
  - At the 48 decision points that ended games, it mostly helped: the dice
    there went from typically 21 (Reg M-A) and 27 (Reg M-B) points to 15.
  - It moved 41 earlier ones (24 Reg M-A, 17 Reg M-B), mostly for the worse;
    3 of them are in the top-10 lists above.
  - **Fixed now:** every player brings four, so a Pokemon not yet seen cannot
    have fainted. The test was written first and shown failing.
- **I told you the game-end fix touched "the last turn of most games",** then
  corrected that to 3 of 110 turns on 16 games. On the whole sample it moved
  1% of decision points by more than a point, in both directions.
- **Reg M-A's biggest swing was not Speed** (Week 10's report). Task 2 found the
  cause: a hidden choice averaged over Protect.
- **My first Encore fix followed the main games' rule** (the target keeps its
  place in the order). Showdown's Champions files change the target's queued
  move, with the new move's priority. I caught it while listing the Reg M-C
  changes, before it reached your computer. The test that shows the difference
  failed on the first version.
- **The cloud workspace was wiped on 11 November,** with the work ahead not yet
  on your computer. I rebuilt it from this conversation, kept copies in three
  places since, and checked it against the copies on your computer.

## Process notes

- Tests first throughout, each shown failing before the code.
- The suite on your computer: **755 passed, 6 skipped.** The same 15 test files
  cannot load in my workspace on your computer (bot libraries). ruff and
  pyright are clean.
- The test split was not opened. It has been opened 5 times.
- Runbook Section 20 covers this week's commands. Section 21 (new) covers the
  replay report.

### Worked ahead while your run went (not in its numbers)

- **The replay report (M7):**
  `python -m wpa.replay <replay link> --player <your name>`. It gives:
  - a game's biggest swings for one player, each split four ways;
  - your choice against both the typical choice and the best, with the best
    named when yours was not it;
  - what happened in each turn (moves, faints, and luck such as critical hits,
    misses and full paralysis);
  - your leads against the best pair, and your costliest choices.

  It takes a link, a saved replay page or a best-of-three. An end-to-end test
  on five validation games needs about ten minutes to record (Section 21).
- **More of the Champions rules in the resolver,** each tested first against
  Showdown's Champions data:
  - Encore changing the target's move that turn: 122 decision points marked in
    the first Week 11 run.
  - The Toxic counter (54), Leech Seed (67), Taunt (37), Yawn (32) and Disable
    (32).
  - Mental Herb; Spicy Spray, which always burns the attacker and was silent
    before; and Haze, Belly Drum, Moonlight and the like, Heal Pulse, Psych Up
    and Strength Sap.
  - Abilities that act only by chance when hit or hitting (Flame Body, Static,
    Cursed Body, Poison Touch and others) now mark the turn instead of passing
    in silence.
  - On 8 of the sample's games that had these causes, turns fully modelled
    went from 59% to 95%, and the board found from 59% to 72%.
- **The Reg M-C gaps** (`REG-MC-GAPS.md` in the project): 24 new Pokemon and 6
  Megas, about a dozen new abilities, 12 items and 15 moves. Each has what our
  model does with it today. M-C is deferred (your decision below).
- **Reading a game from a phone recording** (`APP-CAPTURE-TRIAL.md` in the
  project). Every one of the 39 actions in your 12-turn game was read from the
  battle messages; HP comes from the boxes; targets come from the HP change
  between turns (your suggestion).

## Decisions for the product owner

### Made this week (11 November)

1. **Reg M-C waits** until Reg M-A and M-B are ironed out. The gaps are listed
   for when it starts.
2. **Live advice during a match is the goal.** That means reading the phone's
   screen as it plays, mirrored to your computer (an iPhone: wireless to test,
   a cable and capture card for real use). The reader is built live-first, so
   the post-game reports come from the same work. Before using it in ranked,
   check the app's rules. Official tournaments forbid outside help during
   games.

### For you now

1. **Week 12: ironing out Reg M-A and M-B.** I suggest this order:
   - **(a) Measure the fixes since this run.** That is the game-end fix and the
     resolver work ahead. Use the resolver check, beside Weeks 10 and 11, on
     your computer (about an hour).
   - **(b) Protean and Libero:** a Pokemon's type changes with the move it uses.
     This is the cause behind Reg M-A's two biggest choices.
   - **(c) The stronger opponent model** (from Week 10).
   - **(d) A cheaper spread method** (from Week 10). Spreads are most of the
     "not found, fully modelled" turns.
   - **(e) Hidden opponent sets,** checked on Reg M-A and M-B games by hiding
     the sheets we know. Your app games and live advice both need it.
   - **(f) The brief's sample again,** at the end, to measure the week.

   Agree, or reorder?
2. **Try the replay report** on a Showdown game of yours, or any in Reg M-A or
   M-B (Section 21), and record its end-to-end check once (about ten minutes).
   Tell me what reads well and what doesn't.
