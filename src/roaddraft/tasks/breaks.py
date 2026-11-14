"""Sheet breaks left to the drafter: the training-only type ``plan-sheet-breaks``.

Every other seeded layout task names its sheets and the stations they break
at, at both prompt levels, and the sheet check (D1-00) grades against the
generator's own breaks.  So nothing seeded asks what the ``p05`` pilots ask:
given a line and a scale, how many plan sheets does it take, and where do they
break?  This type does (training plan section 6, decision 8, Robert
2026-11-13: a training-only type with a check of its own, no tool change).  Its
prompt gives the line, the scale, the sheet size and the first sheet's number;
the count and the breaks are the drafter's.

The task itself is the generator's whole plan sheet job (``plan-sheet``) on a
line long enough for the sheets asked of the dial, and its reference solution
drafts the generator's own breaks.  What is new is how it is graded
(``verify.breaks``): the drafter's sheets and breaks are read off its drawing,
judged by the rules below, and the rest of the sheet work (lettering,
legibility, each sheet's curve table, title blocks, north arrows) is graded
against the truth this module builds for the breaks the drafter chose
(``rebuilt``), by the generator's own derivation of a layout from its breaks
(``sheets_for``).

The rules, each the generator's own (``tasks.generator``) or the pilot
grader's (``probes.pilot.layout``), none stricter than its source:

- *How much a sheet holds* (``stretch_fits``).  The generator fits a sheet's
  share of the line, with its lettering and a quarter inch margin
  (``VIEWPORT_MARGIN_IN``), into the office's plan window (the spec's
  ``fit_window_in``, 26 by 15 in), at the twist every viewport of the layout
  shares.  Counted here on the bare centerline with the same margin, the way
  the pilot grader counts on the bare centerline: a stretch that fits with its
  lettering fits without it, so the count below is never more than the
  generator's.
- *The fewest sheets* (``fewest``): the fewest stretches, broken where the
  office breaks a line (``office_breaks``: whole stations on a tangent, sixty
  feet clear of its ends, the generator's ``_match_options``), that each fit.
  A layout passes on any count up to it.  A task is only made when the
  generator's own count is that fewest (``opened``), so its reference passes.
- *Where a match line is sound* (``unsound``): sixty feet (``MATCH_CLEAR_FT``)
  along the line from every point that carries lettering square to the line or
  beside it: the ends of the line, each curve's BC and EC, a curve's middle
  (its number's bubble) and a station equation.  On a tangent that is the
  generator's rule to the foot.  The generator never breaks on a curve and the
  pilot grader takes a break anywhere, so a break on a curve is taken here when
  it is that clear of the curve's own lettering.  A whole station is not asked
  for (the pilot grader's solver cuts at ten feet).
"""
from __future__ import annotations

import copy
import dataclasses
import math
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.horizontal import Alignment, CurveElement, TangentElement
from roaddraft.document.sheets import SHEET_SIZES, Sheet
from roaddraft.tasks import generator as gen
from roaddraft.tasks.brief import GroundTruth, Task
from roaddraft.tasks.ground_truth import sheet_rows
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import OPEN_BREAKS

#: the type's name (``tasks.types.TRAIN_TASK_TYPES``)
TYPE = "plan-sheet-breaks"
#: the number the first sheet of a layout carries, which the prompt gives; the rest are
#: numbered on from it along the line (the generator's ``SHEET_NAMES``)
FIRST_SHEET = gen.SHEET_NAMES[0]
#: the office's stationing interval: a whole station is a multiple of it
STATION_FT = float(DRAFTING_SPEC_V1["stationing"]["interval_ft"])
#: how far along the line a match line keeps from a lettered point (the generator's)
CLEAR_FT = gen.MATCH_CLEAR_FT
#: the margin a sheet's stretch keeps inside the plan window, on paper (the generator's)
MARGIN_IN = gen.VIEWPORT_MARGIN_IN


def sheet_names(count: int, first: str = FIRST_SHEET) -> List[str]:
    """``count`` sheets numbered on from ``first``: C-101, C-102, ..."""
    prefix, _, number = first.rpartition("-")
    return [f"{prefix}-{int(number) + k:0{len(number)}d}" for k in range(count)]


