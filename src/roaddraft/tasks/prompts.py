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

from roaddraft.core.units import format_station
from roaddraft.design.labels import CURVE_COLUMNS
from roaddraft.tasks.brief import TaskBrief
from roaddraft.tasks.types import PHASE_ORDER, task_type

LEVELS = ("explicit", "vague")

_DESIGN_GIVEN = ("The design (alignments and profiles) is already in the document. Draft it as "
                 "given; do not create, edit or delete design data.")
_DESIGN_ASKED = ("The design is empty. Create the alignment exactly as the task gives it (it is "
                 "design data, not linework), then draft it; create nothing else in the design.")

RULES_TEMPLATE = """Do one drafting task on a RoadDraft document, using the tools you have been given. RoadDraft is a headless CAD engine.

Rules:
- Every change to the drawing goes through a tool call.
- {design}
- Labels and the curve data table count only when the engine anchors them to the design: place_label, annotate_stationing with alignment=..., and place_curve_table (on a sheet file whose design is in an attached base drawing, name its alignment through the reference, BASE:ALIGN-1). Text typed with place_text or a table built with place_table earns nothing, however right it reads.
- Keep what is already drawn, and keep new labels clear of it.
- Nobody can answer questions. Work until you judge the task done."""

#: the rules of every task that is handed its design
RULES = RULES_TEMPLATE.format(design=_DESIGN_GIVEN)


def rules(brief: TaskBrief) -> str:
    """The benchmark's rules for this task: the design is given, or is the task."""
    ttype = task_type(brief.deliverable.get("task_type", "plan-sheet"))
    return RULES_TEMPLATE.format(design=_DESIGN_ASKED if "design" in ttype.asks
                                 else _DESIGN_GIVEN)


# ----------------------------------------------------------------- pieces


