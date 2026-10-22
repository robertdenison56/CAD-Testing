"""Pilot 12 (plan set): the combined base holds together, the probe builds, the
scripted set passes while the empty start fails, and the naive slips fail."""
from __future__ import annotations

import math
import shutil

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, plan_set

PROBE = plan_set.PROBES[0]


def test_probe_builds():
    assert [p.id for p in plan_set.PROBES] == ["p12-route65-d13"]
    assert PROBE.prompt.strip() and PROBE.note.strip() and PROBE.solve
    assert PROBE.start in fixture.START


def test_combined_centerline():
    # one "D13": L-1's tangent, the published R 5000' curve from L-2's BC
    d13 = plan_set.centerline()
    st = d13.stations()
    assert st.begin_text() == "638+95.91"
    curve = d13.curves()[0]
    assert abs(curve.radius - 5000.0) < 1e-6
    assert st.format(d13.begin_station + curve.start_dist) == "654+06.05"
    assert d13.begin_station <= plan_set.RANGE[0] and d13.end_station >= plan_set.RANGE[1]
    q = plan_set.quantities()
    assert math.isclose(q["SY"], 80.0 * 3200.0 / 9.0)
    assert 2000.0 < q["LF"] < 4000.0


def test_selftest(tmp_path):
    ref = reference.write(PROBE, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", PROBE.start)
    assert not PROBE.check(Session.load(doc, out_dir=doc.parent),
                           Session.load(doc, out_dir=doc.parent)).passed


def _attempt(tmp_path, **slip):
    start = tmp_path / "start"
    doc = fixture.start_document(start, PROBE.start)
    work = tmp_path / "work"
    shutil.copytree(start, work)
    mine = work / doc.name
    session = Session.load(mine, out_dir=work)
    plan_set.make_solve(**slip)(session)
    common.save(session, mine)
    return PROBE.check(Session.load(doc, out_dir=start), Session.load(mine, out_dir=work))


def test_index_typed_from_the_plan_fails(tmp_path):
    r = _attempt(tmp_path, index_from_plan=True)
    assert not r.passed and "index" in r.detail
    assert dict(r.items)["the index of sheets"] is False


def test_match_line_lettered_off_its_station_fails(tmp_path):
    r = _attempt(tmp_path, rounded_match=True)
    assert not r.passed and "match line" in r.detail


def test_fence_over_the_whole_layer_fails(tmp_path):
    r = _attempt(tmp_path, whole_fence=True)
    assert not r.passed and "fence" in r.detail
