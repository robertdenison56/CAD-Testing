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

Codex has no turn cap, so the runner counts tool calls as the stream arrives
and stops the process past ``max_turns``; the budget is a wall clock, as for
claude-code. Tool results reach the model under Codex's own output limit, not
the runner's 30,000-character cap.

The binary: ``--codex-bin``, ``$CODEX_BIN``, the copy inside the ChatGPT app,
then ``codex`` on PATH. The app's copy comes first because it updates with
the app: on 2026-10-12 the npm install (0.145) could not read the models
cache the app's 0.162 wrote and the service refused ``gpt-6-luna`` from it.
A ``PYTHONPATH`` in the runner's environment is handed to the server (Codex
starts MCP servers with a short list of variables), so a run from a pinned
worktree serves that worktree's engine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """What the server needs from the runner's environment."""
    return {k: os.environ[k] for k in ("PYTHONPATH",) if os.environ.get(k)}


@register
class CodexBackend(Backend):
    name = "codex"
    needs_server = False

    def __init__(self, options, codex_bin: Optional[str] = None):
        super().__init__(options)
        self.codex = find_codex(codex_bin or options.extra.get("codex_bin"))

    def command(self, episode: Episode) -> List[str]:
        instructions = (episode.folder / "instructions.md").resolve()   # the CLI runs from project/
        instructions.write_text(INSTRUCTIONS)
        cmd = episode.setup.cmd
        settings: Dict[str, Any] = {
            "approval_policy": "never",
            "model_instructions_file": str(instructions),
            "project_doc_max_bytes": 0,
            "web_search": "disabled",
            **{key: False for key in QUIET},
            f"mcp_servers.{SERVER_NAME}.command": cmd[0],
            f"mcp_servers.{SERVER_NAME}.args": list(cmd[1:]),
            f"mcp_servers.{SERVER_NAME}.default_tools_approval_mode": "approve",
            f"mcp_servers.{SERVER_NAME}.startup_timeout_sec": 60,
            f"mcp_servers.{SERVER_NAME}.tool_timeout_sec": 600,
        }
        env = server_env()
        if env:
            settings[f"mcp_servers.{SERVER_NAME}.env"] = env
        if self.options.effort:
            settings["model_reasoning_effort"] = self.options.effort
        argv = [self.codex, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                "--skip-git-repo-check", "--sandbox", "read-only", "--model", self.options.model]
        for feature in DISABLED:
            argv += ["--disable", feature]
        for key, value in settings.items():
            argv += ["-c", f"{key}={toml(value)}"]
        argv += list(self.options.extra.get("codex_args") or [])
        argv.append(episode.task)
        return argv

    def run(self, episode: Episode) -> Outcome:
        argv = self.command(episode)
        episode.log.append({"role": "system", "content": INSTRUCTIONS})
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
            for line in proc.stdout:
                stream.feed(line)
                if stream.calls > self.options.max_turns:
                    stop("max_turns")
            proc.wait()
        finally:
            if timer:
                timer.cancel()
            reader.join(timeout=5)
        (episode.folder / "codex.log").write_text("".join(err_lines))
        outcome = stream.outcome()
        if stopped:
            outcome.stop = stopped["why"]
        elif proc.returncode != 0 and (outcome.stop == "answered" or outcome.stop == Stream.UNFINISHED):
            text = "".join(err_lines).strip()
            outcome.stop = f"error: codex exited {proc.returncode}: {text[-300:]}"
        return outcome


class Stream:
    """``codex exec --json``, event by event, into the transcript and the
    outcome. The transcript keeps the API backends' shape: an assistant
    message gathers reasoning, text and the tool calls up to their results;
    each result goes back as a ``tool_result`` block."""

    UNFINISHED = "error: codex ended without finishing its turn"

    def __init__(self, episode: Episode):
        self.episode = episode
        self.calls = 0
        self.turns = 0
        self.final = ""
        self.stop = self.UNFINISHED
        self.usage: Dict[str, int] = {}
        self.extra: Dict[str, Any] = {}
        self._assistant: Optional[dict] = None

    def _say(self, block: dict) -> None:
        if self._assistant is None:
            self._assistant = {"role": "assistant", "content": []}
            self.episode.log.append(self._assistant)
            self.turns += 1
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
        elif kind == "item.completed":
            self.item(event.get("item") or {})
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
            self.episode.log.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": content,
                 "is_error": is_error}]})
            self._assistant = None
        elif kind == "error":
            # a warning Codex reports as an item (fallback model metadata and the like)
            self.extra.setdefault("codex_warnings", []).append(item.get("message"))
        elif kind:
            # a built-in Codex kept (apply_patch, view_image ...): on the record, not hidden
            self.calls += kind in ("file_change", "command_execution", "web_search")
            self._say({"type": "codex_item", "item": item})
            self._assistant = None

    def outcome(self) -> Outcome:
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
