"""place_dimension: measure the drawing and say so on it.

Dimensioning is the one annotation whose text has to keep agreeing with the
geometry, so the command's job is to pin the measurement to real points.
Pass the points if you have them, or name the entities and let the engine
find them -- ``of_entity`` dimensions a line end to end or reads a curve's
centre and radius, ``from_entity``/``to_entity`` measure between two, and two
lines given to an angular dimension are intersected for the vertex. What
lands in the document is a Dimension entity that stores the measurement, not
its linework (see ``document.dimgeom``).

``line_point`` is the one thing the engine cannot guess: it is where the
drafter drags the dimension line to, and it also says *which* measurement was
meant -- above or below a pair of points is a horizontal dimension, out to
the side is a vertical one, and for an angular dimension it picks which of
the four angles between two rays is being called out.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from roaddraft.commands.handlers import (
    CommandFault, _add, _annotation_warnings, _diff, _entity_common, _space,
    _space_label, _style,
)
from roaddraft.core import geometry as geo
from roaddraft.design.angles import direction_of
from roaddraft.design.labels import SHEET_TEXT_HEIGHT
from roaddraft.document import annotation as anno
from roaddraft.document import dimgeom
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Circle, Dimension, Line, Polyline
from roaddraft.document.locate import point_at, resolve_entity

EPS = 1e-9

#: Params that pass straight through to the entity when given.
PASS_THROUGH = ("rotation_deg", "suffix", "precision", "arrow", "arrow_size",
                "text_gap", "extension_offset", "extension_beyond", "measure_scale")


def place_dimension(doc: Document, p: dict):
    space_key, _container = _space(doc, p["space"])
    kind = p["kind"]
    line_point = _point(p, "line_point")
    geometry = _resolve_geometry(doc, space_key, kind, p, line_point)

    height = float(p.get("text_height", _default_height(doc, space_key)))
    if height <= 0:
        raise CommandFault(f"text_height must be positive, got {height}")
    scale = float(p.get("measure_scale", 1.0))
    fields = {
        **_entity_common(doc, p),
        "kind": kind,
        "line_point": line_point,
        "text_height": height,
        "style": _style(doc, p.get("style", doc.settings["current_text_style"])),
        "unit_format": p.get("unit_format",
                             "feet" if space_key == "model" or scale != 1.0
                             else "decimal"),
        "annotative": anno.text_record(doc, height) if space_key == "model" else None,
        **geometry,
        **{key: p[key] for key in PASS_THROUGH if key in p},
    }
    if "text" in p:
        fields["text_override"] = str(p["text"])
    if "prefix" in p:
        fields["prefix"] = str(p["prefix"])
    twist = float(p.get("view_rotation") or 0.0)
    if twist and space_key == "model":
        fields["view_rotation"] = twist

    _, dim = _add(doc, p["space"], "dimension", Dimension, fields)
    _check_measurement(dim, p)

    warnings: List[str] = []
    if twist and space_key != "model":
        warnings.append(
            f"view_rotation {twist:g} was not used: {dim.id} is on the sheet itself, where "
            f"its text already reads upright; it is for a model dimension read through a "
            f"twisted viewport")
    if not dimgeom.fits(dim, doc):
        warnings.append(
            f"{dim.id} is too short for its text: the text needs "
            f"{dimgeom.text_width(dim, doc, dimgeom.text_of(dim)):.2f} plus arrowheads "
            f"across a {dimgeom.span(dim):.2f} span, so both are drawn outside the "
            f"extension lines")
    warnings += _annotation_warnings(doc, space_key, dim)
    return (f"{kind} dimension {dim.id} ({dimgeom.text_of(dim)!r}) placed in "
            f"{_space_label(doc, space_key)}{_how(dim, p)}",
            _diff(created=[dim.id]), warnings)


def _how(dim: Dimension, p: dict) -> str:
    """The part of the measurement the caller left to the engine."""
    if dim.kind != "linear" or "rotation_deg" in p:
        return ""
    return (", measured horizontally" if dimgeom.direction_deg(dim) == 0.0
            else ", measured vertically")


def _default_height(doc: Document, space_key: str) -> float:
    if space_key != "model":
        return SHEET_TEXT_HEIGHT
    return anno.size_defaults(doc)["text_height"]


# --------------------------------------------------------------- geometry


def _resolve_geometry(doc, space_key, kind, p, line_point) -> dict:
    """The measured geometry for ``kind``: from points, or from the entities
    the caller named."""
    if kind in ("linear", "aligned"):
        p1, p2 = _two_points(doc, space_key, kind, p)
        return {"p1": p1, "p2": p2}
    if kind == "angular":
        return _angular_geometry(doc, space_key, p, line_point)
    return _circular_geometry(doc, space_key, kind, p, line_point)


def _two_points(doc, space_key, kind, p) -> Tuple[list, list]:
    if "of_entity" in p:
        entity, owner = _target(doc, space_key, p["of_entity"], "of_entity")
        p1, _ = point_at(owner, entity, "start")
        p2, _ = point_at(owner, entity, "end")
        if geo.distance(p1, p2) <= EPS:
            raise CommandFault(
                f"{p['of_entity']} ({entity.TYPE}) has no two ends to measure between",
                hint="of_entity dimensions a line, polyline or arc end to end; for "
                     "anything else give p1 and p2, or from_entity and to_entity")
        return p1, p2
    p1 = _end_point(doc, space_key, p, "from_entity", "from_at", "p1")
    p2 = _end_point(doc, space_key, p, "to_entity", "to_at", "p2")
    if p1 is None or p2 is None:
        raise CommandFault(
            f"a {kind} dimension measures between two points",
            hint="give p1 and p2, or from_entity/to_entity (with from_at/to_at: "
                 "start|mid|end or a fraction), or of_entity to measure one entity "
                 "end to end")
    return p1, p2


def _angular_geometry(doc, space_key, p, line_point) -> dict:
    if "from_entity" in p and "to_entity" in p and "center" not in p:
        a, a_owner = _target(doc, space_key, p["from_entity"], "from_entity")
        b, b_owner = _target(doc, space_key, p["to_entity"], "to_entity")
        return _angle_between_lines(a, a_owner, b, b_owner, p, line_point)
    center = _end_point(doc, space_key, p, None, None, "center")
    p1 = _end_point(doc, space_key, p, "from_entity", "from_at", "p1")
    p2 = _end_point(doc, space_key, p, "to_entity", "to_at", "p2")
    if center is None or p1 is None or p2 is None:
        raise CommandFault(
            "an angular dimension measures the angle at a vertex between two rays",
            hint="give center (the vertex) with p1 and p2 (a point out along each "
                 "ray), or from_entity and to_entity as two lines, whose "
                 "intersection is the vertex")
    if geo.distance(center, p1) <= EPS or geo.distance(center, p2) <= EPS:
        raise CommandFault("p1 and p2 must be away from the vertex to define a ray",
                           hint="they are points out along each side of the angle, "
                                "not the vertex itself")
    return {"center": center, "p1": p1, "p2": p2}


def _angle_between_lines(a, a_owner, b, b_owner, p, line_point) -> dict:
    """DIMANGULAR's two-line mode: the vertex is where the lines cross.

    Two crossing lines make four angles. Each line contributes the end that
    lies nearest the way ``line_point`` was dragged, so dragging into any of
    the four picks that one -- which is what selecting a side of each line
    does in AutoCAD."""
    a_ends = _line_ends(a, a_owner, p["from_entity"])
    b_ends = _line_ends(b, b_owner, p["to_entity"])
    vertex = geo.line_intersection(a_ends[0], a_ends[1], b_ends[0], b_ends[1])
    if vertex is None:
        raise CommandFault(
            f"{p['from_entity']} and {p['to_entity']} are parallel, so there is no "
            f"vertex to measure an angle at",
            hint="give center, p1 and p2 to state the vertex and rays yourself")
    if geo.distance(vertex, line_point) <= EPS:
        raise CommandFault(
            "line_point is the vertex itself, so it cannot say which of the four "
            "angles is meant",
            hint="drag line_point out into the angle you want to call out")
    toward = direction_of(vertex, line_point)
    a_rays = _rays(a_ends, vertex, p["from_entity"])
    b_rays = _rays(b_ends, vertex, p["to_entity"])
    # The four wedges tile the plane around the vertex and exactly one holds the
    # drag; it is the only non-reflex one, so the smallest wins.
    _sweep, p1, p2 = min((_wedge(vertex, qa, qb, toward), qa, qb)
                         for qa in a_rays for qb in b_rays)
    return {"center": vertex, "p1": p1, "p2": p2}


def _rays(ends, vertex, eid) -> list:
    usable = [q for q in ends if geo.distance(vertex, q) > EPS]
    if not usable:
        raise CommandFault(f"{eid} ends at the vertex, leaving no ray to measure from",
                           hint="give center, p1 and p2 to state the rays yourself")
    return usable


def _wedge(vertex, qa, qb, toward: float) -> float:
    """The sweep from ``qa`` to ``qb`` that contains the drag direction."""
    a = direction_of(vertex, qa)
    ccw = (direction_of(vertex, qb) - a) % 360.0
    return ccw if (toward - a) % 360.0 <= ccw else 360.0 - ccw


def _line_ends(entity, owner, eid) -> Tuple[list, list]:
    if not isinstance(entity, (Line, Polyline)):
        raise CommandFault(
            f"{eid} is a {entity.TYPE}; an angle between entities is measured "
            f"between two straight lines",
            hint="give center, p1 and p2 to measure an angle at a vertex you name")
    start, _ = point_at(owner, entity, "start")
    end, _ = point_at(owner, entity, "end")
    return start, end


def _circular_geometry(doc, space_key, kind, p, line_point) -> dict:
    """Centre, radius and the point(s) on the circle for radius / diameter /
    arc_length -- read off an arc or circle when one is named."""
    entity = None
    if "of_entity" in p:
        entity, owner = _target(doc, space_key, p["of_entity"], "of_entity")
        if not isinstance(entity, (Arc, Circle)):
            raise CommandFault(
                f"{p['of_entity']} is a {entity.TYPE}; a {kind.replace('_', ' ')} "
                f"dimension measures an arc or a circle",
                hint="find_entities type='arc' lists the curves; or give center and "
                     "radius yourself")
        center, radius = list(entity.center), float(entity.radius)
    else:
        center = _point(p, "center") if "center" in p else None
        radius = float(p["radius"]) if "radius" in p else None
        if center is None or radius is None:
            raise CommandFault(
                f"a {kind.replace('_', ' ')} dimension measures an arc or a circle",
                hint="give of_entity (an arc or circle), or center and radius")
        if radius <= 0:
            raise CommandFault(f"radius must be positive, got {radius}")
    at_center = geo.distance(center, line_point) <= EPS
    out = {"center": center, "radius": radius}
    if kind != "arc_length":
        # text at the centre is ordinary on a diameter: measure across horizontally
        out["p1"] = _point(p, "p1") if "p1" in p else _on_circle(
            center, radius, 0.0 if at_center else direction_of(center, line_point),
            entity)
        return out
    if at_center:
        raise CommandFault(
            "line_point is the centre, so the dimension arc has no radius to run at",
            hint="line_point is where the arc length is drawn: put it out beyond "
                 "(or inside) the arc being measured")
    if "p1" in p and "p2" in p:
        out["p1"], out["p2"] = _point(p, "p1"), _point(p, "p2")
        return out
    if isinstance(entity, Arc):
        start, end = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        out["p1"] = geo.arc_point(center, radius, start)
        out["p2"] = geo.arc_point(center, radius, end)
        return out
    raise CommandFault(
        "an arc length dimension needs the two ends of the arc",
        hint="give of_entity (an arc), or p1 and p2 on the circle -- the length is "
             "measured counter-clockwise from p1 to p2")


def _on_circle(center, radius, angle_deg, entity) -> list:
    """The point the arrowhead touches: out along ``angle_deg``, kept within
    the arc when the dimension is measuring one."""
    if isinstance(entity, Arc):
        start, end = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        angle = angle_deg % 360.0
        if not (start <= angle <= end or start <= angle + 360.0 <= end):
            to_start = min((start - angle) % 360.0, (angle - start) % 360.0)
            to_end = min((end - angle) % 360.0, (angle - end) % 360.0)
            angle = start if to_start <= to_end else end
        angle_deg = angle
    return geo.arc_point(center, radius, angle_deg)


# ---------------------------------------------------------------- lookups


def _target(doc, space_key, eid, role):
    """An entity to measure, host or reference, in the dimension's own space."""
    found = resolve_entity(doc, eid)
    if found is None:
        raise CommandFault(
            f"no entity {eid!r} to measure ({role})",
            hint="find_entities and hit_test return ids; elements of an attached "
                 "reference are 'REFNAME:ID'")
    entity, owner, _ref, entity_space = found
    if entity_space != space_key:
        raise CommandFault(
            f"{eid} is in {entity_space}, but the dimension goes in {space_key}",
            hint=f"place the dimension in {entity_space}, or measure something there")
    return entity, owner


