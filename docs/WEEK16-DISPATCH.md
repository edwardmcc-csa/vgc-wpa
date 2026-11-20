# Week 16 — Dispatch Brief (Phase 3, part 1: the bot plays, within the clock)

**Status:** approved by the PO 17 Nov 2026 ("Go ahead"); started the same day.
From plan revision 4, Phase 3.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.
**Gate (Phase 3, over Weeks 16–17):** on the local server, Reg M-C, closed team
sheets:
- 90% or more against random over 200 games;
- more than 55% against "the strongest move";
- better than even against the choice model (plays as people typically do),
  with its 95% interval above 50%;
- no crashes, illegal choices or timeouts.

This week aims at the first two and the clock. The third may need Week 17.

## Why

The engine can advise; now it has to play whole games on its own, inside
Showdown's clock: 90 seconds for team preview, at most 55 seconds a turn, and 7
minutes of thinking in all per game. Since revision 13 it compares every play:
the after-game analysis now takes a median of about 2 minutes a turn for both
players' choices, and some turns take most of an hour. So the clock comes first.

## Decisions this brief relies on

- **Revision 13:** the bot chooses by win chance alone, over every play the rules
  allow. When time is short, it searches the likeliest plays first and says how
  many it searched.
- **Revision 15:** the opponent model expects the opponent's strength from their
  rating where the ladder shows it. On the local server there is no rating, so
  Reg M-C's own strength (9.6) is used.
- **The ladder plan stands** (17 Nov), and Reg M-C ends on 2 December (below).

## Tasks

### Task 1 — The engine as a player
Tests first, shown failing.
- [ ] **Team preview:** the four it brings and the two it leads (the advice's
      own choices), and it denies open team sheets.
- [ ] **Each turn and each forced switch:** the best play by win chance.
- [ ] Plays on the local Showdown server with Reg M-C's rules (its own pinned
      copy), through the existing harness.
- [ ] **Only legal choices,** checked against Showdown's own request every turn.
      If something goes wrong, it falls back to a legal choice and logs why. It
      never stalls.

### Task 2 — Within the clock
- [ ] **Measure first:** time per turn of today's advice on the local server, at
      a cap of 300 boards. That means the typical turn, the slowest 1%, and a
      whole game.
- [ ] **A time budget per turn,** from the game clock left: a share of what
      remains, never over 45 seconds.
      - The search goes likeliest plays first and stops at the budget. It plays
        the best found so far.
      - It records how many plays it valued and whether it stopped early.
- [ ] **Gate:** no timeouts in 200 games. Report how often the search stopped
      early and what it left unvalued.

### Task 3 — The opponents
- [ ] **Random:** a legal choice at random.
- [ ] **The strongest move:** each Pokémon's most damaging move at the likeliest
      target.
- [ ] **The choice model:** plays as people typically do, by sampling the choice
      model.
- [ ] **The engine at strength 0:** the same bot, with an opponent model that
      expects typical play.

### Task 4 — The teams and the matches
- [ ] **Teams:** both sides draw from the same pool of popular Reg M-C teams,
      taken from rated games of 1500 and up in the training split. Every pairing
      is played from both sides, so neither side gets the better teams. The
      bot's own team is Phase 4's work.
- [ ] **200 games against random,** then **200 against the strongest move**,
      with 95% intervals. Then the choice model, as far as time allows.

### Task 5 — Quality control on the bot's own games
- [ ] **The resolver check on its games.** Every team's exact sets are known
      there, so an HP miss is a rules gap, not a guessed spread (Week 13's open
      question).
- [ ] **The win model's calibration** on these games. They are unlike the corpus
      (random and greedy opponents), so it should be read with that in mind.
- [ ] **A count of crashes, illegal choices and timeouts:** the gate wants zero.

### Task 6 — Ready for the next regulation (parallel, small)
- [ ] Reg M-C ends on 2 December. Find what replaces it and when Showdown's
      ladder opens for it. List what its rules add, as `REG-MC-GAPS.md` did.
- [ ] Once its ladder has enough uploaded games, the download and the
      runbook's §27–28 steps run overnight on your computer, about two days of
      runs. That is likely Week 17's to start.

### Task 7 — Runbook and report
- [ ] **Runbook §29:** how to play the bot locally and read its results.
- [ ] One report in prose, with a surprises section and where the gate stands.

## Runs on your computer

- **The matches:** 6 games at a time. Against random, a few hours; against the
  strongest move and the choice model, overnight each.
- **The resolver check on the bot's games:** under an hour.

## For you

1. **Approved** 17 Nov.
2. **Leave your computer on** for the overnight matches.
3. **Your guaranteed-win test cases** fit here: each one becomes a test the bot
   must pass.
