# The damage calculator

Week 7 Task 2. Code: `wpa/damage.py` (Python side), `calc/bridge.js` (Node side).
Tests: `tests/test_damage.py`.
Check: `python -m wpa.damage` (1,000 cases), plus `--format regmb` for Reg M-B.

## What it is

We use the Smogon damage calculator, `@smogon/calc` 0.12.0, pinned in
`calc/package-lock.json` and checked by `scripts/check_pins.py`. That version has
the Champions rules: level 50, stat points in place of EVs, and the Champions
Megas. We do not compute damage ourselves.

One Node process runs the calculator. Python sends it requests in batches, named
by Showdown id, and caches the answers. Each answer is the 16 damage rolls (all
hits added up for multi-hit moves), the defender's maximum and current hit
points, and the number of hits.

**What we hand it**, for each side:
- species (Mega form once Mega Evolved), nature and stat points;
- item, ability, stat stages, status and current hit points.

**For the field:** weather, terrain, Reflect / Light Screen / Aurora Veil on the
defender's side, Friend Guard and Helping Hand. Spread moves lose a quarter only
when the request says they hit two targets.

**What we add on top of it:**
- **Fixed damage.** The calculator's Champions rules give 0 for moves whose damage
  doesn't come from stats. We compute those here:
  - Super Fang, Ruination, Nature's Madness: half the target's current hit points;
  - Endeavor;
  - Seismic Toss and Night Shade: 50, the level;
  - Final Gambit.

  Type immunity is respected (no Super Fang against a Ghost).
- **Unknown moves.** Counter, Mirror Coat, Metal Burst, Comeuppance, Bide and Beat
  Up are marked unknown, with 0 damage.
- **Aegislash** attacks in its Blade form (Stance Change).
- **Cosmetic forms** the calculator does not list (Vivillon-Garden,
  Alcremie-Rainbow-Swirl) use their base species.

## Check against Showdown's own damage code (30 Oct 2026)

Cases are drawn from real team sheets in the validation split: a random attacker,
one of its damaging moves, and a random defender from the other side. Each case
gets randomised conditions:
- stat points and nature, and Mega form half the time when the item allows it;
- stat stages, burn, and hit points;
- weather, terrain, screens, spread, and critical hits.

`calc/check_showdown.js` builds a Showdown battle for each case and asks Showdown's
own `getDamage` for all 16 rolls. It first does what Showdown does before a move
hits: type changes (Pixilate, Weather Ball, Liquid Voice, Raging Bull), Stance
Change, Protean and Libero, and the Special Attack raise from Electro Shot's
charging turn. Nothing in `pokemon-showdown/` is edited.

| | Reg M-A | Reg M-B |
|---|---|---|
| cases compared | 969 | 330 |
| ... multi-hit moves (first hit compared) | 31 | 4 |
| **every one of the 16 rolls the same** | **964** | **326** |
| the calculator stops the move (right in game; Showdown's `getDamage` does not check this) | 5 | 2 |
| the calculator does not know the move (Beat Up) | 0 | 2 |
| left out (Imposter copies a Pokemon this check does not place) | 1 | 0 |
| **unexplained differences** | **0** | **0** |

The moves the calculator stops are priority moves into Psychic Terrain or into
Armor Tail, Queenly Majesty or Dazzling, and moves into Soundproof or
Bulletproof. The game stops these too, so for our features the calculator's 0 is
the right answer.
