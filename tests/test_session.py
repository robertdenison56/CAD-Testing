from roaddraft.api.session import Session


def test_manifest_self_describes_everything():
    s = Session()
    manifest = s.manifest()
    command_names = {c["name"] for c in manifest["commands"]}
    assert {"draw_line", "place_text", "create_sheet", "create_viewport",
            "fill_title_block", "undo"} <= command_names
    for item in manifest["commands"] + manifest["queries"]:
        assert item["description"]
        assert item["params_schema"]["type"] == "object"
        assert item["example"] is not None
    draw_line = next(c for c in manifest["commands"] if c["name"] == "draw_line")
    assert draw_line["aliases"]["c3d"] == ["LINE"]
    assert draw_line["aliases"]["ord"] == ["place line"]


def test_document_state_summary_and_full():
    s = Session(project_name="StateTest")
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 50]})
    s.execute("create_sheet", {"name": "C-101"})
    r = s.query("get_document_state")
    assert r["ok"]
    summary = r["summary"]
    assert summary["meta"]["project_name"] == "StateTest"
    assert summary["model_entity_count"] == 1
    assert summary["sheets"][0]["name"] == "C-101"
    assert summary["model_extents"] == (0, 0, 100, 50)
    full = s.query("get_document_state", {"detail": "full"})["document"]
    assert full["model"]["entities"]["LN-001"]["end"] == [100, 50]
    assert full["sheets"]["SH-001"]["name"] == "C-101"


def test_get_sheet_state_includes_viewport_view():
    s = Session()
    s.execute("create_sheet", {"name": "C-101"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11],
                                  "width_in": 10, "height_in": 10,
                                  "model_center": [5000, 3000],
                                  "feet_per_inch": 50})
    sheet = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]
    assert sheet["usable_area"] == (0.5, 1.75, 33.5, 21.5)
    assert sheet["viewports"][0]["visible_model_bbox"] == (4750, 2750, 5250, 3250)


def test_get_model_state_bounds_filter():
    s = Session()
    s.execute("draw_circle", {"space": "model", "center": [0, 0], "radius": 5})
    s.execute("draw_circle", {"space": "model", "center": [1000, 1000],
                              "radius": 5})
    r = s.query("get_model_state", {"bounds": [-10, -10, 10, 10]})
    assert r["count"] == 1 and r["entities"][0]["center"] == [0, 0]


def test_get_entity_and_errors():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    r = s.query("get_entity", {"id": "LN-001"})
    assert r["ok"] and r["space"] == "model" and r["bbox"] == (0, 0, 1, 1)
    r = s.query("get_entity", {"id": "LN-999"})
    assert not r["ok"] and r["error"]["type"] == "query_failed"
    r = s.query("get_extents", {"space": "mars"})
    assert not r["ok"]
    r = s.query("no_such_query")
    assert not r["ok"] and r["error"]["type"] == "unknown_query"


def test_query_invalid_params_teaching():
    s = Session()
    r = s.query("get_sheet_state", {})
    assert not r["ok"] and r["error"]["type"] == "invalid_params"
    assert "example" in r["error"]


def test_save_and_load_round_trip(tmp_path):
    s = Session(project_name="SaveMe")
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [9, 9]})
    path = tmp_path / "doc.rdoc.json"
    assert s.query("save_document", {"path": str(path)})["ok"]
    s2 = Session.load(path)
    assert s2.doc.to_dict() == s.doc.to_dict()
