"""MicroStation-style reference attachment features: per-attachment level
display, symbology overrides, clip boundary and masks, locate on reference
elements, host-relative paths, and true scale between unit systems."""
import shutil

import ezdxf

from roaddraft.api.session import Session
from roaddraft.commands.bus import CommandBus
from roaddraft.web.server import WebApp


def make_basefile(path, units=None):
    base = Session(project_name="Survey Base", out_dir=str(path.parent))
    if units:
        base.execute("set_meta", {"updates": {"model_units": units}})
    base.execute("create_layer", {"name": "V-SURV-TOPO", "color": "green"})
    base.execute("create_layer", {"name": "V-SURV-TREE", "color": "blue"})
    base.execute("draw_line", {"space": "model", "start": [900, 900],
                               "end": [2500, 900], "layer": "V-SURV-TOPO"})
    base.execute("draw_circle", {"space": "model", "center": [1500, 950],
                                 "radius": 25, "layer": "V-SURV-TREE"})
    base.execute("place_text", {"space": "model", "position": [1800, 920],
                                "content": "EP", "height": 5,
                                "layer": "V-SURV-TOPO"})
    path.parent.mkdir(parents=True, exist_ok=True)
    base.query("save_document", {"path": str(path)})
    return path


def host_with_survey(tmp_path, **attach):
    path = make_basefile(tmp_path / "base.rdoc.json")
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "SURVEY", "path": str(path),
                                       **attach})
    assert r["ok"], r
    return s


def hits(s, point, **extra):
    return s.query("hit_test", {"space": "model", "point": point,
                                "tolerance": 2.0, **extra})["hits"]


# ------------------------------------------------------------- locate


def test_hit_test_locates_reference_elements_read_only(tmp_path):
    s = host_with_survey(tmp_path)
    found = hits(s, [1500, 975])
    assert found and found[0]["id"] == "SURVEY:CI-001"
    assert found[0]["reference"] == "SURVEY" and found[0]["read_only"] is True
    assert found[0]["layer"] == "V-SURV-TREE"
    assert hits(s, [1500, 975], include_references=False) == []
    info = s.query("get_entity", {"id": "SURVEY:CI-001"})
    assert info["ok"] and info["read_only"] and info["reference"] == "SURVEY"
    assert info["entity"]["center"] == [1500, 950] and info["space"] == "model"
    missing = s.query("get_entity", {"id": "SURVEY:ZZ-999"})
    assert not missing["ok"] and "REFNAME:ID" in missing["error"]["hint"]
    # host entities win the sort when nearer; reference elements are not editable
    s.execute("draw_line", {"space": "model", "start": [1500, 976],
                            "end": [1600, 976]})
    assert hits(s, [1500, 976])[0]["id"] == "LN-001"
    r = s.execute("modify_entity", {"id": "SURVEY:CI-001",
                                    "changes": {"radius": 1}})
    assert not r["ok"]


# ----------------------------------------------------------- levels


def test_levels_off_per_attachment(tmp_path):
    s = host_with_survey(tmp_path)
    assert s.query("get_extents", {"space": "model"})["extents"][3] == 975
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"levels_off": ["V-SURV-TREE"]}})
    assert r["ok"] and "levels off: ['V-SURV-TREE']" in r["message"]
    assert hits(s, [1500, 975]) == []                      # circle level is off
    assert hits(s, [1200, 900])[0]["id"] == "SURVEY:LN-001"  # topo still there
    assert s.query("get_extents", {"space": "model"})["extents"][3] == 925
    levels = {lv["name"]: lv for lv in
              s.query("list_references")["references"][0]["levels"]}
    assert levels["V-SURV-TREE"]["on"] is False and levels["V-SURV-TREE"]["entities"] == 1
    assert levels["V-SURV-TOPO"]["on"] is True and levels["V-SURV-TOPO"]["entities"] == 2
    # the basefile's own level visibility is untouched
    assert levels["V-SURV-TREE"]["visible_in_basefile"] is True
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"levels_off": ["NOPE"]}})
    assert not r["ok"] and "V-SURV-TOPO" in r["error"]["hint"]
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"levels_off": []}})
    assert r["ok"] and "all levels on" in r["message"]
    assert hits(s, [1500, 975])[0]["id"] == "SURVEY:CI-001"


