"""Pilot 11 (redlines): the probes build, the scripted solutions pass while the
untouched starts fail, and the naive answers named in the module docstring fail."""
from __future__ import annotations

import shutil

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, redlines

IDS = ["p11-radius-ppm160", "p11-station-ppm045"]
BY_ID = {p.id: p for p in redlines.PROBES}


def test_probes_build():
    assert [p.id for p in redlines.PROBES] == IDS
    for p in redlines.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "redline" in p.tags


@pytest.mark.parametrize("pid", IDS)
def test_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", probe.start)
    untouched = probe.check(Session.load(doc, out_dir=doc.parent), Session.load(doc, out_dir=doc.parent))
    assert not untouched.passed


def _attempt(tmp_path, inst, **skip):
    """The scripted solution with steps left out, scored against a fresh start."""
    start = tmp_path / "start"
    doc = fixture.start_document(start, inst.id)
    work = tmp_path / "work"
    shutil.copytree(start, work)
    mine = work / doc.name
    session = Session.load(mine, out_dir=work)
    redlines.make_solve(inst, **skip)(session)
    common.save(session, mine)
    return BY_ID[inst.id].check(Session.load(doc, out_dir=start), Session.load(mine, out_dir=work))


@pytest.mark.parametrize("inst", redlines.INSTANCES, ids=IDS)
def test_design_only_fails(tmp_path, inst):
    # the design revised in AA01 and nothing else: the lettering is stale
    r = _attempt(tmp_path, inst, letter=False, callouts=False)
    assert not r.passed
    design, done = r.items[0]
    assert done, design            # the design itself is right ...
    assert not all(d for _k, d in r.items[2:7])   # ... the alignment data is not


@pytest.mark.parametrize("inst", redlines.INSTANCES, ids=IDS)
def test_lettering_without_design_fails(tmp_path, inst):
    # the sheet re-lettered but AA01 left alone
    r = _attempt(tmp_path, inst, design=False)
    assert not r.passed
    assert not r.items[0][1], r.items[0]


@pytest.mark.parametrize("inst", redlines.INSTANCES, ids=IDS)
def test_old_lettering_left_fails(tmp_path, inst):
    # new lettering placed beside the old
    r = _attempt(tmp_path, inst, delete_old=False)
    assert not r.passed and "stale" in r.detail


def test_callouts_left_fails(tmp_path):
    # the station change with every label redone but the two callouts citing "TB1" untouched
    r = _attempt(tmp_path, redlines.STATION, callouts=False)
    assert not r.passed and "645+66.69" in r.detail


def test_redline_and_revision(tmp_path):
    assert "REDLINE" in _attempt(tmp_path / "a", redlines.RADIUS, redline=False).detail
    assert "revision" in _attempt(tmp_path / "b", redlines.RADIUS, revision=False).detail
