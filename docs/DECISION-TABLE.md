# Our own decision table

Week 6 Task 1. Code: `wpa/decisions.py`. Tests: `tests/test_decisions.py`.
Check: `python -m wpa.decisions --one-in 100`.

## Why

The stored states skip a player's decision when one of their slots did nothing and
one of their Pokemon fainted during the turn, which is decided by what happens
*after* the decision. Winners therefore had more rows than losers, turn-start rows
were won 56% of the time, and every model trained on them overrated losing
positions (Week 5 report, surprise 2).

## What it does

Decision points come from the game's own structure: team preview; the start of
every turn, for both players; after the turn's residual, a player with an empty
slot and a Pokemon left to send in (read from the board, not from what follows); a
switch during the turn (after U-turn and similar) for the player who switches. At
each, the board is tracked from the log itself (who is in, hit points, who has
fainted, who has been seen, in sheet order; Regenerator's silent heal on switching
out included), with the timers there and the field conditions at the end of each
earlier turn. The result comes from the `|win|` line, forfeits included.

## Checks on real data (30 Oct 2026)

| | Reg M-A (1 in 50 bo3, 1 in 20 single) | Reg M-B (1 in 20) |
|---|---|---|
| games | 1,938 | 214 |
| decision points | 39,251 | 4,224 |
| ... of which the old reader kept | 32,953 (84%) | 3,531 (84%) |
| board compared with the stored states | 353,544 Pokemon, **0 differ** | 38,148 Pokemon, 0 differ (after the Regenerator fix) |
| label rate, turn-start rows | **0.5000** | **0.5000** |
| label rate, all rows | 0.489 | 0.483 |

Every turn start now has one row per player, so turn-start rows are won exactly
half the time. Over all rows the rate is slightly under half because the side that
is losing Pokemon has more replacement decisions, which is the game's structure,
not a selection on the future.

## Stat stages, status and items (Week 7 Task 1)

The board now also carries, for every Pokemon, what the damage calculator needs:

- **Stat stages** (`boosts`, only the ones that are not zero, e.g. `{"atk": -1}`),
  from -6 to +6. They come from every line that changes them:
  - `-boost`, `-unboost`, `-setboost`;
  - `-clearboost`, `-clearallboost`, `-clearnegativeboost`, `-clearpositiveboost`;
  - `-invertboost`, `-copyboost`, `-swapboost`.

  Stages reset when the Pokemon switches out or faints, except that Baton Pass hands
  them to the Pokemon coming in (on about 1% of team sheets). Mega Evolution
  keeps them.
- **Status** (`status`: `brn`, `par`, `slp`, `frz`, `psn`, `tox` or empty). It comes
  from `-status`, `-curestatus` and `-cureteam`, and from the hit-point text the
  log prints (`55/100 par`). It stays through switching and clears on fainting.
- **Item** (`item`, an id such as `focussash`, empty once gone). It starts from the
  sheet. `-enditem` removes it (eaten, used, knocked off) and `-item` changes it
  (Trick and similar).

Check: `python -m wpa.decisions --one-in 100` now also lists these lines.

### Checks on real data (30 Oct 2026, 1 game in 100)

| | Reg M-A (827 games) | Reg M-B (41 games) |
|---|---|---|
| board against the stored states | 147,696 Pokemon, **0 differ** | 6,552 Pokemon, 0 differ |
| a stage the log would push past ±6 | 0 | 0 |
| stage lines (`-boost` / `-unboost` / other) | 1,842 / 3,061 / 227 | 126 / 147 / 6 |
| `-status` / `-curestatus` | 553 / 84 | 25 / 1 |
| `-enditem` / `-item` | 1,132 / 28 | 41 / 0 |
| Intimidate lowered every opposing active Pokemon | 638 of 697 | 36 of 49 |

**Every Intimidate that did not lower everyone has a reason in the log:**
- **Reg M-A:**
  - abilities that block it: Scrappy 19, Inner Focus 7, Clear Body 6, Hyper Cutter 3, Oblivious 3;
  - Mirror Armor sending it back: 19;
  - Flower Veil: 1;
  - a raise instead of a drop: 1.
- **Reg M-B:**
  - a raise instead of a drop: 6;
  - abilities that block it: Clear Body 2, Inner Focus 2, Scrappy 1;
  - Flower Veil: 1;
  - immune: 1.

In the raise cases the log shows a plain `-boost` of Attack, mostly on Staraptor.
The board follows the log in every case, so a blocked or reflected Intimidate
leaves the right stages.
