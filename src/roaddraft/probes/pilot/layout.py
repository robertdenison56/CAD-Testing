"""Pilots 4, 17 and 5: layout decisions on the real sheets.

The 33 probes hand the model one alignment at a time on a sheet whose layout
is already decided. These three take that away.

**Pilot 4, crowded annotation** (``p04-crowded-*``). A real Caltrans layout
with every alignment's annotation stripped: L-1 (PPM-045, three lines, D13,
TB2 and TB1) and L-7 (PPM-050, the Route 65 / Ferrari Ranch Road
interchange, five lines, D13, F3, F6, FR and F2, around a loop ramp), both
twisted (-89.94 and -131.21 degrees). The model letters all the lines at
once: ticks and station numbers, BC/EC, bearings and lengths, curve
bubbles and one CURVE DATA table per line with curves. What makes it hard
is room: on L-7 the engine's default poses put nine labels on other
lettering (the sheet's 180 surviving callouts, or another line's labels)
and the four tables land on top of each other, so the model has to look at
the sheet and move labels to the other side of a line, further off it, or
along a tangent. Graded with the E1 verifier (``roaddraft.verify.verify``):
``tasks.real.build_real_task`` gives one truth per (sheet, line), and each
is verified on the same submitted document. Every truth lists the start
document's entities as ``given_entities``, so overlaps among the real
sheet's own lettering are not charged, while an overlap between two new
labels -- of the same line or of two different lines -- is (the verifier
only forgives pairs that are both given). Per line: ticks, station numbers,
BC/EC and curve numbers, bearings, the table, labels at their anchors,
layers and heights (D1-02 to D1-07, D1-09; a duplicate or wrong value
fails the item even where E1 only notes it); once for the sheet: D1-08
(no overlaps, no line through text, nothing cut by the viewport, off the
sheet or upside down). Two checks of this module's own sit beside E1: every
station number and bearing runs along its line and every BC/EC square to
it, as plotted (E1 accepts a ``rotation`` override that turns a bearing
off its line), and each table's title names its line (four tables on one
sheet are otherwise unreadable). The sheet's own entities must all still
be there.

**Pilot 17, twisted variants** (``p17-twist-*``). GPT-6.1-Sol's only miss on
the 33 was a bearing lettered at 0 degrees where its line ran at 5.03
degrees through a twisted viewport. Here a real sheet's viewport is re-cut
at a new twist, keeping its scale and the model: Caltrans PD-1 (PPM-160,
Route 78) turned half a turn so "NWR" stations run right to left (twist 28
to -152), and the FDOT drainage plan sheet 1 (FDOT-916) turned so CL1's
first tangent climbs at 37 degrees on the paper (twist -148.34 to -113,
viewport fitted to the usable area and centred on the line). The plan
callouts drawn for the old view are taken off (the ``real-annotate-sheet``
start empties the sheet the same way), the base files' remaining lettering
is turned half a turn where it would read upside down at the new twist,
and the line itself is stripped. The ask is the ``real-alignment-data``
job for that line, graded like pilot 4: ``build_real_task``'s truth (the
labels' content does not depend on the twist; visibility, clipping and
upside-down text are judged through the document's re-cut viewport) plus
this module's orientation check, which is what catches a station number or
bearing set along the line but reading from the wrong side (E1 accepts any
paper rotation up to 135 degrees). Both twists are chosen so that
lettering without the viewport's twist (no ``view_rotation``) reads upside
down; on PD-1 so does lettering with the published twist. A straight line
cannot trap both mistakes at one twist (the two fail on complementary
halves of the circle), which is why there are two instances.

**Pilot 5, the model picks the sheet breaks** (``p05-breaks-*``). A fresh
sheet file that references the base files of a long alignment and has no
sheets: FDOT's SR 50 (CL1 of the FDOT-904 landscape plan's base, 472+00 to
490+00, on the FDOT 11 x 17 border) and CFL's sample main road (CL1 of
CFL-D-Plan-and-Profile, 10+00 to 25+00, on the Federal Lands 11 x 17
border). The model chooses how many sheets at 1" = 50', where to break,
each viewport's twist so stationing reads left to right, and draws a
lettered match line (MATCH LINE STA xx+xx.xx) at each break on both
sheets. Graded from the sheets as they plot (``probes.plotted``): every
sheet that shows the stretch is on the stated border at 1" = 50' with its
viewports inside the usable area; every station A to B shows inside a
viewport; the breaks are read from the lettered match lines, each on
exactly the two sheets it joins with the same station; each sheet shows
all of its own stretch (break to break) with CL1 running left to right
(positive paper x component at every 5 ft); each match line crosses CL1
within 1 ft of its lettered station, square to it within 1 degree on the
paper and at least 40 ft each side, lettered along itself; and the sheet
count is at most the fewest that can do it plus one (worked out here by a
greedy fit of the stretch into the border's usable area over every twist
that keeps it left to right; greedy is optimal for covering an interval.
Both stretches need 2, each run corner to corner, so 3 sheets cut the
conventional way pass and 4 fail).
"""
from __future__ import annotations

import copy
import math
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import compile_label
from roaddraft.document.entities import Line, Polyline, Table, Text
from roaddraft.document.fileformat import write_document
from roaddraft.document.references import find_reference_alignment
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common
from roaddraft.tasks import real
from roaddraft.tasks.brief import GroundTruth
from roaddraft.tasks.reference import phase_commands
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1 as SPEC
from roaddraft.verify import verify
from roaddraft.verify.context import Context
from roaddraft.verify.legibility import (
    OVERLAP_EPS_IN, crosses, overlap_depth, reads_upside_down, reference_items, sheet_items,
    sheet_strokes, text_quad,
)

TABLE_LAYER = SPEC["layers"]["tables"]          # align_CURVE-DATA
TABLE_HEIGHT_IN = float(SPEC["text"]["table_height_in"])
TURN_DEG = 2.0            # how far lettering may turn off its line (or off square to it)
READ_TOL_DEG = 1.0        # past the reading range before text reads from the wrong side


# =================================================================== shared


def _sheet(session: Session, name: str):
    return next((s for s in session.doc.sheets.values() if s.name == name), None)


def _given(session: Session, sheet_name: str) -> List[str]:
    """What the start document holds: the sheet's entities and the file's model."""
    sheet = _sheet(session, sheet_name)
    return sorted((set(sheet.entities) if sheet is not None else set())
                  | set(session.doc.model_entities))


def _q(text: str) -> str:
    return '"' + " ".join(str(text).split()) + '"'


def _add_layers(session: Session) -> None:
    """The spec's layer set, as a real Caltrans sheet file carries it."""
    for name in SPEC["layer_set"]:
        if name not in session.doc.layers:
            common.ok(session.execute("create_layer", {"name": name, **SPEC["layer_props"][name]}))


# ============================================================ lettering (4, 17)

#: the groups a whole-alignment lettering job asks for (``real-alignment-data``)
LETTER_GROUPS = ("ticks", "stations", "curve_points", "bearings", "callouts", "table")
#: what each E1 check grades here, by item
LETTER_CHECKS = (("D1-02", "station ticks"), ("D1-03", "station numbers"),
                 ("D1-04", "BC/EC and curve numbers"), ("D1-05", "bearings and lengths"),
                 ("D1-06", "CURVE DATA table"), ("D1-07", "labels sit at their anchors"),
                 ("D1-09", "layers and text heights"))
#: finding codes that fail an item (E1 credits a label with a duplicate beside it; a
#: line lettered twice is not done here)
BAD_CODES = ("missing", "wrong_value", "not_visible", "duplicate", "misplaced",
             "anchor_inconsistent", "wrong_layer", "wrong_height", "wrong_layer_props",
             "wrong_field", "geometry_mismatch")


@lru_cache(maxsize=None)
def _task(sheet_id: str, name: str):
    """The ``real-alignment-data`` task for one line (``real-bearings`` for a line
    with no curve, whose truth carries its ticks and station numbers all the same)."""
    why = None
    for kind in ("real-alignment-data", "real-bearings"):
        try:
            return real.build_real_task(sheet_id, name, kind)
        except ValueError as e:
            why = e
    raise RuntimeError(f"{sheet_id} {name}: {why}")


def _truth(sheet_id: str, name: str, given: Sequence[str]) -> GroundTruth:
    """One line's E1 truth, graded against this pilot's start: the whole lettering
    job (for a line with no curve, its ticks, station numbers and bearings only),
    with the start's entities given, so only new work is charged for overlaps."""
    truth = GroundTruth.from_dict(copy.deepcopy(_task(sheet_id, name).truth.to_dict()))
    curved = bool(truth.curve_tables)
    truth.scope = [g for g in LETTER_GROUPS if curved or g in ("ticks", "stations", "bearings")]
    for sh in truth.sheets:
        sh["given_entities"] = list(given)
        sh.pop("stripped", None)
    return truth


