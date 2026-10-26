"""The agent interface and the four non-LLM agents."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from roaddraft.tasks.brief import Task
from roaddraft.tasks.reference import phase_commands, solution_commands
from roaddraft.tasks.types import task_type


@dataclass
class ToolCall:
    name: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "params": self.params}


@dataclass
class Submit:
    note: str = ""
    implicit: bool = False   # the model stopped talking without calling submit


Action = Union[List[ToolCall], Submit]


class AgentRefusal(Exception):
    """The agent declined the task (an LLM refusal); the episode ends with
    ``termination = "refusal"``."""


class Agent:
    """One drafting agent for one episode at a time."""
    name = "agent"

    def reset(self, task: Task, level: str, mode: str) -> None:
        """Called once per episode before the first observation."""

    def ready(self) -> bool:
        """Whether an episode may start: an LLM agent asks its provider, whose
        local-server guard reloads and probes the engine. False stops the run
        before the episode file is written, so the episode runs on resume."""
        return True

    def begin(self, context: dict) -> None:
        """Called after ``reset`` with the episode's ``mode``, ``level``,
        ``dialect``, ``budgets`` (the mode's) and ``scope``, before the
        header is written: an LLM agent builds its system prompt here."""

    def act(self, observation: dict) -> Action:  # pragma: no cover - abstract
        raise NotImplementedError

    def usage(self) -> Dict[str, int]:
        """Tokens the last ``act`` cost, for the budget; nothing for a scripted agent."""
        return {}

    def turn_record(self) -> dict:
        """What the trajectory keeps of the last ``act`` beside the calls: an
        LLM agent's text, thinking and stop reason."""
        return {}

    def close(self) -> None:
        """Called once when the episode ends, however it ends."""

    def describe(self) -> dict:
        """What the trajectory header records about the agent."""
        return {"model": self.name, "provider": "harness"}


def calls_from_commands(commands: Iterable[Tuple[str, dict]]) -> List[ToolCall]:
    return [ToolCall(name, dict(params)) for name, params in commands]


class _QueueAgent(Agent):
    """Emits a queue of calls, ``per_turn`` at a time (all at once by default),
    then submits."""

    def __init__(self, per_turn: Optional[int] = None):
        self.per_turn = per_turn
        self.queue: List[ToolCall] = []

    def act(self, observation: dict) -> Action:
        if not self.queue:
            return Submit()
        n = len(self.queue) if self.per_turn is None else max(1, self.per_turn)
        batch, self.queue = self.queue[:n], self.queue[n:]
        return batch


class OracleAgent(_QueueAgent):
    """The reference solution, replayed through the episode loop."""
    name = "oracle"

    def reset(self, task: Task, level: str, mode: str) -> None:
        self.queue = calls_from_commands(solution_commands(task))


class NullAgent(Agent):
    """Submits at once."""
    name = "null"

    def act(self, observation: dict) -> Action:
        return Submit("nothing to do")


SCRIPTED_PHASES = ("layers", "linework", "stationing", "sheet")


class ScriptedAgent(_QueueAgent):
    """A naive drafter: of the phases the task asks for it drafts the layers,
    the linework, the stationing and the sheet, and never the bearings,
    callouts, table, title block or north arrow."""
    name = "scripted"

    def reset(self, task: Task, level: str, mode: str) -> None:
        ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
        phases = [p for p in ttype.solution_phases() if p in SCRIPTED_PHASES]
        self.queue = calls_from_commands(phase_commands(task, phases))


def journal_entries(source: Union[str, Path, Sequence[dict]]) -> List[dict]:
    """The command entries of a journal: a ``save_journal`` file (init record
    first), a trajectory's journal block, or a bare list of entries."""
    if isinstance(source, (str, Path)):
        lines = [json.loads(l) for l in Path(source).read_text().splitlines() if l.strip()]
    else:
        lines = list(source)
    out = []
    for e in lines:
        if not isinstance(e, dict):
            continue
        kind = e.get("type", "command")
        if kind == "command" and "name" in e:
            out.append({"name": e["name"], "params": e.get("params") or {}})
    return out


class ReplayAgent(_QueueAgent):
    """Replays a saved journal's commands, in order, then submits."""
    name = "replay"

    def __init__(self, source: Union[str, Path, Sequence[dict]], per_turn: Optional[int] = None,
                 name: str = "replay"):
        super().__init__(per_turn)
        self.entries = journal_entries(source)
        self.name = name
        self.source = str(source) if isinstance(source, (str, Path)) else None

    def reset(self, task: Task, level: str, mode: str) -> None:
        self.queue = [ToolCall(e["name"], dict(e["params"])) for e in self.entries]

    def describe(self) -> dict:
        return {"model": self.name, "provider": "harness",
                **({"journal": self.source} if self.source else {})}


AGENTS = {"oracle": OracleAgent, "null": NullAgent, "scripted": ScriptedAgent}

__all__ = ["ToolCall", "Submit", "Action", "AgentRefusal", "Agent", "calls_from_commands",
           "OracleAgent", "NullAgent", "ScriptedAgent", "SCRIPTED_PHASES", "journal_entries",
           "ReplayAgent", "AGENTS"]
