"""Pilot 11 (redlines): the probes build, the scripted solutions pass while the
untouched starts fail, and the naive answers named in the module docstring fail."""
from __future__ import annotations

import dataclasses
import re
import shutil

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, redlines

#: the expansion of 2026-11-03 (redlines.MORE)
NEW_IDS = ["p11-radius-ppm048", "p11-radius-ppm230", "p11-radius-wfl07", "p11-radius-ppm158",
           "p11-pi-ppm161", "p11-pi-ppm154", "p11-station-fdot916", "p11-station-ppm046",
           "p11-station-ppm050", "p11-station-ppm111"]
IDS = ["p11-radius-ppm160", "p11-station-ppm045"] + NEW_IDS
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


# ------------------------------------------------------------------ the expansion


def _inst(pid):
    return next(i for i in redlines.INSTANCES if i.id == pid)


def _attempt_with(tmp_path, inst, after=None, check_inst=None, **skip):
    """The scripted solution of ``inst`` (a variant, for a wrong answer), then
    ``after(session)``, scored by ``check_inst``'s probe against a fresh start."""
    check_inst = check_inst or inst
    start = tmp_path / "start"
    doc = fixture.start_document(start, check_inst.id)
    work = tmp_path / "work"
    shutil.copytree(start, work)
    mine = work / doc.name
    session = Session.load(mine, out_dir=work)
    redlines.make_solve(inst, **skip)(session)
    if after is not None:
        after(session)
    common.save(session, mine)
    return BY_ID[check_inst.id].check(Session.load(doc, out_dir=start), Session.load(mine, out_dir=work))


def test_new_instances_spread():
    new = [_inst(i) for i in NEW_IDS]
    assert {i.agency for i in new} >= {"caltrans", "wfl", "fdot"}
    assert {i.kind for i in new} == {"radius", "station", "pi"}
    sheets = [i.sheet_id for i in new]
    assert len(set(sheets)) == len(sheets)
    assert not set(sheets) & {"PPM-160", "PPM-045"}
    # the radius taken up and down, shifts forward and back, PIs ahead and back
    radius = [(i.value, redlines._original(i).curves()[i.curve - 1].radius) for i in new
              if i.kind == "radius"]
    assert any(v > r for v, r in radius) and any(v < r for v, r in radius)
    assert any(i.value > 0 for i in new if i.kind == "station")
    assert any(i.value < 0 for i in new if i.kind == "station")
    assert {i.value > 0 for i in new if i.kind == "pi"} == {True, False}


@pytest.mark.parametrize("pid", NEW_IDS)
def test_prompt_names_no_answer(pid):
    # the task text names the sheet, the line and the base file, never a value to work out
    probe, inst = BY_ID[pid], _inst(pid)
    assert inst.sheet in probe.prompt and inst.design_file in probe.prompt
    assert not re.search(r"\d+\+\d{2}", probe.prompt)
    assert "R = " not in probe.prompt and str(int(abs(inst.value))) not in probe.prompt


@pytest.mark.parametrize("pid", ["p11-radius-ppm048", "p11-station-fdot916", "p11-station-ppm046",
                                 "p11-station-ppm050", "p11-station-ppm111"])
def test_new_callouts_left_fail(tmp_path, pid):
    # everything else done, the callouts citing the line's stations left as they were
    inst = _inst(pid)
    r = _attempt(tmp_path, inst, callouts=False)
    assert not r.passed
    failed = [k for k, done in r.items if not done]
    assert failed and all(k.startswith("the callout") for k in failed), failed


@pytest.mark.parametrize("pid,line", [("p11-station-ppm046", '"IN4" 661+66.77'),
                                      ("p11-station-ppm050", '"F2" 705+19.93')])
def test_every_station_in_a_tie_shifted_fails(tmp_path, pid, line):
    # a find-and-replace drafter: the other line's station in the tie shifted too
    inst = _inst(pid)
    name, station = line.split(" ")

    def shift_other(session):
        sheet = next(s for s in session.doc.sheets.values() if s.name == inst.sheet)
        for e in list(sheet.entities.values()):
            if getattr(e, "content", None) and line in redlines._norm(e.content).replace("’", "'"):
                whole, frac = station.split("+")
                ft = int(whole) * 100 + float(frac) + inst.value
                new = f"{int(ft // 100)}+{ft % 100:05.2f}"
                common.ok(session.execute("modify_entity", {"id": e.id, "changes": {
                    "content": e.content.replace(f"{name} {station}", f"{name} {new}")}}))
                return
        raise AssertionError(f"no tie citing {line}")

    r = _attempt_with(tmp_path, inst, after=shift_other)
    assert not r.passed and "callout" in r.detail