def _qualified(sheet_id: str, name: str) -> str:
    return f"{_task(sheet_id, name).brief.deliverable['design_reference']}:{name}"


def _content_of(session: Session, eid: str) -> str:
    """A finding's entity, as a reader sees it."""
    ref, sep, local = eid.rpartition(":")
    if sep:
        from roaddraft.document.references import reference_groups
        for r, _base, prims in reference_groups(session.doc, "model"):
            if r.name == ref:
                hit = next((p for p in prims if p.id == local and isinstance(p, Text)), None)
                if hit is not None:
                    return f"{ref}'s {_q(hit.content)}"
        return f"{ref}'s {local}"
    e = session.doc.model_entities.get(eid)
    if e is None:
        for sh in session.doc.sheets.values():
            e = sh.entities.get(eid) or e
    if isinstance(e, Text):
        return _q(e.content)
    if isinstance(e, Table):
        return f"the table {_q(e.title or eid)}"
    return eid


def _finding(session: Session, f) -> str:
    who = ", ".join(_content_of(session, i) for i in f.entity_ids) or ""
    anchor = f"{f.anchor.get('ref')} {f.anchor.get('kind')}" if f.anchor else ""
    text = f"{f.code}: {anchor or who}"
    if anchor and who:
        text += f" ({who})"
    if f.note:
        text += f" -- {f.note}"
    if f.code in ("wrong_value", "wrong_height", "wrong_layer") and f.expected is not None:
        text += f"; expected {f.expected!r}, found {f.actual!r}"
    return text[:300]


def _orientation_problems(session: Session, sheet_name: str, qualified: str) -> List[str]:
    """Lettering of one line that does not run along it (station numbers,
    bearings) or square to it (BC/EC), as plotted, or that reads from the wrong
    side: along the line upright in (-90, 90], square to it bottom to top in
    (-45, 135]."""
    found = find_reference_alignment(session.doc, qualified)
    sheet = _sheet(session, sheet_name)
    if found is None or sheet is None or not sheet.viewports:
        return []
    align, _place = found
    name = qualified.split(":", 1)[1]
    vp = sheet.viewports[0]
    t, twist = vp.transform(), float(vp.rotation_deg)
    begin = float(align.begin_station)
    out = []
    spaces = [("model", e) for e in session.doc.model_entities.values()]
    spaces += [("sheet", e) for e in sheet.entities.values()]
    for space, e in spaces:
        rec = (e.anchor or {}) if isinstance(e, Text) else {}
        if rec.get("alignment") not in (name, qualified):
            continue
        kind = rec.get("kind")
        if kind not in ("station", "bearing", "pc", "pt", "pcc", "prc"):
            continue
        station = rec.get("station")
        if station is None:
            continue
        if space == "model":
            if not geo.bbox_contains(vp.paper_bbox(), (*t.to_paper(e.position),
                                                       *t.to_paper(e.position))):
                continue
            rot = float(e.rotation_deg) + twist
        else:
            rot = float(e.rotation_deg)
        dist = min(max(float(station) - begin, 0.0), align.length)
        line = align.direction_at(dist) + twist
        want = line if kind in ("station", "bearing") else line + 90.0
        what = f"{_q(e.content)} ({kind} at {align.stations().format(float(station))})"
        if pl.turn_between(rot, want, 180.0) > TURN_DEG:
            how = "along" if kind in ("station", "bearing") else "square to"
            out.append(f"{what} is lettered at {pl.wrap(rot):.1f}° on the sheet; {how} the line "
                       f"there is {pl.wrap(want) % 180.0:.1f}°")
            continue
        r = pl.wrap(rot)
        if kind in ("station", "bearing"):
            bad = not (-90.0 - READ_TOL_DEG < r <= 90.0 + READ_TOL_DEG)
        else:
            bad = reads_upside_down(r)
        if bad:
            out.append(f"{what} reads from the wrong side of the sheet ({r:.1f}° as plotted)")
    return out


def _base_lettering(session: Session) -> set:
    """``(reference, id, content)`` of every text the referenced base files hold."""
    from roaddraft.document.references import reference_groups
    return {(r.name, e.id, e.content) for r, _base, prims in reference_groups(session.doc, "model")
            for e in prims if isinstance(e, Text)}


def _grade_lettering(baseline: Session, submitted: Session, sheet_id: str, sheet_name: str,
                     names: Sequence[str], tally: Tally) -> None:
    """Add every graded item of lettering ``names`` on ``sheet_name`` to ``tally``."""
    given = _given(baseline, sheet_name)
    sheet_b, sheet_s = _sheet(baseline, sheet_name), _sheet(submitted, sheet_name)
    if sheet_s is None:
        tally.add(f"sheet {sheet_name}", f"sheet {sheet_name} is gone")
        return
    gone = sorted(set(sheet_b.entities) - set(sheet_s.entities))
    tally.add("the sheet's own work kept",
              f"{len(gone)} of the sheet's own entities were removed "
              f"({', '.join(_content_of(baseline, i) for i in gone[:4])})" if gone else None)
    # the viewport is the task's (a re-cut twist turned back would letter the old sheet)
    def view(sheet):
        return [(round(float(v.rotation_deg), 3), round(float(v.feet_per_inch), 3),
                 [round(float(c), 2) for c in v.center_paper], round(float(v.width_in), 2),
                 round(float(v.height_in), 2), [round(float(c), 2) for c in v.model_center])
                for v in sheet.viewports]
    tally.add("the sheet's viewport kept", None if view(sheet_b) == view(sheet_s) else
              f"the viewport of {sheet_name} was changed (twist, scale or window)")
    lost = _base_lettering(baseline) - _base_lettering(submitted)
    tally.add("the base files' lettering kept", f"{len(lost)} of the base files' texts are gone "
              f"or changed ({', '.join(_q(c) for _r, _i, c in sorted(lost)[:3])})" if lost else None)
    legibility = None
    for name in names:
        truth = _truth(sheet_id, name, given)
        report = verify(submitted.doc, truth)
        line = _q(name)
        if not report.design_fingerprint_ok:
            tally.add(f"{line}: the design", f"the design of {line} was changed")
            continue
        by_id = {c.id: c for c in report.checks}
        for cid, what in LETTER_CHECKS:
            c = by_id.get(cid)
            if c is None or not c.in_scope:
                continue
            bad = [f for f in c.findings if f.code in BAD_CODES]
            problem = None
            if c.credit < 1.0 - 1e-9 or bad:
                first = _finding(submitted, bad[0]) if bad else f"credit {c.credit:.2f}"
                problem = f"{line} {what}: {first}"
                if len(bad) > 1:
                    problem += f" (and {len(bad) - 1} more)"
            tally.add(f"{line}: {what}", problem)
        problems = _orientation_problems(submitted, sheet_name, _qualified(sheet_id, name))
        tally.add(f"{line}: lettering along (BC/EC square to) its line and reading from the "
                  f"bottom or right", f"{line}: {problems[0]}" + (
                      f" (and {len(problems) - 1} more)" if len(problems) > 1 else "")
                  if problems else None)
        if truth.curve_tables:
            titles = [e.title or "" for e in sheet_s.entities.values()
                      if isinstance(e, Table) and (e.anchor or {}).get("kind") == "curve_table"
                      and (e.anchor or {}).get("alignment") in (name, _qualified(sheet_id, name))]
            named = [t for t in titles if re.search(rf"(?<![A-Z0-9]){re.escape(name)}(?![A-Z0-9])",
                                                     t.upper())]
            tally.add(f"{line}: its table's title names the line",
                      None if named else f"no CURVE DATA table titled with {line}"
                      + (f" (titles: {', '.join(_q(t) for t in titles)})" if titles else ""))
        if legibility is None:
            legibility = by_id.get("D1-08")
    if legibility is not None:
        problem = None
        if legibility.credit < 1.0 - 1e-9 or legibility.findings:
            fs = legibility.findings
            problem = (f"{len(fs)} legibility problem(s) on {sheet_name}: "
                       + "; ".join(_finding(submitted, f) for f in fs[:3]))
        tally.add("legibility: nothing over other lettering, under a leader, cut by the "
                  "viewport, off the sheet or upside down", problem)


# ------------------------------------------------------------ the scripted lettering

#: where a label may go when its first pose is taken (paper inches off the line)
OFFSETS_IN = {"station": (0.12, 0.24, 0.36), "pc": (0.45, 0.75, 1.05, 1.35),
              "pt": (0.45, 0.75, 1.05, 1.35), "pcc": (0.45, 0.75, 1.05, 1.35),
              "prc": (0.45, 0.75, 1.05, 1.35), "bearing": (0.06, 0.2, 0.35, 0.5),
              "mc": (0.8, 1.2, 1.6, 2.0)}
