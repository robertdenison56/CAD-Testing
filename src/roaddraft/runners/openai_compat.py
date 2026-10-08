"""Any OpenAI-compatible chat-completions endpoint as a backend: LM Studio,
Ollama, vLLM, and a fine-tuned checkpoint served by any of them.

The LM Studio rig's runner (benchmarks/probe_runs/2026-10-04-lmstudio-tier2),
generalised: the MCP tools go in as function tools, the server's instructions
as the system message, tool results back as ``role: tool`` messages. A
model's thinking (``reasoning_content``) is kept in the transcript and not
sent back: the tool schema already costs ~22k tokens a request and a local
model's context is the scarce resource. Runs are text-only -- a render comes
back as a note with the file path -- since tool messages carry strings.

LM Studio's guard is kept, switched on by ``--lms-context N``: a 400 that
names a context overflow or a dead engine reloads the model through ``lms``
at that context and retries the request, and a refused connection waits for
the server to come back. Streamed, a dead engine is an error inside the
stream (``terminated``, Qwen3.5-9B on edge-c102, 2026-10-08 10:06, the model
unloaded with it); that reloads too, when the model is no longer loaded at
the guard's context. Without the guard the backend is plain HTTP.

The guards the Tier-3 batch B and C rig added on 2026-10-07/08
(benchmarks/probe_runs/2026-10-07-lmstudio-t3bc, lmstudio_runner.py and
run_models.py) are here too:

- Every turn is streamed (``stream_options.include_usage``) and assembled
  here -- content, reasoning and tool calls by index -- and the turn ends when
  the model starts a call past ``CALL_CAP``; the first ``CALL_CAP`` calls run
  and their results go back, as for any turn. GLM-4.6V-Flash otherwise wrote
  one call after another without waiting for a result (``place_text`` at
  coordinates it had not read) until the context filled; LM Studio ignores
  ``parallel_tool_calls: false``. No other model came near the cap: Qwen3.5-9B
  never made more than four calls in a turn. A turn still gets ``TURN_LIMIT``
  seconds; past it the probe stops with ``stop: "turn_limit"`` and the partial
  turn is kept in the transcript. A cut turn has no usage (LM Studio reports
  it at the end of the stream), so its output tokens are the chunk count,
  marked ``usage_estimated``; ``cut_turns`` counts the call-cap cuts.
- A 400 for a request over the context, with the model already loaded at the
  guard's context, stops the probe with ``stop: "context"``: the conversation
  has outgrown the context and a reload cannot fit it. (Before, the guard
  reloaded three times for nothing.) Below that context it is still the
  Oct 4 case, and the guard reloads.
- When the endpoint refuses the tools with ``filter-mapping not implemented``
  (Gemma-4-E4B's chat template in LM Studio, on the schemas whose ``type`` is
  a list), the request goes again with every list-valued ``type`` written as
  the equivalent ``anyOf`` of single types, for the rest of the run;
  ``type_lists_rewritten`` in run.json says so. Templates that take the
  original see it unchanged.
- The result cap, which every backend shares, is ``core.RESULT_CAP``.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from roaddraft.runners.core import Backend, Episode, Outcome, register

DEFAULT_BASE_URL = "http://localhost:1234/v1"
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms")
RELOAD_MARKERS = ("exceed_context_size_error", "fetch failed", "terminated",
                  "LM Link client transport disposed")
#: a 400 that is the model's fault, not the request's: LM Studio could not
#: parse the tool call the model wrote (seen with Llama 3.1 8B, Oct 7 2026).
#: Sampling again is the only answer, so it is retried like a 5xx. Streamed,
#: the same failure arrives as an error inside the stream.
RESAMPLE_MARKERS = ("does not match the expected",)
#: the chat template cannot render a list-valued JSON Schema ``type`` (Gemma-4-E4B)
TYPE_LIST_MARKERS = ("filter-mapping not implemented",)
SERVER_WAIT = 15 * 60
CALL_CAP = 4            # tool calls run from one turn; the start of another ends the turn
TURN_LIMIT = 1800.0     # seconds one turn may take, and the socket's read timeout


class ContextFull(Exception):
    """The request is bigger than the context the model is already loaded at."""


class ToolsRefused(Exception):
    """The endpoint's chat template cannot render the tool schemas as written."""


