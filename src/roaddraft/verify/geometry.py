"""Geometric matching of linework and ticks against the design (D1-01, D1-02).

Linework earns credit by geometry, anchor or not (eval plan section 3.3):
every model-space line, arc and polyline is broken into *pieces* (a polyline
into its straight and bulged segments), and a piece matches a design element
when it is the same kind and its two ends and its midpoint each lie within
``position_model_ft`` of the element's (either direction).  The midpoint is
what tells an arc from the other arc through the same two points.

A piece that matches no element but lies on the centerline (part of a
tangent, say) is not wrong, it just earns nothing.  A piece that strays off
the centerline is wrong linework when it is on the alignment layer.

Ticks are straight pieces whose ends match a truth tick's ends.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from roaddraft.core import geometry as geo
from roaddraft.design.angles import unit_vector
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment, CurveElement
from roaddraft.document.entities import Arc, Circle, Entity, Line, Polyline


@dataclass
class Piece:
    kind: str  # "line" | "arc" | "circle" (a circle never matches)
    a: List[float]
    b: List[float]
    m: List[float]
    entity: Entity
    samples: List[List[float]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return geo.distance(self.a, self.b)


def _line_piece(a, b, entity) -> Piece:
    a, b = [float(a[0]), float(a[1])], [float(b[0]), float(b[1])]
    m = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
    q1 = [(3 * a[0] + b[0]) / 4.0, (3 * a[1] + b[1]) / 4.0]
    q3 = [(a[0] + 3 * b[0]) / 4.0, (a[1] + 3 * b[1]) / 4.0]
    return Piece("line", a, b, m, entity, [a, q1, m, q3, b])


def _arc_piece(center, radius, start_deg, sweep_deg, entity) -> Piece:
    pts = [geo.arc_point(center, radius, start_deg + sweep_deg * i / 4.0) for i in range(5)]
    return Piece("arc", pts[0], pts[4], pts[2], entity, pts)


def pieces_of(entity: Entity) -> List[Piece]:
    """The matchable pieces of a linework entity ([] for anything else)."""
    if isinstance(entity, Line):
        return [_line_piece(entity.start, entity.end, entity)]
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        return [_arc_piece(entity.center, entity.radius, s, e - s, entity)]
    if isinstance(entity, Polyline):
        out = []
        for a, b, bulge in entity.segments():
            arc = geo.bulge_arc(a, b, bulge)
            if arc is None:
                out.append(_line_piece(a, b, entity))
            else:
                center, radius, start, sweep = arc
                out.append(_arc_piece(center, radius, start, sweep, entity))
        return out
    if isinstance(entity, Circle):
        c, r = entity.center, entity.radius
        pts = [geo.arc_point(c, r, 90.0 * i) for i in range(4)]
        return [Piece("circle", pts[0], pts[0], pts[2], entity, pts)]
    return []


def element_piece(el) -> Piece:
    """The design element as a piece (entity None)."""
    if isinstance(el, CurveElement):
        half = math.degrees(el.length / el.radius) / 2.0
        phi = el.phi0_deg + el.sign * half
        m = [el.center[0] + el.radius * unit_vector(phi)[0],
             el.center[1] + el.radius * unit_vector(phi)[1]]
        return Piece("arc", list(el.pc), list(el.pt), m, None)
    return _line_piece(el.start, el.end, None)


def same_piece(p: Piece, q: Piece, tol: float) -> bool:
    if p.kind != q.kind or geo.distance(p.m, q.m) > tol:
        return False
    return ((geo.distance(p.a, q.a) <= tol and geo.distance(p.b, q.b) <= tol)
            or (geo.distance(p.a, q.b) <= tol and geo.distance(p.b, q.a) <= tol))


def on_centerline(align: Alignment, piece: Piece, tol: float) -> bool:
    """True when every sample of the piece is within ``tol`` of the centerline."""
    if piece.kind == "circle":
        return False
    for p in piece.samples:
        try:
            if abs(align.xy_to_station(p)["offset"]) > tol:
                return False
        except DesignError:
            return False
    return True


@dataclass
class ElementMatch:
    ref: str
    kind: str
    piece: Piece
    hits: List[Piece] = field(default_factory=list)  # document pieces that match it


@dataclass
class LineworkResult:
    elements: List[ElementMatch]
    bad_entities: List[Entity]  # on the alignment layer, off the design


def match_linework(align: Alignment, entities: Sequence[Entity], alignment_layer: str,
                   tol: float) -> LineworkResult:
    elements = [ElementMatch(ref=align.element_ref(i), kind=el.kind, piece=element_piece(el))
                for i, el in enumerate(align.elements)]
    bad: List[Entity] = []
    for entity in entities:
        pieces = pieces_of(entity)
        if not pieces:
            continue
        fits = True
        for piece in pieces:
            hit = False
            for em in elements:
                if same_piece(piece, em.piece, tol):
                    em.hits.append(piece)
                    hit = True
            if not hit and entity.layer == alignment_layer and not on_centerline(align, piece, tol):
                fits = False
        if not fits:
            bad.append(entity)
    return LineworkResult(elements=elements, bad_entities=bad)


@dataclass
class TickMatch:
    truth: dict
    piece: Piece  # the truth tick
    hits: List[Piece] = field(default_factory=list)  # document lines that match it
    near: Optional[Piece] = None  # an unmatched line close by: a misplaced tick


def crosses_at(piece: Piece, tick: Piece, tol: float, rot_tol_deg: float) -> bool:
    """A straight piece crossing the centerline square at the tick's station:
    within ``tol`` of the station point and within ``rot_tol_deg`` of the
    tick's direction, whatever its length or which side it reaches to."""
    if piece.kind != "line" or piece.length <= 0.0:
        return False
    if geo.dist_point_to_segment(tick.m, piece.a, piece.b) > tol:
        return False
    da = math.degrees(math.atan2(piece.b[1] - piece.a[1], piece.b[0] - piece.a[0]))
    dt = math.degrees(math.atan2(tick.b[1] - tick.a[1], tick.b[0] - tick.a[0]))
    off = abs((da - dt) % 180.0)
    return min(off, 180.0 - off) <= rot_tol_deg


