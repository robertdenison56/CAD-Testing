import json
import threading
import urllib.request

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.web.server import STATIC_DIR, create_server


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


def test_model_render_takes_the_shape_of_the_canvas(server):
    """The GUI sends its canvas's width/height; model space widens to fill
    it, about the same centre, rather than leaving the canvas half empty."""
    import io

    from PIL import Image
    post(server, "/api/execute", {
        "command": "draw_line",
        "params": {"space": "model", "start": [0, 0], "end": [1000, 500]}})
    for aspect in (3.0, 0.5):
        url = server + f"/render/model.png?dpi=40&aspect={aspect}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            b = [float(v) for v in resp.headers["X-RD-Bounds"].split(",")]
            png = Image.open(io.BytesIO(resp.read()))
        assert abs((b[2] - b[0]) / (b[3] - b[1]) - aspect) < 1e-6
        assert abs(png.width / png.height - aspect) < 0.02
        assert b[0] < 0 and b[2] > 1000 and b[1] < 0 and b[3] > 500
        assert abs((b[0] + b[2]) / 2 - 500) < 1e-6  # same centre


def test_fit_aspect_grows_the_short_side_only():
    from roaddraft.render.mpl import fit_aspect
    assert fit_aspect((0, 0, 100, 100), 2.0) == (-50, 0, 150, 100)
    assert fit_aspect((0, 0, 100, 100), 0.5) == (0, -50, 100, 150)
    assert fit_aspect((0, 0, 200, 100), 2.0) == (0, 0, 200, 100)


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
    parsed = json.loads(state)
    assert "NORTH_ARROW" in parsed["blocks"]
    assert "STANDARD" in parsed["text_styles"]


def test_state_includes_property_choices(server):
    """The properties panel needs linetypes and named colors from state."""
    _, state = get(server, "/api/state")
    parsed = json.loads(state)
    assert "continuous" in parsed["linetypes"]
    assert "dashed" in parsed["linetypes"]
    assert parsed["colors"]["red"].startswith("#")
    assert "grey" not in parsed["colors"]  # deduplicated alias
    assert all("linetype" in layer for layer in parsed["layers"])


def test_properties_panel_edit_flow(server):
    """Layer/color/linetype changes as the properties panel sends them,
    including clearing an override back to ByLayer with null."""
    post(server, "/api/execute", {"command": "create_layer",
                                  "params": {"name": "V-ROAD", "color": "red"}})
    _, r = post(server, "/api/execute", {"command": "draw_line", "params": {
        "space": "model", "start": [0, 0], "end": [100, 0]}})
    eid = r["created"][0]
    for changes in ({"layer": "V-ROAD"}, {"color": "cyan"},
                    {"color": "#12AB34"}, {"linetype": "dashed"}):
        _, r = post(server, "/api/execute", {"command": "modify_entity",
            "params": {"id": eid, "changes": changes}})
        assert r["ok"], r
    _, info = post(server, "/api/query", {"query": "get_entity",
                                          "params": {"id": eid}})
    e = info["entity"]
    assert (e["layer"], e["color"], e["linetype"]) == \
        ("V-ROAD", "#12AB34", "dashed")
    _, r = post(server, "/api/execute", {"command": "modify_entity",
        "params": {"id": eid, "changes": {"color": None, "linetype": None}}})
    assert r["ok"]
    _, info = post(server, "/api/query", {"query": "get_entity",
                                          "params": {"id": eid}})
    assert "color" not in info["entity"]      # back to ByLayer
    assert "linetype" not in info["entity"]


def test_edit_text_full_flow_over_http(server):
    """The GUI's edit path: place text, fetch it, modify it, fetch again."""
    _, r = post(server, "/api/execute", {"command": "place_text", "params": {
        "space": "model", "position": [100, 100], "content": "DRAFT NOTE",
        "height": 8}})
    eid = r["created"][0]
    _, info = post(server, "/api/query", {"query": "get_entity",
                                          "params": {"id": eid}})
    assert info["entity"]["content"] == "DRAFT NOTE"
    _, r = post(server, "/api/execute", {"command": "modify_entity",
        "params": {"id": eid, "changes": {"content": "FINAL NOTE\nSEE SHEET 2",
                                          "halign": "center"}}})
    assert r["ok"]
    _, info = post(server, "/api/query", {"query": "get_entity",
                                          "params": {"id": eid}})
    assert info["entity"]["content"] == "FINAL NOTE\nSEE SHEET 2"
    assert info["entity"]["halign"] == "center"


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


def draw(server, command, **params):
    """Create one entity and hand back its id."""
    _, r = post(server, "/api/execute",
                {"command": command, "params": {"space": "model", **params}})
    assert r["ok"], r
    return r["created"][0]


def entity_of(server, eid):
    _, info = post(server, "/api/query", {"query": "get_entity",
                                          "params": {"id": eid}})
    assert info["ok"], info
    return info["entity"], info["bbox"]


