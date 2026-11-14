"""Drawable entities. Every entity serializes to/from plain JSON dicts so the
full document state can be handed to an AI agent verbatim.

Entities carry a layer plus optional color/linetype overrides (None = ByLayer),
matching AutoCAD property semantics. Compound entities (BlockRef, Table) can be
expanded into primitives for rendering, export, and bounding boxes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from roaddraft.core import geometry as geo
from roaddraft.core.units import LENGTH_FORMATS

HALIGN = ("left", "center", "right")
VALIGN = ("bottom", "middle", "top")

MAX_BLOCK_DEPTH = 5


def as_point(value):
    """Validate and coerce a [x, y] point. Raises ValueError on anything else
    (including strings, which iterate as characters) so a bad modify_entity
    payload becomes a teaching fault instead of stored corruption."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"expected a point [x, y], got {value!r}")
    return [float(value[0]), float(value[1])]


def as_positive(value, name):
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _in_enum(value, allowed, name):
    if value not in allowed:
        raise ValueError(f"{name} must be one of {list(allowed)}, "
                         f"got {value!r}")
    return value


def _as_size(value, name):
    """A dimension size override: a positive length, in space units."""
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive (or null for the default), "
                         f"got {value}")
    return value


def _as_precision(value):
    value = int(value)
    if not 0 <= value <= 6:
        raise ValueError(f"precision must be 0 to 6 decimals, got {value}")
    return value


def _as_nonzero(value, name):
    value = float(value)
    if value == 0:
        raise ValueError(f"{name} must not be zero")
    return value


ANCHOR_REQUIRED = ("alignment", "ref", "kind")
#: a callout's record: its text (``callout``) and the leader, shoulder and arrowhead
#: drawn with it (``callout_leader``). A callout aimed at a point or an entity names
#: no alignment, so these kinds alone may leave ``alignment`` (and ``ref``) empty.
CALLOUT_KINDS = ("callout", "callout_leader")
ANCHOR_SIDES = ("left", "right")
ANCHOR_ROTATIONS = ("along", "perpendicular", "horizontal")


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


ANNOTATIVE_SIZES = ("height_in", "half_len_in", "offset_in")


def as_annotative(value) -> Optional[Dict]:
    """Validate an ``annotative`` record: {"scale": ft/in (> 0), optional
    "height_in" / "half_len_in" (> 0), "offset_in" (any number)} — the paper
    sizes set_annotation_scale re-sizes the entity from.

    ``offset_in`` is signed like an anchor's label_offset: a negative one is a
    label on the other side of the line from its anchor's side.  Stationing
    lettered on the right was saved that way before annotate_stationing
    recorded it as side right, and those files still open."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"annotative: expected an object, got {value!r}")
    if not _is_number(value.get("scale")) or value["scale"] <= 0:
        raise ValueError(f"annotative: scale must be a positive number (feet per inch), "
                         f"got {value.get('scale')!r}")
    out = {"scale": float(value["scale"])}
    for key, v in value.items():
        if key == "scale":
            continue
        if key not in ANNOTATIVE_SIZES:
            raise ValueError(f"annotative: unknown key {key!r}; keys: scale, "
                             + ", ".join(ANNOTATIVE_SIZES))
        if key == "offset_in":
            if not _is_number(v) or not math.isfinite(v):
                raise ValueError(f"annotative: offset_in must be a number (inches), got {v!r}")
        elif not _is_number(v) or v <= 0:
            raise ValueError(f"annotative: {key} must be a positive number (inches), got {v!r}")
        out[key] = float(v)
    return out


def as_anchor(value) -> Optional[Dict]:
    """Validate an anchor record (provenance of a design-anchored entity).

    Returns None for None, otherwise a plain dict copy. Required string keys:
    alignment, ref, kind. Optional keys: station/offset/label_offset/
    view_rotation (number or None), side (left|right|None), rotation (along|perpendicular|
    horizontal|None), viewport (str|None), content_auto (bool), placed_by
    (str|None). Anything else raises ValueError('anchor: ...').

    ``placed_by`` is provenance: the command bus stamps it with the name of
    the command that created the entity, and nothing else writes it (see
    CommandBus._stamp_provenance). An anchor a caller attached to an entity
    by hand therefore carries none, which is what lets a verifier tell a
    drafted label from a decorated one."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"anchor: expected an object, got {value!r}")
    out = {}
    callout = value.get("kind") in CALLOUT_KINDS
    for key in ANCHOR_REQUIRED:
        v = value.get(key)
        if callout and key != "kind" and (v is None or v == ""):
            out[key] = ""  # a callout aimed at a point or an entity names no alignment
            continue
        if not isinstance(v, str) or not v:
            raise ValueError(f"anchor: {key} must be a non-empty string, got {v!r}")
        out[key] = v
    for key, v in value.items():
        if key in ANCHOR_REQUIRED:
            continue
        if key == "tip":
            if not callout:
                raise ValueError("anchor: tip belongs to a callout record only")
            if (not isinstance(v, (list, tuple)) or len(v) != 2
                    or not all(_is_number(c) for c in v)):
                raise ValueError(f"anchor: tip must be [x, y], got {v!r}")
            out[key] = [float(v[0]), float(v[1])]
        elif key in ("station", "offset", "label_offset", "view_rotation"):
            if v is not None and not _is_number(v):
                raise ValueError(f"anchor: {key} must be a number or null, got {v!r}")
            out[key] = None if v is None else float(v)
        elif key == "side":
            if v is not None and v not in ANCHOR_SIDES:
                raise ValueError(f"anchor: side must be one of {list(ANCHOR_SIDES)} or "
                                 f"null, got {v!r}")
            out[key] = v
        elif key == "rotation":
            if v is not None and v not in ANCHOR_ROTATIONS:
                raise ValueError(f"anchor: rotation must be one of "
                                 f"{list(ANCHOR_ROTATIONS)} or null, got {v!r}")
            out[key] = v
        elif key == "viewport":
            if v is not None and not isinstance(v, str):
                raise ValueError(f"anchor: viewport must be a string or null, got {v!r}")
            out[key] = v
        elif key == "content_auto":
            if not isinstance(v, bool):
                raise ValueError(f"anchor: content_auto must be true/false, got {v!r}")
            out[key] = v
        elif key == "placed_by":
            if v is not None and (not isinstance(v, str) or not v):
                raise ValueError(f"anchor: placed_by must be a non-empty string or null, "
                                 f"got {v!r}")
            out[key] = v
        else:
            raise ValueError(f"anchor: unknown key {key!r}; keys: alignment, ref, kind, "
                             f"station, offset, side, label_offset, rotation, viewport, "
                             f"view_rotation, content_auto, placed_by, tip (callouts)")
    return out


