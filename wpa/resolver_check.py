"""The resolver check (Week 12 Task 1). On a fixed, saved sample of validation
games per format: the share of turns the resolver plays out in full (no rule it
models only in part), the share where the board that happened is among its
boards, the share with both, the reasons left and the time.

    python -m wpa.resolver_check                   # today's code
    python -m wpa.resolver_check --code 9e9ef90    # a commit's code, same games
    python -m wpa.resolver_check --report          # every run so far, side by side

Each turn resolves the choices both players took, as the analysis does (where
the log hides one, every choice it allows). No win probability is needed, so no
model is loaded for it. The games are listed in data/resolver_check_games.json,
made once from the brief's sample of sets (--new-sample) and kept, so every run
checks the same games. Each run's turns are saved in
reports/resolver_check/<code>.jsonl, and the table in summary.txt.

A commit's code is taken with `git archive` into build/code-<commit>, with this
check beside it, and run there on the same data: the working copy is untouched.
"""

from __future__ import annotations

import argparse
import copy
import io
import itertools
import json
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

ROLES = ("p1", "p2")
TOL = 0.06  # the analysis's: the larger of 3 points and the HP grid (5) + 1
SAMPLE = Path("data/resolver_check_games.json")
OUT_DIR = Path("reports/resolver_check")
FORMAT_NAMES = {"regma": "Reg M-A", "regmb": "Reg M-B"}


# --------------------------------------------------------------------------
# One turn, one game
# --------------------------------------------------------------------------


def _hp_gap(a: Mapping, b: Mapping) -> float | None:
    """The largest HP difference between two boards, or None when a different
    Pokemon is knocked out in each."""
    gap = 0.0
    for r in ROLES:
        for x, y in zip(a[r], b[r]):
            if bool(x["fainted"]) != bool(y["fainted"]):
                return None
            if not x["fainted"]:
                gap = max(gap, abs(x["hp_fraction"] - y["hp_fraction"]))
    return gap


def _knock_out(before: Mapping, after: Mapping) -> bool:
    return any(
        y["fainted"] and not x["fainted"]
        for r in ROLES
        for x, y in zip(before[r], after[r])
    )


_OTHER = ("-heal", "-sethp", "-crit", "-enditem", "-item", "-ability", "-activate")


def clean_hits(
    lines: Sequence[str], names: Mapping[str, Sequence[str]]
) -> dict[tuple[str, int], bool]:
    """The Pokemon hit cleanly in a turn's log lines (Week 13 Task 1): one hit
    from a move and nothing else on it (no other HP change, critical hit, item
    or ability), with no weather that turn. Each as (side, sheet position) ->
    whether the move was a spread move. `names`: each side's Pokemon as the
    log names them, in sheet order."""
    hits: Counter = Counter()
    spread: dict[tuple[str, int], bool] = {}
    other: set[tuple[str, int]] = set()
    last_spread = False

    def who(field: str) -> tuple[str, int] | None:
        side, _, name = field.partition(": ")
        role = side[:2]
        if role not in names or name not in names[role]:
            return None
        return role, list(names[role]).index(name)

    for line in lines:
        f = line.split("|")
        if len(f) < 3:
            continue
        kind = f[1]
        if kind == "-weather" and f[2] != "none":
            return {}
        if kind == "move":
            last_spread = "[spread]" in line
            continue
        if kind not in ("-damage", *_OTHER):
            continue
        pk = who(f[2])
        if pk is None:
            continue
        if kind == "-damage" and "[from]" not in line and "fnt" not in line:
            hits[pk] += 1
            spread[pk] = last_spread
        else:
            other.add(pk)
    return {pk: spread[pk] for pk, n in hits.items() if n == 1 and pk not in other}


