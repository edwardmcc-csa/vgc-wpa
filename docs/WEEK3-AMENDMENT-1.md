# Week 3 — Amendment 1

**Issued:** mid-week, after Tasks 1 and 2 reported
**Adds:** Task 10, plus DEFINITIONS §14
**Execution order:** run Task 10 **after Task 7 and before Task 8.** Task 8 is the single re-parse and this amendment is schema-affecting. It must be merged and green before the parse runs.

This is the case rule 5 anticipated: a schema change raised before the re-parse rather than after. Nothing already committed is invalidated.

---

## Why this is arriving now

Open team sheets remove **composition** uncertainty. They do not remove **stat** uncertainty.

The sheets give species, item, ability, moves and Tera type. They do not give EVs, IVs or nature. So speed tier and effective physical and special bulk remain hidden in both open- and closed-sheet play — and those are the quantities that decide whether a line is correct. A player who knows the opposing Pokémon is faster plays a different turn from one who does not.

The WPA product attributes a decision to a win probability change. That is only meaningful against what the player could actually know at that moment. So the model needs to track what has been **revealed** about spreads, turn by turn, and revelation is observable in the log.

**We are capturing observations this week, not inferring from them.** The inference model is M4b. Bounds computation, speed-tier solving and spread fitting are all explicitly out of scope here. This task records the raw evidence in the parsed record so that M4b has it, and so that it is aligned to the same `(turn, decision index)` the rest of the schema uses.

**Why it can't wait for M4b.** It could, technically — the 601MB of raw logs is retained, so a later derivation pass costs about an hour rather than a re-scrape. Nothing is unrecoverable. The argument is cost and alignment: this week's parse is already budgeted, and a second one is not.

---

## Task 10 — Capture spread-revealing observations

Add an observation record to the parsed schema. Each observation attaches to the state at the `(turn, decision index)` where it occurred, using the same pair Task 5 tightened.

### What to capture

**Damage events.** For every damage instance: attacker, defender, move, and the damage as the log expresses it. Plus the modifier context known at that moment — weather, terrain, Tera state of both sides, screens, active stat boosts, whether the move hit multiple targets, and any item or ability already revealed.

**HP expression, flagged.** Record whether the HP figure is exact or a percentage, **per side, per event.** This is not cosmetic. Exact HP at level 50 with a known base stat pins the HP investment outright; a percentage turns the same event into an interval. If the flag is missing, every downstream constraint has to assume the weaker case.

**Move order.** At each decision point, who acted first, with move priority and every speed-relevant condition active — Tailwind, Trick Room, Icy Wind or equivalent drops, paralysis, Choice Scarf if already revealed. Order at equal priority is the primary speed-tier signal.

**Survival and faint events.** Whether a Pokémon survived or fainted, and at what HP figure. A survival at low HP is as informative as a KO.

**Recovery amounts.** Leftovers, Sitrus Berry and similar recover an exact fraction of max HP. Where the log gives an exact figure, that is a direct pin on the HP stat.

**Behavioural item and ability tells.** Choice lock observed, no status move used by a suspected Assault Vest holder, and any other item or ability that becomes evident through behaviour rather than through the sheet.

**Tera activation.** Species, type and turn. Task 2 established what coverage exists; whatever exists must be recorded.

### What NOT to do

- **No inference.** No stat bounds, no speed-tier solving, no spread fitting, no probability of any kind. Record what happened; that is all
- **No new representation.** Observations hang off the existing state record, not a parallel structure. Same rule that governed the live and replay paths
- **No upstream edits.** If capture appears to require changing VGC-Bench's own modules, stop and raise it

### Tests first, as always

- [ ] Every observation carries a `(turn, decision index)` that matches an existing state in the same trajectory
- [ ] Every observation identifies its actor and target unambiguously
- [ ] The HP-expression flag is populated on every observation that carries an HP figure — no defaults, no nulls
- [ ] Round-trip: observations survive the schema conversion both directions, unchanged
- [ ] Both paths produce the same observation schema: the replay corpus and a Week 2 fixture battle
- [ ] Observation counts are sane against a hand-checked fixture — pick two of the 20 golden battles and verify by eye

**Report back:** the observation schema, the counts per category across a sample, and the exact-versus-percentage breakdown. That last figure sizes M4b more than anything else in this task.

**Stop and report if** the HP expression turns out to be percentage-only on both sides throughout the corpus. That is a materially different M4b and a decision for the product owner, not something to work around.

---

## DEFINITIONS §14 — insert into `docs/DEFINITIONS.md`

Add the following as §14, and bump the revision line to `Revision 6 — adds §14 (spread revelation)`.

> ## 14. Spread revelation (added rev 6)
>
> Open team sheets reveal species, item, ability, moves and Tera type. They do **not** reveal EVs, IVs or nature. Speed tier and effective bulk are therefore hidden information in both open- and closed-sheet formats.
>
> These quantities determine correct play. A win probability that ignores them is not measuring the decision the player actually faced.
>
> **Rule: the parsed record must carry what has been revealed about spreads, at the decision point where it was revealed.** Revelation is monotonic within a set — evidence from game 1 remains available in game 3 (see §11.3) — and it never runs backwards. A model must not condition on information the player did not yet hold.
>
> **Observation, not inference.** The parsed record stores observable events: damage dealt with full modifier context, move order at known priority, survival and faint thresholds, exact recovery amounts, behavioural item tells, Tera activation. It does not store derived bounds, fitted spreads or probabilities. Derivation is M4b's responsibility and must be reproducible from the stored observations alone.
>
> **HP expression is part of the record.** Whether an HP figure is exact or a percentage must be stored per side and per event. Exact HP constrains a spread to a point; a percentage constrains it to an interval. Losing the distinction silently weakens every constraint built on top of it.
>
> This section defines what must be captured. It does not define how spreads are estimated.

---

## Consequence to note, not to act on

If the replay corpus carries no spread ground truth, there are no supervised targets for spread inference from replays alone.

The simulation harness built in Week 2 is the answer to that: battles run with spreads we specify are battles where the labels are known exactly. That reframes M2 from a validation tool into the training data generator for M4b, and it means the harness will need to run battles with **specified rather than random teams**.

That is week 4 or later work. Do not start it. It is recorded here so that M4b is sized with it in view.
