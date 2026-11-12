# Reg M-C: what is new since M-B, and what our model needs

Written 11 Nov 2026, from Showdown's Champions data (its current version against
the one we pin, 20 Jun 2026) and the M-C patch notes. **Status: deferred.** The PO
decided on 11 Nov that M-C waits until M-A and M-B are ironed out. This is the
list to start from when it does.

## The format

- In the app since 9 Sep 2026. Season M-8 (4 Nov to 2 Dec) is the third M-C season.
- On Showdown: "[Gen 9 Champions] VGC 2026 Reg M-C" and its best-of-three. Ladder
  games show team sheets only if both players agree; most show species only, as
  in the app. Best-of-three games always show full sheets.
- Same Flat Rules as M-A and M-B: Species Clause, Item Clause, level 50.
- **Nothing legal in M-B was removed.**

## New Pokémon: 24 species and 6 Mega Evolutions (35 forms)

| Pokémon | Types | Abilities |
|---|---|---|
| Rillaboom | Grass | Overgrow, Grassy Surge |
| Cinderace | Fire | Blaze, **Libero** |
| Inteleon | Water | Torrent, Sniper |
| Salamence | Dragon/Flying | Intimidate, Moxie |
| Mega Salamence | Dragon/Flying | Aerilate |
| Golisopod | Bug/Water | **Emergency Exit** |
| Mega Golisopod | Bug/Steel | Tough Claws |
| Baxcalibur | Dragon/Ice | **Thermal Exchange**, Ice Body |
| Mega Baxcalibur | Dragon/Ice | **Thermal Exchange** |
| Mega Absol Z | Dark/Ghost | Sharpness |
| Mega Garchomp Z | Dragon | Levitate |
| Mega Lucario Z | Fighting/Steel | **Aura Guard** (new to Champions) |
| Wigglytuff | Normal/Fairy | Cute Charm, Competitive, Frisk |
| Persian | Normal | Limber, Technician, Unnerve |
| Alolan Persian | Dark | Fur Coat, Technician, **Rattled** |
| Mr. Mime | Psychic/Fairy | Soundproof, Filter, Technician |
| Swalot | Poison | **Liquid Ooze**, Sticky Hold, Gluttony |
| Gogoat | Grass | Sap Sipper, **Grass Pelt** |
| Thievul | Dark | **Run Away**, Unburden, **Stakeout** |
| Toxtricity (both forms) | Electric/Poison | **Punk Rock**, Plus or Minus, Technician |
| Grapploct | Fighting | Limber, Technician |
| Perrserker | Steel | Battle Armor, Tough Claws, **Steely Spirit** |
| Pincurchin | Electric | Lightning Rod, Electric Surge |
| Indeedee (both forms) | Psychic/Normal | Inner Focus or Own Tempo, Synchronize, **Psychic Surge** |
| Arboliva | Grass/Normal | **Seed Sower**, Harvest |
| Squawkabilly (4 plumages) | Normal/Flying | Intimidate, Hustle, Guts or Sheer Force |
| Mabosstiff | Dark | Intimidate, **Guard Dog**, **Stakeout** |
| Pawmot | Electric/Fighting | Volt Absorb, Natural Cure, Iron Fist |
| Farfetch'd | Normal/Flying | Keen Eye, Inner Focus, Defiant |
| Sirfetch'd | Fighting | Steadfast, Scrappy |

**Bold:** on no M-A or M-B Pokémon. Abilities are as Showdown's data has them;
patch-note sites disagree on some Mega abilities (Lucario Z, Golisopod).

**To check:** some sites list more Pokémon seen on the app's ladder (Heatran,
Iron Hands, Tapu Koko and others). Showdown's data doesn't make them legal.
Check against the app's own list before building.

## New abilities, and what our model does with them today

| Ability | Who | What it does | Our model today | Needed |
|---|---|---|---|---|
| Aura Guard | Mega Lucario Z | Halves damage from contact moves | Not known; the damage calculator may not know it either | Add to the damage step |
| Seed Sower | Arboliva | Sets Grassy Terrain when hit | Ignored, not marked | Model it (it never fails) |
| Thermal Exchange | Baxcalibur, Mega | +1 Attack when hit by a Fire move; cannot be burned | Ignored, not marked | Model it |
| Libero | Cinderace | Becomes the type of the move it uses | Ignored, not marked | Model or mark. Protean does the same and is already silent in M-A and M-B (261 of 9,060 validation games). |
| Emergency Exit | Golisopod | Switches out when knocked below half | Ignored, not marked | Model it as a switch during the turn, as for Eject Button |
| Liquid Ooze | Swalot | Draining moves and Leech Seed hurt the drainer instead | Ignored | Model it, with the new Leech Seed |
| Run Away | Thievul | In Champions it also escapes trapping (Showdown, 10 Sep) | Not known | Allow switching when trapped |
| Stakeout | Mabosstiff, Thievul | Double damage on a target that switched in this turn | Not passed to the calculator | Pass it |
| Steely Spirit | Perrserker | The ally's Steel moves ×1.5 | Not known | Check the calculator; pass the ally |
| Punk Rock | Toxtricity | Sound moves ×1.3; takes half from them | The calculator's job | Check the calculator |
| Grass Pelt | Gogoat | Defense ×1.5 on Grassy Terrain | The calculator's job, if given the terrain | Check |
| Rattled | Alolan Persian | +1 Speed when hit by Bug, Ghost or Dark, or Intimidated | Intimidate only | Add the other trigger |
| Guard Dog | Mabosstiff | Intimidate raises its Attack; cannot be forced out | The Intimidate part | Check the other part |
| Psychic Surge, Grassy Surge | Indeedee, Rillaboom | Set terrain on entry | Modelled | — |

