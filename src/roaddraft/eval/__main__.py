"""The harness CLI.

    python -m roaddraft.eval run --taskset d1-dev --agent oracle [--agent null ...]
        [--level explicit --level vague] [--mode single] [--samples 1] [--limit N]
        [--task ID ...] [--out results] [--run-id ID] [--concurrency 4] [--dry-run]
        [--journal FILE]                              # for --agent replay
    python -m roaddraft.eval run --taskset d1-dev --model claude-sonnet-5-5 [--model ...]
        [--provider anthropic|openai|fake|claude-code|codex] [--effort high] [--max-tokens N]
        [--strict] [--base-url URL] [--api-key-env VAR] [--extra-body JSON] [--lms-context N]
        [--dialect neutral] [--cost-cap USD] [--output-tokens N]
        [--context-tokens N] ...                      # defaults to --lms-context
        [--system-extra FILE]                         # appended to every model's system prompt (T0)
        [--thinking off]                              # openai: the think block closed (a no-think base)
        [--claude-bin PATH] [--claude-arg ARG ...] [--max-budget-usd D]   # --provider claude-code
        [--codex-bin PATH] [--codex-arg ARG ...]                          # --provider codex
    python -m roaddraft.eval taskset [NAME ...] [--write | --check]
    python -m roaddraft.eval verify EPISODE.jsonl [--level L] [--json]
    python -m roaddraft.eval verify DOCUMENT --task ID [--taskset d1-dev] [--journal J] [--level L]
    python -m roaddraft.eval human start --task ID [--taskset d1-dev] --out DIR [--level L]
    python -m roaddraft.eval human score DIR [--journal J] [--level L] [--expert benchmarks/expert]
    python -m roaddraft.eval report results/RUN [--out DIR] [--reverify] [--no-check-delta]
        [--publish [--allow-unrankable]] [--runs benchmarks/runs]
    python -m roaddraft.eval t2 plan RUN_DIR [RUN_DIR ...] --round 1 [--size 600] [--name d1-train-t2-r1]
        [--floor 0.25] [--level L] [--flavour F ...] [--root DIR] [--dry-run] [--force]
    python -m roaddraft.eval t2 check [NAME ...] [--root DIR]
    python -m roaddraft.eval run --taskset d1-train-t2-r1 [--tasksets-root DIR] ...
"""
from __future__ import annotations

from dataclasses import replace

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
from roaddraft.eval.prompts import SystemExtra
from roaddraft.eval.tools import DIALECTS
from roaddraft.eval.providers import PROVIDERS
from roaddraft.eval.runner import ResumeMismatch, RunSpec, make_agent, matrix, measured_cost, run
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


def _models(values: Optional[List[str]]) -> List[str]:
    """``--model a,b --model c`` as ``[a, b, c]``."""
    return [m.strip() for v in values or [] for m in v.split(",") if m.strip()]


def _budgets(args) -> Budgets:
    """The run's budgets: the task set's defaults (a probe set takes Track P's,
    taskset.default_budgets), with any the command line set.  The context
    budget is ``--context-tokens``, else the window ``--lms-context`` loads
    the model at, so a local row trips on an oversize prompt as a hosted
    row's server refuses one."""
    base = tasksets.default_budgets(args.taskset)
    context = args.context_tokens if args.context_tokens is not None else args.lms_context
    return replace(base, **{k: v for k, v in (("steps", args.steps),
                                             ("wall_clock_s", None if args.wall_clock is None
                                              else args.wall_clock * 60),
                                             ("output_tokens", args.output_tokens),
                                             ("context_tokens", context))
                            if v is not None})


