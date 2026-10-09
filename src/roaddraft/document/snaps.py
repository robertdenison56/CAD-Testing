"""Object snaps: the exact points a drafter picks instead of eyeballing.

A click is never exactly on anything. CAD makes it exact by snapping: the
pick jumps to the nearest *key point* of the linework under the cursor -- an
endpoint, a midpoint, a centre, where two lines cross, the foot of a
perpendicular from the last point. The same points answer an agent's "where
exactly is the corner of that curb" without arithmetic.

Two questions are answered here:

* ``key_points``: every key point of an entity (or of an alignment, whose
  PIs, BCs and ECs are design points with no entity at them);
* ``snap``: the best key point near a point, the way a cursor snaps, among
  the modes switched on.

On a sheet a snap sees the sheet's own lettering and linework and, through
each viewport, the model -- referenced basefiles included -- so a leader can
be drawn to the edge of pavement it is labelling. Points come back in the
space asked about: paper inches on a sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Entity, Line, Point, Polyline, Table, Text,
)
from roaddraft.document import paths

#: Every snap mode, in the order a tie at the same distance is settled.
SNAP_KINDS = ("endpoint", "intersection", "center", "quadrant", "midpoint", "design",
              "node", "insertion", "perpendicular", "tangent", "nearest")
#: What the cursor snaps to unless told otherwise (AutoCAD's running osnaps
#: plus the design points a roadway plan is built on).
DEFAULT_MODES = ("endpoint", "midpoint", "center", "intersection", "perpendicular",
                 "insertion", "design")
#: Modes that need the point the line is being drawn from.
FROM_MODES = ("perpendicular", "tangent")

_PRIORITY = {kind: i for i, kind in enumerate(SNAP_KINDS)}


@dataclass
class SnapPoint:
    kind: str
    point: List[float]
    ids: Tuple[str, ...] = ()
    label: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self, decimals: int = 6) -> dict:
        out = {"kind": self.kind, "point": [round(v, decimals) for v in self.point],
               "label": self.label}
        if self.ids:
            out["ids"] = list(self.ids)
        out.update(self.extra)
        return out


# ------------------------------------------------------------- key points


def _quadrants(center, radius, arc: Optional[paths.ArcSeg] = None):
    out = []
    for angle in (0.0, 90.0, 180.0, 270.0):
        if arc is None or arc.contains_angle(angle):
            out.append((angle, geo.arc_point(center, radius, angle)))
    return out


def entity_key_points(entity: Entity, eid: Optional[str] = None) -> List[SnapPoint]:
    """The key points of one entity: what a running object snap offers on it."""
    eid = eid or entity.id
    ids = (eid,)
    out: List[SnapPoint] = []
    if isinstance(entity, Line):
        out += [SnapPoint("endpoint", list(entity.start), ids, f"start of {eid}"),
                SnapPoint("endpoint", list(entity.end), ids, f"end of {eid}"),
                SnapPoint("midpoint", [(entity.start[0] + entity.end[0]) / 2.0,
                                       (entity.start[1] + entity.end[1]) / 2.0], ids,
                          f"midpoint of {eid}")]
    elif isinstance(entity, Polyline):
        verts = entity.vertices
        for i, v in enumerate(verts):
            out.append(SnapPoint("endpoint", list(v), ids, f"vertex {i + 1} of {eid}"))
        for i, (a, b, bulge) in enumerate(entity.segments()):
            arc = geo.bulge_arc(a, b, bulge)
            if arc is None:
                out.append(SnapPoint("midpoint", [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0],
                                     ids, f"midpoint of {eid} segment {i + 1}"))
                continue
            center, radius, start, sweep = arc
            piece = paths.ArcSeg(center, radius, start, start + sweep)
            out.append(SnapPoint("midpoint", geo.arc_point(center, radius, start + sweep / 2.0),
                                 ids, f"midpoint of {eid} segment {i + 1}"))
            out.append(SnapPoint("center", list(center), ids,
                                 f"center of {eid} segment {i + 1}"))
            out += [SnapPoint("quadrant", q, ids, f"quadrant {angle:g}° of {eid} segment "
                                                  f"{i + 1}")
                    for angle, q in _quadrants(center, radius, piece)]
    elif isinstance(entity, Point):
        number = f" (point {entity.number})" if entity.number is not None else ""
        out.append(SnapPoint("node", list(entity.position), ids, f"{eid}{number}"))
    elif isinstance(entity, Arc):
        piece = paths.pieces_of(entity)[0][0]
        mid_angle = piece.a0 + piece.sweep / 2.0
        out += [SnapPoint("endpoint", piece.start, ids, f"start of {eid}"),
                SnapPoint("endpoint", piece.end, ids, f"end of {eid}"),
                SnapPoint("midpoint", geo.arc_point(entity.center, entity.radius, mid_angle),
                          ids, f"midpoint of {eid}"),
                SnapPoint("center", list(entity.center), ids, f"center of {eid}")]
        out += [SnapPoint("quadrant", q, ids, f"quadrant {angle:g}° of {eid}")
                for angle, q in _quadrants(entity.center, entity.radius, piece)]
    elif isinstance(entity, Circle):
        out.append(SnapPoint("center", list(entity.center), ids, f"center of {eid}"))
        out += [SnapPoint("quadrant", q, ids, f"quadrant {angle:g}° of {eid}")
                for angle, q in _quadrants(entity.center, entity.radius)]
    elif isinstance(entity, (Text, BlockRef, Table)):
        out.append(SnapPoint("insertion", list(entity.position), ids,
                             f"insertion point of {eid}"))
    elif isinstance(entity, Dimension):
        for name in ("p1", "p2", "center", "line_point"):
            value = getattr(entity, name, None)
            if value is not None:
                out.append(SnapPoint("node", list(value), ids, f"{name} of {eid}"))
    return out


def alignment_key_points(alignment, name: str, placement=None) -> List[SnapPoint]:
    """BEGIN, every PI, BC (PC) and EC (PT), and END of an alignment, in host
    coordinates; each carries the anchor that names it, ready for
    target_anchor."""
    def host(p):
        return list(p) if placement is None or placement.is_identity \
            else placement.to_host(p)

    def point(kind, anchor, label, p):
        return SnapPoint("design", host(p), (), f"{label} of {name}",
                         {"anchor": anchor, "alignment": name, "design": kind})

    out = [point("begin", "BEGIN", "BEGIN", alignment.point_at(0.0))]
    if alignment.pis:
        for i, pi in enumerate(alignment.pis[1:-1], start=2):
            out.append(point("pi", f"PI-{i}", f"PI-{i}", pi.point))
    else:  # laid out from elements: the curves still know their PIs
        for n, curve in enumerate(alignment.curves(), start=1):
            out.append(point("pi", f"PC-{n}", f"PI of curve {n}", curve.pi))
            out[-1].extra.pop("anchor")
    for n, curve in enumerate(alignment.curves(), start=1):
        out.append(point("pc", f"PC-{n}", f"BC-{n} (PC-{n})", curve.pc))
        out.append(point("pt", f"PT-{n}", f"EC-{n} (PT-{n})", curve.pt))
        out.append(point("center", f"PC-{n}", f"radius point of curve {n}",
                         curve.center))
    out.append(point("end", "END", "END", alignment.point_at(alignment.length)))
    # the radius point carries no anchor of its own: it is not on the alignment
    for sp in out:
        if sp.extra["design"] == "center":
            sp.extra.pop("anchor")
    return out


def design_key_points(doc) -> List[SnapPoint]:
    """Design points of every alignment the document owns or references, in
    host model coordinates."""
    out: List[SnapPoint] = []
    for name, alignment in doc.design.alignments.items():
        out += alignment_key_points(alignment, name)
    from roaddraft.document.references import reference_alignments
    for ref, _base, alignment, placement in reference_alignments(doc):
        if ref.space == "model" and ref.visible:
            out += alignment_key_points(alignment, f"{ref.name}:{alignment.name}", placement)
    return out


# --------------------------------------------------------------- the pool


@dataclass
class Item:
    """An entity a snap can land on, with the id it answers to."""

    eid: str
    entity: Entity
    owner: object  # the document it belongs to (a basefile for references)
    _box: object = field(default=None, repr=False)

    @property
    def box(self):
        """The entity's bounding box, worked out once (None: it has none)."""
        if self._box is None:
            self._box = self.entity.bbox(self.owner) or ()
        return self._box or None


