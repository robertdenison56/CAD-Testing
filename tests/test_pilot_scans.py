"""Pilots 1 and 15 (probes/pilot/scans.py): redraw an alignment from a scan,
and read a scanned sheet. The probes build, their scripted solutions pass,
their starts and the naive wrong answers fail, and the truth they grade
against agrees with the redraft and the published sheet."""
from __future__ import annotations

import math
import re
import subprocess

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture
from roaddraft.probes import notation as nt
from roaddraft.probes.pilot import BY_ID, common, scans

REDRAW_IDS = [s.id for s in scans.REDRAWS]
READING_IDS = [s.id for s in scans.READINGS]


@pytest.fixture(scope="module")
def starts(tmp_path_factory):
    """Each probe's start, built once: ``{id: document path}``."""
    root = tmp_path_factory.mktemp("scans")
    return {p.id: fixture.start_document(root / p.id, p.start) for p in scans.PROBES}


def _fresh(path):
    return Session.load(path, out_dir=path.parent)


def _spec(pid):
    return next(s for s in scans.REDRAWS + scans.READINGS if s.id == pid)


# ------------------------------------------------------------------ the probes


def test_probes_build():
    assert [p.id for p in scans.PROBES] == REDRAW_IDS + READING_IDS
    for p in scans.PROBES:
        assert p.id in BY_ID and "pilot" in BY_ID[p.id].tags
        assert p.prompt.strip() and p.note.strip() and p.solve is not None
        assert p.server_args == ["--attachments", "{project}/scans"]
        assert re.match(r"p(01|15)-[a-z-]+-[a-z0-9]+$", p.id)
        assert "view_attachment" in p.prompt


def test_starts_hold_the_scan_and_no_answers(starts):
    for pid, doc in starts.items():
        scans_dir = doc.parent / scans.SCANS
        pngs = list(scans_dir.glob("*.png"))
        assert len(pngs) == 1 and pngs[0].name in BY_ID[pid].prompt
        assert not list(doc.parent.rglob("*.pdf"))           # no text layer anywhere
    for spec in scans.REDRAWS:
        folder = starts[spec.id].parent
        assert not (folder / common.sheet_file(spec.sheet)).exists()
        base = _fresh(starts[spec.id])
        assert spec.alignment not in base.doc.design.alignments
        assert spec.truth(base).curves()                  # the truth builds on the start
        for path in folder.glob("*.rdraft"):
            doc = common.document(path)
            for e in doc.model_entities.values():
                anchor = getattr(e, "anchor", None) or {}
                assert anchor.get("alignment") != spec.alignment
                content = getattr(e, "content", "") or ""
                for _sta, bearing in spec.tangents:
                    assert not any(nt.azimuth_close(a, nt.bearings(bearing)[0])
                                   for a in nt.bearings(content)), (path.name, content)


# ------------------------------------------------------------ p01: the truth


@pytest.mark.parametrize("pid", REDRAW_IDS)
def test_truth_agrees_with_the_redraft(starts, pid):
    """The lettered design held at the tie runs within 0.3 ft of the redraft's
    own alignment (fitted to the drawn linework) wherever the sheet shows it."""
    spec = _spec(pid)
    truth = spec.truth(_fresh(starts[pid]))
    redraft = common.load(common.folder(spec.sheet) / spec.design_file).doc.design.alignments[
        spec.alignment]
    worst, raw = 0.0, redraft.begin_station
    while raw <= redraft.end_station:
        if truth.begin_station <= raw <= truth.end_station:
            worst = max(worst, math.dist(redraft.station_to_xy(raw)[0],
                                         truth.station_to_xy(raw)[0]))
        raw += 5.0
    assert worst < spec.redraft_ft, worst
    assert len(truth.curves()) == len(spec.curves)
    for c, el in zip(spec.curves, truth.curves()):
        assert abs(truth.begin_station + el.start_dist - c.pc) < 0.011
        assert abs(truth.begin_station + el.end_dist - c.pt) < 0.011
        assert el.direction == c.turn


def test_fdot_tie_is_the_redrafts():
    """The prompt's N 9820.83, E 10300.67 is the redraft's CL1 at 700+00.00."""
    f = common.folder("FDOT-915-1-Roadway-Plan-Profile")
    cl1 = common.load(f / "ALGNRD01.rdraft").doc.design.alignments["CL1"]
    t = cl1.tangents()[0]
    back = cl1.begin_station - 70000.00
    a = math.radians(90.0 - t.direction_deg)
    at = [t.start[0] - back * math.sin(a), t.start[1] - back * math.cos(a)]
    assert math.dist(at, scans.CL1["tie"]) < 0.01
    assert "N 9820.83, E 10300.67" in BY_ID["p01-redraw-alignment-fdot915"].prompt


# ---------------------------------------------------- p01: solve and naive wrong


