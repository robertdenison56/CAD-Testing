"""The paired delta between two runs: what a training stage ends on (training plan §3, "What counts as a result").

``python -m roaddraft.eval delta RUN BASE`` reads two run reports (a run folder with ``report/summary.json``, a
published folder with ``summary.json``, or a run folder with episodes and no report yet) and pairs them by
task: the mean of ``effective(RUN) - effective(BASE)`` over the tasks both ran, with the board's bootstrap
interval (resampled within a task type), the same by task type, and the tasks at 100 in each (on a probe set a
task is 0 or 100, so that is the pilots passed).  Tasks only one run has are counted and left out, so a
checkpoint that ran the text pilots pairs with a base that ran them all.

It also says whether the two are like for like: the same set, prompt level, mode and run settings (thinking, a system extra), the same tool surface,
instructions, harness, verifier, generator and spec.  A difference is listed, never hidden: a delta between a
board row on an older surface and a run on the pin is not the training's effect alone.

Nothing here scores an episode or writes into a run folder; it reads what ``eval report`` wrote.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from roaddraft.eval.report import bootstrap, mean

FULL = 100.0
WHO_KEYS = ("model", "provider", "effort")     # who ran: what a delta is between, not a difference in the test
PIN_KEYS = ("tools_sha256", "instructions_sha256")
VERSION_KEYS = ("spec_version", "spec_hash", "generator_version", "verifier_version", "harness_version")


def load_summary(path) -> dict:
    """The summary of a run: ``summary.json`` in the folder (a published run), ``report/summary.json`` (a run
    that was reported), or the report built now from the episodes (nothing is written). A run folder also holds
    the runner's own ``summary.json``, which has no rows; that one is passed over."""
    path = Path(path)
    for f in (path / "report" / "summary.json", path / "summary.json"):
        if f.is_file():
            data = json.loads(f.read_text())
            if "rows" in data:
                return data
    if (path / "episodes").is_dir():
        from roaddraft.eval.report import build
        return build(path)
    raise FileNotFoundError(f"{path}: no summary.json, no report/summary.json and no episodes")


def pick_row(summary: dict, label: Optional[str] = None) -> dict:
    """The run's one row, or the one whose label holds ``label``."""
    rows = summary.get("rows") or []
    if label is not None:
        rows = [g for g in rows if label in g["label"]]
    if len(rows) != 1:
        have = ", ".join(repr(g["label"]) for g in summary.get("rows") or []) or "none"
        raise ValueError(f"{summary.get('run_id')}: {len(rows)} rows" + (f" match {label!r}" if label else "")
                         + f"; name one with --row/--base-row (rows: {have})")
    return rows[0]


def _r(x: Optional[float], digits: int = 2) -> Optional[float]:
    return None if x is None else round(x, digits)


def _one(diffs: Sequence[float], types: Sequence[str], a: Sequence[float], b: Sequence[float]) -> dict:
    lo, hi = bootstrap(diffs, types)
    return {"n_tasks": len(diffs), "run_mean": _r(mean(a)), "base_mean": _r(mean(b)), "gap": _r(mean(diffs)),
            "ci_low": _r(lo), "ci_high": _r(hi),
            "separated": bool(lo is not None and (lo > 0 or hi < 0)),
            "better": sum(d > 0 for d in diffs), "worse": sum(d < 0 for d in diffs),
            "same": sum(d == 0 for d in diffs),
            "run_full": sum(x >= FULL for x in a), "base_full": sum(x >= FULL for x in b),
            "gained_full": sum(x >= FULL > y for x, y in zip(a, b)),
            "lost_full": sum(y >= FULL > x for x, y in zip(a, b))}


def differences(run: dict, base: dict, run_row: dict, base_row: dict) -> List[str]:
    """What keeps the two from being like for like, as sentences; empty when nothing does."""
    out = []
    if run.get("taskset") != base.get("taskset"):
        out.append(f"the sets differ: {run.get('taskset')} against {base.get('taskset')}")
    ka, kb = run_row.get("key") or {}, base_row.get("key") or {}
    for k in sorted((set(ka) | set(kb)) - set(WHO_KEYS)):     # the prompt, the mode, thinking, a system extra
        x, y = ka.get(k), kb.get(k)
        if x != y:
            out.append(f"{k}: {x} against {y}")
    for k in PIN_KEYS:
        x, y = (run.get("pins") or {}).get(k), (base.get("pins") or {}).get(k)
        if x != y:
            out.append(f"{k}: {str(x)[:19]} against {str(y)[:19]}")
    for k in VERSION_KEYS:
        x, y = (run.get("versions") or {}).get(k), (base.get("versions") or {}).get(k)
        if x != y:
            out.append(f"{k}: {x} against {y}")
    for name, s in (("the run", run), ("the base", base)):
        if s.get("partial"):
            out.append(f"{name} is partial: {s.get('partial_reason') or 'not every task of the set'}")
        if s.get("stale"):
            out.append(f"{name} was scored under older versions than the current ones: {', '.join(s['stale'])}")
    if bool(run.get("reverified")) != bool(base.get("reverified")):
        out.append("one of the two was re-scored with the current verifier and the other was not")
    return out


