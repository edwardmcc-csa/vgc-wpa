"""The choices on offer at a move-selection decision point (Week 9 Task 1).

At the start of every turn each player picks one action for each of their active
Pokemon: a move and its target, or a switch to a Pokemon on their bench, with Mega
Evolution as an extra on a move. `options` lists every action the rules allow
there, as far as the board knows them:

* each move on the Pokemon's sheet, except that a Choice item locks it to its last
  move and an Assault Vest rules out status moves (Fake Out after the first turn
  can still be picked; it fails);
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
(`[from]`). A target is a slot: if its Pokemon switched out first, the log names
the newcomer, but the choice was the Pokemon there when the turn began.

Some choices cannot be seen: a Pokemon that could not move (`|cant|`, flinch,
sleep ...), one knocked out before its turn, one forced to repeat a move
(Outrage's lock) or to Struggle, one that hit itself in confusion, one using a
move borrowed by Transform (Imposter included), or a move with no target left.
A move that charges, fails or is blocked (Armor Tail, Queenly Majesty) is
logged without its target; an animation line may show it, and otherwise the
target stays hidden. `check` counts how many of the choices the log does show
are in the list.

Not yet tracked, so offered even when the game would refuse: Taunt, Encore,
Disable, Torment, Imprison, and trapping (Shadow Tag, Arena Trap, bound moves).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import product

from wpa.decisions import ROLES, _Board, to_id
from wpa.team_sheets import Dex, SheetMon

# move targets that the player chooses (the rest have none to choose)
FOE_TARGETS = {"normal", "any", "adjacentFoe"}
ALLY_TARGETS = {"normal", "any", "adjacentAlly", "adjacentAllyOrSelf"}


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
    # itself (Acupressure; Curse used by a non-Ghost), or no target to choose
    if kind == "adjacentAllyOrSelf" or move == "curse" or not out:
        out.append(None)
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
        if st.get("moves"):  # transformed (Week 13): the moves it copied
            mon = replace(mon, moves=tuple(st["moves"]))
        ally = next((k for k in actives if k != i), None)
        mega_ok = not side_megaed and not st.get("mega") and _has_own_stone(mon, dex)
        acts: list[Action] = []
        moves, can_switch = _locked(mon, st, _usable_moves(mon, st))
        # no status moves with an Assault Vest, or while taunted (unless that
        # is all it has: Struggle is not modelled)
        no_status = st.get("item") == "assaultvest" or bool(
            st.get("taunt")
            and any((dex.moves.get(x) or {}).get("category") != "Status" for x in moves)
        )
        for move in moves:
            m = dex.moves.get(move) or {}
            if no_status and m.get("category") == "Status":
                continue
            if move == st.get("disabled") and len(moves) > 1:
                continue  # disabled (Disable, Cursed Body)
            for target in _targets(move, dex, foes, ally):
                acts.append(Action(i, "move", move=move, target=target))
                if mega_ok:
                    acts.append(Action(i, "move", move=move, target=target, mega=True))
        if can_switch:
            acts += [Action(i, "switch", switch_to=j) for j in bench]
        out[i] = acts
    return out


def _locked(
    mon: SheetMon, st: Mapping, usable: Sequence[str]
) -> tuple[Sequence[str], bool]:
    """Week 11 Task 3: a charging move's second turn allows only that move and
    no switch; Encore allows only the encored move (switching is still
    allowed). Otherwise every usable move, and switching."""
    charging = st.get("charging")
    if charging:
        return (charging,), False
    encore = st.get("encore")
    if encore and encore in mon.moves:
        return (encore,), True
    return usable, True


# moves that switch the user out; which Pokemon comes in is part of the choice
# (Week 10): an Action's `switch_to` on one of these is the Pokemon it brought in
PIVOT_MOVES = {
    "uturn",
    "voltswitch",
    "flipturn",
    "partingshot",
    "batonpass",
    "chillyreception",
    "shedtail",
    "teleport",
}


def base(a: Action) -> Action:
    """The option as `options` lists it: a switching move without the Pokemon it
    brought in."""
    if a.kind == "move" and a.switch_to is not None:
        return replace(a, switch_to=None)
    return a


def joint(opts: Mapping[int, Sequence[Action]]) -> list[tuple[Action, ...]]:
    """Every allowed pair (or single, with one Pokemon active) of actions. Two
    actions cannot bring in the same Pokemon, by a switch or a switching move."""
    keys = sorted(opts)
    out = []
    for combo in product(*(opts[k] for k in keys)):
        to = [a.switch_to for a in combo if a.switch_to is not None]
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
    # Pokemon whose move the log shows but not its target
    hidden: set[int] = field(default_factory=set)
    # Pokemon the log shows Mega Evolving this turn (Week 13: a Mega Evolution
    # shows even when the move does not)
    megas: set[int] = field(default_factory=set)


def _target(
    move: str, dex: Dex | None, user_role: str, user: int, role: str, idx: int | None
) -> tuple[str, int] | None:
    kind = ((dex.moves.get(move) or {}) if dex else {}).get("target", "normal")
    if idx is None or (kind not in FOE_TARGETS and kind not in ALLY_TARGETS):
        return None
    if role != user_role:
        return ("foe", idx)
    return None if idx == user else ("ally", idx)


def _chooses_target(move: str, dex: Dex | None) -> bool:
    kind = ((dex.moves.get(move) or {}) if dex else {}).get("target", "normal")
    return kind in FOE_TARGETS or kind in ALLY_TARGETS


def turns(log: str, dex: Dex | None = None) -> list[Turn]:
    """Every start-of-turn decision of both players, with the actions taken."""
    board = _Board()
    out: list[Turn] = []
    now: dict[str, Turn] | None = None
    slots: dict[str, dict] = {}  # who was in each slot when the turn began
    moved = False
    megas: set[tuple[str, int]] = set()
    transformed: set[tuple[str, int]] = set()

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
            slots = {r: dict(board.slots[r]) for r in ROLES}
            moved, megas = False, set()
        if t in ("-transform", "switch", "drag") and len(p) > 2 and p[2][:2] in ROLES:
            # a transformation lasts until the Pokemon leaves the field
            r = p[2][:2]
            if t == "-transform":
                idx = board._index(r, p[2])
                if idx is not None:
                    transformed.add((r, idx))
            else:
                old = board.slots[r].get(p[2][2:3]) if len(p[2]) > 2 else None
                if old is not None:
                    transformed.discard((r, old))
        if now is not None and len(p) > 2 and p[2][:2] in now:
            role = p[2][:2]
            taken = now[role].taken
            if t == "switch" and not moved and len(p) > 3:
                old = board.slots[role].get(p[2][2:3]) if len(p[2]) > 2 else None
                new = board._index(role, p[2], p[3])
                if old is not None and taken.get(old) == "none" and new is not None:
                    taken[old] = Action(old, "switch", switch_to=new)
            elif t == "switch" and moved and len(p) > 3:
                # a switching move's switch-in, during the turn: part of its choice
                old = board.slots[role].get(p[2][2:3]) if len(p[2]) > 2 else None
                new = board._index(role, p[2], p[3])
                act = taken.get(old) if old is not None else None
                if (
                    old is not None
                    and isinstance(act, Action)
                    and act.kind == "move"
                    and act.move in PIVOT_MOVES
                    and act.switch_to is None
                    and new is not None
                ):
                    taken[old] = replace(act, switch_to=new)
            elif t == "-mega":
                idx = board._index(role, p[2])
                if idx is not None:
                    megas.add((role, idx))
                    if now is not None and role in now:
                        now[role].megas.add(idx)
            elif t == "-anim" and len(p) > 4:
                idx = board._index(role, p[2])
                act = taken.get(idx) if idx is not None else None
                if isinstance(act, Action) and idx in now[role].hidden:
                    tr = p[4][:2] if p[4][:2] in ROLES else ""
                    tidx = slots.get(tr, {}).get(p[4][2:3]) if tr else None
                    target = _target(act.move, dex, role, act.user, tr, tidx)
                    if target is not None:
                        taken[idx] = Action(
                            act.user,
                            "move",
                            move=act.move,
                            target=target,
                            mega=act.mega,
                        )
                        now[role].hidden.discard(idx)
            elif t == "move" and len(p) > 3:
                moved = True
                idx = board._index(role, p[2])
                tags = " ".join(p[5:])
                if idx is not None and taken.get(idx) == "none":
                    if (
                        "[from]lockedmove" in tags.replace(" ", "")
                        or p[3] == "Struggle"
                    ):
                        taken[idx] = "forced"
                    elif (role, idx) in transformed and not board.mons[role][idx].get(
                        "moves"
                    ):
                        taken[idx] = "transformed"  # its copied moves unknown
                    elif "[from]" in tags:
                        pass  # called by another effect: not this Pokemon's choice
                    elif "[notarget]" in tags:
                        taken[idx] = "notarget"
                    else:
                        move = to_id(p[3])
                        tr = p[4][:2] if len(p) > 4 and p[4][:2] in ROLES else ""
                        # the player chose a slot: its occupant when the turn began
                        tidx = slots.get(tr, {}).get(p[4][2:3]) if tr else None
                        if tr and tidx is None:
                            tidx = board._index(tr, p[4])
                        target = _target(move, dex, role, idx, tr, tidx)
                        taken[idx] = Action(
                            idx,
                            "move",
                            move=move,
                            target=target,
                            mega=(role, idx) in megas,
                        )
                        if not tr and _chooses_target(move, dex):
                            now[role].hidden.add(idx)
            elif t == "-damage" and "[from] confusion" in raw:
                idx = board._index(role, p[2])
                if idx is not None and taken.get(idx) == "none":
                    taken[idx] = "confused"  # it hit itself; its choice is hidden
            elif t in ("cant", "faint"):
                if t == "cant" and len(p) > 3 and p[3].startswith("ability:"):
                    board.handle(p)  # Armor Tail and the like name the blocker
                    continue
                idx = board._index(role, p[2])
                if idx is not None and taken.get(idx) == "none":
                    taken[idx] = "cant" if t == "cant" else "fainted"
        board.handle(p)
    if now is not None:
        out += [now[r] for r in ROLES if r in now]
    return out


@dataclass
class Replacement:
    """One player's forced switch after a turn (DEFINITIONS §6, Week 10 Task 6):
    the board when the choice was made (the turn over, nobody in yet), the
    Pokemon that fainted in each slot to fill (`slots`, sheet positions), the
    Pokemon sent in for each (`taken`, fainted -> incoming), and the Pokemon that
    could have come in (`bench`: every one not out, as the opponent sees it; the
    log does not say which of the unseen were brought)."""

    turn: int
    role: str
    ours: list[dict]
    theirs: list[dict]
    slots: list[int]
    taken: dict[int, int] = field(default_factory=dict)
    bench: list[int] = field(default_factory=list)


def replacements(log: str) -> list[Replacement]:
    """Every forced switch the log shows: a switch after a turn's end (`|upkeep`)
    and before the next turn, into a slot whose Pokemon fainted. Both players
    choose without seeing the other's, so each side's board is the one at the
    turn's end. A Pokemon that faints on the way in starts a new choice."""
    board = _Board()
    out: list[Replacement] = []
    turn = 0
    snap: dict[str, tuple[list[dict], list[dict]]] | None = None
    now: dict[str, Replacement] = {}
    fell: dict[str, dict[str, int]] = {r: {} for r in ROLES}  # slot -> fainted

    def other(r: str) -> str:
        return "p2" if r == "p1" else "p1"

    def snapshot() -> dict[str, tuple[list[dict], list[dict]]]:
        return {r: (board.side(r), board.side(other(r))) for r in ROLES}

    def close() -> None:
        nonlocal now
        out.extend(now[r] for r in ROLES if r in now)
        now = {}

    for raw in log.split("\n"):
        p = raw.split("|")
        if len(p) < 2:
            continue
        t = p[1]
        if t == "showteam":
            board.sheet(raw)
            continue
        if t in ("turn", "win", "tie"):
            close()
            snap = None
            if t == "turn" and len(p) > 2:
                turn = int(p[2])
        elif t == "upkeep":
            snap = snapshot()
        elif t == "faint" and len(p) > 2 and p[2][:2] in ROLES and len(p[2]) > 2:
            role, slot = p[2][:2], p[2][2:3]
            idx = board.slots[role].get(slot)
            if idx is not None:
                fell[role][slot] = idx
        elif (
            t == "switch"
            and snap is not None
            and len(p) > 3
            and p[2][:2] in ROLES
            and len(p[2]) > 2
            and p[2][2:3] in fell[p[2][:2]]
        ):
            role, slot = p[2][:2], p[2][2:3]
            new = board._index(role, p[2], p[3])
            if new is not None:
                if role not in now:
                    ours, theirs = snap[role]
                    now[role] = Replacement(
                        turn,
                        role,
                        ours,
                        theirs,
                        sorted(fell[role].values()),
                        {},
                        [
                            j
                            for j, m in enumerate(ours)
                            if not m["active"] and not m["fainted"]
                        ],
                    )
                now[role].taken[fell[role].pop(slot)] = new
        board.handle(p)
        if t == "faint" and snap is not None:
            close()  # fainted after the turn's end: the next switch is a new choice
            snap = snapshot()
    close()
    return out


def replacement_options(
    r: Replacement, brought: set[int] | None = None
) -> dict[int, list[Action]]:
    """For each slot to fill (by the fainted Pokemon's sheet position), a switch
    to each Pokemon that could come in. `brought`: the side's four, where known.
    With fewer Pokemon left than slots, only the slots filled are offered."""
    pool = [j for j in r.bench if brought is None or j in brought]
    if not pool:
        return {}
    slots = r.slots if len(pool) >= len(r.slots) else sorted(r.taken)
    return {i: [Action(i, "switch", switch_to=j) for j in pool] for i in slots}


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
            elif idx in t.hidden:
                same = any(
                    o.move == act.move and o.mega == act.mega for o in opts.get(idx, [])
                )
                counts["target_hidden" if same else "out"] += 1
                if not same:
                    counts[f"out:move:{act.move}"] += 1
            elif base(act) in opts.get(idx, []):
                counts["in"] += 1
            else:
                counts["out"] += 1
                counts[f"out:{act.kind}" + (f":{act.move}" if act.move else "")] += 1
        counts["choices_offered"] += len(joint(opts)) if opts else 0
        counts["decisions"] += 1
    return counts