#: a bearing may also slide along its tangent (d1-verify-v5 reads a bearing anchored at
#: a station inside the tangent as that tangent's)
BEARING_SLIDE = (0.5, 0.35, 0.65, 0.2, 0.8)
#: which labels move first when two collide
MOVE_ORDER = {"mc": 0, "bearing": 1, "pc": 2, "pt": 2, "pcc": 2, "prc": 2, "station": 3}
OUT_COST = 100


class _Placer:
    """What a finished sheet shows, in paper inches, for choosing clear poses:
    the start's lettering (sheet, model and the base files'), fixed, and the
    lettering added since, re-read on demand."""

    def __init__(self, session: Session, truth: GroundTruth, given: Sequence[str]):
        self.session, self.truth, self.given = session, truth, set(given)
        ctx = Context.build(session.doc, truth, SPEC)
        sv = ctx.sheets[0]
        self.sheet_name = sv.name
        self.view = sv.views[0]
        self.usable = sv.usable
        items = sheet_items(ctx, sv) + reference_items(ctx, sv)
        self.static = [it for it in items if self._given(it.entity_id)]
        self.strokes = [s for s in sheet_strokes(ctx, sv) if self._given(s.entity_id)]

    def _given(self, eid: str) -> bool:
        return eid in self.given or ":" in eid

    def added(self):
        ctx = Context.build(self.session.doc, self.truth, SPEC)
        return [it for it in sheet_items(ctx, ctx.sheets[0]) if not self._given(it.entity_id)]

    def cost(self, quad, own: Sequence[str], added=None) -> int:
        added = self.added() if added is None else added
        box = geo.bbox_of_points(quad)
        c = 0
        for it in self.static + added:
            if it.entity_id in own or not geo.bbox_intersects(box, it.box):
                continue
            if overlap_depth(quad, it.quad) > OVERLAP_EPS_IN:
                c += 1
        for s in self.strokes:
            if geo.bbox_intersects(box, s.box) and crosses(s.a, s.b, quad):
                c += 1
        win = self.view.window
        if win is None or not all(win[0] <= v[0] <= win[2] and win[1] <= v[1] <= win[3]
                                  for v in quad):
            c += OUT_COST
        return c


def _mc_box(center, h_in: float):
    r = float(SPEC["labels"]["mc"]["bubble"]["radius_text_heights"]) * h_in
    return [[center[0] - r, center[1] - r], [center[0] + r, center[1] - r],
            [center[0] + r, center[1] + r], [center[0] - r, center[1] + r]]


def _label_quad(placer: _Placer, align: Alignment, anchor: str, kind: str, side: str,
                offset_ft: float, content: str, height_ft: float, vr: float):
    ap = resolve_anchor(align, parse_anchor(anchor))
    spec = compile_label(align, ap, kind, side=side, label_offset=offset_ft, content=content,
                         view_rotation=vr)
    vp = placer.view.vp
    fpi, twist = float(vp.feet_per_inch), float(vp.rotation_deg)
    p = placer.view.transform.to_paper(spec.position)
    if kind == "mc":
        return _mc_box(p, height_ft / fpi)
    return text_quad(p, content, height_ft / fpi, spec.rotation_deg + twist, spec.halign,
                     spec.valign)


def _options(align: Alignment, rec: dict, kind: str) -> List[Tuple[str, str, float]]:
    """``(anchor, side, offset in)`` to try for one label, its own pose first."""
    first = rec.get("side") or "left"
    other = "right" if first == "left" else "left"
    anchors = [rec["ref"]]
    if kind == "bearing":
        n = None
        if str(rec["ref"]).startswith("T-"):
            n = int(str(rec["ref"])[2:])
        else:
            try:
                n = resolve_anchor(align, parse_anchor(rec["ref"])).tangent_index
            except DesignError:
                n = None
        if n:
            tan = align.tangents()[n - 1]
            begin = float(align.begin_station)
            anchors = [align.stations().format(begin + tan.start_dist + f * tan.length)
                       for f in BEARING_SLIDE]
    out = []
    for off in OFFSETS_IN[kind]:
        for anchor in anchors:
            for side in (first, other):
                out.append((anchor, side, off))
    return out


def _group(session: Session, rec: dict) -> List[str]:
    """A label's entities: its text, and a curve bubble's circle and leader."""
    kinds = ("mc", "mc_bubble", "mc_leader") if rec.get("kind") == "mc" else (rec.get("kind"),)
    return [e.id for e in session.doc.model_entities.values()
            if (e.anchor or {}).get("alignment") == rec.get("alignment")
            and (e.anchor or {}).get("ref") == rec.get("ref")
            and (e.anchor or {}).get("kind") in kinds]


def _repair(session: Session, placer: _Placer, rounds: int = 4) -> None:
    """Re-place each added label that lands on something, at the clearest of
    its other poses (the other side, further off, along its tangent)."""
    for _round in range(rounds):
        added = placer.added()
        bad = []
        for it in added:
            e = session.doc.model_entities.get(it.entity_id)
            if not isinstance(e, Text) or not e.anchor or e.anchor.get("kind") not in MOVE_ORDER:
                continue
            c = placer.cost(it.quad, [it.entity_id], added)
            if c:
                bad.append((MOVE_ORDER[e.anchor["kind"]], -c, e.id))
        if not bad:
            return
        moved = False
        for _order, _c, eid in sorted(bad):
            e = session.doc.model_entities.get(eid)
            if e is None:
                continue
            rec = dict(e.anchor)
            kind = rec["kind"]
            found = find_reference_alignment(session.doc, rec["alignment"])
            if found is None:
                continue
            align = found[0]
            added = placer.added()
            own = _group(session, rec)
            now = next((placer.cost(it.quad, own, added) for it in added if it.entity_id == eid),
                       OUT_COST)
            vr = float(rec.get("view_rotation") or 0.0)
            fpi = float(placer.view.vp.feet_per_inch)
            best = None
            for anchor, side, off in _options(align, rec, kind):
                try:
                    quad = _label_quad(placer, align, anchor, kind, side, off * fpi, e.content,
                                       float(e.height), vr)
                except DesignError:
                    continue
                c = placer.cost(quad, own, added)
                if best is None or c < best[0]:
                    best = (c, anchor, side, off)
                if c == 0:
                    break
            if best is None or best[0] >= now:
                continue
            common.ok(session.execute("delete_entities", {"ids": own}))
            common.ok(session.execute("place_label", {
                "space": "model", "alignment": rec["alignment"], "anchor": best[1], "kind": kind,
                "content": e.content, "side": best[2], "label_offset": round(best[3] * fpi, 3),
                "height": float(e.height), "layer": e.layer, "view_rotation": vr}))
            moved = True
        if not moved:
            return


def _place_tables(session: Session, placer: _Placer, sheet_id: str, names: Sequence[str],
                  sheet_name: str) -> None:
    """One CURVE DATA table per line with curves, each in the clear space of the
    finished sheet nearest its lower right corner, titled with its line."""
    from roaddraft.tasks.generator import _table_size
    sheet = _sheet(session, sheet_name)
    usable = tuple(sheet.usable_area())
    for name in names:
        task = _task(sheet_id, name)
        if not task.truth.curve_tables:
            continue
        D = task.brief.deliverable
        align = Alignment.from_dict(task.brief.design["alignments"][name])
        curves = D["sheets"][0]["curves"]
        title = f'CURVE DATA "{name}" LINE'
        w, h = _table_size(align, curves, D["curve_table_columns"], TABLE_HEIGHT_IN)
        w = max(w, geo.text_size(title, TABLE_HEIGHT_IN, 1.0)[0] + 0.2)
        grid = real.occupancy(session.doc, sheet_name)
        prefer = [usable[2] - w - 0.3, usable[1] + h + 0.3]
        spot = real.table_spot(grid, usable, w, h, prefer)
        if spot is None:  # no space clear of linework too: clear of lettering will do
            added = placer.added()
            best = None
            for y in np.arange(usable[1] + h + 0.2, usable[3] - 0.2, 0.25):
                for x in np.arange(usable[0] + 0.2, usable[2] - w - 0.2, 0.25):
                    pad = 0.1
                    quad = [[x - pad, y - h - pad], [x + w + pad, y - h - pad],
                            [x + w + pad, y + pad], [x - pad, y + pad]]
                    c = placer.cost(quad, [], added)
                    d = (x - prefer[0]) ** 2 + (y - prefer[1]) ** 2
                    if c == 0 and (best is None or d < best[0]):
                        best = (d, [round(float(x), 2), round(float(y), 2)])
            spot = best[1] if best else prefer
        common.ok(session.execute("place_curve_table", {
            "space": sheet_name, "alignment": _qualified(sheet_id, name), "position": spot,
            "columns": list(D["curve_table_columns"]), "text_height": TABLE_HEIGHT_IN,
            "layer": TABLE_LAYER, "title": title}))


