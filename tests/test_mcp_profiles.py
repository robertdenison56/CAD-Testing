"""The basic tool profile and the attachment viewer (pilots 16 and 1/15,
2026-10-19): both opt-in, so the default surface the board ranks on is unchanged."""
from __future__ import annotations

import base64
import io

from PIL import Image

from roaddraft.api.session import Session
from roaddraft.mcp import profiles
from roaddraft.mcp.server import INSTRUCTIONS, RoadDraftMCP, tool_definitions
from roaddraft.probes import tasks


def _names(server):
    return {t["name"] for t in server.tools()}


def test_default_surface_unchanged():
    default = RoadDraftMCP(Session())
    assert _names(default) == {t["name"] for t in tool_definitions(Session())}
    assert "view_attachment" not in _names(default)
    assert default._initialize({})["instructions"] == INSTRUCTIONS


def test_basic_hides_the_helpers_and_strips_aimed_params():
    basic = RoadDraftMCP(Session(), profile="basic")
    names = _names(basic)
    assert not names & set(profiles.BASIC_EXCLUDE)
    assert {"draw_line", "draw_arc", "place_text", "place_callout", "create_alignment",
            "get_design_data", "render_sheet"} <= names
    tools = {t["name"]: t for t in basic.tools()}
    assert "target_entity" not in tools["place_callout"]["inputSchema"]["properties"]
    assert "legs" not in tools["create_alignment"]["inputSchema"]["properties"]
    refused = basic.call_tool("place_callout", {"space": "model", "position": [0, 0],
                                                "content": "X", "target_entity": "e1"})
    assert refused["isError"] and "target_entity" in refused["content"][0]["text"]
    made = basic.call_tool("create_alignment", {"name": "A", "pis": [[0, 0], [100, 0, 50], [200, 100]]})
    assert not made["isError"]
    assert basic._initialize({})["instructions"] == profiles.BASIC_INSTRUCTIONS


def test_basic_excludes_only_real_tools():
    every = {t["name"] for t in tool_definitions(Session())}
    assert set(profiles.BASIC_EXCLUDE) <= every
    assert set(profiles.BASIC_STRIP) <= every


def test_view_attachment_lists_and_crops(tmp_path):
    Image.new("RGB", (4000, 2000), "white").save(tmp_path / "scan.png")
    server = RoadDraftMCP(Session(), attachments=str(tmp_path))
    assert "view_attachment" in _names(server)
    listing = server.call_tool("view_attachment", {})
    assert "scan.png" in listing["content"][0]["text"]
    whole = server.call_tool("view_attachment", {"name": "scan.png"})
    im = Image.open(io.BytesIO(base64.b64decode(whole["content"][1]["data"])))
    assert max(im.size) <= 1568
    part = server.call_tool("view_attachment", {"name": "scan.png", "region": [0.5, 0.5, 0.75, 1]})
    im = Image.open(io.BytesIO(base64.b64decode(part["content"][1]["data"])))
    assert im.size == (1000, 1000)
    bad = server.call_tool("view_attachment", {"name": "scan.png", "region": [0.5, 0.5, 0.4, 1]})
    assert bad["isError"]
    assert server.call_tool("view_attachment", {"name": "nope.png"})["isError"]


def test_pilots_stay_off_the_board():
    from roaddraft.probes import pilot
    assert len(tasks.PROBES) == 33
    assert not set(pilot.BY_ID) & {p.id for p in tasks.PROBES}
    for pid in pilot.BY_ID:
        assert tasks.get(pid).id == pid
