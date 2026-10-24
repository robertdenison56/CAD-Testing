"""Pilot 11: a checker's redlines whose effects ripple through the sheet.

A finished sheet comes back from checking with one red markup on layer
REDLINE: a revision cloud, a leader and a note. The note names one change to
the design. Picking it up is three jobs nobody spells out. The design has to
change where it lives, in the base file the sheet references (``AA01``), not in
the lettering. Every piece of lettering, table cell and station callout the
change touches has to be found and brought up to date, and nothing else
touched. And the revision has to be recorded in the border's revision block,
with the markup taken off the sheet.

The engine does not do the cascade. ``modify_alignment`` changes the design
and warns that the entities anchored to it "were not regenerated"; across
files it does not even warn, since the sheet's labels are anchored *through
the reference* (``AA01:WS``) and the base knows nothing of them. Old
lettering keeps its old text and its old place, so the cascade is the
model's job even though the labels are anchored, and there was no need to
start from plain text. Starting anchored is also what lets the E1 verifier
grade the result. The sheets carry the alignment data a ``real-alignment-data``
task letters (``tasks.real.build_real_task`` with ``tasks.reference``'s
reference solution: ticks and Caltrans station numbers, BC/EC, bearings, the
curve bubble, a CURVE DATA table). The prompt says it is anchored and asks
the model to keep it that way, because that is the convention the verifier
credits.

* ``p11-radius-ppm160``: Caltrans PD-1 (Route 78 pavement delineation and
  sign plan, 1" = 50', twist 28°). The redline reads REVISE CURVE 1 "WS" LINE,
  R = 1500', HOLD PI. The "WS" line was rebuilt from the published sheet as
  elements, so it has no PIs to edit. The model has to recover them (the
  engine's key_points gives the PI) and re-make the alignment in PI form with
  the new radius. That moves the BC 38 ft ahead and the EC 37 ft back. It
  shortens T from 150.46' to about 112.9' and L from 300.36' to about
  225.4', adds 37.5 ft to both tangents, and shifts the end station. The
  rebuilt line's tangents meet its curve with 20" kinks, so the curve's own PI
  and the tangents' crossing lie 0.02 ft apart; either may be held, and the
  bearings and delta move by seconds accordingly. The bearing labels
  (which carry the tangent lengths), the BC and EC, the bubble, the table's
  R, T and L, the downstream station numbers and the centerline drawn in
  AA01 all have to follow.
* ``p11-station-ppm045``: Caltrans L-1 (Route 65 layout, twist -89.94°). The
  redline reads REVISE "TB1" STATIONING: +25.00', BEGIN "TB1" = 639+19.58.
  Geometry, bearings and the curve table stay as they are. Every station on
  "TB1" moves: each tick (25 ft along the line), each station number, the BC
  and EC. The knock-on edit nobody names is that two of the published
  callouts on the sheet cite "TB1" stations: ``"TB1" 645+66.69`` and the
  ramp tie ``"TB1" 647+73.40 POT= 63.32' Rt "D13" 647+73.40 POT``. Both must
  gain 25 ft on their "TB1" station, while the "D13" station in the tie must
  not change.

Neither instance has a match line on the revised alignment: "TB1" ends at its
tie to "D13" short of L-1's match line, and PD-1's match line is on the "B"
line. So the match-line item of the brief does not arise here.

Grading reads only the documents: the sheet file and the base files saved
beside it. The truth is recomputed from the revised design
(``tasks.ground_truth.compute_ground_truth`` on the real task's brief with
the design swapped). That is the design the model saved when it is within
tolerance of the asked revision, so lettering is judged against the design
it was lettered from, and otherwise the revision made by the engine itself.
The items:

1. the design: the radius (PIs, begin and end held within 0.06 ft), or the
   begin station (to the hundredth, geometry unchanged);
2. the centerline drawn in AA01 lies on the revised alignment, sampled,
   within 0.05 ft, and covers it;
3. to 7. the E1 verifier (``roaddraft.verify.verify``, vague level) with full
   credit on ticks (D1-02), station numbers (D1-03), BC/EC and the bubble
   (D1-04), bearings (D1-05) and the curve table (D1-06). Placement,
   legibility and layers (D1-07 to D1-09) are not required;
8. nothing stale or lettered twice: no verifier ``duplicate`` or
   ``anchor_inconsistent`` finding, no anchored label more than 0.25 in from
   where its own anchor now puts it, no tick-sized line square across the
   alignment at a station that is not a 100-ft station, and no text anywhere
   in the sheet file still reading an old value (old BC/EC stations, old
   tangent lengths, old R/T/L);
9. (station instance) each callout citing "TB1" reads its station plus
   25 ft, within 0.2 ft because the published lettering and the rebuilt line
   differ by up to 0.13 ft, and the old station is gone;
10. the redline is gone: nothing on layer REDLINE, no text with the note;
11. the revision is recorded, initials RD and the date 10-19-26 in any
    format: in the Caltrans border's REVISED BY / DATE REVISED cells
    (``revised_by_N`` / ``date_revised_N``), or, since nothing the model is
    shown names those keys, in any title block field whose key says
    revision, or in a new revision note on the sheet;
12. nothing unrelated changed. Every other entity of the sheet file, every
    other title block field, the other alignments and model entities of
    AA01 and all of BB01 stay as they were. The callouts' own leaders may
    be redrawn.

Naive wrong answers this catches (``tests/test_pilot_redlines.py``):
changing the design and nothing else (stale lettering: D1-04/05/06 fail);
re-lettering on the sheet without changing AA01 (the design item fails); and,
for the station change, re-lettering the alignment data but leaving the two
callouts at their old stations.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from roaddraft.api.session import Session
from roaddraft.design.horizontal import Alignment
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Line, Polyline, Table, Text
from roaddraft.document.references import find_reference_alignment, resolve_reference
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.core import geometry as geo
from roaddraft.probes.pilot import common, repairs
from roaddraft.tasks.brief import GroundTruth, Task, TaskBrief
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.real import build_real_task
from roaddraft.tasks.reference import phase_commands, reference_solution, session_for_task

DESIGN_FILE = "0000000000aa01.rdraft"
DESIGN_REF = "AA01"
REDLINE = "REDLINE"
#: what the prompt asks to be written in the revision block
REVISED_BY = "RD"
REVISED_ON = "10-19-26"

DESIGN_TOL_FT = 0.06       # PIs, begin and end held
CENTERLINE_TOL_FT = 0.05   # the drawn centerline on the revised alignment
FAR_IN = 0.25              # an anchored label this far off its anchor is stale
CALLOUT_TOL_FT = 0.2       # a cited station: the published value or the rebuilt line's
TICK_TOL_FT = 0.5          # a tick off a 100-ft station by more is stale
PAPER_CLOUD_PAD_IN = 0.35


@dataclass
class Redline:
    id: str
    sheet_id: str               # the redrafted sheet (common.row)
    sheet: str                  # its sheet name
    alignment: str
    kind: str                   # "radius" | "station"
    value: float                # the new radius, or the shift in feet
    note: List[str]             # the redline's lettering, line by line
    cloud: Tuple[float, float]  # raw stations the cloud wraps (from, to)
    cloud_offsets: Tuple[float, float] = (-45.0, 45.0)
    text_at: Tuple[float, float] = (0.0, 0.0)   # the note's insertion point, paper inches
    note_text: str = ""


RADIUS = Redline(
    id="p11-radius-ppm160", sheet_id="PPM-160", sheet="PD-1", alignment="WS", kind="radius",
    value=1500.0, note=['REVISE CURVE 1 "WS" LINE', "R = 1500'", "HOLD PI"],
    cloud=(84290.0, 84650.0), cloud_offsets=(-40.0, 40.0), text_at=(18.7, 5.25))

STATION = Redline(
    id="p11-station-ppm045", sheet_id="PPM-045", sheet="L-1", alignment="TB1", kind="station",
    value=25.0, note=['REVISE "TB1" STATIONING: +25.00\'', 'BEGIN "TB1" = 639+19.58'],
    cloud=(63894.6, 64200.0), cloud_offsets=(-25.0, 25.0), text_at=(5.4, 5.6))

INSTANCES = [RADIUS, STATION]


# ------------------------------------------------------------------ the task


@lru_cache(maxsize=None)
def _task(inst_id: str) -> Task:
    inst = _instance(inst_id)
    return build_real_task(inst.sheet_id, inst.alignment, "real-alignment-data")


def _instance(inst_id: str) -> Redline:
    return next(i for i in INSTANCES if i.id == inst_id)


def _qualified(inst: Redline) -> str:
    return f"{DESIGN_REF}:{inst.alignment}"


@lru_cache(maxsize=None)
def _pristine(inst_id: str, name: str) -> Document:
    """A base file as the start ships it."""
    return Document.from_dict(copy.deepcopy(_task(inst_id).files[name]))


def _original(inst: Redline) -> Alignment:
    return Alignment.from_dict(_task(inst.id).brief.design["alignments"][inst.alignment])


def _key(points: List[dict], design: str) -> List[float]:
    return list(next(p["point"] for p in points if p.get("design") == design))


def apply_revision(inst: Redline, base: Session) -> None:
    """The redline's change, made on a session over the base file, the way an
    agent makes it: the PI from key_points and the alignment re-made in PI form
    with the new radius (the drawn centerline redrawn), or the begin station."""
    name = inst.alignment
    if inst.kind == "radius":
        pts = common.ok(base.query("key_points", {"alignment": name}))["points"]
        pis = [_key(pts, "begin"), _key(pts, "pi") + [inst.value], _key(pts, "end")]
        common.ok(base.execute("modify_alignment", {"name": name, "changes": {"pis": pis},
                                                    "redraw": True}))
    else:
        align = base.doc.design.alignments[name]
        new = align.stations().format(align.begin_station + inst.value)
        common.ok(base.execute("modify_alignment", {"name": name,
                                                    "changes": {"begin_station": new}}))


@lru_cache(maxsize=None)
def _intended(inst_id: str) -> dict:
    """The revised alignment as the engine makes it from the start's base."""
    inst = _instance(inst_id)
    s = Session(_document=Document.from_dict(copy.deepcopy(_task(inst_id).files[DESIGN_FILE])))
    apply_revision(inst, s)
    return s.doc.design.alignments[inst.alignment].to_dict()