def cmd_run(args) -> int:
    models = _models(args.model)
    options = {"effort": args.effort, "max_tokens": args.max_tokens, "base_url": args.base_url,
               "api_key_env": args.api_key_env, "lms_context": args.lms_context,
               "extra_body": json.loads(args.extra_body) if args.extra_body else None,
               "send_reasoning": True if args.send_reasoning else None, "thinking": args.thinking,
               "claude_bin": args.claude_bin, "claude_args": args.claude_arg or None,
               "max_budget_usd": args.max_budget_usd,
               "codex_bin": args.codex_bin, "codex_args": args.codex_arg or None}
    if args.strict:
        options["strict"] = True
    task_ids = args.task or None
    extra = None
    if args.system_extra:
        if args.agent or not models:
            print("run: --system-extra goes into a model's system prompt; the oracle, null, scripted "
                  "and replay agents have none, so run it with --model only", file=sys.stderr)
            return 2
        try:
            extra = SystemExtra.load(args.system_extra)
        except ValueError as ex:
            print(f"run: {ex}", file=sys.stderr)
            return 2
    if args.thinking:
        from roaddraft.eval import providers
        others = sorted({args.provider or providers.infer(m) for m in models} - {"openai"})
        if args.agent or not models or others or args.effort:
            why = ("it does not combine with --effort (both set reasoning_effort)" if args.effort else
                   "run it with --model on the openai provider only"
                   + (f" (not {', '.join(others)})" if others else ""))
            print(f"run: --thinking is a request field of an OpenAI-compatible server; {why}", file=sys.stderr)
            return 2
    if args.subset:
        if args.limit:
            print("run: --subset takes the subset's tasks; it does not combine with --limit",
                  file=sys.stderr)
            return 2
        from roaddraft.eval.subsets import subset_ids
        try:
            task_ids = subset_ids(args.taskset, args.subset)
        except ValueError as ex:
            print(f"run: {ex}", file=sys.stderr)
            return 2
        if args.task:   # part of the subset (a text-only model's text pilots): the report says what it holds
            stray = [t for t in args.task if t not in set(task_ids)]
            if stray:
                print(f"run: --task with --subset takes the subset's own tasks; not in {args.subset}: "
                      f"{', '.join(stray[:5])}", file=sys.stderr)
                return 2
            task_ids = [t for t in task_ids if t in set(args.task)]
    spec = RunSpec(taskset=args.taskset,
                   agents=tuple(args.agent or ([] if models else ["oracle"])),
                   levels=tuple(args.level or ["explicit"]), modes=tuple(args.mode or ["single"]),
                   samples=args.samples, limit=args.limit, task_ids=task_ids, subset=args.subset,
                   results_root=args.out, run_id=args.run_id, concurrency=args.concurrency,
                   budgets=_budgets(args),
                   journal=args.journal, models=tuple(models), provider=args.provider,
                   provider_options={k: v for k, v in options.items() if v is not None},
                   dialects=tuple(args.dialect or ["neutral"]), cost_cap=args.cost_cap,
                   system_extra=extra, tasksets_root=args.tasksets_root)
    cells = matrix(spec)
    if args.dry_run:
        print(f"run {spec.resolved_run_id()}: {len(cells)} episodes -> {spec.out_root}")
        for c in cells[:20]:
            print(f"  {c.task_id} {c.entry['task_type']} {c.entry['sheets']}sh {c.agent} "
                  f"{c.level} {c.mode}" + (f" {c.dialect}" if c.dialect != "neutral" else "")
                  + f" s{c.sample}")
        if len(cells) > 20:
            print(f"  ... {len(cells) - 20} more")
        for model in models:
            n = sum(c.agent == model for c in cells)
            seen = measured_cost(model, spec.results_root)
            if seen:
                print(f"  {model}: {n} episodes x ${seen['mean_cost_usd']:.3f} measured over "
                      f"{seen['n']} = ${n * seen['mean_cost_usd']:.2f} projected")
            else:
                print(f"  {model}: {n} episodes, no measured cost yet")
        if spec.cost_cap is not None:
            print(f"  cost cap ${spec.cost_cap:.2f}")
        if extra is not None:
            print(f"  system extra {extra.path} {extra.sha256[:19]}: {len(extra.text.strip())} "
                  "characters after every model's system prompt")
        if args.thinking:
            print(f"  thinking {args.thinking}: every request asks the server for it")
        return 0
    for model in models:   # fail before the matrix, not once per cell
        try:
            make_agent(model, spec)
        except (RuntimeError, ValueError) as exc:
            print(f"run: {model}: {exc}", file=sys.stderr)
            return 2
    if args.provider == "codex" and spec.concurrency > 1 and models:
        print("codex: a ChatGPT Plus account answers parallel runs with 429s; "
              "--concurrency 1 runs them one at a time", file=sys.stderr)
    try:
        summary = run(spec, progress=lambda s: print(s, flush=True))
    except ResumeMismatch as exc:
        print(f"run: {exc}", file=sys.stderr)
        return 2
    print(f"\nrun {summary['run_id']}: {summary['episodes']} episodes, {summary['skipped']} resumed, "
          f"{len(summary['failures'])} failed to start"
          + (f", ${summary['spent_usd']:.2f} spent" if summary.get("spent_usd") else "")
          + (f", stopped at the cost cap with {summary['not_run']} not run"
             if summary.get("stopped") == "cost_cap" else ""))
    for key, g in summary["groups"].items():
        print(f"  {g['agent']:9s} {g['level']:8s} {g['mode']:12s}"
              + (f" {g['dialect']}" if g.get("dialect", "neutral") != "neutral" else "")
              + f" n={g['n']:3d} "
              f"effective {g['mean_effective']:6.2f} rubric {g['mean_rubric']:6.2f} "
              f"hard-fail {g['hard_fail_rate']:.0%} clean {g['clean_sheet_rate']:.0%} "
              f"submit {g['submit_rate']:.0%} steps {g['median_steps']}"
              + (f" invalid {g['invalid_call_rate']:.1%}" if g.get("invalid_call_rate") else "")
              + (f" ${g['mean_cost_usd']:.3f}/ep" if g.get("mean_cost_usd") is not None else "")
              + (f" errors {g['errors']}" if g['errors'] else ""))
    return 1 if summary["failures"] else 0


