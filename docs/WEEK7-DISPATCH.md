# Week 7 — Dispatch Brief (M4 v3: damage, stat changes, and spreads the game reveals)

**Status:** drafted 30 Oct 2026 from the PO's decisions after the Week 6 report.
Work starts when the PO says go.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.

## Why

v2 knows who is faster but not how hard anything hits. That is why EC-001 did not
move: the model can see that the opponent's reserve outspeeds us after a double
knock-out, but not that it would knock out our pair (Week 6 report). Damage depends
on three things we don't model yet:
- **stat changes:** Intimidate, Swords Dance and similar;
- **status:** burn halves physical damage; paralysis halves Speed;
- **hidden investment:** stat points and, in Reg M-A, nature.

## Decisions (PO, 30 Oct 2026)

1. **Damage comes from the Smogon damage calculator, not our own.**
   `@smogon/calc` 0.12.0 (released 18 Sep 2026) has Champions mechanics, Champions
   stat points and the new Megas (checked 30 Oct). It is pinned and recorded in
   `docs/PINNED-VERSIONS.md`.
2. **Stat boosts and drops are tracked on the board.** Status, and items used up or
   removed, are tracked too, because the calculator needs them.
3. **Hidden investment starts at the most common spread, then is refined by what the
   game reveals.**
   - **Starting point:** Smogon's usage statistics for the same format and month.
     The "chaos" files list spreads in stat points, e.g. `Adamant:32/32/0/0/2/0`.
   - **Refinement:** the damage we deal to a Pokemon shows its bulk; the damage it
     deals shows its offence; who moved first shows its Speed.
   - Only what happened before the decision is used.
4. **Our own investment is known.**
   - **Your own games:** your real spreads, from your team export.
   - **The public corpus:** the logs show species, item, ability, moves and (in
     Reg M-B) nature, but nobody's stat points. So in training both sides are
     estimated the same way. Task 3 measures how far off that leaves us.

## Tasks

### Task 1 — Stat changes, status and items on the board (`wpa/decisions.py`)
- [ ] **Stat stages** for each Pokemon, from -6 to +6, from every boost line the log
      can carry:
      - `-boost`, `-unboost`, `-setboost`;
      - the clear lines: `-clearboost`, `-clearallboost`, `-clearnegativeboost`,
        `-clearpositiveboost`;
      - `-invertboost`, `-copyboost`, `-swapboost`.

      Stages reset when the Pokemon switches out; Mega Evolution keeps them.
- [ ] **Status** (burn, paralysis, poison, sleep, freeze) from `-status`,
      `-curestatus` and `-cureteam`. Status stays through switching.
- [ ] **Items:** taken from the sheet. An item is gone after `-enditem` (eaten,
      knocked off, Focus Sash used) and changed by `-item` (Trick and similar).
- [ ] Tests first, on hand-written log fragments.
- [ ] Real-data check per format:
      - every stage stays within ±6;
      - each Intimidate lowers Attack once per opposing active Pokemon;
      - a count of each event type seen;
      - the Week 6 board comparison still shows 0 differences.

### Task 2 — The damage calculator
- [ ] Pinned install of `@smogon/calc` 0.12.0 in its own `calc/` folder (package file
      and lock file committed). CI checks the version.
- [ ] One long-running Node process that Python feeds batches of (attacker,
      defender, move, field). It returns the 16 damage rolls and the defender's
      maximum hit points, with a cache.
- [ ] **Inputs from the board:**
      - species and form (Mega), level 50;
      - stat points and nature (the estimate from Task 3);
      - held item, ability, stat stages, status, current hit points.
- [ ] **Inputs from the field:**
      - weather and terrain;
      - Reflect, Light Screen and Aurora Veil on the defender's side;
      - Friend Guard;
      - spread moves at ×0.75 when they hit two targets.
- [ ] **Check against Showdown's own damage code** (a script, no edits to
      `pokemon-showdown/`): take 1,000 cases sampled from real teams, with known
      spreads. Every roll Showdown can produce must be one of the calculator's 16.
      Any mismatch is listed and explained before moving on.

