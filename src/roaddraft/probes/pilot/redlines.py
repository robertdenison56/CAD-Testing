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

The expansion (2026-11-03, ``MORE``) adds ten instances on ten other sheets, the
three agencies whose sheets carry a letterable line (Caltrans, FDOT, FLH's WFL;
CFL's one line is a stretch clipped on a two-strip sheet, so it was left out):

* the radius down on ``IN4`` (L-4, Δ 75°: the line grows 17.50 ft and its tie to
  IND1 restations), on ``D`` (E-18, the curve ends the line; an angle point to
  keep) and on WFL ``MAIN 01`` (F.7, curve 1 at BEGIN, pushing curve 2), and up on
  ``SB10`` (PD-32). A curve that begins or ends the line gains a tangent, so a BC or
  EC that sat on BEGIN or END and a new tangent's bearing are lettered anew;
* a third kind, ``pi``: the PI of curve 1 moved along its back tangent, R and the
  other PIs held, so the ahead tangent turns and its bearing changes with Δ, T, L,
  the BC, EC and every station after (``ENRA`` on PD-2 ahead, ``R1`` on PD-1 back);
* restations by odd amounts forward and back where the sheet's callouts cite the
  line: FDOT's eight drainage structures (STA. 706+00.00 (45.50 RT), the line not
  named, ``cite``), L-2's ramp ties whose D13 station reads the same number as the
  ramp's, L-7's three-line tie (only F3 moves), U-1's positive location table and a
  general note citing IND1 stations off the sheet.

The rules generalise: the base file and reference per sheet (``design_file``,
``design_ref``); the PIs held one by one, its own PI or its tangents' crossing,
angle points too (``_held_problem``; PD-1's instance keeps its first rule,
``pi_rule``); a cited station on a line whose geometry changed is graded where the
same point of the line falls on the revised one, to the places it is lettered to
(``_moved``); WFL's sheet, lettered as the real stationing task leaves it (no room
for a curve table), is held to D1-02 to D1-05 (``graded``) and records the revision
in a note, its border having no revision block (``revision``). The new instances
let a bare station plus ('+99.5 BEGIN MBGR', whose line the sheet does not name) be
re-lettered without counting it as unrelated (``loose_pluses``), and L-7's start
takes off what the strip left of F3's published BC/EC callouts (``_tidy``).

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

At the vague prompt level (``VAGUE``) the brief names the sheet, the base file and
its reference, says the alignment data stays anchored, and gives the revision's
initials and date, but not where the revision goes; its check (``make_check(inst,
"vague")``) grades the same items and takes a revision note that quotes the
redline's words beside RD and the date as the record on every sheet (item 10
allows it only where the brief asks for a note).

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
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.design.horizontal import (Alignment, CurveElement, TangentElement,
                                         pis_from_elements, signed_delta_deg)
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
from roaddraft.tasks.types import GROUPS

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


#: the E1 checks that grade the alignment data, and the reference phase that letters each
ALL_LABEL_CHECKS = ("D1-02", "D1-03", "D1-04", "D1-05", "D1-06")
CHECK_PHASES = {"D1-02": ("stationing",), "D1-03": ("stationing",),
                "D1-04": ("stationing", "callouts"), "D1-05": ("bearings",), "D1-06": ("table",)}
CHECK_SCOPE = {"D1-02": ("ticks",), "D1-03": ("stations",), "D1-04": ("curve_points", "callouts"),
               "D1-05": ("bearings",), "D1-06": ("table",)}
#: how a Caltrans sheet cites a station of a line: '"TB1" 645+66.69'
CITE_CALTRANS = '"{name}"\\s*'


@dataclass
class Redline:
    id: str
    sheet_id: str               # the redrafted sheet (common.row)
    sheet: str                  # its sheet name
    alignment: str
    kind: str                   # "radius" | "station" | "pi"
    value: float                # the new radius, the shift in feet, or how far the PI moves
                                # along its back tangent (feet, + ahead)
    note: List[str]             # the redline's lettering, line by line
    cloud: Tuple[float, float]  # raw stations the cloud wraps (from, to)
    cloud_offsets: Tuple[float, float] = (-45.0, 45.0)
    text_at: Tuple[float, float] = (0.0, 0.0)   # the note's insertion point, paper inches
    note_text: str = ""
    curve: int = 1              # the curve a radius or PI revision is on, 1 = the first
    design_file: str = ""       # the base file that holds the line ("" = AA01's file) ...
    design_ref: str = ""        # ... and the reference it is attached by
    task_type: str = "real-alignment-data"   # the real task the sheet's lettering comes from
    graded: Tuple[str, ...] = ALL_LABEL_CHECKS  # the E1 checks the lettering is held to
    cite: str = CITE_CALTRANS   # what precedes a station of the line in the sheet's callouts
    revision: str = "block"     # where the revision goes: the border's "block", or a "note"
    agency: str = "caltrans"    # the tag
    pi_rule: str = "either"     # a PI held: its own or its tangents' crossing ("crossing": the
                                # latter only, PD-1's rule for a curve between two tangents)
    loose_pluses: bool = False  # a callout lettered with a bare station plus ('+99.5 BEGIN
                                # MBGR') may have its plus re-lettered: whose line it is is unsure
    named_points: bool = False  # the line's own published BC/EC callouts the strip left, taken off
    traced: bool = False        # the line's lettering traced as strokes in a base, taken off

    def __post_init__(self):
        self.design_file = self.design_file or DESIGN_FILE
        self.design_ref = self.design_ref or DESIGN_REF


RADIUS = Redline(
    id="p11-radius-ppm160", sheet_id="PPM-160", sheet="PD-1", alignment="WS", kind="radius",
    value=1500.0, note=['REVISE CURVE 1 "WS" LINE', "R = 1500'", "HOLD PI"],
    cloud=(84290.0, 84650.0), cloud_offsets=(-40.0, 40.0), text_at=(18.7, 5.25),
    pi_rule="crossing")

STATION = Redline(
    id="p11-station-ppm045", sheet_id="PPM-045", sheet="L-1", alignment="TB1", kind="station",
    value=25.0, note=['REVISE "TB1" STATIONING: +25.00\'', 'BEGIN "TB1" = 639+19.58'],
    cloud=(63894.6, 64200.0), cloud_offsets=(-25.0, 25.0), text_at=(5.4, 5.6))

#: the expansion (2026-11-03): more sheets, lines and agencies, the radius taken up and down,
#: odd shifts forward and back, and a third kind, a PI moved along its back tangent. A bare
#: station plus ('+46 BEGIN MBGR') may be re-lettered on these sheets (``loose_pluses``).
NEW = dict(loose_pluses=True)
FDOT_916 = dict(sheet_id="FDOT-916-1-Drainage-Network-Plan-Sheet", sheet="1",
                design_file="ALGNRD01.rdraft", design_ref="ALI", agency="fdot", **NEW)
