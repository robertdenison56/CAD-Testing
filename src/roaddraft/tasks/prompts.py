"""The natural-language prompts a D1 task is posed with (the prompt dial).

A task is handed to a model the way a PE hands work to a drafter, in words,
at one of the spec's ``prompt_levels``:

- ``explicit`` -- the request as a PE would brief a drafter, in a few plain
  sentences that guide the work and name the standards it is graded on:
  scale, layers, text heights, tick length, label forms (by example), table
  columns, title-block values.  It leaves out what a drafter knows or the
  engine does (layer colours and weights, one arc per curve, keeping clear of
  the border) and names no tool or parameter the vague prompt does not.
  Graded exactly.
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
        # every break of the layout, once, in station order (three sheets have two)
        self.match_texts = [m["station_text"] for m in sorted(
            {m["station"]: m for m in self.matches}.values(), key=lambda m: m["station"])]
        self.section = self.P.get("typical_section") or {}
        self.pave = self.D.get("pavement") or {}
        self.width_dims = self.D.get("width_dimensions") or []
        self.basefile = self.D.get("basefile")
        self.source = self.D.get("source") or {}  # a real plan sheet's provenance
        self.ref_name = self.D.get("design_reference") or self.S.get("reference", {}).get(
            "name", "BASE")
        # a twisted layout (the seeded generator's twist dial, 2026-11-11): the turn of its
        # viewports.  A real sheet's twist has its own words (``_real_reading``)
        self.twist = float(self.D.get("view_rotation") or 0.0)
        self.twisted = abs(self.twist) > 1e-6 and not self.source

    # -- a twisted layout: nothing at all on an untwisted one
    def turned(self) -> str:
        """The viewports' turn, said where a viewport is named."""
        return f" turned {self.twist:.2f}°" if self.twisted else ""

    def turned_views(self) -> str:
        """The turn a vague layout prompt still gives: it is part of the layout asked for,
        as the published twist is on a real sheet."""
        if not self.twisted:
            return ""
        return f", the viewport{'s' if self.many else ''} turned {self.twist:.2f}°"

    def reading(self, stated: bool = False) -> str:
        """What the twist asks of the model lettering; ``stated`` when the prompt has
        already given the viewports' turn."""
        if not self.twisted:
            return ""
        sheets = "sheets" if self.many else "sheet"
        if stated:
            return f" Letter model-space labels to read upright on the plotted {sheets}."
        views = "viewports are" if self.many else "viewport is"
        return (f" The {views} turned {self.twist:.2f}°, so letter model-space labels to read "
                f"upright on the plotted {sheets}.")

    def dims_reading(self, stated: bool = False) -> str:
        """What the twist asks of a width dimension's text; ``stated`` when the
        prompt has already given the viewports' turn."""
        if not self.twisted:
            return ""
        sheets = "sheets" if self.many else "sheet"
        if stated:
            return f" Set the dimension text to read upright on the plotted {sheets} too."
        views = "viewports are" if self.many else "viewport is"
        return (f" The {views} turned {self.twist:.2f}°, so set the dimension text to read "
                f"upright on the plotted {sheets}.")

    def lettered(self) -> str:
        """The lettering a sheet-setup task is handed, already made for the twist."""
        if not self.twisted:
            return ""
        return f" The model is lettered to read upright through a view turned {self.twist:.2f}°."

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
        """The layer a role's work goes on, by name (its colour and weight are the
        layer's own, so only the layer-setup prompt states them)."""
        return self.layers[role]

    @property
    def label_h(self) -> str:
        return f"{self.text['label_height_in']:.2f} in"

    # -- the standards, each a sentence a PE would say (no closing period)
    def linework(self) -> str:
        return f"Draw the centerline of {self.A} on {self.layer('alignment')}"

    def stationing(self, it: str, verb: str = "Station") -> str:
        every = int(self.st.get("full_station_every_ft", 500))
        ticks = (f" on {self.layer('ticks')}" if self.layer("ticks") != self.layer("labels")
                 else "")
        return (f"{verb} {it} every {self.st['interval_ft']:g} ft with "
                f"{2 * float(self.st['tick_half_len_in']):.2f} in ticks{ticks}, numbered "
                f"{self.st['label_side']} the line the Caltrans way: the full station every "
                f"{every} ft and just the ones digit in between")

    def curve_points(self) -> str:
        pp = self.labels["pc_pt"]
        text = (f"Letter each curve's BC and EC with its station, square to the line on its "
                f"{pp['side']} and reading {pp.get('reads', 'bottom to top')} "
                f"({pp['format']})")
        if self.has_eq:
            text += f", and the station equation the same way ({self.labels['equation']['format']})"
        return text

    def callouts(self, of: str = "") -> str:
        mc = self.labels["mc"]
        return (f"Number the curves{of} in order along the line (1, 2, ...), each in a bubble "
                f"off the {mc.get('side', 'right')} of the curve with a leader to it")

    def bearings(self, of: str = "") -> str:
        b = self.labels["bearing"]
        example = b.get("example", "N 45°30'15\" E 1234.56'")
        return (f"Letter the bearing and length of each tangent{of} {b['side']} the line at its "
                f"middle, like {example}")

    def lettering(self) -> str:
        """Where the alignment's lettering goes: one height and layer for all of it."""
        what = "The ticks and all of that lettering go" if (
            self.layer("ticks") == self.layer("labels")) else "All of that lettering goes"
        return f"{what} on {self.layer('labels')}, in {self.label_h} text"

    def table(self) -> str:
        headers = [CURVE_COLUMNS[c][0] for c in self.D["curve_table_columns"]]
        with_curves = [sh["name"] for sh in self.sheets if sh["curves"]]
        title = self.S["curve_table"]["title"]
        where = (f"on {with_curves[0]}" if len(with_curves) == 1 else
                 "on each of " + ", ".join(with_curves[:-1]) + f" and {with_curves[-1]}, "
                 "listing the curves that sheet shows")
        return (f"Add a {title} table {where}, with columns {', '.join(headers[:-1])} and "
                f"{headers[-1]} (Δ in degrees, minutes and seconds, lengths to the hundredth), in "
                f"{self.text['table_height_in']:.2f} in text on {self.layer('tables')}")

    def north(self) -> str:
        block = self.S["sheet"]["north_arrow"]["block"]
        on = f" on {self.layer('symbols')}" if "symbols" in self.layers else ""
        where = "each sheet" if self.many else "the sheet"
        north = f", turned {self.twist:.2f}° to point to true north" if self.twisted else ""
        return f"Put the {block} block in the upper right of {where}{on}{north}"

    def title(self) -> str:
        fields = [sh["title_block_fields"] for sh in self.sheets]
        common = {k: v for k, v in fields[0].items()
                  if k != "sheet_number" and all(f.get(k) == v for f in fields)}
        if len(common) != len(fields[0]) - 1:  # the sheets differ in more than their numbers
            return "; ".join(f"on {sh['name']}, " + self._title_of(sh["title_block_fields"])
                             for sh in self.sheets)
        numbers = _and([f["sheet_number"] for f in fields])
        return self._title_of({**fields[0], "sheet_number": numbers},
                              plural=len(fields) > 1)

    @staticmethod
    def _title_of(tb: dict, plural: bool = False) -> str:
        roles = {}
        for role in ("designed", "drawn", "checked"):
            roles.setdefault(tb[f"{role}_by"], []).append(role)
        people = ", ".join(" and ".join(r) + f" by {who}" for who, r in roles.items())
        return (f"project {tb['project']}, agency {tb['agency']}, sheet title "
                f"{tb['sheet_title']}, sheet{'s' if plural else ''} {tb['sheet_number']} of "
                f"{tb['total_sheets']}, {people}, dated {tb['date']}, scale {tb['scale']}")

    def viewports(self) -> str:
        if not self.many:
            return f"one viewport at {self.scale}{self.turned()} showing all of {self.A}"
        return (f"a viewport at {self.scale}{self.turned()} on each sheet showing its part of "
                f"{self.A}")

    def match_line(self) -> str:
        m = self.match
        on = self.layer("match") if "match" in self.layers else self.layer("ticks")
        if len(self.match_texts) > 1:
            return (f"Draw a match line square across the centerline at each break "
                    f"({_and(self.match_texts)}), {m['half_width_ft']:g} ft each side, and label "
                    f"each at its end on both sheets it joins MATCH LINE STA <its station> SEE "
                    f"SHEET <the other sheet> in {self.label_h} text, all on {on}")
        return (f"Draw a match line square across the centerline at {m['station_text']}, "
                f"{m['half_width_ft']:g} ft each side, and label it at its end on each sheet "
                f"MATCH LINE STA {m['station_text']} SEE SHEET <the other sheet> in "
                f"{self.label_h} text, both on {on}")

    def breaking(self) -> str:
        if len(self.match_texts) > 1:
            return f", breaking at stations {_and(self.match_texts)}"
        return f", breaking at station {self.match['station_text']}" if self.match else ""

    def match_words(self) -> str:
        """The match lines a set-up layout already has, for the annotate prompts."""
        if len(self.match_texts) > 1:
            return f" and match lines at {_and(self.match_texts)}"
        return f" and a match line at {self.match['station_text']}" if self.match else ""

    # -- plan prep
    def section_words(self) -> str:
        lanes, lw = self.section.get("lanes", 2), self.section.get("lane_width_ft", 12)
        words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
        return f"{self.A} is {words.get(lanes, lanes)} {lw:g}-ft lanes"

    def edges(self) -> str:
        half = self.pave.get("half_width_ft", 12)
        return (f"Draw the edges of pavement {half:g} ft either side of the centerline, "
                f"following it through the curves, on {self.layer('edges')}")

    def widths(self) -> str:
        width = self.section.get("pavement_width_ft", 24)
        at = [f"{wd['station_text']} on {wd['ref']}" for wd in self.width_dims]
        where = at[0] if len(at) == 1 else ", ".join(at[:-1]) + f" and {at[-1]}"
        return (f"dimension the {width:.2f}' pavement width edge to edge across each tangent, "
                f"at {where}, in {self.label_h} text on {self.layer('dims')}")

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
        if with_props:  # grouped by their colour, linetype and weight, as a PE would read them off
            groups: Dict[str, List[str]] = {}
            for name in self.layer_set:
                groups.setdefault(self.layer_props(name), []).append(name)
            return "; ".join(f"{', '.join(names)} in {props}" for props, names in groups.items())
        return ", ".join(self.layer_set)

    def layer_props(self, name: str) -> str:
        p = self.props[name]
        linetype = f" {p['linetype']} linetype" if "linetype" in p else ""
        return f"{p['color']}{linetype} at {p['lineweight_mm']:g} mm"

    # -- what is already there
    def done(self) -> str:
        given = [p for p in PHASE_ORDER if p in self.type.given and p not in ("layers", "design")]
        if not given:
            return ""
        words = {"design": "", "linework": "the centerline", "edges": "the pavement edges",
                 "stationing": "the stationing", "bearings": "the bearings",
                 "callouts": "the curve callouts", "widths": "the width dimensions",
                 "sheet": f"{self.sheet_list} with {'their viewports' if self.many else 'its viewport'}"
                          + (" and the match line" if self.match else ""),
                 "reference": "the base drawing reference",
                 "table": "the curve data table" + ("s" if self.many else ""),
                 "north": "the north arrow" + ("s" if self.many else ""),
                 "title": "the title block" + ("s" if self.many else ""),
                 "notes": "the construction callouts"}
        items = [words[p] for p in given]
        text = items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"
        return f" {text[0].upper()}{text[1:]} {'are' if len(items) > 1 else 'is'} already done."


