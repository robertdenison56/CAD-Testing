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


def _check_label(start: str, eid: str, value_of, want: float, what: str, model: bool = False):
    """``model``: model space compared too (``qa.changed_outside``)."""
    def check(baseline: Session, submitted: Session) -> Result:
        expected = Path(qa._built(start))
        truth = c.load(expected)
        tally = Tally()
        allow = _corrected_label(truth, submitted, eid, value_of, want, 0.006, what, tally)
        tally.add("every other source unchanged",
                  qa.changed_outside(expected, submitted, allow_ids=allow, model=model))
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


# ======================================================= more instances (2026-11-03)
#
# * ``p02-sources-ppm048a`` -- Caltrans L-4 (pilot 14's prepared sheet): curve 36's T
#   in the CURVE DATA table lettered 215.05'. Its R 328.08' and Δ 74°50'50", its L
#   428.58', the design and the EC give 251.05'. Fix: the table cell.
# * ``p02-sources-ppm048b`` -- L-4, "IN4"'s radius changed to 300 ft in the design
#   file (PIs kept) and its centerline redrawn: the curve table (R, T, L), the EC
#   681+58.69, the POT 683+40.13 = "IND1" 59+72.49, the ramp's edges and its
#   station numbers all describe R 328.08. Fix: the base file, R at the PI back to
#   328.08 and the centerline redrawn.
# * ``p02-sources-cflpla`` -- CFL Davis Dam Road (pilot 14's prepared sheet): the
#   lower plan's PT lettered 38+48.48. The design's PT and the curve data (PC
#   34+00.32 lettered beside it, L 484.15') give 38+84.48: the sheet's lettering is
#   wrong against both the curve data and the design. Fix: the label.
# * ``p02-sources-fdot916`` -- FDOT sheet 1: the PC lettered +70.47 (digits
#   transposed); the design's PC, the drawn centerline's curve and the pavement
#   edges put it at 705+70.74. Fix: the label.
# * ``p02-sources-ppm045b`` -- L-1, "D13"'s bearing lettered N 00°03'30" W in the
#   design file (where L-1 keeps its bearings): the design, the drawn "D13" and the
#   POT offsets of "TB2" and "TB1" from it give N 00°03'30" E. Fix: the label, in the
#   base file it lives in.

PPM048_TABLE_T = "215.05'"
PPM048_DESIGN_R = 300.0
CFL_PT = "PT 38+48.48"
FDOT916_PC = "PC STA. +70.47"
#: how far a corrected label in a base file may sit from the one it replaces (feet, 0.5 in at 50 scale)
NEAR_FT = 25.0


def _build_ppm048_table(out: Path) -> Path:
    path = qa.prepare_ppm048(out)
    s = c.load(path)
    sheet = next(iter(s.doc.sheets.values()))
    rows = [list(r) for r in sheet.entities[qa.PPM048_TABLE].rows]
    if rows[1][3] != "251.05'":
        raise RuntimeError(f"L-4: curve 36's T reads {rows[1][3]!r}, not 251.05'")
    rows[1][3] = PPM048_TABLE_T
    c.ok(s.execute("modify_entity", {"id": qa.PPM048_TABLE, "changes": {"rows": rows}}))
    return c.save(s, path)


def _in4_pis(ali: Session, radius: Optional[float] = None) -> list:
    pis = [list(p["point"]) + ([p["radius"]] if p.get("radius") else [])
           for p in ali.doc.design.alignments["IN4"].to_dict()["pis"]]
    if radius is not None:
        pis[1] = pis[1][:2] + [radius]
    return pis


def _build_ppm048_design(out: Path) -> Path:
    path = qa.prepare_ppm048(out)
    aa = c.load(Path(out) / qa.PPM048_AA01)
    c.ok(aa.execute("modify_alignment", {"name": "IN4", "redraw": True,
                                         "changes": {"pis": _in4_pis(aa, PPM048_DESIGN_R)}}))
    c.save(aa, Path(out) / qa.PPM048_AA01)
    return path


def _build_cfl_pt(out: Path) -> Path:
    path = qa.prepare_cflpla(out)
    s = c.load(path)
    c.ok(s.execute("modify_entity", {"id": "TX-057", "changes": {"content": CFL_PT}}))
    return c.save(s, path)


