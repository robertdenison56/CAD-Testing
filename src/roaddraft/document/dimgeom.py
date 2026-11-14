"""How a dimension is drawn: the drafting rules behind the Dimension entity.

A dimension is stored as the *measurement*, never as the linework: the points
it measures between, the arc it measures along, and the place the drafter
dragged the dimension line to. Extension lines, the dimension line,
arrowheads and the number are derived here, every time they are needed. That
is what makes a dimension a dimension rather than a picture of one — move a
measured point and the number follows, change the annotation scale and the
text and arrows re-size while the geometry stays where the survey put it.

Sizes (arrowhead, text gap, extension line offset and extension) are stored
as multiples of the text height, not as absolutes, so a dimension carries one
number a caller has to think about. ``size()`` resolves a stored override or
falls back to the ratio.

Conventions here match AutoCAD's, which is what a drafter expects:

* text sits *above* the dimension line (DIMTAD=1), reading left to right,
* arrowheads sit inside the extension lines and point outward, and flip to
  the outside pointing in when the text and arrows will not fit,
* an angular dimension measures the sweep that contains the dimension line
  point — that is how dragging picks one of the four angles between two rays,
* an arc length dimension measures counter-clockwise from ``p1`` to ``p2``,
  the same direction an Arc entity runs.

Pure geometry: this module knows about entities, and nothing about commands,
documents-on-disk, or the bus.
"""
from __future__ import annotations

import math
from typing import List, Optional

from roaddraft.core import geometry as geo
from roaddraft.core.units import format_length
from roaddraft.design.angles import DEG, format_dms
from roaddraft.document.entities import (
    DIM_ARROWS, DIM_KINDS, DIM_REQUIRED, Arc, Circle, Line, Polyline, Text,
)

#: What a dimension can measure, what its terminators can be, and what
#: geometry each kind needs -- the entity's own shape, re-exported here.
KINDS, ARROWS, REQUIRED = DIM_KINDS, DIM_ARROWS, DIM_REQUIRED

#: What the number is called on a plan, unless the caller says otherwise.
PREFIXES = {"radius": "R=", "diameter": "Ø", "arc_length": "L="}

#: Sizes as multiples of the text height (AutoCAD's DIMASZ / DIMGAP / DIMEXO /
#: DIMEXE, in the proportions a 0.10 in plan-view text uses).
RATIOS = {"arrow_size": 1.2, "text_gap": 0.5,
          "extension_offset": 0.6, "extension_beyond": 1.0}

TICK_FACTOR = 1.4   # oblique tick length as a multiple of the arrow size
DOT_FACTOR = 0.25   # dot radius as a multiple of the arrow size
LEADER_LANDING = 2.5  # radial leader shoulder, in text heights (as place_callout)
EPS = 1e-9


# ----------------------------------------------------------------- sizes


def size(dim, key: str) -> float:
    """A dimension size in space units: the stored override, or the ratio."""
    value = getattr(dim, key)
    if value is None:
        return RATIOS[key] * dim.text_height
    return float(value)


def arrow_size(dim) -> float:
    return 0.0 if dim.arrow == "none" else size(dim, "arrow_size")


# ----------------------------------------------------------- measurement


def direction_deg(dim) -> float:
    """The direction a linear/aligned dimension measures along.

    ``aligned`` runs along the two points. ``linear`` uses ``rotation_deg``
    when it is given. Otherwise: two points that are separated along one axis
    only have one dimension worth drawing, so it is drawn; and when both axes
    are in play the side the dimension line was dragged to decides, exactly as
    DIMLINEAR does -- drag it clear above or below and you measure
    horizontally, drag it out to the side and you measure vertically.
    """
    if dim.kind == "aligned":
        return _heading(dim.p1, dim.p2)
    if dim.rotation_deg is not None:
        return float(dim.rotation_deg)
    dx = abs(dim.p2[0] - dim.p1[0])
    dy = abs(dim.p2[1] - dim.p1[1])
    if dx <= EPS < dy:
        return 90.0
    if dy <= EPS < dx:
        return 0.0
    mx, my = _mid(dim.p1, dim.p2)
    drag_x, drag_y = dim.line_point[0] - mx, dim.line_point[1] - my
    return 0.0 if abs(drag_y) >= abs(drag_x) else 90.0


