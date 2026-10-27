"""What every provider shares (eval plan section 4.4).

A provider turns one request -- the system prompt, the conversation so far,
the tool definitions -- into one ``Turn``: the model's text, its thinking
(when the vendor returns any), the tool calls it made with their parameters
parsed, the stop reason in the harness's words, and the token usage.  The
conversation is kept provider-neutral by the agent and translated by each
provider on every request, so the agent never sees a vendor's wire format:

    {"role": "user", "text": str}
    {"role": "assistant", "text": str, "calls": [{"id", "name", "params"}],
     "raw": <the vendor's own assistant message, sent back verbatim>}
    {"role": "results", "results": [{"id", "name", "content": str,
     "is_error": bool, "images": [(mime, base64)]}], "note": str | None}

``raw`` is what makes the history append-only: Anthropic requires thinking
blocks to go back exactly as they came, and a provider that keeps its own
message never rebuilds one the vendor has to recognise.

Usage keys are Anthropic's names whatever the vendor -- ``input_tokens``
(uncached), ``output_tokens``, ``cache_read_input_tokens``,
``cache_creation_input_tokens`` -- plus ``reasoning_tokens`` from vendors
that report them, already counted in ``output_tokens``.

Stop reasons: ``tool_use`` (calls to run), ``end`` (the model is done
talking), ``max_tokens`` (cut off at the output limit), ``refusal`` (the
model or the vendor's classifier declined; the episode ends).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens", "reasoning_tokens")
STOPS = ("tool_use", "end", "max_tokens", "refusal")


@dataclass
class Call:
    """One tool call as the model made it."""
    id: str
    name: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "params": self.params}


@dataclass
class Turn:
    """One model response, vendor-neutral."""
    text: str = ""
    calls: List[Call] = field(default_factory=list)
    stop: str = "end"
    usage: Dict[str, int] = field(default_factory=dict)
    thinking: str = ""
    raw: Any = None                  # the vendor's assistant message, for the next request
    stop_detail: Optional[str] = None  # the vendor's own stop reason or refusal category


class LimitReached(Exception):
    """The model cannot go on inside a limit the run sets: cut off at the
    output limit turn after turn (``output_limit``), a conversation past the
    context it is served at (``context``: the server refused the request, or
    the agent's own context budget, ``Budgets.context_tokens``, says it
    cannot fit), a turn past the provider's time limit (``turn_time``).  That is the model's outcome, like a budget, not
    the harness's failure: the episode ends with ``termination = "budget"``
    and ``budget_tripped`` = the limit.  Everything else a provider raises
    (HTTP errors, refused credentials) is an ``error``."""

    def __init__(self, limit: str, message: str = ""):
        super().__init__(message or limit)
        self.limit = limit


class Provider:
    """One vendor's API for one model."""
    name = "provider"

    def __init__(self, model: str, effort: Optional[str] = None):
        self.model = model
        self.effort = effort

    def reset(self, task) -> None:
        """Called once per episode with the task (the fake oracle reads it)."""

    def ready(self) -> bool:
        """The endpoint answers, so an episode may start; a local server's
        provider reloads and probes its engine here (the LM Studio guard).
        False stops the run before the episode is written, so a dead engine
        burns no episodes (the 9B's d1-real run, 2026-10-24: 61 of 99)."""
        return True

    def complete(self, system: str, transcript: List[dict], tools: List[dict]) -> Turn:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:
        """The settings the trajectory header records beside model and provider."""
        return {}


def add_usage(total: Dict[str, int], usage: Optional[Dict[str, int]]) -> Dict[str, int]:
    for k, v in (usage or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total[k] = total.get(k, 0) + int(v)
    return total


__all__ = ["USAGE_KEYS", "STOPS", "Call", "Turn", "LimitReached", "Provider", "add_usage"]