def _build_fdot916_pc(out: Path) -> Path:
    path = qa.prepare_fdot916(out)
    s = c.load(path)
    sheet = next(iter(s.doc.sheets.values()))
    if sheet.entities["TX-057"].content != "PC STA. +70.74":
        raise RuntimeError(f"FDOT 1: the PC reads {sheet.entities['TX-057'].content!r}")
    c.ok(s.execute("modify_entity", {"id": "TX-057", "changes": {"content": FDOT916_PC}}))
    return c.save(s, path)


def _build_ppm045_d13(out: Path) -> Path:
    path = qa.prepare_ppm045(out)
    aa = c.load(Path(out) / qa.PPM_AA01)
    e = aa.doc.model_entities["TX-029"]
    if not e.content.endswith(" E"):
        raise RuntimeError(f"L-1: D13's bearing reads {e.content!r}")
    c.ok(aa.execute("modify_entity", {"id": "TX-029", "changes": {"content": e.content[:-1] + "W"}}))
    c.save(aa, Path(out) / qa.PPM_AA01)
    return path


START_PPM048_TABLE = c.register("p02-ppm048a", qa.PPM048_FILE, _build_ppm048_table)
START_PPM048_DESIGN = c.register("p02-ppm048b", qa.PPM048_FILE, _build_ppm048_design)
START_CFL_PT = c.register("p02-cflpla", qa.CFL_FILE, _build_cfl_pt)
START_FDOT916_PC = c.register("p02-fdot916", qa.FDOT916_FILE, _build_fdot916_pc)
START_PPM045_D13 = c.register("p02-ppm045b", qa.PPM_FILE, _build_ppm045_d13)


# ----------------------------------------------------------------- reading them


def _station_value(word: str):
    """A station lettered with ``word`` (PT, PC): its feet, else None."""
    def value_of(content: str) -> Optional[float]:
        if not re.search(rf"\b{word}\b", content or ""):
            return None
        found = nt.stations(content)
        if found:
            return found[0][0]
        m = re.search(r"\+\s*(\d{2}\.\d{2})", content)
        return float(m.group(1)) if m else None
    return value_of


def _cell_value(content: str) -> Optional[float]:
    m = re.match(r"^\s*([\d,]+(?:\.\d+)?)\s*(?:[’']|FT\.?)?\s*$", content or "")
    return float(m.group(1).replace(",", "")) if m else None


def _check_cell(start: str, table: str, row: int, col: int, want: float, what: str):
    """A table cell corrected to ``want``; the table's other cells, and everything
    else in every file, unchanged."""
    def check(baseline: Session, submitted: Session) -> Result:
        from roaddraft.document.entities import Table
        expected = Path(qa._built(start))
        truth = c.load(expected)
        old = next(iter(truth.doc.sheets.values())).entities[table]
        sheet = next(iter(submitted.doc.sheets.values()))
        tally = Tally()
        cands = [e for e in sheet.entities.values() if isinstance(e, Table)
                 and (e.id == table or math.dist(e.position, old.position) <= NEAR_IN)]
        allow = [table] + [e.id for e in cands]
        if len(cands) != 1:
            tally.add(what, f"{len(cands)} curve tables where the one was")
        else:
            new = cands[0]
            rows_ok = (len(new.rows) == len(old.rows) and
                       all(new.rows[i][j] == old.rows[i][j] for i in range(len(old.rows))
                           for j in range(len(old.rows[i])) if (i, j) != (row, col)))
            v = _cell_value(new.rows[row][col]) if rows_ok else None
            tally.add(what, None if rows_ok and v is not None and abs(v - want) <= 0.006 else
                      (f"{what} reads {new.rows[row][col]!r}; the other sources say {want:.2f}"
                       if rows_ok else "the curve table's other cells were changed"))
        tally.add("every other source unchanged",
                  qa.changed_outside(expected, submitted, allow_ids=allow, model=True))
        tally.add("the finding recorded", None if _finding(submitted) else
                  "no finding recorded (set_meta {\"updates\": {\"finding\": ...}})")
        return tally.result(f"{what} corrected to {want:.2f}, every other source unchanged, "
                            f"the finding recorded")
    return check