def angular_sweep(dim):
    """``(start_deg, end_deg, sweep_deg)`` of an angular dimension's arc.

    Of the two sweeps between the rays, this is the one the dimension line
    point falls in — dragging is how a drafter says which angle they meant.
    """
    a1 = _heading(dim.center, dim.p1)
    a2 = _heading(dim.center, dim.p2)
    al = _heading(dim.center, dim.line_point)
    ccw = (a2 - a1) % 360.0
    if (al - a1) % 360.0 <= ccw:
        return a1, a1 + ccw, ccw
    cw = (a1 - a2) % 360.0
    return a2, a2 + cw, cw


def arc_sweep(dim):
    """``(start_deg, end_deg, sweep_deg)`` of an arc length dimension —
    counter-clockwise from ``p1`` to ``p2``, the direction an Arc runs."""
    a1 = _heading(dim.center, dim.p1)
    a2 = _heading(dim.center, dim.p2)
    sweep = (a2 - a1) % 360.0
    if sweep <= EPS:
        sweep = 360.0  # p1 == p2: the whole circle
    return a1, a1 + sweep, sweep


def measure(dim) -> float:
    """The measured value: a length in space units × ``measure_scale``, or,
    for an angular dimension, an angle in degrees (never scaled)."""
    if dim.kind in ("linear", "aligned"):
        ux, uy = _unit(direction_deg(dim))
        vx, vy = dim.p2[0] - dim.p1[0], dim.p2[1] - dim.p1[1]
        return abs(vx * ux + vy * uy) * dim.measure_scale
    if dim.kind == "angular":
        return angular_sweep(dim)[2]
    if dim.kind == "radius":
        return dim.radius * dim.measure_scale
    if dim.kind == "diameter":
        return 2.0 * dim.radius * dim.measure_scale
    return dim.radius * math.radians(arc_sweep(dim)[2]) * dim.measure_scale


def text_of(dim) -> str:
    """What the dimension reads: the override, or the measurement formatted.

    An override of ``""`` suppresses the text, which is how a drafter hides
    the number on a dimension that only has to show the extent.
    """
    if dim.text_override is not None:
        return dim.text_override
    value = measure(dim)
    prefix = PREFIXES.get(dim.kind, "") if dim.prefix is None else dim.prefix
    if dim.kind == "angular":
        body = (f"{value:.{dim.precision}f}{DEG}" if dim.unit_format == "decimal"
                else format_dms(value))
    else:
        body = format_length(value, dim.unit_format, dim.precision)
    return f"{prefix}{body}{dim.suffix}"


def span(dim) -> float:
    """How much dimension line there is to fit text and arrowheads into."""
    if dim.kind not in ("linear", "aligned"):
        return float("inf")
    return geo.distance(*_dim_line_points(dim))


def fits(dim, doc) -> bool:
    """Whether the text and both arrowheads fit between the extension lines.
    False puts them outside, and is worth a warning to the caller."""
    if dim.kind not in ("linear", "aligned"):
        return True
    return span(dim) >= text_width(dim, doc, text_of(dim)) + 2.0 * arrow_size(dim)


def text_width(dim, doc, text: str) -> float:
    """Width of the dimension text in space units: its text box's."""
    if not text:
        return 0.0
    width_factor = 1.0
    if doc is not None:
        style = doc.text_styles.get(dim.style)
        if style is not None:
            width_factor = style.width_factor
    return geo.text_size(text, dim.text_height, width_factor)[0]


# ------------------------------------------------------------ primitives


