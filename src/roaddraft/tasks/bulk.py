"""The bulk dial of the seeded generator (2026-11-25, Robert: "Go with 1").

A seeded sheet is one road on white paper: nothing on the sheet but what its
own task put there (0 to 4 entities), one base drawing of nine or ten
elements, attached as ``BASE``, its line ``ALIGN-1`` on sheet ``C-101``.  The
redrafted agency sheets the real sets are made of are another size of thing.
Measured on the three ``d1-real-dev`` sheets (2026-11-25): 126 to 1,122
entities on the paper, base files of 121 to 6,621 elements attached as
``AA01`` and ``BB01``, lines called ``SB10``, sheets ``L-39`` and ``IR-4``.
There ``get_sheet_state`` comes back cut at the harness's 30,000 characters,
and a list of what a sheet shows runs to hundreds of rows.  No training
recording ever met either (the largest tool answer in the 5,380 vague
conversations is 23,059 characters), and both the T1 checkpoint and the
reference drafter itself stop there: the checkpoint reads a list page after
page until the clock runs out or asks for the cut answer again, the drafter
has nothing to read the scale from (``T1.md`` section 11).

No real sheet can train (training plan, finding 3 and decision 7: every one
is held out), so ``bulked`` gives a seeded sheet a real one's size instead:

- *names as an office gives them*: the line (``SB10``, ``L2``, ``RTE-7``), the
  sheet (``L-39``, ``PP-12``), the reference its base drawing is attached as
  and that drawing's file (``AA01``, ``0412000123aa01.rdraft``), drawn from
  patterns, never from a held-out sheet;
- *survey bases* attached beside the design's, one to three files (two to four
  references on the sheet, the design's attached first or last): the topo
  (contours, the existing pavement and its stripe, driveways, ditches and
  culverts, fences, buildings, trees, spot shots), the right of way and the
  parcels behind it, the existing utilities.  A few hundred to a few thousand
  elements a file, much of it digitised a stroke at a time and most of it
  beyond the sheet's own stretch of the road, as a project's base file is;
- *a design file that is a project's*: beside the line and its pavement edges,
  the shoulders, hinge and catch lines with their slope ticks, inlets and
  drains, hatched patches, tags, and, seven times in ten, a second line (a
  frontage road beside the first or a street across it) stationed in the
  file, so ``list_alignments`` names two lines and the brief one of them;
- *the paper's own furniture*, drawn as entities the way a redrafted sheet
  carries it: general notes, a legend, schedules ruled by hand, details
  sketched in lines, revision strips in the margins.  Enough of it that the
  sheet's state does not fit the harness's result cap, which is checked.

bulk-v2 (2026-11-25, Robert: "verify that the training tasks are as realistic
as possible. additional references, topo included in plan views").  v1 kept
every base element ``CLEAR_IN`` of paper off the line; measured against the
three ``d1-real-dev`` sheets that was the largest difference left: there 4 to
1,288 topo elements and 12 to 105 of the design file's lie within half an inch
of the line on the paper, on a v1 sheet none and 6 to 14.  Legibility
(``verify.checks.check_legibility``) judges text against text and a leader or
dimension line against text, never linework, so v2 lets linework run where the
ground puts it, under and across the line, and keeps only the base files'
*text* ``CLEAR_IN`` off it; the furniture stays outside the corridor.  The
engine's default poses still land clear and what is graded is what it was:
the lesson is in the reading, not the placing (aiming at the lettering is the
crowd dial, ``tasks.crowd``).  A bulked task is kept when its starting sheet
scores 0, its reference solution 100, and its sheet's state is cut.

bulk-v3 (2026-11-25, Robert: "Yes, seeded sheets") closes the two differences v2
left.  *The border*: an agency's most times (``borders``: ``caltrans``, the border of
the three ``d1-real-dev`` sheets, on 55 seeds in 100, the Federal Lands ``wfl`` on 20),
its title block floating over the plan and every field it letters filled from patterns;
on the Caltrans border the plan moves right of the binding strip, the north arrow
stands beside the title block and the curve table keeps to the paper left of it.  A
sheet whose line would run under the title block keeps the seeded ``standard`` border.
*Base text inside the line's lettering* (``NEAR_IN``): a contour's elevation where the
surveyor lettered it, the old pavement's and the shoulder's tags, a main lettered along
itself, a cross street stationed through the crossing: 0 to 12 pieces within half an
inch of the line on a sheet (the real sheets: 1 to 14).  Where a default pose lands on
one the truth sets that label as a drafter would (``tasks.crowd.choose_poses``: the
other side of the line, then further off), which makes the task one of its own id.

Still not a real sheet's: the text near the line is where the ground puts it, not aimed
at the lettering, so a label has to be set again on about one sheet in twenty-five.

The bulk is drawn from streams of its own (``bulk-names:<seed>``,
``bulk:<seed>``), so the seed's road and layout are those of its plain task.
"""
from __future__ import annotations

import copy
import json
import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core.geometry import ViewportTransform
from roaddraft.design.horizontal import Alignment
from roaddraft.tasks.brief import Task
from roaddraft.tasks.types import BASE_LETTER_TYPES

BULK_VERSION = "bulk-v3"
#: the types the dial fits: one piece of a referenced line's lettering on a finished sheet
BULK_TYPES = BASE_LETTER_TYPES
#: paper kept clear each side of the line for its lettering (a curve point's label, the
#: longest the bulked types letter, reaches about an inch and a half off it)
CLEAR_IN = 2.0
#: how far off the line its own lettering reaches, on the paper: what an agency border's
#: title block is kept beyond
LETTERING_IN = 1.6
#: how far off the line a base file's text may stand inside its lettering (``near``)
NEAR_IN = 1.4
#: how far off the line the survey's corridor runs, on the paper; the furniture stays
#: beyond it
CORRIDOR_IN = 4.0
#: paper kept between the furniture and anything else
GAP_IN = 0.25
#: how much of a sheet's state must be furniture: past the harness's result cap
#: (``eval.episode.RESULT_CAP``) with room to spare
STATE_FLOOR = 34000
#: the entities the paper is filled toward (the real sheets measured carry 126 to 1,122)
PAPER_TARGET = (170, 620)
#: the elements of the survey base beyond the sheet's stretch of road
FAR_TARGET = (150, 1800)

#: what a survey base can carry, each part in the topo file or a file of its own
SURVEY_PARTS = ("topo", "rw", "util")
#: the layer prefixes each part draws on
_PART_LAYERS = {"topo": ("topo",), "rw": ("rw", "prcl"), "util": ("util",)}
SURVEY_LAYERS = (
    ("rw_EXIST", "magenta", "phantom", 0.35, "Existing right of way"),
    ("rw_TEXT", "magenta", "continuous", 0.18, "Right of way text"),
    ("prcl_LINE", "gray", "dashed", 0.13, "Parcel lines"),
    ("topo_EP", "gray", "dashed", 0.18, "Existing edge of pavement"),
    ("topo_STRIPE", "gray", "continuous", 0.13, "Existing striping"),
    ("topo_DRAIN", "gray", "dashed", 0.18, "Existing ditches and culverts"),
    ("topo_FENCE", "gray", "continuous", 0.18, "Existing fences"),
    ("topo_CONTOUR", "gray", "continuous", 0.13, "Existing ground contours"),
    ("topo_SPOT", "gray", "continuous", 0.13, "Spot shots"),
    ("topo_BLDG", "gray", "continuous", 0.25, "Existing buildings"),
    ("topo_VEG", "green", "continuous", 0.13, "Existing trees"),
    ("topo_TEXT", "gray", "continuous", 0.18, "Survey text"),
    ("util_EXIST", "cyan", "dashed", 0.18, "Existing utilities above ground"),
    ("util_UG", "cyan", "dashed", 0.13, "Existing utilities underground"),
    ("util_TEXT", "cyan", "continuous", 0.18, "Utility text"),
)
#: what the dial adds to the design's base drawing
DESIGN_LAYERS = (
    ("dsgn_SHLD", "black", "continuous", 0.25, "Edge of shoulder"),
    ("dsgn_SLOPE", "black", "continuous", 0.18, "Hinge and catch lines"),
    ("dsgn_SLOPE-tick", "gray", "continuous", 0.13, "Slope ticks"),
    ("dsgn_DRAIN", "blue", "continuous", 0.25, "Drainage"),
    ("dsgn_HATCH", "gray", "continuous", 0.13, "Pavement hatching"),
    ("dsgn_TEXT", "black", "continuous", 0.18, "Design text"),
    ("align_SIDE", "red", "center", 0.35, "Other alignments"),
    ("align_SIDE-anno", "red", "continuous", 0.18, "Other alignments' stationing"),
)
_DESIGN_TAGS = ("ES", "EP", "HP", "TOE", "TOP", "CATCH PT", "CONFORM", "SAWCUT", "AC DIKE",
                "OVERSIDE DRAIN", "DI", "LIMIT OF WORK", "MATCH EXIST", "DAYLIGHT")
PAPER_LAYERS = (
    ("sht_NOTES", "black", "continuous", 0.25, "General notes"),
    ("sht_LEGEND", "black", "continuous", 0.25, "Legend"),
    ("sht_SCHED", "black", "continuous", 0.25, "Schedules and quantities"),
    ("sht_SCHED-grid", "gray", "continuous", 0.13, "Schedule ruling"),
    ("sht_DETAIL", "black", "continuous", 0.18, "Details"),
    ("sht_REV", "gray", "continuous", 0.13, "Revision strips"),
    ("sht_STAMP", "gray", "continuous", 0.13, "Plot stamps"),
)

