"""Similarity transforms of entities: move, rotate, scale and mirror.

Every entity already maps itself through a rotation-and-scale
(``Entity.transformed``). A mirror is different: it turns the drawing over, so
an angle no longer just gains a constant -- an arc that ran counter-clockwise
runs clockwise, a polyline's arcs bow the other way. ``transform_entity``
handles both, for every entity type, from one description of the map:

    p -> offset + scale * R(rotation) * F^mirror * p

where F reflects across the x-axis. Drafting conventions ride along: text and
point labels still read left to right after a mirror (AutoCAD MIRRTEXT 0 --
plan lettering is never printed backwards), a table stays upright, and a block
is flagged ``mirrored`` so the symbol itself turns over.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from roaddraft.core import geometry as geo
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Entity, Hatch, Line, Point, Polyline, Table, Text,
)


@dataclass
class Similarity:
    """``p -> offset + scale * R(rotation_deg) * F^mirror * p``."""

    scale: float = 1.0
    rotation_deg: float = 0.0
    mirror: bool = False
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0])

    # ------------------------------------------------------------ makers

    @classmethod
    def translation(cls, delta) -> "Similarity":
        return cls(offset=[float(delta[0]), float(delta[1])])

    @classmethod
    def rotation(cls, base, angle_deg: float) -> "Similarity":
        """Rotate ``angle_deg`` counter-clockwise about ``base``."""
        t = cls(rotation_deg=float(angle_deg))
        moved = t.apply(base)
        return t.then_translate([base[0] - moved[0], base[1] - moved[1]])

    @classmethod
    def scaling(cls, base, factor: float) -> "Similarity":
        """Scale by ``factor`` about ``base``."""
        t = cls(scale=float(factor))
        moved = t.apply(base)
        return t.then_translate([base[0] - moved[0], base[1] - moved[1]])

    @classmethod
    def reflection(cls, p1, p2) -> "Similarity":
        """Mirror across the line through ``p1`` and ``p2``."""
        phi = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        t = cls(rotation_deg=2.0 * phi, mirror=True)
        moved = t.apply(p1)
        return t.then_translate([p1[0] - moved[0], p1[1] - moved[1]])

    # ----------------------------------------------------------- applying

    def apply(self, p) -> List[float]:
        x, y = float(p[0]), float(p[1])
        if self.mirror:
            y = -y
        x, y = geo.rotate_point([x * self.scale, y * self.scale], self.rotation_deg)
        return [x + self.offset[0], y + self.offset[1]]

    def angle(self, angle_deg: float) -> float:
        """Where a direction goes."""
        return self.rotation_deg + (-angle_deg if self.mirror else angle_deg)

    def then_translate(self, delta) -> "Similarity":
        return Similarity(self.scale, self.rotation_deg, self.mirror,
                          [self.offset[0] + delta[0], self.offset[1] + delta[1]])

    def then(self, other: "Similarity") -> "Similarity":
        """This map followed by ``other``."""
        o = other.apply(self.offset)
        rot = other.rotation_deg + (-self.rotation_deg if other.mirror else self.rotation_deg)
        return Similarity(self.scale * other.scale, rot, self.mirror != other.mirror, o)

    @property
    def is_identity(self) -> bool:
        return (abs(self.scale - 1.0) < 1e-15 and abs(self.rotation_deg % 360.0) < 1e-12
                and not self.mirror and abs(self.offset[0]) < 1e-15
                and abs(self.offset[1]) < 1e-15)


def _norm(angle_deg: float) -> float:
    """An angle in [0, 360), with -0.0 and 359.9999999999 read as 0."""
    a = angle_deg % 360.0
    return 0.0 if a > 360.0 - 1e-9 or a < 1e-12 else a


def _common(e: Entity) -> dict:
    return dict(id=e.id, layer=e.layer, color=e.color, linetype=e.linetype,
                anchor=e.anchor, annotative=e.annotative)


def _readable(t: Similarity, rotation_deg: float, halign: str, valign: str):
    """Rotation and justification that keep mirrored lettering readable.

    The mirror image of a text box has a left-handed frame. Either flip its
    up direction (keep the reading direction, swap bottom/top) or flip its
    reading direction (keep up, turn 180 degrees, swap left/right) -- whichever
    leaves the lettering closer to upright, as a drafter would letter it."""
    swap_v = {"bottom": "top", "top": "bottom", "middle": "middle"}
    swap_h = {"left": "right", "right": "left", "center": "center"}
    keep_reading = t.angle(rotation_deg)
    turned = keep_reading + 180.0

    def lean(a):
        return abs(((a % 360.0) + 180.0) % 360.0 - 180.0)

    if lean(keep_reading) <= lean(turned):
        return keep_reading, halign, swap_v.get(valign, valign)
    return turned, swap_h.get(halign, halign), valign


def transform_entity(e: Entity, t: Similarity) -> Entity:
    """A copy of ``e`` mapped through ``t`` (same id, same properties)."""
    if not t.mirror:  # a turn and a size: every entity knows how
        out = e.transformed(t.apply, t.rotation_deg, t.scale)
        for name in ("rotation_deg", "angle_deg"):
            if isinstance(getattr(out, name, None), float):
                setattr(out, name, _norm(getattr(out, name)))
        return out
    fn, s = t.apply, t.scale
    if isinstance(e, Line):
        return Line(**_common(e), start=fn(e.start), end=fn(e.end))
    if isinstance(e, Polyline):
        return Polyline(**_common(e), vertices=[fn(v) for v in e.vertices], closed=e.closed,
                        bulges=[-b for b in e.bulges] if e.bulges else None)
    if isinstance(e, Arc):
        # a counter-clockwise arc comes out clockwise: swap its ends
        return Arc(**_common(e), center=fn(e.center), radius=e.radius * s,
                   start_angle_deg=t.angle(e.end_angle_deg),
                   end_angle_deg=t.angle(e.start_angle_deg))
    if isinstance(e, Circle):
        return Circle(**_common(e), center=fn(e.center), radius=e.radius * s)
    if isinstance(e, Text):
        rotation, halign, valign = _readable(t, e.rotation_deg, e.halign, e.valign)
        return Text(**_common(e), position=fn(e.position), content=e.content,
                    height=e.height * s, style=e.style, rotation_deg=_norm(rotation),
                    halign=halign, valign=valign)
    if isinstance(e, BlockRef):
        # F R(r) M^m = R(-r) F M^m = R(180 - r) M^(m+1): flip the flag
        return BlockRef(**_common(e), block_name=e.block_name, position=fn(e.position),
                        scale=e.scale * s,
                        rotation_deg=_norm(t.rotation_deg - e.rotation_deg + 180.0),
                        mirrored=not e.mirrored)
    if isinstance(e, Table):
        # tables stay upright: the mirrored box keeps its corner at top-left
        x0, y0, x1, y1 = e.bbox(None)
        corners = [fn(c) for c in ([x0, y0], [x1, y0], [x1, y1], [x0, y1])]
        top_left = [min(c[0] for c in corners), max(c[1] for c in corners)]
        moved = e.transformed(lambda p: p, 0.0, s)
        moved.position = top_left
        return moved
    if isinstance(e, Dimension):
        swap = e.kind in ("angular", "arc_length")  # measured counter-clockwise
        p1 = None if e.p1 is None else fn(e.p1)
        p2 = None if e.p2 is None else fn(e.p2)
        if swap and p2 is not None:
            p1, p2 = p2, p1

        def scaled(value):
            return None if value is None else value * s

        return Dimension(
            **_common(e), kind=e.kind, p1=p1, p2=p2,
            center=None if e.center is None else fn(e.center), radius=scaled(e.radius),
            line_point=fn(e.line_point),
            rotation_deg=None if e.rotation_deg is None else t.angle(e.rotation_deg),
            text_height=e.text_height * s, style=e.style, text_override=e.text_override,
            prefix=e.prefix, suffix=e.suffix, unit_format=e.unit_format,
            precision=e.precision, arrow=e.arrow, arrow_size=scaled(e.arrow_size),
            text_gap=scaled(e.text_gap), extension_offset=scaled(e.extension_offset),
            extension_beyond=scaled(e.extension_beyond),
            measure_scale=e.measure_scale / s if s else e.measure_scale,
            view_rotation=e.view_rotation)
    if isinstance(e, Point):
        return e.transformed(fn, 0.0, s)
    if isinstance(e, Hatch):
        loops = []
        for loop in e.loops:
            moved = {"vertices": [fn(v) for v in loop["vertices"]]}
            if loop.get("bulges"):
                moved["bulges"] = [-b for b in loop["bulges"]]
            loops.append(moved)
        return Hatch(**_common(e), loops=loops, pattern=e.pattern, scale=e.scale * s,
                     angle_deg=_norm(t.angle(e.angle_deg)), opacity=e.opacity)
    raise TypeError(f"cannot transform a {e.TYPE}")


__all__ = ["Similarity", "transform_entity"]
