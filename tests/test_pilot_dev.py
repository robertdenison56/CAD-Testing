"""``pilot-dev`` (probes/pilot_dev.py): the instances build, each scripted solution
passes and each naive answer its family is built to catch fails, at both prompt
levels; the sheets are the clean ones; and the held-out pilots do not move."""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from roaddraft.eval import probe_tasks as P
from roaddraft.eval import taskset as tasksets
from roaddraft.probes import fixture
from roaddraft.probes import pilot_dev as D
from roaddraft.probes.pilot import PILOT_PROBES, common, layout, redlines

IDS = [p.id for p in D.PROBES]
FAMILIES = ("p17", "p04", "p05", "p11")
PILOT_DIR = Path(layout.__file__).parent


def test_instances():
    assert len(IDS) == 19 and len(set(IDS)) == 19
    for p in D.PROBES:
        assert P.family(p) in FAMILIES and "-dev-" in p.id, p.id
        assert p.prompt.strip() and p.vague.strip() and p.vague != p.prompt and p.note.strip()
        assert p.solve and p.vague_check is not None and p.start in fixture.START
        assert "pilot-dev" in p.tags and D.NAIVE[p.id]
    # every clean sheet carries at least one instance, each family several sheets
    assert {D.sheet_of(i) for i in IDS} == set(D.SHEETS)
    for fam in FAMILIES:
        assert len({D.sheet_of(i) for i in IDS if i.startswith(fam)}) >= 2, fam


@pytest.mark.parametrize("pid", IDS)
def test_scripted_passes_and_naive_fails(tmp_path, pid):
    """The scripted solution passes at both levels, the untouched start fails, and
    every naive answer recorded for the instance fails at both levels on its item."""
    assert D.selftest(pid, tmp_path) == []


def test_tables_match_the_families_measures():
    # the 500-ft stations each lettering instance writes whole, and each stretch's fewest sheets
    for pid, cfg in list(D.P4.items()) + list(D.P17.items()):
        names = cfg["names"] if "names" in cfg else [cfg["name"]]
        assert cfg["whole"] == layout._whole(cfg["sheet_id"], names), pid
    assert {pid: layout._fewest(pid) for pid in D.P5} == D.FEWEST
    # strict like the expansion: only the fewest sheets pass
    assert all(cfg["spare"] == 0 for cfg in D.P5.values())


# ------------------------------------------------------------------ the sheets


def _manifest_ids():
    return {r["id"] for agency in common.AGENCIES for r in common.manifest(agency)}


