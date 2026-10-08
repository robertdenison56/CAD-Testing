"""The Anthropic Messages API as a backend: the bare model, billed per token.

Raw HTTP on the standard library, like everything else in this project: the
current ``anthropic`` SDK needs Python 3.10 and this runs on 3.9 (the MCP
server speaks its protocol on the stdlib for the same reason). The request is
the documented shape -- ``system``, ``tools`` with each MCP tool's JSON Schema
as ``input_schema``, the conversation, and a top-level ``cache_control`` so
the 22k-token tool list is read from cache on every turn after the first.
Thinking is left at each model's default (always on for Fable, off for Haiku
4.5) and the assistant's content comes back verbatim, thinking blocks
included, which is what the API requires on the next turn.

Credentials: ``ANTHROPIC_API_KEY``, or ``ANTHROPIC_AUTH_TOKEN`` as a bearer
token. Neither set is an error that says so, before any probe is set up.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

from roaddraft.runners.core import (Backend, Episode, Outcome, ToolResult, estimate_cost,
                                    register, text_of)

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
MAX_TOKENS = 16000
RETRY_STATUSES = (408, 409, 429, 500, 502, 503, 529)
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def credentials(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The auth headers, from the environment."""
    env = os.environ if env is None else env
    key = env.get("ANTHROPIC_API_KEY")
    if key:
        return {"x-api-key": key}
    token = env.get("ANTHROPIC_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"}
    raise RuntimeError("no Anthropic credentials: set ANTHROPIC_API_KEY (a Console key, "
                       "billed per token) or ANTHROPIC_AUTH_TOKEN. A Claude subscription "
                       "does not cover the API; use --backend claude-code for that.")


def post_messages(body: dict, headers: Dict[str, str], timeout: float = 900.0,
                  attempts: int = 5, sleep: Callable[[float], None] = time.sleep) -> dict:
    """``POST /v1/messages`` with retries on the statuses the SDK retries."""
    data = json.dumps(body).encode()
    last: Optional[Exception] = None
    for attempt in range(attempts):
        req = urllib.request.Request(URL, data, {"Content-Type": "application/json",
                                                 "anthropic-version": VERSION, **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            text = ex.read().decode(errors="replace")
            if ex.code in RETRY_STATUSES and attempt < attempts - 1:
                retry_after = ex.headers.get("retry-after") if ex.headers else None
                try:
                    wait = float(retry_after) if retry_after else 10.0 * (attempt + 1)
                except ValueError:
                    wait = 10.0 * (attempt + 1)
                sleep(min(wait, 120.0))
                last = RuntimeError(f"anthropic HTTP {ex.code}: {text[:300]}")
                continue
            if ex.code == 401:
                raise RuntimeError(f"anthropic HTTP 401: the credentials were refused ({text[:200]})")
            raise RuntimeError(f"anthropic HTTP {ex.code}: {text[:500]}")
        except (urllib.error.URLError, TimeoutError) as ex:
            last = ex
            if attempt < attempts - 1:
                sleep(10.0 * (attempt + 1))
                continue
            raise
    raise last or RuntimeError("anthropic: gave up")


def tool_definitions(tools: List[dict]) -> List[dict]:
    """MCP tool definitions in the Messages API's shape."""
    return [{"name": t["name"], "description": t.get("description", ""),
             "input_schema": t["inputSchema"]} for t in tools]


def tool_result_block(tool_use_id: str, result: ToolResult, vision: bool) -> dict:
    """One ``tool_result``; a render goes in as an image when the run is vision."""
    content: object = result.rendered(vision)
    if vision and result.images:
        content = [{"type": "text", "text": result.rendered(vision)}]
        for mime, data in result.images:
            content.append({"type": "image", "source": {"type": "base64",
                                                        "media_type": mime, "data": data}})
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if result.is_error:
        block["is_error"] = True
    return block


@register
class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self, options, post: Optional[Callable[[dict], dict]] = None):
        super().__init__(options)
        self.post = post or self._post
        if post is None:
            self.headers = credentials()

    def _post(self, body: dict) -> dict:
        return post_messages(body, self.headers)

    def request(self, system: str, tools: List[dict], messages: List[dict]) -> dict:
        body = {"model": self.options.model, "max_tokens": MAX_TOKENS, "system": system,
                "tools": tools, "messages": messages,
                "cache_control": {"type": "ephemeral"}}
        if self.options.effort:
            body["output_config"] = {"effort": self.options.effort}
        return body

    def run(self, episode: Episode) -> Outcome:
        server = episode.server
        assert server is not None
        tools = tool_definitions(server.tools)
        messages: List[dict] = [{"role": "user", "content": episode.task}]
        episode.log.append({"role": "system", "content": server.instructions})
        episode.log.append(messages[0])
        usage: Dict[str, int] = {k: 0 for k in USAGE_KEYS}
        turns, final, stop = 0, "", "max_turns"
        for _turn in range(self.options.max_turns):
            if episode.over_budget():
                stop = "budget"
                break
            t0 = time.time()
            reply = self.post(self.request(server.instructions, tools, messages))
            for key in USAGE_KEYS:
                usage[key] += (reply.get("usage") or {}).get(key) or 0
            content = reply.get("content") or []
            messages.append({"role": "assistant", "content": content})
            turns += 1
            episode.log.append({"role": "assistant", "content": content,
                                "stop_reason": reply.get("stop_reason"),
                                "seconds": round(time.time() - t0, 1)})
            reason = reply.get("stop_reason")
            if reason == "tool_use":
                results = []
                for block in content:
                    if block.get("type") != "tool_use":
                        continue
                    result = server.call(block["name"], block.get("input") or {})
                    results.append(tool_result_block(block["id"], result, self.options.vision))
                user = {"role": "user", "content": results}
                messages.append(user)
                episode.log.append(user)
                continue
            if reason == "pause_turn":   # a server-side pause: send the turn back as it is
                continue
            final = text_of(content)
            stop = {"end_turn": "answered", "stop_sequence": "answered",
                    "max_tokens": "length", "refusal": "refusal"}.get(reason, f"stop: {reason}")
            if reason == "refusal":
                episode.log[-1]["stop_details"] = reply.get("stop_details")
            break
        return Outcome(stop=stop, final=final, turns=turns, usage=usage,
                       cost_usd=estimate_cost(self.options.model, usage))