def delta(run: dict, base: dict, row: Optional[str] = None, base_row: Optional[str] = None) -> dict:
    """``run`` minus ``base``, paired by task, from two summaries."""
    g, h = pick_row(run, row), pick_row(base, base_row)
    ma: Dict[str, float] = g.get("task_means") or {}
    mb: Dict[str, float] = h.get("task_means") or {}
    types: Dict[str, str] = {**(h.get("task_types") or {}), **(g.get("task_types") or {})}
    shared = sorted(set(ma) & set(mb))
    if not shared:
        raise ValueError(f"{run.get('run_id')} and {base.get('run_id')} share no task")
    a, b = [ma[t] for t in shared], [mb[t] for t in shared]
    diffs = [x - y for x, y in zip(a, b)]
    strata = [str(types.get(t)) for t in shared]
    by_type = []
    for name in sorted(set(strata)):
        idx = [i for i, s in enumerate(strata) if s == name]
        by_type.append({"task_type": name, **_one([diffs[i] for i in idx], [name] * len(idx),
                                                   [a[i] for i in idx], [b[i] for i in idx])})
    return {"run": {"run_id": run.get("run_id"), "label": g["label"], "effective_mean": g.get("effective_mean"),
                    "n_tasks": g.get("n_tasks"), "errors": g.get("errors")},
            "base": {"run_id": base.get("run_id"), "label": h["label"], "effective_mean": h.get("effective_mean"),
                     "n_tasks": h.get("n_tasks"), "errors": h.get("errors")},
            "taskset": run.get("taskset"),
            "only_run": sorted(set(ma) - set(mb)), "only_base": sorted(set(mb) - set(ma)),
            "all": _one(diffs, strata, a, b), "by_task_type": by_type,
            "tasks": {t: {"run": _r(x, 4), "base": _r(y, 4), "task_type": s}
                      for t, x, y, s in zip(shared, a, b, strata)},
            "not_like_for_like": differences(run, base, g, h)}


def _f(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.1f}"


def _signed(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:+.1f}"


def _row(name: str, o: dict) -> str:
    return (f"| {name} | {o['n_tasks']} | {_f(o['base_mean'])} | {_f(o['run_mean'])} | {_signed(o['gap'])} | "
            f"{_signed(o['ci_low'])} to {_signed(o['ci_high'])} | {o['better']} / {o['worse']} / {o['same']} | "
            f"{o['base_full']} | {o['run_full']} | +{o['gained_full']} / -{o['lost_full']} |")


def render(d: dict) -> str:
    """The delta as markdown: the headline, the table by task type, what is not like for like."""
    o = d["all"]
    lines = [f"# {d['run']['run_id']} minus {d['base']['run_id']}", "",
             f"Set `{d['taskset']}`, paired on the {o['n_tasks']} tasks both ran. "
             f"Run: {d['run']['label']}. Base: {d['base']['label']}.", "",
             f"**Effective {_signed(o['gap'])} ({_signed(o['ci_low'])} to {_signed(o['ci_high'])}, 95%), "
             + ("separated from zero" if o["separated"] else "not separated from zero")
             + f"**: {_f(o['base_mean'])} to {_f(o['run_mean'])}. Tasks at 100: {o['base_full']} to "
               f"{o['run_full']} ({o['gained_full']} gained, {o['lost_full']} lost).", ""]
    for name, ids in (("run", d["only_run"]), ("base", d["only_base"])):
        if ids:
            lines += [f"{len(ids)} task(s) only the {name} ran are left out.", ""]
    if d["not_like_for_like"]:
        lines += ["**Not like for like:**", ""] + [f"- {x}" for x in d["not_like_for_like"]] + [""]
    else:
        lines += ["Like for like: the same set, prompt, mode, tool surface, instructions and versions.", ""]
    lines += ["| task type | tasks | base | run | gap | 95% | better / worse / same | base at 100 | run at 100 | "
              "gained / lost |", "|---|---:|---:|---:|---:|---|---|---:|---:|---|"]
    lines += [_row(t["task_type"], t) for t in sorted(d["by_task_type"], key=lambda t: (t["gap"], t["task_type"]))]
    lines += [_row("**all**", o), ""]
    return "\n".join(lines)
