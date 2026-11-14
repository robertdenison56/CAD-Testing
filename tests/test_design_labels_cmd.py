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
    assert r["message"] == "label TX-001 '16+00.00 BC' (pc @ PC-1 of ALIGN-1) placed in model space"
    e = text_of(s, r)
    assert e.content == "16+00.00 BC" and near(e.position, [1600.0, 1022.5])
    assert e.rotation_deg == 90.0 and e.halign == "left" and e.valign == "middle"
    assert e.height == 8.0 and e.layer == "V-ANNO-TEXT" and e.style == "STANDARD"
    a = e.anchor
    assert a["alignment"] == "ALIGN-1" and a["ref"] == "PC-1" and a["kind"] == "pc"
    assert a["station"] == pytest.approx(1600.0, abs=1e-6) and a["offset"] == 0.0
    assert a["side"] == "left" and a["label_offset"] == 22.5 and a["rotation"] == "perpendicular"
    assert a["viewport"] is None and a["content_auto"] is True
    assert a["placed_by"] == "place_label"
    assert set(a) == {"alignment", "ref", "kind", "station", "offset", "side", "label_offset",
                      "rotation", "viewport", "content_auto", "placed_by"}


def test_place_label_station_13_00_1300_1016():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "13+00"})
    e = text_of(s, r)
    assert e.content == "3" and near(e.position, [1300.0, 994.0])
    assert e.valign == "top" and e.anchor["side"] == "right" and e.anchor["kind"] == "station"
    r = s.execute("place_label", {"space": "model", "anchor": 1300, "side": "right",
                                  "label_offset": 20, "height": 5})
    e = text_of(s, r)
    assert near(e.position, [1300.0, 980.0]) and e.height == 5.0 and e.valign == "top"


def test_place_label_bearing_T2_N60E_rotation_30():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "T-2", "kind": "bearing"})
    e = text_of(s, r)  # bearing and distance, 3 ft above the middle of the tangent
    assert e.content == 'N 60°00\'00" E 500.00\'' and near(e.position, [2215.006, 1234.778])
    assert e.rotation_deg == pytest.approx(30.0, abs=1e-6) and e.anchor["side"] == "left"


def test_place_label_perpendicular_reads_bottom_to_top():
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "18+00", "rotation": "perpendicular"})
    assert text_of(s, r).rotation_deg == pytest.approx(104.324, abs=1e-3)
    r = s.execute("place_label", {"space": "model", "anchor": "18+00", "rotation": "horizontal"})
    assert text_of(s, r).rotation_deg == 0.0 and text_of(s, r).anchor["rotation"] == "horizontal"


def test_perpendicular_label_on_a_twisted_sheet_reads_bottom_to_top():
    # 18+00 runs at 14.324 deg in the model; a -6.457 deg twist shows it at
    # 7.867 deg, so the square label reads up at 97.867, not down at -82.133
    s = sheet_session(rotation=-6.457)
    r = s.execute("place_label", {"space": "C-101", "anchor": "18+00", "rotation": "perpendicular"})
    assert r["ok"], r
    assert text_of(s, r).rotation_deg == pytest.approx(97.867, abs=1e-3)
    r = s.execute("place_label", {"space": "C-101", "anchor": "BC-1"})
    assert r["ok"] and text_of(s, r).content == "16+00.00 BC", r


def test_place_label_infers_kind_from_anchor():
    s = session_A()
    for anchor, kind, content in (("T-1", "bearing", 'N 90°00\'00" E 600.00\''), ("MC-1", "mc", "1"),
                                  ("PT-1", "pt", "20+18.88 EC"), ("PI-1", "pi", "18+14.36 PI"),
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
    assert e.anchor["offset"] == 30.0 and near(e.position, [1600.0, 1000.0 - 30.0 + 6.0])


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
    e = text_of(s, r)  # 0.45 in left of the line, square to it, reading up
    assert near(e.position, [15.0, 9.15], 1e-6) and e.height == 0.10
    assert e.anchor["viewport"] == "VP-001" and e.anchor["label_offset"] == 0.45
    assert e.rotation_deg == 90.0 and e.id in s.doc.sheets["SH-001"].entities
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1", "viewport": "VP-001",
                                  "label_offset": 0.5, "height": 0.15})
    e = text_of(s, r)
    assert near(e.position, [15.0, 9.2], 1e-6) and e.height == 0.15
    assert e.anchor["label_offset"] == 0.5
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1", "viewport": "VP-009"})
    assert not r["ok"] and r["error"]["message"] == "viewport VP-009 is not on C-101"


def test_place_label_sheet_twist20_rotation_20():
    s = sheet_session(rotation=20.0)
    r = s.execute("place_label", {"space": "C-101", "anchor": "PC-1"})
    e = text_of(s, r)  # square to the line as the sheet shows it: 20 + 90
    assert e.rotation_deg == pytest.approx(110.0)
    vp = s.doc.sheets["SH-001"].viewports[0]
    q = vp.transform().to_paper([1600.0, 1000.0])
    expect = [q[0] + 0.45 * math.cos(math.radians(110.0)),
              q[1] + 0.45 * math.sin(math.radians(110.0))]
    assert near(e.position, expect, 1e-6)


