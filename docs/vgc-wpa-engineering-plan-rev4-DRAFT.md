# VGC Win Probability + WPA — Engineering Plan

*Revision 4 DRAFT, agent-oriented rewrite of revision 3. Proposed, not adopted: the product owner reviews it and decides whether it replaces `vgc-wpa-engineering-plan.md`. Nothing in the original file was changed.*

---

## 0. How to use this document

This plan is read by an autonomous coding agent working one milestone at a time, and by the product owner (PO) who signs off. It is organised so an agent can find, for the milestone it is on: what is already true, what to read, what to build, what proves it done, and when to stop.

- **Contract documents win over this plan.** `docs/DEFINITIONS.md` is the signed-off contract for what WP, WPA, luck and decision mean. If this plan and DEFINITIONS disagree, stop and raise it.
- **Weekly dispatch briefs win over this plan** for the week they cover (`docs/WEEKn-DISPATCH.md`, plus any `WEEKn-AMENDMENT-n.md`).
- **One milestone at a time.** Do not start work on a later milestone because it looks easy.
- **Findings override assumptions.** Several earlier assumptions were wrong (§2). Check the status ledger before relying on anything in the milestone text.

### Standing rules (apply to every milestone)

1. **Failing test first, every time.** Write the test, run it, show it failing, then implement. Do not write the implementation and the test together.
2. **Additive only.** Our code lives in `wpa/` and `tests/`. Do not edit `vgc_bench/` or `pokemon-showdown/`. If a task seems to need an upstream edit, stop and report.
3. **One commit per task**, with the task number in the message. Never commit with failing tests.
4. **Run tests with `python -m pytest`**, not bare `pytest` (it is not on the PATH on the PO's Windows machine).
5. **No modelling before M4.** No win probability, evaluation function or "who is ahead" heuristics earlier.
6. **Do not edit `docs/vgc-wpa-engineering-plan.md`** unless the PO says so; they may have it open.
7. **Stop and ask** on: licence questions, credentials or payment, a parse failure rate above 5%, more than 2% of games not assignable to a set, anything needing an upstream patch, or a finding that changes a milestone's scope.
8. **Report in prose, not a status table.** Always include a "surprises" section; it has been the most useful part of every report so far.
9. **Instructions for the PO are plain CLI steps for a non-developer**, copy-pasteable, one command per line (Windows / PowerShell).

---

## 1. Scoping decision: adopt the commodity, build the product

Do not build a battle engine or replay ingestion. Build the analytics layer: a win probability model and a per-decision WPA attribution that says *which choice cost the game and which loss was variance*.

| Layer | Decision | Why |
|---|---|---|
| Battle rules engine | Adopt: Pokémon Showdown, pinned submodule, run locally | Ground truth, MIT |
| Replay scrape and parse | Adopt: VGC-Bench fork | Handles open team sheets |
| Python battle interface | Adopt: poke-env (VGC-Bench's pinned branch) | Doubles support |
| Outcome enumeration | Adapt: poke-engine pattern (§5) | Needs the damage-roll change |
| **Win probability model** | **Build** | The product |
| **WPA attribution** | **Build** | The product |
| Bot | Adopt and tune | Data generator, not the goal |

Definitions of WP, WPA, and the decision/luck split are in `docs/DEFINITIONS.md` §1–§3. Headline test: **Decision WPA + Luck WPA = total turn delta, every turn.**

---

## 2. Status ledger and findings that changed the plan

*Last updated from the repository's git log. Update this section at the end of every milestone.*

| Milestone | Status |
|---|---|
| M0 Repo skeleton | Done (Week 1) |
| M1 Adopt VGC-Bench pipeline | Done (Week 1) |
| M2 Simulation harness | Done (Week 2: live battles, 100-battle volume test, determinism study, round-trip, 20 golden fixtures, runbook) |
| M1b Set reconstruction | Schema and extraction done (Week 3 Tasks 1–7, 10 committed). **Re-parse (Task 8) not yet complete.** Runbook section (Task 9) drafted, not committed |
| M3 Outcome distributions | Not started |
| M4 Win probability model | Brief drafted: `docs/WEEK4-DISPATCH.md` (format tagging, splits, metrics, v0 baseline). v1 follows in Week 5 |
| M4b Bring-four and spread model | Not started |
| M5–M7 | Not started |
| M8 Team-building layer | Proposed only: what-if analysis of natures, moves, EVs and Pokémon changes. Needs the specified-team harness, M4 and M6. Scope before committing |

### Findings that overrode earlier assumptions

| Earlier assumption | What was found | Where |
|---|---|---|
| Same seed gives the same battle (M2 test) | **False.** The pinned Showdown does not expose seed control to a connecting client. The 20-fixture corpus is the reproducibility mechanism; do not regenerate it casually | `docs/DETERMINISM.md` |
| Terastallisation is a hidden-information item (M4b) | **Tera is disabled in the format.** Zero Tera events in 88,905 of 88,905 corpus battles, and the simulation uses the same format. Mega Evolution is the gimmick that works | `docs/TERA-COVERAGE.md` |
| Nature is hidden on the sheet | **Depends on the regulation**: shown in all Reg M-B sheets, in none of Reg M-A. EVs, IVs, Tera type are never shown | `docs/SHEET-FIELDS.md` |
| Open sheets remove most hidden information | They remove **composition** uncertainty only. Speed tier and bulk (EVs, IVs, nature) stay hidden, and they decide whether a line is correct | `DEFINITIONS` §14 |
| Upstream parser is adequate | It is game-scoped and discards best-of-three structure; fixed in M1b | `DEFINITIONS` §11 |
| Parsed output is small | 601MB of logs expands to roughly 49GB in VGC-Bench's format (about 80×). Parse output is a build artifact | `docs/DATA-FOOTPRINT.md` |
| `open-spiel` can be installed | Removed. `vgc_bench.eval` stays dead by decision | `docs/RUNBOOK.md` |

### Decisions taken by the PO (12 Oct 2026)

- **Reg M-A and Reg M-B are two formats** (`DEFINITIONS` §15, rev 7). Models, calibration and evaluation are per format; splits are made inside each format. M-B has roughly 5% of the data (4,167 battles against 84,738), so M-B results must state their sample size.
- **No licence issues** with any dependency or dataset in use.
- **Execution order:** close out Week 3, then M3 and M4 in parallel where one engineer allows it, then the specified-team harness, M4b, M5, M7, then scope the team-building layer (M8).

### Still open

- **M4b size.** Not re-baselined. The Task 10 finding (`docs/OBSERVATIONS.md`) is that HP is **percentage-only** in all 88,905 corpus battles, so every damage observation is an interval, not a point. Exact-HP pins are available only from the specified-team simulation harness. This is a larger effect on M4b than the open sheets removing the composition problem.
- **Archetype definition** for the M4 hold-out (`DEFINITIONS` §13). Week 4 proposes one; the PO signs it off.
- **Team-building layer (M8).** Proposed, not scoped or approved.

---

## 3. Milestones

Each milestone uses the same shape. "Read first" lists what an agent must open before starting.

### M0 — Repo skeleton — DONE
CI runs `python -m pytest` on every push. Version-drift check pins the fork, Showdown and poke-env.

### M1 — Adopt the VGC-Bench pipeline — DONE
Fork, scraper, parser, adapter into `wpa/state.py`, so we are not coupled to their format.

### M1b — Set reconstruction and schema finalisation — IN PROGRESS
- **Goal:** every parsed state carries its set, game index, set score entering the game, and the spread-revealing observations, so the one expensive full re-parse happens once.
- **Read first:** `DEFINITIONS` §11–§14, `docs/WEEK3-DISPATCH.md`, `docs/WEEK3-AMENDMENT-1.md`, `docs/DATA-FOOTPRINT.md`.
- **Remaining:** Task 8 (run `python -m wpa.reparse --num_workers 4`, about an hour, PO runs it on their machine), Task 9 (runbook, drafted).
- **Done when:** failure count is still 6 known failures and nothing new; set fields are populated throughout the full output, not a sample; tests green in CI.
- **Do not:** start a second re-parse; any further schema change must be raised before Task 8 completes.

### M2 — Simulation harness — DONE; scope extended
- **Done:** live battles through poke-env, round-trip through our schema, volume test, 20 golden fixtures.
- **New requirement (not started, week 4 or later):** run battles with **specified rather than random teams**. Battles with known spreads are the only source of exact spread labels, so the harness becomes the training-data generator for M4b rather than only a validation tool.

### M3 — Outcome distributions — NOT STARTED
- **Goal:** for a board and a pair of chosen actions, enumerate what can happen and with what probability, keeping the **full damage distribution** (§5).
- **Read first:** §5 of this plan, `DEFINITIONS` §7–§8.
- **Tests:** golden cases hand-checked against a public damage calculator (a known KO range, a 50/50 range, an accuracy check, a crit branch); probabilities in each enumeration sum to 1.0 within tolerance; two different non-fainting damage rolls produce two different states, never one averaged state.
- **Constraints the agent has not yet been briefed on:** this milestone has design constraints; wait for its dispatch brief rather than inferring them from this summary.
- **Highest-risk milestone.** Estimate: 2–3 weeks. Golden fixture corpus has **no Terastallisation coverage by design**; Mega Evolution is covered by format.

### M4 — Win probability model — NOT STARTED
- **Prerequisites:** M1b complete (the set-level split rule exists because of it).
- **Per format (`DEFINITIONS` §15):** Reg M-A and Reg M-B are fitted, calibrated and reported separately; splits are made inside each format.
- **v0:** hand-written heuristic baseline (HP fractions, Pokémon remaining, speed control, field).
- **v1:** gradient-boosted model on parsed states, label = this side won.
- **Split rule (non-negotiable, `DEFINITIONS` §13):** split by **set**, never by trajectory, game or player; additionally hold out whole team archetypes. Tests: no set ID in more than one split; no exact team pairing in more than one split.
- **Metric tests (set thresholds in CI, fail on regression):** Brier beats 0.25 and beats v0; calibration by bucket within tolerance; monotonicity (removing an opposing Pokémon never lowers your WP); symmetry (mirrored state returns 0.50); terminal (won battle returns 1.0).
- Estimate: 3–4 weeks.

### M4b — Bring-four and spread model — NOT STARTED
- **Hidden after open sheets:** which four of six are brought, and the **spread** (EVs, IVs; nature in Reg M-A). Tera is not a factor in this format.
- **Input:** the observation records captured in M1b (damage with modifier context, move order, survival thresholds, exact recoveries, behavioural tells), derived reproducibly from stored observations alone. HP expression (exact versus percentage) is stored per side per event and sizes this milestone.
- **Tests:** bring-four prediction beats a uniform-over-fifteen baseline; observed move order at equal priority narrows the speed range; observed damage narrows the defensive spread; prior-game information narrows the belief set relative to a game-1 state (`DEFINITIONS` §11.3); the inference never conditions on information the player did not yet hold (§14).
- **Non-negotiable from day one:** the pipeline runs end to end with all opposing sheet fields blanked, producing a valid but less confident `WP_public`. Sheet knowledge is evidence, never a required field.
- **Labels:** spread ground truth comes from the specified-team simulation harness (M2 extension), because the replay corpus carries none.
- Estimate: not re-baselined (see §2 open questions).

### M5 — WPA attribution — NOT STARTED
- Split each turn's delta into decision and luck (`DEFINITIONS` §3–§8).
- **Tests:** conservation on every turn of every replay; scripted turn where only a crit varies gives luck captures it and decision ≈ 0; scripted obviously losing switch gives decision strongly negative.
- Estimate: 2 weeks.

### M6 — Bot (optional) — NOT STARTED
Adopt a VGC-Bench checkpoint; its job is clean self-play data and stress-testing the WP model. Tests: beats random ≥ 90% over 200 battles; beats "always strongest move" > 55%. Estimate: 3–4 weeks.

### M7 — The deliverable — NOT STARTED
CLI: paste a replay URL, get a ranked table of the biggest win-probability swings, each tagged decision or luck. Tests: end-to-end on 5 fixture replays with expected top-3 swings. Reporting threshold 0.5pp, with the variance measurement from `DEFINITIONS` §10 completed before this ships. Estimate: 1 week.

**Schedule:** the rev 3 total (4.5–5.5 months for one strong engineer) predates the spread finding and is not re-baselined. M3 remains the schedule risk.

---

## 4. The damage roll trap (read before M3)

Every move has 16 equally likely damage rolls plus roughly a 5% crit chance, up to 32 distinct values per move. poke-engine groups rolls by whether they cause a faint and averages within each group. That is right for a bot choosing a move and **wrong for measurement**: a high roll leaving the target at 2 HP versus a low roll leaving it at 40 HP is exactly the luck the product sells, and averaging erases it.

- Keep the full distribution in the WPA path.
- If a grouped version exists for search, keep it as a **separate code path** with a test asserting the two disagree in the expected direction. Never let one silently become the other.

---

## 5. Appendix A — Environment facts an agent needs

- Python 3.14 (top edge of VGC-Bench's supported range). On strange import or typing errors, suspect this first and report it; do not work around it silently.
- Windows / PowerShell. Local Showdown server: `cd pokemon-showdown` then `node pokemon-showdown start --no-security`, leave it running, work in a second window.
- Repeated live-battle runs in one terminal can hang (Week 2 Task 4 finding). Restart the terminal between runs.
- Do not fix the parser's memory ceiling. Parse output is a build artifact; the batching workaround is in `docs/RUNBOOK.md`.
- Do not change the battle format string or regenerate the golden fixtures.
- Runbook (`docs/RUNBOOK.md`) is the PO-facing source for every command.

## 6. Appendix B — Public resources and licences

| Resource | Note |
|---|---|
| `cameronangliss/vgc-bench` | MIT. The fork's origin |
| `cameronangliss/vgc-battle-logs` (HF) | Pre-scraped open-sheet logs; saves scraping |
| `cameronangliss/vgc-bench-models` (HF) | Pre-trained checkpoints; skip training at first |
| `smogon/pokemon-showdown` | Use the pinned submodule, never a fresh clone |
| `hsahovic/poke-env` | Pinned branch; a stale copy is the usual cause of breakage |
| `pmariglia/foul-play` + `poke-engine` | Architecture template (MCTS, instruction generation, set prediction). Read before M3 and M4b |
| `pkmn/engine` | Fast Zig engine, pre-1.0; check status before depending on it |
| Metamon parsed replays (HF) | **Non-commercial licence. Check before any commercial use** |
| Showdown replay API | Paginated; respect rate limits |
| arXiv 2506.10326 (VGC-Bench), 2608.29197 (PokaiTrainer) | Benchmark paper; recent belief-state search for VGC |

Licence discipline: MIT code is safe with attribution; non-commercial datasets are not.

## 7. Appendix C — Product owner's backlog and risks

**Expert claims into tests (PO's job).** Sources: WolfeyVGC, CybertronVGC, James Baek, vgcguide.com. Each entry is a claim plus a labelled test position and assertion, for example "never lead a Trick Room setter into a faster Taunt user" becomes WP(lead A) < WP(lead B) by a margin. Target 50–100 entries; 20 before M4 starts. They become v0 features, a regression suite, and the demo.

**Risks to watch:**
1. Scope creep into engine building.
2. Format lock-in: the model must function with blanked sheet fields (M4b).
3. Generalisation: hold out whole archetypes or the evaluation is a lie.
4. Format churn: regulations rotate; "currently legal" is config data, never hardcoded. Reg M-A and M-B already differ on visible nature.
5. Calibration over accuracy.
6. Doubles combinatorics: anything that works in singles may be 100× too slow.
7. Dependency drift among the fork, Showdown submodule and poke-env; keep version checks in CI.
8. Set structure silently lost: without M1b every game 2 and 3 trains as a fresh matchup.
9. Leaky splits: a split by trajectory gives excellent-looking calibration that means nothing.
