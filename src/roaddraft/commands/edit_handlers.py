"""Drafting tools that work from linework already drawn, or from a survey call:

* ``draw_traverse`` -- lines and curves by bearing and distance (COGO), the
  way a deed, a field book or a design report gives them;
* ``offset_entity`` -- a parallel copy of a line, polyline, arc or circle, or
  of a chain of them (AutoCAD OFFSET, MicroStation Copy Parallel);
* ``fillet`` -- the curve between two lines, trimming them back to it
  (AutoCAD FILLET, MicroStation Construct Circular Fillet).

Each returns ``(message, diff, warnings)`` and raises ``CommandFault`` with a
hint, like every handler: the bus makes it atomic, journaled and undoable.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from roaddraft.commands.handlers import (
    CommandFault, _add, _diff, _entity_common, _space, _space_label,
)
from roaddraft.design import cogo
from roaddraft.design.angles import format_dms
from roaddraft.document import paths
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Circle, Line, Polyline

COMPASS = ("north", "northeast", "east", "southeast", "south", "southwest", "west",
           "northwest")


def _cogo_fault(e: cogo.CogoError) -> CommandFault:
    return CommandFault(str(e), hint=e.hint)


def _path_fault(e: paths.PathError) -> CommandFault:
    return CommandFault(str(e), hint=e.hint)


def _fmt(p) -> str:
    return f"[{p[0]:.2f}, {p[1]:.2f}]"


def compass_side(heading_deg: float) -> str:
    """The compass word for a math heading (degrees CCW from +X)."""
    azimuth = (90.0 - heading_deg) % 360.0
    return COMPASS[int(((azimuth + 22.5) % 360.0) // 45.0)]


def _resolve(doc: Document, eid: str):
    """``(entity, owner, reference name or None, space)`` or a fault."""
    from roaddraft.document.locate import resolve_entity
    found = resolve_entity(doc, eid)
    if found is None:
        raise CommandFault(f"entity {eid!r} not found",
                           hint="find_entities, hit_test and snap return ids; elements of "
                                "an attached reference are 'REFNAME:ID'")
    return found


# ---------------------------------------------------------------- traverse


def traverse_start(doc: Document, p: dict):
    """``(start point, direction to continue from, what it is)`` for a
    traverse: ``start`` is a point, or an entity whose end it continues from
    (``start_at`` = end, the default, or start)."""
    from roaddraft.document.locate import point_at
    start = p["start"]
    initial = cogo.initial_azimuth_of(p)
    if isinstance(start, (list, tuple)):
        if len(start) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                      for v in start):
            raise CommandFault(f"start must be a point [x, y] or an entity id, got {start!r}")
        if "start_at" in p:
            raise CommandFault("start_at goes with a start entity, not a point")
        return [float(start[0]), float(start[1])], initial, _fmt(start)
    if not isinstance(start, str) or not start:
        raise CommandFault(f"start must be a point [x, y] or an entity id, got {start!r}")
    entity, owner, _ref, _space_key = _resolve(doc, start)
    where = p.get("start_at", "end")
    if where not in ("start", "end"):
        raise CommandFault(f"start_at must be start or end, got {where!r}")
    try:
        point, heading = point_at(owner, entity, where)
    except ValueError as ex:
        raise CommandFault(str(ex))
    if heading is not None and initial is None:
        if where == "start":  # walking away from the entity, back past its start
            heading += 180.0
        initial = (90.0 - heading) % 360.0
    return list(point), initial, f"the {where} of {start} {_fmt(point)}"


def compute_traverse(doc: Document, p: dict) -> Tuple[cogo.Traverse, str]:
    start, initial, described = traverse_start(doc, p)
    try:
        legs = [cogo.as_leg(leg, f"legs[{i}]") for i, leg in enumerate(p["legs"])]
        return cogo.run_traverse(start, legs, initial, close=bool(p.get("close"))), described
    except cogo.CogoError as e:
        raise _cogo_fault(e)


def closure_text(traverse: cogo.Traverse) -> str:
    m = traverse.misclosure()
    if m["distance"] <= 1e-6:
        return "closes on its start"
    return (f"misses its start by {m['distance']:.3f}' ({m['bearing']}), precision "
            f"{m['precision_text']}")


def draw_traverse(doc: Document, p: dict):
    space_key, _container = _space(doc, p["space"])
    common = _entity_common(doc, p)
    traverse, described = compute_traverse(doc, p)
    courses = list(traverse.courses)
    closing = traverse.closing
    created: List[str] = []
    lines: List[str] = []
    if p.get("polyline"):
        curves = [c for c in courses if c.kind == "curve"]
        if curves:
            raise CommandFault("a polyline holds straight courses only, and this traverse "
                               "has curves",
                               hint="leave polyline off to draw lines and arcs")
        vertices = [list(traverse.start)] + [list(c.end) for c in courses]
        closed = bool(p.get("close"))
        if closed and closing is None:
            vertices.pop()  # it closes exactly: the last vertex is the first
        if len(vertices) < 2:
            raise CommandFault("a polyline needs at least two vertices")
        _, pl = _add(doc, space_key, "polyline", Polyline,
                     {**common, "vertices": vertices, "closed": closed})
        created.append(pl.id)
        lines = [c.describe() for c in courses] + ([f"{closing.describe()} (closing)"]
                                                    if closing else [])
        drawn = f"polyline {pl.id}"
    else:
        for course in courses + ([closing] if closing else []):
            if course.kind == "line":
                _, e = _add(doc, space_key, "line", Line,
                            {**common, "start": list(course.start), "end": list(course.end)})
            else:
                a0, a1 = course.arc_angles()
                _, e = _add(doc, space_key, "arc", Arc,
                            {**common, "center": list(course.center), "radius": course.radius,
                             "start_angle_deg": a0, "end_angle_deg": a1})
            created.append(e.id)
            note = " (closing)" if course is closing else ""
            lines.append(f"{e.id} {course.describe()}{note}")
        drawn = f"{len(created)} entities"
    end = traverse.end
    message = (f"traverse from {described} in {_space_label(doc, space_key)}: "
               + "; ".join(lines) + f"; ends at {_fmt(end)}")
    m = traverse.misclosure()
    if p.get("close") or m["distance"] <= cogo.CLOSURE_REPORT_FT:
        message += f"; {closure_text(traverse)}"
    warnings = []
    if space_key != "model":
        warnings.append(f"drawn on {_space_label(doc, space_key)}, where distances are paper "
                        f"inches; a survey traverse belongs in model space (feet)")
    return f"{message} ({drawn})", _diff(created=created), warnings


# ------------------------------------------------------------------ offset


def _offset_distances(path: paths.Path, p: dict) -> List[float]:
    """Signed offsets (right of the path's direction positive) from whichever
    way they were asked for."""
    from roaddraft.design.anchors import parse_offset
    from roaddraft.design.errors import DesignError
    ways = [k for k in ("offsets", "through", "distance") if k in p]
    if len(ways) != 1:
        raise CommandFault(
            "say how far with exactly one of distance (with side or toward), through, or "
            "offsets",
            hint="distance: 15 with side: 'left' (of the direction it runs) or toward: a "
                 "point on the side to offset to; through: a point the parallel passes "
                 "through; offsets: [-15, 15] or ['15L', '15R'] for several at once")
    if ways[0] != "distance":
        for key in ("side", "toward"):
            if key in p:
                raise CommandFault(f"{key} goes with distance, not {ways[0]}")
    if ways[0] == "offsets":
        out = []
        for value in p["offsets"]:
            try:
                d = parse_offset(value)
            except DesignError as e:
                raise CommandFault(str(e), hint=e.hint)
            if d == 0:
                raise CommandFault("an offset of 0 is the entity itself",
                                   hint="right of the direction it runs is positive: 15 or "
                                        "'15R'; left is -15 or '15L'")
            out.append(d)
        return out
    if ways[0] == "through":
        proj = path.project(p["through"])
        if abs(proj.offset) < 1e-9:
            raise CommandFault(f"{_fmt(p['through'])} is on the linework itself, so the "
                               f"parallel through it is the same line")
        return [proj.offset]
    distance = float(p["distance"])
    if distance <= 0:
        raise CommandFault(f"distance must be positive, got {distance:g}",
                           hint="give the side with side (left/right) or toward (a point)")
    if ("side" in p) == ("toward" in p):
        raise CommandFault("with distance, give exactly one of side (left/right of the "
                           "direction it runs) or toward (a point on the side to offset to)")
    if "side" in p:
        side = str(p["side"]).lower()
        if side not in ("left", "right"):
            raise CommandFault(f"side must be left or right, got {p['side']!r}")
        return [distance if side == "right" else -distance]
    proj = path.project(p["toward"])
    if abs(proj.offset) < 1e-9:
        raise CommandFault(f"toward {_fmt(p['toward'])} is on the linework, so it names "
                           f"neither side",
                           hint="pick a point off to the side the copy should go")
    return [math.copysign(distance, proj.offset)]


def _signed_area(points) -> float:
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))


def _describe_side(path: paths.Path, d: float) -> str:
    """Where an offset went, in words a reader checks against the plan."""
    side = "right" if d > 0 else "left"
    if path.closed:
        pts = []
        for piece in path.pieces:
            pts += [piece.point_at(piece.length * k / 8.0) for k in range(8)]
        ccw = _signed_area(pts) > 0
        # travelling counter-clockwise, the right hand is outside
        inside = (d > 0) != ccw
        return f"{abs(d):.2f}' {'inside' if inside else 'outside'}"
    heading = path.dir_at(path.length / 2.0)
    normal = heading - 90.0 if d > 0 else heading + 90.0
    return f"{abs(d):.2f}' {side} ({compass_side(normal)} side)"


def _entities_for(doc: Document, space_key: str, path: paths.Path, groups, sources,
                  fields: dict) -> List[str]:
    """Draw the parallel: a polyline's copy is one polyline (its arcs and any
    round joins as bulges); every other piece becomes a line or an arc."""
    created: List[str] = []
    by_source = {}
    for i, group in enumerate(groups):
        if group:  # a piece too short for the distance leaves an empty group
            by_source.setdefault(path.owners[i], []).append(group)
    for index in sorted(by_source):
        source = sources[index]
        pieces = [piece for group in by_source[index] for piece in group]
        if isinstance(source, Polyline):
            closed = bool(path.closed and len(sources) == 1)
            _, e = _add(doc, space_key, "polyline", Polyline,
                        {**fields, **paths.polyline_fields_of(pieces, closed)})
            created.append(e.id)
            continue
        for piece in pieces:
            created.append(_draw_piece(doc, space_key, piece, fields))
    return created


def _draw_piece(doc: Document, space_key: str, piece, fields: dict) -> str:
    cls, geometry = paths.entity_fields_of(piece)
    kind = {Line: "line", Arc: "arc", Circle: "circle"}[cls]
    _, e = _add(doc, space_key, kind, cls, {**fields, **geometry})
    return e.id


def offset_entity(doc: Document, p: dict):
    ids = list(p["ids"])
    if len(set(ids)) != len(ids):
        raise CommandFault("ids lists an entity twice")
    found = [_resolve(doc, eid) for eid in ids]
    spaces = {space for _e, _o, _r, space in found}
    if len(spaces) > 1:
        raise CommandFault("the entities are in different spaces",
                           hint="offset what is drawn in one space at a time")
    space_key = spaces.pop()
    entities = []
    for eid, (entity, _owner, _ref, _space) in zip(ids, found):
        if not isinstance(entity, paths.PATH_ENTITY_TYPES):
            raise CommandFault(
                f"{eid} is a {entity.TYPE}; offset makes a parallel of a line, polyline, "
                f"arc or circle",
                hint="move_entities copies nothing; to shift text or a block, move it")
        entities.append(entity)
    try:
        if len(entities) == 1:
            path = paths.Path.of_entity(entities[0])
        else:
            path = paths.Path.of_chain(entities,
                                       float(p.get("connect_tolerance", paths.CHAIN_TOL)))
    except paths.PathError as e:
        raise _path_fault(e)
    distances = _offset_distances(path, p)
    join = p.get("join", "sharp")

    # the copy's layer: given, else the source's (a reference's layer only when
    # the host has one by that name), else the current layer
    first_entity, _owner, ref, _space = found[0]
    if "layer" not in p and (ref is None or first_entity.layer in doc.layers):
        p = {**p, "layer": first_entity.layer}
    fields = _entity_common(doc, p)
    if ref is None:
        if "color" not in p and first_entity.color is not None:
            fields["color"] = first_entity.color
        if "linetype" not in p and first_entity.linetype is not None:
            fields["linetype"] = first_entity.linetype

    created: List[str] = []
    parts: List[str] = []
    warnings: List[str] = []
    for d in distances:
        try:
            groups, notes = path.offset_groups(d, join)
        except paths.PathError as e:
            raise _path_fault(e)
        made = _entities_for(doc, space_key, path, groups, entities, fields)
        created += made
        parts.append(f"{_describe_side(path, d)}: {', '.join(made)}")
        warnings += notes
    anchored = [eid for eid, e in zip(ids, entities)
                if e.anchor and e.anchor.get("alignment")]
    if anchored:
        alignment = entities[ids.index(anchored[0])].anchor["alignment"]
        warnings.append(f"{', '.join(anchored)} belong to alignment {alignment}; these copies "
                        f"are plain linework with no anchor. draw_offset draws offsets that "
                        f"stay tied to the design")
    what = ids[0] if len(ids) == 1 else f"the chain {' > '.join(ids)}"
    return (f"offset {what} on layer {fields['layer']!r}: " + "; ".join(parts),
            _diff(created=created), warnings)


# ------------------------------------------------------------------ fillet


def _kept_direction(line: Line, corner, keep, eid: str):
    """Unit direction from the corner along the part of the line to keep, and
    how far the line runs that way."""
    dx, dy = line.end[0] - line.start[0], line.end[1] - line.start[1]
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        raise CommandFault(f"{eid} has no length")
    ux, uy = dx / length, dy / length

    def along(q):  # distance from the corner in the line's own direction
        return (q[0] - corner[0]) * ux + (q[1] - corner[1]) * uy

    sa, sb = along(line.start), along(line.end)
    if keep is not None:
        s = along(keep)
        if abs(s) < 1e-9 * max(1.0, length):
            raise CommandFault(f"the keep point for {eid} is at the corner, so it names "
                               f"neither part of the line",
                               hint="pick a point along the part of the line to keep")
        sign = 1.0 if s > 0 else -1.0
    else:  # keep the end farther from the corner
        sign = 1.0 if (sa if abs(sa) > abs(sb) else sb) > 0 else -1.0
    return (ux * sign, uy * sign), max(sa * sign, sb * sign)


def fillet(doc: Document, p: dict):
    ids = list(p["ids"])
    if len(ids) != 2 or ids[0] == ids[1]:
        raise CommandFault("fillet joins two different lines: ids takes exactly two")
    radius = float(p["radius"])
    if radius < 0:
        raise CommandFault(f"radius must be zero or positive, got {radius:g}",
                           hint="radius 0 extends or trims the two lines to a sharp corner")
    trim = bool(p.get("trim", True))
    found = [_resolve(doc, eid) for eid in ids]
    for eid, (entity, _owner, ref, _space) in zip(ids, found):
        if not isinstance(entity, Line):
            raise CommandFault(f"{eid} is a {entity.TYPE}; fillet joins two lines",
                               hint="a polyline's corners and arcs are not filleted yet: "
                                    "draw the curve with draw_arc, or explode the polyline "
                                    "into lines first")
        if ref is not None and trim:
            raise CommandFault(f"{eid} is in reference {ref}, which this document cannot "
                               f"trim",
                               hint="pass trim: false to draw only the curve, or fillet "
                                    "the lines in the basefile")
    if found[0][3] != found[1][3]:
        raise CommandFault(f"{ids[0]} and {ids[1]} are in different spaces")
    space_key = found[0][3]
    l1, l2 = found[0][0], found[1][0]
    corner = paths.line_line(l1.start, l1.end, l2.start, l2.end)
    if corner is None:
        raise CommandFault(f"{ids[0]} and {ids[1]} are parallel, so no curve is tangent to "
                           f"both at a corner",
                           hint="a fillet needs two lines that meet, or would meet if "
                                "extended")
    keep = p.get("keep")
    if keep is not None and len(keep) != 2:
        raise CommandFault("keep takes two points, one on each line, in the order of ids")
    u1, far1 = _kept_direction(l1, corner, keep[0] if keep else None, ids[0])
    u2, far2 = _kept_direction(l2, corner, keep[1] if keep else None, ids[1])
    for eid, far in ((ids[0], far1), (ids[1], far2)):
        if far <= 1e-9:
            raise CommandFault(f"{eid} does not run away from the corner on the side kept",
                               hint="pass keep: a point on the part of each line to keep")
    cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    theta = math.degrees(math.acos(cos_t))  # the angle between the kept parts
    if theta < 1e-7 or theta > 180.0 - 1e-7:
        raise CommandFault(f"{ids[0]} and {ids[1]} run along one line; there is no corner "
                           f"to round")
    half = math.radians(theta) / 2.0
    tangent = radius / math.tan(half) if radius > 0 else 0.0
    if tangent > min(far1, far2) + 1e-9:
        biggest = min(far1, far2) * math.tan(half)
        raise CommandFault(
            f"a {radius:g}' radius needs {tangent:.2f}' of each line back from the corner, "
            f"and {ids[0] if far1 < far2 else ids[1]} has only {min(far1, far2):.2f}'",
            hint=f"the largest radius that fits is "
                 f"{math.floor(biggest * 100 + 1e-6) / 100:.2f}'")
    t1 = [corner[0] + u1[0] * tangent, corner[1] + u1[1] * tangent]
    t2 = [corner[0] + u2[0] * tangent, corner[1] + u2[1] * tangent]

    modified: List[str] = []
    if trim:
        for eid, line, u, t in ((ids[0], l1, u1, t1), (ids[1], l2, u2, t2)):
            def along(q, u=u):
                return (q[0] - corner[0]) * u[0] + (q[1] - corner[1]) * u[1]
            # the end nearer the corner (or past it) moves to the tangent point
            if along(line.start) <= along(line.end):
                new_start, new_end = list(t), list(line.end)
            else:
                new_start, new_end = list(line.start), list(t)
            _key, container = doc.resolve_space(space_key)
            container[eid] = Line(id=line.id, layer=line.layer, color=line.color,
                                  linetype=line.linetype,
                                  anchor=dict(line.anchor) if line.anchor else None,
                                  annotative=line.annotative, start=new_start, end=new_end)
            from roaddraft.commands.modify_handlers import _restation
            _restation(doc, container[eid])  # an edge cut back starts at a new station
            modified.append(eid)

    created: List[str] = []
    delta = 180.0 - theta
    if radius > 0:
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        norm = math.hypot(*bis)
        reach = radius / math.sin(half)
        center = [corner[0] + bis[0] / norm * reach, corner[1] + bis[1] / norm * reach]
        a1 = math.degrees(math.atan2(t1[1] - center[1], t1[0] - center[0]))
        a2 = math.degrees(math.atan2(t2[1] - center[1], t2[0] - center[0]))
        ccw = (a2 - a1) % 360.0
        start, end = (a1, a1 + ccw) if ccw <= 180.0 else (a2, a2 + (360.0 - ccw))
        if "layer" not in p:
            p = {**p, "layer": l1.layer if l1.layer in doc.layers else None}
            if p["layer"] is None:
                p.pop("layer")
        fields = _entity_common(doc, p)
        _, arc = _add(doc, space_key, "arc", Arc,
                      {**fields, "center": center, "radius": radius,
                       "start_angle_deg": start, "end_angle_deg": end})
        created.append(arc.id)
        length = radius * math.radians(delta)
        message = (f"fillet {arc.id} R={radius:.2f}' between {ids[0]} and {ids[1]}: tangent "
                   f"points {_fmt(t1)} and {_fmt(t2)}, Δ={format_dms(delta)}, "
                   f"T={tangent:.2f}', L={length:.2f}', corner (PI) {_fmt(corner)}")
    else:
        message = f"{ids[0]} and {ids[1]} meet at {_fmt(corner)}"
    if not trim:
        message += " (lines left as they were)"
    return message, _diff(created=created, modified=modified), []


__all__ = ["draw_traverse", "offset_entity", "fillet", "compute_traverse", "closure_text",
           "traverse_start", "compass_side"]