def runs_clear(e: Text, paper_direction: float) -> bool:
    """A label square to its line runs away from it (halign left runs along its
    rotation, right against it); one along its line sits clear of it (valign
    bottom puts the lettering on its rotation's +90 side, top on its -90)."""
    side = paper_direction + (90.0 if e.anchor["side"] == "left" else -90.0)
    if e.anchor["rotation"] == "perpendicular":
        body = e.rotation_deg + (0.0 if e.halign == "left" else 180.0)
    else:
        body = e.rotation_deg + (90.0 if e.valign == "bottom" else -90.0)
    return math.cos(math.radians(body - side)) > 0.5


@pytest.mark.parametrize("twist", [-150.0, -95.0, -30.0, 45.0, 120.0, 175.0])
def test_a_label_on_a_twisted_sheet_runs_clear_of_its_line(twist):
    # Training plan decision 13 (found 2026-11-11): the end a label was set from and
    # the edge it sat on came from the model, its rotation from the paper, so through
    # a turned viewport about half of them ran back over the line or sat on it
    from roaddraft.design.anchors import parse_anchor, resolve_anchor
    s = sheet_session(rotation=twist)
    align = s.doc.design.alignments["ALIGN-1"]
    cases = [{"anchor": "PC-1"}, {"anchor": "PT-1", "side": "right"},
             {"anchor": "13+00", "kind": "custom", "content": "MATCH LINE STA 13+00",
              "rotation": "perpendicular", "side": "right"},
             {"anchor": "13+00", "kind": "custom", "content": "FENCE", "side": "left"},
             {"anchor": "T-1", "kind": "bearing"},
             {"anchor": "21+00", "kind": "custom", "content": "R/W", "side": "below"},
             {"anchor": "21+00", "kind": "custom", "content": "R/W", "side": "above"}]
    for case in cases:
        r = s.execute("place_label", {"space": "C-101", **case})
        assert r["ok"], (case, r)
        e = text_of(s, r)
        paper = resolve_anchor(align, parse_anchor(case["anchor"])).direction_deg + twist
        assert runs_clear(e, paper), (case, e.rotation_deg, e.halign, e.valign)
        assert "view_rotation" not in e.anchor  # the viewport it names carries the twist
    # below and above are read on the paper: the two R/W labels are on opposite sides,
    # and the one below sits under the line as the sheet shows it
    below, above = [e for e in s.doc.sheets["SH-001"].entities.values()
                    if isinstance(e, Text) and e.content == "R/W"]
    assert below.anchor["side"] != above.anchor["side"]
    paper = math.radians(resolve_anchor(align, parse_anchor("21+00")).direction_deg + twist)
    flipped = math.cos(paper) < 0.0  # the line runs right to left on the paper
    assert below.anchor["side"] == ("left" if flipped else "right")


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


def test_place_label_custom_at_the_middle_of_a_curve_names_kind_mc():
    # the curve number lettered as plain text at MC-1 draws no bubble and no leader: the
    # result says the plan's callout is kind mc (2026-11-03: every local model and Opus 5.5
    # placed kind custom there, and D1-04 credits only mc)
    s = session_A()
    r = s.execute("place_label", {"space": "model", "anchor": "MC-1", "kind": "custom", "content": "1"})
    assert r["ok"] and len(r["warnings"]) == 1 and "kind mc" in r["warnings"][0]
    assert "omit kind at an MC-n anchor" in r["warnings"][0]
    # custom elsewhere, and mc itself, say nothing
    assert s.execute("place_label", {"space": "model", "anchor": "PC-1", "kind": "custom",
                                     "content": "SEE DETAIL"})["warnings"] == []
    assert s.execute("place_label", {"space": "model", "anchor": "MC-1", "kind": "mc"})["warnings"] == []


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
    assert e.anchor == anchor and near(e.position, [1605.0, 1027.5])


def test_place_curve_table_row_and_anchor():
    s = sheet_session()
    s.execute("create_layer", {"name": "V-ANNO-TABL"})
    r = s.execute("place_curve_table", {"space": "C-101", "alignment": "ALIGN-1",
                                        "position": [24.0, 8.5], "layer": "V-ANNO-TABL"})
    assert r["ok"], r
    assert r["message"] == "curve table TB-001 (1 curve, 5 columns) placed on sheet C-101"
    e = s.doc.sheets["SH-001"].entities[r["created"][0]]
    assert isinstance(e, Table) and e.title == "CURVE DATA" and e.text_height == 0.12
    assert [c["header"] for c in e.columns] == ["No.", "R", "Δ", "T", "L"]
    assert e.rows == [["1", "800.00'", "30°00'00\"", "214.36'", "418.88'"]]
    assert e.anchor == {"alignment": "ALIGN-1", "ref": "CURVES", "kind": "curve_table",
                        "content_auto": True, "placed_by": "place_curve_table"}
    assert e.layer == "V-ANNO-TABL" and e.position == [24.0, 8.5]
    r = s.execute("place_curve_table", {"space": "C-101", "position": [2.0, 20.0],
                                        "columns": ["curve", "radius"], "title": "CURVES",
                                        "text_height": 0.1})
    e = s.doc.sheets["SH-001"].entities[r["created"][0]]
    assert e.rows == [["1", "800.00'"]] and e.title == "CURVES"
    r = s.execute("place_curve_table", {"space": "C-101", "position": [2.0, 20.0],
                                        "columns": ["curve", "bogus"]})
    assert not r["ok"] and "unknown curve table column" in r["error"]["message"]


def test_place_curve_table_in_model_faults():
    s = session_A()
    r = s.execute("place_curve_table", {"space": "model", "position": [0, 0]})
    assert not r["ok"]
    assert r["error"]["message"] == "place_curve_table places tables on sheets"
    assert r["error"]["hint"] == "pass a sheet id/name as space"
