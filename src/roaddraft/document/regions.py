"""Closed regions: the loops that bound an area, how large it is, and the
region around a point.

An area -- a parking lot to hatch, pavement to quantify, a parcel to report
-- is bounded by one or more closed loops; a loop inside another is an island
(the even-odd rule: a point inside an odd number of loops is in the area).
A loop is a list of vertices joined by segments, each straight or an arc,
stored like a closed polyline: ``{"vertices": [...], "bulges": [...]}``.

Loops come from three places:

* an entity that is closed already -- a closed polyline, a circle;
* entities that join end to end into a closed chain -- four lines;
* a point inside a region of the drawing (AutoCAD's BOUNDARY and the "pick
  internal point" of HATCH): ``trace_region`` walks the linework around the
  point, turning at every crossing to keep the point on its left, until it is
  back where it started. Dangling lines that poke into the region are walked
  out and back and drop away; closed shapes inside the region become islands.

Areas are exact: the polygon through the vertices plus or minus the circular
segment of every arc.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document import paths
from roaddraft.document.entities import Circle, Entity, Polyline, loop_points, loop_segments

#: Default largest gap between linework that still closes a region.
GAP_TOL = 0.01


class RegionError(ValueError):
    """No closed region where one was asked for. Carries a teaching hint."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


# ------------------------------------------------------------------- loops


def loop_from_pieces(pieces: Sequence[paths.Piece]) -> dict:
    """A closed loop through pieces that join end to end (the last back to the
    first)."""
    fields = paths.polyline_fields_of(pieces, closed=True)
    loop = {"vertices": fields["vertices"]}
    if fields.get("bulges"):
        loop["bulges"] = fields["bulges"]
    return loop


def loop_of_entity(entity: Entity) -> Optional[dict]:
    """The loop a closed entity bounds, or None when it is not closed."""
    if isinstance(entity, Circle):
        c, r = entity.center, entity.radius
        return {"vertices": [[c[0] + r, c[1]], [c[0] - r, c[1]]], "bulges": [1.0, 1.0]}
    if isinstance(entity, Polyline) and entity.closed and len(entity.vertices) > 2:
        loop = {"vertices": [list(v) for v in entity.vertices]}
        if entity.has_arcs:
            loop["bulges"] = [entity.bulge(i) for i in range(len(entity.vertices))]
        return loop
    return None


def loop_pieces(loop: dict) -> List[paths.Piece]:
    return [paths.segment_piece(a, b, bulge) for a, b, bulge in loop_segments(loop)
            if geo.distance(a, b) > 1e-12]


def loop_signed_area(loop: dict) -> float:
    """Signed area, positive counter-clockwise: the polygon through the
    vertices plus the circular segment each arc adds (or takes away)."""
    area = 0.0
    for a, b, bulge in loop_segments(loop):
        area += a[0] * b[1] - b[0] * a[1]
    area /= 2.0
    for a, b, bulge in loop_segments(loop):
        arc = geo.bulge_arc(a, b, bulge)
        if arc is None:
            continue
        _c, r, _start, sweep = arc
        theta = math.radians(sweep)
        area += 0.5 * r * r * (theta - math.sin(theta))
    return area


def loop_perimeter(loop: dict) -> float:
    return sum(piece.length for piece in loop_pieces(loop))


def loop_centroid(loop: dict) -> List[float]:
    """Centroid of the area a loop bounds (exact for arcs)."""
    total = 0.0
    cx = cy = 0.0
    for a, b, _bulge in loop_segments(loop):
        cross = a[0] * b[1] - b[0] * a[1]
        total += cross / 2.0
        cx += (a[0] + b[0]) * cross / 6.0
        cy += (a[1] + b[1]) * cross / 6.0
    for a, b, bulge in loop_segments(loop):
        arc = geo.bulge_arc(a, b, bulge)
        if arc is None:
            continue
        center, r, start, sweep = arc
        theta = math.radians(sweep)
        seg_area = 0.5 * r * r * (theta - math.sin(theta))
        half = abs(theta) / 2.0
        # a circular segment's centroid is on its bisector, this far from the centre
        reach = (4.0 * r * math.sin(half) ** 3) / (3.0 * (2 * half - math.sin(2 * half))) \
            if half > 1e-12 else r
        mid = math.radians(start + sweep / 2.0)
        sx, sy = center[0] + reach * math.cos(mid), center[1] + reach * math.sin(mid)
        total += seg_area
        cx += seg_area * sx
        cy += seg_area * sy
    if abs(total) < 1e-15:
        pts = loop["vertices"]
        return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
    return [cx / total, cy / total]


