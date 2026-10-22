"""Pilots 1 and 15: the drawing comes as a scan.

Every probe so far hands the model clean data: an alignment in the design
model, a description in the prompt. Real work often starts from paper: an
old plan sheet, a scan of a print. Here the published sheet is rasterized at
200 dpi into the project's ``scans`` folder and served through the opt-in
``view_attachment`` tool (``server_args = ["--attachments", "{project}/scans"]``).
The PDF's text layer does not survive: the PNG is pixels only, so every
number has to be read off the image, and a whole sheet comes back scaled to
1568 px on its long side (3400 px scanned), where 0.10 in lettering is about
nine pixels tall: a 3 and an 8, a 5 and a 6, a minute and a second mark run
together. The model has to zoom (``region`` as fractions of the image) to
read it reliably, and know where on the sheet to look.
Nothing the model can open holds the answers as text: the redraft sheet file,
which letters the same numbers, is not copied into the project, and the
target alignment's own lettering is stripped from the base file.

* **p01 -- redraw an alignment from a scanned sheet.** The start is the
  sheet's base file with one alignment cut out of it: its design deleted, its
  centerline linework, stationing and bearing text removed, and the small
  strokes the redraft digitized beside it (lettering and curve point circles
  that came in as linework, some of it in the topo file) taken out of every
  base file. The corridor and the other alignments stay. The model reads the tangent bearings, the curve
  data and the curve point stations off the scan, rebuilds the alignment in
  the base file under its own name and draws it. What makes it hard: the
  numbers are scattered over the sheet in lettering at two or three angles
  (L-1 letters TB1's BC and EC stations vertically, its curve data in a table
  across the sheet, the second tangent's bearing on the far side of the
  curve); the curve's direction is drawn, not lettered (L-1), or lettered only
  as "(RT)" (sheet 12); the alignment has to be tied in where the prompt or
  the sheet says, which on L-1 means working back from a POT tie to the D13
  line ("TB1" 647+73.40 POT = 63.32' Rt "D13" 647+73.40 POT) to a begin point
  417.16 ft back along a tangent that starts off the sheet; and on sheet 12
  the published state-plane coordinates do not apply (the file is on a local
  datum, which the prompt gives) and the bearing out of the curve is lettered
  nowhere -- it is the bearing in turned by the curve's delta.

  Graded against the design the sheet states, held where the tie puts it.
  The redraft's own alignments were fitted to the drawn linework (its L-1
  TB1 has R 3243 ft and its BC at 642+81.10 against the lettered 3280' and
  642+81.23; its sheet-12 CL1 has R 878.86 against 881.00), so they are good
  to a few tenths of a foot in position but not to the lettered stations; the
  truth is instead the lettered data -- bearings to the second, lengths and
  stations to the hundredth -- built by the engine from the tie, which the
  test holds to within 0.3 ft of the redraft's alignment everywhere the sheet
  shows it. Items: the alignment exists (by name, or the one new alignment);
  it covers the stretch asked for; each tangent's bearing within 2"; each
  curve's radius (L-1's table letters 3280', a 1000 m radius rounded to the
  foot -- its T 82.03 and L 164.02 are those of R 3280.83 -- so 3279.5 to
  3281.5 passes), direction and delta within 3"; the curve's PC and PT
  stations within 0.10 ft of the lettered ones; every 25 ft over the stretch,
  and at the curve points, within 0.10 ft of the truth; and centerline
  linework added along it (0.5 ft). 0.10 ft is what the lettered data allows:
  a radius rounded to the foot moves L-1's stations 0.04 ft and nothing else
  moves them more than a hundredth, while a bearing misread by a minute
  moves a 400 ft tangent's end 0.12 ft and a tie misread by a foot fails
  everywhere.

* **p15 -- plan reading.** The start is a blank document and the scan. The
  prompt asks six questions a reviewer asks of a sheet before using it --
  a radius, a curve point station, a bearing, a title block entry, a value
  that has to be worked out from two lettered ones (an EC that is off the
  sheet, a PT that is not lettered, the tangent between two curves) and on
  one sheet something the scan does not show plainly (the quadrant letter of
  a bearing cut off by the edge of the plan, a scale given only as a bar).
  The model records each answer with ``set_meta {"updates": {"q1": ...}}``.
  Graded exactly after the spelling is normalized: stations, lengths and
  coordinates to the last place lettered (``654+06.40``, ``5,000'`` and
  ``5000 ft`` are the same), bearings and angles to the second (``N 00°03'30" E``
  and ``N00-03-30E`` are the same; the quadrant must be right), the turn of a
  curve where asked, text with spaces and case ignored. The truth is read
  from the redraft documents in the repository by the check (the sheet file's
  lettering and title block, the base files' bearing text, the viewport's
  scale), and derived values are computed from them there.

The two need images to reach the model: the claude-code and codex backends
pass MCP image content through themselves, the anthropic backend only with
``--vision``, and the openai-compatible backend (LM Studio, Runpod) never.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.design.horizontal import Alignment, CurveElement, TangentElement
from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Polyline, Text
from roaddraft.probes import notation as nt
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.drafting import added, covered, run
from roaddraft.probes.pilot import common

#: where the scans go in the project, and the server option that serves them
SCANS = "scans"
SERVER_ARGS = ["--attachments", "{project}/" + SCANS]
#: scan resolution: a 17 x 11 in print comes out 3400 x 2200 px
DPI = 200

POS_FT = 0.10          # the rebuilt alignment against the truth, at every check station
STATION_FT = 0.10      # a curve point's station against the lettered one
BEARING_SEC = 2.0      # a tangent's bearing against the lettered one
DELTA_SEC = 3.0        # a curve's delta against the lettered one
SAMPLE_FT = 25.0       # check stations along the stretch


def _scan(out: Path, sheet_id: str, name: str) -> Path:
    """The published sheet as a scan: pixels only, no text layer."""
    return common.rasterize(common.source_pdf(sheet_id), Path(out) / SCANS / name, dpi=DPI)


def _azimuth(bearing: str) -> float:
    found = nt.bearings(bearing)
    if not found:
        raise ValueError(f"not a bearing: {bearing!r}")
    return found[0]


def _dms(text: str) -> float:
    found = nt.angles(text)
    if not found:
        raise ValueError(f"not an angle: {text!r}")
    return found[0]


def _arc_sec(a: float, b: float) -> float:
    """Difference of two directions in arc seconds, either way round the circle."""
    return abs((a - b + 180.0) % 360.0 - 180.0) * 3600.0


def _step(p: Sequence[float], azimuth: float, dist: float) -> List[float]:
    a = math.radians(azimuth)
    return [p[0] + dist * math.sin(a), p[1] + dist * math.cos(a)]


def _sta(raw: float) -> str:
    """``64281.23`` -> ``642+81.23``."""
    hundreds = int(math.floor(round(raw, 2) / 100.0))
    return f"{hundreds}+{round(raw, 2) - hundreds * 100.0:05.2f}"


def _norm_name(name: str) -> str:
    return re.sub(r"[\s\"'“”]", "", name or "").upper()


# ======================================================================= p01


@dataclass
class Curve:
    """A curve as the sheet letters it."""
    label: str                     # "curve 2", for the items
    pc: float                      # lettered PC (BC) station
    pt: float                      # lettered PT (EC) station
    radius: Tuple[float, float]    # the radii that pass
    delta: str                     # lettered delta
    turn: str                      # "L" | "R"
    words: Tuple[str, str] = ("PC", "PT")


@dataclass
class Redraw:
    """One redraw-from-scan instance."""
    id: str
    sheet: str                     # redraft id
    design_file: str               # the base file the alignment is cut out of (the start)
    alignment: str                 # the alignment cut out and rebuilt
    aliases: Tuple[str, ...]       # other names the rebuilt line may go by
    scan: str                      # the scan's file name
    begin_by: float                # the rebuilt line begins at or before this station
    end_by: float                  # ... and ends at or after this one
    tangents: List[Tuple[float, str]]   # (a station on the tangent, the lettered bearing)
    curves: List[Curve]
    truth: Callable[[Session], Alignment]   # the lettered design held at the tie
    layer: str                     # where the solution draws the centerline
    prompt: str = ""
    note: str = ""
    solve: Optional[Callable[[Session], None]] = None


def _engine_alignment(name: str, start, legs: list, begin_station: float) -> Alignment:
    """An alignment from start + legs, built by the engine itself."""
    s = Session(project_name="truth")
    common.ok(s.execute("create_alignment", {"name": name, "start": [float(v) for v in start],
                                             "legs": legs, "begin_station": begin_station}))
    return s.doc.design.alignments[name]


def _vertices(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [list(e.start), list(e.end)]
    if isinstance(e, Polyline):
        return [list(v) for v in e.vertices]
    return []


def _traces(session: Session, path: Sequence[Sequence[float]], trace_ft: float = 13.0,
            glyph_ft: float = 8.0) -> List[str]:
    """Small loose linework hugging a path: lettering the redraft digitized as
    strokes and curve points it drew as little circles (L-1's "N 01°05'14\" W",
    "328.15'" and the quotes of "TB1" LINE, partly in the design file and
    partly in the topo file; its BC and POT circles)."""
    out = []
    for eid, e in session.doc.model_entities.items():
        pts = _vertices(e)
        if not pts or getattr(e, "anchor", None):
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(max(xs) - min(xs), max(ys) - min(ys)) > glyph_ft:
            continue
        if all(min(math.dist(p, q) for q in path) <= trace_ft for p in pts):
            out.append(eid)
    return out


def _strip_alignment(session: Session, name: str, others: Sequence[Session] = (),
                     reach_ft: float = 30.0) -> None:
    """Cut an alignment out of its base file: the design, everything anchored to
    it (centerline, ticks, station numbers), the loose lettering beside it that
    is its own -- its bearings and its name -- so nothing in the file holds its
    data as text, and (here and in the ``others``) the small strokes hugging it."""
    align = session.doc.design.alignments[name]
    path = [align.point_at(align.length * i / 400.0) for i in range(401)]
    gone = set(_traces(session, path))
    for eid, e in session.doc.model_entities.items():
        anchor = getattr(e, "anchor", None) or {}
        if anchor.get("alignment") == name:
            gone.add(eid)
        elif isinstance(e, Text) and not anchor:
            c = e.content.strip()
            own = (name.upper() in c.upper() or re.search(r"\d+\s*°\s*\d+", c)
                   or re.fullmatch(r"[NSEW]", c))
            if own and min(math.dist(e.position, q) for q in path) <= reach_ft:
                gone.add(eid)
    if gone:
        common.ok(session.execute("delete_entities", {"ids": sorted(gone)}))
    common.ok(session.execute("delete_alignment", {"name": name, "cascade": True}))
    for other in others:
        strokes = _traces(other, path)
        if strokes:
            common.ok(other.execute("delete_entities", {"ids": strokes}))


def _redraw_builder(spec: Redraw):
    def build(out: Path) -> Path:
        files = common.stage(out, spec.sheet)
        # the sheet file letters the alignment's data as text: it does not go
        sheet = files.pop(common.sheet_file(spec.sheet))
        sheet.unlink()
        doc = files[spec.design_file]
        session = common.load(doc)
        others = {path: common.load(path) for fname, path in files.items()
                  if fname != spec.design_file}
        _strip_alignment(session, spec.alignment, list(others.values()))
        common.save(session, doc)
        for path, other in others.items():
            common.save(other, path)
        _scan(out, spec.sheet, spec.scan)
        return doc
    return build


def _rebuilt(baseline: Session, submitted: Session, spec: Redraw):
    """``(alignment, problem)``: the line the model rebuilt, by name or as the
    one alignment the start did not have."""
    aligns = submitted.doc.design.alignments
    wanted = {_norm_name(n) for n in (spec.alignment,) + spec.aliases}
    named = [a for key, a in aligns.items() if _norm_name(key) in wanted]
    if named:
        return named[0], None
    new = [a for key, a in aligns.items() if key not in baseline.doc.design.alignments]
    if len(new) == 1:
        return new[0], None
    if new:
        return None, (f"no alignment named {spec.alignment}, and {len(new)} new ones "
                      f"({', '.join(sorted(a.name for a in new))}): which is it?")
    return None, f"no alignment {spec.alignment} in the design model (it has {sorted(aligns)})"


def _display(align: Alignment, raw: float) -> float:
    return align.stations().to_display(raw)[0]


def _raw(align: Alignment, display: float) -> Optional[float]:
    try:
        raw = align.stations().to_raw(display)
    except Exception:
        return None
    if raw < align.begin_station - 1e-6 or raw > align.end_station + 1e-6:
        return None
    return raw


def _curve_at(align: Alignment, display: float) -> Optional[CurveElement]:
    raw = _raw(align, display)
    if raw is None:
        return None
    i, _s = align.element_at(raw - align.begin_station)
    e = align.elements[i]
    return e if isinstance(e, CurveElement) else None


def _check_redraw(spec: Redraw):
    def check(baseline: Session, submitted: Session) -> Result:
        t = Tally()
        truth = spec.truth(baseline)
        found, problem = _rebuilt(baseline, submitted, spec)
        t.add(f"the alignment {spec.alignment}, rebuilt", problem)
        span = f"it runs {_sta(spec.begin_by)} to {_sta(spec.end_by)}"
        tangent_items = [f"tangent bearing {b}" for _s, b in spec.tangents]
        curve_items = [(f"{c.label}: R {c.radius[0]:g}-{c.radius[1]:g} ft, "
                        f"{'right' if c.turn == 'R' else 'left'}, delta {c.delta}",
                        f"{c.label}: {c.words[0]} {_sta(c.pc)} and {c.words[1]} {_sta(c.pt)}")
                       for c in spec.curves]
        held = f"on its tie: within {POS_FT} ft of the lettered design every {SAMPLE_FT:g} ft"
        drawn = "its centerline drawn"
        if found is None:
            for item in [span] + tangent_items + [i for pair in curve_items for i in pair] + [held, drawn]:
                t.add(item, problem)
            return t.result("")
        name = found.name
        begin = _display(found, found.begin_station)
        end = _display(found, found.end_station)
        t.add(span, None if begin <= spec.begin_by + 0.01 and end >= spec.end_by - 0.05 else
              f"{name} runs {_sta(begin)} to {_sta(end)}; the sheet shows it from "
              f"{_sta(spec.begin_by)} to {_sta(spec.end_by)}")
        for (station, bearing), item in zip(spec.tangents, tangent_items):
            raw = _raw(found, station)
            if raw is None:
                t.add(item, f"{name} does not reach {_sta(station)}, on the {bearing} tangent")
                continue
            dist = raw - found.begin_station
            i, _s = found.element_at(dist)
            if not isinstance(found.elements[i], TangentElement):
                t.add(item, f"{name} is curving at {_sta(station)}, on the {bearing} tangent")
                continue
            az = (90.0 - found.direction_at(dist)) % 360.0
            off = _arc_sec(az, _azimuth(bearing))
            t.add(item, None if off <= BEARING_SEC else
                  f"{name} runs at azimuth {az:.5f} at {_sta(station)}, {off:.0f}\" off {bearing}")
        for c, (shape_item, points_item) in zip(spec.curves, curve_items):
            mid = (c.pc + c.pt) / 2.0
            el = _curve_at(found, mid)
            if el is None:
                why = f"{name} has no curve at {_sta(mid)}, the middle of {c.label}"
                t.add(shape_item, why)
                t.add(points_item, why)
                continue
            delta_off = abs(el.delta_deg - _dms(c.delta)) * 3600.0
            shape = []
            if not c.radius[0] <= el.radius <= c.radius[1]:
                shape.append(f"R {el.radius:.2f} ft")
            if el.direction != c.turn:
                shape.append(f"turns {'right' if el.direction == 'R' else 'left'}")
            if delta_off > DELTA_SEC:
                shape.append(f"delta {el.delta_deg:.5f} deg ({delta_off:.0f}\" off)")
            t.add(shape_item, f"{c.label} in {name}: {', '.join(shape)}" if shape else None)
            pc = _display(found, found.begin_station + el.start_dist)
            pt = _display(found, found.begin_station + el.end_dist)
            miss = [f"{word} at {_sta(got)} ({got - want:+.2f} ft)"
                    for word, got, want in ((c.words[0], pc, c.pc), (c.words[1], pt, c.pt))
                    if abs(got - want) > STATION_FT]
            t.add(points_item, f"{c.label} in {name}: {', '.join(miss)}" if miss else None)
        # positions, station by station, against the lettered design held at the tie
        lo, hi = max(spec.begin_by, begin), min(spec.end_by, end)
        stations = [lo + (hi - lo) * k / max(1, int(math.ceil((hi - lo) / SAMPLE_FT)))
                    for k in range(int(math.ceil((hi - lo) / SAMPLE_FT)) + 1)] if hi > lo else []
        stations += [s for c in spec.curves for s in (c.pc, c.pt) if lo <= s <= hi]
        worst = (0.0, None)
        for s in stations:
            raw = _raw(found, s)
            if raw is None:
                continue
            got = found.station_to_xy(raw)[0]
            want = truth.station_to_xy(truth.stations().to_raw(s))[0]
            d = math.dist(got, want)
            if d > worst[0]:
                worst = (d, s, got, want)
        if not stations:
            t.add(held, f"{name} does not overlap {_sta(spec.begin_by)} to {_sta(spec.end_by)}")
        else:
            t.add(held, None if worst[0] <= POS_FT else
                  f"{name} at {_sta(worst[1])} is at [{worst[2][0]:.2f}, {worst[2][1]:.2f}], "
                  f"{worst[0]:.2f} ft from [{worst[3][0]:.2f}, {worst[3][1]:.2f}] where the "
                  f"sheet's data puts it from the tie")
        # the centerline: added linework along the line it rebuilt
        r0, r1 = _raw(found, lo), _raw(found, hi)
        if r0 is None or r1 is None or r1 <= r0:
            t.add(drawn, f"{name} does not cover the stretch to draw")
        else:
            pts = [found.station_to_xy(r0 + (r1 - r0) * k / 40.0)[0] for k in range(41)]
            t.add(drawn, covered(submitted, added(baseline, submitted), pts,
                                 f"the {name} centerline"))
        return t.result(f"{name} rebuilt from the scan: on its tie, its bearings, curve data "
                        f"and curve point stations as lettered, and drawn")
    return check


# ---------------------------------------------------------- L-1, the TB1 line

#: Caltrans layout L-1 (PPM-045): "TB1" as lettered. N 03°57'06" W 417.16' to
#: the BC at 642+81.23; curve 2 of the CURVE DATA table, R 3280' (a 1000 m
#: radius: its T 82.03 and L 164.02 are R 3280.83's), delta 02°51'52", turning
#: right (drawn, not lettered); the EC at 644+45.25; N 01°05'14" W 328.15' to
#: "TB1" 647+73.40 POT = 63.32' Rt "D13" 647+73.40 POT.
TB1 = {"b1": "N 03°57'06\" W", "l1": 417.16, "bc": 64281.23, "ec": 64445.25,
       "radius": 1000.0 * 3937.0 / 1200.0, "delta": "02°51'52\"",
       "b2": "N 01°05'14\" W", "l2": 328.15, "pot": 64773.40, "tie": 63.32}


def _tb1_pot(session: Session) -> List[float]:
    r = common.ok(session.query("station_to_xy", {"alignment": "D13", "station": TB1["pot"],
                                                  "offset": TB1["tie"]}))
    return r["point"]


def _tb1_truth(baseline: Session) -> Alignment:
    az1, az2 = _azimuth(TB1["b1"]), _azimuth(TB1["b2"])
    delta = abs((az2 - az1 + 180.0) % 360.0 - 180.0)
    T = TB1["radius"] * math.tan(math.radians(delta) / 2.0)
    ec = _step(_tb1_pot(baseline), az2, -TB1["l2"])
    pi = _step(ec, az2, -T)
    start = _step(pi, az1, -(TB1["l1"] + T))
    return _engine_alignment("TB1", start,
                             [{"bearing": TB1["b1"], "distance": TB1["l1"] + T},
                              {"bearing": TB1["b2"], "distance": T + TB1["l2"],
                               "radius": TB1["radius"]}],
                             TB1["bc"] - TB1["l1"])


def _tb1_solve(session: Session) -> None:
    """Work back from the POT tie to the begin point with the traverse query,
    then lay TB1 out by bearings and distances and draw it."""
    pot = _tb1_pot(session)
    T = 82.03                      # the table's T; the engine fits the curve at the PI
    r = common.ok(session.query("traverse", {"start": pot, "legs": [
        {"bearing": "S 01°05'14\" E", "distance": TB1["l2"] + T},
        {"bearing": "S 03°57'06\" E", "distance": T + TB1["l1"]}]}))
    begin = r["points"][-1]
    run(session, "create_alignment", {
        "name": "TB1", "start": begin, "begin_station": "638+64.07",
        "legs": [{"bearing": TB1["b1"], "distance": TB1["l1"] + T},
                 {"bearing": TB1["b2"], "distance": T + TB1["l2"], "radius": 3280.83}]})
    run(session, "draw_alignment", {"alignment": "TB1", "layer": "V-ALIGN-CNTR"})


TB1_SPEC = Redraw(
    id="p01-redraw-alignment-ppm045",
    sheet="PPM-045", design_file="0000000000aa01.rdraft", alignment="TB1", aliases=(),
    scan="L-1-scan.png",
    begin_by=63900.00, end_by=TB1["pot"],
    tangents=[(64050.00, TB1["b1"]), (64600.00, TB1["b2"])],
    curves=[Curve("curve 2", TB1["bc"], TB1["ec"], (3279.5, 3281.5), TB1["delta"], "R",
                  ("BC", "EC"))],
    truth=_tb1_truth, layer="V-ALIGN-CNTR",
    prompt=(
        "We lost the \"TB1\" line (the NB entrance ramp from Twelve Bridges Drive) out of the "
        "roadway design file you have open, 0000000000aa01.rdraft. All we have to go on is a "
        "scan of layout sheet L-1, L-1-scan.png: look at it with view_attachment, and zoom in "
        "with region to read the lettering. Rebuild TB1 in this file from the alignment data "
        "lettered on the sheet (the tangent bearings and lengths, the curve data, the curve "
        "point stations) over the whole length of it the sheet shows, name it TB1, and draw "
        "it. The D13 line is still in the file: hold the tie the sheet gives between TB1's "
        "end and D13. The proposed roadway linework is still there too, if you want to check "
        "your work against it."),
    note=("TB1's design, centerline, stationing and bearing/name text cut out of AA01 and the "
          "sheet file left out of the project. Expected: N 03°57'06\" W to BC 642+81.23, curve 2 "
          "(R 3280', delta 02°51'52\", right -- drawn, not lettered), EC 644+45.25, "
          "N 01°05'14\" W 328.15' to the POT at 647+73.40, held 63.32 ft right of D13 "
          "647+73.40; the begin point is 417.16 ft back from the BC, off the sheet. Naive "
          "wrong answers that fail: the line 1 ft off the tie (placed by eye on the ramp "
          "linework); the tie read as 63.32' Lt; the second bearing read N 01°05'41\" W. The "
          "table's rounded R 3280' still passes."),
    solve=_tb1_solve,
)


# ----------------------------------------------------- sheet 12, the SR 61 line

#: FDOT roadway plan-profile sheet 12: SR 61 (CL1) as lettered. N59°59'28"W
#: from STA 700+00.00 (= STA 32+90.00 SR 30) through BEGIN PROJECT 700+23.62;
#: CURVE DATA: PI 709+72.30, delta 49°03'08" (RT), R 881.00, T 401.98, L 754.24,
#: PC 705+70.32, PT 713+24.57. The tie is the redraft's CL1 at 700+00.00, on
#: its local datum (the test holds the prompt's figures to it).
CL1 = {"tie": [10300.67, 9820.83], "begin": 70000.00, "bearing": "N 59°59'28\" W",
       "pi": 70972.30, "delta": "49°03'08\"", "radius": 881.00, "pc": 70570.32, "pt": 71324.57}


def _cl1_truth(_baseline: Session) -> Alignment:
    az_in = _azimuth(CL1["bearing"])
    return _engine_alignment("CL1", CL1["tie"],
                             [{"bearing": CL1["bearing"], "distance": CL1["pi"] - CL1["begin"]},
                              {"azimuth": (az_in + _dms(CL1["delta"])) % 360.0,
                               "distance": 600.0, "radius": CL1["radius"]}],
                             CL1["begin"])


def _cl1_solve(session: Session) -> None:
    run(session, "create_alignment", {
        "name": "CL1", "start": CL1["tie"], "begin_station": "700+00.00",
        "legs": [{"bearing": CL1["bearing"], "distance": 972.30},
                 {"deflection": "49°03'08\" RT", "distance": 401.98 + 200.0, "radius": 881.00}]})
    run(session, "draw_alignment", {"alignment": "CL1", "layer": "P_ALIGN"})


CL1_SPEC = Redraw(
    id="p01-redraw-alignment-fdot915",
    sheet="FDOT-915-1-Roadway-Plan-Profile", design_file="ALGNRD01.rdraft", alignment="CL1",
    aliases=("SR61", "SR 61", "SR61CL", "CLCONSTSR61"),
    scan="sheet-12-scan.png",
    begin_by=CL1["begin"], end_by=CL1["pt"],
    tangents=[(70300.00, CL1["bearing"])],
    curves=[Curve("the curve", CL1["pc"], CL1["pt"], (880.5, 881.5), CL1["delta"], "R")],
    truth=_cl1_truth, layer="P_ALIGN",
    prompt=(
        "Our alignment file ALGNRD01.rdraft (open) has lost the SR 61 construction "
        "centerline, CL1. SR 30's centerline, CL2, is still in it, and the proposed roadway "
        "linework is in DSGNRD01.rdraft beside it. What we have is a scan of roadway "
        "plan-profile sheet 12, sheet-12-scan.png: look at it with view_attachment, and zoom "
        "in with region to read the lettering. Rebuild CL1 in this file from what the sheet "
        "letters (the tangent bearing, the curve data, the stations) from station 700+00.00 "
        "at SR 30 through the end of the curve, name it CL1, and draw it. This file is on a "
        "local datum, not state plane: SR 61 station 700+00.00 is at N 9820.83, E 10300.67."),
    note=("CL1's design, centerline, stationing and bearing text cut out of ALGNRD01 and the "
          "sheet file left out of the project. Expected: N 59°59'28\" W from the given tie at "
          "700+00.00 to the PC 705+70.32, the curve R 881.00 turning right through 49°03'08\" "
          "to the PT 713+24.57 (the bearing out, N 10°56'20\" W, is lettered nowhere). Naive "
          "wrong answers that fail: the curve turned left; the line started at BEGIN PROJECT "
          "700+23.62 on the tie point."),
    solve=_cl1_solve,
)


# ======================================================================= p15


@dataclass
class Question:
    key: str                       # q1 ...
    ask: str                       # as the prompt puts it
    kind: str                      # station | feet | bearing | angle | turn-angle | text | scale | number
    truth: Callable[["Sources"], object]
    places: int = 2                # decimals a number is held to


class Sources:
    """The redraft documents of a sheet, read from the repository: the sheet's
    lettering (paper inches) and title block, the base files' loose text."""

    def __init__(self, sheet_id: str):
        self.folder = common.folder(sheet_id)
        self.doc = common.document(self.folder / common.sheet_file(sheet_id))
        self.sheet = list(self.doc.sheets.values())[0]
        self.texts = [e for e in self.sheet.entities.values() if isinstance(e, Text)]
        self.bases: Dict[str, Document] = {
            p.name: common.document(p) for p in sorted(self.folder.glob("*.rdraft"))
            if p.name != common.sheet_file(sheet_id)}

    def base_texts(self) -> List[Text]:
        return [e for doc in self.bases.values() for e in doc.model_entities.values()
                if isinstance(e, Text)]

    def one(self, pattern: str) -> Text:
        hits = [t for t in self.texts if re.search(pattern, t.content)]
        if len(hits) != 1:
            raise LookupError(f"{len(hits)} texts match {pattern!r} on {self.sheet.name}")
        return hits[0]

    def nearest(self, pattern: str, to: Text) -> Text:
        hits = [t for t in self.texts if re.search(pattern, t.content)]
        if not hits:
            raise LookupError(f"no text matches {pattern!r} on {self.sheet.name}")
        return min(hits, key=lambda t: math.dist(t.position, to.position))

    def fpi(self) -> float:
        return float(self.sheet.viewports[0].feet_per_inch)