@dataclass
class Entity:
    id: str = ""
    layer: str = "0"
    color: Optional[str] = None
    linetype: Optional[str] = None
    anchor: Optional[dict] = None  # design provenance (see as_anchor); sparse
    annotative: Optional[dict] = None  # paper sizes at a scale (see as_annotative); sparse

    TYPE = "entity"

    def _base_dict(self):
        d = {"id": self.id, "type": self.TYPE, "layer": self.layer}
        if self.color is not None:
            d["color"] = self.color
        if self.linetype is not None:
            d["linetype"] = self.linetype
        if self.anchor is not None:
            d["anchor"] = dict(self.anchor)
        if self.annotative is not None:
            d["annotative"] = dict(self.annotative)
        return d

    @staticmethod
    def _base_kwargs(d):
        return {
            "id": d.get("id", ""),
            "layer": d.get("layer", "0"),
            "color": d.get("color"),
            "linetype": d.get("linetype"),
            "anchor": as_anchor(d.get("anchor")),
            "annotative": as_annotative(d.get("annotative")),
        }

    def bbox(self, doc):
        raise NotImplementedError

    def transformed(self, fn: Callable, angle_delta_deg: float, scale: float) -> "Entity":
        """Return a copy mapped through a similarity transform: fn maps points,
        angle_delta rotates orientations, scale multiplies lengths."""
        raise NotImplementedError

    def translated(self, delta) -> "Entity":
        return self.transformed(lambda p: geo.translate_point(p, delta), 0.0, 1.0)


@dataclass
class Line(Entity):
    start: list = field(default_factory=lambda: [0.0, 0.0])
    end: list = field(default_factory=lambda: [0.0, 0.0])

    TYPE = "line"

    def to_dict(self):
        d = self._base_dict()
        d.update(start=list(self.start), end=list(self.end))
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(start=as_point(d["start"]), end=as_point(d["end"]),
                   **cls._base_kwargs(d))

    def bbox(self, doc):
        return geo.bbox_of_points([self.start, self.end])

    def transformed(self, fn, angle_delta_deg, scale):
        return Line(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                    start=fn(self.start), end=fn(self.end))


