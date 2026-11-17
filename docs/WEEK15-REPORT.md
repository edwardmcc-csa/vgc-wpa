# Week 15 report: Reg M-C, part 2 (its own models; better plays, not copied ones)

17 November 2026. Brief: `docs/WEEK15-DISPATCH.md`. Commits `872136c` to `1dc2c98`, plus this report. Numbers are on the **validation split** unless they say test. Reg M-C's test split was opened once this week, with your approval: the sixth opening, logged.

**Every task's boxes are ticked.** No decision is waiting on you. The tests pass: 1,125, with 12 skipped as slow. The 15 files that need the battle harness's libraries were not run, and none of them changed.

## The headline

- **Phase 2's gate is met on Reg M-C, on validation and on the test split.**
  - The win model's error is 0.1775 on validation and 0.1776 on test, against the simple baseline's 0.2075. Every calibration band is within 0.05.
  - The choice, lead and forced-switch models all beat a uniform guess on both splits.
  - The resolver check was met in Week 14: 92.9% of Reg M-C turns found, at a cap of 3,000 boards.
- **The tool now looks for better plays, not copied ones** (DEFINITIONS revision 13, your principle of 15 Nov). It compares every play the rules allow, not just the 10 players usually make.
  - The best play is one players rarely make at 36–47% of decision points, depending on the format.
  - It beats the best of the usual 10 by over 3 points at 19–32% of them.
  - The price is time: about 3.5 times as long per turn. That is fine after a game, but too slow for the bot's clock as it stands.
- **The opponent model now expects stronger play where players are stronger.**
  - Reg M-C has its own strength, 9.6, against 6.55 for M-A and M-B (revision 14).
  - Where the log shows a player's rating, their strength follows it, from 8.0 at 1000 to 10.3 at 1700 (revision 15, your direction of 16 Nov).
- **The three busiest accounts do not skew the models**, so no cap on games per player is needed.
- **Both models do at least as well on higher-rated games.** The win model's error falls from 0.182 (1100–1299) to 0.165 (1500 and up).

## Task 1: every choice, not the usual ten (revision 13)

**What changed** (`872136c`, `e2c82a2`, `202837c`):
- The replay report and the analysis compare your choice with every play the rules allow. The report names the best play and marks one players rarely make.
- The live advice ranks every play by win chance and says how many it compared.
- **Two passes, to keep the time down.** A first pass values every play against the opponent's 3 likeliest replies. Then the best 12, with the usual 10 and your own, are valued against every reply. `--exact-best` values every play in full, for checking.

**Is the two-pass search right?** On the same 10 Reg M-A games (172 decision points, 152 with both results), against the full search:

| | Time per decision point | Same best play | Cost vs. best within 1 point |
|---|---|---|---|
| The usual 10 (before) | 24 s | | |
| Two passes | 86 s | 86% | 72% |
| Every play in full | 162 s | | |

- Two runs of the old way agree within 1 point at 74%: the opponent's less likely replies are drawn at random. So most of the gap is that randomness, not the shortcut.
- The two-pass search misses a better play by over 3 points at 7 of 152 decision points (5%), by 10 at most. It still finds a play worth over 3 points at 22% of them, against 23% for the full search.

