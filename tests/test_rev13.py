"""DEFINITIONS revision 13 (PO, 15 Nov 2026): cost vs. best is measured against
every choice the rules allow, not the 10 the choice model finds likeliest; the
choice model predicts but never sets the standard (Week 15 Task 1)."""

from __future__ import annotations

import pytest

from wpa import attribution as A
from wpa import replay as RP
from wpa.choices import Action

# fifteen joint choices; the choice model finds the last one least likely, and it
# is the best by far
CHOICES = [(Action(0, "move", move=f"m{i}", target=("foe", 0)),) for i in range(15)]
FULL = [(j, (15 - i) / 120) for i, j in enumerate(CHOICES)]
REPLY = (Action(0, "move", move="tackle", target=("foe", 0)),)
LIKELY = [(REPLY, 1.0)]


def value(ours, theirs):
    i = CHOICES.index(ours)
    return 0.9 if i == 14 else 0.5 - 0.01 * i


def test_every_choice_the_rules_allow_is_compared_likeliest_first():
    alts, usual = A.choices_to_compare(FULL, None)
    assert [a[0][0] for a in alts] == CHOICES  # all 15, likeliest first
    assert usual == set(CHOICES[: A.USUAL])  # the 10 players most often make
    alts10, _ = A.choices_to_compare(FULL, 10)
    assert len(alts10) == 10  # the old way, kept for comparison runs
    assert A.choices_to_compare(FULL, 0) == ([], usual)


def test_a_choice_with_almost_no_chance_is_still_compared():
    tiny = FULL + [((Action(0, "switch", switch_to=2),), 1e-15)]
    alts, _ = A.choices_to_compare(tiny, None)
    assert len(alts) == 16


def test_the_best_play_can_be_one_players_rarely_make():
    alts, usual = A.choices_to_compare(FULL, None)
    mine = [(CHOICES[0], 1.0)]
    e_mine = A.expected(value, mine, LIKELY)
    best = A.best_choice(value, alts, LIKELY, e_mine)
    assert best == CHOICES[14] and best not in usual
    s = A.decompose(value, 0.5, 0.5, mine, LIKELY, LIKELY, alts)
    assert s.vs_best == pytest.approx(0.5 - 0.9)
    # with the usual ten only, as before revision 13, it could not be found
    old, _ = A.choices_to_compare(FULL, 10)
    assert A.best_choice(value, old, LIKELY, e_mine) is None


def test_the_analysis_and_the_replay_report_compare_every_choice_by_default():
    assert A.Tools.__dataclass_fields__["alternatives"].default is None
    assert A.parser().parse_args([]).alternatives is None


def test_the_report_says_when_the_best_play_is_one_players_rarely_make():
    from tests.test_replay import LOG, RECORDS, TAG, Y

    recs = [dict(r) for r in RECORDS]
    recs[1].update(best=A.joint_json(Y), best_rare=True, compared=42)
    text = RP.game_report(TAG, LOG, recs, "p1", top=3)
    line = next(x for x in text.splitlines() if "Best: " in x)
    assert line.rstrip().endswith("(a play players rarely make)")
    assert "42 choices compared" in text
    recs[1]["best_rare"] = False
    text = RP.game_report(TAG, LOG, recs, "p1", top=3)
    assert "rarely make" not in text


# --------------------------------------------------------------------------
# The live advice: every choice, ranked by win chance, in two passes
# --------------------------------------------------------------------------

from wpa import advise as AD  # noqa: E402

R = [(Action(0, "move", move=f"r{k}", target=("foe", 0)),) for k in range(5)]
REPLIES = [(R[k], p) for k, p in enumerate((0.4, 0.3, 0.15, 0.1, 0.05))]


def value2(ours, theirs):
    """The rarest choice is best against every reply; choice 1 is best against
    the likeliest reply only, and poor against the rest."""
    i, k = CHOICES.index(ours), R.index(theirs)
    if i == 14:
        return 0.8
    if i == 1:
        return 0.95 if k == 0 else 0.1
    return 0.5 - 0.01 * i


