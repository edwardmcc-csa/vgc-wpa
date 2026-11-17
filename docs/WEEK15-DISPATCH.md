# Week 15 — Dispatch Brief (Reg M-C, part 2: the models; better plays, not copied ones)

**Status:** done 17 Nov 2026 (report: `docs/WEEK15-REPORT.md`). Drafted 15 Nov 2026, after Week 14's report and the PO's two decisions
of the same morning. From plan revision 4, Phase 2. **Started 15 Nov** with Task 1
(revision 13 in the code, `872136c`, `e2c82a2`). The code for Tasks 1 to 3 is
committed (`b275902`, `202837c`), with runbook §28 (`00c8b29`). The overnight
runs (`build\w15\w15_run.cmd`) ran from 15 Nov 12:20 PM to 16 Nov 1:13 AM, all 12
steps. **Phase 2's gate on Reg M-C: passed on validation and on the test split**
(opened once, 16 Nov, with the PO's approval; below). One decision for the PO:
DEFINITIONS revision 15, the strength by the player's rating (Task 3).
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.
**Gate (Phase 2):** the same checks as Reg M-A and M-B, on Reg M-C's validation
split:
- the win model's calibration;
- beating the baselines (the win model against v0, the choice model against
  choosing uniformly);
- the resolver check, already met: 92.9% found at a cap of 3,000.

## Why

The bot must play Reg M-C, and every model it uses was trained on M-A and M-B.
And the PO set a principle on 15 Nov (DEFINITIONS revision 13): **the model should
not imitate the players it learns from; it should find the plays that would have
improved their position.** Today, judging a play and the live advice look only at
the 10 choices players most often make, out of a median of 90 the rules allow.

## Decisions (PO, 15 Nov 2026)

1. **The resolver check keeps 3,000 boards a turn** (`32f6af4`). The advice and
   the replay report keep 300 until Phase 3 measures the clock.
2. **DEFINITIONS revision 13 approved** (`111f864`): cost vs. best over every
   choice the rules allow. The choice model predicts the opponent, the typical
   choice and the search order, and never sets the standard. The advice and the
   bot choose by win chance alone.
3. **The strength should follow the opponent's rating** (PO, 16 Nov: "If the
   opponents ELO is known, we should scale up/down accordingly"). Measured first
   (Task 3); then a DEFINITIONS §7 revision for approval.
4. **Each format has its own strength; Reg M-C's is 9.6** (PO, 16 Nov: "Default
   of 9.6 is fine"). DEFINITIONS revision 14 (`37bb585`). Reg M-A and M-B keep
   the 6.55 they share. In the code since `050c495`.
5. **Reg M-C's test split may be opened once** for Phase 2's final numbers (PO,
   16 Nov: "Yes"; the sixth opening, logged). `python -m wpa.final_test` scores
   every model in use with the gate's checks; it runs tonight after the
   strength-by-rating run, after a trial of the same command on validation.
   Done 16 Nov, 7:30 PM (`63eed44`); one opening logged.
6. **The ladder plan stands** (PO, 17 Nov: "Accept the risk"). Showdown's October
   bot policy makes an unlabelled bot bannable; the account stays `chasevgc`, no
   bot name, no message to Showdown's staff. The PO noted Reg M-C ends on 2
   December.

## Tasks

### Task 1 — Revision 13 in the code: every choice, not the usual ten
Tests first, shown failing.
- [x] **The replay report and the analysis:** cost vs. best against every joint
      choice the rules allow, each valued against the opponent's likely replies.
      *(872136c)*
      - The report names the best choice and what it would have gained.
      - It marks a best choice that is outside the 10 the choice model finds
        likeliest ("a play players rarely make").
- [x] **The live advice:** every choice ranked by win chance, within a time
      budget. *(872136c)*
      - A first pass values every choice quickly (the likeliest outcome, a small
        cap).
      - A second pass values the best few in full.
      - Neither pass drops a choice for being unusual, and the advice says how
        many it valued.
- [x] **What it changes, per format, on the validation sample** (running: 15
      Reg M-A and 15 Reg M-B validation sets, with every choice and with the usual
      10; Reg M-C once its models are trained, Task 2):
      - how often the best choice lies outside the 10 likeliest;
      - what it is worth when it does (the median, and the share over the
        3-point reporting threshold);
      - the time per decision point, before and after.
      - *So far (10 Reg M-A games, 172 decision points):* valuing every choice
        in full took 162 s a decision point, against 24 s for the usual 10
        (about 7 times). The best play was one players rarely make at 31% of
        decision points; it beat the best of the usual 10 by over 3 points at
        23% (median 0, most 41). The full run stopped after those 10 games (the
        calculator's process died; it now restarts, `b275902`). The quicker
        two-pass way is step 1 of the overnight runs, on the same 30 sets.
      - *The two-pass way on the same 10 games:* 86 s a decision point (about
        half the full comparison). Same best play at 86% of decision points.
        Its cost vs. best is within 1 point of the full comparison's at 72%,
        about as close as two runs of the old way agree with each other (74%;
        the opponent's less likely replies are drawn at random). It misses a
        better play by over 3 points at 7 of 152 (5%), by 10 at most. The
        share over 3 points is unchanged (22% against 23%). On 40 games so
        far it runs about 4 times the old way (103 s against 26 s).
      - *Step 1 done (two-pass, all 30 sets, 15 Nov 4:54 PM):*
        - Reg M-A (408 decision points): the best play is one players rarely
          make at 40%; it beats the best of the usual 10 by over 3 points at
          24%. Cost vs. best goes from −6.2 to −8.5 points; best choice taken
          from 32% to 22%; a cost of 5+ points from 35% to 47%.
        - Reg M-B (360): rarely made at 47%; over 3 points at 32%. Cost vs.
          best from −7.0 to −10.8; best taken from 22% to 11%; 5+ points from
          40% to 56%.
        - Cost vs. typical (the fairness number) is unchanged: +2.0 and +0.7.
        - Time per turn: median 128 s and 155 s (35 s and 45 s before). A few
          turns are very slow (slowest 61 and 74 minutes; 9 and 18 turns over
          10 minutes).
      - *Reg M-C (15 validation sets, 34 games, 580 decision points; its own
        models):* rarely made at 35%; over 3 points at 18%. Cost vs. best
        −7.6 (−5.8 against the usual 10); best taken 21% (31%); 5+ points
        51%. Median 113 s a turn. Its summary first came out empty: the
        summary listed M-A and M-B only (fixed, `617be61`).
      - *Something to know on Reg M-C:* the opponent's replies valued
        exactly cover 42% of the chance on average (85% on M-A and M-B); the
        rest are drawn. Reg M-C's choice model spreads its chance over more
        joint choices. The numbers stay unbiased but noisier; covering more
        replies costs time (a Phase 3 question with the clock).
- [x] Cost vs. typical, the split in §3 and the opponent model in §7 are
      unchanged (tests guard them; 1,066 pass).

### Task 2 — The win probability model on Reg M-C
- [x] **The bring model** on Reg M-C's training sets, then Reg M-C's features (the
      v4 table: who was brought, best-of-three memory, this turn, the board).
- [x] **The averaged model** (as Reg M-A's), trained on Reg M-C alone. It has
      47,621 training games, so it needs no pooling, unlike Reg M-B.
- [x] **Sheets hidden** (`WP_public`, the opponent's sheet blanked) and **team
      preview**, as for Reg M-A and M-B.
- [x] **Gate, on validation:**
      - calibration, under the rule since Week 8 (a bin more than 0.05 off is
        reported, not failed, when its interval reaches back within 0.05);
      - a Brier score better than v0's, with the 95% interval;
      - side by side with Reg M-A's and Reg M-B's numbers.
      - *Result (`models_v4_avg\report_regmc.txt`): passed.* Brier 0.1775
        [0.1745, 0.1805] against v0's 0.2075, a gain of 0.0300 [0.0283,
        0.0318]; every calibration bin within 0.05 (the largest gap 0.015).
        Reg M-A: 0.1807 against 0.2099; Reg M-B: 0.1652 against 0.2033 (small
        sample). Noise of the average: 1.0 point, under the 3-point threshold.
      - *Sheets hidden (`models_v4_preview\report_regmc.txt`): passed.* Brier
        0.1810 against v0's 0.2075 (M-A 0.1878, M-B 0.1779).
      - *The bring model:* the four brought, log chance −2.278 against
        uniform −2.708 on validation; its likeliest four right 32%.
      - *The test split (opened once, 16 Nov; `reports\test_regmc.txt`): the
        gate passed.* Averaged win model Brier 0.1776 [0.1745, 0.1806] against
        v0's 0.2075, a gain of 0.0299 [0.0280, 0.0319], every calibration bin
        within 0.05 (largest gap 0.016); sheets hidden 0.1817; the bring model
        −2.259 against −2.708. On validation these were 0.1775, 0.1810 and
        −2.278: the test split agrees.

### Task 3 — The choice, lead and replacement models and the strength on Reg M-C
- [x] **The choice model** on Reg M-C's training games, with M-C's moves (its own
      copy of Showdown's code). Gate: it beats choosing uniformly on validation.
      *Passed:* log chance −1.908 against uniform −2.458 on 23,272 choices;
      its likeliest option right 30.5%.
- [x] **The lead and replacement models** on Reg M-C. *Both beat uniform:* the
      pair led −2.386 against −2.708 (likeliest pair right 28.5%, uniform
      6.7%); the Pokemon sent in −0.883 against −1.279 (right 56.9%, uniform
      28.1%). *On the test split:* choices −1.896 against −2.458 (likeliest
      right 31.1%, 133,647 choices); leads −2.383 against −2.708 (29.1%);
      forced switches −0.880 against −1.278 (56.5%).
- [x] **The strength** (DEFINITIONS §7) fitted on Reg M-C's training games and
      reported beside M-A's (6.3) and M-B's (6.8). §7 says one strength serves
      every format. If M-C's own differs by more than 1, that is a DEFINITIONS
      question for the PO, not a silent change.
      - *Measured: 9.6* on 92 training games, 976 choices (resampling the
        games: 8.2 to 11.5). It differs from the one in use (6.55) by 3.1, so
        **this is the PO's decision.** At 6.55 the model rates Reg M-C
        players' choices 1.2 points a choice below how they play. The one in
        use stays until the PO decides.
      - *By rating (the PO's direction, 16 Nov).* Each player's rating is in
        the log's player lines on about 85% of Reg M-C games (the replay page
        shows one number on about a third). A first look on the 92 games:
        9.3 under 1150, 9.6 from 1150 to 1299, 10.3 from 1300 (20 to 45 games
        each: too few to tell). The measurement: 150 training games in each
        of four bands, fitted by the rating of the player choosing, per band
        and as a line (about 9 hours). Training games by rating: 7,154 under
        1100; 21,344 from 1100 to 1299; 12,277 from 1300 to 1499; 1,142 from
        1500 to 1699; **30 at 1700 and up** (the bot's target is 1750).
      - *Measured (16 Nov, 603 games, 3,697 rated choices):* 7.9 [6.6, 9.4]
        under 1100; 8.3 [6.9, 9.9] at 1100 to 1299; 10.1 [8.6, 11.5] at 1300
        to 1499; 9.9 [8.1, 12.3] at 1500 and up. As a line: 8.7 at 1200, +0.32
        per 100 points (95% range −0.05 to +0.73; likelihood ratio p ≈ 0.015).
        Likely, modest, uncertain in size. **DEFINITIONS revision 15 drafted
        for the PO** (`claude/DEFINITIONS-REV15-DRAFT.md`): the line, the
        rating held within 1000 to 1700, 9.6 without a rating.
- [x] The replay report and the advice on an M-C game use M-C's models.

### Task 4 — Two checks on the Reg M-C corpus (raised in Week 14's report)
- [x] **A few accounts play a lot.** The three busiest training accounts are in
      10.3% of training games and 9.2% of validation games. Each model trained
      without their 2,073 sets, against a control dropping 2,073 sets at random
      (`reports\corpus_checks_mc.txt`, `bed46ec`):
      - the win model: Brier +0.0003 [−0.0001, +0.0007], no change beyond the
        noise; on validation games with them +0.0010 [−0.0003, +0.0023];
      - the choice model: +0.0007 in mean log chance without them (the model's
        edge over a uniform guess is 0.56): measurable, but about a tenth of a
        percent of that edge.
      - **No cap on games per player is needed.**
- [x] **The ladder is mostly below the target.** The win model's and the choice
      model's scores by rating band, where a game shows a rating (36% do;
      median 1,174).
      - *First run, by the replay page's rating (a third of games):* the win
        model is about as good in every band (Brier 0.175 to 0.179, about 0.03
        better than v0 in each; 1500 and up: 51 games only). The choice model
        predicts higher-rated players a little better (log chance −1.918 under
        1100, −1.904, −1.871, −1.846 at 1500 and up).
      - *By each game's two players' average rating (88% of validation
        games, `c2ccf7f`):*

        | Rating | Games | Win model Brier [95%] | Against v0 | Choice model log chance |
        | --- | --- | --- | --- | --- |
        | under 1100 | 858 | 0.179 [0.172, 0.186] | −0.026 | −1.915 |
        | 1100 to 1299 | 2,660 | 0.182 [0.178, 0.186] | −0.030 | −1.914 |
        | 1300 to 1499 | 1,609 | 0.173 [0.167, 0.178] | −0.033 | −1.871 |
        | 1500 and up | 234 | 0.165 [0.153, 0.178] | −0.035 | −1.852 |
        | no rating shown | 700 | 0.176 [0.166, 0.185] | −0.025 | −1.893 |

        Both models do at least as well on higher-rated games: the win model's
        Brier falls from 0.182 to 0.165 and its lead over v0 grows; the choice
        model predicts higher-rated players a little better. Above 1700 there
        are too few games to score.

### Task 5 — Runbook and report
- [x] **Runbook §28:** the models for a new regulation, after §27's data steps,
      so the next rotation trains with the same commands. *(00c8b29)*
- [x] One report in prose, per format, with a surprises section, and Phase 2's
      gate. *(`docs/WEEK15-REPORT.md`, 17 Nov)*

## Runs on the PO's computer

- **Features and the models on Reg M-C:** about 3 to 4 hours, overnight, from one
  file to double-click, as in Week 14.
- **The validation sample with every choice (Task 1):** about 9 times today's
  analysis time, which will be measured first on a few games.

## For the PO

1. **Leave your computer on** for the overnight runs.
2. **Opening Reg M-C's test split once:** approved 16 Nov (decision 5).
