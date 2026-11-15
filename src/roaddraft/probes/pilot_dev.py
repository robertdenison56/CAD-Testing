"""``pilot-dev``: pilot instances on the clean sample sheets, for choosing a checkpoint.

The training plan (``RoadDraft_Training_Plan.md`` §8, "A validation set on real
sheets", and §6 decision 7, settled 2026-11-13) keeps every sheet a held-out
pilot uses out of training and asks for a validation set on the redrafted
sheets that carry an alignment and are in no pilot, no real-sheet eval set and
no dev set. Nine are in none by sheet id, and eight of them are clean: Caltrans
PPM-206, 207, 214, 215 and 218 (the electrical examples), FDOT-924 (a selective
clearing and grubbing plan) and WFL Other Sections p06 (an erosion control plan)
and p09 (a wall plan). The ninth, the CFL parking-lot SWPPP sheet, is left out
(below). This module sets instances of four pilot families on the eight:

* ``p17`` twisted sheet: the line's viewport re-cut at a new twist (or turned
  half a turn), the line lettered so it reads from the bottom or right;
* ``p04`` crowded annotation: the lines stripped and lettered again among the
  sheet's own lettering;
* ``p05`` sheet breaks: a fresh sheet file over the base files, the drafter
  choosing how many sheets and how to turn each one;
* ``p11`` redlines with knock-on edits: a checker's redline to restation a line,
  everything downstream lettered again and nothing stale left.

It is for choosing a checkpoint only, like ``d1-real-dev``: never trained on,
never reported. The task set is ``pilot-dev`` (``eval/taskset.py``).

**Reuse, not copies.** The builders, checks, scripted solutions and prompts are
the pilot families' own (``probes.pilot.layout`` and ``probes.pilot.redlines``),
by import. Those functions look their instance up by id in the family's table
(``layout.P4``, ``P17``, ``P5``; ``redlines._instance``), so importing this module
adds its instances to those tables under ids of their own (``p17-dev-ppm206``
and so on, all with ``-dev-`` after the family). It never adds to a family's
``PROBES``, to ``probes.pilot.PILOT_PROBES`` or to ``redlines.INSTANCES``, and it
lives outside the pilot package: the held-out set, its task texts and its check
hash (``eval.probe_tasks.check_version``, over the package's sources) do not
move.

**What each sheet carries** (measured 2026-11-13; ``tasks.real.build_real_task``
is what makes a lettering job of a line, and it refuses traced linework, more
than 6 tangents, and a line under 200 ft):

* PPM-206 (E-1) and PPM-207 (E-9): the same design, lines A1 and CL2 (two
  tangents each, no curve), 1" = 20', twist -90°. PPM-206: p17 on A1, p11 on A1;
  p04 left out (the labelers' default poses already clear the sheet). PPM-207 is
  the crowded one (551 sheet entities): p17 on CL2, p04 on both lines, p11 on CL2.
* PPM-214 (E-5) and PPM-215 (E-56): the same design again, line B (one tangent)
  and line E (176 ft, too short to letter), 1" = 20', twist -20.33°. PPM-214: p17
  on B re-cut at 120°. PPM-215: p17 on B turned half a turn, p11 on B. p04 left
  out on both (the default poses pass).
* PPM-218 (E-9 of example F): CL1 and CL2 are traced (14 and 11 tangents), so no
  lettering job; p05 on CL2 only, whose stationing runs up and to the left, so
  a north-up sheet reads it right to left.
* FDOT-924 (sheet 1371): CL1, one 1063-ft tangent, 1" = 69'. p17, p11, and p05
  twice: at 1" = 40' it needs two sheets (a real break), at 1" = 50' one sheet
  set corner to corner where the level cut takes two. p04 left out (defaults pass).
* CFL parking-lot SWPPP (ECP(PKG)): not used. Its CL1 (traced, 44 tangents) and
  its alignment file's linework are the CFL-F-Parking-Lot sheet's, and that sheet
  is held out twice: the pilot ``p18-redline-pdf-cfld1`` and a ``d1-real``
  construction-callouts task both work on that line. A sheet id of its own does
  not make a design clean, so ``p05-dev-cflpkg``, the one instance set on it, was
  dropped (2026-11-14, before any ``pilot-dev`` run); ``tests/test_pilot_dev.py``
  holds every sheet here to sharing no design line and no base drawing with any
  other eval set.
* WFL Other Sections p06 (F.2): CL1 (one tangent) and CL2 (two tangents, then a
  compound pair of curves to its end), 1" = 100'. p17 on CL2, p04 on CL1 among
  CL2's published lettering, p05 on CL1 at 1" = 40' (one sheet turned; the level
  cut takes two), p11 restationing CL1. A radius or PI redline (``p11``'s other two
  kinds) is not possible on any of the eight: CL2 is the only line with a curve,
  and a compound curve that ends the line has no PI form (``pis_from_elements``
  returns none), so it cannot be re-made with a new radius.
* WFL Other Sections p09 (H.5): CL1 is one 211-ft curve with no tangent, which no
  lettering job takes; p05 on it at 1" = 40' (stationing runs right to left on a
  north-up sheet).

**Weaker than the held-out instances**, where they differ: the four Caltrans
sheets are two designs, each drawn twice; the electrical sheets and FDOT-924 are
at 1" = 20' and 69' (the spec drafts at 40' and 50', which is part of why the
real-sheet catalogue left them out: ``tasks.real.candidates``), so their lettering
is graded at a scale the board's tasks never use; every lettered line but WFL
CL2 is tangents only, so the curve items (BC/EC, bubbles, the CURVE DATA table)
arise only in the WFL p17 instance; the two p04 sheets are lightly crowded (the
default poses put one label, and two, on other lettering, against 3 to 25 on
the held-out sheets); four of the five p05 stretches fit one sheet, so they test
the count and the turn but no match line; and every p11 is a restation.

Each instance records the naive answers its family is built to catch (``NAIVE``),
and ``tests/test_pilot_dev.py`` holds each one failing and the scripted solution
passing, at both prompt levels.

    python -m roaddraft.probes.pilot_dev selftest [ID ...]
"""
from __future__ import annotations

