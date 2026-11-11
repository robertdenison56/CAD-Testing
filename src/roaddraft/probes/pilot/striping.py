"""Pilot 13: a striping plan with the no-passing zones found from the profile.

A two-lane road: MAIN 01, the Northeast Entrance Road of the WFL sample plan
set (sheets D.6 and D.7, 12-ft lanes on a 30-ft pavement). The model stripes
a station range in model space: a yellow centerline -- one broken line (10-ft
stripes, 30-ft gaps) where passing is allowed both ways, and a pair of lines
0.33 ft either side of the centerline where it is not, solid on the side of
the traffic the zone applies to (solid beside broken for one direction,
solid/solid for both) -- and white solid edge lines 12 ft each side.

What makes it hard: nobody says where the zones are. The model has to know
that MUTCD Table 3B-1 gives the minimum passing sight distance for the stated
85th-percentile speed (800 ft at 50 mph, 900 ft at 55 mph -- not the old
Green Book design values, and not stopping sight distance), that Section
3B.02 measures it from a 3.5-ft eye to a 3.5-ft object, and that each
direction of travel has its own zones, which begin where the sight distance
ahead first falls short and end where it recovers. No engine query answers
an elevation at a station, so the model computes the grade line from the
PVIs that ``get_design_data`` gives (parabolic curves) and sweeps the sight
line along it both ways. On this crest (PVI 123+50, -1.00% to -3.90%, 400'
VC) the two directions' zones do not even overlap: each sheet carries a
one-direction zone only, so the naive "double yellow over the crest" is
wrong twice over (wrong place, wrong marking), and the solid line has to go
on the correct side.

* ``p13-striping-wfl15`` -- sheet D.6, 115+00 to 122+50, 55 mph (900 ft).
  Truth: up-station traffic is in a no-passing zone 116+60 to 121+29; the
  down-station traffic has none on this range.
* ``p13-striping-wfl16`` -- sheet D.7, 122+50 to 130+00, 50 mph (800 ft).
  Truth: down-station traffic is in a no-passing zone from 129+21 back to
  125+75; up-station traffic has none on this range (its zone ends at
  121+21, on D.6).

The design profile is the whole MAIN 01 profile pieced together from the
published sheets D.5 to D.12, every PVI checked against the next sheet's
grade and the published K: 104+00 el 6280.87 (the existing road behind the
begin of project, on the same -2.00% grade), PVIs 111+00 el 6266.87 (150'),
116+10 el 6255.14 (400'), 123+50 el 6247.73 (400'), 131+00 el 6218.48
(500'), 146+40 el 6192.30 (800'), 158+60 el 6265.50 (600'), 164+10 el
6272.65 (100'), 165+40 el 6273.16 (100'), end 166+00 el 6273.74. The
redraft base files carry no profile, so the start builds it with
``create_profile`` in the sheet file, which owns the alignment (see
``profile.build_host``). The horizontal curves on both sheets are taken as
cleared (the prompt says so): only the profile governs.

How the truth is computed (``zones``): elevations on a 1-ft grid from the
design profile. For each station s, 1 ft apart, and each direction, the eye
is 3.5 ft above the grade at s; walking away from s a foot at a time the
running maximum of the slope from the eye to the road surface is kept, and
the object 3.5 ft above the grade at distance d is hidden when the slope from
the eye to it is below that maximum (the road between rises above the sight
line). s is in that direction's no-passing zone when some object within the
passing sight distance is hidden. Zones are the runs of such stations; zones
of one direction less than 400 ft apart are joined (MUTCD 3B.02); then they
are clipped to the striping range. The grid is 1 ft against a 25-ft
tolerance. Sweeping both directions is what makes the zones asymmetric: the
up-station zone sits before the crest, the down-station zone after it.

How it is graded (``check``, on the saved document's added model-space
linework, each piece projected onto MAIN 01 for its station and offset):
pieces at 0 ft (+-0.12) are the centerline stripe, at +-0.33 (+-0.10) the
right and left stripes of a pair (right of stationing = the up-station
traffic's side), at +-12 (+-0.25) the edge lines; touching pieces in a band
are merged; a merged piece over 15 ft is a solid line, otherwise a stripe.

* edge lines: each side covers 99.5% of the range.
* each direction's zones: the solid lines on its side match the truth zones
  one for one, each end within 25 ft (an end clipped by the range only has
  to reach it).
* broken lines: where both directions may pass, the centerline stripe; beside
  a one-direction zone, the other stripe of the pair; stripes 10 ft (+-0.5),
  gaps 30 ft (+-1), running the length of the region (25 ft of slack at each
  zone end, 40 ft for the pattern's phase).
* nothing in the wrong place: no centerline stripe inside a zone, no pair
  stripe where both directions may pass, no solid line on the centerline,
  nothing unreadable within 0.8 ft of the centerline.

Naive answers this fails (built in tests/test_pilot_striping.py): double
yellow from PVC to PVT (121+50 to 125+50) both ways; the right zone with the
solid line on the wrong side; zones from stopping-sight-distance heights
(3.5-ft eye, 2.0-ft object).

The vague level (``Probe.vague``, 2026-11-08) keeps the job and its data -- the
line, range and sheet, two lanes of 12 ft, the profile and speed, the clear
horizontal sight lines, what the profile covers -- and how the work is read
(stripe centers, real stripes, model space), and says "per the MUTCD" for the
rest. The MUTCD's own values stay the standard (Table 3B-1, the 3.5-ft heights,
zones exactly where the sight distance falls short, joined under 400 ft, the
solid on the restricted traffic's side), so ``vague_check`` grades the zones as
``check`` does; it reads only what the explicit brief fixed beyond the MUTCD
over the range the MUTCD allows: each stripe of a pair 0.20 to 0.60 ft off the
centerline, broken lines of 10-ft stripes and 30-ft gaps or a similar ratio
(12/36), edge lines within 0.35 ft of 12 ft. Neither level grades layers or
colours.

Four more instances (2026-11), each on another stretch or profile, so no
answer is a copy of the D.6/D.7 crest:

* ``p13-striping-wfl17`` -- D.8, 130+00 to 137+50, 65 mph (1,100 ft): the only
  curve on the sheet is the 131+00 sag; the down-station zone of the 123+50
  crest runs on onto the sheet, 130+00 to 132+15.
* ``p13-striping-wfl19`` -- D.10, 145+00 to 152+50, 60 mph (1,000 ft): the
  146+40 sag restricts nothing; the up-station zone toward the 158+60 crest
  bend (+6.00% to +1.30%) begins at 149+37, 623 ft before its PVC (155+60).
* ``p13-striping-wfl20`` -- D.11, 152+50 to 160+00, 55 mph (900 ft): both
  directions on one sheet (up-station to 158+23, down-station from 159+39),
  with a broken centerline between.
* ``p13-striping-cflpnp`` -- CFL Plan 1, CL1 10+00 to 17+50, 55 mph: the 11+50
  crest has a summit (+0.50% to -1.67%), but its approach is so flat that
  only the down-station traffic is restricted, 13+90 to 16+80, across the
  16+00 sag.

These use MAIN01_PVIS_EXT (the existing road beyond END PROJECT carried on at
+0.97% to 172+00, which the D.11 sweep needs) and CFL_PVIS_EXT, and say so in
the prompt. None of the profiles here gives zones of the two directions that
overlap: MAIN 01 has no summit at all (every crest bend is on a grade that
keeps its sign), and the CFL summit restricts one direction only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.core.units import format_station
from roaddraft.design.errors import DesignError
from roaddraft.design.vertical import PVI, Profile
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common
from roaddraft.probes.pilot.profile import build_host, short_station

#: MUTCD (2009, retained in the 11th edition) Table 3B-1: minimum passing sight
#: distance by 85th-percentile or posted speed, mph -> ft
MUTCD_PSD = {25: 450, 30: 500, 35: 550, 40: 600, 45: 700, 50: 800, 55: 900, 60: 1000,
             65: 1100, 70: 1200}
EYE = 3.5
OBJECT = 3.5
CONNECT = 400.0             # zones of one direction closer than this are joined
ZONE_TOL = 25.0             # ft on each zone end
PAIR = 0.33                 # ft: each stripe of a pair off the centerline
EDGE = 12.0
BAND_TOL = {"center": 0.12, "pair": 0.10, "edge": 0.25}
SOLID_MIN = 15.0            # a merged piece longer than this is a solid line
DASH, GAP = 10.0, 30.0
DASH_TOL, GAP_TOL = 0.5, 1.0
MERGE = 0.5                 # ft: pieces this close in one band are one mark

# The vague level states none of the marking pattern, only "per the MUTCD", so what the
# explicit brief fixed beyond the MUTCD is read over the range the MUTCD allows (2009,
# Section 3A.06): a double line is two normal lines (4 to 6 in) "separated by a discernible
# space", so each stripe of a pair may sit from 0.20 ft (4-in lines 0.8 in apart) to 0.60 ft
# (6-in lines 8 in apart) off the centerline; broken lines "should consist of 10-foot line
# segments and 30-foot gaps, or dimensions in a similar ratio", so a stripe of 10 ft up to
# SOLID_MIN with gaps three times it (within RATIO_TOL); the edge lines bound 12-ft lanes, so
# an edge line's center may sit up to 0.35 ft off 12 ft (a 6-in line inside or outside the
# lane edge). The zones themselves are the MUTCD's own (Table 3B-1, Section 3B.02) and are
# graded the same at both levels.
PAIR_SPAN = (0.20, 0.60)
EDGE_TOL_VAGUE = 0.35
RATIO, RATIO_TOL = GAP / DASH, 0.3

#: MAIN 01, pieced together from WFL sheets D.5-D.12 (display stations)
MAIN01_PVIS = ((10400.0, 6280.87), (11100.0, 6266.87, 150.0), (11610.0, 6255.14, 400.0),
               (12350.0, 6247.73, 400.0), (13100.0, 6218.48, 500.0), (14640.0, 6192.30, 800.0),
               (15860.0, 6265.50, 600.0), (16410.0, 6272.65, 100.0), (16540.0, 6273.16, 100.0),
               (16600.0, 6273.74))


@dataclass(frozen=True)
class Job:
    id: str
    start: str
    redraft: str
    sheet_file: str
    sheet: str
    ra: float                       # the striping range
    rb: float
    mph: int
    ali_file: str = "SamplePlan_ali.rdraft"
    refs: Tuple[Tuple[str, str], ...] = (("COR", "SamplePlan_cor.rdraft"),
                                         ("SUR", "SamplePlan_sur.rdraft"))
    alignment: str = "MAIN 01"
    profile: str = "MAIN 01 PGL"
    pvis: Tuple[Tuple[float, ...], ...] = MAIN01_PVIS
    #: what the prompt says the design profile covers beyond the project
    extent: str = "the profile includes the existing road behind the begin of project"

    def folder(self) -> Path:
        return common.REDRAFT_ROOT / self.redraft

    @property
    def psd(self) -> float:
        return float(MUTCD_PSD[self.mph])


D6 = Job(id="p13-striping-wfl15", start="p13-wfl15",
         redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p15",
         sheet_file="SamplePlan_pln_pp2.rdraft", sheet="D.6", ra=11500.0, rb=12250.0, mph=55)
D7 = Job(id="p13-striping-wfl16", start="p13-wfl16",
         redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p16",
         sheet_file="SamplePlan_pln_pp3.rdraft", sheet="D.7", ra=12250.0, rb=13000.0, mph=50)

#: MAIN 01 with the existing road beyond END PROJECT 166+00 carried on at the
#: +0.97% the last design grade ends on (D.12 draws the existing ground running
#: on at that grade past 166+00), to 172+00: the sweeps on D.11 look past 166+00
MAIN01_PVIS_EXT = MAIN01_PVIS + ((17200.0, 6279.54),)
#: CFL CL1 PGL (sample Plan 1, 10+00 to 24+00, see profile.CFL) with the
#: existing road behind BEGIN PROJECT 10+00 on the +0.50% the design begins on,
#: back to 0+00, and the -0.50% it leaves the sheet on carried to 30+00
CFL_PVIS_EXT = ((0.0, 8184.84), (1000.0, 8189.84), (1150.0, 8190.59, 150.0),
                (1600.0, 8183.06, 200.0), (2200.0, 8187.90, 200.0), (2400.0, 8186.90),
                (3000.0, 8183.90))
_BEYOND = ("the profile includes the existing road behind the begin of project and beyond "
           "the end of project")

D8 = Job(id="p13-striping-wfl17", start="p13-wfl17",
         redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p17",
         sheet_file="SamplePlan_pln_pp4.rdraft", sheet="D.8", ra=13000.0, rb=13750.0, mph=65,
         pvis=MAIN01_PVIS_EXT, extent=_BEYOND)
D10 = Job(id="p13-striping-wfl19", start="p13-wfl19",
          redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p19",
          sheet_file="SamplePlan_pln_pp6.rdraft", sheet="D.10", ra=14500.0, rb=15250.0, mph=60,
          pvis=MAIN01_PVIS_EXT, extent=_BEYOND)
D11 = Job(id="p13-striping-wfl20", start="p13-wfl20",
          redraft="WFL/WFL-Plan-Profile-Sheets/WFL-Plan-Profile-Sheets-p20",
          sheet_file="SamplePlan_pln_pp7.rdraft", sheet="D.11", ra=15250.0, rb=16000.0, mph=55,
          pvis=MAIN01_PVIS_EXT, extent=_BEYOND)
CFLPNP = Job(id="p13-striping-cflpnp", start="p13-cflpnp",
             redraft="CFL/CFL-D-Plan-and-Profile", sheet_file="PNP(Sample).rdraft",
             sheet="Plan 1", ra=1000.0, rb=1750.0, mph=55,
             ali_file="ALI(MAIN)Sample.rdraft",
             refs=(("COR", "COR(MAIN)Sample.rdraft"), ("TER", "TERSample.rdraft")),
             alignment="CL1", profile="CL1 PGL", pvis=CFL_PVIS_EXT,
             extent=("the profile includes the existing road behind the begin of project and "
                     "runs on past this sheet"))
NEW_JOBS = [D8, D10, D11, CFLPNP]
JOBS = [D6, D7] + NEW_JOBS

Interval = Tuple[float, float]


# ------------------------------------------------------------------ truth


def _profile(pvis) -> Profile:
    prof = Profile("P", "A", [PVI(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pvis])
    prof.validate()
    return prof


def zones(pvis, psd: float, ra: float, rb: float, eye: float = EYE, obj: float = OBJECT
          ) -> Tuple[List[Interval], List[Interval]]:
    """``(up-station zones, down-station zones)`` within [ra, rb]: see the
    module docstring for the method. Raises if the profile does not reach
    ``psd`` beyond the range both ways."""
    prof = _profile(pvis)
    p0, p1 = prof.station_range()
    lo, hi = max(p0, ra - CONNECT - psd), min(p1, rb + CONNECT + psd)
    n0 = int(math.floor(lo))
    elev = [prof.elevation_at(min(max(float(n0 + i), p0), p1)) for i in range(int(hi) - n0 + 1)]
    n = int(round(psd))
    last = len(elev) - 1

    def hidden(i: int, sign: int) -> Optional[bool]:
        j_end = i + sign * n
        if j_end < 0 or j_end > last:
            return None
        e0 = elev[i] + eye
        steepest = -1e18
        for k in range(1, n + 1):
            g = elev[i + sign * k]
            if (g + obj - e0) / k < steepest - 1e-12:
                return True
            steepest = max(steepest, (g - e0) / k)
        return False

    out = []
    for sign in (1, -1):
        runs: List[Interval] = []
        cur = None
        for i in range(len(elev)):
            st = float(n0 + i)
            if not (ra - CONNECT <= st <= rb + CONNECT):
                continue
            h = hidden(i, sign)
            if h is None:
                if ra <= st <= rb:
                    raise ValueError(f"the profile does not reach {psd:.0f} ft beyond {st:.0f}")
                if cur is not None:
                    runs.append((cur, st - 1.0))
                    cur = None
                continue
            if h and cur is None:
                cur = st
            elif not h and cur is not None:
                runs.append((cur, st - 1.0))
                cur = None
        if cur is not None:
            runs.append((cur, min(rb + CONNECT, float(n0 + len(elev) - 1))))
        joined: List[Interval] = []
        for a, b in runs:
            if joined and a - joined[-1][1] < CONNECT:
                joined[-1] = (joined[-1][0], b)
            else:
                joined.append((a, b))
        out.append([(max(a, ra), min(b, rb)) for a, b in joined if b >= ra and a <= rb])
    return out[0], out[1]


@lru_cache(maxsize=None)
def truth(job: Job) -> Tuple[Tuple[Interval, ...], Tuple[Interval, ...]]:
    up, down = zones(job.pvis, job.psd, job.ra, job.rb)
    return tuple(up), tuple(down)


# ------------------------------------------------------------ intervals


def _union(xs: Sequence[Interval]) -> List[Interval]:
    out: List[Interval] = []
    for a, b in sorted(xs):
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _minus(xs: Sequence[Interval], ys: Sequence[Interval]) -> List[Interval]:
    out = []
    for a, b in xs:
        pieces = [(a, b)]
        for c, d in ys:
            nxt = []
            for p, q in pieces:
                if d <= p or c >= q:
                    nxt.append((p, q))
                    continue
                if c > p:
                    nxt.append((p, c))
                if d < q:
                    nxt.append((d, q))
            pieces = nxt
        out.extend(p for p in pieces if p[1] - p[0] > 1e-6)
    return out


def _shrink(xs: Sequence[Interval], by: float, ra: float, rb: float) -> List[Interval]:
    """Each interval pulled in by ``by`` at an end that is a zone boundary (not
    a range end)."""
    out = []
    for a, b in xs:
        a2 = a if a <= ra + 1e-6 else a + by
        b2 = b if b >= rb - 1e-6 else b - by
        if b2 > a2:
            out.append((a2, b2))
    return out


def _sta(s: float) -> str:
    return format_station(s)


# ---------------------------------------------------------------- reading


def _points(e) -> List[List[float]]:
    """Points along a line, polyline or arc, about every half foot."""
    def seg(a, b):
        n = max(1, int(math.ceil(math.dist(a, b) / 0.5)))
        return [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(n + 1)]
    if e.TYPE == "line":
        return seg(e.start, e.end)
    if e.TYPE == "polyline":
        verts = [list(v) for v in e.vertices]
        if e.closed:
            verts.append(verts[0])
        out = []
        for k, (a, b) in enumerate(zip(verts, verts[1:])):
            bulge = (e.bulges or [0.0] * len(verts))[k] if e.bulges else 0.0
            arc = geo.bulge_arc(a, b, bulge) if bulge else None
            if arc is None:
                out.extend(seg(a, b))
            else:
                c, r, start, sweep = arc
                n = max(1, int(math.ceil(abs(math.radians(sweep)) * r / 0.5)))
                out.extend([c[0] + r * math.cos(math.radians(start + sweep * i / n)),
                            c[1] + r * math.sin(math.radians(start + sweep * i / n))]
                           for i in range(n + 1))
        return out
    if e.TYPE == "arc":
        s, t = geo.arc_sweep(e.start_angle_deg, e.end_angle_deg)
        n = max(1, int(math.ceil(math.radians(t - s) * e.radius / 0.5)))
        return [[e.center[0] + e.radius * math.cos(math.radians(s + (t - s) * i / n)),
                 e.center[1] + e.radius * math.sin(math.radians(s + (t - s) * i / n))]
                for i in range(n + 1)]
    return []


BANDS = {"center": 0.0, "right": PAIR, "left": -PAIR, "edge-right": EDGE, "edge-left": -EDGE}


def _band(offsets: Sequence[float], lenient: bool = False) -> Optional[str]:
    if lenient:   # the vague level: the offsets the MUTCD allows (PAIR_SPAN, EDGE_TOL_VAGUE)
        for name, at in BANDS.items():
            if name == "center":
                fits = all(abs(o) <= BAND_TOL["center"] for o in offsets)
            elif name.startswith("edge"):
                fits = all(abs(o - at) <= EDGE_TOL_VAGUE for o in offsets)
            else:
                side = 1.0 if at > 0 else -1.0
                fits = all(PAIR_SPAN[0] <= side * o <= PAIR_SPAN[1] for o in offsets)
            if fits:
                return name
        return None
    for name, at in BANDS.items():
        tol = BAND_TOL["edge" if name.startswith("edge") else "pair" if at else "center"]
        if all(abs(o - at) <= tol for o in offsets):
            return name
    return None


@dataclass
class Marks:
    bands: Dict[str, List[Interval]]
    strays: List[Tuple[str, float]]

    def solids(self, band: str) -> List[Interval]:
        return [m for m in self.bands.get(band, []) if m[1] - m[0] > SOLID_MIN]

    def dashes(self, band: str) -> List[Interval]:
        return [m for m in self.bands.get(band, []) if m[1] - m[0] <= SOLID_MIN]


def read_marks(job: Job, baseline: Session, submitted: Session, lenient: bool = False) -> Marks:
    """The striping the submission added, as station intervals per band (``lenient``: the
    bands the MUTCD allows, for the vague level)."""
    align = baseline.doc.design.alignments[job.alignment]
    before = set(baseline.doc.model_entities)
    raw: Dict[str, List[Interval]] = {b: [] for b in BANDS}
    strays = []
    for eid, e in submitted.doc.model_entities.items():
        if eid in before or e.TYPE not in ("line", "polyline", "arc"):
            continue
        sts, offs = [], []
        for p in _points(e):
            try:
                r = align.xy_to_station(p)
            except DesignError:
                continue
            sts.append(r["station"])
            offs.append(r["offset"])
        if not sts or max(sts) < job.ra or min(sts) > job.rb:
            continue
        band = _band(offs, lenient)
        if band is None:
            if any(abs(o) <= 0.8 for o in offs):
                strays.append((eid, min(sts)))
            continue
        a, b = max(min(sts), job.ra), min(max(sts), job.rb)
        if b > a:
            raw[band].append((a, b))
    merged = {}
    for band, xs in raw.items():
        out: List[Interval] = []
        for a, b in sorted(xs):
            if out and a <= out[-1][1] + MERGE:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        merged[band] = out
    return Marks(merged, strays)


# ------------------------------------------------------------------ check


def _zone_problem(drawn: List[Interval], want: Sequence[Interval], who: str, job: Job
                  ) -> Optional[str]:
    if len(drawn) != len(want):
        said = ", ".join(f"{_sta(a)} to {_sta(b)}" for a, b in drawn) or "none"
        need = (", ".join(f"{_sta(a)} to {_sta(b)}" for a, b in want)
                or "nowhere on this range")
        return (f"{who}: solid no-passing line drawn {said}; the sight distance puts the "
                f"no-passing zone{'s' if len(want) > 1 else ''} {need}")
    for (a, b), (c, d) in zip(drawn, want):
        for got, need, clipped, end in ((a, c, c <= job.ra + 1e-6, "begins"),
                                        (b, d, d >= job.rb - 1e-6, "ends")):
            off = abs(got - need)
            if clipped:
                off = got - job.ra if end == "begins" else job.rb - got
            if off > ZONE_TOL:
                return (f"{who}: the no-passing zone {end} at {_sta(got)}, the sight distance "
                        f"says {_sta(need)} ({off:.0f} ft off; {ZONE_TOL:.0f} ft allowed)")
    return None


def _dash_problem(dashes: List[Interval], lo: float, hi: float, what: str,
                  lenient: bool = False) -> Optional[str]:
    if hi - lo < DASH + GAP + 5.0:
        return None
    ds = [d for d in dashes if d[1] > lo and d[0] < hi]
    if not ds:
        return f"no broken line on {what} from {_sta(lo)} to {_sta(hi)}"
    inner = [d for d in ds if d[0] >= lo - 1e-6 and d[1] <= hi + 1e-6]
    problem = None
    for d in inner:
        if abs((d[1] - d[0]) - DASH) > DASH_TOL:
            problem = (f"a {d[1] - d[0]:.1f} ft stripe at {_sta(d[0])} on {what} "
                       f"({DASH:.0f}-ft stripes, {GAP:.0f}-ft gaps)")
            break
    for p, q in zip(inner, inner[1:]):
        if problem is None and abs((q[0] - p[1]) - GAP) > GAP_TOL:
            problem = (f"a {q[0] - p[1]:.1f} ft gap at {_sta(p[1])} on {what} "
                       f"({DASH:.0f}-ft stripes, {GAP:.0f}-ft gaps)")
            break
    if problem is None and (ds[0][0] - lo > DASH + GAP or hi - ds[-1][1] > DASH + GAP):
        problem = (f"the broken line on {what} runs {_sta(ds[0][0])} to {_sta(ds[-1][1])}, "
                   f"short of {_sta(lo)} to {_sta(hi)}")
    if problem is not None and lenient:
        return _ratio_problem(ds, inner, lo, hi, what)
    return problem


def _ratio_problem(ds: List[Interval], inner: List[Interval], lo: float, hi: float, what: str
                   ) -> Optional[str]:
    """A broken line read the way the MUTCD allows it (the vague level): one stripe length
    from 10 ft to SOLID_MIN and one gap three times it, kept the length of the region."""
    stripes = sorted(b - a for a, b in inner)
    gaps = sorted(q[0] - p[1] for p, q in zip(inner, inner[1:]))
    stripe = stripes[len(stripes) // 2] if stripes else DASH
    gap = gaps[len(gaps) // 2] if gaps else RATIO * stripe
    if not (DASH - DASH_TOL <= stripe <= SOLID_MIN and abs(gap / stripe - RATIO) <= RATIO_TOL):
        return (f"the broken line on {what} is {stripe:.1f}-ft stripes with {gap:.1f}-ft gaps; "
                f"the MUTCD's is {DASH:.0f}-ft stripes with {GAP:.0f}-ft gaps, or a similar ratio")
    for d in inner:
        if abs((d[1] - d[0]) - stripe) > DASH_TOL:
            return (f"a {d[1] - d[0]:.1f} ft stripe at {_sta(d[0])} on {what}, among "
                    f"{stripe:.1f}-ft stripes")
    for p, q in zip(inner, inner[1:]):
        if abs((q[0] - p[1]) - gap) > GAP_TOL:
            return f"a {q[0] - p[1]:.1f} ft gap at {_sta(p[1])} on {what}, among {gap:.1f}-ft gaps"
    if ds[0][0] - lo > stripe + gap or hi - ds[-1][1] > stripe + gap:
        return (f"the broken line on {what} runs {_sta(ds[0][0])} to {_sta(ds[-1][1])}, "
                f"short of {_sta(lo)} to {_sta(hi)}")
    return None


def _overlap(marks: Sequence[Interval], regions: Sequence[Interval]) -> Optional[Interval]:
    for a, b in marks:
        for c, d in regions:
            if min(b, d) - max(a, c) > 0.5:
                return (max(a, c), min(b, d))
    return None


def make_check(job: Job, lenient: bool = False):
    """The check of ``job``; ``lenient`` is the vague level's, which reads the pair offsets,
    the edge line offsets and the broken-line pattern over the range the MUTCD allows (see
    PAIR_SPAN) and grades the zones exactly as the explicit level does."""
    def check(baseline: Session, submitted: Session) -> Result:
        up, down = truth(job)
        marks = read_marks(job, baseline, submitted, lenient)
        rng = [(job.ra, job.rb)]
        t = Tally()

        for band, side in (("edge-left", "left"), ("edge-right", "right")):
            cover = _cover(marks.bands[band], job.ra, job.rb)
            gaps = _minus(rng, marks.bands[band])
            t.add(f"{side} edge line", None if cover >= 0.995 else
                  f"the {side} edge line ({EDGE:.0f} ft {side} of centerline) covers "
                  f"{cover * 100:.0f}% of {_sta(job.ra)} to {_sta(job.rb)}"
                  f"{'; first gap at ' + _sta(gaps[0][0]) if gaps else ''}")

        t.add("no-passing zone, up-station traffic",
              _zone_problem(marks.solids("right"), up, "up-station traffic (solid right of "
                            "the centerline)", job))
        t.add("no-passing zone, down-station traffic",
              _zone_problem(marks.solids("left"), down, "down-station traffic (solid left of "
                            "the centerline)", job))

        any_zone = _union(list(up) + list(down))
        passing = _minus(rng, any_zone)
        problem = None
        for lo, hi in _shrink(passing, ZONE_TOL, job.ra, job.rb):
            problem = problem or _dash_problem(marks.dashes("center"), lo, hi,
                                               "the centerline (passing both ways)", lenient)
        t.add("broken centerline where passing is allowed", problem)

        problem = None
        for zone_set, other, band in ((up, down, "left"), (down, up, "right")):
            for lo, hi in _shrink(_minus(zone_set, other), ZONE_TOL, job.ra, job.rb):
                problem = problem or _dash_problem(
                    marks.dashes(band), lo, hi,
                    f"the {band} stripe beside the one-direction zone", lenient)
        t.add("broken stripe beside each one-direction zone", problem)

        problem = None
        hit = _overlap(marks.bands["center"], _shrink(any_zone, ZONE_TOL, job.ra, job.rb))
        if hit:
            problem = (f"a centerline stripe at {_sta(hit[0])} to {_sta(hit[1])}, inside a "
                       f"no-passing zone (where the pair of stripes goes instead)")
        solid_center = marks.solids("center")
        if problem is None and solid_center:
            problem = (f"a solid line on the centerline at {_sta(solid_center[0][0])} to "
                       f"{_sta(solid_center[0][1])}")
        open_core = _shrink(passing, ZONE_TOL, job.ra, job.rb)
        for band in ("left", "right"):
            hit = _overlap(marks.bands[band], open_core)
            if problem is None and hit:
                problem = (f"a {band} stripe of a pair at {_sta(hit[0])} to {_sta(hit[1])}, "
                           f"where both directions may pass (one broken centerline there)")
        if problem is None and marks.strays:
            eid, at = marks.strays[0]
            off = f"{PAIR_SPAN[0]:.2f} to {PAIR_SPAN[1]:.2f}" if lenient else f"{PAIR}"
            problem = (f"{eid} near the centerline at {_sta(at)} is not on the centerline or "
                       f"{off} ft off it, so it reads as no stripe")
        t.add("nothing in the wrong zone", problem)

        zs = "; ".join(f"{who} {_sta(a)} to {_sta(b)}" for who, xs in (("up-station", up),
                                                                     ("down-station", down))
                       for a, b in xs)
        return t.result(f"{job.sheet} striped {_sta(job.ra)} to {_sta(job.rb)} at {job.mph} mph "
                        f"(PSD {job.psd:.0f} ft): zones {zs}, broken lines 10/30, edge lines")
    return check


def _cover(xs: Sequence[Interval], lo: float, hi: float) -> float:
    total = sum(b - a for a, b in _union([(max(a, lo), min(b, hi)) for a, b in xs
                                          if min(b, hi) > max(a, lo)]))
    return total / (hi - lo) if hi > lo else 1.0


# ------------------------------------------------------------------ solve


def _layer(session: Session, name: str, color: str) -> str:
    if name not in session.doc.layers:
        common.ok(session.execute("create_layer", {"name": name, "color": color,
                                                   "lineweight_mm": 0.35}))
    return name


def _dashes(session: Session, job: Job, lo: float, hi: float, offset: float, layer: str,
            phase: float) -> None:
    """10-ft stripes from ``lo`` to ``hi`` on the 40-ft cycle that starts at ``phase``."""
    k = math.ceil((lo - phase) / (DASH + GAP) - 1e-9)
    s = phase + k * (DASH + GAP)
    while s + DASH <= hi + 1e-6:
        common.ok(session.execute("draw_station_offset", {
            "alignment": job.alignment, "layer": layer,
            "points": [{"station": s, "offset": offset}, {"station": s + DASH, "offset": offset}]}))
        s += DASH + GAP


def solve_job(job: Job, session: Session, up=None, down=None, swap: bool = False) -> None:
    """Stripe the range through the command bus. The zones come from the
    profile ``get_design_data`` returns, swept with ``zones``; ``up``/``down``
    override them and ``swap`` puts the solid lines on the wrong side, for the
    naive answers the tests check fail."""
    rows = common.ok(session.query("get_design_data", {"kind": "pvis", "profile": job.profile,
                                                       "limit": 200}))["rows"]
    pvis = [(r["station"], r["elevation"], r["length"]) for r in rows]
    z_up, z_down = zones(pvis, float(MUTCD_PSD[job.mph]), job.ra, job.rb)
    up = z_up if up is None else up
    down = z_down if down is None else down
    yellow = _layer(session, "PVMT_STRIPE_YELLOW", "#C8A000")
    white = _layer(session, "PVMT_STRIPE_WHITE", "black")
    common.ok(session.execute("draw_offset", {"alignment": job.alignment, "offsets": [-EDGE, EDGE],
                                              "station_range": [job.ra, job.rb], "layer": white}))
    right, left = (PAIR, -PAIR) if not swap else (-PAIR, PAIR)
    for zs, off in ((up, right), (down, left)):
        for a, b in zs:
            common.ok(session.execute("draw_offset", {"alignment": job.alignment,
                                                      "offsets": [off], "station_range": [a, b],
                                                      "layer": yellow}))
    rng = [(job.ra, job.rb)]
    phase = job.ra
    any_zone = _union(list(up) + list(down))
    for lo, hi in _minus(rng, any_zone):
        _dashes(session, job, lo, hi, 0.0, yellow, phase)
    for zs, other, off in ((up, down, left), (down, up, right)):
        for lo, hi in _minus(zs, other):
            _dashes(session, job, lo, hi, off, yellow, phase)


# ------------------------------------------------------------------ probes


def _prompt(job: Job) -> str:
    return (
        f"Stripe {job.alignment} from {short_station(job.ra)} to {short_station(job.rb)} (sheet "
        f"{job.sheet}), in "
        f"model space. It is a two-lane road with 12-ft lanes. Centerline markings are "
        f"yellow: where passing is allowed in both directions, one broken line on the "
        f"centerline, 10-ft stripes with 30-ft gaps; where it is not, a pair of lines "
        f"{PAIR} ft either side of the centerline, the solid line on the side of the traffic "
        f"the no-passing zone applies to (solid beside broken for one direction, double solid "
        f"for both). White solid edge lines {EDGE:.0f} ft left and right of centerline. Draw "
        f"every stripe as a line along its center, the broken lines as their actual 10-ft "
        f"stripes, not a linetype. Locate the no-passing zones for each direction of travel "
        f"per the MUTCD (2009 edition, Section 3B.02), from the passing sight distance on the "
        f"design profile {job.profile} for an 85th-percentile speed of {job.mph} mph (Table "
        f"3B-1). The clearing "
        f"on the horizontal curves keeps the horizontal sight lines open, so the profile "
        f"governs, and {job.extent}. "
        f"Mark each zone exactly where the sight distance falls short (no stretching to a "
        f"minimum length; join zones less than 400 ft apart).")


def _vague(job: Job) -> str:
    """The vague brief: the job and its data (the line, range and sheet, the lanes, the
    profile, the speed, the clear horizontal sight lines, what the profile covers) and how
    the work is read (stripe centers, real stripes, model space), but not the marking
    pattern, its offsets and colours, or the MUTCD's sections and tables: "per the MUTCD"."""
    return (
        f"Stripe {job.alignment} from {short_station(job.ra)} to {short_station(job.rb)} (sheet "
        f"{job.sheet}) per the MUTCD, centerline and edge lines, in model space. It is a "
        f"two-lane road with {EDGE:.0f}-ft lanes. Place the no-passing zones from the passing "
        f"sight distance on the design profile {job.profile} for an 85th-percentile speed of "
        f"{job.mph} mph; the horizontal sight lines are clear, so the profile governs, and "
        f"{job.extent}. Draw every stripe as a line along its center, the broken lines as "
        f"their actual stripes, not a linetype.")


