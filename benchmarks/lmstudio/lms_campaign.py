#!/usr/bin/env python3
"""The local rig, packaged: the leaderboard models that fit on RobertsPC, through LM Studio over LM Link.

    python benchmarks/lmstudio/lms_campaign.py list
    python benchmarks/lmstudio/lms_campaign.py status                   # link, server, files, what is loaded
    python benchmarks/lmstudio/lms_campaign.py pins                     # the worktree's engine/tool/instruction pins
    python benchmarks/lmstudio/lms_campaign.py fit NAME                 # the highest context that loads, 131k down to 65k; below: dropped
    python benchmarks/lmstudio/lms_campaign.py check NAME               # load at its context, time one ~29k-token prompt
    python benchmarks/lmstudio/lms_campaign.py vision NAME              # one image through the harness's route; records it
    python benchmarks/lmstudio/lms_campaign.py smoke NAME [--probe edge-c102] [--print]
    python benchmarks/lmstudio/lms_campaign.py k3 NAME [PROBE...] [--force] [--print]
    python benchmarks/lmstudio/lms_campaign.py e3 NAME [--taskset d1-variance] [--samples 5|1] [--mode single]
                                                [--level explicit] [--limit N] [--run-id ID]
                                                [--pilots text|images|all] [--worktree PATH] [--dry-run] [--print]
                                                [--system-extra FILE] [--thinking off]
    python benchmarks/lmstudio/lms_campaign.py thinking RUN_ID          # a run's reasoning tokens; exit 1 when a --thinking off run thought
    python benchmarks/lmstudio/lms_campaign.py run-state RUN_ID [--commit SHA]   # new, partial, finished or other (a queue's relaunch reads it)
    python benchmarks/lmstudio/lms_campaign.py clear-errors RUN_ID [--apply] [--stalled] [--turn-time]  # errored (stalled, silent) episodes aside
    python benchmarks/lmstudio/lms_campaign.py watch RUN_ID [--interval 60] [--idle 20]   # stop + set aside a stalled run's episode (0 steps, or a silent last turn)
    python benchmarks/lmstudio/lms_campaign.py score NAME [--print]

NAME is a key of ``models`` in ``benchmarks/lmstudio/models.json`` (``qwen3.5-9b``, ``qwen3.5-4b``, ``gemma-4-12b``).

What it fixes, so a local run is the same run as the plan:
- the code: the Runpod rig's worktree ``.claude/worktrees/runpod-k3`` at ``PIN`` (same check as
  ``benchmarks/runpod/runpod_campaign.py``), so edits to ``main`` during a run change nothing;
- the model file: ``lms load`` over LM Link takes only the bare key and loads the variant selected on the PC,
  so before a run the PC's selected variant and the loaded quantization must be the spec's, and the model is
  loaded alone at its own context (``context`` in models.json, found by ``fit``: the highest rung of ``LADDER``
  that loads, ceiling ``CONTEXT`` 131,072, floor ``FLOOR_CONTEXT`` 65,536), parallel 1 (the runner's
  ``--lms-context`` guard reloads it the same way);
- the setting: the Runpod rows' budget (30 min, 120 turns) and sampling (``extra_body``), ``--base-url`` named
  so ``pgrep`` finds a running rig;
- one model at a time: k = 3 is one process with ``--repeat 3`` (r1, r2, r3 in turn), never three at once,
  since a reload in one would unload the model under the others; the e3 harness runs at concurrency 1;
- the Mac stays awake: every launch runs under ``caffeinate -i`` (the PC's own sleep setting is Robert's).

The folder is ``benchmarks/probe_runs/2026-10-20-lms-k3`` (labels ``<label>-r1..r3``, logs ``run-<label>.log``);
the smoke probe runs as ``-r1`` so the repeat skips it. Nothing here starts a run until ``smoke``, ``k3`` or
``e3`` is called; ``check``, ``status`` and ``clear-errors --apply`` only load models, read state or move files.

Resuming a run (2026-10-26, after the 9B's d1-real run lost 61 of 99 episodes to a dead engine): the harness
resumes a run id by skipping every episode file with an end record, errored ones included, so ``clear-errors
RUN_ID --apply`` first moves the errored episodes into ``<run>/errored-<date>/``; then ``e3 NAME --run-id
RUN_ID --worktree PATH`` runs the rest from a worktree checked out at the run's own pin (``run.json``
``pins.commit``), so the resumed episodes see the same task set and engine as the first ones. ``--worktree``
must be clean in ``src`` and ``tests``; its HEAD is recorded in the run's pins as usual. A pin older than
291ae711 (2026-10-27) has no ``--context-tokens``: ``e3`` leaves the flag out for such a worktree (the 9B's d1-real
run at d98e7025) and the run keeps the budgets it had.

``e3 --system-extra FILE`` and ``e3 --thinking off`` (2026-11-14, the training plan's base rerun and T0) go to the
harness as they are. A relative FILE is the worktree's own copy (the pin's file, not main's, which moves), and a
worktree whose harness has no such flag is refused, since a run without it would be another run. ``thinking RUN_ID``
reads a run's episodes: the reasoning tokens against the output tokens, and whether the headers say thinking was off;
a run asked to answer without thinking that carries reasoning tokens means the server did not obey, and exits 1.
So does one with no thinking-off episode to judge by: an episode that ended in error, or that reports no output
tokens, shows nothing about the server (a request it refused ends that way), so it is not counted as obeyed.
``run-state RUN_ID`` says where a run stands for a queue that is relaunched: ``new``, ``partial`` (the harness
resumes it), ``finished`` (every cell ended and the report written) or ``other`` (run at another commit than
``--commit``, so not to be resumed from this pin).

A copy of this script inside a worktree (``<repo>/.claude/worktrees/<name>/benchmarks/lmstudio/``) is run as the
pin's own driver: the interpreter, ``results/e3-lms`` and the other worktrees are the main checkout's (``HOME``);
the specs (``models.json``) and the task sets are the copy's.

The context (2026-10-27): every ``e3`` run passes ``--context-tokens CONTEXT`` beside ``--lms-context CONTEXT``, so
the harness ends an episode whose prompt reaches the window as a ``context`` budget trip, the way vLLM's refusal
ends one on the hosted rows; LM Studio alone would truncate the prompt and answer.

The window (2026-10-28, Robert: "run at the highest context possible that will fit on my local machine; a model
that cannot run with enough context for these tasks leaves the list of local tested models"): ``fit NAME`` walks
``LADDER`` from ``CONTEXT`` down to ``FLOOR_CONTEXT``, records the first context LM Studio loads the model at as
``context`` in models.json (every run, check and vision load it there, and the runner guard reloads it there),
and below the floor marks the model ``dropped`` with the reason; ``e3``, ``check``, ``smoke``, ``k3`` and
``vision`` refuse a dropped model, ``fit`` alone takes it again. The floor is the hosted vLLM rows' window: at
65,536 about 17 in 100 of the 9B's d1-test episodes would have ended as context trips (its largest prompt 104k).

Stalls (2026-10-28): Gemma 4 12B Q8_0 at 98,304 on d1-test answered the harness's one-token probe before every
episode and then streamed empty chunks for the whole 30-minute turn limit, nine episodes in a row over five
hours, each scored 0 with 0 steps while LM Studio listed the model GENERATING; stopping the client and reloading
cleared it. An episode whose end record says ``turn_time`` with 0 steps is a *stall* (``stalled``), the engine's
outcome rather than the model's -- once; so is one that ended ``turn_time`` after steps when its last turn record
carried no tokens at all (2026-11-04: the 9B sat 1,800 s in one request the engine never answered, five times in
ten episodes, after 1 to 10 steps; the model's own over-long turn carries tokens). ``watch RUN_ID`` polls a run for one, stops the run's eval process (a
queue script's ``run_e3`` retry loop then reloads the model and resumes the run), moves the episode into
``<run>/errored-<date>/`` so the resume runs it again, and records it in ``<run>/watch.json``; a stall of the
same episode after that stays as the model's result. ``clear-errors --stalled`` does the move by hand.

Images (2026-10-27): the nine hard-pilots that come with a page (two scans to redraw, three to read, four marked-up
prints) reach the model through the harness's own route, a ``view_attachment`` result with the PNG as a data URL,
which LM Studio takes for a model with vision (``lms ls --json`` says which; ``vision`` in ``models.json`` records
it). ``e3 NAME --taskset hard-pilots --pilots images`` runs those nine, ``text`` the other 24, ``all`` (the default)
every pilot; a model without vision is refused the image pilots. ``vision NAME`` sends one lettered image through
that route first and records whether the model read it (``vision_check``), with what one image costs in prompt
tokens: a capability read, not a run.
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
from typing import Dict, List, Optional, Tuple

def home_repo(repo: Path) -> Path:
    """The main checkout: ``repo`` itself, or the checkout whose ``.claude/worktrees`` folder ``repo`` sits in."""
    if repo.parent.name == "worktrees" and repo.parent.parent.name == ".claude":
        return repo.parents[2]
    return repo


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HOME = home_repo(REPO)               # where the interpreter, the results and the worktrees live
SPECS = HERE / "models.json"
WORKTREE = HOME / ".claude" / "worktrees" / "runpod-k3"
PIN = "2658fa0"                      # the Runpod rig's pin (2026-10-19); tool surface 60eeeb21 since e7178a2
PYTHON = HOME / ".venv" / "bin" / "python"
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms")
CAMPAIGN = HOME / "benchmarks" / "probe_runs" / "2026-10-20-lms-k3"
E3_OUT = HOME / "results" / "e3-lms"
BASE_URL = "http://localhost:1234/v1"
MODELS_URL = "http://localhost:1234/api/v0/models"
DEVICE = "RobertsPC"
#: the context every local row is loaded at (2026-10-26, Robert: the largest the two 4060s hold for the 9B
#: by LM Studio's estimate, 13.3 of 16 GiB; 65,536 before that, which LM Studio silently truncated past on 8 of
#: the 9B's first 38 d1-real episodes). The hosted vLLM rows stay at their recorded 65,536.
CONTEXT = 131072
#: the floor (2026-10-28, Robert): a model that cannot load at this context has too little for these tasks and
#: is dropped from the local list. It is the hosted vLLM rows' window; 17 of the 9B's 100 d1-test episodes peaked
#: past it (the largest 104,370 tokens), so a row at the floor loses about that share to context trips.
FLOOR_CONTEXT = 65536
#: the rungs ``fit`` tries, highest first
LADDER = (131072, 114688, 98304, 81920, 65536)
LOAD_TIMEOUT_S = 300  # lms load over LM Link: 6-10 s when it works, hung for good when it does not

BUDGET_MIN, MAX_TURNS = 30, 120     # the hosted open-weight setting of the Runpod rows
#: the tool surfaces with the scrubbed help text (fe26ce2): 60eeeb21 to the engine merge of 2026-10-31,
#: 379e02f1 from it, 0334fd4a from the label-kind help of 2026-11-03 (what each kind letters; mc draws the bubble),
#: 9db020d9 from the stationing help of the same day (drawn in model space, never on a sheet; the sheet refusal's hint)
CLEAN_TOOLS = ("sha256:60eeeb2195be", "sha256:379e02f1995f", "sha256:0334fd4aaade", "sha256:9db020d9af1e")
CLEAN_INSTRUCTIONS = "sha256:4dff2849f3c5"
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


def context(m: dict) -> int:
    """The context this model loads at: ``context`` in models.json (set by ``fit``), else the ceiling."""
    return int(m.get("context") or CONTEXT)


def dropped_problem(m: dict) -> Optional[str]:
    """Why the model is off the local list, or None."""
    d = m.get("dropped")
    if not d:
        return None
    return f"dropped from the local list on {d.get('date')}: {d.get('reason')} (fit NAME tries it again)"


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


def load_alone(m: dict, gpu: Optional[str] = None, ctx: Optional[int] = None) -> subprocess.CompletedProcess:
    """Everything else unloaded, the spec's model at its context (``ctx`` to try another), parallel 1 (the
    runner guard's own load).

    Oct 23 2026: a ``load`` issued right behind ``unload --all`` over LM Link sat at "97%" for eight minutes with the
    server reporting ``loading``, and the CLI never returned; a second load after the unload had settled took 6 s.
    So wait for the unload to show on the server, give the CLI a deadline, and trust the server's state over the
    CLI's exit: the load counts when the server says ``loaded``.
    """
    lms("unload", "--all")
    wait_state(m["lms_key"], "not-loaded", 60)
    args = [LMS, "load", m["lms_key"], "--context-length", str(ctx or context(m)), "--parallel", "1", "-y"]
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


def loaded_problem(m: dict, ctx: Optional[int] = None) -> Optional[str]:
    """Why what the server serves is not the spec's model at its context (or ``ctx``), or None."""
    want = ctx or context(m)
    rows = [s for s in served() if s.get("state") == "loaded"]
    mine = [s for s in rows if s["id"] == m["lms_key"]]
    if len(rows) != 1 or not mine:
        return f"loaded: {[s['id'] for s in rows]} (want {m['lms_key']} alone)"
    if not same_quant(mine[0].get("quantization"), m["quantization"]):
        return f"{m['lms_key']} is loaded as {mine[0].get('quantization')}, not {m['quantization']}"
    if mine[0].get("loaded_context_length") != want:
        return f"{m['lms_key']} is loaded at {mine[0].get('loaded_context_length')}, not {want}"
    return None


