"""Paper-space footprints of everything visible on a deliverable sheet (D1-08).

Legibility is judged in paper space at the deliverable scale (PE decision,
eval plan section 3.7 item 6): a model-space label is mapped through the
viewport it is seen in, so its footprint on paper is its height over the
viewport's feet per inch, turned by the view twist.  Text is an oriented
rectangle (the same width estimate the engine's ``text_bbox`` uses, without
the axis-aligned blow-up a rotated label would otherwise get), tables and
block references their boxes.  Overlap is tested with separating axes and
must be deeper than ``OVERLAP_EPS_IN`` to count, so labels that merely touch
are fine.

A line through a text box is the same offence (d1-verify-v4, 2026-10-16: the
generator's own width dimension line ran through the bearing on nearly every
pavement seed and D1-08 never saw it).  ``sheet_strokes`` gathers the lines
that annotation draws across a sheet -- a dimension's dimension line,
extension lines, stubs and radial leader (``dimgeom.primitives``, never the
arrowheads) and a callout's leader (the line chain that ends at a text's
insertion point, which is what ``place_callout`` draws) -- in paper space
through the viewport like the text, clipped to it, and ``crossing_pairs``
charges a stroke that crosses another owner's footprint drawn in by
``OVERLAP_EPS_IN`` or ends inside it.  Ordinary linework (the centerline, the
edges of pavement, a real sheet's pipes) is not a stroke: text touching an
edge of pavement on a narrow road is ordinary practice (Robert, 2026-10-12).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import BlockRef, Dimension, Line, Table, Text
from roaddraft.verify.context import Context, Rect, SheetView

OVERLAP_EPS_IN = 0.005
Quad = List[List[float]]


@dataclass
class Item:
    entity_id: str
    quad: Quad  # paper corners, counter-clockwise
    box: Rect   # paper axis-aligned bounds of the quad


@dataclass
class Stroke:
    """A line annotation draws across the sheet, in paper space: owned by the
    dimension it belongs to, or by the callout text its leader runs to."""
    entity_id: str
    a: List[float]
    b: List[float]
    box: Rect   # paper axis-aligned bounds of the segment


#: the parts of a dimension that are lines across the sheet: the dimension line,
#: the extension lines, the stubs past them when text and arrows flip outside, and
#: a radial dimension's leader and landing (``dimgeom``); the arrowheads are not
DIMENSION_LINE_PARTS = ("line", "ext1", "ext2", "stub1", "stub2", "landing")


def text_quad(position: Sequence[float], content: str, height: float, rotation_deg: float,
              halign: str, valign: str, width_factor: float = 1.0) -> Quad:
    """Oriented footprint of a text entity: the engine's ``text_bbox`` rectangle,
    rotated rather than boxed."""
    w, h = geo.text_size(str(content), height, width_factor)
    x0 = {"center": -w / 2.0, "right": -w}.get(halign, 0.0)
    y0 = {"middle": -h / 2.0, "top": -h}.get(valign, 0.0)
    corners = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]
    return [geo.translate_point(geo.rotate_point(c, rotation_deg), position) for c in corners]


def _texts(doc, entities):
    """``(owner id, Text)`` for every text in ``entities``: text entities
    themselves and the text a dimension draws."""
    for e in entities:
        if isinstance(e, Text):
            yield e.id, e
        elif isinstance(e, Dimension):
            for prim in e.primitives(doc):
                if isinstance(prim, Text) and prim.content:
                    yield e.id, prim


def _box_quad(bb: Rect) -> Quad:
    return [[bb[0], bb[1]], [bb[2], bb[1]], [bb[2], bb[3]], [bb[0], bb[3]]]


def _item(entity_id: str, quad: Quad) -> Item:
    return Item(entity_id, quad, tuple(geo.bbox_of_points(quad)))


def sheet_items(ctx: Context, sv: Optional[SheetView] = None) -> List[Item]:
    """Every text, table and block reference visible on one deliverable sheet
    (the first by default), model-space text through each viewport that
    shows it."""
    sv = ctx.first if sv is None else sv
    doc, items = ctx.doc, []
    if sv is None or sv.sheet is None:
        return items
    for view in sv.views:
        fpi = float(view.vp.feet_per_inch)
        twist = float(view.vp.rotation_deg)
        for owner, e in _texts(doc, doc.model_entities.values()):
            q = view.transform.to_paper(e.position)
            if not (view.rect[0] <= q[0] <= view.rect[2] and view.rect[1] <= q[1] <= view.rect[3]):
                continue
            style = doc.text_styles.get(e.style)
            items.append(_item(owner, text_quad(q, e.content, e.height / fpi, e.rotation_deg + twist,
                                                e.halign, e.valign,
                                                style.width_factor if style else 1.0)))
    if sv.sheet is not None:
        for owner, e in _texts(doc, sv.sheet.entities.values()):
            style = doc.text_styles.get(e.style)
            items.append(_item(owner, text_quad(e.position, e.content, e.height, e.rotation_deg,
                                                e.halign, e.valign,
                                                style.width_factor if style else 1.0)))
        for e in sv.sheet.entities.values():
            if isinstance(e, (Table, BlockRef)):
                bb = e.bbox(doc)
                if bb is not None:
                    items.append(_item(e.id, _box_quad(bb)))
    return items


def reference_items(ctx: Context, sv: Optional[SheetView] = None) -> List[Item]:
    """Text a sheet's viewports show from the referenced base drawings (the other
    alignments' stationing, R/W tags on a real plan sheet), ids prefixed with the
    reference name.  Context to keep new work clear of, never the drafter's own."""
    from roaddraft.document.references import reference_groups
    sv = ctx.first if sv is None else sv
    items: List[Item] = []
    if sv is None or sv.sheet is None or not sv.views:
        return items
    groups = reference_groups(ctx.doc, "model")
    for view in sv.views:
        fpi = float(view.vp.feet_per_inch)
        twist = float(view.vp.rotation_deg)
        for ref, base, prims in groups:
            for e in prims:
                if not isinstance(e, Text) or not e.content:
                    continue
                q = view.transform.to_paper(e.position)
                if not (view.rect[0] <= q[0] <= view.rect[2] and view.rect[1] <= q[1] <= view.rect[3]):
                    continue
                style = base.text_styles.get(e.style)
                items.append(_item(f"{ref.name}:{e.id}",
                                   text_quad(q, e.content, e.height / fpi, e.rotation_deg + twist,
                                             e.halign, e.valign,
                                             style.width_factor if style else 1.0)))
    return items


