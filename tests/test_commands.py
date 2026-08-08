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
