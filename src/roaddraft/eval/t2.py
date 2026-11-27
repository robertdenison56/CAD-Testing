"""Stage T2's task sets (``RoadDraft_Training_Plan.md`` §3, *the subject's own
passes*; §4, stage T2): "sample the T1 checkpoint on fresh training seeds
weighted to the types it still fails, keep the 100s, retrain from base".

This module plans a round's manifest from a checkpoint's finished run.  The
keep rule is the converter's (``trajectories.conversations``, ``rollouts``);
the runbook is ``benchmarks/training/T2.md``.

**What a T2 task is.**  The same kind of task the eight D1 training sets hold,
built by their own entry builders (``eval.taskset``) on a seed none of them
draws.  A *cell* is a training flavour and a task type: ``plain`` (``d1-train``),
``hard``, ``twist``, ``crowd``, ``revise``, ``twist-widths``, ``revise-base``
and ``breaks``, each over the types its dials cycle through (42 cells).  A
cell's ``k``-th task takes the ``k``-th index of its set's dial cycle that
dials the cell's type, so the curve count, the equation, the sheet count, the
twist and the kind of revision turn as they do in the set.

**What is read from the run** (``observe``).  Every finished episode of the run
folder that did not end in a harness or provider error: its task type from the
header, its flavour from the set it ran on (``d1-dev`` and ``d1-train`` are
``plain``, each training set its own, a T2 manifest's entries say theirs), and
whether it is a *miss*: an effective score under 100 as the episode ended, the
complement of what the keep rule keeps.  A run on a held-out set is refused:
what a model does on ``d1-test`` does not shape what it is trained on.

**The weighting** (``plan``).  A cell's miss rate is its misses over its
episodes, shrunk toward a prior worth ``PRIOR_STRENGTH`` episodes: the miss
rate of the same task type in the run's other flavours, itself shrunk the
same way toward the run's overall rate (which it is when no other flavour of
the run held the type).  A cell the run never met takes the prior alone, and
the table says which (``source``: ``run``, ``type`` or ``overall``).  A
cell's weight is

    floor * base + (1 - floor) * base * rate / sum(base * rate)

where ``base`` is the cell's share of the eight training manifests.  So a run
that passes everything, or fails everything, draws the training sets' own mix;
otherwise ``1 - floor`` of the round follows the misses, and no cell falls
under ``floor`` times its training share.  Counts are whole tasks: one for
every cell when the round holds that many, the rest by weight, largest
remainder first.

**Seeds.**  ``taskset.T2_SEEDS`` (21000-22999), a thousand a round
(``taskset.t2_round_seeds``).  Tasks take the round's seeds in order, the cells
in turn; a seed the cell's builder cannot make its type of is left out and
named under ``skipped_seeds``.

Everything is a function of the run's per-cell counts, the round, the size and
the floor: the manifest carries them (``t2``), and ``check`` plans and builds
it again from its own record.  A manifest is written only by ``python -m
roaddraft.eval t2 plan`` and only when ``taskset.t2_overlap`` finds nothing
shared with any other set.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.brief import GENERATOR_VERSION
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash

T2_VERSION = "t2-v1"
#: the share of a round that keeps the training sets' own mix whatever the run failed
FLOOR = 0.25
#: episodes the prior of a cell's miss rate is worth
PRIOR_STRENGTH = 2.0
#: a round's default size
SIZE = 600
#: every dial cycle of ``eval.taskset`` repeats within this many indices
PERIOD = 720


@dataclass(frozen=True)
class Flavour:
    """One kind of training task: the set that holds it, the dials of that
    set's ``index``-th task and the builder of its ``index``-th entry."""
    name: str
    taskset: str
    dials: Callable[[int], dict]
    entry: Callable[[int, int], dict]


def _twist_entry(seed: int, index: int) -> dict:
    return tasksets._entry(seed, index, twist=True)


