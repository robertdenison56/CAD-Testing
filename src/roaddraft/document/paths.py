"""Paths: lines, polylines, arcs and circles as one thing to walk along,
project a point onto, offset and intersect.

The drafting tools that work *relative to* linework -- offset it, fillet two
pieces of it, measure along it and square off it, snap to it -- all need the
same few questions answered for every kind of linework, so they are answered
once, here. A path is a run of pieces, each a straight segment or a circular
arc travelled in one direction:

* a line runs start to end; a polyline vertex to vertex (and back to the first
  when closed); an arc counter-clockwise, as the entity stores it; a circle
  counter-clockwise from 0 degrees, closed;
* several entities that join end to end chain into one path, oriented head to
  tail in the order given -- a centerline drawn as line, arc, line.

Sides follow the engine's roadway convention: **right of the direction of
travel is positive**, the way ``draw_offset`` takes 12 for 12 ft right.

Everything here is pure geometry on ``[x, y]`` lists; it reads entities but
never changes a document.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import Arc, Circle, Entity, Line, Polyline

EPS = 1e-9
#: Directions within this many degrees are one direction (a tangent joint).
TANGENT_DEG = 1e-6
#: Default largest gap between pieces of a chain (feet / space units).
CHAIN_TOL = 0.01

PATH_ENTITY_TYPES = (Line, Polyline, Arc, Circle)


class PathError(ValueError):
    """Linework that cannot be walked, offset or met. Carries a teaching hint."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


def _unit(deg: float) -> Tuple[float, float]:
    a = math.radians(deg)
    return math.cos(a), math.sin(a)