def _number(text: str) -> float:
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text.replace(" ", ""))
    if not m:
        raise ValueError(f"no number in {text!r}")
    return float(m.group(0).replace(",", ""))


def _curve_table(src: Sources) -> Dict[str, List[str]]:
    """A Caltrans CURVE DATA table read from its lettering: ``{No.: [R, Δ, T, L]}``."""
    title = src.one(r"^CURVE DATA$")
    head = src.nearest(r"^No\.$", title)
    cells = [t for t in src.texts if head.position[0] - 0.5 <= t.position[0] <= head.position[0] + 8.0
             and title.position[1] - 3.0 <= t.position[1] < head.position[1] - 0.1]
    rows: List[List[Text]] = []
    for t in sorted(cells, key=lambda t: -t.position[1]):
        if rows and abs(rows[-1][0].position[1] - t.position[1]) <= 0.05:
            rows[-1].append(t)
        else:
            rows.append([t])
    table = {}
    for row in rows:
        row.sort(key=lambda t: t.position[0])
        table[row[0].content.strip()] = [t.content for t in row[1:]]
    return table


def _curve_block(src: Sources, pi_station: str) -> Dict[str, str]:
    """An FLH curve data block lettered as label/value pairs under its PI
    station (``R =`` | ``855.00'``): ``{"R": "855.00'", ...}``."""
    pi = src.one(r"^" + re.escape(pi_station) + r"$")
    block = {}
    for label in src.texts:
        m = re.fullmatch(r"\s*(R|T|L|Δ)\s*=\s*", label.content)
        if not m or not (0.0 < pi.position[1] - label.position[1] < 0.8
                         and abs(label.position[0] - pi.position[0]) < 0.5):
            continue
        value = min((t for t in src.texts if t is not label
                     and abs(t.position[1] - label.position[1]) < 0.02
                     and 0.0 < t.position[0] - label.position[0] < 1.0),
                    key=lambda t: t.position[0] - label.position[0])
        block[m.group(1)] = value.content
    return block