import copy
import math
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.document.entities import Text
from roaddraft.probes.base import Probe
from roaddraft.probes.pilot import common, layout, redlines
from roaddraft.probes.pilot.redlines import Redline
from roaddraft.tasks.reference import phase_commands

#: the redrafted sheets with an alignment that no held-out pilot, real-sheet eval set or
#: dev set uses (plan §8), and whose design no sheet of those sets carries;
#: ``tests/test_pilot_dev.py`` derives them again
SHEETS = ("PPM-206", "PPM-207", "PPM-214", "PPM-215", "PPM-218",
          "FDOT-924-1-Selective-CandG-Plan",
          "WFL-Other-Sections-p06", "WFL-Other-Sections-p09")
#: the task set (``eval/taskset.py``)
TASK_SET = "pilot-dev"

_WFL06 = "WFL-Other-Sections-p06"
_FDOT924 = "FDOT-924-1-Selective-CandG-Plan"
_WFL = "Western Federal Lands"


# ================================================================ p17, twisted sheet

#: as ``layout.P17``: each re-cut with its viewport fitted to the usable area and
#: centred on the line, at a twist where the labelers without ``view_rotation``, and
#: with the published twist, letter from the wrong side (``published`` is that twist)
P17 = {
    "p17-dev-ppm206": {"sheet_id": "PPM-206", "sheet": "E-1", "name": "A1", "ref": "AA01",
                       "agency": "Caltrans", "whole": "50", "twist": 50.0, "fit": True},
    "p17-dev-ppm207": {"sheet_id": "PPM-207", "sheet": "E-9", "name": "CL2", "ref": "AA01",
                       "agency": "Caltrans", "whole": "50", "twist": -140.0, "fit": True},
    "p17-dev-ppm214": {"sheet_id": "PPM-214", "sheet": "E-5", "name": "B", "ref": "AA01",
                       "agency": "Caltrans", "whole": "20", "twist": 120.0, "fit": True},
    # the published E-56 turned half a turn, as p17-twist-ppm160 turns PD-1
    "p17-dev-ppm215": {"sheet_id": "PPM-215", "sheet": "E-56", "name": "B", "ref": "AA01",
                       "agency": "Caltrans", "whole": "20", "turn": 180.0},
    "p17-dev-wfl06": {"sheet_id": _WFL06, "sheet": "F.2", "name": "CL2", "ref": "ALI",
                      "agency": _WFL, "whole": "110, 115", "twist": 130.0, "fit": True},
    "p17-dev-fdot924": {"sheet_id": _FDOT924, "sheet": "1371", "name": "CL1", "ref": "ALI",
                        "agency": "FDOT", "whole": "6400, 6405", "twist": 150.0, "fit": True},
}
#: the published twists, the second naive answer of each p17 instance
PUBLISHED_TWIST = {"PPM-206": -90.0, "PPM-207": -90.0, "PPM-214": -20.33, "PPM-215": -20.33,
                   _WFL06: 0.0, _FDOT924: 0.0}