class StreamError(RuntimeError):
    """An error the server sent inside a stream, after the 200."""


def parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw or not str(raw).strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparsed": raw}


def rewrite_type_lists(schema):
    """The same JSON Schema with every list-valued ``type`` as an ``anyOf`` of single types."""
    if isinstance(schema, dict):
        schema = {k: rewrite_type_lists(v) for k, v in schema.items()}
        if isinstance(schema.get("type"), list):
            schema["anyOf"] = [{"type": t} for t in schema.pop("type")]
        return schema
    if isinstance(schema, list):
        return [rewrite_type_lists(v) for v in schema]
    return schema


def function_tools(server_tools: List[dict], rewrite: bool = False) -> List[dict]:
    """The MCP tools as chat-completions function tools."""
    return [{"type": "function", "function": {
        "name": t["name"], "description": t.get("description", ""),
        "parameters": rewrite_type_lists(t["inputSchema"]) if rewrite else t["inputSchema"]}}
        for t in server_tools]


def overflows(text: str) -> bool:
    """An error that says the request is bigger than the context."""
    return "exceed" in text and "context" in text


class LmStudioGuard:
    """Reload the model at the context the run needs; wait out a server restart."""

    def __init__(self, base_url: str, model: str, context: int, lms: str = LMS):
        self.base_url, self.model, self.context, self.lms = base_url, model, context, lms
        self.models_url = base_url.rsplit("/v1", 1)[0] + "/api/v0/models"
        self.reloads = 0

    def reload(self) -> None:
        self.reloads += 1
        subprocess.run([self.lms, "unload", self.model], capture_output=True, text=True)
        r = subprocess.run([self.lms, "load", self.model, "--context-length", str(self.context),
                            "--parallel", "1", "-y"], capture_output=True, text=True)
        print(f"reloaded {self.model} at context {self.context}: rc={r.returncode}", flush=True)

    def models(self) -> List[dict]:
        with urllib.request.urlopen(self.models_url, timeout=10) as resp:
            return json.loads(resp.read()).get("data", [])

    def loaded_context(self) -> int:
        """The context the model is loaded at now; 0 if it is not loaded or the server is down."""
        try:
            models = self.models()
        except Exception:
            return 0
        loaded = [m for m in models if m.get("id") == self.model and m.get("state") == "loaded"]
        return loaded[0].get("loaded_context_length", 0) if loaded else 0

    def wait_for_server(self) -> None:
        t0 = time.time()
        while time.time() - t0 < SERVER_WAIT:
            try:
                self.models()
            except Exception:
                time.sleep(30)
                continue
            if self.loaded_context() < self.context:
                self.reload()
            return
        print(f"LM Studio did not come back within {SERVER_WAIT} s", flush=True)