def test_levels_off_exported_to_dxf_on_off_layers(tmp_path):
    s = host_with_survey(tmp_path, levels_off=["V-SURV-TREE"])
    out = tmp_path / "host.dxf"
    s.query("export_dxf", {"path": str(out)})
    dxf = ezdxf.readfile(out)
    assert dxf.layers.get("SURVEY$V-SURV-TREE").is_off()
    assert not dxf.layers.get("SURVEY$V-SURV-TOPO").is_off()
    circles = [e for e in dxf.modelspace() if e.dxftype() == "CIRCLE"]
    assert circles and circles[0].dxf.layer == "SURVEY$V-SURV-TREE"


# -------------------------------------------------------- symbology


def test_symbology_gray_out_and_overrides(tmp_path):
    s = host_with_survey(tmp_path)
    before = s.query("render_model", {"dpi": 60, "path": str(tmp_path / "a.png")})
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"symbology": {"gray": True}}})
    assert r["ok"] and "gray=True" in r["message"]
    assert s.query("get_entity", {"id": "SURVEY:LN-001"})["entity"]["color"] == "#9E9E9E"
    after = s.query("render_model", {"dpi": 60, "path": str(tmp_path / "b.png")})
    assert after["size_bytes"] != before["size_bytes"]
    r = s.execute("modify_reference", {"name": "SURVEY", "changes": {"symbology": {
        "color": "red", "linetype": "dashed", "lineweight_mm": 0.5}}})
    assert r["ok"]
    e = s.query("get_entity", {"id": "SURVEY:LN-001"})["entity"]
    assert e["color"] == "red" and e["linetype"] == "dashed"
    out = tmp_path / "host.dxf"
    s.query("export_dxf", {"path": str(out)})
    line = next(e for e in ezdxf.readfile(out).modelspace() if e.dxftype() == "LINE")
    assert line.dxf.color == 1 and line.dxf.linetype == "DASHED"
    assert line.dxf.lineweight == 50
    for bad in ({"color": "nope"}, {"linetype": "wavy"}, {"gray": "yes"},
                {"bogus": 1}, {"lineweight_mm": -1}):
        assert not s.execute("modify_reference", {"name": "SURVEY",
                                                  "changes": {"symbology": bad}})["ok"]
    r = s.execute("modify_reference", {"name": "SURVEY",
                                       "changes": {"symbology": None}})
    assert r["ok"] and "cleared" in r["message"]
    assert s.query("get_entity", {"id": "SURVEY:LN-001"})["entity"].get("color") is None


# ------------------------------------------------------------- clip


def test_clip_boundary_clips_geometry_everywhere(tmp_path):
    window = [[1000, 800], [2000, 800], [2000, 1000], [1000, 1000]]
    s = host_with_survey(tmp_path, clip=window)
    piece = s.query("get_entity", {"id": "SURVEY:LN-001#1"})
    assert piece["ok"] and piece["entity"]["start"] == [1000, 900]
    assert piece["entity"]["end"] == [2000, 900]
    assert s.query("get_extents", {"space": "model"})["extents"] == (1000, 900, 2000, 975)
    assert hits(s, [950, 900]) == []
    assert hits(s, [1500, 900])[0]["id"] == "SURVEY:LN-001#1"
    out = tmp_path / "host.dxf"
    s.query("export_dxf", {"path": str(out)})
    line = next(e for e in ezdxf.readfile(out).modelspace() if e.dxftype() == "LINE")
    assert tuple(line.dxf.start)[:2] == (1000, 900) and tuple(line.dxf.end)[:2] == (2000, 900)
    r = s.execute("modify_reference", {"name": "SURVEY", "changes": {"clip": None}})
    assert r["ok"] and "clip boundary cleared" in r["message"]
    assert s.query("get_extents", {"space": "model"})["extents"][2] == 2500


