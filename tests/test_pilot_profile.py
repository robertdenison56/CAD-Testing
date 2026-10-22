"""Pilot 6 (plan and profile on one sheet): the probes build, their scripted
solutions pass, and the naive answers fail."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.probes import fixture
from roaddraft.probes.pilot import BY_ID
from roaddraft.probes.pilot import profile as pp

IDS = ["p06-plan-profile-cflpnp", "p06-plan-profile-wfl14"]


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
    for p in pp.PROBES:
        assert p.prompt and p.note and p.solve and p.start in fixture.START
        assert "1\"=5'" in p.prompt and "lower-left corner" in p.prompt


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
