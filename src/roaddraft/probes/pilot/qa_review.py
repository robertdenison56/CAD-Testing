"""Pilot 14: an open-ended QA review of a real plan sheet, errors unknown in number.

The ``qa-alignment-data`` probe (tier3) hands the model five errors on the
synthetic SR-100 sheets, says what kind of thing to check, and asks for them
FIXED. A checker's real job is different: a finished sheet comes back from
drafting, nobody says what is wrong with it or whether anything is, and the
checker marks it up for the drafter -- red callouts, nothing fixed. What makes
that hard is the open end. A model has to decide what on the sheet can be
checked against the design (bearings, distances, stations, curve data, curve
points, the north arrow against the viewport twist, lettering that reads
upside down), check all of it on a busy real sheet seen through a twisted
viewport, and then stop: a clean sheet must come back called clean, and a
model that marks everything it is unsure of fails on false alarms.

Three instances, on two real sheets, the prompt never saying how many errors:

* ``p14-qa-review-ppm045a`` -- Caltrans PPM example L-1 (Route 65, 1" = 50',
  twist -89.94 deg, "D13", "TB2" and "TB1" lines). The CONTROL: no plants.
* ``p14-qa-review-ppm045b`` -- the same sheet with six plants of six kinds:
  a bearing with its quadrant flipped (E for W), a curve-table L with two
  digits transposed, an EC station 100 ft off, an EC lettered BC, the north
  arrow turned 180 deg, and a label turned upside down.
* ``p14-qa-review-wfl19`` -- WFL plan-and-profile sheet D.10 (MAIN 01, one
  81 deg curve, 1" = 50', no twist) with three: the curve's Δ lettered (LT)
  on a curve that turns right, the PT station 100 ft off, and the north arrow
  left turned 39.78 deg off north on an untwisted viewport.

**The sheets had to be made consistent first.** The redrafts were rebuilt
from the published PDFs, and the published examples disagree with their own
geometry here and there (L-1's curve table gives R 835' with T 712.07' and L
1424.72', which no Δ satisfies; its bearings and lengths are a few seconds and
hundredths off the rebuilt lines, and two of them were digitised as strokes,
not text; D.10's design held only the part of its curve inside the window and
its north arrow disagreed with the untwisted viewport). A "plant" is only
unambiguous on a sheet whose unplanted content agrees with the design, so the
start builders normalise each sheet before planting, in the real sheet's own
places and styles (``prepare_ppm045``, ``prepare_wfl19``, shared with pilot 2):

* L-1: "TB2" and "TB1" are made tangent at their curve points (the redraft's
  fitted elements met their tangents at 1'47" and 18" kinks): TB1 rebuilt from
  PIs, TB2's curve recomputed in place because the line begins on it at the
  sheet's edge; both redrawn. Every bearing, tangent length, curve-table row,
  BC/EC station and POT callout is relettered from that design to the
  hundredth (R too: the published whole-foot R would disagree with the
  rebuilt radii). Leftovers of the digitising that a checker would fairly
  query go: the two labels drawn as strokes (N 01°05'14" W, 328.15') and a
  doubled pair of quotes become text or vanish, "Orchard Creek" in seven
  overlapping pieces becomes one text, an 8' lettered over a 12' drops clear,
  and the empty curve bubbles get their numbers. The construction callouts
  (fence, MBGR, ESA notes) and the lane and shoulder widths are out of scope:
  the redraft aimed several callouts at the element the published leader
  touched rather than at the station they state, and the widths are traced
  linework with no design behind them, so the prompt says they were checked
  separately.
* D.10: MAIN 01 is rebuilt as the whole curve its curve data describes (PI
  149+35.83, Δ 81°35'22", R 643.00', T 554.92', L 915.64', PT 152+96.54) on
  the redraft's own arc and stationing -- Δ carries 0.4" more than lettered so
  L rounds to the lettered 915.64; its PC lands on 143+80.91, the PC sheet D.9
  letters. The station numbers 149 to 152 and the PT label, which read top to
  bottom, are turned to read up; "E dges of pavement" becomes one word; and
  the north arrow is turned to the untwisted viewport's north and dropped a
  quarter inch off the border. The profile is out of scope (no profile design
  is in the files).

**Grading** reads only the documents. A QA mark is a leader on layer
QA-REVIEW (paper or the sheet file's model space) with a text at its other
end; its tip is the leader's free end farthest from the text. A cloud or
circle on QA-REVIEW counts as a mark around what it encloses. Each plant is
one item: found when a mark's tip lies within 0.5 in on paper of the planted
item as plotted (its text box, or the north arrow's linework). 0.5 in is
25 ft at 1" = 50': a leader set beside a label, not on it, still finds it,
while no two plants on a sheet lie within 2 in of each other, so one mark
cannot claim two. A mark that lands on no plant is a false alarm; one is
allowed on a sheet with errors (a checker's defensible query should not sink
the review), more fail it. The control passes only with no marks at all and a
NO ERRORS FOUND text on QA-REVIEW. On every instance nothing outside
QA-REVIEW may change, in the sheet file or its base files.
"""
from __future__ import annotations

import atexit
import math
import re
import shutil
from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.core.units import format_station
from roaddraft.document.entities import Circle, Line, Polyline, Text
from roaddraft.document.fileformat import read_document
from roaddraft.document.references import reference_groups
from roaddraft.verify.legibility import reads_upside_down
from roaddraft.probes import fixture
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common as c

QA_LAYER = "QA-REVIEW"
CLEAN_TEXT = "NO ERRORS FOUND"
#: how far a QA leader tip may land from a planted item, paper inches (25 ft at 1" = 50')
REACH_IN = 0.5
#: marks that land on no plant, allowed on a sheet that has errors
FALSE_ALARMS = 1
#: how near a leader's end must come to a QA text to be that text's callout (paper inches)
ATTACH_IN = 0.3
#: a closed shape smaller than this is an arrowhead, not a cloud (paper inches)
CLOUD_MIN_IN = 0.25


# ----------------------------------------------------------------- small helpers


def _ok(r: dict) -> dict:
    return c.ok(r)


