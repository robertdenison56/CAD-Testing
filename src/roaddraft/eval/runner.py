"""The runner (eval plan section 4.7): a matrix of episodes -- task set x
agents and models x prompt levels x modes x dialects x samples -- run
through a thread pool and written under ``results/<run_id>/``.  A cell whose
episode file already has an ``end`` record is skipped, so a stopped run
resumes.  ``summary.json`` and ``run.json`` (the configuration and the
engine pins) are written at the end; the leaderboard report over many runs
is E4.

A model is an agent too: ``models`` names model ids, each run as an
``LLMAgent`` over its provider (``provider``, or the one the id implies),
with ``provider_options`` (effort, max_tokens, base_url ...), or as a
``CLIAgent`` when the provider is a headless CLI (``claude-code``, ``codex``).  The cost cap
stops the runner, not an episode: once the episodes finished so far (the
resumed ones included) have cost ``cost_cap`` dollars, no new episode starts
and the running ones finish.  Episodes of an unpriced model cost nothing
against the cap, so a cap on a local model never trips.

A run may append one file to every model's system prompt (``system_extra``,
``--system-extra``: training plan stage T0).  ``run.json`` and every episode
header name the file and its digest, and a run is not resumed over finished
episodes that were told another one (``ResumeMismatch``).  The same holds
for ``--thinking off`` (``provider_options["thinking"]``, recorded in each
header's ``provider_config``): a run is not resumed over episodes that ran
under the other setting.

A dead endpoint stops the runner too (``stopped = "engine"``): before each
episode the agent is asked whether it is ready (an LLM agent's provider
probes its local server and reloads the engine, up to its own deadline),
and a no leaves that episode unwritten and starts no other, so the resume
runs them. As a backstop, ``DEAD_EPISODES`` episodes in a row that ended
in an error before their first step stop the runner the same way
(``stopped = "errors"``). Both are what the 9B's d1-real run lacked on
2026-10-24, when 61 of 99 episodes went to a server whose engine had died.
"""
from __future__ import annotations

import json
import statistics
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from roaddraft.eval import providers
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import AGENTS, Agent, CLIAgent, LLMAgent, ReplayAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import HARNESS_VERSION, Episode, EpisodeConfig, EpisodeResult
from roaddraft.eval.prompts import SystemExtra
from roaddraft.eval.trajectory import episode_path, is_complete, read_episode

DEFAULT_RESULTS = "results"
#: consecutive episodes that errored before their first step: the endpoint, not the model
DEAD_EPISODES = 3


class EngineDown(RuntimeError):
    """The agent's endpoint did not answer, so the episode was not started."""


@dataclass(frozen=True)
class Cell:
    """One episode to run."""
    entry: dict
    agent: str
    level: str
    mode: str
    sample: int
    dialect: str = "neutral"

    @property
    def task_id(self) -> str:
        """The task's id; a probe task at the vague level has its own (``probe_tasks.task_id``),
        and so has a generated one (``train-deeds``, ``train-qa``)."""
        if self.level == "vague" and ("probe" in self.entry or "generated" in self.entry):
            tid = self.entry.get("vague_task_id")
            if not tid:
                raise ValueError(f"probe {self.entry.get('probe') or self.entry['task_id']} "
                                 "has no vague prompt")
            return tid
        return self.entry["task_id"]


@dataclass
class RunSpec:
    taskset: str
    agents: Sequence[str] = ("oracle",)
    levels: Sequence[str] = ("explicit",)
    modes: Sequence[str] = ("single",)
    samples: int = 1
    limit: Optional[int] = None
    task_ids: Optional[Sequence[str]] = None
    results_root: str = DEFAULT_RESULTS
    run_id: Optional[str] = None
    concurrency: int = 4
    budgets: Budgets = Budgets()
    journal: Optional[str] = None      # for the replay agent
    tasksets_root: Optional[str] = None
    models: Sequence[str] = ()         # model ids, each an LLMAgent
    provider: Optional[str] = None     # None: the provider each model id implies
    provider_options: Dict[str, Any] = field(default_factory=dict)
    dialects: Sequence[str] = ("neutral",)
    cost_cap: Optional[float] = None   # dollars; stops the runner, not an episode
    subset: Optional[str] = None       # a cost subset's tag (eval/subsets.py): task_ids are its ids
    #: a file appended to every model's system prompt (``--system-extra``, plan stage T0)
    system_extra: Optional[SystemExtra] = None

    @property
    def all_agents(self) -> List[str]:
        return list(self.agents) + [m for m in self.models if m not in self.agents]

    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        stamp = time.strftime("%Y-%m-%d")
        names = "+".join(a.replace("/", "-") for a in self.all_agents)
        return f"{stamp}-{self.taskset}-{names}"

    @property
    def out_root(self) -> Path:
        return Path(self.results_root) / self.resolved_run_id()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["budgets"] = self.budgets.to_dict()
        d["run_id"] = self.resolved_run_id()
        # the file and its digest, not its text; no key at all without one, so run.json reads as before
        del d["system_extra"]
        if self.system_extra is not None:
            d["system_extra"] = self.system_extra.record()
        return d


