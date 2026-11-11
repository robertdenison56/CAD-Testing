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

The later instances (2026-11) lean on working out over copying. p01 adds L-7's "F6" loop
(two curves, the middle tangent lettered against the stationing, the loop's table radius a
rounded 55 m that only its L over its delta reproduces, held at its POT on FR), CFL Plan 1's
Main Road (two reversing curves, the last bearing lettered nowhere, held at a staked PI that
is T + tangent + T, not the station difference, from the one before) and WFL D.11's "MAIN 01"
(the bearing past the curve lettered nowhere, held at an equation with APPR 01 that falls on
the curve). p15 adds FDOT's Drainage Network 1, Caltrans L-39 and L-5 and WFL D.7 and D.12:
six questions each, most of them worked out (an off-sheet BC, PI or PT, a bearing ahead, a
grade elevation, coordinates carried back from End Project, an arc along an offset), one a
scale on an 11 x 17 print of a 22 x 34 sheet or off the profile grid, and one a trap (a PC
lettered without its hundreds, a grade's minus a half-height dash, the left bridge's stations
beside the right one's, a lettered tangent length a hundredth off its stations).

Each instance has a vague brief too (``Redraw.vague``, ``Reading.vague``): the request as a PE
puts it, without the tool hints (view_attachment, region) or the list of what to read off the
sheet. It keeps what the drafter cannot know: the file, the line and its name, the scan, the
stretch, the tie or datum point given, and for p15 every question with the meta keys and the
answer form the check parses. Neither check grades a drafting convention, so each serves both
levels.

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
    #: bearings another line letters alike, cut from every base file too (no file may
    #: hold one of the rebuilt line's bearings as text)
    also_strip: Tuple[str, ...] = ()
    #: how far the redraft's own (fitted) alignment may run from the truth
    redraft_ft: float = 0.3
    #: how the redraft's strokes beside the line are found (``_traces``' options)
    traces: Optional[dict] = None
    #: the vague brief's pieces (``vague``): the line as the PE names it, the sheet the scan
    #: is of, the stretch to rebuild, and the tie or datum handed over
    line: str = ""
    sheet_name: str = ""
    extent: str = ""
    given: str = ""

    @property
    def vague(self) -> str:
        """The request at the vague level: which file, line, scan and stretch, the name, and
        the tie or datum point given, without the tool hints or what to read off the sheet."""
        return (f"{self.design_file}, the file you have open, has lost the {self.line}. Rebuild "
                f"it from {self.scan}, a scan of {self.sheet_name}, {self.extent}; name it "
                f"{self.alignment} and draw it. {self.given}")


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
            glyph_ft: float = 8.0, layers: str = "", layers_ft: float = 13.0) -> List[str]:
    """Small loose linework hugging a path: lettering the redraft digitized as
    strokes and curve points it drew as little circles (L-1's "N 01°05'14\" W",
    "328.15'" and the quotes of "TB1" LINE, partly in the design file and
    partly in the topo file; its BC and POT circles). With ``layers`` (a pattern),
    strokes on those layers are taken out to ``layers_ft`` as well: where the redraft
    draws a plan in short segments (CFL's contours and hatching), 13 ft round the line
    would take half the corridor, so the rest stays to ``trace_ft``."""
    out = []
    for eid, e in session.doc.model_entities.items():
        pts = _vertices(e)
        if not pts or getattr(e, "anchor", None):
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(max(xs) - min(xs), max(ys) - min(ys)) > glyph_ft:
            continue
        reach = layers_ft if layers and re.search(layers, e.layer or "") else trace_ft
        if all(min(math.dist(p, q) for q in path) <= reach for p in pts):
            out.append(eid)
    return out


def _strip_alignment(session: Session, name: str, others: Sequence[Session] = (),
                     reach_ft: float = 30.0, traces: Optional[dict] = None) -> None:
    """Cut an alignment out of its base file: the design, everything anchored to
    it (centerline, ticks, station numbers), the loose lettering beside it that
    is its own -- its bearings and its name -- so nothing in the file holds its
    data as text, and (here and in the ``others``) the small strokes hugging it."""
    align = session.doc.design.alignments[name]
    path = [align.point_at(align.length * i / 400.0) for i in range(401)]
    gone = set(_traces(session, path, **(traces or {})))
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
        strokes = _traces(other, path, **(traces or {}))
        if strokes:
            common.ok(other.execute("delete_entities", {"ids": strokes}))


def _strip_bearings(session: Session, bearings: Sequence[str]) -> None:
    """Delete the loose text lettering any of these bearings."""
    want = [_azimuth(b) for b in bearings]
    gone = [eid for eid, e in session.doc.model_entities.items()
            if isinstance(e, Text) and any(nt.azimuth_close(a, w) for a in nt.bearings(e.content)
                                           for w in want)]
    if gone:
        common.ok(session.execute("delete_entities", {"ids": sorted(gone)}))


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
        _strip_alignment(session, spec.alignment, list(others.values()), traces=spec.traces)
        for one in [session] + list(others.values()):
            _strip_bearings(one, spec.also_strip)
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
    line="\"TB1\" line", sheet_name="layout sheet L-1", extent="over the length the sheet shows",
    given="Hold it to the tie the sheet gives to D13.",
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
    line="SR 61 construction centerline, CL1", sheet_name="roadway plan-profile sheet 12",
    extent=f"from station {_sta(CL1['begin'])} at SR 30 through the end of the curve",
    given=(f"The file is on a local datum, not state plane: SR 61 station {_sta(CL1['begin'])} "
           f"is at N {CL1['tie'][1]:.2f}, E {CL1['tie'][0]:.2f}."),
)


# ------------------------------------------- a line from its lettered legs, held at a tie

#: the redraft's strokes on the line (curve point circles, 3 ft) and its digitized lettering
#: (the TRACE layers, 13 ft), for the sheets drawn in short segments
TIGHT_TRACES = {"trace_ft": 3.0, "layers": r"TRACE"}


def _legs(bearings: Sequence[str], lengths: Sequence[float], radii: Sequence[float]):
    """``(legs, vectors)``: a line as a sheet letters it -- the tangent bearings in the
    direction of stationing, each tangent's length between curve points (the first from the
    begin, the last to the end) and each curve's radius -- as create_alignment legs, with each
    leg's vector, so a tie at any PI can place it."""
    az = [_azimuth(b) for b in bearings]
    tans = [r * math.tan(math.radians(abs((az[i + 1] - az[i] + 180.0) % 360.0 - 180.0)) / 2.0)
            for i, r in enumerate(radii)]
    legs, vectors = [], []
    for i, b in enumerate(bearings):
        dist = lengths[i] + (tans[i - 1] if i else 0.0) + (tans[i] if i < len(tans) else 0.0)
        leg = {"bearing": b, "distance": dist}
        if i:
            leg["radius"] = radii[i - 1]
        legs.append(leg)
        vectors.append(_step([0.0, 0.0], az[i], dist))
    return legs, vectors


