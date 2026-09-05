# Week 1 — Dispatch Brief

**For:** Claude Code, or a contract engineer working unsupervised
**Owner:** product owner (non-developer) — report back in writing, no live debugging sessions
**Time budget:** 3 days
**Definition of done:** every checkbox below is ticked and `pytest` is green in GitHub Actions

---

## Context in one paragraph

We are building a win probability model and a per-decision "WPA" attribution for Pokémon VGC doubles — a tool that tells a player which choice cost them the game and which loss was just variance. We are not building a battle engine. We are forking `cameronangliss/vgc-bench` (MIT) and adopting its replay scraper and parser. Week 1 is setup and proving the data pipeline runs end to end. No modelling.

---

## Task 1 — Fork and stand up the environment

- [ ] Fork `cameronangliss/vgc-bench` to our org as `vgc-wpa`, clone it
- [ ] Initialise submodules — the pinned `pokemon-showdown` version is required, do not clone Showdown separately
- [ ] `npm i` inside `pokemon-showdown`, confirm the server starts with `--no-security` and listens on 8000
- [ ] `pip install .[dev]` — if `open-spiel` blocks the install, remove it from `pyproject.toml` and note that you did
- [ ] Record the exact versions of the fork commit, the Showdown submodule commit, and poke-env in `docs/PINNED-VERSIONS.md`

**Report back:** the three pinned versions, and anything you had to remove or patch.

## Task 2 — Prove the data pipeline

- [ ] Download the pre-scraped log dataset `cameronangliss/vgc-battle-logs` from Hugging Face into `battle_logs/`
- [ ] Run their `logs2trajs.py` parser over it with parallelisation on
- [ ] Confirm parsed trajectories come out the other side

**Report back:** how many battles parsed, how many failed and why, wall-clock time, disk used. If more than 5% fail, stop and report rather than working around it.

## Task 3 — Our own scaffolding

Create `wpa/` as a new top-level package alongside their code. Do not edit their modules; we want to pull upstream fixes cleanly.

- [ ] `wpa/state.py` — our own state schema, plus an adapter to and from their trajectory format
- [ ] `tests/test_adapter.py` — round-trip test: their format → ours → theirs, unchanged
- [ ] `tests/test_invariants.py` — property tests over parsed battles: HP never negative, turn numbers strictly increase, no fainted Pokémon takes an action, exactly one battle outcome recorded

**Write the tests first and show them failing before the adapter exists.** Include the failing output in your report.

## Task 4 — CI

- [ ] GitHub Actions workflow running `pytest` on every push to `main` and every PR
- [ ] Include a version-drift check that fails loudly if the Showdown submodule or poke-env pin moves unexpectedly
- [ ] Green check visible on the repo

## Task 5 — Handover doc

- [ ] `docs/RUNBOOK.md`: how to start the server, run the parser, run the tests — written for someone who has never seen the repo. Assume the reader is not a developer.

---

## Rules of engagement

1. **Test first, always.** Failing test, then implementation. If you find yourself writing implementation first, stop.
2. **Do not touch VGC-Bench's own modules.** Additive only, in `wpa/`.
3. **Do not start modelling.** No win probability work this week, however tempting. Wrong order.
4. **Stop and ask rather than improvise** on: licence questions, anything requiring a paid account, anything requiring credentials beyond the GitHub token, or a >5% parse failure rate.
5. **One commit per task**, message describing what changed and why.

## Report format

Reply with: what's done, what's blocked, the three pinned versions, the parse statistics, and a link to the green CI run. Prose, not a status table. Flag anything that surprised you — surprises this early are usually the important signal.