def primitives(dim, doc) -> List:
    """Expand a dimension into Line/Polyline/Arc/Circle/Text primitives."""
    if dim.kind in ("linear", "aligned"):
        return _linear(dim, doc)
    if dim.kind == "angular":
        return _angular(dim, doc)
    if dim.kind in ("radius", "diameter"):
        return _radial(dim, doc)
    return _arc_length(dim, doc)


def _linear(dim, doc) -> List:
    base = _base(dim)
    rot = direction_deg(dim)
    u = _unit(rot)
    d1, d2 = _dim_line_points(dim)
    out = []
    for name, p, d in (("ext1", dim.p1, d1), ("ext2", dim.p2, d2)):
        line = _extension(dim, base, name, p, d)
        if line is not None:
            out.append(line)
    out.append(Line(id=f"{dim.id}:line", start=list(d1), end=list(d2), **base))

    text = text_of(dim)
    width = text_width(dim, doc, text)
    asz = arrow_size(dim)
    gap = size(dim, "text_gap")
    span = geo.distance(d1, d2)
    if span >= width + 2.0 * asz:                      # arrows and text inside
        out += _arrows(dim, base, 1, d1, d2)
        out += _arrows(dim, base, 2, d2, d1)
        anchor = _mid(d1, d2)
    else:                                              # flip both outside
        o1 = _unit(_heading(d2, d1)) if span > EPS else (-u[0], -u[1])
        o2 = (-o1[0], -o1[1])
        lead = 2.0 * asz + (gap + width if text else 0.0)
        for name, d, o, run in (("stub1", d1, o1, 2.0 * asz),
                                ("stub2", d2, o2, lead)):
            if run > EPS:  # no arrowheads and no text leaves nothing to run to
                out.append(Line(id=f"{dim.id}:{name}", start=list(d),
                                end=_step(d, o, run), **base))
        out += _arrows(dim, base, 1, d1, _step(d1, o1, max(asz, EPS)))
        out += _arrows(dim, base, 2, d2, _step(d2, o2, max(asz, EPS)))
        anchor = _step(d2, o2, 2.0 * asz + gap + width / 2.0)
    if text:
        t_rot = _reads(dim, rot)
        nx, ny = _unit(t_rot + 90.0)
        out.append(Text(id=f"{dim.id}:text", position=[anchor[0] + nx * gap,
                                                       anchor[1] + ny * gap],
                        content=text, height=dim.text_height, style=dim.style,
                        rotation_deg=t_rot, halign="center", valign="bottom", **base))
    return out


def _angular(dim, doc) -> List:
    base = _base(dim)
    c = dim.center
    radius = geo.distance(c, dim.line_point)
    a1, a2, sweep = angular_sweep(dim)
    out = []
    for name, p in (("ext1", dim.p1), ("ext2", dim.p2)):
        line = _radial_extension(dim, base, name, c, geo.distance(c, p), radius,
                                 _heading(c, p))
        if line is not None:
            out.append(line)
    out += _dim_arc(dim, base, c, radius, a1, a2)
    out += _arc_text(dim, doc, base, c, radius, a1 + sweep / 2.0)
    return out


def _arc_length(dim, doc) -> List:
    base = _base(dim)
    c = dim.center
    radius = geo.distance(c, dim.line_point)
    a1, a2, sweep = arc_sweep(dim)
    out = []
    for name, ang in (("ext1", a1), ("ext2", a2)):
        line = _radial_extension(dim, base, name, c, dim.radius, radius, ang)
        if line is not None:
            out.append(line)
    out += _dim_arc(dim, base, c, radius, a1, a2)
    out += _arc_text(dim, doc, base, c, radius, a1 + sweep / 2.0)
    return out


