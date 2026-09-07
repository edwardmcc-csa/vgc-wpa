# Runbook

This is for anyone who needs to start the local battle server, run the log
parser, or run the tests, and has never touched this repository before. You
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
- `tests/` - our own tests (for the code in `wpa/`), including
  `tests/fixtures/battles/` - the 20 saved example battles from Section 7,
  documented in `tests/fixtures/README.md`.
- `unit_tests/` and `integration_tests/` - the original vgc-bench project's
  own tests.
- `docs/` - documents like this one, plus the project's pinned dependency
  versions (`PINNED-VERSIONS.md`) and the original planning documents.

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

**Nothing here covers the problem.**
Same answer: stop and ask rather than guessing, especially for anything
touching licensing, payment, credentials, or a parse failure rate above 5%.
