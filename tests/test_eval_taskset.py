"""The task-set manifests (eval plan section 4.8).  The regeneration test is
the tripwire: a changed spec or generator fails it, and
``python -m roaddraft.eval taskset --write`` regenerates the manifests once
the change is meant."""
from __future__ import annotations

from collections import Counter

import pytest

from roaddraft.eval import taskset as tasksets


@pytest.mark.parametrize("name", tasksets.NAMES)
def test_manifest_regenerates_to_the_same_task_ids(name):
    problems = tasksets.check(name)
    assert not problems, (f"{name} is stale: {'; '.join(problems)}. If the spec or generator "
                          f"change is meant: python -m roaddraft.eval taskset --write")


def test_sizes_and_seeds():
    dev, test, var = (tasksets.load(n)["tasks"] for n in tasksets.SEEDED_NAMES)
    assert len(dev) == 50 and [t["seed"] for t in dev] == list(range(1, 51))
    assert len(test) == 100 and [t["seed"] for t in test] == list(range(1000, 1100))
    assert len(var) == tasksets.VARIANCE_SIZE and var == test[:tasksets.VARIANCE_SIZE]
    assert not {t["task_id"] for t in dev} & {t["task_id"] for t in test}


def test_d1_test_is_balanced_over_curves_and_equations_and_mixes_the_rest():
    test = tasksets.load("d1-test")["tasks"]
    curves = Counter(t["curves"] for t in test)
    assert set(curves) == {1, 2, 3} and max(curves.values()) - min(curves.values()) <= 1
    eq = Counter(t["equations"] for t in test)
    assert abs(eq[True] - eq[False]) <= 2
    assert len({t["task_type"] for t in test}) == len(tasksets.SEEDED_TYPES)
    assert {t["sheets"] for t in test} == {1, 2}
    for t in test:
        assert t["task_id"].startswith("D1-")


def test_entries_filter_and_limit_and_task_from_entry_checks_the_id():
    rows = tasksets.entries("d1-dev", limit=5)
    assert len(rows) == 5
    one = tasksets.entries("d1-dev", task_ids=[rows[2]["task_id"]])
    assert one == [rows[2]]
    task = tasksets.task_from_entry(rows[2])
    assert task.task_id == rows[2]["task_id"]
    with pytest.raises(ValueError):
        tasksets.task_from_entry({**rows[2], "task_id": "D1-000000-wrong"})
    assert tasksets.task_from_entry({**rows[2], "task_id": "D1-000000-wrong"}, strict=False)


def test_dials_cycle():
    d = [tasksets.dials(i) for i in range(12)]
    assert [x["curves"] for x in d] == [1, 2, 3] * 4
    assert [x["equations"] for x in d] == [False] * 3 + [True] * 3 + [False] * 3 + [True] * 3
    assert [x["sheets"] for x in d] == [1] * 6 + [2] * 6


# ------------------------------------------------------------ the real sets


def test_real_quotas_split_each_group_evenly_over_its_types():
    from roaddraft.tasks.types import D1_REAL_GROUPS, REAL_GROUPS, REAL_TASK_TYPES, real_group
    q = tasksets.real_quotas()
    assert list(q) == list(REAL_TASK_TYPES), "quotas run in type order, every real type in"
    assert sum(q.values()) == tasksets.REAL_PER_GROUP * len(D1_REAL_GROUPS) == 100
    for key, _, types in REAL_GROUPS:
        if key not in D1_REAL_GROUPS:
            continue  # the whole job is d1-real-hard's (2026-11-03)
        shares = [q[ty] for ty in types]
        assert sum(shares) == tasksets.REAL_PER_GROUP
        assert max(shares) - min(shares) <= 1 and shares == sorted(shares, reverse=True)
    assert q["real-draw-alignment"] == 25 and q["real-construction-callouts"] == 25
    assert q["real-stationing"] == 5 and q["real-plan-sheet"] == 5
    # a type added to a group shares its quota: seven types in the letter group would get 4,4,4,4,3,3,3
    assert tasksets.real_quotas(27)["real-stationing"] == 6 and tasksets.real_quotas(27)["real-alignment-data"] == 5
    assert real_group("real-bearings") == "letter"
    with pytest.raises(ValueError):
        real_group("real-no-such-type")


