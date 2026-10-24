"""MCP server mode: the command surface as agent tools (roaddraft/mcp/server.py).

The protocol surface is small on purpose -- initialize, tools/list, tools/call,
ping -- so these tests mostly pin the contract an agent depends on: every
command and query is a tool, a faulting command comes back as a *tool* error
carrying the teaching message rather than a protocol error, and a render comes
back as an image.
"""
from __future__ import annotations

import io
import json

import pytest

from roaddraft.api.session import Session
from roaddraft.mcp.server import PROTOCOL_VERSION, RoadDraftMCP, tool_definitions

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def server(tmp_path=None, **kwargs) -> RoadDraftMCP:
    return RoadDraftMCP(Session(project_name="mcp-tests", out_dir=tmp_path), **kwargs)


def request(mid, method, **params):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}


def call(srv: RoadDraftMCP, tool: str, **arguments) -> dict:
    reply = srv.handle(request(1, "tools/call", name=tool, arguments=arguments))
    return reply["result"]


def payload(result: dict):
    return json.loads(result["content"][0]["text"])


def test_initialize_echoes_the_clients_version_and_declares_tools():
    srv = server()
    r = srv.handle(request(1, "initialize", protocolVersion="2024-11-05",
                           capabilities={}, clientInfo={"name": "probe"}))["result"]
    assert r["protocolVersion"] == "2024-11-05"      # the client's, not ours
    assert r["capabilities"]["tools"] == {"listChanged": False}
    assert r["serverInfo"]["name"] == "roaddraft"
    assert "model space" in r["instructions"].lower()
    # with no version offered, the server names the revision it implements
    assert server().handle(request(1, "initialize"))["result"]["protocolVersion"] \
        == PROTOCOL_VERSION


def test_every_command_and_query_is_a_tool_plus_open_document():
    srv = server()
    manifest = srv.session.manifest()
    tools = srv.handle(request(1, "tools/list"))["result"]["tools"]
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names))
    expected = ({c["name"] for c in manifest["commands"]}
                | {q["name"] for q in manifest["queries"]} | {"open_document"})
    assert set(names) == expected
    assert "draw_offset" in names and "place_label" in names
    for tool in tools:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]
    # the worked example rides along in the description, where a model reads it
    offset = next(t for t in tools if t["name"] == "draw_offset")
    assert "Example params:" in offset["description"]
    assert json.loads(offset["description"].split("Example params: ")[1])["offsets"]


def test_a_tool_call_runs_through_the_bus_and_is_journaled():
    srv = server()
    r = call(srv, "create_alignment", name="SR-100", begin_station="10+00", pis=A_PIS)
    assert r["isError"] is False
    body = payload(r)
    assert body["ok"] and body["name"] == "create_alignment"
    r = call(srv, "draw_offset", offsets=[-12, 12])
    assert r["isError"] is False and len(payload(r)["created"]) == 6
    journal = payload(call(srv, "get_journal"))
    assert [e["name"] for e in journal["entries"]] == ["create_alignment", "draw_offset"]


def test_a_faulting_command_is_a_tool_error_carrying_the_teaching_message():
    """The model has to be able to read the error and fix its own call."""
    srv = server()
    r = call(srv, "draw_offset", offsets=[-12])
    assert r["isError"] is True
    error = payload(r)["error"]
    assert error["type"] == "command_failed" and "alignment" in error["message"]
    r = call(srv, "create_alignment", name="X", pis="not a list")
    assert r["isError"] is True
    error = payload(r)["error"]
    assert error["type"] == "invalid_params"
    assert error["valid_params_schema"]["type"] == "object" and error["example"]
    # a handler-level fault teaches too, with a worked example attached
    r = call(srv, "create_alignment", name="X")
    error = payload(r)["error"]
    assert error["type"] == "command_failed" and error["example"]["pis"]