def revised_truth(inst: Redline, design: dict) -> GroundTruth:
    """The real task's truth, recomputed on a brief whose design carries the change."""
    task = _task(inst.id)
    bd = copy.deepcopy(task.brief.to_dict())
    bd["design"]["alignments"][inst.alignment] = copy.deepcopy(design)
    align = Alignment.from_dict(design)
    for sh in bd["deliverable"]["sheets"]:
        sh["station_range"] = [float(align.begin_station), float(align.end_station)]
    truth = compute_ground_truth(TaskBrief.from_dict(bd))
    for tsh, osh in zip(truth.sheets, task.truth.sheets):
        tsh["given_entities"] = list(osh.get("given_entities") or [])
        tsh["stripped"] = copy.deepcopy(osh.get("stripped") or {})
    return truth


# ------------------------------------------------------------------ the start


def _paper(vp, align: Alignment, raw: float, offset: float = 0.0) -> List[float]:
    raw = min(max(raw, align.begin_station), align.end_station)
    return vp.transform().to_paper(align.station_to_xy(raw, offset)[0])


def _cloud(box: Tuple[float, float, float, float], step: float = 0.35) -> Tuple[list, list]:
    """A revision cloud round a paper box: vertices along it, every segment an
    arc bulging out."""
    x0, y0, x1, y1 = box
    corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    verts = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        n = max(1, int(round(math.dist(a, b) / step)))
        verts += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n)]
    return verts, [0.6] * len(verts)   # counter-clockwise round the box, each scallop bulging out


