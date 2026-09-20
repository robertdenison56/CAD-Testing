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
from typing import List, Optional, Tuple

from roaddraft.design.angles import right_normal
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment, CurveElement, TangentElement

STATION_EPS = 1e-6


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


def _lerp(a, b, t: float) -> List[float]:
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def offset_pieces(alignment: Alignment, offset: float,
                  station_range: Optional[Tuple[float, float]] = None
                  ) -> List[OffsetPiece]:
    """The offset chain of ``alignment`` at ``offset`` feet (right positive).

    One piece per source element, in stationing order. An offset of 0 returns
    the alignment's own geometry.

    ``station_range`` (RAW stations) cuts the chain to that window, which is
    how an offset stops at an intersection: an element that falls outside is
    dropped, one that straddles an end is trimmed there. A trimmed piece keeps
    the ref of the element it came from and carries its own start station and
    length, so a pavement edge drawn leg by leg is still anchored leg by leg.
    """
    begin = float(alignment.begin_station)
    lo = hi = None
    if station_range is not None:
        lo, hi = sorted((float(station_range[0]), float(station_range[1])))
    pieces: List[OffsetPiece] = []
    for i, el in enumerate(alignment.elements):
        ref = alignment.element_ref(i)
        station = begin + float(el.start_dist)
        span = float(el.length)
        t0, t1 = 0.0, 1.0
        if lo is not None:
            if span <= 0 or station + span <= lo + STATION_EPS \
                    or station >= hi - STATION_EPS:
                continue
            t0 = max(0.0, (lo - station) / span)
            t1 = min(1.0, (hi - station) / span)
            if t1 - t0 <= 1e-12:
                continue
        if isinstance(el, TangentElement):
            start = _lerp(el.start, el.end, t0)
            end = _lerp(el.start, el.end, t1)
            pieces.append(OffsetPiece(
                kind="tangent", ref=ref, element_index=i,
                station=station + span * t0, offset=offset,
                length=span * (t1 - t0),
                start=shift(start, el.direction_deg, offset),
                end=shift(end, el.direction_deg, offset),
                direction_deg=float(el.direction_deg)))
        else:
            r = offset_radius(el, offset)
            # the sweep from the PC runs CCW on a left curve, CW on a right one
            phi0 = el.phi0_deg
            a0 = phi0 + el.sign * el.delta_deg * t0
            a1 = phi0 + el.sign * el.delta_deg * t1
            s, e = (a0, a1) if el.direction == "L" else (a1, a0)
            delta = el.delta_deg * (t1 - t0)
            pieces.append(OffsetPiece(
                kind="curve", ref=ref, element_index=i,
                station=station + span * t0, offset=offset,
                length=r * math.radians(delta),
                center=list(el.center), radius=r, start_angle_deg=s, end_angle_deg=e,
                direction=el.direction, delta_deg=delta))
    return pieces


def offset_length(alignment: Alignment, offset: float,
                  station_range: Optional[Tuple[float, float]] = None) -> float:
    """Total length of the offset chain (longer than the alignment outside a
    left curve, shorter inside it)."""
    return sum(p.length for p in offset_pieces(alignment, offset, station_range))


__all__ = ["OffsetPiece", "shift", "offset_radius", "offset_pieces", "offset_length"]
