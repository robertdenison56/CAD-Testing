"""The harness CLI.

    python -m roaddraft.eval run --taskset d1-dev --agent oracle [--agent null ...]
        [--level explicit --level vague] [--mode single] [--samples 1] [--limit N]
        [--task ID ...] [--out results] [--run-id ID] [--concurrency 4] [--dry-run]
        [--journal FILE]                              # for --agent replay
    python -m roaddraft.eval taskset [NAME ...] [--write | --check]
    python -m roaddraft.eval verify EPISODE.jsonl [--level L] [--json]
    python -m roaddraft.eval verify DOCUMENT --task ID [--taskset d1-dev] [--journal J] [--level L]
    python -m roaddraft.eval human start --task ID [--taskset d1-dev] --out DIR [--level L]
    python -m roaddraft.eval human score DIR [--journal J] [--level L] [--expert benchmarks/expert]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import AGENTS, ReplayAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import Episode, EpisodeConfig
from roaddraft.eval.runner import RunSpec, matrix, run
from roaddraft.eval.tools import MODES
from roaddraft.eval.trajectory import read_episode, reverify
from roaddraft.tasks.prompts import LEVELS, task_text

EXPERT_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "expert"


def _print_report(report, as_json: bool) -> None:
    if as_json:
        print(report.to_json(indent=1))
        return
    print(f"effective {report.effective_score:.2f}  rubric {report.rubric_score:.2f}  "
          f"hard_failed {report.hard_failed}  scope {', '.join(report.scope)}")
    for c in report.in_scope():
        line = f"  {c.id} {c.status:8s} credit {c.credit:.2f} x {c.weight}"
        if c.findings:
            line += "  " + "; ".join(f"{f.code}" + (f" {f.to_dict(strip=True).get('anchor')}"
                                                   if f.to_dict(strip=True).get("anchor") else "")
                                   for f in c.findings[:4])
        print(line)


def cmd_run(args) -> int:
    spec = RunSpec(taskset=args.taskset, agents=tuple(args.agent or ["oracle"]),
                   levels=tuple(args.level or ["explicit"]), modes=tuple(args.mode or ["single"]),
                   samples=args.samples, limit=args.limit, task_ids=args.task or None,
                   results_root=args.out, run_id=args.run_id, concurrency=args.concurrency,
                   budgets=Budgets(steps=args.steps, wall_clock_s=args.wall_clock * 60),
                   journal=args.journal)
    cells = matrix(spec)
    if args.dry_run:
        print(f"run {spec.resolved_run_id()}: {len(cells)} episodes -> {spec.out_root}")
        for c in cells[:20]:
            print(f"  {c.task_id} {c.entry['task_type']} {c.entry['sheets']}sh {c.agent} "
                  f"{c.level} {c.mode} s{c.sample}")
        if len(cells) > 20:
            print(f"  ... {len(cells) - 20} more")
        return 0
    summary = run(spec, progress=lambda s: print(s, flush=True))
    print(f"\nrun {summary['run_id']}: {summary['episodes']} episodes, {summary['skipped']} resumed, "
          f"{len(summary['failures'])} failed to start")
    for key, g in summary["groups"].items():
        print(f"  {g['agent']:9s} {g['level']:8s} {g['mode']:12s} n={g['n']:3d} "
              f"effective {g['mean_effective']:6.2f} rubric {g['mean_rubric']:6.2f} "
              f"hard-fail {g['hard_fail_rate']:.0%} clean {g['clean_sheet_rate']:.0%} "
              f"submit {g['submit_rate']:.0%} steps {g['median_steps']}"
              + (f" errors {g['errors']}" if g['errors'] else ""))
    return 1 if summary["failures"] else 0


def cmd_taskset(args) -> int:
    names = args.names or list(tasksets.NAMES)
    rc = 0
    for name in names:
        if args.write:
            path = tasksets.write(name)
            m = tasksets.load(name)
            print(f"{name}: {len(m['tasks'])} tasks, {m['generator_version']} {m['spec_hash'][:19]} -> {path}")
        else:
            try:
                problems = tasksets.check(name)
            except FileNotFoundError as exc:
                print(f"{name}: {exc}")
                rc = 1
                continue
            m = tasksets.load(name)
            if problems:
                rc = 1
                print(f"{name}: STALE ({len(m['tasks'])} tasks): " + "; ".join(problems))
            else:
                print(f"{name}: current, {len(m['tasks'])} tasks, {m['generator_version']} {m['spec_hash'][:19]}")
    return rc


def cmd_verify(args) -> int:
    target = Path(args.target)
    if target.suffix == ".jsonl" and not args.task:
        report = reverify(target, level=args.level)
        rec = read_episode(target)["end"] or {}
        _print_report(report, args.json)
        if rec and not args.json:
            print(f"  (the episode's own verify said effective {rec.get('effective_score')})")
        return 0
    if not args.task:
        print("verify: a document needs --task ID (and --taskset)", file=sys.stderr)
        return 2
    from roaddraft.document.document import Document
    from roaddraft.document.fileformat import read_document
    from roaddraft.verify import read_journal, verify
    entry = next((e for e in tasksets.entries(args.taskset) if e["task_id"] == args.task), None)
    if entry is None:
        print(f"verify: task {args.task} is not in {args.taskset}", file=sys.stderr)
        return 2
    task = tasksets.task_from_entry(entry)
    doc = Document.from_dict(read_document(target))
    journal = read_journal(args.journal) if args.journal else None
    report = verify(doc, task.truth, journal=journal, prompt_level=args.level or "explicit")
    _print_report(report, args.json)
    return 0


def _find_entry(task_id: str, taskset: Optional[str]) -> dict:
    names = [taskset] if taskset else list(tasksets.NAMES)
    for name in names:
        try:
            rows = tasksets.entries(name, task_ids=[task_id])
        except FileNotFoundError:
            continue
        if rows:
            return rows[0]
    raise SystemExit(f"task {task_id} is not in {', '.join(names)}")


def cmd_human(args) -> int:
    from roaddraft.tasks.reference import session_for_task
    level = args.level or "explicit"
    if args.action == "start":
        entry = _find_entry(args.task, args.taskset)
        task = tasksets.task_from_entry(entry)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        session = session_for_task(task, out_dir=out)
        doc_path = out / f"{task.task_id}.rdoc.json"
        result = session.query("save_document", {"path": str(doc_path)})
        if not result["ok"]:
            raise SystemExit(result["error"]["message"])
        text = task_text(task.brief, level)
        (out / "PROMPT.md").write_text(
            f"# {task.task_id}  ({entry['task_type']}, {entry['sheets']} sheet"
            f"{'s' if entry['sheets'] > 1 else ''}, {level} prompt)\n\n"
            f"Open `{doc_path.name}` in RoadDraft, do the task below, and save it over the same "
            f"file. If the GUI or REPL lets you, save the journal beside it as "
            f"`{task.task_id}.journal.jsonl` (REPL: `journal {task.task_id}.journal.jsonl`).\n"
            f"Then: `python -m roaddraft.eval human score {out}`\n\n---\n\n{text}\n")
        (out / "task.json").write_text(json.dumps({**entry, "level": level,
                                                   "taskset": args.taskset}, indent=1))
        print(f"{task.task_id}: {doc_path}\n{out / 'PROMPT.md'}")
        return 0
    # score
    folder = Path(args.target)
    meta = json.loads((folder / "task.json").read_text())
    level = args.level or meta.get("level", "explicit")
    task = tasksets.task_from_entry(meta)
    doc_path = folder / f"{task.task_id}.rdoc.json"
    journal_path = Path(args.journal) if args.journal else folder / f"{task.task_id}.journal.jsonl"
    expert = Path(args.expert) / task.task_id
    expert.mkdir(parents=True, exist_ok=True)
    if journal_path.exists():
        agent = ReplayAgent(journal_path, name="human")
        config = EpisodeConfig(level=level, mode="self_correct", run_id="human",
                               budgets=Budgets(steps=10000, faults=10000, wall_clock_s=0))
        result = Episode(task, agent, config, out_root=expert).run()
        report = result.report
        shutil.copy(journal_path, expert / journal_path.name)
        print(f"replayed {journal_path.name} through the loop: {result.steps} steps, "
              f"{result.faults} faults, termination {result.termination}")
        print(f"episode: {result.path}")
    else:
        from roaddraft.document.document import Document
        from roaddraft.document.fileformat import read_document
        from roaddraft.verify import verify
        if not doc_path.exists():
            raise SystemExit(f"no saved document at {doc_path}")
        doc = Document.from_dict(read_document(doc_path))
        report = verify(doc, task.truth, prompt_level=level)
        print("no journal beside the document: the document alone was verified")
    shutil.copy(doc_path, expert / doc_path.name)
    (expert / "verify.json").write_text(report.to_json(indent=1))
    (expert / "PROMPT.md").write_text((folder / "PROMPT.md").read_text()
                                      if (folder / "PROMPT.md").exists() else task_text(task.brief, level))
    _print_report(report, args.json)
    print(f"recorded under {expert}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.eval",
                                     description="the RoadDraft evaluation harness")
    subs = parser.add_subparsers(dest="command")

    p = subs.add_parser("run", help="run a matrix of episodes")
    p.add_argument("--taskset", default="d1-dev", help="a task set (benchmarks/tasksets)")
    p.add_argument("--agent", action="append", help=f"one of {', '.join(sorted(AGENTS))}, replay")
    p.add_argument("--level", action="append", choices=list(LEVELS), help="prompt level(s)")
    p.add_argument("--mode", action="append", choices=list(MODES))
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--limit", type=int, help="the first N tasks of the set")
    p.add_argument("--task", action="append", help="task id(s) to run")
    p.add_argument("--out", default="results", help="results root (gitignored)")
    p.add_argument("--run-id")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--steps", type=int, default=Budgets.steps, help="step budget per episode")
    p.add_argument("--wall-clock", type=float, default=Budgets.wall_clock_s / 60,
                   help="minutes per episode")
    p.add_argument("--journal", help="replay agent: the journal to replay")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)

    p = subs.add_parser("taskset", help="check or regenerate the task-set manifests")
    p.add_argument("names", nargs="*")
    p.add_argument("--write", action="store_true", help="regenerate the manifest(s)")
    p.add_argument("--check", action="store_true", help="(default) report stale manifests")
    p.set_defaults(func=cmd_taskset)

    p = subs.add_parser("verify", help="re-score an episode file, or score a saved document")
    p.add_argument("target", help="an episode .jsonl, or a saved document")
    p.add_argument("--task", help="task id (for a document)")
    p.add_argument("--taskset", default="d1-dev")
    p.add_argument("--journal")
    p.add_argument("--level", choices=list(LEVELS))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = subs.add_parser("human", help="set up a task for a human playtest, or score one")
    p.add_argument("action", choices=["start", "score"])
    p.add_argument("target", nargs="?", help="score: the playtest folder")
    p.add_argument("--task", help="start: the task id")
    p.add_argument("--taskset", default=None)
    p.add_argument("--out", help="start: the playtest folder to write")
    p.add_argument("--level", choices=list(LEVELS))
    p.add_argument("--journal", help="score: the journal, if not beside the document")
    p.add_argument("--expert", default=str(EXPERT_DIR), help="score: where the record goes")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_human)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    if args.command == "human":
        if args.action == "start" and not (args.task and args.out):
            parser.error("human start needs --task ID and --out DIR")
        if args.action == "score" and not args.target:
            parser.error("human score needs the playtest folder")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