Abilities already in M-A or M-B that M-C makes more common, which our model ignores
without marking:
- **Moxie** (Salamence): +1 Attack on a knock-out.
- **Harvest** (Arboliva): the Berry comes back half the time, always in sun.
- **Volt Absorb and Sap Sipper:** the immunity is the calculator's, but not the
  heal or the +1 Attack.

These belong in the M-A/M-B work too.

## New items: 12, bought with Victory Points

| Item | Our model today | Needed |
|---|---|---|
| Rocky Helmet, Terrain Extender | Modelled | — |
| Air Balloon | Partly modelled (the immunity) | Pop it when hit |
| Eject Button | Modelled | Check Showdown's two Champions changes (13 and 30 Sep) |
| Electric, Grassy, Misty and Psychic Seed | Not modelled | +1 Defense or Sp. Def when that terrain starts. Matters now that Indeedee, Rillaboom and Pincurchin set terrain. |
| Red Card | Not modelled | The attacker is forced out, replaced at random: model or mark |
| Normal Gem | Not modelled | One Normal move ×1.3, then used up |
| Leek | Not modelled | Higher critical-hit chance (Farfetch'd, Sirfetch'd) |
| Binding Band | Not modelled | Binding moves deal 1/6 a turn |

## Moves usable for the first time

Court Change, Double Shock, Drum Beating, Glaive Rush, Jaw Lock, Meteor Assault,
Milk Drink, Octolock, Overdrive, Pyro Ball, Revival Blessing, Shift Gear, Slash,
Snipe Shot, Zing Zap.

Most are damage plus an effect the resolver already reads from the move data.
These need work:
- **Revival Blessing:** brings back a fainted Pokémon at half HP.
- **Court Change:** swaps the two sides' conditions (Tailwind, screens).
- **Glaive Rush:** until its next turn the user takes double damage and is
  always hit.
- **Jaw Lock and Octolock:** trap the target, so it cannot switch; Octolock also
  lowers Defense and Sp. Def each turn.
- **Meteor Assault:** the user must recharge the next turn. Recharging is not
  modelled for any move yet.
- **Double Shock:** the user loses its Electric type.
- **Milk Drink:** in Champions it can heal an ally too.

## Changes to things already in M-B

- **Power and PP:** Slash 80, Snipe Shot 85, Meteor Assault 170; Wish 8 PP and
  Strength Sap 8 PP (Showdown keeps M-B's 10); Double Shock now counts as a punch.
- **Moves gained:** Golisopod gains Close Combat, U-turn and Gunk Shot and loses
  Knock Off; Indeedee-F gains Sing and Terrain Pulse; Grapploct gains Mach Punch;
  Wigglytuff gains Moonblast.
- **Moves lost:** Archaludon loses Mirror Coat and Metal Burst; Annihilape loses
  Pound.
- **Showdown's Champions mechanics changed since our pin:**
  - Curse is reworked.
  - Disable no longer stops moves that cannot be used twice.
  - Emergency Exit and Wimp Out follow Champions.
  - Run Away escapes trapping.
  - No Retreat cannot trap twice.
  - Eject Button lets self-switches happen.
  - Sheer Force no longer turns off Berserk, Eject Button and the like.
  - Mega Sol and Electro Shot interact with Encore.

## What adding M-C takes in our pipeline

1. **A second Showdown version.** Ours (20 Jun) has the M-A and M-B rules but not
   M-C. Current Showdown has M-B and M-C, but dropped M-A's rules on 9 Sep. So we
   keep one Showdown version per regulation. That's a decision for when we start.
2. **The damage calculator:** check that it knows the Z Megas and Aura Guard.
3. **Data:**
   - M-C replays from Showdown. At the rate on 11 Nov, about 1,800 public ladder
     games a day, plus fewer best-of-threes.
   - Smogon usage statistics for September and October.
4. **The format, in every part:**
   - add `regmc` to the formats list;
   - features and the win probability models, with sheets shown and hidden;
   - the opponent model, and the bring, lead and switch-in models.
5. **The resolver:** the abilities, items and moves above, each tested first
   against Showdown's Champions data.
6. **Hidden opponent sets:** also needed for games played in the app. This can
   start on M-A and M-B.

## Found while checking, which matters for M-A and M-B now

**Encore.** In Champions, Encore changes the target's queued move. The target
then moves where the *new* move's priority puts it, not where its old move was.
For example, a Pokémon encored into Protect protects at once, before the attacks
still to come. Showdown's M-A and M-B rules do the same.

My Encore fix from 11 Nov (not yet on the PO's computer) kept the old place in
the order. It's corrected, with a test. Like the rest of that batch, the test
runs once the computer is linked again.

## Sources

- Showdown's Champions data: `data/mods/champions`, current version against our
  pin `913da36`; `config/formats.ts`; commit history from 15 Jun to 10 Nov 2026
- [Game8: Pokémon Champions list of changes](https://game8.co/games/Pokemon-Champions/archives/593893)
- [Stratadex: Reg M-C, every new Pokémon and Mega](https://stratadex.net/guides/m-c-new-pokemon)
- [Serebii: Season M-8](https://serebii.net/pokemonchampions/rankedbattle/seasonm-8.shtml)
- [Showdown replay search, Reg M-C](https://replay.pokemonshowdown.com/search.json?format=gen9championsvgc2026regmc)
