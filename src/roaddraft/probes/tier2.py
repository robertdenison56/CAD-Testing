"""Tier-2 probes: harder tasks, for the agents that pass the first seventeen.

The find-probes are saturated -- a 9B model aims every callout by name at
0.00 ft -- and the drafting-probes separate models on four things: hand
arithmetic, width-vs-offset, stopping at a station, and keeping track of one's
own entities. Nothing in them measures the scope of a job that spans sheets,
the legibility of what is placed, geometry that involves two alignments,
checking an existing drawing, or carrying a design through to a plotted sheet.
These six do, one each, plus a loop:

* ``sheet-set-callouts`` -- the whole plan set, every sheet, every edge, named
  centerline, numbered title blocks: the T2 statement as one task.
* ``station-callouts`` -- every even station a sheet shows, text reading the
  station: fifteen near-identical calls without drift.
* ``clean-callouts`` -- three callouts that must be *legible*: text clear of
  linework, callouts clear of each other, everything inside the drawing area.
* ``draft-intersection-corner`` -- a curb return between two alignments, and
  the curb lines trimmed to it.
* ``draft-fix-the-drawing`` -- three mistakes planted in a finished drawing:
  find them, fix them, touch nothing else.
* ``draft-roadway-sheets`` -- the whole roadway, then a sheet that shows it at
  the scale asked for, title block filled.

The rules do not change. Every check judges the document on disk, never the
report. Aim is held to the find-probes' 1 ft and linework to the
drafting-probes' 0.5 ft. A probe passes however the work was done: callouts
composed by hand pair up with their text the same way place_callout's do, a
curb trimmed by editing its endpoint scores like one deleted and redrawn, and
the scripted solutions here are one route, not the route.

Two helpers carry most of the new weight. ``callouts`` pairs each text with
the chain of lines that leaves it and finds the far end, which is the tip --
so a check can ask what *this* callout says and where *it* points, not just
whether some text and some tip exist. ``paper_linework`` samples everything a
reader sees on a sheet, in paper inches: the sheet's own linework and the
model's, own and referenced, through each viewport. Clearance is judged
against that, with ``CLEAR_IN`` of air around the text.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.design.errors import DesignError
from roaddraft.document import viewmap
from roaddraft.document.entities import Arc, Circle, Entity, Line, Polyline, Text, entity_distance
from roaddraft.document.locate import resolve_entity
from roaddraft.document.references import reference_groups
from roaddraft.probes import drafting, fixture
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.drafting import (CL, EOP, NOTE, SHLD, along, between, clear, covered,
                                        expected_alignment, on_layer, run)
from roaddraft.probes.tasks import (TITLE_FIELDS, TOLERANCE_FT, added_by_space, aimed_at,
                                    ensure_layer, targets)

AIM_FT = TOLERANCE_FT                 # 1.0 ft: where a leader lands
LINE_FT = drafting.TOLERANCE_FT       # 0.5 ft: where linework lies
CLEAR_IN = 0.05                       # air around text on paper
STEP_IN = 0.05                        # paper sampling of linework
EDGE_IN = 0.25                        # a station this close to the window edge is optional
ALIGN = fixture.ALIGNMENT


# ------------------------------------------------------------- callouts


@dataclass
class Callout:
    """A text and the leader that leaves it. ``tip`` is the far end of the
    chain, in the callout's own space; None when the text has no leader.
    ``ids`` holds the text, the leader's pieces and any arrowhead at the tip."""
    text: Text
    tip: Optional[list] = None
    segments: List[Tuple[list, list]] = field(default_factory=list)
    ids: set = field(default_factory=set)


def _pieces(e: Entity) -> List[Tuple[list, list]]:
    """The straight pieces of a leader candidate; closed polylines are
    arrowheads, not leaders."""
    if isinstance(e, Line):
        return [(list(e.start), list(e.end))]
    if isinstance(e, Polyline) and not e.closed and len(e.vertices) >= 2:
        return [(list(a), list(b)) for a, b in zip(e.vertices, e.vertices[1:])]
    return []


def callouts(entities: Sequence[Entity], doc) -> List[Callout]:
    """Pair every text with its leader. The chain starts at the line end
    nearest the text (within 1.5 text heights of its box) and follows
    coincident ends until nothing continues it; where it stops is the tip.
    place_callout's leader, shoulder and text chain this way, and so does a
    single hand-drawn line from the text to the thing. A closed polyline with
    a vertex on the tip is the callout's arrowhead and belongs to it."""
    pieces: Dict[str, List[Tuple[list, list]]] = {}
    ends: List[Tuple[list, list, str]] = []           # (end, other end of that entity, id)
    heads = [e for e in entities if isinstance(e, Polyline) and e.closed]
    for e in entities:
        ps = _pieces(e)
        if not ps:
            continue
        pieces[e.id] = ps
        ends.append((ps[0][0], ps[-1][1], e.id))
        ends.append((ps[-1][1], ps[0][0], e.id))
    out = []
    for t in (e for e in entities if isinstance(e, Text)):
        box = t.bbox(doc)
        reach = 1.5 * t.height
        best = None
        for near, far, eid in ends:
            d = geo.dist_point_to_bbox(near, box)
            if d <= reach and (best is None or d < best[0]):
                best = (d, near, far, eid)
        if best is None:
            out.append(Callout(t, None, [], {t.id}))
            continue
        used, current = {best[3]}, best[2]
        snap = max(0.05 * t.height, 1e-6)
        while True:
            nxt = next(((far, eid) for near, far, eid in ends
                        if eid not in used and math.dist(near, current) <= snap), None)
            if nxt is None:
                break
            used.add(nxt[1])
            current = nxt[0]
        segments = [seg for eid in used for seg in pieces[eid]]
        arrows = {h.id for h in heads if any(math.dist(v[:2], current[:2]) <= snap for v in h.vertices)}
        out.append(Callout(t, list(current), segments, used | arrows | {t.id}))
    return out


