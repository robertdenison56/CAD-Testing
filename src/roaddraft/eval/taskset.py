"""Task sets (eval plan section 4.8): ``benchmarks/tasksets/<name>.json``
manifests, ``{"taskset", "generator_version", "spec_hash", "tasks": [{"seed",
"curves", "equations", "task_type", "sheets", "task_id"}]}``.

- ``d1-dev``: seeds 1-50, every dial mixed.  For iteration; never reported.
- ``d1-test``: seeds 1000-1099, held out, balanced over curves 1/2/3 and
  equations on/off, the task types and the sheet count cycling.  The
  leaderboard set.
- ``d1-variance``: the first 20 tasks of ``d1-test``, for k = 5 sampling.
- ``d1-real``: 100 held-out tasks on the redrafted sample plan sheets
  (``examples/Exmple Plans/Redraft``), 25 from each of the four question
  groups of ``tasks.types.REAL_GROUPS`` (draft linework, letter alignment
  data, produce the sheet, notes and dimensions: the real-sheet counterpart of
  the probe board's tiers, decided 2026-10-24), the group's quota split as
  evenly as its types allow, drawn from the validated catalogue
  ``benchmarks/real_tasks/catalog.json`` (``scripts/real_tasks.py`` writes it).
  Within a type, every agency that has the type is drawn once before any is
  drawn again, then the sheet the set has used least.  Ranked beside
  ``d1-test``, with a column per group beside the blended score.  (Until
  2026-10-27 it was nine of each type, so two groups held 45 tasks and two
  held 9.)
- ``d1-real-dev``: 24 tasks, two of each real type, on a few Caltrans sheets
  that ``d1-real`` never uses.  For smoke runs and iteration, so it covers
  every type rather than balancing the groups; never reported.
- ``hard-pilots``: the 33 harder-task pilots (``probes/pilot``, all of them),
  run as probe tasks (``eval/probe_tasks.py``): each its own start project on a
  sample sheet, the MCP server's tools, graded pass or fail by its own check.
  Ranked on its own board.  Too few instances per family to spare a dev split.

The prompt level is a run dimension, not a task-set one.  A test regenerates
each manifest and asserts identical task ids: a changed spec or generator
fails it, which is the tripwire; ``python -m roaddraft.eval taskset --write``
regenerates them once the change is meant.  For the real sets the tripwire
also rebuilds every task from the redrafted sheets and checks its id, and
fails when the catalogue was validated under another verifier: rebuild it with
``python scripts/real_tasks.py`` first, then write the manifests.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from roaddraft.tasks.brief import GENERATOR_VERSION, Task
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.types import REAL_GROUPS, REAL_TASK_TYPES, TASK_TYPES, real_group

REPO = Path(__file__).resolve().parents[3]
TASKSETS_DIR = REPO / "benchmarks" / "tasksets"
#: the sets the seeded generator makes, one synthetic centerline per task
SEEDED_NAMES = ("d1-dev", "d1-test", "d1-variance")
#: the sets on the redrafted sample plan sheets
REAL_NAMES = ("d1-real", "d1-real-dev")
#: the sets of probe tasks, each graded by its probe's own check (eval/probe_tasks.py)
PROBE_NAMES = ("hard-pilots",)
NAMES = SEEDED_NAMES + REAL_NAMES + PROBE_NAMES
#: the validated real-sheet tasks the real sets are drawn from
REAL_CATALOG = REPO / "benchmarks" / "real_tasks" / "catalog.json"
#: tasks of each question group (tasks.types.REAL_GROUPS) in d1-real, and of each
#: real type in d1-real-dev
REAL_PER_GROUP = 25
REAL_DEV_PER_TYPE = 2
#: the agency the dev sheets are taken from: the only one with sheets to spare
#: (WFL has 6 sheets, FDOT 3, CFL 1; every one of them stays in d1-real)
REAL_DEV_AGENCY = "Caltrans-PPM"
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


def is_real(name: str) -> bool:
    """Whether ``name`` is a set on the redrafted sample sheets."""
    return name in REAL_NAMES


def is_probe(name: str) -> bool:
    """Whether ``name`` is a set of probe tasks."""
    return name in PROBE_NAMES


def current_generator(name: Optional[str]) -> str:
    """The generator version a run on ``name`` is held to: the seeded
    generator's, the real-sheet builder's, or the probe set's own hash."""
    if name is not None and is_real(name):
        from roaddraft.tasks.real import REAL_GENERATOR_VERSION
        return REAL_GENERATOR_VERSION
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.generator_version()
    return GENERATOR_VERSION


def current_verifier(name: Optional[str]) -> str:
    """The verifier version a run on ``name`` is held to: the D1 verifier's,
    or, for a probe set, the pilot checks' source hash
    (``probe_tasks.check_version``), since a pilot is graded by its own check."""
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.check_version()
    from roaddraft.verify import VERIFIER_VERSION
    return VERIFIER_VERSION


def default_budgets(name: Optional[str]):
    """The budgets a run on ``name`` takes when it sets none: Track P's for the
    probe tasks (eval/probe_tasks.BUDGETS), the harness's otherwise."""
    from roaddraft.eval.budget import Budgets
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.BUDGETS
    return Budgets()