def _radial(dim, doc) -> List:
    """A radius or diameter dimension: across the circle when the text sits
    inside it, an external leader — the callout's geometry — when outside."""
    base = _base(dim)
    c, r = dim.center, dim.radius
    tip = dim.p1
    far = [2.0 * c[0] - tip[0], 2.0 * c[1] - tip[1]]   # diameter's other end
    text = text_of(dim)
    gap = size(dim, "text_gap")
    out = []
    if geo.distance(c, dim.line_point) <= r:                   # text inside
        tail = far if dim.kind == "diameter" else list(c)
        out.append(Line(id=f"{dim.id}:line", start=list(tail), end=list(tip), **base))
        out += _arrows(dim, base, 1, tip, tail)
        if dim.kind == "diameter":
            out += _arrows(dim, base, 2, far, tip)
        rot = _reads(dim, _heading(tail, tip))
        nx, ny = _unit(rot + 90.0)
        anchor = _project(dim.line_point, tail, tip)
        if text:
            out.append(Text(id=f"{dim.id}:text",
                            position=[anchor[0] + nx * gap, anchor[1] + ny * gap],
                            content=text, height=dim.text_height, style=dim.style,
                            rotation_deg=rot, halign="center", valign="bottom", **base))
        return out
    landing = LEADER_LANDING * dim.text_height
    twist = _twist(dim)
    if not twist:
        from_left = tip[0] <= dim.line_point[0]
        elbow = [dim.line_point[0] + (-landing if from_left else landing),
                 dim.line_point[1]]
        level = 0.0
    else:  # the landing and the text run level on the sheet, not in the model
        level = _fold(-twist)
        hx, hy = _unit(level)
        from_left = ((tip[0] - dim.line_point[0]) * hx
                     + (tip[1] - dim.line_point[1]) * hy) <= 0.0
        elbow = _step(dim.line_point, (hx, hy), -landing if from_left else landing)
    out.append(Line(id=f"{dim.id}:line", start=list(tip), end=elbow, **base))
    if landing > 0:
        out.append(Line(id=f"{dim.id}:landing", start=elbow,
                        end=list(dim.line_point), **base))
    out += _arrows(dim, base, 1, tip, elbow)
    if text:
        out.append(Text(id=f"{dim.id}:text", position=list(dim.line_point),
                        content=text, height=dim.text_height, style=dim.style,
                        rotation_deg=level, halign="left" if from_left else "right",
                        valign="middle", **base))
    return out


# -------------------------------------------------------------- fragments


def _dim_arc(dim, base, center, radius, a1, a2) -> List:
    """The arc a dimension measures along, with an arrowhead at each end
    pointing outward along it."""
    out = [Arc(id=f"{dim.id}:arc", center=list(center), radius=max(radius, EPS),
               start_angle_deg=a1, end_angle_deg=a2, **base)]
    asz = arrow_size(dim)
    if asz > 0 and radius > EPS:
        step = math.degrees(asz / radius)
        out += _arrows(dim, base, 1, geo.arc_point(center, radius, a1),
                       geo.arc_point(center, radius, a1 + step))
        out += _arrows(dim, base, 2, geo.arc_point(center, radius, a2),
                       geo.arc_point(center, radius, a2 - step))
    return out


def _arc_text(dim, doc, base, center, radius, mid_deg) -> List:
    """Text on the outside of a dimension arc, tangent and upright."""
    text = text_of(dim)
    if not text:
        return []
    gap = size(dim, "text_gap")
    rot = _reads(dim, mid_deg + 90.0)
    ux, uy = _unit(mid_deg)                       # outward, away from center
    nx, ny = _unit(rot + 90.0)                    # the text's own "up"
    valign = "bottom" if (nx * ux + ny * uy) >= 0 else "top"
    return [Text(id=f"{dim.id}:text",
                 position=geo.arc_point(center, radius + gap, mid_deg),
                 content=text, height=dim.text_height, style=dim.style,
                 rotation_deg=rot, halign="center", valign=valign, **base)]


