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


# ------------------------------------------------------------------ the vague level

import dataclasses  # noqa: E402
import re  # noqa: E402

from roaddraft.probes import prompting  # noqa: E402

JOBS = {job.id: job for job in pp.JOBS + pp.NEW_JOBS}


def _tool_names():
    from roaddraft.mcp.server import tool_definitions
    return {t["name"] for t in tool_definitions(Session(), attachments=True)}


def _both(tmp_path, job, edit=None, layout=None, **solve):
    """The explicit and the vague verdicts on one scripted sheet (laid out for
    ``layout``, a Job with another datum, when given)."""
    start = fixture.start_document(tmp_path / job.start, job.start)
    baseline = Session.load(start, out_dir=start.parent)
    session = Session.load(start, out_dir=start.parent)
    pp.solve_job(layout or job, session, **solve)
    if edit:
        edit(session)
    assert session.query("save_document", {"path": str(start)})["ok"]
    submitted = Session.load(start, out_dir=start.parent)
    probe = BY_ID[job.id]
    return probe.check(baseline, submitted), probe.check_at("vague")(baseline, submitted)


@pytest.mark.parametrize("pid", IDS)
def test_vague_brief(pid):
    # the request in a sentence: the sheet, the line, its stations and the design
    # profile; no scale, grid datum, grid spacing, text height or list of what to letter
    probe, job = BY_ID[pid], JOBS[pid]
    vague = probe.vague
    assert vague.strip() and vague != probe.prompt and len(vague) < len(probe.prompt) / 3
    names = [n for n in _tool_names() if re.search(rf"\b{re.escape(n)}\b", vague, re.I)]
    assert not names, names
    for words in (f"sheet {job.sheet} ", job.alignment, pp.short_station(job.s0),
                  pp.short_station(job.s1), job.profile, "plan and profile"):
        assert words in vague, words
    for words in ("1\"=", "lower-left", "paper", "0.10", "PVI", "K value", "every", "level",
                  "elevation"):
        assert words not in vague, words
    assert prompting.prompt_at(probe, "vague") == vague and vague in prompting.task_text(probe, "vague")
    assert probe.vague_check is not None and probe.check_at("vague") is probe.vague_check
    assert probe.check_at("explicit") is probe.check


@pytest.mark.parametrize("job", pp.JOBS + pp.NEW_JOBS, ids=IDS)
def test_vague_reads_the_grid_where_it_is_drawn(tmp_path, job):
    # the grid moved off the stated corner, onto another elevation range, at the other
    # standard vertical scale (1"=10' for 1"=5', 1"=20' on D.12): the explicit check
    # fails it, the vague one reads the grid as drawn and passes it
    tall = job.v_scale == 10.0
    moved = dataclasses.replace(job, y0=1.3, e0=job.e0 - 5.0, e1=job.e1 + (0.0 if tall else 5.0),
                                v_scale=20.0 if tall else 10.0)
    explicit, vague = _both(tmp_path, job, layout=moved)
    assert not explicit.passed and dict(explicit.items)["profile grid"] is False
    assert vague.passed, vague.detail
    assert [name for name, _ok in vague.items] == [name for name, _ok in explicit.items]


@pytest.mark.parametrize("job", [pp.CFL, pp.WFL18, pp.FDOT], ids=lambda j: j.id)
def test_vague_allows_another_standard_plan_scale(tmp_path, job):
    # plan and profile at 1"=60' (the profile at 1"=6', 10:1): another standard scale
    explicit, vague = _both(tmp_path, job, h_scale=60.0, vertical=6.0)
    assert not explicit.passed and dict(explicit.items)["plan view"] is False
    assert vague.passed, vague.detail


def test_vague_untouched_starts_fail(tmp_path):
    for job in pp.JOBS + pp.NEW_JOBS:
        start = fixture.start_document(tmp_path / job.start, job.start)
        s = Session.load(start, out_dir=start.parent)
        result = BY_ID[job.id].check_at("vague")(s, s)
        assert not result.passed and "no viewport" in result.detail


