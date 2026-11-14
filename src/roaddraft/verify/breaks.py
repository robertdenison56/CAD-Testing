"""Grading a layout whose sheet count and breaks the drafter chose.

A ``plan-sheet-breaks`` task (``tasks.breaks``, training only) gives the line,
the scale and the first sheet's number, and leaves the rest of the layout to
the drafter.  Its truth carries the mark ``tasks.types.OPEN_BREAKS`` in its
scope, and ``verify`` sends such a truth here instead of grading it against
the generator's own breaks.  No other truth has the mark, so no other truth is
read by anything in this module.

What is done with it, in order:

1. *Read the drafter's layout off the drawing* (``read``), the way the ``p05``
   pilot grader does from the plotted sheets.  The plan sheets are the sheets a
   viewport of which shows some of the line, in order along it.  The breaks are
   the stations a match line is lettered at (any text that reads MATCH LINE, on
   a sheet or in the model: its anchor's station, else the station it letters)
   or drawn at (a model line square across the centerline, at least the spec's
   lenient ``match_line_min_in`` long on the paper).
2. *Give that layout its truth* (``tasks.breaks.rebuilt``): the sheets under the
   drafter's own names, each with its stretch, the curves it shows, its curve
   table, title block and match lines, by the generator's derivation.  The D1
   checks then grade the drawing against it as they grade any layout: the
   viewport on each stretch and the match line at each break on both sheets
   (D1-00), each sheet's table (D1-06), legibility with nothing cut by a frame
   (D1-08), title blocks (D1-10), north arrows (D1-11), and all the lettering.
   A drawing that does not read as N sheets joined at N - 1 breaks is graded
   against the generator's own layout, where it loses what it lacks.
3. *Judge the choice itself* (``check``), the one thing no D1 check can: a check
   of this module's own, ``D1-17``, added to the report beside the spec's.  Five
   parts, a fifth of its credit each:

   - ``joined``: N plan sheets, N - 1 breaks.
   - ``fewest``: no more sheets than the line takes at the scale asked
     (``tasks.breaks.fewest``), every one of them at that scale.
   - ``sound``: every break where a match line is sound (``tasks.breaks.unsound``).
   - ``whole``: every sheet shows all of its own stretch inside one viewport,
     inside the border, and every label lettered on that stretch whole inside
     a viewport of that sheet.
   - ``numbered``: the sheets numbered on from the first along the line, each
     title block giving its own number and the number of sheets.

The spec's check list, weights and hash are untouched and so is
``VERIFIER_VERSION``: nothing here runs for a truth without the mark.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import LABEL_KINDS
from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Polyline, Text
from roaddraft.tasks import breaks as rules
from roaddraft.tasks.brief import GroundTruth
from roaddraft.tasks.types import OPEN_BREAKS
from roaddraft.verify.context import rect_contains, rect_intersection
from roaddraft.verify.geometry import pieces_of
from roaddraft.verify.legibility import OVERLAP_EPS_IN, text_quad
from roaddraft.verify.normalize import normalize
from roaddraft.verify.report import CheckResult, Finding, VerifyReport

#: this module's check, beside the spec's frozen list and the verifier's ``EXTRA_CHECKS``:
#: in a report only for a truth whose breaks are open
CHECK = {"id": "D1-17",
         "name": "sheet breaks left to the drafter: no more sheets than the line takes at the "
                 "scale, each showing its whole stretch with its lettering, joined at sound "
                 "breaks and numbered in order",
         "weight": 10, "hard_fail": False}
PARTS = ("joined", "fewest", "sound", "whole", "numbered")

_MATCH_TEXT = re.compile(r"MATCH\s*LINE", re.I)
_STATION_TEXT = re.compile(r"(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)")
#: two readings of one break agree within this, and a match line lettered this near an end
#: of the line is no break (the pilot grader's 0.5 ft and ``ENDS_FT``)
SAME_FT = 0.5
ENDS_FT = 1.0
#: the centerline is sampled this often to see what a sheet shows (``verify.context``'s step)
STEP_FT = 10.0


@dataclass
class PlanSheet:
    """A sheet that shows some of the line: its viewports' windows (the part
    of each inside the border) and where along the line it first shows it."""
    sheet: object
    views: List[tuple] = field(default_factory=list)  # (viewport, transform, window)
    first: float = 0.0

    @property
    def name(self) -> str:
        return self.sheet.name


@dataclass
class Reading:
    """A drafter's layout as read off its drawing."""
    align: Alignment
    fpi: float                 # the scale the task asks for
    turn: float                # the twist the task asks for
    sheets: List[PlanSheet]    # the plan sheets, in order along the line
    breaks: List[float]        # the breaks, as distances from BEGIN, in order

    @property
    def joined(self) -> bool:
        return bool(self.sheets) and len(self.breaks) == len(self.sheets) - 1

    def stretches(self) -> List[Tuple[float, float]]:
        bounds = [0.0] + list(self.breaks) + [float(self.align.length)]
        return list(zip(bounds[:-1], bounds[1:]))


