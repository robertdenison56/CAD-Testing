#!/usr/bin/env python3
"""The local rig, packaged: the leaderboard models that fit on RobertsPC, through LM Studio over LM Link.

    python benchmarks/lmstudio/lms_campaign.py list
    python benchmarks/lmstudio/lms_campaign.py status                   # link, server, files, what is loaded
    python benchmarks/lmstudio/lms_campaign.py pins                     # the worktree's engine/tool/instruction pins
    python benchmarks/lmstudio/lms_campaign.py check NAME               # load at 65k, time one ~29k-token prompt
    python benchmarks/lmstudio/lms_campaign.py smoke NAME [--probe edge-c102] [--print]
    python benchmarks/lmstudio/lms_campaign.py k3 NAME [PROBE...] [--force] [--print]
    python benchmarks/lmstudio/lms_campaign.py e3 NAME [--taskset d1-variance] [--samples 5] [--mode single]
                                                [--level explicit] [--limit N] [--dry-run] [--print]
    python benchmarks/lmstudio/lms_campaign.py score NAME [--print]

NAME is a key of ``models`` in ``benchmarks/lmstudio/models.json`` (``qwen3.5-9b``, ``qwen3.5-4b``, ``gemma-4-12b``).

What it fixes, so a local run is the same run as the plan:
- the code: the Runpod rig's worktree ``.claude/worktrees/runpod-k3`` at ``PIN`` (same check as
  ``benchmarks/runpod/runpod_campaign.py``), so edits to ``main`` during a run change nothing;
- the model file: ``lms load`` over LM Link takes only the bare key and loads the variant selected on the PC,
  so before a run the PC's selected variant and the loaded quantization must be the spec's, and the model is
  loaded alone at context 65536, parallel 1 (the runner's ``--lms-context`` guard reloads it the same way);
- the setting: the Runpod rows' budget (30 min, 120 turns) and sampling (``extra_body``), ``--base-url`` named
  so ``pgrep`` finds a running rig;
- one model at a time: k = 3 is one process with ``--repeat 3`` (r1, r2, r3 in turn), never three at once,
  since a reload in one would unload the model under the others; the e3 harness runs at concurrency 1;
- the Mac stays awake: every launch runs under ``caffeinate -i`` (the PC's own sleep setting is Robert's).

The folder is ``benchmarks/probe_runs/2026-10-20-lms-k3`` (labels ``<label>-r1..r3``, logs ``run-<label>.log``);
the smoke probe runs as ``-r1`` so the repeat skips it. Nothing here starts a run until ``smoke``, ``k3`` or
``e3`` is called; ``check`` and ``status`` only load models and read state.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPECS = HERE / "models.json"
WORKTREE = REPO / ".claude" / "worktrees" / "runpod-k3"
PIN = "2658fa0"                      # the Runpod rig's pin (2026-10-19); tool surface 60eeeb21 since e7178a2
PYTHON = REPO / ".venv" / "bin" / "python"
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms")
CAMPAIGN = REPO / "benchmarks" / "probe_runs" / "2026-10-20-lms-k3"
E3_OUT = REPO / "results" / "e3-lms"
BASE_URL = "http://localhost:1234/v1"
MODELS_URL = "http://localhost:1234/api/v0/models"
DEVICE = "RobertsPC"
CONTEXT = 65536
LOAD_TIMEOUT_S = 300  # lms load over LM Link: 6-10 s when it works, hung for good when it does not

BUDGET_MIN, MAX_TURNS = 30, 120     # the hosted open-weight setting of the Runpod rows
CLEAN_TOOLS, CLEAN_INSTRUCTIONS = "sha256:60eeeb2195be", "sha256:4dff2849f3c5"
SPEED_TEXT = REPO / "benchmarks" / "runpod" / "README.md"   # the 2026-10-20 timing prompt (80,000 chars)


# ------------------------------------------------------------------ specs and LM Studio

def load() -> dict:
    return json.loads(SPECS.read_text())


def save(data: dict) -> None:
    SPECS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def spec(data: dict, name: str) -> dict:
    if name not in data["models"]:
        sys.exit(f"unknown model {name!r}; one of: {', '.join(data['models'])}")
    return data["models"][name]


def lms(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([LMS, *args], capture_output=True, text=True)


def downloaded() -> List[dict]:
    return [m for m in json.loads(lms("ls", "--json").stdout or "[]") if m.get("type") == "llm"]


def loaded() -> List[dict]:
    return json.loads(lms("ps", "--json").stdout or "[]")


def served() -> List[dict]:
    with urllib.request.urlopen(MODELS_URL, timeout=10) as resp:
        return json.loads(resp.read()).get("data", [])


def link_ok() -> bool:
    r = lms("link", "status")
    out = r.stdout + r.stderr                    # lms prints the device list on stderr
    return DEVICE in out and "Status: connected" in out.split(DEVICE, 1)[1].split("\n  - ", 1)[0]


def same_quant(a: Optional[str], b: Optional[str]) -> bool:
    return (a or "").upper() == (b or "").upper()


def server_up() -> bool:
    try:
        served()
        return True
    except Exception:
        return False


def file_problem(m: dict) -> Optional[str]:
    """Why the spec's file cannot be loaded as the spec's file, or None."""
    if not m.get("lms_key"):
        found = [d["modelKey"] for d in downloaded() if m.get("find", "") in d["modelKey"].lower()]
        return (f"lms_key not set; downloaded keys matching {m.get('find')!r}: {found or 'none'}"
                + (f"; download: {m['download']}" if not found and m.get("download") else ""))
    rec = next((d for d in downloaded() if d["modelKey"] == m["lms_key"]), None)
    if rec is None:
        return f"{m['lms_key']} is not on {DEVICE}" + (f"; download: {m['download']}" if m.get("download") else "")
    if m.get("variant") and m["variant"] not in rec.get("variants", []):
        return f"{m['variant']} is not on {DEVICE} (variants: {rec.get('variants')}); download: {m.get('download')}"
    if m.get("variant") and rec.get("selectedVariant") != m["variant"]:
        return (f"{DEVICE} has {rec.get('selectedVariant')} selected, not {m['variant']}: select it for "
                f"{m['lms_key']} in LM Studio on the PC")
    quant = (rec.get("quantization") or {}).get("name")
    if not same_quant(quant, m["quantization"]):
        return f"{m['lms_key']} is {quant} on {DEVICE}, not {m['quantization']}"
    return None


def wait_state(key: str, want: str, seconds: int) -> bool:
    """Poll the server until ``key`` is in state ``want`` (``not-loaded`` after an unload, ``loaded`` after a load)."""
    for _ in range(seconds):
        try:
            rows = {s["id"]: s.get("state") for s in served()}
        except Exception:  # noqa: BLE001  the server answers again in a moment
            rows = {}
        if rows.get(key, "not-loaded") == want:
            return True
        time.sleep(1)
    return False


def load_alone(m: dict, gpu: Optional[str] = None) -> subprocess.CompletedProcess:
    """Everything else unloaded, the spec's model at CONTEXT, parallel 1 (the runner guard's own load).

    Oct 23 2026: a ``load`` issued right behind ``unload --all`` over LM Link sat at "97%" for eight minutes with the
    server reporting ``loading``, and the CLI never returned; a second load after the unload had settled took 6 s.
    So wait for the unload to show on the server, give the CLI a deadline, and trust the server's state over the
    CLI's exit: the load counts when the server says ``loaded``.
    """
    lms("unload", "--all")
    wait_state(m["lms_key"], "not-loaded", 60)
    args = [LMS, "load", m["lms_key"], "--context-length", str(CONTEXT), "--parallel", "1", "-y"]
    args += ["--gpu", gpu] if gpu else []
    try:
        r = subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=LOAD_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        r = subprocess.CompletedProcess(args, 124, out, f"lms load gave no answer in {LOAD_TIMEOUT_S} s")
    if r.returncode != 0 and wait_state(m["lms_key"], "loaded", 30):
        r = subprocess.CompletedProcess(args, 0, r.stdout, r.stderr)
    elif r.returncode == 0:
        wait_state(m["lms_key"], "loaded", 30)
    return r


def loaded_problem(m: dict) -> Optional[str]:
    """Why what the server serves is not the spec's model at CONTEXT, or None."""
    rows = [s for s in served() if s.get("state") == "loaded"]
    mine = [s for s in rows if s["id"] == m["lms_key"]]
    if len(rows) != 1 or not mine:
        return f"loaded: {[s['id'] for s in rows]} (want {m['lms_key']} alone)"
    if not same_quant(mine[0].get("quantization"), m["quantization"]):
        return f"{m['lms_key']} is loaded as {mine[0].get('quantization')}, not {m['quantization']}"
    if mine[0].get("loaded_context_length") != CONTEXT:
        return f"{m['lms_key']} is loaded at {mine[0].get('loaded_context_length')}, not {CONTEXT}"
    return None