def test_real_sets_draw_every_group_type_and_agency_from_the_catalogue():
    from roaddraft.tasks.types import D1_REAL_GROUPS, REAL_TASK_TYPES, real_group
    catalogue = {t["task_id"]: t for t in tasksets.load_catalog()["tasks"]}
    real, dev = (tasksets.load(n) for n in tasksets.REAL_NAMES)
    real, real_groups, dev = real["tasks"], real["groups"], dev["tasks"]
    groups_with_types = list(D1_REAL_GROUPS)  # the whole job is d1-real-hard's
    assert len(real) == tasksets.REAL_PER_GROUP * len(groups_with_types) == 100
    assert len(dev) == tasksets.REAL_DEV_PER_TYPE * len(REAL_TASK_TYPES) == 24
    # held out: the same number of tasks in every question group, split over the group's types
    assert Counter(t["group"] for t in real) == {k: tasksets.REAL_PER_GROUP for k in groups_with_types}
    assert real_groups == {k: tasksets.REAL_PER_GROUP for k in groups_with_types}
    assert Counter(t["task_type"] for t in real) == tasksets.real_quotas()
    # dev: two of every type, for smoke runs
    assert Counter(t["task_type"] for t in dev) == {ty: tasksets.REAL_DEV_PER_TYPE for ty in REAL_TASK_TYPES}
    for rows in (real, dev):
        assert len({t["task_id"] for t in rows}) == len(rows)
        for t in rows:
            c = catalogue[t["task_id"]]  # every task is a validated catalogue task
            assert (c["sheet_id"], c["alignment"], c["type"]) == (t["sheet_id"], t["alignment"],
                                                                   t["task_type"])
            assert t["sheets"] == 1 and t["task_id"].startswith("D1-")
            assert t["group"] == real_group(t["task_type"])
    # the held-out set reaches every agency; the first twelve are one of each type
    assert {t["agency"] for t in real} == {t["agency"] for t in catalogue.values()}
    assert {t["task_type"] for t in real[:len(REAL_TASK_TYPES)]} == set(REAL_TASK_TYPES)
    # dev and held-out never share a sheet
    assert not {t["sheet_id"] for t in real} & {t["sheet_id"] for t in dev}
    assert {t["sheet_id"] for t in dev} == set(tasksets.real_dev_sheets(list(catalogue.values())))
    assert all(t["agency"] == tasksets.REAL_DEV_AGENCY for t in dev)


def test_a_real_entry_rebuilds_its_task_and_checks_the_id():
    entry = tasksets.entries("d1-real-dev", limit=1)[0]
    task = tasksets.task_from_entry(entry)
    assert task.task_id == entry["task_id"] and task.brief.task_type == entry["task_type"]
    assert task.files, "a real task ships its base files"
    with pytest.raises(ValueError):
        tasksets.task_from_entry({**entry, "task_id": "D1-000000-wrong"})
    assert tasksets.task_from_entry({**entry, "task_id": "D1-000000-wrong"}, strict=False)


def test_a_catalogue_validated_under_another_verifier_trips_the_real_sets(monkeypatch):
    cat = tasksets.load_catalog()
    monkeypatch.setattr(tasksets, "load_catalog",
                        lambda path=None: {**cat, "verifier_version": "d1-verify-v0"})
    saved = tasksets.load("d1-real-dev")
    problems = tasksets._check_real({**saved, "tasks": saved["tasks"][:1]})
    assert any("verifier_version" in p and "real_tasks.py" in p for p in problems)


# ------------------------------------------------------------ the harder sets (2026-11-03)