def _build(session, name, start, begin, legs, layer):
    common.ok(session.execute("create_alignment", {"name": name, "start": start,
                                                   "begin_station": begin, "legs": legs}))
    common.ok(session.execute("draw_alignment", {"alignment": name, "layer": layer}))


def _tb1(session, tie_offset=63.32, shift=0.0, b2="N 01°05'14\" W", radius=3280.83):
    pot = common.ok(session.query("station_to_xy", {"alignment": "D13", "station": 64773.40,
                                                    "offset": tie_offset}))["point"]
    pot = [pot[0] + shift, pot[1]]
    T = 82.03
    back2 = "S" + b2[1:-1] + "E"
    r = common.ok(session.query("traverse", {"start": pot, "legs": [
        {"bearing": back2, "distance": 328.15 + T},
        {"bearing": "S 03°57'06\" E", "distance": T + 417.16}]}))
    _build(session, "TB1", r["points"][-1], "638+64.07",
           [{"bearing": "N 03°57'06\" W", "distance": 417.16 + T},
            {"bearing": b2, "distance": T + 328.15, "radius": radius}], "V-ALIGN-CNTR")


def _cl1(session, turn="RT", begin="700+00.00"):
    _build(session, "CL1", scans.CL1["tie"], begin,
           [{"bearing": "N 59°59'28\" W", "distance": 972.30},
            {"deflection": f"49°03'08\" {turn}", "distance": 601.98, "radius": 881.0}], "P_ALIGN")


@pytest.mark.parametrize("pid", REDRAW_IDS + READING_IDS)
def test_solution_passes_and_start_fails(starts, pid):
    probe = BY_ID[pid]
    base = _fresh(starts[pid])
    assert not probe.check(base, _fresh(starts[pid])).passed
    work = _fresh(starts[pid])
    probe.solve(work)
    result = probe.check(base, work)
    assert result.passed, result.detail
    assert result.items and all(done for _item, done in result.items)


@pytest.mark.parametrize("variant, passes, item", [
    ({}, True, None),
    ({"radius": 3280.0}, True, None),                     # the table's rounded radius still holds
    ({"shift": 1.0}, False, "on its tie"),                # placed by eye on the ramp linework
    ({"tie_offset": -63.32}, False, "on its tie"),         # the tie read as Lt
    ({"b2": "N 01°05'41\" W"}, False, "tangent bearing N 01°05'14\" W"),   # seconds transposed
])
def test_tb1_naive_answers(starts, variant, passes, item):
    probe = BY_ID["p01-redraw-alignment-ppm045"]
    base, work = _fresh(starts[probe.id]), _fresh(starts[probe.id])
    _tb1(work, **variant)
    result = probe.check(base, work)
    assert result.passed is passes, result.detail
    if item:
        assert not dict(result.items)[next(k for k in dict(result.items) if k.startswith(item))]


@pytest.mark.parametrize("variant, item", [
    ({"turn": "LT"}, "the curve: R"),                     # the (RT) missed
    ({"begin": "700+23.62"}, "the curve: PC"),            # BEGIN PROJECT put on the tie point
])
def test_cl1_naive_answers(starts, variant, item):
    probe = BY_ID["p01-redraw-alignment-fdot915"]
    base, work = _fresh(starts[probe.id]), _fresh(starts[probe.id])
    _cl1(work, **variant)
    result = probe.check(base, work)
    assert not result.passed
    assert not dict(result.items)[next(k for k in dict(result.items) if k.startswith(item))]


# ----------------------------------------------------------- p15: the truth


def _pdf_text(sheet_id: str) -> str:
    out = subprocess.run(["pdftotext", "-layout", str(common.source_pdf(sheet_id)), "-"],
                         capture_output=True, text=True, check=True).stdout
    # Caltrans' font letters the degree sign as ^
    return re.sub(r"\s+", "", out.replace("’", "'").replace("”", '"').replace("^", "°"))


#: the answers the published sheet letters as such (the rest are worked out):
#: {key: (as the PDF's text layer holds it, the answer)}; rotated lettering comes out
#: of the text layer broken (L-2's vertical BC callout, CFL's tilted bearing)
PRINTED = {
    "p15-plan-reading-ppm046": {"q1": ("5000'", "5000'"), "q2": ("654+06", "654+06.40"),
                                "q4": ("N00°03'30\"E",) * 2, "q5": ("R11.9/R24.1",) * 2,
                                "q6": ("03°03'45\"",) * 2},
    "p15-plan-reading-wflp14": {"q1": ("1,190.00'",) * 2, "q3": ("N23°38'45\"E",) * 2,
                                "q4": ("AKNPSSAMP14(1)", "AK NPS SAMP 14(1)"),
                                "q5": ("937984.0982",) * 2},
    "p15-plan-reading-cflpla": {"q1": ("855.00'",) * 2, "q2": ("S71°44", "S71°44'22\"E"),
                                "q3": ("243.42'",) * 2, "q6": ("06°20'23\"(RT)",) * 2},
    # the later readings ask nothing the sheet letters as such: every answer is worked out
    # (their inputs are checked in test_reading_inputs_are_on_the_published_sheet)
    "p15-plan-reading-fdot916": {}, "p15-plan-reading-ppm052": {},
    "p15-plan-reading-ppm049": {}, "p15-plan-reading-wflp16": {},
    "p15-plan-reading-wflp21": {},
}


