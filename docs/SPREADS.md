# Spread estimates

Week 7 Task 3. Code: `wpa/spreads.py`. Tests: `tests/test_spreads.py`.
Measure: `python -m wpa.spreads` (validation split, 1 game in 20), then
`python -c "from wpa.spreads import report; print(report())"`.

## Where a spread starts

Nobody's stat points are in the logs. Each Pokemon starts from Smogon's usage
statistics for its own format (Bo3 kept apart) and the month of the game, at the
1500 rating cutoff (PO, 30 Oct). They are downloaded into `usage_stats/` (not
committed):
- Reg M-A: April, May and June 2026, single games and Bo3;
- Reg M-B: June 2026.

The statistics list Mega forms apart from their base forms, so a Pokemon holding
its Mega Stone uses its Mega's entry.

**Profiles instead of raw spreads.** Raw spreads are too scattered to use one by
one. They differ by a point or two (`2/32/0/0/0/32` against `0/32/0/0/2/32`), and
it takes a median of 123 of them to cover 90% of a Pokemon's usage.

So spreads are grouped into profiles. A profile has one nature, and each stat
reads as none (0-7 points), some (8-23) or full (24-32). Its stat points are the
usage-weighted mean of its spreads, kept to 66 in all.

A Pokemon's candidates are its most used profiles, up to 90% of usage or 10
profiles, whichever comes first. In practice the cap of 10 is usually reached:
for the 60 most used Pokemon, 10 profiles cover a median of 79% of usage in Reg
M-A (May) and 81% in Reg M-B (June). This departs from the brief's "spreads
covering 90%", for the reason above.

In Reg M-B the sheet shows the nature, so only profiles with that nature are kept.
A Pokemon missing from the statistics gets a default: 32 HP, 32 in its higher
attacking stat, 2 in Speed, and the sheet's nature (or a neutral one).

## How the game refines it

Events are taken in the order of the log, and each one re-weights the
candidates of the two Pokemon involved:

- **A hit** updates both Pokemon. The defender's candidates are weighted by how
  likely the shown hit points are, averaged over the attacker's current
  weights. The same goes for the attacker's candidates, averaged over the
  defender's.
  - **The likelihood** comes from the calculator's 16 rolls.
  - **Hit points:** Champions shows them as `floor(100 * hp / max)`, at least 1
    while standing.
  - **The board and field at the move:** stat stages, status, held item (a resist
    berry eaten before the damage line still counts), form (Aegislash's Stance
    Change), weather, terrain, screens, Helping Hand, Friend Guard, Fairy and Dark
    Aura, and the attacker's ally's Battery, Power Spot, Steely Spirit or Flower
    Gift.
  - **Critical hits and spread moves** are read from the log.
  - **Left out:** hits that end on Focus Sash, Sturdy, Endure, a Substitute,
    Disguise or Ice Face; moves that hit several times; and moves whose damage
    does not come from the usual stats (Super Fang, Seismic Toss, Body Press, Foul
    Play, Last Respects and the like).
- **Two Pokemon moving one after the other** in the same priority bracket:
  - **What it means:** the first was at least as fast at that moment (slower
    under Trick Room). Speeds are the calculator's final Speed: stage, paralysis,
    Choice Scarf, Tailwind, weather and terrain abilities, and Unburden once the
    item is gone.
  - **Priority changes** from Prankster, Gale Wings, Triage and Grassy Glide are
    applied.
  - **Left out:** turns with anything that lets a Pokemon act out of its Speed
    order (Quick Claw, Quick Draw, Custap Berry, After You, Quash, Instruct,
    Dancer, Lagging Tail, Full Incense), and Pokemon with Stall or Mycelium Might.

To speed up the calculator, only what changes a result is sent: the attacking
stat, the defensive stats, or Speed, and the nature's effect on them. Requests
that differ only elsewhere then share one cached answer.

**Allowance for the unexplained.** 2% of events are taken as unexplained by any
spread, so one odd event cannot rule a spread out completely. Without it, belief
became overconfident and the log likelihood got worse than not refining at all.
Values 0, 0.02, 0.05 and 0.1 were tried on the validation sample; 0.02 was best
in both formats.

**No look-ahead.** A decision uses the spreads as they stood after the events of
earlier blocks of the log only (`GameBeliefs.at`).

## Does refining help? (validation, 1 game in 20, 30 Oct 2026)

Each event is predicted from the events before it only:
- **"fits"** is how often the single most likely pair of spreads allows what the
  log shows (for move order: puts them in that order);
- **log chance** is the mixture's average log chance of what happened (higher,
  that is nearer zero, is better).

| | events | fits, starting | fits, refined | log chance, starting | log chance, refined |
|---|---|---|---|---|---|
| Reg M-A hits | 4,876 | 69.0% | **73.6%** | -2.153 | **-2.100** |
| Reg M-A move orders | 3,193 | 89.8% | **91.8%** | -0.220 | **-0.193** |
| Reg M-B hits | 164 | 66.5% | **71.3%** | -2.532 | **-2.486** |
| Reg M-B move orders | 93 | 89.2% | 89.2% | -0.293 | **-0.285** |

Refining does better on every measure but one tie, so it goes into the features
(the brief's rule). Reg M-B is a small sample: 16 games at 1 in 20.

In about 6% of hits no pair of candidates fits at all. From a look at examples,
these are spreads outside the candidates and effects the log does not show.
