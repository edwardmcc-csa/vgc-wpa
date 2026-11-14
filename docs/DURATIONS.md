# Durations of timed effects

**Generated. Do not edit by hand.** Regenerate with `python -m wpa.durations --out docs/DURATIONS.md`; a test fails if this file differs from a fresh generation.

Source: the pinned copies of Showdown's code, `pokemon-showdown` at `913da3602a3aa1db79f9fdc5d5222eaf8d39569d`; `pokemon-showdown-mc` at `7e743761cd13cdb361fc0f58eb5a866284894f5b`, read through Showdown's own mod inheritance by `scripts/dump_durations.js`. Every row gives the file and line the number comes from.

## How to read the turn numbers

- **Base** is the duration in turns. An effect set by a move during turn T is in force on turns T to T + base - 1 and is removed in that turn's end-of-turn residual.
- An effect set *after* the residual of turn T (a replacement switching in, or a weather ability) loses no turn: it ends in the residual of T + base. Leads switch in on turn 0, before any residual, so turn 0 behaves the same way.
- **Modifiers** replace the base when the user holds the item or ability. With open team sheets both are known from the first state.
- **Ordering** adjustments add or remove a turn depending on whether the target has already moved this turn. That is visible in the log at the moment the effect starts.
- An **attempt** (counted effects below) is a turn on which the Pokemon is about to act. Turns on which it is switched out or has fainted are not attempts.
- The turns remaining at a decision point are computed from the start turn and this table only, never from the end event (`wpa.durations.turns_remaining`).

## Formats and mods

| Format | Copy of Showdown's code | Showdown mod | Inherits |
|---|---|---|---|
| regma | `pokemon-showdown` | `championsregma` | `championsregma`, `champions` |
| regmb | `pokemon-showdown` | `champions` | `champions` |
| regmc | `pokemon-showdown-mc` | `champions` | `champions` |

## regma (`pokemon-showdown`, `championsregma`)

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


## regmb (`pokemon-showdown`, `champions`)

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


