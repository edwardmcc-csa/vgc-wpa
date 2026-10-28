# Durations of timed effects

**Generated. Do not edit by hand.** Regenerate with `python -m wpa.durations --out docs/DURATIONS.md`; a test fails if this file differs from a fresh generation.

Source: the pinned `pokemon-showdown` submodule at `913da3602a3aa1db79f9fdc5d5222eaf8d39569d`, read through Showdown's own mod inheritance by `scripts/dump_durations.js`. Every row gives the file and line the number comes from.

## How to read the turn numbers

- **Base** is the duration in turns. An effect set by a move during turn T is in force on turns T to T + base - 1 and is removed in that turn's end-of-turn residual.
- An effect set *after* the residual of turn T (a replacement switching in, or a weather ability) loses no turn: it ends in the residual of T + base. Leads switch in on turn 0, before any residual, so turn 0 behaves the same way.
- **Modifiers** replace the base when the user holds the item or ability. With open team sheets both are known from the first state.
- **Ordering** adjustments add or remove a turn depending on whether the target has already moved this turn. That is visible in the log at the moment the effect starts.
- An **attempt** (counted effects below) is a turn on which the Pokemon is about to act. Turns on which it is switched out or has fainted are not attempts.
- The turns remaining at a decision point are computed from the start turn and this table only, never from the end event (`wpa.durations.turns_remaining`).

## Formats and mods

| Format | Showdown mod | Inherits |
|---|---|---|
| regma | `championsregma` | `championsregma`, `champions` |
| regmb | `champions` | `champions` |

## regma (`championsregma`)

### Timed effects

