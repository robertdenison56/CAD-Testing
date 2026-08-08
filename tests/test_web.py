import json
import threading
import urllib.request

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.web.server import create_server


# ------------------------------------------------------------- route_line


def test_route_line_command_and_alias():
    s = Session()
    r = route_line(s, "line 0,0 10,5", "model")
    assert r["kind"] == "result" and r["result"]["ok"]
    assert r["result"]["created"] == ["LN-001"]
    r = route_line(s, "mklayer CL color=red", "model")
    assert r["result"]["ok"]
    r = route_line(s, "layer CL", "model")
    assert r["result"]["ok"]
    assert s.doc.settings["current_layer"] == "CL"


def test_route_line_space_switching():
    s = Session()
    s.execute("create_sheet", {"name": "C-101"})
    r = route_line(s, "space C-101", "model")
    assert r["kind"] == "space" and r["space"] == "SH-001"
    r = route_line(s, "space model", "SH-001")
    assert r["kind"] == "space" and r["space"] == "model"
    r = route_line(s, "space nope", "model")
    assert r["kind"] == "error"


def test_route_line_current_space_injected():
    s = Session()
    s.execute("create_sheet", {"name": "C-101"})
    r = route_line(s, 'text 5,5 "HELLO" height=0.2', "SH-001")
    assert r["result"]["ok"]
    assert "TX-001" in s.doc.sheets["SH-001"].entities


def test_route_line_builtins_and_help():
    s = Session()
    r = route_line(s, "state", "model")
    assert r["result"]["ok"] and "summary" in r["result"]
    r = route_line(s, "help draw_arc", "model")
    assert r["kind"] == "help" and r["item"]["name"] == "draw_arc"
    r = route_line(s, "help", "model")
    assert r["kind"] == "help" and len(r["topics"]) > 20
    r = route_line(s, "render", "model")
    assert r["kind"] == "noop"
    r = route_line(s, "entities", "model")
    assert r["result"]["ok"] and r["result"]["count"] == 0


def test_route_line_teaching_error_passthrough():
    s = Session()
    r = route_line(s, "line 5,5", "model")  # missing end point
    assert r["kind"] == "result" and not r["result"]["ok"]
    assert r["result"]["error"]["type"] == "invalid_params"


# ----------------------------------------------------------------- server


