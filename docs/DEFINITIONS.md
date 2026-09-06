# DEFINITIONS

**Status:** approved by the product owner. Revision 5 — adds §13 (data splitting).
**Applies to:** milestones M4, M4b, M5, M7.

This document is the contract. If code and this document disagree, the code is wrong.

---

## 1. Win Probability — `WP(s)`

The probability that a given side eventually wins **the current game**, given the state `s`.

- Range 0.0 to 1.0. A won game is exactly 1.0, a lost game exactly 0.0.
- Always stated **from the perspective of the player being analysed**, never "player 1". The other side is `1 − WP`.
- Conditioned on an explicit information set — see §5, which is the single most important decision in this document.
- The game is the modelled unit. Set-level probability is derived from it, never modelled directly — see §11.

## 2. Win Probability Added — `WPA`

For any decision point, `WPA = WP(after) − WP(before)`.

Positive means the player's position improved. Summed over a whole game, WPA telescopes to `1.0 − WP(start)` for the winner. That is a useful end-to-end check.

## 3. The split: decision versus luck

Every `WPA` decomposes into exactly two components.

- **Decision WPA** = the expected `WP` of the action the player chose, averaged over every random outcome, minus the expected `WP` of the baseline action (§4). *Did they choose well?*
- **Luck WPA** = the `WP` of what actually happened, minus the expected `WP` of the action they chose. *Did the dice cooperate?*

**Conservation:** `Decision WPA + Luck WPA = WPA`, at every decision point, in every game, with no exceptions. Tolerance ±0.001 for floating point only. A conservation failure is a P1 bug, not a rounding note.

## 4. Baseline for Decision WPA

We report **two** numbers, always both, never one alone:

- **Cost vs. best** — against the single best action available. This is the coaching number: "that switch cost you 14%."
- **Cost vs. average** — against the mean over legal actions. This is the fairness number, and it stops the tool telling a competent player they misplayed every single turn because they weren't a solver.

Rationale: "vs. best" alone is demoralising and makes good players look bad. "Vs. average" alone hides real errors. Shipping both is a product requirement, not an implementation detail.

## 5. Information set — the critical decision

Two distinct quantities. They must never be conflated, and both must be labelled wherever they appear.

- **`WP_public`** — conditioned only on what was legitimately known to the player at that moment. This includes everything revealed earlier **in the same set** (§11.3) and, in open-team-sheet formats, the sheet contents themselves (§12). **This is the product.** It is what the player could actually have known, and therefore the only fair basis for judging their decision.
- **`WP_oracle`** — conditioned on full information, using open team sheets in hindsight. **Internal only.** For model debugging, research, and post-hoc analysis. Never shown to a user as a judgement of their play.

`WP_oracle` remains distinct even in open-sheet formats, because sheets do not reveal everything (§12.2). Degrading honestly to `WP_public` at inference is a build requirement, not an optimisation.

## 6. Decision points, not turns

Attribution happens at every point where the player made a choice. That includes:

- team preview / bring-four selection
- lead selection
- each move-and-target selection
- forced switch after a faint
- Terastallisation and any format gimmick, as a distinct choice

A single game turn may therefore contain multiple decision points. Do not aggregate to the turn before attribution — aggregate afterwards for display.

## 7. Simultaneity

Both players choose without seeing the other's choice. Therefore the baseline in §4 is evaluated against the **opponent's belief-weighted distribution over their plausible actions**, not against the action the opponent actually chose.

This matters more than it sounds. Evaluating against what the opponent actually did would punish a player for a well-reasoned read that happened to be exploited, and reward a lucky guess. We are measuring decision quality, not outcome.

## 8. What counts as luck

Enumerated, and this list is the spec. Anything on it is variance; anything not on it is a decision.

Damage rolls · critical hits · accuracy checks · secondary effect procs · status wake-up and thaw timers · confusion self-hits · flinches · speed ties · multi-hit move counts · any item or ability with a stated proc chance.

Opponent behaviour is **not** luck. A surprising opponent choice is information, and it shows up through the belief model in §7.

## 9. Excluded games

No WPA is produced for games ending in forfeit, timeout, or disconnection. Mark them incomplete and drop them from both training data and reports. Silently treating a timeout as a loss would poison the calibration set. Where such a game occurs inside a set, see §11.5.