_P17_NOTES = {
    "p17-dev-ppm206": "E-1 (Electrical Example B1, 1\" = 20') re-cut from -90° to 50°: A1 "
                      "(47+92.96 to 53+92.81, two tangents) now climbs right to left at 40°. "
                      "Naive answers checked: without view_rotation, and with the published "
                      "-90°, every label reads from the wrong side.",
    "p17-dev-ppm207": "E-9 (Electrical Example B2, 1\" = 20') re-cut from -90° to -140°: CL2 "
                      "(47+95.88 to 51+83.78, two tangents, due east in the model) falls right "
                      "to left at 40°. Naive answers checked: without view_rotation every label, "
                      "with the published -90° some, read from the wrong side.",
    "p17-dev-ppm214": "E-5 (Electrical Example E1, 1\" = 20') re-cut from -20.33° to 120°: B "
                      "(15+50.47 to 21+49.97, one tangent) climbs right to left at 40°. Naive "
                      "answers checked: without view_rotation, and with the published -20.33° "
                      "(the same here: the line runs at 20.2°), every label reads from the wrong "
                      "side.",
    "p17-dev-ppm215": "E-56 (Electrical Example E2, the design of E-5) turned half a turn, from "
                      "-20.33° to 159.67°: B runs right to left. Naive answers checked: without "
                      "view_rotation, and with the published twist, every label reads from the "
                      "wrong side.",
    "p17-dev-wfl06": "WFL erosion control sheet F.2 (1\" = 100') re-cut from 0° to 130°: CL2 "
                     "(109+90.07 to 115+47.19: two tangents, then a compound pair of curves, R "
                     "1410.76' and R 1394.51') climbs right to left. The one p17 instance here "
                     "with curves (BC, PCC, bubbles, the table). Naive answers checked: without "
                     "view_rotation (the published twist too) every label reads from the wrong "
                     "side.",
    "p17-dev-fdot924": "FDOT selective clearing and grubbing plan sheet 1371 (1\" = 69') re-cut "
                       "from 0° to 150°: CL1 (6399+22.74 to 6409+85.42, one tangent) climbs "
                       "right to left at 31°. Naive answers checked: without view_rotation (the "
                       "published twist too) every label reads from the wrong side.",
}


# ================================================================ p04, crowded annotation

P4 = {
    "p04-dev-ppm207": {"sheet_id": "PPM-207", "sheet": "E-9", "ref": "AA01", "whole": "50",
                       "names": ("A1", "CL2")},
    # CL1 lettered among CL2's published lettering and the survey's contour labels
    "p04-dev-wfl06": {"sheet_id": _WFL06, "sheet": "F.2", "ref": "ALI", "whole": "120, 125",
                      "names": ("CL1",), "kept": ("CL2",), "set": f"{_WFL} set",
                      "way": "as follows"},
}
_P4_NOTES = {
    "p04-dev-ppm207": "E-9 (Electrical Example B2, 1\" = 20', twist -90°, 551 sheet entities) "
                      "with A1 and CL2 (two tangents each) stripped. Naive answer checked: the "
                      "labelers' default poses put a bearing on the sheet's own 26' callout "
                      "(D1-08). Lightly crowded: one overlap against the held-out sheets' 3 to "
                      "25.",
    "p04-dev-wfl06": "WFL erosion control sheet F.2 (1\" = 100', untwisted) with CL1 (one "
                     "tangent) stripped; CL2 keeps its published lettering. Naive answer "
                     "checked: the default poses put two station numbers on the survey base's "
                     "contour labels (4725, 4735) (D1-08).",
}


# ================================================================ p05, sheet breaks

_FDOT_FILES = {"ALGNRD01.rdraft": "ALI", "DSGNRD01.rdraft": "COR"}
_FL_BORDER = ("the Federal Lands 11 x 17 plan sheet border (ANSI B, title block template "
              "wfl)")

