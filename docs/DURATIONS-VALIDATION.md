# Duration table checked against the battle logs

**Generated** by `python -m wpa.timers`. For every timed effect that
starts
and later ends in a log, the observed end turn is compared with the
turn the
table predicts from the start alone. Effects with no end event (the game
ended, the Pokemon left or fainted, weather replaced by other
weather) are
*censored*: they say nothing about the table and are counted separately.

- **match**: ended on the predicted turn.
- **explained**: ended early, with a named cause in the log (Defog, Brick
  Break and so on) or by using Trick Room again.
- **unexplained**: ended on a different turn with no cause given.
  This is the
  mismatch rate to watch.

Games read: regma 84738, regmb 4167

## regma

| Effect | Started with an end event | Match | Explained | Unexplained | Mismatch rate | Censored |
|---|---|---|---|---|---|---|
| Aurora Veil | 2846 | 2809 | 37 | 0 | 0.0% | 1748 |
| Disable | 776 | 740 | 36 | 0 | 0.0% | 3695 |
| Electric Terrain | 34 | 34 | 0 | 0 | 0.0% | 34 |
| Encore | 2820 | 2604 | 160 | 56 | 2.0% | 8896 |
| futuremove | 36 | 35 | 0 | 1 | 2.8% | 16 |
| Grassy Terrain | 68 | 68 | 0 | 0 | 0.0% | 55 |
| Gravity | 499 | 499 | 0 | 0 | 0.0% | 365 |
| Heal Block | 282 | 266 | 16 | 0 | 0.0% | 224 |
| Light Screen | 3647 | 3611 | 36 | 0 | 0.0% | 2080 |
| Magic Room | 5 | 5 | 0 | 0 | 0.0% | 12 |
| Magnet Rise | 0 | 0 | 0 | 0 | - | 2 |
| Misty Terrain | 13 | 12 | 1 | 0 | 0.0% | 16 |
| Psychic Terrain | 365 | 359 | 6 | 0 | 0.0% | 446 |
| RainDance | 9118 | 9118 | 0 | 0 | 0.0% | 20303 |
| Reflect | 2064 | 2034 | 30 | 0 | 0.0% | 1213 |
| Safeguard | 20 | 20 | 0 | 0 | 0.0% | 18 |
| Sandstorm | 5388 | 5388 | 0 | 0 | 0.0% | 13198 |
| Snowscape | 5393 | 5393 | 0 | 0 | 0.0% | 13361 |
| SunnyDay | 7657 | 7657 | 0 | 0 | 0.0% | 23431 |
| Tailwind | 31950 | 31950 | 0 | 0 | 0.0% | 14881 |
| Taunt | 1030 | 903 | 127 | 0 | 0.0% | 2346 |
| Trick Room | 13992 | 12641 | 1351 | 0 | 0.0% | 7861 |
| Wish | 154 | 149 | 0 | 5 | 3.2% | 52 |
| Wonder Room | 8 | 6 | 2 | 0 | 0.0% | 6 |
| Yawn | 934 | 934 | 0 | 0 | 0.0% | 880 |

### Unexplained examples (tag, start turn, end turn, predicted end turns, cause)

- encore: ('gen9championsvgc2026regmabo3-2608399698', 10, 10, [12], '')
- encore: ('gen9championsvgc2026regmabo3-2616761211', 13, 15, [16], '')
- encore: ('gen9championsvgc2026regmabo3-2619942583', 12, 14, [15], '')
- futuremove: ('gen9championsvgc2026regmabo3-2596814044', 6, 11, [8], '')
- wish: ('gen9championsvgc2026regmabo3-2611774684', 14, 21, [15], '')
- wish: ('gen9championsvgc2026regmabo3-2626134733', 8, 12, [9], '')
- wish: ('gen9championsvgc2026regmabo3-2619653082', 4, 7, [5], '')

### Named causes of early ends

- auroraveil: move: Psychic Fangs (14), move: Brick Break (10), move: Raging Bull (8), ability: Screen Cleaner (4), move: Defog (1)
- disable: item: Mental Herb (36)
- encore: item: Mental Herb (160)
- healblock: item: Mental Herb (16)
- lightscreen: move: Brick Break (14), move: Psychic Fangs (12), ability: Screen Cleaner (5), move: Raging Bull (5)
- mistyterrain: move: Steel Roller (1)
- psychicterrain: move: Ice Spinner (2), move: Defog (2), move: Steel Roller (2)
- reflect: move: Brick Break (13), move: Psychic Fangs (7), move: Raging Bull (7), ability: Screen Cleaner (3)
- taunt: item: Mental Herb (127)
- trickroom: move: Protect (284), move: Hyper Voice (47),  (42), move: Flare Blitz (40), move: Psychic (36), move: Calm Mind (34)
- wonderroom: move: Dire Claw (1),  (1)

### Counted effects

**slp**: 6824 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 0.0% | 1.3% (89) |
| 1 | 33.3% | 42.5% (2902) |
| 2 | 66.7% | 56.2% (3833) |