def _held_at_pi(name: str, legs: list, vectors: list, begin_station: float,
                tie: Sequence[float], k: int) -> Alignment:
    """The line with its k-th PI (0 the begin, ``len(legs)`` the end) on the tie."""
    start = [tie[0] - sum(v[0] for v in vectors[:k]), tie[1] - sum(v[1] for v in vectors[:k])]
    return _engine_alignment(name, start, legs, begin_station)


def _held_at_station(name: str, legs: list, begin_station: float, station: float,
                     tie: Sequence[float]) -> Alignment:
    """The line with the point at ``station`` (on a curve, say) on the tie."""
    at = _engine_alignment(name, [0.0, 0.0], legs, begin_station).station_to_xy(station)[0]
    return _engine_alignment(name, [tie[0] - at[0], tie[1] - at[1]], legs, begin_station)


# ------------------------------------------------- L-7, the F6 loop (Caltrans PPM-050)

#: Caltrans layout L-7 (PPM-050): ramp "F6", the loop, as lettered. N 42°23'13" W 328.15' to
#: the BC at 703+83.48; curve 44 of the CURVE DATA table (R 3280' -- 1000 m --, delta
#: 02°51'53", T 82.04', L 164.04'), turning left (drawn, not lettered); EC 705+47.52; the
#: next tangent lettered S 45°15'06" E 353.79', against the stationing (F6 runs N 45°15'06" W
#: up-station); BC 709+01.31; curve 45 (R 180', delta 176°11'09", T 5419.20', L 554.87'), the
#: loop, left; EC 714+56.18; S 41°26'15" E 261.57' to "F6" 717+17.75 POT = "FR" 71+69.42 POT.
#: The table's R 180' is 55 m rounded to the foot: its T and L are those of R 180.44 (L over
#: delta), and R 180' itself would bring the loop's EC up 1.37 ft short of 714+56.18.
F6 = {"b1": "N 42°23'13\" W", "l1": 328.15, "bc44": 70383.48, "ec44": 70547.52,
      "r44": 1000.0 * 3937.0 / 1200.0, "d44": "02°51'53\"", "t44": 82.04,
      "b2": "N 45°15'06\" W", "l2": 353.79, "bc45": 70901.31, "ec45": 71456.18,
      "r45": 554.87 / math.radians(176.0 + 11.0 / 60.0 + 9.0 / 3600.0), "d45": "176°11'09\"",
      "t45": 5419.20, "b3": "S 41°26'15\" E", "l3": 261.57, "pot": 71717.75, "fr": 7169.42}


def _f6_legs():
    return _legs([F6["b1"], F6["b2"], F6["b3"]], [F6["l1"], F6["l2"], F6["l3"]],
                 [F6["r44"], F6["r45"]])


def _f6_pot(session: Session) -> List[float]:
    return common.ok(session.query("station_to_xy", {"alignment": "FR",
                                                     "station": F6["fr"]}))["point"]


def _f6_truth(baseline: Session) -> Alignment:
    legs, vectors = _f6_legs()
    return _held_at_pi("F6", legs, vectors, F6["bc44"] - F6["l1"], _f6_pot(baseline), len(legs))


def _f6_solve(session: Session) -> None:
    """Work back from the POT on FR with the traverse query (curve 45's R from its L and
    delta), then lay F6 out by bearings and distances and draw it."""
    pot = _f6_pot(session)
    t44, t45 = F6["t44"], F6["t45"]          # the table's T; the engine fits the curves at the PIs
    r = common.ok(session.query("traverse", {"start": pot, "legs": [
        {"bearing": "N 41°26'15\" W", "distance": F6["l3"] + t45},
        {"bearing": "S 45°15'06\" E", "distance": t45 + F6["l2"] + t44},
        {"bearing": "S 42°23'13\" E", "distance": t44 + F6["l1"]}]}))
    run(session, "create_alignment", {
        "name": "F6", "start": r["points"][-1], "begin_station": "700+55.33",
        "legs": [{"bearing": F6["b1"], "distance": F6["l1"] + t44},
                 {"bearing": F6["b2"], "distance": t44 + F6["l2"] + t45, "radius": 3280.83},
                 {"bearing": F6["b3"], "distance": t45 + F6["l3"], "radius": 180.444}]})
    run(session, "draw_alignment", {"alignment": "F6", "layer": "V-ALIGN-CNTR"})


F6_SPEC = Redraw(
    id="p01-redraw-alignment-ppm050",
    sheet="PPM-050", design_file="0000000000aa01.rdraft", alignment="F6", aliases=(),
    scan="L-7-scan.png",
    begin_by=70200.00, end_by=F6["pot"],
    tangents=[(70250.00, F6["b1"]), (70700.00, F6["b2"]), (71600.00, F6["b3"])],
    curves=[Curve("curve 44", F6["bc44"], F6["ec44"], (3279.5, 3281.5), F6["d44"], "L",
                  ("BC", "EC")),
            Curve("curve 45", F6["bc45"], F6["ec45"], (180.40, 180.50), F6["d45"], "L",
                  ("BC", "EC"))],
    truth=_f6_truth, layer="V-ALIGN-CNTR", also_strip=(F6["b3"],), redraft_ft=0.35,
    traces=TIGHT_TRACES,
    prompt=(
        "We lost the \"F6\" line (the loop ramp at Ferrari Ranch Road) out of the roadway "
        "design file you have open, 0000000000aa01.rdraft. All we have to go on is a scan of "
        "layout sheet L-7, L-7-scan.png: look at it with view_attachment, and zoom in with "
        "region to read the lettering. Rebuild F6 in this file from the alignment data "
        "lettered on the sheet (the tangent bearings and lengths, the curve data, the curve "
        "point stations) over the whole length of it the sheet shows, name it F6, and draw "
        "it. The FR line is still in the file: hold the tie the sheet gives between F6's end "
        "and FR. The proposed roadway linework is still there too, if you want to check your "
        "work against it."),
    note=("F6's design, centerline, stationing and bearing/name text cut out of AA01 (with "
          "F2's S 41°26'15\" E beside it, the same bearing as F6's last tangent) and the sheet "
          "file left out of the project. Expected: N 42°23'13\" W to BC 703+83.48, curve 44 "
          "(R 3280', delta 02°51'53\", left), EC 705+47.52, N 45°15'06\" W 353.79' (lettered "
          "S 45°15'06\" E, against the stationing) to BC 709+01.31, curve 45 (the loop: delta "
          "176°11'09\", left, R 180.44 -- the table letters 180', 55 m rounded, and only "
          "L 554.87 / delta gives the lettered EC 714+56.18), S 41°26'15\" E 261.57' to the POT "
          "717+17.75 on FR 71+69.42; the begin is 328.15 ft back from the BC, off the sheet. "
          "Naive wrong answers that fail: curve 45 at the table's R 180' (EC 1.37 ft short); "
          "the loop turned right; the middle tangent laid out S 45°15'06\" E as lettered; the "
          "tie taken at F2's POT on FR (71+28.97)."),
    solve=_f6_solve,
    line="\"F6\" line", sheet_name="layout sheet L-7", extent="over the length the sheet shows",
    given="Hold it to the tie the sheet gives to FR.",
)


