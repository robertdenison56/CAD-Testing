"""A provider with no network (eval plan section 4.4): every E3 test runs on it.

``FakeProvider(script)`` answers each request with the next item of a
script -- a ``Turn``, or a callable ``(system, transcript, tools) -> Turn``
-- and records every request it was given.  Past the end of the script it
ends the conversation (``stop = "end"``).

``FakeProvider.oracle()`` replays the task's reference solution as tool
calls, ``per_turn`` at a time, through the whole LLM stack -- the agent's
transcript, the dialect's tool names, the provider's turn shape -- and must
score what the oracle agent scores: 100.  From the CLI it is ``--provider
fake --model fake-oracle``.
"""
from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional, Sequence, Union

from roaddraft.eval.providers.base import Call, Provider, Turn

Step = Union[Turn, Callable[[str, List[dict], List[dict]], Turn]]


def turn(calls: Sequence = (), text: str = "", stop: Optional[str] = None,
         usage: Optional[Dict[str, int]] = None, thinking: str = "") -> Turn:
    """A scripted turn: ``calls`` as ``(name, params)`` pairs or ``Call``s."""
    made = [c if isinstance(c, Call) else Call(f"call_{i}", c[0], dict(c[1]))
            for i, c in enumerate(calls)]
    return Turn(text=text, calls=made, stop=stop or ("tool_use" if made else "end"),
                usage=dict(usage or {}), thinking=thinking,
                raw={"text": text, "calls": [c.to_dict() for c in made]})


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, script: Sequence[Step] = (), model: str = "fake", effort: Optional[str] = None,
                 usage: Optional[Dict[str, int]] = None, oracle: bool = False, per_turn: int = 8):
        super().__init__(model, effort)
        self.script: List[Step] = list(script)
        self.usage = dict(usage or {})     # added to every turn that has none of its own
        self.oracle_mode = oracle
        self.per_turn = max(1, int(per_turn))
        self.requests: List[dict] = []
        self._n = 0

    @classmethod
    def oracle(cls, model: str = "fake-oracle", per_turn: int = 8,
               usage: Optional[Dict[str, int]] = None) -> "FakeProvider":
        return cls(model=model, oracle=True, per_turn=per_turn, usage=usage)

    def reset(self, task) -> None:
        self._n = 0
        self.requests = []
        if self.oracle_mode:
            from roaddraft.tasks.reference import solution_commands
            self._solution = [(name, dict(params)) for name, params in solution_commands(task)]

    def _oracle_turn(self, tools: List[dict]) -> Turn:
        shown = {t.get("canonical", t["name"]): t["name"] for t in tools}
        start = (self._n - 1) * self.per_turn
        batch = self._solution[start:start + self.per_turn]
        if not batch:
            return turn([("submit", {"note": "reference solution replayed"})])
        return turn([(shown.get(name, name), params) for name, params in batch])

    def complete(self, system: str, transcript: List[dict], tools: List[dict]) -> Turn:
        self._n += 1
        self.requests.append({"system": system, "transcript": copy.deepcopy(transcript),
                              "tools": [t["name"] for t in tools]})
        if self.oracle_mode:
            result = self._oracle_turn(tools)
        elif self._n <= len(self.script):
            step = self.script[self._n - 1]
            result = step(system, transcript, tools) if callable(step) else copy.deepcopy(step)
        else:
            result = turn(text="(the script is over)")
        if not result.usage and self.usage:
            result.usage = dict(self.usage)
        return result

    def describe(self) -> dict:
        return {"oracle": True, "per_turn": self.per_turn} if self.oracle_mode else {}


__all__ = ["FakeProvider", "turn"]
