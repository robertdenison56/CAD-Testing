"""Pilot 10: a typical section drawn from a written description.

A typical section is the one roadway drawing with no alignment to hang it on:
the engineer describes lanes, shoulders, cross slopes, the pavement layers and
the side slopes, and the drafter turns that into geometry, finds where each
side slope catches the existing ground, and dimensions and labels it. The
engine has no typical-section command, so every vertex is the model's own
arithmetic or construction (offsets, intersections with ``extend`` or
``key_points``), and the catch points depend on the ground line it is given.

Both instances start from a real example sheet with its main section stripped
(border, title block, notes, the other details and the section's own title
kept), plus an existing-ground polyline drawn in the sheet file's model space.
The published sections are NO SCALE; here the prompt fixes the frame instead:
the section is drawn in model space at true scale, x the offset from the
centreline in feet (right positive) and y the elevation, and shown on the
sheet through a viewport at 1" = 10', horizontal and vertical. It is graded in
model feet. Slopes are V:H, as FLH sheets write them, and the prompt says so.

* ``p10-typical-cfl01`` -- CFL sheet A6 (TYPICAL SECTION MAINLINE), the section
  for 10+00 to 37+50 and 38+25 to 47+30: 10' lanes, 2' shoulders, 2 % crown,
  3" AC on 6" aggregate base, a 1:4 aggregate shoulder to the hinge 15' out,
  1:3 fill on the right and on the left the 1:4 carried 4' past the hinge to a
  graded ditch and a 1:2 cut slope. Ground at 24+00, PG 1,186.42.
* ``p10-typical-wfl07`` -- WFL sheet C.1 (YELL 12(2)), the MAIN 01 section for
  394+00 to 401+07: 11' lanes, 4' shoulders, 2 % crown, 24" of surfacing in
  four layers (6" AC, 4" aggregate base grading D, 4" recycled aggregate base,
  10" select borrow), a 1:2 foreslope from the shoulder edge through the
  surfacing to the subgrade (the hinge, 19.17' out and 2.38' down, found by
  intersection), 1:6 fill on the right, and on the left a ditch 1' below the
  hinge with a 1:3 backslope. Ground at 397+50, PG 6,241.36.

What makes it hard: the hinge and catch points are intersections, not given
numbers (a fill slope run "to existing ground" has to stop on the drawn
ground line); the 2 % is a drop of 0.20-0.30 ft that a sketchy section skips;
layer depths are inches in one description; and the sheet half is a layout
decision in a crowded sheet (scale, a clear place, above the title).

Graded (all in model feet, from the submitted document only):
  * every finished-grade break (centreline crown, shoulder edges, hinge,
    ditch bottom) is a vertex of the added linework within 0.05 ft;
  * each catch point, where the side slope meets the given ground line, is a
    vertex within 0.05 ft;
  * each pavement layer's bottom has added linework within 0.03 ft of it at
    four offsets across the lanes and shoulders;
  * dimension entities reading the lane width and the shoulder width;
  * text giving the cross slope (2 %) and each side slope ratio in V:H;
  * a viewport on the sheet at 1" = 10', untwisted, that shows the section
    from catch point to catch point, inside the border above the title strip
    and clear of the sheet's remaining notes and details.

Three more sections (2026-11, FDOT 913-2 divided, WFL JEFF sidehill with slope
tables, WFL ADA superelevated) are described where they are defined, at the
end of this module; their specs carry ``v2`` and may set their own dims, cross
slopes, viewport scale and paper area.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.document import dimgeom
from roaddraft.document.entities import (
    Dimension, Hatch, Line, Polyline, Text, entity_distance,
)
from roaddraft.document.fileformat import read_document, write_document
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common

VERTEX_FT = 0.05
LAYER_FT = 0.03
WIDTH_FT = 0.05
SCALE_FT_PER_IN = 10.0
EG_LAYER = "XS_EXISTING_GROUND"
#: paper the viewport may use: inside the WFL border, above its title strip
#: (C.1 carries that strip as a line at y = 1.3; A6's title box is below it)
PAPER_AREA = (0.7, 1.3, 16.3, 10.7)


# ------------------------------------------------------------------ geometry


def _catch(start: Sequence[float], dx_sign: int, slope: float, ground) -> List[float]:
    """Where a slope from ``start`` running ``dx_sign`` (+1 right, -1 left) and
    changing elevation by ``slope`` ft per ft of horizontal run meets the
    ground polyline."""
    x0, y0 = start
    for (ax, ay), (bx, by) in zip(ground, ground[1:]):
        g = (by - ay) / (bx - ax)
        # y0 + slope*dx_sign*(x - x0) = ay + g*(x - ax)
        k = slope * dx_sign - g
        if abs(k) < 1e-12:
            continue
        x = (ay - g * ax - y0 + slope * dx_sign * x0) / k
        if min(ax, bx) - 1e-9 <= x <= max(ax, bx) + 1e-9 and (x - x0) * dx_sign > 0:
            return [x, y0 + slope * dx_sign * (x - x0)]
    raise ValueError("the slope never meets the ground line")


def _fg_at(vertices, x: float) -> float:
    for (ax, ay), (bx, by) in zip(vertices, vertices[1:]):
        if ax <= x <= bx:
            return ay + (by - ay) * (x - ax) / (bx - ax)
    raise ValueError(f"offset {x} is off the section")


def cfl_truth() -> dict:
    """CFL A6: crown, shoulder edges at 12', 1:4 to the hinge at 15', 1:3 fill
    right, the 1:4 carried to a ditch at 19' left and a 1:2 cut slope."""
    pg = CFL["pg"]
    ground = [[x, pg + dy] for x, dy in CFL["ground"]]
    es = pg - 0.02 * 12.0
    hinge = es - 3.0 / 4.0
    ditch = [-19.0, hinge - 1.0]
    right_hinge = [15.0, hinge]
    left_catch = _catch(ditch, -1, 1.0 / 2.0, ground)
    right_catch = _catch(right_hinge, +1, -1.0 / 3.0, ground)
    breaks = [("ditch bottom", ditch), ("left shoulder edge", [-12.0, es]),
              ("centreline crown", [0.0, pg]), ("right shoulder edge", [12.0, es]),
              ("right hinge", right_hinge)]
    fg = [left_catch, ditch, [-12.0, es], [0.0, pg], [12.0, es], right_hinge, right_catch]
    return {"pg": pg, "ground": ground, "breaks": breaks, "catches": [("left catch point (cut)", left_catch),
            ("right catch point (fill)", right_catch)], "fg": fg}


