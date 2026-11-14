"""The seeded D1 task generator (spec section 7.4).

``generate_task(seed)`` draws a plausible two-lane alignment (radii above the
AASHTO minimum for the design speed, deflections 15-60 degrees, tangents with
room for the curves), an optional station equation, a profile whose grades
and K values satisfy the DRAFT standards tables, project metadata, and a
deliverable of one or two ANSI D plan sheets at 1"=50' or 1"=100'.  Only
``random.Random(seed)`` is consulted (no global RNG, no clock), so the same
seed always yields byte-identical briefs, truths and task ids.  The fit loop
shrinks the design deterministically (no new draws) until every sheet's
share of it fits the plan window.

A task can be *twisted* (``twist``, 2026-11-11): its sheets look at the model
through viewports turned alike, and the road is turned under them the other
way, so the paper layout is the untwisted task's.  The model lettering then
has to be made to read through the twist and the north arrow turned to north.
The untwisted task is the default and its id is what it always was.

A task can be *crowded* (``crowd``, 2026-11-12; ``tasks.crowd``): its sheet
already carries a second lettered line and notes on the paper, set where the
default poses of the asked labels land, so the drafter has to look at what its
lettering fell on and set it again clear.  The uncrowded task is the default
and its id is what it always was.

A task can be *revised* (``revise``, 2026-11-12; ``tasks.revise``): its sheet is
handed over finished, after the designer has changed the design under it (a
radius, a PI, the stationing), so the drafter has to take off what the change
left behind, letter it again and restation the notes that cite the line.  The
unrevised task is the default and its id is what it always was.

A task also has a *type* (``tasks.types``): the phases of the drawing it
starts with and the ones it asks for.  The starting document is the design
plus the given phases drafted by the reference solution, so a drafter joins
work in progress that already shows the office's standards.
"""
from __future__ import annotations

import datetime as _dt
import math
import random
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.angles import direction_of, unit_vector
from roaddraft.design.horizontal import PI, Alignment, TangentElement, compile_pis
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.labels import (
    DEFAULT_VALIGN, LabelSpec, compile_label, curve_table_rows, sheet_pose, stationing_plan,
)
from roaddraft.design.model import DesignModel
from roaddraft.design.stations import build_equations
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document import dimgeom
from roaddraft.document.document import Document
from roaddraft.document.entities import Dimension, Table, Text
from roaddraft.document.fileformat import INTERCHANGE_EXT
from roaddraft.document.sheets import SHEET_SIZES, Sheet
from roaddraft.tasks.brief import GENERATOR_VERSION, Task, TaskBrief, compute_task_id
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.prompts import render_prompts
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash, spec_subset
from roaddraft.tasks.standards import max_grade, min_k, min_radius
from roaddraft.tasks.types import DEFAULT_TYPE, OPEN_BREAKS, PHASE_ORDER, TaskType
from roaddraft.tasks.types import task_type as _task_type

SPEEDS = [35, 40, 45, 50, 55]
CURVE_COUNTS = [1, 2, 2, 3]
ROUTES = ["SR 12", "SR 118", "US 41", "CR 7", "SR 260"]
PROJECTS = ["RESURFACING", "REALIGNMENT", "WIDENING", "SAFETY IMPROVEMENTS"]
AGENCIES = ["STATE DOT DISTRICT 4", "COUNTY ENGINEER", "STATE DOT DISTRICT 7"]
COUNTIES = ["HARLAN COUNTY", "MERCER COUNTY", "LINCOLN COUNTY", "CLAY COUNTY", "PIKE COUNTY"]
EQUATION_JUMPS = [100, 200, 300, 500]
# the fit loop never shrinks a tangent below this: at 1"=100' it leaves the EC of one
# curve and the BC of the next 1.2 in apart on paper, clear of each other
#: the shortest tangent beyond the curve tangents and the shortest curve, as paper
#: lengths at the coarsest plan scale in use: a bearing letters along the one, the BC
#: and EC labels stay apart on the other (seed 123 at 1" = 100' had them touch on a
#: 105 ft curve, 1.05 in)
MIN_EXTRA_IN = 1.2
MIN_CURVE_IN = 1.5
_COARSEST_FPI = float(max(DRAFTING_SPEC_V1["sheet"]["allowed_feet_per_inch"]))
MIN_EXTRA_FT = MIN_EXTRA_IN * _COARSEST_FPI  # 60 ft at 1" = 50'
# ... nor a curve below this length: at 1"=100' the BC and EC labels of a shorter
# curve (each about 1 in of lettering) run into each other on the inside of the bend
MIN_CURVE_FT = MIN_CURVE_IN * _COARSEST_FPI  # 75 ft at 1" = 50'
FIT_ATTEMPTS = 22
#: how much the fit loop shrinks the tangents and radii per attempt: a two-sheet layout
#: shrinks more gently, because its match line needs a tangent at least
#: ``MATCH_END_CLEAR_FT + MATCH_CLEAR_FT`` long on one side of its only curve and a
#: steep shrink jumps over the lengths where that holds and the shares still fit
SHRINK = {1: (0.85, 0.92), 2: (0.8, 0.9)}
#: fit loop: the design speed steps down a notch per attempt from here (a road this
#: fast with this many curves is longer than one sheet shows at the plan scales in
#: use: it is a slower road), and the chord is laid along the window's diagonal from
#: ``DIAGONAL_ATTEMPT`` on
SLOWER_ATTEMPT = 8
DIAGONAL_ATTEMPT = 9
#: room kept round a one-sheet alignment inside the plan window for the labels that
#: reach past its ends (the square curve-point labels reach about 1.35 in), on paper
#: at the coarsest scale in use
PAD_IN = 1.5
PAD_FT = PAD_IN * _COARSEST_FPI  # 75 ft at 1" = 50'
CORNER_INSET_IN = 0.25
# label offsets come from the spec's labels section (the PPM's placement): station numbers
# below the line, bearings above it, curve points square to it on the left, the curve
# number bubble on the right
# two-sheet layouts: longer tangents, a match line on a tangent clear of the curve
# points, 2 in each side of the centerline on paper, labelled past its end
TWO_SHEET_STRETCH = 2.2
MATCH_CLEAR_FT = 60.0
MATCH_END_CLEAR_FT = 300.0
MATCH_HALF_IN = 2.0
MATCH_LABEL_OFFSET_IN = 3.5
SAMPLE_STEP_FT = 10.0
# pavement width dimensions: the dimension line sits 0.1 in ahead of its station on
# paper, and a wide text gap sets the text (which cannot fit between the edges at plan
# scale) past 0.5 in right of the centerline, outside the band the BC/EC labels use;
# the station keeps the extension lines on the tangent (they reach 0.2 in ahead of it;
# nothing reaches behind), the text clear of an equation label, and the dimension line
# clear of the bearing lettered above the tangent's midpoint (2026-10-16: a bearing and
# distance letters about 1.5 in along a tangent 3 to 4 in long, so the half station
# nearest the midpoint ran the line through it on nearly every seed) and of the station
# numbers under the line
WIDTH_DIM_LINE_IN = 0.1
WIDTH_TEXT_GAP_FACTOR = 1.5  # x text height; the engine's default is 0.5
WIDTH_AHEAD_IN = 0.22
WIDTH_BEHIND_IN = 0.05
WIDTH_CLEAR_IN = 1.6
#: paper the dimension line keeps from the bearing lettering, and from a whole station
#: (its number, 1 to 3 digits, sits under the line there); the stations tried after the
#: half stations step along the tangent by ``WIDTH_STEP_FT``, nearest the midpoint first.
#: A tangent shorter than about 110 ft has no room beside a 1.5 in bearing and is left
#: undimensioned (1,026 of 10,732 tangents over seeds 1-200 and 1000-1099 at every dial,
#: against 520 under the old rule; 72 three-curve one-sheet layouts have none)
WIDTH_LETTER_CLEAR_IN = 0.05
WIDTH_STATION_CLEAR_IN = 0.15
WIDTH_STEP_FT = 5.0
ALIGNMENT_NAME = "ALIGN-1"
PROFILE_NAME = "PROF-1"
SHEET_NAMES = ["C-101", "C-102", "C-103", "C-104"]
#: the twist dial (2026-11-11, Robert: "Twist dial first"): a twisted task's sheets look at
#: the model through viewports turned alike, the way three ``d1-real`` tasks in four do and
#: every ``p17`` pilot does, so its model lettering wants ``view_rotation`` to read upright
#: as plotted and its north arrow is turned to north.  The seed's own twist is drawn from
#: a stream of its own, so the seed's road, stationing and paper layout are those of its
#: untwisted task (to the hundredth of a foot its PIs are rounded to): the road is turned
#: under the sheet by the twist and the viewport turned back.  A twist under
#: ``TWIST_MIN_DEG`` either way is not drawn: lettering reads the same through it, so it
#: would teach nothing
TWIST_MIN_DEG = 10.0