def _split_bearings(src: Sources) -> List[Tuple[str, Text]]:
    """Bearings lettered in pieces (``S71°44`` + ``'`` + ``22"E``), joined."""
    out = []
    for head in src.texts:
        if not re.fullmatch(r"[NS]\d{1,2}°\d{1,2}", head.content.strip()):
            continue
        tail = min((t for t in src.texts if re.fullmatch(r"\d{1,2}(?:\.\d+)?\"[EW]", t.content.strip())),
                   key=lambda t: math.dist(t.position, head.position))
        if math.dist(tail.position, head.position) < 1.0:
            out.append((f"{head.content.strip()}'{tail.content.strip()}", head))
    return out


# ---------------------------------------------------------------- answers


def _turn(text: str) -> Optional[str]:
    m = re.search(r"\b(RT|LT|RIGHT|LEFT|R|L)\b", text.upper().replace("(", " ").replace(")", " "))
    return None if not m else m.group(1)[0]


def _graded(q: Question, want, got: Optional[str]) -> Optional[str]:
    """None when the answer is the truth, after the spelling is normalized."""
    if got is None or not str(got).strip():
        return f"{q.key} unanswered"
    got = str(got)
    try:
        if q.kind == "station":
            found = nt.stations(got)
            value = found[0][0] if found else _number(got)
            ok = abs(value - want) <= 0.5 * 10 ** -q.places + 1e-9
            shown = _sta(want)
        elif q.kind in ("feet", "number"):
            value = _number(got)
            ok = abs(value - want) <= 0.5 * 10 ** -q.places + 1e-9
            shown = f"{want:.{q.places}f}"
        elif q.kind == "bearing":
            found = nt.bearings(got)
            ok = bool(found) and _arc_sec(found[0], _azimuth(want)) <= 0.5
            shown = want
        elif q.kind in ("angle", "turn-angle"):
            angle, turn = want if q.kind == "turn-angle" else (want, None)
            found = nt.angles(got)
            ok = bool(found) and abs(found[0] - _dms(angle)) * 3600.0 <= 0.5
            if turn:
                ok = ok and _turn(nt.DMS_RE.sub(" ", got)) == turn
            shown = angle + (f" {turn}T" if turn else "")
        elif q.kind == "text":
            def norm(s: str) -> str:
                return re.sub(r"\s+", "", s.upper().replace("’", "'"))
            ok = norm(want) in norm(got)
            shown = want
        elif q.kind == "scale":
            text = got.replace(",", "")
            ratio = re.search(r"1\s*:\s*(\d+(?:\.\d+)?)", text)
            if ratio:
                value = float(ratio.group(1)) / 12.0
            else:
                after = re.search(r"=\s*(\d+(?:\.\d+)?)", text)
                nums = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", text)]
                value = float(after.group(1)) if after else max(nums) if nums else float("nan")
            ok = abs(value - want) <= 0.01
            shown = f"1\" = {want:g}'"
        else:
            raise ValueError(f"unknown question kind {q.kind}")
    except (ValueError, IndexError):
        ok, shown = False, str(want)
    return None if ok else f"{q.key}: {got!r}, not {shown}"