def wfl_truth() -> dict:
    """WFL C.1: crown, shoulder edges at 15', 1:2 foreslope to the subgrade
    (2.0 ft below finished grade, extended) at the hinge, 1:6 fill right, the
    1:2 carried 1 ft below the hinge to the ditch and a 1:3 backslope left."""
    pg = WFL["pg"]
    ground = [[x, pg + dy] for x, dy in WFL["ground"]]
    es = pg - 0.02 * 15.0
    # 1:2 from (15, es) down-out meets the subgrade pg - 2.0 - 0.02 x
    hx = (2.0 - 0.30 + 7.5) / 0.48            # es - 0.5 (x - 15) = pg - 2 - 0.02 x
    hy = pg - 2.0 - 0.02 * hx
    ditch = [-(hx + 2.0), hy - 1.0]
    right_hinge = [hx, hy]
    left_catch = _catch(ditch, -1, 1.0 / 3.0, ground)
    right_catch = _catch(right_hinge, +1, -1.0 / 6.0, ground)
    breaks = [("ditch bottom", ditch), ("left shoulder edge", [-15.0, es]),
              ("centreline crown", [0.0, pg]), ("right shoulder edge", [15.0, es]),
              ("right hinge", right_hinge)]
    fg = [left_catch, ditch, [-15.0, es], [0.0, pg], [15.0, es], right_hinge, right_catch]
    return {"pg": pg, "ground": ground, "breaks": breaks, "catches": [("left catch point (cut)", left_catch),
            ("right catch point (fill)", right_catch)], "fg": fg}


#: the CFL instance: ground as (offset, elevation above PG)
CFL = {
    "id": "p10-typical-cfl01", "sheet_id": "CFL-C-Typical-Sections-Approach-Roads-p01",
    "sheet": "A6", "pg": 1186.42, "station": "24+00",
    "ground": [(-50.0, 4.10), (-38.0, 3.40), (-27.0, 2.20), (-16.0, 0.60), (-4.0, -0.40),
               (8.0, -1.60), (20.0, -3.90), (31.0, -5.60), (50.0, -6.80)],
    "lane": 10.0, "shoulder": 2.0,
    "layers": [("3-inch asphalt concrete", 0.25), ("6-inch aggregate base", 0.75)],
    "layer_offsets": [-9.0, -3.0, 3.0, 9.0],
    "slopes": ["1:4", "1:3", "1:2"],
    "strip": [(0.75, 3.15, 11.5, 7.9)],
    "keep": [(9.0, 2.2, 11.5, 3.7)],           # the MGS guardrail detail
    "clip": [],
    "keep_text": {"TYPICAL SECTION", "10+00 to 37+50", "38+25 to 47+30"},
    "truth": cfl_truth,
}

WFL = {
    "id": "p10-typical-wfl07", "sheet_id": "WFL-Typical-Sections-p07",
    "sheet": "C.1", "pg": 6241.36, "station": "397+50",
    "ground": [(-55.0, 4.60), (-40.0, 3.40), (-28.0, 1.20), (-14.0, 0.20), (0.0, -1.20),
               (14.0, -2.90), (26.0, -4.40), (40.0, -5.90), (60.0, -6.60)],
    "lane": 11.0, "shoulder": 4.0,
    "layers": [("6-inch asphalt concrete pavement", 0.5), ("4-inch aggregate base grading D",
               0.5 + 4.0 / 12.0), ("4-inch recycled aggregate base", 0.5 + 8.0 / 12.0),
               ("10-inch select borrow", 2.0)],
    "layer_offsets": [-13.0, -5.0, 5.0, 13.0],
    "slopes": ["1:2", "1:3", "1:6"],
    "strip": [(0.7, 1.35, 16.3, 4.28)],
    "keep": [],
    #: the dashed shoulder-edge lines that ran from the parking details down to
    #: the NO SCALE section's shoulders: cut back to the details, since a section
    #: at 1" = 10' cannot meet them
    "clip": ["LN-016", "LN-017"],
    "keep_text": {'"MAIN 01"', "394+00 to 401+07"},
    "truth": wfl_truth,
}


# ------------------------------------------------------------------ the start


def _inside(bb, box) -> bool:
    return bb[0] >= box[0] and bb[1] >= box[1] and bb[2] <= box[2] and bb[3] <= box[3]


def _build(spec: dict, out: Path) -> Path:
    """Stage the sheet, strip its section (what lies wholly inside the strip
    boxes, but not the kept detail or the section's title), and draw the
    existing ground in the sheet file's model space."""
    files = common.stage(out, spec["sheet_id"])
    path = files[common.sheet_file(spec["sheet_id"])]
    session = common.load(path)
    doc = session.doc
    sheet = doc.sheet_by_ref(spec["sheet"])
    for eid, e in list(sheet.entities.items()):
        bb = e.bbox(doc)
        if not bb or not any(_inside(bb, box) for box in spec["strip"]):
            continue
        if any(_inside(bb, box) for box in spec["keep"]):
            continue
        if isinstance(e, Text) and e.content.strip() in spec["keep_text"]:
            continue
        del sheet.entities[eid]
    top = max(box[3] for box in spec["strip"])
    for eid in spec["clip"]:
        line = sheet.entities[eid]
        low = 0 if line.start[1] < line.end[1] else 1
        ends = [list(line.start), list(line.end)]
        ends[low][1] = top
        line.start, line.end = ends
    common.save(session, path)
    session = common.load(path)
    common.ok(session.execute("create_layer", {"name": EG_LAYER, "color": "black",
                                               "linetype": "dashed",
                                               "description": f"existing ground at {spec['station']}"}))
    common.ok(session.execute("draw_polyline", {
        "space": "model", "layer": EG_LAYER,
        "vertices": [[x, round(spec["pg"] + dy, 2)] for x, dy in spec["ground"]]}))
    common.save(session, path)
    return path


# ------------------------------------------------------------------ checking


def _added(baseline: Session, submitted: Session):
    """``(space, entity)`` the submission added, model space and the sheets."""
    before = set(baseline.doc.model_entities)
    for s in baseline.doc.sheets.values():
        before |= set(s.entities)
    out = [("model", e) for k, e in submitted.doc.model_entities.items() if k not in before]
    for s in submitted.doc.sheets.values():
        out += [(s.name, e) for k, e in s.entities.items() if k not in before]
    return out


def _vertices(entities) -> List[List[float]]:
    pts = []
    for e in entities:
        if isinstance(e, Line):
            pts += [list(e.start), list(e.end)]
        elif isinstance(e, Polyline):
            pts += [list(v) for v in e.vertices]
    return pts


def _ratio_pattern(ratio: str):
    v, h = ratio.split(":")
    num = lambda n: rf"{n}(?:\.0+)?"
    return re.compile(rf"(?<![\d.]){num(v)}\s*V?\s*:\s*{num(h)}\s*H?(?![\d.])|"
                      rf"(?<![\d.]){num(h)}\s*H\s*:\s*{num(v)}\s*V", re.I)


CROSS_SLOPE = re.compile(r"(?<![\d.])2(?:\.0+)?\s*%|(?<![\d.])0?\.020*\s*(?:ft/ft|'/')", re.I)


def _percent_pattern(pct: float):
    """A cross slope as written: '6%', '6.0 %', '0.06', '.060 ft/ft' (FDOT
    letters its cross slopes as bare decimals)."""
    whole = f"{pct:g}"
    dec = f"{pct / 100.0:.2f}".lstrip("0")          # 6 -> .06
    return re.compile(rf"(?<![\d.]){re.escape(whole)}(?:\.0+)?\s*%|"
                      rf"(?<![\d.])0?{re.escape(dec)}0*(?![\d])", re.I)