| Effect | Attached as | Turns | Modifiers | Ordering | Source |
|---|---|---|---|---|---|
| Ally Switch | - | 2 | - | - | data/moves.ts:333 |
| Aurora Veil | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:846) | - | data/moves.ts:844 |
| Baneful Bunker | volatileStatus | 1 | - | - | data/moves.ts:1003 |
| Beak Blast | - | 1 | - | - | data/moves.ts:1132 |
| Bide | volatileStatus | 3 | - | - | data/moves.ts:1280 |
| Bounce | - | 2 | - | - | data/moves.ts:1727 |
| Burning Bulwark | volatileStatus | 1 | - | - | data/moves.ts:2038 |
| Chilly Reception | weather | 1 | - | - | data/moves.ts:2411 |
| Counter | - | 1 | - | - | data/moves.ts:3007 |
| Crafty Shield | sideCondition | 1 | - | - | data/moves.ts:3157 |
| DeltaStream | weather | 0 | - | - | data/conditions.ts:732 |
| DesolateLand | weather | 0 | - | - | data/conditions.ts:595 |
| Dig | - | 2 | - | - | data/moves.ts:3609 |
| Disable | volatileStatus | 5 | - | -1 if `this.queue.willMove(pokemon) || pokemon === this.activePokemon && this.activeMove && !this.activeMove.isExternal` (data/moves.ts:3672) | data/moves.ts:3664 |
| Dive | - | 2 | - | - | data/moves.ts:3775 |
| Echoed Voice | - | 2 | - | - | data/moves.ts:4424 |
| Electric Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:4511) | - | data/moves.ts:4509 |
| Electrify | volatileStatus | 1 | - | - | data/moves.ts:4571 |
| Embargo | volatileStatus | 5 | - | - | data/moves.ts:4691 |
| Encore | volatileStatus | 3 | - | +1 if `!action   [where action = this.queue.willMove(target)]` (data/mods/champions/moves.ts:305) | data/moves.ts:4735 |
| Endure | volatileStatus | 1 | - | - | data/moves.ts:4823 |
| Fairy Lock | pseudoWeather | 2 | - | - | data/moves.ts:5061 |
| Fire Pledge | - | 4 | - | - | data/moves.ts:5423 |
| flinch | - | 1 | - | - | data/conditions.ts:200 |
| Fly | - | 2 | - | - | data/moves.ts:5918 |
| Focus Punch | - | 1 | - | - | data/moves.ts:6022 |
| Follow Me | volatileStatus | 1 | - | - | data/moves.ts:6053 |
| Fury Cutter | - | 2 | - | - | data/moves.ts:6323 |
| futuremove | slotCondition | 3 | - | - | data/conditions.ts:384 |
| G-Max Cannonade | - | 4 | - | - | data/moves.ts:6753 |
| G-Max Vine Lash | - | 4 | - | - | data/moves.ts:7383 |
| G-Max Volcalith | - | 4 | - | - | data/moves.ts:7421 |
| G-Max Wildfire | - | 4 | - | - | data/moves.ts:7481 |
| gem | - | 1 | - | - | data/conditions.ts:465 |
| Grass Pledge | - | 4 | - | - | data/moves.ts:7622 |
| Grassy Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:7687) | - | data/moves.ts:7685 |
| Gravity | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:7767) | - | data/moves.ts:7765 |
| Hail | weather | 5 | item `icyrock`: 8 (data/conditions.ts:671) | - | data/conditions.ts:669 |
| Heal Block | volatileStatus | 5 | trigger `Psychic Noise`: 2 (data/moves.ts:8289); ability `persistent`: 7 (data/moves.ts:8292) | - | data/moves.ts:8287 |
| Helping Hand | volatileStatus | 1 | - | - | data/moves.ts:8589 |
| Ice Ball | - | 1 | - | - | data/moves.ts:9287 |
| Ion Deluge | pseudoWeather | 1 | - | - | data/moves.ts:9689 |
| King's Shield | volatileStatus | 1 | - | - | data/moves.ts:9926 |
| Laser Focus | volatileStatus | 2 | - | - | data/moves.ts:10026 |
| Light Screen | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:10329) | - | data/moves.ts:10327 |
| Lock-On | - | 2 | - | - | data/moves.ts:10413 |
| lockedmove | - | 2 | - | - | data/conditions.ts:256 |
| Lucky Chant | sideCondition | 5 | - | - | data/moves.ts:10514 |
| Magic Coat | volatileStatus | 1 | - | - | data/moves.ts:10704 |
| Magic Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:10768) | - | data/moves.ts:10766 |
| Magnet Rise | volatileStatus | 5 | - | - | data/moves.ts:10874 |
| Mat Block | sideCondition | 1 | - | - | data/moves.ts:11004 |
| Max Guard | volatileStatus | 1 | - | - | data/moves.ts:11177 |
| Me First | - | 1 | - | - | data/moves.ts:11555 |
| Micle Berry | - | 2 | - | - | data/items.ts:4085 |
| Mirror Coat | - | 1 | - | - | data/moves.ts:12010 |
| Mist | sideCondition | 5 | - | - | data/moves.ts:12088 |
| Misty Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:12171) | - | data/moves.ts:12169 |
| Mud Sport | pseudoWeather | 5 | - | - | data/moves.ts:12473 |
| mustrecharge | - | 2 | - | - | data/conditions.ts:366 |
| Obstruct | volatileStatus | 1 | - | - | data/moves.ts:12898 |
| partiallytrapped | - | random 5-6 | item `gripclaw`: 8 (data/conditions.ts:226) | - | data/conditions.ts:224 |
| Perish Song | - | 4 | - | - | data/moves.ts:13268 |
| Phantom Force | - | 2 | - | - | data/moves.ts:13335 |
| Powder | volatileStatus | 1 | - | - | data/moves.ts:13677 |
| PrimordialSea | weather | 0 | - | - | data/conditions.ts:517 |
| Protect | volatileStatus | 1 | - | - | data/moves.ts:13985 |
| Psychic Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:14115) | - | data/moves.ts:14113 |
| Pursuit | - | 1 | - | - | data/moves.ts:14407 |
| Quick Guard | sideCondition | 1 | - | - | data/moves.ts:14512 |
| Rage Powder | volatileStatus | 1 | - | - | data/moves.ts:14618 |
| RainDance | weather | 5 | item `damprock`: 8 (data/conditions.ts:481) | - | data/conditions.ts:479 |
| Reflect | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:14861) | - | data/moves.ts:14859 |
| Revival Blessing | slotCondition | 1 | - | - | data/moves.ts:15137 |
| Rollout | - | 1 | - | - | data/moves.ts:15417 |
| rolloutstorage | - | 2 | - | - | data/conditions.ts:945 |
| Roost | - | 1 | - | - | data/moves.ts:15448 |
| Safeguard | sideCondition | 5 | ability `persistent`: 7 (data/moves.ts:15594) | - | data/moves.ts:15592 |
| Sandstorm | weather | 5 | item `smoothrock`: 8 (data/conditions.ts:633) | - | data/conditions.ts:631 |
| Shadow Force | - | 2 | - | - | data/moves.ts:16101 |
| Shell Trap | - | 1 | - | - | data/moves.ts:16303 |
| Silk Trap | volatileStatus | 1 | - | - | data/moves.ts:16429 |
| Sky Drop | - | 2 | - | - | data/moves.ts:16743 |
| Snatch | volatileStatus | 1 | - | - | data/moves.ts:17121 |
| Snowscape | weather | 5 | item `icyrock`: 8 (data/conditions.ts:701) | - | data/conditions.ts:699 |
| Spiky Shield | volatileStatus | 1 | - | - | data/moves.ts:17555 |
| Spotlight | volatileStatus | 1 | - | - | data/moves.ts:17783 |
| stall | - | 2 | - | - | data/conditions.ts:442 |
| SunnyDay | weather | 5 | item `heatrock`: 8 (data/conditions.ts:551) | - | data/conditions.ts:549 |
| Syrup Bomb | - | 4 | - | - | data/moves.ts:18782 |
| Tailwind | sideCondition | 4 | ability `persistent`: 6 (data/moves.ts:18898) | - | data/moves.ts:18896 |
| Taunt | volatileStatus | 3 | - | +1 if `target.activeTurns && !this.queue.willMove(target)` (data/moves.ts:18998) | data/moves.ts:18995 |
| Telekinesis | volatileStatus | 3 | - | - | data/moves.ts:19144 |
| Throat Chop | - | 2 | - | - | data/moves.ts:19409 |
| Trick Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:19963) | - | data/moves.ts:19961 |
| twoturnmove | - | 2 | - | - | data/conditions.ts:290 |
| Uproar | - | 3 | - | - | data/moves.ts:20242 |
| Water Pledge | - | 4 | - | - | data/moves.ts:20575 |
| Water Sport | pseudoWeather | 5 | - | - | data/moves.ts:20649 |
| Wide Guard | sideCondition | 1 | - | - | data/moves.ts:20835 |
| Wish | slotCondition | 2 | - | - | data/moves.ts:20938 |
| Wonder Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:20992) | - | data/moves.ts:20990 |
| Yawn | volatileStatus | 2 | - | - | data/moves.ts:21158 |