def match_ticks(truth_ticks: Sequence[dict], entities: Sequence[Entity], tol: float,
                exact: bool = True, rot_tol_deg: float = 1.0,
                length_range: Optional[Sequence[float]] = None) -> List[TickMatch]:
    """Match truth ticks.  ``exact``: both ends within ``tol`` (the prompt
    stated the tick length).  Otherwise a line crossing at the station square
    to the line counts, with its length within ``length_range`` (model feet)."""
    lines: List[Piece] = []
    for entity in entities:
        if isinstance(entity, Line) or (isinstance(entity, Polyline)
                                        and len(entity.vertices) == 2 and not entity.closed):
            lines.extend(p for p in pieces_of(entity) if p.kind == "line")
    lo, hi = (0.0, float("inf")) if length_range is None else map(float, length_range)
    # bucket by midpoint so a sheet's worth of ticks stays linear
    cell = 10.0 if exact else max(10.0, min(hi, 1000.0) / 2.0)
    buckets: Dict[tuple, List[Piece]] = {}
    for p in lines:
        buckets.setdefault((math.floor(p.m[0] / cell), math.floor(p.m[1] / cell)), []).append(p)

    def near(point, radius):
        r = int(math.ceil(radius / cell))
        cx, cy = math.floor(point[0] / cell), math.floor(point[1] / cell)
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                yield from buckets.get((i, j), ())

    out: List[TickMatch] = []
    for tick in truth_ticks:
        tp = _line_piece(tick["start"], tick["end"], None)
        tm = TickMatch(truth=tick, piece=tp)
        reach = max(tp.length, 1.0) if exact else max(tp.length, 1.0, min(hi, 1000.0))
        best = None
        for p in near(tp.m, reach + tol):
            if exact:
                hit = same_piece(p, tp, tol)
            else:
                hit = lo <= p.length <= hi and crosses_at(p, tp, tol, rot_tol_deg)
            if hit:
                tm.hits.append(p)
                continue
            # a near miss is a tick-sized line close by, not the tangent it sits on
            sized = (p.length <= 2.0 * max(tp.length, 1.0)) if exact else (p.length <= hi)
            d = geo.distance(p.m, tp.m)
            if sized and d <= max(tp.length, 1.0) and (
                    best is None or (d, p.entity.id) < (best[0], best[1].entity.id)):
                best = (d, p)
        if not tm.hits and best is not None:
            tm.near = best[1]
        out.append(tm)
    return out


__all__ = ["Piece", "pieces_of", "element_piece", "same_piece", "on_centerline", "crosses_at",
           "ElementMatch", "LineworkResult", "match_linework", "TickMatch", "match_ticks"]
