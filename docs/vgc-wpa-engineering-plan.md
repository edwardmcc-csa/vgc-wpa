# VGC Battle Sim + Win Probability Added (WPA)
### Engineering plan for a product owner — TDD, milestone by milestone
*Revision 2 — updated after reading the VGC-Bench README and the Foul Play write-up*

---

## 1. The single most important scoping decision

**Do not build a Pokémon battle engine from scratch.** A frame-accurate engine is 2+ years of work and several people have already done it under MIT licenses. That work is a commodity. Your product is the **analytics layer on top**: a win probability model and a per-decision WPA attribution that tells a player *which choice cost them the game, and which loss was just bad luck*. Nobody has shipped that well for VGC doubles.

**Revision 2 goes further: don't build the replay ingestion either.** VGC-Bench already ships a scraper that pulls the Showdown replay database and filters for open-team-sheet battles, plus a parser that converts those logs into state-action transitions with Elo and winner filters. Fork it. That removes most of a milestone.

| Layer | Decision | Why |
|---|---|---|
| Battle rules engine | **Adopt** (Pokémon Showdown, pinned version, run locally) | Ground truth, MIT licensed |
| Replay scrape + parse | **Adopt** (VGC-Bench `scrape_logs.py` + `logs2trajs.py`) | Already handles open team sheets |
| Python battle interface | **Adopt** (poke-env) | VGC doubles support contributed by the VGC-Bench team |
| Outcome enumeration | **Adapt** (poke-engine pattern, see §5) | Needs modification — see the damage-roll trap |
| **Win probability model** | **BUILD** | This is the product |
| **WPA attribution** | **BUILD** | This is the product |
| Bot | **Adopt + tune** | Data generator, not the goal |

---

## 2. What "WPA" means here (define this before any code)

Borrowed from baseball. Two definitions your engineers must agree on in writing:

- **WP(state)** = probability the player to move eventually wins, given everything publicly known at that moment. A single number, 0 to 1.
- **WPA(decision)** = WP *after* the turn resolves minus WP *before*.

The interesting part is splitting that delta into two buckets:

- **Decision WPA** = WP of the choice you made, in expectation over all dice rolls, minus WP of the best choice available. (Did you pick the right move?)
- **Luck WPA** = what actually happened minus what was expected to happen. (Crit, freeze, 15% miss, low damage roll.)

**Conservation rule:** Decision WPA + Luck WPA must sum to the total turn delta, every turn. That is your headline unit test and it will catch most modelling bugs.

---

## 3. Milestones with test-first acceptance criteria

Each milestone: write the failing test first, then the code, then refactor. A milestone is not "done" until its tests are green in CI on a fresh machine.

### M0 — Repo skeleton (1–2 days)
Empty project, one trivial test, CI running on every push.
**Done when:** `pytest` passes locally and the green check appears on GitHub.

### M1 — Adopt the VGC-Bench pipeline (2–3 days, was 1 week)
Fork VGC-Bench, get their scraper and parser running, produce your own corpus of parsed VGC battles. Add a thin adapter into your own state schema so you are not permanently coupled to theirs.
**Tests:** 500 replays parse without error; your adapter round-trips their trajectory format without loss; property tests (HP never negative, turn numbers increase, no fainted Pokémon acts).

### M2 — Simulation harness (1 week)
Play battles programmatically against a local Showdown server via poke-env.
**Tests:** 100 random-vs-random VGC battles complete with no crashes; same seed → same result; battle state round-trips through your schema unchanged.

### M3 — Outcome distributions (2–3 weeks, was 1–2)
For a given board and a given pair of chosen actions, enumerate what can happen and with what probability.
**Design constraint added in rev 2: keep the full damage distribution.** See §5 for why, and why this milestone got longer.
**Tests:** golden cases hand-checked against the public damage calculator — a known KO range, a 50/50 range, an accuracy check, a crit branch. Probabilities in each enumeration must sum to 1.0 within tolerance. Explicit test that two different non-fainting damage rolls produce two different states, not one averaged one.
**Highest-risk milestone.** Budget generously.

### M4 — Win probability model (3–4 weeks)
- **v0 heuristic baseline:** HP fractions, Pokémon remaining, speed control up, field conditions. Hand-written, no ML.
- **v1 learned:** gradient-boosted model trained on parsed replay states, label = did this side win.

**Tests are metrics, not asserts.** Set thresholds in CI and fail the build if they regress:
- Brier score beats the 0.25 coin-flip baseline, and beats v0
- Calibration: of all states rated 70%, roughly 70% are won (bucketed, with tolerance)
- **Monotonicity:** removing an opponent's Pokémon must never lower your WP
- **Symmetry:** a perfectly mirrored state returns 0.50
- **Terminal:** a won battle returns 1.0
- **Generalisation split (added rev 2):** hold out entire team archetypes, not random turns. Train and test on the same teams and you will ship a model that collapses in the wild — VGC-Bench measured exactly this failure.

