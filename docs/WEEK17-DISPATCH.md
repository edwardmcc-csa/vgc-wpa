# Week 17 — Dispatch Brief (Phase 3, part 2): on time every turn, and fewer misplays

**Status:** approved by the PO 20 Nov 2026 ("Week 17 is approved"); started the
same day.
From plan revision 4, Phase 3, and the PO's notes on his games against the bot
(17 Nov).
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.
**Gate (closes Phase 3):** on the local server, Reg M-C, closed team sheets, 200
games against each of random, the strongest move and the choice model:
- no timeouts and no refused choices, in all 600;
- the win rates still meet Week 16's bars (90% or more, over 55%, better than even
  with the 95% interval above 50%).

## Why

Week 16's bot met the three win-rate bars, but 48 turns in 46 games ran past
Showdown's 55 seconds, and every refused choice followed one of them. The cause
is a single step of the search that cannot be stopped part way.

The PO then played it and won every game. His notes point to five patterns:
Protect after Protect, plays whose payoff comes next turn (Electro Shot without
rain, Tailwind), no PP, team preview that never looks at the opponent's six, and
no plan over several turns. Checking them turn by turn also found a bug: a
charge that goes off at once (Electro Shot in rain) was read as still charging,
in one ladder game in five. That is fixed (`d4ab5bf`). This week fixes the
clock, then the cheap ones, and measures the rest.

## Tasks