# ------------------------------------------------------------------ preflight and commands

def git(*args: str, cwd: Path = WORKTREE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def preflight(m: Optional[dict] = None, worktree: Path = WORKTREE, allow_dropped: bool = False) -> None:
    problems = []
    if not worktree.is_dir():
        at = PIN if worktree == WORKTREE else "<the run's pins.commit>"
        problems.append(f"worktree missing: git worktree add --detach {worktree} {at}")
    else:
        head = git("rev-parse", "--short", "HEAD", cwd=worktree)
        if worktree == WORKTREE and not head.startswith(PIN) and not PIN.startswith(head):
            problems.append(f"worktree at {head}, not {PIN}")
        dirty = git("status", "--porcelain", "--", "src", "tests", cwd=worktree)
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
        why = None if allow_dropped else dropped_problem(m)
        if why:
            problems.append(why)
    if problems:
        sys.exit("preflight failed:\n- " + "\n- ".join(problems))


def ready(m: dict) -> None:
    """The spec's model loaded alone at its context, checked against the server's own record."""
    r = load_alone(m)
    why = loaded_problem(m) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-400:]
    if why:
        sys.exit(f"could not load {m['lms_key']} as specified: {why}")
    print(f"loaded {m['lms_key']} ({m['quantization']}) alone at context {context(m)} on {DEVICE}")


