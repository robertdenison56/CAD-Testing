"""WP7 tests: design-model queries and the REPL grammar (spec sections 5, 8.1)."""
from __future__ import annotations

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import DESIGN_DATA_KINDS, Session
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.stations import StationEquation
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document.document import Document

A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]


def design_session(equation=False) -> Session:
    doc = Document.new("queries")
    eqs = [StationEquation(2000.0, 2000.0, 2500.0)] if equation else []
    doc.design.alignments["ALIGN-1"] = Alignment(name="ALIGN-1", elements=compile_pis(A_PIS),
                                                 pis=list(A_PIS), begin_station=1000.0,
                                                 equations=eqs)
    doc.design.profiles["PROF-1"] = Profile(
        name="PROF-1", alignment="ALIGN-1",
        pvis=[PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90)])
    return Session(_document=doc)


def near(p, q, tol=1e-3):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def test_list_alignments_shape():
    s = design_session()
    r = s.query("list_alignments")
    assert r["ok"] and r["count"] == 1
    a = r["alignments"][0]
    assert a["name"] == "ALIGN-1" and a["source"] == "pis" and a["description"] == ""
    assert a["begin_station"] == 1000.0 and a["begin_station_text"] == "10+00.00"
    assert a["end_station"] == pytest.approx(2518.879, abs=1e-3)
    assert a["end_station_text"] == "25+18.88" and a["length"] == pytest.approx(1518.879, abs=1e-3)
    assert a["curves"] == 1 and a["tangents"] == 2 and a["equations"] == 0
    assert a["profiles"] == ["PROF-1"] and a["drawn"] is False
    s.execute("draw_alignment", {"alignment": "ALIGN-1"})
    assert s.query("list_alignments")["alignments"][0]["drawn"] is True
    assert Session().query("list_alignments") == {"ok": True, "name": "list_alignments",
                                                  "count": 0, "alignments": []}


def test_station_to_xy_16_00_string_and_1600_number_agree():
    s = design_session()
    a = s.query("station_to_xy", {"alignment": "ALIGN-1", "station": "16+00"})
    b = s.query("station_to_xy", {"station": 1600})  # default alignment
    assert a["ok"] and b["ok"]
    for key in ("point", "station", "station_text", "element_index", "element_ref"):
        assert a[key] == b[key]
    assert near(a["point"], [1600.0, 1000.0]) and a["station_text"] == "16+00.00"
    assert a["element_kind"] == "curve" and a["element_ref"] == "C-1" and a["element_index"] == 1
    assert a["direction_deg"] == 0.0 and a["azimuth_deg"] == 90.0
    assert a["bearing"] == 'N 90°00\'00" E' and a["region"] == 1
    r = s.query("station_to_xy", {"station": "26+00"})
    assert not r["ok"] and r["error"]["type"] == "query_failed"
    r = s.query("station_to_xy", {"station": "bad"})
    assert not r["ok"] and "cannot parse station" in r["error"]["message"]


def test_station_to_xy_offset12_1600_988():
    s = design_session()
    r = s.query("station_to_xy", {"alignment": "ALIGN-1", "station": "16+00", "offset": 12})
    assert r["ok"] and near(r["point"], [1600.0, 988.0]) and near(r["on_point"], [1600.0, 1000.0])
    assert r["offset"] == 12.0
    eq = design_session(equation=True)
    r = eq.query("station_to_xy", {"station": "28+00"})
    assert r["ok"] and r["station"] == pytest.approx(2300.0) and r["region"] == 2
    r = eq.query("station_to_xy", {"station": "22+00"})
    assert not r["ok"] and "gap" in r["error"]["message"]


def test_xy_to_station_1300_1012_neg12_side_L():
    s = design_session()
    r = s.query("xy_to_station", {"alignment": "ALIGN-1", "point": [1300, 1012]})
    assert r["ok"]
    assert r["station"] == pytest.approx(1300.0) and r["station_text"] == "13+00.00"
    assert r["offset"] == pytest.approx(-12.0) and r["distance"] == pytest.approx(12.0)
    assert r["side"] == "L" and near(r["on_point"], [1300.0, 1000.0])
    assert r["element_index"] == 0 and r["element_kind"] == "tangent" and r["element_ref"] == "T-1"
    assert s.query("xy_to_station", {"point": [1300, 1000]})["side"] == "ON"
    assert s.query("xy_to_station", {"point": [1300, 990]})["side"] == "R"
    r = s.query("xy_to_station", {"point": [900, 1000]})
    assert not r["ok"] and "does not project" in r["error"]["message"]


