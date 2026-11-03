"""Pilot 6 (plan and profile on one sheet): the probes build, their scripted
solutions pass, and the naive answers fail."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.probes import fixture
from roaddraft.probes.pilot import BY_ID
from roaddraft.probes.pilot import profile as pp

IDS = ["p06-plan-profile-cflpnp", "p06-plan-profile-wfl14", "p06-plan-profile-wfl18",
       "p06-plan-profile-wfl21", "p06-plan-profile-fdot915"]


def _checked(tmp_path, job, edit=None, **solve):
    start = fixture.start_document(tmp_path / job.start, job.start)
    baseline = Session.load(start, out_dir=start.parent)
    session = Session.load(start, out_dir=start.parent)
    if solve is not None:
        pp.solve_job(job, session, **solve)
    if edit:
        edit(session)
    assert session.query("save_document", {"path": str(start)})["ok"]
    return BY_ID[job.id].check(baseline, Session.load(start, out_dir=start.parent))


def test_probes_build():
    assert [p.id for p in pp.PROBES] == IDS
    v_scale = {job.id: job.v_scale for job in pp.JOBS + pp.NEW_JOBS}
    for p in pp.PROBES:
        assert p.prompt and p.note and p.solve and p.start in fixture.START
        # 1"=5' on all but D.12, which is drawn at the 1"=10' the WFL sheets print
        assert f"1\"={v_scale[p.id]:g}'" in p.prompt and "lower-left corner" in p.prompt


def test_starts_own_the_profile(tmp_path):
    for job in pp.JOBS:
        start = fixture.start_document(tmp_path / job.start, job.start)
        s = Session.load(start, out_dir=start.parent)
        rows = s.query("get_design_data", {"kind": "vcs", "profile": job.profile})["rows"]
        assert rows and all(r["K"] for r in rows if r["length"] > 0)
        assert not BY_ID[job.id].check(s, s).passed


def test_solutions_pass(tmp_path):
    for job in pp.JOBS:
        result = _checked(tmp_path / "ok", job)
        assert result.passed, result.detail
        assert len(result.items) >= 8


def test_grade_drawn_pvi_to_pvi_fails(tmp_path):
    """The naive grade line: straight from PVI to PVI, no vertical curves."""
    for job in pp.JOBS:
        result = _checked(tmp_path / "chord", job, curves=False)
        assert not result.passed
        assert dict(result.items)["profile grade line"] is False, result.detail


def test_ten_foot_vertical_scale_fails(tmp_path):
    result = _checked(tmp_path / "v10", pp.CFL, vertical=10.0)
    items = dict(result.items)
    assert not result.passed and not items["profile grade line"] and not items["profile grid"]


def test_a_high_point_where_there_is_none_fails(tmp_path):
    job = pp.WFL

    def liar(session):
        x, y = job.x(11100.0), job.y(6266.87)
        assert session.execute("place_text", {"space": job.sheet, "position": [x + 0.3, y - 1.0],
                                              "content": "HIGH PT 111+00.00", "height": 0.1})["ok"]

    result = _checked(tmp_path / "hp", job, edit=liar)
    assert not result.passed
    assert dict(result.items)["no high or low point where the profile has none"] is False


# ------------------------------------------------- the instances added Nov 2026

import pytest  # noqa: E402

NEW = {job.id: job for job in pp.NEW_JOBS}


def test_new_curves_are_what_the_notes_say():
    lows = [vc["high_low"] for vc in pp.WFL18.design().curves() if vc["high_low"]]
    assert len(lows) == 1 and lows[0]["kind"] == "low"
    assert lows[0]["station"] == pytest.approx(14416.62, abs=0.01)
    assert lows[0]["elevation"] == pytest.approx(6197.60, abs=0.01)
    # D.9 has no PVI on it; D.12 and FDOT have no high or low point on theirs
    assert not [vc for vc in pp.WFL18.design().curves()
                if pp.WFL18.s0 <= vc["pvi_station"] <= pp.WFL18.s1]
    for job in (pp.WFL21, pp.FDOT):
        assert not [vc for vc in job.design().curves() if vc["high_low"]
                    and job.s0 <= vc["high_low"]["station"] <= job.s1]
    sag = [vc for vc in pp.FDOT.design().curves() if vc["length"] > 0][0]
    assert sag["K"] == pytest.approx(115.3, abs=0.1)
    assert sag["high_low"]["station"] == pytest.approx(70718.83, abs=0.01)
    assert pp.WFL21.v_scale == 10.0 and "1\"=10' vertical" in BY_ID[pp.WFL21.id].prompt


@pytest.mark.parametrize("job", pp.NEW_JOBS, ids=list(NEW))
def test_new_starts_fail_and_solutions_pass(tmp_path, job):
    start = fixture.start_document(tmp_path / "start" / job.start, job.start)
    s = Session.load(start, out_dir=start.parent)
    rows = s.query("get_design_data", {"kind": "pvis", "profile": job.profile})["rows"]
    assert [(r["station"], r["elevation"]) for r in rows] == [p[:2] for p in job.pvis]
    assert not BY_ID[job.id].check(s, s).passed
    result = _checked(tmp_path / "ok", job)
    assert result.passed, result.detail
    assert len(result.items) >= 7


@pytest.mark.parametrize("job", pp.NEW_JOBS, ids=list(NEW))
def test_new_grade_drawn_pvi_to_pvi_fails(tmp_path, job):
    result = _checked(tmp_path / "chord", job, curves=False)
    assert dict(result.items)["profile grade line"] is False, result.detail


def test_d9_low_point_unlettered_fails(tmp_path):
    def drop(session):
        ids = [e.id for s in session.doc.sheets.values() for e in s.entities.values()
               if "LOW PT" in getattr(e, "content", "")]
        assert ids and session.execute("delete_entities", {"ids": ids})["ok"]

    result = _checked(tmp_path / "nolow", pp.WFL18, edit=drop)
    assert not result.passed
    assert dict(result.items)["low point 144+16.62"] is False


def test_d12_at_five_foot_vertical_fails(tmp_path):
    result = _checked(tmp_path / "v5", pp.WFL21, vertical=5.0)
    items = dict(result.items)
    assert not items["profile grid"] and not items["profile grade line"]


@pytest.mark.parametrize("job, station, label", [
    (pp.WFL21, 16410.0, "HIGH PT 164+10.00"), (pp.FDOT, 70718.83, "LOW PT 707+18.83")])
def test_a_point_that_is_not_on_the_sheet_fails(tmp_path, job, station, label):
    def liar(session):
        x, y = job.x(min(station, job.s1)), job.y(job.design().elevation_at(station))
        assert session.execute("place_text", {"space": job.sheet, "position": [x + 0.2, y - 1.0],
                                              "content": label, "height": 0.1})["ok"]

    result = _checked(tmp_path / "liar", job, edit=liar)
    assert not result.passed
    assert dict(result.items)["no high or low point where the profile has none"] is False
