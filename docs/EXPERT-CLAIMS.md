# Expert claims backlog

The product owner's list of things strong players know, each turned into a labelled test position. Format from the plan (§4): *Claim* becomes a *test position* plus an *assertion*. Target 20 before modelling is judged, 50–100 eventually. Where the model disagrees with a claim, that is either a bug or an insight, and we triage.

Entries here are **specification, not yet tests**. A claim becomes a test when someone builds its labelled position from a real or hand-made state. "Needs" lists the information the position must carry; where the current state record lacks it, that is a finding about the schema, not a reason to drop the claim.

---

## EC-001 — Do not knock out the weak Pokémon if it brings in a stronger one under a running timer

*Source:* product owner, 12 Oct 2026.

*Claim:* My two Pokémon are the faster pair and the opposing pair on the field has little damage potential. The opposing side has Tailwind with about two turns left, and strong sweepers behind the actives. Knocking out both actives brings the sweepers in while their Tailwind still has turns, and they can knock me out. It can be better to knock out only one, or to stall the Tailwind for a turn.

*Becomes:* a position with those features, and two follow-up states: after a double knockout, and after a single knockout or a stall. Assert WP(single knockout or stall) > WP(double knockout). A decision-level version (M5) asserts that Decision WPA marks the double knockout as the worse choice.

*Needs:* Tailwind turns remaining, relative speed of the four active and incoming Pokémon, who is held in reserve, damage potential of the reserve. **Not in `BattleState` today** (it carries species, HP fraction, fainted, active, gimmick).

*Why it matters:* it is a direct counterexample to "fewer opposing Pokémon is never worse for me", which is why the strict monotonicity test was dropped (Week 4 brief, Task 4).

## EC-002 — Sacrifice the spent or badly placed Pokémon to keep the strong one

*Source:* product owner, 12 Oct 2026.

*Claim:* A Pokémon that has done its job, or is poorly positioned for the matchup, can be worth giving up so a strong Pokémon is protected and I gain a speed or type advantage.

*Becomes:* a pair of positions that differ in whether the spent Pokémon is still alive with the strong one at risk, versus the spent Pokémon gone with the strong one preserved and positioned. Assert WP(sacrificed) > WP(kept) when the labelled advantage is present.

*Needs:* speed relationship after the switch, type matchups of the incoming Pokémon, remaining HP of the preserved one. Also not in `BattleState` today.

*Why it matters:* the mirror of EC-001, for your own side. It means "more of my Pokémon alive is better" is not a law either.

---

## Entry template

## EC-nnn — short name
*Source:* who, when.
*Claim:* one or two sentences.
*Becomes:* the labelled position(s) and the assertion.
*Needs:* the state information the position requires, and whether `BattleState` has it.
*Why it matters:* what it tests that other entries do not.
