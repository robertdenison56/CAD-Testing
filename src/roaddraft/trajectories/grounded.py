"""Grounded reference solutions: the reference drafter, working as a model must.

``tasks.reference`` drafts a task from the generator's truth.  Its commands
are right, and they carry values no tool ever returned: a size already
multiplied out for a scale nobody read, a count of tangents nobody asked
for.  Replayed as a conversation (``OracleAgent``) that is two calls and no
question, and a model trained on it learns to write numbers from nowhere.

``GroundedAgent`` drafts the same tasks the way a model has to: it is given
the task text and the work the request calls for (the phases of
``TaskType.solution_phases``, which is what reading the request means), and
everything else it reads through the tool surface before it uses it -- the
sheets, the layers and their descriptions, the scale a sheet shows the model
at, the tangents and curves of the alignment.  It runs through the ordinary
episode loop, so what it leaves is an ordinary episode file, scored by the
verifier like any model's.

Where the engine has a convention it takes the engine's route instead of
doing arithmetic: the annotation scale is set to the sheet's scale and the
labelers size their own lettering, so no command carries a height or an
offset worked out by hand.

``audit`` is the check that makes a recording training data.  It reads a
finished episode the way the model saw it and reports every value in a tool
call that was not *grounded* when the call was made:

- in the task text, or
- in the result of an earlier call, or
- in the called tool's own definition (an enum value, a word of its
  description), or
- a drafting standard of spec v1 (``STANDARDS``: the layer properties, the
  north arrow's place; what the vague prompt leaves to the drafter and what
  training is meant to teach), or
- written another way of one of those: a station as feet (``73+00.00`` is
  7300), a distance to the left as a negative offset, a design point named
  by its index (``T-2``, ``MC-1``), a scale as a title block letters it
  (``1" = 40'`` for a viewport at 40 ft to the inch), a point by station and
  offset (``150+00.00@100L``), a match line's label in the office's form
  (``MATCH LINE STA 150+00.00 SEE SHEET C-102``, its station and sheet ones
  seen), a sheet numbered on from the one a task names where it leaves the
  layout open (``C-102`` after ``numbered from C-101``, the number counted in
  the shown work), a part of a longer string (the agency out of the project's
  description), or
- worked out from grounded numbers in the turn's own line of shown work
  (``21.5 - 0.25 = 21.25``; the audit redoes the sum), or
- a size a tool's own definition gives as a ratio of the text height
  (``place_dimension``'s arrowheads, ``1.2 x the text height``), or
- the drafter's own to choose (``CHOICES``: the quarter inch it leaves
  between its work and a border, the inch and a quarter it keeps clear round
  a label's point inside a viewport, the inch and a half it allows the
  lettering round the line when it picks a scale, the two inches a match
  line reaches each side, the 25 rows it reads at a time when it wants each
  text whole, the two, four, three and six text heights further off its
  line it tries a label that will not clear, the sixty feet it keeps a match
  line from a curve point where the breaks are left to it).

A recording is kept when the verifier scores it 100 and the audit finds
nothing.  The audit knows nothing of the agent, so it reads a model's
rollout the same way.

On a sheet whose viewport is turned (the generator's twist dial, 2026-11-11)
the drafter reads the turn off the viewport and hands it to each labeler as
``view_rotation``, so the model lettering reads upright as plotted, and turns
the north arrow the same way.  The curve table's corner is checked another
way there: the model's extents are no box on a turned sheet's paper, so the
table goes down, its box (and a quarter inch round it) is taken back to the
model, and that stretch of the model is searched for anything the sheet
shows.  ``twist_ignored`` is the keep rule's third leg: lettering added on a
twisted sheet without the twist, which the verifier lets through wherever it
happens not to plot upside down.

The sheets themselves (the sheet and viewport phase, 2026-11-11, Robert:
"Yes, start it") are laid out through the engine, never by working a viewport
out by hand.  Each sheet gets the office's plan viewport, set down on the
point midway between the ends of its stretch of the line; the engine is asked
where the stretch falls on the paper and then which model point shows at its
middle, and the view is centred there (``_lay_out``).  A scale the task leaves
open is the one the model's lettering was made for, or the largest of the
office's plan scales that leaves room for lettering still to come.  The model
is lettered after that, for the scale and twist the viewport shows.  On a
layout of several sheets each frame is then trimmed round its own stretch from
the points the engine reports the lettering at, so no label is cut by a
frame's edge, and the match lines are drawn and lettered and the labels read
back (``_trim_and_match``).

On a sheet that showed other lettering before the drafter's (the generator's
crowd dial, ``tasks.crowd``, 2026-11-12, Robert: "Clearing step": another
line's, or notes on the paper) the new lettering is read back and whatever
sits on any of it is set again (``_clear``).  The engine sets one line's
lettering clear of itself and of nothing else, and it reports a text by its
box on the model's axes and no other way, so the drafter compares in steps:
the boxes as they stand (two that do not meet settle it); then, since a box
round lettering at an angle is mostly empty, along and across a line -- a
line's label lies from its offset to its offset plus its height off its line,
by its record, and the other thing's corners are put in the same terms by
``xy_to_station``.  Where that finds the two meeting only by a loose measure
(a label along or square to a tangent bounded by its box, or the other's
corners those of its box), the labels are measured by their true sizes first:
the length from the box, the height and the tangent's run, and the other's
true corners worked out along its own tangent (2026-11-12, the crowded
bearings); what is left is taken to meet.  A label that meets
something is deleted and placed again by the same labeler on the other side
of its line, then further off, read back and compared again.  Of two lines in
one design the one drafted is the one the request names.  A line alone on its
sheet is not read back: its recordings are what they were before the step.

On a finished sheet whose line has a design change to pick up (the
generator's revision dial, ``tasks.revise``: a radius, a PI, a restation) the
drafter works where the design lives.  In a base drawing the designer has made
the change: the drafter takes off what was lettered from the old design, found
by its anchor, restations each note on the paper that cites the line (by the
stated shift on a restation, and from the old tick at the whole station before
the note, taken to the revised line, on a change of the geometry), and letters
the line again by the phases above (``_revise``).  In this file the change is
the drafter's (Robert, 2026-11-12: "Yes, revision only"): ``modify_alignment``
makes it and brings the labels along, ``update_labels`` checks them, and each
note is restationed from its own point before and after (``_revise_own``).  The
keep rule's fourth leg is ``tasks.revise.left_stale``: nothing lettered from the
old design left, every note restationed.

Where the task leaves the change to the drafter in the base drawing itself
(``tasks.revise.BASE_KINDS``, 2026-11-13; the tool list then has
``open_document`` and ``reload_references``), the drafter goes where the design
lives (``_revise_base``): while the line is still the old one it reads where
each note's station lies, and the base drawing's file from the reference;
opens the base drawing; changes the line there with its centerline redrawn,
and redraws the pavement edges it finds drawn from it, at their own offsets on
their own level; goes back to the file it was handed; reloads the reference;
and then, as where the designer made the change, takes off what was lettered
from the old design and letters the line again, each note restationed from
where its own point now falls.  It does not hand the old lettering to
``update_labels``: through a reference that re-poses each label from its own
record, and over ``d1-train-revise-base`` it left 49 of 300 sheets short (a
restationed set stopped short of the new stations on 35, labels turned upside
down on 14).

The pavement width is dimensioned square across each tangent (the width
phase, 2026-11-12, the last phase of the seeded types; ``_widths``), between
the two pavement edges at one station: ``place_dimension`` takes each edge and
the same fraction along it, so the engine finds the points, and the
annotation scale sizes the text.  At plan scale the text does not fit between
the edges and goes out past the second point, so the edge on the side the
curve points are not lettered goes second.  Where a dimension may stand is
judged in the line's terms from each label's record: a label along a tangent
by its true length, worked out from its box, its height and the tangent's run
(``(76.549 * 273.594 - 5 * 0.426) / 273.594``), never its box; the dimension
line must miss every label's stretch, the text every stretch of a label that
reaches past the edge on its side.  A station the task states is kept and the
line moved off what it would cross; one left to the drafter is the half
station nearest the tangent's middle that clears, the office's standard, else
the nearest place just past what is in the way, where a station past an
equation is worked out from the equation's own numbers.  On sheets handed over
each dimension is read back as the sheets show it, its number with the corners
of its lettering on the paper (``paper_corners``, as a text's), and those are
compared with each view's frame; a dimension a frame would cut is set again.
On sheets the drafter lays out, each frame is trimmed round the dimensions'
numbers with the lettering.  Through a turned view a dimension takes the
viewport's twist as its ``view_rotation``, as the lettering does (plan
decision 9, 2026-11-13), so its number reads upright on the sheet.

A task can leave the layout itself to the drafter (``tasks.breaks``, the
training-only type ``plan-sheet-breaks``, 2026-11-13, plan section 6 decision
8): it gives the line, the scale and the first sheet's number, and not how many
sheets there are or where they break.  The drafter then decides both before it
lays anything out (``_choose_breaks``): it makes the first sheet, asks where the
line's points fall on its paper, fills each sheet as far as the office's plan
window holds the line with a quarter inch all round, ends a sheet only at a
whole station on a tangent sixty feet from its ends, and with the count known
moves the breaks to the sound whole stations nearest the even splits when
every stretch still fits.  The sheets are then laid out, lettered, trimmed and
matched as any are.

A title block the task does not spell out is filled from the document: the
project and the agency from its name and description, and any field the
document's own record carries under the field's name -- who designed, drew
and checked the sheet, and its date, which every seeded document has held
since 2026-11-11 (``tasks.generator.DOCUMENT_PEOPLE``).  A field nothing
gives is left blank and said so in the note, never made up; the verifier
wants every field filled (D1-10), so such a recording scores short of 100
and is not kept.

A sheet at a real one's size (the generator's bulk dial, ``tasks.bulk``,
2026-11-25, Robert: "Go with 1") does not fit one answer: ``get_sheet_state``
comes back cut at the harness's cap.  Until then the drafter stopped there, as
the T1 checkpoint does on the real sheets (``T1.md`` section 11).  Now it reads
what the cut answer still holds (``_cut_sheet``: the size, the title block and
the viewport are written before the entities, so the scale and the twist come
whole), says so, does not ask again, and asks for the rest by kind and by
place: its own line's lettering by the line's anchor, then only what lies in
the box its new labels take (``_clear``).  Work that needs the whole paper on
such a sheet (a table's corner, a title block's keys) is not built, and the
drafter stops rather than guess.

    python -m roaddraft.trajectories.grounded --taskset d1-train --out results/grounded-v2/d1-train-vague
                                              [--level vague] [--type TYPE ...] [--limit N]

Phases covered so far are ``COVERED``; a task that needs another is listed
as not covered and not run.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence

from roaddraft.eval.agents import Agent, ToolCall
from roaddraft.tasks.brief import Task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import PHASE_ORDER, task_type

#: the phases the grounded drafter can do; a task needing any other is not covered yet
COVERED = ("design", "layers", "linework", "edges", "stationing", "bearings", "callouts",
           "widths", "reference", "sheet", "table", "north", "title")
#: the phases that letter the model, sized for the sheet that shows it
MODEL_LETTERING = ("stationing", "bearings", "callouts")
#: the phases drawn on the sheets themselves, in paper inches
SHEET_WORK = ("table", "north", "title")

SPEC = DRAFTING_SPEC_V1
ROLE_LAYER: Dict[str, str] = SPEC["layers"]
#: the office's standard layers, in the spec's order
LAYER_SET: List[str] = list(SPEC.get("layer_set") or dict.fromkeys(ROLE_LAYER.values()))
#: the one number the drafter chooses for itself, where no standard speaks: the gap it
#: leaves between its work and a border, in paper inches
MARGIN_IN = 0.25
#: the clear paper it keeps round a label's point inside a viewport's frame: more than any
#: label but a station equation's reaches from the point it is set at (the longest of the
#: rest, a curve point past station 100+00 such as ``200+64.43 BC``, is 1.07 in)
ROOM_IN = 1.25
_ROOM_WORDS = "an inch and a quarter"
#: the room it allows the lettering all round the line when it judges whether a plan
#: scale fits, where the task leaves the scale to it
LETTERING_IN = 1.5
#: how far it draws a match line each side of the centerline on the paper, where the task
#: does not say (the length the office's own sheets show)
MATCH_HALF_IN = 2.0
#: how far along the line it keeps a match line from a curve point or an end of the line,
#: where the task leaves the breaks to it: a curve point's label stands square to the line
#: as the match line does, and at the office's plan scales sixty feet is more than an inch
#: of paper between the two (the distance the office's own layouts keep)
MATCH_CLEAR_FT = 60.0
#: what a plan sheet of a roadway is titled when the task does not say (the title the
#: title block tool's own example letters)
SHEET_TITLE = "ROADWAY PLAN"
#: how many text heights further off its line it tries a label that will not clear
CLEAR_STEPS = (2, 4, 3, 6)
#: where a label that sits on other lettering is set again, in the order tried: across
#: the line or not, and how many text heights further off it than it was first set (the
#: three and six heights since 2026-11-12, tried after the rest: where a second line's
#: bearing crosses this one's, two heights off is too near and four is on the next thing)
CLEAR_MOVES = ((True, 0), (False, CLEAR_STEPS[0]), (True, CLEAR_STEPS[0]),
               (False, CLEAR_STEPS[1]), (True, CLEAR_STEPS[1]),
               (False, CLEAR_STEPS[2]), (True, CLEAR_STEPS[2]),
               (False, CLEAR_STEPS[3]), (True, CLEAR_STEPS[3]))
_TIMES = {2: "twice", 3: "three times", 4: "four times", 6: "six times"}
#: the rows it asks for at a time when it wants each text whole: a whole row runs to about
#: 1,100 characters and a result is cut at 30,000
FULL_ROWS = 20


class NotCovered(Exception):
    """The task needs something the grounded drafter cannot do yet, or the
    document did not show what it needed to go on."""


@dataclass
class Turn:
    """One assistant turn: a line of shown work and the calls it makes."""
    say: str
    calls: List[ToolCall] = field(default_factory=list)


def _q(tool: str, /, **params) -> ToolCall:
    return ToolCall(tool, params)


# ------------------------------------------------------------ reading the task text

_STATION = re.compile(r"(?<![\d.])(\d+)\+(\d{2}(?:\.\d+)?)")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_N = r"(\d+(?:\.\d+)?)"
_S = r"(\d+\+\d+(?:\.\d+)?)"
_BEGIN = re.compile(rf"(\S+) begins at N {_N}, E {_N}, station {_S}")
_PI = re.compile(rf"PI-\d+ at N {_N}, E {_N}(?:, R = {_N}')?")
_END = re.compile(rf"ends at N {_N}, E {_N}")
_NOT_YET = re.compile(r"(\S+) is not in the design yet")
_EQUATION = re.compile(rf"{_S} BK = {_S} AH")
_LANES = re.compile(r"two (\d+(?:\.\d+)?)-ft lanes")
_BASEFILE = re.compile(r"(\S+\.rdoc\.json)")
_SCALE = r"1\" = \d+'"
_TITLE = re.compile(
    r"project (?P<project>.+?), agency (?P<agency>.+?), sheet title (?P<sheet_title>.+?), "
    r"sheets? (?P<numbers>.+?) of (?P<total_sheets>\d+), (?P<people>.+?), "
    rf"dated (?P<date>\S+), scale (?P<scale>{_SCALE})")
_ROLE = r"(?:designed|drawn|checked)"
_PEOPLE = re.compile(rf"({_ROLE}(?: and {_ROLE})*) by ([^,]+)")


_ST = r"\d+\+\d+(?:\.\d+)?"
_SHEET_NAME = r"[A-Z]+-\d+"
_SHEETS = re.compile(rf"sheets?,? ({_SHEET_NAME}(?:(?:, | and ){_SHEET_NAME})*)")
_AT_SCALE = re.compile(r"at 1\" = (\d+(?:\.\d+)?)'")
_TURNED = re.compile(r"turned (-?\d+(?:\.\d+)?)°")
_BREAKS = re.compile(rf"breaking at stations? ({_ST}(?:(?:, | and ){_ST})*)")
_MATCH_HALF = re.compile(r"(\d+(?:\.\d+)?) ft each side")
_SIZE = re.compile(r"\b(ANSI|ARCH) ([A-E])\b")
#: a layout left to the drafter (``tasks.breaks``): only the first sheet's number is given
_NUMBERED = re.compile(rf"numbered from ({_SHEET_NAME})")
#: the title block such a task states: every value but the sheet's number and the count
_TITLE_OPEN = re.compile(
    r"project (?P<project>.+?), agency (?P<agency>.+?), sheet title (?P<sheet_title>.+?), "
    r"the sheet's own number and the number of sheets, (?P<people>.+?), "
    rf"dated (?P<date>\S+), scale (?P<scale>{_SCALE})")
#: a revision the designer reports (the generator's revision dial)
_REVISED = (("radius", re.compile(r"curve (\d+)'s radius is now (\d+(?:\.\d+)?)'")),
            ("pi", re.compile(r"the PI of curve (\d+) has moved (\d+(?:\.\d+)?) ft (ahead|back)")),
            ("station", re.compile(rf"is restationed to begin at ({_ST}) \(it began at ({_ST})\)")))
#: a revision the task leaves for the drafter to make in the base drawing that holds the design
_IN_BASE = re.compile(r"Make the change in the base drawing")


def request_of(text: str) -> str:
    """The request itself: what follows the rules in the task text."""
    return text.split("THE TASK:", 1)[-1].strip()


def stated_alignment(text: str) -> Optional[dict]:
    """The alignment a task states (``create-alignment``), as the parameters
    of ``create_alignment``: the PIs as [easting, northing(, radius)], the
    stations as the text gives them."""
    begin, end = _BEGIN.search(text), _END.search(text)
    if not begin or not end:
        return None
    pis = [[float(begin.group(3)), float(begin.group(2))]]
    for n, e, r in _PI.findall(text):
        pis.append([float(e), float(n)] + ([float(r)] if r else []))
    pis.append([float(end.group(2)), float(end.group(1))])
    name = begin.group(1)
    if name == "it":  # "ALIGN-1 is not in the design yet: it begins at ..."
        named = _NOT_YET.search(text)
        if not named:
            return None
        name = named.group(1)
    params = {"name": name, "begin_station": begin.group(4), "pis": pis}
    equations = [{"back": back, "ahead": ahead} for back, ahead in _EQUATION.findall(text)]
    if equations:
        params["equations"] = equations
    return params


def stated_title(text: str) -> Optional[dict]:
    """The title block a task states: the fields every sheet shares, as
    ``fill_title_block`` takes them, and under ``sheet_numbers`` the numbers
    the task lists.  None when the task leaves the title block to the drafter."""
    found = _TITLE.search(text)
    if not found:
        # a layout left to the drafter states every value but the number and the count,
        # which follow from the layout: ``sheet_numbers`` None, no ``total_sheets``
        found = _TITLE_OPEN.search(text)
        if not found:
            return None
        fields = {k: found.group(k) for k in ("project", "agency", "sheet_title", "date", "scale")}
        for roles, who in _PEOPLE.findall(found.group("people")):
            for role in roles.split(" and "):
                fields[f"{role}_by"] = who.strip()
        fields["sheet_numbers"] = None
        return fields
    fields = {k: found.group(k) for k in ("project", "agency", "sheet_title", "total_sheets",
                                          "date", "scale")}
    for roles, who in _PEOPLE.findall(found.group("people")):
        for role in roles.split(" and "):
            fields[f"{role}_by"] = who.strip()
    fields["sheet_numbers"] = found.group("numbers")
    return fields


def stated_open(text: str) -> Optional[str]:
    """The number of the first sheet, when the task leaves the layout to the
    drafter (how many sheets, and where they break) and says only where the
    numbering starts; None for a task that names its sheets."""
    found = _NUMBERED.search(text)
    return found.group(1) if found else None


def stated_revision(text: str) -> Optional[dict]:
    """The change a task reports the designer made to the line under a finished
    sheet: ``{"kind", "said"}`` (``radius``, ``pi`` or ``station``, and the
    words that report it), or None."""
    for kind, pattern in _REVISED:
        found = pattern.search(text)
        if found:
            out = {"kind": kind, "said": found.group(0)}
            if kind == "station":
                out.update(begins=found.group(1), began=found.group(2))
            elif kind == "radius":
                out.update(curve=int(found.group(1)), radius=float(found.group(2)))
            else:
                out.update(curve=int(found.group(1)), by=float(found.group(2)),
                           ahead=found.group(3) == "ahead")
            return out
    return None


def stated_layout(text: str) -> dict:
    """The sheet layout a task asks for, as far as it says: the ``sheets`` to
    make, the stations they break at (``breaks``, one fewer), and the sheet
    ``size``, the plan ``scale`` (feet to the inch), the viewports' ``twist``
    and how far a match line reaches each side (``match_half_ft``) where the
    task gives them; None for what it leaves to the drafter (no twist is 0)."""
    names = _SHEETS.search(text)
    breaks = _BREAKS.search(text)
    size, scale = _SIZE.search(text), _AT_SCALE.search(text)
    twist, half = _TURNED.search(text), _MATCH_HALF.search(text)
    return {"sheets": re.findall(_SHEET_NAME, names.group(1)) if names else [],
            "breaks": re.findall(_ST, breaks.group(1)) if breaks else [],
            "size": f"{size.group(1)}_{size.group(2)}" if size else None,
            "scale": float(scale.group(1)) if scale else None,
            "twist": float(twist.group(1)) if twist else 0.0,
            "match_half_ft": float(half.group(1)) if half else None}


# ------------------------------------------------------------ paper geometry


def _n(value: float) -> str:
    """A number as the drafter writes it: to the thousandth, no trailing zeros."""
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _r(value: float) -> float:
    """A number as it is written: what a sum shown in the work is done on."""
    return float(_n(value))


def _n4(value: float) -> str:
    """A place on the paper as the engine gives a corner: to the ten-thousandth."""
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _corner_box(corners: Sequence[Sequence[float]]) -> tuple:
    """The box round a footprint's corners on the paper, and the words that say
    it: ``((x0, y0, x1, y1), words)``."""
    xs = [float(_n4(c[0])) for c in corners]
    ys = [float(_n4(c[1])) for c in corners]
    box = (min(xs), min(ys), max(xs), max(ys))
    return box, (f"corners {', '.join(f'({_n4(x)}, {_n4(y)})' for x, y in zip(xs, ys))}, x "
                 f"{_n4(box[0])} to {_n4(box[2])} and y {_n4(box[1])} to {_n4(box[3])}")


def _mid(a: float, b: float) -> tuple:
    """The middle of two written numbers as the two sums that find it:
    ``(the sums, the middle)``."""
    a, b = _r(a), _r(b)
    total = round(a + b, 3)
    middle = round(total / 2.0, 3)
    return f"{_n(a)} + {_n(b)} = {_n(total)} and {_n(total)} / 2 = {_n(middle)}", middle


def _rect(p: Sequence[float], q: Sequence[float]) -> tuple:
    return (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))


def _apart(a: Sequence[float], b: Sequence[float], gap: float = 0.0) -> Optional[str]:
    """How two paper boxes are clear of each other by ``gap``: ``'x'`` or
    ``'y'``, the axis they are apart on (the wider way), or None when they are not."""
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    if max(dx, dy) < gap:
        return None
    return "x" if dx >= dy else "y"


def _frame(viewport: dict) -> tuple:
    """A viewport's frame on the paper."""
    (cx, cy), w, h = viewport["center_paper"], viewport["width_in"], viewport["height_in"]
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _box_sides(box: Sequence[float]) -> tuple:
    """A model box's two sides as written, and the sums that find them."""
    x0, y0, x1, y1 = (_r(v) for v in box)
    w, h = round(x1 - x0, 3), round(y1 - y0, 3)
    return w, h, f"{_n(x1)} - {_n(x0)} = {_n(w)} ft by {_n(y1)} - {_n(y0)} = {_n(h)} ft"


def _meet(a: Sequence[float], b: Sequence[float]) -> Optional[tuple]:
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[0] < box[2] and box[1] < box[3] else None


def _match_lines(sheet: dict) -> List[dict]:
    """The match lines lettered on a sheet: ``[{"station", "text"}]`` in
    station order, the station as the design counts it."""
    found = []
    for e in (sheet.get("entities") or {}).values():
        anchor = e.get("anchor") or {}
        if (e.get("type") == "text" and str(e.get("content", "")).startswith("MATCH LINE")
                and anchor.get("station") is not None):
            found.append({"station": float(anchor["station"]), "text": anchor.get("ref")})
    return sorted(found, key=lambda m: m["station"])


def _share(matches: Sequence[dict], centre: float) -> tuple:
    """The stretch of the line a sheet holds, ``(from, to)`` with None for an
    open end: between its match lines, on the side its viewport looks at."""
    if not matches:
        return None, None
    if len(matches) == 1:
        m = matches[0]
        return (None, m) if centre < m["station"] else (m, None)
    below = [m for m in matches if m["station"] <= centre]
    above = [m for m in matches if m["station"] > centre]
    return (below[-1] if below else None), (above[0] if above else None)


# ------------------------------------------------------------ the drafter


def _ok(results: Sequence[dict], calls: Sequence[ToolCall], cut: Sequence[str] = ()) -> None:
    """Every call answered, and whole: an answer the harness cut is read only
    from a query named in ``cut``, by a caller that reads its head."""
    for call, result in zip(calls, results):
        if not result.get("ok"):
            why = (result.get("error") or {}).get("message")
            raise NotCovered(f"{call.name} failed: {why}")
        if result.get("truncated") and call.name not in cut:
            raise NotCovered(f"{call.name}: the result was cut; nothing to read it from")


#: what the head of a sheet's state holds, in the order it is written: all of it comes
#: before the sheet's entities, which is where an answer too long for the harness is cut
_SHEET_HEAD = ("name", "size", "width_in", "height_in", "title_block_template",
               "title_block_fields", "viewports")


def _cut_sheet(result: dict) -> dict:
    """What a ``get_sheet_state`` answer still says after the harness cut it
    (``eval.episode``: an answer over the cap comes back as its first 30,000
    characters under ``text``).  The sheet's size, its title block and its
    viewports are written before its entities, so they come whole: the scale
    and the twist are read there.  The entities, the usable area and the
    title block's keys do not come, and are marked not known (``"cut"``)."""
    text = str(result.get("text") or "")
    start = text.find('"sheet": {')
    end = text.find('"entities": {', start)
    if start < 0 or end < 0:
        raise NotCovered("get_sheet_state: the result was cut before its viewports")
    decoder = json.JSONDecoder()
    state: dict = {"cut": True}
    for key in _SHEET_HEAD:
        at = text.find(f'"{key}": ', start, end)
        if at < 0:
            raise NotCovered(f"get_sheet_state: the result was cut before its {key}")
        try:
            state[key], _stop = decoder.raw_decode(text, at + len(key) + 4)
        except ValueError:
            raise NotCovered(f"get_sheet_state: the result was cut inside its {key}") from None
    return state


