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
from roaddraft.runners.core import IMAGE_OMITTED
from roaddraft.runners.anthropic_api import (AnthropicBackend, credentials, tool_definitions,
                                             tool_result_block)
from roaddraft.runners.claude_code import ClaudeCodeBackend, mcp_config, parse_stream
from roaddraft.runners.codex_cli import CodexBackend
from roaddraft.runners.codex_cli import Stream as CodexStream
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
    assert json.loads((tmp_path / "p" / "server.json").read_text())["cmd"][-7:] == [
        "--autosave", "--trace", str(tmp_path / "p" / "trace.jsonl"), "--out-dir", str(tmp_path / "p" / "renders"),
        "--root", str(tmp_path / "p")]
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


def test_a_relative_run_folder_still_starts_the_server(tmp_path, monkeypatch):
    # the server starts in project/, so the paths it is handed must not be relative
    monkeypatch.chdir(tmp_path)
    replies = iter([anthropic_reply([{"type": "tool_use", "id": "t", "name": "get_document_state", "input": {}}]),
                    anthropic_reply([{"type": "text", "text": "ok"}], "end_turn")])
    backend = AnthropicBackend(Options(model="claude-haiku-4-5"), post=lambda body: next(replies))
    meta = run_probe(backend, Path("out/runs/h") / BLANK.id, BLANK, SERVER)
    assert meta["stop"] == "answered" and meta["truncated_results"] == 0
    cmd = json.loads((tmp_path / "out/runs/h" / BLANK.id / "server.json").read_text())["cmd"]
    assert Path(cmd[cmd.index("--doc") + 1]).is_absolute()
    trace = (tmp_path / "out/runs/h" / BLANK.id / "trace.jsonl").read_text().splitlines()
    assert [json.loads(l)["tool"] for l in trace] == ["get_document_state"]


def test_tool_result_rendering_and_cost():
    r = ToolResult(text="x", images=[("image/png", "QUJD")])
    assert "text-only" in r.rendered(vision=False) and "text-only" not in r.rendered(vision=True)
    # the note claims nothing about the text above it: an attachment's carries no path
    assert r.rendered(vision=False) == "x\n" + IMAGE_OMITTED
    assert "path" not in IMAGE_OMITTED and "above" not in IMAGE_OMITTED
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
    assert entry["args"][-2:] == ["--root", str(ep.setup.folder)]   # held to the run folder
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


def test_claude_code_config_path_survives_a_relative_out(tmp_path, monkeypatch):
    # the CLI runs from project/, so a relative --out once sent it a path that doubled up
    monkeypatch.chdir(tmp_path)
    ep = episode(tmp_path)
    ep.folder = Path("run")
    argv = ClaudeCodeBackend(ep.options, claude_bin="/x/claude").command(ep)
    config = Path(argv[argv.index("--mcp-config") + 1])
    assert config.is_absolute() and config.exists()


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


# ---------------------------------------------------------------- codex

def fake_codex(tmp_path, lines, rc=0, stderr="", sleep=0.0):
    """A stand-in ``codex``: prints the given --json lines and exits; a
    ``{"__sleep__": s}`` among them pauses, the way a model turn does."""
    script = tmp_path / "codex"
    script.write_text("#!/usr/bin/env python3\nimport sys, json, time\n"
                      "if sys.argv[1:] == ['--version']: print('codex-cli 9.9.9'); sys.exit(0)\n"
                      f"open(sys.argv[0] + '.argv', 'w').write(json.dumps(sys.argv[1:]))\n"
                      f"sys.stderr.write({stderr!r})\n"
                      f"for line in {[json.dumps(l) for l in lines]!r}:\n"
                      "    pause = json.loads(line).get('__sleep__')\n"
                      "    time.sleep(pause) if pause else print(line, flush=True)\n"
                      f"time.sleep({sleep})\n"
                      f"sys.exit({rc})\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


CODEX_CALL = {"type": "item.completed", "item": {
    "id": "item_1", "type": "mcp_tool_call", "server": "roaddraft", "tool": "get_document_state",
    "arguments": {}, "result": {"content": [{"type": "text", "text": "{\"ok\": true}"}]},
    "error": None, "status": "completed"}}
CODEX_STREAM = [
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "look first"}},
    CODEX_CALL,
    {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": "All done."}},
    {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 900,
                                         "output_tokens": 50, "reasoning_output_tokens": 20}},
]


