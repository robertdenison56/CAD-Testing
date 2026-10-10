"""Annotation scales: the scale list, paper-unit defaults, annotative records,
and re-sizing annotation for another plot scale."""
from __future__ import annotations

import json
import math

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.cli.repl import HELP
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.labels import compile_label
from roaddraft.document import annotation as anno
from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Text, as_annotative, entity_from_dict
from roaddraft.web.server import STATIC_DIR, WebApp

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def session_A() -> Session:
    s = Session(project_name="anno")
    assert s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                                          "pis": A_PIS})["ok"]
    return s


def alignment_A() -> Alignment:
    pis = [PI(p[:2], p[2] if len(p) == 3 else 0.0) for p in A_PIS]
    return Alignment(name="ALIGN-1", elements=compile_pis(pis), pis=pis, begin_station=1000.0)


def near(p, q, tol=1e-6):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


# ------------------------------------------------------------------ helpers


def test_parse_and_format_scale():
    assert anno.format_scale(50) == "1\"=50'"
    assert anno.format_scale(12.5) == "1\"=12.5'"
    for value in (50, 50.0, "50", "1\"=50'", '1"=50', "1in=50ft", "1 in = 50 ft", "1:600"):
        assert anno.parse_scale(value) == pytest.approx(50.0), value
    for bad in ("", "fifty", 0, -5, True, None, "1:0", [50]):
        with pytest.raises(ValueError):
            anno.parse_scale(bad)


def test_new_document_defaults_scale_off_and_legacy_docs_get_settings():
    doc = Document.new("x")
    assert doc.settings["annotation_scale"] is None
    assert [s["feet_per_inch"] for s in doc.settings["annotation_scales"]] == list(
        anno.DEFAULT_SCALES)
    assert doc.settings["annotation_paper"] == anno.DEFAULT_PAPER
    assert anno.model_sizes(doc) is None
    assert anno.size_defaults(doc) == {"text_height": 8.0, "tick_half_len": 10.0,
                                       "label_offset": 16.0}
    legacy = doc.to_dict()
    legacy["settings"] = {"current_layer": "0", "current_text_style": "STANDARD"}
    back = Document.from_dict(legacy)
    assert back.settings["annotation_scale"] is None and len(back.settings["annotation_scales"]) == 9
    assert back.settings["current_layer"] == "0"


def test_as_annotative_validation_and_round_trip():
    assert as_annotative(None) is None
    assert as_annotative({"scale": 50, "height_in": 0.1}) == {"scale": 50.0, "height_in": 0.1}
    for bad in ("x", {"height_in": 0.1}, {"scale": 0}, {"scale": 50, "bogus": 1},
                {"scale": 50, "height_in": -1}, {"scale": 50, "height_in": "0.1"},
                {"scale": True}, {"scale": 50, "half_len_in": 0},
                {"scale": 50, "offset_in": "0.2"}, {"scale": 50, "offset_in": float("nan")}):
        with pytest.raises(ValueError):
            as_annotative(bad)
    # a label offset is signed: negative is the other side of the line
    assert as_annotative({"scale": 50, "offset_in": -0.2}) == {"scale": 50.0, "offset_in": -0.2}
    assert as_annotative({"scale": 50, "offset_in": 0}) == {"scale": 50.0, "offset_in": 0.0}
    t = Text(id="TX-1", position=[0, 0], content="a", height=5,
             annotative={"scale": 50, "height_in": 0.1, "offset_in": 0.32})
    d = json.loads(json.dumps(t.to_dict()))
    assert d["annotative"] == {"scale": 50.0, "height_in": 0.1, "offset_in": 0.32}
    assert entity_from_dict(d).annotative == t.annotative
    assert t.translated([1, 1]).annotative == t.annotative
    assert "annotative" not in Line(id="L", start=[0, 0], end=[1, 0]).to_dict()


# ---------------------------------------------------------------- drafting