def _check_base_label(start: str, base: str, eid: str, want_az: float, what: str):
    """A label in a base file's model corrected where it lives: the bearing it
    letters within 1\" of ``want_az``; the rest of that file and of every other
    file unchanged."""
    def check(baseline: Session, submitted: Session) -> Result:
        expected = Path(qa._built(start))
        tally = Tally()
        home = Path(getattr(submitted.doc, "_path", "") or ".").parent
        want = qa.model_entities(read_document(expected.parent / base))
        got = qa.model_entities(read_document(home / base)) if (home / base).exists() else {}
        at = want[eid]["position"]
        cands = [(i, e["content"]) for i, e in got.items() if e.get("type") == "text"
                 and (i == eid or i not in want) and math.dist(e.get("position", [1e9, 1e9]), at) <= NEAR_FT
                 and nt.bearings(e.get("content", ""))]
        if len(cands) != 1:
            tally.add(what, f"{what} is lettered {len(cands)} times in {base} where the one was"
                      + (": " + ", ".join(repr(x[1]) for x in cands) if cands else ""))
        else:
            az = nt.bearings(cands[0][1])[0]
            off = abs((az - want_az + 180.0) % 360.0 - 180.0) * 3600.0
            tally.add(what, None if off <= 1.0 else f"{what} reads {cands[0][1]!r}")
        allow = {eid} | {i for i, _c in cands}
        other = next((i for i, e in want.items() if i not in allow and got.get(i) != e), None) or \
            next((i for i in got if i not in want and i not in allow), None)
        tally.add(f"the rest of {base} unchanged", f"{base}'s {other} was changed" if other else None)
        tally.add("every other source unchanged",
                  qa.changed_outside(expected, submitted, allow_files=[base], model=True))
        tally.add("the finding recorded", None if _finding(submitted) else
                  "no finding recorded (set_meta {\"updates\": {\"finding\": ...}})")
        return tally.result(f"{what} corrected in {base}, every other source unchanged, the finding "
                            f"recorded")
    return check


def _scratch_alignment(source: dict) -> Session:
    """An alignment rebuilt from its PIs as ``TRUE`` in a scratch session."""
    pis = [list(p["point"]) + ([p["radius"]] if p.get("radius") else []) for p in source["pis"]]
    s = Session()
    c.ok(s.execute("create_alignment", {"name": "TRUE", "begin_station": source["begin_station"],
                                        "pis": pis}))
    return s


def _design_problem_of(ali: Session, true: Session, name: str, radius: float) -> Optional[str]:
    if name not in ali.doc.design.alignments:
        return f"the design file has no {name} any more"
    curves = c.ok(ali.query("get_design_data", {"kind": "curves", "alignment": name}))["rows"]
    want = len(c.ok(true.query("get_design_data", {"kind": "curves", "alignment": "TRUE"}))["rows"])
    if len(curves) != want:
        return f"{name} has {len(curves)} curves; it has {want}"
    R = float(curves[0]["radius"])
    if abs(R - radius) > RADIUS_FT:
        return f"{name}'s curve is still R {R:.2f} ft; the other sources describe R {radius:.2f}"
    a = true.doc.design.alignments["TRUE"]
    b = ali.doc.design.alignments[name]
    station = math.ceil(max(a.begin_station, b.begin_station) / STEP_FT) * STEP_FT
    while station <= min(a.end_station, b.end_station):
        p = c.ok(true.query("station_to_xy", {"alignment": "TRUE", "station": station}))["point"]
        q = c.ok(ali.query("station_to_xy", {"alignment": name, "station": station}))["point"]
        if math.dist(p, q) > POSITION_FT:
            return (f"{name} at {station / 100:.0f}+{station % 100:05.2f} is {math.dist(p, q):.2f} ft "
                    f"from where the restored design puts it")
        station += STEP_FT
    return None


def _samples(e, n=8):
    if isinstance(e, Line):
        return [[e.start[0] + (e.end[0] - e.start[0]) * k / n,
                 e.start[1] + (e.end[1] - e.start[1]) * k / n] for k in range(n + 1)]
    if isinstance(e, Arc):
        a0, a1 = e.start_angle_deg, e.end_angle_deg
        sweep = (a1 - a0) % 360.0
        return [[e.center[0] + e.radius * math.cos(math.radians(a0 + sweep * k / n)),
                 e.center[1] + e.radius * math.sin(math.radians(a0 + sweep * k / n))] for k in range(n + 1)]
    return [list(v) for v in e.vertices]


