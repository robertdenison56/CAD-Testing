"""The seeded D1 task generator (spec section 7.4).

``generate_task(seed)`` draws a plausible two-lane alignment (radii above the
AASHTO minimum for the design speed, deflections 15-60 degrees, tangents with
room for the curves), an optional station equation, a profile whose grades
and K values satisfy the DRAFT standards tables, project metadata, and a
single-sheet deliverable that fits an ANSI D plan window at 1"=50' or
1"=100'.  Only ``random.Random(seed)`` is consulted (no global RNG, no
clock), so the same seed always yields byte-identical briefs, truths and
task ids.  The fit loop shrinks the design deterministically (no new draws)
until it fits the sheet.
"""
from __future__ import annotations

import datetime as _dt
import math
import random
from typing import List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.angles import direction_of, unit_vector
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.labels import curve_table_rows
from roaddraft.design.model import DesignModel
from roaddraft.design.stations import build_equations
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document.document import Document
from roaddraft.document.entities import Table
from roaddraft.document.sheets import SHEET_SIZES, Sheet
from roaddraft.tasks.brief import GENERATOR_VERSION, Task, TaskBrief, compute_task_id
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash, spec_subset
from roaddraft.tasks.standards import max_grade, min_k, min_radius

SPEEDS = [35, 40, 45, 50, 55]
CURVE_COUNTS = [1, 2, 2, 3]
ROUTES = ["SR 12", "SR 118", "US 41", "CR 7", "SR 260"]
PROJECTS = ["RESURFACING", "REALIGNMENT", "WIDENING", "SAFETY IMPROVEMENTS"]
AGENCIES = ["STATE DOT DISTRICT 4", "COUNTY ENGINEER", "STATE DOT DISTRICT 7"]
COUNTIES = ["HARLAN COUNTY", "MERCER COUNTY", "LINCOLN COUNTY", "CLAY COUNTY", "PIKE COUNTY"]
EQUATION_JUMPS = [100, 200, 300, 500]
MIN_EXTRA_FT = 80.0
FIT_ATTEMPTS = 10
PAD_FT = 100.0
CORNER_INSET_IN = 0.25
BEARING_OFFSET_FACTOR = 2.5  # bearing labels sit 2.5 label offsets off the tangent
ALIGNMENT_NAME = "ALIGN-1"
PROFILE_NAME = "PROF-1"


def _round2(v: float) -> float:
    return round(float(v), 2)


def _build_pis(x0: float, y0: float, d0: float, radii: List[float], deltas: List[float],
               turns: List[str], extras: List[float]) -> List[PI]:
    """PIs from an origin, initial heading, curve parameters and tangent extras."""
    n = len(radii)
    tl = [r * math.tan(math.radians(dl) / 2.0) for r, dl in zip(radii, deltas)]
    lengths = [round(tl[0] + extras[0])]
    for k in range(1, n):
        lengths.append(round(tl[k - 1] + tl[k] + extras[k]))
    lengths.append(round(tl[-1] + extras[n]))
    pts = [[x0, y0]]
    d = d0
    for k in range(n):
        u = unit_vector(d)
        p = pts[-1]
        pts.append([_round2(p[0] + lengths[k] * u[0]), _round2(p[1] + lengths[k] * u[1])])
        d += deltas[k] if turns[k] == "L" else -deltas[k]
    u = unit_vector(d)
    p = pts[-1]
    pts.append([_round2(p[0] + lengths[-1] * u[0]), _round2(p[1] + lengths[-1] * u[1])])
    return [PI(pts[0], 0.0)] + [PI(pts[k + 1], radii[k]) for k in range(n)] + [PI(pts[-1], 0.0)]


def _fits(align: Alignment) -> Optional[int]:
    fit_w, fit_h = DRAFTING_SPEC_V1["sheet"]["fit_window_in"]
    bb = geo.bbox_expand(align.bbox(), PAD_FT)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    for fpi in DRAFTING_SPEC_V1["sheet"]["allowed_feet_per_inch"]:
        if w <= fit_w * fpi and h <= fit_h * fpi:
            return int(fpi)
    return None


