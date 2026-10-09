"""Run probes through one native MCP client, on any vendor; score the folders.

    python -m roaddraft.runners run --backend BACKEND --model MODEL --out DIR --label LABEL
                                    [--tag TAG] [PROBE ...] [--max-turns N] [--budget MIN]
                                    [--repeat K] [--vision] [--effort LEVEL] [--force]
        anthropic:    ANTHROPIC_API_KEY in the environment
        claude-code:  [--claude-bin PATH] [--max-budget-usd D] [--claude-arg ARG ...]
        openai:       [--base-url URL] [--api-key-env NAME] [--lms-context N]
    python -m roaddraft.runners score DIR/runs/LABEL [PROBE ...]
    python -m roaddraft.runners leaderboard [--runs benchmarks/probe_runs] [--out benchmarks/leaderboard] [--check]
    python -m roaddraft.runners backends

A run writes ``DIR/runs/LABEL/<probe>/`` per probe (``--repeat K`` writes
``LABEL-r1`` .. ``LABEL-rK``); a probe with a report already is skipped unless
``--force``. ``score`` reads the folders back and writes ``scores.json``.
``leaderboard`` re-scores every run folder the runner wrote and writes the
Track P board and its model cards; ``--check`` exits 1 while they are stale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from roaddraft.mcp import config as mcpconfig
from roaddraft.probes import tasks
from roaddraft.runners import anthropic_api, claude_code, leaderboard, openai_compat  # noqa: F401  (register)
from roaddraft.runners.core import BACKENDS, Options, run_probe
from roaddraft.runners.score import format_table, score_label


def select(tag: Optional[str], ids: Sequence[str]) -> List:
    """Probes by tag and/or id; a family instance id (``draft-offsets@4``) counts."""
    chosen = [p for p in tasks.PROBES if (not tag or tag in p.tags)]
    if ids:
        by_id = {p.id: p for p in tasks.PROBES}
        chosen = [by_id[i] if i in by_id else tasks.get(i) for i in ids]
        if tag:
            chosen = [p for p in chosen if tag in p.tags]
    return chosen


def build_backend(args) -> object:
    extra = {}
    if args.backend == "claude-code":
        extra = {"claude_bin": args.claude_bin, "max_budget_usd": args.max_budget_usd,
                 "claude_args": args.claude_arg or []}
    elif args.backend == "openai":
        extra = {"base_url": args.base_url, "api_key_env": args.api_key_env,
                 "lms_context": args.lms_context}
    options = Options(model=args.model, max_turns=args.max_turns,
                      budget=args.budget * 60 if args.budget else None,
                      vision=args.vision, effort=args.effort, extra=extra)
    return BACKENDS[args.backend](options)


def cmd_run(args) -> int:
    probes = select(args.tag, args.probes)
    if not probes:
        print("no probes selected", file=sys.stderr)
        return 2
    backend = build_backend(args)
    server_command = mcpconfig.server_command()
    labels = [args.label] if args.repeat <= 1 else [f"{args.label}-r{i}" for i in range(1, args.repeat + 1)]
    out = Path(args.out)
    for label in labels:
        for probe in probes:
            folder = out / "runs" / label / probe.id
            meta = run_probe(backend, folder, probe, server_command, force=args.force)
            if meta.get("skipped"):
                print(f"skip {label}/{probe.id} (already ran)", flush=True)
    return 0


def cmd_score(args) -> int:
    rows = score_label(Path(args.folder), args.probes or None)
    print(format_table(rows))
    return 0 if rows and all(r.get("passed") for r in rows) else 1


def cmd_leaderboard(args) -> int:
    b = leaderboard.board(*leaderboard.collect(Path(args.runs)))
    if args.check:
        stale = leaderboard.check(b, Path(args.out))
        for rel in stale:
            print(f"stale: {Path(args.out) / rel}")
        return 1 if stale else 0
    for path in leaderboard.write(b, Path(args.out)):
        print(path)
    print(f"{len(b['ranked'])} ranked, {len(b['unranked'])} not ranked yet, "
          f"{len(b['others'])} other run folders")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.runners",
                                     description="run probes through one native MCP client")
    subs = parser.add_subparsers(dest="command")
    run = subs.add_parser("run", help="run probes on a backend")
    run.add_argument("--backend", required=True, choices=sorted(BACKENDS))
    run.add_argument("--model", required=True, help="model id, as the backend names it")
    run.add_argument("--out", required=True, help="the run's folder; runs/LABEL/<probe> goes under it")
    run.add_argument("--label", required=True)
    run.add_argument("--tag", help="probes with this tag (tier2, draft, find ...)")
    run.add_argument("probes", nargs="*", help="probe ids; default every probe with the tag, or all")
    run.add_argument("--max-turns", type=int, default=120)
    run.add_argument("--budget", type=float, help="minutes per probe, checked between turns")
    run.add_argument("--repeat", type=int, default=1, help="k runs: LABEL-r1 .. LABEL-rk")
    run.add_argument("--vision", action="store_true", help="hand renders to the model as images")
    run.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    run.add_argument("--force", action="store_true", help="rerun probes that already have a report")
    run.add_argument("--claude-bin", help="claude-code: the CLI to run (default: PATH, then the app's)")
    run.add_argument("--max-budget-usd", type=float, help="claude-code: the CLI's own spend cap")
    run.add_argument("--claude-arg", action="append", help="claude-code: an extra CLI argument")
    run.add_argument("--base-url", help="openai: the endpoint (default http://localhost:1234/v1)")
    run.add_argument("--api-key-env", help="openai: environment variable holding the key (OPENAI_API_KEY)")
    run.add_argument("--lms-context", type=int, help="openai: LM Studio guard, reload the model at this context")
    run.set_defaults(func=cmd_run)
    score = subs.add_parser("score", help="score a label's run folders")
    score.add_argument("folder", help="runs/LABEL")
    score.add_argument("probes", nargs="*")
    score.set_defaults(func=cmd_score)
    board = subs.add_parser("leaderboard", help="the Track P leaderboard and model cards, from the run folders")
    board.add_argument("--runs", default="benchmarks/probe_runs", help="the folder holding the run folders")
    board.add_argument("--out", default="benchmarks/leaderboard")
    board.add_argument("--check", action="store_true",
                       help="write nothing; exit 1 if the files differ from what the run folders give")
    board.set_defaults(func=cmd_leaderboard)
    subs.add_parser("backends", help="list the backends").set_defaults(
        func=lambda a: print("\n".join(f"{name}: {cls.__module__}" for name, cls in sorted(BACKENDS.items()))) or 0)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