def _letter(session: Session, sheet_id: str, sheet_name: str, names: Sequence[str]) -> None:
    """The scripted lettering: each line with the engine's labelers at the
    sheet's own twist, the tables, then every label that lands on something
    re-placed where it clears."""
    sheet = _sheet(session, sheet_name)
    twist = float(sheet.viewports[0].rotation_deg)
    given = _given(session, sheet_name)
    for name in names:
        task = copy.deepcopy(_task(sheet_id, name))
        D = task.brief.deliverable
        if abs(float(D.get("view_rotation") or 0.0) - twist) > 1e-6:
            D["view_rotation"] = twist  # a re-cut sheet: the poses chosen for the old view go
            D.pop("label_poses", None)
        for command, params in phase_commands(task, ["stationing", "bearings", "callouts"]):
            common.ok(session.execute(command, params))
    placer = _Placer(session, _truth(sheet_id, names[0], given), given)
    _repair(session, placer)
    _place_tables(session, placer, sheet_id, names, sheet_name)
    _repair(session, placer)


#: the lettering conventions, as the benchmark's explicit prompt states them
CONVENTIONS = (
    "- A station tick every 100 ft, 0.14 in long on paper and centered on the line, on layer "
    "align_MAIN-anno.\n"
    "- Its station number under each tick, below the line and reading along it, lettered the "
    "Caltrans way: the whole station number at every 500 ft station ({whole}) and only "
    "the ones digit at the others (1, 2, 3, 4), 0.10 in high on paper, on layer align_MAIN-anno.\n"
    "- The beginning and end of every curve lettered with its station to the hundredth "
    "followed by BC or EC (24+05.27 BC form), square to the line on its left and reading "
    "bottom to top, 0.10 in high on paper, on layer align_MAIN-anno.\n"
    "- The number of every curve in a bubble off the middle of the curve on its right, with a "
    "leader from the bubble to the curve, 0.10 in high on paper, on layer align_MAIN-anno; "
    "each line numbers its own curves 1, 2, ... along it.\n"
    "- The bearing and length of every tangent as one line of text beside it, above the line "
    "and parallel to it (quadrant bearing to the second and length to 0.01 ft: "
    "N 71°33'54\" E 1240.36' form), 0.10 in high on paper, on layer align_MAIN-anno.\n"
    "- A CURVE DATA table on the sheet for each line that has curves, titled with the line "
    "(CURVE DATA \"F3\" LINE): one row per curve, columns No., R, Δ, T, L, lengths to 0.01 ft "
    "and angles in degrees-minutes-seconds, text 0.12 in high, on layer align_CURVE-DATA, "
    "inside the border and clear of the title block.\n"
    "Letter them with the design's own labels, anchored through the reference, so they stay "
    "tied to the design: to clear something, re-place a label (the other side of the line, "
    "further off it, or along its tangent) rather than dragging it off its anchor.")


def _strip(out: Path, sheet_id: str, names: Sequence[str]):
    """Stage a sheet's file set in ``out`` with ``names``' annotation removed
    from the sheet file and the base files; returns (sheet doc, bases, sheet file)."""
    src = real.real_sheet(sheet_id)
    common.stage(out, sheet_id)
    work = common.document(out / src.sheet_file)
    bases = {n: common.document(out / n) for n in src.files if n != src.sheet_file}
    for name in names:
        task = _task(sheet_id, name)
        align = Alignment.from_dict(task.brief.design["alignments"][name])
        real.strip_alignment(work, bases, task.brief.deliverable["design_file"], align,
                             task.truth.labels)
        _strip_reversed(work, bases, align, task.truth.labels)
        _strip_rings(work, align)
        _strip_traced(work, bases, STALE_TRACED.get(sheet_id, {}).get(name, ()))
    return work, bases, src.sheet_file


#: a curve bubble digitised as a ring of vertices (S-ANNO-TAG polylines) is no
#: Circle, so strip_alignment leaves it: its size and reach, paper inches
RING_MAX_IN = 0.5
RING_REACH_IN = 2.5
#: published lettering that survives only as strokes in a base file (a trace layer,
#: traced.py, or the road layers the digitiser used): paper boxes and layers per sheet
#: and line, gone with the line's annotation
STALE_TRACED = {"PPM-050": {"F3": [((13.2, 12.95, 16.3, 13.4),      # '"F3" 705+03.23 BC'
                                    ("V-ANNO-TRACE", "V-ROAD", "V-ROAD-THIN", "V-ROAD-HTCH"))]}}


