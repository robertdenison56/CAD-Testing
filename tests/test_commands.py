import json

from roaddraft.api.session import Session


def make_session(tmp_path=None):
    return Session(project_name="cmd-tests",
                   out_dir=str(tmp_path) if tmp_path else None)


def test_draw_line_creates_entity():
    s = make_session()
    r = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [10, 5]})
    assert r["ok"] and r["created"] == ["LN-001"]
    assert "LN-001" in s.doc.model_entities
    assert len(s.bus.journal) == 1


def test_invalid_params_teaching_error():
    s = make_session()
    r = s.execute("draw_line", {"space": "model", "start": [0, 0]})  # missing end
    assert not r["ok"]
    assert r["error"]["type"] == "invalid_params"
    assert "end" in r["error"]["message"]
    assert "example" in r["error"] and "valid_params_schema" in r["error"]
    assert len(s.bus.journal) == 0  # invalid calls are not journaled


def test_unknown_command_suggestions():
    s = make_session()
    r = s.execute("draw_lin", {})
    assert not r["ok"] and r["error"]["type"] == "unknown_command"
    assert "draw_line" in r["error"]["hint"]


def test_fault_is_atomic():
    s = make_session()
    r = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1],
                                "layer": "NOPE"})
    assert not r["ok"] and r["error"]["type"] == "command_failed"
    assert "create_layer" in r["error"]["hint"]
    assert len(s.doc.model_entities) == 0


def test_move_multiple_atomic_on_missing_id():
    s = make_session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    r = s.execute("move_entities", {"ids": ["LN-001", "LN-999"], "delta": [5, 5]})
    assert not r["ok"]
    assert s.doc.model_entities["LN-001"].start == [0, 0]  # untouched


def test_current_layer_applied():
    s = make_session()
    s.execute("create_layer", {"name": "V-ALIGN-CNTR", "color": "red"})
    s.execute("set_current_layer", {"name": "V-ALIGN-CNTR"})
    r = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    assert s.doc.model_entities[r["created"][0]].layer == "V-ALIGN-CNTR"


def test_aliases_resolve():
    s = make_session()
    r = s.execute("LINE", {"space": "model", "start": [0, 0], "end": [1, 1]})
    assert r["ok"] and r["name"] == "draw_line"
    r = s.execute("ERASE", {"ids": r["created"]})
    assert r["ok"] and r["name"] == "delete_entities"
    assert len(s.doc.model_entities) == 0


def test_undo_redo_cycle():
    s = make_session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    s.execute("draw_circle", {"space": "model", "center": [5, 5], "radius": 2})
    assert len(s.doc.model_entities) == 2
    r = s.execute("undo", {})
    assert r["ok"] and "draw_circle" in r["message"]
    assert len(s.doc.model_entities) == 1
    r = s.execute("redo", {})
    assert r["ok"] and len(s.doc.model_entities) == 2
    assert [e["name"] for e in s.bus.journal] == \
        ["draw_line", "draw_circle", "undo", "redo"]


def test_undo_empty():
    s = make_session()
    r = s.execute("undo", {})
    assert not r["ok"] and r["error"]["type"] == "nothing_to_undo"


def test_sheet_viewport_titleblock_flow():
    s = make_session()
    r = s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    assert r["ok"] and r["created"] == ["SH-001"]
    r = s.execute("create_sheet", {"name": "C-101"})
    assert not r["ok"]  # duplicate name
    r = s.execute("create_viewport", {
        "sheet": "C-101", "center_paper": [17, 12], "width_in": 31,
        "height_in": 18, "model_center": [1700, 1150], "feet_per_inch": 50})
    assert r["ok"] and r["created"] == ["VP-001"]
    r = s.execute("fill_title_block", {"sheet": "C-101",
                                       "fields": {"project": "SR 100"}})
    assert r["ok"]
    assert s.doc.sheet_by_ref("C-101").title_block_fields["project"] == "SR 100"


def test_viewport_outside_usable_area_warns():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r = s.execute("create_viewport", {
        "sheet": "C-101", "center_paper": [17, 1.0], "width_in": 10,
        "height_in": 4, "model_center": [0, 0], "feet_per_inch": 50})
    assert r["ok"] and any("usable area" in w for w in r["warnings"])