def test_unknown_tool_points_at_the_manifest():
    r = call(server(), "draw_spiral")
    assert r["isError"] is True
    assert "unknown tool" in r["content"][0]["text"]
    assert "list_commands" in r["content"][0]["text"]


def test_unknown_method_is_a_protocol_error_and_notifications_get_no_reply():
    srv = server()
    reply = srv.handle(request(7, "resources/list"))
    assert reply["error"]["code"] == -32601 and "not supported" in reply["error"]["message"]
    assert reply["id"] == 7
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert srv.handle({"jsonrpc": "2.0", "id": 8, "method": "ping"})["result"] == {}
    assert srv.handle({"id": 9, "method": "ping"})["error"]["code"] == -32600


def test_render_sheet_comes_back_as_an_image_the_agent_can_look_at(tmp_path):
    srv = server(tmp_path=tmp_path)
    call(srv, "create_sheet", name="C-101", size="ANSI_D")
    r = call(srv, "render_sheet", sheet="C-101")
    assert r["isError"] is False
    kinds = [c["type"] for c in r["content"]]
    assert kinds == ["text", "image"]
    image = r["content"][1]
    assert image["mimeType"] == "image/png" and len(image["data"]) > 1000
    # a query with no image stays text-only
    assert [c["type"] for c in call(srv, "list_sheets")["content"]] == ["text"]


def test_open_document_loads_a_sheet_file_and_resolves_its_reference(tmp_path):
    """T2's starting condition: a sheet file with the model referenced in."""
    model = Session(project_name="SR-100 model", out_dir=tmp_path)
    model.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                       "pis": A_PIS})
    model.execute("draw_offset", {"offsets": [-12, 12]})
    model_path = tmp_path / "SR-100.model.rdoc.json"
    assert model.query("save_document", {"path": str(model_path)})["ok"]

    sheets = Session(project_name="SR-100 plans", out_dir=tmp_path)
    sheets.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    sheet_path = tmp_path / "SR-100.sheets.rdoc.json"
    assert sheets.query("save_document", {"path": str(sheet_path)})["ok"]
    # a relative reference, the way a real project stores it: next to the sheet file
    assert sheets.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                               "path": "SR-100.model.rdoc.json"})["ok"]
    assert sheets.query("save_document", {"path": str(sheet_path)})["ok"]

    srv = server(tmp_path=tmp_path)
    r = call(srv, "open_document", path=str(sheet_path))
    assert r["isError"] is False, r["content"][0]["text"]
    assert payload(r)["state"]["summary"]["sheets"][0]["name"] == "C-101"
    refs = payload(call(srv, "list_references"))
    assert refs["references"][0]["status"] == "loaded"
    assert refs["references"][0]["entities"] == 6      # the offset chain, through the ref
    # and the opened document is what later calls act on
    assert call(srv, "fill_title_block", sheet="C-101",
                fields={"project": "SR-100"})["isError"] is False


def test_open_document_reports_a_bad_path_as_a_tool_error(tmp_path):
    srv = server(tmp_path=tmp_path)
    r = call(srv, "open_document", path=str(tmp_path / "nope.rdoc.json"))
    assert r["isError"] is True and "no such document" in r["content"][0]["text"]
    (tmp_path / "junk.json").write_text("{not json")
    r = call(srv, "open_document", path=str(tmp_path / "junk.json"))
    assert r["isError"] is True and "cannot open" in r["content"][0]["text"]


def test_only_and_exclude_trim_the_surface():
    srv = server(only=["create_alignment", "draw_offset", "render_sheet"])
    assert {t["name"] for t in srv.tools()} == {"create_alignment", "draw_offset",
                                                "render_sheet"}
    assert call(srv, "list_sheets")["isError"] is True  # hidden means unavailable
    srv = server(exclude=["delete_entities", "open_document"])
    names = {t["name"] for t in srv.tools()}
    assert "delete_entities" not in names and "open_document" not in names
    assert "draw_line" in names