def _u(deg: float) -> Tuple[float, float]:
    return math.cos(math.radians(deg)), math.sin(math.radians(deg))


def _add(p, d, k: float) -> List[float]:
    return [p[0] + d[0] * k, p[1] + d[1] * k]


def _ft(v: float) -> str:
    """A length the way both sheets letter it: 426.42’."""
    return f"{v:.2f}’"


def _dms(deg: float, width: int = 2) -> str:
    """Δ the way L-1's curve table letters it: 02°53’14\"."""
    total = int(round(abs(deg) * 3600.0))
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d:0{width}d}°{m:02d}’{s:02d}\""


def _bearing(b: str) -> str:
    """The engine's N 04°56'41\" E in L-1's lettering (’ for minutes)."""
    return b.replace("'", "’")


def _rows(session: Session, kind: str, alignment: str) -> List[dict]:
    return _ok(session.query("get_design_data", {"kind": kind, "alignment": alignment}))["rows"]


def _anchor(session: Session, alignment: str, ref: str) -> dict:
    return next(r for r in _rows(session, "anchors", alignment) if r["ref"] == ref)


def _expect(entity, content: str, where: str) -> None:
    """The redraft text a builder edits must still read what it was built for."""
    got = getattr(entity, "content", None)
    if got != content:
        raise RuntimeError(f"{where}: expected {content!r}, the redraft has {got!r} "
                           f"(was the redraft rebuilt? update the pilot)")


def _sheet(session: Session):
    return next(iter(session.doc.sheets.values()))


def _within(points, box) -> bool:
    x0, y0, x1, y1 = box
    return bool(points) and all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in points)


