"""The CLI route for the eval harness (eval plan section 4.4, Track D's
frontier route): a headless CLI runs the episode with the harness as its MCP
server.  Every test runs on a stand-in ``claude`` / ``codex`` written here --
a real MCP client that starts the bridge, lists its tools and calls them over
stdio, and prints the vendor's event stream -- so the whole route is
exercised, socket, bridge and loop, and nothing touches a subscription.

The oracle through the route scores 100: the harness loses no points to the
bridge, whichever CLI drives it."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from roaddraft.eval import prompts
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import CLIAgent, LLMAgent
from roaddraft.eval.agents.cli import Link, content_blocks, mcp_tool
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import EpisodeConfig, run_episode
from roaddraft.eval.providers import CLI_PROVIDERS, PROVIDERS, FakeProvider, make
from roaddraft.eval.providers.claude_code import ClaudeCodeProvider, ClaudeStream
from roaddraft.eval.providers.cli import BRIDGE, CLIProvider
from roaddraft.eval.providers.codex import CodexProvider, CodexStream, usage as codex_usage
from roaddraft.eval.providers.fake import turn
from roaddraft.eval.runner import Cell, RunSpec, run_cell
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.reference import solution_commands

DEV = tasksets.load("d1-dev")["tasks"]

FAKE = r'''#!%(python)s
"""A stand-in headless CLI: claude when called with -p, codex when with exec."""
import json, os, subprocess, sys, time

def main():
    argv = sys.argv[1:]
    if argv == ["--version"]:
        print("fake-cli 1.0")
        return 0
    mode = os.environ.get("FAKE_CLI_MODE", "script")
    if argv and argv[0] == "exec":
        vendor = "codex"
        settings = {argv[i + 1].split("=", 1)[0]: argv[i + 1].split("=", 1)[1]
                    for i, a in enumerate(argv) if a == "-c"}
        task = argv[-1]
        command = [json.loads(settings["mcp_servers.roaddraft.command"])] + json.loads(settings["mcp_servers.roaddraft.args"])
        system = open(json.loads(settings["model_instructions_file"])).read()
    else:
        vendor = "claude"
        task = argv[argv.index("-p") + 1]
        entry = json.load(open(argv[argv.index("--mcp-config") + 1]))["mcpServers"]["roaddraft"]
        command = [entry["command"]] + entry["args"]
        system = argv[argv.index("--system-prompt") + 1]
    seen = {"vendor": vendor, "argv": argv, "task": task, "system": system, "cwd": os.getcwd(),
            "cwd_files": sorted(os.listdir(os.getcwd())), "model": argv[argv.index("--model") + 1]}
    if mode == "nologin":
        sys.stderr.write("Not logged in \xc2\xb7 Please run /login\n")
        return 1
    if mode == "hang":
        time.sleep(float(os.environ.get("FAKE_CLI_HANG", "30")))
        return 0
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    n, replies = [0], {}
    def send(method, params=None, mid=True):
        msg = {"jsonrpc": "2.0", "method": method}
        if mid:
            n[0] += 1
            msg["id"] = n[0]
        if params is not None:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        return n[0]
    def read(mid):
        while mid not in replies:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit("the bridge closed")
            reply = json.loads(line)
            replies[reply.get("id")] = reply
        return replies.pop(mid)
    init = read(send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "fake", "version": "1"}}))
    send("notifications/initialized", mid=False)
    tools = read(send("tools/list"))["result"]["tools"]
    seen["init"] = init["result"]
    seen["tools"] = [t["name"] for t in tools]
    seen["schemas"] = {t["name"]: t["inputSchema"] for t in tools[:2]}
    script = os.environ.get("FAKE_CLI_SCRIPT")
    calls = json.load(open(script)) if script else [["get_document_state", {"detail": "summary"}], ["submit", {"note": "done"}]]
    if mode == "nosubmit":
        calls = [c for c in calls if c[0] != "submit"]
    out = sys.stdout
    def emit(event):
        out.write(json.dumps(event) + "\n")
        out.flush()
    if vendor == "claude":
        emit({"type": "system", "subtype": "init", "session_id": "s1", "mcp_servers": [{"name": "roaddraft", "status": "connected"}]})
    else:
        emit({"type": "thread.started", "thread_id": "t1"})
        emit({"type": "turn.started"})
    results = []
    def call(batch):
        if vendor == "claude":
            emit({"type": "assistant", "message": {"role": "assistant", "content":
                  [{"type": "text", "text": "calling %%s" %% ", ".join(c[0] for c in batch)}]
                  + [{"type": "tool_use", "id": "c%%d" %% i, "name": "mcp__roaddraft__" + c[0], "input": c[1]} for i, c in enumerate(batch)],
                  "usage": {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 50}}})
        else:
            emit({"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "think"}})
        ids = [send("tools/call", {"name": name, "arguments": args}) for name, args in batch]
        got = [read(mid)["result"] for mid in ids]
        for (name, args), r in zip(batch, got):
            results.append({"name": name, "result": r})
            if vendor == "claude":
                emit({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": name, "content": r["content"][0]["text"]}]}})
            else:
                emit({"type": "item.completed", "item": {"id": name, "type": "mcp_tool_call", "server": "roaddraft", "tool": name,
                      "arguments": args, "result": r, "error": None, "status": "completed"}})
        if mode == "crash":
            raise SystemExit(3)
    if mode == "parallel":
        call(calls[:2])
        for c in calls[2:]:
            call([c])
    else:
        for c in calls:
            call([c])
    if vendor == "claude":
        emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "All done."}],
              "usage": {"input_tokens": 100, "output_tokens": 5}, "stop_reason": "end_turn"}})
        emit({"type": "result", "subtype": "success", "is_error": False, "result": "All done.", "num_turns": len(calls) + 1,
              "usage": {"input_tokens": 999, "output_tokens": 999}, "total_cost_usd": 0.0123, "duration_ms": 10})
    else:
        emit({"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "All done."}})
        emit({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 50, "reasoning_output_tokens": 20}})
    seen["results"] = results
    record = os.environ.get("FAKE_CLI_RECORD")
    if record:
        with open(record, "w") as fh:
            json.dump(seen, fh)
    proc.stdin.close()
    proc.wait(timeout=10)
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """The stand-in binary, and the file it reports what it saw to."""
    body = tmp_path / "fake-cli.py"
    body.write_text(FAKE % {"python": sys.executable})
    script = tmp_path / "fake-cli"           # a shell wrapper: the venv's path has a space, no shebang takes it
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / "seen.json"
    monkeypatch.setenv("FAKE_CLI_RECORD", str(record))
    monkeypatch.delenv("FAKE_CLI_MODE", raising=False)
    monkeypatch.delenv("FAKE_CLI_SCRIPT", raising=False)
    return script, record


def _task(i: int = 0):
    return tasksets.task_from_entry(DEV[i])


def _script(tmp_path, monkeypatch, calls):
    path = tmp_path / "script.json"
    path.write_text(json.dumps([[name, params] for name, params in calls]))
    monkeypatch.setenv("FAKE_CLI_SCRIPT", str(path))


def _oracle_script(tmp_path, monkeypatch, task):
    calls = [(name, dict(params)) for name, params in solution_commands(task)]
    _script(tmp_path, monkeypatch, calls + [("submit", {"note": "reference solution replayed"})])
    return calls


# ---------------------------------------------------------------- the bridge


def test_the_bridge_speaks_mcp_over_stdio_and_forwards_calls():
    tools = [mcp_tool({"name": "create_layer", "description": "a layer",
                       "input_schema": {"type": "object", "properties": {"name": {"type": "string"}},
                                        "required": ["name"]}})]
    link = Link(tools)
    proc = subprocess.Popen([sys.executable, str(BRIDGE), link.address], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, bufsize=1)

    def rpc(mid, method, params=None):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def reply():
        return json.loads(proc.stdout.readline())

    try:
        rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        init = reply()
        assert init["id"] == 1 and init["result"]["protocolVersion"] == "2025-06-18"
        assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
        assert "instructions" not in init["result"]          # the eval's words come as the system prompt
        rpc(2, "tools/list")
        listed = reply()["result"]["tools"]
        assert listed == tools and listed[0]["inputSchema"]["required"] == ["name"]
        rpc(3, "ping")
        assert reply()["result"] == {}
        # two calls in flight at once reach the harness in order, each answered by id
        rpc(4, "tools/call", {"name": "create_layer", "arguments": {"name": "A"}})
        rpc(5, "tools/call", {"name": "create_layer", "arguments": {"name": "B"}})
        first, second = link.events.get(timeout=5), link.events.get(timeout=5)
        assert first == ("call", 4, "create_layer", {"name": "A"})
        assert second == ("call", 5, "create_layer", {"name": "B"})
        link.respond(5, content_blocks({"ok": True, "name": "create_layer"}))
        link.respond(4, content_blocks({"ok": False, "name": "create_layer",
                                        "error": {"type": "invalid_params", "message": "no"}},
                                       images=[("image/png", "AAAA")]), is_error=True)
        r5, r4 = reply(), reply()
        assert r5["id"] == 5 and r5["result"]["isError"] is False
        assert json.loads(r5["result"]["content"][0]["text"]) == {"ok": True, "name": "create_layer"}
        assert r4["id"] == 4 and r4["result"]["isError"] is True
        assert r4["result"]["content"][1] == {"type": "image", "data": "AAAA", "mimeType": "image/png"}
        rpc(6, "nothing/here")
        assert reply()["error"]["code"] == -32601
        # once the harness is gone, a call is answered at once, not left hanging
        link.close()
        rpc(7, "tools/call", {"name": "create_layer", "arguments": {}})
        over = reply()
        assert over["id"] == 7 and over["result"]["isError"] is True
        assert "ended" in over["result"]["content"][0]["text"]
        proc.stdin.close()
        assert proc.wait(timeout=5) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
        link.close()


# ---------------------------------------------------------------- the route


def test_the_oracle_through_claude_code_scores_100(tmp_path, monkeypatch, fake_cli):
    script, record = fake_cli
    task = _task(0)
    calls = _oracle_script(tmp_path, monkeypatch, task)
    provider = ClaudeCodeProvider("claude-fake", effort="medium", claude_bin=str(script))
    r = run_episode(task, CLIAgent(provider), EpisodeConfig(), out_root=tmp_path / "res")
    assert r.termination == "submit" and not r.implicit_submit, r.error
    assert r.effective_score == 100.0 and r.faults == 0 and r.invalid_calls == 0
    assert r.steps == len(calls) + 1 and r.turns == len(calls) + 1
    rec = read_episode(r.path)
    h = rec["header"]
    assert h["provider"] == "claude-code" and h["model"] == "claude-fake" and h["effort"] == "medium"
    assert h["billing"] == "subscription" and h["provider_config"]["version"] == "fake-cli 1.0"
    assert h["prompt_sha256"] == prompts.digest(prompts.system_prompt("neutral", "single"))
    assert rec["end"]["usage_total"]["input_tokens"] == 100 * (len(calls) + 2)
    assert rec["end"]["usage_total"]["cache_read_input_tokens"] == 50 * (len(calls) + 1)
    assert rec["end"]["cost_usd"] is None                     # claude-fake has no price row
    last = rec["turns"][-1]["assistant"]
    assert last["tool_calls"][0]["name"] == "submit" and last["submit"] is True
    assert last["text"].endswith("All done.") and last["cli"]["cli_cost_usd"] == 0.0123
    assert rec["turns"][0]["assistant"]["text"].startswith("calling ")
    # what the CLI was handed: the eval's prompt, the task, the episode's tools, an empty folder
    seen = json.loads(record.read_text())
    assert seen["system"] == prompts.system_prompt("neutral", "single")
    assert "THE TASK:" in seen["task"] and seen["model"] == "claude-fake"
    assert seen["tools"] == sorted(seen["tools"]) and "submit" in seen["tools"]
    assert "run_check" not in seen["tools"] and "save_document" not in seen["tools"]
    assert seen["schemas"][seen["tools"][0]]["type"] == "object"
    assert seen["cwd_files"] == [] and seen["init"]["serverInfo"]["name"] == "roaddraft-eval"
    argv = seen["argv"]
    assert argv[argv.index("--effort") + 1] == "medium" and argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--max-turns") + 1] == str(Budgets().steps + 2)
    assert "--restricted" in argv and "--strict-mcp-config" in argv
    assert all(json.loads(x["result"]["content"][0]["text"])["ok"] for x in seen["results"])
    # the CLI's own stream and stderr kept beside the trajectory
    raw = tmp_path / "res" / "cli"
    streams = list(raw.glob("*.claude-code.jsonl"))
    assert len(streams) == 1 and '"type": "result"' in streams[0].read_text()


def test_the_oracle_through_codex_scores_100_and_the_usage_lands_in_the_last_turn(tmp_path, monkeypatch, fake_cli):
    script, record = fake_cli
    task = _task(3)
    calls = _oracle_script(tmp_path, monkeypatch, task)
    provider = CodexProvider("gpt-fake", effort="low", codex_bin=str(script))
    r = run_episode(task, CLIAgent(provider), EpisodeConfig(), out_root=tmp_path / "res")
    assert r.termination == "submit" and r.effective_score == 100.0, r.error
    rec = read_episode(r.path)
    assert rec["header"]["provider"] == "codex" and rec["header"]["effort"] == "low"
    assert rec["end"]["usage_total"] == {"input_tokens": 100, "cache_read_input_tokens": 900,
                                          "output_tokens": 50, "reasoning_tokens": 20}
    assert rec["turns"][-1]["usage"]["output_tokens"] == 50
    assert rec["turns"][-1]["assistant"]["cli"]["thread_id"] == "t1"
    assert rec["turns"][0]["assistant"]["thinking"] == "think"
    seen = json.loads(record.read_text())
    argv = seen["argv"]
    assert argv[:2] == ["exec", "--json"] and argv[-1] == seen["task"]
    settings = dict(argv[i + 1].split("=", 1) for i, a in enumerate(argv) if a == "-c")
    assert settings["model_reasoning_effort"] == '"low"' and settings["approval_policy"] == '"never"'
    assert json.loads(settings["mcp_servers.roaddraft.command"]) == sys.executable
    assert json.loads(settings["mcp_servers.roaddraft.args"])[0] == str(BRIDGE)
    assert "mcp_servers.roaddraft.env" not in settings
    assert seen["system"] == prompts.system_prompt("neutral", "single")


def test_a_system_extra_reaches_both_clis_inside_the_system_prompt_they_are_given(tmp_path, fake_cli):
    """``--system-extra`` (training plan T0) on the CLI route: Claude Code's
    ``--system-prompt`` and Codex's instructions file carry it, as an API row's
    system prompt does, and the header names it."""
    script, record = fake_cli
    sheet = tmp_path / "conventions.md"
    sheet.write_text("# House rules\n\n- Never draft on layer 0.\n")
    extra = prompts.SystemExtra.load(sheet)
    want = prompts.with_extra(prompts.system_prompt("neutral", "single"), extra.text)
    assert want != prompts.system_prompt("neutral", "single") and want.endswith("layer 0.\n")
    for provider in (ClaudeCodeProvider("claude-fake", claude_bin=str(script)),
                     CodexProvider("gpt-fake", codex_bin=str(script))):
        r = run_episode(_task(1), CLIAgent(provider), EpisodeConfig(system_extra=extra),
                        out_root=tmp_path / provider.name)
        assert r.termination == "submit", (provider.name, r.error)
        assert json.loads(record.read_text())["system"] == want, provider.name
        h = read_episode(r.path)["header"]
        assert h["system_extra"] == extra.record() and h["prompt_sha256"] == prompts.digest(want)


def test_calls_that_arrive_together_are_one_turn_answered_in_order(tmp_path, monkeypatch, fake_cli):
    script, record = fake_cli
    monkeypatch.setenv("FAKE_CLI_MODE", "parallel")
    _script(tmp_path, monkeypatch, [("create_layer", {"name": "rd_A", "color": "black"}),
                                    ("create_layer", {"nmae": "oops"}),
                                    ("submit", {"note": "done"})])
    provider = ClaudeCodeProvider("claude-fake", claude_bin=str(script))
    r = run_episode(_task(1), CLIAgent(provider), EpisodeConfig(), out_root=tmp_path / "res")
    assert r.termination == "submit" and r.steps == 3 and r.turns == 2
    assert r.faults == 1 and r.invalid_calls == 1
    rec = read_episode(r.path)
    first = rec["turns"][0]
    assert [c["name"] for c in first["assistant"]["tool_calls"]] == ["create_layer", "create_layer"]
    assert [x["ok"] for x in first["results"]] == [True, False]
    seen = json.loads(record.read_text())
    assert [x["name"] for x in seen["results"]] == ["create_layer", "create_layer", "submit"]
    assert json.loads(seen["results"][1]["result"]["content"][0]["text"])["error"]["type"] == "invalid_params"
    assert seen["results"][1]["result"]["isError"] is True
    assert json.loads(seen["results"][2]["result"]["content"][0]["text"])["message"] == "submitted"


def test_a_cli_that_stops_without_submit_has_submitted(tmp_path, monkeypatch, fake_cli):
    script, _ = fake_cli
    monkeypatch.setenv("FAKE_CLI_MODE", "nosubmit")
    provider = CodexProvider("gpt-fake", codex_bin=str(script))
    r = run_episode(_task(0), CLIAgent(provider), EpisodeConfig(), out_root=tmp_path / "res")
    assert r.termination == "submit" and r.implicit_submit and r.steps == 1
    rec = read_episode(r.path)
    assert rec["turns"][-1]["assistant"]["implicit_submit"] is True
    assert rec["turns"][-1]["assistant"]["text"] == "All done."


def test_the_wall_clock_kills_a_cli_that_never_calls(tmp_path, monkeypatch, fake_cli):
    script, _ = fake_cli
    monkeypatch.setenv("FAKE_CLI_MODE", "hang")
    monkeypatch.setenv("FAKE_CLI_HANG", "30")
    provider = ClaudeCodeProvider("claude-fake", claude_bin=str(script))
    agent = CLIAgent(provider)
    t0 = time.monotonic()
    r = run_episode(_task(0), agent, EpisodeConfig(budgets=Budgets(wall_clock_s=1.5)))
    assert r.termination == "budget" and r.budget_tripped == "wall_clock"
    assert time.monotonic() - t0 < 15 and r.steps == 0
    assert agent.proc.poll() is not None                       # killed, not left running


def test_a_cli_that_is_not_signed_in_is_an_error_not_a_score(tmp_path, monkeypatch, fake_cli):
    script, _ = fake_cli
    monkeypatch.setenv("FAKE_CLI_MODE", "nologin")
    provider = ClaudeCodeProvider("claude-fake", claude_bin=str(script))
    r = run_episode(_task(0), CLIAgent(provider), EpisodeConfig())
    assert r.termination == "error" and "not signed in" in r.error and r.steps == 0


def test_a_cli_that_dies_mid_run_is_an_error(tmp_path, monkeypatch, fake_cli):
    script, _ = fake_cli
    monkeypatch.setenv("FAKE_CLI_MODE", "crash")
    provider = CodexProvider("gpt-fake", codex_bin=str(script))
    r = run_episode(_task(0), CLIAgent(provider), EpisodeConfig())
    assert r.termination == "error" and "exited 3" in r.error and r.steps == 1


def test_the_cli_is_handed_the_api_rows_tool_names(tmp_path, monkeypatch, fake_cli):
    script, record = fake_cli
    task = _task(2)
    fake = FakeProvider([turn([("submit", {})])])
    run_episode(task, LLMAgent(fake), EpisodeConfig())
    provider = ClaudeCodeProvider("claude-fake", claude_bin=str(script))
    r = run_episode(task, CLIAgent(provider), EpisodeConfig())
    assert r.termination == "submit"
    seen = json.loads(record.read_text())
    assert seen["tools"] == fake.requests[0]["tools"]
    assert seen["system"] == fake.requests[0]["system"]


def test_a_probe_task_runs_through_the_route(tmp_path, monkeypatch, fake_cli):
    script, record = fake_cli
    entry = tasksets.entries("hard-pilots", limit=1)[0]
    spec = RunSpec(taskset="hard-pilots", models=("claude-fake",), provider="claude-code",
                   results_root=str(tmp_path / "res"), run_id="pilot")
    provider = ClaudeCodeProvider("claude-fake", claude_bin=str(script))
    r = run_cell(Cell(entry, "claude-fake", "explicit", "single", 0), spec,
                 agent_factory=lambda name, s: CLIAgent(provider))
    assert r.termination == "submit" and r.steps == 2
    rec = read_episode(r.path)
    assert rec["header"]["probe"] == entry["probe"] and rec["header"]["provider"] == "claude-code"
    seen = json.loads(record.read_text())
    assert "open_document" in seen["tools"] and "submit" in seen["tools"]
    assert seen["system"].startswith("RoadDraft is a headless")
    assert (tmp_path / "res" / "pilot" / "cli").is_dir()


# ------------------------------------------------------------- the pieces


def test_make_and_the_cli_flags(tmp_path, monkeypatch, fake_cli):
    script, _ = fake_cli
    assert set(CLI_PROVIDERS) <= set(PROVIDERS)
    p = make("claude-sonnet-5-5", "claude-code", claude_bin=str(script), effort="high",
             max_tokens=5, claude_args=["--x"], max_budget_usd=2.0)
    assert isinstance(p, CLIProvider) and p.name == "claude-code" and p.effort == "high"
    assert p.extra_args == ["--x"] and p.max_budget_usd == 2.0 and p.ready()
    argv = p.argv("do it", "SYS", ["py", "bridge.py", "unix:/s"], tmp_path, Budgets(steps=10))
    assert argv[argv.index("--max-turns") + 1] == "12" and argv[-1] == "--x"
    assert argv[argv.index("--max-budget-usd") + 1] == "2.0"
    assert json.loads((tmp_path / "mcp.json").read_text())["mcpServers"]["roaddraft"] == {
        "type": "stdio", "command": "py", "args": ["bridge.py", "unix:/s"]}
    c = make("gpt-6.1-sol", "codex", codex_bin=str(script), codex_args=["--y"], effort="medium")
    assert isinstance(c, CodexProvider) and c.extra_args == ["--y"]
    argv = c.argv("do it", "SYS", ["py", "bridge.py", "tcp:127.0.0.1:1"], tmp_path, Budgets())
    assert argv[-2:] == ["--y", "do it"] and (tmp_path / "instructions.md").read_text() == "SYS"
    assert "--disable" in argv and "shell_tool" in argv
    # a model id never implies a CLI: gpt-* is an OpenAI-compatible endpoint unless asked
    assert make("gpt-6.1-sol").name == "openai"
    with pytest.raises(RuntimeError):
        make("m", "claude-code", claude_bin=str(tmp_path / "nowhere"))


def test_the_streams_read_usage_text_and_the_outcome():
    s = ClaudeStream()
    s.feed(json.dumps({"type": "system", "subtype": "init", "session_id": "x",
                       "mcp_servers": [{"name": "roaddraft", "status": "connected"}]}))
    s.feed(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "hm"}, {"type": "text", "text": "hi"},
        {"type": "tool_use", "id": "a", "name": "mcp__roaddraft__x", "input": {}}],
        "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 3,
                  "server_tool_use": {"web_search_requests": 0}}}}))
    usage, record = s.take()
    assert usage == {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 3}
    assert record == {"text": "hi", "thinking": "hm"} and s.error is None
    s.feed(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "",
                       "usage": {"input_tokens": 500}, "total_cost_usd": 0.5, "num_turns": 9}))
    usage, record = s.take()
    assert usage == {} and record["stop"] == "max_turns" and s.error is None
    assert s.extra["cli_cost_usd"] == 0.5 and s.extra["session_id"] == "x"
    t = ClaudeStream()
    t.feed(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                       "result": "Rate limit reached for the account", "usage": {"input_tokens": 7}}))
    assert t.error.startswith("account limit:") and t.take()[0] == {"input_tokens": 7}
    u = ClaudeStream()
    u.feed(json.dumps({"type": "system", "subtype": "init",
                       "mcp_servers": [{"name": "roaddraft", "status": "failed"}]}))
    assert "did not connect" in u.error

    c = CodexStream()
    c.feed(json.dumps({"type": "thread.started", "thread_id": "t"}))
    c.feed(json.dumps({"type": "item.completed", "item": {"type": "reasoning", "text": "r"}}))
    c.feed(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}))
    c.feed(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}}))
    c.feed(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 900,
                                                           "output_tokens": 50, "reasoning_output_tokens": 20}}))
    usage, record = c.take()
    assert usage == {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 50,
                     "reasoning_tokens": 20}
    assert record == {"text": "done", "thinking": "r", "stop": "end"} and c.final == "done"
    assert c.extra["builtins_used"] == ["command_execution"]
    d = CodexStream()
    d.feed(json.dumps({"type": "turn.failed", "error": {"message": "You have hit your usage limit"}}))
    assert d.error.startswith("account limit:")
    assert codex_usage({"input_tokens": 5, "cached_input_tokens": 9}) == {
        "input_tokens": 0, "cache_read_input_tokens": 9, "output_tokens": 0}


def test_the_command_line_runs_the_route(tmp_path, monkeypatch, fake_cli, capsys):
    from roaddraft.eval.__main__ import main
    script, _ = fake_cli
    _oracle_script(tmp_path, monkeypatch, _task(0))
    rc = main(["run", "--taskset", "d1-dev", "--limit", "1", "--model", "claude-fake",
               "--provider", "claude-code", "--claude-bin", str(script), "--effort", "high",
               "--out", str(tmp_path / "res"), "--run-id", "cli", "--concurrency", "1"])
    out = capsys.readouterr().out
    assert rc == 0 and "effective 100.00" in out, out
    run_json = json.loads((tmp_path / "res" / "cli" / "run.json").read_text())
    assert run_json["spec"]["provider"] == "claude-code"
    assert run_json["spec"]["provider_options"] == {"effort": "high", "claude_bin": str(script)}
    # the summary groups the row under the model; the report labels the route
    from roaddraft.eval import report as reports
    summary = reports.build(tmp_path / "res" / "cli", check_delta=False)
    assert summary["rows"][0]["label"].startswith("claude-fake (high) via claude-code")
    assert summary["rows"][0]["effort"] == "high"
    # no binary: refused before the matrix
    rc = main(["run", "--taskset", "d1-dev", "--limit", "1", "--model", "m", "--provider", "codex",
               "--codex-bin", str(tmp_path / "nowhere"), "--out", str(tmp_path / "res2")])
    assert rc == 2 and "nowhere" in capsys.readouterr().err
