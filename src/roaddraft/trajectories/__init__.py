"""Trajectories: a drafting run kept as the conversation a model would have had.

A scripted solution or a model's run is a sequence of tool calls on one
document. The MCP server's ``--trace`` keeps every call with the full answer
the agent was shown (the journal keeps commands only, and a model learns as
much from the questions it asked as from the commands it sent); ``record``
runs a scripted solve through the same server so it leaves the same trace,
and audits whether the solve read anything a model could not; ``convert``
turns a trace into a conversation in the tool-calling shape: system, user,
assistant tool calls, tool results, report. ``python -m roaddraft.trajectories``
records every probe's scripted solution and converts a model's run folders.
"""
from roaddraft.trajectories.record import (Recorder, Recording, read_trace, record_solve,
                                           replay_trace)
from roaddraft.trajectories.convert import (MissingResults, calls_from_trace, conversation,
                                            has_results, tool_list, tools_digest)

__all__ = ["Recorder", "Recording", "read_trace", "record_solve", "replay_trace",
           "MissingResults", "calls_from_trace", "conversation", "has_results",
           "tool_list", "tools_digest"]