def _samples(align: Alignment, lo: float, hi: float) -> List[float]:
    """Distances from BEGIN along ``lo``..``hi``: every ``STEP_FT``, both ends
    and every element end between."""
    dists = {lo, hi} | {d for el in align.elements for d in (el.start_dist, el.end_dist)
                        if lo < d < hi}
    d = lo
    while d < hi:
        dists.add(d)
        d += STEP_FT
    return sorted(dists)


def _in_window(view: tuple, point) -> bool:
    _vp, transform, window = view
    return window is not None and rect_contains(window, transform.to_paper(point))


def _crossing(align: Alignment, piece, rot_tol_deg: float) -> Optional[float]:
    """Where a straight piece crosses the centerline square, as a distance
    from BEGIN; None when it does not."""
    try:
        a, b = align.xy_to_station(piece.a), align.xy_to_station(piece.b)
    except DesignError:
        return None
    if a["offset"] * b["offset"] >= 0.0:
        return None
    share = abs(a["offset"]) / (abs(a["offset"]) + abs(b["offset"]))
    dist = a["station"] + (b["station"] - a["station"]) * share - float(align.begin_station)
    if not 0.0 <= dist <= align.length:
        return None
    way = math.degrees(math.atan2(piece.b[1] - piece.a[1], piece.b[0] - piece.a[0]))
    off = abs((way - align.direction_at(dist) - 90.0) % 180.0)
    return dist if min(off, 180.0 - off) <= rot_tol_deg else None


def read(doc: Document, truth: GroundTruth, spec: dict) -> Reading:
    """The drafter's plan sheets and breaks, read off ``doc``."""
    align, fpi, turn, _own, _names = rules.layout_of(truth)
    begin, length = float(align.begin_station), float(align.length)
    line = [(d, align.point_at(d)) for d in _samples(align, 0.0, length)]
    sheets: List[PlanSheet] = []
    for sheet in doc.sheets.values():
        usable = tuple(sheet.usable_area())
        views = [(vp, vp.transform(), rect_intersection(tuple(vp.paper_bbox()), usable))
                 for vp in sheet.viewports]
        shown = [d for d, p in line if any(_in_window(v, p) for v in views)]
        if shown:
            sheets.append(PlanSheet(sheet=sheet, views=views, first=shown[0]))
    sheets.sort(key=lambda s: (s.first, s.name))

    found: List[float] = []
    stations = align.stations()
    texts = [e for e in doc.model_entities.values() if isinstance(e, Text)]
    texts += [e for s in doc.sheets.values() for e in s.entities.values() if isinstance(e, Text)]
    for e in texts:
        if not _MATCH_TEXT.search(str(e.content)):
            continue
        raw = (e.anchor or {}).get("station")
        if raw is None:
            lettered = _STATION_TEXT.search(str(e.content))
            try:
                raw = stations.parse(f"{lettered.group(1)}+{lettered.group(2)}") if lettered else None
            except (DesignError, ValueError):
                raw = None
        if raw is not None:
            found.append(float(raw) - begin)
    shortest = float(spec["lenient"]["match_line_min_in"]) * fpi
    rot_tol = float(spec["tolerances"]["rotation_deg"])
    for e in doc.model_entities.values():
        if not isinstance(e, (Line, Polyline)):
            continue
        for piece in pieces_of(e):
            if piece.kind == "line" and piece.length >= shortest - 1e-9:
                at = _crossing(align, piece, rot_tol)
                if at is not None:
                    found.append(at)
    breaks: List[float] = []
    for d in sorted(found):
        if d < ENDS_FT or d > length - ENDS_FT:
            continue
        if not breaks or d - breaks[-1] > SAME_FT:
            breaks.append(d)
    return Reading(align=align, fpi=fpi, turn=turn, sheets=sheets, breaks=breaks)


