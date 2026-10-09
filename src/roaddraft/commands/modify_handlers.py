"""Editing linework already drawn: the modify toolbox of a CAD program.

* ``trim`` / ``extend`` -- cut linework back to cutting edges, or run it on
  to boundary edges (AutoCAD TRIM / EXTEND, MicroStation Trim to Element /
  Extend Element to Intersection);
* ``break_entity``, ``join_entities``, ``explode_entities`` -- split, merge,
  and take apart;
* ``chamfer`` and ``lengthen`` -- a straight corner cut, and a precise
  change of length;
* ``copy_entities``, ``rotate_entities``, ``mirror_entities``,
  ``scale_entities``, ``array_entities`` -- the transforms, each able to
  leave the original and make copies.

Each handler returns ``(message, diff, warnings)`` and raises ``CommandFault``
with a hint; the bus makes every command atomic, journaled and undoable.
Reference elements ('REFNAME:ID') can be read -- used as cutting edges, as a
path, or copied into this document -- but never changed: reading is not owning.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.commands.edit_handlers import _fmt, _kept_direction, _path_fault, _resolve
from roaddraft.commands.handlers import (
    CommandFault, _add, _diff, _entity_common, _space_label,
)
from roaddraft.core import geometry as geo
from roaddraft.design import cogo
from roaddraft.design.angles import direction_to_azimuth, format_bearing
from roaddraft.document import paths, snaps
from roaddraft.document.document import Document
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Entity, Hatch, Line, Point, Polyline, Table, Text,
    entity_from_dict,
)
from roaddraft.document.transform import Similarity, transform_entity

#: Anchor kinds that are design linework: moving them off the design matters.
LINEWORK_ANCHORS = ("element", "offset")


# ------------------------------------------------------------------ helpers


def _own(doc: Document, eid: str, verb: str):
    """``(space, entity)`` of an entity this document owns."""
    entity, _owner, ref, space_key = _resolve(doc, eid)
    if ref is not None:
        raise CommandFault(
            f"{eid} is in reference {ref}, which this document can read but not {verb}",
            hint="change it in the basefile, or copy_entities it into this document first")
    return space_key, entity


def _container(doc: Document, space_key: str):
    return doc.resolve_space(space_key)[1]


def _props(entity: Entity, anchor: bool = True) -> dict:
    return dict(layer=entity.layer, color=entity.color, linetype=entity.linetype,
                anchor=dict(entity.anchor) if (anchor and entity.anchor) else None,
                annotative=entity.annotative)


def _new_id(doc: Document, entity: Entity) -> str:
    return doc.new_id(entity.TYPE)


def _merge_arcs(pieces: List[paths.Piece]) -> List[paths.Piece]:
    """Consecutive arcs on one circle, turning one way, as one arc."""
    out: List[paths.Piece] = []
    for piece in pieces:
        last = out[-1] if out else None
        if isinstance(piece, paths.ArcSeg) and isinstance(last, paths.ArcSeg) \
                and geo.distance(piece.center, last.center) < 1e-9 \
                and abs(piece.radius - last.radius) < 1e-9 and piece.sweep * last.sweep > 0:
            out[-1] = paths.ArcSeg(last.center, last.radius, last.a0,
                                   last.a1 + piece.sweep)
        else:
            out.append(piece)
    return out


def _rebuild(source: Entity, pieces: List[paths.Piece], eid: str) -> Entity:
    """``source`` redrawn as ``pieces`` (one run), keeping its type where it
    can: a line stays a line, an arc (or a cut circle) an arc, a polyline a
    polyline."""
    props = _props(source)
    if isinstance(source, Polyline):
        return Polyline(id=eid, **props, **paths.polyline_fields_of(pieces, closed=False))
    pieces = _merge_arcs(pieces)
    if len(pieces) != 1:
        return Polyline(id=eid, **props, **paths.polyline_fields_of(pieces, closed=False))
    cls, fields = paths.entity_fields_of(pieces[0])
    return cls(id=eid, **props, **fields)


def _restation(doc: Document, entity: Entity) -> None:
    """Keep a cut piece of design linework anchored at the station it now
    starts at."""
    a = entity.anchor
    if not a or a.get("kind") not in LINEWORK_ANCHORS or a.get("station") is None:
        return
    align = doc.design.alignments.get(a.get("alignment"))
    if align is None:
        return
    try:
        path = paths.Path.of_entity(entity)
        stations = [align.xy_to_station(q)["station"] for q in (path.start, path.end)]
    except Exception:
        return
    entity.anchor = dict(a, station=min(stations))


def _put(doc: Document, space_key: str, entity: Entity) -> None:
    _container(doc, space_key)[entity.id] = entity


def _path_of(entity: Entity, eid: str) -> paths.Path:
    try:
        return paths.Path.of_entity(entity)
    except paths.PathError as e:
        raise _path_fault(e)


def _cutting_pieces(doc: Document, space_key: str, p: dict, exclude: Sequence[str],
                    role: str) -> List[Tuple[str, paths.Piece]]:
    """``[(id, piece)]`` of the cutting / boundary edges: the ones named, else
    every line, polyline, arc and circle in the space (references too)."""
    found = []
    if "boundaries" in p:
        for bid in p["boundaries"]:
            entity, _owner, _ref, sk = _resolve(doc, bid)
            if sk != space_key:
                raise CommandFault(f"{role} {bid} is in {_space_label(doc, sk)}, the "
                                   f"linework in {_space_label(doc, space_key)}")
            if not isinstance(entity, paths.PATH_ENTITY_TYPES):
                raise CommandFault(f"{role} {bid} is a {entity.TYPE}; {role}s are lines, "
                                   f"polylines, arcs and circles")
            found.append((bid, entity))
    else:
        for item in snaps.space_items(doc, space_key, p.get("include_references", True)):
            if isinstance(item.entity, paths.PATH_ENTITY_TYPES):
                found.append((item.eid, item.entity))
    out = []
    for eid, entity in found:
        if eid in exclude:
            continue
        try:
            out += [(eid, piece) for piece in paths.pieces_of(entity)[0]]
        except paths.PathError:
            continue
    return out


def _piece_box(piece) -> tuple:
    return snaps._piece_box(piece)


def _meets(A: paths.Piece, B: paths.Piece, extend_b: bool) -> List[List[float]]:
    """Where piece A meets piece B (B carried on past its ends when
    ``extend_b``: a line as its infinite line, an arc as its circle)."""
    if not extend_b:
        return paths.piece_intersections(A, B)
    return [q for q in paths._carrier_meets(A, B) if paths._on_piece(A, q, 1e-9)]


# --------------------------------------------------------------------- trim


def _cuts(path: paths.Path, cutting, extend_b: bool) -> List[Tuple[float, str]]:
    """``[(distance along, by id)]`` where the cutting edges cross the path."""
    found = []
    for i, A in enumerate(path.pieces):
        box_a = geo.bbox_expand(_piece_box(A), 1e-6)
        for eid, B in cutting:
            if not extend_b and not geo.bbox_intersects(box_a, _piece_box(B)):
                continue
            for q in _meets(A, B, extend_b):
                s, _foot, _off = A.project(q)
                found.append((path.starts[i] + min(max(s, 0.0), A.length), eid))
    found.sort()
    tol = 1e-7 * max(1.0, path.length)
    merged: List[Tuple[float, str]] = []
    for s, eid in found:
        if merged and s - merged[-1][0] <= tol:
            continue
        merged.append((s, eid))
    return merged


def _intervals(path: paths.Path, cuts: List[float]) -> List[Tuple[float, float]]:
    """The runs of a path between its cuts. A closed path's last run wraps
    past the start (s0 > s1)."""
    if path.closed:
        return [(cuts[k], cuts[(k + 1) % len(cuts)]) for k in range(len(cuts))]
    bounds = [0.0] + cuts + [path.length]
    return list(zip(bounds, bounds[1:]))


def _in_run(run: Tuple[float, float], s: float, length: float) -> bool:
    a, b = run
    if a <= b:
        return a - 1e-9 <= s <= b + 1e-9
    return s >= a - 1e-9 or s <= b + 1e-9


def _run_length(run, length: float) -> float:
    a, b = run
    return b - a if a <= b else length - a + b


def trim(doc: Document, p: dict):
    targets = p["targets"]
    extend_b = bool(p.get("extend_boundaries", False))
    grouped: Dict[str, List[dict]] = {}
    order: List[str] = []
    for i, t in enumerate(targets):
        if ("at" in t) == ("keep" in t):
            raise CommandFault(
                f"targets[{i}] needs exactly one of at (a point on the part to cut away) or "
                f"keep (a point on the part to keep)",
                hint="AutoCAD trims the part you click: give that point as at")
        if t["id"] not in grouped:
            order.append(t["id"])
        grouped.setdefault(t["id"], []).append(t)
    created: List[str] = []
    modified: List[str] = []
    deleted: List[str] = []
    lines: List[str] = []
    warnings: List[str] = []
    for eid in order:
        space_key, entity = _own(doc, eid, "trim")
        if not isinstance(entity, paths.PATH_ENTITY_TYPES):
            raise CommandFault(f"{eid} is a {entity.TYPE}; trim cuts lines, polylines, arcs "
                               f"and circles", hint="to remove text or a block, delete it")
        path = _path_of(entity, eid)
        cutting = _cutting_pieces(doc, space_key, p, [eid], "cutting edge")
        found = _cuts(path, cutting, extend_b)
        ends_tol = 1e-7 * max(1.0, path.length)
        if not path.closed:
            found = [(s, by) for s, by in found if ends_tol < s < path.length - ends_tol]
        if path.closed and len(found) < 2:
            raise CommandFault(
                f"{eid} is closed and is crossed at {len(found)} point"
                f"{'' if len(found) == 1 else 's'}; trimming a closed shape takes two",
                hint="name cutting edges that cross it twice (boundaries), or break_entity it "
                     "at two points")
        if not found:
            raise CommandFault(
                f"{eid} crosses none of the cutting edges, so there is nothing to trim it to",
                hint="name the edges to trim to (boundaries), pass extend_boundaries to cut "
                     "where an edge would cross if it ran on, or delete_entities to remove it")
        runs = _intervals(path, [s for s, _by in found])
        by_at = {s: by for s, by in found}
        remove = set()
        for t in grouped[eid]:
            q = t.get("at", t.get("keep"))
            _foot, _d, s = path.nearest(q)
            hit = [k for k, run in enumerate(runs) if _in_run(run, s, path.length)]
            if not hit:
                raise CommandFault(f"the point {_fmt(q)} does not fall on a part of {eid}")
            k = hit[0] if len(hit) == 1 else min(
                hit, key=lambda k: abs(s - (runs[k][0] + runs[k][1]) / 2.0))
            if "at" in t:
                remove.add(k)
            else:
                remove.update(j for j in range(len(runs)) if j != k)
        kept = [run for k, run in enumerate(runs) if k not in remove]
        removed = [run for k, run in enumerate(runs) if k in remove]
        container = _container(doc, space_key)
        if not kept:
            del container[eid]
            deleted.append(eid)
            lines.append(f"{eid} removed entirely (every part of it was picked)")
            continue
        new_ids = []
        for n, run in enumerate(kept):
            pieces = path.sub(run[0], run[1])
            if not pieces:
                continue
            nid = eid if n == 0 else doc.new_id("polyline" if isinstance(entity, Polyline)
                                                else "arc" if isinstance(entity, Circle)
                                                else entity.TYPE)
            part = _rebuild(entity, pieces, nid)
            if isinstance(entity, Circle) and n == 0 and not isinstance(part, Circle):
                # a circle cut open is an arc: it needs an arc's id
                del container[eid]
                deleted.append(eid)
                nid = doc.new_id(part.TYPE)
                part.id = nid
                created.append(nid)
            elif n == 0:
                modified.append(eid)
            else:
                part.id = nid
                created.append(nid)
            _restation(doc, part)
            container[part.id] = part
            new_ids.append(part.id)
        cut_by = sorted({by_at[s] for run in removed for s in run if s in by_at})
        lost = sum(_run_length(run, path.length) for run in removed)
        lines.append(f"{eid} trimmed at {', '.join(cut_by) or 'its cutting edges'}: "
                     f"{lost:.2f}' cut away, {', '.join(new_ids)} kept "
                     f"({sum(_run_length(r, path.length) for r in kept):.2f}')")
    return "; ".join(lines), _diff(created=created, modified=modified,
                                   deleted=deleted), warnings


# ------------------------------------------------------------------- extend


def _which_end(path: paths.Path, t: dict, eid: str) -> str:
    if "end" in t and "at" in t:
        raise CommandFault(f"give end or at for {eid}, not both")
    if "end" in t:
        if t["end"] not in ("start", "end"):
            raise CommandFault(f"end must be start or end, got {t['end']!r}")
        return t["end"]
    if "at" in t:
        q = t["at"]
        return "start" if geo.distance(q, path.start) <= geo.distance(q, path.end) else "end"
    raise CommandFault(f"say which end of {eid} to extend: end (start|end) or at (a point "
                       f"near that end)")


def _ray_reach(piece: paths.Piece, outward: bool, cutting, extend_b: bool):
    """How far past its end a piece can run before it meets a boundary:
    ``(distance beyond, boundary id, point)`` of the nearest, or None.
    ``outward`` means past its end (else back past its start)."""
    best = None
    if isinstance(piece, paths.Seg):
        end = piece.end if outward else piece.start
        heading = piece.direction if outward else piece.direction + 180.0
        ux, uy = math.cos(math.radians(heading)), math.sin(math.radians(heading))
        ray = paths.Seg(end, [end[0] + ux, end[1] + uy])
        for eid, B in cutting:
            for q in paths._carrier_meets(ray, B):
                if not extend_b and not paths._on_piece(B, q, 1e-9):
                    continue
                t = (q[0] - end[0]) * ux + (q[1] - end[1]) * uy
                if t > 1e-7 and (best is None or t < best[0]):
                    best = (t, eid, q)
        return best
    # an arc runs on round its circle
    circle = paths.ArcSeg(piece.center, piece.radius, 0.0, 360.0)
    end_angle = piece.a1 if outward else piece.a0
    turn = piece.sign if outward else -piece.sign  # +1: counter-clockwise onward
    room = 360.0 - abs(piece.sweep)
    for eid, B in cutting:
        for q in paths._carrier_meets(circle, B):
            if not extend_b and not paths._on_piece(B, q, 1e-9):
                continue
            angle = math.degrees(math.atan2(q[1] - piece.center[1], q[0] - piece.center[0]))
            onward = (turn * (angle - end_angle)) % 360.0
            if 1e-7 < onward < room - 1e-7:
                t = piece.radius * math.radians(onward)
                if best is None or t < best[0]:
                    best = (t, eid, q)
    return best


def extend(doc: Document, p: dict):
    extend_b = bool(p.get("extend_boundaries", False))
    modified: List[str] = []
    lines: List[str] = []
    warnings: List[str] = []
    for i, t in enumerate(p["targets"]):
        eid = t["id"]
        space_key, entity = _own(doc, eid, "extend")
        if isinstance(entity, Circle) or (isinstance(entity, Polyline) and entity.closed):
            raise CommandFault(f"{eid} is closed; it has no end to extend")
        if not isinstance(entity, (Line, Arc, Polyline)):
            raise CommandFault(f"{eid} is a {entity.TYPE}; extend runs lines, arcs and open "
                               f"polylines on to a boundary")
        path = _path_of(entity, eid)
        which = _which_end(path, t, eid)
        cutting = _cutting_pieces(doc, space_key, p, [eid], "boundary")
        piece = path.pieces[-1] if which == "end" else path.pieces[0]
        reach = _ray_reach(piece, which == "end", cutting, extend_b)
        if reach is None:
            raise CommandFault(
                f"run on past its {which}, {eid} meets none of the boundary edges",
                hint="name the edge to extend to (boundaries), or pass extend_boundaries "
                     "when the edge itself stops short of where they would meet")
        dist, by, q = reach
        if which == "end":
            grown = piece.cut(0.0, piece.length + dist)
            pieces = path.pieces[:-1] + [grown]
        else:
            grown = piece.cut(-dist, piece.length)
            pieces = [grown] + path.pieces[1:]
        part = _rebuild(entity, pieces, eid)
        _restation(doc, part)
        _put(doc, space_key, part)
        modified.append(eid)
        lines.append(f"{eid} {which} extended {dist:.2f}' to {by} at {_fmt(q)}")
        if entity.anchor and entity.anchor.get("kind") in LINEWORK_ANCHORS:
            warnings.append(f"{eid} is drawn from alignment {entity.anchor.get('alignment')}; "
                            f"extended past where it was drawn, it runs straight on (or round "
                            f"the same radius) rather than following the design")
    return "; ".join(lines), _diff(modified=modified), warnings


# -------------------------------------------------------------------- break


def break_entity(doc: Document, p: dict):
    eid = p["id"]
    space_key, entity = _own(doc, eid, "break")
    if not isinstance(entity, paths.PATH_ENTITY_TYPES):
        raise CommandFault(f"{eid} is a {entity.TYPE}; break splits lines, polylines, arcs "
                           f"and circles")
    path = _path_of(entity, eid)
    s1 = path.nearest(p["at"])[2]
    container = _container(doc, space_key)
    tol = 1e-7 * max(1.0, path.length)
    if "to" not in p:
        if isinstance(entity, Circle):
            raise CommandFault(f"{eid} is a circle; breaking it takes two points (at and to)",
                               hint="the part from at counter-clockwise to to is removed")
        if path.closed:  # a closed polyline opens at the point
            pieces = path.sub(s1, path.length) + path.sub(0.0, s1) \
                if tol < s1 < path.length - tol else list(path.pieces)
            part = Polyline(id=eid, **_props(entity),
                            **paths.polyline_fields_of(pieces, closed=False))
            container[eid] = part
            q = path.point_at(s1)
            return (f"{eid} opened at {_fmt(q)}: an open polyline from there all the way "
                    f"round", _diff(modified=[eid]), [])
        if s1 <= tol or s1 >= path.length - tol:
            raise CommandFault(f"{_fmt(p['at'])} is at an end of {eid}; there is nothing to "
                               f"break off", hint="pick a point between its ends")
        first = _rebuild(entity, path.sub(0.0, s1), eid)
        second = _rebuild(entity, path.sub(s1, path.length), doc.new_id(entity.TYPE))
        for part in (first, second):
            _restation(doc, part)
            container[part.id] = part
        q = path.point_at(s1)
        return (f"{eid} broken at {_fmt(q)} into {first.id} ({s1:.2f}') "
                f"and {second.id} ({path.length - s1:.2f}')",
                _diff(created=[second.id], modified=[eid]), [])
    s2 = path.nearest(p["to"])[2]
    if abs(s2 - s1) <= tol:
        raise CommandFault("at and to are the same point on the entity",
                           hint="give two different points; with one, the entity is split")
    if path.closed:
        # remove from at onward (counter-clockwise / in vertex order) to to
        keep_pieces = path.sub(s2, s1)
        part = _rebuild(entity, keep_pieces, eid) if not isinstance(entity, Polyline) else \
            Polyline(id=eid, **_props(entity),
                     **paths.polyline_fields_of(keep_pieces, closed=False))
        if part.TYPE != entity.TYPE:
            del container[eid]
            part.id = doc.new_id(part.TYPE)
            container[part.id] = part
            gone = _run_length((s1, s2), path.length)
            return (f"{eid} broken: {gone:.2f}' removed from {_fmt(path.point_at(s1))} to "
                    f"{_fmt(path.point_at(s2))}; what is left is {part.TYPE} {part.id}",
                    _diff(created=[part.id], deleted=[eid]), [])
        container[eid] = part
        return (f"{eid} broken: {_run_length((s1, s2), path.length):.2f}' removed",
                _diff(modified=[eid]), [])
    a, b = sorted((s1, s2))
    created, modified, deleted = [], [], []
    parts = []
    if a > tol:
        parts.append(path.sub(0.0, a))
    if b < path.length - tol:
        parts.append(path.sub(b, path.length))
    if not parts:
        del container[eid]
        return f"{eid} removed: the break took all of it", _diff(deleted=[eid]), []
    for n, pieces in enumerate(parts):
        part = _rebuild(entity, pieces, eid if n == 0 else doc.new_id(entity.TYPE))
        _restation(doc, part)
        container[part.id] = part
        (modified if n == 0 else created).append(part.id)
    return (f"{eid} broken: {b - a:.2f}' removed between {_fmt(path.point_at(a))} and "
            f"{_fmt(path.point_at(b))}; {', '.join(modified + created)} left",
            _diff(created=created, modified=modified, deleted=deleted), [])


# --------------------------------------------------------------------- join


def _collinear_lines(lines: List[Line], tol: float):
    a, b = lines[0].start, lines[0].end
    length = geo.distance(a, b)
    if length <= 1e-12:
        return None
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    spans = []
    for line in lines:
        for q in (line.start, line.end):
            if abs((q[0] - a[0]) * uy - (q[1] - a[1]) * ux) > tol:
                return None
        s0 = (line.start[0] - a[0]) * ux + (line.start[1] - a[1]) * uy
        s1 = (line.end[0] - a[0]) * ux + (line.end[1] - a[1]) * uy
        spans.append(sorted((s0, s1)))
    spans.sort()
    gaps = []
    reach = spans[0][1]
    for lo, hi in spans[1:]:
        if lo > reach + tol:
            gaps.append(lo - reach)
        reach = max(reach, hi)
    lo = spans[0][0]
    return ([a[0] + ux * lo, a[1] + uy * lo], [a[0] + ux * reach, a[1] + uy * reach], gaps)


def _cocircular_arcs(arcs: List[Arc], tol: float):
    c, r = arcs[0].center, arcs[0].radius
    for arc in arcs[1:]:
        if geo.distance(arc.center, c) > tol or abs(arc.radius - r) > tol:
            return None
    spans = []
    for arc in arcs:
        s, e = geo.arc_sweep(arc.start_angle_deg, arc.end_angle_deg)
        spans.append((s, e))
    # walk counter-clockwise from the first arc, taking each arc that starts
    # within reach of where the run has got to
    start, reach = spans[0]
    left = spans[1:]
    gaps = []
    while left:
        best = None
        for k, (s, e) in enumerate(left):
            ahead = (s - reach) % 360.0
            if ahead > 360.0 - 1e-6:
                ahead = 0.0
            if best is None or ahead < best[0]:
                best = (ahead, k)
        ahead, k = best
        s, e = left.pop(k)
        if ahead > 1e-6 and ahead * math.pi / 180.0 * r > tol:
            gaps.append(ahead * math.pi / 180.0 * r)
        reach = reach + ahead + (e - s)
    return c, r, start, reach, gaps


def _chain(entities: List[Entity], tol: float):
    """Pieces of entities joined end to end in some order: ``(pieces, closed,
    order of ids)``. Raises CommandFault naming a loose end."""
    runs = []
    for e in entities:
        if isinstance(e, Circle) or (isinstance(e, Polyline) and e.closed):
            raise CommandFault(f"{e.id} is closed; join links open pieces end to end")
        runs.append((e.id, paths.pieces_of(e)[0]))
    eid, chain = runs.pop(0)
    order = [eid]
    grew = True
    while runs and grew:
        grew = False
        for k, (other, run) in enumerate(runs):
            head, tail = run[0].start, run[-1].end
            if geo.distance(chain[-1].end, head) <= tol:
                chain = chain + run
            elif geo.distance(chain[-1].end, tail) <= tol:
                chain = chain + [pc.reversed() for pc in reversed(run)]
            elif geo.distance(chain[0].start, tail) <= tol:
                chain = run + chain
            elif geo.distance(chain[0].start, head) <= tol:
                chain = [pc.reversed() for pc in reversed(run)] + chain
            else:
                continue
            order.append(other)
            runs.pop(k)
            grew = True
            break
    if runs:
        loose = ", ".join(eid for eid, _r in runs)
        raise CommandFault(
            f"{loose} {'does' if len(runs) == 1 else 'do'} not join the others end to end "
            f"(within {tol:g})",
            hint="join links pieces that touch end to end; extend, trim or fillet them to meet "
                 "first, or raise tolerance for a small gap. Collinear lines and arcs on one "
                 "circle join across gaps")
    # close tiny gaps between pieces by snapping each start to the previous end
    fixed = [chain[0]]
    for piece in chain[1:]:
        if geo.distance(fixed[-1].end, piece.start) > 1e-12:
            piece = piece.with_start(fixed[-1].end)
        fixed.append(piece)
    closed = geo.distance(fixed[-1].end, fixed[0].start) <= tol and len(fixed) > 1
    if closed and geo.distance(fixed[-1].end, fixed[0].start) > 1e-12:
        fixed[-1] = fixed[-1].with_end(fixed[0].start)
    return fixed, closed, order


def join_entities(doc: Document, p: dict):
    ids = list(p["ids"])
    if len(set(ids)) != len(ids):
        raise CommandFault("ids lists an entity twice")
    tol = float(p.get("tolerance", 0.01))
    found = [_own(doc, eid, "join") for eid in ids]
    spaces = {sk for sk, _e in found}
    if len(spaces) > 1:
        raise CommandFault("the entities are in different spaces")
    space_key = spaces.pop()
    entities = [e for _sk, e in found]
    for e in entities:
        if not isinstance(e, (Line, Arc, Polyline)):
            raise CommandFault(f"{e.id} is a {e.TYPE}; join links lines, arcs and polylines")
    container = _container(doc, space_key)
    first = entities[0]
    warnings = []
    if any(e.anchor for e in entities):
        warnings.append("the joined entity carries no design anchor: one piece of linework "
                        "no longer stands for one element of the alignment")
    props = _props(first, anchor=False)
    deleted = [e.id for e in entities[1:]]
    if all(isinstance(e, Line) for e in entities):
        joined = _collinear_lines(entities, tol)
        if joined is not None:
            a, b, gaps = joined
            for eid in deleted:
                del container[eid]
            container[first.id] = Line(id=first.id, **props, start=a, end=b)
            note = f", across {len(gaps)} gap{'s' if len(gaps) != 1 else ''}" if gaps else ""
            return (f"{len(ids)} collinear lines joined into {first.id} from {_fmt(a)} to "
                    f"{_fmt(b)} ({geo.distance(a, b):.2f}'){note}",
                    _diff(modified=[first.id], deleted=deleted), warnings)
    if all(isinstance(e, Arc) for e in entities):
        joined = _cocircular_arcs(entities, tol)
        if joined is not None:
            c, r, start, end, gaps = joined
            for eid in deleted:
                del container[eid]
            if end - start >= 360.0 - 1e-6:
                del container[first.id]
                circle = Circle(id=doc.new_id("circle"), **props, center=list(c), radius=r)
                container[circle.id] = circle
                return (f"{len(ids)} arcs close the circle: circle {circle.id} R={r:.2f}'",
                        _diff(created=[circle.id], deleted=[first.id] + deleted), warnings)
            container[first.id] = Arc(id=first.id, **props, center=list(c), radius=r,
                                      start_angle_deg=start, end_angle_deg=end)
            note = f", across {len(gaps)} gap{'s' if len(gaps) != 1 else ''}" if gaps else ""
            return (f"{len(ids)} arcs on one circle joined into {first.id} (R={r:.2f}', "
                    f"{end - start:.4f}°){note}",
                    _diff(modified=[first.id], deleted=deleted), warnings)
    pieces, closed, order = _chain(entities, tol)
    fields = paths.polyline_fields_of(pieces, closed)
    for e in entities:
        del container[e.id]
    if isinstance(first, Polyline):
        joined = Polyline(id=first.id, **props, **fields)
        container[first.id] = joined
        diff = _diff(modified=[first.id], deleted=deleted)
    else:
        joined = Polyline(id=doc.new_id("polyline"), **props, **fields)
        container[joined.id] = joined
        diff = _diff(created=[joined.id], deleted=[e.id for e in entities])
    length = sum(pc.length for pc in pieces)
    return (f"joined {' > '.join(order)} into polyline {joined.id} "
            f"({len(fields['vertices'])} vertices, {length:.2f}'"
            f"{', closed' if closed else ''})", diff, warnings)


# ------------------------------------------------------------------ explode


def _explode_parts(doc: Document, entity: Entity) -> List[Entity]:
    if isinstance(entity, Polyline):
        out = []
        for piece in paths.pieces_of(entity)[0]:
            cls, fields = paths.entity_fields_of(piece)
            out.append(cls(id="", **_props(entity, anchor=False), **fields))
        return out
    if isinstance(entity, BlockRef):
        block = doc.blocks.get(entity.block_name)
        if block is None:
            raise CommandFault(f"block {entity.block_name!r} of {entity.id} is not defined")
        bx, by = block.base_point
        if entity.mirrored:
            place = Similarity(scale=entity.scale, rotation_deg=entity.rotation_deg + 180.0,
                               mirror=True)
        else:
            place = Similarity(scale=entity.scale, rotation_deg=entity.rotation_deg)
        origin = place.apply([bx, by])
        place = place.then_translate([entity.position[0] - origin[0],
                                      entity.position[1] - origin[1]])
        out = []
        for inner in block.entities:
            part = transform_entity(inner, place)
            if part.layer == "0" or part.layer not in doc.layers:
                part.layer = entity.layer  # what was drawn on 0 takes the insert's layer
            if part.color is None:
                part.color = entity.color
            part.anchor = None
            out.append(part)
        return out
    if isinstance(entity, (Dimension, Table, Point)):
        out = []
        for prim in entity.primitives(doc):
            prim.anchor = None
            prim.annotative = None
            out.append(prim)
        return out
    if isinstance(entity, Hatch):
        out = []
        for loop in entity.loops:
            fields = {"vertices": [list(v) for v in loop["vertices"]], "closed": True}
            if loop.get("bulges"):
                fields["bulges"] = list(loop["bulges"])
            out.append(Polyline(id="", **_props(entity, anchor=False), **fields))
        return out
    raise CommandFault(f"{entity.id} is a {entity.TYPE}, which is already as simple as it gets",
                       hint="explode takes polylines, blocks, dimensions, tables, points and "
                            "hatches apart")


def explode_entities(doc: Document, p: dict):
    created: List[str] = []
    deleted: List[str] = []
    lines: List[str] = []
    for eid in p["ids"]:
        space_key, entity = _own(doc, eid, "explode")
        parts = _explode_parts(doc, entity)
        container = _container(doc, space_key)
        del container[eid]
        deleted.append(eid)
        made = []
        for part in parts:
            part.id = doc.new_id(part.TYPE)
            container[part.id] = part
            made.append(part.id)
        created += made
        what = "boundary polyline" if isinstance(entity, Hatch) else "piece"
        what += "" if len(made) == 1 else "s"
        lines.append(f"{eid} ({entity.TYPE}) exploded into {len(made)} {what}"
                     + (f": {', '.join(made)}" if len(made) <= 12 else ""))
    return "; ".join(lines), _diff(created=created, deleted=deleted), []


# ------------------------------------------------------------------ chamfer


def chamfer(doc: Document, p: dict):
    ids = list(p["ids"])
    if len(ids) != 2 or ids[0] == ids[1]:
        raise CommandFault("chamfer cuts the corner between two different lines: ids takes "
                           "exactly two")
    trim_lines = bool(p.get("trim", True))
    found = [_resolve(doc, eid) for eid in ids]
    for eid, (entity, _owner, ref, _sk) in zip(ids, found):
        if not isinstance(entity, Line):
            raise CommandFault(f"{eid} is a {entity.TYPE}; chamfer joins two lines")
        if ref is not None and trim_lines:
            raise CommandFault(f"{eid} is in reference {ref}, which this document cannot trim",
                               hint="pass trim: false to draw only the chamfer line")
    if found[0][3] != found[1][3]:
        raise CommandFault(f"{ids[0]} and {ids[1]} are in different spaces")
    space_key = found[0][3]
    l1, l2 = found[0][0], found[1][0]
    corner = paths.line_line(l1.start, l1.end, l2.start, l2.end)
    if corner is None:
        raise CommandFault(f"{ids[0]} and {ids[1]} are parallel; they make no corner to cut")
    keep = p.get("keep")
    u1, far1 = _kept_direction(l1, corner, keep[0] if keep else None, ids[0])
    u2, far2 = _kept_direction(l2, corner, keep[1] if keep else None, ids[1])
    cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    phi = math.degrees(math.acos(cos_t))  # the angle between the kept parts
    if phi < 1e-7 or phi > 180.0 - 1e-7:
        raise CommandFault(f"{ids[0]} and {ids[1]} run along one line; there is no corner")
    d1 = float(p["distance"])
    if "angle" in p and "distance2" in p:
        raise CommandFault("give distance2 or angle, not both")
    if "angle" in p:
        theta = abs(_degrees(p["angle"], "angle"))
        if not 0 < theta < 180.0 - phi:
            raise CommandFault(f"a chamfer at {theta:g}° from {ids[0]} never reaches {ids[1]} "
                               f"(the corner is {phi:.4f}°)",
                               hint=f"the angle must be between 0 and {180.0 - phi:.4f}°")
        d2 = d1 * math.sin(math.radians(theta)) / math.sin(math.radians(theta + phi))
    else:
        d2 = float(p.get("distance2", d1))
    if d1 <= 0 or d2 <= 0:
        raise CommandFault("chamfer distances must be positive",
                           hint="to meet the lines at a sharp corner, fillet them with radius 0")
    for eid, d, far in ((ids[0], d1, far1), (ids[1], d2, far2)):
        if d > far + 1e-9:
            raise CommandFault(f"{eid} runs only {far:.2f}' from the corner, less than the "
                               f"{d:.2f}' chamfer distance on it")
    t1 = [corner[0] + u1[0] * d1, corner[1] + u1[1] * d1]
    t2 = [corner[0] + u2[0] * d2, corner[1] + u2[1] * d2]
    modified = []
    if trim_lines:
        container = _container(doc, space_key)
        for eid, line, u, t in ((ids[0], l1, u1, t1), (ids[1], l2, u2, t2)):
            def along(q, u=u):
                return (q[0] - corner[0]) * u[0] + (q[1] - corner[1]) * u[1]
            if along(line.start) <= along(line.end):
                start, end = list(t), list(line.end)
            else:
                start, end = list(line.start), list(t)
            container[eid] = Line(id=line.id, **_props(line), start=start, end=end)
            modified.append(eid)
    if "layer" not in p and l1.layer in doc.layers:
        p = {**p, "layer": l1.layer}
    _, cut = _add(doc, space_key, "line", Line,
                  {**_entity_common(doc, p), "start": t1, "end": t2})
    length = geo.distance(t1, t2)
    return (f"chamfer {cut.id} between {ids[0]} and {ids[1]}: {d1:.2f}' and {d2:.2f}' back "
            f"from the corner {_fmt(corner)}, {length:.2f}' long, from {_fmt(t1)} to "
            f"{_fmt(t2)}", _diff(created=[cut.id], modified=modified), [])


# ----------------------------------------------------------------- lengthen


def lengthen(doc: Document, p: dict):
    eid = p["id"]
    space_key, entity = _own(doc, eid, "lengthen")
    if not isinstance(entity, (Line, Arc, Polyline)) or \
            (isinstance(entity, Polyline) and entity.closed):
        raise CommandFault(f"{eid} is a {'closed ' if getattr(entity, 'closed', False) else ''}"
                           f"{entity.TYPE}; lengthen changes the length of a line, an arc or an "
                           f"open polyline")
    path = _path_of(entity, eid)
    which = _which_end(path, p, eid)
    ways = [k for k in ("delta", "total", "percent", "to") if k in p]
    if len(ways) != 1:
        raise CommandFault("say how much with exactly one of delta, total, percent or to",
                           hint="delta: feet to add (negative shortens); total: the new length; "
                                "percent: the new length as a percentage of the old; to: a point "
                                "to run the end to")
    old = path.length
    if ways[0] == "delta":
        change = float(p["delta"])
    elif ways[0] == "total":
        change = float(p["total"]) - old
    elif ways[0] == "percent":
        change = old * float(p["percent"]) / 100.0 - old
    else:
        proj = path.project(p["to"])
        change = (proj.along - old) if which == "end" else -proj.along
    piece = path.pieces[-1] if which == "end" else path.pieces[0]
    if old + change <= 1e-9:
        raise CommandFault(f"{eid} is {old:.2f}' long; it cannot be shortened by "
                           f"{-change:.2f}'")
    if change < 0 and -change >= piece.length - 1e-9:
        raise CommandFault(f"shortening {eid} by {-change:.2f}' would take its whole "
                           f"{which} segment ({piece.length:.2f}')",
                           hint="break_entity or trim it instead")
    if isinstance(piece, paths.ArcSeg) and abs(piece.sweep) + math.degrees(
            change / piece.radius) >= 360.0:
        raise CommandFault(f"{eid} would come round on itself: an arc of radius "
                           f"{piece.radius:.2f}' holds at most {2 * math.pi * piece.radius:.2f}'")
    if which == "end":
        pieces = path.pieces[:-1] + [piece.cut(0.0, piece.length + change)]
    else:
        pieces = [piece.cut(-change, piece.length)] + path.pieces[1:]
    part = _rebuild(entity, pieces, eid)
    _restation(doc, part)
    _put(doc, space_key, part)
    new_end = pieces[-1].end if which == "end" else pieces[0].start
    verb = "lengthened" if change >= 0 else "shortened"
    return (f"{eid} {verb} {abs(change):.2f}' at its {which}, now {old + change:.2f}' long; "
            f"the {which} is at {_fmt(new_end)}", _diff(modified=[eid]), [])


# ------------------------------------------------------------- transforms


def _selection(doc: Document, ids: Sequence[str], verb: str, copy: bool):
    """``[(eid, space, entity, reference)]``: own entities, or reference
    elements when they are only being copied."""
    if len(set(ids)) != len(ids):
        raise CommandFault("ids lists an entity twice")
    out = []
    for eid in ids:
        entity, _owner, ref, space_key = _resolve(doc, eid)
        if ref is not None and not copy:
            raise CommandFault(
                f"{eid} is in reference {ref}, which this document can read but not {verb}",
                hint=f"{verb} a copy of it instead (copy: true / copy_entities), or change the "
                     f"basefile")
        out.append((eid, space_key, entity, ref))
    return out


def _place_copy(doc: Document, space_key: str, entity: Entity, ref, t: Similarity) -> Entity:
    copy = transform_entity(entity, t)
    copy.anchor = None  # a copy is drawn, not placed from the design
    if ref is not None and copy.layer not in doc.layers:
        copy.layer = doc.settings["current_layer"]
    if isinstance(copy, Point):
        copy.number = None  # numbered afresh below
    copy.id = doc.new_id(copy.TYPE)
    _container(doc, space_key)[copy.id] = copy
    return copy


def _renumber_points(doc: Document, made: List[Entity]) -> None:
    from roaddraft.commands.cogo_handlers import next_point_number
    for e in made:
        if isinstance(e, Point) and e.number is None:
            e.number = next_point_number(doc)


def _apply(doc: Document, p: dict, t_for, verb: str, copy: bool, count: int = 1):
    """Transform the selection in place, or make ``count`` copies (copy k
    through ``t_for(k)``). Returns ``(created, modified, warnings)``."""
    selection = _selection(doc, p["ids"], verb, copy)
    created: List[str] = []
    modified: List[str] = []
    warnings: List[str] = []
    if copy:
        made = []
        for k in range(1, count + 1):
            t = t_for(k)
            for eid, space_key, entity, ref in selection:
                made.append(_place_copy(doc, space_key, entity, ref, t))
        _renumber_points(doc, made)
        created = [e.id for e in made]
        return created, modified, warnings
    t = t_for(1)
    for eid, space_key, entity, _ref in selection:
        moved = transform_entity(entity, t)
        if abs(t.scale - 1.0) > 1e-12 and moved.annotative:
            moved.annotative = None
            warnings.append(f"{eid} was annotative; scaled, its size no longer follows the "
                            f"annotation scale")
        _put(doc, space_key, moved)
        modified.append(eid)
        if entity.anchor and entity.anchor.get("kind") in LINEWORK_ANCHORS \
                and not t.is_identity:
            warnings.append(f"{eid} is drawn from alignment {entity.anchor.get('alignment')}; "
                            f"it no longer lies on the design it is anchored to")
    return created, modified, warnings


def _two_points(p: dict, a: str, b: str):
    return [float(p[a][0]), float(p[a][1])], [float(p[b][0]), float(p[b][1])]


def copy_entities(doc: Document, p: dict):
    if ("delta" in p) == ("from" in p or "to" in p):
        raise CommandFault("give the displacement as delta [dx, dy], or as from and to (a base "
                           "point and where it goes)")
    if "delta" in p:
        dx, dy = float(p["delta"][0]), float(p["delta"][1])
    else:
        if "from" not in p or "to" not in p:
            raise CommandFault("from and to go together: the base point and where it goes")
        a, b = _two_points(p, "from", "to")
        dx, dy = b[0] - a[0], b[1] - a[1]
    count = int(p.get("count", 1))
    if count < 1:
        raise CommandFault("count must be at least 1")
    created, _m, warnings = _apply(
        doc, p, lambda k: Similarity.translation([dx * k, dy * k]), "copy", True, count)
    reach = math.hypot(dx, dy)
    return (f"copied {len(p['ids'])} entit{'y' if len(p['ids']) == 1 else 'ies'} "
            f"{count} time{'s' if count != 1 else ''} by [{dx:.2f}, {dy:.2f}] ({reach:.2f}' "
            f"{_bearing_text(dx, dy)}): {', '.join(created)}",
            _diff(created=created), warnings)


def _bearing_text(dx: float, dy: float) -> str:
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return ""
    return format_bearing(direction_to_azimuth(math.degrees(math.atan2(dy, dx))))


def _degrees(value, what: str) -> float:
    """Degrees from a number or DMS text (30, "30°15'00\"", '30-15-00')."""
    try:
        return cogo._angle(value, what)
    except cogo.CogoError as e:
        raise CommandFault(str(e), hint=e.hint)


def _direction(value, what: str) -> float:
    """A math heading from a quadrant bearing, an azimuth ('AZ 30'), or two
    points."""
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(
            isinstance(q, (list, tuple)) and len(q) == 2 for q in value):
        a, b = value
        if geo.distance(a, b) < 1e-12:
            raise CommandFault(f"{what}: the two points are the same")
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    if isinstance(value, str):
        text = value.strip()
        if text.upper().startswith("AZ"):
            return 90.0 - _degrees(text[2:].strip(" =:"), what)
        try:
            return 90.0 - cogo.parse_quadrant_bearing(text)
        except cogo.CogoError as e:
            raise CommandFault(f"{what}: {e}", hint=e.hint)
    raise CommandFault(f"{what} must be a bearing ('N 30°00'00\" E'), an azimuth ('AZ 30') or "
                       f"two points [[x1, y1], [x2, y2]]")


def _rotation_angle(p: dict) -> float:
    if ("angle" in p) == ("from_direction" in p or "to_direction" in p):
        raise CommandFault("give angle (degrees counter-clockwise), or from_direction and "
                           "to_direction (turn one direction onto another)")
    if "angle" in p:
        value = p["angle"]
        if isinstance(value, str):
            text = value.strip().upper()
            for suffix, sign in (("CCW", 1.0), ("CW", -1.0)):
                if text.endswith(suffix):
                    return sign * _degrees(text[:-len(suffix)].strip(), "angle")
        return _degrees(value, "angle")
    if "from_direction" not in p or "to_direction" not in p:
        raise CommandFault("from_direction and to_direction go together")
    turn = _direction(p["to_direction"], "to_direction") - \
        _direction(p["from_direction"], "from_direction")
    return (turn + 180.0) % 360.0 - 180.0


def rotate_entities(doc: Document, p: dict):
    angle = _rotation_angle(p)
    base = [float(p["base"][0]), float(p["base"][1])]
    copy = bool(p.get("copy", False))
    created, modified, warnings = _apply(
        doc, p, lambda k: Similarity.rotation(base, angle * k), "rotate", copy)
    turn = f"{abs(angle):.6g}° {'counter-clockwise' if angle >= 0 else 'clockwise'}"
    if copy:
        return (f"rotated copies {', '.join(created)} {turn} about {_fmt(base)}",
                _diff(created=created), warnings)
    return (f"rotated {', '.join(modified)} {turn} about {_fmt(base)}",
            _diff(modified=modified), warnings)


def mirror_entities(doc: Document, p: dict):
    line = p["line"]
    a, b = [float(v) for v in line[0]], [float(v) for v in line[1]]
    if geo.distance(a, b) < 1e-12:
        raise CommandFault("the mirror line needs two different points")
    keep = bool(p.get("keep_original", True))
    created, modified, warnings = _apply(doc, p, lambda k: Similarity.reflection(a, b),
                                         "mirror", keep)
    axis = _bearing_text(b[0] - a[0], b[1] - a[1])
    if keep:
        return (f"mirrored copies {', '.join(created)} across the line through {_fmt(a)} and "
                f"{_fmt(b)} ({axis}); text still reads left to right",
                _diff(created=created), warnings)
    return (f"mirrored {', '.join(modified)} across the line through {_fmt(a)} and {_fmt(b)} "
            f"({axis})", _diff(modified=modified), warnings)


def scale_entities(doc: Document, p: dict):
    base = [float(p["base"][0]), float(p["base"][1])]
    ways = ["factor" in p, "from_length" in p or "to_length" in p]
    if sum(ways) != 1:
        raise CommandFault("give factor, or from_length and to_length (scale so a length "
                           "becomes another)")
    if "factor" in p:
        factor = float(p["factor"])
    else:
        if "from_length" not in p or "to_length" not in p:
            raise CommandFault("from_length and to_length go together")
        factor = float(p["to_length"]) / float(p["from_length"])
    if factor <= 0:
        raise CommandFault("the scale factor must be positive",
                           hint="to turn the drawing over, mirror_entities it")
    copy = bool(p.get("copy", False))
    created, modified, warnings = _apply(
        doc, p, lambda k: Similarity.scaling(base, factor), "scale", copy)
    ids = created or modified
    return (f"scaled {'copies ' if copy else ''}{', '.join(ids)} by {factor:.6g} about "
            f"{_fmt(base)}", _diff(created=created, modified=modified), warnings)


# -------------------------------------------------------------------- array


def selection_base(doc: Document, entities: Sequence[Entity]):
    """Where a selection sits: a lone point, block or text's own insertion,
    else the middle of the selection's box."""
    if len(entities) == 1 and isinstance(entities[0], (Point, BlockRef, Text)):
        return list(entities[0].position)
    bb = None
    for e in entities:
        bb = geo.bbox_union(bb, e.bbox(doc))
    if bb is None:
        raise CommandFault("the selection has no extent to place")
    return [(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0]


def array_entities(doc: Document, p: dict):
    kind = p.get("kind", "rectangular")
    selection = _selection(doc, p["ids"], "array", True)
    entities = [e for _eid, _sk, e, _ref in selection]
    transforms: List[Similarity] = []
    if kind == "rectangular":
        rows, cols = int(p.get("rows", 1)), int(p.get("columns", 1))
        if rows < 1 or cols < 1 or rows * cols < 2:
            raise CommandFault("a rectangular array needs at least two items (rows x columns)")
        if rows > 1 and "row_spacing" not in p or cols > 1 and "column_spacing" not in p:
            raise CommandFault("give row_spacing for several rows and column_spacing for "
                               "several columns (negative goes down / left)")
        dr, dc = float(p.get("row_spacing", 0.0)), float(p.get("column_spacing", 0.0))
        angle = float(p.get("angle", 0.0))
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue
                d = geo.rotate_point([c * dc, r * dr], angle)
                transforms.append(Similarity.translation(d))
        what = f"{rows} x {cols} rectangular array"
    elif kind == "polar":
        if "center" not in p or "count" not in p:
            raise CommandFault("a polar array needs center and count")
        count = int(p["count"])
        if count < 2:
            raise CommandFault("count must be at least 2 (the original is the first)")
        fill = float(p.get("fill_angle", 360.0))
        full = abs(abs(fill) - 360.0) < 1e-9
        step = fill / (count if full else count - 1)
        center = [float(p["center"][0]), float(p["center"][1])]
        rotate_items = bool(p.get("rotate_items", True))
        base = selection_base(doc, entities)
        for k in range(1, count):
            if rotate_items:
                transforms.append(Similarity.rotation(center, step * k))
            else:
                q = geo.rotate_point(base, step * k, center)
                transforms.append(Similarity.translation([q[0] - base[0], q[1] - base[1]]))
        what = f"polar array of {count} about {_fmt(center)} over {fill:g}°"
    elif kind == "path":
        from roaddraft.commands.cogo_handlers import sample_path
        positions, described = sample_path(doc, p)
        base = [float(v) for v in p["base_point"]] if "base_point" in p \
            else selection_base(doc, entities)
        align = bool(p.get("align_items", True))
        for pos in positions:
            t = Similarity.rotation(base, pos["heading"]) if align else Similarity()
            moved = t.apply(base)
            transforms.append(t.then_translate([pos["point"][0] - moved[0],
                                                pos["point"][1] - moved[1]]))
        what = f"{len(positions)} copies along {described}"
    else:
        raise CommandFault(f"kind must be rectangular, polar or path, got {kind!r}")
    if not transforms:
        raise CommandFault("the array has no positions to fill")
    if len(transforms) * len(entities) > 5000:
        raise CommandFault(f"{len(transforms)} copies of {len(entities)} entities is too many "
                           f"for one command", hint="space them wider or array fewer at once")
    made = []
    for t in transforms:
        for eid, space_key, entity, ref in selection:
            made.append(_place_copy(doc, space_key, entity, ref, t))
    _renumber_points(doc, made)
    created = [e.id for e in made]
    shown = ", ".join(created) if len(created) <= 16 else \
        f"{', '.join(created[:8])} ... {', '.join(created[-4:])}"
    return (f"{what}: {len(created)} entities created ({shown})", _diff(created=created), [])


__all__ = ["trim", "extend", "break_entity", "join_entities", "explode_entities", "chamfer",
           "lengthen", "copy_entities", "rotate_entities", "mirror_entities",
           "scale_entities", "array_entities", "selection_base"]