@dataclass
class Reading:
    """One plan-reading instance."""
    id: str
    sheet: str
    scan: str
    kind: str                      # what the sheet is, for the prompt
    questions: List[Question]
    answers: Dict[str, str]        # the scripted solution's answers, as a reviewer writes them
    note: str = ""
    doc: str = "plan-check.rdraft"

    @property
    def prompt(self) -> str:
        asks = " ".join(f"{q.key}: {q.ask}" for q in self.questions)
        keys = ", ".join(f'"{q.key}": ...' for q in self.questions)
        return (f"Before we use it, check what this scanned {self.kind} says. The scan is "
                f"{self.scan}: look at it with view_attachment, and zoom in with region to read "
                f"the lettering. Answer each question below and record the answers in the open "
                f"document with set_meta {{\"updates\": {{{keys}}}}}, each answer the value "
                f"alone: stations as 123+45.67, bearings as N 12°34'56\" E, lengths in feet. "
                f"{asks}")


def _reading_builder(spec: Reading):
    def build(out: Path) -> Path:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        session = Session(project_name="Plan check")
        doc = common.save(session, out / spec.doc)
        _scan(out, spec.sheet, spec.scan)
        return doc
    return build


def _check_reading(spec: Reading):
    def check(baseline: Session, submitted: Session) -> Result:
        src = Sources(spec.sheet)
        given = {k.lower(): v for k, v in common.answers(submitted).items()}
        t = Tally()
        for q in spec.questions:
            want = q.truth(src)
            shown = want if not isinstance(want, tuple) else " ".join(want)
            if isinstance(want, float):
                shown = _sta(want) if q.kind == "station" else f"{want:.{q.places}f}"
            t.add(f"{q.key} {q.ask} -- {shown}", _graded(q, want, given.get(q.key)))
        return t.result(f"all {len(spec.questions)} answers read right off the scan")
    return check


