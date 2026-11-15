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
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.document import confine
from roaddraft.eval.agents import Agent, Submit, ToolCall
from roaddraft.eval.agents.basic import _QueueAgent
from roaddraft.eval.budget import Budgets, BudgetState
from roaddraft.eval.episode import (HARNESS_VERSION, INVALID, STATE_KEYS, Episode,
                                    EpisodeConfig, _error, _hash, begin_context, prompt_fields)
from roaddraft.eval.tools import HARNESS_DEFINITIONS, RENDER_QUERIES, repair_params, shape_params
from roaddraft.mcp.server import INSTRUCTIONS, RoadDraftMCP
from roaddraft.probes import fixture, prompting
from roaddraft.probes.base import Probe, Result

#: the task set of the harder-task pilots (docs/Probes_Pilots.md)
PILOT_SET = "hard-pilots"
#: the validation set (2026-11-13, training plan §8): pilot families set on the sample sheets
#: no held-out pilot or real-sheet set uses (``probes/pilot_dev.py``); for choosing a
#: checkpoint only, never trained on, never reported
DEV_SET = "pilot-dev"
SETS = (PILOT_SET, DEV_SET)
#: a probe task's id: ``PR-<probe id>-<hash of its task text>``, so a changed
#: prompt is a new task and the manifest's tripwire sees it
ID_PREFIX = "PR-"
#: the pilot families by the brainstorm's numbers, as task types
FAMILIES = {
    "p01": "redraw-from-scan", "p02": "sources-disagree", "p03": "survey-traps",
    "p04": "crowded-annotation", "p05": "sheet-breaks", "p06": "plan-and-profile",
    "p10": "typical-section", "p11": "redlines", "p12": "plan-set", "p13": "striping",
    "p14": "qa-review", "p15": "plan-reading", "p17": "twisted-sheet",
    "p18": "redline-understanding",
}
#: the budgets a probe task runs under when the run sets none: Track P's
#: (120 turns of several calls each), not D1's 150 steps -- one scripted
#: solution alone makes about a thousand calls. The clock is a backstop behind
#: the 200,000 output tokens, sized the way the D1 clock is (e3-v3, 2026-11-03):
#: the slowest stack in use, the PC's 9B at ~33 tokens a second, needs ~100
#: minutes for them. At Track P's 30 minutes the 9B lost 8 of its 33 pilots to
#: the clock; no hosted, codex or claude-code pilot run ever reached it.
BUDGETS = Budgets(steps=600, faults=12, output_tokens=200000, wall_clock_s=7200.0)
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


def brief_text(probe: Probe, level: str = "explicit") -> str:
    """The task text at prompt ``level``, exactly as the probe runner sends it."""
    return prompting.task_text(probe, level)


def task_id(probe: Probe, level: str = "explicit") -> str:
    """``PR-<probe id>-<hash of its task text at level>``: the explicit id is the one every
    run before 2026-11-08 ran under; a vague task is its own id (its own text), so a vague
    run is held to the vague texts as an explicit run is to the explicit ones."""
    h = hashlib.sha256(brief_text(probe, level).encode("utf-8")).hexdigest()[:10]
    return f"{ID_PREFIX}{probe.id}-{h}"


def levels_of(probe: Probe) -> Tuple[str, ...]:
    """The prompt levels ``probe`` can be posed at."""
    return ("explicit", "vague") if probe.vague else ("explicit",)


def attachments_arg(probe: Probe, project: Path) -> Optional[str]:
    """The attachments folder the probe's server is started with, if any."""
    args = [a.replace("{project}", str(project)) for a in probe.server_args]
    return args[args.index("--attachments") + 1] if "--attachments" in args else None


def pilots() -> List[Probe]:
    """The pilots in the brainstorm's order, instances by id."""
    from roaddraft.probes.pilot import PILOT_PROBES
    return sorted(PILOT_PROBES, key=lambda p: (int(family(p)[1:]), p.id))


def dev_probes() -> List[Probe]:
    """``pilot-dev``'s instances, by family as the pilots are, then by id."""
    from roaddraft.probes.pilot_dev import PROBES
    return sorted(PROBES, key=lambda p: (int(family(p)[1:]), p.id))


