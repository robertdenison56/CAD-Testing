"""The runner (eval plan section 4.7): a matrix of episodes -- task set x
agents x prompt levels x modes x samples -- run through a thread pool and
written under ``results/<run_id>/``.  A cell whose episode file already has
an ``end`` record is skipped, so a stopped run resumes.  ``summary.json``
and ``run.json`` (the configuration and the engine pins) are written at the
end; the leaderboard report over many runs is E4.
"""
from __future__ import annotations

import json
import statistics
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import AGENTS, Agent, ReplayAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import HARNESS_VERSION, Episode, EpisodeConfig, EpisodeResult
from roaddraft.eval.trajectory import episode_path, is_complete

DEFAULT_RESULTS = "results"


@dataclass(frozen=True)
class Cell:
    """One episode to run."""
    entry: dict
    agent: str
    level: str
    mode: str
    sample: int

    @property
    def task_id(self) -> str:
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

    def resolved_run_id(self) -> str:
        if self.run_id:
            return self.run_id
        stamp = time.strftime("%Y-%m-%d")
        return f"{stamp}-{self.taskset}-{'+'.join(self.agents)}"

    @property
    def out_root(self) -> Path:
        return Path(self.results_root) / self.resolved_run_id()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["budgets"] = self.budgets.to_dict()
        d["run_id"] = self.resolved_run_id()
        return d


def matrix(spec: RunSpec) -> List[Cell]:
    rows = tasksets.entries(spec.taskset, spec.limit, spec.task_ids, spec.tasksets_root)
    return [Cell(entry, agent, level, mode, sample)
            for entry in rows for agent in spec.agents for level in spec.levels
            for mode in spec.modes for sample in range(spec.samples)]


def make_agent(name: str, spec: RunSpec) -> Agent:
    if name == "replay":
        if not spec.journal:
            raise ValueError("the replay agent needs --journal")
        return ReplayAgent(spec.journal)
    if name not in AGENTS:
        raise ValueError(f"unknown agent {name!r}; agents: {', '.join(sorted(AGENTS))}, replay")
    return AGENTS[name]()


def run_cell(cell: Cell, spec: RunSpec, pins: Optional[dict] = None,
             agent_factory: Optional[Callable[[str, RunSpec], Agent]] = None) -> EpisodeResult:
    task = tasksets.task_from_entry(cell.entry)
    agent = (agent_factory or make_agent)(cell.agent, spec)
    config = EpisodeConfig(level=cell.level, mode=cell.mode, budgets=spec.budgets,
                           sample=cell.sample, run_id=spec.resolved_run_id())
    return Episode(task, agent, config, out_root=spec.out_root, pins=pins).run()


def _pins() -> dict:
    try:
        from roaddraft.runners.core import pins
        return pins()
    except Exception:  # pragma: no cover - a checkout without git or the runner
        return {}


def summarize(results: Iterable[dict]) -> dict:
    """Per agent (and level, mode): n, mean effective and rubric score, hard-fail,
    submit and clean-sheet rates, median steps."""
    rows = list(results)
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        groups.setdefault(f"{r['agent']}|{r['level']}|{r['mode']}", []).append(r)
    out = {}
    for key, rs in sorted(groups.items()):
        agent, level, mode = key.split("|")
        n = len(rs)
        eff = [r["effective_score"] for r in rs]
        out[key] = {"agent": agent, "level": level, "mode": mode, "n": n,
                    "mean_effective": round(statistics.fmean(eff), 2) if n else None,
                    "mean_rubric": round(statistics.fmean(r["rubric_score"] for r in rs), 2) if n else None,
                    "hard_fail_rate": round(sum(r["hard_failed"] for r in rs) / n, 3) if n else None,
                    "submit_rate": round(sum(r["termination"] == "submit" for r in rs) / n, 3) if n else None,
                    "clean_sheet_rate": round(sum(e == 100.0 for e in eff) / n, 3) if n else None,
                    "median_steps": statistics.median(r["steps"] for r in rs) if n else None,
                    "errors": sum(r["termination"] == "error" for r in rs),
                    "min_effective": min(eff) if n else None, "max_effective": max(eff) if n else None}
    return {"groups": out, "episodes": len(rows)}


def run(spec: RunSpec, agent_factory: Optional[Callable[[str, RunSpec], Agent]] = None,
        progress: Optional[Callable[[str], None]] = None) -> dict:
    """Run the matrix; returns the summary (also written as ``summary.json``)."""
    cells = matrix(spec)
    out_root = spec.out_root
    out_root.mkdir(parents=True, exist_ok=True)
    pins = _pins()
    (out_root / "run.json").write_text(json.dumps(
        {"spec": spec.to_dict(), "harness_version": HARNESS_VERSION, "pins": pins,
         "cells": len(cells), "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    todo, skipped = [], []
    for cell in cells:
        path = episode_path(out_root, cell.task_id, cell.agent, "neutral", cell.mode, cell.level,
                            cell.sample)
        (skipped if is_complete(path) else todo).append(cell)
    say = progress or (lambda s: None)
    say(f"{len(cells)} cells: {len(todo)} to run, {len(skipped)} already complete")
    results: List[dict] = []
    failures: List[dict] = []

    def one(cell: Cell) -> dict:
        r = run_cell(cell, spec, pins, agent_factory)
        return {**r.summary(), "level": cell.level, "mode": cell.mode, "sample": cell.sample}

    with ThreadPoolExecutor(max_workers=max(1, spec.concurrency)) as pool:
        futures = {pool.submit(one, cell): cell for cell in todo}
        for fut in as_completed(futures):
            cell = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:  # a cell that could not even start (bad entry, agent)
                failures.append({"task_id": cell.task_id, "agent": cell.agent,
                                 "error": "".join(traceback.format_exception_only(type(exc), exc)).strip()})
                say(f"ERROR {cell.task_id} {cell.agent}: {exc}")
                continue
            results.append(row)
            say(f"{row['task_id']} {cell.agent} {cell.level} {cell.mode} s{cell.sample}: "
                f"{row['effective_score']:.1f} ({row['termination']}, {row['steps']} steps)")
    # fold in the episodes already on disk, so the summary covers the whole run
    for cell in skipped:
        from roaddraft.eval.trajectory import read_episode
        rec = read_episode(episode_path(out_root, cell.task_id, cell.agent, "neutral", cell.mode,
                                        cell.level, cell.sample))
        end = rec["end"]
        results.append({"task_id": cell.task_id, "agent": cell.agent, "level": cell.level,
                        "mode": cell.mode, "sample": cell.sample,
                        "termination": end["termination"], "effective_score": end["effective_score"],
                        "rubric_score": end["rubric_score"], "hard_failed": end["hard_failed"],
                        "steps": end["steps"], "resumed": True})
    summary = summarize(results)
    summary.update({"run_id": spec.resolved_run_id(), "taskset": spec.taskset,
                    "failures": failures, "skipped": len(skipped)})
    (out_root / "summary.json").write_text(json.dumps(summary, indent=1))
    (out_root / "episodes.json").write_text(json.dumps(results, indent=1))
    return summary


__all__ = ["DEFAULT_RESULTS", "Cell", "RunSpec", "matrix", "make_agent", "run_cell", "summarize",
           "run"]
