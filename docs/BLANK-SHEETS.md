# Blank sheets: win probability without the opponent's team sheet

Week 8 Task 5, the plan's non-negotiable for M4b. Code: `public_sheet`,
`blank_state`, `rows_for_file_blank` and `_blank_contexts` in `wpa/features.py`;
one-sided models in `wpa/model.py`. Tests: `tests/test_blank.py`,
`tests/test_model.py`, `tests/test_evaluate.py`, and the blank build test in
`tests/test_damage_features.py`. Commands: runbook Section 17, step 6.

## Why

Our corpus uses open team sheets: each log shows both sheets at team preview.
Ladder play and other formats do not. The plan requires the model to run without
the opponent's sheet and still give a valid, if less confident, `WP_public`
(`docs/DEFINITIONS.md`, Sections 11 and 12).

## What is hidden

With `--blank`, at every decision:
- **the opponent's species** are known only once each has appeared;
- **their items, abilities and moves** only as the log has revealed them;
- **their sheet order and natures** are not known;
- **spreads** come from the usage statistics alone, with no refining and no Bo3
  memory;
- **the bring model** is used for our own side only.

**Our own sheet stays whole.** `WP_public` is what the player could have known,
and a player knows their own team.

## The symmetric model is wrong here

Every model so far scores a row from both sides and averages:
p = (f(row) + 1 - f(mirrored row)) / 2. That relies on the two sides knowing the
same kind of thing. With only the opponent's sheet blanked they do not: the
mirrored row (their sheet whole, ours blanked) looks like nothing in training.

The first run showed it. On validation the symmetric model over-predicted the side
that keeps its sheet:

| validation, symmetric model | mean predicted | observed | calibration bins off by more than 0.05 |
|---|---|---|---|
| Reg M-A | 0.529 | 0.488 | 3 (0.4-0.7; worst 0.645 predicted, 0.579 happened) |
| Reg M-B (pooled) | 0.522 | 0.483 | 5 (0.2-0.7) |

The model's own score of the row, f, averaged 0.488; the mirrored score,
1 - f(mirror), averaged 0.571. Recalibrating did not fix it.

**The fix: one-sided models** (`v2-train --one-sided`). Such a model scores each
row as it is, p = f(row), and its rounds are chosen on that score. Rows exist from
both players' points of view in training, so f learns each side's chance from what
that side knows.

## Results (validation, 20% Reg M-A sample)

Brier score (lower is better), with the paired loss against full sheets on the
same rows:

| validation | full sheets (v4) | opponent's sheet blanked (`WP_public`) | lost (95% interval) | v0 |
|---|---|---|---|---|
| Reg M-A (5,167 sets) | 0.1851 | **0.1886** | +0.0036 (+0.0028 to +0.0043) | 0.2099 |
| Reg M-B, pooled (199 sets) | 0.1678 | **0.1781** | +0.0104 (+0.0066 to +0.0136) | 0.2033 |

- **It is valid.** Both formats pass the calibration gate. Reg M-A's bins are all
  within 0.013, the same as with full sheets.
- **It is less confident, as the plan expects.** It keeps 85% of v4's gain over v0
  in Reg M-A and 71% in Reg M-B.
- **Reg M-B loses more,** though with 199 sets the size of its loss is
  uncertain.
- The Reg M-B figure has no cross-fitted correction (the brief set no gate for
  this run), and its pooled model reached the 1,000-round cap.

## Both sheets blanked (optional)

`--blank-both` blanks our sheet too, as someone watching a replay with neither
sheet would see it. Both sides then know the same kind of thing, and the
symmetric model is right again.

| validation | full sheets (v4) | both blanked | lost (95% interval) |
|---|---|---|---|
| Reg M-A | 0.1851 | 0.1905 | +0.0055 (+0.0043 to +0.0067) |
| Reg M-B (pooled) | 0.1678 | 0.1815 | +0.0138 (+0.0081 to +0.0194) |

Both formats pass the gate. It loses more than `WP_public`, as it should, since our
own sheet is hidden too. It is a different question from the player's, so it is
not the product number. It may be useful for scoring replays of other people's
games where neither sheet is shown.

## Not done

- **Team preview.** In a real game without open sheets, team preview still shows
  all six species of both teams. The brief hides species until they
  appear, which is stricter than any real game. A team-preview variant would keep
  the twelve species and hide the rest.
- **Bo3 memory** is not carried in the blank run. Within a set, what game 1
  revealed would be public in game 2.