def _ring_center(e):
    pts = [list(v) for v in e.vertices] if isinstance(e, Polyline) else []
    if len(pts) < 8:
        return None
    bb = geo.bbox_of_points(pts)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    if not (0.05 <= w <= RING_MAX_IN and abs(w - h) <= 0.1 * max(w, h)):
        return None
    return [(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0], max(w, h) / 2.0


def _strip_rings(work, align: Alignment) -> List[str]:
    """The line's curve bubbles drawn as rings: the ring, the number in it and
    the leader from it."""
    sheet = next(iter(work.sheets.values()))
    vp = sheet.viewports[0]
    t = vp.transform()
    mids = [t.to_paper(align.point_at(c.start_dist + c.length / 2.0)) for c in align.curves()]
    gone = []
    for e in list(sheet.entities.values()):
        ring = _ring_center(e)
        if ring is None:
            continue
        center, radius = ring
        if not any(geo.distance(center, m) <= RING_REACH_IN for m in mids):
            continue
        gone.append(e.id)
        for o in list(sheet.entities.values()):
            if isinstance(o, Text) and o.content.strip().isdigit() and geo.distance(
                    o.position, center) <= 1.3 * radius:
                gone.append(o.id)
            elif isinstance(o, Line) and min(geo.distance(o.start, center),
                                             geo.distance(o.end, center)) <= radius + 0.05:
                gone.append(o.id)
    for i in gone:
        sheet.entities.pop(i, None)
    return gone


def _strip_traced(work, bases, boxes) -> List[str]:
    """Strokes of the line's lettering left in the base files, by paper box and layer."""
    if not boxes:
        return []
    sheet = next(iter(work.sheets.values()))
    to_paper = sheet.viewports[0].transform().to_paper
    gone = []
    for doc in bases.values():
        for e in list(doc.model_entities.values()):
            pts = ([list(e.start), list(e.end)] if isinstance(e, Line)
                   else [list(v) for v in e.vertices] if isinstance(e, Polyline) else [])
            paper = [to_paper(p) for p in pts]
            if paper and any(e.layer in layers and all(
                    b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for p in paper)
                             for b, layers in boxes):
                del doc.model_entities[e.id]
                gone.append(e.id)
    return gone


REVERSED_REACH_IN = 1.0   # a tangent's bearing lettered the other way, within this of it
#: a curve point called out with its line's name: '"F3" 705+03.23 BC'
NAMED_POINT = re.compile(r"[\"“”]\s*([A-Z0-9]+)\s*[\"“”]\s*(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)\s*"
                         r"(?:BCC|ECC|PCC|PRC|BC|EC)\b")


def _strip_reversed(work, bases, align: Alignment, truth_labels) -> List[str]:
    """What ``strip_alignment`` leaves of a line's published annotation: a
    tangent's bearing lettered against the stationing (L-7's F6 tangent reads
    S45°15'06"E on the sheet, N 45°13'54" W along its rebuilt stationing), and
    BC/EC callouts that name the line, on leaders further off than it looks."""
    flip = {"N": "S", "S": "N", "E": "W", "W": "E"}
    wanted = [real._bearings_in(l["content"])[0] for l in truth_labels
              if l["kind"] == "bearing" and real._bearings_in(l["content"])]
    back = [(flip[b[0]], b[1], b[2], flip.get(b[3]) if b[3] else None) for b in wanted]
    tangents = list(zip(back, align.tangents()))
    sheet = next(iter(work.sheets.values()))
    vp = sheet.viewports[0]
    t, fpi = vp.transform(), float(vp.feet_per_inch)
    gone = []

    def hits(text: Text, at) -> bool:
        for b in real._bearings_in(text.content):
            for tb, tan in tangents:
                if real._same_bearing(b, tb) and geo.dist_point_to_segment(
                        at, tan.start, tan.end) <= REVERSED_REACH_IN * fpi:
                    return True
        return False

    for doc in bases.values():
        for e in list(doc.model_entities.values()):
            if isinstance(e, Text) and hits(e, e.position):
                del doc.model_entities[e.id]
                gone.append(e.id)
    # the published BC/EC callouts that name the line ('"F3" 705+03.23 BC'), set off on a
    # leader further than strip_alignment looks, and their leaders
    points = [float(l["station"]) for l in truth_labels if l["kind"] in ("pc", "pt", "pcc", "prc")]
    quads = []
    for e in list(sheet.entities.values()):
        if not isinstance(e, Text):
            continue
        if hits(e, t.to_model(e.position)) or any(
                m.group(1) == align.name and any(
                    abs(int(m.group(2)) * 100.0 + float(m.group(3)) - p) <= real.STATION_TOL_FT
                    for p in points)
                for m in NAMED_POINT.finditer(e.content)):
            quads.append(real._quad(e, work))
            del sheet.entities[e.id]
            gone.append(e.id)
    for i in real._leaders(sheet.entities, quads, 1.0):
        sheet.entities.pop(i, None)
        gone.append(i)
    return gone


def _write(out: Path, work, bases, sheet_file: str) -> Path:
    for n, d in bases.items():
        write_document(out / n, d.to_dict())
    write_document(out / sheet_file, work.to_dict())
    session = common.load(out / sheet_file)
    _add_layers(session)
    return common.save(session, out / sheet_file)


# ================================================================ pilot 4

P4 = {
    "p04-crowded-ppm045": {"sheet_id": "PPM-045", "sheet": "L-1", "ref": "AA01",
                           "whole": "640, 645", "names": ("D13", "TB2", "TB1")},
    "p04-crowded-ppm050": {"sheet_id": "PPM-050", "sheet": "L-7", "ref": "AA01",
                           "whole": "705, 710", "names": ("D13", "F3", "F6", "FR", "F2")},
}


def _p4_builder(pid: str):
    cfg = P4[pid]

    def build(out: Path) -> Path:
        work, bases, sheet_file = _strip(Path(out), cfg["sheet_id"], cfg["names"])
        return _write(Path(out), work, bases, sheet_file)
    return build


def _p4_check(pid: str):
    cfg = P4[pid]

    def check(baseline: Session, submitted: Session) -> Result:
        tally = Tally()
        _grade_lettering(baseline, submitted, cfg["sheet_id"], cfg["sheet"], cfg["names"], tally)
        return tally.result(f"all {len(cfg['names'])} lines of {cfg['sheet']} lettered in full "
                            f"and to the spec, every table titled with its line, and nothing over "
                            f"anything")
    return check


def _p4_solve(pid: str):
    cfg = P4[pid]

    def solve(session: Session) -> None:
        _letter(session, cfg["sheet_id"], cfg["sheet"], cfg["names"])
    return solve


def _p4_prompt(pid: str) -> str:
    cfg = P4[pid]
    names = cfg["names"]
    ref = cfg["ref"]
    lines = ", ".join(f'"{n}"' for n in names[:-1]) + f' and "{names[-1]}"'
    return (f"Sheet {cfg['sheet']} of this Caltrans layout has lost the alignment data of all "
            f"{len(names)} of its lines: {lines} (alignments {', '.join(names)} of the base file "
            f"attached as {ref}, reached as {ref}:{names[0]} and so on). Letter all of them, in "
            f"this sheet file, for every line the way a Caltrans layout shows it:\n"
            + CONVENTIONS.format(whole=cfg["whole"]) +
            f"\nThe sheet is crowded: nothing you add may sit on other lettering (the sheet's "
            f"own, the base file's, or another line's), run under a leader, be cut by the edge of "
            f"the viewport, leave the border or read upside down as plotted. Keep everything "
            f"already on the sheet.")


# ================================================================ pilot 17

P17 = {
    # the published PD-1 turned 180 degrees: "NWR" stations run right to left
    "p17-twist-ppm160": {"sheet_id": "PPM-160", "sheet": "PD-1", "name": "NWR", "ref": "AA01",
                         "agency": "Caltrans", "whole": "840, 845", "turn": 180.0},
    # FDOT drainage plan sheet 1 turned so CL1's first tangent climbs at 37 degrees
    "p17-twist-fdot916": {"sheet_id": "FDOT-916-1-Drainage-Network-Plan-Sheet", "sheet": "1",
                          "name": "CL1", "ref": "ALI", "agency": "FDOT", "whole": "705", "twist": -113.0,
                          "fit": True},
}


def _upright_texts(doc, twist: float) -> int:
    """Turn the base drawing's lettering that would read upside down through a
    viewport at ``twist`` half a turn about its own centre, as a drafter re-reads
    a base for a new sheet; returns how many turned."""
    n = 0
    for e in doc.model_entities.values():
        if not isinstance(e, Text) or not e.content:
            continue
        r = pl.wrap(float(e.rotation_deg) + twist)
        if -90.0 + READ_TOL_DEG < r <= 135.0 + READ_TOL_DEG:
            continue
        style = doc.text_styles.get(e.style)
        quad = text_quad(e.position, e.content, e.height, e.rotation_deg, e.halign, e.valign,
                         style.width_factor if style else 1.0)
        c = [sum(v[0] for v in quad) / 4.0, sum(v[1] for v in quad) / 4.0]
        e.position = [2.0 * c[0] - e.position[0], 2.0 * c[1] - e.position[1]]
        e.rotation_deg = float(e.rotation_deg) + 180.0
        n += 1
    return n


def _p17_builder(pid: str):
    cfg = P17[pid]

    def build(out: Path) -> Path:
        out = Path(out)
        work, bases, sheet_file = _strip(out, cfg["sheet_id"], [cfg["name"]])
        sheet = next(s for s in work.sheets.values() if s.name == cfg["sheet"])
        sheet.entities.clear()  # the plan callouts were drawn for the old view
        vp = sheet.viewports[0]
        if "turn" in cfg:
            vp.rotation_deg = pl.wrap(float(vp.rotation_deg) + cfg["turn"])
        else:
            vp.rotation_deg = float(cfg["twist"])
        if cfg.get("fit"):  # the viewport fills the usable area, centred on the line
            ua = sheet.usable_area()
            vp.center_paper = [round((ua[0] + ua[2]) / 2.0, 3), round((ua[1] + ua[3]) / 2.0, 3)]
            vp.width_in, vp.height_in = round(ua[2] - ua[0], 3), round(ua[3] - ua[1], 3)
            task = _task(cfg["sheet_id"], cfg["name"])
            align = Alignment.from_dict(task.brief.design["alignments"][cfg["name"]])
            pts = [align.point_at(d) for d in np.linspace(0.0, align.length, 60)]
            turned = [geo.rotate_point(p, vp.rotation_deg) for p in pts]
            bb = geo.bbox_of_points(turned)
            centre = geo.rotate_point([(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0],
                                      -vp.rotation_deg)
            vp.model_center = [round(centre[0], 2), round(centre[1], 2)]
        for base in bases.values():
            _upright_texts(base, float(vp.rotation_deg))
        return _write(out, work, bases, sheet_file)
    return build


def _p17_check(pid: str):
    cfg = P17[pid]

    def check(baseline: Session, submitted: Session) -> Result:
        tally = Tally()
        _grade_lettering(baseline, submitted, cfg["sheet_id"], cfg["sheet"], [cfg["name"]],
                         tally)
        return tally.result(f"{_q(cfg['name'])} lettered in full on the re-cut sheet "
                            f"{cfg['sheet']}, every label along (or square to) its line and "
                            f"reading from the bottom or right as plotted")
    return check


def _p17_solve(pid: str):
    cfg = P17[pid]

    def solve(session: Session) -> None:
        _letter(session, cfg["sheet_id"], cfg["sheet"], [cfg["name"]])
    return solve


def _p17_prompt(pid: str) -> str:
    cfg = P17[pid]
    name = cfg["name"]
    ref, agency = cfg["ref"], cfg["agency"]
    how = ("so that it runs the other way: the plan is turned half a turn from the published "
           "sheet" if "turn" in cfg else "at a new twist, so the plan crosses the sheet on a "
                                         "diagonal")
    conventions = CONVENTIONS.format(whole=cfg["whole"]).replace(
        ", titled with the line (CURVE DATA \"F3\" LINE)", f", titled with the line (CURVE DATA "
        f"\"{name}\" LINE)").replace("for each line that has curves", "for the line")
    return (f"Sheet {cfg['sheet']} of this {agency} set has been re-cut {how}, at the same "
            f"scale and on the same base files; the plan callouts drawn for the old view were "
            f"taken off. The {_q(name)} line (alignment {name} of the base file attached as "
            f"{ref}, reached as {ref}:{name}) has no lettering. Letter its alignment data in "
            f"this sheet file:\n" + conventions +
            f"\nEvery piece of lettering must read from the bottom or the right of the sheet as "
            f"it plots and run along its line (BC and EC square to it). Nothing may sit on "
            f"other lettering, be cut by the edge of the viewport or leave the border. Keep "
            f"everything else as it is.")


# ================================================================ pilot 5

P5 = {
    "p05-breaks-fdot904": {
        "sheet_id": "FDOT-904-1-Landscape-Opportunity-Plan", "agency": "FDOT",
        "files": {"ALGNRD01.rdraft": "ALI", "DSGNRD01.rdraft": "COR"},
        "doc": "PLANRD01.rdraft", "alignment": "ALI:CL1", "line": "CL1",
        "a": "472+00.00", "b": "490+00.00", "size": "ANSI_B", "template": "fdot",
        "border": "the FDOT 11 x 17 plan sheet border (ANSI B, title block template fdot)",
        "road": "SR 50 (W Colonial Drive)"},
    "p05-breaks-cfl": {
        "sheet_id": "CFL-D-Plan-and-Profile", "agency": "CFL",
        "files": {"TERSample.rdraft": "SUR", "ALI(MAIN)Sample.rdraft": "ALI",
                  "COR(MAIN)Sample.rdraft": "COR"},
        "doc": "PLA(Sample).rdraft", "alignment": "ALI:CL1", "line": "CL1",
        "a": "10+00.00", "b": "25+00.00", "size": "ANSI_B", "template": "wfl",
        "border": "the Federal Lands 11 x 17 plan sheet border (ANSI B, title block template "
                  "wfl)",
        "road": "the main road"},
}
FPI = 50.0
STEP_FT = 5.0             # stations sampled along the stretch
AIM_FT = 1.0              # a match line within this of its lettered station
SQUARE_DEG = 1.0          # ... square to the line within this on the paper
REACH_FT = 40.0           # ... and running at least this far each side of it
TEXT_NEAR_IN = 0.5        # its lettering within this of it
THETA_STEP = 0.25         # degrees, the twists tried when fitting a stretch
MATCH = re.compile(r"MATCH\s*LINE.*?(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)", re.I | re.S)
ENDS_FT = 1.0             # a "match line" lettered at A or B is not a break


@lru_cache(maxsize=None)
def _usable(size: str, template: str) -> Tuple[float, float, float, float]:
    s = Session()
    common.ok(s.execute("create_sheet", {"name": "X", "size": size,
                                         "title_block_template": template}))
    return tuple(float(v) for v in next(iter(s.doc.sheets.values())).usable_area())


def _road(session: Session, qualified: str) -> Alignment:
    found = find_reference_alignment(session.doc, qualified)
    if found is None:
        raise RuntimeError(f"no alignment {qualified}")
    return found[0]


def _samples(align: Alignment, a: float, b: float, step: float = STEP_FT):
    """Raw stations from a to b every ``step`` plus the element ends, their
    points (ft) and directions (degrees, unwrapped)."""
    begin = float(align.begin_station)
    st = list(np.arange(a, b, step)) + [b]
    st += [begin + d for el in align.elements for d in (el.start_dist, el.end_dist)
           if a < begin + d < b]
    st = sorted(set(round(float(s), 6) for s in st))
    pts = np.array([align.point_at(min(max(s - begin, 0.0), align.length)) for s in st])
    dirs = np.unwrap(np.radians([align.direction_at(min(max(s - begin, 0.0), align.length))
                                 for s in st]))
    return st, pts, np.degrees(dirs)


def _fit(align: Alignment, a: float, b: float, W: float, H: float,
         level: Optional[float] = None) -> Optional[Tuple[float, float]]:
    """``(twist, slack in)`` fitting stations a..b in a W x H in viewport at
    1" = 50' with the line running left to right, or None. Any twist will do
    (corner to corner, if that is what fits) and the roomiest is returned;
    with ``level``, only twists that set the chord from a to b within that many
    degrees of level, the most nearly level first -- the way plan sheets are cut."""
    _st, pts, dirs = _samples(align, a, b)
    lo = -90.0 - float(dirs.min()) + 0.5
    hi = 90.0 - float(dirs.max()) - 0.5
    if lo > hi:
        return None
    th = np.radians(np.arange(lo, hi + 1e-9, THETA_STEP))
    x = pts[:, 0:1] * np.cos(th) - pts[:, 1:2] * np.sin(th)
    y = pts[:, 0:1] * np.sin(th) + pts[:, 1:2] * np.cos(th)
    w = (x.max(axis=0) - x.min(axis=0)) / FPI
    h = (y.max(axis=0) - y.min(axis=0)) / FPI
    slack = np.minimum(W - w, H - h)
    if level is None:
        k = int(np.argmax(slack))
        return (float(np.degrees(th[k])), float(slack[k])) if slack[k] >= 0.0 else None
    chord = math.degrees(math.atan2(pts[-1, 1] - pts[0, 1], pts[-1, 0] - pts[0, 0]))
    tilt = np.abs((chord + np.degrees(th) + 180.0) % 360.0 - 180.0)
    ok = np.nonzero((slack >= 0.0) & (tilt <= level))[0]
    if not len(ok):
        return None
    k = int(ok[np.argmin(tilt[ok])])
    return float(np.degrees(th[k])), float(slack[k])


def _greedy(align: Alignment, a: float, b: float, W: float, H: float,
            round_to: float = 0.0, level: Optional[float] = None) -> List[float]:
    """The sheet ends of the fewest sheets for a..b: each sheet takes the longest
    stretch that fits (greedy is optimal: a stretch that fits, every part of it
    fits), optionally ending on a round station."""
    ends, start = [], a
    while True:
        if _fit(align, start, b, W, H, level) is not None:
            ends.append(b)
            return ends
        lo, hi = start, b
        while hi - lo > 0.5:
            mid = (lo + hi) / 2.0
            if _fit(align, start, mid, W, H, level) is not None:
                lo = mid
            else:
                hi = mid
        end = math.floor(lo / round_to) * round_to if round_to else lo
        if end <= start + 1.0:
            raise RuntimeError("a sheet cannot hold any of the stretch")
        ends.append(end)
        start = end


@lru_cache(maxsize=None)
def _fewest(pid: str) -> int:
    cfg = P5[pid]
    align = _base_alignment(pid)
    ua = _usable(cfg["size"], cfg["template"])
    st = align.stations()
    return len(_greedy(align, st.parse(cfg["a"]), st.parse(cfg["b"]), ua[2] - ua[0],
                       ua[3] - ua[1]))


@lru_cache(maxsize=None)
def _base_alignment(pid: str) -> Alignment:
    cfg = P5[pid]
    folder = real.real_sheet(cfg["sheet_id"]).folder
    for fname in cfg["files"]:
        doc = common.document(folder / fname)
        name = cfg["alignment"].split(":", 1)[1]
        if name in doc.design.alignments:
            return doc.design.alignments[name]
    raise RuntimeError(f"{pid}: no {cfg['alignment']}")


def _p5_builder(pid: str):
    cfg = P5[pid]

    def build(out: Path) -> Path:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        folder = real.real_sheet(cfg["sheet_id"]).folder
        for fname in cfg["files"]:
            shutil.copyfile(folder / fname, out / fname)
        doc = out / cfg["doc"]
        s = Session(project_name=f"{cfg['road']} plan sheets", out_dir=out)
        common.save(s, doc)
        s = common.load(doc)
        for fname, ref in cfg["files"].items():
            common.ok(s.execute("attach_reference", {"name": ref, "path": fname,
                                                     "space": "model"}))
        return common.save(s, doc)
    return build


def _shows(vp, usable, q) -> bool:
    x0, y0, x1, y1 = vp.paper_bbox()
    return (x0 <= q[0] <= x1 and y0 <= q[1] <= y1
            and usable[0] - 1e-6 <= q[0] <= usable[2] + 1e-6
            and usable[1] - 1e-6 <= q[1] <= usable[3] + 1e-6)


def _seen(sheet, pts) -> List[Optional[object]]:
    """For each model point, the 1" = 50' viewport of ``sheet`` that shows it."""
    usable = sheet.usable_area()
    out = []
    for p in pts:
        hit = None
        for vp in sheet.viewports:
            if abs(float(vp.feet_per_inch) - FPI) < 1e-6 and _shows(vp, usable,
                                                                    vp.transform().to_paper(p)):
                hit = vp
                break
        out.append(hit)
    return out


def _lettered(plot) -> List[Tuple[float, object]]:
    """``(display station, text)`` of every MATCH LINE lettering on a sheet."""
    out = []
    for t in plot.free_texts():
        m = MATCH.search(t.content)
        if m:
            out.append((int(m.group(1)) * 100.0 + float(m.group(2)), t))
    return out


def _match_problem(plot, align: Alignment, vp, station: float, text) -> Optional[str]:
    """Whether the match line at ``station`` crosses the line square to it on
    this sheet, far enough each side, and is lettered along itself."""
    begin = float(align.begin_station)
    dist = min(max(station - begin, 0.0), align.length)
    t = vp.transform()
    q = t.to_paper(align.point_at(dist))
    d = align.direction_at(dist) + float(vp.rotation_deg)
    label = align.stations().format(station)
    near = [s for s in plot.segs if not s.closed and s.distance(q) <= AIM_FT / FPI]
    good = []
    for s in near:
        if pl.turn_between(s.angle, d + 90.0, 180.0) > SQUARE_DEG:
            continue
        lefts = [pl.offset_from(p, q, d)[1] * FPI for p in (s.a, s.b)]
        if min(lefts) <= -REACH_FT and max(lefts) >= REACH_FT:
            good.append(s)
    if not good:
        if not near:
            return f"no match line crosses the line at {label}"
        s = max(near, key=lambda s: s.length)
        if pl.turn_between(s.angle, d + 90.0, 180.0) > SQUARE_DEG:
            return (f"the match line at {label} runs at {s.angle % 180.0:.2f}° on the sheet; "
                    f"square to the line there is {(d + 90.0) % 180.0:.2f}°")
        lefts = [pl.offset_from(p, q, d)[1] * FPI for p in (s.a, s.b)]
        return (f"the match line at {label} reaches {min(lefts):.0f} ft to {max(lefts):.0f} ft "
                f"from the centerline; it should run at least {REACH_FT:g} ft past it each side")
    line = good[0]
    if line.distance(text.center()) > TEXT_NEAR_IN:
        return f"{_q(text.content)} is not lettered at its match line"
    if pl.turn_between(text.rotation, line.angle, 180.0) > TURN_DEG:
        return f"{_q(text.content)} is not lettered along its match line"
    if reads_upside_down(text.rotation):
        return f"{_q(text.content)} reads upside down"
    return None


def _p5_check(pid: str):
    cfg = P5[pid]

    def check(baseline: Session, submitted: Session) -> Result:
        tally = Tally()
        align = _road(baseline, cfg["alignment"])
        st = align.stations()
        A, B = st.parse(cfg["a"]), st.parse(cfg["b"])
        stations, pts, _dirs = _samples(align, A, B)
        # the plan sheets: every sheet a viewport of which shows part of the stretch
        plans = []
        for sheet in submitted.doc.sheets.values():
            shown = [k for k, p in enumerate(pts)
                     if any(_shows(vp, sheet.usable_area(), vp.transform().to_paper(p))
                            for vp in sheet.viewports)]
            if shown:
                plans.append((stations[shown[0]], sheet))
        plans.sort(key=lambda x: x[0])
        sheets = [s for _st, s in plans]
        if not sheets:
            tally.add("plan sheets", f"no sheet shows {cfg['line']} between {cfg['a']} and "
                                     f"{cfg['b']}")
            return tally.result("")
        # border, scale, viewports inside the border
        for sheet in sheets:
            template = getattr(sheet, "title_block_template", None)
            problem = None
            if template != cfg["template"] or sheet.size != cfg["size"]:
                problem = (f"sheet {sheet.name} is {sheet.size} with the {template} border, not "
                           f"{cfg['size']} with the {cfg['template']} border")
            for vp in sheet.viewports:
                if abs(float(vp.feet_per_inch) - FPI) > 1e-6 and any(
                        _shows(vp, sheet.usable_area(), vp.transform().to_paper(p)) for p in pts):
                    problem = problem or (f"a viewport on {sheet.name} shows the stretch at 1\" = "
                                          f"{float(vp.feet_per_inch):g}'")
            tally.add(f"{sheet.name}: border and 1\" = 50'", problem)
            ua = sheet.usable_area()
            outside = [vp for vp in sheet.viewports if not (
                vp.paper_bbox()[0] >= ua[0] - 0.01 and vp.paper_bbox()[1] >= ua[1] - 0.01
                and vp.paper_bbox()[2] <= ua[2] + 0.01 and vp.paper_bbox()[3] <= ua[3] + 0.01)]
            tally.add(f"{sheet.name}: viewports inside the border's usable area",
                      f"a viewport on {sheet.name} runs outside the usable area of its border"
                      if outside else None)
        # every station shows somewhere at 1" = 50'
        seen = [any(v is not None for v in vs) for vs in zip(*[_seen(s, pts) for s in sheets])]
        missing = [stations[k] for k, ok in enumerate(seen) if not ok]
        tally.add(f"every station {cfg['a']} to {cfg['b']} shown",
                  f"{len(missing)} stations show on no sheet at 1\" = 50', first "
                  f"{st.format(missing[0])}" if missing else None)
        # how many sheets
        fewest = _fewest(pid)
        tally.add("number of sheets", f"{len(sheets)} sheets; the stretch needs {fewest} at "
                                      f"1\" = 50' on this border, so at most {fewest + 1}"
                  if len(sheets) > fewest + 1 else None)
        # the breaks, from the lettered match lines
        plots, letters = {}, {}
        for sheet in sheets:
            plots[sheet.id] = pl.plot(submitted, sheet, pl.sheet_items(baseline, submitted,
                                                                       sheet.name))
            letters[sheet.id] = [(s, t) for s, t in _lettered(plots[sheet.id])
                                 if abs(s - A) > ENDS_FT and abs(s - B) > ENDS_FT]
        found = sorted(s for lst in letters.values() for s, _t in lst)
        breaks: List[float] = []
        for s in found:
            if not breaks or abs(s - breaks[-1]) > 0.5:
                breaks.append(s)
        problem = None
        if len(breaks) != len(sheets) - 1:
            problem = (f"{len(sheets)} sheets but {len(breaks)} lettered match line station(s) "
                       f"({', '.join(st.format(b) for b in breaks) or 'none'}); every break "
                       f"between two sheets wants one")
        tally.add("one lettered match line per break", problem)
        if problem is None:
            for k, sheet in enumerate(sheets):
                want = [b for b in breaks[max(0, k - 1):k + 1]]
                have = [s for s, _t in letters[sheet.id]]
                ok = all(any(abs(s - b) <= 0.5 for s in have) for b in want) and all(
                    any(abs(s - b) <= 0.5 for b in want) for s in have)
                tally.add(f"{sheet.name}: lettered at its own breaks", None if ok else (
                    f"sheet {sheet.name} letters match lines at "
                    f"{', '.join(st.format(s) for s in have) or 'nothing'}; in order along the "
                    f"line its breaks are {', '.join(st.format(b) for b in want)}"))
            for j, b in enumerate(breaks):
                pair = sheets[j:j + 2]
                values = [s for sh in pair for s, _t in letters[sh.id] if abs(s - b) <= 0.5]
                tally.add(f"match line {st.format(b)}: the same station on both sheets",
                          None if values and max(values) - min(values) <= 0.011 else
                          f"the two sheets letter the break at "
                          f"{', '.join(st.format(v) for v in values)}")
                for sh in pair:
                    text = next((t for s, t in letters[sh.id] if abs(s - b) <= 0.5), None)
                    vp = next((v for v in _seen(sh, [align.point_at(
                        min(max(b - float(align.begin_station), 0.0), align.length))]) if v), None)
                    if text is None or vp is None:
                        problem = f"sheet {sh.name} does not show the break at {st.format(b)}"
                    else:
                        problem = _match_problem(plots[sh.id], align, vp, b, text)
                    tally.add(f"match line {st.format(b)} on {sh.name}: square to "
                              f"{cfg['line']} at its station, lettered along it",
                              f"{sh.name}: {problem}" if problem else None)
            # each sheet: its own stretch, all of it shown, left to right
            bounds = [A] + breaks + [B]
            for k, sheet in enumerate(sheets):
                lo, hi = bounds[k], bounds[k + 1]
                idx = [i for i, s in enumerate(stations) if lo - 1e-6 <= s <= hi + 1e-6]
                views = _seen(sheet, [pts[i] for i in idx])
                gap = [stations[i] for i, v in zip(idx, views) if v is None]
                tally.add(f"{sheet.name}: shows all of {st.format(lo)} to {st.format(hi)}",
                          f"sheet {sheet.name} does not show {st.format(gap[0])} of its stretch "
                          f"{st.format(lo)} to {st.format(hi)}" if gap else None)
                wrong = []
                for i, v in zip(idx, views):
                    if v is None:
                        continue
                    dist = min(max(stations[i] - float(align.begin_station), 0.0), align.length)
                    if math.cos(math.radians(align.direction_at(dist) + float(v.rotation_deg))) <= 0.0:
                        wrong.append(stations[i])
                tally.add(f"{sheet.name}: stationing reads left to right",
                          f"on {sheet.name} {cfg['line']} runs right to left (or straight up "
                          f"or down) at {st.format(wrong[0])}"
                          + (f" to {st.format(wrong[-1])}" if len(wrong) > 1 else "")
                          if wrong else None)
        return tally.result(f"{len(sheets)} sheets at 1\" = 50' on the {cfg['template']} border "
                            f"(the stretch needs {fewest}), every station shown, stationing left "
                            f"to right on each, match lines square and lettered alike at "
                            f"{', '.join(st.format(b) for b in breaks) or 'no break'}")
    return check


def _p5_solve(pid: str):
    cfg = P5[pid]

    def solve(session: Session) -> None:
        qualified = cfg["alignment"]
        align = _road(session, qualified)
        st = align.stations()
        A, B = st.parse(cfg["a"]), st.parse(cfg["b"])
        ua = _usable(cfg["size"], cfg["template"])
        W, H = ua[2] - ua[0] - 0.1, ua[3] - ua[1] - 0.1
        fewest = _fewest(pid)
        for margin, level in ((1.0, 3.0), (0.6, 10.0), (0.3, None), (0.0, None)):
            ends = _greedy(align, A, B, W - margin, H - margin, round_to=10.0, level=level)
            if len(ends) <= fewest + 1:
                break
        # as many sheets as that, cut evenly where even cuts still fit
        n = len(ends)
        even = [round((A + (B - A) * (k + 1) / n) / 10.0) * 10.0 for k in range(n - 1)] + [B]
        if all(_fit(align, a, b, W - margin, H - margin, level) is not None
               for a, b in zip([A] + even[:-1], even)):
            ends = even
        common.ok(session.execute("create_layer", {"name": "MATCH-LINE", "color": "black",
                                                   "lineweight_mm": 0.35}))
        starts = [A] + ends[:-1]
        names = [f"PL-{k + 1}" for k in range(len(ends))]
        for name, a, b in zip(names, starts, ends):
            twist, _slack = _fit(align, a, b, W - margin, H - margin, level)
            _s, pts, _d = _samples(align, a, b)
            turned = [geo.rotate_point(list(p), twist) for p in pts]
            bb = geo.bbox_of_points(turned)
            centre = geo.rotate_point([(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0], -twist)
            common.ok(session.execute("create_sheet", {"name": name, "size": cfg["size"],
                                                       "title_block_template": cfg["template"]}))
            common.ok(session.execute("create_viewport", {
                "sheet": name, "center_paper": [(ua[0] + ua[2]) / 2.0, (ua[1] + ua[3]) / 2.0],
                "width_in": round(W, 3), "height_in": round(H, 3),
                "model_center": [round(centre[0], 2), round(centre[1], 2)],
                "feet_per_inch": FPI, "rotation_deg": round(twist, 3)}))
        for k, b in enumerate(ends[:-1]):
            label = f"MATCH LINE STA {st.format(b)}"
            for name in names[k:k + 2]:
                ends_paper = []
                for off in (-60.0, 60.0):
                    r = common.ok(session.query("station_to_xy", {
                        "alignment": qualified, "station": st.format(b), "offset": off,
                        "sheet": name}))
                    ends_paper.append(r["on_sheet"]["sheet_point"])
                p, q = ends_paper
                common.ok(session.execute("draw_line", {"space": name, "layer": "MATCH-LINE",
                                                        "start": p, "end": q}))
                angle = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
                rot = geo.reading_up(angle)
                mid = [p[0] + (q[0] - p[0]) * 0.8, p[1] + (q[1] - p[1]) * 0.8]
                common.ok(session.execute("place_text", {
                    "space": name, "layer": "MATCH-LINE", "position": mid, "content": label,
                    "height": 0.1, "rotation_deg": round(rot, 3), "halign": "center",
                    "valign": "bottom"}))
    return solve


def _p5_prompt(pid: str) -> str:
    cfg = P5[pid]
    refs = ", ".join(f"{f} (attached as {r})" for f, r in cfg["files"].items())
    return (f"This sheet file references the base files of {cfg['road']}: {refs}. The "
            f"centerline is alignment {cfg['line']}, reached as {cfg['alignment']}. Lay out the "
            f"plan sheets for {cfg['line']} from STA {cfg['a']} to STA {cfg['b']} at 1\" = 50' on "
            f"{cfg['border']}. You decide how many sheets, where to break between them and how "
            f"to turn each viewport: on every sheet {cfg['line']}'s stationing must read left to "
            f"right, each sheet's viewport must stay inside its border, and every station from "
            f"{cfg['a']} to {cfg['b']} must show on a sheet. Use no more sheets than the stretch "
            f"needs. At each break between two of your sheets, draw a match line on both "
            f"sheets, square to {cfg['line']} at the break station and running at least 40 ft "
            f"past the centerline on each side, and letter it along the line MATCH LINE STA "
            f"followed by the break station to the hundredth (MATCH LINE STA 12+34.56), the same "
            f"on both sheets. {cfg['a']} and {cfg['b']} are the limits of this work: no match "
            f"lines there.")


# ================================================================ the probes

PROBES: List[Probe] = []

_P4_NOTES = {
    "p04-crowded-ppm045": "L-1 (twist -89.94°) with D13 (one tangent), TB2 (curve, tangent) and "
                          "TB1 (tangent, curve, tangent) stripped: 37 labels and 2 tables. Naive "
                          "answer checked: the labelers' default poses (view_rotation right, tables "
                          "placed clear) put TB2's and TB1's bearings on the sheet's TWELVE BRIDGES "
                          "DRIVE and NB ENTRANCE RAMP callouts and fails D1-08; with both tables at "
                          "one spot it fails 11 ways.",
    "p04-crowded-ppm050": "L-7, the Ferrari Ranch Road interchange (twist -131.21°), with D13, "
                          "F3, F6, FR and F2 stripped: 67 labels and 4 tables around the loop "
                          "ramp. Naive answer checked: the labelers' default poses with the tables "
                          "placed clear leave 7 overlaps (labels on the 180 surviving callouts, on "
                          "the base's lettering and on each other); with the four tables at one "
                          "spot, 25. Lettering without view_rotation reads upside down.",
}
_P17_NOTES = {
    "p17-twist-ppm160": "PD-1 (Route 78, Example A-1) turned from 28.00° to -152.00°: NWR "
                        "(836+23.85 to 848+61.15; S 63°26'35\" E, R 2979.64', S 65°09'31\" E, "
                        "R 1999.03', S 79°39'17\" E) now runs right to left. Naive answers "
                        "checked: lettered without view_rotation, or with the published 28°, "
                        "the station numbers plot at -178.6° and every label reads upside down "
                        "(fails the orientation item and D1-08).",
    "p17-twist-fdot916": "FDOT drainage plan sheet 1 re-cut at -113.00°, viewport fitted to the "
                         "usable area and centred on CL1: its tangent (N 59°59'28\" W) climbs at "
                         "37.0° on the paper and the R 875.31' curve bends it to 26.6°. Naive "
                         "answer checked: lettered without view_rotation the labels plot at "
                         "-143° and read upside down. (The published twist, -148.34°, happens to "
                         "letter right here.)",
}
_P5_NOTES = {
    "p05-breaks-fdot904": "SR 50 CL1 472+00 to 490+00, 1800 ft: the end of a R 2862.46' curve "
                          "(S 70°24' W to S 49°24' W), a 1069 ft tangent, the start of a R "
                          "2864.60' curve back toward S 81°34' W. Stationing runs south-west, so "
                          "north-up viewports read right to left. FDOT usable area 15.4 x 9.6 in "
                          "(770 x 480 ft): the fewest sheets is 2 (each run corner to corner), so "
                          "3 pass. Naive answers checked: north-up sheets (right to left), match "
                          "lines drawn vertical on the paper (1.2° off square), four sheets.",
    "p05-breaks-cfl": "CFL main road CL1 10+00 to 25+00, 1500 ft: tangent at N 13°34' E, a R "
                      "675.78' curve to N 36°15' E, a R 498.48' reverse curve back to N 16°08' "
                      "E. Federal Lands usable area 15.6 x 10.4 in (780 x 520 ft): the fewest "
                      "sheets is 2, so 3 pass. North-up sheets read left to right here but need "
                      "3 cut close; naive answers checked: four sheets, match lines vertical on "
                      "the paper (8° off square).",
}

for _pid in P4:
    PROBES.append(Probe(
        id=_pid, prompt=_p4_prompt(_pid), check=_p4_check(_pid), solve=_p4_solve(_pid),
        note=_P4_NOTES[_pid], tags=["layout", "crowded", "caltrans", "twist", "verifier"],
        start=common.register(_pid, common.sheet_file(P4[_pid]["sheet_id"]),
                              _p4_builder(_pid))))
for _pid in P17:
    PROBES.append(Probe(
        id=_pid, prompt=_p17_prompt(_pid), check=_p17_check(_pid), solve=_p17_solve(_pid),
        note=_P17_NOTES[_pid], tags=["layout", "twist", "verifier"],
        start=common.register(_pid, common.sheet_file(P17[_pid]["sheet_id"]),
                              _p17_builder(_pid))))
for _pid in P5:
    PROBES.append(Probe(
        id=_pid, prompt=_p5_prompt(_pid), check=_p5_check(_pid), solve=_p5_solve(_pid),
        note=_P5_NOTES[_pid], tags=["layout", "sheet-breaks", "match-line", P5[_pid]["agency"]],
        start=common.register(_pid, P5[_pid]["doc"], _p5_builder(_pid))))


__all__ = ["PROBES", "P4", "P17", "P5"]
