"""What a sheet shows, in paper inches: the reader the tier-3 checks judge by.

A plan is checked as it plots. Lettering on the sheet itself and lettering in
the sheet file's own model space reach the paper the same way: model-space work
goes through each viewport, scaled by its plot scale, turned by its twist and
clipped to its window. So the checks read both, and an agent that copied the
design into the sheet file and lettered it with the engine's own labelers is
judged exactly like one that lettered the paper by hand.

Work saved into a *referenced* design file is not read: the job is the sheet
file's.

Text gets an oriented box, not ``Text.bbox``'s axis-aligned one, which is about
0.7 in tall for a 2 in label turned 18 degrees. Blocks, tables and dimensions
are read through ``expand_entities`` as the renderer draws them. Tables and
dimensions are also kept whole, because a check wants a table's rows and a
dimension's measured points, not just their linework.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document import dimgeom, viewmap
from roaddraft.document.clip import clip_primitives
from roaddraft.document.entities import (Arc, Circle, Dimension, Entity, Line, Polyline, Table,
                                         Text, expand_entities)

ARC_STEP_IN = 0.02          # chord length when an arc becomes segments on paper


# --------------------------------------------------------------- marks


@dataclass
class PText:
    """A text as it plots: paper position, rotation (deg) and height (in)."""
    content: str
    position: List[float]
    rotation: float
    height: float
    halign: str = "left"
    valign: str = "bottom"
    width_factor: float = 1.0
    source: str = ""            # id of the entity the text belongs to
    space: str = "paper"        # "paper" or "model"

    @property
    def lines(self) -> List[str]:
        return self.content.split("\n") or [""]

    def size(self) -> Tuple[float, float]:
        return geo.text_size(self.content, self.height, self.width_factor)

    def frame(self):
        """``(origin, u, v, w, h)``: the box's lower-left corner in paper, the
        unit vector along the text and the one up it, width and height."""
        w, h = self.size()
        x0 = {"center": -w / 2.0, "right": -w}.get(self.halign, 0.0)
        y0 = {"middle": -h / 2.0, "top": -h}.get(self.valign, 0.0)
        r = math.radians(self.rotation)
        u = (math.cos(r), math.sin(r))
        v = (-math.sin(r), math.cos(r))
        origin = [self.position[0] + u[0] * x0 + v[0] * y0,
                  self.position[1] + u[1] * x0 + v[1] * y0]
        return origin, u, v, w, h

    def corners(self, pad: float = 0.0) -> List[List[float]]:
        o, u, v, w, h = self.frame()
        out = []
        for a, b in ((-pad, -pad), (w + pad, -pad), (w + pad, h + pad), (-pad, h + pad)):
            out.append([o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b])
        return out

    def center(self) -> List[float]:
        o, u, v, w, h = self.frame()
        return [o[0] + u[0] * w / 2.0 + v[0] * h / 2.0, o[1] + u[1] * w / 2.0 + v[1] * h / 2.0]

    def local(self, p) -> Tuple[float, float]:
        """``p`` in the box's own frame: (along from the left edge, up from the bottom)."""
        o, u, v, _w, _h = self.frame()
        dx, dy = p[0] - o[0], p[1] - o[1]
        return dx * u[0] + dy * u[1], dx * v[0] + dy * v[1]

    def contains(self, p, pad: float = 0.0) -> bool:
        a, b = self.local(p)
        w, h = self.size()
        return -pad <= a <= w + pad and -pad <= b <= h + pad

    def axis_distance(self, p) -> float:
        """How far ``p`` lies off the line through the text's centre, along it."""
        _o, u, v, _w, _h = self.frame()
        c = self.center()
        return abs((p[0] - c[0]) * v[0] + (p[1] - c[1]) * v[1])

    def bbox(self) -> Tuple[float, float, float, float]:
        return geo.bbox_of_points(self.corners())


@dataclass
class PSeg:
    a: List[float]
    b: List[float]
    source: str = ""
    space: str = "paper"
    closed: bool = False        # part of a closed polyline: an arrowhead or a frame, not a leader

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def angle(self) -> float:
        return math.degrees(math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0]))

    def mid(self) -> List[float]:
        return [(self.a[0] + self.b[0]) / 2.0, (self.a[1] + self.b[1]) / 2.0]

    def distance(self, p) -> float:
        return geo.dist_point_to_segment(p, self.a, self.b)


@dataclass
class PCircle:
    center: List[float]
    radius: float
    source: str = ""
    space: str = "paper"


@dataclass
class PTable:
    headers: List[str]
    rows: List[List[str]]
    title: str
    box: Tuple[float, float, float, float]
    source: str = ""
    space: str = "paper"


