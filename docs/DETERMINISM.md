# Determinism — Week 2 Task 3 finding

**Finding: no.** The pinned Pokémon Showdown build does not let us fix the
RNG seed for a live battle played through the protocol our simulation
harness actually uses. This is a negative result, investigated properly
rather than assumed, and is the dispatch's own definition of a successful
outcome for this task.

## What Showdown actually has

`pokemon-showdown/sim/prng.ts` implements a real, fully deterministic PRNG
(a Gen5-style linear congruential generator, or a ChaCha20-based one for
newer "sodium" seeds). It is genuinely seedable: `Battle` and
`RoomBattleOptions` both accept a `seed` field
(`pokemon-showdown/sim/battle.ts:224`,
`pokemon-showdown/server/room-battle.ts:490`), and the PRNG's own docstring
says exactly what we'd want: a seed plus a fixed sequence of choices
reproduces an identical simulation.

So the capability exists in the simulator core. The question is whether
anything exposes it to a normal connecting client - which is what our
harness (and any realistic training setup) is.

## What's actually reachable

I traced the exact code path a live two-agent battle takes: poke-env
issues a challenge, the opponent accepts, and the server turns that into a
battle via `Rooms.createBattle(...)`. That call site
(`pokemon-showdown/server/ladders.ts:473`) passes `format`, `players`,
`rated`, `challengeType`, `delayedStart` - and nothing else. No `seed`.
`Battle`'s constructor then falls back to `PRNG.generateSeed()`
unconditionally. This is the only creation path our RandomPlayer agents
(or any bot using the normal challenge/accept flow) can trigger.

Two other places do touch the seed, and neither fits:

- **`/importinputlog`** (`pokemon-showdown/server/chat-commands/core.ts:878`)
  starts a battle from a complete, pre-recorded input log - a seed plus
  every choice already made. It requires elevated permission
  (`checkCan('importinputlog')`, driver rank or above by Showdown's default
  permission scheme). More importantly, it replays *fixed* prior
  decisions - it isn't compatible with two live agents actually choosing
  moves during play, which is what "same seed and same agent choices" in
  the Task 3 test would need to mean for a simulation harness.

- **`/editbattle reseed [seed]`** (`pokemon-showdown/server/chat-commands/admin.ts:1622`)
  reseeds a battle that's already running. It requires `forcewin`
  permission (also driver rank or above). Even granted that permission,
  anything that happens between battle creation and the moment this
  command lands - and there's no guaranteed way to fire it before a single
  RNG call has occurred - is already non-deterministic. This can't cleanly
  guarantee determinism from the start of the battle, only from some
  uncertain point shortly after.

Neither permission comes from `--no-security`. I checked
`pokemon-showdown/server/config-loader.ts` directly: that flag maps to
`nothrottle`, `noguestsecurity`, `noipchecks` only - none of it is a
permission grant.

## Why I stopped there

Making either path work for our bot accounts would mean granting our own
server's accounts admin-level rank and then sending raw, undocumented chat
commands that poke-env's public API doesn't support - workable in the
narrow sense that it's our own local server, but it stretches past "using
the client as intended" into altering the server's permission model to get
around a restriction Showdown puts there on purpose. That lands inside the
dispatch's own rule to stop and ask rather than decide alone if determinism
turns out to require patching Showdown. So I stopped investigating there
instead of building either workaround.

## What this means downstream

We cannot pre-declare a seed and get a reproducible live battle. If exact
reproducibility is needed later (for example, replaying a specific
troubling battle to debug the model at M5), the workaround Showdown itself
provides is record-then-replay, not seed-then-generate: `/exportinputlog`
can retrieve a completed battle's full input log (seed included), which
`/importinputlog` can later replay bit-for-bit. That's a different
capability than what Task 3 asked about, but it's a real one, and worth
keeping in mind if reproducibility becomes a hard requirement rather than
a nice-to-have. It has its own permission gate
(`pokemon-showdown/server/chat-commands/core.ts:825`) that would need
separate investigation before relying on it.

No `tests/test_determinism.py` was written. The dispatch's own task
description branches on this finding: a test is the "if yes" path, and
this is "if no." Writing one that would just skip or assert around a
capability confirmed unavailable would be exactly the kind of faking the
dispatch says not to do.

## Flag for the PO

If bit-for-bit reproducibility of live battles turns out to matter for
M5 (or for anything before it), this is a real constraint to design
around now rather than discover then - the current answer is that
reproducibility would need to come from recording and replaying full
battles after the fact, not from planting a seed in advance.
