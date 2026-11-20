# Week 16 Report: the bot plays, within the clock (mostly)

19 Nov 2026. Brief: Week 16 (Phase 3, part 1), approved 17 Nov.

## In short

The engine now plays whole Reg M-C games on its own on the local Showdown
server, with closed team sheets and Showdown's clock on. In 600 games it met all
three win-rate parts of the Phase 3 gate:

| Against | Wins | 95% interval | Gate |
|---|---|---|---|
| Random choices | 198 of 200 (99%) | 96% to 100% | 90% or more: met |
| The strongest move | 146 of 200 (73%) | 66% to 79% | over 55%: met |
| The choice model (as people typically play) | 174 of 200 (87%) | 82% to 91% | better than even: met |

It did **not** meet the gate's last part, no timeouts or illegal choices: 48
turns in 46 games ran past the 55-second limit, and every choice Showdown
refused came after one of them. Nothing crashed, and no game was lost on time.

Against a strong human, you, it lost every game on Tuesday evening. Your notes
on those games are the best test it has had: they found more than the 600
games against programs did. They are below, turn by turn, and checking them
found a bug in how the engine reads a charging move (fixed Thursday, `d4ab5bf`).

## What was built

All committed on your computer: `ba699fa`, `6a8e00d`, `04049df`, `91f40ca`.
Your computer's whole test suite passed (1,327 tests).

- **The engine as a player** (`wpa/bot.py`). Team preview: the advice's four
  and leads, and it denies open team sheets. Each turn: the best play by win
  chance. Each forced switch: the advice's newcomer. It reads its own stream
  of the game as a spectator's log, and sends only a choice taken from
  Showdown's own request. A choice it cannot find there is replaced by a legal
  one at random, and the reason kept.
- **Within the clock** (`wpa/advise.py`). The search goes the likeliest plays
  first, in batches, and stops when the turn's time is up: a sixth of the
  game's clock left, never over 45 seconds. With time to spare it plays exactly
  the advice's best play.
- **Its own stat points known.** Until now the engine believed even the
  player's own spreads from usage statistics. A team paste's stat points are
  now used as they are (for the bot, and for your own team in the advice).
- **The opponents** (`wpa/opponents.py`): the strongest move (each Pokemon's
  most damaging move at the foe it hurts most), the choice model (choices drawn
  by how often players make them) and the engine at strength 0.
- **The matches** (`wpa/matches.py`): a pool of the 40 commonest teams of
  1500+ games, each Pokemon with its likeliest stat points; every pairing
  played from both sides; results with 95% intervals.
- **Play the bot yourself** (`wpa/play.py`, `build\w16\play_bot.cmd`).
- **Runbook section 29.**

## The clock

**Measured first, with the clock off** (12 games): a typical turn took 68
seconds, the slowest 1% over 10 minutes, and a typical game 411 seconds of
thinking against the 420 Showdown allows. The full advice cannot fit the
clock.

**With the cut-off:** a typical turn 32 to 34 seconds; a typical game 137 to
171 seconds of thinking. The clock stopped the search on about two turns in
three. When it
did, about 9 plays had been valued against every reply and three-quarters had
not been valued at all. That is the price of the clock, and the main reason to
make the engine faster.

**The late turns.** 48 of about 3,500 turns ran past 55 seconds, in 46 games
(15 against random, 9 against the strongest move, 24 against the choice model).
All 48 were in one step of the search: weighing the opponent's likely replies
against one of the bot's plays. That step is one batch of about 12 pairs of
plays and cannot be stopped part way; on some opening turns one batch took 60
to 145 seconds. When a turn runs late, Showdown chooses for the bot, the bot
falls out of step with Showdown's requests for the rest of that game, and its
next choices are refused: all 211 refusals came in those 46 games. The late
turns were in 10 of the bot's 82 losses.

**The fix** is the first task of Week 17: check the clock inside the batch,
play the likeliest play when nothing is valued yet, and read Showdown's
current request again after a missed turn.