def test_d1_test_hard_is_whole_sheet_jobs_on_its_own_seeds():
    hard = tasksets.load("d1-test-hard")["tasks"]
    assert len(hard) == 100 and [t["seed"] for t in hard] == list(tasksets.HARD_SEEDS)
    others = {t["task_id"] for n in tasksets.SEEDED_NAMES for t in tasksets.load(n)["tasks"]}
    assert not {t["task_id"] for t in hard} & others
    types = Counter(t["task_type"] for t in hard)
    assert set(types) == set(tasksets.HARD_SEEDED_TYPES) and max(types.values()) - min(types.values()) <= 2
    assert {t["curves"] for t in hard} == {3, 4, 5} and {t["sheets"] for t in hard} == {2, 3}
    # one task in five carries a station equation (hard_equation), spread over the
    # types and the other dials; the dialed type where a seed fell back to the next
    assert [t["equations"] for t in hard] == [tasksets.hard_equation(i) for i in range(100)]
    eq = [t for t in hard if t["equations"]]
    assert len(eq) == 20
    dialed = Counter(t.get("dialed", {}).get("task_type", t["task_type"]) for t in eq)
    assert dialed == {ttype: 4 for ttype in tasksets.HARD_SEEDED_TYPES}
    assert sorted(Counter(t["curves"] for t in eq).values()) == [6, 7, 7]
    # the hard types stay out of the seeded sets' type cycle, so their ids do not move
    from roaddraft.tasks.types import HARD_TASK_TYPES
    assert not set(HARD_TASK_TYPES) & set(tasksets.SEEDED_TYPES)


def test_hard_dials_cycle():
    d = [tasksets.hard_dials(i) for i in range(12)]
    assert [x["curves"] for x in d] == [3, 4, 5] * 4
    assert [x["sheets"] for x in d] == [2] * 3 + [3] * 3 + [2] * 3 + [3] * 3
    assert [x["task_type"] for x in d[:5]] == list(tasksets.HARD_SEEDED_TYPES)
    assert [x["equations"] for x in d] == [i in (0, 7) for i in range(12)]
    on = [i for i in range(100) if tasksets.hard_equation(i)]
    assert on == [5 * b + (2 * b) % 5 for b in range(20)]
    assert sorted(Counter(tasksets.hard_dials(i)["sheets"] for i in on).values()) == [9, 11]


@pytest.mark.parametrize("ttype", ["plan-sheet-pavement", "create-plan-sheet", "base-plan-sheet"])
def test_a_hard_seeded_task_verifies_100_and_its_start_0(ttype):
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify import verify
    task = generate_task(2003, curves=3, equations=True, task_type=ttype, sheets=3)
    start = session_for_task(task)
    done = session_for_task(task)
    reference_solution(task, done)
    for level in ("explicit", "vague"):
        assert verify(start.doc, task.truth, prompt_level=level).effective_score == 0.0
        assert verify(done.doc, task.truth, prompt_level=level).effective_score == 100.0
    # three sheets: the prompt names both breaks, and the title block all three numbers
    stations = sorted({m["station_text"] for sh in task.brief.deliverable["sheets"]
                       for m in sh["matches"]})
    assert len(stations) == 2
    for level in ("explicit", "vague"):
        text = task.brief.prompts[level]
        assert all(s in text for s in stations), (level, text)
    assert "C-101, C-102 and C-103 of 3" in task.brief.prompts["explicit"]


def test_d1_real_hard_holds_every_whole_job_and_none_of_d1_real():
    hard = tasksets.load("d1-real-hard")
    real = {t["task_id"] for n in tasksets.REAL_NAMES for t in tasksets.load(n)["tasks"]}
    ids = [t["task_id"] for t in hard["tasks"]]
    assert len(ids) == tasksets.REAL_HARD_SIZE == len(set(ids)) and not set(ids) & real
    dev = set(tasksets.real_dev_sheets(tasksets.load_catalog()["tasks"]))
    assert not {t["sheet_id"] for t in hard["tasks"]} & dev
    jobs = {t["task_id"] for t in tasksets.load_catalog(tasksets.JOB_CATALOG)["tasks"]
            if t["sheet_id"] not in dev}
    assert {t["task_id"] for t in hard["tasks"] if t["group"] == "job"} == jobs
    fill = Counter(t["task_type"] for t in hard["tasks"] if t["group"] != "job")
    assert set(fill) == set(tasksets.REAL_HARD_FILL) and max(fill.values()) - min(fill.values()) <= 1
    assert sum(hard["groups"].values()) == len(ids)


