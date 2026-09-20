"""Seeing the model through a viewport: model feet <-> sheet inches.

Plan annotation belongs on the sheet, in paper inches, so it neither scales nor
turns with the view. But what it points at lives in the model -- usually in a
referenced basefile -- and is only *seen* on the sheet, through a viewport that
has a centre, a scale and a twist. Getting from one to the other is a rotation
and a division that is easy to get slightly wrong by hand, and a leader that is
slightly wrong lands on the neighbouring line. So the engine does it.

Three questions are answered here:

* which viewport shows a model point, and where on the paper it falls;
* which part of an entity a viewport shows -- a pavement edge runs the length
  of the project while a sheet shows one stretch of it, so "the middle of the
  edge" has to mean the middle of what *this sheet* shows;
* what a point on the paper is looking at in the model.

Viewport choice follows ``place_label``: an explicit viewport wins, otherwise
the first one whose window shows the point.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from roaddraft.core import geometry as geo
from roaddraft.document.entities import Arc, Circle, Entity, Line, Polyline
from roaddraft.document.locate import point_at

EPS = 1e-9
#: Arcs are walked in steps no longer than this on paper, then the ends of each
#: visible run are refined by bisection. Anything that shows less than this
#: much of itself in a window is not there to point at.
ARC_STEP_IN = 0.05

Span = Tuple[float, float]


class ViewError(ValueError):
    """Something cannot be seen through a viewport. Carries a teaching hint."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


# ------------------------------------------------------------------ windows


def in_window(vp, paper_point, eps: float = EPS) -> bool:
    """Is a point on the paper inside this viewport's window?"""
    x0, y0, x1, y1 = vp.paper_bbox()
    return (x0 - eps <= paper_point[0] <= x1 + eps
            and y0 - eps <= paper_point[1] <= y1 + eps)


def shows(vp, model_point) -> bool:
    """Does this viewport show a model point?"""
    return in_window(vp, vp.transform().to_paper(model_point))


def viewport_named(sheet, viewport_id: str):
    vp = sheet.viewport_by_id(viewport_id)
    if vp is None:
        raise ViewError(f"viewport {viewport_id} is not on {sheet.name}",
                        hint=f"viewports: {[v.id for v in sheet.viewports]}")
    return vp


def describe_windows(sheet) -> str:
    """What each viewport of a sheet shows, for a hint."""
    if not sheet.viewports:
        return "the sheet has no viewport; create_viewport first"
    parts = []
    for vp in sheet.viewports:
        mb = vp.transform().visible_model_bbox(vp.width_in, vp.height_in)
        parts.append(f"{vp.id} shows x {mb[0]:.0f}..{mb[2]:.0f}, y {mb[1]:.0f}..{mb[3]:.0f}")
    return "viewports: " + "; ".join(parts)


def viewport_showing(sheet, model_point, explicit: Optional[str] = None):
    """The viewport that shows a model point, or None when none does. An
    explicit viewport is returned whether or not the point is inside it."""
    if explicit:
        return viewport_named(sheet, explicit)
    for vp in sheet.viewports:
        if shows(vp, model_point):
            return vp
    return None


def viewport_under(sheet, paper_point, explicit: Optional[str] = None):
    """The viewport whose window a paper point falls in, or None."""
    if explicit:
        return viewport_named(sheet, explicit)
    for vp in sheet.viewports:
        if in_window(vp, paper_point):
            return vp
    return None


# ------------------------------------------------------------ visible spans