**What it changes** (15 Reg M-A and 15 Reg M-B validation sets, 55 games; Reg M-C on 15 of its own, 34 games, at revision 15's strengths):

| | Reg M-A | Reg M-B | Reg M-C |
|---|---|---|---|
| decision points | 408 | 360 | 580 |
| the best play is one players rarely make | 40% | 47% | 36% |
| it beats the best of the usual 10 by over 3 points | 24% | 32% | 19% |
| cost vs. best, mean (usual 10 → every play) | −6.2 → −8.5 | −7.0 → −10.8 | −5.9 → −7.8 |
| best play taken (usual 10 → every play) | 32% → 22% | 22% → 11% | 30% → 21% |
| cost of 5+ points (usual 10 → every play) | 35% → 47% | 40% → 56% | 38% → 49% |
| your choice against the typical one (unchanged by revision 13) | +2.0 | +0.7 | +1.8 |
| time per turn, median (usual 10 → every play) | 35 s → 128 s | 45 s → 155 s | – → 136 s |

- **Cost vs. typical, the fairness number, is unchanged**, as revision 13 asked. Only cost vs. best got harsher, because there are now better plays to compare against.
- **A few turns are very slow:** the slowest took 61 minutes (M-A) and 74 minutes (M-B). That is fine for a report written after the game, but not for advice during one.
- **Reg M-C's "usual 10" figures come from the same run** (the best of the usual 10, which every record keeps). M-A's and M-B's come from a separate run with the usual 10 only.
- **Reg M-C at its new strengths** (17 Nov). Each player's strength followed their rating, from 8.2 to 9.6, where the first run used 6.55 for everyone.
  - The best plays barely moved: rarely made at 36% (35% before), over 3 points at 19% (18%), cost vs. best −7.8 (−7.6).
  - Your choice against the typical one fell from +2.6 to +1.8. A stronger opponent model expects better choices, so the same choices stand out less.
  - The opponent's replies valued exactly still cover 42% of their chance (below).

## Task 2: the win model on Reg M-C

Trained on Reg M-C's 47,621 training games alone: the bring model, then the features, then the average of 10 models (`202837c`, overnight 15–16 Nov).

| | Reg M-C, validation | Reg M-C, test | Reg M-A, validation | Reg M-B, validation |
|---|---|---|---|---|
| decision points | 122,959 | 116,856 | 173,070 | 7,477 (small) |
| Brier [95%] | 0.1775 [0.1745, 0.1805] | 0.1776 [0.1745, 0.1806] | 0.1807 | 0.1652 |
| v0 | 0.2075 | 0.2075 | 0.2099 | 0.2033 |
| model − v0 | −0.0300 [−0.0318, −0.0283] | −0.0299 [−0.0319, −0.0280] | −0.0291 | −0.0381 |
| largest calibration gap | 0.015 | 0.016 | 0.017 | 0.081 (within its interval: small sample) |
| sheets hidden: Brier | 0.1810 | 0.1817 | 0.1878 | 0.1779 |

- **The gate passes on both splits.** Every calibration band is within 0.05, and the model beats v0 with room to spare.
- **The test split agrees with validation** within 0.0001 on the main model and 0.0007 with sheets hidden.
- **The average of 10 has 1.0 point of its own noise**, under the 3-point reporting threshold.

## Task 3: the other models and the strength

**Reg M-C's own choice, lead, forced-switch and bring models**, against a uniform guess (log chance of what the player did; higher is better):

| | validation | test | uniform | likeliest right (validation / test) |
|---|---|---|---|---|
| choices | −1.908 | −1.896 | −2.458 | 30.5% / 31.1% |
| the pair that led | −2.386 | −2.383 | −2.708 | 28.5% / 29.1% (uniform 6.7%) |
| the Pokémon sent in | −0.883 | −0.880 | −1.279 | 56.9% / 56.5% (uniform 28.1%) |
| the four brought | −2.278 | −2.259 | −2.708 | 32% / 32% |

- All beat a uniform guess on both splits, so the choice model's gate is met.
- The tool picks each game's format's own models by itself (`202837c`); Reg M-A's and M-B's are untouched.

**The strength** (how much the opponent model expects players to pick the plays worth more):
- **Reg M-C's own: 9.6** on 92 training games (resampling the games: 8.2 to 11.5), against 6.55 for M-A and M-B. At 6.55, the model rated M-C players 1.2 points a choice below how they play. **Revision 14** (`37bb585`, your decision of 16 Nov): each format uses its own.
- **By rating** (your direction of 16 Nov): 603 training games sampled band by band, 3,697 choices whose player's rating the log shows (`050c495`):

  | Player's rating | Games | Strength [95%] |
  |---|---|---|
  | under 1100 | 180 | 7.9 [6.6, 9.4] |
  | 1100 to 1299 | 240 | 8.3 [6.9, 9.9] |
  | 1300 to 1499 | 263 | 10.1 [8.6, 11.5] |
  | 1500 and up | 171 | 9.9 [8.1, 12.3] |

  As one line: 8.7 at 1200, +0.32 for every 100 points (95% range −0.05 to +0.73). A line fits better than one strength for everyone (p ≈ 0.015). **Revision 15** (`a2b37e7`, approved 17 Nov) uses the line, with the rating held within 1000 to 1700. Without a rating, a player keeps the format's own strength. The analysis, the replay report and the advice all use it (`a9c91fb`).

## Task 4: two checks on the Reg M-C corpus

**A few accounts play a lot** (`bed46ec`). The three busiest training accounts are in 10.3% of training games and 9.2% of validation games. Each model was trained three ways: on everything; without their 2,073 sets; and, as the control, without 2,073 sets drawn at random.
- **Win model:** without them against the control, Brier +0.0003 [−0.0001, +0.0007], no change beyond the noise. On validation games with one of them: +0.0010 [−0.0003, +0.0023].
- **Choice model:** +0.0007 in log chance without them. That is measurable, but about a tenth of a percent of the model's edge over a uniform guess (0.56).
- **No cap on games per player is needed.**

**By rating band.** Each game's rating is its two players' average, from the log's player lines. That covers 88% of validation games; the replay page's single number covers about a third.

| Rating | Games | Win model Brier [95%] | Against v0 | Choice model log chance |
|---|---|---|---|---|
| under 1100 | 858 | 0.179 [0.172, 0.186] | −0.026 | −1.915 |
| 1100 to 1299 | 2,660 | 0.182 [0.178, 0.186] | −0.030 | −1.914 |
| 1300 to 1499 | 1,609 | 0.173 [0.167, 0.178] | −0.033 | −1.871 |
| 1500 and up | 234 | 0.165 [0.153, 0.178] | −0.035 | −1.852 |
| no rating shown | 700 | 0.176 [0.166, 0.185] | −0.025 | −1.893 |

- **Both models do at least as well on higher-rated games.** That is good news for a bot aiming at 1750.
- **Above 1700 there are too few games to score:** 30 training games in all.

## Task 5: the runbook

**Runbook §28** gives the commands for a new regulation's models, after §27's data steps. It also covers the corpus checks, the strength by rating, and opening a test split (`00c8b29`, `ec5073f`, `ad75012`, `1dc2c98`). Every long run now shows its progress on screen, with a second window following the log.

## Surprises

- **Players rarely take the best play.** Once every play is compared, they take it 11–22% of the time, and the best is one they rarely make at 36–47% of decisions. The usual 10 had hidden that: cost vs. best went from −6.2 to −8.5 points in Reg M-A and from −7.0 to −10.8 in Reg M-B.
- **The two-pass search saves only half the time.** It was expected to save more. The first pass is quick, but valuing the finalists against every reply dominates. A few turns take close to an hour.
- **On Reg M-C, the opponent's likely replies are spread thin.** Those valued exactly cover 42% of their chance, against 85% on M-A and M-B; the rest are drawn. The numbers stay unbiased but are noisier. Reg M-C players have more options a turn.
- **Reg M-C players read each other better.** Their strength is 9.6 against 6.55, and it rises with rating.
- **The ratings were there all along.** Each player's rating is in the log's player lines on 85% of Reg M-C games; the replay page shows one on only a third.
- **Two crashes, both fixed:**
  - The every-play run stopped after 10 games when the damage calculator's process died, most likely from memory. It now restarts once and caps its cache (`b275902`).
  - Reg M-C's summary came out empty, because the summary knew only M-A and M-B (`617be61`).
- **The test split agrees with validation** to within 0.0001 on the win model.

## For you

1. **Decided this week:**
   - revision 13, every play compared (15 Nov);
   - revision 14, each format's own strength, Reg M-C 9.6 (16 Nov);
   - opening Reg M-C's test split once (16 Nov);
   - revision 15, the strength by rating (17 Nov).
2. **Decided 17 Nov: the ladder plan stands.** You accept the risk that Showdown's October bot policy puts on an unlabelled bot: the account stays `chasevgc`, with no bot name and no message to Showdown's staff. You also noted Reg M-C ends on 2 December. A ladder pilot after that date needs the next regulation's data and models first (runbook §27–28).
3. **Next, Phase 3: the bot.** The first problem is its clock (55 seconds a turn). Comparing every play takes about 3.5 times as long as before, and some turns take minutes. The search has to get faster, or stop early and say how far it got (revision 13 allows that).
4. **Your guaranteed-win test cases:** the template is ready in your docs. Each case you mark "Ready for Claude" becomes an automated test.