## regmc (`pokemon-showdown-mc`, `champions`)

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
| Counter | - | 1 | - | - | data/moves.ts:3008 |
| Crafty Shield | sideCondition | 1 | - | - | data/moves.ts:3158 |
| DeltaStream | weather | 0 | - | - | data/conditions.ts:736 |
| DesolateLand | weather | 0 | - | - | data/conditions.ts:599 |
| Dig | - | 2 | - | - | data/moves.ts:3609 |
| Disable | volatileStatus | 5 | - | -1 if `this.queue.willMove(pokemon) || pokemon === this.activePokemon && this.activeMove && !this.activeMove.isExternal` (data/moves.ts:3675) | data/moves.ts:3667 |
| Dive | - | 2 | - | - | data/moves.ts:3778 |
| Echoed Voice | - | 2 | - | - | data/moves.ts:4427 |
| Electric Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:4514) | - | data/moves.ts:4512 |
| Electrify | volatileStatus | 1 | - | - | data/moves.ts:4574 |
| Embargo | volatileStatus | 5 | - | - | data/moves.ts:4694 |
| Encore | volatileStatus | 3 | - | +1 if `!action   [where action = this.queue.willMove(target)]` (data/mods/champions/moves.ts:328) | data/moves.ts:4738 |
| Endure | volatileStatus | 1 | - | - | data/moves.ts:4826 |
| Fairy Lock | pseudoWeather | 2 | - | - | data/moves.ts:5064 |
| Fire Pledge | - | 4 | - | - | data/moves.ts:5426 |
| flinch | - | 1 | - | - | data/conditions.ts:200 |
| Fly | - | 2 | - | - | data/moves.ts:5921 |
| Focus Punch | - | 1 | - | - | data/moves.ts:6025 |
| Follow Me | volatileStatus | 1 | - | - | data/moves.ts:6056 |
| Fury Cutter | - | 2 | - | - | data/moves.ts:6326 |
| futuremove | slotCondition | 3 | - | - | data/conditions.ts:384 |
| G-Max Cannonade | - | 4 | - | - | data/moves.ts:6756 |
| G-Max Vine Lash | - | 4 | - | - | data/moves.ts:7386 |
| G-Max Volcalith | - | 4 | - | - | data/moves.ts:7424 |
| G-Max Wildfire | - | 4 | - | - | data/moves.ts:7484 |
| gem | - | 1 | - | - | data/conditions.ts:469 |
| Grass Pledge | - | 4 | - | - | data/moves.ts:7625 |
| Grassy Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:7690) | - | data/moves.ts:7688 |
| Gravity | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:7770) | - | data/moves.ts:7768 |
| Hail | weather | 5 | item `icyrock`: 8 (data/conditions.ts:675) | - | data/conditions.ts:673 |
| Heal Block | volatileStatus | 5 | trigger `Psychic Noise`: 2 (data/moves.ts:8290); ability `persistent`: 7 (data/moves.ts:8293) | - | data/moves.ts:8288 |
| Helping Hand | volatileStatus | 1 | - | - | data/moves.ts:8590 |
| Ice Ball | - | 1 | - | - | data/moves.ts:9287 |
| Ion Deluge | pseudoWeather | 1 | - | - | data/moves.ts:9689 |
| King's Shield | volatileStatus | 1 | - | - | data/moves.ts:9926 |
| Laser Focus | volatileStatus | 2 | - | - | data/moves.ts:10026 |
| Light Screen | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:10330) | - | data/moves.ts:10328 |
| Lock-On | - | 2 | - | - | data/moves.ts:10414 |
| lockedmove | - | 2 | - | - | data/conditions.ts:256 |
| Lucky Chant | sideCondition | 5 | - | - | data/moves.ts:10515 |
| Magic Coat | volatileStatus | 1 | - | - | data/moves.ts:10705 |
| Magic Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:10769) | - | data/moves.ts:10767 |
| Magnet Rise | volatileStatus | 5 | - | - | data/moves.ts:10875 |
| Mat Block | sideCondition | 1 | - | - | data/moves.ts:11005 |
| Max Guard | volatileStatus | 1 | - | - | data/moves.ts:11178 |
| Me First | - | 1 | - | - | data/moves.ts:11556 |
| Micle Berry | - | 2 | - | - | data/items.ts:4108 |
| Mirror Coat | - | 1 | - | - | data/moves.ts:12006 |
| Mist | sideCondition | 5 | - | - | data/moves.ts:12084 |
| Misty Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:12167) | - | data/moves.ts:12165 |
| Mud Sport | pseudoWeather | 5 | - | - | data/moves.ts:12469 |
| mustrecharge | - | 2 | - | - | data/conditions.ts:366 |
| Obstruct | volatileStatus | 1 | - | - | data/moves.ts:12889 |
| partiallytrapped | - | random 5-6 | item `gripclaw`: 8 (data/conditions.ts:226) | - | data/conditions.ts:224 |
| Perish Song | - | 4 | - | - | data/moves.ts:13259 |
| Phantom Force | - | 2 | - | - | data/moves.ts:13326 |
| Powder | volatileStatus | 1 | - | - | data/moves.ts:13668 |
| PrimordialSea | weather | 0 | - | - | data/conditions.ts:521 |
| Protect | volatileStatus | 1 | - | - | data/moves.ts:13976 |
| Psychic Terrain | terrain | 5 | item `terrainextender`: 8 (data/moves.ts:14106) | - | data/moves.ts:14104 |
| Pursuit | - | 1 | - | - | data/moves.ts:14394 |
| Quick Guard | sideCondition | 1 | - | - | data/moves.ts:14503 |
| Rage Powder | volatileStatus | 1 | - | - | data/moves.ts:14609 |
| RainDance | weather | 5 | item `damprock`: 8 (data/conditions.ts:485) | - | data/conditions.ts:483 |
| Reflect | sideCondition | 5 | item `lightclay`: 8 (data/moves.ts:14852) | - | data/moves.ts:14850 |
| Revival Blessing | slotCondition | 1 | - | - | data/moves.ts:15128 |
| Rollout | - | 1 | - | - | data/moves.ts:15407 |
| rolloutstorage | - | 2 | - | - | data/conditions.ts:949 |
| Roost | - | 1 | - | - | data/moves.ts:15438 |
| Safeguard | sideCondition | 5 | ability `persistent`: 7 (data/moves.ts:15584) | - | data/moves.ts:15582 |
| Sandstorm | weather | 5 | item `smoothrock`: 8 (data/conditions.ts:637) | - | data/conditions.ts:635 |
| Shadow Force | - | 2 | - | - | data/moves.ts:16091 |
| Shell Trap | - | 1 | - | - | data/moves.ts:16293 |
| Silk Trap | volatileStatus | 1 | - | - | data/moves.ts:16419 |
| Sky Drop | - | 2 | - | - | data/moves.ts:16734 |
| Snatch | volatileStatus | 1 | - | - | data/moves.ts:17112 |
| Snowscape | weather | 5 | item `icyrock`: 8 (data/conditions.ts:705) | - | data/conditions.ts:703 |
| Spiky Shield | volatileStatus | 1 | - | - | data/moves.ts:17546 |
| Spotlight | volatileStatus | 1 | - | - | data/moves.ts:17774 |
| stall | - | 2 | - | - | data/conditions.ts:446 |
| SunnyDay | weather | 5 | item `heatrock`: 8 (data/conditions.ts:555) | - | data/conditions.ts:553 |
| Syrup Bomb | - | 4 | - | - | data/moves.ts:18768 |
| Tailwind | sideCondition | 4 | ability `persistent`: 6 (data/moves.ts:18884) | - | data/moves.ts:18882 |
| Taunt | volatileStatus | 3 | - | +1 if `target.activeTurns && !this.queue.willMove(target)` (data/moves.ts:18984) | data/moves.ts:18981 |
| Telekinesis | volatileStatus | 3 | - | - | data/moves.ts:19130 |
| Throat Chop | - | 2 | - | - | data/moves.ts:19395 |
| Trick Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:19949) | - | data/moves.ts:19947 |
| twoturnmove | - | 2 | - | - | data/conditions.ts:290 |
| Uproar | - | 3 | - | - | data/moves.ts:20228 |
| Water Pledge | - | 4 | - | - | data/moves.ts:20561 |
| Water Sport | pseudoWeather | 5 | - | - | data/moves.ts:20635 |
| Wide Guard | sideCondition | 1 | - | - | data/moves.ts:20821 |
| Wish | slotCondition | 2 | - | - | data/moves.ts:20924 |
| Wonder Room | pseudoWeather | 5 | ability `persistent`: 7 (data/moves.ts:20984) | - | data/moves.ts:20982 |
| Yawn | volatileStatus | 2 | - | - | data/moves.ts:21150 |

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
