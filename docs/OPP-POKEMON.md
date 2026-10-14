# What `opp_pokemon` contains, and whether anything unrevealed leaks in

Week 4 Task 5. Evidence from the 177,808 files in `wpa_states/`, checked on random samples of 400 files (12 Oct 2026). Read with `docs/DEFINITIONS.md` section 5 (the information set).

## Contents

- `opp_pokemon` always has **six** entries: the opponent's whole open team sheet, in **sheet order**. The order never changes during a game (400 of 400 files).
- **Nothing is revealed at team preview.** Every opposing Pokemon in the first state has `hp_fraction` 0.0, `fainted` False, `active` False.
- A Pokemon becomes visible (hp above 0, active, or fainted) only when it appears. No game ever shows more than **four** (bring-four is confirmed: files by number of opposing Pokemon ever seen: 2, 3 or 4, never more).
- `hp_fraction` keeps the last seen value after a Pokemon leaves the field (for example 0.01). It is 0.0 for anything never seen.

## Leak checks

- **Brought and unbrought cannot be told apart before a Pokemon appears.** For every unrevealed opposing Pokemon in the sample the fields are `(hp 0.0, fainted False, active False)`, whether or not it is brought later. So nothing in `hp_fraction`, `fainted` or `active` reveals which four were brought.
- **The same is true of our own side.** The record shows 0.0 for our own bench too, although the player knows their own hit points. That loses information; it does not leak any.
- **The baseline reads only `hp_fraction`, `fainted`, `active` and `outcome`.** `tests/test_baseline.py` enforces this with a guard that fails on any other field.

## Two things the learned model must be told about

1. **Sheet position carries real, public signal.** Among opposing Pokemon not yet seen, the share that is eventually seen is 0.45, 0.41, 0.42, 0.41, 0.29 and 0.27 for sheet positions 1 to 6. Pokemon listed fifth or sixth are brought far less often. The sheet order is visible to the player, so using it is allowed under `WP_public`. It is not a leak, but it is a feature to add on purpose, not by accident.
2. **The `gimmick` field is unreliable on unrevealed Pokemon.** 6.4% of unrevealed opposing Pokemon carry `gimmick = "mega"`. `PokemonState.from_pokemon` gives "mega" to any Pokemon holding an item whose name ends in "ite" once that side has mega-evolved, so a second mega-stone holder (or a holder of an item such as Eviolite) is tagged before it has done anything. The item is public on the sheet, so this is not a leak, but the flag does not mean what its name says. Fixing it changes the parse and needs a re-parse; raised as a question, not changed.

## What the existing `observations` could supply without a schema change

`Observation.weather`, `.fields` and `.side_conditions` are tracked by replaying every broadcast message in log order, then copied onto each observation event. Seen in the sample: Tailwind, Light Screen, Reflect, Aurora Veil, Stealth Rock and Toxic Spikes (per side, written `p1:Tailwind`); Rain, Sun, Sand and Snow; Trick Room, Psychic and Grassy Terrain, Gravity, Magic Room.

- **Presence only, never turns remaining.** There is no start turn or duration. A rough "first turn this was recorded" can be derived from the same game's earlier states, but it can lag the true start by the number of turns with no observation, so it bounds elapsed time from below.
- **Only on states that have an observation.** After a condition was first recorded in a game, 21% of later states have no observations at all (363 of 1,757 sampled), so the condition is not recorded there even if still active.
- **Speed.** `move_order` observations carry the order a move was used within a turn and its priority, which is direct evidence of who is faster than whom, mixed up with priority, Tailwind and Trick Room (the last two are in the same record). Nothing is solved or interpreted in the record; that is M4b.
- **Not available at all:** Encore, Disable, Taunt, sleep, freeze and confusion counters; stat boosts (flagged as not implemented in `wpa/observations.py`); the set of items and abilities revealed so far.

Question for the product owner: should Week 5 derive approximate timers and speed evidence from these observations as a stop-gap (no re-parse), or wait for the Task 7 schema decision (a `Timer` record, one more re-parse)?
