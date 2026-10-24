"""The construction callouts of a redrafted plan sheet, read back for a task.

The redraft pipelines (``examples/*_redraft``) placed every published note
with ``place_callout`` on a layer of its own (``S-ANNO-CALL`` on Caltrans
sheets, ``S_ANNO_CALLOUT`` on the FHWA and FDOT ones), then lettered the note
as the sheet does: the head line where the engine's text was, the lines under
it as texts of their own.  Nothing in those files records what each callout
pointed at, so this module reads it back from the geometry: the leader
strokes on the callout layer are grouped by the ends they share, each group's
free end nearest a text is the note's end and the arrowhead's apex (or the
free end farthest from the note) is the tip, and the tip is projected onto
the sheet's referenced alignments through the viewport to give a station
and offset.

``real-construction-callouts`` (``tasks.real``) strips a spread of those
callouts from the sheet and hands the notes back with their stations and
offsets; the oracle re-places each with ``place_callout`` aimed by
``target_anchor`` at the note's end, where the published note stood.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment
from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Polyline, Text
from roaddraft.document.references import reference_alignments
from roaddraft.verify.legibility import text_quad

#: the layer each redraft pipeline put the published callouts on
CALLOUT_LAYERS = ("S-ANNO-CALL", "S_ANNO_CALLOUT")
#: callouts a task takes off a sheet: at least this many, at most that many, spread
#: along the line (an episode has 150 steps; a sheet can carry fifty notes)
MIN_NOTES = 3
MAX_NOTES = 12
#: a note's tip is a target when it projects onto a referenced alignment this close
MAX_OFFSET_FT = 200.0
#: two strokes join when an end of one is within this of the other (paper inches)
JOIN_IN = 1e-3
#: a note's text stands within this of its leader's end
TEXT_REACH_IN = 0.2
#: an arrowhead belongs to a leader when its apex sits within this of a free end
ARROW_REACH_IN = 0.02
#: a line of a note under its head: same left edge and turn, this close below
LINE_GAP_HEIGHTS = 2.2
_WORD = re.compile(r"[A-Za-z0-9]")


@dataclass
class PublishedCallout:
    """One published callout: its head text, the lines under it, the strokes
    and arrowhead of its leader, where the tip and the note's end are, and
    the target the tip projects to."""

    head: Text
    lines: List[Text]
    strokes: List[str]
    arrows: List[str]
    tip: List[float]
    outer: List[float]
    layer: str
    #: ``(reference name, alignment name, raw station, offset)`` or None
    target: Optional[Tuple[str, str, float, float]] = None
    on_sheet: bool = True

    @property
    def content(self) -> str:
        return "\n".join(t.content for t in self.lines)

    @property
    def ids(self) -> List[str]:
        return [t.id for t in self.lines] + list(self.strokes) + list(self.arrows)

    @property
    def height(self) -> float:
        return float(self.head.height)


def _key(p) -> Tuple[float, float]:
    return (round(float(p[0]), 3), round(float(p[1]), 3))


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def _quad_dist(p, quad) -> float:
    if geo.point_in_polygon(p, quad):
        return 0.0
    return min(_seg_dist(p, quad[i], quad[(i + 1) % 4]) for i in range(4))


def _components(strokes: List[Tuple[str, List[list]]]) -> List[List[Tuple[str, List[list]]]]:
    """Strokes grouped by touching: a shared end, or an end on another stroke."""
    parent = {sid: sid for sid, _ in strokes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, (sa, pa) in enumerate(strokes):
        ends_a = (pa[0], pa[-1])
        for sb, pb in strokes[i + 1:]:
            ends_b = (pb[0], pb[-1])
            hit = any(math.dist(p, q) < JOIN_IN for p in ends_a for q in ends_b)
            if not hit:
                hit = (any(_seg_dist(p, pb[k], pb[k + 1]) < JOIN_IN
                           for p in ends_a for k in range(len(pb) - 1))
                       or any(_seg_dist(q, pa[k], pa[k + 1]) < JOIN_IN
                              for q in ends_b for k in range(len(pa) - 1)))
            if hit:
                parent[find(sa)] = find(sb)
    groups: Dict[str, List[Tuple[str, List[list]]]] = {}
    for sid, pts in strokes:
        groups.setdefault(find(sid), []).append((sid, pts))
    return list(groups.values())


def _free_ends(members: Sequence[Tuple[str, List[list]]]) -> List[list]:
    """Ends of a group's strokes that no other stroke of the group touches."""
    count: Dict[Tuple[float, float], int] = {}
    ends = [p for _, pts in members for p in (pts[0], pts[-1])]
    for p in ends:
        count[_key(p)] = count.get(_key(p), 0) + 1
    out = []
    for p in ends:
        if count[_key(p)] != 1:
            continue
        on_other = any(_seg_dist(p, pts[k], pts[k + 1]) < JOIN_IN
                       for _, pts in members for k in range(len(pts) - 1)
                       if not (math.dist(p, pts[0]) < JOIN_IN or math.dist(p, pts[-1]) < JOIN_IN))
        if not on_other:
            out.append(list(p))
    return out


