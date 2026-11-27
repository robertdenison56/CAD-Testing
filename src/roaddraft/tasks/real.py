"""D1 tasks on real plan sheets: the redrafted example plan sets.

The seeded generator (``tasks.generator``) makes every task from one
synthetic centerline on a blank sheet.  These tasks start from a real plan
sheet instead: one of the sample plan sets redrafted into RoadDraft files
under ``examples/Exmple Plans/Redraft`` (Caltrans PPM, FHWA WFL and CFL,
FDOT), whose sheet file references its own alignment, corridor and survey
base files through a viewport at the published scale and twist.  The
drafter letters one of the sheet's alignments to the spec; everything else
on the sheet -- the other alignments, the corridor, notes, callouts,
legend, border and title block -- is the real sheet's and stays.

Twelve types: five letter one alignment around the sheet's own work
(stationing, bearings, curve callouts, curve table, all of it); the rest are
the sheet's other jobs on the same sets -- draw the alignment in its base
file, re-attach the sheet's base files, fill its title block, lay the sheet
out on the annotated model, annotate it blank, draft it from the base files
alone, or re-place its construction callouts (``tasks.real_callouts``: the
published notes taken off the sheet and handed back with a station and
offset each; ``START_KIND`` says how each starts).

A lettering task is made from (sheet, alignment, task type):

1. The design is the base file's alignment as it is.  The sheet file does
   not own it, so labels anchor through the reference (``AA01:TB1``), the
   ``annotate-base`` route.
2. The truth is ``compute_ground_truth`` on it, at the sheet's own scale,
   viewport and twist: the same code the synthetic tasks use.
3. That alignment's own real annotation is removed from the copies the
   task ships (``strip_alignment``): the stationing anchored to it in the
   base; text whose station or bearing is one of its curve points or
   tangents and that stands next to it; the bubbles at its curve
   midpoints (a Circle, or a ring of vertices as the Caltrans sheets were
   digitised); its rows of a CURVE DATA table.  The leaders of what is
   removed go with it.  A table that tabulates other lines' curves too
   (Route 65 L-1 lists TB1's and TB2's) keeps their rows, closed up.
4. The phases the task gives are drafted on the sheet file in the spec's
   conventions; the phases it asks for are left to the drafter.
5. The curve table goes in the clear space nearest the real table it
   replaces (else the lower right), found on an occupancy grid of
   everything the finished sheet shows; when the real table stays for the
   other lines' rows, the new one goes below it.

Legibility on a real sheet judges the drafter's work, not the original
drafters': each truth sheet lists ``given_entities`` (what the starting
document holds), and the verifier counts no overlap between two given items
and no given item off the sheet; an overlap between new work and the real
sheet still counts, and the referenced base files' text (the other
alignments' stationing, R/W tags) joins the sheet as given context.

A (sheet, alignment, type) is a benchmark task only when its reference
solution verifies 100 and its starting document 0 at both prompt levels
(``validate``); ``catalog`` sweeps every candidate and records why the
rest were left out.
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from matplotlib.path import Path as _MplPath

from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.core import geometry as geo
from roaddraft.design.horizontal import Alignment, CurveElement
from roaddraft.document.document import Document
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Hatch, Line, Point, Polyline, Table, Text, expand_entities,
    loop_points,
)
from roaddraft.document.fileformat import read_document
from roaddraft.document.references import reference_alignments, reference_groups, space_primitives
from roaddraft.tasks.brief import Task, TaskBrief, compute_task_id
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.prompts import render_prompts
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash, spec_subset
from roaddraft.tasks.types import PHASE_ORDER, REAL_JOB_TYPES, REAL_TASK_TYPES, TaskType, task_type

REAL_GENERATOR_VERSION = "real-v1"  # (2026-10-13) first cut: one sheet, one alignment per task

REPO = Path(__file__).resolve().parents[3]
REDRAFT_ROOT = REPO / "examples" / "Exmple Plans" / "Redraft"
#: the redrafted plan sets, in catalogue order, with the agency each comes from
AGENCIES: Dict[str, str] = {
    "Caltrans-PPM": "Caltrans",
    "WFL": "FHWA Western Federal Lands",
    "CFL": "FHWA Central Federal Lands",
    "FDOT-NexGen": "FDOT",
}
#: how each real type starts: the file the drafter works in, and how it is cut --
#: ``letter`` the sheet file without the alignment's annotation; ``draw`` the alignment's
#: base file without its centerline; ``attach`` the sheet file with no references;
#: ``title`` the sheet file with its title block emptied; ``setup`` the sheet file with
#: its sheet gone and the alignment annotated in the model; ``blank`` the sheet emptied;
#: ``scratch`` the sheet file with its sheet gone; ``notes`` the sheet file with a spread
#: of its construction callouts removed
START_KIND = {
    "real-stationing": "letter", "real-bearings": "letter", "real-callouts": "letter",
    "real-curve-table": "letter", "real-alignment-data": "letter",
    "real-draw-alignment": "draw", "real-attach-reference": "attach",
    "real-title-block": "title", "real-sheet-setup": "setup",
    "real-annotate-sheet": "blank", "real-plan-sheet": "scratch",
    "real-construction-callouts": "notes",
    # the whole job (types.REAL_JOB_TYPES): a sheet from scratch or a blank sheet, its
    # construction callouts asked for with the rest
    "real-sheet-job": "scratch", "real-annotate-job": "blank",
}
#: types about the sheet itself, not one of its alignments: one task per sheet
SHEET_TYPES = ("real-attach-reference", "real-title-block", "real-construction-callouts")
#: types whose targets may sit on any referenced line, traced centerlines included: the
#: alignment named is the task's primary line, not the one lettered
ANY_LINE_TYPES = ("real-construction-callouts",)
#: the fields of each border a drafter fills for a sheet (key, how the prompt names it),
#: and the two a vague prompt still states (the rest need only be filled)
TITLE_FIELDS = {
    "caltrans": (("dist", "Dist"), ("county", "County"), ("route", "Route"),
                 ("post_miles", "Post miles"), ("project_number_phase", "Project number & phase"),
                 ("sheet_title", "Sheet title"), ("sheet_id", "Sheet"), ("scale", "Scale")),
    "wfl": (("project", "Project"), ("project_name", "Project name"),
            ("sheet_number", "Sheet number"), ("sheet_title", "Sheet title")),
    "fdot": (("road_no", "Road no."), ("county", "County"), ("fpid", "Financial project ID"),
             ("sheet_number", "Sheet no."), ("eor_name", "Engineer of record"),
             ("eor_license", "License"), ("eor_firm", "Firm")),
}
TITLE_VAGUE = {"caltrans": ("route", "sheet_id"), "wfl": ("project", "sheet_number"),
               "fdot": ("fpid", "sheet_number")}
#: the north arrow's scale per inch of sheet height (the spec's 0.9 on a 22-in ANSI D)
NORTH_SCALE_PER_IN = 0.9 / 22.0

#: phases the real files supply: never drafted by the reference
REAL_PHASES = ("design", "linework", "reference", "sheet", "north", "title")
#: annotation phases the reference drafts on the sheet file, in order
ANNOTATION_PHASES = ("stationing", "bearings", "callouts", "table")

# -- which alignments are worth lettering (the oracle decides the rest)
MAX_TANGENTS = 6
MAX_CURVES = 4
MIN_LENGTH_FT = 200.0

# -- what counts as an alignment's own real annotation (paper inches)
POINT_LABEL_REACH_IN = 1.0    # a curve-point label's box within this of its point
BEARING_REACH_IN = 1.0        # a bearing's box within this of its tangent
BUBBLE_MAX_RADIUS_IN = 0.5    # a curve bubble is a circle no bigger than this
BUBBLE_REACH_IN = 2.5         # ... centred within this of the curve's midpoint
RING_MIN_IN = 0.15            # a bubble digitised as a ring of vertices is at least this across
RING_MAX_IN = 0.5             # ... and at most this, round to 10 %, of RING_MIN_VERTICES or more
RING_MIN_VERTICES = 8         # ... on the sheet, with a leader from it that ends on the curve
LEADER_TIP_IN = 0.2           # a bubble's leader ends within this of the curve it calls out
LEADER_REACH_IN = 0.12        # a leader ends within this of what it points from
LEADER_MAX_IN = 4.0           # ... and is no longer than this
# the base files' alignments are rebuilt from the published linework, so their values
# drift from what the sheet letters (L-1's TB1: BC 642+81.10 against 642+81.23 lettered,
# R 3242.93 against 3280'): real annotation is matched loosely, and by where it stands
STATION_TOL_FT = 2.0          # a lettered station within this of the rebuilt one
RADIUS_TOL = 0.03             # a tabulated radius within 3 % of the rebuilt one
ROW_RADIUS_TOL = 0.05         # a table row is a curve's within 5 % (the redraft's fit of a curve
                              # the sheet clips drifts further than its table names it)
RULE_TOL_IN = 0.02            # a table rule lies along a row's edge within this
BEARING_TOL_MIN = 15          # a lettered bearing within 15 minutes of the rebuilt one
LENGTH_MIN_FT = 50.0          # a lettered tangent length, not a lane width
LENGTH_ALONG_DEG = 5.0        # ... set along its tangent
LENGTH_REACH_IN = 0.6         # ... and right beside it
STATION_REACH_IN = 0.6        # a lettered station number within this of its station
TICK_MAX_IN = 0.4             # a station tick no longer than this ...
TICK_REACH_IN = 0.08          # ... centred within this of its station
BLOCK_GAP_IN = 0.3            # the lines of a curve data block stand this close
TABLE_TITLE = re.compile(r"\bCURVE\s+(DATA|TABLE)\b|\bHORIZONTAL\s+CURVE", re.I)

# -- the curve table's clear space
GRID_IN = 0.05
TABLE_MARGIN_IN = 0.2

# -- where a label goes when the spec's pose lands on the sheet's work (paper inches):
# the spec's side and offset first, then the other side, then further off
POINT_OFFSETS_IN = (0.45, 0.75, 1.05)
BEARING_OFFSETS_IN = (0.06, 0.2, 0.35)
MC_OFFSETS_IN = (0.80, 1.2, 1.6)
OUT_OF_VIEW_COST = 100


# ===================================================================== catalogue


@dataclass(frozen=True)
class RealSheet:
    """One redrafted plan sheet that carries a rebuilt alignment."""

    id: str             # the manifest id: PPM-045, WFL-Plan-Profile-Sheets-p14, ...
    agency: str         # the redraft folder: Caltrans-PPM, WFL, CFL, FDOT-NexGen
    folder: Path        # the sheet's file set
    sheet_file: str     # the sheet file; every other .rdraft beside it is a base file
    family: str         # layout, plan-profile, drainage, ...
    project: str        # the project the sample is from, when the manifest names one
    alignments: Tuple[str, ...]

    @property
    def agency_name(self) -> str:
        return AGENCIES.get(self.agency, self.agency)

    @property
    def files(self) -> List[str]:
        return sorted(p.name for p in self.folder.glob("*.rdraft"))


def _locate(agency: str, row: dict) -> Optional[Path]:
    hits = sorted((REDRAFT_ROOT / agency).rglob(row["sheet_file"]))
    for h in hits:
        if h.parent.name == row["id"] or h.parent.name.startswith(row["id"] + "-"):
            return h.parent
    return hits[0].parent if len(hits) == 1 else None


#: redrafted sheets whose alignment was rebuilt for TRAINING (2026-11-26): the Route 70
#: stage construction and Route 121 traffic handling sheets of the PPM examples, numbered
#: from readings in their redraft configs (``stations``).  No held-out set draws on these
#: two projects.  They are not catalogue sheets: ``real_sheets``, ``candidates`` and
#: ``catalog`` leave them out, so the held-out catalogue is what it was.
TRAIN_SHEET_IDS = frozenset(f"PPM-{n}" for n in (*range(128, 141), 142, *range(144, 151)))


def real_sheets() -> Tuple[RealSheet, ...]:
    """Every redrafted plan sheet with a rebuilt alignment, in catalogue order
    (the training sheets, ``TRAIN_SHEET_IDS``, left out: ``train_sheets``)."""
    return tuple(s for s in _all_sheets() if s.id not in TRAIN_SHEET_IDS)


def train_sheets() -> Tuple[RealSheet, ...]:
    """The redrafted plan sheets kept for training (``TRAIN_SHEET_IDS``)."""
    return tuple(s for s in _all_sheets() if s.id in TRAIN_SHEET_IDS)


@lru_cache(maxsize=1)
def _all_sheets() -> Tuple[RealSheet, ...]:
    out: List[RealSheet] = []
    for agency in AGENCIES:
        manifest = REDRAFT_ROOT / agency / "redraft-manifest.csv"
        if not manifest.exists():
            continue
        with manifest.open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("status") != "ok" or row.get("kind") != "plan" or not row.get("alignments"):
                    continue
                folder = _locate(agency, row)
                if folder is None:
                    continue
                out.append(RealSheet(id=row["id"], agency=agency, folder=folder,
                                     sheet_file=row["sheet_file"], family=row.get("family", ""),
                                     project=row.get("project", "") or "",
                                     alignments=tuple(row["alignments"].split())))
    return tuple(out)


def real_sheet(sheet_id: str) -> RealSheet:
    for s in _all_sheets():
        if s.id == sheet_id:
            return s
    raise ValueError(f"no redrafted plan sheet {sheet_id!r}")


def _load(path: Path) -> Document:
    doc = Document.from_dict(read_document(path))
    doc._path = path
    return doc


def _only_sheet(doc: Document):
    sheets = list(doc.sheets.values())
    if len(sheets) != 1:
        raise ValueError(f"{doc.meta.get('project_name')}: expected one sheet, found {len(sheets)}")
    return sheets[0]


def usable_alignment(align: Alignment) -> Optional[str]:
    """Why an alignment cannot carry a lettering task, or None when it can.
    Rebuilt centerlines traced as dozens of short lines are left out: a
    bearing per 20-ft tangent is not a plan sheet."""
    kinds = {el.kind for el in align.elements}
    if not kinds <= {"tangent", "curve"}:
        return "has elements other than tangents and curves"
    n_t, n_c = len(align.tangents()), len(align.curves())
    if n_t > MAX_TANGENTS:
        return f"{n_t} tangents (traced linework, more than {MAX_TANGENTS})"
    if n_c > MAX_CURVES:
        return f"{n_c} curves (more than {MAX_CURVES})"
    if align.length < MIN_LENGTH_FT:
        return f"{align.length:.0f} ft long (under {MIN_LENGTH_FT:.0f})"
    return None


def type_fits(align: Alignment, ttype: TaskType) -> Optional[str]:
    """Why a task type has nothing to ask of this alignment, or None."""
    from roaddraft.design.labels import stationing_plan
    n_c, n_t = len(align.curves()), len(align.tangents())
    if ({"callouts", "table", "curve_points"} & ttype.asks) and not n_c:
        return "no curve to number, tabulate or letter"
    if "bearings" in ttype.asks and not n_t:
        return "no tangent to label"
    if "curve_points" in ttype.asks and not any(
            l.kind in ("pc", "pt", "pcc", "prc") for l in stationing_plan(align).labels()):
        return "no curve begins or ends on it (it starts or stops inside one)"
    return None


def candidates(types: Optional[Dict[str, TaskType]] = None,
               train: bool = False) -> List[Tuple[RealSheet, str, str]]:
    """``(sheet, alignment, task type)`` for every pairing worth building, of
    ``types`` (``REAL_TASK_TYPES``; ``REAL_JOB_TYPES`` for the whole-job catalogue);
    ``train`` takes the training sheets instead of the catalogue's."""
    out = []
    for src in (train_sheets() if train else real_sheets()):
        doc = _load(src.folder / src.sheet_file)
        sheet = _only_sheet(doc)
        if len(sheet.viewports) != 1:
            continue
        fpi = float(sheet.viewports[0].feet_per_inch)
        if fpi not in [float(f) for f in DRAFTING_SPEC_V1["sheet"]["allowed_feet_per_inch"]]:
            continue  # a scale the spec does not draft at
        every = [align for _ref, _base, align, placement in reference_alignments(doc)
                 if placement.is_identity]
        aligns = [align for align in every if not usable_alignment(align)]
        for name, ttype in (types or REAL_TASK_TYPES).items():
            pool = every if name in ANY_LINE_TYPES else aligns
            fits = [a for a in pool if not type_fits(a, ttype)]
            for align in fits[:1] if name in SHEET_TYPES else fits:
                out.append((src, align.name, name))
    return out


