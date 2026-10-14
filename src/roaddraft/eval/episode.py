"""The episode loop (eval plan section 4.1).

    reset    a Session on the task's starting document (files beside it)
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
"""
from __future__ import annotations

import hashlib
import json
import time
import traceback
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from roaddraft.api.session import Session
from roaddraft.eval.agents import Agent, AgentRefusal, Submit, ToolCall
from roaddraft.eval.budget import Budgets, BudgetState
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

HARNESS_VERSION = "e2-v1"  # (2026-10-14) episode loop, four non-LLM agents, trajectories
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

    @property
    def effective_score(self) -> float:
        return self.report.effective_score

    def summary(self) -> dict:
        return {"task_id": self.task_id, "agent": self.agent, "termination": self.termination,
                "budget_tripped": self.budget_tripped, "effective_score": self.effective_score,
                "rubric_score": self.report.rubric_score, "hard_failed": self.report.hard_failed,
                "steps": self.steps, "turns": self.turns, "faults": self.faults,
                "run_check_uses": self.run_check_uses, "elapsed_ms": self.elapsed_ms,
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
        self.state = BudgetState()
        self.brief_text = task_text(task.brief, config.level)
        self.scope = list(task.truth.scope)
        self.allowed = allowed_names(config.mode, self.scope)
        self.tools: List[dict] = []
        self.turns: List[dict] = []
        self.termination: Optional[str] = None
        self.budget_tripped: Optional[str] = None
        self.error: Optional[str] = None
        self.submit_note: str = ""

    # ------------------------------------------------------------ pieces

    @property
    def path(self):
        if self.out_root is None:
            return None
        return episode_path(self.out_root, self.task.task_id, self.agent.name, self.config.dialect,
                            self.config.mode, self.config.level, self.config.sample)

    def reset(self) -> dict:
        self.session = session_for_task(self.task)
        self.tools = tool_definitions(self.session.manifest(), self.config.mode, self.scope)
        self.state = BudgetState()
        self.agent.reset(self.task, self.config.level, self.config.mode)
        return {"turn": 0, "brief": self.brief_text, "tools": self.tools,
                "state": self.state_summary(), "budget": self.state.remaining(self.budgets)}

    def state_summary(self) -> dict:
        result = self.session.query("get_document_state", {"detail": "summary"})
        summary = result.get("summary") or {}
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
        """One tool call on the session: a step, whatever it returns."""
        name, params = call.name, call.params or {}
        if name not in self.allowed:
            hint = ("tools in this episode: " + ", ".join(sorted(self.allowed)))
            result = _error(name, "unknown_command",
                            f"{name!r} is not a tool of this episode", hint)
        elif name in HARNESS_TOOLS:
            result = self._harness_tool(name, params)
        else:
            shaped, notes = shape_params(name, params)
            if name in RENDER_QUERIES or name in self.session_queries():
                result = self.session.query(name, shaped)
            else:
                result = self.session.execute(name, shaped)
            if notes and isinstance(result, dict):
                result = dict(result)
                result["warnings"] = list(result.get("warnings") or []) + notes
            result = self._shape_result(name, result)
        self.state.note_call(bool(result.get("ok")))
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

    def _shape_result(self, name: str, result: dict) -> dict:
        if not isinstance(result, dict):
            return {"ok": True, "name": name, "result": result}
        if name in RENDER_QUERIES and "base64" in result:
            result = {k: v for k, v in result.items() if k != "base64"}
            result["note"] = "the image is on disk at 'path'; it is not returned inline in this mode"
        text = json.dumps(result, ensure_ascii=False)
        if len(text) > self.config.result_cap:
            return {"ok": bool(result.get("ok")), "name": name, "truncated": True,
                    "text": text[:self.config.result_cap],
                    "hint": (f"the result was {len(text):,} characters and was cut at "
                             f"{self.config.result_cap:,}; ask for less (a sheet, a layer, "
                             "find_entities with a filter, get_entity by id)")}
        return result

    # ----------------------------------------------------------------- run

    def run(self) -> EpisodeResult:
        started = time.monotonic()
        observation = self.reset()
        writer = TrajectoryWriter(self.path) if self.path else None
        if writer:
            writer.write(self.header())
        usage_total: Dict[str, int] = {}
        n = 0
        while self.termination is None:
            tripped = self.state.tripped(self.budgets)
            if tripped:
                self.termination, self.budget_tripped = "budget", tripped
                break
            t0 = time.monotonic()
            try:
                action = self.agent.act(observation)
            except AgentRefusal as refusal:
                self.termination, self.error = "refusal", str(refusal) or "refused"
                break
            except Exception as exc:  # the agent's failure is the episode's outcome
                self.termination = "error"
                self.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                break
            n += 1
            usage = self.agent.usage() or {}
            self.state.note_usage(usage)
            for k, v in usage.items():
                usage_total[k] = usage_total.get(k, 0) + int(v or 0)
            calls: List[ToolCall]
            if isinstance(action, Submit):
                calls, submitted = [], True
                self.submit_note = action.note
            else:
                calls = list(action)
                submitted = False
            results = []
            for call in calls:
                if call.name == "submit":
                    results.append(self.execute(call))
                    submitted = True
                    break
                tripped = self.state.tripped(self.budgets)
                if tripped:
                    results.append(_error(call.name, "budget_exhausted",
                                          f"the {tripped} budget is spent; the episode ends"))
                    break
                results.append(self.execute(call))
            turn = {"type": "turn", "n": n,
                    "assistant": {"text": self.submit_note if submitted else "",
                                  "tool_calls": [c.to_dict() for c in calls],
                                  "submit": submitted},
                    "results": results, "usage": usage,
                    "elapsed_ms": int(round((time.monotonic() - t0) * 1000))}
            self.turns.append(turn)
            if writer:
                writer.write(turn)
            if submitted:
                self.termination = "submit"
                break
            observation = {"turn": n, "results": results, "state": self.state_summary(),
                           "budget": self.state.remaining(self.budgets)}
        report = verify(self.session.doc, self.task.truth, journal=self.session.bus.journal,
                        prompt_level=self.config.level)
        audit = audit_journal(self.session.bus.journal, self.session.doc)
        elapsed_ms = int(round((time.monotonic() - started) * 1000))
        if writer:
            journal = {"type": "journal", "baseline": self.task.baseline,
                       "entries": list(self.session.bus.journal),
                       "truth": self.task.truth.to_dict(),
                       "document_name": f"{self.task.task_id}.rdoc.json"}
            if self.task.files:
                journal["files"] = self.task.files
            writer.write(journal)
            writer.write({"type": "verify", **report.to_dict()})
            writer.write({"type": "audit", **audit})
            writer.write({"type": "end", "termination": self.termination,
                          "budget_tripped": self.budget_tripped, "error": self.error,
                          "steps": self.state.steps, "turns": n,
                          "run_check_uses": self.state.run_check_uses,
                          "faults": self.state.faults, "usage_total": usage_total,
                          "cost_usd": None, "elapsed_ms": elapsed_ms,
                          "effective_score": report.effective_score,
                          "rubric_score": report.rubric_score,
                          "hard_failed": report.hard_failed})
            writer.close()
        return EpisodeResult(task_id=self.task.task_id, agent=self.agent.name,
                             termination=self.termination, report=report,
                             steps=self.state.steps, run_check_uses=self.state.run_check_uses,
                             faults=self.state.faults, usage_total=usage_total,
                             elapsed_ms=elapsed_ms, path=str(self.path) if self.path else None,
                             budget_tripped=self.budget_tripped, error=self.error, turns=n)


def run_episode(task: Task, agent: Agent, config: EpisodeConfig = EpisodeConfig(),
                out_root=None, pins: Optional[dict] = None) -> EpisodeResult:
    """Run one episode; the trajectory is written under ``out_root`` when given."""
    return Episode(task, agent, config, out_root=out_root, pins=pins).run()


__all__ = ["HARNESS_VERSION", "RESULT_CAP", "EpisodeConfig", "EpisodeResult", "Episode",
           "run_episode"]
