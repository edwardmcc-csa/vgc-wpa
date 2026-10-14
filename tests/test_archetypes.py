"""Week 4 Task 3: archetype hold-out (wpa/archetypes.py + the splitter option).

DEFINITIONS section 13 requires holding out whole team archetypes. This task
PROPOSES a definition and builds the option; no headline number may use it
until the product owner signs the definition off.

Proposed definition (leader clustering on the six-species team):
  * rank the teams of a format by how many units (sets or single games) use
    them, most used first, ties broken by the species list;
  * walk that list: a team joins the earliest leader it shares at least
    `min_shared` species with (default 4 of 6), otherwise it becomes a new
    leader;
  * the archetype is named after its leader.
It is deliberately NOT single-linkage: on the real corpus that chains 73% of
M-A teams into one archetype at 5 shared species and 95% at 4.

Hold-out semantics: a game belongs to the archetype test split if ANY side
is a held-out archetype. Everything else is split as usual into train and
validation. So a held-out archetype is never seen in training or validation,
and the opponent of a held-out team may be a familiar archetype. (Requiring
BOTH sides to be held out leaves about 1% of games.)
"""

import random

import pytest

from wpa.formats import FORMAT_MA, FORMAT_MB, format_of
from wpa.splits import CannotSplitError, GameFile, assign_splits
from wpa.archetypes import DEFAULT_MIN_SHARED, archetype_id, build_archetypes

MA_BO3 = "gen9championsvgc2026regmabo3"
MB_BO3 = "gen9championsvgc2026regmbbo3"
MA_SINGLE = "gen9championsvgc2026regma"


def T(*species):
    assert len(species) == 6
    return tuple(sorted(species))


# --------------------------------------------------------------------------
# The definition
# --------------------------------------------------------------------------

CORE = ("a", "b", "c", "d")
T1 = T(*CORE, "e", "f")
T2 = T(*CORE, "e", "g")  # shares 5 with T1
T3 = T(*CORE, "h", "i")  # shares 4 with T1 and T2
FAR = T("a", "b", "p", "q", "r", "s")  # shares only 2 with T1


def test_the_default_is_four_shared_species_of_six():
    assert DEFAULT_MIN_SHARED == 4


def test_teams_sharing_enough_species_with_a_leader_join_it():
    m = build_archetypes({T1: 10, T2: 5, T3: 1, FAR: 7}, min_shared=4)
    assert m[T1] == m[T2] == m[T3]
    assert m[FAR] != m[T1]
    assert set(m) == {T1, T2, T3, FAR}


def test_the_most_used_team_leads_and_names_the_archetype():
    m = build_archetypes({T1: 1, T2: 9}, min_shared=4)
    assert m[T1] == m[T2] == archetype_id(T2)
    m = build_archetypes({T1: 9, T2: 1}, min_shared=4)
    assert m[T1] == m[T2] == archetype_id(T1)


def test_equal_usage_is_broken_by_the_species_list_not_by_input_order():
    first = build_archetypes({T1: 3, T2: 3, T3: 3}, min_shared=4)
    reordered = build_archetypes({T3: 3, T2: 3, T1: 3}, min_shared=4)
    assert first == reordered
    assert first[T1] == archetype_id(min(T1, T2, T3))


def test_it_does_not_chain_a_line_of_overlapping_teams_into_one_archetype():
    species = [f"s{i:02d}" for i in range(14)]
    chain = [T(*species[i : i + 6]) for i in range(9)]  # neighbours share 5
    usage = {t: 1 for t in chain}
    m = build_archetypes(usage, min_shared=4)
    # leaders are 0, 3 and 6; single-linkage would give exactly one archetype
    assert [m[t] for t in chain[:3]] == [m[chain[0]]] * 3
    assert [m[t] for t in chain[3:6]] == [m[chain[3]]] * 3
    assert len(set(m.values())) == 3


def test_a_team_that_fits_two_leaders_joins_the_more_used_one():
    l1 = T("a", "b", "c", "d", "e", "f")
    l2 = T("a", "b", "g", "h", "i", "j")  # shares only 2 with l1: its own leader
    x = T("a", "b", "c", "d", "g", "h")  # shares 4 with l1 and 4 with l2
    m = build_archetypes({l1: 10, l2: 9, x: 1}, min_shared=4)
    assert m[l1] != m[l2]
    assert m[x] == m[l1]
    m = build_archetypes({l1: 9, l2: 10, x: 1}, min_shared=4)
    assert m[x] == m[l2]


def test_min_shared_six_is_the_exact_team_and_lower_values_merge_more():
    usage = {T1: 5, T2: 4, T3: 3, FAR: 2}
    assert len(set(build_archetypes(usage, min_shared=6).values())) == 4
    assert len(set(build_archetypes(usage, min_shared=5).values())) == 3
    assert len(set(build_archetypes(usage, min_shared=4).values())) == 2
    assert len(set(build_archetypes(usage, min_shared=2).values())) == 1