# ------------------------------------------------------------------ preflight and commands

def git(*args: str, cwd: Path = WORKTREE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def preflight(m: Optional[dict] = None) -> None:
    problems = []
    if not WORKTREE.is_dir():
        problems.append(f"worktree missing: git worktree add --detach {WORKTREE} {PIN}")
    else:
        head = git("rev-parse", "--short", "HEAD")
        if not head.startswith(PIN) and not PIN.startswith(head):
            problems.append(f"worktree at {head}, not {PIN}")
        dirty = git("status", "--porcelain", "--", "src", "tests")
        if dirty:
            problems.append(f"worktree src/tests dirty:\n{dirty}")
    if not PYTHON.is_file():
        problems.append(f"no interpreter at {PYTHON}")
    if not link_ok():
        problems.append(f"LM Link: {DEVICE} is not connected (lms link status)")
    if not server_up():
        lms("server", "start")
        if not server_up():
            problems.append("the LM Studio server does not answer on localhost:1234 (lms server start)")
    busy = subprocess.run(["pgrep", "-fl", "roaddraft.(runners|eval) run .*localhost:1234"],
                          capture_output=True, text=True).stdout.strip()
    if busy:
        problems.append(f"a local run is already going (one model at a time):\n{busy}")
    if m is not None:
        why = file_problem(m)
        if why:
            problems.append(why)
    if problems:
        sys.exit("preflight failed:\n- " + "\n- ".join(problems))


def ready(m: dict) -> None:
    """The spec's model loaded alone at CONTEXT, checked against the server's own record."""
    r = load_alone(m)
    why = loaded_problem(m) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-400:]
    if why:
        sys.exit(f"could not load {m['lms_key']} as specified: {why}")
    print(f"loaded {m['lms_key']} ({m['quantization']}) alone at context {CONTEXT} on {DEVICE}")