---

## 10. Resolved decisions (closed rev 4)

### 10.1 Display unit — percentage points

All user-facing WPA figures are expressed in percentage points, signed. "That switch cost you 14 points." Internal computation stays in raw probability; conversion happens at the display boundary only.

### 10.2 Reporting threshold — 0.5 percentage points

Swings at or above 0.5pp are surfaced in the M7 report. Below that, aggregated and not itemised.

**Compute-versus-display separation is mandatory.** Every decision point is computed and stored at full precision regardless of threshold. The threshold is a display filter, configurable at runtime, never a shortcut that skips calculation. The §3 conservation check runs over all computed values, not the displayed subset.

**Engineering must raise a blocker if the model's own uncertainty exceeds this threshold.** A 0.5pp filter is only meaningful if the model can resolve differences at that scale. Before M7 ships, measure the run-to-run variation of `WP` on identical states and report it. If that variation is larger than 0.5pp, the report is showing noise as insight and we raise the threshold rather than ship it. Do not quietly adjust the number — bring the measurement to the PO.

Rationale for the low setting: VGC games are short, roughly 15–25 decision points, so the itemised list stays readable even at a fine threshold, and small consistent leaks are exactly what a coaching tool should catch. The risk is noise, hence the measurement requirement above.

### 10.3 `WP_oracle` stays internal

Not exposed to users in v1, in any form, including opt-in. It appears in debugging output and research notebooks only. Revisit after v1 ships and we have seen how users respond to `WP_public`.

---

## 11. Best-of-three (added rev 2)

Official VGC is played as a best-of-three set. "Game" and "set" are distinct units and must be distinct fields everywhere in the codebase, schema, and UI. Roughly 89,000 parsed battles in our corpus are dominated by bo3 logs, so this is the common case, not an edge case.

### 11.1 Model the game, derive the set

`WP` is modelled **only** at game level. Set-level probability is computed arithmetically from game-level probabilities and the current set score. There is no separately trained set-level model.

Rationale: a set-level model would have roughly a third of the training examples and would have to learn game dynamics implicitly anyway. Deriving keeps one model, one calibration target, one thing to debug.

### 11.2 Set win probability — `SWP`

Given `WP_g` for the current game and the set score, the probability of winning the set follows directly. With the set level at one game each, `SWP = WP_g`. Where the player leads, winning the current game closes it out and losing it forces a decider; where the player trails, the current game must be won to reach a decider at all.

**Implementation constraint:** derive `SWP` from the *current* `WP_g` plus an estimate for any hypothetical future game, and state that estimate explicitly rather than assuming 0.5. Teams are not symmetric, and matchup advantage carries across games.

**Tests:** `SWP` = 1.0 when the set is won; `SWP` = `WP_g` at one game apiece; `SWP` is monotone increasing in `WP_g` at every set score.

### 11.3 Information carries across games — this is the important one

Games 2 and 3 are **not** fresh starts. Both players have legitimately seen part of the opponent's team, and often items, moves, spreads, and Tera type. That information is public knowledge for the rest of the set and **must** be included in `WP_public`.

Consequences:

- A game-2 team preview state has a materially narrower belief distribution than a game-1 team preview state of the same matchup. Treating them alike understates the player's actual knowledge and mislabels good reads as luck.
- The M4b belief model must accept prior-game revelations as evidence, alongside the within-game inference rules already specified.
- Bring-four selection in games 2 and 3 is a *higher-information* decision than in game 1, and the Decision WPA baseline in §4 must reflect that. This is likely one of the largest genuine skill signals in the whole product.

**Tests:** for the same board position, the belief distribution after a prior game revealed a Pokémon must be strictly narrower than with no prior game. A game-2 state must never be assigned a wider belief set than the corresponding game-1 state.

### 11.4 Attribution scope

WPA is computed within a game. Set-level reporting aggregates game-level WPA and additionally reports the bring-four decision at each game start as its own line item, since that decision is set-scoped in character even though it opens a game.

### 11.5 Incomplete games inside a set