def office_breaks(align: Alignment) -> List[float]:
    """Where the office breaks a line, as distances from BEGIN: every whole
    station on a tangent at least ``CLEAR_FT`` from each end of it (the
    generator's ``_match_options``, without its three hundred feet from the
    ends of the line, which only keeps its own sheets from being short)."""
    begin = float(align.begin_station)
    out: List[float] = []
    k = math.floor(begin / STATION_FT) + 1
    while k * STATION_FT - begin < align.length:
        d = k * STATION_FT - begin
        k += 1
        if d <= 0:
            continue
        i, _ = align.element_at(d)
        el = align.elements[i]
        if not isinstance(el, TangentElement):
            continue
        if d - el.start_dist < CLEAR_FT or el.end_dist - d < CLEAR_FT:
            continue
        out.append(d)
    return out


def lettered_points(align: Alignment) -> List[Tuple[float, str]]:
    """``(distance from BEGIN, what it is)`` of every point of the line whose
    lettering a match line keeps clear of."""
    points: List[Tuple[float, str]] = [(0.0, "the beginning of the line"),
                                       (float(align.length), "the end of the line")]
    n = 0
    for el in align.elements:
        if isinstance(el, CurveElement):
            n += 1
            points += [(float(el.start_dist), f"the BC of curve {n}"),
                       (float(el.end_dist), f"the EC of curve {n}"),
                       ((float(el.start_dist) + float(el.end_dist)) / 2.0,
                        f"the middle of curve {n}, where its number stands")]
    begin = float(align.begin_station)
    points += [(float(q.raw_station) - begin, "the station equation") for q in align.equations]
    return sorted(points)


def unsound(align: Alignment, dist: float) -> Optional[str]:
    """Why a match line ``dist`` from BEGIN is not sound, or None when it is:
    at least ``CLEAR_FT`` along the line from every lettered point."""
    if not 0.0 < dist < align.length:
        return "it is not on the line"
    for at, what in lettered_points(align):
        if abs(dist - at) < CLEAR_FT - 1e-6:
            return f"it is {abs(dist - at):.2f} ft from {what}; a match line keeps {CLEAR_FT:g} ft clear"
    return None


def stretch_fits(laid: Alignment, lo: float, hi: float, fpi: float) -> bool:
    """Whether the stretch ``lo``..``hi`` of the line as the sheets show it
    (``generator._laid``) fits the office's plan window at ``fpi`` feet to the
    inch, with the generator's margin all round."""
    box = geo.bbox_of_points(gen.segment_points(laid, lo, hi))
    return gen._fits_window(box, fpi, pad=MARGIN_IN * fpi)


def fewest(align: Alignment, fpi: float, turn: float = 0.0) -> Optional[int]:
    """The fewest sheets that carry the line at ``fpi`` feet to the inch
    through viewports turned ``turn``: the fewest stretches, broken where the
    office breaks a line, that each fit the plan window.  None when no such
    breaks do it."""
    laid = gen._laid(align, turn)
    length = min(float(align.length), float(laid.length))
    cuts = [0.0] + [d for d in office_breaks(align) if d < length] + [length]
    best = {0: 0}
    for j in range(1, len(cuts)):
        counts = [best[i] + 1 for i in range(j)
                  if i in best and stretch_fits(laid, cuts[i], cuts[j], fpi)]
        if counts:
            best[j] = min(counts)
    return best.get(len(cuts) - 1)


