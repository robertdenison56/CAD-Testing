"""Trajectories: a run recorded as the conversation a model would have had.

The recorder runs a solve through the MCP server with tracing on and notes
each direct read of the document the solve makes; the converter turns a trace
file into messages, as it stands when the server wrote the results into it
and by replay when it did not; a model's run folders convert the same way.
The find and draft solves are held to zero direct reads, since those are the
ones a training set starts from.
"""
from __future__ import annotations

import json

import pytest

from roaddraft.api.session import Session
from roaddraft.mcp.server import INSTRUCTIONS, result_text
from roaddraft.probes import fixture, tasks
from roaddraft.probes.prompting import NO_CALCULATOR, task_text
from roaddraft.trajectories import (MissingResults, Recorder, calls_from_trace, conversation,
                                    has_results, record_solve, replay_trace, tool_list,
                                    tools_digest)
from roaddraft.trajectories.__main__ import main
from roaddraft.trajectories.record import read_trace, same_document


def _sheets(tmp_path):
    doc = fixture.start_document(tmp_path, "sheets")
    return Session.load(doc, out_dir=tmp_path)


def test_recorder_keeps_queries_with_results_and_flags_direct_reads(tmp_path):
    s = _sheets(tmp_path)
    with Recorder(s) as rec:
        listed = s.query("list_sheets", {})
        names = [sheet.name for sheet in s.doc.sheets.values()]      # a direct read
        created = s.execute("create_layer", {"name": "S-ANNO-CALL", "color": "black"})
        fault = s.execute("create_layer", {"name": 7})
    # the calls came back untouched
    assert listed["ok"] and created["ok"] and not fault["ok"]
    assert names == ["C-101", "C-102", "C-103"]
    # and were kept with their results, the fault with its error
    assert [(c.tool, c.kind, c.ok) for c in rec.calls] == [
        ("list_sheets", "query", True), ("create_layer", "command", True),
        ("create_layer", "command", False)]
    assert rec.calls[0].result["sheets"][0]["name"] == "C-101"
    assert rec.calls[2].result["error"]["type"] == "invalid_params"
    line = rec.calls[2].trace_line()
    assert line["ok"] is False and line["error"]["message"] and "result" in line
    # the one direct read is named: this file, this test
    assert not rec.faithful
    assert len(rec.direct_reads) == 1
    assert rec.direct_reads[0].file.endswith("test_trajectories.py")
    assert rec.direct_reads[0].function == "test_recorder_keeps_queries_with_results_and_flags_direct_reads"
    # the engine's own reads of the document, answering the queries, were not counted
    # detached: the session is itself again
    assert type(s) is Session and "execute" not in s.__dict__
    s.query("list_layers", {})
    assert len(rec.calls) == 3


def test_say_puts_the_arithmetic_before_the_next_call(tmp_path):
    s = _sheets(tmp_path)
    with Recorder(s) as rec:
        s.say("PI = [1000, 1000] + 900 (sin 62.5°, cos 62.5°) = [1798.31, 1415.57]")
        s.query("list_layers", {})
        s.query("list_sheets", {})
    assert rec.calls[0].said.startswith("PI = ")
    assert rec.calls[1].said is None


@pytest.mark.parametrize("probe_id", [p.id for p in tasks.FIND_PROBES + tasks.DRAFT_PROBES])
def test_find_and_draft_solves_are_faithful(tmp_path, probe_id):
    """Every step a model could have taken: no direct read of the document,
    and the result on disk still passes the check."""
    rec = record_solve(tasks.get(probe_id), tmp_path)
    assert rec.result.passed, rec.result.detail
    assert rec.faithful, [str(d) for d in rec.direct_reads]
    assert rec.counts()["commands"] >= 1


def test_tier3_solves_are_audited_as_they_are(tmp_path):
    """The Tier 3 solves draft from the plotted reader; the recorder says so
    rather than hiding it, with the lines that read the document."""
    rec = record_solve(tasks.get("line-data"), tmp_path)
    assert rec.result.passed
    assert rec.direct_reads, "line-data's solve is expected to read the document until it is rewritten"
    assert all(d.file.startswith("roaddraft/probes/") for d in rec.direct_reads)


