# DEFINITIONS

**Status:** approved by the product owner. Revision 11 — §7 weighs each plausible action by its worth to the one choosing, at the strength learned on training games (PO, 13 Nov 2026). Revision 10 — §3 splits "your decision" into your choice and the position, and §4's average becomes the typical choice (PO, 10 Nov 2026). Revision 9 — §10.2's threshold raised to 3pp, and the reported `WP` is an average of models (PO, 6 Nov 2026). Revision 8 rewrote §3 as a three-way split, with §4's first line to match. Revision 7 added §15 (two formats).
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

## 3. The split: your choice, the position, their decision, the dice

Every `WPA` decomposes into exactly four components. All four are from the analysed player's side. Write:

- `WP(before)` for the win probability at the decision point;
- `E[WP | a typical choice]` for the expected `WP` after the decision when your choice is drawn from what players typically choose in this position (the same choice model §7 uses for the opponent), averaged over the opponent's likely replies (§7) and every random outcome (§8);
- `E[WP | your choice]` for the same with your actual choice;
- `E[WP | your choice, their choice]` for the same, averaged over random outcomes only.

The four components are:

- **Your choice** = `E[WP | your choice] − E[WP | a typical choice]`. *Did you choose better than players typically do here?* This is the decision credited to you. With only one option it is exactly 0.
- **The position** = `E[WP | a typical choice] − WP(before)`. *What did this decision point hold, whatever you chose?* It is credited to no one. It carries what playing the turn out reveals that the single `WP` estimate did not: a game that ends whatever anyone chooses, a Pokemon about to come in.
- **Their decision** = `E[WP | your choice, their choice] − E[WP | your choice]`. *Did their actual reply do better or worse than their likely replies?* It is negative when they read you well.
- **The dice** = `WP(after) − E[WP | your choice, their choice]`. *Did the random outcomes in §8 cooperate?*

**Conservation:** your choice + the position + their decision + the dice = `WPA`, at every decision point, in every game, with no exceptions. Tolerance ±0.001 for floating point only. A conservation failure is a P1 bug, not a rounding note.

Rationale (rev 10, PO, 10 Nov 2026): revision 8 called your choice plus the position "your decision". On the Week 10 sample the position was typically about 11 points a turn, as big as the choice itself, so "your decision" credited players with what no choice of theirs moved.

## 4. Baseline for Decision WPA

Beside the split in §3 we report the choice against two baselines, always both, never one alone:

- **Cost vs. best** — against the best of the player's likely choices. This is the coaching number: "that switch cost you 14%."
- **Cost vs. typical** — against the typical choice: this is **your choice** in §3. It is the fairness number, and it stops the tool telling a competent player they misplayed every single turn because they weren't a solver.

Rationale: "vs. best" alone is demoralising and makes good players look bad. "Vs. typical" alone hides real errors. Shipping both is a product requirement, not an implementation detail.

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

Each plausible action's chance is the choice model's chance, weighed by how much the action is worth to the one choosing: `chance × exp(strength × worth)`, scaled so the chances add up to 1. Its worth is the expected `WP` for the one choosing, against the other side's likely actions from the choice model alone. Where the log hides part of a player's action (§3: averaged over the actions the log allows), that average is weighed the same way. One strength serves both formats. It is learned on training games: it is the strength that makes the actions players took likeliest, which is also the strength at which, on training games, the actions players took are worth on average what the model expects. Revision 10's model is strength 0.

Rationale (rev 11, PO, 13 Nov 2026): with the choice model alone, the choices players made were worth 6.2 points more on average than the model expected (115 training games, both formats), and their opponents' "their decision" averaged about −2.2 points in Weeks 10 and 11: real players read each other better than the model assumed. The learned strength is 6.55 (6.3 Reg M-A, 6.8 Reg M-B alone). On validation (the Week 12 sample), where the log shows the choice, your choice's average went from +3.0 to +1.2 points in Reg M-A and from +3.1 to +1.3 in Reg M-B; their decision's from −2.4 to −0.6 and from −2.6 to −0.7.

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

### 10.2 Reporting threshold — 3 percentage points

Swings at or above 3pp are surfaced in the M7 report. Below that, aggregated and not itemised.