@pytest.mark.parametrize("pid", READING_IDS)
def test_reading_truth_is_on_the_published_sheet(pid):
    spec = _spec(pid)
    src = scans.Sources(spec.sheet)
    text = _pdf_text(spec.sheet)
    for key, (in_pdf, answer) in PRINTED[pid].items():
        assert in_pdf in text, (key, in_pdf)
        q = next(q for q in spec.questions if q.key == key)
        assert scans._graded(q, q.truth(src), answer) is None, (key, answer)


def test_worked_out_answers():
    got = {}
    for spec in scans.READINGS:
        src = scans.Sources(spec.sheet)
        got.update({(spec.id, q.key): q.truth(src) for q in spec.questions})
    assert got[("p15-plan-reading-ppm046", "q3")] == pytest.approx(65406.40 + 3604.04)
    assert got[("p15-plan-reading-wflp14", "q2")] == pytest.approx(11361.72 + 584.76)
    assert got[("p15-plan-reading-wflp14", "q6")] == pytest.approx(11361.72 - 11005.00)
    assert got[("p15-plan-reading-cflpla", "q4")] == pytest.approx(3400.32 - 3273.85)
    assert got[("p15-plan-reading-cflpla", "q5")] == 50.0


# ----------------------------------------------- p15: spellings and naive wrong


@pytest.mark.parametrize("pid, answers, passes, bad", [
    # other spellings of the right answers pass
    ("p15-plan-reading-ppm046", {"q1": "R = 5,000'", "q2": "Sta. 654+06.40",
                                 "q4": "N00-03-30E", "q6": "3°03'45\""}, True, None),
    ("p15-plan-reading-cflpla", {"q5": "1:600", "q6": "6°20'23\" right",
                                 "q2": "S71°44'22\"E"}, True, None),
    ("p15-plan-reading-wflp14", {"q4": "ak nps samp 14(1)", "q5": "937984.0982"}, True, None),
    # the naive answers fail
    ("p15-plan-reading-ppm046", {"q3": "672+90.72"}, False, "q3"),         # BC + T, not BC + L
    ("p15-plan-reading-wflp14", {"q5": "938002.4670"}, False, "q5"),       # Begin Construction's
    ("p15-plan-reading-wflp14", {"q2": "119+58.54"}, False, "q2"),         # PI + T
    ("p15-plan-reading-cflpla", {"q2": "N 71°44'22\" E"}, False, "q2"),    # the cut-off S
    ("p15-plan-reading-cflpla", {"q2": "71°44'22\"E"}, False, "q2"),       # no quadrant
    ("p15-plan-reading-cflpla", {"q6": "06°20'23\" LT"}, False, "q6"),
    ("p15-plan-reading-ppm046", {"q4": "N 00°03'30\" W"}, False, "q4"),
])
def test_reading_answers(starts, pid, answers, passes, bad):
    spec, probe = _spec(pid), BY_ID[pid]
    base, work = _fresh(starts[pid]), _fresh(starts[pid])
    common.ok(work.execute("set_meta", {"updates": dict(spec.answers, **answers)}))
    result = probe.check(base, work)
    assert result.passed is passes, result.detail
    if bad:
        failed = [item for item, done in result.items if not done]
        assert len(failed) == 1 and failed[0].startswith(bad), failed


# ------------------------------------- the later redraws: L-7's F6, CFL Plan 1, WFL D.11


NEW_REDRAWS = ["p01-redraw-alignment-ppm050", "p01-redraw-alignment-cflpnp",
               "p01-redraw-alignment-wfl20"]


@pytest.mark.parametrize("pid", NEW_REDRAWS)
def test_later_strips_keep_the_corridor(starts, pid):
    """On sheets drawn in short segments the strip takes the strokes on the line and the
    TRACE layers only, not the corridor and topo round it (L-1's 13 ft would take half of
    CFL's corridor file)."""
    spec = _spec(pid)
    folder = starts[pid].parent
    for path in folder.glob("*.rdraft"):
        if path.name == spec.design_file:
            continue
        before = common.document(common.folder(spec.sheet) / path.name).model_entities
        after = common.document(path).model_entities
        assert len(before) - len(after) < 40, (path.name, len(before), len(after))


