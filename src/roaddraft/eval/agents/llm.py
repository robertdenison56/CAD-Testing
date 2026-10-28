"""The LLM agent (eval plan sections 4.2, 4.3): a provider-driven
tool-calling loop behind the same ``act(observation)`` as every other agent.

Turn 0 hands the model the system prompt (``eval.prompts``, in the
episode's dialect, with its budgets and mode), the task text as the first
user message, and the episode's tool definitions.  Each later turn hands
back every result of the calls the model made, in order, in one message --
the bus result JSON verbatim, a fault as an error result carrying the
engine's teaching error -- and, in the vision mode, the renders as images.
When few steps or few faults remain, a one-line ``[harness]`` note says so.
The conversation is append-only, so a provider's cached prefix grows turn
by turn and the thinking blocks a vendor requires back go back untouched.

How a turn ends the episode, or does not:

- tool calls: the harness runs them (a ``submit`` call ends the episode);
- the model stops talking without a call: that is its final answer, an
  implicit submit (``Submit(implicit=True)``), recorded as such;
- cut off at the output limit without a call: the agent asks it to go on,
  up to ``max_nudges`` times in one turn, then ``LimitReached`` ends the
  episode as a budget (``output_limit``), the model's outcome;
- a refusal: ``AgentRefusal``, ``termination = "refusal"``, never rescued.

The context budget (``Budgets.context_tokens``, the window the row is served
at) is held here, since a server that truncates an oversize prompt and
answers (LM Studio) never says so: a reply whose own prompt count is at the
budget ends the episode as ``context`` before any of its calls run, as a
refusal by vLLM would have, and a next request that cannot fit by the
transcript's own size -- the last prompt count plus a floor on the tokens
of what was appended since -- is not sent at all.  The floor never trips
a request a server would take; the reply's count is the backstop.

A provider's HTTP failure is an ``error``: the harness's, not the model's.
"""
from __future__ import annotations

import json
import math
from typing import Dict, List, Optional, Tuple

from roaddraft.eval import prompts
from roaddraft.eval.agents.basic import Action, Agent, AgentRefusal, Submit, ToolCall
from roaddraft.eval.providers.base import Call, LimitReached, Provider, add_usage

NUDGE = ("Your last turn was cut off at the output limit before it made a tool call. "
         "Go on with tool calls, and call submit when the drawing is done.")
#: the step and fault counts at or below which each turn's results carry a note
LOW_STEPS = 15
LOW_FAULTS = 3
#: a floor on the tokens in a run of text: no tokenizer in use makes fewer than
#: one token per this many characters of JSON or prose
CHARS_PER_TOKEN_MAX = 4.5
#: the fewest prompt tokens one image costs on the models the harness runs (Gemma's 256)
IMAGE_TOKENS_MIN = 256