def plant_redline(inst: Redline, session: Session) -> List[str]:
    """Draw the checker's markup on the sheet: the cloud, the note, a leader."""
    doc = session.doc
    sheet = next(s for s in doc.sheets.values() if s.name == inst.sheet)
    vp = sheet.viewports[0]
    align, _place = find_reference_alignment(doc, _qualified(inst))
    pts = []
    a, b = inst.cloud
    n = 24
    for k in range(n + 1):
        raw = a + (b - a) * k / n
        for off in inst.cloud_offsets:
            pts.append(_paper(vp, align, raw, off))
    pad = PAPER_CLOUD_PAD_IN
    box = (min(p[0] for p in pts) - pad, min(p[1] for p in pts) - pad,
           max(p[0] for p in pts) + pad, max(p[1] for p in pts) + pad)
    common.ok(session.execute("create_layer", {"name": REDLINE, "color": "red",
                                               "lineweight_mm": 0.35}))
    verts, bulges = _cloud(box)
    common.ok(session.execute("draw_polyline", {"space": sheet.name, "layer": REDLINE,
                                                "vertices": verts, "bulges": bulges,
                                                "closed": True}))
    tx, ty = inst.text_at
    h = 0.16
    common.ok(session.execute("place_text", {"space": sheet.name, "layer": REDLINE,
                                             "position": [tx, ty], "height": h,
                                             "content": "\n".join(inst.note),
                                             "halign": "left", "valign": "top"}))
    # the leader: from the note's nearer edge to the cloud's nearest corner
    cx = box[0] if abs(box[0] - tx) < abs(box[2] - tx) else box[2]
    cy = box[1] if abs(box[1] - ty) < abs(box[3] - ty) else box[3]
    start = [tx - 0.08, ty - 0.1] if cx < tx else [tx + 0.08 + 0.12 * len(inst.note[0]) * h / 0.16, ty - 0.1]
    common.ok(session.execute("draw_line", {"space": sheet.name, "layer": REDLINE,
                                            "start": start, "end": [cx, cy]}))
    return [e.id for e in sheet.entities.values() if e.layer == REDLINE]


def _builder(inst: Redline):
    def build(out: Path) -> Path:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        task = _task(inst.id)
        session = session_for_task(task, out_dir=out)
        reference_solution(task, session)
        for key in ("task_id", "spec_version"):
            session.doc.meta.pop(key, None)
        plant_redline(inst, session)
        path = common.save(session, out / common.sheet_file(inst.sheet_id))
        repairs.apply(out, inst.sheet_id)      # what the redraft left (repairs.py)
        if inst.id == STATION.id:
            _restore_tb2(out)
        return path
    return build


#: L-1's other curve: the real task strips the CURVE DATA table that held both lines'
#: curves and the reference letters TB1's alone, so TB2's row and bubble come back
TB2_RING = "PL-004"       # TB2's bubble ring on the sheet (its number the redraft lost)
TB1_RING = "PL-005"       # TB1's published ring, empty beside the reference's bubble
TB2_NUMBER = "2"          # TB1's anchored bubble is 1, so TB2's curve is 2
TABLE_GAP_IN = 0.25


def _restore_tb2(out: Path) -> None:
    s = common.load(out / common.sheet_file(STATION.sheet_id))
    sheet = next(iter(s.doc.sheets.values()))
    table = next(e for e in sheet.entities.values() if isinstance(e, Table))
    ring = sheet.entities[TB2_RING]
    centre = [sum(p[0] for p in ring.vertices) / len(ring.vertices),
              sum(p[1] for p in ring.vertices) / len(ring.vertices)]
    common.ok(s.execute("place_text", {"space": sheet.name, "layer": ring.layer, "position": centre,
                                       "height": 0.12, "halign": "center", "valign": "middle",
                                       "content": TB2_NUMBER}))
    old = sheet.entities[TB1_RING]
    oc = [sum(p[0] for p in old.vertices) / len(old.vertices),
          sum(p[1] for p in old.vertices) / len(old.vertices)]
    gone = [TB1_RING] + [e.id for e in sheet.entities.values() if isinstance(e, Line)
                         and min(geo.distance(e.start, oc), geo.distance(e.end, oc)) <= 0.25]
    common.ok(s.execute("delete_entities", {"ids": gone}))
    bb = table.bbox(s.doc)
    common.ok(s.execute("place_curve_table", {
        "space": sheet.name, "alignment": f"{DESIGN_REF}:TB2",
        "position": [bb[0], bb[1] - TABLE_GAP_IN],
        "text_height": float(table.text_height), "layer": table.layer,
        "first_curve_number": int(TB2_NUMBER)}))
    common.save(s, out / common.sheet_file(STATION.sheet_id))


for _inst in INSTANCES:
    common.register(_inst.id, common.sheet_file(_inst.sheet_id), _builder(_inst))


# ------------------------------------------------------------------ reading


def _norm(text: str) -> str:
    t = (text or "").upper()
    for a in "’′‘`":
        t = t.replace(a, "'")
    for a in "”“″":
        t = t.replace(a, '"')
    return " ".join(t.split())


def _sheet(session: Session, name: str):
    return next((s for s in session.doc.sheets.values() if s.name == name), None)


def _all_texts(session: Session) -> List[Tuple[str, str]]:
    """``(entity id, content)`` of every text and table cell the sheet file holds."""
    out = []
    spaces = [session.doc.model_entities] + [s.entities for s in session.doc.sheets.values()]
    for ents in spaces:
        for e in ents.values():
            if isinstance(e, Text):
                out.append((e.id, e.content))
            elif isinstance(e, Table):
                out.append((e.id, " | ".join(str(c) for r in e.rows for c in r)))
                out.append((e.id, e.title or ""))
    return out


def _lettering_ids(session: Session, inst: Redline) -> set:
    """The alignment's own lettering in the start: everything anchored to it."""
    q = _qualified(inst)
    spaces = [session.doc.model_entities] + [s.entities for s in session.doc.sheets.values()]
    return {e.id for ents in spaces for e in ents.values()
            if e.anchor and e.anchor.get("alignment") == q}


