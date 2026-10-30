# Week 5 — Dispatch Brief (M4 v1: the first learned win probability model)

**Status:** DRAFT. Decisions 2 to 4 are made. Decision 1 (archetype rules) is a proposal the PO signs off from the Task 4b report; it does not block Tasks 1 to 4, and nothing uses archetypes in a headline until it is signed. Hand to the agent when the PO says go.
**For:** Claude Code, or a contract engineer working unsupervised
**Prerequisite:** Week 4 committed (formats, splits, metric harness, v0 baseline, timers) and `splits.json` produced
**Time budget:** 5 days
**Definition of done:** every checkbox ticked, `python -m pytest` green in CI, one report in prose

---

## Decisions and questions

1. **Archetype hold-out: play-style archetypes.** Your ten: Tailroom, Hard Trick Room, Hyper Offense, Balance, Protect the Queen, Perish Trap, Sun, Rain, Sand, Snow. Task 4b turns each into a rule over the open sheet (moves, abilities, items, types, base stats) and reports how many teams carry each tag, per format. **You sign off the rules from that report** before any number uses them. Teams carry **every tag they match** (Sun plus Trick Room is two tags), and some teams may match none.

2. **Library (DECIDED 29 Oct 2026: yes).** Gradient boosting needs a package the repo does not have. Proposal: scikit-learn's `HistGradientBoostingClassifier`, added as an optional extra (`pip install -e ".[model]"`), because it is the most likely to install on Python 3.14. LightGBM is faster but has a history of lagging new Python versions. The agent checks that the chosen one installs and reports before writing model code.
3. **Reg M-B model (DECIDED 29 Oct 2026: yes, secondary comparison allowed).** M-B has 3,366 training games. The headline is a model trained on M-B alone. May the agent also report a labelled *secondary* comparison, a model trained on M-A plus M-B with a format flag, scored on M-B only?
4. **Schema (DECIDED 27 Oct and confirmed 29 Oct 2026: no re-parse).** You decided on 27 Oct: timers live in a side file, no re-parse. This brief keeps to that. Week 5's report says whether anything the model wants *cannot* come from a side file. If nothing, there is never a second re-parse.

---

## Context

Week 4 built the yardstick: leak-proof splits by set inside each format, a metric harness, and a hand-written baseline (v0) that cannot see timers, speed or the team sheet. Its validation Brier is 0.2198 in Reg M-A and 0.2143 in Reg M-B (coin flip 0.25), and it is under-confident whenever a side is ahead. This week builds v1: a gradient-boosted model on the parsed states, label = this side won (`DEFINITIONS` §1, §5), per format (§15), judged by that same harness.

The week has a second job. Each family of features is added one at a time, so the report shows which ones earn their place. That is the evidence for what, if anything, still needs the state schema to change.

What exists, and what it lacks:

- `wpa_states/`: about 1.8M states in all, one file per battle per player, named `<tag>-<p1|p2>.json`. Each `BattleState` has species, HP fraction, fainted, active, a `gimmick` flag, turn, set score, and `observations`. It has **no** items, abilities, moves, timers or speed information.
- `timers.jsonl.gz` (`python -m wpa.timers --timers-out`): for each game and turn, the timed effects in force with turns left, and sleep/freeze/confusion attempts so far. Built from the logs with no future information. Targets are `p1`/`p2`, not "ours"/"theirs".
- The open team sheets are in the raw logs (`|showteam|`), not in the state.
- Splits: Reg M-A 67,508 / 8,694 / 8,532 games (train/validation/test); Reg M-B 3,366 / 366 / 435.

Read `DEFINITIONS` §1, §5, §13, §14, §15, `docs/OPP-POKEMON.md`, `docs/TIMERS.md`, `docs/OBSERVATIONS.md`. **Do not start M3, M4b or the specified-team simulation.**

---

## Task 1 — Audit what each state knows (before any feature is built)

