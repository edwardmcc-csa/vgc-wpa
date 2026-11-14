"""Your biggest swings in one game (M7 in the engineering plan).

    python -m wpa.replay <replay link> --player <your name>

Paste a Showdown replay link (or a saved replay page, or its `.json` or `.log`)
and get, for that player, a ranked list of the game's biggest win-probability
swings. Each is split four ways, as DEFINITIONS §3 says: your choice, the
position, their decision and the dice. Your choice is shown against both
baselines of §4: what players typically choose there, and the best of your
likely choices, named when it was not yours. With it: what happened, from the
log (the moves, what fainted, and the luck: critical hits, misses, full
paralysis and the like), the game's sum, and your costliest choices.

Several links in a set's order (games 1, 2, 3 of a best-of-three) are analysed
as a set: games 2 and 3 use what earlier games showed (§11.3).

The analysis is `wpa.attribution.analyse_game`, as in the weekly runs, so it
needs the same models and data. It takes about two minutes a game. It is saved
in `reports/replays/`, so the report can be shown again (another player,
more swings) at once; `--fresh` analyses again. Nothing here reads the splits.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from wpa.team_sheets import to_id

SITE = "replay.pokemonshowdown.com"
_ID = re.compile(r"^[a-z0-9]+-\d+(?:-[a-z0-9]+)?$")
_PAGE_LOG = re.compile(
    r'<script type="text/plain" class="battle-log-data">(.*?)</script>', re.S
)
_PAGE_ID = re.compile(re.escape(SITE) + r"/([a-z0-9]+-\d+(?:-[a-z0-9]+)?)")
FORMAT_NAMES = {"regma": "Reg M-A", "regmb": "Reg M-B"}


class ReplayError(ValueError):
    """Something about the replay asked for that the report cannot use, said in
    words for the person who asked."""


# --------------------------------------------------------------------------
# Finding the replay
# --------------------------------------------------------------------------


def replay_id(src: str) -> str:
    """The battle id in a replay link (or the id itself)."""
    s = src.strip()
    s = re.sub(r"^https?://", "", s).split("#")[0].split("?")[0]
    if s.startswith(SITE + "/"):
        s = s[len(SITE) + 1 :]
    s = s.strip("/")
    for ext in (".json", ".log"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    if not _ID.match(s):
        raise ReplayError(f"not a Showdown replay link: {src.strip()!r}")
    return s


def download_url(rid: str) -> str:
    return f"https://{SITE}/{rid}.json"


def fetch(rid: str) -> str:  # pragma: no cover - the network
    import urllib.request

    url = download_url(rid)
    req = urllib.request.Request(url, headers={"User-Agent": "vgc-wpa replay report"})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.read().decode("utf-8")
    except Exception as e:
        raise ReplayError(
            f"could not download {url} ({e}). If the replay is private, or this "
            "computer is offline, open the replay in a browser, save the page "
            "(Ctrl+S), and give the saved file instead of the link."
        ) from e


def tag_from_log(log: str) -> str:
    """A battle id for a log saved without one: its format from the `|tier|`
    line (the number is 0)."""
    for line in log.split("\n"):
        if line.startswith("|tier|"):
            return f"{to_id(line[len('|tier|') :])}-0"
    raise ReplayError("this is not a Showdown battle log (it has no |tier| line)")


def from_text(text: str, name: str) -> tuple[str, str]:
    """(battle id, log) from a replay's `.json`, a saved replay page, or a log.
    `name`: the file's name, used as the id when it is one."""
    stem = Path(name).name
    for ext in (".json", ".log", ".html", ".htm", ".txt"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
    if name.endswith(".json") or text.lstrip().startswith("{"):
        d = json.loads(text)
        log = d["log"].replace("\r\n", "\n")
        return d.get("id") or tag_from_log(log), log
    page = _PAGE_LOG.search(text)
    if page:
        log = page.group(1).replace("<\\/", "</").replace("\r\n", "\n")
        if _ID.match(stem):
            return stem, log
        found = _PAGE_ID.search(text)
        return (found.group(1) if found else tag_from_log(log)), log
    log = text.replace("\r\n", "\n")
    return (stem if _ID.match(stem) else tag_from_log(log)), log


def load(src: str) -> tuple[str, str]:
    """(battle id, log) from a link, a battle id, or a saved file."""
    p = Path(src.strip().strip('"'))
    if p.is_file():
        return from_text(p.read_text(encoding="utf-8"), p.name)
    rid = replay_id(src)
    return from_text(fetch(rid), rid + ".json")


def format_for(tag: str, log: str) -> str:
    """'regma' or 'regmb', or a ReplayError naming the formats the models know."""
    from wpa.formats import UnknownFormatError, format_of

    try:
        return format_of(tag)
    except UnknownFormatError:
        pass
    try:
        return format_of(tag_from_log(log))
    except (UnknownFormatError, ReplayError):
        pass
    tier = next(
        (x[len("|tier|") :] for x in log.split("\n") if x.startswith("|tier|")), "?"
    )
    raise ReplayError(
        f"this game is {tier}: the models know Champions VGC 2026 "
        f"{' and '.join(FORMAT_NAMES.values())} only"
    )


def players(log: str) -> dict[str, str]:
    from wpa.bring import players as _players

    return _players(log)


def side_of(log: str, player: str) -> str:
    """'p1' or 'p2': which side `player` played (names compared as Showdown
    compares them: case, spaces and symbols aside)."""
    names = players(log)
    for role, name in names.items():
        if to_id(name) == to_id(player):
            return role
    raise ReplayError(
        f"{player.strip()!r} did not play in this game: the players were "
        f"{names.get('p1', '?')} and {names.get('p2', '?')}"
    )


# --------------------------------------------------------------------------
# A game without team sheets (Week 12 Task 5)
# --------------------------------------------------------------------------

_STATS = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "spa": "spa",
    "spd": "spd",
    "spe": "spe",
}
_STAT_ORDER = ("hp", "atk", "def", "spa", "spd", "spe")