def probes_of(name: str) -> List[Probe]:
    """The probes of probe set ``name``."""
    if name == PILOT_SET:
        return pilots()
    if name == DEV_SET:
        return dev_probes()
    raise ValueError(f"unknown probe task set {name!r}; sets: {', '.join(SETS)}")


def set_of(probe: Probe) -> str:
    """The probe set ``probe`` belongs to."""
    from roaddraft.probes.pilot_dev import BY_ID
    return DEV_SET if probe.id in BY_ID and BY_ID[probe.id] is probe else PILOT_SET


def by_id(probe_id: str) -> Probe:
    for p in pilots():
        if p.id == probe_id:
            return p
    from roaddraft.probes.pilot_dev import BY_ID
    if probe_id in BY_ID:
        return BY_ID[probe_id]
    from roaddraft.probes import tasks
    try:
        return tasks.get(probe_id)
    except KeyError:
        probe = generated(probe_id)
        if probe is None:
            raise
        return probe


def generated(probe_id: str) -> Optional[Probe]:
    """A generated training probe by its id (``tasks.deeds``: ``t03-deed-<seed>``;
    ``tasks.planted``: ``t14-qa-<seed>``), made again from its seed, which also
    registers its start; None when the id is neither's.  With it ``rescore``
    (``report --reverify``) reaches the episodes of ``train-deeds`` and ``train-qa``."""
    name, seed = generated_set(probe_id), probe_id.rpartition("-")[2]
    if name == "train-deeds":
        from roaddraft.tasks import deeds
        return deeds.deed_task(int(seed)).probe
    if name == "train-qa":
        from roaddraft.tasks import planted
        return planted.qa_task(int(seed)).probe
    return None


#: the generated training sets by the stem of their probe ids
GENERATED_SETS = {"t03-deed": "train-deeds", "t14-qa": "train-qa"}


def generated_set(probe_id: str) -> Optional[str]:
    """The generated training set a probe id is of (``t03-deed-<seed>``: ``train-deeds``;
    ``t14-qa-<seed>``: ``train-qa``); None for a pilot or a ``pilot-dev`` instance."""
    kind, _, seed = probe_id.rpartition("-")
    return GENERATED_SETS.get(kind) if seed.isdigit() else None


def pins_of(probe: Probe) -> Tuple[str, str]:
    """The generator and verifier versions an episode of ``probe`` is stamped with: its
    set's.  A generated training probe carries its own set's (``train-deeds``,
    ``train-qa``): the generator version its manifest names and the hash of the checks
    that grade it, not the held-out pilots' hashes."""
    name = generated_set(probe.id)
    if name is not None:
        from roaddraft.tasks.brief import GENERATOR_VERSION
        return GENERATOR_VERSION, check_version(check_sources(name))
    name = set_of(probe)
    return generator_version(probes_of(name)), check_version(check_sources(name))


def generator_version(probes: Optional[Sequence[Probe]] = None) -> str:
    """``probe-<hash>`` over the set's ids and task texts: what the report
    holds a run's episodes to, as the seeded sets are held to the generator."""
    probes = list(probes) if probes is not None else pilots()
    h = hashlib.sha256()
    for p in sorted(probes, key=lambda p: p.id):
        h.update(p.id.encode("utf-8") + b"\0" + brief_text(p).encode("utf-8") + b"\0")
    return "probe-" + h.hexdigest()[:12]


def current_ids(probes: Optional[Sequence[Probe]] = None, level: str = "explicit") -> FrozenSet[str]:
    """The task ids of the current set at prompt ``level``.  An id carries the hash of its
    task text, so a run whose ids are all here ran on texts the set still has."""
    return frozenset(task_id(p, level) for p in (probes if probes is not None else pilots())
                     if level in levels_of(p))


def check_sources(name: str = PILOT_SET) -> List[Path]:
    """The files the pilot checks live in: the pilot package, one module per family;
    for ``pilot-dev``, its own module beside them (it reuses the families' checks);
    for a generated training set, the module that generates it beside them (a deed
    is graded by the survey family's check, a review by its own in ``tasks.planted``)."""
    import roaddraft.probes.pilot as pilot_pkg
    paths = sorted(Path(pilot_pkg.__file__).parent.glob("*.py"))
    if name == DEV_SET:
        import roaddraft.probes.pilot_dev as dev
        paths.append(Path(dev.__file__))
    elif name in GENERATED_SETS.values():
        import importlib
        module = {"train-deeds": "roaddraft.tasks.deeds", "train-qa": "roaddraft.tasks.planted"}[name]
        paths.append(Path(importlib.import_module(module).__file__))
    return paths


