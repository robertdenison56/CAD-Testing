"""WP6 tests: alignment/profile/draw/import commands through the bus (spec section 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.adapters.landxml import write_landxml
from roaddraft.api.session import Session
from roaddraft.commands.bus import ALIASES, REGISTRY
from roaddraft.document.entities import Arc, Line, Text

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
NINE = ["create_alignment", "modify_alignment", "delete_alignment", "create_profile",
        "delete_profile", "draw_alignment", "place_label", "place_curve_table", "import_landxml"]


def session_A(**extra) -> Session:
    s = Session(project_name="cmd-tests")
    r = s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                                       "pis": A_PIS, **extra})
    assert r["ok"], r
    s.execute("create_layer", {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center"})
    return s


def test_create_alignment_diff_and_message_10_00_to_25_18_88():
    s = Session()
    r = s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00", "pis": A_PIS})
    assert r["ok"] and r["created"] == ["alignment:ALIGN-1"]
    assert r["message"] == ("alignment ALIGN-1 created: 3 elements (2 tangents, 1 curve), "
                            "1518.88 ft, 10+00.00 to 25+18.88")
    a = s.doc.design.alignments["ALIGN-1"]
    assert a.begin_station == 1000.0 and a.source == "pis" and len(a.pis) == 3
    assert s.doc.to_dict()["design"]["alignments"]["ALIGN-1"]["elements"][1]["kind"] == "curve"
    # numeric begin station, equations, description
    r = s.execute("create_alignment", {
        "name": "EQ", "begin_station": 1000, "pis": A_PIS, "description": "with equation",
        "equations": [{"back": "20+00", "ahead": "25+00"}]})
    assert r["ok"] and "10+00.00 to 30+18.88" in r["message"]
    assert s.doc.design.alignments["EQ"].equations[0].to_dict() == {
        "raw_station": 2000.0, "back": 2000.0, "ahead": 2500.0}


def test_create_alignment_duplicate_faults():
    s = session_A()
    r = s.execute("create_alignment", {"name": "ALIGN-1", "pis": A_PIS})
    assert not r["ok"] and r["error"]["type"] == "command_failed"
    assert "already exists" in r["error"]["message"]
    assert r["error"]["hint"] == "modify_alignment or delete_alignment"
    r = s.execute("create_alignment", {"name": "B"})
    assert not r["ok"] and "exactly one of pis" in r["error"]["message"]
    r = s.execute("create_alignment", {"name": "B", "pis": A_PIS,
                                       "elements": [{"kind": "tangent", "start": [0, 0],
                                                     "end": [1, 0]}]})
    assert not r["ok"]


def test_create_alignment_overlap_atomic_no_journal_growth():
    s = Session()
    n = len(s.bus.journal)
    # two R=1200 30-degree curves on a 600-ft tangent overlap by 43.08 ft
    r = s.execute("create_alignment", {"name": "BAD", "pis": [
        [0, 0], [1000, 0, 1200], [1000 + 600 * 0.8660254, 300, 1200], [2600, 300]]})
    assert not r["ok"]
    assert "overlap" in r["error"]["message"]
    assert len(s.bus.journal) == n and "BAD" not in s.doc.design.alignments
    r = s.execute("create_alignment", {"name": "BAD", "pis": [[0, 0], [100, 0, 0], [200, 50]]})
    assert not r["ok"] and "angle point" in r["error"]["message"]
    assert r["error"]["hint"] == "pass [x, y, R] for every interior PI"


def test_undo_removes_alignment():
    s = session_A()
    assert "ALIGN-1" in s.doc.design.alignments
    s.execute("undo", {})  # undoes create_layer
    s.execute("undo", {})  # undoes create_alignment
    assert s.doc.design.alignments == {}
    s.execute("redo", {})
    assert "ALIGN-1" in s.doc.design.alignments


def test_create_alignment_from_elements():
    s = Session()
    r = s.execute("create_alignment", {"name": "EL", "begin_station": 1000, "elements": [
        {"kind": "tangent", "start": [1000, 1000], "end": [1600, 1000]},
        {"kind": "curve", "pc": [1600, 1000], "pt": [2000, 1107.179677], "center": [1600, 1800],
         "direction": "L"},
        {"kind": "tangent", "start": [2000, 1107.179677], "end": [2433.012702, 1357.179677]}]})
    assert r["ok"], r
    a = s.doc.design.alignments["EL"]
    assert a.length == pytest.approx(1518.879, abs=1e-3)
    assert a.source == "pis" and len(a.pis) == 3  # PI recovery
    r = s.execute("create_alignment", {"name": "GAP", "elements": [
        {"kind": "tangent", "start": [0, 0], "end": [100, 0]},
        {"kind": "tangent", "start": [100.05, 0], "end": [200, 0]}]})
    assert not r["ok"] and "0.050 ft" in r["error"]["message"]


def test_modify_alignment_rename_rewrites_anchors_and_profiles():
    s = session_A()
    s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                 "pvis": [[1000, 100], [2000, 120, 400], [2500, 90]]})
    r = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    ids = r["created"]
    s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    r = s.execute("modify_alignment", {"name": "ALIGN-1", "changes": {"rename": "SR-100"}})
    assert r["ok"], r
    assert "alignment:SR-100" in r["created"] and "alignment:ALIGN-1" in r["deleted"]
    assert set(ids) <= set(r["modified"]) and "alignment:SR-100" in r["modified"]
    assert list(s.doc.design.alignments) == ["SR-100"]
    assert s.doc.design.profiles["PROF-1"].alignment == "SR-100"
    for e in s.doc.model_entities.values():
        assert e.anchor["alignment"] == "SR-100"
    assert r["warnings"] == []
    # station change warns about anchored entities and is re-validated
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"begin_station": "20+00"}})
    assert r["ok"] and r["warnings"] and "anchored to SR-100" in r["warnings"][0]
    assert s.doc.design.alignments["SR-100"].begin_station == 2000.0
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"bogus": 1}})
    assert not r["ok"] and "pis" in r["error"]["hint"]
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {
        "pis": [[0, 0], [500, 0, 300], [1000, 200]], "description": "moved"}})
    assert r["ok"] and s.doc.design.alignments["SR-100"].description == "moved"
    assert s.doc.design.alignments["SR-100"].length < 1200
    r = s.execute("modify_alignment", {"name": "NOPE", "changes": {"description": "x"}})
    assert not r["ok"] and "no alignment named 'NOPE'" in r["error"]["message"]


def test_delete_alignment_with_profile_faults_then_cascade():
    s = session_A()
    s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                 "pvis": [[1000, 100], [2000, 120, 400], [2500, 90]]})
    s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    r = s.execute("delete_alignment", {"name": "ALIGN-1"})
    assert not r["ok"]
    assert r["error"]["message"] == "ALIGN-1 has 1 profile (PROF-1)"
    assert r["error"]["hint"] == "pass cascade=true or delete_profile first"
    r = s.execute("delete_alignment", {"name": "ALIGN-1", "cascade": True})
    assert r["ok"] and r["deleted"] == ["alignment:ALIGN-1", "profile:PROF-1"]
    assert r["warnings"] == ["3 entities remain anchored to deleted alignment ALIGN-1"]
    assert s.doc.design.alignments == {} and s.doc.design.profiles == {}
    assert all(e.anchor for e in s.doc.model_entities.values())


def test_create_profile_display_stations_and_warning_beyond_end():
    s = session_A()
    r = s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                     "pvis": [[1000, 100], [2000, 120, 400], [3000, 90]]})
    assert r["ok"], r
    assert r["message"] == ("profile PROF-1 created on ALIGN-1: 3 PVIs, 1 vertical curve, "
                            "10+00.00 to 30+00.00")
    assert r["warnings"] == ["PVI-3 (30+00.00) is beyond the end of ALIGN-1 (25+18.88)"]
    assert r["created"] == ["profile:PROF-1"]
    prof = s.doc.design.profiles["PROF-1"]
    assert [q.station for q in prof.pvis] == [1000.0, 2000.0, 3000.0]
    r = s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                     "pvis": [[1000, 1], [2000, 2]]})
    assert not r["ok"] and "already exists" in r["error"]["message"]
    r = s.execute("create_profile", {"name": "BAD", "alignment": "ALIGN-1",
                                     "pvis": [[1000, 100], [1200, 120, 800], [2500, 90]]})
    assert not r["ok"] and "does not fit" in r["error"]["message"]
    r = s.execute("create_profile", {"name": "BAD", "alignment": "NOPE",
                                     "pvis": [[1000, 100], [2000, 90]]})
    assert not r["ok"]
    # display stations go through equations
    s.execute("modify_alignment", {"name": "ALIGN-1", "changes": {
        "equations": [{"back": "20+00", "ahead": "25+00"}]}})
    r = s.execute("create_profile", {"name": "PROF-2", "alignment": "ALIGN-1",
                                     "pvis": [[1000, 100], [2800, 90]]})
    assert r["ok"] and s.doc.design.profiles["PROF-2"].pvis[1].station == pytest.approx(2300.0)
    r = s.execute("delete_profile", {"name": "PROF-2"})
    assert r["ok"] and r["deleted"] == ["profile:PROF-2"]
    assert not s.execute("delete_profile", {"name": "PROF-2"})["ok"]


def test_draw_alignment_LN_AR_LN_arc_270_300_anchors_T1_C1_T2():
    s = session_A()
    r = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    assert r["ok"] and r["created"] == ["LN-001", "AR-001", "LN-002"]
    assert r["message"] == "ALIGN-1 drawn on V-ALIGN-CNTR: 2 lines, 1 arc"
    ln1, ar, ln2 = (s.doc.model_entities[i] for i in r["created"])
    assert isinstance(ln1, Line) and isinstance(ar, Arc) and isinstance(ln2, Line)
    assert ar.center == pytest.approx([1600.0, 1800.0], abs=1e-6) and ar.radius == 800.0
    assert ar.start_angle_deg == pytest.approx(270.0, abs=1e-6)
    assert ar.end_angle_deg == pytest.approx(300.0, abs=1e-6)
    assert ln1.anchor["ref"] == "T-1" and ar.anchor["ref"] == "C-1" and ln2.anchor["ref"] == "T-2"
    assert ar.anchor == {"alignment": "ALIGN-1", "ref": "C-1", "kind": "element",
                         "station": pytest.approx(1600.0, abs=1e-6), "offset": 0.0,
                         "placed_by": "draw_alignment"}
    assert ln1.layer == "V-ALIGN-CNTR"
    # default alignment when only one exists; missing layer faults
    assert s.execute("draw_alignment", {"layer": "NOPE"})["ok"] is False


def test_draw_alignment_mirror_arc_60_90():
    s = Session()
    s.execute("create_alignment", {"name": "MIRROR", "begin_station": 1000, "pis": [
        [1000, 1000], [1814.359354, 1000, 800], [2433.012702, 642.820323]]})
    r = s.execute("draw_alignment", {"alignment": "MIRROR"})
    ar = s.doc.model_entities[r["created"][1]]
    assert ar.center == pytest.approx([1600.0, 200.0], abs=1e-6)
    assert ar.start_angle_deg == pytest.approx(60.0, abs=1e-6)
    assert ar.end_angle_deg == pytest.approx(90.0, abs=1e-6)


def test_draw_alignment_twice_warns_replace_deletes():
    s = session_A()
    r1 = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    r2 = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    assert r2["ok"] and r2["warnings"] == [
        "ALIGN-1 already drawn (LN-001, AR-001, LN-002); pass replace=true to redraw"]
    assert len(s.doc.model_entities) == 6
    r3 = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR",
                                      "replace": True})
    assert r3["ok"] and r3["warnings"] == []
    assert set(r3["deleted"]) == set(r1["created"]) | set(r2["created"])
    assert len(s.doc.model_entities) == 3


def test_import_landxml_inline_xml_replays(tmp_path):
    src = session_A(equations=[{"back": "20+00", "ahead": "25+00"}])
    r = src.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                       "pvis": [[1000, 100], [1900, 120, 200], [2800, 90]]})
    assert r["ok"], r  # 28+00 display = raw 2300 through the equation
    xml = write_landxml([src.doc.design.alignments["ALIGN-1"]],
                        [src.doc.design.profiles["PROF-1"]], "x")
    s = Session()
    r = s.execute("import_landxml", {"xml": xml})
    assert r["ok"], r
    assert r["message"] == ("imported 1 alignment (ALIGN-1) and 1 profile from LandXML 1.2 "
                            "(USSurveyFoot)")
    assert r["created"] == ["alignment:ALIGN-1", "profile:PROF-1"]
    a = s.doc.design.alignments["ALIGN-1"]
    assert a.length == pytest.approx(1518.879, abs=1e-3) and a.equations[0].ahead == 2500.0
    path = tmp_path / "j.jsonl"
    s.query("save_journal", {"path": str(path)})
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()
    # path mode reads the file at execute time
    xml_path = tmp_path / "cl.xml"
    xml_path.write_text(xml)
    s2 = Session()
    r = s2.execute("import_landxml", {"path": str(xml_path), "alignments": ["ALIGN-1"]})
    assert r["ok"]
    r = s2.execute("import_landxml", {"path": str(tmp_path / "missing.xml")})
    assert not r["ok"] and "file not found" in r["error"]["message"]
    r = s2.execute("import_landxml", {"xml": xml, "alignments": ["NOPE"]})
    assert not r["ok"] and "not in the file" in r["error"]["message"]
    r = s2.execute("import_landxml", {"xml": "<LandXML><Alignments></LandXML>"})
    assert not r["ok"] and "parse error" in r["error"]["message"]
    assert not s2.execute("import_landxml", {})["ok"]


def test_import_landxml_conflict_error_replace_rename():
    src = session_A()
    xml = write_landxml([src.doc.design.alignments["ALIGN-1"]], [], "x")
    s = session_A()
    r = s.execute("import_landxml", {"xml": xml})
    assert not r["ok"] and r["error"]["message"] == "alignment ALIGN-1 already exists"
    assert r["error"]["hint"] == "on_conflict=replace|rename"
    r = s.execute("import_landxml", {"xml": xml, "on_conflict": "replace"})
    assert r["ok"] and r["modified"] == ["alignment:ALIGN-1"] and r["created"] == []
    r = s.execute("import_landxml", {"xml": xml, "on_conflict": "rename"})
    assert r["ok"] and r["created"] == ["alignment:ALIGN-1-2"]
    assert set(s.doc.design.alignments) == {"ALIGN-1", "ALIGN-1-2"}


def test_modify_entity_sets_and_clears_anchor_rejects_junk():
    s = session_A()
    r = s.execute("place_text", {"space": "model", "position": [0, 0], "content": "x",
                                 "height": 5})
    tid = r["created"][0]
    r = s.execute("modify_entity", {"id": tid, "changes": {
        "anchor": {"alignment": "ALIGN-1", "ref": "PC-1", "kind": "custom"}}})
    assert r["ok"] and s.doc.model_entities[tid].anchor["ref"] == "PC-1"
    r = s.execute("modify_entity", {"id": tid, "changes": {"anchor": None}})
    assert r["ok"] and s.doc.model_entities[tid].anchor is None
    assert "anchor" not in s.doc.model_entities[tid].to_dict()
    r = s.execute("modify_entity", {"id": tid, "changes": {"anchor": {"bad": 1}}})
    assert not r["ok"] and "anchor:" in r["error"]["message"]
    r = s.execute("modify_entity", {"id": tid, "changes": {"anchor": "PC-1"}})
    assert not r["ok"]


def test_replay_determinism_all_new_commands(tmp_path):
    s = session_A(equations=[{"back": "20+00", "ahead": "25+00"}])
    r = s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                                     "pvis": [[1000, 100], [1900, 120, 200], [2800, 90]]})
    assert r["ok"], r
    s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    s.execute("place_label", {"space": "model", "anchor": "T-1"})
    s.execute("place_label", {"space": "model", "anchor": "MC-1", "kind": "curve_data"})
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.7], "width_in": 31,
                                  "height_in": 18.5, "model_center": [1700, 1150],
                                  "feet_per_inch": 50})
    s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    s.execute("place_curve_table", {"space": "C-101", "position": [24.0, 8.5]})
    s.execute("modify_alignment", {"name": "ALIGN-1", "changes": {"description": "d"}})
    xml = write_landxml([s.doc.design.alignments["ALIGN-1"]], [], "x")
    s.execute("import_landxml", {"xml": xml, "on_conflict": "rename"})
    s.execute("delete_alignment", {"name": "ALIGN-1-2"})
    s.execute("delete_profile", {"name": "PROF-1"})
    assert all(e["name"] != "undo" for e in s.bus.journal)
    path = tmp_path / "all.jsonl"
    s.query("save_journal", {"path": str(path)})
    replayed = Session.replay_journal(path)
    assert replayed.doc.to_dict() == s.doc.to_dict()
    # a saved document round-trips with its design and anchors
    doc_path = tmp_path / "doc.json"
    s.query("save_document", {"path": str(doc_path)})
    assert Session.load(doc_path).doc.to_dict() == s.doc.to_dict()


def test_manifest_lists_nine_commands_with_examples():
    s = Session()
    manifest = s.manifest()
    by_name = {c["name"]: c for c in manifest["commands"]}
    for name in NINE:
        assert name in by_name, name
        assert by_name[name]["example"] and by_name[name]["params_schema"]["type"] == "object"
        assert by_name[name]["aliases"]["c3d"] and by_name[name]["aliases"]["ord"]
    names = [c.name for c in REGISTRY]
    assert names.index("annotate_stationing") < names.index("create_alignment")
    assert names.index("import_landxml") < names.index("attach_reference")
    # every example validates through the bus schema check (no invalid_params)
    for name in NINE:
        r = s.execute(name, by_name[name]["example"])
        assert r["ok"] or r["error"]["type"] == "command_failed", (name, r)


def test_no_alias_collisions_except_LAYER_XREF():
    seen = {}
    dupes = set()
    for spec in REGISTRY:
        for names in spec.aliases.values():
            for alias in names:
                key = alias.lower()
                if key in seen and seen[key] != spec.name:
                    dupes.add(alias)
                seen.setdefault(key, spec.name)
    assert dupes <= {"LAYER", "XREF"}, dupes
    assert ALIASES["createalignmentlayout"] == "create_alignment"
    assert ALIASES["place label"] == "place_label"
    assert ALIASES["landxmlin"] == "import_landxml"