def test_f6_needs_the_loop_radius_worked_out():
    """Curve 45's table R 180' is 55 m rounded: its L over its delta is 180.44, and R 180'
    would bring the loop's EC 1.37 ft short of the lettered 714+56.18."""
    delta = math.radians(176 + 11 / 60 + 9 / 3600)
    assert scans.F6["r45"] == pytest.approx(180.444, abs=0.001)
    assert scans.F6["r45"] * math.tan(delta / 2) == pytest.approx(5419.20, abs=0.01)
    assert 554.87 - 180.0 * delta == pytest.approx(1.37, abs=0.01)
    # the middle tangent is lettered against the stationing: S 45°15'06" E, run N 45°15'06" W
    assert scans._azimuth(scans.F6["b2"]) == pytest.approx(
        (scans._azimuth("S 45°15'06\" E") + 180.0) % 360.0)


def test_cfl_and_d11_bearings_are_worked_out():
    """The bearing on past the last curve is lettered nowhere on either sheet: it is the
    bearing in turned by the delta (CFL's second curve LT, D.11's LT)."""
    assert scans._azimuth(scans.CFL1["b3"]) == pytest.approx(
        scans._azimuth(scans.CFL1["b2"]) - scans._dms(scans.CFL1["d2"]), abs=1e-6)
    assert scans._azimuth(scans.D11["b2"]) == pytest.approx(
        scans._azimuth(scans.D11["b1"]) - scans._dms(scans.D11["delta"]), abs=1e-6)
    text = _pdf_text("CFL-D-Plan-and-Profile") + _pdf_text("WFL-Plan-Profile-Sheets-p20")
    assert "16°07'37" not in text and "45°53'12" not in text and "45°53'11" not in text
    # PI to PI along the tangents is T + tangent + T, not the difference of the PI stations
    legs, _vectors = scans._cfl1_legs()
    assert legs[1]["distance"] == pytest.approx(135.40 + 119.52 + 88.70, abs=0.01)
    assert legs[1]["distance"] - (2160.40 - 1820.33) == pytest.approx(3.55, abs=0.01)


def test_later_ties_are_in_the_prompts():
    assert "N 10486.51, E 9889.59" in BY_ID["p01-redraw-alignment-cflpnp"].prompt
    assert "N 10090.40, E 10058.92" in BY_ID["p01-redraw-alignment-wfl20"].prompt
    assert "FR" in BY_ID["p01-redraw-alignment-ppm050"].prompt
    # the truths hold them: CL1's second PI on the staked point, D.11's 155+69.97 on APPR 01
    truth = scans._cfl1_truth(None)
    legs, vectors = scans._cfl1_legs()
    begin = truth.station_to_xy(truth.begin_station)[0]
    pi2 = [begin[0] + vectors[0][0] + vectors[1][0], begin[1] + vectors[0][1] + vectors[1][1]]
    assert math.dist(pi2, scans.CFL1["pi2"]) < 1e-6
    d11 = scans._d11_truth(None)
    assert math.dist(d11.station_to_xy(15569.97)[0], scans.D11["tie"]) < 1e-6
    for pid in NEW_REDRAWS:            # nothing the check grades is in the task text
        spec = _spec(pid)
        prompt = BY_ID[pid].prompt
        for c in spec.curves:
            assert scans._sta(c.pc) not in prompt and scans._sta(c.pt) not in prompt
            assert c.delta not in prompt
        for _s, bearing in spec.tangents:
            assert not nt.bearings(prompt), prompt


def _f6(session, r45=180.444, turn45=None, b2="N 45°15'06\" W", fr=7169.42):
    pot = common.ok(session.query("station_to_xy", {"alignment": "FR", "station": fr}))["point"]
    t44, t45 = 82.04, 5419.20
    r = common.ok(session.query("traverse", {"start": pot, "legs": [
        {"bearing": "N 41°26'15\" W", "distance": 261.57 + t45},
        {"bearing": "S 45°15'06\" E", "distance": t45 + 353.79 + t44},
        {"bearing": "S 42°23'13\" E", "distance": t44 + 328.15}]}))
    third = ({"deflection": f"176°11'09\" {turn45}"} if turn45 else {"bearing": "S 41°26'15\" E"})
    result = session.execute("create_alignment", {
        "name": "F6", "start": r["points"][-1], "begin_station": "700+55.33",
        "legs": [{"bearing": "N 42°23'13\" W", "distance": 328.15 + t44},
                 {"bearing": b2, "distance": t44 + 353.79 + t45, "radius": 3280.83},
                 dict(third, distance=t45 + 261.57, radius=r45)]})
    if result.get("ok"):
        common.ok(session.execute("draw_alignment", {"alignment": "F6",
                                                     "layer": "V-ALIGN-CNTR"}))