#: as ``layout.P5``, every one strict (``spare`` 0: only the fewest sheets pass)
P5 = {
    "p05-dev-fdot924": {
        "sheet_id": _FDOT924, "agency": "FDOT", "files": _FDOT_FILES, "doc": "SCGPRD01.rdraft",
        "alignment": "ALI:CL1", "line": "CL1", "a": "6400+00.00", "b": "6409+00.00",
        "size": "ANSI_B", "template": "fdot", "border": layout._FDOT_BORDER,
        "road": "SR 91 (Orange County)", "fpi": 40.0, "spare": 0},
    "p05-dev-fdot924x50": {
        "sheet_id": _FDOT924, "agency": "FDOT", "files": _FDOT_FILES, "doc": "SCGPRD01.rdraft",
        "alignment": "ALI:CL1", "line": "CL1", "a": "6400+00.00", "b": "6409+00.00",
        "size": "ANSI_B", "template": "fdot", "border": layout._FDOT_BORDER,
        "road": "SR 91 (Orange County)", "fpi": 50.0, "spare": 0},
    "p05-dev-wfl06": {
        "sheet_id": _WFL06, "agency": "WFL",
        "files": {"pfh247-1_sur.rdraft": "SUR", "pfh247-1_ali.rdraft": "ALI",
                  "pfh247-1_cor.rdraft": "COR"},
        "doc": "pfh247-1_pln_ec.rdraft", "alignment": "ALI:CL1", "line": "CL1",
        "a": "118+00.00", "b": "125+00.00", "size": "ANSI_B", "template": "wfl",
        "border": _FL_BORDER, "road": "PFH 247(1)", "fpi": 40.0, "spare": 0},
    "p05-dev-ppm218": {
        "sheet_id": "PPM-218", "agency": "Caltrans",
        "files": {"1300010110aa01.rdraft": "AA01", "1300010110bb01.rdraft": "BB01"},
        "doc": "1300010110ua009.rdraft", "alignment": "AA01:CL2", "line": "CL2",
        "a": "10+00.00", "b": "16+90.00", "size": "ANSI_D", "template": "caltrans",
        "border": "the Caltrans 22 x 34 plan sheet border (ANSI D, title block template "
                  "caltrans)",
        "road": "Electrical Example F", "fpi": 40.0, "spare": 0},
    "p05-dev-wfl09": {
        "sheet_id": "WFL-Other-Sections-p09", "agency": "WFL",
        "files": {"olym11-9_sur.rdraft": "SUR", "olym11-9_ali.rdraft": "ALI",
                  "olym11-9_cor.rdraft": "COR"},
        "doc": "olym11-9_pln_wall.rdraft", "alignment": "ALI:CL1", "line": "CL1",
        "a": "109+80.00", "b": "111+80.00", "size": "ANSI_B", "template": "wfl",
        "border": _FL_BORDER, "road": "NPS OLYM 11(9)", "fpi": 40.0, "spare": 0},
}
#: the fewest sheets each stretch takes (``layout._fewest``; a test holds it)
FEWEST = {"p05-dev-fdot924": 2, "p05-dev-fdot924x50": 1, "p05-dev-wfl06": 1,
          "p05-dev-ppm218": 1, "p05-dev-wfl09": 1}
_P5_NOTES = {
    "p05-dev-fdot924": "SR 91 CL1 6400+00 to 6409+00 at 1\" = 40' on the FDOT border (616 x 384 "
                       "ft): 900 ft of one tangent heading due east, so the level cut is also "
                       "the fewest, 2 sheets, and north-up sheets are level ones. Naive answer "
                       "checked: three even sheets.",
    "p05-dev-fdot924x50": "The same stretch at 1\" = 50' (770 x 480 ft): one sheet, the tangent "
                          "set corner to corner. Naive answers checked: north-up sheets and the "
                          "level cut (2 each). No break, so no match line.",
    "p05-dev-wfl06": "PFH 247(1) CL1 118+00 to 125+00 at 1\" = 40' on the Federal Lands border "
                     "(624 x 416 ft): 700 ft of one tangent at 3.9°, one sheet set corner to "
                     "corner. Naive answers checked: north-up sheets and the level cut (2 each), "
                     "two even sheets. No match line.",
    "p05-dev-ppm218": "Electrical Example F, CL2 (traced, 11 tangents) 10+00 to 16+90 at 1\" = "
                      "40' on the Caltrans border: one sheet, but the line heads up and to the "
                      "left (N 48° W to N 38° W in plan). Naive answers checked: a north-up sheet "
                      "(right to left), two even sheets. No match line.",
    "p05-dev-wfl09": "NPS OLYM 11(9) CL1, one 211-ft curve heading west, 109+80 to 111+80 at "
                     "1\" = 40': one sheet. Naive answers checked: a north-up sheet (right to "
                     "left), two even sheets. No match line; the shortest stretch of the set.",
}


# ================================================================ p11, redlines

_NEW = dict(loose_pluses=True)
_TANGENTS = dict(task_type="real-bearings", graded=("D1-02", "D1-03", "D1-05"), **_NEW)
_CALTRANS = dict(design_file="1300010110aa01.rdraft", design_ref="AA01", **_TANGENTS)