# ===================================================================== stripping


_STATION = re.compile(r"(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)")
_POINT_WORD = re.compile(r"\b(BCC|ECC|PCC|PRC|BC|EC|PC|PT)\b")
_BEARING = re.compile(r"\b([NS])\s*(\d{1,3})\s*°\s*(\d{1,2})(?:\s*['’′]\s*(?:\d{1,2}(?:\.\d+)?)?"
                      r"\s*(?:\"|”|″|''|’’)?)?\s*([EW])?")
_NUMBER = re.compile(r"(\d[\d,]*\.?\d*)")
#: the lines of a curve data block: PI STA. = 709+72.30, Δ = 49°03'08", R = 881.00', ...
_CURVE_DATA_LINE = re.compile(
    r"^\s*(=|(PI|PC|PT|PCC|PRC|POC|CURVE|NO\.?|Δ|¬|DELTA|D|T|L|R|E|M|C|LC|CH|CB|BRG|e|SE)"
    r"\b\s*(STA\.?)?\s*(=|\d|\(|$))", re.I)
#: a value lettered on its own in a block (CFL splits "R =" and "855.00'"): a number,
#: station or angle, perhaps after "=", perhaps with (LT)/(RT)
_CURVE_DATA_VALUE = re.compile(
    r"^\s*=?\s*(\d+\s*\+\s*\d+(\.\d+)?|[\d,]+(\.\d+)?\s*['’]?|\d+\s*°.*)\s*"
    r"(\((LT|RT|L|R)\))?\s*$")
BLOCK_MIN_LABELS = 3          # a curve data block letters at least three of PI, Δ, R, T, L
_LENGTH_ONLY = re.compile(r"^\s*(\d[\d,]*\.\d{1,2})\s*['’′]\s*$")
_LENGTH_AT_END = re.compile(r"(\d[\d,]*\.\d+)\s*['’′]\s*$")


def _stations_in(text: str) -> List[float]:
    return [int(a) * 100.0 + float(b) for a, b in _STATION.findall(text)]


def _bearings_in(text: str) -> List[Tuple[str, int, int, Optional[str]]]:
    return [(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))
            for m in _BEARING.finditer(text)]


def _same_bearing(a, b) -> bool:
    if a[0] != b[0] or a[3] and b[3] and a[3] != b[3]:
        return False
    return abs((a[1] * 60 + a[2]) - (b[1] * 60 + b[2])) <= BEARING_TOL_MIN


def _numbers_in(text: str) -> List[float]:
    out = []
    for m in _NUMBER.findall(text.replace(",", "")):
        try:
            out.append(float(m))
        except ValueError:
            pass
    return out


def _quad(text: Text, doc: Document, scale: float = 1.0, to=lambda p: p, twist: float = 0.0):
    """Corners of a text's box, mapped by ``to`` (model -> paper) at ``scale``."""
    from roaddraft.verify.legibility import text_quad
    style = doc.text_styles.get(text.style)
    return text_quad(to(text.position), text.content, text.height * scale,
                     text.rotation_deg + twist, text.halign, text.valign,
                     style.width_factor if style else 1.0)


def _dist_to_poly(p, poly) -> float:
    if geo.point_in_polygon(p, poly):
        return 0.0
    return min(geo.dist_point_to_segment(p, poly[i], poly[(i + 1) % len(poly)])
               for i in range(len(poly)))


def _poly_dist(a, b) -> float:
    """Distance between two convex polygons (0 when they touch)."""
    if any(geo.point_in_polygon(p, b) for p in a) or any(geo.point_in_polygon(p, a) for p in b):
        return 0.0
    return min(geo.dist_point_to_segment(p, b[i], b[(i + 1) % len(b)])
               for p in a for i in range(len(b)))