FLAVOURS: Tuple[Flavour, ...] = (
    Flavour("plain", "d1-train", tasksets.dials, tasksets._entry),
    Flavour("hard", "d1-train-hard", tasksets.hard_dials, tasksets._hard_entry),
    Flavour("twist", "d1-train-twist", tasksets.twist_dials, _twist_entry),
    Flavour("crowd", "d1-train-crowd", tasksets.crowd_dials, tasksets._crowd_entry),
    Flavour("revise", "d1-train-revise", tasksets.revise_dials, tasksets._revise_entry),
    Flavour("twist-widths", "d1-train-twist-widths", tasksets.twist_width_dials,
            tasksets._twist_width_entry),
    Flavour("revise-base", "d1-train-revise-base", tasksets.revise_base_dials,
            tasksets._revise_base_entry),
    Flavour("breaks", "d1-train-breaks", tasksets.breaks_dials, tasksets._breaks_entry),
    Flavour("bulk", "d1-train-bulk", tasksets.bulk_dials, tasksets._bulk_entry),
)
FLAVOUR = {f.name: f for f in FLAVOURS}
assert {f.taskset for f in FLAVOURS} == set(tasksets.TRAIN_NAMES), "a training set has no T2 flavour"
#: the flavour of every task of a set a T2 round may be planned from; a T2 manifest's
#: entries carry their own.  No held-out board set is here, and none is taken.
SET_FLAVOUR = {"d1-dev": "plain", **{f.taskset: f.name for f in FLAVOURS}}

Cell = Tuple[str, str]   # (flavour, task type)


def indices(flavour: str, task_type: str) -> List[int]:
    """The indices of one period of the flavour's dial cycle that dial ``task_type``."""
    f = FLAVOUR[flavour]
    return [i for i in range(PERIOD) if f.dials(i)["task_type"] == task_type]