def _register(job: Job) -> str:
    desc = f"[STRIPING - {_sta(job.ra)} TO {_sta(job.rb)}]"
    return common.register(job.start, job.sheet_file,
                           lambda out: build_host(out, job, job.pvis, job.sheet,
                                                  keep_viewport=True, strip_annotation=False,
                                                  description=desc))


def _probe(job: Job, note: str) -> Probe:
    return Probe(id=job.id, prompt=_prompt(job), check=make_check(job),
                 solve=lambda session, job=job: solve_job(job, session),
                 note=note, tags=["pilot-13", "striping", "sight-distance"], start=job.start,
                 vague=_vague(job), vague_check=make_check(job, lenient=True))


for _job in JOBS:
    _register(_job)

PROBES: List[Probe] = [
    _probe(D6, "WFL sheet D.6, 55 mph, MUTCD PSD 900 ft over the crest at PVI 123+50 (-1.00% to "
               "-3.90%, 400' VC). Expected: up-station no-passing zone 116+60 to 121+29 (solid "
               "right of centerline, broken left), none down-station; broken centerline "
               "elsewhere. Naive double yellow PVC-PVT, the solid on the wrong side, and SSD "
               "object height (2.0 ft) all fail."),
    _probe(D7, "WFL sheet D.7, 50 mph, MUTCD PSD 800 ft, the same crest seen from its far side. "
               "Expected: down-station no-passing zone 125+75 to 129+21 (solid left of "
               "centerline, broken right), none up-station (its zone ends at 121+21 on D.6)."),
    _probe(D8, "WFL sheet D.8, 65 mph, MUTCD PSD 1,100 ft. The sheet's only vertical curve is "
               "the 131+00 sag (-3.90% to -1.70%, 500' VC), which restricts nothing; the zone "
               "comes from the 123+50 crest on D.7, whose down-station zone runs on past "
               "130+00 at this speed. Expected: down-station no-passing zone 130+00 (the range "
               "end) to 132+15 (solid left of centerline, broken right), none up-station; "
               "broken centerline from 132+15 on. Naive answers that fail: no zones (\"only a "
               "sag here\"), the solid on the wrong side, SSD object height (zone to 132+83)."),
    _probe(D10, "WFL sheet D.10, 60 mph, MUTCD PSD 1,000 ft, over the 146+40 sag (-1.70% to "
                "+6.00%, 800' VC) and up the +6.00% grade toward the 158+60 crest bend (+6.00% "
                "to +1.30%, 600' VC, PVC 155+60, off this sheet). Expected: up-station "
                "no-passing zone 149+37 to 152+50 (the range end; solid right of centerline, "
                "broken left), none down-station, broken centerline 145+00 to 149+37. The sag "
                "restricts nothing. Naive answers that fail: no zones, a zone over the sag "
                "(PVC 142+40 to PVT 150+40), SSD object height (zone from 148+72)."),
    _probe(D11, "WFL sheet D.11, 55 mph, MUTCD PSD 900 ft, over the 158+60 crest bend (+6.00% "
                "to +1.30%, 600' VC; no high point). Both directions on one sheet: up-station "
                "no-passing zone 152+50 (the range end) to 158+23 (solid right), down-station "
                "159+39 to 160+00 (the range end; solid left), a broken centerline between. "
                "The up-station sweep looks past END PROJECT 166+00, so the start's profile "
                "carries the existing road on at +0.97% to 172+00. Naive answers that fail: "
                "double yellow PVC 155+60 to the range end, the solids swapped, SSD object "
                "height (158+59 and 159+05), one direction only."),
    _probe(CFLPNP, "CFL sample Plan 1, CL1 10+00 to 17+50, 55 mph, MUTCD PSD 900 ft. The 11+50 "
                   "crest (+0.50% to -1.67%, 150' VC, K 69, high point 11+09.51) restricts only "
                   "the down-station traffic, and only once it is past the crest: expected "
                   "down-station no-passing zone 13+90 to 16+80 (solid left of centerline, "
                   "broken right; it runs across the 16+00 sag), none up-station, broken "
                   "centerline elsewhere. The start's CL1 PGL is the published profile with the "
                   "existing road behind BEGIN PROJECT carried back on +0.50% to 0+00 and the "
                   "-0.50% carried on to 30+00. Naive answers that fail: double yellow over the "
                   "crest (PVC 10+75 to PVT 12+25), the zone on the up-station side, SSD object "
                   "height (13+50 to 17+50)."),
]

__all__ = ["PROBES", "JOBS", "NEW_JOBS", "Job", "zones", "truth", "read_marks", "make_check",
           "solve_job", "MUTCD_PSD"]