def sheet_named(doc, name: str):
    return next((s for s in doc.sheets.values() if s.name.upper() == name.upper()), None)


def tip_in_model(submitted: Session, space_key: str, tip):
    """A tip in model feet: carried through the viewport it sits in when the
    callout is on a sheet; None when it sits outside every viewport."""
    sheet = submitted.doc.sheets.get(space_key)
    if sheet is None:
        return list(tip)
    vp = viewmap.viewport_under(sheet, tip)
    return None if vp is None else vp.transform().to_model(tip)


def sheet_callouts(baseline: Session, submitted: Session, sheet_name: str
                   ) -> List[Tuple[Callout, Optional[list]]]:
    """``(callout, tip in model feet)`` for every callout added to one sheet."""
    sheet = sheet_named(submitted.doc, sheet_name)
    if sheet is None:
        return []
    added = [e for _key, e in added_by_space(baseline, submitted, on_sheet=sheet.name)]
    return [(c, tip_in_model(submitted, sheet.id, c.tip) if c.tip else None)
            for c in callouts(added, submitted.doc)]


def lands_on(baseline: Session, ids: Sequence[str], point) -> bool:
    """Is a model point within AIM_FT of one of these fixture entities?"""
    if point is None:
        return False
    for eid in ids:
        found = resolve_entity(baseline.doc, eid)
        if found is not None and entity_distance(found[1], found[0], point) <= AIM_FT:
            return True
    return False


# --------------------------------------------------------- paper geometry


def _samples(e: Entity, step: float) -> List[list]:
    """Points every ``step`` along a line, polyline, arc or circle."""
    if isinstance(e, Line):
        return between(e.start, e.end, step)
    if isinstance(e, Polyline):
        verts = list(e.vertices) + ([e.vertices[0]] if e.closed and e.vertices else [])
        out = []
        for a, b in zip(verts, verts[1:]):
            out += between(a, b, step)
        return out
    if isinstance(e, (Arc, Circle)):
        if isinstance(e, Arc):
            s, t = geo.arc_sweep(e.start_angle_deg, e.end_angle_deg)
        else:
            s, t = 0.0, 360.0
        sweep = math.radians(t - s)
        n = max(1, int(math.ceil(e.radius * sweep / step)))
        return [[e.center[0] + e.radius * math.cos(math.radians(s) + sweep * i / n),
                 e.center[1] + e.radius * math.sin(math.radians(s) + sweep * i / n)]
                for i in range(n + 1)]
    return []


def paper_linework(session: Session, sheet, exclude: Sequence[str] = ()) -> List[list]:
    """Paper points along everything a reader sees on a sheet: its own
    linework and the model's -- own entities and referenced ones -- through
    each viewport. ``exclude`` leaves out entity ids (a callout's own leader)."""
    points = []
    for e in sheet.entities.values():
        if e.id not in exclude:
            points += _samples(e, STEP_IN)
    model = [e for e in session.doc.model_entities.values() if e.id not in exclude]
    for _ref, _base, prims in reference_groups(session.doc, "model"):
        model += prims
    for vp in sheet.viewports:
        to_paper = vp.transform().to_paper
        for e in model:
            for p in _samples(e, STEP_IN * vp.feet_per_inch):
                q = to_paper(p)
                if viewmap.in_window(vp, q):
                    points.append(q)
    return points


def _inside(box, p) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def _crosses(a, b, c, d) -> bool:
    r = geo.segment_intersection_params(a, b, c, d)
    if r is None:
        return False
    t, u = r
    return 1e-6 < t < 1 - 1e-6 and 1e-6 < u < 1 - 1e-6


def _fmt(p) -> str:
    return f"[{p[0]:.2f}, {p[1]:.2f}]"


# ------------------------------------------------------ the roadway, by sheet

ROADWAY = [
    ("the left edge of pavement", {"anchor": {"kind": "offset", "offset": -12.0}}),
    ("the right edge of pavement", {"anchor": {"kind": "offset", "offset": 12.0}}),
    ("the left edge of shoulder", {"anchor": {"kind": "offset", "offset": -20.0}}),
    ("the right edge of shoulder", {"anchor": {"kind": "offset", "offset": 20.0}}),
    ("the centerline", {"anchor": {"kind": "element"}}),
]
WORDING = {"the left edge of pavement": "EDGE OF PAVEMENT",
           "the right edge of pavement": "EDGE OF PAVEMENT",
           "the left edge of shoulder": "EDGE OF SHOULDER",
           "the right edge of shoulder": "EDGE OF SHOULDER",
           "the centerline": ALIGN}