def point_in_loop(p, loop: dict) -> bool:
    return geo.point_in_polygon(p, loop_points(loop, 2.0), tol=0.0)


def loop_bbox(loop: dict):
    bb = None
    for a, b, bulge in loop_segments(loop):
        bb = geo.bbox_union(bb, geo.bulge_bbox(a, b, bulge))
    return bb


def nesting_depths(loops: Sequence[dict]) -> List[int]:
    """How many of the other loops each loop lies inside."""
    probes = [_inside_probe(loop) for loop in loops]
    depths = []
    for i, probe in enumerate(probes):
        depths.append(sum(1 for j, other in enumerate(loops)
                          if j != i and point_in_loop(probe, other)))
    return depths


def _inside_probe(loop: dict) -> List[float]:
    """A point on the loop itself (a vertex will do for containment tests of
    loops that do not cross)."""
    a, b, bulge = loop_segments(loop)[0]
    return geo.bulge_points(a, b, bulge, 45.0)[1] if abs(bulge) > 1e-12 else \
        [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]


def region_measure(loops: Sequence[dict]) -> dict:
    """Area (even-odd: islands subtract), perimeter (every loop), centroid,
    and each loop's own figures."""
    depths = nesting_depths(loops)
    area = 0.0
    mx = my = 0.0
    rows = []
    for loop, depth in zip(loops, depths):
        a = abs(loop_signed_area(loop))
        sign = 1.0 if depth % 2 == 0 else -1.0
        c = loop_centroid(loop)
        area += sign * a
        mx += sign * a * c[0]
        my += sign * a * c[1]
        rows.append({"kind": "outer" if depth % 2 == 0 else "island", "area": a,
                     "perimeter": loop_perimeter(loop), "centroid": c,
                     "vertices": len(loop["vertices"])})
    centroid = [mx / area, my / area] if abs(area) > 1e-15 else (
        rows[0]["centroid"] if rows else None)
    return {"area": area, "perimeter": sum(r["perimeter"] for r in rows),
            "centroid": centroid, "loops": rows}


def oriented(loops: Sequence[dict]) -> List[dict]:
    """The loops turned the way a hatch boundary is written: outer loops
    counter-clockwise, islands clockwise."""
    out = []
    for loop, depth in zip(loops, nesting_depths(loops)):
        ccw = loop_signed_area(loop) > 0
        if ccw != (depth % 2 == 0):
            loop = reverse_loop(loop)
        out.append(loop)
    return out


def reverse_loop(loop: dict) -> dict:
    verts = loop["vertices"]
    n = len(verts)
    out = {"vertices": [list(verts[0])] + [list(v) for v in reversed(verts[1:])]}
    if loop.get("bulges"):
        b = loop["bulges"]
        # reversed segment k runs v(-k) -> v(-k-1): original segment -k-1, backwards
        out["bulges"] = [-b[(-k - 1) % n] for k in range(n)]
    return out


# ---------------------------------------------------- loops from entities


