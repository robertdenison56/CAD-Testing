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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple

#: the drafting phases in reference order, and the truth group each produces
PHASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("layers", ("layers",)),
    ("linework", ("linework",)),
    ("edges", ("edges",)),
    ("stationing", ("ticks", "stations", "curve_points")),
    ("bearings", ("bearings",)),
    ("callouts", ("callouts",)),
    ("widths", ("widths",)),
    ("sheet", ("sheet",)),
    ("reference", ("reference",)),
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
    "D1-09": LABEL_GROUPS + ("ticks", "linework", "table", "edges", "widths", "layers"),
    "D1-10": ("title",),
    "D1-11": ("north",),
    "D1-12": ("edges",),
    "D1-13": ("widths",),
    "D1-14": ("reference",),
}
#: which spec layer role each group's work is drawn on (D1-09)
GROUP_LAYER_ROLE: Dict[str, str] = {
    "linework": "alignment", "ticks": "ticks", "stations": "labels", "curve_points": "labels",
    "callouts": "labels", "bearings": "labels", "table": "tables", "edges": "edges",
    "widths": "dims",
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

    def solution_phases(self) -> List[str]:
        """Phases the reference solution runs on the starting document."""
        return [p for p, gs in PHASES
                if p not in self.given and p not in self.basefile
                and (p == "layers" or any(g in self.asks for g in gs))]

    def shown(self) -> List[str]:
        """Phases present on the finished reference drawing: the layers, and
        every phase given, asked for, or carried by the base drawing."""
        return [p for p, gs in PHASES
                if p == "layers" or p in self.given or p in self.basefile
                or any(g in self.asks for g in gs)]


def _type(name, asks, given, summary, basefile=()) -> TaskType:
    return TaskType(name, frozenset(asks), frozenset(given), summary, frozenset(basefile))


def _layout_but(*phases) -> List[str]:
    return [p for p in LAYOUT_PHASES if p not in phases]


LAYOUT_GROUPS = tuple(g for p, gs in PHASES if p in LAYOUT_PHASES for g in gs if g != "layers")

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
)}

DEFAULT_TYPE = "plan-sheet"


def task_type(name: str) -> TaskType:
    try:
        return TASK_TYPES[name]
    except KeyError:
        raise ValueError(f"unknown task type {name!r}; types: {', '.join(TASK_TYPES)}") from None


def checks_in_scope(scope, check_ids) -> List[str]:
    """The check ids whose groups intersect ``scope`` (all of them for an
    empty scope, which is how a truth without one reads)."""
    scope = set(scope or GROUPS)
    return [c for c in check_ids if any(g in scope for g in CHECK_GROUPS.get(c, ()))]


__all__ = ["PHASES", "PHASE_ORDER", "GROUPS", "GROUP_PHASE", "LAYOUT_PHASES", "LAYOUT_GROUPS",
           "MODEL_PHASES", "LABEL_GROUPS", "CHECK_GROUPS", "GROUP_LAYER_ROLE", "TaskType",
           "TASK_TYPES", "DEFAULT_TYPE", "task_type", "checks_in_scope"]