def _and(items: List[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"


def _bullets(items: List[str]) -> str:
    return "\n".join(f"- {s[0].upper()}{s[1:]}." for s in items)


def _sentences(items: List[str]) -> str:
    return " ".join(f"{s[0].upper()}{s[1:]}." for s in items)


def _alignment_data(w: _Words, it: str, table: bool = True) -> List[str]:
    """The alignment data a sheet letters: stationing, curve points, callouts,
    bearings, the one height and layer they share, then the curve table."""
    items = [w.stationing(it), w.curve_points(), w.callouts(), w.bearings(), w.lettering()]
    return items + ([w.table()] if table else [])


# ----------------------------------------------------------------- prompts


def _draw_alignment(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Draw the centerline of {w.A} in model space on {w.layer('alignment')}, right on "
                f"the design geometry. The layers exist; draw nothing else.")
    return f"Draw {w.A}."


def _stationing(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Station {w.A}."
    shows = "show" if w.many else "shows"
    return (f"Working in model space where {w.sheet_list} {shows} it, "
            f"{w.stationing(w.A, 'station')}. {_sentences([w.curve_points(), w.lettering()])}"
            f"{w.done()}{w.reading()}")


def _callouts(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"{w.callouts(f' of {w.A}')}, in {w.label_h} text on {w.layer('labels')}."
                f"{w.done()}{w.reading()}")
    return f"Number the curves on {w.A}."


def _bearings(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"{w.bearings(f' of {w.A}')}, in {w.label_h} text on {w.layer('labels')}."
                f"{w.done()}{w.reading()}")
    return f"Add bearings to {w.A}."


def _curve_table(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"{w.table()}.{w.done()}"
    return f"Put the curve data on {w.sheet_list}."


def _title_block(w: _Words, explicit: bool) -> str:
    if explicit:
        blocks = "title blocks" if w.many else "title block"
        return f"Fill in the {blocks}: {w.title()}. {w.north()}.{w.done()}"
    arrows = "north arrows" if w.many else "a north arrow"
    blocks = "title blocks" if w.many else "title block"
    return f"Finish the {blocks} on {w.sheet_list} and add {arrows}."


def _sheet_setup(w: _Words, explicit: bool) -> str:
    if not explicit:
        verb = "Set up plan " + w.sheet_list
        return f"{verb} for {w.A}{w.breaking()}{w.turned_views()}."
    if not w.many:
        return (f"Set up plan {w.sheet_list}, {w.size}, with {w.viewports()}.{w.done()}"
                f"{w.lettered()}")
    return (f"Lay out {w.A} on {_COUNT.get(len(w.sheets), len(w.sheets))} {w.size} plan sheets, "
            f"{w.sheet_list[7:]}, at {w.scale}{w.breaking()}, with a viewport on each sheet"
            f"{w.turned()} showing its part of the line. {w.match_line()}.{w.done()}"
            f"{w.lettered()}")


def _annotate_sheet(w: _Words, explicit: bool) -> str:
    is_are = "are" if w.many else "is"
    crowded = bool(w.D.get("crowd"))  # (the crowd dial: the sheet is not blank, the line is)
    if not explicit:
        if crowded:
            return f"Nothing of {w.A} is annotated on {w.sheet_list} yet. Annotate it."
        return f"{w.Sheet_list} {is_are} blank. Annotate {'them' if w.many else 'it'}."
    match = w.match_words()
    them = "them" if w.many else "it"
    views = "viewports" if w.many else "a viewport"
    nothing = f"nothing of {w.A} is annotated yet" if crowded else "nothing is annotated yet"
    return (f"{w.Sheet_list} {is_are} set up with {views} on {w.A} at {w.scale}{w.turned()}"
            f"{match}, and the centerline is drawn, but {nothing}."
            f"{w.reading(stated=True)} Annotate {them} fully:\n"
            f"{_bullets(_alignment_data(w, 'the line') + [w.north(), 'Fill in the title block' + ('s' if w.many else '') + ': ' + w.title()])}")


def _plan_sheet(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Draft plan {w.sheet_list} for {w.A}{w.breaking()}{w.turned_views()}."
    setup = f"Set up {w.viewports()}" + (f". {w.match_line()}" if w.match else "")
    items = ([setup, w.linework()] + _alignment_data(w, "it")
             + [w.north(), "Fill in the title block" + ("s" if w.many else "") + ": " + w.title()])
    return (f"Draft plan {w.sheet_list} for {w.A} on the {w.P['name']} project ({w.P['agency']}, "
            f"{w.P['county']}): {w.size} at {w.scale}{w.breaking()}{w.turned_views()}. {w.A} is "
            f"already in the design.{w.reading(stated=True)}\n{_bullets(items)}")


# -- the harder whole-sheet jobs (types.HARD_TASK_TYPES, the d1-test-hard set)


def _plan_sheet_items(w: _Words, alignment: List[str], extra: List[str] = ()) -> List[str]:
    """The bullets of a whole plan sheet: the viewports (and match lines), then
    ``alignment`` (the linework and pavement, as the job has them), the
    alignment data, the north arrow and the title block."""
    setup = f"Set up {w.viewports()}" + (f". {w.match_line()}" if w.match else "")
    return ([setup] + list(alignment) + _alignment_data(w, "it") + list(extra)
            + [w.north(), "Fill in the title block" + ("s" if w.many else "") + ": " + w.title()])


def _plan_sheet_pavement(w: _Words, explicit: bool) -> str:
    if not explicit:
        return (f"{w.section_words()}. Draft plan {w.sheet_list} for {w.A}{w.breaking()}"
                f"{w.turned_views()}, with "
                f"the pavement edges and a width dimension across each tangent.")
    items = _plan_sheet_items(w, [w.linework(), w.edges(), w.widths()])
    return (f"Draft plan {w.sheet_list} for {w.A} on the {w.P['name']} project ({w.P['agency']}, "
            f"{w.P['county']}): {w.size} at {w.scale}{w.breaking()}{w.turned_views()}. {w.A} is "
            f"already in the "
            f"design and {w.section_words()[len(w.A) + 1:]}.{w.reading(stated=True)}"
            f"{w.dims_reading(stated=True)}\n{_bullets(items)}")


def _create_plan_sheet(w: _Words, explicit: bool) -> str:
    if not explicit:
        return (f"{w.A} {w.geometry()}. Create it, then draft plan {w.sheet_list} for it"
                f"{w.breaking()}{w.turned_views()}.")
    items = _plan_sheet_items(w, [w.linework()])
    return (f"{w.A} is not in the design yet: it {w.geometry()}. Coordinates are northing and "
            f"easting in US survey feet. Create it in the design from the PIs and the curve "
            f"radius at each, then draft plan {w.sheet_list} for it on the {w.P['name']} project "
            f"({w.P['agency']}, {w.P['county']}): {w.size} at {w.scale}{w.breaking()}"
            f"{w.turned_views()}.{w.reading(stated=True)}\n{_bullets(items)}")


def _base_plan_sheet(w: _Words, explicit: bool) -> str:
    ref = w.ref_name
    if not explicit:
        return (f"The base drawing is attached as {ref}. Draft plan {w.sheet_list} for {w.A} in "
                f"this file{w.breaking()}{w.turned_views()}.")
    items = _plan_sheet_items(w, [])
    return (f"This sheet file has no sheets yet. The base drawing {w.basefile} is attached as "
            f"{ref} and carries {w.A}'s design, centerline and pavement edges; {w.A} lives in the "
            f"base, not in this file, so reach it as {ref}:{w.A}. Draft plan {w.sheet_list} for it "
            f"on the {w.P['name']} project ({w.P['agency']}, {w.P['county']}): {w.size} at "
            f"{w.scale}{w.breaking()}{w.turned_views()}.{w.reading(stated=True)}\n"
            f"{_bullets(items)}")


# -- the sheet breaks left to the drafter (types.TRAIN_TASK_TYPES, tasks.breaks): training only


def _plan_sheet_breaks(w: _Words, explicit: bool) -> str:
    """The whole plan sheet job with the count and the breaks left open.  No
    word here may give the count away (``sheet`` or ``sheets``, ``each`` of two,
    a list of names), so none of the pieces that speak of ``w.sheets`` is used:
    the prompt names the first sheet's number and the rest follow from it."""
    from roaddraft.tasks import breaks  # (it imports the generator, which imports this)
    first = breaks.FIRST_SHEET
    turned = f", every viewport turned {w.twist:.2f}°" if w.twisted else ""
    if not explicit:
        return f"Draft the plan sheets for {w.A} at {w.scale}, numbered from {first}{turned}."
    fpi = float(w.D["feet_per_inch"])
    fit_w, fit_h = w.S["sheet"]["fit_window_in"]
    half = breaks.gen.MATCH_HALF_IN * fpi
    on = w.layer("match") if "match" in w.layers else w.layer("ticks")
    headers = [CURVE_COLUMNS[c][0] for c in w.D["curve_table_columns"]]
    block = w.S["sheet"]["north_arrow"]["block"]
    north = f", turned {w.twist:.2f}° to point to true north" if w.twisted else ""
    tb = w.sheets[0]["title_block_fields"]
    roles: Dict[str, List[str]] = {}
    for role in ("designed", "drawn", "checked"):
        roles.setdefault(tb[f"{role}_by"], []).append(role)
    people = ", ".join(" and ".join(r) + f" by {who}" for who, r in roles.items())
    items = ([f"Set up a viewport at {w.scale}{w.turned()} on each sheet showing its part of "
              f"{w.A}, with all of that part's lettering whole inside it. At each break draw a "
              f"match line square across the centerline, {half:g} ft each side, and label it at "
              f"its end on both sheets it joins MATCH LINE STA <its station> SEE SHEET <the other "
              f"sheet> in {w.label_h} text, all on {on}", w.linework()]
             + _alignment_data(w, "it", table=False)
             + [f"Add a {w.S['curve_table']['title']} table on each sheet that shows a curve, "
                f"listing the curves that sheet shows, with columns {', '.join(headers[:-1])} and "
                f"{headers[-1]} (Δ in degrees, minutes and seconds, lengths to the hundredth), in "
                f"{w.text['table_height_in']:.2f} in text on {w.layer('tables')}",
                f"Put the {block} block in the upper right of every sheet on "
                f"{w.layer('symbols')}{north}",
                f"Fill in every title block: project {tb['project']}, agency {tb['agency']}, sheet "
                f"title {tb['sheet_title']}, the sheet's own number and the number of sheets, "
                f"{people}, dated {tb['date']}, scale {tb['scale']}"])
    reading = " Letter model-space labels to read upright as plotted." if w.twisted else ""
    return (f"Draft the plan sheets for {w.A} on the {w.P['name']} project ({w.P['agency']}, "
            f"{w.P['county']}): {w.size} at {w.scale}, numbered from {first} in order along the "
            f"line{turned}. {w.A} is already in the design.{reading}\n"
            f"How many sheets and where they break is yours to decide. Use as few sheets as the "
            f"line takes: a sheet holds the stretch of the line that fits the office's {fit_w:g} "
            f"by {fit_h:g} in plan window with {breaks.MARGIN_IN:.2f} in clear all round. Break "
            f"only where a match line is sound, at least {breaks.CLEAR_FT:g} ft along the line "
            f"from a curve's BC, EC or middle"
            + (", from the station equation" if w.has_eq else "")
            + f" and from either end of the line. A line that fits one sheet gets one sheet and "
            f"no match line.\n{_bullets(items)}")


# -- plan prep


def _layer_setup(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Set up the Caltrans named levels a layout sheet file carries as layers of this "
                f"drawing: {w.layer_list(with_props=True)}. Nothing is drawn yet; draw nothing.")
    return f"Set up the standard Caltrans levels: {w.layer_list(with_props=False)}."


def _pavement_edges(w: _Words, explicit: bool) -> str:
    if explicit:
        return f"{w.section_words()}. {w.edges()}.{w.done()}"
    return f"{w.section_words()}. Draw the pavement edges."


def _pavement_widths(w: _Words, explicit: bool) -> str:
    if explicit:
        text = w.widths()
        return f"{w.section_words()}. {text[0].upper()}{text[1:]}.{w.done()}{w.dims_reading()}"
    return f"Dimension the pavement width on each tangent of {w.A}."


def _pavement(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"{w.section_words()}. {w.edges()}, then {w.widths()}.{w.done()}"
                f"{w.dims_reading()}")
    return f"{w.section_words()}. Draw the pavement edges and dimension the width on each tangent."


def _annotate_base(w: _Words, explicit: bool) -> str:
    ref = w.S.get("reference", {}).get("name", "BASE")
    if not explicit:
        return (f"The base drawing is attached as {ref}. Add the alignment data of {w.A} to "
                f"{w.sheet_list}.")
    return (f"{w.Sheet_list} and {'their viewports' if w.many else 'its viewport'} on {w.A} are "
            f"set up in this file, and the base drawing {w.basefile} is attached as {ref}. {w.A} "
            f"lives in the base, not in this file, so reach it as {ref}:{w.A}.{w.reading()} Letter "
            f"its alignment data here:\n{_bullets(_alignment_data(w, 'it'))}")


def _base_context(w: _Words) -> str:
    """Where the drafter is on a finished sheet whose line lives in a base drawing: the
    sheet, the base drawing and any other the sheet file references (the bulk dial's
    survey base, ``tasks.bulk``)."""
    also = [f"{r['file']} as {r['name']}" for r in w.D.get("references") or []]
    more = (f" The sheet file references {_and(also)} too." if also else "")
    return (f"{w.Sheet_list} is {_a(w.size)} plan sheet at {w.scale}, its viewport on {w.A}"
            f"{w.turned()}. {w.A} is not in this file: it lives in the base drawing "
            f"{w.basefile}, attached as {w.ref_name}, so reach it as {w.ref_name}:{w.A}.{more}"
            f"{w.reading(stated=True)}")


def _base_given(w: _Words) -> str:
    """What a base lettering task is handed of the line's lettering."""
    words = {"stationing": "its stationing", "bearings": "its bearings",
             "callouts": "its curve callouts", "table": "its curve data table"}
    given = [words[p] for p in ("stationing", "bearings", "callouts", "table")
             if p in w.type.given]
    return f" {_and(given).capitalize()} are already done; keep them."


def _base_stationing(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Station the {w.A} line on {w.sheet_list}."
    return (f"{_base_context(w)}\nWorking in model space, {w.stationing(w.A, 'station')}. "
            f"{_sentences([w.curve_points(), w.lettering()])}{_base_given(w)}")


def _base_bearings(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Add the bearings of the {w.A} line to {w.sheet_list}."
    return (f"{_base_context(w)}\n{w.bearings(f' of {w.A}')}, in {w.label_h} text on "
            f"{w.layer('labels')}.{_base_given(w)}")


def _base_callouts(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Number the curves of the {w.A} line on {w.sheet_list}."
    return (f"{_base_context(w)}\n{w.callouts(f' of {w.A}')}, in {w.label_h} text on "
            f"{w.layer('labels')}.{_base_given(w)}")


def _attach_reference(w: _Words, explicit: bool) -> str:
    ref = w.S.get("reference", {})
    if explicit:
        many = w.many
        return (f"{w.Sheet_list} and {'their viewports' if many else 'its viewport'} on {w.A} are "
                f"set up in this file, but the drawing lives in the base file {w.basefile} beside "
                f"it. Attach that file as {ref.get('name', 'BASE')} in {ref.get('space', 'model')} "
                f"space at its own coordinates, so it shows through the "
                f"viewport{'s' if many else ''}.")
    return f"Attach the base drawing {w.basefile} to this sheet file."


# -- design input


def _create_alignment(w: _Words, explicit: bool) -> str:
    if explicit:
        return (f"Create alignment {w.A} in the design and draw its centerline. {w.A} "
                f"{w.geometry()}. Coordinates are northing and easting in US survey feet; build "
                f"it from the PIs and the curve radius at each, then draw it in model space on "
                f"{w.layer('alignment')}. The layers exist; draw nothing else.")
    return f"{w.A} {w.geometry()}. Create it and draw it."


_COUNT = {2: "two", 3: "three", 4: "four"}


# -- real plan sheets (tasks.real): one alignment of a redrafted sample sheet


def _a(word: str) -> str:
    """``word`` with its article: an ANSI, an FHWA (said letter by letter), a Caltrans."""
    first = word.split()[0] if word.split() else word
    initials = first.isupper() and len(first) > 1
    vowel = first[:1].upper() in ("AEFHILMNORSX" if initials else "AEIOU")
    return ("an " if vowel else "a ") + word


def _real_context(w: _Words) -> str:
    """Where the drafter is: the real sheet, and the base drawing its alignment lives in."""
    src = w.source
    others = src.get("other_alignments") or []
    also = (" along with " + (others[0] if len(others) == 1 else
                              ", ".join(others[:-1]) + f" and {others[-1]}") if others else "")
    return (f"Sheet {w.names[0]} is {_a(w.size)} {src.get('family', 'plan')} sheet at {w.scale} "
            f"from {_real_set(w)}. {w.A} is not in this file: it lives in the base drawing "
            f"{w.D.get('design_file')}, attached as {w.ref_name}{also}, so reach it as "
            f"{w.ref_name}:{w.A}." + _real_reading(w))


def _real_reading(w: _Words, stated: bool = False) -> str:
    """The twist and what it asks of the lettering; ``stated`` when the prompt has
    already given the viewport's turn."""
    twist = _real_twist(w)
    if abs(twist) <= 1e-6:
        return ""
    if stated:
        return " Letter model-space labels to read upright on the plotted sheet."
    return (f" The viewport is turned {twist:.2f}°, so letter model-space labels to read upright "
            f"on the plotted sheet.")


def _real_turned(w: _Words) -> str:
    """The existing viewport's turn, when it has one."""
    twist = _real_twist(w)
    return f" turned {twist:.2f}°" if abs(twist) > 1e-6 else ""


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
    return (f"{_real_context(w)}\nWorking in model space, {w.stationing(w.A, 'station')}. "
            f"{_sentences([w.curve_points(), w.lettering()])}{_real_given(w)}")


def _real_bearings(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Add the bearings of the {w.A} line to sheet {w.names[0]}."
    return (f"{_real_context(w)}\n{w.bearings(f' of {w.A}')}, in {w.label_h} text on "
            f"{w.layer('labels')}.{_real_given(w)}")


def _real_callouts(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Number the curves of the {w.A} line on sheet {w.names[0]}."
    return (f"{_real_context(w)}\n{w.callouts(f' of {w.A}')}, in {w.label_h} text on "
            f"{w.layer('labels')}.{_real_given(w)}")


def _real_curve_table(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Put the curve data of the {w.A} line on sheet {w.names[0]}."
    return (f"{_real_context(w)}\n{w.table()}, listing the curves of {w.A}.{_real_given(w)}")


def _real_alignment_data(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Letter the alignment data of the {w.A} line on sheet {w.names[0]}."
    return (f"{_real_context(w)}\n{w.A} has no annotation on this sheet yet. Letter its "
            f"alignment data:\n{_bullets(_alignment_data(w, 'it'))}")


# -- real plan sheets: the sheet's own jobs and the sheet from scratch


def _real_set(w: _Words) -> str:
    src = w.source
    return f"{_a(src.get('agency_name', ''))} plan set ({w.P['name']})"


def _real_twist(w: _Words) -> float:
    return float(w.D.get("view_rotation") or 0.0)


def _real_border(w: _Words) -> str:
    tpl = w.sheets[0].get("template") or "standard"
    return f"the {tpl} border (create_sheet title_block_template '{tpl}')"


def _real_files(w: _Words) -> str:
    files = [r["file"] for r in w.D.get("references") or []] or w.D.get("base_files") or []
    return ", ".join(files) or w.D.get("design_file", "")


_LINE_COUNTS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
                9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


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
    turned = f" (turned {turn:.2f}° here)" if abs(turn) > 1e-6 else ""
    return (f"Put the {block} block on the sheet pointing to true north{turned}, clear of the "
            f"title block and the plan, on {w.layer('symbols')}")


def _real_draw_alignment(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Draw the {w.A} line in this alignment file."
    return (f"This is {w.D.get('design_file')}, the alignment base file of {_real_set(w)}, "
            f"shown on sheet {w.names[0]} at {w.scale}. {w.A} is in its design but is not drawn "
            f"yet. {w.linework()}, right on the design geometry. The layers exist; draw nothing "
            f"else.")


def _real_attach_reference(w: _Words, explicit: bool) -> str:
    refs = w.D.get("references") or []
    if not explicit:
        return f"Attach the base files {_real_files(w)} to sheet {w.names[0]}."
    each = [f"{r['file']} as {r['name']}" for r in refs]
    each = each[0] if len(each) == 1 else ", ".join(each[:-1]) + f" and {each[-1]}"
    return (f"Sheet {w.names[0]} of {_real_set(w)} is drawn, border, notes and all, but its "
            f"viewport shows nothing: the base files beside it are not attached. Attach "
            f"{each}, in {refs[0]['space']} space at their own coordinates.")


def _real_title_block(w: _Words, explicit: bool) -> str:
    if not explicit:
        return f"Fill in the title block of sheet {w.names[0]}: {_real_title_vague(w)}."
    return (f"Fill in the title block of sheet {w.names[0]} of {_real_set(w)}: "
            f"{_real_title(w, False)}.")


def _real_sheet_setup(w: _Words, explicit: bool) -> str:
    twist = _real_twist(w)
    if not explicit:
        return (f"Set up plan sheet {w.names[0]} for the {w.A} line: {w.size}, on "
                f"{_real_border(w)}, the viewport turned {twist:.2f}° as published.")
    return (f"This sheet file of {_real_set(w)} has its base files {_real_files(w)} attached "
            f"and {w.A} drawn and annotated in model space, lettered for a sheet turned "
            f"{twist:.2f}°, but no sheet yet. Set up plan sheet {w.names[0]}, {w.size}, on "
            f"{_real_border(w)}, with one viewport at {w.scale} turned {twist:.2f}° showing all of "
            f"{w.A}.")


def _real_sheet_items(w: _Words) -> List[str]:
    return _alignment_data(w, "it") + [_real_north(w),
                                       f"Fill in the title block: {_real_title(w, False)}"]


def _real_annotate_sheet(w: _Words, explicit: bool) -> str:
    if not explicit:
        return (f"Sheet {w.names[0]} is blank. Annotate the {w.A} line and finish the sheet; "
                f"title block: {_real_title_vague(w)}.")
    return (f"Sheet {w.names[0]} of {_real_set(w)} is set up on {_real_border(w)} with a "
            f"viewport at {w.scale}{_real_turned(w)} on the attached base files, and {w.A} is "
            f"drawn, but nothing is lettered yet. {w.A} lives in the base, so reach it as "
            f"{w.ref_name}:{w.A}.{_real_reading(w, stated=True)} Annotate the sheet fully:\n"
            f"{_bullets(_real_sheet_items(w))}")


def _real_plan_sheet(w: _Words, explicit: bool) -> str:
    twist = _real_twist(w)
    if not explicit:
        return (f"Draft plan sheet {w.names[0]} for the {w.A} line from the base files, on "
                f"{_real_border(w)}, turned {twist:.2f}° as published; title block: "
                f"{_real_title_vague(w)}.")
    return (f"Draft plan sheet {w.names[0]} of {_real_set(w)} from the attached base files "
            f"{_real_files(w)}: {w.size}, on {_real_border(w)}, with one viewport at {w.scale} "
            f"turned {twist:.2f}° showing all of {w.A}. {w.A} lives in the base, so reach it as "
            f"{w.ref_name}:{w.A}.{_real_reading(w, stated=True)}\n"
            f"{_bullets(_real_sheet_items(w))}")


# -- real plan sheets: the construction callouts


def _note_target(c: dict) -> str:
    """Where a note points: on its line at a station, so many feet right or left of it."""
    off = float(c["offset"])
    at = f"{c['alignment']} at {c['station_text']}"
    if abs(off) < 0.05:
        return f"on {at}"
    return f"{abs(off):.1f} ft {'right' if off > 0 else 'left'} of {at}"


def _note_list(w: _Words) -> str:
    """The notes, each on its own bullet, the lines of a note indented under its target."""
    out = []
    for c in w.D["callouts"]:
        lines = "\n".join("    " + line for line in c["content"].split("\n"))
        out.append(f"- {_note_target(c)}:\n{lines}")
    return "\n".join(out)


def _note_lines(w: _Words) -> str:
    """The lines the notes point at, with the base drawing they live in."""
    names = list(dict.fromkeys(c["alignment"] for c in w.D["callouts"]))
    refs = list(dict.fromkeys(c["reference"] for c in w.D["callouts"]))
    lines = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    live = "lives" if len(names) == 1 else "live"
    ref = refs[0]
    return (f"{lines} {live} in the base drawing {w.D.get('design_file')}, attached as {ref}, "
            f"so name {'it' if len(names) == 1 else 'each'} as {ref}:{names[0]}")


def _real_construction_callouts(w: _Words, explicit: bool) -> str:
    notes = w.D["callouts"]
    n = len(notes)
    count = _LINE_COUNTS.get(n, str(n)) if n > 1 else "one"
    if not explicit:
        return (f"Add these construction notes to sheet {w.names[0]} as callouts, each pointing "
                f"at the place given:\n{_note_list(w)}")
    heights = sorted((c["height"] for c in notes), key=lambda h: (-[c["height"] for c in notes].count(h), h))
    h = heights[0]
    src = w.source
    return (f"Sheet {w.names[0]} is {_a(w.size)} {src.get('family', 'plan')} sheet at {w.scale} "
            f"from {_real_set(w)}. {_note_lines(w)}. {count[0].upper()}{count[1:]} of its "
            f"construction callouts {'is' if n == 1 else 'are'} missing. Place each one on sheet "
            f"{w.names[0]}, in sheet space, as a callout: the note in {h:.2f} in text, and a "
            f"leader whose tip lands on the point given as a station and offset on the line named "
            f"(right is to the right looking up-station). Aim the leader at that station and "
            f"offset through the line (place_callout with target_anchor and the line's "
            f"name), not at a point worked out by hand, and keep the note clear of the sheet's "
            f"lettering and linework. The notes:\n{_note_list(w)}")


# -- real plan sheets: the whole job (types.REAL_JOB_TYPES, the d1-real-hard set)


def _job_notes(w: _Words, explicit: bool) -> str:
    """The construction callouts a whole job places after the rest of the sheet."""
    if not explicit:
        return (f"Add its construction notes as callouts, each pointing at the place given:\n"
                f"{_note_list(w)}")
    notes = w.D["callouts"]
    h = sorted((c["height"] for c in notes),
               key=lambda h: (-[c["height"] for c in notes].count(h), h))[0]
    return (f"Then place the sheet's construction callouts on sheet {w.names[0]}, in sheet space: "
            f"each note in {h:.2f} in text with a leader whose tip lands on the point given as a "
            f"station and offset on the line named (right is to the right looking up-station). "
            f"{_note_lines(w)}. Aim each leader at its station and offset through the line "
            f"(place_callout with target_anchor and the line's name), not at a point worked out "
            f"by hand, and keep every note clear of the lettering and linework. The notes:\n"
            f"{_note_list(w)}")


def _real_sheet_job(w: _Words, explicit: bool) -> str:
    return f"{_real_plan_sheet(w, explicit)}\n{_job_notes(w, explicit)}"


def _real_annotate_job(w: _Words, explicit: bool) -> str:
    return f"{_real_annotate_sheet(w, explicit)}\n{_job_notes(w, explicit)}"


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
    "plan-sheet-pavement": _plan_sheet_pavement,
    "create-plan-sheet": _create_plan_sheet,
    "base-plan-sheet": _base_plan_sheet,
    "plan-sheet-breaks": _plan_sheet_breaks,
    "base-stationing": _base_stationing,
    "base-bearings": _base_bearings,
    "base-callouts": _base_callouts,
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
    "real-construction-callouts": _real_construction_callouts,
    "real-sheet-job": _real_sheet_job,
    "real-annotate-job": _real_annotate_job,
}


def prompt(brief: TaskBrief, level: str) -> str:
    """The prompt for ``brief`` at ``level`` (``explicit`` or ``vague``)."""
    if level not in LEVELS:
        raise ValueError(f"unknown prompt level {level!r}; levels: {', '.join(LEVELS)}")
    w = _Words(brief)
    if w.D.get("revision"):  # the revision dial: a finished sheet, its design since changed
        return _revision(w, level == "explicit")
    text = PROMPTS[w.type.name](w, level == "explicit")
    crowd = _crowd(w, level == "explicit")
    if crowd:
        text += ("\n" if "\n" in text else " ") + crowd
    return text


def _revision_words(w: _Words) -> str:
    """The change itself, as the designer reports it (both levels: it is the redline)."""
    R = w.D["revision"]
    if R["kind"] == "radius":
        return (f"curve {R['curve']}'s radius is now {R['to']:g}' (it was {R['from']:g}'), every "
                f"PI held")
    if R["kind"] == "pi":
        way = "ahead" if R["by"] > 0 else "back"
        return (f"the PI of curve {R['curve']} has moved {abs(R['by']):.2f} ft {way} along its back "
                f"tangent, its radius and every other PI held")
    return f"{w.A} is restationed to begin at {R['to']} (it began at {R['from']}), its geometry held"


def _revision(w: _Words, explicit: bool) -> str:
    """A revised task's prompt (the generator's revision dial, ``tasks.revise``).
    The vague words name the sheet, where the line lives and the change, and no
    more: the notes that cite the line are the knock-on edit nobody names, as on
    the redline pilots (``p11``).  Where the change is the drafter's to make,
    they say so and where (this file, or the base drawing), and not how: the
    explicit words alone name the base drawing's file, its linework to redraw
    and the reference to reload."""
    change = _revision_words(w)
    # the change left for the drafter to make in the base drawing (tasks.revise.BASE_KINDS)
    in_base = w.type.design_referenced and bool(w.D["revision"].get("by_drafter"))
    if in_base:
        where = (f"{w.A} lives in the base drawing attached as {w.ref_name}, and {w.sheet_list} "
                 f"letters it through the reference as {w.ref_name}:{w.A}. The designer has revised "
                 f"it: {change}.")
    elif w.type.design_referenced:
        where = (f"{w.A} lives in the base drawing attached as {w.ref_name}, and {w.sheet_list} "
                 f"letters it through the reference as {w.ref_name}:{w.A}. The designer has revised "
                 f"{w.A} there and redrawn its linework: {change}.")
    else:  # the design lives in this file, so the change is the drafter's to make
        where = (f"{w.Sheet_list} is lettered for {w.A}, whose design lives in this file. The "
                 f"designer has revised it: {change}.")
    if not explicit:
        if in_base:
            return (f"{where} Make the change in the base drawing and bring {w.sheet_list} up to "
                    f"date.")
        if not w.type.design_referenced:
            return f"{where} Make the change and bring {w.sheet_list} up to date."
        return f"{where} Bring {w.sheet_list} up to date."
    if in_base:
        make = (f" Make the change in the base drawing, {w.basefile}: open it, change {w.A}'s "
                f"design there and redraw its centerline to it on {w.layer('alignment')} and its "
                f"pavement edges on {w.pave.get('layer') or w.layer('edges')}; then come back to "
                f"this file and reload the reference.")
    else:
        make = ("" if w.type.design_referenced else
                f" Make the change in this file's design and redraw {w.A}'s centerline to it, on "
                f"{w.layer('alignment')}.")
    return (f"{where}{make} Bring {w.sheet_list} up to date with the revised design.{w.reading()} "
            f"Whatever the change touches is lettered again with the design's own labels, the "
            f"office's way:\n{_bullets(_alignment_data(w, 'the line'))}\nNothing lettered from "
            f"before the change may be left, and a note on the sheet that cites a station of "
            f"{w.A} must cite the same point of the line, restationed. Keep everything else as "
            f"it is.")


def _crowd(w: _Words, explicit: bool) -> str:
    """What a crowded task (the generator's crowd dial, ``tasks.crowd``) adds to
    its prompt: nothing at all on an uncrowded one.  The vague words are the
    crowded pilots' (``p04``)."""
    crowd = w.D.get("crowd")
    if not crowd:
        return ""
    if not explicit:
        return "The sheet is crowded; keep everything already on it."
    name = crowd["alignment"].get("name") or "ALIGN-2"
    n = len(crowd["notes"])
    notes = "a note" if n == 1 else f"{_COUNT.get(n, n)} notes"
    return (f"The sheet is not empty: it already shows another line, {name}, across {w.A} with "
            f"its own lettering, and {notes} lettered on the paper. Keep all of it. Nothing you "
            f"add may sit on other lettering as plotted: where a label would, set that label "
            f"again on the other side of the line or further off it, with the design's own "
            f"label, rather than dragging it off its anchor.")


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