If one game of a set is excluded under §9, the remaining games stay valid and are still analysed. The set-level summary is marked incomplete. Do not infer a set result from a forfeited game.

### 11.6 Schema requirement

Every parsed state carries: a set identifier, a game index within the set, and the set score entering that game. If the upstream parser flattens bo3 logs into independent games and discards this, reconstructing it is a **blocking prerequisite for M4**, not a nice-to-have. Verify before modelling starts.

---

## 12. Open team sheets (added rev 3)

Our training corpus is the Champions VGC Bo3 format, which uses **open team sheets**. Each game log contains a `|showteam|` entry for both sides at team preview, and both players legitimately see it before choosing their bring-four.

This materially changes the hidden-information problem and narrows M4b.

### 12.1 What the sheet gives us

Confirmed present in the sampled logs, for all six Pokémon on both sides: species, item, ability, full move list, gender, and level.

This information is **public from team preview onward** and must be treated as such in `WP_public`. A model that estimates a distribution over the opponent's items or moves in this format is estimating something both players already know, and will be worse for it.

### 12.2 What remains hidden — verify before building

The sampled sheet strings show empty slots where EVs, natures, and IVs would sit, and the Tera type field was not visible in the truncated sample.

**Engineering task, before M4b starts:** parse a sheet string field by field, document in `docs/SHEET-FIELDS.md` exactly which are populated and which are empty, and confirm against several logs rather than one. Do not assume. The residual hidden information is the entire remaining scope of M4b, so getting this list wrong sets the milestone's size wrong.

Expected residual, subject to that verification:

- **Bring-four selection** — which four of six, revealed only as they switch in. This is the largest remaining unknown and the most interesting one.
- **Terastallisation** — type, if not on the sheet; and timing and target, which are decisions rather than facts.
- **EV spreads, natures, IVs** — inferred from observed damage and move order, using the same inference rules already specified in the plan's M4b test list.

### 12.3 Consequences for scope

- M4b narrows from a general belief model over full opposing sets to a **bring-four and spread model**. Rescoped in the plan.
- The §11.3 requirement that prior-game information carries forward still holds, but its content changes: what carries forward is the four they brought, the Tera they used, and observed damage evidence — not the team, which was known from the start.
- The prior-game carryover and the bring-four model are now the same problem, and should be built as one component.

### 12.4 Transferability — do not paint us into a corner

Open sheets are standard in official VGC, which is our target user's context, so training here is the right call. But ladder play and many online formats hide sheets entirely.

**Architectural requirement:** the state schema and the model interface must accept an *unknown* set for any opposing Pokémon, even though our current corpus never produces one. Represent sheet knowledge as evidence supplied to the belief model, never as a required field. A model that cannot run without a sheet is a model that cannot be used outside this one format, and retrofitting that later is expensive.

**Test:** the pipeline must run end to end on a synthetic battle with all opposing sheet fields blanked, producing a valid — if less confident — `WP_public`. This test should exist from the first day of M4b, before the format-specific work.

### 12.5 Format is configuration

The corpus is Regulation M-A, which predates the ruleset effective September 2026. Legal species, items, and mechanics are configuration data, never hardcoded. Assume the format will rotate again before we ship.

---

## 13. Data splitting (added rev 5)

The parser emits **two trajectories per game**, one from each player's perspective. Up to three games share a set. Both players' teams persist across the whole set.

A random split by trajectory therefore places the same game — and the same matchup — in both training and test data. Every downstream metric would look strong and mean nothing.

**Rule: split by set identifier.** All trajectories from a best-of-three go to the same side of any train/validation/test boundary. Never split by trajectory, game, or player.

**Additionally, for M4 evaluation:** hold out whole team archetypes, not random sets. VGC-Bench found agents trained narrowly beat broadly-trained ones on familiar teams and lose badly on unfamiliar ones. A set-level split alone still lets near-identical team compositions appear on both sides.

**Tests:** no set ID appears in more than one split; no exact team pairing appears in more than one split; the archetype holdout is available as an option from the first day of M4.

This is not tunable and not a performance trade-off. A leaky split does not announce itself — it silently converts every calibration number in the product into a false claim.

---

*Approved: product owner. Engineering to raise a blocker rather than reinterpret if any clause here proves impractical.*