def _clip_segment(a, b, box) -> Optional[Span]:
    """Liang-Barsky: the (t0, t1) of segment a->b inside an axis-aligned box."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for delta, low, high, origin in ((dx, box[0], box[2], a[0]),
                                     (dy, box[1], box[3], a[1])):
        if abs(delta) < 1e-15:
            if origin < low - EPS or origin > high + EPS:
                return None
            continue
        ta, tb = (low - origin) / delta, (high - origin) / delta
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t1 - t0 <= 1e-12:
            return None
    return t0, t1


def _merge(spans: List[Span]) -> List[Span]:
    merged: List[Span] = []
    for t0, t1 in sorted(spans):
        if merged and t0 <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], t1))
        else:
            merged.append((t0, t1))
    return merged


def _polyline_spans(entity: Polyline, to_paper, box) -> List[Span]:
    points = [list(v) for v in entity.vertices]
    if entity.closed and len(points) > 2:
        points.append(list(points[0]))
    lengths = [geo.distance(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 0:
        return []
    spans, walked = [], 0.0
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if length > 0:
            cut = _clip_segment(to_paper(a), to_paper(b), box)
            if cut is not None:
                spans.append(((walked + cut[0] * length) / total,
                              (walked + cut[1] * length) / total))
        walked += length
    return _merge(spans)


def _sampled_spans(owner, entity: Entity, vp, paper_length: float) -> List[Span]:
    """Visible runs of a curved entity: walk it, then bisect each run's ends."""
    transform = vp.transform()

    def inside(t: float) -> bool:
        return in_window(vp, transform.to_paper(point_at(owner, entity, t)[0]), 0.0)

    def edge(t_out: float, t_in: float) -> float:
        for _ in range(48):
            mid = (t_out + t_in) / 2.0
            if inside(mid):
                t_in = mid
            else:
                t_out = mid
        return t_in

    n = int(min(4096, max(64, math.ceil(paper_length / ARC_STEP_IN))))
    flags = [inside(i / n) for i in range(n + 1)]
    spans, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = 0.0 if i == 0 else edge((i - 1) / n, i / n)
        elif not flag and start is not None:
            spans.append((start, edge(i / n, (i - 1) / n)))
            start = None
    if start is not None:
        spans.append((start, 1.0))
    return [s for s in spans if s[1] - s[0] > 1e-12]


def visible_spans(owner, entity: Entity, vp) -> Optional[List[Span]]:
    """The parts of an entity a viewport shows, as ``(t0, t1)`` fractions of
    its length. ``[]`` when it shows none of it; None for an entity with no
    path (text, a block, a table), where there is nothing to take a part of."""
    transform = vp.transform()
    box = vp.paper_bbox()
    if isinstance(entity, Line):
        cut = _clip_segment(transform.to_paper(entity.start),
                            transform.to_paper(entity.end), box)
        return [] if cut is None else [cut]
    if isinstance(entity, Polyline):
        return _polyline_spans(entity, transform.to_paper, box)
    if isinstance(entity, (Arc, Circle)):
        if isinstance(entity, Arc):
            s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
            sweep = math.radians(e - s)
        else:
            sweep = 2.0 * math.pi
        return _sampled_spans(owner, entity, vp,
                              entity.radius * sweep / vp.feet_per_inch)
    return None


def is_visible(owner, entity: Entity, vp) -> bool:
    """Does the viewport show any of this entity?"""
    spans = visible_spans(owner, entity, vp)
    if spans is not None:
        return bool(spans)
    try:
        return shows(vp, point_at(owner, entity, "mid")[0])
    except ValueError:
        return False


def point_at_visible(owner, entity: Entity, where, vp):
    """``(model point, direction_deg, fraction shown)`` at ``where`` along the
    part of the entity the viewport shows, or None when it shows none of it.

    ``where`` means what it means to ``point_at`` -- start, mid, end or a
    fraction -- but measured along what is visible, so "mid" is the middle of
    the stretch on this sheet and the point is always one the reader can see.
    """
    from roaddraft.document.locate import as_fraction
    spans = visible_spans(owner, entity, vp)
    if spans is None:
        point, direction = point_at(owner, entity, where)
        return (point, direction, 1.0) if shows(vp, point) else None
    if not spans:
        return None
    shown = sum(t1 - t0 for t0, t1 in spans)
    want = as_fraction(where) * shown
    t = spans[-1][1]
    for t0, t1 in spans:
        if want <= (t1 - t0) + 1e-15:
            t = t0 + want
            break
        want -= t1 - t0
    point, direction = point_at(owner, entity, min(max(t, 0.0), 1.0))
    return point, direction, shown


def viewport_showing_entity(sheet, owner, entity: Entity, explicit: Optional[str] = None):
    """The viewport through which an entity is seen, or None."""
    if explicit:
        return viewport_named(sheet, explicit)
    for vp in sheet.viewports:
        if is_visible(owner, entity, vp):
            return vp
    return None


# ------------------------------------------------------------ what is there


def seen_at(doc, sheet, paper_point, explicit: Optional[str] = None):
    """What a point on the paper is looking at: ``(viewport, model point,
    (entity id, distance in feet) or None)``, or None outside every viewport.
    References are searched, so in a sheet file this finds the design."""
    from roaddraft.document.locate import nearest_entity
    vp = viewport_under(sheet, paper_point, explicit)
    if vp is None:
        return None
    model_point = vp.transform().to_model(paper_point)
    return vp, model_point, nearest_entity(doc, "model", model_point)


__all__ = ["ViewError", "ARC_STEP_IN", "in_window", "shows", "viewport_named",
           "describe_windows", "viewport_showing", "viewport_under", "visible_spans",
           "is_visible", "point_at_visible", "viewport_showing_entity", "seen_at"]
