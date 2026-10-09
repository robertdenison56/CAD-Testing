"""2D geometry helpers: points, bounding boxes, arcs, text extents, and the
viewport (model -> paper) similarity transform.

Points are [x, y] lists (JSON-native). Angles are degrees, counter-clockwise
from +X, matching DXF conventions. Bounding boxes are (minx, miny, maxx, maxy).
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------- point ops


def rotate_point(p, angle_deg, origin=(0.0, 0.0)):
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y = p[0] - origin[0], p[1] - origin[1]
    return [origin[0] + x * c - y * s, origin[1] + x * s + y * c]


def translate_point(p, delta):
    return [p[0] + delta[0], p[1] + delta[1]]


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def dist_point_to_segment(p, a, b):
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = p[0] - a[0], p[1] - a[1]
    len2 = abx * abx + aby * aby
    if len2 <= 1e-18:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / len2))
    return math.hypot(apx - t * abx, apy - t * aby)


def dist_point_to_bbox(p, bb):
    dx = max(bb[0] - p[0], 0.0, p[0] - bb[2])
    dy = max(bb[1] - p[1], 0.0, p[1] - bb[3])
    return math.hypot(dx, dy)


# ------------------------------------------------------------ bounding boxes


def bbox_of_points(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def bbox_expand(bb, margin):
    return (bb[0] - margin, bb[1] - margin, bb[2] + margin, bb[3] + margin)


def bbox_intersects(a, b, tol=0.0):
    return not (a[2] < b[0] - tol or b[2] < a[0] - tol or a[3] < b[1] - tol or b[3] < a[1] - tol)


def bbox_contains(outer, inner, tol=1e-9):
    return (
        inner[0] >= outer[0] - tol
        and inner[1] >= outer[1] - tol
        and inner[2] <= outer[2] + tol
        and inner[3] <= outer[3] + tol
    )


# ------------------------------------------------------------------- arcs


def arc_sweep(start_deg, end_deg):
    """Normalize a CCW arc to (start, end) with start in [0, 360) and end > start."""
    s = start_deg % 360.0
    e = end_deg % 360.0
    if e <= s:
        e += 360.0
    return s, e


def arc_point(center, radius, angle_deg):
    a = math.radians(angle_deg)
    return [center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)]


def arc_bbox(center, radius, start_deg, end_deg):
    s, e = arc_sweep(start_deg, end_deg)
    pts = [arc_point(center, radius, s), arc_point(center, radius, e)]
    q = math.ceil(s / 90.0) * 90.0
    while q <= e:
        pts.append(arc_point(center, radius, q))
        q += 90.0
    return bbox_of_points(pts)


# ------------------------------------------------------------------- bulges
# A polyline segment may be a circular arc, stored the DXF way as a *bulge*:
# tan(sweep / 4), where sweep is the arc's central angle from the segment's
# start vertex to its end vertex, positive counter-clockwise. 0 is straight,
# 1 a half circle; the sign says which way it bows (positive: to the right of
# the chord, travelling start to end).


def bulge_of_sweep(sweep_deg):
    """The bulge of an arc segment with signed central angle ``sweep_deg``."""
    return math.tan(math.radians(sweep_deg) / 4.0)


def bulge_arc(a, b, bulge):
    """``(center, radius, start_angle_deg, sweep_deg)`` of the arc segment
    from ``a`` to ``b`` with ``bulge``; None when it is straight (or has no
    chord to bow)."""
    chord = distance(a, b)
    if abs(bulge) < 1e-12 or chord < 1e-12:
        return None
    ux, uy = (b[0] - a[0]) / chord, (b[1] - a[1]) / chord
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    k = chord * (1.0 - bulge * bulge) / (4.0 * bulge)  # signed, along the left normal
    center = [mx - uy * k, my + ux * k]
    radius = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
    start = math.degrees(math.atan2(a[1] - center[1], a[0] - center[0]))
    sweep = math.degrees(4.0 * math.atan(bulge))
    return center, radius, start, sweep


def bulge_points(a, b, bulge, step_deg=4.0):
    """Points along a polyline segment from ``a`` to ``b`` (both included):
    the two ends when straight, else the arc sampled every ``step_deg``."""
    arc = bulge_arc(a, b, bulge)
    if arc is None:
        return [list(a), list(b)]
    center, radius, start, sweep = arc
    n = max(2, int(math.ceil(abs(sweep) / step_deg)))
    pts = [list(a)]
    for i in range(1, n):
        pts.append(arc_point(center, radius, start + sweep * i / n))
    pts.append(list(b))
    return pts


def bulge_bbox(a, b, bulge):
    """Bounding box of one polyline segment, arc or straight."""
    arc = bulge_arc(a, b, bulge)
    if arc is None:
        return bbox_of_points([a, b])
    center, radius, start, sweep = arc
    lo, hi = (start, start + sweep) if sweep >= 0 else (start + sweep, start)
    return arc_bbox(center, radius, lo, hi)


def dist_point_to_arc(p, center, radius, start_deg, sweep_deg):
    """Distance from ``p`` to the arc from ``start_deg`` sweeping
    ``sweep_deg`` (signed) about ``center``."""
    lo, hi = (start_deg, start_deg + sweep_deg) if sweep_deg >= 0 \
        else (start_deg + sweep_deg, start_deg)
    s, e = arc_sweep(lo, hi) if abs(hi - lo) < 360.0 - 1e-12 else (0.0, 360.0)
    ang = math.degrees(math.atan2(p[1] - center[1], p[0] - center[0])) % 360.0
    if s <= ang <= e or s <= ang + 360.0 <= e:
        return abs(distance(p, center) - radius)
    return min(distance(p, arc_point(center, radius, s)),
               distance(p, arc_point(center, radius, e)))


def upright(angle_deg):
    """Fold a rotation into (-90, 90] so text never reads upside down."""
    a = angle_deg % 360.0
    if 90.0 < a <= 270.0:
        a -= 180.0
    return ((a + 180.0) % 360.0) - 180.0


def reading_up(angle_deg):
    """Fold a rotation into (-45, 135] for text set square to a line.

    Caltrans letters BC and EC stations, and match lines, along the
    perpendicular and reading bottom to top (PPM 2-1.2). ``upright`` would
    turn every one of them whose line climbs to the right on the sheet so it
    reads top to bottom. Here text stays bottom-to-top until it leans more
    than 45 degrees past vertical; beyond that it reads left to right instead
    of nearly upside down."""
    a = angle_deg % 360.0
    if 135.0 < a <= 315.0:
        a -= 180.0
    return ((a + 180.0) % 360.0) - 180.0


# --------------------------------------------------------------- arrowheads

ARROW_HALF_RATIO = 0.18  # half-width of an arrowhead as a fraction of its length


def arrow_head(tip, tail, size, half_ratio=ARROW_HALF_RATIO):
    """Vertices of a closed triangle at ``tip``, pointing away from ``tail``."""
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        ux, uy = 1.0, 0.0
    else:
        ux, uy = dx / length, dy / length
    base = [tip[0] - ux * size, tip[1] - uy * size]
    half = size * half_ratio
    return [list(tip), [base[0] - uy * half, base[1] + ux * half],
            [base[0] + uy * half, base[1] - ux * half]]


def line_intersection(a, b, c, d):
    """Intersection of the infinite lines a-b and c-d, or None when parallel."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / denom
    return [a[0] + r[0] * t, a[1] + r[1] * t]


