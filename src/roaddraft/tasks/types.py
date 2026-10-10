"""The D1 task types: what a task starts with and what it asks for.

A plan sheet is drafted in phases -- layers, linework, stationing, bearings,
callouts, the sheet, the curve table, the north arrow, the title block --
and a task hands the drafter a document with some phases done and asks for
others (decided 2026-10-10: one piece of work per task, a few whole sheets
from scratch, a few across two sheets).  Each phase produces a *group* of
truth items; the verifier grades only the groups a task asks for (its
``scope``) and renormalises the rubric to 100 over the checks those groups
drive.  Phases a task neither gives nor asks for are simply absent and
ungraded (a sheet-setup task has no table to show yet).

``layers`` is a phase without a group: every partial task is handed the
office's layer set, and the from-scratch task creates it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple

#: the drafting phases in reference order, and the truth group each produces
PHASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("layers", ()),
    ("linework", ("linework",)),
    ("stationing", ("ticks", "stations", "curve_points")),
    ("bearings", ("bearings",)),
    ("callouts", ("callouts",)),
    ("sheet", ("sheet",)),
    ("table", ("table",)),
    ("north", ("north",)),
    ("title", ("title",)),
)
PHASE_ORDER = [name for name, _ in PHASES]
GROUPS: Tuple[str, ...] = tuple(g for _, gs in PHASES for g in gs)
GROUP_PHASE: Dict[str, str] = {g: name for name, gs in PHASES for g in gs}

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
    "D1-08": LABEL_GROUPS + ("table", "north", "sheet"),
    "D1-09": LABEL_GROUPS + ("ticks", "linework", "table"),
    "D1-10": ("title",),
    "D1-11": ("north",),
}


@dataclass(frozen=True)
class TaskType:
    name: str
    asks: FrozenSet[str]   # groups the task asks for (the verifier's scope)
    given: FrozenSet[str]  # phases already done in the starting document
    summary: str           # one line for people

    @property
    def start(self) -> str:
        """Where the drafter starts: ``model`` (no sheet yet) or ``sheet``."""
        return "sheet" if "sheet" in self.given else "model"

    def solution_phases(self) -> List[str]:
        """Phases the reference solution runs on the starting document."""
        return [p for p, gs in PHASES
                if p not in self.given and (p == "layers" or any(g in self.asks for g in gs))]

    def shown(self) -> List[str]:
        """Phases present on the finished reference drawing (given or asked)."""
        return [p for p, gs in PHASES if p in self.given or any(g in self.asks for g in gs)]


def _type(name, asks, given, summary) -> TaskType:
    return TaskType(name, frozenset(asks), frozenset(given), summary)


_ALL_BUT = lambda *phases: [p for p in PHASE_ORDER if p not in phases]  # noqa: E731

TASK_TYPES: Dict[str, TaskType] = {t.name: t for t in (
    _type("draw-alignment", ["linework"], ["layers"],
          "draw the centerline in the model from the design"),
    _type("stationing", ["ticks", "stations", "curve_points"], _ALL_BUT("stationing"),
          "station the drawn alignment: ticks, station labels, BC/EC"),
    _type("curve-callouts", ["callouts"], _ALL_BUT("callouts"),
          "number the curves at their midpoints"),
    _type("bearings", ["bearings"], _ALL_BUT("bearings"),
          "label the bearing of every tangent"),
    _type("curve-table", ["table"], _ALL_BUT("table"),
          "add the curve data table to the sheet(s)"),
    _type("title-block", ["title", "north"], _ALL_BUT("title", "north"),
          "fill the title block(s) and place the north arrow(s)"),
    _type("sheet-setup", ["sheet"], ["layers", "linework", "stationing", "bearings", "callouts"],
          "lay out the annotated model on plan sheet(s)"),
    _type("annotate-sheet", ["ticks", "stations", "curve_points", "callouts", "bearings",
                             "table", "title", "north"], ["layers", "linework", "sheet"],
          "annotate an empty, set-up sheet from scratch"),
    _type("plan-sheet", list(GROUPS), [],
          "draft the whole plan sheet from the design"),
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


__all__ = ["PHASES", "PHASE_ORDER", "GROUPS", "GROUP_PHASE", "LABEL_GROUPS", "CHECK_GROUPS",
           "TaskType", "TASK_TYPES", "DEFAULT_TYPE", "task_type", "checks_in_scope"]
