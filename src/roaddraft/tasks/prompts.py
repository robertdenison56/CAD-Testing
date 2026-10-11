"""The natural-language prompts a D1 task is posed with (the prompt dial).

A task is handed to a model the way a PE hands work to a drafter, in words,
at one of the spec's ``prompt_levels``:

- ``explicit`` -- the request with the drafting standards it touches spelled
  out: scale, layers, text heights, tick length, label wording, table
  columns, title-block values.  Graded exactly.
- ``vague`` -- the request in a sentence.  What belongs on a layout sheet is
  the drafter's to know, and a convention the prompt did not state is graded
  by the spec's lenient rules.

Both levels share one truth, so the gap between them, paired by task, says
how much a model leans on being told.  Each task type (``tasks.types``) has
its own pair, and a two-sheet layout adds the sheets and the match line.
``RULES`` are the benchmark's own rules (anchor your labels, leave the design
alone) and go with every level: they are about the instrument, not about
drafting.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from roaddraft.design.labels import CURVE_COLUMNS
from roaddraft.tasks.brief import TaskBrief
from roaddraft.tasks.types import PHASE_ORDER, task_type

LEVELS = ("explicit", "vague")

RULES = """Do one drafting task on a RoadDraft document, using the tools you have been given. RoadDraft is a headless CAD engine.