def _reading_solve(spec: Reading):
    def solve(session: Session) -> None:
        run(session, "set_meta", {"updates": dict(spec.answers)})
    return solve


# ---------------------------------------------------- L-2 (Caltrans PPM-046)


def _l2_bc(src: Sources) -> float:
    return nt.stations(src.one(r'^"D13"\s*\d+\+\d+\.\d+\s*BC$').content)[0][0]


def _base_bearing(src: Sources) -> str:
    """The one bearing the sheet's base files letter in model space."""
    found = {t.content for t in src.base_texts() if nt.bearings(t.content)}
    if len(found) != 1:
        raise LookupError(f"{src.sheet.name}'s base files letter {len(found)} bearings: "
                          f"{sorted(found)}")
    return found.pop()


L2_SPEC = Reading(
    id="p15-plan-reading-ppm046", sheet="PPM-046", scan="L-2-scan.png",
    kind="Caltrans layout sheet",
    questions=[
        Question("q1", "What is the radius of curve 3?", "feet",
                 lambda s: _number(_curve_table(s)["3"][0])),
        Question("q2", "At what station is the BC of curve 3 on the \"D13\" line?", "station",
                 _l2_bc),
        Question("q3", "Curve 3 runs on past this sheet. At what station is its EC?", "station",
                 lambda s: round(_l2_bc(s) + _number(_curve_table(s)["3"][3]), 2)),
        Question("q4", "What is the bearing of the \"D13\" tangent?", "bearing", _base_bearing),
        Question("q5", "What post miles (total project) does the title block give?", "text",
                 lambda s: s.sheet.title_block_fields["post_miles"]),
        Question("q6", "What is the delta of curve 31?", "angle",
                 lambda s: _curve_table(s)["31"][1]),
    ],
    answers={"q1": "5000 ft", "q2": "654+06.40", "q3": "690+10.44",
             "q4": "N 00°03'30\" E", "q5": "R11.9/R24.1", "q6": "03°03'45\""},
    note=("Truth from the redraft: the CURVE DATA table (R 5000' for curve 3, delta 03°03'45\" "
          "for 31), the BC callout \"D13\" 654+06.40 BC, AA01's D13 bearing N 00°03'30\" E, the "
          "title block's post miles R11.9/R24.1; q3 is worked out, BC + L = 654+06.40 + "
          "3604.04 = 690+10.44. Naive wrong answer that fails: q3 as BC + T (672+90.72)."),
)


