"""Generated plan-and-profile sheets to lay out (2026-11-15, training plan §8).

The plan-and-profile pilots (``p06``, five instances on agency sheets) hand a model
a sheet, a line and a design profile and ask for the whole sheet: the plan across
the top, turned so the centerline runs level and stationed; under it a profile grid,
the grade line, each vertical curve lettered; and a station at the same paper x in
the plan and the profile.  The best frontier row passes one of five, and the usual
miss is the plan's stations not lined up with the profile's.  None of the pilots'
sheets may train (plan decision 7), and the task needs none of them: it takes a
line with a long tangent, a profile and a sheet.  ``profile_task(seed)`` makes one
from the seed alone:

- the road: a seeded design (``tasks.generator.generate_task`` on the two-sheet
  stretch, which has the long tangents), its centerline and pavement edges drawn
  by the reference;
- the sheet's stations: a window of 400 ft and up, whole 50s, whose middle is on a
  tangent.  It may run a little way onto the curve at the tangent's end (as FDOT
  sheet 12 does), no further than leaves every full station within ``DRIFT_FT`` of
  where a level plan puts it (the check allows 0.05 in on the paper), and, one
  window in eight on a first or last tangent, past the line's own beginning or end
  (as WFL sheet D.5 does);
- the profile: ``PROF-1`` made again on that line, PVIs 180 to 480 ft apart running
  past the sheet both ways, elevations to the hundredth, grades 0.3 % to 5 % that
  change sign about half the time (so some curves have a high or low point and
  some have none), curve lengths 100 to 500 ft with one PVI in eight a grade break
  with no curve and one in ten an odd length; one profile in eight begins on the
  sheet and one in eight ends on it.  At least one vertical curve is on the sheet;
- the sheet: 11 x 17, 17 x 22 or 22 x 34, the ``standard`` or ``fdot`` border, empty.
  The file plots at 1" = 50' (four in five) or 1" = 40', and that is the plan's and
  the profile's horizontal scale; the vertical is a tenth or a fifth of it;
- the prompts: the pilots' own wording (``probes.pilot.profile._prompt`` and
  ``_vague``).  The explicit one states the scales and the grid's datum on the
  paper, which the generator moves about; the vague one leaves the layout to the
  drafter;
- the check: the pilots' own.  At 1" = 50' ``profile.make_check`` as it stands; at
  1" = 40' the same items from the same functions, read in the stated grid's frame
  (the pilots' explicit check has 1" = 50' written into it).  At the vague level
  ``profile.make_vague_check``.

The ``wfl`` and ``caltrans`` borders are left out: their title blocks float inside
the usable area the engine reports, so a drafter told nothing of the layout cannot
keep a grid clear of them from what it can read.

A probe task of the pilots' harness (``eval.probe_tasks``), registered outside
``probes/pilot`` with ``probes.fixture.register_start`` under
``train-profile-<seed>``.  Every random draw comes from the stream
``profile:<seed>``.  A seed whose first line gives no window takes the line with
the other curve count, and a sheet too large for the window the next size down;
the manifest entry says so under ``dialed``.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.design.vertical import PVI, Profile
from roaddraft.document.sheets import SHEET_SIZES, Sheet
from roaddraft.probes import fixture
from roaddraft.probes.base import Probe, Result, Tally

#: the training set's seeds (the D1 sets hold 10000-18299, the deeds 19000-19299,
#: the QA reviews 20000-20299)
SEEDS = range(25000, 25300)
FILE = "plan-profile.rdraft"
TASK_TYPE = "train-plan-profile"
FAMILY = "p06"
ID_PREFIX = "TR-"
PROFILE_DESCRIPTION = "profile grade line"
#: the plan's (and the profile's horizontal) scale, and how often
H_SCALES = ((50.0, 0.8), (40.0, 0.2))
#: the second vertical scale, where a tenth of the horizontal is too tall
V_COARSE = 10.0
#: the sheets, largest first: ``(size, the shortest window worth it in ft, weight)``
SIZES = (("ANSI_D", 800.0, 0.15), ("ANSI_C", 600.0, 0.25), ("ANSI_B", 400.0, 0.60))
TEMPLATES = ("standard", "fdot")
SHEET_NAMES = ("PP-1", "PP-2", "PP-3", "PP-4", "P-201", "P-202", "C-301", "C-302")
#: how far a full station may sit from where a level plan puts it (the check allows
#: 0.05 in: 2.5 ft at 1" = 50', 2 ft at 1" = 40')
DRIFT_FT = 1.0
#: ... and how far off the tangent's line, so the curve stays in the plan view
SWING_FT = 50.0
MIN_WINDOW = 400.0
MIN_FULL_STATIONS = 4
#: the layout a drafter told nothing takes (``rule_layout``); the grounded drafter
#: (``trajectories.reasoning_profile``) works the same rule out in its shown work
MARGIN_IN = 0.5          # the grid's corner inside the usable area's
GAP_IN = 0.25            # between the grid's top and the plan view
SIDE_IN = 0.2            # the plan view past the grid, each side
ELEV_STEP = 5.0          # ft between the grid's elevation lines
MIN_PLAN_IN = 2.5        # the least plan view worth drawing
#: the layers the office keeps for a profile, in half the starts (in the others the
#: drafter makes its own)
PROFILE_LAYERS = (
    ("prof_GRID", "gray", 0.18, "Profile grid lines"),
    ("prof_MAIN", "black", 0.5, "Profile grade line of the Main line"),
    ("prof_MAIN-anno", "black", 0.25,
     "Annotation for the profile: grid stations and elevations, vertical curve data"),
)
ATTEMPTS = 60


def _ok(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


def _f2(value: float) -> float:
    return round(float(value) + 0.0, 2)


def _pick(rng: random.Random, weighted: Sequence[tuple]):
    """One of ``weighted`` (``(..., weight)`` rows) by its weight."""
    roll, run = rng.random() * sum(w[-1] for w in weighted), 0.0
    for row in weighted:
        run += row[-1]
        if roll <= run:
            return row
    return weighted[-1]


# ------------------------------------------------------------------ the sheet's frame


@dataclass(frozen=True)
class Lay:
    """One sheet's profile grid, as ``probes.pilot.profile.Job`` has it (the checks
    read ``x``, ``y``, ``x0`` ... off either), at this sheet's horizontal scale."""
    id: str
    sheet: str
    alignment: str
    profile: str
    pvis: Tuple[Tuple[float, ...], ...]
    s0: float
    e0: float
    s1: float
    e1: float
    x0: float
    y0: float
    h_scale: float
    v_scale: float
    usable: Tuple[float, float, float, float]
    level_at: Optional[float] = None

    def x(self, station: float) -> float:
        return self.x0 + (station - self.s0) / self.h_scale

    def y(self, elevation: float) -> float:
        return self.y0 + (elevation - self.e0) / self.v_scale

    @property
    def x1(self) -> float:
        return self.x(self.s1)

    @property
    def y1(self) -> float:
        return self.y(self.e1)

    @property
    def grade_tol_in(self) -> float:
        from roaddraft.probes.pilot import profile as pp
        return pp.GRADE_TOL_FT / self.v_scale

    def design(self) -> Profile:
        return Profile(self.profile, self.alignment,
                       [PVI(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in self.pvis])


def rule_layout(usable: Sequence[float], h: float, s0: float, s1: float, low: float,
                high: float) -> Optional[dict]:
    """The layout a drafter told only the sheet and the stations takes, or None where
    it does not fit: the grid's corner ``MARGIN_IN`` inside the usable area's, the
    horizontal scale the file plots at, the vertical a tenth of it (1" = 10' where
    that grid would be taller than half the usable height), the 5 ft lines at or
    outside the lowest and highest grade on the sheet, the plan above it."""
    ux0, uy0, ux1, uy1 = (float(v) for v in usable)
    x0, y0 = ux0 + MARGIN_IN, uy0 + MARGIN_IN
    e0 = math.floor(low / ELEV_STEP) * ELEV_STEP
    e1 = math.ceil(high / ELEV_STEP) * ELEV_STEP
    if e1 - e0 < 2 * ELEV_STEP:
        return None        # two lines are no grid (the vague check wants three)
    half = (uy1 - uy0) / 2.0
    v = h / 10.0
    if (e1 - e0) / v > half:
        v = V_COARSE
        if (e1 - e0) / v > half:
            return None
    width = (s1 - s0) / h
    y1 = y0 + (e1 - e0) / v
    if x0 + width + SIDE_IN > ux1 or uy1 - (y1 + GAP_IN) < MIN_PLAN_IN:
        return None
    return {"x0": x0, "y0": y0, "v": v, "e0": e0, "e1": e1}


def plan_view(lay: Lay) -> dict:
    """Where the plan view goes over ``lay``'s grid: as wide as the grid and
    ``SIDE_IN`` more each side, from ``GAP_IN`` over the grid to the usable area's
    top, the station under its middle the grid's middle station."""
    width = (lay.s1 - lay.s0) / lay.h_scale
    bottom = lay.y1 + GAP_IN
    height = lay.usable[3] - bottom
    return {"center": [lay.x0 + width / 2.0, bottom + height / 2.0],
            "width": width + 2 * SIDE_IN, "height": height,
            "station": lay.s0 + (lay.s1 - lay.s0) / 2.0}


# ------------------------------------------------------------------ the road


def _base(seed: int, curves: int):
    """The seeded design under the sheet: ``(task, session)`` with the centerline and
    the pavement edges drawn."""
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import phase_commands, session_for_task
    task = generate_task(seed, curves=curves, equations=False, task_type="draw-alignment",
                         sheets=2)
    session = session_for_task(task)
    for name, params in phase_commands(task, ["linework", "edges"]):
        _ok(session.execute(name, params))
    return task, session


def _full_stations(lo: float, hi: float) -> List[float]:
    out, s = [], math.ceil(lo / 100.0 - 1e-9) * 100.0
    while s <= hi + 1e-6:
        out.append(s)
        s += 100.0
    return out


def _drift(align, mid: float, stations: Sequence[float]) -> Tuple[float, float]:
    """How far ``stations`` sit from where a plan levelled at ``mid`` puts them: the
    most along the line, and the most square off it (feet)."""
    pm, heading, _i = align.station_to_xy(mid)
    u = (math.cos(math.radians(heading)), math.sin(math.radians(heading)))
    along = across = 0.0
    for s in stations:
        p = align.station_to_xy(s)[0]
        dx, dy = p[0] - pm[0], p[1] - pm[1]
        along = max(along, abs(dx * u[0] + dy * u[1] - (s - mid)))
        across = max(across, abs(-dx * u[1] + dy * u[0]))
    return along, across


def _window(rng: random.Random, session, alignment: str, longest: float,
            shortest: float) -> Optional[Tuple[float, float]]:
    """The sheet's stations ``(s0, s1)``: whole 50s, ``shortest`` to ``longest`` ft,
    the middle on a tangent, every full station within ``DRIFT_FT`` of a level
    plan's; None when the line has no tangent for it."""
    align = session.doc.design.alignments[alignment]
    a0, a1 = float(align.begin_station), float(align.end_station)
    tangents = session.query("get_design_data", {"alignment": alignment, "kind": "tangents"})["rows"]
    curves = session.query("get_design_data", {"alignment": alignment, "kind": "curves"})["rows"]
    rows = [t for t in tangents if t["length"] >= 0.6 * shortest]
    rng.shuffle(rows)
    rows.sort(key=lambda t: -t["length"] * rng.uniform(0.7, 1.0))
    for t in rows:
        ts, te = float(t["start_station"]), float(t["end_station"])
        # how far past each end of the tangent the sheet may run: onto a curve as far as
        # the drift allows (a^3 / 6R^2), past the line's own end one window in eight
        reach = []
        for end, first_or_last in ((ts, abs(ts - a0) < 1e-6), (te, abs(te - a1) < 1e-6)):
            if first_or_last:
                reach.append(rng.uniform(60.0, 240.0) if rng.random() < 0.125 else 0.0)
            else:
                c = next(c for c in curves if abs(c["pc_station"] - end) < 1e-6
                         or abs(c["pt_station"] - end) < 1e-6)
                reach.append(min((6.0 * float(c["radius"]) ** 2 * DRIFT_FT) ** (1.0 / 3.0) * 0.9,
                                 float(c["length"])) * rng.uniform(0.0, 1.0))
        lo = math.ceil((ts - reach[0]) / 50.0) * 50.0
        hi = math.floor((te + reach[1]) / 50.0) * 50.0
        top = min(longest, hi - lo)
        lengths = [n * 50.0 for n in range(int(shortest // 50), int(top // 50) + 1)]
        if not lengths:
            continue
        for _ in range(8):
            length = rng.choice(lengths[len(lengths) // 3:])   # the longer two thirds
            s0 = lo + 50.0 * rng.randrange(int((hi - lo - length) // 50) + 1)
            s1 = s0 + length
            mid = s0 + length / 2.0
            if not (ts + 25.0 <= mid <= te - 25.0):
                continue
            on = _full_stations(max(s0, a0), min(s1, a1))
            if len(on) < MIN_FULL_STATIONS:
                continue
            along, across = _drift(align, mid, on)
            if along <= DRIFT_FT and across <= SWING_FT:
                return s0, s1
    return None


# ------------------------------------------------------------------ the profile


def _stations(rng: random.Random, lo: float, hi: float) -> List[float]:
    """PVI stations from ``lo`` to ``hi``, 180 to 480 ft apart; one in four to the
    hundredth, the rest whole tens."""
    out = [lo]
    while hi - out[-1] > 480.0:
        step = rng.uniform(180.0, 480.0)
        s = out[-1] + step
        s = _f2(s) if rng.random() < 0.25 else round(s / 10.0) * 10.0
        if hi - s < 150.0:
            break
        out.append(s)
    if hi - out[-1] > 300.0 and rng.random() < 0.7:
        out.append(round((out[-1] + hi) / 2.0 / 10.0) * 10.0)
    out.append(hi)
    return out


#: the sharpest vertical curve drawn (K = L / A): a grade line drawn with a vertex every
#: 25 ft is then within 0.04 ft of it (A L / 800 scaled: 625 / (800 K)), inside the check's
#: 0.10 ft.  The pilots' sharpest is K = 69
MIN_K = 20.0
#: the largest grade change left as a break with no curve (FDOT sheet 12's is 0.51 %)
MAX_BREAK_PCT = 1.0


def _pvis(rng: random.Random, stations: Sequence[float]) -> Optional[Tuple[Tuple[float, ...], ...]]:
    band = rng.choice(((20.0, 95.0), (100.0, 950.0), (1000.0, 8500.0)))
    elevation = _f2(rng.uniform(*band))
    grade = rng.choice((-1, 1)) * rng.randrange(3, 51) / 10.0
    rows: List[List[float]] = [[stations[0], elevation]]
    grades = []
    for a, b in zip(stations, stations[1:]):
        grades.append(grade)
        elevation = _f2(elevation + grade * (b - a) / 100.0)
        rows.append([b, elevation])
        if rng.random() < 0.5:          # over a crest or through a sag
            grade = -math.copysign(rng.randrange(3, 46) / 10.0, grade)
        else:                           # steeper or flatter, the same way
            while True:
                g = math.copysign(rng.randrange(3, 51) / 10.0, grade)
                if abs(g - grade) >= 0.4:
                    grade = g
                    break
    half_before = 0.0
    for k in range(1, len(rows) - 1):
        back = rows[k][0] - rows[k - 1][0] - half_before
        ahead = (rows[k + 1][0] - rows[k][0]) / (2.0 if k + 1 < len(rows) - 1 else 1.0)
        most = 2.0 * min(back, ahead)
        roll = rng.random()
        if roll < 0.125 or most < 60.0:
            length = 0.0                 # a grade break with no vertical curve
        elif roll < 0.225:
            length = float(rng.randint(60, int(min(most, 500.0))))
        else:
            fits = [L for L in (100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0) if L <= most]
            length = rng.choice(fits) if fits else float(int(most // 10) * 10)
        a_pct = abs(grades[k] - grades[k - 1])
        if length and length < MIN_K * a_pct:   # too sharp: the shortest curve that is not
            fits = [L for L in (100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0)
                    if MIN_K * a_pct <= L <= most]
            length = fits[0] if fits else 0.0
        if not length and a_pct > MAX_BREAK_PCT:
            return None                  # no road breaks grade that much without a curve
        rows[k].append(length)
        half_before = length / 2.0
    return tuple(tuple(r) for r in rows)


def _range(prof: Profile, lo: float, hi: float) -> Tuple[float, float]:
    """The lowest and highest grade between two stations."""
    n = max(int((hi - lo) / 5.0), 1)
    values = [prof.elevation_at(lo + (hi - lo) * i / n) for i in range(n + 1)]
    return min(values), max(values)


def _on_sheet(prof: Profile, s0: float, s1: float) -> Tuple[float, float]:
    p0, p1 = prof.station_range()
    return max(s0, p0), min(s1, p1)


def _profile(rng: random.Random, name: str, alignment: str, a0: float, a1: float,
             s0: float, s1: float, h: float) -> Optional[Profile]:
    """A profile through the sheet, running past it both ways where the line does
    (one in eight begins on the sheet, one in eight ends on it), with a vertical
    curve on the sheet; None when this draw has none."""
    roll = rng.random()
    lo = max(a0, s0 - rng.uniform(150.0, 600.0))
    hi = min(a1, s1 + rng.uniform(150.0, 600.0))
    if roll < 0.125:
        lo = max(a0, s0 + rng.uniform(30.0, 180.0))
    elif roll < 0.25:
        hi = min(a1, s1 - rng.uniform(30.0, 180.0))
    lo = _f2(lo) if (rng.random() < 0.25 or lo == a0) else math.ceil(lo / 10.0) * 10.0
    hi = math.floor(hi * 100.0) / 100.0 if (rng.random() < 0.25 or hi == a1) \
        else math.floor(hi / 10.0) * 10.0
    lo, hi = max(lo, math.ceil(a0 * 100.0) / 100.0), min(hi, math.floor(a1 * 100.0) / 100.0)
    # the grade's ends plot where a drafter working to four decimals of an inch puts them
    # (the check wants a line drawn at the very station the grade begins and ends at):
    # hundredths of a foot at 1" = 50', fifths at 1" = 40'
    q = 0.01 if abs(h - 50.0) < 1e-9 else 0.2
    lo, hi = _f2(math.ceil(lo / q - 1e-6) * q), _f2(math.floor(hi / q + 1e-6) * q)
    if hi - lo < 400.0:
        return None
    stations = _stations(rng, lo, hi)
    if len(stations) < 3:
        return None
    pvis = _pvis(rng, stations)
    if pvis is None:
        return None
    try:
        prof = Profile(name, alignment, [PVI(p[0], p[1], p[2] if len(p) > 2 else 0.0)
                                         for p in pvis], description=PROFILE_DESCRIPTION)
        prof.validate()
    except Exception:
        return None
    g0, g1 = _on_sheet(prof, s0, s1)
    if g1 - g0 < 0.6 * (s1 - s0) or min(p.elevation for p in prof.pvis) < 12.0:
        return None
    curved = [vc for vc in prof.curves() if vc["length"] > 0
              and vc["pvc_station"] < g1 - 20.0 and vc["pvt_station"] > g0 + 20.0]
    return prof if curved else None


# ------------------------------------------------------------------ the stated layout


def _stated(rng: random.Random, usable, h: float, s0: float, s1: float, low: float,
            high: float, rule: dict) -> Optional[dict]:
    """The grid the explicit prompt states: the rule's, moved about (its corner, a
    line or two more above or below, sometimes the other vertical scale)."""
    ux0, uy0, ux1, uy1 = usable
    width = (s1 - s0) / h
    room = ux1 - SIDE_IN - width - ux0
    xs = [d for d in (0.3, 0.5, 0.6, 0.75, 1.0, 1.25) if d <= room + 1e-9]
    if not xs:
        return None
    x0 = _f2(ux0 + rng.choice(xs))
    y0 = _f2(uy0 + rng.choice((0.4, 0.5, 0.6, 0.75, 0.85)))
    e0, e1, v = rule["e0"], rule["e1"], rule["v"]
    fine = h / 10.0
    if rng.random() < 0.3:              # the other vertical scale, where there is one
        v = V_COARSE if v == fine else fine
    for _ in range(3):                  # room over or under the grade, a line at a time
        roll = rng.random()
        if roll < 0.35:
            e1 += ELEV_STEP
        elif roll < 0.6:
            e0 -= ELEV_STEP
    for _ in range(12):
        if uy1 - (y0 + (e1 - e0) / v + GAP_IN) >= MIN_PLAN_IN and (e1 - e0) / v >= 1.0:
            return {"x0": x0, "y0": y0, "v": v, "e0": e0, "e1": e1}
        if (e1 - e0) / v < 1.0:         # too flat to read: more lines
            e1 += ELEV_STEP
        elif e1 - ELEV_STEP >= rule["e1"]:
            e1 -= ELEV_STEP
        elif e0 + ELEV_STEP <= rule["e0"]:
            e0 += ELEV_STEP
        elif v != V_COARSE and (e1 - e0) / V_COARSE >= 1.0:
            v = V_COARSE
        else:
            return None
    return None


# ------------------------------------------------------------------ the check


def _check(lay: Lay):
    """The pilots' explicit check: ``profile.make_check`` at 1" = 50'; at another
    scale the same items from the same functions, in the stated grid's frame."""
    from roaddraft.probes import plotted as pl
    from roaddraft.probes.pilot import profile as pp
    if abs(lay.h_scale - pp.H_SCALE) < 1e-9:
        return pp.make_check(lay)

    def check(baseline, submitted) -> Result:
        t = Tally()
        sheet = pp._sheet(submitted, lay.sheet)
        if sheet is None:
            return Result(False, f"sheet {lay.sheet} is gone", [])
        view = pl.plot(submitted, sheet, pl.sheet_items(baseline, submitted, lay.sheet))
        prof = lay.design()
        n = int(round((lay.e1 - lay.e0) / ELEV_STEP))
        ys = tuple(lay.y(lay.e0 + ELEV_STEP * k) for k in range(n + 1))
        stated = pp.Grid(lay.sheet, lay.alignment, lay.s0, lay.s1, lay.h_scale, lay.x0, ys,
                         lay.v_scale, lay.e0, lay.y0, ys)
        vp, _hint = pp._plan_viewport(lay, baseline, sheet, (lay.h_scale,))
        if vp is None:
            problem = (f"no 1\"={lay.h_scale:g}' viewport on {lay.sheet} shows {lay.alignment} "
                       f"at the middle of the sheet's stations")
            for item in ("plan view", "plan stations line up with the profile",
                         "plan stationing"):
                t.add(item, problem)
        else:
            pp._vague_plan_items(lay, t, baseline, view, vp, stated)
        pp._grid_items(lay, t, view)
        pp._grade_item(lay, t, view, prof)
        pp._label_items(lay, t, view, prof)
        return t.result(f"{lay.sheet}: plan over profile at 1\"={lay.h_scale:g}', grade line "
                        f"within {pp.GRADE_TOL_FT:.2f} ft, stations lined up, curves lettered")
    return check


# ------------------------------------------------------------------ the scripted answer


def _text(session, sheet: str, layer: str, at, content: str, rot: float = 0.0,
          halign: str = "left", valign: str = "bottom") -> None:
    from roaddraft.probes.pilot import profile as pp
    _ok(session.execute("place_text", {"space": sheet, "layer": layer, "position": list(at),
                                       "content": content, "height": pp.TEXT_H,
                                       "rotation_deg": rot, "halign": halign, "valign": valign}))


def solve_lay(lay: Lay, session, twist_off: float = 0.0, curves: bool = True) -> None:
    """Lay the sheet out through the command bus, as the pilots' scripted answer does
    (``profile.solve_job``), on this sheet's frame.  ``twist_off`` (degrees) and
    ``curves`` build the naive answers the tests check fail: the plan turned off
    level, the grade drawn PVI to PVI."""
    from roaddraft.core.units import format_station
    from roaddraft.probes.pilot import profile as pp
    sh, h = lay.sheet, lay.h_scale
    grid = pp._layer(session, "PROF_GRID", "gray", 0.18)
    grade = pp._layer(session, "PROF_GRADE", "black", 0.5)
    note = pp._layer(session, "PROF_TEXT", "black", 0.25)
    sta_layer = pp._layer(session, "PLAN_STA", "black", 0.25)
    prof = pp._profile_from(session, lay)
    a = session.doc.design.alignments[lay.alignment]
    X, Y = lay.x, lay.y

    view = plan_view(lay)
    at = _ok(session.query("station_to_xy", {"alignment": lay.alignment,
                                             "station": view["station"]}))
    twist = -at["direction_deg"] + twist_off
    _ok(session.execute("create_viewport", {
        "sheet": sh, "center_paper": view["center"], "width_in": view["width"],
        "height_in": view["height"], "model_center": at["point"], "feet_per_inch": float(h),
        "rotation_deg": twist}))
    lo, hi = max(lay.s0, a.begin_station), min(lay.s1, a.end_station)
    _ok(session.execute("annotate_stationing", {
        "space": "model", "alignment": lay.alignment, "station_range": [lo, hi],
        "interval": 100, "lettering": "full", "view_rotation": twist, "layer": sta_layer}))

    first = math.ceil(lay.s0 / 100.0) * 100.0
    n_cols = int(math.floor((lay.s1 - first) / 100.0 + 1e-6)) + 1
    line = _ok(session.execute("draw_line", {"space": sh, "layer": grid,
                                             "start": [X(first), lay.y0],
                                             "end": [X(first), lay.y1]}))["created"][0]
    if n_cols > 1:
        _ok(session.execute("array_entities", {"ids": [line], "kind": "rectangular", "rows": 1,
                                               "columns": n_cols, "column_spacing": 100.0 / h}))
    n_rows = int(round((lay.e1 - lay.e0) / ELEV_STEP)) + 1
    line = _ok(session.execute("draw_line", {"space": sh, "layer": grid,
                                             "start": [lay.x0, lay.y0],
                                             "end": [lay.x1, lay.y0]}))["created"][0]
    _ok(session.execute("array_entities", {"ids": [line], "kind": "rectangular", "rows": n_rows,
                                           "columns": 1, "row_spacing": ELEV_STEP / lay.v_scale}))
    for k in range(n_cols):
        s = first + 100.0 * k
        _text(session, sh, note, [X(s), lay.y0 - 0.12], format_station(s)[:-3], halign="center",
              valign="top")
    for k in range(n_rows):
        e = lay.e0 + ELEV_STEP * k
        _text(session, sh, note, [lay.x0 + 0.05, Y(e) + 0.03], f"{e:.0f}")
        _text(session, sh, note, [lay.x1 - 0.05, Y(e) + 0.03], f"{e:.0f}", halign="right")

    g0, g1 = _on_sheet(prof, lay.s0, lay.s1)
    if curves:
        cuts = {g0, g1}
        s = math.ceil(g0 / 5.0) * 5.0
        while s < g1:
            cuts.add(s)
            s += 5.0
        for vc in prof.curves():
            cuts.update(vc[key] for key in ("pvc_station", "pvt_station") if g0 < vc[key] < g1)
        verts = [[X(s), Y(prof.elevation_at(s))] for s in sorted(cuts)]
    else:
        def chord(s):
            for p, q in zip(prof.pvis, prof.pvis[1:]):
                if p.station <= s <= q.station:
                    return p.elevation + (q.elevation - p.elevation) * (s - p.station) \
                        / (q.station - p.station)
            raise ValueError(s)
        pts = sorted({g0, g1} | {p.station for p in prof.pvis if g0 < p.station < g1})
        verts = [[X(s), Y(chord(s))] for s in pts]
    _ok(session.execute("draw_polyline", {"space": sh, "layer": grade, "vertices": verts}))

    for vc in prof.curves():
        if vc["length"] <= 0:
            continue
        if lay.s0 <= vc["pvi_station"] <= lay.s1:
            x, y = X(vc["pvi_station"]), Y(vc["pvi_elevation"])
            _ok(session.execute("draw_line", {"space": sh, "layer": note, "start": [x, y],
                                              "end": [x, y + 0.45]}))
            _text(session, sh, note, [x - 0.05, y + 0.5],
                  f"PVI {format_station(vc['pvi_station'])}\nEL {vc['pvi_elevation']:.2f}",
                  rot=90.0)
            _text(session, sh, note, [x, y - 0.35], f"{vc['length']:.0f}' VC\nK = {vc['K']:.2f}",
                  halign="center", valign="top")
        hl = vc["high_low"]
        if hl and lay.s0 <= hl["station"] <= lay.s1:
            hx, hy = X(hl["station"]), Y(hl["elevation"])
            high = hl["kind"] == "high"
            word, sign = ("HIGH PT", -1.0) if high else ("LOW PT", 1.0)
            _ok(session.execute("draw_line", {"space": sh, "layer": note, "start": [hx, hy],
                                              "end": [hx, hy + sign * 0.9]}))
            _text(session, sh, note, [hx + 0.05, hy + sign * 1.0],
                  f"{word} {format_station(hl['station'])}\nEL {hl['elevation']:.2f}",
                  rot=90.0, halign="right" if high else "left")


# ------------------------------------------------------------------ the task


@dataclass(frozen=True)
class ProfileTask:
    """One generated plan-and-profile sheet: its probe, its frame, what was drawn."""
    seed: int
    probe: Probe
    lay: Lay
    base_task_id: str
    size: str
    template: str
    layers: bool
    dialed: Tuple[Tuple[str, object], ...]
    facts: Tuple[Tuple[str, object], ...]

    def task_id(self, level: str) -> str:
        """``TR-<probe id>-<hash>`` over the task text at ``level``, the design it is on,
        the profile and the sheet, so a changed generator or prompt is a new task (the
        vague text states neither the profile's PVIs nor the sheet's size)."""
        from roaddraft.eval.probe_tasks import brief_text
        lay = self.lay
        what = repr((lay.pvis, lay.s0, lay.s1, lay.h_scale, self.size, self.template,
                     self.layers))
        h = hashlib.sha256((brief_text(self.probe, level) + "\0" + self.base_task_id + "\0"
                            + what).encode("utf-8")).hexdigest()[:10]
        return f"{ID_PREFIX}{self.probe.id}-{h}"


def _facts(lay: Lay, align) -> Dict[str, object]:
    """What this sheet asks of the drafter, for the manifest: the pilots' traps it has."""
    prof = lay.design()
    p0, p1 = prof.station_range()
    a0, a1 = float(align.begin_station), float(align.end_station)
    curves = [vc for vc in prof.curves() if vc["length"] > 0]
    pvi_on = [vc for vc in curves if lay.s0 <= vc["pvi_station"] <= lay.s1]
    points = [vc["high_low"] for vc in curves
              if vc["high_low"] and lay.s0 <= vc["high_low"]["station"] <= lay.s1]
    on = _full_stations(max(lay.s0, a0), min(lay.s1, a1))
    kinds = {type(align.elements[align.element_at(s - a0)[0]]).__name__ for s in on}
    return {
        "curves_lettered": len(pvi_on),
        "high_low": sorted(p["kind"] for p in points),
        # a high or low point on the sheet whose PVI is off it (WFL D.9)
        "point_without_pvi": any(not (lay.s0 <= vc["pvi_station"] <= lay.s1) for vc in curves
                                 if vc["high_low"] and lay.s0 <= vc["high_low"]["station"] <= lay.s1),
        # a curve on the sheet whose PVI is off it (WFL D.5, D.12)
        "curve_without_pvi": any(vc["pvc_station"] < lay.s1 and vc["pvt_station"] > lay.s0
                                 and not (lay.s0 <= vc["pvi_station"] <= lay.s1) for vc in curves),
        # a PVI with no vertical curve on the sheet (FDOT sheet 12)
        "grade_break": any(vc["length"] <= 0 and lay.s0 <= vc["pvi_station"] <= lay.s1
                           for vc in prof.curves()),
        # the grade begins or ends on the sheet (WFL D.5, D.12; FDOT sheet 12)
        "grade_begins_on_sheet": p0 > lay.s0 + 1e-6,
        "grade_ends_on_sheet": p1 < lay.s1 - 1e-6,
        # the sheet runs past the line's own beginning or end
        "past_the_line": lay.s0 < a0 - 1e-6 or lay.s1 > a1 + 1e-6,
        # the sheet runs onto a horizontal curve (FDOT sheet 12)
        "onto_a_curve": len(kinds) > 1,
    }


_STARTS: Dict[int, dict] = {}


def _title_fields(template: str, task, sheet: str, h: float, s0: float, s1: float) -> dict:
    from roaddraft.core.units import format_station
    given = dict(task.brief.deliverable["sheets"][0]["title_block_fields"])
    span = f"{format_station(s0)[:-3]} TO {format_station(s1)[:-3]}"
    if template == "fdot":
        return {"agency": given.get("agency", ""), "road_no": given.get("project", "").split(" ")[1]
                if len(given.get("project", "").split(" ")) > 1 else "",
                "sheet_title": f"PLAN AND PROFILE - {span}", "sheet_number": sheet}
    given.update(sheet_title="PLAN AND PROFILE", sheet_number=sheet, total_sheets="",
                 scale=f"1\" = {h:g}'")
    return given


def _build(seed: int, rng: random.Random, curves: int, sizes: Sequence[tuple]):
    """One line and the sheet on it, or None when this line gives no window.  Returns
    ``(task, session, lay, size, template, layers)``."""
    task, session = _base(seed, curves)
    alignment = task.brief.alignment_name
    align = session.doc.design.alignments[alignment]
    a0, a1 = float(align.begin_station), float(align.end_station)
    h = _pick(rng, H_SCALES)[0]
    template = rng.choice(TEMPLATES)
    name = rng.choice(SHEET_NAMES)
    layers = rng.random() < 0.5
    profile_name = next(iter(session.doc.design.profiles), "PROF-1")
    for size, shortest, _w in sizes:
        width_in, height_in = SHEET_SIZES[size]
        usable = tuple(float(v) for v in Sheet(
            id="-", name="-", size=size, width_in=width_in, height_in=height_in,
            title_block_template=template).usable_area())
        longest = math.floor((usable[2] - usable[0] - MARGIN_IN - SIDE_IN) * h / 50.0) * 50.0
        window = _window(rng, session, alignment, longest, max(shortest, MIN_WINDOW))
        if window is None:
            continue
        s0, s1 = window
        for _ in range(ATTEMPTS):
            prof = _profile(rng, profile_name, alignment, a0, a1, s0, s1, h)
            if prof is None:
                continue
            low, high = _range(prof, *_on_sheet(prof, s0, s1))
            rule = rule_layout(usable, h, s0, s1, low, high)
            if rule is None:
                continue
            stated = _stated(rng, usable, h, s0, s1, low, high, rule)
            if stated is None:
                continue
            pvis = tuple((p.station, p.elevation) + ((p.length,) if p.length else ())
                         for p in prof.pvis)
            lay = Lay(id=f"t06-profile-{seed}", sheet=name, alignment=alignment,
                      profile=profile_name, pvis=pvis, s0=s0, e0=stated["e0"], s1=s1,
                      e1=stated["e1"], x0=stated["x0"], y0=stated["y0"], h_scale=h,
                      v_scale=stated["v"], usable=usable)
            return task, session, lay, size, template, layers
    return None


def _start(session, task, lay: Lay, size: str, template: str, layers: bool) -> None:
    """The start document: the road, the profile, the empty sheet, the plot scale."""
    doc = session.doc
    for name in list(doc.design.profiles):
        _ok(session.execute("delete_profile", {"name": name}))
    _ok(session.execute("create_profile", {"name": lay.profile, "alignment": lay.alignment,
                                           "pvis": [list(p) for p in lay.pvis],
                                           "description": PROFILE_DESCRIPTION}))
    if layers:
        for name, color, weight, description in PROFILE_LAYERS:
            _ok(session.execute("create_layer", {"name": name, "color": color,
                                                 "lineweight_mm": weight,
                                                 "description": description}))
    _ok(session.execute("create_sheet", {
        "name": lay.sheet, "size": size, "title_block_template": template,
        "title_block_fields": _title_fields(template, task, lay.sheet, lay.h_scale, lay.s0,
                                            lay.s1)}))
    _ok(session.execute("set_annotation_scale", {"scale": lay.h_scale}))
    for key in ("task_id", "spec_version"):
        (doc.meta or {}).pop(key, None)


def _prompts(lay: Lay) -> Tuple[str, str]:
    """The pilots' wording on this sheet (their explicit prompt has 1" = 50' written in)."""
    from roaddraft.probes.pilot import profile as pp
    explicit = pp._prompt(lay)
    assert explicit.count("1\"=50'") == 2
    explicit = explicit.replace("1\"=50'", f"1\"={lay.h_scale:g}'")
    return explicit, pp._vague(lay)


@lru_cache(maxsize=None)
def profile_task(seed: int) -> ProfileTask:
    """The generated plan-and-profile sheet of ``seed``; ``ValueError`` when the seed's
    lines give none."""
    from roaddraft.probes.pilot import profile as pp
    rng = random.Random(f"profile:{seed}")
    first = rng.choice((1, 2))
    want = _pick(rng, SIZES)[0]
    sizes = SIZES[[s[0] for s in SIZES].index(want):]
    built, curves = None, first
    for curves in (first, 3 - first):
        try:
            built = _build(seed, random.Random(f"profile:{seed}:{curves}"), curves, sizes)
        except (RuntimeError, AssertionError):
            built = None     # the generator lays no two-sheet line of this many curves out
        if built is not None:
            break
    if built is None:
        raise ValueError(f"seed {seed}: no tangent long enough for a plan and profile sheet")
    task, session, lay, size, template, layers = built
    dialed = []
    if curves != first:
        dialed.append(("curves", curves))
    if size != want:
        dialed.append(("size", size))
    align = session.doc.design.alignments[lay.alignment]
    _start(session, task, lay, size, template, layers)
    explicit, vague = _prompts(lay)
    start = _register(seed, session)
    facts = _facts(lay, align)
    probe = Probe(id=lay.id, prompt=explicit, vague=vague, check=_check(lay),
                  vague_check=pp.make_vague_check(lay),
                  solve=lambda s, lay=lay: solve_lay(lay, s), start=start,
                  tags=["plan-profile", "layout", "train"], family=FAMILY,
                  params={"seed": seed, "size": size, "template": template},
                  note=(f"Generated plan and profile sheet on seed {seed}'s design: "
                        f"{lay.s0:.0f} to {lay.s1:.0f} at 1\"={lay.h_scale:g}' over "
                        f"1\"={lay.v_scale:g}', {size} {template}; "
                        + ", ".join(f"{k}={v}" for k, v in facts.items() if v) + "."))
    return ProfileTask(seed, probe, lay, task.task_id, size, template, layers, tuple(dialed),
                       tuple(facts.items()))


def _register(seed: int, session) -> str:
    """Register the start ``train-profile-<seed>``: the document as built, written to
    the project folder each time an episode starts."""
    from roaddraft.document.fileformat import write_document
    name = f"train-profile-{seed}"
    _STARTS[seed] = session.doc.to_dict()
    if name in fixture.EXTRA_STARTS:
        return name

    def build(out: Path) -> Path:
        path = Path(out) / FILE
        write_document(path, _STARTS[seed])
        return path

    fixture.register_start(name, FILE, build)
    return name


# ------------------------------------------------------------------ the set


def entry(seed: int) -> dict:
    """A manifest entry of ``train-profile``."""
    t = profile_task(seed)
    lay = t.lay
    row = {"seed": seed, "family": FAMILY, "task_type": TASK_TYPE, "kind": "plan-profile",
           "stations": [lay.s0, lay.s1], "feet_per_inch": lay.h_scale,
           "vertical_feet_per_inch": lay.v_scale, "size": t.size, "template": t.template,
           "profile_layers": t.layers, "pvis": len(lay.pvis), **dict(t.facts),
           "base_task_id": t.base_task_id,
           "task_id": t.task_id("explicit"), "vague_task_id": t.task_id("vague")}
    if t.dialed:
        row["dialed"] = dict(t.dialed)
    return row


def probe_task(row: dict, strict: bool = True, level: str = "explicit"):
    """The probe task a ``train-profile`` manifest row names, posed at ``level``."""
    from roaddraft.eval.probe_tasks import ProbeTask, brief_text
    t = profile_task(int(row["seed"]))
    tid = t.task_id(level)
    want = row.get("vague_task_id") if level == "vague" else row["task_id"]
    if strict and tid != want:
        raise ValueError(f"{level} task id of plan-and-profile seed {row['seed']} is {tid}, the "
                         f"manifest says {want}: the generator or prompt changed; python -m "
                         "roaddraft.eval taskset --write train-profile")
    return ProbeTask(t.probe, tid, TASK_TYPE, brief_text(t.probe, level), level)


__all__ = ["SEEDS", "FILE", "TASK_TYPE", "FAMILY", "Lay", "ProfileTask", "profile_task",
           "rule_layout", "plan_view", "solve_lay", "entry", "probe_task", "PROFILE_LAYERS",
           "MARGIN_IN", "GAP_IN", "SIDE_IN", "ELEV_STEP", "V_COARSE"]