@pytest.fixture()
def server(tmp_path):
    session = Session(project_name="WebTest", out_dir=str(tmp_path))
    srv = create_server(session, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read()


def post(base, path, body):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def test_index_served(server):
    status, body = get(server, "/")
    assert status == 200 and b"RoadDraft" in body


def test_state_and_execute_bumps_rev(server):
    _, state = get(server, "/api/state")
    state = json.loads(state)
    assert state["rev"] == 0 and state["project"] == "WebTest"
    _, result = post(server, "/api/execute", {
        "command": "draw_line",
        "params": {"space": "model", "start": [0, 0], "end": [100, 50]}})
    assert result["ok"]
    _, state2 = get(server, "/api/state")
    state2 = json.loads(state2)
    assert state2["rev"] == 1 and state2["model_entity_count"] == 1


def test_query_does_not_bump_rev(server):
    _, result = post(server, "/api/query", {"query": "list_layers"})
    assert result["ok"]
    _, state = get(server, "/api/state")
    assert json.loads(state)["rev"] == 0


def test_line_endpoint_full_flow(server):
    _, resp = post(server, "/api/line",
                   {"line": "sheet C-101 size=ANSI_D", "space": "model"})
    assert resp["kind"] == "result" and resp["result"]["ok"]
    _, resp = post(server, "/api/line",
                   {"line": "space C-101", "space": "model"})
    assert resp["kind"] == "space" and resp["space"] == "SH-001"
    _, resp = post(server, "/api/line",
                   {"line": 'text 1,20 "VIA WEB" height=0.2', "space": "SH-001"})
    assert resp["result"]["ok"]
    _, state = get(server, "/api/state")
    state = json.loads(state)
    assert state["sheets"][0]["entities"] == 1
    assert state["rev"] == 2


def test_render_endpoints(server):
    post(server, "/api/execute", {
        "command": "draw_circle",
        "params": {"space": "model", "center": [0, 0], "radius": 50}})
    status, body = get(server, "/render/model.png?dpi=72")
    assert status == 200 and body[:4] == b"\x89PNG"
    post(server, "/api/execute", {"command": "create_sheet",
                                  "params": {"name": "C-101"}})
    status, body = get(server, "/render/SH-001.png?dpi=60")
    assert status == 200 and body[:4] == b"\x89PNG"
    status, body = get(server, "/render/C-101.png?dpi=60")  # by name too
    assert status == 200 and body[:4] == b"\x89PNG"


def test_render_unknown_space_404(server):
    try:
        get(server, "/render/GHOST.png")
        assert False, "expected 404"
    except urllib.error.HTTPError as ex:
        assert ex.code == 404


def test_manifest_served(server):
    _, body = get(server, "/api/manifest")
    manifest = json.loads(body)
    assert any(c["name"] == "draw_line" for c in manifest["commands"])
    assert any(c["name"] == "annotate_stationing" for c in manifest["commands"])
    assert any(c["name"] == "attach_reference" for c in manifest["commands"])


def test_render_metadata_headers(server):
    post(server, "/api/execute", {
        "command": "draw_line",
        "params": {"space": "model", "start": [0, 0], "end": [1000, 500]}})
    req = urllib.request.Request(server + "/render/model.png?dpi=60")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.headers["X-RD-Kind"] == "model"
        bounds = [float(v) for v in resp.headers["X-RD-Bounds"].split(",")]
        assert bounds[0] < 0 and bounds[2] > 1000  # extents + margin
    post(server, "/api/execute", {"command": "create_sheet",
                                  "params": {"name": "C-101"}})
    with urllib.request.urlopen(server + "/render/C-101.png?dpi=60",
                                timeout=10) as resp:
        assert resp.headers["X-RD-Kind"] == "sheet"
        assert resp.headers["X-RD-Size-In"] == "34.0,22.0"


def test_render_model_bounds_window(server):
    post(server, "/api/execute", {
        "command": "draw_circle",
        "params": {"space": "model", "center": [500, 500], "radius": 400}})
    url = server + "/render/model.png?dpi=60&bounds=400,400,600,600"
    with urllib.request.urlopen(url, timeout=10) as resp:
        bounds = [float(v) for v in resp.headers["X-RD-Bounds"].split(",")]
        assert abs(bounds[0] - 400) < 1e-6 and abs(bounds[2] - 600) < 1e-6
        assert resp.read()[:4] == b"\x89PNG"


def test_dark_theme_model_render(server):
    post(server, "/api/execute", {
        "command": "draw_line",
        "params": {"space": "model", "start": [0, 0], "end": [500, 200]}})
    with urllib.request.urlopen(server + "/render/model.png?dpi=60&theme=dark",
                                timeout=10) as resp:
        dark = resp.read()
    with urllib.request.urlopen(server + "/render/model.png?dpi=60",
                                timeout=10) as resp:
        paper = resp.read()
    assert dark[:4] == b"\x89PNG" and paper[:4] == b"\x89PNG"
    assert dark != paper  # different canvases, both cached separately


def test_state_includes_blocks(server):
    _, state = get(server, "/api/state")
    assert "NORTH_ARROW" in json.loads(state)["blocks"]


def test_state_includes_references(server, tmp_path):
    base = tmp_path / "b.rdoc.json"
    post(server, "/api/query", {"query": "save_document",
                                "params": {"path": str(base)}})
    post(server, "/api/execute", {
        "command": "attach_reference",
        "params": {"name": "BASE", "path": str(base), "space": "model"}})
    _, state = get(server, "/api/state")
    refs = json.loads(state)["references"]
    assert refs and refs[0]["name"] == "BASE" and refs[0]["status"] == "loaded"