# ------------------------------------------------- D.5 (WFL plan-profile p14)


def _d5_pc(src: Sources) -> float:
    return nt.stations(src.one(r"^PC\s*\d+\+\d+\.\d+$").content)[0][0]


def _d5_value(src: Sources, letter: str) -> float:
    return _number(src.one(r"^" + letter + r"\s*=\s*[\d,]+\.\d+").content.split("=", 1)[1])


def _d5_begin(src: Sources) -> Text:
    return src.one(r"^BEGIN PROJECT$")


def _d5_begin_station(src: Sources) -> float:
    return nt.stations(src.nearest(r'^"MAIN 01"\s*\d+\+\d+', _d5_begin(src)).content)[0][0]


D5_SPEC = Reading(
    id="p15-plan-reading-wflp14", sheet="WFL-Plan-Profile-Sheets-p14", scan="D5-scan.png",
    kind="WFL plan and profile sheet",
    questions=[
        Question("q1", "What is the radius of the \"MAIN 01\" curve on this sheet?", "feet",
                 lambda s: _d5_value(s, "R")),
        Question("q2", "At what station is that curve's PT? It is not lettered on this sheet.",
                 "station", lambda s: round(_d5_pc(s) + _d5_value(s, "L"), 2)),
        Question("q3", "What is the bearing of the \"MAIN 01\" tangent from Begin Project to the PC?",
                 "bearing", _base_bearing),
        Question("q4", "What is the project number in the title block?", "text",
                 lambda s: s.sheet.title_block_fields["project"]),
        Question("q5", "What northing does the sheet give for Begin Project?", "number",
                 lambda s: _number(s.nearest(r"^N=\s*\d", _d5_begin(s)).content), 4),
        Question("q6", "How long is the tangent from Begin Project to the PC?", "feet",
                 lambda s: round(_d5_pc(s) - _d5_begin_station(s), 2)),
    ],
    answers={"q1": "1,190.00'", "q2": "119+46.48", "q3": "N23°38'45\"E",
             "q4": "AK NPS SAMP 14(1)", "q5": "N 937,984.0982", "q6": "356.72 ft"},
    note=("Truth from the redraft: the curve data (R = 1,190.00', L = 584.76'), PC113+61.72, the "
          "ali file's N23°38'45\"E, the title block's project AK NPS SAMP 14(1), the N= under "
          "BEGIN PROJECT (937984.0982, not BEGIN CONSTRUCTION's 938002.4670); q2 = PC + L = "
          "119+46.48 and q6 = PC - 110+05.00 = 356.72 are worked out. Naive wrong answer that "
          "fails: q2 as the PI + T (119+58.54) or q5 as Begin Construction's northing."),
)