def test_conversation_is_the_run_as_a_model_would_see_it(tmp_path):
    probe = tasks.get("sta-offset-c101-paper")
    rec = record_solve(probe, tmp_path)
    tools = tool_list(Session.load(rec.document, out_dir=tmp_path))
    conv = conversation(probe, rec.calls, tools_digest(tools), rec.result, rec.direct_reads)
    msgs = conv["messages"]
    assert msgs[0] == {"role": "system", "content": INSTRUCTIONS}
    assert msgs[1] == {"role": "user", "content": task_text(probe)}
    assert NO_CALCULATOR not in msgs[1]["content"]          # a find-probe
    assert NO_CALCULATOR in task_text(tasks.get("draft-building"))
    # one assistant tool call, then its tool result, per recorded call
    body = msgs[2:-1]
    assert len(body) == 2 * len(rec.calls)
    for k, call in enumerate(rec.calls):
        ask, answer = body[2 * k], body[2 * k + 1]
        assert ask["role"] == "assistant" and ask["tool_calls"][0]["name"] == call.tool
        assert ask["tool_calls"][0]["arguments"] == call.arguments
        assert answer["role"] == "tool" and answer["tool_call_id"] == ask["tool_calls"][0]["id"]
        assert answer["content"] == result_text(call.result)
        assert answer["is_error"] is (not call.ok)
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"].startswith("Done.")
    assert "place_callout" in msgs[-1]["content"]
    assert conv["faithful"] and conv["outcome"]["passed"] and conv["report"] == "templated"
    assert conv["tools_sha256"].startswith("sha256:") and len(tools) == 84
    # the station the solve asked for is in the conversation as a query, not a number from nowhere
    asked = [m["tool_calls"][0] for m in msgs if m.get("tool_calls")]
    assert asked[0]["name"] == "station_to_xy" and asked[0]["arguments"]["station"] == "18+00"


def test_rehydrating_an_mcp_trace_recovers_the_conversation(tmp_path):
    """The MCP server's trace keeps arguments and outcomes, not results; replayed
    on a fresh start the results come back, and so does the document."""
    probe = tasks.get("pc-by-station")
    first = record_solve(probe, tmp_path / "first")
    mcp_lines = []
    for call in first.calls:
        line = call.trace_line()
        line.pop("result")
        mcp_lines.append(line)
    again = replay_trace(probe, mcp_lines, tmp_path / "again")
    assert again.result.passed
    assert [(c.tool, c.arguments, c.result) for c in again.calls] == \
        [(c.tool, c.arguments, c.result) for c in first.calls]
    assert same_document(first.document, again.document)


