"""Any OpenAI-compatible chat-completions endpoint as a backend: LM Studio,
Ollama, vLLM, and a fine-tuned checkpoint served by any of them.

The LM Studio rig's runner (benchmarks/probe_runs/2026-10-04-lmstudio-tier2),
generalised: the MCP tools go in as function tools, the server's instructions
as the system message, tool results back as ``role: tool`` messages. A
model's thinking (``reasoning_content``, or ``reasoning``) is kept in the
transcript and by default not sent back: the tool schema already costs ~22k
tokens a request and a local model's context is the scarce resource. Runs are
text-only -- a render comes back as a note with the file path -- since tool
messages carry strings.

``--send-reasoning`` sends a tool-call turn's thinking back as that message's
``reasoning``, the field vLLM reads (v0.31.0,
entrypoints/openai/parser/harmony_utils.py) and renders as harmony's
``analysis`` channel. gpt-oss expects the thinking behind its earlier tool
calls in front of it, per the harmony format; vLLM drops what came before a
final answer itself. gpt-oss-20b's k = 3 row (2026-10-17) ran without it:
82 of 99 episodes reported calls it never made and 17 ended on vLLM's harmony
parser refusing its tool header. run.json records ``send_reasoning``.

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
- A stream whose chunks carry nothing -- no content, no reasoning under any
  key, no call fragment, no finish -- for ``STALL_LIMIT`` seconds, and at least
  ``STALL_CHUNKS`` of them, is a stall of the engine, not a turn: Gemma 4 12B
  Q8_0 at 98,304 (2026-10-28, 12:53 to 17:54) flooded empty chunks for the
  whole turn limit on ten turns in a row while answering every one-token
  probe before each episode, and Qwen3.5-9B's four "over-long turns" of
  Oct 27-28 had the same shape. With the guard the model is reloaded and the
  request sent again, once; a second stall, or one without the guard, ends
  the turn as ``turn_limit`` with ``stalled`` in the reply for the records.
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

``--extra-body JSON`` goes into every request beside the model, messages and
tools, which it cannot replace, and into run.json as ``extra_body``: the
sampling a model card asks for (Qwen3.5's thinking mode wants ``top_p`` 0.95,
``top_k`` 20, ``presence_penalty`` 1.5), or ``chat_template_kwargs``. vLLM
otherwise falls back to the repo's generation_config.json, and Qwen3.5-9B
ships none. A Runpod serverless vLLM endpoint is this backend too: the base
URL is ``https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1``, the key
``RUNPOD_API_KEY`` (benchmarks/runpod/README.md).
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
#: the model is gone or going: an engine that died, or a reload from the LM Studio
#: window (Qwen's k = 3 run, 2026-10-08 22:30:44 to 22:31:11: the last three ended
#: seven probes in 27 s, one after another, while the model came back)
RELOAD_MARKERS = ("exceed_context_size_error", "fetch failed", "terminated",
                  "LM Link client transport disposed", "Model is unloaded",
                  "Model unloaded by user or API request", "Instance does not exist",
                  "Failed to load model", "No models loaded")
#: a 400 that is the model's fault, not the request's: LM Studio could not
#: parse the tool call the model wrote (seen with Llama 3.1 8B, Oct 7 2026).
#: Sampling again is the only answer, so it is retried like a 5xx. Streamed,
#: the same failure arrives as an error inside the stream.
RESAMPLE_MARKERS = ("does not match the expected",)
#: the chat template cannot render a list-valued JSON Schema ``type`` (Gemma-4-E4B)
TYPE_LIST_MARKERS = ("filter-mapping not implemented",)
SERVER_WAIT = 15 * 60
#: after ``lms load`` returns, how long the server may take to list the model as loaded
#: (2026-10-23 22:27, d1-real: the CLI came back with rc=1 and the load finished 10 s later)
LOAD_WAIT = 180
#: a one-token completion that proves the engine answers; an engine that hung on the PC
#: (2026-10-24 01:50) took the server five minutes to call "fetch failed", so this is short
PROBE_TIMEOUT = 90.0
#: how long ``ensure_alive`` keeps reloading and probing before it gives the run up,
#: and the pause between its tries
ENGINE_WAIT, ENGINE_RETRY = 30 * 60, 30
CALL_CAP = 4            # tool calls run from one turn; the start of another ends the turn
TURN_LIMIT = 1800.0     # seconds one turn may take, and the socket's read timeout
#: a stream whose chunks carry nothing for this long is a stall of the engine (the docstring's last bullet)
STALL_LIMIT = 300.0
#: and at least this many empty chunks in that time: one empty chunk after a long prompt's processing is not one
STALL_CHUNKS = 50


class ContextFull(Exception):
    """The request is bigger than the context the model is already loaded at."""


class ToolsRefused(Exception):
    """The endpoint's chat template cannot render the tool schemas as written."""


