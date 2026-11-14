"""Export the eval leaderboard (Track D) as the dashboard's three datasets.

    python scripts/export_eval_dashboard.py OUT_DIR [--runs benchmarks/runs] [--results results]

Reads ``benchmarks/runs/leaderboard.json`` (what ``scripts/make_leaderboard.py``
wrote), each ranked run's ``summary.json``, and the per-episode report the run
was published from (``results/**/<run_id>/report/episodes.csv`` and the episode
logs beside it), and writes

    OUT_DIR/eval_board.json   one row per published run: rank on its set, the board's
                              columns as LEADERBOARD.md prints them, why a row is not ranked
    OUT_DIR/eval_grid.json    one cell per ranked row and task type (the d1 sets) or
                              pilot (hard-pilots): the effective mean, its tasks, and what
                              the verifier marked down, in the checks' own words; ``order``
                              is the row's place on the board (vague ranking first)
    OUT_DIR/eval_checks.json  the verifier's checks, id and full name
    OUT_DIR/eval_overall.json one row per model: its overall score (the weighted mean of its five
                              set scores, ``report.OVERALL_WEIGHTS``) and each set's score

Errored episodes are left out, as the report leaves them out.  Each cell's mean
is checked against the summary's ``by_task_type``; a mismatch stops the export,
since it means the episode report no longer matches the published run.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from roaddraft.eval.report import _usd, row_level  # noqa: E402
from roaddraft.runners.leaderboard import NAMES  # noqa: E402
from roaddraft.tasks.types import REAL_GROUP_NAMES, REAL_GROUP_OF, REAL_GROUP_ORDER  # noqa: E402

SETS = ("d1-test", "d1-real", "hard-pilots", "d1-test-hard", "d1-real-hard")
RUNNERS = {"claude-code": "Claude Code CLI", "codex": "Codex CLI"}
QUANT = {"q4km": "Q4_K_M", "q8": "Q8_0"}
# model ids the probe board never ran
LOCAL_NAMES = {"google/gemma-4-12b": "Gemma 4 12B", "zai-org/glm-4.6v-flash": "GLM-4.6V-Flash",
               "gpt-6.1-terra": "GPT-6.1-Terra",
               "mistralai/Mistral-Small-4-119B-2603-NVFP4": "Mistral Small 4 119B (NVFP4, vLLM)",
               "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4": "Nemotron 3.5 Super VL 120B-A12B (NVFP4, vLLM)"}
LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")

# d1-test has no question groups of its own; its seeded types sit under the d1-real
# group each real type was made from, so the two grids read the same way
SEEDED_GROUP = {
    "draw-alignment": "draft", "create-alignment": "draft", "pavement-edges": "draft",
    "stationing": "letter", "curve-callouts": "letter", "bearings": "letter",
    "curve-table": "letter", "annotate-base": "letter",
    "layer-setup": "sheet", "attach-reference": "sheet", "title-block": "sheet",
    "sheet-setup": "sheet", "annotate-sheet": "sheet", "plan-sheet": "sheet",
    "pavement-widths": "notes", "pavement": "notes",
    # d1-test-hard's three whole-sheet types sit with d1-real-hard's whole jobs
    "plan-sheet-pavement": "job", "create-plan-sheet": "job", "base-plan-sheet": "job",
}
GROUP_KEY = {"draft": "Draft", "letter": "Letter", "sheet": "Sheet", "notes": "Notes", "job": "Job"}

# the checks' names cut to a few words for a tooltip line; the full names go out in eval_checks
CHECK_SHORT = {
    "D1-00": "sheet setup", "D1-01": "alignment linework", "D1-02": "station ticks",
    "D1-03": "station numbers", "D1-04": "BC/EC and curve numbers", "D1-05": "bearings and distances",
    "D1-06": "curve table", "D1-07": "label positions", "D1-08": "legibility",
    "D1-09": "layers and text heights", "D1-10": "title block", "D1-11": "north arrow",
    "D1-12": "pavement edges", "D1-13": "width dimensions", "D1-14": "base attached",
    "D1-15": "alignment from geometry", "D1-16": "construction callouts", "PROBE": "the pilot's check",
}


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def f1(x):
    return "–" if x is None else f"{x:.1f}"


def model_name(key: dict, run_id: str) -> str:
    name = NAMES.get(key["model"]) or LOCAL_NAMES.get(key["model"], key["model"])
    quant = next((QUANT[q] for q in QUANT if f"-{q}-" in run_id), None)
    if "-lms-" in run_id:
        return f"{name} ({quant}, LM Studio)" if quant else f"{name} (LM Studio)"
    return name


def runner_name(key: dict, run_id: str) -> str:
    if key["provider"] in RUNNERS:
        return RUNNERS[key["provider"]]
    if "-lms-" in run_id:
        return "LM Studio, local"
    if "runpod" in run_id or key["provider"] == "openai":
        return "OpenAI-compatible server"
    return key["provider"]


def effort_text(effort: str) -> str:
    return f"{effort} effort" if effort in LEVELS else effort


def mode_text(key: dict) -> str:
    return key["mode"].replace("_", "-")


def row_label(key: dict) -> str:
    """What sets a row apart from the model's other rows on the same set."""
    bits = [] if key["mode"] == "single" else [mode_text(key)]
    if key["level"] != "explicit":
        bits.append(f"{key['level']} prompt")
    if key.get("dialect", "neutral") != "neutral":
        bits.append(f"{key['dialect']} skin")
    return " · ".join(bits)