WFL_07 = dict(sheet_id="WFL-Parking-Lot-Section-p07", sheet="F.7",
              design_file="WA-NP-FOVA-101_ali.rdraft", design_ref="ALI", agency="wfl",
              task_type="real-stationing", graded=("D1-02", "D1-03", "D1-04", "D1-05"),
              revision="note", **NEW)
MORE = [
    Redline(id="p11-radius-ppm048", sheet_id="PPM-048", sheet="L-4", alignment="IN4", kind="radius",
            value=250.0, note=['REVISE CURVE 1 "IN4" LINE', "R = 250'", "HOLD PI"],
            cloud=(67760.0, 68160.0), cloud_offsets=(-25.0, 25.0), text_at=(24.1, 5.5), **NEW),
    Redline(id="p11-radius-ppm230", sheet_id="PPM-230", sheet="E-18", alignment="D", kind="radius",
            value=350.0, note=['REVISE CURVE 1 "D" LINE', "R = 350'", "HOLD PI"],
            cloud=(3342.55, 3797.52), cloud_offsets=(-40.0, 40.0), text_at=(18.45, 13.9), **NEW),
    Redline(id="p11-radius-wfl07", alignment="MAIN 01", kind="radius", value=600.0,
            note=['REVISE CURVE 1 "MAIN 01" LINE', "R = 600'", "HOLD PI"],
            cloud=(3638.9, 3798.5), cloud_offsets=(-30.0, 30.0), text_at=(11.6, 5.8), **WFL_07),
    Redline(id="p11-radius-ppm158", sheet_id="PPM-158", sheet="PD-32", alignment="SB10",
            kind="radius", value=4000.0, note=['REVISE CURVE 1 "SB10" LINE', "R = 4000'", "HOLD PI"],
            cloud=(103280.0, 103480.0), cloud_offsets=(-40.0, 40.0), text_at=(21.8, 13.35), **NEW),
    Redline(id="p11-pi-ppm161", sheet_id="PPM-161", sheet="PD-2", alignment="ENRA", kind="pi",
            value=30.0, note=['REVISE CURVE 1 "ENRA" LINE', "MOVE PI 30.00' AHEAD ALONG",
                              "BACK TANGENT, HOLD R AND END"],
            cloud=(85030.0, 85540.0), cloud_offsets=(-40.0, 40.0), text_at=(3.25, 14.95), **NEW),
    Redline(id="p11-pi-ppm154", sheet_id="PPM-154", sheet="PD-1", alignment="R1", kind="pi",
            value=-30.0, note=['REVISE CURVE 1 "R1" LINE', "MOVE PI 30.00' BACK ALONG",
                               "BACK TANGENT, HOLD R AND END"],
            cloud=(61840.0, 62252.0), cloud_offsets=(-40.0, 40.0), text_at=(24.1, 3.65), **NEW),
    Redline(id="p11-station-fdot916", alignment="CL1", kind="station", value=-41.0,
            note=['REVISE "CL1" STATIONING: -41.00\'', 'BEGIN "CL1" = 701+88.98'],
            cloud=(70229.98, 70400.0), cloud_offsets=(-25.0, 25.0), text_at=(2.4, 3.6),
            cite=r"STA\.\s*", **FDOT_916),
    Redline(id="p11-station-ppm046", sheet_id="PPM-046", sheet="L-2", alignment="D13",
            kind="station", value=38.0,
            note=['REVISE "D13" STATIONING: +38.00\'', 'BEGIN "D13" = 651+62.30'],
            cloud=(65124.3, 65400.0), cloud_offsets=(-25.0, 25.0), text_at=(7.65, 14.55), **NEW),
    Redline(id="p11-station-ppm050", sheet_id="PPM-050", sheet="L-7", alignment="F3",
            kind="station", value=-53.0,
            note=['REVISE "F3" STATIONING: -53.00\'', 'BEGIN "F3" = 701+22.52'],
            cloud=(70175.52, 70450.0), cloud_offsets=(-25.0, 25.0), text_at=(6.95, 14.75),
            named_points=True, traced=True, **NEW),
    Redline(id="p11-station-ppm111", sheet_id="PPM-111", sheet="U-1", alignment="IND1",
            kind="station", value=62.0,
            note=['REVISE "IND1" STATIONING: +62.00\'', 'BEGIN "IND1" = 27+41.06'],
            cloud=(2679.06, 2950.0), cloud_offsets=(-25.0, 25.0), text_at=(5.55, 7.65), **NEW),
]

INSTANCES = [RADIUS, STATION] + MORE


# ------------------------------------------------------------------ the task


@lru_cache(maxsize=None)
def _task(inst_id: str) -> Task:
    inst = _instance(inst_id)
    return build_real_task(inst.sheet_id, inst.alignment, inst.task_type)


def _instance(inst_id: str) -> Redline:
    return next(i for i in INSTANCES if i.id == inst_id)


def _qualified(inst: Redline) -> str:
    return f"{inst.design_ref}:{inst.alignment}"


@lru_cache(maxsize=None)
def _pristine(inst_id: str, name: str) -> Document:
    """A base file as the start ships it."""
    return Document.from_dict(copy.deepcopy(_task(inst_id).files[name]))


def _original(inst: Redline) -> Alignment:
    return Alignment.from_dict(_task(inst.id).brief.design["alignments"][inst.alignment])


def _key(points: List[dict], design: str) -> List[float]:
    return list(next(p["point"] for p in points if p.get("design") == design))


def _pi_rows(align: Alignment) -> List[List[float]]:
    """The line's PIs as ``modify_alignment`` takes them: BEGIN, each curve's PI
    with its radius and each angle point (no radius), END. A line laid out from
    elements gives its curves' own PIs (``pis_from_elements``)."""
    pis = align.pis if align.source == "pis" and align.pis else pis_from_elements(align.elements)
    return [list(p.point) + ([float(p.radius)] if p.radius else []) for p in pis]


def _curve_row(rows: List[List[float]], n: int) -> int:
    """The index in ``rows`` of curve ``n``'s PI (1-based, angle points skipped)."""
    k = [i for i, r in enumerate(rows[1:-1], start=1) if len(r) > 2]
    return k[n - 1]


def _moved_pi(back: List[float], pi: List[float], by: float) -> List[float]:
    """``pi`` moved ``by`` feet along its back tangent (from ``back``), + ahead."""
    d = math.dist(back[:2], pi[:2])
    return [pi[0] + (pi[0] - back[0]) / d * by, pi[1] + (pi[1] - back[1]) / d * by]