class StreamError(RuntimeError):
    """An error the server sent inside a stream, after the 200."""


class Stalled(Exception):
    """The stream carried chunks with nothing in them for ``STALL_LIMIT`` seconds."""

    def __init__(self, seconds: float, chunks: int):
        super().__init__(f"the stream carried nothing for {seconds:.0f} s ({chunks} empty chunks)")
        self.seconds, self.chunks = seconds, chunks


def carries(delta: dict) -> bool:
    """Whether a chunk's delta brings any of the turn: text, reasoning under whatever key, a call fragment."""
    return any(v for k, v in delta.items() if k != "role")


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

    def reload(self, sleep: Callable[[float], None] = time.sleep) -> bool:
        """Unload and load the model at the run's context, then wait until the
        server lists it as loaded: ``lms load`` over LM Link can return before
        the load has finished (or with rc=1 while it goes on), and a request
        sent in that gap meets "No models loaded"."""
        self.reloads += 1
        subprocess.run([self.lms, "unload", self.model], capture_output=True, text=True)
        r = subprocess.run([self.lms, "load", self.model, "--context-length", str(self.context),
                            "--parallel", "1", "-y"], capture_output=True, text=True)
        up = self.wait_loaded(LOAD_WAIT, sleep)
        print(f"reloaded {self.model} at context {self.context}: rc={r.returncode}, "
              f"{'listed as loaded' if up else f'not listed as loaded after {LOAD_WAIT} s'}", flush=True)
        return up

    def wait_loaded(self, seconds: float, sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.time) -> bool:
        """True once the server lists the model loaded at the run's context, polling for ``seconds``."""
        t0 = clock()
        while True:
            if self.loaded_context() >= self.context:
                return True
            if clock() - t0 >= seconds:
                return False
            sleep(2)

    def probe(self, timeout: float = PROBE_TIMEOUT) -> bool:
        """One token from the model, not streamed: the engine behind the listing
        answers. False on any error or after ``timeout`` seconds."""
        body = json.dumps({"model": self.model, "max_tokens": 1,
                           "messages": [{"role": "user", "content": "Reply with one word."}]}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", body,
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return bool(json.loads(resp.read()).get("choices"))
        except Exception:  # noqa: BLE001  a dead engine fails in any of several ways
            return False

    def ensure_alive(self, deadline: float = ENGINE_WAIT, sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.time) -> bool:
        """The model listed at the run's context and answering a probe; a
        model that is not listed, or is listed but does not answer (the
        engine on the PC hung, 2026-10-24 01:50, and LM Studio listed it as
        loaded for the next seven hours), is reloaded and probed again every
        ``ENGINE_RETRY`` seconds until ``deadline``. False when it never came
        back: the caller stops the run rather than burn its episodes."""
        t0 = clock()
        tries = 0
        while True:
            if self.loaded_context() < self.context:
                print(f"{self.model} is not loaded at context {self.context}; loading it", flush=True)
                self.reload(sleep)
            if self.probe():
                if tries:
                    print(f"{self.model} answers again after {tries} reload(s)", flush=True)
                return True
            if clock() - t0 >= deadline:
                print(f"{self.model} did not answer a probe within {deadline:.0f} s", flush=True)
                return False
            tries += 1
            print(f"{self.model} is listed but does not answer (try {tries}); reloading the engine",
                  flush=True)
            self.reload(sleep)
            sleep(ENGINE_RETRY)

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
                turn_limit: float = TURN_LIMIT, clock: Callable[[], float] = time.time,
                stall_limit: float = STALL_LIMIT, stall_chunks: int = STALL_CHUNKS) -> dict:
    """A streamed turn assembled into the shape of a non-streamed reply. It
    ends at the start of a call past ``call_cap`` (``finish_reason``
    ``call_cap``, the earlier calls whole) or after ``turn_limit`` seconds
    (``turn_limit``, whatever had come). Without a usage chunk the output
    tokens are the chunk count, marked ``estimated``. Chunks carrying nothing
    for ``stall_limit`` seconds, ``stall_chunks`` of them at least, raise
    ``Stalled``."""
    content, reasoning, calls, usage, finish, chunks = [], [], {}, {}, None, 0
    stall_from, empty_run = None, 0    # when the chunks stopped carrying anything, and how many since
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
            if carries(delta) or ch.get("finish_reason") or d.get("usage"):
                stall_from, empty_run = None, 0
            else:
                now = clock()
                stall_from = now if stall_from is None else stall_from
                empty_run += 1
                if empty_run >= stall_chunks and now - stall_from >= stall_limit:
                    raise Stalled(now - stall_from, empty_run)
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


