"""What a model is told when it is handed a probe.

The probe runs under ``benchmarks/probe_runs`` each carried a copy of this
text in their runner. It lives here so the recorded trajectories, the runners
and the tests hand a model the same words: the rules, the task, and the shape
of the report asked for at the end. ``task_text`` is the user message of a
probe conversation; the system message is the MCP server's ``INSTRUCTIONS``.
"""
from __future__ import annotations

from roaddraft.probes.base import Probe

RULES = """Do one drafting task in a headless CAD engine called RoadDraft, using the tools you have been given. They are your ENTIRE tool surface.

Rules:
- Every change to the drawing must go through a tool call.
- The document is already open and saves itself after each command. Do not save it under another name.
- Nobody can answer questions. Work until you judge the task done, then stop and give your report.{extra}

THE TASK:
{task}

{report}"""

#: the draft-probes' line: the arithmetic is part of what they measure
NO_CALCULATOR = ("\n- You have no calculator and no code execution. Any arithmetic you "
                 "need, do yourself.")

T2_REPORT = """When finished, reply briefly with:
1. What you placed, in which space, and what it points at.
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages."""

T1_REPORT = """When finished, reply briefly with:
1. What you created and drew (names, layers, key coordinates).
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages. If you had to compute coordinates yourself, show the arithmetic."""


def is_draft(probe: Probe) -> bool:
    """Draft-probes draw from a description and get the no-calculator rule
    and the T1 report; everything else finds and annotates."""
    return "draft" in probe.tags


#: the prompt levels a probe can be posed at (as ``tasks.prompts.LEVELS``): its own brief
#: (``Probe.prompt``, which states the standards it is graded on) and the vague one
LEVELS = ("explicit", "vague")


def prompt_at(probe: Probe, level: str = "explicit") -> str:
    """The probe's task at prompt ``level``: ``prompt``, or ``vague`` at the vague level."""
    if level not in LEVELS:
        raise ValueError(f"unknown prompt level {level!r}; levels: {', '.join(LEVELS)}")
    if level == "vague":
        if not probe.vague:
            raise ValueError(f"probe {probe.id} has no vague prompt")
        return probe.vague
    return probe.prompt


def task_text(probe: Probe, level: str = "explicit") -> str:
    """The user message: rules, the probe's prompt at ``level``, and the report asked for."""
    draft = is_draft(probe)
    return RULES.format(extra=NO_CALCULATOR if draft else "", task=prompt_at(probe, level),
                        report=T1_REPORT if draft else T2_REPORT)


__all__ = ["RULES", "NO_CALCULATOR", "T1_REPORT", "T2_REPORT", "LEVELS", "is_draft", "prompt_at",
           "task_text"]