def _arrows(dim, base, index: int, tip, tail) -> List:
    """A terminator at ``tip``, pointing away from ``tail``."""
    asz = arrow_size(dim)
    if asz <= 0:
        return []
    eid = f"{dim.id}:arrow{index}"
    if dim.arrow == "dot":
        return [Circle(id=eid, center=list(tip), radius=asz * DOT_FACTOR, **base)]
    if dim.arrow == "tick":
        ux, uy = _unit(_heading(tail, tip) + 45.0)
        half = asz * TICK_FACTOR / 2.0
        return [Line(id=eid, start=[tip[0] - ux * half, tip[1] - uy * half],
                     end=[tip[0] + ux * half, tip[1] + uy * half], **base)]
    return [Polyline(id=eid, vertices=geo.arrow_head(tip, tail, asz),
                     closed=True, **base)]


def _extension(dim, base, name, p, d) -> Optional[Line]:
    """An extension line from near the measured point ``p`` to just past the
    dimension line at ``d`` — omitted when the point is already on the line."""
    dx, dy = d[0] - p[0], d[1] - p[1]
    length = math.hypot(dx, dy)
    offset = size(dim, "extension_offset")
    if length <= offset + EPS:
        return None
    ux, uy = dx / length, dy / length
    beyond = size(dim, "extension_beyond")
    return Line(id=f"{dim.id}:{name}",
                start=[p[0] + ux * offset, p[1] + uy * offset],
                end=[d[0] + ux * beyond, d[1] + uy * beyond], **base)


def _radial_extension(dim, base, name, center, from_r, to_r, ang) -> Optional[Line]:
    """An extension line running radially from ``from_r`` out (or in) to the
    dimension arc at ``to_r``."""
    offset = size(dim, "extension_offset")
    if abs(to_r - from_r) <= offset + EPS:
        return None
    sign = 1.0 if to_r > from_r else -1.0
    beyond = size(dim, "extension_beyond")
    return Line(id=f"{dim.id}:{name}",
                start=geo.arc_point(center, from_r + sign * offset, ang),
                end=geo.arc_point(center, to_r + sign * beyond, ang), **base)


# ---------------------------------------------------------------- helpers


def _base(dim) -> dict:
    return {"layer": dim.layer, "color": dim.color, "linetype": dim.linetype}


def _twist(dim) -> float:
    """The twist of the viewport the dimension is read through (0: none)."""
    return float(getattr(dim, "view_rotation", None) or 0.0)


def _fold(angle_deg: float) -> float:
    """An angle in (-180, 180]."""
    a = (float(angle_deg) + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def _reads(dim, angle_deg: float) -> float:
    """The rotation of text set along ``angle_deg`` so that it reads upright:
    in the model, or, for a dimension lettered for a twisted viewport, on the
    sheet that shows it (the model rotation is then the paper one turned back
    by the twist, as ``design.labels.label_pose`` does for a label)."""
    twist = _twist(dim)
    if not twist:
        return geo.upright(angle_deg)
    return _fold(geo.upright(angle_deg + twist) - twist)


def _dim_line_points(dim):
    """Where the measured points land on the dimension line."""
    ux, uy = _unit(direction_deg(dim))
    lx, ly = dim.line_point

    def on_line(p):
        t = (p[0] - lx) * ux + (p[1] - ly) * uy
        return [lx + ux * t, ly + uy * t]

    return on_line(dim.p1), on_line(dim.p2)


def _project(p, a, b):
    """``p`` projected onto the infinite line a-b (a when a == b)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    len2 = dx * dx + dy * dy
    if len2 <= EPS:
        return list(a)
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2
    return [a[0] + dx * t, a[1] + dy * t]


def _unit(angle_deg):
    a = math.radians(angle_deg)
    return math.cos(a), math.sin(a)


def _step(p, u, dist):
    return [p[0] + u[0] * dist, p[1] + u[1] * dist]


def _mid(a, b):
    return [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]


def _heading(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


__all__ = ["KINDS", "ARROWS", "REQUIRED", "PREFIXES", "RATIOS", "size", "arrow_size",
           "direction_deg", "angular_sweep", "arc_sweep", "measure", "text_of", "span",
           "fits",
           "text_width", "primitives"]