#: as ``redlines.MORE``; every one a restation (no line here has a curve whose radius or PI
#: can be re-made: the module docstring). Tangent-only lines letter the ``real-bearings``
#: job and are held to D1-02, D1-03 and D1-05, as WFL F.7 is held to its own.
P11 = [
    Redline(id="p11-dev-ppm206", sheet_id="PPM-206", sheet="E-1", alignment="A1",
            kind="station", value=17.0,
            note=['REVISE "A1" STATIONING: +17.00\'', 'BEGIN "A1" = 48+09.96'],
            cloud=(4792.96, 4950.0), cloud_offsets=(-25.0, 25.0), text_at=(3.0, 15.0),
            **_CALTRANS),
    Redline(id="p11-dev-ppm207", sheet_id="PPM-207", sheet="E-9", alignment="CL2",
            kind="station", value=29.0,
            note=['REVISE "CL2" STATIONING: +29.00\'', 'BEGIN "CL2" = 48+24.88'],
            cloud=(4795.88, 4950.0), cloud_offsets=(-25.0, 25.0), text_at=(15.5, 20.2),
            **_CALTRANS),
    Redline(id="p11-dev-ppm215", sheet_id="PPM-215", sheet="E-56", alignment="B",
            kind="station", value=-22.0,
            note=['REVISE "B" STATIONING: -22.00\'', 'BEGIN "B" = 15+28.47'],
            cloud=(1550.47, 1700.0), cloud_offsets=(-25.0, 25.0), text_at=(3.0, 15.0),
            **_CALTRANS),
    Redline(id="p11-dev-fdot924", sheet_id=_FDOT924, sheet="1371", alignment="CL1",
            kind="station", value=36.0,
            note=['REVISE "CL1" STATIONING: +36.00\'', 'BEGIN "CL1" = 6399+58.74'],
            cloud=(639922.74, 640100.0), cloud_offsets=(-25.0, 25.0), text_at=(1.5, 8.6),
            design_file="ALGNRD01.rdraft", design_ref="ALI", agency="fdot", cite=r"STA\.\s*",
            **_TANGENTS),
    Redline(id="p11-dev-wfl06", sheet_id=_WFL06, sheet="F.2", alignment="CL1",
            kind="station", value=-43.0,
            note=['REVISE "CL1" STATIONING: -43.00\'', 'BEGIN "CL1" = 117+19.72'],
            cloud=(11762.72, 11900.0), cloud_offsets=(-30.0, 30.0), text_at=(9.0, 6.2),
            design_file="pfh247-1_ali.rdraft", design_ref="ALI", agency="wfl",
            revision="note", **_TANGENTS),
]
_P11_BY_ID = {i.id: i for i in P11}
_P11_NAIVE = ("Naive answers checked: the design alone (stale lettering), the lettering redone "
              "with the base left alone, new lettering beside the old.")
_P11_NOTES = {
    "p11-dev-ppm206": "E-1, A1 restationed +17 ft (BEGIN 47+92.96 -> 48+09.96): every tick and "
                      "station number moves; the bearings stay. " + _P11_NAIVE,
    "p11-dev-ppm207": "E-9 (the crowded sheet), CL2 restationed +29 ft (BEGIN 47+95.88 -> "
                      "48+24.88). " + _P11_NAIVE,
    "p11-dev-ppm215": "E-56, B restationed -22 ft (BEGIN 15+50.47 -> 15+28.47). " + _P11_NAIVE,
    "p11-dev-fdot924": "FDOT sheet 1371, CL1 restationed +36 ft (BEGIN 6399+22.74 -> "
                       "6399+58.74); the revision goes in the FDOT REVISIONS rows. " + _P11_NAIVE,
    "p11-dev-wfl06": "WFL F.2, CL1 restationed -43 ft (BEGIN 117+62.72 -> 117+19.72); the "
                     "border has no revision block, so the revision is a note. " + _P11_NAIVE,
}


# ================================================================ registration


def _install() -> None:
    """Make the families' functions find these instances by id (module docstring)."""
    for table, mine in ((layout.P17, P17), (layout.P4, P4), (layout.P5, P5)):
        for pid, cfg in mine.items():
            if table.get(pid, cfg) is not cfg:
                raise RuntimeError(f"{pid} is already a held-out instance")
            table[pid] = cfg
    if not getattr(redlines._instance, "pilot_dev", False):
        held_out = redlines._instance

        def _instance(inst_id: str) -> Redline:
            return _P11_BY_ID[inst_id] if inst_id in _P11_BY_ID else held_out(inst_id)
        _instance.pilot_dev = True
        redlines._instance = _instance


_install()


def _p11_probe(inst: Redline) -> Probe:
    """``redlines._probe`` with this module's note and the start registered here."""
    key = "note" if inst.revision == "note" else inst.kind
    template = redlines.PROMPTS[key]
    if inst.sheet.isdigit():   # FDOT's "1371": "everything on sheet 1371"
        template = template.replace("everything on {sheet}", "everything on sheet {sheet}")
    words = dict(sheet=inst.sheet, name=inst.alignment, design=inst.design_file,
                 ref=inst.design_ref, by=redlines.REVISED_BY, on=redlines.REVISED_ON)
    return Probe(id=inst.id, prompt=template.format(**words), check=redlines.make_check(inst),
                 solve=redlines.make_solve(inst), note=_P11_NOTES[inst.id],
                 tags=["pilot-dev", "redline", "edit", inst.agency, "base-file", inst.kind],
                 start=common.register(inst.id, common.sheet_file(inst.sheet_id),
                                       redlines._builder(inst)),
                 vague=redlines.VAGUE.format(**words), vague_check=redlines.make_check(inst, "vague"))


