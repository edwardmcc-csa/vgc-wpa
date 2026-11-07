"""How likely each Pokemon is to pick each of its options (Week 9 Task 3).

DEFINITIONS §7 judges a choice against the opponent's likely replies, not the one
they made. This module learns those replies from the training split: for one
Pokemon at a move-selection decision, each legal option (`wpa.choices.options`)
gets a score from a few facts about it, and its chance is its share of the
exponentiated scores (a conditional logit, like `wpa.bring`'s set chances).

The facts are what a player sees: what kind of action it is (switch, Protect and
whether it was used last turn, a status move, Fake Out on the first turn or after
it, priority, a spread move, an ally target, Mega Evolution), how hard it hits
(expected share of the target's hit points and knock-out chance, from the damage
calculator and the spread estimates), the target's hit points, how often players
pick this move when they have it (a rate learned from training, per format), a
field condition already in force (Tailwind blowing, Trick Room up), and for a
switch, the incoming Pokemon's hit points, whether it is still unseen and how
likely it was brought (`wpa.bring`), how hard it hits back, and how threatened
the Pokemon leaving is.

The two Pokemon of a side are taken as choosing independently (v1); a side's
joint reply is the product. Nothing from later in the game is used.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from wpa.choices import Action

FEATURES = (
    "is_switch",
    "is_protect",
    "protect_again",
    "is_status",
    "fakeout_first",
    "fakeout_late",
    "priority",
    "is_spread",
    "targets_ally",
    "mega",
    "dmg_share",
    "ko_chance",
    "target_hp",
    "target_weaker",
    "move_rate",
    "redundant_field",
    "user_hp",
    "switch_hp",
    "switch_unseen",
    "switch_bring",
    "switch_best_dmg",
    "switch_when_threatened",
)
PROTECT_LIKE = {
    "protect",
    "detect",
    "spikyshield",
    "kingsshield",
    "banefulbunker",
    "silktrap",
    "burningbulwark",
    "obstruct",
    "wideguard",
    "quickguard",
}
SPREAD = {"allAdjacentFoes", "allAdjacent"}
FIELD_MOVES = {
    "tailwind": "tailwind",
    "trickroom": "trickroom",
    "reflect": "reflect",
    "lightscreen": "lightscreen",
    "auroraveil": "auroraveil",
}
SMOOTH = 20.0


class DamageInfo:
    """Damage facts at one decision, from the decider's side: `share(i, move,
    target)` and `ko(...)` for one target, `best(i)` (the best share Pokemon i
    could take of an opposing active), `threat(i)` (the best share an opposing
    active could take of it)."""

    def __init__(
        self, s: Mapping, sheets: Mapping, role: str, spreads, dex, calc, fld=None
    ):
        self.s, self.sheets, self.role = s, sheets, role
        self.other = "p2" if role == "p1" else "p1"
        self.spreads, self.dex, self.calc = spreads, dex, calc
        self.fld = fld or {}
        self._memo: dict = {}

    def _pair(self, a_side: str, i: int, move: str, d_side: str, j: int, spread: bool):
        key = (a_side, i, move, d_side, j, spread)
        if key in self._memo:
            return self._memo[key]
        from wpa.features import _board_state
        from wpa.spreads import damage_request, default_spread

        role_of = {"our": self.role, "their": self.other}
        mons = {"our": self.s["our_pokemon"], "their": self.s["opp_pokemon"]}

        def spread_of(side, k):
            r = role_of[side]
            sp = self.spreads.get((r, k))
            if sp is None:
                mon = self.sheets[r][k]
                sp = default_spread(
                    mon.nature,
                    (self.dex.species.get(mon.species) or {}).get("baseStats"),
                )
            return sp

        a_st, d_st = mons[a_side][i], mons[d_side][j]
        req = damage_request(
            self.sheets[role_of[a_side]][i],
            _board_state(a_st),
            spread_of(a_side, i),
            self.sheets[role_of[d_side]][j],
            _board_state(d_st),
            spread_of(d_side, j),
            move,
            self.dex,
            spread=spread,
            field=self.fld,
        )
        ans = self.calc.run([req])[0]
        rolls = ans.get("rolls")
        if not rolls or "error" in ans:
            out = (0.0, 0.0)
        else:
            hp = max(
                1.0,
                (d_st["hp_fraction"] if d_st["hp_fraction"] > 0 else 1.0)
                * ans["max_hp"],
            )
            out = (
                min(1.0, sum(rolls) / len(rolls) / hp),
                sum(r >= hp for r in rolls) / len(rolls),
            )
        self._memo[key] = out
        return out

    def share(self, i: int, move: str, target: tuple[str, int], spread: bool = False):
        side = "their" if target[0] == "foe" else "our"
        return self._pair("our", i, move, side, target[1], spread)

    def _foes(self):
        return [
            j
            for j, p in enumerate(self.s["opp_pokemon"])
            if p["active"] and not p["fainted"]
        ]

    def best(self, i: int) -> float:
        mon = self.sheets[self.role][i]
        best = 0.0
        for move in mon.moves:
            for j in self._foes():
                best = max(best, self._pair("our", i, move, "their", j, False)[0])
        return best

    def threat(self, i: int) -> float:
        out = 0.0
        for j in self._foes():
            for move in self.sheets[self.other][j].moves:
                out = max(out, self._pair("their", j, move, "our", i, False)[0])
        return out


def option_features(
    s: Mapping,
    a: Action,
    moves: Mapping,
    rates: Mapping[str, float],
    ctx: DamageInfo | None,
    our_side: set[str] | None = None,
    trickroom: bool = False,
    bring_p: Sequence[float] | None = None,
) -> list[float]:
    """The facts about one option of the Pokemon `a.user`, in FEATURES order,
    from the decider's side of the board `s`."""
    f = dict.fromkeys(FEATURES, 0.0)
    ours, theirs = s["our_pokemon"], s["opp_pokemon"]
    st = ours[a.user]
    f["user_hp"] = st["hp_fraction"]
    if a.kind == "switch":
        j = a.switch_to if a.switch_to is not None else 0
        tgt = ours[j]
        unseen = not (tgt["active"] or tgt["fainted"] or tgt["hp_fraction"] > 0)
        f["is_switch"] = 1.0
        f["switch_hp"] = 1.0 if unseen else tgt["hp_fraction"]
        f["switch_unseen"] = float(unseen)
        if unseen and bring_p is not None and j < len(bring_p):
            p = min(max(bring_p[j], 1e-4), 1 - 1e-4)
            f["switch_bring"] = math.log(p / (1 - p))
        if ctx is not None:
            f["switch_best_dmg"] = ctx.best(j)
            f["switch_when_threatened"] = ctx.threat(a.user)
        return [f[k] for k in FEATURES]
    m = moves.get(a.move) or {}
    cat = m.get("category", "Physical")
    f["is_protect"] = float(a.move in PROTECT_LIKE)
    f["protect_again"] = float(
        a.move in PROTECT_LIKE and st.get("protect_streak", 0) > 0
    )
    f["is_status"] = float(cat == "Status" and a.move not in PROTECT_LIKE)
    first = not st.get("moved")
    f["fakeout_first"] = float(a.move == "fakeout" and first)
    f["fakeout_late"] = float(a.move == "fakeout" and not first)
    f["priority"] = float((m.get("priority") or 0) > 0 and cat != "Status")
    f["is_spread"] = float(m.get("target") in SPREAD)
    f["targets_ally"] = float(a.target is not None and a.target[0] == "ally")
    f["mega"] = float(a.mega)
    f["move_rate"] = rates.get(a.move, 0.0)
    eff = FIELD_MOVES.get(a.move)
    if eff == "trickroom":
        f["redundant_field"] = float(trickroom)
    elif eff is not None:
        f["redundant_field"] = float(eff in (our_side or set()))
    if a.target is not None and a.target[0] == "foe":
        t = theirs[a.target[1]]
        f["target_hp"] = t["hp_fraction"]
        others = [
            p
            for j, p in enumerate(theirs)
            if p["active"] and not p["fainted"] and j != a.target[1]
        ]
        f["target_weaker"] = float(
            bool(others) and t["hp_fraction"] < min(p["hp_fraction"] for p in others)
        )
    if ctx is not None and cat != "Status":
        if f["is_spread"]:
            for j, p in enumerate(theirs):
                if p["active"] and not p["fainted"]:
                    sh, ko = ctx.share(a.user, a.move, ("foe", j), spread=True)
                    f["dmg_share"] += sh
                    f["ko_chance"] += ko
        elif a.target is not None and a.target[0] == "foe":
            f["dmg_share"], f["ko_chance"] = ctx.share(a.user, a.move, a.target)
    return [f[k] for k in FEATURES]


@dataclass
class PolicyModel:
    weights: list[float]
    rates: dict[str, dict[str, float]] = field(
        default_factory=dict
    )  # format -> move -> logit
    # multiplies every score: above 1 the likeliest options get more of the
    # chance, in the same order (PO decision, 6 Nov; `wpa.attribution`)
    sharpness: float = 1.0

    def chances(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(X, dtype=float) @ np.asarray(self.weights, dtype=float)
        z = self.sharpness * z
        z = np.exp(z - z.max())
        return z / z.sum()

    def save(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "features": list(FEATURES),
                    "weights": self.weights,
                    "rates": self.rates,
                    "sharpness": self.sharpness,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> PolicyModel:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d["features"] != list(FEATURES):
            raise ValueError("policy features changed since this model was saved")
        return cls(d["weights"], d.get("rates", {}), float(d.get("sharpness", 1.0)))


def fit(groups: Sequence[tuple[np.ndarray, int]], l2: float = 1e-2) -> PolicyModel:
    """Maximum likelihood (with a small ridge) over (options x features, chosen)."""
    from scipy.optimize import minimize

    k = len(FEATURES)

    def nll(w):
        total, grad = 0.0, np.zeros(k)
        for X, c in groups:
            z = X @ w
            zmax = z.max()
            e = np.exp(z - zmax)
            p = e / e.sum()
            total -= z[c] - zmax - math.log(e.sum())
            grad -= X[c] - p @ X
        total += 0.5 * l2 * float(w @ w) * len(groups)
        grad += l2 * w * len(groups)
        return total, grad

    res = minimize(nll, np.zeros(k), jac=True, method="L-BFGS-B")
    return PolicyModel([float(x) for x in res.x])


def score(
    model: PolicyModel, groups: Sequence[tuple[np.ndarray, int]]
) -> tuple[float, float]:
    """(mean log chance of the option chosen, the same for a uniform guess)."""
    ll = [math.log(max(model.chances(X)[c], 1e-300)) for X, c in groups]
    un = [math.log(1 / len(X)) for X, _ in groups]
    return float(np.mean(ll)), float(np.mean(un))


def rates_from_counts(
    chosen: Mapping[str, float], offered: Mapping[str, float]
) -> dict[str, float]:
    """Log-odds that a move is picked when offered, pulled towards the average."""
    tot_c, tot_o = sum(chosen.values()), sum(offered.values())
    base = tot_c / tot_o if tot_o else 0.1
    out = {}
    for mv, o in offered.items():
        p = (chosen.get(mv, 0.0) + SMOOTH * base) / (o + SMOOTH)
        p = min(max(p, 1e-4), 1 - 1e-4)
        out[mv] = math.log(p / (1 - p))
    return out


def main() -> None:  # pragma: no cover - runs on the corpus
    p = argparse.ArgumentParser(
        description="Fit the opponent choice model (Week 9 Task 3)."
    )
    p.add_argument("--logs", type=Path, default=Path("logs_shards"))
    p.add_argument("--splits", type=Path, default=Path("splits.json"))
    p.add_argument("--usage", type=Path, default=Path("usage_stats"))
    p.add_argument("--bring", type=Path, default=Path("models_v4/bring.json"))
    p.add_argument(
        "--moves-dir",
        type=Path,
        default=None,
        help="saved dump_moves.js output, moves_<format>.json",
    )
    p.add_argument("--showdown", type=Path, default=Path("pokemon-showdown"))
    p.add_argument(
        "--dex-tables",
        type=Path,
        default=None,
        help="a pickled (dexes, tables) pair, instead of reading Showdown",
    )
    p.add_argument(
        "--games",
        type=int,
        nargs=2,
        default=(1500, 2000),
        help="training games per format (Reg M-A, Reg M-B)",
    )
    p.add_argument("--val-games", type=int, nargs=2, default=(1000, 400))
    p.add_argument("--out", type=Path, default=Path("models_v4/policy.json"))
    a = p.parse_args()
    from wpa.policy_data import collect

    collect(a)


if __name__ == "__main__":
    main()