def chain_loops(entities: Sequence[Entity], tol: float = GAP_TOL) -> List[dict]:
    """Closed loops from entities: each closed one on its own, the open ones
    joined end to end into closed chains (in any order and either direction).
    Raises RegionError naming the loose ends of a chain that does not close."""
    loops: List[dict] = []
    open_runs: List[Tuple[str, List[paths.Piece]]] = []
    for entity in entities:
        loop = loop_of_entity(entity)
        if loop is not None:
            loops.append(loop)
            continue
        try:
            pieces, closed = paths.pieces_of(entity)
        except paths.PathError as e:
            raise RegionError(f"{entity.id} is a {entity.TYPE}, which bounds no area",
                              hint="a boundary is made of lines, polylines, arcs and circles")
        open_runs.append((entity.id, pieces))
    while open_runs:
        eid, chain = open_runs.pop(0)
        ids = [eid]
        grew = True
        while grew and geo.distance(chain[-1].end, chain[0].start) > tol:
            grew = False
            for k, (other, run) in enumerate(open_runs):
                head, tail = run[0].start, run[-1].end
                if geo.distance(chain[-1].end, head) <= tol:
                    chain = chain + run
                elif geo.distance(chain[-1].end, tail) <= tol:
                    chain = chain + [p.reversed() for p in reversed(run)]
                elif geo.distance(chain[0].start, tail) <= tol:
                    chain = run + chain
                elif geo.distance(chain[0].start, head) <= tol:
                    chain = [p.reversed() for p in reversed(run)] + chain
                else:
                    continue
                ids.append(other)
                open_runs.pop(k)
                grew = True
                break
        gap = geo.distance(chain[-1].end, chain[0].start)
        if gap > tol:
            a, b = chain[0].start, chain[-1].end
            raise RegionError(
                f"{', '.join(ids)} {'does' if len(ids) == 1 else 'do'} not close: the ends at "
                f"[{a[0]:.2f}, {a[1]:.2f}] and [{b[0]:.2f}, {b[1]:.2f}] are {gap:.3f} apart",
                hint="a boundary must close; add the missing piece, raise gap_tolerance for "
                     "a small gap, or pick a point inside the region (at) to trace it")
        loops.append(loop_from_pieces(chain))
    return loops


# ------------------------------------------------------- tracing a region


class _Arrangement:
    """Pieces of linework and where they cross, worked out lazily: only the
    pieces a boundary walk touches are ever intersected."""

    def __init__(self, pieces: Sequence[paths.Piece], owners: Sequence[str], tol: float):
        self.pieces = list(pieces)
        self.owners = list(owners)
        self.tol = tol
        self.boxes = [geo.bbox_expand(_piece_box(pc), tol) for pc in self.pieces]
        extent = None
        for box in self.boxes:
            extent = geo.bbox_union(extent, box)
        self.extent = extent
        size = max(extent[2] - extent[0], extent[3] - extent[1], tol * 10) if extent else 1.0
        self.cell = size / 64.0
        self.grid: Dict[Tuple[int, int], List[int]] = {}
        for i, box in enumerate(self.boxes):
            for key in self._cells(box):
                self.grid.setdefault(key, []).append(i)
        self._cuts: Dict[int, List[float]] = {}

    def _cells(self, box):
        x0, y0 = int(math.floor(box[0] / self.cell)), int(math.floor(box[1] / self.cell))
        x1, y1 = int(math.floor(box[2] / self.cell)), int(math.floor(box[3] / self.cell))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 4096:  # a huge piece: one coarse entry
            return [("big", 0)]
        return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]

    def near(self, box) -> List[int]:
        found = set(self.grid.get(("big", 0), []))
        for key in self._cells(box):
            found.update(self.grid.get(key, []))
        return [i for i in found if geo.bbox_intersects(self.boxes[i], box)]

    def cuts(self, i: int) -> List[float]:
        """Distances along piece ``i`` where it ends, crosses another piece, or
        another piece ends on it (within the gap tolerance)."""
        if i in self._cuts:
            return self._cuts[i]
        piece = self.pieces[i]
        length = piece.length
        found = [0.0, length]
        for j in self.near(self.boxes[i]):
            if j == i:
                continue
            other = self.pieces[j]
            for q in paths.piece_intersections(piece, other, 1e-9):
                found.append(_along(piece, q))
            for q in (other.start, other.end):
                s, foot, off = piece.project(q)
                if -self.tol <= s <= length + self.tol and abs(off) <= self.tol:
                    found.append(min(max(s, 0.0), length))
        found.sort()
        merged: List[float] = []
        for s in found:
            if not merged or s - merged[-1] > self.tol:
                merged.append(s)
        merged[0] = 0.0
        if length - merged[-1] <= self.tol:
            merged[-1] = length
        else:
            merged.append(length)
        self._cuts[i] = merged
        return merged

    def edges_from(self, q) -> List[Tuple[int, float, float]]:
        """Every way to leave the point ``q`` along the linework:
        ``(piece, from, to)`` distances along the piece."""
        box = (q[0] - self.tol, q[1] - self.tol, q[0] + self.tol, q[1] + self.tol)
        out = []
        for j in self.near(box):
            piece = self.pieces[j]
            s, foot, off = piece.project(q)
            length = piece.length
            if s < -self.tol or s > length + self.tol:
                continue
            if geo.distance(piece.point_at(min(max(s, 0.0), length)), q) > self.tol:
                continue
            s = min(max(s, 0.0), length)
            cuts = self.cuts(j)
            starts = [s]
            if getattr(piece, "full", False) and min(s, length - s) <= self.tol:
                starts = [0.0, length]  # the seam of a circle is both its ends
            for s in starts:
                ahead = [c for c in cuts if c > s + self.tol]
                behind = [c for c in cuts if c < s - self.tol]
                if ahead:
                    out.append((j, s, ahead[0]))
                if behind:
                    out.append((j, s, behind[-1]))
        return out


