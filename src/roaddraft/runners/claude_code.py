"""Claude Code in headless mode as a backend: a subscription, no API key.

``claude -p`` takes the task, a model, an MCP config naming the probe's
server, and exits with the final answer. The CLI starts ``roaddraft-mcp``
itself, so the server's trace and autosave work exactly as for the other
backends; the model calls the tools natively as ``mcp__roaddraft__<tool>``.

The harness is pared back to be as close to the bare API as the CLI allows:
``--system-prompt`` replaces Claude Code's own system prompt with the server's
instructions (the same system message the API backend sends), ``--tools ""``
removes every built-in tool so the server is the whole world, ``--restricted``
ignores the user's settings and hooks, ``--strict-mcp-config`` ignores every
other MCP server, and the tools are pre-allowed so nothing prompts. What
remains of the harness -- its tool-calling loop, its own retry and context
handling -- is why rows from this backend carry ``runner: claude-code`` on the
leaderboard, and why ``--append-system-prompt`` is not used: the words the
model gets are the server's and the task's, nothing else.

``--output-format stream-json`` gives every message as it happens; the
transcript is kept in the same shape as the API backend's (assistant content
blocks, ``tool_result`` blocks). The CLI reports the tokens and its own cost
estimate; on a subscription that estimate is notional.

The CLI must be signed in (``claude login``, or ``claude setup-token`` for a
long-lived token); the copy bundled with the desktop app is not, so point
``--claude-bin`` at a standalone install. A "Not logged in" reply ends the
probe with that error, in ``run.json``, and the run goes on to the next.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from roaddraft.mcp import config as mcpconfig
from roaddraft.mcp import profiles
from roaddraft.mcp.server import INSTRUCTIONS
from roaddraft.runners.core import Backend, Episode, Outcome, estimate_cost, register, text_of

SERVER_NAME = "roaddraft"
BUNDLED = os.path.expanduser("~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude")


def find_claude(explicit: Optional[str] = None) -> str:
    """The CLI to run: ``--claude-bin``, ``$CLAUDE_BIN``, ``claude`` on PATH,
    or the newest copy bundled with the desktop app (which may not be signed in)."""
    for candidate in (explicit, os.environ.get("CLAUDE_BIN")):
        if candidate:
            return candidate
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    bundled = sorted(glob.glob(BUNDLED), key=os.path.getmtime)
    if bundled:
        return bundled[-1]
    raise RuntimeError("no claude CLI found: install Claude Code (npm i -g @anthropic-ai/claude-code), "
                       "sign in, and pass --claude-bin or put it on PATH")


def mcp_config(cmd: List[str]) -> dict:
    """The MCP config the CLI starts the probe's server from."""
    return {"mcpServers": {SERVER_NAME: mcpconfig.entry(cmd[:1], cmd[1:], "claude-code")}}


@register
class ClaudeCodeBackend(Backend):
    name = "claude-code"
    needs_server = False

    def __init__(self, options, claude_bin: Optional[str] = None):
        super().__init__(options)
        self.claude = find_claude(claude_bin or options.extra.get("claude_bin"))

    def command(self, episode: Episode) -> List[str]:
        config = (episode.folder / "mcp.json").resolve()   # the CLI runs from project/
        config.write_text(json.dumps(mcp_config(episode.setup.cmd), indent=2))
        argv = [self.claude, "-p", episode.task,
                "--model", self.options.model,
                "--max-turns", str(self.options.max_turns),
                "--mcp-config", str(config), "--strict-mcp-config",
                "--tools", "",
                "--allowedTools", f"mcp__{SERVER_NAME}__*",
                "--restricted",
                "--system-prompt", profiles.instructions(self.options.profile, INSTRUCTIONS),
                "--output-format", "stream-json", "--verbose",
                "--no-session-persistence"]
        if self.options.effort:
            argv += ["--effort", self.options.effort]
        budget_usd = self.options.extra.get("max_budget_usd")
        if budget_usd:
            argv += ["--max-budget-usd", str(budget_usd)]
        argv += list(self.options.extra.get("claude_args") or [])
        return argv

    def run(self, episode: Episode) -> Outcome:
        argv = self.command(episode)
        episode.log.append({"role": "system",
                            "content": profiles.instructions(self.options.profile, INSTRUCTIONS)})
        episode.log.append({"role": "user", "content": episode.task})
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)       # a nested session refuses to start otherwise
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                cwd=str(episode.folder / "project"), env=env)
        timed_out = False
        try:
            out, err = proc.communicate(timeout=self.options.budget or None)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            timed_out = True
        (episode.folder / "claude.log").write_text(err or "")
        outcome = parse_stream(out, episode, self.options.model)
        if timed_out:
            outcome.stop = "budget"
        elif proc.returncode != 0 and outcome.stop == "max_turns" and not outcome.turns:
            text = (err or out or "").strip()
            if "not logged in" in text.lower() or "/login" in text:
                outcome.stop = "error: claude is not signed in (claude login, or claude setup-token)"
            else:
                outcome.stop = f"error: claude exited {proc.returncode}: {text[-300:]}"
        return outcome


def parse_stream(out: str, episode: Episode, model: str) -> Outcome:
    """The CLI's stream-json, line by line, into the transcript and the outcome."""
    usage: Dict[str, int] = {}
    turns, final, stop, extra = 0, "", "max_turns", {}
    for line in (out or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            servers = {s.get("name"): s.get("status") for s in event.get("mcp_servers") or []}
            extra["mcp_servers"] = servers
            extra["session_id"] = event.get("session_id")
            if servers.get(SERVER_NAME) not in (None, "connected"):
                stop = f"error: the {SERVER_NAME} server did not connect ({servers.get(SERVER_NAME)})"
        elif kind == "assistant":
            message = event.get("message") or {}
            content = message.get("content") or []
            turns += 1
            entry = {"role": "assistant", "content": content}
            if message.get("stop_reason"):
                entry["stop_reason"] = message["stop_reason"]
            episode.log.append(entry)
            if text_of(content):
                final = text_of(content)
        elif kind == "user":
            message = event.get("message") or {}
            episode.log.append({"role": "user", "content": message.get("content") or []})
        elif kind == "result":
            subtype = event.get("subtype") or ""
            usage = {k: v for k, v in (event.get("usage") or {}).items() if isinstance(v, int)}
            if event.get("result"):
                final = event["result"]
            stop = {"success": "answered", "error_max_turns": "max_turns",
                    "error_max_budget_usd": "budget_usd"}.get(subtype, f"error: {subtype}")
            if event.get("is_error") and subtype == "success":
                stop = f"error: {str(event.get('result'))[:200]}"
            extra["num_turns"] = event.get("num_turns")
            extra["claude_cost_usd"] = event.get("total_cost_usd")
            extra["duration_ms"] = event.get("duration_ms")
    cost = estimate_cost(model, usage) if usage else None
    return Outcome(stop=stop, final=final, turns=turns, usage=usage, cost_usd=cost, extra=extra)