def _references(session: Session) -> Dict[str, Optional[Document]]:
    out = {}
    for ref in session.doc.references.values():
        base, _err = resolve_reference(session.doc, ref)
        out[ref.name] = base
    return out


def _submitted_alignment(submitted: Session, inst: Redline) -> Optional[Alignment]:
    base = _references(submitted).get(DESIGN_REF)
    if base is None:
        return None
    return base.design.alignments.get(inst.alignment)


def _pi_of(align: Alignment) -> Optional[List[float]]:
    """Where the first and last tangents' lines cross."""
    ts = align.tangents()
    if len(ts) < 2:
        return None
    a, b = ts[0], ts[-1]
    ua = [math.cos(math.radians(a.direction_deg)), math.sin(math.radians(a.direction_deg))]
    ub = [math.cos(math.radians(b.direction_deg)), math.sin(math.radians(b.direction_deg))]
    den = ua[0] * ub[1] - ua[1] * ub[0]
    if abs(den) < 1e-12:
        return None
    dx, dy = b.start[0] - a.start[0], b.start[1] - a.start[1]
    t = (dx * ub[1] - dy * ub[0]) / den
    return [a.start[0] + ua[0] * t, a.start[1] + ua[1] * t]


def _ends(align: Alignment) -> Tuple[List[float], List[float]]:
    return align.point_at(0.0), align.point_at(align.length)


def _design_problem(inst: Redline, now: Optional[Alignment]) -> Optional[str]:
    old = _original(inst)
    name = f'"{inst.alignment}"'
    if now is None:
        return f"{DESIGN_REF} no longer carries {name}"
    b0, e0 = _ends(old)
    b1, e1 = _ends(now)
    if math.dist(b0, b1) > DESIGN_TOL_FT or math.dist(e0, e1) > DESIGN_TOL_FT:
        return f"{name} no longer begins and ends where it did (moved {math.dist(b0, b1):.2f} ft " \
               f"and {math.dist(e0, e1):.2f} ft)"
    if inst.kind == "radius":
        curves = now.curves()
        if len(curves) != 1 or len(now.tangents()) != 2:
            return f"{name} has {len(curves)} curves and {len(now.tangents())} tangents; it had 1 and 2"
        if abs(curves[0].radius - inst.value) > 0.01:
            return f"curve 1 of {name} has R = {curves[0].radius:.2f}'; the redline asks for " \
                   f"{inst.value:.0f}'"
        p0 = _pi_of(old)
        p1 = _pi_of(now)
        if p1 is None or math.dist(p0, p1) > DESIGN_TOL_FT:
            return f"the PI of curve 1 of {name} moved " + (
                f"{math.dist(p0, p1):.2f} ft" if p1 else "(no tangents)") + "; the redline holds it"
        if abs(now.begin_station - old.begin_station) > 0.006:
            return f"{name} begins at {now.stations().begin_text()}; its stationing was not to change"
        return None
    want = old.begin_station + inst.value
    if abs(now.begin_station - want) > 0.006:
        return f"{name} begins at {now.stations().begin_text()}; the redline makes it " \
               f"{old.stations().format(want)}"
    if len(now.elements) != len(old.elements) or abs(now.length - old.length) > 0.02:
        return f"{name}'s geometry changed (length {old.length:.2f} -> {now.length:.2f} ft); " \
               f"only its stationing was to"
    for k in range(9):
        d = old.length * k / 8.0
        if math.dist(old.point_at(d), now.point_at(d)) > DESIGN_TOL_FT:
            return f"{name}'s geometry changed; only its stationing was to"
    return None