def _label_shown_whole(doc: Document, text: Text, views: List[tuple]) -> bool:
    style = doc.text_styles.get(text.style)
    for vp, transform, window in views:
        if window is None:
            continue
        quad = text_quad(transform.to_paper(text.position), text.content,
                         text.height / float(vp.feet_per_inch),
                         text.rotation_deg + float(vp.rotation_deg), text.halign, text.valign,
                         style.width_factor if style else 1.0)
        if all(window[0] - OVERLAP_EPS_IN <= q[0] <= window[2] + OVERLAP_EPS_IN
               and window[1] - OVERLAP_EPS_IN <= q[1] <= window[3] + OVERLAP_EPS_IN for q in quad):
            return True
    return False


def check(doc: Document, truth: GroundTruth, spec: dict, reading: Reading) -> Tuple[float, List[Finding]]:
    """``(credit, findings)`` of ``D1-17`` for a layout as read."""
    align, begin = reading.align, float(reading.align.begin_station)
    stations = align.stations()
    name = next(iter(truth.alignments))
    sheets, n = reading.sheets, len(reading.sheets)
    findings: List[Finding] = []
    if not sheets:
        return 0.0, [Finding("sheet_missing", note="no sheet shows any of the line")]
    passed = {part: True for part in PARTS}

    def anchor(dist: float) -> dict:
        return {"alignment": name, "ref": stations.format(begin + dist), "kind": "match_line"}

    # -- joined: N sheets, N - 1 breaks
    if not reading.joined:
        passed["joined"] = passed["sound"] = passed["whole"] = False
        at = ", ".join(stations.format(begin + d) for d in reading.breaks) or "none"
        findings.append(Finding(
            "missing", expected=n - 1, actual=len(reading.breaks),
            note=f"{n} plan sheet(s) but {len(reading.breaks)} break(s) lettered or drawn "
                 f"({at}); every pair of sheets that meet wants one match line, and a line on "
                 f"one sheet none"))

    # -- fewest: no more sheets than the line takes, at the scale asked
    least = rules.fewest(align, reading.fpi, reading.turn)
    if least is not None and n > least:
        passed["fewest"] = False
        findings.append(Finding(
            "not_fitted", expected=least, actual=n,
            note=f"{n} plan sheets; the line takes {least} at the scale asked"))
    for ps in sheets:
        off = [float(vp.feet_per_inch) for vp, _t, _w in ps.views
               if abs(float(vp.feet_per_inch) - reading.fpi) > 1e-9]
        if off:
            passed["fewest"] = False
            findings.append(Finding("viewport_scale", expected=reading.fpi, actual=off,
                                    note=f"a viewport on {ps.name} is not at the scale asked, "
                                         f"which the number of sheets is counted at"))

    # -- sound: every break where a match line is sound
    if reading.joined:
        for d in reading.breaks:
            why = rules.unsound(align, d)
            if why:
                passed["sound"] = False
                findings.append(Finding("misplaced", anchor=anchor(d),
                                        note=f"the break is not where a match line is sound: {why}"))

    # -- whole: each sheet shows all of its stretch, and its lettering, inside a viewport
    if reading.joined:
        tol = float(spec["tolerances"]["station_ft"])
        labels = [e for e in doc.model_entities.values()
                  if isinstance(e, Text) and (e.anchor or {}).get("kind") in LABEL_KINDS
                  and (e.anchor or {}).get("station") is not None]
        for ps, (lo, hi) in zip(sheets, reading.stretches()):
            points = [align.point_at(d) for d in _samples(align, lo, hi)]
            if not any(all(_in_window(v, p) for p in points) for v in ps.views):
                passed["whole"] = False
                findings.append(Finding(
                    "not_fitted", entity_ids=[vp.id for vp, _t, _w in ps.views],
                    note=f"no viewport on {ps.name} shows all of its stretch, "
                         f"{stations.format(begin + lo)} to {stations.format(begin + hi)}, inside "
                         f"the border"))
            cut = [e.id for e in labels
                   if lo - tol <= float(e.anchor["station"]) - begin <= hi + tol
                   and not _label_shown_whole(doc, e, ps.views)]
            if cut:
                passed["whole"] = False
                findings.append(Finding(
                    "clipped", entity_ids=sorted(cut),
                    note=f"lettering of {ps.name}'s own stretch is not shown whole inside a "
                         f"viewport of that sheet"))

    # -- numbered: on from the first sheet along the line, each title block saying so
    wanted = rules.sheet_names(n, truth.sheets[0]["name"])
    for ps, want in zip(sheets, wanted):
        if normalize(ps.name) != normalize(want):
            passed["numbered"] = False
            findings.append(Finding("wrong_field", expected=want, actual=ps.name,
                                    note=f"the sheets are not numbered on from "
                                         f"{wanted[0]} in order along the line"))
            continue
        fields = ps.sheet.title_block_fields or {}
        for key, value in (("sheet_number", ps.name), ("total_sheets", str(n))):
            have = fields.get(key)
            if have is None or not str(have).strip():
                continue  # a blank field is D1-10's to charge
            if normalize(str(have)) != normalize(value):
                passed["numbered"] = False
                findings.append(Finding("wrong_field", expected=value, actual=have,
                                        note=f"title block field {key} on sheet {ps.name}"))
    return sum(passed.values()) / len(PARTS), findings