def test_codex_command_pares_the_harness_back(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/pinned/src")
    ep = episode(tmp_path, model="gpt-6-astra", effort="medium")
    argv = CodexBackend(ep.options, codex_bin="/x/codex").command(ep)
    assert argv[:2] == ["/x/codex", "exec"] and argv[-1] == "do the task"
    for flag in ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules"):
        assert flag in argv
    assert argv[argv.index("--model") + 1] == "gpt-6-astra" and argv[argv.index("--sandbox") + 1] == "read-only"
    assert {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"} >= {"shell_tool", "plugins", "memories"}
    settings = dict(argv[i + 1].split("=", 1) for i, a in enumerate(argv) if a == "-c")
    assert settings["approval_policy"] == '"never"' and settings["model_reasoning_effort"] == '"medium"'
    assert settings["include_environment_context"] == "false" and settings["project_doc_max_bytes"] == "0"
    assert settings["mcp_servers.roaddraft.default_tools_approval_mode"] == '"approve"'
    assert json.loads(settings["mcp_servers.roaddraft.command"]) == sys.executable
    args = json.loads(settings["mcp_servers.roaddraft.args"])
    assert args[:2] == ["-m", "roaddraft.mcp.server"] and "--autosave" in args
    assert args[-2:] == ["--root", str(ep.setup.folder)]   # held to the run folder
    assert settings["mcp_servers.roaddraft.env"] == '{PYTHONPATH = "/pinned/src"}'
    instructions = Path(json.loads(settings["model_instructions_file"]))
    assert instructions.is_absolute() and "model space" in instructions.read_text().lower()


def test_codex_stream_becomes_the_transcript(tmp_path):
    e = episode(tmp_path)
    log = e.log
    stream = CodexStream(e)
    for event in CODEX_STREAM:
        stream.feed(json.dumps(event))
    out = stream.outcome()
    assert out.stop == "answered" and out.final == "All done." and out.cost_usd is None
    assert out.usage == {"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 50,
                         "reasoning_output_tokens": 20}
    assert out.extra["thread_id"] == "t1" and out.extra["tool_calls"] == 1 and out.turns == 2
    assert [m["role"] for m in log] == ["assistant", "user", "assistant"]
    assert [b["type"] for b in log[0]["content"]] == ["thinking", "tool_use"]
    assert log[1]["content"][0] == {"type": "tool_result", "tool_use_id": "item_1",
                                    "content": "{\"ok\": true}", "is_error": False}
    # a refused call is an error result; an account limit is the infrastructure's stop
    refused = dict(CODEX_CALL["item"], result=None, error={"message": "requires approval"})
    stream = CodexStream(e)
    stream.feed(json.dumps({"type": "item.completed", "item": refused}))
    stream.feed(json.dumps({"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}))
    limited = stream.outcome()
    assert log[-1]["content"][0]["is_error"] and log[-1]["content"][0]["content"] == "[tool error] requires approval"
    assert limited.stop.startswith("error: account limit")


def test_codex_runs_the_cli_and_leaves_the_run_folder(tmp_path):
    bin_ = fake_codex(tmp_path, CODEX_STREAM)
    backend = CodexBackend(Options(model="gpt-6-luna", effort="medium"), codex_bin=str(bin_))
    meta = run_probe(backend, tmp_path / "runs" / "cx" / BLANK.id, BLANK, SERVER)
    assert meta["stop"] == "answered" and meta["backend"] == "codex" and meta["effort"] == "medium"
    assert meta["codex_version"] == "codex-cli 9.9.9"
    folder = tmp_path / "runs" / "cx" / BLANK.id
    assert (folder / "report.txt").read_text() == "All done."
    transcript = json.loads((folder / "transcript.json").read_text())
    assert [m["role"] for m in transcript["messages"]] == ["system", "user", "assistant", "user", "assistant"]
    assert (folder / "instructions.md").exists() and (folder / "codex.log").exists()


def test_codex_stops_past_the_turn_cap_and_the_budget(tmp_path):
    # five responses, a pause before each: past a cap of three turns
    many = [CODEX_STREAM[0]] + [{"__sleep__": 0.3}, CODEX_CALL] * 5
    capped = CodexBackend(Options(model="m", max_turns=3), codex_bin=str(fake_codex(tmp_path, many, sleep=30)))
    assert run_probe(capped, tmp_path / "a" / BLANK.id, BLANK, SERVER)["stop"] == "max_turns"
    # fifty calls made at once are one turn, not fifty (GPT-6-Astra, stationing, 2026-10-14)
    burst = [CODEX_STREAM[0]] + [CODEX_CALL] * 50 + [{"__sleep__": 0.3}] + CODEX_STREAM[-2:]
    wide = CodexBackend(Options(model="m", max_turns=3), codex_bin=str(fake_codex(tmp_path, burst)))
    meta = run_probe(wide, tmp_path / "w" / BLANK.id, BLANK, SERVER)
    assert meta["stop"] == "answered" and meta["tool_calls"] == 50 and meta["turns"] == 2
    assert (tmp_path / "w" / BLANK.id / "codex.jsonl").read_text().count("mcp_tool_call") == 50
    slow = CodexBackend(Options(model="m", budget=1), codex_bin=str(fake_codex(tmp_path, [], sleep=30)))
    assert run_probe(slow, tmp_path / "b" / BLANK.id, BLANK, SERVER)["stop"] == "budget"
    broken = CodexBackend(Options(model="m"),
                          codex_bin=str(fake_codex(tmp_path, [], rc=1, stderr="Not signed in\n")))
    assert run_probe(broken, tmp_path / "c" / BLANK.id, BLANK, SERVER)["stop"] == \
        "error: codex exited 1: Not signed in"


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


def chunk(content=None, reasoning=None, calls=None, finish=None) -> dict:
    """One chat.completion.chunk, as LM Studio streams it."""
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    if calls is not None:
        delta["tool_calls"] = calls
    return {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def call_delta(index, name=None, arguments="", id=None) -> dict:
    fn = {"arguments": arguments}
    if name is not None:
        fn["name"] = name
    out = {"index": index, "type": "function", "function": fn}
    if id is not None:
        out["id"] = id
    return out


USAGE = {"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 12,
                                  "completion_tokens_details": {"reasoning_tokens": 5}}}


def sse(*chunks, done=True):
    """The lines of a server-sent-events body."""
    lines = []
    for c in chunks:
        lines += [f"data: {json.dumps(c)}\n".encode(), b"\n"]
    return lines + ([b"data: [DONE]\n", b"\n"] if done else [])


class Stream:
    """What urlopen hands back for a streamed request: its lines, then closed."""

    def __init__(self, lines):
        self.lines = iter(lines)

    def __iter__(self):
        return self.lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


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
    assert out.cost_usd is None and out.extra["reloads"] == 0 and "extra_body" not in out.extra
    assert set(bodies[0]) == {"model", "messages", "tools"}
    assert bodies[0]["tools"][1]["function"]["parameters"] == FakeServer.tools[1]["inputSchema"]
    assert bodies[0]["messages"][0] == {"role": "system", "content": FakeServer.instructions}
    tool_msg = bodies[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1" and '"ok": true' in tool_msg["content"]
    assert not {"reasoning_content", "reasoning"} & set(bodies[1]["messages"][2])
    assert ep.log[2]["reasoning"] == "let me think" and "send_reasoning" not in out.extra
    assert ep.server.calls == [("draw_line", {"start": [0, 0], "end": [1, 1]})]
    assert parse_args("not json") == {"_unparsed": "not json"} and parse_args("") == {}


def test_openai_sends_the_extra_body_every_turn_and_records_it(tmp_path, capsys):
    bodies = []
    replies = iter([
        openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": "get_document_state", "arguments": "{}"}}]),
        openai_reply("Done."),
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        return next(replies)

    sampling = {"top_p": 0.95, "top_k": 20, "presence_penalty": 1.5, "model": "not-this-one"}
    ep = episode(tmp_path, model="Qwen/Qwen3.5-9B")
    ep.options.extra = {"base_url": "https://api.runpod.ai/v2/abc/openai/v1", "extra_body": sampling}
    out = OpenAIBackend(ep.options, post=post).run(ep)
    assert out.stop == "answered" and len(bodies) == 2
    for body in bodies:     # the sampling rides along; it cannot replace the model, messages or tools
        assert body["top_k"] == 20 and body["presence_penalty"] == 1.5 and body["model"] == "Qwen/Qwen3.5-9B"
        assert body["tools"] and body["messages"][0]["role"] == "system"
    assert out.extra["extra_body"] == sampling and out.extra["base_url"].startswith("https://api.runpod.ai/")
    assert cli.json_object('{"top_k": 20}') == {"top_k": 20}
    for bad in ("[1, 2]", "top_k=20"):
        with pytest.raises(cli.argparse.ArgumentTypeError):
            cli.json_object(bad)


def test_openai_sends_a_tool_call_turns_reasoning_back_when_asked(tmp_path, monkeypatch):
    def call(cid, name, arguments="{}"):
        return [{"id": cid, "type": "function", "function": {"name": name, "arguments": arguments}}]

    bodies = []
    replies = iter([
        openai_reply(tool_calls=call("c1", "get_document_state"), reasoning="read the state first"),
        {"choices": [{"message": {"role": "assistant", "content": "", "reasoning": "now the line",  # vLLM's name
                                  "tool_calls": call("c2", "draw_line", json.dumps({"start": [0, 0], "end": [1, 1]}))},
                      "finish_reason": "tool_calls"}]},
        openai_reply(tool_calls=call("c3", "get_document_state")),     # no thinking, nothing to send
        openai_reply("Drew the line.", reasoning="done"),
    ])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        return next(replies)

    ep = episode(tmp_path, model="openai/gpt-oss-20b")
    ep.options.extra = {"send_reasoning": True}
    out = OpenAIBackend(ep.options, post=post).run(ep)
    assert out.stop == "answered" and out.turns == 4 and out.extra["send_reasoning"] is True
    sent = [m for m in bodies[-1]["messages"] if m["role"] == "assistant"]
    assert [m.get("reasoning") for m in sent] == ["read the state first", "now the line", None]
    assert all("reasoning_content" not in m for m in sent)
    assert bodies[1]["messages"][2]["reasoning"] == "read the state first"  # from the next turn on
    assert [r.get("reasoning") for r in ep.log if r["role"] == "assistant"] == \
        ["read the state first", "now the line", None, "done"]

    seen = []
    monkeypatch.setattr(cli, "run_probe", lambda backend, *a, **k: seen.append(backend) or {})
    for flag in (["--send-reasoning"], []):
        assert cli.main(["run", "--backend", "openai", "--model", "openai/gpt-oss-20b", "--out", str(tmp_path / "o"),
                         "--label", "g", *flag, BLANK.id]) == 0
    assert [b.send_reasoning for b in seen] == [True, False]


def test_openai_post_resamples_a_malformed_tool_call_and_reloads_on_overflow(monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import openai_compat
    attempts, reloads = [], []

    def urlopen(req, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(
                b'{"error":"The model produced output that does not match the expected peg-native format"}'))
        if len(attempts) == 2:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(
                b'{"error":"exceed_context_size_error"}'))
        return Stream(sse(chunk(content="fine"), chunk(finish="stop"), USAGE))

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", urlopen)
    guard = openai_compat.LmStudioGuard("http://localhost:1234/v1", "m", 65536)
    monkeypatch.setattr(guard, "reload", lambda: reloads.append(1))
    monkeypatch.setattr(guard, "loaded_context", lambda: 16384)   # LM Studio's own reload, at its default
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


def test_a_streamed_turn_is_assembled_by_index_with_its_reasoning_and_usage():
    from roaddraft.runners.openai_compat import read_stream
    lines = sse(chunk(reasoning="let me "), chunk(reasoning="think"), chunk(content="On it."),
                chunk(calls=[call_delta(0, "draw_line", '{"start": [0, ', id="c1")]),
                chunk(calls=[call_delta(1, "get_document_state", "{}", id="c2")]),
                chunk(calls=[call_delta(0, arguments='0], "end": [1, 1]}')]),
                chunk(finish="tool_calls"), USAGE)
    reply = read_stream(lines, t0=0.0, clock=lambda: 1.0)
    choice = reply["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    msg = choice["message"]
    assert msg["content"] == "On it." and msg["reasoning_content"] == "let me think"
    assert [c["id"] for c in msg["tool_calls"]] == ["c1", "c2"]
    assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {"start": [0, 0], "end": [1, 1]}
    assert msg["tool_calls"][1]["function"] == {"name": "get_document_state", "arguments": "{}"}
    assert reply["usage"] == USAGE["usage"]
    # a server that leaves the index out: a new id starts a call, no id goes on with the last
    lines = sse(chunk(calls=[{"id": "a", "function": {"name": "x", "arguments": "{"}}]),
                chunk(calls=[{"function": {"arguments": "}"}}]),
                chunk(calls=[{"id": "b", "function": {"name": "y", "arguments": "{}"}}]), chunk(finish="tool_calls"))
    calls = read_stream(lines, 0.0, clock=lambda: 1.0)["choices"][0]["message"]["tool_calls"]
    assert [(c["id"], c["function"]["arguments"]) for c in calls] == [("a", "{}"), ("b", "{}")]


def test_a_turn_ends_when_the_model_starts_a_call_past_the_cap():
    from roaddraft.runners.openai_compat import CALL_CAP, read_stream
    assert CALL_CAP == 4
    # GLM-4.6V-Flash on width-dims: one call after another, none waiting for a result
    names = ["get_document_state", "list_sheets", "render_sheet", "list_alignments", "place_text", "place_text"]
    stream = iter(sse(*[chunk(calls=[call_delta(i, n, "{}", id=f"c{i}")]) for i, n in enumerate(names)],
                      chunk(finish="tool_calls"), USAGE))
    reply = read_stream(stream, 0.0, clock=lambda: 1.0)
    choice = reply["choices"][0]
    assert choice["finish_reason"] == "call_cap"
    assert [c["function"]["name"] for c in choice["message"]["tool_calls"]] == names[:4]
    # the rest of the stream was never read, and a cut turn's usage is the chunk count, marked
    assert next(stream, None) is not None
    assert reply["usage"] == {"completion_tokens": 5, "estimated": True}


def test_a_turn_past_the_turn_limit_ends_with_what_had_come():
    from roaddraft.runners.openai_compat import read_stream
    ticks = iter([100.0, 1901.0])          # the second chunk comes in past the limit
    lines = sse(chunk(reasoning="the PC is at "), chunk(reasoning="station"), chunk(content="never read"),
                chunk(finish="stop"), USAGE)
    reply = read_stream(lines, t0=0.0, turn_limit=1800, clock=lambda: next(ticks))
    choice = reply["choices"][0]
    assert choice["finish_reason"] == "turn_limit"
    assert choice["message"] == {"role": "assistant", "content": "", "reasoning_content": "the PC is at station"}
    assert reply["usage"]["estimated"] is True


def test_post_chat_streams_and_retries_a_stalled_stream(monkeypatch):
    import socket
    from roaddraft.runners import openai_compat
    bodies, slept = [], []

    class Stalled(Stream):
        def __iter__(self):
            yield sse(chunk(content="hal"))[0]
            raise socket.timeout("timed out")     # what a stalled read raises on Python 3.9

    def urlopen(req, timeout):
        bodies.append(json.loads(req.data))
        assert timeout == openai_compat.TURN_LIMIT
        if len(bodies) == 1:
            return Stalled([])
        return Stream(sse(chunk(content="whole"), chunk(finish="stop"), USAGE))

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", urlopen)
    reply = openai_compat.post_chat("http://x/v1/chat/completions", {"model": "m", "messages": []}, {},
                                    sleep=slept.append)
    assert reply["choices"][0]["message"]["content"] == "whole" and slept == [15]
    assert bodies[0]["stream"] is True and bodies[0]["stream_options"] == {"include_usage": True}
    # an error inside the stream: Llama's unparseable call is sampled again, anything else is the end
    streams = iter([Stream(sse({"error": {"message": "Engine protocol predict stream returned an error: "
                                          "The model produced output that does not match the expected "
                                          "peg-native format"}})),
                    Stream(sse({"error": {"message": "terminated"}}))])
    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", lambda req, timeout: next(streams))
    with pytest.raises(RuntimeError, match="stream error: .*terminated"):
        openai_compat.post_chat("http://x/v1/chat/completions", {"model": "m"}, {}, sleep=slept.append)


def test_an_engine_that_dies_mid_stream_is_reloaded_when_it_took_the_model(monkeypatch):
    from roaddraft.runners import openai_compat
    # Qwen3.5-9B on edge-c102, 2026-10-08 10:06: "terminated" in prompt processing, the model unloaded
    streams = iter([Stream(sse({"error": {"message": "terminated"}})),
                    Stream(sse(chunk(content="back"), chunk(finish="stop"), USAGE))])
    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", lambda req, timeout: next(streams))
    guard = openai_compat.LmStudioGuard("http://localhost:1234/v1", "qwen/qwen3.5-9b", 65536)
    reloads = []
    monkeypatch.setattr(guard, "reload", lambda: reloads.append(1))
    monkeypatch.setattr(guard, "loaded_context", lambda: 0)
    reply = openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                    guard=guard, sleep=lambda s: None)
    assert reply["choices"][0]["message"]["content"] == "back" and reloads == [1]
    # pc-by-station, 2026-10-08 19:48: "terminated" with the model still listed at the run's
    # context, then "Model is unloaded." on the next request. Ask again, then reload.
    streams = iter([Stream(sse({"error": {"message": "terminated"}})),
                    Stream(sse({"error": {"message": "Model is unloaded."}})),
                    Stream(sse(chunk(content="again"), chunk(finish="stop"), USAGE))])
    contexts = iter([65536, 0])
    monkeypatch.setattr(guard, "loaded_context", lambda: next(contexts))
    reply = openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                    guard=guard, sleep=lambda s: None)
    assert reply["choices"][0]["message"]["content"] == "again" and reloads == [1, 1]
    # an engine that keeps dying still ends the episode once the attempts run out
    streams = iter([Stream(sse({"error": {"message": "terminated"}})) for _ in range(4)])
    monkeypatch.setattr(guard, "loaded_context", lambda: 65536)
    with pytest.raises(RuntimeError, match="stream error"):
        openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                guard=guard, sleep=lambda s: None)


def test_a_model_reloaded_from_the_lm_studio_window_is_waited_for_not_given_up_on(monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import openai_compat
    # 2026-10-08 22:30: the model reloaded by hand ended seven probes in 27 s with these three
    streams = iter([Stream(sse({"error": {"message": "Model unloaded by user or API request."}})),
                    Stream(sse({"error": {"message": "Instance does not exist or is not LLM."}})),
                    Stream(sse(chunk(content="back"), chunk(finish="stop"), USAGE))])
    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", lambda req, timeout: next(streams))
    guard = openai_compat.LmStudioGuard("http://localhost:1234/v1", "qwen/qwen3.5-9b", 65536)
    reloads = []
    monkeypatch.setattr(guard, "reload", lambda: reloads.append(1))
    monkeypatch.setattr(guard, "loaded_context", lambda: 0)
    reply = openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                    guard=guard, sleep=lambda s: None)
    assert reply["choices"][0]["message"]["content"] == "back" and reloads == [1, 1]
    # and a load that failed: "Failed to load model ... Engine protocol startup was aborted."
    failed = b'{"error": {"message": "Failed to load model \\"qwen/qwen3.5-9b\\". Error: Engine protocol startup was aborted."}}'
    calls = []

    def urlopen(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(failed))
        return Stream(sse(chunk(content="loaded"), chunk(finish="stop"), USAGE))
    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", urlopen)
    reply = openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                    guard=guard, sleep=lambda s: None)
    assert reply["choices"][0]["message"]["content"] == "loaded" and reloads == [1, 1, 1]


def test_openai_runs_the_first_four_calls_of_a_cut_turn(tmp_path, monkeypatch):
    from roaddraft.runners import openai_compat
    first = [chunk(reasoning="go")] + [
        chunk(calls=[call_delta(i, "get_document_state", "{}", id=f"c{i}")]) for i in range(7)]
    streams = iter([Stream(sse(*first, chunk(finish="tool_calls"), USAGE)),
                    Stream(sse(chunk(content="Looked six ways."), chunk(finish="stop"), USAGE))])
    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", lambda req, timeout: next(streams))
    ep = episode(tmp_path, model="glm-4.6v-flash")
    out = OpenAIBackend(ep.options).run(ep)
    assert out.stop == "answered" and out.final == "Looked six ways." and out.turns == 2
    assert len(ep.server.calls) == 4
    assert out.extra["cut_turns"] == 1 and out.extra["usage_estimated_turns"] == 1
    cut = ep.log[2]
    assert cut["finish_reason"] == "call_cap" and cut["usage_estimated"] is True and len(cut["tool_calls"]) == 4
    assert [m["tool_call_id"] for m in ep.log[3:7]] == ["c0", "c1", "c2", "c3"]
    # estimated output (the chunk count, the cutting chunk too) plus the real usage of the second turn
    assert out.usage == {"input_tokens": 900, "output_tokens": 6 + 12, "reasoning_tokens": 5}


def test_openai_stops_at_the_turn_limit_and_keeps_the_partial_turn(tmp_path):
    partial = {"choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "hmm",
                                        "tool_calls": [{"id": "c0", "type": "function", "function": {
                                            "name": "draw_line", "arguments": '{"start": [0'}}]},
                            "finish_reason": "turn_limit"}],
               "usage": {"completion_tokens": 9000, "estimated": True}}
    ep = episode(tmp_path, model="glm-4.6v-flash")
    out = OpenAIBackend(ep.options, post=lambda body: partial).run(ep)
    assert out.stop == "turn_limit" and out.turns == 1 and out.final == ""
    assert ep.server.calls == []               # a half-written call is not run
    assert ep.log[-1]["finish_reason"] == "turn_limit" and ep.log[-1]["reasoning"] == "hmm"
    assert ep.log[-1]["tool_calls"][0]["function"]["arguments"] == '{"start": [0'


L2_OVERFLOW = (b'{"error":"Engine protocol predict request returned 400: {\\"error\\":{\\"code\\":400,'
               b'\\"message\\":\\"request (467928 tokens) exceeds the available context size (65536 tokens), '
               b'try increasing it\\",\\"type\\":\\"exceed_context_size_error\\"}}"}')


def test_a_request_over_the_loaded_context_stops_the_probe(tmp_path, monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import openai_compat
    attempts, reloads = [], []

    def urlopen(req, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(L2_OVERFLOW))

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", urlopen)
    guard = openai_compat.LmStudioGuard("http://localhost:1234/v1", "qwen/qwen3.5-9b", 65536)
    monkeypatch.setattr(guard, "reload", lambda: reloads.append(1))
    monkeypatch.setattr(guard, "loaded_context", lambda: 65536)
    with pytest.raises(openai_compat.ContextFull, match="467928 tokens"):
        openai_compat.post_chat("http://localhost:1234/v1/chat/completions", {"model": "m"}, {},
                                guard=guard, sleep=lambda s: None)
    assert attempts == [1] and reloads == []    # no reload: it cannot fit
    # the backend: the probe stops with "context" and keeps what came before
    replies = iter([openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {
        "name": "get_document_state", "arguments": "{}"}}])])

    def post(body):
        reply = next(replies, None)
        if reply is None:
            raise openai_compat.ContextFull("request (467928 tokens) exceeds the available context size")
        return reply

    ep = episode(tmp_path, model="qwen/qwen3.5-9b")
    out = OpenAIBackend(ep.options, post=post).run(ep)
    assert out.stop == "context" and out.turns == 1 and ep.server.calls == [("get_document_state", {})]
    assert "467928" in out.extra["context_error"] and ep.log[-1]["role"] == "tool"