def _check_design_of(start: str, prepared: str, base: str, name: str, layer: str, radius: float,
                     what: str):
    """``name`` restored in ``base`` to what the clean ``prepared`` start has, its
    centerline redrawn on ``layer`` (new elements, or ones anchored to it, lie on
    the restored design and cover it), the rest of ``base`` and every other file
    as the start has them."""
    def check(baseline: Session, submitted: Session) -> Result:
        expected = Path(qa._built(start))
        clean = c.document(Path(qa._built(prepared)).parent / base)
        true = _scratch_alignment(clean.design.alignments[name].to_dict())
        tally = Tally()
        home = Path(getattr(submitted.doc, "_path", "") or ".").parent
        if not (home / base).exists():
            tally.add(what, f"{base} is missing")
        else:
            ali = c.load(home / base)
            tally.add(what, _design_problem_of(ali, true, name, radius))
            want = qa.model_entities(read_document(expected.parent / base))
            got = qa.model_entities(read_document(home / base))
            # the line's own drawn elements and labels: a redraw replaces them, and the
            # engine re-places what is anchored to the line when its design changes
            mine = {i for d in (want, got) for i, e in d.items()
                    if (e.get("anchor") or {}).get("alignment") == name}
            drawn = [e for e in ali.doc.model_entities.values() if isinstance(e, (Line, Arc, Polyline))
                     and e.layer == layer and (e.id not in want or e.id in mine)]
            problem = None if drawn else f"{name}'s centerline is no longer drawn in {base}"
            for e in drawn:
                for p in _samples(e):
                    r = c.ok(true.query("xy_to_station", {"alignment": "TRUE", "point": p}))
                    if abs(r["offset"]) > DRAWN_FT:
                        problem = (f"{name}'s centerline drawn in {base} ({e.id}) runs "
                                   f"{abs(r['offset']):.1f} ft off the restored design")
                        break
                if problem:
                    break
            if not problem:
                a = true.doc.design.alignments["TRUE"]
                pts = [p for e in drawn for p in _samples(e, 40)]
                station = math.ceil(a.begin_station / STEP_FT) * STEP_FT
                while station <= a.end_station:
                    q = c.ok(true.query("station_to_xy", {"alignment": "TRUE", "station": station}))["point"]
                    if min(math.dist(q, p) for p in pts) > STEP_FT:
                        problem = f"{name}'s centerline is not drawn near {station / 100:.0f}+{station % 100:05.2f}"
                        break
                    station += STEP_FT
            tally.add(f"{name}'s centerline redrawn from it", problem)
            moved = next((i for i, e in want.items() if i not in mine and got.get(i) != e), None)
            added = next((i for i, e in got.items() if i not in want and i not in mine
                          and e.get("layer") != layer), None)
            tally.add(f"the rest of {base} unchanged",
                      f"{base}'s {moved or added} was changed" if (moved or added) else None)
        tally.add("every other source unchanged",
                  qa.changed_outside(expected, submitted, allow_files=[base], model=True))
        tally.add("the finding recorded", None if _finding(submitted) else
                  "no finding recorded (set_meta {\"updates\": {\"finding\": ...}})")
        return tally.result(f"{what}, its centerline redrawn, every other source unchanged, the "
                            f"finding recorded")
    return check


# ----------------------------------------------------------------- their solutions


def _solve_cell(row: int, col: int, content: str, finding: str):
    def solve(session: Session) -> None:
        sheet = next(iter(session.doc.sheets.values()))
        rows = [list(r) for r in sheet.entities[qa.PPM048_TABLE].rows]
        rows[row][col] = content
        c.ok(session.execute("modify_entity", {"id": qa.PPM048_TABLE, "changes": {"rows": rows}}))
        c.ok(session.execute("set_meta", {"updates": {"finding": finding}}))
    return solve


