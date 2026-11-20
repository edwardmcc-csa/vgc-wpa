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
CHOICE_ITEMS = {"choiceband", "choicescarf", "choicespecs"}
# moves that share Protect's counter: each one in a row works a third as often
PROTECT_MOVES = {
    "protect",
    "detect",
    "spikyshield",
    "kingsshield",
    "banefulbunker",
    "silktrap",
    "burningbulwark",
    "obstruct",
    "maxguard",
    "endure",
}


def _status(text: str) -> str:
    """'55/100 par' -> 'par'; '100/100' or '0 fnt' -> ''."""
    for tok in text.split()[1:]:
        if tok in STATUSES:
            return tok
    return ""


def _clamp(n: int) -> int:
    return max(-6, min(6, n))


# Week 11 Task 3: lines that start or end what the board tracks beside status
_VOLATILE_LINES = frozenset(
    {
        "-status",
        "-curestatus",
        "cant",
        "-start",
        "-end",
        "-activate",
        "-prepare",
        "-anim",
        "-enditem",
        "-damage",
        "-ability",
        "-singlemove",
        "-transform",
        "-mustrecharge",
    }
)
# Week 13: hazards and the most layers of each
HAZARD_LAYERS = {"stealthrock": 1, "spikes": 3, "toxicspikes": 2, "stickyweb": 1}
# Week 13: what the board keeps besides, each ended by leaving the field
WEEK13 = (
    "ability",
    "cursed",
    "stockpile",
    "saltcure",
    "healblock",
    "focusenergy",
    "imprison",
    "destinybond",
    "attract",
    "transform",
    "moves",
    "recharge",
    "glaiverush",
    "flashfire",  # Week 14
    "bound_by",  # Week 14: who bound it (the bind ends when that one is gone)
)
# what leaving the field ends (Rage Fist's hits too, in Champions; the Toxic
# count starts again; Leech Seed, Taunt, Yawn and Disable end)
LEAVING = (
    "confused",
    "charging",
    "encore",
    "hits",
    "tox_n",
    "seeded",
    "taunt",
    "drowsy",
    "disabled",
    "types",
    "typeadd",
    "protean",
    "bound",
    *WEEK13,
)
# what `side` passes on when present
TRACKED = (
    "slp_n",
    "frz_n",
    "confused",
    "charging",
    "encore",
    "tox_n",
    "seeded",
    "taunt",
    "drowsy",
    "disabled",
    "types",
    "typeadd",
    "protean",
    "bound",
    *WEEK13,
    "eaten",  # Week 14: the Berry it ate, for Harvest (leaving does not end it)
)
# the moves that bind (an eighth at each end of turn, for 4 or 5 turns)
BINDING = {
    "bind",
    "wrap",
    "firespin",
    "whirlpool",
    "sandtomb",
    "clamp",
    "infestation",
    "magmastorm",
    "snaptrap",
    "thundercage",
}

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
        # each one's moves, from the sheet (what Transform copies, Week 13)
        self.movesets: dict[str, list[tuple[str, ...]]] = {}
        # each one's gender, from team preview (before the sheets in the log)
        self.preview: dict[tuple[str, str], str] = {}
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
        self._protecting: dict | None = None  # the Pokemon whose Protect is pending
        self._fakeout: tuple | None = None  # a Fake Out just used, for the check
        self._last: list[str] | None = None  # the line before (a substitute paid for)
        self._mover: int | None = None  # sheet position of the last Pokemon to move
        self._mover_at: tuple[str, str] | None = None  # its side and place (a, b)
        # Week 13: hazards on each side (layers); the timers keep only what
        # has a length
        self.hazards: dict[str, dict[str, int]] = {r: {} for r in ROLES}

    def sheet(self, line: str) -> None:
        role, mons = parse_showteam_message(line)
        self.names[role] = [m.name for m in mons]
        self.abilities[role] = [to_id(m.ability) for m in mons]
        self.species[role] = [to_id(m.species) for m in mons]
        self.movesets[role] = [tuple(to_id(x) for x in m.moves) for m in mons]
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
                # since it last came in (Week 8): Fake Out, Choice lock, Protect
                "moved": False,
                "last_move": "",
                "protect_streak": 0,
                # what the log has shown of its set (for blanked sheets)
                "rev_moves": set(),
                "rev_item": "",
                "rev_ability": "",
                **(
                    {"gender": self.preview[(role, to_id(m.species))]}
                    if (role, to_id(m.species)) in self.preview
                    else {}
                ),
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
            if len(p) > 3 and "[eat]" in p[4:]:
                m["eaten"] = to_id(p[3])  # Week 14: Harvest can bring it back
        elif t == "-item" and len(p) > 3:
            if to_id(p[3]) != m["item"]:
                m["last_move"] = ""  # a new Choice item locks from the next move
            m["item"] = to_id(p[3])
            if "[from] ability: Harvest" in p[4:]:
                m.pop("eaten", None)
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

    def _reveal(self, p: list[str]) -> None:
        """Items and abilities the line shows: `[from] item: X` / `[from] ability:
        X` belong to the `[of]` Pokemon if there is one, else to the line's own;
        `-ability`, `-item`, `-enditem` and `-mega` show the line's Pokemon's."""
        own = self._mon(p[2]) if len(p) > 2 and p[2][:2] in ROLES else None
        of = next((x[5:] for x in p[3:] if x.startswith("[of] ")), None)
        holder = self._mon(of) if of else own
        for x in p[3:]:
            if holder is not None and x.startswith("[from] item: "):
                holder["rev_item"] = to_id(x[len("[from] item: ") :])
            elif holder is not None and x.startswith("[from] ability: "):
                holder["rev_ability"] = to_id(x[len("[from] ability: ") :])
        if own is None or len(p) < 4:
            return
        t = p[1]
        if t == "-ability" and not any(x.startswith("[from]") for x in p[4:]):
            own["rev_ability"] = to_id(p[3])
        elif t in ("-item", "-enditem"):
            own["rev_item"] = to_id(p[3])
        elif t == "-mega" and len(p) > 4:
            own["rev_item"] = to_id(p[4])

    def _volatiles(self, p: list[str]) -> None:
        """Week 11 Task 3: the tries spent asleep or frozen (the Champions rules
        end both by the third), confusion and its tries, a charging move, and
        Encore with the move it locks. After Week 11: the turns badly poisoned
        (the Toxic count), Leech Seed and the seeder's place (`side` gives the
        Pokemon there),
        Taunt, Yawn (it falls asleep at the end of the next turn), and the move
        Disable stops."""
        m = self._mon(p[2])
        if m is None:
            return
        t = p[1]
        what = to_id(p[3].removeprefix("move: ")) if len(p) > 3 else ""
        if t == "-mustrecharge":
            m["recharge"] = 1  # Meteor Assault and the like: it rests next turn
            return
        if t == "cant":
            m.pop("glaiverush", None)  # it tried to move: Glaive Rush is over
            if what == "recharge":
                m.pop("recharge", None)
        if t == "-damage":
            # badly poisoned: each end of turn's damage counts one more
            if len(p) > 4 and "[from] psn" in p[4:] and p[3].endswith("tox"):
                m["tox_n"] = m.get("tox_n", 0) + 1
            return
        if t in ("-status", "-curestatus"):
            m.pop("slp_n", None)  # a new status, or none, starts the count again
            m.pop("frz_n", None)
            m.pop("tox_n", None)
            m.pop("drowsy", None)
        elif t == "cant" and what in ("slp", "frz"):
            m[what + "_n"] = m.get(what + "_n", 0) + 1
        elif t == "-start" and what == "confusion":
            m["confused"] = 0
        elif t == "-activate" and what == "confusion" and "confused" in m:
            m["confused"] += 1
        elif t == "-end" and what == "confusion":
            m.pop("confused", None)
        elif t == "-prepare" and what:
            m["charging"] = what
        elif t == "-anim" and what and m.get("charging") == what:
            # it went off in the same action (Electro Shot in rain, Solar Beam
            # in sun): no charge is left (Week 17)
            m.pop("charging", None)
        elif t == "-enditem" and what == "powerherb":
            m.pop("charging", None)  # it went off at once
        elif t == "-start" and what == "encore":
            m["encore"] = m.get("last_move") or ""
        elif t == "-start" and what == "abilityflashfire":
            m["flashfire"] = 1  # its Fire moves x1.5 until it leaves (Week 14)
        elif t == "-end" and what == "encore":
            m.pop("encore", None)
        elif t == "-start" and what == "leechseed":
            # the seeder's place: Showdown drains into whoever is there
            at = self._mover_at
            m["seeded"] = at[1] if at and at[0] != p[2][:2] else ""
        elif t == "-start" and what in ("taunt", "yawn"):
            m["taunt" if what == "taunt" else "drowsy"] = 1
        elif t == "-start" and what == "disable" and len(p) > 4:
            m["disabled"] = to_id(p[4].removeprefix("move: "))
        elif t == "-end" and what == "disable":
            m.pop("disabled", None)
        elif t == "-start" and what == "typechange":
            # Week 12: Protean, Libero, Soak, Burn Up and the like: the types it
            # has now, until it leaves the field; copied from another (Reflect
            # Type: no types in the line), not followed: []
            new = p[4] if len(p) > 4 and not p[4].startswith("[") else ""
            m["types"] = new.split("/") if new else []
            m.pop("typeadd", None)
            if any(
                x in ("[from] ability: Protean", "[from] ability: Libero")
                for x in p[4:]
            ):
                m["protean"] = 1  # once each time it comes in
        elif t == "-start" and what == "typeadd" and len(p) > 4:
            m["typeadd"] = p[4]  # Trick-or-Treat, Forest's Curse
        elif t == "-end" and what == "typechange":
            m.pop("types", None)
        elif t == "-activate" and what in BINDING:
            m["bound"] = 8  # an eighth each end of turn (Week 12)
            # Week 14: who bound it (`[of]`), and a sixth with its Binding Band
            of = next((x[5:] for x in p[4:] if x.startswith("[of] ")), None)
            k = self._index(of[:2], of) if of and of[:2] in self.mons else None
            if of and k is not None:
                m["bound_by"] = k
                if self.mons[of[:2]][k]["item"] == "bindingband":
                    m["bound"] = 6
        elif t == "-end" and "[partiallytrapped]" in p[4:]:
            m.pop("bound", None)
        elif t == "-activate" and what == "skillswap" and len(p) > 5:
            # Week 13: the user takes the target's ability, the target the user's
            of = next((x[5:] for x in p[6:] if x.startswith("[of] ")), None)
            other = self._mon(of) if of else None
            if p[4]:
                m["ability"] = to_id(p[4])
            if other is not None and p[5]:
                other["ability"] = to_id(p[5])
        elif t == "-ability" and any(
            x in ("[from] move: Entrainment", "[from] move: Simple Beam") for x in p[4:]
        ):
            m["ability"] = to_id(p[3])
        elif t == "-start" and what == "curse":
            m["cursed"] = 1
        elif t == "-start" and what.startswith("stockpile") and what[9:].isdigit():
            m["stockpile"] = int(what[9:])
        elif t == "-end" and what == "stockpile":
            m.pop("stockpile", None)
        elif t == "-start" and what in (
            "saltcure",
            "healblock",
            "focusenergy",
            "imprison",
        ):
            m[what] = 1
        elif t == "-end" and what == "healblock":
            m.pop("healblock", None)
        elif t == "-singlemove" and what == "destinybond":
            m["destinybond"] = 1
        elif t == "-singlemove" and what == "glaiverush":
            m["glaiverush"] = 1  # every move at it hits, twice as hard (Week 14)
        elif t == "-transform" and len(p) > 3 and p[3][:2] in ROLES:
            # Week 13 (Imposter): the foe it copied, and whether that one had
            # Mega Evolved; its moves, stat stages (the log does not print
            # them), a changed ability and types. The ally is not copied here
            r2 = p[3][:2]
            j = self._index(r2, p[3])
            if j is not None and r2 != p[2][:2]:
                o = self.mons[r2][j]
                m["transform"] = [j, int(bool(o["mega"]))]
                sets = self.movesets.get(r2, [])
                m["moves"] = list(sets[j]) if j < len(sets) else []
                m["boosts"] = dict(o["boosts"])
                for k in ("ability", "types", "typeadd"):
                    if k in o:
                        m[k] = list(o[k]) if isinstance(o[k], list) else o[k]
                    else:
                        m.pop(k, None)
        elif t == "-start" and what == "attract":
            # infatuated (Cute Charm): by whom, on the other side
            of = next((x[5:] for x in p[4:] if x.startswith("[of] ")), "")
            src = self._index(of[:2], of) if of[:2] in ROLES else None
            if src is not None and of[:2] != p[2][:2]:
                m["attract"] = src
        elif t == "-end" and what == "attract":
            m.pop("attract", None)
        elif t == "-end" and what in ("leechseed", "taunt", "yawn"):
            m.pop(
                {"leechseed": "seeded", "taunt": "taunt", "yawn": "drowsy"}[what], None
            )

    def _acted(self, p: list[str]) -> None:
        """A move line: the Pokemon has moved; Protect in a row is counted."""
        m = self._mon(p[2])
        if m is None or len(p) < 4:
            return
        move = to_id(p[3])
        self._mover = self._index(p[2][:2], p[2])
        self._mover_at = (p[2][:2], p[2][2:3])
        released = m.get("charging") == move and "[still]" not in p[4:]
        if released:
            m.pop("charging", None)  # the charged move goes off
        if move != "destinybond":
            m.pop("destinybond", None)  # it ends when the Pokemon moves again
        m.pop("glaiverush", None)  # so does Glaive Rush (its own line follows)
        called = any(x.startswith("[from]") and "lockedmove" not in x for x in p[4:])
        # the real-data check: Fake Out only before moving, and Choice locks
        self._fakeout = None
        if move == "fakeout" and not called:
            key = "fakeout_not_available" if m["moved"] else "fakeout_available"
            self.counts[key + "_used"] += 1
            self._fakeout = (m, key)
        if (
            m["item"] in CHOICE_ITEMS
            and m["last_move"]
            and move != m["last_move"]
            and not called
        ):
            self.counts["choice_locked_used_another_move"] += 1
        elif m["item"] in CHOICE_ITEMS and m["last_move"] and not called:
            self.counts["choice_locked_used_its_move"] += 1
        m["moved"] = True
        m["last_move"] = move
        if not called:
            m["rev_moves"].add(move)
        # its PP (Week 17): one for each use, a failed one too; none for a
        # charged move going off, a move another called, a locked repeat
        # (Outrage), or Struggle. Pressure's extra PP is not counted.
        locked = any("lockedmove" in x for x in p[4:])
        if not (called or released or locked or move == "struggle"):
            used = m.setdefault("pp_used", {})
            used[move] = used.get(move, 0) + 1
        if move in PROTECT_MOVES:
            m["protect_streak"] += 1
            self._protecting = m
        else:
            m["protect_streak"] = 0
            self._protecting = None

    def handle(self, p: list[str]) -> None:
        last, self._last = self._last, p
        if len(p) > 3 and p[1] in ("-sidestart", "-sideend") and p[2][:2] in ROLES:
            hz = to_id(p[3].removeprefix("move: "))
            if hz in HAZARD_LAYERS:
                side = self.hazards[p[2][:2]]
                if p[1] == "-sidestart":
                    side[hz] = min(HAZARD_LAYERS[hz], side.get(hz, 0) + 1)
                else:
                    side.pop(hz, None)
        if len(p) > 3 and p[1] in ("-start", "-end", "-activate"):
            # a substitute (Week 10): up, and whether it has been hit (the log
            # never shows how many hit points it has left)
            if to_id(p[3].removeprefix("move: ")) == "substitute":
                m = self._mon(p[2])
                if m is not None:
                    if p[1] == "-start":
                        m["sub_up"] = "full"
                    elif p[1] == "-end":
                        m.pop("sub_up", None)
                    elif "[damage]" in p[4:]:
                        m["sub_up"] = "hit"
        if len(p) > 3 and p[1] == "-start":
            n = re.fullmatch(r"perish(\d)", to_id(p[3]))
            m = self._mon(p[2]) if n else None
            if m is not None and n is not None:
                # the count the log shows; it faints when the count reaches 0
                if int(n.group(1)) > 0:
                    m["perish"] = int(n.group(1))
                else:
                    m.pop("perish", None)
        if len(p) > 2 and p[1] in _VOLATILE_LINES:
            self._volatiles(p)
        if len(p) > 2:
            self._reveal(p)
        if len(p) > 2 and p[1] == "move":
            self._acted(p)
        if len(p) > 2 and p[1] == "-fail" and self._fakeout is not None:
            m, key = self._fakeout
            if self._mon(p[2]) is m:
                self.counts[key + "_failed"] += 1
            self._fakeout = None
        if len(p) > 2 and p[1] == "-fail" and self._protecting is not None:
            if self._mon(p[2]) is self._protecting:
                self._protecting["protect_streak"] = 0  # a failed Protect resets
            self._protecting = None
        if len(p) > 1:
            self._check_intimidate(p)
        if len(p) > 1 and self._effects(p[1], p):
            return
        if len(p) < 3:
            return
        t = p[1]
        ident = p[2]
        role = ident[:2]
        if t == "poke" and len(p) > 3 and role in ROLES:
            # team preview: each one's gender (Cute Charm, Week 13), usually
            # before the sheets; none shown is none to have (N)
            sex = [d for d in p[3].split(", ")[1:] if d in ("M", "F")]
            self.preview[(role, to_id(p[3].split(",")[0]))] = sex[0] if sex else "N"
            idx = self._index(role, "", p[3]) if self.mons.get(role) else None
            if idx is not None:
                self.mons[role][idx]["gender"] = sex[0] if sex else "N"
            return
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
            perish = None
            sub_up = None
            if old is not None and old != idx:
                if any(x == "[from] Baton Pass" for x in p[5:]):
                    passed = dict(self.mons[role][old]["boosts"])
                    perish = self.mons[role][old].get("perish")
                    sub_up = self.mons[role][old].get("sub_up")
                self.mons[role][old].pop("perish", None)
                self.mons[role][old].pop("sub_up", None)
                for k in LEAVING:
                    self.mons[role][old].pop(k, None)
                self.mons[role][old]["active"] = False
                self.mons[role][old]["boosts"] = {}
                self.mons[role][old].update(moved=False, last_move="", protect_streak=0)
                # Regenerator heals a third on switching out; the log does not
                # print it (the stored states apply it too)
                if self.abilities.get(role, [""] * 6)[old] == "regenerator":
                    o = self.mons[role][old]
                    if not o["fainted"]:
                        o["hp"] = min(1.0, round(o["hp"] + 1 / 3, 2))
            m = self.mons[role][idx]
            m.update(moved=False, last_move="", protect_streak=0)
            m["active"] = True
            m["seen"] = True
            # its gender, as its switch-in shows it (Cute Charm, Week 13): none
            # shown is none to have (N)
            sex = [d for d in p[3].split(", ")[1:] if d in ("M", "F")]
            m["gender"] = sex[0] if sex else "N"
            m["hp"], fainted = _hp(p[4])
            m["fainted"] = m["fainted"] or (fainted and m["hp"] == 0)
            m["status"] = _status(p[4])
            m["boosts"] = passed
            m.pop("perish", None)
            m.pop("sub_up", None)
            if perish:
                m["perish"] = perish
            if old is not None and old != idx and sub_up:
                m["sub_up"] = sub_up
            self.slots[role][slot] = idx
        elif t in ("-damage", "-heal", "-sethp") and len(p) > 3:
            idx = self._index(role, ident)
            if idx is not None:
                m = self.mons[role][idx]
                m["hp"], fainted = _hp(p[3])
                m["status"] = "" if fainted else _status(p[3])
                paid = (
                    last is not None
                    and len(last) > 3
                    and last[1] == "-start"
                    and last[2] == ident
                    and to_id(last[3].removeprefix("move: ")) == "substitute"
                )
                if (
                    t == "-damage"
                    and not paid
                    and not any(x.startswith("[from]") for x in p[4:])
                ):
                    # hit by a move (Rage Fist counts these; in Champions they
                    # reset when it leaves the field); not the hit points paid
                    # for a substitute
                    m["hits"] = m.get("hits", 0) + 1
        elif t == "faint":
            idx = self._index(role, ident)
            if idx is not None:
                m = self.mons[role][idx]
                m.update(hp=0.0, fainted=True, active=False, boosts={}, status="")
                m.update(moved=False, last_move="", protect_streak=0)
                m.pop("perish", None)
                m.pop("sub_up", None)
                for k in (*LEAVING, *TRACKED):
                    m.pop(k, None)
                for s, v in self.slots[role].items():
                    if v == idx:
                        self.slots[role][s] = None
        elif t == "-mega":
            idx = self._index(role, ident)
            if idx is not None:
                self.mons[role][idx]["mega"] = True
                # its new form's types replace any change, and its ability is
                # given afresh, so Protean can act again (Showdown's forme change)
                for k in ("types", "typeadd", "protean"):
                    self.mons[role][idx].pop(k, None)
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

    def hazard_spans(self) -> tuple[tuple[str, str, int, int], ...]:
        """The hazards as timer spans (no length: 99 turns), with their layers
        as the longest: what `wpa.resolver.field_from_timers` reads."""
        return tuple(
            (hz, r, 99, n) for r in ROLES for hz, n in sorted(self.hazards[r].items())
        )

    def side(self, role: str) -> list[dict]:
        # which place each Pokemon on the field is in (Week 13: Imposter copies
        # the foe opposite)
        at = {v: k for k, v in self.slots.get(role, {}).items() if v is not None}
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
                "moved": m["moved"],
                "last_move": m["last_move"],
                "protect_streak": m["protect_streak"],
                "rev_moves": sorted(m["rev_moves"]),
                "rev_item": m["rev_item"],
                "rev_ability": m["rev_ability"],
                **({"perish": m["perish"]} if m.get("perish") else {}),
                **({"pp_used": dict(m["pp_used"])} if m.get("pp_used") else {}),
                **({"hits": m["hits"]} if m.get("hits") else {}),
                **({"sub_up": m["sub_up"]} if m.get("sub_up") else {}),
                **({"gender": m["gender"]} if m.get("gender") else {}),
                **({"slot": at[i]} if m["active"] and i in at else {}),
                **{k: m[k] for k in TRACKED if k in m and k != "seeded"},
                **({"seeded": self._seeded(role, m)} if "seeded" in m else {}),
            }
            for i, (sp, m) in enumerate(
                zip(self.species.get(role, []), self.mons.get(role, []))
            )
        ]

    def _seeded(self, role: str, m: dict) -> int:
        """Leech Seed: the sheet position of the Pokemon now in the seeder's
        place on the other side, or -1 while the place is empty (Showdown
        drains into whoever is there, `getAtSlot`; nothing when no one is)."""
        other = "p2" if role == "p1" else "p1"
        idx = self.slots.get(other, {}).get(m["seeded"]) if m["seeded"] else None
        if idx is None or self.mons[other][idx]["fainted"]:
            return -1
        return idx

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
        timers = tuple(timers) + board.hazard_spans()
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