### Counted effects (status and volatile counters)

**par** (`par`, data/conditions.ts:23)

- Chance 1/8 each attempt that the Pokemon cannot move (full paralysis). This is not a length.

**slp** (`slp`, data/mods/champions/conditions.ts:23)

- Starting count: 2: 1/3, 3: 2/3.
- Chance it ends at each attempt, given it has not ended: 0, 1/3, 1.
- With Early Bird the count drops by 2 per attempt: 1/3, 1.

**frz** (`frz`, data/mods/champions/conditions.ts:43)

- Starting count: 3: 1.
- Chance it ends at each attempt, given it has not ended: 1/4, 1/4, 1.
- Ends early with chance 1/4 each attempt.

**tox** (`tox`, data/conditions.ts:141)

- the poison count rises by one each residual (see the source).

**confusion** (`confusion`, data/conditions.ts:174)

- Starting count: 2: 1/4, 3: 1/4, 4: 1/4, 5: 1/4.
- Starting count when caused by `axekick`: 3: 1/3, 4: 1/3, 5: 1/3.
- Chance it ends at each attempt, given it has not ended: 0, 1/4, 1/3, 1/2, 1.
- Chance 33/100 each attempt that the Pokemon hits itself instead of moving. This is not a length.


## regmb (`champions`)

### Timed effects