def parse_team(text: str) -> list[dict]:
    """A team as Showdown exports it (and PokePaste shows it): each Pokemon's
    name, species, gender, item, ability, level, nature, stat points (EVs) and
    moves, as written."""
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [x.strip() for x in block.split("\n") if x.strip()]
        if not lines:
            continue
        head, _, item = lines[0].partition(" @ ")
        head, gender = head.strip(), ""
        found = re.search(r" \(([MF])\)$", head)
        if found:
            gender, head = found.group(1), head[: found.start()]
        found = re.fullmatch(r"(.+?) \((.+)\)", head)
        name, species = (found.group(1), found.group(2)) if found else (head, head)
        mon = {
            "name": name,
            "species": species,
            "gender": gender,
            "item": item.strip(),
            "ability": "",
            "level": 50,
            "nature": "",
            "evs": {},
            "moves": [],
        }
        for x in lines[1:]:
            if x.startswith("Ability:"):
                mon["ability"] = x[len("Ability:") :].strip()
            elif x.startswith("Level:"):
                mon["level"] = int(x[len("Level:") :].strip() or 50)
            elif x.startswith("EVs:"):
                for part in x[len("EVs:") :].split("/"):
                    n, _, stat = part.strip().partition(" ")
                    key = _STATS.get(to_id(stat))
                    if key and n.isdigit():
                        mon["evs"][key] = int(n)
            elif x.endswith(" Nature"):
                mon["nature"] = x[: -len(" Nature")].strip()
            elif x.startswith("-"):
                mon["moves"].append(x.lstrip("-~ ").split(" [")[0].strip())
        out.append(mon)
    return out


def has_sheets(log: str) -> bool:
    """Whether the log shows both players' team sheets."""
    return {x.split("|")[2] for x in log.split("\n") if x.startswith("|showteam|")} >= {
        "p1",
        "p2",
    }


def _packed(mon: Mapping) -> str:
    evs = mon.get("evs") or {}
    ev = ",".join(str(evs.get(k, 0)) for k in _STAT_ORDER) if evs else ""
    species = mon["species"] if mon["name"] != mon["species"] else ""
    return "|".join(
        [
            mon["name"],
            species,
            mon.get("item", ""),
            mon.get("ability", ""),
            ",".join(mon.get("moves") or ()),
            mon.get("nature", ""),
            ev,
            mon.get("gender", ""),
            "",
            "",
            str(mon.get("level", 50)),
            "",
        ]
    )


def with_sheets(log: str, role: str, team: str) -> str:
    """A log that shows no team sheets, with `|showteam|` lines put in where
    Showdown puts them (after team preview starts): `role`'s from its team
    paste, in team preview's order; the other's with the species team preview
    shows and nothing else, as a closed-sheet game shows it. A log that shows
    the sheets comes back as it is."""
    if has_sheets(log):
        return log
    lines = log.split("\n")
    preview: dict[str, list[dict]] = {"p1": [], "p2": []}
    for x in lines:
        p = x.split("|")
        if x.startswith("|poke|") and len(p) > 3 and p[2] in preview:
            details = [d.strip() for d in p[3].split(",")]
            level = next((d[1:] for d in details if re.fullmatch(r"L\d+", d)), "50")
            gender = next((d for d in details if d in ("M", "F")), "")
            preview[p[2]].append(
                {
                    "name": details[0],
                    "species": details[0],
                    "gender": gender,
                    "level": int(level),
                }
            )
    if not preview["p1"] or not preview["p2"]:
        raise ReplayError("this game has no team preview to read the teams from")
    left = parse_team(team)
    mine = []
    for shown in preview[role]:
        sp = to_id(shown["species"].replace("-*", ""))
        hit = next((m for m in left if to_id(m["species"]) == sp), None) or next(
            (
                m
                for m in left
                if to_id(m["species"]).startswith(sp)
                or sp.startswith(to_id(m["species"]))
            ),
            None,
        )
        if hit is None:
            raise ReplayError(
                f"your team paste has no {shown['species']}: give the team you "
                "played in this game"
            )
        left.remove(hit)
        mine.append(hit)
    other = "p2" if role == "p1" else "p1"
    show = [
        f"|showteam|{role}|" + "]".join(_packed(m) for m in mine),
        f"|showteam|{other}|" + "]".join(_packed(m) for m in preview[other]),
    ]
    at = next(
        (i + 1 for i, x in enumerate(lines) if x.startswith("|teampreview")),
        max(i for i, x in enumerate(lines) if x.startswith("|poke|")) + 1,
    )
    return "\n".join(lines[:at] + show + lines[at:])


