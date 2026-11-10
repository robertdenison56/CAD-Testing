#!/usr/bin/env python3
"""The Runpod ladder, packaged: endpoints from models.json, the probe runs through them.

    python benchmarks/runpod/runpod_campaign.py list
    python benchmarks/runpod/runpod_campaign.py key-check
    python benchmarks/runpod/runpod_campaign.py pins                     # the worktree's engine/tool/instruction pins
    python benchmarks/runpod/runpod_campaign.py create NAME... [--dry-run]
    python benchmarks/runpod/runpod_campaign.py status [NAME...]
    python benchmarks/runpod/runpod_campaign.py smoke NAME [--probe edge-c102] [--print]
    python benchmarks/runpod/runpod_campaign.py k3 NAME [PROBE...] [--force] [--print]
    python benchmarks/runpod/runpod_campaign.py e3-smoke NAME [--limit 5] [--level vague] [--dry-run] [--print]
    python benchmarks/runpod/runpod_campaign.py e3 NAME [--taskset d1-variance] [--samples 5] [--mode single]
                                                [--concurrency 4] [--limit N] [--pilots all|text|images]
                                                [--run-id ID] [--dry-run] [--print]
    python benchmarks/runpod/runpod_campaign.py rerun NAME [--print]      # infrastructure-error episodes, again
    python benchmarks/runpod/runpod_campaign.py score NAME [--print]
    python benchmarks/runpod/runpod_campaign.py bill
    python benchmarks/runpod/runpod_campaign.py workers NAME MAX            # 0 frees one of the account's 10 max workers
    python benchmarks/runpod/runpod_campaign.py delete NAME... --yes

NAME is a key of ``models`` in ``benchmarks/runpod/models.json`` (``qwen3.8-27b``, ``gpt-oss-120b`` ...).

What it fixes, so a run tomorrow is the same run as the plan:
- the code: every run is launched with ``PYTHONPATH`` on the worktree ``.claude/worktrees/runpod-k3``,
  pinned at ``PIN`` (the runner and the MCP server it starts both import from there; ``preflight`` refuses a
  moved or dirty worktree), so edits to ``main`` during a run change nothing;
- the key: ``RUNPOD_API_KEY`` from the environment, else read from ``~/.claude.json`` (the Runpod MCP
  header) into the child's environment; it is never printed;
- the route: ``https://api.runpod.ai/v2/<endpoint>/openai/v1`` with ``--backend openai``, the model id as the
  worker serves it, the spec's ``extra_body`` on every request (recorded in each run.json), and
  ``--send-reasoning`` when the spec sets ``send_reasoning`` (gpt-oss: harmony wants its earlier thinking back);
- the folder: ``benchmarks/probe_runs/2026-10-17-k3``, or the spec's ``campaign`` folder name when it has one (the
  board makes one row of a model per folder, so a rerun under another rig setting needs a folder of its own),
  labels ``<label>-r1..r3``, logs ``run-<label>-rN.log``; the smoke probe runs as ``-r1`` so the repeat skips it
  (``2026-10-12-k3`` did the same).

Nothing here starts a worker until ``smoke``, ``k3`` or ``e3-smoke`` sends a request: ``create`` makes
endpoints with ``workers.min = 0``, which bill nothing while idle.

The Track D spread (2026-10-28, ``PLAN.md`` beside this file): a spec with ``public: true`` is a Runpod public
endpoint, served and billed per token by Runpod on the same /openai/v1 route, so ``create``, ``warm``, ``status``,
``workers`` and ``delete`` refuse it; a spec with ``trackd_local`` already has its Track D row on RobertsPC, so
``e3`` refuses it without ``--force`` (Robert: do not duplicate a model that runs locally).

Track D under harness e3-v3 (2026-11-04, ``PLAN.md`` "The $100 plan"): ``e3`` and ``e3-smoke`` run from their
own worktree ``TRACKD_WORKTREE`` at ``TRACKD_PIN`` (the probe commands keep ``runpod-k3`` at ``PIN``), and a spec's
``context`` goes to the harness as ``--context-tokens`` (the endpoint's ``MAX_MODEL_LEN``), so a transcript that
outgrows the window ends as the context stop rather than an HTTP 400.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPECS = HERE / "models.json"
WORKTREE = REPO / ".claude" / "worktrees" / "runpod-k3"
PIN = "2658fa0"                      # 2026-10-19: main a1c0038 + 89f7a13 (eval file access held to the episode folder, e3-v2), for d1-variance; before it 3daef52 (2026-10-18): the engine refuses stationing out of its linework's
                                     # space, d1-verify-v5; tool surface unchanged since e7178a2 (60eeeb21). The
                                     # 2026-10-17-k3 rows ran at e7178a2, the gpt-oss rerun at 727fb7f
# Track D (e3, e3-smoke): the v3 reruns' surface (main 3b7e7fe9: harness e3-v3, tools 0334fd4aaade, the stall
# fix) plus the eval provider's reading of Runpod's 570 s proxy cut and vLLM's context refusal as the turn_time and
# context stops: 9f7c02bb (2026-11-04) = 3b7e7fe9 + main's 463a9707 cherry-picked (the cost subsets, the board's
# partial rule, the provider changes), on the local branch runpod-trackd-v3; tools 0334fd4aaade, instructions
# 4dff2849, harness e3-v3, as queue 10 and the codex queue.
TRACKD_WORKTREE = REPO / ".claude" / "worktrees" / "runpod-trackd"
TRACKD_PIN: Optional[str] = "9f7c02bb"
PILOT_SET = REPO / "benchmarks" / "tasksets" / "hard-pilots.json"
PYTHON = REPO / ".venv" / "bin" / "python"
CAMPAIGN = REPO / "benchmarks" / "probe_runs" / "2026-10-17-k3"
E3_OUT = REPO / "results" / "e3-runpod"
API = "https://api.runpod.io/v2"
ROUTE = "https://api.runpod.ai/v2/{id}/openai/v1"
HEALTH = "https://api.runpod.ai/v2/{id}/health"
BUDGET_MIN, MAX_TURNS = 30, 120     # the hosted open-weight setting of the Qwen3.5-9B row
# the scrubbed help text (fe26ce2); a run whose pins differ ran on another surface
CLEAN_TOOLS, CLEAN_INSTRUCTIONS = "sha256:60eeeb2195be", "sha256:4dff2849f3c5"


# ------------------------------------------------------------------ specs and key

def load() -> dict:
    return json.loads(SPECS.read_text())


def save(data: dict) -> None:
    SPECS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def spec(data: dict, name: str) -> dict:
    try:
        return data["models"][name]
    except KeyError:
        sys.exit(f"no model {name!r} in {SPECS.name}; names: {', '.join(data['models'])}")


def api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if key:
        return key
    try:
        cfg = json.loads((Path.home() / ".claude.json").read_text())
        header = cfg["mcpServers"]["runpod"]["headers"]["Authorization"]
    except (OSError, KeyError, ValueError):
        sys.exit("no RUNPOD_API_KEY in the environment and none in ~/.claude.json (mcpServers.runpod)")
    return header.split(" ", 1)[1].strip() if header.lower().startswith("bearer ") else header.strip()


def request(method: str, url: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode()
            return json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode(errors="replace")[:800]
        sys.exit(f"{method} {url}: HTTP {ex.code}: {detail}")


# ------------------------------------------------------------------ the endpoint body

def endpoint_body(data: dict, name: str) -> dict:
    m = spec(data, name)
    env = dict(data["common_env"])
    env["MODEL_NAME"] = m["model"]
    env.update(m.get("env") or {})
    # allowedCudaVersions and minCudaVersion are mutually exclusive on create; the image is CUDA 13.0 only
    gpu = {"pools": list(m["pools"]), "count": 1, "allowedCudaVersions": [data["cuda"]]}
    if m.get("excluded_types"):
        gpu["excludedTypes"] = list(m["excluded_types"])
    return {"name": f"roaddraft-{name}", "image": data["image"], "disk": int(m["disk"]),
            "env": {k: str(v) for k, v in env.items()}, "gpu": gpu, "type": "QUEUE",
            "scaling": {"type": "QUEUE_DELAY", "queueDelay": 4},
            "workers": {"min": 0, "max": 1, "idleTimeout": 120},
            "flashboot": "FLASHBOOT", "timeout": 1_800_000}


def campaign(m: dict) -> Path:
    return REPO / "benchmarks" / "probe_runs" / m["campaign"] if m.get("campaign") else CAMPAIGN


def route(m: dict) -> str:
    if not m.get("endpoint"):
        sys.exit(f"{m['model']} has no endpoint yet: run `create` first")
    return ROUTE.format(id=m["endpoint"])


def is_public(m: dict) -> bool:
    """A Runpod public endpoint (``public: true``): Runpod serves the model and bills per token, the account
    owns no endpoint resource, and the route is the ladder's /openai/v1 with the same key. Nothing here
    creates, arms, warms, parks or deletes one (2026-10-28: GLM-5.3, b1dd8hy2hqo1nb)."""
    return bool(m.get("public"))


def not_public(m: dict, name: str, what: str) -> None:
    if is_public(m):
        sys.exit(f"{name}: a Runpod public endpoint ({m.get('endpoint')}); `{what}` does not apply, Runpod runs it")


def local_row(m: dict) -> Optional[str]:
    """The Track D row this model already has on RobertsPC (``trackd_local``), when it has one. Robert,
    2026-10-28: the Runpod spread does not duplicate a model that runs locally; ``e3`` refuses such a
    model without ``--force``."""
    return m.get("trackd_local") or None


# ------------------------------------------------------------------ preflight and commands

def git(*args: str, cwd: Path = WORKTREE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def preflight(need_key: bool = True, worktree: Path = WORKTREE, pin: Optional[str] = PIN) -> None:
    problems = []
    if not pin:
        problems.append(f"no pin set for {worktree.name} (TRACKD_PIN in {Path(__file__).name})")
    elif not worktree.is_dir():
        problems.append(f"worktree missing: git worktree add --detach {worktree} {pin}")
    else:
        head = git("rev-parse", "--short", "HEAD", cwd=worktree)
        if not head.startswith(pin) and not pin.startswith(head):
            problems.append(f"worktree at {head}, not {pin}")
        dirty = git("status", "--porcelain", "--", "src", "tests", cwd=worktree)
        if dirty:
            problems.append(f"worktree src/tests dirty:\n{dirty}")
    if not PYTHON.is_file():
        problems.append(f"no interpreter at {PYTHON}")
    if need_key:
        api_key()
    if problems:
        sys.exit("preflight failed:\n- " + "\n- ".join(problems))


def arm(m: dict) -> None:
    """A parked endpoint (max workers 0) is paused: the gateway answers 409 ENDPOINT_PAUSED. Set max 1 and
    give the two planes the 20-25 s they take to agree (Runpod's own cold-start write-up measured it)."""
    if is_public(m):
        return
    workers = request("GET", f"{API}/serverless/{m['endpoint']}")["workers"]
    if int(workers.get("max", 0)) >= 1:
        return
    request("PATCH", f"{API}/serverless/{m['endpoint']}", {"workers": {"min": 0, "max": 1}})
    print(f"armed {m['endpoint']}: max workers 0 -> 1; waiting 30 s for the job gateway to unpause")
    time.sleep(30)


def child_env(worktree: Path = WORKTREE) -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(worktree / "src")
    env["RUNPOD_API_KEY"] = api_key()
    return env


def run_command(m: dict, label: str, probes: List[str], force: bool = False) -> List[str]:
    cmd = [str(PYTHON), "-m", "roaddraft.runners", "run", "--backend", "openai", "--model", m["model"],
           "--base-url", route(m), "--api-key-env", "RUNPOD_API_KEY",
           "--out", str(campaign(m)), "--label", label, "--budget", str(BUDGET_MIN), "--max-turns", str(MAX_TURNS)]
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
    if m.get("send_reasoning"):
        cmd.append("--send-reasoning")
    if force:
        cmd.append("--force")
    return cmd + list(probes)


def show(cmd: List[str], log: Optional[Path] = None, worktree: Path = WORKTREE) -> None:
    line = "PYTHONPATH=" + shlex.quote(str(worktree / "src")) + " " + shlex.join(cmd)
    print(line + (f" > {log} 2>&1 &" if log else ""))


def stream(cmd: List[str], log: Path, worktree: Path = WORKTREE) -> int:
    """Run in the foreground, every line to the terminal and the log."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh, subprocess.Popen(cmd, cwd=REPO, env=child_env(worktree), stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT, text=True) as proc:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
        proc.wait()
        return proc.returncode


# ------------------------------------------------------------------ subcommands

def cmd_list(args) -> int:
    data = load()
    print(f"{'name':20} {'rung':34} {'model':34} {'pools':26} {'$/h':>5} {'est $':>7}  endpoint")
    for name, m in data["models"].items():
        if is_public(m):
            pr = m.get("pricing_usd_per_m") or {}
            where = f"public ${pr.get('input')}/${pr.get('output')} per M"
            print(f"{name:20} {m['rung'][:34]:34} {m['model'][:34]:34} {where[:26]:26} "
                  f"{'':>5} {m.get('est_usd', '')[:7]:>7}  {m.get('endpoint') or '-'}")
            continue
        tail = "  LOCAL ROW: not on the Runpod spread" if local_row(m) else ""
        print(f"{name:20} {m['rung'][:34]:34} {m['model'][:34]:34} {','.join(m['pools'])[:26]:26} "
              f"{m['rate_usd_h']:>5.2f} {m['est_usd'][:7]:>7}  {m.get('endpoint') or '-'}{tail}")
    print("\nout of range:")
    for model, why in data.get("out_of_range", {}).items():
        print(f"  {model}: {why}")
    return 0


def cmd_key_check(args) -> int:
    key = api_key()
    print(f"key present ({len(key)} characters, from "
          f"{'the environment' if os.environ.get('RUNPOD_API_KEY') else '~/.claude.json'}); not printed")
    listing = request("GET", f"{API}/serverless")
    items = listing.get("endpoints", []) if isinstance(listing, dict) else []
    print(f"key accepted: {len(items)} serverless endpoint(s) on the account, "
          f"{sum(int(e.get('workers', {}).get('max', 0)) for e in items)} max workers in all (quota 10): "
          + ", ".join(f"{e.get('name')} ({e.get('id')}, max {e.get('workers', {}).get('max')})" for e in items))
    return 0


def cmd_workers(args) -> int:
    """The account allows 10 max workers across all endpoints: a finished endpoint set to 0 frees one."""
    data = load()
    m = spec(data, args.name)
    not_public(m, args.name, "workers")
    if not m.get("endpoint"):
        sys.exit(f"{args.name}: no endpoint")
    before = request("GET", f"{API}/serverless/{m['endpoint']}")["workers"]
    request("PATCH", f"{API}/serverless/{m['endpoint']}", {"workers": {"min": 0, "max": int(args.max)}})
    after = request("GET", f"{API}/serverless/{m['endpoint']}")["workers"]
    print(f"{args.name} {m['endpoint']}: workers {before} -> {after}")
    return 0


def cmd_pins(args) -> int:
    preflight(need_key=False)
    code = ("import json; from roaddraft.runners.core import pins; p = pins(); "
            "print(json.dumps(p, indent=1))")
    env = dict(os.environ, PYTHONPATH=str(WORKTREE / "src"))
    out = subprocess.run([str(PYTHON), "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    if out.returncode:
        print(out.stderr, file=sys.stderr)
        return out.returncode
    p = json.loads(out.stdout)
    print(json.dumps(p, indent=1))
    ok = p["tools_sha256"].startswith(CLEAN_TOOLS) and p["instructions_sha256"].startswith(CLEAN_INSTRUCTIONS)
    print("clean help text:", "yes" if ok else f"NO (expected {CLEAN_TOOLS}... / {CLEAN_INSTRUCTIONS}...)")
    print("dirty files:", p.get("dirty") or "none")
    return 0 if ok and not p.get("dirty") else 1


def cmd_create(args) -> int:
    data = load()
    for name in args.names:
        m = spec(data, name)
        not_public(m, name, "create")
        body = endpoint_body(data, name)
        if m.get("endpoint") and not args.again:
            print(f"{name}: already has endpoint {m['endpoint']} (pass --again to create another)")
            continue
        if args.dry_run:
            print(f"--- {name}: POST {API}/serverless")
            print(json.dumps(body, indent=1))
            continue
        created = request("POST", f"{API}/serverless", body)
        eid = created.get("id")
        if not eid:
            sys.exit(f"{name}: no id in the create response: {json.dumps(created)[:400]}")
        back = request("GET", f"{API}/serverless/{eid}")
        m["endpoint"] = eid
        save(data)
        print(f"{name}: created {eid} ({back.get('name')}), image {back.get('image')}, "
              f"pools {back.get('gpu', {}).get('pools')}, workers {back.get('workers')}, "
              f"disk {back.get('disk')} GB, timeout {back.get('timeout')} ms; "
              f"route {ROUTE.format(id=eid)}")
        env = back.get("env", {})
        print(f"   env: MODEL_NAME={env.get('MODEL_NAME')} TOOL_CALL_PARSER={env.get('TOOL_CALL_PARSER')} "
              f"REASONING_PARSER={env.get('REASONING_PARSER')} MAX_MODEL_LEN={env.get('MAX_MODEL_LEN')} "
              f"VLLM_EXTRA_ARGS={env.get('VLLM_EXTRA_ARGS', '')!r}")
    return 0


def cmd_status(args) -> int:
    data = load()
    names = args.names or list(data["models"])
    for name in names:
        m = spec(data, name)
        if is_public(m):
            print(f"{name:20} {m['endpoint']} public endpoint: Runpod runs it, no workers of ours to read")
            continue
        if not m.get("endpoint"):
            print(f"{name:20} no endpoint")
            continue
        e = request("GET", f"{API}/serverless/{m['endpoint']}")
        h = request("GET", HEALTH.format(id=m["endpoint"]))
        workers, jobs = h.get("workers", {}), h.get("jobs", {})
        print(f"{name:20} {m['endpoint']} {e.get('name')}: workers min {e['workers']['min']} max {e['workers']['max']}; "
              f"now idle {workers.get('idle', 0)} running {workers.get('running', 0)} "
              f"initializing {workers.get('initializing', 0)} throttled {workers.get('throttled', 0)}; "
              f"jobs queued {jobs.get('inQueue', 0)} in progress {jobs.get('inProgress', 0)} "
              f"completed {jobs.get('completed', 0)} failed {jobs.get('failed', 0)}")
    return 0


def cmd_warm(args) -> int:
    """Cold-start the worker through the queue route, not the streamed OpenAI route: Runpod's proxy ends a
    streamed request after 570 s, and a 50-70 GB model's cold start alone is longer (GLM-4.7-Flash and
    Gemma 4 26B-A4B both lost their first probe to it, 2026-10-17). A tiny chat job on /run waits out the
    start without that limit; the smoke or the campaign then meets a warm worker (idle timeout permitting)."""
    data = load()
    m = spec(data, args.name)
    not_public(m, args.name, "warm")
    api_key()   # warm runs no harness code: the key is all it needs (the probe worktree runpod-k3 is gone)
    arm(m)
    base = f"https://api.runpod.ai/v2/{m['endpoint']}"
    body = {"input": {"openai_route": "/v1/chat/completions",
                      "openai_input": {"model": m["model"], "max_tokens": 8,
                                       "messages": [{"role": "user", "content": "Say ready."}]}}}
    t_arm = time.time()
    while True:   # the job gateway can stay paused for a while after max workers goes 0 -> 1
        try:
            job = request("POST", f"{base}/run", body)
            break
        except SystemExit as ex:
            if "409" not in str(ex) or time.time() - t_arm > 300:
                raise
            print("gateway still paused (409); retrying in 15 s")
            time.sleep(15)
    jid = job.get("id")
    print(f"warm {args.name}: job {jid} queued on {m['endpoint']} (${m['rate_usd_h']}/h once the worker runs)")
    t0 = time.time()
    while True:
        st = request("GET", f"{base}/status/{jid}")
        status = st.get("status")
        if status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
            out = json.dumps(st.get("output") or st.get("error"))[:300]
            print(f"{status} after {time.time() - t0:.0f} s (delay {st.get('delayTime')} ms, "
                  f"execution {st.get('executionTime')} ms): {out}")
            return 0 if status == "COMPLETED" else 1
        if time.time() - t0 > args.wait:
            print(f"still {status} after {args.wait} s; the job stays queued (cancel: {base}/cancel/{jid})")
            return 2
        time.sleep(15)


def cmd_smoke(args) -> int:
    data = load()
    m = spec(data, args.name)
    label = f"{m['label']}-r1"
    cmd = run_command(m, label, [args.probe])
    log = campaign(m) / f"run-{m['label']}-smoke.log"
    if args.print:
        show(cmd, log)
        return 0
    preflight()
    arm(m)
    print(f"smoke {args.name}: {args.probe} as {label}; log {log}; the first request cold-starts a worker "
          f"(${m['rate_usd_h']}/h while it runs, ~5 min to load)")
    t0 = time.time()
    rc = stream(cmd, log)
    meta = campaign(m) / "runs" / label / args.probe / "run.json"
    if meta.is_file():
        d = json.loads(meta.read_text())
        print(f"run.json: stop={d.get('stop')} turns={d.get('turns')} seconds={d.get('seconds')} "
              f"tokens={d.get('tokens')} pins={d.get('pins', {}).get('commit', '')[:7]} "
              f"tools={d.get('pins', {}).get('tools_sha256', '')[:19]} "
              f"instr={d.get('pins', {}).get('instructions_sha256', '')[:19]}")
    print(f"exit {rc} after {time.time() - t0:.0f} s; score it with: "
          f"PYTHONPATH={WORKTREE / 'src'} {PYTHON} -m roaddraft.runners score {campaign(m) / 'runs' / label}")
    return rc


def cmd_k3(args) -> int:
    data = load()
    m = spec(data, args.name)
    cmds = [(f"{m['label']}-r{i}", run_command(m, f"{m['label']}-r{i}", args.probes, args.force)) for i in (1, 2, 3)]
    if args.print:
        for label, cmd in cmds:
            show(cmd, campaign(m) / f"run-{label}.log")
        return 0
    preflight()
    arm(m)
    campaign(m).mkdir(parents=True, exist_ok=True)
    pids = []
    for label, cmd in cmds:
        log = campaign(m) / f"run-{label}.log"
        fh = log.open("a")
        proc = subprocess.Popen(cmd, cwd=REPO, env=child_env(), stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
        pids.append((label, proc.pid, log))
    for label, pid, log in pids:
        print(f"{label}: pid {pid}, log {log}")
    print(f"three detached processes on endpoint {m['endpoint']} ({m['rate_usd_h']}/h while the worker runs); "
          f"watch with: tail -f {campaign(m)}/run-{m['label']}-r*.log; "
          f"stop with: pkill -f 'label {m['label']}-r'")
    return 0


def cmd_e3(args) -> int:
    """A Track D run through the E3 harness: a task set (or its first ``--limit``) x ``--samples`` x one
    mode and prompt level, on the model's endpoint. Results under results/e3-runpod/<run id> (gitignored);
    the harness resumes a run id, skipping every episode that already has an end record."""
    data = load()
    m = spec(data, args.name)
    if local_row(m) and not getattr(args, "force", False):
        sys.exit(f"{args.name}: its Track D row runs on RobertsPC ({local_row(m)}); the Runpod spread does not "
                 f"duplicate it (Robert, 2026-10-28). --force runs a Runpod row of it anyway.")
    subset = getattr(args, "subset", None)
    run_id = args.run_id or (f"e3-{args.taskset}-{args.name}-{args.mode}" + ("-vague" if args.level == "vague" else "")
                             + (f"-{subset}" if subset else "") + "-v3")
    cmd = [str(PYTHON), "-m", "roaddraft.eval", "run", "--taskset", args.taskset,
           "--model", m["model"], "--provider", "openai", "--base-url", route(m), "--api-key-env", "RUNPOD_API_KEY",
           "--out", str(E3_OUT), "--run-id", run_id, "--mode", args.mode, "--level", args.level,
           "--samples", str(args.samples), "--concurrency", str(args.concurrency)]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    pilots = getattr(args, "pilots", "all")
    if subset:   # a cost subset (eval/subsets.py): the board ranks it, tagged partial to save cost
        if args.limit or pilots != "all":
            sys.exit("--subset takes the subset's tasks; it does not combine with --limit or --pilots")
        cmd += ["--subset", subset]
    if args.taskset == "hard-pilots" and pilots != "all":
        cmd += [x for i in pilot_ids(pilots) for x in ("--task", i)]
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
    if m.get("send_reasoning"):   # gpt-oss: harmony wants a tool turn's reasoning back (the probe runner's flag)
        cmd.append("--send-reasoning")
    if getattr(args, "cost_cap", None) is not None:   # a per-token endpoint: no new episode past it
        cmd += ["--cost-cap", str(args.cost_cap)]
    if m.get("context"):   # the harness's own context budget (291ae711): a public endpoint's window, no MAX_MODEL_LEN of ours
        cmd += ["--context-tokens", str(m["context"])]
    if args.dry_run:
        cmd.append("--dry-run")
    log = E3_OUT / f"{run_id}.log"
    if args.print:
        show(cmd, log, TRACKD_WORKTREE)
        return 0
    preflight(need_key=not args.dry_run, worktree=TRACKD_WORKTREE, pin=TRACKD_PIN)
    if args.dry_run:
        env = dict(os.environ, PYTHONPATH=str(TRACKD_WORKTREE / "src"))
        return subprocess.run(cmd, cwd=REPO, env=env).returncode
    arm(m)
    what = f"{args.taskset}" + (f"[:{args.limit}]" if args.limit else "")
    print(f"E3 {args.name}: {what} x {args.samples} sample(s) x {args.mode} x {args.level} -> {E3_OUT / run_id}; "
          f"log {log}")
    rc = stream(cmd, log, TRACKD_WORKTREE)
    print(f"exit {rc}; report with: PYTHONPATH={TRACKD_WORKTREE / 'src'} {PYTHON} -m roaddraft.eval report "
          f"{E3_OUT / run_id}")
    return rc


def pilot_ids(kind: str) -> List[str]:
    """The hard-pilots task ids of one kind: ``images`` (the pilots that come with a page), ``text``, ``all``
    (as ``lms_campaign.py``)."""
    rows = json.loads(PILOT_SET.read_text())
    rows = rows["tasks"] if isinstance(rows, dict) else rows
    want = {"images": lambda r: bool(r.get("attachments")), "text": lambda r: not r.get("attachments"),
            "all": lambda r: True}[kind]
    return [r["task_id"] for r in rows if want(r)]


def cmd_e3_smoke(args) -> int:
    """The E3 smoke run: d1-dev[:5] x single, at the vague prompt by default (2026-11-08, Robert: "Update the
    runpod batches with vague prompts only"; explicit until then, first run 2026-10-18 on Qwen3.6-35B-A3B)."""
    args.taskset, args.samples, args.mode = "d1-dev", 1, "single"
    args.run_id = f"e3-smoke-v3-{args.name}"     # -v3: the Oct 18 smoke of the same name stays on disk
    return cmd_e3(args)


INFRA_ERRORS = ("Connection reset", "connection reset", "Remote end closed", "HTTP 5")
# Runpod's 570 s streamed-request limit is NOT rerun: reached by a model's turn (its first turn included:
# Qwen3.8-27B thought past it three times on draft-roadway-sheets on a warm worker, 2026-10-18) it is the
# board's budget stop (BUDGET_ERRORS). A cold start that reaches it is avoided with `warm`, and a smoke
# probe lost that way is set aside by hand (run.json with 0 turns and no tokens).


def cmd_rerun(args) -> int:
    """Episodes that ended on the infrastructure (a reset connection, a 5xx) are moved to
    runs/_superseded/ for the record and run again, one process per label."""
    data = load()
    m = spec(data, args.name)
    todo: Dict[str, List[str]] = {}
    for i in (1, 2, 3):
        label = f"{m['label']}-r{i}"
        for meta in sorted((campaign(m) / "runs" / label).glob("*/run.json")):
            d = json.loads(meta.read_text())
            stop = str(d.get("stop", ""))
            if stop.startswith("error") and any(s in stop for s in INFRA_ERRORS):
                todo.setdefault(label, []).append(meta.parent.name)
    if not todo:
        print(f"{args.name}: no infrastructure-error episodes")
        return 0
    for label, probes in todo.items():
        print(f"{label}: {', '.join(probes)}")
    if args.print:
        for label, probes in todo.items():
            show(run_command(m, label, probes), campaign(m) / f"run-{label}-rerun.log")
        return 0
    preflight()
    arm(m)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    aside = campaign(m) / "runs" / "_superseded"
    aside.mkdir(exist_ok=True)
    for label, probes in todo.items():
        for probe in probes:
            (campaign(m) / "runs" / label / probe).rename(aside / f"{label}-{probe}-{stamp}")
        log = campaign(m) / f"run-{label}-rerun.log"
        proc = subprocess.Popen(run_command(m, label, probes), cwd=REPO, env=child_env(),
                                stdout=log.open("a"), stderr=subprocess.STDOUT, start_new_session=True)
        print(f"{label}: rerunning {len(probes)} episode(s), pid {proc.pid}, log {log}; "
              f"the old folders are under {aside}")
    return 0


def cmd_score(args) -> int:
    data = load()
    m = spec(data, args.name)
    cmds = [[str(PYTHON), "-m", "roaddraft.runners", "score", str(campaign(m) / "runs" / f"{m['label']}-r{i}")]
            for i in (1, 2, 3)]
    board = [str(PYTHON), "-m", "roaddraft.runners", "leaderboard"]
    if args.print:
        for cmd in cmds:
            show(cmd)
        print(shlex.join(board) + "   # from the main checkout, not the worktree")
        return 0
    preflight(need_key=False)
    for cmd in cmds:
        if (campaign(m) / "runs" / Path(cmd[-1]).name).is_dir():
            subprocess.run(cmd, cwd=REPO, env=dict(os.environ, PYTHONPATH=str(WORKTREE / "src")), check=False)
    return subprocess.run(board, cwd=REPO, check=False).returncode


def cmd_bill(args) -> int:
    b = request("GET", f"{API}/billing/serverless")
    meta = b.get("metadata", {}) if isinstance(b, dict) else {}
    print("window:", json.dumps(meta.get("query")))
    print("totals:", json.dumps(meta.get("totals")))
    for rec in (b.get("records") or [])[-10:]:
        print(" ", rec.get("startTime", "")[:10], rec.get("serverlessId") or rec.get("endpointId") or "",
              f"gpu ${rec.get('serverlessGpuAmount', rec.get('gpuAmount', 0)):.2f}",
              f"total ${rec.get('totalAmount', 0):.2f}")
    return 0


def cmd_delete(args) -> int:
    if not args.yes:
        sys.exit("refusing without --yes (Robert's word): deleting an endpoint is the teardown")
    data = load()
    for name in args.names:
        m = spec(data, name)
        not_public(m, name, "delete")
        if not m.get("endpoint"):
            print(f"{name}: no endpoint")
            continue
        eid = m["endpoint"]
        request("DELETE", f"{API}/serverless/{eid}")
        try:
            request("GET", f"{API}/serverless/{eid}")
            print(f"{name}: {eid} still answers a GET; check the console")
        except SystemExit as ex:
            if "HTTP 404" in str(ex):
                print(f"{name}: {eid} deleted (GET now 404)")
            else:
                raise
        m["endpoint"] = None
        save(data)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("key-check").set_defaults(fn=cmd_key_check)
    sub.add_parser("pins").set_defaults(fn=cmd_pins)
    c = sub.add_parser("create"); c.add_argument("names", nargs="+"); c.add_argument("--dry-run", action="store_true")
    c.add_argument("--again", action="store_true", help="create even if the spec already names an endpoint")
    c.set_defaults(fn=cmd_create)
    s = sub.add_parser("status"); s.add_argument("names", nargs="*"); s.set_defaults(fn=cmd_status)
    wm = sub.add_parser("warm"); wm.add_argument("name"); wm.add_argument("--wait", type=int, default=1500)
    wm.set_defaults(fn=cmd_warm)
    sm = sub.add_parser("smoke"); sm.add_argument("name"); sm.add_argument("--probe", default="edge-c102")
    sm.add_argument("--print", action="store_true"); sm.set_defaults(fn=cmd_smoke)
    k = sub.add_parser("k3"); k.add_argument("name"); k.add_argument("probes", nargs="*")
    k.add_argument("--force", action="store_true"); k.add_argument("--print", action="store_true"); k.set_defaults(fn=cmd_k3)
    e = sub.add_parser("e3-smoke"); e.add_argument("name"); e.add_argument("--limit", type=int, default=5)
    e.add_argument("--concurrency", type=int, default=3); e.add_argument("--dry-run", action="store_true")
    e.add_argument("--print", action="store_true"); e.add_argument("--cost-cap", type=float)
    e.add_argument("--level", default="vague", choices=["explicit", "vague"])
    e.add_argument("--force", action="store_true", help="run a model whose Track D row is local (trackd_local)")
    e.set_defaults(fn=cmd_e3_smoke)
    e3 = sub.add_parser("e3"); e3.add_argument("name"); e3.add_argument("--taskset", default="d1-variance")
    e3.add_argument("--samples", type=int, default=5); e3.add_argument("--limit", type=int)
    e3.add_argument("--mode", default="single", choices=["single", "self_correct", "vision"])
    e3.add_argument("--level", default="explicit", choices=["explicit", "vague"])
    e3.add_argument("--concurrency", type=int, default=4); e3.add_argument("--run-id")
    e3.add_argument("--subset", help="a cost subset (benchmarks/tasksets/cost-subsets.json, e.g. cost5): ranked on "
                                    "the board as partial to save cost")
    e3.add_argument("--cost-cap", type=float, help="dollars (a public endpoint's per-token bill): no new episode past it")
    e3.add_argument("--pilots", choices=["all", "text", "images"], default="all",
                    help="hard-pilots only: all 112, the text pilots, or the ones briefed by an image")
    e3.add_argument("--dry-run", action="store_true"); e3.add_argument("--print", action="store_true")
    e3.add_argument("--force", action="store_true", help="run a model whose Track D row is local (trackd_local)")
    e3.set_defaults(fn=cmd_e3)
    sc = sub.add_parser("score"); sc.add_argument("name"); sc.add_argument("--print", action="store_true")
    sc.set_defaults(fn=cmd_score)
    rr = sub.add_parser("rerun"); rr.add_argument("name"); rr.add_argument("--print", action="store_true")
    rr.set_defaults(fn=cmd_rerun)
    sub.add_parser("bill").set_defaults(fn=cmd_bill)
    w = sub.add_parser("workers"); w.add_argument("name"); w.add_argument("max", type=int)
    w.set_defaults(fn=cmd_workers)
    d = sub.add_parser("delete"); d.add_argument("names", nargs="+"); d.add_argument("--yes", action="store_true")
    d.set_defaults(fn=cmd_delete)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