The one sampled file the author opened suggests a state's `observations` can describe events that happen *after* the decision it sits beside: state (turn 1, decision 0) has none, state (turn 1, decision 1) carries turn 1's move order and damage. If so, using observations as features leaks the future, and the timing of timers joined to states is also in question. Settle this first.

- [ ] Write down, with a test on real fixture games, what a state at each `(turn, decision_index)` represents: before or after the turn's moves, team preview, lead selection, forced switches
- [ ] State which `observations` on each state were already public when that decision was made, and which describe what happens after
- [ ] Define, in one function with tests, the **decision point**: the states a model is asked to score, and the information allowed for each. If the rule drops states, report how many per format
- [ ] Check the `outcome` field: when it is non-null, is the game already decided? Confirm the v0 baseline's "undecided states" filter agrees

**Stop and report if** the observations on states are future information. The features below then use only what the audit allows.

## Task 2 — Dependency and environment

- [ ] Install the library chosen above on the PO's Python 3.14 and report the version and whether it works. If it does not install, stop and ask
- [ ] Add it as an optional extra in `pyproject.toml` and to CI, pinned; the existing lint and version-drift checks must stay green
- [ ] Training must be deterministic given a seed. Test: two runs on a small fixture give identical predictions

## Task 3 — Join the timers to the states

- [ ] A function `(tag, role, turn, decision_index) -> timers` reading `timers.jsonl.gz`, mapping `p1`/`p2` to ours/theirs by role, using the decision-point rule from Task 1
- [ ] Tests first: a game with Tailwind started on a known turn gives the right turns left at each state, on both players' perspectives; a state with no timer gets an empty result, never a missing-data error
- [ ] **Cross-check against an independent source:** where a state's `observations.side_conditions` lists a condition, the join should show a timer for it. Report the disagreement rate per effect and per format
- [ ] **No end-event information.** A test builds the join for a game, truncates the game after state k, and shows the result for states up to k is identical

## Task 4 — Team-sheet side file

- [ ] From the logs, one record per game and side: for each of the six Pokémon in sheet order, item, ability and four moves. Generated, not hand-written; keyed by tag. No schema change
- [ ] Derive per-side features from it, each defined in code with a test: sheet position of each Pokémon, whether the team has Tailwind, Trick Room, weather setters, redirection, Fake Out, priority moves, Intimidate, screens. Alive-and-not-yet-seen versus seen is computed from the state
- [ ] **Public information only** (`WP_public`). Show with a test that nothing depends on which four Pokémon were brought, other than what the state already reveals
- [ ] List any feature you wanted that the sheet cannot give (speed stats, EVs) and leave it out

## Task 4b — Play-style archetypes, proposal only

The PO's categories, as rules over the six-Pokémon sheet. Below is the first reading of each; the PO corrects the rules from the report. Base stats, types and move data come from the pinned Showdown data, never from memory. A team carries every tag whose rule it meets.