Rules:
- Every change to the drawing goes through a tool call.
- The design (alignments and profiles) is already in the document. Draft it as given; do not create, edit or delete design data.
- Labels and the curve data table count only when the engine anchors them to the design: place_label, annotate_stationing with alignment=..., and place_curve_table. Text typed with place_text or a table built with place_table earns nothing, however right it reads.
- Keep what is already drawn, and keep new labels clear of it.
- Nobody can answer questions. Work until you judge the task done."""


# ----------------------------------------------------------------- pieces


class _Words:
    """The nouns and standards of one task, ready to be put in sentences."""

    def __init__(self, brief: TaskBrief):
        self.D, self.S, self.P = brief.deliverable, brief.drafting_spec, brief.project
        self.A = brief.alignment_name
        self.type = task_type(self.D.get("task_type", "plan-sheet"))
        self.sheets = self.D["sheets"]
        self.names = [sh["name"] for sh in self.sheets]
        self.many = len(self.sheets) > 1
        fpi = float(self.D["feet_per_inch"])
        self.scale = self.S["sheet"]["scale_text_format"].format(fpi=fpi)
        self.size = self.sheets[0]["size"].replace("_", " ")
        self.layers, self.props = self.S["layers"], self.S["layer_props"]
        self.st, self.labels, self.text = (self.S["stationing"], self.S["labels"],
                                           self.S["text"])
        self.has_eq = "equation" in self.D["required_label_kinds"]
        self.matches = [m for sh in self.sheets for m in sh.get("matches", [])]
        self.match = self.matches[0] if self.matches else None
        self.section = self.P.get("typical_section") or {}
        self.pave = self.D.get("pavement") or {}
        self.width_dims = self.D.get("width_dimensions") or []
        self.basefile = self.D.get("basefile")

    # -- nouns
    @property
    def sheet_list(self) -> str:
        names = self.names
        if len(names) == 1:
            return f"sheet {names[0]}"
        return "sheets " + ", ".join(names[:-1]) + f" and {names[-1]}"

    @property
    def Sheet_list(self) -> str:
        return self.sheet_list[0].upper() + self.sheet_list[1:]

    def each_sheet(self) -> str:
        return f"each of {self.sheet_list}" if self.many else self.sheet_list

    def layer(self, role: str) -> str:
        name = self.layers[role]
        p = self.props[name]
        bits = [p["color"]]
        if "linetype" in p:
            bits.append(f"{p['linetype']} linetype")
        bits.append(f"{p['lineweight_mm']:g} mm")
        return f"layer {name} ({', '.join(bits)})"

    @property
    def label_h(self) -> str:
        return f"{self.text['label_height_in']:.2f} in high on paper"

    # -- standards, each a clause
    def linework(self) -> str:
        return (f"the centerline of {self.A}: one line per tangent and one arc per curve, on "
                f"the design geometry exactly, on {self.layer('alignment')}")

    def ticks(self) -> str:
        return (f"a station tick every {self.st['interval_ft']:g} ft, "
                f"{2 * float(self.st['tick_half_len_in']):.2f} in long on paper and centered on "
                f"the line, on {self.layer('ticks')}")

    def station_labels(self) -> str:
        return (f"its station in {self.st['format']} form at each tick, {self.label_h}, on the "
                f"{self.st['label_side']} of the line, on {self.layer('labels')}")

    def curve_points(self) -> str:
        fmt = self.labels["pc_pt"]["format"]
        return (f"the beginning and end of every curve lettered {fmt.split()[0]} and EC with "
                f"their stations ({fmt} form), {self.label_h}, on the "
                f"{self.labels['pc_pt']['side']} of the line")

    def equation(self) -> str:
        return (f"the station equation, lettered in {self.labels['equation']['format']} form")

    def callouts(self) -> str:
        return (f"a callout at the middle of every curve naming it "
                f"({self.labels['mc']['format']}, C-2, ...), {self.label_h}, on the right of "
                f"the line, on {self.layer('labels')}")

    def bearings(self) -> str:
        return (f"a quadrant bearing at the middle of every tangent, to the second "
                f"(N 45°30'15\" E form), {self.label_h}, on the {self.labels['bearing']['side']} "
                f"of the line, on {self.layer('labels')}")

    def table(self) -> str:
        headers = ", ".join(CURVE_COLUMNS[c][0] for c in self.D["curve_table_columns"])
        with_curves = [sh["name"] for sh in self.sheets if sh["curves"]]
        if len(with_curves) == 1:
            where = f"a {self.S['curve_table']['title']} table on sheet {with_curves[0]}"
            rows = "one row per curve"
        else:
            where = (f"a {self.S['curve_table']['title']} table on each of sheets "
                     + ", ".join(with_curves[:-1]) + f" and {with_curves[-1]}")
            rows = "one row per curve that sheet shows"
        return (f"{where}: {rows}, columns {headers}, lengths to 0.01 ft and angles in "
                f"degrees-minutes-seconds, text {self.text['table_height_in']:.2f} in high, on "
                f"{self.layer('tables')}, inside the border and clear of the plan and the title "
                f"block")

    def north(self) -> str:
        block = self.S["sheet"]["north_arrow"]["block"]
        return (f"a north arrow (the {block} block) in the upper right of "
                f"{self.each_sheet()}, inside the border")

    def title(self) -> str:
        parts = []
        for sh in self.sheets:
            tb = sh["title_block_fields"]
            parts.append(
                f"the title block of {sh['name']}: project {tb['project']}, agency {tb['agency']}, "
                f"sheet title {tb['sheet_title']}, sheet {tb['sheet_number']} of "
                f"{tb['total_sheets']}, designed by {tb['designed_by']}, drawn by "
                f"{tb['drawn_by']}, checked by {tb['checked_by']}, date {tb['date']}, scale "
                f"{tb['scale']}")
        return "; ".join(parts)

    def viewports(self) -> str:
        if not self.many:
            return (f"one viewport at {self.scale} showing all of {self.A}, inside the border "
                    f"and clear of the title block")
        return (f"a viewport at {self.scale} on each sheet showing its part of {self.A}, inside "
                f"the border and clear of the title block")

    def match_line(self) -> str:
        m = self.match
        return (f"a match line across the centerline at station {m['station_text']}, "
                f"{m['half_width_ft']:g} ft each side, on {self.layer('ticks')}, and on each "
                f"sheet a label reading MATCH LINE STA {m['station_text']} SEE SHEET <the other "
                f"sheet>, {self.label_h}, at the end of the match line, on {self.layer('labels')}")

    def breaking(self) -> str:
        return f", breaking at station {self.match['station_text']}" if self.match else ""

    # -- plan prep
    def section_words(self) -> str:
        lanes, lw = self.section.get("lanes", 2), self.section.get("lane_width_ft", 12)
        words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
        return f"{self.A} is {words.get(lanes, lanes)} {lw:g}-ft lanes"

    def edges(self) -> str:
        half = self.pave.get("half_width_ft", 12)
        return (f"its edges of pavement: a constant offset of the centerline {half:g} ft each "
                f"side, following it through the curves, on {self.layer('edges')}")

    def widths(self) -> str:
        width = self.section.get("pavement_width_ft", 24)
        where = ", ".join(f"{wd['station_text']} on {wd['ref']}" for wd in self.width_dims)
        return (f"the pavement width across each tangent: an aligned dimension between the two "
                f"edges of pavement at station {where}, text {self.label_h}, reading "
                f"{width:.2f}', on {self.layer('dims')}")

    def layer_list(self, with_props: bool) -> str:
        if with_props:
            return ", ".join(self.layer(role) for role in self.layers).replace("layer ", "")
        return ", ".join(self.layers.values())

    # -- what is already there
    def done(self) -> str:
        given = [p for p in PHASE_ORDER if p in self.type.given and p != "layers"]
        if not given:
            return ""
        words = {"linework": "the centerline linework", "edges": "the pavement edges",
                 "stationing": "the stationing", "bearings": "the bearings",
                 "callouts": "the curve callouts", "widths": "the width dimensions",
                 "sheet": f"{self.sheet_list} with {'their viewports' if self.many else 'its viewport'}"
                          + (" and the match line" if self.match else ""),
                 "reference": "the base drawing reference",
                 "table": "the curve data table" + ("s" if self.many else ""),
                 "north": "the north arrow" + ("s" if self.many else ""),
                 "title": "the title block" + ("s" if self.many else "")}
        items = [words[p] for p in given]
        text = items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"
        return f" {text[0].upper()}{text[1:]} {'are' if len(items) > 1 else 'is'} already done."


def _bullets(items: List[str]) -> str:
    return "\n".join(f"- {s[0].upper()}{s[1:]}." for s in items)


# ----------------------------------------------------------------- prompts


def _draw_alignment(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Draw alignment {w.A} in model space: one line per tangent and one arc per "
                f"curve, on the design geometry exactly, on {w.layer('alignment')}. The layers "
                f"exist; draw nothing else.")
    return f"Draw {w.A}."


def _stationing(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Station {w.A}."
    items = [w.ticks(), w.station_labels(), w.curve_points()] + ([w.equation()] if w.has_eq else [])
    return (f"Station alignment {w.A} in model space, where {w.sheet_list} shows it:\n"
            f"{_bullets(items)}\n{w.done().strip()}")


def _callouts(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"Add {w.callouts()}.{w.done()}"
    return f"Number the curves on {w.A}."


def _bearings(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"Label {w.A}'s tangents: {w.bearings()}.{w.done()}"
    return f"Add bearings to {w.A}."


def _curve_table(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"Add {w.table()}.{w.done()}"
    return f"Put the curve data on {w.sheet_list}."


def _title_block(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"Fill in {w.title()}. Insert {w.north()}.{w.done()}"
    arrows = "north arrows" if w.many else "a north arrow"
    blocks = "title blocks" if w.many else "title block"
    return f"Finish the {blocks} on {w.sheet_list} and add {arrows}."


def _sheet_setup(w: _Words, explicit: bool) -> str:
    if not explicit:
        verb = "Set up plan " + w.sheet_list
        return f"{verb} for {w.A}{w.breaking()}."
    if not w.many:
        return (f"Create plan {w.sheet_list}, {w.size}, with {w.viewports()}.{w.done()}")
    return (f"Lay out {w.A} on {len(w.sheets)} {w.size} plan sheets, {w.sheet_list[7:]}, at "
            f"{w.scale}{w.breaking()}:\n{_bullets([w.viewports(), w.match_line()])}\n"
            f"{w.done().strip()}")


def _annotation_items(w: _Words) -> List[str]:
    items = [w.ticks(), w.station_labels(), w.curve_points()]
    if w.has_eq:
        items.append(w.equation())
    items += [w.callouts(), w.bearings(), w.table(), w.north(), w.title()]
    return items


def _annotate_sheet(w: _Words, explicit: bool) -> str:
    is_are = "are" if w.many else "is"
    if not explicit:
        return f"{w.Sheet_list} {is_are} blank. Annotate {'them' if w.many else 'it'}."
    match = f" and a match line at station {w.match['station_text']}" if w.match else ""
    return (f"{w.Sheet_list} {is_are} set up with a viewport on {w.A} at {w.scale}{match}, and "
            f"the centerline is drawn, but there is no annotation. Annotate "
            f"{'them' if w.many else 'it'} completely:\n{_bullets(_annotation_items(w))}")


def _plan_sheet(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Draft plan {w.sheet_list} for {w.A}{w.breaking()}."
    items = [w.linework()] + _annotation_items(w)
    layout = w.viewports() + (f"; {w.match_line()}" if w.match else "")
    return (f"Draft plan {w.sheet_list} for the {w.P['name']} project ({w.P['agency']}, "
            f"{w.P['county']}): {w.size}, {w.scale}, showing alignment {w.A}, which is already "
            f"in the design{w.breaking()}. Set up {layout}. Show:\n{_bullets(items)}")


# -- plan prep


def _layer_setup(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Create the office's standard layers in this drawing: "
                f"{w.layer_list(with_props=True)}. Nothing is drawn yet; draw nothing.")
    return f"Set up the standard layers: {w.layer_list(with_props=False)}."


def _pavement_edges(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"{w.section_words()}. Draw {w.edges()}.{w.done()}"
    return f"{w.section_words()}. Draw the pavement edges."


def _pavement_widths(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"{w.section_words()}. Dimension {w.widths()}.{w.done()}"
    return f"Dimension the pavement width on each tangent of {w.A}."


def _pavement(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"{w.section_words()}. Draw {w.edges()}, then dimension {w.widths()}."
                f"{w.done()}")
    return f"{w.section_words()}. Draw the pavement edges and dimension the width on each tangent."


def _attach_reference(w: _Words, explicit: bool) -> str:
    ref = w.S.get("reference", {})
    if explicit:
        return (f"This is the sheet file for {w.sheet_list}: the sheet{'s' if w.many else ''} and "
                f"{'their viewports' if w.many else 'its viewport'} on {w.A} are set up, but the "
                f"drawing itself lives in the base file {w.basefile} beside it. Attach that file "
                f"as a reference named {ref.get('name', 'BASE')} into {ref.get('space', 'model')} "
                f"space at its own coordinates (no offset, rotation or scale), visible and "
                f"unclipped, so it shows through the viewport{'s' if w.many else ''}.")
    return f"Attach the base drawing {w.basefile} to this sheet file."


PROMPTS: Dict[str, Callable[[_Words, bool], str]] = {
    "draw-alignment": _draw_alignment,
    "stationing": _stationing,
    "curve-callouts": _callouts,
    "bearings": _bearings,
    "curve-table": _curve_table,
    "title-block": _title_block,
    "sheet-setup": _sheet_setup,
    "annotate-sheet": _annotate_sheet,
    "plan-sheet": _plan_sheet,
    "layer-setup": _layer_setup,
    "pavement-edges": _pavement_edges,
    "pavement-widths": _pavement_widths,
    "pavement": _pavement,
    "attach-reference": _attach_reference,
}


def prompt(brief: TaskBrief, level: str) -> str:
    """The prompt for ``brief`` at ``level`` (``explicit`` or ``vague``)."""
    if level not in LEVELS:
        raise ValueError(f"unknown prompt level {level!r}; levels: {', '.join(LEVELS)}")
    w = _Words(brief)
    return PROMPTS[w.type.name](w, level == "explicit")


def render_prompts(brief: TaskBrief) -> Dict[str, str]:
    """``{level: prompt}`` for every prompt level."""
    return {level: prompt(brief, level) for level in LEVELS}


def task_text(brief: TaskBrief, level: str = "explicit") -> str:
    """The user message of a D1 episode: the rules, then the prompt at ``level``."""
    if level not in LEVELS:
        raise ValueError(f"unknown prompt level {level!r}; levels: {', '.join(LEVELS)}")
    text = brief.prompts.get(level) if brief.prompts else None
    return f"{RULES}\n\nTHE TASK:\n{text or prompt(brief, level)}"


__all__ = ["LEVELS", "RULES", "PROMPTS", "prompt", "render_prompts", "task_text"]
