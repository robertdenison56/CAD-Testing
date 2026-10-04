"""The project the find-probes run against: a design file and a plan set that
references it.

Deterministic and self-contained, so a probe run is reproducible: the same
alignment, the same offsets, the same three sheets every time.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

from roaddraft.api.session import Session

#: ~4,600 ft of two-lane highway: tangent, 1,200 ft curve right, tangent,
#: 900 ft curve left, tangent. Long enough to need three sheets at 1"=50'.
PIS = [
    [1000.0, 1000.0],
    [2600.0, 1000.0, 1200.0],
    [4100.0, 1500.0, 900.0],
    [5600.0, 1500.0],
]
BEGIN_STATION = "10+00"
EDGE_OFFSETS = [-12.0, 12.0]        # a 24 ft pavement
SHOULDER_OFFSETS = [-20.0, 20.0]    # 8 ft shoulders
ALIGNMENT = "SR-100"

LAYERS = [
    {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center", "lineweight_mm": 0.35},
    {"name": "V-ROAD-EOP", "color": "yellow", "lineweight_mm": 0.35},
    {"name": "V-ROAD-SHLD", "color": "gray", "linetype": "dashed", "lineweight_mm": 0.18},
    {"name": "V-ANNO-TEXT", "color": "black", "lineweight_mm": 0.25},
]

SHEETS = ["C-101", "C-102", "C-103"]
FEET_PER_INCH = 50.0
VIEWPORT = {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5}

MODEL_FILE = "SR-100.model.rdoc.json"
SHEET_FILE = "SR-100.sheets.rdoc.json"
BLANK_FILE = "DESIGN.model.rdoc.json"
CENTERLINE_FILE = "SR-100.centerline.rdoc.json"
INTERSECTION_FILE = "Main-Cross.model.rdoc.json"
FLAWED_FILE = "SR-100.flawed.rdoc.json"

#: the document an agent is handed, by Probe.start
START = {"sheets": SHEET_FILE, "model": MODEL_FILE, "blank": BLANK_FILE,
         "centerline": CENTERLINE_FILE, "intersection": INTERSECTION_FILE,
         "flawed": FLAWED_FILE}

#: MAIN ST / CROSS AVE for the tier-2 probes: two straight alignments crossing
#: at right angles, curb faces at constant offsets, 50 ft curb returns. MAIN-ST
#: runs east (right of stationing is south), CROSS-AVE runs north (right is east).
INTERSECTION = {
    "point": [5000.0, 5000.0],
    "main": {"name": "MAIN-ST", "begin": 1000.0, "leg": 800.0, "curb": 44.0},
    "cross": {"name": "CROSS-AVE", "begin": 2000.0, "leg": 700.0, "curb": 32.0},
    "radius": 50.0,
    #: (name, east sign, north sign); the open corner has no return yet
    "corners": [("NE", 1, 1), ("SE", 1, -1), ("SW", -1, -1), ("NW", -1, 1)],
    "open": "NE",
}

#: What build_flawed plants in the SR-100 model, for draft-fix-the-drawing.
FLAWS = {"edge_offset": 11.0, "callout_text": "EDGE OF PAVEMENT"}


def check(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


def build_model(out: Path) -> Path:
    """The design: alignment, pavement edges, shoulders. No sheets, no labels."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    check(s.execute("create_alignment", {"name": ALIGNMENT, "begin_station": BEGIN_STATION,
                                         "pis": PIS, "description": "SR-100 mainline"}))
    check(s.execute("draw_alignment", {"alignment": ALIGNMENT, "layer": "V-ALIGN-CNTR"}))
    check(s.execute("draw_offset", {"alignment": ALIGNMENT, "offsets": EDGE_OFFSETS,
                                    "layer": "V-ROAD-EOP"}))
    check(s.execute("draw_offset", {"alignment": ALIGNMENT, "offsets": SHOULDER_OFFSETS,
                                    "layer": "V-ROAD-SHLD"}))
    path = out / MODEL_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_sheets(out: Path, model_path: Path) -> Path:
    """The plans: three sheets over the referenced model, title blocks empty."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    path = out / SHEET_FILE
    # Save first so the relative reference resolves from the sheet file's own
    # folder, the way it will when the file is opened again later.
    check(s.query("save_document", {"path": str(path)}))
    check(s.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                         "path": model_path.name}))

    reference = Session.load(model_path, out_dir=out)
    align = reference.doc.design.alignments[ALIGNMENT]
    x0, _y0, _x1, y1 = align.bbox()
    per_sheet = VIEWPORT["width_in"] * FEET_PER_INCH
    mid_y = (align.bbox()[1] + y1) / 2.0
    for i, name in enumerate(SHEETS):
        check(s.execute("create_sheet", {"name": name, "size": "ANSI_D"}))
        check(s.execute("create_viewport", {
            "sheet": name, "feet_per_inch": FEET_PER_INCH,
            "model_center": [x0 + per_sheet * (i + 0.5), mid_y], **VIEWPORT}))
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_blank(out: Path) -> Path:
    """A design file with the office's layers and nothing drawn: where a
    drafting job starts."""
    s = Session(project_name="Design model", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    path = out / BLANK_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def build_centerline(out: Path) -> Path:
    """SR-100 with its alignment designed and drawn, and no roadway on it yet."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    check(s.execute("create_alignment", {"name": ALIGNMENT, "begin_station": BEGIN_STATION,
                                         "pis": PIS, "description": "SR-100 mainline"}))
    check(s.execute("draw_alignment", {"alignment": ALIGNMENT, "layer": "V-ALIGN-CNTR"}))
    path = out / CENTERLINE_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def corner_geometry(name: str) -> dict:
    """One curb return of the intersection: its centre, the two tangent points
    and the stations of the curb pieces it joins. ``east``/``north`` are the
    corner's signs; the arc runs CCW from ``start_deg`` to ``end_deg``."""
    I = INTERSECTION
    east, north = next((e, n) for c, e, n in I["corners"] if c == name)
    px, py = I["point"]
    main, cross, r = I["main"], I["cross"], I["radius"]
    cx, cy = px + east * (cross["curb"] + r), py + north * (main["curb"] + r)
    main_tp = [cx, py + north * main["curb"]]           # on MAIN ST's curb face
    cross_tp = [px + east * cross["curb"], cy]          # on CROSS AVE's curb face
    mid = math.degrees(math.atan2(-north, -east)) % 360.0
    main_station = main["begin"] + main["leg"] + east * (cross["curb"] + r)
    cross_station = cross["begin"] + cross["leg"] + north * (main["curb"] + r)
    return {"east": east, "north": north, "center": [cx, cy], "radius": r,
            "main_offset": -north * main["curb"], "cross_offset": east * cross["curb"],
            "main_tp": main_tp, "cross_tp": cross_tp,
            "start_deg": (mid - 45.0) % 360.0, "end_deg": (mid + 45.0) % 360.0,
            "main_station": main_station, "cross_station": cross_station,
            # where the untrimmed curb lines meet: the corner itself
            "main_corner_station": main["begin"] + main["leg"] + east * cross["curb"],
            "cross_corner_station": cross["begin"] + cross["leg"] + north * main["curb"]}


