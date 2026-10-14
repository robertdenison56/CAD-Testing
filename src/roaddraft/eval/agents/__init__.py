"""Agents (eval plan section 4.3): one interface, ``act(observation) ->
list[ToolCall] | Submit``, and the four non-LLM implementations E2 ships.

- ``OracleAgent`` replays the task's reference solution through the loop;
  it must score 100, which proves the harness loses no points.
- ``NullAgent`` submits at once: 0.
- ``ScriptedAgent`` is a deliberately naive drafter: layers, linework,
  stationing and the sheet, nothing else; the rubric must discriminate.
- ``ReplayAgent`` replays any saved journal (a human GUI session, an earlier
  episode) for regression and curation.

An LLM agent (E3) implements the same interface over a provider.
"""
from roaddraft.eval.agents.basic import (
    AGENTS, Agent, AgentRefusal, NullAgent, OracleAgent, ReplayAgent, ScriptedAgent, Submit,
    ToolCall, calls_from_commands, journal_entries,
)

__all__ = ["AGENTS", "Agent", "AgentRefusal", "NullAgent", "OracleAgent", "ReplayAgent",
           "ScriptedAgent", "Submit", "ToolCall", "calls_from_commands", "journal_entries"]