@pytest.mark.parametrize("variant, passes, item", [
    ({}, True, None),
    ({"r45": 180.0}, False, "curve 45: BC"),               # the table's rounded loop radius
    ({"turn45": "RT"}, False, "curve 45: R"),              # the loop turned the wrong way
    ({"b2": "S 45°15'06\" E"}, False, "the alignment F6"),  # the reversed bearing laid out as lettered
    ({"fr": 7128.97}, False, "on its tie"),                # F2's POT on FR taken for F6's
])
def test_f6_naive_answers(starts, variant, passes, item):
    probe = BY_ID["p01-redraw-alignment-ppm050"]
    base, work = _fresh(starts[probe.id]), _fresh(starts[probe.id])
    _f6(work, **variant)
    result = probe.check(base, work)
    assert result.passed is passes, result.detail
    if item:
        assert not dict(result.items)[next(k for k in dict(result.items) if k.startswith(item))]


def _cfl_main(session, pi_pi=343.62, turn2="LT", from_pi=2):
    t1, t2 = 135.40, 88.70
    back = [{"bearing": "S 36°14'46\" W", "distance": pi_pi},
            {"bearing": "S 13°33'40\" W", "distance": t1 + 684.93}][2 - from_pi:]
    r = common.ok(session.query("traverse", {"start": scans.CFL1["pi2"], "legs": back}))
    _build(session, "CL1", r["points"][-1], "10+00.00",
           [{"bearing": "N 13°33'40\" E", "distance": 684.93 + t1},
            {"deflection": "22°41'06\" RT", "radius": 675.0, "distance": pi_pi},
            {"deflection": f"20°07'09\" {turn2}", "radius": 500.0,
             "distance": t2 + 252.73}], "P_ALIGN")


@pytest.mark.parametrize("variant, passes, item", [
    ({}, True, None),
    ({"pi_pi": 340.07}, False, "on its tie"),     # PI to PI as the difference of their stations
    ({"turn2": "RT"}, False, "curve 2: R"),       # the (LT) missed
    ({"from_pi": 1}, False, "on its tie"),        # the staked point taken for the first PI
])
def test_cfl_main_naive_answers(starts, variant, passes, item):
    probe = BY_ID["p01-redraw-alignment-cflpnp"]
    base, work = _fresh(starts[probe.id]), _fresh(starts[probe.id])
    _cfl_main(work, **variant)
    result = probe.check(base, work)
    assert result.passed is passes, result.detail
    if item:
        assert not dict(result.items)[next(k for k in dict(result.items) if k.startswith(item))]


def _d11(session, turn="LT", hold="155+69.97", out_bearing=None):
    curve = ({"bearing": out_bearing} if out_bearing
             else {"deflection": f"33°13'58\" {turn}"})
    spec = {"name": "MAIN 01", "begin_station": "152+96.54",
            "legs": [{"bearing": "S 12°39'14\" E", "distance": 230.80 + 191.89},
                     dict(curve, radius=643.0, distance=191.89 + 99.71)]}
    common.ok(session.execute("create_alignment", dict(spec, start=[0.0, 0.0])))
    at = common.ok(session.query("station_to_xy", {"alignment": "MAIN 01",
                                                   "station": hold}))["point"]
    common.ok(session.execute("delete_alignment", {"name": "MAIN 01"}))
    tie = scans.D11["tie"]
    common.ok(session.execute("create_alignment",
                              dict(spec, start=[tie[0] - at[0], tie[1] - at[1]])))
    common.ok(session.execute("draw_alignment", {"alignment": "MAIN 01", "layer": "P_ALIGN"}))


@pytest.mark.parametrize("variant, passes, item", [
    ({}, True, None),
    ({"turn": "RT"}, False, "the curve: R"),                       # the (LT) missed
    ({"hold": "155+27.34"}, False, "on its tie"),                  # the PC put on APPR 01
    ({"out_bearing": "S 20°34'44\" W"}, False, "tangent bearing S 45"),  # the delta added, not taken off
])
def test_d11_naive_answers(starts, variant, passes, item):
    probe = BY_ID["p01-redraw-alignment-wfl20"]
    base, work = _fresh(starts[probe.id]), _fresh(starts[probe.id])
    _d11(work, **variant)
    result = probe.check(base, work)
    assert result.passed is passes, result.detail
    if item:
        assert not dict(result.items)[next(k for k in dict(result.items) if k.startswith(item))]


# ------------------------------------------------------------- the later readings