def _strings(obj, seen=None):
    """Every string inside a pilot module's data (dicts, lists, dataclasses)."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k, seen)
            yield from _strings(v, seen)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            yield from _strings(v, seen)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _strings(getattr(obj, f.name), seen)


def held_out_pilot_sheets():
    """The redrafted sheets the held-out pilots use: every sheet id written in the
    pilot package's sources, or held in its modules' tables (the instances' configs;
    this module's own instances, which those tables also hold, are left out)."""
    import importlib
    ids = _manifest_ids()
    found = set()
    for path in PILOT_DIR.glob("*.py"):
        text = path.read_text()
        found |= {i for i in ids if re.search(r"[\"']" + re.escape(i) + r"[\"'-]", text)}
    mine = set(IDS)
    for name in ["common"] + list(importlib.import_module("roaddraft.probes.pilot").MODULES):
        module = importlib.import_module(f"roaddraft.probes.pilot.{name}")
        for attr, value in vars(module).items():
            if attr.startswith("__"):
                continue
            if isinstance(value, dict):
                value = {k: v for k, v in value.items() if k not in mine}
            found |= {s for s in _strings(value) if s in ids}
    return found


def test_no_pilot_dev_sheet_is_held_out():
    pilots = held_out_pilot_sheets()
    assert len(pilots) >= 40          # 42 by the plan's count (§8)
    real = {t["sheet_id"] for name in ("d1-real", "d1-real-hard", "d1-real-dev")
            for t in tasksets.load(name)["tasks"]}
    assert real and not set(D.SHEETS) & pilots and not set(D.SHEETS) & real
    # and the nine are every sheet with an alignment that is in none of them
    from roaddraft.tasks import real as R
    clean = {s.id for s in R.real_sheets()} - pilots - real
    assert clean == set(D.SHEETS)


def test_every_instance_builds_on_its_own_sheet(tmp_path):
    # a quick one per family: the start holds the sheet's own files
    for pid in ("p17-dev-ppm214", "p05-dev-wfl09", "p11-dev-ppm215", "p04-dev-wfl06"):
        doc = fixture.start_document(tmp_path / pid, D.BY_ID[pid].start)
        from roaddraft.tasks import real as R
        src = R.real_sheet(D.sheet_of(pid))
        names = {p.name for p in doc.parent.glob("*.rdraft")}
        assert names <= set(src.files), (pid, names)


# ------------------------------------------------------------------ the held-out set


def test_the_held_out_pilots_do_not_move():
    assert len(PILOT_PROBES) == 112 and len(P.pilots()) == 112
    assert not {p.id for p in PILOT_PROBES} & set(IDS)
    assert not {p.id for p in layout.PROBES} & set(IDS)
    assert not {i.id for i in redlines.INSTANCES} & set(IDS)
    assert not {p.id for p in redlines.PROBES} & set(IDS)
    # nothing of pilot-dev is in the package whose sources the held-out check hash reads
    assert Path(D.__file__).parent != PILOT_DIR
    assert Path(D.__file__) not in P.check_sources(P.PILOT_SET)
    assert Path(D.__file__) in P.check_sources(P.DEV_SET)
    assert tasksets.check(P.PILOT_SET) == []
    # a held-out instance still resolves to itself
    assert redlines._instance("p11-radius-ppm160") is redlines.RADIUS


# ------------------------------------------------------------------ the task set


def test_the_task_set():
    m = tasksets.load(D.TASK_SET)
    assert tasksets.check(D.TASK_SET) == []
    assert [r["probe"] for r in m["tasks"]] == [p.id for p in P.dev_probes()]
    assert sorted(r["probe"] for r in m["tasks"]) == sorted(IDS)
    for r in m["tasks"]:
        assert r["task_id"] != r["vague_task_id"] and r["vague_task_id"]
        assert r["sheet_id"] == D.sheet_of(r["probe"]) and not r["attachments"]
    # its own ids, generator and checks: none shared with hard-pilots
    hp = tasksets.load(P.PILOT_SET)
    ours = {r[k] for r in m["tasks"] for k in ("task_id", "vague_task_id")}
    theirs = {r[k] for r in hp["tasks"] for k in ("task_id", "vague_task_id") if r.get(k)}
    assert not ours & theirs
    assert m["generator_version"] == tasksets.current_generator(D.TASK_SET) != \
        hp["generator_version"]
    assert tasksets.current_verifier(D.TASK_SET) != tasksets.current_verifier(P.PILOT_SET)
    assert tasksets.is_probe(D.TASK_SET) and D.TASK_SET in tasksets.NAMES
    assert tasksets.default_budgets(D.TASK_SET) == P.BUDGETS
    # not on the board
    from roaddraft.eval.report import LEADERBOARD_SETS, set_ids
    assert D.TASK_SET not in LEADERBOARD_SETS
    assert set_ids(D.TASK_SET, ["vague"]) == {r["vague_task_id"] for r in m["tasks"]}


def test_an_entry_poses_its_probe_at_both_levels():
    (row,) = tasksets.entries(D.TASK_SET, task_ids=[P.task_id(D.BY_ID["p17-dev-ppm214"])])
    for level in ("explicit", "vague"):
        task = tasksets.task_from_entry(row, level=level)
        assert task.probe is D.BY_ID["p17-dev-ppm214"] and task.level == level
        assert task.brief == P.brief_text(task.probe, level)
    assert P.set_of(D.BY_ID["p17-dev-ppm214"]) == D.TASK_SET
    assert P.set_of(PILOT_PROBES[0]) == P.PILOT_SET


def test_a_grade_carries_its_sets_check_hash(tmp_path):
    probe = D.BY_ID["p05-dev-wfl09"]
    project = tmp_path / "project"
    fixture.start_document(project, probe.start)
    report = P.grade(probe, project)
    assert not report.passed
    assert report.to_dict()["verifier_version"] == tasksets.current_verifier(D.TASK_SET)


def test_the_training_sets_share_nothing_with_pilot_dev():
    dev = tasksets.load(D.TASK_SET)
    for name in tasksets.TRAIN_NAMES:
        assert tasksets.shared(tasksets.load(name), dev) == []