def _samples(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [[e.start[0] + (e.end[0] - e.start[0]) * k / 8, e.start[1] + (e.end[1] - e.start[1]) * k / 8]
                for k in range(9)]
    if isinstance(e, Arc):
        s, t = e.start_angle_deg, e.end_angle_deg
        sweep = (t - s) % 360.0
        return [[e.center[0] + e.radius * math.cos(math.radians(s + sweep * k / 8)),
                 e.center[1] + e.radius * math.sin(math.radians(s + sweep * k / 8))] for k in range(9)]
    if isinstance(e, Polyline):
        out = []
        for a, b in zip(e.vertices, e.vertices[1:]):
            out += [[a[0] + (b[0] - a[0]) * k / 4, a[1] + (b[1] - a[1]) * k / 4] for k in range(5)]
        return out
    return []


def _length(e) -> float:
    if isinstance(e, Line):
        return math.dist(e.start, e.end)
    if isinstance(e, Arc):
        return e.radius * math.radians((e.end_angle_deg - e.start_angle_deg) % 360.0)
    if isinstance(e, Polyline):
        return sum(math.dist(a, b) for a, b in zip(e.vertices, e.vertices[1:]))
    return 0.0


def _off(align: Alignment, p) -> float:
    try:
        return abs(float(align.xy_to_station(p)["offset"]))
    except Exception:  # past the ends
        return float("inf")


def _centerline_ids(inst: Redline, doc: Document) -> List[str]:
    """AA01's drawn centerline of the alignment: its element linework."""
    return [e.id for e in doc.model_entities.values()
            if e.anchor and e.anchor.get("alignment") == inst.alignment
            and e.anchor.get("kind") == "element"]


@lru_cache(maxsize=None)
def _slack(inst_id: str) -> float:
    """How far the start's own drawn centerline sits off its alignment (the
    redraft drew it before the line's last refit: 0.06 ft on "TB1")."""
    inst = _instance(inst_id)
    pristine = _pristine(inst_id, DESIGN_FILE)
    old = _original(inst)
    return max((_off(old, p) for i in _centerline_ids(inst, pristine)
                for p in _samples(pristine.model_entities[i])), default=0.0)


def _centerline_problem(inst: Redline, base: Optional[Document], now: Optional[Alignment]):
    if base is None or now is None:
        return f"{DESIGN_REF} or its \"{inst.alignment}\" is missing"
    pristine = _pristine(inst.id, DESIGN_FILE)
    layer = next(pristine.model_entities[i].layer for i in _centerline_ids(inst, pristine))
    ids = set(_centerline_ids(inst, base))
    ids |= {i for i, e in base.model_entities.items()
            if i not in pristine.model_entities and e.layer == layer}
    covered = 0.0
    tol = CENTERLINE_TOL_FT + _slack(inst.id)
    for i in sorted(ids):
        e = base.model_entities[i]
        worst = max((_off(now, p) for p in _samples(e)), default=0.0)
        if worst > tol:
            return (f"the centerline drawn in {DESIGN_REF} ({i}) strays {worst:.2f} ft off the "
                    f"revised \"{inst.alignment}\"")
        covered += _length(e)
    if abs(covered - now.length) > 1.0:
        return (f"the centerline drawn in {DESIGN_REF} covers {covered:.1f} ft of the revised "
                f"\"{inst.alignment}\" ({now.length:.1f} ft)")
    return None


# ------------------------------------------------------------------ the verifier


LABEL_CHECKS = (("D1-02", "the station ticks"), ("D1-03", "the station numbers"),
                ("D1-04", "the BC, EC and curve bubble"), ("D1-05", "the bearings and lengths"),
                ("D1-06", "the curve table"))


def _verify(submitted: Session, inst: Redline, design: dict):
    from roaddraft.verify import verify
    return verify(submitted.doc, revised_truth(inst, design), prompt_level="vague")


def _finding_text(f) -> str:
    anchor = f.anchor or {}
    where = anchor.get("ref") or ""
    return f"{f.code}{' at ' + where if where else ''}: {f.note or ''}".strip()


def _stale_from_report(report, submitted: Session, fpi: float) -> Optional[str]:
    for c in report.checks:
        if not c.in_scope:
            continue
        for f in c.findings:
            if f.code in ("duplicate", "anchor_inconsistent"):
                return f"stale lettering left: {_finding_text(f)} ({', '.join(f.entity_ids)})"
            if f.code == "misplaced" and c.id == "D1-07" and isinstance(f.expected, dict):
                eid = f.entity_ids[0] if f.entity_ids else ""
                scale = 1.0 / fpi if eid in submitted.doc.model_entities else 1.0
                d = math.dist(f.expected["position"], f.actual["position"]) * scale
                if d > FAR_IN:
                    e = submitted.doc.model_entities.get(eid)
                    what = repr(e.content) if isinstance(e, Text) else eid
                    return (f"stale lettering left: {what} sits {d:.2f} in from where its anchor "
                            f"({(f.anchor or {}).get('ref')}) now puts it")
    return None


def _stale_ticks(baseline: Session, submitted: Session, inst: Redline, now: Alignment,
                 lettering: set) -> Optional[str]:
    """A tick-sized line square across the alignment at a station that is not
    a 100-ft one: stationing left from before the change."""
    sheet = _sheet(submitted, inst.sheet)
    vp = sheet.viewports[0] if sheet is not None and sheet.viewports else None
    before = set(baseline.doc.model_entities)
    for s in baseline.doc.sheets.values():
        before |= set(s.entities)
    context = before - lettering
    candidates = [(e, lambda p: p, 1.0) for e in submitted.doc.model_entities.values()]
    if sheet is not None and vp is not None:
        to_model = vp.transform().to_model
        candidates += [(e, to_model, vp.feet_per_inch) for e in sheet.entities.values()]
    for e, fn, _k in candidates:
        if e.id in context or not isinstance(e, Line):
            continue
        a, b = fn(e.start), fn(e.end)
        length = math.dist(a, b)
        if not (2.0 <= length <= 20.0):
            continue
        m = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
        try:
            r = now.xy_to_station(m)
        except Exception:
            continue
        if abs(float(r["offset"])) > 1.0:
            continue
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        turn = abs(((ang - float(r["direction_deg"])) % 180.0) - 90.0)
        if turn > 10.0:
            continue
        st = float(r["station"])
        if abs(st - round(st / 100.0) * 100.0) > TICK_TOL_FT:
            return (f"a station tick ({e.id}) crosses \"{inst.alignment}\" at "
                    f"{now.stations().format(st)}, which is not a 100-ft station: stationing "
                    f"left from before the change")
    return None


def _old_values(inst: Redline, now: Alignment) -> List[str]:
    """Lettered values of the design before the change that the change makes wrong."""
    old = _original(inst)
    st_old, st_new = old.stations(), now.stations()
    vals = []
    for c_old, c_new in zip(old.curves(), now.curves()):
        for a, b in ((old.begin_station + c_old.start_dist, now.begin_station + c_new.start_dist),
                     (old.begin_station + c_old.start_dist + c_old.length,
                      now.begin_station + c_new.start_dist + c_new.length)):
            if st_old.format(a) != st_new.format(b):
                vals.append(st_old.format(a))
        if inst.kind == "radius":
            for x, y in ((c_old.radius, c_new.radius), (c_old.length, c_new.length),
                         (c_old.radius * math.tan(math.radians(c_old.delta_deg) / 2.0),
                          c_new.radius * math.tan(math.radians(c_new.delta_deg) / 2.0))):
                if f"{x:.2f}" != f"{y:.2f}":
                    vals.append(f"{x:.2f}'")
    if inst.kind == "radius":
        for t_old, t_new in zip(old.tangents(), now.tangents()):
            if f"{t_old.length:.2f}" != f"{t_new.length:.2f}":
                vals.append(f"{t_old.length:.2f}'")
    return vals


# ------------------------------------------------------------------ callouts


CITE_RE = r'"{name}"\s*(\d+\+\d{{2}}(?:\.\d+)?)'


def _cited(inst: Redline, text: str) -> List[Tuple[float, str]]:
    """``(station ft, as written)`` of each station the text cites on the alignment."""
    out = []
    for m in re.finditer(CITE_RE.format(name=re.escape(inst.alignment)), _norm(text)):
        whole, frac = m.group(1).split("+")
        out.append((int(whole) * 100.0 + float(frac), m.group(1)))
    return out


def _callouts(baseline: Session, inst: Redline, lettering: set) -> List[Text]:
    """The start's sheet texts, other than the alignment's own lettering, that
    cite one of its stations."""
    sheet = _sheet(baseline, inst.sheet)
    return [e for e in sheet.entities.values()
            if isinstance(e, Text) and e.id not in lettering and _cited(inst, e.content)]


def _others(text: str, inst: Redline) -> str:
    """The text with the alignment's own citations taken out: what must not
    change (spacing aside)."""
    return re.sub(r"\s+", "", re.sub(CITE_RE.format(name=re.escape(inst.alignment)), "#", _norm(text)))


def _callout_problem(inst: Redline, callout: Text, submitted: Session) -> Optional[str]:
    sheet = _sheet(submitted, inst.sheet)
    want = [(st + inst.value, w) for st, w in _cited(inst, callout.content)]
    texts = [e for e in sheet.entities.values() if isinstance(e, Text)] if sheet else []
    old = {w for _st, w in _cited(inst, callout.content)}
    for e in texts:
        stale = [w for _st, w in _cited(inst, e.content) if w in old]
        if stale:
            return f"the callout still cites \"{inst.alignment}\" {stale[0]}: {_quote(e.content)}"
    for e in texts:
        got = _cited(inst, e.content)
        if len(got) != len(want) or _others(e.content, inst) != _others(callout.content, inst):
            continue
        if all(abs(g - w) <= CALLOUT_TOL_FT for (g, _x), (w, _y) in zip(got, want)):
            return None
    return (f"no callout reads {_quote(callout.content)} with its \"{inst.alignment}\" station "
            f"moved {inst.value:+.2f} ft")


def _quote(text: str, limit: int = 70) -> str:
    one = " / ".join((text or "").split("\n"))
    return repr(one if len(one) <= limit else one[:limit - 3] + "...")


def _leader_ids(baseline: Session, inst: Redline, callouts: List[Text]) -> set:
    """The leaders of the callouts: call-out linework ending near their text."""
    sheet = _sheet(baseline, inst.sheet)
    out = set()
    for c in callouts:
        x0, y0, x1, y1 = c.bbox(baseline.doc)
        for e in sheet.entities.values():
            if not isinstance(e, (Line, Polyline)) or e.layer != c.layer:
                continue
            pts = [e.start, e.end] if isinstance(e, Line) else list(e.vertices)
            if any(x0 - 0.3 <= p[0] <= x1 + 0.3 and y0 - 0.3 <= p[1] <= y1 + 0.3 for p in pts):
                out.add(e.id)
    return out


# ------------------------------------------------------------------ unchanged


def _same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    da, db = a.to_dict(), b.to_dict()
    da.pop("id", None)
    db.pop("id", None)
    return da == db


def _unchanged_problem(baseline: Session, submitted: Session, inst: Redline, skip: set) -> Optional[str]:
    # the sheet file: its paper and model space
    pairs = [("model", baseline.doc.model_entities, submitted.doc.model_entities)]
    for sb in baseline.doc.sheets.values():
        ss = _sheet(submitted, sb.name)
        if ss is None:
            return f"sheet {sb.name} is gone"
        pairs.append((sb.name, sb.entities, ss.entities))
        fb, fs = dict(sb.title_block_fields or {}), dict(ss.title_block_fields or {})
        for k in sorted(set(fb) | set(fs)):
            if REVISION_KEY.search(k) and k in fs and k not in fb:
                continue    # a revision field filled in
            if re.match(r"^(revised_by|date_revised|last_revision)", k):
                continue
            if str(fb.get(k, "")).strip() != str(fs.get(k, "")).strip():
                return f"the title block's {k} was changed ({fb.get(k)!r} -> {fs.get(k)!r})"
    for where, before, after in pairs:
        for i, e in before.items():
            if i in skip:
                continue
            mine = after.get(i)
            if mine is not None and _same(e, mine):
                continue
            if any(_same(e, f) for f in after.values()):
                continue
            what = f"the text {_quote(e.content)}" if isinstance(e, Text) else f"{type(e).__name__} {i}"
            return f"{what} in {where} was changed or removed, and the redline did not touch it"
    # the base files, against the start's own copies (repaired at staging: repairs.py)
    refs = _references(submitted)
    shipped = _references(baseline)
    for name, fname in ((DESIGN_REF, DESIGN_FILE), ("BB01", "0000000000bb01.rdraft")):
        base = refs.get(name)
        if base is None:
            return f"{name} is no longer attached"
        pristine = shipped.get(name) or _pristine(inst.id, fname)
        drawn = set(_centerline_ids(inst, pristine)) if name == DESIGN_REF else set()
        for i, e in pristine.model_entities.items():
            if i in drawn:
                continue
            mine = base.model_entities.get(i)
            if mine is None or not _same(e, mine):
                return f"{type(e).__name__} {i} in {name} was changed or removed"
        if name == DESIGN_REF:
            for aname, a in pristine.design.alignments.items():
                if aname == inst.alignment:
                    continue
                b = base.design.alignments.get(aname)
                if b is None or b.to_dict() != a.to_dict():
                    return f"alignment \"{aname}\" in {name} was changed"
            layer = pristine.model_entities[next(iter(drawn))].layer if drawn else None
            extra = [i for i, e in base.model_entities.items()
                     if i not in pristine.model_entities and e.layer != layer
                     and not (e.anchor and e.anchor.get("alignment") == inst.alignment)]
            if extra:
                return f"{len(extra)} entities were added to {name} ({extra[0]})"
        elif len(base.model_entities) != len(pristine.model_entities):
            return f"entities were added to {name}"
    return None


# ------------------------------------------------------------------ the check


REVISION_KEY = re.compile(r"rev", re.I)
INITIALS_RE = re.compile(r"\bR\.?\s*D\b\.?")


def _dated(text: str) -> bool:
    nums = re.findall(r"\d+", text or "")
    return (("10" in nums or "OCT" in (text or "").upper()) and "19" in nums
            and ("26" in nums or "2026" in nums))


def _revision_problem(baseline: Session, submitted: Session, inst: Redline) -> Optional[str]:
    """RD and 10-19-26 recorded on the sheet. The Caltrans border's REVISED BY /
    DATE REVISED cells are ``revised_by_N`` / ``date_revised_N``, but nothing
    the model is shown names those keys (fill_title_block lists only the
    standard ones), so any title block field whose key says revision, or a new
    revision note on the sheet, is taken as the record."""
    sb, ss = _sheet(baseline, inst.sheet), _sheet(submitted, inst.sheet)
    if ss is None:
        return f"sheet {inst.sheet} is gone"
    fb, fs = dict(sb.title_block_fields or {}), dict(ss.title_block_fields or {})
    changed = [str(v) for k, v in fs.items()
               if REVISION_KEY.search(k) and str(v).strip() != str(fb.get(k, "")).strip()]
    record = " ".join(changed)
    if changed:
        if not INITIALS_RE.search(record.upper()):
            return f"the revision block reads {record!r}; the revision is RD's"
        if not _dated(record):
            return f"the revision block reads {record!r}; the revision is dated 10-19-26"
        return None
    before = set(baseline.doc.model_entities) | set(sb.entities)
    notes = [e.content for e in list(ss.entities.values()) + list(submitted.doc.model_entities.values())
             if isinstance(e, Text) and e.id not in before and e.layer != REDLINE
             and INITIALS_RE.search(e.content.upper()) and _dated(e.content)]
    if notes:
        return None
    return f"no revision recorded on {inst.sheet} (REVISED BY RD, DATE REVISED 10-19-26)"


def _redline_problem(submitted: Session, inst: Redline) -> Optional[str]:
    spaces = [("model", submitted.doc.model_entities)] + [
        (s.name, s.entities) for s in submitted.doc.sheets.values()]
    for where, ents in spaces:
        left = [e for e in ents.values() if e.layer == REDLINE]
        if left:
            return f"{len(left)} entities are still on layer {REDLINE} ({where})"
    note = _norm(inst.note[0])
    for _i, content in _all_texts(submitted):
        if note in _norm(content):
            return f"the redline note is still on the drawing: {_quote(content)}"
    return None


def make_check(inst: Redline):
    def check(baseline: Session, submitted: Session) -> Result:
        tally = Tally()
        sheet_b = _sheet(baseline, inst.sheet)
        fpi = float(sheet_b.viewports[0].feet_per_inch)
        lettering = _lettering_ids(baseline, inst)
        redline = {e.id for e in sheet_b.entities.values() if e.layer == REDLINE}
        name = f'"{inst.alignment}"'

        # 1. the design, where it lives
        now = _submitted_alignment(submitted, inst)
        design_problem = _design_problem(inst, now)
        design_item = (f"curve 1 of {name} revised to R = {inst.value:.0f}' in {DESIGN_REF}, PIs held"
                       if inst.kind == "radius" else
                       f"{name} restationed {inst.value:+.2f} ft in {DESIGN_REF}")
        tally.add(design_item, design_problem)
        design = now.to_dict() if design_problem is None else _intended(inst.id)
        revised = Alignment.from_dict(design)

        # 2. the centerline drawn in the base
        base = _references(submitted).get(DESIGN_REF)
        tally.add(f"the centerline of {name} in {DESIGN_REF} follows the design",
                  _centerline_problem(inst, base, now if design_problem is None else revised))

        # 3-7. the alignment data, against truth from the revised design
        report = _verify(submitted, inst, design)
        by_id = {c.id: c for c in report.checks}
        for cid, what in LABEL_CHECKS:
            c = by_id.get(cid)
            problem = None
            if c is None or not c.in_scope:
                problem = f"{cid} was not graded"
            elif c.credit < 1.0 - 1e-9:
                first = next((f for f in c.findings), None)
                problem = (f"{what} on {inst.sheet} do not match the revised design ({cid} "
                           f"{c.credit:.2f}" + (f"; {_finding_text(first)}" if first else "") + ")")
            tally.add(f"{what} of {name}", problem)

        # 8. nothing stale, nothing twice
        stale = _stale_from_report(report, submitted, fpi)
        if stale is None:
            stale = _stale_ticks(baseline, submitted, inst, revised, lettering)
        if stale is None:
            olds = _old_values(inst, revised)
            for _i, content in _all_texts(submitted):
                hit = next((v for v in olds if v in content), None)
                if hit:
                    stale = f"{_quote(content)} still reads {hit}, a value from before the change"
                    break
        tally.add("no stale lettering left behind", stale)

        # 9. the callouts that cite the alignment's stations
        callouts = _callouts(baseline, inst, lettering) if inst.kind == "station" else []
        for c in callouts:
            tally.add(f"the callout {_quote(c.content, 40)}", _callout_problem(inst, c, submitted))

        # 10-12
        tally.add("the redline markup removed", _redline_problem(submitted, inst))
        tally.add("the revision recorded (RD, 10-19-26)", _revision_problem(baseline, submitted, inst))
        skip = lettering | redline | {c.id for c in callouts} | _leader_ids(baseline, inst, callouts)
        tally.add("nothing unrelated changed", _unchanged_problem(baseline, submitted, inst, skip))
        return tally.result(
            f"the redline picked up: {design_item}, the alignment data on {inst.sheet} re-lettered "
            f"from it with nothing stale left"
            + (", the callouts restationed" if callouts else "")
            + ", the revision recorded and the markup removed")
    return check


# ------------------------------------------------------------------ the solution


def _anchored_ids(session: Session, inst: Redline) -> List[str]:
    q = _qualified(inst)
    ids = []
    spaces = ["model"] + [s.name for s in session.doc.sheets.values()]
    for space in spaces:
        r = common.ok(session.query("find_entities", {"space": space, "anchor": {"alignment": q},
                                                      "include_references": False,
                                                      "limit": 500}))
        ids += [row["id"] for row in r["entities"]]
    return ids


def relettering_commands(inst: Redline, design: dict) -> List[tuple]:
    """The reference phases that letter the alignment, on the revised design."""
    task = _task(inst.id)
    bd = copy.deepcopy(task.brief.to_dict())
    bd["design"]["alignments"][inst.alignment] = copy.deepcopy(design)
    # the curve points' poses carry their text, lettered for the old design
    truth = revised_truth(inst, design)
    now = {lab["anchor"]: lab["content"] for lab in truth.labels}
    for ref, pz in ((bd["deliverable"].get("label_poses") or {}).get("points") or {}).items():
        pz["content"] = now.get(ref, pz.get("content"))
    revised = Task(brief=TaskBrief.from_dict(bd), truth=truth, baseline=task.baseline,
                   files=task.files)
    return phase_commands(revised, ["stationing", "bearings", "callouts", "table"])


def make_solve(inst: Redline, callouts: bool = True, design: bool = True, letter: bool = True,
               revision: bool = True, redline: bool = True, delete_old: bool = True):
    """The scripted solution; the switches leave a step out, for the naive
    wrong answers the tests try."""
    def solve(session: Session) -> None:
        folder = Path(session.doc._path).parent
        base_path = folder / DESIGN_FILE
        # 1. the design, in the base file (an agent: open_document, edit, save)
        base = Session.load(base_path, out_dir=folder)
        if design:
            apply_revision(inst, base)
            common.save(base, base_path)
        common.ok(session.execute("reload_references", {}))
        new = base.doc.design.alignments[inst.alignment].to_dict()
        # 2. the lettering: the old taken off, the alignment data lettered again
        if letter:
            if delete_old:
                common.ok(session.execute("delete_entities", {"ids": _anchored_ids(session, inst)}))
            for name, params in relettering_commands(inst, new):
                common.ok(session.execute(name, params))
        # 3. the callouts that cite the alignment's stations
        if callouts and inst.kind == "station":
            sheet = _sheet(session, inst.sheet)
            pattern = re.compile(r'("' + re.escape(inst.alignment) + r'"\s*)(\d+)\+(\d{2}(?:\.\d+)?)')
            for e in list(sheet.entities.values()):
                if not isinstance(e, Text) or (e.anchor and e.anchor.get("placed_by")):
                    continue

                def shift(m):
                    frac = m.group(3)
                    places = len(frac.split(".")[1]) if "." in frac else 0
                    ft = int(m.group(2)) * 100.0 + float(frac) + inst.value
                    whole, rest = divmod(round(ft, places), 100.0)
                    return f"{m.group(1)}{int(whole)}+{rest:0{3 + places if places else 2}.{places}f}"

                content = pattern.sub(shift, e.content)
                if content != e.content:
                    common.ok(session.execute("modify_entity", {"id": e.id,
                                                                "changes": {"content": content}}))
        # 4. the redline off, the revision recorded
        if redline:
            ids = [row["id"] for row in common.ok(session.query("find_entities", {
                "space": inst.sheet, "layer": REDLINE, "include_references": False}))["entities"]]
            common.ok(session.execute("delete_entities", {"ids": ids}))
        if revision:
            common.ok(session.execute("fill_title_block", {"sheet": inst.sheet, "fields": {
                "revised_by_1": REVISED_BY, "date_revised_1": REVISED_ON}}))
    return solve


# ------------------------------------------------------------------ the probes


PROMPTS = {
    "radius": (
        "Sheet {sheet} came back from checking with a redline, drawn in red on layer REDLINE. "
        "Pick it up. Make the change in the design itself: the \"{name}\" line lives in the "
        "base file {design}, attached to this sheet as {ref}. Then bring everything on {sheet} "
        "that the change affects up to date. The alignment data on the sheet is lettered with "
        "the engine's labelers and anchored to the design through {ref}; keep it lettered that "
        "way. Record the revision in the border's revision block (revised by {by}, "
        "{on}) and take the redline off the sheet. Leave everything else as it is."),
}
PROMPTS["station"] = PROMPTS["radius"]

NOTES = {
    "radius": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"WS\", reading "
        "REVISE CURVE 1 \"WS\" LINE / R = 1500' / HOLD PI. Expected: WS re-made in PI form in "
        "AA01 with R 1500 (holding the PI key_points gives: BC 843+20.92 -> 843+58.48, EC "
        "846+21.28 -> 845+83.87, T 150.46' -> 112.91', L 300.36' -> 225.40', tangents 460.15' -> "
        "497.71' and 236.33' -> 273.88'), the "
        "centerline in AA01 redrawn, the alignment data re-lettered with nothing stale, "
        "REVISED BY RD / 10-19-26, the redline gone."),
    "station": (
        "Planted: a red cloud, leader and note on layer REDLINE round the start of \"TB1\", "
        "reading REVISE \"TB1\" STATIONING: +25.00' / BEGIN \"TB1\" = 639+19.58. Expected: the "
        "begin station changed in AA01, every TB1 tick and number moved 25 ft, BC 642+81.10 -> "
        "643+06.11, EC 644+45.08 -> 644+70.08, the "
        "callouts \"TB1\" 645+66.69 -> 645+91.69 and \"TB1\" 647+73.40 POT -> 647+98.40 POT (its "
        "\"D13\" 647+73.40 unchanged), REVISED BY RD / 10-19-26, the redline gone; the bearings "
        "and curve table stay."),
}


def _probe(inst: Redline) -> Probe:
    prompt = PROMPTS[inst.kind].format(sheet=inst.sheet, name=inst.alignment, design=DESIGN_FILE,
                                       ref=DESIGN_REF, by=REVISED_BY, on=REVISED_ON)
    return Probe(id=inst.id, prompt=prompt, check=make_check(inst), solve=make_solve(inst),
                 note=NOTES[inst.kind], tags=["redline", "edit", "caltrans", "base-file", inst.kind],
                 start=inst.id)


PROBES: List[Probe] = [_probe(i) for i in INSTANCES]

__all__ = ["PROBES", "INSTANCES", "Redline", "apply_revision", "revised_truth", "plant_redline",
           "make_check", "make_solve"]