@pytest.mark.parametrize("bad", [0, 7, 4.5, "4", None, -1])
def test_min_shared_must_be_a_whole_number_from_one_to_six(bad):
    with pytest.raises(ValueError):
        build_archetypes({T1: 1}, min_shared=bad)


def test_a_team_that_is_not_six_species_is_rejected():
    with pytest.raises(ValueError):
        build_archetypes({("a", "b", "c"): 1}, min_shared=2)


# --------------------------------------------------------------------------
# A synthetic corpus with known archetypes
#
# Archetype j has the core species c{j}_0..c{j}_3; every team in it adds two
# species unique to that team. Teams of one archetype share exactly 4
# species; teams of different archetypes share none. The tests identify an
# archetype from the species names, independent of the code under test.
# --------------------------------------------------------------------------


def variant(j, k):
    return T(*(f"c{j}_{i}" for i in range(4)), f"u{j}_{k}_a", f"u{j}_{k}_b")


def arch_index(team):
    return int(next(s for s in team if s.startswith("c")).split("_")[0][1:])


def _game(tag, set_id, a, b):
    return [
        GameFile(tag, "p1", set_id, a, b, 5, 0),
        GameFile(tag, "p2", set_id, b, a, 5, 0),
    ]


def arch_corpus(log, n_arch, n_sets, seed, n_variants=6, first_battle=1):
    """n_sets best-of-three sets between random archetypes (and variants)."""
    rng = random.Random(seed)
    files = []
    for s in range(n_sets):
        ja, jb = rng.randrange(n_arch), rng.randrange(n_arch)
        a = variant(ja, rng.randrange(n_variants))
        b = variant(jb, rng.randrange(n_variants))
        set_number = first_battle + s
        sid = f"{log}-{set_number}"
        for g in (1, 2):
            files += _game(f"{log}-{set_number}{g}", sid, a, b)
    return files


def key(f):
    return (f.tag, f.role)


def seen_archetypes(files, assignments, splits):
    out = set()
    for f in files:
        if assignments.get(key(f)) in splits:
            out |= {arch_index(f.own_team), arch_index(f.opp_team)}
    return out


# --------------------------------------------------------------------------
# The hold-out
# --------------------------------------------------------------------------


def test_a_held_out_archetype_never_appears_in_train_or_validation():
    files = arch_corpus(MA_BO3, 300, 2500, seed=1)
    result = assign_splits(files, archetype_holdout=0.1)
    seen_in_training = seen_archetypes(files, result.assignments, ("train", "validation"))
    seen_in_test = seen_archetypes(files, result.assignments, ("test",))
    held = seen_in_test - seen_in_training
    assert held  # something really was held out
    # every test game touches an archetype that training never saw...
    for f in files:
        if result.assignments[key(f)] == "test":
            assert {arch_index(f.own_team), arch_index(f.opp_team)} & held
    # ...and no train/validation game touches one of them, by construction
    for f in files:
        if result.assignments[key(f)] != "test":
            assert not ({arch_index(f.own_team), arch_index(f.opp_team)} & held)


def test_the_reported_held_out_archetypes_match_what_the_files_show():
    files = arch_corpus(MA_BO3, 300, 2500, seed=2)
    result = assign_splits(files, archetype_holdout=0.1)
    ids = result.held_out_archetypes[FORMAT_MA]
    mapping = result.archetypes[FORMAT_MA]
    assert ids
    for f in files:
        touches = {mapping[f.own_team], mapping[f.opp_team]} & ids
        assert bool(touches) == (result.assignments[key(f)] == "test")


def test_the_share_of_archetypes_held_out_follows_the_parameter():
    files = arch_corpus(MA_BO3, 600, 6000, seed=3)
    for fraction in (0.05, 0.2):
        result = assign_splits(files, archetype_holdout=fraction)
        stats = result.archetype_stats[FORMAT_MA]
        assert stats.held_out / stats.archetypes == pytest.approx(fraction, abs=0.04)
        assert result.archetype_holdout == fraction


def test_set_pairing_and_perspective_guarantees_still_hold_in_archetype_mode():
    files = arch_corpus(MA_BO3, 200, 3000, seed=4) + arch_corpus(
        MB_BO3, 60, 900, seed=5
    )
    result = assign_splits(files, archetype_holdout=0.1)
    by_set, by_tag, by_pairing = {}, {}, {}
    for f in files:
        split = result.assignments[key(f)]
        by_set.setdefault(f.set_id, set()).add(split)
        by_tag.setdefault(f.tag, set()).add(split)
        by_pairing.setdefault(
            (format_of(f.tag), frozenset([f.own_team, f.opp_team])), set()
        ).add(split)
    assert all(len(v) == 1 for v in by_set.values())
    assert all(len(v) == 1 for v in by_tag.values())
    assert all(len(v) == 1 for v in by_pairing.values())