def check_version(paths: Optional[Sequence[Path]] = None) -> str:
    """``pilot-check-<hash>`` over the pilot checks' sources: the verifier
    version of a probe episode.  A pilot is graded by its own check, not the
    D1 verifier, and a check that changes without its task text changing
    (the p14 repairs of pilot-astra) would otherwise re-grade earlier rows
    unseen; ``report --reverify`` re-scores a run under the current checks."""
    paths = list(paths) if paths is not None else check_sources()
    h = hashlib.sha256()
    for f in sorted(Path(x) for x in paths):
        h.update(f.name.encode("utf-8") + b"\0" + f.read_bytes() + b"\0")
    return "pilot-check-" + h.hexdigest()[:12]


def entry(probe: Probe) -> dict:
    """A task-set manifest entry."""
    return {"probe": probe.id, "family": family(probe), "task_type": task_type(probe),
            "start": probe.start, "sheets": 1,
            "attachments": "--attachments" in probe.server_args, "task_id": task_id(probe),
            "vague_task_id": task_id(probe, "vague") if probe.vague else None}


@dataclass
class ProbeTask:
    """A probe as a task of the harness: what the runner and the episode need."""
    probe: Probe
    task_id: str
    task_type: str
    brief: str
    level: str = "explicit"

    @property
    def files(self):  # the project is built by the probe's fixture, not shipped
        return None


def task_from_entry(row: dict, strict: bool = True, level: str = "explicit") -> ProbeTask:
    """The probe task a manifest row names, posed at prompt ``level``."""
    probe = by_id(row["probe"])
    tid = task_id(probe, level)
    want = row.get("vague_task_id") if level == "vague" else row["task_id"]
    if strict and tid != want:
        raise ValueError(f"{level} task id of probe {probe.id} is {tid}, the manifest says "
                         f"{want}: its task text changed; python -m roaddraft.eval "
                         "taskset --write")
    return ProbeTask(probe, tid, task_type(probe), brief_text(probe, level), level)


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
    #: the check hash of the probe's set (``check_version``); empty: the pilots'
    verifier_version: str = ""

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
        done, asked = self.scope
        return {"kind": "probe", "probe": self.probe, "passed": self.passed,
                "detail": self.detail, "touched": self.touched,
                "items": [[n, bool(d)] for n, d in self.items],
                "items_done": done, "items_asked": asked,
                "effective_score": self.effective_score, "rubric_score": self.rubric_score,
                "hard_failed": self.hard_failed, "spec_version": SPEC_VERSION,
                "spec_hash": spec_hash(),
                "verifier_version": self.verifier_version or check_version(),
                "checks": [{"id": CHECK_ID, "name": "the probe's own check", "weight": 100,
                            "credit": round(done / asked, 4) if asked else 0.0,
                            "in_scope": True, "findings": [],
                            "hard_fail_triggered": not self.passed}],
                "findings": []}