def test_type_lists_are_rewritten_as_anyof():
    from roaddraft.api.session import Session
    from roaddraft.mcp.server import tool_definitions
    from roaddraft.runners.openai_compat import function_tools, rewrite_type_lists
    schema = {"type": "object", "properties": {
        "offsets": {"type": "array", "items": {"type": ["number", "string"], "description": "ft or '12R'"}},
        "scale": {"type": ["string", "number", "null"]}, "name": {"type": "string"}}}
    assert rewrite_type_lists(schema) == {"type": "object", "properties": {
        "offsets": {"type": "array", "items": {"description": "ft or '12R'",
                                                "anyOf": [{"type": "number"}, {"type": "string"}]}},
        "scale": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "null"}]},
        "name": {"type": "string"}}}
    assert schema["properties"]["scale"]["type"] == ["string", "number", "null"]   # not changed in place

    def type_lists(s):
        if isinstance(s, dict):
            return isinstance(s.get("type"), list) or any(type_lists(v) for v in s.values())
        return isinstance(s, list) and any(type_lists(v) for v in s)

    tools = tool_definitions(Session())
    listed = {t["name"] for t in tools if type_lists(t["inputSchema"])}
    assert {"draw_offset", "annotate_stationing"} <= listed
    rewritten = function_tools(tools, rewrite=True)
    assert not any(type_lists(t["function"]["parameters"]) for t in rewritten)
    changed = {t["name"] for t, r in zip(tools, rewritten) if r["function"]["parameters"] != t["inputSchema"]}
    assert changed == listed
    assert function_tools(tools)[0]["function"]["parameters"] is tools[0]["inputSchema"]


