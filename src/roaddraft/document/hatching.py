"""Hatch patterns: the families of lines an AutoCAD pattern is made of, laid
across a boundary.

A pattern (from acad.pat) is one or more families of parallel lines. Each
family has an angle, an origin, the offset from one line to the next and,
optionally, a dash pattern -- dashes positive, gaps negative, dots zero --
that starts at the line's own origin. SOLID has no lines at all: it fills.
The definitions are AutoCAD's own (imperial, as shipped with ezdxf), so a
hatch exported to DXF plots in Civil 3D or MicroStation exactly as it renders
here.

Scale works the AutoCAD way: pattern units times ``scale`` are drawing units.
ANSI31's lines are 0.125 apart, so in model space at 1" = 50' a scale of 50
spaces them 6.25 ft -- an eighth of an inch on the plot.
"""
from __future__ import annotations

import difflib
import math
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

#: Patterns a roadway plan reaches for, with what they usually mean there.
ROADWAY_PATTERNS = {
    "SOLID": "solid fill (a legend swatch, a screened area with opacity)",
    "ANSI31": "diagonal lines -- removal, new pavement, a cut section",
    "ANSI37": "diagonal crosshatch -- pavement to be removed, overlay",
    "AR-CONC": "concrete -- sidewalk, curb ramp, PCC pavement",
    "AR-SAND": "stipple -- AC dike, sand, aggregate base",
    "GRAVEL": "gravel -- aggregate shoulder, rock slope protection",
    "DOTS": "dots -- landscaping, decomposed granite",
    "EARTH": "earth -- embankment, native ground",
    "NET": "square grid -- grated areas, pavers",
    "LINE": "horizontal lines",
    "BRICK": "brick -- pavers, masonry",
    "SWAMP": "marsh -- wetlands",
    "GRASS": "grass -- turf, erosion control",
}

#: The most dash segments one hatch draws before it reports "too dense".
MAX_SEGMENTS = 60000


@lru_cache(maxsize=1)
def _library() -> Dict[str, list]:
    from ezdxf.tools import pattern
    return {name.upper(): lines for name, lines in pattern.load(measurement=0).items()}


def pattern_names() -> List[str]:
    return sorted(_library())


def canonical_pattern(name) -> str:
    """The upper-case name of a known pattern. Raises ValueError with the
    nearest names for anything else."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"pattern must be a pattern name, got {name!r}")
    key = name.strip().upper()
    if key == "SOLID" or key in _library():
        return key
    close = difflib.get_close_matches(key, pattern_names(), n=4)
    raise ValueError(f"unknown hatch pattern {name!r}" +
                     (f"; did you mean {', '.join(close)}?" if close else "") +
                     f" Roadway patterns: {', '.join(ROADWAY_PATTERNS)}")


def definition(name: str) -> list:
    """The pattern's line families ``[angle, base, offset, dashes]``,
    pattern units (offsets are world vectors, as DXF stores them)."""
    return _library().get(name.upper(), [])


def spacing(name: str, scale: float) -> float:
    """The smallest distance between the lines of a pattern at a scale."""
    best = math.inf
    for angle, _base, offset, _dashes in definition(name):
        a = math.radians(angle)
        perp = abs(-offset[0] * math.sin(a) + offset[1] * math.cos(a))
        if perp > 1e-12:
            best = min(best, perp * scale)
    return best


def _edges(polygons: Sequence[Sequence[Sequence[float]]]):
    out = []
    for poly in polygons:
        n = len(poly)
        for i in range(n):
            out.append((poly[i], poly[(i + 1) % n]))
    return out


def pattern_segments(polygons, pattern: str, scale: float, angle_deg: float,
                     max_segments: int = MAX_SEGMENTS
                     ) -> Tuple[List[Tuple[List[float], List[float]]], bool]:
    """The dashes of a pattern inside the area the polygons bound (even-odd),
    as ``([start, end], ...)`` -- a dot is a segment with no length -- and
    whether the pattern was too dense and stopped at ``max_segments``."""
    lines = definition(pattern)
    if not lines or not polygons:
        return [], False
    edges = _edges(polygons)
    xs = [p[0] for poly in polygons for p in poly]
    ys = [p[1] for poly in polygons for p in poly]
    if not xs:
        return [], False
    rot = math.radians(angle_deg)
    cr, sr = math.cos(rot), math.sin(rot)

    def turn(v):
        return (v[0] * cr - v[1] * sr, v[0] * sr + v[1] * cr)

    out: List[Tuple[List[float], List[float]]] = []
    for angle, base, offset, dashes in lines:
        a = math.radians(angle) + rot
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        bx, by = turn((base[0] * scale, base[1] * scale))
        ox, oy = turn((offset[0] * scale, offset[1] * scale))
        step = ox * nx + oy * ny  # perpendicular distance between lines
        if abs(step) < 1e-12:
            continue
        base_n = bx * nx + by * ny
        ns = [x * nx + y * ny for x, y in zip(xs, ys)]
        k_lo = math.ceil((min(ns) - base_n) / step) if step > 0 else \
            math.ceil((max(ns) - base_n) / step)
        k_hi = math.floor((max(ns) - base_n) / step) if step > 0 else \
            math.floor((min(ns) - base_n) / step)
        if k_hi < k_lo:
            continue
        crossings: Dict[int, List[float]] = {}
        for p, q in edges:
            pn, qn = p[0] * nx + p[1] * ny, q[0] * nx + q[1] * ny
            if abs(qn - pn) < 1e-15:
                continue
            lo_n, hi_n = (pn, qn) if pn < qn else (qn, pn)
            ka = math.ceil((lo_n - base_n) / step) if step > 0 else \
                math.ceil((hi_n - base_n) / step)
            kb = math.floor((hi_n - base_n) / step) if step > 0 else \
                math.floor((lo_n - base_n) / step)
            for k in range(min(ka, kb) - 1, max(ka, kb) + 2):
                line_n = base_n + k * step
                if not (lo_n <= line_n < hi_n):  # half-open: a vertex counts once
                    continue
                w = (line_n - pn) / (qn - pn)
                x, y = p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w
                crossings.setdefault(k, []).append(x * ux + y * uy)
        period = sum(abs(d) for d in dashes)
        for k, ts in crossings.items():
            ts.sort()
            origin = (bx + k * ox) * ux + (by + k * oy) * uy  # along-line origin
            px, py = (bx + k * ox) - origin * ux, (by + k * oy) - origin * uy

            def at(t):
                return [px + ux * t, py + uy * t]

            for i in range(0, len(ts) - 1, 2):
                t0, t1 = ts[i], ts[i + 1]
                if t1 - t0 <= 1e-12:
                    continue
                if not dashes or period <= 1e-12:
                    out.append((at(t0), at(t1)))
                else:
                    first = math.floor((t0 - origin) / period)
                    last = math.floor((t1 - origin) / period)
                    for m in range(first, last + 1):
                        start = origin + m * period
                        for d in dashes:
                            length = abs(d)
                            if d > 0:
                                a0, a1 = max(start, t0), min(start + length, t1)
                                if a1 > a0:
                                    out.append((at(a0), at(a1)))
                            elif d == 0 and t0 <= start <= t1:
                                out.append((at(start), at(start)))
                            start += length
                        if len(out) > max_segments:
                            return out[:max_segments], True
                if len(out) > max_segments:
                    return out[:max_segments], True
    return out, False


__all__ = ["ROADWAY_PATTERNS", "MAX_SEGMENTS", "pattern_names", "canonical_pattern",
           "definition", "spacing", "pattern_segments"]