def cmd_taskset(args) -> int:
    names = args.names or list(tasksets.NAMES)
    rc = 0
    for name in names:
        check = tasksets.check
        if tasksets.is_t2(name):   # a T2 round's manifest: planned from a run, checked from its own record
            from roaddraft.eval import t2
            check = t2.check
            if args.write:
                print(f"{name}: a T2 round's manifest is planned from a checkpoint's run, not "
                      "generated by name: python -m roaddraft.eval t2 plan")
                rc = 1
                continue
        if args.write:
            path = tasksets.write(name)
            m = tasksets.load(name)
            print(f"{name}: {len(m['tasks'])} tasks, {m['generator_version']} {m['spec_hash'][:19]} -> {path}")
        else:
            try:
                problems = check(name)
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
    if "probe" in entry:
        print("verify: a probe task is graded by its own check, not the D1 verifier: run it with python -m roaddraft.eval run --taskset hard-pilots, or set one up for a person with python -m roaddraft.probes setup", file=sys.stderr)
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
        if "probe" in entry:
            print("human: a probe task is graded by its own check, not the D1 verifier: run it with python -m roaddraft.eval run --taskset hard-pilots, or set one up for a person with python -m roaddraft.probes setup", file=sys.stderr)
            return 2
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


def cmd_report(args) -> int:
    from roaddraft.eval import report as reports
    run_dir = Path(args.run_dir)
    summary = reports.build(run_dir, reverify=args.reverify, check_delta=not args.no_check_delta)
    out = Path(args.out) if args.out else run_dir / "report"
    reports.write(summary, out)
    print(f"run {summary['run_id']} ({summary.get('taskset')}): {summary['episodes']} episodes"
          + (f", {len(summary['incomplete'])} without an end record" if summary["incomplete"] else "")
          + (", re-scored with the current verifier" if summary["reverified"] else ""))
    for g in summary["rows"]:
        ci = (f"{g['ci_low']:.1f}-{g['ci_high']:.1f}" if g["ci_low"] is not None else "-")
        print(f"  {g['rank']:2d} {g['label']:40s} effective {g['effective_mean']:6.2f} [{ci}] "
              f"rubric {g['rubric_mean']:6.2f} hard-fail {g['hard_fail_rate']:.0%} "
              f"n={g['n_tasks']}x{g['k_max']}" + (f" errors {g['errors']}" if g["errors"] else ""))
    for p in summary["publish_problems"]:
        print(f"  not rankable: {p}")
    if summary.get("partial"):
        c = summary["coverage"]
        print(f"  partial: {c['tasks_run']} of the set's {c['tasks_in_set']} tasks; "
              "published and listed, ranked once the run holds them all")
    print(f"-> {out}")
    if args.publish:
        try:
            dest = reports.publish(summary, out, runs_root=args.runs or reports.RUNS_DIR,
                                   allow_unrankable=args.allow_unrankable)
        except ValueError as exc:
            print(f"publish: {exc}", file=sys.stderr)
            return 1
        print(f"published -> {dest}  (then: python scripts/make_leaderboard.py)")
    return 0