def _dimension_reads(dim: Dimension, width: float) -> bool:
    if dim.text_override:
        return any(abs(float(n) - width) <= WIDTH_FT
                   for n in re.findall(r"\d+(?:\.\d+)?", dim.text_override))
    try:
        return abs(dimgeom.measure(dim) - width) <= WIDTH_FT
    except Exception:
        return False


def check_section(spec: dict, baseline: Session, submitted: Session) -> Result:
    truth = spec["truth"]()
    added = _added(baseline, submitted)
    model = [e for space, e in added if space == "model"]
    lines = [e for e in model if isinstance(e, (Line, Polyline))]
    vertices = _vertices(lines)
    tally = Tally()

    def vertex_item(name, point):
        d = min((math.dist(v, point) for v in vertices), default=math.inf)
        tally.add(f"{name} at [{point[0]:.2f}, {point[1]:.2f}]",
                  None if d <= VERTEX_FT else
                  ("no linework was added in model space" if not vertices else
                   f"the {name} [{point[0]:.2f}, {point[1]:.2f}] has no vertex within "
                   f"{VERTEX_FT} ft (nearest {d:.2f} ft)"))

    for name, point in truth["breaks"]:
        vertex_item(name, point)
    for name, point in truth["catches"]:
        vertex_item(name, point)

    linework = [e for e in model if isinstance(e, (Line, Polyline, Hatch))]
    for layer, depth in spec["layers"]:
        misses = []
        for x in spec["layer_offsets"]:
            p = [x, _fg_at(truth["fg"], x) - depth]
            d = min((entity_distance(submitted.doc, e, p) for e in linework), default=math.inf)
            if d > LAYER_FT:
                misses.append((x, d))
        inches = f"{depth * 12:g}" if spec.get("v2") else f"{depth * 12:.0f}"
        tally.add(f"bottom of the {layer} ({inches} in down)",
                  None if not misses else
                  f"the bottom of the {layer}, {depth:.3f} ft below finished grade, has no "
                  f"linework within {LAYER_FT} ft at offset {misses[0][0]:+.0f} ft "
                  f"(nearest {misses[0][1]:.2f} ft)")

    dims = [e for _space, e in added if isinstance(e, Dimension)]
    for what, width in spec.get("dims") or (("lane", spec["lane"]), ("shoulder", spec["shoulder"])):
        tally.add(f"{what} width dimensioned ({width:g}')",
                  None if any(_dimension_reads(d, width) for d in dims) else
                  f"no dimension reads the {width:g}' {what} width"
                  + ("" if dims else " (no dimensions were added)"))

    texts = [e.content for _space, e in added if isinstance(e, Text)]
    if spec.get("cross_slopes"):
        for pct in spec["cross_slopes"]:
            pattern = _percent_pattern(pct)
            tally.add(f"cross slope labelled ({pct:g}%)",
                      None if any(pattern.search(t) for t in texts) else
                      f"no text gives the {pct:g}% cross slope")
    else:
        tally.add("cross slope labelled (2%)",
                  None if any(CROSS_SLOPE.search(t) for t in texts) else "no text gives the 2% cross slope")
    for ratio in spec["slopes"]:
        pattern = _ratio_pattern(ratio)
        tally.add(f"side slope labelled ({ratio})",
                  None if any(pattern.search(t) for t in texts) else
                  f"no text gives the {ratio} slope (V:H)")

    tally.add(f"viewport at 1\" = {spec.get('scale', SCALE_FT_PER_IN):g}' showing the section, "
              f"clear of the sheet's notes", _viewport_problem(spec, baseline, submitted, truth))
    return tally.result(f"section drawn to the description: catch points "
                        f"{truth['catches'][0][1][0]:.2f} and {truth['catches'][1][1][0]:.2f} ft, "
                        f"shown at 1\" = {spec.get('scale', SCALE_FT_PER_IN):g}'")


def _viewport_problem(spec, baseline, submitted, truth) -> Optional[str]:
    sheet = submitted.doc.sheet_by_ref(spec["sheet"])
    if sheet is None:
        return f"sheet {spec['sheet']} is gone"
    ports = sheet.viewports
    ports = list(ports.values()) if isinstance(ports, dict) else list(ports)
    if not ports:
        return f"no viewport on sheet {spec['sheet']}"
    base_sheet = baseline.doc.sheet_by_ref(spec["sheet"])
    notes = [e.bbox(baseline.doc) for e in base_sheet.entities.values() if isinstance(e, Text)]
    must_show = [truth["catches"][0][1], truth["catches"][1][1], [0.0, truth["pg"]]]
    problems = []
    for vp in ports:
        if abs(vp.feet_per_inch - spec.get("scale", SCALE_FT_PER_IN)) > 1e-6:
            problems.append(f"viewport {vp.id} is at 1\" = {vp.feet_per_inch:g}'")
            continue
        if abs(((vp.rotation_deg + 180.0) % 360.0) - 180.0) > 0.01:
            problems.append(f"viewport {vp.id} is twisted {vp.rotation_deg:g}°")
            continue
        half_w = vp.width_in * vp.feet_per_inch / 2.0
        half_h = vp.height_in * vp.feet_per_inch / 2.0
        cx, cy = vp.model_center
        unseen = [p for p in must_show if not (cx - half_w <= p[0] <= cx + half_w
                                               and cy - half_h <= p[1] <= cy + half_h)]
        if unseen:
            problems.append(f"viewport {vp.id} does not show [{unseen[0][0]:.1f}, "
                            f"{unseen[0][1]:.1f}]")
            continue
        px, py = vp.center_paper
        rect = (px - vp.width_in / 2, py - vp.height_in / 2, px + vp.width_in / 2,
                py + vp.height_in / 2)
        if not _inside(rect, spec.get("paper_area", PAPER_AREA)):
            problems.append(f"viewport {vp.id} runs outside the border or into the title strip")
            continue
        hit = [bb for bb in notes if bb and not (bb[2] <= rect[0] or bb[0] >= rect[2]
                                                 or bb[3] <= rect[1] or bb[1] >= rect[3])]
        if hit:
            problems.append(f"viewport {vp.id} covers the sheet's own notes "
                            f"(text at [{hit[0][0]:.2f}, {hit[0][1]:.2f}] in)")
            continue
        return None
    return "; ".join(problems)


# ------------------------------------------------------------------ solving


