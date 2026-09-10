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


ANCHOR_REQUIRED = ("alignment", "ref", "kind")
ANCHOR_SIDES = ("left", "right")
ANCHOR_ROTATIONS = ("along", "perpendicular", "horizontal")


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def as_anchor(value) -> Optional[Dict]:
    """Validate an anchor record (provenance of a design-anchored entity).

    Returns None for None, otherwise a plain dict copy. Required string keys:
    alignment, ref, kind. Optional keys: station/offset/label_offset (number
    or None), side (left|right|None), rotation (along|perpendicular|
    horizontal|None), viewport (str|None), content_auto (bool). Anything
    else raises ValueError('anchor: ...')."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"anchor: expected an object, got {value!r}")
    out = {}
    for key in ANCHOR_REQUIRED:
        v = value.get(key)
        if not isinstance(v, str) or not v:
            raise ValueError(f"anchor: {key} must be a non-empty string, got {v!r}")
        out[key] = v
    for key, v in value.items():
        if key in ANCHOR_REQUIRED:
            continue
        if key in ("station", "offset", "label_offset"):
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
        else:
            raise ValueError(f"anchor: unknown key {key!r}; keys: alignment, ref, kind, "
                             f"station, offset, side, label_offset, rotation, viewport, "
                             f"content_auto")
    return out


@dataclass
class Entity:
    id: str = ""
    layer: str = "0"
    color: Optional[str] = None
    linetype: Optional[str] = None
    anchor: Optional[dict] = None  # design provenance (see as_anchor); sparse

    TYPE = "entity"

    def _base_dict(self):
        d = {"id": self.id, "type": self.TYPE, "layer": self.layer}
        if self.color is not None:
            d["color"] = self.color
        if self.linetype is not None:
            d["linetype"] = self.linetype
        if self.anchor is not None:
            d["anchor"] = dict(self.anchor)
        return d

    @staticmethod
    def _base_kwargs(d):
        return {
            "id": d.get("id", ""),
            "layer": d.get("layer", "0"),
            "color": d.get("color"),
            "linetype": d.get("linetype"),
            "anchor": as_anchor(d.get("anchor")),
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
        return Line(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
                    start=fn(self.start), end=fn(self.end))


@dataclass
class Polyline(Entity):
    vertices: list = field(default_factory=list)
    closed: bool = False

    TYPE = "polyline"

    def to_dict(self):
        d = self._base_dict()
        d.update(vertices=[list(v) for v in self.vertices], closed=self.closed)
        return d

    @classmethod
    def from_dict(cls, d):
        vertices = [as_point(v) for v in d["vertices"]]
        if len(vertices) < 2:
            raise ValueError("polyline needs at least 2 vertices")
        return cls(vertices=vertices,
                   closed=bool(d.get("closed", False)), **cls._base_kwargs(d))

    def bbox(self, doc):
        if not self.vertices:
            return None
        return geo.bbox_of_points(self.vertices)

    def transformed(self, fn, angle_delta_deg, scale):
        return Polyline(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
                        vertices=[fn(v) for v in self.vertices], closed=self.closed)


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
        return Arc(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
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
        return Circle(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
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
        return Text(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
                    position=fn(self.position), content=self.content,
                    height=self.height * scale, style=self.style,
                    rotation_deg=self.rotation_deg + angle_delta_deg,
                    halign=self.halign, valign=self.valign)


@dataclass
class BlockRef(Entity):
    block_name: str = ""
    position: list = field(default_factory=lambda: [0.0, 0.0])
    scale: float = 1.0
    rotation_deg: float = 0.0

    TYPE = "blockref"

    def to_dict(self):
        d = self._base_dict()
        d.update(block_name=self.block_name, position=list(self.position),
                 scale=self.scale, rotation_deg=self.rotation_deg)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(block_name=d["block_name"], position=as_point(d["position"]),
                   scale=as_positive(d.get("scale", 1.0), "scale"),
                   rotation_deg=float(d.get("rotation_deg", 0.0)), **cls._base_kwargs(d))

    def bbox(self, doc):
        prims = expand_entities(doc, [self])
        bb = None
        for e in prims:
            bb = geo.bbox_union(bb, e.bbox(doc))
        return bb

    def transformed(self, fn, angle_delta_deg, scale):
        return BlockRef(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
                        block_name=self.block_name, position=fn(self.position),
                        scale=self.scale * scale,
                        rotation_deg=self.rotation_deg + angle_delta_deg)


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
        return Table(id=self.id, layer=self.layer, color=self.color, linetype=self.linetype, anchor=self.anchor,
                     position=fn(self.position),
                     columns=[{"header": c["header"], "width": c["width"] * scale}
                              for c in self.columns],
                     rows=[list(r) for r in self.rows],
                     text_height=self.text_height * scale, title=self.title, style=self.style)


ENTITY_TYPES = {
    cls.TYPE: cls for cls in (Line, Polyline, Arc, Circle, Text, BlockRef, Table)
}


def entity_from_dict(d) -> Entity:
    t = d.get("type")
    if t not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {t!r}; expected one of {sorted(ENTITY_TYPES)}")
    return ENTITY_TYPES[t].from_dict(d)


def entity_distance(doc, entity: Entity, p) -> float:
    """Distance from a point to an entity, for screen picking (hit tests)."""
    if isinstance(entity, Line):
        return geo.dist_point_to_segment(p, entity.start, entity.end)
    if isinstance(entity, Polyline):
        verts = entity.vertices
        if len(verts) < 2:
            return geo.distance(p, verts[0]) if verts else float("inf")
        segs = list(zip(verts, verts[1:]))
        if entity.closed:
            segs.append((verts[-1], verts[0]))
        return min(geo.dist_point_to_segment(p, a, b) for a, b in segs)
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
    if isinstance(entity, BlockRef):
        prims = expand_entities(doc, [entity])
        if not prims:
            return float("inf")
        return min(entity_distance(doc, prim, p) for prim in prims)
    return float("inf")


def expand_entities(doc, entities, depth: int = 0) -> List[Entity]:
    """Recursively expand BlockRefs and Tables into drawable primitives.
    Line/Polyline/Arc/Circle/Text pass through unchanged."""
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

            def fn(p, e=e, bx=bx, by=by, s=s, rot=rot):
                local = [(p[0] - bx) * s, (p[1] - by) * s]
                local = geo.rotate_point(local, rot)
                return [e.position[0] + local[0], e.position[1] + local[1]]

            inner = expand_entities(doc, block.entities, depth + 1)
            for prim in inner:
                t = prim.transformed(fn, rot, s)
                t.id = f"{e.id}:{prim.id}"
                out.append(t)
        elif isinstance(e, Table):
            out.extend(e.primitives(doc))
        else:
            out.append(e)
    return out
