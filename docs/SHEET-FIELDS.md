# Open team sheet fields — Week 3 Task 1

DEFINITIONS.md §12.2 flagged that its own sample was truncated and asked
for this to be verified properly rather than assumed. It was: 40 real
`|showteam|` logs (well over the requested 20), drawn from all four
corpus files - `regma`, `regmb`, `regmabo3`, `regmbbo3` - parsed field by
field against pokemon-showdown's own packed-team spec
(`pokemon-showdown/sim/teams.ts`'s `Team.unpack`), not guessed from
examples. 480 individual Pokémon sheets checked in total (10 logs × 2
sides × 6 Pokémon × 4 files).

## The finding that changes M4b's scope: it depends on the regulation

**Nature is not uniformly hidden.** It is populated in 100% of Reg M-B
sheets and 0% of Reg M-A sheets, across every log checked - not a mix, not
an occasional reveal, a clean split by regulation. Everything else is
identical between the two regs (see the table below). DEFINITIONS §12.2
assumed nature was hidden across the board; this is only half true.

## Field-by-field results

Checked against 240 Pokémon sheets per regulation (20 logs × 2 sides × 6):

| Field | Reg M-A | Reg M-B | Notes |
|---|---|---|---|
| `species` | 100% | 100% | Always present |
| `item` | 100% | 100% | Always present |
| `ability` | 100% | 100% | Always present |
| `moves` | 100% | 100% | Always present, always the full set |
| `level` | 100% | 100% | Always present (50, VGC's standard level) |
| `gender` | 90% | 84% | Blank only for genuinely genderless species (confirmed: Golurk, Aromatisse's line, etc.) - not a hidden-information gap, a fact about the Pokémon |
| `nature` | **0%** | **100%** | Regulation-dependent - see above |
| `evs` | 0% | 0% | Never populated, either regulation |
| `ivs` | 0% | 0% | Never populated, either regulation |
| `shiny` | 0% | 0% | Never populated, either regulation |
| `tera_type` | 0% | 0% | Never populated, either regulation - consistent with Tera being disabled entirely (see `docs/TERA-COVERAGE.md`) |
| `happiness` / `hp_type` / `pokeball` / `gigantamax` / `dynamax_level` | 0% | 0% | The entire trailing "misc" block is *absent*, not empty - see below |

## A precision worth keeping: absent vs. empty

The trailing misc block (`happiness,hp_type,pokeball,gigantamax,dynamax_level,tera_type`)
is not present as an empty placeholder when unused - pokemon-showdown's own
packer (`teams.ts`, the `pack` half of the same file) only writes it at all
when *any* of those fields is non-default. In every sheet checked, that
whole block - Tera type included - was missing from the string entirely,
not present-but-blank. Functionally the same as "hidden," but worth being
precise about for anyone parsing these lines directly rather than through
`wpa.sheets.parse_showteam_message`.

## What this means for M4b's scope

DEFINITIONS §12.2's expected residual hidden information was: bring-four
selection, Terastallisation, and "EV spreads, natures, IVs - inferred from
observed damage." Nature turns out not to need inference in Reg M-B at
all - it's simply given, the same way species and item are. The M4b belief
model's job in Reg M-A includes inferring nature from observed damage
rolls and speed order; in Reg M-B it does not, for that one field. Any
model or belief-tracking logic that assumes "regulation" is just a label
and treats sheet content as uniform across regs will get this wrong.

## Method

`wpa/sheets.py`'s `parse_showteam_message` parses the pipe-delimited
packed-team format directly against the field order and semantics defined
in `pokemon-showdown/sim/teams.ts`'s `Team.unpack` (read, not edited - the
usual additive-only rule). `tests/test_sheets.py` covers the parser
itself; `tests/test_sheet_fields.py` is a regression guard for the
regulation-split finding above, built on fixtures already checked into
the repo (`tests/fixtures/sample_battles.json` for Reg M-B,
`tests/fixtures/battles/early_forfeit.json` for Reg M-A) rather than new
large data files.
