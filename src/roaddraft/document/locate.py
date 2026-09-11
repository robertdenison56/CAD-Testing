"""Points on entities: where to aim at a thing, computed by the engine.

An agent that has found an entity still has to say *where* on it to point, and
that is exactly where geometry goes wrong. A curve arrives as a center, a
radius and two angles -- no start, no end, no midpoint -- and the obvious
shortcut, averaging the endpoints, lands off the arc by the sagitta. So the
engine answers the question instead: name the entity and a position along it,
get back a point that is genuinely on it and the direction it runs.

``where`` is ``"start"``, ``"mid"``, ``"end"`` or a fraction of the entity's
length from 0 to 1. Entities with no path (text, blocks, tables) answer with
their insertion point, since there is nothing to run along.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Entity, Line, Polyline, Table, Text,
)

WHERE_NAMES = {"start": 0.0, "mid": 0.5, "middle": 0.5, "end": 1.0, "center": 0.5}

#: Entity types that run along a path, so a fraction of one means something.
PATH_TYPES = (Line, Polyline, Arc, Circle)


def as_fraction(where) -> float:
    """``"mid"`` / ``0.25`` -> a fraction in [0, 1]. Raises ValueError."""
    if isinstance(where, bool):
        raise ValueError(f"where must be start/mid/end or a fraction, got {where!r}")
    if isinstance(where, (int, float)):
        value = float(where)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"a fraction along an entity must be 0 to 1, got {value:g}")
        return value
    key = str(where).strip().lower()
    if key not in WHERE_NAMES:
        raise ValueError(f"where must be one of {sorted(set(WHERE_NAMES))} or a "
                         f"fraction from 0 to 1, got {where!r}")
    return WHERE_NAMES[key]


def entity_length(doc, entity: Entity) -> Optional[float]:
    """Length along the entity, or None when it has no path."""
    if isinstance(entity, Line):
        return geo.distance(entity.start, entity.end)
    if isinstance(entity, Polyline):
        points = _polyline_points(entity)
        return sum(geo.distance(a, b) for a, b in zip(points, points[1:]))
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        return entity.radius * math.radians(e - s)
    if isinstance(entity, Circle):
        return 2.0 * math.pi * entity.radius
    return None


def point_at(doc, entity: Entity, where="mid") -> Tuple[List[float], Optional[float]]:
    """``(point, direction_deg)`` at ``where`` along ``entity``.

    The point is on the entity -- on the arc, not on its chord. ``direction_deg``
    is the heading the entity runs at that point, or None where it has no path.
    """
    t = as_fraction(where)
    if isinstance(entity, Line):
        return _lerp(entity.start, entity.end, t), _heading(entity.start, entity.end)
    if isinstance(entity, Polyline):
        return _along_polyline(entity, t)
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        angle = s + (e - s) * t
        # CCW travel: the tangent leads the radius by 90 degrees
        return geo.arc_point(entity.center, entity.radius, angle), (angle + 90.0) % 360.0
    if isinstance(entity, Circle):
        angle = 360.0 * t
        return geo.arc_point(entity.center, entity.radius, angle), (angle + 90.0) % 360.0
    if isinstance(entity, (Text, BlockRef, Table)):
        return list(entity.position), getattr(entity, "rotation_deg", 0.0) or 0.0
    bbox = entity.bbox(doc)
    if bbox is None:
        raise ValueError(f"{entity.TYPE} {entity.id} has no position to point at")
    return [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0], None


def representative_point(doc, entity: Entity) -> List[float]:
    """The point to offer as "this is where it is" -- the middle of its path."""
    return point_at(doc, entity, "mid")[0]


def resolve_entity(doc, eid: str):
    """``(entity, owning document, reference name or None, space)`` for an id.

    Reference elements are addressed ``"REFNAME:ID"`` and come back in host
    coordinates, owned by the basefile they were read from. Returns None when
    nothing answers to the id.
    """
    found = doc.find_entity(eid)
    if found is not None:
        return found[1], doc, None, found[0]
    from roaddraft.document.references import reference_groups
    name, sep, sub_id = str(eid).partition(":")
    if not sep:
        return None
    for ref in doc.references.values():
        if ref.name != name:
            continue
        for group_ref, base, prims in reference_groups(doc, ref.space):
            if group_ref.id != ref.id:
                continue
            for prim in prims:
                if prim.id == sub_id:
                    return prim, base, ref.name, ref.space
    return None


def nearest_entity(doc, space_key: str, point):
    """``(id, distance)`` of the closest entity to ``point``, references
    included, or None when the space is empty. Ids of reference elements are
    qualified, as everywhere else."""
    from roaddraft.document.entities import entity_distance
    from roaddraft.document.references import reference_groups
    resolved = doc.resolve_space(space_key)
    best = None
    if resolved is not None:
        for entity in resolved[1].values():
            distance = entity_distance(doc, entity, point)
            if best is None or distance < best[1]:
                best = (entity.id, distance)
    for ref, base, prims in reference_groups(doc, space_key):
        for entity in prims:
            distance = entity_distance(base, entity, point)
            if best is None or distance < best[1]:
                best = (f"{ref.name}:{entity.id}", distance)
    return best


# ------------------------------------------------------------------ helpers


def _polyline_points(entity: Polyline) -> List[List[float]]:
    points = [list(v) for v in entity.vertices]
    if entity.closed and len(points) > 2:
        points.append(list(points[0]))
    return points


def _along_polyline(entity: Polyline, t: float):
    points = _polyline_points(entity)
    if len(points) == 1:
        return list(points[0]), None
    spans = [geo.distance(a, b) for a, b in zip(points, points[1:])]
    total = sum(spans)
    if total <= 0:
        return list(points[0]), None
    target = total * t
    walked = 0.0
    for (a, b), span in zip(zip(points, points[1:]), spans):
        if span <= 0:
            continue
        if walked + span >= target - 1e-12:
            return _lerp(a, b, (target - walked) / span), _heading(a, b)
        walked += span
    return list(points[-1]), _heading(points[-2], points[-1])


def _lerp(a, b, t: float) -> List[float]:
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def _heading(a, b) -> Optional[float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


__all__ = ["WHERE_NAMES", "PATH_TYPES", "as_fraction", "entity_length", "point_at",
           "representative_point", "resolve_entity", "nearest_entity"]