_NOTES = (
    "ALL WORK SHALL CONFORM TO THE STANDARD PLANS AND SPECIFICATIONS.",
    "CONTRACTOR SHALL VERIFY ALL EXISTING UTILITIES BEFORE EXCAVATION.",
    "EXISTING FENCE TO REMAIN UNLESS OTHERWISE NOTED.",
    "PROTECT EXISTING SURVEY MONUMENTS IN PLACE.",
    "SAWCUT EXISTING PAVEMENT TO A NEAT LINE AT CONFORMS.",
    "DIMENSIONS ARE TO EDGE OF TRAVELED WAY UNLESS OTHERWISE SHOWN.",
    "FOR ACCURATE RIGHT OF WAY DATA, CONTACT RIGHT OF WAY ENGINEERING.",
    "REMOVE AND DISPOSE OF EXISTING AC DIKE WITHIN THE LIMITS OF WORK.",
    "ADJUST EXISTING UTILITY COVERS TO FINISHED GRADE.",
    "MAINTAIN ACCESS TO ALL DRIVEWAYS DURING CONSTRUCTION.",
    "PLACE TEMPORARY FENCE (TYPE ESA) WHERE SHOWN ON THE PLANS.",
    "EXISTING DRAINAGE PATTERNS SHALL BE MAINTAINED.",
    "SEE DRAINAGE PLANS FOR CULVERT AND INLET DETAILS.",
    "SEE TYPICAL CROSS SECTIONS FOR STRUCTURAL SECTION.",
    "STATIONS AND OFFSETS ARE FROM THE CENTERLINE SHOWN.",
    "CONFORM TO EXISTING PAVEMENT AT THE BEGINNING AND END OF WORK.",
    "CLEAR AND GRUB WITHIN THE GRADING LIMITS ONLY.",
    "SEE STAGE CONSTRUCTION PLANS FOR TRAFFIC HANDLING.",
    "EXISTING SIGNS TO BE RELOCATED ARE SHOWN ON THE SIGN PLANS.",
    "SHOULDER BACKING SHALL BE PLACED AFTER PAVING IS COMPLETE.",
    "ELEVATIONS ARE BASED ON NAVD 88.",
    "BEARINGS AND COORDINATES ARE ON THE STATE PLANE GRID.",
)
_LEGEND = (
    ("EXIST RIGHT OF WAY", "phantom"), ("EXIST FENCE", "cross"), ("EXIST EDGE OF PAVEMENT", "dashed"),
    ("EXIST CONTOUR", "continuous"), ("EXIST UTILITY", "dashed"), ("EXIST TREE", "circle"),
    ("EXIST BUILDING", "box"), ("PARCEL LINE", "dashed"), ("NEW EDGE OF PAVEMENT", "continuous"),
    ("TEMPORARY FENCE", "cross"), ("LIMIT OF WORK", "phantom"), ("SAWCUT LINE", "dot"),
)
_SCHEDULES = (
    ("SUMMARY OF QUANTITIES", ("ITEM", "DESCRIPTION", "UNIT", "QTY", "REMARKS")),
    ("DRAINAGE SCHEDULE", ("No.", "STATION", "OFFSET", "TYPE", "SIZE", "LENGTH")),
    ("FENCE SCHEDULE", ("STATION", "TO STA", "SIDE", "TYPE", "LF")),
    ("SIGN SCHEDULE", ("No.", "STATION", "SIDE", "CODE", "SIZE", "POST")),
    ("PAVEMENT DELINEATION QUANTITIES", ("STATION", "TO STA", "DETAIL", "LF")),
)
_ITEMS = ("AC DIKE", "FENCE CL-6", "MINOR CONC", "HMA TYPE A", "CL 2 AB", "RSP", "18 CMP", "24 RCP",
          "MBGR", "THERMO", "TYPE D", "DI TYPE G", "OMP", "TEMP FENCE", "SAWCUT", "COLD PLANE")
_UNITS = ("LF", "SQYD", "CY", "TON", "EA", "LS", "SQFT")
_TAGS = ("EXIST FENCE", "EXIST R/W", "EXIST EP", "EXIST DWY", "EXIST CMP", "EXIST DITCH",
         "EXIST PP", "EXIST SIGN", "BARN", "SHED", "RESIDENCE", "ORCHARD", "PASTURE", "WELL")


def _r(v: float, places: int = 2) -> float:
    return round(float(v), places)


# ----------------------------------------------------------------- names


def names(seed: int, route: str = "") -> dict:
    """What an office would call the bulked task's line, sheet, references and
    files: ``{alignment, sheet, design, survey, design_file, survey_file, side, surveys,
    design_first}``.  ``surveys`` lists the survey's files, ``{name, file, parts}`` each
    (``SURVEY_PARTS``); ``side`` names the design file's second line.  Drawn from
    patterns on a stream of their own."""
    rng = random.Random(f"bulk-names:{int(seed)}")
    letters = "ABCDEFGHJKLMNPRSTW"
    form = rng.randrange(4)
    if form == 0:
        line = rng.choice(letters)
    elif form == 1:
        line = f"{rng.choice(letters)}{rng.randrange(1, 10)}"
    elif form == 2:
        line = f"{rng.choice(('NB', 'SB', 'EB', 'WB', 'TB', 'FR', 'RA', 'RP', 'CD'))}{rng.randrange(1, 21)}"
    else:
        line = rng.choice(("MAIN", f"BL-{rng.randrange(1, 10)}", f"CL-{rng.randrange(1, 10)}",
                           f"RTE-{rng.randrange(2, 400)}", f"LINE-{rng.choice(letters)}"))
    sheet = f"{rng.choice(('L', 'P', 'PP', 'IR', 'C', 'RD', 'PL', 'SC', 'X', 'DD'))}-{rng.randrange(1, 241)}"
    if rng.random() < 0.6:
        a, b = rng.sample("ABCDEFGH", 2)
        n = rng.randrange(1, 4)
        design, survey = f"{a}{a}{n:02d}", f"{b}{b}{rng.randrange(1, 4):02d}"
    else:
        design = rng.choice(("ALGN", "DSGN", "ALIGN", "CORR", "GEOM", "HA01"))
        survey = rng.choice(("SURV", "TOPO", "EXST", "SV01", "TP01"))
    tag = (route or "RTE").replace(" ", "")
    if rng.random() < 0.6:
        job = rng.randrange(10 ** 9, 10 ** 10)
        design_file, survey_file = f"{job}{design.lower()}.rdraft", f"{job}{survey.lower()}.rdraft"
    else:
        from roaddraft.document.fileformat import INTERCHANGE_EXT
        design_file = f"{tag}-{design.lower()}{INTERCHANGE_EXT}"
        survey_file = f"{tag}-{survey.lower()}{INTERCHANGE_EXT}"
    # a second line in the design file, never the first one's name
    side = line
    while side == line:
        side = rng.choice((f"{rng.choice(letters)}{rng.randrange(1, 10)}", f"FR{rng.randrange(1, 9)}",
                           f"CL{rng.randrange(1, 9)}", f"{rng.choice(letters)}{rng.choice(letters)}",
                           f"RAMP-{rng.choice(letters)}", f"EX-{rng.randrange(1, 9)}"))
    # the survey in one file, or its right of way and its utilities in files of their own
    # (two to four references on the sheet), and the design attached first or last
    pick = rng.random()
    own = [] if pick < 0.4 else ([rng.choice(("rw", "util"))] if pick < 0.75 else ["rw", "util"])
    words = {"rw": ("RW01", "RWAY", "ROW", "RWEX"), "util": ("UTIL", "UT01", "EXUT", "UTEX")}
    surveys = [{"name": survey, "file": survey_file,
                "parts": [part for part in SURVEY_PARTS if part not in own]}]
    used = {design, survey}
    for part in own:
        name = None
        while name is None or name in used:
            if len(design) == 4 and design[0] == design[1]:
                c = rng.choice("ABCDEFGHJK")
                name = f"{c}{c}{rng.randrange(1, 4):02d}"
            else:
                name = rng.choice(words[part])
        used.add(name)
        surveys.append({"name": name, "file": survey_file.replace(survey.lower(), name.lower()),
                        "parts": [part]})
    return {"alignment": line, "sheet": sheet, "design": design, "survey": survey,
            "design_file": design_file, "survey_file": survey_file, "side": side,
            "surveys": surveys, "design_first": rng.random() < 0.6}


def fits(ttype, n_sheets: int, equations: bool = False) -> Optional[str]:
    """Why the dial cannot bulk a task of this type and layout, or None."""
    if ttype.name not in BULK_TYPES:
        return (f"a {ttype.name} task is not bulked: the bulk dial fits "
                f"{', '.join(BULK_TYPES)}")
    if n_sheets != 1:
        return "a bulked task is laid out on one sheet"
    if equations:
        return "a bulked task has no station equation (its label reaches past the clear band)"
    return None


# ----------------------------------------------------------------- the border