def _ends(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [list(e.start), list(e.end)]
    if isinstance(e, Polyline) and e.vertices:
        return [list(e.vertices[0]), list(e.vertices[-1])]
    return []


def _length(e) -> float:
    if isinstance(e, Line):
        return geo.distance(e.start, e.end)
    if isinstance(e, Polyline):
        return sum(geo.distance(a, b) for a, b in zip(e.vertices, e.vertices[1:]))
    return math.inf


@dataclass
class _Targets:
    """What the alignment's own annotation would say, and where it stands,
    in the coordinates of one space (``scale`` feet or inches per model foot)."""

    points: List[Tuple[float, List[float]]]          # (raw station, point)
    tangents: List[Tuple[tuple, List[float], List[float], float]]  # (bearing, start, end, length)
    midpoints: List[List[float]]                     # curve midpoints
    radii: List[float]
    unit: float                                      # space units per paper inch
    stations: List[Tuple[int, str, List[float]]] = field(default_factory=list)  # (hundreds, text, point)
    curves: List[Tuple[float, float]] = field(default_factory=list)   # (radius, length) of each curve
    others: List[Tuple[float, float]] = field(default_factory=list)   # the sheet's other lines' curves
    curve_paths: List[List[List[float]]] = field(default_factory=list)  # each curve, sampled


def _targets(align: Alignment, truth_labels: Sequence[dict], to, unit: float,
             others: Sequence[Alignment] = ()) -> _Targets:
    points = [(float(l["station"]), to(align.station_to_xy(float(l["station"]))[0]))
              for l in truth_labels if l["kind"] in ("pc", "pt", "pcc", "prc")]
    bearings = [_bearings_in(l["content"])[0] for l in truth_labels
                if l["kind"] == "bearing" and _bearings_in(l["content"])]
    tangents = [(b, to(t.start), to(t.end), float(t.length))
                for b, t in zip(bearings, align.tangents())]
    mids, paths = [], []
    for c in align.curves():
        mids.append(to(align.point_at((c.start_dist + c.end_dist) / 2.0)))
        paths.append([to(align.point_at(c.start_dist + c.length * k / 40.0)) for k in range(41)])
    st = align.stations()
    stations = []
    for l in truth_labels:
        if l["kind"] == "station":
            disp, _region = st.to_display(float(l["station"]))
            stations.append((int(round(disp / 100.0)), l["anchor"],
                             to(align.station_to_xy(float(l["station"]))[0])))
    curves = [(float(c.radius), float(c.length)) for c in align.curves()]
    return _Targets(points, tangents, mids, [r for r, _l in curves], unit, stations, curves,
                    [(float(c.radius), float(c.length)) for o in others for c in o.curves()], paths)


def _is_point_label(text: Text, quad, tg: _Targets) -> bool:
    if not _POINT_WORD.search(text.content):
        return False
    for sta in _stations_in(text.content):
        for raw, p in tg.points:
            if abs(sta - raw) <= STATION_TOL_FT and _dist_to_poly(p, quad) <= POINT_LABEL_REACH_IN * tg.unit:
                return True
    return False


def _is_length(text: Text, quad, tg: _Targets) -> bool:
    """A tangent's length lettered on its own beside it (the published sheets
    split ``N 03°57'06" W`` and ``417.16'`` into two texts)."""
    m = _LENGTH_ONLY.match(text.content)
    if not m:
        return False
    v = float(m.group(1).replace(",", ""))
    for _b, a, c, L in tg.tangents:
        near = min(geo.dist_point_to_segment(q, a, c) for q in quad)
        if abs(v - L) <= max(STATION_TOL_FT, 0.01 * L) and near <= BEARING_REACH_IN * tg.unit:
            return True
        # the published length of a tangent the rebuild shortened (L-1's TB1: 417.16'
        # lettered, 386.53 ft rebuilt): a length to the hundredth lettered along it
        along = abs((float(text.rotation_deg) - math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))
                     + 90.0) % 180.0 - 90.0)
        if (v >= LENGTH_MIN_FT and "." in m.group(1) and along <= LENGTH_ALONG_DEG
                and near <= LENGTH_REACH_IN * tg.unit):
            return True
    return False


def _is_station_number(text: Text, quad, tg: _Targets) -> bool:
    """A station lettered as plain text beside its station: ``703``, ``3``,
    ``703+00`` (a profile grid's station axis stands far off and stays)."""
    c = text.content.strip()
    for h, sta_text, p in tg.stations:
        if c in (str(h), str(h % 10), f"{h}+00", sta_text) and \
                _dist_to_poly(p, quad) <= STATION_REACH_IN * tg.unit:
            return True
    return False


def _ticks(ents: Dict[str, object], tg: _Targets) -> List[str]:
    """Short lines centred on the alignment's stations: its published ticks."""
    out = []
    for e in ents.values():
        if not isinstance(e, Line) or _length(e) > TICK_MAX_IN * tg.unit:
            continue
        anchor = getattr(e, "anchor", None) or {}
        if anchor.get("placed_by") == "draw_alignment":
            continue
        m = [(e.start[0] + e.end[0]) / 2.0, (e.start[1] + e.end[1]) / 2.0]
        if any(geo.distance(m, p) <= TICK_REACH_IN * tg.unit for _h, _t, p in tg.stations):
            out.append(e.id)
    return out


def _curve_data_block(ents: Dict[str, object], doc: Document, tg: _Targets) -> List[str]:
    """A curve data block without a grid (FDOT, CFL): a CURVE DATA title or an
    ``R = ...`` line with one of the alignment's radii, and the curve data
    lines stacked with it."""
    texts = {e.id: e for e in ents.values() if isinstance(e, Text) and e.content.strip()}
    boxes = {i: geo.bbox_of_points(_quad(t, doc)) for i, t in texts.items()}
    labels = {i for i, t in texts.items()
              if _CURVE_DATA_LINE.match(t.content) or TABLE_TITLE.search(t.content)}
    datalike = labels | {i for i, t in texts.items() if _CURVE_DATA_VALUE.match(t.content)}

    def radius_in(i: str) -> bool:
        return any(abs(v - r) <= RADIUS_TOL * r for v in _numbers_in(texts[i].content)
                   for r in tg.radii)

    out: List[str] = []
    for seed in sorted(datalike):
        if seed in out or not (TABLE_TITLE.search(texts[seed].content) or radius_in(seed)):
            continue
        block, box = {seed}, boxes[seed]
        grown = True
        while grown:
            grown = False
            for i in datalike - block:
                if geo.bbox_intersects(geo.bbox_expand(box, BLOCK_GAP_IN), boxes[i]):
                    block.add(i)
                    box = geo.bbox_union(box, boxes[i])
                    grown = True
        named = sum(1 for i in block if i in labels and not _CURVE_DATA_VALUE.match(texts[i].content))
        if named >= BLOCK_MIN_LABELS and any(radius_in(i) for i in block):
            out += sorted(block - set(out))
    return out


def _is_bearing(text: Text, quad, tg: _Targets) -> bool:
    for b in _bearings_in(text.content):
        for tb, a, c, _L in tg.tangents:
            if _same_bearing(b, tb) and min(
                    geo.dist_point_to_segment(q, a, c) for q in quad) <= BEARING_REACH_IN * tg.unit:
                return True
    return False