def seed_twist(seed: int) -> float:
    """The viewport twist of ``seed``'s twisted task, in (-180, 180] to the
    hundredth of a degree, at least ``TWIST_MIN_DEG`` from none."""
    rng = random.Random(f"twist:{int(seed)}")
    t = round(rng.uniform(TWIST_MIN_DEG, 360.0 - TWIST_MIN_DEG), 2)
    return round(t - 360.0, 2) if t > 180.0 else t


def _about(p: Sequence[float], origin: Sequence[float], deg: float) -> List[float]:
    """``p`` turned ``deg`` counter-clockwise about ``origin``."""
    q = geo.rotate_point([p[0] - origin[0], p[1] - origin[1]], deg)
    return [origin[0] + q[0], origin[1] + q[1]]


def _laid(align: Alignment, turn: float) -> Alignment:
    """``align`` as a viewport twisted ``turn`` shows it: the same line turned
    about its BEGIN, so the layout rules (which fit a road to an untwisted
    window) run on it as they stand.  ``align`` itself when there is no twist."""
    if not turn:
        return align
    origin = align.pis[0].point
    pis = [PI(_about(pi.point, origin, turn), pi.radius) for pi in align.pis]
    return Alignment(name=align.name, elements=compile_pis(pis), pis=pis, source="pis",
                     begin_station=align.begin_station, equations=list(align.equations))


def _round2(v: float) -> float:
    return round(float(v), 2)


def _delta_floor(radius: float) -> float:
    """The smallest deflection (degrees, to the half degree) that keeps a curve
    of ``radius`` at least ``MIN_CURVE_FT`` long; never below 15 degrees."""
    return max(15.0, math.ceil(math.degrees(MIN_CURVE_FT / radius) * 2.0) / 2.0)


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


def segment_points(align: Alignment, lo: float, hi: float) -> List[List[float]]:
    """Centerline points between distances ``lo`` and ``hi`` from BEGIN, every
    ``SAMPLE_STEP_FT`` plus both ends and every element end in between."""
    dists = [lo, hi] + [d for el in align.elements for d in (el.start_dist, el.end_dist)
                        if lo < d < hi]
    d = lo
    while d < hi:
        dists.append(d)
        d += SAMPLE_STEP_FT
    return [align.point_at(x) for x in sorted(set(dists))]


def _fits_window(bb, fpi: float, pad: float = PAD_FT) -> bool:
    fit_w, fit_h = DRAFTING_SPEC_V1["sheet"]["fit_window_in"]
    bb = geo.bbox_expand(bb, pad)
    return (bb[2] - bb[0]) <= fit_w * fpi and (bb[3] - bb[1]) <= fit_h * fpi


# a two-sheet viewport is sized round the labels it shows (2026-10-12): the square BC/EC
# and equation labels reach 0.45 in plus their length past the centerline, further than
# the 100 ft pad, and the renderer clips whatever crosses the viewport's edge
VIEWPORT_MARGIN_IN = 0.25


