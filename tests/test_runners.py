"""The native MCP runner (roaddraft/runners): one client for every vendor.

The server over stdio is real; the models are fakes that answer the way each
API does, so what is pinned is the loop each backend runs -- the request it
builds, how a tool result goes back, when it stops -- and the run folder it
leaves, which is what the scorer reads.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from roaddraft.mcp import config as mcpconfig
from roaddraft.probes import fixture, tasks
from roaddraft.runners import (Episode, McpServer, Options, ToolResult, estimate_cost,
                               run_probe, setup_probe)
from roaddraft.runners import __main__ as cli
from roaddraft.runners.anthropic_api import (AnthropicBackend, credentials, tool_definitions,
                                             tool_result_block)
from roaddraft.runners.claude_code import ClaudeCodeBackend, mcp_config, parse_stream
from roaddraft.runners.openai_compat import OpenAIBackend, parse_args
from roaddraft.runners.score import measures, score_label

BLANK = next(p for p in tasks.PROBES if p.start == "blank")
SERVER = [sys.executable, "-m", "roaddraft.mcp.server"]


class FakeServer:
    """What a backend sees of the server, without a process."""
    instructions = "RoadDraft is a headless 2D CAD engine. [fake instructions]"
    tools = [{"name": "get_document_state", "description": "the document",
              "inputSchema": {"type": "object", "properties": {}}},
             {"name": "draw_line", "description": "a line",
              "inputSchema": {"type": "object", "required": ["start", "end"],
                              "properties": {"start": {"type": "array"}, "end": {"type": "array"}}}},
             {"name": "render_sheet", "description": "a picture",
              "inputSchema": {"type": "object", "properties": {"sheet": {"type": "string"}}}}]

    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "render_sheet":
            return ToolResult(text='{"ok": true, "path": "renders/C-102.png"}', images=[("image/png", "QUJD")])
        if name == "draw_line" and "end" not in (arguments or {}):
            return ToolResult(text='{"ok": false, "error": {"message": "end is required"}}', is_error=True)
        return ToolResult(text=json.dumps({"ok": True, "echo": name, "arguments": arguments}))


def episode(tmp_path, server=None, **opts) -> Episode:
    probe = BLANK
    setup = setup_probe(tmp_path / "run", probe, SERVER)
    return Episode(folder=tmp_path / "run", probe=probe, setup=setup, task="do the task",
                   options=Options(model=opts.pop("model", "claude-haiku-4-5"), **opts),
                   server=server or FakeServer())


# ------------------------------------------------------------------ core

def test_the_server_over_stdio_serves_tools_and_traces_calls(tmp_path):
    setup = setup_probe(tmp_path / "p", BLANK, SERVER)
    assert (tmp_path / "p" / "server.json").exists() and (tmp_path / "p" / "prompt.txt").exists()
    assert json.loads((tmp_path / "p" / "server.json").read_text())["cmd"][-5:] == [
        "--autosave", "--trace", str(tmp_path / "p" / "trace.jsonl"), "--out-dir", str(tmp_path / "p" / "renders")]
    assert BLANK.prompt in (tmp_path / "p" / "prompt.txt").read_text()
    server = McpServer(setup.cmd, cwd=setup.folder / "project", log=setup.folder / "server.log")
    try:
        assert "model space" in server.instructions.lower()
        names = {t["name"] for t in server.tools}
        assert {"get_document_state", "draw_line", "render_model", "open_document"} <= names
        ok = server.call("get_document_state", {})
        assert not ok.is_error and json.loads(ok.text)["ok"] is True
        bad = server.call("draw_line", {"start": [0, 0]})
        assert bad.is_error and "[tool error]" in bad.rendered()
        unknown = server.call("no_such_tool", {})
        assert unknown.is_error
    finally:
        server.close()
    lines = [json.loads(l) for l in (tmp_path / "p" / "trace.jsonl").read_text().splitlines()]
    assert [l["tool"] for l in lines] == ["get_document_state", "draw_line"]
    assert lines[1]["ok"] is False


def test_tool_result_rendering_and_cost():
    r = ToolResult(text="x", images=[("image/png", "QUJD")])
    assert "text-only" in r.rendered(vision=False) and "text-only" not in r.rendered(vision=True)
    assert ToolResult(text="x", is_error=True).rendered().startswith("[tool error]")
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000,
             "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0}
    assert estimate_cost("claude-haiku-4-5", usage) == pytest.approx(1.0 + 0.5 + 0.1)
    assert estimate_cost("qwen3.5-9b", usage) is None


# ------------------------------------------------------------- anthropic

def anthropic_reply(content, stop="tool_use", usage=None):
    return {"content": content, "stop_reason": stop, "usage": usage or
            {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50,
             "cache_creation_input_tokens": 10}}


def test_anthropic_loop_builds_the_request_and_feeds_tool_results_back(tmp_path):
    bodies = []
    replies = iter([
        anthropic_reply([{"type": "thinking", "thinking": "", "signature": "sig"},
                         {"type": "tool_use", "id": "t1", "name": "get_document_state", "input": {}},
                         {"type": "tool_use", "id": "t2", "name": "draw_line", "input": {"start": [0, 0]}}]),
        anthropic_reply([{"type": "tool_use", "id": "t3", "name": "render_sheet", "input": {"sheet": "C-102"}}]),
        anthropic_reply([{"type": "text", "text": "Done: a line and a look."}], stop="end_turn"),
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))   # a copy: the loop keeps appending to its lists
        return next(replies)

    ep = episode(tmp_path, effort="high")
    backend = AnthropicBackend(ep.options, post=post)
    outcome = backend.run(ep)
    assert outcome.stop == "answered" and outcome.final == "Done: a line and a look."
    assert outcome.turns == 3
    assert outcome.usage == {"input_tokens": 300, "output_tokens": 60,
                             "cache_read_input_tokens": 150, "cache_creation_input_tokens": 30}
    assert outcome.cost_usd == estimate_cost("claude-haiku-4-5", outcome.usage)
    first = bodies[0]
    assert first["model"] == "claude-haiku-4-5" and first["system"] == FakeServer.instructions
    assert first["cache_control"] == {"type": "ephemeral"} and first["output_config"] == {"effort": "high"}
    assert first["tools"][1] == {"name": "draw_line", "description": "a line",
                                 "input_schema": FakeServer.tools[1]["inputSchema"]}
    assert first["messages"] == [{"role": "user", "content": "do the task"}]
    # the assistant content went back verbatim, thinking block included, then the results
    second = bodies[1]["messages"]
    assert second[1]["role"] == "assistant" and second[1]["content"][0]["type"] == "thinking"
    results = second[2]["content"]
    assert results[0] == {"type": "tool_result", "tool_use_id": "t1",
                          "content": json.dumps({"ok": True, "echo": "get_document_state", "arguments": {}})}
    assert results[1]["tool_use_id"] == "t2" and results[1]["is_error"] is True \
        and results[1]["content"].startswith("[tool error]")
    # text-only: the render is a note, no image block
    third = bodies[2]["messages"][-1]["content"][0]
    assert isinstance(third["content"], str) and "text-only" in third["content"]
    assert ep.server.calls[2] == ("render_sheet", {"sheet": "C-102"})
    roles = [m["role"] for m in ep.log]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user", "assistant"]
    assert ep.log[2]["stop_reason"] == "tool_use" and "seconds" in ep.log[2]


def test_anthropic_vision_passes_renders_as_images_and_stops_on_limits(tmp_path):
    result = ToolResult(text="look", images=[("image/png", "QUJD")])
    block = tool_result_block("t9", result, vision=True)
    assert block["content"][0]["type"] == "text" and block["content"][1] == {
        "type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}}
    assert "is_error" not in block
    # max_turns
    ep = episode(tmp_path, max_turns=2)
    backend = AnthropicBackend(ep.options, post=lambda body: anthropic_reply(
        [{"type": "tool_use", "id": "t", "name": "get_document_state", "input": {}}]))
    out = backend.run(ep)
    assert out.stop == "max_turns" and out.turns == 2 and out.final == ""
    # length and refusal
    ep = episode(tmp_path)
    out = AnthropicBackend(ep.options, post=lambda b: anthropic_reply(
        [{"type": "text", "text": "half"}], stop="max_tokens")).run(ep)
    assert out.stop == "length" and out.final == "half"
    ep = episode(tmp_path)
    out = AnthropicBackend(ep.options, post=lambda b: {
        "content": [], "stop_reason": "refusal", "usage": {},
        "stop_details": {"type": "refusal", "category": "x"}}).run(ep)
    assert out.stop == "refusal" and ep.log[-1]["stop_details"]["category"] == "x"
    # budget: already over when the loop starts
    ep = episode(tmp_path, budget=0.001)
    ep.started -= 10
    out = AnthropicBackend(ep.options, post=lambda b: pytest.fail("no request past the budget")).run(ep)
    assert out.stop == "budget" and out.turns == 0


def test_anthropic_credentials_come_from_the_environment():
    assert credentials({"ANTHROPIC_API_KEY": "sk-x"}) == {"x-api-key": "sk-x"}
    assert credentials({"ANTHROPIC_AUTH_TOKEN": "tok"}) == {
        "Authorization": "Bearer tok", "anthropic-beta": "oauth-2025-04-20"}
    with pytest.raises(RuntimeError, match="claude-code"):
        credentials({})
    assert tool_definitions(FakeServer.tools)[0]["input_schema"] == {"type": "object", "properties": {}}


def test_anthropic_retries_the_statuses_the_sdk_retries(monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import anthropic_api
    attempts = []

    def urlopen(req, timeout):
        attempts.append(json.loads(req.data))
        if len(attempts) < 3:
            raise urllib.error.HTTPError(req.full_url, 529, "overloaded", {"retry-after": "1"},
                                         io.BytesIO(b'{"error": "overloaded"}'))
        return io.BytesIO(json.dumps(anthropic_reply([], "end_turn")).encode())

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(anthropic_api.urllib.request, "urlopen",
                        lambda req, timeout: Resp(urlopen(req, timeout).read()))
    slept = []
    reply = anthropic_api.post_messages({"model": "m"}, {"x-api-key": "k"}, sleep=slept.append)
    assert reply["stop_reason"] == "end_turn" and len(attempts) == 3 and slept == [1.0, 1.0]

    def refuse(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b"bad key"))
    monkeypatch.setattr(anthropic_api.urllib.request, "urlopen", refuse)
    with pytest.raises(RuntimeError, match="401"):
        anthropic_api.post_messages({"model": "m"}, {"x-api-key": "k"}, sleep=slept.append)


# ------------------------------------------------------------ claude-code

def fake_claude(tmp_path, lines, rc=0, stderr=""):
    """A stand-in CLI: prints the given stream-json lines and exits."""
    script = tmp_path / "claude"
    script.write_text("#!/usr/bin/env python3\nimport sys, json\n"
                      f"sys.stderr.write({stderr!r})\n"
                      f"for line in {[json.dumps(l) for l in lines]!r}: print(line)\n"
                      f"open(sys.argv[0] + '.argv', 'w').write(json.dumps(sys.argv[1:]))\n"
                      f"sys.exit({rc})\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


STREAM = [
    {"type": "system", "subtype": "init", "session_id": "s1",
     "mcp_servers": [{"name": "roaddraft", "status": "connected"}]},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "a", "name": "mcp__roaddraft__get_document_state", "input": {}}]}},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "a", "content": "{\"ok\": true}"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "All done."}],
                                      "stop_reason": "end_turn"}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "All done.", "num_turns": 2,
     "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 900,
               "cache_creation_input_tokens": 0, "server_tool_use": {"web_search_requests": 0}},
     "total_cost_usd": 0.0123, "duration_ms": 4000},
]


def test_claude_code_command_and_stream_parsing(tmp_path):
    ep = episode(tmp_path, server=None, effort="medium")
    backend = ClaudeCodeBackend(ep.options, claude_bin="/x/claude")
    argv = backend.command(ep)
    assert argv[:3] == ["/x/claude", "-p", "do the task"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert "--strict-mcp-config" in argv and "--restricted" in argv and "--no-session-persistence" in argv
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--allowedTools") + 1] == "mcp__roaddraft__*"
    assert "model space" in argv[argv.index("--system-prompt") + 1].lower()
    assert argv[argv.index("--effort") + 1] == "medium" and "--append-system-prompt" not in argv
    config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
    entry = config["mcpServers"]["roaddraft"]
    assert entry["type"] == "stdio" and entry["command"] == sys.executable
    assert entry["args"][:2] == ["-m", "roaddraft.mcp.server"] and "--autosave" in entry["args"]
    assert mcp_config(["/v/roaddraft-mcp", "--doc", "x"])["mcpServers"]["roaddraft"]["args"] == ["--doc", "x"]

    out = parse_stream("\n".join(json.dumps(l) for l in STREAM), ep, "claude-haiku-4-5")
    assert out.stop == "answered" and out.final == "All done." and out.turns == 2
    assert out.usage == {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 900,
                         "cache_creation_input_tokens": 0}
    assert out.cost_usd == estimate_cost("claude-haiku-4-5", out.usage)
    assert out.extra["claude_cost_usd"] == 0.0123 and out.extra["mcp_servers"] == {"roaddraft": "connected"}
    assert [m["role"] for m in ep.log] == ["assistant", "user", "assistant"]
    # a server that did not connect, and a max-turns result
    failed = [dict(STREAM[0], mcp_servers=[{"name": "roaddraft", "status": "failed"}])]
    assert parse_stream(json.dumps(failed[0]), episode(tmp_path), "m").stop.startswith("error: the roaddraft server")
    capped = dict(STREAM[-1], subtype="error_max_turns", result="")
    assert parse_stream(json.dumps(capped), episode(tmp_path), "m").stop == "max_turns"


def test_claude_code_runs_the_cli_and_leaves_the_run_folder(tmp_path):
    bin_ = fake_claude(tmp_path, STREAM)
    options = Options(model="claude-haiku-4-5", max_turns=7, extra={"max_budget_usd": 2.5})
    backend = ClaudeCodeBackend(options, claude_bin=str(bin_))
    meta = run_probe(backend, tmp_path / "runs" / "cc" / BLANK.id, BLANK, SERVER)
    assert meta["stop"] == "answered" and meta["turns"] == 2 and meta["backend"] == "claude-code"
    folder = tmp_path / "runs" / "cc" / BLANK.id
    assert (folder / "report.txt").read_text() == "All done."
    transcript = json.loads((folder / "transcript.json").read_text())
    assert transcript["meta"]["claude_cost_usd"] == 0.0123
    assert [m["role"] for m in transcript["messages"]] == ["system", "user", "assistant", "user", "assistant"]
    argv = json.loads(Path(str(bin_) + ".argv").read_text())
    assert argv[argv.index("--max-turns") + 1] == "7" and argv[argv.index("--max-budget-usd") + 1] == "2.5"
    assert (folder / "mcp.json").exists() and (folder / "project").is_dir()
    # a second run is skipped; --force reruns
    assert run_probe(backend, folder, BLANK, SERVER)["skipped"] is True
    assert run_probe(backend, folder, BLANK, SERVER, force=True)["stop"] == "answered"


def test_claude_code_not_signed_in_is_an_error_not_a_crash(tmp_path):
    bin_ = fake_claude(tmp_path, [], rc=1, stderr="Not logged in · Please run /login\n")
    backend = ClaudeCodeBackend(Options(model="haiku"), claude_bin=str(bin_))
    meta = run_probe(backend, tmp_path / "r" / BLANK.id, BLANK, SERVER)
    assert meta["stop"].startswith("error: claude is not signed in")
    assert (tmp_path / "r" / BLANK.id / "report.txt").read_text().startswith("(no final answer")


# ---------------------------------------------------------------- openai

def openai_reply(content="", tool_calls=None, finish="stop", reasoning=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
        finish = "tool_calls"
    if reasoning:
        msg["reasoning_content"] = reasoning
    return {"choices": [{"message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 40,
                      "completion_tokens_details": {"reasoning_tokens": 30}}}


def test_openai_loop_sends_function_tools_and_keeps_reasoning_out_of_the_next_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")
    bodies = []
    replies = iter([
        openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": "draw_line", "arguments": json.dumps({"start": [0, 0], "end": [1, 1]})}}],
            reasoning="let me think"),
        openai_reply("Drew the line."),
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        return next(replies)

    ep = episode(tmp_path, model="qwen3.5-9b")
    ep.options.extra = {"base_url": "http://localhost:1234/v1/", "api_key_env": "MY_KEY"}
    backend = OpenAIBackend(ep.options, post=post)
    assert backend.headers == {"Authorization": "Bearer secret"} and backend.base_url == "http://localhost:1234/v1"
    out = backend.run(ep)
    assert out.stop == "answered" and out.final == "Drew the line." and out.turns == 2
    assert out.usage == {"input_tokens": 1000, "output_tokens": 80, "reasoning_tokens": 60}
    assert out.cost_usd is None and out.extra["reloads"] == 0
    assert bodies[0]["tools"][1]["function"]["parameters"] == FakeServer.tools[1]["inputSchema"]
    assert bodies[0]["messages"][0] == {"role": "system", "content": FakeServer.instructions}
    tool_msg = bodies[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1" and '"ok": true' in tool_msg["content"]
    assert "reasoning_content" not in bodies[1]["messages"][2] and ep.log[2]["reasoning"] == "let me think"
    assert ep.server.calls == [("draw_line", {"start": [0, 0], "end": [1, 1]})]
    assert parse_args("not json") == {"_unparsed": "not json"} and parse_args("") == {}


def test_openai_post_resamples_a_malformed_tool_call_and_reloads_on_overflow(monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import openai_compat
    attempts, reloads = [], []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(
                b'{"error":"The model produced output that does not match the expected peg-native format"}'))
        if len(attempts) == 2:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(
                b'{"error":"exceed_context_size_error"}'))
        return Resp(json.dumps(openai_reply("fine")).encode())

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", urlopen)
    guard = openai_compat.LmStudioGuard("http://localhost:1234/v1", "m", 65536)
    monkeypatch.setattr(guard, "reload", lambda: reloads.append(1))
    reply = openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                    guard=guard, sleep=lambda s: None)
    assert reply["choices"][0]["message"]["content"] == "fine"
    assert len(attempts) == 3 and reloads == [1]      # resampled once, reloaded once
    # without the guard an overflow is not retried
    attempts.clear()
    with pytest.raises(RuntimeError, match="HTTP 400"):
        openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                guard=None, sleep=lambda s: None)
    assert len(attempts) == 2


# ----------------------------------------------------------------- score

def test_measures_read_faults_recovery_and_loops_off_a_trace():
    ok = lambda tool, kind="command": {"tool": tool, "kind": kind, "ok": True}
    bad = lambda tool, msg="x": {"tool": tool, "kind": "command", "ok": False, "error": {"message": msg}}
    calls = [ok("get_document_state", "query"), bad("draw_line"), ok("draw_line"),
             bad("place_callout", "a"), bad("place_callout", "a"), bad("place_callout", "a"),
             bad("place_callout", "a"), bad("place_callout", "a"), ok("render_sheet", "query")]
    m = measures(calls)
    assert m["calls"] == 9 and m["faults"] == 6 and m["invalid_rate"] == round(6 / 9, 3)
    assert m["recovered"] == 1 and m["fault_streak"] == 5 and m["fault_loop"] is True
    assert m["commands"] == 7 and m["queries"] == 2 and m["renders"] == 1
    assert measures([])["invalid_rate"] is None


def test_score_reads_the_run_folders_back_from_disk(tmp_path):
    # a run the fake model left: the real server drew nothing useful, so the probe fails
    ep_tool = [{"type": "tool_use", "id": "t", "name": "get_document_state", "input": {}}]
    replies = iter([anthropic_reply(ep_tool), anthropic_reply([{"type": "text", "text": "done"}], "end_turn")])
    backend = AnthropicBackend(Options(model="claude-haiku-4-5"), post=lambda b: next(replies))
    run_probe(backend, tmp_path / "runs" / "h" / BLANK.id, BLANK, SERVER)
    rows = score_label(tmp_path / "runs" / "h")
    assert len(rows) == 1
    row = rows[0]
    assert row["probe"] == BLANK.id and row["passed"] is False and row["calls"] == 1
    assert row["backend"] == "anthropic" and row["stop"] == "answered" and row["turns"] == 2
    assert row["tokens"]["input_tokens"] == 200 and row["cost_usd"] is not None
    assert json.loads((tmp_path / "runs" / "h" / "scores.json").read_text())[0]["probe"] == BLANK.id
    # the CLI: score exits 1 on a failing label, and `backends` lists the three
    assert cli.main(["score", str(tmp_path / "runs" / "h")]) == 1
    assert cli.main(["backends"]) == 0
    drafts = cli.select("draft", [])
    assert drafts and all("draft" in p.tags for p in drafts) and cli.select(None, [BLANK.id]) == [BLANK]


def test_cli_run_with_the_fake_claude(tmp_path):
    bin_ = fake_claude(tmp_path, STREAM)
    rc = cli.main(["run", "--backend", "claude-code", "--model", "claude-haiku-4-5",
                   "--out", str(tmp_path / "out"), "--label", "cc", "--repeat", "2",
                   "--claude-bin", str(bin_), BLANK.id])
    assert rc == 0
    for label in ("cc-r1", "cc-r2"):
        assert (tmp_path / "out" / "runs" / label / BLANK.id / "report.txt").read_text() == "All done."
    rows = score_label(tmp_path / "out" / "runs" / "cc-r1")
    assert rows[0]["calls"] == 0 and rows[0]["detail"] == "no tool calls"   # the fake CLI never called the server