def as_bulges(value, n_vertices: int, closed: bool) -> Optional[list]:
    """Validate a polyline's bulges: one per vertex (the segment that starts
    there; an open polyline's last one is unused and may be left off), each
    tan(sweep / 4) of an arc segment, 0 for a straight one. Returns None when
    every segment is straight, so straight polylines serialize as before."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"bulges must be a list of numbers, got {value!r}")
    out = []
    for i, b in enumerate(value):
        if not _is_number(b) or not math.isfinite(b):
            raise ValueError(f"bulges[{i}] must be a number, got {b!r}")
        out.append(float(b))
    if len(out) == n_vertices - 1 and not closed:
        out.append(0.0)
    if len(out) != n_vertices:
        raise ValueError(f"bulges needs one value per vertex ({n_vertices}), got {len(out)}")
    if not any(abs(b) > 1e-12 for b in out):
        return None
    return out


@dataclass
class Polyline(Entity):
    """Vertices joined by segments, each straight or a circular arc. An arc
    segment is stored the DXF/LWPOLYLINE way, as the bulge of the segment that
    starts at a vertex: tan(sweep / 4), positive counter-clockwise (see
    ``geometry.bulge_arc``). ``bulges`` is None when every segment is
    straight."""
    vertices: list = field(default_factory=list)
    closed: bool = False
    bulges: Optional[list] = None

    TYPE = "polyline"

    def to_dict(self):
        d = self._base_dict()
        d.update(vertices=[list(v) for v in self.vertices], closed=self.closed)
        if self.has_arcs:
            d["bulges"] = list(self.bulges)
        return d

    @classmethod
    def from_dict(cls, d):
        vertices = [as_point(v) for v in d["vertices"]]
        if len(vertices) < 2:
            raise ValueError("polyline needs at least 2 vertices")
        closed = bool(d.get("closed", False))
        return cls(vertices=vertices, closed=closed,
                   bulges=as_bulges(d.get("bulges"), len(vertices), closed),
                   **cls._base_kwargs(d))

    @property
    def has_arcs(self) -> bool:
        return bool(self.bulges) and any(abs(b) > 1e-12 for b in self.bulges)

    def bulge(self, i: int) -> float:
        if not self.bulges or i >= len(self.bulges):
            return 0.0
        return self.bulges[i]

    def segments(self):
        """``[(start, end, bulge)]`` for every segment, the closing one
        included when the polyline is closed."""
        verts = self.vertices
        out = [(verts[i], verts[i + 1], self.bulge(i)) for i in range(len(verts) - 1)]
        if self.closed and len(verts) > 2:
            out.append((verts[-1], verts[0], self.bulge(len(verts) - 1)))
        return out

    def points(self, step_deg: float = 4.0):
        """The polyline as points to draw through, arcs sampled every
        ``step_deg`` (the first point repeated at the end when closed)."""
        if not self.has_arcs:
            pts = [list(v) for v in self.vertices]
            if self.closed and len(pts) > 2:
                pts.append(list(pts[0]))
            return pts
        pts = [list(self.vertices[0])]
        for a, b, bulge in self.segments():
            pts.extend(geo.bulge_points(a, b, bulge, step_deg)[1:])
        return pts

    def bbox(self, doc):
        if not self.vertices:
            return None
        if not self.has_arcs:
            return geo.bbox_of_points(self.vertices)
        bb = geo.bbox_of_points(self.vertices)
        for a, b, bulge in self.segments():
            if abs(bulge) > 1e-12:
                bb = geo.bbox_union(bb, geo.bulge_bbox(a, b, bulge))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        return Polyline(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                        vertices=[fn(v) for v in self.vertices], closed=self.closed,
                        bulges=list(self.bulges) if self.bulges else None)


@dataclass
class Arc(Entity):
    center: list = field(default_factory=lambda: [0.0, 0.0])
    radius: float = 1.0
    start_angle_deg: float = 0.0
    end_angle_deg: float = 90.0

    TYPE = "arc"

    def to_dict(self):
        d = self._base_dict()
        d.update(center=list(self.center), radius=self.radius,
                 start_angle_deg=self.start_angle_deg, end_angle_deg=self.end_angle_deg)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(center=as_point(d["center"]),
                   radius=as_positive(d["radius"], "radius"),
                   start_angle_deg=float(d["start_angle_deg"]),
                   end_angle_deg=float(d["end_angle_deg"]), **cls._base_kwargs(d))

    def bbox(self, doc):
        return geo.arc_bbox(self.center, self.radius, self.start_angle_deg, self.end_angle_deg)

    def transformed(self, fn, angle_delta_deg, scale):
        return Arc(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                   center=fn(self.center), radius=self.radius * scale,
                   start_angle_deg=self.start_angle_deg + angle_delta_deg,
                   end_angle_deg=self.end_angle_deg + angle_delta_deg)


@dataclass
class Circle(Entity):
    center: list = field(default_factory=lambda: [0.0, 0.0])
    radius: float = 1.0

    TYPE = "circle"

    def to_dict(self):
        d = self._base_dict()
        d.update(center=list(self.center), radius=self.radius)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(center=as_point(d["center"]),
                   radius=as_positive(d["radius"], "radius"),
                   **cls._base_kwargs(d))

    def bbox(self, doc):
        c, r = self.center, self.radius
        return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)

    def transformed(self, fn, angle_delta_deg, scale):
        return Circle(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                      center=fn(self.center), radius=self.radius * scale)


@dataclass
class Text(Entity):
    position: list = field(default_factory=lambda: [0.0, 0.0])
    content: str = ""
    height: float = 0.12
    style: str = "STANDARD"
    rotation_deg: float = 0.0
    halign: str = "left"
    valign: str = "bottom"

    TYPE = "text"

    def to_dict(self):
        d = self._base_dict()
        d.update(position=list(self.position), content=self.content, height=self.height,
                 style=self.style, rotation_deg=self.rotation_deg,
                 halign=self.halign, valign=self.valign)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(position=as_point(d["position"]), content=str(d["content"]),
                   height=as_positive(d["height"], "height"),
                   style=d.get("style", "STANDARD"),
                   rotation_deg=float(d.get("rotation_deg", 0.0)),
                   halign=_in_enum(d.get("halign", "left"), HALIGN, "halign"),
                   valign=_in_enum(d.get("valign", "bottom"), VALIGN, "valign"),
                   **cls._base_kwargs(d))

    def bbox(self, doc):
        wf = 1.0
        if doc is not None:
            style = doc.text_styles.get(self.style)
            if style is not None:
                wf = style.width_factor
        return geo.text_bbox(self.position, self.content, self.height,
                             self.rotation_deg, self.halign, self.valign, wf)

    def transformed(self, fn, angle_delta_deg, scale):
        return Text(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                    position=fn(self.position), content=self.content,
                    height=self.height * scale, style=self.style,
                    rotation_deg=self.rotation_deg + angle_delta_deg,
                    halign=self.halign, valign=self.valign)


@dataclass
class BlockRef(Entity):
    """An insertion of a block definition: its base point lands on
    ``position``, scaled and rotated. ``mirrored`` flips the symbol across its
    own vertical axis first (AutoCAD's negative X scale), which is what
    mirror_entities makes of a block -- a left-turn arrow becomes a right-turn
    arrow."""
    block_name: str = ""
    position: list = field(default_factory=lambda: [0.0, 0.0])
    scale: float = 1.0
    rotation_deg: float = 0.0
    mirrored: bool = False

    TYPE = "blockref"

    def to_dict(self):
        d = self._base_dict()
        d.update(block_name=self.block_name, position=list(self.position),
                 scale=self.scale, rotation_deg=self.rotation_deg)
        if self.mirrored:
            d["mirrored"] = True
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(block_name=d["block_name"], position=as_point(d["position"]),
                   scale=as_positive(d.get("scale", 1.0), "scale"),
                   rotation_deg=float(d.get("rotation_deg", 0.0)),
                   mirrored=bool(d.get("mirrored", False)), **cls._base_kwargs(d))

    def bbox(self, doc):
        prims = expand_entities(doc, [self])
        bb = None
        for e in prims:
            bb = geo.bbox_union(bb, e.bbox(doc))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        return BlockRef(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                        block_name=self.block_name, position=fn(self.position),
                        scale=self.scale * scale,
                        rotation_deg=self.rotation_deg + angle_delta_deg,
                        mirrored=self.mirrored)


@dataclass
class Table(Entity):
    """Grid of text cells with an optional title row. position is the TOP-LEFT
    corner; the table grows downward. columns: [{"header": str, "width": num}].
    """
    position: list = field(default_factory=lambda: [0.0, 0.0])
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    text_height: float = 0.12
    title: str = ""
    style: str = "STANDARD"

    TYPE = "table"
    ROW_FACTOR = 1.8  # row height as multiple of text height
    TITLE_FACTOR = 2.0

    def to_dict(self):
        d = self._base_dict()
        d.update(position=list(self.position),
                 columns=[{"header": c["header"], "width": c["width"]} for c in self.columns],
                 rows=[[str(v) for v in r] for r in self.rows],
                 text_height=self.text_height, title=self.title, style=self.style)
        return d

    @classmethod
    def from_dict(cls, d):
        columns = [{"header": str(c["header"]),
                    "width": as_positive(c["width"], "column width")}
                   for c in d["columns"]]
        if not columns:
            raise ValueError("table needs at least one column")
        rows = [[str(v) for v in r] for r in d.get("rows", [])]
        for i, row in enumerate(rows):
            if len(row) != len(columns):
                raise ValueError(f"rows[{i}] has {len(row)} cells but the "
                                 f"table has {len(columns)} columns")
        return cls(position=as_point(d["position"]), columns=columns, rows=rows,
                   text_height=as_positive(d.get("text_height", 0.12),
                                           "text_height"),
                   title=str(d.get("title", "")), style=d.get("style", "STANDARD"),
                   **cls._base_kwargs(d))

    def size(self):
        w = sum(c["width"] for c in self.columns)
        rh = self.text_height * self.ROW_FACTOR
        th = self.text_height * self.TITLE_FACTOR if self.title else 0.0
        h = th + (1 + len(self.rows)) * rh
        return w, h

    def bbox(self, doc):
        w, h = self.size()
        x, y = self.position
        return (x, y - h, x + w, y)

    def primitives(self, doc) -> List[Entity]:
        """Expand to Line/Text primitives (same space, absolute coordinates)."""
        x0, y0 = self.position
        w, h = self.size()
        rh = self.text_height * self.ROW_FACTOR
        th = self.text_height * self.TITLE_FACTOR if self.title else 0.0
        base = dict(layer=self.layer, color=self.color, linetype=self.linetype)
        out: List[Entity] = []

        def hline(y, i):
            out.append(Line(id=f"{self.id}:h{i}", start=[x0, y], end=[x0 + w, y], **base))

        # frame and row lines
        out.append(Polyline(id=f"{self.id}:frame",
                            vertices=[[x0, y0], [x0 + w, y0], [x0 + w, y0 - h], [x0, y0 - h]],
                            closed=True, **base))
        y = y0 - th
        if self.title:
            hline(y, 0)
        for i in range(1 + len(self.rows) - 1 + 1):  # header + rows boundaries (interior)
            yy = y - rh * (i + 1)
            if yy > y0 - h + 1e-9:
                hline(yy, i + 1)
        # column lines (below title row only)
        cx = x0
        for c in self.columns[:-1]:
            cx += c["width"]
            out.append(Line(id=f"{self.id}:v{cx:.3f}", start=[cx, y], end=[cx, y0 - h], **base))

        def cell_text(tid, cx_center, cy_center, content):
            out.append(Text(id=tid, position=[cx_center, cy_center], content=str(content),
                            height=self.text_height, style=self.style,
                            halign="center", valign="middle", **base))

        if self.title:
            cell_text(f"{self.id}:title", x0 + w / 2.0, y0 - th / 2.0, self.title)
        # header row
        cx = x0
        for j, c in enumerate(self.columns):
            cell_text(f"{self.id}:head{j}", cx + c["width"] / 2.0, y - rh / 2.0, c["header"])
            cx += c["width"]
        # data rows
        for i, row in enumerate(self.rows):
            cy = y - rh * (i + 1) - rh / 2.0
            cx = x0
            for j, c in enumerate(self.columns):
                if j < len(row):
                    cell_text(f"{self.id}:c{i}_{j}", cx + c["width"] / 2.0, cy, row[j])
                cx += c["width"]
        return out

    def transformed(self, fn, angle_delta_deg, scale):
        # Tables stay axis-aligned; rotation applies to position only.
        return Table(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor, annotative=self.annotative,
                     position=fn(self.position),
                     columns=[{"header": c["header"], "width": c["width"] * scale}
                              for c in self.columns],
                     rows=[list(r) for r in self.rows],
                     text_height=self.text_height * scale, title=self.title, style=self.style)


DIM_KINDS = ("linear", "aligned", "angular", "radius", "diameter", "arc_length")
DIM_ARROWS = ("arrow", "tick", "dot", "none")
#: Geometry each kind needs before it can be drawn (``line_point`` always).
DIM_REQUIRED = {
    "linear": ("p1", "p2"),
    "aligned": ("p1", "p2"),
    "angular": ("center", "p1", "p2"),
    "radius": ("center", "radius", "p1"),
    "diameter": ("center", "radius", "p1"),
    "arc_length": ("center", "radius", "p1", "p2"),
}


@dataclass
class Dimension(Entity):
    """A measurement, not a picture of one.

    The entity stores what is being measured -- the points, the arc, and
    ``line_point``, the place the dimension line was dragged to -- and derives
    extension lines, the dimension line, arrowheads and the number from them
    (see ``document.dimgeom``). Move a measured point and the text follows.

    Which fields carry meaning depends on ``kind`` (see ``DIM_REQUIRED``):
    ``linear``/``aligned`` measure between ``p1`` and ``p2``; ``angular``
    measures the angle at ``center`` between the rays to ``p1`` and ``p2``;
    ``radius``/``diameter`` measure a circle at ``center`` with ``p1`` on it;
    ``arc_length`` measures counter-clockwise from ``p1`` to ``p2``.

    ``arrow_size``/``text_gap``/``extension_offset``/``extension_beyond``
    default to fixed multiples of ``text_height`` when left null, so one
    number sizes the whole dimension. ``measure_scale`` is AutoCAD's DIMLFAC:
    the multiplier from drawn length to reported length, which is how a
    dimension drawn on a sheet reports model feet (and what the viewport
    transform maintains when model geometry is shown on paper).

    ``view_rotation`` is the twist of the viewport a model dimension is read
    through: its text is then set to read upright on that sheet, not in the
    model (as a label's is). Null or 0 is an untwisted view, and is not
    written to the file.
    """
    kind: str = "linear"
    p1: list = field(default_factory=lambda: [0.0, 0.0])
    p2: Optional[list] = None
    center: Optional[list] = None
    radius: Optional[float] = None
    line_point: list = field(default_factory=lambda: [0.0, 0.0])
    rotation_deg: Optional[float] = None  # linear: measured direction, null = infer
    text_height: float = 0.12
    style: str = "STANDARD"
    text_override: Optional[str] = None  # null = the measurement; "" = no text
    prefix: Optional[str] = None  # null = the kind's own (R=, Ø, L=)
    suffix: str = ""
    unit_format: str = "feet"
    precision: int = 2
    arrow: str = "arrow"
    arrow_size: Optional[float] = None
    text_gap: Optional[float] = None
    extension_offset: Optional[float] = None
    extension_beyond: Optional[float] = None
    measure_scale: float = 1.0
    view_rotation: Optional[float] = None  # the twist of the view it is read through

    TYPE = "dimension"

    FIELDS = ("kind", "p1", "p2", "center", "radius", "line_point", "rotation_deg",
              "text_height", "style", "text_override", "prefix", "suffix",
              "unit_format", "precision", "arrow", "arrow_size", "text_gap",
              "extension_offset", "extension_beyond", "measure_scale")

    def to_dict(self):
        d = self._base_dict()
        for name in self.FIELDS:
            value = getattr(self, name)
            d[name] = list(value) if isinstance(value, list) else value
        if self.view_rotation:  # an untwisted dimension's record is what it always was
            d["view_rotation"] = float(self.view_rotation)
        return d

    @classmethod
    def from_dict(cls, d):
        kind = _in_enum(d.get("kind", "linear"), DIM_KINDS, "kind")
        fields = {
            "kind": kind,
            "line_point": as_point(d.get("line_point", [0.0, 0.0])),
            "text_height": as_positive(d.get("text_height", 0.12), "text_height"),
            "style": d.get("style", "STANDARD"),
            "suffix": str(d.get("suffix", "")),
            "unit_format": _in_enum(d.get("unit_format", "feet"), LENGTH_FORMATS,
                                    "unit_format"),
            "precision": _as_precision(d.get("precision", 2)),
            "arrow": _in_enum(d.get("arrow", "arrow"), DIM_ARROWS, "arrow"),
            "measure_scale": _as_nonzero(d.get("measure_scale", 1.0), "measure_scale"),
        }
        for name in ("p1", "p2", "center"):
            value = d.get(name)
            fields[name] = None if value is None else as_point(value)
        for name in ("arrow_size", "text_gap", "extension_offset", "extension_beyond"):
            value = d.get(name)
            fields[name] = None if value is None else _as_size(value, name)
        radius = d.get("radius")
        fields["radius"] = None if radius is None else as_positive(radius, "radius")
        rotation = d.get("rotation_deg")
        fields["rotation_deg"] = None if rotation is None else float(rotation)
        twist = d.get("view_rotation")
        fields["view_rotation"] = float(twist) if twist else None
        for name in ("text_override", "prefix"):
            value = d.get(name)
            fields[name] = None if value is None else str(value)
        if fields["p1"] is None:
            fields["p1"] = [0.0, 0.0]
        missing = [name for name in DIM_REQUIRED[kind] if fields.get(name) is None]
        if missing:
            raise ValueError(f"a {kind} dimension needs {', '.join(DIM_REQUIRED[kind])}; "
                             f"missing {', '.join(missing)}")
        return cls(**fields, **cls._base_kwargs(d))

    def primitives(self, doc) -> List[Entity]:
        """Expand to Line/Polyline/Arc/Circle/Text primitives (same space)."""
        from roaddraft.document import dimgeom
        return dimgeom.primitives(self, doc)

    def bbox(self, doc):
        bb = None
        for prim in self.primitives(doc):
            bb = geo.bbox_union(bb, prim.bbox(doc))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        def scaled(value):
            return None if value is None else value * scale

        return Dimension(
            id=self.id, layer=self.layer, color=self.color, linetype=self.linetype,
            anchor=self.anchor, annotative=self.annotative, kind=self.kind,
            p1=fn(self.p1), p2=None if self.p2 is None else fn(self.p2),
            center=None if self.center is None else fn(self.center),
            radius=scaled(self.radius), line_point=fn(self.line_point),
            rotation_deg=None if self.rotation_deg is None
            else self.rotation_deg + angle_delta_deg,
            text_height=self.text_height * scale, style=self.style,
            text_override=self.text_override, prefix=self.prefix, suffix=self.suffix,
            unit_format=self.unit_format, precision=self.precision, arrow=self.arrow,
            arrow_size=scaled(self.arrow_size), text_gap=scaled(self.text_gap),
            extension_offset=scaled(self.extension_offset),
            extension_beyond=scaled(self.extension_beyond),
            # the drawing shrinks onto paper; the number it reports must not
            measure_scale=(self.measure_scale / scale if scale else self.measure_scale),
            # the view it is read through has not turned because the dimension moved
            view_rotation=self.view_rotation)


POINT_MARKERS = ("x", "cross", "circle", "circle_x", "dot", "none")
POINT_LABEL_FIELDS = ("number", "elevation", "description")


def _as_point_number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or float(value) != int(value) or int(value) < 1:
        raise ValueError(f"a point number is a whole number from 1 up, got {value!r}")
    return int(value)


def _as_label_fields(value):
    if value is None:
        return list(POINT_LABEL_FIELDS)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"label must be a list of {list(POINT_LABEL_FIELDS)}, got {value!r}")
    out = []
    for item in value:
        if item not in POINT_LABEL_FIELDS:
            raise ValueError(f"label fields are {list(POINT_LABEL_FIELDS)}, got {item!r}")
        if item in out:
            raise ValueError(f"label lists {item!r} twice")
        out.append(item)
    return out


@dataclass
class Point(Entity):
    """A COGO point (Civil 3D point, MicroStation/ORD survey point): a
    numbered location with an optional elevation and description (the raw
    description code a survey carries, e.g. 'EP', 'MON'), drawn as a marker
    with its label stacked beside it -- point number, elevation, description.

    ``size`` is the marker's width and ``text_height`` the label's, both in
    space units (feet in model space); ``label`` lists which fields show."""
    position: list = field(default_factory=lambda: [0.0, 0.0])
    number: Optional[int] = None
    elevation: Optional[float] = None
    description: str = ""
    marker: str = "x"
    size: float = 1.0
    text_height: float = 1.0
    label: list = field(default_factory=lambda: list(POINT_LABEL_FIELDS))
    style: str = "STANDARD"

    TYPE = "point"

    def to_dict(self):
        d = self._base_dict()
        d.update(position=list(self.position), number=self.number,
                 elevation=self.elevation, description=self.description,
                 marker=self.marker, size=self.size, text_height=self.text_height,
                 label=list(self.label), style=self.style)
        return d

    @classmethod
    def from_dict(cls, d):
        elevation = d.get("elevation")
        if elevation is not None and (not _is_number(elevation)
                                      or not math.isfinite(elevation)):
            raise ValueError(f"elevation must be a number or null, got {elevation!r}")
        return cls(position=as_point(d["position"]),
                   number=_as_point_number(d.get("number")),
                   elevation=None if elevation is None else float(elevation),
                   description=str(d.get("description") or ""),
                   marker=_in_enum(d.get("marker", "x"), POINT_MARKERS, "marker"),
                   size=as_positive(d.get("size", 1.0), "size"),
                   text_height=as_positive(d.get("text_height", 1.0), "text_height"),
                   label=_as_label_fields(d.get("label")),
                   style=d.get("style", "STANDARD"), **cls._base_kwargs(d))

    def label_lines(self) -> List[str]:
        lines = []
        for name in self.label:
            if name == "number" and self.number is not None:
                lines.append(str(self.number))
            elif name == "elevation" and self.elevation is not None:
                lines.append(f"{self.elevation:.2f}")
            elif name == "description" and self.description:
                lines.append(self.description)
        return lines

    def primitives(self, doc) -> List[Entity]:
        """The marker and the label, as Line/Circle/Text primitives."""
        x, y = self.position
        h = self.size / 2.0
        base = dict(layer=self.layer, color=self.color, linetype=None)
        out: List[Entity] = []

        def line(tag, a, b):
            out.append(Line(id=f"{self.id}:{tag}", start=a, end=b, **base))

        if self.marker in ("x", "circle_x"):
            k = h * math.sqrt(0.5) if self.marker == "circle_x" else h
            line("m1", [x - k, y - k], [x + k, y + k])
            line("m2", [x - k, y + k], [x + k, y - k])
        if self.marker == "cross":
            line("m1", [x - h, y], [x + h, y])
            line("m2", [x, y - h], [x, y + h])
        if self.marker in ("circle", "circle_x"):
            out.append(Circle(id=f"{self.id}:m3", center=[x, y], radius=h, **base))
        if self.marker == "dot":
            out.append(Circle(id=f"{self.id}:m3", center=[x, y], radius=h * 0.3, **base))
        lines = self.label_lines()
        spacing = self.text_height * 1.5
        for k, content in enumerate(lines):
            dy = ((len(lines) - 1) / 2.0 - k) * spacing
            out.append(Text(id=f"{self.id}:t{k + 1}", position=[x + h + self.text_height * 0.5,
                                                                  y + dy],
                            content=content, height=self.text_height, style=self.style,
                            halign="left", valign="middle", **base))
        return out

    def bbox(self, doc):
        bb = geo.bbox_of_points([self.position])
        for prim in self.primitives(doc):
            bb = geo.bbox_union(bb, prim.bbox(doc))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        return Point(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype,
                     anchor=self.anchor, annotative=self.annotative,
                     position=fn(self.position), number=self.number,
                     elevation=self.elevation, description=self.description,
                     marker=self.marker, size=self.size * scale,
                     text_height=self.text_height * scale, label=list(self.label),
                     style=self.style)


def as_loops(value) -> list:
    """Validate hatch boundary loops: ``[{"vertices": [[x, y], ...], "bulges":
    [...]}]``, each implicitly closed, bulges optional (one per vertex, for the
    segment that starts there)."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("a hatch needs at least one boundary loop")
    loops = []
    for i, loop in enumerate(value):
        if not isinstance(loop, dict) or "vertices" not in loop:
            raise ValueError(f"loops[{i}] must be an object with vertices (and optional "
                             f"bulges), got {loop!r}")
        unknown = set(loop) - {"vertices", "bulges"}
        if unknown:
            raise ValueError(f"loops[{i}]: unknown keys {sorted(unknown)}")
        vertices = [as_point(v) for v in loop["vertices"]]
        try:
            bulges = as_bulges(loop.get("bulges"), len(vertices), True)
        except ValueError as ex:
            raise ValueError(f"loops[{i}]: {ex}")
        if len(vertices) < (2 if bulges else 3):
            raise ValueError(f"loops[{i}] needs at least 3 vertices (2 when its segments "
                             f"are arcs)")
        out = {"vertices": vertices}
        if bulges:
            out["bulges"] = bulges
        loops.append(out)
    return loops


def loop_segments(loop):
    """``[(start, end, bulge)]`` of a closed boundary loop."""
    verts = loop["vertices"]
    bulges = loop.get("bulges") or [0.0] * len(verts)
    return [(verts[i], verts[(i + 1) % len(verts)], bulges[i]) for i in range(len(verts))]


def loop_points(loop, step_deg: float = 4.0):
    """A loop as a polygon (arcs sampled), not repeating its first point."""
    pts = []
    for a, b, bulge in loop_segments(loop):
        pts.extend(geo.bulge_points(a, b, bulge, step_deg)[:-1])
    return pts


@dataclass
class Hatch(Entity):
    """An area filled solid or with a pattern (AutoCAD HATCH, MicroStation
    Pattern Area / Fill): pavement, removals, a legend swatch.

    ``loops`` are closed boundaries; an area inside an even number of them is
    left open, so a loop inside another is an island. ``pattern`` is SOLID or
    an AutoCAD pattern name (ANSI31, AR-CONC, GRAVEL, ...); ``scale`` sizes it
    the AutoCAD way (pattern units times scale), ``angle_deg`` turns it.
    ``opacity`` below 1 screens it, as a shaded area on a plan often is."""
    loops: list = field(default_factory=list)
    pattern: str = "SOLID"
    scale: float = 1.0
    angle_deg: float = 0.0
    opacity: float = 1.0

    TYPE = "hatch"

    def to_dict(self):
        d = self._base_dict()
        d.update(loops=[{k: [list(v) for v in loop["vertices"]] if k == "vertices"
                         else list(loop[k]) for k in loop} for loop in self.loops],
                 pattern=self.pattern, scale=self.scale, angle_deg=self.angle_deg,
                 opacity=self.opacity)
        return d

    @classmethod
    def from_dict(cls, d):
        from roaddraft.document.hatching import canonical_pattern
        opacity = float(d.get("opacity", 1.0))
        if not 0.0 < opacity <= 1.0:
            raise ValueError(f"opacity must be more than 0 and at most 1, got {opacity:g}")
        return cls(loops=as_loops(d["loops"]),
                   pattern=canonical_pattern(d.get("pattern", "SOLID")),
                   scale=as_positive(d.get("scale", 1.0), "scale"),
                   angle_deg=float(d.get("angle_deg", 0.0)), opacity=opacity,
                   **cls._base_kwargs(d))

    @property
    def solid(self) -> bool:
        return self.pattern == "SOLID"

    def bbox(self, doc):
        bb = None
        for loop in self.loops:
            for a, b, bulge in loop_segments(loop):
                bb = geo.bbox_union(bb, geo.bulge_bbox(a, b, bulge))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        loops = []
        for loop in self.loops:
            moved = {"vertices": [fn(v) for v in loop["vertices"]]}
            if loop.get("bulges"):
                moved["bulges"] = list(loop["bulges"])
            loops.append(moved)
        return Hatch(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype,
                     anchor=self.anchor, annotative=self.annotative, loops=loops,
                     pattern=self.pattern, scale=self.scale * scale,
                     angle_deg=self.angle_deg + angle_delta_deg, opacity=self.opacity)


ENTITY_TYPES = {
    cls.TYPE: cls
    for cls in (Line, Polyline, Arc, Circle, Text, BlockRef, Table, Dimension, Point, Hatch)
}


def entity_from_dict(d) -> Entity:
    t = d.get("type")
    if t not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {t!r}; expected one of {sorted(ENTITY_TYPES)}")
    return ENTITY_TYPES[t].from_dict(d)


def _segment_distance(p, a, b, bulge) -> float:
    arc = geo.bulge_arc(a, b, bulge)
    if arc is None:
        return geo.dist_point_to_segment(p, a, b)
    center, radius, start, sweep = arc
    return geo.dist_point_to_arc(p, center, radius, start, sweep)


def entity_distance(doc, entity: Entity, p) -> float:
    """Distance from a point to an entity, for screen picking (hit tests)."""
    if isinstance(entity, Line):
        return geo.dist_point_to_segment(p, entity.start, entity.end)
    if isinstance(entity, Polyline):
        verts = entity.vertices
        if len(verts) < 2:
            return geo.distance(p, verts[0]) if verts else float("inf")
        return min(_segment_distance(p, a, b, bulge) for a, b, bulge in entity.segments())
    if isinstance(entity, Point):
        return geo.distance(p, entity.position)
    if isinstance(entity, Hatch):
        return min(_segment_distance(p, a, b, bulge)
                   for loop in entity.loops for a, b, bulge in loop_segments(loop))
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        ang = math.degrees(math.atan2(p[1] - entity.center[1],
                                      p[0] - entity.center[0])) % 360.0
        if s <= ang <= e or s <= ang + 360.0 <= e:
            return abs(geo.distance(p, entity.center) - entity.radius)
        return min(geo.distance(p, geo.arc_point(entity.center, entity.radius, s)),
                   geo.distance(p, geo.arc_point(entity.center, entity.radius, e)))
    if isinstance(entity, Circle):
        return abs(geo.distance(p, entity.center) - entity.radius)
    if isinstance(entity, (Text, Table)):
        bb = entity.bbox(doc)
        return geo.dist_point_to_bbox(p, bb) if bb else float("inf")
    if isinstance(entity, (BlockRef, Dimension)):
        prims = expand_entities(doc, [entity])
        if not prims:
            return float("inf")
        return min(entity_distance(doc, prim, p) for prim in prims)
    return float("inf")


def expand_entities(doc, entities, depth: int = 0) -> List[Entity]:
    """Recursively expand BlockRefs, Tables and Dimensions into drawable
    primitives. Line/Polyline/Arc/Circle/Text pass through unchanged, and so
    do Point and Hatch, which every renderer draws itself (a point is found
    and snapped to as one thing, a hatch fills rather than strokes)."""
    out: List[Entity] = []
    for e in entities:
        if isinstance(e, BlockRef):
            if depth >= MAX_BLOCK_DEPTH:
                continue
            block = doc.blocks.get(e.block_name) if doc is not None else None
            if block is None:
                continue
            bx, by = block.base_point
            s, rot = e.scale, e.rotation_deg
            inner = expand_entities(doc, block.entities, depth + 1)
            if e.mirrored:
                # x -> -x in the block, then rotate and place: R(rot) M = R(rot + 180) F
                from roaddraft.document.transform import Similarity, transform_entity
                place = Similarity(scale=s, rotation_deg=rot + 180.0, mirror=True)
                origin = place.apply([bx, by])
                place = place.then_translate([e.position[0] - origin[0],
                                              e.position[1] - origin[1]])
                for prim in inner:
                    t = transform_entity(prim, place)
                    t.id = f"{e.id}:{prim.id}"
                    out.append(t)
                continue

            def fn(p, e=e, bx=bx, by=by, s=s, rot=rot):
                local = [(p[0] - bx) * s, (p[1] - by) * s]
                local = geo.rotate_point(local, rot)
                return [e.position[0] + local[0], e.position[1] + local[1]]

            for prim in inner:
                t = prim.transformed(fn, rot, s)
                t.id = f"{e.id}:{prim.id}"
                out.append(t)
        elif isinstance(e, (Table, Dimension)):
            out.extend(e.primitives(doc))
        else:
            out.append(e)
    return out
