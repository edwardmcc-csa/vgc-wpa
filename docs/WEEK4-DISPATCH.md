# Week 4 — Dispatch Brief (M4 foundations: formats, splits, metrics, v0 baseline, timers)

**Status:** DRAFT for product owner review. Do not hand to the agent until Week 3 is closed out (re-parse signed off, Tasks 8 and 9 committed).
**For:** Claude Code, or a contract engineer working unsupervised
**Prerequisite:** Week 3 complete, CI green, `wpa_states/` populated by the single full re-parse
**Time budget:** 5 days
**Definition of done:** every checkbox ticked, `python -m pytest` green in CI, one report in prose

---

## Context

From this week modelling is allowed, in the narrow form below. The product measures a player's decisions against the win probability they could actually have known, so the foundations come first: how data is split, how it is scored, and a baseline any learned model must beat. A learned model comes next week, and it is only trustworthy if this week's split and metrics are right.

Two decisions from the product owner shape the week:

- **Reg M-A and Reg M-B are two formats** (`docs/DEFINITIONS.md` §15). Everything below is done per format. M-B has about 5% of the data (4,167 battles against 84,738), so its numbers must carry their sample size.
- **Splits are by set, never by trajectory** (§13), and inside each format.

Read `docs/DEFINITIONS.md` §1, §5, §11, §13, §15 before starting. They are the contract. The parsed records are in `wpa_states/`, one file per battle per player, described by `wpa/state.py` (`BattleState`).

This brief covers M4 only. **Do not start M3** (outcome distributions) or the specified-team simulation work.

---

## Task 1 — Format tagging

- [ ] A function mapping a battle tag to its format (`regma` or `regmb`), configuration-driven, not hardcoded in the model code
- [ ] Tests first: every file in `wpa_states/` maps to exactly one format; an unrecognised tag raises, it is never defaulted; a set never contains games from two formats

**Report back:** battles, sets and states per format and per file type (single game versus best-of-three).

## Task 2 — Leak-proof splits

- [ ] `wpa/splits.py`: assign each set (and each single game) to train, validation or test, deterministically from its identifier, inside each format
- [ ] Single games are their own unit; best-of-three sets stay whole
- [ ] **Exclude the 71 states with no set information.** They are one best-of-5 set (3 games, `gen9championsvgc2026regmabo3-2614987695`, `-2614990439`, `-2614996363`) that sits in the best-of-3 file. It is outside the format and 0.0037% of bo3 games. Drop any bo3-file state whose `set_id` is `None`, count what you drop, and report the count
- [ ] Tests first, before any splitting code:
  - no set ID appears in more than one split
  - both player perspectives of every game land on the same side
  - no exact team pairing appears in more than one split
  - the split is identical across two runs
  - each format has its own non-empty train, validation and test sets, or the function says plainly that it cannot (M-B is small)
- [ ] Split proportions are a parameter and are recorded with the output

**Stop and report if** any test can only pass by weakening it. A leaky split does not announce itself.

## Task 3 — Archetype hold-out, proposal only

`DEFINITIONS` §13 requires holding out whole team archetypes, and it must be available from day one. No archetype definition exists yet.

- [ ] Propose a concrete definition from the team sheets (for example, similarity of the six-species team) and implement it as an option on the splitter
- [ ] Report how many archetypes it produces per format, the size distribution, and how many sets fall in the largest ones
- [ ] Tests first: no archetype appears on both sides of the hold-out

**Do not use the archetype split for any headline number this week.** The product owner signs off the definition from your report first.

## Task 4 — Metric harness

Metrics are tests, with thresholds in CI. Implement them against the baseline in Task 5, before the baseline exists.

- [ ] Brier score; coin-flip reference of 0.25
- [ ] Calibration: bucketed predicted versus observed win rate, with a tolerance, reported with each bucket's sample count
- [ ] **No strict monotonicity test.** "Removing an opposing Pokémon never lowers your win probability" is false for real play: a weak active Pokémon can be worth more to leave alive than the stronger one that replaces it, and a timer such as Tailwind can make a knockout costly. The same holds for your own side (sacrificing a spent Pokémon can raise your odds). Say so in the test module's docstring so the test is not re-added
- [ ] **Trend, reported not gated:** mean predicted win probability by number of Pokémon remaining on each side, on the validation split, per format, with sample sizes. It should rise as the opposing count falls. This is a sanity trend over many states, never a pass or fail on one state
- [ ] **Expert-claim cases:** if `docs/EXPERT-CLAIMS.md` has labelled positions, report how the baseline scores each. Report only, do not gate
- [ ] **Symmetry:** a perfectly mirrored state returns 0.50
- [ ] **Terminal:** a won state returns 1.0, a lost state 0.0
- [ ] Every metric is computed per format. Pooled figures are secondary and labelled as pooled