def _piece_box(piece):
    if isinstance(piece, paths.Seg):
        return geo.bbox_of_points([piece.a, piece.b])
    lo, hi = sorted((piece.a0, piece.a1))
    if hi - lo >= 360.0 - 1e-9:
        c, r = piece.center, piece.radius
        return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
    return geo.arc_bbox(piece.center, piece.radius, lo, hi)


def _along(piece, q) -> float:
    s, _foot, _off = piece.project(q)
    return min(max(s, 0.0), piece.length)


def _chord_heading(arr: _Arrangement, j: int, s_from: float, s_to: float, delta: float,
                   q) -> float:
    """Heading from ``q`` to the point ``delta`` along the edge from
    ``s_from`` toward ``s_to``: the tangent, bent by the edge's curvature,
    which settles edges that leave a vertex on the same tangent."""
    piece = arr.pieces[j]
    step = min(delta, abs(s_to - s_from))
    p = piece.point_at(s_from + step if s_to > s_from else s_from - step)
    return math.degrees(math.atan2(p[1] - q[1], p[0] - q[0]))


def _walk(arr: _Arrangement, start: Tuple[int, float, float], limit: int):
    """Walk a face boundary from a start edge, keeping the face on the left:
    at every vertex take the first edge clockwise from the way back."""
    edges = [start]
    j, s0, s1 = start
    for _ in range(limit):
        piece = arr.pieces[j]
        q = piece.point_at(s1)
        cands = arr.edges_from(q)
        if not cands:
            return None
        # compare directions a short step from the vertex, the same step for all
        delta = min([abs(s1 - s0)] + [abs(c1 - c0) for _cj, c0, c1 in cands]) * 0.25
        delta = max(min(delta, arr.tol * 5.0), 1e-9)
        back = _chord_heading(arr, j, s1, s0, delta, q)
        best = None
        for cand in cands:
            cj, c0, c1 = cand
            reverse = cj == j and abs(c0 - s1) <= arr.tol and abs(c1 - s0) <= arr.tol
            turn = (back - _chord_heading(arr, cj, c0, c1, delta, q)) % 360.0
            if turn < 1e-9 or turn > 360.0 - 1e-9:
                turn = 360.0  # straight back the way it came: a last resort
            key = (turn, 1 if reverse else 0)
            if best is None or key < best[0]:
                best = (key, cand)
        nxt = best[1]
        sj, sa, sb = start
        if nxt[0] == sj and abs(nxt[1] - sa) <= arr.tol and abs(nxt[2] - sb) <= arr.tol:
            return edges
        edges.append(nxt)
        j, s0, s1 = nxt
    return None


def _drop_spikes(edges):
    """Remove edges walked out and straight back (a dangling line)."""
    changed = True
    while changed and len(edges) > 1:
        changed = False
        for k in range(len(edges)):
            a, b = edges[k], edges[(k + 1) % len(edges)]
            if a[0] == b[0] and abs(a[1] - b[2]) < 1e-9 and abs(a[2] - b[1]) < 1e-9:
                if (k + 1) % len(edges) == 0:
                    edges = edges[1:k]
                else:
                    edges = edges[:k] + edges[k + 2:]
                changed = True
                break
    return edges


