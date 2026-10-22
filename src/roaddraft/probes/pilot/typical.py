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
        tally.add(f"bottom of the {layer} ({depth * 12:.0f} in down)",
                  None if not misses else
                  f"the bottom of the {layer}, {depth:.3f} ft below finished grade, has no "
                  f"linework within {LAYER_FT} ft at offset {misses[0][0]:+.0f} ft "
                  f"(nearest {misses[0][1]:.2f} ft)")

    dims = [e for _space, e in added if isinstance(e, Dimension)]
    for what, width in (("lane", spec["lane"]), ("shoulder", spec["shoulder"])):
        tally.add(f"{what} width dimensioned ({width:g}')",
                  None if any(_dimension_reads(d, width) for d in dims) else
                  f"no dimension reads the {width:g}' {what} width"
                  + ("" if dims else " (no dimensions were added)"))

    texts = [e.content for _space, e in added if isinstance(e, Text)]
    tally.add("cross slope labelled (2%)",
              None if any(CROSS_SLOPE.search(t) for t in texts) else "no text gives the 2% cross slope")
    for ratio in spec["slopes"]:
        pattern = _ratio_pattern(ratio)
        tally.add(f"side slope labelled ({ratio})",
                  None if any(pattern.search(t) for t in texts) else
                  f"no text gives the {ratio} slope (V:H)")

    tally.add("viewport at 1\" = 10' showing the section, clear of the sheet's notes",
              _viewport_problem(spec, baseline, submitted, truth))
    return tally.result(f"section drawn to the description: catch points "
                        f"{truth['catches'][0][1][0]:.2f} and {truth['catches'][1][1][0]:.2f} ft, "
                        f"shown at 1\" = 10'")


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
        if abs(vp.feet_per_inch - SCALE_FT_PER_IN) > 1e-6:
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
        if not _inside(rect, PAPER_AREA):
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
