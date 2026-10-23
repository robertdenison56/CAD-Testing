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


def test_real_sets_draw_every_type_and_agency_from_the_catalogue():
    from roaddraft.tasks.types import REAL_TASK_TYPES
    catalogue = {t["task_id"]: t for t in tasksets.load_catalog()["tasks"]}
    real, dev = (tasksets.load(n)["tasks"] for n in tasksets.REAL_NAMES)
    assert len(real) == tasksets.REAL_PER_TYPE * len(REAL_TASK_TYPES) == 99
    assert len(dev) == tasksets.REAL_DEV_PER_TYPE * len(REAL_TASK_TYPES) == 22
    for rows, per in ((real, tasksets.REAL_PER_TYPE), (dev, tasksets.REAL_DEV_PER_TYPE)):
        assert Counter(t["task_type"] for t in rows) == {ty: per for ty in REAL_TASK_TYPES}
        assert len({t["task_id"] for t in rows}) == len(rows)
        for t in rows:
            c = catalogue[t["task_id"]]  # every task is a validated catalogue task
            assert (c["sheet_id"], c["alignment"], c["type"]) == (t["sheet_id"], t["alignment"],
                                                                   t["task_type"])
            assert t["sheets"] == 1 and t["task_id"].startswith("D1-")
    # the held-out set reaches every agency; the first eleven are one of each type
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