def build_probes(name: str) -> dict:
    """A probe set's manifest: every pilot, in the brainstorm's order."""
    from roaddraft.eval import probe_tasks
    if name != probe_tasks.PILOT_SET:
        raise ValueError(f"unknown probe task set {name!r}; sets: {', '.join(PROBE_NAMES)}")
    probes = probe_tasks.pilots()
    return {"taskset": name, "generator_version": probe_tasks.generator_version(probes),
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "source": "src/roaddraft/probes/pilot (docs/Probes_Pilots.md)",
            "grading": "each probe's own check, pass = 100, fail = 0",
            "tasks": [probe_tasks.entry(p) for p in probes]}


def _h(text: str) -> str:
    """A fixed order that is not the catalogue's own (which runs sheet by sheet)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_catalog(path=None) -> dict:
    """The real-task catalogue (``scripts/real_tasks.py`` writes it)."""
    path = Path(path or REAL_CATALOG)
    if not path.exists():
        raise FileNotFoundError(f"no real-task catalogue at {path}; python scripts/real_tasks.py")
    return json.loads(path.read_text())


def real_dev_sheets(tasks: Sequence[dict]) -> List[str]:
    """The sheets ``d1-real-dev`` is drawn from: Caltrans sheets in a fixed
    hashed order, each one taken while it adds a type still short of
    ``REAL_DEV_PER_TYPE`` tasks, until every real type has that many.  No
    other sheet is in d1-real-dev, and none of these is in d1-real."""
    by_sheet: Dict[str, Counter] = {}
    for t in tasks:
        if t["agency"] == REAL_DEV_AGENCY:
            by_sheet.setdefault(t["sheet_id"], Counter())[t["type"]] += 1
    have: Counter = Counter()
    picked: List[str] = []
    for sheet in sorted(by_sheet, key=_h):
        if all(have[ty] >= REAL_DEV_PER_TYPE for ty in REAL_TASK_TYPES):
            break
        if any(have[ty] < REAL_DEV_PER_TYPE for ty in by_sheet[sheet]):
            picked.append(sheet)
            have.update(by_sheet[sheet])
    short = [ty for ty in REAL_TASK_TYPES if have[ty] < REAL_DEV_PER_TYPE]
    if short:
        raise RuntimeError(f"the {REAL_DEV_AGENCY} sheets cannot give {REAL_DEV_PER_TYPE} tasks "
                           f"of {', '.join(short)}")
    return sorted(picked)


def real_quotas(per_group: int = REAL_PER_GROUP) -> Dict[str, int]:
    """How many tasks of each real type ``d1-real`` draws: ``per_group`` for
    every question group that has types (``REAL_GROUPS``), split as evenly as
    the group's types allow, the first types of the group taking the
    remainder.  So the blended score weighs every question type the same,
    whatever the number of types each holds, and a type added to a group
    shares the group's quota rather than growing the set."""
    quotas: Dict[str, int] = {}
    for _, _, types in REAL_GROUPS:
        if not types:
            continue
        base, extra = divmod(per_group, len(types))
        for i, ty in enumerate(types):
            quotas[ty] = base + (1 if i < extra else 0)
    return {ty: quotas[ty] for ty in REAL_TASK_TYPES if ty in quotas}


def _pick(pool: Sequence[dict], quotas: Dict[str, int]) -> List[dict]:
    """``quotas[type]`` tasks of each real type from ``pool``, picked round by
    round over the types in ``REAL_TASK_TYPES`` order (every type still owed
    a task gets one before any type gets its next).  Within a type, an agency
    the type has not drawn yet comes first, then the sheet the set has used
    least so far, then the hashed task id.  So a set holds every agency's
    sheets wherever the agency has the type, and spreads over sheets instead
    of taking one sheet's whole catalogue."""
    by_type = {ty: sorted((t for t in pool if t["type"] == ty), key=lambda t: _h(t["task_id"]))
               for ty in REAL_TASK_TYPES}
    for ty, rows in by_type.items():
        if len(rows) < quotas.get(ty, 0):
            raise RuntimeError(f"{ty}: {len(rows)} tasks to draw from, {quotas[ty]} wanted")
    used_sheet: Counter = Counter()
    used_agency = {ty: Counter() for ty in REAL_TASK_TYPES}
    taken = set()
    out: List[dict] = []
    for round_ in range(max(quotas.values(), default=0)):
        for ty in REAL_TASK_TYPES:
            if round_ >= quotas.get(ty, 0):
                continue
            best = min((t for t in by_type[ty] if t["task_id"] not in taken),
                       key=lambda t: (min(used_agency[ty][t["agency"]], 1),
                                      used_sheet[t["sheet_id"]], _h(t["task_id"])))
            taken.add(best["task_id"])
            used_sheet[best["sheet_id"]] += 1
            used_agency[ty][best["agency"]] += 1
            out.append(best)
    return out


