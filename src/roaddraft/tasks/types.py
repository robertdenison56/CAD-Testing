"""The D1 task types: what a task starts with and what it asks for.

A plan sheet is drafted in phases -- layers, linework, pavement edges,
stationing, bearings, callouts, width dimensions, the sheet, the curve table,
the north arrow, the title block -- and a task hands the drafter a document
with some phases done and asks for others (decided 2026-10-10: one piece of
work per task, a few whole sheets from scratch, a few across two sheets, and
the general plan-prep jobs: layers, references, pavement edges and widths).
Each phase produces a *group* of truth items; the verifier grades only the
groups a task asks for (its ``scope``) and renormalises the rubric to 100
over the checks those groups drive.  Phases a task neither gives nor asks
for are simply absent and ungraded (a sheet-setup task has no table to show
yet).

A *basefile* type splits the drawing the way an office does: the model work
lives in a base drawing shipped with the task, the task's own document is the
sheet file, and the job is to attach the base as a reference.

``design`` is the alignment itself: every task but ``create-alignment`` is
handed it (seeded into the document, never drafted), and that one creates it
from the geometry the prompt states.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

#: the drafting phases in reference order, and the truth group each produces
PHASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("design", ("design",)),
    ("layers", ("layers",)),
    ("linework", ("linework",)),
    ("edges", ("edges",)),
    ("stationing", ("ticks", "stations", "curve_points")),
    ("bearings", ("bearings",)),
    ("callouts", ("callouts",)),
    ("widths", ("widths",)),
    ("reference", ("reference",)),
    ("sheet", ("sheet",)),
    ("table", ("table",)),
    ("north", ("north",)),
    ("title", ("title",)),
)
PHASE_ORDER = [name for name, _ in PHASES]
GROUPS: Tuple[str, ...] = tuple(g for _, gs in PHASES for g in gs)
GROUP_PHASE: Dict[str, str] = {g: name for name, gs in PHASES for g in gs}

#: the phases of a layout sheet: what ``plan-sheet`` draws and ``annotate-sheet`` annotates
LAYOUT_PHASES = ("layers", "linework", "stationing", "bearings", "callouts", "sheet", "table",
                 "north", "title")
#: the model-space phases a base drawing carries
MODEL_PHASES = ("layers", "linework", "edges", "stationing", "bearings", "callouts", "widths")

#: the groups each verifier check draws its items from; a check is in scope
#: when any of them is
LABEL_GROUPS = ("stations", "curve_points", "callouts", "bearings")
CHECK_GROUPS: Dict[str, Tuple[str, ...]] = {
    "D1-00": ("sheet",),
    "D1-01": ("linework",),
    "D1-02": ("ticks",),
    "D1-03": ("stations",),
    "D1-04": ("curve_points", "callouts"),
    "D1-05": ("bearings",),
    "D1-06": ("table",),
    "D1-07": LABEL_GROUPS,
    "D1-08": LABEL_GROUPS + ("table", "north", "sheet", "widths"),
    # (the "sheet" group joins D1-09 only on a two-sheet layout, whose match line and labels
    # have a level of their own; see verify.check_groups)
    "D1-09": LABEL_GROUPS + ("ticks", "linework", "table", "edges", "widths", "layers", "north"),
    "D1-10": ("title",),
    "D1-11": ("north",),
    "D1-12": ("edges",),
    "D1-13": ("widths",),
    "D1-14": ("reference",),
    "D1-15": ("design",),
}
#: which spec layer role each group's work is drawn on (D1-09)
GROUP_LAYER_ROLE: Dict[str, str] = {
    "linework": "alignment", "ticks": "ticks", "stations": "labels", "curve_points": "labels",
    "callouts": "labels", "bearings": "labels", "table": "tables", "edges": "edges",
    "widths": "dims", "north": "symbols", "sheet": "match",
}


@dataclass(frozen=True)
class TaskType:
    name: str
    asks: FrozenSet[str]   # groups the task asks for (the verifier's scope)
    given: FrozenSet[str]  # phases already done in the starting document
    summary: str           # one line for people
    basefile: FrozenSet[str] = frozenset()  # phases drafted in a shipped base drawing

    @property
    def start(self) -> str:
        """Where the drafter starts: ``model`` (no sheet yet) or ``sheet``."""
        return "sheet" if "sheet" in self.given else "model"

    @property
    def design_referenced(self) -> bool:
        """The design lives only in the attached base drawing: the task's own
        document neither holds it nor creates it, so every anchored label
        goes through the reference (``BASE:ALIGN-1``)."""
        return "design" not in self.given and "design" not in self.asks

    def solution_phases(self) -> List[str]:
        """Phases the reference solution runs on the starting document."""
        return [p for p, gs in PHASES
                if p not in self.given and p not in self.basefile
                and (p == "layers" or any(g in self.asks for g in gs))]

    def shown(self) -> List[str]:
        """Phases the reference drafts for the finished drawing: the layers,
        the design when it is the task (otherwise it is seeded, not drafted),
        and every phase given, asked for, or carried by the base drawing."""
        return [p for p, gs in PHASES
                if (p == "design" and "design" in self.asks)
                or (p != "design" and (p == "layers" or p in self.given or p in self.basefile
                                       or any(g in self.asks for g in gs)))]


def _type(name, asks, given, summary, basefile=(), owns_design=True) -> TaskType:
    given = set(given)
    if "design" not in asks and owns_design:
        given.add("design")  # the alignment is handed over unless creating it is the task
    return TaskType(name, frozenset(asks), frozenset(given), summary, frozenset(basefile))


def _layout_but(*phases) -> List[str]:
    return [p for p in LAYOUT_PHASES if p not in phases]


LAYOUT_GROUPS = tuple(g for p, gs in PHASES if p in LAYOUT_PHASES for g in gs if g != "layers")
#: groups an agent may add to the design: creating these is the task, not tampering
DESIGN_GROUPS = ("design",)

TASK_TYPES: Dict[str, TaskType] = {t.name: t for t in (
    # -- the layout sheet, one phase at a time
    _type("draw-alignment", ["linework"], ["layers"],
          "draw the centerline in the model from the design"),
    _type("stationing", ["ticks", "stations", "curve_points"], _layout_but("stationing"),
          "station the drawn alignment: ticks, station labels, BC/EC"),
    _type("curve-callouts", ["callouts"], _layout_but("callouts"),
          "number the curves at their midpoints"),
    _type("bearings", ["bearings"], _layout_but("bearings"),
          "label the bearing of every tangent"),
    _type("curve-table", ["table"], _layout_but("table"),
          "add the curve data table to the sheet(s)"),
    _type("title-block", ["title", "north"], _layout_but("title", "north"),
          "fill the title block(s) and place the north arrow(s)"),
    _type("sheet-setup", ["sheet"], ["layers", "linework", "stationing", "bearings", "callouts"],
          "lay out the annotated model on plan sheet(s)"),
    _type("annotate-sheet", [g for g in LAYOUT_GROUPS if g not in ("linework", "sheet")],
          ["layers", "linework", "sheet"], "annotate an empty, set-up sheet from scratch"),
    _type("plan-sheet", list(LAYOUT_GROUPS), [], "draft the whole plan sheet from the design"),
    # -- general plan prep
    _type("layer-setup", ["layers"], [], "create the office's standard layer set"),
    _type("pavement-edges", ["edges"], LAYOUT_PHASES,
          "draw the edges of pavement at the typical section's width"),
    _type("pavement-widths", ["widths"], LAYOUT_PHASES + ("edges",),
          "dimension the pavement width across each tangent"),
    _type("pavement", ["edges", "widths"], LAYOUT_PHASES,
          "draw the pavement edges and dimension the width on each tangent"),
    _type("attach-reference", ["reference"], ["layers", "sheet"],
          "attach the base drawing to the sheet file as a reference",
          basefile=["linework", "edges", "stationing", "bearings", "callouts"]),
    # -- the sheet file annotates the base drawing it references: the design is in the base
    # only, and every label anchors through the reference (decided 2026-10-11, so the
    # benchmark's credit route is the one the Tier 3 probes use)
    _type("annotate-base", ["ticks", "stations", "curve_points", "bearings", "callouts", "table"],
          ["layers", "reference", "sheet"],
          "letter the alignment data of the referenced base drawing on the set-up sheet(s)",
          basefile=["linework", "edges"], owns_design=False),
    # -- design input
    _type("create-alignment", ["design", "linework"], ["layers"],
          "create the alignment from the PIs, radii and stationing the prompt gives, then draw it"),
)}

DEFAULT_TYPE = "plan-sheet"

#: phases a real plan sheet supplies (its base files, sheet, north arrow and title block)
REAL_SHEET_PHASES = ("layers", "linework", "reference", "sheet", "north", "title")


def _real(name, asks, given_annotation, summary) -> TaskType:
    return _type(name, asks, list(REAL_SHEET_PHASES) + list(given_annotation), summary,
                 owns_design=False)


#: tasks on the redrafted example plan sheets (``tasks.real``, decided 2026-10-13: the
#: benchmark's sheets come from real plan sets, not only the seeded generator).  The sheet
#: file references the real base files, so the design is referenced, never owned, and the
#: labels anchor through the reference (``AA01:TB1``); one alignment is lettered per task.
REAL_TASK_TYPES: Dict[str, TaskType] = {t.name: t for t in (
    _real("real-stationing", ["ticks", "stations", "curve_points"],
          ["bearings", "callouts", "table"],
          "station one alignment of a real plan sheet: ticks, station numbers, BC/EC"),
    _real("real-bearings", ["bearings"], ["stationing", "callouts", "table"],
          "label the tangent bearings of one alignment of a real plan sheet"),
    _real("real-callouts", ["callouts"], ["stationing", "bearings", "table"],
          "number the curves of one alignment of a real plan sheet"),
    _real("real-curve-table", ["table"], ["stationing", "bearings", "callouts"],
          "add one alignment's curve data table to a real plan sheet"),
    _real("real-alignment-data", ["ticks", "stations", "curve_points", "bearings", "callouts",
                                  "table"], [],
          "letter all the alignment data of one alignment on a real plan sheet"),
    # -- the rest of a sheet's jobs on the same real sets (decided 2026-10-13, Robert:
    # "convert"): drawing an alignment in its base file, re-attaching a sheet's base
    # files, its title block, and laying out or annotating a sheet from scratch
    _type("real-draw-alignment", ["linework"], ["layers"],
          "draw one alignment of a real plan set in its alignment base file"),
    _type("real-attach-reference", ["reference"],
          ["layers", "linework", "sheet", "north", "title", "stationing", "bearings",
           "callouts", "table"],
          "attach a real sheet file's base files as references", owns_design=False),
    _type("real-title-block", ["title"],
          ["layers", "linework", "reference", "sheet", "north", "stationing", "bearings",
           "callouts", "table"],
          "fill in a real sheet's title block", owns_design=False),
    _type("real-sheet-setup", ["sheet"],
          ["layers", "linework", "reference", "stationing", "bearings", "callouts"],
          "lay out a real sheet: its border and a viewport on the annotated model",
          owns_design=False),
    _type("real-annotate-sheet", ["ticks", "stations", "curve_points", "bearings", "callouts",
                                  "table", "north", "title"],
          ["layers", "linework", "reference", "sheet"],
          "annotate a blank real sheet from scratch: one alignment, table, north arrow, title",
          owns_design=False),
    _type("real-plan-sheet", ["sheet", "ticks", "stations", "curve_points", "bearings",
                              "callouts", "table", "north", "title"],
          ["layers", "linework", "reference"],
          "draft a real plan sheet from the base files: sheet, viewport, annotation",
          owns_design=False),
)}


def task_type(name: str) -> TaskType:
    try:
        return TASK_TYPES[name]
    except KeyError:
        pass
    try:
        return REAL_TASK_TYPES[name]
    except KeyError:
        raise ValueError(f"unknown task type {name!r}; types: "
                         f"{', '.join(list(TASK_TYPES) + list(REAL_TASK_TYPES))}") from None


def checks_in_scope(scope, check_ids, check_groups: Optional[Dict[str, Tuple[str, ...]]] = None
                    ) -> List[str]:
    """The check ids whose groups intersect ``scope`` (all of them for an
    empty scope, which is how a truth without one reads).  ``check_groups``
    overrides ``CHECK_GROUPS`` (the verifier adds the match level to D1-09 on
    a two-sheet layout)."""
    groups = CHECK_GROUPS if check_groups is None else check_groups
    scope = set(scope or GROUPS)
    return [c for c in check_ids if any(g in scope for g in groups.get(c, ()))]


__all__ = ["PHASES", "PHASE_ORDER", "GROUPS", "GROUP_PHASE", "LAYOUT_PHASES", "LAYOUT_GROUPS",
           "DESIGN_GROUPS",
           "MODEL_PHASES", "LABEL_GROUPS", "CHECK_GROUPS", "GROUP_LAYER_ROLE", "TaskType",
           "TASK_TYPES", "REAL_TASK_TYPES", "REAL_SHEET_PHASES", "DEFAULT_TYPE", "task_type",
           "checks_in_scope"]
