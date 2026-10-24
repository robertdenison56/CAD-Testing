"""Repairs to the redrafted sheets a pilot starts from.

The redraft pipelines left a few things on the example sheets that a reviewer
flags and the pilots' checks do not plant: GPT-6-Astra found them on
2026-10-23, marking them as errors on the clean QA-review control and the
planted sheets (docs/Probes_Pilots.md). Each repair here is applied by
``common.stage`` to every pilot that starts on the sheet, so the start is the
sheet as a drafter would have left it, and the redraft itself stays as it is
(the real-task catalogue ships the unrepaired files).

- Every sheet: stroke lettering that doubles real text.  A PDF's outlined
  font came through both as text and as its outlines (``S-TEXT-*`` lines
  and polylines under the words), so PD-1's notes and title printed twice.
  The strokes under a text go; stroke lettering with no text copy (PD-1's
  legend) stays.
- L-1 (PPM-045): "Orchard Creek" digitised in seven pieces, one 0.5 in tall,
  becomes one text; the two labels digitised as strokes (TB1's bearing
  ``N 01°05'14" W`` and ``328.15'``, stale against the design) go -- the QA
  review re-letters them from the design, the other pilots strip TB1.
- PD-1 (PPM-160): the title's second line at 0.5 in over the first, the notes'
  second lines at 0.175 in over their first: set a line apart at one height.
- D.10 (WFL p19): two "See Section X for details" placeholders name a sheet;
  a leader's landing drawn twice; the 153+00 station number that sits under
  the plan/profile divider (the viewport reaches over the profile).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.document.entities import Line, Polyline, Text
from roaddraft.probes.pilot import common as c

Box = Tuple[float, float, float, float]

#: a stroke under a text's box, grown by this (paper inches), doubles it
DOUBLED_MARGIN_IN = 0.3
STROKE_LAYER_PREFIX = "S-TEXT-"

# ------------------------------------------------------------------ L-1

PPM045 = "PPM-045"
#: the pieces of "Orchard Creek" on the sheet (the C was in AA01: qa_review)
PPM_CREEK = {"TX-089": "O", "TX-090": "rcha", "TX-091": "r", "TX-092": "d", "TX-094": "r",
             "TX-093": "8’"}
PPM_CREEK_PIECES = ("TX-089", "TX-090", "TX-091", "TX-092", "TX-094")
#: paper boxes of the two labels the redraft digitised as strokes:
#: N 01°05'14" W along "TB1" ahead of its curve, and 328.15' further on
PPM_STROKES = {"bearing": (16.25, 8.12, 18.10, 8.45), "length": (21.15, 8.20, 22.20, 8.48),
               "quotes": (14.30, 8.22, 15.15, 8.40)}   # a second pair of quotes on "TB1" LINE
#: the layers the digitiser put those strokes on, per file (the ticks on V-ANNO-STAT stay)
PPM_STROKE_LAYERS = {"0000000000aa01.rdraft": ("V-ROAD", "V-ROAD-HTCH", "V-ANNO-TRACE"),
                     "0000000000bb01.rdraft": ("E-TOPO-SYMB", "E-TOPO-TRACE")}
PPM_STROKES_EXPECTED = 24
#: TB2's 641 station number, drawn a second time as strokes on E-TOPO-SYMB under the real one
PPM_STROKES_TOPO = {"0000000000bb01.rdraft": ("E-TOPO-SYMB",)}
PPM_STROKES_TOPO_BOX = (8.6, 11.0, 9.4, 11.7)
#: the bubble rings (S-ANNO-TAG polylines) whose numbers the redraft lost
PPM_BUBBLES = {"PL-004": "1", "PL-005": "2"}

# ------------------------------------------------------------------ PD-1

PPM160 = "PPM-160"
#: the title's two lines and the notes' second lines, digitised at odd heights
#: over the line above: id -> (text, position, height)
PPM160_TEXTS = {
    "TX-003": ("PAVEMENT DELINEATION", [26.67, 1.86], 0.29),
    "TX-002": ("AND SIGN PLAN", [26.67, 1.44], 0.29),
    "TX-041": ("FOR ACCURATE RIGHT OF WAY DATA, CONTACT RIGHT OF WAY ENGINEERING", [2.68, 20.39], 0.14),
    "TX-039": ("AT THE DISTRICT OFFICE.", [2.68, 20.14], 0.14),
    "TX-038": ("FEDERAL SIGN DESIGNATIONS ARE SHOWN UNLESS DESIGNATED BY (CA) WHICH", [2.68, 19.82], 0.14),
    "TX-036": ("INDICATES A CALIFORNIA SIGN DESIGNATION.", [2.68, 19.57], 0.14),
    "TX-037": ("2.", [2.39, 19.82], 0.14),
}
#: the notes' stroke copies that landed on a line layer: nothing but text sits here
PPM160_NOTES_BOX = (1.5, 19.3, 11.5, 20.6)

# ------------------------------------------------------------------ D.10

WFL19 = "WFL-Plan-Profile-Sheets-p19"
WFL19_PLACEHOLDER = "See Section X for details"
WFL19_DETAIL = "See Sheet C.3 for details"
WFL19_DOUBLED_LANDING = ("LN-005", "LN-026")
WFL19_ALI = "SamplePlan_ali.rdraft"
#: the plan/profile divider on the paper; alignment lettering under it is off the plan
WFL19_DIVIDER_Y_IN = 6.6


def _points(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [list(e.start), list(e.end)]
    if isinstance(e, Polyline):
        return [list(p) for p in e.vertices]
    return []


def _within(points: Sequence[Sequence[float]], box: Box) -> bool:
    return bool(points) and all(box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]
                                for p in points)


def _text_box(session: Session, text: Text, margin: float) -> Box:
    from roaddraft.tasks.real import _quad
    bb = geo.bbox_of_points(_quad(text, session.doc))
    return (bb[0] - margin, bb[1] - margin, bb[2] + margin, bb[3] + margin)


def strip_doubled_strokes(session: Session, margin: float = DOUBLED_MARGIN_IN) -> List[str]:
    """Delete the ``S-TEXT-*`` strokes on every sheet that lie under a text."""
    gone: List[str] = []
    for sheet in session.doc.sheets.values():
        boxes = [_text_box(session, e, margin) for e in sheet.entities.values()
                 if isinstance(e, Text)]
        ids = []
        for e in sheet.entities.values():
            if not e.layer.startswith(STROKE_LAYER_PREFIX) or isinstance(e, Text):
                continue
            pts = _points(e)
            if not pts:
                continue
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            if any(b[0] <= mx <= b[2] and b[1] <= my <= b[3] for b in boxes):
                ids.append(e.id)
        if ids:
            c.ok(session.execute("delete_entities", {"ids": ids}))
            gone += ids
    return gone


def _expect(entity, content: str, what: str) -> None:
    if entity is None or entity.content != content:
        raise RuntimeError(f"{what}: expected {content!r}, found "
                           f"{None if entity is None else entity.content!r}")


def strip_boxed_strokes(out: Path, sheet_file: str, layers: Dict[str, Sequence[str]],
                        boxes: Sequence[Box], expected: int = 0) -> int:
    """Delete the lines and polylines on ``layers`` (per base file) whose every
    point shows inside one of ``boxes`` on the sheet's paper."""
    s = c.load(out / sheet_file)
    sheet = next(iter(s.doc.sheets.values()))
    to_paper = sheet.viewports[0].transform().to_paper
    found = 0
    for name, layer_names in layers.items():
        base = c.load(out / name)
        ids = [e.id for e in base.doc.model_entities.values()
               if e.layer in layer_names and isinstance(e, (Line, Polyline))
               and any(_within([to_paper(p) for p in _points(e)], box) for box in boxes)]
        if ids:
            c.ok(base.execute("delete_entities", {"ids": ids}))
            c.save(base, out / name)
        found += len(ids)
    if found < expected:
        raise RuntimeError(f"{sheet_file}: only {found} of {expected} strokes found")
    return found