def solve_section(spec: dict, session: Session) -> None:
    """Draft it the way a drafter would: finished grade through the breaks,
    each side slope extended to the ground line, the layer bottoms offset from
    finished grade, dimensions and labels in model space, then a viewport."""
    truth = spec["truth"]()
    pg = truth["pg"]
    run = lambda name, params: common.ok(session.execute(name, params))
    for name, color in (("XS_FINISHED_GRADE", "black"), ("XS_PAVEMENT", "black"),
                        ("XS_ANNO", "black")):
        session.execute("create_layer", {"name": name, "color": color})
    breaks = [p for _n, p in truth["breaks"]]
    # finished grade between the breaks, then each side slope run out past the
    # ground line and cut back to it with extend (start short of it)
    fg = run("draw_polyline", {"space": "model", "layer": "XS_FINISHED_GRADE",
                               "vertices": breaks})["created"][0]
    ground = session.query("find_entities", {"layer": EG_LAYER})["entities"][0]["id"]
    left, right = truth["catches"][0][1], truth["catches"][1][1]
    for start, catch in ((breaks[0], left), (breaks[-1], right)):
        # a stub along the slope, extended to the ground line
        stub = [start[0] + (catch[0] - start[0]) * 0.5, start[1] + (catch[1] - start[1]) * 0.5]
        ln = run("draw_line", {"space": "model", "layer": "XS_FINISHED_GRADE",
                               "start": start, "end": stub})["created"][0]
        run("extend", {"targets": [{"id": ln, "end": "end"}], "boundaries": [ground]})
    # layer bottoms under the lanes and shoulders; on C.1 each runs out to
    # the 1:2 foreslope (es - (x - es)/2 = pg - d - 0.02 x)
    es = spec["lane"] + spec["shoulder"]
    for _layer, depth in spec["layers"]:
        edge = es if spec is CFL else (0.5 * es - 0.02 * es + depth) / 0.48
        run("draw_polyline", {"space": "model", "layer": "XS_PAVEMENT",
                              "vertices": [[-edge, pg - depth - 0.02 * edge],
                                           [0.0, pg - depth],
                                           [edge, pg - depth - 0.02 * edge]]})
    # widths above the section, the narrow shoulders a step higher so the
    # numbers stay apart
    y_dim = pg + 3.0
    for x0, x1, y in ((-es, -spec["lane"], y_dim + 1.5), (-spec["lane"], 0.0, y_dim),
                      (0.0, spec["lane"], y_dim), (spec["lane"], es, y_dim + 1.5)):
        run("place_dimension", {"space": "model", "layer": "XS_ANNO", "kind": "linear",
                                "p1": [x0, _fg_at(truth["fg"], x0)],
                                "p2": [x1, _fg_at(truth["fg"], x1)],
                                "line_point": [(x0 + x1) / 2.0, y], "text_height": 1.0})
    run("place_text", {"space": "model", "layer": "XS_ANNO", "position": [-spec["lane"] / 2, pg + 0.6],
                       "content": "2%", "height": 1.0, "halign": "center"})
    run("place_text", {"space": "model", "layer": "XS_ANNO", "position": [spec["lane"] / 2, pg + 0.6],
                       "content": "2%", "height": 1.0, "halign": "center"})
    labels = _slope_label_points(spec, truth)
    for ratio, point in zip(spec["slopes"], labels):
        run("place_text", {"space": "model", "layer": "XS_ANNO", "position": point,
                           "content": ratio, "height": 1.0, "halign": "center"})
    # the viewport: the section's extents at 1" = 10', above the title
    xs = [left[0], right[0]]
    ys = [p[1] for p in truth["ground"]] + [y_dim + 1.5]
    x_lo, x_hi = min(xs) - 4.0, max(xs) + 4.0
    y_lo = min(min(p[1] for p in truth["fg"]) - 2.5, min(truth["ground"], key=lambda p: abs(p[0] - right[0]))[1] - 1.0)
    y_hi = y_dim + 3.5
    width_in = (x_hi - x_lo) / SCALE_FT_PER_IN
    height_in = (y_hi - y_lo) / SCALE_FT_PER_IN
    run("create_viewport", {"sheet": spec["sheet"], "feet_per_inch": SCALE_FT_PER_IN,
                            "center_paper": list(spec["paper_center"]),
                            "width_in": round(width_in, 2), "height_in": round(height_in, 2),
                            "model_center": [(x_lo + x_hi) / 2.0, (y_lo + y_hi) / 2.0]})


def _slope_label_points(spec: dict, truth: dict) -> List[List[float]]:
    """Where to letter each of the spec's side slopes: the midpoint of the
    piece it names, raised a foot."""
    fg = truth["fg"]
    mid = lambda a, b: [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0 + 1.0]
    if spec is CFL:   # 1:4 shoulder-and-ditch, 1:3 fill, 1:2 cut
        return [mid(fg[1], fg[2]), mid(fg[5], fg[6]), mid(fg[0], fg[1])]
    return [mid(fg[1], fg[2]), mid(fg[0], fg[1]), mid(fg[5], fg[6])]   # 1:2, 1:3, 1:6


CFL["paper_center"] = (5.7, 5.4)
WFL["paper_center"] = (8.5, 2.95)


# ------------------------------------------------------------------ prompts

CFL_PROMPT = (
    "Sheet A6 (TYPICAL SECTION MAINLINE) has lost its main typical section, the one for "
    "10+00 to 37+50 and 38+25 to 47+30; only its title is left. Redraw it from this "
    "description as a true-scale section in this file's model space: x is the offset from the "
    "centreline in feet (right positive) and y is the elevation. The existing ground at station "
    "24+00 is already drawn there on layer XS_EXISTING_GROUND, and the profile grade at the "
    "centreline is 1,186.42. Two 10-ft traveled-way lanes and 2-ft paved shoulders, crowned at "
    "the centreline and sloping 2% down both ways (the shoulders on the lane slope). Pavement: "
    "3-inch asphalt concrete placed in two lifts on 6-inch aggregate base, under the lanes and "
    "shoulders. Beyond each shoulder edge the aggregate shoulder slopes 1:4 out to the hinge "
    "point, 15 ft from the centreline. Right side, in fill: a 1:3 fill slope from the hinge down "
    "to existing ground. Left side, in cut: a 4-ft graded ditch, the 1:4 slope carried on 4 ft "
    "past the hinge to the ditch bottom, then a 1:2 cut slope up to existing ground. Slopes are "
    "V:H, as on our sheets. Draw the finished grade from catch point to catch point and the "
    "bottom of each pavement layer, dimension the lane and shoulder widths, and label the cross "
    "slope and each side slope. Then show it on sheet A6 in a viewport at 1\" = 10' "
    "(horizontal and vertical), above its title and clear of the other details and notes.")

