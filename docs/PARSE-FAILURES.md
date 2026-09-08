# Known logs2trajs.py Parse Failures

Week 1 found that 6 (battle, role) pairs out of the 88,905-battle corpus
raise an exception when passed through `vgc_bench.logs2trajs.process_log`
(0.0034% of the corpus). Week 1's report described this as "all six trip
the same assertion... at `logs2trajs.py:259`."

**Correction:** that description is inaccurate. Only 2 of the 6 trip that
assertion. The other 4 come from two different battles and fail for a
different reason entirely. This was discovered during Week 3 Task 6 while
building a regression fixture from the original Week 1 finding, and is
being corrected here rather than carried forward silently.

The 6 pairs break down into 3 distinct battles, 2 roles each:

## 1. `gen9championsvgc2026regma-2617076884` (both roles) — `AssertionError`

Fails at `logs2trajs.py:259`:

```python
assert len(non_lead_revealed) == 2
```

This is the one Week 1 actually verified. `non_lead_revealed` is the set
of team slots revealed during teampreview that weren't part of the lead;
the parser assumes bo1 teampreview reveals exactly a pair of non-lead
Pokemon ahead of time, and this battle violates that assumption. Root
cause not investigated further this week — out of scope for Task 6, which
is regression coverage, not a parser fix.

## 2. `gen9championsvgc2026regmabo3-2631121423` (both roles) — `ValueError`

Fails at `logs2trajs.py:378`:

```python
win_start_index = log.index("|win|")
```

This battle has no `|win|` line because it has no winner: it is the
mutual-timeout tie already identified in Week 2 Task 3 ("All players are
inactive" — both players' clocks ran out at the same time). A tie is a
legitimate battle outcome that `process_log` has no code path for.

## 3. `gen9championsvgc2026regmabo3-2617355709` (both roles) — `ValueError`

Also fails at `logs2trajs.py:378`, same missing-`|win|` symptom as #2, but
a different underlying cause. This log has no win, tie, or forfeit message
of any kind — it ends abruptly mid-battle, immediately after `|turn|6`,
5,574 characters in (versus 10,000-12,000+ for the other two failing logs
and for ordinary complete battles of similar length). This looks like a
truncated or incompletely-scraped log rather than a real battle outcome.
Not investigated further this week — flagging it here as a data-quality
gap distinct from #2's legitimate tie, since conflating the two would
have been wrong.

## Regression coverage

`tests/fixtures/known_parser_failures.json` stores the raw log, timestamp,
role list, and documented error type/cause for all 3 battles.
`tests/test_known_parser_failures.py` asserts:

- exactly 3 battles / 6 (tag, role) pairs are recorded (fails if this
  count grows without a deliberate update),
- the two distinct error types are both still present (guards against
  re-flattening this into "one assertion" again),
- each recorded pair still raises the same exception type when replayed
  through `process_log`.

This is hermetic — the fixture embeds the full logs, so CI does not need
`battle_logs/`. It is a regression guard, not a fix: none of these 3
battles are corrected by this task, and Task 8's full re-parse is expected
to confirm the failure count is still exactly 6 (see Task 8 report).