# ------------------------------------------------------------------- text

TEXT_WIDTH_RATIO = 0.7  # estimated glyph width as a fraction of text height
TEXT_LINE_SPACING = 1.6  # line spacing as a fraction of text height


def text_bbox(position, content, height, rotation_deg=0.0, halign="left",
              valign="bottom", width_factor=1.0):
    """Estimated axis-aligned bounding box for a text entity."""
    lines = content.split("\n") or [""]
    n = max(len(line) for line in lines)
    w = max(n, 1) * height * TEXT_WIDTH_RATIO * width_factor
    h = height + (len(lines) - 1) * height * TEXT_LINE_SPACING

    if halign == "center":
        x0 = -w / 2.0
    elif halign == "right":
        x0 = -w
    else:
        x0 = 0.0
    if valign == "middle":
        y0 = -h / 2.0
    elif valign == "top":
        y0 = -h
    else:
        y0 = 0.0

    corners = [
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h],
    ]
    corners = [translate_point(rotate_point(c, rotation_deg), position) for c in corners]
    return bbox_of_points(corners)


# --------------------------------------------------------- viewport transform


class ViewportTransform:
    """Similarity transform between model space (feet) and sheet paper space
    (inches) for one viewport.

    paper = center_paper + R(rotation) @ ((model - model_center) / feet_per_inch)

    rotation_deg is the view twist: the angle by which model geometry appears
    rotated CCW on the sheet.
    """

    def __init__(self, center_paper, model_center, feet_per_inch, rotation_deg=0.0):
        self.center_paper = [float(center_paper[0]), float(center_paper[1])]
        self.model_center = [float(model_center[0]), float(model_center[1])]
        self.feet_per_inch = float(feet_per_inch)
        self.rotation_deg = float(rotation_deg)

    @property
    def scale(self) -> float:
        """Inches of paper per foot of model."""
        return 1.0 / self.feet_per_inch

    def to_paper(self, p):
        d = [(p[0] - self.model_center[0]) * self.scale,
             (p[1] - self.model_center[1]) * self.scale]
        d = rotate_point(d, self.rotation_deg)
        return [self.center_paper[0] + d[0], self.center_paper[1] + d[1]]

    def to_model(self, q):
        d = [q[0] - self.center_paper[0], q[1] - self.center_paper[1]]
        d = rotate_point(d, -self.rotation_deg)
        return [self.model_center[0] + d[0] * self.feet_per_inch,
                self.model_center[1] + d[1] * self.feet_per_inch]

    def visible_model_bbox(self, width_in, height_in):
        """Model-space AABB covered by a paper rect width_in x height_in
        centered on this viewport."""
        cx, cy = self.center_paper
        corners = [
            [cx - width_in / 2, cy - height_in / 2],
            [cx + width_in / 2, cy - height_in / 2],
            [cx + width_in / 2, cy + height_in / 2],
            [cx - width_in / 2, cy + height_in / 2],
        ]
        return bbox_of_points([self.to_model(c) for c in corners])