def test_d1_real_draws_no_whole_job():
    from roaddraft.tasks.types import REAL_JOB_TYPES
    assert not set(REAL_JOB_TYPES) & set(tasksets.real_quotas())
    assert not {t["task_type"] for t in tasksets.load("d1-real")["tasks"]} & set(REAL_JOB_TYPES)


# ------------------------------------------------------------ the training sets (2026-11-10)


def test_the_training_sets_share_nothing_with_any_eval_set():
    """The tripwire the training plan rests on: no task id and no seed of a
    training set is in a set a model is ever scored on, dev sets included."""
    assert tasksets.train_overlap() == []
    assert not set(tasksets.TRAIN_NAMES) & set(tasksets.NAMES)
    assert tasksets.TRAIN_NAMES == ("d1-train", "d1-train-hard", "d1-train-twist",
                                    "d1-train-crowd", "d1-train-revise",
                                    "d1-train-twist-widths", "d1-train-revise-base")
    train, hard, *_rest = (tasksets.load(n) for n in tasksets.TRAIN_NAMES)
    assert [t["seed"] for t in train["tasks"]] == list(tasksets.TRAIN_SEEDS)
    kept = [s for s in tasksets.TRAIN_HARD_SEEDS if s not in hard["skipped_seeds"]]
    assert [t["seed"] for t in hard["tasks"]] == kept and len(kept) >= 0.9 * len(tasksets.TRAIN_HARD_SEEDS)
    assert {t["task_type"] for t in train["tasks"]} == set(tasksets.SEEDED_TYPES)
    assert {t["task_type"] for t in hard["tasks"]} == set(tasksets.HARD_SEEDED_TYPES)
    eval_seeds = {t["seed"] for n in tasksets.NAMES for t in tasksets.load(n)["tasks"] if "seed" in t}
    assert not eval_seeds & (set(tasksets.TRAIN_SEEDS) | set(tasksets.TRAIN_HARD_SEEDS)
                             | set(tasksets.TRAIN_TWIST_SEEDS) | set(tasksets.TRAIN_CROWD_SEEDS)
                             | set(tasksets.TRAIN_REVISE_SEEDS)
                             | set(tasksets.TRAIN_TWIST_WIDTH_SEEDS))
    assert not eval_seeds & set(tasksets.TRAIN_REVISE_BASE_SEEDS)