def test_text_overlap_and_offsheet_warnings():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r1 = s.execute("place_text", {"space": "C-101", "position": [10, 10],
                                  "content": "HELLO", "height": 0.2})
    assert r1["ok"] and r1["warnings"] == []
    r2 = s.execute("place_text", {"space": "C-101", "position": [10.1, 10.05],
                                  "content": "WORLD", "height": 0.2})
    assert r2["ok"] and any("overlaps TX-001" in w for w in r2["warnings"])
    r3 = s.execute("place_text", {"space": "C-101", "position": [33.8, 10],
                                  "content": "EDGE RUNNER", "height": 0.2})
    assert r3["ok"] and any("beyond" in w for w in r3["warnings"])


def test_table_row_length_fault():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_table", {
        "space": "C-101", "position": [5, 10],
        "columns": [{"header": "A", "width": 1}, {"header": "B", "width": 1}],
        "rows": [["only-one"]]})
    assert not r["ok"] and "2 columns" in r["error"]["message"]


def test_modify_entity():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_text", {"space": "C-101", "position": [5, 5],
                                 "content": "OLD", "height": 0.2})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid, "changes": {"content": "NEW",
                                                           "height": 0.3}})
    assert r["ok"]
    entity = s.doc.sheet_by_ref("C-101").entities[eid]
    assert entity.content == "NEW" and entity.height == 0.3
    r = s.execute("modify_entity", {"id": eid, "changes": {"type": "line"}})
    assert not r["ok"]


def test_modify_entity_text_editing_fields():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_text", {"space": "C-101", "position": [5, 5],
                                 "content": "OLD", "height": 0.2})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid, "changes": {
        "content": "LINE ONE\nLINE TWO", "halign": "center",
        "valign": "middle", "rotation_deg": 30.0, "height": 0.25}})
    assert r["ok"]
    e = s.doc.sheet_by_ref("C-101").entities[eid]
    assert e.content == "LINE ONE\nLINE TWO"
    assert e.halign == "center" and e.valign == "middle"
    assert e.rotation_deg == 30.0 and e.height == 0.25


def test_modify_entity_color_override_and_clear():
    s = make_session()
    r = s.execute("draw_line", {"space": "model", "start": [0, 0],
                                "end": [1, 1]})
    eid = r["created"][0]
    assert s.execute("modify_entity", {"id": eid,
                                       "changes": {"color": "red"}})["ok"]
    assert s.doc.model_entities[eid].color == "red"
    assert s.execute("modify_entity", {"id": eid,
                                       "changes": {"color": None}})["ok"]
    assert s.doc.model_entities[eid].color is None  # back to ByLayer
    r = s.execute("modify_entity", {"id": eid,
                                    "changes": {"color": "not-a-color"}})
    assert not r["ok"]


def test_modify_entity_table_cells_and_headers():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_table", {
        "space": "C-101", "position": [5, 10], "title": "CURVE DATA",
        "columns": [{"header": "CURVE", "width": 1.0},
                    {"header": "R", "width": 1.2}],
        "rows": [["C-1", "800.00'"]]})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid, "changes": {
        "title": "CURVE TABLE",
        "columns": [{"header": "NO.", "width": 1.0},
                    {"header": "RADIUS", "width": 1.2}],
        "rows": [["C-1", "800.00'"], ["C-2", "1200.00'"]]}})
    assert r["ok"]
    e = s.doc.sheet_by_ref("C-101").entities[eid]
    assert e.title == "CURVE TABLE"
    assert [c["header"] for c in e.columns] == ["NO.", "RADIUS"]
    assert e.rows[1] == ["C-2", "1200.00'"]


def test_modify_entity_rejects_corrupt_geometry():
    """Review finding: strings iterate, so list('6,7') would silently store a
    char-list. All geometry must coerce or fault cleanly."""
    s = make_session()
    r = s.execute("draw_circle", {"space": "model", "center": [5, 5],
                                  "radius": 3})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid, "changes": {"center": "6,7"}})
    assert not r["ok"] and r["error"]["type"] == "command_failed"
    assert s.doc.model_entities[eid].center == [5, 5]  # untouched
    r = s.execute("modify_entity", {"id": eid, "changes": {"radius": -5}})
    assert not r["ok"] and "positive" in r["error"]["message"]
    r = s.execute("modify_entity", {"id": eid, "changes": {"radius": 0}})
    assert not r["ok"]