def _table_size(align: Alignment, columns: List[str], text_height: float) -> Tuple[float, float]:
    _headers, rows, widths = curve_table_rows(align, columns)
    w = sum(widths)
    h = text_height * (Table.TITLE_FACTOR + Table.ROW_FACTOR * (len(rows) + 1))
    return w, h


def _curve_table_position(align: Alignment, sheet: Sheet, viewport: dict, columns: List[str],
                          text_height: float) -> List[float]:
    """First candidate corner (bottom-right, top-right, bottom-left, top-left)
    whose table rect clears the alignment (mapped to paper, padded 1 in) and
    the north arrow; fallback bottom-right."""
    w, h = _table_size(align, columns, text_height)
    ua = sheet.usable_area()
    x0, y0, x1, y1 = (ua[0] + CORNER_INSET_IN, ua[1] + CORNER_INSET_IN,
                      ua[2] - CORNER_INSET_IN, ua[3] - CORNER_INSET_IN)
    candidates = [[x1 - w, y0 + h], [x1 - w, y1], [x0, y0 + h], [x0, y1]]
    t = geo.ViewportTransform(viewport["center_paper"], viewport["model_center"],
                              viewport["feet_per_inch"], viewport.get("rotation_deg", 0.0))
    mb = align.bbox()
    corners = [[mb[0], mb[1]], [mb[2], mb[1]], [mb[2], mb[3]], [mb[0], mb[3]]]
    obstacles = [geo.bbox_expand(geo.bbox_of_points([t.to_paper(c) for c in corners]), 1.0)]
    na = DRAFTING_SPEC_V1["sheet"]["north_arrow"]
    px, py, sc = na["position"][0], na["position"][1], na["scale"]
    obstacles.append((px - 1.2 * sc, py - 1.2 * sc, px + 1.2 * sc, py + 1.8 * sc))
    for cand in candidates:
        rect = (cand[0], cand[1] - h, cand[0] + w, cand[1])
        if not any(geo.bbox_intersects(rect, ob) for ob in obstacles):
            return [_round2(cand[0]), _round2(cand[1])]
    return [_round2(candidates[0][0]), _round2(candidates[0][1])]


def _profile(rng: random.Random, align: Alignment, v_mph: int) -> Profile:
    begin, end = float(align.begin_station), float(align.end_station)
    length = end - begin
    stations = [begin]
    remaining = length
    while remaining - 600.0 >= 600.0:
        s = min(round(rng.uniform(600.0, 1000.0)), remaining - 600.0)
        stations.append(stations[-1] + s)
        remaining -= s
    stations.append(end)
    n_seg = len(stations) - 1
    elev0 = round(rng.uniform(100.0, 500.0), 2)
    gmax_tenths = int(max_grade(v_mph) * 10)
    grades = [rng.choice([-1, 1]) * rng.randrange(5, gmax_tenths + 1) / 1000.0
              for _ in range(n_seg)]
    lengths = [0.0] * (n_seg + 1)
    for k in range(1, n_seg):
        g_in, g_out = grades[k - 1], grades[k]
        step = 0.001
        if abs(g_out - g_in) < 1e-9:
            g_out += step
        while True:
            a_pct = abs(g_out - g_in) * 100.0
            vtype = "crest" if g_out < g_in else "sag"
            vc_len = max(200.0, math.ceil(min_k(v_mph, vtype) * a_pct / 50.0) * 50.0)
            if vc_len <= 500.0:
                break
            g_out -= step if g_out > g_in else -step  # move g_out toward g_in
            if abs(g_out) < 0.0005:  # grades are never zero
                g_out -= step if g_out > g_in else -step
        grades[k] = g_out
        lengths[k] = vc_len
    elevations = [elev0]
    for k in range(n_seg):
        elevations.append(elevations[-1] + grades[k] * (stations[k + 1] - stations[k]))
    pvis = [PVI(station=st, elevation=el, length=ln)
            for st, el, ln in zip(stations, elevations, lengths)]
    profile = Profile(name=PROFILE_NAME, alignment=align.name, pvis=pvis,
                      description=f"finished grade, V = {v_mph} mph")
    profile.validate()
    return profile


