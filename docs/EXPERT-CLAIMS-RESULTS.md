# Expert claims, scored by v0 and v1 (report only)

Week 5 Task 8. Code: `wpa/claims.py` (`python -m wpa.claims`). Nothing here gates.

Each claim in `docs/EXPERT-CLAIMS.md` was turned into real starting positions from
the validation split, and the follow-up positions the claim compares were built by
editing the features: a replacement comes in at full hit points, a turn passing
takes a turn off every timer, the team-sheet features stay as they were.

| | Reg M-A v0 | Reg M-A v1 | Reg M-B v0 | Reg M-B v1 |
|---|---|---|---|---|
| EC-001 (single KO or stall beats double KO) | 0% of 71 | 0% of 71 | 0% of 1 | 0% of 1 |
| EC-002 (sacrificing the spent Pokemon beats keeping it) | 100% of 500 | 6% of 500 | 100% of 189 | 7% of 189 |

Percentages are how often the model prefers the claim's choice.

**EC-001.** Positions: the opponent has Tailwind with 1-2 turns left, two weakened
Pokemon active (60% hit points or less between them), two unseen in the back,
nobody fainted. Both models always prefer the double knock-out. v1 rates it
higher still (mean 0.81 against 0.66 for one knock-out and 0.52 for a stall). The
claim turns on *who is faster* once the sweepers come in under Tailwind, and no
feature carries speed: not the Pokemon's Speed, not who is faster than whom. So
this result is expected, and it is the clearest pointer to what the next feature
round needs: base Speed of the active and incoming Pokemon, combined with the
Tailwind and Trick Room timers.

**EC-002.** Positions: we have two Pokemon active, one nearly spent. Follow-ups:
the spent one is knocked out and the strong one untouched, or the spent one
survives and the strong one loses half its hit points. v0 always prefers the
sacrifice, but only because it adds up hit points. v1 prefers keeping the spent
Pokemon alive in 93-94% of positions: it has learned that a Pokemon on the board
is worth more than half a Pokemon's hit points. The claim's own condition
("a speed or type advantage") is not in the features. Like EC-001, it needs speed
and type match-ups before it can be judged.

---

## Week 6: re-scored with v2 (speed features, decision table)

Week 6 Task 5. Code: `wpa/claims_v2.py` (`python -m wpa.claims_v2 scan`, then
`python -m wpa.claims_v2 report`). Nothing here gates.

**What changed in the method.** Week 5 edited feature rows, so whoever came in was
anonymous. Now the follow-ups are made on the board itself and every feature is
computed again by the same code that builds the training table:

- Who comes in is the real reserve: the Pokemon that side actually brought (the
  ones that appear at some point in the game). A position is used only when all
  four of the side that changes are known.
- Choices are a small game tree: we pick which of theirs to knock out (our best),
  they pick who comes in (their best reply). For EC-002 we pick who comes in.
- A turn passing takes a turn off every timer, so Tailwind with one turn left is
  gone when the replacements arrive and Tailwind with two turns left still runs.
- Approximations, the same for every follow-up: nobody else takes damage,
  counters such as Protect's reset, and the end-of-turn field record of the turn
  being decided is not used.

Positions come from the validation split: every EC-001 position, and up to 12 EC-002
positions per log shard and format. Percentages are how often the model prefers the
claim's choice.

| | Reg M-A v0 | Reg M-A v1 | Reg M-A v2 | Reg M-B v0 | Reg M-B v1 | Reg M-B v2 |
|---|---|---|---|---|---|---|
| EC-001, all positions | 0% of 138 | 0% of 138 | 0% of 138 | 0% of 2 | 0% of 2 | 0% of 2 |
| EC-001, their reserve acts first after a double KO | 0% of 105 | 0% of 105 | 0% of 105 | 0% of 1 | 0% of 1 | 0% of 1 |
| EC-001, the claim's full premise | none found | | | none found | | |
| EC-002, all positions | 100% of 768 | 22% of 768 | 37% of 768 | 100% of 399 | 16% of 399 | 35% of 399 |
| EC-002, the sacrifice gains speed | 100% of 182 | 26% of 182 | 49% of 182 | 100% of 97 | 10% of 97 | 52% of 97 |

