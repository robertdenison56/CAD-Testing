"""Where a vague prompt's points go, and how many of them a drafting standard explains.

Robert, 2026-11-08: "Important to know if any of these prompts fail due to not knowing
drafting standards."  A vague prompt states the request in a sentence; what belongs on the
sheet and how it is drafted is the drafter's to know (``tasks.prompts``).  The verifier
grades what must be on the sheet the same at both levels, and a convention the prompt did
not state by the spec's lenient rules (any standard scale, any layer but 0, any legible
height, values read by meaning, not format).  So a vague episode's lost points fall in
three places:

- **a drafting standard not applied**: an element a plan sheet carries left off (ticks,
  station numbers, BC/EC and curve numbers, bearings, the curve table, title-block fields,
  the north arrow, the match line, pavement widths, construction notes), lettering on
  layer 0 or at an illegible height, labels set over linework, other labels or the border,
  a sheet at a non-standard scale or not fitted (finding categories ``completeness``,
  ``standards``, ``legibility``, ``sheet_setup``);
- **the work done wrong**: a wrong value on the sheet, linework off the design, labels
  typed by hand or doubled, work drawn where no sheet shows it (``value``, ``anchoring``,
  ``placement``), and the points a hard fail zeroes: graded the same at both levels, so
  not a standard;
- **an episode that ended early**, on its budget or in error: all of its lost points.

Paired with an explicit run of the same model on the same tasks, each check's lost points
split again: **recovered when told** (the explicit episode, told the standard, earned
them) and **lost at both levels** (it could not do the work even when told).  A standards
miss the explicit episode recovered is the plainest sign the model did not know the
standard; one lost at both is a capability miss whatever the prompt.  Without a pair the
split is by finding code alone, and an element left off cannot be told apart from one the
model could not draw.  k = 1 everywhere, so a single task's split carries sampling noise;
the totals over a set are the read.

``python -m roaddraft.eval standards RUN [--explicit RUN]`` writes ``standards.md`` and
``standards.json`` into the run's ``report/``.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.eval.report import CATEGORY_OF
from roaddraft.eval.trajectory import read_episode

#: finding categories (``report.TAXONOMY``) that a drafting standard explains
STANDARD_CATEGORIES = ("completeness", "standards", "legibility", "sheet_setup")
#: the rest: the work done wrong, whatever the prompt said
WORK_CATEGORIES = ("value", "anchoring", "placement")

#: what each check's ``completeness`` finding leaves off, as a drafter would say it
LEFT_OFF = {
    "D1-00": "the sheet setup (a sheet, its viewport, the match line)",
    "D1-01": "the alignment linework",
    "D1-02": "station ticks every 100 ft",
    "D1-03": "station numbers (and station equations)",
    "D1-04": "BC/EC stations and the curve-number bubbles",
    "D1-05": "bearing and distance on each tangent",
    "D1-06": "the curve data table",
    "D1-07": "labels at their anchors",
    "D1-08": "lettering",
    "D1-09": "a standard layer",
    "D1-10": "title-block fields",
    "D1-11": "the north arrow",
    "D1-12": "pavement edges",
    "D1-13": "pavement width dimensions",
    "D1-14": "the base reference",
    "D1-15": "the alignment",
    "D1-16": "construction callouts",
}
#: the standard behind each code of the other standard categories
CODE_STANDARD = {
    "wrong_layer": "nothing drafted on layer 0 (explicit: the stated layer)",
    "wrong_layer_props": "layer color and linetype as the standard sets them",
    "wrong_height": "lettering at a legible plan height (0.08-0.20 in; explicit: the stated height)",
    "overlap": "lettering clear of linework and other lettering",
    "off_sheet": "everything inside the sheet's usable area",
    "clipped": "everything inside the sheet's usable area",
    "upside_down": "lettering that reads upright",
    "viewport_scale": "a standard plan scale",
    "not_fitted": "the alignment fitted in its viewport",
    "sheet_missing": "the deliverable sheet",
}
ENDED_EARLY = ("budget", "error")


def standard_of(check_id: str, code: str) -> str:
    """The plain-words standard a finding of this check and code misses."""
    if CATEGORY_OF.get(code) == "completeness":
        return "left off: " + LEFT_OFF.get(check_id, check_id)
    return CODE_STANDARD.get(code, code)


def load_run(run_dir) -> Dict[str, dict]:
    """task id -> the episode's level, scores, termination and in-scope checks (weight,
    credit, finding codes), for every episode with a verify and an end record."""
    out: Dict[str, dict] = {}
    for f in sorted(Path(run_dir, "episodes").glob("*.jsonl")):
        rec = read_episode(f)
        header, verify, end = rec["header"], rec["verify"], rec["end"]
        if header is None or end is None:
            continue
        verify = verify or {}
        checks = {}
        for c in verify.get("checks") or []:
            if c.get("in_scope", True) and not c.get("skipped"):
                checks[c["id"]] = {"weight": float(c.get("weight") or 0.0),
                                   "credit": float(c.get("credit") or 0.0),
                                   "codes": [x["code"] for x in c.get("findings") or []]}
        out[header["task_id"]] = {
            "task_type": header.get("task_type"), "level": header.get("level", "explicit"),
            "model": header.get("model"), "termination": end.get("termination") or "unknown",
            "effective": float(verify.get("effective_score", end.get("effective_score") or 0.0)),
            "rubric": float(verify.get("rubric_score", end.get("rubric_score") or 0.0)),
            "hard_failed": bool(verify.get("hard_failed", end.get("hard_failed"))),
            "verifier": verify.get("verifier_version"), "checks": checks,
        }
    return out


def _lost(ep: dict) -> Dict[str, float]:
    """Rubric points each check lost, scaled to 100 over the task's in-scope weight."""
    total = sum(c["weight"] for c in ep["checks"].values())
    if total <= 0:
        return {}
    return {cid: 100.0 * c["weight"] * (1.0 - c["credit"]) / total for cid, c in ep["checks"].items()}


