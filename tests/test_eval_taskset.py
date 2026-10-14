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
    dev, test, var = (tasksets.load(n)["tasks"] for n in tasksets.NAMES)
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