def test_clip_masks_hide_inside(tmp_path):
    s = host_with_survey(tmp_path)
    mask = [[1400, 850], [1600, 850], [1600, 1000], [1400, 1000]]
    r = s.execute("modify_reference", {"name": "SURVEY", "changes": {"masks": [mask]}})
    assert r["ok"] and "1 clip mask(s)" in r["message"]
    assert hits(s, [1500, 975]) == []                 # circle sits inside the mask
    assert hits(s, [1500, 900]) == []                 # so does this part of the line
    assert hits(s, [1000, 900])[0]["id"] == "SURVEY:LN-001#1"
    assert hits(s, [2000, 900])[0]["id"] == "SURVEY:LN-001#2"
    assert s.query("get_entity", {"id": "SURVEY:LN-001#2"})["entity"]["start"] == [1600, 900]
    s.execute("modify_reference", {"name": "SURVEY", "changes": {"masks": []}})
    assert hits(s, [1500, 900])[0]["id"] == "SURVEY:LN-001"


def test_clip_validation_and_replay(tmp_path):
    s = host_with_survey(tmp_path)
    assert not s.execute("modify_reference", {"name": "SURVEY",
                                              "changes": {"clip": [[0, 0], [1, 1]]}})["ok"]
    assert not s.execute("modify_reference", {"name": "SURVEY",
                                              "changes": {"masks": "nope"}})["ok"]
    assert not s.execute("modify_reference", {"name": "SURVEY",
                                              "changes": {"true_scale": "yes"}})["ok"]
    s.execute("modify_reference", {"name": "SURVEY", "changes": {
        "clip": [[1000, 800], [2000, 800], [2000, 1000]],
        "masks": [[[1400, 850], [1600, 850], [1600, 1000]]],
        "levels_off": ["V-SURV-TREE"], "symbology": {"gray": True},
        "true_scale": False}})
    doc_path = tmp_path / "host.rdoc.json"
    s.query("save_document", {"path": str(doc_path)})
    loaded = Session.load(doc_path)
    assert loaded.doc.to_dict() == s.doc.to_dict()
    ref = loaded.doc.to_dict()["references"]["RF-001"]
    assert ref["clip"] and len(ref["masks"]) == 1 and ref["levels_off"] == ["V-SURV-TREE"]
    assert ref["symbology"] == {"gray": True} and ref["true_scale"] is False
    journal = tmp_path / "j.jsonl"
    s.query("save_journal", {"path": str(journal)})
    assert Session.replay_journal(journal).doc.to_dict() == s.doc.to_dict()


# ------------------------------------------------------------ paths


def test_relative_path_resolves_against_host_folder(tmp_path, monkeypatch):
    project = tmp_path / "project"
    make_basefile(project / "survey" / "base.rdoc.json")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "SURVEY",
                                       "path": "survey/base.rdoc.json"})
    assert not r["ok"] and "file not found" in r["error"]["message"]
    assert "no path yet" in r["error"]["hint"]
    s.query("save_document", {"path": str(project / "host.rdoc.json")})
    r = s.execute("attach_reference", {"name": "SURVEY",
                                       "path": "survey/base.rdoc.json"})
    assert r["ok"], r
    info = s.query("list_references")["references"][0]
    assert info["status"] == "loaded" and info["path_is_relative"] is True
    assert info["path"] == "survey/base.rdoc.json"
    assert info["resolved_path"] == str(project / "survey" / "base.rdoc.json")
    # undo/redo keep the host path, so the relative reference still resolves
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})
    s.execute("undo", {})
    assert s.query("list_references")["references"][0]["status"] == "loaded"
    # the project moves as a whole: the link follows
    s.query("save_document", {"path": str(project / "host.rdoc.json")})
    moved = tmp_path / "moved"
    shutil.move(str(project), str(moved))
    again = Session.load(moved / "host.rdoc.json")
    info = again.query("list_references")["references"][0]
    assert info["status"] == "loaded"
    assert info["resolved_path"] == str(moved / "survey" / "base.rdoc.json")
    # a bad relative path reports where it looked
    r = again.execute("modify_reference", {"name": "SURVEY",
                                           "changes": {"path": "missing.json"}})
    assert not r["ok"] and str(moved) in r["error"]["message"]