def _edges_loop(arr: _Arrangement, edges) -> dict:
    vertices, bulges = [], []
    for j, s0, s1 in edges:
        piece = arr.pieces[j]
        if isinstance(piece, paths.Seg):
            vertices.append(piece.point_at(s0))
            bulges.append(0.0)
            continue
        # a bulge cannot hold more than a half circle: split longer arcs
        sweep = math.degrees((s1 - s0) / piece.radius) * piece.sign
        parts = max(1, int(math.ceil(abs(sweep) / 180.0 - 1e-9)))
        for k in range(parts):
            vertices.append(piece.point_at(s0 + (s1 - s0) * k / parts))
            bulges.append(geo.bulge_of_sweep(sweep / parts))
    # a vertex in the middle of a straight run (where a dangling line met it,
    # or two collinear lines join) is no corner: drop it
    k = 0
    while len(vertices) > 3 and k < len(vertices):
        n = len(vertices)
        a, b, c = vertices[k - 1], vertices[k], vertices[(k + 1) % n]
        if abs(bulges[k - 1]) < 1e-12 and abs(bulges[k]) < 1e-12:
            ux, uy = b[0] - a[0], b[1] - a[1]
            vx, vy = c[0] - b[0], c[1] - b[1]
            la, lb = math.hypot(ux, uy), math.hypot(vx, vy)
            if la > 0 and lb > 0 and abs(ux * vy - uy * vx) <= 1e-9 * la * lb \
                    and ux * vx + uy * vy > 0:
                del vertices[k]
                del bulges[k]
                continue
        k += 1
    loop = {"vertices": vertices}
    if any(abs(b) > 1e-12 for b in bulges):
        loop["bulges"] = bulges
    return loop


def _ray_hit(arr: _Arrangement, origin, angle_deg: float, beyond: float = 0.0):
    """The first piece a ray from ``origin`` meets past distance ``beyond``:
    ``(t, piece, s, point)``, or None."""
    ux, uy = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    far = [origin[0] + ux * 1e9, origin[1] + uy * 1e9]
    best = None
    for i, piece in enumerate(arr.pieces):
        box = arr.boxes[i]
        # cheap reject: the ray's half-plane must reach the box
        if ux > 0 and box[2] < origin[0] or ux < 0 and box[0] > origin[0] or \
                uy > 0 and box[3] < origin[1] or uy < 0 and box[1] > origin[1]:
            if abs(ux) > 1e-12 or abs(uy) > 1e-12:
                continue
        for q in paths._carrier_meets(paths.Seg(origin, far), piece):
            t = (q[0] - origin[0]) * ux + (q[1] - origin[1]) * uy
            if t <= beyond + arr.tol:
                continue
            if not paths._on_piece(piece, q, 1e-9):
                continue
            if best is None or t < best[0]:
                best = (t, i, _along(piece, q), q)
    return best


def _good_hit(arr: _Arrangement, hit, angle_deg: float) -> bool:
    t, i, s, q = hit
    piece = arr.pieces[i]
    cuts = arr.cuts(i)
    if any(abs(s - c) <= arr.tol * 10 for c in cuts):
        return False  # at a corner: which side is ambiguous
    d = math.radians(piece.dir_at(s))
    ray = math.radians(angle_deg)
    return abs(math.sin(d - ray)) > 1e-3


RAY_ANGLES = (0.0, 37.0, 113.0, 199.0, 271.0, 61.0, 151.0, 227.0, 313.0, 89.0)


def _walk_from_hit(arr: _Arrangement, origin, hit, limit: int):
    """Walk the face boundary through a ray hit, ``origin`` on its left."""
    t, i, s, q = hit
    piece = arr.pieces[i]
    d = math.radians(piece.dir_at(s))
    dx, dy = math.cos(d), math.sin(d)
    tx, ty = origin[0] - q[0], origin[1] - q[1]
    forward = dx * ty - dy * tx > 0  # origin on the left walking forward
    cuts = arr.cuts(i)
    lo = max(c for c in cuts if c < s)
    hi = min(c for c in cuts if c > s)
    edges = _walk(arr, (i, lo, hi) if forward else (i, hi, lo), limit)
    if edges is None:
        return None
    edges = _drop_spikes(edges)
    return edges or None