def _ring(e, unit: float):
    """A curve bubble digitised as a closed ring of vertices (the Caltrans
    sheets' S-ANNO-TAG polylines): its centre and radius, else None."""
    if not isinstance(e, Polyline) or len(e.vertices) < RING_MIN_VERTICES:
        return None
    pts = [list(v) for v in e.vertices]
    if not (e.closed or geo.distance(pts[0], pts[-1]) <= RULE_TOL_IN * unit):
        return None
    bb = geo.bbox_of_points(pts)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    across = max(w, h)
    if not (RING_MIN_IN * unit <= across <= RING_MAX_IN * unit and abs(w - h) <= 0.1 * across):
        return None
    return [(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0], across / 2.0


def _square(center, r: float) -> List[List[float]]:
    x, y = center
    return [[x - r, y - r], [x + r, y - r], [x + r, y + r], [x - r, y + r]]


def _dist_to_path(p, path) -> float:
    return min(geo.dist_point_to_segment(p, a, b) for a, b in zip(path, path[1:]))


def _called_out(ents: Dict[str, object], square, tg: _Targets) -> bool:
    """A leader runs from the box ``square`` to one of the alignment's curves."""
    for e in ents.values():
        ends = _ends(e)
        if not ends or _length(e) > LEADER_MAX_IN * tg.unit:
            continue
        for a, b in ((ends[0], ends[1]), (ends[1], ends[0])):
            if (_dist_to_poly(a, square) <= LEADER_REACH_IN * tg.unit
                    and any(_dist_to_path(b, path) <= LEADER_TIP_IN * tg.unit
                            for path in tg.curve_paths)):
                return True
    return False


def _bubbles(ents: Dict[str, object], doc: Document, tg: _Targets, quad_of
             ) -> Tuple[List[str], List[list]]:
    """Curve bubbles at the alignment's curve midpoints, and the number in
    each: a Circle within reach of a midpoint; on the sheet also a ring of
    vertices within reach whose leader ends on one of the alignment's curves
    (the sheets' note tags are rings too, so reach alone does not name one;
    in a base file a ring that size is a road symbol).  Returns the ids and
    the bubbles' boxes (what their leaders end on)."""
    out, quads = [], []
    rings = []  # (midpoint index, distance, id, center, radius): each curve takes the nearest
    for e in ents.values():
        if isinstance(e, Circle):
            if e.radius > BUBBLE_MAX_RADIUS_IN * tg.unit:
                continue
            center, radius = list(e.center), float(e.radius)
            if not any(geo.distance(center, m) <= BUBBLE_REACH_IN * tg.unit for m in tg.midpoints):
                continue
            out.append(e.id)
            quads.append(_square(center, radius))
        else:
            ring = _ring(e, tg.unit) if tg.unit == 1.0 else None
            if ring is None:
                continue
            center, radius = ring
            if not _called_out(ents, _square(center, radius), tg):
                continue
            near = [(geo.distance(center, m), k) for k, m in enumerate(tg.midpoints)
                    if geo.distance(center, m) <= BUBBLE_REACH_IN * tg.unit]
            if near:
                d, k = min(near)
                rings.append((k, d, e.id, center, radius))
    taken = set()
    for k, _d, rid, center, radius in sorted(rings, key=lambda r: (r[0], r[1])):
        if k in taken:
            continue
        taken.add(k)
        out.append(rid)
        quads.append(_square(center, radius))
    digits = []
    for rid, square in zip(out, quads):
        center = [(square[0][0] + square[2][0]) / 2.0, (square[0][1] + square[2][1]) / 2.0]
        radius = (square[2][0] - square[0][0]) / 2.0
        for t in ents.values():
            if (isinstance(t, Text) and t.content.strip().isdigit()
                    and geo.distance(t.position, center) <= 1.3 * radius):
                digits.append(t.id)
    return out + digits, quads


# ------------------------------------------------------------- the curve table

_R_HEADER = re.compile(r"^\s*R(ADIUS)?\b", re.I)
_L_HEADER = re.compile(r"^\s*L(ENGTH)?\b", re.I)
_DMS = re.compile(r"[°º]")


def _cell_value(cell: str) -> Optional[float]:
    """The number a table cell states, unless it is an angle."""
    if _DMS.search(cell):
        return None
    nums = _numbers_in(cell)
    return nums[0] if nums else None


def _own_rows(rows: Sequence[Sequence[str]], headers: Sequence[str], tg: _Targets) -> List[int]:
    """Indices of the rows that tabulate the alignment's curves.  A row is a
    curve's when its R is within ROW_RADIUS_TOL of the curve's radius.  Where
    the sheet's lines have curves of nearly one radius (Route 65's ramps run
    4,850 to 5,000 ft), each curve on the sheet takes the one row it fits
    best, by radius then by length, the best fits first."""
    r_col = next((i for i, h in enumerate(headers) if _R_HEADER.match(h)), None)
    l_col = next((i for i, h in enumerate(headers) if _L_HEADER.match(h)), None)
    pairs = []
    for ri, row in enumerate(rows):
        if r_col is not None and r_col < len(row):
            value = _cell_value(row[r_col])
            radii = [value] if value is not None else []
        else:  # no R header: any plain number in the row may be the radius
            radii = [v for v in (_cell_value(c) for c in row) if v is not None]
        length = _cell_value(row[l_col]) if l_col is not None and l_col < len(row) else None
        for mine, curves in ((True, tg.curves), (False, tg.others)):
            for ci, (cr, cl) in enumerate(curves):
                for value in radii:
                    if abs(value - cr) <= ROW_RADIUS_TOL * cr:
                        score = abs(value - cr) / cr
                        if length is not None and cl:
                            score += abs(length - cl) / cl
                        pairs.append((score, ri, mine, ci))
    taken_rows, taken_curves, own = set(), set(), []
    for _score, ri, mine, ci in sorted(pairs):
        if ri in taken_rows or (mine, ci) in taken_curves:
            continue
        taken_rows.add(ri)
        taken_curves.add((mine, ci))
        if mine:
            own.append(ri)
    return sorted(own)


@dataclass
class _TableCut:
    """What ``_table_cut`` did to a curve data table."""

    ids: List[str] = field(default_factory=list)       # entities removed
    rows: List[str] = field(default_factory=list)      # rows removed from a kept table
    corner: Optional[List[float]] = None               # the published table's top-left corner
    kept: Optional[List[float]] = None                 # the kept table's box, when rows remain


def _is_rule(e, bb, horizontal: bool, span: float) -> bool:
    """A grid rule: a Line along one axis at least half the grid's span."""
    if not isinstance(e, Line):
        return False
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    return (h <= RULE_TOL_IN and w >= 0.5 * span) if horizontal else (w <= RULE_TOL_IN and h >= 0.5 * span)


def _shifted(p, dy: float):
    return [float(p[0]), float(p[1]) + dy]


def _table_cut(ents: Dict[str, object], doc: Document, tg: _Targets) -> _TableCut:
    """A curve data table that tabulates one of the alignment's curves.  Only
    the alignment's rows go: when the table tabulates other lines' curves too
    (L-1's lists TB1's and TB2's), their rows stay and the table is kept,
    the rows below the cut closed up; a table that tabulates nothing else
    goes whole.  Works on a Table entity, or on a title with a grid of lines
    and text cells under it (the redrafted Caltrans sheets)."""
    for e in list(ents.values()):
        if not isinstance(e, Table):
            continue
        heads = [str(c.get("header", "")) for c in e.columns]
        if not (TABLE_TITLE.search(str(getattr(e, "title", "") or "")) or "Δ" in " ".join(heads)):
            continue
        own = _own_rows(e.rows, heads, tg)
        if not own:
            continue
        bb = e.bbox(doc)
        corner = [bb[0], bb[3]]
        if len(own) == len(e.rows):
            return _TableCut(ids=[e.id], corner=corner)
        e.rows = [r for i, r in enumerate(e.rows) if i not in own]
        return _TableCut(rows=[f"{e.id}:{i}" for i in own], corner=corner, kept=list(e.bbox(doc)))
    for title in ents.values():
        if not (isinstance(title, Text) and TABLE_TITLE.search(title.content)):
            continue
        tq = _quad(title, doc)
        tb = geo.bbox_of_points(tq)
        # the grid: axis-aligned lines in a window below the title, grown from the
        # lines that start just under it
        window = (tb[0] - 8.0, tb[1] - 6.0, tb[2] + 8.0, tb[3] + 0.3)
        lines = []
        for e in ents.values():
            pts = (_ends(e) if isinstance(e, Line)
                   else [list(v) for v in e.vertices] if isinstance(e, Polyline) else [])
            if pts and all(geo.bbox_contains(window, (p[0], p[1], p[0], p[1])) for p in pts):
                lines.append((e.id, geo.bbox_of_points(pts)))
        region = None
        seed = [lid for lid, bb in lines if tb[1] - 0.45 <= bb[3] <= tb[1] + 0.05
                and bb[0] <= tb[2] and bb[2] >= tb[0]]
        if not seed:
            continue
        grid = set(seed)
        region = None
        for lid, bb in lines:
            if lid in grid:
                region = geo.bbox_union(region, bb)
        grown = True
        while grown:
            grown = False
            for lid, bb in lines:
                if lid not in grid and geo.bbox_intersects(geo.bbox_expand(region, 0.02), bb):
                    grid.add(lid)
                    region = geo.bbox_union(region, bb)
                    grown = True
        cells = [t for t in ents.values() if isinstance(t, Text) and t.id != title.id
                 and geo.bbox_contains(region, (t.position[0], t.position[1],
                                                t.position[0], t.position[1]))]
        boxes = {lid: bb for lid, bb in lines if lid in grid}
        span_x, span_y = region[2] - region[0], region[3] - region[1]
        # the rows are the bands between the horizontal rules, the columns the
        # gaps between the vertical ones
        ys = sorted({round(bb[1], 3) for lid, bb in boxes.items()
                     if _is_rule(ents[lid], bb, True, span_x)
                     and region[1] + RULE_TOL_IN < bb[1] < region[3] - RULE_TOL_IN}, reverse=True)
        edges = [region[3]] + ys + [region[1]]
        bands = [(edges[i + 1], edges[i]) for i in range(len(edges) - 1)]  # (lo, hi), top first
        xs = sorted({round(bb[0], 3) for lid, bb in boxes.items()
                     if _is_rule(ents[lid], bb, False, span_y)
                     and region[0] + RULE_TOL_IN < bb[0] < region[2] - RULE_TOL_IN})
        col_edges = [region[0]] + xs + [region[2]]

        def col_of(t: Text) -> int:
            return max(0, min(len(col_edges) - 2,
                              sum(1 for x in col_edges[1:-1] if t.position[0] >= x)))

        band_cells = [[t for t in cells if lo <= t.position[1] < hi] for lo, hi in bands]
        header_i = next((i for i, bc in enumerate(band_cells)
                         if any(_R_HEADER.match(t.content) or "Δ" in t.content for t in bc)), None)
        headers = [""] * (len(col_edges) - 1)
        if header_i is not None:
            for t in band_cells[header_i]:
                headers[col_of(t)] = (headers[col_of(t)] + " " + t.content).strip()
        data_i = [i for i, bc in enumerate(band_cells) if bc and i != header_i]
        rows = []
        for i in data_i:
            row = [""] * len(headers)
            for t in band_cells[i]:
                row[col_of(t)] = (row[col_of(t)] + " " + t.content).strip()
            rows.append(row)
        own = _own_rows(rows, headers, tg)
        if not own:
            continue
        corner = [min(region[0], tb[0]), max(region[3], tb[3])]
        if len(own) == len(data_i):
            return _TableCut(ids=[title.id] + sorted(grid) + [t.id for t in cells], corner=corner)
        # cut the alignment's rows: their cells and one rule each (the one along
        # the row's bottom edge, else its top, which the border below then
        # takes over), and close the rows below up by the height removed
        drop = [bands[data_i[k]] for k in own]
        gone: List[str] = []
        for lo, hi in drop:
            gone += [t.id for t in band_cells[bands.index((lo, hi))]]
            for edge in (lo, hi):
                rule = [lid for lid, bb in boxes.items() if _is_rule(ents[lid], bb, True, span_x)
                        and abs(bb[1] - edge) <= RULE_TOL_IN and lid not in gone]
                if rule:
                    gone += rule
                    break

        def shift(y: float) -> float:
            return sum(hi - lo for lo, hi in drop if y <= lo + RULE_TOL_IN)

        for lid in grid:
            e = ents[lid]
            if lid in gone:
                continue
            if isinstance(e, Line):
                e.start, e.end = _shifted(e.start, shift(e.start[1])), _shifted(e.end, shift(e.end[1]))
            elif isinstance(e, Polyline):
                e.vertices = [_shifted(v, shift(v[1])) for v in e.vertices]
        for t in cells:
            if t.id not in gone:
                t.position = _shifted(t.position, shift(t.position[1]))
        closed = sum(hi - lo for lo, hi in drop)
        return _TableCut(ids=gone, rows=[f"{title.id}:{data_i[k]}" for k in own], corner=corner,
                         kept=[region[0], region[1] + closed, region[2], max(region[3], tb[3])])
    return _TableCut()


def _leaders(ents: Dict[str, object], removed_quads: List[list], unit: float) -> List[str]:
    out = []
    for e in ents.values():
        ends = _ends(e)
        if not ends or _length(e) > LEADER_MAX_IN * unit:
            continue
        if any(_dist_to_poly(p, q) <= LEADER_REACH_IN * unit for p in ends for q in removed_quads):
            out.append(e.id)
    return out


def _strip_space(ents: Dict[str, object], doc: Document, tg: _Targets, name: str,
                 quad_of, own_anchor: bool, linework: bool = False) -> Dict[str, List[str]]:
    """Remove the alignment's annotation from one space (and, with ``linework``,
    its drawn centerline); returns the ids by kind."""
    gone: Dict[str, List[str]] = {}
    if own_anchor:  # stationing and labels anchored to it in the base
        gone["anchored"] = [e.id for e in ents.values()
                            if getattr(e, "anchor", None) and e.anchor.get("alignment") == name
                            and e.anchor.get("placed_by") in ANCHOR_PRODUCERS
                            and (linework or e.anchor.get("placed_by") != "draw_alignment")]
    quads = {e.id: quad_of(e) for e in ents.values() if isinstance(e, Text)}
    taken = set(gone.get("anchored", []))

    def fresh(ids):
        out = [i for i in ids if i not in taken]
        taken.update(out)
        return out

    gone["curve_points"] = fresh(i for i, q in quads.items() if _is_point_label(ents[i], q, tg))
    gone["bearings"] = fresh(i for i, q in quads.items()
                             if _is_bearing(ents[i], q, tg) or _is_length(ents[i], q, tg))
    gone["stations"] = fresh(i for i, q in quads.items() if _is_station_number(ents[i], q, tg))
    gone["ticks"] = fresh(_ticks(ents, tg))
    bubbles, bubble_quads = _bubbles(ents, doc, tg, quad_of)
    gone["bubbles"] = fresh(bubbles)
    cut = _table_cut(ents, doc, tg) if tg.unit == 1.0 else _TableCut()
    table, corner = cut.ids, cut.corner
    if tg.unit == 1.0 and not table and not cut.rows:
        table = _curve_data_block(ents, doc, tg)
        if table:
            bb = None
            for i in table:
                bb = geo.bbox_union(bb, geo.bbox_of_points(quads[i]))
            corner = [bb[0], bb[3]]
    gone["table"] = fresh(table)
    gone["table_rows"] = list(cut.rows)
    removed_quads = [quads[i] for k in ("curve_points", "bearings", "stations") for i in gone[k]]
    removed_quads += bubble_quads
    taken = {i for ids in gone.values() for i in ids}
    gone["leaders"] = [i for i in _leaders({k: v for k, v in ents.items() if k not in taken},
                                           removed_quads, tg.unit)]
    for ids in gone.values():
        for i in ids:
            ents.pop(i, None)
    if corner is not None:
        gone["_table_corner"] = corner  # type: ignore[assignment]
    if cut.kept is not None:
        gone["_table_kept"] = cut.kept  # type: ignore[assignment]
    return {k: v for k, v in gone.items() if v}


def geo_circle_quad(c: Circle) -> List[List[float]]:
    return _square(c.center, float(c.radius))


def strip_alignment(sheet_doc: Document, bases: Dict[str, Document], design_file: str,
                    align: Alignment, truth_labels: Sequence[dict],
                    linework: bool = False) -> dict:
    """Remove ``align``'s own real annotation from the sheet file and the base
    files (in place), and with ``linework`` its drawn centerline too; returns
    what went, by file and kind, the top-left corner of the curve table it
    was tabulated in (``table_corner``), and that table's box when it stays
    for the other lines' rows (``table_kept``, else None)."""
    sheet = _only_sheet(sheet_doc)
    vp = sheet.viewports[0]
    t = vp.transform()
    fpi = float(vp.feet_per_inch)
    report: Dict[str, dict] = {}
    corner = None
    # the sheet's other lines, whose rows of a shared curve table stay
    others = [a for base in bases.values() for a in base.design.alignments.values()
              if a.name != align.name]
    # model space of every base: model units, one paper inch = fpi feet
    tg_model = _targets(align, truth_labels, lambda p: list(p), fpi, others)
    for fname, base in bases.items():
        got = _strip_space(base.model_entities, base, tg_model, align.name,
                           lambda e, b=base: _quad(e, b), own_anchor=(fname == design_file),
                           linework=linework)
        if got:
            report[fname] = got
    # the sheet: paper inches
    tg_paper = _targets(align, truth_labels, lambda p: list(t.to_paper(p)), 1.0, others)
    got = _strip_space(sheet.entities, sheet_doc, tg_paper, align.name,
                       lambda e: _quad(e, sheet_doc), own_anchor=False)
    corner = got.pop("_table_corner", None)
    kept = got.pop("_table_kept", None)
    if got:
        report["sheet"] = got
    return {"removed": report, "table_corner": corner, "table_kept": kept}


# ===================================================================== clear space


class _Grid:
    """Occupancy of a sheet on a ``GRID_IN`` lattice of paper points."""

    def __init__(self, width_in: float, height_in: float):
        self.nx = int(math.ceil(width_in / GRID_IN)) + 1
        self.ny = int(math.ceil(height_in / GRID_IN)) + 1
        self.a = np.zeros((self.ny, self.nx), dtype=bool)

    def _cell(self, p):
        return int(round(p[1] / GRID_IN)), int(round(p[0] / GRID_IN))

    def points(self, pts, clip=None):
        for p in pts:
            if clip is not None and not geo.bbox_contains(clip, (p[0], p[1], p[0], p[1])):
                continue
            iy, ix = self._cell(p)
            if 0 <= iy < self.ny and 0 <= ix < self.nx:
                self.a[iy, ix] = True

    def path(self, pts, clip=None):
        out = []
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(geo.distance(a, b) / (GRID_IN / 2.0)))
            out += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n]
                    for k in range(n + 1)]
        self.points(out or pts, clip)

    def fill(self, poly, clip=None):
        bb = geo.bbox_of_points(poly)
        if clip is not None:
            bb = (max(bb[0], clip[0]), max(bb[1], clip[1]), min(bb[2], clip[2]), min(bb[3], clip[3]))
            if bb[0] > bb[2] or bb[1] > bb[3]:
                return
        x0, x1 = max(0, int(bb[0] / GRID_IN)), min(self.nx - 1, int(math.ceil(bb[2] / GRID_IN)))
        y0, y1 = max(0, int(bb[1] / GRID_IN)), min(self.ny - 1, int(math.ceil(bb[3] / GRID_IN)))
        if x1 < x0 or y1 < y0:
            return
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) * GRID_IN, np.arange(y0, y1 + 1) * GRID_IN)
        inside = _MplPath(poly).contains_points(np.column_stack([xs.ravel(), ys.ravel()]),
                                                radius=GRID_IN)
        self.a[y0:y1 + 1, x0:x1 + 1] |= inside.reshape(xs.shape)
        self.path(list(poly) + [poly[0]], clip)

    def clear_spots(self, w: float, h: float, inside) -> np.ndarray:
        """Boolean map of lattice points (as top-left corners) where a w x h
        rect is clear and lies inside ``inside``."""
        cw, ch = int(math.ceil(w / GRID_IN)), int(math.ceil(h / GRID_IN))
        s = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int64)
        s[1:, 1:] = np.cumsum(np.cumsum(self.a, axis=0), axis=1)
        ok = np.zeros_like(self.a)
        if ch >= self.ny or cw >= self.nx:
            return ok
        # rect spans rows iy-ch..iy (top-left at row iy, y up), cols ix..ix+cw
        top = np.arange(ch, self.ny)[:, None]
        left = np.arange(0, self.nx - cw)[None, :]
        cnt = (s[top + 1, left + cw + 1] - s[top - ch, left + cw + 1]
               - s[top + 1, left] + s[top - ch, left])
        ok[ch:, :self.nx - cw] = cnt == 0
        ys, xs = np.mgrid[0:self.ny, 0:self.nx]
        xin = (xs * GRID_IN >= inside[0]) & (xs * GRID_IN + w <= inside[2])
        yin = (ys * GRID_IN <= inside[3]) & (ys * GRID_IN - h >= inside[1])
        return ok & xin & yin