def _label_boxes(align: Alignment, fpi: float, turn: float = 0.0) -> List[Tuple[float, tuple]]:
    """``(distance from BEGIN, model bbox)`` of every label the finished
    drawing carries, placed as the ground truth places them (the spec's
    offsets at this scale): station numbers, curve points, equations,
    bearings and the curve bubbles.  Under a viewport twisted ``turn`` the
    labels are lettered to read through it, as the truth letters them, and
    each box is the label's as that view shows it (``_laid``'s frame)."""
    spec = DRAFTING_SPEC_V1
    origin = align.pis[0].point if turn else None
    height = _round2(spec["text"]["label_height_in"] * fpi)
    view = {"view_rotation": turn} if turn else {}
    plan = stationing_plan(align, interval=float(spec["stationing"]["interval_ft"]),
                           tick_half=_round2(spec["stationing"]["tick_half_len_in"] * fpi),
                           label_offset=_round2(spec["stationing"]["label_offset_in"] * fpi),
                           lettering=spec["stationing"]["format"],
                           station_side=spec["stationing"]["label_side"],
                           point_offset=_round2(spec["labels"]["pc_pt"]["label_offset_in"] * fpi),
                           **view)
    specs: List[LabelSpec] = plan.labels()
    for n in range(1, len(align.tangents()) + 1):
        specs.append(compile_label(align, resolve_anchor(align, parse_anchor(f"T-{n}")), "bearing",
                                   label_offset=_round2(spec["labels"]["bearing"]["label_offset_in"] * fpi),
                                   **view))
    for n in range(1, len(align.curves()) + 1):
        specs.append(compile_label(align, resolve_anchor(align, parse_anchor(f"MC-{n}")), "mc",
                                   label_offset=_round2(spec["labels"]["mc"]["label_offset_in"] * fpi),
                                   **view))
    begin = float(align.begin_station)
    out = []
    for s in specs:
        w, h = geo.text_size(s.content, height)
        x0 = {"center": -w / 2.0, "right": -w}.get(s.halign, 0.0)
        y0 = {"middle": -h / 2.0, "top": -h}.get(s.valign, 0.0)
        corners = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]
        pts = [geo.translate_point(geo.rotate_point(c, s.rotation_deg), s.position) for c in corners]
        at = s.position
        if turn:  # the label and its bubble as the twisted view shows them
            pts = [_about(p, origin, turn) for p in pts]
            at = _about(at, origin, turn)
        if s.kind == "mc":  # the bubble round the number
            r = 2.0 * height
            pts += [[at[0] - r, at[1] - r], [at[0] + r, at[1] + r]]
        out.append((float(s.station) - begin, tuple(geo.bbox_of_points(pts))))
    return out


def _dimension_boxes(align: Alignment, half_width: float, width_dims: Sequence[dict],
                     fpi: float, turn: float = 0.0) -> List[Tuple[float, tuple]]:
    """``(distance from BEGIN, model bbox)`` of each width dimension's text, as
    the engine sets it for the dimension the reference places.  Under a
    viewport twisted ``turn`` the dimension is given the twist, as the
    reference gives it, and each box is the text's as that view shows it
    (``_laid``'s frame, like ``_label_boxes``')."""
    height = _round2(DRAFTING_SPEC_V1["text"]["label_height_in"] * fpi)
    begin = float(align.begin_station)
    origin = align.pis[0].point if turn else None
    scratch = Document.new("dimension text")
    out = []
    for n, wd in enumerate(width_dims, start=1):
        raw = float(wd["station"])
        p1 = align.station_to_xy(raw, -half_width)[0]
        p2 = align.station_to_xy(raw, half_width)[0]
        ahead = align.station_to_xy(min(raw + float(wd["line_offset_ft"]), align.end_station), 0.0)[0]
        dim = Dimension(id=f"DM-{n:03d}", kind="aligned", p1=list(p1), p2=list(p2),
                        line_point=list(ahead), text_height=height, unit_format="feet",
                        text_gap=float(wd["text_gap_ft"]) if wd.get("text_gap_ft") else None,
                        view_rotation=turn or None)
        for prim in dimgeom.primitives(dim, scratch):
            if not (isinstance(prim, Text) and prim.content):
                continue
            if not turn:
                out.append((raw - begin, tuple(geo.text_bbox(prim.position, prim.content, prim.height,
                                                               prim.rotation_deg, prim.halign,
                                                               prim.valign))))
                continue
            w, h = geo.text_size(prim.content, prim.height)
            x0 = {"center": -w / 2.0, "right": -w}.get(prim.halign, 0.0)
            y0 = {"middle": -h / 2.0, "top": -h}.get(prim.valign, 0.0)
            corners = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]
            pts = [_about(geo.translate_point(geo.rotate_point(c, prim.rotation_deg), prim.position),
                          origin, turn) for c in corners]
            out.append((raw - begin, tuple(geo.bbox_of_points(pts))))
    return out


def _sheet_box(align: Alignment, lo: float, hi: float, fpi: float,
               labels: Sequence[Tuple[float, tuple]]) -> tuple:
    """The model window a two-sheet viewport shows for the share ``lo``..``hi``
    of the alignment: the centerline and every label anchored on that share,
    with a margin, then grown until no label of the other share crosses its
    edge (a label is shown whole or not at all)."""
    margin = VIEWPORT_MARGIN_IN * fpi
    pts = segment_points(align, lo, hi)
    own = [bb for d, bb in labels if lo - 1e-6 <= d <= hi + 1e-6]
    others = [bb for d, bb in labels if not (lo - 1e-6 <= d <= hi + 1e-6)]
    box = geo.bbox_expand(geo.bbox_of_points(pts + [[bb[0], bb[1]] for bb in own]
                                             + [[bb[2], bb[3]] for bb in own]), margin)
    for _ in range(20):
        crossing = [bb for bb in others
                    if geo.bbox_intersects(box, bb) and not geo.bbox_contains(box, bb)]
        if not crossing:
            break
        for bb in crossing:
            grown = geo.bbox_expand(bb, margin)
            box = (min(box[0], grown[0]), min(box[1], grown[1]),
                   max(box[2], grown[2]), max(box[3], grown[3]))
    return box