def test_scale_off_keeps_fixed_feet_defaults_and_stamps_nothing():
    s = session_A()
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    tick, label = (s.doc.model_entities[i] for i in r["created"][:2])
    assert label.height == 8.0 and label.annotative is None and tick.annotative is None
    assert math.hypot(tick.end[0] - tick.start[0], tick.end[1] - tick.start[1]) == pytest.approx(20)
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert s.doc.model_entities[r["created"][0]].height == 8.0
    assert s.doc.model_entities[r["created"][0]].annotative is None


def test_scale_on_sizes_from_paper_defaults_and_stamps_annotative():
    s = session_A()
    r = s.execute("set_annotation_scale", {"scale": "1\"=50'"})
    assert r["ok"], r
    assert "text 5 ft, ticks 10 ft, label offset 16 ft" in r["message"]
    assert r["modified"] == ["settings"] and s.doc.settings["annotation_scale"] == 50.0
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    tick, label = (s.doc.model_entities[i] for i in r["created"][:2])
    assert label.height == 5.0 and near(label.position, [1000.0, 1016.0])
    assert label.annotative == {"scale": 50.0, "height_in": 0.1, "offset_in": 0.32}
    assert tick.annotative == {"scale": 50.0, "half_len_in": 0.2}
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    pc = s.doc.model_entities[r["created"][0]]
    assert pc.height == 5.0 and near(pc.position, [1600.0, 984.0])
    assert pc.annotative == {"scale": 50.0, "height_in": 0.1, "offset_in": 0.32}
    # explicit feet still win, and are recorded at their paper equivalent
    r = s.execute("place_label", {"space": "model", "anchor": "PT-1", "height": 7.5,
                                  "label_offset": 25})
    pt = s.doc.model_entities[r["created"][0]]
    assert pt.height == 7.5 and pt.annotative == {"scale": 50.0, "height_in": 0.15,
                                                   "offset_in": 0.5}
    # plain model text is annotative too; sheet text is not
    r = s.execute("place_text", {"space": "model", "position": [0, 0], "content": "N",
                                 "height": 5})
    assert s.doc.model_entities[r["created"][0]].annotative == {"scale": 50.0, "height_in": 0.1}
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("place_text", {"space": "C-101", "position": [1, 1], "content": "N",
                                 "height": 0.1})
    assert s.doc.sheets["SH-001"].entities[r["created"][0]].annotative is None
    dry = s.query("resolve_anchor", {"anchor": "MC-1"})
    assert dry["height"] == 5.0 and dry["anchor"]["label_offset"] == 16.0


def test_entity_mode_stationing_honours_the_scale():
    s = Session()
    s.execute("set_annotation_scale", {"scale": 100})
    r = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [500, 0]})
    r = s.execute("annotate_stationing", {"space": "model", "path_ids": r["created"],
                                          "begin_station": 0})
    tick, label = (s.doc.model_entities[i] for i in r["created"][:2])
    assert label.height == 10.0 and near(label.position, [0.0, 32.0])
    assert near(tick.start, [0.0, -20.0]) and near(tick.end, [0.0, 20.0])
    assert label.annotative["offset_in"] == pytest.approx(0.32)