## Task 5 — v0 heuristic baseline

Hand-written, no machine learning.

- [ ] Win probability from the fields the state already carries (hit-point fractions, Pokémon remaining), following `DEFINITIONS` §1 and §5
- [ ] It must be `WP_public`: use nothing the player did not yet know. **Check and document what `opp_pokemon` contains** (all six from the sheet, or only the revealed Pokémon) and confirm no unrevealed information leaks in
- [ ] Tests first: the Task 4 symmetry and terminal tests, written to fail on an empty implementation
- [ ] State plainly in the report that this baseline cannot represent timers or speed relationships, so it is expected to get the `docs/EXPERT-CLAIMS.md` cases wrong. That is the evidence for which state features the learned model needs
- [ ] Report Brier and calibration on the validation split, per format

**Do not add state fields.** Speed control and field conditions are not in `BattleState`, and a new field would force a second re-parse. List which of them the existing `observations` could supply without one, and raise any proposal as a question. Any schema change needs the product owner's approval.

## Task 7 — Timers: how long each effect lasts (investigate and design; no re-parse)

Product owner requirement (12 Oct 2026): the state must know how many turns remain on timed effects, because they drive different decisions (`docs/EXPERT-CLAIMS.md` EC-001). That means at least Tailwind, Light Screen, Reflect, Aurora Veil, Trick Room, Encore and Disable, plus weather and terrain, Taunt, Gravity, Wonder Room, Magic Room, Safeguard, Mist, Lucky Chant and delayed effects such as Future Sight and Perish Song. Today `Observation.side_conditions` stores names only, with no start turn or duration, and per-Pokémon effects such as Encore and Disable are not tracked.

Durations are not constants. In the pinned Showdown source (found 12 Oct, **verify**): Tailwind lasts 4 turns, 6 with the Persistent ability; Light Screen 5, or 8 with Light Clay; Trick Room 5, or 7 with Persistent; Encore 3, one longer if the target has already moved that turn; Disable 5, one shorter if the target has not yet moved. The Champions mod overrides Encore's start behaviour.

- [ ] **Generate, do not hand-write,** `docs/DURATIONS.md` from the pinned Showdown data for both format mods (`champions` and `championsregma`): every timed condition, its base duration, and every modifier (ability, item, ordering within the turn). Record the source file and line for each
- [ ] **Validate against the corpus.** For every start event in the logs that has a matching end event, the observed length matches the table, or the exception is explained (removed early, ended by a switch-out, extended by an item or ability). Report the mismatch rate per condition, per format
- [ ] **Leakage rule, with a test:** turns remaining at a decision point is computed from the start turn and the table, **never** from the end event, which is the future. End events are used only to validate the table
- [ ] **List which timers are hidden or random** (for example sleep and confusion lengths) and so cannot be known to the player. They are not features
- [ ] **Propose a `Timer` record** on `BattleState` (kind, side or target, name, start turn, scheduled end turn, what extended it) for both the live and replay paths, one schema. Check what poke-env exposes on the live path before proposing
- [ ] **Do not change the schema and do not re-parse.** A schema change costs one more re-parse (about 103 minutes) and should carry every feature the learned model needs. Report; the product owner decides

## Task 6 — Runbook update

- [ ] Extend `docs/RUNBOOK.md`: how to run the splitter and the metric report, written for a non-developer, same standard as before

---

## Rules of engagement

1. **Test first, always.** Failing test, then implementation. Show the failure.
2. **Additive only.** Everything in `wpa/` and `tests/`. Do not edit `vgc_bench/` or `pokemon-showdown/`.
3. **No learned model this week.** Baseline and measurement only. The gradient-boosted model is Week 5.
4. **No new state fields and no re-parse.** Raise it, do not do it.
5. **Per format, always.** No headline metric from pooled data.
6. **Do not touch `docs/vgc-wpa-engineering-plan.md`** or `docs/DEFINITIONS.md`. Propose changes in your report.
7. **Stop and ask** on: credentials or payment, anything needing an upstream patch, an archetype definition that cannot separate the data, or a split test that only passes if weakened.
8. **One commit per task.** Run tests with `python -m pytest`, not bare `pytest`.

## Carried-forward environment notes

- Python 3.14, top edge of VGC-Bench's supported range. On strange import or typing errors suspect this first and report it.
- `wpa_states/` is about 5.3GB across roughly 178,000 files. Stream it; do not load it whole.
- Battles are not deterministic and the 20-fixture corpus is not to be regenerated.
- `vgc_bench.eval` stays dead.

## Report format

Prose, not a status table. Cover: counts per format, the split guarantees and how each is tested, the archetype proposal with its numbers, the baseline's Brier and calibration per format with sample sizes, what `opp_pokemon` contains, and what the observations could supply. Flag anything surprising — the surprises sections have been the most useful part of every report so far.
