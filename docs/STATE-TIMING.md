# What a stored state knows, and when

Week 5 Task 1. Code: `wpa/state_timing.py`. Tests: `tests/test_state_timing.py`,
with six real game files (three games, both players) in `tests/fixtures/w5/`.
Rerun the audit with `python -m wpa.state_timing --one-in 100`.

## The short version

**More than half of all decision points carry observations from after the
decision.** Any feature built from `state.observations` as stored would leak
the future into the model. The fix is a rule, not a re-parse: use observations
from earlier turns only (below).

## What a state is

A state is a copy of the battle made at the moment a player has to choose
(`LogReader.choose_move` in `vgc_bench/logs2trajs.py`). It contains only what
had been broadcast up to that choice.

- **Turn 0** holds team preview (decision 0, every Pokemon at 0 hit points because
  none is revealed) and lead selection (decision 1).
- **Each later turn** has a decision at its start (decision_index 0) and one more
  for every forced switch after a knock-out. A forced switch is taken after the
  turn's moves, so its snapshot already shows the damage.
- **The last state of every file is a terminal marker**, not a decision. It is the
  only state with an `outcome` (checked on every sampled file, no exceptions). The
  v0 baseline already sets these aside as "decided".

## Where the leak is

The parser attaches every event of turn N to the state with the highest
`decision_index` of turn N. That is right when turn N has a forced switch: the
state comes after the events. It is wrong when turn N has only its starting
decision: the events are attached to the snapshot taken *before* them.

Sample: one game in 100 for the whole corpus (1,654 Reg M-A files, 82 Reg M-B
files), and a larger Reg M-B sample, one game in five, because the first has only
41 M-B games (1,648 files).

| | Reg M-A | Reg M-B (1 in 5) |
|---|---|---|
| decision points | 15,314 | 15,275 |
| with observations | 67.9% | 68.6% |
| **carrying events from after the decision** | **54.3%** | **51.7%** |
| hit-point check: snapshot is before its events | 73.4% | 73.7% |

The hit-point check is independent evidence: it compares the last hit points an
observation reports for a Pokemon with the same Pokemon's hit points in the
snapshot. Where they differ, the snapshot was taken before the event. It agrees
with the structural rule almost everywhere. The exceptions are 3.6% of states
with evidence in Reg M-A (318 of 8,829) and 4.9% in Reg M-B (427 of 8,672): last decisions of a turn whose
snapshot still lags a few end-of-turn events (damage with no move behind it,
recoveries). They are not flagged by the structure rule, which is why the rule
below is stricter than it needs to be.

## The rule for features

**A decision at turn N may use observations carried by states of turns before N,
and nothing carried by a state of turn N.**

- Safe: events of turn N-1 and earlier are over before turn N starts.
- Costs something: at a forced-switch decision the same turn's moves are public
  but excluded. The snapshot's own hit points and fainted flags already show their
  effect, so the loss is small.
- `usable_observations(states, k)` implements it. Tests prove it uses only earlier
  turns on all six real files, that cutting the game after the decision changes
  nothing, and that rewriting the future changes nothing.

## Joining timers (Task 3) follows from this

A snapshot at `(turn N, decision_index 0)` is taken at the start of turn N, which
is where `GameTimers.snapshots[N]` is computed (at the `|turn|N` line). A forced
switch at `(N, d>0)` is after turn N's moves and residual, so turns left are one
fewer than the turn-start snapshot says for effects that end at the end of turn N.
Task 3 handles that case explicitly.

## Other findings

- **About 35% of games end by forfeit or timeout.** In the Reg M-B raw logs, 104 of
  324 single games contain "forfeited." and 2 more end on inactivity. In the state
  data the loser still shows a Pokemon with hit points in 38% of Reg M-A and 35% of
  Reg M-B files (median remaining hit points of the leftover Pokemon about 85% in a
  Reg M-B check). The label is still the real result, but a win probability
  model is partly predicting concessions, not knock-outs. Worth a product-owner
  decision on whether concessions need their own treatment.
- **Hit points shown for a decision are the player's last-seen values.** Unseen or
  unbrought Pokemon, including the player's own bench, are at 0.0 (see
  `docs/OPP-POKEMON.md`).
- **Nothing is revealed at team preview**, so decision 0 of turn 0 carries no
  information about which Pokemon are brought.

## Decision-point rule (what a model is asked to score)

Every state except the terminal marker. That is 100% of non-terminal states: no
state is dropped. The v0 baseline's "undecided" filter (`outcome is None`) selects
exactly the same states (tested on the six fixtures; the audit finds one terminal
state, last, in every sampled file).
