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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import BlockRef, Table, Text
from roaddraft.verify.context import Context, Rect, SheetView

OVERLAP_EPS_IN = 0.005
Quad = List[List[float]]


@dataclass
class Item:
    entity_id: str
    quad: Quad  # paper corners, counter-clockwise
    box: Rect   # paper axis-aligned bounds of the quad


def text_quad(position: Sequence[float], content: str, height: float, rotation_deg: float,
              halign: str, valign: str, width_factor: float = 1.0) -> Quad:
    """Oriented footprint of a text entity: the engine's ``text_bbox`` rectangle,
    rotated rather than boxed."""
    w, h = geo.text_size(str(content), height, width_factor)
    x0 = {"center": -w / 2.0, "right": -w}.get(halign, 0.0)
    y0 = {"middle": -h / 2.0, "top": -h}.get(valign, 0.0)
    corners = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]
    return [geo.translate_point(geo.rotate_point(c, rotation_deg), position) for c in corners]


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
        for e in doc.model_entities.values():
            if not isinstance(e, Text):
                continue
            q = view.transform.to_paper(e.position)
            if not (view.rect[0] <= q[0] <= view.rect[2] and view.rect[1] <= q[1] <= view.rect[3]):
                continue
            style = doc.text_styles.get(e.style)
            items.append(_item(e.id, text_quad(q, e.content, e.height / fpi, e.rotation_deg + twist,
                                               e.halign, e.valign,
                                               style.width_factor if style else 1.0)))
    if sv.sheet is not None:
        for e in sv.sheet.entities.values():
            if isinstance(e, Text):
                style = doc.text_styles.get(e.style)
                items.append(_item(e.id, text_quad(e.position, e.content, e.height, e.rotation_deg,
                                                   e.halign, e.valign,
                                                   style.width_factor if style else 1.0)))
            elif isinstance(e, (Table, BlockRef)):
                bb = e.bbox(doc)
                if bb is not None:
                    items.append(_item(e.id, _box_quad(bb)))
    return items


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


def outside(items: Sequence[Item], usable: Optional[Rect]) -> List[str]:
    if usable is None:
        return []
    eps = OVERLAP_EPS_IN
    return sorted({it.entity_id for it in items
                   if not all(usable[0] - eps <= v[0] <= usable[2] + eps
                              and usable[1] - eps <= v[1] <= usable[3] + eps for v in it.quad)})


__all__ = ["OVERLAP_EPS_IN", "Item", "text_quad", "sheet_items", "overlap_depth",
           "overlapping_pairs", "outside"]