# ---------------------------------------------- Plan 1, the Main Road (CFL plan and profile)

#: CFL plan and profile sheet Plan 1 (Main Road, Schedule A): CL1 as lettered. BEGIN PROJECT
#: 10+00.00 on N13°33'40"E; PC 16+84.93, PI 18+20.33, delta 22°41'06" (RT), R 675.00',
#: T 135.40', L 267.25', PT 19+52.18; N36°14'46"E; PC 20+71.70, PI 21+60.40, delta 20°07'09"
#: (LT), R 500.00', T 88.70', L 175.57', PT 22+47.27; the bearing on past the second curve,
#: N16°07'37"E, is lettered nowhere. The published N/E are state plane; the file is on a local
#: datum, and the tie (the prompt's) is the second curve's PI, fitted to the redraft.
CFL1 = {"b1": "N 13°33'40\" E", "b2": "N 36°14'46\" E", "b3": "N 16°07'37\" E",
        "begin": 1000.00, "pc1": 1684.93, "pt1": 1952.18, "d1": "22°41'06\"", "r1": 675.00,
        "pc2": 2071.70, "pt2": 2247.27, "d2": "20°07'09\"", "r2": 500.00, "end": 2500.00,
        "pi2": [9889.59, 10486.51]}


def _cfl1_legs():
    return _legs([CFL1["b1"], CFL1["b2"], CFL1["b3"]],
                 [CFL1["pc1"] - CFL1["begin"], CFL1["pc2"] - CFL1["pt1"],
                  CFL1["end"] + 50.0 - CFL1["pt2"]], [CFL1["r1"], CFL1["r2"]])


def _cfl1_truth(_baseline: Session) -> Alignment:
    legs, vectors = _cfl1_legs()
    return _held_at_pi("CL1", legs, vectors, CFL1["begin"], CFL1["pi2"], 2)


def _cfl1_solve(session: Session) -> None:
    """Back from the staked PI to Begin Project (PI to PI is T + tangent + T, not the
    difference of the PI stations), then forward by deflections."""
    t1, t2 = 135.40, 88.70
    r = common.ok(session.query("traverse", {"start": CFL1["pi2"], "legs": [
        {"bearing": "S 36°14'46\" W", "distance": t2 + (2071.70 - 1952.18) + t1},
        {"bearing": "S 13°33'40\" W", "distance": t1 + 684.93}]}))
    run(session, "create_alignment", {
        "name": "CL1", "start": r["points"][-1], "begin_station": "10+00.00",
        "legs": [{"bearing": CFL1["b1"], "distance": 684.93 + t1},
                 {"deflection": "22°41'06\" RT", "radius": 675.0,
                  "distance": t1 + (2071.70 - 1952.18) + t2},
                 {"deflection": "20°07'09\" LT", "radius": 500.0,
                  "distance": t2 + (2500.00 - 2247.27)}]})
    run(session, "draw_alignment", {"alignment": "CL1", "layer": "P_ALIGN"})


CFL1_SPEC = Redraw(
    id="p01-redraw-alignment-cflpnp",
    sheet="CFL-D-Plan-and-Profile", design_file="ALI(MAIN)Sample.rdraft", alignment="CL1",
    aliases=("MAIN", "MAIN ROAD", "MAINROAD", "MAINRD"),
    scan="plan-1-scan.png",
    begin_by=CFL1["begin"], end_by=CFL1["end"],
    tangents=[(1300.00, CFL1["b1"]), (2000.00, CFL1["b2"]), (2400.00, CFL1["b3"])],
    curves=[Curve("curve 1", CFL1["pc1"], CFL1["pt1"], (674.5, 675.5), CFL1["d1"], "R"),
            Curve("curve 2", CFL1["pc2"], CFL1["pt2"], (499.5, 500.5), CFL1["d2"], "L")],
    truth=_cfl1_truth, layer="P_ALIGN", traces=TIGHT_TRACES,
    prompt=(
        "Our alignments file ALI(MAIN)Sample.rdraft (open) has lost the Main Road centerline, "
        "CL1. The proposed roadway linework is in COR(MAIN)Sample.rdraft beside it. What we "
        "have is a scan of plan and profile sheet Plan 1, plan-1-scan.png: look at it with "
        "view_attachment, and zoom in with region to read the lettering. Rebuild CL1 in this "
        "file from what the sheet letters (the tangent bearings, the curve data, the "
        "stations) from Begin Project through station 25+00.00, name it CL1, and draw it. This "
        "file is on a local datum, not state plane: the survey staked the PI of the second "
        "curve at N 10486.51, E 9889.59."),
    note=("CL1's design, centerline, stationing and bearing text cut out of the ALI file and "
          "the sheet file left out of the project. Expected: N13°33'40\"E from Begin Project "
          "10+00.00 to the PC 16+84.93, R 675.00 right through 22°41'06\" to the PT 19+52.18, "
          "N36°14'46\"E to the PC 20+71.70, R 500.00 left through 20°07'09\" to the PT "
          "22+47.27, then N16°07'37\"E (lettered nowhere: the bearing before turned left by the "
          "delta) to 25+00.00, held at the staked PI 21+60.40, 343.62 ft along the tangents "
          "from PI 18+20.33 (T + tangent + T). Naive wrong answers that fail: the PIs 340.07 "
          "apart (the difference of their stations); the second curve turned right; the "
          "lettered state-plane N/E taken for Begin Project."),
    solve=_cfl1_solve,
    line="Main Road centerline, CL1", sheet_name="plan and profile sheet Plan 1",
    extent=f"from Begin Project through station {_sta(CFL1['end'])}",
    given=(f"The file is on a local datum, not state plane: the survey staked the PI of the "
           f"second curve at N {CFL1['pi2'][1]:.2f}, E {CFL1['pi2'][0]:.2f}."),
)


# --------------------------------------------- D.11, "MAIN 01" past the 643' curve (WFL)

#: WFL plan and profile sheet D.11: "MAIN 01" as lettered. PT 152+96.54 (of the 81°35'22"
#: curve on D.10); S12°39'14"E; PC 155+27.34; PI 157+19.23, delta 33°13'58" (LT), R 643.00',
#: T 191.89', L 372.95'; PT 159+00.29; the bearing on past it, S45°53'12"E, is lettered
#: nowhere on this sheet (D.12 letters S45°53'11"E, the design's own rounding).
#: "MAIN 01" 155+69.97 = "APPR 01" 610+00.00, on the curve: the tie (the prompt's coordinates
#: of APPR 01 610+00.00, fitted to the redraft on its local datum).
D11 = {"b1": "S 12°39'14\" E", "b2": "S 45°53'12\" E", "begin": 15296.54, "pc": 15527.34,
       "pt": 15900.29, "delta": "33°13'58\"", "radius": 643.00, "end": 16000.00,
       "eq": 15569.97, "tie": [10058.92, 10090.40], "appr": 61000.00}