def matrix(spec: RunSpec) -> List[Cell]:
    rows = tasksets.entries(spec.taskset, spec.limit, spec.task_ids, spec.tasksets_root)
    return [Cell(entry, agent, level, mode, sample, dialect)
            for entry in rows for agent in spec.all_agents for level in spec.levels
            for mode in spec.modes for dialect in spec.dialects
            for sample in range(spec.samples)]


def make_agent(name: str, spec: RunSpec) -> Agent:
    if name in spec.models:
        provider = providers.make(name, spec.provider, **spec.provider_options)
        if isinstance(provider, providers.CLIProvider):
            return CLIAgent(provider)
        return LLMAgent(provider)
    if name == "replay":
        if not spec.journal:
            raise ValueError("the replay agent needs --journal")
        return ReplayAgent(spec.journal)
    if name not in AGENTS:
        raise ValueError(f"unknown agent {name!r}; agents: {', '.join(sorted(AGENTS))}, "
                         "replay, or a model (--model)")
    return AGENTS[name]()


def run_cell(cell: Cell, spec: RunSpec, pins: Optional[dict] = None,
             agent_factory: Optional[Callable[[str, RunSpec], Agent]] = None) -> EpisodeResult:
    task = tasksets.task_from_entry(cell.entry, level=cell.level)
    config = EpisodeConfig(level=cell.level, mode=cell.mode, dialect=cell.dialect,
                           budgets=spec.budgets, sample=cell.sample, run_id=spec.resolved_run_id(),
                           system_extra=spec.system_extra)
    # a probe task (eval/probe_tasks.py), a pilot or a generated one: its own episode and oracle
    if "probe" in cell.entry or "generated" in cell.entry:
        from roaddraft.eval import probe_tasks
        if cell.agent == "oracle" and agent_factory is None:
            agent = probe_tasks.ProbeOracleAgent()
        elif cell.agent in ("scripted",) and agent_factory is None:
            raise ValueError("the scripted agent drafts D1 tasks only; on a probe task run "
                             "oracle, null, replay or a model")
        else:
            agent = (agent_factory or make_agent)(cell.agent, spec)
        _ready(agent)
        return probe_tasks.ProbeEpisode(task, agent, config, out_root=spec.out_root,
                                        pins=pins).run()
    agent = (agent_factory or make_agent)(cell.agent, spec)
    _ready(agent)
    return Episode(task, agent, config, out_root=spec.out_root, pins=pins).run()


def _ready(agent: Agent) -> None:
    """Raise ``EngineDown`` when the agent's endpoint does not answer, before
    any episode file is written."""
    check = getattr(agent, "ready", None)
    if check is not None and not check():
        raise EngineDown(f"{getattr(agent, 'name', 'the agent')}: the model endpoint did not answer; "
                         "the episode was not started")


def cell_path(spec: RunSpec, cell: Cell):
    return episode_path(spec.out_root, cell.task_id, cell.agent, cell.dialect, cell.mode,
                        cell.level, cell.sample)


def measured_cost(agent: str, results_root: str = DEFAULT_RESULTS) -> Optional[dict]:
    """What the finished episodes of ``agent`` under ``results_root`` cost:
    ``{"n", "mean_cost_usd"}`` over those with a cost, or None."""
    safe = agent.replace("/", "-").replace(" ", "_")
    costs = []
    for path in Path(results_root).glob(f"*/episodes/*.{safe}.*.jsonl"):
        try:
            end = read_episode(path)["end"]
        except (OSError, ValueError):
            continue
        if end and end.get("cost_usd") is not None:
            costs.append(float(end["cost_usd"]))
    if not costs:
        return None
    return {"n": len(costs), "mean_cost_usd": round(statistics.fmean(costs), 4)}


def _pins() -> dict:
    try:
        from roaddraft.runners.core import pins
        return pins()
    except Exception:  # pragma: no cover - a checkout without git or the runner
        return {}


def _key(r: dict) -> str:
    key = f"{r['agent']}|{r['level']}|{r['mode']}"
    dialect = r.get("dialect", "neutral")
    return key if dialect == "neutral" else f"{key}|{dialect}"


