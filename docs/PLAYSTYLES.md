# Play-style archetypes (PROPOSAL, awaiting product-owner sign-off)

Week 5 Task 4b. Code: `wpa/playstyles.py`. Tests: `tests/test_playstyles.py`.
Report: `python -m wpa.playstyles` (needs `sheets.jsonl.gz`; about two minutes).
**No number anywhere uses these tags until the product owner signs off the rules.**
Example teams for each tag, and teams that barely miss Hyper Offense or Balance:
`docs/PLAYSTYLE-EXAMPLES.md` (`python -m wpa.playstyles --examples docs/PLAYSTYLE-EXAMPLES.md`).

## The rules as written

A team carries every tag whose rule it meets. Base stats and types come from the
pinned Showdown data; a Pokemon holding its own Mega Stone is judged as its Mega
form. Numbers marked PO are the product owner's; the rest are proposals.

| Tag | Rule |
|---|---|
| Perish Trap | Perish Song, plus a trapper (Shadow Tag, Arena Trap, Mean Look, Block, Spider Web) |
| Hard Trick Room | two or more Trick Room users, average base Speed of the six at most 70 |
| Tailroom | Tailwind and Trick Room both on the team |
| Protect the Queen | a Follow Me or Rage Powder user, plus a *different* Pokemon with a setup move (Swords Dance, Dragon Dance, Nasty Plot, Calm Mind and similar) whose attacking stat is 110+ |
| Sun, Rain, Sand, Snow | a setter of that weather, by ability (including a Mega's) or move |
| Hyper Offense | all of: at least 3 Pokemon with a base attacking stat of 110+ in the stat their moves use (PO) and base Speed 100+, or 80+ when the team has a Prankster or Gale Wings Tailwind user (PO); at least one damaging spread move of power 80+ (Heat Wave, Hyper Voice; Rock Slide's 75 is below); at most 2 disrupters; average base bulk ((HP+Def+SpD)/3) at most 88 (PO); no Assault Vest, Eviolite or Rocky Helmet (PO: not in Reg M-A or M-B yet, kept for when they return) |
| Balance | not Hyper Offense, and at least 2 of 4 signals: a Fire-Water-Grass or Steel-Fairy-Fighting type core; Intimidate cycling (an Intimidate user and a pivot, or two Intimidate users); 2+ pivot users (U-turn, Volt Switch, Flip Turn, Parting Shot, Teleport, Baton Pass, Chilly Reception, Shed Tail); a mix (a 110+ attacker, 2+ disrupters, a member with bulk 90+) |

Disrupters: Pokemon with Fake Out, Taunt, Encore, Disable, Imprison, Quash, a
status move (Will-O-Wisp, Thunder Wave, Spore, Sleep Powder, Yawn and others),
Icy Wind, Electroweb, Snarl, Parting Shot, Haze, redirection, a trapping move, or
Intimidate or a trapping ability. Tailwind is not disruption.

## What they give (all 88,905 games)

| Tag | Reg M-A teams | Reg M-A units if held out | Reg M-B teams | Reg M-B units if held out |
|---|---|---|---|---|
| Tailroom | 16.5% | 30.0% | 18.6% | 33.9% (767 units) |
| Hard Trick Room | 3.2% | 7.0% | 2.4% | 4.9% (111 units) |
| Hyper Offense | 7.9% | 14.8% | 7.3% | 13.3% (301 units) |
| Balance | 49.6% | 73.8% | 55.1% | 80.0% (1807 units) |
| Protect the Queen | 22.4% | 38.8% | 24.1% | 41.0% (927 units) |
| Perish Trap | 5.0% | 9.8% | 2.3% | 4.8% (109 units) |
| Sun | 26.5% | 45.0% | 22.1% | 38.3% (866 units) |
| Rain | 19.9% | 36.8% | 24.2% | 42.3% (955 units) |
| Sand | 11.5% | 21.8% | 4.2% | 8.1% (183 units) |
| Snow | 14.4% | 26.5% | 12.3% | 23.1% (522 units) |

169,476 Reg M-A team sheets in 50,781 units; 8,334 Reg M-B in 2,260 units. A
unit is a best-of-three set or a single game; holding a tag out removes every unit
in which either player's team carries it. 5.1% of Reg M-A teams and 3.6% of Reg
M-B carry no tag; 59.2% and 56.8% carry two or more. The commonest pairs are
Balance with Protect the Queen, then Balance with each weather.

## What needs the product owner

1. **Hyper Offense: bulk cut-off set to 88 (PO, 29 Oct)**, from the proposed 85,
   after the Sneasler / Garchomp / Basculegion / Glimmora / Charizard-Y /
   Whimsicott example (average bulk 86). Hyper Offense is now 7.9% of Reg M-A
   teams and 7.3% of Reg M-B (was 3.2% and 2.7%). Low bulk passes for 37% of teams
   on its own; three or more fast 110+ attackers for 34%.
2. **Defensive items (PO, 29 Oct): kept.** Assault Vest, Eviolite and Rocky Helmet
   are not in Reg M-A or M-B (Rocky Helmet is expected in M-C), so the test passes
   for every team today; it stays for when they return.
3. **Balance and Protect the Queen are broad.** Balance is half of all teams with "2 of 4
   signals"; with 3 of 4 it would be about 23% (Reg M-A signal counts: 0 16%, 1 30%,
   2 31%, 3 17%, 4 6%). Protect the Queen is 22% even after requiring the setup user
   to be a 110+ attacker, because Follow Me and Rage Powder are on 40% of teams.
4. **Snow: 14% of Reg M-A teams**, almost all from Snow Warning (Alolan Ninetales
   above all). PO, 29 Oct: snow ebbs as the power level rises, so this is a
   ladder-wide figure.
5. **Only small tags can be held out.** Holding out Balance, a weather or Protect
   the Queen would remove a third or more of all units. Hard Trick Room, Hyper
   Offense and Perish Trap remove 5-10%. In Reg M-B these are about 110 units each,
   which is too small to give a stable number on their own.
6. **Perish Trap includes Mega Gengar (PO, 29 Oct).** Gengarite gives Shadow Tag,
   so Gengar with Gengarite and Perish Song is Perish Trap. 8,187 Reg M-A Gengars
   carry both. Trapping and Perish Song are also model features now (Task 4), and so is
   the way out: a pivot move (U-turn, Parting Shot ...), being a Ghost type (never
   trapped) or Shed Shell. Arena Trap also misses Flying types and Levitate; that
   finer point is not modelled.

## The full report

```
=== play-style tags (PROPOSAL) ===
regma: 169476 team sheets in 50781 units (sets or single games); untagged 5.1%; two or more tags 59.2%
  tailroom           28042 teams (16.5%); held out, it would remove 15234 units (30.0%)
  hardtrickroom       5481 teams ( 3.2%); held out, it would remove 3539 units (7.0%)
  hyperoffense       13405 teams ( 7.9%); held out, it would remove 7508 units (14.8%)
  balance            84040 teams (49.6%); held out, it would remove 37452 units (73.8%)
  protectthequeen    38042 teams (22.4%); held out, it would remove 19727 units (38.8%)
  perishtrap          8455 teams ( 5.0%); held out, it would remove 4999 units (9.8%)
  sun                44930 teams (26.5%); held out, it would remove 22851 units (45.0%)
  rain               33677 teams (19.9%); held out, it would remove 18701 units (36.8%)
  sand               19416 teams (11.5%); held out, it would remove 11055 units (21.8%)
  snow               24458 teams (14.4%); held out, it would remove 13434 units (26.5%)
  common pairs: balance+protectthequeen 27962, balance+sun 15427, balance+rain 15362, balance+tailroom 11840, balance+snow 10772, balance+sand 9943
  hyper offense conditions met on their own: fast_damage_dealers 34.2%, heavy_spread 91.7%, low_disruption 62.8%, low_bulk 37.4%, no_defensive_items 100.0%, all 7.9%
  weather setters (Pokemon): rain:ability 27187, rain:move 12907, sand:ability 19277, sand:move 376, snow:ability 24083, snow:move 1082, sun:ability 41957, sun:move 7255
  average_bulk: 50: 0.0%, 55: 0.0%, 60: 0.0%, 65: 0.0%, 70: 0.2%, 75: 1.5%, 80: 13.2%, 85: 42.0%, 90: 35.0%, 95: 7.5%, 100: 0.6%, 105: 0.0%, 110: 0.0%
  average_speed: 20: 0.0%, 30: 0.0%, 40: 0.8%, 50: 2.3%, 60: 5.0%, 70: 14.4%, 80: 35.6%, 90: 33.5%, 100: 7.5%, 110: 0.7%, 120: 0.0%
  balance_signals: 0: 16.3%, 1: 30.0%, 2: 31.0%, 3: 17.2%, 4: 5.5%
  choice_items: 0: 52.9%, 1: 47.1%, 2: 0.0%
  damage_dealers: 0: 0.0%, 1: 0.3%, 2: 2.8%, 3: 13.5%, 4: 32.0%, 5: 41.0%, 6: 10.4%
  defensive_items: 0: 100.0%, 1: 0.0%, 2: 0.0%
  disrupters: 0: 6.3%, 1: 23.9%, 2: 32.6%, 3: 24.1%, 4: 11.0%, 5: 1.9%, 6: 0.1%
  fast_damage_dealers: 0: 10.5%, 1: 25.2%, 2: 30.2%, 3: 28.7%, 4: 5.3%, 5: 0.1%
  heavy_spread_users: 0: 8.3%, 1: 26.4%, 2: 39.5%, 3: 20.6%, 4: 4.9%, 5: 0.3%, 6: 0.0%
  intimidate_users: 0: 61.5%, 1: 37.4%, 2: 1.1%, 3: 0.0%, 5: 0.0%, 6: 0.0%
  pivot_users: 0: 41.6%, 1: 46.4%, 2: 11.1%, 3: 0.8%, 4: 0.1%, 5: 0.0%, 6: 0.0%
regmb: 8334 team sheets in 2260 units (sets or single games); untagged 3.6%; two or more tags 56.8%
  tailroom            1553 teams (18.6%); held out, it would remove 767 units (33.9%)
  hardtrickroom        200 teams ( 2.4%); held out, it would remove 111 units (4.9%)
  hyperoffense         610 teams ( 7.3%); held out, it would remove 301 units (13.3%)
  balance             4592 teams (55.1%); held out, it would remove 1807 units (80.0%)
  protectthequeen     2009 teams (24.1%); held out, it would remove 927 units (41.0%)
  perishtrap           191 teams ( 2.3%); held out, it would remove 109 units (4.8%)
  sun                 1841 teams (22.1%); held out, it would remove 866 units (38.3%)
  rain                2014 teams (24.2%); held out, it would remove 955 units (42.3%)
  sand                 347 teams ( 4.2%); held out, it would remove 183 units (8.1%)
  snow                1029 teams (12.3%); held out, it would remove 522 units (23.1%)
  common pairs: balance+protectthequeen 1399, balance+sun 784, balance+rain 741, balance+tailroom 671, rain+tailroom 599, balance+snow 494
  hyper offense conditions met on their own: fast_damage_dealers 37.2%, heavy_spread 93.4%, low_disruption 56.2%, low_bulk 38.9%, no_defensive_items 100.0%, all 7.3%
  weather setters (Pokemon): rain:ability 1885, rain:move 679, sand:ability 347, snow:ability 1036, snow:move 2, sun:ability 1756, sun:move 253
  average_bulk: 60: 0.0%, 65: 0.0%, 70: 0.2%, 75: 1.7%, 80: 12.8%, 85: 43.7%, 90: 37.3%, 95: 4.0%, 100: 0.3%
  average_speed: 30: 0.0%, 40: 0.6%, 50: 1.4%, 60: 6.5%, 70: 17.8%, 80: 32.0%, 90: 31.7%, 100: 9.1%, 110: 0.8%
  balance_signals: 0: 10.9%, 1: 31.0%, 2: 30.0%, 3: 21.0%, 4: 7.2%
  choice_items: 0: 62.4%, 1: 37.6%
  damage_dealers: 1: 0.2%, 2: 1.4%, 3: 7.9%, 4: 32.4%, 5: 44.0%, 6: 14.2%
  defensive_items: 0: 100.0%
  disrupters: 0: 5.4%, 1: 19.3%, 2: 31.6%, 3: 27.7%, 4: 13.2%, 5: 2.7%, 6: 0.2%
  fast_damage_dealers: 0: 12.4%, 1: 21.8%, 2: 28.6%, 3: 30.9%, 4: 5.4%, 5: 0.9%
  heavy_spread_users: 0: 6.6%, 1: 26.8%, 2: 36.2%, 3: 24.9%, 4: 5.0%, 5: 0.5%
  intimidate_users: 0: 45.6%, 1: 42.8%, 2: 11.4%, 3: 0.2%
  pivot_users: 0: 37.1%, 1: 44.5%, 2: 15.9%, 3: 2.2%, 4: 0.3%, 5: 0.0%

```
