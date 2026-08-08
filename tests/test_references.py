import ezdxf

from roaddraft.api.session import Session


def make_basefile(tmp_path, name="base.rdoc.json"):
    base = Session(project_name="Survey Base", out_dir=str(tmp_path))
    base.execute("create_layer", {"name": "V-SURV-TOPO", "color": "green"})
    base.execute("draw_line", {"space": "model", "start": [900, 900],
                               "end": [2500, 900], "layer": "V-SURV-TOPO"})
    base.execute("draw_circle", {"space": "model", "center": [1500, 950],
                                 "radius": 25, "layer": "V-SURV-TOPO"})
    path = tmp_path / name
    base.query("save_document", {"path": str(path)})
    return path


def test_attach_and_list(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "SURVEY", "path": str(path),
                                       "space": "model"})
    assert r["ok"] and r["created"] == ["RF-001"]
    assert "2 entities" in r["message"]
    refs = s.query("list_references")["references"]
    assert refs[0]["name"] == "SURVEY" and refs[0]["status"] == "loaded"
    assert refs[0]["entities"] == 2


def test_attach_missing_file_fault(tmp_path):
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "GHOST",
                                       "path": str(tmp_path / "nope.json")})
    assert not r["ok"] and "file not found" in r["error"]["message"]
    assert s.doc.references == {}


def test_extents_include_references(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [10, 10]})
    assert s.query("get_extents", {"space": "model"})["extents"][2] == 10
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    assert s.query("get_extents", {"space": "model"})["extents"][2] == 2500
    s.execute("modify_reference", {"name": "SURVEY",
                                   "changes": {"visible": False}})
    assert s.query("get_extents", {"space": "model"})["extents"][2] == 10


def test_reference_offset_transform(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "S", "path": str(path),
                                   "offset": [1000.0, 0.0]})
    assert s.query("get_extents", {"space": "model"})["extents"][2] == 3500


def test_detach_and_modify(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"scale": 0}})
    assert not r["ok"]
    r = s.execute("detach_reference", {"name": "SURVEY"})
    assert r["ok"] and s.doc.references == {}
    r = s.execute("detach_reference", {"name": "SURVEY"})
    assert not r["ok"]


def test_reference_renders_into_sheet_and_model(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    s.execute("create_sheet", {"name": "C-101"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.6],
                                  "width_in": 31, "height_in": 18,
                                  "model_center": [1700, 925],
                                  "feet_per_inch": 50})
    r_with = s.query("render_sheet", {"sheet": "C-101", "dpi": 80})
    assert r_with["ok"]
    r_model = s.query("render_model", {"dpi": 80})
    assert r_model["ok"] and r_model["bounds"][2] > 2400
    # hiding the ref changes the sheet raster (it was actually drawn)
    s.execute("modify_reference", {"name": "SURVEY",
                                   "changes": {"visible": False}})
    r_without = s.query("render_sheet", {
        "sheet": "C-101", "dpi": 80, "path": str(tmp_path / "no_ref.png")})
    assert r_without["size_bytes"] != r_with["size_bytes"]


def test_reference_survives_save_load_and_undo(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    doc_path = tmp_path / "host.rdoc.json"
    s.query("save_document", {"path": str(doc_path)})
    s2 = Session.load(doc_path)
    assert s2.doc.references and s2.doc.to_dict() == s.doc.to_dict()
    refs = s2.query("list_references")["references"]
    assert refs[0]["status"] == "loaded"
    s2.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    s2.execute("undo", {})
    assert s2.query("list_references")["references"][0]["status"] == "loaded"


def test_reference_replay_determinism(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [5, 5]})
    journal = tmp_path / "j.jsonl"
    s.query("save_journal", {"path": str(journal)})
    replayed = Session.replay_journal(journal)
    assert replayed.doc.to_dict() == s.doc.to_dict()


def test_reference_bound_into_dxf(tmp_path):
    path = make_basefile(tmp_path)
    s = Session(out_dir=str(tmp_path))
    s.execute("attach_reference", {"name": "SURVEY", "path": str(path)})
    out = tmp_path / "host.dxf"
    s.query("export_dxf", {"path": str(out)})
    dxf = ezdxf.readfile(out)
    layer_names = {layer.dxf.name for layer in dxf.layers}
    assert "SURVEY$V-SURV-TOPO" in layer_names
    msp_layers = {e.dxf.layer for e in dxf.modelspace()}
    assert "SURVEY$V-SURV-TOPO" in msp_layers