def read_stream(lines: Iterable[bytes], t0: float, call_cap: int = CALL_CAP,
                turn_limit: float = TURN_LIMIT, clock: Callable[[], float] = time.time) -> dict:
    """A streamed turn assembled into the shape of a non-streamed reply. It
    ends at the start of a call past ``call_cap`` (``finish_reason``
    ``call_cap``, the earlier calls whole) or after ``turn_limit`` seconds
    (``turn_limit``, whatever had come). Without a usage chunk the output
    tokens are the chunk count, marked ``estimated``."""
    content, reasoning, calls, usage, finish, chunks = [], [], {}, {}, None, 0
    for raw in lines:
        line = (raw.decode(errors="replace") if isinstance(raw, bytes) else raw).strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        d = json.loads(data)
        if d.get("error"):
            raise StreamError(json.dumps(d["error"]))
        if d.get("usage"):
            usage = d["usage"]
        for ch in d.get("choices") or []:
            delta = ch.get("delta") or {}
            chunks += 1
            content.append(delta.get("content") or "")
            reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            for tc in delta.get("tool_calls") or []:
                i = tc.get("index")
                if i is None:   # a server that leaves it out: a new id starts a call, no id goes on
                    ids = {c["id"]: k for k, c in calls.items()}
                    i = ids.get(tc["id"], len(calls)) if tc.get("id") else max(calls, default=0)
                if i not in calls and len(calls) >= call_cap:
                    finish = "call_cap"
                    break
                slot = calls.setdefault(i, {"id": None, "type": "function",
                                            "function": {"name": "", "arguments": ""}})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
            if finish == "call_cap":
                break
            finish = ch.get("finish_reason") or finish
        if finish == "call_cap":
            break
        if clock() - t0 > turn_limit:
            finish = "turn_limit"
            break
    msg: Dict[str, object] = {"role": "assistant", "content": "".join(content)}
    if "".join(reasoning):
        msg["reasoning_content"] = "".join(reasoning)
    if calls:
        ordered = [calls[i] for i in sorted(calls)]
        for n, c in enumerate(ordered):
            c["id"] = c["id"] or f"call_{int(t0)}_{n}"
        msg["tool_calls"] = ordered
    if not usage:
        usage = {"completion_tokens": chunks, "estimated": True}
    return {"choices": [{"message": msg, "finish_reason": finish}], "usage": usage}


def post_chat(url: str, body: dict, headers: Dict[str, str], guard: Optional[LmStudioGuard] = None,
              attempts: int = 4, sleep: Callable[[float], None] = time.sleep,
              call_cap: int = CALL_CAP, turn_limit: float = TURN_LIMIT,
              clock: Callable[[], float] = time.time) -> dict:
    """One streamed chat completion, read by ``read_stream``, with the retries
    and the guard. Raises ``ToolsRefused`` and ``ContextFull`` for the backend
    to act on."""
    data = json.dumps(dict(body, stream=True, stream_options={"include_usage": True})).encode()
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers})
            t0 = clock()
            with urllib.request.urlopen(req, timeout=turn_limit) as resp:
                return read_stream(resp, t0, call_cap, turn_limit, clock)
        except urllib.error.HTTPError as ex:
            code, text = ex.code, ex.read().decode(errors="replace")
        except StreamError as ex:
            code, text = None, str(ex)
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError,
                http.client.HTTPException):
            # socket.timeout is not a TimeoutError before Python 3.10: a stalled stream raises it
            if not last:
                if guard:
                    guard.wait_for_server()
                else:
                    sleep(15 * (attempt + 1))
                continue
            raise
        where = f"HTTP {code}" if code else "stream error"
        if any(m in text for m in TYPE_LIST_MARKERS):
            raise ToolsRefused(text[:300])
        if guard and overflows(text) and guard.loaded_context() >= guard.context:
            raise ContextFull(text[:300])
        # streamed, an engine that dies mid-turn says so after the 200: reload
        # only if it took the model with it
        if (guard and any(m in text for m in RELOAD_MARKERS) and not last
                and (code == 400 or guard.loaded_context() < guard.context)):
            print(f"{where}, reloading the model: {text[:140]}", flush=True)
            guard.reload()
            sleep(5)
            continue
        if any(m in text for m in RESAMPLE_MARKERS) and not last:
            print(f"{where}, the model's output could not be parsed; sampling again", flush=True)
            continue
        if code in (429, 500, 502, 503) and not last:
            sleep(15 * (attempt + 1))
            continue
        raise RuntimeError(f"{where}: {text[:300]}")
    raise RuntimeError("gave up")