def find_report(results: Path, run_id: str) -> Path:
    hits = sorted(results.glob(f"**/{run_id}/report/episodes.csv"))
    if not hits:
        raise SystemExit(f"no episode report for {run_id} under {results}")
    return hits[0]


def read_episodes(csv_path: Path):
    """The scored episodes of a published run, each with its verify event."""
    out = []
    for row in csv.DictReader(csv_path.open()):
        if row["termination"] == "error":
            continue
        log = csv_path.parent.parent / "episodes" / row["file"]
        verify = None
        for line in log.open():
            if '"type": "verify"' in line:
                verify = json.loads(line)
        row["verify"] = verify or {}
        out.append(row)
    return out


def errored(csv_path: Path):
    n = defaultdict(int)
    for row in csv.DictReader(csv_path.open()):
        if row["termination"] == "error":
            n[row["task_type"]] += 1
    return n


def per_task(eps):
    """Mean effective, rubric, hard fails and cleans per task id over its samples."""
    by = defaultdict(list)
    for e in eps:
        by[e["task_id"]].append(e)
    tasks = []
    for tid, es in sorted(by.items()):
        tasks.append({
            "task": tid,
            "effective": mean(float(e["effective_score"]) for e in es),
            "rubric": mean(float(e["rubric_score"]) for e in es),
            "hard": sum(e["hard_failed"] == "True" for e in es),
            "clean": sum(e["clean"] == "True" for e in es),
            "hard_checks": sorted({c for e in es for c in (e["hard_fail_checks"] or "").split(";") if c}),
            "episodes": es,
        })
    return tasks


def step(value: int) -> int:
    """The colour step of a cell, read from the number it prints."""
    if value <= 0:
        return 0
    if value < 50:
        return 1
    if value < 80:
        return 2
    if value < 100:
        return 3
    return 4


def weak_checks(tasks):
    """In-scope checks below full credit, averaged over the tasks that scored them."""
    credit = defaultdict(list)
    for t in tasks:
        for e in t["episodes"]:
            for c in e["verify"].get("checks", []):
                if c.get("in_scope") and not c.get("skipped"):
                    credit[c["id"]].append(float(c.get("credit") or 0.0))
    low = [(mean(v), cid) for cid, v in credit.items() if mean(v) < 0.995]
    return [f"{cid} {CHECK_SHORT.get(cid, cid)} {100 * m:.0f}%" for m, cid in sorted(low)[:3]]


def type_cell(run_id, who, rank, set_id, ty, tasks, n_err):
    eff = mean(t["effective"] for t in tasks)
    label = round(eff)
    grp = REAL_GROUP_OF[ty] if set_id.startswith("d1-real") else SEEDED_GROUP[ty]
    hard = [t for t in tasks if t["hard"]]
    clean = sum(1 for t in tasks if t["clean"])
    bits = [f"hard-fail {len(hard)} of {len(tasks)}"
            + (f" ({', '.join(sorted({c for t in hard for c in t['hard_checks']}))})" if hard else ""),
            f"clean {clean} of {len(tasks)}"]
    if n_err:
        bits.append(f"{n_err} errored, left out")
    weak = weak_checks(tasks)
    detail = "; ".join(bits) + (". Marked down on " + ", ".join(weak) if weak else ". Full credit on every check")
    scores = sorted((round(t["effective"]) for t in tasks), reverse=True)
    return {
        "key": f"{run_id}|{ty}", "model": run_id, "set": set_id, **who, "rank": rank,
        "group": GROUP_KEY[grp], "group_name": REAL_GROUP_NAMES[grp], "group_order": REAL_GROUP_ORDER.index(grp),
        "column": ty, "column_label": ty.removeprefix("real-"),
        "label": str(label), "step": step(label), "n": len(tasks), "effective": f1(eff),
        "summary": f"{who['row']}: {eff:.1f} over {len(tasks)} task{'s' if len(tasks) != 1 else ''}",
        "detail": detail, "tasks": " · ".join(str(s) for s in scores),
    }


