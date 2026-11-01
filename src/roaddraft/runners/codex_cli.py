"""Codex in headless mode as a backend: a ChatGPT subscription, no API key.

``codex exec --json`` takes the task, a model and its reasoning effort, the
probe's server as the one MCP server, and exits with the final answer. Codex
starts ``roaddraft-mcp`` itself, so the server's trace and autosave work
exactly as for the other backends; the model calls the tools natively as
``mcp__roaddraft__<tool>``.

The harness is pared back the way the claude-code backend's is:
``--ignore-user-config`` and ``--ignore-rules`` drop the user's config.toml
(plugins, personality, notify, memories, hooks) and exec-policy rules, auth
still comes from ``~/.codex``; ``model_instructions_file`` replaces Codex's
own base instructions with the server's (the system message every backend
sends); the environment, permissions, apps and collaboration-mode messages
are switched off and so is ``AGENTS.md`` discovery, so the words the model
gets are the server's and the task's. The shell, web search, browser,
computer use, image generation, sub-agents and the rest are disabled as
features; what Codex keeps regardless (``apply_patch``, ``view_image``, the
clock and the MCP resource listers) runs under a read-only sandbox with no
approvals, so the document can change only through the server. The server's
tools are pre-approved (``default_tools_approval_mode = "approve"``);
otherwise ``approval_policy = "never"`` refuses every call. ``--ephemeral``
keeps the episodes out of the user's Codex history.

Codex has no turn cap, so the runner counts the model's turns as the stream
arrives and stops the process past ``max_turns``, the cap Claude Code's
``--max-turns`` sets: a turn is one model response, however many tool calls
it makes. Codex does not mark where a response ends, so the turns are told
apart by structure and timing: text or reasoning after a tool result starts a
new response (the model has to have read the result), and so does a tool call
that arrives ``TURN_GAP`` seconds or more after the event before it -- the
calls of one response come back to back, the next response waits on the
model. A response quicker than that merges with the one before, so turns can
be undercounted, never overcounted. (Counting tool calls instead cut
GPT-6-Astra off on stationing on 2026-10-14 after 96 ``station_to_xy`` calls
made at once: 122 calls, a handful of turns.) The budget is a wall clock, as
for claude-code. Tool results reach the model under Codex's own output limit,
not the runner's 30,000-character cap. Codex's own event stream is kept as
``codex.jsonl``.

The binary: ``--codex-bin``, ``$CODEX_BIN``, the copy inside the ChatGPT app,
then ``codex`` on PATH. The app's copy comes first because it updates with
the app: on 2026-10-12 the npm install (0.145) could not read the models
cache the app's 0.162 wrote and the service refused ``gpt-6-luna`` from it.
Since the app updates it on its own, each episode's ``run.json`` records
``codex --version``. A ``PYTHONPATH`` in the runner's environment is handed
to the server (Codex starts MCP servers with a short list of variables), so
a run from a pinned worktree serves that worktree's engine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from roaddraft.mcp import profiles
from roaddraft.mcp.server import INSTRUCTIONS
from roaddraft.runners.core import Backend, Episode, Outcome, register

SERVER_NAME = "roaddraft"
APP_BUNDLED = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"

#: features off: every built-in that could reach past the server
DISABLED = ("shell_tool", "apps", "browser_use", "browser_use_external", "computer_use",
            "image_generation", "in_app_browser", "multi_agent", "goals", "memories",
            "personality", "plugins", "skill_search", "hooks", "fast_mode")

#: the extra messages Codex adds around the task, off
QUIET = ("include_environment_context", "include_permissions_instructions",
         "include_apps_instructions", "include_collaboration_mode_instructions")

#: seconds of quiet before a tool call that mark a new model response
TURN_GAP = 0.2

#: words in a failed turn that mean the account, not the model, stopped it
LIMIT_WORDS = ("usage limit", "rate limit", "too many requests", "quota")


def find_codex(explicit: Optional[str] = None) -> str:
    """The CLI to run: ``--codex-bin``, ``$CODEX_BIN``, the ChatGPT app's copy,
    or ``codex`` on PATH."""
    for candidate in (explicit, os.environ.get("CODEX_BIN")):
        if candidate:
            return candidate
    if os.path.exists(APP_BUNDLED):
        return APP_BUNDLED
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    raise RuntimeError("no codex CLI found: install the ChatGPT app or Codex (npm i -g @openai/codex), "
                       "sign in, and pass --codex-bin or put it on PATH")


def toml(value: Any) -> str:
    """A ``-c`` value as TOML: strings and lists through JSON (a JSON string
    is a TOML basic string), booleans and numbers as they are, a dict as an
    inline table."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {toml(v)}" for k, v in value.items()) + "}"
    return json.dumps(value)