def child_env(worktree: Path = WORKTREE) -> Dict[str, str]:
    return dict(os.environ, PYTHONPATH=str(worktree / "src"))


def context_budget_in(worktree: Path = WORKTREE) -> bool:
    """Whether the worktree's harness takes ``--context-tokens`` (main since 291ae711, 2026-10-27). A resume from an
    older pin runs without it, under the budgets the run had; a missing worktree is preflight's to report."""
    main = worktree / "src" / "roaddraft" / "eval" / "__main__.py"
    return not main.is_file() or "--context-tokens" in main.read_text(encoding="utf-8")


def harness_takes(flag: str, worktree: Path = WORKTREE) -> bool:
    """Whether the worktree's harness has ``flag`` on its command line; a missing worktree is preflight's to report."""
    main = worktree / "src" / "roaddraft" / "eval" / "__main__.py"
    return not main.is_file() or f'"{flag}"' in main.read_text(encoding="utf-8")


def run_command(m: dict, label: str, probes: List[str], repeat: int = 1, force: bool = False) -> List[str]:
    cmd = ["caffeinate", "-i", str(PYTHON), "-m", "roaddraft.runners", "run", "--backend", "openai",
           "--model", m["lms_key"], "--base-url", BASE_URL, "--lms-context", str(context(m)),
           "--out", str(CAMPAIGN), "--label", label, "--budget", str(BUDGET_MIN), "--max-turns", str(MAX_TURNS)]
    if repeat > 1:
        cmd += ["--repeat", str(repeat)]
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
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
    print(f"{'name':14} {'model':36} {'quant':7} {'context':>8} {'est h':>6} {'label':24} board row")
    for name, m in data["models"].items():
        window = "dropped" if m.get("dropped") else (str(m["context"]) if m.get("context") else "to fit")
        print(f"{name:14} {m['name']:36} {m['quantization']:7} {window:>8} {m.get('est_k3_hours') or '':>6} "
              f"{m['label']:24} {m.get('board_row', '')}")
    return 0