def apply_revision(inst: Redline, base: Session) -> None:
    """The redline's change, made on a session over the base file, the way an
    agent makes it: the PIs from key_points and the design data, the alignment
    re-made in PI form with the new radius or the PI moved (the drawn centerline
    redrawn), or the begin station."""
    name = inst.alignment
    if inst.kind in ("radius", "pi"):
        pts = common.ok(base.query("key_points", {"alignment": name}))["points"]
        align = base.doc.design.alignments[name]
        rows = _pi_rows(align)
        if inst.kind == "radius" and len(align.curves()) == 1 and len(rows) == 3:
            # one curve between the ends: the PI key_points gives
            pis = [_key(pts, "begin"), _key(pts, "pi") + [inst.value], _key(pts, "end")]
        else:
            rows[0], rows[-1] = _key(pts, "begin"), _key(pts, "end")
            k = _curve_row(rows, inst.curve)
            if inst.kind == "radius":
                rows[k] = rows[k][:2] + [inst.value]
            else:
                rows[k] = _moved_pi(rows[k - 1], rows[k], inst.value) + rows[k][2:]
            pis = rows
        params = {"name": name, "changes": {"pis": pis}, "redraw": True}
        if any(len(r) < 3 for r in pis[1:-1]):
            params["angle_points"] = True   # the line's angle points kept as they are
        common.ok(base.execute("modify_alignment", params))
    else:
        align = base.doc.design.alignments[name]
        new = align.stations().format(align.begin_station + inst.value)
        common.ok(base.execute("modify_alignment", {"name": name,
                                                    "changes": {"begin_station": new}}))


@lru_cache(maxsize=None)
def _intended(inst_id: str) -> dict:
    """The revised alignment as the engine makes it from the start's base."""
    inst = _instance(inst_id)
    s = Session(_document=Document.from_dict(copy.deepcopy(_task(inst_id).files[inst.design_file])))
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
    if inst.task_type != "real-alignment-data":
        # a sheet lettered from another real task (no room for a curve table): every
        # group the start carries is graded, not only the task's own
        want = {g for c in inst.graded for g in CHECK_SCOPE[c]}
        truth.scope = [g for g in GROUPS if g in want]
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
        _tidy(out, inst)
        return path
    return build


#: a curve point called out with its line's name: '"F3" 706+27.65 EC'
NAMED_POINT = re.compile(r'"\s*([A-Z0-9]+)\s*"\s*(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)\s*'
                         r"(?:BCC|ECC|PCC|PRC|BC|EC)\b")


def _tidy(out: Path, inst: Redline) -> None:
    """What the real task's strip leaves of the line's own published lettering
    (the layout pilots take the same off, ``layout._strip_reversed`` and
    ``_strip_traced``): a BC/EC callout that names the line on a leader longer
    than the strip looks (L-7's '"F3" 706+27.65 EC', the anchored EC beside it),
    and lettering traced as strokes in a base (L-7's '"F3" 705+03.23 BC')."""
    if not (inst.named_points or inst.traced):
        return
    from roaddraft.tasks import real
    path = out / common.sheet_file(inst.sheet_id)
    s = common.load(path)
    sheet = _sheet(s, inst.sheet)
    if inst.named_points:
        points = [float(lab["station"]) for lab in _task(inst.id).truth.labels
                  if lab["kind"] in ("pc", "pt", "pcc", "prc")]
        gone, quads = [], []
        for e in sheet.entities.values():
            if isinstance(e, Text) and any(
                    m.group(1) == inst.alignment and any(
                        abs(int(m.group(2)) * 100.0 + float(m.group(3)) - p) <= real.STATION_TOL_FT
                        for p in points) for m in NAMED_POINT.finditer(_norm(e.content))):
                quads.append(real._quad(e, s.doc))
                gone.append(e.id)
        rest = {i: e for i, e in sheet.entities.items() if i not in gone}
        gone += real._leaders(rest, quads, 1.0)
        if gone:
            common.ok(s.execute("delete_entities", {"ids": gone}))
            common.save(s, path)
    if inst.traced:
        from roaddraft.probes.pilot.layout import STALE_TRACED
        boxes = STALE_TRACED[inst.sheet_id][inst.alignment]
        to_paper = sheet.viewports[0].transform().to_paper
        for name in sorted(_task(inst.id).files):
            base = common.load(out / name)
            gone = []
            for e in base.doc.model_entities.values():
                pts = ([list(e.start), list(e.end)] if isinstance(e, Line)
                       else [list(v) for v in e.vertices] if isinstance(e, Polyline) else [])
                paper = [to_paper(q) for q in pts]
                if paper and any(e.layer in layers and all(
                        b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for q in paper)
                        for b, layers in boxes):
                    gone.append(e.id)
            if gone:
                common.ok(base.execute("delete_entities", {"ids": gone}))
                common.save(base, out / name)


#: L-1's other curve: the real task's strip keeps TB2's row of the CURVE DATA table that
#: held both lines' curves (reading No. 1, as published) while the reference letters TB1's
#: bubble and table as 1, and TB2's ring lost its number in the redraft: TB2's curve is 2
TB2_RING = "PL-004"       # TB2's bubble ring on the sheet (its number the redraft lost)
TB2_NUMBER = "2"          # TB1's anchored bubble is 1, so TB2's curve is 2
NO_COLUMN_IN = 0.6        # a No. cell sits within this of the header, in x
NO_ROWS_IN = 1.0          # and within this below it


def _restore_tb2(out: Path) -> None:
    """Number TB2's curve 2: the digit in its ring and the No. cell of its kept row.
    (Until 2026-10-31 the strip took the whole shared table and this placed TB2's
    table back and deleted TB1's ring; the strip now keeps the row and takes the ring.)"""
    s = common.load(out / common.sheet_file(STATION.sheet_id))
    sheet = next(iter(s.doc.sheets.values()))
    ring = sheet.entities[TB2_RING]
    centre = [sum(p[0] for p in ring.vertices) / len(ring.vertices),
              sum(p[1] for p in ring.vertices) / len(ring.vertices)]
    common.ok(s.execute("place_text", {"space": sheet.name, "layer": ring.layer, "position": centre,
                                       "height": 0.12, "halign": "center", "valign": "middle",
                                       "content": TB2_NUMBER}))
    header = [e for e in sheet.entities.values() if isinstance(e, Text) and _norm(e.content) == "NO."]
    cells = [e for e in sheet.entities.values() if isinstance(e, Text) and e.content.strip() == "1"
             and any(abs(e.position[0] - h.position[0]) <= NO_COLUMN_IN
                     and 0 < h.position[1] - e.position[1] <= NO_ROWS_IN for h in header)]
    if len(header) != 1 or len(cells) != 1:
        raise RuntimeError(f"L-1's kept CURVE DATA row: {len(header)} No. header(s), "
                           f"{len(cells)} No. 1 cell(s) under it; expected one of each")
    common.ok(s.execute("modify_entity", {"id": cells[0].id, "changes": {"content": TB2_NUMBER}}))
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
    base = _references(submitted).get(inst.design_ref)
    if base is None:
        return None
    return base.design.alignments.get(inst.alignment)


def _pi_of(align: Alignment) -> Optional[List[float]]:
    """Where the first and last tangents' lines cross."""
    ts = align.tangents()
    if len(ts) < 2:
        return None
    return _crossing(ts[0], ts[-1])


KINK_DEG = 1e-4   # two tangents turning more than this meet at an angle point


