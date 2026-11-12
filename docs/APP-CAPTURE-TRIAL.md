# Trial: turning a recorded app game into a game record

11 Nov 2026. The PO recorded one ranked game in the Champions app on his phone
and shared it as a YouTube link: 13 minutes, Season M-8, so Reg M-C. This trial
asks one question: can the game be read off the video well enough to analyse?
The analysis itself waits for M-C (see `REG-MC-GAPS.md`).

## How it was read

1. **Download.** The cloud workspace was refused by YouTube's bot check. The
   PO's computer workspace downloaded it at 720p.
2. **Battle messages.** Text recognition (Tesseract) on the strip where the
   messages appear, four frames a second: about 10 minutes of computing. Names
   were then matched against the two teams and their moves, for example
   "Sneaster" to Sneasler and "Saar" to Snarl.
3. **Turns.** Grouped by the pauses while players choose.
4. **HP.** Read from the boxes on the move-selection screens. Yours are exact
   numbers (157/157); the opponent's are percentages.

## What it got

**Every action both players took, in all 12 turns: 39 of 39.** That includes
both switches, the moves, both flinches, the Protects, a critical hit and every
knock-out.

| Turn | You (Cbadcrazie) | Diego | HP at the next turn's start |
|---|---|---|---|
| Leads | Sneasler, Archaludon | Sneasler, Archaludon | |
| 1 | Archaludon out for End Game; Sneasler Swords Dance (+2) | Archaludon out for Basculegion; Sneasler Close Combat into End Game (no effect) | |
| 2 | Sneasler Poison Jab → Sneasler (not very effective); End Game Shadow Ball → Basculegion (super effective) | Sneasler Dire Claw → your Sneasler (not very effective); Basculegion Muddy Water | theirs: Sneasler 27%, Basculegion 5%; yours: Sneasler 34/157, End Game 160/195 |
| 3 | Sneasler Protect; End Game Muddy Water: **critical hit**, their Sneasler fainted | Basculegion Protect; Sneasler Dire Claw into Protect; Raichu in | Raichu 100%, Basculegion 5% |
| 4 | Sneasler **flinched**; End Game fainted before moving; Archaludon in | Raichu Fake Out → Sneasler; Basculegion Shadow Ball → End Game | yours: Sneasler 4/157, Archaludon 197/197 |
| 5 | Sneasler Protect, broken by Feint, fainted; Archaludon Snarl: Basculegion fainted, Raichu Sp. Atk −1; Mia in | Raichu Feint → Sneasler; Basculegion Muddy Water → Archaludon (Stamina: Def +1); Archaludon in | theirs: Raichu 80%, Archaludon 100%; yours: Mia 167/167, Archaludon 174/197 |
| 6 | Mia Fake Out → Raichu (**flinched**); Archaludon Dragon Pulse: Raichu fainted | Archaludon Snarl → Mia and your Archaludon (Sp. Atk −1; Stamina: Def +1) | |
| 7 | Archaludon Protect; Mia Volt Tackle → Archaludon (Stamina: Def +1), recoil | Archaludon Snarl (into Protect; Mia Sp. Atk −1) | theirs 88%; yours: Mia 103/167, Archaludon 176/197 |
| 8 | Mia Volt Switch (no one to switch to); Archaludon Dragon Pulse | Archaludon Dragon Pulse → **Mia** (103 → 10: found from the HP change) | theirs 58%; yours: Mia 10/167, Archaludon 188/197 (Leftovers +12) |
| 9 | Mia Feint; Mia fainted to Snarl; Archaludon Dragon Pulse | Archaludon Snarl | theirs 43%; yours 176/197 |
| 10 | Archaludon Dragon Pulse | Archaludon Dragon Pulse | yours 115/197 |
| 11 | Archaludon Protect | Archaludon charges Electro Shot (Sp. Atk +1) | theirs 35%; yours 127/197 |
| 12 | Archaludon Dragon Pulse: their Archaludon fainted. **You won.** | Electro Shot → Archaludon (not very effective) | |

## What it missed, and what fixes each

- **Some targets.** A move with no message about its effect ("not very
  effective", "protected") doesn't say whom it hit. Fix (the PO's
  suggestion): compare each Pokémon's HP from one turn to the next. On turn 8
  it shows Diego's Dragon Pulse hit Mia (103 → 10), and that your Archaludon's
  176 → 188 was Leftovers. Where two hits and healing land on the same
  Pokémon in one turn, the HP box shown during each hit settles it.
- **Ability and item pop-ups** (Stamina, Leftovers) sit in another place on the
  screen. Fix: read that place too.
- **HP at 3 of 12 turn starts:** the Battle Info panel or the move buttons
  covered the boxes. Fix: take the HP from another frame in the same turn where
  the boxes show, as done for turn 9.
- **Your full team** (moves, items, abilities, stat points) isn't on screen
  during the game. Fix: give it once, as a team paste.
- **Confirmed by the PO:** "End Game" is a shiny female Basculegion. Mia did
  not Mega Evolve in this game.

## Verdict

**This route works.** Messages alone recovered every action in the game. HP is
readable, and what's missing is fixable with readers for more parts of the
screen. A tool would:
1. download the video;
2. read the messages, pop-ups and HP boxes;
3. build turns;
4. list what it is unsure of for the PO to answer in a minute;
5. write a Showdown-style game record that the replay report reads.

About a week to build, on top of M-C and hidden opponent sets.

**For the PO, per game:** record the game, upload it to YouTube (unlisted is
fine), send the link.