def _points(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [list(e.start), list(e.end)]
    if isinstance(e, Polyline):
        return [list(v) for v in e.vertices]
    if isinstance(e, Text):
        return [list(e.position)]
    if isinstance(e, Circle):
        return [list(e.center)]
    d = e.to_dict()
    loops = d.get("loops") or d.get("boundaries") or []
    out = []
    for loop in loops:
        verts = loop.get("vertices") if isinstance(loop, dict) else loop
        out += [list(v) for v in verts or [] if isinstance(v, (list, tuple)) and len(v) >= 2]
    return out


def _turn_text(session: Session, eid: str) -> None:
    """Turn a text half round about its own centre: same place, reading the other way."""
    e = session.doc.find_entity(eid)[1]
    box = pl.PText(e.content, list(e.position), float(e.rotation_deg), float(e.height),
                   e.halign, e.valign)
    _ok(session.execute("rotate_entities", {"ids": [eid], "base": box.center(), "angle": 180.0}))


def _to_model(sheet_session: Session, sheet: str, p) -> List[float]:
    r = _ok(sheet_session.query("sheet_to_model", {"sheet": sheet, "point": list(p)}))
    return list(r.get("model_point") or r.get("point"))


def _to_paper(sheet_session: Session, sheet: str, p) -> List[float]:
    r = _ok(sheet_session.query("model_to_sheet", {"sheet": sheet, "point": list(p)}))
    return list(r.get("sheet_point") or r.get("point"))


# ------------------------------------------------------- L-1 (PPM-045), made consistent

PPM = "PPM-045"
PPM_SHEET = "L-1"
PPM_FILE = "0000000000ea001.rdraft"
PPM_AA01 = "0000000000aa01.rdraft"
PPM_BB01 = "0000000000bb01.rdraft"

#: the published lettering the builder relettered, as the redraft has it (id -> text)
PPM_AA01_TEXT = {"TX-029": 'N 00°03’30" E', "TX-031": 'N 04°56’15" E', "TX-036": 'N 03°57’06" W'}
PPM_SHEET_TEXT = {
    "TX-084": "426.51’", "TX-096": "417.16’", "TX-030": "2470.24’",
    "TX-008": "835’", "TX-006": '29°05’15"', "TX-009": "712.07’", "TX-010": "1424.72’",
    "TX-002": "3280’", "TX-003": '02°51’52"', "TX-004": "82.03’", "TX-005": "164.02’",
    "TX-126": '"TB2" 639+92.66 EC', "TX-127": '"TB1" 644+45.25 EC', "TX-128": '"TB1" 642+81.23 BC',
    "TX-122": '"TB2" 644+19.17 POT=\n63.32’ Lt "D13" 644+19.17 POT',
    "TX-115": '"TB1" 647+73.40 POT=\n63.32’ Rt "D13" 647+73.40 POT',
    "TX-031": "ROUTE 65",
}
#: the stroked labels, their layers and the creek's pieces: repairs.py (applied at staging)
from roaddraft.probes.pilot.repairs import PPM_CREEK, PPM_STROKES, PPM_STROKE_LAYERS  # noqa: E402
#: where the north arrow sits on L-1 (S-ANNO-SYMB lines and polylines)
PPM_NORTH_BOX = (20.0, 18.3, 24.0, 19.3)
PPM_BUBBLES = {"PL-004": "1", "PL-005": "2"}


def _rebuild_from_elements(aa: Session) -> None:
    """Make "TB2" and "TB1" tangent at their curve points. The redraft fitted
    their elements to the plotted ticks, and the fit left each curve meeting
    its tangents at a kink (1'47" at TB2's EC, 18" at both ends of TB1's
    curve), so a curve's own bearings disagree with the tangents beside it.

    TB2 begins on its curve at the sheet's edge, which a PI-defined line cannot
    do, so its curve element is recomputed in place: the same radius, Δ and
    EC (station and point), ending on the tangent's bearing. TB1 is rebuilt
    from PIs where its two tangents meet, with the redraft's radius and ends.
    The curve points move by less than 1 ft."""
    from roaddraft.design.horizontal import Alignment
    tb2 = aa.doc.design.alignments["TB2"].to_dict()
    curve, tangent = tb2["elements"]
    R, delta = float(curve["radius"]), float(curve["delta_deg"])
    out_dir = float(tangent["direction_deg"])
    in_dir = out_dir - delta                            # a curve left turns counter-clockwise
    T = R * math.tan(math.radians(delta / 2.0))
    L = R * math.radians(delta)
    pt = list(tangent["start"])
    centre = _add(pt, _u(out_dir + 90.0), R)
    pc = _add(centre, _u(in_dir - 90.0), R)
    pt_station = float(tb2["begin_station"]) + float(curve["length"])
    curve.update({"pc": pc, "pt": pt, "pi": _add(pt, _u(out_dir), -T), "center": centre,
                  "radius": R, "delta_deg": delta, "direction": "L", "length": L, "start_dist": 0.0,
                  "direction_in_deg": in_dir % 360.0, "direction_out_deg": out_dir % 360.0})
    tangent["start_dist"] = L
    tb2["begin_station"] = pt_station - L
    aa.doc.design.alignments["TB2"] = Alignment.from_dict(tb2)
    _ok(aa.execute("draw_alignment", {"alignment": "TB2", "layer": "V-ALIGN-CNTR", "replace": True}))
    tb1 = aa.doc.design.alignments["TB1"].to_dict()
    t1, curve, t2 = tb1["elements"]
    p1, d1 = t1["start"], _u(t1["direction_deg"])
    p2, d2 = t2["end"], _u(t2["direction_deg"])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    k = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    pi = _add(p1, d1, k)
    _ok(aa.execute("modify_alignment", {"name": "TB1", "redraw": True, "changes": {
        "pis": [list(p1), pi + [float(curve["radius"])], list(p2)]}}))


def ppm045_values(aa: Session) -> Dict[str, str]:
    """L-1's alignment lettering as the (rebuilt) design gives it."""
    v: Dict[str, str] = {}
    for name in ("D13", "TB2", "TB1"):
        for t in _rows(aa, "tangents", name):
            v[f"{name} {t['ref']} bearing"] = _bearing(t["bearing"])
            v[f"{name} {t['ref']} length"] = _ft(t["length"])
        for cv in _rows(aa, "curves", name):
            v[f"{name} {cv['ref']} R"] = _ft(cv["radius"])
            v[f"{name} {cv['ref']} delta"] = _dms(cv["delta_deg"])
            v[f"{name} {cv['ref']} T"] = _ft(cv["tangent"])
            v[f"{name} {cv['ref']} L"] = _ft(cv["length"])
            v[f"{name} {cv['ref']} PC"] = cv["pc_station_text"]
            v[f"{name} {cv['ref']} PT"] = cv["pt_station_text"]
    for name, side in (("TB2", "Lt"), ("TB1", "Rt")):
        end = _anchor(aa, name, "END")
        d13 = _ok(aa.query("xy_to_station", {"alignment": "D13", "point": end["point"]}))
        v[f"{name} POT"] = (f'"{name}" {end["station_text"]} POT=\n{abs(d13["offset"]):.2f}’ '
                            f'{side} "D13" {format_station(d13["station"])} POT')
    return v


def prepare_ppm045(out: Path) -> Path:
    """Stage L-1 and make its alignment data agree with its design (see the
    module docstring); returns the sheet file."""
    out = Path(out)
    c.stage(out, PPM)
    s = c.load(out / PPM_FILE)
    sheet = _sheet(s)
    aa = c.load(out / PPM_AA01)
    for eid, text in PPM_AA01_TEXT.items():
        _expect(aa.doc.model_entities.get(eid), text, f"AA01 {eid}")
    for eid, text in PPM_SHEET_TEXT.items():
        _expect(sheet.entities.get(eid), text, f"L-1 {eid}")
    _rebuild_from_elements(aa)
    v = ppm045_values(aa)
    for eid, key in (("TX-029", "D13 T-1 bearing"), ("TX-031", "TB2 T-1 bearing"),
                     ("TX-036", "TB1 T-1 bearing")):
        _ok(aa.execute("modify_entity", {"id": eid, "changes": {"content": v[key]}}))
    # TB1's two stroked labels went at staging (repairs.py); their values come back as text
    t2 = next(t for t in _rows(aa, "tangents", "TB1") if t["ref"] == "T-2")
    # where the strokes began, lifted clear of the station ticks (4.5 ft left of the line)
    at = _ok(aa.query("xy_to_station", {"alignment": "TB1",
                                        "point": _to_model(s, PPM_SHEET, (16.33, 8.13))}))
    spot = _ok(aa.query("station_to_xy", {"alignment": "TB1", "station": at["station"],
                                          "offset": -4.5}))
    _ok(aa.execute("place_text", {"space": "model", "layer": "V-ANNO-ALGN",
                                  "position": list(spot.get("point") or spot.get("xy")),
                                  "rotation_deg": float(t2["direction_deg"]), "height": 7.0,
                                  "content": v["TB1 T-2 bearing"]}))
    c.save(aa, out / PPM_AA01)
    # the sheet, reading the rebuilt design through its reference
    s = c.load(out / PPM_FILE)
    sheet = _sheet(s)
    twist = float(sheet.viewports[0].rotation_deg)
    for eid, key in (("TX-084", "TB2 T-1 length"), ("TX-096", "TB1 T-1 length"),
                     ("TX-030", "D13 T-1 length"),
                     ("TX-008", "TB2 C-1 R"), ("TX-006", "TB2 C-1 delta"), ("TX-009", "TB2 C-1 T"),
                     ("TX-010", "TB2 C-1 L"),
                     ("TX-002", "TB1 C-1 R"), ("TX-003", "TB1 C-1 delta"), ("TX-004", "TB1 C-1 T"),
                     ("TX-005", "TB1 C-1 L")):
        _ok(s.execute("modify_entity", {"id": eid, "changes": {"content": v[key]}}))
    _ok(s.execute("place_text", {"space": PPM_SHEET, "layer": "S-ANNO-NOTE", "position": [21.22, 8.27],
                                 "rotation_deg": float(t2["direction_deg"]) + twist, "height": 0.14,
                                 "content": v["TB1 T-2 length"]}))
    for eid, text in (("TX-126", f'"TB2" {v["TB2 C-1 PT"]} EC'), ("TX-127", f'"TB1" {v["TB1 C-1 PT"]} EC'),
                      ("TX-128", f'"TB1" {v["TB1 C-1 PC"]} BC'), ("TX-122", v["TB2 POT"]),
                      ("TX-115", v["TB1 POT"])):
        _ok(s.execute("modify_entity", {"id": eid, "changes": {"content": text}}))
    _reaim_curve_points(s)
    for pid, number in PPM_BUBBLES.items():
        verts = sheet.entities[pid].vertices
        centre = [sum(p[0] for p in verts) / len(verts), sum(p[1] for p in verts) / len(verts)]
        _ok(s.execute("place_text", {"space": PPM_SHEET, "layer": "S-ANNO-TAG", "position": centre,
                                     "height": 0.12, "halign": "center", "valign": "middle",
                                     "content": number}))
    return c.save(s, out / PPM_FILE)


def _reaim_curve_points(s: Session) -> None:
    """The BC/EC callouts' leader ends moved onto the rebuilt curve points."""
    sheet = _sheet(s)
    for name, ref in (("TB2", "PT-1"), ("TB1", "PC-1"), ("TB1", "PT-1")):
        a = _anchor(s, f"AA01:{name}", ref)
        q = _ok(s.query("station_to_xy", {"alignment": f"AA01:{name}", "station": a["station"],
                                          "sheet": PPM_SHEET}))["on_sheet"]["sheet_point"]
        best = None
        for e in sheet.entities.values():
            if e.layer == "S-ANNO-CALL" and isinstance(e, Line):
                for end in ("start", "end"):
                    d = math.dist(getattr(e, end), q)
                    if best is None or d < best[0]:
                        best = (d, e, end)
        if best is not None and 1e-4 < best[0] < 0.1:
            _ok(s.execute("modify_entity", {"id": best[1].id, "changes": {best[2]: list(q)}}))


# ------------------------------------------------------- D.10 (WFL p19), made consistent

WFL = "WFL-Plan-Profile-Sheets-p19"
WFL_SHEET = "D.10"
WFL_FILE = "SamplePlan_pln_pp6.rdraft"
WFL_ALI = "SamplePlan_ali.rdraft"
WFL_COR = "SamplePlan_cor.rdraft"
WFL_ALIGN = "MAIN 01"
#: the curve data D.10 letters, which the rebuilt design reproduces to the hundredth: with
#: Δ 81°35'22" flat, L is 915.6349 and letters 915.63, so Δ carries 0.4" more (still 22")
WFL_CURVE = {"pi": 14935.826, "delta_dms": (81, 35, 22.4), "radius": 643.0, "pt": "152+96.54"}
WFL_SHEET_TEXT = {"TX-045": "PI 149+35.83", "TX-043": 'Δ = 81°35\'22" (RT)', "TX-042": "R = 643.00'",
                  "TX-040": "T = 554.92'", "TX-039": "L = 915.64'", "TX-051": "PT 152+96.54",
                  "TX-048": "N"}
#: the north arrow: the sheet's N, and its shapes, which the redraft put in the corridor file
WFL_NORTH_SHEET = ["TX-048"]
WFL_NORTH_COR = ["LN-002", "LN-003", "HT-001", "HT-002", "HT-003", "HT-004",
                 "PL-003", "PL-004", "PL-005", "PL-006"]
#: how far D.10's arrow is turned off the untwisted viewport's north (the published N's rotation)
WFL_NORTH_TURN = 39.78
WFL_NORTH_DROP_IN = 0.25
#: the pavement edges: the redraft drew them 15.00 ft either side of the centerline
WFL_EDGES = {"PL-261": 15.0, "PL-262": -15.0}


def wfl19_pis(radius: float = WFL_CURVE["radius"]) -> Tuple[list, float]:
    """MAIN 01 as the whole curve D.10's curve data describes, ``(pis, begin
    station)``, on the redraft's own arc (its centre, and the stationing its
    ticks were fitted to): the redraft held only the part of the curve inside
    the viewport. ``radius`` other than 643 keeps the PIs and changes the curve
    (pilot 2 plants one)."""
    ali = c.document(c.folder(WFL) / WFL_ALI)
    el = ali.design.alignments[WFL_ALIGN].to_dict()
    arc = el["elements"][0]
    centre, begin = arc["center"], float(el["begin_station"])
    R = WFL_CURVE["radius"]
    d, m, s = WFL_CURVE["delta_dms"]
    delta = d + m / 60.0 + s / 3600.0
    T = R * math.tan(math.radians(delta / 2.0))
    L = R * math.radians(delta)
    pt_station = WFL_CURVE["pi"] - T + L
    pc_station = pt_station - L
    a0 = math.degrees(math.atan2(arc["pc"][1] - centre[1], arc["pc"][0] - centre[0]))
    # a curve right runs clockwise round its centre: back along it is counter-clockwise
    a_pc = a0 + math.degrees((begin - pc_station) / R)
    pc = [centre[0] + R * math.cos(math.radians(a_pc)), centre[1] + R * math.sin(math.radians(a_pc))]
    dir_in = a_pc - 90.0
    pi = _add(pc, _u(dir_in), T)
    dir_out = dir_in - delta
    back, ahead = 200.0, 150.0
    start = _add(pc, _u(dir_in), -back)
    end = _add(pi, _u(dir_out), T + ahead)
    return [start, pi + [radius], end], pc_station - back


def prepare_wfl19(out: Path, north: bool = True) -> Path:
    """Stage D.10 and make it agree with its design: MAIN 01 rebuilt as the whole
    curve its curve data describes, and (``north``) the north arrow turned to
    the untwisted viewport's north. Returns the sheet file."""
    out = Path(out)
    c.stage(out, WFL)
    s = c.load(out / WFL_FILE)
    sheet = _sheet(s)
    for eid, text in WFL_SHEET_TEXT.items():
        _expect(sheet.entities.get(eid), text, f"D.10 {eid}")
    ali = c.load(out / WFL_ALI)
    pis, begin = wfl19_pis()
    r = _ok(ali.execute("modify_alignment", {"name": WFL_ALIGN, "redraw": True,
                                             "changes": {"pis": pis, "begin_station": begin}}))
    if not r.get("deleted"):
        raise RuntimeError("D.10: the redraft's centerline was not redrawn from the rebuilt design")
    # station numbers past the top of the curve were lettered radially reading top to
    # bottom (upside down by the reading rule the verifier uses); turned to read up
    flips = [e.id for e in ali.doc.model_entities.values()
             if isinstance(e, Text) and e.layer == "P_ALIGN_STA" and reads_upside_down(e.rotation_deg)]
    for eid in flips:
        _turn_text(ali, eid)
    c.save(ali, out / WFL_ALI)
    if reads_upside_down(sheet.entities["TX-051"].rotation_deg):
        _turn_text(s, "TX-051")
    # "Edges of pavement" was digitised as an E and "dges of pavement" a space apart
    e, rest = sheet.entities["TX-046"], sheet.entities["TX-062"]
    _expect(e, "E", "D.10 TX-046")
    _expect(rest, "dges of pavement", "D.10 TX-062")
    _ok(s.execute("modify_entity", {"id": "TX-062", "changes": {
        "content": "Edges of pavement", "position": [e.position[0], rest.position[1]]}}))
    _ok(s.execute("delete_entities", {"ids": ["TX-046"]}))
    if north:
        cor = c.load(out / WFL_COR)
        found = [eid for eid in WFL_NORTH_COR if eid in cor.doc.model_entities]
        if len(found) != len(WFL_NORTH_COR):
            raise RuntimeError(f"D.10: north arrow shapes missing from the corridor file: {found}")
        pts = [p for eid in found for p in _points(cor.doc.model_entities[eid])]
        x0, y0, x1, y1 = geo.bbox_of_points(pts)
        centre = [(x0 + x1) / 2.0, (y0 + y1) / 2.0]
        _ok(cor.execute("rotate_entities", {"ids": found, "base": centre, "angle": -WFL_NORTH_TURN}))
        c.save(cor, out / WFL_COR)
        paper_centre = _to_paper(s, WFL_SHEET, centre)
        _ok(s.execute("rotate_entities", {"ids": WFL_NORTH_SHEET, "base": paper_centre,
                                          "angle": -WFL_NORTH_TURN}))
        # upright, the arrow's N would touch the border: the arrow drops a quarter inch
        _ok(cor.execute("move_entities", {"ids": found, "delta": [0.0, -WFL_NORTH_DROP_IN * 50.0]}))
        c.save(cor, out / WFL_COR)
        _ok(s.execute("move_entities", {"ids": WFL_NORTH_SHEET, "delta": [0.0, -WFL_NORTH_DROP_IN]}))
    return c.save(s, out / WFL_FILE)


# ------------------------------------------------------------------ the plants


def _modify_text(session: Session, eid: str, fn) -> None:
    e = session.doc.find_entity(eid)[1]
    _ok(session.execute("modify_entity", {"id": eid, "changes": {"content": fn(e.content)}}))


def _turn_about_centre(session: Session, sheet: str, ids: Sequence[str], angle: float) -> None:
    sh = session.doc.sheet_by_ref(sheet)
    pts = [p for eid in ids for p in _points(sh.entities[eid])]
    if any(isinstance(sh.entities[eid], Text) for eid in ids) and len(ids) == 1:
        t = pl.plot(session, sh, [(sh.id, sh.entities[ids[0]])]).texts[0]
        centre = t.center()
    else:
        x0, y0, x1, y1 = geo.bbox_of_points(pts)
        centre = [(x0 + x1) / 2.0, (y0 + y1) / 2.0]
    _ok(session.execute("rotate_entities", {"ids": list(ids), "base": centre, "angle": angle}))


def _transpose(value: str) -> str:
    """Swap the 2nd and 3rd digits of a lettered number: 163.42’ -> 136.42’."""
    digits = [i for i, ch in enumerate(value) if ch.isdigit()]
    i, j = digits[1], digits[2]
    chars = list(value)
    chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _plus100(text: str) -> str:
    m = re.search(r"(\d+)\+(\d{2}\.\d{2})", text)
    return text[:m.start()] + f"{int(m.group(1)) + 1}+{m.group(2)}" + text[m.end():]


def _ppm_north_ids(session: Session) -> List[str]:
    sh = session.doc.sheet_by_ref(PPM_SHEET)
    return sorted(e.id for e in sh.entities.values()
                  if e.layer == "S-ANNO-SYMB" and _within(_points(e), PPM_NORTH_BOX))


#: each plant: what it is, where it is (``sheet`` ids on the sheet, ``ref`` a base
#: file's ids seen through the viewport), and how the builder plants it
PPM_PLANTS = [
    {"what": "\"TB1\"'s first tangent lettered N 03°57’26\" E; the design bearing is N 03°57’26\" W",
     "item": "the TB1 bearing (quadrant flipped)", "ref": ("AA01", ["TX-036"])},
    {"what": "curve 2's L in the CURVE DATA table with two digits transposed (136.42’ for 163.42’)",
     "item": "curve 2's L in the curve table", "sheet": ["TX-005"]},
    {"what": "\"TB2\"'s EC lettered 640+92.73, 100 ft ahead of the EC at 639+92.73",
     "item": "the TB2 EC station (100 ft off)", "sheet": ["TX-126"]},
    {"what": "\"TB1\"'s EC at 644+44.35 lettered BC",
     "item": "the TB1 EC lettered BC", "sheet": ["TX-127"]},
    {"what": "the north arrow turned 180°: it points west on the paper; through the -89.94° "
             "viewport north is to the right",
     "item": "the north arrow (turned 180°)", "sheet": "north"},
    {"what": "ROUTE 65 lettered upside down",
     "item": "ROUTE 65 upside down", "sheet": ["TX-031"]},
]

WFL_PLANTS = [
    {"what": "the curve's Δ lettered 81°35'22\" (LT); MAIN 01 turns right",
     "item": "the curve direction (LT for RT)", "sheet": ["TX-043"]},
    {"what": "the PT lettered 151+96.54, 100 ft back of the PT at 152+96.54",
     "item": "the PT station (100 ft off)", "sheet": ["TX-051"]},
    {"what": "the north arrow turned 39.78° off north; the viewport is not twisted, so north is up",
     "item": "the north arrow (turned 39.78°)", "sheet": WFL_NORTH_SHEET, "ref": ("COR", WFL_NORTH_COR)},
]


def _build_ppm_clean(out: Path) -> Path:
    return prepare_ppm045(out)


def _build_ppm_planted(out: Path) -> Path:
    path = prepare_ppm045(out)
    aa = c.load(out / PPM_AA01)
    _modify_text(aa, "TX-036", lambda t: t[:-1] + ("E" if t.endswith("W") else "W"))
    c.save(aa, out / PPM_AA01)
    s = c.load(path)
    _modify_text(s, "TX-005", _transpose)
    _modify_text(s, "TX-126", _plus100)
    _modify_text(s, "TX-127", lambda t: re.sub(r"\bEC\b", "BC", t))
    _turn_about_centre(s, PPM_SHEET, _ppm_north_ids(s), 180.0)
    _turn_about_centre(s, PPM_SHEET, ["TX-031"], 180.0)
    return c.save(s, path)


def _build_wfl_planted(out: Path) -> Path:
    path = prepare_wfl19(out, north=False)          # the arrow stays as published: turned
    s = c.load(path)
    _modify_text(s, "TX-043", lambda t: t.replace("(RT)", "(LT)"))
    _modify_text(s, "TX-051", lambda t: re.sub(r"152\+", "151+", t))
    return c.save(s, path)


START_PPM_A = c.register("p14-ppm045a", PPM_FILE, _build_ppm_clean)
START_PPM_B = c.register("p14-ppm045b", PPM_FILE, _build_ppm_planted)
START_WFL = c.register("p14-wfl19", WFL_FILE, _build_wfl_planted)


# ------------------------------------------------------------- reading the marks


_BUILT_DIRS: List[str] = []


@atexit.register
def _forget_built() -> None:
    for folder in _BUILT_DIRS:
        shutil.rmtree(folder, ignore_errors=True)


@lru_cache(maxsize=None)
def _built(start: str) -> str:
    """A fresh copy of a start, built once per process: the check's reference
    for what the planted sheet and its base files are (read from the repo's
    redraft, never from the model's folder)."""
    folder = Path(tempfile.mkdtemp(prefix=f"roaddraft-{start}-"))
    _BUILT_DIRS.append(str(folder))
    fixture.start_document(folder, start)
    return str(folder / fixture.START[start])


def _ref_plot(session: Session, sheet, ref_name: str, ids: Sequence[str]) -> pl.Plot:
    """A base file's entities as they plot through the sheet's viewports."""
    out = pl.Plot(sheet=sheet)
    want = set(ids)
    for vp in sheet.viewports:
        fn, turn, k = vp.transform().to_paper, float(vp.rotation_deg), 1.0 / vp.feet_per_inch
        for ref, _base, prims in reference_groups(session.doc, "model"):
            if ref.name != ref_name:
                continue
            for e in prims:
                if e.id in want:
                    pl._add_prims(out, session.doc, [e.transformed(fn, turn, k)], e.id, "model")
    return out


def plant_marks(session: Session, plant: dict) -> Tuple[List[pl.PText], List[pl.PSeg]]:
    """Where a plant shows on the sheet: its text boxes and linework, in paper inches."""
    sheet = _sheet(session)
    texts: List[pl.PText] = []
    segs: List[pl.PSeg] = []
    ids = plant.get("sheet") or []
    if ids == "north":
        ids = _ppm_north_ids(session)
    if ids:
        view = pl.plot(session, sheet, [(sheet.id, sheet.entities[i]) for i in ids])
        texts += view.texts
        segs += view.segs
    if plant.get("ref"):
        name, rids = plant["ref"]
        view = _ref_plot(session, sheet, name, rids)
        texts += view.texts
        segs += view.segs
    if not texts and not segs:
        raise RuntimeError(f"plant {plant['item']!r} shows nothing on the sheet")
    return texts, segs


def _inside(poly, p) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > p[1]) != (y2 > p[1]):
            x = x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1)
            if x > p[0]:
                inside = not inside
    return inside


