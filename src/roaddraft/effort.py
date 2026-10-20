"""The effort a run ran at, and what a model does when the run sets none.

A run sets an effort level with ``--effort`` where its backend sends one, or
puts one in the request body (``reasoning_effort``, or a chat template's
``enable_thinking`` switch). When it sets none, the model runs at its default,
which no run records, so the defaults are kept here, read from where each
setting lives (checked 2026-10-18):

- the open-weight models on vLLM: each model's ``chat_template.jinja`` on
  Hugging Face, which vLLM renders the prompt with. gpt-oss is the exception:
  vLLM v0.31.0 builds its prompt with ``openai_harmony``, and with no
  ``reasoning_effort`` in the request (vLLM's default is None) harmony's
  system message says ``Reasoning: medium`` (``SystemContent``'s default; the
  chat template defaults to medium too);
- Gemma 4: the template the Runpod endpoints serve, vLLM's
  ``examples/tool_chat_template_gemma4.jinja`` (``enable_thinking |
  default(false)``);
- Codex: the model catalog Codex 0.163 fetched (``~/.codex/models_cache.json``,
  ``default_reasoning_level``). The codex backend passes
  ``--ignore-user-config``, so the catalog default is what applies.

Claude Code and the Messages API are not here: no row on the board leaves
their effort unset.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

_THINKS = ("thinking on", "its chat template thinks unless the request sets `enable_thinking: false`, "
           "and has no effort levels")
_GEMMA = ("thinking off", "vLLM's Gemma 4 chat template leaves thinking off unless the request sets "
          "`enable_thinking: true`")
_HARMONY = ("medium", "vLLM sends no `reasoning_effort`, so the harmony system message reads `Reasoning: medium`")


def _codex(level: str, model: str) -> Tuple[str, str]:
    return level, f"Codex's model catalog default for `{model}`"


#: a model's effort when the run sets none: (level, where that comes from)
DEFAULTS: Dict[str, Tuple[str, str]] = {
    "Qwen/Qwen3.5-4B": _THINKS, "Qwen/Qwen3.5-9B": _THINKS, "Qwen/Qwen3.6-35B-A3B": _THINKS,
    "zai-org/GLM-4.7-Flash": _THINKS,
    "Qwen/Qwen3.8-27B": ("xhigh", "its chat template thinks unless the request sets `enable_thinking: false`, "
                         "at `reasoning_effort` xhigh unless the request asks for medium or low"),
    "google/gemma-4-12B-it": _GEMMA, "google/gemma-4-26B-A4B-it": _GEMMA, "google/gemma-4-31B-it": _GEMMA,
    "openai/gpt-oss-20b": _HARMONY, "openai/gpt-oss-120b": _HARMONY,
    **{m: _codex(level, m) for m, level in (("gpt-6-luna", "medium"), ("gpt-6-sol", "medium"),
                                            ("gpt-6-astra", "low"), ("gpt-6.1-sol", "low"))},
}


def describe(model: str, level: Optional[str], sent_as: Optional[str],
             body: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """The effort a run ran at, as a cell and in words.

    ``level`` is the effort the run asked for, ``sent_as`` how its backend
    sends one (None for a backend that sends none), ``body`` the extra
    request body. The cell is the level set, else what the body set, else
    the model's default marked ``(default)``, or plain ``default`` where the
    default is not known here."""
    body = body or {}
    known = DEFAULTS.get(model)
    unset = f" Left unset it would be {known[0]}: {known[1]}." if known else ""
    if level and sent_as:
        return level, f"set by the run, sent as {sent_as}." + unset
    if body.get("reasoning_effort"):
        return str(body["reasoning_effort"]), f"`reasoning_effort: {body['reasoning_effort']}` in the request body." + unset
    thinking = (body.get("chat_template_kwargs") or {}).get("enable_thinking")
    if thinking is not None:
        return (f"thinking {'on' if thinking else 'off'}",
                f"the request body set `enable_thinking: {'true' if thinking else 'false'}`." + unset)
    recorded = f"`{level}` was recorded, but this backend sends no effort. " if level else ""
    if known:
        return f"{known[0]} (default)", f"{recorded}Nothing set, so the model's default applied: {known[1]}."
    if sent_as:
        return "default", f"{recorded}Nothing set, so the provider's default level applied (not looked up here)."
    return "default", f"{recorded}Nothing set, so the model's own default applied (not looked up here)."


__all__ = ["DEFAULTS", "describe"]