def generate_task(seed: int, curves: Optional[int] = None, equations: bool = False,
                  design_speed_mph: Optional[int] = None, level: str = "D1") -> Task:
    """Generate a deterministic D1 plan-sheet task from ``seed``."""
    rng = random.Random(int(seed))
    v_mph = int(design_speed_mph) if design_speed_mph else rng.choice(SPEEDS)
    n = rng.choice(CURVE_COUNTS) if curves is None else int(curves)
    if n < 1:
        raise ValueError("curves must be >= 1")
    r_min = min_radius(v_mph)
    x0 = round(rng.uniform(5000.0, 20000.0), 2)
    y0 = round(rng.uniform(5000.0, 20000.0), 2)
    d0 = float(rng.randrange(0, 360))
    radii, deltas, turns = [], [], []
    for _ in range(n):
        radii.append(math.ceil(r_min * rng.uniform(1.15, 2.5) / 50.0) * 50.0)
        deltas.append(rng.randrange(30, 121) / 2.0)
        turns.append(rng.choice(["L", "R"]))
    extras = [rng.uniform(250.0, 600.0)]
    extras += [rng.uniform(200.0, 600.0) for _ in range(n - 1)]
    extras.append(rng.uniform(250.0, 600.0))
    r_floor = math.ceil(r_min * 1.15 / 50.0) * 50.0

    # ---- fit loop: deterministic shrinking, no new draws
    fpi = None
    warnings: List[str] = []
    for attempt in range(FIT_ATTEMPTS + 1):
        pis = _build_pis(x0, y0, d0, radii, deltas, turns, extras)
        elements = compile_pis(pis)
        align = Alignment(name=ALIGNMENT_NAME, elements=elements, pis=pis, source="pis")
        fpi = _fits(align)
        if fpi is not None:
            break
        if attempt == FIT_ATTEMPTS:
            raise AssertionError(f"generator bug: seed {seed} never fit the sheet window")
        extras = [max(MIN_EXTRA_FT, e * 0.7) for e in extras]
        deltas = [max(15.0, math.floor(d * 0.85 * 2.0) / 2.0) for d in deltas]
        radii = [max(r_floor, math.ceil(r * 0.85 / 50.0) * 50.0) for r in radii]
        if attempt >= 4:  # lay the BEGIN-END chord along the sheet
            chord = direction_of(pis[0].point, pis[-1].point)
            d0 = (d0 - chord) % 360.0
    assert fpi is not None

    begin_station = 100.0 * rng.randrange(10, 200)
    align.begin_station = begin_station

    # ---- station equation on the longest tangent
    eq_items = []
    if equations:
        tangents = align.tangents()
        t = max(tangents, key=lambda el: el.length)
        start_sta = begin_station + t.start_dist
        end_sta = start_sta + t.length
        back = math.ceil((start_sta + 50.0) / 100.0) * 100.0
        if back <= end_sta - 50.0:
            ahead = back + rng.choice(EQUATION_JUMPS)
            eq_items.append({"back": back, "ahead": ahead})
        else:
            warnings.append("no station equation: the longest tangent has no even station "
                            "50 ft clear of both ends")
    align.equations = build_equations(begin_station, align.length, eq_items)

    profile = _profile(rng, align, v_mph)

    # ---- project metadata
    route = rng.choice(ROUTES)
    kind = rng.choice(PROJECTS)
    agency = rng.choice(AGENCIES)
    county = rng.choice(COUNTIES)
    date = (_dt.date(2026, 1, 1) + _dt.timedelta(days=int(seed) % 365)).isoformat()
    project = {"name": f"{route} {kind}", "agency": agency, "route": route, "county": county,
               "design_speed_mph": v_mph, "designed_by": "RD", "drawn_by": "AGENT",
               "checked_by": "RD", "date": date}

    # ---- deliverable
    spec = DRAFTING_SPEC_V1
    sheet_spec = spec["sheet"]
    size = sheet_spec["size"]
    width, height = SHEET_SIZES[size]
    sheet_name = "C-101"
    sheet = Sheet(id="SH-001", name=sheet_name, size=size, width_in=width, height_in=height)
    mb = align.bbox()
    viewport = {"center_paper": list(sheet_spec["viewport"]["center_paper"]),
                "width_in": sheet_spec["viewport"]["width_in"],
                "height_in": sheet_spec["viewport"]["height_in"],
                "model_center": [_round2((mb[0] + mb[2]) / 2.0), _round2((mb[1] + mb[3]) / 2.0)],
                "feet_per_inch": float(fpi), "rotation_deg": 0.0}
    columns = list(spec["curve_table"]["columns"])
    table_h = spec["text"]["table_height_in"]
    scale_text = sheet_spec["scale_text_format"].format(fpi=fpi)
    deliverable = {
        "sheet_name": sheet_name, "sheet_size": size, "feet_per_inch": float(fpi),
        "viewport": viewport,
        "stationing_interval_ft": spec["stationing"]["interval_ft"],
        "station_format": spec["stationing"]["format"],
        "required_label_kinds": ["station", "pc", "pt", "bearing", "mc", "curve_table"],
        "curve_table_columns": columns,
        "curve_table_position": _curve_table_position(align, sheet, viewport, columns, table_h),
        "text_heights": {"model_label_ft": _round2(spec["text"]["label_height_in"] * fpi),
                         "sheet_table_in": table_h},
        "tick_half_len_ft": _round2(spec["stationing"]["tick_half_len_in"] * fpi),
        "label_offset_ft": _round2(spec["stationing"]["label_offset_in"] * fpi),
        # bearings sit outside the station labels (same side) so the two never collide
        "bearing_label_offset_ft": _round2(BEARING_OFFSET_FACTOR
                                           * spec["stationing"]["label_offset_in"] * fpi),
        "north_arrow": True,
        "title_block_fields": {
            "project": project["name"], "agency": agency, "sheet_title": "ROADWAY PLAN",
            "sheet_number": sheet_name, "total_sheets": "1", "designed_by": "RD",
            "drawn_by": "AGENT", "checked_by": "RD", "date": date, "scale": scale_text},
    }
    if align.equations:
        deliverable["required_label_kinds"].append("equation")
    design = {"design_speed_mph": v_mph,
              "alignments": {ALIGNMENT_NAME: align.to_dict()},
              "profiles": {PROFILE_NAME: profile.to_dict()}}
    payload = {"generator_version": GENERATOR_VERSION, "spec_hash": spec_hash(),
               "project": project, "design": design, "deliverable": deliverable}
    task_id = compute_task_id(int(seed), level, payload)
    instructions = (
        f"Draft plan sheet {sheet_name} ({size}, {scale_text}) showing alignment "
        f"{ALIGNMENT_NAME} in full: draw the alignment on {spec['layers']['alignment']}, "
        f"station ticks and labels every {spec['stationing']['interval_ft']} ft, BC/EC labels, "
        f"a bearing on every tangent, a C-n callout at every mid-curve, "
        f"{'the station equation label, ' if align.equations else ''}a curve data table on the "
        f"sheet, a north arrow, and a filled title block. Use anchored labels (place_label), "
        f"never raw text.")
    if warnings:
        instructions += " Note: " + "; ".join(warnings) + "."
    brief = TaskBrief(task_id=task_id, seed=int(seed), level=level,
                      generator_version=GENERATOR_VERSION, spec_version=SPEC_VERSION,
                      spec_hash=spec_hash(), project=project, design=design,
                      deliverable=deliverable, drafting_spec=spec_subset(),
                      instructions=instructions)

    # ---- baseline document with the design pre-seeded
    doc = Document.new(project["name"])
    doc.design = DesignModel.from_dict({"alignments": design["alignments"],
                                        "profiles": design["profiles"]})
    doc.meta.update(task_id=task_id, spec_version=SPEC_VERSION, design_speed_mph=v_mph,
                    description=f"{project['name']} — {county}, {agency}")
    baseline = doc.to_dict()
    truth = compute_ground_truth(brief)
    return Task(brief=brief, truth=truth, baseline=baseline)


__all__ = ["generate_task", "ALIGNMENT_NAME", "PROFILE_NAME", "SPEEDS", "CURVE_COUNTS"]
