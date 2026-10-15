"""The RoadDraft evaluation harness (eval plan section 4): the episode loop a
drafting agent runs through, the budgets it runs under, the tools it is
shown, the trajectory it leaves behind, the task sets it is run on, and the
runner that drives a matrix of episodes.

An episode opens a task's starting document in a ``Session``, hands the
agent the task text and the tool definitions, executes the agent's tool
calls on the session (through the whitelist, counting every call against the
budgets), and when the agent submits -- or a budget trips -- verifies the
document against the task's ground truth and writes one JSON-lines
trajectory: header, turns, the replayable journal, the verify report, the
audit, the end record.

E2 ships four non-LLM agents (``oracle``, ``null``, ``scripted``, ``replay``)
and the CLI ``python -m roaddraft.eval run | taskset | verify | human``.  The
oracle replays the task's reference solution *through the loop* and must
score 100: that is the harness's own acceptance test, kept permanent in
``tests/test_eval_episode.py``.

E3 adds the model under test: ``LLMAgent`` over a provider
(``eval.providers``: ``anthropic``, ``openai``-compatible, ``fake``), the
system prompts (``eval.prompts``), the dialect skins (``eval.dialects``) and
the dated price table (``eval.prices``); ``run --model ID`` runs one.
"""
from roaddraft.eval.agents import (
    AGENTS, Agent, LLMAgent, NullAgent, OracleAgent, ReplayAgent, ScriptedAgent, Submit, ToolCall,
)
from roaddraft.eval.budget import Budgets, BudgetState
from roaddraft.eval.episode import HARNESS_VERSION, Episode, EpisodeConfig, EpisodeResult, run_episode
from roaddraft.eval.tools import DIALECTS, MODES, tool_definitions

__all__ = ["HARNESS_VERSION", "AGENTS", "Agent", "LLMAgent", "NullAgent", "OracleAgent",
           "ReplayAgent", "ScriptedAgent", "Submit", "ToolCall", "Budgets", "BudgetState",
           "Episode", "EpisodeConfig", "EpisodeResult", "run_episode", "DIALECTS", "MODES",
           "tool_definitions"]