def _mark(grid: _Grid, prim, doc, to=lambda p: p, scale: float = 1.0, twist: float = 0.0,
          clip=None):
    """Mark one expanded primitive, mapped to paper by ``to``."""
    if isinstance(prim, Text):
        if prim.content:
            grid.fill(_quad(prim, doc, scale, to, twist), clip)
    elif isinstance(prim, Line):
        grid.path([to(prim.start), to(prim.end)], clip)
    elif isinstance(prim, Polyline):
        pts = []
        verts = list(prim.vertices) + ([prim.vertices[0]] if prim.closed and prim.vertices else [])
        bulges = prim.bulges or []
        for i, (a, b) in enumerate(zip(verts, verts[1:])):
            bulge = bulges[i] if i < len(bulges) else 0.0
            pts += geo.bulge_points(a, b, bulge) if bulge else [list(a), list(b)]
        grid.path([to(p) for p in pts], clip)
    elif isinstance(prim, (Arc, Circle)):
        s, e = ((prim.start_angle_deg, prim.end_angle_deg) if isinstance(prim, Arc)
                else (0.0, 360.0))
        s, e = geo.arc_sweep(s, e) if isinstance(prim, Arc) else (s, e)
        n = max(8, int(abs(e - s) / 3.0))
        grid.path([to(geo.arc_point(prim.center, prim.radius, s + (e - s) * k / n))
                   for k in range(n + 1)], clip)
    elif isinstance(prim, Hatch):
        for loop in prim.loops:
            pts = [to(p) for p in loop_points(loop)]
            if len(pts) >= 3:
                grid.fill(pts, clip)
    elif isinstance(prim, Point):
        grid.points([to(prim.position)], clip)
    else:
        bb = prim.bbox(doc)
        if bb:
            corners = [to(p) for p in ((bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3]))]
            grid.fill(corners, clip)