def _d11_legs():
    return _legs([D11["b1"], D11["b2"]], [D11["pc"] - D11["begin"], D11["end"] + 50.0 - D11["pt"]],
                 [D11["radius"]])[0]


def _d11_truth(_baseline: Session) -> Alignment:
    return _held_at_station("MAIN 01", _d11_legs(), D11["begin"], D11["eq"], D11["tie"])


def _d11_solve(session: Session) -> None:
    """Lay the line out anywhere, find where its 155+69.97 (on the curve) lands, and move
    the start by the difference to the equation's point."""
    legs = [{"bearing": D11["b1"], "distance": 230.80 + 191.89},
            {"deflection": "33°13'58\" LT", "radius": 643.0, "distance": 191.89 + 99.71}]
    spec = {"name": "MAIN 01", "begin_station": "152+96.54", "legs": legs}
    run(session, "create_alignment", dict(spec, start=[0.0, 0.0]))
    at = common.ok(session.query("station_to_xy", {"alignment": "MAIN 01",
                                                   "station": "155+69.97"}))["point"]
    run(session, "delete_alignment", {"name": "MAIN 01"})
    run(session, "create_alignment", dict(spec, start=[D11["tie"][0] - at[0],
                                                       D11["tie"][1] - at[1]]))
    run(session, "draw_alignment", {"alignment": "MAIN 01", "layer": "P_ALIGN"})


D11_SPEC = Redraw(
    id="p01-redraw-alignment-wfl20",
    sheet="WFL-Plan-Profile-Sheets-p20", design_file="SamplePlan_ali.rdraft",
    alignment="MAIN 01", aliases=("MAIN01", "MAIN"),
    scan="D11-scan.png",
    begin_by=D11["begin"], end_by=D11["end"],
    tangents=[(15400.00, D11["b1"]), (15950.00, D11["b2"])],
    curves=[Curve("the curve", D11["pc"], D11["pt"], (642.5, 643.5), D11["delta"], "L")],
    truth=_d11_truth, layer="P_ALIGN", traces=TIGHT_TRACES,
    prompt=(
        "Our alignments file SamplePlan_ali.rdraft (open) has lost the \"MAIN 01\" line over "
        "sheet D.11. The proposed roadway linework is in SamplePlan_cor.rdraft beside it. What "
        "we have is a scan of plan and profile sheet D.11, D11-scan.png: look at it with "
        "view_attachment, and zoom in with region to read the lettering. Rebuild MAIN 01 in "
        "this file from what the sheet letters (the bearing, the curve data, the stations), "
        "from the PT where this sheet picks up the curve coming in from D.10 through station "
        "160+00.00, name it MAIN 01, and draw it. This file is on a local datum: the survey "
        "has \"APPR 01\" 610+00.00 at N 10090.40, E 10058.92; hold MAIN 01 to the equation "
        "the sheet letters there."),
    note=("MAIN 01's design, centerline and stationing cut out of the ALI file and the sheet "
          "file left out of the project. Expected: from the PT 152+96.54, S12°39'14\"E to the "
          "PC 155+27.34, R 643.00 left through 33°13'58\" to the PT 159+00.29, then "
          "S45°53'12\"E (lettered nowhere on D.11: the bearing in turned left by the delta) to "
          "160+00.00, held where the equation \"MAIN 01\" 155+69.97 = \"APPR 01\" 610+00.00 "
          "puts it -- on the curve, 42.63 ft past the PC. Naive wrong answers that fail: the "
          "curve turned right; the PC (not 155+69.97) put on the APPR 01 point; the line run "
          "on at S12°39'14\"E + 33°13'58\" (the delta added the wrong way)."),
    solve=_d11_solve,
    line="\"MAIN 01\" line over sheet D.11", sheet_name="plan and profile sheet D.11",
    extent=(f"from the PT where the sheet picks up the curve from D.10 through station "
            f"{_sta(D11['end'])}"),
    given=(f"The file is on a local datum: the survey has \"APPR 01\" {_sta(D11['appr'])} at "
           f"N {D11['tie'][1]:.2f}, E {D11['tie'][0]:.2f}; tie MAIN 01 in at the equation the "
           f"sheet letters there."),
)


# ======================================================================= p15


@dataclass
class Question:
    key: str                       # q1 ...
    ask: str                       # as the prompt puts it
    kind: str                      # station | feet | bearing | angle | turn-angle | turn | text | scale | number
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
        elif q.kind == "turn":
            ok = _turn(nt.DMS_RE.sub(" ", got)) == want
            shown = f"{want}T"
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

    @property
    def vague(self) -> str:
        """The request at the vague level: the scan, every question, the meta keys and the
        answer form the check reads, without the tool hints."""
        asks = " ".join(f"{q.key}: {q.ask}" for q in self.questions)
        keys = f"{self.questions[0].key} to {self.questions[-1].key}"
        return (f"Before we use the scanned {self.kind} in {self.scan}, check what it says. "
                f"Record each answer with set_meta under its key, {keys}, the value alone: "
                f"stations as 123+45.67, bearings as N 12°34'56\" E, lengths in feet. {asks}")


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


# ------------------------------------------------------- shared readers for the later sheets


def _bearing_text(azimuth: float) -> str:
    """An azimuth as a quadrant bearing to the second: ``N 30°00'32" E``."""
    az = azimuth % 360.0
    ns, ew, ang = (("N", "E", az) if az < 90.0 else ("S", "E", 180.0 - az) if az < 180.0
                   else ("S", "W", az - 180.0) if az < 270.0 else ("N", "W", 360.0 - az))
    sec = int(round(ang * 3600.0))
    return f"{ns} {sec // 3600:02d}°{sec % 3600 // 60:02d}'{sec % 60:02d}\" {ew}"


def _dms_text(degrees: float) -> str:
    sec = int(round(abs(degrees) * 3600.0))
    return f"{sec // 3600:02d}°{sec % 3600 // 60:02d}'{sec % 60:02d}\""


def _turned(bearing: str, delta: str, turn: str) -> float:
    """The azimuth on past a curve: the bearing in, turned by the delta."""
    return (_azimuth(bearing) + (1.0 if turn == "R" else -1.0) * _dms(delta)) % 360.0


def _station_of(src: Sources, pattern: str) -> float:
    return nt.stations(src.one(pattern).content)[0][0]