WFL_PROMPT = (
    "Sheet C.1 (TYPICAL SECTION) has lost its MAIN 01 section, 394+00 to 401+07; only its title "
    "is left. Redraw it from this description as a true-scale section in this file's model "
    "space: x is the offset from the centreline in feet (right positive) and y is the "
    "elevation. The existing ground at station 397+50 is already drawn there on layer "
    "XS_EXISTING_GROUND, and the profile grade at the centreline is 6,241.36. Two 11-ft "
    "traveled lanes and 4-ft shoulders with a 2% crown both ways (the shoulders on the lane "
    "slope). Surfacing, parallel to the finished grade under the lanes and shoulders, top down: "
    "6-inch asphalt concrete pavement in two equal lifts, 4-inch aggregate base grading D, "
    "4-inch recycled aggregate base and 10-inch select borrow. From each shoulder edge a 1:2 "
    "foreslope runs down through the surfacing to the subgrade (the bottom of the select borrow, "
    "extended); that point is the hinge. Right side, in fill: a 1:6 fill slope from the hinge "
    "down to existing ground. Left side, in cut: the 1:2 foreslope carries on below the hinge to "
    "a ditch bottom 1 ft lower, then a 1:3 backslope rises to existing ground. Slopes are V:H, "
    "as on our sheets. Draw the finished grade from catch point to catch point and the bottom of "
    "each surfacing layer, dimension the lane and shoulder widths, and label the cross slope and "
    "each side slope. Then show it on sheet C.1 in a viewport at 1\" = 10' (horizontal and "
    "vertical), above its title and clear of the other sections and notes.")


def _note(spec: dict, naive: str) -> str:
    t = spec["truth"]()
    pts = "; ".join(f"{n} [{p[0]:.2f}, {p[1]:.2f}]" for n, p in t["breaks"] + t["catches"])
    return f"Truth (x offset, y elevation): {pts}. {naive}"


CFL_START = common.register(CFL["id"], common.sheet_file(CFL["sheet_id"]),
                            lambda out: _build(CFL, out))
WFL_START = common.register(WFL["id"], common.sheet_file(WFL["sheet_id"]),
                            lambda out: _build(WFL, out))

PROBES: List[Probe] = [
    Probe(id=CFL["id"], prompt=CFL_PROMPT, start=CFL_START, tags=["typical-section", "cfl"],
          check=lambda b, s: check_section(CFL, b, s), solve=lambda s: solve_section(CFL, s),
          note=_note(CFL, "Naive answers that fail: the 1:3 fill read as 3:1 (H:V) or run a "
                          "fixed distance instead of to the ground line, the crown skipped "
                          "(flat lanes are 0.24 ft high at the shoulder edge), or the section "
                          "drawn on the sheet in inches.")),
    Probe(id=WFL["id"], prompt=WFL_PROMPT, start=WFL_START, tags=["typical-section", "wfl"],
          check=lambda b, s: check_section(WFL, b, s), solve=lambda s: solve_section(WFL, s),
          note=_note(WFL, "The hinge is the 1:2 foreslope meeting the subgrade 2.0 ft below the "
                          "2% finished grade (19.17 ft out, not 19.0 = 15 + 2 x 2.0). Naive answers "
                          "that fail: the hinge at 19.00, the subgrade drawn level, layer depths "
                          "in inches as feet, the catch points left short of the ground line.")),
]


# ================================================ the sections added 2026-11
#
# Three more sections, each with its own geometry and the same check items
# (the ``v2`` specs: their own dims, cross slopes, scale and paper area):
#
# * ``p10-typical-fdot9132`` -- FDOT sheet 5 (SR 22), a four-lane divided rural
#   section: two roadways sloping 0.02 away from a 40-ft depressed median,
#   profile grade points at the inside edges of the travel lanes, 0.06
#   shoulders, 1:6 median slopes to a ditch at the centreline, a flat-bottom
#   roadside ditch in cut on the left and a 1:6 fill on the right; four
#   travel-lane layers (3/4-inch friction course to 12-inch stabilization).
#   Too wide for 1" = 10' on a B sheet, so the viewport is 1" = 20'.
# * ``p10-typical-wfl04`` -- WFL sheet C.1 (WA FLAP JEFF 1(23)), the sidehill
#   mirror of the existing two: fill on the LEFT and cut on the RIGHT, and the
#   fill and cut slopes are not given -- they come from slope tables by height,
#   so the catch point decides the slope that decides the catch point (1:3 fill
#   at 10.94 ft, 1:2 cut at 5.83 ft; the table's first rows, 1:6 and 1:3, catch
#   25 ft and 8.75 ft away from the right answer).
# * ``p10-typical-wfl05`` -- WFL sheet C.1 (ID FLAP ADA 60(5)), the MAIN 01
#   section through full superelevation: 6% down to the right rotated about
#   the centreline, the inside (right) lane widened 2 ft, the high-side
#   shoulder breaking over to 2% down away from the lanes; no crown.


def _seg_mid(a, b, rise: float = 1.0) -> List[float]:
    return [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0 + rise]


def fdot_truth() -> dict:
    """FDOT 913-2: offsets from the construction centreline (the median's
    centre); the profile grade points 20 ft out at PG."""
    pg = FDOT["pg"]
    ground = [[x, pg + dy] for x, dy in FDOT["ground"]]
    lane_out = pg - 0.02 * 24.0                       # 44 ft out
    sh_out = lane_out - 0.06 * 10.0                   # 54 ft out
    sh_in = pg - 0.06 * 8.0                           # 12 ft out
    median = [0.0, sh_in - 12.0 / 6.0]
    toe = [-54.0 - 3.5 * 6.0, sh_out - 3.5]           # the front slope's foot
    back = [toe[0] - 5.0, toe[1]]                     # the flat bottom's far edge
    left_catch = _catch(back, -1, 1.0 / 4.0, ground)
    right_catch = _catch([54.0, sh_out], +1, -1.0 / 6.0, ground)
    breaks = [("left ditch bottom, back edge", back), ("left ditch bottom, front slope foot", toe),
              ("left outside shoulder edge", [-54.0, sh_out]), ("left travel lane edge", [-44.0, lane_out]),
              ("left profile grade point", [-20.0, pg]), ("left inside shoulder edge", [-12.0, sh_in]),
              ("median ditch", median), ("right inside shoulder edge", [12.0, sh_in]),
              ("right profile grade point", [20.0, pg]), ("right travel lane edge", [44.0, lane_out]),
              ("right outside shoulder edge", [54.0, sh_out])]
    fg = [left_catch] + [p for _n, p in breaks] + [right_catch]

    def lane_line(depth, side):
        return [[side * 20.0, pg - depth], [side * 44.0, lane_out - depth]]
    layer_lines = [line for _n, d in FDOT["layers"] for line in (lane_line(d, -1), lane_line(d, 1))]
    y = pg + 4.0
    dims = [(-54.0, -44.0, y + 2.0), (-44.0, -32.0, y), (-32.0, -20.0, y), (-20.0, -12.0, y + 2.0),
            (12.0, 20.0, y + 2.0), (20.0, 32.0, y), (32.0, 44.0, y), (44.0, 54.0, y + 2.0)]
    labels = [("0.02", [-32.0, pg + 1.0]), ("0.02", [32.0, pg + 1.0]),
              ("0.06", [-49.0, sh_out + 1.4]), ("0.06", [49.0, sh_out + 1.4]),
              ("0.06", [-16.0, pg + 1.0]), ("0.06", [16.0, pg + 1.0]),
              ("1:6", _seg_mid([-12.0, sh_in], median, -2.0)),
              ("1:6", _seg_mid([54.0, sh_out], right_catch, 1.5)),
              ("1:6", _seg_mid([-54.0, sh_out], toe, 1.5)),
              ("1:4", _seg_mid(back, left_catch, 1.5))]
    return {"pg": pg, "ground": ground, "breaks": breaks,
            "catches": [("left catch point (cut)", left_catch), ("right catch point (fill)", right_catch)],
            "fg": fg, "layer_lines": layer_lines, "dims": dims, "labels": labels, "dim_y": y + 2.0}


