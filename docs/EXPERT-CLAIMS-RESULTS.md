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
