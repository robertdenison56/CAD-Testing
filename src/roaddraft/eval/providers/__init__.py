"""Model providers (eval plan section 4.4): one interface, ``complete(system,
transcript, tools) -> Turn``, and one class per vendor.  This package is the
only place in ``roaddraft.eval`` that talks to a model, and it does so over
the standard library's HTTP; tests never touch the network (``fake``).

- ``anthropic``: the Messages API, billed per token (``ANTHROPIC_API_KEY``).
- ``openai``: any OpenAI-compatible chat-completions endpoint -- LM Studio,
  Ollama, vLLM, Runpod.
- ``fake``: scripted turns, or the task's reference solution (``fake-oracle``).
- ``claude-code`` and ``codex``: a headless CLI on a subscription runs the whole
  episode with the harness as its MCP server (``providers/cli.py``,
  ``agents/cli.py``); asked for by name, never inferred from a model id.
"""
from __future__ import annotations

from typing import Optional

from roaddraft.eval.providers.anthropic import AnthropicProvider
from roaddraft.eval.providers.base import STOPS, USAGE_KEYS, Call, Provider, Turn, add_usage
from roaddraft.eval.providers.claude_code import ClaudeCodeProvider
from roaddraft.eval.providers.cli import CLIProvider
from roaddraft.eval.providers.codex import CodexProvider
from roaddraft.eval.providers.fake import FakeProvider
from roaddraft.eval.providers.openai_compat import OpenAICompatProvider

PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAICompatProvider, "fake": FakeProvider,
             "claude-code": ClaudeCodeProvider, "codex": CodexProvider}
#: the providers that are a headless CLI running the episode (``CLIProvider``)
CLI_PROVIDERS = ("claude-code", "codex")
#: options each provider takes from the command line
OPTIONS = {
    "anthropic": ("effort", "max_tokens", "strict"),
    "openai": ("effort", "base_url", "api_key_env", "extra_body", "max_tokens", "lms_context",
               "call_cap", "send_reasoning", "thinking"),
    "fake": ("effort",),
    "claude-code": ("effort", "claude_bin", "claude_args", "max_budget_usd"),
    "codex": ("effort", "codex_bin", "codex_args"),
}


def infer(model: str) -> str:
    """The provider a model id names by itself: ``claude-*`` is Anthropic's,
    ``fake*`` the fake, anything else an OpenAI-compatible endpoint."""
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("fake"):
        return "fake"
    return "openai"


def make(model: str, provider: Optional[str] = None, **options):
    """A provider for ``model`` (a ``Provider``, or a ``CLIProvider`` for the
    CLI routes); options a provider does not take are dropped, and None
    means the provider's default."""
    name = provider or infer(model)
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider {name!r}; providers: {', '.join(sorted(PROVIDERS))}")
    kept = {k: v for k, v in options.items() if k in OPTIONS[name] and v is not None}
    if name == "fake":
        return FakeProvider.oracle(model=model) if model.endswith("oracle") else FakeProvider(model=model, **kept)
    return PROVIDERS[name](model, **kept)


__all__ = ["PROVIDERS", "CLI_PROVIDERS", "OPTIONS", "infer", "make", "Provider", "CLIProvider",
           "Turn", "Call", "USAGE_KEYS", "STOPS", "add_usage", "AnthropicProvider",
           "OpenAICompatProvider", "FakeProvider", "ClaudeCodeProvider", "CodexProvider"]