def summarize(results: Iterable[dict]) -> dict:
    """Per agent (and level, mode, dialect when not neutral): n, mean effective
    and rubric score, hard-fail, submit and clean-sheet rates, median steps,
    the invalid-call rate, and the cost where the model is priced."""
    rows = list(results)
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        groups.setdefault(_key(r), []).append(r)
    out = {}
    for key, rs in sorted(groups.items()):
        agent, level, mode = key.split("|")[:3]
        n = len(rs)
        eff = [r["effective_score"] for r in rs]
        steps = sum(r.get("steps", 0) for r in rs)
        costs = [r["cost_usd"] for r in rs if r.get("cost_usd") is not None]
        out[key] = {"agent": agent, "level": level, "mode": mode,
                    "dialect": rs[0].get("dialect", "neutral"), "n": n,
                    "mean_effective": round(statistics.fmean(eff), 2) if n else None,
                    "mean_rubric": round(statistics.fmean(r["rubric_score"] for r in rs), 2) if n else None,
                    "hard_fail_rate": round(sum(r["hard_failed"] for r in rs) / n, 3) if n else None,
                    "submit_rate": round(sum(r["termination"] == "submit" for r in rs) / n, 3) if n else None,
                    "clean_sheet_rate": round(sum(e == 100.0 for e in eff) / n, 3) if n else None,
                    "median_steps": statistics.median(r["steps"] for r in rs) if n else None,
                    "errors": sum(r["termination"] == "error" for r in rs),
                    "min_effective": min(eff) if n else None, "max_effective": max(eff) if n else None,
                    "invalid_call_rate": (round(sum(r.get("invalid_calls", 0) for r in rs) / steps, 4)
                                          if steps else None),
                    "mean_cost_usd": round(statistics.fmean(costs), 4) if costs else None,
                    "total_cost_usd": round(sum(costs), 4) if costs else None}
    return {"groups": out, "episodes": len(rows)}


def _header_and_end(path) -> dict:
    """A finished episode's header and end records, without its turns."""
    rec = read_episode(path)
    return {"header": rec["header"], "end": rec["end"]}


class ResumeMismatch(ValueError):
    """The run's folder holds finished episodes told another system extra (or none),
    or run under another thinking setting."""


def check_resumed_prompt(spec: RunSpec, finished: Sequence[tuple]) -> None:
    """A resumed run keeps its prompt: ``ResumeMismatch`` when any finished
    episode (``(cell, record)`` pairs) was told another system extra than
    ``spec`` asks for, or none where it asks for one, or one where it asks for
    none.  Nothing is written before it is checked."""
    want = spec.system_extra.sha256 if spec.system_extra is not None else None
    odd = [cell.task_id for cell, rec in finished
           if ((rec.get("header") or {}).get("system_extra") or {}).get("sha256") != want]
    if odd:
        told = f"the system extra {spec.system_extra.path} ({want[:19]})" if want else "no system extra"
        raise ResumeMismatch(
            f"{len(odd)} finished episodes in {spec.out_root} ({', '.join(odd[:3])}"
            f"{', ...' if len(odd) > 3 else ''}) were told another system extra than this run "
            f"asks for ({told}); a resumed run keeps its prompt: give it a new --run-id")
    think = (spec.provider_options or {}).get("thinking")
    odd = [cell.task_id for cell, rec in finished
           if ((rec.get("header") or {}).get("provider_config") or {}).get("thinking") != think]
    if odd:
        raise ResumeMismatch(
            f"{len(odd)} finished episodes in {spec.out_root} ({', '.join(odd[:3])}"
            f"{', ...' if len(odd) > 3 else ''}) ran with thinking "
            f"{'left to the model' if think else 'off'} and this run asks for it "
            f"{think or 'left to the model'}; a resumed run keeps its setting: give it a new --run-id")


