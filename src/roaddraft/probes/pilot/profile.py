"""Pilot 6: plan and profile on one sheet.

The engine letters a plan for the model (``annotate_stationing``,
``place_label``, a viewport through ``create_viewport``), but it has no
profile view: no command draws a profile grid, a grade line or a vertical
curve label. Here the model lays out a whole plan-and-profile sheet the way
the FHWA Federal Lands offices print them (WFL ``WFL-Plan-Profile-Sheets``,
CFL ``CFL-D-Plan-and-Profile``): the plan at 1" = 50' across the top, rotated
so the centerline runs level, left to right, and stationed; under it a
profile grid at 1" = 50' horizontal and 1" = 5' vertical (10:1), the profile
grade line, and for each vertical curve the PVI station and elevation, the
curve length, the K value and, where the curve has one, the high or low
point. A station must sit at the same paper x in the plan and the profile.

What makes it hard: everything below the plan is the model's own arithmetic.
``get_design_data`` gives the PVIs and the curve table (K, high/low point),
but the grade line has to be computed from the PVIs as parabolas and mapped
to paper through a 10:1 exaggeration; the plan viewport has to be placed and
twisted so its stations land on the profile's station axis; and the profile
data has to be cut to the sheet (the design profile runs past the sheet both
ways, and on D.5 the next curve begins on the sheet while its PVI is off it).

The redraft base files carry no design profiles (``doc.design.profiles`` is
empty in every one), so each start builds the profile with ``create_profile``
from the published sheets' PVIs:

* ``p06-plan-profile-cflpnp`` -- CFL sample "Plan 1" (CL1). The published
  profile: begin 10+00 el 8189.84, PVI 11+50 el 8190.59 (150' VC, K = 69,
  crest), PVI 16+00 el 8183.06 (200' VC, K = 81, sag), PVI 22+00 el 8187.90
  (200' VC, K = 153), end 24+00 on -0.50% (8186.90). The sheet covers 10+00
  to 17+50, so two curves are on it, with a high point (11+09.51 el 8190.30)
  and a low point (16+34.95 el 8183.60). The published plan is 1" = 100';
  this sheet is laid out again at 1" = 50'.
* ``p06-plan-profile-wfl14`` -- WFL sample sheet D.5 (MAIN 01, Northeast
  Entrance Road). The profile is the whole MAIN 01 profile pieced together
  from sheets D.5 to D.10, each PVI checked against the next sheet's grade
  and the published K: begin 110+05 el 6268.77, PVIs 111+00 el 6266.87
  (150' VC, K = 500), 116+10 el 6255.14 (400', K = 308), 123+50 el 6247.73
  (400', K = 138), 131+00 el 6218.48 (500', K = 227), 146+40 el 6192.30 (800',
  K = 104), end 152+00 on +6.00%. The grid runs 107+50 to 115+00 as the
  published sheet's does: the grade begins mid-grid at 110+05, only the
  111+00 curve has its PVI on the sheet, it is a crest between -2.00% and
  -2.30% so it has no high point (a model that letters one is wrong), and the
  116+10 sag begins at 114+10, inside the grid.

How it is graded (``check``, on the saved sheet as it plots: ``plotted.plot``
reads the sheet's own entities and the sheet file's model space through every
viewport, so a profile drawn on paper and one drawn exaggerated in model space
behind a second viewport are judged alike; what was in the start is ignored).
The prompt fixes the profile grid's datum, so paper maps to station and
elevation: x = x0 + (station - S0) / 50, y = y0 + (elevation - E0) / 5.

* plan view: a 1" = 50' viewport above the grid (not overlapping it); every
  full station on the sheet inside it; the tangent level on the paper within
  0.5 deg; each full station at the profile's x within 0.05 in (2.5 ft);
  each full station lettered within 1.5 in of its point on the centerline
  ('12+00', '12', or Caltrans's ones digit '2').
* grid: a line at every full station and every 5 ft of elevation at the
  datum's positions (0.01 in), each covering 95% of the grid; the stations
  lettered under the grid and the elevations at an end of each line.
* grade line: sampled every 10 ft wherever the profile is on the grid; at
  each sample some drawn line (other than the grid) crosses the station's x
  within 0.02 in of the design elevation's y. 0.02 in is 0.10 ft at 1" = 5':
  about a plotted line width and a half, tight enough to fail a curve drawn
  as its two tangents (the smallest curve's external is 0.41 ft, 0.08 in) or
  a 1" = 10' vertical scale, loose enough for a polyline with vertices every
  25 ft (chord error under 0.01 ft) or even 50 ft (0.04 ft). On D.5 the
  111+00 curve is so flat (A = 0.30%, external 0.06 ft) that its chord is
  inside the tolerance; there the grade line is decided where the 116+10 sag
  bends the grade before 115+00 (0.13 ft off the tangent at 115+00).
* labels, near the point they label (within 2.5 in on the paper): for each
  curve whose PVI is on the grid, the PVI station and elevation (0.01 ft),
  the length (0.5 ft) and K (0.51, so 69, 69.0 and 69.02 all read right);
  the high or low point's station (0.6 ft) and elevation (0.02 ft) where the
  curve has one on the grid; where none does, no high or low point lettered.

Naive answers this fails (built by hand, see tests/test_pilot_profile.py):
the grade drawn as straight lines PVI to PVI (fails the grade line: CFL at 18
of 76 samples, D.5 at the two samples past 114+80), the same sheet with the
profile at 1" = 10' vertical (fails the grid and the grade line), the plan
turned 3 deg off level (fails the line-up), and a high point lettered on D.5
(fails the no-high-point item).
"""
from __future__ import annotations