def _offset(text: str) -> float:
    """``45.50 LT`` / ``34.78' Rt``: signed feet, right positive."""
    m = re.search(r"([\d.]+)\s*'?’?\)?\s*\(?\s*(LT|RT)\b", text.upper().replace("’", "'"))
    if not m:
        raise ValueError(f"no offset in {text!r}")
    return float(m.group(1)) * (1.0 if m.group(2) == "RT" else -1.0)


def _base_alignment(src: Sources, name: str) -> Alignment:
    found = [doc.design.alignments[name] for doc in src.bases.values()
             if name in doc.design.alignments]
    if len(found) != 1:
        raise LookupError(f"{len(found)} alignments {name} in {src.sheet.name}'s base files")
    return found[0]


def _print_fpi(src: Sources, print_long_in: float = 17.0) -> float:
    """The plan scale on a print of the sheet whose long side is ``print_long_in``."""
    return src.fpi() * max(src.sheet.width_in, src.sheet.height_in) / print_long_in


# ------------------------------------- Drainage Network 1 (FDOT drainage plan, sheet 1)


def _fdot_block(src: Sources, name: str) -> List[str]:
    """An FDOT structure's data block: the lines lettered under its name (``S-104``)."""
    head = src.one(r"^" + re.escape(name) + r"$")
    below = sorted((t for t in src.texts if abs(t.position[0] - head.position[0]) < 0.02
                    and 0.0 < head.position[1] - t.position[1] < 1.2),
                   key=lambda t: -t.position[1])
    lines, y = [], head.position[1]
    for t in below:
        if y - t.position[1] > 0.16:
            break
        lines.append(t.content)
        y = t.position[1]
    return lines


def _fdot_place(src: Sources, name: str) -> Tuple[float, float]:
    line = next(v for v in _fdot_block(src, name) if v.startswith("STA."))
    return nt.stations(line)[0][0], _offset(line)


def _fdot_depth(src: Sources, name: str) -> float:
    block = _fdot_block(src, name)
    grate = _number(next(v for v in block if v.startswith("ELEV.")))
    return round(grate - min(_number(v) for v in block if v.startswith("FL ")), 2)


def _fdot_apart(src: Sources, a: str, b: str) -> float:
    (sa, oa), (sb, ob) = _fdot_place(src, a), _fdot_place(src, b)
    if abs(sa - sb) > 1e-6:
        raise ValueError(f"{a} and {b} are not at one station")
    return round(abs(oa - ob), 2)


def _fdot_pipe(src: Sources, size: int) -> float:
    """Feet of pipe of one size the sheet constructs: each ``CONST. 87 LF`` over its
    ``OF 18" PIPE``."""
    total = 0.0
    for t in src.texts:
        m = re.fullmatch(r"CONST\.\s*(\d+)\s*LF", t.content.strip())
        if not m:
            continue
        under = min((u for u in src.texts if abs(u.position[0] - t.position[0]) < 0.12
                     and 0.05 < t.position[1] - u.position[1] < 0.3),
                    key=lambda u: t.position[1] - u.position[1])
        if re.fullmatch(rf'OF {size}" PIPE', under.content.strip()):
            total += float(m.group(1))
    return total


def _fdot_baseline(src: Sources) -> Alignment:
    return _base_alignment(src, "CL1")


def _fdot_pc(src: Sources) -> float:
    """``PC STA. +70.72`` lettered without its hundreds: they come from where the PC is."""
    plus = _number(src.one(r"^PC STA\.\s*\+\d\d\.\d\d$").content.split("+", 1)[1])
    cl1 = _fdot_baseline(src)
    pc = cl1.begin_station + cl1.curves()[0].start_dist
    return round(math.floor((pc - plus + 50.0) / 100.0) * 100.0 + plus, 2)


def _fdot_cross_pipe(src: Sources) -> str:
    """S-101 (Lt) to S-102 (Rt), square across the baseline at one station: the bearing
    up-station turned 90° right."""
    (bearing, _t), = _split_bearings(src)
    return _bearing_text(_azimuth(bearing) + 90.0)


FDOT916_SPEC = Reading(
    id="p15-plan-reading-fdot916", sheet="FDOT-916-1-Drainage-Network-Plan-Sheet",
    scan="drainage-network-1-scan.png", kind="FDOT drainage plan sheet",
    questions=[
        Question("q1", "At what station is the PC of the SR 22 baseline?", "station", _fdot_pc),
        Question("q2", "How deep is inlet S-104, from its grate elevation down to its lowest "
                       "flow line?", "feet", lambda s: _fdot_depth(s, "S-104")),
        Question("q3", "How far apart are inlets S-101 and S-102, center to center?", "feet",
                 lambda s: _fdot_apart(s, "S-101", "S-102")),
        Question("q4", "How much 18-inch pipe does this sheet construct, in all?", "feet",
                 lambda s: _fdot_pipe(s, 18), 0),
        Question("q5", "What is the bearing of pipe P-101, from S-101 to S-102?", "bearing",
                 _fdot_cross_pipe),
        Question("q6", "Past the PC, which way does the baseline curve, looking up-station: "
                       "left or right?", "turn", lambda s: _fdot_baseline(s).curves()[0].direction),
    ],
    answers={"q1": "705+70.72", "q2": "5.69 ft", "q3": "91.00 ft", "q4": "564 LF",
             "q5": "N 30°00'32\" E", "q6": "Right"},
    note=("Truth from the redraft: the PC callout lettered \"PC STA. +70.72\" with no hundreds "
          "(they come from the station numbers either side of it, 705 and 706; the redraft's "
          "CL1 has its PC at 705+70.74); S-104's block (ELEV. 31.69, lowest FL 26.00); S-101 and "
          "S-102 both at STA. 703+00.00, 45.50 LT and 45.50 RT, so 91.00 apart (P-101 between "
          "them is lettered 87 LF, inside wall to inside wall); the six CONST. ... LF OF 18\" "
          "PIPE callouts, 87 + 47 + 197 + 95 + 47 + 91 = 564 (the 53 LF of 24\" is not one); "
          "the baseline's N59°59'28\"W turned 90° right for the run from the Lt inlet to the Rt "
          "one, N30°00'32\"E; the redraft CL1's curve turns right (drawn, not lettered here). "
          "Naive wrong answers that fail: q1 as 700+70.72 or 706+70.72, q3 as the pipe's 87, "
          "q4 with the 24\" pipe counted (617), q5 reversed (S30°00'32\"W)."),
)


# ---------------------------------------------------- L-39 (Caltrans PPM-052, "SB10")


def _l39_curve(src: Sources, number: str) -> Tuple[float, float, float, float]:
    r, delta, t, length = _curve_table(src)[number]
    return _number(r), _dms(delta), _number(t), _number(length)


def _l39_ec14(src: Sources) -> float:
    return _station_of(src, r'^"SB10"\s*\d+\+\d+\.\d+\s*EC$')


def _l39_bc15(src: Sources) -> float:
    return _station_of(src, r'^"SB10"\s*\d+\+\d+\.\d+\s*BC$')