def stalled_reply(ex: Stalled, reloaded: bool) -> dict:
    """The turn a stalled stream ends: ``finish_reason`` ``turn_limit`` (the provider gave the turn up), nothing
    said, and ``stalled`` saying why, for the backends' records."""
    return {"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "turn_limit"}],
            "usage": {"completion_tokens": 0, "estimated": True},
            "stalled": {"seconds": round(ex.seconds, 1), "chunks": ex.chunks, "reloaded": reloaded}}


def post_chat(url: str, body: dict, headers: Dict[str, str], guard: Optional[LmStudioGuard] = None,
              attempts: int = 4, sleep: Callable[[float], None] = time.sleep,
              call_cap: int = CALL_CAP, turn_limit: float = TURN_LIMIT,
              clock: Callable[[], float] = time.time) -> dict:
    """One streamed chat completion, read by ``read_stream``, with the retries
    and the guard. Raises ``ToolsRefused`` and ``ContextFull`` for the backend
    to act on. A stall (``Stalled``) reloads the model once, with the guard,
    and asks again; a second one, or one without the guard, ends the turn as
    ``turn_limit`` with ``stalled`` in the reply."""
    data = json.dumps(dict(body, stream=True, stream_options={"include_usage": True})).encode()
    asked_again = False   # a reload marker met once with the model still listed
    stalled_once = False  # a stall met once: the model reloaded and the request sent again
    attempt = 0
    while attempt < attempts:
        attempt += 1
        last = attempt == attempts
        try:
            req = urllib.request.Request(url, data, {"Content-Type": "application/json", **headers})
            t0 = clock()
            with urllib.request.urlopen(req, timeout=turn_limit) as resp:
                try:
                    return read_stream(resp, t0, call_cap, turn_limit, clock)
                except Stalled as ex:
                    if guard is not None and not stalled_once:
                        print(f"stall: {ex}; reloading the model and asking again", flush=True)
                        guard.reload()
                        stalled_once = True
                        attempt -= 1    # the engine's fault, not a try of the request
                        continue
                    print(f"stall: {ex}" + (" again, after a reload" if stalled_once else
                                            " (no guard to reload the model)") + "; the turn ends", flush=True)
                    return stalled_reply(ex, stalled_once)
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
                    sleep(15 * attempt)
                continue
            raise
        where = f"HTTP {code}" if code else "stream error"
        if any(m in text for m in TYPE_LIST_MARKERS):
            raise ToolsRefused(text[:300])
        if guard and overflows(text) and guard.loaded_context() >= guard.context:
            raise ContextFull(text[:300])
        # streamed, an engine that dies mid-turn says so after the 200: reload
        # if it took the model with it, else ask again -- LM Studio can still
        # list the model for a moment after the engine stopped (2026-10-08 19:48,
        # pc-by-station), and the retry then meets "Model is unloaded" and reloads
        # An engine that died with the model still listed is asked once more, and reloaded on
        # the next such error: the listing can outlive the engine for a moment (2026-10-08) or for
        # good (2026-10-24 01:50, d1-real: "fetch failed" for seven hours with the model listed),
        # and asking again forever was 20 minutes an episode for 20 episodes.
        if guard and any(m in text for m in RELOAD_MARKERS) and not last:
            if code == 400 or asked_again or guard.loaded_context() < guard.context:
                print(f"{where}, reloading the model: {text[:140]}", flush=True)
                guard.reload()
                asked_again = False
            else:
                print(f"{where} with the model still loaded; asking again: {text[:140]}", flush=True)
                asked_again = True
            sleep(5)
            continue
        if any(m in text for m in RESAMPLE_MARKERS) and not last:
            print(f"{where}, the model's output could not be parsed; sampling again", flush=True)
            continue
        if code in (429, 500, 502, 503) and not last:
            sleep(15 * attempt)
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
        self.extra_body = dict(options.extra.get("extra_body") or {})
        self.send_reasoning = bool(options.extra.get("send_reasoning"))
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
                return self.post(dict(self.extra_body, model=self.options.model,
                                      messages=messages, tools=tools))
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
                reasoning = msg.get("reasoning_content") or msg.get("reasoning")
                sent = {"role": "assistant", "content": content}
                if calls:
                    sent["tool_calls"] = calls
                    if reasoning and self.send_reasoning:
                        sent["reasoning"] = reasoning
                messages.append(sent)
                turns += 1
                finish = choice.get("finish_reason")
                kept = dict(sent)
                kept["finish_reason"] = finish
                kept["seconds"] = round(time.time() - t0, 1)
                if reply.get("stalled"):
                    kept["stalled"] = reply["stalled"]
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
        if self.extra_body:
            extra["extra_body"] = self.extra_body
        if self.send_reasoning:
            extra["send_reasoning"] = True
        if unparsed:
            extra["unparsed_tool_markup"] = True
        return Outcome(stop=stop, final=final, turns=turns, usage=usage, extra=extra)