**EC-001.** The claim's full situation never turns up in the validation games: in
the 8 positions where our pair outspeeds their Tailwind pair, their reserve does not
outspeed us after a double knock-out. The narrower situation the claim warns about
(after a double knock-out, their reserve acts before our fastest) is common: 105 of
138 positions in Reg M-A, 81 of them with Tailwind still running when the
reserve arrives. In every one of them, all three models prefer the double
knock-out. v2 gives a mean of 0.79 for the double knock-out, 0.67 for the single
and 0.55 for a stall.

So the speed features do not change the verdict. The models have now seen the
speed of the incoming Pokemon and still value two knock-outs above tempo. Either
the claim holds only in narrower cases than these positions (the claim also
says "the opposing pair has little damage potential", which no feature measures),
or what makes the reserve dangerous is damage, not just speed. Nothing estimates
how hard the incoming Pokemon hit or how much our side can take. That is the next
feature this claim needs.

**EC-002.** v1 strongly preferred keeping the spent Pokemon (16-22% agreement).
v2 moves towards the claim, and the move comes from speed. Where bringing in the
replacement leaves us outspeeding more of their Pokemon, v2 is split almost
evenly: 49% in Reg M-A and 52% in Reg M-B, with mean win probability for sacrifice
and keep within 0.01. Without that speed gain it still prefers to keep. That is
what the claim says: the sacrifice is worth it *when* it buys an advantage. The
claim's other condition, a type advantage, is still not in the features.

v0 always prefers the sacrifice, but only because it adds up hit points. That is not
evidence for the claim.

---

## Week 7: re-scored with v3 (damage, stat changes, spreads)

Code: `wpa/claims_v2.py` with `--groups ABCDEFG --usage usage_stats`
(runbook Section 16, step 7). Nothing here gates.

Each position now carries every Pokemon's most likely spread at that decision.
Follow-ups keep those spreads, and a Pokemon that faints or comes in loses its
stat stages. Damage (group G) is recomputed for every follow-up.

Each claim also gets a premise **in damage terms**:
- **EC-001:** their active pair cannot take 40% of either of ours, and after a
  double knock-out some way in for their reserve knocks one of ours out this turn.
- **EC-002:** some sacrifice leaves us hitting their board harder than keeping does.

"v3 without damage" is the same model trained without group G.

| Reg M-A | v0 | v1 | v3 without damage | v3 |
|---|---|---|---|---|
| EC-001, all (138) | 0% | 0% | 0% | 3% |
| EC-001, their reserve acts first after a double KO (104) | 0% | 0% | 0% | 4% |
| EC-001, premise in damage terms (1) | 0% | 0% | 0% | 0% |
| EC-002, all (768) | 100% | 22% | 38% | **46%** |
| EC-002, the sacrifice gains speed (204) | 100% | 24% | 59% | 59% |
| EC-002, the sacrifice hits harder (307) | 100% | 21% | 36% | **58%** |

| Reg M-B | v0 | v1 | v3 without damage | v3 |
|---|---|---|---|---|
| EC-001, all (2) | 0% | 0% | 0% | 0% |
| EC-002, all (399) | 100% | 16% | 38% | 38% |
| EC-002, the sacrifice gains speed (76) | 100% | 7% | 59% | 61% |
| EC-002, the sacrifice hits harder (156) | 100% | 24% | 43% | **53%** |

**EC-001.** Damage does not change the verdict. v3 still prefers the double
knock-out in 97% of positions: mean win probability 0.80 against 0.68 for one
knock-out and 0.56 for a stall. The claim's situation in damage terms turns up
once in 9,000 validation games. So the data cannot judge the claim as written. In
the positions the games do contain, taking two Pokemon is worth more than the
tempo it gives away.

**EC-002.** This is where damage shows. Where the sacrifice brings in a Pokemon
that hits their board harder, v3 agrees with the claim in 58% of Reg M-A positions
and 53% of Reg M-B. The same model without damage agrees in 36% and 43%. Where the
sacrifice gains speed, both v3 models agree about 60% of the time. The claim's
condition — "when it buys a speed or type advantage" — is now what moves the
model, in both formats.

**PO decision on EC-001 (30 Oct 2026):** accepted as a niche case. The claim holds
in a rare situation, and that is fine. Keep it as a caveat to understand when
positioning, not as something the model must show on average.