def _hit(ts: Any, outs: Sequence, r: str, i: int) -> tuple[float, float] | None:
    """A clean hit's estimate (the median HP lost over the boards where the
    Pokemon is hit and stays standing, by their chances) and what it lost."""
    before = ts.tv.sides[r][i]["hp_fraction"]
    z = ts.actual[r][i]
    if z["fainted"] or z["hp_fraction"] >= before - 1e-9:
        return None
    hit = [
        (o.prob, o.sides[r][i]["hp_fraction"])
        for o in outs
        if not o.sides[r][i]["fainted"] and o.sides[r][i]["hp_fraction"] < before - 1e-9
    ]
    total = sum(p for p, _ in hit)
    if total <= 0:
        return None
    acc = 0.0
    for p, h in sorted(hit, key=lambda t: t[1]):
        acc += p
        if acc >= total / 2 - 1e-12:
            return round(before - h, 4), round(before - z["hp_fraction"], 4)
    return None


def check_turn(
    ts: Any,
    priority: Mapping[str, int],
    tol: float = TOL,
    clean: Mapping[tuple[str, int], bool] | None = None,
) -> dict:
    """One turn (a `wpa.attribution.TurnSetup`): the choices both players took
    resolved, each board against the board that happened. A miss says whether a
    knock-out differs on every board, or only HP (`off`: the closest board's
    largest HP difference). With `clean` (`clean_hits`), and both choices shown
    whole, each clean hit's estimate against what happened (`hits`)."""
    from wpa.attribution import _close, taken_mixture

    mixes = {}
    for r in ROLES:
        t = ts.turns[r]
        mixes[r] = taken_mixture(
            t.taken,
            t.hidden,
            ts.opts[r],
            ts.chances[r],
            priority,
            getattr(t, "megas", ()),
        )
    t0 = time.time()
    outs: list = []
    pairs = 0
    for (x, _p), (y, _q) in itertools.product(mixes["p1"], mixes["p2"]):
        pairs += 1
        outs += ts.tv.resolver.resolve(
            copy.deepcopy(dict(ts.tv.sides)),
            copy.deepcopy(ts.tv.fld),
            {"p1": x, "p2": y},
        )
    secs = time.time() - t0
    found = any(_close(o.sides, ts.actual, tol) for o in outs)
    partial = sorted(set().union(*(o.partial for o in outs))) if outs else []
    missed: str | None = None
    off: float | None = None
    if not found:
        gaps = [g for o in outs if (g := _hp_gap(o.sides, ts.actual)) is not None]
        if not outs:
            missed = "no boards"
        elif gaps:
            missed, off = "hp", round(min(gaps), 4)
        else:
            missed = "knock-out"
    rec = {
        "tag": ts.base["tag"],
        "format": ts.base["format"],
        "turn": ts.base["turn"],
        "found": found,
        "partial": partial,
        "ko": _knock_out(ts.tv.sides, ts.actual),
        "missed": missed,
        "off": off,
        "pairs": pairs,
        "boards": len(outs),
        "seconds": round(secs, 4),
    }
    if clean is not None:
        rec["hits"] = [
            [r, i, sp, *got]
            for (r, i), sp in sorted(clean.items())
            if all(len(m) == 1 for m in mixes.values())
            and (got := _hit(ts, outs, r, i)) is not None
        ]
    return rec


def _segments(log: str) -> tuple[dict[str, list[str]], dict[int, list[str]]]:
    """Each side's Pokemon as the log names them (sheet order), and each
    turn's lines."""
    from wpa.sheets import parse_showteam_message

    names: dict[str, list[str]] = {}
    turns: dict[int, list[str]] = {}
    turn = None
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            role, mons = parse_showteam_message(line)
            names[role] = [m.name or m.species for m in mons]
        elif line.startswith("|turn|"):
            turn = int(line.split("|")[2])
            turns[turn] = []
        elif turn is not None:
            turns[turn].append(line)
    return names, turns


