# Week 13 — Dispatch Brief (damage from the spreads players run; the rules still modelled in part)

**Status:** approved by the PO on 14 Nov 2026 ("Go"). Drafted 13 Nov from his
decisions that evening; Week 12's report is in (`docs/WEEK12-REPORT.md`).
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.
**Gate** (plan revision 4, Phase 1): on the resolver check, HP misses down by at
least a third, and moves modelled in part on under 0.5% of turns, per format.

## Why

Week 12 brought the resolver to fully right on 81% of Reg M-A turns and 85% of
Reg M-B turns. What is left (diagnosed 13 Nov, 120 missed turns):

- **HP off by more than 6 points: 14.4% and 12.5% of turns,** typically by 12
  points. On those turns the resolver hit harder than what happened 70% of the
  time.
- **The typical hit is estimated right; the misses are a one-sided tail.** On
  every clean single hit in a sample of 400 fully modelled turns (84 hits,
  found or not), real damage was a median 0.99 of the estimate. But when the
  estimate was off by more than 10%, it was too high in 31% of hits and too low
  in 17%.
- **The likely cause is the hidden spreads.** The resolver values a hit with
  each Pokemon's likeliest spread from the usage statistics, usually all-out
  offence. Most players run it, so the typical hit is right; those who don't
  lean toward bulk and away from full offence, and both only make hits weaker.
  That tail is what the likeliest spread alone cannot cover, and the error
  lands in the dice.
- **Moves and effects still modelled in part: 1.7% and 0.6% of turns,** none
  more than about 10 turns per format.

## Decisions (PO, 13 Nov 2026)

1. **DEFINITIONS revision 11 is approved** (§7: the stronger opponent model,
   strength 6.55). Committed as `bdfa065`.
2. **Week 13 takes the spread fix** suggested from the diagnosis.
3. **The remaining moves come before the bot** (Task 2).
4. **The order after Week 13: Reg M-C modelled, then the bot (M6).** The bot
   plays on Showdown, for quality control and evaluation of the engine (sketched
   under "Later" so it is not lost).
5. **The PO's current team is loaded into the tool** (Task 3). He sent it on
   13 Nov; its paste was written and all 36 stats checked that evening.

## Tasks

### Task 1 — Damage from the spreads players run
- [ ] **First, the forms the statistics count under their species** (found 13
      Nov). The statistics count Sinistcha-Masterpiece as Sinistcha (in 96 of
      the 892 games) and Maushold-Four as Maushold (46). Looked up under their
      own names they get the spread for a Pokemon the statistics do not list:
      full HP and full Special Attack, where real Sinistchas are Bold or Calm
      with points in the defences. So hits on them are valued too strong. The
      spread is taken from the species, then the resolver check is run before
      and after. The win model's features change for these Pokemon too: they
      take it at the next retraining (Reg M-C), which is measured then.
- [ ] **Measure the bias on more hits** (13 Nov's sample had 84): every clean
      single hit in the resolver check's games (no item, ability, weather or
      second hit on the target that turn): real damage against the estimate,
      per format, single-target and spread moves apart, the median and the
      tails.
- [ ] **A hit's damage is weighed over the spreads players run** (each spread's
      chance from the spread belief, refined by the game so far as now),
      instead of the likeliest spread alone. Week 12 Task 4's branching where a
      knock-out depends on the spread stays.
- [ ] **If that is too slow** (the stop rule: more than 1.5 times the resolver's
      time per turn), report the cost and the options. A flat correction is not
      one: the typical hit is already right, so it would break it.
- [ ] **The resolver check before and after**, on the same 892 games: HP misses,
      knock-out misses, the bias on clean hits, the time.
- [ ] Tests first, each shown failing.

### Task 2 — The rules still modelled in part
Every move or effect the resolver check still marks partly modelled, in either
format (turns at `7df9b1d`, Reg M-A / Reg M-B):

- [ ] Skill Swap (9 / 2), Entrainment (6 / 0): abilities change hands or are
      replaced.
- [ ] Transform (7 / 2): copies the target's species, stats (but HP), moves and
      boosts.
- [ ] Gravity (7 / 0): everything grounded, accuracy up, some moves blocked.
- [ ] Imprison (7 / 0): the foes cannot use the moves the user knows.
- [ ] The Pokemon sent in after a pivot move (7 / 10): which one, by the
      replacement model, as a forced switch is. Done ahead (`189aac7`): a
      Prankster Parting Shot into a Dark type and a sound move into Soundproof
      fail without switching (5 of these turns). Left: Magic Bounce (about 4),
      and turns where the switch depends on a branch (a Protect that fails).
- [ ] A Substitute's hit points (7 / 0), and Leech Seed healing whatever stands
      in the seeder's place (7 / 1).
- [ ] Curse (5 / 1), Stockpile (5 / 4), Stealth Rock (5 / 0), Heal Block (3 / 0),
      Ally Switch (0 / 2), Power Swap (0 / 2), Focus Energy, Tidy Up, Magic
      Powder and Cute Charm (one turn or so each).
- [ ] Each against Showdown's Champions data, with a test first, shown failing.
      The resolver check before and after.

### Task 3 — The PO's team, loaded in (done ahead, `5d13538` and `50e3ba8`)
- [x] **The tool keeps the PO's team** (`my_team.txt`, outside git): the advice,
      the session and the replay report use it without `--team`.
- [x] **His nicknames in the advice** (End Game, Mia), not only the species.
- [x] **A check of a team paste against the app's Stats screen:** each
      Pokemon's six stats at level 50 from its stat points and nature, to set
      beside the screen, and the stat points add up to 66 at most.
- [x] **A warning when the team has what the format's data has not seen** (on
      13 Nov: Golisopod is in neither Reg M-A's nor Reg M-B's statistics, and
      female Basculegion is under 1%): the advice says its numbers are rough.
      A species counts its Mega forms (Raichu-Mega-X is a Raichu).
- [x] Tests first, each shown failing. `python -m wpa.team_check`, Runbook
      Section 25.

### Task 4 — The report
- [ ] Per format throughout. The test split stays closed.

## Later (not this week)

- **Reg M-C, next:** what it needs is in `docs/REG-MC-GAPS.md` (24 new Pokemon,
  6 Megas, about a dozen abilities, 12 items, 15 moves). The PO's ladder games
  are M-C, so the advice is approximate there until it is modelled.
- **Then M6: the engine plays on Showdown.**
  - The engine as a player on M2's harness: it picks four and leads as the
    advice does, and takes the choice worth the most against the likely
    replies.
  - Against random, "the strongest move" and the choice model (plays as
    players typically do; beating it is the real test).
  - The plan's gates: beats random in 90% of 200 games or more, the strongest
    move in more than 55%.
  - Quality control from its games, where every spread is known: a board the
    resolver misses there is a rules gap; the win model's calibration on games
    unlike the corpus; no crashes or illegal choices.
  - Teams: the most used teams per format, and the PO's.
  - The PO is fine with Showdown for these games.
- **Turn-by-turn advice from the app's screen.**