### M4b — Hidden information model (2–3 weeks, NEW in rev 2)
Track what is *not* known: the opponent's back four, items, spreads. Maintain a belief distribution and filter it as evidence arrives.
**Why this got its own milestone:** the Foul Play author reports set prediction matters as much as or more than search accuracy, and his own numbers back it — 88% GXE in a format with known sets versus 80% where teams are freely built. In VGC without open sheets, this component will dominate your accuracy.
**Tests (each inference rule is one test):** a Pokémon that used a status move is no longer assigned Assault Vest; one that took hazard damage on switch-in is no longer assigned Heavy-Duty Boots; weather persisting past five turns forces the extension item; observed move order under equal priority narrows the speed range; observed damage taken narrows the defensive spread.

### M5 — WPA attribution (2 weeks)
Split each turn's delta into decision and luck.
**Tests:** conservation (components sum to total, every turn, all replays). Scripted turn where the only variable is a critical hit → luck captures it, decision ≈ 0. Scripted turn with an obviously losing switch → decision strongly negative.

### M6 — Bot (optional, 3–4 weeks)
Adopt an existing agent — VGC-Bench ships pre-trained checkpoints, so start there rather than training. Its job is generating clean self-play data and stress-testing the WP model.
**Tests:** beats random ≥ 90% over 200 battles; beats "always strongest move" > 55%.

### M7 — The actual deliverable (1 week)
CLI: paste a replay URL, get a ranked table of your biggest win-probability swings, each tagged decision or luck.
**Tests:** end-to-end on 5 fixture replays with expected top-3 swings.

**Revised total: 5–6 months for one strong engineer.** M1 got cheaper, M3 and M4b got more expensive. Net roughly flat, but the risk is better placed — you are now spending time on the parts nobody has solved.

---

## 4. Turning expert content into tests (your job, not engineering's)

WolfeyVGC, CybertronVGC, James Baek and vgcguide.com are not code inputs — they are **your specification source**. Watch/read with a notebook and produce a backlog where each entry is:

> *Claim:* "Never lead your Trick Room setter into a faster opposing Taunt user."
> *Becomes:* a labelled test position + assertion that WP(lead A) < WP(lead B) by a meaningful margin.

Aim for 50–100. They become features in v0, a regression suite catching nonsense predictions, and the demo — because the model agreeing with a world champion sells itself. Where it disagrees, that's either a bug or an insight, and you triage.

**Head start:** the Foul Play inference rules in M4b above came from a blog post in twenty minutes. Mine existing technical write-ups the same way you mine the videos.

---

## 5. The damage roll trap (read this before M3)

Every move has 16 equally likely damage rolls, plus roughly a 5% critical hit chance — up to 32 distinct damage values per move.

For speed, poke-engine groups these: it checks which rolls cause the target to faint, buckets the rolls by that outcome, averages the damage inside each bucket and sums the probabilities. A 75%-to-KO move becomes two branches instead of thirty-two. This is an excellent optimisation **for a bot choosing a move**, because the practical difference between two non-fainting rolls is usually nil.

**It is wrong for measurement.** Your product exists to tell a player they got lucky. A high roll leaving the opponent at 2 HP versus a low roll leaving them at 40 HP is precisely the swing you are selling, and averaging erases it. Keep the full distribution in the WPA path.

You may still want the grouped version for any search component. If so, treat them as two separate code paths with a test asserting they disagree in the expected direction — do not let one silently become the other.

---

## 6. Public resources to use