def test_resolve_anchor_dry_run_equals_place_label():
    s = design_session()
    s.execute("create_sheet", {"name": "C-101"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.7], "width_in": 31,
                                  "height_in": 18.5, "model_center": [1700, 1150],
                                  "feet_per_inch": 50})
    for params in ({"anchor": "PC-1"}, {"anchor": "T-2", "rotation": "perpendicular"},
                   {"anchor": "18+00@25L", "kind": "custom", "side": "right", "content": "X"},
                   {"anchor": "PC-1", "space": "C-101"}):
        dry = s.query("resolve_anchor", {"alignment": "ALIGN-1", **params})
        assert dry["ok"], dry
        cmd = s.execute("place_label", {"space": params.get("space", "model"),
                                        "alignment": "ALIGN-1", **params})
        assert cmd["ok"], cmd
        _, e = s.doc.find_entity(cmd["created"][0])
        assert e.position == pytest.approx(dry["position"], abs=1e-9)
        assert e.rotation_deg == pytest.approx(dry["rotation_deg"])
        assert (e.halign, e.valign, e.height) == (dry["halign"], dry["valign"], dry["height"])
        # the dry run is the same record minus provenance: only the bus stamps that
        assert e.anchor == {**dry["anchor"], "placed_by": "place_label"}
        assert "placed_by" not in dry["anchor"]
        assert dry["kind"] == e.anchor["kind"] and dry["space"] == ("SH-001" if "space" in params
                                                                     else "model")
        if e.anchor["content_auto"]:
            assert e.content == dry["content"] == dry["auto_content"]
    dry = s.query("resolve_anchor", {"anchor": "PC-1", "space": "C-101"})
    assert dry["viewport"] == "VP-001" and dry["anchor"]["label_offset"] == 0.45
    r = s.query("resolve_anchor", {"anchor": "PT-1", "kind": "pc"})
    assert not r["ok"] and "requires a PC-n anchor" in r["error"]["message"]
    r = s.query("resolve_anchor", {"anchor": "PC-1", "space": "mars"})
    assert not r["ok"]


def test_get_design_data_curves_row_numbers():
    s = design_session()
    r = s.query("get_design_data", {"kind": "curves", "alignment": "ALIGN-1"})
    assert r["ok"] and r["total"] == 1 and r["start"] == 0 and r["limit"] == 50
    row = r["rows"][0]
    assert row["ref"] == "C-1" and row["direction"] == "L" and row["radius"] == 800.0
    assert row["tangent"] == pytest.approx(214.359354, abs=1e-5)
    assert row["length"] == pytest.approx(418.87902, abs=1e-5)
    assert row["external"] == pytest.approx(28.220944, abs=1e-5)
    assert row["mid_ordinate"] == pytest.approx(27.259339, abs=1e-5)
    assert row["chord"] == pytest.approx(414.110472, abs=1e-5)
    assert row["degree_of_curve_dms"] == "7°09'43\"" and row["delta_dms"] == "30°00'00\""
    assert row["pc_station_text"] == "16+00.00" and row["pt_station_text"] == "20+18.88"
    assert row["pi_station_text"] == "18+14.36" and row["mc_station_text"] == "18+09.44"
    assert row["chord_bearing"] == 'N 75°00\'00" E'
    tangents = s.query("get_design_data", {"kind": "tangents"})["rows"]
    assert [t["ref"] for t in tangents] == ["T-1", "T-2"]
    assert tangents[1]["bearing"] == 'N 60°00\'00" E' and tangents[0]["mid_station_text"] == "13+00.00"
    aligns = s.query("get_design_data", {"kind": "alignments"})["rows"]
    assert aligns[0]["name"] == "ALIGN-1" and "elements" not in aligns[0]
    assert aligns[0]["curves"] == 1 and aligns[0]["end_station_text"] == "25+18.88"
    anchors = s.query("get_design_data", {"kind": "anchors"})["rows"]
    assert [a["ref"] for a in anchors] == ["BEGIN", "END", "PC-1", "PI-1", "PT-1", "MC-1", "T-1",
                                           "T-2"]
    eq = design_session(equation=True)
    rows = eq.query("get_design_data", {"kind": "equations"})["rows"]
    assert rows == [{"alignment": "ALIGN-1", "index": 1, "ref": "EQ-1", "raw_station": 2000.0,
                     "back": 2000.0, "back_text": "20+00.00", "ahead": 2500.0,
                     "ahead_text": "25+00.00", "label": "STA 20+00.00 BK = STA 25+00.00 AH"}]
    assert list(DESIGN_DATA_KINDS) == ["alignments", "curves", "tangents", "equations",
                                       "anchors", "profiles", "pvis", "vcs"]