def test_negative_label_offset_letters_stations_right_and_the_file_reopens(tmp_path):
    # Caltrans letters stations right of the line. A negative label_offset swaps
    # the sides; each label records the side it is on, a positive offset, and
    # reads away from the line. The saved file opens again (it did not).
    s = session_A()
    s.execute("set_annotation_scale", {"scale": 50})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "label_offset": -16})
    assert r["ok"], r
    texts = [s.doc.model_entities[i] for i in r["created"]
             if isinstance(s.doc.model_entities[i], Text)]
    sta = next(t for t in texts if t.anchor["ref"] == "10+00.00")
    bc = next(t for t in texts if t.anchor["ref"] == "PC-1")
    assert near(sta.position, [1000.0, 984.0]) and sta.valign == "top"
    assert sta.anchor["side"] == "right" and sta.anchor["label_offset"] == 16.0
    assert sta.annotative == {"scale": 50.0, "height_in": 0.1, "offset_in": 0.32}
    assert near(bc.position, [1600.0, 1016.0]) and bc.valign == "bottom"
    assert bc.anchor["side"] == "left" and bc.annotative["offset_in"] == pytest.approx(0.32)

    path = s.query("save_document", {"path": str(tmp_path / "right.rdraft")})["path"]
    again = Session.load(path, out_dir=str(tmp_path))
    assert ({k: e.to_dict() for k, e in again.doc.model_entities.items()}
            == {k: e.to_dict() for k, e in s.doc.model_entities.items()})
    assert again.execute("modify_entity", {"id": sta.id, "changes": {"content": "0"}})["ok"]
    assert again.execute("set_annotation_scale", {"scale": 100})["ok"]
    sta = again.doc.model_entities[sta.id]
    assert near(sta.position, [1000.0, 968.0]) and sta.anchor["side"] == "right"
    assert sta.annotative["offset_in"] == pytest.approx(0.32)


def test_entity_mode_negative_label_offset_swaps_the_sides():
    s = Session()
    s.execute("set_annotation_scale", {"scale": 50})
    ids = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [500, 0]})["created"]
    ids += s.execute("draw_arc", {"space": "model", "center": [500, 500], "radius": 500,
                                  "start_angle_deg": -90, "end_angle_deg": 0})["created"]
    r = s.execute("annotate_stationing", {"space": "model", "path_ids": ids,
                                          "begin_station": 0, "label_offset": -10})
    texts = [s.doc.model_entities[i] for i in r["created"]
             if isinstance(s.doc.model_entities[i], Text)]
    sta = next(t for t in texts if t.content == "0+00.00")
    bc = next(t for t in texts if t.content.startswith("BC"))
    assert near(sta.position, [0.0, -10.0]) and sta.valign == "top"
    assert near(bc.position, [500.0, 10.0]) and bc.valign == "bottom"
    assert sta.annotative["offset_in"] == pytest.approx(0.2)
    assert Document.from_dict(s.doc.to_dict()).to_dict() == s.doc.to_dict()


def test_files_with_a_signed_offset_in_open_modify_undo_and_rescale(tmp_path):
    # Before annotate_stationing recorded side right, a right-hand station label
    # was saved as side left with a negative offset. Those files open, edit, undo,
    # and survive a failed command; a rescale re-places the label on the right
    # and records it the new way.
    s = session_A()
    s.execute("set_annotation_scale", {"scale": 50})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    sta = s.doc.model_entities[r["created"][1]]
    sta.position, sta.valign = [1000.0, 984.0], "bottom"
    sta.anchor = dict(sta.anchor, side="left", label_offset=-16.0)
    sta.annotative = {"scale": 50.0, "height_in": 0.1, "offset_in": -0.32}
    path = s.query("save_document", {"path": str(tmp_path / "old.rdraft")})["path"]

    again = Session.load(path, out_dir=str(tmp_path))
    assert again.doc.model_entities[sta.id].annotative["offset_in"] == -0.32
    assert again.execute("modify_entity", {"id": sta.id, "changes": {"content": "0"}})["ok"]
    r = again.execute("modify_entity", {"id": "TX-999", "changes": {"content": "x"}})
    assert not r["ok"] and again.doc.model_entities[sta.id].content == "0"

    assert again.execute("set_annotation_scale", {"scale": 100})["ok"]
    moved = again.doc.model_entities[sta.id]
    assert near(moved.position, [1000.0, 968.0]) and moved.valign == "bottom"
    assert moved.anchor["side"] == "right" and moved.anchor["label_offset"] == 32.0
    assert moved.annotative == {"scale": 100.0, "height_in": 0.1, "offset_in": 0.32}
    assert again.execute("undo", {})["ok"]
    back = again.doc.model_entities[sta.id]
    assert near(back.position, [1000.0, 984.0]) and back.annotative["offset_in"] == -0.32