| Resource | What it is | Note |
|---|---|---|
| `cameronangliss/vgc-bench` | VGC doubles benchmark: PSRO RL, behaviour cloning, LLM and heuristic agents, replay scraper and parser | MIT. **Your starting point.** Fork it |
| `cameronangliss/vgc-battle-logs` (HF) | Pre-scraped open-team-sheet VGC logs through 04 May 2026 | Saves days of scraping |
| `cameronangliss/vgc-bench-models` (HF) | Pre-trained behaviour-cloning and RL checkpoints | Skip training entirely at first |
| `smogon/pokemon-showdown` | The reference simulator | **Use the version VGC-Bench pins as a submodule, not a fresh clone** |
| `hsahovic/poke-env` | Python interface for Showdown bots | MIT; pinned in VGC-Bench and updated often — a stale copy is the usual cause of breakage |
| `pmariglia/foul-play` + `poke-engine` | Strong singles bot: MCTS with decoupled simultaneous-move handling, over a Rust engine that returns reversible instructions rather than copied states | Architecture template, not a drop-in |
| Foul Play write-up (pmariglia.github.io) | Explains instruction generation, damage roll grouping, hidden-info inference, set prediction | Read before M3 and M4b |
| `pkmn/engine` | Very fast Zig engine, ~1000× Showdown | Still pre-1.0, check status before depending on it |
| Metamon parsed replays (HF) | Replays parsed into RL trajectories | **Non-commercial licence — check before any commercial use** |
| Showdown replay API | Public replays, add `.json` to a replay URL | Paginated; be polite with rate limits |
| pkmn.ai | Survey of prior Pokémon AI projects | Saves rediscovering dead ends |
| pikalytics / Victory Road | Usage stats, current regulation, tournament teams | Feeds your priors and team pools |
| arXiv 2506.10326 (VGC-Bench) | The benchmark paper | |
| arXiv 2608.29197 (PokaiTrainer) | Aug 2026 belief-state search for VGC, engine reported at ~99% Showdown parity | Recent; worth reading before committing to an engine |

**Licence discipline:** MIT code is safe to build on with attribution. Non-commercial datasets are not. Have someone check each dependency at M0, not at launch.

---

## 7. Terminal instructions

Run these in **Terminal** (Mac: Cmd+Space, type "Terminal") or **PowerShell** (Windows: Start, type "PowerShell"). Copy one line at a time, press Enter, wait for it to finish.

### One-time setup — Mac
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh node python@3.13
```

### One-time setup — Windows
```powershell
winget install Git.Git GitHub.cli OpenJS.NodeJS Python.Python.3.13
```

### Connect to GitHub
```bash
gh auth login
```
Choose GitHub.com → HTTPS → login with a browser, then follow the prompts.

### Fork VGC-Bench and set it up
```bash
gh repo fork cameronangliss/vgc-bench --clone --fork-name vgc-wpa
cd vgc-wpa
git submodule update --init --recursive
cd pokemon-showdown
npm i
node pokemon-showdown start --no-security
```
Wait until it says a worker is listening on port 8000. **Leave that window open** — the server is running. Open a **second** terminal window for everything else.

### Install the Python side
```bash
cd vgc-wpa
pip install .[dev]
```
If that fails on the `open-spiel` dependency, it can be removed from `pyproject.toml` — it is only needed for their evaluation module.

### Everyday commands
```bash
cd vgc-wpa
pytest            # run the tests — this is your definition of done
git add -A
git commit -m "describe what changed"
git push
```

### Make it your own repo
The fork keeps a link back to the original, which is correct and courteous while you are contributing fixes upstream. When your own code outgrows theirs, split the WP model and WPA engine into a separate private repo that depends on the fork.

### Have Claude Code do the building
```bash
npm install -g @anthropic-ai/claude-code
cd vgc-wpa
claude
```
Paste this plan in and say: *"Start with M0. Write the failing test first, show it failing, then make it pass."* Insist on that order every milestone — it is the whole discipline, and it is easy to let slip.

---

## 8. Risks to watch as PO

1. **Scope creep into engine building.** Every week on rules accuracy is a week not spent on the thing nobody else has.
2. **Hidden information (now M4b).** You cannot see the opponent's items, spreads, or back four. A model trained only on open-team-sheet battles knows more than your live user does — you must degrade it honestly at inference time or it will be confidently wrong.
3. **Generalisation.** VGC-Bench found agents trained on one team beat broadly-trained agents on that team, then lose badly on unseen teams. Hold out whole archetypes when you evaluate, or you will ship a lie.
4. **Format churn.** Regulations rotate every few months and a new ruleset took effect in September 2026. Treat "currently legal" as config data, never hardcoded.
5. **Calibration over accuracy.** A model that says 80% and is right 80% of the time beats a sharper but miscalibrated one. Hold the line in reviews.
6. **Doubles combinatorics.** Hundreds of joint actions per turn versus a handful in singles. Anything that works in singles may be 100× too slow.
7. **Dependency drift.** Three moving pieces are pinned to each other — the fork, the Showdown submodule, and poke-env. Most "it broke" reports will be one of these being stale. Put version checks in CI.

---

## 9. First week, concretely

1. Run §7. Fork, submodules, local Showdown server up, `pytest` green.
2. Read the VGC-Bench README and the Foul Play write-up yourself. Two hours, and it will change your questions.
3. Write §2 into `docs/DEFINITIONS.md` and have engineering sign off before any modelling.
4. Download the pre-scraped log dataset and run their parser over it. You will have real parsed VGC data in week one.
5. Start the expert-claims backlog from §4. Target 20 entries before modelling starts.
6. Ship M0. A green CI check is a real milestone.