def _match_options(align: Alignment, n_sheets: int) -> List[List[float]]:
    """Ways to break the alignment into ``n_sheets`` shares: lists of
    ``n_sheets - 1`` distances from BEGIN, each an even 100-ft station on a
    tangent, clear of its curve points and of the alignment's ends.  For two
    sheets every legal break is offered, nearest the even split first (the
    share holding the curve may need a break well off the middle to fit a
    sheet); for more, the one set of breaks nearest the even splits.  Empty
    when there is none."""
    L = align.length
    per_break: List[List[float]] = []
    for k in range(1, n_sheets):
        want = L * k / n_sheets
        legal: List[float] = []
        for m in range(1, int(L // 100.0) + 1):
            d = 100.0 * m
            if d < MATCH_END_CLEAR_FT or d > L - MATCH_END_CLEAR_FT:
                continue
            i, _ = align.element_at(d)
            el = align.elements[i]
            if not isinstance(el, TangentElement):
                continue
            if d - el.start_dist < MATCH_CLEAR_FT or el.end_dist - d < MATCH_CLEAR_FT:
                continue
            legal.append(d)
        if not legal:
            return []
        per_break.append(sorted(legal, key=lambda d: abs(d - want)))
    if n_sheets == 2:
        return [[d] for d in per_break[0]]
    chosen = [cands[0] for cands in per_break]
    return [chosen] if all(b > a for a, b in zip(chosen, chosen[1:])) else []


def _fits(align: Alignment, n_sheets: int, design: Optional[Alignment] = None,
          turn: float = 0.0) -> Optional[Tuple[int, List[float]]]:
    """``(feet_per_inch, match_dists)`` at the smallest allowed scale that
    shows every sheet's share of the alignment in the plan window, breaking
    the alignment at the legal match line nearest the even split that lets
    every share fit.  Under a twist ``align`` is the line as the sheets show
    it (``_laid``) and ``design`` the line itself, whose labels are boxed
    through the twist ``turn``."""
    options = _match_options(align, n_sheets) if n_sheets > 1 else [[]]
    if not options:
        return None
    for fpi in DRAFTING_SPEC_V1["sheet"]["allowed_feet_per_inch"]:
        if n_sheets == 1:
            bb = geo.bbox_of_points(segment_points(align, 0.0, align.length))
            if _fits_window(bb, fpi):
                return int(fpi), []
            continue
        labels = _label_boxes(design or align, fpi, turn)
        for matches in options:
            bounds = [0.0] + matches + [align.length]
            boxes = [_sheet_box(align, bounds[i], bounds[i + 1], fpi, labels)
                     for i in range(n_sheets)]
            if all(_fits_window(bb, fpi, pad=0.0) for bb in boxes):
                return int(fpi), matches
    return None


def _table_size(align: Alignment, curves: Sequence[int], columns: List[str],
                text_height: float) -> Tuple[float, float]:
    _headers, rows, widths = curve_table_rows(align, columns, curves=curves)
    w = sum(widths)
    h = text_height * (Table.TITLE_FACTOR + Table.ROW_FACTOR * (len(rows) + 1))
    return w, h


def _curve_table_position(align: Alignment, curves: Sequence[int], sheet: Sheet, viewport: dict,
                          columns: List[str], text_height: float,
                          avoid: Sequence[tuple] = ()) -> List[float]:
    """First candidate corner (bottom-right, top-right, bottom-left, top-left)
    whose table rect clears the drawn alignment (mapped to paper, padded 1 in),
    the north arrow and the ``avoid`` rects; fallback bottom-right.  Through a
    twisted viewport the alignment shown is what falls inside its rect on the
    paper, and the north arrow is the turned one."""
    w, h = _table_size(align, curves, columns, text_height)
    ua = sheet.usable_area()
    x0, y0, x1, y1 = (ua[0] + CORNER_INSET_IN, ua[1] + CORNER_INSET_IN,
                      ua[2] - CORNER_INSET_IN, ua[3] - CORNER_INSET_IN)
    candidates = [[x1 - w, y0 + h], [x1 - w, y1], [x0, y0 + h], [x0, y1]]
    t = geo.ViewportTransform(viewport["center_paper"], viewport["model_center"],
                              viewport["feet_per_inch"], viewport.get("rotation_deg", 0.0))
    turn = float(viewport.get("rotation_deg", 0.0))
    if turn:
        cx, cy = viewport["center_paper"]
        hw, hh = viewport["width_in"] / 2.0, viewport["height_in"] / 2.0
        shown = [p for p in segment_points(align, 0.0, align.length)
                 if abs((q := t.to_paper(p))[0] - cx) <= hw and abs(q[1] - cy) <= hh]
    else:
        visible = t.visible_model_bbox(viewport["width_in"], viewport["height_in"])
        shown = [p for p in segment_points(align, 0.0, align.length)
                 if geo.bbox_contains(visible, (p[0], p[1], p[0], p[1]))]
    obstacles = []
    if shown:
        obstacles.append(geo.bbox_expand(geo.bbox_of_points([t.to_paper(p) for p in shown]), 1.0))
    obstacles.append(_north_arrow_rect(turned=bool(turn)))
    obstacles.extend(geo.bbox_expand(r, 0.25) for r in avoid)
    for cand in candidates:
        rect = (cand[0], cand[1] - h, cand[0] + w, cand[1])
        if not any(geo.bbox_intersects(rect, ob) for ob in obstacles):
            return [_round2(cand[0]), _round2(cand[1])]
    return [_round2(candidates[0][0]), _round2(candidates[0][1])]


#: match-label poses to try, in order: square to the line past its end, then closer,
#: then along the line just past its end
MATCH_LABEL_POSES = (("perpendicular", MATCH_LABEL_OFFSET_IN), ("perpendicular", 3.0),
                     ("along", 2.4))


def _north_arrow_rect(turned: bool = False) -> Tuple[float, float, float, float]:
    """The paper the north arrow takes; ``turned``, the square that holds it at
    any turn about its insertion point (the block reaches 1.65 units from it,
    the N over the circle)."""
    na = DRAFTING_SPEC_V1["sheet"]["north_arrow"]
    px, py, sc = na["position"][0], na["position"][1], na["scale"]
    if turned:
        return (px - 1.8 * sc, py - 1.8 * sc, px + 1.8 * sc, py + 1.8 * sc)
    return (px - 1.2 * sc, py - 1.2 * sc, px + 1.2 * sc, py + 1.8 * sc)


def _match_label_bbox(align: Alignment, station_text: str, label: str, viewport: dict,
                      side: str, rotation: str, offset_in: float):
    """Paper bbox of the match-line label the reference would place."""
    spec = compile_label(align, resolve_anchor(align, parse_anchor(station_text)), "custom",
                         side=side, rotation=rotation, content=label)
    t = geo.ViewportTransform(viewport["center_paper"], viewport["model_center"],
                              viewport["feet_per_inch"], viewport.get("rotation_deg", 0.0))
    position, rot = sheet_pose(spec, t, viewport.get("rotation_deg", 0.0), offset_in)
    height = DRAFTING_SPEC_V1["text"]["label_height_in"]
    return geo.text_bbox(position, label, height, rot, "center", DEFAULT_VALIGN[side])


def _match_layout(align: Alignment, station_text: str, label: str, viewport: dict,
                  sheet: Sheet) -> Tuple[str, str, float, tuple]:
    """``(side, rotation, label_offset_in, paper bbox)`` for a match-line label
    that stays inside the usable area and clear of the north arrow."""
    ua = sheet.usable_area()
    inner = (ua[0] + 0.1, ua[1] + 0.1, ua[2] - 0.1, ua[3] - 0.1)
    na = _north_arrow_rect(turned=bool(viewport.get("rotation_deg")))
    first = None
    for rotation, offset in MATCH_LABEL_POSES:
        for side in ("right", "left"):
            bb = _match_label_bbox(align, station_text, label, viewport, side, rotation, offset)
            first = first or (side, rotation, offset, bb)
            if geo.bbox_contains(inner, bb) and not geo.bbox_intersects(bb, na):
                return side, rotation, offset, bb
    return first


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


#: the project's people and date, which every seeded document carries in its meta
#: under the title block's own field names (Robert, 2026-11-11: "do 3", put the names
#: and date in the document).  Until then nothing a drafter could read gave them, so a
#: title block drafted from a vague prompt had them made up or left blank; the vague
#: prompt still does not state them.  No generator bump: the task's payload always held
#: them (``project``), so ids, manifests and the truth are unchanged, and only the
#: starting document differs from what runs before this date were handed
DOCUMENT_PEOPLE = ("designed_by", "drawn_by", "checked_by", "date")


def _baseline(design: dict, project: dict, task_id: str, v_mph: int, county: str,
              agency: str) -> Document:
    doc = Document.new(project["name"])
    doc.design = DesignModel.from_dict({"alignments": design["alignments"],
                                        "profiles": design["profiles"]})
    doc.meta.update(task_id=task_id, spec_version=SPEC_VERSION, design_speed_mph=v_mph,
                    description=f"{project['name']} — {county}, {agency}")
    doc.meta.update({key: project[key] for key in DOCUMENT_PEOPLE})
    return doc


def generate_task(seed: int, curves: Optional[int] = None, equations: bool = False,
                  design_speed_mph: Optional[int] = None, level: str = "D1",
                  task_type: str = DEFAULT_TYPE, sheets: int = 1, twist=False,
                  crowd: bool = False, revise=None) -> Task:
    """Generate a deterministic D1 task from ``seed``.

    ``task_type`` names what the drafter starts with and is asked for
    (``tasks.TASK_TYPES``); ``sheets`` (1 or 2) is how many plan sheets the
    alignment is laid out on, with a match line between them.  ``twist``
    turns the sheets' viewports: ``True`` for the seed's own twist
    (``seed_twist``), or the degrees.  The untwisted task is the default, and
    is what it was before the dial existed, id and all.  ``crowd`` hands the
    task over on a sheet already worked on (``tasks.crowd``): a second
    lettered line and notes on the paper, on the default poses of labels the
    task asks for.  The uncrowded task is the default, id and all.  ``revise``
    hands over the finished sheet after the designer has changed its design
    (``tasks.revise``): a kind of ``tasks.revise.KINDS``, or True for the
    seed's own pick.  The unrevised task is the default, id and all."""
    ttype: TaskType = _task_type(task_type) if isinstance(task_type, str) else task_type
    n_sheets = int(sheets)
    if n_sheets < 1 or n_sheets > len(SHEET_NAMES):
        raise ValueError(f"sheets must be 1..{len(SHEET_NAMES)}")
    if crowd:
        from roaddraft.tasks.crowd import fits as _crowd_fits
        why = _crowd_fits(ttype, n_sheets)
        if why:
            raise ValueError(why)
    if revise:
        from roaddraft.tasks.revise import fits as _revise_fits
        why = ("a task is crowded or revised, not both" if crowd
               else _revise_fits(ttype, n_sheets, equations))
        if why:
            raise ValueError(why)
    turn = 0.0
    if twist:
        turn = seed_twist(seed) if twist is True else round(float(twist), 2)
        turn = round((turn + 180.0) % 360.0 - 180.0, 2)
        turn = 180.0 if turn == -180.0 else turn
    if turn:
        shown = ttype.shown()
        if "sheet" not in shown:
            raise ValueError(f"a {ttype.name} task has no sheet, so nothing to twist")
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
        deltas.append(max(rng.randrange(30, 121) / 2.0, _delta_floor(radii[-1])))
        turns.append(rng.choice(["L", "R"]))
    extras = [rng.uniform(250.0, 600.0)]
    extras += [rng.uniform(200.0, 600.0) for _ in range(n - 1)]
    extras.append(rng.uniform(250.0, 600.0))
    if n_sheets > 1:
        extras = [e * TWO_SHEET_STRETCH * (n_sheets - 1) for e in extras]
    r_floor = math.ceil(r_min * 1.15 / 50.0) * 50.0

    # ---- fit loop: deterministic shrinking, no new draws
    fit = None
    warnings: List[str] = []
    rotated = False
    for attempt in range(FIT_ATTEMPTS + 1):
        # ``d0`` is the way the line starts across the sheet; a twisted task's road is
        # turned under the sheet by the twist, and ``laid`` is the road as the sheet shows it
        pis = _build_pis(x0, y0, d0 - turn if turn else d0, radii, deltas, turns, extras)
        elements = compile_pis(pis)
        align = Alignment(name=ALIGNMENT_NAME, elements=elements, pis=pis, source="pis")
        laid = _laid(align, turn)
        fit = _fits(laid, n_sheets, align, turn)
        if fit is not None:
            break
        if attempt == FIT_ATTEMPTS:
            if design_speed_mph:
                raise ValueError(f"seed {seed}: a {v_mph} mph road with {n} curve(s) does not fit "
                                 f"{n_sheets} sheet(s) at the plan scales in use; ask for more "
                                 f"sheets, fewer curves or no fixed design speed")
            raise AssertionError(f"generator bug: seed {seed} never fit {n_sheets} sheet(s)")
        if n_sheets > 1 and not rotated:
            # a two-sheet layout is long: lay the BEGIN-END chord along the sheet
            # before shrinking anything, or the match line runs out of tangent
            rotated = True
            chord = direction_of(laid.pis[0].point, laid.pis[-1].point)
            d0 = (d0 - chord) % 360.0
            continue
        k_extra, k_radius = SHRINK.get(n_sheets, SHRINK[2])
        extras = [max(MIN_EXTRA_FT, e * k_extra) for e in extras]
        if attempt >= SLOWER_ATTEMPT and v_mph > SPEEDS[0] and not design_speed_mph:
            v_mph = SPEEDS[SPEEDS.index(v_mph) - 1]
            r_min = min_radius(v_mph)
            r_floor = math.ceil(r_min * 1.15 / 50.0) * 50.0
        radii = [max(r_floor, math.ceil(r * k_radius / 50.0) * 50.0) for r in radii]
        deltas = [max(_delta_floor(r), math.floor(d * 0.85 * 2.0) / 2.0)
                  for d, r in zip(deltas, radii)]
        if attempt >= 4:  # lay the BEGIN-END chord along the sheet, then its diagonal
            chord = direction_of(laid.pis[0].point, laid.pis[-1].point)
            d0 = (d0 - chord) % 360.0
            if attempt >= DIAGONAL_ATTEMPT:
                fit_w, fit_h = DRAFTING_SPEC_V1["sheet"]["fit_window_in"]
                d0 = (d0 + math.degrees(math.atan2(fit_h, fit_w))) % 360.0
    assert fit is not None
    fpi, match_dists = fit

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
        # clear of a match line: the equation is lettered square to the line like a
        # match label, and the two would overlap at the same station
        while (back <= end_sta - 50.0
               and any(abs(back - (begin_station + d)) < MATCH_CLEAR_FT for d in match_dists)):
            back += 100.0
        if back <= end_sta - 50.0:
            ahead = back + rng.choice(EQUATION_JUMPS)
            eq_items.append({"back": back, "ahead": ahead})
        else:
            warnings.append("no station equation: the longest tangent has no even station "
                            "50 ft clear of both ends")
    align.equations = build_equations(begin_station, align.length, eq_items)
    laid = _laid(align, turn)  # with the stationing, for the match lines' labels

    profile = _profile(rng, align, v_mph)

    # ---- project metadata
    route = rng.choice(ROUTES)
    kind = rng.choice(PROJECTS)
    agency = rng.choice(AGENCIES)
    county = rng.choice(COUNTIES)
    date = (_dt.date(2026, 1, 1) + _dt.timedelta(days=int(seed) % 365)).isoformat()
    pave = DRAFTING_SPEC_V1["pavement"]
    lane_width = float(rng.choice(pave["lane_widths_ft"]))
    half_width = lane_width * pave["lanes"] / 2.0
    project = {"name": f"{route} {kind}", "agency": agency, "route": route, "county": county,
               "design_speed_mph": v_mph, "designed_by": "RD", "drawn_by": "AGENT",
               "checked_by": "RD", "date": date,
               "typical_section": {"lanes": pave["lanes"], "lane_width_ft": lane_width,
                                   "pavement_width_ft": 2.0 * half_width}}

    # ---- deliverable
    spec = DRAFTING_SPEC_V1
    sheet_spec = spec["sheet"]
    size = sheet_spec["size"]
    width, height = SHEET_SIZES[size]
    columns = list(spec["curve_table"]["columns"])
    table_h = spec["text"]["table_height_in"]
    scale_text = sheet_spec["scale_text_format"].format(fpi=fpi)
    st = align.stations()
    bounds = [0.0] + list(match_dists) + [align.length]
    eq_raws = [float(q.raw_station) for q in align.equations]
    width_dims = []
    for n, t in enumerate(align.tangents(), start=1):
        raw = _width_station(begin_station + t.start_dist, begin_station + t.end_dist,
                             eq_raws, fpi, lettering=[_bearing_extent(align, n, fpi)])
        if raw is not None:  # a tangent too short to dimension cleanly is left alone
            width_dims.append({"ref": f"T-{n}", "station": raw, "station_text": st.format(raw),
                               "line_offset_ft": _round2(WIDTH_DIM_LINE_IN * fpi),
                               "text_gap_ft": _round2(WIDTH_TEXT_GAP_FACTOR
                                                      * spec["text"]["label_height_in"] * fpi)})
    if "widths" in ttype.asks and not width_dims:
        raise ValueError(f"seed {seed} has no tangent long enough to dimension the pavement "
                         f"width; use another seed for a {ttype.name} task")
    label_boxes: List[Tuple[float, tuple]] = []
    if n_sheets > 1:
        label_boxes = _label_boxes(align, fpi, turn)
        if "widths" in ttype.shown():  # the width dimensions' text shows on these sheets
            label_boxes += _dimension_boxes(align, half_width, width_dims, fpi, turn)
    sheet_dicts: List[dict] = []
    for i in range(n_sheets):
        name = SHEET_NAMES[i]
        sheet = Sheet(id=f"SH-{i + 1:03d}", name=name, size=size, width_in=width,
                      height_in=height)
        lo, hi = bounds[i], bounds[i + 1]
        if turn:  # the turned line is the same length to the last bit, not past it
            hi = min(hi, laid.length)
        bb = geo.bbox_of_points(segment_points(laid, lo, hi))
        viewport = {"center_paper": list(sheet_spec["viewport"]["center_paper"]),
                    "width_in": sheet_spec["viewport"]["width_in"],
                    "height_in": sheet_spec["viewport"]["height_in"],
                    "model_center": [_round2((bb[0] + bb[2]) / 2.0),
                                     _round2((bb[1] + bb[3]) / 2.0)],
                    "feet_per_inch": float(fpi), "rotation_deg": 0.0}
        if n_sheets > 1:
            # a viewport sized round this sheet's share and its labels, grown so no
            # label of the other share is cut by its edge: the nearest thing to a
            # viewport clipped at the match line
            padded = _sheet_box(laid, lo, hi, fpi, label_boxes)
            viewport["model_center"] = [_round2((padded[0] + padded[2]) / 2.0),
                                        _round2((padded[1] + padded[3]) / 2.0)]
            viewport["width_in"] = _round2((padded[2] - padded[0]) / fpi)
            viewport["height_in"] = _round2((padded[3] - padded[1]) / fpi)
        if turn:
            # the window was fitted on the line as the sheet shows it: the viewport looks
            # at the same place on the road itself, turned back by the twist
            centre = _about(viewport["model_center"], align.pis[0].point, -turn)
            viewport["model_center"] = [_round2(centre[0]), _round2(centre[1])]
            viewport["rotation_deg"] = turn
        lo, hi = bounds[i], bounds[i + 1]
        on_sheet = [k + 1 for k, c in enumerate(align.curves())
                    if c.start_dist < hi - 1e-6 and c.end_dist > lo + 1e-6]
        matches, label_rects = [], []
        for j, d in enumerate(match_dists):
            if d not in (lo, hi):
                continue
            raw = begin_station + d
            other = SHEET_NAMES[i + 1] if d == hi else SHEET_NAMES[i - 1]
            text = st.format(raw)
            label = f"MATCH LINE STA {text} SEE SHEET {other}"
            side, rotation, offset, rect = _match_layout(align, text, label, viewport, sheet)
            label_rects.append(rect)
            matches.append({
                "station": float(raw), "station_text": text,
                "half_width_ft": _round2(MATCH_HALF_IN * fpi), "other_sheet": other,
                "label": label, "label_offset_in": offset, "side": side, "rotation": rotation})
        sheet_dicts.append({
            "name": name, "size": size, "viewport": viewport,
            "station_range": [float(begin_station + lo), float(begin_station + hi)],
            "curves": on_sheet,
            "curve_table_position": _curve_table_position(align, on_sheet, sheet, viewport,
                                                          columns, table_h, avoid=label_rects),
            "title_block_fields": {
                "project": project["name"], "agency": agency, "sheet_title": "ROADWAY PLAN",
                "sheet_number": name, "total_sheets": str(n_sheets), "designed_by": "RD",
                "drawn_by": "AGENT", "checked_by": "RD", "date": date, "scale": scale_text},
            "matches": matches})
        if turn:
            # the arrow stays where the spec puts it, turned to north as the sheet shows
            # it; and a task that lays the sheet out must turn its viewport this much
            na = sheet_spec["north_arrow"]
            sheet_dicts[-1]["north_arrow"] = {"position": list(na["position"]),
                                              "scale": na["scale"], "rotation_deg": turn}
            if "sheet" in ttype.asks:
                sheet_dicts[-1]["twist_deg"] = turn
    deliverable = {
        "task_type": ttype.name, "sheets": sheet_dicts, "feet_per_inch": float(fpi),
        "pavement": {"half_width_ft": half_width, "offsets_ft": [-half_width, half_width],
                     "layer": DRAFTING_SPEC_V1["layers"]["edges"]},
        "width_dimensions": width_dims,
        "dims_layer": DRAFTING_SPEC_V1["layers"]["dims"],
        "stationing_interval_ft": spec["stationing"]["interval_ft"],
        "station_format": spec["stationing"]["format"],
        "required_label_kinds": ["station", "pc", "pt", "bearing", "mc", "curve_table"],
        "curve_table_columns": columns,
        "text_heights": {"model_label_ft": _round2(spec["text"]["label_height_in"] * fpi),
                         "sheet_table_in": table_h},
        "station_lettering": spec["stationing"]["format"],
        "station_label_side": spec["stationing"]["label_side"],
        "tick_half_len_ft": _round2(spec["stationing"]["tick_half_len_in"] * fpi),
        "label_offset_ft": _round2(spec["stationing"]["label_offset_in"] * fpi),
        "point_label_offset_ft": _round2(spec["labels"]["pc_pt"]["label_offset_in"] * fpi),
        "bearing_label_offset_ft": _round2(spec["labels"]["bearing"]["label_offset_in"] * fpi),
        "mc_label_offset_ft": _round2(spec["labels"]["mc"]["label_offset_in"] * fpi),
        "north_arrow": True,
    }
    if align.equations:
        deliverable["required_label_kinds"].append("equation")
    if turn:  # model lettering reads upright through the twist (truth and reference)
        deliverable["view_rotation"] = turn
    if ttype.basefile:
        deliverable["basefile"] = f"{route.replace(' ', '')}-base{INTERCHANGE_EXT}"
    design = {"design_speed_mph": v_mph,
              "alignments": {ALIGNMENT_NAME: align.to_dict()},
              "profiles": {PROFILE_NAME: profile.to_dict()}}
    if "design" not in ttype.given:  # the alignment is the task; nothing else is designed yet
        design["profiles"] = {}
    payload = {"generator_version": GENERATOR_VERSION, "spec_hash": spec_hash(),
               "project": project, "design": design, "deliverable": deliverable}
    task_id = compute_task_id(int(seed), level, payload)
    brief = TaskBrief(task_id=task_id, seed=int(seed), level=level,
                      generator_version=GENERATOR_VERSION, spec_version=SPEC_VERSION,
                      spec_hash=spec_hash(), project=project, design=design,
                      deliverable=deliverable, drafting_spec=spec_subset(), instructions="",
                      task_type=ttype.name, sheets=n_sheets)
    brief.prompts = render_prompts(brief)
    brief.instructions = brief.prompts["explicit"]
    if warnings:
        brief.instructions += "\nNote: " + "; ".join(warnings) + "."

    # ---- truth, then the starting document (the design plus the given phases) and,
    # for a basefile type, the base drawing shipped beside it
    truth = compute_ground_truth(brief)
    seeded = design if "design" in ttype.given else {"alignments": {}, "profiles": {}}
    doc = _baseline(seeded, project, task_id, v_mph, county, agency)
    task = Task(brief=brief, truth=truth, baseline=doc.to_dict())
    if ttype.basefile:
        # the base drawing always carries the design, whether or not the sheet file does
        designed = Task(brief=brief, truth=truth,
                        baseline=_baseline(design, project, task_id, v_mph, county, agency).to_dict())
        base = _draft(designed, ["layers"] + sorted(ttype.basefile, key=PHASE_ORDER.index), seed)
        base.meta["description"] = f"{project['name']} — base drawing"
        task.files[deliverable["basefile"]] = base.to_dict()
    drafted = sorted((p for p in ttype.given if p != "design"), key=PHASE_ORDER.index)
    if drafted:
        task.baseline = _draft(task, drafted, seed).to_dict()
    if crowd:
        from roaddraft.tasks.crowd import crowded
        task = crowded(task, seed)
    if revise:
        from roaddraft.tasks.revise import revised
        task = revised(task, seed, revise)
    if OPEN_BREAKS in ttype.asks:  # the count and the breaks are the drafter's (tasks.breaks)
        from roaddraft.tasks.breaks import opened
        task = opened(task, seed)
    return task


def _draft(task: Task, phases: List[str], seed: int) -> Document:
    """The task's bare starting document with ``phases`` drafted on it."""
    from roaddraft.tasks.reference import phase_commands, session_for_task
    session = session_for_task(task)
    for name, params in phase_commands(task, phases):
        result = session.execute(name, params)
        if not result["ok"]:
            raise AssertionError(f"generator bug: drafting {phases} for {task.brief.task_type} "
                                 f"seed {seed}: {name} failed: {result['error']['message']}")
    return session.doc


def _bearing_extent(align: Alignment, n: int, fpi: float) -> Tuple[float, float]:
    """The raw stations tangent ``n``'s bearing and distance letters over: the
    label is centred on the tangent's midpoint and reads along it, so it
    covers half its width each way, at this scale's text height."""
    spec = DRAFTING_SPEC_V1
    height = _round2(spec["text"]["label_height_in"] * fpi)
    label = compile_label(align, resolve_anchor(align, parse_anchor(f"T-{n}")), "bearing",
                          label_offset=_round2(spec["labels"]["bearing"]["label_offset_in"] * fpi))
    w, _ = geo.text_size(label.content, height)
    return float(label.station) - w / 2.0, float(label.station) + w / 2.0


def _width_station(lo: float, hi: float, avoid: List[float], fpi: float,
                   lettering: Sequence[Tuple[float, float]] = ()) -> Optional[float]:
    """Where a tangent's pavement width is dimensioned: the half station
    (xx+50) nearest its midpoint, else the station on the ``WIDTH_STEP_FT``
    grid nearest the midpoint, such that the dimension line
    (``WIDTH_DIM_LINE_IN`` ahead of the station) is ``WIDTH_LETTER_CLEAR_IN``
    clear of the bearing lettering (``lettering``: the raw-station ranges the
    text covers) and ``WIDTH_STATION_CLEAR_IN`` from every whole station (its
    number sits under the line there); the station itself ``WIDTH_AHEAD_IN``
    short of the tangent's end and ``WIDTH_BEHIND_IN`` past its start (so the
    extension lines stay on the tangent) and ``WIDTH_CLEAR_IN`` from an
    equation label in ``avoid`` (whose band the dimension's text shares).
    None when nothing will do."""
    mid = (lo + hi) / 2.0
    half_sta = math.floor(mid / 100.0) * 100.0 + 50.0
    ahead, behind, clear = WIDTH_AHEAD_IN * fpi, WIDTH_BEHIND_IN * fpi, WIDTH_CLEAR_IN * fpi
    line_ahead = WIDTH_DIM_LINE_IN * fpi
    letter_clear, station_clear = WIDTH_LETTER_CLEAR_IN * fpi, WIDTH_STATION_CLEAR_IN * fpi
    first = math.ceil((lo + behind) / WIDTH_STEP_FT) * WIDTH_STEP_FT
    grid = [first + k * WIDTH_STEP_FT
            for k in range(int(math.floor((hi - ahead - first) / WIDTH_STEP_FT)) + 1)]
    candidates = [half_sta, half_sta - 100.0, half_sta + 100.0, half_sta - 200.0,
                  half_sta + 200.0] + sorted(grid, key=lambda s: (abs(s - mid), s))
    tried = set()
    for raw in candidates:
        if raw in tried:
            continue
        tried.add(raw)
        if not (lo + behind <= raw <= hi - ahead):
            continue
        if any(abs(raw - a) < clear for a in avoid):
            continue
        at = raw + line_ahead  # where the dimension line crosses the centerline
        if any(a - letter_clear < at < b + letter_clear for a, b in lettering):
            continue
        if abs(at - round(at / 100.0) * 100.0) < station_clear:
            continue
        return float(raw)
    return None


__all__ = ["generate_task", "segment_points", "ALIGNMENT_NAME", "PROFILE_NAME", "SPEEDS",
           "CURVE_COUNTS", "SHEET_NAMES", "DOCUMENT_PEOPLE", "seed_twist", "TWIST_MIN_DEG"]