# --------------------------------------------------------------- polygons
# Used by reference clip boundaries / masks (document/clip.py). Polygons are
# lists of [x, y] points, implicitly closed; orientation does not matter.


def polygon_edges(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def point_in_polygon(p, poly, tol=1e-9) -> bool:
    """Even-odd (ray casting) point-in-polygon test. Points on an edge count
    as inside."""
    x, y = p[0], p[1]
    inside = False
    for a, b in polygon_edges(poly):
        if dist_point_to_segment(p, a, b) <= tol:
            return True
        if (a[1] > y) != (b[1] > y):
            xi = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if xi > x:
                inside = not inside
    return inside


def segment_intersection_params(a, b, c, d):
    """(t, u) with a + t(b - a) == c + u(d - c), or None if parallel."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) <= 1e-15:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    return (qx * sy - qy * sx) / den, (qx * ry - qy * rx) / den


def segment_polygon_params(a, b, poly, eps=1e-9):
    """Sorted parameters t strictly inside (0, 1) where segment ab crosses an
    edge of the polygon."""
    ts = []
    for c, d in polygon_edges(poly):
        r = segment_intersection_params(a, b, c, d)
        if r is None:
            continue
        t, u = r
        if -eps <= u <= 1.0 + eps and eps < t < 1.0 - eps:
            ts.append(t)
    return sorted(ts)


def circle_segment_angles(center, radius, c, d, eps=1e-9):
    """Angles (degrees in [0, 360)) where a circle meets segment cd."""
    dx, dy = d[0] - c[0], d[1] - c[1]
    fx, fy = c[0] - center[0], c[1] - center[1]
    qa = dx * dx + dy * dy
    if qa <= 1e-18:
        return []
    qb = 2.0 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - radius * radius
    disc = qb * qb - 4.0 * qa * qc
    if disc < 0.0:
        return []
    root = math.sqrt(disc)
    out = []
    for u in ((-qb - root) / (2.0 * qa), (-qb + root) / (2.0 * qa)):
        if -eps <= u <= 1.0 + eps:
            px, py = c[0] + u * dx, c[1] + u * dy
            out.append(math.degrees(math.atan2(py - center[1], px - center[0])) % 360.0)
    return out


def circle_polygon_angles(center, radius, poly):
    """Sorted angles (degrees) where a circle crosses the polygon's edges."""
    out = []
    for c, d in polygon_edges(poly):
        out.extend(circle_segment_angles(center, radius, c, d))
    return sorted(out)
