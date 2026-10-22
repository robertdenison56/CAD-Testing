"""Pilot 2: sources that disagree, and the evidence that settles which is wrong.

A plan sheet and its base files say the same thing several times over: the
alignment design in the alignment file, the centerline drawn from it, the
pavement edges in the corridor file, the station ticks and numbers, the curve
points lettered on the sheet and the curve data. When one of them is wrong a
drafter does not just make them agree -- making the wrong one agree is how a
bad radius ends up in the corridor and the cross sections. The job is to find
the disagreement, weigh the other sources (three agree, one does not), fix
the one that is wrong in the file where it lives, and leave the rest alone.
Nothing in the prompt says which source, or what kind of value. The engine
does not help: it has no notion of a "true" source, and the obvious move --
re-letter the sheet from get_design_data -- is the wrong fix when the design is
the thing that was broken.

The sheets are pilot 14's normalised ones (``qa_review.prepare_wfl19`` and
``prepare_ppm045``): every source on them agrees to the hundredth before one
disagreement is planted.

* ``p02-sources-wfl19a`` -- WFL D.10, the curve data says R = 683.00'. The
  design (R 643.00), the drawn centerline, the edges 15.00 ft either side of
  a 643-ft curve, the stationing and the curve data's own Δ, T and L (81°35'22",
  554.92', 915.64', which only R 643 satisfies) all say 643. Fix: the sheet's
  R back to 643.00'.
* ``p02-sources-wfl19b`` -- WFL D.10, MAIN 01's radius changed to 680 ft in the
  alignment file (PIs unchanged) and its centerline redrawn from it. The curve
  data (R, T, L), the PT 152+96.54, the station ticks and numbers and the
  pavement edges all still describe the 643-ft curve; the drawn centerline
  runs off the middle of the road, out along the inside edge (PI 149+35.83 and Δ
  still agree; R, T, L and the PT do not). Fix: open the alignment file,
  restore R 643 at the PI, redraw the centerline, save it.
* ``p02-sources-ppm045`` -- Caltrans L-1, "TB2"'s tangent lettered 462.42' (two
  digits transposed). The design's T-1 is 426.42 ft, and its EC 639+92.73 and
  POT 644+19.15, lettered on the sheet, are 426.42 ft apart. Fix: the label.

**Grading** reads the documents: the wrong source corrected to the true value
(a lettered value to the hundredth; the restored design within 0.01 ft of
radius and 0.05 ft of position at every 25 ft station, and every centerline
element in the alignment file on it, covering the line); every right source
unchanged -- the sheet file and each base file compared entity by entity with
a fresh build of the start, the only allowance being the one wrong item (and,
for the design, the centerline drawn from it); and a finding recorded with
set_meta (presence only: the sheet file's meta, or a base file's).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Optional

from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, Line, Polyline, Text
from roaddraft.document.fileformat import read_document, journal_path
from roaddraft.probes import notation as nt
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common as c
from roaddraft.probes.pilot import qa_review as qa

#: the planted values
WFL_TABLE_R = 683.0
WFL_DESIGN_R = 680.0
PPM_TB2_LENGTH = "462.42’"
#: where a corrected label may sit, from the one it replaces (paper inches)
NEAR_IN = 0.5
#: how close a restored design must come to the true one
RADIUS_FT = 0.01
POSITION_FT = 0.05
STEP_FT = 25.0
#: how far a centerline element may lie off the restored design
DRAWN_FT = 0.1


# ----------------------------------------------------------------- the starts


def _build_wfl_table(out: Path) -> Path:
    path = qa.prepare_wfl19(out)
    s = c.load(path)
    c.ok(s.execute("modify_entity", {"id": "TX-042", "changes": {"content": f"R = {WFL_TABLE_R:.2f}'"}}))
    return c.save(s, path)


def _build_wfl_design(out: Path) -> Path:
    path = qa.prepare_wfl19(out)
    ali = c.load(Path(out) / qa.WFL_ALI)
    pis, begin = qa.wfl19_pis(radius=WFL_DESIGN_R)
    c.ok(ali.execute("modify_alignment", {"name": qa.WFL_ALIGN, "redraw": True,
                                          "changes": {"pis": pis, "begin_station": begin}}))
    c.save(ali, Path(out) / qa.WFL_ALI)
    return path


def _build_ppm_length(out: Path) -> Path:
    path = qa.prepare_ppm045(out)
    s = c.load(path)
    sheet = next(iter(s.doc.sheets.values()))
    if sheet.entities["TX-084"].content != "426.42’":
        raise RuntimeError(f"L-1: TB2's length reads {sheet.entities['TX-084'].content!r}, not 426.42’")
    c.ok(s.execute("modify_entity", {"id": "TX-084", "changes": {"content": PPM_TB2_LENGTH}}))
    return c.save(s, path)


START_TABLE = c.register("p02-wfl19a", qa.WFL_FILE, _build_wfl_table)
START_DESIGN = c.register("p02-wfl19b", qa.WFL_FILE, _build_wfl_design)
START_LENGTH = c.register("p02-ppm045", qa.PPM_FILE, _build_ppm_length)


# ----------------------------------------------------------------- reading


def _finding(submitted: Session) -> Optional[str]:
    """The finding the model recorded: the sheet file's meta, else a base file's."""
    meta = submitted.doc.meta or {}
    if str(meta.get("finding", "")).strip():
        return str(meta["finding"])
    home = Path(getattr(submitted.doc, "_path", "") or ".").parent
    for ref in submitted.doc.references.values():
        path = home / ref.path
        if path.exists():
            found = (read_document(path).get("meta") or {}).get("finding")
            if str(found or "").strip():
                return str(found)
    return None


def _texts(session: Session):
    """Every text the sheet file shows on its sheet: ``(id, content, paper PText)``."""
    sheet = next(iter(session.doc.sheets.values()))
    items = [(sheet.id, e) for e in sheet.entities.values() if isinstance(e, Text)]
    items += [("model", e) for e in session.doc.model_entities.values() if isinstance(e, Text)]
    view = pl.plot(session, sheet, items)
    return [(t.source, t.content, t) for t in view.texts]


def _corrected_label(truth: Session, submitted: Session, eid: str, value_of, want: float,
                     tol: float, what: str, tally: Tally) -> List[str]:
    """The planted label, or the one that replaced it near the same place: its
    value must be ``want``. Returns the ids the check lets change."""
    original = next(t for i, _c, t in _texts(truth) if i == eid)
    before = {i for i, _c, _t in _texts(truth)}
    cands = []
    for i, content, t in _texts(submitted):
        if i != eid and i in before:
            continue
        if math.dist(t.center(), original.center()) > NEAR_IN and i != eid:
            continue
        v = value_of(content)
        if v is not None:
            cands.append((i, content, v))
    if not cands:
        tally.add(what, f"{what} is gone, and nothing replaced it")
        return [eid]
    if len(cands) > 1:
        tally.add(what, f"{what} is lettered {len(cands)} times: "
                        + ", ".join(repr(x[1]) for x in cands))
        return [eid] + [x[0] for x in cands]
    i, content, v = cands[0]
    tally.add(what, None if abs(v - want) <= tol else
              f"{what} reads {content!r}; the other sources say {want:.2f}")
    return [eid, i]


def _r_value(content: str) -> Optional[float]:
    m = re.match(r"^\s*R\s*=\s*([\d,]+(?:\.\d+)?)", content)
    return float(m.group(1).replace(",", "")) if m else None


def _length_value(content: str) -> Optional[float]:
    if nt.bearings(content) or re.search(r"\d\+\d", content):
        return None
    vals = nt.feet(content)
    if len(vals) == 1:
        return vals[0]
    m = re.match(r"^\s*([\d,]+\.\d+)\s*(?:[’']|FT\.?|ft\.?)?\s*$", content)
    return float(m.group(1).replace(",", "")) if m else None


# ----------------------------------------------------------------- the checks


def _check_label(start: str, eid: str, value_of, want: float, what: str):
    def check(baseline: Session, submitted: Session) -> Result:
        expected = Path(qa._built(start))
        truth = c.load(expected)
        tally = Tally()
        allow = _corrected_label(truth, submitted, eid, value_of, want, 0.006, what, tally)
        tally.add("every other source unchanged",
                  qa.changed_outside(expected, submitted, allow_ids=allow))
        tally.add("the finding recorded", None if _finding(submitted) else
                  "no finding recorded (set_meta {\"updates\": {\"finding\": ...}})")
        return tally.result(f"{what} corrected to {want:.2f}, every other source unchanged, "
                            f"the finding recorded")
    return check


def _true_alignment() -> Session:
    """MAIN 01 as it should be, in a scratch session."""
    pis, begin = qa.wfl19_pis()
    s = Session()
    c.ok(s.execute("create_alignment", {"name": "TRUE", "begin_station": begin, "pis": pis}))
    return s


def _design_problem(ali: Session, true: Session) -> Optional[str]:
    if qa.WFL_ALIGN not in ali.doc.design.alignments:
        return f"the alignment file has no {qa.WFL_ALIGN} any more"
    curves = c.ok(ali.query("get_design_data", {"kind": "curves", "alignment": qa.WFL_ALIGN}))["rows"]
    if len(curves) != 1:
        return f"{qa.WFL_ALIGN} has {len(curves)} curves; it has one"
    R = float(curves[0]["radius"])
    if abs(R - qa.WFL_CURVE["radius"]) > RADIUS_FT:
        return (f"{qa.WFL_ALIGN}'s curve is still R {R:.2f} ft; the curve data, the PT, the "
                f"stationing and the edges all describe R {qa.WFL_CURVE['radius']:.2f}")
    a = true.doc.design.alignments["TRUE"]
    b = ali.doc.design.alignments[qa.WFL_ALIGN]
    lo = max(a.begin_station, b.begin_station)
    hi = min(a.end_station, b.end_station)
    station = math.ceil(lo / STEP_FT) * STEP_FT
    while station <= hi:
        p = c.ok(true.query("station_to_xy", {"alignment": "TRUE", "station": station}))["point"]
        q = c.ok(ali.query("station_to_xy", {"alignment": qa.WFL_ALIGN, "station": station}))["point"]
        if math.dist(p, q) > POSITION_FT:
            return (f"{qa.WFL_ALIGN} at {station / 100:.0f}+{station % 100:05.2f} is "
                    f"{math.dist(p, q):.2f} ft from where the restored design puts it")
        station += STEP_FT
    return None


def _drawn_problem(ali: Session, true: Session) -> Optional[str]:
    """The centerline in the alignment file lies on the true design and covers it
    where the sheet shows it."""
    drawn = [e for e in ali.doc.model_entities.values()
             if e.layer == "P_ALIGN" and isinstance(e, (Line, Arc, Polyline))]
    if not drawn:
        return "the centerline is no longer drawn in the alignment file"

    def samples(e, n=8):
        if isinstance(e, Line):
            return [[e.start[0] + (e.end[0] - e.start[0]) * k / n,
                     e.start[1] + (e.end[1] - e.start[1]) * k / n] for k in range(n + 1)]
        if isinstance(e, Arc):
            a0, a1 = e.start_angle_deg, e.end_angle_deg
            sweep = (a1 - a0) % 360.0
            return [[e.center[0] + e.radius * math.cos(math.radians(a0 + sweep * k / n)),
                     e.center[1] + e.radius * math.sin(math.radians(a0 + sweep * k / n))]
                    for k in range(n + 1)]
        return [list(v) for v in e.vertices]

    for e in drawn:
        for p in samples(e):
            r = c.ok(true.query("xy_to_station", {"alignment": "TRUE", "point": p}))
            if abs(r["offset"]) > DRAWN_FT:
                return (f"the centerline drawn in the alignment file ({e.id}) runs "
                        f"{abs(r['offset']):.1f} ft off the restored design")
    a = true.doc.design.alignments["TRUE"]
    pts = [p for e in drawn for p in samples(e, 40)]
    station = math.ceil(a.begin_station / STEP_FT) * STEP_FT
    while station <= a.end_station:
        q = c.ok(true.query("station_to_xy", {"alignment": "TRUE", "station": station}))["point"]
        if min(math.dist(q, p) for p in pts) > STEP_FT:
            return f"the centerline is not drawn near {station / 100:.0f}+{station % 100:05.2f}"
        station += STEP_FT
    return None


def _check_design(baseline: Session, submitted: Session) -> Result:
    expected = Path(qa._built(START_DESIGN))
    tally = Tally()
    home = Path(getattr(submitted.doc, "_path", "") or ".").parent
    ali_path = home / qa.WFL_ALI
    true = _true_alignment()
    if not ali_path.exists():
        tally.add("the design restored in the alignment file", "the alignment file is missing")
    else:
        ali = c.load(ali_path)
        tally.add("the design restored in the alignment file", _design_problem(ali, true))
        tally.add("the centerline redrawn from it", _drawn_problem(ali, true))
        # the rest of the alignment file: the station ticks and numbers, untouched
        want = read_document(expected.parent / qa.WFL_ALI).get("model_entities") or {}
        got = read_document(ali_path).get("model_entities") or {}
        want = want if isinstance(want, dict) else {e["id"]: e for e in want}
        got = got if isinstance(got, dict) else {e["id"]: e for e in got}
        moved = next((eid for eid, e in want.items() if e.get("layer") != "P_ALIGN"
                      and got.get(eid) != e), None)
        added = next((eid for eid, e in got.items() if eid not in want and e.get("layer") != "P_ALIGN"),
                     None)
        tally.add("the stationing in the alignment file unchanged",
                  f"the alignment file's {moved or added} was changed" if (moved or added) else None)
    tally.add("every other source unchanged",
              qa.changed_outside(expected, submitted, allow_files=[qa.WFL_ALI]))
    tally.add("the finding recorded", None if _finding(submitted) else
              "no finding recorded (set_meta {\"updates\": {\"finding\": ...}})")
    return tally.result("MAIN 01 restored to R 643.00 in the alignment file and its centerline "
                        "redrawn; the sheet, the corridor and the stationing untouched; the finding "
                        "recorded")


# ----------------------------------------------------------------- the solutions


def _solve_label(eid: str, content: str, finding: str):
    def solve(session: Session) -> None:
        c.ok(session.execute("modify_entity", {"id": eid, "changes": {"content": content}}))
        c.ok(session.execute("set_meta", {"updates": {"finding": finding}}))
    return solve


def _solve_design(session: Session) -> None:
    """What an agent does over MCP: open_document the alignment file, put the
    radius at the PI back, redraw, and come back to the sheet for the finding."""
    path = Path(session.doc._path).parent / qa.WFL_ALI
    ali = c.load(path)
    curve = c.ok(ali.query("get_design_data", {"kind": "curves", "alignment": qa.WFL_ALIGN}))["rows"][0]
    pis = [list(p["point"]) + ([p["radius"]] if p.get("radius") else [])
           for p in ali.doc.design.alignments[qa.WFL_ALIGN].to_dict()["pis"]]
    pis[1] = pis[1][:2] + [qa.WFL_CURVE["radius"]]
    c.ok(ali.execute("modify_alignment", {"name": qa.WFL_ALIGN, "redraw": True,
                                          "changes": {"pis": pis}}))
    c.save(ali, path)
    c.ok(ali.query("save_journal", {"path": str(journal_path(path))}))
    c.ok(session.execute("set_meta", {"updates": {"finding": (
        f"MAIN 01's curve in {qa.WFL_ALI} was R {curve['radius']:.2f}; the curve data, PT, "
        f"stationing and pavement edges all give R 643.00. Restored R 643.00 at the PI and "
        f"redrew the centerline.")}}))


# ----------------------------------------------------------------- the probes

WFL_PROMPT = ("Sheet D.10 and the base files it references are meant to tell one story about "
              "MAIN 01: the alignment design in the alignment file, the centerline drawn from it, "
              "the pavement edges in the corridor file, the station ticks and numbers, the PT "
              "station and the curve data on the sheet. They disagree in one place. Find it, work "
              "out from the rest of the evidence which one is wrong, and correct that one, in "
              "whichever file it lives, so it agrees with the others. Change nothing else. Then "
              "record what was wrong in the sheet file with set_meta {\"updates\": {\"finding\": "
              "\"...\"}}.")
PPM_PROMPT = ("Sheet L-1 and the base files it references are meant to tell one story about the "
              "\"D13\", \"TB2\" and \"TB1\" lines: the alignment designs in the design file, the "
              "centerlines drawn from them, the station ticks and numbers, the bearings and "
              "distances, the BC, EC and POT stations and the curve table. They disagree in one "
              "place. Find it, work out from the rest of the evidence which one is wrong, and "
              "correct that one, in whichever file it lives, so it agrees with the others. Change "
              "nothing else; the construction notes are not part of this. Then record what was "
              "wrong in the sheet file with set_meta {\"updates\": {\"finding\": \"...\"}}.")

PROBES: List[Probe] = [
    Probe(id="p02-sources-wfl19a", start=START_TABLE, tags=["pilot", "sources", "wfl", "edit"],
          prompt=WFL_PROMPT,
          check=_check_label(START_TABLE, "TX-042", _r_value, qa.WFL_CURVE["radius"],
                             "the curve data's R"),
          solve=_solve_label("TX-042", "R = 643.00'",
                             "Curve data R read 683.00'; the design, centerline, edges and the "
                             "table's own Δ, T and L give R 643.00'. Corrected the table."),
          note="Planted: the curve data's R lettered 683.00'; Δ 81°35'22\", T 554.92', L 915.64', the "
               "design, the centerline and the edges all say 643. Naive wrong: changing MAIN 01 to "
               "R 683 so the design matches the table (fails: the design changed, the table not)."),
    Probe(id="p02-sources-wfl19b", start=START_DESIGN, tags=["pilot", "sources", "wfl", "edit", "basefile"],
          prompt=WFL_PROMPT, check=_check_design, solve=_solve_design,
          note="Planted: MAIN 01's radius 680 ft in the alignment file (PIs kept) with its centerline "
               "redrawn: the curve data, PT 152+96.54, stationing and edges describe R 643. The fix is "
               "in the base file: modify_alignment back to 643 with redraw. Naive wrong: re-lettering "
               "the sheet from get_design_data (R 680.00', T 586.85', L 968.32', PT 153+17.30) -- the sheet "
               "changes, the design does not."),
    Probe(id="p02-sources-ppm045", start=START_LENGTH, tags=["pilot", "sources", "caltrans", "edit"],
          prompt=PPM_PROMPT,
          check=_check_label(START_LENGTH, "TX-084", _length_value, 426.42, "\"TB2\"'s tangent length"),
          solve=_solve_label("TX-084", "426.42’",
                             "\"TB2\" tangent length lettered 462.42'; the design's T-1 and the EC "
                             "639+92.73 to POT 644+19.15 stationing give 426.42'. Corrected the label."),
          note="Planted: \"TB2\"'s tangent lettered 462.42' (426.42 transposed). The design, the EC "
               "and POT stations (426.42 ft apart) and the drawn line agree. Naive wrong: moving the "
               "POT or the design to make T-1 462.42 ft."),
]

__all__ = ["PROBES"]