def prepare(
    games: Sequence[tuple[str, str, str]],
    player: str | None,
    team: str | None,
    hidden: bool = False,
) -> tuple[list[tuple[str, str, str]], bool]:
    """The games to analyse, and whether with the opponent's sheet hidden: so
    when asked (`hidden`), and always for a game that shows no team sheets,
    whose log then gets the player's sheet from their team paste."""
    out = []
    for tag, log, fmt in games:
        if not has_sheets(log):
            if not team or not player:
                raise ReplayError(
                    "this game shows no team sheets: give your team with --team "
                    "(a team paste, as Showdown exports it) and your name with "
                    "--player"
                )
            log, hidden = with_sheets(log, side_of(log, player), team), True
        out.append((tag, log, fmt))
    return out, hidden


HIDDEN_NOTE = (
    "Their team sheet was hidden: their moves, items and abilities are the "
    "likeliest from the usage statistics and what the game showed. Team preview "
    "and forced switches are not split."
)


# --------------------------------------------------------------------------
# What happened, from the log
# --------------------------------------------------------------------------


@dataclass
class Moment:
    """What the log shows at one decision point: each side's actions, what
    fainted, and the luck (role of the Pokemon it happened to or by, words)."""

    actions: dict[str, list[str]] = field(default_factory=lambda: {"p1": [], "p2": []})
    fainted: dict[str, list[str]] = field(default_factory=lambda: {"p1": [], "p2": []})
    luck: list[tuple[str, str]] = field(default_factory=list)


_STATUS = {
    "brn": "was burned",
    "par": "was paralysed",
    "psn": "was poisoned",
    "tox": "was badly poisoned",
    "frz": "was frozen",
    "slp": "fell asleep",
}
_BLOCKS = ("Protect", "Wide Guard", "Quick Guard", "Mat Block", "Crafty Shield")