#: what the worked-out answers rest on, as the published sheet's text layer holds it
#: (rotated lettering comes out broken: FDOT's PC callout and bearing, L-39's BC 15, D.7's PC)
INPUTS = {
    "p15-plan-reading-fdot916": ["PCSTA.+70.", "ELEV.31.69", "FL26.00(P-104)",
                                 "STA.703+00.00(45.50LT)", "STA.703+00.00(45.50RT)",
                                 "CONST.87LF", "CONST.197LF", "CONST.95LF", "CONST.91LF",
                                 "CONST.53LF", 'OF24"PIPE'],
    "p15-plan-reading-ppm052": ['"SB10"1034+63.35EC', "3,280'", "169.01'", "507.16'",
                                "1,014.09'", "02°57'06\"", "453.29'", 'SCALE:1"=50'],
    "p15-plan-reading-ppm049": ["686+74.74BB(R)", "689+00.31EB(R)", '"D13"690+10.44EC',
                                "1884.32'", "3604.04'", "301.15'Rt\"D13\"688+64.26",
                                "239.93'Rt\"D13\"688+64.26", "86.58'Rt\"D13\"689+00.32",
                                "86.58'Rt\"D13\"686+74.73", 'SCALE:1"=50'],
    "p15-plan-reading-wflp16": ["L=539.31'", "33°57'22\"(RT)", "6247.73", "400'VC", "3.90%",
                                "+58.91", "+70.91", "30.76'Lt"],
    "p15-plan-reading-wflp21": ['"MAIN01"166+00.00', "N=937944.7494", "E=544237.5831",
                                "PI163+50.00", "S45°53'11\"E", "S44°46'51\"E", "6273.16",
                                "10.50'Lt", "10.50'Rt"],
}
NEW_READINGS = sorted(INPUTS)


@pytest.mark.parametrize("pid", NEW_READINGS)
def test_reading_inputs_are_on_the_published_sheet(pid):
    text = _pdf_text(_spec(pid).sheet)
    for item in INPUTS[pid]:
        assert item in text, (pid, item)


def test_later_worked_out_answers():
    got = {}
    for spec in scans.READINGS:
        if spec.id in INPUTS:
            src = scans.Sources(spec.sheet)
            got.update({(spec.id, q.key): q.truth(src) for q in spec.questions})
    f, l39, l5, d7, d12 = NEW_READINGS[0], "p15-plan-reading-ppm052", "p15-plan-reading-ppm049", \
        "p15-plan-reading-wflp16", "p15-plan-reading-wflp21"
    assert got[(f, "q1")] == pytest.approx(70570.72)                 # +70.72 between 705 and 706
    assert got[(f, "q2")] == pytest.approx(31.69 - 26.00)
    assert got[(f, "q3")] == pytest.approx(45.50 + 45.50)
    assert got[(f, "q4")] == pytest.approx(87 + 47 + 197 + 95 + 47 + 91)
    assert got[(f, "q5")] == "N 30°00'32\" E" and got[(f, "q6")] == "R"
    assert got[(l39, "q1")] == pytest.approx(103463.35 - 169.01)
    assert got[(l39, "q2")] == pytest.approx(103916.63 + 507.16)
    assert got[(l39, "q3")][1] == "L" and got[(l39, "q4")] == 100.0
    assert got[(l39, "q5")] == 3281.0 and got[(l39, "q6")] == pytest.approx(453.28)
    assert got[(l5, "q1")] == pytest.approx(68900.31 - 68674.74)
    assert got[(l5, "q2")] == pytest.approx(69010.44 - 3604.04 + 1884.32)
    assert got[(l5, "q3")] == pytest.approx(301.15 - 239.93)
    assert got[(l5, "q4")] == pytest.approx(round(225.59 * 5086.58 / 5000.0, 1))
    assert got[(l5, "q6")] == pytest.approx(69010.44 - 68900.31)
    assert got[(d7, "q1")] == pytest.approx(12643.20 + 539.31)
    assert got[(d7, "q2")] == "N 85°45'25\" E"
    assert got[(d7, "q3")] == pytest.approx(6247.73 - 0.039 * 200)
    assert got[(d7, "q4")] == 10.0
    assert got[(d7, "q5")] == pytest.approx(round(6247.73 - 0.039 * (12643.20 - 12350.0), 2))
    assert got[(d7, "q6")] == pytest.approx(70.91 - 58.91)
    az = math.radians(180.0 - (44 + 46 / 60 + 51 / 3600))
    assert got[(d12, "q1")] == pytest.approx(round(937944.7494 - 250.0 * math.cos(az), 2))
    assert got[(d12, "q2")] == pytest.approx(round(544237.5831 - 250.0 * math.sin(az), 2))
    assert got[(d12, "q3")] == ("01°06'20\"", "R")
    assert got[(d12, "q4")] == pytest.approx(6273.16 + 0.0096 * 50)
    assert got[(d12, "q5")] == 50.0 and got[(d12, "q6")] == pytest.approx(21.0)
    # the radius from L-39's table: L and T agree on 3281 to the foot, against the lettered 3,280'
    delta = math.radians(2 + 57 / 60 + 6 / 3600)
    assert round(84.52 / math.tan(delta / 2)) == round(169.01 / delta) == 3281


