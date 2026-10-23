"""Probe tasks: the harder-task pilots run as tasks of the eval harness.

A probe (``probes/base.py``) is a task with its own pass/fail check, read from
the documents a run leaves on disk.  Run here it keeps everything Track P gives
it -- the start project its fixture builds (``fixture.start_document``), the
task text the probe runner sends (``prompting.task_text``), the MCP server's own
tools (``RoadDraftMCP``, served in-process with autosave, ``open_document``, and
``view_attachment`` for a probe that comes with scans), file access held to the
episode folder and every path shown relative to the project folder, where the
probe runner starts its server -- and gains what the harness adds: the
providers and budgets, the trajectory log, the report and the board.

Grading is the probe's own check, applied as ``runners.score`` applies it: the
start built fresh is the baseline, the document the probe hands over is read
back from disk, and an episode that made no engine call fails.  The effective
score is 100 on a pass and 0 on a fail.  The rubric score beside it is the
share of the items the check asked for that the document has (the research
plan's scope completion), so a near miss shows beside the pass rate.  The
files of the project the episode changed are kept beside its trajectory
(``<run>/projects/<episode>/``), so ``report --reverify`` grades them again
under the current checks, as Track P re-scores its run folders.

``run_check`` (the self-correct mode) answers pass or fail and how many of the
items are done, never the check's own words: a probe's detail names expected
values.  The oracle agent is the probe's scripted solution as tool calls,
recorded through the server (``trajectories.record``); a session the solution
opens on another file of the project, such as a base drawing it repairs, is
recorded as an ``open_document`` of that file, as a model would have to do it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.document import confine
from roaddraft.eval import dialects
from roaddraft.eval.agents import Agent, Submit, ToolCall
from roaddraft.eval.agents.basic import _QueueAgent
from roaddraft.eval.budget import Budgets, BudgetState
from roaddraft.eval.episode import (HARNESS_VERSION, INVALID, STATE_KEYS, Episode,
                                    EpisodeConfig, _error, _hash)
from roaddraft.eval.tools import HARNESS_DEFINITIONS, RENDER_QUERIES, shape_params
from roaddraft.mcp.server import INSTRUCTIONS, RoadDraftMCP
from roaddraft.probes import fixture, prompting
from roaddraft.probes.base import Probe, Result

#: the task set of the harder-task pilots (docs/Probes_Pilots.md)
PILOT_SET = "hard-pilots"
#: a probe task's id: ``PR-<probe id>-<hash of its task text>``, so a changed
#: prompt is a new task and the manifest's tripwire sees it
ID_PREFIX = "PR-"
#: the pilot families by the brainstorm's numbers, as task types
FAMILIES = {
    "p01": "redraw-from-scan", "p02": "sources-disagree", "p03": "survey-traps",
    "p04": "crowded-annotation", "p05": "sheet-breaks", "p06": "plan-and-profile",
    "p10": "typical-section", "p11": "redlines", "p12": "plan-set", "p13": "striping",
    "p14": "qa-review", "p15": "plan-reading", "p17": "twisted-sheet",
}
#: the budgets a probe task runs under when the run sets none: Track P's
#: (120 turns of several calls each, 30 minutes), not D1's 150 steps -- one
#: scripted solution alone makes about a thousand calls
BUDGETS = Budgets(steps=600, faults=12, output_tokens=200000, wall_clock_s=1800.0)
#: the id of the one check a probe task's report carries
CHECK_ID = "PROBE"
#: what the agent is told about the harness, after the server's instructions
HARNESS_NOTE = """How the task runs:
- Each tool call is one step. You have $steps steps, and $faults failed calls in a row end the task. Several calls in one turn run in order, and their results come back together.
- The document saves itself after every command; open_document switches to another file of the project, and the one you were handed is what gets graded.
- get_task_brief shows the task again.
$mode_rules
- When the task is done, call submit, or reply with your report. What is in the files when you finish, or when the steps run out, is what gets graded."""
MODE_RULES = {
    "single": "- run_check is not available in this task.",
    "self_correct": ("- run_check says whether the task passes as it stands, and how many of its "
                     "items are done ($run_checks uses, each a step); it never says what is wrong."),
    "vision": ("- run_check says whether the task passes as it stands, and how many of its "
               "items are done ($run_checks uses, each a step); it never says what is wrong. "
               "render_sheet and render_model return the image."),
}


# ----------------------------------------------------------------- tasks


def family(probe: Probe) -> str:
    return probe.id.split("-")[0]


def task_type(probe: Probe) -> str:
    """``pilot-<family name>``: the stratum the report's interval samples within."""
    return "pilot-" + FAMILIES.get(family(probe), family(probe))


