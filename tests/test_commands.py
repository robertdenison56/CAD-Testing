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


def test_title_block_templates():
    """create_sheet picks the border drawing; the document remembers it and
    the renderers all draw from the one place."""
    from roaddraft.render.titleblock import title_block_entities

    s = make_session()
    assert s.execute("create_sheet", {"name": "A"})["ok"]
    assert s.doc.sheet_by_ref("A").title_block_template == "standard"

    r = s.execute("create_sheet", {"name": "L-2", "size": "ANSI_D",
                                   "title_block_template": "caltrans"})
    assert r["ok"] and "caltrans" in r["message"]
    sheet = s.doc.sheet_by_ref("L-2")
    assert sheet.title_block_template == "caltrans"
    # the binding strip is on the left, and nothing is reserved at the bottom
    assert sheet.usable_area() == (1.904, 0.5, 33.5, 21.5)

    s.execute("fill_title_block", {"sheet": "L-2", "fields": {
        "dist": "03", "county": "But", "route": "70", "post_miles": "46.0/47.0",
        "sheet_number": "6", "total_sheets": "179", "sheet_title": "LAYOUT",
        "scale": "1\" = 50'", "sheet_id": "L-2", "seal_name": "J. KUSZ"}})
    drawn = {e.content for e in title_block_entities(sheet)
             if getattr(e, "content", None)}
    for value in ("03", "But", "70", "46.0/47.0", "6", "179", "LAYOUT", "L-2"):
        assert value in drawn, value
    assert "Dist" in drawn and "COUNTY" in drawn      # the grid captions

    r = s.execute("create_sheet", {"name": "N", "title_block_template": "none"})
    assert r["ok"]
    assert title_block_entities(s.doc.sheet_by_ref("N")) == []
    assert s.doc.sheet_by_ref("N").usable_area() == (0.5, 0.5, 33.5, 21.5)


def test_caltrans_border_letters_last_revision_and_plot_date_up_the_right_margin():
    """The panel in the right margin strip, as on the published sheets: the
    LAST REVISION box at the foot, the plot date and time lettered above it."""
    from roaddraft.document.entities import Line, Text
    from roaddraft.render.titleblock import CT_MARGIN, CT_PLOT_H, title_block_entities

    s = make_session()
    s.execute("create_sheet", {"name": "L-4", "size": "ANSI_D",
                               "title_block_template": "caltrans"})
    s.execute("fill_title_block", {"sheet": "L-4", "fields": {
        "last_revision": "00-00-00", "date_plotted": "DATE PLOTTED =>  29-DEC-2011",
        "time_plotted": "TIME PLOTTED =>  09:13"}})
    sheet = s.doc.sheet_by_ref("L-4")
    W = sheet.width_in
    drawn = title_block_entities(sheet)
    texts = {e.content: e for e in drawn if isinstance(e, Text)}
    top = CT_MARGIN + CT_PLOT_H
    for content in ("LAST REVISION", "00-00-00", "DATE PLOTTED =>  29-DEC-2011",
                    "TIME PLOTTED =>  09:13"):
        t = texts[content]
        assert W - CT_MARGIN < t.position[0] < W and t.rotation_deg == 90.0, content
    assert texts["LAST REVISION"].position[1] < top and texts["00-00-00"].position[1] < top
    assert texts["DATE PLOTTED =>  29-DEC-2011"].position[1] > top
    assert texts["TIME PLOTTED =>  09:13"].position[1] > top
    # the box: its foot and head across the margin, and the split between caption and value
    across = [e for e in drawn if isinstance(e, Line) and e.start[0] == W - CT_MARGIN
              and e.start[1] == e.end[1] and e.end[0] > W - CT_MARGIN]
    assert sorted(round(e.start[1], 3) for e in across) == [CT_MARGIN, round(top, 3)]
    assert any(isinstance(e, Line) and e.start[0] == e.end[0] == W - 0.351 for e in drawn)