import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core.units import format_station
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document import viewmap
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common

H_SCALE = 50.0           # feet per inch along the profile, as in the plan
V_SCALE = 5.0            # feet of elevation per inch
GRID_POS_TOL = 0.01      # in: a grid line at its datum position
GRID_COVER = 0.95        # share of the grid a grid line must span
GRADE_TOL_IN = 0.02      # in: 0.10 ft of elevation at 1" = 5'
GRADE_STEP = 10.0        # ft between grade-line samples
X_ALIGN_TOL = 0.05       # in: plan station vs profile station (2.5 ft)
LEVEL_TOL_DEG = 0.5
STATION_LABEL_REACH = 1.5
LABEL_REACH = 2.5        # in: a label belongs to the point it is within this of
TEXT_H = 0.10


# ------------------------------------------------------------ the instances


@dataclass(frozen=True)
class Job:
    id: str
    start: str
    redraft: str                    # the redraft folder, relative to Redraft/
    sheet_file: str                 # the sheet file: rebuilt as the start document
    ali_file: str                   # the alignment file: the start owns its design
    refs: Tuple[Tuple[str, str], ...]   # (name, file) attached for the plan view
    alignment: str
    profile: str
    pvis: Tuple[Tuple[float, ...], ...]
    sheet: str
    s0: float                       # profile grid: lower-left station, elevation
    e0: float
    s1: float                       # and its right and top edges
    e1: float
    x0: float = 1.0                 # paper inches of the lower-left corner
    y0: float = 1.6

    def folder(self) -> Path:
        return common.REDRAFT_ROOT / self.redraft

    def x(self, station: float) -> float:
        return self.x0 + (station - self.s0) / H_SCALE

    def y(self, elevation: float) -> float:
        return self.y0 + (elevation - self.e0) / V_SCALE

    @property
    def x1(self) -> float:
        return self.x(self.s1)

    @property
    def y1(self) -> float:
        return self.y(self.e1)

    def design(self) -> Profile:
        return Profile(self.profile, self.alignment,
                       [PVI(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in self.pvis])


CFL = Job(
    id="p06-plan-profile-cflpnp", start="p06-cflpnp",
    redraft="CFL/CFL-D-Plan-and-Profile", sheet_file="PNP(Sample).rdraft",
    ali_file="ALI(MAIN)Sample.rdraft",
    refs=(("COR", "COR(MAIN)Sample.rdraft"), ("TER", "TERSample.rdraft")),
    alignment="CL1", profile="CL1 PGL",
    pvis=((1000.0, 8189.84), (1150.0, 8190.59, 150.0), (1600.0, 8183.06, 200.0),
          (2200.0, 8187.90, 200.0), (2400.0, 8186.90)),
    sheet="Plan 1", s0=1000.0, e0=8175.0, s1=1750.0, e1=8195.0,
)

WFL = Job(
    id="p06-plan-profile-wfl14", start="p06-wfl14",
    redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p14",
    sheet_file="SamplePlan_pln_pp1.rdraft", ali_file="SamplePlan_ali.rdraft",
    refs=(("COR", "SamplePlan_cor.rdraft"), ("SUR", "SamplePlan_sur.rdraft")),
    alignment="MAIN 01", profile="MAIN 01 PGL",
    pvis=((11005.0, 6268.77), (11100.0, 6266.87, 150.0), (11610.0, 6255.14, 400.0),
          (12350.0, 6247.73, 400.0), (13100.0, 6218.48, 500.0), (14640.0, 6192.30, 800.0),
          (15200.0, 6225.90)),
    sheet="D.5", s0=10750.0, e0=6255.0, s1=11500.0, e1=6275.0,
)

JOBS = [CFL, WFL]


# ------------------------------------------------------- the start document


def build_host(out: Path, job, profile_pvis, sheet_name: str, keep_viewport: bool = False,
               strip_annotation: bool = True, description: str = "") -> Path:
    """The start: the redraft's file set copied into ``out``, with the sheet
    file rebuilt so that it OWNS the alignment (copied from the alignment
    file, with its drawn centerline) and a design profile on it, attaches the
    corridor and survey files for the plan view, and holds the agency sheet
    (border and title block from the redraft; its viewport only when
    ``keep_viewport``). The engine reads a profile only from the document
    that owns its alignment (``get_design_data`` does not see a referenced
    file's profiles), which is why the design moves into the sheet file.

    ``job`` needs ``folder()``, ``sheet_file``, ``ali_file``, ``refs``,
    ``alignment`` and ``profile``; shared with the striping pilot."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    src = job.folder()
    for p in sorted(src.glob("*.rdraft")):
        shutil.copyfile(p, out / p.name)
    published = common.document(src / job.sheet_file)
    sheet = next(s for s in published.sheets.values() if s.name == sheet_name)
    s = Session.load(out / job.ali_file, out_dir=out)
    if strip_annotation:
        drop = [e.id for e in s.doc.model_entities.values() if e.layer != "P_ALIGN"]
        if drop:
            common.ok(s.execute("delete_entities", {"ids": drop}))
    host = out / job.sheet_file
    common.save(s, host)        # so the references resolve from the host's own folder
    for name, path in job.refs:
        common.ok(s.execute("attach_reference", {"name": name, "path": path, "space": "model"}))
    fields = dict(sheet.title_block_fields)
    if description:
        fields["description"] = description
    common.ok(s.execute("create_sheet", {"name": sheet.name, "size": sheet.size,
                                         "title_block_template": sheet.title_block_template,
                                         "title_block_fields": fields}))
    if keep_viewport:
        for vp in sheet.viewports:
            common.ok(s.execute("create_viewport", {
                "sheet": sheet.name, "center_paper": list(vp.center_paper),
                "width_in": vp.width_in, "height_in": vp.height_in,
                "model_center": list(vp.model_center), "feet_per_inch": vp.feet_per_inch,
                "rotation_deg": vp.rotation_deg}))
    common.ok(s.execute("create_profile", {"name": job.profile, "alignment": job.alignment,
                                           "pvis": [list(p) for p in profile_pvis],
                                           "description": "profile grade line"}))
    common.ok(s.execute("set_annotation_scale", {"scale": 50}))
    common.ok(s.execute("set_meta", {"updates": {
        "project_name": fields.get("project", "") or published.meta.get("project_name", ""),
        "description": f"Sheet {sheet.name}: {job.alignment} and its profile {job.profile}"}}))
    return common.save(s, host)


def _register(job: Job) -> str:
    desc = f"[PLAN AND PROFILE - {format_station(job.s0)} TO {format_station(job.s1)}]"
    return common.register(job.start, job.sheet_file,
                           lambda out: build_host(out, job, job.pvis, job.sheet,
                                                  description=desc))


# --------------------------------------------------------------- reading


STATION_RE = re.compile(r"(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)")
NUMBER_RE = re.compile(r"(?<![\d+.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d+])")
_NUM = r"(\d+(?:\.\d+)?)"
#: a curve length: "150' VC", "150 FT V.C.", "L = 150'", "LVC = 150", "VC = 150'"
LENGTH_RE = re.compile(
    _NUM + r"\s*(?:'|FT\.?|FEET)?\s*(?:V\.?\s*C\b|VERT(?:ICAL)?\.?\s*CURVE)"
    r"|\b(?:L|LVC|VCL|VC|LENGTH)\s*=\s*" + _NUM, re.I)
K_RE = re.compile(r"\bK\s*=?\s*" + _NUM, re.I)
HIGH_RE = re.compile(r"\bHI(?:GH)?\.?\s*(?:PT|POINT)\b|\bH\.?\s*P\.?(?=[\s:=]|$)", re.I)
LOW_RE = re.compile(r"\bLO(?:W)?\.?\s*(?:PT|POINT)\b|\bL\.?\s*P\.?(?=[\s:=]|$)", re.I)


def stations_in(text: str) -> List[float]:
    return [int(a) * 100.0 + float(b) for a, b in STATION_RE.findall(text)]


def numbers_in(text: str) -> List[float]:
    """Plain numbers in a text, station strings left out ('8,190.59' -> 8190.59)."""
    bare = STATION_RE.sub(" ", text)
    return [float(n.replace(",", "")) for n in NUMBER_RE.findall(bare)]


def _station_word(text: str, station: float) -> bool:
    """A plan station label: '12+00', '12+00.00', '12', or the ones digit '2'
    of Caltrans lettering."""
    t = text.strip()
    if any(abs(v - station) < 0.01 for v in stations_in(t)):
        return True
    if re.fullmatch(r"\d+", t):
        n = int(t)
        whole = int(round(station / 100.0))
        return abs(station - whole * 100.0) < 0.01 and n in (whole, whole % 10)
    return False


def _sheet(session: Session, name: str):
    return next((s for s in session.doc.sheets.values() if s.name == name), None)


def _near(texts: Sequence[pl.PText], point, reach: float) -> List[pl.PText]:
    return [t for t in texts if math.dist(t.center(), point) <= reach]


def _joined(texts: Sequence[pl.PText]) -> str:
    return "\n".join(t.content for t in texts)


def _cover(intervals: List[Tuple[float, float]], lo: float, hi: float) -> float:
    """Share of [lo, hi] the union of intervals covers."""
    if hi <= lo:
        return 1.0
    clipped = sorted((max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo))
    total, cur_a, cur_b = 0.0, None, None
    for a, b in clipped:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                total += cur_b - cur_a
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        total += cur_b - cur_a
    return total / (hi - lo)


def _vertical(seg: pl.PSeg) -> bool:
    return abs(seg.a[0] - seg.b[0]) < 1e-4 and seg.length > 1e-6


def _horizontal(seg: pl.PSeg) -> bool:
    return abs(seg.a[1] - seg.b[1]) < 1e-4 and seg.length > 1e-6


def _crossings(segs: Sequence[pl.PSeg], x: float) -> List[float]:
    """The y of every segment crossing the vertical x."""
    out = []
    for s in segs:
        (ax, ay), (bx, by) = s.a, s.b
        if min(ax, bx) - 1e-9 <= x <= max(ax, bx) + 1e-9 and abs(bx - ax) > 1e-9:
            out.append(ay + (by - ay) * (x - ax) / (bx - ax))
    return out


# ------------------------------------------------------------------ check


def _full_stations(lo: float, hi: float) -> List[float]:
    first = math.ceil(lo / 100.0 - 1e-9) * 100.0
    out = []
    s = first
    while s <= hi + 1e-6:
        out.append(s)
        s += 100.0
    return out


def _plan_items(job: Job, t: Tally, baseline: Session, sheet, view: pl.Plot) -> None:
    align = baseline.doc.design.alignments[job.alignment]
    a0, a1 = align.begin_station, align.end_station
    on = [s for s in _full_stations(max(job.s0, a0), min(job.s1, a1))]
    mid = (max(job.s0, a0) + min(job.s1, a1)) / 2.0
    mid_xy = align.station_to_xy(mid)[0]
    vp = None
    for v in sheet.viewports:
        if abs(v.feet_per_inch - 50.0) < 0.01 and viewmap.in_window(v, v.transform().to_paper(mid_xy)):
            vp = v
            break
    if vp is None:
        problem = (f"no 1\"=50' viewport on {job.sheet} shows {job.alignment} at "
                   f"{format_station(mid)}")
        for item in ("plan view", "plan stations line up with the profile", "plan stationing"):
            t.add(item, problem)
        return
    fn = vp.transform().to_paper
    bx0, by0, bx1, by1 = vp.paper_bbox()
    problem = None
    if by0 < job.y1 - 0.05 and bx0 < job.x1 and bx1 > job.x0:
        problem = (f"the plan viewport (y {by0:.2f} to {by1:.2f} in) overlaps the profile grid "
                   f"(top at y {job.y1:.2f}): the plan goes above it")
    missing = [s for s in on if not viewmap.in_window(vp, fn(align.station_to_xy(s)[0]))]
    if problem is None and missing:
        problem = (f"the plan viewport does not show {job.alignment} at "
                   f"{', '.join(format_station(s) for s in missing)}")
    t.add("plan view", problem)

    # level and lined up with the profile
    problem = None
    tangent = [s for s in on if _on_first_tangent(align, s)]
    if len(tangent) >= 2:
        p, q = fn(align.station_to_xy(tangent[0])[0]), fn(align.station_to_xy(tangent[-1])[0])
        ang = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        if abs(pl.wrap(ang)) > LEVEL_TOL_DEG:
            problem = (f"the centerline runs at {ang:.2f} deg on the paper between "
                       f"{format_station(tangent[0])} and {format_station(tangent[-1])}; the "
                       f"plan should be turned so it runs level, stations increasing to the right")
    if problem is None:
        for s in on:
            px = fn(align.station_to_xy(s)[0])[0]
            if abs(px - job.x(s)) > X_ALIGN_TOL:
                problem = (f"{format_station(s)} is at x {px:.2f} in on the plan but "
                           f"{job.x(s):.2f} in on the profile ({abs(px - job.x(s)) * 50:.1f} ft off)")
                break
    t.add("plan stations line up with the profile", problem)

    # stationing
    missing = []
    for s in on:
        p = fn(align.station_to_xy(s)[0])
        if not any(_station_word(x.content, s) for x in _near(view.texts, p, STATION_LABEL_REACH)):
            missing.append(s)
    t.add("plan stationing", None if not missing else
          f"no station label within {STATION_LABEL_REACH} in of the centerline at "
          f"{', '.join(format_station(s) for s in missing)}")


def _on_first_tangent(align, station: float) -> bool:
    i = align.element_at(station - align.begin_station)[0]
    e = align.elements[0]
    return i == 0 and type(e).__name__ == "TangentElement"


def _grid_items(job: Job, t: Tally, view: pl.Plot) -> None:
    verticals = [s for s in view.segs if _vertical(s)]
    horizontals = [s for s in view.segs if _horizontal(s)]
    missing = []
    for st in _full_stations(job.s0, job.s1):
        x = job.x(st)
        spans = [(min(s.a[1], s.b[1]), max(s.a[1], s.b[1])) for s in verticals
                 if abs(s.a[0] - x) <= GRID_POS_TOL]
        if _cover(spans, job.y0, job.y1) < GRID_COVER:
            missing.append(format_station(st))
    elev = job.e0
    while elev <= job.e1 + 1e-6:
        y = job.y(elev)
        spans = [(min(s.a[0], s.b[0]), max(s.a[0], s.b[0])) for s in horizontals
                 if abs(s.a[1] - y) <= GRID_POS_TOL]
        if _cover(spans, job.x0, job.x1) < GRID_COVER:
            missing.append(f"el {elev:.0f}")
        elev += 5.0
    t.add("profile grid", None if not missing else
          f"no grid line across the profile grid at {', '.join(missing[:6])}"
          f"{' ...' if len(missing) > 6 else ''} (datum: {format_station(job.s0)} el "
          f"{job.e0:.0f} at paper ({job.x0:.2f}, {job.y0:.2f}), 1\"=50' by 1\"=5')")

    missing = []
    for st in _full_stations(job.s0, job.s1):
        x = job.x(st)
        if not any(_station_word(tx.content, st) for tx in view.texts
                   if abs(tx.center()[0] - x) <= 0.3 and job.y0 - 0.7 <= tx.center()[1] <= job.y0 + 0.1):
            missing.append(format_station(st))
    elev = job.e0
    while elev <= job.e1 + 1e-6:
        y = job.y(elev)
        found = False
        for tx in view.texts:
            cx, cy = tx.center()
            at_end = (job.x0 - 1.2 <= cx <= job.x0 + 1.2) or (job.x1 - 1.2 <= cx <= job.x1 + 1.2)
            if at_end and abs(cy - y) <= 0.2 and any(abs(v - elev) < 0.01 for v in numbers_in(tx.content)):
                found = True
                break
        if not found:
            missing.append(f"el {elev:.0f}")
        elev += 5.0
    t.add("grid lettering", None if not missing else
          f"grid lines not lettered: {', '.join(missing[:6])}{' ...' if len(missing) > 6 else ''} "
          f"(stations under the grid, elevations at an end of each line)")


def _grade_samples(job: Job, prof: Profile) -> List[float]:
    p0, p1 = prof.station_range()
    lo, hi = max(job.s0, p0), min(job.s1, p1)
    out = []
    s = math.ceil(lo / GRADE_STEP) * GRADE_STEP
    while s <= hi + 1e-6:
        out.append(s)
        s += GRADE_STEP
    if not out or out[0] - lo > 1e-6:
        out.insert(0, lo)
    if hi - out[-1] > 1e-6:
        out.append(hi)
    return out


def _grade_item(job: Job, t: Tally, view: pl.Plot, prof: Profile) -> None:
    grid_y = []
    e = job.e0
    while e <= job.e1 + 1e-6:
        grid_y.append(job.y(e))
        e += 5.0
    cands = [s for s in view.segs
             if not _vertical(s)
             and not (_horizontal(s) and any(abs(s.a[1] - gy) <= 0.002 for gy in grid_y))
             and max(s.a[0], s.b[0]) >= job.x0 - 0.01 and min(s.a[0], s.b[0]) <= job.x1 + 0.01
             and max(s.a[1], s.b[1]) >= job.y0 - 0.5 and min(s.a[1], s.b[1]) <= job.y1 + 0.5]
    misses = []
    samples = _grade_samples(job, prof)
    for st in samples:
        want = job.y(prof.elevation_at(st))
        ys = _crossings(cands, job.x(st))
        if not any(abs(y - want) <= GRADE_TOL_IN for y in ys):
            near = min(ys, key=lambda y: abs(y - want)) if ys else None
            misses.append((st, near))
    if not misses:
        t.add("profile grade line", None)
        return
    st, near = misses[0]
    drawn = (f"the nearest line there is at el {job.e0 + (near - job.y0) * V_SCALE:.2f}"
             if near is not None else "nothing is drawn there")
    t.add("profile grade line",
          f"the grade line misses the design profile at {len(misses)} of {len(samples)} "
          f"stations sampled every {GRADE_STEP:.0f} ft, first at {format_station(st)}: design "
          f"el {prof.elevation_at(st):.2f}, {drawn} (tolerance {GRADE_TOL_IN * V_SCALE:.2f} ft)")


def _label_items(job: Job, t: Tally, view: pl.Plot, prof: Profile) -> None:
    texts = view.texts
    any_point = False
    for vc in prof.curves():
        if vc["length"] <= 0 or not (job.s0 <= vc["pvi_station"] <= job.s1):
            continue
        sta = format_station(vc["pvi_station"])
        P = (job.x(vc["pvi_station"]), job.y(vc["pvi_elevation"]))
        near = _near(texts, P, LABEL_REACH)
        words = _joined(near)
        problem = None
        if not any(abs(v - vc["pvi_station"]) < 0.01 for v in stations_in(words)):
            problem = f"the PVI at {sta} is not lettered with its station within {LABEL_REACH} in"
        elif not any(abs(v - vc["pvi_elevation"]) <= 0.011 for v in numbers_in(words)):
            problem = (f"the PVI at {sta} is not lettered with its elevation "
                       f"{vc['pvi_elevation']:.2f}")
        t.add(f"PVI {sta}: station and elevation", problem)
        lengths = [float(a or b) for a, b in LENGTH_RE.findall(words)]
        t.add(f"PVI {sta}: curve length",
              None if any(abs(v - vc["length"]) < 0.5 for v in lengths) else
              f"the {vc['length']:.0f}' vertical curve at {sta} is not lettered with its length "
              f"(read: {', '.join(f'{v:g}' for v in lengths) or 'none'})")
        ks = [float(v) for v in K_RE.findall(words)]
        t.add(f"PVI {sta}: K",
              None if any(abs(v - vc["K"]) <= 0.51 for v in ks) else
              f"the curve at {sta} is not lettered with K = {vc['K']:.1f} "
              f"(read: {', '.join(f'{v:g}' for v in ks) or 'none'})")
    for vc in prof.curves():
        hl = vc["high_low"]
        if not hl or not (job.s0 <= hl["station"] <= job.s1):
            continue
        any_point = True
        word = HIGH_RE if hl["kind"] == "high" else LOW_RE
        P = (job.x(hl["station"]), job.y(hl["elevation"]))
        near = _near(texts, P, LABEL_REACH)
        words = _joined(near)
        label = f"{hl['kind']} point {format_station(hl['station'])}"
        problem = None
        if not word.search(words):
            problem = (f"no {hl['kind']} point lettered within {LABEL_REACH} in of "
                       f"{format_station(hl['station'])} el {hl['elevation']:.2f}")
        elif not any(abs(v - hl["station"]) <= 0.6 for v in stations_in(words)):
            problem = (f"the {hl['kind']} point is not lettered at its station "
                       f"{format_station(hl['station'])} (read: "
                       f"{', '.join(format_station(v) for v in stations_in(words)) or 'none'})")
        elif not any(abs(v - hl["elevation"]) <= 0.02 for v in numbers_in(words)):
            problem = f"the {hl['kind']} point is not lettered with its elevation {hl['elevation']:.2f}"
        t.add(label, problem)
    if not any_point:
        box = (job.x0 - 1.0, job.y0 - 1.0, job.x1 + 1.0, job.y1 + 1.0)
        liars = [x for x in texts if box[0] <= x.center()[0] <= box[2]
                 and box[1] <= x.center()[1] <= box[3]
                 and (HIGH_RE.search(x.content) or LOW_RE.search(x.content))]
        t.add("no high or low point where the profile has none",
              None if not liars else
              f"{liars[0].content!r} is lettered, but no curve on this sheet has a high or low "
              f"point (its grades do not change sign)")


def make_check(job: Job):
    def check(baseline: Session, submitted: Session) -> Result:
        t = Tally()
        sheet = _sheet(submitted, job.sheet)
        if sheet is None:
            return Result(False, f"sheet {job.sheet} is gone", [])
        view = pl.plot(submitted, sheet, pl.sheet_items(baseline, submitted, job.sheet))
        prof = job.design()
        _plan_items(job, t, baseline, sheet, view)
        _grid_items(job, t, view)
        _grade_item(job, t, view, prof)
        _label_items(job, t, view, prof)
        return t.result(f"{job.sheet}: plan over profile, grade line within "
                        f"{GRADE_TOL_IN * V_SCALE:.2f} ft, stations lined up, curves lettered")
    return check


# ------------------------------------------------------------------ solve


def _profile_from(session: Session, job: Job) -> Profile:
    rows = common.ok(session.query("get_design_data", {"kind": "pvis", "profile": job.profile,
                                                       "limit": 200}))["rows"]
    return Profile(job.profile, job.alignment,
                   [PVI(r["station"], r["elevation"], r["length"]) for r in rows])


def _layer(session: Session, name: str, color: str = "black", weight: float = 0.25) -> str:
    if name not in session.doc.layers:
        common.ok(session.execute("create_layer", {"name": name, "color": color,
                                                   "lineweight_mm": weight}))
    return name


def _text(session: Session, sheet: str, layer: str, at, content: str, rot: float = 0.0,
          halign: str = "left", valign: str = "bottom") -> None:
    common.ok(session.execute("place_text", {"space": sheet, "layer": layer, "position": list(at),
                                             "content": content, "height": TEXT_H,
                                             "rotation_deg": rot, "halign": halign,
                                             "valign": valign}))


def solve_job(job: Job, session: Session, vertical: float = V_SCALE, curves: bool = True) -> None:
    """Lay the sheet out through the command bus. ``vertical`` and ``curves``
    exist to build the naive answers the tests check fail (a 1" = 10' vertical
    scale; the grade drawn PVI to PVI with no vertical curves)."""
    sh = job.sheet
    grid = _layer(session, "PROF_GRID", "gray", 0.18)
    grade = _layer(session, "PROF_GRADE", "black", 0.5)
    note = _layer(session, "PROF_TEXT", "black", 0.25)
    sta_layer = _layer(session, "PLAN_STA", "black", 0.25)
    prof = _profile_from(session, job)
    a = session.doc.design.alignments[job.alignment]

    def X(s):
        return job.x0 + (s - job.s0) / H_SCALE

    def Y(e):
        return job.y0 + (e - job.e0) / vertical

    # plan: the centerline level across the top, stations over the profile's
    centre_x = 8.5
    s_c = job.s0 + (centre_x - job.x0) * H_SCALE
    at = common.ok(session.query("station_to_xy", {"alignment": job.alignment, "station": s_c}))
    common.ok(session.execute("create_viewport", {
        "sheet": sh, "center_paper": [centre_x, 8.2], "width_in": 15.4, "height_in": 4.6,
        "model_center": at["point"], "feet_per_inch": 50.0,
        "rotation_deg": -at["direction_deg"]}))
    lo, hi = max(job.s0, a.begin_station), min(job.s1, a.end_station)
    common.ok(session.execute("annotate_stationing", {
        "space": "model", "alignment": job.alignment, "station_range": [lo, hi],
        "interval": 100, "lettering": "full", "view_rotation": -at["direction_deg"],
        "layer": sta_layer}))

    # the grid: one line of each kind, arrayed
    first = math.ceil(job.s0 / 100.0) * 100.0
    n_cols = int(math.floor((job.s1 - first) / 100.0 + 1e-6)) + 1
    top = Y(job.e1)
    line = common.ok(session.execute("draw_line", {"space": sh, "layer": grid,
                                                   "start": [X(first), job.y0],
                                                   "end": [X(first), top]}))["created"][0]
    if n_cols > 1:
        common.ok(session.execute("array_entities", {"ids": [line], "kind": "rectangular",
                                                     "rows": 1, "columns": n_cols,
                                                     "column_spacing": 100.0 / H_SCALE}))
    n_rows = int(round((job.e1 - job.e0) / 5.0)) + 1
    line = common.ok(session.execute("draw_line", {"space": sh, "layer": grid,
                                                   "start": [job.x0, job.y0],
                                                   "end": [X(job.s1), job.y0]}))["created"][0]
    common.ok(session.execute("array_entities", {"ids": [line], "kind": "rectangular",
                                                 "rows": n_rows, "columns": 1,
                                                 "row_spacing": 5.0 / vertical}))
    for k in range(n_cols):
        s = first + 100.0 * k
        _text(session, sh, note, [X(s), job.y0 - 0.12], format_station(s)[:-3], halign="center",
              valign="top")
    for k in range(n_rows):
        e = job.e0 + 5.0 * k
        _text(session, sh, note, [job.x0 + 0.05, Y(e) + 0.03], f"{e:,.0f}")
        _text(session, sh, note, [X(job.s1) - 0.05, Y(e) + 0.03], f"{e:,.0f}", halign="right")

    # the grade line: every 5 ft, and at each PVC and PVT
    p0, p1 = prof.station_range()
    g0, g1 = max(job.s0, p0), min(job.s1, p1)
    if curves:
        cuts = {g0, g1}
        s = math.ceil(g0 / 5.0) * 5.0
        while s < g1:
            cuts.add(s)
            s += 5.0
        for vc in prof.curves():
            for key in ("pvc_station", "pvt_station"):
                if g0 < vc[key] < g1:
                    cuts.add(vc[key])
        verts = [[X(s), Y(prof.elevation_at(s))] for s in sorted(cuts)]
    else:
        def chord(s):
            pv = prof.pvis
            for p, q in zip(pv, pv[1:]):
                if p.station <= s <= q.station:
                    return p.elevation + (q.elevation - p.elevation) * (s - p.station) / (q.station - p.station)
            raise ValueError(s)
        pts = sorted({g0, g1} | {p.station for p in prof.pvis if g0 < p.station < g1})
        verts = [[X(s), Y(chord(s))] for s in pts]
    common.ok(session.execute("draw_polyline", {"space": sh, "layer": grade, "vertices": verts}))

    # each curve with its PVI on the sheet, and its high or low point
    for vc in prof.curves():
        if vc["length"] <= 0 or not (job.s0 <= vc["pvi_station"] <= job.s1):
            continue
        x, y = X(vc["pvi_station"]), Y(vc["pvi_elevation"])
        common.ok(session.execute("draw_circle", {"space": sh, "layer": note, "center": [x, y],
                                                  "radius": 0.04}))
        common.ok(session.execute("draw_line", {"space": sh, "layer": note,
                                                "start": [x, y + 0.04], "end": [x, y + 0.45]}))
        _text(session, sh, note, [x - 0.03, y + 0.5],
              f"PVI {vc['pvi_station_text']}\nEL {vc['pvi_elevation']:.2f}", rot=90.0)
        _text(session, sh, note, [x, y - 0.35],
              f"{vc['length']:.0f}' VC\nK = {vc['K']:.0f}", halign="center", valign="top")
        hl = vc["high_low"]
        if hl and job.s0 <= hl["station"] <= job.s1:
            hx, hy = X(hl["station"]), Y(hl["elevation"])
            # a high point lettered under the grade, a low point over it
            high = hl["kind"] == "high"
            word, sign = ("HIGH PT", -1.0) if high else ("LOW PT", 1.0)
            common.ok(session.execute("draw_line", {"space": sh, "layer": note,
                                                    "start": [hx, hy],
                                                    "end": [hx, hy + sign * 0.9]}))
            _text(session, sh, note, [hx + 0.03, hy + sign * 0.95],
                  f"{word} {format_station(hl['station'])}\nEL {hl['elevation']:.2f}",
                  rot=90.0, halign="right" if high else "left")


# ------------------------------------------------------------------ probes


def short_station(s: float) -> str:
    """'10+00' for a whole station, '10+05.50' otherwise."""
    text = format_station(s)
    return text[:-3] if text.endswith(".00") else text


def _prompt(job: Job) -> str:
    sta = short_station
    return (
        f"Lay out sheet {job.sheet} as a plan and profile sheet for {job.alignment}, stations "
        f"{sta(job.s0)} to {sta(job.s1)}, using the design profile "
        f"{job.profile}. Plan view on top at 1\"=50', turned so the centerline runs level "
        f"left to right, with the centerline stationed (every full station lettered). Profile "
        f"view below it at 1\"=50' horizontal and 1\"=5' vertical: put the profile grid's "
        f"lower-left corner at paper ({job.x0:.2f}, {job.y0:.2f}) in, which is station "
        f"{sta(job.s0)}, elevation {job.e0:.2f}; the grid runs to station "
        f"{sta(job.s1)} and elevation {job.e1:.2f}, with a line at every full station "
        f"and every 5 ft of elevation (finer lines are up to you), the stations lettered under "
        f"the grid and the elevations at the ends of the lines. Draw the profile grade line, "
        f"and for each vertical curve whose PVI is on this sheet letter the PVI station and "
        f"elevation, the curve length and the K value; where a curve has a high or low point "
        f"on the sheet, letter its station and elevation. A station must sit at the same "
        f"paper x in the plan and the profile. Text 0.10 in.")


def _probe(job: Job, note: str) -> Probe:
    return Probe(
        id=job.id, prompt=_prompt(job), check=make_check(job),
        solve=lambda session, job=job: solve_job(job, session),
        note=note, tags=["pilot-06", "plan-profile", "layout"], start=job.start)


for _job in JOBS:
    _register(_job)

PROBES: List[Probe] = [
    _probe(CFL, "CFL sample Plan 1 (CL1) re-laid at 1\"=50' over a 10:1 profile, 10+00 to "
                "17+50. Expected: the crest at 11+50 (150' VC, K 69.0, high point 11+09.51 el "
                "8190.30) and the sag at 16+00 (200' VC, K 80.6, low point 16+34.95 el 8183.60); "
                "the CL1 PGL runs on to 24+00, so the 22+00 curve is not this sheet's. Naive "
                "PVI-to-PVI grade and a 1\"=10' vertical both fail."),
    _probe(WFL, "WFL sheet D.5 (MAIN 01) over the whole MAIN 01 profile pieced from D.5-D.10. "
                "Planted: the grade begins mid-grid at 110+05; the only PVI on the sheet "
                "(111+00, 150' VC, K 500) is a crest between -2.00% and -2.30%, so there is no "
                "high point to letter (lettering one fails); the 116+10 sag begins at 114+10, "
                "on the sheet, so the grade must bend before 115+00."),
]

__all__ = ["PROBES", "JOBS", "Job", "build_host", "make_check", "solve_job"]
