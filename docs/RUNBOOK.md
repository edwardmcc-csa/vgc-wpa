# Runbook

This is for anyone who needs to start the local battle server, run the log
parser, run the tests, split the data, or run the metric report, and has
never touched this repository before. You
do not need to know how to write code to follow this - every command is
meant to be copied and pasted exactly as written, from a terminal opened in
the repo's top-level folder (the one containing `pyproject.toml`).

If a command fails, the "If something goes wrong" section near the bottom
covers the problems we've actually hit. If your problem isn't there, stop
and ask rather than guessing - see `docs/WEEK1-DISPATCH.md`'s rules of
engagement.

Windows notes are called out explicitly; everything else works the same on
Windows (in Git Bash or PowerShell), macOS, and Linux.

---

## 1. One-time setup

You only need to do this once per computer.

1. **Install prerequisites**, if you don't already have them:
   - Python 3.10 or newer
   - Node.js (any recent version)
   - Git

2. **Get the code, including its submodule.** This repository depends on a
   specific, pinned copy of Pokémon Showdown, kept as what Git calls a
   "submodule" - a second repository nested inside this one, checked out to
   an exact commit. If you already cloned this repo without its submodule,
   run this from the repo root:
   ```
   git submodule update --init --recursive
   ```
   This downloads the `pokemon-showdown/` folder. Do not `git clone` the
   Pokémon Showdown server separately - it has to be this exact pinned
   version, recorded in `docs/PINNED-VERSIONS.md`.