@pytest.mark.parametrize("pid, answers, bad", [
    # other spellings of the right answers pass
    ("p15-plan-reading-fdot916", {"q1": "STA. 705+70.72", "q4": "564 ft", "q5": "N30-00-32E",
                                  "q6": "RT"}, None),
    ("p15-plan-reading-ppm052", {"q3": "2°57'06\" left", "q4": "1:1200", "q5": "R = 3,281'"}, None),
    ("p15-plan-reading-ppm049", {"q4": "229.49 ft", "q5": "100 ft per inch"}, None),
    ("p15-plan-reading-wflp16", {"q3": "El. 6,239.93", "q4": "1 in = 10 ft"}, None),
    ("p15-plan-reading-wflp21", {"q1": "938122.20", "q2": "544,061.48", "q3": "1°06'20\" R"},
     None),
    # the naive answers fail
    ("p15-plan-reading-fdot916", {"q1": "706+70.72"}, "q1"),          # the hundreds after it
    ("p15-plan-reading-fdot916", {"q3": "87 ft"}, "q3"),              # P-101's pipe length
    ("p15-plan-reading-fdot916", {"q4": "617 LF"}, "q4"),             # the 24" pipe counted too
    ("p15-plan-reading-fdot916", {"q5": "S 30°00'32\" W"}, "q5"),     # Rt to Lt
    ("p15-plan-reading-fdot916", {"q6": "Left"}, "q6"),
    ("p15-plan-reading-ppm052", {"q4": "1\" = 50'"}, "q4"),           # the full-size scale
    ("p15-plan-reading-ppm052", {"q5": "3280 ft"}, "q5"),             # the table's rounding
    ("p15-plan-reading-ppm052", {"q6": "453.29'"}, "q6"),             # the lettered length
    ("p15-plan-reading-ppm052", {"q3": "02°57'06\" RT"}, "q3"),
    ("p15-plan-reading-ppm049", {"q1": "225.61 ft"}, "q1"),           # the left bridge
    ("p15-plan-reading-ppm049", {"q2": "671+26.12"}, "q2"),           # EC - T
    ("p15-plan-reading-ppm049", {"q4": "225.59 ft"}, "q4"),           # the station difference
    ("p15-plan-reading-ppm049", {"q4": "221.7 ft"}, "q4"),            # the inside of the curve
    ("p15-plan-reading-ppm049", {"q5": "1\" = 50'"}, "q5"),
    ("p15-plan-reading-wflp16", {"q1": "131+98.86"}, "q1"),           # PI + T
    ("p15-plan-reading-wflp16", {"q2": "N 85°45'24\" E"}, "q2"),      # the next sheet's rounding
    ("p15-plan-reading-wflp16", {"q2": "N 17°50'41\" E"}, "q2"),      # the delta taken off
    ("p15-plan-reading-wflp16", {"q3": "6255.53"}, "q3"),             # the minus missed
    ("p15-plan-reading-wflp16", {"q3": "6247.73"}, "q3"),             # the VPI's own
    ("p15-plan-reading-wflp16", {"q4": "1\" = 50'"}, "q4"),           # the plan's
    ("p15-plan-reading-wflp16", {"q5": "6259.16"}, "q5"),
    ("p15-plan-reading-wflp21", {"q1": "938118.77"}, "q1"),           # back on S45°53'11"E
    ("p15-plan-reading-wflp21", {"q2": "544058.09"}, "q2"),
    ("p15-plan-reading-wflp21", {"q3": "01°06'20\" LT"}, "q3"),
    ("p15-plan-reading-wflp21", {"q6": "30.00 ft"}, "q6"),            # the PI's 15.00' each side
])
def test_later_reading_answers(starts, pid, answers, bad):
    spec, probe = _spec(pid), BY_ID[pid]
    base, work = _fresh(starts[pid]), _fresh(starts[pid])
    common.ok(work.execute("set_meta", {"updates": dict(spec.answers, **answers)}))
    result = probe.check(base, work)
    assert result.passed is (bad is None), result.detail
    if bad:
        failed = [item for item, done in result.items if not done]
        assert len(failed) == 1 and failed[0].startswith(bad), failed


def test_later_prompts_leak_no_answers():
    for pid in NEW_READINGS:
        spec, prompt = _spec(pid), BY_ID[pid].prompt
        src = scans.Sources(spec.sheet)
        for q in spec.questions:
            want = q.truth(src)
            if isinstance(want, float) and q.kind == "station":
                assert scans._sta(want) not in prompt, (pid, q.key)
            elif isinstance(want, float):       # as a number of its own, not in 163+50.00
                assert not re.search(rf"(?<![\d.+]){want:.{q.places}f}(?!\d)", prompt), \
                    (pid, q.key)
            elif isinstance(want, tuple):
                assert want[0] not in prompt, (pid, q.key)
            elif q.kind == "bearing":           # the format example's N 12°34'56" E aside
                assert not any(nt.azimuth_close(a, scans._azimuth(want), either_way=True)
                               for a in nt.bearings(prompt)), (pid, q.key)