def test_the_advice_ranks_every_choice_and_the_best_first():
    asked = []
    got, compared = AD.rank_all(
        value2, FULL, REPLIES, prepare=asked.append, screen=3, finalists=3
    )
    assert compared == 15
    assert got[0][0] == CHOICES[14]  # players rarely make it; it is the best
    assert got[0][1] == pytest.approx(0.8)
    assert got[0][2] == pytest.approx(FULL[14][1])  # how often players make it
    assert {j for j, _v, _p in got} == set(CHOICES)  # every choice is ranked


def test_the_first_pass_never_drops_the_usual_choices_from_the_full_pass():
    """The choice model orders the search: the ones players usually make are
    always valued in full, beside the first pass's best."""
    asked = []
    got, _ = AD.rank_all(
        value2, FULL, REPLIES, prepare=asked.append, screen=1, finalists=2
    )
    first, second = asked
    assert len(first) == 15 * 1  # every choice, against the likeliest reply
    full_pass = {j for j, _r in second}
    assert set(CHOICES[: A.USUAL]) <= full_pass and CHOICES[14] in full_pass
    # valued in full, choice 1 (great against one reply only) is not first
    assert got[0][0] == CHOICES[14]
    v1 = next(v for j, v, _p in got if j == CHOICES[1])
    assert v1 == pytest.approx(0.95 * 0.4 + 0.1 * 0.6)


def test_with_few_choices_every_one_is_valued_in_full_at_once():
    asked = []
    few = FULL[:4]
    got, compared = AD.rank_all(value2, few, REPLIES, prepare=asked.append)
    assert compared == 4 and len(asked) == 1 and len(asked[0]) == 4 * 5
    assert [j for j, _v, _p in got][0] == CHOICES[0]  # 0.5; choice 1 averages 0.44


def test_the_advice_says_how_many_choices_it_compared():
    from tests.test_advise import TABLE, X, Y  # noqa: F401
    from tests.test_replay import LOG, TAG

    adv = AD.Advice(
        tag=TAG,
        turn=2,
        role="p1",
        wp=0.58,
        choices=[(Y, 0.73, 0.003), (X, 0.45, 0.6)],
        replies=[(R[0], 1.0)],
        kept=0.9,
        hidden=False,
        typical=0.62,
        compared=90,
    )
    text = AD.advice_text(adv, LOG)
    assert "Your choices, best first, of the 90 the rules allow" in text
    first = next(x for x in text.splitlines() if x.strip().startswith("1."))
    assert "players choose it 0%" in first  # the best can be one players rarely make


def test_a_turns_advice_ranks_every_choice():
    from types import SimpleNamespace as NS

    class TV:
        def __init__(self):
            self.asked = []

        def prepare(self, pairs):
            self.asked.append(pairs)

        def for_role(self, role):
            return value2  # from either side: (yours, theirs)

    tv = TV()
    pt = NS(wp=0.5, hidden=False)
    mine = [(CHOICES[0], 1.0)]
    adv = AD._advice("t", 2, "p1", pt, tv, FULL, mine, REPLIES, 1.0, every=True)
    assert adv.compared == 15 and adv.choices[0][0] == CHOICES[14]
    # as p2, the pairs go to the resolver as (p1's, p2's)
    tv2 = TV()
    AD._advice("t", 2, "p2", pt, tv2, FULL, mine, REPLIES, 1.0, every=True)
    assert all(a in R and b in CHOICES for a, b in tv2.asked[0])


def test_each_record_also_keeps_the_best_of_the_usual_ten():
    """So one run measures what revision 13 adds: the gain of the best of every
    choice over the best of the 10 players usually make."""
    alts, usual = A.choices_to_compare(FULL, None)
    mine = [(CHOICES[3], 1.0)]
    e_mine = A.expected(value, mine, LIKELY)
    got = A.best_of_usual(value, alts, usual, LIKELY, e_mine)
    assert got == pytest.approx(e_mine - 0.5)  # choice 0 is the usual best
    assert A.best_of_usual(value, alts, usual, LIKELY, 0.95) == 0.0  # yours beats them