def result_text(result: dict) -> str:
    """A bus result as the model reads it: compact JSON, unicode as is."""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def prompt_size(usage: Optional[Dict[str, int]]) -> int:
    """The tokens a request held, by its reply's usage: the uncached and the
    cached input together (0 when the reply reported none)."""
    u = usage or {}
    return sum(int(u.get(k) or 0) for k in
               ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def message_size(message: dict) -> Tuple[int, int]:
    """(characters, images) a transcript message adds to the next request:
    what goes back to the model, so an assistant's thinking does not."""
    role = message["role"]
    if role == "user":
        return len(message["text"]), 0
    if role == "assistant":
        return len(message.get("text") or "") + len(json.dumps(message.get("calls") or [])), 0
    chars, images = len(message.get("note") or ""), 0
    for r in message["results"]:
        chars += len(r["content"]) + len(r["name"])
        images += len(r.get("images") or [])
    return chars, images


def system_for(context: dict) -> str:
    """The system prompt an episode's ``begin`` context asks for: the task's
    own where it has one (a probe task), else the dialect's template filled
    with the mode and budgets, in the skin's tool names."""
    if context.get("system"):
        return context["system"]
    text = prompts.system_prompt(context.get("dialect", "neutral"), context["mode"],
                                 context.get("budgets"))
    skin = context.get("skin")
    return skin.text(text) if skin is not None else text


class LLMAgent(Agent):
    """One model, through one provider, for one episode at a time."""

    def __init__(self, provider: Provider, label: Optional[str] = None,
                 system: Optional[str] = None, max_nudges: int = 2):
        self.provider = provider
        self.name = label or provider.model
        self.fixed_system = system
        self.max_nudges = max_nudges
        self.system = ""
        self.transcript: List[dict] = []
        self.tools: List[dict] = []
        self.context_tokens: Optional[int] = None
        self._pending: List[Call] = []
        self._usage: Dict[str, int] = {}
        self._record: dict = {}
        self._last_prompt = 0          # the last reply's prompt count
        self._appended = (0, 0)        # (characters, images) added since that reply

    # ------------------------------------------------------------ lifecycle

    def reset(self, task, level: str, mode: str) -> None:
        self.provider.reset(task)
        self.transcript, self.tools, self._pending = [], [], []
        self._usage, self._record = {}, {}
        self._last_prompt, self._appended = 0, (0, 0)
        self.system = self.fixed_system or prompts.system_prompt("neutral", mode)

    def ready(self) -> bool:
        return self.provider.ready()

    def begin(self, context: dict) -> None:
        budgets = context.get("budgets")
        self.context_tokens = getattr(budgets, "context_tokens", None) or None
        if not self.fixed_system:
            self.system = system_for(context)

    # ----------------------------------------------------------------- turns

    def _note(self, budget: dict) -> Optional[str]:
        notes = []
        steps = budget.get("steps")
        if steps is not None and steps <= LOW_STEPS:
            notes.append(f"{steps} steps left; call submit before they run out")
        faults = budget.get("faults_before_stop")
        if faults is not None and faults <= LOW_FAULTS:
            notes.append(f"{faults} more failed calls in a row end the task")
        return ("[harness] " + "; ".join(notes) + ".") if notes else None

    def _results(self, observation: dict) -> dict:
        results = observation.get("results") or []
        images = observation.get("images") or []
        out = []
        for i, call in enumerate(self._pending):
            if i < len(results):
                r = results[i]
            else:
                r = {"ok": False, "name": call.name,
                     "error": {"type": "not_run", "message": "not run: the turn stopped before this call"}}
            out.append({"id": call.id, "name": call.name, "content": result_text(r),
                        "is_error": not r.get("ok", False),
                        "images": list(images[i] or []) if i < len(images) else []})
        return {"role": "results", "results": out, "note": self._note(observation.get("budget") or {})}

    def _append(self, message: dict) -> None:
        self.transcript.append(message)
        chars, images = message_size(message)
        self._appended = (self._appended[0] + chars, self._appended[1] + images)

    def context_floor(self) -> int:
        """The fewest tokens the next request can hold: the last reply's prompt
        count plus a floor on what was appended since; 0 before the first reply."""
        if not self._last_prompt:
            return 0
        chars, images = self._appended
        return self._last_prompt + math.ceil(chars / CHARS_PER_TOKEN_MAX) + images * IMAGE_TOKENS_MIN

    def _check_context(self, held: Optional[int] = None) -> None:
        """``LimitReached("context")`` when the budget is set and the request
        cannot fit: before sending, by the floor; after a reply, by its count."""
        budget = self.context_tokens
        if not budget:
            return
        if held is None:
            floor = self.context_floor()
            if floor >= budget:
                raise LimitReached("context", f"the next request would hold at least {floor} "
                                   f"tokens, past the context budget of {budget}: the "
                                   "conversation has outgrown the context")
        elif held >= budget:
            raise LimitReached("context", f"the request held {held} tokens, past the context "
                               f"budget of {budget}: the conversation has outgrown the context")

    def act(self, observation: dict) -> Action:
        if not self.transcript:
            self.tools = list(observation.get("tools") or [])
            self._append({"role": "user", "text": observation["brief"]})
        else:
            self._append(self._results(observation))
        self._pending = []
        usage: Dict[str, int] = {}
        texts, thoughts, stops = [], [], []
        self._usage, self._record = usage, {}
        nudges = 0
        while True:
            self._check_context()
            turn = self.provider.complete(self.system, self.transcript, self.tools)
            add_usage(usage, turn.usage)
            held = prompt_size(turn.usage)
            if held:
                self._last_prompt, self._appended = held, (0, 0)
            texts += [turn.text] if turn.text else []
            thoughts += [turn.thinking] if turn.thinking else []
            stops.append(turn.stop_detail or turn.stop)
            self._record = {"text": "\n".join(texts), "thinking": "\n".join(thoughts),
                            "stop": turn.stop, "stop_detail": stops[-1]}
            if nudges:
                self._record["nudges"] = nudges
            if turn.stop == "refusal":
                raise AgentRefusal(turn.stop_detail or "refusal")
            self._check_context(held)
            self._append({"role": "assistant", "text": turn.text,
                          "calls": [c.to_dict() for c in turn.calls], "raw": turn.raw})
            if turn.calls:
                self._pending = list(turn.calls)
                return [ToolCall(c.name, dict(c.params)) for c in turn.calls]
            if turn.stop == "max_tokens":
                if nudges >= self.max_nudges:
                    raise LimitReached("output_limit",
                                       f"the model was cut off at the output limit {nudges + 1} "
                                       "times in one turn without a tool call")
                nudges += 1
                self._append({"role": "user", "text": NUDGE})
                continue
            return Submit(note=turn.text, implicit=True)

    # ---------------------------------------------------------------- record

    def usage(self) -> Dict[str, int]:
        return dict(self._usage)

    def turn_record(self) -> dict:
        return dict(self._record)

    def describe(self) -> dict:
        return {"model": self.provider.model, "provider": self.provider.name,
                "effort": self.provider.effort, "label": self.name,
                "prompt_sha256": prompts.digest(self.system) if self.system else None,
                "system_prompt": self.system, "provider_config": self.provider.describe()}


__all__ = ["LLMAgent", "system_for", "NUDGE", "LOW_STEPS", "LOW_FAULTS", "CHARS_PER_TOKEN_MAX",
           "IMAGE_TOKENS_MIN", "result_text", "prompt_size", "message_size"]
