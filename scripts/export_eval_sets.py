"""Write just the eval sets' tasks to one Excel workbook: a sheet per set, each
task with its prompts, links to its starting files and start / finished pictures.

    PYTHONPATH=src uv run --no-project --python 3.9 --with openpyxl --with jsonschema \\
        --with ezdxf --with matplotlib python scripts/export_eval_sets.py \\
        [--out benchmarks/prompts/roaddraft_eval_sets.xlsx] [--fresh]

A cut of ``export_prompts.py`` (the full prompt workbook): the six task-set
manifests under ``benchmarks/tasksets`` and nothing else.  d1-dev and d1-test
(with d1-variance marked) are the seeded sets; d1-real and d1-real-dev the
tasks on the redrafted sample plan sheets; hard-pilots the 29 harder-task
pilots run as probe tasks.  The task files are the ones the full workbook
writes under ``benchmarks/prompts/tasks/`` (``eval/<set>/seed-<n>/``,
``real/<agency>/<sheet>/<alignment>/<type>/``, ``starts/<start>/`` and
``pilot/<id>/``); folders already written for the same task id are reused
unless ``--fresh`` is given.  Links are absolute ``file://`` paths to this
checkout, so a copy of the workbook opened from anywhere on this Mac still
reaches them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_prompts as ep  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

from roaddraft.eval import taskset as tasksets  # noqa: E402
from roaddraft.probes.pilot import PILOT_PROBES  # noqa: E402
from roaddraft.tasks.types import checks_in_scope, task_type  # noqa: E402

SEEDED_HEADS = ["Set", "#", "Seed", "Type", "Sheets", "Curves", "Station equation", "Task ID",
                "In d1-variance", "Starts with", "Checks graded", "Points", "EXPLICIT prompt",
                "VAGUE prompt", *ep.TASK_LINK_HEADS]
SEEDED_WIDTHS = [8, 5, 6, 16, 7, 7, 11, 24, 10, 36, 30, 7, 95, 40, *ep.TASK_LINK_WIDTHS]

REAL_HEADS = ["Set", "#", "Agency", "Sheet ID", "Sheet", "Scale", "Twist (deg)", "Alignment",
              "Type", "Task ID", "Starts with", "Checks graded", "Points", "EXPLICIT prompt",
              "VAGUE prompt", "Files", "Start", "Finished", "Redraft", "Base files",
              "Start (picture)", "Finished (picture)"]
REAL_WIDTHS = [10, 5, 14, 30, 16, 10, 7, 12, 18, 24, 40, 30, 7, 95, 40,
               *ep.TASK_LINK_WIDTHS[:4], 24, *ep.TASK_LINK_WIDTHS[4:]]

PILOT_HEADS = ["Set", "#", "Pilot", "Probe ID", "Task ID", "Family", "Task type", "Tags",
               "Starts from", "Prompt", "Note", *ep.PROBE_LINK_HEADS]
PILOT_WIDTHS = [10, 5, 22, 28, 30, 7, 20, 24, 16, 90, 60, *ep.PROBE_LINK_WIDTHS]


def seeded_rows(name: str, tasks_dir: Path, workbook_dir: Path) -> list:
    variance = {t["task_id"] for t in tasksets.load("d1-variance")["tasks"]}
    rows = []
    for i, entry in enumerate(tasksets.load(name)["tasks"], start=1):
        task = tasksets.task_from_entry(entry)
        ttype = task_type(entry["task_type"])
        graded = checks_in_scope(ttype.asks, list(ep.WEIGHTS))
        rows.append([
            name, i, entry["seed"], entry["task_type"], entry["sheets"], entry["curves"],
            "yes" if task.truth.counts["equations"] else
            ("asked, none fit" if entry["equations"] else "no"),
            entry["task_id"], "yes" if name == "d1-test" and entry["task_id"] in variance else "",
            ep._given(ttype), ", ".join(graded), sum(ep.WEIGHTS[c] for c in graded),
            task.brief.prompts["explicit"], task.brief.prompts["vague"],
            *ep.task_links(task, tasks_dir / "eval" / name / f"seed-{entry['seed']}",
                           workbook_dir)])
    return rows


def real_rows(name: str, catalog: dict, tasks_dir: Path, workbook_dir: Path) -> list:
    by_id = {t["task_id"]: t for t in catalog["tasks"]}
    rows = []
    for i, entry in enumerate(tasksets.load(name)["tasks"], start=1):
        task = tasksets.task_from_entry(entry)
        cat = by_id.get(entry["task_id"])
        if cat is None:
            raise SystemExit(f"{entry['task_id']} ({name}) is not in {ep.REAL_CATALOG}: "
                             "rerun scripts/real_tasks.py")
        ttype = task_type(entry["task_type"])
        graded = checks_in_scope(ttype.asks, list(ep.WEIGHTS))
        src = task.brief.deliverable["source"]
        folder = (tasks_dir / "real" / entry["agency"] / entry["sheet_id"]
                  / ("whole-sheet" if cat.get("per_sheet") else entry["alignment"].replace(" ", "-"))
                  / entry["task_type"])
        links = ep.task_links(task, folder, workbook_dir)
        source = Path(src["folder"])
        links.insert(4, ep.Link(source.name + "/", source.resolve().as_uri() + "/")
                     if source.exists() else src["folder"])
        rows.append([
            name, i, src["agency_name"], entry["sheet_id"], entry["sheet"],
            f"1\" = {entry['feet_per_inch']:g}'", entry["twist_deg"],
            "(whole sheet)" if cat.get("per_sheet") else entry["alignment"],
            entry["task_type"], entry["task_id"], ep._real_given(ttype), ", ".join(graded),
            sum(ep.WEIGHTS[c] for c in graded),
            task.brief.prompts["explicit"], task.brief.prompts["vague"], *links])
    return rows


def pilot_rows(name: str, tasks_dir: Path) -> list:
    pilots = {p.id: p for p in PILOT_PROBES}
    rows = []
    for i, entry in enumerate(tasksets.load(name)["tasks"], start=1):
        p = pilots[entry["probe"]]
        n = ep.pilot_number(p)
        rows.append([name, i, f"{n}. {ep.PILOT_NAMES.get(n, '')}", p.id, entry["task_id"],
                     entry["family"], entry["task_type"],
                     ", ".join(t for t in p.tags if t != "pilot"), p.start, p.prompt, p.note,
                     *ep.probe_links(p, ep.PILOT_REFS, "pilot", tasks_dir)])
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="benchmarks/prompts/roaddraft_eval_sets.xlsx")
    ap.add_argument("--fresh", action="store_true",
                    help="rebuild every task folder (default: reuse folders already written "
                         "for the same task id, only re-making the pictures)")
    ns = ap.parse_args(argv)
    ep.REUSE = not ns.fresh
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tasks_dir = out.parent / "tasks"
    if not ep.REAL_CATALOG.exists():
        raise SystemExit(f"{ep.REAL_CATALOG} is missing: run scripts/real_tasks.py first")
    catalog = json.loads(ep.REAL_CATALOG.read_text())
    sets = {name: tasksets.load(name) for name in tasksets.NAMES}
    root = str(tasks_dir.resolve())

    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    readme = [
        ("RoadDraft eval sets", None),
        (f"Every task the eval harness runs, as the manifests under benchmarks/tasksets pin "
         f"them, generated from the code on {dt.date.today().isoformat()}. Spec "
         f"{sets['d1-test']['spec_version']}, seeded generator "
         f"{sets['d1-test']['generator_version']}, real generator "
         f"{sets['d1-real']['generator_version']}.", None),
        ("", None),
        ("Sheet", "What it holds"),
        ("d1-dev", f"{len(sets['d1-dev']['tasks'])} seeded tasks on seeds 1-50, every dial mixed. "
                   "For iteration; never reported."),
        ("d1-test", f"{len(sets['d1-test']['tasks'])} held-out seeded tasks on seeds 1000-1099, "
                    "balanced over curves 1/2/3 and station equation on/off; the leaderboard set. "
                    f"In d1-variance marks the first {len(sets['d1-variance']['tasks'])}, the "
                    "d1-variance set sampled k = 5 times to size the interval."),
        ("d1-real", f"{len(sets['d1-real']['tasks'])} held-out tasks on the redrafted sample "
                    "plan sheets (Caltrans, FHWA WFL and CFL, FDOT), nine of each of the eleven "
                    "real-sheet types. Ranked beside d1-test."),
        ("d1-real-dev", f"{len(sets['d1-real-dev']['tasks'])} tasks, two of each real type, on "
                        "Caltrans sheets d1-real never uses. For smoke runs; never reported."),
        ("hard-pilots", f"The {len(sets['hard-pilots']['tasks'])} harder-task pilots run as probe "
                        "tasks: each its own start project on a sample sheet, graded pass or fail "
                        "by its own check. Ranked on its own board."),
        ("", None),
        ("Columns", None),
        ("Prompts", "Each seeded and real task has an EXPLICIT prompt (the request as a PE would "
                    "brief a drafter, naming the standards it is graded on; graded exactly) and a "
                    "VAGUE prompt (the request in a sentence; unstated conventions graded "
                    "leniently). A pilot has one prompt."),
        ("Files / Start / Finished", "Links to the task's folder and to full-size renders of what "
                                     "the drafter starts with and of the reference solution's "
                                     "finished sheet. Open start.rdoc.json in RoadDraft to see the "
                                     "starting document; finished.rdoc.json is the reference "
                                     "solution, reference.journal.jsonl how it was drawn."),
        ("Base files", "What the starting document attaches as references (NAME: file, anything "
                       "those attach in turn indented under them); the files sit beside "
                       "start.rdoc.json in the task's folder."),
        ("Redraft (real sets)", "The published redraft folder under examples/ the sheet and its "
                                "base files were copied from."),
        ("Pictures", "The start and finished renders as pictures (both sheets side by side on a "
                     "two-sheet task). Click a picture and enlarge it to read it; the full "
                     "renders are the Start and Finished links."),
        ("Pilots", "Start files links the pilot's start project (tasks/starts/<start>/), "
                   "Reference its scripted solution's folder and PDF; Scripted solution says "
                   "whether that solution passes the pilot's own check."),
        ("Task files", f"{root}/eval/<set>/seed-<n>/ (seeded), {root}/real/<agency>/<sheet>/"
                       f"<alignment>/<type>/ (real), {root}/starts/<start>/ and {root}/pilot/"
                       "<id>/ (pilots). The links are absolute paths on this Mac; if one does not "
                       "open, paste the path into Finder's Go to Folder."),
    ]
    for r, (a, b) in enumerate(readme, start=1):
        ws.cell(row=r, column=1, value=a).font = Font(
            name=ep.FONT, bold=(b is None and bool(a)) or r == 4, size=14 if r == 1 else 10)
        if b is not None:
            c = ws.cell(row=r, column=2, value=b)
            c.font = Font(name=ep.FONT, size=10, bold=(r == 4))
            c.alignment = ep.TOP_WRAP
            ws.row_dimensions[r].height = 13.5 * ep._lines(b, 110) + 4
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110

    counts = {}
    for name in ("d1-dev", "d1-test"):
        print(f"{name}: {len(sets[name]['tasks'])} tasks")
        rows = seeded_rows(name, tasks_dir, out.parent)
        ep._table(wb.create_sheet(name), SEEDED_HEADS, SEEDED_WIDTHS, rows,
                  wrap_cols=(10, 11, 13, 14, 17))
        counts[name] = len(rows)
    for name in ("d1-real", "d1-real-dev"):
        print(f"{name}: {len(sets[name]['tasks'])} tasks")
        rows = real_rows(name, catalog, tasks_dir, out.parent)
        ep._table(wb.create_sheet(name), REAL_HEADS, REAL_WIDTHS, rows,
                  wrap_cols=(11, 12, 14, 15, 20))
        counts[name] = len(rows)
    print(f"hard-pilots: {len(sets['hard-pilots']['tasks'])} tasks")
    rows = pilot_rows("hard-pilots", tasks_dir)
    ep._table(wb.create_sheet("hard-pilots"), PILOT_HEADS, PILOT_WIDTHS, rows,
              wrap_cols=(3, 7, 8, 10, 11, 12, 13))
    counts["hard-pilots"] = len(rows)
    for ws in wb.worksheets[1:]:
        ws.row_dimensions[1].height = 42

    wb.save(out)
    print(f"wrote {out}: " + ", ".join(f"{k} {v}" for k, v in counts.items())
          + f"; task files under {tasks_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
