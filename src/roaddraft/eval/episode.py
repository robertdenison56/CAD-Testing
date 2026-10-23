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

The dialect is the harness's: the agent is shown the skin's tool names and
task text, and every call is resolved back to the canonical command before
the whitelist sees it.  In the vision mode a render's PNG goes to the agent
as an image beside the results and never into the trajectory.

The episode folder is a fresh temporary folder: the task's files, the
document's home (a relative reference path resolves there) and the renders.
Every file a tool reads or writes -- a reference attached or loaded, a
render -- must resolve, links followed, inside it (document/confine.py), so
the reference solutions, other tasks' files and the trajectories that carry
the truth are out of reach; the truth itself is never written there.  The
agent is shown the folder's paths relative to it, never where it is.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from roaddraft.api.session import Session
from roaddraft.document import confine
from roaddraft.document.fileformat import INTERCHANGE_EXT
from roaddraft.eval import dialects, prices
from roaddraft.eval.agents import Agent, AgentRefusal, Submit, ToolCall
from roaddraft.eval.budget import Budgets, BudgetState
from roaddraft.eval.providers.base import LimitReached
from roaddraft.eval.tools import (
    DIALECTS, HARNESS_TOOLS, MODES, RENDER_QUERIES, allowed_names, shape_params,
    tool_definitions,
)
from roaddraft.eval.trajectory import TrajectoryWriter, episode_path
from roaddraft.tasks.brief import Task
from roaddraft.tasks.prompts import LEVELS, task_text
from roaddraft.tasks.reference import session_for_task
from roaddraft.verify import VERIFIER_VERSION, verify
from roaddraft.verify.audit import audit_journal
from roaddraft.verify.report import VerifyReport

HARNESS_VERSION = "e3-v2"  # (2026-10-18) + file access held to the episode folder
#                  e3-v1     (2026-10-14) + LLM agents, dialect skins, vision images, cost
#: bus error types that count as invalid calls (a fault of the call, not of the drawing)
INVALID = ("invalid_params", "unknown_command")
#: a tool result longer than this (as JSON) is cut, with a hint to filter
RESULT_CAP = 30000
#: ``get_document_state`` summary keys the per-turn state keeps
STATE_KEYS = ("meta", "model", "sheets", "layers", "counts", "references", "design")


