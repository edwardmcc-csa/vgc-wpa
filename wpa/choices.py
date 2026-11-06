"""The choices on offer at a move-selection decision point (Week 9 Task 1).

At the start of every turn each player picks one action for each of their active
Pokemon: a move and its target, or a switch to a Pokemon on their bench, with Mega
Evolution as an extra on a move. `options` lists every action the rules allow
there, as far as the board knows them:

* each move on the Pokemon's sheet, except that a Choice item locks it to its last
  move, Fake Out and First Impression work only before it has moved, and an
  Assault Vest rules out status moves;
* a target for each move that takes one: either opposing Pokemon, or the ally for
  moves that can hit it (in doubles every Pokemon is adjacent to every other);
* a switch to each brought Pokemon on the bench;
* each move again with Mega Evolution, while the side has not Mega Evolved and the
  Pokemon holds its own Mega Stone.

`joint` pairs the two actives' actions, dropping pairs the game forbids (both
switching to the same Pokemon, or both Mega Evolving).

`turns` reads the choices the log shows. A switch before any move this turn is
the choice of the Pokemon it replaces; the first move of each Pokemon that was
active at the start of the turn is its choice, unless another effect called it
(`[from]`). Some choices cannot be seen: a Pokemon that could not move (`|cant|`,
flinch, sleep ...), one knocked out before its turn, one forced to repeat a move
(Outrage's lock), or a move with no target left. `check` counts how many of the
choices the log does show are in the list.

Not yet tracked, so offered even when the game would refuse: Taunt, Encore,
Disable, Torment, Imprison, and trapping (Shadow Tag, Arena Trap, bound moves).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product

from wpa.decisions import ROLES, _Board, to_id
from wpa.team_sheets import Dex, SheetMon

# move targets that the player chooses (the rest have none to choose)
FOE_TARGETS = {"normal", "any", "adjacentFoe"}
ALLY_TARGETS = {"normal", "any", "adjacentAlly", "adjacentAllyOrSelf"}
FIRST_TURN_ONLY = {"fakeout", "firstimpression"}


@dataclass(frozen=True)
class Action:
    """One Pokemon's action: `user` and `switch_to` are sheet positions from 0;
    `target` is ("foe", their sheet position) or ("ally", ours), or None."""

    user: int
    kind: str  # "move" or "switch"
    move: str = ""
    target: tuple[str, int] | None = None
    switch_to: int | None = None
    mega: bool = False


def _targets(
    move: str, dex: Dex, foes: Sequence[int], ally: int | None
) -> list[tuple[str, int] | None]:
    kind = (dex.moves.get(move) or {}).get("target", "normal")
    out: list[tuple[str, int] | None] = []
    if kind in FOE_TARGETS:
        out += [("foe", j) for j in foes]
    if kind in ALLY_TARGETS and ally is not None:
        out.append(("ally", ally))
    if kind == "adjacentAllyOrSelf" or not out:
        out.append(None)  # itself, or no target to choose
    return out


def options(
    ours: Sequence[Mapping],
    theirs: Sequence[Mapping],
    sheet: Sequence[SheetMon],
    dex: Dex,
    brought: set[int] | None = None,
) -> dict[int, list[Action]]:
    """The actions each of our active Pokemon may take, by sheet position.
    `brought`: our four (we know them); None means any Pokemon not yet fainted."""
    from wpa.features import _has_own_stone, _usable_moves

    actives = [i for i, p in enumerate(ours) if p["active"] and not p["fainted"]]
    foes = [j for j, p in enumerate(theirs) if p["active"] and not p["fainted"]]
    side_megaed = any(p.get("mega") for p in ours)
    pool = set(range(len(ours))) if brought is None else set(brought)
    bench = sorted(
        j
        for j in pool
        if j < len(ours) and not ours[j]["active"] and not ours[j]["fainted"]
    )
    out: dict[int, list[Action]] = {}
    for i in actives:
        st, mon = ours[i], sheet[i]
        ally = next((k for k in actives if k != i), None)
        mega_ok = not side_megaed and not st.get("mega") and _has_own_stone(mon, dex)
        acts: list[Action] = []
        for move in _usable_moves(mon, st):
            m = dex.moves.get(move) or {}
            if move in FIRST_TURN_ONLY and st.get("moved"):
                continue
            if st.get("item") == "assaultvest" and m.get("category") == "Status":
                continue
            for target in _targets(move, dex, foes, ally):
                acts.append(Action(i, "move", move=move, target=target))
                if mega_ok:
                    acts.append(Action(i, "move", move=move, target=target, mega=True))
        acts += [Action(i, "switch", switch_to=j) for j in bench]
        out[i] = acts
    return out


def joint(opts: Mapping[int, Sequence[Action]]) -> list[tuple[Action, ...]]:
    """Every allowed pair (or single, with one Pokemon active) of actions."""
    keys = sorted(opts)
    out = []
    for combo in product(*(opts[k] for k in keys)):
        to = [a.switch_to for a in combo if a.kind == "switch"]
        if len(to) != len(set(to)) or sum(a.mega for a in combo) > 1:
            continue
        out.append(tuple(combo))
    return out


@dataclass
class Turn:
    """One player's move-selection decision at the start of a turn: the board,
    and for each Pokemon active then, the action the log shows it taking, or why
    none can be seen ("cant", "fainted", "forced", "notarget", "none")."""

    turn: int
    role: str
    ours: list[dict]
    theirs: list[dict]
    taken: dict[int, Action | str] = field(default_factory=dict)


def _target(
    move: str, dex: Dex | None, user_role: str, user: int, role: str, idx: int | None
) -> tuple[str, int] | None:
    kind = ((dex.moves.get(move) or {}) if dex else {}).get("target", "normal")
    if idx is None or (kind not in FOE_TARGETS and kind not in ALLY_TARGETS):
        return None
    if role != user_role:
        return ("foe", idx)
    return None if idx == user else ("ally", idx)


def turns(log: str, dex: Dex | None = None) -> list[Turn]:
    """Every start-of-turn decision of both players, with the actions taken."""
    board = _Board()
    out: list[Turn] = []
    now: dict[str, Turn] | None = None
    moved = False
    megas: set[tuple[str, int]] = set()

    def other(r: str) -> str:
        return "p2" if r == "p1" else "p1"

    for raw in log.split("\n"):
        p = raw.split("|")
        if len(p) < 2:
            continue
        t = p[1]
        if t == "showteam":
            board.sheet(raw)
            continue
        if t in ("turn", "upkeep", "win", "tie") and now is not None:
            out += [now[r] for r in ROLES if r in now]
            now = None
        if t == "turn":
            now = {
                r: Turn(
                    int(p[2]),
                    r,
                    board.side(r),
                    board.side(other(r)),
                    {
                        i: "none"
                        for i, m in enumerate(board.mons[r])
                        if m["active"] and not m["fainted"]
                    },
                )
                for r in ROLES
                if board.mons.get(r)
            }
            moved, megas = False, set()
        elif now is not None and len(p) > 2 and p[2][:2] in now:
            role = p[2][:2]
            taken = now[role].taken
            if t == "switch" and not moved and len(p) > 3:
                old = board.slots[role].get(p[2][2:3]) if len(p[2]) > 2 else None
                new = board._index(role, p[2], p[3])
                if old is not None and taken.get(old) == "none" and new is not None:
                    taken[old] = Action(old, "switch", switch_to=new)
            elif t == "-mega":
                idx = board._index(role, p[2])
                if idx is not None:
                    megas.add((role, idx))
            elif t == "move" and len(p) > 3:
                moved = True
                idx = board._index(role, p[2])
                tags = " ".join(p[5:])
                if idx is not None and taken.get(idx) == "none":
                    if "[from]lockedmove" in tags.replace(" ", ""):
                        taken[idx] = "forced"
                    elif "[from]" in tags:
                        pass  # called by another effect: not this Pokemon's choice
                    elif "[notarget]" in tags:
                        taken[idx] = "notarget"
                    else:
                        move = to_id(p[3])
                        tr = p[4][:2] if len(p) > 4 and p[4][:2] in ROLES else ""
                        tidx = board._index(tr, p[4]) if tr else None
                        taken[idx] = Action(
                            idx,
                            "move",
                            move=move,
                            target=_target(move, dex, role, idx, tr, tidx),
                            mega=(role, idx) in megas,
                        )
            elif t in ("cant", "faint"):
                idx = board._index(role, p[2])
                if idx is not None and taken.get(idx) == "none":
                    taken[idx] = "cant" if t == "cant" else "fainted"
        board.handle(p)
    if now is not None:
        out += [now[r] for r in ROLES if r in now]
    return out


def check(log: str, dex: Dex, sheets: Mapping | None = None) -> Counter:
    """How many of the choices the log shows are in `options` ("in", "out"), and
    how many cannot be seen, by reason. Misses are also counted by kind and move
    ("out:move:<id>", "out:switch")."""
    from wpa.bring import brought_from_log
    from wpa.team_sheets import sheets_from_log

    sheets = sheets or sheets_from_log(log)
    brought = brought_from_log(log)
    counts: Counter = Counter()
    for t in turns(log, dex):
        if t.role not in sheets:
            continue
        opts = options(t.ours, t.theirs, sheets[t.role], dex, brought.get(t.role))
        for idx, act in t.taken.items():
            if isinstance(act, str):
                counts[act] += 1
            elif act in opts.get(idx, []):
                counts["in"] += 1
            else:
                counts["out"] += 1
                counts[f"out:{act.kind}" + (f":{act.move}" if act.move else "")] += 1
        counts["choices_offered"] += len(joint(opts)) if opts else 0
        counts["decisions"] += 1
    return counts