# ---------------------------------------------------------------- rescale


def test_set_scale_rescales_text_ticks_and_replaces_anchored_labels():
    s = session_A()
    s.execute("set_annotation_scale", {"scale": 50})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    tick, sta = (s.doc.model_entities[i] for i in r["created"][:2])
    r = s.execute("place_label", {"space": "model", "anchor": "T-2"})
    bearing = s.doc.model_entities[r["created"][0]]
    r = s.execute("place_text", {"space": "model", "position": [1500, 900], "content": "NOTE",
                                 "height": 6})
    note = s.doc.model_entities[r["created"][0]]
    r = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [10, 0]})
    plain = s.doc.model_entities[r["created"][0]]
    n_annotative = sum(1 for e in s.doc.model_entities.values() if e.annotative)
    assert n_annotative == 34 + 2  # stationing + bearing + note; not the drawn line/arc/line

    r = s.execute("set_annotation_scale", {"scale": 100})
    assert r["ok"], r
    assert "annotation scale set to 1\"=100' (was 1\"=50')" in r["message"]
    assert f"{n_annotative} annotative entities rescaled" in r["message"]
    assert "settings" in r["modified"] and sta.id in r["modified"] and plain.id not in r["modified"]
    # station label: height doubled, re-placed 32 ft off the line, anchor updated
    assert sta.height == 10.0 and near(sta.position, [1000.0, 1032.0])
    assert sta.annotative == {"scale": 100.0, "height_in": 0.1, "offset_in": 0.32}
    assert sta.anchor["label_offset"] == 32.0
    # tick: 20 ft half-length about the same midpoint
    assert near(tick.start, [1000.0, 980.0]) and near(tick.end, [1000.0, 1020.0])
    assert tick.annotative == {"scale": 100.0, "half_len_in": 0.2}
    # bearing on T-2 re-placed through the design at 32 ft
    A = alignment_A()
    spec = compile_label(A, resolve_anchor(A, parse_anchor("T-2")), "bearing", label_offset=32.0)
    assert near(bearing.position, spec.position) and bearing.height == 10.0
    assert bearing.rotation_deg == pytest.approx(30.0, abs=1e-6)
    # plain annotative text keeps its insertion point, doubles its height
    assert note.position == [1500.0, 900.0] and note.height == 12.0
    assert note.annotative == {"scale": 100.0, "height_in": 0.12}
    # linework untouched
    assert plain.annotative is None and plain.end == [10.0, 0.0]
    # back to 50: everything returns
    s.execute("set_annotation_scale", {"scale": "1\"=50'"})
    assert sta.height == 5.0 and near(sta.position, [1000.0, 1016.0]) and note.height == 6.0
    assert near(tick.start, [1000.0, 990.0])


def test_rescale_false_and_off_leave_entities_alone():
    s = session_A()
    s.execute("set_annotation_scale", {"scale": 50})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    sta = s.doc.model_entities[r["created"][1]]
    r = s.execute("set_annotation_scale", {"scale": 100, "rescale": False})
    assert r["ok"] and r["modified"] == ["settings"] and sta.height == 5.0
    assert sta.annotative["scale"] == 50.0
    r = s.execute("set_annotation_scale", {"scale": None})
    assert r["ok"] and "turned off" in r["message"] and s.doc.settings["annotation_scale"] is None
    assert sta.height == 5.0
    r = s.execute("set_annotation_scale", {"scale": "off"})
    assert r["ok"]
    # drafting is back to the fixed defaults
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert s.doc.model_entities[r["created"][0]].height == 8.0
    # turning it on again rescales the stale 50-scale entities
    r = s.execute("set_annotation_scale", {"scale": 100})
    assert sta.height == 10.0 and sta.annotative["scale"] == 100.0


