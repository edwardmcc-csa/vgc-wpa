# DEFINITIONS

**Status:** approved by the product owner. Changes require PO sign-off, not just a PR review.
**Applies to:** milestones M4, M4b, M5, M7.

This document is the contract. If code and this document disagree, the code is wrong.

---

## 1. Win Probability — `WP(s)`

The probability that a given side eventually wins the battle, given the state `s`.

- Range 0.0 to 1.0. A won battle is exactly 1.0, a lost battle exactly 0.0.
- Always stated **from the perspective of the player being analysed**, never "player 1". The other side is `1 − WP`.
- Conditioned on an explicit information set — see §5, which is the single most important decision in this document.

## 2. Win Probability Added — `WPA`

For any decision point, `WPA = WP(after) − WP(before)`.

Positive means the player's position improved. Summed over a whole battle, WPA telescopes to `1.0 − WP(start)` for the winner. That is a useful end-to-end check.

## 3. The split: decision versus luck

Every `WPA` decomposes into exactly two components.

- **Decision WPA** = the expected `WP` of the action the player chose, averaged over every random outcome, minus the expected `WP` of the baseline action (§4). *Did they choose well?*
- **Luck WPA** = the `WP` of what actually happened, minus the expected `WP` of the action they chose. *Did the dice cooperate?*

**Conservation:** `Decision WPA + Luck WPA = WPA`, at every decision point, in every battle, with no exceptions. Tolerance ±0.001 for floating point only. A conservation failure is a P1 bug, not a rounding note.

## 4. Baseline for Decision WPA

We report **two** numbers, always both, never one alone:

- **Cost vs. best** — against the single best action available. This is the coaching number: "that switch cost you 14%."
- **Cost vs. average** — against the mean over legal actions. This is the fairness number, and it stops the tool telling a competent player they misplayed every single turn because they weren't a solver.

Rationale: "vs. best" alone is demoralising and makes good players look bad. "Vs. average" alone hides real errors. Shipping both is a product requirement, not an implementation detail.

## 5. Information set — the critical decision

Two distinct quantities. They must never be conflated, and both must be labelled wherever they appear.

- **`WP_public`** — conditioned only on what was publicly visible at that moment: revealed Pokémon, revealed moves, observed damage, inferred constraints from M4b. **This is the product.** It is what the player could actually have known, and therefore the only fair basis for judging their decision.
- **`WP_oracle`** — conditioned on full information, using open team sheets in hindsight. **Internal only.** For model debugging, research, and post-hoc analysis. Never shown to a user as a judgement of their play.

Training on open-team-sheet battles gives a model that knows more than a live user does. Degrading it honestly to `WP_public` at inference is a build requirement, not an optimisation. See risk 2 in the plan.

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

## 9. Excluded battles

No WPA is produced for battles ending in forfeit, timeout, or disconnection. Mark them incomplete and drop them from both training data and reports. Silently treating a timeout as a loss would poison the calibration set.

---

## 10. Open items requiring PO decision before M5

- [ ] Display unit: raw probability, percentage points, or a normalised score. Recommend percentage points.
- [ ] Minimum swing worth surfacing in the M7 report. Recommend 3 percentage points, tunable.
- [ ] Whether `WP_oracle` is ever exposed to users as an opt-in "what actually was true" view. Recommend not in v1.

---

*Approved: product owner. Engineering to raise a blocker rather than reinterpret if any clause here proves impractical.*