**Compute-versus-display separation is mandatory.** Every decision point is computed and stored at full precision regardless of threshold. The threshold is a display filter, configurable at runtime, never a shortcut that skips calculation. The §3 conservation check runs over all computed values, not the displayed subset.

**The `WP` the report shows is an average of models.** It is the average of 5 to 10 models, each trained with the same settings on a resample of the training sets (whole sets drawn with replacement). Averaging brings the model's own noise down, roughly with the square root of the number of models.

**Engineering must raise a blocker if the model's own uncertainty exceeds this threshold.** Before M7 ships, measure the run-to-run variation of the averaged `WP` on identical states and report it. If that variation is larger than 3pp, the report is showing noise as insight and we raise the threshold rather than ship it. Do not quietly adjust the number — bring the measurement to the PO.

Rationale: the threshold was 0.5pp until 6 Nov 2026. A single v4 model's own noise measured about 3pp (Week 9, Task 6), so a 0.5pp filter would have shown noise. Small consistent leaks under 3pp are still found by aggregating over many games; they are not itemised per decision.

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

## 14. Spread revelation (added rev 6)

Open team sheets reveal species, item, ability, moves and Tera type. They do **not** reveal EVs, IVs or nature. Speed tier and effective bulk are therefore hidden information in both open- and closed-sheet formats.

These quantities determine correct play. A win probability that ignores them is not measuring the decision the player actually faced.

**Rule: the parsed record must carry what has been revealed about spreads, at the decision point where it was revealed.** Revelation is monotonic within a set — evidence from game 1 remains available in game 3 (see §11.3) — and it never runs backwards. A model must not condition on information the player did not yet hold.

**Observation, not inference.** The parsed record stores observable events: damage dealt with full modifier context, move order at known priority, survival and faint thresholds, exact recovery amounts, behavioural item tells, Tera activation. It does not store derived bounds, fitted spreads or probabilities. Derivation is M4b's responsibility and must be reproducible from the stored observations alone.

**HP expression is part of the record.** Whether an HP figure is exact or a percentage must be stored per side and per event. Exact HP constrains a spread to a point; a percentage constrains it to an interval. Losing the distinction silently weakens every constraint built on top of it.

This section defines what must be captured. It does not define how spreads are estimated.

**Addendum, Week 3 Task 10:** the corpus's HP is percentage-only, exhaustively — every `|-damage|`/`|-heal|` figure across all 88,905 battles resolves to a percentage of max HP, zero exceptions. The "exact HP pins the stat outright" case this section anticipates does not occur in this data; only the weaker interval case does. Flagged to the product owner per this section's own rule rather than worked around silently; the decision was to record `hp_expression` as specified (still populated on every HP-bearing observation, never null) rather than narrow scope, since the field is correct — it just never varies in this corpus.

---

*Approved: product owner. Engineering to raise a blocker rather than reinterpret if any clause here proves impractical.*

---

## 15. Two formats (added rev 7)

**Decision (product owner):** Regulation M-A and Regulation M-B are **two formats**, not one format with a missing field. They differ in what a team sheet reveals (nature is shown in every M-B sheet and in none of M-A, `docs/SHEET-FIELDS.md`), and the PO treats the rule sets as distinct.

**Consequences:**

- **Every set belongs to exactly one format.** A set never spans formats. Format is identified from the battle tag (`gen9championsvgc2026regma...` or `...regmb...`).
- **Models are fitted, calibrated and evaluated per format.** Every metric in §1–§14 is reported per format. A pooled number may be shown as a secondary figure and never as the headline.
- **Splits (§13) are made inside each format.** The set rule is unchanged; the format is an additional stratum, so each format has its own train, validation and test sets.
- **Spread inference differs by format.** Nature is an observation in M-B and a hidden quantity in M-A. M4b must not carry a nature assumption from one format into the other.
- **Data volume is unequal and must be reported.** At the time of this revision the corpus holds 84,738 M-A battles and 4,167 M-B battles (about 5%). Any M-B result must state its sample size alongside it. A model that only works where data is plentiful must say so.
- **Format stays configuration (§12.5).** Adding a third format is a configuration change, not a code change.

This section does not change §12.2's stale expectation about Terastallisation; `docs/TERA-COVERAGE.md` is the current finding (the format disables it). Correcting §12.2 and §12.3 is a separate edit for the PO to approve.
