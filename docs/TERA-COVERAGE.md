# Terastallization coverage — Week 3 Task 2

## Plain statement: one problem, not two

Terastallization is absent from **both** the simulation path and the
replay corpus, and for the **same reason** — they are not two separate
problems with different costs, as the task framing anticipated. Both run
under the same "Champions" custom format, which disables Tera at the mod
level.

The proof is direct: a real replay log's own `|tier|` line reads
`[Gen 9 Champions] VGC 2026 Reg M-A` — the exact format string
`wpa/battle.py`'s `get_current_format()` builds for live simulation
(`format_map["ma"]` → `gen9championsvgc2026regma`). The historical corpus
was scraped from real ladder games played under this identical format, not
a different one. Whatever restricts Tera for one restricts it for both,
because it's the same format.

The restriction itself, confirmed at the code level in Week 2 and
reconfirmed here: `pokemon-showdown/data/mods/champions/scripts.ts`
overrides `canTerastallize(pokemon) { return null; }` unconditionally.
Every regulation built on this mod family (`champions` for M-B,
`championsregma` for M-A) inherits that override. Mega Evolution's
`canMegaEvo` is left fully functional in the same file — the format
substitutes one gimmick for the other, it doesn't just drop one.

## Quantified: exhaustive, not a sample

Zero Terastallization events in **88,905 of 88,905** parsed replay
battles — every log in the corpus, not an estimate from a sample:

| File | Battles | With `\|-terastallize\|` |
|---|---|---|
| `logs_gen9championsvgc2026regma.json` | 6,905 | 0 |
| `logs_gen9championsvgc2026regmb.json` | 324 | 0 |
| `logs_gen9championsvgc2026regmabo3.json` | 77,833 | 0 |
| `logs_gen9championsvgc2026regmbbo3.json` | 3,843 | 0 |
| **Total** | **88,905** | **0 (0.0000%)** |

Week 2's Task 5 report already found this on a search across the same
corpus; this task re-ran it as a full, exhaustive count rather than
relying on that earlier result, since a plain "documented finding" should
be checked again before being treated as settled.

## A format does exist on the pinned server that enables Tera in VGC doubles

`pokemon-showdown/config/formats.ts` defines `[Gen 9] VGC 2025 Reg I` and
`[Gen 9] VGC 2025 Reg J`:

```
name: "[Gen 9] VGC 2025 Reg J",
mod: 'gen9',
gameType: 'doubles',
ruleset: ['Flat Rules', '!! Adjust Level = 50', 'Min Source Gen = 9',
          'VGC Timer', 'Open Team Sheets', 'Limit Two Restricted'],
```

`mod: 'gen9'` is the standard mechanics mod, not `champions`/`championsregma`
- no `canTerastallize` override applies. The only mechanism on this server
that removes Tera from an otherwise-standard Gen 9 format is the opt-in
`Terastal Clause` rule (used elsewhere, e.g. `[Gen 9] Monotype`); neither
Reg I nor Reg J includes it. Both are real doubles VGC formats with open
team sheets, structurally identical in spirit to our M-A/M-B corpus,
except they run the actual game mechanics rather than the Champions
mod's substitution. These are the real Pokémon Company regulations that
chronologically precede the fictional "2026" Champions regs our corpus
uses.

## What this means for the fixture corpus

Nothing changes about it as a result of this task - per the dispatch,
Task 2 investigates, it does not act. But plainly: the Week 2 fixture
corpus's "at least one Terastallisation" requirement could not be met
with a real Tera event under the format actually in use, because no such
event exists anywhere in 88,905 real battles, and none can be simulated
live under that format either. The Mega Evolution substitution already
made (with product owner sign-off, see Week 2's Task 5 report and
`wpa/state.py`'s generic `gimmick` field) is not a workaround for a
sampling gap - it's the only gimmick this format structurally has. If Tera
coverage is wanted in the fixture corpus or in future simulation, it
would require switching to a format like Reg I/J (a real product decision
with training-corpus implications, not a fixture-regeneration tweak) -
raised here, not decided here.

## Open question surfaced, not resolved here

Given a real Tera-enabled doubles format exists on the pinned server, the
product owner may want to weigh in on whether the training corpus should
eventually include Tera-enabled regulations (Reg I/J or a future Champions
revision that restores it) alongside or instead of the current Tera-less
M-A/M-B/M-C. That's a scope question for M3/M4, not something this task
decides.
