"""Any OpenAI-compatible chat-completions endpoint as a provider (eval plan
section 4.4): LM Studio, Ollama, vLLM, a Runpod serverless vLLM endpoint,
and the fine-tuned checkpoint the Phase 5 run will serve from one of them.

The HTTP is the Track P runner's (``roaddraft.runners.openai_compat``):
every turn streamed and assembled, retries, the LM Studio reload guard when
``lms_context`` is given, and the type-list rewrite for a chat template that
cannot render a list-valued ``type``.  The tools go in as function tools,
the system prompt as the system message, each tool result as a ``role:
tool`` message.  A model's reasoning (``reasoning_content``) is kept for the
trajectory and not sent back, as in the runner: a local model's context is
the scarce resource.  An image a call returned -- a render in the vision
mode, a scan or a marked-up page from ``view_attachment`` in every mode --
goes back as a user message with the PNG as a data URL after the tool
messages, since tool messages carry strings: the ``image_url`` content part
LM Studio and vLLM take for a vision model (the Track P runner of the same
name never passed images; this provider always has).

``call_cap`` ends a turn when the model starts a call past it (the earlier
calls run).  The runner's cap of 4 was a guard for one local model that
wrote calls without waiting for results; here it is 16 by default, so a
strong model's parallel calls are not cut.

``thinking="off"`` (``--thinking off``; training plan, the like-for-like base
of a checkpoint served without thinking) asks the server to render the
generation prompt with the think block closed: ``THINKING_OFF`` goes into
every request, over ``extra_body`` where the two meet.  It is recorded in
the episode header (``provider_config.thinking``) and in ``run.json``; left
unset nothing is sent and nothing is recorded, so the model's default
stands (Qwen3.5 thinks).  Whether the server obeyed shows in the reply: a
turn's ``reasoning_tokens`` and thinking text stay empty when it did.

Usage: ``prompt_tokens`` includes any cached tokens, so ``input_tokens`` is
the prompt less ``prompt_tokens_details.cached_tokens`` and the cached part
is ``cache_read_input_tokens``, the Anthropic meaning of each.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List, Optional

from roaddraft.eval.providers.base import Call, LimitReached, Provider, Turn

DEFAULT_BASE_URL = "http://localhost:1234/v1"
CALL_CAP = 16
#: what ``--thinking off`` adds to a request.  ``chat_template_kwargs`` is the field llama.cpp's server and vLLM
#: pass to the chat template (Qwen3.5's closes the think block on ``enable_thinking: false``); ``reasoning_effort:
#: "none"`` is the OpenAI-style spelling of the same wish.  Which of the two LM Studio's server reads was not
#: confirmed against a live server when this was written (2026-11-14), so both go and the run is checked by
#: its reasoning tokens (``lms_campaign.py thinking RUN``) before it is believed.
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"}
THINKING = ("off",)
STOP_MAP = {"tool_calls": "tool_use", "function_call": "tool_use", "call_cap": "tool_use",
            "stop": "end", "length": "max_tokens", "content_filter": "refusal"}


def parse_args(raw) -> dict:
    """A call's arguments; text that is not a JSON object comes back as
    ``{"_unparsed": text}``, which the command's schema then refuses with a
    teaching error, as any invalid call."""
    if isinstance(raw, dict):
        return raw
    if not raw or not str(raw).strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparsed": raw}
    return value if isinstance(value, dict) else {"_unparsed": raw}


def function_tools(tools: List[dict], rewrite: bool = False) -> List[dict]:
    from roaddraft.runners.openai_compat import rewrite_type_lists
    return [{"type": "function", "function": {
        "name": t["name"], "description": t.get("description", ""),
        "parameters": rewrite_type_lists(t["input_schema"]) if rewrite else t["input_schema"]}}
        for t in tools]


def chat_messages(system: str, transcript: List[dict]) -> List[dict]:
    """The neutral conversation as chat-completions messages."""
    out: List[dict] = [{"role": "system", "content": system}]
    for m in transcript:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            out.append(m["raw"])
        elif role == "results":
            images = []
            for r in m["results"]:
                out.append({"role": "tool", "tool_call_id": r["id"], "name": r["name"],
                            "content": r["content"]})
                images.extend(r.get("images") or [])
            parts = []
            if m.get("note"):
                parts.append({"type": "text", "text": m["note"]})
            if images:
                parts.append({"type": "text", "text": "The image(s) from the calls above:"})
                parts.extend({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
                             for mime, data in images)
            if parts:
                out.append({"role": "user", "content": parts if images else m["note"]})
        else:
            raise ValueError(f"unknown transcript role {role!r}")
    return out


def parse_reply(reply: dict, send_reasoning: bool = False) -> Turn:
    choice = (reply.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    finish = choice.get("finish_reason") or "stop"
    if finish == "turn_limit":
        stall = reply.get("stalled")
        if stall:   # the backend's stall guard gave the turn up: the engine streamed nothing (runners.openai_compat)
            what = (f"the model's stream sent no chunk for {stall['seconds']:.0f} s" if stall.get("silent") else
                    f"the model's stream carried nothing for {stall['seconds']:.0f} s ({stall['chunks']} empty chunks)")
            raise LimitReached("turn_time", what
                               + (", before and after a reload of the engine" if stall.get("reloaded") else ""))
        raise LimitReached("turn_time", "the model's turn ran past the provider's turn limit")
    raw_calls = msg.get("tool_calls") or []
    calls = []
    for n, c in enumerate(raw_calls):
        fn = c.get("function") or {}
        calls.append(Call(c.get("id") or f"call_{n}", fn.get("name", ""),
                          parse_args(fn.get("arguments"))))
    sent: Dict[str, object] = {"role": "assistant", "content": msg.get("content") or ""}
    if raw_calls:
        sent["tool_calls"] = raw_calls
    u = reply.get("usage") or {}
    prompt = int(u.get("prompt_tokens") or 0)
    cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    usage = {"input_tokens": prompt - cached, "output_tokens": int(u.get("completion_tokens") or 0),
             "cache_read_input_tokens": cached, "cache_creation_input_tokens": 0,
             "reasoning_tokens": int((u.get("completion_tokens_details") or {})
                                     .get("reasoning_tokens") or 0)}
    stop = "tool_use" if calls else STOP_MAP.get(finish, "end")
    if stop == "tool_use" and not calls:
        stop = "end"
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    if send_reasoning and raw_calls and reasoning:
        # gpt-oss: its harmony format wants the reasoning of a tool-calling turn back with the calls (the probe
        # runner's --send-reasoning, 2026-10-19: gpt-oss-20b 7.1% -> 13.1% on Track P)
        sent["reasoning"] = reasoning
    return Turn(text=(msg.get("content") or "").strip(), calls=calls, stop=stop, usage=usage,
                thinking=reasoning if isinstance(reasoning, str) else json.dumps(reasoning),
                raw=sent, stop_detail=finish + (" (usage estimated)" if u.get("estimated") else ""))


#: Runpod's serverless proxy ends a streamed request after 570 s and says so inside the stream
#: ('{"message": "stream did not complete within 570 seconds", "type": "timeout_error"}'; Gemma 4 12B lost 10 of
#: 100 d1-variance episodes to it on 2026-10-20, all left out of its score as errors). A warm worker reaches it
#: only by the model's own turn running that long, so it is that turn's time limit, as on the probe board.
PROXY_CUT_MARKERS = ("did not complete within",)
#: vLLM refuses a prompt past --max-model-len with an HTTP 400 ("This model's maximum context length is N
#: tokens. However, you requested M tokens ..."); without the LM Studio guard nothing turned that into the
#: context stop it is.
CONTEXT_REFUSAL_MARKERS = ("maximum context length", "maximum model length", "max_model_len")


def hosted_limit(text: str) -> Optional[tuple]:
    """The budget a hosted endpoint's error stands for, as ``(limit, message)``, or None for a real error."""
    if text.startswith("stream error") and any(m in text for m in PROXY_CUT_MARKERS):
        return ("turn_time", "the endpoint's proxy ended the streamed turn: " + text[len("stream error: "):][:200])
    if text.startswith("HTTP 400") and (any(m in text for m in CONTEXT_REFUSAL_MARKERS)
                                        or ("exceed" in text and "context" in text)):
        return ("context", "the server refused the request as longer than its context: " + text[10:][:200])
    return None


