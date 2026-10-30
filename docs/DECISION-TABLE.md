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
