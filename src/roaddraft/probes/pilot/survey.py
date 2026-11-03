"""Pilot 3: survey traps -- a deed that does not close, ground distances on a
grid drawing, and coordinates in the wrong foot.

Each of the three gives the model survey data the way it arrives at a design
office, on a real example sheet's base file, and the engine does none of the
reduction: ``traverse`` will report a misclosure, but it does not balance one,
and nothing in RoadDraft knows about scale factors or feet that are not US
survey feet. A model that types the numbers in as given draws something that
looks right at plot scale and is wrong by a tenth of a foot or by thirteen
feet. The data is computed from the redraft (its right of way, its culvert,
its control), so the right answer lands on the drawing's own features, and a
careful model can see the naive one does not.

* ``p03-misclosure-ppm045`` -- Caltrans L-1 (Route 65), design file AA01. A
  grant deed for the remainder parcel east of the right of way, written from
  the redraft's own R/W angle points (N 9,655.09 E 10,232.52 and on), with two
  scrivener's errors (one distance 0.24 ft long, one bearing 25" off) that
  leave a 0.275 ft misclosure, 1:6,534. The model plots it, reports misclosure
  and precision, balances it by the compass (Bowditch) rule holding the POB,
  draws the balanced parcel closed on V-PROP, labels its area and records
  ``misclosure_ft``, ``precision`` and ``area_sqft`` with set_meta. Hard
  because the balance is arithmetic the model does itself (each corner moves
  by the misclosure times its share of the perimeter, 0.02 to 0.23 ft), and a
  plotted deed "closed" with a closing course or a moved last corner looks
  identical at 1" = 50'. Graded: every corner within 0.02 ft of the compass
  balance and no other corner on V-PROP, the boundary closed, an area label
  inside it and ``area_sqft`` within 1 sq ft (of the true balanced area, or of
  the model's own boundary when that boundary passed), misclosure within
  0.01 ft, precision 1:N within 3 %.

* ``p03-grid-ground-wfl20`` -- WFL sheet D.11 (Yellowstone River Bridge, WY
  NPS YELL 12(2)). The file set is moved by translation only so the GPS
  symbol the sheet draws at its corner sits on YRB3's state plane coordinates
  from the project's survey control sheet D.1 (WFL Plan-Profile p10), and the
  twelve control points of that table are put in the survey file as COGO
  points. The crew occupied YRB3, backsighted 23307 and measured angles right
  and horizontal *ground* distances to the 24" CMP's two end sections and
  three borings; the combined factor at YRB3 is 0.999649. Hard because the
  drawing is grid and the distances are ground: plotting them as measured
  puts every point 0.16-0.24 ft long, dividing by the factor puts it twice as
  far. Graded: COGO points 601-605 each within 0.05 ft of grid truth (angle
  from the grid backsight azimuth, distance x 0.999649).

* ``p03-intl-feet-ppm047`` -- Caltrans L-3 (Route 65). AA01 and BB01 are moved
  by translation to California Zone 2 magnitudes (sheet centre near E
  6,763,418, N 2,078,237) and the sheet's viewport is moved with them. Four
  right of way monuments on the easterly R/W line arrive in *international*
  feet, two GPS control points in metres; the drawing is US survey feet. Hard
  because at these magnitudes the 2 ppm between the feet is 13.5 ft in E and
  4.2 ft in N, and 3.28084 (the international factor) for metres is the same
  mistake; a careful model sees the monuments miss the R/W line. Graded: COGO
  points 201-204, 1001 and 1002 each within 0.05 ft (intl x 0.999998, metres
  x 3937/1200).

Four more (2026-11):

* ``p03-misclosure-ppm049`` -- Caltrans L-5: a 10-course deed (two R/W
  courses, seven along an old fence), misclosure 0.354 ft, 1:4,840.
* ``p03-misclosure-fdot915`` -- FDOT sheet 12: a 6-course deed with a tangent
  curve along SR 61's R/W (R 810.91), misclosure 0.282 ft, 1:4,259. The
  balance moves the curve's ends and the curve keeps its radius; the check
  adds an item for the curve drawn on its balanced arc.
* ``p03-grid-ground-cflpnp`` -- CFL Plan 1 the other way round: the drawing is
  project ground (scaled about CP-1), the GPS locates are state plane grid, so
  the combined factor 0.999562 is divided out.
* ``p03-intl-feet-wfl15`` -- WFL D.6 moved onto Montana State Plane, which is
  defined in international feet: the drawing is international feet, the data
  US survey feet and metres (x 1.000002 and / 0.3048).

Every check reads only the submitted document: the points, the V-PROP
linework and its label, and the set_meta answers.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.design import cogo
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Line, Point, Polyline, Text, entity_distance
from roaddraft.document.fileformat import read_document, write_document
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common

# ------------------------------------------------------------------ helpers

#: alignment element keys that hold points (moved by a re-georeference)
_ELEMENT_POINTS = ("pc", "pt", "pi", "center", "start", "end")


def _shift(p, delta):
    return [float(p[0]) + delta[0], float(p[1]) + delta[1]] + list(p[2:])


def translate_file(path: Path, delta: Sequence[float]) -> None:
    """Move a base file's model space by ``delta`` (translation only, so every
    bearing, distance and station is unchanged): entities through the engine's
    own ``Entity.translated``, alignments element by element."""
    doc = Document.from_dict(read_document(path))
    doc.model_entities = {k: e.translated(list(delta)) for k, e in doc.model_entities.items()}
    data = doc.to_dict()
    for a in data["design"]["alignments"].values():
        a["pis"] = [_shift(p, delta) for p in a.get("pis") or []]
        for element in a.get("elements") or []:
            for key in _ELEMENT_POINTS:
                if element.get(key) is not None:
                    element[key] = _shift(element[key], delta)
    write_document(path, data)


def shift_viewports(path: Path, delta: Sequence[float]) -> None:
    """Move every viewport's model window by ``delta``: the engine has no
    re-georeference command, and a sheet whose bases moved shows empty paper
    until its viewports follow."""
    data = read_document(path)
    for sheet in data.get("sheets", {}).values():
        ports = sheet.get("viewports") or []
        for vp in (ports.values() if isinstance(ports, dict) else ports):
            vp["model_center"] = _shift(vp["model_center"], delta)
    write_document(path, data)


def georeference(out: Path, sheet_id: str, delta: Sequence[float]) -> Dict[str, Path]:
    """Stage a redrafted sheet's file set and move its bases (and the sheet's
    viewports) by ``delta``."""
    files = common.stage(out, sheet_id)
    sheet = common.sheet_file(sheet_id)
    for name, path in files.items():
        if name != sheet:
            translate_file(path, delta)
    shift_viewports(files[sheet], delta)
    return files


def added_model(baseline: Session, submitted: Session) -> list:
    before = set(baseline.doc.model_entities)
    return [e for k, e in submitted.doc.model_entities.items() if k not in before]


def added_points(baseline: Session, submitted: Session) -> List[Point]:
    return [e for e in added_model(baseline, submitted) if isinstance(e, Point)]


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")


def numbers(text: str) -> List[float]:
    """Every number written in ``text``: ``132,346 SQ FT`` -> [132346.0]."""
    out = []
    for m in _NUMBER.finditer(str(text)):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return out


def meta_value(submitted: Session, key: str) -> Optional[str]:
    """A set_meta answer, the key matched without regard to case."""
    for k, v in common.answers(submitted).items():
        if k.strip().lower() == key.lower():
            return v
    return None


def check_points(baseline: Session, submitted: Session, truth, tol: float, why: str,
                 good: str) -> Result:
    """Each ``(number, description, [x, y])`` must be an added COGO point of
    that number within ``tol`` ft; every copy of a number is held to it."""
    found: Dict[int, List[Point]] = {}
    for p in added_points(baseline, submitted):
        found.setdefault(p.number, []).append(p)
    tally = Tally()
    for number, desc, xy in truth:
        item = f"point {number} ({desc})"
        copies = found.get(number, [])
        if not copies:
            tally.add(item, f"no COGO point {number} was added")
            continue
        worst = max(copies, key=lambda p: math.dist(p.position, xy))
        d = math.dist(worst.position, xy)
        if d <= tol:
            tally.add(item, None)
        else:
            de, dn = worst.position[0] - xy[0], worst.position[1] - xy[1]
            tally.add(item, f"point {number} is {d:.3f} ft from where {why} puts it "
                            f"(off by {de:+.3f} E, {dn:+.3f} N)")
    return tally.result(good)


def _vertices(entities) -> List[List[float]]:
    pts = []
    for e in entities:
        if isinstance(e, Line):
            pts += [list(e.start), list(e.end)]
        elif isinstance(e, Polyline):
            pts += [list(v) for v in e.vertices]
    return pts


def _inside(point, polygon) -> bool:
    x, y = point
    inside = False
    for i in range(len(polygon)):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % len(polygon)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _shoelace(points) -> float:
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
                   for i in range(n))) / 2.0


# ===================================================== 1. misclosure (PPM-045)

MIS_ID = "p03-misclosure-ppm045"
MIS_SHEET = "PPM-045"
MIS_FILE = "0000000000aa01.rdraft"
MIS_LAYER = "V-PROP"
#: the point of beginning: the angle point of the easterly R/W line, the end of
#: AA01's LN-213/LN-214 (local datum)
MIS_POB = (10232.52, 9655.09)
#: the deed as written, from the redraft's R/W corners B, C, D, the new corners
#: E, F and the R/W corner A, rounded to the second and the hundredth; course 4
#: is written 0.24 ft long and course 5's bearing 25" off (true: 733.08,
#: N 87°38'25" W), which leaves the misclosure
MIS_DEED = [
    ("N 01°14'31\" W", 153.17),
    ("N 00°03'47\" E", 282.02),
    ("N 88°50'01\" E", 174.90),
    ("S 02°52'25\" E", 733.32),
    ("N 87°38'00\" W", 160.31),
    ("N 09°35'06\" W", 290.85),
]
MIS_CORNER_FT = 0.02
MIS_AREA_SQFT = 1.0
MIS_CLOSE_FT = 0.01
MIS_PRECISION = 0.03


def misclosure_truth() -> dict:
    """The deed plotted from the POB, its misclosure, and the compass-rule
    balance holding the POB: corners, perimeter, precision and area."""
    raw = [list(MIS_POB)]
    for bearing, dist in MIS_DEED:
        raw.append(cogo.forward(raw[-1], cogo.parse_quadrant_bearing(bearing), dist))
    perimeter = sum(d for _b, d in MIS_DEED)
    dx, dy = MIS_POB[0] - raw[-1][0], MIS_POB[1] - raw[-1][1]
    balanced, run = [list(MIS_POB)], 0.0
    for i, (_b, dist) in enumerate(MIS_DEED[:-1]):
        run += dist
        balanced.append([raw[i + 1][0] + dx * run / perimeter, raw[i + 1][1] + dy * run / perimeter])
    error = math.hypot(dx, dy)
    return {"raw": raw, "corners": balanced, "misclosure": error, "perimeter": perimeter,
            "precision": perimeter / error, "area": _shoelace(balanced)}


def _deed_text() -> str:
    c = MIS_DEED
    return (f"BEGINNING at the angle point in the easterly right of way line of State Highway "
            f"03-PLA-65 at N {MIS_POB[1]:,.2f}, E {MIS_POB[0]:,.2f}; thence along said right of "
            f"way line {c[0][0]} {c[0][1]:.2f} feet; thence {c[1][0]} {c[1][1]:.2f} feet; thence "
            f"leaving said right of way line {c[2][0]} {c[2][1]:.2f} feet; thence {c[3][0]} "
            f"{c[3][1]:.2f} feet; thence {c[4][0]} {c[4][1]:.2f} feet to said right of way line; "
            f"thence along said right of way line {c[5][0]} {c[5][1]:.2f} feet to the POINT OF "
            f"BEGINNING.")


def _build_misclosure(out: Path) -> Path:
    common.stage(out, MIS_SHEET)
    return out / MIS_FILE


def _parse_precision(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    found = numbers(text)
    # "1:6,534", "1/6534", "1 in 6,534" or "6534": N is the largest number
    return max(found) if found else None


def check_misclosure(baseline: Session, submitted: Session) -> Result:
    truth = misclosure_truth()
    corners = truth["corners"]
    tally = Tally()
    drawn = [e for e in added_model(baseline, submitted)
             if e.layer == MIS_LAYER and isinstance(e, (Line, Polyline))]
    own_area = None
    if not drawn:
        tally.add("balanced parcel drawn closed on V-PROP", f"nothing was drawn on {MIS_LAYER}")
        tally.add("corners on the compass-rule balance (0.02 ft)", "no corners to check")
        tally.add("no unbalanced or extra corners on V-PROP", "no corners to check")
    else:
        closed = submitted.query("area", {"ids": [e.id for e in drawn]})
        loops = closed.get("loops") or []
        if not closed.get("ok"):
            tally.add("balanced parcel drawn closed on V-PROP",
                      f"the {MIS_LAYER} linework is not a closed boundary: "
                      f"{closed['error']['message']}")
        elif len(loops) != 1:
            tally.add("balanced parcel drawn closed on V-PROP",
                      f"the {MIS_LAYER} linework makes {len(loops)} loops, not one parcel")
        else:
            tally.add("balanced parcel drawn closed on V-PROP", None)
        vertices = _vertices(drawn)
        misses = [(i, min(math.dist(v, c) for v in vertices)) for i, c in enumerate(corners)]
        worst = max(misses, key=lambda m: m[1])
        tally.add("corners on the compass-rule balance (0.02 ft)",
                  None if worst[1] <= MIS_CORNER_FT else
                  f"corner {worst[0] + 1} of the balanced parcel is {worst[1]:.3f} ft from the "
                  f"nearest {MIS_LAYER} vertex (compass rule puts it at [{corners[worst[0]][0]:.3f}, "
                  f"{corners[worst[0]][1]:.3f}])")
        stray = [v for v in vertices if min(math.dist(v, c) for c in corners) > MIS_CORNER_FT]
        tally.add("no unbalanced or extra corners on V-PROP",
                  None if not stray else
                  f"{len(stray)} {MIS_LAYER} vertices are not corners of the balanced parcel, "
                  f"e.g. [{stray[0][0]:.3f}, {stray[0][1]:.3f}]")
        if tally.clean:
            own_area = float(closed["area"])

    def area_ok(value: float) -> bool:
        return (abs(value - truth["area"]) <= MIS_AREA_SQFT
                or (own_area is not None and abs(value - own_area) <= MIS_AREA_SQFT))

    labels = [e for e in added_model(baseline, submitted) if isinstance(e, Text)
              and any(area_ok(n) for n in numbers(e.content))]
    inside = [e for e in labels if _inside(e.position, corners)]
    tally.add("area label inside the parcel (1 sq ft)",
              None if inside else
              ("the area label is not inside the parcel" if labels else
               f"no text gives the parcel's area ({truth['area']:,.0f} sq ft balanced)"))

    value = meta_value(submitted, "misclosure_ft")
    found = numbers(value) if value is not None else []
    tally.add("misclosure_ft recorded (0.01 ft)",
              "set_meta has no misclosure_ft" if not found else
              None if abs(found[0] - truth["misclosure"]) <= MIS_CLOSE_FT else
              f"misclosure_ft is {value}; the deed misses its start by {truth['misclosure']:.3f} ft")
    value = meta_value(submitted, "precision")
    n = _parse_precision(value)
    tally.add("precision recorded as 1:N (3 %)",
              "set_meta has no precision" if n is None else
              None if abs(n - truth["precision"]) <= MIS_PRECISION * truth["precision"] else
              f"precision is {value}; the deed closes 1:{truth['precision']:,.0f}")
    value = meta_value(submitted, "area_sqft")
    found = numbers(value) if value is not None else []
    tally.add("area_sqft recorded (1 sq ft)",
              "set_meta has no area_sqft" if not found else
              None if area_ok(found[0]) else
              f"area_sqft is {value}; the balanced parcel is {truth['area']:,.1f} sq ft")
    return tally.result(f"balanced parcel on {MIS_LAYER}, misclosure "
                        f"{truth['misclosure']:.3f} ft, 1:{truth['precision']:,.0f}, "
                        f"{truth['area']:,.0f} sq ft")


def solve_misclosure(session: Session) -> None:
    r = common.ok(session.query("traverse", {
        "start": list(MIS_POB), "close": True,
        "legs": [{"bearing": b, "distance": d} for b, d in MIS_DEED]}))
    raw, closure, perimeter = r["points"], r["closure"], r["length"]
    corners, run = [raw[0]], 0.0
    for i, (_b, dist) in enumerate(MIS_DEED[:-1]):
        run += dist
        corners.append([raw[i + 1][0] + closure["dx"] * run / perimeter,
                        raw[i + 1][1] + closure["dy"] * run / perimeter])
    session.execute("create_layer", {"name": MIS_LAYER, "color": "magenta",
                                     "linetype": "phantom", "lineweight_mm": 0.35,
                                     "description": "property lines"})
    pl = common.ok(session.execute("draw_polyline", {
        "space": "model", "layer": MIS_LAYER, "vertices": corners, "closed": True}))["created"][0]
    area = common.ok(session.query("area", {"ids": [pl]}))
    common.ok(session.execute("place_text", {
        "space": "model", "layer": MIS_LAYER, "position": area["centroid"],
        "content": f"REMAINDER PARCEL\n{area['area']:,.0f} SQ FT", "height": 5.0,
        "halign": "center", "valign": "middle"}))
    common.ok(session.execute("set_meta", {"updates": {
        "misclosure_ft": round(closure["distance"], 3),
        "precision": closure["precision_text"],
        "area_sqft": round(area["area"])}}))


MIS_PROMPT = (
    "Right of Way sent the grant deed for the remainder parcel east of Route 65 on layout "
    "sheet L-1. Plot it in this design file (the L-1 base, on the project's local "
    "coordinates). The deed reads: " + _deed_text() + " Check the closure: work out the "
    "misclosure and the precision, balance the traverse by the compass (Bowditch) rule holding "
    "the point of beginning, and draw the balanced parcel as one closed boundary on layer "
    "V-PROP. Label its area in square feet inside the parcel. Record the results with set_meta: "
    "misclosure_ft, precision (as 1:N) and area_sqft.")


# =================================================== 2. grid vs ground (WFL D.11)

GG_ID = "p03-grid-ground-wfl20"
GG_SHEET = "WFL-Plan-Profile-Sheets-p20"
GG_FILE = "SamplePlan_sur.rdraft"
#: YRB3: where the redraft draws the GPS symbol (COR's spoked triangle at the
#: sheet's top-left corner), and its state plane coordinates on control sheet D.1
GG_YRB3_LOCAL = (10032.364616898818, 10439.27515730945)
GG_YRB3_GRID = (543541.829, 939062.686)
GG_DELTA = (GG_YRB3_GRID[0] - GG_YRB3_LOCAL[0], GG_YRB3_GRID[1] - GG_YRB3_LOCAL[1])
#: survey control sheet D.1 (WFL Plan-Profile p10): number, N, E, orthometric
#: elevation, combined factor, description. YRB1-3 are numbered 9001-9003.
GG_CONTROL = [
    (121, 939525.161, 540442.590, 6236.204, 0.99964918, '1/2" IR'),
    (122, 940196.920, 543607.272, 6155.301, 0.999652437, '1/2" IR'),
    (16301, 939686.304, 540314.336, 6219.581, 0.999649998, '5/8" IR W/FHWA ALUM CAP'),
    (16302, 939760.550, 540872.848, 6175.146, 0.999652012, '5/8" IR W/FHWA ALUM CAP'),
    (16303, 939740.417, 541380.977, 6139.023, 0.999653639, '5/8" IR W/FHWA ALUM CAP'),
    (16305, 939894.514, 542685.536, 6091.312, 0.999655667, '5/8" IR W/FHWA ALUM CAP'),
    (16306, 940249.797, 543401.072, 6148.812, 0.999652785, '5/8" IR W/FHWA ALUM CAP'),
    (23304, 939808.665, 542034.764, 6095.636, 0.999655585, '5/8" IR W/FHWA ALUM CAP'),
    (23307, 939863.603, 543634.446, 6184.665, 0.999651029, '5/8" IR W/FHWA ALUM CAP'),
    (9001, 939323.171, 539882.079, 6240.507, 0.999649084, 'YRB1 5/8" IR W/FHWA ALUM CAP'),
    (9002, 939871.595, 543788.404, 6187.720, 0.999650854, 'YRB2 5/8" IR W/FHWA ALUM CAP'),
    (9003, 939062.686, 543541.829, 6228.857, 0.999648937, 'YRB3 5/8" IR W/FHWA ALUM CAP'),
]
GG_OCCUPIED, GG_BACKSIGHT = 9003, 23307
GG_FACTOR = 0.999649
#: the field ties: angle right from the backsight, horizontal ground distance.
#: Computed from the georeferenced drawing (the centroids of the CMP end
#: sections COR:PL-016 and PL-012, and MAIN 01 157+75 28' Lt, 158+60 31' Lt,
#: 159+45 26' Lt), angles to the second and ground distances to the hundredth.
GG_TIES = [
    (601, "CMP 24 INL", "159°31'04\"", 447.53),
    (602, "CMP 24 OUT", "168°25'03\"", 467.41),
    (603, "BORING B-1", "158°28'38\"", 535.49),
    (604, "BORING B-2", "155°10'57\"", 609.26),
    (605, "BORING B-3", "152°25'15\"", 686.67),
]
GG_TOL_FT = 0.05


def _control(number: int) -> Tuple[float, float]:
    row = next(r for r in GG_CONTROL if r[0] == number)
    return (row[2], row[1])


def grid_ground_truth() -> List[Tuple[int, str, List[float]]]:
    occupied, backsight = _control(GG_OCCUPIED), _control(GG_BACKSIGHT)
    az_bs, _ = cogo.inverse(occupied, backsight)
    out = []
    for number, desc, angle, ground in GG_TIES:
        az = (az_bs + cogo.parse_dms(angle)) % 360.0
        out.append((number, desc, cogo.forward(occupied, az, ground * GG_FACTOR)))
    return out


def _build_grid_ground(out: Path) -> Path:
    files = georeference(out, GG_SHEET, GG_DELTA)
    session = common.load(files[GG_FILE])
    common.ok(session.execute("create_layer", {"name": "E_SURVEY_CONTROL", "color": "black",
                                               "description": "project control (sheet D.1)"}))
    common.ok(session.execute("create_points", {
        "space": "model", "layer": "E_SURVEY_CONTROL", "marker": "circle_x",
        "points": [{"number": n, "northing": north, "easting": east, "elevation": z,
                    "description": desc} for n, north, east, z, _cf, desc in GG_CONTROL]}))
    common.save(session, files[GG_FILE])
    return files[GG_FILE]


def check_grid_ground(baseline: Session, submitted: Session) -> Result:
    return check_points(baseline, submitted, grid_ground_truth(), GG_TOL_FT,
                        "the tie reduced to grid (ground x 0.999649)",
                        "all five ties on grid within 0.05 ft")


def solve_grid_ground(session: Session) -> None:
    found = common.ok(session.query("find_entities", {"type": "point", "limit": 50,
                                                      "detail": "full"}))["entities"]
    where = {row["entity"]["number"]: row["entity"]["position"] for row in found}
    occupied, backsight = where[GG_OCCUPIED], where[GG_BACKSIGHT]
    az_in, _ = cogo.inverse(backsight, occupied)   # the course the angle turns from
    points = []
    for number, desc, angle, ground in GG_TIES:
        r = common.ok(session.query("traverse", {
            "start": occupied, "initial_azimuth": az_in,
            "legs": [{"angle_right": angle, "distance": round(ground * GG_FACTOR, 4)}]}))
        points.append({"number": number, "point": r["end"], "description": desc})
    session.execute("create_layer", {"name": "E_SURVEY_TIES", "color": "black"})
    common.ok(session.execute("create_points", {"space": "model", "layer": "E_SURVEY_TIES",
                                                "points": points}))


def _ties_text() -> str:
    return "; ".join(f"{n} {desc}: {angle}, {dist:.2f}'" for n, desc, angle, dist in GG_TIES)


GG_PROMPT = (
    "Field ties from today's survey for sheet D.11 need to go into this survey file. The base "
    "files are on the project control, NAD83 Wyoming West state plane grid in US survey feet; "
    "the control points from sheet D.1 are in this file as COGO points (YRB3 is point 9003). "
    "The crew occupied YRB3, backsighted control point 23307 and turned angles right, measuring "
    "horizontal ground distances: " + _ties_text() + ". The control sheet gives a combined "
    "factor of 0.999649 at YRB3. Set the tied points as COGO points with those numbers and "
    "descriptions.")


# ================================================ 3. international feet (PPM-047)

IF_ID = "p03-intl-feet-ppm047"
IF_SHEET = "PPM-047"
IF_FILE = "0000000000aa01.rdraft"
#: the local datum (sheet centre near E 10,000 N 10,000) moved to California
#: Zone 2 magnitudes by translation
IF_DELTA = (6753418.37, 2068236.52)
#: US survey feet per international foot, and per metre
INTL_TO_US = 0.999998
M_TO_US = 3937.0 / 1200.0
#: the R/W consultant's monuments (international feet: northing, easting), on
#: AA01's easterly R/W line LN-229 25, 200, 375 and 550 ft from its south end,
#: and the GPS control (metres), each rounded as delivered
IF_POINTS = [
    (201, "RW MON 2-1/2 IN BC", "ift", 2078048.30, 6763722.76),
    (202, "RW MON 2-1/2 IN BC", "ift", 2078222.66, 6763707.80),
    (203, "RW MON 2-1/2 IN BC", "ift", 2078397.02, 6763692.85),
    (204, "RW MON 2-1/2 IN BC", "ift", 2078571.38, 6763677.90),
    (1001, "GPS CP", "m", 633377.575, 2061447.610),
    (1002, "GPS CP", "m", 633581.723, 2061532.204),
]
IF_TOL_FT = 0.05


def intl_feet_truth() -> List[Tuple[int, str, List[float]]]:
    out = []
    for number, desc, unit, north, east in IF_POINTS:
        k = INTL_TO_US if unit == "ift" else M_TO_US
        out.append((number, desc, [east * k, north * k]))
    return out


def _build_intl_feet(out: Path) -> Path:
    files = georeference(out, IF_SHEET, IF_DELTA)
    return files[IF_FILE]


def check_intl_feet(baseline: Session, submitted: Session) -> Result:
    return check_points(baseline, submitted, intl_feet_truth(), IF_TOL_FT,
                        "the coordinate converted to US survey feet",
                        "all six points in US survey feet within 0.05 ft")


def solve_intl_feet(session: Session) -> None:
    points = [{"number": n, "northing": round(north * k, 4), "easting": round(east * k, 4),
               "description": desc}
              for n, desc, unit, north, east in IF_POINTS
              for k in [INTL_TO_US if unit == "ift" else M_TO_US]]
    session.execute("create_layer", {"name": "V-SURV-MONU", "color": "black"})
    common.ok(session.execute("create_points", {"space": "model", "layer": "V-SURV-MONU",
                                                "points": points}))


def _intl_list(unit: str) -> str:
    fmt = "{:,.2f}" if unit == "ift" else "{:,.3f}"
    return "; ".join(f"{n} N {fmt.format(north)} E {fmt.format(east)} {desc}"
                     for n, desc, u, north, east in IF_POINTS if u == unit)


IF_PROMPT = (
    "Right of Way has set monuments along the easterly R/W line on layout sheet L-3, and our "
    "crew set two GPS control points for the job. Plot all of them as COGO points in this "
    "design file, which is CCS83 Zone 2 in US survey feet, with the numbers and descriptions "
    "given. The R/W consultant's list (CCS83 Zone 2, NAD83(2011) epoch 2010.00; header: units "
    "international feet): " + _intl_list("ift") + ". The control report (CCS83 Zone 2, "
    "metres): " + _intl_list("m") + ".")


# ================================================ 4. more deeds (2026-11)

#: a corner or a point on a curve course within this of the balance passes
DEED_CORNER_FT = 0.02


@dataclass(frozen=True)
class Deed:
    """A deed to plot, check and balance: the point of beginning and the courses
    as written (``cogo`` legs: ``{bearing, distance}`` or a tangent curve
    ``{radius, turn, delta}``), on the design file ``file`` of ``sheet_id``."""
    id: str
    sheet_id: str
    file: str
    pob: Tuple[float, float]
    legs: Tuple[dict, ...]
    layer: str = "V-PROP"


def _arc_frame(a, b, radius: float, turn: int):
    """``(center, azimuth from the center to a, sweep in degrees)`` of the arc
    of ``radius`` from ``a`` to ``b`` that turns ``turn`` (+1 right, -1 left);
    a positive sweep runs clockwise."""
    chord = math.dist(a, b)
    half = math.asin(min(1.0, chord / (2.0 * radius)))
    az, _ = cogo.inverse(a, b)
    az_in = az - turn * math.degrees(half)
    center = cogo.forward(a, az_in + turn * 90.0, radius)
    a0, _ = cogo.inverse(center, a)
    return center, a0, 2.0 * math.degrees(half) * turn


def _arc_points(a, b, radius: float, turn: int, step_ft: float = 1.0) -> List[List[float]]:
    """Points along the arc of ``radius`` from ``a`` to ``b`` (both included),
    bowing the way a curve that turns ``turn`` (+1 right, -1 left) does."""
    center, a0, sweep = _arc_frame(a, b, radius, turn)
    n = max(2, int(math.ceil(radius * math.radians(abs(sweep)) / step_ft)))
    return [cogo.forward(center, a0 + sweep * k / n, radius) for k in range(n + 1)]


def deed_truth(deed: Deed) -> dict:
    """The deed plotted from its POB (``cogo.run_traverse``, curves on their own
    arcs), its misclosure, and the compass-rule balance holding the POB: each
    corner moves by the misclosure times its share of the perimeter run to it
    (course lengths as ``traverse`` reports them: a curve by its arc). A balanced
    curve keeps its radius between its balanced ends."""
    t = cogo.run_traverse(deed.pob, [dict(leg) for leg in deed.legs], close=True)
    raw = [list(deed.pob)] + [list(c.end) for c in t.courses]
    m = t.misclosure()
    corners, run = [list(deed.pob)], 0.0
    for i, course in enumerate(t.courses[:-1]):
        run += course.length
        corners.append([raw[i + 1][0] + m["dx"] * run / m["perimeter"],
                        raw[i + 1][1] + m["dy"] * run / m["perimeter"]])
    arcs = []
    boundary: List[List[float]] = []
    for i, course in enumerate(t.courses):
        a, b = corners[i], corners[(i + 1) % len(corners)]
        if course.kind == "curve":
            arcs.append((i, course.radius, course.turn))
            boundary.extend(_arc_points(a, b, course.radius, course.turn)[:-1])
        else:
            boundary.append(a)
    return {"raw": raw, "corners": corners, "arcs": arcs, "boundary": boundary,
            "misclosure": m["distance"], "perimeter": m["perimeter"],
            "precision": m["perimeter"] / m["distance"], "area": _shoelace(boundary)}


def _deed_vertices(entities) -> List[List[float]]:
    """Line and polyline vertices, and the two ends of each arc."""
    pts = _vertices(entities)
    for e in entities:
        if isinstance(e, Arc):
            for ang in (e.start_angle_deg, e.end_angle_deg):
                pts.append([e.center[0] + e.radius * math.cos(math.radians(ang)),
                            e.center[1] + e.radius * math.sin(math.radians(ang))])
    return pts


def _on_arcs(v, truth: dict, tol: float) -> bool:
    """Whether ``v`` lies on one of the balanced curves (within ``tol`` of the
    circle, inside the curve's sweep)."""
    corners = truth["corners"]
    for i, radius, turn in truth["arcs"]:
        a, b = corners[i], corners[(i + 1) % len(corners)]
        center, a0, sweep = _arc_frame(a, b, radius, turn)
        az, d = cogo.inverse(center, v)
        along = ((az - a0) * (1 if sweep > 0 else -1)) % 360.0
        if abs(d - radius) <= tol and along <= abs(sweep) + 1e-6:
            return True
    return False


def check_deed(deed: Deed, baseline: Session, submitted: Session) -> Result:
    """``check_misclosure`` for any deed: the balanced boundary closed on the
    layer, every corner within 0.02 ft, no other vertex off a corner (or off a
    balanced curve, for a curve drawn as short chords), the area labelled
    inside, misclosure, precision and area recorded."""
    truth = deed_truth(deed)
    corners = truth["corners"]
    tally = Tally()
    drawn = [e for e in added_model(baseline, submitted)
             if e.layer == deed.layer and isinstance(e, (Line, Polyline, Arc))]
    own_area = None
    if not drawn:
        tally.add(f"balanced parcel drawn closed on {deed.layer}",
                  f"nothing was drawn on {deed.layer}")
        tally.add("corners on the compass-rule balance (0.02 ft)", "no corners to check")
        tally.add(f"no unbalanced or extra corners on {deed.layer}", "no corners to check")
    else:
        closed = submitted.query("area", {"ids": [e.id for e in drawn]})
        loops = closed.get("loops") or []
        if not closed.get("ok"):
            tally.add(f"balanced parcel drawn closed on {deed.layer}",
                      f"the {deed.layer} linework is not a closed boundary: "
                      f"{closed['error']['message']}")
        elif len(loops) != 1:
            tally.add(f"balanced parcel drawn closed on {deed.layer}",
                      f"the {deed.layer} linework makes {len(loops)} loops, not one parcel")
        else:
            tally.add(f"balanced parcel drawn closed on {deed.layer}", None)
        vertices = _deed_vertices(drawn)
        misses = [(i, min(math.dist(v, c) for v in vertices)) for i, c in enumerate(corners)]
        worst = max(misses, key=lambda m: m[1])
        tally.add("corners on the compass-rule balance (0.02 ft)",
                  None if worst[1] <= DEED_CORNER_FT else
                  f"corner {worst[0] + 1} of the balanced parcel is {worst[1]:.3f} ft from the "
                  f"nearest {deed.layer} vertex (compass rule puts it at "
                  f"[{corners[worst[0]][0]:.3f}, {corners[worst[0]][1]:.3f}])")
        stray = [v for v in vertices
                 if min(math.dist(v, c) for c in corners) > DEED_CORNER_FT
                 and not _on_arcs(v, truth, DEED_CORNER_FT)]
        tally.add(f"no unbalanced or extra corners on {deed.layer}",
                  None if not stray else
                  f"{len(stray)} {deed.layer} vertices are not corners of the balanced parcel, "
                  f"e.g. [{stray[0][0]:.3f}, {stray[0][1]:.3f}]")
        for i, radius, turn in truth["arcs"]:
            a, b = corners[i], corners[(i + 1) % len(corners)]
            center, a0, sweep = _arc_frame(a, b, radius, turn)
            mid = cogo.forward(center, a0 + sweep / 2.0, radius)
            d = min(entity_distance(submitted.doc, e, mid) for e in drawn)
            tally.add(f"curve course {i + 1} drawn on its balanced arc (0.05 ft)",
                      None if d <= 0.05 else
                      f"the {deed.layer} linework passes {d:.2f} ft from the middle of the "
                      f"balanced curve of course {i + 1} (radius {radius:.2f}, at "
                      f"[{mid[0]:.3f}, {mid[1]:.3f}])")
        if tally.clean:
            own_area = float(closed["area"])

    def area_ok(value: float) -> bool:
        return (abs(value - truth["area"]) <= MIS_AREA_SQFT
                or (own_area is not None and abs(value - own_area) <= MIS_AREA_SQFT))

    labels = [e for e in added_model(baseline, submitted) if isinstance(e, Text)
              and any(area_ok(n) for n in numbers(e.content))]
    inside = [e for e in labels if _inside(e.position, truth["boundary"])]
    tally.add("area label inside the parcel (1 sq ft)",
              None if inside else
              ("the area label is not inside the parcel" if labels else
               f"no text gives the parcel's area ({truth['area']:,.0f} sq ft balanced)"))
    value = meta_value(submitted, "misclosure_ft")
    found = numbers(value) if value is not None else []
    tally.add("misclosure_ft recorded (0.01 ft)",
              "set_meta has no misclosure_ft" if not found else
              None if abs(found[0] - truth["misclosure"]) <= MIS_CLOSE_FT else
              f"misclosure_ft is {value}; the deed misses its start by {truth['misclosure']:.3f} ft")
    value = meta_value(submitted, "precision")
    n = _parse_precision(value)
    tally.add("precision recorded as 1:N (3 %)",
              "set_meta has no precision" if n is None else
              None if abs(n - truth["precision"]) <= MIS_PRECISION * truth["precision"] else
              f"precision is {value}; the deed closes 1:{truth['precision']:,.0f}")
    value = meta_value(submitted, "area_sqft")
    found = numbers(value) if value is not None else []
    tally.add("area_sqft recorded (1 sq ft)",
              "set_meta has no area_sqft" if not found else
              None if area_ok(found[0]) else
              f"area_sqft is {value}; the balanced parcel is {truth['area']:,.1f} sq ft")
    return tally.result(f"balanced parcel on {deed.layer}, misclosure "
                        f"{truth['misclosure']:.3f} ft, 1:{truth['precision']:,.0f}, "
                        f"{truth['area']:,.0f} sq ft")


def solve_deed(deed: Deed, session: Session, balance: bool = True) -> None:
    """Plot the deed with ``traverse`` (close=true for the misclosure), balance
    it by the compass rule and draw it as one closed polyline, the curve as a
    bulge on its balanced chord. ``balance=False`` draws the deed as written,
    closed with a closing course (the naive answer the tests check fails)."""
    r = common.ok(session.query("traverse", {
        "start": list(deed.pob), "close": True, "legs": [dict(leg) for leg in deed.legs]}))
    raw, closure, perimeter = r["points"], r["closure"], r["length"]
    corners, run = [raw[0]], 0.0
    for i, course in enumerate(r["courses"][:-1]):
        run += course.get("distance", course.get("length"))
        k = run / perimeter if balance else 0.0
        corners.append([raw[i + 1][0] + closure["dx"] * k, raw[i + 1][1] + closure["dy"] * k])
    if not balance:
        corners.append(raw[-1])
    bulges = [0.0] * len(corners)
    for i, course in enumerate(r["courses"]):
        if course["kind"] == "curve" and i + 1 < len(corners):
            chord = math.dist(corners[i], corners[i + 1])
            half = math.asin(min(1.0, chord / (2.0 * course["radius"])))
            sign = -1.0 if course["turn"] == "right" else 1.0
            bulges[i] = sign * math.tan(half / 2.0)
    session.execute("create_layer", {"name": deed.layer, "color": "magenta",
                                     "linetype": "phantom", "lineweight_mm": 0.35,
                                     "description": "property lines"})
    params = {"space": "model", "layer": deed.layer, "vertices": corners, "closed": True}
    if any(bulges):
        params["bulges"] = bulges
    pl = common.ok(session.execute("draw_polyline", params))["created"][0]
    area = common.ok(session.query("area", {"ids": [pl]}))
    common.ok(session.execute("place_text", {
        "space": "model", "layer": deed.layer, "position": area["centroid"],
        "content": f"REMAINDER PARCEL\n{area['area']:,.0f} SQ FT", "height": 5.0,
        "halign": "center", "valign": "middle"}))
    common.ok(session.execute("set_meta", {"updates": {
        "misclosure_ft": round(closure["distance"], 3),
        "precision": closure["precision_text"],
        "area_sqft": round(area["area"])}}))


def _course_text(leg: dict) -> str:
    if "radius" in leg:
        arc = leg["radius"] * math.radians(cogo.parse_dms(leg["delta"]))
        return (f"along a tangent curve to the {leg['turn']}, having a radius of "
                f"{leg['radius']:.2f} feet, through a central angle of {leg['delta']}, an arc "
                f"distance of {arc:.2f} feet")
    return f"{leg['bearing']} {leg['distance']:.2f} feet"


def _deed_prompt(intro: str, deed_text: str, sheet: str) -> str:
    return (intro + " The deed reads: " + deed_text + " Check the closure: work out the "
            "misclosure and the precision, balance the traverse by the compass (Bowditch) rule "
            "holding the point of beginning, and draw the balanced parcel as one closed boundary "
            f"on layer V-PROP. Label its area in square feet inside the parcel. Record the "
            f"results with set_meta: misclosure_ft, precision (as 1:N) and area_sqft.")


#: Caltrans L-5 (Route 65): the easterly R/W line of AA01 runs from the angle
#: point LN-433 starts at, through the angle point at its end, on along LN-432;
#: the parcel east of it leaves the R/W at LN-432's end and follows an old fence
#: back in seven courses. Written with course 5 0.38 ft long (true 143.07) and
#: course 8 48" off (true S 13°35'05" W): misclosure 0.354 ft, 1:4,840.
DEED_PPM049 = Deed(
    id="p03-misclosure-ppm049", sheet_id="PPM-049", file="0000000000aa01.rdraft",
    pob=(10521.57, 9993.77),
    legs=({"bearing": "N 45°42'45\" W", "distance": 399.34},
          {"bearing": "N 40°00'00\" W", "distance": 167.75},
          {"bearing": "N 41°29'47\" E", "distance": 212.37},
          {"bearing": "S 61°47'07\" E", "distance": 96.18},
          {"bearing": "N 66°23'28\" E", "distance": 143.45},
          {"bearing": "S 28°12'40\" E", "distance": 188.52},
          {"bearing": "S 52°41'26\" E", "distance": 124.93},
          {"bearing": "S 13°35'53\" W", "distance": 151.66},
          {"bearing": "S 51°05'53\" W", "distance": 87.20},
          {"bearing": "S 19°37'40\" W", "distance": 142.49}))


def _deed_text_ppm049() -> str:
    c = [_course_text(leg) for leg in DEED_PPM049.legs]
    n, e = DEED_PPM049.pob[1], DEED_PPM049.pob[0]
    return (f"BEGINNING at an angle point in the easterly right of way line of State Highway "
            f"03-PLA-65 at N {n:,.2f}, E {e:,.2f}; thence along said right of way line "
            f"{c[0]}; thence {c[1]}; thence leaving said right of way line along an existing "
            f"fence the following seven courses: {c[2]}; {c[3]}; {c[4]}; {c[5]}; {c[6]}; "
            f"{c[7]}; {c[8]}; thence leaving said fence {c[9]} to the POINT OF BEGINNING.")


#: FDOT sheet 12 (SR 61): the parcel north-east of the road, on the right of
#: way 67.95 ft right of CL1 from 702+50 through the PC (705+70.34) and around
#: the R/W curve (CL1's 878.86-ft curve, 810.91 ft at the R/W) to 706+95, then
#: a radial line and three new courses back. Written with course 4 0.29 ft
#: long (true 238.71) and course 5 41" off (true S 71°17'11" E): misclosure
#: 0.282 ft, 1:4,259.
DEED_FDOT915 = Deed(
    id="p03-misclosure-fdot915", sheet_id="FDOT-915-1-Roadway-Plan-Profile",
    file="DSGNRD01.rdraft", pob=(10118.17, 10004.71),
    legs=({"bearing": "N 59°59'25\" W", "distance": 320.34},
          {"radius": 810.91, "turn": "right", "delta": "8°07'38\""},
          {"bearing": "N 38°08'13\" E", "distance": 152.43},
          {"bearing": "S 55°22'39\" E", "distance": 239.00},
          {"bearing": "S 71°17'52\" E", "distance": 196.18},
          {"bearing": "S 35°25'14\" W", "distance": 179.07}))


def _deed_text_fdot915() -> str:
    c = [_course_text(leg) for leg in DEED_FDOT915.legs]
    n, e = DEED_FDOT915.pob[1], DEED_FDOT915.pob[0]
    return (f"COMMENCE at a point on the northeasterly right of way line of State Road 61 at "
            f"N {n:,.2f}, E {e:,.2f}, said point being the POINT OF BEGINNING; thence along "
            f"said right of way line {c[0]}; thence continue along said right of way line "
            f"{c[1]}; thence leaving said right of way line {c[2]}; thence {c[3]}; thence "
            f"{c[4]}; thence {c[5]} to the POINT OF BEGINNING.")


DEED_PPM049_PROMPT = _deed_prompt(
    "Right of Way sent the grant deed for the remainder parcel east of Route 65 on layout "
    "sheet L-5. Plot it in this design file (the L-5 base, on the project's local "
    "coordinates).", _deed_text_ppm049(), "L-5")
DEED_FDOT915_PROMPT = _deed_prompt(
    "The right of way agent sent the legal description of the parcel north-east of SR 61 on "
    "plan-profile sheet 12. Plot it in this design file (the sheet's design base, on the "
    "project's local coordinates).", _deed_text_fdot915(), "12")


def _deed_builder(deed: Deed):
    def build(out: Path) -> Path:
        common.stage(out, deed.sheet_id)
        return out / deed.file
    return build


# ======================================= 5. ground drawing, grid data (CFL)

GG2_ID = "p03-grid-ground-cflpnp"
GG2_SHEET = "CFL-D-Plan-and-Profile"
GG2_FILE = "TERSample.rdraft"
#: the file set moved by translation so CL1 10+00 sits on the coordinates the
#: sheet letters at BEGIN PROJECT (N 1,214,356.6315 E 2,453,409.7460), taken as
#: project (ground) coordinates
GG2_DELTA = (2443915.8235, 1204944.6501)
GG2_FACTOR = 0.999562
#: project control, set in the survey file: CL1 10+20 45' Rt, 17+80 60' Lt,
#: 24+60 50' Rt (project coordinates, N, E)
GG2_CONTROL = [
    (1, 1214365.513, 2453458.183, "CP-1 5/8 IN REBAR W/ CFLHD CAP"),
    (2, 1215135.115, 2453543.488, "CP-2 5/8 IN REBAR W/ CFLHD CAP"),
    (3, 1215706.778, 2453937.321, "CP-3 5/8 IN REBAR W/ CFLHD CAP"),
]
#: the consultant's GPS locates, NAD83 Colorado Central grid (N, E): the ends
#: of the three 24-inch CMPs the profile notes, at CL1 12+54 23' Lt/Rt, 16+90
#: 21' Lt/Rt and 21+98 18' Lt/Rt, reduced from project coordinates about CP-1
#: (grid = CP-1 + (ground - CP-1) x 0.999562) and rounded to the thousandth
GG2_LOCATES = [
    (801, "CMP 24 INL", 1214608.830, 2453446.998),
    (802, "CMP 24 OUT", 1214598.040, 2453491.694),
    (803, "CMP 24 INL", 1215032.160, 2453551.268),
    (804, "CMP 24 OUT", 1215021.980, 2453591.997),
    (805, "CMP 24 INL", 1215475.929, 2453797.334),
    (806, "CMP 24 OUT", 1215462.573, 2453830.748),
]


def grid_to_ground_truth() -> List[Tuple[int, str, List[float]]]:
    """Grid to project: scaled up about CP-1, which holds its coordinates
    (ground = CP-1 + (grid - CP-1) / 0.999562)."""
    _n, cn, ce, _d = GG2_CONTROL[0]
    return [(n, desc, [ce + (east - ce) / GG2_FACTOR, cn + (north - cn) / GG2_FACTOR])
            for n, desc, north, east in GG2_LOCATES]


def _build_grid_to_ground(out: Path) -> Path:
    files = georeference(out, GG2_SHEET, GG2_DELTA)
    session = common.load(files[GG2_FILE])
    common.ok(session.execute("create_layer", {"name": "E_SURVEY_CONTROL", "color": "black",
                                               "description": "project control"}))
    common.ok(session.execute("create_points", {
        "space": "model", "layer": "E_SURVEY_CONTROL", "marker": "circle_x",
        "points": [{"number": n, "northing": north, "easting": east, "description": desc}
                   for n, north, east, desc in GG2_CONTROL]}))
    common.save(session, files[GG2_FILE])
    return files[GG2_FILE]


def check_grid_to_ground(baseline: Session, submitted: Session) -> Result:
    return check_points(baseline, submitted, grid_to_ground_truth(), GG_TOL_FT,
                        "the grid coordinate scaled to project ground about CP-1",
                        "all six locates on project ground within 0.05 ft")


def solve_grid_to_ground(session: Session) -> None:
    found = common.ok(session.query("find_entities", {"type": "point", "limit": 50,
                                                      "detail": "full"}))["entities"]
    cp1 = next(row["entity"]["position"] for row in found if row["entity"]["number"] == 1)
    points = [{"number": n, "description": desc,
               "point": [cp1[0] + (east - cp1[0]) / GG2_FACTOR,
                         cp1[1] + (north - cp1[1]) / GG2_FACTOR]}
              for n, desc, north, east in GG2_LOCATES]
    session.execute("create_layer", {"name": "E_SURVEY_LOCATES", "color": "black"})
    common.ok(session.execute("create_points", {"space": "model", "layer": "E_SURVEY_LOCATES",
                                                "points": points}))


GG2_PROMPT = (
    "The utility consultant's GPS locates of the existing culverts on CFL Plan 1 need to go "
    "into this survey file. Our base files are on the project's ground coordinates: NAD83 "
    "Colorado Central zone state plane grid coordinates in US survey feet, scaled about "
    "control point CP-1 (point 1 in this file, which has the same coordinates on both) with "
    "the project combined scale factor 0.999562; the project control CP-1 to CP-3 is in this "
    "file. The consultant's list (NAD83 Colorado Central grid, US survey feet; N, E): "
    + "; ".join(f"{n} N {north:,.3f} E {east:,.3f} {desc}" for n, desc, north, east in GG2_LOCATES)
    + ". Set them as COGO points with those numbers and descriptions.")


# ================================= 6. a drawing in international feet (WFL)

IF2_ID = "p03-intl-feet-wfl15"
IF2_SHEET = "WFL-Plan-Profile-Sheets-p15"
IF2_FILE = "SamplePlan_sur.rdraft"
#: WFL D.6's file set moved by translation onto NAD83 Montana State Plane
#: (zone 2500, which Montana defines in international feet): the sheet centre
#: (local E 10,000 N 10,000) to E 928,412.37 N 1,585,236.18, and every file of
#: the set declares model_units international feet
IF2_DELTA = (918412.37, 1575236.18)
#: international feet per US survey foot, and per metre
US_TO_INTL = (1200.0 / 3937.0) / 0.3048
M_TO_INTL = 1.0 / 0.3048
#: the record of survey's R/W monuments, 40 ft left of MAIN 01 at 115+50,
#: 117+00, 118+50 and 120+00 (US survey feet: N, E), and the GPS control
#: (metres), each rounded as delivered
IF2_POINTS = [
    (301, "RW MON 3-1/4 IN AL CAP", "usft", 1585137.08, 928037.42),
    (302, "RW MON 3-1/4 IN AL CAP", "usft", 1585262.02, 928129.08),
    (303, "RW MON 3-1/4 IN AL CAP", "usft", 1585373.80, 928235.29),
    (304, "RW MON 3-1/4 IN AL CAP", "usft", 1585472.17, 928353.56),
    (1101, "GPS CP", "m", 483149.363, 282905.966),
    (1102, "GPS CP", "m", 483295.195, 282999.251),
]


def intl_drawing_truth() -> List[Tuple[int, str, List[float]]]:
    out = []
    for number, desc, unit, north, east in IF2_POINTS:
        k = US_TO_INTL if unit == "usft" else M_TO_INTL
        out.append((number, desc, [east * k, north * k]))
    return out


def _build_intl_drawing(out: Path) -> Path:
    files = georeference(out, IF2_SHEET, IF2_DELTA)
    for path in files.values():
        data = read_document(path)
        data.setdefault("meta", {})["model_units"] = "ft"
        write_document(path, data)
    return files[IF2_FILE]


def check_intl_drawing(baseline: Session, submitted: Session) -> Result:
    return check_points(baseline, submitted, intl_drawing_truth(), IF_TOL_FT,
                        "the coordinate converted to international feet",
                        "all six points in international feet within 0.05 ft")


def solve_intl_drawing(session: Session) -> None:
    points = [{"number": n, "northing": round(north * k, 4), "easting": round(east * k, 4),
               "description": desc}
              for n, desc, unit, north, east in IF2_POINTS
              for k in [US_TO_INTL if unit == "usft" else M_TO_INTL]]
    session.execute("create_layer", {"name": "V_SURV_MONU", "color": "black"})
    common.ok(session.execute("create_points", {"space": "model", "layer": "V_SURV_MONU",
                                                "points": points}))


def _if2_list(unit: str) -> str:
    fmt = "{:,.2f}" if unit == "usft" else "{:,.3f}"
    return "; ".join(f"{n} N {fmt.format(north)} E {fmt.format(east)} {desc}"
                     for n, desc, u, north, east in IF2_POINTS if u == unit)


IF2_PROMPT = (
    "The county's record of survey and our GPS control for sheet D.6 need to go into this "
    "survey file as COGO points, with the numbers and descriptions given. This project is on "
    "NAD83 Montana State Plane (zone 2500), which Montana law defines in international feet, "
    "and the base files are in those units. The record of survey's right of way monuments "
    "(NAD83 Montana State Plane; header: US survey feet): " + _if2_list("usft") + ". The GPS "
    "control report (NAD83 Montana State Plane, metres): " + _if2_list("m") + ".")


# ------------------------------------------------------------------- registry

MIS_START = common.register(MIS_ID, MIS_FILE, _build_misclosure)
GG_START = common.register(GG_ID, GG_FILE, _build_grid_ground)
IF_START = common.register(IF_ID, IF_FILE, _build_intl_feet)
DEED_PPM049_START = common.register(DEED_PPM049.id, DEED_PPM049.file, _deed_builder(DEED_PPM049))
DEED_FDOT915_START = common.register(DEED_FDOT915.id, DEED_FDOT915.file,
                                     _deed_builder(DEED_FDOT915))
GG2_START = common.register(GG2_ID, GG2_FILE, _build_grid_to_ground)
IF2_START = common.register(IF2_ID, IF2_FILE, _build_intl_drawing)

PROBES: List[Probe] = [
    Probe(id=MIS_ID, prompt=MIS_PROMPT, check=check_misclosure, solve=solve_misclosure,
          start=MIS_START, tags=["survey", "cogo", "caltrans"],
          note="Deed of 6 courses from the PPM-045 R/W corners, perimeter 1,794.57 ft; written "
               "with course 4 0.24 ft long and course 5 25\" off, it misses by 0.275 ft "
               "(N 03°06'36\" W), 1:6,534. Compass corrections grow from 0.023 ft at corner 2 "
               "to 0.230 ft at corner 6; balanced area 132,346.1 sq ft. Naive answers that fail: "
               "the deed drawn as written with a closing course (corners 0.02-0.23 ft off, "
               "area 132,370 sq ft), or the last corner moved onto the POB."),
    Probe(id=GG_ID, prompt=GG_PROMPT, check=check_grid_ground, solve=solve_grid_ground,
          start=GG_START, tags=["survey", "grid-ground", "wfl"],
          note="D.11's file set moved onto D.1's state plane coordinates (YRB3 at the drawn GPS "
               "symbol). Ties 447-687 ft from YRB3; reduced to grid they land on the CMP end "
               "sections and at the borings. Plotted at ground distance they are 0.157-0.241 ft "
               "long, divided by the factor 0.31-0.48 ft long; both fail the 0.05 ft tolerance."),
    Probe(id=IF_ID, prompt=IF_PROMPT, check=check_intl_feet, solve=solve_intl_feet,
          start=IF_START, tags=["survey", "units", "caltrans"],
          note="AA01/BB01 of L-3 moved by (+6,753,418.37, +2,068,236.52). Monuments 201-204 "
               "converted (x 0.999998) fall on the easterly R/W line LN-229; plotted as given "
               "they sit 13.53 ft E and 4.16 ft N of it. GPS points in metres need 3937/1200; "
               "3.28084 is off by the same 13.5 ft, 3.2808333 by about 0.07 ft."),
    Probe(id=DEED_PPM049.id, prompt=DEED_PPM049_PROMPT,
          check=lambda b, s: check_deed(DEED_PPM049, b, s),
          solve=lambda s: solve_deed(DEED_PPM049, s), start=DEED_PPM049_START,
          tags=["survey", "cogo", "caltrans"],
          note="Deed of 10 courses on the L-5 easterly R/W (AA01 LN-433, LN-432) and an old "
               "fence, perimeter 1,713.89 ft; written with course 5 0.38 ft long and course 8 "
               "48\" off, it misses by 0.354 ft (S 62°52'18\" W), 1:4,840. Compass corrections "
               "grow from 0.08 ft at corner 2 to 0.33 ft at corner 10; balanced area "
               "167,644.9 sq ft. Naive answers that fail: the deed drawn as written with a "
               "closing course, the last corner moved onto the POB, the two scrivener's errors "
               "found and corrected (it then closes, but that is not the balance asked for)."),
    Probe(id=DEED_FDOT915.id, prompt=DEED_FDOT915_PROMPT,
          check=lambda b, s: check_deed(DEED_FDOT915, b, s),
          solve=lambda s: solve_deed(DEED_FDOT915, s), start=DEED_FDOT915_START,
          tags=["survey", "cogo", "fdot"],
          note="Deed of 6 courses with a tangent curve, on SR 61's north-east R/W 67.95 ft "
               "right of CL1 (702+50 to 706+95, the R/W curve R 810.91 = CL1's 878.86 less "
               "67.95), perimeter 1,202.04 ft; written with course 4 0.29 ft long and course "
               "5 41\" off, it misses by 0.282 ft (N 63°20'38\" W), 1:4,259. The balance "
               "moves the curve's ends; the curve keeps its radius between them (a curve "
               "drawn as short chords on the balanced arc is accepted); balanced area "
               "66,156.3 sq ft. Naive answers that fail: the deed as written closed with a "
               "closing course, the last corner moved onto the POB, the curve drawn as its "
               "chord (2.0 ft inside the arc at its middle, 156 sq ft short), the curve "
               "turned the wrong way."),
    Probe(id=GG2_ID, prompt=GG2_PROMPT, check=check_grid_to_ground, solve=solve_grid_to_ground,
          start=GG2_START, tags=["survey", "grid-ground", "cfl"],
          note="The other way round from p03-grid-ground-wfl20: the drawing is project ground "
               "(CFL Plan 1's set moved so 10+00 is on the lettered BEGIN PROJECT "
               "coordinates) and the data is state plane grid, so the factor is divided out, "
               "about CP-1. The locates land on the CMP ends at CL1 12+54, 16+90 and 21+98. "
               "Plotted as given they are 0.10-0.51 ft short of the ends (toward CP-1); "
               "multiplied by the factor 0.21-1.02 ft; scaled about N 0, E 0 over 1,000 ft "
               "off. All fail the 0.05 ft tolerance."),
    Probe(id=IF2_ID, prompt=IF2_PROMPT, check=check_intl_drawing, solve=solve_intl_drawing,
          start=IF2_START, tags=["survey", "units", "wfl"],
          note="The mirror of p03-intl-feet-ppm047: the drawing is international feet (WFL "
               "D.6's set moved onto Montana State Plane magnitudes, sheet centre E 928,412 "
               "N 1,585,236, model_units ft), the data US survey feet and metres. US feet "
               "x 1.000002 put monuments 301-304 on a line 40 ft left of MAIN 01; typed as "
               "given they are 3.67 ft off, x 0.999998 (the conversion the wrong way) 7.3 ft. "
               "Metres need / 0.3048 exactly; 3937/1200 is 3.67 ft off."),
]