def occupancy(doc: Document, sheet_name: str) -> _Grid:
    """Everything a sheet shows: its border, title block and entities, and the
    model (its own and its references') through each viewport."""
    sheet = doc.sheet_by_ref(sheet_name)
    grid = _Grid(sheet.width_in, sheet.height_in)
    _key, prims = space_primitives(doc, sheet.id)
    for p in prims:
        _mark(grid, p, doc)
    model = expand_entities(doc, list(doc.model_entities.values()))
    groups = [(doc, model)] + [(base, prims) for _ref, base, prims in reference_groups(doc, "model")]
    for vp in sheet.viewports:
        t = vp.transform()
        rect = tuple(vp.paper_bbox())
        fpi = float(vp.feet_per_inch)
        for owner, prims in groups:
            for p in prims:
                _mark(grid, p, owner, to=lambda q, t=t: list(t.to_paper(q)), scale=1.0 / fpi,
                      twist=float(vp.rotation_deg), clip=rect)
    return grid


def table_spot(grid: _Grid, usable, w: float, h: float, prefer: Sequence[float]) -> Optional[List[float]]:
    """Top-left corner of the clear w x h spot (with its margin) nearest ``prefer``."""
    m = TABLE_MARGIN_IN
    ok = grid.clear_spots(w + 2 * m, h + 2 * m, usable)
    ys, xs = np.nonzero(ok)
    if not len(xs):
        return None
    cx, cy = xs * GRID_IN + m, ys * GRID_IN - m  # the table's own corner
    d = (cx - prefer[0]) ** 2 + (cy - prefer[1]) ** 2
    k = int(np.argmin(d))
    return [round(float(cx[k]), 2), round(float(cy[k]), 2)]


# ===================================================================== label poses


def _options(default_side: str, other_side: str, offsets: Sequence[float]) -> List[Tuple[str, float]]:
    out = []
    for off in offsets:
        for side in (default_side, other_side):
            out.append((side, off))
    return out


def choose_poses(task: Task) -> dict:
    """Where each of the alignment's labels goes on the real sheet: the spec's
    pose unless it lands on the sheet's own work (its text, tables and
    blocks, the base drawings' text) or on a label already placed, then the
    other side of the line, then further off -- a drafter's moves, which the
    rubric allows (side and offset are not graded; legibility is).  Station
    numbers come from one stationing command and move as a set."""
    from roaddraft.design.anchors import parse_anchor, resolve_anchor
    from roaddraft.design.labels import compile_label, stationing_plan
    from roaddraft.verify.context import Context, rect_contains
    from roaddraft.verify.legibility import (
        OVERLAP_EPS_IN, overlap_depth, reference_items, sheet_items, text_quad,
    )
    D = task.brief.deliverable
    spec = DRAFTING_SPEC_V1
    session = _draft(task, ["layers"])  # the stripped sheet: none of the alignment's labels
    ctx = Context.build(session.doc, task.truth, spec)
    sv = ctx.sheets[0]
    view = sv.views[0]
    context = [it.quad for it in sheet_items(ctx, sv) + reference_items(ctx, sv)]
    fpi = float(D["feet_per_inch"])
    vr = float(D.get("view_rotation") or 0.0)
    twist = float(view.vp.rotation_deg)
    h_in = float(spec["text"]["label_height_in"])
    align = Alignment.from_dict(task.brief.design["alignments"][task.brief.alignment_name])
    placed: List[list] = []

    def quad(ls) -> list:
        return text_quad(view.transform.to_paper(ls.position), ls.content, h_in,
                         ls.rotation_deg + twist, ls.halign, ls.valign)

    def bubble(ls) -> list:
        c = view.transform.to_paper(ls.position)
        r = float(spec["labels"]["mc"]["bubble"]["radius_text_heights"]) * h_in
        return [[c[0] - r, c[1] - r], [c[0] + r, c[1] - r], [c[0] + r, c[1] + r], [c[0] - r, c[1] + r]]

    def cost(q) -> int:
        c = sum(1 for o in context + placed if overlap_depth(q, o) > OVERLAP_EPS_IN)
        if view.window is None or not all(rect_contains(view.window, v) for v in q):
            c += OUT_OF_VIEW_COST
        return c

    poses: dict = {"points": {}, "bearings": {}, "callouts": {}}
    best = None
    for side in ("below", "above"):
        plan = stationing_plan(align, interval=float(D["stationing_interval_ft"]),
                               tick_half=float(D["tick_half_len_ft"]),
                               label_offset=float(D["label_offset_ft"]),
                               lettering=D.get("station_lettering", "caltrans"),
                               station_side=side,
                               point_offset=float(D["point_label_offset_ft"]), view_rotation=vr)
        qs = [quad(l) for l in plan.labels() if l.kind == "station"]
        c = sum(cost(q) for q in qs)
        if best is None or c < best[0]:
            best = (c, side, qs, plan)
    poses["station_side"] = best[1]
    placed += best[2]

    def pick(ap, kind, content, options, footprint) -> Tuple[str, float, list]:
        scored = []
        for side, off in options:
            ls = compile_label(align, ap, kind, side=side, label_offset=off * fpi,
                               content=content, view_rotation=vr)
            q = footprint(ls)
            c = cost(q)
            if c == 0:
                return side, off, q
            scored.append((c, side, off, q))
        c, side, off, q = min(scored, key=lambda x: x[0])
        return side, off, q

    pp = spec["labels"]["pc_pt"]
    for l in best[3].labels():
        if l.kind not in ("pc", "pt", "pcc", "prc"):
            continue
        ap = resolve_anchor(align, parse_anchor(l.ref))
        other = "right" if pp["side"] == "left" else "left"
        side, off, q = pick(ap, l.kind, l.content, _options(pp["side"], other, POINT_OFFSETS_IN),
                            quad)
        poses["points"][l.ref] = {"kind": l.kind, "content": l.content, "side": side,
                                  "label_offset_ft": round(off * fpi, 2)}
        placed.append(q)
    b = spec["labels"]["bearing"]
    for n in range(1, len(align.tangents()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"T-{n}"))
        other = "below" if b["side"] == "above" else "above"
        side, off, q = pick(ap, "bearing", None, _options(b["side"], other, BEARING_OFFSETS_IN),
                            quad)
        poses["bearings"][f"T-{n}"] = {"side": side, "label_offset_ft": round(off * fpi, 2)}
        placed.append(q)
    mc = spec["labels"]["mc"]
    for n in range(1, len(align.curves()) + 1):
        ap = resolve_anchor(align, parse_anchor(f"MC-{n}"))
        other = "left" if mc["side"] == "right" else "right"
        side, off, q = pick(ap, "mc", None, _options(mc["side"], other, MC_OFFSETS_IN), bubble)
        poses["callouts"][f"MC-{n}"] = {"side": side, "label_offset_ft": round(off * fpi, 2)}
        placed.append(q)
    return poses


# ===================================================================== tasks


def _session(task: Task):
    from roaddraft.tasks.reference import session_for_task
    return session_for_task(task)


def _draft(task: Task, phases: Iterable[str]):
    from roaddraft.tasks.reference import phase_commands
    session = _session(task)
    for name, params in phase_commands(task, list(phases)):
        result = session.execute(name, params)
        if not result["ok"]:
            raise ValueError(f"drafting {name} on {task.brief.deliverable['source']['sheet']}: "
                             f"{result['error']['message']}")
    return session


def _notes_through_text(task: Task) -> List[int]:
    """Indexes of the task's construction callouts (``D["callouts"]``) that the
    reference cannot place legibly on the stripped sheet: a leader through
    the sheet's own text, or a note on another item.  Of two new notes on each
    other, the later one goes."""
    from roaddraft.tasks.reference import phase_commands
    from roaddraft.verify import verify
    session = _session(task)
    made: Dict[str, int] = {}
    for n, (name, params) in enumerate(phase_commands(task, ["notes"])):
        result = session.execute(name, params)
        if not result["ok"]:
            raise ValueError(f"placing note {n + 1} on "
                             f"{task.brief.deliverable['source']['sheet']}: "
                             f"{result['error']['message']}")
        made[result["created"][-1]] = n  # the callout's text is created last
    bad = set()
    for finding in verify(session.doc, task.truth).check("D1-08").findings:
        mine = sorted(made[i] for i in finding.entity_ids if i in made)
        if mine:
            bad.add(mine[-1])
    return sorted(bad)


def _project(src: RealSheet, sheet) -> dict:
    tb = dict(sheet.title_block_fields or {})
    name = src.project or tb.get("project") or tb.get("project_name") or src.id
    return {"name": name, "agency": src.agency_name, "source": src.id, "family": src.family,
            "designed_by": "", "drawn_by": "AGENT", "checked_by": "", "date": ""}


