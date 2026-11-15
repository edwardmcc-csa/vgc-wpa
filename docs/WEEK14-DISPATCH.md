# Week 14 — Dispatch Brief (Reg M-C, part 1: the rules, the data, the format)

**Status:** started 14 Nov 2026 on the PO's word ("Reg M-C now & update the pinned
code"). Drafted the same day from plan revision 4, Phase 2, and
`docs/REG-MC-GAPS.md`. **Done 15 Nov:** every box ticked; report in
`docs/WEEK14-REPORT.md`.
**Definition of done:** every checkbox ticked, `python -m pytest` green, one report
in prose.
**Gate (Phase 2, met over Weeks 14 and 15):** the same checks as Reg M-A and M-B
(calibration, beats-uniform, the resolver check) on Reg M-C's validation split.
This week ends with the resolver check on Reg M-C; Week 15 trains the models.

## Why

Reg M-C is the regulation in the app and on Showdown's ladder now (season M-8 runs
to 2 December), and the bot must play it. Our Showdown code is from 20 June: it
has the M-A and M-B rules but not M-C's. Showdown's current code has M-C and M-B,
but dropped M-A's rules on 9 September.

## Decisions (PO, 14 Nov 2026)

1. **Move on to Reg M-C now.** The Week 13 HP gate is carried as a known limit;
   the bot's own games (Phase 3) are where an HP miss can be told apart from a
   guessed spread.
2. **Update the pinned Showdown code.** Done as a second pinned copy for M-C
   (below), so M-A and M-B keep the rules their games were played under and their
   numbers stay comparable.
3. **DEFINITIONS revision 12 approved** (13:16): three formats; adding one never
   moves another format's sets; one pinned copy per format.

## Tasks

### Task 1 — Showdown's code for Reg M-C
- [x] **A second pinned copy, `pokemon-showdown-mc`:** Showdown's own repository
      at `7e74376` (13 Nov 2026), which has M-C (mod `champions`) and M-B. The
      June copy stays for M-A and M-B. `docs/PINNED-VERSIONS.md` and the
      version-drift check cover both. *(055b4b0)*
- [x] **Each format reads its rules from its own copy:** the dex, the moves, the
      durations of timed effects. *(b93f0ad)*
- [x] **The damage calculator** knows every M-C species, Mega, ability, item and
      move on the sheets. Two gaps are handled beside it, with tests: Flash Fire's
      and Stakeout's boosts, and an ally's Steely Spirit. *(f7d173d)*
- [x] Runbook: how to get and build the second copy. *(§27)*

### Task 2 — The Reg M-C games and statistics
- [x] **A downloader for Showdown's public replays** (`python -m
      wpa.fetch_replays`). Tests first, with no network. *(5de4c1c, 7163913)*
      60,000 games in 9 hours, 8 Oct to 14 Nov; no failed request.
- [x] **Smogon's usage statistics** for Reg M-C and its best-of-three,
      September and October.
- [x] **What we got:**
      - 27,120 sets from 8,851 players.
      - Ratings on 36% of games, median 1,174.
      - Every rules check passes on all 120,006 sheets.

### Task 3 — Reg M-C as a third format
- [x] **DEFINITIONS revision 12** (§15: three formats). Approved. *(5d285c1)*
- [x] `regmc` in the formats table *(b93f0ad)*. The re-parse of the M-C logs:
      118,702 of 120,000 game-sides parsed.
- [x] **Splits for M-C, made inside the format** (§13). *(b114bbe)*
      - 47,621 train games, 6,061 validation and 5,789 test.
      - 0 of 88,901 M-A and M-B games moved.
- [x] Sheet fields: what an M-C sheet shows (nature is shown, as in M-B).
      *(b14f672)*

### Task 4 — The resolver: the rules M-C adds
*(3760d8f, 2671ff9, f7d173d, 60b8665, 034f773)*
- [x] **Abilities:** Aura Guard, Seed Sower, Thermal Exchange, Emergency Exit,
      Liquid Ooze, Stakeout, Steely Spirit, Punk Rock, Grass Pelt, Rattled, Guard
      Dog; Moxie, Harvest, and Volt Absorb and Sap Sipper's heal and boost; Flash
      Fire's boost. Run Away needs nothing here.
- [x] **Items:** Air Balloon popping, the four terrain Seeds, Red Card, Normal
      Gem, Leek (Binding Band was done in Week 12).
- [x] **Moves:** Revival Blessing, Court Change, Glaive Rush, Meteor Assault's
      recharge, Milk Drink on an ally.
      - Jaw Lock is its damage only.
      - Octolock stays marked: 2 of 12,258 sets.
      - Found and done, in every format: Dragon Tail and Circle Throw's drag,
        Grassy Glide's priority, and a bind that ends with its source.
- [x] **Champions rules changed since June:** Emergency Exit and Wimp Out, and
      Eject Button, follow Champions; the rest reviewed, no change needed.
- [x] **The resolver check on M-C's validation games** (300 sets, 4,984 turns):
      99.9% fully modelled, 90.0% found. Partly modelled turns: Acupressure (2),
      Healing Wish, Pain Split, and a move aimed at an Ally Switch user's place.
      - Found on the way: half of all HP misses, in every format, come from the
        300-board cap.
      - At 3,000: 92.9% found on M-C (91.0% on M-A, 93.1% on M-B).
      - The PO decides the check's cap.

### Task 5 — Runbook and report
- [x] **A runbook for a new regulation** (§27).
- [x] One report in prose, per format, with a surprises section
      (`docs/WEEK14-REPORT.md`).

## Next (Week 15)

The models retrained on M-C: win probability (sheets shown and hidden),
choices, bring, leads, replacement, the opponent's strength; Phase 2's gate.

## For the PO

1. ~~Decide the resolver check's cap.~~ **Decided 15 Nov: 3,000** (`32f6af4`).
2. ~~Close the overnight PowerShell window.~~ Closed 15 Nov.
3. **Showdown's bot rules changed in October** (see the report of 14 Nov): this
   bears on Phases 5 and 6.