def test_adopt_stamps_legacy_annotation():
    s = session_A()
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    tick, sta = (s.doc.model_entities[i] for i in r["created"][:2])
    r = s.execute("place_text", {"space": "model", "position": [0, 0], "content": "N",
                                 "height": 4})
    note = s.doc.model_entities[r["created"][0]]
    r = s.execute("set_annotation_scale", {"scale": 50, "adopt": True})
    assert r["ok"] and "adopted" in r["message"]
    assert sta.annotative == {"scale": 50.0, "height_in": 0.16, "offset_in": 0.32}
    assert tick.annotative == {"scale": 50.0, "half_len_in": 0.2}
    assert note.annotative == {"scale": 50.0, "height_in": 0.08}
    s.execute("set_annotation_scale", {"scale": 25})
    assert sta.height == 4.0 and near(sta.position, [1000.0, 1008.0]) and note.height == 2.0
    assert near(tick.start, [1000.0, 995.0])


def test_unknown_scale_is_added_to_the_list_and_viewport_mismatch_warns():
    s = session_A()
    r = s.execute("set_annotation_scale", {"scale": "1:300"})
    assert r["ok"] and "(added to the scale list)" in r["message"]
    assert any(abs(x["feet_per_inch"] - 25.0) < 1e-9 for x in s.doc.settings["annotation_scales"])
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.7],
                                      "width_in": 31, "height_in": 18.5,
                                      "model_center": [1700, 1150], "feet_per_inch": 50})
    assert r["ok"] and r["warnings"] == [
        "VP-001 plots at 1\"=50' but the annotation scale is 1\"=25'; model annotation will "
        "appear at 0.5x its paper size (set_annotation_scale 50 to match)"]
    r = s.execute("set_annotation_scale", {"scale": 100})
    assert r["warnings"] and "VP-001 on sheet C-101 plots at 1\"=50'" in r["warnings"][0]
    r = s.execute("set_annotation_scale", {"scale": 50})
    assert r["warnings"] == []
    r = s.execute("set_annotation_scale", {"scale": "fifty"})
    assert not r["ok"] and "cannot parse scale" in r["error"]["message"]
    assert "1\"=50'" in r["error"]["hint"]


def test_add_delete_scale_and_defaults():
    s = Session()
    r = s.execute("add_annotation_scale", {"scale": 25})
    assert r["ok"] and r["created"] == ["scale:1\"=25'"]
    names = [x["name"] for x in s.doc.settings["annotation_scales"]]
    assert names.index("1\"=25'") == names.index("1\"=30'") - 1
    r = s.execute("add_annotation_scale", {"scale": "1\"=25'"})
    assert not r["ok"] and "already exists" in r["error"]["message"]
    r = s.execute("add_annotation_scale", {"scale": "1:300", "name": "SITE"})
    assert not r["ok"] and "already exists as" in r["error"]["message"]
    r = s.execute("add_annotation_scale", {"scale": 75, "name": "1\"=75'"})
    assert r["ok"]
    s.execute("set_annotation_scale", {"scale": 75})
    r = s.execute("delete_annotation_scale", {"scale": 75})
    assert not r["ok"] and "current annotation scale" in r["error"]["message"]
    r = s.execute("delete_annotation_scale", {"scale": "1\"=25'"})
    assert r["ok"] and r["deleted"] == ["scale:1\"=25'"]
    r = s.execute("delete_annotation_scale", {"scale": 999})
    assert not r["ok"] and "no annotation scale" in r["error"]["message"]
    r = s.execute("set_annotation_defaults", {"text_height_in": 0.12, "label_offset_in": 0.4})
    assert r["ok"] and "text_height_in = 0.12 in (9 ft at 1\"=75')" in r["message"]
    assert anno.model_sizes(s.doc) == {"text_height": 9.0, "tick_half_len": 15.0,
                                       "label_offset": 30.0}
    r = s.execute("set_annotation_defaults", {})
    assert not r["ok"]
    r = s.execute("set_annotation_defaults", {"tick_half_len_in": -1})
    assert not r["ok"] and r["error"]["type"] == "invalid_params"