def space_items(doc, space_key: str, include_references: bool = True,
                bounds=None, pool: Optional[List[Item]] = None) -> List[Item]:
    """Visible entities of a space (and its attachments), in host coordinates,
    optionally only those whose box meets ``bounds``. ``pool`` is a list made
    earlier by this function for the same space and document state, which a
    cursor asking many times a second reuses instead of re-reading every
    attachment."""
    if pool is not None:
        if bounds is None:
            return list(pool)
        return [item for item in pool
                if item.box is not None and geo.bbox_intersects(item.box, bounds)]
    resolved = doc.resolve_space(space_key)
    items: List[Item] = []
    if resolved is not None:
        for entity in resolved[1].values():
            layer = doc.layers.get(entity.layer)
            if layer is not None and not layer.visible:
                continue
            items.append(Item(entity.id, entity, doc))
    if include_references:
        from roaddraft.document.references import reference_groups
        for ref, base, prims in reference_groups(doc, space_key):
            for prim in prims:
                items.append(Item(f"{ref.name}:{prim.id}", prim, base))
    if bounds is not None:
        items = [item for item in items
                 if item.box is not None and geo.bbox_intersects(item.box, bounds)]
    return items


def _path_pieces(item: Item):
    if not isinstance(item.entity, paths.PATH_ENTITY_TYPES):
        return None
    try:
        return paths.pieces_of(item.entity)[0]
    except paths.PathError:
        return None