# ------------------------------------------------ Davis Dam Road (CFL PLA)


def _cfl_begin_bearing(src: Sources) -> str:
    begin = src.one(r"^BEGIN PROJECT$")
    return min(_split_bearings(src), key=lambda bt: math.dist(bt[1].position, begin.position))[0]


def _cfl_station(src: Sources, word: str, which: int) -> float:
    """The ``which``-th distinct ``PC``/``PT`` station lettered, in station order."""
    found = sorted({nt.stations(t.content)[0][0] for t in src.texts
                    if re.fullmatch(word + r"\s*\d+\+\d+\.\d+", t.content.strip())})
    return found[which]


CFL_SPEC = Reading(
    id="p15-plan-reading-cflpla", sheet="CFL-D-Plan-and-Plan", scan="davis-dam-road-scan.png",
    kind="CFL plan sheet",
    questions=[
        Question("q1", "What is the radius of the curve at PI 36+49.08?", "feet",
                 lambda s: _number(_curve_block(s, "36+49.08")["R"])),
        Question("q2", "What is the bearing of the tangent the project begins on, at Begin Project?",
                 "bearing", _cfl_begin_bearing),
        Question("q3", "What is the length of the curve at PI 31+52.26?", "feet",
                 lambda s: _number(_curve_block(s, "31+52.26")["L"])),
        Question("q4", "How long is the tangent between the two curves, from the first curve's "
                       "PT to the second curve's PC?", "feet",
                 lambda s: round(_cfl_station(s, "PC", 1) - _cfl_station(s, "PT", 0), 2)),
        Question("q5", "The sheet is plotted full size, 11 x 17 in. What is the plan scale, in "
                       "feet per inch?", "scale", lambda s: s.fpi()),
        Question("q6", "What is the delta of the curve at PI 31+52.26, and which way does it turn?",
                 "turn-angle", lambda s: (lambda v: (v.split("(")[0].strip(),
                                                     _turn(v.split("(", 1)[1])))(
                     _curve_block(s, "31+52.26")["Δ"])),
    ],
    answers={"q1": "855.00 ft", "q2": "S 71°44'22\" E", "q3": "243.42'", "q4": "126.47 ft",
             "q5": "1\" = 50'", "q6": "06°20'23\" RT"},
    note=("Truth from the redraft: the two curve data blocks (R = 855.00', L = 243.42', "
          "06°20'23\" (RT)), the bearing lettered at the left edge (S71°44'22\"E -- on the scan "
          "the S is cut off by the edge of the plan, so it has to be worked out: S65°23'59\"E "
          "back through the 06°20'23\" right turn), PC 34+00.32 - PT 32+73.85 = 126.47, and the "
          "viewport's 50 ft/in (the sheet shows only a bar scale). Naive wrong answer that "
          "fails: q2 as N 71°44'22\" E."),
)


