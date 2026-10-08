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
the server to come back. Without it the backend is plain HTTP.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from roaddraft.runners.core import Backend, Episode, Outcome, register

DEFAULT_BASE_URL = "http://localhost:1234/v1"
LMS = str(Path.home() / ".lmstudio" / "bin" / "lms")
RELOAD_MARKERS = ("exceed_context_size_error", "fetch failed", "terminated",
                  "LM Link client transport disposed")
#: a 400 that is the model's fault, not the request's: LM Studio could not
#: parse the tool call the model wrote (seen with Llama 3.1 8B, Oct 7 2026).
#: Sampling again is the only answer, so it is retried like a 5xx.
RESAMPLE_MARKERS = ("does not match the expected",)
SERVER_WAIT = 15 * 60


def parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw or not str(raw).strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparsed": raw}


class LmStudioGuard:
    """Reload the model at the context the run needs; wait out a server restart."""

    def __init__(self, base_url: str, model: str, context: int, lms: str = LMS):
        self.base_url, self.model, self.context, self.lms = base_url, model, context, lms
        self.reloads = 0

    def reload(self) -> None:
        self.reloads += 1
        subprocess.run([self.lms, "unload", self.model], capture_output=True, text=True)
        r = subprocess.run([self.lms, "load", self.model, "--context-length", str(self.context),
                            "--parallel", "1", "-y"], capture_output=True, text=True)
        print(f"reloaded {self.model} at context {self.context}: rc={r.returncode}", flush=True)

    def wait_for_server(self) -> None:
        models_url = self.base_url.rsplit("/v1", 1)[0] + "/api/v0/models"
        t0 = time.time()
        while time.time() - t0 < SERVER_WAIT:
            try:
                with urllib.request.urlopen(models_url, timeout=10) as resp:
                    models = json.loads(resp.read()).get("data", [])
                loaded = [m for m in models if m.get("id") == self.model and m.get("state") == "loaded"]
                if not loaded or loaded[0].get("loaded_context_length", 0) < self.context:
                    self.reload()
                return
            except Exception:
                time.sleep(30)
        print(f"LM Studio did not come back within {SERVER_WAIT} s", flush=True)


def post_chat(url: str, body: dict, headers: Dict[str, str], guard: Optional[LmStudioGuard] = None,
              timeout: float = 1800.0, attempts: int = 4,
              sleep: Callable[[float], None] = time.sleep) -> dict:
    data = json.dumps(body).encode()
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            text = ex.read().decode(errors="replace")
            if (guard and ex.code == 400 and any(m in text for m in RELOAD_MARKERS)
                    and attempt < attempts - 1):
                print(f"HTTP 400, reloading the model: {text[:140]}", flush=True)
                guard.reload()
                sleep(5)
                continue
            if ex.code == 400 and any(m in text for m in RESAMPLE_MARKERS) and attempt < attempts - 1:
                print(f"HTTP 400, the model's output could not be parsed; sampling again", flush=True)
                continue
            if ex.code in (429, 500, 502, 503) and attempt < attempts - 1:
                sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {ex.code}: {text[:300]}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < attempts - 1:
                if guard:
                    guard.wait_for_server()
                else:
                    sleep(15 * (attempt + 1))
                continue
            raise
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

    def _post(self, body: dict) -> dict:
        return post_chat(self.base_url + "/chat/completions", body, self.headers, self.guard)

    def run(self, episode: Episode) -> Outcome:
        server = episode.server
        assert server is not None
        tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                   "parameters": t["inputSchema"]}} for t in server.tools]
        messages: List[dict] = [{"role": "system", "content": server.instructions},
                                {"role": "user", "content": episode.task}]
        episode.log.extend(messages)
        usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        turns, final, stop, unparsed = 0, "", "max_turns", False
        reloads_before = self.guard.reloads if self.guard else 0
        for _turn in range(self.options.max_turns):
            if episode.over_budget():
                stop = "budget"
                break
            t0 = time.time()
            reply = self.post({"model": self.options.model, "messages": messages, "tools": tools,
                               "stream": False})
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
            kept = dict(sent)
            kept["finish_reason"] = choice.get("finish_reason")
            kept["seconds"] = round(time.time() - t0, 1)
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                kept["reasoning"] = reasoning
            episode.log.append(kept)
            if not calls:
                final = content
                stop = "length" if choice.get("finish_reason") == "length" else "answered"
                unparsed = "<tool_call>" in content
                break
            for call in calls:
                fn = call["function"]
                result = server.call(fn["name"], parse_args(fn.get("arguments")))
                tool_msg = {"role": "tool", "tool_call_id": call.get("id"), "name": fn["name"],
                            "content": result.rendered(vision=False)}
                messages.append(tool_msg)
                episode.log.append(tool_msg)
        extra = {"reloads": (self.guard.reloads - reloads_before) if self.guard else 0,
                 "base_url": self.base_url}
        if unparsed:
            extra["unparsed_tool_markup"] = True
        return Outcome(stop=stop, final=final, turns=turns, usage=usage, extra=extra)