3. **Install the Showdown server's own dependencies:**
   ```
   cd pokemon-showdown
   npm install
   cd ..
   ```
   (Run each line one at a time. `cd ..` returns you to the repo root
   afterwards - you'll need to be there for the rest of this document.)

4. **Create the server's config file.** This file is intentionally not
   checked into Git (it's the kind of file people customize per-machine), so
   it needs to be created once from the provided example:
   - Windows (PowerShell): `copy pokemon-showdown\config\config-example.js pokemon-showdown\config\config.js`
   - Windows (Git Bash) / macOS / Linux: `cp pokemon-showdown/config/config-example.js pokemon-showdown/config/config.js`

   You don't need to edit this file - the defaults (including port 8000)
   are what everything else in this document expects.

5. **Install the Python dependencies:**
   ```
   pip install -e ".[dev]"
   ```
   This installs everything needed to run the parser and the tests. If this
   command fails specifically because of a package called `open-spiel`, that
   is a known issue (see "If something goes wrong" below) - it is not
   required for anything in this runbook.

That's the whole one-time setup. Everything below can be run any number of
times after this.

---

## 2. Starting the local battle server

Some of the tests, and some future work on this project, need a local copy
of the Pokémon Showdown battle server running on your own machine (not the
public pokemonshowdown.com site). To start it:

```
cd pokemon-showdown
node pokemon-showdown start --no-security
```

Wait for output that looks like this:
```
RESTORE CHATROOM: lobby
RESTORE CHATROOM: staff
```

That means it's running and listening on `http://localhost:8000`. Leave
that terminal window open for as long as you need the server - closing it
(or pressing Ctrl+C in it) stops the server. Open a *new* terminal window,
back in the repo root, for anything else in this document.

You do **not** need this server running to run the parser (Section 3) or
the automated tests (Section 4) - those replay saved battle logs offline.
It matters if you're doing anything involving live battles.

---

## 3. Getting battle data and running the parser

The parser turns raw Pokémon Showdown battle logs into the structured data
files ("trajectories") used downstream. This section downloads a
ready-made set of logs and runs the parser over them.

1. **Download the pre-scraped battle logs.** From the repo root, run:
   ```
   python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='cameronangliss/vgc-battle-logs', repo_type='dataset', local_dir='battle_logs')"
   ```
   This downloads about 600MB into a new `battle_logs/` folder. It also
   adds a `README.md` file, a `.gitattributes` file, and a hidden `.cache`
   folder that aren't battle logs - delete those three (the two files and
   the whole `.cache` folder) from `battle_logs/` afterwards, or the parser
   will crash trying to read them as if they were log files.

2. **Run the parser:**
   ```
   python -m vgc_bench.logs2trajs --num_workers 4
   ```
   `--num_workers 4` tells it to use 4 CPU cores at once. Set it to roughly
   the number of cores your computer has, but see the memory warning below
   before setting it any higher.

   This takes a while - on a 16-core machine, parsing the full dataset
   (about 89,000 battles) took about an hour. You'll see progress lines
   like:
   ```
   processing 6905 logs_gen9championsvgc2026regma logs...
   prepared 13808 trajectories with 131910 transitions (0 discarded trajs, 2 failed traj reads)
   ```
   A handful of "failed traj reads" out of tens of thousands is normal and
   expected (some real battle logs have quirks the parser doesn't handle -
   see `docs/WEEK1-DISPATCH.md` for the threshold that would mean something
   is actually wrong: more than 5% failing).

   The output lands in a new `trajs/` folder as many small `.pkl` files -
   these are the structured, ready-to-use battle records.

   **Memory warning:** one of the four log files
   (`logs_gen9championsvgc2026regmabo3.json`) is much larger than the
   others and holds every battle in memory before saving anything to disk.
   On a machine with less than about 20GB of RAM, running the command above
   over the *full* dataset in one go can crash partway through (the
   computer runs out of memory, not a bug in your command). If that
   happens:
   - Lower `--num_workers` (try 2), which reduces how much is held in
     memory at once, and try again.
   - If it still crashes, ask an engineer to run it in smaller batches
     instead of the whole file at once - we do have a proven way to do
     this without editing any of the parser's own code, it's just more
     involved than a single command.

---

## 4. Running the automated tests

This checks that nothing is broken. From the repo root:

```
python -m pytest
```

(Not just `pytest` on its own - depending on how Python is set up on your
machine, the plain `pytest` command may not be found even though it's
installed. `python -m pytest` always works.)

A healthy run ends with a line like:
```
86 passed, 5 skipped in 21.23s
```

"Skipped" tests are expected - a few tests only run when extra setup (like
an LLM API key) is present, and are intentionally skipped otherwise.
Anything that says "failed" or "error" means something is actually wrong -
stop and report it rather than re-running things or guessing at a fix
(see the dispatch's rules of engagement).

You don't need `battle_logs/` or `trajs/` (Section 3) to run the tests -
they use a small set of sample battles that are already checked into the
repository, specifically so the tests work without any of that setup.

The same tests run automatically in GitHub Actions on every change pushed
to this repository - look for a green checkmark (or red X) next to the
latest commit on GitHub, or check the "Actions" tab.

---

## 5. Running a live battle

Sections 3-4 work from saved battle logs. This section actually plays a
battle: two computer-controlled players connect to your local server
(Section 2) and play a real VGC doubles game to completion, move by move.

1. Make sure the local server (Section 2) is running in its own terminal
   window first. This will not work without it.
2. In a different terminal, from the repo root:
   ```
   python -m wpa.battle
   ```
3. You'll see one line of output once the battle finishes, for example:
   ```
   battle battle-gen9championsvgc2026regma-1294: finished=True, winner=RandomPlayer 1
   ```
   That's it - a full battle, played and decided, in a few seconds.

Both players choose moves randomly (they're a simple baseline, not a real
strategy) - this proves the plumbing works end to end, not that the players
are any good. Which exact regulation/format they play is read from
project configuration, not typed into this command - see
`docs/DEFINITIONS.md` if you want to know which one is currently active.

---

## 6. Running the volume test

This plays 100 battles back to back (instead of just one) and checks that
enough of them finish without crashing. It's the same idea as Section 5,
just at scale, and it also needs the local server running.

1. Make sure the local server (Section 2) is running.
2. From the repo root:
   ```
   python -m pytest -m volume_full -v
   ```
3. This takes about a minute (100 real battles played one after another).
   A healthy result looks like:
   ```
   tests/test_battle_volume.py::test_hundred_battles_stay_within_dispatch_failure_threshold PASSED
   ```

This specific test is normally skipped when you just run `python -m
pytest` (Section 4) - a smaller 10-battle version runs instead, so the
everyday test command stays fast. `-m volume_full` is what asks for the
full 100-battle version specifically.

If this reports more than 2 failed battles out of 100, stop and report it
rather than re-running - see the Week 2 dispatch's rules of engagement.

---

## 7. Regenerating fixtures

`tests/fixtures/battles/` holds 20 saved example battles used by the
automated tests - each one is a real battle's log plus the turn-by-turn
information extracted from it (see `tests/fixtures/README.md` for what
each one is and why it was chosen). You don't need to touch these to do
normal work; this section is for the rare case where one needs
regenerating (for example, if the extraction logic in `wpa/state.py`
changes and the saved results need to be refreshed).

Given a battle log you already have (for example, one from
`battle_logs/` - see Section 3 to download those), this saves it as a
fixture:

```
python -c "
import asyncio, json
from threading import Thread
from pathlib import Path
from wpa.fixtures import build_fixture, save_fixture

loop = asyncio.new_event_loop()
Thread(target=loop.run_forever, daemon=True).start()

logs = json.load(open('battle_logs/logs_gen9championsvgc2026regmb.json', encoding='utf-8'))
tag = next(iter(logs))
timestamp, log = logs[tag]

fixture = build_fixture(tag, timestamp, 'p1', log, loop)
path = save_fixture(fixture, Path('tests/fixtures/battles'), 'my_fixture_name')
print('wrote', path, 'with', len(fixture.states), 'states')
loop.call_soon_threadsafe(loop.stop)
"
```

Change the file name, the `tag` selection, and `my_fixture_name` to
whatever battle and name you actually want. This does not need the local
server running - it works from a saved log, the same way Section 3's
parser does.

This does **not** regenerate the exact 20 fixtures already in the repo -
which specific battles were chosen, and why, is a curation decision
documented in `tests/fixtures/README.md`, not something a single command
reproduces. This command is the mechanical part: turning one battle log
you've already picked into a saved fixture file.

---

## 8. Where things live

- `pokemon-showdown/` - the pinned battle server (Section 2). Not ours;
  don't edit it.
- `vgc_bench/` - the original vgc-bench code we forked. Not ours to edit
  either, so that we can pull in their future fixes cleanly.
- `wpa/` - our own code, kept separate from `vgc_bench/` for that reason.
- `battle_logs/` - downloaded raw battle logs (Section 3). Not checked into
  Git - it's regenerated by the download command, and it's large.
- `trajs/` - the parser's output (Section 3). Also not checked into Git,
  also regenerated, also large.
- `wpa_states/` - the output of the re-parse (Section 9): our own, much
  smaller records, one file per battle per player. Not checked into Git,
  also regenerated.
- `splits.json` - the output of the splitter (Section 10): which split
  every game belongs to. Not checked into Git, also regenerated.
- `tests/` - our own tests (for the code in `wpa/`), including
  `tests/fixtures/battles/` - the 20 saved example battles from Section 7,
  documented in `tests/fixtures/README.md`.
- `unit_tests/` and `integration_tests/` - the original vgc-bench project's
  own tests.
- `docs/` - documents like this one, plus the project's pinned dependency
  versions (`PINNED-VERSIONS.md`) and the original planning documents.

---

## 9. Running the re-parse and checking set fields

The Section 3 parser produces vgc-bench's own format. The **re-parse**
produces ours: turn-by-turn battle records from `wpa/state.py`, including
the best-of-three set information (which set a game belongs to, which game
of the set it is, and the set score going into it). It reads the same
`battle_logs/` folder from Section 3, so do that section's download step
first. It does not need the local server running.

1. **Run the tests first.** From the repo root:
   ```
   python -m pytest tests/test_reparse.py
   ```
   Every line should end in "passed". If anything fails, stop and write down
   the exact error message - do not start the re-parse.

2. **Run the re-parse:**
   ```
   python -m wpa.reparse --num_workers 4
   ```
   This takes about an hour. Leave the window open. It prints a line when it
   starts each log file and another when it finishes it, for example:
   ```
   parsing 6905 logs_gen9championsvgc2026regma logs...
     13808/13810 succeeded, 2 failed
   ```
   The output lands in a new `wpa_states/` folder, one `.json` file per
   battle per player (`-p1` and `-p2`). Running it again is safe: each file
   is simply overwritten. Only run it again if something went wrong or the
   project has agreed to a new one - the full run is deliberately done once
   per schema change.

   If the computer runs out of memory, lower `--num_workers` (try 2). The
   re-parse saves each battle as soon as it finishes instead of holding the
   whole file in memory, so it is far less likely to hit the Section 3
   memory problem.

3. **Read the summary at the end.** When it finishes it prints a block
   starting `=== wpa re-parse summary ===`. The lines that matter:
   - `failed:` - the count of battles that could not be parsed. On the
     real data this is **2** (one battle, counted once per player:
     `gen9championsvgc2026regma-2617076884`). More than 5% of `attempted`
     means something is wrong - stop and report it.
   - `bo3 states missing set_id` and `bo3 states missing game_index` -
     on the real data both are **71**, not 0. Those 71 states are one
     best-of-5 match (three games) that sits in the best-of-3 file; it is
     outside the format and is expected. Any other number means set
     information was lost - run the check in step 4.
   - `bo3 states missing score` - the same 71 on the real data. A game 2
     whose game 1 log is not in the data can add a few more; that is a
     known, documented gap.
   - `wall clock` and `bytes written` - how long it took and how much disk
     it used. Copy these into your report.

4. **Check every file's set fields.** After the re-parse, run:
   ```
   python -m wpa.check_set_fields
   ```
   It reads all the best-of-three files in `wpa_states/` (a few minutes) and
   prints a `=== wpa set-field check ===` block. On the real data it reports
   71 states missing each field, in 6 files, all from the best-of-5 match
   above: `gen9championsvgc2026regmabo3-2614987695`, `-2614990439` and
   `-2614996363` (each with a `-p1` and `-p2` file). Anything beyond those
   6 files means set information was lost - stop and report it. It only
   reads files; it never changes them.

5. **Look at one record's set fields.** Any bo3 file works. This prints how
   many states are in the file, then the set fields for the first four:
   ```
   python -c "import json; s=json.load(open('wpa_states/gen9championsvgc2026regmabo3-2580300180-p1.json')); print(len(s), 'states'); [print('turn', x['turn'], 'decision', x['decision_index'], 'set', x['set_id'], 'game', x['game_index'], 'score', x['set_score_entering_game']) for x in s[:4]]"
   ```
   Replace the file name with any other `...bo3...` file in `wpa_states/`.
   A good result looks like:
   ```
   3 states
   turn 0 decision 0 set gen9championsvgc2026regmabo3-2580300179 game 1 score [0, 0]
   turn 1 decision 0 set gen9championsvgc2026regmabo3-2580300179 game 1 score [0, 0]
   turn 1 decision 1 set gen9championsvgc2026regmabo3-2580300179 game 1 score [0, 0]
   ```
   What each field means:
   - `set` - the best-of-three this game belongs to. Every game in the same
     set shows the same value.
   - `game` - 1, 2, or 3.
   - `score` - games won by each side *before* this game starts, so game 1
     is always `[0, 0]`.

   Files whose name does not contain `bo3` are single games and show `None`
   for all three fields. That is correct, not a bug.

---

## 10. Splitting the data into train, validation and test

Before we can say whether any model is good, some games have to be kept
hidden from it. This step decides, once and for good, which games are used
for what:

- **train** - what a model learns from (about 80%)
- **validation** - what we measure and tune against (about 10%)
- **test** - the final exam, looked at as rarely as possible (about 10%)

The important word is *leak-proof*. If one half of a best-of-three set were
in train and the other half in test, the model would be tested on a match it
has partly seen, and every score would look better than it really is. So the
splitter keeps things together: both players' views of the same game, every
game of the same best-of-three set, and games that share the same pair of
teams all land in the same split. It also does this separately for each
format (Regulation M-A and Regulation M-B are never mixed - see
`docs/DEFINITIONS.md` section 15).

It reads `wpa_states/` from Section 9, so do that first. It does not need
the local server.

1. **Run the tests first.** From the repo root:
   ```
   python -m pytest tests\test_formats.py tests\test_splits.py tests\test_archetypes.py
   ```
   The last line should say `84 passed`, with nothing failed or skipped. If
   anything fails, stop and write down the exact error message.

2. **Run the splitter:**
   ```
   python -m wpa.splits --out splits.json
   ```
   It reads about 178,000 files, so expect several minutes, possibly
   longer on a slow disk. Leave the window open. If the computer struggles,
   add `--num_workers 2`.

   On the real data the first run printed this:
   ```
   === wpa splits ===
   proportions: train 0.80, validation 0.10, test 0.10 (salt wpa-splits-v1)
   dropped: 6 files, 71 states (best-of-three files with no set information)
   regma:
     train       40502 units (79.8%),  67508 games, 135016 files,  1396571 states
     validation   5167 units (10.2%),   8694 games,  17388 files,   178823 states
     test         5108 units (10.1%),   8532 games,  17064 files,   175775 states
     independent groups: 48022 (of 50777 units); largest group: 28 units
   regmb:
     train        1824 units (80.7%),   3366 games,   6732 files,    69761 states
     validation    199 units ( 8.8%),    366 games,    732 files,     7799 states
     test          237 units (10.5%),    435 games,    870 files,     9254 states
     independent groups: 2218 (of 2260 units); largest group: 6 units
   wrote splits.json
   ```
   If your numbers differ, the data in `wpa_states/` is different from the
   data this runbook was written against. That is not necessarily a problem,
   but note it in your report.

3. **How to read it.**
   - A **unit** is the thing that is never split: one best-of-three set
     counts as one unit, and a single game counts as one unit. A game is one
     battle; it has two **files** (one per player's point of view); a
     **state** is one decision point within it.
   - The percentages are close to 80 / 10 / 10 but not exact, and the
     smaller format wanders more (Regulation M-B validation is 8.8%). That
     is expected: whole groups of linked games move together, so the
     splitter cannot slice the data to the exact percent. Do not try to
     "fix" it.
   - `dropped: 6 files, 71 states` is the best-of-5 match from Section 9. It
     is outside the format, so it is left out of every split. Any other
     number here means something changed - stop and report it.
   - **Independent groups** is how many separate clumps of linked games
     there are. Many small groups is good; one giant group would make the
     split impossible.

4. **What `splits.json` is.** It lists which split every game belongs to,
   and it is what the metric report (Section 11) reads. Running the
   splitter again on the same data gives the identical answer every time,
   so it is safe to delete and regenerate. Do **not** commit it to Git, and
   do **not** put it inside `wpa_states/` (see "If something goes wrong").
   If `wpa_states/` changes, for example after a new re-parse, run the
   splitter again and use the new file - never mix an old `splits.json`
   with new data.

5. **Leave the settings alone.** `--salt`, `--train`, `--validation` and
   `--test` change who lands in which split, which makes every earlier
   number impossible to compare with later ones. Only change them if the
   project has agreed to.

There is also an experimental `--archetype_holdout 0.1` option that sets
aside whole kinds of team (instead of random games) as the test set, to
check how a model copes with teams it has never seen. That definition is a
*proposal* awaiting sign-off - see `docs/WEEK4-DISPATCH.md` - so do not use
numbers from it for anything official.

---

## 11. Running the metric report (the v0 baseline)

This is the project's yardstick. A deliberately simple, hand-written
predictor - no machine learning - guesses each side's chance of winning at
every decision point, and the report grades those guesses against what
actually happened. Any later, smarter model has to beat these numbers to
earn its place. The report is always **per format**; the two formats are
never averaged into one headline number.

The predictor is simple: count each side's remaining health (plus one point
for every Pokémon it brought that we haven't seen yet) and turn the
difference into a percentage. It is known to ignore many things - timers
such as Tailwind and Trick Room, speed, and the team sheet - and it prints a
list of those at the top of the report.

It needs `wpa_states/` (Section 9) and `splits.json` (Section 10). It does
not need the local server.

1. **Run the tests first:**
   ```
   python -m pytest tests\test_metrics.py tests\test_baseline.py
   ```
   The last line should say `75 passed`. (On a computer without the
   `poke_env` package two tests are skipped, giving `73 passed, 2 skipped`;
   that is fine too.) Anything "failed" means stop and report it.

2. **Run the report:**
   ```
   python -m wpa.baseline --splits splits.json
   ```
   It reads the validation games only (about 18,000 files), so it is
   quicker than the splitter - expect several minutes. If you leave out
   `--splits splits.json` it works the splits out for itself first, which
   adds the splitter's whole running time, so use the file.

   The report starts with the baseline's list of known blind spots, then one
   block per format. Here is the Regulation M-A part from the first run
   (the trend table is shortened):
   ```
   regma: 161435 undecided states in 8694 games (17388 decided states set aside)
     Brier 0.2198 (coin flip 0.25; skill +0.121); including decided states 0.1984
     0.0-0.1  n=592      predicted 0.078  observed 0.064  gap 0.014
     0.1-0.2  n=5360     predicted 0.160  observed 0.132  gap 0.028
     0.2-0.3  n=13107    predicted 0.257  observed 0.257  gap 0.000
     0.3-0.4  n=17276    predicted 0.352  observed 0.372  gap 0.020
     0.4-0.5  n=20228    predicted 0.450  observed 0.486  gap 0.035
     0.5-0.6  n=71258    predicted 0.514  observed 0.519  gap 0.005
     0.6-0.7  n=16312    predicted 0.647  observed 0.709  gap 0.061  <-- outside tolerance
     0.7-0.8  n=11461    predicted 0.743  observed 0.817  gap 0.074  <-- outside tolerance
     0.8-0.9  n=5136     predicted 0.840  observed 0.921  gap 0.080  <-- outside tolerance
     0.9-1.0  n=705      predicted 0.924  observed 0.974  gap 0.051  <-- outside tolerance
     calibration bins outside tolerance: 4
     trend (reported, not a gate): mean predicted WP by Pokemon remaining ...
       ...
     trend: WP rose in 100% of 12 'opponent loses one Pokemon' steps
   ```

3. **How to read it.**
   - **Brier** is the average squared miss between the predicted chance and
     what happened (1 for a win, 0 for a loss). Lower is better. A predictor
     that always says "50%" scores 0.25, which is printed as the coin flip.
     **Skill** is how far below that coin flip we are: 0 means no better
     than guessing, higher is better. Here +0.121 means "somewhat better
     than a coin flip", not "good".
   - **Undecided vs decided states.** Once a game is already over (nobody
     has a Pokémon left on one side), predicting the winner is trivial. The
     headline Brier leaves those states out so the baseline does not get
     credit for easy questions; the number "including decided states" is
     there for completeness only.
   - **The calibration table** asks: when the predictor said "60 to 70%",
     did that side really win about 65% of the time? Each row is one band of
     predictions, with how many states fell in it (`n`), the average
     prediction, the real win rate (`observed`) and the difference (`gap`).
     A row is flagged `<-- outside tolerance` when the gap is bigger than
     the tolerance. The tolerance of 0.05 is a placeholder to show how the
     flag works; the project has not agreed a real one. Bands with fewer
     than 100 states say `(too few to judge)` and are never flagged.
   - **The pattern to notice:** in every flagged row the observed rate is
     higher than predicted, so the baseline is under-confident whenever a
     side is ahead.
   - `n` counts states, and states from the same game are not independent,
     so the real amount of evidence is closer to the number of games.
   - **`SMALL SAMPLE`** appears when a format has fewer than 500 games in
     the split (Regulation M-B does). Read every number for that format with
     that in mind.
   - **Trend** checks that the prediction goes up when the opponent loses a
     Pokémon. It is reported, not pass/fail.
   - The **POOLED** line at the very end is a secondary check only. It is
     never a headline.

4. **Numbers to expect.** On the first run, with the default settings and the
   splits from Section 10:

   | Format | States scored | Games | Brier | Skill |
   |---|---|---|---|---|
   | Regulation M-A | 161,435 | 8,694 | 0.2198 | +0.121 |
   | Regulation M-B | 7,067 | 366 | 0.2143 | +0.143 |

   The baseline is hand-written and deterministic, so with the same data and
   the same `splits.json` you should get these exact figures. If you do not,
   stop and report it rather than re-running.

5. **Leave the other options alone.** `--split test` scores the final exam;
   look at it only when asked to, never to tune anything. `--k`,
   `--tolerance` and `--min_count` change the baseline's scale and the report's
   thresholds - the defaults are the agreed ones.

---

## 12. Checking your changes before you push

Every push to GitHub runs three style and type checks (the "lint" job in
the Actions tab), and the push shows a red X if any of them fails. You can
run the same checks yourself first. They need the dev install from Section
1 (`pip install -e ".[dev]"`), which installs the exact versions GitHub
uses. Use the `python -m` form so it works even if the plain commands are
not found on your PATH:

```
python -m ruff check .
python -m ruff format --check .
python -m pyright
```

- `ruff check` looks for mistakes such as unused imports and lines over 88
  characters. A healthy run ends `All checks passed!`.
- `ruff format --check` checks the code layout. A healthy run says every
  file is "already formatted". If it lists files it "would reformat", run
  `python -m ruff format .`, then run the tests again, then commit the
  result.
- `pyright` is the type checker. The first run downloads a component and can
  take a minute. Errors that only say an import of `poke_env` or
  `imitation` "could not be resolved" mean the packages are not installed in
  your environment - they are not a problem in the code. Anything else is a
  real error.

Then run `python -m pytest` (Section 4) as usual.

---

## 13. Timers: how long each effect lasts

Three commands, all from the repo folder. The Showdown submodule must be
built (the `dist` folder exists) and Node must be installed.

**Rebuild the duration table** (`docs/DURATIONS.md`). A test fails if this file
is out of date, so run it whenever the Showdown submodule or `wpa/durations.py`
changes:

```
python -m wpa.durations --out docs/DURATIONS.md
```

**Check the table against the battle logs.** This reads every game, so it
takes a long time on one machine (the full corpus is about 89,000 games). To
try it quickly, add `--shard 0/8`, which reads every eighth game:

```
python -m wpa.timers --shard 0/8 --markdown timers-check.md
```

A healthy run ends with `wrote timers-check.md`. Open the file: the
"Unexplained" column should be a fraction of a percent for nearly every row.
The full result from 27 Oct 2026 is `docs/DURATIONS-VALIDATION.md`.

**Write the timer side file** that training will read. One line per game, with
the timers in force at each turn, built from start turns and the duration table
only (nothing from the future):

```
python -m wpa.timers --timers-out timers.jsonl.gz
```

A healthy run ends `wrote 88905 games to timers.jsonl.gz` (the number is how
many games are in `battle_logs`). The file is about 6.5 MB. Like `splits.json`,
it is generated, so do not commit it. It holds the timers at the start of every
turn and at every decision point each player has in `wpa_states/`.

**Check that the timers line up with the stored states.** This reads one game
in 100 from the logs and compares them with the files in `wpa_states/`:

```
python -m wpa.timer_join --one-in 100
```

A healthy run says `aligned ... of ... state files (100.00%)` for each format,
and the `unexplained` figure on every effect line is `0.0%`. Anything else,
stop and report it. Expect several minutes: it reads every log file once.

**Write the team-sheet side file** (Week 5): every game's two open team sheets,
used for the model's team features. About a minute:

```
python -m wpa.team_sheets --out sheets.jsonl.gz
```

It prints, per format, how many teams have Tailwind, Trick Room, each weather
and so on, then `wrote 88905 games to sheets.jsonl.gz`. Like the timer file, it
is generated and not committed.

---

## 14. The win probability model (Week 5)

This builds the learned model (v1) and grades it against the Week 4 baseline
(v0). Everything is per format. It needs `wpa_states/`, `splits.json`
(Section 10), `timers.jsonl.gz` and `sheets.jsonl.gz` (Section 13), Node and the
built Showdown submodule.

1. **Install the model library** (once):
   ```
   python -m pip install -e ".[model]"
   python -m pytest tests\test_gbm.py tests\test_model.py tests\test_evaluate.py
   ```
   The last line should say `passed` with nothing failed.

2. **Build the feature table.** One row per decision point. It is split into 64
   parts so a run can stop and restart. On the development machine it took about
   an hour; more workers is faster if your computer has the cores:
   ```
   python -m wpa.features --shards 64 --workers 4
   ```
   Each part prints a line such as
   `shard 0: {'games': 1394, 'files': 2788, 'misaligned': 0, ...}`.
   `misaligned` should be 0 or close to it (4 files in the whole corpus on 30 Oct).
   The result is the `features` folder (about 60 MB). It is generated, not
   committed.

3. **Train.** The four settings in the fixed grid are tried, the validation split
   chooses the number of rounds. The `--sample 0.2` option trains Reg M-A on 20%
   of its sets; leave it out to use all of them (better, slower):
   ```
   python -m wpa.evaluate train --format regmb
   python -m wpa.evaluate train --format regma --sample 0.2
   python -m wpa.evaluate select --format regmb
   python -m wpa.evaluate select --format regma
   ```
   If a run prints `not finished ... run the same command again`, do exactly
   that: it carries on where it stopped. `select` prints which setting won and
   whether the model was recalibrated.

4. **Ablation** (which feature groups earn their place), then the report:
   ```
   python -m wpa.evaluate ablation --format regmb
   python -m wpa.evaluate ablation --format regma --sample 0.2
   python -m wpa.evaluate report
   ```
   The report is also saved as `models\report.txt`. Each line is a Brier with a
   95% interval in brackets. The interval comes from resampling whole sets, so it
   is honest about how much evidence there is. `minus v0` below zero means v1 is
   better; if its whole interval is below zero, v1 is better beyond doubt.

5. **The gate** (pass or fail on the validation split):
   ```
   python -m wpa.evaluate check
   ```
   It ends `gate: passed` or `gate: FAILED` with the reasons above it.

6. **The test split - once.** This is the final, untouched number. Run it only
   when everything above is settled; every run is logged with the date and git
   commit in `models\test_openings.json`:
   ```
   python -m wpa.evaluate final
   ```

7. **Optional comparisons:**
   ```
   python -m wpa.evaluate pooled --sample 0.2
   python -m wpa.claims
   ```
   `pooled` trains one model on both formats with a format flag and scores it on
   Reg M-B only (add `--test` to score the test split too; that counts as another
   opening). `claims` scores the expert-claim positions (report only).

---

## 15. The v2 model on our own decision table (Week 6)

v2 is built from our own decision table (`wpa/decisions.py`, see
`docs/DECISION-TABLE.md`) instead of the parser's stored states, and adds the
speed features (group F). It needs `splits.json`, the `battle_logs` folder, Node
and the built Showdown submodule, and the model library from Section 14 step 1.

1. **Split the logs into 64 parts** (once; about 90 MB, not committed):
   ```
   python -m wpa.features --split-logs logs_shards --shards 64
   ```
   It ends with a line such as `{'games': 88901, 'unassigned': ...}`.

2. **Build the v2 feature table** (about 85 MB, not committed):
   ```
   python -m wpa.features --from-logs logs_shards --out features_v2 --shards 64 --workers 4
   ```
   Each part prints `shard N: {...}`. If it stops, add `--only 20-63` (the parts
   still missing) and run it again.

3. **Train.** One command per model. `--sample 0.2` trains on 20% of the Reg M-A
   sets; that is what fits on the development machine and what the Week 6 report
   uses. Leave it out to train on everything (see step 7):
   ```
   python -m wpa.evaluate v2-train --format regma --groups ABCDEF --sample 0.2 --features features_v2 --models models_v2
   python -m wpa.evaluate v2-train --format regma --groups ABCDE --sample 0.2 --features features_v2 --models models_v2
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEF --sample 0.2 --features features_v2 --models models_v2
   python -m wpa.evaluate v2-train --format pooled --groups ABCDE --sample 0.2 --features features_v2 --models models_v2
   ```
   `pooled` is the Reg M-B model: trained on Reg M-A and Reg M-B together with a
   format flag, judged on Reg M-B only. `ABCDE` is the same model without speed,
   kept only to measure what speed adds. Each command ends
   `validation Brier 0.19.. after N rounds`. If one prints `not finished ... run
   the same command again`, do exactly that.

4. **Report and gate** (validation split):
   ```
   python -m wpa.evaluate v2-report --features features_v2 --models models_v2
   ```
   For each format: the Brier with its 95% interval, v0, `model - v0` (below zero
   means v2 is better), the calibration table, and what adding speed changes. It
   ends `gate: passed` or `gate: FAILED`. Saved as `models_v2\report.txt`.

5. **The test split - once.** Logged in `models\test_openings.json` like every
   opening:
   ```
   python -m wpa.evaluate v2-final --features features_v2 --models models_v2
   ```

6. **Expert claims** (report only, about 4 minutes):
   ```
   python -m wpa.claims_v2 scan
   python -m wpa.claims_v2 report
   ```
   Saved as `claims_v2\report.txt`. `docs/EXPERT-CLAIMS-RESULTS.md` explains it.

7. **Training Reg M-A on all of its sets (your computer).** The development machine
   does not have the memory for this: it needs about 4 GB free. Use a new models
   folder so the 20% models stay as they are:
   ```
   python -m wpa.evaluate v2-train --format regma --groups ABCDEF --features features_v2 --models models_v2_full
   python -m wpa.evaluate v2-train --format regma --groups ABCDE --features features_v2 --models models_v2_full
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEF --features features_v2 --models models_v2_full
   python -m wpa.evaluate v2-train --format pooled --groups ABCDE --features features_v2 --models models_v2_full
   python -m wpa.evaluate v2-report --features features_v2 --models models_v2_full
   ```
   Expect somewhere between 15 minutes and an hour for each training command.
   Compare its `models_v2_full\report.txt` with `models_v2\report.txt`. Do not run
   `v2-final` on it unless you decide to: it would be a fourth test opening, and
   it is logged.

---

## 16. The v3 model: damage, stat changes and spreads (Week 7)

v3 adds what the damage calculator says (group G). Speed (group F) becomes the
real stat, from each Pokemon's estimated spread. It needs everything from
Section 15, plus:

1. **Install the damage calculator** (once; it goes into `calc/node_modules`):
   ```
   npm ci --prefix calc
   ```
   Check it against Showdown's own damage code:
   ```
   python -m wpa.damage
   ```
   It ends with how many cases match. Every mismatch it lists is explained in
   `docs/DAMAGE-CALC.md`.

2. **Usage statistics** for the starting spreads. They are already in your
   `usage_stats` folder. On a new computer, download them with these two
   lines in PowerShell:
   ```
   mkdir usage_stats
   foreach ($f in "2026-04/gen9championsvgc2026regma","2026-04/gen9championsvgc2026regmabo3","2026-05/gen9championsvgc2026regma","2026-05/gen9championsvgc2026regmabo3","2026-06/gen9championsvgc2026regma","2026-06/gen9championsvgc2026regmabo3","2026-06/gen9championsvgc2026regmb","2026-06/gen9championsvgc2026regmbbo3") { $m, $n = $f.Split("/"); Invoke-WebRequest "https://www.smogon.com/stats/$m/chaos/$n-1500.json" -OutFile "usage_stats\$m-$n-1500.json" }
   ```

3. **Build the v3 feature table.** This is slow, because every game's spreads are
   worked out hit by hit. `--train-sample 0.2` takes the same 20% of Reg M-A's
   training sets as before; leave it out to build everything:
   ```
   python -m wpa.features --from-logs logs_shards --out features_v3 --groups ABCDEFG --usage usage_stats --train-sample 0.2 --shards 64 --workers 4
   ```
   Each part prints `shard N: {...}`. If it stops, add `--only 30-63` (the
   parts still missing) and run it again. `docs/DAMAGE-FEATURES.md` has the
   timings.

4. **Train.** The table is already the 20% sample, so there is no `--sample`
   here:
   ```
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFG --features features_v3 --models models_v3
   python -m wpa.evaluate v2-train --format regma --groups ABCDEF --features features_v3 --models models_v3
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFG --features features_v3 --models models_v3
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEF --features features_v3 --models models_v3
   ```
   `ABCDEF` is the same model without damage, kept to measure what damage adds.

5. **Report and gate** (validation):
   ```
   python -m wpa.evaluate v2-report --features features_v3 --models models_v3 --full ABCDEFG
   ```

6. **The test split - once, logged:**
   ```
   python -m wpa.evaluate v2-final --features features_v3 --models models_v3 --full ABCDEFG
   ```

7. **Expert claims** (report only):
   ```
   python -m wpa.claims_v2 scan --groups ABCDEFG --usage usage_stats --out claims_v3
   python -m wpa.claims_v2 report --groups ABCDEFG --out claims_v3 --model "v3 without damage=models_v3:ABCDEF" --model v3=models_v3:ABCDEFG
   ```

8. **Everything, on every training game (your computer).** The same steps
   without `--train-sample`, into new folders so the 20% results stay. Paste the
   whole block into PowerShell and leave it running; it takes hours (build time is
   in `docs/DAMAGE-FEATURES.md`, and each training command can take an hour):
   ```
   cd C:\dev\VGC_WPA\vgc-wpa
   python -m pip install -e ".[model]"
   npm ci --prefix calc
   python -m wpa.features --from-logs logs_shards --out features_v3_full --groups ABCDEFG --usage usage_stats --shards 64 --workers 4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFG --features features_v3_full --models models_v3_full
   python -m wpa.evaluate v2-train --format regma --groups ABCDEF --features features_v3_full --models models_v3_full
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFG --features features_v3_full --models models_v3_full
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEF --features features_v3_full --models models_v3_full
   python -m wpa.evaluate v2-report --features features_v3_full --models models_v3_full --full ABCDEFG
   ```
   If the build stops part-way, run its line again with `--only` and the parts
   still missing (e.g. `--only 40-63`), then carry on with the training lines.
   The result is `models_v3_full\report.txt`. Do not run `v2-final` on it: that
   would be another test opening.

---

## 17. The v4 model: who was brought, Bo3 memory, this turn, the whole board (Week 8)

v4 adds three feature groups:
- **H:** what each side can do this turn;
- **I:** the likely back;
- **J:** damage across the whole board.

It also remembers a Bo3 set from game to game, and Reg M-B gets a one-number
correction learned from its training sets. It needs everything from Section 16.

1. **Shard the logs by set** (once; a set's games together and in order):
   ```
   python -m wpa.features --split-logs logs_sets --shards 64
   ```

2. **Fit the bring model** (which four each player brought; about 5 minutes):
   ```
   python -m wpa.bring
   ```
   It prints how it does against a uniform guess and saves
   `models_v4\bring.json` and `models_v4\bring.txt`.

3. **Build the v4 feature table** (about as slow as v3):
   ```
   python -m wpa.features --from-logs logs_sets --out features_v4 --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --train-sample 0.2 --shards 64 --workers 4
   ```

4. **Train.** First the headline models, then Reg M-B's correction, then the
   models the comparisons need:
   ```
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHIJ --features features_v4 --models models_v4
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFGHIJ --features features_v4 --models models_v4
   python -m wpa.evaluate v2-crossfit --format pooled --groups ABCDEFGHIJ --features features_v4 --models models_v4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFG --features features_v4 --models models_v4
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFG --features features_v4 --models models_v4
   ```
   `v2-crossfit` trains the pooled model five more times, so it is the slowest
   step. It ends with `Reg M-B temperature 0.xx from N training sets`.

5. **Report and gate** (validation):
   ```
   python -m wpa.evaluate v2-report --features features_v4 --models models_v4 --full ABCDEFGHIJ --base ABCDEFG
   ```

6. **Blank sheets** (report only; `docs/BLANK-SHEETS.md`). The opponent's sheet
   is blanked and ours stays whole, as in a game without open team sheets. The
   two sides of a row then know different things, so the model is trained
   **one-sided** (`--one-sided`):
   ```
   python -m wpa.features --from-logs logs_shards --out features_v4_blank --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --blank --train-sample 0.2 --shards 64 --workers 4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHIJ --features features_v4_blank --models models_v4_public --one-sided
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFGHIJ --features features_v4_blank --models models_v4_public --one-sided
   python -m wpa.evaluate v2-report --features features_v4_blank --models models_v4_public --full ABCDEFGHIJ
   ```
   The report says "one-sided" next to each format. This build is fast (under a
   minute a shard), because spreads come from the statistics alone.

   **Optional: both sheets blanked**, as someone watching a replay without
   either sheet would see it. Both sides know the same kind of thing, so the
   usual symmetric model is right:
   ```
   python -m wpa.features --from-logs logs_shards --out features_v4_spect --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --blank-both --train-sample 0.2 --shards 64 --workers 4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHIJ --features features_v4_spect --models models_v4_spect
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFGHIJ --features features_v4_spect --models models_v4_spect
   python -m wpa.evaluate v2-report --features features_v4_spect --models models_v4_spect --full ABCDEFGHIJ
   ```

   **What each addition is worth** (paired, on validation). This needs the models
   trained without one group each, v3 from Section 16, and the blank-sheet models:
   ```
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGIJ --features features_v4 --models models_v4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHJ --features features_v4 --models models_v4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHI --features features_v4 --models models_v4
   python -m wpa.evaluate v2-compare --features features_v4 --models models_v4 --full ABCDEFGHIJ --others ABCDEFG ABCDEFGIJ ABCDEFGHJ ABCDEFGHI ABCDEFG@features_v3@models_v3 ABCDEFGHIJ@features_v4_blank@models_v4_public ABCDEFGHIJ@features_v4_spect@models_v4_spect
   ```
   The results are saved in `models_v4\compare.txt`. A model that has not been
   trained is skipped.

7. **The test split** is opened only if you agree; every opening is logged:
   ```
   python -m wpa.evaluate v2-final --features features_v4 --models models_v4 --full ABCDEFGHIJ
   ```

8. **Expert claims** (report only):
   ```
   python -m wpa.claims_v2 scan --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --out claims_v4
   python -m wpa.claims_v2 report --groups ABCDEFGHIJ --out claims_v4 --model "v3 groups=models_v4:ABCDEFG" --model v4=models_v4:ABCDEFGHIJ
   ```

9. **On every training game (your computer):** steps 3 to 5 without
   `--train-sample 0.2`, with `features_v4_full` and `models_v4_full` in place of
   `features_v4` and `models_v4`.

---

## 18. Week 9: the choices, the opponent's likely reply, what can happen, decision versus luck

This week adds the pieces that look inside a turn:
- **the choices on offer** at each decision point (`wpa.choices`);
- **what can happen** when both sides' choices play out, every damage roll,
  critical hit, miss and Speed tie with its chance (`wpa.resolver`);
- **the opponent's likely reply**, learned from the training games
  (`wpa.policy`);
- **decision versus luck**: each turn's swing split into your decision, their
  decision and the dice (`wpa.attribution`, DEFINITIONS §3), with cost against
  the best choice and against the average choice beside it (§4).

It needs everything from Section 17, including `models_v4_full` and
`models_v4\bring.json`. The resolver reads each move's facts from
`build\moves_regma.json` and `build\moves_regmb.json`, which are already in
`build`. Without them, leave `--moves-dir build` off each command below and the
facts are read from Showdown instead (a little slower to start).

1. **The opponent choice model** (about 15 minutes):
   ```
   python -m wpa.policy --moves-dir build
   ```
   It prints, per format, how it does against a uniform guess on the validation
   games, and saves `models_v4\policy.json` and `models_v4\policy.txt`. (A copy
   made here is already in `models_v4`; this remakes it on your computer.)

2. **The opponent model's sharpness** (about an hour; your decisions of 6 Nov).
   One setting that gives the opponent model's likeliest replies more of the
   chance, in the same order. It is measured on training sets, and you chose 4:
   ```
   python -m wpa.attribution --fit-sharpness --sharpness 4 --models models_v4_full --moves-dir build --sets 10 10 --workers 6
   ```
   It prints "your decision" on average for each setting, and saves 4 in
   `models_v4\policy.json` (the curve goes in `models_v4\policy_sharpness.txt`).
   Without `--sharpness 4` it would save the setting closest to zero instead.
   Step 1 resets the setting to 1, so after step 1 always run this step again.
   **The copy already in `models_v4` has 4: you do not need this step now.**

3. **Decision versus luck on the validation sample** (overnight; 300 Reg M-A sets
   and all 199 Reg M-B sets, the same sets every run):
   ```
   python -m wpa.attribution --models models_v4_full --moves-dir build --workers 6 --alternatives-every 3 --out reports/attribution_week9.jsonl
   ```
   - `--workers 6` uses six of your eight cores. Use fewer if the computer is
     needed for something else.
   - `--alternatives-every 3` works out cost against the best and the average
     choice in every third game; it is what makes a turn slow (about five times
     slower). `--alternatives-every 1` does it everywhere.
   - It can be stopped (Ctrl+C) and run again with the same command: games
     already done are skipped.

   At the end it prints the summary and saves it as
   `reports\attribution_week9.txt`. To see the summary of what is done so far:
   ```
   python -m wpa.attribution --report --out reports/attribution_week9.jsonl
   ```

4. **Blank sheets with team preview** (report only; replaces Section 17 step 6's
   blank build). The opponent's six species are known, as team preview shows
   them; their items, abilities, moves and spreads stay hidden until revealed.
   New folders, so Week 8's blank models stay for comparison:
   ```
   python -m wpa.features --from-logs logs_shards --out features_v4_preview --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --blank --train-sample 0.2 --shards 64 --workers 4
   python -m wpa.evaluate v2-train --format regma --groups ABCDEFGHIJ --features features_v4_preview --models models_v4_preview --one-sided
   python -m wpa.evaluate v2-train --format pooled --groups ABCDEFGHIJ --features features_v4_preview --models models_v4_preview --one-sided
   python -m wpa.evaluate v2-report --features features_v4_preview --models models_v4_preview --full ABCDEFGHIJ
   ```

5. **How much win probability wobbles** (DEFINITIONS §10.2; several hours a
   format). Three models retrained on resamples of the training sets:
   ```
   python -m wpa.wobble --features features_v4 --models models_v4 --groups ABCDEFGHIJ --format regma --resamples 3 --out wobble_v4
   python -m wpa.wobble --features features_v4 --models models_v4 --groups ABCDEFGHIJ --format pooled --resamples 3 --out wobble_v4
   ```
   Each prints the median and 90th percentile wobble in points, against the
   0.5-point threshold, and saves it in `wobble_v4`.

---

## 19. Week 10: the biggest swings made right, the averaged model, forced switches

This week fixes what put the wrong turns at the top of Week 9's list (Perish
Song, Last Respects, Rage Fist, Supreme Overlord), and makes the win probability
an average of 10 models (DEFINITIONS §10.2, revision 9). Two of the fixes change
the feature table, so it is built again first. It needs everything from
Sections 17 and 18.

1. **Build the full table again, with the fixes** (about 2½ hours at 4 workers,
   as in Section 17). A new folder, so the old table stays:
   ```
   python -m wpa.features --from-logs logs_sets --out features_v4b_full --groups ABCDEFGHIJ --usage usage_stats --bring models_v4/bring.json --shards 64 --workers 4
   ```

2. **Train the 10 models for each format** (each one is a full training, like
   Section 17's; the first one prints how long it took). Reg M-A first, then the
   pooled model for Reg M-B:
   ```
   python -m wpa.ensemble train --features features_v4b_full --models models_v4_avg --format regma
   python -m wpa.ensemble train --features features_v4b_full --models models_v4_avg --format pooled
   ```
   Each prints a line per model, such as `regma member 1 of 10: validation
   Brier 0.18xx after N rounds, H hours`. They can be stopped (Ctrl+C) and run
   again with the same command: finished models are kept, and the one in
   progress carries on from its last save. Spreading them over several nights
   is fine.

3. **Put the average together and check it** (minutes):
   ```
   python -m wpa.ensemble finish --features features_v4b_full --models models_v4_avg --base models_v4_full
   ```
   For each format it prints the validation score, the comparison with
   `models_v4_full` (negative is better), and the averaged model's own noise
   against the 3-point threshold. It ends with `Gate: passed` or the bins that
   failed, and saves it all in `models_v4_avg\report.txt`. A line starting
   `BLOCKER` means the noise is over the threshold: stop there and send it to me.

4. **The forced-switch model** (optional; about an hour). Which Pokemon a
   player sends in after a faint, learned from the training games. A copy made
   here is already in `models_v4\replace.json`; this remakes it on your
   computer:
   ```
   python -m wpa.replace_model
   ```
   It prints, per format, how it does against a uniform guess over the Pokemon
   that could come in, and saves `models_v4\replace.json` and `replace.txt`.

5. **Decision versus luck again, with everything** (overnight; the same 300
   Reg M-A and 199 Reg M-B sets as Week 9). Needs step 3's `Gate: passed`:
   ```
   python -m wpa.attribution --models models_v4_avg --moves-dir build --workers 6 --alternatives-every 3 --out reports/attribution_week10.jsonl
   ```
   - It now splits forced switches too, and checks that each game's swings
     add up to its result.
   - Each decision point values at most 4,000 boards; over that, boards are
     grouped on a coarser hit-point grid (nothing is dropped). `--budget 0`
     turns this off.
   - As in Section 18, Ctrl+C stops it and the same command carries on.

   At the end it prints the summary and saves it as
   `reports\attribution_week10.txt`. Send me that file.


## 20. Week 11: your choice and the position, team preview, Speed order

This week splits "your decision" into **your choice** (against the typical
choice) and **the position** (DEFINITIONS §3, revision 10), scores **team
preview's leads**, branches on **Speed order** where the spreads are not settled,
and follows the **Champions rules** for paralysis, sleep, freeze, confusion,
charging moves and Encore. It needs everything from Section 19, including
`models_v4_avg`.

1. **The lead model** (optional; about 10 minutes). Which two each player leads
   with, learned from the training games, using the set's previous game. A copy
   made here is already in `models_v4\leads.json`; this remakes it on your
   computer:
   ```
   python -m wpa.lead_model
   ```
   It prints, per format, how it does against a uniform guess over the 15 pairs,
   and saves `models_v4\leads.json` and `leads.txt`.

2. **Decision versus luck again** (about 1½ to 2 times Week 10's run: one long
   night, or two; the same 300 Reg M-A and 199 Reg M-B sets):
   ```
   python -m wpa.attribution --models models_v4_avg --moves-dir build --workers 6 --alternatives-every 3 --out reports/attribution_week11.jsonl
   ```
   - The summary now leads with **your choice** and shows **the position**
     beside it, and has a section for team preview.
   - As before, Ctrl+C stops it and the same command carries on where it
     stopped, so it can run over two nights.

   At the end it prints the summary and saves it as
   `reports\attribution_week11.txt`. Send me that file.

---

## 21. Your own games: the replay report

Paste a Showdown replay link and get **your biggest win-probability swings in
that game**, each split as DEFINITIONS §3 says (your choice, the position,
their decision, the dice), with what happened and, where your choice was not
the best of your likely choices, the best one named. It uses the same models
and settings as Section 20's run, so it needs everything from Sections 19
and 20.

1. **One game** (about two minutes; a long game, a few):
   ```
   python -m wpa.replay https://replay.pokemonshowdown.com/gen9championsvgc2026regma-2605147085 --player "your Showdown name"
   ```
   It prints the report and saves it in `reports\replays\`.

2. **A best-of-three:** give the games' links in order, game 1 first:
   ```
   python -m wpa.replay LINK1 LINK2 LINK3 --player "your Showdown name"
   ```
   Games 2 and 3 then use what game 1 showed (DEFINITIONS §11.3). The report
   starts with one line per game. The games are analysed side by side (three
   at once; add `--workers 1` for one at a time).

3. **The same game again** shows at once: the analysis is saved.
   - `--top 10` shows ten swings instead of five.
   - `--player` with the other player's name shows their side.
   - `--fresh` analyses the game again (after a change to the models or the
     code).

4. **A private replay, or no internet:** open the replay in your browser, save
   the page (Ctrl+S), and give the saved file instead of the link:
   ```
   python -m wpa.replay "C:\Users\you\Downloads\replay.html" --player "your Showdown name"
   ```

**What the report shows**
- Your win probability at team preview and at the start of each turn.
- **Over the game:** how your choices, their decisions, the dice and the
  positions add up to the game's result.
- **Team preview:** the two you led, against the typical leads and the best
  leads (named when yours were not the best).
- **Your biggest swings**, biggest first. For each: the moves both sides made,
  what fainted, the luck the log shows (critical hits, misses, full paralysis,
  a burn from a move's added effect, and the like), your choice against the
  typical choice and against the best, and the best choice when yours was not.
- **Your costliest choices:** where the best of your likely choices was worth
  the most more than yours.

**Limits**
- Champions VGC 2026 Reg M-A and Reg M-B only; for another format it says so
  and stops.
- The game must show open team sheets (Champions games do).
- "The best" is the best of your 10 likeliest choices against the opponent's
  likely replies, by the model. It is a coaching number, not a solver's answer.

**The end-to-end check** (M7's test; about ten minutes, so only when asked):
```
$env:WPA_SLOW=1; python -m pytest tests/test_replay_e2e.py; Remove-Item Env:WPA_SLOW
```

---

## 22. Week 12: the resolver check

The resolver plays out each turn from the choices both players made. This check
measures how often it does that **in full** (no rule it models only in part) and
how often **the board that happened is among its boards**. It uses the same 892
validation games every time: every game of the brief's 300 Reg M-A and 199
Reg M-B sets, listed in `data\resolver_check_games.json`. It needs no model
and never reads the test split.

1. **Today's code** (13 minutes on 2 workers; quicker with the 6 it uses by
   default):
   ```
   python -m wpa.resolver_check
   ```
   The run is named after the current commit, plus "-modified" if the code has
   changes not yet committed.

2. **An earlier commit's code, on the same games** (about the same time):
   ```
   python -m wpa.resolver_check --code 9e9ef90
   ```
   It copies that commit's code into `build\code-9e9ef90` and runs it there.
   Your working copy is not touched.

3. **The table only:**
   ```
   python -m wpa.resolver_check --report
   ```
   Each run is a column, oldest first. The table is saved as
   `reports\resolver_check\summary.txt`.

- Ctrl+C stops a run; the same command carries on where it stopped.
- `--max-games 20` is a quick trial on 20 games.
- `--fresh` starts a run over.
- `--spread-hits` runs it with Task 4's spread method (Section 23). The run's
  column is named with "-spread-hits".

**What the table shows, per format**
- **Fully modelled:** the share of turns where nothing happened that the
  resolver models only in part.
- **Board found:** the share where one of its boards matches what happened:
  the same Pokemon knocked out, and every HP within 6 points.
- **Both:** the share of turns with both.
- **Turns with a knock-out:** the same three shares for these turns alone.
- **Not found:** the misses, split in two:
  - a knock-out differs on every board;
  - only HP differs, with the median gap. Most of these are spreads the
    resolver does not branch on (Task 4).
- **Left out:** turns it does not check, such as a game lost on the timer.
- **Boards per turn** and **resolver time per turn:** what it costs.
- **Partly modelled, turns by reason:** what is left to model, with each run's
  count.

---

## 23. Week 12: the stronger opponent model and the sample again

This week's run adds two things to Section 20's:
- **Task 4's spread method** (`--spread-hits`): a hit branches on the target's
  likely spreads where one of them would change whether it is knocked out.
- **Task 3's stronger opponent model, measured only:** each likely choice is
  also weighed by how good it is for the one choosing. Its one setting, the
  strength, is learned on training games. The analysis itself still uses the
  model of DEFINITIONS revision 10 (strength 0) until you approve a change.

It needs everything from Section 20, including `models_v4_avg`. Do step 1
first: step 2 uses what it learns.

1. **Learn the strength** (about half an hour to an hour; training games of 40
   Reg M-A and 30 Reg M-B sets, never validation or test):
   ```
   python -m wpa.attribution --fit-strength --spread-hits --models models_v4_avg --moves-dir build --workers 6 --sets 40 30
   ```
   - It counts the games as it goes (115 in all: 59 Reg M-A, 56 Reg M-B).
   - Ctrl+C stops it; the same command carries on where it stopped.
   - At the end it prints the strength per format and saves
     `models_v4\strength.txt` (and `strength.json`, which step 2 reads).
     Send me `strength.txt`.

2. **Decision versus luck again** (Task 6; the same 300 Reg M-A and 199 Reg M-B
   sets as Week 11, the averaged model, sharpness 4; about as long as Week 11's
   run, one long night or two):
   ```
   python -m wpa.attribution --models models_v4_avg --moves-dir build --workers 6 --alternatives-every 3 --spread-hits --measure-strengths 0 fitted --out reports/attribution_week12.jsonl
   ```
   - The summary is laid out as Week 11's. A new section, "the opponent
     model's strength", shows the split at strength 0 and at the learned one,
     side by side.
   - If step 1 has not finished, it stops at once and says so.
   - Ctrl+C stops it and the same command carries on, so it can run over two
     nights.

   At the end it prints the summary and saves it as
   `reports\attribution_week12.txt`. Send me that file.

---

## If something goes wrong

**`pip install -e ".[dev]"` fails because of `open-spiel`.**
This is a known, accepted issue - `open-spiel` is difficult to install on
some systems and is only needed for one specific module
(`vgc_bench/eval.py`, used for a kind of tournament analysis) that this
project isn't currently using. It's already been removed from the
dependency list for that reason. If `pip install -e ".[dev]"` still fails
mentioning `open-spiel`, check that `pyproject.toml`'s dependency list
doesn't have it listed - it shouldn't.

**Starting the server says the port is already in use.**
Something is already using port 8000 - most likely you (or someone else)
already has the server running in another terminal window. Look for an
existing terminal window running `node pokemon-showdown start` and use
that one instead of starting a second copy.

**The parser (Section 3) crashes or the computer becomes very slow.**
See the memory warning in Section 3 - this is almost always the very large
`logs_gen9championsvgc2026regmabo3.json` file combined with too many
`--num_workers`. Lower `--num_workers` and try again.

**Running a battle (Section 5) or the volume test (Section 6) says it
can't connect, or just sits there doing nothing.**
Almost always the local server (Section 2) isn't running - check that
terminal window first. If the server is running and it still hangs with no
error at all, this project has hit that exact symptom before from running
several live-battle commands back to back in the same long-running
process (a known issue, not something you did wrong) - closing the
terminal and starting a fresh one before trying again works around it.

**The volume test (Section 6) reports more than 2 failed battles out of
100.**
Stop and report it with the exact output rather than re-running it - see
the Week 2 dispatch's rules of engagement. This has not happened in
practice; if it does, something changed.

**`pytest` reports failures you don't understand, or CI shows a red X.**
Don't try to work around it by re-running or changing test files. Write
down the exact error message and stop - see
`docs/WEEK1-DISPATCH.md`'s rules of engagement for what to do next.

**The splitter or the report (Sections 10-11) stops with `not a state file:`
and a file name.**
Something that is not a battle record is sitting inside `wpa_states/` - most
often `splits.json` saved there by mistake. Both tools refuse to guess, and
stop. Move the file out (`splits.json` belongs in the repo's top-level
folder) and run the command again. Do not delete anything else in
`wpa_states/`.

**The splitter stops with `UnknownFormatError: unrecognised battle tag`.**
A file in `wpa_states/` belongs to a battle format the project has not been
told about, and it will not guess which one. Stop and report the exact tag
in the message; adding a format is a small code change, not something to
work around.

**The splitter stops with `CannotSplitError: cannot give every format its
own train, validation and test sets`.**
One format has too few independent games to fill all three splits. This is
the splitter refusing to produce a split that would be unreliable. Stop and
report the whole message.

**The report (Section 11) prints different numbers from the ones listed
there.**
With the same data and the same `splits.json` the numbers should match
exactly. Check that `wpa_states/` is the full re-parse (Section 9) and that
`splits.json` was made from it, then stop and report both sets of numbers
rather than re-running.

**`ruff` or `pyright` "is not recognized" (Section 12).**
Use `python -m ruff ...` and `python -m pyright` instead. If that says "No
module named ruff", the dev install has not been done on this computer: run
`pip install -e ".[dev]"` from the repo root (Section 1, step 5) and try
again.

**Nothing here covers the problem.**
Same answer: stop and ask rather than guessing, especially for anything
touching licensing, payment, credentials, or a parse failure rate above 5%.
