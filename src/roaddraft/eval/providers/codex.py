"""Codex in headless mode as the model's route: ``codex exec --json`` on a
ChatGPT subscription, pared back exactly as the Track P backend pares it
(``runners/codex_cli.py``: the user's config and rules ignored, the built-in
features off, a read-only sandbox with no approvals, the bridge's tools
pre-approved), with the eval's system prompt as ``model_instructions_file``
in place of Codex's own and the harness's bridge as the one MCP server.
Codex has no turn cap; the harness's budgets end the episode.

The stream is Codex's ``--json`` items: ``reasoning`` and ``agent_message``
items are the turn's thinking and text, ``turn.completed`` carries the whole
run's token usage (so it lands in the episode's last turn: the agent waits
for the CLI to finish before it hands the loop the submit call), and
``turn.failed`` or ``error`` is the run's error, an account limit named as
one.  Codex's ``input_tokens`` holds the cached tokens too (the Responses
API's count), so the harness's uncached ``input_tokens`` is the difference
and ``cached_input_tokens`` is ``cache_read_input_tokens``;
``reasoning_output_tokens``, already in ``output_tokens``, is kept as
``reasoning_tokens``.  No price row names a Codex model, so a Codex row has
no cost.  The binary: ``--codex-bin``, ``$CODEX_BIN``, the ChatGPT app's
copy, then ``codex`` on PATH.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from roaddraft.eval.providers.cli import CLIProvider, Stream
from roaddraft.runners.codex_cli import codex_argv, find_codex


def usage(raw: dict) -> Dict[str, int]:
    """Codex's turn usage in the harness's keys."""
    total = int(raw.get("input_tokens") or 0)
    cached = int(raw.get("cached_input_tokens") or 0)
    out = {"input_tokens": max(0, total - cached), "cache_read_input_tokens": cached,
           "output_tokens": int(raw.get("output_tokens") or 0)}
    if raw.get("reasoning_output_tokens") is not None:
        out["reasoning_tokens"] = int(raw["reasoning_output_tokens"])
    return out


class CodexStream(Stream):
    def event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "thread.started":
            self.extra["thread_id"] = event.get("thread_id")
        elif kind == "item.completed":
            item = event.get("item") or {}
            t = item.get("type")
            if t == "reasoning":
                self.think(item.get("text") or "")
            elif t == "agent_message":
                self.say(item.get("text") or "")
            elif t == "error":
                self.extra.setdefault("codex_warnings", []).append(item.get("message"))
            elif t in ("file_change", "command_execution", "web_search"):
                # a built-in Codex kept regardless: on the record, never hidden
                self.extra.setdefault("builtins_used", []).append(t)
        elif kind == "turn.completed":
            self.count(usage(event.get("usage") or {}))
            self.stop = "end"
        elif kind in ("turn.failed", "error"):
            message = str((event.get("error") or {}).get("message") if kind == "turn.failed"
                          else event.get("message"))
            self.error = self.limit(message)


class CodexProvider(CLIProvider):
    name = "codex"

    def __init__(self, model: str, effort: Optional[str] = None, codex_bin: Optional[str] = None,
                 codex_args: Optional[Sequence[str]] = None):
        super().__init__(model, effort, binary=find_codex(codex_bin), extra_args=codex_args or ())

    def argv(self, task: str, system: str, bridge: Sequence[str], work: Path, budgets) -> List[str]:
        instructions = (Path(work) / "instructions.md").resolve()
        instructions.write_text(system)
        return codex_argv(self.binary, task, self.model, instructions, list(bridge),
                          effort=self.effort, extra=self.extra_args)

    def stream(self) -> Stream:
        return CodexStream()


__all__ = ["usage", "CodexStream", "CodexProvider"]