class _Reader:
    """Walks a log once, filing what happens under each decision point:
    ("preview", 0), ("turn", n), and ("replacement", n) for the switch-ins
    after turn n."""

    def __init__(self) -> None:
        self.out: dict[tuple[str, int], Moment] = {}
        # each decision point's actions while reading: [text, marks]
        self.acts: dict[tuple[str, int], dict[str, list[tuple[str, list[str]]]]] = {}
        self.names: dict[tuple[str, str], str] = {}  # (role, nickname) -> species
        self.slots: dict[str, str | None] = {}  # "p1a" -> species in it
        self.at: tuple[str, int] | None = None
        self.turn = 0
        self.leads: dict[str, list[str]] = {"p1": [], "p2": []}
        # the move being resolved: its role and marks, its user and name, and
        # the slots it damaged
        self.role = ""
        self.marks: list[str] | None = None
        self.user = ""
        self.move = ""
        self.hit: set[str] = set()
        self.faked_out: set[str] = set()  # slots hit by Fake Out this turn
        self.sleep: dict[tuple[str, str], int] = {}  # tries asleep so far
        # a Mega Evolution not yet followed by its Pokemon's move: where its
        # own line is, to fold into the move's
        self.mega: dict[tuple[str, str], tuple[tuple[str, int], int]] = {}

    # -- helpers
    def moment(self) -> Moment:
        assert self.at is not None
        self.acts.setdefault(self.at, {"p1": [], "p2": []})
        return self.out.setdefault(self.at, Moment())

    def who(self, ref: str) -> tuple[str, str, str]:
        """(role, slot, species) of 'p1a: Nickname'."""
        slot, _, nick = ref.partition(": ")
        role = slot[:2]
        return role, slot[:3], self.names.get((role, nick.strip()), nick.strip())

    def add(self, role: str, text: str) -> list[str]:
        self.moment()
        assert self.at is not None
        marks: list[str] = []
        self.acts[self.at][role].append((text, marks))
        return marks

    def mark(self, what: str) -> None:
        if self.marks is not None and what not in self.marks:
            self.marks.append(what)

    def luck(self, role: str, text: str) -> None:
        if self.at is None:
            return
        m = self.moment()
        if (role, text) not in m.luck:
            m.luck.append((role, text))

    # -- lines
    def line(self, p: list[str]) -> None:
        kind = p[1] if len(p) > 1 else ""
        if kind == "start":
            self.at = ("preview", 0)
            self.moment()
        elif kind == "turn":
            if self.at == ("preview", 0):
                for role, mons in self.leads.items():
                    if mons:
                        self.add(role, "led " + " and ".join(mons))
            self.turn = int(p[2])
            self.at = ("turn", self.turn)
            self.moment()
            self.marks, self.faked_out = None, set()
        elif kind == "upkeep":
            self.at = ("replacement", self.turn)
            self.marks = None
        elif self.at is None:
            return
        elif kind in ("switch", "drag", "replace"):
            self.switch(kind, p)
        elif kind == "move":
            self.on_move(p)
        elif kind == "-crit":
            self.mark("critical hit")
            if self.marks is not None:
                self.luck(self.role, f"{self.user} landed a critical hit")
        elif kind == "-miss":
            self.mark("missed")
            if self.marks is not None:
                self.luck(self.role, f"{self.user}'s {self.move} missed")
        elif kind == "-activate" and len(p) > 3:
            if any(b in p[3] for b in _BLOCKS):
                self.mark("protected")
        elif kind == "-fail":
            self.mark("failed")
        elif kind == "-immune":
            self.mark("no effect")
        elif kind == "-damage" and len(p) > 3:
            role, slot, name = self.who(p[2])
            src = next((x for x in p[4:] if x.startswith("[from]")), None)
            if src is None:
                self.hit.add(slot)
            elif "confusion" in src:
                self.luck(role, f"{name} hit itself in confusion")
        elif kind == "-status" and len(p) > 3:
            role, slot, name = self.who(p[2])
            st = p[3].strip()
            if st == "slp":
                self.sleep[(role, name)] = 0
            # a status the move gave as well as damage: a chance (a secondary
            # effect), unless it came from somewhere else
            if not any(x.startswith("[from]") for x in p[4:]) and slot in self.hit:
                self.luck(role, f"{name} {_STATUS.get(st, st)} by {self.move}")
        elif kind == "-start" and len(p) > 3 and p[3].strip() == "confusion":
            role, slot, name = self.who(p[2])
            if not any(x.startswith("[from]") for x in p[4:]) and slot in self.hit:
                self.luck(role, f"{name} became confused by {self.move}")
        elif kind == "-curestatus" and len(p) > 3:
            role, _slot, name = self.who(p[2])
            st = p[3].strip()
            if st == "frz" and "[msg]" in p[4:]:
                self.luck(role, f"{name} thawed out")
            elif st == "slp" and "[msg]" in p[4:]:
                # Champions: never on the first try, 1 in 3 on the second,
                # always on the third (data/mods/champions)
                if self.sleep.get((role, name), 0) + 1 == 2:
                    self.luck(role, f"{name} woke up early")
                self.sleep.pop((role, name), None)
        elif kind == "cant" and len(p) > 3:
            self.cant(p)
        elif kind == "-mega":
            role, _slot, name = self.who(p[2])
            self.add(role, f"{name} Mega Evolved")
            assert self.at is not None
            self.mega[(role, name)] = (self.at, len(self.acts[self.at][role]) - 1)
        elif kind == "faint":
            role, slot, name = self.who(p[2])
            self.moment().fainted[role].append(name)
            self.slots[slot] = None

    def switch(self, kind: str, p: list[str]) -> None:
        role, slot, _ = self.who(p[2])
        nick = p[2].partition(": ")[2].strip()
        species = p[3].split(",")[0].strip() if len(p) > 3 else nick
        species = self.names.setdefault((role, nick), species)
        before = self.slots.get(slot)
        self.slots[slot] = species
        if self.at == ("preview", 0):
            self.leads[role].append(species)
        elif kind == "drag":
            self.add(role, f"{before} was forced out for {species}")
        elif before is None or (self.at is not None and self.at[0] == "replacement"):
            self.add(role, f"sent in {species}")
        else:
            self.add(role, f"{before} switched out for {species}")

    def on_move(self, p: list[str]) -> None:
        role, slot, user = self.who(p[2])
        move = p[3].strip() if len(p) > 3 else "?"
        extras = p[5:] if len(p) > 5 else []
        spread = next((x for x in extras if x.startswith("[spread]")), None)
        text = f"{user} {move}"
        if (role, user) in self.mega:
            at, i = self.mega.pop((role, user))
            if at == self.at:
                self.acts[at][role][i] = ("", [])  # folded into this line
                text = f"{user} Mega Evolved, {move}"
        if spread is not None:
            hit = [s.strip()[:3] for s in spread[len("[spread]") :].split(",")]
            hit = [s for s in hit if s]
            if len(hit) == 1:
                text += f" → {self.slots.get(hit[0]) or '?'}"
            elif len(hit) == 2 and all(s[:2] != role for s in hit):
                text += " (both foes)"
            else:
                text += " (spread)"
        elif len(p) > 4 and p[4].strip() and p[4].strip()[:3] != slot:
            t_role, t_slot, t_name = self.who(p[4])
            text += f" → {t_name}" + (" (ally)" if t_role == role else "")
            if to_id(move) == "fakeout":
                self.faked_out.add(t_slot)
        if "[notarget]" in extras:
            text += " (no target)"
        self.marks = self.add(role, text)
        self.role, self.user, self.move, self.hit = role, user, move, set()

    def cant(self, p: list[str]) -> None:
        role, slot, name = self.who(p[2])
        why = p[3].strip()
        if why == "par":
            self.luck(role, f"{name} was fully paralysed")
        elif why == "flinch" and slot not in self.faked_out:
            self.luck(role, f"{name} flinched")
        elif why == "frz":
            self.luck(role, f"{name} stayed frozen")
        elif why == "slp":
            n = self.sleep.get((role, name), 0) + 1
            self.sleep[(role, name)] = n
            if n == 2:  # the second try wakes 1 time in 3 (Champions)
                self.luck(role, f"{name} stayed asleep")

    def finish(self) -> dict[tuple[str, int], Moment]:
        for at, acts in self.acts.items():
            m = self.out.setdefault(at, Moment())
            for role in ("p1", "p2"):
                m.actions[role] = [
                    text + (f" ({', '.join(marks)})" if marks else "")
                    for text, marks in acts[role]
                    if text
                ]
        return self.out