def server_env() -> Dict[str, str]:
    """What the server needs from the runner's environment: ``PYTHONPATH``,
    every entry made absolute. The CLI starts the server in the episode's
    ``project/`` folder, where a relative ``src`` names nothing, and Python
    would then import whatever is installed -- another checkout's engine --
    without a word (the 2026-10-27 Astra window ran on main's engine that way)."""
    return {k: absolute_path_list(os.environ[k]) for k in ("PYTHONPATH",) if os.environ.get(k)}


def absolute_path_list(value: str) -> str:
    """A ``PATH``-style list with each entry absolute against the current
    directory; empty entries dropped."""
    return os.pathsep.join(os.path.abspath(e) for e in value.split(os.pathsep) if e)


def codex_settings(instructions, server: Sequence[str], effort: Optional[str] = None,
                   env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The ``-c`` settings that pare Codex back as the module docstring says,
    with ``server`` (a command) as the one MCP server and ``instructions``
    (an absolute path) as the whole system prompt."""
    settings: Dict[str, Any] = {
        "approval_policy": "never",
        "model_instructions_file": str(instructions),
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        **{key: False for key in QUIET},
        f"mcp_servers.{SERVER_NAME}.command": server[0],
        f"mcp_servers.{SERVER_NAME}.args": list(server[1:]),
        f"mcp_servers.{SERVER_NAME}.default_tools_approval_mode": "approve",
        f"mcp_servers.{SERVER_NAME}.startup_timeout_sec": 60,
        f"mcp_servers.{SERVER_NAME}.tool_timeout_sec": 600,
    }
    if env:
        settings[f"mcp_servers.{SERVER_NAME}.env"] = dict(env)
    if effort:
        settings["model_reasoning_effort"] = effort
    return settings


def codex_argv(codex: str, task: str, model: str, instructions, server: Sequence[str],
               effort: Optional[str] = None, extra: Sequence[str] = (),
               env: Optional[Dict[str, str]] = None) -> List[str]:
    """``codex exec --json`` on ``task`` with the settings above, then
    ``extra`` arguments verbatim.  The eval harness's codex provider builds
    its command here too."""
    argv = [codex, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", model]
    for feature in DISABLED:
        argv += ["--disable", feature]
    for key, value in codex_settings(instructions, server, effort, env).items():
        argv += ["-c", f"{key}={toml(value)}"]
    argv += list(extra or [])
    argv.append(task)
    return argv


def codex_version(codex: str) -> Optional[str]:
    """``codex --version``, or None when it does not run."""
    try:
        out = subprocess.run([codex, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


@register
class CodexBackend(Backend):
    name = "codex"
    needs_server = False

    def __init__(self, options, codex_bin: Optional[str] = None):
        super().__init__(options)
        self.codex = find_codex(codex_bin or options.extra.get("codex_bin"))

    def command(self, episode: Episode) -> List[str]:
        instructions = (episode.folder / "instructions.md").resolve()   # the CLI runs from project/
        instructions.write_text(profiles.instructions(self.options.profile, INSTRUCTIONS))
        return codex_argv(self.codex, episode.task, self.options.model, instructions,
                          episode.setup.cmd, effort=self.options.effort,
                          extra=self.options.extra.get("codex_args") or [], env=server_env())

    def version(self) -> Optional[str]:
        """``codex --version``, asked per episode: the ChatGPT app updates its
        copy on its own, so a campaign can span two versions."""
        return codex_version(self.codex)

    def run(self, episode: Episode) -> Outcome:
        version = self.version()
        argv = self.command(episode)
        episode.log.append({"role": "system",
                            "content": profiles.instructions(self.options.profile, INSTRUCTIONS)})
        episode.log.append({"role": "user", "content": episode.task})
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                cwd=str(episode.folder / "project"))
        stopped: Dict[str, str] = {}

        def stop(why: str) -> None:
            if proc.poll() is None:
                stopped.setdefault("why", why)
                proc.kill()

        timer = threading.Timer(self.options.budget, stop, ("budget",)) if self.options.budget else None
        if timer:
            timer.daemon = True
            timer.start()
        err_lines: List[str] = []
        reader = threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True)
        reader.start()
        stream = Stream(episode)
        try:
            with open(episode.folder / "codex.jsonl", "w") as raw:
                for line in proc.stdout:
                    raw.write(line)
                    stream.feed(line)
                    if stream.turns > self.options.max_turns:
                        stop("max_turns")
            proc.wait()
        finally:
            if timer:
                timer.cancel()
            reader.join(timeout=5)
        (episode.folder / "codex.log").write_text("".join(err_lines))
        outcome = stream.outcome()
        outcome.extra["codex_version"] = version
        if stopped:
            outcome.stop = stopped["why"]
        elif proc.returncode != 0 and (outcome.stop == "answered" or outcome.stop == Stream.UNFINISHED):
            text = "".join(err_lines).strip()
            outcome.stop = f"error: codex exited {proc.returncode}: {text[-300:]}"
        return outcome


class Stream:
    """``codex exec --json``, event by event, into the transcript and the
    outcome. The transcript keeps the API backends' shape: an assistant
    message holds one model response -- reasoning, text and the tool calls it
    made -- and the user message after it the results, as ``tool_result``
    blocks. Where one response ends and the next begins is read from the
    stream as the module docstring says."""

    UNFINISHED = "error: codex ended without finishing its turn"

    def __init__(self, episode: Episode, clock=time.monotonic):
        self.episode = episode
        self.calls = 0
        self.turns = 0
        self.final = ""
        self.stop = self.UNFINISHED
        self.usage: Dict[str, int] = {}
        self.extra: Dict[str, Any] = {}
        self._clock = clock
        self._last: Optional[float] = None          # when the previous item event arrived
        self._started: set = set()                  # item ids seen starting
        self._assistant: Optional[dict] = None
        self._results: List[dict] = []

    def _flush(self) -> None:
        if self._assistant is not None:
            self.episode.log.append(self._assistant)
            if self._results:
                self.episode.log.append({"role": "user", "content": self._results})
        self._assistant, self._results = None, []

    def _open(self, kind: str) -> None:
        """Model output arrived: a new response if it has to be one."""
        now = self._clock()
        gap = now - self._last if self._last is not None else None
        new = (self._assistant is None
               or (kind in ("reasoning", "agent_message") and bool(self._results))
               or (gap is not None and gap >= TURN_GAP))
        if new:
            self._flush()
            self._assistant = {"role": "assistant", "content": []}
            self.turns += 1
        self._last = now

    def _say(self, block: dict) -> None:
        if self._assistant is None:
            self._open(block.get("type", ""))
        self._assistant["content"].append(block)

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            event = json.loads(line)
        except ValueError:
            return
        kind = event.get("type")
        if kind == "thread.started":
            self.extra["thread_id"] = event.get("thread_id")
        elif kind == "item.started":
            item = event.get("item") or {}
            if item.get("type") not in (None, "error"):
                self._started.add(item.get("id"))
                self._open(item.get("type"))
        elif kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") not in (None, "error") and item.get("id") not in self._started:
                self._open(item.get("type"))
            else:
                self._last = self._clock()
            self.item(item)
        elif kind == "turn.completed":
            for key, value in (event.get("usage") or {}).items():
                if isinstance(value, int):
                    self.usage[key] = self.usage.get(key, 0) + value
            self.stop = "answered"
        elif kind in ("turn.failed", "error"):
            message = str((event.get("error") or {}).get("message") if kind == "turn.failed"
                          else event.get("message"))
            if any(word in message.lower() for word in LIMIT_WORDS):
                self.stop = f"error: account limit: {message[:300]}"
            else:
                self.stop = f"error: {message[:300]}"

    def item(self, item: dict) -> None:
        kind = item.get("type")
        if kind == "reasoning" and item.get("text"):
            self._say({"type": "thinking", "thinking": item["text"]})
        elif kind == "agent_message":
            self._say({"type": "text", "text": item.get("text") or ""})
            if item.get("text"):
                self.final = item["text"]
        elif kind == "mcp_tool_call":
            self.calls += 1
            call_id = item.get("id") or f"call_{self.calls}"
            name = item.get("tool") or "?"
            if item.get("server") not in (None, SERVER_NAME):
                name = f"{item.get('server')}.{name}"
            self._say({"type": "tool_use", "id": call_id, "name": name,
                       "input": item.get("arguments") or {}})
            error, result = item.get("error"), item.get("result")
            content = (f"[tool error] {error.get('message') if isinstance(error, dict) else error}"
                       if error else result_text(result))
            is_error = bool(error) or (isinstance(result, dict)
                                       and bool(result.get("is_error") or result.get("isError")))
            self._results.append({"type": "tool_result", "tool_use_id": call_id, "content": content,
                                  "is_error": is_error})
        elif kind == "error":
            # a warning Codex reports as an item (fallback model metadata and the like)
            self.extra.setdefault("codex_warnings", []).append(item.get("message"))
        elif kind:
            # a built-in Codex kept (apply_patch, view_image ...): on the record, not hidden
            self.calls += kind in ("file_change", "command_execution", "web_search")
            self._say({"type": "codex_item", "item": item})

    def outcome(self) -> Outcome:
        self._flush()
        self.extra["tool_calls"] = self.calls
        return Outcome(stop=self.stop, final=self.final, turns=self.turns, usage=self.usage,
                       cost_usd=None, extra=self.extra)


def result_text(result: Any) -> str:
    """An MCP result as Codex reports it, as the text the model read."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = []
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, dict):
                parts.append(f"[{block.get('type')} content]")
        if parts:
            return "\n".join(parts)
        if result.get("structured_content") is not None:
            return json.dumps(result["structured_content"])
    return json.dumps(result)