def repair_ppm045(out: Path) -> None:
    strip_boxed_strokes(out, c.sheet_file(PPM045), PPM_STROKE_LAYERS, list(PPM_STROKES.values()),
                        PPM_STROKES_EXPECTED)
    strip_boxed_strokes(out, c.sheet_file(PPM045), PPM_STROKES_TOPO, [PPM_STROKES_TOPO_BOX], 3)
    s = c.load(out / c.sheet_file(PPM045))
    sheet = next(iter(s.doc.sheets.values()))
    for eid, text in PPM_CREEK.items():
        _expect(sheet.entities.get(eid), text, f"L-1 {eid}")
    o = sheet.entities["TX-089"]
    c.ok(s.execute("delete_entities", {"ids": list(PPM_CREEK_PIECES)}))
    c.ok(s.execute("place_text", {"space": sheet.name, "layer": o.layer, "position": list(o.position),
                                  "rotation_deg": float(o.rotation_deg), "height": 0.14,
                                  "content": "Orchard Creek"}))
    # an 8' width lettered over the 12' above it
    c.ok(s.execute("move_entities", {"ids": ["TX-098"], "delta": [0.0, -0.04]}))
    c.save(s, out / c.sheet_file(PPM045))


def repair_ppm160(out: Path) -> None:
    s = c.load(out / c.sheet_file(PPM160))
    sheet = next(iter(s.doc.sheets.values()))
    for eid, (text, position, height) in PPM160_TEXTS.items():
        _expect(sheet.entities.get(eid), text, f"PD-1 {eid}")
        c.ok(s.execute("modify_entity", {"id": eid, "changes": {"height": height,
                                                                "position": position}}))
    strokes = [e.id for e in sheet.entities.values()
               if not isinstance(e, Text) and _within(_points(e), PPM160_NOTES_BOX)]
    if strokes:
        c.ok(s.execute("delete_entities", {"ids": strokes}))
    c.save(s, out / c.sheet_file(PPM160))