def test_command_line_records_audits_and_rehydrates(tmp_path, capsys):
    out = tmp_path / "solves"
    assert main(["record", "--out", str(out), "edge-c102", "draft-tangent-ne"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["README.md", "draft-tangent-ne", "edge-c102",
                                                     "tools.json"]
    rec = json.loads((out / "edge-c102" / "record.json").read_text())
    assert rec["faithful"] and rec["outcome"]["passed"]
    conv = json.loads((out / "edge-c102" / "conversation.json").read_text())
    assert conv["tools_sha256"] == json.loads((out / "tools.json").read_text())["sha256"]
    trace = read_trace(out / "edge-c102" / "trace.jsonl")
    assert all("result" in line for line in trace)
    index = (out / "README.md").read_text()
    assert "2 of 2 faithful; 2 of 2 pass" in index
    assert main(["audit", "edge-c102"]) == 0
    assert "0 scripted solution(s) read the document directly" in capsys.readouterr().out
    # a rehydrated run: the recorded trace, stripped to what the server writes, replayed
    stripped = tmp_path / "trace.jsonl"
    with stripped.open("w") as fh:
        for line in trace:
            line.pop("result")
            fh.write(json.dumps(line) + "\n")
    report = tmp_path / "report.txt"
    report.write_text("Placed one callout on the edge of pavement.\n")
    kept = tmp_path / "rehydrated"
    assert main(["rehydrate", "edge-c102", "--trace", str(stripped), "--out", str(kept),
                 "--report", str(report)]) == 0
    conv2 = json.loads((kept / "conversation.json").read_text())
    assert conv2["source"] == "model" and conv2["report"] == "given"
    assert conv2["messages"][-1]["content"].startswith("Placed one callout")
    assert conv2["messages"][2:-1] == conv["messages"][2:-1]


def test_the_servers_trace_converts_without_replay(tmp_path):
    """The solve ran through the MCP server with --trace on, so the server's
    file carries every call with its result; the converter turns that file
    into the conversation the recorder kept, no engine needed. Stripped to
    arguments and outcomes (the older trace shape) it converts by replay."""
    probe = tasks.get("pc-by-station")
    server_trace = tmp_path / "server.jsonl"
    rec = record_solve(probe, tmp_path / "run", trace=server_trace)
    lines = read_trace(server_trace)
    assert has_results(lines)
    # what the server wrote is what the recorder kept, less the solve's shown work
    assert lines == [{k: v for k, v in c.trace_line().items() if k != "said"} for c in rec.calls]
    calls = calls_from_trace(lines)
    assert [(c.tool, c.kind, c.arguments, c.result) for c in calls] == \
        [(c.tool, c.kind, c.arguments, c.result) for c in rec.calls]
    kept = tmp_path / "kept"
    assert main(["convert", probe.id, "--trace", str(server_trace), "--out", str(kept),
                 "--document", str(rec.document)]) == 0
    record = json.loads((kept / "record.json").read_text())
    assert record["how"] == "converted" and record["outcome"]["passed"]
    assert record["source"] == "model" and record["task"] == "probe"
    conv = json.loads((kept / "conversation.json").read_text())
    tools = tool_list(Session.load(rec.document, out_dir=tmp_path))
    assert conv["messages"] == conversation(probe, rec.calls, tools_digest(tools),
                                            rec.result)["messages"]
    # the older shape: arguments and outcomes only
    bare = tmp_path / "bare.jsonl"
    with bare.open("w") as fh:
        for line in lines:
            line.pop("result")
            fh.write(json.dumps(line) + "\n")
    with pytest.raises(MissingResults):
        calls_from_trace(read_trace(bare))
    replayed = tmp_path / "replayed"
    assert main(["convert", probe.id, "--trace", str(bare), "--out", str(replayed),
                 "--document", str(rec.document)]) == 0
    record = json.loads((replayed / "record.json").read_text())
    assert record["how"].startswith("replayed") and record["document_matches"] is True
    again = json.loads((replayed / "conversation.json").read_text())
    assert again["messages"][2:-1] == conv["messages"][2:-1]
    assert has_results(read_trace(replayed / "trace.jsonl"))   # kept with the recovered results


def test_a_models_run_folders_convert_with_their_reports_and_documents(tmp_path):
    """A probe rig leaves runs/<model>/<probe>/ with the server's trace, the
    model's report, the prompt it was handed and the project it left. --runs
    converts every folder: the model is the source, its report closes the
    conversation, and the document it left is scored."""
    probe = tasks.get("edge-c102")
    runs = tmp_path / "runs" / "haiku"
    folder = runs / probe.id
    rec = record_solve(probe, folder / "project", trace=folder / "trace.jsonl")
    (folder / "report.txt").write_text("One callout on the edge of pavement, C-102.\n")
    (folder / "prompt.txt").write_text("Do the task through the bridge.\n")
    (runs / "notes").mkdir()                                  # not a run folder: no trace
    out = tmp_path / "conversations"
    assert main(["convert", "--runs", str(runs), "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["README.md", "edge-c102", "tools.json"]
    record = json.loads((out / probe.id / "record.json").read_text())
    assert record["source"] == "haiku" and record["report"] == "given"
    assert record["how"] == "converted" and record["outcome"]["passed"]
    assert record["from"].endswith("trace.jsonl") and record["faithful"]
    conv = json.loads((out / probe.id / "conversation.json").read_text())
    assert conv["messages"][-1]["content"].startswith("One callout")
    assert conv["messages"][1]["content"] == task_text(probe) and conv["task"] == "probe"
    assert "1 of 1 faithful; 1 of 1 pass" in (out / "README.md").read_text()
    # one folder, with the prompt the model was actually handed as the user message
    one = tmp_path / "one"
    assert main(["convert", "--run", str(folder), "--out", str(one), "--kept-prompt"]) == 0
    conv = json.loads((one / "conversation.json").read_text())
    assert conv["task"] == "kept" and conv["messages"][1]["content"].startswith("Do the task")
    assert conv["source"] == "haiku"