@pytest.mark.parametrize("pid", [i for i in NEW_IDS if "-station-" in i or "-pi-" in i])
def test_wrong_direction_fails(tmp_path, pid):
    # the shift, or the PI's move, taken the other way, and everything lettered from it
    inst = _inst(pid)
    try:
        r = _attempt_with(tmp_path, dataclasses.replace(inst, value=-inst.value), check_inst=inst)
    except RuntimeError as e:   # R1's PI moved ahead: the curve no longer fits before END
        assert "longer than" in str(e)
        return
    assert not r.passed and not r.items[0][1], r.items[0]


@pytest.mark.parametrize("pid", [i for i in NEW_IDS if "-radius-" in i or "-pi-" in i])
@pytest.mark.parametrize("phases", [("stationing",), ("table",)], ids=["stationing", "table"])
def test_only_the_obvious_lettering_fails(tmp_path, pid, phases):
    # the design revised, but only the stations (or only the curve table) lettered again:
    # the bearings carry the tangent lengths, the table R/T/L, the change moves them all
    inst = _inst(pid)
    if "table" in phases and "D1-06" not in inst.graded:
        pytest.skip("no curve table on the sheet")
    r = _attempt(tmp_path, inst, phases=phases, callouts=False)
    assert not r.passed and r.items[0][1]


def test_plus_callout_relettered_is_allowed(tmp_path):
    # L-2 letters its MBGR ends as bare D13 pluses ('+46 BEGIN MBGR'): moving the plus
    # with the restation is not held against the drafter, changing the note is
    inst = _inst("p11-station-ppm046")

    def reletter(content):
        def edit(session):
            sheet = next(s for s in session.doc.sheets.values() if s.name == inst.sheet)
            e = next(e for e in sheet.entities.values()
                     if getattr(e, "content", "") == "+46 BEGIN MBGR")
            common.ok(session.execute("modify_entity", {"id": e.id, "changes": {"content": content}}))
        return edit

    ok = _attempt_with(tmp_path / "a", inst, after=reletter("+84 BEGIN MBGR"))
    assert ok.passed, ok.detail
    bad = _attempt_with(tmp_path / "b", inst, after=reletter("+46 END MBGR"))
    assert not bad.passed and "unrelated" in [k for k, d in bad.items if not d][0]


def test_wfl_revision_note(tmp_path):
    # an FLH border has no revision block: the revision goes in a note on the sheet
    inst = _inst("p11-radius-wfl07")
    assert "revision note" in BY_ID[inst.id].prompt
    assert "revision" in _attempt(tmp_path / "a", inst, revision=False).detail

    def note_quoting_the_redline(session):
        common.ok(session.execute("place_text", {
            "space": inst.sheet, "position": [11.6, 7.0], "height": 0.1,
            "content": f"REV 1: {inst.note[0]}, R = 600' -- RD 10-19-26"}))

    r = _attempt_with(tmp_path / "b", inst, after=note_quoting_the_redline, revision=False)
    assert r.passed, r.detail


def test_end_tie_follows_the_radius(tmp_path):
    # L-4: R 250' on IN4 lengthens the line 17.50 ft, so its tie to IND1 reads
    # "IN4" 683+57.63 while "IND1" 59+72.49 stays
    inst = _inst("p11-radius-ppm048")

    def tie(session):
        sheet = next(s for s in session.doc.sheets.values() if s.name == inst.sheet)
        return next(e.content for e in sheet.entities.values()
                    if '"IND1" 59+72.49' in (getattr(e, "content", "") or ""))

    seen = {}
    _attempt_with(tmp_path, inst, after=lambda s: seen.setdefault("tie", tie(s)))
    assert '"IN4" 683+57.63 POT' in seen["tie"]


def test_angle_point_dropped_fails(tmp_path, monkeypatch):
    # E-18's "D" turns 0.26° 30 ft from BEGIN; key_points lists only the curve's PI, so a
    # line re-made from BEGIN, that PI and END loses the angle point
    inst = _inst("p11-radius-ppm230")
    redlines._intended(inst.id)   # the check's own revision, made before the patch

    def drop_angle_point(i, base):
        pts = common.ok(base.query("key_points", {"alignment": i.alignment}))["points"]
        pis = [redlines._key(pts, "begin"), redlines._key(pts, "pi") + [i.value],
               redlines._key(pts, "end")]
        common.ok(base.execute("modify_alignment", {"name": i.alignment, "changes": {"pis": pis},
                                                    "redraw": True}))

    monkeypatch.setattr(redlines, "apply_revision", drop_angle_point)
    r = _attempt(tmp_path, inst)
    assert not r.passed and "angle point" in r.items[0][0] + str(r.detail), r.items[0]
