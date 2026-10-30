"""Our own decision table, built from the logs (Week 6 Task 1).

The stored states (`wpa_states/`) skip a player's decision when one of their
slots did nothing and one of their Pokemon fainted during that turn, which
depends on what happens *after* the decision (Week 5 report, surprise 2). This
module builds every decision point from the game's own structure instead:

* **preview**: team preview, both players;
* **turn_start**: the start of every turn, both players;
* **after_turn**: after the turn's residual, a player with an empty slot and a
  Pokemon left to send in (decided from the board, not from what follows);
* **mid_turn**: a switch during the turn (after U-turn, Eject Button ...), for
  the player who switches.

At each point it records the board the way a stored state shows it (species,
hit points, fainted, active, in sheet order; a Pokemon never seen shows 0 hit
points), the timers in force there (`wpa.timers`), and the end-of-turn field
conditions as observations for later turns. The last state of each player is a
terminal one carrying the result from the `|win|` line (a forfeit included).

`compare_with_stored` checks the board against the stored states wherever the
old log reader also took a snapshot.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from wpa.durations import AFTER_RESIDUAL, Durations
from wpa.sheets import parse_showteam_message
from wpa.timer_join import JoinedTimers, orient
from wpa.timers import DecisionTimers, _acts, _moment, _Walker

ROLES = ("p1", "p2")
BRING = 4

_BESTOF = re.compile(
    r"<strong>Game (\d+)</strong> of <a href=\"/game-bestof3-([^\"]+)\""
)
_SCORE = re.compile(
    r"<tr><td align=\"left\">(?P<p1>.*?)</td>"
    r"<td align=\"right\">(?P<p2>.*?)</tr></table>"
)


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


_HP = re.compile(r"(\d+(?:\.\d+)?)(?:/(\d+(?:\.\d+)?))?")


def _hp(text: str) -> tuple[float, bool]:
    """'55/100 par' -> (0.55, False); '0 fnt' -> (0.0, True). Tolerates stray
    characters after the numbers (one real log has '20/100y')."""
    fainted = "fnt" in text
    m = _HP.match(text.strip())
    if not m:
        return 0.0, fainted
    num = float(m.group(1))
    den = float(m.group(2)) if m.group(2) else 100.0
    return (num / den if den else 0.0), fainted or num == 0


STATUSES = ("brn", "par", "slp", "frz", "psn", "tox")
STATS = ("atk", "def", "spa", "spd", "spe", "accuracy", "evasion")


def _status(text: str) -> str:
    """'55/100 par' -> 'par'; '100/100' or '0 fnt' -> ''."""
    for tok in text.split()[1:]:
        if tok in STATUSES:
            return tok
    return ""


def _clamp(n: int) -> int:
    return max(-6, min(6, n))


_EFFECT_LINES = {
    "-boost",
    "-unboost",
    "-setboost",
    "-clearboost",
    "-clearnegativeboost",
    "-clearpositiveboost",
    "-invertboost",
    "-copyboost",
    "-swapboost",
    "-status",
    "-curestatus",
    "-cureteam",
    "-enditem",
    "-item",
}


class _Board:
    def __init__(self) -> None:
        self.names: dict[str, list[str]] = {}
        self.species: dict[str, list[str]] = {}
        self.mons: dict[str, list[dict]] = {}
        self.slots: dict[str, dict[str, int | None]] = {
            r: {"a": None, "b": None} for r in ROLES
        }
        # the name the log uses for a Pokemon (often its species, not the sheet
        # name), learned when it switches in
        self.seen_as: dict[str, dict[str, int]] = {r: {} for r in ROLES}
        self.abilities: dict[str, list[str]] = {}
        # for the real-data check: lines seen, stages that would pass +-6, and
        # whether each Intimidate lowered every opposing active Pokemon's Attack
        self.counts: Counter[str] = Counter()
        self._intimidate: list | None = None

    def sheet(self, line: str) -> None:
        role, mons = parse_showteam_message(line)
        self.names[role] = [m.name for m in mons]
        self.abilities[role] = [to_id(m.ability) for m in mons]
        self.species[role] = [to_id(m.species) for m in mons]
        self.mons[role] = [
            {
                "hp": 0.0,
                "fainted": False,
                "active": False,
                "seen": False,
                "mega": False,
                "boosts": {},
                "status": "",
                "item": to_id(m.item),
            }
            for m in mons
        ]

    def _mon(self, ident: str) -> dict | None:
        role = ident[:2]
        if role not in self.mons:
            return None
        idx = self._index(role, ident)
        return None if idx is None else self.mons[role][idx]

    def _effects(self, t: str, p: list[str]) -> bool:
        """Stat stages, status and items. True if the line was one of these."""
        if t == "-clearallboost":
            for mons in self.mons.values():
                for m in mons:
                    m["boosts"] = {}
            return True
        if t not in _EFFECT_LINES or len(p) < 3:
            return False
        self.counts[t] += 1
        m = self._mon(p[2])
        if m is None:
            self.counts["unmatched_" + t] += 1
            return True
        b = m["boosts"]
        touched = [m]
        if t in ("-boost", "-unboost", "-setboost") and len(p) > 4:
            stat, n = p[3], int(p[4]) if p[4].lstrip("-").isdigit() else 0
            if stat in STATS:
                new = (
                    n
                    if t == "-setboost"
                    else b.get(stat, 0) + (n if t == "-boost" else -n)
                )
                self.counts["stage_outside_6"] += new != _clamp(new)
                b[stat] = _clamp(new)
        elif t == "-clearboost":
            m["boosts"] = {}
        elif t == "-clearnegativeboost":
            m["boosts"] = {k: v for k, v in b.items() if v > 0}
        elif t == "-clearpositiveboost":
            m["boosts"] = {k: v for k, v in b.items() if v < 0}
        elif t == "-invertboost":
            m["boosts"] = {k: -v for k, v in b.items()}
        elif t in ("-copyboost", "-swapboost") and len(p) > 3:
            other = self._mon(p[3])
            if other is None:
                return True
            if t == "-copyboost":
                m["boosts"] = dict(other["boosts"])
            else:
                stats = STATS
                if len(p) > 4 and p[4] and not p[4].startswith("["):
                    stats = tuple(s.strip() for s in p[4].split(","))
                mine, theirs = dict(b), dict(other["boosts"])
                for s in stats:
                    mine[s], theirs[s] = other["boosts"].get(s, 0), b.get(s, 0)
                m["boosts"] = mine
                other["boosts"] = theirs
                touched.append(other)
        elif t == "-status" and len(p) > 3:
            m["status"] = p[3] if p[3] in STATUSES else m["status"]
        elif t == "-curestatus":
            m["status"] = ""
        elif t == "-cureteam":
            for x in self.mons[p[2][:2]]:
                x["status"] = ""
        elif t == "-enditem":
            m["item"] = ""
        elif t == "-item" and len(p) > 3:
            m["item"] = to_id(p[3])
        for x in touched:  # keep only the stages that are not zero
            x["boosts"] = {k: v for k, v in x["boosts"].items() if v}
        return True

    def _index(self, role: str, ident: str, details: str = "") -> int | None:
        names = self.names.get(role, [])
        nick = ident.split(": ", 1)[-1]
        if nick in self.seen_as.get(role, {}):
            return self.seen_as[role][nick]
        if nick in names:
            return names.index(nick)
        if details:
            sp = to_id(details.split(",")[0])
            hits = [
                i
                for i, s in enumerate(self.species.get(role, []))
                if sp.startswith(s) or s.startswith(sp)
            ]
            if len(hits) == 1:
                return hits[0]
        return None

    def _check_intimidate(self, p: list[str]) -> None:
        t = p[1]
        opens = (
            t == "-ability"
            and len(p) > 4
            and to_id(p[3]) == "intimidate"
            and p[4] == "boost"
            and p[2][:2] in ROLES
        )
        it = self._intimidate
        if it is not None and not opens:
            if t == "-unboost" and len(p) > 3 and p[2][:2] == it[0] and p[3] == "atk":
                it[2] += 1
                return
            if t == "-ability" and len(p) > 3:  # Defiant, Mirror Armor, ...
                it[3].append(f"ability: {p[3]}")
                return
            if t in (
                "-fail",
                "-immune",
                "-activate",
                "-item",
                "-boost",
                "-miss",
                "-block",
            ):
                src = next((x for x in p[3:] if x.startswith("[from]")), t)
                it[3].append(src)
                return
        self.close_intimidate()
        if opens:
            target = "p2" if p[2][:2] == "p1" else "p1"
            n = sum(m["active"] and not m["fainted"] for m in self.mons.get(target, []))
            self._intimidate = [target, n, 0, []]

    def close_intimidate(self) -> None:
        it, self._intimidate = self._intimidate, None
        if it is None:
            return
        if it[2] == it[1]:
            self.counts["intimidate_all_lowered"] += 1
        else:
            self.counts["intimidate_not_all_lowered"] += 1
            for why in it[3] or ["(nothing shown)"]:
                self.counts["  because " + why] += 1

    def handle(self, p: list[str]) -> None:
        if len(p) > 1:
            self._check_intimidate(p)
        if len(p) > 1 and self._effects(p[1], p):
            return
        if len(p) < 3:
            return
        t = p[1]
        ident = p[2]
        role = ident[:2]
        if role not in self.mons:
            return
        if t in ("switch", "drag") and len(p) > 4:
            slot = ident[2:3]
            idx = self._index(role, ident, p[3])
            if idx is None or slot not in ("a", "b"):
                return
            self.seen_as[role][ident.split(": ", 1)[-1]] = idx
            old = self.slots[role][slot]
            passed: dict = {}
            if old is not None and old != idx:
                if any(x == "[from] Baton Pass" for x in p[5:]):
                    passed = dict(self.mons[role][old]["boosts"])
                self.mons[role][old]["active"] = False
                self.mons[role][old]["boosts"] = {}
                # Regenerator heals a third on switching out; the log does not
                # print it (the stored states apply it too)
                if self.abilities.get(role, [""] * 6)[old] == "regenerator":
                    o = self.mons[role][old]
                    if not o["fainted"]:
                        o["hp"] = min(1.0, round(o["hp"] + 1 / 3, 2))
            m = self.mons[role][idx]
            m["active"] = True
            m["seen"] = True
            m["hp"], fainted = _hp(p[4])
            m["fainted"] = m["fainted"] or (fainted and m["hp"] == 0)
            m["status"] = _status(p[4])
            m["boosts"] = passed
            self.slots[role][slot] = idx
        elif t in ("-damage", "-heal", "-sethp") and len(p) > 3:
            idx = self._index(role, ident)
            if idx is not None:
                m = self.mons[role][idx]
                m["hp"], fainted = _hp(p[3])
                m["status"] = "" if fainted else _status(p[3])
        elif t == "faint":
            idx = self._index(role, ident)
            if idx is not None:
                m = self.mons[role][idx]
                m.update(hp=0.0, fainted=True, active=False, boosts={}, status="")
                for s, v in self.slots[role].items():
                    if v == idx:
                        self.slots[role][s] = None
        elif t == "-mega":
            idx = self._index(role, ident)
            if idx is not None:
                self.mons[role][idx]["mega"] = True
        elif t == "swap":
            a, b = self.slots[role]["a"], self.slots[role]["b"]
            self.slots[role]["a"], self.slots[role]["b"] = b, a
        elif t == "replace" and len(p) > 3:
            slot = ident[2:3]
            idx = self._index(role, ident, p[3])
            old = self.slots[role].get(slot)
            if idx is not None and slot in ("a", "b"):
                if old is not None and old != idx:
                    self.mons[role][idx]["hp"] = self.mons[role][old]["hp"]
                    self.mons[role][old]["active"] = False
                self.mons[role][idx].update(active=True, seen=True)
                self.slots[role][slot] = idx

    def side(self, role: str) -> list[dict]:
        return [
            {
                "species": sp,
                "hp_fraction": (m["hp"] if m["seen"] and not m["fainted"] else 0.0),
                "fainted": m["fainted"],
                "active": m["active"],
                "gimmick": None,
                "mega": m["mega"],
                "boosts": dict(m["boosts"]),
                "status": m["status"],
                "item": m["item"],
            }
            for sp, m in zip(self.species.get(role, []), self.mons.get(role, []))
        ]

    def needs_replacement(self, role: str) -> bool:
        mons = self.mons.get(role, [])
        fainted = sum(m["fainted"] for m in mons)
        active = sum(m["active"] and not m["fainted"] for m in mons)
        left = BRING - fainted - active
        return active < 2 and left > 0


@dataclass
class Game:
    states: dict[str, list[dict]] = field(default_factory=dict)
    joined: dict[str, list[JoinedTimers | None]] = field(default_factory=dict)
    recorded: dict[str, list[bool]] = field(default_factory=dict)
    points: dict[str, list[int]] = field(default_factory=dict)
    # boards where the old log reader took a snapshot (for validation)
    logreader: dict[str, list[dict]] = field(default_factory=dict)
    # stat stage, status and item lines seen (for the real-data check)
    effects: Counter = field(default_factory=Counter)


def _set_fields(
    log: str, role: str
) -> tuple[str | None, int | None, tuple[int, int] | None]:
    m = _BESTOF.search(log)
    if not m:
        return None, None, None
    score = None
    s = _SCORE.search(log)
    if s:
        a = s.group("p1").count('fa fa-circle"')
        b = s.group("p2").count('fa fa-circle"')
        score = (a, b) if role == "p1" else (b, a)
    return m.group(2), int(m.group(1)), score


def _context(walker: _Walker) -> dict:
    weather = None
    fields: list[str] = []
    sides: list[str] = []
    for key in walker.active:
        if key[0] == "weather":
            weather = key[1]
        elif key[0] == "field":
            fields.append(key[1])
        elif key[0] == "side":
            sides.append(f"{key[2]}:{key[1]}")
    return {
        "turn": walker.turn,
        "weather": weather,
        "fields": sorted(fields),
        "side_conditions": sorted(sides),
    }


def build_game(log: str, table: Durations) -> Game:
    walker = _Walker(table)
    board = _Board()
    players = {}
    for line in log.split("\n"):
        if line.startswith("|player|"):
            p = line.split("|")
            # a reconnect repeats the line with no name: keep the first
            if len(p) > 3 and p[2] in ROLES and p[3] and p[2] not in players:
                players[p[2]] = p[3]
    raw: dict[str, list[tuple]] = {r: [] for r in ROLES}
    lr: dict[str, list[tuple[int, dict]]] = {r: [] for r in ROLES}
    contexts: dict[int, dict] = {}
    winner = None
    over = False
    pending_start: int | None = None
    emitted_after: dict[str, tuple[int, int]] = {}

    def snap(role: str, point: int, moment: str) -> None:
        timers, counters = walker.now()
        raw[role].append(
            (
                point,
                walker.turn,
                moment,
                board.side(role),
                board.side("p2" if role == "p1" else "p1"),
                timers,
                counters,
            )
        )

    for i, block in enumerate(log.split("\n|\n")):
        if i > 0:
            walker.feed("|")
        lines = block.split("\n")
        if i == 1:
            for r in ROLES:
                snap(r, i, "preview")
        elif i >= 2 and not over:
            moment = _moment(walker)
            if pending_start is not None:
                # the first block after |turn|N: both players choose, whatever
                # chat, timer or reconnect lines came in between
                pending_start = None
                for r in ROLES:
                    snap(r, i, "turn_start")
            elif walker.phase == AFTER_RESIDUAL:
                for r in ROLES:
                    fainted = sum(m["fainted"] for m in board.mons.get(r, []))
                    if board.needs_replacement(r) and emitted_after.get(r) != (
                        walker.turn,
                        fainted,
                    ):
                        emitted_after[r] = (walker.turn, fainted)
                        snap(r, i, "after_turn")
            elif moment == "mid_turn":
                first_move = next(
                    (k for k, x in enumerate(lines) if x.startswith("|move|")),
                    len(lines),
                )
                for r in ROLES:
                    if any(x.startswith(f"|switch|{r}") for x in lines[:first_move]):
                        snap(r, i, "mid_turn")
            # where the old log reader would have taken its snapshots
            if "|switch|" in block or "|move|" in block:
                for r in ROLES:
                    a, b = _acts(lines, r)
                    if (a and b) or ((a or b) and f"|faint|{r}" not in block):
                        lr[r].append(
                            (
                                i,
                                {
                                    "turn": walker.turn,
                                    "our": board.side(r),
                                    "opp": board.side("p2" if r == "p1" else "p1"),
                                },
                            )
                        )
        for line in lines:
            p = line.split("|")
            if len(p) > 1:
                if p[1] == "showteam":
                    board.sheet(line)
                elif p[1] == "turn" and len(p) > 2:
                    contexts[int(p[2]) - 1] = _context(walker)
                    pending_start = int(p[2])
                elif p[1] == "win" and len(p) > 2:
                    winner = p[2]
                    over = True
                elif p[1] == "tie":
                    over = True
                board.handle(p)
            walker.feed(line)
    walker.flush()
    board.close_intimidate()

    game = Game(effects=board.counts)
    for r in ROLES:
        set_id, game_index, score = _set_fields(log, r)
        states: list[dict] = []
        joined: list[JoinedTimers | None] = []
        points: list[int] = []
        last_turn, index = None, 0
        for point, turn, moment, ours, theirs, timers, counters in raw[r]:
            index = index + 1 if turn == last_turn else 0
            last_turn = turn
            states.append(
                {
                    "turn": turn,
                    "decision_index": index,
                    "moment": moment,
                    "our_pokemon": ours,
                    "opp_pokemon": theirs,
                    "outcome": None,
                    "set_id": set_id,
                    "game_index": game_index,
                    "set_score_entering_game": score,
                    "observations": [],
                }
            )
            joined.append(
                orient(DecisionTimers(turn, index, timers, counters, moment), r)
            )
            points.append(point)
        # end-of-turn conditions, offered to later turns
        for turn, ctx in contexts.items():
            last = max(
                (k for k, s in enumerate(states) if s["turn"] == turn), default=None
            )
            if last is not None:
                states[last]["observations"].append(ctx)
        outcome = None if winner is None else (winner == players.get(r))
        final_turn = states[-1]["turn"] if states else 0
        states.append(
            {
                "turn": final_turn,
                "decision_index": (states[-1]["decision_index"] + 1) if states else 0,
                "moment": "terminal",
                "our_pokemon": board.side(r),
                "opp_pokemon": board.side("p2" if r == "p1" else "p1"),
                "outcome": outcome,
                "set_id": set_id,
                "game_index": game_index,
                "set_score_entering_game": score,
                "observations": [],
            }
        )
        joined.append(None)
        lr_points = {pt for pt, _ in lr[r]}
        game.states[r] = states
        game.joined[r] = joined
        game.points[r] = points
        game.recorded[r] = [
            pt in lr_points or s["moment"] == "preview" for pt, s in zip(points, states)
        ]
        game.logreader[r] = [b for _, b in lr[r]]
    return game


@dataclass
class Comparison:
    compared: int = 0
    mismatched: int = 0
    examples: list = field(default_factory=list)


def compare_with_stored(game: Game, role: str, stored: list[dict]) -> Comparison:
    """Compare our board with the stored states where the old reader took one."""
    out = Comparison()
    ours = game.logreader[role]
    theirs = [s for s in stored[:-1] if s["turn"] > 0]
    if len(ours) != len(theirs):
        out.mismatched += 1
        out.examples.append(("count", len(ours), len(theirs)))
        return out
    for a, b in zip(ours, theirs):
        for side_a, side_b in (
            (a["our"], b["our_pokemon"]),
            (a["opp"], b["opp_pokemon"]),
        ):
            for x, y in zip(side_a, side_b):
                out.compared += 1
                same = (
                    abs(x["hp_fraction"] - y["hp_fraction"]) < 0.006
                    and x["fainted"] == y["fainted"]
                    and x["active"] == y["active"]
                )
                if not same:
                    out.mismatched += 1
                    if len(out.examples) < 5:
                        out.examples.append((b["turn"], b["decision_index"], x, y))
    return out


def main() -> None:
    """Check the decision table against the stored states on a sample of games."""
    import argparse
    import json
    from collections import Counter
    from pathlib import Path

    from wpa.durations import Durations
    from wpa.state_timing import in_sample
    from wpa.timers import iter_log_file

    p = argparse.ArgumentParser(description="Check our decision table (Week 6 Task 1).")
    p.add_argument("--logs", type=Path, default=Path("battle_logs"))
    p.add_argument("--states", type=Path, default=Path("wpa_states"))
    p.add_argument("--one-in", type=int, default=100)
    p.add_argument("--files", nargs="*")
    a = p.parse_args()
    empty = Durations("none", timed={})
    c: dict[str, Counter] = {}
    effects: dict[str, Counter] = {}
    examples: list = []
    paths = sorted(a.logs.glob("logs_*.json"))
    if a.files:
        paths = [x for x in paths if x.name in a.files]
    for path in paths:
        for tag, (_ts, log) in iter_log_file(path):
            if not in_sample(f"{tag}-p1.json", a.one_in):
                continue
            fmt = (
                tag.split("-")[0]
                .removeprefix("gen9championsvgc2026")
                .removesuffix("bo3")
            )
            k = c.setdefault(fmt, Counter())
            g = build_game(log, empty)
            k["games"] += 1
            e = effects.setdefault(fmt, Counter())
            e.update(g.effects)
            for role in ROLES:
                for s in g.states[role]:
                    for m in s["our_pokemon"]:
                        for v in m["boosts"].values():
                            e["stage_seen_outside_6"] += not -6 <= v <= 6
            for role in ROLES:
                f = a.states / f"{tag}-{role}.json"
                states = g.states[role]
                if states[-1]["outcome"] is None:
                    k["no_result"] += 1
                    continue
                won = int(states[-1]["outcome"])
                for s in states[:-1]:
                    k[f"rows_{s['moment']}"] += 1
                    k["rows"] += 1
                    k["won_rows"] += won
                    if s["moment"] == "turn_start":
                        k["won_turn_start"] += won
                k["recorded"] += sum(g.recorded[role])
                if f.exists():
                    stored = json.loads(f.read_text(encoding="utf-8"))
                    r = compare_with_stored(g, role, stored)
                    k["files_compared"] += 1
                    k["cells"] += r.compared
                    k["cells_mismatched"] += r.mismatched
                    k["files_with_mismatch"] += r.mismatched > 0
                    if r.mismatched and len(examples) < 8:
                        examples.append((tag, role, r.examples[:1]))
    for fmt, k in sorted(c.items()):
        rows = k["rows"] or 1
        ts = k["rows_turn_start"] or 1
        print(
            f"{fmt}: {k['games']} games, {k['rows']} decision points "
            f"(turn start {k['rows_turn_start']}, after turn {k['rows_after_turn']}, "
            f"mid turn {k['rows_mid_turn']}, preview {k['rows_preview']}); the old "
            f"reader kept {k['recorded']}"
        )
        print(
            f"  label rate: all rows {k['won_rows'] / rows:.4f}, turn-start rows "
            f"{k['won_turn_start'] / ts:.4f}; games without a result {k['no_result']}"
        )
        print(
            f"  board against stored states: {k['files_compared']} files, "
            f"{k['cells']} Pokemon compared, {k['cells_mismatched']} differ "
            f"({k['cells_mismatched'] / (k['cells'] or 1):.3%}); files with any "
            f"difference {k['files_with_mismatch']}"
        )
        print("  stat stage, status and item lines:")
        for name, n in sorted(effects.get(fmt, Counter()).items()):
            print(f"    {name}: {n}")
    for e in examples:
        print("example:", e)


if __name__ == "__main__":
    main()