def _slope_by_height(start, dx_sign, rising: bool, table, ground):
    """The slope a height table picks: for each ratio (V:H run) the catch
    point it makes, kept when the height it makes falls in that ratio's band.
    ``table`` is ``[(upper height or None, run)]`` in order."""
    hits = []
    lower = 0.0
    for upper, run in table:
        slope = (1.0 if rising else -1.0) / run
        try:
            catch = _catch(start, dx_sign, slope, ground)
        except ValueError:
            lower = upper if upper is not None else lower
            continue
        height = abs(catch[1] - start[1])
        if height > lower and (upper is None or height <= upper):
            hits.append((run, catch, height))
        lower = upper if upper is not None else lower
    if len(hits) != 1:
        raise ValueError(f"the slope table picks {len(hits)} slopes")
    return hits[0]


def jeff_truth() -> dict:
    """WFL C.1 (JEFF 1(23)): 12-ft lanes, 2-ft shoulders, 2% crown; a 1:4
    slope from each shoulder edge: on the left to the hinge 4 ft out, then the
    fill slope from the table; on the right on down to a ditch bottom 2 ft
    below the shoulder edge, then the cut slope from the table."""
    pg = JEFF["pg"]
    ground = [[x, pg + dy] for x, dy in JEFF["ground"]]
    es = pg - 0.02 * 14.0
    hinge = [-18.0, es - 1.0]
    ditch = [22.0, es - 2.0]
    fill_run, left_catch, _h = _slope_by_height(hinge, -1, False, JEFF["fill_table"], ground)
    cut_run, right_catch, _h = _slope_by_height(ditch, +1, True, JEFF["cut_table"], ground)
    breaks = [("left hinge", hinge), ("left shoulder edge", [-14.0, es]), ("centreline crown", [0.0, pg]),
              ("right shoulder edge", [14.0, es]), ("right ditch bottom", ditch)]
    fg = [left_catch] + [p for _n, p in breaks] + [right_catch]

    def layer(depth):
        return [[-14.0, es - depth], [0.0, pg - depth], [14.0, es - depth]]
    y = pg + 3.0
    return {"pg": pg, "ground": ground, "breaks": breaks,
            "catches": [("left catch point (fill)", left_catch), ("right catch point (cut)", right_catch)],
            "fg": fg, "fill_run": fill_run, "cut_run": cut_run,
            "layer_lines": [layer(d) for _n, d in JEFF["layers"]],
            "dims": [(-14.0, -12.0, y + 1.5), (-12.0, 0.0, y), (0.0, 12.0, y), (12.0, 14.0, y + 1.5)],
            "labels": [("2%", [-6.0, pg + 0.6]), ("2%", [6.0, pg + 0.6]),
                       ("1:4", _seg_mid([-14.0, es], hinge)), ("1:4", _seg_mid([14.0, es], ditch)),
                       (f"1:{fill_run:g}", _seg_mid(hinge, left_catch)),
                       (f"1:{cut_run:g}", _seg_mid(ditch, right_catch))],
            "dim_y": y + 1.5}


def ada_truth() -> dict:
    """WFL C.1 (ADA 60(5)) in full superelevation: 6% down to the right about
    the centreline; left lane 12 ft, right (inside) lane 12 + 2 ft widening;
    the right shoulder on the 6%, the left (high-side) shoulder breaking over
    to 2% down away from the lanes; a 1:4 foreslope from the left shoulder
    edge to a ditch 1.5 ft below it, then a 1:2 backslope; on the right a 1:4
    fill slope from the shoulder edge to the ground."""
    pg = ADA["pg"]
    ground = [[x, pg + dy] for x, dy in ADA["ground"]]
    e = 0.06
    left_lane = [-12.0, pg + e * 12.0]
    left_sh = [-14.0, left_lane[1] - 0.02 * 2.0]
    right_sh = [16.0, pg - e * 16.0]
    ditch = [-14.0 - 1.5 * 4.0, left_sh[1] - 1.5]
    left_catch = _catch(ditch, -1, 1.0 / 2.0, ground)
    right_catch = _catch(right_sh, +1, -1.0 / 4.0, ground)
    breaks = [("left ditch bottom", ditch), ("left shoulder edge", left_sh),
              ("left lane edge (high side)", left_lane), ("right shoulder edge (low side)", right_sh)]
    fg = [left_catch] + [p for _n, p in breaks] + [right_catch]

    def layer(depth):
        return [[-12.0, left_lane[1] - depth], [16.0, right_sh[1] - depth]]
    y = left_lane[1] + 3.0
    return {"pg": pg, "ground": ground, "breaks": breaks,
            "catches": [("left catch point (cut)", left_catch), ("right catch point (fill)", right_catch)],
            "fg": fg, "layer_lines": [layer(d) for _n, d in ADA["layers"]],
            "dims": [(-14.0, -12.0, y + 1.5), (-12.0, 0.0, y), (0.0, 14.0, y), (14.0, 16.0, y + 1.5)],
            "labels": [("6%", [-6.0, pg + 1.2]), ("6%", [7.0, pg + 0.2]), ("2%", [-13.0, left_sh[1] + 1.2]),
                       ("1:4", _seg_mid(left_sh, ditch)), ("1:2", _seg_mid(ditch, left_catch)),
                       ("1:4", _seg_mid(right_sh, right_catch))],
            "dim_y": y + 1.5}


FDOT = {
    "id": "p10-typical-fdot9132", "sheet_id": "FDOT-913-2-4-Lane-Flush-Shoulder",
    "sheet": "5", "pg": 38.65, "station": "120+00", "v2": True, "scale": 20.0,
    "ground": [(-150.0, 2.70), (-120.0, 1.40), (-95.0, 0.30), (-70.0, -0.70), (-40.0, -1.40),
               (-10.0, -2.00), (15.0, -2.50), (45.0, -3.10), (75.0, -4.20), (110.0, -4.90),
               (150.0, -5.30)],
    "lane": 12.0, "shoulder": 10.0,
    "dims": (("lane", 12.0), ("outside shoulder", 10.0), ("inside shoulder", 8.0)),
    "cross_slopes": (2.0, 6.0),
    "layers": [("3/4-inch friction course FC-7", 0.75 / 12.0),
               ("Type SP structural course (two lifts, 3-1/2 inches)", 4.25 / 12.0),
               ("10-inch Optional Base Group 9", 14.25 / 12.0),
               ("12-inch Type B stabilization", 26.25 / 12.0)],
    "layer_offsets": [-41.0, -23.0, 23.0, 41.0],
    "slopes": ["1:6", "1:4"],
    #: the main section (with its R/W and clearing dimensions above it), not
    #: the traffic data, the details or the section's titles below
    "strip": [(0.9, 6.15, 15.95, 10.65)],
    "keep": [],
    "clip": [],
    "keep_text": set(),
    #: inside the FDOT border, above its title block
    "paper_area": (0.8, 1.15, 16.2, 10.7),
    "paper_center": (8.4, 8.2),
    "truth": fdot_truth,
}

