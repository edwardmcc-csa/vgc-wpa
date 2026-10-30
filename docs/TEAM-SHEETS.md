# Team sheets as features

Week 5 Task 4. Code: `wpa/team_sheets.py`, `scripts/dump_dex.js`. Tests:
`tests/test_team_sheets.py`. Side file: `python -m wpa.team_sheets --out
sheets.jsonl.gz` (about 50 seconds, 13.5 MB, 88,905 games, never committed).

## What is read

Both open team sheets of every game: for each of the six Pokemon, in sheet order,
species, item, ability and four moves, and the nature where the sheet shows it
(every Reg M-B sheet, no Reg M-A sheet). All of it is public before the first
decision.

The states list both sides in sheet order. Checked on one game in 50 (7,208
sides): every side matched the sheet position for position, and the order never
changed within a file.

## Capabilities

Each Pokemon gets a set of capabilities by rules in `capabilities()`. Move
priority and target come from the pinned Showdown data, and a held Mega Stone
adds its Mega form's ability (Charizardite Y gives Drought, so sun).

| Capability | Rule | Reg M-A teams | Reg M-B teams |
|---|---|---|---|
| tailwind | Tailwind | 60.4% | 64.4% |
| trickroom | Trick Room | 36.8% | 37.1% |
| rain | Drizzle, Primordial Sea, Rain Dance | 19.9% | 24.2% |
| sun | Drought, Orichalcum Pulse, Desolate Land, Sunny Day | 26.5% | 22.1% |
| sand | Sand Stream, Sandstorm | 11.5% | 4.2% |
| snow | Snow Warning, Snowscape, Chilly Reception | 14.4% | 12.3% |
| redirection | Follow Me, Rage Powder, Spotlight | 40.0% | 47.5% |
| fakeout | Fake Out | 66.0% | 57.6% |
| priority | a damaging move with priority above 0, not Fake Out | 71.4% | 63.0% |
| prankster | Prankster | 23.9% | 47.3% |
| intimidate | Intimidate | 38.5% | 54.4% |
| screens | Light Screen, Reflect, Aurora Veil | 16.9% | 35.6% |
| spread | a damaging move that hits both foes | 95.7% | 96.3% |
| trapping | Shadow Tag, Arena Trap (Gengarite gives Mega Gengar's Shadow Tag), Mean Look, Block, Spider Web | 8.0% | 3.2% |
| perishsong | Perish Song | 5.4% | 2.6% |

(169,476 Reg M-A and 8,334 Reg M-B team sheets, two per game.)

Snow is on 14% of Reg M-A teams by this rule, more than "uncommon". Most of it is
Chilly Reception and Snowscape users rather than Snow Warning; Task 4b will show
how many teams are built around it.

## Features at one decision

For each side ("our" and "their") and each capability: how many Pokemon with it
are **active**, **on the bench** (seen, still standing, not active), or **unseen**
(the state shows them at 0 hit points, not fainted, not active). Fainted
Pokemon count for nothing. Also: how many are unseen, which sheet positions are
unseen, and how many unseen sit in positions 1-4 against 5-6 (Pokemon listed
fifth or sixth are brought far less often, `docs/OPP-POKEMON.md`).

The features read only `species`, `hp_fraction`, `fainted` and `active` from the
state (a guard test fails on anything else, `gimmick` included). Which four
Pokemon were brought is never an input, so it cannot leak.

The same rule is applied to our own side. The player knows which four they
brought, but the state does not record it (our bench also shows 0 hit points), and
inferring it from who appears later in the log would leak the game's length.

## What the sheet cannot give

- Speed and bulk: EVs and IVs are never shown, nature only in Reg M-B. Base stats
  are public and come from the Showdown data; Task 4b uses them.
- Which four were brought.
- What has happened to an item (a Focus Sash already used, a berry eaten): the
  log has it (`-enditem`), the state does not. A candidate for a later side file.
- Stat boosts, and whether Fake Out is still usable (only on a Pokemon's first
  turn in). Neither is in the state.
