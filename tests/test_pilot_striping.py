"""Pilot 13 (striping with no-passing zones): the probes build, the
sight-distance truth is what the docstring says, the scripted solutions pass
and the naive answers fail."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.probes import fixture
from roaddraft.probes.pilot import BY_ID
from roaddraft.probes.pilot import striping as st

IDS = ["p13-striping-wfl15", "p13-striping-wfl16"]


def _checked(tmp_path, job, **solve):
    start = fixture.start_document(tmp_path / job.start, job.start)
    baseline = Session.load(start, out_dir=start.parent)
    session = Session.load(start, out_dir=start.parent)
    st.solve_job(job, session, **solve)
    assert session.query("save_document", {"path": str(start)})["ok"]
    return BY_ID[job.id].check(baseline, Session.load(start, out_dir=start.parent))


def test_probes_build():
    assert [p.id for p in st.PROBES] == IDS
    for p in st.PROBES:
        assert p.prompt and p.note and p.solve and p.start in fixture.START
        assert "Table 3B-1" in p.prompt and "mph" in p.prompt


def test_truth():
    """MUTCD PSD 900 ft at 55 mph and 800 ft at 50 mph over the 123+50 crest:
    one zone per sheet, each for one direction only."""
    assert st.truth(st.D6) == (((11660.0, 12129.0),), ())
    assert st.truth(st.D7) == ((), ((12575.0, 12921.0),))


def test_starts_carry_the_profile_and_fail(tmp_path):
    for job in st.JOBS:
        start = fixture.start_document(tmp_path / job.start, job.start)
        s = Session.load(start, out_dir=start.parent)
        rows = s.query("get_design_data", {"kind": "pvis", "profile": job.profile})["rows"]
        assert [(r["station"], r["elevation"]) for r in rows] == [p[:2] for p in job.pvis]
        assert not BY_ID[job.id].check(s, s).passed


def test_solutions_pass(tmp_path):
    for job in st.JOBS:
        result = _checked(tmp_path / "ok", job)
        assert result.passed, result.detail


def test_double_yellow_over_the_crest_fails(tmp_path):
    """The naive answer: no-passing both ways from PVC to PVT."""
    for job in st.JOBS:
        crest = [(max(12150.0, job.ra), min(12550.0, job.rb))]
        crest = [c for c in crest if c[1] > c[0]]
        result = _checked(tmp_path / "pvc", job, up=crest, down=crest)
        assert not result.passed


def test_solid_on_the_wrong_side_fails(tmp_path):
    result = _checked(tmp_path / "swap", st.D7, swap=True)
    items = dict(result.items)
    assert not items["no-passing zone, up-station traffic"]
    assert not items["no-passing zone, down-station traffic"]


def test_stopping_sight_distance_heights_fail(tmp_path):
    rows = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in st.D6.pvis]
    up, down = st.zones(rows, st.D6.psd, st.D6.ra, st.D6.rb, obj=2.0)
    assert up and abs(up[0][0] - 11660.0) > st.ZONE_TOL
    result = _checked(tmp_path / "ssd", st.D6, up=up, down=down)
    assert not dict(result.items)["no-passing zone, up-station traffic"]