def test_modify_entity_rejects_bad_enums_and_heights():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_text", {"space": "C-101", "position": [5, 5],
                                 "content": "X", "height": 0.2})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid,
                                    "changes": {"halign": "sideways"}})
    assert not r["ok"] and "halign" in r["error"]["message"]
    r = s.execute("modify_entity", {"id": eid, "changes": {"height": 0}})
    assert not r["ok"]
    e = s.doc.sheet_by_ref("C-101").entities[eid]
    assert e.halign == "left" and e.height == 0.2


def test_modify_entity_rejects_unknown_fields_and_ghost_blocks():
    s = make_session()
    r = s.execute("place_text", {"space": "model", "position": [0, 0],
                                 "content": "X", "height": 5})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid, "changes": {"contnet": "Y"}})
    assert not r["ok"] and "contnet" in r["error"]["message"]
    assert "content" in r["error"]["hint"]
    r = s.execute("insert_block", {"space": "model",
                                   "block_name": "NORTH_ARROW",
                                   "position": [10, 10]})
    bid = r["created"][0]
    r = s.execute("modify_entity", {"id": bid,
                                    "changes": {"block_name": "GHOST"}})
    assert not r["ok"] and "GHOST" in r["error"]["message"]


def test_modify_entity_rejects_wrong_table_row_length():
    s = make_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_table", {
        "space": "C-101", "position": [5, 10],
        "columns": [{"header": "A", "width": 1}, {"header": "B", "width": 1}],
        "rows": [["a", "b"]]})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid,
                                    "changes": {"rows": [["only-one"]]}})
    assert not r["ok"] and "2 columns" in r["error"]["message"]
    assert s.doc.sheet_by_ref("C-101").entities[eid].rows == [["a", "b"]]


def test_modify_entity_bad_geometry_is_atomic():
    s = make_session()
    r = s.execute("draw_circle", {"space": "model", "center": [5, 5],
                                  "radius": 3})
    eid = r["created"][0]
    r = s.execute("modify_entity", {"id": eid,
                                    "changes": {"radius": "huge"}})
    assert not r["ok"]
    assert s.doc.model_entities[eid].radius == 3  # untouched


def test_define_and_insert_block():
    s = make_session()
    r = s.execute("define_block", {"name": "MON", "entities": [
        {"type": "circle", "center": [0, 0], "radius": 0.5},
        {"type": "line", "start": [-0.5, 0], "end": [0.5, 0]}]})
    assert r["ok"]
    r = s.execute("insert_block", {"space": "model", "block_name": "MON",
                                   "position": [100, 100], "scale": 2.0})
    assert r["ok"]
    bb = s.doc.model_entities[r["created"][0]].bbox(s.doc)
    assert abs(bb[0] - 99.0) < 1e-9 and abs(bb[2] - 101.0) < 1e-9
    r = s.execute("insert_block", {"space": "model", "block_name": "GHOST",
                                   "position": [0, 0]})
    assert not r["ok"] and "MON" in r["error"]["hint"]


def test_replay_determinism(tmp_path):
    s = make_session(tmp_path)
    s.execute("create_layer", {"name": "CL", "color": "red"})
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0],
                            "layer": "CL"})
    s.execute("create_sheet", {"name": "C-101"})
    s.execute("place_text", {"space": "C-101", "position": [5, 5],
                             "content": "PLAN", "height": 0.25})
    s.execute("draw_circle", {"space": "model", "center": [50, 0], "radius": 10})
    s.execute("undo", {})
    journal_path = tmp_path / "j.jsonl"
    r = s.query("save_journal", {"path": str(journal_path)})
    assert r["ok"]
    replayed = Session.replay_journal(journal_path)
    assert replayed.doc.to_dict() == s.doc.to_dict()
    # journal is plain JSON all the way down
    for line in journal_path.read_text().splitlines():
        json.loads(line)