def _and(names: Sequence[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _s(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# ------------------------------------------------------------ laying out the sheets

#: what each kind of label is called in the shown work
_LABEL_WORDS = {"station": "the station number", "pc": "the BC label", "pt": "the EC label",
                "mc": "the curve number", "bearing": "the bearing",
                "equation": "the station-equation label"}
_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four"}
#: a frame's edges: its name, the paper axis it bounds and the way it faces
_EDGES = (("left", "x", -1), ("bottom", "y", -1), ("right", "x", 1), ("top", "y", 1))
#: how many times a match line's label is set before the drafter gives up on it: on the
#: right of the line and then on the left, each from the end the engine picks and then
#: from the other
MATCH_LABEL_TRIES = 4


def _sheet_points(results: Sequence[dict]) -> List[List[float]]:
    """Where each queried point falls on its sheet, from ``model_to_sheet``
    and ``station_to_xy`` results alike."""
    return [list((r.get("on_sheet") or r)["sheet_point"]) for r in results]


def _span(lo: float, hi: float) -> tuple:
    """How far it is from ``lo`` up to ``hi`` on the paper: ``(the distance,
    the sum that finds it)``.  A point off the sheet's lower left has a
    negative place, and the sum is written on the sizes of the two numbers,
    whichever side of zero they fall."""
    lo, hi = _r(lo), _r(hi)
    d = round(hi - lo, 3)
    if lo >= 0:
        return d, f"{_n(hi)} - {_n(lo)} = {_n(d)}"
    if hi <= 0:
        return d, f"{_n(abs(lo))} - {_n(abs(hi))} = {_n(d)}"
    return d, f"{_n(hi)} + {_n(abs(lo))} = {_n(d)}"


def _choose_breaks(request: str, alignment: str, first: str,
                   kinds: Sequence[str]) -> Generator[Turn, List[dict], dict]:
    """Decide how many sheets a line takes and where they break, for a task
    that leaves both to the drafter (``tasks.breaks``), and return what
    ``_lay_out`` then lays out: the sheets, the breaks, the line as read and
    the first sheet, which is made here to measure on.

    The rule, each step from what the engine reports:

    - *What a sheet holds.*  The first sheet is made with the office's plan
      viewport at the scale (and twist) asked, and the engine is asked where
      the line's points fall on its paper: the two ends, and the BC, middle and
      EC of each curve, which bound the line closely.  Every sheet is turned
      the same way, so the width and height of any stretch are read off those
      places.  A stretch fits a sheet when its box, with a quarter inch all
      round, is inside the office's plan window.
    - *How many sheets.*  Each sheet in turn takes the line as far as it fits:
      where the next point would run past the window, the place the window
      runs out is worked out along the tangent between (the line is straight
      there, so its place on the paper goes with the distance along it).
    - *Where a match line may stand.*  At a whole station on a tangent, sixty
      feet from each end of it, clear of the curve points' lettering.  Where
      the window runs out inside a curve, or too near a tangent's end, the
      sheet ends on the tangent before.
    - *Evenly, if it still fits.*  Filling each sheet leaves the last one
      short, so with the count known the breaks are tried at the sound whole
      stations nearest the even splits, and kept there when every stretch
      still fits.

    Each break is asked of the engine before it is used: its station, its
    point, and where it falls on the paper, to see the stretch it ends fits."""
    sheet_spec = SPEC["sheet"]
    ask = stated_layout(request)
    scale, twist = ask["scale"], ask["twist"]
    if scale is None:
        raise NotCovered("the breaks are left open but no scale is given to count the sheets at")
    kinds = ["curves"] + [k for k in kinds if k != "curves"]
    size = ask["size"] or sheet_spec["size"]
    frame = sheet_spec["viewport"]
    (cx, cy), fw, fh = frame["center_paper"], frame["width_in"], frame["height_in"]
    fit_w, fit_h = sheet_spec["fit_window_in"]
    window = f"{_n(fit_w)} by {_n(fit_h)} in plan window"
    m, clear, station = MARGIN_IN, MATCH_CLEAR_FT, float(SPEC["stationing"]["interval_ft"])

    # -- the line
    calls = [_q("get_design_data", kind="alignments", alignment=alignment)]
    calls += [_q("get_design_data", kind=kind, alignment=alignment) for kind in kinds]
    results = yield Turn(
        "The task asks for the sheets themselves and leaves it to the drafter how many there "
        f"are and where they break, so read the line first: where {alignment} begins and ends "
        "and its curves.", calls)
    _ok(results, calls)
    if not results[0].get("rows"):
        raise NotCovered(f"the design shows no {alignment}")
    line = results[0]["rows"][0]
    rows = {kind: r["rows"] for kind, r in zip(kinds, results[1:])}
    if line.get("equations"):
        raise NotCovered("choosing the breaks of a line with a station equation")
    begin, end = float(line["begin_station"]), float(line["end_station"])
    keys = [{"s": begin, "text": line["begin_station_text"], "kind": "begin",
             "what": f"the beginning of the line at {line['begin_station_text']}",
             "point": list(line["pis"][0]["point"])}]
    for c in rows["curves"]:
        n = c["index"]
        keys += [{"s": float(c["pc_station"]), "text": c["pc_station_text"], "kind": "pc",
                  "curve": n, "what": f"the BC of curve {n} at {c['pc_station_text']}",
                  "point": list(c["pc"])},
                 {"s": float(c["mc_station"]), "text": c["mc_station_text"], "kind": "mc",
                  "curve": n, "what": f"the middle of curve {n} at {c['mc_station_text']}"},
                 {"s": float(c["pt_station"]), "text": c["pt_station_text"], "kind": "pt",
                  "curve": n, "what": f"the EC of curve {n} at {c['pt_station_text']}",
                  "point": list(c["pt"])}]
    keys.append({"s": end, "text": line["end_station_text"], "kind": "end",
                 "what": f"the end of the line at {line['end_station_text']}",
                 "point": list(line["pis"][-1]["point"])})
    #: the tangents, each from the point it starts at to the point it ends at
    tangents = [(a, b) for a, b in zip(keys, keys[1:]) if b["kind"] in ("pc", "end")]
    #: the hundreds of every station read so far: what a whole station is counted from
    hundreds = sorted({int(str(v).split("+")[0]) for row in [line] + [r for rs in rows.values()
                                                                        for r in rs]
                       for k, v in row.items() if k.endswith("station_text")})

    def whole_words(w: float) -> str:
        """The sums that name a whole station: counted on from the nearest
        station already read, then written in feet."""
        number = int(round(w / station))
        h = min(hundreds, key=lambda v: (abs(v - number), v))
        words = ""
        if h != number:
            op = " - " if number < h else " + "
            words = f"{h}{op}{op.join(['1'] * abs(number - h))} = {number} and "
        hundreds.append(number)
        return words + f"{number} * {_n(station)} = {_n(w)}"

    # -- the first sheet, to measure the line on
    turned = {"rotation_deg": twist} if twist else {}
    calls = [_q("create_sheet", name=first, size=size),
             _q("create_viewport", sheet=first, center_paper=[cx, cy], width_in=fw, height_in=fh,
                model_center=list(keys[0]["point"]), feet_per_inch=scale, **turned)]
    for k in keys:
        calls.append(_q("station_to_xy", alignment=alignment, station=k["text"], sheet=first)
                     if k["kind"] == "mc" else
                     _q("model_to_sheet", sheet=first, point=list(k["point"])))
    results = yield Turn(
        f"How much of the line a sheet holds is a matter of the paper, so make the first sheet, "
        f"{first}, on {size.replace('_', ' ')}, "
        f"{'the size asked for' if ask['size'] else 'the plan sheet the office uses'}, with the "
        f"office's plan viewport: {_n(fw)} by {_n(fh)} in, centred at x {_n(cx)}, y {_n(cy)}, at "
        f"{_n(scale)} ft to the inch as the task asks"
        + (f" and turned {_n(twist)}° as it asks" if twist else "")
        + ", set down on the beginning of the line for now. Then ask the engine where the "
        "line's points fall on that paper: its two ends, and the BC, the middle and the EC of "
        "each curve, which bound the line closely. Every sheet is turned the same way, so how "
        "wide and how high any stretch of the line runs can be read off those places, wherever "
        "the view is centred.", calls)
    _ok(results, calls)
    view = results[1]["created"][0]
    for k, q in zip(keys, _sheet_points(results[2:])):
        k["q"] = (_r(q[0]), _r(q[1]))

    def measure(points: Sequence[dict]) -> dict:
        """The box round some points on the paper: its sides, whether it fits
        the plan window with the margin, and the sums."""
        xs, ys = [p["q"][0] for p in points], [p["q"][1] for p in points]
        box = (min(xs), min(ys), max(xs), max(ys))
        w, wsum = _span(box[0], box[2])
        h, hsum = _span(box[1], box[3])
        ww, hh = round(w + m + m, 3), round(h + m + m, 3)
        return {"box": box, "w": w, "h": h, "ww": ww, "hh": hh,
                "fits": ww <= fit_w + 1e-9 and hh <= fit_h + 1e-9,
                "words": f"{wsum} in wide and {hsum} in high, which with a quarter inch all "
                         f"round is {_n(w)} + {_n(m)} + {_n(m)} = {_n(ww)} by {_n(h)} + {_n(m)} "
                         f"+ {_n(m)} = {_n(hh)}"}

    def between(lo: dict, hi: dict) -> List[dict]:
        """A stretch's points: its two ends and the line's points between."""
        return [lo] + [k for k in keys if lo["s"] + 1e-6 < k["s"] < hi["s"] - 1e-6] + [hi]

    def sound_on(a: dict, b: dict, upto: float, after: float) -> Optional[float]:
        """The last whole station on the tangent ``a`` to ``b`` that is not
        past ``upto``, is sixty feet from both its ends and is past ``after``."""
        w = math.floor(min(b["s"] - clear, upto) / station + 1e-9) * station
        return w if w >= a["s"] + clear - 1e-9 and w > after + 1e-6 else None

    def range_words(a: dict, b: dict) -> tuple:
        lo, hi = round(_r(a["s"]) + clear, 3), round(_r(b["s"]) - clear, 3)
        return lo, hi, (f"A match line keeps {_n(clear)} ft from a curve point and from an end "
                        f"of the line, so on the tangent from {a['text']} to {b['text']} it may "
                        f"stand from {_n(_r(a['s']))} + {_n(clear)} = {_n(lo)} to "
                        f"{_n(_r(b['s']))} - {_n(clear)} = {_n(hi)}")

    def asked_cut(text: str, result: dict) -> dict:
        q = _sheet_points([result])[0]
        return {"s": float(result["station"]), "raw": float(result["station"]), "text": text,
                "kind": "cut", "what": f"the break at {text}", "point": list(result["point"]),
                "q": (_r(q[0]), _r(q[1]))}

    # -- how many sheets: each takes the line as far as the window lets it
    count_words = {1: "one sheet", 2: "two sheets", 3: "three sheets", 4: "four sheets"}
    names, filled, start, told = [first], [], keys[0], ""
    prefix, _dash, number = first.rpartition("-")
    while True:
        name = names[-1]
        pts, bad = [start], None
        for k in keys:
            if k["s"] <= start["s"] + 1e-6:
                continue
            if not measure(pts + [k])["fits"]:
                bad = k
                break
            pts.append(k)
        if bad is None:
            whole = measure(pts)
            told += (f"From {start['text']} to the end of the line at {keys[-1]['text']} the "
                     f"points run {whole['words']}, inside the office's {window}, so "
                     + (f"{name} takes the rest of the line. " if filled else
                        f"one sheet carries the whole line: {name}, with no break and no match "
                        "line. "))
            break
        p0, so_far, over = pts[-1], measure(pts), measure(pts + [bad])
        say = (f"{name} starts at {start['text']}. "
               + (f"Through {p0['what']} its points run {so_far['words']}, inside the office's "
                  f"{window}. " if p0 is not start else "")
               + f"Through {bad['what']} {'they' if p0 is not start else 'its points'} would "
               "run "
               + " and ".join(
                   (f"{_span(over['box'][0], over['box'][2])[1]} in wide, {_n(over['w'])} + "
                    f"{_n(m)} + {_n(m)} = {_n(over['ww'])}" if axis == "x" else
                    f"{_span(over['box'][1], over['box'][3])[1]} in high, {_n(over['h'])} + "
                    f"{_n(m)} + {_n(m)} = {_n(over['hh'])}")
                   for axis in ("x", "y")
                   if (over["ww"] > fit_w + 1e-9 if axis == "x" else over["hh"] > fit_h + 1e-9))
               + (f", past the office's {window}. " if p0 is start else ", past the window. "))
        limit = None
        if bad["kind"] in ("pc", "end"):
            # the window runs out on the tangent between: find where along it
            length = round(_r(bad["s"]) - _r(p0["s"]), 3)
            say += (f"The line is straight between the two, {_n(_r(bad['s']))} - "
                    f"{_n(_r(p0['s']))} = {_n(length)} ft of it, so its place on the paper goes "
                    "with the distance along it. ")
            for i, (axis, room_in) in enumerate((("x", fit_w), ("y", fit_h))):
                if (over["ww"] if axis == "x" else over["hh"]) <= room_in + 1e-9:
                    continue
                lo_edge, hi_edge = so_far["box"][i], so_far["box"][i + 2]
                up = bad["q"][i] > p0["q"][i]
                reach, reach_sum = (_span(lo_edge, p0["q"][i]) if up else
                                    _span(p0["q"][i], hi_edge))
                run, run_sum = (_span(p0["q"][i], bad["q"][i]) if up else
                                _span(bad["q"][i], p0["q"][i]))
                room = round(room_in - m - m - reach, 3)
                dist = round(room / run * length, 3)
                at = round(_r(p0["s"]) + dist, 3)
                limit = at if limit is None else min(limit, at)
                say += (f"In {axis} it goes on {run_sum} in over that length, "
                        + (f"and the window, less the quarter inch each side, has {_n(room_in)} "
                           f"- {_n(m)} - {_n(m)} = {_n(room)} in" if p0 is start else
                           f"and the stretch already reaches {reach_sum} in to that point, so "
                           f"the window has {_n(room_in)} - {_n(m)} - {_n(m)} - {_n(reach)} = "
                           f"{_n(room)} in left")
                        + f": {_n(room)} / {_n(run)} * {_n(length)} = {_n(dist)} ft more of the "
                        f"line, to {_n(_r(p0['s']))} + {_n(dist)} = {_n(at)}. ")
            i = next(i for i, (_a, b) in enumerate(tangents) if b is bad)
        else:
            say += (f"That is inside curve {bad['curve']}, and a match line stays off a curve, so "
                    "the sheet ends on the tangent before it. ")
            i = next(i for i, (_a, b) in enumerate(tangents)
                     if b["kind"] == "pc" and b["curve"] == bad["curve"])
        w = None
        while i >= 0 and tangents[i][1]["s"] > start["s"] + 1e-6:
            a, b = tangents[i]
            lo_ok, hi_ok, words = range_words(a, b)
            upto = hi_ok if limit is None else min(hi_ok, limit)
            w = sound_on(a, b, upto, start["s"])
            if w is not None:
                say += (f"{words}. The last whole station there"
                        + (f" not past {_n(upto)}" if upto < hi_ok else "")
                        + f" is {whole_words(w)}: {_station_text(w)}. ")
                break
            say += (f"{words}, and no whole station there"
                    + (f" up to {_n(upto)}" if upto < hi_ok else "")
                    + (f" past {start['text']}" if a["s"] <= start["s"] else "")
                    + " is that clear, so the sheet ends on the tangent before. ")
            i, limit = i - 1, None
        if w is None:
            raise NotCovered(f"no sound whole station ends the sheet that starts at {start['text']}")
        text = _station_text(w)
        calls = [_q("station_to_xy", alignment=alignment, station=text, sheet=first)]
        results = yield Turn(
            told + say + f"Ask the engine for {text}: its point, and where it falls on the paper.",
            calls)
        _ok(results, calls)
        cut = asked_cut(text, results[0])
        ended = measure(between(start, cut))
        if not ended["fits"]:
            raise NotCovered(f"the stretch to {text} does not fit the window after all")
        told = (f"{text} falls at x {_n(cut['q'][0])}, y {_n(cut['q'][1])}: from {start['text']} "
                f"to it the points run {ended['words']}, inside the window, so {name} can run to "
                f"{text}. ")
        filled.append(cut)
        start = cut
        if len(names) >= len(count_words):
            raise NotCovered("the line takes more sheets than the drafter lays out")
        last = int(number) + len(names) - 1
        names.append(f"{prefix}-{last + 1:0{len(number)}d}")
        told += f"The next sheet is numbered on from {name}, {last} + 1 = {last + 1}: "

    # -- where: as evenly as the line allows, when every stretch still fits
    cuts = list(filled)
    if filled:
        n = len(names)
        length = round(_r(end) - _r(begin), 3)
        step = round(length / n, 3)
        targets, at = [], _r(begin)
        sums = [f"{_n(_r(end))} - {_n(_r(begin))} = {_n(length)} ft of line",
                f"{_n(length)} / {n} = {_n(step)} ft a sheet"]
        for _k in range(n - 1):
            nxt = round(at + step, 3)
            sums.append(f"{_n(at)} + {_n(step)} = {_n(nxt)}")
            targets.append(nxt)
            at = nxt
        sound = [w for a, b in tangents
                 for w in [station * j for j in range(int(math.ceil((a["s"] + clear) / station
                                                                    - 1e-9)),
                                                      int(math.floor((b["s"] - clear) / station
                                                                     + 1e-9)) + 1)]]
        even = [min(sound, key=lambda w: (abs(w - t), w)) for t in targets] if sound else []
        told += (f"That is {count_words[n]}. Filling each sheet in turn leaves the last one "
                 f"whatever remains, so see whether the line breaks evenly: {sums[0]}, "
                 f"{sums[1]}, which puts the even break{'s' if n > 2 else ''} at "
                 f"{_and(sums[2:])}. ")
        if even and all(b > a for a, b in zip(even, even[1:])) and \
                [round(w, 3) for w in even] != [round(c["s"], 3) for c in filled]:
            known = {round(c["s"], 3): c for c in filled}
            fresh = [w for w in even if round(w, 3) not in known]
            said = []
            for w in even:
                a, b = next((a, b) for a, b in tangents if a["s"] <= w <= b["s"])
                back, ahead = round(w - _r(a["s"]), 3), round(_r(b["s"]) - w, 3)
                said.append(
                    (f"{_station_text(w)}" if round(w, 3) in known else
                     f"{whole_words(w)}, {_station_text(w)}")
                    + f", {_n(w)} - {_n(_r(a['s']))} = {_n(back)} ft past the start of its "
                    f"tangent and {_n(_r(b['s']))} - {_n(w)} = {_n(ahead)} ft short of its end")
            calls = [_q("station_to_xy", alignment=alignment, station=_station_text(w),
                        sheet=first) for w in fresh]
            results = yield Turn(
                told + "The whole station nearest each that is on a tangent and "
                f"{_n(clear)} ft from its ends: {'; '.join(said)}. Ask the engine for "
                f"{'each' if len(fresh) > 1 else 'it'}, to see that every stretch still fits.",
                calls)
            _ok(results, calls)
            for w, result in zip(fresh, results):
                known[round(w, 3)] = asked_cut(_station_text(w), result)
            tried = [known[round(w, 3)] for w in even]
            bounds = [keys[0]] + tried + [keys[-1]]
            parts, fits_all = [], True
            for name, lo, hi in zip(names, bounds, bounds[1:]):
                stretch = measure(between(lo, hi))
                fits_all = fits_all and stretch["fits"]
                parts.append(f"{name}, {lo['text']} to {hi['text']}, would run "
                             f"{stretch['words']}"
                             + ("" if stretch["fits"] else ", past the window"))
            told = "; ".join(parts) + ". "
            if fits_all:
                cuts = tried
                told += (f"Every stretch is inside the office's {window}, so the sheets break "
                         f"there, at {_and([c['text'] for c in cuts])}. ")
            else:
                told += (f"That does not fit, so the break{'s stay' if n > 2 else ' stays'} where "
                         f"the sheets filled, at {_and([c['text'] for c in cuts])}. ")
        elif even and all(b > a for a, b in zip(even, even[1:])):
            told += (f"The sound whole station{'s' if n > 2 else ''} nearest "
                     f"{'are' if n > 2 else 'is'} where the sheets filled, so the "
                     f"break{'s stay' if n > 2 else ' stays'} at "
                     f"{_and([c['text'] for c in cuts])}. ")
        else:
            told += ("No two sound whole stations near them keep the sheets in order, so the "
                     f"break{'s stay' if n > 2 else ' stays'} where the sheets filled, at "
                     f"{_and([c['text'] for c in cuts])}. ")
    return {"names": names, "breaks": [c["text"] for c in cuts], "line": line, "rows": rows,
            "cuts": [{"text": c["text"], "raw": c["raw"], "point": c["point"]} for c in cuts],
            "made": {first: view}, "lead": told,
            "done": (f"counted {count_words[len(names)]} for {alignment} at "
                     f"{SPEC['sheet']['scale_text_format'].format(fpi=scale)}"
                     + (f", breaking at {_and([c['text'] for c in cuts])}" if cuts else
                        ", with no break"))}


def _lay_out(request: str, alignment: str, summary: dict, kinds: Sequence[str],
             lettered: bool, chosen: Optional[dict] = None) -> Generator[Turn, List[dict], dict]:
    """Make the sheets a task asks for, each with the office's plan viewport
    centred on its stretch of the line, and return the layout: the sheets,
    their viewports and states, the scale and twist, the stretch each holds.

    Nothing of a viewport is worked out by hand.  The view is set down first
    on the point midway between the ends of its stretch; the engine is asked
    where the points that bound the stretch fall on the paper (its ends, and
    the PI of each curve on it: a curve lies inside the corner its tangents
    make there) and then which model point shows at the middle of their box;
    the view is centred on that.  A scale
    the task leaves open is the one the model's lettering was made for, or,
    with nothing lettered yet, the largest of the office's plan scales that
    leaves room for the lettering inside the office's plan window.

    ``chosen`` is a layout the task left to the drafter (``_choose_breaks``):
    its sheets and breaks, the line as already read, and the first sheet, made
    to measure the line on.  The sheets are then laid out as any are."""
    sheet_spec = SPEC["sheet"]
    ask = stated_layout(request)
    names, breaks = ask["sheets"], ask["breaks"]
    if chosen:
        names, breaks = chosen["names"], chosen["breaks"]
    if not names:
        raise NotCovered("the task names no sheet to lay out")
    if len(breaks) != len(names) - 1:
        raise NotCovered("the task gives no break between each pair of its sheets")
    several = len(names) > 1
    twist = ask["twist"]
    kinds = ["curves"] + [k for k in kinds if k != "curves"]
    probe = ask["scale"] is None and lettered and not chosen

    # -- the line the sheets show
    if chosen:  # read already, to choose the breaks by
        line, rows, cuts = chosen["line"], chosen["rows"], chosen["cuts"]
        results = []
    else:
        calls = [_q("get_design_data", kind="alignments", alignment=alignment)]
        calls += [_q("get_design_data", kind=kind, alignment=alignment) for kind in kinds]
        calls += [_q("station_to_xy", alignment=alignment, station=b) for b in breaks]
        if probe:
            calls.append(_q("find_entities", type="text", anchor={"kind": "station"}, limit=1))
        results = yield Turn(
            f"The task asks for the sheet{'s themselves' if several else ' itself'}, so read the "
            f"line first: where {alignment} begins and ends and its curves"
            + (f", the point of the break{'s' if len(breaks) > 1 else ''} at {_and(breaks)}"
               if breaks else "")
            + (", and one of the station numbers already lettered, for the scale it was made for"
               if probe else "") + ".", calls)
        _ok(results, calls)
        if not results[0].get("rows"):
            raise NotCovered(f"the design shows no {alignment}")
        line = results[0]["rows"][0]
        rows = {kind: r["rows"] for kind, r in zip(kinds, results[1:])}
        cuts = [{"text": b, "raw": float(r["station"]), "point": list(r["point"])}
                for b, r in zip(breaks, results[1 + len(kinds):])]
    ends = ([{"text": line["begin_station_text"], "raw": float(line["begin_station"]),
              "point": list(line["pis"][0]["point"])}] + cuts
            + [{"text": line["end_station_text"], "raw": float(line["end_station"]),
                "point": list(line["pis"][-1]["point"])}])
    stretch = {name: (ends[i], ends[i + 1]) for i, name in enumerate(names)}

    # -- the scale: stated, read off the lettering, or tried from the office's own
    allowed = [float(f) for f in sheet_spec["allowed_feet_per_inch"]]
    why = ""
    if ask["scale"] is not None:
        tries = [ask["scale"]]
    elif probe:
        found = results[-1].get("entities") or []
        paper = ((summary.get("settings") or {}).get("annotation_paper") or {}).get(
            "label_offset_in")
        off = (found[0].get("anchor") or {}).get("label_offset") if found else None
        if not off or not paper:
            raise NotCovered("the model's lettering does not show the scale it was made for")
        made = round(_r(off) / _r(paper), 3)
        tries = [made]
        why = (f"The task gives no scale, but the model is lettered already: its station numbers "
               f"sit {_n(off)} ft off the line, which the office plots at {_n(paper)} in, so the "
               f"lettering was made for {_n(off)} / {_n(paper)} = {_n(made)} ft to the inch. ")
    else:
        tries = allowed
        plots = " or ".join(sheet_spec["scale_text_format"].format(fpi=f) for f in allowed)
        why = (f"The task gives no scale. The office plots plans at {plots}; try the larger, "
               f"{_n(allowed[0])} ft to the inch, first. ")

    frame = sheet_spec["viewport"]
    (cx, cy), fw, fh = frame["center_paper"], frame["width_in"], frame["height_in"]
    fit_w, fit_h = sheet_spec["fit_window_in"]
    size = ask["size"] or sheet_spec["size"]
    turned = {"rotation_deg": twist} if twist else {}
    scale = tries[0]

    def measure(name: str) -> List[ToolCall]:
        """Ask where the points that bound a sheet's stretch fall on its paper."""
        lo, hi = stretch[name]
        out = [_q("model_to_sheet", sheet=name, point=list(lo["point"])),
               _q("model_to_sheet", sheet=name, point=list(hi["point"]))]
        out += [_q("model_to_sheet", sheet=name, point=list(c["pi"])) for c in rows["curves"]
                if c["pc_station"] < hi["raw"] - 1e-6 and c["pt_station"] > lo["raw"] + 1e-6]
        return out

    def asked(calls: List[ToolCall]) -> Dict[str, tuple]:
        spans = {}
        for name in names:
            more = measure(name)
            spans[name] = (len(calls), len(calls) + len(more))
            calls += more
        return spans

    def boxes_of(pts: Dict[str, list]) -> Dict[str, tuple]:
        out = {}
        for name in names:
            xs, ys = [_r(q[0]) for q in pts[name]], [_r(q[1]) for q in pts[name]]
            if min(xs) < 0 or min(ys) < 0:
                raise NotCovered(f"the stretch on {name} falls off the paper from where the view "
                                 f"was started")
            out[name] = (min(xs), min(ys), max(xs), max(ys))
        return out

    # -- the sheets, each with a view started midway between the ends of its stretch
    #: a sheet made already (the first of a layout the drafter chose, measured on), with
    #: its viewport's id: its view is moved to the start, not made
    made: Dict[str, str] = dict((chosen or {}).get("made") or {})
    calls = [_q("create_sheet", name=name, size=size) for name in names if name not in made]
    starts = []
    for name in names:
        lo, hi = stretch[name]
        tx, mx = _mid(lo["point"][0], hi["point"][0])
        ty, my = _mid(lo["point"][1], hi["point"][1])
        starts.append(f"for {name}, {lo['text']} to {hi['text']}, x {tx} and y {ty}")
        if name in made:
            calls.append(_q("modify_viewport", sheet=name, viewport_id=made[name],
                            changes={"model_center": [mx, my]}))
        else:
            calls.append(_q("create_viewport", sheet=name, center_paper=[cx, cy], width_in=fw,
                            height_in=fh, model_center=[mx, my], feet_per_inch=scale, **turned))
    calls += [_q("get_sheet_state", sheet=name) for name in names]
    spans = asked(calls)
    count = len(names)
    fresh = [name for name in names if name not in made]
    if chosen and fresh:
        say = (f"{chosen['lead']}Make {_and(fresh)} like {_and(list(made))}: on "
               f"{size.replace('_', ' ')}, with the office's plan viewport, {_n(fw)} by {_n(fh)} "
               f"in, centred at x {_n(cx)}, y {_n(cy)}, at {_n(scale)} ft to the inch"
               + (f" and turned {_n(twist)}°" if twist else "")
               + f". Start each view, {_and(list(made))}'s too, on the point midway between the "
               f"ends of its stretch: {'; '.join(starts)}. Then ask the engine where each stretch "
               "falls on its paper. Its two ends and the PI of each curve on it bound it: a curve "
               "lies inside the corner its tangents make at the PI.")
    elif chosen:
        say = (f"{chosen['lead']}Move the view of {_and(list(made))} to the point midway between "
               f"the two ends of the line: {'; '.join(starts)}. Then ask the engine where the "
               "line falls on the paper from there. Its two ends and the PI of each curve bound "
               "it: a curve lies inside the corner its tangents make at the PI.")
    else:
        say = (
            f"{why}Make {_and(names)} on {size.replace('_', ' ')}, "
            f"{'the size asked for' if ask['size'] else 'the plan sheet the office uses'}, "
            f"{'each ' if several else ''}with the office's plan viewport: {_n(fw)} by {_n(fh)} in, "
            f"centred at x {_n(cx)}, y {_n(cy)}, at {_n(scale)} ft to the inch"
            + (f" and turned {_n(twist)}° as the task asks" if twist else "")
            + f". Start {'each' if several else 'the'} view on the point midway between the ends of "
            f"its stretch: {'; '.join(starts)}. Then ask the engine where the stretch falls on the "
            "paper. Its two ends and the PI of each curve on it bound it: a curve lies inside the "
            "corner its tangents make at the PI.")
    results = yield Turn(say, calls)
    _ok(results, calls)
    views = len(fresh)  # (the calls run: the sheets made, a view each, then each sheet read)
    vp = {name: made[name] if name in made else results[views + i]["created"][0]
          for i, name in enumerate(names)}
    state = {name: results[views + count + i]["sheet"] for i, name in enumerate(names)}
    frame_box = (cx - fw / 2.0, cy - fh / 2.0, cx + fw / 2.0, cy + fh / 2.0)
    for name in names:
        ua = state[name]["usable_area"]
        if not (ua[0] <= frame_box[0] and ua[1] <= frame_box[1]
                and frame_box[2] <= ua[2] and frame_box[3] <= ua[3]):
            raise NotCovered(f"the office's plan viewport does not fit the usable area of {name}")
    boxes = boxes_of({name: _sheet_points(results[a:b]) for name, (a, b) in spans.items()})

    # -- a scale left to the drafter: the largest that leaves room for the lettering.  The
    # stretch was measured at the first of them; at another its spans are those times the
    # ratio of the two, so no view is set twice to find out
    judged = ""
    measured_at = scale
    window = f"{_n(fit_w)} by {_n(fit_h)} in plan window"

    #: the sheets whose measured spans the shown work has already given
    told: set = set()

    def spans_at(name: str, at: float, say: bool = False) -> tuple:
        """``(wide, high, the sums)`` of a sheet's stretch on the paper at a
        scale; ``say`` marks the measured spans as given in the shown work."""
        box = boxes[name]
        w, h = round(box[2] - box[0], 3), round(box[3] - box[1], 3)
        sums = (f"{_n(box[2])} - {_n(box[0])} = {_n(w)} in wide and {_n(box[3])} - "
                f"{_n(box[1])} = {_n(h)} in high")
        given = name in told
        if say:
            told.add(name)
        if at == measured_at:
            return w, h, sums
        w2, h2 = round(w * measured_at / at, 3), round(h * measured_at / at, 3)
        scaled = (f"{_n(w)} * {_n(measured_at)} / {_n(at)} = {_n(w2)} in wide and {_n(h)} * "
                  f"{_n(measured_at)} / {_n(at)} = {_n(h2)} in high")
        if not given:
            scaled = f"{sums} at {_n(measured_at)}, which at {_n(at)} is {scaled}"
        return w2, h2, scaled

    def lettered_spans(name: str, at: float) -> tuple:
        w, h, _sums = spans_at(name, at)
        return round(w + 2 * LETTERING_IN, 3), round(h + 2 * LETTERING_IN, 3)

    if len(tries) > 1:
        room, parts = _n(LETTERING_IN), []
        for k, at in enumerate(tries):
            fullest = max(names, key=lambda name: max(lettered_spans(name, at)[0] / fit_w,
                                                     lettered_spans(name, at)[1] / fit_h))
            again = fullest in told
            w, h, sums = spans_at(fullest, at, say=True)
            ww, hh = lettered_spans(fullest, at)
            on = (f"At {_n(at)} ft to the inch the {'same ' if again else ''}stretch"
                  f"{f' on {fullest}' if several else ''} "
                  f"is {sums}; with an inch and a half all round for the lettering that is "
                  f"{_n(w)} + {room} + {room} = {_n(ww)} by {_n(h)} + {room} + {room} = {_n(hh)}")
            scale = at
            if ww <= fit_w and hh <= fit_h:
                parts.append(f"{on}, inside the office's {window}, so that scale does.")
                break
            if k == len(tries) - 1:
                parts.append(f"{on}, past the office's {window} as well, but it is the smallest "
                             f"scale the office plots at, so it stands.")
                break
            parts.append(f"{on}, more than the office's {window} holds, so that scale is too "
                         f"large.")
        judged = " ".join(parts) + " "
    rescaled = scale != measured_at

    # -- the model point at the middle of each stretch, as the paper shows it
    calls, says = [], []
    for name in names:
        b = boxes[name]
        w, h, _sums = spans_at(name, scale)
        if w > fw - 2 * MARGIN_IN or h > fh - 2 * MARGIN_IN:
            raise NotCovered(f"the stretch on {name} does not fit the plan viewport at "
                             f"{scale:g} ft to the inch")
        tx, mx = _mid(b[0], b[2])
        ty, my = _mid(b[1], b[3])
        lo, hi = stretch[name]
        calls.append(_q("sheet_to_model", sheet=name, point=[mx, my]))
        says.append(f"On {name} the line from {lo['text']} to {hi['text']} falls between x "
                    f"{_n(b[0])} and x {_n(b[2])} and between y {_n(b[1])} and y {_n(b[3])}, so "
                    f"its middle is at x {tx} and y {ty}.")
    results = yield Turn(
        judged + " ".join(says) + " Ask the engine which model point shows at "
        f"{'each middle' if several else 'that middle'}, to centre the view on it"
        + (": the same point is the middle of the stretch at any scale." if rescaled else "."),
        calls)
    _ok(results, calls)

    # -- centre each view there, and see that its stretch shows
    to_scale = {"feet_per_inch": scale} if rescaled else {}
    calls = [_q("modify_viewport", sheet=name, viewport_id=vp[name],
                changes={**to_scale, "model_center": list(r["point"])})
             for name, r in zip(names, results)]
    for name, r in zip(names, results):
        state[name]["viewports"][0].update(model_center=list(r["point"]), feet_per_inch=scale)
    first = len(calls)
    for name in names:
        lo, hi = stretch[name]
        calls += [_q("model_to_sheet", sheet=name, point=list(lo["point"])),
                  _q("model_to_sheet", sheet=name, point=list(hi["point"]))]
    results = yield Turn(
        f"Centre {'each' if several else 'the'} view on that point"
        + (f", at {_n(scale)} ft to the inch" if rescaled else "")
        + f", and ask where the two ends of {'its' if several else 'the'} stretch fall now, to "
        "see that both show.", calls)
    _ok(results, calls)
    ends_paper = {}
    for i, name in enumerate(names):
        pair = results[first + 2 * i:first + 2 * i + 2]
        if not all(r.get("visible") for r in pair):
            raise NotCovered(f"an end of the stretch does not show on {name}")
        ends_paper[name] = _sheet_points(pair)
    return {"ask": ask, "names": names, "size": size, "scale": scale, "twist": twist, "vp": vp,
            "state": state, "rows": rows, "stretch": stretch, "cuts": cuts, "line": line,
            "ends_paper": ends_paper, "frame": (fw, fh),
            "carry": f"Both ends of {'each' if several else 'the'} stretch show inside "
                     f"{'its' if several else 'the'} frame."}


def _trim_and_match(layout: dict, alignment: str, match_layer: str, lead: str,
                    read_state: bool,
                    dims: Optional[Dict[str, dict]] = None) -> Generator[Turn, List[dict], dict]:
    """On a layout of several sheets, trim each viewport's frame round its own
    stretch and draw and letter the match lines; returns the labels' boxes by
    sheet and, with ``read_state``, each sheet's state as it ends up.

    The frame is drawn from what the engine reports, the point each label the
    sheet shows is set at on the paper: an inch and a quarter clear round
    every label of the stretch and the ends of the stretch, and a quarter inch
    round the ends of its match lines.  A label of another sheet's stretch
    that would show inside the frame nearer an edge than that would be cut
    there, so the edge moves out past it.  A station equation's label is the
    one long enough to reach further, so its own box is read for it.  A width
    dimension (``dims``: each one's id with the station it measures at) is
    read with the lettering and framed round its number, whose corners on the
    paper come with the listing: whole inside the frame of its own stretch's
    sheet, and whole or not at all on another's.

    A frame worked out that way can reach past what its view showed while the
    view was the whole plan viewport, where no lettering was read; the view
    is then centred on the frame's middle and the sheet read again before the
    frame is trusted.

    A match line's label starts a quarter inch past the end of its line and
    is read back: if its text runs back along the line instead (on a sheet
    the engine picks the end a label is set from by how it would read in the
    model and its rotation by how it reads on the paper, and through a turned
    viewport the two can disagree), it is set again from its other end, and
    on the other side of the line if it will not fit the paper on the first."""
    names, stretch, cuts = layout["names"], layout["stretch"], layout["cuts"]
    scale, vp, state = layout["scale"], layout["vp"], layout["state"]
    fw, fh = layout["frame"]
    stated = layout["ask"]["match_half_ft"]
    half = _r(stated) if stated is not None else round(MATCH_HALF_IN * _r(scale), 3)
    half_in = round(half / _r(scale), 3) if stated is not None else MATCH_HALF_IN
    touching = {name: [c for c in cuts if c is stretch[name][0] or c is stretch[name][1]]
                for name in names}
    each = "each" if len(cuts) > 1 else "the"

    # -- what each sheet shows of the lettering, and where its match lines will end
    #: how far from the centerline a match line's label starts: a quarter inch past its end
    start = round(half_in + MARGIN_IN, 3)
    #: what each sheet is read for: its lettering, and the width dimensions with it
    shown_types = ["text", "dimension"] if dims else "text"
    calls, at = [], {}
    for name in names:
        at[name] = {"texts": len(calls), "cuts": []}
        calls.append(_q("find_entities", visible_on=name, type=shown_types))
        for cut in touching[name]:
            at[name]["cuts"].append(len(calls))
            calls += [_q("station_to_xy", alignment=alignment, station=cut["text"],
                         offset=-half, sheet=name),
                      _q("station_to_xy", alignment=alignment, station=cut["text"],
                         offset=half, sheet=name)]
    equations_at = len(calls)
    calls.append(_q("find_entities", type="text", anchor={"kind": "equation"}, detail="full"))
    reach_words = (f"{_n(half)} ft each side of the centerline, as the task gives"
                   if stated is not None else
                   f"{_n(MATCH_HALF_IN)} in each side of the centerline on the paper, as the "
                   f"office's sheets show them, which at {_n(scale)} ft to the inch is "
                   f"{_n(MATCH_HALF_IN)} * {_n(scale)} = {_n(half)} ft")
    results = yield Turn(
        (lead + " " if lead else "")
        + f"{_COUNT_WORDS.get(len(names), 'Several')} sheets share the line, so each frame is "
        "trimmed round its own stretch: wide enough that every label of the stretch shows "
        "whole, and no further into the next sheet's stretch than it must reach. Read the "
        "lettering each sheet shows, each label with the point it is set at on the paper; where "
        f"the two ends of {each} match line will fall ({reach_words}); and the box of any "
        f"station-equation label, the one label long enough to reach more than {_ROOM_WORDS} "
        "from its point.", calls)
    _ok(results, calls)
    texts = {name: list(results[at[name]["texts"]].get("entities") or []) for name in names}
    more = {name: results[at[name]["texts"]].get("more") for name in names}
    line_ends = {name: [_sheet_points(results[k:k + 2]) for k in at[name]["cuts"]]
                 for name in names}
    eq_boxes = {row["id"]: row["bbox"] for row in results[equations_at].get("entities") or []
                if row.get("bbox")}
    while any(more.values()):
        cut_short = [name for name in names if more[name]]
        calls = [_q("find_entities", visible_on=name, type=shown_types,
                    start=more[name]["start"]) for name in cut_short]
        results = yield Turn(f"The list for {_and(cut_short)} stopped short of all the "
                             "lettering shown; read the rest.", calls)
        _ok(results, calls)
        for name, r in zip(cut_short, results):
            texts[name] += list(r.get("entities") or [])
            more[name] = r.get("more")

    #: each long label's reach, worked out once: said before the frames that use it
    long_labels: Dict[str, str] = {}

    dim_words = ("A width dimension is framed round its number, whose corners on each sheet "
                 "came with the listing: whole inside the frame of the sheet its station is "
                 "on, and on another sheet whole or not at all. ") if dims else ""

    def reach_of(row: dict, who: str) -> float:
        """How far the label may reach from its point, in paper inches: an
        inch, or a station equation's own length."""
        if (row.get("anchor") or {}).get("kind") != "equation":
            return ROOM_IN
        bb = eq_boxes.get(row["id"])
        if bb is None:
            raise NotCovered("a station-equation label's box was not read")
        w = round(_r(bb[2]) - _r(bb[0]), 3)
        h = round(_r(bb[3]) - _r(bb[1]), 3)
        total = round(w + h, 3)
        paper = round(total / _r(scale), 3)
        reach = round(paper + MARGIN_IN, 3)
        long_labels[who] = (
            f"{who[0].upper()}{who[1:]} is long: its box in the model is {_n(bb[2])} - "
            f"{_n(bb[0])} = {_n(w)} ft by {_n(bb[3])} - {_n(bb[1])} = {_n(h)} ft, so it reaches "
            f"no more than {_n(w)} + {_n(h)} = {_n(total)} ft from its point, {_n(total)} / "
            f"{_n(scale)} = {_n(paper)} in on the paper, and it is given {_n(paper)} + "
            f"{_n(MARGIN_IN)} = {_n(reach)} in clear.")
        return reach

    # -- each frame: round its own, then out past any other label it would cut
    cx, cy = state[names[0]]["viewports"][0]["center_paper"]
    #: what each view shows while its frame is still the whole plan viewport, and the sum
    #: that finds each edge of it
    shown = {"left": (cx - fw / 2.0, f"{_n(cx)} - {_n(fw)} / 2"),
             "bottom": (cy - fh / 2.0, f"{_n(cy)} - {_n(fh)} / 2"),
             "right": (cx + fw / 2.0, f"{_n(cx)} + {_n(fw)} / 2"),
             "top": (cy + fh / 2.0, f"{_n(cy)} + {_n(fh)} / 2")}
    ends_now = dict(layout["ends_paper"])

    def frame_for(name: str) -> dict:
        """The frame a sheet needs, from what was last read of it: its size,
        the point at its middle, the words that say how it was found, and
        ``past``, the edges of the view it reaches beyond (where lettering has
        not been read, so it cannot be trusted yet)."""
        lo, hi = stretch[name]
        own, others = [], []
        #: the width dimensions' numbers this sheet lists, each the box round its corners
        own_dims, other_dims = [], []
        for row in texts[name]:
            q, anchor = row.get("sheet_point"), row.get("anchor") or {}
            if dims and row.get("type") == "dimension":
                if row["id"] not in dims:
                    raise NotCovered(f"{name} shows a dimension the drafter did not place")
                if not row.get("paper_corners"):
                    raise NotCovered(f"{row['id']} came back without the corners of its number")
                box, said = _corner_box(row["paper_corners"])
                station = dims[row["id"]]["station"]
                mine = lo["raw"] - 1e-6 <= float(station) <= hi["raw"] + 1e-6
                (own_dims if mine else other_dims).append(
                    {"box": box, "said": said,
                     "who": f"the number of the width dimension {row['id']} on "
                            f"{dims[row['id']]['ref']}"})
                continue
            if not q:
                continue
            who = (f"{_LABEL_WORDS.get(anchor.get('kind'), 'the label')} at "
                   f"{anchor.get('ref') or row['id']}")
            station = anchor.get("station")
            item = {"x": _r(q[0]), "y": _r(q[1]), "r": reach_of(row, who), "who": who}
            mine = (station is not None
                    and lo["raw"] - 1e-6 <= float(station) <= hi["raw"] + 1e-6)
            (own if mine else others).append(item)
        for end, q in zip((lo, hi), ends_now[name]):
            own.append({"x": _r(q[0]), "y": _r(q[1]), "r": ROOM_IN,
                        "who": f"the end of the stretch at {end['text']}"})
        for cut, pair in zip(touching[name], line_ends[name]):
            for q in pair:
                own.append({"x": _r(q[0]), "y": _r(q[1]), "r": MARGIN_IN,
                            "who": f"the end of the match line at {cut['text']}"})
        def r_of(it: dict, axis: str) -> float:
            return it.get("r" + axis, it["r"])

        edge, notes = {}, []
        for side, axis, way in _EDGES:
            it = (min if way < 0 else max)(own, key=lambda i: i[axis] + way * r_of(i, axis))
            edge[side] = round(it[axis] + way * r_of(it, axis), 3)
            notes.append(f"the {side} edge at {axis} {_n(it[axis])} {'-' if way < 0 else '+'} "
                         f"{_n(r_of(it, axis))} = {_n(edge[side])}, past {it['who']}")
        grown = []
        def take_in(box: Sequence[float]) -> List[str]:
            """Move out each edge the box reaches past, to the thousandth just
            beyond it; the words for each move."""
            out = []
            for k, (side, axis, way) in enumerate(_EDGES):
                if way * (box[k] - edge[side]) > 1e-9:
                    edge[side] = (math.ceil if way > 0 else math.floor)(
                        round(box[k] * 1000.0, 6)) / 1000.0
                    out.append(f"the {side} edge moves out to {axis} {_n(edge[side])}")
            return out

        # a width dimension of this stretch: its number whole inside the frame
        for d in own_dims:
            out = take_in(d["box"])
            grown.append(f"{d['who'][0].upper()}{d['who'][1:]} has {d['said']}: "
                         + (_and(out) + " to take it in." if out else "inside the frame."))
        for _ in range(30):
            moved = False
            for d in other_dims:
                box = d["box"]
                if not (box[0] < edge["right"] and edge["left"] < box[2]
                        and box[1] < edge["top"] and edge["bottom"] < box[3]):
                    continue  # none of it is inside the frame: the other sheet's to show
                out = take_in(box)
                if out:
                    grown.append(
                        f"{d['who'][0].upper()}{d['who'][1:]}, of another sheet's stretch, has "
                        f"{d['said']}, part inside the frame and part not, so it would be cut: "
                        f"{_and(out)} to show it whole.")
                    moved = True
            for it in others:
                if not (edge["left"] < it["x"] < edge["right"]
                        and edge["bottom"] < it["y"] < edge["top"]):
                    continue  # its point is off the frame: the other sheet's to show
                for side, axis, way in _EDGES:
                    gap = round(way * (edge[side] - it[axis]), 3)
                    if gap >= r_of(it, axis) - 1e-9:
                        continue
                    was = edge[side]
                    edge[side] = round(it[axis] + way * r_of(it, axis), 3)
                    inside = (f"{_n(was)} - {_n(it[axis])}" if way > 0
                              else f"{_n(it[axis])} - {_n(was)}")
                    grown.append(
                        f"{it['who'][0].upper()}{it['who'][1:]}, of another sheet's stretch, "
                        f"would show only {inside} = {_n(gap)} in inside the {side} edge and "
                        f"be cut there, so that edge moves out to {axis} {_n(it[axis])} "
                        f"{'-' if way < 0 else '+'} {_n(r_of(it, axis))} = {_n(edge[side])}.")
                    moved = True
            if not moved:
                break
        else:
            raise NotCovered(f"the frame on {name} does not settle clear of the lettering")
        w = round(edge["right"] - edge["left"], 3)
        h = round(edge["top"] - edge["bottom"], 3)
        if w > fw + 1e-9 or h > fh + 1e-9:
            raise NotCovered(f"the frame {name} needs is larger than the office's plan viewport")
        if min(edge.values()) < 0:
            raise NotCovered(f"the frame {name} needs runs off the paper")
        past = [side for side, _axis, way in _EDGES
                if way * (edge[side] - shown[side][0]) > 1e-9]
        tx, mx = _mid(edge["left"], edge["right"])
        ty, my = _mid(edge["bottom"], edge["top"])
        words = (f"On {name}, {lo['text']} to {hi['text']}: {'; '.join(notes)}. "
                 + (" ".join(grown) + " " if grown else "")
                 + f"That frame is {_n(edge['right'])} - {_n(edge['left'])} = {_n(w)} in wide "
                 f"and {_n(edge['top'])} - {_n(edge['bottom'])} = {_n(h)} in high, with its "
                 f"middle at x {tx} and y {ty}.")
        if past:
            words += (" But the view shows the model only as far as "
                      + _and([f"its {side} edge at {shown[side][1]} = {_n(shown[side][0])}"
                              for side in past])
                      + ", and this frame reaches past that, where no lettering has been read "
                      "yet: the view is centred on this middle first, as it is, and read again.")
        return {"size": (w, h), "middle": [mx, my], "words": words, "past": past}

    def ask_middles(which: Sequence[str]) -> List[ToolCall]:
        return [_q("sheet_to_model", sheet=name, point=frames[name]["middle"])
                for name in which]

    frames = {name: frame_for(name) for name in names}
    calls = ask_middles(names)
    results = yield Turn(
        f"Each frame keeps {_ROOM_WORDS} clear round the points of its own stretch's labels "
        "and the ends of the stretch, and a quarter inch round the ends of its match line. "
        + dim_words
        + "".join(words + " " for words in long_labels.values())
        + " ".join(frames[name]["words"] for name in names)
        + " Ask the engine which model point shows at each middle.", calls)
    _ok(results, calls)
    centre = {name: list(r["point"]) for name, r in zip(names, results)}
    for _again in range(2):
        behind = [name for name in names if frames[name]["past"]]
        if not behind:
            break
        # the frame reaches where nothing was read: look from its middle, then frame again
        calls, at = [], {}
        for name in behind:
            lo, hi = stretch[name]
            at[name] = len(calls)
            calls += [_q("modify_viewport", sheet=name, viewport_id=vp[name],
                         changes={"model_center": centre[name]}),
                      _q("find_entities", visible_on=name, type=shown_types),
                      _q("model_to_sheet", sheet=name, point=list(lo["point"])),
                      _q("model_to_sheet", sheet=name, point=list(hi["point"]))]
            for cut in touching[name]:
                calls += [_q("station_to_xy", alignment=alignment, station=cut["text"],
                             offset=-half, sheet=name),
                          _q("station_to_xy", alignment=alignment, station=cut["text"],
                             offset=half, sheet=name)]
        results = yield Turn(
            f"Centre the view of {_and(behind)} on that point, its frame still the whole plan "
            "viewport, and read again what it shows: the lettering, the two ends of the stretch "
            "and the ends of its match line.", calls)
        _ok(results, calls)
        for name in behind:
            k = at[name]
            if results[k + 1].get("more"):
                raise NotCovered(f"{name} shows more lettering than one reading lists")
            state[name]["viewports"][0]["model_center"] = centre[name]
            texts[name] = list(results[k + 1].get("entities") or [])
            ends_now[name] = _sheet_points(results[k + 2:k + 4])
            line_ends[name] = [_sheet_points(results[k + 4 + 2 * i:k + 6 + 2 * i])
                               for i in range(len(touching[name]))]
            frames[name] = frame_for(name)
        calls = ask_middles(behind)
        results = yield Turn(
            "Seen from there. " + " ".join(frames[name]["words"] for name in behind)
            + f" Ask the engine which model point shows at {'each' if len(behind) > 1 else 'that'}"
            " middle.", calls)
        _ok(results, calls)
        centre.update({name: list(r["point"]) for name, r in zip(behind, results)})
    else:
        raise NotCovered("a frame keeps reaching past what its view shows")
    sized = {name: frames[name]["size"] for name in names}

    # -- the trimmed frames, the match lines across the centerline and their labels
    label_h = SPEC["text"]["label_height_in"]
    calls = [_q("modify_viewport", sheet=name, viewport_id=vp[name],
                changes={"width_in": sized[name][0], "height_in": sized[name][1],
                         "model_center": centre[name]})
             for name in names]
    calls += [_q("draw_station_offset", alignment=alignment, layer=match_layer,
                 points=[f"{cut['text']}@{_n(half)}L", f"{cut['text']}@{_n(half)}R"])
              for cut in cuts]
    labels = []
    for i, name in enumerate(names):
        for cut in touching[name]:
            other = names[i + 1] if cut is stretch[name][1] else names[i - 1]
            labels.append({"sheet": name, "cut": cut, "side": "right", "halign": None,
                           "content": f"MATCH LINE STA {cut['text']} SEE SHEET {other}"})

    def place(label: dict) -> ToolCall:
        params = {"space": label["sheet"], "alignment": alignment,
                  "anchor": label["cut"]["text"], "kind": "custom", "content": label["content"],
                  "rotation": "perpendicular", "side": label["side"], "label_offset": start,
                  "height": label_h, "layer": match_layer}
        if label["halign"]:  # the end the text is set from, where the engine's own ran back
            params["halign"] = label["halign"]
        return _q("place_label", **params)

    for label in labels:
        label["call"] = len(calls)
        calls.append(place(label))
    for label in labels:
        label["point_call"] = len(calls)
        calls.append(_q("station_to_xy", alignment=alignment, station=label["cut"]["text"],
                        sheet=label["sheet"]))
    results = yield Turn(
        "Set each frame to that size and centre it on the point the engine gave, which keeps "
        f"the plan in the middle of its sheet. Then draw {each} match line square across the "
        f"centerline at {_and([c['text'] for c in cuts])}, {_n(half)} ft each side, on "
        f"{match_layer}, and letter it on both sheets it joins, MATCH LINE STA <its station> "
        f"SEE SHEET <the other sheet>, in {_n(label_h)} in text reading along the match line. "
        + (f"The line reaches {_n(half)} / {_n(scale)} = {_n(half_in)} in from the centerline "
           "on the paper" if stated is not None else
           f"The line reaches {_n(half_in)} in from the centerline on the paper")
        + f", so each label starts a quarter inch past its end: {_n(half_in)} + "
        f"{_n(MARGIN_IN)} = {_n(start)}. Ask where each break falls on its sheets now, to check "
        "the labels against.", calls)
    _ok(results, calls)
    for label in labels:
        label["id"] = results[label["call"]]["created"][0]
        label["point"] = _sheet_points([results[label["point_call"]]])[0]

    # -- read the labels back: on the paper, and beyond the end of the line, not across it
    pending, checked = list(labels), []
    for _round in range(MATCH_LABEL_TRIES):
        calls = [_q("get_entity", id=label["id"]) for label in pending]
        reread = len(calls)
        if read_state:
            calls += [_q("get_sheet_state", sheet=name) for name in names]
        results = yield Turn(
            (" ".join(checked) + " " if checked else "")
            + "Read each match line label back for the box it takes"
            + (", and each sheet as it now stands." if read_state else "."), calls)
        _ok(results, calls)
        if read_state:
            state = {name: r["sheet"] for name, r in zip(names, results[reread:])}
        checked, again = [], []
        for label, result in zip(pending, results):
            name, box = label["sheet"], tuple(result["bbox"])
            ua = state[name]["usable_area"]
            px, py = _r(label["point"][0]), _r(label["point"][1])
            gaps = [(round(_r(box[0]) - px, 3), f"{_n(box[0])} - {_n(px)}"),
                    (round(px - _r(box[2]), 3), f"{_n(px)} - {_n(box[2])}"),
                    (round(_r(box[1]) - py, 3), f"{_n(box[1])} - {_n(py)}"),
                    (round(py - _r(box[3]), 3), f"{_n(py)} - {_n(box[3])}")]
            gap, sums = max(gaps)
            on_paper = (ua[0] + MARGIN_IN <= box[0] and ua[1] + MARGIN_IN <= box[1]
                        and box[2] <= ua[2] - MARGIN_IN and box[3] <= ua[3] - MARGIN_IN)
            beyond = gap >= ROOM_IN
            apart = all(_apart(box, other["box"], MARGIN_IN) is not None
                        for other in labels if other is not label and other["sheet"] == name
                        and other.get("box") and other not in pending)
            takes = (f"{label['id']} on {name} takes up x {_n(box[0])} to {_n(box[2])} and y "
                     f"{_n(box[1])} to {_n(box[3])}")
            where = f"the break's point at x {_n(px)}, y {_n(py)}"
            if on_paper and beyond and apart:
                label["box"] = box
                checked.append(f"{takes}, inside the usable area and {sums} = {_n(gap)} in "
                               f"clear of {where}, so it lies beyond the end of the match line.")
                continue
            runs_back = (f"{where} is "
                         + ("inside that box" if gap < 0 else f"only {sums} = {_n(gap)} in from it")
                         + ": the text runs back along the match line instead of away from it")
            if not beyond and label["halign"] is None:
                # the engine set the text from the end that runs it back over the line
                set_from = (result.get("entity") or {}).get("halign")
                label["halign"] = "right" if set_from == "left" else "left"
                checked.append(f"{takes}, and {runs_back}. It was set from its {set_from} end; "
                               f"set it again from the other (halign {label['halign']}).")
            elif label["side"] == "right":
                label["side"], label["halign"] = "left", None
                checked.append(
                    f"{takes}, "
                    + (f"and {runs_back} still" if not beyond else
                       "which is not clear of the other label on the sheet" if on_paper else
                       f"past the usable area (x {_n(ua[0])} to {_n(ua[2])}, y {_n(ua[1])} to "
                       f"{_n(ua[3])}) or within a quarter inch of its edge")
                    + ". Set it on the left of the line instead.")
            else:
                raise NotCovered(f"no place holds the match line label on {name}")
            again.append(label)
        if not again:
            break
        calls = [_q("delete_entities", ids=[label["id"] for label in again])]
        calls += [place(label) for label in again]
        results = yield Turn(" ".join(checked), calls)
        _ok(results, calls)
        checked = []
        for label, result in zip(again, results[1:]):
            label["id"] = result["created"][0]
        pending = again
    else:
        raise NotCovered("the match line labels did not settle")
    boxes: Dict[str, dict] = {name: {} for name in names}
    for label in labels:
        boxes[label["sheet"]][label["id"]] = label["box"]
    return {"labels": boxes, "state": state, "carry": " ".join(checked), "half": half}


# ------------------------------------------------------------ clearing the lettering

_OTHER_SIDE = {"left": "right", "right": "left"}
_PAPER_WORDS = {"text": "the note", "table": "the table", "blockref": "the symbol"}


def _named(request: str, names: Sequence[str]) -> str:
    """The line the request is about, of the ones the design holds: the one it
    names first (``BASE:ALIGN-1`` is named by ``ALIGN-1``), else the first.  A name is
    looked for as a word of its own first: a design file's second line called ``AN`` is
    not named by "ANSI D" (the bulk dial's sheets, ``tasks.bulk``)."""
    found = []
    for i, n in enumerate(names):
        hit = re.search(r"(?<![A-Za-z0-9_-])" + re.escape(n.rsplit(":", 1)[-1])
                        + r"(?![A-Za-z0-9_-])", request)
        if hit:
            found.append((hit.start(), i))
    if not found:
        found = [(request.find(n.rsplit(":", 1)[-1]), i) for i, n in enumerate(names)]
    found = [(at, i) for at, i in found if at >= 0]
    return names[min(found)[1]] if found else names[0]


def _clear(name: str, sheet: dict, alignment: str, groups: Dict[str, List[str]], anno: str,
           view: dict, others: Sequence[str],
           lead: str) -> Generator[Turn, List[dict], dict]:
    """See what the new lettering fell on, on a sheet that showed other
    lettering before it, and set again whatever sits on any of it.

    ``groups`` is what the drafter lettered: each new entity's id with the ids
    that go when it does (a curve number takes its bubble and leader along).
    The engine sets one line's lettering clear of itself and of nothing else,
    so each new label is compared with the lettering that is not its line's.
    The listing of what a sheet shows gives each text the four corners of its
    lettering on the paper (``paper_corners``, the footprint legibility is
    judged by); a table or a symbol on the paper is its box.  Two footprints
    are rectangles, and two rectangles are apart when the places of their
    corners along some side of one of them do not overlap.  So:

    1. *The boxes round the corners*, along the paper's own axes: two
       footprints whose boxes do not meet do not meet.  A footprint that
       stands square to the paper (a note, a table) is its own box, so its
       sides are settled here.
    2. *Along each side* of a footprint that is turned.  A side runs from one
       corner to the next, and a point's place along it is the point's x times
       the run in x plus its y times the run in y: products and sums, nothing
       else.  The footprint the side is of spans the places of the side's two
       ends; the other spans the places of its four corners.
    3. *Apart along no side*: the two meet.

    Nothing is asked of the engine for it: the corners came with the
    listing, and the engine names no collision.  A label that meets something
    is deleted and placed again by the same labeler on the other side of its
    line, then further off by multiples of its text height (``CLEAR_MOVES``),
    read back with its corners and compared again, now with its own line's
    lettering on that side as well.  Returns ``{"carry", "done"}``.

    On a sheet whose state came back cut (``sheet["cut"]``: a sheet at a real
    one's size, ``tasks.bulk``) the whole of what it shows is not read: a list
    of every text on it runs to hundreds of rows.  The drafter asks by line and
    then by place instead.  First its own line's lettering, the new labels among
    it, by the line's anchor.  Then the box the new labels take on the paper, a
    quarter inch added all round, its corners taken back to the model by the
    engine, and only what lies in that box: what is drawn on the paper there,
    and the text the sheet shows from the model there.  A label set again on such a
    sheet may land on paper that was not searched (a base file's text stands inside the
    line's lettering on a bulked sheet): the box it now takes is searched the same way
    before it is compared."""
    shown_q = {"visible_on": name, "type": "text", "detail": "full", "limit": FULL_ROWS}
    paper_q = {"space": name, "type": ["text", "table", "blockref"], "detail": "full",
               "limit": FULL_ROWS}
    wide = bool(sheet.get("cut"))

    def rest(more: List[tuple]) -> Generator[Turn, List[dict], None]:
        """Read on through each list that runs past its first rows."""
        while any(m for _query, _rows, m in more):
            ask = [(query, rows, m) for query, rows, m in more if m]
            calls = [_q("find_entities", **query, start=m["start"]) for query, _rows, m in ask]
            results = yield Turn("The list runs on: read the rest of it.", calls)
            _ok(results, calls)
            more[:] = []
            for (query, rows, _m), result in zip(ask, results):
                rows.extend(result["entities"])
                more.append((query, rows, result.get("more")))

    #: the boxes of paper searched so far on a sheet too large to read whole
    searched: List[list] = []

    def look(rows: Sequence[dict], head: str,
             tail: str) -> Generator[Turn, List[dict], tuple]:
        """Search the paper ``rows`` take, a quarter inch added all round: ``(what is
        on the paper there, the text the sheet shows from the model there, the box)``."""
        px = [float(_n4(c[0])) for row in rows for c in row["paper_corners"]]
        py = [float(_n4(c[1])) for row in rows for c in row["paper_corners"]]
        on_paper = (min(px), min(py), max(px), max(py))
        if min(on_paper[:2]) < MARGIN_IN:
            raise NotCovered(f"the new lettering reaches the edge of {name}")
        box = [round(on_paper[0] - MARGIN_IN, 4), round(on_paper[1] - MARGIN_IN, 4),
               round(on_paper[2] + MARGIN_IN, 4), round(on_paper[3] + MARGIN_IN, 4)]
        calls = [_q("sheet_to_model", sheet=name, point=[x, y])
                 for x, y in ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]),
                              (box[0], box[3]))]
        results = yield Turn(
            f"{head} from x {_n4(on_paper[0])} to "
            f"{_n4(on_paper[2])} and y {_n4(on_paper[1])} to {_n4(on_paper[3])}. A quarter "
            f"inch round that: {_n4(on_paper[0])} - {_n(MARGIN_IN)} = {_n4(box[0])}, "
            f"{_n4(on_paper[1])} - {_n(MARGIN_IN)} = {_n4(box[1])}, {_n4(on_paper[2])} + "
            f"{_n(MARGIN_IN)} = {_n4(box[2])} and {_n4(on_paper[3])} + {_n(MARGIN_IN)} = "
            f"{_n4(box[3])}. {tail} Take its "
            "corners back to the model, to ask what the sheet shows there.", calls)
        _ok(results, calls)
        pts = [r["point"] for r in results]
        bounds = [min(q[0] for q in pts), min(q[1] for q in pts),
                  max(q[0] for q in pts), max(q[1] for q in pts)]
        # (a text is listed with its corners; a table or a symbol is its box, which only
        # the full row carries, and there are few of those)
        here_q = {"space": name, "type": "text", "bounds": box}
        boxed_q = {"space": name, "type": ["table", "blockref"], "detail": "full",
                   "limit": FULL_ROWS, "bounds": box}
        near_q = {"visible_on": name, "type": "text", "bounds": bounds}
        calls = [_q("find_entities", **here_q), _q("find_entities", **boxed_q),
                 _q("find_entities", **near_q)]
        results = yield Turn(
            ("The view is turned, so the corners span a wider box in the model than on the "
             "paper. " if view else "")
            + f"Ask only for what lies in the box: the lettering on the paper of {name} there, "
            f"any table or symbol there, and the text {name} shows from the model there.", calls)
        _ok(results, calls)
        on: List[dict] = list(results[0]["entities"])
        boxed: List[dict] = list(results[1]["entities"])
        by: List[dict] = list(results[2]["entities"])
        yield from rest([(here_q, on, results[0].get("more")),
                         (boxed_q, boxed, results[1].get("more")),
                         (near_q, by, results[2].get("more"))])
        return on + boxed, by, box

    if wide:
        # this line's own lettering, by its anchor: a row as listed has the corners of
        # its lettering on the paper and its anchor, which is all the comparison reads
        own_q = {"visible_on": name, "type": "text", "anchor": {"alignment": alignment}}
        calls = [_q("find_entities", **own_q)]
        results = yield Turn(
            (lead + " " if lead else "")
            + f"{name} carries too much to read whole, and the engine sets a line's lettering "
            "clear of itself, not of anything else. So see what the new labels fell on by "
            f"asking narrowly. First {alignment}'s own lettering as {name} shows it, the new "
            "labels among it, each with the corners of its lettering on the paper.", calls)
        _ok(results, calls)
        shown: List[dict] = list(results[0]["entities"])
        yield from rest([(own_q, shown, results[0].get("more"))])
        new = [row for row in shown if row["id"] in groups]
        if not new:
            raise NotCovered(f"{name} shows none of the new lettering")
        paper, near, box = yield from look(
            new, f"{_s(len(new), 'new label').capitalize()} among {_s(len(shown), 'text')} of "
                 f"{alignment}'s. On the paper their corners run",
            "Whatever a new label could sit on lies in that box.")
        searched.append(box)
        have = {row["id"] for row in shown}
        shown += [row for row in near if row["id"] not in have]
    else:
        calls = [_q("find_entities", **shown_q), _q("find_entities", **paper_q)]
        there = ([f"the design holds {_and(list(others))} as well"] if others else []) + (
            ["the paper carries lettering of its own"]
            if any(e.get("type") == "text" and not (e.get("anchor") or {}).get("kind")
                   for e in (sheet.get("entities") or {}).values()) else [])
        results = yield Turn(
            (lead + " " if lead else "")
            + f"{alignment} is not alone on {name}: {_and(there)}. The engine sets a line's "
            "lettering clear of itself, not of anything else, so read back where the new labels "
            f"fell: every text {name} shows from the model, each with the corners of its "
            "lettering on the paper, and what is drawn on the paper.", calls)
        _ok(results, calls)
        shown = list(results[0]["entities"])
        paper = list(results[1]["entities"])
        yield from rest([(shown_q, shown, results[0].get("more")),
                         (paper_q, paper, results[1].get("more"))])
    by_id: Dict[str, dict] = {row["id"]: row for row in shown}
    paper_rows = {id(row) for row in paper}
    mine = [row["id"] for row in shown if row["id"] in groups]
    if not mine:
        raise NotCovered(f"{name} shows none of the new lettering")
    #: where each new label was first set, and how often it has been set again; a label
    #: set again is known by the id it was first set under
    first = {i: (by_id[i]["anchor"]["side"], float(by_id[i]["anchor"]["label_offset"]))
             for i in mine}
    tried = {i: 0 for i in mine}
    root: Dict[str, str] = {i: i for i in mine}
    moved: set = set()
    #: the comparisons worked out since the last turn, said at the head of the next one
    said: List[str] = []

    def line_of(row: dict) -> Optional[str]:
        on = (row.get("anchor") or {}).get("alignment")
        if not on:
            return None
        return f"{row['reference']}:{on}" if row.get("reference") and ":" not in on else on

    def same_line(row: dict) -> bool:
        return line_of(row) == alignment

    def what(row: dict) -> str:
        anchor = row.get("anchor") or {}
        word = _LABEL_WORDS.get(anchor.get("kind"), "the label")
        return f"{word} at {anchor.get('ref')}, {row['id']}"

    def whose(row: dict) -> str:
        if id(row) in paper_rows:
            return f"{_PAPER_WORDS.get(row['type'], 'the item')} {row['id']} on the paper"
        anchor = row.get("anchor") or {}
        if same_line(row):
            return what(row)
        on = line_of(row)
        return (f"{on}'s {_LABEL_WORDS.get(anchor.get('kind'), 'the lettering')[4:]} "
                f"{row['id']}" if on else f"the text {row['id']} in the model")

    def n4(value: float) -> str:
        """A number in the comparison as written: to the ten-thousandth, the
        corners' own places (a footprint's short side is a tenth of an inch, so
        thousandths would round a shallow overlap away)."""
        return f"{float(value):.4f}".rstrip("0").rstrip(".")

    def r4(value: float) -> float:
        return float(n4(value))

    def footprint(row: dict) -> List[List[float]]:
        """A row's footprint on the paper as written: a text's corners, or the box of
        a table or a symbol."""
        if row.get("paper_corners"):
            out = [[r4(x), r4(y)] for x, y in row["paper_corners"]]
        else:
            x0, y0, x1, y1 = (r4(v) for v in row["bbox"])
            out = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        if any(v < 0 for c in out for v in c):
            raise NotCovered(f"{row['id']} reaches past the edge of {name}")
        return out

    def box_of(q: Sequence[Sequence[float]]) -> tuple:
        return (min(c[0] for c in q), min(c[1] for c in q),
                max(c[0] for c in q), max(c[1] for c in q))

    def box_words(box: Sequence[float]) -> str:
        return f"x {n4(box[0])} to {n4(box[2])} and y {n4(box[1])} to {n4(box[3])}"

    def square(q: Sequence[Sequence[float]]) -> bool:
        """A footprint that stands square to the paper: its own box."""
        return len({c[0] for c in q}) <= 2 and len({c[1] for c in q}) <= 2

    def point(c: Sequence[float]) -> str:
        return f"({n4(c[0])}, {n4(c[1])})"

    def place(c: Sequence[float], dx: float, dy: float) -> tuple:
        """A point's place along a run of ``dx`` in x and ``dy`` in y: ``(the
        place, the sum)``, the products of like sign added and the rest taken off."""
        terms = [(v * d, f"{n4(v)} * {n4(abs(d))}") for v, d in ((c[0], dx), (c[1], dy)) if d]
        value = r4(sum(t for t, _w in terms))
        plus = [w for t, w in terms if t >= 0]
        minus = [w for t, w in terms if t < 0]
        words = " + ".join(plus) if plus else "0"
        if minus:
            words += " - " + " - ".join(minus)
        return value, f"{words} = {n4(value)}"

    def side(p0: Sequence[float], p1: Sequence[float], q_words: str,
             other: Sequence[Sequence[float]], other_words: str) -> tuple:
        """Compare two footprints along the side of the first from ``p0`` to
        ``p1``: ``(apart, the words)``."""
        dx, dy = r4(p1[0] - p0[0]), r4(p1[1] - p0[1])
        if not dx and not dy:
            return False, ""
        a0, w0 = place(p0, dx, dy)
        a1, w1 = place(p1, dx, dy)
        lo, hi = min(a0, a1), max(a0, a1)
        at = [place(c, dx, dy) for c in other]
        o_lo, o_hi = min(v for v, _w in at), max(v for v, _w in at)
        apart = hi <= o_lo or o_hi <= lo
        return apart, (
            f"along the side of {q_words} from {point(p0)} to {point(p1)}, a run of "
            f"{n4(p1[0])} - {n4(p0[0])} = {n4(dx)} in x and {n4(p1[1])} - {n4(p0[1])} = "
            f"{n4(dy)} in y, it spans {w0} to {w1}, and the corners of {other_words} fall at "
            + ", ".join(w for _v, w in at)
            + (": clear of it" if apart else ": within its span"))

    def compare(i: str, other: dict) -> Optional[str]:
        """None when label ``i`` and ``other`` are apart (said when it took more
        than their boxes), else the words for how they meet."""
        row = by_id[i]
        a, b = footprint(row), footprint(other)
        ba, bb = box_of(a), box_of(b)
        if not _meet(ba, bb):
            return None
        head = (f"{what(row)[0].upper() + what(row)[1:]} takes {box_words(ba)} on the paper "
                f"and {whose(other)} takes {box_words(bb)}: the boxes round their corners meet")
        steps = []
        for q, r, qw, rw in ((a, b, what(row), whose(other)), (b, a, whose(other), what(row))):
            if square(q):
                continue
            for p0, p1 in ((q[0], q[1]), (q[0], q[3])):
                apart, words = side(p0, p1, qw, r, rw)
                if not words:
                    continue
                steps.append(words)
                if apart:
                    said.append(f"{head}; {'; '.join(steps)}. The two do not meet.")
                    return None
        if not steps:
            return (f"{head}, and both stand square to the paper, so the boxes are the "
                    "footprints and the two meet")
        return f"{head}; {'; '.join(steps)}: apart along no side, so the two meet"

    def partners(i: str) -> List[dict]:
        """What label ``i`` is compared with: the lettering in the model that is not
        its line's, and what is on the paper."""
        row, out = by_id[i], []
        for other in by_id.values():
            if other["id"] == i:
                continue
            if same_line(other):
                # one line's lettering as its labelers set it is clear of itself; a label
                # set again is kept from its line's lettering across the line by the line
                if i not in moved and other["id"] not in moved:
                    continue
                if (other.get("anchor") or {}).get("side") != row["anchor"]["side"]:
                    continue
            out.append(other)
        return out + paper

    def check(ids: Sequence[str]) -> Dict[str, str]:
        """Compare each of ``ids`` with what it could sit on: ``{id: why it has to
        move}``, the comparisons said in ``said``."""
        bad: Dict[str, str] = {}
        closer = False
        before = len(said)
        for i in ids:
            for other in partners(i):
                closer = closer or bool(_meet(box_of(footprint(by_id[i])),
                                              box_of(footprint(other))))
                why = compare(i, other)
                if why:
                    bad[i] = why
                    break
        said.insert(before, (
            f"Every pair on {name} is apart by the boxes round their corners, but where those "
            "meet; there the two are compared along their sides." if closer else
            f"No box round the corners of the new lettering meets another's on {name}."))
        return bad

    bad = check(mine)
    count = 0
    while bad:
        short = [i for i in bad if "entity" not in by_id[i]]
        if short:
            # a row of the narrow list has a label's corners and anchor, not its height,
            # and a label is set further off by multiples of that
            calls = [_q("get_entity", id=i) for i in short]
            one = len(short) == 1
            results = yield Turn(
                " ".join(said) + (" " if said else "")
                + " ".join(f"{why[0].upper() + why[1:]}." for why in bad.values())
                + f" {'It has' if len(bad) == 1 else 'They have'} to be set again, by "
                f"{'its' if one else 'their'} own text height, which the list did not give: "
                f"read {'it' if one else 'them'}.", calls)
            _ok(results, calls)
            del said[:]
            for i, result in zip(short, results):
                by_id[i]["entity"] = result["entity"]
        calls, says, placing = [], list(said), []
        del said[:]
        for i, why in bad.items():
            row, anchor = by_id[i], by_id[i]["anchor"]
            k = tried[root[i]]
            if k >= len(CLEAR_MOVES):
                raise NotCovered(f"{what(row)} will not clear on either side of its line")
            tried[root[i]] = k + 1
            side0, off0 = first[root[i]]
            across, times = CLEAR_MOVES[k]
            to = _OTHER_SIDE[side0] if across else side0
            h = _r(row["entity"]["height"])
            off = round(_r(off0) + h * times, 3)
            where = (f"on the other side of the line, its {to}" if across
                     else f"back on its own side, the {to}")
            far = (f"the same {_n(off0)} ft off it" if not times else
                   f"further off it by {_TIMES[times]} its height: "
                   f"{_n(off0)} + {_n(h)} * {times} = {_n(off)} ft")
            says.append(f"{why[0].upper() + why[1:]}. Delete it and set the same label again "
                        f"{where}, {far}.")
            params = {"space": "model", "alignment": alignment, "anchor": anchor["ref"],
                      "kind": anchor["kind"], "side": to, "label_offset": off, "layer": anno,
                      **view}
            if anchor["kind"] in ("station", "pc", "pt", "pcc", "prc"):
                params["content"] = row["content"]  # the stationing's own lettering of it
            calls += [_q("delete_entities", ids=list(groups[i])), _q("place_label", **params)]
            placing.append(i)
        results = yield Turn(" ".join(says), calls)
        _ok(results, calls)
        again: Dict[str, List[str]] = {}
        for n, i in enumerate(placing):
            made = list(results[2 * n + 1]["created"])
            for j in made:
                groups[j] = made
            again[i] = made
            del by_id[i]
            moved.discard(i)
        placed = [call.params for call in calls if call.name == "place_label"]
        calls = [_q("find_entities", visible_on=name, type="text", detail="full",
                    anchor={"alignment": alignment,
                            "ref": sorted({q["anchor"] for q in placed}),
                            "kind": sorted({q["kind"] for q in placed})},
                    limit=FULL_ROWS)]
        results = yield Turn(
            f"Read {'it' if len(placing) == 1 else 'them'} back where "
            f"{'it now sits' if len(placing) == 1 else 'they now sit'}, with "
            f"{'its' if len(placing) == 1 else 'their'} corners.", calls)
        _ok(results, calls)
        fresh = []
        for i, made in again.items():
            row = next((r for r in results[0]["entities"] if r["id"] in made), None)
            if row is None:
                raise NotCovered(f"{name} does not show a label that was set again")
            by_id[row["id"]] = row
            root[row["id"]] = root.pop(i)
            moved.add(row["id"])
            fresh.append(row["id"])
        count += len(placing)
        if wide:
            # where a label now sits may not be paper that was searched: search it too
            rows = [by_id[j] for j in fresh]
            cs = [(r4(c[0]), r4(c[1])) for row in rows for c in row["paper_corners"]]
            if not all(any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in searched)
                       for x, y in cs):
                one = len(rows) == 1
                on, by, box = yield from look(
                    rows, f"Where {'it now sits' if one else 'they now sit'} is not all paper "
                          f"that was searched. {'Its' if one else 'Their'} corners run",
                    f"Whatever {'it' if one else 'they'} could sit on now lies in that box.")
                searched.append(box)
                have = {row["id"] for row in paper}
                for row in on:
                    if row["id"] not in have:
                        paper.append(row)
                        paper_rows.add(id(row))
                for row in by:
                    by_id.setdefault(row["id"], row)
        bad = check(fresh)
    tail = " ".join(said)
    if count:
        carry = ((tail + " " if tail else "")
                 + f"{_s(len(moved), 'label')} set again, and nothing {alignment} was given "
                 "now sits on other lettering.")
        done = (f"checked the new lettering against what {name} already showed and set "
                f"{_s(len(moved), 'label')} again clear of it")
    else:
        carry = ((tail + " " if tail else "")
                 + f"Nothing {alignment} was given sits on other lettering.")
        done = f"checked the new lettering against what {name} already showed: nothing meets"
    return {"carry": carry, "done": done}


