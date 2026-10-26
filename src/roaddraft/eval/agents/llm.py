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

A provider's HTTP failure is an ``error``: the harness's, not the model's.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from roaddraft.eval import prompts
from roaddraft.eval.agents.basic import Action, Agent, AgentRefusal, Submit, ToolCall
from roaddraft.eval.providers.base import Call, LimitReached, Provider, add_usage

NUDGE = ("Your last turn was cut off at the output limit before it made a tool call. "
         "Go on with tool calls, and call submit when the drawing is done.")
#: the step and fault counts at or below which each turn's results carry a note
LOW_STEPS = 15
LOW_FAULTS = 3


def result_text(result: dict) -> str:
    """A bus result as the model reads it: compact JSON, unicode as is."""
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


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
        self._pending: List[Call] = []
        self._usage: Dict[str, int] = {}
        self._record: dict = {}

    # ------------------------------------------------------------ lifecycle

    def reset(self, task, level: str, mode: str) -> None:
        self.provider.reset(task)

    def ready(self) -> bool:
        return self.provider.ready()
        self.transcript, self.tools, self._pending = [], [], []
        self._usage, self._record = {}, {}
        self.system = self.fixed_system or prompts.system_prompt("neutral", mode)

    def begin(self, context: dict) -> None:
        if self.fixed_system:
            return
        if context.get("system"):  # a task with a system prompt of its own (a probe task)
            self.system = context["system"]
            return
        text = prompts.system_prompt(context.get("dialect", "neutral"), context["mode"],
                                     context.get("budgets"))
        skin = context.get("skin")
        self.system = skin.text(text) if skin is not None else text

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

    def act(self, observation: dict) -> Action:
        if not self.transcript:
            self.tools = list(observation.get("tools") or [])
            self.transcript.append({"role": "user", "text": observation["brief"]})
        else:
            self.transcript.append(self._results(observation))
        self._pending = []
        usage: Dict[str, int] = {}
        texts, thoughts, stops = [], [], []
        self._usage, self._record = usage, {}
        nudges = 0
        while True:
            turn = self.provider.complete(self.system, self.transcript, self.tools)
            add_usage(usage, turn.usage)
            texts += [turn.text] if turn.text else []
            thoughts += [turn.thinking] if turn.thinking else []
            stops.append(turn.stop_detail or turn.stop)
            self._record = {"text": "\n".join(texts), "thinking": "\n".join(thoughts),
                            "stop": turn.stop, "stop_detail": stops[-1]}
            if nudges:
                self._record["nudges"] = nudges
            if turn.stop == "refusal":
                raise AgentRefusal(turn.stop_detail or "refusal")
            self.transcript.append({"role": "assistant", "text": turn.text,
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
                self.transcript.append({"role": "user", "text": NUDGE})
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


__all__ = ["LLMAgent", "NUDGE", "LOW_STEPS", "LOW_FAULTS", "result_text"]