def published_callouts(doc: Document, sheet) -> List[PublishedCallout]:
    """The callouts on ``sheet`` (of ``doc``), read back from the callout layer;
    one per leader group that reaches a text.  Branching leaders (two
    arrowheads) and leaders that reach no text are left out."""
    vp = sheet.viewports[0]
    t = vp.transform()
    rect = tuple(vp.paper_bbox())
    ents = sheet.entities
    lines = [e for e in ents.values() if isinstance(e, Line) and e.layer in CALLOUT_LAYERS]
    polys = [e for e in ents.values() if isinstance(e, Polyline) and e.layer in CALLOUT_LAYERS]
    texts = [e for e in ents.values() if isinstance(e, Text) and e.layer in CALLOUT_LAYERS]
    arrows = [e for e in polys if e.closed and len(e.vertices) == 3]
    strokes = ([(e.id, [list(e.start), list(e.end)]) for e in lines]
               + [(e.id, [list(v) for v in e.vertices]) for e in polys if e not in arrows])
    quads = {tx.id: text_quad(tx.position, tx.content, tx.height, tx.rotation_deg, tx.halign,
                              tx.valign, 1.0) for tx in texts}
    aligns = [(ref, align) for ref, _base, align, placement in reference_alignments(doc)
              if placement.is_identity]
    out: List[PublishedCallout] = []
    used: set = set()
    for members in _components(strokes):
        free = _free_ends(members)
        if not free:
            continue
        heads = [a for a in arrows
                 if any(math.dist(a.vertices[0], p) < ARROW_REACH_IN for p in free)]
        best = None
        for tx in texts:
            if tx.id in used:
                continue
            d = min(_quad_dist(p, quads[tx.id]) for p in free)
            if d < TEXT_REACH_IN and (best is None or d < best[0]):
                best = (d, tx)
        if best is None or len(heads) > 1:
            continue
        head = best[1]
        if heads:
            tip = list(heads[0].vertices[0])
        else:
            far = [p for p in free if _quad_dist(p, quads[head.id]) > TEXT_REACH_IN]
            if not far:
                continue
            tip = max(far, key=lambda p: _quad_dist(p, quads[head.id]))
        outer = min(free, key=lambda p: _quad_dist(p, quads[head.id]))
        used.add(head.id)
        note = [head]
        while True:  # the lines of the note under its head
            last = note[-1]
            below = [o for o in texts if o.id not in used
                     and abs(o.rotation_deg - last.rotation_deg) < 0.5
                     and abs(o.position[0] - last.position[0]) < 0.08
                     and 0 < (last.position[1] - o.position[1]) < LINE_GAP_HEIGHTS * head.height
                     and o.height <= head.height * 1.15]
            if not below:
                break
            below.sort(key=lambda o: last.position[1] - o.position[1])
            used.add(below[0].id)
            note.append(below[0])
        target = None
        model_tip = t.to_model(tip)
        for ref, align in aligns:
            try:
                r = align.xy_to_station(model_tip)
            except DesignError:
                continue
            if target is None or abs(float(r["offset"])) < abs(target[3]):
                target = (ref.name, align.name, float(r["station"]), float(r["offset"]))
        out.append(PublishedCallout(
            head=head, lines=note, strokes=[sid for sid, _ in members],
            arrows=[a.id for a in heads], tip=[float(tip[0]), float(tip[1])],
            outer=[float(outer[0]), float(outer[1])], layer=head.layer, target=target,
            on_sheet=(rect[0] <= tip[0] <= rect[2] and rect[1] <= tip[1] <= rect[3])))
    return out


def task_notes(callouts: Sequence[PublishedCallout]) -> List[PublishedCallout]:
    """The callouts a task hands back: those whose tip is inside the plan view
    and projects onto a referenced line within ``MAX_OFFSET_FT``, with a note
    worth reading, up to ``MAX_NOTES`` spread along the lines in station
    order (the rest stay on the sheet as given)."""
    fit = [c for c in callouts
           if c.on_sheet and c.target is not None and abs(c.target[3]) <= MAX_OFFSET_FT
           and _WORD.search(c.content) and abs(float(c.head.rotation_deg)) <= 1.0]
    fit.sort(key=lambda c: (c.target[1], c.target[2], c.head.id))
    n = len(fit)
    if n <= MAX_NOTES:
        return fit
    picks = sorted({round(i * (n - 1) / (MAX_NOTES - 1)) for i in range(MAX_NOTES)})
    return [fit[i] for i in picks]


def note_rows(notes: Sequence[PublishedCallout], alignments: Dict[str, Alignment]) -> List[dict]:
    """The deliverable's callout rows: what the brief says and the oracle draws.
    Stations to the hundredth and offsets to the tenth of a foot (the tip
    moves under a thousandth of an inch on paper).  ``position`` is where
    ``place_callout`` puts the note so that its text fills the box the
    published note stood in: the engine letters from its position outward,
    away from the target, centred on it vertically."""
    rows = []
    for n, c in enumerate(notes, start=1):
        ref, name, station, offset = c.target
        st = alignments[name].stations()
        raw = round(station, 2)
        head = c.head
        quad = text_quad(head.position, head.content, head.height, head.rotation_deg,
                         head.halign, head.valign, 1.0)
        left, right = min(p[0] for p in quad), max(p[0] for p in quad)
        top = max(p[1] for p in quad)
        _w, block = geo.text_size(c.content, c.height)
        from_left = c.tip[0] <= (left + right) / 2.0
        position = [left if from_left else right, top - block / 2.0]
        rows.append({"ref": f"N-{n}", "content": c.content, "reference": ref, "alignment": name,
                     "station": raw, "station_text": st.format(raw),
                     "offset": round(offset, 1), "position": [round(v, 3) for v in position],
                     "height": round(c.height, 3), "arrow": bool(c.arrows), "layer": c.layer})
    return rows


__all__ = ["CALLOUT_LAYERS", "MIN_NOTES", "MAX_NOTES", "MAX_OFFSET_FT", "PublishedCallout",
           "published_callouts", "task_notes", "note_rows"]