def test_get_design_data_pagination_start_1_limit_1_total_3():
    s = design_session()
    r = s.query("get_design_data", {"kind": "pvis", "profile": "PROF-1", "start": 1, "limit": 1})
    assert r["ok"] and r["total"] == 3 and r["start"] == 1 and r["limit"] == 1
    assert len(r["rows"]) == 1 and r["rows"][0]["ref"] == "PVI-2"
    row = r["rows"][0]
    assert row["station_text"] == "20+00.00" and row["length"] == 400.0
    assert row["grade_in_pct"] == pytest.approx(2.0) and row["grade_out_pct"] == pytest.approx(-3.0)
    profiles = s.query("get_design_data", {"kind": "profiles"})["rows"]
    assert profiles[0]["name"] == "PROF-1" and profiles[0]["pvis"] == 3
    assert profiles[0]["curves"] == 1 and profiles[0]["station_range_text"] == "10+00.00 to 30+00.00"
    r = s.query("get_design_data", {"kind": "pvis", "profile": "NOPE"})
    assert not r["ok"] and "no profile named 'NOPE'" in r["error"]["message"]
    r = s.query("get_design_data", {"kind": "bogus"})
    assert not r["ok"] and r["error"]["type"] == "invalid_params"


def test_get_design_data_vcs_A5_K80():
    s = design_session()
    r = s.query("get_design_data", {"kind": "vcs", "alignment": "ALIGN-1"})
    assert r["ok"] and r["total"] == 1
    vc = r["rows"][0]
    assert vc["ref"] == "VC-1" and vc["type"] == "crest" and vc["length"] == 400.0
    assert vc["A_pct"] == pytest.approx(5.0) and vc["K"] == pytest.approx(80.0)
    assert vc["pvc_station"] == 1800.0 and vc["pvc_elevation"] == pytest.approx(116.0)
    assert vc["pvt_station"] == 2200.0 and vc["pvt_elevation"] == pytest.approx(114.0)
    assert vc["high_low"]["station"] == pytest.approx(1960.0)
    assert vc["high_low"]["elevation"] == pytest.approx(117.6)
    assert vc["high_low_station_text"] == "19+60.00" and vc["pvi_station_text"] == "20+00.00"
    eq = design_session(equation=True)
    vc = eq.query("get_design_data", {"kind": "vcs"})["rows"][0]
    assert vc["pvt_station_text"] == "27+00.00"  # raw 2200 through the equation


def test_unknown_alignment_query_failed_hint():
    s = design_session()
    for q, p in (("station_to_xy", {"alignment": "SR-100", "station": 1600}),
                 ("xy_to_station", {"alignment": "SR-100", "point": [0, 0]}),
                 ("resolve_anchor", {"alignment": "SR-100", "anchor": "PC-1"}),
                 ("get_design_data", {"alignment": "SR-100", "kind": "curves"})):
        r = s.query(q, p)
        assert not r["ok"] and r["error"]["type"] == "query_failed", q
        assert r["error"]["message"] == "no alignment named 'SR-100'"
        assert r["error"]["hint"] == "alignments: ['ALIGN-1']"
    empty = Session()
    r = empty.query("station_to_xy", {"station": 1600})
    assert not r["ok"] and "no alignments" in r["error"]["message"]