# ======================================================================= probes


def _redraw_probe(spec: Redraw) -> Probe:
    start = common.register(f"scan-{spec.id}", spec.design_file, _redraw_builder(spec))
    return Probe(id=spec.id, prompt=spec.prompt, check=_check_redraw(spec), solve=spec.solve,
                 note=spec.note, tags=["scan", "redraw", "draft", "alignment"], start=start,
                 server_args=list(SERVER_ARGS))


def _reading_probe(spec: Reading) -> Probe:
    start = common.register(f"scan-{spec.id}", spec.doc, _reading_builder(spec))
    return Probe(id=spec.id, prompt=spec.prompt, check=_check_reading(spec),
                 solve=_reading_solve(spec), note=spec.note, tags=["scan", "reading"],
                 start=start, server_args=list(SERVER_ARGS))


REDRAWS = [TB1_SPEC, CL1_SPEC]
READINGS = [L2_SPEC, D5_SPEC, CFL_SPEC]

PROBES: List[Probe] = [_redraw_probe(s) for s in REDRAWS] + [_reading_probe(s) for s in READINGS]

__all__ = ["PROBES", "REDRAWS", "READINGS", "Redraw", "Reading", "Question", "Curve", "Sources",
           "SCANS", "SERVER_ARGS", "DPI", "POS_FT", "STATION_FT"]