def sheets_for(align: Alignment, fpi: float, turn: float, match_dists: Sequence[float],
               names: Sequence[str], title: dict, size: Optional[str] = None) -> List[dict]:
    """The sheets of a deliverable for a layout that breaks ``match_dists``
    from BEGIN, as the generator derives them from its own breaks
    (``generator.generate_task``, the same helpers in the same order): each
    sheet's viewport round its stretch and its lettering, the curves it shows,
    where its curve table goes, its title block and its match lines.  ``title``
    is any sheet's title block fields; the number and the total are set here.

    The generator's own loop is not shared code (another change was open in it
    when this was written), so ``opened`` checks, on every task made, that this
    gives the generator's sheets back from the generator's breaks."""
    spec = DRAFTING_SPEC_V1
    sheet_spec = spec["sheet"]
    size = size or sheet_spec["size"]
    width, height = SHEET_SIZES[size]
    columns = list(spec["curve_table"]["columns"])
    table_h = spec["text"]["table_height_in"]
    begin_station = float(align.begin_station)
    st = align.stations()
    laid = gen._laid(align, turn)
    names = list(names)
    n_sheets = len(names)
    match_dists = [float(d) for d in match_dists]
    bounds = [0.0] + match_dists + [align.length]
    label_boxes = gen._label_boxes(align, fpi, turn) if n_sheets > 1 else []
    out: List[dict] = []
    for i, name in enumerate(names):
        sheet = Sheet(id=f"SH-{i + 1:03d}", name=name, size=size, width_in=width,
                      height_in=height)
        lo, hi = bounds[i], bounds[i + 1]
        if turn:
            hi = min(hi, laid.length)
        bb = geo.bbox_of_points(gen.segment_points(laid, lo, hi))
        viewport = {"center_paper": list(sheet_spec["viewport"]["center_paper"]),
                    "width_in": sheet_spec["viewport"]["width_in"],
                    "height_in": sheet_spec["viewport"]["height_in"],
                    "model_center": [gen._round2((bb[0] + bb[2]) / 2.0),
                                     gen._round2((bb[1] + bb[3]) / 2.0)],
                    "feet_per_inch": float(fpi), "rotation_deg": 0.0}
        if n_sheets > 1:
            padded = gen._sheet_box(laid, lo, hi, fpi, label_boxes)
            viewport["model_center"] = [gen._round2((padded[0] + padded[2]) / 2.0),
                                        gen._round2((padded[1] + padded[3]) / 2.0)]
            viewport["width_in"] = gen._round2((padded[2] - padded[0]) / fpi)
            viewport["height_in"] = gen._round2((padded[3] - padded[1]) / fpi)
        if turn:
            centre = gen._about(viewport["model_center"], align.pis[0].point, -turn)
            viewport["model_center"] = [gen._round2(centre[0]), gen._round2(centre[1])]
            viewport["rotation_deg"] = turn
        lo, hi = bounds[i], bounds[i + 1]
        on_sheet = [k + 1 for k, c in enumerate(align.curves())
                    if c.start_dist < hi - 1e-6 and c.end_dist > lo + 1e-6]
        matches, label_rects = [], []
        for d in match_dists:
            if d not in (lo, hi):
                continue
            raw = begin_station + d
            other = names[i + 1] if d == hi else names[i - 1]
            text = st.format(raw)
            label = f"MATCH LINE STA {text} SEE SHEET {other}"
            side, rotation, offset, rect = gen._match_layout(align, text, label, viewport, sheet)
            label_rects.append(rect)
            matches.append({
                "station": float(raw), "station_text": text,
                "half_width_ft": gen._round2(gen.MATCH_HALF_IN * fpi), "other_sheet": other,
                "label": label, "label_offset_in": offset, "side": side, "rotation": rotation})
        out.append({
            "name": name, "size": size, "viewport": viewport,
            "station_range": [float(begin_station + lo), float(begin_station + hi)],
            "curves": on_sheet,
            "curve_table_position": gen._curve_table_position(align, on_sheet, sheet, viewport,
                                                              columns, table_h, avoid=label_rects),
            "title_block_fields": {**title, "sheet_number": name, "total_sheets": str(n_sheets)},
            "matches": matches})
        if turn:
            na = sheet_spec["north_arrow"]
            out[-1]["north_arrow"] = {"position": list(na["position"]), "scale": na["scale"],
                                      "rotation_deg": turn}
            out[-1]["twist_deg"] = turn  # the type asks for the sheet: its viewport is turned
    return out


def layout_of(truth: GroundTruth) -> Tuple[Alignment, float, float, List[float], List[str]]:
    """What a truth's layout is made of: ``(the line, feet to the inch, the
    twist, the breaks as distances from BEGIN, the sheets' names)``."""
    align = Alignment.from_dict(truth.alignments[next(iter(truth.alignments))])
    first = truth.sheets[0]
    fpi = float(first["feet_per_inch"])
    turn = float(first["viewport"].get("rotation_deg") or 0.0)
    begin = float(align.begin_station)
    stations = sorted({float(m["station"]) for sh in truth.sheets for m in sh.get("matches") or []})
    return align, fpi, turn, [s - begin for s in stations], [sh["name"] for sh in truth.sheets]