# ------------------------------------------------------------ a revised design

#: what of a line's own is not lettering: its drawn centerline and offsets, which the
#: designer redraws with the design
LINEWORK_KINDS = ("element", "offset")
#: how far off the revised line an old tick may lie and still mark a point of it (ft)
ON_LINE_FT = 0.01


def _station_text(raw: float) -> str:
    """A station to the hundredth, as the office letters it (``147+65.32``)."""
    cents = int(round(float(raw) * 100.0))
    whole, rest = divmod(cents, 10000)
    return f"{whole}+{rest // 100:02d}.{rest % 100:02d}"


def _revise(revision: dict, alignment: str, sheet_name: str, sheet: dict,
            curves: Sequence[dict], lead: str) -> Generator[Turn, List[dict], dict]:
    """Take off what was lettered from the line before the designer changed it,
    and restation the notes on the sheet that cite it, before the line is
    lettered again.

    Every label the engine letters records the station it stands at, so a
    restation leaves all of them behind, the bearings and curve numbers too,
    though they read the same; the curve data holds no station, so a
    restation leaves the table standing, and a change of the geometry does not.
    A note citing a station is restationed.  A restation moves every station of
    the line by the same amount, the new begin station less the old, so a note
    moves by that.  A change of the geometry moves stations by amounts that
    depend on where they are, so there the note is restationed from the old
    lettering itself: the tick at the whole station before the note was
    lettered from the old design, so it still marks where that old station was.
    Where it lies on the revised line, ``xy_to_station`` reads its new station,
    and the note is as far past it as it was.  That holds only along a stretch
    the change left in place, so the tick has to lie on the revised line and no
    curve point of the revised line may fall between it and the note (on the
    redline pilots, 2026-11-12, the method agrees with the pilots' own grader on
    all 20 cited stations that have a tick).  Returns ``{"deleted", "done"}``."""
    kind = revision["kind"]
    geometry = kind != "station"
    query = {"anchor": {"alignment": alignment}, "include_references": False, "limit": 50}
    calls = [_q("find_entities", **query)]
    if geometry:
        calls.append(_q("find_entities", space=sheet_name, type="table",
                        anchor={"alignment": alignment}))
    if geometry:
        why = (f"The designer has changed the geometry under {sheet_name}: {revision['said']}. "
               "That moves the curve points and every station after them and changes the "
               f"curve data, so everything lettered from {alignment} before the change is out "
               f"of date, the curve table too.")
    else:
        why = (f"The designer has restationed {alignment}, its geometry held. Every label the "
               "engine letters records the station it stands at, the bearings and curve numbers "
               "too, so all of it is out of date though some of it reads the same. The curve "
               "data holds no station, so the table stands.")
    results = yield Turn(
        (lead + " " if lead else "") + why + f" Find what was lettered from it: everything the "
        f"model holds anchored to {alignment}" + (f", and its curve table on {sheet_name}."
                                                   if geometry else "."), calls)
    _ok(results, calls)
    rows = list(results[0]["entities"])
    tables = [row["id"] for row in results[1]["entities"]] if geometry else []
    more = results[0].get("more")
    while more:
        calls = [_q("find_entities", **query, start=more["start"])]
        results = yield Turn("The list runs on: read the rest of it.", calls)
        _ok(results, calls)
        rows += results[0]["entities"]
        more = results[0].get("more")
    drawn = [row for row in rows if row["anchor"].get("kind") in LINEWORK_KINDS]
    rows = [row for row in rows if row["anchor"].get("kind") not in LINEWORK_KINDS]
    if not rows:
        raise NotCovered(f"nothing in the model is lettered from {alignment}")
    ticks = {round(float(row["anchor"]["station"]), 2): row for row in rows
             if row["anchor"]["kind"] == "tick"}
    # -- the notes on the paper that cite a station of the line
    notes = []
    for eid, e in (sheet.get("entities") or {}).items():
        content = str(e.get("content") or "")
        if e.get("type") != "text" or (e.get("anchor") or {}).get("kind"):
            continue
        cited = _STATION.findall(content)
        if len(cited) != 1:
            continue
        written = f"{cited[0][0]}+{cited[0][1]}"
        at = numbers_in(written)[0]
        whole = 100.0 * math.floor(at / 100.0)
        tick = ticks.get(round(whole, 2))
        if tick is None and geometry:
            raise NotCovered(f"no tick of the old lettering at the whole station before {written}")
        notes.append({"id": eid, "content": content, "written": written, "at": at,
                      "whole": whole, "tick": tick})
    changes: List[ToolCall] = []
    says: List[str] = []
    if notes and not geometry:
        # every station moves by the same amount: the new begin station less the old
        begins, began = numbers_in(revision["begins"])[0], numbers_in(revision["began"])[0]
        by = round(abs(begins - began), 3)
        ahead = begins > began
        says.append(
            f"{_s(len(notes), 'note').capitalize()} on {sheet_name} "
            f"cite{'s' if len(notes) == 1 else ''} a station of {alignment}: "
            + _and([f"{n['id']}, \"{n['content']}\"" for n in notes])
            + f". The line now begins at {revision['begins']} and began at {revision['began']}: "
            + (f"{_n(begins)} - {_n(began)} = {_n(by)}" if ahead
               else f"{_n(began)} - {_n(begins)} = {_n(by)}")
            + f" ft {'ahead' if ahead else 'back'}, the same for every station of it.")
        for n in notes:
            now = round(n["at"] + by if ahead else n["at"] - by, 3)
            text = n["content"].replace(n["written"], _station_text(now))
            says.append(f"{n['id']} cites {n['written']}: {_n(n['at'])} "
                        f"{'+' if ahead else '-'} {_n(by)} = {_n(now)}; restation it to that, "
                        f"to the hundredth.")
            changes.append(_q("modify_entity", id=n["id"], changes={"content": text}))
    elif notes:
        calls = [_q("xy_to_station", alignment=alignment, point=list(n["tick"]["point"]))
                 for n in notes]
        results = yield Turn(
            f"{_s(len(notes), 'note').capitalize()} on {sheet_name} "
            f"cite{'s' if len(notes) == 1 else ''} a station of {alignment}: "
            + _and([f"{n['id']}, \"{n['content']}\"" for n in notes])
            + ". The ticks were lettered from the old design, so each still marks where an old "
            "whole station was. Take the tick at the whole station before each note to the "
            "revised line.", calls)
        _ok(results, calls)
        stops = sorted(float(c[key]) for c in curves for key in ("pc_station", "pt_station"))
        for n, r in zip(notes, results):
            off = float(r.get("offset") or 0.0)
            if abs(off) > ON_LINE_FT:
                raise NotCovered(f"the tick before {n['written']} is not on the revised line")
            past = round(n["at"] - n["whole"], 3)
            now = round(_r(r["station"]) + past, 3)
            if geometry and any(min(_r(r["station"]), now) < c < max(_r(r["station"]), now)
                                for c in stops):
                raise NotCovered(f"a curve point of the revised line falls between the tick and "
                                 f"{n['written']}")
            text = n["content"].replace(n["written"], _station_text(now))
            work = (f"{n['id']} cites {n['written']}: {_n(n['at'])} - {_n(n['whole'])} = "
                    f"{_n(past)} ft past the tick at {n['tick']['anchor']['ref']}, "
                    f"{n['tick']['id']}. That tick lies on the revised line ({_n(abs(off))} ft "
                    f"off it) at {_n(r['station'])}, so the same point of the line is "
                    f"{_n(r['station'])} + {_n(past)} = {_n(now)}")
            if text == n["content"]:
                says.append(work + f", which is {n['written']} still: it stays as it reads.")
            else:
                says.append(work + ": restation it to that, to the hundredth.")
                changes.append(_q("modify_entity", id=n["id"], changes={"content": text}))
    ids = [row["id"] for row in rows] + tables
    calls = [_q("delete_entities", ids=ids)] + changes
    keep = (" The centerline drawn from it was redrawn with the design, so it stays."
            if drawn else "")
    results = yield Turn(
        " ".join(says + ["Take off everything lettered from the old design"
                         + (f" and the curve table {tables[0]}" if tables else "")
                         + (", and restation the note" + ("s" if len(changes) > 1 else "")
                            if changes else "")
                         + f"; {alignment} is lettered again below." + keep]), calls)
    _ok(results, calls)
    kept_notes = [n["id"] for n in notes if n["id"] not in {c.params["id"] for c in changes}]
    done = (f"took off what was lettered from {alignment} before the designer's change"
            + (f" and restationed the note{'s' if len(changes) > 1 else ''} citing it ("
               + _and([c.params["id"] for c in changes]) + ")" if changes else "")
            + (f"; {_and(kept_notes)} kept {'its' if len(kept_notes) == 1 else 'their'} "
               f"station" if kept_notes else ""))
    return {"deleted": ids, "done": done}


