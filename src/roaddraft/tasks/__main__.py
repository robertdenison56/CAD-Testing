"""``python -m roaddraft.tasks SEED [--out DIR] [--curves N] [--equations] [--speed V]``

Generates a D1 task, runs the reference solution, and writes
``<task_id>.brief.json``, ``.truth.json``, ``.journal.jsonl``, ``.rdoc.json``,
``.xml`` (LandXML) and ``C-101.png`` into ``--out`` (default ``./tasks_out``),
then checks that the journal replays and prints how the reference document
matches the ground truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.ground_truth import match_truth
from roaddraft.tasks.reference import check_replay, reference_solution, session_for_task


def write_task(task, out_dir, render: bool = True) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tid = task.task_id
    (out / f"{tid}.brief.json").write_text(task.brief.to_json())
    (out / f"{tid}.truth.json").write_text(task.truth.to_json())
    session = session_for_task(task, out_dir=out)
    reference_solution(task, session)
    paths = {"brief": out / f"{tid}.brief.json", "truth": out / f"{tid}.truth.json"}
    for query, params, key in (
            ("save_journal", {"path": str(out / f"{tid}.journal.jsonl")}, "journal"),
            ("save_document", {"path": str(out / f"{tid}.rdoc.json")}, "document"),
            ("export_landxml", {"path": str(out / f"{tid}.xml")}, "landxml")):
        result = session.query(query, params)
        if not result["ok"]:
            raise SystemExit(f"{query} failed: {result['error']['message']}")
        paths[key] = Path(result["path"])
    if render:
        sheet = task.brief.deliverable["sheet_name"]
        result = session.query("render_sheet", {"sheet": sheet, "dpi": 150,
                                                "path": str(out / f"{tid}.{sheet}.png")})
        if not result["ok"]:
            raise SystemExit(f"render_sheet failed: {result['error']['message']}")
        paths["png"] = Path(result["path"])
    replay_ok = check_replay(session, out / f"{tid}.journal.jsonl")
    match = match_truth(session.doc, task.truth)
    return {"task_id": tid, "paths": paths, "replay_ok": replay_ok, "match": match,
            "warnings": session.reference_warnings, "commands": len(session.bus.journal)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.tasks",
                                     description="Generate a RoadDraft D1 task and its "
                                                 "reference solution")
    parser.add_argument("seed", type=int)
    parser.add_argument("--out", default="tasks_out", help="output directory")
    parser.add_argument("--curves", type=int, default=None, help="number of curves (1-3)")
    parser.add_argument("--equations", action="store_true", help="add a station equation")
    parser.add_argument("--speed", type=int, default=None, help="design speed (35..55 mph)")
    parser.add_argument("--no-render", action="store_true", help="skip the PNG render")
    ns = parser.parse_args(argv)
    task = generate_task(ns.seed, curves=ns.curves, equations=ns.equations,
                         design_speed_mph=ns.speed)
    report = write_task(task, ns.out, render=not ns.no_render)
    print(f"task {report['task_id']}: {task.brief.project['name']}, "
          f"{task.truth.counts['curves']} curve(s), {task.truth.counts['tangents']} tangents, "
          f"{task.truth.counts['equations']} equation(s), 1\"={task.brief.deliverable['feet_per_inch']:.0f}'")
    for key, path in report["paths"].items():
        print(f"  {key:9s} {path}")
    print(f"  reference: {report['commands']} commands, replay "
          f"{'OK' if report['replay_ok'] else 'DIVERGED'}, "
          f"{len(report['warnings'])} warning(s)")
    m = report["match"]
    print(f"  truth match: {m['matched']} matched, {len(m['missing'])} missing, "
          f"{len(m['extra'])} extra, {len(m['content_mismatch'])} content mismatches, "
          f"{len(m['position_mismatch'])} position mismatches")
    if not report["replay_ok"] or m["missing"] or m["content_mismatch"] or m["position_mismatch"]:
        print(json.dumps(m, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