@dataclass(frozen=True)
class EpisodeConfig:
    level: str = "explicit"
    mode: str = "single"
    dialect: str = "neutral"
    budgets: Budgets = Budgets()
    sample: int = 0
    run_id: str = ""
    result_cap: int = RESULT_CAP

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

    @property
    def effective_score(self) -> float:
        return self.report.effective_score

    def summary(self) -> dict:
        return {"task_id": self.task_id, "agent": self.agent, "termination": self.termination,
                "budget_tripped": self.budget_tripped, "effective_score": self.effective_score,
                "rubric_score": self.report.rubric_score, "hard_failed": self.report.hard_failed,
                "steps": self.steps, "turns": self.turns, "faults": self.faults,
                "invalid_calls": self.invalid_calls, "run_check_uses": self.run_check_uses,
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
        #: the episode folder every tool's file access is held to (``reset``)
        self.root: Optional[confine.Root] = None
        self.state = BudgetState()
        self.scope = list(task.truth.scope)
        self.allowed = allowed_names(config.mode, self.scope)
        self.dialect = dialects.get(config.dialect, self.allowed)
        self.brief_text = self.dialect.text(task_text(task.brief, config.level))
        self.tools: List[dict] = []
        self.turns: List[dict] = []
        self.termination: Optional[str] = None
        self.budget_tripped: Optional[str] = None
        self.error: Optional[str] = None
        self.submit_note: str = ""
        self.implicit_submit = False
        self.invalid_calls = 0
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
        self.tools = self.dialect.tools(
            tool_definitions(self.session.manifest(), self.config.mode, self.scope))
        self.state = BudgetState()
        self.agent.reset(self.task, self.config.level, self.config.mode)
        self.agent.begin({"mode": self.config.mode, "level": self.config.level,
                          "dialect": self.config.dialect, "skin": self.dialect,
                          "budgets": self.budgets, "scope": self.scope})
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

    def state_summary(self) -> dict:
        with confine.held(self.root):
            result = self.session.query("get_document_state", {"detail": "summary"})
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
                "prompt_hash": _hash(self.brief_text), "git_commit": pins.get("commit"),
                "dirty": pins.get("dirty"), "tools_sha256": _hash(json.dumps(self.tools, sort_keys=True)),
                **self.agent.describe(), "agent": self.agent.name,
                "dialect": self.config.dialect, "mode": self.config.mode,
                "level": self.config.level, "sample": self.config.sample,
                "scope": self.scope, "budgets": self.budgets.to_dict(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    # ------------------------------------------------------------ execute

    def execute(self, call: ToolCall) -> dict:
        """One tool call on the session: a step, whatever it returns.  The
        call's name is resolved through the dialect first; the session runs
        it with file access held to the episode folder, and its result is
        shown with the folder's paths relative.  A render's image in the
        vision mode, read from disk by the session, is kept for the agent in
        ``_turn_images``."""
        name, params = self.dialect.canonical(call.name), call.params or {}
        images = None
        if name not in self.allowed:
            hint = ("tools in this episode: "
                    + ", ".join(sorted(self.dialect.present(n) for n in self.allowed)))
            result = _error(call.name, "unknown_command",
                            f"{call.name!r} is not a tool of this episode", hint)
        elif name in HARNESS_TOOLS:
            result = self._shown(self._harness_tool(name, params))
        else:
            shaped, notes = shape_params(name, params)
            if name in RENDER_QUERIES and self.config.mode == "vision":
                shaped = dict(shaped, include_base64=True)
            with confine.held(self.root):
                if name in RENDER_QUERIES or name in self.session_queries():
                    result = self.session.query(name, shaped)
                else:
                    result = self.session.execute(name, shaped)
            result = self._shown(result)
            if notes and isinstance(result, dict):
                result = dict(result)
                result["warnings"] = list(result.get("warnings") or []) + notes
            result, images = self._shape_result(name, result)
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

    def _harness_tool(self, name: str, params: dict) -> dict:
        if name == "get_task_brief":
            return {"ok": True, "name": name, "brief": self.brief_text}
        if name == "run_check":
            if self.budgets.run_checks <= 0:
                return _error(name, "not_available", "run_check is not available in single mode")
            if self.state.run_check_uses >= self.budgets.run_checks:
                return _error(name, "budget_exhausted",
                              f"run_check has been used {self.state.run_check_uses} times, its budget")
            self.state.note_check()
            report = verify(self.session.doc, self.task.truth, prompt_level=self.config.level)
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
                    if self.dialect.canonical(call.name) == "submit":
                        results.append(self.execute(call))
                        submitted = True
                        break
                    tripped = self.state.tripped(self.budgets)
                    if tripped:
                        results.append(_error(call.name, "budget_exhausted",
                                              f"the {tripped} budget is spent; the episode ends"))
                        self._turn_images.append(None)
                        break
                    results.append(self.execute(call))
                assistant = {"text": "", "tool_calls": [self._call_record(c) for c in calls],
                             "submit": submitted, **self.agent.turn_record()}
                if submitted and self.submit_note and not assistant.get("text"):
                    assistant["text"] = self.submit_note
                if self.implicit_submit:
                    assistant["implicit_submit"] = True
                record({"type": "turn", "n": n, "assistant": assistant, "results": results,
                        "usage": usage, "elapsed_ms": int(round((time.monotonic() - t0) * 1000))})
                if submitted:
                    self.termination = "submit"
                    break
                observation = {"turn": n, "results": results, "state": self.state_summary(),
                               "budget": self.state.remaining(self.budgets)}
                if any(self._turn_images):
                    observation["images"] = list(self._turn_images)
        finally:
            self.agent.close()
        report, records = self.finish()
        elapsed_ms = int(round((time.monotonic() - started) * 1000))
        if writer:
            for rec in records:
                writer.write(rec)
            writer.write({"type": "end", "termination": self.termination,
                          "budget_tripped": self.budget_tripped, "error": self.error,
                          "steps": self.state.steps, "turns": n, "tool_calls": self.state.steps,
                          "invalid_calls": self.invalid_calls,
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
                             invalid_calls=self.invalid_calls, cost_usd=self.cost_usd,
                             implicit_submit=self.implicit_submit)

    def finish(self) -> Tuple[Any, List[dict]]:
        """Grade the episode: the report (``effective_score``, ``rubric_score``,
        ``hard_failed``, ``to_dict``) and the records written before the end
        record -- the journal that re-scores it, the verify report, the audit.
        A probe task (``eval/probe_tasks.py``) grades with its own check."""
        report = verify(self.session.doc, self.task.truth, journal=self.session.bus.journal,
                        prompt_level=self.config.level)
        audit = audit_journal(self.session.bus.journal, self.session.doc)
        journal = {"type": "journal", "baseline": self.task.baseline,
                   "entries": list(self.session.bus.journal),
                   "truth": self.task.truth.to_dict(),
                   "document_name": f"{self.task.task_id}.rdoc.json"}
        if self.task.files:
            journal["files"] = self.task.files
        return report, [journal, {"type": "verify", **report.to_dict()}, {"type": "audit", **audit}]

    def _call_record(self, call: ToolCall) -> dict:
        d = call.to_dict()
        canonical = self.dialect.canonical(call.name)
        if canonical != call.name:
            d["tool"] = canonical
        return d


def run_episode(task: Task, agent: Agent, config: EpisodeConfig = EpisodeConfig(),
                out_root=None, pins: Optional[dict] = None) -> EpisodeResult:
    """Run one episode; the trajectory is written under ``out_root`` when given."""
    return Episode(task, agent, config, out_root=out_root, pins=pins).run()


__all__ = ["HARNESS_VERSION", "RESULT_CAP", "EpisodeConfig", "EpisodeResult", "Episode",
           "run_episode"]
