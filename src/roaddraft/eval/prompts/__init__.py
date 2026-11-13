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

A run may add one file to the end of that prompt (``--system-extra FILE``,
training plan stage T0: a convention sheet, measured as T0 minus base on the
same tasks).  ``SystemExtra`` is that file, read once for the run;
``with_extra`` appends its text.  With no extra the prompt is the template's,
byte for byte, so every run before the flag reads as it did.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Optional

from roaddraft.eval.budget import Budgets

HERE = Path(__file__).resolve().parent
#: the checkout: a system extra inside it is recorded by its path from here
REPO = HERE.parents[3]

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


@dataclass(frozen=True)
class SystemExtra:
    """A file a run appends to every system prompt it sends (``--system-extra``).

    ``path`` is where it was read, from the checkout's root when it lies inside
    it; ``sha256`` is the digest of the file's bytes; ``text`` is what is
    appended.  The run's ``run.json`` and every episode header name the file
    and its digest (``record``), and the episode's prompt hash covers its text."""
    path: str
    sha256: str
    text: str

    @classmethod
    def load(cls, path) -> "SystemExtra":
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read the system extra {path}: {exc.strerror or exc}") from None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"the system extra {path} is not UTF-8 text") from None
        if not text.strip():
            raise ValueError(f"the system extra {path} is empty")
        resolved = p.resolve()
        try:
            shown = resolved.relative_to(REPO.resolve()).as_posix()
        except ValueError:
            shown = resolved.as_posix()
        return cls(path=shown, sha256="sha256:" + hashlib.sha256(data).hexdigest(), text=text)

    def record(self) -> dict:
        """What a run's manifest and an episode's header say of it."""
        return {"path": self.path, "sha256": self.sha256}


def with_extra(system: str, extra: Optional[str]) -> str:
    """``system`` with a system extra's text after it, a blank line between;
    ``system`` itself, unchanged, when there is none."""
    if extra is None:
        return system
    return system.rstrip("\n") + "\n\n" + extra.strip() + "\n"


__all__ = ["MODE_RULES", "template", "system_prompt", "digest", "SystemExtra", "with_extra"]
