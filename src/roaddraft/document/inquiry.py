"""What a drafter reads off an entity with LIST (AutoCAD) or Analyze Element
(MicroStation): not the fields it is stored as, but the geometry they mean --
a line's length and bearing, a curve's radius, delta, length, chord and
tangent, a closed shape's area and perimeter, a point's northing and easting.

``properties`` answers for every entity type, in the entity's own space
units, rounded for reading.
"""
from __future__ import annotations

import math
from typing import List

from roaddraft.core import geometry as geo
from roaddraft.design.angles import direction_to_azimuth, format_bearing, format_dms
from roaddraft.document import paths, regions
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Entity, Hatch, Line, Point, Polyline, Table, Text,
)

DECIMALS = 6


def _r(value):
    if isinstance(value, float):
        return round(value, DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0
    if isinstance(value, (list, tuple)):
        return [_r(v) for v in value]
    if isinstance(value, dict):
        return {k: _r(v) for k, v in value.items()}
    return value


def _bearing(heading_deg: float) -> str:
    return format_bearing(direction_to_azimuth(heading_deg))


def _line_props(a, b) -> dict:
    heading = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return {"start": list(a), "end": list(b), "length": geo.distance(a, b),
            "bearing": _bearing(heading), "azimuth_deg": direction_to_azimuth(heading),
            "direction_deg": heading % 360.0, "dx": b[0] - a[0], "dy": b[1] - a[1],
            "midpoint": [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]}


def _curve_props(piece: paths.ArcSeg) -> dict:
    """Curve data of an arc travelled the way the piece runs."""
    delta = abs(piece.sweep)
    r = piece.radius
    half = math.radians(delta) / 2.0
    a, b = piece.start, piece.end
    chord_heading = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    mid = piece.point_at(piece.length / 2.0)
    out = {"start": a, "end": b, "center": list(piece.center), "radius": r,
           "delta_deg": delta, "delta": format_dms(delta), "length": piece.length,
           "chord": 2.0 * r * math.sin(half), "chord_bearing": _bearing(chord_heading),
           "turn": "left" if piece.sweep > 0 else "right",
           "start_bearing": _bearing(piece.dir_in()), "end_bearing": _bearing(piece.dir_out()),
           "midpoint": mid, "mid_ordinate": r * (1.0 - math.cos(half))}
    if delta < 180.0 - 1e-9:
        out["tangent"] = r * math.tan(half)
        out["external"] = r * (1.0 / math.cos(half) - 1.0)
    return out


def _segment_rows(entity: Polyline) -> List[dict]:
    rows = []
    for k, piece in enumerate(paths.pieces_of(entity)[0], 1):
        if isinstance(piece, paths.Seg):
            row = {"segment": k, "kind": "line", **_line_props(piece.a, piece.b)}
            for key in ("dx", "dy", "midpoint", "direction_deg"):
                row.pop(key)
        else:
            row = {"segment": k, "kind": "curve", **_curve_props(piece)}
        rows.append(row)
    return rows


def _area_props(loops, space_units: str) -> dict:
    m = regions.region_measure(loops)
    out = {"area": m["area"], "perimeter": m["perimeter"], "centroid": m["centroid"]}
    if space_units == "ft":
        out["square_yards"] = m["area"] / 9.0
        out["acres"] = m["area"] / 43560.0
    islands = sum(1 for row in m["loops"] if row["kind"] == "island")
    if islands:
        out["islands"] = islands
    return out


def properties(owner, entity: Entity, space_key: str = "model") -> dict:
    """The geometry an entity stands for, for reading (see the module doc)."""
    units = "ft" if space_key == "model" else "in"
    out: dict = {"units": units}
    if isinstance(entity, Line):
        out.update(_line_props(entity.start, entity.end))
    elif isinstance(entity, Arc):
        piece = paths.pieces_of(entity)[0][0]
        out.update(_curve_props(piece))
        out["start_angle_deg"] = entity.start_angle_deg
        out["end_angle_deg"] = entity.end_angle_deg
    elif isinstance(entity, Circle):
        r = entity.radius
        out.update({"center": list(entity.center), "radius": r, "diameter": 2 * r,
                    "circumference": 2 * math.pi * r, "area": math.pi * r * r})
        if units == "ft":
            out["acres"] = math.pi * r * r / 43560.0
    elif isinstance(entity, Polyline):
        path = paths.Path.of_entity(entity)
        out.update({"vertices": len(entity.vertices), "closed": entity.closed,
                    "length": path.length, "start": path.start, "end": path.end,
                    "arc_segments": sum(1 for pc in path.pieces
                                        if isinstance(pc, paths.ArcSeg))})
        out["segments"] = _segment_rows(entity)
        loop = regions.loop_of_entity(entity)
        if loop is not None:
            out.update(_area_props([loop], units))
    elif isinstance(entity, Text):
        out.update({"content": entity.content, "position": list(entity.position),
                    "height": entity.height, "rotation_deg": entity.rotation_deg,
                    "style": entity.style, "justify": f"{entity.valign} {entity.halign}"})
    elif isinstance(entity, BlockRef):
        out.update({"block_name": entity.block_name, "position": list(entity.position),
                    "scale": entity.scale, "rotation_deg": entity.rotation_deg,
                    "mirrored": entity.mirrored})
    elif isinstance(entity, Point):
        out.update({"number": entity.number, "northing": entity.position[1],
                    "easting": entity.position[0], "elevation": entity.elevation,
                    "description": entity.description})
    elif isinstance(entity, Hatch):
        out.update({"pattern": entity.pattern, "scale": entity.scale,
                    "angle_deg": entity.angle_deg, "loops": len(entity.loops)})
        out.update(_area_props(entity.loops, units))
    elif isinstance(entity, Dimension):
        from roaddraft.document import dimgeom
        out["kind"] = entity.kind
        try:
            out["value"] = dimgeom.measure(entity)
            out["text"] = dimgeom.text_of(entity)
        except Exception:
            pass
    elif isinstance(entity, Table):
        w, h = entity.size()
        out.update({"title": entity.title, "columns": [c["header"] for c in entity.columns],
                    "rows": len(entity.rows), "width": w, "height": h})
    bb = entity.bbox(owner)
    if bb is not None:
        out["extents"] = list(bb)
    return {k: _r(v) for k, v in out.items()}


__all__ = ["properties"]