JEFF = {
    "id": "p10-typical-wfl04", "sheet_id": "WFL-Typical-Sections-p04",
    "sheet": "C.1", "pg": 412.86, "station": "86+50", "v2": True,
    "ground": [(-200.0, -30.12), (-150.0, -24.12), (-100.0, -18.12), (-60.0, -13.32),
               (-40.0, -10.92), (-18.0, -8.28), (-5.0, -5.60), (5.0, -2.60), (14.0, 0.20),
               (22.0, 1.22), (40.0, 4.82), (60.0, 8.82), (90.0, 14.82), (120.0, 20.82)],
    "lane": 12.0, "shoulder": 2.0,
    "cross_slopes": (2.0,),
    "fill_table": [(5.0, 6.0), (10.0, 4.0), (None, 3.0)],
    "cut_table": [(5.0, 3.0), (15.0, 2.0), (None, 1.5)],
    "layers": [("4-inch asphalt concrete pavement", 4.0 / 12.0),
               ("5-inch emulsified asphalt treated aggregate base grading C", 9.0 / 12.0),
               ("8-inch aggregate base grading D", 17.0 / 12.0)],
    "layer_offsets": [-10.0, -3.0, 3.0, 10.0],
    "slopes": ["1:4", "1:3", "1:2"],
    #: the section, above its title (the project box at the top right stays)
    "strip": [(0.7, 6.55, 16.3, 10.28)],
    "keep": [],
    "clip": [],
    "keep_text": {'"MAIN 01"', "78+00 to 96+00"},
    "paper_center": (8.4, 8.3),
    "truth": jeff_truth,
}

ADA = {
    "id": "p10-typical-wfl05", "sheet_id": "WFL-Typical-Sections-p05",
    "sheet": "C.1", "pg": 3247.15, "station": "417+40", "v2": True,
    "ground": [(-80.0, 11.40), (-60.0, 8.40), (-40.0, 5.40), (-20.0, 2.40), (-8.0, 0.90),
               (4.0, -0.80), (16.0, -2.20), (30.0, -3.60), (50.0, -5.60), (80.0, -8.60)],
    "lane": 12.0, "shoulder": 2.0,
    "dims": (("left lane", 12.0), ("right lane, widened", 14.0), ("shoulder", 2.0)),
    "cross_slopes": (6.0, 2.0),
    "layers": [("4-inch asphalt concrete pavement", 4.0 / 12.0),
               ("5-inch emulsified asphalt treated aggregate base grading C", 9.0 / 12.0),
               ("8-inch aggregate base grading D", 17.0 / 12.0)],
    "layer_offsets": [-9.0, -3.0, 3.0, 11.0],
    "slopes": ["1:4", "1:2"],
    #: the normal section and its curb-and-sidewalk variants, above the title
    #: (the variants' dimensions run up to the border); the project box stays
    "strip": [(0.7, 4.55, 16.3, 10.69)],
    "keep": [(14.25, 10.25, 16.35, 10.75)],
    "clip": [],
    "keep_text": {'"MAIN 01"', "388+50 to 443+00"},
    "paper_center": (8.4, 7.4),
    "truth": ada_truth,
}

NEW_SPECS = [FDOT, JEFF, ADA]


def solve_drawn(spec: dict, session: Session) -> None:
    """Draft a ``v2`` spec through the command bus from its truth: the
    finished grade catch to catch, each layer bottom, the dimensions and the
    slope labels in model space, then the viewport."""
    truth = spec["truth"]()
    scale = spec.get("scale", SCALE_FT_PER_IN)
    text_h = 0.1 * scale
    run = lambda name, params: common.ok(session.execute(name, params))
    for name in ("XS_FINISHED_GRADE", "XS_PAVEMENT", "XS_ANNO"):
        session.execute("create_layer", {"name": name, "color": "black"})
    run("draw_polyline", {"space": "model", "layer": "XS_FINISHED_GRADE", "vertices": truth["fg"]})
    for line in truth["layer_lines"]:
        run("draw_polyline", {"space": "model", "layer": "XS_PAVEMENT", "vertices": line})
    for x0, x1, y in truth["dims"]:
        run("place_dimension", {"space": "model", "layer": "XS_ANNO", "kind": "linear",
                                "p1": [x0, _fg_at(truth["fg"], x0)],
                                "p2": [x1, _fg_at(truth["fg"], x1)],
                                "line_point": [(x0 + x1) / 2.0, y], "text_height": text_h})
    for content, at in truth["labels"]:
        run("place_text", {"space": "model", "layer": "XS_ANNO", "position": at,
                           "content": content, "height": text_h, "halign": "center"})
    left, right = truth["catches"][0][1], truth["catches"][1][1]
    x_lo, x_hi = left[0] - 0.4 * scale, right[0] + 0.4 * scale
    y_lo = min(p[1] for p in truth["fg"]) - 0.3 * scale
    y_hi = truth["dim_y"] + 0.35 * scale
    run("create_viewport", {"sheet": spec["sheet"], "feet_per_inch": scale,
                            "center_paper": list(spec["paper_center"]),
                            "width_in": round((x_hi - x_lo) / scale, 2),
                            "height_in": round((y_hi - y_lo) / scale, 2),
                            "model_center": [(x_lo + x_hi) / 2.0, (y_lo + y_hi) / 2.0]})


FDOT_PROMPT = (
    "Sheet 5 has lost its typical section for SR 22, STA. 63+65.42 to STA. 328+65.14; its "
    "titles, the traffic data, the pavement notes and the two details are left. Redraw it from "
    "this description as a true-scale section in this file's model space: x is the offset from "
    "the construction centreline in feet (right positive) and y is the elevation. The natural "
    "ground at station 120+00 is already drawn there on layer XS_EXISTING_GROUND, and the "
    "profile grade at both profile grade points is 38.65. It is a four-lane divided section "
    "with a 40-ft depressed median, the construction centreline at the centre of the median. "
    "Each roadway has two 12-ft travel lanes sloping 0.02 down away from the median, with its "
    "profile grade point at the inside edge of its travel lanes. Inside shoulders are 8 ft, "
    "sloping 0.06 down toward the median; outside shoulders are 10 ft, sloping 0.06 down away "
    "from the travel lanes. From each inside shoulder edge a 1:6 slope runs down to the median "
    "ditch at the centreline. Left side: a 1:6 front slope from the outside shoulder edge down "
    "to a roadside ditch 3.5 ft below the shoulder edge, a 5-ft flat ditch bottom, then a 1:4 "
    "back slope up to natural ground. Right side, in fill: a 1:6 slope from the outside "
    "shoulder edge down to natural ground. Travel lane pavement, parallel to the finished "
    "grade, top down: 3/4-inch friction course FC-7, Type SP structural course in two lifts "
    "(1-1/2 inches over 2 inches), 10-inch Optional Base Group 9, on 12-inch Type B "
    "stabilization. Slopes are V:H, as on our sheets. Draw the finished grade from catch point "
    "to catch point and the bottom of each travel-lane pavement layer, dimension the lane, "
    "inside shoulder and outside shoulder widths, and label the cross slopes and each side "
    "slope. Then show it on sheet 5 in a viewport at 1\" = 20' (horizontal and vertical), "
    "above the section's titles and clear of the traffic data, the notes and the details.")

