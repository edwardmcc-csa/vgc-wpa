"""Week 15 Task 2-3: Reg M-C's own models (bring, choice, leads, forced
switch), fitted on its games alone and kept beside Reg M-A's and Reg M-B's,
which stay exactly as they are (DEFINITIONS §15: models are fitted per format;
adding a format never moves another's)."""

from __future__ import annotations

import argparse
import dataclasses

import pytest

from wpa import attribution as A
from wpa.bring import BringModel
from wpa.policy import FEATURES, PolicyModel


def _tools(**kw) -> A.Tools:
    base = dict(
        dexes={},
        tables={},
        moves={},
        calc=None,
        store=None,
        bring="bring M-A/M-B",
        policy="policy M-A/M-B",
        predict={},
    )
    base.update(kw)
    return A.Tools(**base)


def test_a_format_with_its_own_models_uses_them_and_only_them():
    t = _tools(by_format={"regmc": {"policy": "policy M-C", "bring": "bring M-C"}})
    mc = t.for_format("regmc")
    assert (mc.policy, mc.bring) == ("policy M-C", "bring M-C")
    assert mc.leads is None and mc.calc is t.calc  # the rest is shared
    assert t.for_format("regma") is t  # Reg M-A keeps the shared models
    assert t.policy == "policy M-A/M-B"  # unchanged


def test_each_formats_own_models_are_found_beside_the_shared_ones(tmp_path):
    shared = tmp_path / "models_v4"
    (shared / "regmc").mkdir(parents=True)
    PolicyModel([0.0] * len(FEATURES), {"regmc": {}}).save(
        shared / "regmc" / "policy.json"
    )
    BringModel(rates={"regmc": {}}, coef=[0.0] * 9, intercept=0.0).save(
        shared / "regmc" / "bring.json"
    )
    a = argparse.Namespace(
        bring=shared / "bring.json",
        policy=shared / "policy.json",
        leads=shared / "leads.json",
        replace=shared / "replace.json",
    )
    own = A.own_models(a)
    assert set(own) == {"regmc"}
    assert isinstance(own["regmc"]["policy"], PolicyModel)
    assert isinstance(own["regmc"]["bring"], BringModel)
    assert "leads" not in own["regmc"]  # none fitted yet: the shared one stays


@pytest.mark.parametrize("entry", ["analyse_game", "turn_setups", "public_setups"])
def test_every_way_into_a_game_takes_its_formats_models(entry, monkeypatch):
    seen = []

    def for_format(self, fmt):
        seen.append(fmt)
        raise LookupError("stop here")

    monkeypatch.setattr(A.Tools, "for_format", for_format)
    with pytest.raises(LookupError):
        out = getattr(A, entry)("tag", "log", "regmc", _tools())
        list(out)  # a generator starts when read
    assert seen == ["regmc"]


def test_the_advice_takes_its_formats_models(monkeypatch):
    from wpa import advise as AD

    seen = []

    def for_format(self, fmt):
        seen.append(fmt)
        raise LookupError("stop here")

    monkeypatch.setattr(A.Tools, "for_format", for_format)
    for call in (
        lambda: AD.advise("tag", "log", "regmc", _tools(), "p1"),
        lambda: AD.advise_preview("tag", "log", "regmc", _tools(), "p1"),
        lambda: AD.advise_replacement("tag", "log", "regmc", _tools(), "p1"),
    ):
        with pytest.raises(LookupError):
            call()
    assert seen == ["regmc"] * 3


def test_tools_field_kept_when_a_formats_models_are_swapped_in():
    t = _tools(by_format={"regmc": {"policy": "p"}}, strength=6.55, cap=3000)
    mc = t.for_format("regmc")
    assert dataclasses.asdict(mc) | {"policy": "policy M-A/M-B"} == dataclasses.asdict(
        t
    )


def test_the_fits_take_the_formats_they_are_given():
    """`--formats regmc --games 2000 --val-games 1000` fits Reg M-C alone; the
    default fits Reg M-A and Reg M-B together, as before."""
    from wpa.policy_data import format_caps

    assert format_caps(("regma", "regmb"), (1500, 2000), (1000, 400)) == (
        {"regma": 1500, "regmb": 2000},
        {"regma": 1000, "regmb": 400},
    )
    assert format_caps(("regmc",), (2000,), (1000,)) == (
        {"regmc": 2000},
        {"regmc": 1000},
    )
    with pytest.raises(SystemExit):
        format_caps(("regmc",), (1500, 2000), (1000,))  # one count per format


@pytest.mark.parametrize("module", ["wpa.policy", "wpa.replace_model"])
def test_each_fits_command_takes_formats(module, monkeypatch):
    import importlib
    import sys

    m = importlib.import_module(module)
    got = {}
    target = "wpa.policy_data" if module == "wpa.policy" else module
    monkeypatch.setattr(
        importlib.import_module(target), "collect", lambda a: got.update(vars(a))
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["x", "--formats", "regmc", "--games", "2000", "--val-games", "1000"],
    )
    m.main()
    assert got["formats"] == ["regmc"] and got["games"] == [2000]