L39_SPEC = Reading(
    id="p15-plan-reading-ppm052", sheet="PPM-052", scan="L-39-scan.png",
    kind="Caltrans layout sheet",
    questions=[
        Question("q1", "Curve 14 ends on this sheet. At what station is its BC on the "
                       "\"SB10\" line?", "station",
                 lambda s: round(_l39_ec14(s) - _l39_curve(s, "14")[3], 2)),
        Question("q2", "At what station is the PI of curve 15?", "station",
                 lambda s: round(_l39_bc15(s) + _l39_curve(s, "15")[2], 2)),
        Question("q3", "Which way does curve 15 turn, and through what angle?", "turn-angle",
                 lambda s: (_curve_table(s)["15"][1],
                            _base_alignment(s, "SB10").curves()[0].direction)),
        Question("q4", "The scan is of an 11 x 17 in print. At what scale is the plan on that "
                       "print, in feet per inch?", "scale", _print_fpi),
        Question("q5", "What radius do curve 14's T and L give, to the nearest foot?", "feet",
                 lambda s: float(round(_l39_curve(s, "14")[3]
                                       / math.radians(_l39_curve(s, "14")[1]))), 0),
        Question("q6", "How long is the \"SB10\" tangent between curves 14 and 15, from the "
                       "stations at its ends?", "feet",
                 lambda s: round(_l39_bc15(s) - _l39_ec14(s), 2)),
    ],
    answers={"q1": "1032+94.34", "q2": "1044+23.79", "q3": "02°57'06\" LT", "q4": "1\" = 100'",
             "q5": "3281 ft", "q6": "453.28 ft"},
    note=("Truth from the redraft: the CURVE DATA table (14: 3,280', 02°57'06\", 84.52', "
          "169.01'; 15: 19,685', 02°57'06\", 507.16', 1,014.09'), the \"SB10\" 1034+63.35 EC and "
          "1039+16.63 BC callouts, the redraft SB10's curve 15 turning left (drawn, not lettered: "
          "it brings SB10 back from N 02°57'06\" E to the NB10 line's N 00°00'00\" E), the "
          "viewport's 50 ft/in on the 22 x 34 in sheet; worked out: BC 14 = EC - L = 1032+94.34, "
          "PI 15 = BC + T = 1044+23.79, the print is half size, so 1\" = 100' (the sheet letters "
          "1\" = 50', true of the full-size sheet; the border's inch bar shows the reduction), "
          "R 14 = L / delta = 3280.7, 3281 to the foot (a 1000 m radius; T / tan(delta/2) gives "
          "3280.9), and the tangent BC 15 - EC 14 = 453.28 (lettered 453.29'). Naive wrong "
          "answers that fail: q4 as the lettered 1\" = 50', q5 as the table's 3,280', q6 as the "
          "lettered 453.29', q3 turned right."),
)


# --------------------------------------------------- L-5 (Caltrans PPM-049, Ingram Slough)


def _l5_curve(src: Sources) -> Tuple[float, float, float, float]:
    r, delta, t, length = _curve_table(src)["3"]
    return _number(r), _dms(delta), _number(t), _number(length)


def _l5_ec(src: Sources) -> float:
    return _station_of(src, r'^"D13"\s*\d+\+\d+\.\d+\s*EC$')


def _l5_bridge(src: Sources, end: str, side: str) -> float:
    return _station_of(src, rf"^\d+\+\d+\.\d+\s*{end}\s*\({side}\)$")


def _l5_fence(src: Sources, point: str) -> Tuple[float, float]:
    """A FENCE AND GATES row: ``(station, signed offset)`` of its location."""
    key = src.one(r"^" + re.escape(point) + r"$")
    loc = min((t for t in src.texts if abs(t.position[1] - key.position[1]) < 0.03
               and 0.5 < t.position[0] - key.position[0] < 2.5 and '"D13"' in t.content),
              key=lambda t: t.position[0])
    return nt.stations(loc.content)[0][0], _offset(loc.content)


def _l5_fence_apart(src: Sources, a: str, b: str) -> float:
    (sa, oa), (sb, ob) = _l5_fence(src, a), _l5_fence(src, b)
    if abs(sa - sb) > 1e-6:
        raise ValueError(f"{a} and {b} are not at one station")
    return round(abs(oa - ob), 2)


def _l5_along(src: Sources, a: str, b: str) -> float:
    """Two fence points at one offset on curve 3: the arc between them at that offset, the
    offset outside the curve (longer) or inside it, as the redraft's D13 turns."""
    (sa, oa), (sb, ob) = _l5_fence(src, a), _l5_fence(src, b)
    if abs(oa - ob) > 1e-6:
        raise ValueError(f"{a} and {b} are not at one offset")
    radius = _l5_curve(src)[0]
    turn = _base_alignment(src, "D13").curves()[0].direction
    outside = oa if turn == "L" else -oa            # right offsets lie outside a left curve
    return round(abs(sb - sa) * (radius + outside) / radius, 1)


L5_SPEC = Reading(
    id="p15-plan-reading-ppm049", sheet="PPM-049", scan="L-5-scan.png",
    kind="Caltrans layout sheet",
    questions=[
        Question("q1", "How long is the South Ingram Slough Right Bridge, from its BB to its EB?",
                 "feet", lambda s: round(_l5_bridge(s, "EB", "R") - _l5_bridge(s, "BB", "R"), 2)),
        Question("q2", "Curve 3 ends on this sheet. At what station is its PI?", "station",
                 lambda s: round(_l5_ec(s) - _l5_curve(s)[3] + _l5_curve(s)[2], 2)),
        Question("q3", "How far is the gate at FC4 from fence point FC3?", "feet",
                 lambda s: _l5_fence_apart(s, "FC3", "FC4")),
        Question("q4", "Fence points FC8 and FC7 are both 86.58' Rt of \"D13\". How far apart are "
                       "they along that offset line, to the tenth of a foot?", "feet",
                 lambda s: _l5_along(s, "FC8", "FC7"), 1),
        Question("q5", "The scan is of an 11 x 17 in print. At what scale is the plan on that "
                       "print, in feet per inch?", "scale", _print_fpi),
        Question("q6", "How far is the EB of the right bridge from the EC of curve 3?", "feet",
                 lambda s: round(_l5_ec(s) - _l5_bridge(s, "EB", "R"), 2)),
    ],
    answers={"q1": "225.57 ft", "q2": "672+90.72", "q3": "61.22 ft", "q4": "229.5 ft",
             "q5": "1\" = 100'", "q6": "110.13 ft"},
    note=("Truth from the redraft: the bridge callouts 686+74.74 BB (R) and 689+00.31 EB (R) "
          "(the left bridge's, 686+74.72 and 689+00.33, sit beside them), \"D13\" 690+10.44 EC, "
          "the CURVE DATA table (curve 3: R 5000', T 1884.32', L 3604.04'), the FENCE AND GATES "
          "table (FC3 301.15' Rt and FC4 239.93' Rt, both at 688+64.26; FC8 and FC7 86.58' Rt at "
          "686+74.73 and 689+00.32), the redraft D13's curve turning left, and the viewport's "
          "50 ft/in on the 22 x 34 in sheet. Worked out: the right bridge 225.57; PI = EC - L + T "
          "= 672+90.72; FC3 to FC4 61.22 (on one radial); FC8 to FC7 225.59 x (5000 + 86.58) / "
          "5000 = 229.5 (right offsets lie outside the left-turning curve, which the drawing "
          "shows bowing to the right); 1\" = 100' on the half-size print; EB (R) to the EC 110.13. "
          "Naive wrong answers that fail: q1 as the left bridge's 225.61, q4 as the station "
          "difference 225.59 or the inside arc 221.7, q5 as the lettered 1\" = 50'."),
)