def _solve_ppm048_design(session: Session) -> None:
    """Over MCP: open_document the design file, put the PI's radius back to the
    curve table's 328.08, redraw, save; the finding on the sheet."""
    path = Path(session.doc._path).parent / qa.PPM048_AA01
    aa = c.load(path)
    was = c.ok(aa.query("get_design_data", {"kind": "curves", "alignment": "IN4"}))["rows"][0]["radius"]
    c.ok(aa.execute("modify_alignment", {"name": "IN4", "redraw": True,
                                         "changes": {"pis": _in4_pis(aa, 328.08)}}))
    c.save(aa, path)
    c.ok(aa.query("save_journal", {"path": str(journal_path(path))}))
    c.ok(session.execute("set_meta", {"updates": {"finding": (
        f"\"IN4\"'s curve in {qa.PPM048_AA01} was R {was:.2f}; the curve table (R 328.08', T "
        f"251.05', L 428.58'), the EC 681+58.69 and the POT 683+40.13 all give R 328.08. "
        f"Restored R 328.08 at the PI and redrew the centerline.")}}))


def _solve_base_label(base: str, eid: str, content: str, finding: str):
    def solve(session: Session) -> None:
        path = Path(session.doc._path).parent / base
        aa = c.load(path)
        c.ok(aa.execute("modify_entity", {"id": eid, "changes": {"content": content}}))
        c.save(aa, path)
        c.ok(aa.query("save_journal", {"path": str(journal_path(path))}))
        c.ok(session.execute("set_meta", {"updates": {"finding": finding}}))
    return solve


def _ppm045_d13_bearing() -> str:
    aa = c.document(Path(qa._built(START_PPM045_D13)).parent / qa.PPM_AA01)
    return aa.model_entities["TX-029"].content[:-1] + "E"


def _solve_ppm045_d13(session: Session) -> None:
    right = _ppm045_d13_bearing()
    _solve_base_label(qa.PPM_AA01, "TX-029", right,
                      f"\"D13\"'s bearing was lettered {right[:-1]}W in the design file; the "
                      f"design, the drawn line and the POT offsets give {right}. Corrected the "
                      f"label in {qa.PPM_AA01}.")(session)


def _check_ppm045_d13(baseline: Session, submitted: Session) -> Result:
    want = nt.bearings(_ppm045_d13_bearing())[0]
    return _check_base_label(START_PPM045_D13, qa.PPM_AA01, "TX-029", want,
                             "\"D13\"'s bearing in the design file")(baseline, submitted)


PPM048_PROMPT = ("Sheet L-4 and the base files it references are meant to tell one story about the "
                 "\"D13\", \"IND1\" and \"IN4\" lines: the alignment designs in the design file, the "
                 "centerlines drawn from them, the station ticks and numbers, the bearings and "
                 "distances, the EC, POC and POT stations and the curve table. They disagree in one "
                 "place. Find it, work out from the rest of the evidence which one is wrong, and "
                 "correct that one, in whichever file it lives, so it agrees with the others. Change "
                 "nothing else; the construction notes are not part of this. Then record what was "
                 "wrong in the sheet file with set_meta {\"updates\": {\"finding\": \"...\"}}.")
CFL_PROMPT = ("Sheet PLA(SAMPLE) and the base files it references are meant to tell one story about "
              "CL1 in the lower plan: the alignment design in the alignment file, the centerline "
              "drawn from it, the pavement edges in the corridor file, the station ticks and "
              "numbers, the bearing, the PC and PT stations and the curve data. They disagree in "
              "one place. Find it, work out from the rest of the evidence which one is wrong, and "
              "correct that one, in whichever file it lives, so it agrees with the others. Change "
              "nothing else; the construction notes are not part of this. Then record what was "
              "wrong in the sheet file with set_meta {\"updates\": {\"finding\": \"...\"}}.")
FDOT916_PROMPT = ("Sheet 1 and the base files it references are meant to tell one story about CL1: "
                  "the alignment design in the alignment file, the centerline drawn from it, the "
                  "pavement edges in the design file, the station ticks and numbers, the bearing "
                  "and the PC station. They disagree in one place. Find it, work out from the rest "
                  "of the evidence which one is wrong, and correct that one, in whichever file it "
                  "lives, so it agrees with the others. Change nothing else; the drainage notes "
                  "are not part of this. Then record what was wrong in the sheet file with "
                  "set_meta {\"updates\": {\"finding\": \"...\"}}.")