def rebuilt(truth: GroundTruth, match_dists: Sequence[float], names: Sequence[str]) -> GroundTruth:
    """``truth`` for a layout that breaks at ``match_dists`` on sheets ``names``
    instead of the generator's: its sheets and their curve tables derived
    again, everything else as it was, and the scope without the mark that
    sends a truth here (so the D1 checks grade it like any other layout)."""
    name = next(iter(truth.alignments))
    align, fpi, turn, _own, _names = layout_of(truth)
    first = truth.sheets[0]
    S = DRAFTING_SPEC_V1
    columns = (list(truth.curve_tables[0]["columns"]) if truth.curve_tables
               else list(S["curve_table"]["columns"]))
    deliverable = {"sheets": sheets_for(align, fpi, turn, match_dists, names,
                                        first["title_block_fields"], first["size"]),
                   "feet_per_inch": fpi, "curve_table_columns": columns,
                   "text_heights": {"sheet_table_in": S["text"]["table_height_in"]}}
    curve_tables, sheets, stations = sheet_rows(align, deliverable, S, name)
    return dataclasses.replace(
        truth, sheets=sheets, curve_tables=curve_tables,
        scope=[g for g in truth.scope if g != OPEN_BREAKS],
        counts={**truth.counts, "sheets": len(sheets), "match_lines": len(stations)})


def with_breaks(task: Task, match_dists: Sequence[float],
                names: Optional[Sequence[str]] = None) -> Task:
    """``task`` with its deliverable laid out on other breaks, so that its
    reference solution (``tasks.reference``) drafts that layout: for showing
    that another sound set of breaks scores as the generator's does, and an
    unsound one does not.  The truth, and so what the layout is graded
    against, is the task's own."""
    names = list(names) if names else sheet_names(len(match_dists) + 1)
    align, fpi, turn, _own, _names = layout_of(task.truth)
    first = task.truth.sheets[0]
    brief = copy.deepcopy(task.brief)
    brief.deliverable["sheets"] = sheets_for(align, fpi, turn, match_dists, names,
                                             first["title_block_fields"], first["size"])
    return Task(brief=brief, truth=task.truth, baseline=task.baseline, files=task.files)


def opened(task: Task, seed: int) -> Task:
    """A generated plan sheet job as a ``plan-sheet-breaks`` task, or
    ``ValueError`` when it cannot be one: the generator laid the line on more
    sheets than carry it (its reference would then fail the count), or broke it
    where this module does not call a match line sound.  ``AssertionError``
    when ``sheets_for`` no longer derives the generator's sheets from the
    generator's breaks."""
    D = task.brief.deliverable
    align, fpi, turn, own, names = layout_of(task.truth)
    least = fewest(align, fpi, turn)
    if least != len(names):
        raise ValueError(f"seed {seed}: the generator lays the line on {len(names)} sheet(s) "
                         f"where {least} carry it at 1\" = {fpi:g}'; use another seed or sheet "
                         f"count for a {TYPE} task")
    for d in own:
        why = unsound(align, d)
        if why:
            raise ValueError(f"seed {seed}: the generator's break {d:g} ft along is not sound "
                             f"here ({why})")
    title = D["sheets"][0]["title_block_fields"]
    again = sheets_for(align, fpi, turn, own, names, title, D["sheets"][0]["size"])
    if again != D["sheets"]:
        raise AssertionError(f"generator bug: seed {seed}: tasks.breaks.sheets_for no longer "
                             f"derives the generator's sheets from its breaks")
    return task


__all__ = ["TYPE", "FIRST_SHEET", "STATION_FT", "CLEAR_FT", "MARGIN_IN", "sheet_names",
           "office_breaks", "lettered_points", "unsound", "stretch_fits", "fewest", "sheets_for",
           "layout_of", "rebuilt", "with_breaks", "opened"]