# ------------------------------------------------- D.7 (WFL plan-profile p16, the 910' curve)


def _wfl_curve(src: Sources, letter: str) -> str:
    return src.one(r"^" + letter + r"\s*=\s*").content.split("=", 1)[1].strip()


def _d7_pc(src: Sources) -> float:
    return _station_of(src, r"^PC\s*\d+\+\d+\.\d+$")


def _grades(src: Sources) -> List[Tuple[float, float]]:
    """The profile's grade labels, ``(paper x, percent)``: the figures with a ``%`` just
    after them and the sign lettered with them or, smaller, just before them (D.7's
    "-3.90%" is a 0.056 in dash, a 0.084 in "3.90" and a 0.14 in "%")."""
    out = []
    for t in src.texts:
        m = re.fullmatch(r"([-+]?)(\d+\.\d\d)", t.content.strip())
        if not m or not any(u.content.strip() == "%" and 0.0 < u.position[0] - t.position[0] < 0.5
                            and abs(u.position[1] - t.position[1]) < 0.1 for u in src.texts):
            continue
        sign = m.group(1) or next((u.content.strip() for u in src.texts
                                   if u.content.strip() in "-+" and u.content.strip()
                                   and 0.0 < t.position[0] - u.position[0] < 0.12
                                   and abs(u.position[1] - t.position[1]) < 0.06), "+")
        out.append((t.position[0], (-1.0 if sign == "-" else 1.0) * float(m.group(2))))
    return sorted(out)


def _evc_elevation(src: Sources, vpi_station: str) -> float:
    """The end of the vertical curve at a VPI: the VPI's elevation run on half the curve
    at the grade lettered on past it."""
    vpi = src.one(r"^" + re.escape(vpi_station) + r"$")
    elev = _number(src.nearest(r"^\d{4}\.\d\d$", vpi).content)
    length = _number(src.nearest(r"^\d+' VC$", vpi).content)
    grade = next(g for x, g in _grades(src) if x > vpi.position[0])
    return round(elev + grade / 100.0 * length / 2.0, 2)


def _d7_grade_at_pc(src: Sources) -> float:
    """The profile grade at the plan's PC, on the tangent grade past the vertical curve."""
    vpi = src.one(r"^123\+50$")
    elev = _number(src.nearest(r"^\d{4}\.\d\d$", vpi).content)
    length = _number(src.nearest(r"^\d+' VC$", vpi).content)
    grade = next(g for x, g in _grades(src) if x > vpi.position[0])
    run_ = _d7_pc(src) - nt.stations(vpi.content)[0][0]
    if run_ < length / 2.0:
        raise ValueError("the PC is inside the vertical curve")
    return round(elev + grade / 100.0 * run_, 2)


def _profile_fpi_v(src: Sources) -> float:
    """The profile's vertical scale, from its elevation grid labels (feet per paper inch)."""
    left = sorted((t for t in src.texts if re.fullmatch(r"\d,\d{3}", t.content.strip())),
                  key=lambda t: (round(t.position[0], 1), t.position[1]))
    a, b = left[0], left[1]
    return round(abs(_number(b.content) - _number(a.content)) / abs(b.position[1] - a.position[1]), 2)


def _d7_throat(src: Sources) -> float:
    """The driveway's width where its returns end: the two ``+NN.NN`` over ``30.76' Lt``."""
    at = [t for t in src.texts if t.content.strip() == "30.76' Lt"]
    plus = [_number(src.nearest(r"^\+\d\d\.\d\d$", t).content.lstrip("+")) for t in at]
    if len(plus) != 2:
        raise LookupError(f"{len(plus)} return ends at 30.76' Lt")
    return round(abs(plus[0] - plus[1]), 2)


D7_SPEC = Reading(
    id="p15-plan-reading-wflp16", sheet="WFL-Plan-Profile-Sheets-p16", scan="D7-scan.png",
    kind="WFL plan and profile sheet",
    questions=[
        Question("q1", "The \"MAIN 01\" curve runs on past this sheet. At what station is its PT?",
                 "station", lambda s: round(_d7_pc(s) + _number(_wfl_curve(s, "L")), 2)),
        Question("q2", "What is the bearing of \"MAIN 01\" ahead of that curve, past its PT?",
                 "bearing", lambda s: _bearing_text(_turned(
                     _base_bearing(s), _wfl_curve(s, "Δ").split("(")[0],
                     _turn(_wfl_curve(s, "Δ").split("(", 1)[1])))),
        Question("q3", "What is the profile grade elevation at the end of the vertical curve at "
                       "VPI 123+50?", "number", lambda s: _evc_elevation(s, "123+50")),
        Question("q4", "The sheet is plotted full size, 11 x 17 in. What is the profile's "
                       "vertical scale, in feet per inch?", "scale", _profile_fpi_v),
        Question("q5", "What is the profile grade elevation at the PC of the \"MAIN 01\" curve?",
                 "number", _d7_grade_at_pc),
        Question("q6", "How wide is the driveway on the left near the PC where its returns end, "
                       "at 30.76' Lt?", "feet", _d7_throat),
    ],
    answers={"q1": "131+82.51", "q2": "N 85°45'25\" E", "q3": "6239.93", "q4": "1\" = 10'",
             "q5": "6236.30", "q6": "12.00 ft"},
    note=("Truth from the redraft: the curve data (PC126+43.20, Δ = 33°57'22\" (RT), "
          "L = 539.31'), the ali file's N51°48'03\"E, the profile's VPI 123+50 at 6247.73 with "
          "400' VC and -3.90% on past it (its minus a dash half the height of the figures), its "
          "grid labels 10 ft to the inch, and the driveway's return ends (+58.91 and +70.91, "
          "30.76' Lt). Worked out: PT = PC + L = 131+82.51 (the next sheet letters 131+82.50); "
          "N51°48'03\"E turned 33°57'22\" right = N85°45'25\"E (the next sheet letters "
          "N85°45'24\"E, the design's own rounding, which the grader's half-second does not "
          "reach); the EVC 125+50 at 6247.73 - 3.90% x 200 = 6239.93; the PC, past the EVC, at "
          "6247.73 - 3.90% x 293.20 = 6236.30; 1\" = 10' vertical against 1\" = 50' across; "
          "70.91 - 58.91 = 12.00. Naive wrong answers that fail: q1 as PI + T (131+98.86), q2 with "
          "the delta turned left (N17°50'41\"E), q3 with the dash missed (+3.90%: 6255.53) or "
          "at the VPI's own 6247.73, q5 with the dash missed (6259.16), q4 as the plan's 50."),
)