def nth_index(flavour: str, task_type: str, k: int) -> int:
    """The ``k``-th index of the flavour's dial cycle that dials ``task_type``."""
    hits = indices(flavour, task_type)
    if not hits:
        raise ValueError(f"the {flavour} dials never give a {task_type} task")
    return hits[k % len(hits)] + PERIOD * (k // len(hits))


def base_counts() -> Dict[Cell, int]:
    """Tasks of each cell in the eight D1 training manifests, in the flavours'
    order and each flavour's types by name: the mix a round keeps where the run
    says nothing.  A type a set's dials name and its manifest never holds is
    no cell."""
    out: Dict[Cell, int] = {}
    for f in FLAVOURS:
        held = Counter(e["task_type"] for e in tasksets.load(f.taskset)["tasks"])
        for ttype in sorted({f.dials(i)["task_type"] for i in range(PERIOD)}):
            if held[ttype]:
                out[(f.name, ttype)] = held[ttype]
    return out


# ------------------------------------------------------------ the run

def _run_meta(run_dir: Path) -> dict:
    path = run_dir / "run.json"
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def _flavours_of(taskset: Optional[str], run_dir: Path, meta: dict, root=None) -> Callable[[str], Optional[str]]:
    """task id -> flavour, for a run on ``taskset``; ``ValueError`` for a set
    no round is planned from."""
    if taskset in SET_FLAVOUR:
        flavour = SET_FLAVOUR[taskset]
        return lambda task_id: flavour
    if tasksets.is_t2(taskset):
        where = root or (meta.get("spec") or {}).get("tasksets_root")
        by_id = {e["task_id"]: e.get("flavour") for e in tasksets.load(taskset, where)["tasks"]}
        return by_id.get
    allowed = ", ".join(sorted(SET_FLAVOUR))
    if taskset in tasksets.NAMES:
        raise ValueError(f"{run_dir}: a run on {taskset}, a held-out set; a round is planned from "
                         f"a run on {allowed} or an earlier round's manifest, never from a set "
                         "the checkpoint is scored on")
    raise ValueError(f"{run_dir}: a run on {taskset or 'no named task set'} (run.json); a round is "
                     f"planned from a run on {allowed} or an earlier round's manifest")


def observe(run_dirs: Iterable, level: Optional[str] = None, root=None) -> dict:
    """What the run folders say of each cell: ``{"runs": [...], "cells":
    [{"flavour", "task_type", "n", "misses"}]}``, the cells by name.  An
    episode counts when it has an end record and did not end in an error;
    ``level`` keeps one prompt level's episodes."""
    counts: Dict[Cell, List[int]] = {}
    runs = []
    for rd in run_dirs:
        run_dir = Path(rd)
        files = sorted((run_dir / "episodes").glob("*.jsonl"))
        if not files:
            raise FileNotFoundError(f"{run_dir}: no episodes under {run_dir / 'episodes'}")
        meta = _run_meta(run_dir)
        taskset = (meta.get("spec") or {}).get("taskset")
        flavour_of = _flavours_of(taskset, run_dir, meta, root)
        row = {"run_id": run_dir.name, "taskset": taskset, "agents": set(), "levels": set(),
               "episodes": 0, "misses": 0, "errors": 0, "unfinished": 0, "other_level": 0,
               "unplaced": 0}
        for path in files:
            try:
                rec = read_episode(path)
            except (OSError, ValueError):
                row["unfinished"] += 1
                continue
            header, end = rec["header"], rec["end"]
            if header is None or end is None:
                row["unfinished"] += 1
                continue
            if level is not None and header.get("level", "explicit") != level:
                row["other_level"] += 1
                continue
            if (end.get("termination") or "unknown") == "error":
                row["errors"] += 1
                continue
            flavour, ttype = flavour_of(header.get("task_id")), header.get("task_type")
            if not flavour or not ttype:
                row["unplaced"] += 1   # a task its manifest no longer holds
                continue
            miss = float(end.get("effective_score") or 0.0) < 100.0
            cell = counts.setdefault((flavour, str(ttype)), [0, 0])
            cell[0] += 1
            cell[1] += int(miss)
            row["episodes"] += 1
            row["misses"] += int(miss)
            row["agents"].add(str(header.get("model") or header.get("agent")))
            row["levels"].add(header.get("level", "explicit"))
        row["agents"], row["levels"] = sorted(row["agents"]), sorted(row["levels"])
        runs.append(row)
    return {"runs": runs,
            "cells": [{"flavour": f, "task_type": t, "n": n, "misses": m}
                      for (f, t), (n, m) in sorted(counts.items())]}


# ------------------------------------------------------------ the plan

def allocate(weights: Sequence[float], size: int) -> List[int]:
    """``size`` whole tasks over cells weighing ``weights`` (they sum to 1):
    one for every cell when ``size`` holds that many, the rest by weight, the
    largest remainders first and the earlier cell on a tie."""
    n = len(weights)
    if size < 0:
        raise ValueError(f"a round of {size} tasks")
    each = 1 if size >= n else 0
    rest = size - each * n
    quotas = [w * rest for w in weights]
    counts = [int(q) for q in quotas]
    order = sorted(range(n), key=lambda i: (-(quotas[i] - counts[i]), i))
    for i in order[:rest - sum(counts)]:
        counts[i] += 1
    return [each + c for c in counts]


def plan(observed: Sequence[dict], round_: int, size: int = SIZE, floor: float = FLOOR,
         flavours: Optional[Sequence[str]] = None) -> dict:
    """The round's type table from the run's per-cell counts (``observe``'s
    ``cells``): each cell's episodes and misses, its miss rate and where that
    came from, its training share, its weight and its count."""
    if not 0.0 <= floor <= 1.0:
        raise ValueError(f"floor {floor}: a share between 0 and 1")
    seeds = tasksets.t2_round_seeds(round_)
    base = base_counts()
    if flavours:
        unknown = sorted(set(flavours) - set(FLAVOUR))
        if unknown:
            raise ValueError(f"unknown flavour(s) {', '.join(unknown)}; flavours: {', '.join(FLAVOUR)}")
        base = {c: n for c, n in base.items() if c[0] in set(flavours)}
    seen = {(r["flavour"], r["task_type"]): (int(r["n"]), int(r["misses"])) for r in observed}
    total_n = sum(n for n, _ in seen.values())
    total_m = sum(m for _, m in seen.values())
    if not total_n:
        raise ValueError("the run holds no finished episode to read a miss rate from")
    overall = total_m / total_n
    rows = []
    for cell in base:
        n, m = seen.get(cell, (0, 0))
        # the same type in the run's other flavours, else the whole run
        other_n = sum(k for (f, t), (k, _) in seen.items() if t == cell[1] and f != cell[0])
        other_m = sum(j for (f, t), (_, j) in seen.items() if t == cell[1] and f != cell[0])
        prior = (other_m + PRIOR_STRENGTH * overall) / (other_n + PRIOR_STRENGTH)
        prior_from = "type" if other_n else "overall"
        rate = (m + PRIOR_STRENGTH * prior) / (n + PRIOR_STRENGTH)
        rows.append({"flavour": cell[0], "task_type": cell[1], "n": n, "misses": m,
                     "source": "run" if n else prior_from, "prior": prior, "miss_rate": rate,
                     "base": base[cell] / sum(base.values())})
    pull = sum(r["base"] * r["miss_rate"] for r in rows)
    for r in rows:
        r["weight"] = (floor * r["base"] + (1.0 - floor) * r["base"] * r["miss_rate"] / pull
                       if pull > 0 else r["base"])
    for r, count in zip(rows, allocate([r["weight"] for r in rows], int(size))):
        r["count"] = count
        r["expected_kept"] = count * (1.0 - r["miss_rate"])
    for r in rows:
        for key in ("prior", "miss_rate", "base", "weight"):
            r[key] = round(r[key], 6)
        r["expected_kept"] = round(r["expected_kept"], 2)
    return {"version": T2_VERSION, "round": int(round_), "size": int(size), "floor": floor,
            "prior_strength": PRIOR_STRENGTH, "seeds": [seeds.start, seeds.stop - 1],
            "flavours": list(flavours) if flavours else None,
            "observed": {"episodes": total_n, "misses": total_m, "miss_rate": round(overall, 6)},
            # the run's counts as read, the cells no flavour here holds among them: what the
            # table is a function of, and what ``check`` plans it from again
            "observed_cells": [{"flavour": f, "task_type": t, "n": n, "misses": m}
                               for (f, t), (n, m) in sorted(seen.items())],
            "cells": rows}


def render_table(p: dict) -> str:
    """The type table of a plan, as the CLI prints it."""
    o = p["observed"]
    lines = [f"round {p['round']}: {p['size']} tasks on seeds {p['seeds'][0]}-{p['seeds'][1]}, "
             f"floor {p['floor']:g}; the run: {o['misses']} of {o['episodes']} episodes under 100 "
             f"({o['miss_rate']:.1%})",
             f"{'flavour':13s} {'type':20s} {'run n':>5s} {'miss':>5s} {'miss rate':>9s} {'from':7s} "
             f"{'train':>6s} {'weight':>6s} {'count':>5s} {'kept (est.)':>11s}"]
    for r in p["cells"]:
        lines.append(f"{r['flavour']:13s} {r['task_type']:20s} {r['n']:5d} {r['misses']:5d} "
                     f"{r['miss_rate']:9.1%} {r['source']:7s} {r['base']:6.1%} {r['weight']:6.1%} "
                     f"{r['count']:5d} {r['expected_kept']:11.1f}")
    kept = sum(r["expected_kept"] for r in p["cells"])
    lines.append(f"{'all':13s} {'':20s} {o['episodes']:5d} {o['misses']:5d} {o['miss_rate']:9.1%} "
                 f"{'':7s} {1:6.1%} {1:6.1%} {sum(r['count'] for r in p['cells']):5d} {kept:11.1f}")
    lines.append("miss rate: measured where 'from' is run (the cell's own episodes, shrunk toward the "
                 "same type elsewhere in the run and the run's overall rate); where it is type or "
                 "overall the run never met the cell and the rate is that prior alone, an estimate. "
                 "kept (est.) is count x (1 - miss rate), an estimate.")
    return "\n".join(lines)


# ------------------------------------------------------------ the manifest

def build(name: str, p: dict, runs: Optional[Sequence[dict]] = None) -> dict:
    """The manifest of plan ``p``: its tasks on the round's seeds in order, the
    cells in turn (every cell still owed a task takes one before any takes its
    next).  A seed whose task cannot be the cell's type is left out and named."""
    if not tasksets.is_t2(name):
        raise ValueError(f"{name!r} is not a T2 set name ({tasksets.T2_PREFIX}<tag>)")
    for taken in tasksets.NAMES + tasksets.TRAIN_NAMES + tasksets.PROBE_TRAIN_NAMES:
        if name == taken:   # (no such name has the prefix; held all the same)
            raise ValueError(f"{name} is an existing set")
    seeds = iter(tasksets.t2_round_seeds(p["round"]))
    cells = p["cells"]
    tasks, skipped = [], []
    for k in range(max((c["count"] for c in cells), default=0)):
        for c in cells:
            if k >= c["count"]:
                continue
            flavour = FLAVOUR[c["flavour"]]
            index = nth_index(c["flavour"], c["task_type"], k)
            while True:
                seed = next(seeds, None)
                if seed is None:
                    lo, hi = p["seeds"]
                    raise ValueError(f"round {p['round']}'s seeds {lo}-{hi} ran out after "
                                     f"{len(tasks)} of {p['size']} tasks ({len(skipped)} seeds made "
                                     "no task of the type wanted): plan a smaller round")
                try:
                    entry = flavour.entry(seed, index)
                except RuntimeError:
                    skipped.append(seed)
                    continue
                if entry["task_type"] != c["task_type"]:
                    skipped.append(seed)   # the builder fell to another type: not this cell's task
                    continue
                tasks.append({**entry, "flavour": c["flavour"]})
                break
    record = dict(p)
    if runs is not None:
        record["runs"] = [dict(r) for r in runs]
    return {"taskset": name, "generator_version": GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "use": "training rollouts (stage T2): sampled by a checkpoint, kept at 100; never scored "
                   "for a board",
            "t2": record, "skipped_seeds": skipped, "tasks": tasks}


def text(manifest: dict) -> str:
    return json.dumps(manifest, indent=1) + "\n"


def write(manifest: dict, root=None, force: bool = False) -> Path:
    """Write a T2 manifest under ``root`` (default ``benchmarks/tasksets``).
    Refused (``ValueError``) when it shares anything with another set
    (``taskset.t2_overlap``), or when another manifest of its name is there
    and ``force`` is not given: a round's manifest names the tasks its
    rollouts ran on."""
    name = manifest["taskset"]
    if not tasksets.is_t2(name):
        raise ValueError(f"{name!r} is not a T2 set name ({tasksets.T2_PREFIX}<tag>)")
    problems = tasksets.t2_overlap(manifest, root)
    if problems:
        raise ValueError(f"{name} is not written: " + "; ".join(problems))
    path = tasksets.manifest_path(name, root)
    body = text(manifest)
    if path.exists() and path.read_text() != body and not force:
        raise ValueError(f"{path} holds another manifest of that name; a round's rollouts are held "
                         "to the manifest they ran on: plan under a new --name, or pass --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def check(name: str, root=None) -> List[str]:
    """What is wrong with the T2 manifest ``name`` on disk: a spec or
    generator it was not written on, a task list its own record does not
    plan and build again, or anything shared with another set.  Empty when it
    is current and clean."""
    saved = tasksets.load(name, root)
    problems: List[str] = []
    for key, now in (("generator_version", GENERATOR_VERSION),
                     ("spec_hash", spec_hash(DRAFTING_SPEC_V1))):
        if saved.get(key) != now:
            problems.append(f"{key}: manifest {saved.get(key)} != current {now}")
    record = saved.get("t2") or {}
    try:
        again = plan(record.get("observed_cells") or [], record.get("round"), record.get("size"),
                     record.get("floor", FLOOR), record.get("flavours"))
        fresh = build(name, again)
    except (ValueError, TypeError) as why:
        problems.append(f"its record does not plan again: {why}")
    else:
        planned = [(c["flavour"], c["task_type"], c["count"]) for c in again["cells"]]
        if planned != [(c["flavour"], c["task_type"], c["count"]) for c in record["cells"]]:
            problems.append("its record plans other counts now (the training manifests or the "
                            "weighting changed)")
        a, b = [t["task_id"] for t in saved["tasks"]], [t["task_id"] for t in fresh["tasks"]]
        if a != b:
            changed = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            problems.append(f"task ids: {changed} of {len(b)} differ")
    return problems + tasksets.t2_overlap(saved, root)


# ------------------------------------------------------------ CLI

def add_parser(subs) -> None:
    """``python -m roaddraft.eval t2 plan|check``."""
    p = subs.add_parser("t2", help="stage T2: a round's task set, planned from a checkpoint's run")
    sub = p.add_subparsers(dest="t2_command", required=True)
    q = sub.add_parser("plan", help="the type table of a round from a run, and its manifest")
    q.add_argument("run_dirs", nargs="+", help="run folder(s) of the checkpoint, results/<run_id>: "
                                               f"on {', '.join(sorted(SET_FLAVOUR))} or an earlier round")
    q.add_argument("--round", type=int, required=True, dest="round_",
                   help="1, 2, ...: the round's own thousand seeds")
    q.add_argument("--size", type=int, default=SIZE, help=f"tasks in the round (default {SIZE})")
    q.add_argument("--name", help="the manifest's name (default d1-train-t2-r<round>)")
    q.add_argument("--floor", type=float, default=FLOOR,
                   help=f"the share of the round on the training sets' own mix (default {FLOOR:g})")
    q.add_argument("--level", choices=("vague", "explicit"),
                   help="read this prompt level's episodes only (default: every episode)")
    q.add_argument("--flavour", action="append", choices=list(FLAVOUR),
                   help="plan these flavours only (default: all)")
    q.add_argument("--root", help="where the manifest goes, and where an earlier round's is read "
                                  "(default benchmarks/tasksets)")
    q.add_argument("--dry-run", action="store_true", help="print the table; build and write nothing")
    q.add_argument("--force", action="store_true", help="replace a manifest of that name")
    q.set_defaults(func=cmd_plan)
    c = sub.add_parser("check", help="a T2 manifest on disk: current, rebuilt from its record, "
                                     "and sharing nothing with any other set")
    c.add_argument("names", nargs="*", help="default: every T2 manifest under --root")
    c.add_argument("--root")
    c.set_defaults(func=cmd_check)


def cmd_plan(args) -> int:
    import sys
    name = args.name or f"{tasksets.T2_PREFIX}r{args.round_}"
    try:
        seen = observe(args.run_dirs, level=args.level, root=args.root)
        p = plan(seen["cells"], args.round_, args.size, args.floor, args.flavour)
    except (ValueError, FileNotFoundError) as why:
        print(f"t2 plan: {why}", file=sys.stderr)
        return 2
    for r in seen["runs"]:
        left = ", ".join(f"{r[k]} {word}" for k, word in (
            ("errors", "ended in error"), ("unfinished", "unfinished"),
            ("other_level", "at another level"), ("unplaced", "not in the manifest")) if r[k])
        print(f"{r['run_id']} ({r['taskset']}; {', '.join(r['agents']) or 'no agent'}; "
              f"{', '.join(r['levels']) or 'no level'}): {r['misses']} of {r['episodes']} episodes "
              f"under 100" + (f"; left out: {left}" if left else ""))
    print(render_table(p))
    if args.dry_run:
        print(f"dry run: {name} not built")
        return 0
    try:
        manifest = build(name, p, seen["runs"])
        path = write(manifest, args.root, force=args.force)
    except ValueError as why:
        print(f"t2 plan: {why}", file=sys.stderr)
        return 1
    held = Counter(t["flavour"] for t in manifest["tasks"])
    print(f"{name}: {len(manifest['tasks'])} tasks ("
          + ", ".join(f"{f} {held[f]}" for f in FLAVOUR if held[f])
          + f"), {len(manifest['skipped_seeds'])} seeds left out, shares nothing with any other set "
          f"-> {path}")
    return 0


def cmd_check(args) -> int:
    names = args.names or tasksets.t2_names(args.root)
    if not names:
        print("no T2 manifest on disk")
        return 0
    rc = 0
    for name in names:
        try:
            problems = check(name, args.root)
        except FileNotFoundError as why:
            print(f"{name}: {why}")
            rc = 1
            continue
        m = tasksets.load(name, args.root)
        if problems:
            rc = 1
            print(f"{name}: STALE ({len(m['tasks'])} tasks): " + "; ".join(problems))
        else:
            print(f"{name}: current, {len(m['tasks'])} tasks, round {m['t2']['round']}, "
                  f"{m['generator_version']} {m['spec_hash'][:19]}")
    return rc


__all__ = ["T2_VERSION", "FLOOR", "PRIOR_STRENGTH", "SIZE", "PERIOD", "Flavour", "FLAVOURS",
           "FLAVOUR", "SET_FLAVOUR", "indices", "nth_index", "base_counts", "observe",
           "allocate", "plan", "render_table", "build", "text", "write", "check", "add_parser",
           "cmd_plan", "cmd_check"]