def grip(server, eid, changes):
    """A grip edit: the change set a dragged grip hands modify_entity."""
    _, r = post(server, "/api/execute", {"command": "modify_entity",
                                         "params": {"id": eid,
                                                    "changes": changes}})
    assert r["ok"], r
    return entity_of(server, eid)


def test_grip_edit_flow_over_http(server):
    """Dragging a grip is an ordinary modify_entity: this is every change set
    the GUI's grips produce, for each kind of entity that gets them."""
    eid = draw(server, "draw_line", start=[0, 0], end=[100, 0])
    e, _ = grip(server, eid, {"start": [10, 20]})          # endpoint grip
    assert e["start"] == [10, 20] and e["end"] == [100, 0]
    e, _ = grip(server, eid, {"end": [120, 20]})
    assert e["end"] == [120, 20]
    e, _ = grip(server, eid, {"start": [10, 25], "end": [120, 25]})
    assert e["start"] == [10, 25] and e["end"] == [120, 25]  # midpoint grip

    eid = draw(server, "draw_polyline", vertices=[[0, 0], [100, 0], [100, 80]])
    e, _ = grip(server, eid, {"vertices": [[0, 0], [140, 0], [100, 80]]})
    assert e["vertices"][1] == [140, 0]                    # vertex grip
    e, _ = grip(server, eid,
                {"vertices": [[0, 0], [70, -30], [140, 0], [100, 80]]})
    assert len(e["vertices"]) == 4                         # midpoint grip adds

    eid = draw(server, "draw_circle", center=[0, 0], radius=50)
    e, bbox = grip(server, eid, {"radius": 80})            # quadrant grip
    assert e["radius"] == 80 and bbox[2] == 80
    e, _ = grip(server, eid, {"center": [200, 200]})
    assert e["center"] == [200, 200]

    eid = draw(server, "draw_arc", center=[0, 0], radius=50,
               start_angle_deg=0, end_angle_deg=90)
    e, _ = grip(server, eid, {"start_angle_deg": -45.0})   # end-of-arc grips
    assert e["start_angle_deg"] == -45.0
    e, _ = grip(server, eid, {"end_angle_deg": 120.0})
    assert e["end_angle_deg"] == 120.0
    e, _ = grip(server, eid, {"radius": 65})
    assert e["radius"] == 65

    eid = draw(server, "place_text", position=[0, 0], content="STA 10+00",
               height=8)
    e, _ = grip(server, eid, {"position": [40, 60]})       # insertion grip
    assert e["position"] == [40, 60]


def test_grip_on_a_dimension_moves_what_it_measures(server):
    """A dimension stores the measurement: drag the grip on a measured point
    and the reading, the linework and the box all follow it."""
    eid = draw(server, "place_dimension", kind="linear", p1=[0, 0],
               p2=[100, 0], line_point=[50, 30], text_height=4)
    _, bbox = entity_of(server, eid)
    assert bbox[2] < 110                       # the box ends near p2
    e, bbox = grip(server, eid, {"p2": [300, 0]})
    assert e["p2"] == [300, 0] and bbox[2] > 290
    e, bbox = grip(server, eid, {"line_point": [150, -60]})
    assert e["line_point"] == [150, -60] and bbox[1] < -55
    assert e["p1"] == [0, 0]                   # measured points stayed put


def test_gui_wires_grips():
    """The selected entity shows grips, and a grip edit lands as the same
    modify_entity the properties panel sends."""
    html = (STATIC_DIR / "index.html").read_text()
    assert "function gripsFor(" in html and "function gripAt(" in html
    assert "applyProp(active.grip.patch(pt))" in html
    assert "gripGhostSVG(S.grip)" in html and "out += gripsSVG();" in html
    assert '#ovl .grip.hot' in html
    assert 'shape(active.grip)(active.at, "grip hot")' in html  # keeps its shape
    assert "S.grip.hot = true" in html                  # click, then click
    assert "orthoFrom(S.grip.grip.pt, pt, ev)" in html  # ORTHO/Shift apply
    assert "(adds a vertex)" in html                    # polyline midpoints
    assert "sel.reference" in html                      # never on a reference


def test_gui_wires_alignment_grips():
    """A drawn alignment selects the alignment, whose grips edit its PIs: one
    modify_alignment that redraws the centerline and allows angle points."""
    html = (STATIC_DIR / "index.html").read_text()
    assert "function alignmentGrips(" in html and "function alignGeom(" in html
    assert 'anchor.kind === "element"' in html and "selectAlignment(" in html
    assert "editAlignment(S.selected.alignment, active.grip.patch(pt))" in html
    assert "angle_points: true, redraw: true" in html
    assert "renderAlignmentProps(panel)" in html       # the PI table
    assert "angle_points: true } });" in html          # created by PI, curves later