def check_game(
    setups: Iterable,
    priority: Mapping[str, int],
    tol: float = TOL,
    log: str | None = None,
) -> list[dict]:
    """Each decision point `wpa.attribution.turn_setups` gives: a turn checked,
    or a point left out (once, with its reason). An error in one turn is kept as
    a point left out, and the game goes on. With the `log`, each turn's clean
    hits are measured too."""
    names, segs = _segments(log) if log is not None else ({}, {})
    recs = []
    for ts in setups:
        if isinstance(ts, list):
            if ts:
                r = ts[0]
                recs.append(
                    {
                        "tag": r.get("tag"),
                        "format": r.get("format"),
                        "turn": r.get("turn"),
                        "skipped": r.get("skipped", "left out"),
                    }
                )
            continue
        try:
            clean = (
                clean_hits(segs.get(ts.base["turn"], []), names)
                if log is not None
                else None
            )
            recs.append(check_turn(ts, priority, tol, clean))
        except Exception as e:
            recs.append(
                {
                    "tag": ts.base["tag"],
                    "format": ts.base["format"],
                    "turn": ts.base["turn"],
                    "skipped": f"error: {type(e).__name__}: {str(e)[:80]}",
                }
            )
    return recs


# --------------------------------------------------------------------------
# The summary
# --------------------------------------------------------------------------


def summarise(recs: Iterable[Mapping]) -> dict[str, dict]:
    """Per format: turns checked, fully modelled, found, both (and the same for
    turns with a knock-out), the turns per reason, the misses by kind, the
    points left out by reason and the resolver's time."""
    out: dict[str, dict] = {}
    for r in recs:
        fmt = r.get("format")
        if fmt is None:
            continue
        s = out.setdefault(
            fmt,
            {
                "games": set(),
                "turns": 0,
                "full": 0,
                "found": 0,
                "both": 0,
                "ko_turns": 0,
                "ko_full": 0,
                "ko_found": 0,
                "ko_both": 0,
                "reasons": Counter(),
                "missed": Counter(),
                "offs": [],
                "skipped": Counter(),
                "seconds": 0.0,
                "boards": 0,
                "hits": [],
            },
        )
        s["games"].add(r.get("tag"))
        if "skipped" in r:
            s["skipped"][r["skipped"]] += 1
            continue
        full, found = not r["partial"], bool(r["found"])
        s["turns"] += 1
        s["full"] += full
        s["found"] += found
        s["both"] += full and found
        if r.get("ko"):
            s["ko_turns"] += 1
            s["ko_full"] += full
            s["ko_found"] += found
            s["ko_both"] += full and found
        for x in r["partial"]:
            s["reasons"][x] += 1
        if r.get("missed"):
            s["missed"][r["missed"]] += 1
        if r.get("off") is not None:
            s["offs"].append(r["off"])
        s["seconds"] += r.get("seconds", 0.0)
        s["boards"] += r.get("boards", 0)
        for h in r.get("hits", ()):
            s["hits"].append((bool(h[2]), float(h[3]), float(h[4])))
    return out


def bias(hits: Sequence[tuple[bool, float, float]]) -> dict[str, float] | None:
    """Clean hits' real damage against the estimate: the median ratio, and the
    shares where the estimate is too high (real under 90% of it) or too low
    (over 110%)."""
    ratios = [real / est for _sp, est, real in hits if est > 0]
    if not ratios:
        return None
    n = len(ratios)
    return {
        "single": sum(not sp for sp, _e, _r in hits),
        "spread": sum(bool(sp) for sp, _e, _r in hits),
        "median": statistics.median(ratios),
        "high": sum(x < 0.9 for x in ratios) / n,
        "low": sum(x > 1.1 for x in ratios) / n,
    }


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "-"


def _dur(secs: float) -> str:
    return f"{round(secs / 60)} min" if secs >= 60 else f"{secs:.0f} s"


def _plain(reason: str) -> str:
    """A resolver reason in plain words: "move:leechseed" -> "leechseed (move)"."""
    kind, _, what = reason.partition(":")
    return f"{what} ({kind})" if what else reason