def _crossing(a, b) -> Optional[List[float]]:
    """Where the lines of tangents ``a`` and ``b`` cross."""
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


def _pi_points(align: Alignment) -> List[Tuple[float, List[List[float]], Optional[float]]]:
    """``(radius, where, back)`` for each PI between the ends, in order: a curve
    with its own PI and, between two tangents, where their lines cross (the
    rebuilt lines' tangents meet their curves with kinks of seconds, so either
    may be held); an angle point (radius 0) with its corner. ``back`` is the
    direction of the tangent behind it, when there is one."""
    els = align.elements
    out = []
    for i, el in enumerate(els):
        prev = els[i - 1] if i > 0 else None
        back = float(prev.direction_deg) if isinstance(prev, TangentElement) else None
        if isinstance(el, CurveElement):
            where = [list(el.pi)]
            ahead = els[i + 1] if i + 1 < len(els) else None
            if isinstance(prev, TangentElement) and isinstance(ahead, TangentElement):
                x = _crossing(prev, ahead)
                if x is not None:
                    where.append(x)
            out.append((float(el.radius), where, back))
        elif isinstance(prev, TangentElement) and abs(signed_delta_deg(
                prev.direction_deg, el.direction_deg)) > KINK_DEG:
            out.append((0.0, [list(el.start)], back))
    return out


def _count(points) -> str:
    nc = sum(1 for r, _w, _b in points if r)
    na = len(points) - nc
    return f"{nc} curve{'' if nc == 1 else 's'}" + (
        f" and {na} angle point{'' if na == 1 else 's'}" if na else "")


def _held_problem(inst: Redline, old: Alignment, now: Alignment, name: str) -> Optional[str]:
    """Every PI held but the one the redline names: its radius changed, or it moved
    along its back tangent; every other radius and angle point as it was."""
    o, n = _pi_points(old), _pi_points(now)
    if len(n) != len(o):
        return f"{name} has {_count(n)}; it had {_count(o)}"
    seen = 0
    for i, ((r0, where, back), (r1, got, _b)) in enumerate(zip(o, n)):
        seen += 1 if r0 else 0
        what = f"curve {seen}" if r0 else "an angle point"
        if bool(r0) != bool(r1):
            return f"{name} has {_count(n)} in another order; it had {_count(o)}"
        mine = bool(r0) and seen == inst.curve
        if r0:
            want = inst.value if mine and inst.kind == "radius" else r0
            if abs(r1 - want) > 0.01:
                return (f"curve {seen} of {name} has R = {r1:.2f}'; " + (
                    f"the redline asks for {inst.value:.0f}'" if mine and inst.kind == "radius"
                    else f"it had R = {r0:.2f}' and the redline holds it"))
        if mine and inst.kind == "pi":
            if back is None:   # no tangent behind it: the line from the PI before
                prev = o[i - 1][1][0] if i else list(old.point_at(0.0))
                u = math.atan2(where[0][1] - prev[1], where[0][0] - prev[0])
            else:
                u = math.radians(back)
            where = [[p[0] + math.cos(u) * inst.value, p[1] + math.sin(u) * inst.value]
                     for p in where]
        miss = min(math.dist(got[0], p) for p in where)
        if miss > DESIGN_TOL_FT:
            if mine and inst.kind == "pi":
                return (f"the PI of curve {seen} of {name} is {miss:.2f} ft from where the redline "
                        f"moves it ({inst.value:+.2f} ft along its back tangent)")
            return f"the PI of {what} of {name} moved {miss:.2f} ft; the redline holds it"
    if abs(now.begin_station - old.begin_station) > 0.006:
        return f"{name} begins at {now.stations().begin_text()}; its stationing was not to change"
    return None


def _design_problem(inst: Redline, now: Optional[Alignment]) -> Optional[str]:
    old = _original(inst)
    name = f'"{inst.alignment}"'
    if now is None:
        return f"{inst.design_ref} no longer carries {name}"
    b0, e0 = _ends(old)
    b1, e1 = _ends(now)
    if math.dist(b0, b1) > DESIGN_TOL_FT or math.dist(e0, e1) > DESIGN_TOL_FT:
        return f"{name} no longer begins and ends where it did (moved {math.dist(b0, b1):.2f} ft " \
               f"and {math.dist(e0, e1):.2f} ft)"
    if inst.kind == "pi" or (inst.kind == "radius" and inst.pi_rule != "crossing"):
        return _held_problem(inst, old, now, name)
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
    pristine = _pristine(inst_id, inst.design_file)
    old = _original(inst)
    return max((_off(old, p) for i in _centerline_ids(inst, pristine)
                for p in _samples(pristine.model_entities[i])), default=0.0)


def _centerline_problem(inst: Redline, base: Optional[Document], now: Optional[Alignment]):
    if base is None or now is None:
        return f"{inst.design_ref} or its \"{inst.alignment}\" is missing"
    pristine = _pristine(inst.id, inst.design_file)
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
            return (f"the centerline drawn in {inst.design_ref} ({i}) strays {worst:.2f} ft off the "
                    f"revised \"{inst.alignment}\"")
        covered += _length(e)
    if abs(covered - (now.length - _undrawn(inst.id))) > 1.0:
        return (f"the centerline drawn in {inst.design_ref} covers {covered:.1f} ft of the revised "
                f"\"{inst.alignment}\" ({now.length:.1f} ft)")
    return None


@lru_cache(maxsize=None)
def _undrawn(inst_id: str) -> float:
    """How much of the line the start's own centerline leaves undrawn, when that is
    more than a foot (L-7's F3: its 103.79-ft second tangent is not among the
    elements drawn for it in AA01)."""
    inst = _instance(inst_id)
    pristine = _pristine(inst_id, inst.design_file)
    gap = _original(inst).length - sum(_length(pristine.model_entities[i])
                                       for i in _centerline_ids(inst, pristine))
    return gap if gap > 1.0 else 0.0


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
        if inst.kind != "station":   # radius, pi
            for x, y in ((c_old.radius, c_new.radius), (c_old.length, c_new.length),
                         (c_old.radius * math.tan(math.radians(c_old.delta_deg) / 2.0),
                          c_new.radius * math.tan(math.radians(c_new.delta_deg) / 2.0))):
                if f"{x:.2f}" != f"{y:.2f}":
                    vals.append(f"{x:.2f}'")
    if inst.kind != "station":   # radius, pi
        for t_old, t_new in zip(old.tangents(), now.tangents()):
            if f"{t_old.length:.2f}" != f"{t_new.length:.2f}":
                vals.append(f"{t_old.length:.2f}'")
    return vals


# ------------------------------------------------------------------ callouts


CITE_RE = r'"{name}"\s*(\d+\+\d{{2}}(?:\.\d+)?)'
STATION_RE = r"(\d+\+\d{2}(?:\.\d+)?)"