def test_openai_rewrites_the_type_lists_when_the_template_refuses_them(tmp_path, monkeypatch):
    import io
    import urllib.error
    from roaddraft.runners import openai_compat
    refusal = b'{"error":"Error rendering prompt with jinja template: NotImplemented: map: filter-mapping not implemented"}'
    # post_chat: refused at once, whatever the status and whether before or inside the stream
    for raise_it in (lambda req: (_ for _ in ()).throw(
                         urllib.error.HTTPError(req.full_url, 500, "bad", {}, io.BytesIO(refusal))),
                     lambda req: Stream(sse({"error": json.loads(refusal)["error"]}))):
        attempts = []
        monkeypatch.setattr(openai_compat.urllib.request, "urlopen",
                            lambda req, timeout: attempts.append(1) or raise_it(req))
        with pytest.raises(openai_compat.ToolsRefused):
            openai_compat.post_chat("http://x/v1/chat/completions", {"model": "m"}, {},
                                    sleep=lambda s: pytest.fail("no retry for a refusal"))
        assert attempts == [1]
    # the backend: the same turn again with anyOf, and every turn after, for the rest of the run
    server = FakeServer()
    server.tools = FakeServer.tools + [{"name": "draw_offset", "description": "an offset", "inputSchema": {
        "type": "object", "properties": {"offsets": {"type": "array", "items": {"type": ["number", "string"]}}}}}]
    bodies = []
    replies = iter([openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {
        "name": "get_document_state", "arguments": "{}"}}]), openai_reply("done"), openai_reply("again")])

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        if "anyOf" not in json.dumps(body["tools"]):
            raise openai_compat.ToolsRefused(refusal.decode())
        return next(replies)

    ep = episode(tmp_path, server=server, model="google/gemma-4-e4b")
    backend = OpenAIBackend(ep.options, post=post)
    out = backend.run(ep)
    assert out.stop == "answered" and out.turns == 2 and out.extra["type_lists_rewritten"] is True
    assert len(bodies) == 3 and bodies[1]["messages"] == bodies[0]["messages"]
    assert bodies[2]["tools"][3]["function"]["parameters"]["properties"]["offsets"]["items"] == {
        "anyOf": [{"type": "number"}, {"type": "string"}]}
    ep2 = episode(tmp_path / "2", server=server, model="google/gemma-4-e4b")
    assert backend.run(ep2).final == "again" and len(bodies) == 4    # no second refusal
    # a template that refuses the rewrite too is an error, not a loop
    ep3 = episode(tmp_path / "3", model="m")
    stubborn = OpenAIBackend(ep3.options, post=lambda body: (_ for _ in ()).throw(openai_compat.ToolsRefused("x")))
    with pytest.raises(openai_compat.ToolsRefused):
        stubborn.run(ep3)