def repair_wfl19(out: Path) -> None:
    s = c.load(out / c.sheet_file(WFL19))
    sheet = next(iter(s.doc.sheets.values()))
    holders = [e.id for e in sheet.entities.values()
               if isinstance(e, Text) and e.content == WFL19_PLACEHOLDER]
    if len(holders) != 2:
        raise RuntimeError(f"D.10: expected two {WFL19_PLACEHOLDER!r}, found {holders}")
    for eid in holders:
        c.ok(s.execute("modify_entity", {"id": eid, "changes": {"content": WFL19_DETAIL}}))
    a, b = (sheet.entities[i] for i in WFL19_DOUBLED_LANDING)
    if sorted(map(tuple, _points(a))) != sorted(map(tuple, _points(b))):
        raise RuntimeError("D.10: LN-005 and LN-026 no longer coincide")
    c.ok(s.execute("delete_entities", {"ids": [WFL19_DOUBLED_LANDING[1]]}))
    to_paper = sheet.viewports[0].transform().to_paper
    c.save(s, out / c.sheet_file(WFL19))
    ali = c.load(out / WFL19_ALI)
    under = [e.id for e in ali.doc.model_entities.values()
             if e.anchor and e.anchor.get("kind") in ("station", "tick")
             and all(to_paper(p)[1] < WFL19_DIVIDER_Y_IN and to_paper(p)[0] < 16.3
                     for p in (_points(e) or [list(e.position)]))]
    if under:
        c.ok(ali.execute("delete_entities", {"ids": under}))
        c.save(ali, out / WFL19_ALI)


SHEET_REPAIRS: Dict[str, Callable[[Path], None]] = {
    PPM045: repair_ppm045, PPM160: repair_ppm160, WFL19: repair_wfl19,
}


def apply(out: Path, sheet_id: str) -> None:
    """Repair the staged copy of ``sheet_id`` under ``out``."""
    out = Path(out)
    s = c.load(out / c.sheet_file(sheet_id))
    if strip_doubled_strokes(s):
        c.save(s, out / c.sheet_file(sheet_id))
    fix = SHEET_REPAIRS.get(sheet_id)
    if fix:
        fix(out)