### Task 3 — Spread estimates (`wpa/spreads.py`)
- [ ] **Starting point:**
      - Download the usage statistics into `usage_stats/` (not committed). Reg M-A
        games run from April to June 2026 and Reg M-B from June 2026 (from a
        sample; confirm on the whole corpus).
      - Each game uses its own month, at the 1500 rating cutoff (Smogon's standard
        weighting).
      - Candidates for each Pokemon are its most common spreads covering 90% of
        its usage, at most 10, weighted by their share.
      - In Reg M-B, keep only spreads with the nature on the sheet.
      - A Pokemon missing from the statistics gets a documented default.
- [ ] **Refinement from damage:** after each damaging hit, re-weight the candidates
      by how likely the observed hit-point change is under each. Use the 16 rolls,
      rounded to the whole percent the log shows. Critical hits use the critical
      calculation. Hits with modifiers we cannot see are skipped and counted.
- [ ] **Refinement from speed:** when two Pokemon move in the same priority bracket,
      the order rules out Speed candidates that contradict it. Ties and Trick Room
      are handled.
- [ ] **Our own spreads:** a team-export file can fix one side's spreads exactly.
      That is for your own games; in the corpus no file is given.
- [ ] **No look-ahead:** a decision uses only hits before it. A test checks that
      cutting the game after a decision changes nothing.
- [ ] **The test that matters:** predict every hit in the validation split from the
      earlier hits only. Per format, report how often the observed damage falls
      inside the predicted range: starting spread alone versus refined.
      Refinement goes into the features only if it does better.

### Task 4 — Damage features (group G), and real Speed
- [ ] For each side (named our/their, so mirroring keeps working):
      - each active Pokemon's best damage against each opposing active, as a
        share of the target's current hit points;
      - how many opposing actives it knocks out this turn with 50% chance or
        better, and how many in two hits;
      - the best spread move's total across both targets.
- [ ] **The threat in the back:** the most damaging of the opponent's unseen sheet
      Pokemon against our active pair. Public information only: any of the unseen
      six could be there. The same for ours.
- [ ] **Speed (group F) becomes the real stat:** base plus stat points plus 20, then
      nature, stage, paralysis, Scarf and Tailwind, using the spread estimate.
- [ ] Tests first, plus a guard that only public information from earlier in the
      game is read.
- [ ] Real-data check per format: how often "knocks out this turn" was followed by a
      knock-out that turn.
- [ ] **Build time:** measured on one shard first. The full table must build on your
      computer in about two hours or less.

### Task 5 — v3 models and evaluation
- [ ] Same settings as v2 (learning rate 0.05, 31 leaves); rounds chosen on
      validation. Reg M-A on a 20% sample here and on the full set on your
      computer (runbook). Reg M-B uses the pooled model.
- [ ] Ablation: v2 (with real Speed) against v3 (adding G), as a paired difference
      per format. Gate on validation.
- [ ] The test split is opened for v3 only if the PO says so. It would be the
      fourth opening, logged.
- [ ] Expert claims re-scored:
      - **EC-001:** "the opposing pair has little damage potential" becomes
        measurable, as does the reserve's knock-out threat.
      - **EC-002:** a type advantage now shows through damage.

### Task 6 — Runbook and report

## Out of scope this week
- Damage over several turns (weather chip, Leech Seed, poison). The calculator does
  single hits.
- Redirection, Ally Switch and other changes of target. Features assume the attack
  lands where it is aimed.
- Using your own team's spreads in the live tracker. Your own games get this once
  there is a team file to read.

## Risks
- The common spread may be far from what players in the corpus actually ran. Task 3's
  measure says how far.
- Hit points in public logs are whole percentages, so close spreads cannot be told
  apart.
- Build time: millions of calculations, so the cache has to carry it.

## For the PO before starting
1. **Rating cutoff for the starting spreads:** 1500 (recommended; Smogon's standard
   weighting), 0 (everyone) or 1760 (top players only).
2. **Your team export:** not needed this week. It is needed when we analyse your
   own games.
3. **Still open from Week 6:** full Reg M-A training of v2 on your computer
   (runbook Section 15, step 7).
