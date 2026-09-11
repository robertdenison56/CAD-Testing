"""Constant offsets of an alignment: pavement edges, shoulders, right of way.

A constant offset of a tangent-and-curve chain is exact, not an approximation.
Each tangent shifts sideways by the offset and keeps its direction and length;
each curve keeps its center and its angular extent and changes radius only.
The radial lines at the PC and PT are shared with the offset, so the offset
pieces meet end to end with no fillet -- which is why a pavement edge drawn at
a constant offset of the centerline is a clean chain of lines and arcs.

Sign follows the anchor grammar: **offset is positive to the right** of the
direction of stationing, so a 24 ft pavement drafts as offsets -12 and +12.
A curve's radius becomes ``R + offset * sign`` (sign +1 left-turning, -1
right-turning): offsetting outward lengthens the arc, inward shortens it.
An offset that reaches or passes the center of a curve has no geometry and
raises ``DesignError``.

Pure geometry; imports nothing above the design layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from roaddraft.design.angles import right_normal
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment, CurveElement, TangentElement


@dataclass
class OffsetPiece:
    """One line or arc of an offset chain, with the source element it came from."""

    kind: str                    # "tangent" | "curve"
    ref: str                     # source element ref: "T-1", "C-1"
    element_index: int
    station: float               # raw station of the source element's start
    offset: float                # signed, right positive
    length: float
    # tangent geometry
    start: Optional[List[float]] = None
    end: Optional[List[float]] = None
    direction_deg: Optional[float] = None
    # curve geometry (CCW-drawn angles, as the document stores arcs)
    center: Optional[List[float]] = None
    radius: Optional[float] = None
    start_angle_deg: Optional[float] = None
    end_angle_deg: Optional[float] = None
    direction: Optional[str] = None
    delta_deg: Optional[float] = None


def shift(point, direction_deg: float, offset: float) -> List[float]:
    """``point`` moved ``offset`` feet to the right of ``direction_deg``."""
    n = right_normal(direction_deg)
    return [point[0] + n[0] * offset, point[1] + n[1] * offset]


def offset_radius(curve: CurveElement, offset: float) -> float:
    """The offset arc's radius: outward from the center lengthens it.

    Raises ``DesignError`` when the offset reaches or crosses the center.
    """
    r = curve.radius + offset * curve.sign
    if r <= 0:
        side = "left" if offset < 0 else "right"
        raise DesignError(
            f"offset {abs(offset):g} ft {side} passes the center of a "
            f"{curve.radius:g} ft radius curve",
            hint=f"the offset must stay inside {curve.radius:g} ft on the "
                 f"inside of the curve")
    return r


def offset_pieces(alignment: Alignment, offset: float) -> List[OffsetPiece]:
    """The offset chain of ``alignment`` at ``offset`` feet (right positive).

    One piece per source element, in stationing order. An offset of 0 returns
    the alignment's own geometry.
    """
    begin = float(alignment.begin_station)
    pieces: List[OffsetPiece] = []
    for i, el in enumerate(alignment.elements):
        ref = alignment.element_ref(i)
        station = begin + float(el.start_dist)
        if isinstance(el, TangentElement):
            pieces.append(OffsetPiece(
                kind="tangent", ref=ref, element_index=i, station=station, offset=offset,
                length=float(el.length),
                start=shift(el.start, el.direction_deg, offset),
                end=shift(el.end, el.direction_deg, offset),
                direction_deg=float(el.direction_deg)))
        else:
            r = offset_radius(el, offset)
            s, e = el.ccw_angles()
            pieces.append(OffsetPiece(
                kind="curve", ref=ref, element_index=i, station=station, offset=offset,
                length=r * math.radians(el.delta_deg),
                center=list(el.center), radius=r, start_angle_deg=s, end_angle_deg=e,
                direction=el.direction, delta_deg=float(el.delta_deg)))
    return pieces


def offset_length(alignment: Alignment, offset: float) -> float:
    """Total length of the offset chain (longer than the alignment outside a
    left curve, shorter inside it)."""
    return sum(p.length for p in offset_pieces(alignment, offset))


__all__ = ["OffsetPiece", "shift", "offset_radius", "offset_pieces", "offset_length"]