- **Perish Trap:** Perish Song plus a trapper (Shadow Tag, Arena Trap, Mean Look, Block, Spider Web)
- **Hard Trick Room:** two or more Trick Room users and a low average base Speed
- **Tailroom:** Tailwind and Trick Room both on the team
- **Protect the Queen:** a redirector (Follow Me, Rage Powder) plus a setup attacker (Swords Dance, Dragon Dance, Nasty Plot, Calm Mind and similar)
- **Sun, Rain, Sand, Snow:** a setter of that weather, by ability or move. Snow is expected to be uncommon
- **Hyper Offense** (the PO's numbers): fast, frail, hard-hitting, built for a short game and a quick win or loss, low on disruption. A team qualifies when it meets all of:
  - **Attack:** its primary damage dealers have a base attacking stat of 110 or more, in whichever stat they use (Attack for a mostly physical move set, Special Attack for a mostly special one, worked out from the four moves)
  - **Speed:** those damage dealers have base Speed of 100 or more, or 80 or more when the team has a **priority Tailwind** user (Prankster or Gale Wings, such as Whimsicott)
  - **Spread damage:** heavy damaging spread moves on the team (Heat Wave on Mega Charizard Y, Hyper Voice, Rock Slide, Make It Rain and the like); the agent lists the spread moves it counts
  - **Choice items** on damage dealers (Choice Specs, Band, Scarf) count in its favour
  - **Little defensive investment.** EVs are never on the sheet, so this is read from what is: low base bulk (HP, Defense, Special Defense) and no defensive items (Assault Vest, Eviolite and the like). The report says plainly that this is a proxy
  - **Low disruption:** few of Fake Out, Taunt, Encore, status moves, redirection, trapping. Tailwind itself does not count against it
  - "Primary damage dealers" needs an exact definition (for example, the Pokémon with a 110+ attacking stat); the agent proposes one and the PO corrects it
- **Balance:** a mix of offensive and defensive Pokémon, some heavy hitters, some disrupters. Measured as: a Fire-Water-Grass type core or a Steel-Fairy-Fighting type core, and/or Intimidate cycling, and/or several pivot moves (U-turn, Volt Switch, Flip Turn, Parting Shot, Teleport, Baton Pass, Chilly Reception, Shed Tail)

Balance is a judgement call, so its cut-offs are not guessed here: the agent reports the distributions behind each measure (type cores, Intimidate users, pivot moves) and proposes cut-offs for the PO to move. Hyper Offense uses the PO's numbers above; the agent reports how many teams meet each condition on its own, so the PO can see which one does the work.

- [ ] A tagger from the sheet to a set of tags, each rule in code with a test on a hand-built team that must match and one that must not
- [ ] Report per format: teams and sets per tag; how many carry two or more tags and which pairs are common; how many carry none; the distribution behind each Hyper Offense and Balance measure
- [ ] **Hold-out rule with overlapping tags:** setting a tag aside removes every team that carries it from train and validation, so the model never trains on any team with that tag. Tests first: no team with a held-out tag in train or validation. Report how much data each hold-out removes, because a common pairing makes it larger than the tag alone
- [ ] Say which tags are too small in Reg M-B to hold out
- [ ] **Not used in any headline number** until the PO signs off the rules

## Task 5 — Feature table

One compact table per format and split, built by streaming `wpa_states/`, stored under a gitignored folder.

- [ ] Feature groups, each switchable, in this order: **A** state only (HP fractions, Pokémon remaining, who is active, turn, game index, set score); **B** field presence from the state's observations, if Task 1 allows; **C** timers (turns left, and for random-length effects turns elapsed and the table's chance of ending next turn); **D** sheet features (Task 4); **E** sheet position of unseen Pokémon (`docs/OPP-POKEMON.md`)
- [ ] An explicit allow-list of source fields, enforced by a guard test like the v0 baseline's. `outcome` is the label and never a feature. `gimmick` is excluded unless the PO approves (it mislabels unrevealed holders of mega stones; see `docs/OPP-POKEMON.md`)
- [ ] Each row carries its tag, role, set/unit ID and split, so evaluation can group by unit
- [ ] **Prefix invariance test:** features for states up to k are identical whether the game is built whole or cut after k
- [ ] Two perspectives of one game are two rows and never split apart (the splitter already guarantees this; test it on the table)

## Task 6 — v1 model

- [ ] One model per format, trained on that format's train split only. Early stopping on the validation split, not on test. Fixed seed, small fixed hyperparameter grid chosen on validation; the grid is written down before looking at results
- [ ] **Symmetry by construction:** predict from both perspectives and average, `p = (f(x) + 1 - f(mirror(x))) / 2`, so a mirrored state returns exactly 0.50 and the two players' predictions sum to 1. Tests first, using the harness's symmetry, complement and terminal checks
- [ ] If calibration is off after training, fit a monotone recalibration on the validation split only, and say so in the report
- [ ] Save the model and the exact feature list together. A loader that finds a mismatch refuses to predict