# ------------------------------------------------ D.12 (WFL plan-profile p21, End Project)


def _d12_tangent(src: Sources) -> str:
    """The bearing lettered on the tangent from PI 163+50.00 on to End Project."""
    main = _base_alignment(src, "MAIN 01")
    pi = _station_of(src, r"^PI\s*\d+\+\d+\.\d+$")
    found = []
    for doc in src.bases.values():
        for e in doc.model_entities.values():
            if isinstance(e, Text) and nt.bearings(e.content):
                at = main.stations().to_display(main.xy_to_station(e.position)["station"])[0]
                if at > pi:
                    found.append(e.content)
    if len(found) != 1:
        raise LookupError(f"{len(found)} bearings past the PI: {found}")
    return found[0]


def _d12_pi(src: Sources) -> List[float]:
    """PI 163+50.00 worked back from End Project's coordinates along that tangent."""
    end = _station_of(src, r'^"MAIN 01"\s*\d+\+\d+\.\d+$')
    north = _number(src.one(r"^N=\s*\d").content.split("=", 1)[1])
    east = _number(src.one(r"^E=\s*\d").content.split("=", 1)[1])
    back = end - _station_of(src, r"^PI\s*\d+\+\d+\.\d+$")
    e, n = _step([east, north], _azimuth(_d12_tangent(src)), -back)
    return [round(n, 2), round(e, 2)]


def _d12_turn(src: Sources) -> Tuple[str, str]:
    bearings = [e.content for doc in src.bases.values() for e in doc.model_entities.values()
                if isinstance(e, Text) and nt.bearings(e.content)]
    ahead = _d12_tangent(src)
    (back,) = [b for b in bearings if b != ahead]
    d = (_azimuth(ahead) - _azimuth(back) + 180.0) % 360.0 - 180.0
    return _dms_text(d), "R" if d > 0 else "L"


def _d12_width(src: Sources) -> float:
    """Edge to edge at End Project: the two ``+00.00`` callouts' offsets."""
    offs = [_offset(src.nearest(r"^[\d.]+' (Lt|Rt)$", t).content) for t in src.texts
            if t.content.strip() == "+00.00"]
    if len(offs) != 2:
        raise LookupError(f"{len(offs)} +00.00 callouts")
    return round(abs(offs[0] - offs[1]), 2)


D12_SPEC = Reading(
    id="p15-plan-reading-wflp21", sheet="WFL-Plan-Profile-Sheets-p21", scan="D12-scan.png",
    kind="WFL plan and profile sheet",
    questions=[
        Question("q1", "What northing does the PI at 163+50.00 have?", "number",
                 lambda s: _d12_pi(s)[0]),
        Question("q2", "What easting does that PI have?", "number", lambda s: _d12_pi(s)[1]),
        Question("q3", "Through what angle does \"MAIN 01\" turn at that PI, and which way?",
                 "turn-angle", _d12_turn),
        Question("q4", "What is the profile grade elevation at the end of the vertical curve at "
                       "VPI 165+40?", "number", lambda s: _evc_elevation(s, "165+40")),
        Question("q5", "The sheet is plotted full size, 11 x 17 in. What is the plan scale, in "
                       "feet per inch?", "scale", lambda s: s.fpi()),
        Question("q6", "How wide is the pavement at End Project, edge to edge?", "feet",
                 _d12_width),
    ],
    answers={"q1": "N 938,122.20", "q2": "E 544,061.48", "q3": "01°06'20\" RT", "q4": "6273.64",
             "q5": "1\" = 50'", "q6": "21.00 ft"},
    note=("Truth from the redraft: END PROJECT \"MAIN 01\" 166+00.00, N= 937944.7494, "
          "E= 544237.5831, PI 163+50.00, the ali file's two bearings (S45°53'11\"E before the PI, "
          "S44°46'51\"E after it, told apart by where they lie along the redraft's MAIN 01), the "
          "profile's VPI 165+40 at 6273.16 with 100' VC and +0.96% on past it, the +00.00 "
          "callouts 10.50' Lt and 10.50' Rt at End Project, and the viewport's 50 ft/in (the "
          "sheet letters no scale). Worked out: the PI is 250.00 ft back from End Project on "
          "N44°46'51\"W, N 938122.20, E 544061.48; S45°53'11\"E to S44°46'51\"E turns "
          "01°06'20\" right; 6273.16 + 0.96% x 50 = 6273.64; 21.00 ft edge to edge. Naive wrong "
          "answers that fail: the PI worked back on the other tangent's S45°53'11\"E "
          "(N 938118.77), the turn called left, q6 as the 30.00 lettered at the PI."),
)


# ======================================================================= probes


def _redraw_probe(spec: Redraw) -> Probe:
    start = common.register(f"scan-{spec.id}", spec.design_file, _redraw_builder(spec))
    # the check grades the line and its drawing, no drafting convention: it serves both levels
    return Probe(id=spec.id, prompt=spec.prompt, check=_check_redraw(spec), solve=spec.solve,
                 note=spec.note, tags=["scan", "redraw", "draft", "alignment"], start=start,
                 server_args=list(SERVER_ARGS), vague=spec.vague)


def _reading_probe(spec: Reading) -> Probe:
    start = common.register(f"scan-{spec.id}", spec.doc, _reading_builder(spec))
    # the vague brief keeps every question, key and answer form the check reads
    return Probe(id=spec.id, prompt=spec.prompt, check=_check_reading(spec),
                 solve=_reading_solve(spec), note=spec.note, tags=["scan", "reading"],
                 start=start, server_args=list(SERVER_ARGS), vague=spec.vague)


REDRAWS = [TB1_SPEC, CL1_SPEC, F6_SPEC, CFL1_SPEC, D11_SPEC]
READINGS = [L2_SPEC, D5_SPEC, CFL_SPEC, FDOT916_SPEC, L39_SPEC, L5_SPEC, D7_SPEC, D12_SPEC]

PROBES: List[Probe] = [_redraw_probe(s) for s in REDRAWS] + [_reading_probe(s) for s in READINGS]

__all__ = ["PROBES", "REDRAWS", "READINGS", "Redraw", "Reading", "Question", "Curve", "Sources",
           "SCANS", "SERVER_ARGS", "DPI", "POS_FT", "STATION_FT"]
