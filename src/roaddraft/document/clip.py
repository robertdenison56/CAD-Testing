"""Geometric clipping of drawable primitives against polygons: the engine
behind reference clip boundaries and clip masks (MicroStation "reference clip
boundary" / "reference clip mask", AutoCAD XCLIP).

The visible region is *inside the boundary (if one is set) and outside every
mask*. Lines, polylines, arcs and circles are cut where they cross a polygon
edge and only the pieces whose midpoint lies in the visible region survive;
text survives when its insertion point does. Pieces of a cut entity get ids
suffixed '#1', '#2', ... so they stay addressable (hit_test / get_entity).
Because clipping happens on geometry rather than at draw time, renders, DXF
export, extents and picking all agree on what is visible.
"""
from __future__ import annotations

from typing import List

from roaddraft.core import geometry as geo
from roaddraft.document.entities import Arc, Circle, Entity, Line, Polyline, Text

EPS = 1e-9


def _dedupe(values, eps=EPS):
    out = []
    for v in values:
        if not out or v - out[-1] > eps:
            out.append(v)
    return out


class ClipRegion:
    """A boundary polygon (None = unbounded) minus a list of mask polygons,
    in the same coordinates as the primitives being clipped."""

    def __init__(self, boundary=None, masks=None):
        self.boundary = boundary
        self.masks = list(masks or [])
        self.polygons = ([boundary] if boundary else []) + self.masks

    @property
    def empty(self) -> bool:
        return not self.polygons

    def contains(self, p) -> bool:
        if self.boundary is not None and not geo.point_in_polygon(p, self.boundary):
            return False
        return not any(geo.point_in_polygon(p, m) for m in self.masks)

    def segment_cuts(self, a, b):
        ts = []
        for poly in self.polygons:
            ts.extend(geo.segment_polygon_params(a, b, poly))
        return _dedupe(sorted(ts))

    def circle_cuts(self, center, radius):
        angles = []
        for poly in self.polygons:
            angles.extend(geo.circle_polygon_angles(center, radius, poly))
        return _dedupe(sorted(angles))


def _lerp(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def _carry(src: Entity, dst: Entity) -> Entity:
    lw = getattr(src, "_lw_mm", None)
    if lw:
        dst._lw_mm = lw
    return dst


def _props(e: Entity):
    return dict(layer=e.layer, color=e.color, linetype=e.linetype, anchor=e.anchor)


def _segment_pieces(region: ClipRegion, a, b):
    """[(t0, t1)] parameter ranges of segment ab that lie in the region."""
    ts = [0.0] + region.segment_cuts(a, b) + [1.0]
    pieces = []
    for t0, t1 in zip(ts, ts[1:]):
        if t1 - t0 <= EPS:
            continue
        if region.contains(_lerp(a, b, (t0 + t1) / 2.0)):
            pieces.append((t0, t1))
    return pieces


def _clip_line(e: Line, region: ClipRegion):
    pieces = _segment_pieces(region, e.start, e.end)
    if pieces == [(0.0, 1.0)]:
        return [e]
    return [_carry(e, Line(id=f"{e.id}#{k}", start=_lerp(e.start, e.end, t0),
                           end=_lerp(e.start, e.end, t1), **_props(e)))
            for k, (t0, t1) in enumerate(pieces, 1)]


def _clip_polyline(e: Polyline, region: ClipRegion):
    verts = e.vertices
    segs = list(zip(verts, verts[1:]))
    if e.closed and len(verts) > 2:
        segs.append((verts[-1], verts[0]))
    runs = []
    whole = True
    for a, b in segs:
        pieces = _segment_pieces(region, a, b)
        if pieces != [(0.0, 1.0)]:
            whole = False
        for t0, t1 in pieces:
            p, q = _lerp(a, b, t0), _lerp(a, b, t1)
            if runs and t0 == 0.0 and geo.distance(runs[-1][-1], p) <= EPS:
                runs[-1].append(q)
            else:
                runs.append([p, q])
    if whole:
        return [e]
    if e.closed and len(runs) >= 2 \
            and geo.distance(runs[-1][-1], runs[0][0]) <= EPS:
        runs[0] = runs[-1] + runs[0][1:]  # the run wraps past the start vertex
        runs.pop()
    return [_carry(e, Polyline(id=f"{e.id}#{k}", vertices=run, closed=False,
                               **_props(e)))
            for k, run in enumerate(runs, 1)]


def _arc_pieces(region: ClipRegion, center, radius, s, e):
    """[(a0, a1)] angle ranges (degrees, a1 > a0) of the CCW arc s..e that
    lie in the region."""
    cuts = []
    for a in region.circle_cuts(center, radius):
        for cand in (a, a + 360.0):
            if s + EPS < cand < e - EPS:
                cuts.append(cand)
    angles = [s] + _dedupe(sorted(cuts)) + [e]
    pieces = []
    for a0, a1 in zip(angles, angles[1:]):
        if a1 - a0 <= EPS:
            continue
        if region.contains(geo.arc_point(center, radius, (a0 + a1) / 2.0)):
            pieces.append((a0, a1))
    return pieces


def _clip_arc(e: Arc, region: ClipRegion):
    s, end = geo.arc_sweep(e.start_angle_deg, e.end_angle_deg)
    pieces = _arc_pieces(region, e.center, e.radius, s, end)
    if pieces == [(s, end)]:
        return [e]
    return [_carry(e, Arc(id=f"{e.id}#{k}", center=list(e.center),
                          radius=e.radius, start_angle_deg=a0, end_angle_deg=a1,
                          **_props(e)))
            for k, (a0, a1) in enumerate(pieces, 1)]


def _clip_circle(e: Circle, region: ClipRegion):
    cuts = region.circle_cuts(e.center, e.radius)
    if not cuts:
        on_rim = geo.arc_point(e.center, e.radius, 0.0)
        return [e] if region.contains(on_rim) else []
    s = cuts[0]
    pieces = _arc_pieces(region, e.center, e.radius, s, s + 360.0)
    if pieces == [(s, s + 360.0)]:
        return [e]
    return [_carry(e, Arc(id=f"{e.id}#{k}", center=list(e.center),
                          radius=e.radius, start_angle_deg=a0, end_angle_deg=a1,
                          **_props(e)))
            for k, (a0, a1) in enumerate(pieces, 1)]


def clip_primitives(prims, boundary=None, masks=None) -> List[Entity]:
    """Clip expanded primitives (line/polyline/arc/circle/text) to the region
    inside `boundary` and outside every polygon in `masks`. With neither, the
    input is returned unchanged."""
    region = ClipRegion(boundary, masks)
    if region.empty:
        return list(prims)
    out: List[Entity] = []
    for e in prims:
        if isinstance(e, Line):
            out.extend(_clip_line(e, region))
        elif isinstance(e, Polyline):
            out.extend(_clip_polyline(e, region))
        elif isinstance(e, Arc):
            out.extend(_clip_arc(e, region))
        elif isinstance(e, Circle):
            out.extend(_clip_circle(e, region))
        elif isinstance(e, Text):
            if region.contains(e.position):
                out.append(e)
        else:  # compound entity that escaped expansion: keep by bbox center
            try:
                bb = e.bbox(None)
            except Exception:
                bb = None
            if bb is None or region.contains([(bb[0] + bb[2]) / 2.0,
                                              (bb[1] + bb[3]) / 2.0]):
                out.append(e)
    return out