@dataclass
class PDim:
    """A dimension as it plots: its measured points and the number it shows."""
    kind: str
    p1: List[float]
    p2: Optional[List[float]]
    text: str
    texts: List[PText] = field(default_factory=list)
    source: str = ""
    space: str = "paper"


@dataclass
class Plot:
    """Everything one set of entities puts on one sheet."""
    sheet: object
    texts: List[PText] = field(default_factory=list)
    segs: List[PSeg] = field(default_factory=list)
    circles: List[PCircle] = field(default_factory=list)
    tables: List[PTable] = field(default_factory=list)
    dims: List[PDim] = field(default_factory=list)

    def free_texts(self) -> List[PText]:
        """Texts that are not table cells or dimension numbers."""
        bound = {t.source for t in self.tables} | {d.source for d in self.dims}
        return [t for t in self.texts if t.source not in bound]


# ----------------------------------------------------------------- reading


def _width_factor(doc, style: str) -> float:
    s = doc.text_styles.get(style) if doc is not None else None
    return float(s.width_factor) if s is not None else 1.0


def _window(vp) -> List[List[float]]:
    x0, y0, x1, y1 = vp.paper_bbox()
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _arc_segments(a, source: str, space: str) -> List[PSeg]:
    s, t = geo.arc_sweep(a.start_angle_deg, a.end_angle_deg)
    sweep = math.radians(t - s)
    n = max(1, int(math.ceil(a.radius * abs(sweep) / ARC_STEP_IN)))
    pts = [[a.center[0] + a.radius * math.cos(math.radians(s) + sweep * i / n),
            a.center[1] + a.radius * math.sin(math.radians(s) + sweep * i / n)] for i in range(n + 1)]
    return [PSeg(p, q, source, space) for p, q in zip(pts, pts[1:])]


def _add_prims(plot: Plot, doc, prims, source: str, space: str) -> None:
    for p in prims:
        if isinstance(p, Text):
            plot.texts.append(PText(p.content, list(p.position), float(p.rotation_deg),
                                    float(p.height), p.halign, p.valign,
                                    _width_factor(doc, p.style), source, space))
        elif isinstance(p, Line):
            plot.segs.append(PSeg(list(p.start), list(p.end), source, space))
        elif isinstance(p, Polyline):
            verts = [list(v) for v in p.vertices]
            if p.closed and verts:
                verts.append(verts[0])
            plot.segs.extend(PSeg(a, b, source, space, bool(p.closed))
                             for a, b in zip(verts, verts[1:]))
        elif isinstance(p, Arc):
            plot.segs.extend(_arc_segments(p, source, space))
        elif isinstance(p, Circle):
            plot.circles.append(PCircle(list(p.center), float(p.radius), source, space))


def plot(session, sheet, items: Iterable[Tuple[str, Entity]]) -> Plot:
    """Read ``(space key, entity)`` pairs as they plot on ``sheet``: the
    sheet's own entities as they are, the model's through every viewport."""
    doc = session.doc
    out = Plot(sheet=sheet)
    for space, e in items:
        if space == sheet.id:
            views = [(None, lambda p: list(p), 0.0, 1.0)]
        elif space == "model":
            views = [(vp, vp.transform().to_paper, float(vp.rotation_deg), 1.0 / vp.feet_per_inch)
                     for vp in sheet.viewports]
        else:
            continue
        for vp, fn, turn, k in views:
            if isinstance(e, Table):
                x0, y0, x1, y1 = e.bbox(doc)
                corners = [fn(c) for c in ([x0, y0], [x1, y0], [x1, y1], [x0, y1])]
                if vp is None or viewmap.in_window(vp, fn(e.position)):
                    out.tables.append(PTable([c["header"] for c in e.columns],
                                             [[str(v) for v in r] for r in e.rows], e.title,
                                             geo.bbox_of_points(corners), e.id,
                                             "paper" if vp is None else "model"))
            if isinstance(e, Dimension):
                p1 = fn(e.p1) if e.p1 is not None else None
                p2 = fn(e.p2) if e.p2 is not None else None
                if vp is None or (p1 is not None and viewmap.in_window(vp, p1)):
                    dtexts = []
                    for t in expand_entities(doc, [e]):
                        if isinstance(t, Text):
                            t = t.transformed(fn, turn, k)
                            dtexts.append(PText(t.content, list(t.position), float(t.rotation_deg),
                                                float(t.height), t.halign, t.valign,
                                                _width_factor(doc, t.style), e.id,
                                                "paper" if vp is None else "model"))
                    out.dims.append(PDim(e.kind, p1, p2, dimgeom.text_of(e), dtexts, e.id,
                                         "paper" if vp is None else "model"))
            prims = expand_entities(doc, [e])
            if vp is not None:
                prims = [p.transformed(fn, turn, k) for p in prims]
                prims = clip_primitives(prims, _window(vp))
            _add_prims(out, doc, prims, e.id, "paper" if vp is None else "model")
    return out


