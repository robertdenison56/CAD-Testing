"""How the codex backend tells one model response from the next.

Codex's ``--json`` stream marks items, not responses, so the runner reads the
turns from structure and timing (roaddraft/runners/codex_cli.py). The turn
count is what ``max_turns`` caps, as Claude Code's ``--max-turns`` caps model
turns: the calls one response makes at once must count once.
"""
from __future__ import annotations

import json
import sys

from roaddraft.probes import tasks
from roaddraft.runners import Episode, Options, setup_probe
from roaddraft.runners.codex_cli import TURN_GAP, Stream

BLANK = next(p for p in tasks.PROBES if p.start == "blank")


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def stream(tmp_path):
    setup = setup_probe(tmp_path / "run", BLANK, [sys.executable, "-m", "roaddraft.mcp.server"])
    episode = Episode(folder=tmp_path / "run", probe=BLANK, setup=setup, task="t",
                      options=Options(model="m"))
    clock = Clock()
    return Stream(episode, clock=clock), clock, episode.log


def call(n, started=True):
    item = {"id": f"c{n}", "type": "mcp_tool_call", "server": "roaddraft", "tool": "station_to_xy",
            "arguments": {"station": n}, "result": {"content": [{"type": "text", "text": f"r{n}"}]},
            "error": None, "status": "completed"}
    events = [{"type": "item.started", "item": dict(item, result=None, status="in_progress")}] if started else []
    return events + [{"type": "item.completed", "item": item}]


def feed(s, clock, events, step=0.01):
    for event in events:
        clock.now += step
        s.feed(json.dumps(event))


def test_calls_made_at_once_are_one_turn_and_a_pause_starts_the_next(tmp_path):
    s, clock, log = stream(tmp_path)
    feed(s, clock, [{"type": "item.completed", "item": {"id": "r0", "type": "reasoning", "text": "plan"}}])
    for n in range(96):                       # one response, 96 calls, run back to back
        feed(s, clock, call(n))
    clock.now += TURN_GAP + 1                 # the model reads the results
    feed(s, clock, call(96) + call(97))
    clock.now += TURN_GAP + 1
    feed(s, clock, [{"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "done"}},
                    {"type": "turn.completed", "usage": {"input_tokens": 10}}])
    out = s.outcome()
    assert out.turns == 3 and out.extra["tool_calls"] == 98 and out.stop == "answered"
    assert [m["role"] for m in log] == ["assistant", "user", "assistant", "user", "assistant"]
    assert len(log[0]["content"]) == 97 and len(log[1]["content"]) == 96      # reasoning + 96 calls
    assert [b["tool_use_id"] for b in log[3]["content"]] == ["c96", "c97"]
    assert log[4]["content"] == [{"type": "text", "text": "done"}]


def test_text_after_a_result_is_a_new_turn_even_without_a_pause(tmp_path):
    # the model has to have read the result to write about it
    s, clock, log = stream(tmp_path)
    feed(s, clock, call(1, started=False)
         + [{"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "ok"}}], step=0.0)
    assert s.outcome().turns == 2 and [m["role"] for m in log] == ["assistant", "user", "assistant"]


def test_a_preamble_and_its_calls_are_one_turn(tmp_path):
    s, clock, log = stream(tmp_path)
    feed(s, clock, [{"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "looking"}}]
         + call(1) + call(2))
    assert s.outcome().turns == 1 and [b["type"] for b in log[0]["content"]] == ["text", "tool_use", "tool_use"]
