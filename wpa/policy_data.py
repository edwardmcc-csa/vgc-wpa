"""Training and validation examples for the opponent choice model (Week 9 Task 3).

`examples_for_game` walks one game's move-selection decisions (`wpa.choices.turns`)
and, for every Pokemon whose choice the log shows (target included), returns its
options' facts (`wpa.policy.option_features`) and which one it chose. Options are
offered as the opponent would see them: a switch to any Pokemon not yet fainted,
an unseen one weighted by how likely it was brought (`wpa.bring`), since the four
a player brought are not public until they appear.

`collect` (run by `python -m wpa.policy`) counts how often each move is picked
when offered (training games only), builds the examples, fits the model on
training games, scores it on validation games per format against a uniform
guess, and saves `models_v4/policy.json` and `policy.txt`. The test split is never
read.
"""

from __future__ import annotations

import gzip
import json
import pickle
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np

from wpa import choices as C
from wpa.policy import DamageInfo, fit, option_features, rates_from_counts, score

SIDE_KEYS = ("tailwind", "reflect", "lightscreen", "auroraveil")


def _iter_logs(logs_dir: Path) -> Iterator[tuple[str, str]]:
    for path in sorted(Path(logs_dir).glob("part-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                yield d["tag"], d["log"]


def count_moves(log: str, dex, counts: tuple[Counter, Counter]) -> None:
    """Add one game's offered and chosen moves (by move id) to `counts`."""
    from wpa.team_sheets import sheets_from_log

    offered, chosen = counts
    sheets = sheets_from_log(log)
    for t in C.turns(log, dex):
        if t.role not in sheets:
            continue
        opts = C.options(t.ours, t.theirs, sheets[t.role], dex)
        for idx, act in t.taken.items():
            if isinstance(act, str) or idx not in opts:
                continue
            for mv in {a.move for a in opts[idx] if a.kind == "move"}:
                offered[mv] += 1
            if act.kind == "move":
                chosen[act.move] += 1


def _timers_by_turn(game, role: str) -> dict:
    out = {}
    for s, j in zip(game.states[role], game.joined[role]):
        if s["moment"] == "turn_start" and j is not None:
            out[s["turn"]] = j
    return out


def game_tools(tag: str, log: str, fmt: str, store, bring, dex):
    """What every turn of one game shares: both sheets, each Pokemon's most
    likely spread from the usage statistics, and each side's bring odds."""
    from wpa.spreads import Belief, priors_for
    from wpa.team_sheets import sheets_from_log

    sheets = sheets_from_log(log)
    usage = store.for_game(tag, log) if store is not None else {}
    spreads = {
        k: Belief(v).best() for k, v in priors_for(sheets, usage, dex).items() if v
    }
    odds = (
        {r: bring.odds(fmt, tuple(m.species for m in sheets[r]), None) for r in sheets}
        if bring is not None and set(sheets) == {"p1", "p2"}
        else {}
    )
    return sheets, spreads, odds


def side_and_weather(j) -> tuple[set[str], str | None]:
    """The side's conditions up (those the choice model knows) and the field's
    weather, from a side's timers at a turn's start (`j`, or None)."""
    from wpa.features import _field

    side = {
        e
        for e, tt, lo, _h in (j.ours if j else ())
        if tt == "side" and lo > 0 and e in SIDE_KEYS
    }
    return side, (_field(j)["weather"] if j else None)


def turn_options(
    t: C.Turn,
    j,
    sheets,
    spreads,
    dex,
    moves,
    rates,
    calc,
    odds,
    shortcuts: Counter | None = None,
    rules=None,
) -> dict[int, tuple[list, np.ndarray]]:
    """For each Pokemon of `t.role` active at the start of the turn: its options
    and their facts (`wpa.policy.option_features`), as the opponent would see
    them. `j`: the role's timers at the turn start. `shortcuts` (the bot's
    search, Week 17): plays that cannot work are left out, and counted in it by
    rule (`wpa.shortcuts`; `rules`: which, all by default)."""
    from wpa.bring import marginals
    from wpa.features import _field

    role = t.role
    our_side, weather = side_and_weather(j)
    trickroom = any(
        e == "trickroom" and lo > 0 for e, _t, lo, _h in (j.field if j else ())
    )
    s = {"our_pokemon": t.ours, "opp_pokemon": t.theirs}
    revealed = [
        i
        for i, p in enumerate(t.ours)
        if p["active"] or p["fainted"] or p["hp_fraction"] > 0
    ]
    bring_p = marginals(odds[role], revealed) if role in odds else None
    ctx = (
        DamageInfo(s, sheets, role, spreads, dex, calc, _field(j) if j else {})
        if calc is not None
        else None
    )
    out = {}
    for idx, o in C.options(t.ours, t.theirs, sheets[role], dex).items():
        if o and shortcuts is not None:
            from wpa import shortcuts as SC

            ok = SC.keep(
                o,
                t.ours,
                our_side,
                weather,
                moves,
                shortcuts,
                SC.RULES if rules is None else rules,
            )
            o = [a for a, k in zip(o, ok) if k]
        if o:
            X = np.array(
                [
                    option_features(
                        s, a, moves, rates, ctx, our_side, trickroom, bring_p
                    )
                    for a in o
                ],
                dtype=float,
            )
            out[idx] = (list(o), X)
    return out


def examples_for_game(
    tag: str, log: str, fmt: str, dex, moves, table, calc, store, bring, rates
) -> list[tuple[np.ndarray, int]]:
    from wpa import decisions as D

    sheets, spreads, odds = game_tools(tag, log, fmt, store, bring, dex)
    if set(sheets) != {"p1", "p2"}:
        return []
    game = D.build_game(log, table)
    timers = {r: _timers_by_turn(game, r) for r in ("p1", "p2")}
    out = []
    for t in C.turns(log, dex):
        usable = {
            idx: act
            for idx, act in t.taken.items()
            if not isinstance(act, str) and idx not in t.hidden
        }
        if not usable:
            continue
        j = timers[t.role].get(t.turn)
        feats = turn_options(t, j, sheets, spreads, dex, moves, rates, calc, odds)
        for idx, act in usable.items():
            act = C.base(act)  # a switching move is listed without its switch-in
            if idx in feats and act in feats[idx][0]:
                o, X = feats[idx]
                out.append((X, o.index(act)))
    return out


def format_caps(
    formats: Sequence[str], games: Sequence[int], val_games: Sequence[int]
) -> tuple[dict[str, int], dict[str, int]]:
    """Training and validation games per format, one count for each format
    given (`--formats`, `--games`, `--val-games`)."""
    if not len(formats) == len(games) == len(val_games):
        raise SystemExit(
            f"one count of games per format: {list(formats)}, {list(games)}, "
            f"{list(val_games)}"
        )
    return dict(zip(formats, games)), dict(zip(formats, val_games))


def collect(a) -> None:  # pragma: no cover - runs on the corpus
    from wpa.bring import BringModel
    from wpa.damage import Calc
    from wpa.formats import format_of
    from wpa.spreads import UsageStore

    splits = json.loads(Path(a.splits).read_text(encoding="utf-8"))["games"]
    if getattr(a, "dex_tables", None):
        dexes, tables = pickle.load(open(a.dex_tables, "rb"))
    else:
        from wpa.durations import load_all
        from wpa.team_sheets import load_dexes

        dexes, tables = load_dexes(a.showdown), load_all(a.showdown)
    from wpa.durations import FORMAT_MODS, showdown_for
    from wpa.resolver import load_moves, load_moves_file

    # each format's moves from its own copy of Showdown's code (revision 12),
    # or from a saved file
    moves = {
        f: (
            load_moves_file(Path(a.moves_dir) / f"moves_{f}.json")
            if a.moves_dir and (Path(a.moves_dir) / f"moves_{f}.json").exists()
            else load_moves(showdown_for(f, a.showdown), mod)
        )
        for f, mod in FORMAT_MODS.items()
    }
    # the formats the choice model learns: Reg M-A and M-B together, or Reg M-C
    # alone into its own file (Week 15)
    mods = tuple(getattr(a, "formats", None) or ("regma", "regmb"))
    caps, vcaps = format_caps(mods, a.games, a.val_games)
    picked: dict[str, dict[str, list]] = {
        "train": {f: [] for f in mods},
        "validation": {f: [] for f in mods},
    }
    counts = {f: (Counter(), Counter()) for f in mods}
    for tag, log in _iter_logs(a.logs):
        split = splits.get(tag)
        if split not in picked:
            continue  # the test split is never read
        try:
            fmt = format_of(tag)
        except Exception:
            continue
        if fmt not in mods:
            continue
        cap = caps[fmt] if split == "train" else vcaps[fmt]
        if len(picked[split][fmt]) >= cap:
            continue
        picked[split][fmt].append((tag, log))
        if split == "train":
            count_moves(log, dexes[fmt], counts[fmt])
    rates = {f: rates_from_counts(counts[f][1], counts[f][0]) for f in mods}
    store = UsageStore(a.usage)
    bring = BringModel.load(a.bring) if a.bring and Path(a.bring).exists() else None
    groups: dict[str, dict[str, list]] = {"train": {}, "validation": {}}
    with Calc() as calc:
        for split in groups:
            for fmt in mods:
                g = []
                for tag, log in picked[split][fmt]:
                    g += examples_for_game(
                        tag,
                        log,
                        fmt,
                        dexes[fmt],
                        moves[fmt],
                        tables[fmt],
                        calc,
                        store,
                        bring,
                        rates[fmt],
                    )
                groups[split][fmt] = g
                print(
                    f"{split} {fmt}: {len(picked[split][fmt])} games, {len(g)} choices",
                    flush=True,
                )
    from wpa.policy import CHOICE_L2

    l2 = getattr(a, "l2", CHOICE_L2)  # Week 18: the choice model's own ridge
    model = fit([g for f in mods for g in groups["train"][f]], l2=l2)
    model.rates = rates
    a.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(a.out)
    lines = [
        "Opponent choice model (Week 9 Task 3), validation: "
        "mean log chance of the option chosen"
    ]
    for fmt in mods:
        ll, un = score(model, groups["validation"][fmt])
        top = float(
            np.mean(
                [
                    int(np.argmax(model.chances(X)) == c)
                    for X, c in groups["validation"][fmt]
                ]
            )
        )
        lines.append(
            f"  {fmt}: {len(groups['validation'][fmt])} choices; model {ll:.3f}, "
            f"uniform {un:.3f}; most likely option right {100 * top:.1f}%"
        )
    lines.append(
        "  weights: "
        + ", ".join(f"{k} {w:+.2f}" for k, w in zip(_features(), model.weights))
    )
    text = "\n".join(lines)
    print(text)
    Path(a.out).with_suffix(".txt").write_text(text + "\n", encoding="utf-8")


def _features() -> tuple[str, ...]:
    from wpa.policy import FEATURES

    return FEATURES


__all__ = ["collect", "count_moves", "examples_for_game", "game_tools", "turn_options"]