def test_modify_entity_annotative_and_replay(tmp_path):
    s = session_A()
    s.execute("set_annotation_scale", {"scale": 50})
    r = s.execute("place_text", {"space": "model", "position": [0, 0], "content": "N",
                                 "height": 5})
    tid = r["created"][0]
    r = s.execute("modify_entity", {"id": tid, "changes": {"annotative": {"scale": 50,
                                                                          "height_in": 0.2}}})
    assert r["ok"]
    s.execute("set_annotation_scale", {"scale": 100})
    assert s.doc.model_entities[tid].height == 20.0
    r = s.execute("modify_entity", {"id": tid, "changes": {"annotative": {"bad": 1}}})
    assert not r["ok"] and "annotative:" in r["error"]["message"]
    r = s.execute("modify_entity", {"id": tid, "changes": {"annotative": None}})
    assert r["ok"] and s.doc.model_entities[tid].annotative is None
    s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    s.execute("set_annotation_scale", {"scale": 20, "adopt": True})
    s.execute("undo", {})
    assert s.doc.settings["annotation_scale"] == 100.0
    s.execute("redo", {})
    assert s.doc.settings["annotation_scale"] == 20.0
    path = tmp_path / "anno.jsonl"
    s.query("save_journal", {"path": str(path)})
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()


# ------------------------------------------------------ query / repl / gui


def test_list_annotation_scales_query_and_summary():
    s = session_A()
    r = s.query("list_annotation_scales")
    assert r["ok"] and r["current"] is None and r["current_name"] == "off"
    assert len(r["scales"]) == 9 and r["paper"] == anno.DEFAULT_PAPER
    assert r["model_sizes"] == anno.FIXED_MODEL_SIZES and r["annotative_entities"] == 0
    s.execute("set_annotation_scale", {"scale": 50})
    s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    r = s.query("list_annotation_scales")
    assert r["current"] == 50.0 and r["current_name"] == "1\"=50'"
    assert r["model_sizes"] == {"text_height": 5.0, "tick_half_len": 10.0, "label_offset": 16.0}
    assert r["annotative_entities"] == 34
    assert s.query("get_document_state")["summary"]["annotation_scale"] == 50.0


def test_repl_verbs_and_help():
    s = session_A()
    r = route_line(s, "annoscale 100", "model")
    assert r["result"]["ok"] and s.doc.settings["annotation_scale"] == 100.0
    r = route_line(s, "annoscales", "model")
    assert r["result"]["ok"] and r["result"]["current"] == 100.0
    r = route_line(s, "annoadd 25", "model")
    assert r["result"]["ok"]
    r = route_line(s, "annodel 25", "model")
    assert r["result"]["ok"]
    r = route_line(s, "annopaper text_height_in=0.12", "model")
    assert r["result"]["ok"]
    r = route_line(s, "annoscale off", "model")
    assert r["result"]["ok"] and s.doc.settings["annotation_scale"] is None
    for verb in ("annoscale", "annoscales", "annoadd", "annodel", "annopaper"):
        assert verb in HELP


def test_web_state_and_gui_selector():
    app = WebApp(session_A())
    a = app.state()["annotation"]
    assert a["scale"] is None and a["name"] == "off" and len(a["scales"]) == 9
    assert a["model_sizes"] == anno.FIXED_MODEL_SIZES
    app.execute("set_annotation_scale", {"scale": 50})
    a = app.state()["annotation"]
    assert a["scale"] == 50.0 and a["name"] == "1\"=50'" and a["model_sizes"]["text_height"] == 5.0
    html = (STATIC_DIR / "index.html").read_text()
    assert 'id="st-annoscale"' in html and 'command: "set_annotation_scale"' in html
    assert "S.state.annotation.model_sizes" in html
