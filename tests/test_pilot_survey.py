"""Pilot 3, survey traps: the probes build, their truth is what the notes say,
and each scripted solution passes while the untouched start and the naive
answer fail."""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.design import cogo
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, survey

IDS = [survey.MIS_ID, survey.GG_ID, survey.IF_ID, survey.DEED_PPM049.id, survey.DEED_FDOT915.id,
       survey.GG2_ID, survey.IF2_ID]


def test_probes_build():
    assert [p.id for p in survey.PROBES] == IDS
    for p in survey.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START


def test_misclosure_truth():
    t = survey.misclosure_truth()
    assert t["misclosure"] == pytest.approx(0.2747, abs=1e-3)
    assert t["precision"] == pytest.approx(6534, abs=5)
    assert t["area"] == pytest.approx(132346.1, abs=0.5)
    # the balance holds the POB and moves later corners further
    moves = [math.dist(a, b) for a, b in zip(t["raw"], t["corners"])]
    assert moves[0] == 0.0 and all(0.02 < m < 0.25 for m in moves[1:])


def test_unit_truths():
    ties = survey.grid_ground_truth()
    occupied = survey._control(survey.GG_OCCUPIED)
    for (_n, _d, xy), (_n2, _d2, _a, ground) in zip(ties, survey.GG_TIES):
        # skipping the factor would be off by more than the tolerance
        assert ground * (1 - survey.GG_FACTOR) > 3 * survey.GG_TOL_FT
        assert math.dist(occupied, xy) == pytest.approx(ground * survey.GG_FACTOR, abs=1e-6)
    for (_n, _d, xy), row in zip(survey.intl_feet_truth(), survey.IF_POINTS):
        assert abs(xy[0] - row[4]) > 1.0          # the given value is not the answer


def _session_pair(tmp_path, probe):
    doc = fixture.start_document(tmp_path, probe.start)
    return Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path), doc


@pytest.mark.parametrize("probe", survey.PROBES, ids=IDS)
def test_selftest(tmp_path, probe):
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched, _ = _session_pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


def test_naive_answers_fail(tmp_path):
    probes = {p.id: p for p in survey.PROBES}
    # the deed as written, closed with a closing course
    base, s, doc = _session_pair(tmp_path / "a", probes[survey.MIS_ID])
    raw = survey.misclosure_truth()["raw"][:-1]
    s.execute("create_layer", {"name": survey.MIS_LAYER})
    s.execute("draw_polyline", {"space": "model", "layer": survey.MIS_LAYER,
                                "vertices": raw, "closed": True})
    assert not probes[survey.MIS_ID].check(base, s).passed
    # ground distances plotted on the grid drawing
    base, s, doc = _session_pair(tmp_path / "b", probes[survey.GG_ID])
    occ, bs = survey._control(survey.GG_OCCUPIED), survey._control(survey.GG_BACKSIGHT)
    az_bs, _ = cogo.inverse(occ, bs)
    s.execute("create_points", {"points": [
        {"number": n, "point": cogo.forward(occ, az_bs + cogo.parse_dms(a), g)}
        for n, _d, a, g in survey.GG_TIES]})
    assert not probes[survey.GG_ID].check(base, s).passed
    # international feet typed in as US survey feet
    base, s, doc = _session_pair(tmp_path / "c", probes[survey.IF_ID])
    s.execute("create_points", {"points": [
        {"number": n, "northing": north, "easting": east}
        for n, _d, _u, north, east in survey.IF_POINTS]})
    assert not probes[survey.IF_ID].check(base, s).passed


# ------------------------------------------------- the instances added Nov 2026

DEEDS = [survey.DEED_PPM049, survey.DEED_FDOT915]


def test_new_deed_truths():
    t = survey.deed_truth(survey.DEED_PPM049)
    assert len(survey.DEED_PPM049.legs) == 10
    assert t["misclosure"] == pytest.approx(0.3541, abs=1e-3)
    assert t["precision"] == pytest.approx(4840, abs=5)
    t = survey.deed_truth(survey.DEED_FDOT915)
    assert t["misclosure"] == pytest.approx(0.2823, abs=1e-3)
    assert t["precision"] == pytest.approx(4259, abs=5)
    assert len(t["arcs"]) == 1
    # the arc adds its segment: the chord polygon is short by about 156 sq ft
    assert t["area"] - survey._shoelace(t["corners"]) == pytest.approx(156.4, abs=1.0)
    for deed in DEEDS:
        t = survey.deed_truth(deed)
        moves = [math.dist(a, b) for a, b in zip(t["raw"], t["corners"])]
        assert moves[0] == 0.0 and all(m > 3 * survey.DEED_CORNER_FT for m in moves[2:])