def child_env() -> Dict[str, str]:
    return dict(os.environ, PYTHONPATH=str(WORKTREE / "src"))


def run_command(m: dict, label: str, probes: List[str], repeat: int = 1, force: bool = False) -> List[str]:
    cmd = ["caffeinate", "-i", str(PYTHON), "-m", "roaddraft.runners", "run", "--backend", "openai",
           "--model", m["lms_key"], "--base-url", BASE_URL, "--lms-context", str(CONTEXT),
           "--out", str(CAMPAIGN), "--label", label, "--budget", str(BUDGET_MIN), "--max-turns", str(MAX_TURNS)]
    if repeat > 1:
        cmd += ["--repeat", str(repeat)]
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
    if force:
        cmd.append("--force")
    return cmd + list(probes)


def show(cmd: List[str], log: Optional[Path] = None) -> None:
    line = "PYTHONPATH=" + shlex.quote(str(WORKTREE / "src")) + " " + shlex.join(cmd)
    print(line + (f" > {log} 2>&1 &" if log else ""))


def stream(cmd: List[str], log: Path) -> int:
    """Run in the foreground, every line to the terminal and the log."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh, subprocess.Popen(cmd, cwd=REPO, env=child_env(), stdout=subprocess.PIPE,
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
    print(f"{'name':14} {'model':36} {'quant':7} {'est h':>6} {'label':24} board row")
    for name, m in data["models"].items():
        print(f"{name:14} {m['name']:36} {m['quantization']:7} {m.get('est_k3_hours') or '':>6} "
              f"{m['label']:24} {m.get('board_row', '')}")
    return 0


def cmd_status(args) -> int:
    data = load()
    print(f"LM Link {DEVICE}: {'connected' if link_ok() else 'NOT connected'}")
    print(f"server localhost:1234: {'up' if server_up() else 'down (lms server start)'}")
    for s in loaded():
        print(f"loaded: {s['identifier']} {s['quantization']['name']} context {s.get('contextLength')} "
              f"parallel {s.get('parallel')}")
    for name, m in data["models"].items():
        why = file_problem(m)
        print(f"{name:14} {'ready' if not why else why}")
    return 0


def cmd_pins(args) -> int:
    preflight()
    code = ("import json; from roaddraft.runners.core import pins; p = pins(); "
            "print(json.dumps(p, indent=1))")
    out = subprocess.run([str(PYTHON), "-c", code], cwd=REPO, env=child_env(), capture_output=True, text=True)
    if out.returncode:
        print(out.stderr, file=sys.stderr)
        return out.returncode
    p = json.loads(out.stdout)
    print(json.dumps(p, indent=1))
    ok = p["tools_sha256"].startswith(CLEAN_TOOLS) and p["instructions_sha256"].startswith(CLEAN_INSTRUCTIONS)
    print("clean help text:", "yes" if ok else f"NO (expected {CLEAN_TOOLS}... / {CLEAN_INSTRUCTIONS}...)")
    print("dirty files:", p.get("dirty") or "none")
    return 0 if ok and not p.get("dirty") else 1


def cmd_check(args) -> int:
    """Load the model alone at 65k (all layers on the GPUs if they fit, else LM Studio's split), time one
    ~29k-token prompt and record the result in models.json. The model stays loaded."""
    data = load()
    m = spec(data, args.name)
    preflight(m)
    r = load_alone(m, gpu="max")
    offload = "full"
    if r.returncode != 0 or loaded_problem(m):
        print(f"--gpu max did not load: {(r.stdout + r.stderr).strip()[-300:]}")
        r, offload = load_alone(m), "partial (LM Studio's split)"
    why = loaded_problem(m) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-400:]
    if why:
        sys.exit(f"could not load {m['lms_key']}: {why}")
    text = SPEED_TEXT.read_text(errors="ignore")
    text = (text * (80000 // max(len(text), 1) + 1))[:80000]
    body = {"model": m["lms_key"], "max_tokens": 400, "temperature": 0.7,
            "messages": [{"role": "user", "content": text + "\n\nIn three sentences, what is this document about?"}]}
    req = urllib.request.Request(BASE_URL.rsplit("/v1", 1)[0] + "/api/v0/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    reply = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    stats, usage = reply.get("stats") or {}, reply.get("usage") or {}
    ttft = stats.get("time_to_first_token") or 0
    measured = {"date": time.strftime("%Y-%m-%d"), "offload": offload,
                "prompt_tokens": usage.get("prompt_tokens"),
                "prefill_tok_s": round(usage.get("prompt_tokens", 0) / ttft) if ttft else None,
                "gen_tok_s": round(stats.get("tokens_per_second") or 0, 1),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")}
    print(json.dumps(measured, indent=1))
    m["measured"] = measured
    save(data)
    return 0


def cmd_smoke(args) -> int:
    data = load()
    m = spec(data, args.name)
    label = f"{m['label']}-r1"
    cmd = run_command(m, label, [args.probe])
    log = CAMPAIGN / f"run-{m['label']}-smoke.log"
    if args.print:
        show(cmd, log)
        return 0
    preflight(m)
    ready(m)
    print(f"smoke {args.name}: {args.probe} as {label}; log {log}")
    t0 = time.time()
    rc = stream(cmd, log)
    meta = CAMPAIGN / "runs" / label / args.probe / "run.json"
    if meta.is_file():
        d = json.loads(meta.read_text())
        print(f"run.json: stop={d.get('stop')} turns={d.get('turns')} seconds={d.get('seconds')} "
              f"tokens={d.get('tokens')} reloads={d.get('reloads')} "
              f"pins={d.get('pins', {}).get('commit', '')[:7]} tools={d.get('pins', {}).get('tools_sha256', '')[:19]}")
    print(f"exit {rc} after {time.time() - t0:.0f} s; score it with: "
          f"PYTHONPATH={WORKTREE / 'src'} {PYTHON} -m roaddraft.runners score {CAMPAIGN / 'runs' / label}")
    return rc


def cmd_k3(args) -> int:
    data = load()
    m = spec(data, args.name)
    cmd = run_command(m, m["label"], args.probes, repeat=3, force=args.force)
    log = CAMPAIGN / f"run-{m['label']}.log"
    if args.print:
        show(cmd, log)
        return 0
    preflight(m)
    ready(m)
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, cwd=REPO, env=child_env(), stdout=log.open("a"), stderr=subprocess.STDOUT,
                            start_new_session=True)
    print(f"{m['label']}-r1..r3 in one detached process, pid {proc.pid}, log {log} (~{m.get('est_k3_hours')} h); "
          f"watch with: tail -f {log}; stop with: pkill -f 'label {m['label']} '")
    return 0


def cmd_e3(args) -> int:
    """A Track D run through the E3 harness on the PC: a task set (or its first ``--limit``) x ``--samples`` x
    one mode and prompt level, one episode at a time. Results under results/e3-lms/<run id> (gitignored); the
    harness resumes a run id, skipping every episode that already has an end record."""
    data = load()
    m = spec(data, args.name)
    run_id = args.run_id or f"e3-{args.taskset}-{m['label']}-{args.mode}"
    cmd = ["caffeinate", "-i", str(PYTHON), "-m", "roaddraft.eval", "run", "--taskset", args.taskset,
           "--model", m["lms_key"], "--provider", "openai", "--base-url", BASE_URL, "--lms-context", str(CONTEXT),
           "--out", str(E3_OUT), "--run-id", run_id, "--mode", args.mode, "--level", args.level,
           "--samples", str(args.samples), "--concurrency", "1"]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
    if args.dry_run:
        cmd.append("--dry-run")
    log = E3_OUT / f"{run_id}.log"
    if args.print:
        show(cmd, log)
        return 0
    if args.dry_run:
        return subprocess.run(cmd, cwd=REPO, env=child_env()).returncode
    preflight(m)
    ready(m)
    what = f"{args.taskset}" + (f"[:{args.limit}]" if args.limit else "")
    print(f"E3 {args.name}: {what} x {args.samples} sample(s) x {args.mode} x {args.level} -> {E3_OUT / run_id}; "
          f"log {log}")
    rc = stream(cmd, log)
    print(f"exit {rc}; report with: {PYTHON} -m roaddraft.eval report {E3_OUT / run_id}")
    return rc


def cmd_score(args) -> int:
    data = load()
    m = spec(data, args.name)
    cmds = [[str(PYTHON), "-m", "roaddraft.runners", "score", str(CAMPAIGN / "runs" / f"{m['label']}-r{i}")]
            for i in (1, 2, 3)]
    board = [str(PYTHON), "-m", "roaddraft.runners", "leaderboard"]
    if args.print:
        for cmd in cmds:
            show(cmd)
        print(shlex.join(board) + "   # from the main checkout, not the worktree")
        return 0
    for cmd in cmds:
        if (CAMPAIGN / "runs" / Path(cmd[-1]).name).is_dir():
            subprocess.run(cmd, cwd=REPO, env=child_env(), check=False)
    return subprocess.run(board, cwd=REPO, check=False).returncode


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("pins").set_defaults(fn=cmd_pins)
    c = sub.add_parser("check"); c.add_argument("name"); c.set_defaults(fn=cmd_check)
    sm = sub.add_parser("smoke"); sm.add_argument("name"); sm.add_argument("--probe", default="edge-c102")
    sm.add_argument("--print", action="store_true"); sm.set_defaults(fn=cmd_smoke)
    k = sub.add_parser("k3"); k.add_argument("name"); k.add_argument("probes", nargs="*")
    k.add_argument("--force", action="store_true"); k.add_argument("--print", action="store_true")
    k.set_defaults(fn=cmd_k3)
    e3 = sub.add_parser("e3"); e3.add_argument("name"); e3.add_argument("--taskset", default="d1-variance")
    e3.add_argument("--samples", type=int, default=5); e3.add_argument("--mode", default="single")
    e3.add_argument("--level", default="explicit"); e3.add_argument("--limit", type=int)
    e3.add_argument("--run-id"); e3.add_argument("--dry-run", action="store_true")
    e3.add_argument("--print", action="store_true"); e3.set_defaults(fn=cmd_e3)
    sc = sub.add_parser("score"); sc.add_argument("name"); sc.add_argument("--print", action="store_true")
    sc.set_defaults(fn=cmd_score)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
