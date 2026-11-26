# Week 18 — Dispatch Brief: speed's worth next turn, Fake Out, and the team

**Status:** done 26 Nov 2026 (approved 23 Nov: "Agreed"; Task 5 on M-C, "Yes,
choose a team now"). Report: `claude/WEEK18-REPORT.md`. Task 6 carried: Showdown
has no M-D yet.
From plan revision 4 (Phase 3 is done; Phase 4 is the team) and the PO's notes
of 22 and 23 Nov.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

Phase 3 closed this week: 600 games on time, every bar met. What still loses
games against a strong player is reading and timing: the engine under-expects
Fake Out, and it values Tailwind (and other plays that pay off next turn) only
through how the win model reads the board after the turn. Your rule for
Tailwind (23 Nov) asks the right question: will going first next turn change
what happens? This week builds that check, fixes the Fake Out reading, and
starts Phase 4 on M-C as a dry run, since M-D's rules are not out yet.

## Tasks

### Task 1 — Speed's worth next turn (the PO's rule, 23 Nov) (measured 23 Nov; not built, the PO's call: "Agreed")
Measured first: where Tailwind could be set, 1500+ players set it 24% of the time
when it makes one of theirs outspeed a foe, 19% when theirs already outspeed
both foes on the field, 5% when too slow even with it; the bot 28%, 17% and 0%.
A rule counting only next turn would remove Tailwinds good players make, so
today's late-Tailwind rule stays.
Tests first, shown failing.
- [x] (not built: the PO's call, 23 Nov) **A second turn, for Tailwind only.** For each likely result of this
      turn, next turn played twice, with and without Tailwind, with each
      side's likely plays. Tailwind gets the difference: zero unless the
      order flips and that changes a KO (a roll to kill, with damage ranges
      and crits) or a flinch (Fake Out, Iron Head, Rock Slide only work
      going first); and zero if no Pokemon on its side lives to use it.
- [x] (not built, as above) **Waiting out a timer:** the opponent's likely Protect while Trick Room,
      a status or Leftovers runs, counted with the turns each has left.
- [x] (measured before building, above) **Compared with today's rule** (valued last, and it loses a near tie): on
      the gate games' Tailwinds and on 1500+ players' Tailwinds. Kept only if
      it agrees with good players more often, and stays within the clock.
- [x] (dropped with the rule) **Measured, not built:** whether the same check would help Electro
      Shot's charging turn and Protect-stalling Trick Room.

### Task 2 — Fake Out (cause found 23 Nov: the choice model's ridge; refit ready, in use after the team run and a strength re-measure; the PO: "Agreed")
- [x] (the ridge: 0.01 for every choice held a rare play's weight down) **Why the opponent model under-expects it** (33% expected, 48% used, on a
      Pokemon's first turn out) and cannot tell when it comes: the features
      it has (first turn, the target, the partner's threat, the species' own
      rate of using it).
- [x] (`9925d26`; expected 47% against 47% used, log chance -1.915 to -1.875; retrained 23 Nov; head-to-head 106 of 200; 626 turn 1 still prefers attacking) **A fix**, measured on validation games, then the choice model retrained
      on M-C with it. The test for your game 626 turn 1 says whether it is
      enough.

### Task 3 — Nearly lost games
- [x] (measured 23 Nov, not built: under 5%, players won 0 of 89) When every play is worth under about 5%, choose by the best long shot (a
      crit, a miss): the chance of reaching a board worth 50% or more, with
      more samples. Measured on lost positions in the corpus before it is used.

### Task 4 — Rules and leftovers from Week 17
- [x] (`bad9a8d`) **A Pokemon that must recharge** (Hyper Beam): its only option is the
      recharge. 40 of the gate's 66 replaced choices were this.
- [x] (`fc1b66e`: one pair's resolve, up to 15 s, and valuing its boards; both stop now) **The hard limit's late step:** what ran about 25 seconds past the
      deadline in 9 of 800 games.
- [x] (21% low; the cause, merged boards kept the first board's hit points, fixed in `64214fc`: 5.7% low) **The damage estimate** on the bot's own games (low on 27% of hits in
      Week 16): one look, with the PP and charging fixes in.

### Task 5 — Phase 4 begins: the team (on M-C, as a dry run)
- [x] **Candidates:** the most used and best-placed teams of the regulation,
      from usage statistics and tournament results (about 8). (23 Nov: the
      eight pool teams whose 1500+ players won most, by the low end of the 95%
      interval, on training and validation games: pool teams 14, 40, 12, 31,
      28, 11, 2 and 3; teams 2 and 3 are also the second and third most used.
      The tournament pages tried, pokemon-zone.com and champdex.com, refused
      the fetch, so no tournament team is in yet; one can be added to the pool.)
- [x] (round 1: 8 teams x 80 games; round 2: the top four x 200; team 40 57%, 51% to 64%) **A round robin on the local server:** each candidate as the bot's team
      against the pool of 40, with 95% intervals. The tool should rerun on M-D
      unchanged. (Built 23 Nov: `--vs engine --team N`, `--table`, and
      `--format`; each candidate plays 80 games, each pool team twice, the
      engine itself on the other side, so the team is what differs.
      `build\w18\w18_teams.cmd`, about 13 hours.)
- [x] (on M-C: team 40; reruns on the pilot's regulation) Phase 4's gate (the team chosen beats the field of top teams) is for the
      regulation the ladder pilot will play, likely M-D.

### Task 6 — Reg M-D (carried)
- [ ] When Showdown has M-D: the pinned copy updated (your yes), what M-D adds
      listed as REG-MC-GAPS.md did, and its games downloaded once the ladder
      has enough.

### Task 7 — Runbook and report
- [x] (section 31) Runbook: the second-turn check and its switch, the round robin.
- [x] (26 Nov) One report in prose, with a surprises section and where the gates stand.

## Kept for later
- **Reading app games from video** (experts' recorded games, with creators'
  agreement, and the PO's own), as `APP-CAPTURE-TRIAL.md` did for one game: the
  PO wants it in a future week's brief (24 Nov).
- **Looking further ahead in general** (protecting a win condition over several
  turns): Phase 6. Task 1 is the first narrow piece of it.
- **Speed:** the clock still leaves about 70% of plays unvalued.
- **The "value last" order** for the other rare plays: off since 22 Nov.

## Runs on your computer
- Task 1's comparison, if it needs games: 200 games, the bot with the check
  against the bot without (overnight).
- Task 5's round robin: about 8 teams x 100 games (two or three nights).
- Task 2's retrain of the choice model: under an hour.

## For you
1. **Approve this brief**, or change it.
2. **Task 5:** whether to spend the round robin's nights on M-C now, or wait
   for M-D's rules.
3. **The Showdown update for M-D** needs your yes when it comes.
