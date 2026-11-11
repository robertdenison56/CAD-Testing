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


# ------------------------------------------------------- the vague level (2026-11-08)

import re

from roaddraft.mcp.server import tool_definitions
from roaddraft.probes.pilot.profile import short_station


def _both(tmp_path, job, patch=None, monkeypatch=None, **solve):
    """``(explicit, vague)`` results of the scripted striping, solved with the module
    constants in ``patch`` (a drafting convention done another way) and graded with them
    restored."""
    start = fixture.start_document(tmp_path / job.start, job.start)
    baseline = Session.load(start, out_dir=start.parent)
    session = Session.load(start, out_dir=start.parent)
    with monkeypatch.context() as m:
        for name, value in (patch or {}).items():
            m.setattr(st, name, value)
        st.solve_job(job, session, **solve)
    assert session.query("save_document", {"path": str(start)})["ok"]
    probe = BY_ID[job.id]
    got = lambda: Session.load(start, out_dir=start.parent)
    return probe.check(baseline, got()), probe.vague_check(baseline, got())


def test_vague_briefs():
    tools = [t["name"] for t in tool_definitions(Session())]
    for job, p in zip(st.JOBS, st.PROBES):
        v = p.vague
        assert v.strip() and v != p.prompt and len(v) < len(p.prompt), p.id
        assert p.vague_check is not None
        for name in tools:
            assert not re.search(rf"\b{re.escape(name)}\b", v, re.I), (p.id, name)
        # the job and its data, and how the work is read
        for kept in (job.alignment, short_station(job.ra), short_station(job.rb),
                     f"sheet {job.sheet}", "MUTCD", "model space", "two-lane", "12-ft lanes",
                     "edge lines", job.profile, f"85th-percentile speed of {job.mph} mph",
                     "horizontal sight lines are clear", "profile governs", job.extent,
                     "as a line along its center", "actual stripes", "not a linetype"):
            assert kept in v, (p.id, kept)
        # the marking pattern and the MUTCD's sections are the drafter's to know
        for dropped in ("10-ft", "30-ft", f"{st.PAIR}", "yellow", "White", "solid",
                        "Table 3B-1", "3B.02", "400 ft", "each direction"):
            assert dropped not in v, (p.id, dropped)


def test_vague_solutions_pass_and_starts_fail(tmp_path, monkeypatch):
    for job in st.JOBS:
        explicit, vague = _both(tmp_path / "ok", job, monkeypatch=monkeypatch)
        assert explicit.passed and vague.passed, (job.id, vague.detail)
        start = fixture.start_document(tmp_path / "start" / job.start, job.start)
        s = Session.load(start, out_dir=start.parent)
        assert not BY_ID[job.id].vague_check(s, s).passed


def test_vague_takes_the_pair_offsets_the_mutcd_allows(tmp_path, monkeypatch):
    """6-in lines 6 in apart: each stripe of a pair 0.5 ft off the centerline. The explicit
    brief says 0.33 ft; the MUTCD asks for a discernible space."""
    for job in (st.D6, st.D11):
        explicit, vague = _both(tmp_path / job.start, job, {"PAIR": 0.5}, monkeypatch)
        assert not explicit.passed
        assert not dict(explicit.items)["nothing in the wrong zone"]
        assert vague.passed, (job.id, vague.detail)


def test_vague_takes_broken_lines_in_the_mutcd_ratio(tmp_path, monkeypatch):
    """12-ft stripes with 36-ft gaps (the MUTCD's 10 and 30 "or a similar ratio")."""
    explicit, vague = _both(tmp_path, st.D7, {"DASH": 12.0, "GAP": 36.0}, monkeypatch)
    assert not dict(explicit.items)["broken centerline where passing is allowed"]
    assert vague.passed, vague.detail


def test_vague_takes_an_edge_line_off_the_lane_edge(tmp_path, monkeypatch):
    """A 6-in edge line with its inner edge on the 12-ft lane edge: its center at 12.25 ft."""
    _explicit, vague = _both(tmp_path, st.D6, {"EDGE": 12.25}, monkeypatch)
    assert vague.passed, vague.detail


def test_vague_still_fails_what_the_mutcd_does_not_allow(tmp_path, monkeypatch):
    # 10-ft stripes with 20-ft gaps: not the MUTCD's ratio
    _e, vague = _both(tmp_path / "ratio", st.D7, {"GAP": 20.0}, monkeypatch)
    assert not dict(vague.items)["broken centerline where passing is allowed"]
    # a pair 0.75 ft each side of the centerline: no longer a double line
    _e, vague = _both(tmp_path / "wide", st.D6, {"PAIR": 0.75}, monkeypatch)
    assert not vague.passed and not dict(vague.items)["no-passing zone, up-station traffic"]


def test_vague_naive_answers_still_fail(tmp_path, monkeypatch):
    """The zones are the MUTCD's own at both levels: double yellow over the crest, the solid on
    the wrong side and stopping-sight-distance heights fail the vague check too."""
    crest = [(12150.0, 12250.0)]
    _e, vague = _both(tmp_path / "pvc", st.D6, monkeypatch=monkeypatch, up=crest, down=crest)
    assert not vague.passed
    _e, vague = _both(tmp_path / "swap", st.D7, monkeypatch=monkeypatch, swap=True)
    assert not dict(vague.items)["no-passing zone, down-station traffic"]
    rows = [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in st.D6.pvis]
    up, down = st.zones(rows, st.D6.psd, st.D6.ra, st.D6.rb, obj=2.0)
    _e, vague = _both(tmp_path / "ssd", st.D6, monkeypatch=monkeypatch, up=up, down=down)
    assert not dict(vague.items)["no-passing zone, up-station traffic"]
    _e, vague = _both(tmp_path / "none", st.D10, monkeypatch=monkeypatch, up=[], down=[])
    assert not vague.passed