def _deliverable(src: RealSheet, sheet, vp, align: Alignment, ref_name: str, design_file: str,
                 ttype: TaskType, others: List[str]) -> dict:
    spec = DRAFTING_SPEC_V1
    fpi = float(vp.feet_per_inch)
    r2 = lambda v: round(float(v), 2)
    return {
        "task_type": ttype.name,
        "sheets": [{
            "name": sheet.name, "size": sheet.size,
            "viewport": {"center_paper": [r2(v) for v in vp.center_paper], "width_in": r2(vp.width_in),
                         "height_in": r2(vp.height_in),
                         "model_center": [r2(v) for v in vp.model_center],
                         "feet_per_inch": fpi, "rotation_deg": float(vp.rotation_deg)},
            "station_range": [float(align.begin_station), float(align.end_station)],
            "curves": list(range(1, len(align.curves()) + 1)),
            "curve_table_position": [0.0, 0.0],
            "title_block_fields": dict(sheet.title_block_fields or {}),
            "matches": []}],
        "feet_per_inch": fpi,
        "pavement": {},
        "width_dimensions": [],
        "dims_layer": spec["layers"]["dims"],
        "stationing_interval_ft": spec["stationing"]["interval_ft"],
        "station_format": spec["stationing"]["format"],
        "required_label_kinds": ["station", "pc", "pt", "bearing", "mc", "curve_table"],
        "curve_table_columns": list(spec["curve_table"]["columns"]),
        "text_heights": {"model_label_ft": r2(spec["text"]["label_height_in"] * fpi),
                         "sheet_table_in": spec["text"]["table_height_in"]},
        "station_lettering": spec["stationing"]["format"],
        "station_label_side": spec["stationing"]["label_side"],
        "tick_half_len_ft": r2(spec["stationing"]["tick_half_len_in"] * fpi),
        "label_offset_ft": r2(spec["stationing"]["label_offset_in"] * fpi),
        "point_label_offset_ft": r2(spec["labels"]["pc_pt"]["label_offset_in"] * fpi),
        "bearing_label_offset_ft": r2(spec["labels"]["bearing"]["label_offset_in"] * fpi),
        "mc_label_offset_ft": r2(spec["labels"]["mc"]["label_offset_in"] * fpi),
        "north_arrow": False,
        # the viewport's twist: model labels read upright on the sheet, not in the model
        "view_rotation": float(vp.rotation_deg),
        # the design lives in a base file the sheet references: labels go through it
        "design_reference": ref_name,
        "design_file": design_file,
        "source": {"agency": src.agency, "agency_name": src.agency_name, "sheet_id": src.id,
                   "sheet": sheet.name, "family": src.family, "sheet_file": src.sheet_file,
                   "folder": str(src.folder.relative_to(REPO)), "other_alignments": others},
    }


def _brief(src, ttype, project, design, D) -> TaskBrief:
    payload = {"generator_version": REAL_GENERATOR_VERSION, "spec_hash": spec_hash(),
               "project": project, "design": design, "deliverable": D}
    task_id = compute_task_id(0, "D1", payload)
    brief = TaskBrief(task_id=task_id, seed=0, level="D1",
                      generator_version=REAL_GENERATOR_VERSION, spec_version=SPEC_VERSION,
                      spec_hash=spec_hash(), project=project, design=design, deliverable=D,
                      drafting_spec=spec_subset(), instructions="", task_type=ttype.name, sheets=1)
    brief.prompts = render_prompts(brief)
    brief.instructions = brief.prompts["explicit"]
    return brief


def _title(sheet, template: str) -> List[Tuple[str, str, str]]:
    """``(key, label, value)`` of the published fields a drafter fills on this border."""
    fields = sheet.title_block_fields or {}
    return [(k, label, str(fields[k])) for k, label in TITLE_FIELDS.get(template, ())
            if str(fields.get(k) or "").strip()]


def _attachable(doc: Document) -> Optional[str]:
    """Why re-attaching this sheet file's base files is more than attaching them."""
    refs = list(doc.references.values())
    if not refs:
        return "the sheet file references nothing"
    for r in refs:
        if (r.clip is not None or r.masks or r.levels_off or r.space != "model"
                or r.model != "model" or not r.visible or geo.distance(r.offset, [0.0, 0.0]) > 1e-9
                or abs(r.rotation_deg) > 1e-9 or abs(r.scale - 1.0) > 1e-9):
            return f"{r.name} is attached clipped, masked, moved or with levels off"
    return None


def _block_box(doc: Document, block: str, scale: float, rotation: float):
    """The footprint of a block insertion relative to its insertion point."""
    probe = BlockRef(id="probe", block_name=block, position=[0.0, 0.0], scale=scale,
                     rotation_deg=rotation)
    return probe.bbox(doc)


def build_real_task(sheet_id: str, alignment: str, type_name: str) -> Task:
    """The ``type_name`` task on real sheet ``sheet_id`` about ``alignment`` (for
    the sheet's own jobs, the alignment the truth is drawn from); see the module
    docstring and ``START_KIND``.  Raises ValueError when the pairing does not
    make one."""
    src = real_sheet(sheet_id)
    ttype = task_type(type_name)
    if ttype.name not in REAL_TASK_TYPES and ttype.name not in REAL_JOB_TYPES:
        raise ValueError(f"{type_name} is not a real-sheet task type; types: "
                         f"{', '.join(list(REAL_TASK_TYPES) + list(REAL_JOB_TYPES))}")
    kind = START_KIND[ttype.name]
    sheet_doc = _load(src.folder / src.sheet_file)
    sheet = _only_sheet(sheet_doc)
    if len(sheet.viewports) != 1:
        raise ValueError(f"{src.id}: {len(sheet.viewports)} viewports; one is supported")
    vp = sheet.viewports[0]
    found = [(ref, base, al) for ref, base, al, pl in reference_alignments(sheet_doc)
             if al.name == alignment and pl.is_identity]
    if not found:
        raise ValueError(f"{src.id}: no alignment {alignment!r} through a reference at identity")
    ref, base, align = found[0]
    why = (None if ttype.name in ANY_LINE_TYPES else usable_alignment(align)) \
        or type_fits(align, ttype)
    if why:
        raise ValueError(f"{src.id} {alignment}: {why}")
    notes: list = []
    if "notes" in ttype.asks:  # the construction callouts task, or a whole job
        from roaddraft.tasks.real_callouts import MIN_NOTES, published_callouts, task_notes
        notes = task_notes(published_callouts(sheet_doc, sheet))
        if len(notes) < MIN_NOTES:
            raise ValueError(f"{src.id}: {len(notes)} construction callouts point at a referenced "
                             f"line inside the plan view (fewer than {MIN_NOTES})")
    template = getattr(sheet, "title_block_template", None) or "standard"
    title = _title(sheet, template)
    if "title" in ttype.asks and not title:
        raise ValueError(f"{src.id}: its border ({template}) has no title block fields to fill")
    if kind == "attach":
        why = _attachable(sheet_doc)
        if why:
            raise ValueError(f"{src.id}: {why}")
    design_file = Path(ref.path).name
    others = sorted({al.name for _r, _b, al, _p in reference_alignments(sheet_doc)} - {align.name})
    design = {"alignments": {align.name: align.to_dict()},
              "profiles": {name: p.to_dict() for name, p in base.design.profiles.items()
                           if p.alignment == align.name}}
    if notes:  # every line a note points at joins the design the truth is drawn from
        lines = {al.name: al for _r, _b, al, _p in reference_alignments(sheet_doc)}
        for c in notes:
            design["alignments"].setdefault(c.target[1], lines[c.target[1]].to_dict())
    project = _project(src, sheet)
    D = _deliverable(src, sheet, vp, align, ref.name, design_file, ttype, others)
    D["start"] = kind
    if notes:
        from roaddraft.tasks.real_callouts import note_rows
        D["callouts"] = note_rows(notes, {n: Alignment.from_dict(a)
                                          for n, a in design["alignments"].items()})
    D["base_files"] = [Path(r.path).name for r in sheet_doc.references.values()]
    sh = D["sheets"][0]
    sh["template"] = template
    if "sheet" in ttype.asks:
        sh["twist_deg"] = float(vp.rotation_deg)  # the layout reads as published
    if "title" in ttype.asks:
        sh["title_block_fields"] = {k: v for k, _label, v in title}
        sh["title_labels"] = {k: label for k, label, _v in title}
        sh["required_title_fields"] = [k for k, _label, _v in title]
        sh["title_stated"] = {"explicit": [k for k, _l, _v in title],
                              "vague": [k for k in TITLE_VAGUE.get(template, ())
                                        if k in sh["title_block_fields"]]}
    if kind == "attach":
        D["references"] = [{"file": Path(r.path).name, "name": r.name, "space": r.space}
                           for r in sheet_doc.references.values()]
    brief = _brief(src, ttype, project, design, D)
    truth = compute_ground_truth(brief)

    # -- the shipped copies: the base files, and the sheet file cut for the task
    bases = {name: _load(src.folder / name) for name in src.files if name != src.sheet_file}
    work = _load(src.folder / src.sheet_file)
    stripped = {"removed": {}, "table_corner": None, "table_kept": None}
    if kind in ("letter", "draw", "setup", "blank", "scratch"):
        stripped = strip_alignment(work, bases, design_file, align, truth.labels,
                                   linework=(kind == "draw"))
    work_sheet = work.sheet_by_ref(sheet.name)
    if kind == "notes":  # the chosen callouts go: note, leader and arrowhead
        gone = [i for c in notes for i in c.ids]
        for i in gone:
            work_sheet.entities.pop(i, None)
        stripped["removed"]["sheet"] = {"notes": gone}
    if kind in ("setup", "blank", "scratch"):
        work_sheet.entities.clear()  # the finished sheet holds only the drafter's work
    if kind in ("blank", "scratch") or kind == "title":
        for k, _label, _v in title:
            work_sheet.title_block_fields.pop(k, None)
    work.meta.update(task_id=brief.task_id, spec_version=SPEC_VERSION)

    def files_for(doc_name: Optional[str]) -> dict:
        return {name: doc.to_dict() for name, doc in bases.items() if name != doc_name}

    files = files_for(None)
    if kind == "notes":
        # a published note whose leader the real sheet ran through its own lettering, or
        # that lands on another note, stays on the sheet: the task asks only for notes
        # the reference places legibly
        for tsh in truth.sheets:  # legibility judges new work against what is handed over
            tsh["given_entities"] = sorted(set(work_sheet.entities) | set(work.model_entities))
        bad = _notes_through_text(Task(brief=brief, truth=truth, baseline=work.to_dict(),
                                       files=files))
        if bad:
            from roaddraft.tasks.real_callouts import MIN_NOTES, note_rows
            back = [c for i, c in enumerate(notes) if i in bad]
            notes = [c for i, c in enumerate(notes) if i not in bad]
            if len(notes) < MIN_NOTES:
                raise ValueError(f"{src.id}: {len(notes)} construction callouts can be re-placed "
                                 f"clear of the sheet's lettering (fewer than {MIN_NOTES})")
            published = _only_sheet(_load(src.folder / src.sheet_file))
            for c in back:
                for i in c.ids:
                    work_sheet.entities[i] = published.entities[i]
            stripped["removed"]["sheet"] = {"notes": [i for c in notes for i in c.ids]}
            D["callouts"] = note_rows(notes, {n: Alignment.from_dict(a)
                                              for n, a in design["alignments"].items()})
            brief = _brief(src, ttype, project, design, D)
            truth = compute_ground_truth(brief)
            work.meta.update(task_id=brief.task_id)
    lettered = kind in ("letter", "setup", "blank", "scratch")
    if lettered:
        # -- where its labels go: clear of the sheet's own work
        D["label_poses"] = choose_poses(Task(brief=brief, truth=truth,
                                             baseline=work.to_dict(), files=files))
        brief = _brief(src, ttype, project, design, D)
        truth = compute_ground_truth(brief)

    # -- the curve table's spot and the north arrow's: clear of everything the finished
    # sheet shows
    table_wanted = align.curves() and kind in ("letter", "blank", "scratch")
    north_wanted = "north" in ttype.asks
    if table_wanted or north_wanted:
        scratch = Task(brief=brief, truth=truth, baseline=work.to_dict(), files=files)
        session = _draft(scratch, ["layers", "stationing", "bearings", "callouts"])
        grid = occupancy(session.doc, sheet.name)
        usable = tuple(sheet.usable_area())
        if table_wanted:
            from roaddraft.tasks.generator import _table_size
            w, h = _table_size(align, sh["curves"], D["curve_table_columns"],
                               D["text_heights"]["sheet_table_in"])
            # where the published table was; below it when it stays on the sheet
            # for the other lines' rows (a blank sheet has lost it with the rest)
            kept = stripped["table_kept"] if kind == "letter" else None
            if kept:
                prefer = [kept[0], kept[1] - TABLE_MARGIN_IN]
            else:
                prefer = stripped["table_corner"] or [usable[2] - w - 0.25, usable[1] + h + 0.25]
            spot = table_spot(grid, usable, w, h, prefer)
            if spot is None and "table" in ttype.asks:
                raise ValueError(f"{src.id} {alignment}: no clear space for the curve table")
            # a sheet too full for the table starts without one when the task is not the table
            D["table_given"] = spot is not None and "table" in ttype.given
            sh["curve_table_position"] = spot or [round(v, 2) for v in prefer]
            sh["curve_table_replaces"] = (bool(stripped["table_corner"]) and spot is not None
                                          and not kept)
            if spot is not None:
                grid.fill([[spot[0], spot[1] - h], [spot[0] + w, spot[1] - h],
                           [spot[0] + w, spot[1]], [spot[0], spot[1]]])
        if north_wanted:
            na = DRAFTING_SPEC_V1["sheet"]["north_arrow"]
            scale = round(NORTH_SCALE_PER_IN * float(sheet.height_in), 3)
            turn = round(float(vp.rotation_deg), 2)
            bb = _block_box(work, na["block"], scale, turn)
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            corner = table_spot(grid, usable, w, h, [usable[2] - w - 0.5, usable[3] - 0.5])
            if corner is None:
                raise ValueError(f"{src.id} {alignment}: no clear space for the north arrow")
            # the block's insertion point from the clear rect's top-left corner
            sh["north_arrow"] = {"position": [round(corner[0] - bb[0], 3),
                                              round(corner[1] - h - bb[1], 3)],
                                 "scale": scale, "rotation_deg": turn}
        brief = _brief(src, ttype, project, design, D)
        truth = compute_ground_truth(brief)
        work.meta.update(task_id=brief.task_id)

    # -- the starting document
    if kind == "draw":
        doc = bases[design_file]
        doc.meta.update(task_id=brief.task_id, spec_version=SPEC_VERSION)
        files = files_for(design_file)
    else:
        doc = work
        if kind == "attach":
            doc.references.clear()
        if kind in ("setup", "scratch"):
            del doc.sheets[work_sheet.id]
    task = Task(brief=brief, truth=truth, baseline=doc.to_dict(), files=files)
    if kind == "letter":
        drafted = ["layers"] + [p for p in ANNOTATION_PHASES if p in ttype.given
                                and (p != "table" or D.get("table_given"))]
    elif kind == "setup":
        drafted = ["layers", "stationing", "bearings", "callouts"]
    elif kind in ("draw", "blank", "scratch", "notes"):
        drafted = ["layers"]
    else:  # attach, title: the published sheet file as it is
        drafted = []
    if drafted:
        session = _draft(task, drafted)
        task.baseline = session.doc.to_dict()
        start = session.doc
    else:
        start = Document.from_dict(task.baseline)
    start_sheet = start.sheet_by_ref(sheet.name)
    given = sorted((set(start_sheet.entities) if start_sheet is not None else set())
                   | set(start.model_entities))
    for tsh in truth.sheets:
        tsh["given_entities"] = given
        tsh["stripped"] = stripped["removed"]
    if notes and kind != "notes":
        # a whole job: a note the reference cannot place legibly once it has lettered the
        # sheet itself (on its own labels, the table or the north arrow, or a leader through
        # them) leaves the task, as the callouts task leaves such a note on the sheet; the
        # sheet starts blank here, so nothing of it is handed over
        bad = _notes_in_the_way(task)
        if bad:
            from roaddraft.tasks.real_callouts import MIN_NOTES, note_rows
            notes = [c for i, c in enumerate(notes) if i not in bad]
            if len(notes) < MIN_NOTES:
                raise ValueError(f"{src.id} {alignment}: {len(notes)} construction callouts can be "
                                 f"placed clear of the sheet's own lettering (fewer than "
                                 f"{MIN_NOTES})")
            D["callouts"] = note_rows(notes, {n: Alignment.from_dict(a)
                                              for n, a in design["alignments"].items()})
            brief = _brief(src, ttype, project, design, D)
            truth = compute_ground_truth(brief)
            for tsh in truth.sheets:
                tsh["given_entities"] = given
                tsh["stripped"] = stripped["removed"]
            start = Document.from_dict(task.baseline)
            start.meta.update(task_id=brief.task_id)
            task = Task(brief=brief, truth=truth, baseline=start.to_dict(), files=task.files)
    return task