def test_a_tool_result_past_the_cap_is_cut_for_every_backend(tmp_path):
    from roaddraft.runners.core import RESULT_CAP, cap_text
    assert RESULT_CAP == 30000
    assert cap_text("short") == ("short", False)
    cut, was = cap_text("y" * 30010)
    assert was and cut == "y" * 30000 + "\n[output truncated: the first 30000 of 30010 characters are shown]"
    # a stand-in server whose one tool answers like get_model_state on the L-2 start
    script = tmp_path / "fake_mcp.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if 'id' not in msg:\n"
        "        continue\n"
        "    if msg['method'] == 'initialize':\n"
        "        result = {'instructions': 'fake', 'capabilities': {}}\n"
        "    elif msg['method'] == 'tools/list':\n"
        "        result = {'tools': [{'name': 'get_model_state', 'description': 'all of it',\n"
        "                             'inputSchema': {'type': 'object', 'properties': {}}}]}\n"
        "    else:\n"
        "        result = {'content': [{'type': 'text', 'text': 'z' * 748312}]}\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result}), flush=True)\n")
    replies = iter([openai_reply(tool_calls=[{"id": "c1", "type": "function", "function": {
        "name": "get_model_state", "arguments": '{"include_references": true}'}}]), openai_reply("Read it.")])
    sent = []
    backend = OpenAIBackend(Options(model="qwen/qwen3.5-9b"), post=lambda body: sent.append(
        json.loads(json.dumps(body))) or next(replies))
    meta = run_probe(backend, tmp_path / "runs" / "q" / BLANK.id, BLANK, [sys.executable, str(script)])
    assert meta["stop"] == "answered" and meta["truncated_results"] == 1
    shown = sent[1]["messages"][-1]["content"]
    assert len(shown) < 30100 and shown.endswith("[output truncated: the first 30000 of 748312 characters are shown]")
    # the Anthropic backend reads through the same server, so it sees the same cut
    replies = iter([anthropic_reply([{"type": "tool_use", "id": "t", "name": "get_model_state", "input": {}}]),
                    anthropic_reply([{"type": "text", "text": "ok"}], "end_turn")])
    sent.clear()
    backend = AnthropicBackend(Options(model="claude-haiku-4-5"), post=lambda body: sent.append(
        json.loads(json.dumps(body))) or next(replies))
    meta = run_probe(backend, tmp_path / "runs" / "h" / BLANK.id, BLANK, [sys.executable, str(script)])
    assert meta["truncated_results"] == 1
    assert sent[1]["messages"][-1]["content"][0]["content"].endswith("characters are shown]")


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
    # scope: the alignment and its centerline were asked for, neither is there;
    # and the report, "done", claims what the check contradicts
    assert (row["items_done"], row["items_asked"]) == (0, 2)
    assert row["items_missed"] == ["the alignment MAIN-ST", "its centerline on align_MAIN"]
    assert row["claims"]["false_done"] and row["claims"]["false_items"] == 2
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


def test_cli_run_stops_at_an_account_limit_and_leaves_the_probe_to_rerun(tmp_path):
    limited = [CODEX_STREAM[0], {"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}]
    bin_ = fake_codex(tmp_path, limited, rc=1)
    second = next(p for p in tasks.PROBES if p.start == "blank" and p.id != BLANK.id)
    rc = cli.main(["run", "--backend", "codex", "--model", "gpt-6-luna", "--out", str(tmp_path / "out"),
                   "--label", "cx", "--codex-bin", str(bin_), BLANK.id, second.id])
    assert rc == 3
    assert not (tmp_path / "out" / "runs" / "cx" / BLANK.id).exists()
    assert not (tmp_path / "out" / "runs" / "cx" / second.id).exists()
