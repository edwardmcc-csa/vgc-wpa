# Data Footprint: 601MB In, ~49GB Out

Investigate-and-report only, per Week 3 Task 7. Nothing here is
implemented — no pipeline, format, or storage change was made this week.

## What produces the 601MB -> ~49GB expansion

`battle_logs/` (601MB) holds terse textual Showdown protocol logs — one
line per event (`|move|`, `|damage|`, `|switch|`, ...). `trajs/` (measured
this session at 177,804 files, sampled at ~50.7GB total, consistent with
the ~49GB figure in the Week 2/3 dispatches) holds `vgc_bench.logs2trajs`'s
output: one pickled `imitation.data.types.Trajectory` per (battle, role)
pair, unchanged by any work done this week.

The expansion is entirely explained by how `Trajectory.obs` is built:

- Every decision point is embedded as a dense `12 * 578 = 6,936`-float32
  vector (`PolicyPlayer.embed_battle`, via `chunk_obs_len` in
  `vgc_bench/src/utils.py`) — one 578-float chunk per team slot, 12 slots
  (both sides' full 6-Pokemon teams), regardless of how many Pokemon have
  actually been revealed yet. That's 27.7KB per decision point.
- A sampled trajectory averages **9.9 decision points** (`min` 4, several
  in the teens), so a typical trajectory's `obs` array alone is roughly
  270KB before pickle overhead — matching the measured sample average of
  285KB/file almost exactly.
- Measured directly on one sample trajectory: only **~10% of the 6,936
  floats in each decision point's vector are nonzero** (the embedding is
  mostly one-hot/multi-hot categorical: move types, statuses, genders,
  etc.), and **only 2-30 of the 6,936 entries change between one decision
  point and the next** in the same trajectory (0.03%-0.4%) — the
  overwhelming majority of every vector is a verbatim repeat of the
  previous timestep's encoding of Pokemon that haven't changed state.

So: 80x is the cost of re-encoding two full 6-Pokemon teams as a dense,
mostly-zero, mostly-redundant float vector at every single decision point,
rather than a raw or delta-encoded log line.

## Is a more compact representation available without losing information?

Yes, and it doesn't require touching `vgc_bench`'s parsing logic at all —
purely a storage-format question for `trajs/*.pkl`.

Measured directly (30-file random sample, pickle vs. `np.savez_compressed`
holding the identical `obs`/`acts` arrays):

| Format | Sample bytes | Ratio | Projected corpus size |
|---|---|---|---|
| pickle (current) | 8,641,280 | 1.0x | ~49-51GB |
| `np.savez_compressed` | 152,669 | **0.018x** | **~0.9GB** |

That's a ~56x reduction, losslessly (compression is bit-exact; nothing is
approximated or discarded), from switching the on-disk container alone.
Separately, plain `zlib` on one trajectory's raw `obs` array pickle bytes
got a 61x reduction (333KB -> 5.5KB) — consistent with the `savez` result
and confirming the redundancy is real, not a sampling artifact.

Not measured this week, flagged for later if compaction is ever
prioritized: float16 storage is *not* bit-exact for this data (confirmed
by direct comparison) — a meaningful fraction of the ~147 distinct values
per trajectory are non-integer stat/HP-fraction floats, not pure 0/1 flags,
so float16 would be a lossy option, not a free one.

**Per the dispatch, none of this is being implemented this week** — this
is the "is it available" answer, not a recommendation to act on it yet.

## How much do the Task 3/5 fields grow this?

Two different things share the name "the corpus output," and it matters
which one the 49GB figure and this question are about:

1. **`trajs/*.pkl`** — vgc_bench's own packed `Trajectory` format,
   described above. This is untouched by any Week 3 work (additive-only
   applies here too), so it does not grow at all. Task 8's re-parse will
   regenerate the same ~49GB.
2. **`wpa`'s own `BattleState` records** — the semantic schema this week's
   tasks actually extended (`set_id`, `game_index`,
   `set_score_entering_game`, `decision_index`). There is no existing
   batch driver that persists these for the whole corpus today — they are
   currently produced by `parse_battle_states` per-battle (used by tests
   and, per Task 8, corpus-wide validation), not written to disk as a
   standing corpus artifact. If they ever were persisted (e.g. as JSON,
   matching `tests/fixtures/battles/*.json`'s format), measured directly
   on a real bo3 decider-game state:

   - one `BattleState` as JSON, current schema: **1,343 bytes**
   - the same state with the Task 3/5 fields stripped out: **1,217 bytes**
   - **delta: ~126 bytes/state, ~9.4%** for bo3 games (less for Reg-A/bo1
     games, where `set_id`/`game_index`/`set_score_entering_game` are all
     `null` and the delta is just the `decision_index` integer, a few
     bytes).

   Extrapolated at the corpus's measured ~9.9 decision points/trajectory
   and 177,804 trajectories, a full corpus-wide `BattleState` JSON dump
   would run **~2.4GB total** even with the new fields included — about
   2% of `trajs/*.pkl`'s size, because it stores a semantic summary
   (species names, floats, booleans) rather than a dense repeated
   one-hot embedding.

If Task 8's "run one full parse with the new schema" means (1), the
answer to "how much does Task 3 grow this" is zero — vgc_bench's output
format is unaffected. If it means producing a corpus-wide dump of (2), the
answer is the ~9.4%/~126-bytes-per-state figure above, on a total that is
itself two orders of magnitude smaller than the 49GB figure. Flagging
this ambiguity here rather than assuming one reading going into Task 8.
