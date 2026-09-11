"""WP6 tests: place_label / place_curve_table through the bus (spec sections 4.7, 4.8)."""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Table, Text

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
TOL = 1e-3


def session_A() -> Session:
    s = Session(project_name="label-tests")
    r = s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00", "pis": A_PIS})
    assert r["ok"], r
    s.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    return s


def sheet_session(rotation=0.0):
    s = session_A()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.7], "width_in": 31,
                                  "height_in": 18.5, "model_center": [1700, 1150],
                                  "feet_per_inch": 50, "rotation_deg": rotation})
    return s


def near(p, q, tol=TOL):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def text_of(s, r) -> Text:
    space, e = s.doc.find_entity(r["created"][0])
    assert isinstance(e, Text)
    return e


def test_place_label_pc1_content_position_1600_984_anchor_record():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "alignment": "ALIGN-1", "anchor": "PC-1",
                                  "layer": "V-ANNO-TEXT"})
    assert r["ok"], r
    assert r["message"] == "label TX-001 'PC 16+00.00' (pc @ PC-1 of ALIGN-1) placed in model space"
    e = text_of(s, r)
    assert e.content == "PC 16+00.00" and near(e.position, [1600.0, 984.0])
    assert e.rotation_deg == 0.0 and e.halign == "center" and e.valign == "top"
    assert e.height == 8.0 and e.layer == "V-ANNO-TEXT" and e.style == "STANDARD"
    a = e.anchor
    assert a["alignment"] == "ALIGN-1" and a["ref"] == "PC-1" and a["kind"] == "pc"
    assert a["station"] == pytest.approx(1600.0, abs=1e-6) and a["offset"] == 0.0
    assert a["side"] == "right" and a["label_offset"] == 16.0 and a["rotation"] == "along"
    assert a["viewport"] is None and a["content_auto"] is True
    assert a["placed_by"] == "place_label"
    assert set(a) == {"alignment", "ref", "kind", "station", "offset", "side", "label_offset",
                      "rotation", "viewport", "content_auto", "placed_by"}


def test_place_label_station_13_00_1300_1016():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "13+00"})
    e = text_of(s, r)
    assert e.content == "13+00.00" and near(e.position, [1300.0, 1016.0])
    assert e.valign == "bottom" and e.anchor["side"] == "left" and e.anchor["kind"] == "station"
    r = s.execute("place_label", {"space": "model", "anchor": 1300, "side": "right",
                                  "label_offset": 20, "height": 5})
    e = text_of(s, r)
    assert near(e.position, [1300.0, 980.0]) and e.height == 5.0 and e.valign == "top"


def test_place_label_bearing_T2_N60E_rotation_30():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "T-2", "kind": "bearing"})
    e = text_of(s, r)
    assert e.content == 'N 60°00\'00" E' and near(e.position, [2208.506, 1246.036])
    assert e.rotation_deg == pytest.approx(30.0, abs=1e-6)


def test_place_label_perpendicular_neg75_676():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "18+00", "rotation": "perpendicular"})
    assert text_of(s, r).rotation_deg == pytest.approx(-75.676, abs=1e-3)
    r = s.execute("place_label", {"space": "model", "anchor": "18+00", "rotation": "horizontal"})
    assert text_of(s, r).rotation_deg == 0.0 and text_of(s, r).anchor["rotation"] == "horizontal"


def test_place_label_infers_kind_from_anchor():
    s = session_A()
    for anchor, kind, content in (("T-1", "bearing", 'N 90°00\'00" E'), ("MC-1", "mc", "C-1"),
                                  ("PT-1", "pt", "PT 20+18.88"), ("PI-1", "pi", "PI 18+14.36"),
                                  ("BEGIN", "begin", "BEGIN STA 10+00.00"),
                                  ("END", "end", "END STA 25+18.88"),
                                  ("12+50", "station", "12+50.00")):
        r = s.execute("place_label", {"space": "model", "anchor": anchor})
        assert r["ok"], r
        e = text_of(s, r)
        assert e.anchor["kind"] == kind and e.content == content, anchor
    r = s.execute("place_label", {"space": "model", "anchor": "MC-1", "kind": "curve_data"})
    assert text_of(s, r).content.startswith("C-1\nΔ = 30°00'00\"\nR = 800.00'")