def _real_entry(t: dict) -> dict:
    return {"agency": t["agency"], "sheet_id": t["sheet_id"], "sheet": t["sheet"],
            "alignment": t["alignment"], "task_type": t["type"], "group": real_group(t["type"]),
            "sheets": 1, "feet_per_inch": t["feet_per_inch"], "twist_deg": t["twist_deg"],
            "task_id": t["task_id"]}


def build_real(name: str, catalog_path=None) -> dict:
    """A real set's manifest, drawn from the catalogue."""
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    cat = load_catalog(catalog_path)
    tasks = cat["tasks"]
    dev = set(real_dev_sheets(tasks))
    if name == "d1-real":
        chosen = _pick([t for t in tasks if t["sheet_id"] not in dev], real_quotas())
    elif name == "d1-real-dev":
        chosen = _pick([t for t in tasks if t["sheet_id"] in dev],
                       {ty: REAL_DEV_PER_TYPE for ty in REAL_TASK_TYPES})
    else:
        raise ValueError(f"unknown real task set {name!r}; sets: {', '.join(REAL_NAMES)}")
    entries = [_real_entry(t) for t in chosen]
    groups = Counter(e["group"] for e in entries)
    return {"taskset": name, "generator_version": REAL_GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "source": "benchmarks/real_tasks/catalog.json",
            "catalog_verifier": cat.get("verifier_version"),
            "groups": {key: groups[key] for key, _, _ in REAL_GROUPS if groups[key]},
            "tasks": entries}


def build(name: str) -> dict:
    """Generate a manifest."""
    if is_real(name):
        return build_real(name)
    if is_probe(name):
        return build_probes(name)
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
    keys = ("generator_version", "spec_hash") + (("catalog_verifier",) if is_real(name) else ())
    for key in keys:
        if saved.get(key) != fresh.get(key):
            problems.append(f"{key}: manifest {saved.get(key)} != current {fresh.get(key)}")
    saved_ids = [t["task_id"] for t in saved["tasks"]]
    fresh_ids = [t["task_id"] for t in fresh["tasks"]]
    if saved_ids != fresh_ids:
        changed = sum(1 for a, b in zip(saved_ids, fresh_ids) if a != b) + abs(len(saved_ids) - len(fresh_ids))
        problems.append(f"task ids: {changed} of {len(fresh_ids)} differ")
    if is_real(name):
        problems += _check_real(saved)
    return problems


def _check_real(saved: dict) -> List[str]:
    """A real set's own tripwire: the catalogue it was drawn from is current
    (its generator, spec and the verifier it was validated under), and every
    task still builds to its id from the redrafted sheets."""
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    from roaddraft.verify import VERIFIER_VERSION
    cat = load_catalog()
    problems: List[str] = []
    for key, now in (("generator_version", REAL_GENERATOR_VERSION),
                     ("spec_hash", spec_hash(DRAFTING_SPEC_V1)),
                     ("verifier_version", VERIFIER_VERSION)):
        if cat.get(key) != now:
            problems.append(f"the catalogue's {key} is {cat.get(key)}, current {now}: rebuild it "
                            "(python scripts/real_tasks.py), then write the manifests")
    broken = []
    for entry in saved["tasks"]:
        try:
            task_from_entry(entry)
        except ValueError as why:
            broken.append(f"{entry['task_type']} on {entry['sheet_id']} {entry['alignment']}: {why}")
    if broken:
        problems.append(f"{len(broken)} of {len(saved['tasks'])} tasks no longer build to their "
                        f"ids; first: {broken[0]}")
    return problems


def task_from_entry(entry: dict, strict: bool = True) -> Task:
    """The task a manifest entry names; with ``strict`` its id must match.  A
    real-sheet entry (it names a ``sheet_id``) is rebuilt from the redrafted
    sheet by ``tasks.real.build_real_task``; a probe entry (it names a
    ``probe``) is a ``probe_tasks.ProbeTask``, not a ``Task``."""
    if "probe" in entry:
        from roaddraft.eval import probe_tasks
        return probe_tasks.task_from_entry(entry, strict=strict)
    if "sheet_id" in entry:
        from roaddraft.tasks.real import build_real_task
        task = build_real_task(entry["sheet_id"], entry["alignment"], entry["task_type"])
        if strict and task.task_id != entry["task_id"]:
            raise ValueError(f"task id of {entry['task_type']} on {entry['sheet_id']} "
                             f"{entry['alignment']} is {task.task_id}, the manifest says "
                             f"{entry['task_id']}: the redrafts, spec or real generator changed; "
                             "rebuild the catalogue (python scripts/real_tasks.py), then "
                             "python -m roaddraft.eval taskset --write")
        return task
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


__all__ = ["NAMES", "SEEDED_NAMES", "REAL_NAMES", "REAL_CATALOG", "REAL_PER_GROUP",
           "REAL_DEV_PER_TYPE", "SEEDED_TYPES", "TASKSETS_DIR", "VARIANCE_SIZE", "dials",
           "make_task", "is_real", "is_probe", "current_generator", "current_verifier", "default_budgets",
           "build_probes", "PROBE_NAMES", "load_catalog", "real_dev_sheets", "real_quotas", "build_real", "build",
           "manifest_path", "write", "load", "check", "task_from_entry", "entries"]