def pilot_cell(run_id, who, rank, task):
    tid = task["task"]
    short = tid.removeprefix("PR-").rsplit("-", 1)[0]
    family, rest = short.split("-", 1)
    e = task["episodes"][0]
    v = e["verify"]
    passed = not task["hard"]
    done, asked = v.get("items_done"), v.get("items_asked")
    items = f"{done} of {asked} items done" if asked else f"rubric {task['rubric']:.0f}"
    label = round(task["effective"])
    return {
        "key": f"{run_id}|{tid}", "model": run_id, "set": "hard-pilots", **who, "rank": rank,
        "group": family, "group_name": e["task_type"].removeprefix("pilot-").replace("-", " "),
        "group_order": int(family[1:]),
        "column": tid, "column_label": rest,
        "label": str(label), "step": step(label), "n": len(task["episodes"]), "effective": f1(task["effective"]),
        "summary": f"{who['row']}: {'passed' if passed else 'failed'}, {items}",
        "detail": v.get("detail") or ("passed its check" if passed else "failed its check"),
        "tasks": "",
    }


def empty_cell(column, row_cell):
    """A cell for a type or pilot this row's run never drew."""
    cell = dict(row_cell, label="", step=-1, n=0, effective="–", summary=f"{row_cell['row']}: not in this run",
                detail="The run's task draw has no task of this type.", tasks="")
    cell.update({k: column[k] for k in ("column", "column_label", "group", "group_name", "group_order")})
    cell["key"] = f"{row_cell['model']}|{column['column']}"
    return cell