def test_place_label_kind_mismatch_faults():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "PT-1", "kind": "pc"})
    assert not r["ok"] and r["error"]["type"] == "command_failed"
    assert r["error"]["message"] == "kind pc requires a PC-n anchor, not PT-1"
    r = s.execute("place_label", {"space": "model", "anchor": "MC-1", "kind": "bearing"})
    assert not r["ok"] and "bearing labels go on tangents" in r["error"]["message"]
    r = s.execute("place_label", {"space": "model", "anchor": "PC-3"})
    assert not r["ok"] and "does not exist" in r["error"]["message"]
    assert r["error"]["hint"].startswith("valid: BEGIN, END")
    r = s.execute("place_label", {"space": "model", "anchor": "PC3"})
    assert not r["ok"] and "cannot parse anchor" in r["error"]["message"]
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1", "kind": "nope"})
    assert not r["ok"] and r["error"]["type"] == "invalid_params"
    assert len(s.doc.model_entities) == 0


def test_place_label_custom_without_content_faults():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1", "kind": "custom"})
    assert not r["ok"] and r["error"]["message"] == "kind custom requires content"
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1@30", "kind": "custom",
                                  "content": "BEGIN TAPER"})
    assert r["ok"]
    e = text_of(s, r)
    assert e.content == "BEGIN TAPER" and e.anchor["content_auto"] is False
    assert e.anchor["offset"] == 30.0 and near(e.position, [1600.0, 1000.0 - 30.0 + 16.0])


def test_place_label_explicit_content_verbatim_content_auto_false():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1", "content": "PC 16+00"})
    e = text_of(s, r)
    assert e.content == "PC 16+00" and e.anchor["content_auto"] is False
    assert e.anchor["kind"] == "pc"


def test_place_label_sheet_15_0_8_38_viewport_VP001_height_0_10():
    s = sheet_session()
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    assert r["ok"], r
    assert r["message"].endswith("placed in sheet C-101 via VP-001")
    e = text_of(s, r)
    assert near(e.position, [15.0, 8.38], 1e-6) and e.height == 0.10
    assert e.anchor["viewport"] == "VP-001" and e.anchor["label_offset"] == 0.32
    assert e.rotation_deg == 0.0 and e.id in s.doc.sheets["SH-001"].entities
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1", "viewport": "VP-001",
                                  "label_offset": 0.5, "height": 0.15})
    e = text_of(s, r)
    assert near(e.position, [15.0, 8.2], 1e-6) and e.height == 0.15
    assert e.anchor["label_offset"] == 0.5
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1", "viewport": "VP-009"})
    assert not r["ok"] and r["error"]["message"] == "viewport VP-009 is not on C-101"


def test_place_label_sheet_twist20_rotation_20():
    s = sheet_session(rotation=20.0)
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    e = text_of(s, r)
    assert e.rotation_deg == pytest.approx(20.0)
    vp = s.doc.sheets["SH-001"].viewports[0]
    q = vp.transform().to_paper([1600.0, 1000.0])
    expect = [q[0] + 0.32 * math.cos(math.radians(-70.0)),
              q[1] + 0.32 * math.sin(math.radians(-70.0))]
    assert near(e.position, expect, 1e-6)


def test_place_label_sheet_no_viewport_faults_with_hint():
    s = session_A()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    assert not r["ok"]
    assert r["error"]["message"] == ("anchor PC-1 of ALIGN-1 (1600.00, 1000.00) is not visible "
                                     "in any viewport of C-101")
    assert "create_viewport" in r["error"]["hint"]
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.7], "width_in": 10,
                                  "height_in": 10, "model_center": [5000, 5000],
                                  "feet_per_inch": 50})
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    assert not r["ok"]
    assert r["error"]["hint"].startswith("viewports: VP-001 shows x 4750..5250, y 4750..5250")
    assert "modify_viewport" in r["error"]["hint"]