## Quality control

- **Crashes:** none.
- **Choices replaced by a legal one at random:** 97 of about 4,900 (2%). The
  commonest causes were errors in the advice at a forced switch ("no Pokemon to
  send in", 23) and at the game's end (13).
- **The resolver check on its own games** (200 games against random, both
  teams known exactly): the board that happened was among the resolver's on
  97.0% of 1,099 turns (Reg M-A and M-B ladder games: 81% and 85%). With exact
  sets, a miss is a rules gap. The check found one in a trial game: Protect did
  not block an attack from the protected Pokemon's own partner. Showdown's
  Protect, Wide Guard and Quick Guard all do; fixed, with a test.
- **One question left open:** on these games the damage estimate was more
  than 10% too low on 27% of the hits it could check (median real over
  estimate 1.05). On ladder games the bias went the other way. Not explained
  yet.
- **Its win chance runs low on these games.** When it rated itself 50 to 60%,
  it went on to win 98% against random, 77% against the strongest move and 90%
  against the choice model. Expected against weak opponents; it also says the
  choice-model opponent plays well below real players (it draws its choices by
  their odds instead of aiming at anything), so the 87% overstates the bot's
  strength against people.

## Your games against it (Tuesday evening)

You won every game. Your read: "halfway decent, but definitely not going to be
pushing the 1700s in showdown any time soon." That matches the numbers.

Your notes fall into five patterns, plus the bug (next section):

1. **Protect again after Protect** (Basculegion, Kingambit, Golisopod on turns
   9 and 10, Whimsicott; Kingambit's came from the bug). The rules are right: a second Protect in a row works
   one time in three, and the board tracks the streak. So these were the
   engine's values, not a rule error. In its 600 games, Protect was its most
   used move, and the same place protected two turns running 29 to 38 times
   per 200 games. You also named two good ones (Basculegion stalling your
   rain, and the turn-16 Protect against Electro Shot), so the fix is better
   values, not a ban.
2. **Plays whose payoff comes next turn** (Electro Shot without rain in the
   9:41 pm game; Tailwind on turn 4 next to a Sucker Punch, and on turn 17 when it already
   outsped your last Pokemon). The rules are right: Electro Shot charges for a
   turn without rain, with its Special Attack boost. But the engine looks one
   turn ahead, so its worth, and Tailwind's, comes only from how the win model
   reads the board after the turn. Electro Shot was among the bot's five most
   used moves.
3. **Rules missing: PP.** The resolver and the board do not track PP. So the
   engine could not know that your Protect ran out (which ended the bot's
   Encore on your Pokemon on turn 14), nor that a new Encore would then fail
   (game 629, turn 15).
4. **Team preview** (no Mega with Froslass and Charizard; no Sneasler or Raichu
   against your Archaludon). The advice ranks the two leads; the back two are
   simply the two players most often bring with those leads, chosen from the
   bot's own six only. **It never looks at your six when picking its back
   two.** That fits both of your notes.
5. **The plan over several turns** (game 9:34 pm: protect Sneasler for a Close
   Combat into your Archaludon, or keep Basculegion for late Last Respects).
   One turn of looking ahead cannot see a win condition. This is the plan's
   Phase 6 work ("looking further ahead"), and your games argue for starting
   it sooner.

## Your games, turn by turn

I ran every turn you named through the full advice afterwards, with no clock,
from the bot's side and with the four it brought. The numbers are the bot's win
chance after each play.

### The bug: a charge that went off at once

In rain, Electro Shot charges and hits in the same turn (Solar Beam in sun works
the same way). Showdown records that as a charge and then the hit. The engine
read the charge and missed the hit, so from then on it believed that Pokemon was
still charging and could only use Electro Shot. It hit both sides: the bot
thought its own Archaludon had one move, and it was certain your Archaludon
would use Electro Shot.

Fixed on Thursday (`d4ab5bf`), with a test shown failing first; the board's 61
tests pass on your computer's copy. It is not rare: one Reg M-C ladder game in
five has such a turn (11,879 of 59,471), and so do 106 of the bot's 612 games
this week. The models were trained on boards read this way, which raises a
question for Week 17 (see the brief).

### Game by game

**9:26 pm (game 625), turn 5: Basculegion's Protect.** The full advice rated
Protect best (0.965), just ahead of Last Respects and Aqua Jet (0.951 each). It
thought the game was 94% won. It expected your Raichu to use Volt Tackle (47%)
and gave Fake Out only 17%. You used Fake Out on Whimsicott, and Ice Beam took
Whimsicott out. The top plays were within 1.5 points of each other, and
Protect's edge rested on a reply you didn't make. I have not confirmed that an
attack wins against every reply (the engine rated the attacks 95%, not 100%),
so this is not yet a guaranteed-win test case.

**The Froslass game (624), team preview.** Its lead values were all within 2.3
points (0.469 to 0.492). The leads with a Mega (Froslass, Delphox) were in the
pack, not ahead, and the back two never look at your six. Nothing pushed it
toward a Mega.

**9:34 pm (game 626).**
- *Turn 1.* It valued Close Combat into your Archaludon, with Sucker Punch into
  Raichu, best (0.728). It rated Protect on Sneasler 0.569, and it played the
  attack. None of its four likeliest replies had Raichu using Fake Out. Fake
  Out flinched Sneasler, Sucker Punch failed, and Sneasler fell on turn 2.
  Protecting Sneasler is the answer to Fake Out. The engine missed it because
  it didn't expect Fake Out.
- *Turn 7: the bug.* The bot's Archaludon had used Electro Shot in rain on
  turn 5. The engine still had it charging, so Electro Shot was the only move
  it offered. Its best play under that belief was exactly what the bot did:
  Electro Shot into Raichu and Kingambit's Protect (0.037). With the fix, its
  best is Aura Sphere and Sucker Punch, both into your Archaludon (0.236), and
  Kingambit's Protect drops to 0.068. You were right on both counts.

**9:41 pm (game 627), the mirror.**
- *Team preview.* Its best leads were Archaludon and Golisopod (0.567), ahead
  of Archaludon and Sneasler (0.529) and Raichu and Archaludon (0.510). So the
  engine did prefer Golisopod, and its back two (Pelipper, Basculegion-F) were
  picked without looking at your six.
- *Turn 1, both Protect.* With full time it would Protect with Archaludon only,
  and Mega Evolve Golisopod for Iron Head into Sneasler (0.617). Its best play
  with Golisopod protecting was 0.487. The full advice took 51 seconds, so the
  clock cut this turn short: the double Protect was not the engine's choice.
- *Turn 2, Electro Shot without rain.* With full time: switch Archaludon to
  Basculegion-F (0.533), Electro Shot (0.511), Protect (0.505), Dragon Pulse
  (0.493). The engine sees the Special Attack boost as nearly worth the lost
  turn. That is the "payoff next turn" pattern above (Week 17, Task 4).
- *Turns 9 and 10, Golisopod's Protects.* It rated the game at 2% before turn
  9, and every play at 0 to 2%. At that level the order is noise, not a choice.
  It cannot see what you saw, that Protect turned a small chance into none.

**9:50 pm (game 628).**
- *Turn 3, Charizard stays in against your rain.* Heat Wave 0.601, Protect
  0.601, switch 0.596: no difference it can see. The cost of staying in shows
  only over the turns of rain to come, and the engine looks one turn ahead.
- *Turn 8, Basculegion's Protect to stall the rain.* Protect 0.144 against Last
  Respects 0.034: a clear choice, and the one you praised.
- *Whimsicott's fourth move* was Encore (with Moonblast, Tailwind and Protect).

**Game 629.**
- *Turn 4, Tailwind beside Sucker Punch.* The bot played its best play, Tailwind
  0.233, just ahead of Moonblast 0.227. With the fix, Protect on Whimsicott is
  best (0.283), then Tailwind (0.265) and Moonblast (0.230), with Sucker Punch
  still Kingambit's move. Tailwind's value comes only from how the win model
  reads "Tailwind up" after the turn, which is what Task 4 measures.
- *Turn 5, Whimsicott's Protect.* The bug on your side: your Archaludon's
  turn-4 Electro Shot had gone off at once in rain, so the engine was certain
  you would use Electro Shot. With the fix it expects Electro Shot (47%) or
  Flash Cannon (35%), and it still prefers Protect (0.117 against Moonblast
  0.083). So this one is about values (Task 4), not only the bug.
- *Turn 15, Encore.* Before the fix: Encore 0.033 and Moonblast 0.000. With the
  fix, Moonblast is best (0.056), as you said: crits were the way to win. Encore
  would have failed anyway, because your Protect had no PP left, and the engine
  does not count PP.
- *Turn 17, Tailwind at 1 HP.* Tailwind 0.033, Moonblast 0.030, Encore 0.027.
  The game was nearly lost (3%), and at that level these values are noise.

### What this adds to Week 17

- **The bug is fixed.** Whether to re-read the M-C games and retrain the models
  is your call (see the brief).
- **The opponent model under-expects Fake Out.** Two of your turns (625 turn 5,
  626 turn 1) turned on a Fake Out it rated unlikely or didn't list.
- **Nearly lost games.** When every play is worth under about 5%, the engine
  should choose the play with the best long shot (a crit, a miss), as you
  described for game 629. Today it picks by noise.
- **The clock.** The double Protect on 627 turn 1 was cut short by the clock,
  which is Task 1's fix.

## The next regulation

**Reg M-D starts on Wednesday 2 December**, with a balance patch that applies
to battles in every regulation:
- Rock Slide: accuracy 90% to 95%, flinch chance 30% to 20%;
- Screech and Metal Sound: accuracy 85% to 100%; Steel Wing and Frost Breath:
  90% to 100%;
- new moves for 33 Pokemon (one is a Normal status move that copies the
  target's stat changes, for 22 Pokemon including every Rotom form);
- Flash Fire and Stalwart reworked.

Which Pokemon M-D allows is not published yet. The engine's rules come from its
own pinned copy of Showdown's code, so it needs Showdown's M-D update before it
can play M-D, and before its Reg M-C rules match the live game after 2
December.

## Surprises

- **Your games found more than 600 bot games did.** A strong human tests what
  random and model opponents never do: plans, Protect reads, team preview.
- **One misread line, in one game in five.** The charge that goes off at once
  in rain had been misread since the board was built. Only a human asking "what
  did Electro Shot accomplish?" brought it out.
- **The late turns came from one step.** Not the search over the bot's own
  plays, but weighing the opponent's replies, which could not be stopped
  part way.
- **Team preview ignores the opponent.** The advice has ranked leads since Week
  11; the back two never were ranked.
- **No PP.** Sixteen weeks in, the engine has never counted PP. Most games end
  before it matters; your 17-turn game did not.

## Where the gate stands

Phase 3's gate (Weeks 16 to 17): the three win rates are met. No crashes. Not
met: timeouts and illegal choices, which share one cause, fixed first in Week
17. Then the 600 games again, to show zero of each. Those games will also be
the first with the charging fix, which touched 106 of this week's 612.

Sources: [PokeOS, the December 2 balance patch](https://www.pokeos.com/news/2054/Pok%C3%A9mon+Champions+Balance+Patch+on+December+2:+Every+Move,+Learnset+and+Ability+Change); [Game Rant](https://gamerant.com/pokemon-champions-first-balance-patch-december-2/); [PocketMonsters.Net](https://pocketmonsters.net/news/9733); [Pokémon Champions on X](https://x.com/Pokemon_Champs/status/2123053614998401105); the Reddit post you saved (r/VGC, "M-D official balance patch"), which this session could not open.
