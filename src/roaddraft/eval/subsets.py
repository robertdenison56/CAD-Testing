"""Cost subsets: fixed parts of a leaderboard set that a Runpod run may rank on (2026-11-04).

Robert, Nov 4: "for the runpod evals i want to limit the amount of episodes to save cost but still get at least
5 tasks from each category", then "let the board rank these runpod runs and explicitly state the runs are partial
to save costs. only these runs would be allowed on the board with this tag and runs that end early or fail would
be marked partial and unscorable".

A subset is drawn once per set and committed (``benchmarks/tasksets/cost-subsets.json``): for each task type of
the set, ``PER_TYPE`` of its tasks (all of them when the type has fewer), picked by a seeded draw over the type's
ids in manifest order, so every model's subset run holds the same tasks.  A run declares one with
``python -m roaddraft.eval run --subset cost5`` (``run.json`` spec ``subset``); the report ranks it only when it
holds every task of the subset with no episode unfinished or ended in error, and only when its endpoint is a
Runpod route (``ROUTES``).  The board ranks such runs in a table of their own under the set, tagged partial to
save cost, beside every full run of the set re-scored on the same tasks.  ``d1-test`` has no subset: its types
hold 6 or 7 tasks, so five a type would save a fifth of a row.
"""
from __future__ import annotations

import json
import random
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional

from roaddraft.eval.taskset import TASKSETS_DIR

SUBSETS_FILE = Path(TASKSETS_DIR) / "cost-subsets.json"
COST_TAG = "cost5"
PER_TYPE = 5
SEED = 20261104
SETS = ("d1-real", "hard-pilots", "d1-test-hard", "d1-real-hard")
#: the endpoints a cost-subset run may rank from: Runpod's serverless and public routes
ROUTES = ("api.runpod.ai",)


def draw(rows: List[dict], per_type: int = PER_TYPE, seed: int = SEED, name: str = "") -> List[str]:
    """``per_type`` task ids of each task type (every one of a smaller type), in manifest order."""
    by_type: Dict[str, List[str]] = OrderedDict()
    for r in rows:
        by_type.setdefault(str(r["task_type"]), []).append(r["task_id"])
    keep = set()
    for t, ids in by_type.items():
        if len(ids) <= per_type:
            keep.update(ids)
        else:
            keep.update(random.Random(f"{seed}:{name}:{t}").sample(ids, per_type))
    return [r["task_id"] for r in rows if r["task_id"] in keep]


def build(per_type: int = PER_TYPE, seed: int = SEED, sets=SETS, root=None) -> dict:
    """The subsets of ``sets`` as the committed file holds them."""
    from roaddraft.eval.taskset import load
    out = {"_about": ("Cost subsets for Runpod Track D runs (roaddraft.eval.subsets): per set, "
                      f"{per_type} tasks of each task type (every task of a smaller type), a seeded draw "
                      f"(seed {seed}) over the type's ids in manifest order. A run declares one with "
                      "`--subset`; the board ranks it, tagged partial to save cost, only when it holds every "
                      "task listed with none unfinished or in error, from a Runpod route. Regenerate only "
                      "with the set: a redrawn set needs a new tag."),
           "tag": COST_TAG, "per_type": per_type, "seed": seed, "routes": list(ROUTES), "subsets": {}}
    for name in sets:
        rows = load(name, root)["tasks"]
        ids = draw(rows, per_type, seed, name)
        types: Dict[str, int] = OrderedDict()
        for r in rows:
            if r["task_id"] in set(ids):
                types[str(r["task_type"])] = types.get(str(r["task_type"]), 0) + 1
        out["subsets"][name] = {"tasks_in_set": len(rows), "tasks": len(ids), "per_type": dict(types),
                                "task_ids": ids}
    return out


def write(path=SUBSETS_FILE, **kw) -> Path:
    Path(path).write_text(json.dumps(build(**kw), indent=1) + "\n")
    return Path(path)


def load_subsets(path=SUBSETS_FILE) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"subsets": {}}


def subset_ids(taskset: str, tag: str, path=SUBSETS_FILE) -> List[str]:
    """The task ids of ``taskset``'s subset ``tag``; ValueError when there is none."""
    data = load_subsets(path)
    one = (data.get("subsets") or {}).get(taskset)
    if data.get("tag") != tag or not one:
        raise ValueError(f"no cost subset {tag!r} for {taskset} in {path} "
                         f"(sets: {', '.join(data.get('subsets') or {}) or 'none'})")
    return list(one["task_ids"])


def route_allowed(base_url: Optional[str], path=SUBSETS_FILE) -> bool:
    routes = load_subsets(path).get("routes") or list(ROUTES)
    return bool(base_url) and any(r in str(base_url) for r in routes)


__all__ = ["SUBSETS_FILE", "COST_TAG", "PER_TYPE", "SEED", "SETS", "ROUTES", "draw", "build", "write",
           "load_subsets", "subset_ids", "route_allowed"]
