"""The episode loop (eval plan section 4.1).

    reset    a Session on the task's starting document, in a folder of its
             own with the task's files beside it
    observe  the task text, the tool definitions, a state summary, the budget
    loop     agent -> tool calls -> executed in order on the session, through
             the whitelist, each one a step against the budgets -> results
             (the bus result JSON verbatim, faults as is_error results
             carrying the teaching error) -> the agent
    submit   or a budget trips (termination = "budget"), or the agent refuses
             or raises (refusal, error)
    verify   the document against the task's truth at the prompt level;
             the audit over the bus journal
    record   the trajectory: header, turns, journal, verify, audit, end

The agent sees every tool under its own name: no episode renames them
(Robert, 2026-10-30: the eval tests readiness for RoadDraft itself), so
``dialect`` is always ``neutral``, a field kept for the run ids and files
it names.  In the vision mode a render's PNG goes to the agent
as an image beside the results and never into the trajectory.

The episode folder is a fresh temporary folder: the task's files, the
document's home (a relative reference path resolves there) and the renders.
Every file a tool reads or writes -- a reference attached or loaded, a
render -- must resolve, links followed, inside it (document/confine.py), so
the reference solutions, other tasks' files and the trajectories that carry
the truth are out of reach; the truth itself is never written there.  The
agent is shown the folder's paths relative to it, never where it is.

One task type lets the agent work in a second document (2026-11-13: a
revision made in the base drawing a sheet file references; its scope opens
``open_document``, ``eval.tools.BASE_COMMANDS``).  The episode keeps the
session on the document it handed over, which is the one graded, and opens
the other beside it: ``open_document`` reaches only the handed document, by
its own name, and the files the task ships, inside the folder.  While another
document is open every tool runs on it, and each command that changes it is
written to its file, so the sheet file reads it back with
``reload_references``.  ``submit`` while another document is open is refused
with the way back, since nothing of that document is the answer.  At the end
the handed document is graded as a reader opening it would find it: its
references read from the files as they then stand.  What was done to the
other document is kept in the journal block (``opened``), so the block still
rebuilds the episode.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from roaddraft.api.session import Session
from roaddraft.document import confine
from roaddraft.document.fileformat import INTERCHANGE_EXT, write_document
from roaddraft.eval import prices
from roaddraft.eval.agents import Agent, AgentRefusal, Submit, ToolCall
from roaddraft.eval.budget import Budgets, BudgetState
from roaddraft.eval.prompts import SystemExtra
from roaddraft.eval.providers.base import LimitReached
from roaddraft.eval.tools import (
    DIALECTS, DOCUMENT_TOOLS, HARNESS_DEFINITIONS, HARNESS_TOOLS, MODES, RENDER_QUERIES,
    allowed_names, repair_params, shape_params, tool_definitions,
)
from roaddraft.eval.trajectory import TrajectoryWriter, episode_path
from roaddraft.tasks.brief import Task
from roaddraft.tasks.prompts import LEVELS, task_text
from roaddraft.tasks.reference import session_for_task
from roaddraft.verify import VERIFIER_VERSION, verify
from roaddraft.verify.audit import audit_journal
from roaddraft.verify.report import VerifyReport

HARNESS_VERSION = "e3-v3"  # (2026-11-03) + faults counted by turn, a one-item list read as its value, 45-min clock
# 2026-11-04: the openai-compatible runner gives a silent socket read up at READ_TIMEOUT (300 s) and treats it as a
# stall (reload once, ask again); a robustness fix of the stream, no rule of the harness changed, so e3-v3 stands.
#                  e3-v2     (2026-10-18) + file access held to the episode folder
#                  e3-v1     (2026-10-14) + LLM agents, dialect skins, vision images, cost
#: bus error types that count as invalid calls (a fault of the call, not of the drawing)
INVALID = ("invalid_params", "unknown_command")
#: a tool result longer than this (as JSON) is cut, with a hint to filter
RESULT_CAP = 30000
#: ``get_document_state`` summary keys the per-turn state keeps
STATE_KEYS = ("meta", "model", "sheets", "layers", "counts", "references", "design")
#: the error type of a ``submit`` called while another document than the handed one is open:
#: the call is answered with the way back and the episode goes on
WRONG_DOCUMENT = "wrong_document"


@dataclass(frozen=True)
class EpisodeConfig:
    level: str = "explicit"
    mode: str = "single"
    dialect: str = "neutral"
    budgets: Budgets = Budgets()
    sample: int = 0
    run_id: str = ""
    result_cap: int = RESULT_CAP
    #: a file appended to the model's system prompt (``--system-extra``), or None
    system_extra: Optional[SystemExtra] = None

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"unknown prompt level {self.level!r}; levels: {', '.join(LEVELS)}")
        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode!r}; modes: {', '.join(MODES)}")
        if self.dialect not in DIALECTS:
            raise ValueError(f"unknown dialect {self.dialect!r}; dialects: {', '.join(DIALECTS)}")

    @property
    def mode_budgets(self) -> Budgets:
        return self.budgets.for_mode(self.mode)


@dataclass
class EpisodeResult:
    task_id: str
    agent: str
    termination: str                 # submit | budget | refusal | error
    report: VerifyReport
    steps: int
    run_check_uses: int
    faults: int
    usage_total: Dict[str, int]
    elapsed_ms: int
    path: Optional[str] = None
    budget_tripped: Optional[str] = None
    error: Optional[str] = None
    turns: int = 0
    invalid_calls: int = 0
    cost_usd: Optional[float] = None
    implicit_submit: bool = False
    repaired_calls: int = 0          # calls whose one-item list was read as its value

    @property
    def effective_score(self) -> float:
        return self.report.effective_score

    def summary(self) -> dict:
        return {"task_id": self.task_id, "agent": self.agent, "termination": self.termination,
                "budget_tripped": self.budget_tripped, "effective_score": self.effective_score,
                "rubric_score": self.report.rubric_score, "hard_failed": self.report.hard_failed,
                "steps": self.steps, "turns": self.turns, "faults": self.faults,
                "invalid_calls": self.invalid_calls, "repaired_calls": self.repaired_calls,
                "run_check_uses": self.run_check_uses,
                "usage_total": self.usage_total, "cost_usd": self.cost_usd,
                "implicit_submit": self.implicit_submit, "elapsed_ms": self.elapsed_ms,
                "path": self.path, "error": self.error}


def _error(name: str, etype: str, message: str, hint: Optional[str] = None) -> dict:
    err = {"type": etype, "message": message}
    if hint:
        err["hint"] = hint
    return {"ok": False, "name": name, "error": err, "warnings": []}


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(brief_text: str, system_extra: Optional[SystemExtra] = None) -> str:
    """The header's ``prompt_hash``: the digest of the task text, as every run
    has recorded it; with a system extra (``--system-extra``), the digest of
    the task text and the extra's text together, so an episode told the
    extra never shares a prompt hash with its twin that was not."""
    if system_extra is None:
        return _hash(brief_text)
    return _hash(json.dumps({"brief": brief_text, "system_extra": system_extra.text},
                            sort_keys=True, ensure_ascii=False))


def prompt_fields(brief_text: str, system_extra: Optional[SystemExtra] = None) -> dict:
    """The header's prompt fields: ``prompt_hash``, and with a system extra,
    ``system_extra`` naming its file and digest."""
    fields = {"prompt_hash": prompt_hash(brief_text, system_extra)}
    if system_extra is not None:
        fields["system_extra"] = system_extra.record()
    return fields


def begin_context(episode, system: Optional[str] = None) -> dict:
    """What an episode hands its agent's ``begin``: the mode, level, dialect,
    budgets, scope and file, the system prompt when the task has its own (a
    probe), and the system extra's text when the run has one."""
    context = {"mode": episode.config.mode, "level": episode.config.level,
               "dialect": episode.config.dialect,
               "budgets": episode.budgets, "scope": episode.scope, "episode_path": episode.path}
    if system is not None:
        context["system"] = system
    if episode.config.system_extra is not None:
        context["system_extra"] = episode.config.system_extra.text
    return context


