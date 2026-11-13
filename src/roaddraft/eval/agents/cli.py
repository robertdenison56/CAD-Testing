"""The CLI agent: a headless coding CLI (Claude Code, Codex) runs the whole
episode, with the harness as its MCP server.

The CLI drives its own tool-calling loop against an MCP server it starts, so
the harness becomes that server: the episode's tools -- the whitelist and
the harness's own three -- are served to the CLI by a small
stdio bridge (``eval/bridge.py``, the CLI's one MCP server) that forwards
every ``tools/call`` to this agent over a local socket.  ``act`` hands each
call to the loop as a turn and, on the next ``act``, hands the loop's
results back to the bridge, in order, with a render's image in the vision
mode.  So the budgets, the whitelist, the result cap, the file
confinement and the trajectory are the harness's, as for an API row; what a
CLI row keeps of its own is the CLI's harness between the model and the
tools (its context handling, retries and parallel calls), which is why the
row carries ``provider: claude-code`` or ``codex``.

A turn is the calls that arrive together (within ``TURN_GAP``), as the Track
P codex backend counts them.  ``submit``: when the CLI calls it, the agent
answers that call itself (its result is fixed), waits for the CLI to finish
-- its closing words and, for Codex, the whole run's token count arrive only
then -- and hands the loop the call last, after any calls that came with it.
A CLI that stops without calling submit has submitted (``Submit(implicit)``,
its last words the note).  The wall clock is held here too: a CLI that has
not called a tool by the deadline is killed, and the loop ends the episode
as ``wall_clock``.  A CLI that ends without finishing its run -- not signed
in, no such model, an account limit -- is an ``error``: the harness's
outcome, not the model's.  When the loop ends the episode while the CLI is
waiting (a budget), the CLI is killed with its bridge: nothing more is
asked of the model.

The system prompt is the eval's (``eval.prompts``, as the LLM agent builds
it, with the run's ``--system-extra`` appended when it has one), given to the
CLI in place of its own -- Claude Code's ``--system-prompt``, Codex's
``model_instructions_file`` -- so a CLI row is told the extra exactly as an
API row is; the task text is its first user message.  The CLI's own event
stream and stderr are kept beside the trajectories, under ``<run>/cli/``, for
the record.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from roaddraft.eval import prompts
from roaddraft.eval.agents.basic import Action, Agent, Submit, ToolCall
from roaddraft.eval.agents.llm import result_text, system_for
from roaddraft.eval.budget import Budgets
from roaddraft.eval.providers.base import add_usage
from roaddraft.eval.providers.cli import BRIDGE, CLIProvider

#: seconds within which calls arriving together are one turn
TURN_GAP = 0.2
#: seconds the CLI gets to finish after its submit call is answered
SUBMIT_GRACE = 120.0
#: seconds the CLI gets to exit after its bridge said goodbye
EXIT_GRACE = 10.0
#: a Unix socket path longer than this will not bind on every platform
SOCKET_PATH_MAX = 90


def _listen() -> Tuple[socket.socket, str, Optional[str]]:
    """A listening socket for the bridge: a Unix socket in a short temporary
    folder where there is one, else TCP on the loopback at a free port.
    Returns the socket, its address as the bridge takes it, and the folder."""
    if hasattr(socket, "AF_UNIX"):
        folder = tempfile.mkdtemp(prefix="rd-")
        path = os.path.join(folder, "s")
        if len(path.encode("utf-8")) <= SOCKET_PATH_MAX:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(path)
            sock.listen(1)
            return sock, f"unix:{path}", folder
        shutil.rmtree(folder, ignore_errors=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, f"tcp:127.0.0.1:{sock.getsockname()[1]}", None


class Link:
    """The harness's end of the bridge: one listening socket per episode, the
    bridge's hello answered with the tool list, each call queued as an
    event ``("call", id, name, arguments)``; ``("bye",)`` when the bridge's
    CLI closed it."""

    def __init__(self, tools: List[dict]):
        self.tools = tools
        self.events: "queue.Queue" = queue.Queue()
        self.sock, self.address, self._folder = _listen()
        self._stop = False
        self._conn: Optional[socket.socket] = None
        self._wfile = None
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        self.sock.settimeout(0.25)
        conn = None
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                break
            except socket.timeout:
                continue
            except OSError:
                return
        if conn is None:
            return
        conn.settimeout(None)
        self._conn = conn
        rfile = conn.makefile("r", encoding="utf-8")
        with self._lock:
            self._wfile = conn.makefile("w", encoding="utf-8")
        try:
            if not rfile.readline():            # the hello
                return
            self._send({"type": "tools", "tools": self.tools})
            for line in rfile:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("type") == "call":
                    self.events.put(("call", msg.get("id"), str(msg.get("name")),
                                     msg.get("arguments") or {}))
                elif msg.get("type") == "bye":
                    break
        except (OSError, ValueError):
            pass
        finally:
            self.events.put(("bye",))

    def _send(self, payload: dict) -> None:
        with self._lock:
            if self._wfile is None:
                return
            try:
                self._wfile.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._wfile.flush()
            except (OSError, ValueError):
                pass

    def respond(self, call_id: Any, content: List[dict], is_error: bool = False) -> None:
        self._send({"type": "result", "id": call_id, "content": content, "isError": bool(is_error)})

    def close(self) -> None:
        self._stop = True
        self._send({"type": "close"})
        for s in (self._conn, self.sock):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        self.thread.join(timeout=2)
        if self._folder:
            shutil.rmtree(self._folder, ignore_errors=True)


def mcp_tool(definition: dict) -> dict:
    """A harness tool definition as an MCP tool."""
    return {"name": definition["name"],
            "description": definition.get("description") or definition["name"],
            "inputSchema": definition.get("input_schema")
            or {"type": "object", "properties": {}}}


def content_blocks(result: dict, images: Optional[Sequence[Tuple[str, str]]] = None) -> List[dict]:
    """A bus result as MCP content: the compact JSON the LLM agent sends,
    then the images (vision mode)."""
    blocks: List[dict] = [{"type": "text", "text": result_text(result)}]
    for mime, data in images or []:
        blocks.append({"type": "image", "data": data, "mimeType": mime})
    return blocks


def _not_run(name: str, message: str) -> dict:
    return {"ok": False, "name": name, "error": {"type": "not_run", "message": message}}


class CLIAgent(Agent):
    """One model through one headless CLI, for one episode at a time."""

    def __init__(self, provider: CLIProvider, label: Optional[str] = None,
                 system: Optional[str] = None):
        self.provider = provider
        self.name = label or provider.model
        self.fixed_system = system
        self.system = ""
        self.budgets: Optional[Budgets] = None
        self.episode_path = None
        self._clear()

    def _clear(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.link: Optional[Link] = None
        self.stream = None
        self.work: Optional[tempfile.TemporaryDirectory] = None
        self._pending: List[Tuple[Any, str]] = []
        self._queued_submit: Optional[Tuple[Any, str, dict]] = None
        self._usage: Dict[str, int] = {}
        self._record: dict = {}
        self._stderr: List[str] = []
        self._threads: List[threading.Thread] = []
        self._raw = None
        self._calls = 0
        self._killed: Optional[str] = None
        self._started = time.monotonic()

    # ------------------------------------------------------------ lifecycle

    def reset(self, task, level: str, mode: str) -> None:
        self.provider.reset(task)
        self._clear()
        self.system = self.fixed_system or prompts.system_prompt("neutral", mode)

    def ready(self) -> bool:
        return self.provider.ready()

    def begin(self, context: dict) -> None:
        self.budgets = context.get("budgets")
        self.episode_path = context.get("episode_path")
        self._started = time.monotonic()
        self.system = system_for(context, self.fixed_system)

    def close(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self._kill("the episode ended")
        self._join_readers()
        if self.link is not None:
            self.link.close()
        if self._raw is not None:
            self._raw.close()
            self._raw = None
        if self.episode_path and self._stderr:
            self._side_path("stderr.log").write_text("".join(self._stderr))
        if self.work is not None:
            self.work.cleanup()
            self.work = None

    # ----------------------------------------------------------------- turns

    def act(self, observation: dict) -> Action:
        self._usage, self._record = {}, {}
        if self.proc is None:
            self._launch(observation)
        else:
            self._answer(observation)
        return self._next()

    def _side_path(self, suffix: str) -> Path:
        ep = Path(self.episode_path)
        folder = ep.parent.parent / "cli"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{ep.stem}.{self.provider.name}.{suffix}"

    def _launch(self, observation: dict) -> None:
        tools = [mcp_tool(t) for t in observation.get("tools") or []]
        self.work = tempfile.TemporaryDirectory(prefix="roaddraft-cli-")
        work = Path(self.work.name)
        project = work / "project"
        project.mkdir()
        self.link = Link(tools)
        self.stream = self.provider.stream()
        bridge = [sys.executable, str(BRIDGE), self.link.address]
        argv = self.provider.argv(observation["brief"], self.system, bridge, work,
                                 self.budgets or Budgets())
        if self.episode_path:
            self._raw = self._side_path("jsonl").open("w", encoding="utf-8")
        self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, cwd=str(project),
                                     env=self.provider.env(), start_new_session=True)
        self._threads = [threading.Thread(target=f, daemon=True)
                         for f in (self._read_stdout, self._read_stderr, self._wait_exit)]
        for t in self._threads:
            t.start()

    def _read_stdout(self) -> None:
        for line in self.proc.stdout:
            if self._raw is not None:
                try:
                    self._raw.write(line)
                except ValueError:  # closed at the end of the episode
                    pass
            self.stream.feed(line)

    def _read_stderr(self) -> None:
        for line in self.proc.stderr:
            if len(self._stderr) < 2000:
                self._stderr.append(line)

    def _wait_exit(self) -> None:
        rc = self.proc.wait()
        self.link.events.put(("exit", rc))

    def _join_readers(self) -> None:
        for t in self._threads:
            t.join(timeout=5)

    def _answer(self, observation: dict) -> None:
        """The loop's results, to the bridge, one per pending call in order."""
        results = observation.get("results") or []
        images = observation.get("images") or []
        for i, (call_id, name) in enumerate(self._pending):
            if i < len(results):
                r = results[i]
            else:
                r = _not_run(name, "not run: the turn stopped before this call")
            self.link.respond(call_id, content_blocks(r, images[i] if i < len(images) else None),
                              not r.get("ok", False))
        self._pending = []

    def _deadline(self) -> Optional[float]:
        wall = getattr(self.budgets, "wall_clock_s", 0) or 0
        return self._started + wall if wall else None

    def _next(self) -> Action:
        if self._queued_submit is not None:
            return self._finish_submit()
        deadline = self._deadline()
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                self._kill("wall_clock")
                self._take_stream()
                return []                      # the loop trips the wall clock next
            try:
                event = self.link.events.get(timeout=remaining)
            except queue.Empty:
                continue
            if event[0] == "call":
                return self._turn([event] + self._more_calls())
            return self._ended()

    def _more_calls(self) -> List[tuple]:
        """Calls that arrive within ``TURN_GAP`` of the first: the same turn."""
        more: List[tuple] = []
        end = time.monotonic() + TURN_GAP
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return more
            try:
                event = self.link.events.get(timeout=remaining)
            except queue.Empty:
                return more
            if event[0] != "call":
                self.link.events.put(event)    # the CLI's end waits its turn
                return more
            more.append(event)

    def _turn(self, calls: List[tuple]) -> Action:
        turn, submit = [], None
        for _, call_id, name, args in calls:
            args = dict(args) if isinstance(args, dict) else {}
            if submit is None and name == "submit":
                submit = (call_id, name, args)
            else:
                turn.append((call_id, name, args))
        self._calls += len(calls)
        self._pending = [(call_id, name) for call_id, name, _ in turn]
        self._queued_submit = submit
        self._take_stream()
        if turn:
            return [ToolCall(name, args) for _, name, args in turn]
        return self._finish_submit()

    def _finish_submit(self) -> Action:
        """Answer the CLI's submit call, let it finish, hand the loop the call."""
        call_id, name, args = self._queued_submit
        self._queued_submit = None
        self.link.respond(call_id, content_blocks({"ok": True, "name": name, "message": "submitted"}))
        deadline = self._deadline()
        grace = SUBMIT_GRACE if deadline is None else max(1.0, min(SUBMIT_GRACE, deadline - time.monotonic()))
        self._wait(grace, "finished after submit")
        self._take_stream(final=True)
        return [ToolCall(name, args)]

    def _ended(self) -> Action:
        """The CLI is done (its bridge said goodbye, or it exited)."""
        rc = self._wait(EXIT_GRACE, "did not exit")
        self._take_stream(final=True)
        if self.stream.error:
            raise RuntimeError(f"{self.provider.name}: {self.stream.error}")
        if self._killed:
            raise RuntimeError(f"{self.provider.name}: the CLI was killed ({self._killed})")
        if self.stream.stop is None and rc not in (0, None):
            raise RuntimeError(f"{self.provider.name}: {self.provider.exit_error(rc, ''.join(self._stderr))}")
        return Submit(note=self.stream.final, implicit=True)

    def _wait(self, timeout: float, why: str) -> Optional[int]:
        """Wait up to ``timeout`` seconds for the CLI to exit, kill it past
        that, and read its stream to the end."""
        if self.proc is None:
            return None
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(why)
            rc = self.proc.wait(timeout=5) if self.proc.poll() is None else self.proc.returncode
        self._join_readers()
        return rc

    def _kill(self, why: str) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self._killed = self._killed or why
        try:                                   # the CLI and its bridge together
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            self.proc.kill()

    def _take_stream(self, final: bool = False) -> None:
        usage, record = self.stream.take()
        add_usage(self._usage, usage)
        for key in ("text", "thinking"):
            if record.get(key):
                self._record[key] = (self._record[key] + "\n" + record[key]
                                     if self._record.get(key) else record[key])
        if record.get("stop"):
            self._record["stop"] = record["stop"]
        if final and self.stream.extra:
            self._record["cli"] = dict(self.stream.extra)

    # ---------------------------------------------------------------- record

    def usage(self) -> Dict[str, int]:
        return dict(self._usage)

    def turn_record(self) -> dict:
        return dict(self._record)

    def describe(self) -> dict:
        return {"model": self.provider.model, "provider": self.provider.name,
                "effort": self.provider.effort, "label": self.name,
                "prompt_sha256": prompts.digest(self.system) if self.system else None,
                "system_prompt": self.system, "provider_config": self.provider.describe(),
                "billing": "subscription"}


__all__ = ["TURN_GAP", "SUBMIT_GRACE", "EXIT_GRACE", "Link", "CLIAgent", "mcp_tool",
           "content_blocks"]