Chance it ends at attempt k, given it got that far (5909 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 0.0% | 0.8% (89 / 11587) |
| 2 | 33.3% | 33.0% (2902 / 8787) |
| 3 | 100.0% | 100.0% (3833 / 3833) |

**slp (earlybird)**: 1 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 33.3% | 0.0% (0) |
| 1 | 66.7% | 100.0% (1) |

Chance it ends at attempt k, given it got that far (0 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 33.3% | 0.0% (0 / 1) |
| 2 | 100.0% | 100.0% (1 / 1) |

**frz**: 961 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 25.0% | 50.5% (485) |
| 1 | 18.8% | 18.9% (182) |
| 2 | 56.2% | 30.6% (294) |

Chance it ends at attempt k, given it got that far (1384 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 25.0% | 27.1% (485 / 1790) |
| 2 | 25.0% | 24.3% (182 / 749) |
| 3 | 100.0% | 100.0% (294 / 294) |

**confusion**: 467 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 0.0% | 11.8% (55) |
| 1 | 25.0% | 47.1% (220) |
| 2 | 25.0% | 23.1% (108) |
| 3 | 25.0% | 11.6% (54) |
| 4 | 25.0% | 6.4% (30) |

Chance it ends at attempt k, given it got that far (1765 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 0.0% | 3.2% (55 / 1728) |
| 2 | 25.0% | 25.9% (220 / 850) |
| 3 | 33.3% | 35.9% (108 / 301) |
| 4 | 50.0% | 52.4% (54 / 103) |
| 5 | 100.0% | 100.0% (30 / 30) |


## regmb

| Effect | Started with an end event | Match | Explained | Unexplained | Mismatch rate | Censored |
|---|---|---|---|---|---|---|
| Aurora Veil | 112 | 107 | 5 | 0 | 0.0% | 92 |
| Disable | 11 | 11 | 0 | 0 | 0.0% | 69 |
| Electric Terrain | 52 | 52 | 0 | 0 | 0.0% | 53 |
| Encore | 124 | 108 | 12 | 4 | 3.2% | 421 |
| Grassy Terrain | 1 | 1 | 0 | 0 | 0.0% | 0 |
| Gravity | 4 | 4 | 0 | 0 | 0.0% | 3 |
| Heal Block | 12 | 12 | 0 | 0 | 0.0% | 6 |
| Light Screen | 376 | 345 | 31 | 0 | 0.0% | 633 |
| Psychic Terrain | 10 | 9 | 1 | 0 | 0.0% | 12 |
| RainDance | 687 | 687 | 0 | 0 | 0.0% | 1309 |
| Reflect | 322 | 272 | 49 | 1 | 0.3% | 545 |
| Sandstorm | 84 | 84 | 0 | 0 | 0.0% | 233 |
| Snowscape | 227 | 227 | 0 | 0 | 0.0% | 550 |
| SunnyDay | 281 | 281 | 0 | 0 | 0.0% | 942 |
| Tailwind | 1783 | 1783 | 0 | 0 | 0.0% | 926 |
| Taunt | 31 | 30 | 1 | 0 | 0.0% | 89 |
| Trick Room | 595 | 546 | 49 | 0 | 0.0% | 358 |
| Wish | 7 | 7 | 0 | 0 | 0.0% | 3 |
| Yawn | 44 | 44 | 0 | 0 | 0.0% | 35 |

### Unexplained examples (tag, start turn, end turn, predicted end turns, cause)

- encore: ('gen9championsvgc2026regmbbo3-2635420197', 12, 13, [14], '')
- encore: ('gen9championsvgc2026regmbbo3-2635970354', 12, 13, [14], '')
- encore: ('gen9championsvgc2026regmbbo3-2635164196', 12, 13, [14], '')
- reflect: ('gen9championsvgc2026regmbbo3-2635542983', 10, 14, [17], '')

### Named causes of early ends

- auroraveil: move: Psychic Fangs (5)
- encore: item: Mental Herb (12)
- lightscreen: move: Psychic Fangs (23), move: Brick Break (5), move: Raging Bull (2), ability: Screen Cleaner (1)
- psychicterrain: move: Steel Roller (1)
- reflect: move: Psychic Fangs (39), move: Brick Break (6), move: Raging Bull (3), ability: Screen Cleaner (1)
- taunt: item: Mental Herb (1)
- trickroom: move: Protect (8), move: Fake Out (3), move: Play Rough (2), move: Life Dew (2), move: Hyper Voice (2), move: Rock Slide (2)

### Counted effects

**slp**: 146 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 0.0% | 0.7% (1) |
| 1 | 33.3% | 40.4% (59) |
| 2 | 66.7% | 58.9% (86) |

Chance it ends at attempt k, given it got that far (148 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 0.0% | 0.4% (1 / 266) |
| 2 | 33.3% | 30.3% (59 / 195) |
| 3 | 100.0% | 100.0% (86 / 86) |

**frz**: 41 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 25.0% | 53.7% (22) |
| 1 | 18.8% | 24.4% (10) |
| 2 | 56.2% | 22.0% (9) |

Chance it ends at attempt k, given it got that far (76 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 25.0% | 23.9% (22 / 92) |
| 2 | 25.0% | 25.6% (10 / 39) |
| 3 | 100.0% | 100.0% (9 / 9) |

**confusion**: 48 countdowns that ran their course

| Attempts | Expected | Observed |
|---|---|---|
| 0 | 0.0% | 2.1% (1) |
| 1 | 25.0% | 41.7% (20) |
| 2 | 25.0% | 29.2% (14) |
| 3 | 25.0% | 20.8% (10) |
| 4 | 25.0% | 6.2% (3) |

Chance it ends at attempt k, given it got that far (147 cut-off countdowns counted while at risk):

| Attempt k | Expected | Observed (ended / at risk) |
|---|---|---|
| 1 | 0.0% | 0.7% (1 / 152) |
| 2 | 25.0% | 24.1% (20 / 83) |
| 3 | 33.3% | 38.9% (14 / 36) |
| 4 | 50.0% | 71.4% (10 / 14) |
| 5 | 100.0% | 100.0% (3 / 3) |