def test_summary_lists_alignments_profiles():
    s = design_session()
    summary = s.query("get_document_state")["summary"]
    assert summary["alignments"] == ["ALIGN-1"] and summary["profiles"] == ["PROF-1"]
    full = s.query("get_document_state", {"detail": "full"})["document"]
    assert "ALIGN-1" in full["design"]["alignments"]


def test_export_landxml_file_contains_staStart(tmp_path):
    s = design_session(equation=True)
    r = s.query("export_landxml", {"path": str(tmp_path / "out.xml"), "include_xml": True})
    assert r["ok"], r
    text = (tmp_path / "out.xml").read_text()
    assert 'staStart="1000.000000"' in text and text == r["xml"]
    assert '<StaEquation staAhead="2500.000000"' in text and '<ProfAlign name="PROF-1"' in text
    assert r["alignments"] == ["ALIGN-1"] and r["profiles"] == ["PROF-1"]
    assert r["size_bytes"] == len(text.encode("utf-8"))
    r = s.query("export_landxml", {"alignments": ["NOPE"]})
    assert not r["ok"]
    r = Session().query("export_landxml", {})
    assert not r["ok"] and r["error"]["message"] == "no alignments to export"
    s2 = Session(project_name="Round Trip")
    assert s2.execute("import_landxml", {"xml": text})["ok"]
    assert s2.doc.design.alignments["ALIGN-1"].equations[0].ahead == 2500.0


def test_route_line_sta2xy_and_alignments_builtin():
    s = design_session()
    r = route_line(s, "sta2xy 16+00 ALIGN-1")
    assert r["kind"] == "result" and r["result"]["ok"]
    assert near(r["result"]["point"], [1600.0, 1000.0])
    r = route_line(s, "sta2xy 16+00 ALIGN-1 12")
    assert near(r["result"]["point"], [1600.0, 988.0])
    r = route_line(s, "xy2sta 1300,1012 ALIGN-1")
    assert r["result"]["offset"] == pytest.approx(-12.0)
    r = route_line(s, "alignments")
    assert r["result"]["ok"] and r["result"]["count"] == 1
    r = route_line(s, "design curves ALIGN-1")
    assert r["result"]["rows"][0]["ref"] == "C-1"
    r = route_line(s, "anchor PC-1")
    assert r["result"]["ok"] and r["result"]["kind"] == "pc"
    r = route_line(s, "help label")
    assert r["kind"] == "help" and r["item"]["name"] == "place_label"
    r = route_line(s, "landxml")
    assert r["result"]["ok"] and r["result"]["path"].endswith(".xml")


def test_the_end_station_the_engine_prints_is_a_station_it_accepts():
    """Found by a real agent run: SR-100 is 4675.2488 ft long, so its end is
    written '56+75.25' everywhere -- and station_to_xy refused it as off the end."""
    from roaddraft.probes import fixture
    s = Session(project_name="round-trip")
    assert s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                          "pis": fixture.PIS})["ok"]
    row = s.query("list_alignments", {})["alignments"][0]
    assert row["end_station_text"] == "56+75.25" and row["end_station"] < 5675.25
    end = s.query("station_to_xy", {"station": row["end_station_text"]})
    assert end["ok"] and end["station"] == pytest.approx(row["end_station"])
    assert end["point"] == pytest.approx([5600.0, 1500.0])
    begin = s.query("station_to_xy", {"station": "9+99.996"})
    assert begin["ok"] and begin["point"] == pytest.approx([1000.0, 1000.0])
    # a hundredth further is off the end, and still says so
    r = s.query("station_to_xy", {"station": "56+75.26"})
    assert not r["ok"] and "does not exist on this alignment" in r["error"]["message"]


def test_get_design_data_without_a_kind_is_the_overview():
    """The commonest fault across every real agent run was asking for design
    data by alignment alone."""
    s = design_session()
    r = s.query("get_design_data", {"alignment": "ALIGN-1"})
    assert r["ok"] and r["kind"] == "alignments" and r["rows"][0]["name"] == "ALIGN-1"
    assert "curves" in r["other_kinds"] and "tangents" in r["other_kinds"]
    assert "other_kinds" not in s.query("get_design_data", {"kind": "curves"})