JEFF_PROMPT = (
    "Sheet C.1 (TYPICAL SECTION) has lost its MAIN 01 section, 78+00 to 96+00; only its title "
    "is left. Redraw it from this description, as the section at station 86+50, as a "
    "true-scale section in this file's model space: x is the offset from the centreline in "
    "feet (right positive) and y is the elevation. The existing ground at station 86+50 is "
    "already drawn there on layer XS_EXISTING_GROUND, and the profile grade at the centreline "
    "is 412.86. Two 12-ft traveled lanes and 2-ft shoulders with a 2% crown both ways (the "
    "shoulders on the lane slope). Surfacing, parallel to the finished grade under the lanes "
    "and shoulders, top down: 4-inch asphalt concrete pavement in two equal lifts, 5-inch "
    "emulsified asphalt treated aggregate base grading C, 8-inch aggregate base grading D. From "
    "each shoulder edge a 1:4 slope runs down and out. Left side, in fill: the 1:4 runs 4 ft "
    "out to the hinge, then the fill slope runs down to existing ground. Right side, in cut: "
    "the 1:4 runs on down to a ditch bottom 2 ft below the shoulder edge, then the cut slope "
    "rises to existing ground. The fill and cut slopes come from our slope tables. Fill slope, "
    "by the fill height from the hinge down to the catch point: up to 5 ft, 1:6; over 5 ft to "
    "10 ft, 1:4; over 10 ft, 1:3. Cut slope, by the cut height from the ditch bottom up to the "
    "catch point: up to 5 ft, 1:3; over 5 ft to 15 ft, 1:2; over 15 ft, 1:1.5. Slopes are V:H, "
    "as on our sheets. Draw the finished grade from catch point to catch point and the bottom "
    "of each surfacing layer, dimension the lane and shoulder widths, and label the cross "
    "slope and each side slope. Then show it on sheet C.1 in a viewport at 1\" = 10' "
    "(horizontal and vertical), above its title and clear of the details and notes.")

ADA_PROMPT = (
    "Sheet C.1 (TYPICAL SECTION) has lost its MAIN 01 sections, 388+50 to 443+00; only their "
    "title is left. Redraw the superelevated section from this description: the section at "
    "station 417+40, in the full superelevation of the curve to the right there, as a "
    "true-scale section in this file's model space: x is the offset from the centreline in "
    "feet (right positive) and y is the elevation. The existing ground at station 417+40 is "
    "already drawn there on layer XS_EXISTING_GROUND, and the profile grade at the centreline "
    "is 3,247.15. Two traveled lanes and 2-ft shoulders: the left lane 12 ft, the right lane "
    "12 ft plus 2 ft of curve widening on the inside of the curve. The traveled way is rotated "
    "about the centreline to a 6% superelevation sloping down to the right; the right (low "
    "side) shoulder continues on the 6%; the left (high side) shoulder breaks over and slopes "
    "2% down away from the traveled way. Surfacing, parallel to the finished grade under the "
    "lanes and shoulders, top down: 4-inch asphalt concrete pavement in two equal lifts, "
    "5-inch emulsified asphalt treated aggregate base grading C, 8-inch aggregate base grading "
    "D. Left side, in cut: a 1:4 foreslope from the shoulder edge down to a ditch bottom 1.5 ft "
    "below the shoulder edge, then a 1:2 backslope up to existing ground. Right side, in fill: "
    "a 1:4 fill slope from the shoulder edge down to existing ground. Slopes are V:H, as on our "
    "sheets. Draw the finished grade from catch point to catch point and the bottom of each "
    "surfacing layer, dimension the lane and shoulder widths, and label the cross slopes and "
    "each side slope. Then show it on sheet C.1 in a viewport at 1\" = 10' (horizontal and "
    "vertical), above its title and clear of the details and notes.")

for _spec, _prompt in ((FDOT, FDOT_PROMPT), (JEFF, JEFF_PROMPT), (ADA, ADA_PROMPT)):
    _spec["prompt"] = _prompt
    _spec["start"] = common.register(_spec["id"], common.sheet_file(_spec["sheet_id"]),
                                     lambda out, spec=_spec: _build(spec, out))

PROBES += [
    Probe(id=FDOT["id"], prompt=FDOT_PROMPT, start=FDOT["start"], tags=["typical-section", "fdot"],
          check=lambda b, s: check_section(FDOT, b, s), solve=lambda s: solve_drawn(FDOT, s),
          note=_note(FDOT, "Eleven grade breaks on two roadways that slope away from the median, "
                           "profile grade at the inside lane edges (not the centreline). Naive "
                           "answers that fail: the profile grade put on the construction "
                           "centreline (every break 2.48 ft off), the roadways crowned, the ditch "
                           "without its flat bottom (the 1:4 from the front slope's foot), the "
                           "viewport at 1\" = 10' (off the sheet).")),
    Probe(id=JEFF["id"], prompt=JEFF_PROMPT, start=JEFF["start"], tags=["typical-section", "wfl"],
          check=lambda b, s: check_section(JEFF, b, s), solve=lambda s: solve_drawn(JEFF, s),
          note=_note(JEFF, "Fill left and cut right on a sidehill; the slopes come from the "
                           "tables: 1:3 fill (10.94 ft high; 1:4 would be 13.46, 1:6 25.0) and "
                           "1:2 cut (5.83 ft; 1:3 would be 8.75, 1:1.5 exactly 5.0). Naive "
                           "answers that fail: each table's first row (1:6 fill, 1:3 cut), the "
                           "heights read off the ground at the hinge (7.0 ft, so 1:4) and over "
                           "the ditch (3.5 ft, so 1:3) instead of at the catch points, the "
                           "section mirrored (cut left).")),
    Probe(id=ADA["id"], prompt=ADA_PROMPT, start=ADA["start"], tags=["typical-section", "wfl"],
          check=lambda b, s: check_section(ADA, b, s), solve=lambda s: solve_drawn(ADA, s),
          note=_note(ADA, "Full superelevation 6% rotated about the centreline, the right lane "
                          "widened to 14 ft, the high-side shoulder breaking over to 2%. Naive "
                          "answers that fail: the normal 2% crown, rotation about the inside "
                          "(right) edge of the traveled way, no widening (the low-side shoulder "
                          "2 ft short), the high-side shoulder left on the 6%.")),
]
