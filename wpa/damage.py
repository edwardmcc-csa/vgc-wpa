"""The Smogon damage calculator, from Python (Week 7 Task 2).

`@smogon/calc` 0.12.0 is pinned in `calc/` (install with `npm ci --prefix calc`).
It has the Champions rules: level 50, stat points instead of EVs. `calc/bridge.js`
runs it in one long-lived Node process; this module sends it batches of
requests and caches the answers, since the same match-up comes up many times.

Everything is named by Showdown id (`kingambit`, `kowtowcleave`, `choicescarf`).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

CALC_DIR = Path(__file__).resolve().parent.parent / "calc"

WEATHER = {
    "sunnyday": "Sun",
    "raindance": "Rain",
    "sandstorm": "Sand",
    "snowscape": "Snow",
    "snow": "Snow",
    "hail": "Hail",
    "desolateland": "Harsh Sunshine",
    "primordialsea": "Heavy Rain",
    "deltastream": "Strong Winds",
}
TERRAIN = {
    "electricterrain": "Electric",
    "grassyterrain": "Grassy",
    "psychicterrain": "Psychic",
    "mistyterrain": "Misty",
}


def request(
    attacker: Mapping,
    defender: Mapping,
    move: str,
    *,
    spread: bool = False,
    crit: bool = False,
    field: Mapping | None = None,
    bp: int | None = None,
) -> dict:
    """One damage request. `field` uses Showdown ids for weather and terrain
    ("sunnyday", "electricterrain") and true/false for reflect, lightscreen,
    auroraveil, friendguard and helpinghand (on the defender's side, except
    Helping Hand)."""
    f = dict(field or {})
    if f.get("weather"):
        f["weather"] = WEATHER.get(f["weather"])
    if f.get("terrain"):
        f["terrain"] = TERRAIN.get(f["terrain"])
    out = {
        "attacker": dict(attacker),
        "defender": dict(defender),
        "move": move,
        "spread": bool(spread),
        "crit": bool(crit),
        "field": {k: v for k, v in f.items() if v},
    }
    if bp:
        out["bp"] = int(bp)  # a power the game so far decides (Week 10)
    return out


class Calc:
    """One Node process running `calc/bridge.js`, with a cache."""

    BATCH = 200  # requests per round trip, so neither pipe fills up

    def __init__(self, calc_dir: Path | str = CALC_DIR) -> None:
        self.proc = subprocess.Popen(
            ["node", str(Path(calc_dir) / "bridge.js")],
            cwd=str(calc_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.cache: dict[str, dict] = {}
        self.calls = 0  # requests actually sent to the calculator

    def run(self, requests: Sequence[Mapping]) -> list[dict]:
        keys = [json.dumps(r, sort_keys=True) for r in requests]
        todo = [k for k in dict.fromkeys(keys) if k not in self.cache]
        assert self.proc.stdin is not None and self.proc.stdout is not None
        for i in range(0, len(todo), self.BATCH):
            chunk = todo[i : i + self.BATCH]
            self.proc.stdin.write("".join(k + "\n" for k in chunk))
            self.proc.stdin.flush()
            for k in chunk:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError("the damage calculator stopped")
                self.cache[k] = json.loads(line)
            self.calls += len(chunk)
        return [self.cache[k] for k in keys]

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)

    def __enter__(self) -> Calc:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --------------------------------------------------------------------------
# Check against Showdown's own damage code
# --------------------------------------------------------------------------

STAT_IDS = ("hp", "atk", "def", "spa", "spd", "spe")
NATURES = (
    "hardy lonely brave adamant naughty bold docile relaxed impish lax timid hasty "
    "serious jolly naive modest mild quiet bashful rash calm gentle sassy careful "
    "quirky"
).split()


def random_sps(rng) -> dict[str, int]:
    """A legal Champions spread: at most 32 in a stat, 66 in all."""
    sps = dict.fromkeys(STAT_IDS, 0)
    for _ in range(66):
        open_ = [s for s in STAT_IDS if sps[s] < 32]
        sps[rng.choice(open_)] += 1
    return {k: v for k, v in sps.items() if v}


def check_cases(games, dexes, n: int, seed: int = 0) -> list[dict]:
    """`n` random match-ups from real team sheets: (tag, log) pairs in `games`,
    with random spreads, stages, status, hit points and field."""
    import random

    from wpa.formats import format_of
    from wpa.team_sheets import form_of, sheets_from_log

    rng = random.Random(seed)
    games = list(games)
    out: list[dict] = []
    while len(out) < n:
        tag, log = rng.choice(games)
        fmt = format_of(tag)
        dex = dexes[fmt]
        sheets = sheets_from_log(log)
        if len(sheets) != 2:
            continue
        a_role = rng.choice(("p1", "p2"))
        d_role = "p2" if a_role == "p1" else "p1"
        a = rng.choice(sheets[a_role])
        d = rng.choice(sheets[d_role])
        moves = [
            m
            for m in a.moves
            if dex.moves.get(m, {}).get("category") in ("Physical", "Special")
        ]
        if not moves:
            continue
        move = rng.choice(moves)

        def mon(s, side):
            m = {
                "species": s.species,
                "nature": s.nature or rng.choice(NATURES),
                "sps": random_sps(rng),
                "item": s.item,
                "ability": s.ability,
                "hp": 1.0 if rng.random() < 0.6 else round(rng.uniform(0.05, 1.0), 2),
            }
            mega = form_of(s, dex)
            if mega and mega.get("isMega") and rng.random() < 0.5:
                m["base_species"], m["base_ability"] = s.species, s.ability
                m["species"] = "".join(c for c in mega["name"].lower() if c.isalnum())
                m["ability"] = "".join(
                    c for c in mega["abilities"]["0"].lower() if c.isalnum()
                )
            if rng.random() < 0.3:
                stats = ("atk", "spa") if side == "a" else ("def", "spd")
                m["boosts"] = {rng.choice(stats): rng.choice((-2, -1, 1, 2))}
            if side == "a" and rng.random() < 0.1:
                m["status"] = "brn"
            return m

        target = dex.moves[move].get("target")
        field = {
            "weather": rng.choice(list(WEATHER)[:4]) if rng.random() < 0.2 else None,
            "terrain": rng.choice(list(TERRAIN)) if rng.random() < 0.15 else None,
            "reflect": rng.random() < 0.1,
            "lightscreen": rng.random() < 0.1,
        }
        r = request(
            mon(a, "a"),
            mon(d, "d"),
            move,
            spread=target in ("allAdjacent", "allAdjacentFoes") and rng.random() < 0.5,
            crit=rng.random() < 0.1,
            field=field,
        )
        r["format"] = tag.split("-")[0]
        out.append(r)
    return out


BLOCKS_PRIORITY = {"armortail", "queenlymajesty", "dazzling"}
BLOCKS_MOVES = {"soundproof", "bulletproof"}  # sound moves, ball and bomb moves
PRIORITY_MOVES = {
    "suckerpunch",
    "aquajet",
    "bulletpunch",
    "quickattack",
    "feint",
    "fakeout",
    "extremespeed",
    "machpunch",
    "iceshard",
    "shadowsneak",
    "vacuumwave",
    "accelerock",
    "jetpunch",
    "firstimpression",
    "grassyglide",
    "thunderclap",
    "upperhand",
}


def blocked(case: Mapping, calc: Mapping) -> bool:
    """Showdown's getDamage does not check what stops a move before it hits
    (Psychic Terrain, Armor Tail, Queenly Majesty and Dazzling against priority;
    Soundproof, Bulletproof); the calculator does, and gives no damage."""
    if set(calc.get("rolls", [1])) != {0}:
        return False
    ability = case["defender"].get("ability")
    priority = case["move"] in PRIORITY_MOVES and (
        case["field"].get("terrain") == "Psychic" or ability in BLOCKS_PRIORITY
    )
    return priority or ability in BLOCKS_MOVES


def summarise_check(results: Sequence[Mapping]) -> dict:
    from collections import Counter

    c: Counter[str] = Counter()
    mismatches = []
    for r in results:
        fmt = "regmb" if "regmb" in r["case"]["format"] else "regma"
        sd, calc = r["showdown"], r["calc"]
        if "skip" in sd:
            c[f"{fmt} skipped: {sd['skip']}"] += 1
            continue
        if "error" in sd or "error" in calc:
            c[f"{fmt} error"] += 1
            mismatches.append(r)
            continue
        c[f"{fmt} compared"] += 1
        if sd.get("first_hit_only"):
            c[f"{fmt} ... of which several hits (first hit compared)"] += 1
            calc = {**calc, "rolls": calc.get("first_hit") or calc["rolls"]}
        if sorted(sd["rolls"]) == sorted(calc["rolls"]):
            c[f"{fmt} every roll the same"] += 1
        elif calc.get("unknown"):
            c[f"{fmt} the calculator does not know this move"] += 1
            mismatches.append(r)
        elif blocked(r["case"], calc):
            c[f"{fmt} the calculator blocks the move (right in game)"] += 1
        else:
            c[f"{fmt} differ"] += 1
            mismatches.append(r)
    return {"counts": dict(sorted(c.items())), "mismatches": mismatches}


def main() -> None:
    import argparse
    import gzip
    import tempfile

    p = argparse.ArgumentParser(description="Check the damage calculator (Task 2).")
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--shards", type=int, default=4, help="log shards to draw from")
    p.add_argument("--out", type=Path, default=Path("calc_check.json"))
    p.add_argument("--format", default="", help="only games of this format")
    a = p.parse_args()
    from wpa.team_sheets import load_dexes

    splits = json.loads(a.splits.read_text(encoding="utf-8"))["games"]
    games = []
    for path in sorted(a.logs.glob("part-*.jsonl.gz"))[: a.shards]:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if splits.get(d["tag"]) == "validation" and a.format in d["tag"]:
                    games.append((d["tag"], d["log"]))
    cases = check_cases(games, load_dexes(a.showdown), a.n)
    with tempfile.TemporaryDirectory() as tmp:
        cpath = Path(tmp) / "cases.json"
        cpath.write_text(json.dumps(cases), encoding="utf-8")
        subprocess.run(
            [
                "node",
                str(CALC_DIR / "check_showdown.js"),
                str(a.showdown),
                str(cpath),
                str(a.out),
            ],
            check=True,
        )
    s = summarise_check(json.loads(a.out.read_text(encoding="utf-8")))
    for k, v in s["counts"].items():
        print(f"{k}: {v}")
    keys = ("item", "ability", "boosts", "status", "hp")
    for r in s["mismatches"][:15]:
        c = r["case"]
        att = {k: c["attacker"].get(k) for k in keys}
        dfn = {k: c["defender"].get(k) for k in keys}
        print(
            f"- {c['attacker']['species']} {c['move']} -> {c['defender']['species']} "
            f"spread={c['spread']} crit={c['crit']} field={c['field']}\n"
            f"    attacker {att}\n    defender {dfn}\n"
            f"    showdown {r['showdown'].get('rolls', r['showdown'])}\n"
            f"    calc     {r['calc'].get('rolls', r['calc'])}"
        )


if __name__ == "__main__":
    main()
