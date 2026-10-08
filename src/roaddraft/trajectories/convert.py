"""A trace as a conversation: the training format.

The MCP server's ``--trace`` writes one line per tool call with the full
result the agent was shown; the recorder writes the same lines for a scripted
solve. ``calls_from_trace`` reads either back, and ``conversation`` turns the
calls into one conversation in the tool-calling shape every chat template
understands: a system message (the MCP server's own instructions), a user
message (the rules and the task, as ``probes.prompting`` hands them to a
model), then an assistant turn per tool call and a tool turn carrying the
text the MCP server returned for it, and a closing report. The tool
definitions are kept once per set (``tools.json``) and named by digest, since
they are the same 78 for every run on one engine.

A conversation says whether it is ``faithful``: recorded with no direct read
of the document, so every number in it came through the tool surface. A
model's run is faithful by construction.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, List, Optional, Sequence

from roaddraft import __version__
from roaddraft.api.session import Session
from roaddraft.mcp.server import IMAGE_QUERIES, INSTRUCTIONS, result_text, tool_definitions
from roaddraft.probes.base import Probe, Result
from roaddraft.probes.prompting import task_text
from roaddraft.trajectories.record import Call, DirectRead

FORMAT = "roaddraft-trajectory/1"


class MissingResults(ValueError):
    """A trace line with no ``result``: written by a server older than the
    results-in-trace change. Such a trace converts by replay only."""

    def __init__(self, lines: Sequence[int]):
        self.lines = list(lines)
        shown = ", ".join(map(str, self.lines[:5])) + (", ..." if len(self.lines) > 5 else "")
        super().__init__(f"{len(self.lines)} trace line(s) carry no result (line {shown}); "
                         "replay the trace to recover them")


def has_results(lines: Iterable[dict]) -> bool:
    """Whether every line of a trace carries its result."""
    return all("result" in line for line in lines)


def calls_from_trace(lines: Iterable[dict]) -> List[Call]:
    """The calls a trace holds, results included. A line of kind ``extra``
    (``open_document``) is not a call on the document and is skipped."""
    calls, missing = [], []
    for n, line in enumerate(lines, 1):
        if line.get("kind") == "extra":
            continue
        if "result" not in line:
            missing.append(n)
            continue
        calls.append(Call(line["tool"], line.get("kind") or "query",
                          dict(line.get("arguments") or {}), line["result"],
                          said=line.get("said") or None))
    if missing:
        raise MissingResults(missing)
    return calls


def tool_list(session: Session) -> List[dict]:
    """The MCP tool definitions, vendor-neutral: name, description, input_schema."""
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["inputSchema"]} for t in tool_definitions(session)]


def tools_digest(tools: Sequence[dict]) -> str:
    canonical = json.dumps(tools, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _space(arguments: dict) -> str:
    return str(arguments.get("space") or arguments.get("sheet") or "model")


def _key_arguments(arguments: dict, limit: int = 4) -> str:
    parts = []
    for key, value in list(arguments.items())[:limit]:
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > 40:
            text = text[:37] + "..."
        parts.append(f"{key}={text}")
    return ", ".join(parts)


def templated_report(probe: Probe, calls: Sequence[Call]) -> str:
    """A report in the shape the task asks for, written from the calls rather
    than by a model: what was placed, the calls that mattered, what faulted.
    Marked ``templated`` on the conversation so a trainer can drop it."""
    placed = []
    for c in calls:
        if c.kind == "command" and c.ok and c.result.get("created"):
            ids = c.result["created"]
            ids = [i["id"] if isinstance(i, dict) else str(i) for i in ids]
            target = (c.arguments.get("target_entity") or c.arguments.get("target_anchor")
                      or c.arguments.get("alignment"))
            placed.append(f"{c.tool} in {_space(c.arguments)}: {', '.join(ids[:6])}"
                          + (f" ({len(ids)} entities)" if len(ids) > 6 else "")
                          + (f", on {target}" if target else ""))
    mattered = [f"{c.tool}({_key_arguments(c.arguments)})"
                for c in calls if c.kind == "command" and c.ok]
    faults = [f"{c.tool}: {(c.result.get('error') or {}).get('message', 'failed')}"
              for c in calls if not c.ok]
    lines = ["Done.",
             "1. " + ("; ".join(placed) if placed else "No entities were created."),
             "2. " + ("; ".join(mattered) if mattered else "No commands."),
             "3. " + ("Nothing failed." if not faults
                      else f"{len(faults)} call(s) faulted and were corrected: " + "; ".join(faults))]
    return "\n".join(lines)


def conversation(probe: Probe, calls: Sequence[Call], tools_sha256: str,
                 result: Optional[Result] = None, direct_reads: Iterable[DirectRead] = (),
                 report: Optional[str] = None, source: str = "solve",
                 task: Optional[str] = None) -> dict:
    """The run as messages, plus what is known about it. ``task`` replaces
    the user message with the text the model was actually handed (a run that
    kept its prompt); by default it is the probe's task as ``probes.prompting``
    words it."""
    direct = [str(d) for d in direct_reads]
    messages = [{"role": "system", "content": INSTRUCTIONS},
                {"role": "user", "content": task if task is not None else task_text(probe)}]
    for n, c in enumerate(calls, 1):
        cid = f"call_{n:04d}"
        messages.append({"role": "assistant", "content": c.said or "",
                         "tool_calls": [{"id": cid, "name": c.tool, "arguments": c.arguments}]})
        turn = {"role": "tool", "tool_call_id": cid, "name": c.tool,
                "content": result_text(c.result), "is_error": not c.ok}
        if c.ok and c.tool in IMAGE_QUERIES and c.result.get("path"):
            turn["image"] = c.result["path"]
        messages.append(turn)
    messages.append({"role": "assistant",
                     "content": report if report is not None else templated_report(probe, calls)})
    return {
        "format": FORMAT,
        "probe": probe.id,
        "prompt": probe.prompt,
        "tags": list(probe.tags),
        "start": probe.start,
        "source": source,
        "roaddraft": __version__,
        "tools_sha256": tools_sha256,
        "faithful": not direct,
        "direct_reads": direct,
        "task": "kept" if task is not None else "probe",
        "report": "given" if report is not None else "templated",
        "outcome": ({"passed": result.passed, "detail": result.detail} if result else None),
        "counts": {"calls": len(calls),
                   "queries": sum(c.kind == "query" for c in calls),
                   "commands": sum(c.kind == "command" for c in calls),
                   "faults": sum(not c.ok for c in calls)},
        "messages": messages,
    }


__all__ = ["FORMAT", "MissingResults", "has_results", "calls_from_trace", "tool_list",
           "tools_digest", "templated_report", "conversation"]