def brief_text(probe: Probe) -> str:
    """The task text, exactly as the probe runner sends it."""
    return prompting.task_text(probe)


def task_id(probe: Probe) -> str:
    h = hashlib.sha256(brief_text(probe).encode("utf-8")).hexdigest()[:10]
    return f"{ID_PREFIX}{probe.id}-{h}"


def attachments_arg(probe: Probe, project: Path) -> Optional[str]:
    """The attachments folder the probe's server is started with, if any."""
    args = [a.replace("{project}", str(project)) for a in probe.server_args]
    return args[args.index("--attachments") + 1] if "--attachments" in args else None


def pilots() -> List[Probe]:
    """The pilots in the brainstorm's order, instances by id."""
    from roaddraft.probes.pilot import PILOT_PROBES
    return sorted(PILOT_PROBES, key=lambda p: (int(family(p)[1:]), p.id))


def by_id(probe_id: str) -> Probe:
    for p in pilots():
        if p.id == probe_id:
            return p
    from roaddraft.probes import tasks
    return tasks.get(probe_id)


def generator_version(probes: Optional[Sequence[Probe]] = None) -> str:
    """``probe-<hash>`` over the set's ids and task texts: what the report
    holds a run's episodes to, as the seeded sets are held to the generator."""
    probes = list(probes) if probes is not None else pilots()
    h = hashlib.sha256()
    for p in sorted(probes, key=lambda p: p.id):
        h.update(p.id.encode("utf-8") + b"\0" + brief_text(p).encode("utf-8") + b"\0")
    return "probe-" + h.hexdigest()[:12]


def entry(probe: Probe) -> dict:
    """A task-set manifest entry."""
    return {"probe": probe.id, "family": family(probe), "task_type": task_type(probe),
            "start": probe.start, "sheets": 1,
            "attachments": "--attachments" in probe.server_args, "task_id": task_id(probe)}


@dataclass
class ProbeTask:
    """A probe as a task of the harness: what the runner and the episode need."""
    probe: Probe
    task_id: str
    task_type: str
    brief: str

    @property
    def files(self):  # the project is built by the probe's fixture, not shipped
        return None


def task_from_entry(row: dict, strict: bool = True) -> ProbeTask:
    probe = by_id(row["probe"])
    tid = task_id(probe)
    if strict and tid != row["task_id"]:
        raise ValueError(f"task id of probe {probe.id} is {tid}, the manifest says "
                         f"{row['task_id']}: its task text changed; python -m roaddraft.eval "
                         "taskset --write")
    return ProbeTask(probe, tid, task_type(probe), brief_text(probe))


# ------------------------------------------------------------- the server


class EpisodeServer(RoadDraftMCP):
    """The MCP server's tools in-process for one episode: every path the agent
    is shown is relative to the project folder, and a relative path it gives
    resolves there, as with the probe runner's server, which starts in it."""

    def __init__(self, session: Session, project: Path, **kw):
        self.project = Path(project).resolve()
        super().__init__(session, **kw)
        session.base_dir = self.project

    def _shown(self, result):
        return result if self.root is None else self.root.show(result, base=str(self.project))

    def _call_extra(self, name: str, arguments: dict) -> dict:
        path = arguments.get("path")
        if name == "open_document" and isinstance(path, str) and path:
            p = Path(path).expanduser()
            if not p.is_absolute():
                arguments = dict(arguments, path=str(self.project / p))
        result = super()._call_extra(name, arguments)
        self.session.base_dir = self.project
        return result


