"""The system prompts (eval plan section 4.2): the role, how the engine
works, and how the episode runs -- the budgets, the mode's tools, submit.
The task's own rules (anchor your labels, leave the design alone) go with
the task text (``tasks.prompts``), not here.

One template, ``system_neutral.md``, in RoadDraft's own words and tool
names: no episode renames the tools (Robert, 2026-10-30), so ``neutral``
is the only dialect.  ``$steps``, ``$faults`` and ``$mode_rules`` are
filled from the episode's budgets and mode.  The rendered
prompt's digest goes into the trajectory header, so a changed word is a
changed run.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from string import Template
from typing import Optional

from roaddraft.eval.budget import Budgets

HERE = Path(__file__).resolve().parent

MODE_RULES = {
    "single": ("- This run is single-shot: there is no run_check and no render. Check the "
               "drawing with the queries (get_sheet_state, find_entities, get_entity) before "
               "you submit."),
    "self_correct": ("- run_check grades the document as it stands against the task and says "
                     "what is wrong, never the expected values. You may use it $run_checks "
                     "times; each use is a step.\n"
                     "- render_sheet and render_model draw a PNG to disk and return its path; "
                     "you cannot see the picture in this run."),
    "vision": ("- run_check grades the document as it stands against the task and says what "
               "is wrong, never the expected values. You may use it $run_checks times; each "
               "use is a step.\n"
               "- render_sheet and render_model return the picture, so you can look at your "
               "sheet."),
}


def template(dialect: str = "neutral") -> str:
    path = HERE / f"system_{dialect}.md"
    if not path.exists():
        raise ValueError(f"no system prompt for dialect {dialect!r}")
    return path.read_text(encoding="utf-8")


def system_prompt(dialect: str = "neutral", mode: str = "single",
                  budgets: Optional[Budgets] = None) -> str:
    """The system prompt of an episode in ``dialect`` and ``mode`` under
    ``budgets`` (the mode's budgets: ``run_checks`` is 0 in single mode)."""
    if mode not in MODE_RULES:
        raise ValueError(f"unknown mode {mode!r}")
    budgets = budgets or Budgets().for_mode(mode)
    values = {"steps": budgets.steps, "faults": budgets.faults, "run_checks": budgets.run_checks}
    rules = Template(MODE_RULES[mode]).substitute(values)
    return Template(template(dialect)).substitute(values, mode_rules=rules).strip() + "\n"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["MODE_RULES", "template", "system_prompt", "digest"]