@register
class OpenAIBackend(Backend):
    name = "openai"

    def __init__(self, options, post: Optional[Callable[[dict], dict]] = None):
        super().__init__(options)
        self.base_url = (options.extra.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        key_env = options.extra.get("api_key_env") or "OPENAI_API_KEY"
        key = os.environ.get(key_env, "")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}
        context = options.extra.get("lms_context")
        self.guard = LmStudioGuard(self.base_url, options.model, int(context)) if context else None
        self.post = post or self._post
        self.rewrite_type_lists = False     # set for good the first time the tools are refused

    def _post(self, body: dict) -> dict:
        return post_chat(self.base_url + "/chat/completions", body, self.headers, self.guard)

    def chat(self, server_tools: List[dict], messages: List[dict]) -> dict:
        """One turn; a template that refuses the tool schemas gets them again
        with the type lists rewritten (see the module docstring)."""
        while True:
            tools = function_tools(server_tools, self.rewrite_type_lists)
            try:
                return self.post({"model": self.options.model, "messages": messages, "tools": tools})
            except ToolsRefused as ex:
                if self.rewrite_type_lists:
                    raise
                print(f"the tools were refused, rewriting type lists as anyOf: {ex}", flush=True)
                self.rewrite_type_lists = True

    def run(self, episode: Episode) -> Outcome:
        server = episode.server
        assert server is not None
        messages: List[dict] = [{"role": "system", "content": server.instructions},
                                {"role": "user", "content": episode.task}]
        episode.log.extend(messages)
        usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        turns, final, stop, unparsed = 0, "", "max_turns", False
        cut_turns, estimated_turns = 0, 0
        extra: Dict[str, object] = {}
        reloads_before = self.guard.reloads if self.guard else 0
        try:
            for _turn in range(self.options.max_turns):
                if episode.over_budget():
                    stop = "budget"
                    break
                t0 = time.time()
                reply = self.chat(server.tools, messages)
                u = reply.get("usage") or {}
                usage["input_tokens"] += u.get("prompt_tokens", 0)
                usage["output_tokens"] += u.get("completion_tokens", 0)
                usage["reasoning_tokens"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
                choice = reply["choices"][0]
                msg = choice["message"]
                content = msg.get("content") or ""
                calls = msg.get("tool_calls") or []
                sent = {"role": "assistant", "content": content}
                if calls:
                    sent["tool_calls"] = calls
                messages.append(sent)
                turns += 1
                finish = choice.get("finish_reason")
                kept = dict(sent)
                kept["finish_reason"] = finish
                kept["seconds"] = round(time.time() - t0, 1)
                reasoning = msg.get("reasoning_content") or msg.get("reasoning")
                if reasoning:
                    kept["reasoning"] = reasoning
                if u.get("estimated"):
                    kept["usage_estimated"] = True
                    estimated_turns += 1
                episode.log.append(kept)
                if finish == "turn_limit":      # the partial turn is kept; its calls are not run
                    stop = "turn_limit"
                    break
                cut_turns += finish == "call_cap"
                if not calls:
                    final = content
                    stop = "length" if finish == "length" else "answered"
                    unparsed = "<tool_call>" in content
                    break
                for call in calls:
                    fn = call["function"]
                    result = server.call(fn["name"], parse_args(fn.get("arguments")))
                    tool_msg = {"role": "tool", "tool_call_id": call.get("id"), "name": fn["name"],
                                "content": result.rendered(vision=False)}
                    messages.append(tool_msg)
                    episode.log.append(tool_msg)
        except ContextFull as ex:
            stop = "context"
            extra["context_error"] = str(ex)
            print(f"context full: {ex}", flush=True)
        extra.update({"reloads": (self.guard.reloads - reloads_before) if self.guard else 0,
                      "base_url": self.base_url, "cut_turns": cut_turns,
                      "usage_estimated_turns": estimated_turns,
                      "type_lists_rewritten": self.rewrite_type_lists})
        if unparsed:
            extra["unparsed_tool_markup"] = True
        return Outcome(stop=stop, final=final, turns=turns, usage=usage, extra=extra)