def summary_lines(
    runs: Mapping[str, Sequence[Mapping]],
    meta: Mapping[str, Mapping] | None = None,
    reasons: int = 12,
) -> list[str]:
    """Every run side by side, per format, in the order given."""
    meta = meta or {}
    labels = list(runs)
    sums = {k: summarise(v) for k, v in runs.items()}
    fmts = sorted({f for s in sums.values() for f in s})
    w = max([10] + [len(k) + 2 for k in labels])
    nw = max(
        [34]
        + [
            len(_plain(x)) + 3
            for s in sums.values()
            for f in s.values()
            for x in f["reasons"]
        ]
    )

    def row(name: str, vals: Iterable[str]) -> str:
        return f"  {name:<{nw}}" + "".join(f"{v:>{w}}" for v in vals)

    lines = [
        "The resolver check: each turn's choices, as the log shows them, played "
        "out by the resolver.",
        "Fully modelled: no rule it models only in part. Found: the board that "
        "happened is among its boards (HP within 6 points).",
        "",
    ]
    for fmt in fmts:
        ss: list[Mapping] = [sums[k].get(fmt, {}) for k in labels]

        def get(s: Mapping, key: str) -> Any:
            return s.get(key, 0)

        games = max(len(s.get("games", ())) for s in ss)
        lines.append(f"{FORMAT_NAMES.get(fmt, fmt)}: {games:,} games")
        lines.append(row("", labels))
        lines.append(row("turns checked", (f"{get(s, 'turns'):,}" for s in ss)))
        for name, key in (
            ("fully modelled", "full"),
            ("board found", "found"),
            ("both", "both"),
        ):
            lines.append(row(name, (_pct(get(s, key), get(s, "turns")) for s in ss)))
        lines.append(
            row("turns with a knock-out", (f"{get(s, 'ko_turns'):,}" for s in ss))
        )
        for name, key in (
            ("fully modelled", "ko_full"),
            ("board found", "ko_found"),
            ("both", "ko_both"),
        ):
            lines.append(
                row("  " + name, (_pct(get(s, key), get(s, "ko_turns")) for s in ss))
            )
        for name, key in (
            ("not found: a knock-out differs", "knock-out"),
            ("not found: HP only", "hp"),
            ("not found: no boards", "no boards"),
        ):
            if key == "no boards" and not any(s.get("missed", {}).get(key) for s in ss):
                continue
            lines.append(
                row(name, (f"{s.get('missed', {}).get(key, 0):,}" for s in ss))
            )
            if key == "hp":
                lines.append(
                    row(
                        "  median HP difference",
                        (
                            f"{100 * statistics.median(s['offs']):.0f} pts"
                            if s.get("offs")
                            else "-"
                            for s in ss
                        ),
                    )
                )
        left: Counter = Counter()
        per: list[Counter] = []
        for s in ss:
            c: Counter = Counter()
            for why, n in s.get("skipped", {}).items():
                c["errors" if why.startswith("error") else why] += n
            per.append(c)
            left.update(c)
        for why in sorted(left):
            lines.append(row(f"left out: {why}", (f"{c.get(why, 0):,}" for c in per)))
        bs = [bias(s.get("hits", ())) for s in ss]
        if any(bs):
            for name, show in (
                (
                    "clean hits (single / spread)",
                    lambda b: f"{b['single']:,} / {b['spread']:,}",
                ),
                ("real damage / estimate, median", lambda b: f"{b['median']:.2f}"),
                ("estimate too high by over 10%", lambda b: f"{100 * b['high']:.1f}%"),
                ("estimate too low by over 10%", lambda b: f"{100 * b['low']:.1f}%"),
            ):
                lines.append(row(name, (show(b) if b else "-" for b in bs)))
        lines.append(
            row(
                "boards per turn",
                (
                    f"{get(s, 'boards') / get(s, 'turns'):.1f}"
                    if get(s, "turns")
                    else "-"
                    for s in ss
                ),
            )
        )
        lines.append(
            row(
                "resolver time per turn",
                (
                    f"{get(s, 'seconds') / get(s, 'turns'):.3f} s"
                    if get(s, "turns")
                    else "-"
                    for s in ss
                ),
            )
        )
        most: Counter = Counter()
        for s in ss:
            for x, n in s.get("reasons", {}).items():
                most[x] = max(most[x], n)
        if most:
            lines.append("  partly modelled, turns by reason:")
            for x, _n in most.most_common(reasons):
                lines.append(
                    row(
                        "  " + _plain(x),
                        (f"{s.get('reasons', {}).get(x, 0):,}" for s in ss),
                    )
                )
        lines.append("")
    timed = [k for k in labels if k in meta and "wall" in meta[k]]
    if timed:
        lines.append(
            "Each run took: "
            + "; ".join(
                f"{k} {_dur(meta[k]['wall'])} ({meta[k].get('workers', '?')} workers)"
                for k in timed
            )
        )
    return lines