def _heading(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _angle_diff(a: float, b: float) -> float:
    """Signed smallest turn from heading ``a`` to heading ``b``, (-180, 180]."""
    d = (b - a) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def _nearest_turn(angle: float, reference: float) -> float:
    """``angle`` plus whole turns, as close as possible to ``reference``."""
    return angle + 360.0 * round((reference - angle) / 360.0)


# ------------------------------------------------------------------ pieces


class Seg:
    """A straight piece travelled from ``a`` to ``b``."""

    kind = "line"

    def __init__(self, a, b):
        self.a = [float(a[0]), float(a[1])]
        self.b = [float(b[0]), float(b[1])]

    @property
    def start(self):
        return list(self.a)

    @property
    def end(self):
        return list(self.b)

    @property
    def length(self) -> float:
        return geo.distance(self.a, self.b)

    @property
    def direction(self) -> float:
        return _heading(self.a, self.b)

    def dir_in(self) -> float:
        return self.direction

    def dir_out(self) -> float:
        return self.direction

    def point_at(self, s: float):
        ux, uy = _unit(self.direction)
        return [self.a[0] + ux * s, self.a[1] + uy * s]

    def dir_at(self, s: float) -> float:
        return self.direction

    def project(self, p):
        """``(s, foot, offset)``: distance along from ``a`` (beyond the ends
        when the foot falls on the extension), the foot of the perpendicular,
        and the signed offset, right positive."""
        ux, uy = _unit(self.direction)
        dx, dy = p[0] - self.a[0], p[1] - self.a[1]
        s = dx * ux + dy * uy
        offset = dx * uy - dy * ux  # right normal is (uy, -ux)
        return s, [self.a[0] + ux * s, self.a[1] + uy * s], offset

    def offset(self, d: float) -> "Seg":
        ux, uy = _unit(self.direction)
        nx, ny = uy * d, -ux * d
        return Seg([self.a[0] + nx, self.a[1] + ny], [self.b[0] + nx, self.b[1] + ny])

    def reversed(self) -> "Seg":
        return Seg(self.b, self.a)

    def with_start(self, p) -> "Seg":
        return Seg(p, self.b)

    def with_end(self, p) -> "Seg":
        return Seg(self.a, p)

    def same_sense(self, other: "Seg") -> bool:
        """Does ``other`` still run the way this one does (not reversed)?"""
        if other.length <= EPS:
            return False
        return abs(_angle_diff(self.direction, other.direction)) < 90.0

    def describe(self) -> str:
        return f"segment [{self.a[0]:.2f}, {self.a[1]:.2f}] to [{self.b[0]:.2f}, {self.b[1]:.2f}]"


class ArcSeg:
    """A circular piece: ``center``, ``radius``, travelled from heading-angle
    ``a0`` to ``a1`` (degrees CCW from +X about the centre; ``a1 > a0`` runs
    counter-clockwise, ``a1 < a0`` clockwise)."""

    kind = "arc"

    def __init__(self, center, radius: float, a0: float, a1: float):
        self.center = [float(center[0]), float(center[1])]
        self.radius = float(radius)
        self.a0 = float(a0)
        self.a1 = float(a1)

    @property
    def sweep(self) -> float:
        return self.a1 - self.a0

    @property
    def sign(self) -> int:
        return 1 if self.sweep >= 0 else -1

    @property
    def length(self) -> float:
        return self.radius * math.radians(abs(self.sweep))

    @property
    def full(self) -> bool:
        return abs(self.sweep) >= 360.0 - 1e-9

    @property
    def start(self):
        return geo.arc_point(self.center, self.radius, self.a0)

    @property
    def end(self):
        return geo.arc_point(self.center, self.radius, self.a1)

    def angle_at(self, s: float) -> float:
        return self.a0 + self.sign * math.degrees(s / self.radius)

    def point_at(self, s: float):
        return geo.arc_point(self.center, self.radius, self.angle_at(s))

    def dir_at(self, s: float) -> float:
        return self.angle_at(s) + self.sign * 90.0

    def dir_in(self) -> float:
        return self.a0 + self.sign * 90.0

    def dir_out(self) -> float:
        return self.a1 + self.sign * 90.0

    def project(self, p):
        """``(s, foot, offset)`` like ``Seg.project``. A point past either end
        projects onto the circle beyond it (s < 0 or s > length), whichever
        end is nearer around the circle. The centre itself has no
        perpendicular: it projects to the start."""
        r = geo.distance(self.center, p)
        if r <= EPS:
            return 0.0, self.start, self.sign * (0.0 - self.radius)
        phi = math.degrees(math.atan2(p[1] - self.center[1], p[0] - self.center[0]))
        t = (self.sign * (phi - self.a0)) % 360.0  # degrees travelled from a0
        span = abs(self.sweep)
        if t > span and not self.full:
            beyond = t - span            # past the end
            before = 360.0 - t           # short of the start
            if before < beyond:
                t = -before
        s = self.radius * math.radians(t)
        foot = geo.arc_point(self.center, self.radius, self.a0 + self.sign * t)
        # right of travel: outside on a counter-clockwise piece, inside on a clockwise one
        return s, foot, self.sign * (r - self.radius)

    def offset(self, d: float) -> Optional["ArcSeg"]:
        radius = self.radius + self.sign * d
        if radius <= EPS:
            return None
        return ArcSeg(self.center, radius, self.a0, self.a1)

    def reversed(self) -> "ArcSeg":
        return ArcSeg(self.center, self.radius, self.a1, self.a0)

    def _angle_of(self, p) -> float:
        return math.degrees(math.atan2(p[1] - self.center[1], p[0] - self.center[0]))

    def with_start(self, p) -> "ArcSeg":
        return ArcSeg(self.center, self.radius, _nearest_turn(self._angle_of(p), self.a0),
                      self.a1)

    def with_end(self, p) -> "ArcSeg":
        return ArcSeg(self.center, self.radius, self.a0,
                      _nearest_turn(self._angle_of(p), self.a1))

    def same_sense(self, other: "ArcSeg") -> bool:
        return other.sweep * self.sweep > 0 and abs(other.sweep) > 1e-9

    def contains_angle(self, angle: float, eps: float = 1e-9) -> bool:
        """Is the heading-angle ``angle`` on this piece?"""
        if self.full:
            return True
        t = (self.sign * (angle - self.a0)) % 360.0
        return t <= abs(self.sweep) + eps or t >= 360.0 - eps

    def describe(self) -> str:
        return (f"arc R={self.radius:.2f} about [{self.center[0]:.2f}, "
                f"{self.center[1]:.2f}]")


Piece = object  # Seg | ArcSeg


def pieces_of(entity: Entity) -> Tuple[List[Piece], bool]:
    """``(pieces, closed)`` for a line, polyline, arc or circle."""
    if isinstance(entity, Line):
        return [Seg(entity.start, entity.end)], False
    if isinstance(entity, Polyline):
        verts = [list(v) for v in entity.vertices]
        pieces = [Seg(a, b) for a, b in zip(verts, verts[1:])
                  if geo.distance(a, b) > EPS]
        closed = bool(entity.closed) and len(verts) > 2
        if closed and geo.distance(verts[-1], verts[0]) > EPS:
            pieces.append(Seg(verts[-1], verts[0]))
        if not pieces:
            raise PathError(f"{entity.id} has no length")
        return pieces, closed
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        return [ArcSeg(entity.center, entity.radius, s, e)], False
    if isinstance(entity, Circle):
        return [ArcSeg(entity.center, entity.radius, 0.0, 360.0)], True
    raise PathError(f"{entity.id} is a {entity.TYPE}, which has no path to work along",
                    hint="lines, polylines, arcs and circles have one")


def _reverse_pieces(pieces: List[Piece]) -> List[Piece]:
    return [p.reversed() for p in reversed(pieces)]


# -------------------------------------------------------------------- paths


@dataclass
class Projection:
    """Where a point falls relative to a path."""

    along: float           # distance from the path's start to the foot
    foot: List[float]      # the foot, on the path or its extension
    offset: float          # signed perpendicular distance, right positive
    piece: int             # which piece it fell on
    perpendicular: bool    # False when no perpendicular exists (outside a corner)
    beyond: Optional[str]  # "start" / "end" when the foot is on an extension
    direction: float       # heading of the path at the foot (degrees CCW from +X)

    @property
    def side(self) -> str:
        if abs(self.offset) < 1e-9:
            return "on"
        return "right" if self.offset > 0 else "left"


class Path:
    """Pieces travelled one after another, optionally closed."""

    def __init__(self, pieces: List[Piece], closed: bool = False, ids=(), owners=None):
        if not pieces:
            raise PathError("a path needs at least one piece")
        self.pieces = pieces
        self.closed = closed
        self.ids = list(ids)
        #: which of ``ids`` each piece was walked from (index into ids)
        self.owners = list(owners) if owners is not None else [0] * len(pieces)
        self.starts = []
        total = 0.0
        for piece in pieces:
            self.starts.append(total)
            total += piece.length
        self.length = total

    # ----------------------------------------------------------- building

    @classmethod
    def of_entity(cls, entity: Entity) -> "Path":
        pieces, closed = pieces_of(entity)
        return cls(pieces, closed, [entity.id], [0] * len(pieces))

    @classmethod
    def of_chain(cls, entities: Sequence[Entity], tol: float = CHAIN_TOL) -> "Path":
        """Entities that join end to end, in order along the path. Each one is
        turned to run on from the one before, so the first sets the direction
        (and with one entity the path is just that entity)."""
        if len(entities) == 1:
            return cls.of_entity(entities[0])
        runs = []
        for entity in entities:
            pieces, closed = pieces_of(entity)
            if closed:
                raise PathError(f"{entity.id} is closed and cannot be part of a chain",
                                hint="a closed polyline or circle is a whole path on "
                                     "its own")
            runs.append(pieces)
        # orient the first run by which of its ends meets the second
        first, second = runs[0], runs[1]
        ends2 = (second[0].start, second[-1].end)
        fwd = min(geo.distance(first[-1].end, q) for q in ends2)
        rev = min(geo.distance(first[0].start, q) for q in ends2)
        if rev < fwd:
            runs[0] = _reverse_pieces(first)
        pieces = list(runs[0])
        owners = [0] * len(pieces)
        for i in range(1, len(runs)):
            run = runs[i]
            here = pieces[-1].end
            d_fwd, d_rev = geo.distance(run[0].start, here), geo.distance(run[-1].end, here)
            gap = min(d_fwd, d_rev)
            if gap > tol:
                raise PathError(
                    f"{entities[i].id} does not join {entities[i - 1].id} (gap "
                    f"{gap:.3f} > {tol:g})",
                    hint="list the entities in order along the path, each touching the "
                         "one before; offset or measure separate pieces one at a time")
            if d_rev < d_fwd:
                run = _reverse_pieces(run)
            pieces.extend(run)
            owners.extend([i] * len(run))
        closed = geo.distance(pieces[-1].end, pieces[0].start) <= tol and len(pieces) > 2
        return cls(pieces, closed, [e.id for e in entities], owners)

    # -------------------------------------------------------------- walking

    def locate(self, dist: float) -> Tuple[int, float]:
        """``(piece index, distance along that piece)`` for a distance along
        the path; outside [0, length] it runs onto the first or last piece."""
        if dist <= 0:
            return 0, dist
        for i, start in enumerate(self.starts):
            if dist <= start + self.pieces[i].length or i == len(self.pieces) - 1:
                return i, dist - start
        return len(self.pieces) - 1, dist - self.starts[-1]

    def point_at(self, dist: float):
        i, s = self.locate(dist)
        return self.pieces[i].point_at(s)

    def dir_at(self, dist: float) -> float:
        i, s = self.locate(dist)
        return self.pieces[i].dir_at(s)

    @property
    def start(self):
        return self.pieces[0].start

    @property
    def end(self):
        return self.pieces[-1].end

    # ------------------------------------------------------------ projecting

    def project(self, p, extend: bool = True) -> Projection:
        """The perpendicular from ``p`` to the path that is shortest.

        A point past the start or end of an open path projects onto the
        extension there (``beyond``) when ``extend``. A point with no
        perpendicular at all -- outside a corner -- gets the nearest corner,
        ``perpendicular`` False."""
        cands = []
        n = len(self.pieces)
        for i, piece in enumerate(self.pieces):
            s, foot, offset = piece.project(p)
            length = piece.length
            beyond = None
            if s < -1e-9:
                if self.closed or i != 0 or not extend:
                    continue
                beyond = "start"
            elif s > length + 1e-9:
                if self.closed or i != n - 1 or not extend:
                    continue
                beyond = "end"
            if beyond is None:
                s = min(max(s, 0.0), length)
            cands.append((abs(offset), beyond is not None, self.starts[i] + s, i, foot,
                          offset, beyond, piece.dir_at(s)))
        if cands:
            cands.sort(key=lambda c: (round(c[0], 9), c[1], c[2]))
            _a, _b, along, i, foot, offset, beyond, direction = cands[0]
            return Projection(along, list(foot), offset, i, True, beyond, direction)
        # no perpendicular anywhere: the nearest corner
        best = None
        for i, piece in enumerate(self.pieces):
            for s, q in ((0.0, piece.start), (piece.length, piece.end)):
                d = geo.distance(p, q)
                if best is None or d < best[0]:
                    best = (d, i, s, q)
        d, i, s, q = best
        piece = self.pieces[i]
        direction = piece.dir_at(s)
        ux, uy = _unit(direction)
        cross = (p[0] - q[0]) * uy - (p[1] - q[1]) * ux
        return Projection(self.starts[i] + s, list(q), math.copysign(d, cross) if d else 0.0,
                          i, False, None, direction)

    def nearest(self, p) -> Tuple[List[float], float, float]:
        """``(point on the path, distance to it, distance along)`` -- the
        closest point on the path itself, never an extension."""
        proj = self.project(p, extend=False)
        best = (proj.foot, geo.distance(p, proj.foot), proj.along)
        for i, piece in enumerate(self.pieces):
            for s, q in ((0.0, piece.start), (piece.length, piece.end)):
                d = geo.distance(p, q)
                if d < best[1] - 1e-12:
                    best = (q, d, self.starts[i] + s)
        return list(best[0]), best[1], best[2]

    # ------------------------------------------------------------- offsetting

    def offset(self, d: float, join: str = "sharp") -> Tuple[List[Piece], List[str]]:
        """Pieces of the parallel path ``d`` to the right (negative: left);
        see ``offset_groups``."""
        groups, notes = self.offset_groups(d, join)
        return [piece for group in groups for piece in group], notes

    def offset_groups(self, d: float, join: str = "sharp"
                      ) -> Tuple[List[List[Piece]], List[str]]:
        """The parallel path ``d`` to the right (negative: left), one group per
        piece of this path: the piece's parallel, then any round join after it.

        Tangent joints meet on their own. At a corner, pieces on the inside
        are trimmed back to where they cross; on the outside, ``join`` =
        ``sharp`` extends them to meet (a mitre, as AutoCAD's OFFSET and
        MicroStation's Copy Parallel do by default) and ``round`` swings an
        arc about the corner. A piece too short to survive the distance -- it
        would run backwards between its trimmed corners -- is dropped and its
        neighbours joined across it, and its group left empty. Raises
        PathError when nothing sensible is left."""
        if join not in ("sharp", "round"):
            raise PathError(f"join must be sharp or round, got {join!r}")
        side = "right" if d > 0 else "left"
        off: List[Piece] = []
        for piece in self.pieces:
            moved = piece.offset(d)
            if moved is None:
                raise PathError(
                    f"offsetting {abs(d):g} to the {side} collapses {piece.describe()} "
                    f"(radius {piece.radius:g})",
                    hint="that side is the inside of the curve: offset less than the "
                         "radius, or to the other side")
            off.append(moved)
        n = len(off)
        active = list(range(n))
        dropped: List[int] = []
        while True:
            groups, notes, inverted = self._joined(off, active, d, join)
            if not inverted:
                break
            left = [i for i in active if i not in inverted]
            if len(left) < (3 if self.closed else 1):
                raise PathError(
                    f"offsetting {abs(d):g} to the {side} turns the shape inside out: "
                    f"{abs(d):g} is too far for it",
                    hint="offset less, or to the other side")
            dropped += inverted
            active = left
        result = [groups.get(i, []) for i in range(n)]
        if dropped:
            notes.append(f"{len(dropped)} piece{'s' if len(dropped) != 1 else ''} too short "
                         f"for a {abs(d):g} offset dropped out of the copy "
                         f"(piece{'s' if len(dropped) != 1 else ''} "
                         f"{', '.join(str(i + 1) for i in sorted(dropped))})")
        return result, notes

    def _joined(self, off: List[Piece], active: List[int], d: float, join: str):
        """Join the offset pieces still in play. Returns ``(groups by piece
        index, notes, pieces that came out reversed)``."""
        notes: List[str] = []
        current = {i: off[i] for i in active}
        extra = {i: [] for i in active}
        pairs = list(zip(active, active[1:]))
        if self.closed and len(active) > 1:
            pairs.append((active[-1], active[0]))
        for i, k in pairs:
            a, b = self.pieces[i], self.pieces[k]
            turn = _angle_diff(a.dir_out(), b.dir_in())
            adjacent = k == (i + 1) % len(self.pieces)
            if adjacent and abs(turn) < TANGENT_DEG:
                continue  # tangent: the offsets already meet
            A, B = current[i], current[k]
            if geo.distance(A.end, B.start) <= 1e-9:
                continue
            corner = a.end if adjacent else [(a.end[0] + b.start[0]) / 2.0,
                                              (a.end[1] + b.start[1]) / 2.0]
            outside = (turn > 0) == (d > 0)
            if outside and join == "round" and adjacent:
                extra[i].append(_corner_arc(corner, abs(d), A.end, B.start, turn))
                continue
            x = _meet(A, B, corner)
            if x is None:
                if outside and adjacent:
                    extra[i].append(_corner_arc(corner, abs(d), A.end, B.start, turn))
                    notes.append(f"the corner at [{corner[0]:.2f}, {corner[1]:.2f}] was "
                                 f"rounded: the offset pieces do not meet there")
                    continue
                raise PathError(
                    f"near [{corner[0]:.2f}, {corner[1]:.2f}] the offset pieces no longer "
                    f"meet: {abs(d):g} is too far for that shape",
                    hint="offset less, or offset the pieces one at a time")
            current[i] = A.with_end(x)
            current[k] = B.with_start(x)
        inverted = [i for i in active
                    if not off[i].same_sense(current[i]) or current[i].length <= 1e-9]
        groups = {i: [current[i]] + extra[i] for i in active}
        return groups, notes, inverted


def _corner_arc(corner, radius: float, p_from, p_to, turn: float) -> ArcSeg:
    """The round join about ``corner`` from one offset piece to the next,
    turning the way the path turns there."""
    a0 = math.degrees(math.atan2(p_from[1] - corner[1], p_from[0] - corner[0]))
    a1 = math.degrees(math.atan2(p_to[1] - corner[1], p_to[0] - corner[0]))
    a1 = a0 + _angle_diff(a0, a1) if abs(_angle_diff(a0, a1)) > 1e-12 else a0
    if (a1 - a0) * turn < 0:  # went the long way round
        a1 += 360.0 if turn > 0 else -360.0
    return ArcSeg(corner, radius, a0, a1)


# ---------------------------------------------------------- intersections


def line_line(a1, b1, a2, b2):
    """Where the infinite lines through a1-b1 and a2-b2 cross, or None."""
    return geo.line_intersection(a1, b1, a2, b2)


def line_circle(a, b, center, radius: float) -> List[List[float]]:
    """Where the infinite line through a-b meets a circle (0, 1 or 2 points)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    qa = dx * dx + dy * dy
    if qa <= 1e-24:
        return []
    fx, fy = a[0] - center[0], a[1] - center[1]
    qb = 2.0 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - radius * radius
    disc = qb * qb - 4.0 * qa * qc
    if disc < -1e-9 * max(1.0, qb * qb):
        return []
    root = math.sqrt(max(disc, 0.0))
    ts = [(-qb - root) / (2.0 * qa), (-qb + root) / (2.0 * qa)]
    if root < 1e-12:
        ts = ts[:1]
    return [[a[0] + t * dx, a[1] + t * dy] for t in ts]


def circle_circle(c1, r1: float, c2, r2: float) -> List[List[float]]:
    """Where two circles meet (0, 1 or 2 points); concentric circles never do."""
    d = geo.distance(c1, c2)
    if d <= 1e-12 or d > r1 + r2 + 1e-9 or d < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    ux, uy = (c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d
    mx, my = c1[0] + a * ux, c1[1] + a * uy
    if h < 1e-12:
        return [[mx, my]]
    return [[mx - h * uy, my + h * ux], [mx + h * uy, my - h * ux]]


def _carrier_meets(A: Piece, B: Piece) -> List[List[float]]:
    """Where the carriers of two pieces meet: lines extended, arcs as circles."""
    if isinstance(A, Seg) and isinstance(B, Seg):
        x = line_line(A.a, A.b, B.a, B.b)
        return [x] if x is not None else []
    if isinstance(A, Seg):
        return line_circle(A.a, A.b, B.center, B.radius)
    if isinstance(B, Seg):
        return line_circle(B.a, B.b, A.center, A.radius)
    return circle_circle(A.center, A.radius, B.center, B.radius)


def _meet(A: Piece, B: Piece, near) -> Optional[List[float]]:
    """Where piece A (extended) meets piece B (extended) nearest ``near``."""
    found = _carrier_meets(A, B)
    if not found:
        return None
    return min(found, key=lambda q: geo.distance(q, near))


def piece_intersections(A: Piece, B: Piece, eps: float = 1e-7) -> List[List[float]]:
    """Points where two pieces themselves (not their extensions) cross or touch."""
    out = []
    for q in _carrier_meets(A, B):
        if _on_piece(A, q, eps) and _on_piece(B, q, eps):
            if not any(geo.distance(q, o) < eps for o in out):
                out.append(q)
    return out


def _on_piece(piece: Piece, q, eps: float) -> bool:
    if isinstance(piece, Seg):
        return geo.dist_point_to_segment(q, piece.a, piece.b) <= eps * max(1.0, piece.length)
    angle = math.degrees(math.atan2(q[1] - piece.center[1], q[0] - piece.center[0]))
    tol_deg = math.degrees(eps / max(piece.radius, eps)) * max(1.0, piece.radius)
    return (abs(geo.distance(q, piece.center) - piece.radius) <= eps * max(1.0, piece.radius)
            and piece.contains_angle(angle, max(tol_deg, 1e-9)))


# ------------------------------------------------------- back to entities


def entity_fields_of(piece: Piece) -> Tuple[type, dict]:
    """``(entity class, geometry fields)`` drawing one piece."""
    if isinstance(piece, Seg):
        return Line, {"start": piece.start, "end": piece.end}
    if piece.full:
        return Circle, {"center": list(piece.center), "radius": piece.radius}
    # an arc entity runs counter-clockwise, so a clockwise piece starts at its end
    lo = (piece.a0 if piece.sweep >= 0 else piece.a1) % 360.0
    return Arc, {"center": list(piece.center), "radius": piece.radius,
                 "start_angle_deg": lo, "end_angle_deg": lo + abs(piece.sweep)}


__all__ = [
    "PathError", "Seg", "ArcSeg", "Path", "Projection", "pieces_of", "line_line",
    "line_circle", "circle_circle", "piece_intersections", "entity_fields_of",
    "PATH_ENTITY_TYPES",
]