### Task 1 — On time, every turn (done: `9e9b243`; gate met 21 Nov, 0 timeouts and 0 refused choices in 600 games)
Tests first, shown failing.
- [x] **A stop inside the step that ran late** (weighing the opponent's replies):
      the clock is checked between pairs, not only between batches.
- [x] **Nothing valued yet:** play the likeliest play (the choice model's), never
      wait.
- [x] **A hard limit:** if the advice has not answered 50 seconds into a turn, a
      legal choice is sent and the reason kept.
- [x] **Back in step after a missed turn:** each choice is checked against
      Showdown's latest request, so one late turn cannot spoil the rest of the
      game.

### Task 2 — Shortcuts in the move list
- [x] **Plays that cannot work are removed**, for both sides: Fake Out or First
      Impression after a Pokemon's first turn out. (The PO, 20 Nov: Tailwind
      while one's own is up, and a weather move in that weather, stay possible,
      to play around a switch-in or an opposing weather setter; they are valued
      last instead.)
- [x] **Plays valued last, never removed:** (built; off by default since 22 Nov, the PO's call) attacking one's own partner, and a
      status move into a target that already has one. The PO's cases stay
      possible: Sneasler's White Herb Close Combat into its partner for Unburden,
      U-turn into a partner out of Perish Song, status into a Sucker Punch user,
      Yawn into a target already asleep or drowsy, so that a Pokemon switched in
      there is made drowsy (it punishes the switch).
- [x] Each rule: a test, a switch to turn it off, a count of how often it fires,
      and a check on 1500+ games of how often players made the play it removes.
- [x] **Proof on the server:** the bot with the rules against the bot without, on
      the same pairings. Kept only if it wins as often and values more plays
      within the clock. Result (21 Nov): 93 of 200 (46%, 95% interval 40% to
      53%), 71% of plays left unvalued when the clock stopped it against 73%;
      the engine without them sent a late Fake Out twice, refused. The PO (22
      Nov): keep the late Fake Out removal; the value-last order is off by
      default (`6a4d7fa`).

### Task 3 — Rules from the PO's games
- [x] **A charge that goes off at once leaves no charge** (`d4ab5bf`, with a
      test). It touched 11,879 of 59,471 Reg M-C games and 106 of the bot's 612.
- [x] **Retrain on M-C** (approved 19 Nov, run 19-20 Nov,
      `build\w17\w17_retrain.cmd`; whole suite first: 1,331 passed). Result:
      **today's models stay.** The win model's features came out byte for byte
      the same (the charge is not one of its inputs), so the retrained win
      model is the same model; the forced-switch model's report is unchanged.
      The choice model's table gained 291 choices (1.2%) the misread had
      dropped, but on the same 1,000 validation games read with the fix,
      today's model scores as well as the retrained one (mean log chance
      -1.9145 against -1.9153; likeliest option right 30.2% against 30.0%).
      No strength refit needed. The fix matters at play time, where it is in
      use since `d4ab5bf`.
- [x] **Fake Out** (measured 22 Nov, 42 validation positions: players used it 48%
      of the time, the choice model expected 33%, and its weighing step 32%; it
      does not tell apart when it comes. A fix is for Week 18.) How often the opponent model expects Fake Out on a
      Pokemon's first turn out, against how often players use it. It rated
      Fake Out at 17% in 625 turn 5 and left it out of its likeliest replies in
      626 turn 1, and both turns went wrong on it.
- [ ] (moved to Week 18) **Nearly lost games:** when every play is worth under about 5%, choose by
      the best long shot (a crit, a miss) with more samples, not by noise.
      Measured on lost positions from the corpus before it is used.
- [x] **PP:** each move's PP counted on the board and in the resolver. A move
      with none left cannot be chosen, and Encore fails on it. Protect's PP is
      what ended the bot's Encore in game 629.
- [x] **The PO's games, turn by turn:** done, in the Week 16 report.
- [x] **Each clear misplay becomes a test** (`tests/test_po_games.py`, `5d20b30`: 626 turn 7 and 629 turn 15 pass; 626 turn 1 marked to fail until the Fake Out reading is fixed) the bot must pass (626 turns 1 and
      7, 629 turn 15), in the guaranteed-win test cases doc where it qualifies.

### Task 4 — Protect, Electro Shot and Tailwind: measure first
Measured 22 Nov (the bot's 600 gate games; 1500+ players, 439 validation
games): Protect right after its own Protect 12.3% of Protects (players 12.4%);
Electro Shot charged without rain 9% of its Electro Shots (players 36%);
Tailwind among moves made with one foe left 2.4%, its rate at any time
(players drop to 1.0% from 2.1%).
The rules are right (a second Protect works one time in three; Electro Shot
charges without rain). The values are what the PO questioned.
- [x] **How often** the bot protects twice in a row, sets Tailwind when it
      already outspeeds every Pokemon still on the field, and uses Electro Shot
      without rain, against how often 1500+ players do the same.
- [x] **Why:** on those turns, the win model's reading of the board after the
      turn (Tailwind up, Special Attack +1, a successful Protect) against the
      play the PO named.
- [x] A proposal for the fix, for the PO to approve. (Approved 23 Nov for late Tailwind: valued last with one foe left, and it loses a near tie within a point; `20ea0e8`. On 8 of the gate's late Tailwinds, 7 now play something else.) Likely a second turn of
      look-ahead for these moves only (see Task 5).

### Task 5 — Team preview against the opponent's six (done: `49f2f12`; likeliest four right 17.8% against 9.7% on validation)
- [x] Today the back two are the two players most often bring with the chosen
      leads, from the bot's own six only. **Rank the back two as well**, against
      the opponent's six (for example, the bring model given both teams).
- [x] Measured on validation games before it is used: does it pick the fours
      players who won picked?

### Task 6 — Ready for Reg M-D (2 December) (22 Nov: Showdown has no M-D format and no balance patch yet; carried to Week 18)
- [ ] M-D starts with a balance patch for every regulation (Rock Slide's
      accuracy and flinch, four accuracy changes, new moves for 33 Pokemon, Flash
      Fire and Stalwart reworked). Update the pinned Showdown copy once Showdown
      has M-D (you approve the update), and list what M-D adds, as REG-MC-GAPS.md
      did.
- [ ] Download M-D games once its ladder has enough (likely Week 18).

### Task 7 — Runbook and report
- [x] **Runbook:** (section 30, `5d20b30`) the clock fix and the rule switches in Section 29.
- [x] One report in prose, with a surprises section and where the gate stands (23 Nov).

## Kept for later
- **Looking further ahead in general** (protecting a win condition over several
  turns, as in the PO's 9:34 pm game). This is plan Phase 6 work. Task 4's
  measurements decide whether a narrow version comes sooner.
- **Speed.** The clock leaves three-quarters of the plays unvalued; one
  routine in the resolver takes nearly half the time.
- **The engine at strength 0** as an opponent: tried in the cloud only.

## Runs on your computer
- Task 1's gate: the 600 games again (about 6 hours).
- Task 2's proof: 200 games, the bot with the rules against the bot without
  (overnight).
- The PO's games: as many as he likes, with `build\w16\play_bot.cmd`.

## For you
1. **Approve this brief**, or change it.
2. **The Showdown update for M-D** (Task 6) needs your yes when it comes.