def test_the_averaged_model_trains_and_finishes_reg_mc_on_its_own(monkeypatch):
    """`wpa.ensemble train --format regmc` and `finish --formats regmc`: Reg
    M-C's averaged model is made beside Reg M-A's and M-B's, which `finish`
    leaves alone unless asked."""
    import sys

    from wpa import ensemble as E

    got = {}
    monkeypatch.setattr(E, "train", lambda a: got.update(train=vars(a)))
    monkeypatch.setattr(E, "finish", lambda a: got.update(finish=vars(a)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["x", "train", "--features", "f", "--models", "m", "--format", "regmc"],
    )
    E.main()
    assert got["train"]["format"] == "regmc"
    monkeypatch.setattr(
        sys,
        "argv",
        ["x", "finish", "--features", "f", "--models", "m", "--formats", "regmc"],
    )
    E.main()
    assert got["finish"]["formats"] == ["regmc"]
    monkeypatch.setattr(
        sys, "argv", ["x", "finish", "--features", "f", "--models", "m"]
    )
    E.main()
    assert got["finish"]["formats"] == ["regma", "regmb"]  # as before
    assert E.which_model("regmb") == "pooled" and E.which_model("regmc") == "regmc"


def test_the_analysis_takes_its_formats_and_their_sets():
    """`--formats regmc --sets 40`: the strength or the measurement on Reg M-C's
    sets alone; the default stays Reg M-A's 300 and Reg M-B's 199."""
    a = A.parser().parse_args([])
    assert A.per_format(a, a.sets) == {"regma": 300, "regmb": 199}
    b = A.parser().parse_args(["--formats", "regmc", "--sets", "40"])
    assert A.per_format(b, b.sets) == {"regmc": 40}
    c = A.parser().parse_args(
        ["--formats", "regmc", "--sets", "40", "--max-games", "9"]
    )
    assert A.per_format(c, c.max_games) == {"regmc": 9}
    with pytest.raises(SystemExit):
        A.per_format(b, [40, 30])  # one count per format


def test_reg_mc_has_its_name_in_the_replay_report():
    from wpa import replay as RP

    assert RP.FORMAT_NAMES["regmc"] == "Reg M-C"


def test_each_format_names_its_model_and_its_report():
    from wpa.formats import model_for, report_name

    assert [model_for(f) for f in ("regma", "regmb", "regmc")] == [
        "regma",
        "pooled",
        "regmc",
    ]
    # Reg M-A's and M-B's report stays where it was; Reg M-C's goes beside it
    assert report_name(["regma", "regmb"]) == "report.txt"
    assert report_name(["regmc"]) == "report_regmc.txt"


def test_the_win_models_report_covers_the_formats_asked(tmp_path, monkeypatch):
    """`v2-report --formats regmc` scores Reg M-C's model alone, into its own
    report, and leaves Reg M-A's and M-B's report as it was."""
    from wpa import evaluate as EV

    (tmp_path / "report.txt").write_text("M-A and M-B\n", encoding="utf-8")
    seen = []

    class Stop(Exception):
        pass

    def predict(a, which, g, s):
        seen.append(which)
        raise Stop

    monkeypatch.setattr(EV, "_v2_predict", predict)
    a = argparse.Namespace(
        models=tmp_path,
        full="ABCDEFGHIJ",
        base=None,
        formats=["regmc"],
        features=tmp_path,
    )
    (tmp_path / "regmc").mkdir()
    (tmp_path / "regmc" / "ABCDEFGHIJ.pkl").write_bytes(b"")
    with pytest.raises(Stop):
        EV._cmd_v2_report(a)
    assert seen == ["regmc"]
    assert (tmp_path / "report.txt").read_text(encoding="utf-8") == "M-A and M-B\n"


def test_reg_mcs_measured_strength_does_not_replace_the_one_in_use():
    """DEFINITIONS §7: one strength serves every format (models_v4/strength.json).
    Reg M-C's own is measured into its own file, for the report."""
    a = A.parser().parse_args([])
    assert A.strength_path(a).as_posix().endswith("models_v4/strength.json")
    b = A.parser().parse_args(["--strength-out", "models_v4/regmc/strength.json"])
    assert A.strength_path(b).as_posix() == "models_v4/regmc/strength.json"


def test_the_summary_covers_reg_mc_too(tmp_path):
    """The run's summary has a block for each format in the records: step 12
    of the Week 15 runs measured Reg M-C, and its summary came out empty."""
    import json

    from tests.test_attribution import _rec

    rows = []
    for fmt in ("regma", "regmc"):
        r1 = _rec(f"{fmt}-g1", 3, "p1", 0.4, 0.6, True, ())
        r2 = _rec(f"{fmt}-g1", 3, "p2", 0.6, 0.4, True, ())
        rows += [dict(r1, format=fmt), dict(r2, format=fmt)]
    path = tmp_path / "a.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    text = A.report(path)
    assert "Reg M-A: 1 games" in text
    assert "Reg M-C: 1 games" in text
    assert "Reg M-B" not in text  # none of its games in the records