def _notes_in_the_way(task: Task) -> List[int]:
    """Indexes of a whole job's construction callouts (``D["callouts"]``) that
    the reference cannot place legibly after drafting the rest of the sheet:
    a note on its labels, table or north arrow, or a leader through them.  Of
    two notes on each other, the later one goes."""
    from roaddraft.tasks.reference import solution_commands
    from roaddraft.verify import verify
    session = _session(task)
    made: Dict[str, int] = {}
    for name, params in solution_commands(task):
        result = session.execute(name, params)
        if not result["ok"]:
            raise ValueError(f"drafting {name} on {task.brief.deliverable['source']['sheet']}: "
                             f"{result['error']['message']}")
        if name == "place_callout":  # only the notes phase places callouts
            made[result["created"][-1]] = len(made)  # the callout's text is created last
    bad = set()
    for finding in verify(session.doc, task.truth).check("D1-08").findings:
        mine = sorted(made[i] for i in finding.entity_ids if i in made)
        if mine:
            bad.add(mine[-1])
    return sorted(bad)


# ===================================================================== checks


def validate(task: Task) -> dict:
    """Reference solution and starting document, verified at both prompt
    levels: ``{"ok": bool, "oracle": {level: score}, "start": {level: score},
    "findings": [...]}`` (the oracle's findings when it falls short)."""
    from roaddraft.tasks.reference import reference_solution
    from roaddraft.verify import verify
    from roaddraft.tasks.prompts import LEVELS
    start = _session(task)
    finished = _session(task)
    reference_solution(task, finished)
    out = {"oracle": {}, "start": {}, "findings": []}
    for level in LEVELS:
        r = verify(finished.doc, task.truth, prompt_level=level)
        s = verify(start.doc, task.truth, prompt_level=level)
        out["oracle"][level] = r.effective_score
        out["start"][level] = s.effective_score
        if r.effective_score < 100.0 and not out["findings"]:
            out["findings"] = [f"{c.id}: {f.code} {f.note}" for c in r.checks
                               for f in c.findings][:12]
    out["ok"] = (all(v == 100.0 for v in out["oracle"].values())
                 and all(v == 0.0 for v in out["start"].values()))
    return out


def catalog(progress=None, types: Optional[Dict[str, TaskType]] = None) -> dict:
    """Build and validate every candidate (``candidates``) of ``types``: the
    tasks that verify 100 / 0, and the rest with the reason they were left
    out.  ``progress(row)`` is called after each."""
    from roaddraft.verify import VERIFIER_VERSION
    tasks, excluded = [], []
    for src, alignment, type_name in candidates(types):
        row = {"agency": src.agency, "sheet_id": src.id, "alignment": alignment,
               "type": type_name}
        try:
            task = build_real_task(src.id, alignment, type_name)
        except ValueError as why:
            row["why"] = str(why)
            excluded.append(row)
        else:
            v = validate(task)
            sheet = task.brief.deliverable["sheets"][0]
            align = Alignment.from_dict(task.brief.design["alignments"][alignment])
            row.update(task_id=task.task_id, sheet=sheet["name"],
                       per_sheet=type_name in SHEET_TYPES, start=START_KIND[type_name],
                       feet_per_inch=task.brief.deliverable["feet_per_inch"],
                       twist_deg=round(task.brief.deliverable["view_rotation"], 2),
                       tangents=len(align.tangents()), curves=len(align.curves()),
                       labels=len(task.truth.labels), ticks=len(task.truth.ticks))
            if task.truth.callouts:
                row["callouts"] = len(task.truth.callouts)
            if v["ok"]:
                tasks.append(row)
            else:
                row.update(why="the reference does not verify 100 or the start 0",
                           oracle=v["oracle"], start=v["start"], findings=v["findings"])
                excluded.append(row)
        if progress is not None:
            progress(row)
    return {"generator_version": REAL_GENERATOR_VERSION, "spec_version": SPEC_VERSION,
            "spec_hash": spec_hash(), "verifier_version": VERIFIER_VERSION,
            "tasks": tasks, "excluded": excluded}


__all__ = ["REAL_GENERATOR_VERSION", "REDRAFT_ROOT", "AGENCIES", "START_KIND", "SHEET_TYPES",
           "ANY_LINE_TYPES", "RealSheet", "real_sheets",
           "real_sheet", "usable_alignment", "type_fits", "candidates", "strip_alignment",
           "occupancy", "table_spot", "choose_poses", "build_real_task", "validate", "catalog"]
