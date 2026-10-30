# Timers joined to the stored states

Week 5 Task 3. Code: `wpa.timers.track_decisions`, `wpa/timer_join.py`. Tests:
`tests/test_timer_join.py` (19, including the three real games in
`tests/fixtures/w5`). Check on real data: `python -m wpa.timer_join --one-in 100`.

## How a state gets its timers

The stored states are snapshots `vgc_bench`'s LogReader takes as it replays a
log. It cuts the log into blocks at the blank `|` lines and takes a snapshot,
before a block, for each player who acts in that block. `track_decisions`
reproduces those cut points from the log, and computes the timers in force at
each from the log *before* the point only.

Each decision point also records **when in the turn** it was taken, which the
state itself does not say:

| Moment | Decision points (both formats, both players) |
|---|---|
| preview (team preview, turn 0) | 322,611 |
| turn_start | 1,019,577 |
| after_turn (a replacement after the residual) | 254,501 |
| mid_turn (a switch during the turn, such as after U-turn) | 63,584 |

This matters for two reasons. A decision after the turn has one turn fewer left
on everything than one at the start of the same turn. And `decision_index` 0 is
not always the start of the turn: LogReader skips a player's turn-start snapshot
when one of their slots did nothing and one of their Pokemon fainted in that
turn, so their replacement becomes decision 0.

`wpa.timer_join.orient` turns the timers round to "ours" and "theirs" for the
player whose file it is. `align` lines them up with a file's states, one to one,
and refuses (returns None) if the (turn, decision_index) sequence does not match.

## Checks on real data (29 Oct 2026)

One game in 100 of Reg M-A best-of-three games, one game in ten of the other three
log files.

| | Reg M-A | Reg M-B |
|---|---|---|
| state files aligned exactly | 2,930 of 2,930 | 880 of 880 |
| decision points | 28,119 | 8,039 |
| with at least one timer or counter | 51% | 55% |

**Cross-check against the observations.** The observations carry their own
record of the weather, field and side conditions, kept by separate code. At every
turn-start decision, the timers were compared with what the turn's first
observation lists. Across Tailwind, the screens, Aurora Veil, Trick Room,
Gravity, Magic Room, the terrains and the weathers, in both formats, **no
disagreement is left unexplained**. The explained ones are all weather:

- *started this turn*: the observation lists a weather the decision did not have,
  because a Pokemon switched in at the start of the turn set it before the first
  move (for example Pelipper's Drizzle). The decision came first, so the timer is
  right to leave it out;
- *ended this turn*: the mirror image, the old weather replaced at the start of
  the turn.

## The side file

`python -m wpa.timers --timers-out timers.jsonl.gz` now stores, per game and per
player, the timers at every decision point (with its moment), as well as at each
turn start. 88,905 games; 1,581,793 Reg M-A and 78,480 Reg M-B decision points.
The Reg M-B count equals the number of non-terminal states in `wpa_states/`
exactly. Reg M-A has 92 more than `splits.json` counts. 65 of them are the
best-of-five set the splits drop. The other 27 are most likely the one battle that
failed to parse in Week 3, which has no state files.

## Leakage

A decision's timers depend only on the log before it. The tests cut the log
after every block and show every earlier decision unchanged, and delete a later
end event and show nothing before it changes.