def _cite_re(inst: Redline) -> str:
    """How the sheet cites a station of the line, the station captured."""
    return inst.cite.format(name=re.escape(inst.alignment)) + STATION_RE


def _cited(inst: Redline, text: str) -> List[Tuple[float, str]]:
    """``(station ft, as written)`` of each station the text cites on the alignment."""
    out = []
    for m in re.finditer(_cite_re(inst), _norm(text)):
        whole, frac = m.group(1).split("+")
        out.append((int(whole) * 100.0 + float(frac), m.group(1)))
    return out


def _moved(inst: Redline, st: float, revised: Optional[Alignment]) -> float:
    """Where a cited station of the line goes: the shift; or, when the geometry
    changed, the station the same point of the line has on the revised one (a
    station off the line, or on a stretch the change does not reach, stays)."""
    if inst.kind == "station":
        return st + inst.value
    old = _original(inst)
    if revised is None or not (old.begin_station - CALLOUT_TOL_FT <= st
                               <= old.end_station + CALLOUT_TOL_FT):
        return st
    raw = min(max(st, old.begin_station), old.end_station)
    try:
        got = float(revised.xy_to_station(old.station_to_xy(raw, 0.0)[0])["station"])
    except Exception:  # past the revised line's ends
        return st
    return got + (st - raw)


def _as_cited(written: str, ft: float) -> str:
    """``ft`` as a station lettered to the places of ``written``."""
    frac = written.split("+")[1]
    places = len(frac.split(".")[1]) if "." in frac else 0
    whole, rest = divmod(round(ft, places), 100.0)
    return f"{int(whole)}+{rest:0{3 + places if places else 2}.{places}f}"


def _changes(inst: Redline, st: float, written: str, revised: Optional[Alignment]) -> bool:
    """Whether the cited station reads otherwise after the change, to its places."""
    return _as_cited(written, _moved(inst, st, revised)) != _as_cited(written, st)


def _callouts(baseline: Session, inst: Redline, lettering: set) -> List[Text]:
    """The start's sheet texts, other than the alignment's own lettering and the
    redline, that cite one of its stations (when the geometry changes, one the
    change moves)."""
    sheet = _sheet(baseline, inst.sheet)
    out = [e for e in sheet.entities.values()
           if isinstance(e, Text) and e.id not in lettering and _cited(inst, e.content)
           and e.layer != REDLINE]
    if out and inst.kind != "station":
        revised = Alignment.from_dict(_intended(inst.id))
        out = [e for e in out if any(_changes(inst, st, w, revised)
                                     for st, w in _cited(inst, e.content))]
    return out


def _others(text: str, inst: Redline) -> str:
    """The text with the alignment's own citations taken out: what must not
    change (spacing aside)."""
    return re.sub(r"\s+", "", re.sub(_cite_re(inst), "#", _norm(text)))


def _callout_problem(inst: Redline, callout: Text, submitted: Session,
                     revised: Optional[Alignment] = None) -> Optional[str]:
    sheet = _sheet(submitted, inst.sheet)
    want = [(_moved(inst, st, revised), w) for st, w in _cited(inst, callout.content)]
    texts = [e for e in sheet.entities.values() if isinstance(e, Text)] if sheet else []
    old = {w for st, w in _cited(inst, callout.content)
           if inst.kind == "station" or _changes(inst, st, w, revised)}
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
    if inst.kind == "station":
        return (f"no callout reads {_quote(callout.content)} with its \"{inst.alignment}\" station "
                f"moved {inst.value:+.2f} ft")
    return (f"no callout reads {_quote(callout.content)} with its \"{inst.alignment}\" station "
            f"where the revised line puts it")


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


#: a callout lettered with a bare station plus, its line not named: '+99.5 BEGIN MBGR'
PLUS_HEAD = re.compile(r"^\s*\+\s*\d{2}(?:\.\d+)?")


def _plus_relettered(e, f) -> bool:
    """``f`` is ``e`` with only its leading station plus lettered anew."""
    if not (isinstance(e, Text) and isinstance(f, Text) and PLUS_HEAD.match(e.content or "")
            and PLUS_HEAD.match(f.content or "")):
        return False
    da, db = e.to_dict(), f.to_dict()
    for d in (da, db):
        d.pop("id", None)
        d.pop("content", None)
    return da == db and PLUS_HEAD.sub("#", e.content) == PLUS_HEAD.sub("#", f.content)


def _base_files(inst: Redline) -> List[Tuple[str, str]]:
    """``(reference name, file name)`` of the sheet's base files, the design's first
    (AA01 and BB01 on a Caltrans sheet)."""
    task = _task(inst.id)
    sheet = Document.from_dict(task.baseline)
    refs = sorted((r.name, Path(r.path).name) for r in sheet.references.values())
    return sorted(refs, key=lambda r: r[0] != inst.design_ref)


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
            if inst.loose_pluses and any(_plus_relettered(e, f) for f in after.values()):
                continue
            what = f"the text {_quote(e.content)}" if isinstance(e, Text) else f"{type(e).__name__} {i}"
            return f"{what} in {where} was changed or removed, and the redline did not touch it"
    # the base files, against the start's own copies (repaired at staging: repairs.py)
    refs = _references(submitted)
    shipped = _references(baseline)
    for name, fname in _base_files(inst):
        base = refs.get(name)
        if base is None:
            return f"{name} is no longer attached"
        pristine = shipped.get(name) or _pristine(inst.id, fname)
        drawn = set(_centerline_ids(inst, pristine)) if name == inst.design_ref else set()
        for i, e in pristine.model_entities.items():
            if i in drawn:
                continue
            mine = base.model_entities.get(i)
            if mine is None or not _same(e, mine):
                return f"{type(e).__name__} {i} in {name} was changed or removed"
        if name == inst.design_ref:
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


def _redline_problem(submitted: Session, inst: Redline, revision_note: bool = False) -> Optional[str]:
    """The markup off the drawing. ``revision_note``: a revision note that quotes
    the redline's words beside RD and the date is a record of the revision, not the
    redline left, on any sheet (the vague level, whose brief does not say where the
    revision goes); otherwise only where the brief asks for a note (``inst.revision``)."""
    spaces = [("model", submitted.doc.model_entities)] + [
        (s.name, s.entities) for s in submitted.doc.sheets.values()]
    for where, ents in spaces:
        left = [e for e in ents.values() if e.layer == REDLINE]
        if left:
            return f"{len(left)} entities are still on layer {REDLINE} ({where})"
    note = _norm(inst.note[0])
    for _i, content in _all_texts(submitted):
        if note in _norm(content):
            if (inst.revision == "note" or revision_note) and INITIALS_RE.search(_norm(content)) \
                    and _dated(content):
                continue   # the revision note asked for may say what was revised
            return f"the redline note is still on the drawing: {_quote(content)}"
    return None


