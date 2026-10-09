"""What every backend shares: the server over stdio, the run folder, the
episode, the transcript, and a price list for the cost column.

The run folder is the one the rigs under ``benchmarks/probe_runs`` left and
the scorers read::

    runs/<label>/<probe>/
        project/            the fresh start, autosaved as the model works: what is scored
        server.json         the server command, as the rigs kept it
        prompt.txt          the exact user message the model was handed
        trace.jsonl         every tool call as the server saw it (``--trace``)
        transcript.json     every message, thinking included, and the seconds each turn took
        report.txt          the model's final answer
        run.json            stop reason, turns, seconds, tokens, cost, and the pins
        renders/            what the model looked at (not tracked)
"""
from __future__ import annotations

import functools
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from roaddraft.probes import fixture, prompting
from roaddraft.probes.base import Probe

#: Anthropic list prices per million tokens (input, output), 2026-10-06. Cache
#: reads are a tenth of input, cache writes a quarter more. Unknown models
#: (local ones) have no cost column.
PRICES: Dict[str, Tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}
CACHE_READ, CACHE_WRITE = 0.1, 1.25

#: the image note every text-only run carries, as the earlier rigs did
IMAGE_OMITTED = "[image content omitted: this run is text-only -- the text above carries the file path]"

#: characters of one tool result a model is shown, whatever the backend: about
#: the cap Claude Code's Bash tool puts on a command's output, which is what the
#: shell-bridge runs saw. Added to the LM Studio rig on 2026-10-08 after
#: get_model_state with include_references on the L-2 start returned 748,312
#: characters (467,928 tokens), a request no context holds. No result in any
#: earlier run came near it (the largest was 12,886 characters).
RESULT_CAP = 30000


def cap_text(text: str, cap: int = RESULT_CAP) -> Tuple[str, bool]:
    """``text`` cut to its first ``cap`` characters with a note saying so, and
    whether it was cut."""
    if len(text) <= cap:
        return text, False
    return (text[:cap] + f"\n[output truncated: the first {cap} of {len(text)} characters are shown]",
            True)


@dataclass
class Options:
    """What the run is: the model, the caps, the mode, and backend extras."""
    model: str
    max_turns: int = 120
    budget: Optional[float] = None          # seconds per probe, checked between turns
    vision: bool = False                    # pass renders to the model as images
    effort: Optional[str] = None            # low | medium | high | xhigh | max, where the model takes it
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """What a tool call came back with, backend-neutral."""
    text: str
    is_error: bool = False
    images: List[Tuple[str, str]] = field(default_factory=list)   # (mime type, base64)
    protocol_error: Optional[str] = None

    def rendered(self, vision: bool = False) -> str:
        """The text a model is shown; images are a note unless the run is vision."""
        parts = ["[tool error]"] if self.is_error else []
        parts.append(self.text)
        if self.images and not vision:
            parts.append(IMAGE_OMITTED)
        return "\n".join(parts)


class McpServer:
    """One ``roaddraft-mcp`` over stdio, the rigs' client: initialize, the
    instructions and the tools, ``tools/call``, close. A result's text past
    ``RESULT_CAP`` is cut before any backend sees it; ``truncated`` counts the
    cuts."""

    def __init__(self, cmd: Sequence[str], cwd: Optional[Path] = None,
                 log: Optional[Path] = None, client_name: str = "roaddraft-runner"):
        self.cmd = list(cmd)
        self.truncated = 0
        self._log = open(log, "a") if log else subprocess.DEVNULL
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self._log, text=True, bufsize=1,
                                     cwd=str(cwd) if cwd else None)
        self.n = 0
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": client_name, "version": "1"}})
        self.instructions: str = init["result"].get("instructions", "")
        self.notify("notifications/initialized")
        self.tools: List[dict] = self.rpc("tools/list")["result"]["tools"]

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method: str, params: Optional[dict] = None) -> dict:
        self.n += 1
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("the MCP server closed its output")
            reply = json.loads(line)
            if reply.get("id") == self.n:
                return reply

    def call(self, name: str, arguments: Optional[dict]) -> ToolResult:
        reply = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if "error" in reply:
            message = reply["error"].get("message", "")
            return ToolResult(text=f"[protocol error] {message}", is_error=True,
                              protocol_error=message)
        result = reply["result"]
        texts, images = [], []
        for block in result.get("content", []):
            if block.get("type") == "text":
                texts.append(block["text"])
            elif block.get("type") == "image":
                images.append((block.get("mimeType", "image/png"), block.get("data", "")))
            else:
                texts.append(f"[{block.get('type')} content]")
        text, cut = cap_text("\n".join(texts))
        self.truncated += cut
        return ToolResult(text=text, is_error=bool(result.get("isError")), images=images)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        if self._log is not subprocess.DEVNULL:
            self._log.close()


@dataclass
class Setup:
    """A probe's fresh start: the document and the server command on it."""
    folder: Path
    doc: Path
    cmd: List[str]