def build_intersection(out: Path) -> Path:
    """MAIN ST / CROSS AVE with three corners finished and one left as a
    drafter leaves it: both curb lines running to meet at the corner."""
    I = INTERSECTION
    s = Session(project_name="MAIN ST / CROSS AVE", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    px, py = I["point"]
    for road, azimuth in (("main", 90.0), ("cross", 0.0)):
        d = I[road]
        dx, dy = math.sin(math.radians(azimuth)), math.cos(math.radians(azimuth))
        pis = [[px - dx * d["leg"], py - dy * d["leg"]], [px + dx * d["leg"], py + dy * d["leg"]]]
        check(s.execute("create_alignment", {"name": d["name"], "begin_station": d["begin"],
                                             "pis": pis}))
        check(s.execute("draw_alignment", {"alignment": d["name"], "layer": "V-ALIGN-CNTR"}))
    for name, east, north in I["corners"]:
        g = corner_geometry(name)
        done = name != I["open"]
        main_from = g["main_station"] if done else g["main_corner_station"]
        cross_from = g["cross_station"] if done else g["cross_corner_station"]
        main_end = I["main"]["begin"] + I["main"]["leg"] * (2 if east > 0 else 0)
        cross_end = I["cross"]["begin"] + I["cross"]["leg"] * (2 if north > 0 else 0)
        check(s.execute("draw_offset", {
            "alignment": I["main"]["name"], "offsets": [g["main_offset"]], "layer": "V-ROAD-EOP",
            "station_range": sorted([main_from, main_end])}))
        check(s.execute("draw_offset", {
            "alignment": I["cross"]["name"], "offsets": [g["cross_offset"]], "layer": "V-ROAD-EOP",
            "station_range": sorted([cross_from, cross_end])}))
        if done:
            check(s.execute("draw_arc", {
                "space": "model", "layer": "V-ROAD-EOP", "center": g["center"],
                "radius": g["radius"], "start_angle_deg": g["start_deg"],
                "end_angle_deg": g["end_deg"]}))
    path = out / INTERSECTION_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def _middle_tangent(session: Session, offset: float):
    """The straight piece of an SR-100 offset between the two curves."""
    from roaddraft.document.entities import Line
    x_lo, x_hi = PIS[1][0], PIS[2][0]
    for e in session.doc.model_entities.values():
        if isinstance(e, Line) and e.anchor and e.anchor.get("offset") == offset:
            mid_x = (e.start[0] + e.end[0]) / 2.0
            if x_lo < mid_x < x_hi:
                return e
    raise RuntimeError(f"no middle tangent at offset {offset}")


def build_flawed(out: Path) -> Path:
    """The SR-100 model with three mistakes planted for a QA probe: one piece
    of the right edge of pavement redrawn by hand at 11 ft, one piece of the
    left shoulder on the pavement layer, and a callout that calls the right
    shoulder the edge of pavement."""
    model = build_model(out)
    s = Session.load(model, out_dir=out)
    a = s.doc.design.alignments[ALIGNMENT]
    # 1. the right edge between the curves, 1 ft in, as a raw line: no anchor,
    #    no provenance, the way a hand-drawn fix looks
    piece = _middle_tangent(s, EDGE_OFFSETS[1])
    st0 = a.xy_to_station(piece.start)["station"]
    st1 = a.xy_to_station(piece.end)["station"]
    check(s.execute("delete_entities", {"ids": [piece.id]}))
    check(s.execute("draw_line", {
        "space": "model", "layer": "V-ROAD-EOP",
        "start": a.station_to_xy(st0, FLAWS["edge_offset"])[0],
        "end": a.station_to_xy(st1, FLAWS["edge_offset"])[0]}))
    # 2. the left shoulder between the curves, on the wrong layer
    shoulder = _middle_tangent(s, SHOULDER_OFFSETS[0])
    check(s.execute("modify_entity", {"id": shoulder.id, "changes": {"layer": "V-ROAD-EOP"}}))
    # 3. a callout on the first tangent that names the right shoulder wrongly
    from roaddraft.document.entities import Line
    first = next(e for e in s.doc.model_entities.values()
                 if isinstance(e, Line) and e.anchor
                 and e.anchor.get("offset") == SHOULDER_OFFSETS[1]
                 and (e.start[0] + e.end[0]) / 2.0 < PIS[1][0])
    tip = a.station_to_xy(1800.0, SHOULDER_OFFSETS[1])[0]
    check(s.execute("place_callout", {
        "space": "model", "target_entity": first.id, "at": 0.5,
        "position": [tip[0] + 120.0, tip[1] - 160.0], "content": FLAWS["callout_text"],
        "layer": "V-ANNO-TEXT"}))
    path = out / FLAWED_FILE
    check(s.query("save_document", {"path": str(path)}))
    return path


def start_document(out: Path, start: str = "sheets") -> Path:
    """Build the fixture under ``out`` and return the document a probe with
    this ``start`` hands to the agent."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if start == "blank":
        return build_blank(out)
    if start == "centerline":
        return build_centerline(out)
    if start == "intersection":
        return build_intersection(out)
    if start == "flawed":
        return build_flawed(out)
    if start not in START:
        raise KeyError(f"no start document {start!r}; one of {sorted(START)}")
    model_path, sheet_path = build(out)
    return model_path if start == "model" else sheet_path


def build(out: Path) -> Tuple[Path, Path]:
    """``(model path, sheet path)``, created fresh under ``out``."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = build_model(out)
    return model_path, build_sheets(out, model_path)


__all__ = ["START", "BLANK_FILE", "CENTERLINE_FILE", "INTERSECTION_FILE", "FLAWED_FILE",
           "INTERSECTION", "FLAWS", "corner_geometry", "build_intersection", "build_flawed",
           "build_blank", "build_centerline",
           "start_document", "PIS", "BEGIN_STATION", "EDGE_OFFSETS", "SHOULDER_OFFSETS", "ALIGNMENT",
           "LAYERS", "SHEETS", "FEET_PER_INCH", "VIEWPORT", "MODEL_FILE", "SHEET_FILE",
           "build", "build_model", "build_sheets"]