def _revise_own(revision: dict, alignment: str, sheet_name: str, sheet: dict,
                lead: str) -> Generator[Turn, List[dict], dict]:
    """Make the designer's change to a line whose design lives in this file, and
    restation the notes on the sheet that cite it.

    ``modify_alignment`` changes a document's own line, redraws its centerline
    (``redraw``) and brings every label lettered from it along, so nothing is
    taken off or lettered again; ``update_labels`` afterwards checks that
    nothing was left out of step.  A note is restationed from its own point:
    where its station lies on the line before the change, and where that point
    falls on the line after it.  A PI moved along its back tangent is worked out
    from ``measure`` of that leg: each coordinate plus the leg's difference over
    its length times the move.  Returns ``{"done"}``."""
    kind = revision["kind"]
    notes = []
    for eid, e in (sheet.get("entities") or {}).items():
        content = str(e.get("content") or "")
        if e.get("type") != "text" or (e.get("anchor") or {}).get("kind"):
            continue
        cited = _STATION.findall(content)
        if len(cited) == 1:
            notes.append({"id": eid, "content": content,
                          "written": f"{cited[0][0]}+{cited[0][1]}"})
    calls = [_q("get_design_data", kind="alignments", alignment=alignment)]
    calls += [_q("station_to_xy", alignment=alignment, station=n["written"]) for n in notes]
    results = yield Turn(
        (lead + " " if lead else "")
        + f"{alignment}'s design lives in this file, so the designer's change is made here: "
        f"{revision['said']}. modify_alignment changes a document's own line, redraws its "
        "centerline and brings every label lettered from it along. Read its PIs as they stand"
        + (", and, while the line is still the old one, where the station each note on "
           f"{sheet_name} cites lies on it: " + _and([f"{n['id']}, \"{n['content']}\""
                                                     for n in notes]) + "." if notes else "."),
        calls)
    _ok(results, calls)
    line = results[0]["rows"][0]
    pis = line["pis"]
    rows = [list(p["point"]) + ([p["radius"]] if p.get("radius") else []) for p in pis]
    curves = [i for i, r in enumerate(rows) if len(r) > 2]
    points = [list(r["point"]) for r in results[1:]]
    says: List[str] = []
    if kind == "station":
        changes = {"begin_station": revision["begins"]}
        says.append(f"The geometry holds; only the stationing changes: it begins at "
                    f"{revision['begins']}.")
    elif kind == "radius":
        k = curves[revision["curve"] - 1]
        rows[k] = rows[k][:2] + [revision["radius"]]
        changes = {"pis": rows}
        says.append(f"Every PI holds its place; curve {revision['curve']}'s PI, the row at "
                    f"{_n(rows[k][0])}, {_n(rows[k][1])}, takes R = {_n(revision['radius'])}.")
    else:
        k = curves[revision["curve"] - 1]
        back, pi = rows[k - 1], rows[k]
        calls = [_q("measure", **{"from": back[:2], "to": pi[:2]})]
        results = yield Turn(
            f"Curve {revision['curve']}'s PI is at {_n(pi[0])}, {_n(pi[1])}, and its back "
            f"tangent runs from the PI before it, at {_n(back[0])}, {_n(back[1])}. Measure that "
            "leg for its length and how far it runs each way.", calls)
        _ok(results, calls)
        leg = results[0]
        dist = _r(leg["distance"])
        by = _r(revision["by"])
        signed = by if revision["ahead"] else -by
        moved, work = [], []
        for axis, d in (("x", leg["dx"]), ("y", leg["dy"])):
            a, b = _r(pi[0 if axis == "x" else 1]), abs(_r(d))
            ahead = _r(d) * signed >= 0
            value = _r(a + b / dist * by if ahead else a - b / dist * by)
            moved.append(value)
            work.append(f"{_n(a)} {'+' if ahead else '-'} {_n(b)} / {_n(dist)} * {_n(by)} = "
                        f"{_n(value)}")
        rows[k] = moved + rows[k][2:]
        changes = {"pis": rows}
        says.append(f"The leg is {_n(dist)} ft long. Moving the PI {_n(by)} ft "
                    f"{'ahead' if revision['ahead'] else 'back'} along it takes each coordinate "
                    f"that far along the leg: {work[0]} and {work[1]}. Its radius and every "
                    "other PI hold.")
    calls = [_q("modify_alignment", name=alignment, changes=changes, redraw=True)]
    results = yield Turn(" ".join(says + [f"Change {alignment}, its centerline redrawn."]),
                         calls)
    _ok(results, calls)
    followed = results[0].get("message") or ""
    calls = [_q("update_labels", alignment=alignment)]
    calls += [_q("xy_to_station", alignment=alignment, point=p) for p in points]
    results = yield Turn(
        f"The labels came along with the design ({followed.split('labels: ')[-1]}). Check that "
        "none was left out of step"
        + (", and read where each note's point now falls on the revised line." if notes
           else "."), calls)
    _ok(results, calls)
    if "already in step" not in str(results[0].get("message") or ""):
        raise NotCovered(f"update_labels found labels of {alignment} out of step")
    changed, says = [], []
    for n, r in zip(notes, results[1:]):
        if abs(float(r.get("offset") or 0.0)) > ON_LINE_FT:
            raise NotCovered(f"the point {n['written']} cites is off the revised line")
        text = n["content"].replace(n["written"], _station_text(r["station"]))
        if text == n["content"]:
            says.append(f"{n['id']}'s point is at {_n(r['station'])}: it stays as it reads.")
        else:
            says.append(f"{n['id']}'s point is now at {_n(r['station'])}: restation it to that, "
                        "to the hundredth.")
            changed.append(_q("modify_entity", id=n["id"], changes={"content": text}))
    if changed:
        results = yield Turn(" ".join(says), changed)
        _ok(results, changed)
        says = []
    done = (f"made the designer's change to {alignment} in this file's design, its centerline "
            "redrawn and its lettering brought along"
            + (f", and restationed the note{'s' if len(changed) > 1 else ''} citing it ("
               + _and([c.params["id"] for c in changed]) + ")" if changed else ""))
    return {"done": done, "carry": " ".join(says)}