def grade(probe: Probe, project: Path, touched: bool = True, level: str = "explicit") -> ProbeReport:
    """The probe's check at prompt ``level`` (``Probe.check_at``) on the document
    ``project`` holds, against its start built fresh; an episode that made no
    engine call fails, as on Track P."""
    with tempfile.TemporaryDirectory(prefix="roaddraft-probe-start-") as tmp:
        start = Path(fixture.start_document(Path(tmp), probe.start))
        baseline = Session.load(start, out_dir=Path(tmp))
        submitted = Session.load(Path(project) / fixture.START[probe.start],
                                 out_dir=Path(project).parent / "renders")
        result: Result = probe.check_at(level)(baseline, submitted)
    passed = bool(result.passed) and touched
    # an episode that changed nothing did none of the items, whatever the start
    # already satisfies (a clean control's "no false alarms")
    items = list(result.items) if touched else [(n, False) for n, _d in result.items]
    return ProbeReport(probe.id, passed, result.detail if touched else "no engine calls",
                       items, touched, pins_of(probe)[1])


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
        return grade(probe, project, bool(journal.get("touched", True)),
                     journal.get("level", "explicit")).to_dict()


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
        if task.level != config.level:
            raise ValueError(f"probe task {task.task_id} is posed at the {task.level} level, the "
                             f"episode runs at {config.level}: build it with "
                             "task_from_entry(row, level=...)")
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
            # the tool names, before the episode's own server exists
            names = {t["name"] for t in RoadDraftMCP(
                Session(), attachments=tmp if "--attachments" in self.probe.server_args
                else None).tools()}
        self.allowed = names | {"get_task_brief", "submit"} | (
            {"run_check"} if config.mode != "single" else set())
        self.brief_text = task.brief
        self.tools: List[dict] = []
        self.turns: List[dict] = []
        self.termination = None
        self.budget_tripped = None
        self.error = None
        self.submit_note = ""
        self.implicit_submit = False
        self.invalid_calls = 0
        self.repaired_calls = 0
        self._schemas: Dict[str, dict] = {}
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
        self.tools = sorted(defs, key=lambda d: d["name"])
        self._schemas = {d["name"]: d["input_schema"] for d in self.tools}
        self.state = BudgetState()
        self.agent.reset(self.task, self.config.level, self.config.mode)
        self.agent.begin(begin_context(self, system=system_prompt(self.config.mode, self.budgets)))
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
        pins = self.pins or {}
        generator, verifier = pins_of(self.probe)
        return {"type": "header", "run_id": self.config.run_id, "task_id": self.task.task_id,
                "task_type": self.task.task_type, "sheets": 1, "seed": None,
                "probe": self.probe.id, "start": self.probe.start,
                "spec_version": SPEC_VERSION, "spec_hash": spec_hash(),
                "generator_version": generator, "verifier_version": verifier,
                "harness_version": HARNESS_VERSION,
                **prompt_fields(self.brief_text, self.config.system_extra),
                "git_commit": pins.get("commit"),
                "dirty": pins.get("dirty"),
                "tools_sha256": _hash(json.dumps(self.tools, sort_keys=True)),
                **self.agent.describe(), "agent": self.agent.name,
                "dialect": self.config.dialect, "mode": self.config.mode,
                "level": self.config.level, "sample": self.config.sample,
                "scope": self.scope, "budgets": self.budgets.to_dict(),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    def _execute(self, call: ToolCall) -> dict:   # under Episode.execute's harness-failure guard (2026-10-28)
        name, params = call.name, call.params or {}
        images = None
        if name not in self.allowed:
            hint = ("tools in this task: "
                    + ", ".join(sorted(self.allowed)))
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
            params, repairs = repair_params(params, self._schemas.get(name))
            result, shown = _reply(self.mcp.call_tool(name, params))
            self.engine_calls += 1
            if notes or repairs:
                result["warnings"] = list(result.get("warnings") or []) + notes + repairs
            if name == "view_attachment" or (name in RENDER_QUERIES
                                              and self.config.mode == "vision"):
                images = shown or None
            elif shown:
                result["note"] = ("the image is on disk at 'path'; it is not returned "
                                  "inline in this mode")
            result, _ = self._shape_result(name, result)
            if repairs:   # on the record whole, past the result cap: the report counts it
                result = dict(result, repaired=repairs)
                self.repaired_calls += 1
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
            report = grade(self.probe, self.project, self.engine_calls > 0, self.config.level)
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
        report = grade(self.probe, self.project, touched, self.config.level)
        kept, rel = [], None
        if self.path is not None:
            dest = Path(self.out_root) / "projects" / Path(self.path).stem
            if dest.exists():
                shutil.rmtree(dest)
            kept = keep(self.project, self.probe, dest)
            rel = Path("..") / "projects" / Path(self.path).stem
        journal = {"type": "journal", "probe": self.probe.id, "start": self.probe.start,
                   "level": self.config.level,
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


__all__ = ["PILOT_SET", "DEV_SET", "SETS", "dev_probes", "probes_of", "set_of", "FAMILIES", "BUDGETS", "ProbeTask", "ProbeReport", "ProbeEpisode",
           "ProbeOracleAgent", "EpisodeServer", "pilots", "by_id", "entry", "task_id",
           "task_type", "brief_text", "levels_of", "generated", "generated_set", "pins_of", "generator_version", "current_ids", "check_sources",
           "check_version", "task_from_entry", "grade",
           "rescore", "keep", "oracle_calls", "system_prompt"]