def _piece_box(piece):
    if isinstance(piece, paths.Seg):
        return geo.bbox_of_points([piece.a, piece.b])
    c, r = piece.center, piece.radius
    return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)


def intersection_points(items: Sequence[Item], box=None) -> List[SnapPoint]:
    """Where the linework of any two of ``items`` crosses or touches; with
    ``box``, only where the pieces near it do -- a long polyline is hundreds
    of segments, and a cursor needs the two or three under it."""
    pieces = [(item, _path_pieces(item)) for item in items]
    if box is not None:
        pieces = [(item, [pc for pc in p if geo.bbox_intersects(_piece_box(pc), box)])
                  for item, p in pieces if p]
    pieces = [(item, p) for item, p in pieces if p]
    out: List[SnapPoint] = []
    for i in range(len(pieces)):
        item_a, pa = pieces[i]
        for j in range(i + 1, len(pieces)):
            item_b, pb = pieces[j]
            ba, bb = item_a.box, item_b.box
            if ba is None or bb is None or not geo.bbox_intersects(ba, bb, tol=1e-6):
                continue
            for A in pa:
                for B in pb:
                    for q in paths.piece_intersections(A, B):
                        if any(geo.distance(q, o.point) < 1e-7 and set(o.ids) ==
                               {item_a.eid, item_b.eid} for o in out):
                            continue
                        out.append(SnapPoint("intersection", q, (item_a.eid, item_b.eid),
                                             f"intersection of {item_a.eid} and "
                                             f"{item_b.eid}"))
    return out


def _perpendicular_points(item: Item, from_point) -> List[SnapPoint]:
    out = []
    for piece in _path_pieces(item) or []:
        if isinstance(piece, paths.Seg):
            s, foot, _off = piece.project(from_point)
            if -1e-9 <= s <= piece.length + 1e-9:
                out.append(foot)
        else:
            r = geo.distance(piece.center, from_point)
            if r <= 1e-12:
                continue
            ux = (from_point[0] - piece.center[0]) / r
            uy = (from_point[1] - piece.center[1]) / r
            for sign in (1.0, -1.0):
                q = [piece.center[0] + sign * ux * piece.radius,
                     piece.center[1] + sign * uy * piece.radius]
                angle = math.degrees(math.atan2(q[1] - piece.center[1],
                                                q[0] - piece.center[0]))
                if piece.contains_angle(angle):
                    out.append(q)
    return [SnapPoint("perpendicular", q, (item.eid,), f"perpendicular to {item.eid}")
            for q in out]


def _tangent_points(item: Item, from_point) -> List[SnapPoint]:
    out = []
    for piece in _path_pieces(item) or []:
        if not isinstance(piece, paths.ArcSeg):
            continue
        d = geo.distance(piece.center, from_point)
        if d <= piece.radius + 1e-9:
            continue
        base = math.degrees(math.atan2(from_point[1] - piece.center[1],
                                       from_point[0] - piece.center[0]))
        spread = math.degrees(math.acos(piece.radius / d))
        for angle in (base + spread, base - spread):
            if piece.contains_angle(angle):
                out.append(SnapPoint("tangent", geo.arc_point(piece.center, piece.radius,
                                                              angle),
                                     (item.eid,), f"tangent to {item.eid}"))
    return out