def _design_item(inst: Redline) -> str:
    name = f'"{inst.alignment}"'
    if inst.kind == "radius":
        return f"curve {inst.curve} of {name} revised to R = {inst.value:.0f}' in {inst.design_ref}, PIs held"
    if inst.kind == "pi":
        return (f"the PI of curve {inst.curve} of {name} moved {inst.value:+.2f} ft along its back "
                f"tangent in {inst.design_ref}, R and the other PIs held")
    return f"{name} restationed {inst.value:+.2f} ft in {inst.design_ref}"


def make_check(inst: Redline, level: str = "explicit"):
    """The check at prompt ``level``. The vague brief asks for the revision to be
    recorded without saying where, so at ``vague`` a revision note that quotes the
    redline's words (with RD and the date) is the record on every sheet, as it is on
    the sheets whose brief asks for a note; everything else is graded the same."""
    vague = level == "vague"

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
        design_item = _design_item(inst)
        tally.add(design_item, design_problem)
        design = now.to_dict() if design_problem is None else _intended(inst.id)
        revised = Alignment.from_dict(design)

        # 2. the centerline drawn in the base
        base = _references(submitted).get(inst.design_ref)
        tally.add(f"the centerline of {name} in {inst.design_ref} follows the design",
                  _centerline_problem(inst, base, now if design_problem is None else revised))

        # 3-7. the alignment data, against truth from the revised design
        report = _verify(submitted, inst, design)
        by_id = {c.id: c for c in report.checks}
        for cid, what in LABEL_CHECKS:
            if cid not in inst.graded:
                continue
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
        callouts = _callouts(baseline, inst, lettering)
        for c in callouts:
            tally.add(f"the callout {_quote(c.content, 40)}",
                      _callout_problem(inst, c, submitted, revised))

        # 10-12
        tally.add("the redline markup removed", _redline_problem(submitted, inst, revision_note=vague))
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


def relettering_commands(inst: Redline, design: dict,
                         phases: Optional[Sequence[str]] = None) -> List[tuple]:
    """The reference phases that letter the alignment, on the revised design
    (``phases``: only those)."""
    task = _task(inst.id)
    bd = copy.deepcopy(task.brief.to_dict())
    bd["design"]["alignments"][inst.alignment] = copy.deepcopy(design)
    # the curve points' poses carry their text, lettered for the old design
    truth = revised_truth(inst, design)
    now = {lab["anchor"]: lab["content"] for lab in truth.labels}
    points = (bd["deliverable"].get("label_poses") or {}).get("points")
    for ref, pz in (points or {}).items():
        pz["content"] = now.get(ref, pz.get("content"))
    if points:   # each curve point lettered on its own: one the change brings in too (a BC
        # that sat on BEGIN, an EC that sat on END), where the labeler puts it
        D = bd["deliverable"]
        offset = float(D.get("point_label_offset_ft", D["label_offset_ft"]))
        for lab in truth.labels:
            if lab["kind"] not in ("station", "bearing", "mc") and lab["anchor"] not in points:
                points[lab["anchor"]] = {"kind": lab["kind"], "content": lab["content"],
                                         "side": lab["side"], "label_offset_ft": offset}
    revised = Task(brief=TaskBrief.from_dict(bd), truth=truth, baseline=task.baseline,
                   files=task.files)
    if phases is None:
        phases = sorted({p for c in inst.graded for p in CHECK_PHASES[c]})
    return phase_commands(revised, phases)


#: what each lettering phase leaves anchored (the rest is the stationing's)
PHASE_KINDS = {"bearings": ("bearing",), "callouts": ("mc", "mc_bubble", "mc_leader"),
               "table": ("curve_table",)}


def _phase_of(entity) -> str:
    kind = (entity.anchor or {}).get("kind")
    return next((p for p, kinds in PHASE_KINDS.items() if kind in kinds), "stationing")


def make_solve(inst: Redline, callouts: bool = True, design: bool = True, letter: bool = True,
               revision: bool = True, redline: bool = True, delete_old: bool = True,
               phases: Optional[Sequence[str]] = None):
    """The scripted solution; the switches leave a step out, for the naive
    wrong answers the tests try (``phases``: only those lettering phases redone)."""
    def solve(session: Session) -> None:
        folder = Path(session.doc._path).parent
        base_path = folder / inst.design_file
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
                ids = _anchored_ids(session, inst)
                if phases is not None:
                    spaces = [session.doc.model_entities] + [
                        sh.entities for sh in session.doc.sheets.values()]
                    ids = [i for i in ids for ents in spaces
                           if i in ents and _phase_of(ents[i]) in phases]
                common.ok(session.execute("delete_entities", {"ids": ids}))
            for name, params in relettering_commands(inst, new, phases):
                common.ok(session.execute(name, params))
        # 3. the callouts that cite the alignment's stations
        if callouts:
            sheet = _sheet(session, inst.sheet)
            pattern = re.compile("(" + inst.cite.format(name=re.escape(inst.alignment))
                                 + r")(\d+)\+(\d{2}(?:\.\d+)?)")
            moved = None if inst.kind == "station" else Alignment.from_dict(new)
            for e in list(sheet.entities.values()):
                if not isinstance(e, Text) or (e.anchor and e.anchor.get("placed_by")) \
                        or e.layer == REDLINE:
                    continue

                def shift(m):
                    frac = m.group(3)
                    places = len(frac.split(".")[1]) if "." in frac else 0
                    was = int(m.group(2)) * 100.0 + float(frac)
                    ft = was + inst.value if moved is None else _moved(inst, was, moved)
                    if moved is not None and not _changes(inst, was, f"{m.group(2)}+{frac}", moved):
                        return m.group(0)
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
            _record_revision(inst, session)
    return solve


#: what each border's revision block is filled with (the Caltrans REVISED BY / DATE
#: REVISED cells; FDOT's REVISIONS rows, a date and a description)
def _record_revision(inst: Redline, session: Session) -> None:
    sheet = _sheet(session, inst.sheet)
    template = (sheet.title_block_template or "").lower()
    if inst.revision == "note":   # a border with no revision block: a note on the sheet
        common.ok(session.execute("place_text", {
            "space": inst.sheet, "position": list(inst.text_at), "height": 0.1,
            "halign": "left", "valign": "top",
            "content": f"REVISION 1: {REVISION_SUMMARY[inst.kind]} ({REVISED_BY} {REVISED_ON})"
                       .format(name=inst.alignment, curve=inst.curve)}))
    elif template == "fdot":
        common.ok(session.execute("fill_title_block", {"sheet": inst.sheet, "fields": {
            "rev_date_1": REVISED_ON, "rev_desc_1": REVISION_SUMMARY[inst.kind].format(
                name=inst.alignment, curve=inst.curve) + f" ({REVISED_BY})"}}))
    else:
        common.ok(session.execute("fill_title_block", {"sheet": inst.sheet, "fields": {
            "revised_by_1": REVISED_BY, "date_revised_1": REVISED_ON}}))


