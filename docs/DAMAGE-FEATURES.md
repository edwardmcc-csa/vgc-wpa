# Damage features (group G) and real Speed

Week 7 Task 4. Code: `wpa/features.py` (`DamageContext`, `_group_g`,
`damage_contexts`). Tests: `tests/test_damage_features.py`.

## What a decision gets

Each decision gets a **damage context**:
- **the calculator:** `wpa/damage.py`, the pinned Smogon damage calculator;
- **each Pokemon's most likely spread at that moment:** `wpa/spreads.py`, starting
  from the usage statistics and refined only by hits and move orders in earlier
  blocks of the log.

Both players' Pokemon are estimated the same way. The public logs carry nobody's
stat points (PO decision 4). With the context:

**Speed (group F)** becomes the calculator's final Speed for the spread. That
takes in stat stage, paralysis, held item (Choice Scarf; Unburden once the item
is gone), Tailwind, and weather and terrain abilities. Base Speed is no longer
used.

**Damage (group G)**, for each side as the attacker, against the opposing
active Pokemon:

| column | what it is |
|---|---|
| `best_dmg` | the best share of an opposing active's current hit points one of our actives takes with one move (expected roll, capped at 1) |
| `dmg_board` | over the opposing actives, the best share each can lose, added up |
| `ko_n` | opposing actives one of ours knocks out this turn with a 50% chance or better |
| `2hko_n` | the same in two hits of one move |
| `spread_total` | the best spread move's total share over both opposing actives (spread moves at x0.75 when two are hit) |
| `bench_best` | the best share from a Pokemon seen but not active |
| `unseen_best` | the best share from a sheet Pokemon not seen yet (any of them could be in the back) |
| `unseen_ko_n` | opposing actives an unseen sheet Pokemon knocks out (50% or better) |

Each request carries what changes damage:
- **the attacker and defender:** stat stages, status (burn halves physical
  damage), held item (gone once used or knocked off), Mega form, ability, and
  the target's current hit points;
- **the field:** weather, terrain, Reflect, Light Screen and Aurora Veil on the
  defender's side, Friend Guard on the defender's ally, Fairy and Dark Aura, and
  the attacker's ally's Battery, Power Spot, Steely Spirit or Flower Gift.

Helping Hand is not included because it is not known at the decision. Status
moves and moves the calculator cannot do are skipped.

The columns read only public fields of the board, guarded by a test, and the
same mirroring as every other group (`_our_`/`_their_`).

## Check on real data (validation, turn starts)

How often at least one opposing Pokemon fainted that turn, by `g_our_ko_n` at the
turn's start:

| | `ko_n` = 0 | `ko_n` = 1 | `ko_n` = 2 |
|---|---|---|---|
| Reg M-A turns | 31,894 | 47,242 | 29,170 |
| at least one of theirs fainted | 10% | 29% | 47% |
| as many as `ko_n` fainted | | 29% | 7% |
| Reg M-B turns | 1,423 | 1,957 | 1,308 |
| at least one of theirs fainted | 8% | 28% | 46% |
| as many as `ko_n` fainted | | 28% | 7% |

The feature is a threat, not a forecast: players Protect, switch and spread their
attacks. Still, the more knock-outs are on the board, the more happen, in both
formats, which is the shape it should have.

## Building it

```
python -m wpa.features --from-logs logs_shards --out features_v3 --groups ABCDEFG --usage usage_stats --train-sample 0.2 --shards 64 --workers 4
```

`--train-sample 0.2` keeps the same 20% of Reg M-A's training sets that
`wpa.evaluate --sample 0.2` would. Reg M-B and the validation and test splits stay
whole. Leave it out for the full table.

**Build time.** About 0.26 seconds per game per worker process: refining the spreads
is two-thirds of it, and the features the rest. Each worker keeps one calculator
with its cache across the parts it builds.

The 20% table (about 35,000 games) took about 2.5 hours of computing, split
across four processes.

The full table was built on the PO's computer on 4 November 2026: 88,901 games and
1,781,911 rows. It took 27,719 seconds of computing (7.7 hours), about 0.31
seconds per game. With 4 workers that was a little under 2 hours of waiting,
against an estimate of 1.6 hours. Each worker needs about 1 GB of memory.