# ------------------------------------------------------------ units


def test_true_scale_converts_metric_basefile(tmp_path):
    metric = tmp_path / "metric.rdoc.json"
    m = Session(project_name="Metric", out_dir=str(tmp_path))
    m.execute("set_meta", {"updates": {"model_units": "m"}})
    m.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    m.query("save_document", {"path": str(metric)})
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "TOPO", "path": str(metric)})
    assert r["ok"] and "true scale x3.28083" in r["message"] and r["warnings"] == []
    end = s.query("get_entity", {"id": "TOPO:LN-001"})["entity"]["end"]
    assert abs(end[0] - 100 * 3937.0 / 1200.0) < 1e-9
    units = s.query("list_references")["references"][0]["units"]
    assert units["base"] == "m" and units["host"] == "us_survey_ft"
    assert abs(units["factor"] - 3937.0 / 1200.0) < 1e-12
    r = s.execute("modify_reference", {"name": "TOPO",
                                       "changes": {"true_scale": False}})
    assert r["ok"]
    assert s.query("get_entity", {"id": "TOPO:LN-001"})["entity"]["end"] == [100, 0]
    units = s.query("list_references")["references"][0]["units"]
    assert units["factor"] == 1.0 and "true_scale is off" in units["warning"]


def test_true_scale_into_sheet_uses_paper_inches(tmp_path):
    path = make_basefile(tmp_path / "base.rdoc.json")
    s = Session(out_dir=str(tmp_path))
    s.execute("create_sheet", {"name": "C-101"})
    # 1" = 50' is 1:600 in MicroStation terms: feet -> inches x12, then 1/600
    r = s.execute("attach_reference", {"name": "SURVEY", "path": str(path),
                                       "space": "C-101", "scale": 1 / 600,
                                       "offset": [2.0, 3.0]})
    assert r["ok"] and "(us_survey_ft -> inch)" in r["message"]
    line = s.query("get_entity", {"id": "SURVEY:LN-001"})["entity"]
    assert abs(line["end"][0] - line["start"][0] - 1600 * 12.000024 / 600) < 1e-6
    assert abs(line["start"][1] - (3.0 + 900 * 12.000024 / 600)) < 1e-6


def test_unknown_or_missing_units_warn_and_place_1_to_1(tmp_path):
    odd = tmp_path / "odd.rdoc.json"
    o = Session(project_name="Odd", out_dir=str(tmp_path))
    o.execute("set_meta", {"updates": {"model_units": "furlongs"}})
    o.execute("draw_line", {"space": "model", "start": [0, 0], "end": [10, 0]})
    o.query("save_document", {"path": str(odd)})
    s = Session(out_dir=str(tmp_path))
    r = s.execute("attach_reference", {"name": "ODD", "path": str(odd)})
    assert r["ok"] and any("cannot apply true scale" in w for w in r["warnings"])
    assert s.query("get_entity", {"id": "ODD:LN-001"})["entity"]["end"] == [10, 0]


# --------------------------------------------------------- surfaces


def test_manifest_aliases_and_web_state(tmp_path):
    assert CommandBus.resolve("XCLIP").name == "modify_reference"
    assert CommandBus.resolve("reference clip boundary").name == "modify_reference"
    assert CommandBus.resolve("reference levels").name == "modify_reference"
    schema = CommandBus.resolve("attach_reference").schema["properties"]
    assert {"true_scale", "levels_off", "symbology", "clip", "masks"} <= set(schema)
    s = host_with_survey(tmp_path, levels_off=["V-SURV-TREE"],
                         symbology={"gray": True})
    state = WebApp(s).state()["references"][0]
    assert state["status"] == "loaded" and state["symbology"] == {"gray": True}
    assert {lv["name"]: lv["on"] for lv in state["levels"]} == {
        "0": True, "V-SURV-TOPO": True, "V-SURV-TREE": False}
    assert state["units"]["factor"] == 1.0 and state["resolved_path"].endswith("base.rdoc.json")