def test_tool_definitions_filter_is_reusable_for_a_whitelist():
    session = Session()
    manifest = session.manifest()
    total = len(manifest["commands"]) + len(manifest["queries"]) + 1  # + open_document
    assert len(tool_definitions(session)) == total
    assert len(tool_definitions(session, only=["draw_line"])) == 1
    assert len(tool_definitions(session, exclude=["draw_line"])) == total - 1


def test_serve_reads_newline_delimited_json_and_survives_bad_input():
    lines = [
        json.dumps(request(1, "initialize", protocolVersion="2025-06-18")),
        "",                                   # blank lines are skipped
        "{not json",                          # parse error, server keeps going
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps(request(2, "tools/call", name="create_alignment",
                           arguments={"name": "SR-100", "begin_station": "10+00",
                                      "pis": A_PIS})),
        json.dumps([request(3, "ping"), {"jsonrpc": "2.0", "method": "notifications/x"}]),
    ]
    out = io.StringIO()
    server().serve(io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2, 3]
    assert replies[1]["error"]["code"] == -32700      # the bad JSON
    assert replies[2]["result"]["isError"] is False
    assert replies[3]["result"] == {}


def test_autosave_writes_the_document_and_journal_back_after_every_command(tmp_path):
    """An agent is asked to do a drafting job, not to remember to save. Without
    autosave its work lives in memory and is gone when the client hangs up --
    so a probe would score the untouched file and fail for the wrong reason."""
    from roaddraft.mcp.server import journal_path
    from roaddraft.probes import fixture
    _model, sheets = fixture.build(tmp_path)
    srv = RoadDraftMCP(Session.load(sheets, out_dir=tmp_path), autosave=True)
    result = call(srv, "fill_title_block", sheet="C-101", fields={"project": "SR-100"})
    assert not result["isError"]
    on_disk = Session.load(sheets, out_dir=tmp_path)
    assert on_disk.doc.sheet_by_ref("C-101").title_block_fields == {"project": "SR-100"}
    assert journal_path(sheets).name == "SR-100.sheets.jsonl"
    assert journal_path(sheets).is_file()
    assert journal_path(tmp_path / "plan.rdraft").name == "plan.jsonl"

    # an undo is a command too: a retracted mistake must not be what gets scored
    assert not call(srv, "undo")["isError"]
    on_disk = Session.load(sheets, out_dir=tmp_path)
    assert on_disk.doc.sheet_by_ref("C-101").title_block_fields == {}

    # a fault and a query change nothing, and write nothing
    stamp = sheets.stat().st_mtime_ns
    assert call(srv, "fill_title_block", sheet="C-999", fields={"a": "b"})["isError"]
    assert not call(srv, "list_sheets")["isError"]
    assert sheets.stat().st_mtime_ns == stamp


def test_autosave_is_off_by_default_and_leaves_an_unsaved_document_alone(tmp_path):
    from roaddraft.probes import fixture
    _model, sheets = fixture.build(tmp_path)
    before = sheets.read_bytes()
    srv = RoadDraftMCP(Session.load(sheets, out_dir=tmp_path))
    assert not call(srv, "fill_title_block", sheet="C-101", fields={"a": "b"})["isError"]
    assert sheets.read_bytes() == before
    # nowhere to save a document that never came from a file: not an error
    fresh = RoadDraftMCP(Session(project_name="new", out_dir=tmp_path), autosave=True)
    assert not call(fresh, "create_layer", name="L1", color="black")["isError"]