AT = {"the left edge of pavement": 0.2, "the left edge of shoulder": 0.4,
      "the centerline": 0.55, "the right edge of pavement": 0.7,
      "the right edge of shoulder": 0.85}


def _paper_layer(session: Session) -> str:
    return ensure_layer(session, "rd_LAYOUT-NOTE-anno")


def _callout_on(session: Session, sheet: str, what: str, find: dict, dx: float, dy: float,
                content: Optional[str] = None):
    """The scripted route: find what the sheet shows, name it, put the text
    where it was asked to go."""
    r = session.query("find_entities", {**find, "visible_on": sheet, "limit": 50})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    if not r["entities"]:
        return None
    row = r["entities"][0]
    x, y = row["sheet_point"]
    return run(session, "place_callout", {
        "space": sheet, "target_entity": row["id"], "at": AT.get(what, 0.5),
        "position": [x + dx, y + dy], "content": content or WORDING[what],
        "layer": _paper_layer(session)})


# 1. the plan set --------------------------------------------------------------


def _title_block(sheet, number: int, total: int) -> Optional[str]:
    fields = {k: str(v).strip() for k, v in (sheet.title_block_fields or {}).items()}
    for key, value in TITLE_FIELDS.items():
        actual = fields.get(key, "")
        if key == "sheet_title":
            if not actual:
                return "title block: sheet_title is empty"
        elif actual.upper() != value.upper():
            return f"title block: {key}={actual!r} (wanted {value!r})"
    num = fields.get("sheet_number", "").upper()
    tot = fields.get("total_sheets", "").upper()
    if num not in (str(number), f"{number} OF {total}"):
        return f"title block: sheet_number={num!r} (wanted {number!r} or '{number} of {total}')"
    if tot != str(total) and f"OF {total}" not in num:
        return f"title block: total_sheets={tot!r} (wanted {total!r})"
    return None


def _check_sheet_set(baseline, submitted):
    placed = 0
    tally = Tally()
    for i, name in enumerate(fixture.SHEETS):
        sheet = sheet_named(submitted.doc, name)
        gone = f"sheet {name} is gone" if sheet is None else None
        for what, find in ROADWAY:
            wanted = targets(baseline, visible_on=name, **find)
            if not wanted:
                continue
            if gone:
                tally.add(f"{name}: {what}", gone)
                continue
            r = aimed_at(baseline, submitted, wanted, f"{what} on {name}", on_sheet=name)
            if tally.add(f"{name}: {what}", None if r.passed else f"{name}, {what}: {r.detail}"):
                placed += 1
        if gone:
            tally.add(f"{name}'s title block", gone)
            continue
        centerline = targets(baseline, visible_on=name, anchor={"kind": "element"})
        named = [c for c, tip in sheet_callouts(baseline, submitted, name)
                 if ALIGN in c.text.content.upper() and lands_on(baseline, centerline, tip)]
        tally.add(f"{name}: the centerline",
                  None if named else f"{name}: no callout on the centerline reads {ALIGN}")
        problem = _title_block(sheet, i + 1, len(fixture.SHEETS))
        tally.add(f"{name}'s title block", f"{name}: {problem}" if problem else None)
    return tally.result(f"{placed} callouts on paper across {len(fixture.SHEETS)} sheets, each "
                        f"on its edge, the centerline named, title blocks numbered 1 to "
                        f"{len(fixture.SHEETS)}")


def _solve_sheet_set(session):
    for i, name in enumerate(fixture.SHEETS):
        for what, find in ROADWAY:
            north = "left" in what or what == "the centerline"
            dy = 2.0 if north else -2.0
            if what == "the centerline":
                dy = 3.0
            _callout_on(session, name, what, find, 1.0, dy)
        run(session, "fill_title_block", {"sheet": name, "fields": {
            **TITLE_FIELDS, "sheet_number": str(i + 1), "total_sheets": str(len(fixture.SHEETS))}})


# 2. every station ---------------------------------------------------------------

STATION_SHEET = "C-101"


def _sr100_design():
    return expected_alignment(ALIGN, fixture.PIS, fixture.BEGIN_STATION)


def sheet_stations(baseline: Session, sheet_name: str = STATION_SHEET):
    """``(required, optional)``: the even 100 ft stations of SR-100 the sheet
    shows, as ``(station, model point, paper point)``. A station within EDGE_IN
    of the window's edge is optional: there to call out, not to fail on."""
    a = _sr100_design()
    sheet = sheet_named(baseline.doc, sheet_name)
    vp = sheet.viewports[0]
    x0, y0, x1, y1 = vp.paper_bbox()
    required, optional = [], []
    st = int(math.ceil(a.begin_station / 100.0)) * 100
    while st <= a.end_station:
        p = a.station_to_xy(float(st))[0]
        q = vp.transform().to_paper(p)
        if viewmap.in_window(vp, q):
            deep = (x0 + EDGE_IN <= q[0] <= x1 - EDGE_IN and y0 + EDGE_IN <= q[1] <= y1 - EDGE_IN)
            (required if deep else optional).append((st, p, q))
        st += 100
    return required, optional


def station_label(st: int) -> str:
    return f"{st // 100}+{st % 100:02d}"