def test_the_twisted_training_set_is_every_seed_twisted_over_the_types_a_twist_changes():
    """``d1-train-twist`` (2026-11-11): seeds of its own, every entry marked
    twisted and no entry of any other set, each type at every curve count."""
    from collections import Counter
    twisted = tasksets.load("d1-train-twist")["tasks"]
    assert [t["seed"] for t in twisted] == list(tasksets.TRAIN_TWIST_SEEDS)
    assert all(t["twist"] is True for t in twisted)
    for name in tasksets.NAMES + ("d1-train", "d1-train-hard"):
        assert not any("twist" in t for t in tasksets.load(name)["tasks"]), name
    assert {t["task_type"] for t in twisted} == set(tasksets.TWIST_TYPES)
    assert tasksets.TWIST_TYPES == ("annotate-base", "annotate-sheet", "bearings",
                                    "curve-callouts", "curve-table", "plan-sheet",
                                    "sheet-setup", "stationing", "title-block")
    per_type = Counter(t["task_type"] for t in twisted)
    assert max(per_type.values()) - min(per_type.values()) <= 1
    # nine types and three curve counts: the count steps on a turn of the types, so a
    # type is not stuck with one
    for ttype in tasksets.TWIST_TYPES:
        curves = Counter(t["curves"] for t in twisted if t["task_type"] == ttype)
        assert set(curves) == {1, 2, 3} and max(curves.values()) - min(curves.values()) <= 1
    assert [tasksets.twist_dials(i)["curves"] for i in (0, 9, 18)] == [1, 2, 3]
    # the entry rebuilds twisted, and plain when the key is taken off
    entry = twisted[0]
    task = tasksets.task_from_entry(entry)
    assert task.brief.deliverable["view_rotation"]
    plain = {k: v for k, v in entry.items() if k != "twist"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_the_twisted_width_set_is_the_width_types_through_a_turned_view_on_seeds_of_its_own():
    """``d1-train-twist-widths`` (2026-11-13, plan decision 9): the three types that
    dimension the pavement width, every one twisted, on seeds no other set draws; and
    ``d1-train-twist`` keeps the nine types and the ids it was drawn with."""
    from collections import Counter
    manifest = tasksets.load("d1-train-twist-widths")
    tasks, skipped = manifest["tasks"], manifest["skipped_seeds"]
    assert sorted([t["seed"] for t in tasks] + skipped) == list(tasksets.TRAIN_TWIST_WIDTH_SEEDS)
    assert tasksets.TRAIN_TWIST_WIDTH_SEEDS == range(16000, 16300) and len(skipped) <= 10
    assert all(t["twist"] is True for t in tasks)
    assert tasksets.TWIST_WIDTH_TYPES == ("pavement", "pavement-widths", "plan-sheet-pavement")
    assert not set(tasksets.TWIST_WIDTH_TYPES) & set(tasksets.TWIST_TYPES)
    per_type = Counter(t["task_type"] for t in tasks)
    assert set(per_type) == set(tasksets.TWIST_WIDTH_TYPES)
    assert max(per_type.values()) - min(per_type.values()) <= 3
    # the two types handed a sheet on d1-test's dials, the whole plan on d1-test-hard's
    for ttype in ("pavement", "pavement-widths"):
        mine = [t for t in tasks if t["task_type"] == ttype]
        assert {t["curves"] for t in mine} == {1, 2, 3} and {t["sheets"] for t in mine} == {1, 2}
        assert {t["equations"] for t in mine} == {True, False}
    whole = [t for t in tasks if t["task_type"] == "plan-sheet-pavement"]
    assert {t["curves"] for t in whole} == {3, 4, 5} and {t["sheets"] for t in whole} == {2, 3}
    assert [tasksets.twist_width_dials(i)["task_type"] for i in range(3)] == list(
        tasksets.TWIST_WIDTH_TYPES)
    assert [tasksets.twist_width_dials(3 * k)["curves"] for k in range(3)] == [1, 2, 3]
    assert [tasksets.twist_width_dials(3 * k + 2)["curves"] for k in range(3)] == [3, 4, 5]
    # a dialed entry says what its dials were
    assert all(t["dialed"]["sheets"] != t["sheets"] for t in tasks if "dialed" in t)
    # the entry rebuilds twisted, with width dimensions that carry the turn
    entry = next(t for t in tasks if t["task_type"] == "pavement-widths")
    task = tasksets.task_from_entry(entry)
    assert task.brief.deliverable["view_rotation"] and task.brief.deliverable["width_dimensions"]
    plain = {k: v for k, v in entry.items() if k != "twist"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_the_crowded_training_set_is_every_seed_crowded_over_the_types_that_letter_a_set_up_sheet():
    """``d1-train-crowd`` (2026-11-12): seeds of its own, every entry marked
    crowded and no entry of any other set, one sheet each, half of them
    through a turned viewport, each type at every curve count."""
    from collections import Counter
    from roaddraft.tasks.crowd import CROWD_TYPES
    manifest = tasksets.load("d1-train-crowd")
    crowded = manifest["tasks"]
    kept = [s for s in tasksets.TRAIN_CROWD_SEEDS if s not in manifest["skipped_seeds"]]
    assert [t["seed"] for t in crowded] == kept and len(kept) >= 0.95 * len(tasksets.TRAIN_CROWD_SEEDS)
    assert all(t["crowd"] is True and t["sheets"] == 1 for t in crowded)
    for name in tasksets.NAMES + ("d1-train", "d1-train-hard", "d1-train-twist",
                                  "d1-train-revise"):
        assert not any("crowd" in t for t in tasksets.load(name)["tasks"]), name
    assert {t["task_type"] for t in crowded} == set(CROWD_TYPES)
    assert CROWD_TYPES == ("annotate-base", "annotate-sheet", "bearings", "curve-callouts",
                           "stationing")
    turned = sum(1 for t in crowded if t.get("twist"))
    assert abs(turned - len(crowded) / 2) <= 5
    for ttype in CROWD_TYPES:
        assert {t["curves"] for t in crowded if t["task_type"] == ttype} == {1, 2, 3}
    assert [tasksets.crowd_dials(i)["task_type"] for i in range(5)] == list(CROWD_TYPES)
    # a seed whose sheet cannot be crowded for its type took the next type, and says so
    dialed = [t for t in crowded if "dialed" in t]
    assert all(t["dialed"]["task_type"] != t["task_type"] for t in dialed)
    assert len(dialed) < 0.1 * len(crowded)
    # the entry rebuilds crowded, and plain when the key is taken off
    entry = crowded[0]
    task = tasksets.task_from_entry(entry)
    assert task.brief.deliverable["crowd"]["alignment"]["name"] == "ALIGN-2"
    plain = {k: v for k, v in entry.items() if k != "crowd"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_the_revised_training_set_meets_every_kind_with_every_type_count_and_twist():
    """``d1-train-revise`` (2026-11-12): seeds of its own, every entry marked with
    its kind of change and no entry of any other set, one sheet and no equation,
    every kind of change on both types at every curve count and both ways
    round."""
    from collections import Counter
    from roaddraft.tasks.revise import KINDS, REVISE_TYPES
    manifest = tasksets.load("d1-train-revise")
    revised = manifest["tasks"]
    kept = [s for s in tasksets.TRAIN_REVISE_SEEDS if s not in manifest["skipped_seeds"]]
    assert [t["seed"] for t in revised] == kept and len(kept) >= 0.95 * len(tasksets.TRAIN_REVISE_SEEDS)
    assert all(t["revise"] in KINDS and t["sheets"] == 1 and not t["equations"] for t in revised)
    for name in tasksets.NAMES + ("d1-train", "d1-train-hard", "d1-train-twist", "d1-train-crowd"):
        assert not any("revise" in t for t in tasksets.load(name)["tasks"]), name
    per_type = Counter(t["task_type"] for t in revised)
    assert set(per_type) == set(REVISE_TYPES) and min(per_type.values()) >= 0.95 * 300
    combos = Counter((t["revise"], t["task_type"], t["curves"], bool(t.get("twist")))
                     for t in revised)
    assert len(combos) == 3 * 2 * 3 * 2  # every kind, type, curve count and twist
    # a kind the seed's line cannot take took the next one, and says so
    dialed = [t for t in revised if "dialed" in t]
    assert all(t["dialed"]["revise"] != t["revise"] for t in dialed)
    assert len(dialed) < 0.1 * len(revised)
    assert [tasksets.revise_dials(i)["revise"] for i in range(3)] == list(KINDS)
    # the entry rebuilds revised, and plain when the key is taken off
    entry = revised[0]
    task = tasksets.task_from_entry(entry)
    assert task.brief.deliverable["revision"]["kind"] == entry["revise"]
    plain = {k: v for k, v in entry.items() if k != "revise"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_the_base_drawing_revision_set_meets_every_kind_with_every_curve_count_and_twist():
    """``d1-train-revise-base`` (2026-11-13): seeds of its own, every entry a
    change left for the drafter to make in the base drawing (``BASE_KINDS``),
    ``annotate-base`` on one sheet with no equation, every kind at every curve
    count both ways round; no entry of any other set is one."""
    from collections import Counter
    from roaddraft.eval.tools import BASE_SCOPE, REVISION_SCOPE
    from roaddraft.tasks.revise import BASE_KINDS, KINDS
    assert tasksets.TRAIN_REVISE_BASE_SEEDS == range(18000, 18300)
    manifest = tasksets.load("d1-train-revise-base")
    based = manifest["tasks"]
    kept = [s for s in tasksets.TRAIN_REVISE_BASE_SEEDS if s not in manifest["skipped_seeds"]]
    assert [t["seed"] for t in based] == kept and len(kept) >= 0.95 * len(tasksets.TRAIN_REVISE_BASE_SEEDS)
    assert all(t["revise"] in BASE_KINDS and t["task_type"] == "annotate-base"
               and t["sheets"] == 1 and not t["equations"] for t in based)
    for name in tasksets.NAMES + tuple(n for n in tasksets.TRAIN_NAMES
                                       if n != "d1-train-revise-base"):
        assert not any(t.get("revise") in BASE_KINDS for t in tasksets.load(name)["tasks"]), name
    combos = Counter((t["revise"], t["curves"], bool(t.get("twist"))) for t in based)
    assert len(combos) == 3 * 3 * 2  # every kind, curve count and twist
    turned = sum(1 for t in based if t.get("twist"))
    assert abs(turned - len(based) / 2) <= 5
    # a kind the seed's line cannot take took the next one, and says so
    dialed = [t for t in based if "dialed" in t]
    assert all(t["dialed"]["revise"] != t["revise"] for t in dialed)
    assert len(dialed) < 0.1 * len(based)
    assert [tasksets.revise_base_dials(i)["revise"] for i in range(3)] == list(BASE_KINDS)
    assert [tasksets.revise_base_dials(i)["curves"] for i in (0, 3, 6)] == [1, 2, 3]
    assert [tasksets.revise_base_dials(i)["twist"] for i in (0, 9, 18)] == [False, True, False]
    # the entry rebuilds as the change left to the drafter, the base drawing still old; with
    # the plain kind it is the designer's change, another task
    entry = based[0]
    task = tasksets.task_from_entry(entry)
    R = task.brief.deliverable["revision"]
    assert R["by_drafter"] and R["alignment"] == "BASE:ALIGN-1" and R["kind"] in KINDS
    assert task.truth.scope[-2:] == [REVISION_SCOPE, BASE_SCOPE]
    designers = dict(entry, revise=R["kind"])
    assert tasksets.task_from_entry(designers, strict=False).task_id != entry["task_id"]
    plain = {k: v for k, v in entry.items() if k != "revise"}
    assert tasksets.task_from_entry(plain, strict=False).task_id != entry["task_id"]


def test_shared_reports_an_id_a_seed_and_a_task_that_is_not_seeded():
    test = tasksets.load("d1-test")
    stolen = {"taskset": "d1-train", "tasks": [dict(test["tasks"][3])]}
    problems = tasksets.shared(stolen, test)
    assert any("task id" in p for p in problems) and any("seed" in p for p in problems)
    # the same seed under another type is the same design: still shared
    retyped = {"taskset": "d1-train", "tasks": [{**test["tasks"][3], "task_id": "D1-001003-other"}]}
    assert [p for p in tasksets.shared(retyped, test) if "seed" in p]
    real = {"taskset": "d1-train", "tasks": [dict(tasksets.load("d1-real")["tasks"][0])]}
    assert any("not a seeded task" in p for p in tasksets.shared(real, test))
    assert tasksets.shared({"taskset": "d1-train", "tasks": []}, test) == []


def test_the_training_manifests_are_on_the_current_spec_and_rebuild_to_their_ids():
    """A sample, not the whole set (2,100 tasks take three minutes to rebuild):
    ``python -m roaddraft.eval taskset d1-train d1-train-hard d1-train-twist
    d1-train-crowd d1-train-revise`` checks them all."""
    from roaddraft.tasks.brief import GENERATOR_VERSION
    from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
    for name in tasksets.TRAIN_NAMES:
        m = tasksets.load(name)
        assert m["generator_version"] == GENERATOR_VERSION, name
        assert m["spec_hash"] == spec_hash(DRAFTING_SPEC_V1), name
        for entry in m["tasks"][:6] + m["tasks"][-2:]:
            assert tasksets.task_from_entry(entry).task_id == entry["task_id"]