def test_trace_keeps_the_queries_and_the_faults_the_journal_does_not(tmp_path):
    trace = tmp_path / "run" / "trace.jsonl"
    srv = RoadDraftMCP(Session(project_name="t", out_dir=tmp_path), trace=str(trace))
    call(srv, "list_layers")
    call(srv, "create_layer", name="V-ROAD", color="black")
    call(srv, "create_layer", name="V-ROAD", color="black")           # already exists
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [(r["tool"], r["kind"], r["ok"]) for r in rows] == [
        ("list_layers", "query", True), ("create_layer", "command", True),
        ("create_layer", "command", False)]
    assert rows[1]["arguments"] == {"name": "V-ROAD", "color": "black"}
    assert "already exists" in rows[2]["error"]["message"] and rows[2]["error"]["hint"]
    assert len(srv.session.bus.journal) == 1                          # the journal kept one
    # and each line carries the whole result the agent was shown, so the run
    # converts to a conversation without being replayed
    assert rows[0]["result"]["ok"] and "layers" in rows[0]["result"]
    assert rows[1]["result"]["created"] and rows[2]["result"]["error"]["message"]


def test_autosave_stays_with_the_opened_file_when_the_agent_saves_a_copy(tmp_path):
    """Seen in a real run: a model finishes with save_document under a name of
    its own. If autosave followed it there, the file the harness scores would
    silently stop updating."""
    from roaddraft.probes import fixture
    _model, sheets = fixture.build(tmp_path / "project")
    srv = RoadDraftMCP(Session.load(sheets, out_dir=tmp_path), autosave=True)
    copy = tmp_path / "elsewhere" / "my-copy.rdraft"
    assert not call(srv, "save_document", path=str(copy))["isError"]
    assert not call(srv, "fill_title_block", sheet="C-102", fields={"project": "P"})["isError"]
    opened = Session.load(sheets, out_dir=tmp_path)
    assert opened.doc.sheet_by_ref("C-102").title_block_fields == {"project": "P"}
    # the copy is the agent's own business: it holds what was saved, no more
    assert Session.load(copy, out_dir=tmp_path).doc.sheet_by_ref(
        "C-102").title_block_fields == {}
    # opening another document moves home with it
    other = tmp_path / "other" / "plan.rdraft"
    Session(project_name="other", out_dir=tmp_path).query("save_document",
                                                          {"path": str(other)})
    assert not call(srv, "open_document", path=str(other))["isError"]
    assert not call(srv, "create_layer", name="L9", color="black")["isError"]
    assert "L9" in Session.load(other, out_dir=tmp_path).doc.layers
    assert "L9" not in Session.load(sheets, out_dir=tmp_path).doc.layers


def test_a_file_opened_again_keeps_its_journal(tmp_path):
    """Autosave wrote a file's journal from the session that opened it, so an
    agent that went to a base file and came back started the sheet's journal
    over, losing what it had done there first (2026-10-20). A file opened again
    now carries its earlier passes: the journal holds every command, each pass
    from an init with the file as it was then, and replays to the file."""
    from roaddraft.document.fileformat import journal_path
    from roaddraft.probes import fixture
    model, sheets = fixture.build(tmp_path)
    srv = RoadDraftMCP(Session.load(sheets, out_dir=tmp_path), autosave=True)
    assert not call(srv, "create_layer", name="FIRST")["isError"]
    assert not call(srv, "open_document", path=str(model))["isError"]
    assert not call(srv, "create_layer", name="IN-BASE")["isError"]
    assert not call(srv, "open_document", path=str(sheets))["isError"]
    assert not call(srv, "create_layer", name="SECOND")["isError"]

    records = [json.loads(line) for line in journal_path(sheets).read_text().splitlines()]
    assert [r["type"] for r in records] == ["init", "command", "init", "command"]
    assert [r["params"]["name"] for r in records if r["type"] == "command"] == ["FIRST", "SECOND"]
    replayed = Session.replay_journal(journal_path(sheets))
    assert replayed.doc.to_dict() == Session.load(sheets).doc.to_dict()
    assert {"FIRST", "SECOND"} <= set(replayed.doc.layers)
    base = [json.loads(line) for line in journal_path(model).read_text().splitlines()]
    assert [r.get("params", {}).get("name") for r in base] == [None, "IN-BASE"]