def _check_stations(baseline, submitted):
    required, _optional = sheet_stations(baseline)
    pairs = sheet_callouts(baseline, submitted, STATION_SHEET)
    items = [(f"station {station_label(st)}", False) for st, _p, _q in required]
    if not pairs:
        if added_by_space(baseline, submitted):
            return Result(False, f"nothing was drawn on sheet {STATION_SHEET} itself -- this "
                                 f"probe wants the callouts in paper space, not in the model", items)
        return Result(False, "nothing was added to the document", items)
    missing, misread, items = [], [], []
    for st, p, _q in required:
        label = station_label(st)
        on_it = [c for c, tip in pairs if tip is not None and math.dist(tip, p) <= AIM_FT]
        if not on_it:
            missing.append(label)
        elif not any(label in c.text.content for c in on_it):
            misread.append(f"{label} reads {on_it[0].text.content!r}")
        items.append((f"station {label}", bool(on_it) and any(label in c.text.content for c in on_it)))
    if missing or misread:
        parts = []
        if missing:
            parts.append(f"{len(missing)} of {len(required)} stations have no leader on them: "
                         + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
        if misread:
            parts.append("text does not read the station: " + "; ".join(misread[:3]))
        return Result(False, "; ".join(parts), items)
    return Result(True, f"all {len(required)} stations {station_label(required[0][0])} to "
                        f"{station_label(required[-1][0])} called out on {STATION_SHEET}, each "
                        f"leader on its station and each text reading it", items)


def _solve_stations(session):
    required, optional = sheet_stations(session)
    layer = _paper_layer(session)
    for i, (st, _p, q) in enumerate(required + optional):
        run(session, "place_callout", {
            "space": STATION_SHEET, "target_anchor": station_label(st),
            "alignment": f"DESIGN:{ALIGN}", "position": [q[0] + 0.4, q[1] + (1.6 if i % 2 else -1.6)],
            "content": f"STA {station_label(st)}", "layer": layer})


# 3. legible callouts -------------------------------------------------------------

CLEAN_SHEET = "C-102"
CLEAN_TARGETS = [ROADWAY[0], ROADWAY[3], ROADWAY[4]]      # left edge, right shoulder, centerline


def _check_clean(baseline, submitted):
    name = CLEAN_SHEET
    tally = Tally()
    for what, find in CLEAN_TARGETS:
        r = aimed_at(baseline, submitted, targets(baseline, visible_on=name, **find),
                     f"{what} on {name}", on_sheet=name)
        tally.add(what, None if r.passed else f"{what}: {r.detail}")
    pairs = sheet_callouts(baseline, submitted, name) if tally.clean else []
    if tally.clean:
        tally.fail(_legibility_problem(baseline, submitted, name, pairs))
    return tally.result(f"{len(pairs)} callouts on {name}, each on its line, text clear of all "
                        f"linework by {CLEAR_IN} in, leaders clear of each other, all inside "
                        f"the drawing area")


def _legibility_problem(baseline, submitted, name: str, pairs) -> Optional[str]:
    """What makes the callouts on ``name`` hard to read, if anything: a text
    without a leader, anything outside the drawing area, text over linework,
    texts or leaders over each other."""
    sheet = sheet_named(submitted.doc, name)
    area = sheet.usable_area()
    for c, _tip in pairs:
        if c.tip is None:
            return f"the text {c.text.content!r} has no leader"
    added_ids = {e.id for _k, e in added_by_space(baseline, submitted, on_sheet=name)}
    scene = paper_linework(submitted, sheet, exclude=added_ids)
    for c, _tip in pairs:
        label = c.text.content.splitlines()[0]
        box = c.text.bbox(submitted.doc)
        if not geo.bbox_contains(area, box, tol=1e-6):
            return (f"the text {label!r} at {_fmt(c.text.position)} in lies outside "
                    f"the drawing area {tuple(round(v, 2) for v in area)}")
        for a, b in c.segments:
            for p in (a, b):
                if not _inside(area, p):
                    return f"the leader of {label!r} runs outside the drawing area at {_fmt(p)} in"
        clear_box = geo.bbox_expand(box, CLEAR_IN)
        hit = next((p for p in scene if _inside(clear_box, p)), None)
        if hit is not None:
            return (f"the text {label!r} sits over linework at {_fmt(hit)} in "
                    f"(less than {CLEAR_IN} in of air)")
        for other, _t in pairs:
            if other is c:
                continue
            olabel = other.text.content.splitlines()[0]
            if geo.bbox_intersects(clear_box, other.text.bbox(submitted.doc)):
                return f"the texts {label!r} and {olabel!r} overlap"
            for a, b in other.segments:
                if any(_inside(clear_box, p) for p in between(a, b, STEP_IN)):
                    return f"the leader of {olabel!r} runs through the text {label!r}"
                if any(_crosses(a, b, c2, d2) for c2, d2 in c.segments):
                    return f"the leaders of {label!r} and {olabel!r} cross"
    return None


def _solve_clean(session):
    _callout_on(session, CLEAN_SHEET, *CLEAN_TARGETS[0], dx=-1.0, dy=2.2)
    _callout_on(session, CLEAN_SHEET, *CLEAN_TARGETS[1], dx=1.0, dy=-2.2)
    _callout_on(session, CLEAN_SHEET, *CLEAN_TARGETS[2], dx=1.0, dy=3.0)


# 4. a curb return ------------------------------------------------------------------


def _corner():
    return fixture.corner_geometry(fixture.INTERSECTION["open"])


def _corner_points():
    """Where the return goes, where the curbs stay, and where they must go."""
    I, g = fixture.INTERSECTION, _corner()
    c, r = g["center"], g["radius"]
    s, e = g["start_deg"], g["end_deg"]
    if e < s:
        e += 360.0
    arc = [[c[0] + r * math.cos(math.radians(t)), c[1] + r * math.sin(math.radians(t))]
           for t in [s + (e - s) * i / 18 for i in range(19)]]
    main_y, cross_x = g["main_tp"][1], g["cross_tp"][0]
    corner = [cross_x, main_y]
    px, py = I["point"]
    main_end = px + g["east"] * I["main"]["leg"]
    cross_end = py + g["north"] * I["cross"]["leg"]
    ex, ny = g["east"], g["north"]
    # the arc leaves its tangent by 0.5 ft about 7 ft from the tangent point;
    # the "gone" stretch stops 8 ft short of it so the return itself is not blamed
    return {
        "arc": arc,
        "main_keep": between([g["main_tp"][0] + ex * 1.0, main_y], [main_end, main_y], 20.0),
        "cross_keep": between([cross_x, g["cross_tp"][1] + ny * 1.0], [cross_x, cross_end], 20.0),
        "main_gone": between([corner[0] + ex * 2.0, main_y], [g["main_tp"][0] - ex * 8.0, main_y], 2.0),
        "cross_gone": between([cross_x, corner[1] + ny * 2.0], [cross_x, g["cross_tp"][1] - ny * 8.0], 2.0),
    }


def _check_corner(baseline, submitted):
    pts = _corner_points()
    now = [e for e in submitted.doc.model_entities.values() if not isinstance(e, Text)]
    eop = [e for e in now if e.layer == EOP]
    g = _corner()
    main, cross = "MAIN ST's curb, trimmed to the return", "CROSS AVE's curb, trimmed to the return"
    return drafting.tallied([
        ("the curb return", on_layer(baseline, submitted, EOP, pts["arc"],
                                     f"the {g['radius']:g} ft curb return")),
        (main, covered(submitted, eop, pts["main_keep"], "MAIN ST's curb beyond the return")),
        (cross, covered(submitted, eop, pts["cross_keep"], "CROSS AVE's curb beyond the return")),
        (main, clear(submitted, now, pts["main_gone"],
                     "MAIN ST's curb between the return and the corner")),
        (cross, clear(submitted, now, pts["cross_gone"],
                      "CROSS AVE's curb between the return and the corner"))],
        f"a {g['radius']:g} ft return tangent to both curbs at {_fmt(g['main_tp'])} and "
        f"{_fmt(g['cross_tp'])}, both curb lines trimmed to it")


def _ne_pieces(session: Session) -> Dict[str, str]:
    """Ids of the two untrimmed curb pieces, by road."""
    I, g = fixture.INTERSECTION, _corner()
    px, py = I["point"]
    out = {}
    for road, offset in (("main", g["main_offset"]), ("cross", g["cross_offset"])):
        r = session.query("find_entities", {
            "anchor": {"alignment": I[road]["name"], "offset": offset},
            "bounds": [px + 1.0, py + 1.0, px + 2000.0, py + 2000.0], "limit": 10})
        if not r["ok"] or not r["entities"]:
            raise RuntimeError(f"no {road} curb piece at the open corner")
        out[road] = r["entities"][0]["id"]
    return out


def _solve_corner(session):
    I, g = fixture.INTERSECTION, _corner()
    run(session, "draw_arc", {"space": "model", "layer": EOP, "center": g["center"],
                              "radius": g["radius"], "start_angle_deg": g["start_deg"],
                              "end_angle_deg": g["end_deg"]})
    pieces = _ne_pieces(session)
    run(session, "delete_entities", {"ids": list(pieces.values())})
    main_end = I["main"]["begin"] + I["main"]["leg"] * (2 if g["east"] > 0 else 0)
    cross_end = I["cross"]["begin"] + I["cross"]["leg"] * (2 if g["north"] > 0 else 0)
    run(session, "draw_offset", {"alignment": I["main"]["name"], "offsets": [g["main_offset"]],
                                 "layer": EOP, "station_range": sorted([g["main_station"], main_end])})
    run(session, "draw_offset", {"alignment": I["cross"]["name"], "offsets": [g["cross_offset"]],
                                 "layer": EOP, "station_range": sorted([g["cross_station"], cross_end])})


# 5. QA an existing drawing --------------------------------------------------------


def _sr100(session: Session):
    return session.doc.design.alignments[ALIGN]


def planted(baseline: Session) -> dict:
    """The three mistakes build_flawed planted, found from the flawed document
    itself: the raw line on the pavement layer, the shoulder piece on the
    pavement layer, and the callout that reads EDGE OF PAVEMENT."""
    ents = list(baseline.doc.model_entities.values())
    raw = [e for e in ents if e.layer == EOP and isinstance(e, Line) and not e.anchor]
    mislayered = [e for e in ents if e.layer == EOP and e.anchor
                  and abs(e.anchor.get("offset", 0.0)) == abs(fixture.SHOULDER_OFFSETS[0])]
    callout = next(c for c in callouts(ents, baseline.doc)
                   if c.text.content.upper() == fixture.FLAWS["callout_text"])
    assert len(raw) == 1 and len(mislayered) == 1
    return {"edge": raw[0], "shoulder": mislayered[0], "callout": callout}


def _callout_fixed(a, submitted: Session, P: dict) -> Optional[str]:
    ents = list(submitted.doc.model_entities.values())
    ids = set(submitted.doc.model_entities)
    for c in callouts(ents, submitted.doc):
        if fixture.FLAWS["callout_text"] not in c.text.content.upper() or c.tip is None:
            continue
        try:
            off = abs(a.xy_to_station(c.tip)["offset"])
        except DesignError:
            continue
        if abs(off - abs(fixture.SHOULDER_OFFSETS[1])) <= AIM_FT:
            return (f"a callout reading {c.text.content!r} still points at the shoulder, "
                    f"{off:.1f} ft off centerline")
    old = P["callout"]
    if old.text.id not in ids and any(eid in ids for eid in old.ids if eid != old.text.id):
        return "the mislabelled callout's text was deleted but its leader or arrowhead was left behind"
    return None


def _nothing_else_changed(baseline: Session, submitted: Session, untouchable: set) -> Optional[str]:
    """Every fixture entity that was right must still be there: its points
    covered by linework on its own layer. Redrawn equivalently is fine."""
    doc = submitted.doc
    by_layer: Dict[str, list] = {}
    for e in doc.model_entities.values():
        if not isinstance(e, Text):
            by_layer.setdefault(e.layer, []).append(e)
    for e in baseline.doc.model_entities.values():
        if e.id in untouchable or isinstance(e, Text):
            continue
        pts = _samples(e, 100.0)
        gone = [p for p in pts if min((entity_distance(doc, f, p) for f in by_layer.get(e.layer, [])),
                                      default=math.inf) > LINE_FT]
        if gone:
            return (f"{e.id} on {e.layer} was changed or removed, which the task did not ask "
                    f"for (nothing on {e.layer} within {LINE_FT} ft of {_fmt(gone[0])})")
    return None


def _no_duplicates(a, submitted: Session) -> Optional[str]:
    doc = submitted.doc
    for layer, offset, what in ((EOP, -12.0, "the left edge of pavement"),
                                (EOP, 12.0, "the right edge of pavement"),
                                (SHLD, -20.0, "the left edge of shoulder"),
                                (SHLD, 20.0, "the right edge of shoulder")):
        ents = [e for e in doc.model_entities.values() if e.layer == layer and not isinstance(e, Text)]
        pts = along(a, offset, step=50.0)
        doubled = sum(1 for p in pts
                      if sum(entity_distance(doc, e, p) <= LINE_FT for e in ents) >= 2)
        if doubled > 0.5 * len(pts):
            return f"{what} is drawn twice: two pieces of {layer} linework on it at most points"
    return None


def _check_fix(baseline, submitted):
    a = _sr100(baseline)
    P = planted(baseline)
    e = P["edge"]
    st0, st1 = sorted(a.xy_to_station(p)["station"] for p in (e.start, e.end))
    now = [x for x in submitted.doc.model_entities.values() if not isinstance(x, Text)]
    eop = [x for x in now if x.layer == EOP]
    shld = [x for x in now if x.layer == SHLD]
    untouchable = {e.id, P["shoulder"].id} | P["callout"].ids
    edge = f"the right edge drawn at {fixture.FLAWS['edge_offset']:g} ft"
    shoulder = "the shoulder piece on rd_EP"
    tally = Tally()
    tally.add(edge, covered(submitted, eop, along(a, 12.0), "the right edge of pavement at 12 ft"))
    tally.add(edge, clear(submitted, now, along(a, fixture.FLAWS["edge_offset"], st0 + 5.0,
                                                st1 - 5.0, 20.0),
                          f"the hand-drawn piece at {fixture.FLAWS['edge_offset']:g} ft"))
    tally.add(shoulder, covered(submitted, shld, along(a, -20.0), "the left edge of shoulder on rd_ES"))
    tally.add(shoulder, clear(submitted, eop, along(a, -20.0, st0 + 5.0, st1 - 5.0, 20.0),
                              "shoulder linework on rd_EP"))
    tally.add("the callout that calls the shoulder the edge", _callout_fixed(a, submitted, P))
    tally.fail(_nothing_else_changed(baseline, submitted, untouchable))
    tally.fail(_no_duplicates(a, submitted))
    return tally.result(
        "the 11 ft piece replaced at 12 ft, the shoulder back on its layer, the callout no "
        "longer calls the shoulder the edge, and nothing else touched")


def _solve_fix(session):
    a = _sr100(session)
    P = planted(session)
    e = P["edge"]
    st0, st1 = sorted(a.xy_to_station(p)["station"] for p in (e.start, e.end))
    run(session, "delete_entities", {"ids": [e.id]})
    run(session, "draw_offset", {"alignment": ALIGN, "offsets": [12.0], "layer": EOP,
                                 "station_range": [round(st0, 2), round(st1, 2)]})
    run(session, "modify_entity", {"id": P["shoulder"].id, "changes": {"layer": SHLD}})
    run(session, "delete_entities", {"ids": sorted(P["callout"].ids)})
    edge = next(x for x in session.doc.model_entities.values()
                if isinstance(x, Line) and x.anchor and x.anchor.get("offset") == 12.0
                and (x.start[0] + x.end[0]) / 2.0 < fixture.PIS[1][0])
    tip = a.station_to_xy(1800.0, 12.0)[0]
    run(session, "place_callout", {"space": "model", "target_entity": edge.id, "at": 0.5,
                                   "position": [tip[0] + 120.0, tip[1] - 160.0],
                                   "content": fixture.FLAWS["callout_text"], "layer": NOTE})


# 6. the roadway, to paper -----------------------------------------------------------

RS = {"sheet": "C-101", "size": "ANSI_D", "feet_per_inch": 100.0, "project": "ELM AVE",
      "scale": "1\" = 100'"}


def _check_roadway_sheet(baseline, submitted):
    tally = Tally()
    tally.take(drafting._check_roadway(baseline, submitted))
    sheet = sheet_named(submitted.doc, RS["sheet"])
    if sheet is None:
        gone = (f"no sheet named {RS['sheet']} (sheets: "
                f"{[s.name for s in submitted.doc.sheets.values()]})")
        tally.add(f"sheet {RS['sheet']} and its viewport", gone)
        tally.add(f"{RS['sheet']}'s title block", gone)
        return tally.result("")
    tally.add(f"sheet {RS['sheet']} and its viewport", _roadway_viewport_problem(sheet))
    tally.add(f"{RS['sheet']}'s title block", _roadway_title_problem(sheet))
    return tally.result(f"ELM-AVE drafted, and {RS['sheet']} shows all of it through a "
                        f"1\"={RS['feet_per_inch']:g}' viewport inside the border, title block "
                        f"filled")


def _roadway_viewport_problem(sheet) -> Optional[str]:
    """Does the sheet show all of ELM-AVE at 1" = 100', inside its border?"""
    want = expected_alignment(drafting.ELM["name"], drafting._elm_pis(), drafting.ELM["begin"])
    if not sheet.viewports:
        return f"{RS['sheet']} has no viewport, so it shows nothing"
    vp = min(sheet.viewports, key=lambda v: abs(v.feet_per_inch - RS["feet_per_inch"]))
    if abs(vp.feet_per_inch - RS["feet_per_inch"]) > 0.01:
        return f"the viewport is at 1\"={vp.feet_per_inch:g}', not 1\"={RS['feet_per_inch']:g}'"
    if not geo.bbox_contains(sheet.usable_area(), vp.paper_bbox(), tol=0.05):
        return (f"the viewport {tuple(round(v, 2) for v in vp.paper_bbox())} in runs outside the "
                f"sheet's drawing area {tuple(round(v, 2) for v in sheet.usable_area())}")
    pts = along(want, step=25.0)
    edge = drafting.ELM["shoulder"]
    for st in (want.begin_station, want.end_station):
        pts += [want.station_to_xy(st, off)[0] for off in (-edge, edge)]
    shown = [viewmap.shows(vp, p) for p in pts]
    if not all(shown):
        n = len(pts)
        where = ("the start" if not shown[0] else "the end" if not shown[len(pts) - 5] else "part")
        return (f"the viewport shows {sum(shown)} of {n} points of ELM-AVE and its "
                f"shoulders; it misses {where} of the roadway")
    return None


def _roadway_title_problem(sheet) -> Optional[str]:
    fields = {k: str(v).strip() for k, v in (sheet.title_block_fields or {}).items()}
    if fields.get("project", "").upper() != RS["project"]:
        return f"title block: project={fields.get('project', '')!r} (wanted {RS['project']!r})"
    if not fields.get("sheet_title"):
        return "title block: sheet_title is empty"
    if fields.get("scale", "").upper() != RS["scale"].upper():
        return f"title block: scale={fields.get('scale', '')!r} (wanted {RS['scale']!r})"
    return None


def _solve_roadway_sheet(session):
    drafting._solve_roadway(session)
    x0, y0, x1, y1 = session.query("get_extents", {"space": "model"})["extents"]
    run(session, "create_sheet", {"name": RS["sheet"], "size": RS["size"]})
    run(session, "create_viewport", {"sheet": RS["sheet"], "center_paper": [17.0, 11.7],
                                     "width_in": 31.0, "height_in": 18.5,
                                     "model_center": [(x0 + x1) / 2.0, (y0 + y1) / 2.0],
                                     "feet_per_inch": RS["feet_per_inch"]})
    run(session, "fill_title_block", {"sheet": RS["sheet"], "fields": {
        "project": RS["project"], "sheet_title": "ROADWAY PLAN", "scale": RS["scale"]}})


TIER2_PROBES: List[Probe] = [
    Probe(id="sheet-set-callouts", start="sheets", tags=["tier2", "paper", "sheets", "multiple"],
          prompt="Annotate the plan set, sheets C-101 through C-103, in paper space. On every "
                 "sheet where they appear, call out the left and right edges of pavement "
                 "(EDGE OF PAVEMENT) and the left and right outside edges of shoulder (EDGE OF "
                 "SHOULDER), and call out the centerline with the name of its alignment, "
                 "SR-100. Then fill every title block: project SR-100 WIDENING, sheet title "
                 "ROADWAY PLAN, the sheet number and total (1 of 3, 2 of 3, 3 of 3), and the "
                 "scale 1\" = 50'.",
          check=_check_sheet_set, solve=_solve_sheet_set,
          note="The Sep 10 T2 statement as one task: fifteen callouts and three title blocks. "
               "Every target shows on every sheet here, so the check wants all of them; a run "
               "that stops after one sheet, or labels the centerline CENTERLINE, fails."),
    Probe(id="station-callouts", start="sheets", tags=["tier2", "paper", "station", "loop"],
          prompt="On sheet C-101, in paper space, call out every even 100 ft station of SR-100 "
                 "that the sheet shows (11+00, 12+00 and so on, as far as the view runs): one "
                 "callout per station, its leader on the centerline at that station and its "
                 "text reading the station.",
          check=_check_stations, solve=_solve_stations,
          note="Fifteen stations, 11+00 to 25+00. 10+00 sits on the window's edge and is "
               "optional. The text has to read 11+00, not 1100 or 11+00.00's neighbour; the "
               "leader has to land within 1 ft of the station, through the viewport."),
    Probe(id="clean-callouts", start="sheets", tags=["tier2", "paper", "legibility"],
          prompt="On sheet C-102, in paper space, call out the left edge of pavement (EDGE OF "
                 "PAVEMENT), the right outside edge of shoulder (EDGE OF SHOULDER) and the "
                 "centerline (SR-100). Draft them the way they would be checked on a plan: no "
                 "text may sit over any linework, no callout may cross another callout's text "
                 "or leader, and everything must lie inside the sheet's drawing area, clear of "
                 "the border and the title block.",
          check=_check_clean, solve=_solve_clean,
          note="The quality nobody has measured. The roadway is a 0.8 in band on this sheet "
               "and the text is 0.1 in high and over an inch long, so text dropped beside the "
               "tip lands on the shoulder line. A text-only agent has to reason about the "
               "paper; a vision agent can render the sheet and look."),
    Probe(id="draft-intersection-corner", start="intersection",
          tags=["tier2", "draft", "geometry", "two-alignments"],
          prompt="MAIN ST (alignment MAIN-ST, running east) and CROSS AVE (alignment CROSS-AVE, "
                 "running north) cross at MAIN-ST 18+00 / CROSS-AVE 27+00. Their curb faces are "
                 "drawn on rd_EP: MAIN ST's 44 ft either side of its centerline, CROSS "
                 "AVE's 32 ft either side. Three corners have their curb returns; the northeast "
                 "corner does not -- its two curb lines still run to meet at the corner. Draw "
                 "the northeast curb return on rd_EP, a 50 ft radius arc tangent to both "
                 "curb faces, and trim both curb lines back to where the return meets them.",
          check=_check_corner, solve=_solve_corner,
          note="Two alignments, no trigonometry: the centre is 50 ft inside each curb, at "
               "[5082, 5094], and the tangent points are square across, [5082, 5044] on MAIN "
               "ST and [5032, 5094] on CROSS AVE. The traps are the wrong corner, an arc "
               "centred on the corner itself, and curbs left running to it."),
    Probe(id="draft-fix-the-drawing", start="flawed", tags=["tier2", "draft", "qa", "edit"],
          prompt="QA this drawing of SR-100 against its typical section -- two 12 ft lanes and "
                 "8 ft paved shoulders: edges of pavement on rd_EP, outside edges of "
                 "shoulder on rd_ES, callouts on rd_LAYOUT-NOTE-anno -- and fix what is wrong. "
                 "Change nothing else.",
          check=_check_fix, solve=_solve_fix,
          note="Three mistakes are planted: a piece of the right edge redrawn by hand at 11 ft "
               "with no anchor record, a piece of the left shoulder on rd_EP, and a "
               "callout on the right shoulder that reads EDGE OF PAVEMENT. The check wants all "
               "three gone, every correct entity still covered, and nothing drawn twice."),
    Probe(id="draft-roadway-sheets", start="blank", tags=["tier2", "draft", "cogo", "whole-job", "sheets"],
          prompt=drafting.DRAFT_PROBES[-1].prompt +
                 " Then create sheet C-101 (ANSI D) with a viewport at 1\" = 100' that shows "
                 "the whole of ELM-AVE, shoulders included, and fill its title block: project "
                 "ELM AVE, sheet title ROADWAY PLAN, scale 1\" = 100'.",
          check=_check_roadway_sheet, solve=_solve_roadway_sheet,
          note="The parked D1 job in one prompt. The roadway part is draft-roadway's check "
               "unchanged; the sheet part wants a viewport at exactly 100 ft/in that shows "
               "every point of the alignment and its shoulder ends, inside the border. The "
               "design is about 2,000 ft long: at 1\"=50' it would not fit one sheet."),
]

__all__ = ["TIER2_PROBES", "Callout", "callouts", "sheet_callouts", "sheet_named",
           "tip_in_model", "lands_on", "paper_linework", "sheet_stations", "station_label",
           "planted", "AIM_FT", "LINE_FT", "CLEAR_IN"]