REVISION_SUMMARY = {"radius": "CURVE {curve} {name} RADIUS REVISED",
                    "pi": "CURVE {curve} {name} PI MOVED",
                    "station": "{name} RESTATIONED"}


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
PROMPTS["pi"] = PROMPTS["radius"]
#: a border with no revision block (FLH's): the revision goes in a note
PROMPTS["note"] = PROMPTS["radius"].replace(
    "Record the revision in the border's revision block (revised by {by}, {on})",
    "Record the revision in a revision note on the sheet, since its border has no revision "
    "block (revised by {by}, {on}),")
#: the vague brief (2026-11-08): the request as a PE hands it over. It keeps what the drafter
#: cannot know (the sheet, where the line lives and how it is attached, the revision's who and
#: when) and the benchmark's instrument rule that the alignment data stays anchored (the E1
#: verifier credits anchored lettering only); it leaves out what picking up a redline means
#: (change the design, bring the sheet up to date), the labelers and where the revision goes
VAGUE = ("Sheet {sheet} came back from checking with a redline, in red on layer REDLINE. Pick it "
         "up: the \"{name}\" line lives in the base file {design}, attached as {ref}, and the "
         "alignment data on the sheet is anchored to it through {ref}; keep it anchored. Record "
         "the revision ({by}, {on}), take the redline off, and leave everything else as it is.")

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

_NAIVE = ("Naive answers shown to fail (tests/test_pilot_redlines.py): the design alone "
          "(stale lettering); the lettering redone with the base left alone; new lettering "
          "beside the old (duplicates)")
_NAIVE_GEOMETRY = (_NAIVE + "; only the stations lettered again, or only the curve table (the "
                   "bearings carry the tangent lengths, the bubble sits at the curve's middle)")