def _border(template: str, width: float, height: float, viewport: dict) -> dict:
    """One border on a ``width`` by ``height`` sheet: ``{template, blocked,
    center_paper, north_arrow, table_area}``.  ``blocked`` is the paper its title
    block and sheet title take inside the frame (an agency border's float over the
    plan, ``render.titleblock``); the rest is None where the seeded layout stands."""
    from roaddraft.render import titleblock as tb
    out = {"template": template, "blocked": [], "center_paper": None, "north_arrow": None,
           "table_area": None}
    if template == "caltrans":
        x1, y1 = width - tb.CT_MARGIN, height - tb.CT_MARGIN
        x0 = x1 - tb.CT_TB_W
        # the title block over the top right of the plan, the sheet's title, scale and
        # number lettered in the bottom right
        out["blocked"] = [(_r(x0, 3), _r(y1 - tb.CT_TB_H, 3), _r(x1, 3), _r(y1, 3)),
                          (_r(x0, 3), tb.CT_MARGIN, _r(x1, 3), _r(tb.CT_MARGIN + 1.6, 3))]
        # the plan moves right of the binding strip and down from under the title block
        out["center_paper"] = [_r((tb.CT_BIND + x1) / 2.0),
                               _r(tb.CT_MARGIN + 0.85 + float(viewport["height_in"]) / 2.0)]
        out["north_arrow"] = [_r(x0 - 1.8), _r(y1 - 1.8)]  # beside the title block
        out["table_area"] = (tb.CT_BIND, tb.CT_MARGIN, _r(x0 - GAP_IN, 3), _r(y1, 3))
    elif template == "wfl":
        x0, y0 = tb.FLH_MARGIN_X, tb.FLH_MARGIN_Y
        x1, y1 = width - tb.FLH_MARGIN_X, height - tb.FLH_MARGIN_Y
        out["blocked"] = [(_r(x1 - tb.FLH_TB_W, 3), _r(y1 - tb.FLH_TB_H, 3), _r(x1, 3), _r(y1, 3)),
                          (_r(x1 - tb.FLH_TITLE_W - 1.6, 3), y0, _r(x1, 3), _r(y0 + tb.FLH_TITLE_H, 3))]
        out["table_area"] = (x0, _r(y0 + tb.FLH_TITLE_H + GAP_IN, 3), x1, _r(y1 - tb.FLH_TB_H - GAP_IN, 3))
    return out


def borders(seed: int, width: float, height: float, viewport: dict) -> List[dict]:
    """The borders a bulked sheet may be drawn on, the seed's own first: an agency's
    (``caltrans``, the border of the three ``d1-real-dev`` sheets, or the Federal Lands
    ``wfl``) or the seeded ``standard`` one, which is also what a sheet falls back to
    when its line runs under an agency border's title block (``border_fits``)."""
    pick = random.Random(f"bulk:{int(seed)}:border").random()
    first = "caltrans" if pick < 0.55 else ("wfl" if pick < 0.75 else "standard")
    return [_border(t, width, height, viewport)
            for t in dict.fromkeys((first, "standard"))]


def border_fits(edge: dict, viewport: dict, line: Sequence[Sequence[float]]) -> bool:
    """Whether the line, as ``viewport`` shows it, keeps its lettering's reach off the
    border's title block (and off the north arrow where the border moved it)."""
    if not edge["blocked"]:
        return True
    t = ViewportTransform(viewport["center_paper"], viewport["model_center"],
                          viewport["feet_per_inch"], viewport.get("rotation_deg", 0.0))
    keep = [(box, LETTERING_IN) for box in edge["blocked"]]
    if edge["north_arrow"]:
        x, y = edge["north_arrow"]
        keep.append(((x - 1.62, y - 1.62, x + 1.62, y + 1.62), 0.5))
    for p in line:
        x, y = t.to_paper(p)
        for box, reach in keep:
            if box[0] - reach < x < box[2] + reach and box[1] - reach < y < box[3] + reach:
                return False
    return True


_PEOPLE = ("J. ALVAREZ", "M. CHEN", "R. OKAFOR", "S. PATEL", "T. NGUYEN", "L. HARTMANN",
           "D. KOWALSKI", "A. MORALES", "K. YAMADA", "P. SULLIVAN", "E. BRANDT", "C. IBARRA")


def border_fields(seed: int, template: str, fields: dict, project: dict, sheet: str) -> dict:
    """The title block of a bulked sheet on ``template``: the seeded sheet's own
    ``fields`` on the ``standard`` border, an agency's on its own (every key the border
    letters, ``render.titleblock.template_keys``), drawn from patterns."""
    if template == "standard":
        return dict(fields)
    rng = random.Random(f"bulk:{int(seed)}:title")
    people = rng.sample(_PEOPLE, 5)
    year = rng.randrange(19, 27)
    day = lambda: f"{rng.randrange(1, 13):02d}-{rng.randrange(1, 29):02d}-{year:02d}"
    route = "".join(c for c in project.get("route", "") if c.isdigit()) or "1"
    county = project.get("county", "").split()[0][:3].upper()
    job = rng.randrange(10 ** 9, 10 ** 10)
    number, total = rng.randrange(2, 90), rng.randrange(90, 420)
    code = "".join(c for c in sheet if c.isalnum()).lower()
    if template == "caltrans":
        pm = rng.uniform(0.5, 60.0)
        out = {"dist": f"{rng.randrange(1, 13):02d}", "county": county, "route": route,
               "post_miles": f"{pm:.1f}/{pm + rng.uniform(0.4, 6.0):.1f}",
               "sheet_number": str(number), "total_sheets": str(total),
               "designed_by": people[0], "checked_by": people[1],
               "functional_supervisor": people[2], "agency": project.get("agency", ""),
               "division": "DESIGN", "border_revised": "BORDER LAST REVISED 8/1/2016",
               "username": people[3].split()[-1].lower(), "dgn_file": f"{job}{code}.dgn",
               "unit": f"{rng.randrange(1000, 4000)}", "project_number_phase": f"{job}1",
               "last_revision": "00-00-00", "date_plotted": day(),
               "time_plotted": f"{rng.randrange(7, 18):02d}:{rng.randrange(0, 60):02d}",
               "registered_civil_engineer": people[4], "re_date": day(),
               "plans_approval_date": day(),
               "disclaimer": ("THE AGENCY OR ITS OFFICERS OR AGENTS SHALL NOT BE\n"
                              "RESPONSIBLE FOR THE ACCURACY OR COMPLETENESS OF\n"
                              "SCANNED COPIES OF THIS PLAN SHEET."),
               "seal_name": people[4], "seal_number": f"No. C{rng.randrange(40000, 99999)}",
               "seal_expires": f"Exp. {rng.randrange(1, 13):02d}-{rng.choice((30, 31))}-{year + 1:02d}",
               "sheet_title": rng.choice(("LAYOUT", "LAYOUT", "PLAN", "CONSTRUCTION DETAILS")),
               "scale": fields.get("scale", ""), "sheet_id": sheet}
        for k in range(1, rng.randrange(1, 4)):  # a revision or two up the binding strip
            out[f"revised_by_{k}"] = rng.choice(people).split()[-1]
            out[f"date_revised_{k}"] = day()
        return out
    state = rng.choice(("OR", "WA", "ID", "MT", "CO", "UT", "NM", "AZ", "WY", "NV"))
    return {"state": state, "project": f"{state} FLAP {route}({rng.randrange(1, 9)})",
            "project_name": project.get("name", ""), "sheet_number": sheet,
            "sheet_title": rng.choice(("PLAN", "PLAN AND PROFILE", "ROADWAY PLAN")),
            "scale": fields.get("scale", ""), "date_plotted": day(),
            "dgn_file": f"{job}{code}.dgn", "description": project.get("name", "")}


# ----------------------------------------------------------------- the survey base


def _ok(result: dict, what: str) -> dict:
    if not result.get("ok"):
        raise AssertionError(f"bulk dial bug: {what}: {result['error']['message']}")
    return result


def _offset_run(align: Alignment, offset: float, step: float, lo: float = 0.0,
                hi: Optional[float] = None, wobble=None) -> List[List[float]]:
    """Points along ``align`` at ``offset`` (left negative), every ``step`` feet."""
    hi = align.length if hi is None else hi
    n = max(2, int(math.ceil((hi - lo) / step)) + 1)
    out = []
    for k in range(n):
        d = lo + (hi - lo) * k / (n - 1)
        off = offset + (wobble(d) if wobble else 0.0)
        pt, _direction, _i = align.station_to_xy(align.begin_station + d, off)
        out.append([_r(pt[0]), _r(pt[1])])
    return out


def _at(align: Alignment, d: float, off: float) -> List[float]:
    """The point ``d`` feet along ``align`` at ``off`` (left negative); past either end
    the end tangent is run on, as a survey runs past the limits of a job."""
    inside = min(max(d, 0.0), align.length)
    pt, direction, _i = align.station_to_xy(align.begin_station + inside, off)
    if inside != d:
        a = math.radians(direction)
        pt = (pt[0] + (d - inside) * math.cos(a), pt[1] + (d - inside) * math.sin(a))
    return [_r(pt[0]), _r(pt[1])]


class _Pen:
    """Draws one base file's content into its model, counting by part."""

    def __init__(self, doc, layers: Sequence[tuple]):
        from roaddraft.api.session import Session
        self.session = Session(_document=doc)
        self.counts: Dict[str, int] = {}
        for name, color, linetype, weight, description in layers:
            if name not in doc.layers:
                _ok(self.session.execute("create_layer", {
                    "name": name, "color": color, "linetype": linetype, "lineweight_mm": weight,
                    "description": description}), f"layer {name}")

    def add(self, part: str, command: str, **params) -> dict:
        if command != "draw_alignment":
            params = {"space": "model", **params}
        out = _ok(self.session.execute(command, params), f"{part}: {command}")
        self.counts[part] = self.counts.get(part, 0) + 1
        return out

    def run(self, part: str, pts: List[List[float]], layer: str, split: bool = False,
            closed: bool = False) -> None:
        """A run of linework: one polyline, or, ``split``, a line a segment, the way a
        digitised sheet's base carries most of its linework."""
        pts = [q for k, q in enumerate(pts) if k == 0 or q != pts[k - 1]]
        if len(pts) < 2:
            return
        if not split:
            self.add(part, "draw_polyline", vertices=pts, layer=layer, closed=closed)
            return
        for q0, q1 in zip(pts, pts[1:] + ([pts[0]] if closed else [])):
            self.add(part, "draw_line", start=q0, end=q1, layer=layer)

    def text(self, part: str, at: List[float], content: str, height: float, layer: str,
             rotation: float = 0.0) -> None:
        self.add(part, "place_text", position=at, content=content, height=height,
                 rotation_deg=_r(rotation), halign="center", valign="middle", layer=layer)


