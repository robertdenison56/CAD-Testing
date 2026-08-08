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