NOTES.update({
    "p11-radius-ppm048": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"IN4\" (L-4, "
        "the NB exit ramp, twist -72.31°; the curve lies mostly past the sheet's match line), "
        "reading REVISE CURVE 1 \"IN4\" LINE / R = 250' / HOLD PI. The line begins on its curve "
        "(BEGIN = BC; AA01 keeps it in PI form). Expected: R 328.08 -> 250 holding BEGIN, the PI "
        "and END: a 59.75' tangent N 02°21'57\" E now leads in (a bearing and a BC 677+89.86 "
        "lettered anew), EC 681+58.69 -> 681+16.44, T 251.05' -> 191.30', L 428.58' -> "
        "326.58', the last tangent 181.44' -> 241.19', and the line 17.50 ft longer (Δ 74°51'), "
        "so every tick and number past the EC moves and the ramp tie reads \"IND1\" 59+72.49 "
        "POT= / \"IN4\" 683+57.63 POT (its \"IND1\" station unchanged); the centerline in AA01 "
        "redrawn, REVISED BY RD / 10-19-26, the redline gone. " + _NAIVE_GEOMETRY
        + "; the tie left at 683+40.13."),
    "p11-radius-ppm230": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"D\" (E-18, "
        "an electrical sheet; the Culver Dr on-ramp, twist -157.24°), reading REVISE CURVE 1 "
        "\"D\" LINE / R = 350' / HOLD PI. The curve ends the line (EC = END) and the line turns "
        "0.26° at an angle point 30.05 ft from BEGIN, which has to be kept (modify_alignment "
        "angle_points; key_points does not list it). Expected: R 419.99 -> 350 holding BEGIN, the "
        "angle point, the PI and END: BC 33+42.55 -> 33+84.67, EC 37+97.52 -> 37+63.81, a "
        "42.11' tangent S 46°23'07\" W after it (its bearing lettered anew), T 252.69' -> "
        "210.58', L 454.96' -> 379.14', the second tangent 559.37' -> 601.48', the line 8.40 ft "
        "longer (END 38+05.92); REVISED BY RD / 10-19-26, the redline gone. " + _NAIVE_GEOMETRY
        + "; the line re-made from BEGIN, the PI and END alone (the angle point dropped)."),
    "p11-radius-wfl07": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"MAIN 01\" "
        "(FLH F.7, Granite Canyon trailhead layout, Mose Wilson Road, 1\" = 40'), reading REVISE "
        "CURVE 1 \"MAIN 01\" LINE / R = 600' / HOLD PI. The sheet is lettered as the real "
        "stationing task leaves it (ticks, numbers, BC/EC, bearings and bubbles; no room for a "
        "curve table), graded D1-02 to D1-05; the FLH border has no revision block, so the "
        "revision goes in a note on the sheet (the prompt says so). The line begins on curve 1. "
        "Expected: R 765.66 -> 600 holding BEGIN and the PIs: a 17.19' tangent S 79°33'22\" E "
        "now leads in (a bearing and a BC 36+56.09 lettered anew), EC 37+98.51 -> 37+81.45, and "
        "curve 2 pushed (re-made in PI form its Δ moves 2'): BC 38+76.60 -> 38+76.86, EC "
        "39+73.83 -> 39+73.81; tangents 78.08' -> 95.42' and 44.52' -> 44.66', END 40+18.35 -> "
        "40+18.48; a revision note RD 10-19-26, the redline gone. " + _NAIVE
        + "; only the stations lettered again (the bubble and bearings stale); no revision "
        "note. A note that quotes the redline's words beside RD and the date is a revision note, "
        "not the redline left."),
    "p11-radius-ppm158": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"SB10\" (PD-32, "
        "pavement delineation and sign plan, twist -85°), reading REVISE CURVE 1 \"SB10\" LINE / "
        "R = 4000' / HOLD PI: the radius taken up. Expected: R 3293.07 -> 4000: BC 1032+94.21 -> "
        "1032+75.70, EC 1034+63.17 -> 1034+81.68, T 84.50' -> 103.01', L 168.96' -> 205.98', "
        "tangents 942.96' -> 924.45' and 288.17' -> 269.66' (the PI form moves the bearings by "
        "seconds), END 1037+51.35 -> 1037+51.34; REVISED BY RD / 10-19-26, the redline gone. The "
        "curve's own PI and its tangents' crossing lie 0.22 ft apart on this flat curve; either "
        "may be held. " + _NAIVE_GEOMETRY + "."),
    "p11-pi-ppm161": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"ENRA\" (PD-2, "
        "the Route 78 on-ramp, twist 28.02°), reading REVISE CURVE 1 \"ENRA\" LINE / MOVE PI "
        "30.00' AHEAD ALONG / BACK TANGENT, HOLD R AND END. Expected: the PI 30 ft further "
        "along the back tangent, R 3726.02 and END held: Δ 7°19'01\" -> 7°45'33\", the ahead "
        "tangent turns S 57°24'17\" E -> S 57°52'00\" E (its bearing changes, not only its "
        "length), BC 850+45.73 -> 850+61.28, EC 855+21.56 -> 855+65.88, T 238.24' -> 252.69', "
        "L 475.83' -> 504.60', tangents 104.39' -> 119.94' and 279.95' -> 235.76', END "
        "858+01.51 -> 858+01.64; REVISED BY RD / 10-19-26, the redline gone. " + _NAIVE_GEOMETRY
        + "; the PI moved back instead (59 ft from where the redline puts it)."),
    "p11-pi-ppm154": (
        "Planted: a red cloud, leader and note on layer REDLINE round curve 1 of \"R1\" (PD-1 of "
        "the Route 65 set, twist -89.94°), reading REVISE CURVE 1 \"R1\" LINE / MOVE PI 30.00' "
        "BACK ALONG / BACK TANGENT, HOLD R AND END. The curve ends the line (EC = END): the PI "
        "moved back opens a tangent after it. Expected: Δ 27°23'11\" -> 23°59'55\", BC "
        "618+45.83 -> 618+42.27, EC 622+52.02 -> 621+98.20, a 53.48' tangent N 28°55'17\" E "
        "after it (its bearing lettered anew), T 207.05' -> 180.62', L 406.19' -> 355.94', the "
        "back tangent 424.08' -> 420.52', END 622+52.02 -> 622+51.68; REVISED BY RD / "
        "10-19-26, the redline gone. " + _NAIVE_GEOMETRY + "; moving the PI ahead instead is "
        "refused by the engine (the curve no longer fits before END)."),
    "p11-station-fdot916": (
        "Planted: a red cloud, leader and note on layer REDLINE round the start of \"CL1\" (FDOT "
        "drainage network plan sheet 1, SR 22, twist -148.34°), reading REVISE \"CL1\" "
        "STATIONING: -41.00' / BEGIN \"CL1\" = 701+88.98. Expected: the begin station changed in "
        "ALI (ALGNRD01.rdraft), every CL1 tick and number moved 41 ft back, BC 705+70.74 -> "
        "705+29.75, EC 707+30.30 -> 706+89.30, and the eight drainage structure callouts, which "
        "give their stations without the line's name (STA. 706+00.00 (45.50 RT), ...), "
        "restationed with their offsets kept (STA. 705+59.00 (45.50 RT), ...); the revision in "
        "FDOT's REVISIONS block (a date and a description naming RD) or a note, the redline "
        "gone; the bearing and curve table stay. " + _NAIVE + "; the shift taken forward; the "
        "structure callouts left."),
    "p11-station-ppm046": (
        "Planted: a red cloud, leader and note on layer REDLINE round the start of \"D13\" (L-2, "
        "Route 65 layout, twist -92.36°), reading REVISE \"D13\" STATIONING: +38.00' / BEGIN "
        "\"D13\" = 651+62.30. Expected: the begin station changed in AA01, every D13 tick and "
        "number 38 ft ahead, BC 654+06.05 -> 654+44.05, the two ramp ties \"IN4\" 661+66.77 BC= "
        "/ 63.32' Rt \"D13\" 661+66.77 POC -> \"D13\" 662+04.77 POC and \"IN3\" 661+70.30 BC= / "
        "63.32' Lt \"D13\" 661+70.30 POC -> \"D13\" 662+08.30 POC, the ramps' own stations "
        "unchanged though they read the same numbers; REVISED BY RD / 10-19-26, the redline "
        "gone. L-2 letters its MBGR ends as bare pluses (+99.5, +46 BEGIN MBGR, ...) that name no "
        "line: re-lettering a plus is allowed, not required. " + _NAIVE + "; the shift taken "
        "back; the ties left; a find-and-replace that moves the ramps' stations too."),
    "p11-station-ppm050": (
        "Planted: a red cloud, leader and note on layer REDLINE round the start of \"F3\" (L-7, "
        "the Ferrari Ranch Rd interchange, twist -131.21°), reading REVISE \"F3\" STATIONING: "
        "-53.00' / BEGIN \"F3\" = 701+22.52. Staged: F3's published EC callout ('\"F3\" "
        "706+27.65 EC', which the strip leaves on its long leader beside the anchored EC) and the "
        "strokes of its traced BC callout in a base taken off, as the layout pilots do. Expected: "
        "every F3 station 53 ft back (BC/EC 701+75.52/702+40.70 -> 701+22.52/701+87.70 and "
        "705+03.21/706+27.68 -> 704+50.21/705+74.68), the three-line tie \"F3\" 707+28.83 POT= "
        "/ \"F2\" 705+19.93 POT= / \"FR\" 71+28.97 POT -> \"F3\" 706+75.83 with F2 and FR "
        "unchanged, the gate and fence callouts 72.07' Lt \"F3\" 706+08.74 -> 705+55.74 and "
        "89.91' Lt \"F3\" 706+08.38 -> 705+55.38; REVISED BY RD / 10-19-26, the redline gone. "
        "F3's 103.79-ft second tangent is not among its elements drawn in AA01; the centerline "
        "item allows the gap. " + _NAIVE + "; the shift taken forward; the callouts left; a "
        "find-and-replace that moves F2's station in the tie too."),
    "p11-station-ppm111": (
        "Planted: a red cloud, leader and note on layer REDLINE round the start of \"IND1\" "
        "(U-1 utility plan, Industrial Avenue, twist -72.31°), reading REVISE \"IND1\" "
        "STATIONING: +62.00' / BEGIN \"IND1\" = 27+41.06. Expected: every IND1 tick and number "
        "62 ft ahead, BC/EC 32+77.97/33+83.15 -> 33+39.97/34+45.15 and 37+66.30/39+04.01 -> "
        "38+28.30/39+66.01, the four rows of the POSITIVE LOCATION INFORMATION table (63.5' Lt "
        "\"IND1\" 35+51.9 -> 36+13.9, ..., 85.7' Lt \"IND1\" 38+75.2 -> 39+37.2, offsets kept) "
        "and general note 4's STATIONS \"IND1\" 53+05 TO \"IND1\" 55+12 -> 53+67 TO 55+74 (off "
        "this sheet, still IND1 stations); REVISED BY RD / 10-19-26, the redline gone. " + _NAIVE
        + "; the shift taken back; the table and the note left."),
})


def _probe(inst: Redline) -> Probe:
    key = "note" if inst.revision == "note" else inst.kind
    template = PROMPTS[key]
    if inst.sheet.isdigit():   # FDOT's sheet "1": "everything on sheet 1"
        template = template.replace("everything on {sheet}", "everything on sheet {sheet}")
    words = dict(sheet=inst.sheet, name=inst.alignment, design=inst.design_file,
                 ref=inst.design_ref, by=REVISED_BY, on=REVISED_ON)
    prompt = template.format(**words)
    return Probe(id=inst.id, prompt=prompt, check=make_check(inst), solve=make_solve(inst),
                 note=NOTES.get(inst.id) or NOTES[inst.kind],
                 tags=["redline", "edit", inst.agency, "base-file", inst.kind], start=inst.id,
                 vague=VAGUE.format(**words), vague_check=make_check(inst, "vague"))


PROBES: List[Probe] = [_probe(i) for i in INSTANCES]

__all__ = ["PROBES", "INSTANCES", "Redline", "apply_revision", "revised_truth", "plant_redline",
           "make_check", "make_solve"]