## Task 7 — Evaluation and ablation

- [ ] Reuse `wpa.metrics`. Report per format, on undecided states (as v0): Brier, skill, calibration bins with counts, and the trend by Pokémon remaining
- [ ] **Ablation table:** v0, then A, A+B, A+B+C, A+B+C+D, A+B+C+D+E, on the validation split. Brier with a **confidence interval from resampling whole units** (sets and single games), not states, since states within a game are not independent. M-B intervals will be wide; print the game count next to every number
- [ ] A gate script (`python -m wpa.model --check`) that exits non-zero if v1 does not beat v0 and 0.25 on validation in either format, or if any calibration bin with 100 or more states is outside the tolerance. Unit tests for the gate itself run on a tiny synthetic fixture, so CI never needs the real data
- [ ] **The test split is opened once**, at the end, by one command that records the date and git commit in its output. It is for the final reported number and is never used to choose anything. If it is opened a second time, say so in the report
- [ ] Play-style archetype hold-out (Task 4b): reported as a secondary number only if the PO signed off the rules; labelled as such
- [ ] If Question 3 was approved, report the pooled-with-format-flag model on M-B only, labelled secondary

## Task 8 — Expert claims, report only

- [ ] For EC-001 and EC-002 (`docs/EXPERT-CLAIMS.md`), build the labelled positions from real states plus the Task 3 timers, and report v0 and v1's win probability for each. Do not gate. If a position needs information the features cannot carry (relative speed, reserve damage potential), say which, because that is the evidence for what the next feature round needs

## Task 9 — Runbook

- [ ] Extend `docs/RUNBOOK.md`: install the extra, build the side files and feature tables, train, run the ablation, run the gate, open the test split. Non-developer standard, with the expected output of each command

---

## Rules of engagement

1. **Test first, always.** Failing test, then implementation. Show the failure.
2. **Additive only.** `wpa/`, `tests/`, `scripts/`, `docs/` new files, plus the `pyproject.toml` extra and the CI line for Task 2. Do not edit `vgc_bench/` or `pokemon-showdown/`.
3. **No new state fields and no re-parse.** Raise it, do not do it.
4. **Per format, always.** No headline from pooled data.
5. **No tuning on the test split.** Validation chooses everything.
6. **Do not touch `docs/vgc-wpa-engineering-plan.md` or `docs/DEFINITIONS.md`.** Propose changes in the report.
7. **No monotonicity law.** `docs/EXPERT-CLAIMS.md` shows it is false in real play. Trends are reported, never gated per state.
8. **Stop and ask** on: credentials or payment, a library that will not install, anything needing an upstream patch, observations that turn out to be future information (Task 1), or a test that only passes if weakened.
9. **One commit per task.** Run tests with `python -m pytest`, not bare `pytest`.

## Carried-forward environment notes

- Python 3.14, top edge of VGC-Bench's supported range. On strange import or typing errors suspect this first and report it.
- `wpa_states/` is about 5.3GB across roughly 178,000 files. Stream it; do not load it whole.
- The cloud workspace cannot run the project's ML dependencies; model training and the real-data runs happen on the PO's PC. Code written in the workspace is tested there on small fixtures.
- Side files and feature tables are generated, gitignored, and never committed.
- Battles are not deterministic and the 20-fixture corpus is not to be regenerated. `vgc_bench.eval` stays dead.

## Report format

Prose, not a status table. Cover: what each state represents and what leaks (Task 1); the join's cross-check rates; the ablation with intervals, per format, and which feature groups earned their place; v1 against v0 on validation, and the single test-split result; calibration before and after any recalibration; the expert-claim positions; and a plain answer to "is there anything the model needs that a side file cannot give", which settles the re-parse question. Flag anything surprising; the surprises sections have been the most useful part of every report so far.