def moments(log: str) -> dict[tuple[str, int], Moment]:
    """What the log shows at each decision point: ("preview", 0), ("turn", n)
    and ("replacement", n), the switch-ins after turn n."""
    r = _Reader()
    for line in log.split("\n"):
        if line.startswith("|"):
            r.line(line.split("|"))
    return r.finish()


def describe(m: Moment, role: str) -> list[str]:
    """What happened, told from `role`'s side."""
    other = "p2" if role == "p1" else "p1"

    def own(r: str) -> str:
        return "your" if r == role else "their"

    lines = [
        "You: " + ("; ".join(m.actions[role]) or "nothing shown in the log"),
        "They: " + ("; ".join(m.actions[other]) or "nothing shown in the log"),
    ]
    fallen = [f"{own(r)} {n}" for r in (role, other) for n in m.fainted[r]]
    if fallen:
        lines.append("Fainted: " + ", ".join(fallen))
    if m.luck:
        lines.append("Luck: " + "; ".join(f"{own(r)} {t}" for r, t in m.luck))
    return lines


# --------------------------------------------------------------------------
# Choices in words
# --------------------------------------------------------------------------


def sheet_names(log: str) -> dict[str, list[str]]:
    """Each side's six species, as written on the sheet, in sheet order."""
    from wpa.sheets import parse_showteam_message

    out: dict[str, list[str]] = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            role, mons = parse_showteam_message(line)
            out[role] = [m.species for m in mons]
    return out


