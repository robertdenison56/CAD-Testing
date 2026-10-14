"""Task sets (eval plan section 4.8): ``benchmarks/tasksets/<name>.json``
manifests, ``{"taskset", "generator_version", "spec_hash", "tasks": [{"seed",
"curves", "equations", "task_type", "sheets", "task_id"}]}``.

- ``d1-dev``: seeds 1-50, every dial mixed.  For iteration; never reported.
- ``d1-test``: seeds 1000-1099, held out, balanced over curves 1/2/3 and
  equations on/off, the task types and the sheet count cycling.  The
  leaderboard set.
- ``d1-variance``: the first 20 tasks of ``d1-test``, for k = 5 sampling.

The prompt level is a run dimension, not a task-set one.  A test regenerates
each manifest and asserts identical task ids: a changed spec or generator
fails it, which is the tripwire; ``python -m roaddraft.eval taskset --write``
regenerates them once the change is meant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from roaddraft.tasks.brief import GENERATOR_VERSION, Task
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.types import TASK_TYPES

REPO = Path(__file__).resolve().parents[3]
TASKSETS_DIR = REPO / "benchmarks" / "tasksets"
NAMES = ("d1-dev", "d1-test", "d1-variance")
SEEDED_TYPES = tuple(sorted(TASK_TYPES))
CURVES = (1, 2, 3)
VARIANCE_SIZE = 20


def dials(index: int) -> dict:
    """The dials of the ``index``-th task of a set: curves cycle 1, 2, 3;
    equations flip every three; the sheet count flips every six; the task
    type cycles through the seeded types."""
    return {"curves": CURVES[index % len(CURVES)],
            "equations": bool((index // len(CURVES)) % 2),
            "sheets": 1 + (index // (2 * len(CURVES))) % 2,
            "task_type": SEEDED_TYPES[index % len(SEEDED_TYPES)]}


def make_task(seed: int, curves: int, equations: bool, task_type: str, sheets: int) -> Task:
    return generate_task(seed, curves=curves, equations=equations, task_type=task_type,
                         sheets=sheets)


def _entry(seed: int, index: int) -> dict:
    d = dials(index)
    # a type the seed cannot make (a widths task with no dimensionable tangent)
    # takes the next type in the cycle, so every seed stays in the set
    start = SEEDED_TYPES.index(d["task_type"])
    # a seed the generator cannot lay out on two sheets (its own assertion) takes
    # one sheet, so every seed stays in the set; the entry records the fallback
    for sheets in ((d["sheets"], 1) if d["sheets"] != 1 else (1,)):
        for k in range(len(SEEDED_TYPES)):
            ttype = SEEDED_TYPES[(start + k) % len(SEEDED_TYPES)]
            try:
                task = make_task(seed, d["curves"], d["equations"], ttype, sheets)
            except ValueError:
                continue
            except AssertionError:
                break
            entry = {"seed": seed, "curves": d["curves"], "equations": d["equations"],
                     "task_type": ttype, "sheets": sheets, "task_id": task.task_id}
            if ttype != d["task_type"] or sheets != d["sheets"]:
                entry["dialed"] = {"task_type": d["task_type"], "sheets": d["sheets"]}
            return entry
    raise RuntimeError(f"seed {seed}: no task type generates")


def build(name: str) -> dict:
    """Generate a manifest."""
    if name == "d1-dev":
        seeds = range(1, 51)
    elif name == "d1-test":
        seeds = range(1000, 1100)
    elif name == "d1-variance":
        manifest = build("d1-test")
        return {**manifest, "taskset": name, "parent": "d1-test",
                "tasks": manifest["tasks"][:VARIANCE_SIZE]}
    else:
        raise ValueError(f"unknown task set {name!r}; sets: {', '.join(NAMES)}")
    tasks = [_entry(seed, i) for i, seed in enumerate(seeds)]
    return {"taskset": name, "generator_version": GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "tasks": tasks}


def manifest_path(name: str, root=None) -> Path:
    return Path(root or TASKSETS_DIR) / f"{name}.json"


def write(name: str, root=None) -> Path:
    path = manifest_path(name, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(name), indent=1) + "\n")
    return path


def load(name: str, root=None) -> dict:
    path = manifest_path(name, root)
    if not path.exists():
        raise FileNotFoundError(f"no manifest for task set {name!r} at {path}; "
                                f"python -m roaddraft.eval taskset --write {name}")
    return json.loads(path.read_text())


def check(name: str, root=None) -> List[str]:
    """Differences between the committed manifest and a fresh build: empty
    when the spec and generator are the ones the manifest was written on."""
    saved, fresh = load(name, root), build(name)
    problems: List[str] = []
    for key in ("generator_version", "spec_hash"):
        if saved.get(key) != fresh.get(key):
            problems.append(f"{key}: manifest {saved.get(key)} != current {fresh.get(key)}")
    saved_ids = [t["task_id"] for t in saved["tasks"]]
    fresh_ids = [t["task_id"] for t in fresh["tasks"]]
    if saved_ids != fresh_ids:
        changed = sum(1 for a, b in zip(saved_ids, fresh_ids) if a != b) + abs(len(saved_ids) - len(fresh_ids))
        problems.append(f"task ids: {changed} of {len(fresh_ids)} differ")
    return problems


def task_from_entry(entry: dict, strict: bool = True) -> Task:
    """The task a manifest entry names; with ``strict`` its id must match."""
    task = make_task(entry["seed"], entry["curves"], entry["equations"], entry["task_type"],
                     entry["sheets"])
    if strict and task.task_id != entry["task_id"]:
        raise ValueError(f"task id of seed {entry['seed']} ({entry['task_type']}, "
                         f"{entry['sheets']} sheet) is {task.task_id}, the manifest says "
                         f"{entry['task_id']}: the spec or generator changed; regenerate with "
                         "python -m roaddraft.eval taskset --write")
    return task


def entries(name: str, limit: Optional[int] = None, task_ids: Optional[Iterable[str]] = None,
            root=None) -> List[dict]:
    """The manifest's entries, filtered to ``task_ids`` and cut to ``limit``."""
    rows = load(name, root)["tasks"]
    if task_ids:
        wanted = set(task_ids)
        rows = [r for r in rows if r["task_id"] in wanted]
    if limit is not None:
        rows = rows[:limit]
    return rows


__all__ = ["NAMES", "SEEDED_TYPES", "TASKSETS_DIR", "VARIANCE_SIZE", "dials", "make_task", "build",
           "manifest_path", "write", "load", "check", "task_from_entry", "entries"]
