"""A model that opens a base file has to find its way back to the sheet it was
handed: get_document_state names the open file, and open_document with a path
that is no document lists the project's documents (GPT-6-Astra guessed 38 names
for PD-1's sheet file on 2026-10-26 and never got back)."""
from __future__ import annotations

import json

from roaddraft.api.session import Session
from roaddraft.mcp.server import RoadDraftMCP


def _project(tmp_path):
    base = Session(project_name="Base")
    base.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    base.query("save_document", {"path": str(tmp_path / "0000000000aa01.rdraft")})
    sheet = Session(project_name="Sheet")
    sheet.execute("create_sheet", {"name": "PD-1", "size": "ANSI_D"})
    sheet.execute("attach_reference", {"name": "AA01", "path": "0000000000aa01.rdraft"})
    path = tmp_path / "0000000000na001.rdraft"
    sheet.query("save_document", {"path": str(path)})
    return path


def _text(result):
    return "\n".join(b["text"] for b in result["content"] if b["type"] == "text")


def test_the_open_document_is_named_and_a_miss_lists_the_project(tmp_path, monkeypatch):
    path = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    srv = RoadDraftMCP(Session.load(path, out_dir=tmp_path / "renders"), autosave=True,
                       root=str(tmp_path))
    state = json.loads(_text(srv.call_tool("get_document_state", {})))
    assert state["summary"]["document"] == "0000000000na001.rdraft"
    assert not srv.call_tool("open_document", {"path": "0000000000aa01.rdraft"})["isError"]
    state = json.loads(_text(srv.call_tool("get_document_state", {})))
    assert state["summary"]["document"] == "0000000000aa01.rdraft"
    miss = srv.call_tool("open_document", {"path": "0000000000pd01.rdraft"})
    assert miss["isError"]
    msg = _text(miss)
    assert "no such document: 0000000000pd01.rdraft" in msg
    assert "0000000000na001.rdraft (handed to you)" in msg
    assert "0000000000aa01.rdraft (open now)" in msg
    assert not srv.call_tool("open_document", {"path": "0000000000na001.rdraft"})["isError"]
    msg = _text(srv.call_tool("open_document", {"path": "nothing.rdraft"}))
    assert "0000000000na001.rdraft (handed to you, open now)" in msg
