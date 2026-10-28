"""A headless coding CLI as the model's route (eval plan section 4.4): the
Track D counterpart of the Track P ``claude-code`` and ``codex`` backends, on
a subscription, no API key.

A ``CLIProvider`` is not a ``Provider``: it has no ``complete``, because the
CLI runs the whole episode itself -- its own model loop against the MCP
server it starts.  So it says how to start the CLI on an episode (``argv``:
the task, the eval's system prompt in place of the CLI's own, the harness's
bridge as the one MCP server, every built-in tool off, as the Track P
backends pare the CLIs back) and how to read the CLI's event stream
(``stream``: text, thinking, token usage, the final answer, an error of the
account or the CLI rather than the model).  ``agents.cli.CLIAgent`` drives it
through the episode loop, so the budgets, the whitelist, the dialect and the
trajectory are the harness's as for an API row.

The CLI's own harness stays between the model and the tools -- its context
handling, retries and parallel calls -- which is why a row from this route
carries ``provider: claude-code`` or ``codex`` beside the model, and why the
cost a priced model shows is notional: the subscription paid, the price
table says what the tokens would have cost.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from roaddraft.eval.providers.base import add_usage

#: the bridge the CLI starts as its one MCP server, run by file path
BRIDGE = Path(__file__).resolve().parents[1] / "bridge.py"
SERVER_NAME = "roaddraft"
#: words in a failed run that mean the account, not the model, stopped it
LIMIT_WORDS = ("usage limit", "rate limit", "too many requests", "quota")


class Stream:
    """What the CLI's event stream has said since the harness last took it:
    the token usage, the text and thinking (one turn's record), plus the
    final answer, a stop the CLI reported and any error, kept for the run.
    ``feed`` runs on the reader thread, ``take`` on the loop's."""

    def __init__(self):
        self._lock = threading.Lock()
        self._usage: Dict[str, int] = {}
        self._text: List[str] = []
        self._thinking: List[str] = []
        self.final = ""
        self.stop: Optional[str] = None
        self.error: Optional[str] = None
        self.extra: Dict[str, Any] = {}
        self.events = 0

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            event = json.loads(line)
        except ValueError:
            return
        with self._lock:
            self.events += 1
            self.event(event)

    def event(self, event: dict) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def say(self, text: str) -> None:
        if text:
            self._text.append(text)
            self.final = text

    def think(self, text: str) -> None:
        if text:
            self._thinking.append(text)

    def count(self, usage: Optional[dict]) -> None:
        add_usage(self._usage, {k: v for k, v in (usage or {}).items()
                                if isinstance(v, int) and not isinstance(v, bool)})

    def limit(self, message: str) -> str:
        return ("account limit: " if any(w in message.lower() for w in LIMIT_WORDS) else "") + message[:300]

    def take(self) -> Tuple[Dict[str, int], dict]:
        """The usage and the turn record gathered since the last take."""
        with self._lock:
            usage, self._usage = self._usage, {}
            record = {"text": "\n".join(self._text), "thinking": "\n".join(self._thinking)}
            if self.stop:
                record["stop"] = self.stop
            self._text, self._thinking = [], []
        return usage, record


@functools.lru_cache(maxsize=8)
def cli_version(binary: str) -> Optional[str]:
    """``BINARY --version``, once per binary; None when it does not run."""
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


class CLIProvider:
    """One headless CLI for one model."""
    name = "cli"

    def __init__(self, model: str, effort: Optional[str] = None, binary: str = "",
                 extra_args: Sequence[str] = ()):
        self.model = model
        self.effort = effort
        if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
            raise RuntimeError(f"{self.name}: no CLI to run at {binary!r}")
        self.binary = binary
        self.extra_args = list(extra_args or ())

    def reset(self, task) -> None:
        """Called once per episode with the task."""

    def ready(self) -> bool:
        """The binary runs: ``--version`` answers."""
        return cli_version(self.binary) is not None

    def version(self) -> Optional[str]:
        return cli_version(self.binary)

    def describe(self) -> dict:
        """The settings the trajectory header records beside model and provider."""
        return {"binary": self.binary, "version": self.version(), "extra_args": list(self.extra_args)}

    def argv(self, task: str, system: str, bridge: Sequence[str], work: Path,
             budgets) -> List[str]:  # pragma: no cover - abstract
        """The command that runs the CLI on ``task`` with ``system`` as its
        whole system prompt and ``bridge`` (a command) as its one MCP server;
        ``work`` is a folder of the episode's own for the files the command
        needs, ``budgets`` the episode's."""
        raise NotImplementedError

    def env(self) -> Dict[str, str]:
        return dict(os.environ)

    def stream(self) -> Stream:  # pragma: no cover - abstract
        raise NotImplementedError

    def exit_error(self, returncode: int, stderr: str) -> str:
        """What a CLI that ended without finishing its run says."""
        return f"{self.name} exited {returncode}: {stderr.strip()[-300:]}"


__all__ = ["BRIDGE", "SERVER_NAME", "LIMIT_WORDS", "Stream", "CLIProvider", "cli_version"]