def test_new_deeds_sit_on_the_drawing(tmp_path):
    """The deeds' R/W courses run on the drawn R/W: L-5's POB is the end of
    LN-433; the FDOT POB is 67.95 ft right of CL1 at 702+50."""
    doc = common.document(common.folder("PPM-049") / "0000000000aa01.rdraft")
    ln = doc.model_entities["LN-433"]
    assert math.dist(ln.start[:2], survey.DEED_PPM049.pob) < 0.01
    ali = common.document(common.folder(survey.DEED_FDOT915.sheet_id) / "ALGNRD01.rdraft")
    r = ali.design.alignments["CL1"].xy_to_station(list(survey.DEED_FDOT915.pob))
    assert r["station"] == pytest.approx(70250.0, abs=0.01)
    assert r["offset"] == pytest.approx(67.95, abs=0.01)


@pytest.mark.parametrize("deed", DEEDS, ids=[d.id for d in DEEDS])
def test_new_deeds_naive_answers_fail(tmp_path, deed):
    probe = {p.id: p for p in survey.PROBES}[deed.id]
    # as written, closed with a closing course
    base, s, _ = _session_pair(tmp_path / "raw", probe)
    survey.solve_deed(deed, s, balance=False)
    result = probe.check(base, s)
    assert not result.passed
    assert dict(result.items)["corners on the compass-rule balance (0.02 ft)"] is False
    # the last corner moved onto the POB
    base, s, _ = _session_pair(tmp_path / "last", probe)
    survey.solve_deed(deed, s)
    t = survey.deed_truth(deed)
    pl = [e for e in s.doc.model_entities.values() if e.layer == deed.layer
          and e.TYPE == "polyline"][0]
    verts = [list(v) for v in t["raw"][:-1]]
    assert s.execute("modify_entity", {"id": pl.id, "changes": {"vertices": verts}})["ok"]
    assert not probe.check(base, s).passed


def test_corrected_deed_fails(tmp_path):
    """Finding the two scrivener's errors and plotting the true courses closes
    exactly, but it is not the compass balance the task asks for."""
    probe = {p.id: p for p in survey.PROBES}[survey.DEED_PPM049.id]
    legs = list(survey.DEED_PPM049.legs)
    legs[4] = dict(legs[4], distance=143.07)
    legs[7] = dict(legs[7], bearing="S 13°35'05\" W")
    fixed = survey.Deed(id="x", sheet_id="PPM-049", file="x", pob=survey.DEED_PPM049.pob,
                        legs=tuple(legs))
    assert survey.deed_truth(fixed)["misclosure"] < 0.02
    base, s, _ = _session_pair(tmp_path / "fixed", probe)
    survey.solve_deed(fixed, s)
    assert not probe.check(base, s).passed


def test_curve_as_its_chord_or_short_chords(tmp_path):
    """The FDOT curve drawn as its chord fails the area; drawn as short chords
    on the balanced arc it is accepted."""
    deed = survey.DEED_FDOT915
    probe = {p.id: p for p in survey.PROBES}[deed.id]
    t = survey.deed_truth(deed)
    base, s, _ = _session_pair(tmp_path / "chord", probe)
    s.execute("create_layer", {"name": deed.layer})
    s.execute("draw_polyline", {"space": "model", "layer": deed.layer, "vertices": t["corners"],
                                "closed": True})
    s.execute("place_text", {"space": "model", "layer": deed.layer,
                             "position": t["corners"][3],
                             "content": f"{survey._shoelace(t['corners']):,.0f} SQ FT"})
    s.execute("set_meta", {"updates": {"misclosure_ft": round(t["misclosure"], 3),
                                       "precision": f"1:{t['precision']:.0f}",
                                       "area_sqft": round(survey._shoelace(t["corners"]))}})
    result = probe.check(base, s)
    items = dict(result.items)
    assert not result.passed
    assert items["corners on the compass-rule balance (0.02 ft)"]
    assert items["curve course 2 drawn on its balanced arc (0.05 ft)"] is False
    # turned the wrong way: a left curve on the same chord
    base, s, _ = _session_pair(tmp_path / "left", probe)
    survey.solve_deed(deed, s)
    pl = [e for e in s.doc.model_entities.values() if e.layer == deed.layer
          and e.TYPE == "polyline"][0]
    assert s.execute("modify_entity", {"id": pl.id, "changes": {
        "bulges": [-b for b in pl.bulges]}})["ok"]
    assert not probe.check(base, s).passed
    base, s, _ = _session_pair(tmp_path / "dense", probe)
    survey.solve_deed(deed, s)
    pl = [e for e in s.doc.model_entities.values() if e.layer == deed.layer
          and e.TYPE == "polyline"][0]
    i = t["arcs"][0][0]
    pts = survey._arc_points(t["corners"][i], t["corners"][i + 1], t["arcs"][0][1],
                             t["arcs"][0][2], step_ft=10.0)
    verts = t["corners"][:i + 1] + pts[1:-1] + t["corners"][i + 1:]
    assert s.execute("modify_entity", {"id": pl.id, "changes": {"vertices": verts,
                                                               "bulges": [0.0] * len(verts)}})["ok"]
    result = probe.check(base, s)
    items = dict(result.items)
    assert items["no unbalanced or extra corners on V-PROP"], result.detail