@pytest.mark.parametrize("job", pp.JOBS + pp.NEW_JOBS, ids=IDS)
def test_vague_grade_drawn_pvi_to_pvi_fails(tmp_path, job):
    _explicit, vague = _both(tmp_path, job, curves=False)
    assert dict(vague.items)["profile grade line"] is False, vague.detail


def test_vague_still_grades_what_a_drafter_knows(tmp_path):
    def shift_plan(session, job=pp.CFL):
        sheet = next(s for s in session.doc.sheets.values() if s.name == job.sheet)
        vp = sheet.viewports[0]
        at = [vp.center_paper[0] + 0.5, vp.center_paper[1]]
        assert session.execute("modify_viewport", {"sheet": sheet.name, "viewport_id": vp.id,
                                                   "changes": {"center_paper": at}})["ok"]

    # the plan half an inch (25 ft) off the profile's stations
    _e, vague = _both(tmp_path / "shift", pp.CFL, edit=shift_plan)
    assert dict(vague.items)["plan stations line up with the profile"] is False
    # no vertical exaggeration (1"=50' both ways) is no plan-and-profile pair
    _e, vague = _both(tmp_path / "flat", pp.WFL21, vertical=50.0)
    assert dict(vague.items)["profile grid"] is False and "not a standard pair" in vague.detail
    # 1"=12' is on no engineer's scale
    _e, vague = _both(tmp_path / "v12", pp.WFL21, h_scale=60.0, vertical=12.0)
    assert dict(vague.items)["profile grid"] is False
    # a grid whose range the grade runs out of
    low = dataclasses.replace(pp.CFL, e0=pp.CFL.e0 + 10.0, e1=pp.CFL.e1 + 10.0)
    _e, vague = _both(tmp_path / "low", pp.CFL, layout=low)
    assert dict(vague.items)["profile grid"] is False and "outside the grid" in vague.detail

    # a high point lettered where the profile has none
    def liar(session, job=pp.WFL):
        x, y = job.x(11100.0), job.y(6266.87)
        assert session.execute("place_text", {"space": job.sheet, "position": [x + 0.3, y - 1.0],
                                              "content": "HIGH PT 111+00.00", "height": 0.1})["ok"]

    _e, vague = _both(tmp_path / "hp", pp.WFL, edit=liar)
    assert dict(vague.items)["no high or low point where the profile has none"] is False


def test_vague_grid_without_elevations_cannot_be_read(tmp_path):
    # with no elevation lettered at the grid's lines the profile has no datum to read
    def unlettered(session, job=pp.CFL):
        sheet = next(s for s in session.doc.sheets.values() if s.name == job.sheet)
        ids = [e.id for e in sheet.entities.values()
               if re.fullmatch(r"\d,\d{3}", getattr(e, "content", "") or "")]
        assert ids and session.execute("delete_entities", {"ids": ids})["ok"]

    explicit, vague = _both(tmp_path, pp.CFL, edit=unlettered)
    items = dict(vague.items)
    assert not items["grid lettering"] and not items["profile grade line"]
    assert not items["PVI 11+50.00: K"]
    # the item list is the explicit one's, whatever could not be read
    assert [name for name, _ok in vague.items] == [name for name, _ok in explicit.items]


def test_vague_reads_curve_data_by_meaning():
    for text, length, k in (("L.V.C. = 150'\nK-VALUE = 69", 150.0, 69.0),
                            ("VC 200'\nK: 80.6", 200.0, 80.6), ("150' VC\nK = 69", 150.0, 69.0)):
        lengths = [float(a or b) for a, b in pp.LENGTH_RE_ANY.findall(text)]
        assert length in lengths and k in [float(v) for v in pp.K_RE_ANY.findall(text)], text
    # the explicit forms are all still read
    assert pp.LENGTH_RE.findall("L = 150'") and pp.LENGTH_RE_ANY.findall("L = 150'")
    assert not pp.LENGTH_RE.findall("L.V.C. = 150'")