def _trace_along(arr: _Arrangement, origin, angle: float, limit: int):
    """Cast one ray from ``origin`` and walk boundaries until the face's own
    outer boundary is found. Returns ``("ok", outer, outer_edges, holes,
    hole_edges)``, ``("open",)`` when the ray escapes (no closed region), or
    ``("bad",)`` when it grazes a corner and another ray should be tried."""
    holes, hole_edges = [], []
    beyond = 0.0
    ux, uy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    for _ in range(64):
        hit = _ray_hit(arr, origin, angle, beyond)
        if hit is None:
            return ("open",)
        if not _good_hit(arr, hit, angle):
            return ("bad",)
        edges = _walk_from_hit(arr, origin, hit, limit)
        if edges is None:
            return ("bad",)
        loop = _edges_loop(arr, edges)
        if loop_signed_area(loop) > 0:
            return ("ok", loop, edges, holes, hole_edges)
        # walked round the outside of a closed shape: an island between the
        # point and the boundary. Carry on past its far side.
        holes.append(loop)
        hole_edges.append(edges)
        far = [origin[0] + ux * 1e9, origin[1] + uy * 1e9]
        reach = hit[0]
        for a, b in geo.polygon_edges(loop_points(loop, 2.0)):
            r = geo.segment_intersection_params(origin, far, a, b)
            if r is not None and 0.0 <= r[1] <= 1.0 and r[0] > 0.0:
                reach = max(reach, r[0] * 1e9)
        beyond = reach + arr.tol
    return ("bad",)


def trace_region(pieces: Sequence[paths.Piece], owners: Sequence[str], point,
                 tol: float = GAP_TOL, islands: bool = True,
                 closed_shapes: Sequence[Tuple[str, dict]] = (), limit: int = 20000) -> dict:
    """The region of the linework around ``point``: ``{"outer": loop,
    "islands": [loop, ...], "ids": [...]}``.

    ``pieces`` are the linework's pieces and ``owners`` the id each came from.
    ``closed_shapes`` are ``(id, loop)`` of closed entities, candidates for
    islands wholly inside the region. Raises RegionError when the point is
    not inside a closed region."""
    if not pieces:
        raise RegionError("there is no linework to find a boundary in")
    arr = _Arrangement(pieces, owners, tol)
    result = None
    for angle in RAY_ANGLES:
        result = _trace_along(arr, point, angle, limit)
        if result[0] != "bad":
            break
    if result is None or result[0] != "ok":
        raise RegionError(
            f"[{point[0]:.2f}, {point[1]:.2f}] is not inside a closed region of the linework",
            hint="the linework around the point must close, within gap_tolerance; check for "
                 "a gap with snap/key_points, close it, or name the boundary entities "
                 "(boundary) instead")
    _ok, outer, outer_edges, holes, hole_edges = result
    used = {j for j, _a, _b in outer_edges}
    for edges in hole_edges:
        used.update(j for j, _a, _b in edges)
    ids = sorted({arr.owners[j] for j in used})
    kept_holes = [h for h in holes if _inside(h, outer)]
    if islands:
        for eid, loop in closed_shapes:
            if eid in ids:
                continue
            if _inside(loop, outer) and not point_in_loop(point, loop) and not any(
                    _inside(loop, h) or _inside(h, loop) for h in kept_holes):
                kept_holes.append(loop)
                ids.append(eid)
    return {"outer": outer, "islands": kept_holes, "ids": ids}


def _inside(inner: dict, outer: dict) -> bool:
    return all(point_in_loop(q, outer) for q in loop_points(inner, 30.0)[::3]) and \
        abs(loop_signed_area(inner)) < abs(loop_signed_area(outer))


__all__ = ["RegionError", "GAP_TOL", "loop_from_pieces", "loop_of_entity", "loop_pieces",
           "loop_signed_area", "loop_perimeter", "loop_centroid", "point_in_loop",
           "loop_bbox", "nesting_depths", "region_measure", "oriented", "reverse_loop",
           "chain_loops", "trace_region"]