def _harness_failure(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


@dataclass
class UnscoredReport:
    """What an episode gets when scoring itself failed (2026-10-28): no credit, no hard fail, the failure in its
    place. The episode ends as ``error`` and the report leaves it out, as it does every errored episode."""
    error: str
    rubric_score: float = 0.0
    hard_failed: bool = False

    @property
    def effective_score(self) -> float:
        return 0.0

    def to_dict(self) -> dict:
        return {"unscored": True, "error": self.error}


class Episode:
    """One agent on one task under one configuration."""

    def __init__(self, task: Task, agent: Agent, config: EpisodeConfig = EpisodeConfig(),
                 out_root=None, pins: Optional[dict] = None):
        self.task = task
        self.agent = agent
        self.config = config
        self.budgets = config.mode_budgets
        self.out_root = out_root
        self.pins = pins
        self.session: Optional[Session] = None
        #: another document of the task, open in place of the one handed over (``open_document``):
        #: its session and its file name; None while the handed document is the open one
        self.other: Optional[Session] = None
        self.other_name: Optional[str] = None
        #: what was done to other documents, in order, for the journal block: the file, how
        #: many commands the handed document had taken when it was opened, its own commands
        self.opened: List[dict] = []
        #: the copies of other documents the handed one had read before they were changed
        self._outdated: List[tuple] = []
        #: the episode folder every tool's file access is held to (``reset``)
        self.root: Optional[confine.Root] = None
        self.state = BudgetState()
        self.scope = list(task.truth.scope)
        self.allowed = allowed_names(config.mode, self.scope)
        self.brief_text = task_text(task.brief, config.level)
        self.tools: List[dict] = []
        self.turns: List[dict] = []
        self.termination: Optional[str] = None
        self.budget_tripped: Optional[str] = None
        self.error: Optional[str] = None
        self.submit_note: str = ""
        self.implicit_submit = False
        self.invalid_calls = 0
        self.repaired_calls = 0
        self.cost_usd: Optional[float] = None
        self._turn_images: List[Optional[list]] = []

    # ------------------------------------------------------------ pieces

    @property
    def path(self):
        if self.out_root is None:
            return None
        return episode_path(self.out_root, self.task.task_id, self.agent.name, self.config.dialect,
                            self.config.mode, self.config.level, self.config.sample)

    def reset(self) -> dict:
        self.session = self._open_session()
        self.tools = tool_definitions(self.session.manifest(), self.config.mode, self.scope)
        self._schemas = {d["name"]: d["input_schema"] for d in self.tools}
        self.state = BudgetState()
        self.agent.reset(self.task, self.config.level, self.config.mode)
        self.agent.begin(begin_context(self))
        return {"turn": 0, "brief": self.brief_text, "tools": self.tools,
                "state": self.state_summary(), "budget": self.state.remaining(self.budgets),
                "mode": self.config.mode, "dialect": self.config.dialect}

    def _open_session(self) -> Session:
        """A session on the task's starting document in a fresh episode
        folder: the task's files are written there, the document's home is
        there, a render goes there by default and a relative render path
        lands there.  The folder lives as long as the session."""
        workdir = tempfile.TemporaryDirectory(prefix="roaddraft-episode-")
        folder = Path(workdir.name)
        session = session_for_task(self.task, out_dir=folder)
        session._task_dir = workdir
        session.doc._path = folder / f"{self.task.task_id}{INTERCHANGE_EXT}"
        session.base_dir = folder
        session.out_dir = folder / "renders"
        self.root = confine.Root(folder)
        return session

    def _shown(self, value):
        """``value`` as the agent sees it: every absolute path inside the
        episode folder written relative to the folder, which is where a
        relative path the agent gives resolves."""
        return value if self.root is None else self.root.show(value, base=self.root.real)

    @property
    def desk(self) -> Session:
        """The session the tools run on: the handed document's, unless another
        document of the task is open in its place."""
        return self.other if self.other is not None else self.session

    def state_summary(self) -> dict:
        with confine.held(self.root):
            result = self.desk.query("get_document_state", {"detail": "summary"})
        summary = self._shown(result.get("summary") or {})
        return {k: summary[k] for k in STATE_KEYS if k in summary}

    def header(self) -> dict:
        brief = self.task.brief
        pins = self.pins or {}
        return {"type": "header", "run_id": self.config.run_id, "task_id": self.task.task_id,
                "task_type": brief.task_type, "sheets": brief.sheets, "seed": brief.seed,
                "spec_version": brief.spec_version, "spec_hash": brief.spec_hash,
                "generator_version": brief.generator_version,
                "verifier_version": VERIFIER_VERSION, "harness_version": HARNESS_VERSION,
                **prompt_fields(self.brief_text, self.config.system_extra),
                "git_commit": pins.get("commit"),
                "dirty": pins.get("dirty"), "tools_sha256": _hash(json.dumps(self.tools, sort_keys=True)),
                **self.agent.describe(), "agent": self.agent.name,
                "dialect": self.config.dialect, "mode": self.config.mode,
                "level": self.config.level, "sample": self.config.sample,
                "scope": self.scope, "budgets": self.budgets.to_dict(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    # ------------------------------------------------------------ execute

    harness_error: Optional[str] = None

    def execute(self, call: ToolCall) -> dict:
        """``_execute`` with the harness's own failure caught (2026-10-28: a TypeError inside a tool call on
        Gemma 4 12B's D1-001041 escaped the loop and the episode ended with no end record, as a d1-variance cell
        had on Oct 25). The call's result names the failure, the traceback goes to stderr (the run log), and the
        loop ends the episode as ``error``: the harness's outcome, not the model's, so no step is counted and the
        report leaves the episode out, for ``clear-errors`` to run again."""
        try:
            return self._execute(call)
        except Exception as exc:
            self.harness_error = _harness_failure(exc)
            print(f"harness error in {call.name}: {self.harness_error}\n{traceback.format_exc()}",
                  file=sys.stderr, flush=True)
            self._turn_images.append(None)
            return _error(call.name, "harness_error",
                          f"the harness failed on this call ({self.harness_error}); the episode ends")

    def _execute(self, call: ToolCall) -> dict:
        """One tool call on the session: a step, whatever it returns.  The
        session runs it with file access held to the episode folder, and its
        result is shown with the folder's paths relative.  A render's image in
        the vision mode, read from disk by the session, is kept for the agent
        in ``_turn_images``."""
        name, params = call.name, call.params or {}
        images = None
        if name not in self.allowed:
            hint = ("tools in this episode: "
                    + ", ".join(sorted(self.allowed)))
            result = _error(call.name, "unknown_command",
                            f"{call.name!r} is not a tool of this episode", hint)
        elif name in HARNESS_TOOLS:
            result = self._shown(self._harness_tool(name, params))
        elif name in DOCUMENT_TOOLS:
            result = self._shown(self._open_document(params))
        else:
            shaped, notes = shape_params(name, params)
            shaped, repairs = repair_params(shaped, self._schemas.get(name))
            if name in RENDER_QUERIES and self.config.mode == "vision":
                shaped = dict(shaped, include_base64=True)
            desk = self.desk
            with confine.held(self.root):
                if name in RENDER_QUERIES or name in self.session_queries():
                    result = desk.query(name, shaped)
                else:
                    result = desk.execute(name, shaped)
                    if desk is self.other and result.get("ok"):
                        self._save_other()
            result = self._shown(result)
            if (notes or repairs) and isinstance(result, dict):
                result = dict(result)
                result["warnings"] = list(result.get("warnings") or []) + notes + repairs
            result, images = self._shape_result(name, result)
            if repairs:   # on the record whole, past the result cap: the report counts it
                result = dict(result, repaired=repairs)
                self.repaired_calls += 1
        ok = bool(result.get("ok"))
        if not ok and (result.get("error") or {}).get("type") in INVALID:
            self.invalid_calls += 1
        self.state.note_call(ok)
        self._turn_images.append(images)
        return result

    _query_names: Optional[set] = None

    def session_queries(self) -> set:
        if self._query_names is None:
            self._query_names = {q["name"] for q in self.session.manifest()["queries"]}
        return self._query_names

    # ------------------------------------------------- another document of the task

    @property
    def handed_name(self) -> str:
        """The file name of the document the task hands over."""
        return Path(self.session.doc._path).name

    def _documents(self) -> str:
        """The task's documents, by name, for an ``open_document`` that missed."""
        def tag(name: str, handed: bool) -> str:
            notes = (["handed to you"] if handed else []) + (
                ["open now"] if name == (self.other_name or self.handed_name) else [])
            return name + (f" ({', '.join(notes)})" if notes else "")
        names = [tag(self.handed_name, True)] + [tag(n, False) for n in sorted(self.task.files)]
        return "the documents of this task: " + ", ".join(names)

    def _open_document(self, params: dict) -> dict:
        """``open_document``: switch the tools to another document of the task,
        or back to the one handed over.  Only those can be opened: the handed
        document by its own name, and the files the task ships, each inside the
        episode folder (a path that leads out of it is refused as every other
        tool refuses it)."""
        name = "open_document"
        path = params.get("path")
        if not isinstance(path, str) or not path.strip() or set(params) - {"path"}:
            spec = HARNESS_DEFINITIONS[name]["input_schema"]
            return {"ok": False, "name": name, "warnings": [], "error": {
                "type": "invalid_params", "message": "open_document takes the path of a document "
                "file, and nothing else", "valid_params_schema": spec,
                "example": {"path": self.handed_name}}}
        folder = Path(self.root.given)
        try:
            target = Path(path).expanduser()
        except RuntimeError:  # '~nobody/x': no such home; a path a model typed, not a fault
            return _error(name, "command_failed", f"no such document: {path}", self._documents())
        target = target if target.is_absolute() else folder / target
        if not self.root.contains(target):
            refused = confine.OutsideRoot(path)
            return _error(name, "command_failed", f"cannot open {path}: {refused}", refused.hint)
        real = os.path.realpath(target)
        handed = os.path.realpath(self.session.doc._path)
        shipped = {os.path.realpath(folder / n): n for n in self.task.files}
        if real != handed and real not in shipped:
            return _error(name, "command_failed", f"no such document: {path}", self._documents())
        warnings: List[str] = []
        if real == handed:
            self._leave_other()
            stale = [ref.name for ref in self.session.doc.references.values()
                     if any(self.session.doc._ref_cache.get(ref.id) is hit
                            for hit in self._outdated)]
            warnings += [f"{ref} has changed since this file read it; reload_references reads "
                         f"it again as it now stands" for ref in stale]
        elif shipped[real] != self.other_name:
            self._leave_other()
            other = Session.load(folder / shipped[real], out_dir=self.session.out_dir)
            other.base_dir = self.session.base_dir
            self.other, self.other_name = other, shipped[real]
            self.opened.append({"document": self.other_name, "at": len(self.session.bus.journal),
                                "entries": other.bus.journal})
        with confine.held(self.root):
            state = self.desk.query("get_document_state", {})
        return {"ok": True, "name": name, "opened": self.other_name or self.handed_name,
                "graded": self.handed_name, "state": state, "warnings": warnings}

    def _leave_other(self) -> None:
        """Put the other document away: its file already holds every change."""
        if self.other is not None and not self.other.bus.journal:
            self.opened.pop()  # opened and left as it was: nothing to keep
        self.other, self.other_name = None, None

    def _save_other(self) -> None:
        """Write the other document to its file after a command changed it, as
        the MCP server's autosave does, and note which copies of it the handed
        document read before the change: those are out of date until it reloads."""
        path = write_document(self.other.doc._path, self.other.doc.to_dict())
        real = os.path.realpath(path)
        for hit in self.session.doc._ref_cache.values():
            if os.path.realpath(hit[0]) == real and not any(hit is seen for seen in self._outdated):
                self._outdated.append(hit)

    def _harness_tool(self, name: str, params: dict) -> dict:
        if name == "submit" and self.other is not None:
            # nothing of the other document is the answer: say which one is, and the way back
            return _error(name, WRONG_DOCUMENT,
                          f"{self.other_name} is the open document, and the task grades "
                          f"{self.handed_name}, the file you were handed",
                          f"open_document {self.handed_name} first; reload_references there reads "
                          f"{self.other_name} as it now stands; finish that file, then submit")
        if name == "get_task_brief":
            return {"ok": True, "name": name, "brief": self.brief_text}
        if name == "run_check":
            if self.budgets.run_checks <= 0:
                return _error(name, "not_available", "run_check is not available in single mode")
            if self.state.run_check_uses >= self.budgets.run_checks:
                return _error(name, "budget_exhausted",
                              f"run_check has been used {self.state.run_check_uses} times, its budget")
            self.state.note_check()
            # graded as submit would grade it: where another document was changed, the handed
            # one's references read from the files as they stand (and its own copies kept)
            doc = self.session.doc
            changed = any(visit["entries"] for visit in self.opened)
            copies = dict(doc._ref_cache) if changed else {}
            if changed:
                doc._ref_cache.clear()
            try:
                report = verify(doc, self.task.truth, prompt_level=self.config.level)
            finally:
                if changed:
                    doc._ref_cache.clear()
                    doc._ref_cache.update(copies)
            view = report.agent_view()
            return {"ok": True, "name": name,
                    "budget_remaining": self.budgets.run_checks - self.state.run_check_uses, **view}
        if name == "submit":
            self.submit_note = str(params.get("note") or "")
            return {"ok": True, "name": name, "message": "submitted"}
        return _error(name, "unknown_command", f"unknown harness tool {name!r}")

    def _shape_result(self, name: str, result: dict) -> Tuple[dict, Optional[list]]:
        """The result as the agent and the trajectory see it, and the images
        that go to the agent alone (vision mode)."""
        if not isinstance(result, dict):
            return {"ok": True, "name": name, "result": result}, None
        images = None
        if name in RENDER_QUERIES and "base64" in result:
            data = result["base64"]
            result = {k: v for k, v in result.items() if k != "base64"}
            if self.config.mode == "vision":
                images = [("image/png", data)]
                result["note"] = "the image is returned with this result"
            else:
                result["note"] = "the image is on disk at 'path'; it is not returned inline in this mode"
        text = json.dumps(result, ensure_ascii=False)
        if len(text) > self.config.result_cap:
            return {"ok": bool(result.get("ok")), "name": name, "truncated": True,
                    "text": text[:self.config.result_cap],
                    "hint": (f"the result was {len(text):,} characters and was cut at "
                             f"{self.config.result_cap:,}; ask for less (a sheet, a layer, "
                             "find_entities with a filter, get_entity by id)")}, images
        return result, images

    # ----------------------------------------------------------------- run

    def run(self) -> EpisodeResult:
        started = time.monotonic()
        observation = self.reset()
        writer = TrajectoryWriter(self.path) if self.path else None
        if writer:
            writer.write(self.header())
        usage_total: Dict[str, int] = {}
        model = self.agent.describe().get("model") or self.agent.name
        n = 0

        def take_usage() -> Dict[str, int]:
            usage = self.agent.usage() or {}
            self.state.note_usage(usage)
            for k, v in usage.items():
                usage_total[k] = usage_total.get(k, 0) + int(v or 0)
            cost = prices.cost_usd(model, usage) if usage else None
            if cost is not None:
                self.cost_usd = round((self.cost_usd or 0.0) + cost, 6)
            return usage

        def record(turn: dict) -> None:
            self.turns.append(turn)
            if writer:
                writer.write(turn)

        try:
            while self.termination is None:
                tripped = self.state.tripped(self.budgets)
                if tripped:
                    self.termination, self.budget_tripped = "budget", tripped
                    break
                t0 = time.monotonic()
                try:
                    action = self.agent.act(observation)
                except (AgentRefusal, LimitReached) as stop:
                    # the model's outcome: its last turn is kept, and what it cost
                    n += 1
                    if isinstance(stop, AgentRefusal):
                        self.termination, self.error = "refusal", str(stop) or "refused"
                    else:
                        self.termination, self.budget_tripped = "budget", stop.limit
                        self.error = str(stop)
                    usage = take_usage()
                    record({"type": "turn", "n": n,
                            "assistant": {"text": "", "tool_calls": [], "submit": False,
                                          **self.agent.turn_record()},
                            "results": [], "usage": usage,
                            "elapsed_ms": int(round((time.monotonic() - t0) * 1000))})
                    break
                except Exception as exc:  # the agent's failure is the episode's outcome
                    self.termination = "error"
                    self.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                    take_usage()
                    break
                n += 1
                usage = take_usage()
                calls: List[ToolCall]
                if isinstance(action, Submit):
                    calls, submitted = [], True
                    self.submit_note = action.note
                    self.implicit_submit = action.implicit
                else:
                    calls = list(action)
                    submitted = False
                results = []
                self._turn_images = []
                for call in calls:
                    if call.name == "submit":
                        results.append(self.execute(call))
                        if (results[-1].get("error") or {}).get("type") == WRONG_DOCUMENT:
                            continue  # another document is open: answered, and the episode goes on
                        submitted = True
                        break
                    tripped = self.state.tripped(self.budgets)
                    if tripped:
                        results.append(_error(call.name, "budget_exhausted",
                                              f"the {tripped} budget is spent; the episode ends"))
                        self._turn_images.append(None)
                        break
                    results.append(self.execute(call))
                    if self.harness_error:
                        break
                self.state.note_turn(bool(r.get("ok")) for r in results)
                assistant = {"text": "", "tool_calls": [c.to_dict() for c in calls],
                             "submit": submitted, **self.agent.turn_record()}
                if submitted and self.submit_note and not assistant.get("text"):
                    assistant["text"] = self.submit_note
                if self.implicit_submit:
                    assistant["implicit_submit"] = True
                record({"type": "turn", "n": n, "assistant": assistant, "results": results,
                        "usage": usage, "elapsed_ms": int(round((time.monotonic() - t0) * 1000))})
                if self.harness_error:
                    self.termination, self.error = "error", f"harness: {self.harness_error}"
                    break
                if submitted:
                    self.termination = "submit"
                    break
                observation = {"turn": n, "results": results, "state": self.state_summary(),
                               "budget": self.state.remaining(self.budgets)}
                if any(self._turn_images):
                    observation["images"] = list(self._turn_images)
        finally:
            self.agent.close()
        try:
            report, records = self.finish()
        except Exception as exc:  # the verifier or the audit failed: the episode still ends on record (2026-10-28)
            text = _harness_failure(exc)
            print(f"harness error in scoring: {text}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
            self.termination, self.error = "error", f"harness: scoring: {text}"
            report, records = UnscoredReport(text), [{"type": "harness_error", "stage": "scoring", "error": text}]
        elapsed_ms = int(round((time.monotonic() - started) * 1000))
        if writer:
            for rec in records:
                writer.write(rec)
            writer.write({"type": "end", "termination": self.termination,
                          "budget_tripped": self.budget_tripped, "error": self.error,
                          "steps": self.state.steps, "turns": n, "tool_calls": self.state.steps,
                          "invalid_calls": self.invalid_calls,
                          "repaired_calls": self.repaired_calls,
                          "run_check_uses": self.state.run_check_uses,
                          "faults": self.state.faults, "usage_total": usage_total,
                          "cost_usd": self.cost_usd,
                          "prices_checked": prices.load()["checked"] if self.cost_usd is not None else None,
                          "implicit_submit": self.implicit_submit, "elapsed_ms": elapsed_ms,
                          "effective_score": report.effective_score,
                          "rubric_score": report.rubric_score,
                          "hard_failed": report.hard_failed})
            writer.close()
        return EpisodeResult(task_id=self.task.task_id, agent=self.agent.name,
                             termination=self.termination, report=report,
                             steps=self.state.steps, run_check_uses=self.state.run_check_uses,
                             faults=self.state.faults, usage_total=usage_total,
                             elapsed_ms=elapsed_ms, path=str(self.path) if self.path else None,
                             budget_tripped=self.budget_tripped, error=self.error, turns=n,
                             invalid_calls=self.invalid_calls, repaired_calls=self.repaired_calls,
                             cost_usd=self.cost_usd,
                             implicit_submit=self.implicit_submit)

    def finish(self) -> Tuple[Any, List[dict]]:
        """Grade the episode: the report (``effective_score``, ``rubric_score``,
        ``hard_failed``, ``to_dict``) and the records written before the end
        record -- the journal that re-scores it, the verify report, the audit.
        A probe task (``eval/probe_tasks.py``) grades with its own check.

        What is graded is the document handed over, whichever is open at the
        end.  Where the episode changed another document, the handed one is
        read as a reader opening it would find it, its references from the
        files as they now stand, and the journal block keeps what was done to
        the other (``opened``), which ``trajectory.replay_journal`` replays."""
        opened = [{**visit, "entries": list(visit["entries"])} for visit in self.opened
                  if visit["entries"]]
        if opened:
            self.session.doc._ref_cache.clear()
        report = verify(self.session.doc, self.task.truth, journal=self.session.bus.journal,
                        prompt_level=self.config.level)
        audit = audit_journal(self.session.bus.journal, self.session.doc)
        journal = {"type": "journal", "baseline": self.task.baseline,
                   "entries": list(self.session.bus.journal),
                   "truth": self.task.truth.to_dict(),
                   "document_name": f"{self.task.task_id}.rdoc.json"}
        if opened:
            journal["opened"] = opened
        if self.task.files:
            journal["files"] = self.task.files
        return report, [journal, {"type": "verify", **report.to_dict()}, {"type": "audit", **audit}]


def run_episode(task: Task, agent: Agent, config: EpisodeConfig = EpisodeConfig(),
                out_root=None, pins: Optional[dict] = None) -> EpisodeResult:
    """Run one episode; the trajectory is written under ``out_root`` when given."""
    return Episode(task, agent, config, out_root=out_root, pins=pins).run()


__all__ = ["HARNESS_VERSION", "RESULT_CAP", "EpisodeConfig", "EpisodeResult", "Episode",
           "run_episode"]