class _Words:
    """The nouns and standards of one task, ready to be put in sentences."""

    def __init__(self, brief: TaskBrief):
        self.brief = brief
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
        self.source = self.D.get("source") or {}  # a real plan sheet's provenance
        self.ref_name = self.D.get("design_reference") or self.S.get("reference", {}).get(
            "name", "BASE")

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
        return f"layer {self.layer_name(self.layers[role])}"

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
        every = int(self.st.get("full_station_every_ft", 500))
        return (f"its station number under each tick, {self.st['label_side']} the line and "
                f"reading along it, lettered the Caltrans way: the whole station number at every "
                f"{every} ft station (30, 35) and only the ones digit at the others (1, 2, 3, 4), "
                f"{self.label_h}, on {self.layer('labels')}")

    def curve_points(self) -> str:
        pp = self.labels["pc_pt"]
        return (f"the beginning and end of every curve lettered with its station to the "
                f"hundredth followed by BC or EC ({pp['format']} form), square to the line on its "
                f"{pp['side']} and reading {pp.get('reads', 'bottom to top')}, {self.label_h}")

    def equation(self) -> str:
        eq = self.labels["equation"]
        return (f"the station equation, lettered in {eq['format']} form square to the line on "
                f"its {eq.get('side', 'left')}, reading bottom to top")

    def callouts(self) -> str:
        mc = self.labels["mc"]
        return (f"the number of every curve (1, 2, ... along the line) in a bubble off the middle "
                f"of the curve on its {mc.get('side', 'right')}, with a leader from the bubble to "
                f"the curve, {self.label_h}, on {self.layer('labels')}")

    def bearings(self) -> str:
        b = self.labels["bearing"]
        example = b.get("example", "N 45°30'15\" E 1234.56'")
        return (f"the bearing and length of every tangent as one line of text at its middle, "
                f"{b['side']} the line and parallel to it (quadrant bearing to the second and "
                f"length to 0.01 ft: {example} form), {self.label_h}, on {self.layer('labels')}")

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
        on = f", on {self.layer('symbols')}" if "symbols" in self.layers else ""
        return (f"a north arrow (the {block} block) in the upper right of "
                f"{self.each_sheet()}, inside the border{on}")

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
        on = self.layer("match") if "match" in self.layers else self.layer("ticks")
        return (f"a match line across the centerline at station {m['station_text']}, "
                f"{m['half_width_ft']:g} ft each side, and on each sheet a label reading MATCH "
                f"LINE STA {m['station_text']} SEE SHEET <the other sheet>, {self.label_h}, at the "
                f"end of the match line, both on {on}")

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

    @property
    def layer_set(self) -> List[str]:
        return list(self.S.get("layer_set") or dict.fromkeys(self.layers.values()))

    # -- the design itself, for the task that creates it
    def geometry(self) -> str:
        """The alignment as a PE would dictate it: N/E of BEGIN, each PI with
        its radius, END; the begin station; any station equation."""
        al = self.brief.design["alignments"][self.A]
        pis = al["pis"]
        begin = format_station(float(al["begin_station"]))

        def ne(pt) -> str:
            return f"N {pt[1]:.2f}, E {pt[0]:.2f}"

        parts = [f"begins at {ne(pis[0]['point'])}, station {begin}"]
        for k, pi in enumerate(pis[1:-1], start=1):
            parts.append(f"PI-{k} at {ne(pi['point'])}, R = {pi['radius']:.2f}'")
        parts.append(f"ends at {ne(pis[-1]['point'])}")
        for q in al.get("equations", []):
            parts.append(f"station equation {format_station(float(q['back']))} BK = "
                         f"{format_station(float(q['ahead']))} AH")
        return "; ".join(parts)

    def layer_list(self, with_props: bool) -> str:
        if with_props:
            return "; ".join(self.layer_name(name) for name in self.layer_set)
        return ", ".join(self.layer_set)

    def layer_name(self, name: str) -> str:
        p = self.props[name]
        bits = [p["color"]]
        if "linetype" in p:
            bits.append(f"{p['linetype']} linetype")
        bits.append(f"{p['lineweight_mm']:g} mm")
        return f"{name} ({', '.join(bits)})"

    # -- what is already there
    def done(self) -> str:
        given = [p for p in PHASE_ORDER if p in self.type.given and p not in ("layers", "design")]
        if not given:
            return ""
        words = {"design": "", "linework": "the centerline linework", "edges": "the pavement edges",
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
        return (f"Create the Caltrans named levels a layout sheet file carries, as layers of this "
                f"drawing: {w.layer_list(with_props=True)}. Nothing is drawn yet; draw nothing.")
    return f"Set up the standard Caltrans levels: {w.layer_list(with_props=False)}."


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


def _annotate_base(w: _Words, explicit: bool) -> str:
    ref = w.S.get("reference", {}).get("name", "BASE")
    items = [w.ticks(), w.station_labels(), w.curve_points()]
    if w.has_eq:
        items.append(w.equation())
    items += [w.callouts(), w.bearings(), w.table()]
    if not explicit:
        return (f"The base drawing is attached as {ref}. Add the alignment data of {w.A} to "
                f"{w.sheet_list}.")
    return (f"This is the sheet file for {w.sheet_list}: the sheet{'s' if w.many else ''} and "
            f"{'their viewports' if w.many else 'its viewport'} on {w.A} are set up, and the "
            f"base drawing {w.basefile} is attached as reference {ref} at its own coordinates. "
            f"The design, alignment {w.A}, lives in the base: this file does not own it, and "
            f"the labelers reach it through the reference as {ref}:{w.A}. Letter its alignment "
            f"data in this file, anchored through the reference:\n{_bullets(items)}")


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


# -- design input


def _create_alignment(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Create alignment {w.A} and draw it. {w.A} {w.geometry()}. Coordinates are "
                f"northing and easting in US survey feet. Create it in the design from its PIs "
                f"(create_alignment: the PI points with the radius of the curve at each), then "
                f"draw it in model space: one line per tangent and one arc per curve, on "
                f"{w.layer('alignment')}. The layers exist; draw nothing else.")
    return f"{w.A} {w.geometry()}. Create it and draw it."


# -- real plan sheets (tasks.real): one alignment of a redrafted sample sheet


def _real_context(w: _Words) -> str:
    """Where the drafter is: the real sheet, its base drawing, what else it shows."""
    src = w.source
    others = src.get("other_alignments") or []
    also = (f", which also holds alignment{'s' if len(others) > 1 else ''} "
            + ", ".join(others) if others else "")
    return (f"This is the sheet file for sheet {w.names[0]} of a {src.get('agency_name', '')} "
            f"plan set ({w.P['name']}): a {w.size} {src.get('family', 'plan')} sheet at "
            f"{w.scale}. Its viewport shows the base drawing {w.D.get('design_file')}, attached "
            f"as reference {w.ref_name}{also}, over the corridor and survey. Alignment {w.A} "
            f"lives in that base: this file does not own it, and the labelers reach it through "
            f"the reference as {w.ref_name}:{w.A}. Keep everything already on the sheet."
            + _real_reading(w))


def _real_reading(w: _Words) -> str:
    twist = float(w.D.get("view_rotation") or 0.0)
    turned = (f" The viewport is turned {twist:.2f}°: letter model-space labels to read upright "
              f"on the sheet as plotted (the labelers' view_rotation)." if abs(twist) > 1e-6
              else "")
    return (f"{turned} Where a label would land on something already on the sheet, put it on "
            f"the other side of the line or further off it.")


def _real_given(w: _Words) -> str:
    words = {"stationing": "its stationing", "bearings": "its bearings",
             "callouts": "its curve callouts", "table": "its curve data table"}
    al = w.brief.design["alignments"][w.A]
    has = {"stationing": True,
           "bearings": any(el["kind"] == "tangent" for el in al["elements"]),
           "callouts": bool(w.sheets[0]["curves"]),
           "table": bool(w.sheets[0]["curves"]) and bool(w.D.get("table_given"))}
    given = [words[p] for p in ("stationing", "bearings", "callouts", "table")
             if p in w.type.given and has[p]]
    if not given:
        return ""
    text = given[0] if len(given) == 1 else ", ".join(given[:-1]) + f" and {given[-1]}"
    return f" {text[0].upper()}{text[1:]} {'are' if len(given) > 1 else 'is'} already done."


def _real_stationing(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Station the {w.A} line on sheet {w.names[0]}."
    items = [w.ticks(), w.station_labels(), w.curve_points()]
    return (f"{_real_context(w)}\nStation {w.A} in model space, anchored through the "
            f"reference:\n{_bullets(items)}\n{_real_given(w).strip()}")


def _real_bearings(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Add the bearings of the {w.A} line to sheet {w.names[0]}."
    return (f"{_real_context(w)}\nLabel {w.A}'s tangents, anchored through the reference: "
            f"{w.bearings()}.{_real_given(w)}")


def _real_callouts(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Number the curves of the {w.A} line on sheet {w.names[0]}."
    return (f"{_real_context(w)}\nAdd, anchored through the reference, {w.callouts()}."
            f"{_real_given(w)}")


def _real_curve_table(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Put the curve data of the {w.A} line on sheet {w.names[0]}."
    return (f"{_real_context(w)}\nAdd, anchored through the reference, {w.table()}, listing "
            f"the curves of {w.A}.{_real_given(w)}")


def _real_alignment_data(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Letter the alignment data of the {w.A} line on sheet {w.names[0]}."
    items = [w.ticks(), w.station_labels(), w.curve_points(), w.callouts(), w.bearings(),
             w.table()]
    return (f"{_real_context(w)}\n{w.A} has no annotation on this sheet. Letter its alignment "
            f"data in this file, anchored through the reference:\n{_bullets(items)}")


# -- real plan sheets: the sheet's own jobs and the sheet from scratch


def _real_set(w: _Words) -> str:
    src = w.source
    return f"a {src.get('agency_name', '')} plan set ({w.P['name']})"


def _real_twist(w: _Words) -> float:
    return float(w.D.get("view_rotation") or 0.0)


def _real_border(w: _Words) -> str:
    tpl = w.sheets[0].get("template") or "standard"
    return f"the {tpl} border (create_sheet title_block_template '{tpl}')"


def _real_files(w: _Words) -> str:
    files = [r["file"] for r in w.D.get("references") or []] or w.D.get("base_files") or []
    return ", ".join(files) or w.D.get("design_file", "")


_LINE_COUNTS = {2: "two", 3: "three", 4: "four", 5: "five"}


def _field_value(v: str) -> str:
    """A title block value as a prompt states it: a value lettered on several lines
    reads as its lines in quotes (graded with the line breaks as spaces)."""
    lines = [ln.strip() for ln in str(v).split("\n") if ln.strip()]
    if len(lines) < 2:
        return str(v).strip()
    quoted = [f'"{ln}"' for ln in lines]
    return (", ".join(quoted[:-1]) + f" and {quoted[-1]} on "
            f"{_LINE_COUNTS.get(len(lines), len(lines))} lines")


def _real_title(w: _Words, keys: bool) -> str:
    sh = w.sheets[0]
    labels = sh.get("title_labels") or {}
    return "; ".join(f"{labels.get(k, k)}{f' [{k}]' if keys else ''}: {_field_value(v)}"
                     for k, v in sh["title_block_fields"].items())


def _real_title_vague(w: _Words) -> str:
    sh = w.sheets[0]
    labels = sh.get("title_labels") or {}
    keys = (sh.get("title_stated") or {}).get("vague") or []
    return ", ".join(f"{labels.get(k, k).lower()} {_field_value(sh['title_block_fields'][k])}"
                     for k in keys)


def _real_north(w: _Words) -> str:
    na = w.sheets[0].get("north_arrow") or {}
    block = w.S["sheet"]["north_arrow"]["block"]
    turn = float(na.get("rotation_deg", 0.0))
    return (f"a north arrow (the {block} block) pointing to true north, which is turned "
            f"{turn:.2f}° on this sheet, inside the border and clear of the title block and "
            f"the plan, on {w.layer('symbols')}")


def _real_lettering(w: _Words) -> str:
    twist = _real_twist(w)
    turned = (f", model labels lettered to read upright on the sheet as plotted "
              f"(view_rotation {twist:.2f})" if abs(twist) > 1e-6 else "")
    return f"anchored through the reference as {w.ref_name}:{w.A}{turned}"


def _real_draw_alignment(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Draw the {w.A} line in this alignment file."
    return (f"This is {w.D.get('design_file')}, the alignment base file of {_real_set(w)}; "
            f"sheet {w.names[0]} shows it at {w.scale}. Alignment {w.A} is in its design but "
            f"is not drawn. Draw {w.linework()}. The layers exist; keep everything already in "
            f"the file and draw nothing else.")


def _real_attach_reference(w: _Words, explicit: bool) -> str:
    refs = w.D.get("references") or []
    if not explicit:
        return f"Attach the base files {_real_files(w)} to sheet {w.names[0]}."
    each = "; ".join(f"{r['file']} as {r['name']}" for r in refs)
    return (f"This is the sheet file for sheet {w.names[0]} of {_real_set(w)}: its border, "
            f"title block, notes and callouts are drawn, but its viewport shows nothing because "
            f"the base files beside it are not attached. Attach each into {refs[0]['space']} "
            f"space at its own coordinates (no offset, rotation or scale), visible and "
            f"unclipped, under the name given: {each}.")


def _real_title_block(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Fill in the title block of sheet {w.names[0]}: {_real_title_vague(w)}."
    tpl = w.sheets[0].get("template") or "standard"
    return (f"Fill in the title block of sheet {w.names[0]} of {_real_set(w)}, on its {tpl} "
            f"border (the fill_title_block key in brackets): {_real_title(w, True)}.")


def _real_sheet_setup(w: _Words, explicit: bool) -> str:
    twist = _real_twist(w)
    if not explicit:
        return (f"Set up plan sheet {w.names[0]} for the {w.A} line: {w.size}, on "
                f"{_real_border(w)}, the viewport turned {twist:.2f}° as published.")
    return (f"This is the sheet file of {_real_set(w)}: the base files {_real_files(w)} are "
            f"attached, and alignment {w.A} is drawn and annotated in model space, its labels "
            f"lettered to read on a sheet turned {twist:.2f}°, but there is no sheet. Create plan "
            f"sheet {w.names[0]}: {w.size}, on {_real_border(w)}, with one viewport at {w.scale}, "
            f"turned {twist:.2f}°, showing all of {w.A} inside the border and clear of the title "
            f"block.")


def _real_sheet_items(w: _Words) -> List[str]:
    return [w.ticks(), w.station_labels(), w.curve_points(), w.callouts(), w.bearings(),
            w.table(), _real_north(w), f"the title block: {_real_title(w, True)}"]


def _real_annotate_sheet(w: _Words, explicit: bool) -> str:
    twist = _real_twist(w)
    if not explicit:
        return (f"Sheet {w.names[0]} is blank. Annotate the {w.A} line and finish the sheet; "
                f"title block: {_real_title_vague(w)}.")
    return (f"Sheet {w.names[0]} of {_real_set(w)} is set up on {_real_border(w)} with a "
            f"viewport at {w.scale}, turned {twist:.2f}°, on the attached base files; alignment "
            f"{w.A} is drawn, but nothing on the sheet is lettered and the sheet itself is "
            f"blank. Annotate it completely, {_real_lettering(w)}:\n"
            f"{_bullets(_real_sheet_items(w))}")


def _real_plan_sheet(w: _Words, explicit: bool) -> str:
    twist = _real_twist(w)
    if not explicit:
        return (f"Draft plan sheet {w.names[0]} for the {w.A} line from the base files, on "
                f"{_real_border(w)}, turned {twist:.2f}° as published; title block: "
                f"{_real_title_vague(w)}.")
    return (f"Draft plan sheet {w.names[0]} of {_real_set(w)} from the attached base files "
            f"{_real_files(w)}: {w.size}, on {_real_border(w)}, with one viewport at {w.scale}, "
            f"turned {twist:.2f}°, showing all of {w.A} inside the border and clear of the title "
            f"block. Show, {_real_lettering(w)}:\n{_bullets(_real_sheet_items(w))}")


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
    "create-alignment": _create_alignment,
    "annotate-base": _annotate_base,
    "real-stationing": _real_stationing,
    "real-bearings": _real_bearings,
    "real-callouts": _real_callouts,
    "real-curve-table": _real_curve_table,
    "real-alignment-data": _real_alignment_data,
    "real-draw-alignment": _real_draw_alignment,
    "real-attach-reference": _real_attach_reference,
    "real-title-block": _real_title_block,
    "real-sheet-setup": _real_sheet_setup,
    "real-annotate-sheet": _real_annotate_sheet,
    "real-plan-sheet": _real_plan_sheet,
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
    return f"{rules(brief)}\n\nTHE TASK:\n{text or prompt(brief, level)}"


__all__ = ["LEVELS", "RULES", "RULES_TEMPLATE", "rules", "PROMPTS", "prompt", "render_prompts",
           "task_text"]