def test_grid_to_ground_naive_answers_fail(tmp_path):
    probe = {p.id: p for p in survey.PROBES}[survey.GG2_ID]
    truth = {n: xy for n, _d, xy in survey.grid_to_ground_truth()}
    _n, cn, ce, _d = survey.GG2_CONTROL[0]
    variants = {
        "as given": lambda north, east: [east, north],
        "times the factor": lambda north, east: [ce + (east - ce) * survey.GG2_FACTOR,
                                                 cn + (north - cn) * survey.GG2_FACTOR],
        "about the origin": lambda north, east: [east / survey.GG2_FACTOR,
                                                 north / survey.GG2_FACTOR],
    }
    for name, fn in variants.items():
        base, s, _ = _session_pair(tmp_path / name.replace(" ", "-"), probe)
        pts = [{"number": n, "point": fn(north, east)} for n, _d, north, east in survey.GG2_LOCATES]
        s.execute("create_points", {"points": pts})
        assert not probe.check(base, s).passed, name
        off = [math.dist(p["point"], truth[p["number"]]) for p in pts]
        assert min(off) > 2 * survey.GG_TOL_FT, name


def test_grid_to_ground_lands_on_the_culverts():
    """The truth is CL1 station/offset of the culvert ends, in the moved set."""
    ali = common.document(common.folder(survey.GG2_SHEET) / "ALI(MAIN)Sample.rdraft")
    a = ali.design.alignments["CL1"]
    dx, dy = survey.GG2_DELTA
    for (n, _d, xy), (st, off) in zip(survey.grid_to_ground_truth(),
                                      [(1254, -23), (1254, 23), (1690, -21), (1690, 21),
                                       (2198, -18), (2198, 18)]):
        r = a.xy_to_station([xy[0] - dx, xy[1] - dy])
        assert r["station"] == pytest.approx(st, abs=0.01), n
        assert r["offset"] == pytest.approx(off, abs=0.01), n


def test_intl_drawing_start_and_naive_answers(tmp_path):
    probe = {p.id: p for p in survey.PROBES}[survey.IF2_ID]
    base, s, doc = _session_pair(tmp_path / "start", probe)
    assert s.doc.meta.get("model_units") == "ft"
    for path in doc.parent.glob("*.rdraft"):
        assert common.document(path).meta.get("model_units") == "ft", path.name
    variants = {
        "as given": (1.0, 3937.0 / 1200.0),
        "us factor the wrong way": (0.999998, 1.0 / 0.3048),
        "metres by 3937/1200": (survey.US_TO_INTL, 3937.0 / 1200.0),
    }
    for name, (k_us, k_m) in variants.items():
        base, s, _ = _session_pair(tmp_path / name.replace(" ", "-").replace("/", ""), probe)
        s.execute("create_points", {"points": [
            {"number": n, "northing": north * (k_us if u == "usft" else k_m),
             "easting": east * (k_us if u == "usft" else k_m)}
            for n, _d, u, north, east in survey.IF2_POINTS]})
        assert not probe.check(base, s).passed, name
    # the converted monuments sit on one line 40 ft left of MAIN 01
    ali = common.document(common.folder(survey.IF2_SHEET) / "SamplePlan_ali.rdraft")
    a = ali.design.alignments["MAIN 01"]
    dx, dy = survey.IF2_DELTA
    for n, _d, xy in survey.intl_drawing_truth()[:4]:
        r = a.xy_to_station([xy[0] - dx, xy[1] - dy])
        assert r["offset"] == pytest.approx(-40.0, abs=0.02), n


# ------------------------------------------------------------------ the vague level

BY_ID = {p.id: p for p in survey.PROBES}
DEED_IDS = [survey.MIS_ID, survey.DEED_PPM049.id, survey.DEED_FDOT915.id]
DEED_TEXTS = {survey.MIS_ID: survey._deed_text(), survey.DEED_PPM049.id: survey._deed_text_ppm049(),
              survey.DEED_FDOT915.id: survey._deed_text_fdot915()}