def _distance(marks, p) -> float:
    texts, segs = marks
    best = math.inf
    for t in texts:
        quad = t.corners()
        best = min(best, 0.0 if _inside(quad, p) else
                   min(geo.dist_point_to_segment(p, a, b) for a, b in zip(quad, quad[1:] + quad[:1])))
    for g in segs:
        best = min(best, g.distance(p))
    return best


def _components(segs: Sequence[pl.PSeg], snap: float = 0.01):
    nodes: List[List[float]] = []

    def nid(p):
        for i, q in enumerate(nodes):
            if math.dist(p, q) <= snap:
                return i
        nodes.append(list(p))
        return len(nodes) - 1

    edges = [(nid(g.a), nid(g.b)) for g in segs]
    parent = list(range(len(nodes)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    degree = [0] * len(nodes)
    for a, b in edges:
        if a != b:
            parent[find(a)] = find(b)
            degree[a] += 1
            degree[b] += 1
    groups: Dict[int, set] = {}
    for a, b in edges:
        groups.setdefault(find(a), set()).update((a, b))
    return [([nodes[i] for i in ids], [nodes[i] for i in ids if degree[i] == 1])
            for ids in groups.values()]


def qa_marks(baseline: Session, submitted: Session) -> Tuple[List[dict], List[pl.PText]]:
    """The QA marks added on layer QA-REVIEW, as they plot: ``(marks, texts)``.
    A mark is ``{"kind": "leader", "tip", "text"}`` or ``{"kind": "cloud",
    "poly"}``; ``texts`` are every QA-REVIEW text."""
    sheet = _sheet(submitted)
    items = [(space, e) for space, e in pl.sheet_items(baseline, submitted, sheet.name)
             if (e.layer or "").upper() == QA_LAYER]
    view = pl.plot(submitted, sheet, items)
    texts = view.texts
    marks: List[dict] = []
    open_segs = [g for g in view.segs if not g.closed]
    closed: Dict[str, List[pl.PSeg]] = {}
    for g in view.segs:
        if g.closed:
            closed.setdefault(g.source, []).append(g)
    def gap(p, t):
        return 0.0 if t.contains(p, 0.02) else min(math.dist(p, q) for q in t.corners() + [t.center()])

    def small(segs) -> bool:
        x0, y0, x1, y1 = geo.bbox_of_points([g.a for g in segs] + [g.b for g in segs])
        return math.hypot(x1 - x0, y1 - y0) < CLOUD_MIN_IN

    arrows = [g.a for segs in closed.values() if small(segs) for g in segs]
    for nodes, ends in _components(open_segs):
        ends = ends or nodes
        gaps = [min((gap(p, t) for t in texts), default=math.inf) for p in ends]
        if min(gaps) > ATTACH_IN:
            continue  # a line with no words at its end is not a callout
        # an arrowhead marks a tip outright; otherwise a tip is an end away from every text
        tips = [p for p in ends if any(math.dist(p, a) <= 0.01 for a in arrows)]
        rest = [(g, p) for p, g in zip(ends, gaps) if p not in tips]
        if not rest:
            continue
        home = min(rest)[1]
        text = min(texts, key=lambda t: gap(home, t))
        if not tips:
            tips = [p for g, p in rest if g > ATTACH_IN and p is not home] or [max(rest)[1]]
        for tip in tips:  # a callout with two leaders marks two things
            marks.append({"kind": "leader", "tip": tip, "text": text.content})
    shapes = [[g.a for g in segs] for segs in closed.values()]
    shapes += [[[ci.center[0] + ci.radius * math.cos(a), ci.center[1] + ci.radius * math.sin(a)]
                for a in [i * math.pi / 16 for i in range(32)]] for ci in view.circles]
    for poly in shapes:
        x0, y0, x1, y1 = geo.bbox_of_points(poly)
        if math.hypot(x1 - x0, y1 - y0) >= CLOUD_MIN_IN:
            marks.append({"kind": "cloud", "poly": poly})
    return marks, texts


def _hit(mark: dict, marks_of_plant) -> float:
    """How far a mark is from a plant (paper inches); 0 when it lands on it."""
    if mark["kind"] == "leader":
        return _distance(marks_of_plant, mark["tip"])
    texts, segs = marks_of_plant
    pts = [t.center() for t in texts] + [g.mid() for g in segs]
    poly = mark["poly"]
    if any(_inside(poly, p) for p in pts):
        return 0.0
    return min(geo.dist_point_to_segment(p, a, b) for p in pts for a, b in zip(poly, poly[1:] + poly[:1]))


# ----------------------------------------------------------- nothing else changed


def _doc_dict(path: Path) -> dict:
    return read_document(Path(path))


def _strip(d: dict) -> dict:
    return {k: d.get(k) for k in ("layers", "model_entities", "sheets", "references", "design", "blocks")}


def changed_outside(expected_path: Path, submitted: Session, allow_layer: Optional[str] = None,
                    allow_ids: Sequence[str] = (), allow_files: Sequence[str] = ()) -> Optional[str]:
    """What changed in the sheet file or its base files besides work on
    ``allow_layer`` (and the entities ``allow_ids`` of the sheet file, and the
    base files ``allow_files``), or None. ``expected_path`` is a fresh start."""
    expected_path = Path(expected_path)
    want = _strip(_doc_dict(expected_path))
    got = submitted.doc.to_dict()
    allow = (allow_layer or "").upper()

    def entities(d, key):
        return {e["id"]: e for e in (d.get(key) or [])} if isinstance(d.get(key), list) else dict(d.get(key) or {})

    def compare(old: dict, new: dict, where: str) -> Optional[str]:
        for eid, e in old.items():
            if eid in allow_ids:
                continue
            if eid not in new:
                return f"{where}: {e.get('type', 'entity')} {eid} was removed"
            if new[eid] != e:
                return f"{where}: {e.get('type', 'entity')} {eid} was changed"
        for eid, e in new.items():
            if eid not in old and (e.get("layer") or "").upper() != allow and eid not in allow_ids:
                return f"{where}: {e.get('type', 'entity')} {eid} was added on {e.get('layer')!r}"
        return None

    problem = compare(entities(want, "model_entities"), entities(got, "model_entities"),
                      "the sheet file's model")
    if problem:
        return problem
    old_sheets = entities(want, "sheets")
    new_sheets = entities(got, "sheets")
    for sid, sh in old_sheets.items():
        if sid not in new_sheets:
            return f"sheet {sh.get('name', sid)} was removed"
        nsh = new_sheets[sid]
        if sh.get("viewports") != nsh.get("viewports"):
            return f"sheet {sh.get('name', sid)}'s viewport was changed"
        problem = compare(entities(sh, "entities"), entities(nsh, "entities"),
                          f"sheet {sh.get('name', sid)}")
        if problem:
            return problem
    if want.get("references") != got.get("references"):
        return "the sheet's references were changed"
    if want.get("design") != got.get("design"):
        return "the sheet file's design was changed"
    home = Path(getattr(submitted.doc, "_path", "") or ".").parent
    for ref in (entities(want, "references") or {}).values():
        name = ref.get("path")
        if not name or name in allow_files:
            continue
        mine = home / name
        if not mine.exists():
            return f"base file {name} is missing"
        if _strip(_doc_dict(expected_path.parent / name)) != _strip(_doc_dict(mine)):
            return f"base file {name} was changed"
    return None


# ------------------------------------------------------------------ the check


def _check(start: str, plants: List[dict]):
    def check(baseline: Session, submitted: Session) -> Result:
        expected = Path(_built(start))
        truth = c.load(expected)
        marks, texts = qa_marks(truth, submitted)
        clean_said = [t for t in texts if CLEAN_TEXT in " ".join(t.content.upper().split())]
        tally = Tally()
        if not plants:
            tally.add("NO ERRORS FOUND on QA-REVIEW",
                      None if clean_said else "the clean sheet was not called clean: no "
                                              "NO ERRORS FOUND text on QA-REVIEW")
            tally.add("no error marked on the clean sheet",
                      None if not marks else f"{len(marks)} QA mark(s) on a sheet with no errors"
                      + _said(marks))
        else:
            if clean_said:
                tally.fail("NO ERRORS FOUND lettered on a sheet with errors")
            shapes = [plant_marks(truth, p) for p in plants]
            assigned: Dict[int, List[int]] = {}
            stray = []
            for k, mark in enumerate(marks):
                d = [(_hit(mark, sh), i) for i, sh in enumerate(shapes)]
                best = min(d)
                if best[0] <= REACH_IN:
                    assigned.setdefault(best[1], []).append(k)
                else:
                    stray.append(mark)
            for i, plant in enumerate(plants):
                if i in assigned:
                    tally.add(plant["item"], None)
                else:
                    near = min((_hit(m, shapes[i]) for m in marks), default=None)
                    tally.add(plant["item"], f"not marked: {plant['what']}"
                              + (f" (nearest QA mark {near:.2f} in away)" if near is not None else ""))
            if len(stray) > FALSE_ALARMS:
                tally.fail(f"{len(stray)} QA marks point at no planted error (allowed "
                           f"{FALSE_ALARMS})" + _said(stray))
        tally.fail(changed_outside(expected, submitted, allow_layer=QA_LAYER))
        good = ("called clean: NO ERRORS FOUND on QA-REVIEW and no marks" if not plants else
                f"all {len(plants)} errors marked on QA-REVIEW, at most {FALSE_ALARMS} false alarm, "
                f"nothing else changed")
        return tally.result(good)
    return check


def _said(marks: List[dict]) -> str:
    words = [m.get("text") for m in marks if m.get("text")]
    return (": " + "; ".join(repr(" ".join(w.split()))[:60] for w in words[:3])) if words else ""


# ------------------------------------------------------------------ the solutions


def _solve(plants: List[dict]):
    def solve(session: Session) -> None:
        sheet = _sheet(session)
        if QA_LAYER not in session.doc.layers:
            _ok(session.execute("create_layer", {"name": QA_LAYER, "color": "red"}))
        if not plants:
            _ok(session.execute("place_text", {"space": sheet.name, "layer": QA_LAYER,
                                               "position": [3.0, 2.0], "height": 0.14,
                                               "content": CLEAN_TEXT}))
            return
        for plant in plants:
            texts, segs = plant_marks(session, plant)
            target = texts[0].center() if texts else segs[len(segs) // 2].mid()
            x0, y0, x1, y1 = sheet.viewports[0].paper_bbox()
            side = 1.0 if target[0] < (x0 + x1) / 2.0 else -1.0
            pos = [target[0] + side * 1.2, target[1] + (0.9 if target[1] < (y0 + y1) / 2.0 else -0.9)]
            _ok(session.execute("place_callout", {
                "space": sheet.name, "layer": QA_LAYER, "target": target, "position": pos,
                "height": 0.10, "content": "QA: " + plant["item"].upper()}))
    return solve


PROMPT = ("Sheet {sheet} is back from drafting and needs checking before it goes out. Review "
          "the plan against the design -- the alignments in the base files the sheet references -- "
          "and check the drafting of the sheet itself. {scope}Mark every error you find with a "
          "callout on a layer named QA-REVIEW: the leader tip on the item that is wrong and a short "
          "note saying what is wrong. Do not fix anything, and change nothing else on the sheet or "
          "in the base files. If you find nothing wrong, place the single text NO ERRORS FOUND on "
          "QA-REVIEW instead.")
PPM_SCOPE = ("The construction notes and their callouts (fence, guardrail, ESA) and the lane "
             "and shoulder widths were checked separately; leave them out. ")
WFL_SCOPE = "Check the plan view only; the profile is checked separately. "

PROBES: List[Probe] = [
    Probe(id="p14-qa-review-ppm045a", start=START_PPM_A, tags=["pilot", "qa", "caltrans", "twist"],
          prompt=PROMPT.format(sheet="L-1", scope=PPM_SCOPE),
          check=_check(START_PPM_A, []), solve=_solve([]),
          note="The CONTROL: Caltrans L-1 with its alignment data made to agree with the rebuilt "
               "design and nothing planted. Passes only with NO ERRORS FOUND on QA-REVIEW and no "
               "QA marks. Naive wrong: flagging the sheet's own leftovers -- 'MATCH LINE' with no "
               "sheet number, the curve table's R lettered to the hundredth -- or calling the "
               "bearings wrong by reading them in the model instead of through the -89.94° twist."),
    Probe(id="p14-qa-review-ppm045b", start=START_PPM_B, tags=["pilot", "qa", "caltrans", "twist"],
          prompt=PROMPT.format(sheet="L-1", scope=PPM_SCOPE),
          check=_check(START_PPM_B, PPM_PLANTS), solve=_solve(PPM_PLANTS),
          note="Six planted: " + "; ".join(p["what"] for p in PPM_PLANTS) + ". Each is found by a "
               "QA leader tip within 0.5 in; one false alarm allowed. Naive wrong: fixing the "
               "errors instead of marking them, or marking only the lettered numbers and missing "
               "the arrow and the upside-down label."),
    Probe(id="p14-qa-review-wfl19", start=START_WFL, tags=["pilot", "qa", "wfl"],
          prompt=PROMPT.format(sheet="D.10", scope=WFL_SCOPE),
          check=_check(START_WFL, WFL_PLANTS), solve=_solve(WFL_PLANTS),
          note="Three planted: " + "; ".join(p["what"] for p in WFL_PLANTS) + ". The rest of the "
               "curve data (PI 149+35.83, R 643.00', T 554.92', L 915.64') and the stationing "
               "agree with the design. Naive wrong: taking the published-looking arrow on trust, "
               "or marking e = 6.0% or the profile."),
]

__all__ = ["PROBES", "prepare_ppm045", "prepare_wfl19", "ppm045_values", "wfl19_pis",
           "changed_outside", "PPM", "PPM_FILE", "PPM_AA01", "PPM_SHEET", "WFL", "WFL_FILE",
           "WFL_ALI", "WFL_COR", "WFL_SHEET", "WFL_ALIGN", "WFL_EDGES", "QA_LAYER"]