def _nearest_point(item: Item, point) -> Optional[SnapPoint]:
    pieces = _path_pieces(item)
    if not pieces:
        return None
    try:
        path = paths.Path(pieces)
    except paths.PathError:
        return None
    q, _d, _along = path.nearest(point)
    return SnapPoint("nearest", q, (item.eid,), f"nearest point on {item.eid}")


def candidates(doc, space_key: str, point, tolerance: float, modes: Sequence[str],
               from_point=None, include_references: bool = True,
               pool_for=None) -> List[SnapPoint]:
    """Snap points of the given modes within ``tolerance`` of ``point`` in one
    space (no viewports), nearest first. ``pool_for(space_key)`` may hand
    over a cached ``space_items`` list."""
    box = (point[0] - tolerance, point[1] - tolerance,
           point[0] + tolerance, point[1] + tolerance)
    items = space_items(doc, space_key, include_references, bounds=box,
                        pool=pool_for(space_key) if pool_for else None)
    found: List[SnapPoint] = []
    wanted = set(modes)
    for item in items:
        if wanted & {"endpoint", "midpoint", "center", "quadrant", "insertion", "node"}:
            found += [sp for sp in entity_key_points(item.entity, item.eid)
                      if sp.kind in wanted]
        if from_point is not None and "perpendicular" in wanted:
            found += _perpendicular_points(item, from_point)
        if from_point is not None and "tangent" in wanted:
            found += _tangent_points(item, from_point)
        if "nearest" in wanted:
            sp = _nearest_point(item, point)
            if sp is not None:
                found.append(sp)
    if "intersection" in wanted and len(items) > 1:
        found += intersection_points(items, box)
    if "design" in wanted and space_key == "model":
        found += design_key_points(doc)
    near = []
    for sp in found:
        d = geo.distance(sp.point, point)
        if d <= tolerance + 1e-12:
            sp.extra["distance"] = d
            near.append(sp)
    near.sort(key=_rank)
    return near


def _rank(sp: SnapPoint):
    # nearest only wins when nothing else is in reach; otherwise closest first,
    # then the more specific kind
    return (sp.kind == "nearest", round(sp.extra.get("distance", 0.0), 9),
            _PRIORITY.get(sp.kind, 99))


def snap(doc, space_key: str, point, tolerance: float, modes: Sequence[str] = DEFAULT_MODES,
         from_point=None, include_references: bool = True, viewport: Optional[str] = None,
         pool_for=None) -> List[SnapPoint]:
    """Snap candidates near ``point``, best first, in the space's own units.

    On a sheet the sheet's own entities are searched, and through the
    viewport under the point (or ``viewport``) the model as well, with the
    results mapped back onto the paper."""
    found = candidates(doc, space_key, point, tolerance, modes, from_point,
                       include_references, pool_for)
    sheet = doc.sheets.get(space_key)
    if sheet is not None and sheet.viewports:
        from roaddraft.document import viewmap
        vp = viewmap.viewport_under(sheet, point, viewport)
        if vp is not None:
            t = vp.transform()
            model_from = t.to_model(from_point) if from_point is not None else None
            for sp in candidates(doc, "model", t.to_model(point),
                                 tolerance * vp.feet_per_inch, modes, model_from,
                                 include_references, pool_for):
                paper = t.to_paper(sp.point)
                if not viewmap.in_window(vp, paper):
                    continue
                sp.extra["model_point"] = [round(v, 6) for v in sp.point]
                sp.extra["viewport"] = vp.id
                sp.point = paper
                sp.extra["distance"] = geo.distance(paper, point)
                sp.label += f" (through {vp.id})"
                found.append(sp)
            found.sort(key=_rank)
    return found


__all__ = ["SNAP_KINDS", "DEFAULT_MODES", "FROM_MODES", "SnapPoint", "Item",
           "entity_key_points",
           "alignment_key_points", "design_key_points", "space_items",
           "intersection_points", "candidates", "snap"]