def cmd_status(args) -> int:
    data = load()
    print(f"LM Link {DEVICE}: {'connected' if link_ok() else 'NOT connected'}")
    print(f"server localhost:1234: {'up' if server_up() else 'down (lms server start)'}")
    for s in loaded():
        print(f"loaded: {s['identifier']} {s['quantization']['name']} context {s.get('contextLength')} "
              f"parallel {s.get('parallel')}")
    files = downloaded()
    for name, m in data["models"].items():
        why = file_problem(m)
        seen = vision_flag(m, files)
        eyes = "vision" if seen else ("no vision" if seen is False else "vision unknown")
        if m.get("vision") is not None and seen is not None and bool(m["vision"]) != seen:
            eyes += f" (models.json says {m['vision']})"
        window = dropped_problem(m) or (f"context {m['context']}" if m.get("context") else "context not fitted (fit NAME)")
        print(f"{name:14} {'ready' if not why else why}; {eyes}; {window}")
    return 0


def vision_flag(m: dict, files: Optional[List[dict]] = None) -> Optional[bool]:
    """Whether LM Studio lists the spec's model as taking images; None when the file is not there."""
    for d in files if files is not None else downloaded():
        if d.get("modelKey") == m["lms_key"]:
            return bool(d.get("vision"))
    return None


PILOT_SET = REPO / "benchmarks" / "tasksets" / "hard-pilots.json"


def pilot_ids(kind: str) -> List[str]:
    """The hard-pilots task ids of one kind: ``images`` (the pilots that come with a page, served through
    ``view_attachment``), ``text`` (the rest), or ``all``."""
    rows = json.loads(PILOT_SET.read_text())
    rows = rows["tasks"] if isinstance(rows, dict) else rows
    want = {"images": lambda r: bool(r.get("attachments")), "text": lambda r: not r.get("attachments"),
            "all": lambda r: True}[kind]
    return [r["task_id"] for r in rows if want(r)]


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
    print("clean help text:", "yes" if ok else f"NO (expected one of {', '.join(CLEAN_TOOLS)}... / "
                                             f"{CLEAN_INSTRUCTIONS}...)")
    print("dirty files:", p.get("dirty") or "none")
    return 0 if ok and not p.get("dirty") else 1