def _reply(reply: dict) -> Tuple[dict, List[Tuple[str, str]]]:
    """An MCP tool reply as the harness's result dict, and its images."""
    content = reply.get("content") or []
    text = next((c["text"] for c in content if c.get("type") == "text"), "")
    images = [(c.get("mimeType", "image/png"), c["data"]) for c in content
              if c.get("type") == "image" and c.get("data")]
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            result = {"ok": not reply.get("isError"), "result": result}
    except ValueError:
        result = ({"ok": False, "error": {"type": "tool_error", "message": text}}
                  if reply.get("isError") else {"ok": True, "text": text})
    if reply.get("isError"):
        result["ok"] = False
    return result, images


def start_project(probe: Probe, folder: Path) -> Tuple[Path, Path]:
    """The probe's start built under ``folder/project``: (project, document)."""
    project = Path(folder) / "project"
    doc = fixture.start_document(project, probe.start)
    return project, Path(doc)


# ---------------------------------------------------------------- grading


@dataclass
class ProbeReport:
    """A probe task's grade, shaped as the report reads a verify record."""
    probe: str
    passed: bool
    detail: str
    items: List[Tuple[str, bool]] = field(default_factory=list)
    touched: bool = True

    @property
    def scope(self) -> Tuple[int, int]:
        if not self.items:
            return int(self.passed), 1
        return sum(bool(d) for _n, d in self.items), len(self.items)

    @property
    def effective_score(self) -> float:
        return 100.0 if self.passed else 0.0

    @property
    def rubric_score(self) -> float:
        done, asked = self.scope
        return round(100.0 * done / asked, 4) if asked else 0.0

    @property
    def hard_failed(self) -> bool:
        return not self.passed

    def to_dict(self) -> dict:
        from roaddraft.tasks.spec_v1 import SPEC_VERSION, spec_hash
        from roaddraft.verify import VERIFIER_VERSION
        done, asked = self.scope
        return {"kind": "probe", "probe": self.probe, "passed": self.passed,
                "detail": self.detail, "touched": self.touched,
                "items": [[n, bool(d)] for n, d in self.items],
                "items_done": done, "items_asked": asked,
                "effective_score": self.effective_score, "rubric_score": self.rubric_score,
                "hard_failed": self.hard_failed, "spec_version": SPEC_VERSION,
                "spec_hash": spec_hash(), "verifier_version": VERIFIER_VERSION,
                "checks": [{"id": CHECK_ID, "name": "the probe's own check", "weight": 100,
                            "credit": round(done / asked, 4) if asked else 0.0,
                            "in_scope": True, "findings": [],
                            "hard_fail_triggered": not self.passed}],
                "findings": []}


def grade(probe: Probe, project: Path, touched: bool = True) -> ProbeReport:
    """The probe's check on the document ``project`` holds, against its start
    built fresh; an episode that made no engine call fails, as on Track P."""
    with tempfile.TemporaryDirectory(prefix="roaddraft-probe-start-") as tmp:
        start = Path(fixture.start_document(Path(tmp), probe.start))
        baseline = Session.load(start, out_dir=Path(tmp))
        submitted = Session.load(Path(project) / fixture.START[probe.start],
                                 out_dir=Path(project).parent / "renders")
        result: Result = probe.check(baseline, submitted)
    passed = bool(result.passed) and touched
    # an episode that changed nothing did none of the items, whatever the start
    # already satisfies (a clean control's "no false alarms")
    items = list(result.items) if touched else [(n, False) for n, _d in result.items]
    return ProbeReport(probe.id, passed, result.detail if touched else "no engine calls",
                       items, touched)


def _changed_files(project: Path, probe: Probe) -> List[Path]:
    """The files of ``project`` that differ from a fresh start (new ones too)."""
    with tempfile.TemporaryDirectory(prefix="roaddraft-probe-start-") as tmp:
        fixture.start_document(Path(tmp), probe.start)
        out = []
        for f in sorted(p for p in Path(project).rglob("*") if p.is_file()):
            rel = f.relative_to(project)
            fresh = Path(tmp) / rel
            if not fresh.exists() or fresh.read_bytes() != f.read_bytes():
                out.append(rel)
        return out