def run(spec: RunSpec, agent_factory: Optional[Callable[[str, RunSpec], Agent]] = None,
        progress: Optional[Callable[[str], None]] = None) -> dict:
    """Run the matrix; returns the summary (also written as ``summary.json``)."""
    cells = matrix(spec)
    out_root = spec.out_root
    out_root.mkdir(parents=True, exist_ok=True)
    todo, skipped = [], []
    for cell in cells:
        (skipped if is_complete(cell_path(spec, cell)) else todo).append(cell)
    finished = [(cell, _header_and_end(cell_path(spec, cell))) for cell in skipped]
    check_resumed_prompt(spec, finished)   # before run.json is rewritten
    pins = _pins()
    (out_root / "run.json").write_text(json.dumps(
        {"spec": spec.to_dict(), "harness_version": HARNESS_VERSION, "pins": pins,
         "cells": len(cells), "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    say = progress or (lambda s: None)
    say(f"{len(cells)} cells: {len(todo)} to run, {len(skipped)} already complete")
    results: List[dict] = []
    failures: List[dict] = []
    # the episodes already on disk count in the summary and against the cost cap
    for cell, rec in finished:
        end = rec["end"]
        results.append({"task_id": cell.task_id, "agent": cell.agent, "level": cell.level,
                        "mode": cell.mode, "dialect": cell.dialect, "sample": cell.sample,
                        "termination": end["termination"], "effective_score": end["effective_score"],
                        "rubric_score": end["rubric_score"], "hard_failed": end["hard_failed"],
                        "steps": end["steps"], "invalid_calls": end.get("invalid_calls", 0),
                        "cost_usd": end.get("cost_usd"), "resumed": True})
    spent = sum(r["cost_usd"] or 0.0 for r in results if r.get("cost_usd") is not None)
    stopped: Optional[str] = None
    not_run = 0

    def one(cell: Cell) -> dict:
        r = run_cell(cell, spec, pins, agent_factory)
        return {**r.summary(), "level": cell.level, "mode": cell.mode, "dialect": cell.dialect,
                "sample": cell.sample}

    def capped() -> bool:
        return spec.cost_cap is not None and spent >= spec.cost_cap

    workers = max(1, spec.concurrency)
    queue = list(todo)
    dead_streak = 0
    if capped():
        say(f"cost cap ${spec.cost_cap:.2f} already reached (${spent:.2f}); nothing started")

    def stop(reason: str, why: str) -> None:
        nonlocal stopped, not_run
        if stopped is None:
            stopped, not_run = reason, len(queue)
            say(f"{why}: {len(queue)} episodes not started; the running ones finish")
        queue.clear()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        running: Dict[Any, Cell] = {}
        # episodes start only as workers free up, so none starts past the cap
        while queue and len(running) < workers and not capped():
            cell = queue.pop(0)
            running[pool.submit(one, cell)] = cell
        while running:
            done, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for fut in done:
                cell = running.pop(fut)
                try:
                    row = fut.result()
                except Exception as exc:  # a cell that could not start (bad entry, agent), or an escape from the loop
                    tb = traceback.format_exc()
                    failures.append({"task_id": cell.task_id, "agent": cell.agent,
                                     "error": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                                     "traceback": tb})
                    say(f"ERROR {cell.task_id} {cell.agent}: {exc}\n{tb}")
                    if isinstance(exc, EngineDown):
                        stop("engine", "the model endpoint is down")
                    continue
                results.append(row)
                cost = row.get("cost_usd")
                spent += cost or 0.0
                dead_streak = dead_streak + 1 if (row["termination"] == "error"
                                                   and not row.get("steps")) else 0
                if dead_streak >= DEAD_EPISODES:
                    stop("errors", f"{dead_streak} episodes in a row ended in an error before "
                         "their first step")
                say(f"{row['task_id']} {cell.agent} {cell.level} {cell.mode}"
                    + (f" {cell.dialect}" if cell.dialect != "neutral" else "")
                    + f" s{cell.sample}: {row['effective_score']:.1f} ({row['termination']}, "
                    f"{row['steps']} steps" + (f", ${cost:.3f}" if cost is not None else "") + ")")
            if capped() and queue and stopped is None:
                say(f"cost cap ${spec.cost_cap:.2f} reached (${spent:.2f}): {len(queue)} episodes "
                    "not started; the running ones finish")
            while queue and len(running) < workers and not capped():
                cell = queue.pop(0)
                running[pool.submit(one, cell)] = cell
            if capped() and queue:
                stopped = "cost_cap"
    if capped() and queue:
        stopped, not_run = "cost_cap", len(queue)
    summary = summarize(results)
    summary.update({"run_id": spec.resolved_run_id(), "taskset": spec.taskset,
                    "failures": failures, "skipped": len(skipped), "stopped": stopped,
                    "not_run": not_run, "spent_usd": round(spent, 4),
                    "cost_cap": spec.cost_cap})
    (out_root / "summary.json").write_text(json.dumps(summary, indent=1))
    (out_root / "episodes.json").write_text(json.dumps(results, indent=1))
    return summary


__all__ = ["DEFAULT_RESULTS", "DEAD_EPISODES", "EngineDown", "Cell", "RunSpec", "matrix", "make_agent",
           "run_cell", "cell_path", "measured_cost", "summarize", "ResumeMismatch",
           "check_resumed_prompt", "run"]