def _revise_base(revision: dict, alignment: str, sheet_name: str, sheet: dict,
                 document: Optional[str], kinds: Sequence[str],
                 lead: str) -> Generator[Turn, List[dict], dict]:
    """Make the designer's change where the design lives, in the base drawing
    the sheet file references, then take off what the sheet file lettered from
    the old design and restation its notes, before the line is lettered again.

    The line is ``REF:NAME`` here and ``NAME`` in its own file.  While it is
    still the old one, ``station_to_xy`` reads where each note's station lies,
    and ``list_references`` gives the base drawing's file.  ``open_document``
    switches the tools to that file: ``modify_alignment`` changes the line
    there and redraws its centerline (a PI moved along its back tangent is
    worked out from ``measure`` of that leg, as in ``_revise_own``); the
    pavement edges drawn from it are redrawn by ``draw_offset`` with
    ``replace``, at the offsets and on the level they were found on.  Back in
    the handed file (``document``, the name ``get_document_state`` gave),
    ``reload_references`` reads the base drawing again; then the revised line's
    ``kinds`` of design data are read through the reference, each note's point
    is taken to the revised line, and everything the model holds anchored to
    the line comes off (the curve table too, on a change of the geometry).
    Returns ``{"deleted", "done", "rows"}``."""
    kind = revision["kind"]
    geometry = kind != "station"
    ref_name, line = alignment.split(":", 1)
    if not document:
        raise NotCovered("the document names no file of its own to come back to")
    notes = []
    for eid, e in (sheet.get("entities") or {}).items():
        content = str(e.get("content") or "")
        if e.get("type") != "text" or (e.get("anchor") or {}).get("kind"):
            continue
        cited = _STATION.findall(content)
        if len(cited) == 1:
            notes.append({"id": eid, "content": content,
                          "written": f"{cited[0][0]}+{cited[0][1]}"})
    # -- in the sheet file, while the line is the old one
    calls = [_q("list_references")]
    calls += [_q("station_to_xy", alignment=alignment, station=n["written"]) for n in notes]
    change = revision["said"] if geometry else f"{line} {revision['said']}"
    results = yield Turn(
        (lead + " " if lead else "")
        + f"{line}'s design lives in the base drawing attached as {ref_name}, and the change is "
        f"to be made there: {change}. Find that drawing's file"
        + (", and, while the line is still the old one, read where the station each note on "
           f"{sheet_name} cites lies on it: " + _and([f"{n['id']}, \"{n['content']}\""
                                                     for n in notes]) + "." if notes else "."),
        calls)
    _ok(results, calls)
    attached = [r for r in results[0].get("references") or [] if r.get("name") == ref_name]
    if not attached:
        raise NotCovered(f"no reference named {ref_name} is attached")
    base = attached[0]["path"]
    points = [list(r["point"]) for r in results[1:]]
    # -- the base drawing
    calls = [_q("open_document", path=base)]
    results = yield Turn(f"{ref_name} is {base}. Open it: the tools then work on the base "
                         "drawing, and each change is saved to its file.", calls)
    _ok(results, calls)
    if line not in ((results[0].get("state") or {}).get("summary") or {}).get("alignments", []):
        raise NotCovered(f"{base} holds no alignment {line}")
    calls = [_q("get_design_data", kind="alignments", alignment=line)]
    if geometry:
        calls.append(_q("find_entities", anchor={"alignment": line, "kind": "offset"}))
    results = yield Turn(
        f"This is where {line} lives. Read it as it stands"
        + (", and what was drawn from it beside its centerline: a change of the geometry leaves "
           "that linework on the old line until it is drawn again." if geometry else "."), calls)
    _ok(results, calls)
    pis = results[0]["rows"][0]["pis"]
    rows = [list(p["point"]) + ([p["radius"]] if p.get("radius") else []) for p in pis]
    curves = [i for i, r in enumerate(rows) if len(r) > 2]
    #: the offset linework drawn from the line, by the level it is on
    edges: Dict[str, List[float]] = {}
    if geometry:
        if results[1].get("more"):
            raise NotCovered("more offset linework than one read lists")
        for row in results[1]["entities"]:
            offsets = edges.setdefault(row["layer"], [])
            if row["anchor"]["offset"] not in offsets:
                offsets.append(row["anchor"]["offset"])
    says: List[str] = []
    if kind == "station":
        changes = {"begin_station": revision["begins"]}
        says.append(f"The geometry holds; only the stationing changes: it begins at "
                    f"{revision['begins']}. No line moves, so nothing is drawn again.")
    elif kind == "radius":
        k = curves[revision["curve"] - 1]
        rows[k] = rows[k][:2] + [revision["radius"]]
        changes = {"pis": rows}
        says.append(f"Every PI holds its place; curve {revision['curve']}'s PI, the row at "
                    f"{_n(rows[k][0])}, {_n(rows[k][1])}, takes R = {_n(revision['radius'])}.")
    else:
        k = curves[revision["curve"] - 1]
        back, pi = rows[k - 1], rows[k]
        calls = [_q("measure", **{"from": back[:2], "to": pi[:2]})]
        results = yield Turn(
            f"Curve {revision['curve']}'s PI is at {_n(pi[0])}, {_n(pi[1])}, and its back "
            f"tangent runs from the PI before it, at {_n(back[0])}, {_n(back[1])}. Measure that "
            "leg for its length and how far it runs each way.", calls)
        _ok(results, calls)
        leg = results[0]
        dist = _r(leg["distance"])
        by = _r(revision["by"])
        signed = by if revision["ahead"] else -by
        moved, work = [], []
        for axis, d in (("x", leg["dx"]), ("y", leg["dy"])):
            a, b = _r(pi[0 if axis == "x" else 1]), abs(_r(d))
            ahead = _r(d) * signed >= 0
            value = _r(a + b / dist * by if ahead else a - b / dist * by)
            moved.append(value)
            work.append(f"{_n(a)} {'+' if ahead else '-'} {_n(b)} / {_n(dist)} * {_n(by)} = "
                        f"{_n(value)}")
        rows[k] = moved + rows[k][2:]
        changes = {"pis": rows}
        says.append(f"The leg is {_n(dist)} ft long. Moving the PI {_n(by)} ft "
                    f"{'ahead' if revision['ahead'] else 'back'} along it takes each coordinate "
                    f"that far along the leg: {work[0]} and {work[1]}. Its radius and every "
                    "other PI hold.")
    calls = [_q("modify_alignment", name=line, changes=changes, redraw=True)]
    for level, offsets in edges.items():
        calls.append(_q("draw_offset", alignment=line, offsets=sorted(offsets), layer=level,
                        replace=True))
    if edges:
        def sides(offsets: Sequence[float]) -> str:
            return _and([f"{_n(abs(o))} ft {'left' if o < 0 else 'right'}" for o in sorted(offsets)])

        says.append(
            f"Change {line}, its centerline redrawn, and draw again what was offset from it: "
            + _and([f"the lines {sides(offsets)} on {level}" for level, offsets in edges.items()])
            + ", in place of the old.")
    else:
        says.append(f"Change {line}" + (", its centerline redrawn." if geometry else "."))
    results = yield Turn(" ".join(says), calls)
    _ok(results, calls)
    # -- back in the file handed over
    calls = [_q("open_document", path=document)]
    results = yield Turn(
        f"The base drawing holds the revised line"
        + (", its linework drawn to it" if geometry else "") + f". Go back to {document}, the "
        f"sheet file this task handed over: the lettering to bring up to date is there.", calls)
    _ok(results, calls)
    told = any("reload_references" in str(w) for w in results[0].get("warnings") or [])
    query = {"anchor": {"alignment": alignment}, "include_references": False, "limit": 50}
    calls = [_q("reload_references")]
    calls += [_q("get_design_data", kind=k, alignment=alignment) for k in kinds]
    calls += [_q("xy_to_station", alignment=alignment, point=p) for p in points]
    calls.append(_q("find_entities", **query))
    if geometry:
        calls.append(_q("find_entities", space=sheet_name, type="table",
                        anchor={"alignment": alignment}))
    results = yield Turn(
        (f"This file still holds the copy of {ref_name} it read before the change, as the result "
         f"says. " if told else f"This file read {ref_name} before the change. ")
        + f"Reload it, then read the revised line through it"
        + (f": its {_and(list(kinds))}" if kinds else "")
        + (f"{',' if kinds else ':'} where each note's point now falls" if notes else "")
        + f"{',' if kinds or notes else ':'} and what was lettered from the old design, which "
        f"is everything the model holds anchored to {alignment}"
        + (f", and its curve table on {sheet_name}." if geometry else "."), calls)
    _ok(results, calls)
    read = {k: r["rows"] for k, r in zip(kinds, results[1:])}
    at = results[1 + len(kinds):1 + len(kinds) + len(notes)]
    found = results[1 + len(kinds) + len(notes)]
    tables = [row["id"] for row in results[-1]["entities"]] if geometry else []
    lettered = list(found["entities"])
    more = found.get("more")
    while more:
        calls = [_q("find_entities", **query, start=more["start"])]
        results = yield Turn("The list runs on: read the rest of it.", calls)
        _ok(results, calls)
        lettered += results[0]["entities"]
        more = results[0].get("more")
    lettered = [row for row in lettered if row["anchor"].get("kind") not in LINEWORK_KINDS]
    if not lettered:
        raise NotCovered(f"nothing in the model is lettered from {alignment}")
    changed, says = [], []
    for n, r in zip(notes, at):
        if abs(float(r.get("offset") or 0.0)) > ON_LINE_FT:
            raise NotCovered(f"the point {n['written']} cites is off the revised line")
        text = n["content"].replace(n["written"], _station_text(r["station"]))
        if text == n["content"]:
            says.append(f"{n['id']}'s point is at {_n(r['station'])}: it stays as it reads.")
        else:
            says.append(f"{n['id']}'s point is now at {_n(r['station'])}: restation it to that, "
                        "to the hundredth.")
            changed.append(_q("modify_entity", id=n["id"], changes={"content": text}))
    ids = [row["id"] for row in lettered] + tables
    calls = [_q("delete_entities", ids=ids)] + changed
    results = yield Turn(
        " ".join(says + [
            f"The lettering was made from the old line, and a label read through a reference "
            f"does not follow its base drawing. Take all of it off"
            + (f" and the curve table {tables[0]}" if tables else "")
            + (", and restation the note" + ("s" if len(changed) > 1 else "") if changed else "")
            + f"; {alignment} is lettered again below, from the revised design."]), calls)
    _ok(results, calls)
    kept_notes = [n["id"] for n in notes if n["id"] not in {c.params["id"] for c in changed}]
    done = (f"made the designer's change to {line} in the base drawing {base}"
            + (", its centerline" + (" and pavement edges" if edges else "") + " redrawn"
               if geometry else "")
            + f", reloaded {ref_name} in the sheet file, took off what was lettered from "
            f"{alignment} before the change"
            + (f" and restationed the note{'s' if len(changed) > 1 else ''} citing it ("
               + _and([c.params["id"] for c in changed]) + ")" if changed else "")
            + (f"; {_and(kept_notes)} kept {'its' if len(kept_notes) == 1 else 'their'} "
               f"station" if kept_notes else ""))
    return {"deleted": ids, "done": done, "rows": read}


# ------------------------------------------------------------ the width dimensions

#: a width stated at a station on a tangent: ``47+50.00 on T-1``
_WIDTH_AT = re.compile(rf"({_ST}) on (T-\d+)")
#: how many places a fraction along an edge is written to: a station is graded to the
#: two-hundredth of a foot, and a thousandth of a tangent's length is a foot or less
FRACTION_PLACES = 6
#: the last places a width is tried, where a view's frame cuts every other: this many text
#: heights ahead and back of the station (the dimension line alone, where the task states
#: the station)
WIDTH_STEPS = (1, -1, 2, -2, 3, -3, 4, -4)
#: how many times the dimensions are read back and those a frame cuts set again
WIDTH_ROUNDS = 8


def _f(value: float) -> str:
    """A fraction along a line as the drafter writes it: to the millionth."""
    return f"{float(value):.{FRACTION_PLACES}f}".rstrip("0").rstrip(".")


def _apart_words(a: float, b: float) -> tuple:
    """``(|a - b|, the sum that finds it)``, the larger number first."""
    a, b = _r(a), _r(b)
    hi, lo = (a, b) if a >= b else (b, a)
    d = round(hi - lo, 3)
    return d, f"{_n(hi)} - {_n(lo)} = {_n(d)}"


def _to_raw(display: float, line: dict, lo: float, hi: float) -> List[tuple]:
    """Where a station as lettered lies along the line, between ``lo`` and ``hi``
    (raw stations): ``[(raw, the equation it lies past or None)]``, one for each
    stretch between equations that holds it there.  Before the first equation a
    station reads as its distance along the line; past one, it reads the
    equation's ahead station plus the distance past it."""
    begin, end = float(line["begin_station"]), float(line["end_station"])
    eqs = sorted(line.get("equations") or [], key=lambda q: float(q["raw_station"]))
    starts = [(begin, begin, None)] + [(float(q["raw_station"]), float(q["ahead"]), q)
                                       for q in eqs]
    stops = [s[0] for s in starts[1:]] + [end]
    out = []
    for (rs, ds, q), stop in zip(starts, stops):
        raw = round(rs + (display - ds), 6)
        if rs - 1e-9 <= raw <= stop + 1e-9 and lo - 1e-9 <= raw <= hi + 1e-9:
            out.append((raw, q))
    return out