def _shares(codes: Sequence[str]) -> List[Tuple[str, str, float]]:
    """(category, code, share) over a check's findings, by count; a check that lost points
    with no finding is put down as ``completeness`` (nothing there to judge)."""
    counts = Counter(codes)
    n = sum(counts.values())
    if not n:
        return [("completeness", "missing", 1.0)]
    return [(CATEGORY_OF.get(code, "value"), code, k / n) for code, k in counts.items()]


def split_episode(ep: dict, told: Optional[dict] = None) -> List[dict]:
    """The episode's lost effective points as parts: kind (standard / work / hard_fail /
    ended_early), check, category, code, standard, points, and with ``told`` (the same task
    at the explicit level) how much of them the told episode earned (``recovered``)."""
    loss = 100.0 - ep["effective"]
    if loss <= 1e-9:
        return []
    if ep["termination"] in ENDED_EARLY:
        return [{"kind": "ended_early", "check": None, "category": None, "code": ep["termination"],
                 "standard": f"ended on its {ep['termination']}", "points": loss,
                 "recovered": None if told is None else max(0.0, told["effective"] - ep["effective"])}]
    parts: List[dict] = []
    if ep["hard_failed"]:
        parts.append({"kind": "hard_fail", "check": None, "category": "value", "code": "hard_fail",
                      "standard": "a wrong value on the sheet (hard fail): not a standard",
                      "points": ep["rubric"],
                      "recovered": None if told is None else (0.0 if told["hard_failed"] else ep["rubric"])})
    mine, theirs = _lost(ep), (_lost(told) if told is not None else None)
    for cid, pts in mine.items():
        if pts <= 1e-9:
            continue
        rec = None
        if theirs is not None:
            rec = max(0.0, pts - theirs.get(cid, pts))
        for cat, code, share in _shares(ep["checks"][cid]["codes"]):
            parts.append({"kind": "standard" if cat in STANDARD_CATEGORIES else "work",
                          "check": cid, "category": cat, "code": code,
                          "standard": standard_of(cid, code) if cat in STANDARD_CATEGORIES else
                          f"{cid} {code}", "points": pts * share,
                          "recovered": None if rec is None else rec * share})
    return parts


def find_explicit(run_dir) -> Optional[Path]:
    """The explicit run beside a vague one: the same run id without ``-vague``."""
    run_dir = Path(run_dir)
    name = run_dir.name
    if "-vague" not in name:
        return None
    other = run_dir.parent / name.replace("-vague", "", 1)
    return other if (other / "episodes").is_dir() else None


