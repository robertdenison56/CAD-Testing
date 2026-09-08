"""Horizontal alignments: PIs, tangents, circular curves, stationing.

An ``Alignment`` is a list of ``TangentElement``/``CurveElement`` objects in
travel order.  It is normally compiled from PIs (``compile_pis``) but can
also be built from stored/imported element geometry
(``elements_from_dicts`` + ``alignment_from_elements``).

Conventions (spec section 0): points are ``[x, y]`` in US survey feet;
``direction_deg`` is a math heading (CCW from +X); offsets are positive to
the RIGHT of increasing station; ``delta_deg`` is always positive with the
turn sense in ``direction`` (``"L"`` = CCW ahead, ``"R"`` = CW).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.angles import (
    direction_of,
    direction_to_azimuth,
    format_bearing,
    format_dms,
    left_normal,
    norm_deg,
    right_normal,
    signed_delta_deg,
    unit_vector,
)
from roaddraft.design.errors import DesignError
from roaddraft.design.stations import STATION_EPS, StationEquation, StationSystem

ELEMENT_KINDS = ("tangent", "curve", "spiral")
GEOM_EPS = 1e-6  # ft
ANGLE_EPS = 1e-9  # deg
CONNECT_TOL = 1e-3  # ft (LandXML continuity)
_COINCIDENT_TOL = 0.01  # ft
_SPIRAL_MSG = "spiral elements are not supported in this version"


def _pt(p: Sequence[float]) -> List[float]:
    """Copy a point as a two-float list."""
    try:
        return [float(p[0]), float(p[1])]
    except (TypeError, IndexError, KeyError):
        raise DesignError(f"point must be [x, y], not {p!r}")


def _add(p: Sequence[float], v: Sequence[float], k: float = 1.0) -> List[float]:
    return [p[0] + k * v[0], p[1] + k * v[1]]


# ------------------------------------------------------------------ PIs


@dataclass
class PI:
    """A point of intersection; ``radius`` is 0 at BEGIN/END, > 0 interior."""

    point: List[float]
    radius: float = 0.0

    def to_dict(self) -> dict:
        return {"point": _pt(self.point), "radius": float(self.radius)}

    @classmethod
    def from_dict(cls, d) -> "PI":
        if isinstance(d, dict):
            if "point" not in d:
                raise DesignError("PI needs a point: {'point': [x, y], 'radius': R}")
            return cls(point=_pt(d["point"]), radius=float(d.get("radius", 0.0) or 0.0))
        if isinstance(d, (list, tuple)) and len(d) in (2, 3):
            return cls(point=_pt(d), radius=float(d[2]) if len(d) == 3 else 0.0)
        raise DesignError(f"PI must be [x, y], [x, y, radius] or a dict, not {d!r}")


# ------------------------------------------------------------- elements


@dataclass
class TangentElement:
    """A straight element from ``start`` to ``end``."""

    start: List[float]
    end: List[float]
    length: float
    direction_deg: float
    start_dist: float
    kind = "tangent"

    @property
    def end_dist(self) -> float:
        return self.start_dist + self.length


@dataclass
class CurveElement:
    """A circular curve from ``pc`` to ``pt`` about ``center``."""

    pc: List[float]
    pt: List[float]
    pi: List[float]
    center: List[float]
    radius: float
    delta_deg: float
    direction: str  # "L" | "R"
    length: float
    start_dist: float
    direction_in_deg: float
    direction_out_deg: float
    kind = "curve"

    @property
    def sign(self) -> float:
        return 1.0 if self.direction == "L" else -1.0

    @property
    def tangent_length(self) -> float:
        return self.radius * math.tan(math.radians(self.delta_deg) / 2.0)

    @property
    def start(self) -> List[float]:
        return self.pc

    @property
    def end(self) -> List[float]:
        return self.pt

    @property
    def end_dist(self) -> float:
        return self.start_dist + self.length

    @property
    def phi0_deg(self) -> float:
        """Angle from the center to the PC."""
        return direction_of(self.center, self.pc)

    def ccw_angles(self) -> Tuple[float, float]:
        """``(start, end)`` angles from the center for a CCW-drawn arc."""
        a_pc = direction_of(self.center, self.pc)
        a_pt = direction_of(self.center, self.pt)
        return (a_pc, a_pt) if self.direction == "L" else (a_pt, a_pc)


def _tangent(start, end, start_dist: float) -> TangentElement:
    s, e = _pt(start), _pt(end)
    return TangentElement(start=s, end=e, length=geo.distance(s, e),
                          direction_deg=direction_of(s, e), start_dist=float(start_dist))


def curve_from_pi(back_pt, pi_pt, ahead_pt, radius: float, start_dist: float,
                  label: str = "PI") -> CurveElement:
    """Circular curve fitted at ``pi_pt`` between the back and ahead tangents.

    ``start_dist`` is the distance along the alignment at the PC.  ``label``
    names the PI in error messages (``"PI-2"``).
    """
    b, p, a = _pt(back_pt), _pt(pi_pt), _pt(ahead_pt)
    radius = float(radius)
    if radius <= 0:
        raise DesignError(f"{label} needs a curve radius > 0")
    d_in = direction_of(b, p)
    d_out = direction_of(p, a)
    delta = signed_delta_deg(d_in, d_out)
    if abs(delta) < ANGLE_EPS:
        raise DesignError(f"{label} has no deflection (collinear); remove it")
    if abs(delta) >= 180.0 - ANGLE_EPS:
        raise DesignError(f"{label} deflects 180°")
    direction = "L" if delta > 0 else "R"
    big_delta = abs(delta)
    t = radius * math.tan(math.radians(big_delta) / 2.0)
    length = radius * math.radians(big_delta)
    pc = _add(p, unit_vector(d_in), -t)
    pt = _add(p, unit_vector(d_out), t)
    normal = left_normal(d_in) if direction == "L" else right_normal(d_in)
    center = _add(pc, normal, radius)
    return CurveElement(pc=pc, pt=pt, pi=p, center=center, radius=radius, delta_deg=big_delta,
                        direction=direction, length=length, start_dist=float(start_dist),
                        direction_in_deg=d_in, direction_out_deg=norm_deg(d_out))


def compile_pis(pis: List[PI]) -> List[object]:
    """Compile a PI list into tangent/curve elements in travel order.

    PIs are numbered ``PI-n`` by their 1-based position in ``pis`` in every
    error message.  Zero-length tangents between back-to-back curves are not
    emitted.
    """
    pis = [p if isinstance(p, PI) else PI.from_dict(p) for p in (pis or [])]
    n = len(pis)
    if n < 2:
        raise DesignError("an alignment needs at least 2 PIs (BEGIN and END)")
    pts = [_pt(p.point) for p in pis]
    for k in range(n - 1):
        if geo.distance(pts[k], pts[k + 1]) <= _COINCIDENT_TOL:
            raise DesignError(f"PI-{k + 1} and PI-{k + 2} are coincident")
    if float(pis[0].radius) != 0.0 or float(pis[-1].radius) != 0.0:
        raise DesignError("BEGIN/END PIs cannot carry a radius")
    for k in range(1, n - 1):
        if float(pis[k].radius) <= 0.0:
            raise DesignError(
                f"PI-{k + 1} is an angle point (radius 0); interior PIs must have a curve radius",
                hint="pass [x, y, R] for every interior PI")

    # curves (start_dist filled later)
    curves: List[CurveElement] = []
    for k in range(1, n - 1):
        curves.append(curve_from_pi(pts[k - 1], pts[k], pts[k + 1], float(pis[k].radius),
                                    0.0, label=f"PI-{k + 1}"))

    # fit check per PI-to-PI segment
    seg_len = [geo.distance(pts[k], pts[k + 1]) for k in range(n - 1)]
    tl = [0.0] + [c.tangent_length for c in curves] + [0.0]  # T at each PI (0 at ends)
    for k in range(n - 1):
        need = tl[k] + tl[k + 1]
        if need > seg_len[k] + GEOM_EPS:
            if k == 0:
                raise DesignError(
                    f"curve at PI-{k + 2} (T={tl[k + 1]:.2f}') is longer than the back tangent "
                    f"from BEGIN ({seg_len[k]:.2f}')",
                    hint="reduce the radius or move BEGIN back")
            if k == n - 2:
                raise DesignError(
                    f"curve at PI-{k + 1} (T={tl[k]:.2f}') is longer than the ahead tangent "
                    f"to END ({seg_len[k]:.2f}')",
                    hint="reduce the radius or move END ahead")
            raise DesignError(
                f"curves at PI-{k + 1} (T={tl[k]:.2f}') and PI-{k + 2} (T={tl[k + 1]:.2f}') "
                f"overlap by {need - seg_len[k]:.2f}' on the {seg_len[k]:.2f}' tangent between "
                f"them; reduce a radius or move the PIs")

    # emit
    elements: List[object] = []
    dist = 0.0
    prev_end = pts[0]
    for c in curves:
        gap = geo.distance(prev_end, c.pc)
        if gap > GEOM_EPS:
            elements.append(_tangent(prev_end, c.pc, dist))
            dist += elements[-1].length
        c.start_dist = dist
        elements.append(c)
        dist += c.length
        prev_end = c.pt
    gap = geo.distance(prev_end, pts[-1])
    if gap > GEOM_EPS or not elements:
        elements.append(_tangent(prev_end, pts[-1], dist))
    return elements


# ----------------------------------------------------- element (de)serial


def element_to_dict(el) -> dict:
    """Stored element shape (spec section 2.3)."""
    if isinstance(el, TangentElement):
        return {"kind": "tangent", "start": _pt(el.start), "end": _pt(el.end),
                "length": float(el.length), "direction_deg": float(el.direction_deg),
                "start_dist": float(el.start_dist)}
    if isinstance(el, CurveElement):
        return {"kind": "curve", "pc": _pt(el.pc), "pt": _pt(el.pt), "pi": _pt(el.pi),
                "center": _pt(el.center), "radius": float(el.radius),
                "delta_deg": float(el.delta_deg), "direction": el.direction,
                "length": float(el.length), "start_dist": float(el.start_dist),
                "direction_in_deg": float(el.direction_in_deg),
                "direction_out_deg": float(el.direction_out_deg)}
    raise DesignError(f"unknown element type {type(el).__name__}")


def _curve_from_geometry(pc, pt, center, direction: str, radius: Optional[float],
                         pi=None, start_dist: float = 0.0) -> CurveElement:
    """Curve from PC/PT/center (+ turn sense); derived fields recomputed."""
    pc, pt, center = _pt(pc), _pt(pt), _pt(center)
    if direction not in ("L", "R"):
        raise DesignError(f"curve direction must be 'L' or 'R', not {direction!r}")
    r = float(radius) if radius is not None else geo.distance(pc, center)
    if r <= GEOM_EPS:
        raise DesignError("curve radius must be > 0")
    sign = 1.0 if direction == "L" else -1.0
    phi0 = direction_of(center, pc)
    phi1 = direction_of(center, pt)
    delta = norm_deg(sign * (phi1 - phi0))
    if delta >= 360.0 - ANGLE_EPS:
        delta = 0.0
    d_in = norm_deg(phi0 + sign * 90.0)
    d_out = norm_deg(d_in + sign * delta)
    t = r * math.tan(math.radians(delta) / 2.0)
    pi_pt = _pt(pi) if pi is not None else _add(pc, unit_vector(d_in), t)
    return CurveElement(pc=pc, pt=pt, pi=pi_pt, center=center, radius=r, delta_deg=delta,
                        direction=direction, length=r * math.radians(delta),
                        start_dist=float(start_dist), direction_in_deg=d_in,
                        direction_out_deg=d_out)


def element_from_dict(d: dict) -> object:
    """Element from its stored dict.  Stored values are trusted (no recompute);
    derived fields missing from a minimal import shape are computed."""
    if not isinstance(d, dict):
        raise DesignError(f"element must be an object, not {d!r}")
    kind = d.get("kind")
    if kind == "spiral":
        raise DesignError(_SPIRAL_MSG)
    if kind == "tangent":
        for key in ("start", "end"):
            if key not in d:
                raise DesignError(f"tangent element needs {key}")
        start, end = _pt(d["start"]), _pt(d["end"])
        if all(k in d for k in ("length", "direction_deg", "start_dist")):
            return TangentElement(start=start, end=end, length=float(d["length"]),
                                  direction_deg=float(d["direction_deg"]),
                                  start_dist=float(d["start_dist"]))
        return _tangent(start, end, float(d.get("start_dist", 0.0)))
    if kind == "curve":
        for key in ("pc", "pt"):
            if key not in d:
                raise DesignError(f"curve element needs {key}")
        stored = ("pi", "center", "radius", "delta_deg", "direction", "length", "start_dist",
                  "direction_in_deg", "direction_out_deg")
        if all(k in d for k in stored):
            direction = d["direction"]
            if direction not in ("L", "R"):
                raise DesignError(f"curve direction must be 'L' or 'R', not {direction!r}")
            return CurveElement(pc=_pt(d["pc"]), pt=_pt(d["pt"]), pi=_pt(d["pi"]),
                                center=_pt(d["center"]), radius=float(d["radius"]),
                                delta_deg=float(d["delta_deg"]), direction=direction,
                                length=float(d["length"]), start_dist=float(d["start_dist"]),
                                direction_in_deg=float(d["direction_in_deg"]),
                                direction_out_deg=float(d["direction_out_deg"]))
        if "center" not in d:
            raise DesignError("curve element needs center (or pc, pt, center, direction)")
        if "direction" not in d:
            raise DesignError("curve element needs direction 'L' or 'R'")
        return _curve_from_geometry(d["pc"], d["pt"], d["center"], d["direction"],
                                    d.get("radius"), d.get("pi"), float(d.get("start_dist", 0.0)))
    raise DesignError(f"unknown element kind {kind!r}; kinds: tangent, curve")


def validate_continuity(elements, tol: float = CONNECT_TOL) -> None:
    """Every element must start where the previous one ends (within ``tol``)."""
    for i in range(1, len(elements)):
        gap = geo.distance(elements[i - 1].end, elements[i].start)
        if gap > tol:
            raise DesignError(
                f"element {i + 1} starts {gap:.3f} ft from the end of element {i}")


def elements_from_dicts(items: List[dict], tol: float = CONNECT_TOL) -> List[object]:
    """Elements from stored or minimal import dicts, geometry recomputed.

    Accepts ``{"kind":"tangent","start","end"}`` and
    ``{"kind":"curve","pc","pt","center","direction"}`` (radius optional).
    ``length``/``direction``/``delta``/``start_dist`` are always recomputed
    from the geometry; continuity is validated (heading kinks are allowed).
    """
    if not items:
        raise DesignError("an alignment needs at least one element")
    elements: List[object] = []
    dist = 0.0
    for i, d in enumerate(items, start=1):
        if not isinstance(d, dict):
            raise DesignError(f"element {i} must be an object")
        kind = d.get("kind")
        if kind == "spiral":
            raise DesignError(_SPIRAL_MSG)
        if kind == "tangent":
            for key in ("start", "end"):
                if key not in d:
                    raise DesignError(f"element {i}: tangent needs {key}")
            el = _tangent(d["start"], d["end"], dist)
        elif kind == "curve":
            for key in ("pc", "pt", "center", "direction"):
                if key not in d:
                    raise DesignError(f"element {i}: curve needs {key}")
            el = _curve_from_geometry(d["pc"], d["pt"], d["center"], d["direction"],
                                      d.get("radius"), d.get("pi"), dist)
        else:
            raise DesignError(f"element {i}: unknown element kind {kind!r}; kinds: tangent, curve")
        elements.append(el)
        dist += el.length
    validate_continuity(elements, tol)
    return elements


def pis_from_elements(elements) -> List[PI]:
    """Recover PIs (``[BEGIN] + curve PIs + [END]``); ``[]`` when a curve is
    not between tangents/ends (back-to-back curves)."""
    if not elements:
        return []
    for i in range(1, len(elements)):
        if isinstance(elements[i - 1], CurveElement) and isinstance(elements[i], CurveElement):
            return []
    pis = [PI(point=_pt(elements[0].start), radius=0.0)]
    for el in elements:
        if isinstance(el, CurveElement):
            pis.append(PI(point=_pt(el.pi), radius=float(el.radius)))
    pis.append(PI(point=_pt(elements[-1].end), radius=0.0))
    return pis


def _same_geometry(a: List[object], b: List[object], tol: float) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.kind != y.kind:
            return False
        if geo.distance(x.start, y.start) > tol or geo.distance(x.end, y.end) > tol:
            return False
        if isinstance(x, CurveElement) and geo.distance(x.center, y.center) > tol:
            return False
    return True


def junction_kind(alignment: "Alignment", i: int) -> Optional[str]:
    """Junction between element ``i`` and ``i+1``: pc | pt | pcc | prc | None."""
    els = alignment.elements
    if i < 0 or i + 1 >= len(els):
        return None
    a, b = els[i], els[i + 1]
    if isinstance(a, TangentElement) and isinstance(b, CurveElement):
        return "pc"
    if isinstance(a, CurveElement) and isinstance(b, TangentElement):
        return "pt"
    if isinstance(a, CurveElement) and isinstance(b, CurveElement):
        return "pcc" if a.direction == b.direction else "prc"
    return None


# ------------------------------------------------------------ alignment


@dataclass
class Alignment:
    """A horizontal alignment: elements in travel order plus stationing."""

    name: str
    elements: List[object]
    pis: List[PI] = field(default_factory=list)
    begin_station: float = 0.0
    equations: List[StationEquation] = field(default_factory=list)
    description: str = ""
    source: str = "pis"

    # ------------------------------------------------------- properties
    @property
    def length(self) -> float:
        if not self.elements:
            return 0.0
        last = self.elements[-1]
        return float(last.start_dist + last.length)

    @property
    def end_station(self) -> float:
        return float(self.begin_station) + self.length

    def stations(self) -> StationSystem:
        return StationSystem(self.begin_station, self.length, self.equations)

    def curves(self) -> List[CurveElement]:
        return [e for e in self.elements if isinstance(e, CurveElement)]

    def tangents(self) -> List[TangentElement]:
        return [e for e in self.elements if isinstance(e, TangentElement)]

    def curve_index(self, element_index: int) -> int:
        """1-based curve number of the curve at ``element_index``."""
        n = 0
        for i, e in enumerate(self.elements):
            if isinstance(e, CurveElement):
                n += 1
            if i == element_index:
                if not isinstance(e, CurveElement):
                    raise DesignError(f"element {element_index} is a {e.kind}, not a curve")
                return n
        raise DesignError(f"element index {element_index} out of range")

    def tangent_index(self, element_index: int) -> int:
        """1-based tangent number of the tangent at ``element_index``."""
        n = 0
        for i, e in enumerate(self.elements):
            if isinstance(e, TangentElement):
                n += 1
            if i == element_index:
                if not isinstance(e, TangentElement):
                    raise DesignError(f"element {element_index} is a {e.kind}, not a tangent")
                return n
        raise DesignError(f"element index {element_index} out of range")

    def element_ref(self, element_index: int) -> str:
        """``"T-n"`` or ``"C-n"`` for the element at ``element_index``."""
        e = self.elements[element_index]
        if isinstance(e, CurveElement):
            return f"C-{self.curve_index(element_index)}"
        return f"T-{self.tangent_index(element_index)}"

    # -------------------------------------------------------- evaluation
    def element_at(self, dist: float) -> Tuple[int, float]:
        """``(element_index, local_s)``; an exact junction picks the AHEAD element."""
        dist = float(dist)
        if not self.elements:
            raise DesignError(f"alignment {self.name} has no elements")
        last = len(self.elements) - 1
        for i, e in enumerate(self.elements):
            if i == last or dist < e.start_dist + e.length - STATION_EPS:
                s = dist - e.start_dist
                return i, min(max(s, 0.0), e.length)
        return last, self.elements[last].length  # pragma: no cover

    def _eval(self, dist: float) -> Tuple[List[float], float, int]:
        i, s = self.element_at(dist)
        e = self.elements[i]
        if isinstance(e, TangentElement):
            return _add(e.start, unit_vector(e.direction_deg), s), e.direction_deg, i
        sweep = math.degrees(s / e.radius)
        phi = e.phi0_deg + e.sign * sweep
        p = _add(e.center, unit_vector(phi), e.radius)
        return p, norm_deg(e.direction_in_deg + e.sign * sweep), i

    def point_at(self, dist: float) -> List[float]:
        """Centerline point at distance ``dist`` from BEGIN."""
        return self._eval(dist)[0]

    def direction_at(self, dist: float) -> float:
        """Heading ahead at distance ``dist`` from BEGIN."""
        return self._eval(dist)[1]

    def station_to_xy(self, station_raw: float, offset: float = 0.0) -> Tuple[List[float], float, int]:
        """``(point_with_offset, direction_deg, element_index)`` for a raw station."""
        st = self.stations()
        st.require_in_range(station_raw, self.name)
        dist = min(max(float(station_raw) - float(self.begin_station), 0.0), self.length)
        p, heading, i = self._eval(dist)
        if offset:
            p = _add(p, right_normal(heading), float(offset))
        return p, heading, i

    def xy_to_station(self, point) -> dict:
        """Perpendicular projection of ``point`` onto the alignment.

        Returns ``{"station", "offset", "on_point", "direction_deg",
        "element_index"}``; the projection with the smallest ``|offset|``
        wins, ties go to the lower station.  A tangent end that meets a
        curve is covered by the curve (so a curve center, whose only
        perpendiculars are those shared junction normals, has no station).
        """
        P = _pt(point)
        cands: List[Tuple[float, float, List[float], float, int]] = []
        n = len(self.elements)
        for i, e in enumerate(self.elements):
            if isinstance(e, TangentElement):
                u = unit_vector(e.direction_deg)
                dx, dy = P[0] - e.start[0], P[1] - e.start[1]
                s = dx * u[0] + dy * u[1]
                prev_curve = i > 0 and isinstance(self.elements[i - 1], CurveElement)
                next_curve = i + 1 < n and isinstance(self.elements[i + 1], CurveElement)
                lo_ok = s > GEOM_EPS if prev_curve else s >= -GEOM_EPS
                hi_ok = s < e.length - GEOM_EPS if next_curve else s <= e.length + GEOM_EPS
                if not (lo_ok and hi_ok):
                    continue
                s = min(max(s, 0.0), e.length)
                rn = right_normal(e.direction_deg)
                off = dx * rn[0] + dy * rn[1]
                cands.append((off, e.start_dist + s, _add(e.start, u, s), e.direction_deg, i))
            else:
                r = geo.distance(e.center, P)
                if r < GEOM_EPS:
                    continue
                phi = direction_of(e.center, P)
                sweep = norm_deg(e.sign * (phi - e.phi0_deg))
                # a sweep just short of 360 is the PC perpendicular seen from the
                # other side: accept it as s = 0 when the arc-length gap is within
                # GEOM_EPS (ANGLE_EPS alone is tighter than 1e-6-ft coordinate noise)
                if sweep >= 360.0 - ANGLE_EPS or e.radius * math.radians(360.0 - sweep) <= GEOM_EPS:
                    sweep = 0.0
                s = e.radius * math.radians(sweep)
                if s > e.length + GEOM_EPS:
                    continue
                s = min(s, e.length)
                off = (e.radius - r) * (-1.0 if e.direction == "L" else 1.0)
                on = _add(e.center, unit_vector(e.phi0_deg + e.sign * math.degrees(s / e.radius)),
                          e.radius)
                heading = norm_deg(e.direction_in_deg + e.sign * math.degrees(s / e.radius))
                cands.append((off, e.start_dist + s, on, heading, i))
        if not cands:
            st = self.stations()
            raise DesignError(
                f"point ({P[0]:.2f}, {P[1]:.2f}) does not project onto {self.name} "
                f"(stations {st.begin_text()} to {st.end_text()})",
                hint="points before BEGIN, after END, or at a curve center have no perpendicular station")
        cands.sort(key=lambda c: (round(abs(c[0]), 9), c[1]))
        off, dist, on, heading, i = cands[0]
        return {"station": float(self.begin_station) + dist, "offset": off, "on_point": on,
                "direction_deg": heading, "element_index": i}

    def bbox(self) -> Tuple[float, float, float, float]:
        """Bounding box of the centerline geometry."""
        bb = None
        for e in self.elements:
            if isinstance(e, TangentElement):
                b = geo.bbox_of_points([e.start, e.end])
            else:
                s, en = e.ccw_angles()
                b = geo.arc_bbox(e.center, e.radius, s, en)
            bb = geo.bbox_union(bb, b)
        if bb is None:
            raise DesignError(f"alignment {self.name} has no elements")
        return bb

    # ---------------------------------------------------- serialization
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "begin_station": float(self.begin_station),
            "pis": [p.to_dict() for p in self.pis],
            "equations": [q.to_dict() for q in self.equations],
            "elements": [element_to_dict(e) for e in self.elements],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Alignment":
        if not isinstance(d, dict) or not d.get("name"):
            raise DesignError("alignment needs a name")
        elements = [element_from_dict(e) for e in (d.get("elements") or [])]
        if not elements:
            raise DesignError(f"alignment {d['name']} has no elements")
        pis = [PI.from_dict(p) for p in (d.get("pis") or [])]
        equations = [StationEquation.from_dict(q) for q in (d.get("equations") or [])]
        source = d.get("source") or ("pis" if pis else "elements")
        return cls(name=str(d["name"]), elements=elements, pis=pis,
                   begin_station=float(d.get("begin_station", 0.0) or 0.0),
                   equations=equations, description=str(d.get("description") or ""),
                   source=source)


def alignment_from_elements(name: str, elements, begin_station: float = 0.0, equations=(),
                            description: str = "") -> Alignment:
    """Alignment from element geometry, with PI recovery when it reproduces
    every element endpoint within 1e-3 ft (then ``source == "pis"``)."""
    elements = list(elements)
    if not elements:
        raise DesignError(f"alignment {name} has no elements")
    align = Alignment(name=name, elements=elements, pis=[], begin_station=float(begin_station),
                      equations=list(equations or []), description=description, source="elements")
    recovered = pis_from_elements(elements)
    if recovered:
        try:
            rebuilt = compile_pis(recovered)
        except DesignError:
            rebuilt = []
        if rebuilt and _same_geometry(elements, rebuilt, 1e-3):
            align.pis = recovered
            align.source = "pis"
    return align


# ------------------------------------------------------------ data rows


def _curve_n(alignment: Alignment, n: int) -> CurveElement:
    curves = alignment.curves()
    if n < 1 or n > len(curves):
        raise DesignError(
            f"C-{n} does not exist: {alignment.name} has {len(curves)} curve"
            f"{'' if len(curves) == 1 else 's'}")
    return curves[n - 1]


def curve_data(alignment: Alignment, n: int, decimals: int = 2, dms_decimals: int = 0) -> dict:
    """Curve data row for curve ``n`` (1-based); stations raw + ``_text`` display."""
    c = _curve_n(alignment, n)
    st = alignment.stations()
    half = math.radians(c.delta_deg) / 2.0
    R = c.radius
    tangent = R * math.tan(half)
    pc_sta = float(alignment.begin_station) + c.start_dist
    pi_sta = pc_sta + tangent
    pt_sta = pc_sta + c.length
    mc_sta = pc_sta + c.length / 2.0
    chord_dir = norm_deg(c.direction_in_deg + c.sign * c.delta_deg / 2.0)
    dc = 5729.578 / R
    return {
        "alignment": alignment.name, "index": n, "ref": f"C-{n}", "direction": c.direction,
        "radius": R, "delta_deg": c.delta_deg, "delta_dms": format_dms(c.delta_deg, dms_decimals),
        "tangent": tangent, "length": c.length, "external": R * (1.0 / math.cos(half) - 1.0),
        "mid_ordinate": R * (1.0 - math.cos(half)), "chord": 2.0 * R * math.sin(half),
        "degree_of_curve_deg": dc, "degree_of_curve_dms": format_dms(dc, dms_decimals),
        "direction_in_deg": c.direction_in_deg, "direction_out_deg": c.direction_out_deg,
        "azimuth_in_deg": direction_to_azimuth(c.direction_in_deg),
        "azimuth_out_deg": direction_to_azimuth(c.direction_out_deg),
        "bearing_in": format_bearing(direction_to_azimuth(c.direction_in_deg), dms_decimals),
        "bearing_out": format_bearing(direction_to_azimuth(c.direction_out_deg), dms_decimals),
        "chord_direction_deg": chord_dir, "chord_azimuth_deg": direction_to_azimuth(chord_dir),
        "chord_bearing": format_bearing(direction_to_azimuth(chord_dir), dms_decimals),
        "pc_station": pc_sta, "pi_station": pi_sta, "pt_station": pt_sta, "mc_station": mc_sta,
        "pc_station_text": st.format(pc_sta, decimals), "pi_station_text": st.format(pi_sta, decimals),
        "pt_station_text": st.format(pt_sta, decimals), "mc_station_text": st.format(mc_sta, decimals),
        "pc": _pt(c.pc), "pi": _pt(c.pi), "pt": _pt(c.pt), "center": _pt(c.center),
    }


def tangent_data(alignment: Alignment, n: int, decimals: int = 2, dms_decimals: int = 0) -> dict:
    """Tangent data row for tangent ``n`` (1-based)."""
    tangents = alignment.tangents()
    if n < 1 or n > len(tangents):
        raise DesignError(
            f"T-{n} does not exist: {alignment.name} has {len(tangents)} tangent"
            f"{'' if len(tangents) == 1 else 's'}")
    t = tangents[n - 1]
    st = alignment.stations()
    s0 = float(alignment.begin_station) + t.start_dist
    s1 = s0 + t.length
    mid = (s0 + s1) / 2.0
    az = direction_to_azimuth(t.direction_deg)
    return {
        "alignment": alignment.name, "index": n, "ref": f"T-{n}", "start": _pt(t.start),
        "end": _pt(t.end), "length": t.length, "direction_deg": t.direction_deg,
        "azimuth_deg": az, "bearing": format_bearing(az, dms_decimals),
        "start_station": s0, "end_station": s1, "mid_station": mid,
        "start_station_text": st.format(s0, decimals), "end_station_text": st.format(s1, decimals),
        "mid_station_text": st.format(mid, decimals),
        "mid_point": _add(t.start, unit_vector(t.direction_deg), t.length / 2.0),
    }


__all__ = [
    "ELEMENT_KINDS", "GEOM_EPS", "ANGLE_EPS", "CONNECT_TOL", "PI", "TangentElement",
    "CurveElement", "Alignment", "compile_pis", "curve_from_pi", "element_from_dict",
    "element_to_dict", "elements_from_dicts", "pis_from_elements", "validate_continuity",
    "alignment_from_elements", "curve_data", "tangent_data", "junction_kind",
]
