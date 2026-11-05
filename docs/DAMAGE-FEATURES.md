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

---

## Week 8: this turn's options (H), the likely back (I), the whole board (J)

Code: `_group_h`, `_group_i`, `_group_j` in `wpa/features.py`. Tests:
`tests/test_turn_features.py`, `tests/test_board_actions.py`,
`tests/test_damage_features.py`.

**The board now also tracks** (`wpa/decisions.py`), for each Pokemon:
- whether it has used a move since it came in;
- its last move (a Choice item locks it to this; an item received by Trick
  locks it from its next move);
- how many Protect-type moves in a row have worked.

**H, what each side can do this turn**, for its active Pokemon:

| column | what it is |
|---|---|
| `fakeout_n` | Fake Out on the sheet and not used a move since coming in |
| `locked_n` | holding a Choice item and locked into a move |
| `protect_ready_n` / `protect_risky_n` | has a Protect-type move; ready, or one worked last turn (the next works a third as often) |
| `mega_available` / `mega_used` | the side still has a Mega Stone holder that can Mega Evolve, or has Mega Evolved |

Group G now uses only the locked move of a Choice-locked Pokemon.

**The real-data check** covered a quarter of all games (21,208 in Reg M-A and
1,027 in Reg M-B):
- **Fake Out:** of 235 used after the Pokemon had already moved, 233 failed, as
  they should.
- **Choice lock:** Choice-locked Pokemon used their locked move 12,450 times and
  Struggle 79 times (the locked move disabled). They used another move only 8
  times: Trick swaps and Magic Room.

**I, the likely back** (`docs/BRING.md`), for each side:

| column | what it is |
|---|---|
| `back_entropy` | how uncertain its back is (entropy over the sets of four still possible) |
| `back_dmg_exp` | expected best share of an opposing active's hit points its unseen Pokemon could take |
| `back_ko_exp` | expected number of opposing actives its unseen Pokemon could knock out |
| `back_speed_exp` | expected Speed of its fastest unseen Pokemon |
| `back_outspeeds_exp` | expected number of its unseen Pokemon faster than the opponent's fastest active |

**J, the whole board.** For each side as the attacker, every Pokemon still
standing is matched against every Pokemon on the other side. An unseen Pokemon on
either side is counted by the chance it was brought.

| column | what it is |
|---|---|
| `ko_targets_exp` | expected number of the other side's Pokemon that something of ours knocks out in one hit |
| `outko_targets_exp` | the same, while moving first |
| `2hko_targets_exp` | the same, in two hits |
| `outko_pairs_exp` | expected number of pairs where one of ours moves first and knocks one of theirs out |

**Build time with H, I and J:** about the same as v3. The cloud workspace took
about 0.26 seconds per game per process, because the calculator's cache answers
most of the new requests.