def _stroke(entity_id: str, a: Sequence[float], b: Sequence[float]) -> Stroke:
    a, b = [float(a[0]), float(a[1])], [float(b[0]), float(b[1])]
    return Stroke(entity_id, a, b, (min(a[0], b[0]), min(a[1], b[1]),
                                    max(a[0], b[0]), max(a[1], b[1])))


def _dimension_lines(doc, dim: Dimension) -> Iterator[Tuple[list, list]]:
    for prim in dim.primitives(doc):
        if isinstance(prim, Line) and prim.id.rpartition(":")[2] in DIMENSION_LINE_PARTS:
            yield prim.start, prim.end


def _key(p: Sequence[float]) -> Tuple[float, float]:
    return (round(float(p[0]), 6), round(float(p[1]), 6))


def _leaders(entities: Sequence) -> Iterator[Tuple[str, Tuple[list, list]]]:
    """``(text id, (start, end))`` for every callout leader among ``entities``:
    the line with an end at a text's insertion point and, when that line is
    the level shoulder ``place_callout`` draws from the elbow to the text, the
    line that meets its far end (the leader from the target).  Nothing the
    engine draws ends at a label's insertion point otherwise: ticks sit on the
    centerline, a curve bubble's leader starts on the bubble."""
    at = {}
    for e in entities:
        if isinstance(e, Line):
            at.setdefault(_key(e.start), []).append(e)
            at.setdefault(_key(e.end), []).append(e)
    if not at:
        return
    for e in entities:
        if not isinstance(e, Text):
            continue
        here = _key(e.position)
        for first in at.get(here, ()):
            yield e.id, (first.start, first.end)
            if abs(float(first.end[1]) - float(first.start[1])) > 1e-9:
                continue  # not a level shoulder: the leader itself, with no landing
            far = _key(first.end) if _key(first.start) == here else _key(first.start)
            for second in at.get(far, ()):
                if second is not first:
                    yield e.id, (second.start, second.end)


def _lines(doc, entities: Sequence) -> Iterator[Tuple[str, Tuple[list, list]]]:
    for e in entities:
        if isinstance(e, Dimension):
            for a, b in _dimension_lines(doc, e):
                yield e.id, (a, b)
    yield from _leaders(entities)