def setup_probe(folder: Path, probe: Probe, server_command: Sequence[str]) -> Setup:
    """A fresh project for the probe under ``folder``, with ``server.json`` and
    ``prompt.txt`` beside it, the way ``setup_runs.py`` wrote them. The paths
    in the command are absolute: the server starts in ``project/``."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    doc = fixture.start_document(folder / "project", probe.start)
    cmd = list(server_command) + ["--doc", str(doc), "--autosave",
                                  "--trace", str(folder / "trace.jsonl"),
                                  "--out-dir", str(folder / "renders")]
    (folder / "server.json").write_text(json.dumps({"cmd": cmd}))
    (folder / "prompt.txt").write_text(prompting.task_text(probe))
    return Setup(folder=folder, doc=doc, cmd=cmd)


@dataclass
class Outcome:
    """How an episode ended."""
    stop: str                       # answered | max_turns | budget | length | refusal | error: ...
    final: str = ""                 # the report
    turns: int = 0
    usage: Dict[str, int] = field(default_factory=dict)
    cost_usd: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Episode:
    """One probe for one backend: everything it needs, and the log it fills."""
    folder: Path
    probe: Probe
    setup: Setup
    task: str
    options: Options
    server: Optional[McpServer] = None
    log: List[dict] = field(default_factory=list)   # what transcript.json keeps
    started: float = field(default_factory=time.time)

    def over_budget(self) -> bool:
        return bool(self.options.budget) and time.time() - self.started > self.options.budget

    def seconds(self) -> float:
        return round(time.time() - self.started, 1)


class Backend:
    """A vendor. ``run`` drives one episode to its outcome; the runner does
    the rest. ``needs_server`` is False for a backend whose client starts the
    server itself (Claude Code does, from an MCP config)."""
    name = ""
    needs_server = True

    def __init__(self, options: Options):
        self.options = options

    def run(self, episode: Episode) -> Outcome:  # pragma: no cover - abstract
        raise NotImplementedError


def estimate_cost(model: str, usage: Dict[str, int]) -> Optional[float]:
    """Dollars at list price, or None for a model the price list does not know."""
    prices = PRICES.get(model)
    if prices is None:
        return None
    per_in, per_out = prices
    dollars = (usage.get("input_tokens", 0) * per_in
               + usage.get("cache_read_input_tokens", 0) * per_in * CACHE_READ
               + usage.get("cache_creation_input_tokens", 0) * per_in * CACHE_WRITE
               + usage.get("output_tokens", 0) * per_out) / 1_000_000
    return round(dollars, 4)


@functools.lru_cache(maxsize=1)
def pins() -> Dict[str, Any]:
    """What an episode ran on, for the leaderboard to compare rows by: the
    package version, the engine commit and the files under ``src/`` changed
    past it, and digests of the tools and the instructions the server serves.
    The commit is None outside a git checkout."""
    from roaddraft import __version__
    from roaddraft.api.session import Session
    from roaddraft.mcp.server import INSTRUCTIONS
    from roaddraft.trajectories.convert import tool_list, tools_digest
    root = Path(__file__).resolve().parents[3]

    def git(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--", "src") if commit else None
    return {"roaddraft": __version__, "commit": commit.strip() if commit else None,
            "dirty": [line[3:] for line in (status or "").splitlines() if line.strip()],
            "tools_sha256": tools_digest(tool_list(Session())),
            "instructions_sha256": "sha256:" + hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()}


def run_probe(backend: Backend, folder: Path, probe: Probe, server_command: Sequence[str],
              force: bool = False, log=None) -> dict:
    """Set the probe up, run it on the backend, and leave the run folder.
    A probe that already has a report is skipped unless ``force``; the
    outcome is ``run.json``."""
    folder = Path(folder)
    if (folder / "report.txt").exists() and not force:
        return {"probe": probe.id, "skipped": True}
    if folder.exists():
        shutil.rmtree(folder)
    setup = setup_probe(folder, probe, server_command)
    episode = Episode(folder=folder, probe=probe, setup=setup,
                      task=prompting.task_text(probe), options=backend.options)
    try:
        if backend.needs_server:
            episode.server = McpServer(setup.cmd, cwd=folder / "project",
                                       log=folder / "server.log")
        outcome = backend.run(episode)
    except Exception as ex:  # the run folder keeps whatever happened
        outcome = Outcome(stop=f"error: {type(ex).__name__}: {ex}",
                          turns=sum(m.get("role") == "assistant" for m in episode.log))
    finally:
        if episode.server is not None:
            episode.server.close()
    meta = {"backend": backend.name, "model": backend.options.model, "probe": probe.id,
            "stop": outcome.stop, "turns": outcome.turns, "seconds": episode.seconds(),
            "tokens": outcome.usage, "cost_usd": outcome.cost_usd,
            "max_turns": backend.options.max_turns, "budget_s": backend.options.budget,
            "vision": backend.options.vision, "effort": backend.options.effort,
            "pins": pins()}
    if episode.server is not None:
        meta["truncated_results"] = episode.server.truncated
    meta.update(outcome.extra)
    (folder / "transcript.json").write_text(json.dumps({"meta": meta, "messages": episode.log},
                                                       indent=1, ensure_ascii=False))
    (folder / "report.txt").write_text(outcome.final or f"(no final answer: {outcome.stop})")
    (folder / "run.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), file=log or sys.stdout, flush=True)
    return meta


def text_of(blocks) -> str:
    """The text in a list of content blocks (or a string)."""
    if isinstance(blocks, str):
        return blocks
    return "\n".join(b.get("text", "") for b in blocks
                     if isinstance(b, dict) and b.get("type") == "text").strip()


#: filled by the backend modules; the CLI reads it
BACKENDS: Dict[str, type] = {}


def register(cls):
    BACKENDS[cls.name] = cls
    return cls