def sheet_items(baseline, submitted, sheet_name: str, added_only: bool = True):
    """``(space key, entity)`` for what reaches one sheet of the submission:
    its paper and the sheet file's model space. ``added_only`` keeps only what
    the fixture did not have."""
    sheet = next((s for s in submitted.doc.sheets.values() if s.name == sheet_name), None)
    if sheet is None:
        return []
    before = set()
    if added_only:
        before = set(baseline.doc.model_entities)
        for s in baseline.doc.sheets.values():
            before |= set(s.entities)
    out = [(sheet.id, e) for eid, e in sheet.entities.items() if eid not in before]
    out += [("model", e) for eid, e in submitted.doc.model_entities.items() if eid not in before]
    return out


# ------------------------------------------------------------- geometry


def wrap(angle: float) -> float:
    """An angle folded into (-180, 180]."""
    a = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def turn_between(a: float, b: float, period: float = 360.0) -> float:
    """The smallest turn from ``b`` to ``a``; ``period`` 180 ignores direction."""
    d = abs(wrap(a - b))
    return min(d, abs(180.0 - d)) if period == 180.0 else d


def unit(angle_deg: float) -> Tuple[float, float]:
    r = math.radians(angle_deg)
    return math.cos(r), math.sin(r)


def offset_from(p, origin, heading_deg: float) -> Tuple[float, float]:
    """``p`` relative to a line through ``origin`` at ``heading_deg``:
    ``(along, left)``, both in paper inches, left positive."""
    u = unit(heading_deg)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return dx * u[0] + dy * u[1], -dx * u[1] + dy * u[0]


def boxes_overlap(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> bool:
    """Do two convex quads overlap? (Separating axis test.)"""
    for quad in (a, b):
        for i in range(4):
            p, q = quad[i], quad[(i + 1) % 4]
            nx, ny = q[1] - p[1], p[0] - q[0]
            pa = [nx * c[0] + ny * c[1] for c in a]
            pb = [nx * c[0] + ny * c[1] for c in b]
            if max(pa) < min(pb) - 1e-12 or max(pb) < min(pa) - 1e-12:
                return False
    return True


def chains_from(plot: Plot, near, reach: float, snap: float = 0.01) -> List[Tuple[List[float], List[PSeg]]]:
    """Every open chain of segments that starts within ``reach`` of ``near``:
    ``(far end, segments)``. A leader leaving a curve bubble or a text is one
    of these; its far end is the tip."""
    segs = [s for s in plot.segs if not s.closed]
    out = []
    for i, s in enumerate(segs):
        for start, end in ((s.a, s.b), (s.b, s.a)):
            if math.dist(start, near) > reach or math.dist(end, near) <= math.dist(start, near):
                continue
            used, current, path = {i}, end, [s]
            while True:
                nxt = None
                for j, t in enumerate(segs):
                    if j in used:
                        continue
                    if math.dist(t.a, current) <= snap:
                        nxt = (j, t.b, t)
                        break
                    if math.dist(t.b, current) <= snap:
                        nxt = (j, t.a, t)
                        break
                if nxt is None:
                    break
                used.add(nxt[0])
                current = nxt[1]
                path.append(nxt[2])
            out.append((list(current), path))
    return out


def text_rows(texts: Sequence[PText], tol: float = 0.35) -> List[List[str]]:
    """Free texts lettered as a table: square to the sheet and sharing a
    baseline (within ``tol`` of a text height), read left to right. A single
    text holding a whole row is a row of one cell; the reader of the row
    finds the values inside it."""
    flat = [t for t in texts if turn_between(t.rotation, 0.0) <= 2.0 and "\n" not in t.content]
    rows: List[List[PText]] = []
    for t in sorted(flat, key=lambda t: -t.center()[1]):
        for row in rows:
            if abs(row[0].center()[1] - t.center()[1]) <= tol * max(row[0].height, t.height):
                row.append(t)
                break
        else:
            rows.append([t])
    out = []
    for row in rows:
        row.sort(key=lambda t: t.center()[0])
        out.append([t.content.strip() for t in row])
    return out


__all__ = ["PText", "PSeg", "PCircle", "PTable", "PDim", "Plot", "plot", "sheet_items", "wrap",
           "turn_between", "unit", "offset_from", "boxes_overlap", "chains_from", "text_rows"]
