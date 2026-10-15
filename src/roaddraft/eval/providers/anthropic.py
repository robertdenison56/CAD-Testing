"""The Anthropic Messages API as a provider (eval plan section 4.4).

Raw HTTP on the standard library through the Track P runner's client
(``roaddraft.runners.anthropic_api``: credentials, retries on the statuses
the SDK retries): the current ``anthropic`` SDK needs Python 3.10 and the
engine runs on 3.9.

The request, per the plan:

- ``tool_choice`` is left at ``auto`` (never sent): forced tool use is a 400
  on Fable 5.1, Opus 5.5 and Sonnet 5.5, and forcing would bias the
  benchmark anyway.
- ``strict`` is off by default, against the plan's "``strict: true`` is
  free": nine tools take a free-form object by design (``fill_title_block``
  fields, ``modify_entity`` changes, ``find_entities`` anchor ...), which
  strict mode would close to nothing, and the schemas use the numeric and
  length bounds strict grammars are not promised to take.  Off, an invalid
  call is a teaching error, as for every other vendor, so invalid-call rates
  compare.  ``--strict`` marks only the tools whose schemas are closed all
  the way down.
- Adaptive thinking on the models that take it, with ``display:
  "summarized"`` where the default is to omit the text, so the trajectory
  keeps a readable summary of the reasoning (billing is the same either
  way).  Haiku 4.5 and older take no adaptive thinking and run without.
- ``effort`` is a run dimension (default ``high``; Opus 5.5 and Haiku 5.5
  default to ``medium`` when it is left out, so it is always sent), under
  ``output_config``, except to the models that reject it.
- Prompt caching: a top-level ``cache_control`` caches the last cacheable
  block, so the tools, the system prompt and the history so far are read
  from cache on every turn after the first; the history is append-only.
- No server-side ``fallbacks``: a refusal ends the episode with
  ``termination = "refusal"``, since another model answering would
  contaminate the row.  No sampling parameters: they are not a control on
  these models.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from roaddraft.eval.providers.base import Call, Provider, Turn

MAX_TOKENS = 16000
#: models that take ``thinking: {type: adaptive}``
ADAPTIVE = ("claude-fable-", "claude-mythos-", "claude-opus-5", "claude-opus-4-8",
            "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6",
            "claude-haiku-5")
#: adaptive models whose thinking text is omitted unless ``display`` asks for it
DISPLAY = ("claude-fable-", "claude-mythos-", "claude-opus-5", "claude-opus-4-8",
           "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-5")
#: models that reject ``output_config.effort``
NO_EFFORT = ("claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-1", "claude-opus-4-0")
STOP_MAP = {"tool_use": "tool_use", "end_turn": "end", "stop_sequence": "end",
            "pause_turn": "end", "max_tokens": "max_tokens", "refusal": "refusal"}
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens",
         "cache_creation_input_tokens")


def _starts(model: str, prefixes) -> bool:
    return any(model.startswith(p) for p in prefixes)


def closed(schema) -> bool:
    """Every object in ``schema`` has ``additionalProperties: false``."""
    if isinstance(schema, dict):
        if (schema.get("type") == "object" or "properties" in schema) \
                and schema.get("additionalProperties") is not False:
            return False
        return all(closed(v) for v in schema.values())
    if isinstance(schema, list):
        return all(closed(v) for v in schema)
    return True


def api_tools(tools: List[dict], strict: bool = False) -> List[dict]:
    """The episode's tool definitions in the Messages API's shape; with
    ``strict``, the closed ones carry ``strict: true``."""
    out = []
    for t in tools:
        d = {"name": t["name"], "description": t.get("description", ""),
             "input_schema": t["input_schema"]}
        if strict and closed(t["input_schema"]):
            d["strict"] = True
        out.append(d)
    return out


def _result_block(r: dict) -> dict:
    content: object = r["content"]
    if r.get("images"):
        content = [{"type": "text", "text": r["content"]}] + [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}
            for mime, data in r["images"]]
    block = {"type": "tool_result", "tool_use_id": r["id"], "content": content}
    if r.get("is_error"):
        block["is_error"] = True
    return block


def api_messages(transcript: List[dict]) -> List[dict]:
    """The neutral conversation as Messages API messages."""
    out = []
    for m in transcript:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            out.append({"role": "assistant", "content": m["raw"]})
        elif role == "results":
            blocks = [_result_block(r) for r in m["results"]]
            if m.get("note"):
                blocks.append({"type": "text", "text": m["note"]})
            out.append({"role": "user", "content": blocks})
        else:
            raise ValueError(f"unknown transcript role {role!r}")
    return out


def parse_reply(reply: dict) -> Turn:
    """A Messages API response as a ``Turn``."""
    content = reply.get("content") or []
    texts, thoughts, calls = [], [], []
    for block in content:
        kind = block.get("type")
        if kind == "text":
            texts.append(block.get("text", ""))
        elif kind == "thinking":
            thoughts.append(block.get("thinking", ""))
        elif kind == "tool_use":
            params = block.get("input")
            calls.append(Call(block["id"], block["name"], params if isinstance(params, dict) else {}))
    reason = reply.get("stop_reason") or "end_turn"
    stop = STOP_MAP.get(reason, "end")
    detail = reason
    if reason == "refusal":
        details = reply.get("stop_details") or {}
        detail = ": ".join(x for x in ("refusal", details.get("category") or "",
                                       details.get("explanation") or "") if x)
    usage = {k: int((reply.get("usage") or {}).get(k) or 0) for k in USAGE}
    return Turn(text="\n".join(t for t in texts if t).strip(), calls=calls, stop=stop,
                usage=usage, thinking="\n".join(t for t in thoughts if t).strip(),
                raw=content, stop_detail=detail)


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, effort: Optional[str] = "high", max_tokens: int = MAX_TOKENS,
                 strict: bool = False, post: Optional[Callable[[dict], dict]] = None):
        super().__init__(model, effort)
        self.max_tokens = int(max_tokens)
        self.strict = strict
        if post is None:
            from roaddraft.runners.anthropic_api import credentials, post_messages
            try:
                headers = credentials()
            except RuntimeError:
                raise RuntimeError("no Anthropic credentials: set ANTHROPIC_API_KEY (a Console "
                                   "key, billed per token) or ANTHROPIC_AUTH_TOKEN; a Claude "
                                   "subscription does not cover the API") from None
            post = lambda body: post_messages(body, headers)  # noqa: E731
        self.post = post

    def thinking(self) -> Optional[dict]:
        if not _starts(self.model, ADAPTIVE):
            return None
        config = {"type": "adaptive"}
        if _starts(self.model, DISPLAY):
            config["display"] = "summarized"
        return config

    def request(self, system: str, transcript: List[dict], tools: List[dict]) -> dict:
        body: Dict[str, object] = {"model": self.model, "max_tokens": self.max_tokens,
                                   "system": system, "tools": api_tools(tools, self.strict),
                                   "messages": api_messages(transcript),
                                   "cache_control": {"type": "ephemeral"}}
        thinking = self.thinking()
        if thinking:
            body["thinking"] = thinking
        if self.effort and not _starts(self.model, NO_EFFORT):
            body["output_config"] = {"effort": self.effort}
        return body

    def complete(self, system: str, transcript: List[dict], tools: List[dict]) -> Turn:
        return parse_reply(self.post(self.request(system, transcript, tools)))

    def describe(self) -> dict:
        return {"max_tokens": self.max_tokens, "strict": self.strict,
                "thinking": self.thinking()}


__all__ = ["AnthropicProvider", "api_tools", "api_messages", "parse_reply", "MAX_TOKENS"]