#: what each points brief must keep: the data as delivered, the systems and units the files do
#: not carry, the factor and the control it is about
POINT_KEEPS = {
    survey.GG_ID: [survey._ties_text(), "sheet D.11", "Wyoming West state plane grid", "YRB3",
                   "backsighted 23307", "angles right", "horizontal ground distances",
                   "combined factor at YRB3 is 0.999649"],
    survey.IF_ID: [survey._intl_list("ift"), survey._intl_list("m"), "sheet L-3",
                   "CCS83 Zone 2, international feet", "CCS83 Zone 2, metres"],
    survey.GG2_ID: [survey._gg2_list(), "CFL Plan 1", "project ground", "Colorado Central",
                    "scaled about CP-1", "0.999562", "US survey feet"],
    survey.IF2_ID: [survey._if2_list("usft"), survey._if2_list("m"), "sheet D.6",
                    "Montana State Plane (zone 2500)", "base files are in international feet",
                    "(US survey feet)", "(metres)"],
}


def _tools_named(text, allowed=("set_meta",)):
    """The tool names a brief mentions, as words of their own ("area" is the plain word)."""
    import re
    from roaddraft.mcp.server import tool_definitions
    names = [t["name"] for t in tool_definitions(Session(), attachments=True)]
    return [n for n in names if n not in allowed and n != "area"
            and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I)]


@pytest.mark.parametrize("probe", survey.PROBES, ids=IDS)
def test_vague_brief(probe):
    v = probe.vague
    assert v.strip() and v != probe.prompt and len(v) < len(probe.prompt)
    assert not _tools_named(v), _tools_named(v)
    if probe.id in DEED_IDS:
        # the deed as written, the balance the check grades and the keys it reads; no layer
        assert v.endswith("The deed reads: " + DEED_TEXTS[probe.id])
        for keep in ("check the closure", "compass rule", "closed", "area in square feet",
                     "inside", "misclosure_ft", "precision (as 1:N)", "area_sqft", "set_meta"):
            assert keep in v, keep
        assert "V-PROP" in probe.prompt and "layer" not in v and "V-PROP" not in v
        assert probe.vague_check is not None
    else:
        for keep in POINT_KEEPS[probe.id] + ["COGO points", "numbers and descriptions"]:
            assert keep in v, keep
        assert "set_meta" not in v
        assert probe.vague_check is None         # the point checks grade numbers and positions


def _relayered(tmp_path, probe, layer):
    """The scripted solution, its parcel moved onto ``layer``."""
    base, s, _ = _session_pair(tmp_path, probe)
    probe.solve(s)
    if layer not in s.doc.layers:
        assert s.execute("create_layer", {"name": layer})["ok"]
    for e in list(survey.added_model(base, s)):
        if e.layer == survey.MIS_LAYER and e.TYPE != "text":
            assert s.execute("modify_entity", {"id": e.id, "changes": {"layer": layer}})["ok"]
    return base, s


@pytest.mark.parametrize("pid", DEED_IDS)
def test_vague_deed_takes_any_layer_but_0(tmp_path, pid):
    probe = BY_ID[pid]
    vague = probe.check_at("vague")
    # the solution as scripted, on V-PROP: both levels pass, item by item alike
    base, s = _relayered(tmp_path / "vprop", probe, survey.MIS_LAYER)
    explicit, lenient = probe.check(base, s), vague(base, s)
    assert explicit.passed and lenient.passed, lenient.detail
    assert [d for _n, d in explicit.items] == [d for _n, d in lenient.items]
    assert any(n.endswith(f"on {survey.ANY_LAYER}") for n, _d in lenient.items)
    assert not any("V-PROP" in n for n, _d in lenient.items)
    # on a layer of the drafter's own: the vague level passes, the explicit one does not
    base, s = _relayered(tmp_path / "own", probe, "PROPERTY-LINES")
    assert vague(base, s).passed and not probe.check(base, s).passed
    assert [n for n, _d in vague(base, s).items] == [n for n, _d in lenient.items]
    # on layer 0: not even the vague level takes it
    base, s = _relayered(tmp_path / "zero", probe, "0")
    result = vague(base, s)
    assert not result.passed and f"nothing was drawn on {survey.ANY_LAYER}" in result.detail
    # the untouched start fails
    base, untouched, _ = _session_pair(tmp_path / "start", probe)
    assert not vague(base, untouched).passed


@pytest.mark.parametrize("deed", DEEDS, ids=[d.id for d in DEEDS])
def test_vague_deed_still_grades_the_balance(tmp_path, deed):
    """The deed as written, closed with a closing course, on a layer of its own: the vague
    level fails it on the corners as the explicit one does on V-PROP."""
    from dataclasses import replace
    probe = BY_ID[deed.id]
    base, s, _ = _session_pair(tmp_path / "raw", probe)
    survey.solve_deed(replace(deed, layer="PARCEL"), s, balance=False)
    result = probe.check_at("vague")(base, s)
    assert not result.passed
    assert dict(result.items)["corners on the compass-rule balance (0.02 ft)"] is False
    # the raw parcel on one layer and the balanced one on another: the balanced one is graded
    survey.solve_deed(replace(deed, layer="PARCEL-BAL"), s)
    assert probe.check_at("vague")(base, s).passed
