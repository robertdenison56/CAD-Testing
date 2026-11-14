"""``python -m roaddraft.tasks SEED [--out DIR] [--type T] [--sheets N] [--curves N] [--equations] [--speed V] [--twist [DEG]] [--crowd] [--revise [KIND]]``

Generates a D1 task, runs the reference solution on its starting document,
and writes ``<task_id>.brief.json``, ``.truth.json``, ``.journal.jsonl``,
``.rdoc.json``, ``.xml`` (LandXML) and a PNG per sheet into ``--out``
(default ``./tasks_out``), then checks that the journal replays and prints
how the reference document matches the ground truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.ground_truth import match_truth
from roaddraft.tasks.reference import check_replay, reference_solution, session_for_task
from roaddraft.tasks.types import DEFAULT_TYPE, TASK_TYPES


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
        if key == "landxml" and not session.doc.design.alignments:
            continue  # a sheet file whose design lives in its base drawing has none to export
        result = session.query(query, params)
        if not result["ok"]:
            raise SystemExit(f"{query} failed: {result['error']['message']}")
        paths[key] = Path(result["path"])
    if render:
        for sh in task.brief.deliverable["sheets"]:
            if session.doc.sheet_by_ref(sh["name"]) is None:
                continue  # a model-only task has no sheet to plot yet
            result = session.query("render_sheet", {"sheet": sh["name"], "dpi": 150,
                                                    "path": str(out / f"{tid}.{sh['name']}.png")})
            if not result["ok"]:
                raise SystemExit(f"render_sheet failed: {result['error']['message']}")
            paths[f"png {sh['name']}"] = Path(result["path"])
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
    parser.add_argument("--type", default=DEFAULT_TYPE, choices=sorted(TASK_TYPES),
                        help="task type: what is given and what is asked for")
    parser.add_argument("--sheets", type=int, default=1, help="plan sheets (1 or 2)")
    parser.add_argument("--curves", type=int, default=None, help="number of curves (1-3)")
    parser.add_argument("--equations", action="store_true", help="add a station equation")
    parser.add_argument("--speed", type=int, default=None, help="design speed (35..55 mph)")
    parser.add_argument("--twist", nargs="?", const=True, default=False, type=float,
                        help="turn the sheets' viewports: the seed's own twist, or DEG degrees")
    parser.add_argument("--crowd", action="store_true",
                        help="hand the task over on a sheet already worked on: a second "
                             "lettered line and notes on the paper (tasks.crowd)")
    parser.add_argument("--revise", nargs="?", const=True, default=None,
                        choices=[True, "radius", "pi", "station", "base-radius", "base-pi",
                                 "base-station"],
                        help="hand the task over finished after its design has changed: the "
                             "seed's own kind of change, or KIND (tasks.revise); base-KIND "
                             "leaves the change for the drafter to make in the base drawing "
                             "(--type annotate-base)")
    parser.add_argument("--no-render", action="store_true", help="skip the PNG render")
    ns = parser.parse_args(argv)
    task = generate_task(ns.seed, curves=ns.curves, equations=ns.equations,
                         design_speed_mph=ns.speed, task_type=ns.type, sheets=ns.sheets,
                         twist=ns.twist, crowd=ns.crowd, revise=ns.revise)
    report = write_task(task, ns.out, render=not ns.no_render)
    print(f"task {report['task_id']} ({ns.type}, {ns.sheets} sheet(s)): "
          f"{task.brief.project['name']}, {task.truth.counts['curves']} curve(s), "
          f"{task.truth.counts['tangents']} tangents, {task.truth.counts['equations']} "
          f"equation(s), 1\"={task.brief.deliverable['feet_per_inch']:.0f}'"
          + (f", viewports turned {task.brief.deliverable['view_rotation']:.2f}°"
             if task.brief.deliverable.get("view_rotation") else "")
          + (f", crowded ({len(task.brief.deliverable['crowd']['notes'])} note(s) and "
             f"{task.brief.deliverable['crowd']['alignment']['name']})"
             if task.brief.deliverable.get("crowd") else "")
          + (f", revised ({task.brief.deliverable['revision']['kind']}, "
             f"{len(task.brief.deliverable['revision']['notes'])} note(s) to restation)"
             if task.brief.deliverable.get("revision") else ""))
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