def cmd_standards(args) -> int:
    from roaddraft.eval import standards
    run_dir = Path(args.run_dir)
    explicit = Path(args.explicit) if args.explicit else (None if args.no_pair else standards.find_explicit(run_dir))
    s = standards.analyse(run_dir, explicit)
    if not s["tasks"]:
        print(f"{run_dir}: no finished episode", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else run_dir / "report"
    standards.write(s, out)
    print(f"{s['run_id']}: {s['tasks']} tasks, mean effective {s['effective_mean']:.1f}, "
          f"{s['lost_per_task']:.1f} points a task lost"
          + (f"; paired with {s['explicit_run_id']} on {s['paired_tasks']} tasks" if s["paired_tasks"] else ""))
    for k in ("standard", "work", "hard_fail", "ended_early"):
        pts = s["by_kind"].get(k, 0.0)
        rec = (s["recovered_by_kind"] or {}).get(k)
        print(f"  {standards.KIND_WORDS[k]:42s} {pts:5.1f}" + ("" if rec is None else f"  recovered when told {rec:5.1f}"))
    print(f"-> {out / 'standards.md'}")
    return 0


def cmd_delta(args) -> int:
    from roaddraft.eval import delta as deltas
    try:
        d = deltas.delta(deltas.load_summary(args.run_dir), deltas.load_summary(args.base_dir),
                         row=args.row, base_row=args.base_row)
    except (FileNotFoundError, ValueError) as exc:
        print(f"delta: {exc}", file=sys.stderr)
        return 1
    text = deltas.render(d)
    print(text)
    if args.out:
        out = Path(args.out)
        out.write_text(text, encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
        print(f"-> {out}")
    return 0


def cmd_causes(args) -> int:
    from roaddraft.eval import causes
    rows = []
    for rd in args.run_dirs:
        run_dir = Path(rd)
        explicit = None if args.no_pair else causes.find_explicit(run_dir)
        s = causes.analyse(run_dir, explicit)
        if not s["tasks"]:
            print(f"{run_dir}: no finished episode", file=sys.stderr)
            continue
        if not args.no_write:
            causes.write(s, run_dir / "report")
        rows.append(s)
        b = s["by_cause"]
        print(f"{s['run_id']}: {s['tasks']} tasks, effective {s['effective_mean']:.1f}, lost {s['lost_per_task']:.1f}"
              f" = standard {b['standard']:.1f}, tool use {b['tool_use']:.1f}, reasoning {b['reasoning']:.1f},"
              f" budget {b['budget']:.1f}" + (f", unresolved {b['unresolved']:.1f}" if b["unresolved"] else "")
              + (f"  [paired with {s['explicit_run_id']}]" if s["paired_tasks"] else ""))
    if args.table and rows:
        Path(args.table).write_text(causes.render_table(rows), encoding="utf-8")
        print(f"-> {args.table}")
    return 0 if rows else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.eval",
                                     description="the RoadDraft evaluation harness")
    subs = parser.add_subparsers(dest="command")

    p = subs.add_parser("run", help="run a matrix of episodes")
    p.add_argument("--taskset", default="d1-dev", help="a task set (benchmarks/tasksets)")
    p.add_argument("--tasksets-root", metavar="DIR",
                   help="read the task set's manifest from DIR (default benchmarks/tasksets): "
                        "a T2 round's manifest written elsewhere (eval t2 plan --root)")
    p.add_argument("--agent", action="append", help=f"one of {', '.join(sorted(AGENTS))}, replay")
    p.add_argument("--level", action="append", choices=list(LEVELS), help="prompt level(s)")
    p.add_argument("--mode", action="append", choices=list(MODES))
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--limit", type=int, help="the first N tasks of the set")
    p.add_argument("--task", action="append", help="task id(s) to run")
    p.add_argument("--subset", help="a cost subset of the set (eval/subsets.py, e.g. cost5): its tasks only, "
                                    "recorded in run.json; the board ranks it, tagged partial, from a Runpod route")
    p.add_argument("--out", default="results", help="results root (gitignored)")
    p.add_argument("--run-id")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--steps", type=int, help=f"step budget per episode (default "
                                              f"{Budgets.steps}; a probe set's own)")
    p.add_argument("--wall-clock", type=float, help=f"minutes per episode (default "
                                                    f"{Budgets.wall_clock_s / 60:g}; a probe set's own)")
    p.add_argument("--journal", help="replay agent: the journal to replay")
    p.add_argument("--model", action="append",
                   help="model id(s) to run as LLM agents (comma-separated or repeated)")
    p.add_argument("--provider", choices=sorted(PROVIDERS),
                   help="default: anthropic for claude-*, fake for fake*, else openai; "
                        "claude-code and codex (a signed-in CLI on a subscription) by name only")
    p.add_argument("--effort", help="low | medium | high | xhigh | max (anthropic default high)")
    p.add_argument("--max-tokens", type=int, help="output tokens per model turn")
    p.add_argument("--strict", action="store_true",
                   help="anthropic: strict: true on the tools whose schemas are closed")
    p.add_argument("--base-url", help="openai: the endpoint (default LM Studio, localhost:1234/v1)")
    p.add_argument("--api-key-env", help="openai: the variable holding the key (OPENAI_API_KEY)")
    p.add_argument("--extra-body", help="openai: JSON merged into every request")
    p.add_argument("--lms-context", type=int, help="openai: LM Studio reload guard at this context")
    p.add_argument("--send-reasoning", action="store_true",
                   help="openai: a turn's reasoning goes back with its tool calls (gpt-oss: harmony wants it)")
    p.add_argument("--claude-bin", help="claude-code: the CLI to run (default: PATH, then the app's)")
    p.add_argument("--claude-arg", action="append", help="claude-code: an extra CLI argument")
    p.add_argument("--max-budget-usd", type=float, help="claude-code: the CLI's own spend cap per episode")
    p.add_argument("--codex-bin", help="codex: the CLI to run (default: the ChatGPT app's, then PATH)")
    p.add_argument("--codex-arg", action="append", help="codex: an extra CLI argument")
    p.add_argument("--dialect", action="append", choices=list(DIALECTS))
    p.add_argument("--context-tokens", type=int,
                   help="prompt tokens a request may hold (default: --lms-context, else the "
                        "server's own limit)")
    p.add_argument("--output-tokens", type=int,
                   help=f"output-token budget per episode (default {Budgets.output_tokens})")
    p.add_argument("--cost-cap", type=float, help="dollars: no new episode starts past it")
    p.add_argument("--system-extra", metavar="FILE",
                   help="a text file appended to every model's system prompt (training plan T0: a "
                        "convention sheet); run.json and each episode header name it and its sha256, "
                        "and the prompt hash covers it. Every provider takes it, claude-code and "
                        "codex too (it is part of the system prompt they are given)")
    p.add_argument("--thinking", choices=["off"],
                   help="openai: ask the server to answer without thinking (chat_template_kwargs "
                        "enable_thinking false and reasoning_effort none in every request); run.json and "
                        "each episode header record it, and a run is not resumed under the other setting. "
                        "Left out, nothing is sent and the model's default stands")
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

    p = subs.add_parser("report", help="the run report: rows ranked with CIs, per-check credit, "
                                       "failure taxonomy, gaps")
    p.add_argument("run_dir", help="a run folder, results/<run_id>")
    p.add_argument("--out", help="where the report goes (default <run_dir>/report)")
    p.add_argument("--reverify", action="store_true",
                   help="re-score every episode from its journal with the current verifier")
    p.add_argument("--no-check-delta", action="store_true",
                   help="skip replaying to the last run_check (the delta column)")
    p.add_argument("--publish", action="store_true",
                   help="copy summary.json, leaderboard.md and the heatmap to benchmarks/runs/<run_id>/")
    p.add_argument("--allow-unrankable", action="store_true",
                   help="publish a draft-spec or d1-dev run anyway, marked as not ranked")
    p.add_argument("--runs", default=None, help="the published runs folder (default benchmarks/runs)")
    p.set_defaults(func=cmd_report)

    p = subs.add_parser("standards", help="a vague run's lost points split into drafting standards not "
                                          "applied, the work done wrong, hard fails and early ends")
    p.add_argument("run_dir", help="a run folder, results/<run_id>")
    p.add_argument("--explicit", help="the explicit run of the same model to pair with (default: the same "
                                      "run id without -vague, beside it)")
    p.add_argument("--no-pair", action="store_true", help="split by finding code alone")
    p.add_argument("--out", help="where standards.md/.json go (default <run_dir>/report)")
    p.set_defaults(func=cmd_standards)

    p = subs.add_parser("causes", help="every lost point of a run put down to one cause: a drafting "
                                       "standard not known, tool use, reasoning, or budget")
    p.add_argument("run_dirs", nargs="+", help="run folders, results/<run_id>")
    p.add_argument("--no-pair", action="store_true",
                   help="do not pair with the explicit run (every standard unconfirmed)")
    p.add_argument("--no-write", action="store_true", help="print only; no report/causes.md")
    p.add_argument("--table", help="also write one table of every run here (markdown)")
    p.set_defaults(func=cmd_causes)

    p = subs.add_parser("delta", help="one run minus another, paired by task: the gap with its interval, by "
                                      "task type, and whether the two are like for like")
    p.add_argument("run_dir", help="the run (a checkpoint, T0): a run folder or a published one")
    p.add_argument("base_dir", help="the run it is read against (the base on the same pin)")
    p.add_argument("--row", help="the run's row, by a part of its label, when it has several")
    p.add_argument("--base-row", help="the base's row, by a part of its label, when it has several")
    p.add_argument("--out", help="write the markdown here, and the same name with .json beside it")
    p.set_defaults(func=cmd_delta)

    from roaddraft.eval import t2   # stage T2: plan a round's task set from a checkpoint's run
    t2.add_parser(subs)

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