def test_place_label_duplicate_warning():
    s = session_A()
    r1 = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert r1["warnings"] == []
    r2 = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert r2["ok"] and r2["warnings"] == ["label duplicates TX-001 (same alignment/anchor/kind)"]
    r3 = s.execute("place_label", {"space": "model", "anchor": "PC-1", "kind": "station"})
    assert r3["warnings"] == []


def test_place_label_default_alignment_when_single_else_fault():
    s = session_A()
    assert s.execute("place_label", {"space": "model", "anchor": "PC-1"})["ok"]
    s.execute("create_alignment", {"name": "RAMP-A", "pis": [[0, 0], [500, 0, 300], [1000, 300]]})
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert not r["ok"]
    assert r["error"]["message"] == ("alignment is required: the document has 2 alignments "
                                     "(ALIGN-1, RAMP-A)")
    assert r["error"]["hint"] == "run list_alignments"
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1", "alignment": "SR-100"})
    assert not r["ok"] and r["error"]["message"] == "no alignment named 'SR-100'"
    assert r["error"]["hint"] == "alignments: ['ALIGN-1', 'RAMP-A']"
    assert s.execute("place_label", {"space": "model", "anchor": "PC-1",
                                     "alignment": "RAMP-A"})["ok"]
    s2 = Session()
    r = s2.execute("place_label", {"space": "model", "anchor": "PC-1"})
    assert not r["ok"] and "no alignments" in r["error"]["message"]


def test_move_entities_keeps_anchor():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    tid = r["created"][0]
    anchor = dict(s.doc.model_entities[tid].anchor)
    s.execute("move_entities", {"ids": [tid], "delta": [5, 5]})
    e = s.doc.model_entities[tid]
    assert e.anchor == anchor and near(e.position, [1605.0, 989.0])


def test_place_curve_table_row_and_anchor():
    s = sheet_session()
    s.execute("create_layer", {"name": "V-ANNO-TABL"})
    r = s.execute("place_curve_table", {"space": "C-101", "alignment": "ALIGN-1",
                                        "position": [24.0, 8.5], "layer": "V-ANNO-TABL"})
    assert r["ok"], r
    assert r["message"] == "curve table TB-001 (1 curve, 9 columns) placed on sheet C-101"
    e = s.doc.sheets["SH-001"].entities[r["created"][0]]
    assert isinstance(e, Table) and e.title == "CURVE DATA" and e.text_height == 0.12
    assert [c["header"] for c in e.columns] == ["CURVE", "PI STA", "DELTA", "DIR", "R", "T", "L",
                                                "C", "CH BRG"]
    assert e.rows == [["C-1", "18+14.36", "30°00'00\"", "LT", "800.00'", "214.36'", "418.88'",
                       "414.11'", "N 75°00'00\" E"]]
    assert e.anchor == {"alignment": "ALIGN-1", "ref": "CURVES", "kind": "curve_table",
                        "content_auto": True, "placed_by": "place_curve_table"}
    assert e.layer == "V-ANNO-TABL" and e.position == [24.0, 8.5]
    r = s.execute("place_curve_table", {"space": "C-101", "position": [2.0, 20.0],
                                        "columns": ["curve", "radius"], "title": "CURVES",
                                        "text_height": 0.1})
    e = s.doc.sheets["SH-001"].entities[r["created"][0]]
    assert e.rows == [["C-1", "800.00'"]] and e.title == "CURVES"
    r = s.execute("place_curve_table", {"space": "C-101", "position": [2.0, 20.0],
                                        "columns": ["curve", "bogus"]})
    assert not r["ok"] and "unknown curve table column" in r["error"]["message"]


def test_place_curve_table_in_model_faults():
    s = session_A()
    r = s.execute("place_curve_table", {"space": "model", "position": [0, 0]})
    assert not r["ok"]
    assert r["error"]["message"] == "place_curve_table places tables on sheets"
    assert r["error"]["hint"] == "pass a sheet id/name as space"