def keep(project: Path, probe: Probe, dest: Path) -> List[str]:
    """Copy the files the episode changed into ``dest``; their relative paths."""
    changed = _changed_files(project, probe)
    for rel in changed:
        target = Path(dest) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(project) / rel, target)
    return [r.as_posix() for r in changed]


def rescore(episode_file, journal: dict) -> dict:
    """``report --reverify`` for a probe episode: its start built fresh, the
    kept files laid over it, graded by the current check."""
    probe = by_id(journal["probe"])
    kept = journal.get("project")
    with tempfile.TemporaryDirectory(prefix="roaddraft-probe-rescore-") as tmp:
        project, _doc = start_project(probe, Path(tmp))
        if kept:
            src = (Path(episode_file).parent / kept).resolve()
            for rel in journal.get("kept_files") or []:
                if (src / rel).is_file():
                    (project / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src / rel, project / rel)
        return grade(probe, project, bool(journal.get("touched", True))).to_dict()


# ---------------------------------------------------------------- episode


def system_prompt(mode: str, budgets: Budgets) -> str:
    """The server's instructions, as Track P sends them, then how the harness runs."""
    from string import Template
    values = {"steps": budgets.steps, "faults": budgets.faults, "run_checks": budgets.run_checks}
    rules = Template(MODE_RULES[mode]).substitute(values)
    return (INSTRUCTIONS.strip() + "\n\n"
            + Template(HARNESS_NOTE).substitute(values, mode_rules=rules).strip() + "\n")