def _widths(request: str, alignment: str, sheets: Sequence[str], state: Dict[str, dict],
            rows: Dict[str, list], line: Optional[dict], anno_scale, scale: float, paper: dict,
            dims_layer: str, lead: str, read_sheets: bool,
            twist: float = 0.0) -> Generator[Turn, List[dict], dict]:
    """Dimension the pavement width square across each tangent, edge to edge, clear
    of the lettering already along the line; returns ``{"carry", "done", "dims"}``,
    ``dims`` each dimension's id with the station it measures at and its tangent.
    ``twist`` is how far the sheets' viewports are turned: each dimension takes
    it as its ``view_rotation``, so its number reads upright on the sheet.

    Each dimension measures between the two pavement edges of its tangent at one
    station: ``place_dimension`` takes each edge and the same fraction along it,
    so the engine finds the points.  Its text is sized by the annotation scale;
    at plan scale it does not fit between the edges, and the engine sets it with
    the arrowheads outside, past the second point, so the edge on the side the
    curve points are not lettered goes second.  Where the dimension may stand is
    judged in the line's own terms, from each label's record: a label reading
    along a tangent covers the stretch its true length does (worked out from its
    box, its height and the tangent's run: a box round lettering at an angle is
    no measure of it), one square to the line its height, anything else its box;
    and it stands from its offset out by its height (or its length, square to
    the line).  The dimension line crosses the whole road, so it must miss every
    label's stretch; the text stands within its gap and its height of the line,
    out past the edge, so it must also miss the stretch of any label on that side
    that reaches past the edge.  A stated station keeps its measured points and
    moves the line off any label it would cross (the extension lines then run
    along the edges between the two); a station left to the drafter is the half
    station nearest the tangent's middle that clears, the office's standard, or
    else the nearest place just clear of what is in the way.  The dimensions are
    read back to see the text went out where it was meant to and, on sheets that
    were handed over, that no view's frame cuts one: each sheet lists the
    dimensions it shows, each number with the corners of its lettering on that
    paper, and those are compared with the view's frame there; a number that is
    whole on no sheet, or that a frame runs through, is set again at its next
    place (the next station that clears, or its text out on the other side)."""
    stated = {ref: st for st, ref in _WIDTH_AT.findall(request)}
    set_scale = anno_scale != scale
    calls = [_q("set_annotation_scale", scale=scale)] if set_scale else []
    first = len(calls)
    if line is None:
        calls.append(_q("get_design_data", kind="alignments", alignment=alignment))
    if "tangents" not in rows:
        calls.append(_q("get_design_data", kind="tangents", alignment=alignment))
    edges_at = len(calls)
    calls.append(_q("find_entities", anchor={"alignment": alignment, "kind": "offset"}))
    texts_q = {"type": "text", "detail": "full", "limit": FULL_ROWS}
    calls.append(_q("find_entities", **texts_q))
    text_h = float(paper["text_height_in"])
    h = round(_r(text_h) * _r(scale), 3)
    results = yield Turn(
        (lead + " " if lead else "")
        + (f"The sheet shows the model at {_n(scale)} ft to the inch. Set the annotation scale "
           "to match, so the engine sizes the dimension text for that sheet. " if set_scale
           else "")
        + f"Dimension the pavement width square across each tangent of {alignment}. Read what "
        "that takes: "
        + ("the line's station equations, " if line is None else "")
        + ("its tangents, " if "tangents" not in rows else "")
        + "the pavement edges drawn from it, and everything lettered in the model, each label "
        "with its box, to keep the dimensions clear of it.", calls)
    _ok(results, calls)
    n = first
    if line is None:
        if not results[n].get("rows"):
            raise NotCovered(f"the design shows no {alignment}")
        line = results[n]["rows"][0]
        n += 1
    if "tangents" not in rows:
        rows["tangents"] = results[n]["rows"]
    tangents = rows["tangents"]
    edges = results[edges_at]["entities"]
    texts = list(results[edges_at + 1]["entities"])
    more = results[edges_at + 1].get("more")
    while more:
        calls = [_q("find_entities", **texts_q, start=more["start"])]
        results = yield Turn("The list runs on: read the rest of it.", calls)
        _ok(results, calls)
        texts += results[0]["entities"]
        more = results[0].get("more")
    if any((row.get("anchor") or {}).get("alignment") != alignment for row in texts):
        raise NotCovered("the model holds lettering that is not the line's")
    by_ref: Dict[str, Dict[str, dict]] = {}
    for row in edges:
        a = row.get("anchor") or {}
        by_ref.setdefault(a.get("ref"), {})["left" if float(a["offset"]) < 0 else "right"] = row
    halves = {abs(float(row["anchor"]["offset"])) for row in edges}
    if len(halves) != 1:
        raise NotCovered("the pavement edges are not drawn at one width")
    half = _r(halves.pop())

    # -- each tangent's run, said where it is first used
    runs: Dict[str, dict] = {}
    for t in tangents:
        (x0, y0), (x1, y1) = t["start"], t["end"]
        dx, dx_w = _apart_words(x1, x0)
        dy, dy_w = _apart_words(y1, y0)
        runs[t["ref"]] = {
            "dx": dx, "dy": dy, "east": _r(x1) >= _r(x0), "north": _r(y1) >= _r(y0),
            "len": _r(t["length"]), "x0": _r(x0), "y0": _r(y0), "t0": float(t["start_station"]),
            "t1": float(t["end_station"]),
            "words": (f"{t['ref']} runs {_n(t['length'])} ft from x {_n(x0)}, y {_n(y0)} to x "
                      f"{_n(x1)}, y {_n(y1)}: {dx_w} ft {'east' if _r(x1) >= _r(x0) else 'west'} "
                      f"and {dy_w} ft {'north' if _r(y1) >= _r(y0) else 'south'}")}
    told: set = set()

    def run_words(ref: str) -> str:
        """A tangent's run, as a sentence, the first time it is wanted."""
        if ref in told:
            return ""
        told.add(ref)
        return runs[ref]["words"] + ". "

    # -- each label in the line's terms, from its record
    spans: List[dict] = []
    for row in texts:
        a, e = row["anchor"], row["entity"]
        st, off, lh = _r(a["station"]), _r(a["label_offset"]), _r(e["height"])
        w, t, said = _box_sides(row["bbox"])
        kind = a.get("kind")
        name = f"{_LABEL_WORDS.get(kind, 'the label')} at {a.get('ref')}, {row['id']}"
        rot = a.get("rotation")
        bound = round(w + t - lh, 3)
        on = next((tg for tg in tangents
                   if float(tg["start_station"]) - 1e-6 <= float(a["station"])
                   <= float(tg["end_station"]) + 1e-6), None) if rot == "along" else None
        if on is not None:
            r = runs[on["ref"]]
            wide = r["dx"] >= r["dy"]
            box_side, other = (w, r["dy"]) if wide else (t, r["dx"])
            num = round(box_side * r["len"] - lh * other, 3)
            length = round(num / (r["dx"] if wide else r["dy"]), 3)
            how = (f"{name} reads along {on['ref']}; its box is {said} and it is {_n(lh)} ft "
                   f"high, so it is {_n(box_side)} * {_n(r['len'])} - {_n(lh)} * {_n(other)} = "
                   f"{_n(num)} and {_n(num)} / {_n(r['dx'] if wide else r['dy'])} = "
                   f"{_n(length)} ft long")
        elif rot == "along":
            length = bound
            how = (f"{name} reads along the line; its box is {said}, so it is no longer than "
                   f"{_n(w)} + {_n(t)} - {_n(lh)} = {_n(length)} ft")
        if rot == "along":
            reach = round(length / 2.0, 3) if e.get("halign") == "center" else length
            how += (f", {_n(length)} / 2 = {_n(reach)} ft each way from {_n(st)}"
                    if e.get("halign") == "center" else f", set from one end at {_n(st)}")
            outer = round(off + lh, 3)
            out_words = f"{_n(off)} + {_n(lh)} = {_n(outer)}"
        elif rot == "perpendicular":
            mid = e.get("valign") == "middle"
            reach = round(lh / 2.0, 3) if mid else lh
            how = (f"{name} stands square to the line at {_n(st)}"
                   + (f", centred on it, {_n(lh)} / 2 = {_n(reach)} ft each way" if mid
                      else f", within its height of it"))
            outer = round(off + bound, 3)
            out_words = (f"(its box being {said}, it is no longer than {_n(w)} + {_n(t)} - "
                         f"{_n(lh)} = {_n(bound)} ft) {_n(off)} + {_n(bound)} = {_n(outer)}")
        else:
            total = round(w + t, 3)
            reach = round(total / 2.0, 3)
            how = (f"{name} is set level near {_n(st)}; its box is {said}, so it reaches no more "
                   f"than {_n(w)} + {_n(t)} = {_n(total)} and {_n(total)} / 2 = {_n(reach)} ft "
                   "from its point")
            outer = round(off + reach, 3)
            out_words = f"{_n(off)} + {_n(reach)} = {_n(outer)}"
        lo, hi = round(st - reach, 3), round(st + reach, 3)
        spans.append({"id": row["id"], "name": name, "kind": kind, "side": a.get("side"),
                      "lo": lo, "hi": hi,
                      "inner": off if rot in ("along", "perpendicular") else max(0.0, off - reach),
                      "outer": outer, "out_words": out_words,
                      "tangent": on["ref"] if on is not None else None,
                      "words": (f"{how}: {_n(st)} - {_n(reach)} = {_n(lo)} to {_n(st)} + "
                                f"{_n(reach)} = {_n(hi)} along the line")})
    said_spans: set = set()
    #: how the stretches named in a turn are found, said ahead of what the turn decides
    preamble: List[str] = []

    def span_words(s: dict) -> str:
        """A label and its stretch of the line, named; the first time it matters,
        how the stretch is found goes into the turn's preamble."""
        if s["id"] not in said_spans:
            said_spans.add(s["id"])
            if s["tangent"] and s["tangent"] not in told:
                preamble.append(run_words(s["tangent"]).strip())
            preamble.append(s["words"][0].upper() + s["words"][1:] + ".")
        return f"{s['name']} ({_n(s['lo'])} to {_n(s['hi'])})"

    # -- which side the text goes, and what reaches past each edge
    points = {s["side"] for s in spans if s["kind"] in ("pc", "pt")}
    preferred = "left" if points == {"right"} else "right"
    far = {side: [s for s in spans if s["side"] == side and s["outer"] > half + 1e-9]
           for side in _OTHER_SIDE}
    far_ids = {side: {s["id"] for s in far[side]} for side in far}
    gap = round(0.5 * h, 3)
    band = round(gap + h, 3)
    clear = round(h / 2.0, 3)

    def kinds_of(found: Iterable[dict]) -> str:
        return _and(sorted({_LABEL_WORDS.get(s["kind"], "the label")[4:] + "s" for s in found}))

    def blocking(S: float, D: float, side: str) -> List[tuple]:
        """What the dimension measured at ``S``, its line at ``D`` and its text out
        on ``side``, meets: ``[(span, part)]``, part ``line``, ``text`` or
        ``extension``."""
        out = []
        for s in spans:
            if s["lo"] < D < s["hi"]:
                out.append((s, "line"))
            elif s["id"] in far_ids[side] and s["lo"] < D + band and D - band < s["hi"]:
                out.append((s, "text"))
            elif (abs(D - S) > 1e-9 and s["inner"] < half < s["outer"]
                  and s["lo"] < max(S, D) + h and min(S, D) - h < s["hi"]):
                out.append((s, "extension"))
        return out

    def why_not(at: float, found: List[tuple], side: str) -> str:
        """Why a dimension line at ``at`` will not do, as a clause."""
        s, part = found[0]
        if part == "line":
            return f"a line at {_n(at)} would cross {span_words(s)}"
        if part == "text":
            return (f"the text of a line at {_n(at)} would stand within {_n(band)} ft of it, on "
                    f"the stretch of {span_words(s)}, which reaches {s['out_words']} ft out on "
                    f"the {side}, past the edge")
        return f"an extension line would run along the edge across {span_words(s)}"

    def past(s: dict, part: str, ahead: bool) -> tuple:
        """Just clear of a label that is in the way: ``(the station, the sum)``."""
        room = band + clear if part == "text" else clear
        room_w = f"{_n(band)} + {_n(clear)}" if part == "text" else _n(clear)
        if ahead:
            at = round(s["hi"] + room, 3)
            return at, f"{_n(s['hi'])} + {room_w} = {_n(at)}"
        at = round(s["lo"] - room, 3)
        return at, f"{_n(s['lo'])} - {room_w} = {_n(at)}"

    def slide(S: Optional[float], start: float, ahead: bool, t0: float, t1: float,
              side: str) -> Optional[tuple]:
        """From ``start``, move a dimension measured at ``S`` (or, with ``S`` None,
        one measured where its line is) one way along the line past whatever is
        in the way: ``(where it is clear, the moves)``, None when it runs off
        the tangent first."""
        at, moves = start, []
        for _try in range(8):
            found = blocking(at if S is None else S, at, side)
            if not found:
                return at, moves
            if any(part == "extension" for _s, part in found):
                return None
            # past the one that reaches furthest the way it moves
            pick = (max if ahead else min)(found, key=lambda f: past(f[0], f[1], ahead)[0])
            nxt, words = past(pick[0], pick[1], ahead)
            if not t0 < nxt < t1:
                return None
            moves.append((at, [pick], words))
            at = nxt
        return None

    def move_words(moves: Sequence[tuple], ahead: bool, side: str) -> str:
        out = []
        for at, found, words in moves:
            why = why_not(at, found, side)
            out.append(f"{why[0].upper()}{why[1:]}; move "
                       f"{'ahead past its end' if ahead else 'back before its start'}, half a "
                       "text height clear"
                       + (" (and the text's own reach): " if found[0][1] == "text" else ": ")
                       + f"{words}.")
        return " ".join(out)

    def clear_words(D: float, side: str) -> str:
        """Why a dimension line at ``D`` is clear: the nearest lettering behind and
        ahead of it along the line, and, past the edge its text goes out on,
        the nearest label there."""
        before = max((s for s in spans if s["hi"] <= D), key=lambda s: s["hi"], default=None)
        after = min((s for s in spans if s["lo"] >= D), key=lambda s: s["lo"], default=None)
        parts = []
        if before is not None:
            parts.append(f"behind it {span_words(before)} ends")
        if after is not None:
            parts.append(f"ahead {span_words(after)} begins")
        if far[side]:
            f = min(far[side], key=lambda s: max(s["lo"] - D, D - s["hi"], 0.0))
            lo, hi = round(D - band, 3), round(D + band, 3)
            parts.append(f"its text, {_n(D)} - {_n(band)} = {_n(lo)} to {_n(D)} + {_n(band)} = "
                         f"{_n(hi)}, keeps off the nearest of the "
                         f"{kinds_of([f])} past the {side} edge, {span_words(f)}")
        return "; ".join(parts)

    def side_words(side: str, again: bool) -> str:
        """Which edge goes second, so the text goes out on ``side``, and what on
        that side reaches past the edge."""
        other = _OTHER_SIDE[side]
        if again:
            head = f"Put the text out on the {side} instead, the {other} edge first."
        elif points:
            head = (f"The BC and EC labels stand on the {other}, so the {side} edge goes second "
                    f"and the text out on the {side}.")
        else:
            head = f"The {side} edge goes second and the text out on the {side}."
        near: Dict[str, dict] = {}
        for s in spans:
            if s["side"] == side and s["outer"] <= half + 1e-9:
                near.setdefault(s["kind"], s)
        words = [head] + [f"On the {side}, {kinds_of([s])} reach {s['out_words']} ft out, "
                          f"inside the {_n(half)} ft edge." for s in near.values()]
        words.append(f"Past the {side} edge nothing is lettered, so nothing there can meet the "
                     "text." if not far[side] else
                     f"Past the {side} edge stand {kinds_of(far[side])}, so the text must keep "
                     "off their stretches of the line.")
        return " ".join(words)

    general = (
        f"Each width is measured square across its tangent between the two pavement edges at "
        f"one station: place_dimension takes the edge on each side and the same fraction along "
        f"each, and the engine finds the points, {_n(half)} ft either side of the centerline. "
        f"The engine letters at the office's {_n(text_h)} in, {_n(text_h)} * {_n(scale)} = "
        f"{_n(h)} ft at this scale; at that size the text does not fit between the edges, so "
        f"it goes outside with the arrowheads, past the second point. "
        + side_words(preferred, False)
        + f" Along the line the text stands within its gap, 0.5 * {_n(h)} = {_n(gap)} ft (the "
        f"tool's default), and its height of the dimension line: {_n(gap)} + {_n(h)} = "
        f"{_n(band)} ft either way. The dimension line itself crosses the road, so it must miss "
        f"every label's stretch of the line. A line moved off a label is set half a text "
        f"height clear of it, {_n(h)} / 2 = {_n(clear)} ft."
        + (f" The viewport{'s are' if len(sheets) > 1 else ' is'} turned {_n(twist)}°, so each "
           f"dimension takes that as its view_rotation and its number reads upright on the "
           f"sheet{'s' if len(sheets) > 1 else ''}." if twist else ""))

    def options(t: dict) -> Generator[dict, None, None]:
        """Where a tangent's width may go, best first: ``{"S", "D", "side",
        "says"}``, the words worked out as each is asked for."""
        ref, r = t["ref"], runs[t["ref"]]
        t0, t1 = r["t0"], r["t1"]
        says: List[str] = []
        sides = (preferred, _OTHER_SIDE[preferred])
        if ref in stated:
            written = stated[ref]
            held = _to_raw(numbers_in(written)[0], line, t0, t1)
            if len(held) != 1:
                raise NotCovered(f"{written} is not one place on {ref}")
            S, q = _r(held[0][0]), held[0][1]
            says.append(f"The task puts {ref}'s width at {written}"
                        + (f"; past the station equation at {_n(q['raw_station'])} along the "
                           f"line, where {_n(q['back'])} back is {_n(q['ahead'])} ahead, that is "
                           f"{_n(numbers_in(written)[0])} - {_n(q['ahead'])} + "
                           f"{_n(q['raw_station'])} = {_n(S)} along it" if q else "")
                        + ".")
            for k, side in enumerate(sides):
                if k:
                    says.append(side_words(side, True))
                found = blocking(S, S, side)
                if not found:
                    says.append(f"A dimension line at {_n(S)} is clear: {clear_words(S, side)}.")
                    yield {"S": S, "D": S, "side": side, "says": says}
                    says = []
                    continue
                # the measured points stay at the stated station: the line moves off the label
                tries = [(slide(S, S, ahead, t0, t1, side), ahead) for ahead in (True, False)]
                tries = sorted([(got, ahead) for got, ahead in tries if got is not None],
                               key=lambda g: abs(g[0][0] - S))
                for (D, moves), ahead in tries:
                    says.append(move_words(moves, ahead, side))
                    says.append(f"A dimension line at {_n(D)} is clear: {clear_words(D, side)}.")
                    yield {"S": S, "D": D, "side": side, "says": says}
                    says = []
            # last, the line a few text heights either way of the station, the text with it
            for side in sides:
                for k in WIDTH_STEPS:
                    D = round(S + k * h, 3)
                    if not t0 <= D <= t1 or blocking(S, D, side):
                        continue
                    says.append(f"Move the dimension line {abs(k)} text height"
                                f"{'s' if abs(k) > 1 else ''} {'ahead' if k > 0 else 'back'}, "
                                f"its text out on the {side}: {_n(S)} {'+' if k > 0 else '-'} "
                                f"{_n(h)} * {abs(k)} = {_n(D)}. A dimension line there is clear: "
                                f"{clear_words(D, side)}.")
                    yield {"S": S, "D": D, "side": side, "says": says}
                    says = []
            return
        mid_text = t["mid_station_text"]
        mid_d = numbers_in(mid_text)[0]
        hundreds = int(mid_d // 100)
        hs0 = hundreds * 100.0 + 50.0
        says.append(f"{ref} runs from {t['start_station_text']} to {t['end_station_text']}, its "
                    f"middle at {mid_text}: the half station nearest it is {hundreds} * 100 + 50 "
                    f"= {_n(hs0)}.")
        halves = []
        for j in sorted(range(-30, 31), key=lambda j: (abs(hs0 + 100.0 * j - mid_d), j)):
            disp = hs0 + 100.0 * j
            held = _to_raw(disp, line, t0, t1)
            if len(held) != 1 or not t0 < held[0][0] < t1:
                continue
            raw, q = _r(held[0][0]), held[0][1]
            step = (f"{_n(hs0)} {'+' if j > 0 else '-'} 100"
                    + (f" * {abs(j)}" if abs(j) > 1 else "") + f" = {_n(disp)}") if j else ""
            conv = (f"{_n(disp)} - {_n(q['ahead'])} + {_n(q['raw_station'])} = {_n(raw)} along "
                    f"the line, past the station equation at {_n(q['raw_station'])}" if q else "")
            where = ", ".join(w for w in (step, conv) if w)
            halves.append((raw, f"The half station {_n(disp)}" + (f" ({where})" if where else "")))
        start = halves[0][0] if halves else _r(t["mid_station"])
        tried: List[float] = []
        for k, side in enumerate(sides):
            if k:
                says.append(side_words(side, True))
            for raw, named in halves:
                found = blocking(raw, raw, side)
                if found:
                    says.append(f"{named}: {why_not(raw, found, side)}.")
                    continue
                says.append(f"{named} is clear: {clear_words(raw, side)}.")
                tried.append(raw)
                yield {"S": raw, "D": raw, "side": side, "says": says}
                says = []
            tries = [(slide(None, start, ahead, t0, t1, side), ahead) for ahead in (True, False)]
            tries = sorted([(got, ahead) for got, ahead in tries if got is not None],
                           key=lambda g: abs(g[0][0] - start))
            for (S, moves), ahead in tries:
                says.append(("No half station on it clears, so move along the line from "
                             f"{_n(start)}: " if halves else
                             f"No half station falls on it, so start from its middle, "
                             f"{_n(start)}: ") + move_words(moves, ahead, side))
                says.append(f"{_n(S)} is clear: {clear_words(S, side)}.")
                tried.append(S)
                yield {"S": S, "D": S, "side": side, "says": says}
                says = []
        # last, a few text heights either way of the first place that cleared
        if tried:
            for side in sides:
                for k in WIDTH_STEPS:
                    S = round(tried[0] + k * h, 3)
                    if not t0 < S < t1 or blocking(S, S, side):
                        continue
                    says.append(f"Move it {abs(k)} text height{'s' if abs(k) > 1 else ''} "
                                f"{'ahead' if k > 0 else 'back'} of {_n(tried[0])}, its text out "
                                f"on the {side}: {_n(tried[0])} {'+' if k > 0 else '-'} {_n(h)} "
                                f"* {abs(k)} = {_n(S)}, which is clear: {clear_words(S, side)}.")
                    yield {"S": S, "D": S, "side": side, "says": says}
                    says = []
        options.left = says  # what was said of the last tries, for a tangent left alone

    def each_once(t: dict) -> Generator[dict, None, None]:
        """``options``, each place offered once: a move along the line that starts
        where it is already clear lands where the first try did."""
        offered = set()
        for opt in options(t):
            key = (round(opt["S"], 3), round(opt["D"], 3), opt["side"])
            if key in offered:
                continue
            offered.add(key)
            yield opt

    def place(t: dict, opt: dict) -> tuple:
        """The words that put the dimension where ``opt`` says, and the call."""
        ref, r = t["ref"], runs[t["ref"]]
        S, D, side = opt["S"], opt["D"], opt["side"]
        a_off, a_w = _apart_words(S, r["t0"])
        frac = round(a_off / r["len"], FRACTION_PLACES)
        work = (f"{_n(S)} is {a_w} ft along {ref} from its start, and {_n(a_off)} / "
                f"{_n(r['len'])} = {_f(frac)} of its length, along each edge.")
        if abs(D - S) > 1e-9:
            d_off, d_w = _apart_words(D, r["t0"])
            dfrac = round(d_off / r["len"], FRACTION_PLACES)
            work += (f" The dimension line at {_n(D)} is {d_w} ft along, {_n(d_off)} / "
                     f"{_n(r['len'])} = {_f(dfrac)} of the length; the extension lines run "
                     "along the edges between the two, where no lettering crosses them. Its "
                     "point is ")
        else:
            dfrac = frac
            work += " The dimension line goes through the measured points: "
        x = round(r["x0"] + (dfrac * r["dx"] if r["east"] else -dfrac * r["dx"]), 3)
        y = round(r["y0"] + (dfrac * r["dy"] if r["north"] else -dfrac * r["dy"]), 3)
        work += (f"x {_n(r['x0'])} {'+' if r['east'] else '-'} {_f(dfrac)} * {_n(r['dx'])} = "
                 f"{_n(x)} and y {_n(r['y0'])} {'+' if r['north'] else '-'} {_f(dfrac)} * "
                 f"{_n(r['dy'])} = {_n(y)} on the centerline.")
        edges_of = by_ref[ref]
        p1, p2 = edges_of[_OTHER_SIDE[side]]["id"], edges_of[side]["id"]
        work += (f" Dimension {ref} from its {_OTHER_SIDE[side]} edge {p1} to its {side} edge "
                 f"{p2} on {dims_layer}.")
        return work, _q("place_dimension", space="model", kind="aligned", from_entity=p1,
                        from_at=frac, to_entity=p2, to_at=frac, line_point=[x, y],
                        layer=dims_layer, **({"view_rotation": twist} if twist else {}))

    # -- each tangent: where its width goes, and the dimension
    placed: Dict[str, dict] = {}
    skipped: List[str] = []
    pending: List[str] = []  # words of a tangent left undimensioned, said with the next turn
    said_general = False
    for t in tangents:
        ref = t["ref"]
        if "left" not in by_ref.get(ref, {}) or "right" not in by_ref.get(ref, {}):
            raise NotCovered(f"{ref} has no pavement edge on each side")
        if stated and ref not in stated:
            continue
        del preamble[:]
        head = run_words(ref).strip()
        options.left = []
        gen = each_once(t)
        opt = next(gen, None)
        if opt is None:
            if ref in stated:
                raise NotCovered(f"no place on {ref} for the dimension at {stated[ref]}")
            skipped.append(ref)
            pending.extend([head] + preamble + options.left
                           + [f"{ref} has no room clear of its lettering, so its width is left "
                              "undimensioned."])
            continue
        work, call = place(t, opt)
        says = opt["says"]
        results = yield Turn(
            " ".join(w for w in ([] if said_general else [general]) + pending + [head]
                     + says[:1] + preamble + says[1:] + [work] if w), [call])
        _ok(results, [call])
        said_general, pending = True, []
        placed[ref] = {"id": results[0]["created"][0], "opt": opt, "gen": gen, "t": t}
    if not placed:
        raise NotCovered(f"no tangent of {alignment} has room for its width")

    # -- read back: the text went out where it was meant to; on sheets handed over, each
    # number shows whole on a sheet and no frame cuts it
    frames: Dict[str, tuple] = {}
    frame_words: List[str] = []
    unread = [name for name in sheets if name not in state] if read_sheets else []
    head = (" ".join(pending) + " " if pending else "")
    for _round in range(WIDTH_ROUNDS):
        calls = [_q("find_entities", type="dimension", detail="full", limit=FULL_ROWS)]
        if read_sheets:
            calls += [_q("find_entities", visible_on=name, type="dimension") for name in sheets]
        states_at = len(calls)
        calls += [_q("get_sheet_state", sheet=name) for name in unread]
        results = yield Turn(
            head + "Read the dimensions back, each with its box, to see each text went out on "
            "the side meant"
            + (f"; what {_and(list(sheets))} show{'s' if len(sheets) == 1 else ''} of them, each "
               "number with the corners of its lettering on that paper, to see no view's frame "
               "cuts one" if read_sheets else "")
            + (f"; and {_and(unread)} for {'its' if len(unread) == 1 else 'their'} "
               f"view{'' if len(unread) == 1 else 's'}" if unread else "")
            + ".", calls)
        _ok(results, calls)
        head = ""
        for name, result in zip(unread, results[states_at:]):
            state[name] = result["sheet"]
        unread = []
        rows_back = {row["id"]: row for row in results[0]["entities"]}
        listed = {name: {row["id"]: row for row in result.get("entities") or []}
                  for name, result in zip(sheets, results[1:states_at])} if read_sheets else {}
        if any(result.get("more") for result in results[:states_at]):
            raise NotCovered("more dimensions than one reading lists")
        checked, bad = [], []
        if read_sheets and not frames:
            for name in sheets:
                views = state[name].get("viewports") or []
                if len(views) != 1:
                    raise NotCovered(f"{name} has no single view to check against")
                (cx, cy), w, hh = views[0]["center_paper"], views[0]["width_in"], \
                    views[0]["height_in"]
                x0, x1 = round(_r(cx) - _r(w) / 2, 3), round(_r(cx) + _r(w) / 2, 3)
                y0, y1 = round(_r(cy) - _r(hh) / 2, 3), round(_r(cy) + _r(hh) / 2, 3)
                frames[name] = (x0, y0, x1, y1)
                frame_words.append(
                    f"{name}'s view is framed on the paper from x {_n(cx)} - {_n(w)} / 2 = "
                    f"{_n(x0)} to {_n(cx)} + {_n(w)} / 2 = {_n(x1)} and y {_n(cy)} - {_n(hh)} / 2 "
                    f"= {_n(y0)} to {_n(cy)} + {_n(hh)} / 2 = {_n(y1)}.")
        for ref, p in placed.items():
            if p.get("checked"):
                continue
            row = rows_back.get(p["id"])
            if row is None:
                raise NotCovered(f"{p['id']} does not read back")
            side = p["opt"]["side"]
            ent, bb = row["entity"], row["bbox"]
            a, b = ent["p1"], ent["p2"]
            axis = 0 if abs(a[0] - b[0]) >= abs(a[1] - b[1]) else 1
            if _r(b[axis]) >= _r(a[axis]):
                out2, w2 = _apart_words(bb[axis + 2], b[axis])
                out1, w1 = _apart_words(a[axis], bb[axis])
            else:
                out2, w2 = _apart_words(b[axis], bb[axis])
                out1, w1 = _apart_words(bb[axis + 2], a[axis])
            if out2 <= out1:
                raise NotCovered(f"the text of {p['id']} did not go out past its second point")
            words = (f"{p['id']} on {ref} reaches {w2} ft past its {side} point in "
                     f"{'xy'[axis]} and {w1} ft past its {_OTHER_SIDE[side]} one, so its text "
                     f"went out on the {side}.")
            if read_sheets:
                inside, cut, off = [], [], []
                for name in sheets:
                    seen = listed[name].get(p["id"])
                    if seen is None:
                        off.append(f"{name} does not show it")
                        continue
                    if not seen.get("paper_corners"):
                        raise NotCovered(f"{p['id']} came back without the corners of its number")
                    box, said = _corner_box(seen["paper_corners"])
                    f = frames[name]
                    if f[0] <= box[0] and f[1] <= box[1] and box[2] <= f[2] and box[3] <= f[3]:
                        inside.append(f"on {name} its number has {said}, inside the frame")
                    elif box[2] < f[0] or f[2] < box[0] or box[3] < f[1] or f[3] < box[1]:
                        off.append(f"on {name} its number has {said}, wholly outside the frame, "
                                   "so it does not show there")
                    else:
                        over = [f"its {edge_name} edge at {'xy'[k % 2]} {_n(f[k])}"
                                for k, edge_name in enumerate(("left", "bottom", "right", "top"))
                                if (box[k] < f[k] if k < 2 else f[k] < box[k])]
                        cut.append(f"on {name} its number has {said}, across the frame at "
                                   f"{_and(over)}, which would cut it")
                words += " " + "; ".join(w[0].upper() + w[1:] if k == 0 else w
                                         for k, w in enumerate(inside + cut + off))
                if cut or not inside:
                    bad.append(ref)
                    if not cut:
                        words += ": it shows whole on no sheet"
                words += "."
            p["checked"] = ref not in bad
            checked.append(words)
        carry = " ".join(frame_words + checked)
        frame_words = []
        if not bad:
            break
        # set each one a frame would cut again at its next place
        calls, says = [], [carry]
        for ref in bad:
            p = placed[ref]
            del preamble[:]
            opt = next(p["gen"], None)
            if opt is None:
                raise NotCovered(f"no place on {ref} that a sheet's view shows whole")
            work, call = place(p["t"], opt)
            says += preamble + opt["says"] + [work]
            calls += [_q("delete_entities", ids=[p["id"]]), call]
            p["opt"] = opt
        results = yield Turn(f"Take off {_and([placed[ref]['id'] for ref in bad])} and set "
                             f"{'it' if len(bad) == 1 else 'them'} again. " + " ".join(says),
                             calls)
        _ok(results, calls)
        for k, ref in enumerate(bad):
            placed[ref]["id"] = results[2 * k + 1]["created"][0]
    else:
        raise NotCovered("the width dimensions do not settle inside the sheets' views")
    dims = {p["id"]: {"station": p["opt"]["S"], "ref": ref} for ref, p in placed.items()}
    done = (f"dimensioned the pavement width across {_and(list(placed))} on {dims_layer}, clear "
            "of the lettering along the line"
            + (f"; {_and(skipped)} too short to dimension clear of it" if skipped else ""))
    return {"carry": carry, "done": done, "dims": dims}


def solve(text: str, phases: Sequence[str]) -> Generator[Turn, List[dict], Turn]:
    """Draft ``phases`` for the task ``text`` asks, a turn at a time: yields a
    ``Turn``, is sent that turn's results, and returns the turn it submits
    with.  It is handed nothing else, so every value it sends was read from
    ``text``, from a result, or from spec v1's standards, or is worked out
    from those in the line of shown work that goes with the call."""
    request = request_of(text)
    todo = [p for p in PHASE_ORDER if p in phases]
    #: a finished sheet whose line the designer has since changed (the revision dial)
    revision = stated_revision(request)
    if revision and revision["kind"] == "station":
        todo = [p for p in todo if p != "table"]  # the curve data holds no station
    left = [p for p in todo if p not in COVERED]
    if left:
        raise NotCovered(f"phases not covered: {', '.join(left)}")
    done: List[str] = []
    #: what the last read showed, said at the head of the next turn
    carry = ""

    def said(words: str) -> str:
        """A turn's words, led by what the last read showed."""
        nonlocal carry
        lead, carry = carry, ""
        return (lead + " " if lead else "") + words

    # -- what the document holds
    calls = [_q("get_document_state", detail="summary"), _q("list_layers")]
    results = yield Turn("See what the document holds first: its sheets, layers and design.", calls)
    _ok(results, calls)
    summary = results[0]["summary"]
    meta = summary.get("meta") or {}
    layers = {row["name"] for row in results[1]["layers"]}
    sheets = [s["name"] for s in summary.get("sheets") or []]
    own = list(summary.get("alignments") or [])

    def layer(role: str) -> str:
        name = ROLE_LAYER[role]
        if name not in layers:
            raise NotCovered(f"the document has no layer {name}")
        return name

    # -- the design: created from the task, or found in the document or its base drawing
    alignment: Optional[str] = None
    if "design" in todo:
        params = stated_alignment(request)
        if params is None:
            raise NotCovered("the task states no alignment to create")
        calls = [_q("create_alignment", **params)]
        results = yield Turn(
            f"The design is empty, so {params['name']} is created from the points the task gives. "
            "The task writes northing then easting; the engine takes [easting, northing], with "
            "the radius after it at each PI.", calls)
        _ok(results, calls)
        alignment = params["name"]
        done.append(f"created {alignment}")
    elif own:
        alignment = _named(request, own)
    elif any(p in todo for p in MODEL_LETTERING + ("linework", "edges", "sheet", "table")):
        calls = [_q("list_alignments", include_references=True)]
        results = yield Turn("This file holds no alignment of its own, so look for one in the "
                             "attached base drawing.", calls)
        _ok(results, calls)
        own = [row["name"] for row in results[0].get("alignments") or []]
        if not own:
            raise NotCovered("no alignment in the document or its references")
        alignment = _named(request, own)
    #: the other lines the design holds: their lettering is not this line's to trust
    others = [n for n in own if n != alignment]

    # -- the layers
    if "layers" in todo:
        wanted = [n for n in LAYER_SET if n in request] or list(LAYER_SET)
        missing = [n for n in wanted if n not in layers]
        if missing:
            calls = [_q("create_layer", name=n, **SPEC["layer_props"][n]) for n in missing]
            results = yield Turn("Create the levels that are not there yet, each with its "
                                 "standard color and weight.", calls)
            _ok(results, calls)
            layers.update(missing)
            done.append(f"created {len(missing)} layers")

    # -- model linework
    if "linework" in todo:
        calls = [_q("draw_alignment", alignment=alignment, layer=layer("alignment"))]
        results = yield Turn(f"Draw the centerline of {alignment} from the design, on the "
                             f"alignment's own level, {layer('alignment')}.", calls)
        _ok(results, calls)
        done.append(f"drew {alignment} on {layer('alignment')}")
    if "edges" in todo:
        lanes = _LANES.search(request)
        if not lanes:
            raise NotCovered("the task gives no lane width")
        width = float(lanes.group(1))
        calls = [_q("draw_offset", alignment=alignment, offsets=[-width, width],
                    layer=layer("edges"))]
        results = yield Turn(
            f"Two {width:g}-ft lanes put an edge of pavement {width:g} ft each side of the "
            f"centerline: offsets left (negative) and right, on {layer('edges')}.", calls)
        _ok(results, calls)
        done.append(f"drew the pavement edges {width:g} ft each side on {layer('edges')}")

    lettering = [p for p in todo if p in MODEL_LETTERING]
    sheet_work = [p for p in todo if p in SHEET_WORK]

    # -- the sheets themselves, each with a viewport centred on its stretch of the line.
    # The lettering comes after, sized for the scale the viewport shows, and a layout of
    # several sheets is trimmed and given its match lines once the lettering is down
    layout: Optional[dict] = None
    if "sheet" in todo:
        # a task that leaves the number of sheets and their breaks open has them chosen first
        chosen: Optional[dict] = None
        first = stated_open(request)
        if first:
            chosen = yield from _choose_breaks(request, alignment, first,
                                               ["tangents"] if "bearings" in lettering else [])
            done.append(chosen["done"])
        layout = yield from _lay_out(request, alignment, summary,
                                     ["tangents"] if "bearings" in lettering else [],
                                     lettered=not lettering, chosen=chosen)
        sheets, carry = layout["names"], layout["carry"]
        if len(sheets) == 1:
            done.append(
                f"set up {sheets[0]} on {layout['size'].replace('_', ' ')} with a viewport at "
                f"{SPEC['sheet']['scale_text_format'].format(fpi=layout['scale'])}"
                + (f" turned {_n(layout['twist'])}°" if layout["twist"] else "")
                + f", centred on {alignment}")

    # -- the sheets: the scale each shows the model at, what is on the paper, and the
    # design's tangents and curves where the work letters or lists them
    state: Dict[str, dict] = dict(layout["state"]) if layout else {}
    rows: Dict[str, list] = dict(layout["rows"]) if layout else {}
    scale = None
    #: how far the sheets' viewports are turned: model lettering is read through it
    twist = 0.0
    widths = "widths" in todo
    #: a revision left for the drafter to make in the base drawing: the line's tangents and
    #: curves are read after the change, not before it
    in_base = bool(revision and alignment and ":" in alignment and _IN_BASE.search(request))
    later: List[str] = []
    if lettering or sheet_work or widths:
        if not sheets:
            raise NotCovered("no sheet to read the plan scale from")
        read = [name for name in (sheets if sheet_work else sheets[:1]) if name not in state]
        kinds = [kind for kind in (["tangents"] if "bearings" in lettering or widths else []) + (
            ["curves"] if "callouts" in lettering or "table" in sheet_work else [])
            if kind not in rows]
        if in_base:
            later, kinds = kinds, []
        calls = [_q("get_sheet_state", sheet=name) for name in read]
        calls += [_q("get_design_data", kind=kind, alignment=alignment) for kind in kinds]
        if not read:
            say = f"Read the {_and(kinds)} of {alignment} from the design." if kinds else ""
        elif sheet_work:
            say = (f"Read {_and(read)}: the viewport and the scale it shows the model at, the "
                   "usable area inside the border, the title block and what is already on the "
                   "paper" + (f". Read the {_and(kinds)} of {alignment} from the design too."
                              if kinds else "."))
        elif lettering:
            say = (f"The lettering goes in the model and is read on the sheet, so read {read[0]} "
                   "for its scale" + (", and the design for what there is to letter." if kinds
                                      else "."))
        else:
            say = (f"The dimensions go in the model and are read on the sheet, so read {read[0]} "
                   "for its scale" + (", and the design for the tangents to dimension." if kinds
                                      else "."))
        results = []
        if calls:
            results = yield Turn(said(say), calls)
            _ok(results, calls, cut=("get_sheet_state",))

        def take(names: Sequence[str], sheet_results: Sequence[dict]) -> None:
            for name, result in zip(names, sheet_results):
                # a sheet that carries more than one answer holds comes back cut: its head
                # still has the viewport, and so the scale and the twist
                state[name] = (_cut_sheet(result) if result.get("truncated")
                               else result["sheet"])
                if not state[name].get("viewports"):
                    raise NotCovered(f"{name} has no viewport to read a scale from")

        take(read, results)
        rows.update({kind: result["rows"] for kind, result in zip(kinds, results[len(read):])})
        scale = state[sheets[0]]["viewports"][0]["feet_per_inch"]
        twist = float(state[sheets[0]]["viewports"][0].get("rotation_deg") or 0.0)
        rest = [name for name in sheets if name not in state]
        if twist and rest:
            # the model is lettered once, for every sheet that shows it
            calls = [_q("get_sheet_state", sheet=name) for name in rest]
            results = yield Turn(
                f"The viewport of {sheets[0]} is turned {_n(twist)}°. The model is lettered "
                f"once for every sheet that shows it, so read {_and(rest)} too, to see that "
                f"{'it is' if len(rest) == 1 else 'they are'} turned the same.", calls)
            _ok(results, calls, cut=("get_sheet_state",))
            take(rest, results)
        turns = {name: float(state[name]["viewports"][0].get("rotation_deg") or 0.0)
                 for name in state}
        if any(abs(t - twist) > 1e-6 for t in turns.values()):
            raise NotCovered("the sheets' viewports are not turned alike")
        #: the sheets whose state came back cut: what they carry is asked for by place
        wide = [name for name in sheets if state.get(name, {}).get("cut")]
        if wide:
            if sheet_work or widths or revision or layout or len(sheets) > 1:
                raise NotCovered(f"the state of {_and(wide)} was cut, and the work needs what "
                                 "is on the paper")
            carry = (f"The answer for {wide[0]} was cut: the sheet carries more than one answer "
                     f"holds. Its head came whole, and the viewport is in it: the model at "
                     f"{_n(scale)} ft to the inch"
                     + (f", turned {_n(twist)}°" if twist else ", not turned")
                     + ". Asking again would cut it at the same place, so what is on the paper "
                     "is asked for by kind and by place where the work needs it.")

    # -- a revised design: what was lettered before the change comes off first
    if revision and ":" not in alignment:
        # the design lives in this file: the change is made here and the lettering follows it
        if len(sheets) != 1:
            raise NotCovered("a revision on anything but one sheet lettered from the line")
        lead, carry = carry, ""
        made = yield from _revise_own(revision, alignment, sheets[0], state[sheets[0]], lead)
        carry = made["carry"]
        done.append(made["done"])
        todo = [p for p in todo if p not in MODEL_LETTERING + ("table",)]
        lettering = []
    elif revision:
        if not lettering or len(sheets) != 1:
            raise NotCovered("a revision on anything but one sheet lettered from the line")
        lead, carry = carry, ""
        if in_base:
            # the change is the drafter's to make, in the base drawing that holds the design
            cleared = yield from _revise_base(revision, alignment, sheets[0], state[sheets[0]],
                                              summary.get("document"), later, lead)
            rows.update(cleared["rows"])
        else:
            cleared = yield from _revise(revision, alignment, sheets[0], state[sheets[0]],
                                         rows.get("curves") or [], lead)
        gone = set(cleared["deleted"])
        state[sheets[0]] = {**state[sheets[0]], "entities": {
            eid: e for eid, e in (state[sheets[0]].get("entities") or {}).items()
            if eid not in gone}}
        done.append(cleared["done"])

    # -- model lettering, sized for the sheet that shows it
    #: the annotation scale the engine sizes model lettering and dimensions by
    anno_scale = summary.get("annotation_scale")
    if lettering:
        if anno_scale != scale:
            calls = [_q("set_annotation_scale", scale=scale)]
            results = yield Turn(said(
                ("Set the annotation scale to match, so the engine sizes the lettering for "
                 f"{sheets[0]}." if state[sheets[0]].get("cut") else
                 f"{sheets[0]} shows the model at {scale:g} ft to the inch. Set the annotation "
                 "scale to match, so the engine sizes the lettering for that sheet.")), calls)
            _ok(results, calls)
            anno_scale = scale
        anno = layer("labels")
        #: what this turn of work letters: each new entity's id, with what goes when it does
        lettered: Dict[str, List[str]] = {}
        # through a turned viewport the lettering is made to read upright as plotted: each
        # labeler takes the view's turn; said once, with the first lettering that goes down
        view = {"view_rotation": twist} if twist else {}
        reads = (f" The viewport{'s are' if len(sheets) > 1 else ' is'} turned {_n(twist)}°, so "
                 f"the lettering takes that as its view_rotation and reads upright on the "
                 f"plotted sheet{'s' if len(sheets) > 1 else ''}, not in the model."
                 if twist else "")
        if "stationing" in lettering:
            calls = [_q("annotate_stationing", space="model", alignment=alignment,
                        layer=layer("ticks"), label_layer=anno, **view)]
            results = yield Turn(said(
                f"Station {alignment} in model space, where every sheet shows it: ticks, station "
                f"numbers and the curve points, all on {anno}.{reads}"), calls)
            _ok(results, calls)
            lettered.update({i: [i] for i in results[0]["created"]})
            reads = ""
            done.append(f"stationed {alignment} on {anno}")
        if "bearings" in lettering:
            refs = [row["ref"] for row in rows["tangents"]]
            calls = [_q("place_label", space="model", alignment=alignment, anchor=ref,
                        kind="bearing", layer=anno, **view) for ref in refs]
            results = yield Turn(said(
                f"{alignment} has {len(refs)} tangent{'s' if len(refs) != 1 else ''}. Letter the "
                f"bearing and length of each at its middle, on {anno}.{reads}"), calls)
            _ok(results, calls)
            lettered.update({i: list(r["created"]) for r in results for i in r["created"]})
            reads = ""
            done.append(f"lettered {len(refs)} bearing{'s' if len(refs) != 1 else ''} on {anno}")
        if "callouts" in lettering:
            numbers = [row["index"] for row in rows["curves"]]
            calls = [_q("place_label", space="model", alignment=alignment, anchor=f"MC-{n}",
                        kind="mc", layer=anno, **view) for n in numbers]
            results = yield Turn(said(
                f"{alignment} has {len(numbers)} curve{'s' if len(numbers) != 1 else ''}. Number "
                f"each at its midpoint, on {anno}.{reads}"), calls)
            _ok(results, calls)
            lettered.update({i: list(r["created"]) for r in results for i in r["created"]})
            reads = ""
            done.append(f"numbered {len(numbers)} curve{'s' if len(numbers) != 1 else ''} on {anno}")
        if twist:
            done[-1] += f", read through the {_n(twist)}° twist"
        # a sheet that showed other lettering before this: see what the new labels fell on.
        # (A line alone on its sheet is lettered clear of itself by the engine's labelers.)
        notes = [eid for eid, e in (state[sheets[0]].get("entities") or {}).items()
                 if e.get("type") == "text" and not (e.get("anchor") or {}).get("kind")]
        if others or notes or state[sheets[0]].get("cut"):
            if len(sheets) > 1:
                raise NotCovered("other lettering to keep clear of on a layout of several sheets")
            lead, carry = carry, ""
            cleared = yield from _clear(sheets[0], state[sheets[0]], alignment, lettered, anno,
                                        view, others, lead)
            carry = cleared["carry"]
            done.append(cleared["done"])

    # -- the width dimensions, square across each tangent, clear of the lettering
    #: each width dimension's id, with the station it measures at and its tangent
    dims: Dict[str, dict] = {}
    if widths:
        lead, carry = carry, ""
        made = yield from _widths(
            request, alignment, sheets, state, rows, layout["line"] if layout else None, anno_scale,
            scale, (summary.get("settings") or {}).get("annotation_paper") or {},
            layer("dims"), lead, read_sheets=layout is None, twist=twist)
        carry, dims = made["carry"], made["dims"]
        done.append(made["done"])

    # -- several sheets: each frame trimmed round its stretch, and the match lines
    #: the match line labels the drafter put on each sheet, by id, with the box each takes
    drafted: Dict[str, dict] = {}
    if layout and len(sheets) > 1:
        lead, carry = carry, ""
        joined = yield from _trim_and_match(layout, alignment, layer("match"), lead,
                                            read_state=bool(sheet_work), dims=dims)
        carry, drafted = joined["carry"], joined["labels"]
        if sheet_work:
            state.update(joined["state"])
        cuts = [c["text"] for c in layout["cuts"]]
        done.append(
            f"set up {_and(sheets)} on {layout['size'].replace('_', ' ')} with viewports at "
            f"{SPEC['sheet']['scale_text_format'].format(fpi=layout['scale'])}"
            + (f" turned {_n(layout['twist'])}°" if layout["twist"] else "")
            + f", each framed round its stretch of {alignment}, and drew the match "
            f"line{'s' if len(cuts) > 1 else ''} at {_and(cuts)} ({_n(joined['half'])} ft each "
            f"side, on {layer('match')}), lettered on both sheets "
            f"{'each' if len(cuts) > 1 else 'it'} joins")

    # -- the base drawing
    if "reference" in todo:
        base = _BASEFILE.search(request)
        if not base:
            raise NotCovered("the task names no base drawing")
        ref = SPEC["reference"]
        calls = [_q("attach_reference", name=ref["name"], path=base.group(1), space=ref["space"])]
        results = yield Turn(
            f"Attach {base.group(1)} in model space as {ref['name']}, at its own coordinates, so "
            "the sheet's viewport shows it.", calls)
        _ok(results, calls)
        done.append(f"attached {base.group(1)} as {ref['name']}")

    # -- the curve data table, on each sheet that shows a curve
    if "table" in todo and not rows["curves"]:
        done.append(f"{alignment} has no curve, so no curve data table")
    elif "table" in todo:
        curves = rows["curves"]
        several = len(sheets) > 1
        # (a match line label the drafter set itself was read back then: its box is known)
        on_paper = [(name, eid) for name in sheets
                    for eid, e in (state[name].get("entities") or {}).items()
                    if e.get("type") in ("text", "table", "blockref")
                    and eid not in drafted.get(name, {})]
        # through a turned viewport the model's extents are no box on the paper, so there
        # the corner is checked once the table is down, against what the sheet shows under it
        calls = [] if twist else [_q("get_extents", space="model")]
        first = len(calls)
        if several:
            calls += [_q("xy_to_station", alignment=alignment,
                         point=list(state[name]["viewports"][0]["model_center"]))
                      for name in sheets]
        calls += [_q("get_entity", id=eid) for _name, eid in on_paper]
        results = []
        if calls and not twist:
            results = yield Turn(said(
                "Find the room for the table before it goes down: the extents of everything "
                "drawn in the model"
                + (", the station each sheet's viewport is centred on, to tell which stretch of "
                   "the line it holds" if several else "")
                + (", and the box of each thing already on the paper." if on_paper else ".")),
                calls)
        elif calls:
            reads = (["the station each sheet's viewport is centred on, to tell which stretch of "
                      "the line it holds"] if several else []) + (
                ["the box of each thing already on the paper"] if on_paper else [])
            results = yield Turn(said("Before the table goes down, read " + _and(reads) + "."),
                                 calls)
        _ok(results, calls)
        extents = results[0].get("extents") if not twist else None
        if not twist and not extents:
            raise NotCovered("nothing is drawn in the model")
        taken: Dict[str, list] = {name: list(drafted.get(name, {}).values())
                                  for name in sheets}
        for (name, _eid), result in zip(on_paper, results[len(calls) - len(on_paper):]):
            if result.get("bbox"):
                taken[name].append(tuple(result["bbox"]))
        listed: Dict[str, List[int]] = {}
        parts: List[str] = []
        for i, name in enumerate(sheets):
            if not several:
                listed[name] = [c["index"] for c in curves]
                continue
            matches = _match_lines(state[name])
            if not matches:
                raise NotCovered(f"{name} letters no match line to split the curves by")
            lo, hi = _share(matches, float(results[first + i]["station"]))
            listed[name] = [c["index"] for c in curves
                            if (hi is None or c["pc_station"] < hi["station"] - 1e-6)
                            and (lo is None or c["pt_station"] > lo["station"] + 1e-6)]
            stretch = (f"from the match line at {lo['text']} to the one at {hi['text']}"
                       if lo and hi else f"up to the match line at {hi['text']}" if hi
                       else f"from the match line at {lo['text']} on")
            shown = [c for c in curves if c["index"] in listed[name]]
            parts.append(
                f"{name} holds the line {stretch}"
                + (", which takes in " + _and([f"curve {c['index']} ({c['pc_station_text']} to "
                                               f"{c['pt_station_text']})" for c in shown])
                   if shown else ", and no curve falls on it, so it gets no table") + ".")
        tabled = [name for name in sheets if listed[name]]
        plan: Dict[str, tuple] = {}
        if not twist:
            corners = [(name, corner) for name in tabled for corner in (extents[:2], extents[2:])]
            calls = [_q("model_to_sheet", sheet=name, point=list(corner))
                     for name, corner in corners]
            results = yield Turn(said(
                " ".join(parts + [f"Map the two corners of the model's extents onto "
                                  f"{_and(tabled)}, to see where the plan falls on the paper."])),
                calls)
            _ok(results, calls)
            plan = {name: _rect(results[2 * i]["sheet_point"], results[2 * i + 1]["sheet_point"])
                    for i, name in enumerate(tabled)}
            parts = []
        calls, says, corner_of = [], list(parts), {}
        if twist:
            says.append(f"The viewport{'s are' if several else ' is'} turned {_n(twist)}°, so the "
                        "model's extents are no box on the paper: the table goes in the corner "
                        "and its place is checked once it is down.")
        for name in tabled:
            ua = state[name]["usable_area"]
            x, y = round(ua[0] + MARGIN_IN, 4), round(ua[3] - MARGIN_IN, 4)
            params = {"space": name, "alignment": alignment, "position": [x, y],
                      "layer": layer("tables")}
            if several:
                params["curves"] = listed[name]
            calls.append(_q("place_curve_table", **params))
            if (x, y) in corner_of:
                says.append(f"{name} has the same usable area as {corner_of[(x, y)]}, so the "
                            "same corner.")
                continue
            corner_of[(x, y)] = name
            says.append(
                (f"On {name} the model's extents fall between y {_n(plan[name][1])} and "
                 f"y {_n(plan[name][3])}, and the usable area runs from x {_n(ua[0])} to "
                 if not twist else f"On {name} the usable area runs from x {_n(ua[0])} to ")
                + f"{_n(ua[2])} and y {_n(ua[1])} to {_n(ua[3])}. The table's position is its "
                "top-left corner; put it a quarter inch inside the top-left corner of the usable "
                f"area: {_n(ua[0])} + {_n(MARGIN_IN)} = {_n(x)} and {_n(ua[3])} - "
                f"{_n(MARGIN_IN)} = {_n(y)}.")
        says.append(f"The engine's own curve table is the standard one, so only the layer is "
                    f"named: {layer('tables')}.")
        results = yield Turn(said(" ".join(says)), calls)
        _ok(results, calls)
        tables = [result["created"][0] for result in results]
        calls = [_q("get_entity", id=tid) for tid in tables]
        results = yield Turn("Read each table back for the box it takes up, and check it against "
                             "the plan and what was already on the paper.", calls)
        _ok(results, calls)
        checked: Dict[str, str] = {}
        #: on a turned sheet, the tables inside their viewport's frame: checked in the model
        under: Dict[str, tuple] = {}
        for name, tid, result in zip(tabled, tables, results):
            box, ua = tuple(result["bbox"]), state[name]["usable_area"]
            view = state[name]["viewports"][0]
            if not (ua[0] <= box[0] and ua[1] <= box[1] and box[2] <= ua[2] and box[3] <= ua[3]):
                raise NotCovered(f"the table does not fit the usable area of {name}")
            if any(_apart(box, other, MARGIN_IN) is None for other in taken[name]):
                raise NotCovered(f"the table on {name} is not clear of what was on the paper")
            where = (f"{tid} takes up x {_n(box[0])} to {_n(box[2])} and y {_n(box[1])} to "
                     f"{_n(box[3])} on {name}.")
            way = _apart(box, plan[name], MARGIN_IN) if not twist else None
            frame = _frame(view)
            (cx, cy), w, h = view["center_paper"], view["width_in"], view["height_in"]
            if way == "y":
                where += (f" The model's extents reach up to y {_n(plan[name][3])} there, so the "
                          "table is clear above the plan.")
            elif way == "x":
                where += (f" The model's extents start at x {_n(plan[name][0])} there, so the "
                          "table is clear to the left of the plan.")
            elif _apart(box, frame, MARGIN_IN) == "y":
                where += (f" The viewport's frame tops out at {_n(cy)} + {_n(h)} / 2 = "
                          f"{_n(frame[3])}, below the table, so nothing the model shows "
                          "reaches it.")
            elif _apart(box, frame, MARGIN_IN) == "x":
                where += (f" The viewport's frame starts at {_n(cx)} - {_n(w)} / 2 = "
                          f"{_n(frame[0])}, right of the table, so nothing the model shows "
                          "reaches it.")
            elif twist:
                under[name] = box
            else:
                raise NotCovered(f"the top-left corner of {name} is not clear of the plan")
            checked[name] = where
        if under:
            # the table's box and a quarter inch round it, taken back to the model: the box
            # those four points span there holds whatever the sheet shows under the table
            calls, says, grown = [], [], {}
            for name, box in under.items():
                a, b, c, d = (float(_n(v)) for v in box)
                g = (round(a - MARGIN_IN, 3), round(b - MARGIN_IN, 3),
                     round(c + MARGIN_IN, 3), round(d + MARGIN_IN, 3))
                grown[name] = g
                says.append(
                    f"{checked[name]} That is inside the viewport's frame, so see what the "
                    f"sheet shows there. A quarter inch round the table: {_n(a)} - "
                    f"{_n(MARGIN_IN)} = {_n(g[0])}, {_n(b)} - {_n(MARGIN_IN)} = {_n(g[1])}, "
                    f"{_n(c)} + {_n(MARGIN_IN)} = {_n(g[2])} and {_n(d)} + {_n(MARGIN_IN)} = "
                    f"{_n(g[3])}.")
                calls += [_q("sheet_to_model", sheet=name, point=[x, y])
                          for x, y in ((g[0], g[1]), (g[2], g[1]), (g[2], g[3]), (g[0], g[3]))]
            says.append("Take the corners of that box back to the model.")
            results = yield Turn(" ".join(says), calls)
            _ok(results, calls)
            calls = []
            for i, name in enumerate(under):
                pts = [r["point"] for r in results[4 * i:4 * i + 4]]
                bounds = [min(q[0] for q in pts), min(q[1] for q in pts),
                          max(q[0] for q in pts), max(q[1] for q in pts)]
                calls.append(_q("find_entities", bounds=bounds, visible_on=name))
            results = yield Turn(
                "The view is turned, so the corners span a wider box in the model than the "
                f"table itself. Search that box for anything {_and(list(under))} "
                f"{'shows' if len(under) == 1 else 'show'}.", calls)
            _ok(results, calls)
            for name, result in zip(under, results):
                if result.get("total"):
                    raise NotCovered(f"the top-left corner of {name} is not clear of the plan")
                checked[name] = (f"Nothing {name} shows from the model is within a quarter inch "
                                 "of its table.")
        carry = " ".join([checked[name] for name in tabled]
                         + (["Nothing that was on the paper is near."]
                            if any(taken[name] for name in tabled) else []))
        done.append(f"placed the curve data table on {_and(tabled)} ({layer('tables')}), clear of "
                    "the plan")

    # -- the north arrow, on each sheet that has none
    if "north" in todo:
        arrow = SPEC["sheet"]["north_arrow"]
        if arrow["block"] not in (summary.get("blocks") or []):
            raise NotCovered(f"the document has no {arrow['block']} block")
        bare = [name for name in sheets
                if not any(e.get("type") == "blockref" and e.get("block_name") == arrow["block"]
                           for e in (state[name].get("entities") or {}).values())]
        if bare:
            px, py = arrow["position"]
            turned = {"rotation_deg": twist} if twist else {}
            calls = [_q("insert_block", space=name, block_name=arrow["block"], position=[px, py],
                        scale=arrow["scale"], layer=layer("symbols"), **turned) for name in bare]
            north = ("No viewport is turned, so north is up the sheet and the arrow stands as it "
                     "is." if not twist else
                     f"The viewport{'s are' if len(sheets) > 1 else ' is'} turned {_n(twist)}°, "
                     f"which turns the model's north the same way on the paper, so the arrow is "
                     f"turned {_n(twist)}° to point to it.")
            results = yield Turn(said(
                f"The drawing has the {arrow['block']} block, and {_and(bare)} "
                f"{'has' if len(bare) == 1 else 'have'} no north arrow yet. The office's place "
                f"for it is the upper right of the sheet, at x {_n(px)}, y {_n(py)} and a scale "
                f"of {_n(arrow['scale'])}, on {layer('symbols')}. {north}"), calls)
            _ok(results, calls)
            near = [(name, result["created"][0]) for name, result in zip(bare, results)
                    if drafted.get(name)]
            if near:
                # the match line labels went down before the arrow: see that it clears them
                calls = [_q("get_entity", id=eid) for _name, eid in near]
                results = yield Turn("Read each north arrow back for the box it takes, to see it "
                                     "is clear of the match line lettering put on its sheet.",
                                     calls)
                _ok(results, calls)
                for (name, _eid), result in zip(near, results):
                    box = tuple(result["bbox"])
                    if any(_apart(box, other, MARGIN_IN) is None
                           for other in drafted[name].values()):
                        raise NotCovered(f"the north arrow's place on {name} is taken by a match "
                                         f"line label")
                carry = (f"The north arrow{'s are' if len(near) > 1 else ' is'} clear of the "
                         f"match line lettering.")
            done.append(f"put the north arrow on {_and(bare)}"
                        + (f", turned {_n(twist)}° to north" if twist else ""))

    # -- the title block of every sheet
    if "title" in todo:
        stated = stated_title(request)
        project, about = meta.get("project_name"), str(meta.get("description") or "")
        calls, blank, on_record = [], [], {}
        for name in sheets:
            keys = state[name].get("title_block_keys") or []
            have = state[name].get("title_block_fields") or {}
            if stated:
                if stated["sheet_numbers"] is None:  # a layout the task left to the drafter
                    want = {k: v for k, v in stated.items() if k != "sheet_numbers"}
                    want["total_sheets"] = str(len(sheets))
                elif name not in stated["sheet_numbers"]:
                    raise NotCovered(f"the task's title block does not number {name}")
                else:
                    want = {k: v for k, v in stated.items() if k != "sheet_numbers"}
            else:
                want = {"sheet_title": SHEET_TITLE, "total_sheets": str(len(sheets)),
                        "scale": SPEC["sheet"]["scale_text_format"].format(
                            fpi=state[name]["viewports"][0]["feet_per_inch"])}
                if project:
                    want["project"] = project
                if project and about.startswith(project) and ", " in about:
                    want["agency"] = about.rsplit(", ", 1)[1]
                # a field the document's own record carries under the field's name
                on_record = {k: str(meta[k]) for k in keys
                             if k not in want and str(meta.get(k) or "").strip()}
                want.update(on_record)
            want["sheet_number"] = name
            fields = {k: want[k] for k in keys
                      if k in want and str(have.get(k, "")).strip() != want[k]}
            blank = [k for k in keys if k not in want and not str(have.get(k, "")).strip()]
            if fields:
                calls.append(_q("fill_title_block", sheet=name, fields=fields))
        if calls:
            if stated and stated["sheet_numbers"] is None:
                say = ("The task gives every value of the title block but the two the layout "
                       "decides. Letter them as written, each sheet under its own number, and "
                       f"the number of sheets as the file now holds: {_s(len(sheets), 'sheet')}.")
            elif stated:
                say = ("The task gives every value of the title block. Letter them as written, "
                       "each sheet under its own number.")
            else:
                say = (f"The task gives no title block values, so they come from the document. "
                       f"Its description reads \"{about}\": the project, then the county, then "
                       f"the agency. Each sheet is numbered by its name, the file holds "
                       f"{_s(len(sheets), 'sheet')}, and the viewport shows the model at "
                       f"{_n(scale)} ft to the inch, which is lettered "
                       f"{SPEC['sheet']['scale_text_format'].format(fpi=scale)}. It is a plan "
                       f"sheet of a roadway, so the title is {SHEET_TITLE}.")
                if on_record:
                    say += (" The document's own record gives "
                            + _and([f"{k} {v}" for k, v in on_record.items()])
                            + ", lettered as they stand.")
                if blank:
                    say += (f" Nothing in the document gives {_and(blank)}, so "
                            f"{'that is' if len(blank) == 1 else 'those are'} left blank and "
                            "not made up.")
            results = yield Turn(said(say), calls)
            _ok(results, calls)
            done.append(f"filled the title block of {_and(sheets)}"
                        + (f", leaving {_and(blank)} blank because nothing in the document gives "
                           f"{'it' if len(blank) == 1 else 'them'}" if blank else ""))

    return Turn(carry, [_q("submit", note="Done: " + "; ".join(done) + ".")])


def covers(task: Task) -> List[str]:
    """The phases ``task`` needs that the grounded drafter cannot do yet:
    empty when it can do the task."""
    ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
    return [p for p in ttype.solution_phases() if p not in COVERED]


class GroundedAgent(Agent):
    """The grounded reference drafter as an episode agent.  It takes the
    task's asked phases at ``reset`` and the task text from the first
    observation, and nothing else of the task."""
    name = "grounded"

    def __init__(self):
        self._solver: Optional[Generator[Turn, List[dict], Turn]] = None
        self._phases: List[str] = []
        self._say = ""

    def reset(self, task: Task, level: str, mode: str) -> None:
        ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
        self._phases = ttype.solution_phases()
        self._solver = None
        self._say = ""

    def act(self, observation: dict):
        try:
            if self._solver is None:
                self._solver = solve(observation["brief"], self._phases)
                turn = next(self._solver)
            else:
                turn = self._solver.send(observation["results"])
        except StopIteration as finished:
            turn = finished.value
        self._say = turn.say
        return list(turn.calls)

    def turn_record(self) -> dict:
        return {"text": self._say}

    def describe(self) -> dict:
        return {"model": "grounded-reference", "provider": "harness"}


# ------------------------------------------------------------ the audit


def _flatten(value, strings: set, numbers: list) -> None:
    """Every string (keys too) and number in a JSON value; the numbers a
    string writes (``text 5 ft``, ``125+00.00``) count as well."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.append(float(value))
    elif isinstance(value, str):
        strings.add(value)
        numbers.extend(numbers_in(value))
    elif isinstance(value, dict):
        for key, item in value.items():
            strings.add(str(key))
            _flatten(item, strings, numbers)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _flatten(item, strings, numbers)


def numbers_in(text: str) -> List[float]:
    """The numbers a text writes: plain ones, and each station as feet."""
    found = [int(a) * 100 + float(b) for a, b in _STATION.findall(text)]
    found += [float(m) for m in _NUMBER.findall(text)]
    return found


def _standards():
    strings: set = set()
    numbers: list = []
    _flatten(SPEC, strings, numbers)
    return strings, numbers


#: what spec v1 fixes, as the audit reads it: a value found here is a drafting standard
STANDARDS = _standards()
#: what a drafter chooses for itself, where no standard speaks
CHOICES = (MARGIN_IN, ROOM_IN, LETTERING_IN, MATCH_HALF_IN, FULL_ROWS) + CLEAR_STEPS
#: ... and, where a task leaves the sheet breaks to it, how far it keeps a match line from a
#: curve point (its own line, so a change to the tuple above merges without touching this)
CHOICES += (MATCH_CLEAR_FT,)
#: a design point named by its index: the kind is the engine's word, the index a number seen
_ANCHOR = re.compile(r"^(BEGIN|END|PI|PC|PT|BC|EC|MC|T|C|EQ)-(\d+)$")
#: a sheet's number, as a layout left to the drafter counts on from the first (C-102)
_SHEET_NUMBER = re.compile(r"^([A-Z]+)-(\d+)$")
#: a plan scale as a title block letters it
_PLAN_SCALE = re.compile(r"^1\"\s*=\s*(\d+(?:\.\d+)?)'$")
#: a point given by station and offset, as ``draw_station_offset`` takes it
_STATION_OFFSET = re.compile(rf"^({_ST})@(\d+(?:\.\d+)?)[LR]$")
#: a match line's label as the office letters it
_MATCH_LABEL = re.compile(rf"^MATCH LINE STA ({_ST}) SEE SHEET (\S+)$")
#: a station inside a longer text, for a note restationed
_STA_TOKEN = re.compile(rf"(?<![\d.])({_ST})")
#: a sum worked out in the shown work: ``21.5 - 0.25 = 21.25``, ``11.7 + 5.67 / 2 = 14.535``
_TERM = r"\d+(?:\.\d+)?"
_WORKED = re.compile(rf"(?<![\w.+*/-])({_TERM}(?: [-+*/] {_TERM})+) = (-?{_TERM})")
TOLERANCE = 0.005
#: a size a tool's definition gives as a ratio of the text height
_RATIO = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?) x the text height")
#: a part of a longer string counts as read from it from this length up
PART_MIN = 4


def worked_sums(text: str) -> List[tuple]:
    """The arithmetic a line of shown work does: ``[(operands, stated result,
    whether the sum is right)]``.  ``*`` and ``/`` bind before ``+`` and ``-``."""
    found = []
    for expression, stated in _WORKED.findall(text):
        tokens = expression.split(" ")
        operands, terms, signs = [float(t) for t in tokens[0::2]], [], []
        terms.append(operands[0])
        right = True
        for op, value in zip(tokens[1::2], operands[1:]):
            if op == "*":
                terms[-1] *= value
            elif op == "/":
                right = right and value != 0
                terms[-1] = terms[-1] / value if value else 0.0
            else:
                signs.append(op)
                terms.append(value)
        total = terms[0]
        for op, term in zip(signs, terms[1:]):
            total = total + term if op == "+" else total - term
        found.append((operands, float(stated), right and abs(total - float(stated)) <= 0.001))
    return found


class Seen:
    """What the model has in front of it at a point in an episode."""

    def __init__(self, text: str, rules: Sequence = ()):
        self.text = text
        self.strings: set = set()
        self.numbers: List[float] = numbers_in(text)
        #: a task family's own string forms: ``rule(value, seen) -> bool`` (``audit``'s ``rules``)
        self.rules = tuple(rules)

    def add(self, result) -> None:
        _flatten(result, self.strings, self.numbers)

    def number(self, value: float, standards: bool = True) -> bool:
        target = abs(float(value))  # a distance to the left is written negative
        return (any(abs(abs(n) - target) <= TOLERANCE for n in self.numbers)
                or (standards and any(abs(abs(n) - target) <= TOLERANCE
                                      for n in STANDARDS[1] + list(CHOICES))))

    def worked(self, text: str) -> None:
        """Take in what a line of shown work works out: a sum that is right,
        on numbers already grounded, grounds its result."""
        for operands, stated, right in worked_sums(text):
            if right and all(self.number(v) for v in operands):
                self.numbers.append(stated)

    def string(self, value: str, tool_text: str) -> bool:
        if not value or value in self.strings or value in self.text or value in STANDARDS[0]:
            return True
        if value in tool_text:
            return True
        if any(rule(value, self) for rule in self.rules):
            return True
        anchor = _ANCHOR.match(value)
        if anchor:  # the index has to be one the design showed: no standard names a curve
            return self.number(float(anchor.group(2)), standards=False)
        numbered = _SHEET_NUMBER.match(value)
        if numbered and re.search(rf"numbered from {re.escape(numbered.group(1))}-\d", self.text):
            # a sheet numbered on from the one the task names: its number has to be worked out
            return self.number(float(numbered.group(2)), standards=False)
        if _STATION.fullmatch(value):
            return self.number(numbers_in(value)[0], standards=False)
        scale = _PLAN_SCALE.match(value)
        if scale:  # the scale has to be one a viewport showed, not just an allowed one
            return self.number(float(scale.group(1)), standards=False)
        offset = _STATION_OFFSET.match(value)
        if offset:  # a station seen, and a distance off it that is grounded as a number is
            return (self.number(numbers_in(offset.group(1))[0], standards=False)
                    and self.number(float(offset.group(2))))
        if _STATION.search(value):  # a text read, its stations restationed to grounded ones
            shape = _STA_TOKEN.sub("#", value)
            if any(_STATION.search(seen) and _STA_TOKEN.sub("#", seen) == shape
                   for seen in self.strings):
                return all(self.number(numbers_in(st)[0], standards=False)
                           for st in _STA_TOKEN.findall(value))
        label = _MATCH_LABEL.match(value)
        if label:  # the office's form: the station and the sheet have to be ones seen
            return (self.number(numbers_in(label.group(1))[0], standards=False)
                    and self.string(label.group(2), tool_text))
        if ":" in value:  # an alignment named through its reference
            return all(self.string(part, tool_text) for part in value.split(":"))
        # a part of something read: the agency out of the project's description
        return len(value) >= PART_MIN and any(value in seen for seen in self.strings)


def _walk(value, path: str):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")
    else:
        yield path, value


def audit(text: str, tools: Sequence[dict], turns: Sequence[dict], rules: Sequence = (),
          numbers: Sequence[float] = ()) -> List[dict]:
    """Every value an episode's calls carry that was not grounded when the
    call was made, and every number its shown work states that was not:
    ``[{"turn", "tool", "path", "value"}]``, empty for a grounded episode.
    ``text`` is the task as the model was given it, ``tools`` the definitions
    it was shown, ``turns`` the episode's turn records.  A task family with
    forms of its own (``trajectories.reasoning``) adds ``rules``, each
    ``rule(value, seen) -> bool`` for a string the general forms do not ground,
    and ``numbers``, the constants it states as rules; the D1 sets pass neither."""
    tool_text = {t["name"]: json.dumps(t, ensure_ascii=False) for t in tools}
    seen = Seen(text, rules)
    seen.numbers += [float(n) for n in numbers]
    # a size a tool's definition gives as a ratio of the text height (place_dimension's
    # arrowheads, ``1.2 x the text height``) is the tool's own word on it
    seen.numbers += [float(m) for t in tool_text.values() for m in _RATIO.findall(t)]
    findings: List[dict] = []
    for turn in turns:
        assistant = turn.get("assistant") or {}
        n = turn.get("n")
        seen.worked(assistant.get("text") or "")
        for number in numbers_in(assistant.get("text") or ""):
            if not seen.number(number):
                findings.append({"turn": n, "tool": None, "path": "say", "value": number})
        for call in assistant.get("tool_calls") or []:
            name, params = call.get("name"), call.get("params") or {}
            if name == "submit":
                for number in numbers_in(str(params.get("note") or "")):
                    if not seen.number(number):
                        findings.append({"turn": n, "tool": name, "path": "note", "value": number})
                continue
            for path, value in _walk(params, ""):
                if isinstance(value, bool) or value is None:
                    continue
                grounded = (seen.number(value) if isinstance(value, (int, float))
                            else seen.string(str(value), tool_text.get(name, "")))
                if not grounded:
                    findings.append({"turn": n, "tool": name, "path": path, "value": value})
        # what the calls put on the page counts from the next turn on
        for call, result in zip(assistant.get("tool_calls") or [], turn.get("results") or []):
            if result.get("ok"):
                seen.add(call.get("params") or {})
            seen.add(result)
    return findings


def twist_ignored(task: Task, doc) -> List[str]:
    """On a twisted task (the generator's twist dial), the model labels the
    drafter added that were not lettered to read through the sheets' twist:
    their ids, empty on any other task.

    The verifier takes a label's own record for where it belongs and marks it
    down only when it plots upside down, which lettering made for the model
    does on some lines and not on others: over ``d1-train-twist``, the
    reference's commands with the twist taken out still score 100 on 112 of
    the 267 tasks that only letter the model.  Such an episode never looked at
    the viewport, so it is no demonstration of the skill and is not kept."""
    twist = float(task.brief.deliverable.get("view_rotation") or 0.0)
    if not twist:
        return []
    from roaddraft.design.labels import LABEL_KINDS
    from roaddraft.document.document import Document
    from roaddraft.document.entities import Text
    from roaddraft.document.entities import Dimension
    given = set(Document.from_dict(task.baseline).model_entities)
    tol = float(SPEC["tolerances"]["rotation_deg"])

    def off(view_rotation) -> bool:
        return abs((float(view_rotation or 0.0) - twist + 180.0) % 360.0 - 180.0) > tol

    return sorted(
        e.id for e in doc.model_entities.values()
        if e.id not in given and (
            (isinstance(e, Text) and e.anchor and e.anchor.get("kind") in LABEL_KINDS
             and off(e.anchor.get("view_rotation")))
            # a dimension's number is lettering too (plan decision 9)
            or (isinstance(e, Dimension) and off(e.view_rotation))))


# ------------------------------------------------------------ recording


def record_task(task: Task, level: str = "vague", out_root=None, agent: Optional[Agent] = None,
                run_id: str = "") -> dict:
    """Run one task under ``agent`` (the grounded drafter by default) and
    audit what it did.  The row says whether the recording is training data:
    ``kept`` when it submitted, scored 100, nothing was ungrounded and, on a
    twisted sheet, its lettering was made for the twist (``twist_ignored``)."""
    from roaddraft.eval.episode import Episode, EpisodeConfig
    episode = Episode(task, agent or GroundedAgent(), EpisodeConfig(level=level, run_id=run_id),
                      out_root=out_root)
    result = episode.run()
    ungrounded = audit(episode.brief_text, episode.tools, episode.turns)
    blind = twist_ignored(task, episode.session.doc) if episode.session is not None else []
    from roaddraft.tasks.revise import left_stale
    behind = left_stale(task, episode.session.doc) if episode.session is not None else []
    # where the score fell short: each graded check below full credit, and why
    lost = {c.id: {"credit": round(c.credit, 4),
                   "findings": sorted({f.note or f.code for f in c.findings})[:6]}
            for c in result.report.in_scope() if c.credit < 1.0}
    return {"task_id": task.task_id, "task_type": task.brief.task_type, "level": level,
            "termination": result.termination, "error": result.error,
            "effective": result.effective_score, "turns": result.turns, "steps": result.steps,
            "ungrounded": ungrounded, "twist_ignored": blind, "left_stale": behind,
            "lost": lost,
            "path": result.path,
            "kept": (result.termination == "submit" and result.effective_score == 100.0
                     and not ungrounded and not blind and not behind)}


def record(taskset: str, out, level: str = "vague", limit: Optional[int] = None,
           types: Optional[Iterable[str]] = None) -> dict:
    """Record the grounded reference of every task of ``taskset`` the drafter
    covers, under ``out``: the episode files and ``index.json``."""
    from roaddraft.eval import taskset as tasksets
    out = Path(out)
    rows: List[dict] = []
    entries = [e for e in tasksets.entries(taskset) if not types or e["task_type"] in set(types)]
    for entry in entries[:limit]:
        task = tasksets.task_from_entry(entry)
        missing = covers(task)
        if missing:
            rows.append({"task_id": task.task_id, "task_type": entry["task_type"], "level": level,
                         "covered": False, "missing": missing, "kept": False})
            continue
        rows.append({"covered": True, **record_task(task, level, out_root=out, run_id=out.name)})
    by_type: Dict[str, Counter] = {}
    for row in rows:
        tally = by_type.setdefault(row["task_type"], Counter())
        tally["tasks"] += 1
        tally["covered"] += bool(row.get("covered"))
        tally["kept"] += bool(row["kept"])
    index = {"taskset": taskset, "level": level, "covered_phases": list(COVERED),
             "tasks": len(rows), "covered": sum(bool(r.get("covered")) for r in rows),
             "kept": sum(bool(r["kept"]) for r in rows),
             "by_type": {t: dict(c) for t, c in sorted(by_type.items())}, "rows": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories.grounded",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--taskset", default="d1-train")
    parser.add_argument("--out", required=True)
    parser.add_argument("--level", default="vague", choices=("vague", "explicit"))
    parser.add_argument("--type", action="append", dest="types")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    index = record(args.taskset, args.out, args.level, args.limit, args.types)
    print(f"{args.taskset} at the {args.level} level: {index['tasks']} tasks, "
          f"{index['covered']} covered, {index['kept']} kept (scored 100, nothing ungrounded)")
    for ttype, tally in index["by_type"].items():
        print(f"  {ttype:20s} {tally.get('kept', 0):4d} kept of {tally.get('covered', 0):4d} covered "
              f"of {tally['tasks']:4d}")
    bad = [r for r in index["rows"] if r.get("covered") and not r["kept"]]
    for row in bad[:10]:
        print(f"  NOT KEPT {row['task_id']} {row['task_type']}: {row['termination']} "
              f"{row['effective']} {row.get('error') or ''} {row['ungrounded'][:3]} "
              f"{sorted(row.get('lost') or {})}")
    return 1 if bad else 0


__all__ = ["COVERED", "NotCovered", "Turn", "GroundedAgent", "solve", "covers", "audit",
           "twist_ignored", "record_task", "record", "request_of", "stated_alignment",
           "stated_title", "stated_layout", "stated_open", "stated_revision", "numbers_in",
           "worked_sums",
           "STANDARDS",
           "CHOICES"]

if __name__ == "__main__":
    sys.exit(main())