def test_wfl_border_blocks_title_box_and_plot_stamp():
    """The FHWA Federal Lands (WFL) 11 x 17 border: PROJECT / SHEET NUMBER
    block at the top right (a STATE column when a state is given), the sheet
    title box at the bottom right only when there is a title, and the plot
    stamp lettered up the left margin."""
    from roaddraft.document.entities import Polyline, Text
    from roaddraft.render.titleblock import title_block_entities

    s = make_session()
    r = s.execute("create_sheet", {"name": "D.5", "size": "ANSI_B",
                                   "title_block_template": "wfl"})
    assert r["ok"] and "wfl" in r["message"]
    sheet = s.doc.sheet_by_ref("D.5")
    assert sheet.usable_area() == (0.7, 0.3, 16.3, 10.7)
    drawn = title_block_entities(sheet)
    boxes = [e for e in drawn if isinstance(e, Polyline) and e.closed]
    assert len(boxes) == 2                      # the frame and the title block
    assert "STATE" not in {e.content for e in drawn if isinstance(e, Text)}

    s.execute("fill_title_block", {"sheet": "D.5", "fields": {
        "project": "AK NPS SAMP 14(1)", "sheet_number": "D.5", "state": "AK",
        "nps_pmis": "NPS PMIS No. 123/123456", "nps_drawing": "NPS Drwg. No. 123456",
        "sheet_title": "PLAN AND PROFILE\nSheet 1 of 8", "scale": "NO SCALE",
        "date_plotted": "30 April 2025  1:41 PM",
        "dgn_file": "c:\\pw-work\\SamplePlan_pln_pp1.dgn",
        "description": "[PLAN AND PROFILE - 110+05 TO 115+00]"}})
    drawn = title_block_entities(sheet)
    texts = {e.content: e for e in drawn if isinstance(e, Text)}
    for value in ("STATE", "PROJECT", "SHEET", "NUMBER", "AK NPS SAMP 14(1)", "D.5",
                  "AK", "NPS PMIS No. 123/123456", "NPS Drwg. No. 123456",
                  "PLAN AND PROFILE", "Sheet 1 of 8", "NO SCALE"):
        assert value in texts, value
    assert texts["D.5"].position[0] > 15.9 and texts["D.5"].position[1] > 10.3
    assert texts["AK"].position[0] < texts["AK NPS SAMP 14(1)"].position[0]
    assert texts["NPS PMIS No. 123/123456"].position[1] > 10.7       # above the frame
    assert 12.3 < texts["PLAN AND PROFILE"].position[0] < 16.3
    assert texts["Sheet 1 of 8"].position[1] < texts["PLAN AND PROFILE"].position[1] < 1.3
    boxes = [e for e in drawn if isinstance(e, Polyline) and e.closed]
    assert len(boxes) == 3                      # plus the title box
    stamp = [texts[k] for k in ("30 April 2025  1:41 PM",
                                "c:\\pw-work\\SamplePlan_pln_pp1.dgn",
                                "[PLAN AND PROFILE - 110+05 TO 115+00]")]
    for t in stamp:
        assert t.rotation_deg == 90.0 and t.position[0] < 0.7
    assert stamp[0].position[1] < stamp[1].position[1] < stamp[2].position[1]


def test_title_block_template_must_be_known():
    s = make_session()
    r = s.execute("create_sheet", {"name": "X", "title_block_template": "acme"})
    assert not r["ok"] and "acme" in r["error"]["message"]


def test_title_block_template_survives_a_round_trip(tmp_path):
    from roaddraft.api.session import Session

    s = make_session(tmp_path)
    s.execute("create_sheet", {"name": "L-2", "title_block_template": "caltrans"})
    path = s.query("save_document", {"path": str(tmp_path / "plans.rdraft")})["path"]
    again = Session.load(path, out_dir=str(tmp_path))
    assert again.doc.sheet_by_ref("L-2").title_block_template == "caltrans"