def draw_survey(doc, align: Alignment, viewport: dict, seed: int,
                parts: Sequence[str] = SURVEY_PARTS) -> dict:
    """Draw a survey base's content into ``doc`` (an empty document): the ``parts`` of
    ``SURVEY_PARTS`` this file carries.  ``topo`` is the ground under and beside the
    road (contours across it, the existing pavement along it, driveways, culverts,
    ditches, fences, buildings, trees), ``rw`` the right of way and the parcels behind
    it, ``util`` the existing utilities.  Linework runs wherever the ground puts it,
    through the line's lettering as on any plan sheet; *text* keeps ``CLEAR_IN`` of
    paper off the line.  Each part draws from a stream of its own, so a part is the
    same whichever file carries it.  Returns the counts, by part."""
    fpi = float(viewport["feet_per_inch"])
    pen = _Pen(doc, [row for row in SURVEY_LAYERS if row[0].split("_")[0] in
                     {p_ for part in parts for p_ in _PART_LAYERS[part]}])
    text_h = _r(0.08 * fpi)
    small_h = _r(0.06 * fpi)
    clear, edge = CLEAR_IN * fpi, CORRIDOR_IN * fpi
    L = align.length
    view_reach = math.hypot(viewport["width_in"], viewport["height_in"]) * fpi

    def far_frame(rng, back: bool):
        """An origin and axes for a block of far field, beyond one end of the line."""
        end, direction, _i = align.station_to_xy(align.begin_station + (0.0 if back else L), 0.0)
        a = math.radians(direction + (180.0 if back else 0.0))
        ux, uy = math.cos(a), math.sin(a)
        origin = [end[0] + ux * view_reach, end[1] + uy * view_reach]
        return lambda px, py: [_r(origin[0] + px * ux - py * uy), _r(origin[1] + px * uy + py * ux)]

    if "rw" in parts:
        rng = random.Random(f"bulk:{int(seed)}:survey:rw")
        for side in (-1.0, 1.0):
            off = side * (clear + rng.uniform(0.05, 0.35) * fpi)
            # a right of way line jogs: the take is wider at some stations than others
            jogs = sorted(rng.uniform(0.1, 0.9) * L for _ in range(rng.randrange(0, 4)))
            widths = [off + side * rng.uniform(0.0, 0.5) * fpi for _ in range(len(jogs) + 1)]
            pts = []
            for k, (lo, hi) in enumerate(zip([-0.1 * L] + jogs, jogs + [1.1 * L])):
                n = max(2, int((hi - lo) / 25.0))
                pts += [_at(align, lo + (hi - lo) * j / n, widths[k]) for j in range(n + 1)]
            pen.run("row", pts, "rw_EXIST")
            for d in _spread(rng, L, 300.0, 700.0):
                _pt, direction, _i = align.station_to_xy(align.begin_station + d, 0.0)
                pen.text("row", _at(align, d, max(widths, key=abs) + side * 0.12 * fpi), "R/W",
                         text_h, "rw_TEXT", _upright(direction))
            # property lines running back from the right of way
            for d in _spread(rng, L, 120.0, 420.0):
                skew = rng.uniform(-40.0, 40.0)
                pen.run("row", [_at(align, d, off), _at(align, d + skew, side * (edge + rng.uniform(1.0, 4.0) * fpi))],
                        "prcl_LINE")
        # the far field: parcels ruled in blocks beyond the far end of the line
        target = rng.randrange(*FAR_TARGET) // 2
        at = far_frame(rng, back=False)
        lot_w, lot_d = rng.uniform(60.0, 120.0), rng.uniform(100.0, 180.0)
        row, col, per_row = 0, 0, rng.randrange(12, 30)
        while pen.counts.get("far-rw", 0) < target:
            x0, y0 = col * lot_w, (row - 3) * (lot_d + 40.0)
            box = [at(x0, y0), at(x0 + lot_w, y0), at(x0 + lot_w, y0 + lot_d), at(x0, y0 + lot_d)]
            pen.run("far-rw", box, "prcl_LINE", split=rng.random() < 0.5, closed=True)
            if rng.random() < 0.2:
                mid = [_r((box[0][0] + box[2][0]) / 2.0), _r((box[0][1] + box[2][1]) / 2.0)]
                pen.text("far-rw", mid, f"APN {rng.randrange(10, 99):03d}-{rng.randrange(100, 999)}"
                                        f"-{rng.randrange(1, 99):02d}", text_h, "rw_TEXT")
            col += 1
            if col >= per_row:
                row, col = row + 1, 0

    if "util" in parts:
        rng = random.Random(f"bulk:{int(seed)}:survey:util")
        if rng.random() < 0.8:  # a pole line: a run, a circle at each pole
            off = rng.choice((-1.0, 1.0)) * (clear + rng.uniform(1.05, 1.15) * fpi)
            pen.run("utility", _offset_run(align, off, 50.0), "util_EXIST")
            for d in _spread(rng, L, 150.0, 300.0):
                pen.add("utility", "draw_circle", center=_at(align, d, off), radius=_r(0.03 * fpi),
                        layer="util_EXIST")
        # mains under the road: along it a few feet off the line, as they are found
        for kind in rng.sample(("W", "G", "SS", "T", "E", "FO"), rng.randrange(1, 4)):
            off = rng.uniform(-28.0, 28.0)
            lo, hi = rng.uniform(-0.1, 0.3) * L, rng.uniform(0.7, 1.1) * L
            drift = rng.uniform(-8.0, 8.0)
            n = max(3, int((hi - lo) / rng.uniform(40.0, 120.0)))
            pen.run("mains", [_at(align, lo + (hi - lo) * k / n, off + drift * k / n)
                              for k in range(n + 1)], "util_UG", split=rng.random() < 0.5)
            for d in _spread(rng, L, 250.0, 600.0):  # its tag, out where text is clear
                side = rng.choice((-1.0, 1.0))
                tag = _at(align, d, side * (clear + rng.uniform(0.5, 1.6) * fpi))
                pen.text("mains", tag, f"EXIST {rng.choice((4, 6, 8, 12, 16))}\" {kind}", small_h,
                         "util_TEXT")
                pen.add("mains", "draw_line", start=_at(align, d, off + drift * d / L), end=tag,
                        layer="util_TEXT")
            if rng.random() < 0.5:  # and lettered along itself, under the line's lettering
                d = rng.uniform(0.1, 0.9) * L
                _pt, direction, _i = align.station_to_xy(align.begin_station + d, 0.0)
                pen.text("near", _at(align, d, off + drift * d / L + 0.07 * fpi),
                         f"{rng.choice((4, 6, 8, 12, 16))}\" {kind}", small_h, "util_TEXT",
                         _upright(direction))
        for d in _spread(rng, L, 180.0, 520.0):  # services and crossings, square off the road
            reach = rng.uniform(0.6, 3.0) * fpi
            pen.run("crossings", [_at(align, d, -reach), _at(align, d + rng.uniform(-15, 15), reach)],
                    "util_UG")
            for side in (-1.0, 1.0):  # a valve or a box at each end
                if rng.random() < 0.5:
                    pen.add("crossings", "draw_circle", center=_at(align, d, side * reach),
                            radius=_r(0.025 * fpi), layer="util_EXIST")
        target = rng.randrange(*FAR_TARGET) // 4
        at = far_frame(rng, back=True)
        y = 0.0
        while pen.counts.get("far-util", 0) < target:  # the mains of the streets beyond
            y += rng.uniform(40.0, 160.0)
            n = rng.randrange(6, 30)
            xs = sorted(rng.uniform(0.0, 3000.0) for _ in range(n))
            pen.run("far-util", [at(x, y + rng.uniform(-3.0, 3.0)) for x in xs], "util_UG",
                    split=rng.random() < 0.6)
            for x in xs[::rng.randrange(2, 5)]:
                pen.add("far-util", "draw_circle", center=at(x, y), radius=_r(0.025 * fpi),
                        layer="util_EXIST")

    if "topo" in parts:
        rng = random.Random(f"bulk:{int(seed)}:survey:topo")
        # -- the existing road under the new line: its pavement edges, its stripe
        shift, half = rng.uniform(-6.0, 6.0), rng.uniform(9.0, 14.0)
        lo, hi = rng.uniform(-0.15, 0.1) * L, rng.uniform(0.9, 1.15) * L
        for side in (-1.0, 1.0):
            wave, phase = rng.uniform(200.0, 600.0), rng.uniform(0.0, 6.28)
            n = max(3, int((hi - lo) / rng.uniform(15.0, 30.0)))
            pen.run("pavement", [_at(align, lo + (hi - lo) * k / n,
                                     shift + side * half + 0.8 * math.sin((lo + (hi - lo) * k / n) / wave * 6.283 + phase))
                                 for k in range(n + 1)], "topo_EP", split=rng.random() < 0.6)
        if rng.random() < 0.8:  # the stripe, a dash at a time
            d, dash, gap = lo, rng.choice((7.0, 10.0, 12.0)), rng.choice((17.0, 30.0, 36.0))
            while d < hi:
                pen.add("pavement", "draw_line", start=_at(align, d, shift),
                        end=_at(align, d + dash, shift), layer="topo_STRIPE")
                d += dash + gap
        for d in _spread(rng, L, 500.0, 1600.0):  # what the old road is, lettered on it
            if rng.random() < 0.5:
                side = rng.choice((-1.0, 1.0))
                _pt, direction, _i = align.station_to_xy(align.begin_station + d, 0.0)
                pen.text("near", _at(align, d, shift + side * (half + 0.09 * fpi)),
                         rng.choice(("EXIST EP", "EXIST AC", "EXIST DIKE", "EXIST ES")), small_h,
                         "topo_TEXT", _upright(direction))
        # -- driveways and side roads off the pavement
        for d in _spread(rng, L, 110.0, 480.0):
            side, w = rng.choice((-1.0, 1.0)), rng.uniform(10.0, 26.0)
            back = rng.uniform(0.9, 3.4) * fpi
            skew = rng.uniform(-20.0, 20.0)
            for k in (0.0, 1.0):
                pen.run("driveways", [_at(align, d + k * w, shift + side * half),
                                      _at(align, d + k * w + skew, side * back)], "topo_EP")
        # -- ditches and their culverts
        for side in (-1.0, 1.0):
            if rng.random() < 0.3:
                continue
            off = side * rng.uniform(20.0, 40.0)
            a0, a1 = rng.uniform(-0.1, 0.4) * L, rng.uniform(0.6, 1.1) * L
            wave, phase = rng.uniform(150.0, 500.0), rng.uniform(0.0, 6.28)
            n = max(3, int((a1 - a0) / rng.uniform(15.0, 35.0)))
            pen.run("drainage", [_at(align, a0 + (a1 - a0) * k / n,
                                     off + 3.0 * math.sin((a0 + (a1 - a0) * k / n) / wave * 6.283 + phase))
                                 for k in range(n + 1)], "topo_DRAIN", split=rng.random() < 0.5)
        for d in _spread(rng, L, 350.0, 1100.0):  # a pipe under the road, a headwall each end
            reach, skew = rng.uniform(26.0, 48.0), rng.uniform(-25.0, 25.0)
            ends = [_at(align, d - skew / 2, -reach), _at(align, d + skew / 2, reach)]
            pen.run("drainage", ends, "topo_DRAIN")
            for e_, side in zip(ends, (-1.0, 1.0)):
                pen.run("drainage", [_at(align, d + side * skew / 2 - 5.0, side * reach),
                                     _at(align, d + side * skew / 2 + 5.0, side * reach)], "topo_DRAIN")
        # -- contours: the ground does not know where the road is.  Most cross it
        base_el = 10 * rng.randrange(20, 400)
        for k in range(rng.randrange(8, 26)):
            d0 = rng.uniform(-0.1, 1.1) * L
            reach = rng.uniform(1.0, 1.5) * edge
            lean = rng.uniform(-1.6, 1.6) * edge
            amp, wave, phase = rng.uniform(0.1, 0.5) * fpi, rng.uniform(1.5, 5.0), rng.uniform(0.0, 6.28)
            n = rng.randrange(14, 46)
            run = []
            for j in range(n + 1):
                t = -1.0 + 2.0 * j / n
                run.append((d0 + lean * t + amp * math.sin(t * wave + phase), t * reach))
            pen.run("contours", [_at(align, d, off) for d, off in run], "topo_CONTOUR",
                    split=rng.random() < 0.55)
            lettered = [(d, off) for d, off in run if abs(off) >= clear + 0.5 * fpi]
            if lettered and rng.random() < 0.45:
                d, off = rng.choice(lettered)
                pen.text("contours", _at(align, d, off), str(base_el + 2 * k), small_h, "topo_TEXT")
            elif rng.random() < 0.18:  # or where the surveyor lettered it: on the road
                close = [(d, off) for d, off in run if abs(off) < NEAR_IN * fpi]
                if close:
                    d, off = rng.choice(close)
                    pen.text("near", _at(align, d, off), str(base_el + 2 * k), small_h,
                             "topo_TEXT")
        for k in range(rng.randrange(2, 7)):  # and some run with it
            side = rng.choice((-1.0, 1.0))
            mean = rng.uniform(0.3, CORRIDOR_IN - 0.35) * fpi
            amp, wave, phase = rng.uniform(0.05, 0.3) * fpi, rng.uniform(250.0, 900.0), rng.uniform(0, 6.28)
            pen.run("contours", _offset_run(align, side * mean, rng.uniform(12.0, 30.0),
                                            wobble=lambda d, a=amp, w=wave, p=phase, s=side: s * a * math.sin(d / w * 6.283 + p)),
                    "topo_CONTOUR", split=rng.random() < 0.55)
        # -- spot shots: a small cross where the rod stood, anywhere on the ground
        for _ in range(rng.randrange(10, 70)):
            c = _at(align, rng.uniform(-0.05, 1.05) * L, rng.uniform(-1.0, 1.0) * edge)
            h = 0.02 * fpi
            pen.add("spots", "draw_line", start=[_r(c[0] - h), _r(c[1] - h)],
                    end=[_r(c[0] + h), _r(c[1] + h)], layer="topo_SPOT")
            pen.add("spots", "draw_line", start=[_r(c[0] - h), _r(c[1] + h)],
                    end=[_r(c[0] + h), _r(c[1] - h)], layer="topo_SPOT")
        # -- fences: along the road each side, ticked, and the odd one across it
        for side in (-1.0, 1.0):
            if rng.random() < 0.15:
                continue
            off = side * rng.uniform(0.9, 3.0) * fpi
            lo_f, hi_f = rng.uniform(0.0, 0.3) * L, rng.uniform(0.7, 1.0) * L
            pen.run("fence", _offset_run(align, off, 25.0, lo_f, hi_f), "topo_FENCE")
            tick = 0.035 * fpi
            d = lo_f + rng.uniform(5.0, 20.0)
            gap = rng.uniform(0.45, 0.8) * fpi
            while d < hi_f:
                pt, direction, _i = align.station_to_xy(align.begin_station + d, off)
                for turn in (45.0, 135.0):
                    a = math.radians(direction + turn)
                    dx, dy = tick * math.cos(a), tick * math.sin(a)
                    pen.add("fence", "draw_line", start=[_r(pt[0] - dx), _r(pt[1] - dy)],
                            end=[_r(pt[0] + dx), _r(pt[1] + dy)], layer="topo_FENCE")
                d += gap
        for _ in range(rng.randrange(0, 3)):
            d = rng.uniform(0.05, 0.95) * L
            pen.run("fence", [_at(align, d, -edge), _at(align, d + rng.uniform(-60, 60), -half - 4.0)],
                    "topo_FENCE")
        # -- buildings, trees and their tags.  Trees stand where they stand; a building
        # and any tag keep off the road
        inner, outer = clear + 1.1 * fpi, edge - 0.5 * fpi
        for _ in range(rng.randrange(2, 9)):
            d, side = rng.uniform(0.03, 0.97) * L, rng.choice((-1.0, 1.0))
            centre, direction, _i = align.station_to_xy(
                align.begin_station + d, side * rng.uniform(0.9 * fpi + 30.0, outer))
            w, h = rng.uniform(0.25, 0.6) * fpi, rng.uniform(0.2, 0.45) * fpi
            a = math.radians(direction + rng.uniform(-20.0, 20.0))
            ux, uy = math.cos(a), math.sin(a)
            corners = [[_r(centre[0] + sx * w / 2 * ux - sy * h / 2 * uy),
                        _r(centre[1] + sx * w / 2 * uy + sy * h / 2 * ux)]
                       for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            pen.run("buildings", corners, "topo_BLDG", closed=True)
            if rng.random() < 0.4:
                tag = _at(align, d, side * rng.uniform(inner, outer))
                pen.text("buildings", tag, rng.choice(_TAGS), small_h, "topo_TEXT")
        for _ in range(rng.randrange(8, 60)):
            off = rng.choice((-1.0, 1.0)) * rng.uniform(half + 6.0, outer)
            pen.add("trees", "draw_circle", center=_at(align, rng.uniform(0.0, 1.0) * L, off),
                    radius=_r(rng.uniform(0.04, 0.12) * fpi), layer="topo_VEG")
        # -- the far field: the rest of the survey, digitised a stroke at a time
        target = rng.randrange(*FAR_TARGET)
        at = far_frame(rng, back=rng.random() < 0.5)
        y = -400.0
        while pen.counts.get("far-topo", 0) < target:
            y += rng.uniform(15.0, 60.0)
            x, n = rng.uniform(0.0, 600.0), rng.randrange(8, 40)
            amp, wave, phase = rng.uniform(5.0, 40.0), rng.uniform(150.0, 700.0), rng.uniform(0, 6.28)
            pts = []
            for _k in range(n):
                pts.append(at(x, y + amp * math.sin(x / wave * 6.283 + phase)))
                x += rng.uniform(15.0, 70.0)
            pen.run("far-topo", pts, "topo_CONTOUR", split=rng.random() < 0.7)
            if rng.random() < 0.06:
                pen.text("far-topo", pts[len(pts) // 2], str(base_el + rng.randrange(-40, 40)),
                         small_h, "topo_TEXT")
    doc.meta["description"] = f"{doc.meta.get('description') or doc.name} — survey base"
    return pen.counts


def draw_design(doc, align: Alignment, viewport: dict, seed: int, half_width: float,
                side_name: str, twist: float = 0.0) -> dict:
    """Fill out the design's base drawing (the line and its pavement edges, as the
    generator drafted it) to what a project's design file carries: shoulders, hinge and
    catch lines with their slope ticks, inlets and overside drains, tags, and, most
    times, a second line (a frontage road beside the first or a street across it,
    stationed in the file as the first is on the sheet).  Its lettering keeps
    ``CLEAR_IN`` of paper off the first line.  Returns the counts, by part."""
    rng = random.Random(f"bulk:{int(seed)}:design")
    fpi = float(viewport["feet_per_inch"])
    pen = _Pen(doc, DESIGN_LAYERS)
    clear, edge = CLEAR_IN * fpi, CORRIDOR_IN * fpi
    L = align.length
    small_h = _r(0.07 * fpi)
    for side in (-1.0, 1.0):
        shoulder = half_width + rng.choice((2.0, 4.0, 5.0, 8.0, 10.0))
        pen.run("shoulders", _offset_run(align, side * shoulder, 25.0), "dsgn_SHLD")
        hinge = shoulder + rng.uniform(1.5, 4.0)
        wave, phase = rng.uniform(180.0, 700.0), rng.uniform(0.0, 6.28)
        depth = rng.uniform(6.0, 45.0)
        step = rng.uniform(8.0, 22.0)
        n = max(3, int(L / step))
        catch = lambda d, s=side, h=hinge, w=wave, p=phase, dp=depth: s * (h + dp * (0.55 + 0.45 * math.sin(d / w * 6.283 + p)))
        pen.run("slopes", _offset_run(align, side * hinge, 25.0), "dsgn_SLOPE")
        pen.run("slopes", [_at(align, L * k / n, catch(L * k / n)) for k in range(n + 1)],
                "dsgn_SLOPE", split=rng.random() < 0.5)
        for k in range(n + 1):  # slope ticks, long and short by turns
            d = L * k / n
            reach = (1.0 if k % 2 == 0 else 0.5) * (abs(catch(d)) - hinge)
            pen.add("slope ticks", "draw_line", start=_at(align, d, side * hinge),
                    end=_at(align, d, side * (hinge + reach)), layer="dsgn_SLOPE-tick")
        for d in _spread(rng, L, 200.0, 650.0):  # an inlet at the shoulder, its drain down the slope
            box = [_at(align, d - 2.0, side * shoulder), _at(align, d + 2.0, side * shoulder),
                   _at(align, d + 2.0, side * (shoulder + 3.0)), _at(align, d - 2.0, side * (shoulder + 3.0))]
            pen.run("drainage", box, "dsgn_DRAIN", closed=True)
            pen.run("drainage", [_at(align, d, side * (shoulder + 3.0)), _at(align, d, catch(d))],
                    "dsgn_DRAIN")
        for d in _spread(rng, L, 260.0, 800.0):  # what the lines are, lettered out where it is clear
            _pt, direction, _i = align.station_to_xy(align.begin_station + d, 0.0)
            pen.text("tags", _at(align, d, side * (clear + rng.uniform(0.45, 1.6) * fpi)),
                     rng.choice(_DESIGN_TAGS), small_h, "dsgn_TEXT", _upright(direction))
        for d in _spread(rng, L, 600.0, 1800.0):  # and the odd one on the line it names
            if rng.random() < 0.5:
                _pt, direction, _i = align.station_to_xy(align.begin_station + d, 0.0)
                pen.text("near", _at(align, d, side * (shoulder + 0.09 * fpi)),
                         rng.choice(("ES", "EP", "HP", "SAWCUT", "CONFORM", "AC DIKE")), small_h,
                         "dsgn_TEXT", _upright(direction))
    for _ in range(rng.randrange(0, 5)):  # a patch of pavement to be removed or conformed, hatched
        d, w = rng.uniform(0.05, 0.9) * L, rng.uniform(15.0, 60.0)
        side = rng.choice((-1.0, 1.0))
        o0, o1 = side * rng.uniform(0.0, half_width), side * (half_width + rng.uniform(4.0, 30.0))
        pen.add("hatch", "hatch", points=[_at(align, d, o0), _at(align, d + w, o0),
                                           _at(align, d + w, o1), _at(align, d, o1)],
                pattern="ANSI31", scale=_r(fpi / 4.0), layer="dsgn_HATCH")
    # -- a second line
    pick = rng.random()
    if pick < 0.7:
        begin = 100.0 * rng.randrange(8, 600) + rng.choice((0.0, 0.0, 12.5, 37.42, 68.9))
        if pick < 0.4:  # a frontage road or a ramp beside the first, as surveyed: angle points
            side = rng.choice((-1.0, 1.0))
            n = rng.randrange(2, 7)
            pis = [{"point": _at(align, L * (-0.05 + 1.1 * k / n),
                                 side * rng.uniform(2.75, 3.2) * fpi), "radius": 0.0}
                   for k in range(n + 1)]
            ranges = [None]
        else:  # a street across it
            d = rng.uniform(0.2, 0.8) * L
            lean = rng.uniform(-0.7, 0.7)
            reach = rng.uniform(1.1, 1.6) * edge
            pis = [{"point": _at(align, d - lean * reach, -reach), "radius": 0.0},
                   {"point": _at(align, d + lean * reach, reach), "radius": 0.0}]
            # stationed through the crossing, its numbers among the first line's, or
            # only out where its lettering is clear of them
            keep = (clear + 0.9 * fpi) * math.hypot(1.0, lean)
            ranges = [None] if rng.random() < 0.5 else [("low", keep), ("high", keep)]
        from roaddraft.design.horizontal import PI, compile_pis
        points = [PI.from_dict(row) for row in pis]
        doc.design.alignments[side_name] = Alignment(
            name=side_name, elements=compile_pis(points, angle_points=True), pis=points,
            begin_station=begin, description=f"\"{side_name}\" LINE", source="pis")
        pen.counts["side line"] = 1
        made = pen.add("side line", "draw_alignment", alignment=side_name, layer="align_SIDE")
        pen.counts["side line"] += len(made.get("created") or []) - 1
        total = doc.design.alignments[side_name].length
        ranges = [w if w is None else ((begin + 1.0, begin + total / 2.0 - w[1]) if w[0] == "low"
                                       else (begin + total / 2.0 + w[1], begin + total - 1.0))
                  for w in ranges]
        for window in ranges:
            if window and window[1] - window[0] < 60.0:
                continue
            params = dict(alignment=side_name, layer="align_SIDE-anno", interval=100.0,
                          tick_half_len=_r(0.05 * fpi), text_height=_r(0.1 * fpi),
                          label_offset=_r(0.15 * fpi))
            if window:
                params["station_range"] = [_r(window[0]), _r(window[1])]
            if twist:
                params["view_rotation"] = twist
            made = pen.add("side line", "annotate_stationing", **params)
            pen.counts["side line"] += len(made.get("created") or []) - 1
    return pen.counts


def _spread(rng: random.Random, length: float, lo: float, hi: float) -> List[float]:
    """Distances along a line, a draw between ``lo`` and ``hi`` apart."""
    out, d = [], rng.uniform(0.2, 0.8) * lo
    while d < length:
        out.append(d)
        d += rng.uniform(lo, hi)
    return out


def _upright(direction: float) -> float:
    """A text rotation along ``direction`` that does not read upside down in the model."""
    a = (direction + 180.0) % 360.0 - 180.0
    return a + 180.0 if a < -90.0 else (a - 180.0 if a > 90.0 else a)


# ----------------------------------------------------------------- the paper's furniture


class _Paper:
    """The free paper of one sheet, on a grid: inside the usable area, off what the
    sheet already carries, and beyond the survey's corridor where the viewport shows
    the model."""
    CELL = 0.125

    def __init__(self, usable: Sequence[float], frame: Sequence[float], view: ViewportTransform,
                 line: Sequence[Sequence[float]], fpi: float, taken: Sequence[Sequence[float]]):
        self.x0, self.y0 = usable[0] + 0.1, usable[1] + 0.1
        self.nx = int((usable[2] - 0.1 - self.x0) / self.CELL)
        self.ny = int((usable[3] - 0.1 - self.y0) / self.CELL)
        reach = (CORRIDOR_IN + GAP_IN)
        on_paper = [view.to_paper(p) for p in line]
        self.free = [[True] * self.nx for _ in range(self.ny)]
        for j in range(self.ny):
            y = self.y0 + (j + 0.5) * self.CELL
            for i in range(self.nx):
                x = self.x0 + (i + 0.5) * self.CELL
                if frame[0] - GAP_IN <= x <= frame[2] + GAP_IN and frame[1] - GAP_IN <= y <= frame[3] + GAP_IN:
                    if any((x - px) ** 2 + (y - py) ** 2 < reach * reach for px, py in on_paper):
                        self.free[j][i] = False
        for box in taken:
            self.take(box, GAP_IN)

    def _cells(self, box: Sequence[float], pad: float):
        i0 = max(0, int(math.floor((box[0] - pad - self.x0) / self.CELL)))
        i1 = min(self.nx, int(math.ceil((box[2] + pad - self.x0) / self.CELL)))
        j0 = max(0, int(math.floor((box[1] - pad - self.y0) / self.CELL)))
        j1 = min(self.ny, int(math.ceil((box[3] + pad - self.y0) / self.CELL)))
        return i0, i1, j0, j1

    def take(self, box: Sequence[float], pad: float = 0.0) -> None:
        i0, i1, j0, j1 = self._cells(box, pad)
        for j in range(j0, j1):
            for i in range(i0, i1):
                self.free[j][i] = False

    def clear(self, box: Sequence[float]) -> bool:
        if box[0] < self.x0 or box[1] < self.y0:
            return False
        if box[2] > self.x0 + self.nx * self.CELL or box[3] > self.y0 + self.ny * self.CELL:
            return False
        i0, i1, j0, j1 = self._cells(box, GAP_IN)
        return all(self.free[j][i] for j in range(j0, j1) for i in range(i0, i1))

    def place(self, rng: random.Random, w: float, h: float) -> Optional[Tuple[float, float]]:
        """A lower-left corner for a ``w`` by ``h`` block on free paper, or None: the
        free places are scanned from a corner of the sheet drawn for the block."""
        step = 2  # a quarter inch
        xs = list(range(0, self.nx, step))
        ys = list(range(0, self.ny, step))
        if rng.random() < 0.5:
            xs.reverse()
        if rng.random() < 0.5:
            ys.reverse()
        for j in ys:
            y = self.y0 + j * self.CELL
            for i in xs:
                x = self.x0 + i * self.CELL
                if self.clear((x, y, x + w, y + h)):
                    return _r(x, 3), _r(y, 3)
        return None

    def tallest(self, x: float, w: float) -> Optional[Tuple[float, float]]:
        """The longest free run up a ``w``-wide column at ``x``: ``(y, height)``."""
        best, y, top = None, self.y0, self.y0 + self.ny * self.CELL
        while y < top:
            h = 0.0
            while y + h + 0.25 <= top and self.clear((x, y, x + w, y + h + 0.25)):
                h += 0.25
            if h and (best is None or h > best[1]):
                best = (_r(y, 3), _r(h, 3))
            y += max(h, 0.25)
        return best


def _notes(rng, x, y, w, h, header: str) -> List[tuple]:
    n = int((h - 0.45) / 0.22)
    out = [("place_text", dict(position=[x, _r(y + h - 0.12, 3)], content=header, height=0.14,
                               layer="sht_NOTES")),
           ("draw_line", dict(start=[x, _r(y + h - 0.2, 3)], end=[_r(x + 1.6, 3), _r(y + h - 0.2, 3)],
                              layer="sht_NOTES"))]
    picks = rng.sample(_NOTES, min(n, len(_NOTES)))
    for k, note in enumerate(picks):
        words = f"{k + 1}. {note}"
        limit = int(w / 0.068)
        out.append(("place_text", dict(position=[x, _r(y + h - 0.45 - 0.22 * k, 3)],
                                       content=words[:limit], height=0.09, layer="sht_NOTES")))
    return out


def _legend(rng, x, y, w, h) -> List[tuple]:
    rows = int((h - 0.5) / 0.3)
    out = [("draw_polyline", dict(vertices=[[x, y], [_r(x + w, 3), y], [_r(x + w, 3), _r(y + h, 3)],
                                            [x, _r(y + h, 3)]], closed=True, layer="sht_LEGEND")),
           ("place_text", dict(position=[_r(x + w / 2, 3), _r(y + h - 0.22, 3)], content="LEGEND",
                               height=0.14, halign="center", valign="middle", layer="sht_LEGEND"))]
    for k, (label, kind) in enumerate(rng.sample(_LEGEND, min(rows, len(_LEGEND)))):
        yy = _r(y + h - 0.55 - 0.3 * k, 3)
        a, b = _r(x + 0.15, 3), _r(x + 1.05, 3)
        if kind == "circle":
            out.append(("draw_circle", dict(center=[_r((a + b) / 2, 3), yy], radius=0.07,
                                            layer="sht_LEGEND")))
        elif kind == "box":
            out.append(("draw_polyline", dict(vertices=[[a, _r(yy - 0.07, 3)], [b, _r(yy - 0.07, 3)],
                                                        [b, _r(yy + 0.07, 3)], [a, _r(yy + 0.07, 3)]],
                                              closed=True, layer="sht_LEGEND")))
        else:
            params = dict(start=[a, yy], end=[b, yy], layer="sht_LEGEND")
            if kind != "cross":
                params["linetype"] = kind
            out.append(("draw_line", params))
            if kind == "cross":
                for cx in (_r(a + 0.25, 3), _r(a + 0.65, 3)):
                    out.append(("draw_line", dict(start=[_r(cx - 0.04, 3), _r(yy - 0.04, 3)],
                                                  end=[_r(cx + 0.04, 3), _r(yy + 0.04, 3)],
                                                  layer="sht_LEGEND")))
                    out.append(("draw_line", dict(start=[_r(cx - 0.04, 3), _r(yy + 0.04, 3)],
                                                  end=[_r(cx + 0.04, 3), _r(yy - 0.04, 3)],
                                                  layer="sht_LEGEND")))
        out.append(("place_text", dict(position=[_r(x + 1.2, 3), yy], content=label, height=0.08,
                                       valign="middle", layer="sht_LEGEND")))
    return out


def _schedule(rng, x, y, w, h, begin: float, length: float, st, which: tuple) -> List[tuple]:
    title, columns = which
    rows = int((h - 0.35) / 0.22) - 1
    cw = w / len(columns)
    top = _r(y + h - 0.35, 3)
    out = [("place_text", dict(position=[_r(x + w / 2, 3), _r(y + h - 0.15, 3)], content=title,
                               height=0.12, halign="center", valign="middle", layer="sht_SCHED"))]
    for r in range(rows + 2):
        yy = _r(top - 0.22 * r, 3)
        out.append(("draw_line", dict(start=[x, yy], end=[_r(x + w, 3), yy], layer="sht_SCHED-grid")))
    bottom = _r(top - 0.22 * (rows + 1), 3)
    for c in range(len(columns) + 1):
        xx = _r(x + cw * c, 3)
        out.append(("draw_line", dict(start=[xx, top], end=[xx, bottom], layer="sht_SCHED-grid")))

    def cell(column: str, r: int) -> str:
        if column in ("STATION", "TO STA"):
            return st.format(begin + rng.uniform(0.0, length))
        if column == "No.":
            return str(r + 1)
        if column in ("ITEM", "CODE"):
            return f"{rng.randrange(10, 99)}{rng.randrange(1000, 9999)}"
        if column in ("DESCRIPTION", "TYPE", "DETAIL"):
            return rng.choice(_ITEMS)
        if column == "UNIT":
            return rng.choice(_UNITS)
        if column == "SIDE":
            return rng.choice(("LT", "RT"))
        if column == "OFFSET":
            return f"{rng.uniform(12.0, 60.0):.1f} {rng.choice(('LT', 'RT'))}"
        if column == "SIZE":
            return rng.choice(('18"', '24"', '30"', '36"', "24x24", "30x30", "36x36"))
        if column == "REMARKS":
            return rng.choice(("", "", "SEE NOTE 2", "(N)", "(F)"))
        return str(rng.randrange(5, 4800))

    for c, column in enumerate(columns):
        cx = _r(x + cw * (c + 0.5), 3)
        out.append(("place_text", dict(position=[cx, _r(top - 0.11, 3)], content=column,
                                       height=0.07, halign="center", valign="middle",
                                       layer="sht_SCHED")))
        for r in range(rows):
            words = cell(column, r)
            if not words:
                continue
            out.append(("place_text", dict(position=[cx, _r(top - 0.22 * (r + 1) - 0.11, 3)],
                                           content=words[:int(cw / 0.06)], height=0.07,
                                           halign="center", valign="middle", layer="sht_SCHED")))
    return out


def _strip(rng, x, y, w, h) -> List[tuple]:
    """A revision strip up a margin: ruled rows, a mark and a date in each."""
    rows = int(h / 0.3)
    out = [("draw_polyline", dict(vertices=[[x, y], [_r(x + w, 3), y], [_r(x + w, 3), _r(y + h, 3)],
                                            [x, _r(y + h, 3)]], closed=True, layer="sht_REV"))]
    mid = _r(x + w * 0.38, 3)
    out.append(("draw_line", dict(start=[mid, y], end=[mid, _r(y + h, 3)], layer="sht_REV")))
    for r in range(rows):
        yy = _r(y + 0.3 * r, 3)
        if r:
            out.append(("draw_line", dict(start=[x, yy], end=[_r(x + w, 3), yy], layer="sht_REV")))
        if rng.random() < 0.8:
            out.append(("place_text", dict(position=[_r(x + w * 0.19, 3), _r(yy + 0.15, 3)],
                                           content=str(rng.randrange(1, 9)), height=0.06,
                                           halign="center", valign="middle", layer="sht_REV")))
            out.append(("place_text", dict(
                position=[_r(x + w * 0.69, 3), _r(yy + 0.15, 3)],
                content=f"{rng.randrange(1, 13)}/{rng.randrange(1, 29)}/{rng.randrange(19, 27):02d}",
                height=0.06, halign="center", valign="middle", layer="sht_REV")))
    return out


def _detail(rng, x, y, w, h, title: str) -> List[tuple]:
    """A detail drawn on the sheet, as a redrafted sheet carries one: a typical section
    sketched in lines, its layers, its slopes, its dimension lines and a few words."""
    L = "sht_DETAIL"
    out = [("draw_polyline", dict(vertices=[[x, y], [_r(x + w, 3), y], [_r(x + w, 3), _r(y + h, 3)],
                                            [x, _r(y + h, 3)]], closed=True, layer=L)),
           ("place_text", dict(position=[_r(x + w / 2, 3), _r(y + 0.2, 3)], content=title,
                               height=0.12, halign="center", valign="middle", layer=L)),
           ("place_text", dict(position=[_r(x + w / 2, 3), _r(y + 0.42, 3)], content="NO SCALE",
                               height=0.07, halign="center", valign="middle", layer=L))]

    def line(x0, y0, x1, y1):
        out.append(("draw_line", dict(start=[_r(x0, 3), _r(y0, 3)], end=[_r(x1, 3), _r(y1, 3)],
                                      layer=L)))

    cx, top = x + w / 2, y + h - 0.75
    half = w * rng.uniform(0.22, 0.3)
    fall = rng.uniform(0.04, 0.09)
    lanes = rng.choice((1, 2))
    for side in (-1.0, 1.0):
        ex, ey = cx + side * half, top - fall
        for k in range(rng.randrange(2, 5)):  # the structural section, a line a layer
            dy = 0.07 * k
            line(cx, top - dy, ex, ey - dy)
        line(ex, ey, ex, ey - 0.07 * 4)
        sx = ex + side * w * rng.uniform(0.05, 0.09)  # shoulder, then the slope to the ground
        line(ex, ey, sx, ey - 0.02)
        gx, gy = min(max(sx + side * w * rng.uniform(0.06, 0.12), x + 0.1), x + w - 0.1), ey - rng.uniform(0.25, 0.5)
        line(sx, ey - 0.02, gx, gy)
        line(gx, gy, min(max(gx + side * 0.25, x + 0.05), x + w - 0.05), gy)
        for k in range(1, lanes + 1):  # lane lines, ticked on the dimension line above
            lx = cx + side * half * k / lanes
            line(lx, top + 0.22, lx, top + 0.38)
            out.append(("place_text", dict(position=[_r(cx + side * half * (k - 0.5) / lanes, 3),
                                                     _r(top + 0.4, 3)],
                                           content=f"{rng.choice((11, 12))}' LANE", height=0.06,
                                           halign="center", valign="middle", layer=L)))
        out.append(("place_text", dict(position=[_r((ex + sx) / 2, 3), _r(top + 0.14, 3)],
                                       content=rng.choice(("SHLD", "4' SHLD", "8' SHLD", "VAR")),
                                       height=0.05, halign="center", valign="middle", layer=L)))
    line(cx - half, top + 0.3, cx + half, top + 0.3)
    line(cx, top - 0.35, cx, top + 0.45)  # the centerline
    for k in range(rng.randrange(4, 14)):  # ground, hatched in short strokes below the section
        gx = x + 0.2 + (w - 0.5) * k / 14.0
        line(gx, top - 0.85, gx + 0.12, top - 0.73)
    return out


def furnished(task: Task, seed: int) -> Task:
    """``task`` with the paper's furniture on its starting sheet, the truth told
    what was handed over, and the three things a bulked task must be checked:
    the start scores 0, the reference 100, and the sheet's state is cut.
    Raises ``ValueError`` when the seed's sheet cannot carry it."""
    from roaddraft.api.session import Session
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify import verify
    rng = random.Random(f"bulk:{int(seed)}:paper")
    D = task.brief.deliverable
    sh = D["sheets"][0]
    name = sh["name"]
    align = Alignment.from_dict(task.brief.design["alignments"][task.brief.alignment_name])
    session = session_for_task(task)
    sheet = session.doc.sheet_by_ref(name)
    vp = sheet.viewports[0]
    fpi = float(vp.feet_per_inch)
    for layer, color, linetype, weight, description in PAPER_LAYERS:
        _ok(session.execute("create_layer", {"name": layer, "color": color, "linetype": linetype,
                                             "lineweight_mm": weight,
                                             "description": description}), f"layer {layer}")
    line = [align.point_at(align.length * k / 400.0) for k in range(401)]
    taken = [e.bbox(session.doc) for e in sheet.entities.values()]
    # an agency border's title block floats over the plan: the furniture keeps off it
    taken += _border(sheet.title_block_template, sheet.width_in, sheet.height_in,
                     {"height_in": vp.height_in})["blocked"]
    paper = _Paper(sheet.usable_area(), vp.paper_bbox(), vp.transform(), line, fpi, taken)
    st = align.stations()
    made: List[str] = []
    blocks: List[dict] = []

    def put(kind: str, x: float, y: float, w: float, h: float, entities: List[tuple]) -> None:
        for command, params in entities:
            made.extend(_ok(session.execute(command, {"space": name, **params}),
                            f"{kind}: {command}")["created"])
        paper.take((x, y, x + w, y + h), GAP_IN)
        blocks.append({"kind": kind, "box": [x, y, _r(x + w, 3), _r(y + h, 3)]})

    target = rng.randrange(*PAPER_TARGET)
    # -- the margins first: a revision strip up each free one
    ua = sheet.usable_area()
    frame = vp.paper_bbox()
    for x0, x1 in ((ua[0] + 0.1, frame[0] - GAP_IN), (frame[2] + GAP_IN, ua[2] - 0.1)):
        w = _r(min(0.9, x1 - x0), 3)
        if w < 0.6 or rng.random() < 0.25:
            continue
        run = paper.tallest(_r(x0, 3), w)
        if run and run[1] >= 3.0:
            h = _r(min(run[1], rng.uniform(4.0, 18.0)), 3)
            h = _r(math.floor(h / 0.3) * 0.3, 3)
            put("strip", _r(x0, 3), run[0], w, h, _strip(rng, _r(x0, 3), run[0], w, h))
    # -- then blocks on the free paper, until the sheet is as full as it was drawn to be
    kinds = ["notes", "schedule", "legend", "schedule", "notes", "schedule", "schedule",
             "detail", "detail"]
    rng.shuffle(kinds)
    details = rng.sample(("TYPICAL SECTION", "DETAIL A", "SECTION A-A", "DIKE DETAIL"), 2)
    headers = rng.sample(("NOTES:", "GENERAL NOTES:", "CONSTRUCTION NOTES:"), 3)
    schedules = rng.sample(_SCHEDULES, len(_SCHEDULES))
    for kind in kinds:
        if len(made) >= target:
            break
        for _try in range(4):  # a block that does not fit is tried smaller
            if kind == "notes":
                w, h = _r(rng.uniform(4.5, 6.5), 2), _r(0.45 + 0.22 * rng.randrange(5, 17), 2)
            elif kind == "legend":
                w, h = 3.6, _r(0.5 + 0.3 * rng.randrange(5, 11), 2)
            elif kind == "detail":
                w, h = _r(rng.uniform(4.0, 6.0), 2), _r(rng.uniform(2.2, 3.0), 2)
            else:
                w = _r(rng.uniform(4.5, 7.5), 2)
                h = _r(0.35 + 0.22 * (rng.randrange(5, 19) + 1) + 0.01, 2)
            spot = paper.place(rng, w, h)
            if spot is None:
                continue
            x, y = spot
            if kind == "notes":
                entities = _notes(rng, x, y, w, h, headers.pop())
            elif kind == "legend":
                entities = _legend(rng, x, y, w, h)
            elif kind == "detail":
                entities = _detail(rng, x, y, w, h, details.pop())
            else:
                entities = _schedule(rng, x, y, w, h, align.begin_station, align.length, st,
                                     schedules.pop())
            put(kind, x, y, w, h, entities)
            break
    size = len(json.dumps(session.query("get_sheet_state", {"sheet": name}), ensure_ascii=False))
    if size < STATE_FLOOR:
        raise ValueError(f"seed {seed}: its sheet has room for {len(made)} entities of furniture, "
                         f"a state of {size:,} characters, under the {STATE_FLOOR:,} a bulked "
                         "sheet carries")
    truth = copy.deepcopy(task.truth)
    given = sorted(set(session.doc.model_entities) | set(sheet.entities))
    for tsh in truth.sheets:  # legibility judges new work against what was handed over
        tsh["given_entities"] = given
    out = Task(brief=task.brief, truth=truth, baseline=session.doc.to_dict(),
               files=copy.deepcopy(task.files))
    # the base files' text stands inside the line's lettering here and there (``near``):
    # where a default pose lands on it the truth sets that label as a drafter would, on
    # the other side of the line or further off (``tasks.crowd.choose_poses``)
    from roaddraft.tasks.crowd import choose_poses
    poses = choose_poses(out)
    if poses:
        out = _posed(out, poses, given)
    start = session_for_task(out)
    score = verify(start.doc, out.truth).effective_score
    if abs(score) > 1e-9:
        raise ValueError(f"seed {seed}: the bulked sheet starts at {score}, not 0")
    reference_solution(out, start)
    score = verify(start.doc, out.truth).effective_score
    if abs(score - 100.0) > 1e-9:
        raise ValueError(f"seed {seed}: the reference scores {score} on the bulked sheet, not 100")
    return out


def _posed(task: Task, poses: dict, given: Sequence[str]) -> Task:
    """``task`` with ``poses`` in its deliverable: a task of its own (the id is the
    payload's), its truth drawn again and every file told the new id."""
    import dataclasses
    from roaddraft.tasks.brief import compute_task_id
    from roaddraft.tasks.ground_truth import compute_ground_truth
    from roaddraft.tasks.prompts import render_prompts
    b0 = task.brief
    D = copy.deepcopy(b0.deliverable)
    D["label_poses"] = copy.deepcopy(poses)
    payload = {"generator_version": b0.generator_version, "spec_hash": b0.spec_hash,
               "project": b0.project, "design": b0.design, "deliverable": D}
    brief = dataclasses.replace(b0, task_id=compute_task_id(b0.seed, b0.level, payload),
                                deliverable=D, instructions="", prompts={})
    brief.prompts = render_prompts(brief)
    brief.instructions = brief.prompts["explicit"] + b0.instructions[len(b0.prompts["explicit"]):]
    truth = compute_ground_truth(brief)
    for tsh in truth.sheets:
        tsh["given_entities"] = list(given)
    baseline = copy.deepcopy(task.baseline)
    files = copy.deepcopy(task.files)
    for content in [baseline] + list(files.values()):
        if "task_id" in (content.get("meta") or {}):
            content["meta"]["task_id"] = brief.task_id
    return Task(brief=brief, truth=truth, baseline=baseline, files=files)


def describe(task: Task) -> dict:
    """The size of a bulked task's starting drawing: what the dial put there."""
    from roaddraft.tasks.reference import session_for_task
    session = session_for_task(task)
    D = task.brief.deliverable
    name = D["sheets"][0]["name"]
    sheet = session.doc.sheet_by_ref(name)
    files = {fname: len((content.get("model") or {}).get("entities") or {})
             for fname, content in task.files.items()}
    return {"sheet": name, "alignment": task.brief.alignment_name,
            "paper_entities": len(sheet.entities),
            "state_chars": len(json.dumps(session.query("get_sheet_state", {"sheet": name}),
                                          ensure_ascii=False)),
            "files": files, "layers": len(session.doc.layers)}


__all__ = ["BULK_VERSION", "BULK_TYPES", "CLEAR_IN", "CORRIDOR_IN", "NEAR_IN", "LETTERING_IN",
           "STATE_FLOOR", "names", "fits", "borders", "border_fits", "border_fields",
           "draw_survey", "draw_design", "furnished", "describe"]