def _end_point(doc, space_key, p, entity_key, at_key, point_key) -> Optional[list]:
    """One end of a measurement: a point, or a place on a named entity."""
    if entity_key and entity_key in p:
        if point_key in p:
            raise CommandFault(f"give {point_key} or {entity_key}, not both",
                               hint=f"{entity_key} lets the engine put the point on "
                                    f"the entity; {point_key} states it outright")
        entity, owner = _target(doc, space_key, p[entity_key], entity_key)
        try:
            return point_at(owner, entity, p.get(at_key, "mid"))[0]
        except ValueError as ex:
            raise CommandFault(str(ex), hint=f"{at_key} is start|mid|end or a "
                                             f"fraction from 0 to 1")
    return _point(p, point_key) if point_key in p else None


def _point(p, key) -> list:
    value = p[key]
    return [float(value[0]), float(value[1])]


# ------------------------------------------------------------- validation


def _check_measurement(dim: Dimension, p: dict) -> None:
    """A dimension that measures nothing is a mistake, not a drawing."""
    value = dimgeom.measure(dim)
    if dim.kind == "angular":
        if value <= EPS or value >= 360.0 - EPS:
            raise CommandFault(
                "the two rays lie on top of each other, so there is no angle to "
                "measure", hint="p1 and p2 are points out along each side of the "
                                "angle, seen from center")
        return
    if abs(value) > EPS:
        return
    if dim.kind in ("linear", "aligned") and geo.distance(dim.p1, dim.p2) <= EPS:
        raise CommandFault(
            "p1 and p2 are the same point, so there is nothing to measure",
            hint="they are the two ends of what is being measured; from_entity and "
                 "to_entity (with from_at/to_at) put them on real geometry")
    if dim.kind == "linear":
        raise CommandFault(
            f"this dimension measures at {dimgeom.direction_deg(dim):g}\u00b0 and the "
            f"two points are level that way, so it measures 0",
            hint="drop rotation_deg and the direction is read off the points, or use "
                 "kind 'aligned' for the true distance between them")
    raise CommandFault(f"a {dim.kind} dimension of 0 has nothing to show",
                       hint="check the points (or the arc) being measured")


__all__ = ["place_dimension"]