def done_tags(path: Path) -> set[str]:
    """The games a run has saved, so a stopped run carries on. A line cut off
    when it stopped (Ctrl+C) is removed, and its game done again."""
    path = Path(path)
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text = text[: text.rfind("\n") + 1]
        path.write_text(text, encoding="utf-8")
    return {json.loads(x)["tag"] for x in text.splitlines() if x.strip()}


def load_runs(out_dir: Path) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Every run saved in `out_dir`, oldest first."""
    runs: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    for p in Path(out_dir).glob("*.jsonl"):
        lines = p.read_text(encoding="utf-8").splitlines()
        runs[p.stem] = [json.loads(x) for x in lines if x.strip()]
        m = p.with_suffix(".json")
        meta[p.stem] = json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}
    order = sorted(runs, key=lambda k: (meta[k].get("started", float("inf")), k))
    return {k: runs[k] for k in order}, meta


# --------------------------------------------------------------------------
# The sample, and a commit's code
# --------------------------------------------------------------------------


def save_sample(path: Path, games: Mapping[str, Sequence[str]], note: str) -> None:
    """Save the sample once: it is kept, so every run checks the same games."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} is kept as it is; delete it to make another")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "note": note,
        "made": date.today().isoformat(),
        "games": {f: list(ts) for f, ts in games.items()},
    }
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def load_sample(
    path: Path, splits: Mapping[str, str] | None = None
) -> dict[str, list[str]]:
    """The saved sample, per format. With `splits`, it refuses any game in the
    test split (the test split is opened only with the PO's approval)."""
    games = json.loads(Path(path).read_text(encoding="utf-8"))["games"]
    if splits is not None:
        bad = [t for ts in games.values() for t in ts if splits.get(t) == "test"]
        if bad:
            raise ValueError(
                f"{len(bad)} games of the sample are in the test split, e.g. {bad[0]}"
            )
    return {f: list(ts) for f, ts in games.items()}