def clip_segment(a: Sequence[float], b: Sequence[float], rect: Rect):
    """The part of segment ab inside ``rect`` (Liang-Barsky), or None."""
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, float(a[0]) - rect[0]), (dx, rect[2] - float(a[0])),
                 (-dy, float(a[1]) - rect[1]), (dy, rect[3] - float(a[1]))):
        if abs(p) < 1e-15:
            if q < 0.0:
                return None
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    if t0 > t1:
        return None
    return ([float(a[0]) + dx * t0, float(a[1]) + dy * t0],
            [float(a[0]) + dx * t1, float(a[1]) + dy * t1])


def sheet_strokes(ctx: Context, sv: Optional[SheetView] = None) -> List[Stroke]:
    """The lines on one deliverable sheet (the first by default) that may run
    through text: every dimension's lines and every callout's leader, the
    model's through each viewport that shows them (clipped to it, since the
    plot shows no more), the sheet's own as drawn."""
    sv = ctx.first if sv is None else sv
    doc, out = ctx.doc, []
    if sv is None or sv.sheet is None:
        return out
    model = list(doc.model_entities.values())
    for view in sv.views:
        for owner, (a, b) in _lines(doc, model):
            seg = clip_segment(view.transform.to_paper(a), view.transform.to_paper(b), view.rect)
            if seg is not None:
                out.append(_stroke(owner, *seg))
    for owner, (a, b) in _lines(doc, list(sv.sheet.entities.values())):
        out.append(_stroke(owner, a, b))
    return out


def inset(quad: Quad, eps: float) -> Optional[Quad]:
    """A rectangular quad drawn in by ``eps`` on every side; None when nothing
    would be left of it."""
    c0, c1, c3 = quad[0], quad[1], quad[3]
    ux, uy, vx, vy = c1[0] - c0[0], c1[1] - c0[1], c3[0] - c0[0], c3[1] - c0[1]
    w, h = math.hypot(ux, uy), math.hypot(vx, vy)
    if w <= 2.0 * eps or h <= 2.0 * eps:
        return None
    ux, uy, vx, vy = ux / w * eps, uy / w * eps, vx / h * eps, vy / h * eps
    return [[q[0] + su * ux + sv * vx, q[1] + su * uy + sv * vy]
            for q, (su, sv) in zip(quad, ((1, 1), (-1, 1), (-1, -1), (1, -1)))]


def crosses(a: Sequence[float], b: Sequence[float], quad: Quad,
            eps: float = OVERLAP_EPS_IN) -> bool:
    """Whether segment ab runs through ``quad`` deeper than ``eps``: it crosses
    an edge of the quad drawn in by ``eps``, or ends inside it.  A line along
    a text's edge, or one that stops at it, does not."""
    core = inset(quad, eps)
    if core is None:
        return False
    return (bool(geo.segment_polygon_params(a, b, core))
            or geo.point_in_polygon(a, core) or geo.point_in_polygon(b, core))


def crossing_pairs(items: Sequence[Item], strokes: Sequence[Stroke]) -> List[Tuple[str, str]]:
    """``(line owner, text owner)`` for every stroke that runs through another
    owner's item, each pair once; a dimension's lines never cross its own
    text, nor a leader the text it runs to."""
    pairs = set()
    for s in strokes:
        for it in items:
            if it.entity_id == s.entity_id or not geo.bbox_intersects(s.box, it.box):
                continue
            if crosses(s.a, s.b, it.quad):
                pairs.add((s.entity_id, it.entity_id))
    return sorted(pairs)


