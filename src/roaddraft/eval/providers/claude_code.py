"""Claude Code in headless mode as the model's route: ``claude -p`` on a
subscription, pared back exactly as the Track P backend pares it
(``runners/claude_code.py``: ``--system-prompt`` replaces its own prompt,
``--tools ""`` removes every built-in, ``--restricted`` and
``--strict-mcp-config`` ignore the user's settings and servers, the bridge's
tools are pre-allowed), with the eval's system prompt in place of the
server's instructions and the harness's bridge as the one server.  The
model calls the tools as ``mcp__roaddraft__<name>``; the bridge sees the
plain names.  ``--max-turns`` is set past the step budget, a backstop the
harness's own budgets come before.

The stream is ``--output-format stream-json``: an ``assistant`` event per
model message with its text, thinking and token usage; a ``result`` event
at the end with the final answer, the CLI's own cost estimate (notional on
a subscription) and the outcome.  A result the CLI reports as an error --
apart from its own turn and budget caps, which are the model stopping -- is
the run's error; an account limit is named as one.  The CLI must be signed
in (``claude login``, or ``claude setup-token``); the copy bundled with the
desktop app is not, so ``--claude-bin`` or ``$CLAUDE_BIN`` names a
standalone install (``claude`` on PATH comes first).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from roaddraft.eval.providers.cli import SERVER_NAME, CLIProvider, Stream
from roaddraft.mcp import config as mcpconfig
from roaddraft.runners.claude_code import claude_argv, claude_env, find_claude, sign_in_error

#: result subtypes that are the CLI stopping, not failing
STOPPED = {"success": "end", "error_max_turns": "max_turns", "error_max_budget_usd": "budget_usd"}
#: turns the CLI may take past the step budget before its own cap (a backstop)
TURNS_PAST_STEPS = 2


class ClaudeStream(Stream):
    def __init__(self):
        super().__init__()
        self._counted = False

    def event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            servers = {s.get("name"): s.get("status") for s in event.get("mcp_servers") or []}
            self.extra["mcp_servers"] = servers
            self.extra["session_id"] = event.get("session_id")
            if servers.get(SERVER_NAME) not in (None, "connected"):
                self.error = f"the {SERVER_NAME} bridge did not connect ({servers.get(SERVER_NAME)})"
        elif kind == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if block.get("type") == "text":
                    self.say(block.get("text") or "")
                elif block.get("type") == "thinking":
                    self.think(block.get("thinking") or "")
            usage = message.get("usage") or {}
            if usage:
                self.count(usage)
                self._counted = True
            if message.get("stop_reason"):
                self.stop = message["stop_reason"]
        elif kind == "result":
            subtype = event.get("subtype") or ""
            if event.get("result"):
                self.final = str(event["result"])
            if not self._counted:          # a stream without per-message usage: the total
                self.count(event.get("usage") or {})
            self.extra.update({"num_turns": event.get("num_turns"),
                               "cli_cost_usd": event.get("total_cost_usd"),
                               "duration_ms": event.get("duration_ms")})
            if subtype in STOPPED and not (event.get("is_error") and subtype == "success"):
                self.stop = STOPPED[subtype]
            else:
                self.error = self.limit(str(event.get("result") or subtype or "error"))


class ClaudeCodeProvider(CLIProvider):
    name = "claude-code"

    def __init__(self, model: str, effort: Optional[str] = None, claude_bin: Optional[str] = None,
                 claude_args: Optional[Sequence[str]] = None, max_budget_usd: Optional[float] = None):
        super().__init__(model, effort, binary=find_claude(claude_bin), extra_args=claude_args or ())
        self.max_budget_usd = max_budget_usd

    def argv(self, task: str, system: str, bridge: Sequence[str], work: Path, budgets) -> List[str]:
        config = (Path(work) / "mcp.json").resolve()
        config.write_text(json.dumps({"mcpServers": {
            SERVER_NAME: mcpconfig.entry(list(bridge[:1]), list(bridge[1:]), "claude-code")}}, indent=2))
        return claude_argv(self.binary, task, self.model, int(budgets.steps) + TURNS_PAST_STEPS, config,
                           system, effort=self.effort, max_budget_usd=self.max_budget_usd,
                           extra=self.extra_args)

    def env(self) -> Dict[str, str]:
        return claude_env()

    def stream(self) -> Stream:
        return ClaudeStream()

    def exit_error(self, returncode: int, stderr: str) -> str:
        if sign_in_error(stderr):
            return "claude is not signed in (claude login, or claude setup-token)"
        return super().exit_error(returncode, stderr)

    def describe(self) -> dict:
        return {**super().describe(), "max_budget_usd": self.max_budget_usd}


__all__ = ["STOPPED", "TURNS_PAST_STEPS", "ClaudeStream", "ClaudeCodeProvider"]
