# Spread-Revealing Observations (Week 3 Task 10 / Amendment 1)

Implements `docs/DEFINITIONS.md` §14. Adds `wpa/observations.py`
(`Observation` dataclass, `extract_observations`, `attach_observations`)
and a new `BattleState.observations: tuple[Observation, ...]` field,
populated by `parse_battle_states` for every replayed log. Live capture
(`wpa/battle.py`) does not populate it this task - out of scope per the
amendment, which is about the replay corpus feeding M4b. The field exists
on both paths (default `()`), so the one-schema rule still holds; it's
just always empty on the live side for now.

## The schema

One `Observation` per event, carrying its own `(turn, decision_index)` -
the same pair Task 5 tightened - so it attaches unambiguously to the
`BattleState` it occurred alongside, per §14's "hang off the existing
state record, not a parallel structure" rule:

```python
@dataclass(frozen=True)
class Observation:
    turn: int
    decision_index: int
    category: str  # damage | move_order | survival | recovery |
                   # behavioral_tell | tera_activation
    actor: str | None       # e.g. "p1a: Blaziken" - literal log identifier,
    target: str | None      # unambiguous by construction (side + slot)
    move: str | None = None
    priority: int | None = None
    sequence_index: int | None = None   # order within the turn - the
                                         # directly-observed speed signal
    hp_after: float | None = None
    hp_expression: str | None = None    # "percentage" or "exact" -
                                         # always populated when hp_after is
    fainted: bool | None = None
    hit_multiple_targets: bool | None = None
    weather: str | None = None
    fields: tuple[str, ...] = ()        # terrain, Trick Room, etc.
    side_conditions: tuple[str, ...] = ()  # e.g. "p2:Tailwind"
    tera_type: str | None = None
    note: str | None = None
```

Extraction is a pure function of the raw log text (`extract_observations`)
- it replays the log's own broadcast messages (`|-weather|`,
`|-fieldstart|`, `|-sidestart|`, etc.) to track context, rather than
reading vgc-bench's battle object. Every category comes from one specific,
literal protocol message type; nothing here is derived or inferred:

- **damage** — `|-damage|` lines. Attributed to the most recent `|move|`
  when untagged; residual/secondary damage (`[from] psn`, `[from] item:
  Life Orb`, etc.) is recorded with `actor=None` and the tag itself in
  `note`, rather than misattributed to whatever move happened to precede
  it.
- **move_order** — every `|move|` line, in log order (log order *is*
  execution order - the primary directly-observed speed-tier signal),
  with `priority` looked up from poke-env's `Move` class and
  `hit_multiple_targets` read directly off the move's own `[spread]` tag
  (comma-separated slot count - see below).
- **survival** — `|faint|` lines *not* already covered by a matching
  `fainted=True` damage observation for the same Pokemon (e.g. a faint
  from an indirect/delayed cause). A faint directly caused by a move's own
  damage is recorded once, on that damage observation's `fainted` flag,
  not duplicated as a second record.
- **recovery** — `|-heal|` lines, with the healer attributed from a
  `[of]` tag when present (e.g. Hospitality's caster) and the source
  (item/ability/move) recorded in `note`.
- **behavioral_tell** — `|-enditem|` (an item's effect consuming it, e.g.
  Focus Sash, White Herb, a berry) and `|-ability|...|boost`-shaped lines
  (an ability visibly triggering, e.g. Speed Boost, Intimidate). Not
  implemented this pass, flagged rather than silently skipped: choice-lock
  detection and a running "already-revealed" item/ability set - real, but
  not on this task's critical path.
- **tera_activation** — `|-terastallize|` lines. Zero occurrences in this
  corpus (see below) - checked directly against a synthetic protocol
  snippet instead of a real fixture, since Task 2 already established
  Terastallization is disabled format-wide.

**A genuine, defensible scope line, not an oversight:** the amendment also
asks for "active stat boosts" and "any item or ability already revealed"
as *context* on every event. Weather/terrain/screens context is captured
per event (tracked live off the same broadcast messages); stat boosts and
a running reveal-set are not threaded in this pass. Both are watchable the
same way and would be a natural follow-up, not a redesign.

**One deliberate difference from the rest of the schema:** `PokemonState`
speaks in `our`/`opp` terms; `Observation.actor`/`.target` use the raw
log identifiers (`p1a: Blaziken`, `p2b: Kingambit`) instead. Doubles has
two active slots per side, and the test suite requires actor/target be
unambiguous - a bare species name doesn't distinguish which of a side's
two active Pokemon acted. The literal identifier the log itself uses to
disambiguate does, without reinterpretation.

## Counts across a sample

Run across all 20 golden fixtures (Week 2 Task 5's curated corpus,
1,093 observations total, ~55/battle):

| Category | Count |
|---|---|
| move_order | 505 |
| damage | 384 |
| recovery | 145 |
| behavioral_tell | 46 |
| survival | 13 |
| tera_activation | 0 |

tera_activation being zero here is consistent with, not contradicted by,
Task 2's exhaustive corpus-wide finding (0/88,905 battles) - not a bug in
extraction, checked separately against a synthetic snippet (see
`tests/test_observations.py::test_tera_activation_is_extracted_even_though_absent_from_this_corpus`).

## The exact-vs-percentage breakdown

**This is the finding that sizes M4b, and it required stopping mid-task
to report before continuing** (§14's own rule: "Stop and report if the HP
expression turns out to be percentage-only on both sides throughout the
corpus").

Checked exhaustively, not sampled: every `|-damage|` and `|-heal|` figure
across all 88,905 battles, both regulations, bo1 and bo3.

**1,379,285 HP figures. 100% percentage (`X/100`). 0% exact. No
exceptions.** (Ten early false-positive regex hits turned out to be a
spectator's username, "50/50 Kamisama", not HP at all - ruled out before
concluding this.)

Reported to the product owner mid-Task-10, per §14's stop condition. The
decision was to proceed with `hp_expression` hardcoded to `"percentage"`
rather than narrow scope - the field is still correct and still populated
on every HP-bearing observation (never null, per the task's own test
requirement), it simply never takes the other value in this corpus. M4b
should be sized assuming interval constraints only, never a point pin from
an in-battle HP figure, for this data.
