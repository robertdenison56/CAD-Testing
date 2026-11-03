"""Pilot 13 (striping with no-passing zones): the probes build, the
sight-distance truth is what the docstring says, the scripted solutions pass
and the naive answers fail."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.probes import fixture
from roaddraft.probes.pilot import BY_ID
from roaddraft.probes.pilot import striping as st

IDS = ["p13-striping-wfl15", "p13-striping-wfl16", "p13-striping-wfl17", "p13-striping-wfl19",
       "p13-striping-wfl20", "p13-striping-cflpnp"]


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


# ------------------------------------------------- the instances added Nov 2026


def test_new_truths():
    """D.8 carries the tail of the 123+50 crest's down-station zone at 65 mph; D.10
    climbs out of a sag toward the 158+60 bend; D.11 has a zone each way; the CFL
    crest restricts only the down-station traffic, past the crest."""
    assert st.truth(st.D8) == ((), ((13000.0, 13215.0),))
    assert st.truth(st.D10) == (((14937.0, 15250.0),), ())
    assert st.truth(st.D11) == (((15250.0, 15823.0),), ((15939.0, 16000.0),))
    assert st.truth(st.CFLPNP) == ((), ((1390.0, 1680.0),))
    # the extensions carry the last grade on unchanged
    g = lambda p, q: (q[1] - p[1]) / (q[0] - p[0])
    ext = st.MAIN01_PVIS_EXT
    assert abs(g(ext[-3], ext[-2]) - g(ext[-2], ext[-1])) < 1e-6
    cfl = st.CFL_PVIS_EXT
    assert abs(g(cfl[0], cfl[1]) - 0.005) < 1e-9 and abs(g(cfl[-2], cfl[-1]) + 0.005) < 1e-9


def test_new_prompts_say_what_the_profile_covers():
    for job in st.NEW_JOBS:
        prompt = BY_ID[job.id].prompt
        assert job.extent in prompt and str(job.mph) in prompt
    for job in (st.D6, st.D7):
        assert "behind the begin of project. Mark" in BY_ID[job.id].prompt


def test_no_zones_fails_where_the_crest_is_off_the_sheet(tmp_path):
    """The naive reading of D.8 (only a sag) and D.10 (a sag, the crest beyond
    the sheet): broken centerline throughout."""
    for job in (st.D8, st.D10):
        result = _checked(tmp_path / job.start, job, up=[], down=[])
        assert not result.passed


def test_new_naive_answers_fail(tmp_path):
    # D.10: a zone over the sag, PVC to PVT
    result = _checked(tmp_path / "sag", st.D10, up=[(14500.0, 15040.0)], down=[(14500.0, 15040.0)])
    assert not result.passed
    # D.11: double yellow from the PVC of the 158+60 bend to the range end
    bend = [(15560.0, 16000.0)]
    result = _checked(tmp_path / "bend", st.D11, up=bend, down=bend)
    assert not result.passed
    # D.11: one direction only
    result = _checked(tmp_path / "one", st.D11, down=[])
    assert not dict(result.items)["no-passing zone, down-station traffic"]
    # CFL: double yellow over the crest
    crest = [(1075.0, 1225.0)]
    result = _checked(tmp_path / "crest", st.CFLPNP, up=crest, down=crest)
    assert not result.passed
    # CFL: the zone on the wrong side
    result = _checked(tmp_path / "swap", st.CFLPNP, swap=True)
    assert not dict(result.items)["no-passing zone, down-station traffic"]


def test_new_stopping_sight_distance_heights_fail(tmp_path):
    for job in st.NEW_JOBS:
        rows = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in job.pvis]
        up, down = st.zones(rows, job.psd, job.ra, job.rb, obj=2.0)
        result = _checked(tmp_path / job.start, job, up=up, down=down)
        assert not result.passed, job.id