def verify_open(doc: Document, truth: GroundTruth, spec: dict, journal=None,
                prompt_level: str = "explicit") -> VerifyReport:
    """The report for a truth whose breaks are the drafter's: the D1 checks
    against the truth of the layout the drafter chose, and ``D1-17`` on the
    choice.  A layout that does not read as sheets joined at breaks (or whose
    breaks no layout can be derived from) is graded against the generator's."""
    from roaddraft.verify import verify  # (it imports this module to send truths here)
    reading = read(doc, truth, spec)
    _align, _fpi, _turn, own, own_names = rules.layout_of(truth)
    graded = None
    if reading.joined:
        try:
            graded = rules.rebuilt(truth, reading.breaks, [ps.name for ps in reading.sheets])
        except (DesignError, ValueError, KeyError, IndexError, ZeroDivisionError):
            graded = None
    if graded is None:
        graded = rules.rebuilt(truth, own, own_names)
    report = verify(doc, graded, spec=spec, journal=journal, prompt_level=prompt_level)
    result = CheckResult(id=CHECK["id"], name=CHECK["name"], weight=CHECK["weight"], credit=0.0,
                         hard_fail=bool(CHECK["hard_fail"]), in_scope=True)
    if report.design_fingerprint_ok:
        credit, findings = check(doc, truth, spec, reading)
        result.credit = round(min(1.0, max(0.0, float(credit))), 6)
        result.findings = findings
    else:
        result.skipped = True
    report.checks.append(result)
    report.scope = list(report.scope) + [OPEN_BREAKS]
    report.counts = {**report.counts, "sheets": len(reading.sheets) or len(truth.sheets),
                     "breaks": len(reading.breaks)}
    return report


__all__ = ["CHECK", "PARTS", "PlanSheet", "Reading", "read", "check", "verify_open"]