def _words(packed: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", packed)


def move_names(log: str, dex_moves: Mapping | None = None) -> dict[str, str]:
    """Move id -> name: the format's move data when given, else the log's
    `|move|` lines, else the sheets (spaces put back between words)."""
    from wpa.sheets import parse_showteam_message

    out: dict[str, str] = {}
    for line in log.split("\n"):
        if line.startswith("|showteam|"):
            for m in parse_showteam_message(line)[1]:
                for mv in m.moves:
                    out.setdefault(to_id(mv), _words(mv))
    for line in log.split("\n"):
        if line.startswith("|move|"):
            p = line.split("|")
            if len(p) > 3:
                out[to_id(p[3])] = p[3].strip()
    for k, v in (dex_moves or {}).items():
        name = v.get("name") if isinstance(v, Mapping) else v
        if name:
            out[k] = name
    return out


def say_choice(
    data: Sequence[Mapping],
    kind: str,
    role: str,
    sheets: Mapping[str, Sequence[str]],
    names: Mapping[str, str],
) -> str:
    """A choice (as the records keep it) in words, for `role`."""
    other = "p2" if role == "p1" else "p1"
    ours, theirs = sheets[role], sheets[other]
    if kind == "preview":
        ins = sorted(int(d["switch_to"]) for d in data)
        return "lead " + " and ".join(ours[i] for i in ins)
    if kind == "replacement":
        return "send in " + " and ".join(ours[int(d["switch_to"])] for d in data)
    parts = []
    for d in data:
        user = ours[int(d["user"])]
        if d["kind"] == "switch":
            parts.append(f"{user} switch to {ours[int(d['switch_to'])]}")
            continue
        text = f"{user} " + ("Mega Evolves, " if d.get("mega") else "")
        text += names.get(d["move"], d["move"])
        t = d.get("target")
        if t:
            side, j = t[0], int(t[1])
            text += f" → {theirs[j]}" if side == "foe" else f" → {ours[j]} (ally)"
        if d.get("switch_to") is not None:
            text += f", bringing in {ours[int(d['switch_to'])]}"
        parts.append(text)
    return "; ".join(parts)


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

PARTS = (
    ("choice", "your choice"),
    ("position", "the position"),
    ("theirs", "their decision"),
    ("dice", "the dice"),
)


def pts(x: float) -> str:
    """Win probability points: +12, -3, 0."""
    v = int(round(100 * x))
    return "0" if v == 0 else f"{v:+d}"


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def shown(before: float, after: float) -> str:
    """A change as the difference of the percentages shown (so 57% to 70%
    reads +13, whatever the decimals were)."""
    v = round(100 * after) - round(100 * before)
    return "0" if v == 0 else f"{v:+d}"


def swing(r: Mapping) -> float:
    return r["after"] - r["before"]


def _mine(records: Sequence[Mapping], role: str) -> list[Mapping]:
    """`role`'s decision points with their WPs, in game order."""
    got = [
        r
        for r in records
        if r.get("role") == role and r.get("before") is not None and "after" in r
    ]
    return sorted(got, key=lambda r: r.get("point", 0))


def _split(r: Mapping) -> bool:
    return not r.get("skipped") and r.get("choice") is not None


def biggest(records: Sequence[Mapping], role: str, top: int = 5) -> list[Mapping]:
    """`role`'s biggest swings, biggest first."""
    return sorted(_mine(records, role), key=lambda r: -abs(swing(r)))[:top]


def mostly(r: Mapping) -> str:
    """Which part made most of a swing (by size)."""
    if r.get("skipped"):
        return f"not split ({r['skipped']})"
    if r.get("choice") is None:
        return "not split"
    return max(PARTS, key=lambda kv: abs(r.get(kv[0]) or 0.0))[1]


def label(r: Mapping) -> str:
    if r["kind"] == "preview":
        return "Team preview"
    if r["kind"] == "replacement":
        return f"After turn {r['turn']} (switch-ins)"
    return f"Turn {r['turn']}"


def totals(records: Sequence[Mapping], role: str) -> dict[str, float]:
    """The game's sum for `role`: from the first decision point's WP to the
    result, each part over the decision points split, the swings of those not
    split, and any WP the records do not cover (`gap`; 0 when they chain)."""
    mine = _mine(records, role)
    out = {k: 0.0 for k, _ in PARTS}
    out["unsplit"] = 0.0
    out["unsplit_points"] = 0
    for r in mine:
        if _split(r):
            for k, _ in PARTS:
                out[k] += r[k]
        else:
            out["unsplit"] += swing(r)
            out["unsplit_points"] += 1
    out["start"] = mine[0]["before"] if mine else float("nan")
    out["end"] = mine[-1]["after"] if mine else float("nan")
    out["gap"] = (out["end"] - out["start"]) - sum(swing(r) for r in mine)
    return out


def costliest(records: Sequence[Mapping], role: str, top: int = 3) -> list[Mapping]:
    """`role`'s choices furthest below the best of their likely choices."""
    got = [r for r in _mine(records, role) if (r.get("vs_best") or 0.0) < -0.005]
    return sorted(got, key=lambda r: r["vs_best"])[:top]


def _choice_lines(r: Mapping, role: str, sheets, names) -> list[str]:
    out = []
    if r.get("choice") is None:
        return out
    text = f"Your choice: {pts(r['choice'])} against the typical choice"
    if r.get("vs_best") is not None:
        text += f", {pts(r['vs_best'])} against the best"
    out.append(text + ".")
    if r.get("best") and (r.get("vs_best") or 0.0) < -0.005:
        try:
            out.append("Best: " + say_choice(r["best"], r["kind"], role, sheets, names))
        except (IndexError, KeyError, ValueError):  # pragma: no cover - a sheet gap
            pass
    out.append(
        f"The position {pts(r['position'])}, their decision {pts(r['theirs'])}, "
        f"the dice {pts(r['dice'])}."
    )
    return out


LEGEND = [
    "How to read this (DEFINITIONS §3 and §4). Points are win probability:",
    "+10 is ten percentage points. Each swing splits four ways that add up to it:",
    "  your choice     your choice against what players typically choose there;",
    "                  'against the best' is against the best of your likely",
    "                  choices, the coaching number",
    "  the position    what the decision point held whatever you chose; credited",
    "                  to no one",
    "  their decision  their choice against their likely choices; negative when",
    "                  they read you well",
    "  the dice        damage rolls, critical hits, misses and other chance",
]


def game_report(
    tag: str,
    log: str,
    records: Sequence[Mapping],
    role: str,
    top: int = 5,
    dex_moves: Mapping | None = None,
    legend: bool = True,
) -> str:
    """The report for `role` in one game."""
    names_ = players(log)
    other = "p2" if role == "p1" else "p1"
    sheets = sheet_names(log)
    names = move_names(log, dex_moves)
    ms = moments(log)
    fmt = FORMAT_NAMES.get(str(next((r.get("format") for r in records), "")), "")
    turns = max((r.get("turn", 0) for r in records), default=0)
    winner = next(
        (x.split("|")[2] for x in log.split("\n") if x.startswith("|win|")), None
    )
    if winner is None:
        result = "No winner in the log."
    elif to_id(winner) == to_id(names_.get(role, "")):
        result = "You won."
    else:
        result = "You lost."
    lines = [
        f"{names_.get(role, role)} (you) vs {names_.get(other, other)}, {fmt}, "
        f"{turns} turns. {result}",
        f"https://{SITE}/{tag}",
        "",
    ]
    if any(r.get("sheets") == "hidden" for r in records):
        lines[-1:] = [HIDDEN_NOTE, ""]
    mine = _mine(records, role)
    if not mine:
        return "\n".join(lines + ["Nothing in this game could be analysed."])
    path = [f"team preview {pct(r['before'])}" for r in mine if r["kind"] == "preview"]
    path += [
        f"turn {r['turn']} {pct(r['before'])}" for r in mine if r["kind"] == "turn"
    ]
    path.append(f"end {pct(mine[-1]['after'])}")
    lines += ["Your win probability: " + ", ".join(path) + ".", ""]

    t = totals(records, role)
    lines.append(
        f"Over the game, from {pct(t['start'])} to the result ({pct(t['end'])}): "
        f"{shown(t['start'], t['end'])} points"
    )
    rows = [
        ("your choices", t["choice"], "against what players typically choose"),
        ("their decisions", t["theirs"], ""),
        ("the dice", t["dice"], ""),
        ("the positions", t["position"], "credited to no one"),
    ]
    if t["unsplit_points"]:
        why = sorted({r["skipped"] for r in mine if r.get("skipped")})
        rows.append(
            (
                "not split",
                t["unsplit"],
                f"{t['unsplit_points']} decision point"
                + ("s" if t["unsplit_points"] > 1 else "")
                + ": "
                + "; ".join(why),
            )
        )
    if abs(t["gap"]) >= 0.005:
        rows.append(("not analysed", t["gap"], "decision points with an error"))
    for name, v, note in rows:
        lines.append(f"  {name:<16}{pts(v):>5}" + (f"   {note}" if note else ""))
    lines.append("")

    # team preview, always: the leads are a choice made before anything else,
    # and the one most about the team
    pre = next((r for r in mine if r["kind"] == "preview" and _split(r)), None)
    m = ms.get(("preview", 0))
    if pre is not None and m is not None and m.actions[role]:
        led = m.actions[role][0].removeprefix("led ")
        lines.append(f"Team preview: you led {led}.")
        lines += [
            "  " + x
            for x in _choice_lines(pre, role, sheets, names)
            if not x.startswith("The position")
        ]
        lines.append("")

    big = biggest(records, role, top)
    lines.append(f"Your {len(big)} biggest swings")
    for n, r in enumerate(big, 1):
        head = (
            f"{n:>2}. {label(r)}: {pct(r['before'])} → {pct(r['after'])} "
            f"({shown(r['before'], r['after'])}), "
        )
        how = mostly(r)
        head += (
            how.replace(" (", ": ", 1).rstrip(")")
            if how.startswith("not")
            else (f"mostly {how}")
        )
        head += "."
        lines.append(head)
        m = ms.get((r["kind"], r["turn"]))
        for x in describe(m, role) if m else []:
            lines.append("      " + x)
        for x in _choice_lines(r, role, sheets, names):
            lines.append("      " + x)
    lines.append("")

    cost = costliest(records, role, 3)
    if cost:
        lines.append("Your costliest choices, against the best of your likely choices")
        for n, r in enumerate(cost, 1):
            lines.append(f"{n:>2}. {label(r)}: {pts(r['vs_best'])}")
            m = ms.get((r["kind"], r["turn"]))
            if m:
                lines.append("      " + describe(m, role)[0])
            if r.get("best"):
                try:
                    lines.append(
                        "      Best: "
                        + say_choice(r["best"], r["kind"], role, sheets, names)
                    )
                except (IndexError, KeyError, ValueError):  # pragma: no cover
                    pass
        lines.append("")
    if legend:
        lines += LEGEND
    return "\n".join(lines)


def set_summary(games: Sequence[tuple[str, str, list[dict]]], player: str) -> str:
    """One line per game of a set, for `player`."""
    lines = []
    for n, (tag, log, recs) in enumerate(games, 1):
        role = side_of(log, player)
        t = totals(recs, role)
        won = any(
            x.startswith("|win|") and to_id(x.split("|")[2]) == to_id(player)
            for x in log.split("\n")
        )
        lines.append(
            f"Game {n}: {'won' if won else 'lost'}; your choices {pts(t['choice'])}, "
            f"their decisions {pts(t['theirs'])}, the dice {pts(t['dice'])}, "
            f"the positions {pts(t['position'])}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------


def _options(a: argparse.Namespace) -> argparse.Namespace:  # pragma: no cover
    """The weekly run's settings (Runbook Section 20), for `attribution._tools`."""
    models = a.models or (
        Path("models_v4_avg") if Path("models_v4_avg").exists() else Path("models_v4")
    )
    return argparse.Namespace(
        dex_tables=a.dex_tables,
        showdown=Path("pokemon-showdown"),
        moves_dir=a.moves_dir or (Path("build") if Path("build").exists() else None),
        usage=Path("usage_stats"),
        bring=Path("models_v4/bring.json"),
        policy=Path("models_v4/policy.json"),
        models=models,
        groups="ABCDEFGHIJ",
        resolution=0.05,
        cap=300,
        top=6,
        draws=6,
        alternatives=10,
        budget=4000,
        no_typical=False,
        speed_beliefs=False,
        leads=Path("models_v4/leads.json"),
        replace=Path("models_v4/replace.json"),
        hidden_sets=bool(getattr(a, "hidden", False)),
        public_models=getattr(a, "public_models", None) or Path("models_v4_preview"),
        strength="fitted",  # DEFINITIONS revision 11
    )


def stale(path: Path, strength: float) -> bool:
    """Whether a game's saved records must be made again: none saved, or made
    at another opponent model strength (records before revision 11: 0)."""
    path = Path(path)
    if not path.exists():
        return True
    recs = [
        json.loads(x)
        for x in path.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    used = {
        float(r.get("strength", 0.0)) for r in recs if r.get("kind", "turn") == "turn"
    }
    return any(abs(u - strength) > 1e-9 for u in used)


def analyse(
    games: Sequence[tuple[str, str, str]], a: argparse.Namespace
) -> list[list[dict]]:  # pragma: no cover - runs the models
    """Each game's records, from `reports/replays/` when analysed before."""
    from wpa import attribution as A

    a.out.mkdir(parents=True, exist_ok=True)
    prev = A.previous_leads([(tag, log) for tag, log, _f in games])
    end = "-hidden" if getattr(a, "hidden", False) else ""
    saved = {tag: a.out / f"{tag}{end}.jsonl" for tag, _l, _f in games}
    want = A.strength_value(_options(a))  # analysed again at another strength
    jobs = [
        (tag, log, fmt, True, prev.get(tag, {}))
        for tag, log, fmt in games
        if a.fresh or stale(saved[tag], want)
    ]
    if jobs:
        n = len(jobs)
        print(
            f"Analysing {n} game{'s' if n > 1 else ''} (about two minutes a game"
            + (", side by side" if a.workers > 1 and n > 1 else "")
            + ")...",
            flush=True,
        )
        t0 = time.time()
        opts = _options(a)
        if a.workers > 1 and n > 1:
            from multiprocessing import Pool

            with Pool(min(a.workers, n), A._init, (opts,)) as pool:
                got = pool.map(A._one, jobs)
        else:
            A._init(opts)
            got = [A._one(j) for j in jobs]
        for job, recs in zip(jobs, got):
            with open(saved[job[0]], "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")
        print(f"Done in {(time.time() - t0) / 60:.1f} minutes.\n", flush=True)
    out = []
    for tag, _l, _f in games:
        text = saved[tag].read_text(encoding="utf-8")
        out.append([json.loads(x) for x in text.splitlines() if x.strip()])
    return out


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    p = argparse.ArgumentParser(
        description="Your biggest win-probability swings in a game: paste a "
        "Showdown replay link (or several, in a set's order)."
    )
    p.add_argument("replays", nargs="+", help="replay links, or saved replay files")
    p.add_argument("--player", help="your Showdown name (without it: both players)")
    p.add_argument("--top", type=int, default=5, help="how many swings to show")
    p.add_argument("--fresh", action="store_true", help="analyse again")
    p.add_argument("--workers", type=int, default=3, help="games at once, for sets")
    p.add_argument("--out", type=Path, default=Path("reports/replays"))
    p.add_argument("--models", type=Path, default=None)
    p.add_argument("--moves-dir", type=Path, default=None)
    p.add_argument("--dex-tables", type=Path, default=None)
    p.add_argument(
        "--team",
        type=Path,
        default=None,
        help="your team paste (as Showdown exports it), for a game that shows "
        "no team sheets",
    )
    p.add_argument(
        "--hidden",
        action="store_true",
        help="read the game with the opponent's sheet hidden, as if it had not "
        "been shown",
    )
    p.add_argument("--public-models", type=Path, default=Path("models_v4_preview"))
    a = p.parse_args(argv)
    # a console or file that cannot show a character shows "?" instead of failing
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    try:
        games = []
        for src in a.replays:
            tag, log = load(src)
            games.append((tag, log, format_for(tag, log)))
        if a.player:
            for tag, log, _f in games:
                side_of(log, a.player)  # before the long part, not after
        team = a.team.read_text(encoding="utf-8") if a.team else None
        games, a.hidden = prepare(games, a.player, team, a.hidden)
        if a.hidden and not (a.public_models / "regma").exists():
            raise ReplayError(
                "reading a game with the opponent's sheet hidden needs the model "
                f"trained that way, in {a.public_models} (Runbook Section 23, step 3)"
            )
    except (ReplayError, OSError) as e:
        sys.exit(f"Sorry: {e}.")
    recs = analyse(games, a)
    dex_moves = None
    try:
        import pickle

        if a.dex_tables:
            dexes, _t = pickle.load(open(a.dex_tables, "rb"))
            dex_moves = dexes[games[0][2]].moves
        else:
            from wpa.team_sheets import load_dexes

            dex_moves = load_dexes(Path("pokemon-showdown"))[games[0][2]].moves
    except Exception:  # the names then come from the log and the sheets
        pass
    texts = []
    if a.player and len(games) > 1:
        texts.append(
            set_summary([(t, lg, r) for (t, lg, _f), r in zip(games, recs)], a.player)
        )
    for n, ((tag, log, _f), r) in enumerate(zip(games, recs)):
        roles = [side_of(log, a.player)] if a.player else ["p1", "p2"]
        for role in roles:
            if len(games) > 1:
                texts.append(f"=== Game {n + 1} ===")
            texts.append(
                game_report(tag, log, r, role, a.top, dex_moves, legend=False).rstrip()
            )
    texts.append("\n".join(LEGEND))
    text = "\n\n".join(texts)
    print(text)
    who = to_id(a.player) if a.player else "both"
    path = a.out / f"{games[0][0]}-{who}.txt"
    path.write_text(text + "\n", encoding="utf-8")
    print(f"\n(Saved as {path})")


if __name__ == "__main__":
    main()


__all__ = [
    "Moment",
    "ReplayError",
    "biggest",
    "costliest",
    "describe",
    "download_url",
    "format_for",
    "from_text",
    "game_report",
    "has_sheets",
    "label",
    "load",
    "moments",
    "mostly",
    "move_names",
    "parse_team",
    "prepare",
    "pts",
    "replay_id",
    "say_choice",
    "set_summary",
    "sheet_names",
    "side_of",
    "tag_from_log",
    "totals",
    "with_sheets",
]