| Effect | Attached as | Turns | Modifiers | Ordering | Source |
|---|---|---|---|---|---|
| Ally Switch | - | 2 | - | - | data/moves.ts:333 |
| Aurora Veil | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:846) | - | data/moves.ts:844 |
| Baneful Bunker | volatileStatus | 1 | - | - | data/moves.ts:1003 |
| Beak Blast | - | 1 | - | - | data/moves.ts:1132 |
| Bide | volatileStatus | 3 | - | - | data/moves.ts:1280 |
| Bounce | - | 2 | - | - | data/moves.ts:1727 |
| Burning Bulwark | volatileStatus | 1 | - | - | data/moves.ts:2038 |
| Chilly Reception | weather | 1 | - | - | data/moves.ts:2411 |
| Counter | - | 1 | - | - | data/moves.ts:3007 |
| Crafty Shield | sideCondition | 1 | - | - | data/moves.ts:3157 |
| DeltaStream | weather | 0 | - | - | data/conditions.ts:732 |
| DesolateLand | weather | 0 | - | - | data/conditions.ts:595 |
| Dig | - | 2 | - | - | data/moves.ts:3609 |
| Disable | volatileStatus | 5 | - | -1 if `this.queue.willMove(pokemon) || pokemon === this.activePokemon && this.activeMove && !this.activeMove.isExternal` (data/moves.ts:3672) | data/moves.ts:3664 |
| Dive | - | 2 | - | - | data/moves.ts:3775 |
| Echoed Voice | - | 2 | - | - | data/moves.ts:4424 |
| Electric Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:4511) | - | data/moves.ts:4509 |
| Electrify | volatileStatus | 1 | - | - | data/moves.ts:4571 |
| Embargo | volatileStatus | 5 | - | - | data/moves.ts:4691 |
| Encore | volatileStatus | 3 | - | +1 if `!action   [where action = this.queue.willMove(target)]` (data/mods/champions/moves.ts:305) | data/moves.ts:4735 |
| Endure | volatileStatus | 1 | - | - | data/moves.ts:4823 |
| Fairy Lock | pseudoWeather | 2 | - | - | data/moves.ts:5061 |
| Fire Pledge | - | 4 | - | - | data/moves.ts:5423 |
| flinch | - | 1 | - | - | data/conditions.ts:200 |
| Fly | - | 2 | - | - | data/moves.ts:5918 |
| Focus Punch | - | 1 | - | - | data/moves.ts:6022 |
| Follow Me | volatileStatus | 1 | - | - | data/moves.ts:6053 |
| Fury Cutter | - | 2 | - | - | data/moves.ts:6323 |
| futuremove | slotCondition | 3 | - | - | data/conditions.ts:384 |
| G-Max Cannonade | - | 4 | - | - | data/moves.ts:6753 |
| G-Max Vine Lash | - | 4 | - | - | data/moves.ts:7383 |
| G-Max Volcalith | - | 4 | - | - | data/moves.ts:7421 |
| G-Max Wildfire | - | 4 | - | - | data/moves.ts:7481 |
| gem | - | 1 | - | - | data/conditions.ts:465 |
| Grass Pledge | - | 4 | - | - | data/moves.ts:7622 |
| Grassy Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:7687) | - | data/moves.ts:7685 |
| Gravity | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:7767) | - | data/moves.ts:7765 |
| Hail | weather | 5 | item `icyrock`: 8 (data/conditions.ts:671) | - | data/conditions.ts:669 |
| Heal Block | volatileStatus | 5 | trigger `Psychic Noise`: 2 (data/moves.ts:8289); ability `persistent`: 7 (data/moves.ts:8292) | - | data/moves.ts:8287 |
| Helping Hand | volatileStatus | 1 | - | - | data/moves.ts:8589 |
| Ice Ball | - | 1 | - | - | data/moves.ts:9287 |
| Ion Deluge | pseudoWeather | 1 | - | - | data/moves.ts:9689 |
| King's Shield | volatileStatus | 1 | - | - | data/moves.ts:9926 |
| Laser Focus | volatileStatus | 2 | - | - | data/moves.ts:10026 |
| Light Screen | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:10329) | - | data/moves.ts:10327 |
| Lock-On | - | 2 | - | - | data/moves.ts:10413 |
| lockedmove | - | 2 | - | - | data/conditions.ts:256 |
| Lucky Chant | sideCondition | 5 | - | - | data/moves.ts:10514 |
| Magic Coat | volatileStatus | 1 | - | - | data/moves.ts:10704 |
| Magic Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:10768) | - | data/moves.ts:10766 |
| Magnet Rise | volatileStatus | 5 | - | - | data/moves.ts:10874 |
| Mat Block | sideCondition | 1 | - | - | data/moves.ts:11004 |
| Max Guard | volatileStatus | 1 | - | - | data/moves.ts:11177 |
| Me First | - | 1 | - | - | data/moves.ts:11555 |
| Micle Berry | - | 2 | - | - | data/items.ts:4085 |
| Mirror Coat | - | 1 | - | - | data/moves.ts:12010 |
| Mist | sideCondition | 5 | - | - | data/moves.ts:12088 |
| Misty Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:12171) | - | data/moves.ts:12169 |
| Mud Sport | pseudoWeather | 5 | - | - | data/moves.ts:12473 |
| mustrecharge | - | 2 | - | - | data/conditions.ts:366 |
| Obstruct | volatileStatus | 1 | - | - | data/moves.ts:12898 |
| partiallytrapped | - | random 5-6 | item `gripclaw`: 8 (data/conditions.ts:226) | - | data/conditions.ts:224 |
| Perish Song | - | 4 | - | - | data/moves.ts:13268 |
| Phantom Force | - | 2 | - | - | data/moves.ts:13335 |
| Powder | volatileStatus | 1 | - | - | data/moves.ts:13677 |
| PrimordialSea | weather | 0 | - | - | data/conditions.ts:517 |
| Protect | volatileStatus | 1 | - | - | data/moves.ts:13985 |
| Psychic Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:14115) | - | data/moves.ts:14113 |
| Pursuit | - | 1 | - | - | data/moves.ts:14407 |
| Quick Guard | sideCondition | 1 | - | - | data/moves.ts:14512 |
| Rage Powder | volatileStatus | 1 | - | - | data/moves.ts:14618 |
| RainDance | weather | 5 | item `damprock`: 8 (data/conditions.ts:481) | - | data/conditions.ts:479 |
| Reflect | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:14861) | - | data/moves.ts:14859 |
| Revival Blessing | slotCondition | 1 | - | - | data/moves.ts:15137 |
| Rollout | - | 1 | - | - | data/moves.ts:15417 |
| rolloutstorage | - | 2 | - | - | data/conditions.ts:945 |
| Roost | - | 1 | - | - | data/moves.ts:15448 |
| Safeguard | sideCondition | 5 | ability `persistent`: 7 (data/moves.ts:15594) | - | data/moves.ts:15592 |
| Sandstorm | weather | 5 | item `smoothrock`: 8 (data/conditions.ts:633) | - | data/conditions.ts:631 |
| Shadow Force | - | 2 | - | - | data/moves.ts:16101 |
| Shell Trap | - | 1 | - | - | data/moves.ts:16303 |
| Silk Trap | volatileStatus | 1 | - | - | data/moves.ts:16429 |
| Sky Drop | - | 2 | - | - | data/moves.ts:16743 |
| Snatch | volatileStatus | 1 | - | - | data/moves.ts:17121 |
| Snowscape | weather | 5 | item `icyrock`: 8 (data/conditions.ts:701) | - | data/conditions.ts:699 |
| Spiky Shield | volatileStatus | 1 | - | - | data/moves.ts:17555 |
| Spotlight | volatileStatus | 1 | - | - | data/moves.ts:17783 |
| stall | - | 2 | - | - | data/conditions.ts:442 |
| SunnyDay | weather | 5 | item `heatrock`: 8 (data/conditions.ts:551) | - | data/conditions.ts:549 |
| Syrup Bomb | - | 4 | - | - | data/moves.ts:18782 |
| Tailwind | sideCondition | 4 | ability `persistent`: 6 (data/moves.ts:18898) | - | data/moves.ts:18896 |
| Taunt | volatileStatus | 3 | - | +1 if `target.activeTurns && !this.queue.willMove(target)` (data/moves.ts:18998) | data/moves.ts:18995 |
| Telekinesis | volatileStatus | 3 | - | - | data/moves.ts:19144 |
| Throat Chop | - | 2 | - | - | data/moves.ts:19409 |
| Trick Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:19963) | - | data/moves.ts:19961 |
| twoturnmove | - | 2 | - | - | data/conditions.ts:290 |
| Uproar | - | 3 | - | - | data/moves.ts:20242 |
| Water Pledge | - | 4 | - | - | data/moves.ts:20575 |
| Water Sport | pseudoWeather | 5 | - | - | data/moves.ts:20649 |
| Wide Guard | sideCondition | 1 | - | - | data/moves.ts:20835 |
| Wish | slotCondition | 2 | - | - | data/moves.ts:20938 |
| Wonder Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:20992) | - | data/moves.ts:20990 |
| Yawn | volatileStatus | 2 | - | - | data/moves.ts:21158 |

### Counted effects (status and volatile counters)

**par** (`par`, data/conditions.ts:23)

- Chance 1/8 each attempt that the Pokemon cannot move (full paralysis). This is not a length.

**slp** (`slp`, data/mods/champions/conditions.ts:23)

- Starting count: 2: 1/3, 3: 2/3.
- Chance it ends at each attempt, given it has not ended: 0, 1/3, 1.
- With Early Bird the count drops by 2 per attempt: 1/3, 1.

**frz** (`frz`, data/mods/champions/conditions.ts:43)

- Starting count: 3: 1.
- Chance it ends at each attempt, given it has not ended: 1/4, 1/4, 1.
- Ends early with chance 1/4 each attempt.

**tox** (`tox`, data/conditions.ts:141)

- the poison count rises by one each residual (see the source).

**confusion** (`confusion`, data/conditions.ts:174)

- Starting count: 2: 1/4, 3: 1/4, 4: 1/4, 5: 1/4.
- Starting count when caused by `axekick`: 3: 1/3, 4: 1/3, 5: 1/3.
- Chance it ends at each attempt, given it has not ended: 0, 1/4, 1/3, 1/2, 1.
- Chance 33/100 each attempt that the Pokemon hits itself instead of moving. This is not a length.