PROBES: List[Probe] = []
for _pid in P17:
    PROBES.append(Probe(
        id=_pid, prompt=layout._p17_prompt(_pid), check=layout._p17_check(_pid),
        solve=layout._p17_solve(_pid), note=_P17_NOTES[_pid],
        tags=["pilot-dev", "layout", "twist", "verifier"],
        start=common.register(_pid, common.sheet_file(P17[_pid]["sheet_id"]),
                              layout._p17_builder(_pid)),
        vague=layout._p17_vague(_pid), vague_check=layout._p17_check(_pid, "vague")))
for _pid in P4:
    PROBES.append(Probe(
        id=_pid, prompt=layout._p4_prompt(_pid), check=layout._p4_check(_pid),
        solve=layout._p4_solve(_pid), note=_P4_NOTES[_pid],
        tags=["pilot-dev", "layout", "crowded", "verifier"],
        start=common.register(_pid, common.sheet_file(P4[_pid]["sheet_id"]),
                              layout._p4_builder(_pid)),
        vague=layout._p4_vague(_pid), vague_check=layout._p4_check(_pid, "vague")))
for _pid in P5:
    PROBES.append(Probe(
        id=_pid, prompt=layout._p5_prompt(_pid), check=layout._p5_check(_pid),
        solve=layout._p5_solve(_pid), note=_P5_NOTES[_pid],
        tags=["pilot-dev", "layout", "sheet-breaks", "match-line", P5[_pid]["agency"]],
        start=common.register(_pid, P5[_pid]["doc"], layout._p5_builder(_pid)),
        vague=layout._p5_vague(_pid), vague_check=layout._p5_check(_pid, "vague")))
PROBES += [_p11_probe(i) for i in P11]

BY_ID: Dict[str, Probe] = {p.id: p for p in PROBES}
if len(BY_ID) != len(PROBES):
    raise RuntimeError("two pilot-dev probes share an id")


def sheet_of(pid: str) -> str:
    """The redrafted sheet an instance is set on."""
    if pid in _P11_BY_ID:
        return _P11_BY_ID[pid].sheet_id
    return (P17.get(pid) or P4.get(pid) or P5[pid])["sheet_id"]


# ================================================================ the naive answers

#: a naive answer: ``answer(session)`` on a copy of the start, then the probe's check
Naive = Callable[[Session], None]


def letter_defaults(session: Session, sheet_id: str, sheet_name: str, names: Sequence[str],
                    view_rotation: float) -> None:
    """The labelers' default poses at ``view_rotation`` (no clearing), tables placed
    clear: the naive answer of p04 (at the sheet's twist) and p17 (at none, or the
    published one). As ``tests/test_pilot_layout.py`` letters it."""
    given = layout._given(session, sheet_name)
    for name in names:
        task = copy.deepcopy(layout._task(sheet_id, name))
        task.brief.deliverable.pop("label_poses", None)
        task.brief.deliverable["view_rotation"] = view_rotation
        for command, params in phase_commands(task, ["stationing", "bearings", "callouts"]):
            common.ok(session.execute(command, params))
    placer = layout._Placer(session, layout._truth(sheet_id, names[0], given), given)
    layout._place_tables(session, placer, sheet_id, names, sheet_name)


