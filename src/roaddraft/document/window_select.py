"""Window and crossing selection: the entities a dragged box takes in.

Dragging a box picks many entities at once, the AutoCAD and MicroStation
way. Which ones depends on the direction of the drag:

* a *window* (dragged left to right) takes only what lies wholly inside it;
* a *crossing* (dragged right to left) also takes whatever it touches.

Crossing is decided on the real geometry, not on bounding boxes: a diagonal
line whose box overlaps the window but which passes beside it is not taken.
Blocks, tables and dimensions are judged by the linework they draw, text by
its box, a hatch by its fill (a window inside a hatch touches it).

Only the space's own entities are considered -- reference elements are
read-only -- and nothing on a layer that is switched off, since a selection
nobody can see is one that gets deleted by accident.
"""
from __future__ import annotations

from typing import List

from roaddraft.core import geometry as geo
from roaddraft.document.clip import clip_primitives
from roaddraft.document.entities import (
    Entity, Hatch, Polyline, Text, expand_entities,
)


def window_ids(doc, entities, corner_a, corner_b, crossing: bool = False) -> List[str]:
    """Ids of the entities a box between two opposite corners selects: those
    wholly inside it, or with ``crossing`` those touching it too."""
    box = (min(corner_a[0], corner_b[0]), min(corner_a[1], corner_b[1]),
           max(corner_a[0], corner_b[0]), max(corner_a[1], corner_b[1]))
    ring = [[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]
    out = []
    for e in entities.values():
        layer = doc.layers.get(e.layer)
        if layer is not None and not layer.visible:
            continue
        bb = e.bbox(doc)
        if bb is None or not geo.bbox_intersects(bb, box):
            continue
        if geo.bbox_contains(box, bb) or (crossing and _touches(doc, e, box, ring)):
            out.append(e.id)
    return out


def _touches(doc, entity: Entity, box, ring) -> bool:
    for prim in expand_entities(doc, [entity]):
        if isinstance(prim, Text):
            bb = prim.bbox(doc)
            if bb is not None and geo.bbox_intersects(bb, box):
                return True
        elif isinstance(prim, Hatch):
            if _hatch_touches(prim, box, ring):
                return True
        elif clip_primitives([prim], boundary=ring):
            return True
    return False


def _hatch_touches(hatch: Hatch, box, ring) -> bool:
    from roaddraft.document.regions import point_in_loop
    middle = [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]
    if sum(1 for loop in hatch.loops if point_in_loop(middle, loop)) % 2:
        return True                      # the window sits in the fill
    for loop in hatch.loops:
        edge = Polyline(vertices=[list(v) for v in loop["vertices"]], closed=True,
                        bulges=list(loop.get("bulges") or []))
        if clip_primitives([edge], boundary=ring):
            return True
    return False


__all__ = ["window_ids"]
