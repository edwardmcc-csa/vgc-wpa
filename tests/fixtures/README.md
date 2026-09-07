# Golden battle corpus (Week 2 Task 5)

20 real, completed battles from the Week 1 historical corpus
(`battle_logs/`), each saved as one self-contained fixture in
`battles/<name>.json`: the raw replay log, plus its per-turn states computed
via `wpa.state.parse_battle_states` (the same adapter Week 1's invariant
tests use). Regenerate any of them with `wpa.fixtures.build_fixture` - see
`docs/RUNBOOK.md`.

These are real historical games, not staged or synthetic - chosen by
scanning the corpus for each property below and hand-picking a clean,
verified example, not by taking the first 20 results. Every claim below was
checked against the actual raw log text or the computed `BattleState`
fields before the battle was selected, not assumed from a filename.

## A finding that shaped this corpus: Terastallization is disabled

Before selecting anything, I searched the full 88,905-battle corpus for
`|-terastallize|` and found zero matches anywhere. That sent me to
`pokemon-showdown/data/mods/champions/scripts.ts`, which confirms it
structurally: `canTerastallize(pokemon) { return null; }` - Tera is
unconditionally disabled in this format, replaced by a fully-functional
Mega Evolution instead. Confirmed with the product owner: this holds for
M-A, M-B, and M-C, but the schema keeps a generic `gimmick` field (not a
Tera-specific boolean) so a future regulation reintroducing Tera needs no
schema change. Every "gimmick" fixture below is therefore a Mega Evolution,
the format's actual current gimmick, not a substitution I made unilaterally.

One more thing worth knowing: Mega Evolution turned out to be in **6,650 of
6,905** Reg M-A battles (96%) - so close to universal that nearly any
fixture below happens to feature one, not just the one titled for it.

## The 20 fixtures

### Required by the dispatch

**`early_forfeit`** - `gen9championsvgc2026regma-2600882478`, turn 1.
Found by scanning for `|-message|... forfeited.` and counting `|turn|`
messages before it; this was among the earliest (turn 1 is the earliest
that occurs anywhere in the corpus - no battle forfeits before turn 1
completes). Confirmed by reading the raw ending directly: `It'sJustKen -
VGC forfeited.` immediately after turn 1's upkeep.

**`turn_time_limit`** - `gen9championsvgc2026regma-2586167782`, 24 turns.
This took real investigation: I first assumed VGC has a fixed turn-count
cap and searched for a very long battle, but the longest ones (60-80 turns)
all ended normally via a fainted Pokemon, not a forced cutoff. Checking
`pokemon-showdown/data/mods/champions/rulesets.ts` showed the actual rule
is **Endless Battle Clause** plus a per-player game clock (`VGC Timer`),
not a turn cap. Searching for the real termination message
(`lost due to inactivity`) found this one: player `pipievgc103` ran out of
clock time on turn 24 and lost as a result - the format's actual limit
firing, not a stall. (I also found the corpus's only *mutual* timeout, at
turn 15 - kept this one instead since it shows a real, longer game cut off
by the clock rather than an early double-stall.)

**`mega_evolution`** - `gen9championsvgc2026regmb-2635876837`, already
part of the Week 1 hermetic fixture set, reused here rather than
duplicated. Two Mega Evolutions in one game (Aerodactyl and Metagross).
Detecting this correctly took real debugging: `Pokemon.species` never
changes on Mega Evolution during replay (poke-env's
`forme_change`/`mega_evolve` both deliberately call `_update_from_pokedex`
with `store_species=False` - confirmed by reading poke-env's source and
watching `_species` stay `"aerodactyl"` for the whole battle while
`ability` visibly changed to `toughclaws`, Mega Aerodactyl's signature
ability, and `base_stats["atk"]` jumped from 105 to 135). The reliable
signal turned out to be the same public flag vgc-bench's own
`PolicyPlayer.embed_side` already uses -
`battle.used_mega_evolve`/`.opponent_used_mega_evolve` - combined with
checking which Pokemon holds a Mega Stone (real Mega Stones are always
named `<species>ite`).

**`terrain_electric`** / **`terrain_grassy`** - satisfy "at least one
weather or terrain setter" on their own; see the extra weather/terrain
fixtures below for why there are more than the minimum.

### Extra weather and terrain variety

Real terrain and weather setting is common but not universal, so I scanned
for the exact protocol messages (`|-weather|X` where X isn't `none`,
`|-fieldstart|move: X`) and picked one clean example per distinct type
rather than reusing the same weather everywhere:

- **`weather_rain`** - `gen9championsvgc2026regma-2600504884` (Drizzle/Rain Dance)
- **`weather_sandstorm`** - `gen9championsvgc2026regma-2600774495`
- **`weather_snow`** - `gen9championsvgc2026regma-2600469227`
- **`terrain_electric`** - `gen9championsvgc2026regma-2605349359`
- **`terrain_grassy`** - `gen9championsvgc2026regma-2616082716`
- **`terrain_trick_room`** - `gen9championsvgc2026regma-2600664326`. Not
  strictly a "terrain" by the game's own terminology (Trick Room is a
  "room" effect, not one of the four terrains), but it's one of VGC
  doubles' single most important speed-control decisions and appeared in
  1,619 of 6,905 battles (23%) - too central to this format to leave out
  of a corpus meant to be M3's golden cases.

### Doubles-specific and luck-adjacent mechanics

Chosen with an eye toward DEFINITIONS.md's decision/luck split (§8) and
VGC's doubles-specific mechanics, not just "different-looking battles":

- **`double_faint`** - `gen9championsvgc2026regma-2599790190`. Both of a
  side's active Pokemon (Golurk and Sneasler) faint from a single spread
  move, forcing a two-Pokemon simultaneous switch decision - a genuinely
  doubles-specific decision point, confirmed by finding two `|faint|`
  messages 19 characters apart in the raw log.
- **`redirection`** - `gen9championsvgc2026regma-2600338065`. Rage Powder
  redirects an attack - the other core doubles-specific mechanic alongside
  spread moves and double faints.
- **`multi_hit_move`** - `gen9championsvgc2026regma-2599796217`. Maushold's
  Population Bomb hits four times in one turn against Sneasler - chosen
  over a simpler multi-hit move because Population Bomb's hit count itself
  depends on ally survival, adding a real decision-relevant wrinkle.
- **`critical_hit_decisive`** - `gen9championsvgc2026regma-2599901933`. A
  critical hit lands shortly before the game's last faint - luck (§8)
  plausibly swinging the outcome, exactly the kind of case decision/luck
  attribution needs to get right.
- **`focus_sash`** - `gen9championsvgc2026regma-2600687109`. An item-proc
  survival, distinct from a damage-roll or crit as a luck source.
- **`sitrus_berry`** - `gen9championsvgc2026regma-2600356651`. A different
  item-proc mechanism (automatic heal at an HP threshold) from Focus Sash's
  "survive lethal damage," for variety in *how* an item interacts with a
  turn's outcome.
- **`paralysis_status`** - `gen9championsvgc2026regma-2600250252`. A status
  condition in play - full-paralysis-style luck (§8's "status wake-up and
  thaw timers") is a distinct luck category from damage-roll/crit variance.

### Shape variety

- **`stomp_decisive`** - `gen9championsvgc2026regma-2600271141`, 5 turns,
  one-sided. A short, decisive game for contrast against the longer ones.
- **`long_contested_battle`** - `gen9championsvgc2026regma-2622397913`, 55
  turns, ends in a normal faint (not a timeout) - a genuinely long,
  hard-fought game, distinct from `turn_time_limit`'s clock-driven ending.

### Best-of-3 set context, from real data

Task 4 added `set_id`/`game_index`/`set_score_entering_game` to the schema
(DEFINITIONS.md §11.6/§13). These two are picked from the *same* real bo3
set (`bestof3-gen9championsvgc2026regmabo3-2600683599`) - one of the 7,968
sets in the corpus where all three games are present - so the pair
exercises both ends of the schema with genuine data instead of synthetic
values:

- **`bo3_game1`** - `gen9championsvgc2026regmabo3-2600683600`. Game 1 of
  the set: `set_score_entering_game == (0, 0)`, always true by construction.
- **`bo3_game3_decider`** - `gen9championsvgc2026regmabo3-2600685894`. The
  decider: `set_score_entering_game == (1, 1)`, also always true by
  construction (a bo3 only reaches a third game at 1-1) - verified against
  all 7,968 complete sets in the corpus with zero exceptions before this
  was ever written into the schema.

## An incidental finding worth knowing

Several of the fixtures above are filed under the non-bo3
`logs_gen9championsvgc2026regma.json` (not `regmabo3`), and yet their raw
logs *do* contain a real best-of-3 `|uhtml|bestof|` banner (confirmed
directly in `early_forfeit`, `critical_hit_decisive`, `double_faint`, and
others) - meaning some best-of-3 series get scraped into the plain
`regma` file rather than `regmabo3`. This isn't a bug in this task's code;
it's a property of the underlying corpus worth flagging, since anything
that assumes "`regma` implies no bo3 context" will be wrong for some
fraction of that file.