# ------------------------------------------------------------------ the vague level


def _tools_named(text, allowed=("set_meta",)):
    """The tool names a brief mentions: every tool the server can offer (view_attachment
    too), as a word of its own; "area" is the plain word, not a hint."""
    from roaddraft.mcp.server import tool_definitions
    names = [t["name"] for t in tool_definitions(Session(), attachments=True)]
    return [n for n in names if n not in allowed and n != "area"
            and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I)]


#: what each redraw's vague brief must keep beyond its file, scan and line name: the line it
#: ties to, the stretch, and the datum point the survey gave
REDRAW_KEEPS = {
    "p01-redraw-alignment-ppm045": ['"TB1"', "D13", "layout sheet L-1"],
    "p01-redraw-alignment-fdot915": ["700+00.00", "SR 30", "end of the curve", "local datum",
                                     "N 9820.83, E 10300.67", "sheet 12"],
    "p01-redraw-alignment-ppm050": ['"F6"', "FR", "layout sheet L-7"],
    "p01-redraw-alignment-cflpnp": ["Begin Project", "25+00.00", "local datum",
                                    "PI of the second curve", "N 10486.51, E 9889.59", "Plan 1"],
    "p01-redraw-alignment-wfl20": ["160+00.00", "D.10", "local datum", '"APPR 01" 610+00.00',
                                   "N 10090.40, E 10058.92", "equation", "sheet D.11"],
}


@pytest.mark.parametrize("pid", REDRAW_IDS + READING_IDS)
def test_vague_brief_is_shorter_and_names_no_tool_hint(pid):
    p, spec = BY_ID[pid], _spec(pid)
    assert p.vague.strip() and p.vague != p.prompt and len(p.vague) < len(p.prompt)
    assert p.vague_check is None                 # the checks grade no drafting convention
    assert "view_attachment" in p.prompt and not _tools_named(p.vague), _tools_named(p.vague)
    assert spec.scan in p.vague
    # the selftest's levels: the vague brief is what the vague task is posed with
    from roaddraft.probes import prompting
    assert p.vague in prompting.task_text(p, "vague") and p.prompt not in prompting.task_text(p, "vague")


@pytest.mark.parametrize("pid", REDRAW_IDS)
def test_vague_redraw_keeps_the_data(pid):
    p, spec = BY_ID[pid], _spec(pid)
    assert spec.design_file in p.vague and f"name it {spec.alignment} and draw it" in p.vague
    assert "set_meta" not in p.vague
    for keep in REDRAW_KEEPS[pid]:
        assert keep in p.vague, keep
    # every station and coordinate the explicit brief gives, the vague one gives too
    for sta in re.findall(r"\d+\+\d\d\.\d\d", p.prompt):
        assert sta in p.vague, sta
    for ne in re.findall(r"N [\d.]+, E [\d.]+", p.prompt):
        assert ne in p.vague, ne
    # and nothing the check grades: no curve point station, delta or bearing
    for c in spec.curves:
        assert scans._sta(c.pc) not in p.vague and scans._sta(c.pt) not in p.vague
        assert c.delta not in p.vague
    assert not nt.bearings(p.vague), p.vague
    # the enumeration of what to read off the sheet, and the tool hints, are gone
    assert "region" not in p.vague and "curve data" not in p.vague


@pytest.mark.parametrize("pid", READING_IDS)
def test_vague_reading_keeps_every_question_and_the_answer_form(pid):
    p, spec = BY_ID[pid], _spec(pid)
    for q in spec.questions:
        assert f"{q.key}: {q.ask}" in p.vague, q.key
    keys = [q.key for q in spec.questions]
    assert keys == [f"q{i}" for i in range(1, len(keys) + 1)]
    assert f"set_meta under its key, q1 to q{len(keys)}, the value alone" in p.vague
    assert ("stations as 123+45.67, bearings as N 12°34'56\" E, lengths in feet"
            in p.vague)
    # the answers stay out of it, as they do out of the explicit brief
    src = scans.Sources(spec.sheet)
    for q in spec.questions:
        want = q.truth(src)
        if isinstance(want, float) and q.kind == "station":
            assert scans._sta(want) not in p.vague, q.key
        elif isinstance(want, float):
            assert not re.search(rf"(?<![\d.+]){want:.{q.places}f}(?!\d)", p.vague), q.key
        elif isinstance(want, tuple):
            assert want[0] not in p.vague, q.key
        elif q.kind == "bearing":
            assert not any(nt.azimuth_close(a, scans._azimuth(want), either_way=True)
                           for a in nt.bearings(p.vague)), q.key