class OpenAICompatProvider(Provider):
    name = "openai"

    def __init__(self, model: str, effort: Optional[str] = None, base_url: Optional[str] = None,
                 api_key_env: str = "OPENAI_API_KEY", extra_body: Optional[dict] = None,
                 max_tokens: Optional[int] = None, lms_context: Optional[int] = None,
                 call_cap: int = CALL_CAP, post: Optional[Callable[[dict], dict]] = None,
                 send_reasoning: bool = False, thinking: Optional[str] = None):
        super().__init__(model, effort)
        if thinking is not None and thinking not in THINKING:
            raise ValueError(f"unknown thinking setting {thinking!r}; the one setting is 'off' "
                             "(leave it unset for the model's default)")
        if thinking == "off" and effort:
            raise ValueError("thinking off and an effort level both set reasoning_effort; give one")
        self.thinking = thinking
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key_env = api_key_env
        self.extra_body = dict(extra_body or {})
        self.max_tokens = max_tokens
        self.call_cap = int(call_cap)
        self.send_reasoning = bool(send_reasoning)
        self.lms_context = lms_context
        self.rewrite_type_lists = False
        self.guard = None
        if post is None:
            from roaddraft.runners.openai_compat import LmStudioGuard, post_chat
            key = os.environ.get(api_key_env, "")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            guard = LmStudioGuard(self.base_url, model, int(lms_context)) if lms_context else None
            self.guard = guard
            url = self.base_url + "/chat/completions"
            post = lambda body: post_chat(url, body, headers, guard, call_cap=self.call_cap)  # noqa: E731
        self.post = post

    def ready(self) -> bool:
        """With the LM Studio guard: the model listed at the run's context and
        answering a one-token probe, reloaded until it is or the guard's
        deadline passes. Without it (vLLM, Ollama, a hosted endpoint): True."""
        return self.guard.ensure_alive() if self.guard is not None else True

    def request(self, system: str, transcript: List[dict], tools: List[dict]) -> dict:
        body = dict(self.extra_body, model=self.model, messages=chat_messages(system, transcript),
                    tools=function_tools(tools, self.rewrite_type_lists))
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        if self.effort:
            body["reasoning_effort"] = self.effort
        if self.thinking == "off":
            for key, value in THINKING_OFF.items():
                body[key] = dict(body.get(key) or {}, **value) if isinstance(value, dict) else value
        return body

    def complete(self, system: str, transcript: List[dict], tools: List[dict]) -> Turn:
        from roaddraft.runners.openai_compat import ContextFull, ToolsRefused
        while True:
            try:
                return parse_reply(self.post(self.request(system, transcript, tools)), self.send_reasoning)
            except ToolsRefused:
                if self.rewrite_type_lists:
                    raise
                self.rewrite_type_lists = True
            except ContextFull as ex:
                raise LimitReached("context", f"the conversation outgrew the loaded context: {ex}") from ex
            except RuntimeError as ex:
                limit = hosted_limit(str(ex))
                if limit is None:
                    raise
                raise LimitReached(*limit) from ex

    def describe(self) -> dict:
        d = {"base_url": self.base_url, "call_cap": self.call_cap,
             "type_lists_rewritten": self.rewrite_type_lists}
        if self.extra_body:
            d["extra_body"] = self.extra_body
        if self.max_tokens:
            d["max_tokens"] = self.max_tokens
        if self.lms_context:
            d["lms_context"] = self.lms_context
        if self.send_reasoning:
            d["send_reasoning"] = True
        if self.thinking:
            d["thinking"] = self.thinking
        return d


__all__ = ["OpenAICompatProvider", "DEFAULT_BASE_URL", "THINKING", "THINKING_OFF", "parse_args", "function_tools",
           "chat_messages", "parse_reply"]