def board_row(r, set_id, status, as_of, summary=None):
    key = r["key"]
    k = f"{r['n_tasks']} × {r['k_max'] if r['k_min'] == r['k_max'] else str(r['k_min']) + '–' + str(r['k_max'])}"
    groups = r.get("by_group") or {}
    row = {
        "key": r["run_id"], "set": set_id, "status": status, "rank": str(r["rank"]) if status == "ranked" else "",
        "name": model_name(key, r["run_id"]), "mode": mode_text(key), "prompt": row_level(set_id, key) or "–",
        "label": row_label(key), "effort": r["effort"], "runner": runner_name(key, r["run_id"]),
        "row": model_name(key, r["run_id"]) + (f" · {row_label(key)}" if row_label(key) else ""),
        "effective": f1(r["effective_mean"]), "ci": f"{r['ci_low']:.1f}–{r['ci_high']:.1f}",
        "rubric": f1(r["rubric_mean"]), "hard_fail": pct(r["hard_fail_rate"]), "clean": pct(r["clean_sheet_rate"]),
        "invalid": pct(r["invalid_call_rate"]), "cost": _usd(r["cost_per_sheet"]), "tasks": k, "run": r["run_id"],
        "why": "", "as_of": as_of,
    }
    for g in ("draft", "letter", "sheet", "notes", "job"):
        row[g] = f1(groups[g]["effective_mean"]) if g in groups else "–"
    row["passed"] = ""
    if set_id == "hard-pilots" and summary is not None:
        # a pilot scores 100 or 0, so the effective mean is the share passed
        row["passed"] = f"{round(summary['effective_mean'] * summary['n_tasks'] / 100)} of {summary['n_tasks']}"
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--runs", type=Path, default=REPO / "benchmarks" / "runs")
    ap.add_argument("--results", type=Path, default=REPO / "results")
    args = ap.parse_args(argv)

    lb = json.loads((args.runs / "leaderboard.json").read_text())
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    board, grid, checks = [], [], {}

    for set_id in SETS:
        cells = []
        one = lb["boards"].get(set_id, {})
        # the vague-prompt ranking first, then each other level's (the board ranks them apart)
        rankings = [one.get("ranked", [])] + [o.get("ranked", [])
                                              for o in (one.get("other_prompts") or {}).values()]
        for order, r in enumerate(r for rows in rankings for r in rows):
            run_id = r["run_id"]
            summary = json.loads((args.runs / run_id / "summary.json").read_text())["rows"][0]
            board.append(board_row(r, set_id, "ranked", as_of, summary))
            for cid, c in summary["per_check"].items():
                checks[cid] = c["name"]
            name = model_name(r["key"], run_id)
            mode = row_label(r["key"])
            who = {"name": name, "mode": mode, "effort": effort_text(r["effort"]),
                   "row": name + (f" · {mode}" if mode else ""),
                   "prompt": row_level(set_id, r["key"]) or "–", "order": order}
            csv_path = find_report(args.results, run_id)
            eps = read_episodes(csv_path)
            n_err = errored(csv_path)
            tasks = per_task(eps)
            if set_id == "hard-pilots":
                cells.extend(pilot_cell(run_id, who, r["rank"], t) for t in tasks)
                continue
            by_type = defaultdict(list)
            for t in tasks:
                by_type[t["episodes"][0]["task_type"]].append(t)
            for ty, ts in sorted(by_type.items()):
                cell = type_cell(run_id, who, r["rank"], set_id, ty, ts, n_err.get(ty, 0))
                want = summary["by_task_type"][ty]["effective_mean"]
                if abs(float(cell["effective"]) - want) > 0.051:
                    raise SystemExit(f"{run_id} {ty}: cell {cell['effective']} but the summary says {want}")
                cells.append(cell)
        # a type or pilot one ranked row has and another lacks gets an empty cell in the other
        columns = {}
        for c in cells:
            columns.setdefault(c["column"], c)
        for run_id in dict.fromkeys(c["model"] for c in cells):
            mine = [c for c in cells if c["model"] == run_id]
            have = {c["column"] for c in mine}
            cells.extend(empty_cell(proto, mine[0]) for col, proto in columns.items() if col not in have)
        cells.sort(key=lambda c: (c["order"], c["group_order"], c["column"]))
        grid.extend(cells)

    for o in lb.get("others", []):
        for r in o["rows"]:
            board.append({
                "key": o["run_id"], "set": o["taskset"], "status": "not ranked", "rank": "",
                "name": model_name({"model": r["label"].split(" · ")[0]}, o["run_id"]), "mode": "", "prompt": "",
                "label": " · ".join(r["label"].split(" · ")[1:]), "row": "",
                "effort": r["effort"], "runner": "", "effective": f1(r["effective_mean"]),
                "ci": f"± {r['half_width']:.1f}", "rubric": "–", "hard_fail": "–", "clean": "–", "invalid": "–",
                "cost": "–", "tasks": f"{r['n_tasks']} × {r['k_max']}", "run": o["run_id"],
                "why": "; ".join(o["reasons"]), "as_of": as_of,
                "draft": "–", "letter": "–", "sheet": "–", "notes": "–", "job": "–", "passed": "",
            })

    # the overall score (Robert, 2026-11-13): one row per model, the weighted mean of its five set scores
    overall = []
    ov = (lb.get("overall") or {}).get("vague") or {"ranked": [], "partial": [], "weights": {}}
    for o in ov["ranked"] + ov["partial"]:
        run_id = next(iter(o["sets"].values()))["run_id"]
        row = {"key": "|".join(f"{k}={o['key'].get(k)}" for k in ("model", "provider", "effort", "mode")),
               "rank": str(o["rank"]) if o.get("rank") else "", "name": model_name(o["key"], run_id),
               "effort": o.get("effort") or "–", "overall": f1(o["overall"]),
               "pm": "–" if o["half_width"] is None else f"± {o['half_width']:.1f}",
               "sets": f"{o['n_sets']} of {len(ov['sets'])}", "as_of": as_of,
               "missing": ", ".join(o.get("missing") or [])}
        for set_id in SETS:
            c = o["sets"].get(set_id)
            row[set_id.replace("-", "_")] = "–" if not c else f1(c["effective_mean"]) + (" †" if c["text_only"] else "")
        overall.append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "eval_overall.json").write_text(json.dumps(overall, ensure_ascii=False))
    (args.out / "eval_board.json").write_text(json.dumps(board, ensure_ascii=False))
    (args.out / "eval_grid.json").write_text(json.dumps(grid, ensure_ascii=False))
    (args.out / "eval_checks.json").write_text(json.dumps(
        [{"check": k, "short": CHECK_SHORT.get(k, k), "name": v} for k, v in sorted(checks.items())],
        ensure_ascii=False))
    print(f"{len(board)} board rows, {len(grid)} grid cells, {len(checks)} checks -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