class ProbeEpisode(Episode):
    """One agent on one probe task."""

    def __init__(self, task: ProbeTask, agent: Agent, config: EpisodeConfig = EpisodeConfig(),
                 out_root=None, pins: Optional[dict] = None):
        self.task = task
        self.probe = task.probe
        self.agent = agent
        self.config = config
        self.budgets = config.mode_budgets
        self.out_root = out_root
        self.pins = pins
        self.session = None
        self.mcp: Optional[EpisodeServer] = None
        self.root: Optional[confine.Root] = None
        self.state = BudgetState()
        self.scope: List[str] = []
        self.engine_calls = 0
        with tempfile.TemporaryDirectory() as tmp:
            # the tool names, for the dialect, before the episode's own server exists
            names = {t["name"] for t in RoadDraftMCP(
                Session(), attachments=tmp if "--attachments" in self.probe.server_args
                else None).tools()}
        self.allowed = names | {"get_task_brief", "submit"} | (
            {"run_check"} if config.mode != "single" else set())
        self.dialect = dialects.get(config.dialect, self.allowed)
        self.brief_text = self.dialect.text(task.brief)
        self.tools: List[dict] = []
        self.turns: List[dict] = []
        self.termination = None
        self.budget_tripped = None
        self.error = None
        self.submit_note = ""
        self.implicit_submit = False
        self.invalid_calls = 0
        self.cost_usd = None
        self._turn_images: List[Optional[list]] = []
        self._workdir = None
        self.project: Optional[Path] = None

    # ------------------------------------------------------------ pieces

    def reset(self) -> dict:
        self._workdir = tempfile.TemporaryDirectory(prefix="roaddraft-probe-episode-")
        folder = Path(self._workdir.name).resolve()
        self.project, doc = start_project(self.probe, folder)
        session = Session.load(doc, out_dir=folder / "renders")
        self.root = confine.Root(folder)
        self.mcp = EpisodeServer(session, self.project, autosave=True, root=str(folder),
                                 attachments=attachments_arg(self.probe, self.project))
        self.session = session
        defs = []
        for t in self.mcp.tools():
            kind = self.mcp.kind_of(t["name"])
            kind = {"extra": "query" if t["name"] == "view_attachment" else "command"}.get(kind, kind)
            defs.append({"name": t["name"], "kind": kind, "description": t["description"],
                         "input_schema": t["inputSchema"]})
        for name in ("get_task_brief", "run_check", "submit"):
            if name in self.allowed:
                defs.append({"name": name, "kind": "harness", **HARNESS_DEFINITIONS[name]})
        self.tools = self.dialect.tools(sorted(defs, key=lambda d: d["name"]))
        self.state = BudgetState()
        self.agent.reset(self.task, self.config.level, self.config.mode)
        system = system_prompt(self.config.mode, self.budgets)
        self.agent.begin({"mode": self.config.mode, "level": self.config.level,
                          "dialect": self.config.dialect, "skin": self.dialect,
                          "budgets": self.budgets, "scope": self.scope,
                          "system": self.dialect.text(system)})
        return {"turn": 0, "brief": self.brief_text, "tools": self.tools,
                "state": self.state_summary(), "budget": self.state.remaining(self.budgets),
                "mode": self.config.mode, "dialect": self.config.dialect}

    def state_summary(self) -> dict:
        with confine.held(self.root):
            result = self.mcp.session.query("get_document_state", {"detail": "summary"})
        summary = self.mcp._shown(result.get("summary") or {})
        return {k: summary[k] for k in STATE_KEYS if k in summary}

    def header(self) -> dict:
        from roaddraft.tasks.spec_v1 import SPEC_VERSION, spec_hash
        from roaddraft.verify import VERIFIER_VERSION
        pins = self.pins or {}
        return {"type": "header", "run_id": self.config.run_id, "task_id": self.task.task_id,
                "task_type": self.task.task_type, "sheets": 1, "seed": None,
                "probe": self.probe.id, "start": self.probe.start,
                "spec_version": SPEC_VERSION, "spec_hash": spec_hash(),
                "generator_version": generator_version(),
                "verifier_version": VERIFIER_VERSION, "harness_version": HARNESS_VERSION,
                "prompt_hash": _hash(self.brief_text), "git_commit": pins.get("commit"),
                "dirty": pins.get("dirty"),
                "tools_sha256": _hash(json.dumps(self.tools, sort_keys=True)),
                **self.agent.describe(), "agent": self.agent.name,
                "dialect": self.config.dialect, "mode": self.config.mode,
                "level": self.config.level, "sample": self.config.sample,
                "scope": self.scope, "budgets": self.budgets.to_dict(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    def execute(self, call: ToolCall) -> dict:
        name, params = self.dialect.canonical(call.name), call.params or {}
        images = None
        if name not in self.allowed:
            hint = ("tools in this task: "
                    + ", ".join(sorted(self.dialect.present(n) for n in self.allowed)))
            result = _error(call.name, "unknown_command",
                            f"{call.name!r} is not a tool of this task", hint)
        elif name in ("get_task_brief", "run_check", "submit"):
            result = self._harness_tool(name, params)
        else:
            kind = self.mcp.kind_of(name)
            if kind in ("command", "query"):
                params, notes = shape_params(name, params)
            else:
                notes = []
            result, shown = _reply(self.mcp.call_tool(name, params))
            self.engine_calls += 1
            if notes:
                result["warnings"] = list(result.get("warnings") or []) + notes
            if name == "view_attachment" or (name in RENDER_QUERIES
                                              and self.config.mode == "vision"):
                images = shown or None
            elif shown:
                result["note"] = ("the image is on disk at 'path'; it is not returned "
                                  "inline in this mode")
            result, _ = self._shape_result(name, result)
        ok = bool(result.get("ok"))
        if not ok and (result.get("error") or {}).get("type") in INVALID:
            self.invalid_calls += 1
        self.state.note_call(ok)
        self._turn_images.append(images)
        return result

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
            report = grade(self.probe, self.project, self.engine_calls > 0)
            done, asked = report.scope
            return {"ok": True, "name": name, "status": "pass" if report.passed else "fail",
                    "items_done": done, "items_asked": asked,
                    "budget_remaining": self.budgets.run_checks - self.state.run_check_uses}
        if name == "submit":
            self.submit_note = str(params.get("note") or "")
            return {"ok": True, "name": name, "message": "submitted"}
        return _error(name, "unknown_command", f"unknown harness tool {name!r}")

    def finish(self) -> Tuple[ProbeReport, List[dict]]:
        touched = self.engine_calls > 0
        report = grade(self.probe, self.project, touched)
        kept, rel = [], None
        if self.path is not None:
            dest = Path(self.out_root) / "projects" / Path(self.path).stem
            if dest.exists():
                shutil.rmtree(dest)
            kept = keep(self.project, self.probe, dest)
            rel = Path("..") / "projects" / Path(self.path).stem
        journal = {"type": "journal", "probe": self.probe.id, "start": self.probe.start,
                   "document_name": fixture.START[self.probe.start], "touched": touched,
                   "project": rel.as_posix() if rel else None, "kept_files": kept}
        records = [journal, {"type": "verify", **report.to_dict()},
                   {"type": "audit", "skipped": "a probe task is graded by its own check"}]
        return report, records

    def run(self):
        try:
            return super().run()
        finally:
            if self._workdir is not None:
                self._workdir.cleanup()


# ----------------------------------------------------------------- oracle


_ORACLE_LOCK = threading.Lock()
_ORACLE_CACHE: Dict[str, List[Tuple[str, dict]]] = {}


def oracle_calls(probe: Probe) -> List[Tuple[str, dict]]:
    """The probe's scripted solution as the tool calls a model would make, its
    paths relative to the project folder.  Each session the solution works on
    is recorded; a switch to another file of the project becomes an
    ``open_document`` of it.  Recorded once per process."""
    with _ORACLE_LOCK:
        if probe.id not in _ORACLE_CACHE:
            _ORACLE_CACHE[probe.id] = _record(probe)
        return [(n, json.loads(json.dumps(p))) for n, p in _ORACLE_CACHE[probe.id]]


def _record(probe: Probe) -> List[Tuple[str, dict]]:
    if probe.solve is None:
        raise ValueError(f"{probe.id} has no scripted solution")
    calls: List[Tuple[str, dict]] = []
    with tempfile.TemporaryDirectory(prefix="roaddraft-probe-oracle-") as tmp:
        folder = Path(tmp).resolve()
        project, doc = start_project(probe, folder)
        root = confine.Root(folder)
        active = [doc.resolve()]
        original_load = Session.__dict__["load"]

        def rel(value):
            return root.show(value, base=str(project))

        def hook(s: Session) -> Session:
            def record(kind: str, name: str, params=None):
                home = Path(s.doc._path).resolve() if getattr(s.doc, "_path", None) else None
                if home is not None and home != active[0] and root.contains(home):
                    calls.append(("open_document", {"path": rel(str(home))}))
                    active[0] = home
                calls.append((name, rel(json.loads(json.dumps(params or {}, default=str)))))
                method = Session.execute if kind == "command" else Session.query
                return method(s, name, params)
            s.__dict__["execute"] = lambda name, params=None: record("command", name, params)
            s.__dict__["query"] = lambda name, params=None: record("query", name, params)
            return s

        def load(cls, path, out_dir=None):
            s = original_load.__func__(cls, path, out_dir=out_dir)
            return hook(s) if root.contains(Path(path).resolve()) else s

        session = Session.load(doc, out_dir=folder / "renders")
        session.base_dir = project
        hook(session)
        Session.load = classmethod(load)
        try:
            probe.solve(session)
        finally:
            Session.load = original_load
    return calls


class ProbeOracleAgent(_QueueAgent):
    """A probe's scripted solution, replayed through the episode loop as tool calls."""
    name = "oracle"

    def reset(self, task: ProbeTask, level: str, mode: str) -> None:
        self.queue = [ToolCall(n, p) for n, p in oracle_calls(task.probe)]


__all__ = ["PILOT_SET", "FAMILIES", "BUDGETS", "ProbeTask", "ProbeReport", "ProbeEpisode",
           "ProbeOracleAgent", "EpisodeServer", "pilots", "by_id", "entry", "task_id",
           "task_type", "brief_text", "generator_version", "task_from_entry", "grade",
           "rescore", "keep", "oracle_calls", "system_prompt"]