def analyse(run_dir, explicit_dir=None) -> dict:
    """The whole run's split, per task averaged over its tasks (the parts add up to
    100 minus the run's mean effective score)."""
    eps = load_run(run_dir)
    told_eps = load_run(explicit_dir) if explicit_dir else {}
    paired = sorted(t for t in eps if t in told_eps)
    tasks = sorted(eps)
    n = len(tasks)
    rows: List[dict] = []
    by_type: Dict[str, Counter] = defaultdict(Counter)
    tasks_hit: Dict[Tuple[str, str], set] = defaultdict(set)
    for tid in tasks:
        ep = eps[tid]
        told = told_eps.get(tid)
        for p in split_episode(ep, told):
            p["task_id"], p["task_type"] = tid, ep["task_type"]
            rows.append(p)
            by_type[ep["task_type"]][p["kind"]] += p["points"]
            tasks_hit[(p["kind"], p["standard"])].add(tid)
    agg: Dict[Tuple[str, str], dict] = {}
    for p in rows:
        a = agg.setdefault((p["kind"], p["standard"]), {"kind": p["kind"], "standard": p["standard"],
                                                         "points": 0.0, "recovered": 0.0, "paired_points": 0.0})
        a["points"] += p["points"]
        if p["recovered"] is not None:
            a["recovered"] += p["recovered"]
            a["paired_points"] += p["points"]
    lines = []
    for key, a in agg.items():
        lines.append({"kind": a["kind"], "standard": a["standard"],
                      "points_per_task": a["points"] / n, "tasks": len(tasks_hit[key]),
                      "recovered_per_task": a["recovered"] / n if paired else None,
                      "lost_at_both_per_task": (a["paired_points"] - a["recovered"]) / n if paired else None})
    lines.sort(key=lambda r: -r["points_per_task"])
    kinds = Counter()
    rec_kinds = Counter()
    for p in rows:
        kinds[p["kind"]] += p["points"] / n
        if p["recovered"] is not None:
            rec_kinds[p["kind"]] += p["recovered"] / n
    mean_eff = sum(e["effective"] for e in eps.values()) / n if n else None
    told_mean = (sum(told_eps[t]["effective"] for t in paired) / len(paired)) if paired else None
    vague_paired_mean = (sum(eps[t]["effective"] for t in paired) / len(paired)) if paired else None
    first = next(iter(eps.values()), {})
    return {
        "run_id": Path(run_dir).name, "explicit_run_id": Path(explicit_dir).name if explicit_dir else None,
        "model": first.get("model"), "level": first.get("level"), "tasks": n, "paired_tasks": len(paired),
        "verifiers": sorted({e["verifier"] for e in list(eps.values()) + list(told_eps.values()) if e["verifier"]}),
        "effective_mean": mean_eff, "lost_per_task": None if mean_eff is None else 100.0 - mean_eff,
        "explicit_effective_mean": told_mean, "vague_effective_mean_paired": vague_paired_mean,
        "by_kind": dict(kinds), "recovered_by_kind": dict(rec_kinds) if paired else None,
        "lines": lines,
        "by_task_type": {t: {k: v / n for k, v in c.items()} for t, c in sorted(by_type.items())},
        "parts": rows,
    }


KIND_WORDS = {"standard": "a drafting standard not applied", "work": "the work done wrong",
              "hard_fail": "a wrong value on the sheet (hard fail)", "ended_early": "ended early (budget or error)"}


def render_markdown(s: dict) -> str:
    f1 = lambda x: "–" if x is None else f"{x:.1f}"
    L = [f"# Drafting standards behind the lost points: {s['run_id']}", ""]
    L.append(f"{s['model']}, {s['level']} prompt, {s['tasks']} tasks: mean effective {f1(s['effective_mean'])}, "
             f"so {f1(s['lost_per_task'])} points a task lost.")
    if s["paired_tasks"]:
        L.append(f"Paired with `{s['explicit_run_id']}` on {s['paired_tasks']} tasks (explicit "
                 f"{f1(s['explicit_effective_mean'])} against vague {f1(s['vague_effective_mean_paired'])} "
                 "on the same tasks). \"Recovered when told\" is what the explicit episode earned back; "
                 "\"lost at both\" it lost too.")
    else:
        L.append("No explicit run of this model on these tasks: the split is by finding code alone, and an "
                 "element left off cannot be told from one the model could not draw.")
    L += ["", "| Where the points went | Points a task | Recovered when told | Lost at both |", "|---|---:|---:|---:|"]
    for k in ("standard", "work", "hard_fail", "ended_early"):
        pts = s["by_kind"].get(k, 0.0)
        rec = None if s["recovered_by_kind"] is None else s["recovered_by_kind"].get(k, 0.0)
        both = None if rec is None else pts - rec
        L.append(f"| {KIND_WORDS[k]} | {f1(pts)} | {f1(rec)} | {f1(both)} |")
    L += ["", "## By standard", "", "| Standard | Tasks | Points a task | Recovered when told | Lost at both |",
          "|---|---:|---:|---:|---:|"]
    for r in s["lines"]:
        if r["kind"] != "standard" or r["points_per_task"] < 0.05:
            continue
        L.append(f"| {r['standard']} | {r['tasks']} | {f1(r['points_per_task'])} | "
                 f"{f1(r['recovered_per_task'])} | {f1(r['lost_at_both_per_task'])} |")
    L += ["", "## By task type (points a task, over the whole set)", "",
          "| Task type | Standard | Work | Hard fail | Ended early |", "|---|---:|---:|---:|---:|"]
    for t, c in s["by_task_type"].items():
        L.append(f"| {t} | {f1(c.get('standard'))} | {f1(c.get('work'))} | {f1(c.get('hard_fail'))} | "
                 f"{f1(c.get('ended_early'))} |")
    L += ["", "k = 1: a single task's split carries sampling noise; the totals are the read. "
          "Built by `roaddraft.eval.standards`."]
    return "\n".join(L) + "\n"


def write(s: dict, out_dir) -> List[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / "standards.md", out / "standards.json"
    md.write_text(render_markdown(s), encoding="utf-8")
    js.write_text(json.dumps({k: v for k, v in s.items() if k != "parts"}, indent=1), encoding="utf-8")
    return [md, js]
