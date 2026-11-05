# Which four they brought, and a Bo3 set's memory

Week 8 Tasks 1 and 2. Code: `wpa/bring.py`, and `damage_contexts` in
`wpa/features.py`. Tests: `tests/test_bring.py`, `tests/test_sets.py`, and
`tests/test_damage_features.py`. Fit: `python -m wpa.bring` (training split; the
validation check is printed and saved as `models_v4/bring.txt`).

## The model

At team preview each player sees the other's six and brings four. Until all four
have appeared, the back two are unknown. Each sheet Pokemon gets odds from a
small logistic regression on three things:

- **how often its species is brought** in its format (training split, pulled
  towards 4 in 6 for rare species);
- **its place on the sheet** (the first places are brought a little more often);
- **in games 2 and 3 of a set, whether the same player brought it the game before**
  (matched by player name and species).

**The sets of four.** A set of four's chance is the product of its members' odds.
Only sets that contain every Pokemon already seen are counted. The chance each
Pokemon was brought follows from that.

Fitted on 115,429 sides of training games, the weights are:
- species rate 0.86 (on the log-odds scale);
- brought last game +1.99;
- a later game of a set at all -1.13;
- sheet place from +0.25 (first) down to -0.25 (sixth).

## Does it beat the plan's baseline? (validation)

The figures are the mean log chance the model gave the four actually brought,
against a uniform guess over the 15 possible sets.

| | sides | at team preview | uniform | most likely set right | after the two leads | uniform | games 2-3: most likely set right |
|---|---|---|---|---|---|---|---|
| Reg M-A | 14,169 | **-2.471** | -2.708 | 24% (uniform 7%) | **-1.627** | -1.792 | 41% |
| Reg M-B | 593 | **-2.390** | -2.708 | 28% | **-1.562** | -1.792 | 40% |

It beats the uniform guess in both formats, at team preview and after the leads.
It is right most often in games 2 and 3, where the player's previous game is known.

## A Bo3 set's memory

The logs are sharded by set (`logs_sets/`), so a set's games are built together
and in order. When a later game of a set is built:
- **Spreads:** each of a player's Pokemon starts from the spread estimates as the
  set's previous game left them, not from the usage statistics.
- **The four:** what the player brought in the previous game feeds the model
  above.

Nothing from a later game is ever used.

**The plan's test (belief is narrower at the start of game 2).** Over the 20%
build, the mean entropy of a carried Pokemon's spread estimate at the start of a
later game:

| | Pokemon carried | fresh from the statistics | carried from the last game | narrower by |
|---|---|---|---|---|
| Reg M-A | 148,854 | 1.432 | 1.201 | 16.2% |
| Reg M-B | 22,884 | 0.925 | 0.764 | 17.5% |

Reg M-B's estimates start narrower. In both formats, carrying the last game over
narrows them by about a sixth. (An earlier version of this page
said 161,106 Pokemon, from a build that had not finished; both formats together
are 171,738.)

## Groups I and J use it

- **I, the likely back:** for each side, the uncertainty about its back, and what
  its unseen Pokemon would bring against the other side's actives. These are
  expectations over the sets of four still possible (`docs/DAMAGE-FEATURES.md`).
- **J, the whole board:** counts an unseen Pokemon by the chance it was brought.