def cmd_check(args) -> int:
    """Load the model alone at its context (all layers on the GPUs if they fit, else LM Studio's split), time one
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


def fit(m: dict, rungs=LADDER) -> dict:
    """Walk the ladder from the ceiling down: the first context LM Studio loads the model at is its ``context``;
    none at or above the floor drops it. Returns the record written to models.json (``fit`` or ``dropped``)."""
    tried = []
    for ctx in rungs:
        if ctx > CONTEXT or ctx < FLOOR_CONTEXT:
            continue
        r = load_alone(m, ctx=ctx)
        why = loaded_problem(m, ctx) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-300:]
        last = None if why is None else (why.strip().splitlines() or [why])[-1][-200:]
        tried.append({"context": ctx, "loaded": why is None, "why": last})
        print(f"{m['lms_key']} at {ctx:,}: {'loaded' if why is None else 'no: ' + last}")
        if why is None:
            m["context"] = ctx
            m.pop("dropped", None)
            m["fit"] = {"date": time.strftime("%Y-%m-%d"), "context": ctx, "ceiling": CONTEXT,
                        "floor": FLOOR_CONTEXT, "tried": tried}
            return m["fit"]
    reason = next((t["why"] for t in reversed(tried) if t.get("why")), "no rung tried")
    m["context"] = None
    m.pop("fit", None)
    m["dropped"] = {"date": time.strftime("%Y-%m-%d"), "floor": FLOOR_CONTEXT,
                    "reason": f"does not load at the floor {FLOOR_CONTEXT:,} on {DEVICE} ({reason})", "tried": tried}
    return m["dropped"]


def cmd_fit(args) -> int:
    """The highest context the PC loads this model at (``LADDER`` from ``CONTEXT`` down to ``FLOOR_CONTEXT``),
    recorded in models.json as ``context``; a model that does not load at the floor is ``dropped`` from the local
    list (Robert, 2026-10-28). The model stays loaded at its context, or is unloaded when dropped."""
    data = load()
    m = spec(data, args.name)
    preflight(m, allow_dropped=True)
    fit(m)
    save(data)
    if m.get("dropped"):
        lms("unload", "--all")
        print(f"{args.name}: DROPPED from the local list: {m['dropped']['reason']}")
        return 1
    print(f"{args.name}: context {m['context']:,} (ceiling {CONTEXT:,}, floor {FLOOR_CONTEXT:,}); models.json updated")
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
    if args.samples is None:   # d1-variance is the x 5 set; every other set runs x 1 (the ranked rows)
        args.samples = 5 if args.taskset == "d1-variance" else 1
    worktree = Path(args.worktree).resolve() if args.worktree else WORKTREE
    cmd = ["caffeinate", "-i", str(PYTHON), "-m", "roaddraft.eval", "run", "--taskset", args.taskset,
           "--model", m["lms_key"], "--provider", "openai", "--base-url", BASE_URL, "--lms-context", str(context(m))]
    if context_budget_in(worktree):
        cmd += ["--context-tokens", str(context(m))]
    else:
        print(f"note: the harness at {worktree} predates --context-tokens; the run keeps the budgets it had",
              file=sys.stderr)
    cmd += ["--out", str(E3_OUT), "--run-id", run_id, "--mode", args.mode, "--level", args.level,
            "--samples", str(args.samples), "--concurrency", "1"]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.taskset == "hard-pilots" and args.pilots != "all":
        ids = pilot_ids(args.pilots)
        cmd += [x for i in ids for x in ("--task", i)]
    if args.taskset == "hard-pilots" and args.pilots != "text" and m.get("vision") is not True:
        sys.exit(f"{args.name} is not marked as taking images in models.json (vision: {m.get('vision')}); "
                 f"the {len(pilot_ids('images'))} image pilots need a vision model: run `vision {args.name}` "
                 f"first, or --pilots text")
    if m.get("extra_body"):
        cmd += ["--extra-body", json.dumps(m["extra_body"])]
    # the training plan's T0 sheet and no-think base: passed on as given, never dropped for an older harness
    extra = getattr(args, "system_extra", None)
    if extra:
        path = Path(extra) if Path(extra).is_absolute() else worktree / extra
        if not path.is_file():
            sys.exit(f"--system-extra: no file at {path} (a relative path is read in the worktree)")
        cmd += ["--system-extra", str(path)]
    if getattr(args, "thinking", None):
        cmd += ["--thinking", args.thinking]
    for flag in ("--system-extra", "--thinking"):
        if flag in cmd and not harness_takes(flag, worktree):
            sys.exit(f"the harness at {worktree} has no {flag}; run from a worktree at a pin that has it")
    if args.dry_run:
        cmd.append("--dry-run")
    log = E3_OUT / f"{run_id}.log"
    if args.print:
        show(cmd, log, worktree)
        return 0
    if args.dry_run:
        return subprocess.run(cmd, cwd=REPO, env=child_env(worktree)).returncode
    preflight(m, worktree)
    ready(m)
    what = f"{args.taskset}" + (f"[:{args.limit}]" if args.limit else "")
    print(f"E3 {args.name}: {what} x {args.samples} sample(s) x {args.mode} x {args.level} -> {E3_OUT / run_id}; "
          f"log {log}; code {worktree} at {git('rev-parse', '--short', 'HEAD', cwd=worktree)}")
    rc = stream(cmd, log, worktree)
    print(f"exit {rc}; report with: {PYTHON} -m roaddraft.eval report {E3_OUT / run_id}")
    return rc


VISION_QUESTION = "What station and bearing are lettered on the attachment? Answer with the text only."


def lettered_image() -> bytes:
    """A 900 x 300 PNG with a station and a bearing lettered on it, drawn here so the check needs no file."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=48)
    draw.text((40, 50), "STA 12+50.00", fill="black", font=font)
    draw.text((40, 150), "N 45\u00b000'00\" E", fill="black", font=font)
    draw.line((40, 250, 860, 250), fill="black", width=4)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def cmd_vision(args) -> int:
    """One lettered image to the loaded model through the harness's own route -- a ``view_attachment`` call, its
    tool message, then the PNG as a data URL in a user message, as ``eval.providers.openai_compat`` sends every
    image -- and a question only the image answers. Records in models.json whether the model read it and what
    the image cost in prompt tokens (the same request without it, subtracted). The model is loaded alone at
    its context as for a run; nothing else may be running."""
    import base64
    data = load()
    m = spec(data, args.name)
    preflight(m)
    ready(m)
    sys.path.insert(0, str(REPO / "src"))
    from roaddraft.eval.providers.openai_compat import chat_messages
    png = base64.b64encode(lettered_image()).decode("ascii")
    call = {"id": "call_0", "type": "function",
            "function": {"name": "view_attachment", "arguments": json.dumps({"name": "check.png"})}}
    shown = {"ok": True, "name": "check.png", "size_px": [900, 300], "region": [0, 0, 1, 1],
             "region_px": [0, 0, 900, 300], "shown_px": [900, 300], "scale": 1.0}
    tools = [{"type": "function", "function": {
        "name": "view_attachment", "description": "Look at an image this task came with.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}}}}]

    def ask(with_image: bool):
        transcript = [
            {"role": "user", "text": "Look at the attachment check.png with view_attachment. " + VISION_QUESTION},
            {"role": "assistant", "text": "", "calls": [{"id": "call_0", "name": "view_attachment",
                                                            "params": {"name": "check.png"}}],
             "raw": {"role": "assistant", "content": "", "tool_calls": [call]}},
            {"role": "results", "note": None,
             "results": [{"id": "call_0", "name": "view_attachment", "content": json.dumps(shown),
                          "is_error": False, "images": [("image/png", png)] if with_image else []}]}]
        body = dict(m.get("extra_body") or {}, model=m["lms_key"], tools=tools, max_tokens=4000,
                    messages=chat_messages("You are checking an image route. Answer in one line.", transcript))
        req = urllib.request.Request(BASE_URL + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            reply = json.loads(urllib.request.urlopen(req, timeout=900).read())
        except urllib.error.HTTPError as ex:
            return None, None, f"HTTP {ex.code}: {ex.read().decode(errors='replace')[:300]}"
        msg = (reply.get("choices") or [{}])[0].get("message") or {}
        return (msg.get("content") or "").strip(), (reply.get("usage") or {}).get("prompt_tokens"), None

    text, with_tokens, error = ask(True)
    _, without_tokens, _ = ask(False) if error is None else (None, None, None)
    read = bool(text) and "12+50" in text.replace(" ", "")
    record = {"date": time.strftime("%Y-%m-%d"), "read": read, "reply": (text or "")[:200], "error": error,
              "prompt_tokens": with_tokens,
              "image_tokens": (with_tokens - without_tokens) if with_tokens and without_tokens else None,
              "image_px": [900, 300]}
    print(json.dumps(record, indent=1))
    m["vision_check"] = record
    m["vision"] = read
    save(data)
    print(f"{args.name}: {'read the image' if read else 'did NOT read the image'}; models.json updated")
    return 0 if read else 1


def cmd_clear_errors(args) -> int:
    """The episodes of a run that ended in an error (``termination`` ``error`` in their end record),
    listed, and with ``--apply`` moved into ``<run>/errored-<date>/`` so the harness runs them again on
    resume; ``--stalled`` adds the stalled ones (a silent first turn, 0 steps), ``--turn-time`` every episode
    that ended on the turn limit, after steps too. ``summary.json`` and ``episodes.json`` are left as they
    are: the resume rewrites both."""
    run_dir = Path(args.run_id) if Path(args.run_id).is_dir() else E3_OUT / args.run_id
    episodes = run_dir / "episodes"
    if not episodes.is_dir():
        sys.exit(f"no episodes under {run_dir}")
    errored, kept = [], 0
    for f in sorted(episodes.glob("*.jsonl")):
        end = end_record(f)
        if end is None:
            print(f"no end record (left to resume): {f.name}")
            continue
        if end.get("termination") == "error" or (getattr(args, "stalled", False) and stalled(end, last_turn(f))) \
                or (getattr(args, "turn_time", False) and silent_turn(end)):
            errored.append((f, end))
        else:
            kept += 1
    for f, end in errored:
        first = (end.get("error") or "").splitlines()[0][:100] if end.get("error") else ""
        kind = "stalled" if stalled(end, last_turn(f)) else "silent " if silent_turn(end) else "error  "
        print(f"{f.name.split('.')[0]}  {kind}  {end.get('steps', 0):3d} steps  {first}")
    print(f"{len(errored)} errored/stalled episode(s) of {len(errored) + kept} with an end record in {run_dir}")
    if not errored or not args.apply:
        if errored:
            print("dry run: pass --apply to move them aside")
        return 0
    dest = set_aside(run_dir, [f for f, _ in errored])
    print(f"moved {len(errored)} episode file(s) to {dest}; the run resumes them with e3 --run-id {run_dir.name}")
    return 0


# ------------------------------------------------------------------ did a run think (2026-11-14)

def thinking_tally(run_dir: Path) -> dict:
    """A run's finished episodes: how many, their output and reasoning tokens, how many headers record
    ``thinking: off`` (``provider_config``), how many of those can be judged (ended without error and report
    output tokens), and how many carry reasoning tokens all the same."""
    t = {"episodes": 0, "output_tokens": 0, "reasoning_tokens": 0, "off": 0, "off_judged": 0, "off_but_thought": 0}
    for f in sorted((run_dir / "episodes").glob("*.jsonl")):
        end = end_record(f)
        if end is None:
            continue
        with f.open(encoding="utf-8") as fh:
            header = json.loads(fh.readline())
        usage = end.get("usage_total") or {}
        output = int(usage.get("output_tokens") or 0)
        reasoning = int(usage.get("reasoning_tokens") or 0)
        off = (header.get("provider_config") or {}).get("thinking") == "off"
        t["episodes"] += 1
        t["output_tokens"] += output
        t["reasoning_tokens"] += reasoning
        t["off"] += off
        # an errored episode, or one with no output tokens on record, shows nothing about the server
        t["off_judged"] += off and end.get("termination") != "error" and output > 0
        t["off_but_thought"] += off and reasoning > 0
    return t


def cmd_thinking(args) -> int:
    """Whether a run thought: its reasoning tokens against its output tokens. Exit 1 when episodes run with
    ``--thinking off`` carry reasoning tokens (the server did not obey the request), when the run has no
    finished episode to judge by, or when none of its thinking-off episodes both ended without error and
    reports output tokens (a refused request ends in error with no tokens: that is not the server obeying);
    0 otherwise. A server that reports no reasoning tokens at all would pass
    unseen, so the share on a thinking run of the same model is the thing to compare with (the 9B: about three
    quarters of its output tokens)."""
    run_dir = Path(args.run_id) if Path(args.run_id).is_dir() else E3_OUT / args.run_id
    if not (run_dir / "episodes").is_dir():
        sys.exit(f"no episodes under {run_dir}")
    t = thinking_tally(run_dir)
    share = t["reasoning_tokens"] / t["output_tokens"] if t["output_tokens"] else 0.0
    print(f"{run_dir.name}: {t['episodes']} finished episode(s), {t['output_tokens']} output tokens, "
          f"{t['reasoning_tokens']} of them reasoning ({share:.1%}); {t['off']} run with thinking off, "
          f"{t['off_but_thought']} of those thought anyway")
    unjudged = bool(t["off"]) and not t["off_judged"]
    if unjudged:
        print("no thinking-off episode ended without error with output tokens on record: nothing shows the "
              "server obeyed --thinking off (read the episodes' errors, then run the check again)")
    if t["off_but_thought"]:
        print("the server did not obey --thinking off: load the model with thinking off in LM Studio, or a "
              "copy of it with the no-think template, and run again under a new run id")
    return 1 if t["off_but_thought"] or not t["episodes"] or unjudged else 0


# ------------------------------------------------------------------ where a run stands (2026-11-14)

def run_state(run_dir: Path, commit: Optional[str] = None) -> Tuple[str, str]:
    """Where a run stands, for a queue that is relaunched, as a word and a detail: ``new`` (no folder, or
    nothing in it), ``other`` (``run.json`` names another commit than ``commit``, or none: not this pin's run),
    ``finished`` (every cell has an end record and the report is written) or ``partial`` (the harness resumes
    it, skipping the episodes that ended)."""
    episodes = run_dir / "episodes"
    files = sorted(episodes.glob("*.jsonl")) if episodes.is_dir() else []
    if not (run_dir / "run.json").is_file():
        return ("partial", f"{len(files)} episode file(s) and no run.json") if files else ("new", "no run yet")
    record = json.loads((run_dir / "run.json").read_text())
    ran_at = (record.get("pins") or {}).get("commit") or ""
    if commit and ran_at != commit:
        return "other", f"run at {ran_at[:8] or 'no recorded commit'}, not at {commit[:8]}"
    ended = sum(end_record(f) is not None for f in files)
    cells = int(record.get("cells") or 0)
    if cells and ended >= cells and (run_dir / "report").exists():
        return "finished", f"{ended} of {cells} episodes ended, report written"
    return "partial", f"{ended} of {cells} episodes ended" + ("" if ended < cells or not cells else ", no report")


def cmd_run_state(args) -> int:
    """Print where a run stands (``run_state``): the word first, then the detail. Always exit 0."""
    run_dir = Path(args.run_id) if Path(args.run_id).is_dir() else E3_OUT / args.run_id
    print(*run_state(run_dir, args.commit))
    return 0


# ------------------------------------------------------------------ stalled episodes (2026-10-28)

STALL_TRIP = "turn_time"
WATCH_INTERVAL_S = 60
WATCH_IDLE_MIN = 20        # a queue script's retry gap is 10 min plus a model load


def end_record(path: Path) -> Optional[dict]:
    """The episode file's end record, or None while the episode is still being written."""
    for line in path.read_text(encoding="utf-8").splitlines()[::-1]:
        if line.strip():
            rec = json.loads(line)
            return rec if rec.get("type") == "end" else None
    return None


def last_turn(path: Path) -> Optional[dict]:
    """The episode file's last turn record, or None before the first turn."""
    for line in path.read_text(encoding="utf-8").splitlines()[::-1]:
        if line.strip():
            rec = json.loads(line)
            if rec.get("type") == "turn":
                return rec
    return None


def silent_record(turn: dict) -> bool:
    """A turn record the engine answered with nothing: a usage with no output tokens and an assistant with no text
    and no call (the request sat until the read timed out). A record without a usage key (older files, test stubs)
    is not judged."""
    if "usage" not in turn:
        return False
    usage = turn.get("usage") or {}
    tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    said = turn.get("assistant") or {}
    return not tokens and not said.get("text") and not said.get("tool_calls")


def silent_turn(end: dict) -> bool:
    """An episode that ended on the provider's turn limit: a turn that carried nothing for 30 minutes, the shape of
    the Oct 28 stall, on the first turn or after steps (the 9B's four "over-long turns" on d1-test, 2026-10-27)."""
    return end.get("budget_tripped") == STALL_TRIP


def stalled(end: dict, last: Optional[dict] = None) -> bool:
    """An episode the engine, not the model, ended: a silent turn as its first (0 steps; see "Stalls" above), or,
    given the file's last turn record, a ``turn_time`` end after steps whose last turn carried no tokens at all
    (2026-11-04). A turn-limit end whose last turn carried tokens (the model talked and ran long), or a wall-clock
    trip, ``watch`` leaves as the model's outcome; ``clear-errors --turn-time`` sets every turn-limit end aside by
    hand (Robert, 2026-10-28: the 9B's five rerun)."""
    if not silent_turn(end):
        return False
    return not end.get("steps") or (last is not None and silent_record(last))


def stalled_episodes(run_dir: Path, reruns: Dict[str, int], max_reruns: int = 1) -> List[Path]:
    """The episode files of ``run_dir`` with a stalled end record that have been set aside fewer than
    ``max_reruns`` times (``reruns`` by file name): a stall that repeats after a reload is the model's result."""
    out: List[Path] = []
    episodes = run_dir / "episodes"
    if not episodes.is_dir():
        return out
    for f in sorted(episodes.glob("*.jsonl")):
        end = end_record(f)
        if end is not None and stalled(end, last_turn(f)) and reruns.get(f.name, 0) < max_reruns:
            out.append(f)
    return out


def set_aside(run_dir: Path, files: List[Path]) -> Path:
    """Move episode files into ``<run>/errored-<date>/`` (a second copy of a name gets a numbered suffix)."""
    dest = run_dir / f"errored-{time.strftime('%Y-%m-%d')}"
    dest.mkdir(exist_ok=True)
    for f in files:
        target, n = dest / f.name, 1
        while target.exists():
            target, n = dest / f"{f.name}.{n}", n + 1
        f.rename(target)
    return dest


def run_processes(run_id: str) -> List[int]:
    """The pids of the eval harness (and its caffeinate) running ``run_id``."""
    r = subprocess.run(["pgrep", "-f", f"roaddraft.eval run .*--run-id {run_id}( |$)"], capture_output=True, text=True)
    return [int(p) for p in r.stdout.split() if p.strip().isdigit()]


def cmd_watch(args) -> int:
    """Poll a run for a stalled episode every ``--interval`` s. On one: stop the run's eval process (a queue
    script's retry loop reloads the model and resumes), move the episode aside so the resume runs it again,
    note it in ``<run>/watch.json``. Ends after ``--idle`` minutes with no eval process once the run has begun."""
    run_dir = E3_OUT / args.run_id
    state_path = run_dir / "watch.json"
    log = E3_OUT / f"watch-{args.run_id}.log"

    def note(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with log.open("a") as fh:
            fh.write(line + "\n")

    state = json.loads(state_path.read_text()) if state_path.exists() else {"reruns": {}, "events": []}
    note(f"watching {args.run_id} every {args.interval} s (stall = {STALL_TRIP} with 0 steps, or after steps when "
         f"the last turn carried no tokens; {args.max_reruns} rerun(s) each); ends after {args.idle} min without an "
         f"eval process")
    idle_since: Optional[float] = None
    while True:
        pids = run_processes(args.run_id)
        if pids:
            idle_since = None
        elif run_dir.is_dir():
            idle_since = idle_since or time.time()
            if time.time() - idle_since >= args.idle * 60:
                note(f"no eval process for {args.idle} min; the run is over or abandoned; stopping")
                return 0
        found = stalled_episodes(run_dir, state["reruns"], args.max_reruns)
        if found:
            names = [f.name.split(".")[0] for f in found]
            note(f"stalled: {names}; stopping pids {pids} so the queue's retry reloads the model and resumes")
            for pid in pids:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
            for _ in range(30):
                if not run_processes(args.run_id):
                    break
                time.sleep(1)
            dest = set_aside(run_dir, found)
            for f in found:
                state["reruns"][f.name] = state["reruns"].get(f.name, 0) + 1
            state["events"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "stalled": names,
                                    "stopped": pids, "aside": str(dest)})
            state_path.write_text(json.dumps(state, indent=1))
            note(f"moved {len(found)} episode(s) to {dest}" + ("" if pids else
                 f"; no eval process was running: resume by hand with e3 ... --run-id {args.run_id}"))
        time.sleep(args.interval)


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
    f = sub.add_parser("fit"); f.add_argument("name"); f.set_defaults(fn=cmd_fit)
    v = sub.add_parser("vision"); v.add_argument("name"); v.set_defaults(fn=cmd_vision)
    sm = sub.add_parser("smoke"); sm.add_argument("name"); sm.add_argument("--probe", default="edge-c102")
    sm.add_argument("--print", action="store_true"); sm.set_defaults(fn=cmd_smoke)
    k = sub.add_parser("k3"); k.add_argument("name"); k.add_argument("probes", nargs="*")
    k.add_argument("--force", action="store_true"); k.add_argument("--print", action="store_true")
    k.set_defaults(fn=cmd_k3)
    e3 = sub.add_parser("e3"); e3.add_argument("name"); e3.add_argument("--taskset", default="d1-variance")
    e3.add_argument("--samples", type=int, help="default 5 on d1-variance, 1 on every other set")
    e3.add_argument("--mode", default="single")
    e3.add_argument("--level", default="explicit"); e3.add_argument("--limit", type=int)
    e3.add_argument("--run-id"); e3.add_argument("--dry-run", action="store_true")
    e3.add_argument("--pilots", choices=["text", "images", "all"], default="all",
                    help="hard-pilots only: the 24 text pilots, the 9 that come with a page, or every one")
    e3.add_argument("--worktree", help=f"the checkout to run from (default {WORKTREE}); a resume uses one "
                                         "at the run's own pins.commit")
    e3.add_argument("--system-extra", metavar="FILE", help="a file appended to the system prompt (the harness's "
                    "flag; training plan T0); a relative path is read in the worktree")
    e3.add_argument("--thinking", choices=["off"], help="ask the server to answer without thinking (the harness's "
                    "flag); check the run with `thinking RUN_ID`")
    e3.add_argument("--print", action="store_true"); e3.set_defaults(fn=cmd_e3)
    th = sub.add_parser("thinking"); th.add_argument("run_id", help="a run id under results/e3-lms, or a path")
    th.set_defaults(fn=cmd_thinking)
    rs = sub.add_parser("run-state"); rs.add_argument("run_id", help="a run id under results/e3-lms, or a path")
    rs.add_argument("--commit", help="the commit the run must have been made at (run.json pins.commit)")
    rs.set_defaults(fn=cmd_run_state)
    ce = sub.add_parser("clear-errors"); ce.add_argument("run_id", help="a run id under results/e3-lms, or a path")
    ce.add_argument("--apply", action="store_true", help="move them; without it, list only")
    ce.add_argument("--stalled", action="store_true",
                    help="also the stalled ones (turn_time with 0 steps, or after steps with a last turn that carried no tokens)")
    ce.add_argument("--turn-time", action="store_true",
                    help="also every turn_time trip, after steps too (a silent turn; the 9B's rerun of 2026-10-28)")
    ce.set_defaults(fn=cmd_clear_errors)
    w = sub.add_parser("watch"); w.add_argument("run_id", help="a run id under results/e3-lms")
    w.add_argument("--interval", type=int, default=WATCH_INTERVAL_S, help="seconds between looks")
    w.add_argument("--idle", type=int, default=WATCH_IDLE_MIN, help="minutes without an eval process before it ends")
    w.add_argument("--max-reruns", type=int, default=1, help="stalls of one episode set aside before it stays")
    w.set_defaults(fn=cmd_watch)
    sc = sub.add_parser("score"); sc.add_argument("name"); sc.add_argument("--print", action="store_true")
    sc.set_defaults(fn=cmd_score)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