def test_each_format_gets_its_own_hold_out_and_its_own_train_and_validation():
    files = arch_corpus(MA_BO3, 200, 3000, seed=6) + arch_corpus(
        MB_BO3, 80, 1200, seed=7
    )
    result = assign_splits(files, archetype_holdout=0.1)
    for fmt in (FORMAT_MA, FORMAT_MB):
        for split in ("train", "validation", "test"):
            assert result.counts[fmt][split].units > 0, (fmt, split)
        assert result.held_out_archetypes[fmt]


def test_one_formats_data_never_changes_the_other_formats_hold_out():
    ma = arch_corpus(MA_BO3, 200, 3000, seed=8)
    mb = arch_corpus(MB_BO3, 80, 1200, seed=9)
    alone = assign_splits(ma, archetype_holdout=0.1).assignments
    together = assign_splits(ma + mb, archetype_holdout=0.1).assignments
    assert all(together[k] == v for k, v in alone.items())


def test_the_archetype_split_is_identical_across_runs_and_input_orders():
    files = arch_corpus(MA_BO3, 200, 3000, seed=10)
    first = assign_splits(files, archetype_holdout=0.1)
    shuffled = list(files)
    random.Random(1).shuffle(shuffled)
    second = assign_splits(shuffled, archetype_holdout=0.1)
    assert first.assignments == second.assignments
    assert first.held_out_archetypes == second.held_out_archetypes


def test_a_format_with_one_archetype_cannot_be_held_out_and_says_so():
    ma = arch_corpus(MA_BO3, 200, 3000, seed=11)
    mb = arch_corpus(MB_BO3, 1, 200, seed=12, n_variants=6)  # a single archetype
    with pytest.raises(CannotSplitError) as err:
        assign_splits(ma + mb, archetype_holdout=0.1)
    message = str(err.value)
    assert FORMAT_MB in message and "cannot" in message.lower()
    assert FORMAT_MA not in message


@pytest.mark.parametrize("bad", [0, 1, -0.1, 1.5, "0.1"])
def test_the_hold_out_fraction_must_be_strictly_between_zero_and_one(bad):
    with pytest.raises(ValueError):
        assign_splits(arch_corpus(MA_BO3, 100, 1000, seed=13), archetype_holdout=bad)


def test_without_the_option_nothing_changes():
    files = arch_corpus(MA_BO3, 200, 3000, seed=14)
    plain = assign_splits(files)
    explicit = assign_splits(files, archetype_holdout=None)
    assert plain.assignments == explicit.assignments
    assert plain.archetype_holdout is None
    assert plain.held_out_archetypes == {}


def test_train_and_validation_keep_their_ratio_after_the_hold_out():
    files = arch_corpus(MA_BO3, 800, 12000, seed=15)
    result = assign_splits(
        files,
        proportions={"train": 0.6, "validation": 0.3, "test": 0.1},
        archetype_holdout=0.1,
    )
    c = result.counts[FORMAT_MA]
    ratio = c["train"].units / (c["train"].units + c["validation"].units)
    assert ratio == pytest.approx(0.6 / 0.9, abs=0.04)


# --------------------------------------------------------------------------
# The numbers the product owner needs to sign the definition off
# --------------------------------------------------------------------------


def test_archetype_statistics_count_units_per_archetype():
    files = arch_corpus(MA_BO3, 120, 2000, seed=16)
    result = assign_splits(files, archetype_holdout=0.1)
    # independent count: a unit counts once for each archetype it touches
    units = {}
    for f in files:
        units.setdefault(f.set_id, set()).update(
            {arch_index(f.own_team), arch_index(f.opp_team)}
        )
    expected = {}
    for touched in units.values():
        for j in touched:
            expected[j] = expected.get(j, 0) + 1
    stats = result.archetype_stats[FORMAT_MA]
    assert stats.archetypes == len(expected)
    assert stats.sizes == sorted(expected.values(), reverse=True)
    assert stats.largest[0][1] == max(expected.values())
    assert [n for _, n in stats.largest] == sorted(
        expected.values(), reverse=True
    )[: len(stats.largest)]


def test_the_report_mentions_the_hold_out_and_the_archetype_counts():
    files = arch_corpus(MA_BO3, 120, 2000, seed=17)
    result = assign_splits(files, archetype_holdout=0.1)
    text = result.describe()
    assert "archetype" in text.lower()
    assert "held out" in text.lower()
    recorded = result.to_dict()
    assert recorded["archetype_holdout"] == 0.1
    assert recorded["min_shared"] == DEFAULT_MIN_SHARED
    assert recorded["archetype_stats"][FORMAT_MA]["archetypes"] > 0