def lay_sheets(session: Session, cfg: dict, ends: Sequence[float], twists: Sequence[float]) -> None:
    """Sheets ending at ``ends``, viewports filling the usable area less 0.1 in at
    ``twists``, each break's match line drawn square and lettered on both sheets:
    a p05 layout done properly but for the count or the turn."""
    fpi = float(cfg.get("fpi", layout.FPI))
    ua = layout._usable(cfg["size"], cfg["template"])
    align = layout._road(session, cfg["alignment"])
    st = align.stations()
    starts = [st.parse(cfg["a"])] + list(ends[:-1])
    common.ok(session.execute("create_layer", {"name": "ML"}))
    names = []
    for k, (lo, hi, twist) in enumerate(zip(starts, ends, twists)):
        _s, pts, _d = layout._samples(align, lo, hi)
        bb = geo.bbox_of_points([geo.rotate_point(list(p), twist) for p in pts])
        centre = geo.rotate_point([(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0], -twist)
        names.append(f"S{k + 1}")
        common.ok(session.execute("create_sheet", {"name": names[-1], "size": cfg["size"],
                                                   "title_block_template": cfg["template"]}))
        common.ok(session.execute("create_viewport", {
            "sheet": names[-1], "center_paper": [(ua[0] + ua[2]) / 2, (ua[1] + ua[3]) / 2],
            "width_in": ua[2] - ua[0] - 0.1, "height_in": ua[3] - ua[1] - 0.1,
            "model_center": centre, "feet_per_inch": fpi, "rotation_deg": twist}))
    for k, b in enumerate(ends[:-1]):
        for name in names[k:k + 2]:
            p, q = [common.ok(session.query("station_to_xy", {
                "alignment": cfg["alignment"], "station": st.format(b), "offset": off,
                "sheet": name}))["on_sheet"]["sheet_point"] for off in (-60.0, 60.0)]
            common.ok(session.execute("draw_line", {"space": name, "layer": "ML", "start": p,
                                                    "end": q}))
            common.ok(session.execute("place_text", {
                "space": name, "layer": "ML", "content": f"MATCH LINE STA {st.format(b)}",
                "position": [p[0] + (q[0] - p[0]) * 0.8, p[1] + (q[1] - p[1]) * 0.8],
                "height": 0.1, "halign": "center", "valign": "bottom",
                "rotation_deg": geo.reading_up(math.degrees(math.atan2(q[1] - p[1],
                                                                        q[0] - p[0])))}))


def _stretch(session: Session, cfg: dict):
    fpi = float(cfg.get("fpi", layout.FPI))
    ua = layout._usable(cfg["size"], cfg["template"])
    align = layout._road(session, cfg["alignment"])
    st = align.stations()
    return align, st.parse(cfg["a"]), st.parse(cfg["b"]), ua[2] - ua[0] - 0.1, \
        ua[3] - ua[1] - 0.1, fpi


def _north_up_ends(align, a: float, b: float, w: float, h: float, fpi: float) -> List[float]:
    """The longest north-up sheets in turn, ending on 10-ft stations."""
    ends, start = [], a

    def fits(lo, hi):
        _s, pts, _d = layout._samples(align, lo, hi)
        return ((pts[:, 0].max() - pts[:, 0].min()) / fpi <= w
                and (pts[:, 1].max() - pts[:, 1].min()) / fpi <= h)
    while not fits(start, b):
        lo, hi = start, b
        while hi - lo > 0.5:
            lo, hi = ((lo + hi) / 2, hi) if fits(start, (lo + hi) / 2) else (lo, (lo + hi) / 2)
        start = math.floor(lo / 10.0) * 10.0
        ends.append(start)
    return ends + [b]


def _p5_north_up(cfg: dict) -> Naive:
    def answer(session: Session) -> None:
        align, a, b, w, h, fpi = _stretch(session, cfg)
        ends = _north_up_ends(align, a, b, w, h, fpi)
        lay_sheets(session, cfg, ends, [0.0] * len(ends))
    return answer


def _p5_level(cfg: dict) -> Naive:
    """The conventional cut: each sheet's chord within 3° of level."""
    def answer(session: Session) -> None:
        align, a, b, w, h, fpi = _stretch(session, cfg)
        ends = layout._greedy(align, a, b, w, h, round_to=10.0, level=3.0, fpi=fpi)
        twists = [layout._fit(align, lo, hi, w, h, 3.0, fpi)[0]
                  for lo, hi in zip([a] + ends[:-1], ends)]
        lay_sheets(session, cfg, ends, twists)
    return answer


def _p5_one_more(pid: str, cfg: dict) -> Naive:
    """One sheet more than the fewest, cut evenly, each fitted."""
    def answer(session: Session) -> None:
        align, a, b, w, h, fpi = _stretch(session, cfg)
        n = layout._fewest(pid) + 1
        ends = [a + (b - a) * (k + 1) / n for k in range(n)]
        twists = [layout._fit(align, lo, hi, w, h, None, fpi)[0]
                  for lo, hi in zip([a] + ends[:-1], ends)]
        lay_sheets(session, cfg, ends, twists)
    return answer


def _p17_naive(cfg: dict, twist: float) -> Naive:
    def answer(session: Session) -> None:
        letter_defaults(session, cfg["sheet_id"], cfg["sheet"], [cfg["name"]], twist)
    return answer


def _p4_naive(cfg: dict) -> Naive:
    def answer(session: Session) -> None:
        twist = float(layout._sheet(session, cfg["sheet"]).viewports[0].rotation_deg)
        letter_defaults(session, cfg["sheet_id"], cfg["sheet"], list(cfg["names"]), twist)
    return answer


def _p11_naive(inst: Redline, **skip) -> Naive:
    def answer(session: Session) -> None:
        redlines.make_solve(inst, **skip)(session)
    return answer


#: per instance, the naive answers it is built to catch: ``(name, answer, failed item)``,
#: where the failed item is a word of the check's detail or item the answer must fail on
NAIVE: Dict[str, List[Tuple[str, Naive, str]]] = {}
for _pid, _cfg in P17.items():
    NAIVE[_pid] = [("lettered without view_rotation", _p17_naive(_cfg, 0.0), "wrong side")]
    if abs(PUBLISHED_TWIST[_cfg["sheet_id"]]) > 1e-9:
        NAIVE[_pid].append(("lettered at the published twist",
                            _p17_naive(_cfg, PUBLISHED_TWIST[_cfg["sheet_id"]]), "wrong side"))
for _pid, _cfg in P4.items():
    NAIVE[_pid] = [("the labelers' default poses", _p4_naive(_cfg), "legibility")]
_P5_NAIVE = {"p05-dev-fdot924": ("one more",), "p05-dev-fdot924x50": ("north-up", "level"),
             "p05-dev-wfl06": ("north-up", "level", "one more"),
             "p05-dev-ppm218": ("north-up", "one more"),
             "p05-dev-wfl09": ("north-up", "one more")}
for _pid, _cfg in P5.items():
    NAIVE[_pid] = []
    for _what in _P5_NAIVE[_pid]:
        if _what == "north-up":
            NAIVE[_pid].append(("north-up sheets", _p5_north_up(_cfg), ""))
        elif _what == "level":
            NAIVE[_pid].append(("the level cut", _p5_level(_cfg), "number of sheets"))
        else:
            NAIVE[_pid].append(("one sheet too many", _p5_one_more(_pid, _cfg),
                                "number of sheets"))
for _inst in P11:
    NAIVE[_inst.id] = [
        ("the design alone", _p11_naive(_inst, letter=False, callouts=False), "do not match"),
        ("the lettering without the design", _p11_naive(_inst, design=False), "begins at"),
        ("new lettering beside the old", _p11_naive(_inst, delete_old=False), "stale")]


__all__ = ["SHEETS", "TASK_SET", "P17", "P4", "P5", "P11", "PROBES", "BY_ID", "NAIVE", "FEWEST",
           "PUBLISHED_TWIST", "sheet_of", "letter_defaults", "lay_sheets"]


# ================================================================ selftest


def selftest(pid: str, folder: Path) -> List[str]:
    """What is wrong with instance ``pid``, built under ``folder``: the scripted solution
    must pass at both levels, the untouched start fail, and every naive answer fail at
    both levels on the item it is named for. Empty when the instance is sound."""
    from roaddraft.probes import fixture, reference
    probe = BY_ID[pid]
    folder = Path(folder)
    problems = []
    ref = reference.write(probe, folder / "ref", plots=False)
    start = fixture.start_document(folder / "start", probe.start)

    def fresh(path: Path) -> Session:
        return Session.load(path, out_dir=path.parent)
    for level in ("explicit", "vague"):
        check = probe.check_at(level)
        solved = check(fresh(start), fresh(ref.document))
        if not solved.passed:
            problems.append(f"{level}: the scripted solution fails: {solved.detail[:300]}")
        if check(fresh(start), fresh(start)).passed:
            problems.append(f"{level}: the untouched start passes")
    for k, (name, answer, word) in enumerate(NAIVE[pid]):
        work = folder / f"naive{k}"
        shutil.copytree(folder / "start", work)
        mine = work / start.name
        session = fresh(mine)
        answer(session)
        common.save(session, mine)
        for level in ("explicit", "vague"):
            r = probe.check_at(level)(fresh(start), fresh(mine))
            failed = " | ".join([r.detail] + [item for item, done in r.items if not done])
            if r.passed:
                problems.append(f"{level}: naive answer {name!r} passes")
            elif word and word not in failed:
                problems.append(f"{level}: naive answer {name!r} fails, but not on {word!r}: "
                                f"{r.detail[:200]}")
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import tempfile
    ap = argparse.ArgumentParser(prog="python -m roaddraft.probes.pilot_dev")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the instances, by family and sheet")
    st = sub.add_parser("selftest", help="scripted solutions pass, naive answers fail")
    st.add_argument("ids", nargs="*")
    args = ap.parse_args(argv)
    if args.cmd == "list":
        for p in PROBES:
            print(f"{p.id:24s} {sheet_of(p.id)}")
        return 0
    bad = 0
    for pid in args.ids or list(BY_ID):
        with tempfile.TemporaryDirectory(prefix="pilot-dev-") as tmp:
            problems = selftest(pid, Path(tmp))
        bad += bool(problems)
        print(f"{pid}: {'ok' if not problems else 'FAIL'}", flush=True)
        for line in problems:
            print("   " + line)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