def extract_code(commit: str, root: Path, dest: Path) -> Path:
    """The `wpa` package as it was at `commit`, in `dest` (made afresh), with
    this check, the damage calculator and the scripts it calls beside it."""
    root, dest = Path(root), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    try:
        data = subprocess.run(
            ["git", "archive", "--format=tar", commit, "wpa"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except FileNotFoundError:
        raise SystemExit("git was not found: --code needs git (Runbook Section 1)")
    except subprocess.CalledProcessError as e:
        why = e.stderr.decode(errors="replace").strip()
        raise SystemExit(f"git could not find the commit {commit}: {why}")
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        tf.extractall(dest, filter="data")
    shutil.copy2(Path(__file__), dest / "wpa" / "resolver_check.py")
    for d in ("calc", "scripts"):
        if (root / d).exists():
            shutil.copytree(root / d, dest / d)
    return dest


def child_command(a: argparse.Namespace, dest: Path, root: Path) -> list[str]:
    """The check run in `dest` on a commit's code: the same data and settings,
    by full paths."""

    def full(p: Path | str) -> str:
        p = Path(p)
        return str(p if p.is_absolute() else (Path(root) / p).resolve())

    cmd = [sys.executable, "-m", "wpa.resolver_check"]
    cmd += ["--label", run_label(a, a.code), "--expect-code", full(dest)]
    for flag, value in (
        ("--sample", a.sample),
        ("--splits", a.splits),
        ("--logs", a.logs),
        ("--showdown", a.showdown),
        ("--usage", a.usage),
        ("--bring", a.bring),
        ("--policy", a.policy),
        ("--out-dir", a.out_dir),
    ):
        cmd += [flag, full(value)]
    if a.moves_dir:
        cmd += ["--moves-dir", full(a.moves_dir)]
    if a.dex_tables:
        cmd += ["--dex-tables", full(a.dex_tables)]
    cmd += ["--workers", str(a.workers), "--resolution", str(a.resolution)]
    cmd += ["--cap", str(a.cap)]
    if a.max_games:
        cmd += ["--max-games", str(a.max_games)]
    if a.spread_hits:
        cmd.append("--spread-hits")
    if a.spread_damage:
        cmd.append("--spread-damage")
    if a.fresh:
        cmd.append("--fresh")
    return cmd


def run_label(a: argparse.Namespace, code: str) -> str:
    """A run's name: the code's (commit), and what it was asked to do."""
    if a.label:
        return a.label
    label = f"{code}-spread-hits" if a.spread_hits else code
    return f"{label}-spread-damage" if getattr(a, "spread_damage", False) else label


def _label() -> str:  # pragma: no cover - asks git
    """Today's code: the commit, marked when `wpa` has changes not committed."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "wpa"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return "today"
    return f"{head}-modified" if dirty else head


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

_W: dict = {}


def _init(a: argparse.Namespace) -> None:  # pragma: no cover - runs on the corpus
    import numpy as np

    from wpa import attribution as A

    # no win probability is needed: a constant stands in for the model
    def constant(models: Any, fmt: str, groups: str) -> Any:
        return lambda X: np.full(len(X), 0.5)

    A.wp_model = constant
    ns = argparse.Namespace(
        **vars(a), models=None, groups="ABCDEFGHIJ", top=6, draws=6, alternatives=10
    )
    tools = A._tools(ns)
    _W.update(
        tools=tools,
        priority={f: A._priorities(tools.dexes[f]) for f in tools.dexes},
        tol=max(0.03, a.resolution + 0.01),
    )


def _one(job: tuple[str, str, str]) -> tuple[str, str, list[dict]]:  # pragma: no cover
    from wpa import attribution as A

    tag, log, fmt = job
    recs: list[dict] = []
    try:
        for ts in A.turn_setups(tag, log, fmt, _W["tools"]):
            recs += check_game([ts], _W["priority"][fmt], _W["tol"], log)
    except Exception as e:  # reported, not hidden
        why = f"error: {type(e).__name__}: {str(e)[:80]}"
        recs.append({"tag": tag, "format": fmt, "turn": None, "skipped": why})
    return tag, fmt, recs


def _expect_code(dest: Path) -> None:  # pragma: no cover
    import wpa.attribution as A

    here = Path(A.__file__).resolve().parents[1]
    if here != Path(dest).resolve():
        raise SystemExit(f"the check ran on the code in {here}, not in {dest}")


def run(a: argparse.Namespace) -> None:  # pragma: no cover - runs on the corpus
    from multiprocessing import Pool

    from wpa.policy_data import _iter_logs

    if a.expect_code:
        _expect_code(a.expect_code)
    splits = (
        json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
        if Path(a.splits).exists()
        else None
    )
    sample = load_sample(a.sample, splits)
    fmt_of = {t: f for f, ts in sample.items() for t in ts}
    label = run_label(a, _label())
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out, meta_path = out_dir / f"{label}.jsonl", out_dir / f"{label}.json"
    if a.fresh:
        for p in (out, meta_path):
            if p.exists():
                p.unlink()
    done = done_tags(out)
    print(f"The resolver check on {label}: reading the logs ...", flush=True)
    jobs = [
        (tag, log, fmt_of[tag])
        for tag, log in _iter_logs(a.logs)
        if tag in fmt_of and tag not in done
    ]
    lost = len(fmt_of) - len(done) - len(jobs)
    if lost:
        print(f"  {lost} games of the sample are not in {a.logs}", flush=True)
    left = len(jobs)
    if a.max_games:
        jobs = jobs[: a.max_games]
    print(f"{len(jobs)} games to check ({len(done)} done before)", flush=True)
    import wpa

    meta = (
        json.loads(meta_path.read_text(encoding="utf-8"))
        if meta_path.exists()
        else {"label": label, "started": time.time(), "wall": 0.0}
    )
    wall0 = meta.get("wall", 0.0)
    meta.update(workers=a.workers, code=str(Path(wpa.__file__).resolve().parent))
    t0 = time.time()

    def save_meta() -> None:
        meta["wall"] = wall0 + time.time() - t0
        meta_path.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")

    with open(out, "a", encoding="utf-8") as f, Pool(a.workers, _init, (a,)) as pool:
        for i, (tag, fmt, recs) in enumerate(pool.imap_unordered(_one, jobs), 1):
            if not recs:
                why = "no usable game"
                recs = [{"tag": tag, "format": fmt, "turn": None, "skipped": why}]
            f.write("".join(json.dumps(r) + "\n" for r in recs))
            f.flush()
            if i % 20 == 0:
                save_meta()
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)} games", flush=True)
    save_meta()
    if len(jobs) < left:
        print(f"{left - len(jobs)} games left: the same command carries on", flush=True)


def make_sample(a: argparse.Namespace) -> None:  # pragma: no cover - reads the corpus
    from wpa.attribution import sample_sets

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    games = sample_sets(a.logs, splits, {"regma": a.sets[0], "regmb": a.sets[1]})
    save_sample(
        a.sample,
        {f: [t for t, _log in gs] for f, gs in games.items()},
        f"every game of the brief's sample of validation sets ({a.sets[0]} Reg M-A, "
        f"{a.sets[1]} Reg M-B; wpa.attribution.sample_sets)",
    )
    print(
        f"saved {a.sample}: "
        + ", ".join(
            f"{FORMAT_NAMES.get(f, f)} {len(gs)} games" for f, gs in games.items()
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument(
        "--code",
        default=None,
        help="check the code of this commit (e.g. 9e9ef90) instead of today's",
    )
    p.add_argument("--report", action="store_true", help="the table of every run")
    p.add_argument("--fresh", action="store_true", help="start this run over")
    p.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="stop after this many games (a trial); the same command carries on",
    )
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--sample", type=Path, default=SAMPLE)
    p.add_argument(
        "--new-sample",
        action="store_true",
        help="make the sample (once) from the brief's sets",
    )
    p.add_argument("--sets", type=int, nargs=2, default=(300, 199))
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--bring", type=Path, default=Path("models_v4/bring.json"))
    p.add_argument("--policy", type=Path, default=Path("models_v4/policy.json"))
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--dex-tables", type=Path, default=None)
    p.add_argument("--resolution", type=float, default=0.05)
    p.add_argument(
        "--spread-hits",
        action="store_true",
        help="hits branch on the likely spreads where they decide a knock-out "
        "(Week 12 Task 4)",
    )
    p.add_argument(
        "--spread-damage",
        action="store_true",
        help="every hit's damage weighed over the likely spreads (Week 13 Task 1)",
    )
    p.add_argument("--cap", type=int, default=300)
    p.add_argument("--label", default=None, help=argparse.SUPPRESS)
    p.add_argument("--expect-code", type=Path, default=None, help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    if a.moves_dir is None and (Path("build") / "moves_regma.json").exists():
        a.moves_dir = Path("build")
    return a


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    a = parse_args(argv)
    if a.new_sample:
        make_sample(a)
        return
    if a.code and not a.report:
        root = Path.cwd()
        dest = root / "build" / f"code-{a.code}"
        print(f"Taking the code of {a.code} into {dest} ...", flush=True)
        extract_code(a.code, root, dest)
        subprocess.run(child_command(a, dest, root), cwd=dest, check=True)
    elif not a.report:
        run(a)
    if a.expect_code:
        return  # the run on a commit's code: the caller writes the table
    runs, meta = load_runs(a.out_dir)
    text = "\n".join(summary_lines(runs, meta))
    print(text)
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(a.out_dir) / "summary.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


__all__ = [
    "check_game",
    "check_turn",
    "child_command",
    "done_tags",
    "run_label",
    "extract_code",
    "load_runs",
    "load_sample",
    "save_sample",
    "summarise",
    "summary_lines",
]
