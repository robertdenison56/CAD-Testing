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
    assert worst < 0.3, worst
    for c in spec.curves:
        el = truth.curves()[0]
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