PROBES += [
    Probe(id="p02-sources-ppm048a", start=START_PPM048_TABLE, tags=["pilot", "sources", "caltrans", "edit"],
          prompt=PPM048_PROMPT,
          check=_check_cell(START_PPM048_TABLE, qa.PPM048_TABLE, 1, 3, 251.05, "curve 36's T in the curve table"),
          solve=_solve_cell(1, 3, "251.05'", "Curve 36's T read 215.05'; its R 328.08' and Δ "
                            "74°50'50\", its L 428.58' and the design give 251.05'. Corrected the table."),
          note="Planted: curve 36's T lettered 215.05' in L-4's CURVE DATA table (251.05 transposed); "
               "R and Δ in the same row, L, the design and the EC agree on 251.05. The table is a "
               "Table entity: the fix is its rows, the other nine cells untouched. Naive wrong "
               "(tests): bending \"IN4\" to R 281 so its T is 215.05 (the design changes, the cell "
               "not), or putting the cell right and \"refining\" the R beside it to the design's "
               "328.0793 (another cell changed)."),
    Probe(id="p02-sources-ppm048b", start=START_PPM048_DESIGN,
          tags=["pilot", "sources", "caltrans", "edit", "basefile"], prompt=PPM048_PROMPT,
          check=_check_design_of(START_PPM048_DESIGN, "p14-ppm048a", qa.PPM048_AA01, "IN4",
                                 "V-ALIGN-CNTR", 328.0793, "\"IN4\" restored to R 328.08 in the design file"),
          solve=_solve_ppm048_design,
          note="Planted: \"IN4\"'s radius 300 ft in the design file (PIs kept) with its centerline "
               "redrawn; the curve table, EC 681+58.69, POT 683+40.13 = \"IND1\" 59+72.49 and the "
               "ramp's station numbers describe R 328.08. \"D13\" and \"IND1\", drawn on the same "
               "layer, must stay as they are. Naive wrong (tests): re-lettering the table and the "
               "EC from get_design_data (the sheet changes, the design not), or restoring the "
               "radius without redrawing."),
    Probe(id="p02-sources-cflpla", start=START_CFL_PT, tags=["pilot", "sources", "cfl", "edit"],
          prompt=CFL_PROMPT,
          check=_check_label(START_CFL_PT, "TX-057", _station_value("PT"), 3884.48, "the lower PT label", model=True),
          solve=_solve_label("TX-057", "PT 38+84.48",
                             "The lower PT was lettered 38+48.48; the design's PT and the curve data "
                             "(PC 34+00.32 + L 484.15') give 38+84.48. Corrected the label."),
          note="Planted: the lower plan's PT lettered 38+48.48; the curve data (the PC lettered "
               "34+00.32 plus L 484.15') and the design both put it at 38+84.48, so the sheet's "
               "lettering is wrong against the table and the design together. The design is pilot "
               "14's rebuild of the whole curve. Naive wrong (tests): changing the curve data's L "
               "to fit the label."),
    Probe(id="p02-sources-fdot916", start=START_FDOT916_PC, tags=["pilot", "sources", "fdot", "edit"],
          prompt=FDOT916_PROMPT,
          check=_check_label(START_FDOT916_PC, "TX-057", _station_value("PC"), 70.74, "the PC label", model=True),
          solve=_solve_label("TX-057", "PC STA. +70.74",
                             "The PC was lettered +70.47; the design's PC, the drawn centerline's "
                             "curve and the pavement edges put it at 705+70.74. Corrected the label."),
          note="Planted: FDOT sheet 1's PC lettered +70.47 (digits transposed); the design puts it at "
               "705+70.74, where the drawn centerline and the edges begin to curve. The label is "
               "the sheet's only alignment lettering besides the bearing and the station numbers. "
               "Naive wrong (tests): sliding the design's stationing 0.27 ft so its PC is 705+70.47."),
    Probe(id="p02-sources-ppm045b", start=START_PPM045_D13,
          tags=["pilot", "sources", "caltrans", "edit", "basefile"], prompt=PPM_PROMPT,
          check=_check_ppm045_d13, solve=_solve_ppm045_d13,
          note="Planted: \"D13\"'s bearing lettered N 00°03'30\" W, a 7' turn on a line that runs "
               "almost due north, in the design file, where L-1 keeps its bearings (the sheet file "
               "has none of its own). The design, the drawn line and the POT offsets give E. The "
               "fix is in the base file. Naive wrong (tests): placing a corrected bearing on the "
               "sheet over the wrong one (the base file still says W). Replacing the label in the "
               "base file with a new text near it passes."),
]

__all__ = ["PROBES"]