def _axes(quad: Quad):
    for i in range(len(quad)):
        a, b = quad[i], quad[(i + 1) % len(quad)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length > 1e-12:
            yield (-dy / length, dx / length)


def overlap_depth(p: Quad, q: Quad) -> float:
    """Separating-axis overlap of two convex quads: the smallest projection
    overlap over their edge normals (<= 0 when they are apart)."""
    depth = float("inf")
    for ax in list(_axes(p)) + list(_axes(q)):
        pp = [v[0] * ax[0] + v[1] * ax[1] for v in p]
        qq = [v[0] * ax[0] + v[1] * ax[1] for v in q]
        d = min(max(pp), max(qq)) - max(min(pp), min(qq))
        if d <= 0.0:
            return d
        depth = min(depth, d)
    return depth


def overlapping_pairs(items: Sequence[Item]) -> List[Tuple[str, str]]:
    order = sorted(range(len(items)), key=lambda i: (items[i].box[0], items[i].entity_id))
    pairs = set()
    for n, i in enumerate(order):
        a = items[i]
        for j in order[n + 1:]:
            b = items[j]
            if b.box[0] > a.box[2]:
                break
            if b.box[1] > a.box[3] or b.box[3] < a.box[1] or a.entity_id == b.entity_id:
                continue
            if overlap_depth(a.quad, b.quad) > OVERLAP_EPS_IN:
                pairs.add(tuple(sorted((a.entity_id, b.entity_id))))
    return sorted(pairs)


def clipped(ctx: Context, sv: Optional[SheetView] = None) -> List[str]:
    """Model-space texts a viewport of this sheet cuts in two: the text's
    position is inside the viewport but its footprint crosses the
    viewport's edge, so the plot shows part of it."""
    sv = ctx.first if sv is None else sv
    doc, out = ctx.doc, set()
    if sv is None or sv.sheet is None:
        return []
    eps = OVERLAP_EPS_IN
    for view in sv.views:
        fpi = float(view.vp.feet_per_inch)
        twist = float(view.vp.rotation_deg)
        rect = view.rect
        for owner, e in _texts(doc, doc.model_entities.values()):
            q = view.transform.to_paper(e.position)
            if not (rect[0] <= q[0] <= rect[2] and rect[1] <= q[1] <= rect[3]):
                continue
            style = doc.text_styles.get(e.style)
            quad = text_quad(q, e.content, e.height / fpi, e.rotation_deg + twist, e.halign,
                             e.valign, style.width_factor if style else 1.0)
            if not all(rect[0] - eps <= v[0] <= rect[2] + eps
                       and rect[1] - eps <= v[1] <= rect[3] + eps for v in quad):
                out.add(owner)
    return sorted(out)


#: how far past the reading range a text may turn before it reads upside down (degrees)
READING_TOL_DEG = 1.0


def reads_upside_down(paper_rotation_deg: float) -> bool:
    """Text on paper reads from the bottom or the right of the sheet: along a
    line it is upright (-90, 90], square to one it reads bottom to top
    (-45, 135].  Anything outside (-90, 135] reads upside down, or from the
    left."""
    r = (float(paper_rotation_deg) + 180.0) % 360.0 - 180.0
    return r < -90.0 - READING_TOL_DEG or r > 135.0 + READING_TOL_DEG


def upside_down(ctx: Context, sv: Optional[SheetView] = None) -> List[str]:
    """Texts that read upside down on one deliverable sheet as plotted: model
    text through each viewport that shows it (its rotation plus the view's
    twist), and the sheet's own text."""
    sv = ctx.first if sv is None else sv
    doc, out = ctx.doc, set()
    if sv is None or sv.sheet is None:
        return []
    for view in sv.views:
        twist = float(view.vp.rotation_deg)
        rect = view.rect
        for owner, e in _texts(doc, doc.model_entities.values()):
            q = view.transform.to_paper(e.position)
            if rect[0] <= q[0] <= rect[2] and rect[1] <= q[1] <= rect[3] and \
                    reads_upside_down(e.rotation_deg + twist):
                out.add(owner)
    for owner, e in _texts(doc, sv.sheet.entities.values()):
        if reads_upside_down(e.rotation_deg):
            out.add(owner)
    return sorted(out)


def outside(items: Sequence[Item], usable: Optional[Rect]) -> List[str]:
    if usable is None:
        return []
    eps = OVERLAP_EPS_IN
    return sorted({it.entity_id for it in items
                   if not all(usable[0] - eps <= v[0] <= usable[2] + eps
                              and usable[1] - eps <= v[1] <= usable[3] + eps for v in it.quad)})


__all__ = ["OVERLAP_EPS_IN", "READING_TOL_DEG", "DIMENSION_LINE_PARTS", "Item", "Stroke",
           "text_quad", "sheet_items", "reference_items", "sheet_strokes", "clip_segment",
           "inset", "crosses", "crossing_pairs", "overlap_depth", "overlapping_pairs",
           "outside", "clipped", "reads_upside_down", "upside_down"]
