"""COGO points and their table, bearing/distance labels and line/curve tables,
linework by station and offset, and marks along a path
(commands/cogo_handlers.py).

Two probes are decisive. draft-turn-lane is station-and-offset drafting: with
draw_station_offset the whole lane is one call naming the stations and
offsets the engineer gave. row-data is a right of way map's tags and tables:
with label_segments it is one call that tags the pieces a sheet shows, in
order along the alignment, with full-geometry line and curve tables.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, BlockRef, Line, Point, Polyline, Table, Text
from roaddraft.probes import fixture, tasks
from roaddraft.probes.drafting import EOP

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def ok(s: Session, command: str, **params):
    r = s.execute(command, params)
    assert r["ok"], r
    return r


def fault(s: Session, command: str, **params):
    r = s.execute(command, params)
    assert not r["ok"], r
    return r["error"]


def entity(s: Session, eid: str):
    return s.doc.find_entity(eid)[1]


def sr100(begin="10+00") -> Session:
    s = Session()
    ok(s, "create_alignment", name="SR-100", begin_station=begin, pis=A_PIS)
    return s


# ------------------------------------------------------------------ points


def test_points_from_a_point_file_a_list_and_the_corners_of_linework():
    s = Session()
    r = ok(s, "create_points", format="PNEZD",
           text="1,2000.00,1500.00,101.25,MON FD\n2 2059.81 1534.40 - IP SET\n# note\n")
    p1, p2 = entity(s, r["created"][0]), entity(s, r["created"][1])
    assert p1.position == [1500.0, 2000.0] and p1.elevation == 101.25
    assert p1.description == "MON FD" and p1.number == 1
    assert p2.elevation is None and p2.description == "IP SET"
    r = ok(s, "create_points", points=[{"northing": 2200, "easting": 1700}, {"point": [5, 5]}],
           description="TBM")
    assert [entity(s, i).number for i in r["created"]] == [3, 4]
    err = fault(s, "create_points", points=[{"point": [0, 0], "number": 2}])
    assert "already exists" in err["message"] and "start_number" in err["hint"]
    ok(s, "draw_traverse", space="model", start=[100, 100], polyline=True, close=True,
       legs=["N 90°00'00\" E 60", "N 00°00'00\" E 40", "N 90°00'00\" W 60"])
    r = ok(s, "create_points", from_entities=["PL-001"], description="BLDG COR",
           start_number=100)
    assert [entity(s, i).number for i in r["created"]] == [100, 101, 102, 103]
    assert entity(s, r["created"][2]).position == pytest.approx([160.0, 140.0])
    assert "100-103" in r["message"]


def test_a_point_draws_its_marker_and_label_and_is_found_and_snapped_as_a_node():
    s = Session()
    ok(s, "create_points", points=[{"point": [10, 20], "elevation": 99.5,
                                    "description": "EP"}], text_height=2.0, size=2.0)
    pt = entity(s, "CP-001")
    texts = [p.content for p in pt.primitives(s.doc) if isinstance(p, Text)]
    assert texts == ["1", "99.50", "EP"]
    found = s.query("find_entities", {"type": "point"})
    assert found["entities"][0]["id"] == "CP-001"
    assert found["entities"][0]["point"] == [10.0, 20.0]
    snap = s.query("snap", {"point": [10.4, 20.3], "modes": ["node"]})
    assert snap["point"] == [10.0, 20.0] and "point 1" in snap["label"]
    props = s.query("get_entity", {"id": "CP-001"})["properties"]
    assert props["northing"] == 20.0 and props["easting"] == 10.0 and props["elevation"] == 99.5


def test_points_are_annotative_and_follow_the_annotation_scale():
    s = Session()
    ok(s, "set_annotation_scale", scale=50)
    ok(s, "create_points", points=[{"point": [0, 0]}])
    assert entity(s, "CP-001").text_height == pytest.approx(4.0)  # 0.08 in x 50
    ok(s, "set_annotation_scale", scale=20)
    pt = entity(s, "CP-001")
    assert pt.text_height == pytest.approx(1.6) and pt.size == pytest.approx(1.6)


def test_the_point_table_lists_the_points_asked_for():
    s = Session()
    ok(s, "create_points", text="1 2000 1500 101.25 MON\n2 2050 1520\n3 2100 1540 99 EP",
       format="PNEZD")
    ok(s, "create_sheet", name="C-101")
    r = ok(s, "place_point_table", space="C-101", position=[26, 20], points="1, 3")
    table = entity(s, r["created"][0])
    assert [c["header"] for c in table.columns] == ["POINT", "NORTHING", "EASTING", "ELEV",
                                                     "DESCRIPTION"]
    assert table.rows == [["1", "2000.00", "1500.00", "101.25", "MON"],
                          ["3", "2100.00", "1540.00", "99.00", "EP"]]
    assert "no point 9" in fault(s, "place_point_table", space="C-101", position=[1, 1],
                                 points=[9])["message"]


# ---------------------------------------------------------- segment labels


def test_values_letter_bearing_over_distance_and_curve_data_over_length():
    s = sr100()
    ok(s, "draw_alignment")
    r = ok(s, "label_segments", ids=["LN-001", "AR-001"], text_height=5)
    texts = [entity(s, i) for i in r["created"]]
    assert [t.content for t in texts] == [
        "N 90°00'00\" E", "600.00'", "R=800.00' Δ=30°00'00\"", "L=418.88'"]
    above, below = texts[0], texts[1]
    assert above.valign == "bottom" and below.valign == "top"
    assert above.position[1] > 1000 > below.position[1]


def test_tags_number_the_pieces_and_tables_give_their_full_geometry():
    s = sr100()
    ok(s, "draw_alignment")
    r = ok(s, "label_segments", ids=["LN-001", "AR-001", "LN-002"], style="tags",
           table={"position": [2500, 1500]}, text_height=5)
    tables = [entity(s, i) for i in r["created"] if s.doc.find_entity(i)[1].TYPE == "table"]
    line_table, curve_table = tables
    assert line_table.title == "LINE TABLE" and curve_table.title == "CURVE TABLE"
    assert line_table.rows[0] == ["L1", "N 90°00'00\" E", "600.00'"]
    assert curve_table.rows[0][:4] == ["C1", "800.00'", "30°00'00\"", "418.88'"]
    assert curve_table.rows[0][4] == "214.36'"  # T = R tan(delta/2)
    assert "tags need a table" in fault(s, "label_segments", ids=["LN-001"],
                                        style="tags")["message"]


def test_draft_row_data_passes_with_one_label_segments_call(tmp_path):
    probe = tasks.get("row-data")
    doc = fixture.start_document(tmp_path, probe.start)
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    shown = s.query("find_entities", {"layer": "rd_RIGHT-OF-WAY", "visible_on": "C-102", "limit": 100})
    right = [row["id"] for row in shown["entities"]
             if s.query("xy_to_station", {"point": row["point"],
                                          "alignment": "DESIGN:SR-100"})["offset"] > 0]
    r = ok(s, "label_segments", ids=right, style="tags", space="C-102",
           order_along="DESIGN:SR-100", table={"position": [24.0, 7.2]})
    assert "(L1, L2, L3, L4, L5, C1, C2)" in r["message"]
    result = probe.check(base, s)
    assert result.passed, result.detail


# ------------------------------------------------------ station and offset


def test_station_offset_follows_the_alignment_where_the_offset_holds():
    s = sr100()
    r = ok(s, "draw_station_offset", points=["15+20@24R", "21+00@24R"], layer="0")
    pieces = [entity(s, i) for i in r["created"]]
    arc = next(e for e in pieces if isinstance(e, Arc))
    assert arc.radius == pytest.approx(824.0)  # 800 + 24 outside the left curve
    assert arc.anchor["kind"] == "offset" and arc.anchor["offset"] == 24.0
    assert arc.anchor["placed_by"] == "draw_station_offset"
    # the same run drawn by draw_offset lands on the same geometry
    want = s.query("station_to_xy", {"alignment": "SR-100", "station": "21+00", "offset": 24})
    assert pieces[-1].end == pytest.approx(want["point"], abs=1e-6)
    r = ok(s, "draw_station_offset", points=["15+20@24R", "21+00@24R"], polyline=True)
    pl = entity(s, r["created"][0])
    assert isinstance(pl, Polyline) and pl.has_arcs
    assert s.query("measure", {"entity": pl.id})["length"] == pytest.approx(
        sum(s.query("measure", {"entity": e.id})["length"] for e in pieces), abs=1e-6)


def test_station_offset_tapers_are_straight_and_faults_teach():
    s = sr100()
    r = ok(s, "draw_station_offset", points=["14+00@12R", "15+20@24R"])
    line = entity(s, r["created"][0])
    assert isinstance(line, Line) and line.anchor is None
    assert line.start == pytest.approx([1400.0, 988.0]) and line.end == pytest.approx(
        [1520.0, 976.0])
    err = fault(s, "draw_station_offset", points=["14+00@12R"])
    assert err["type"] == "invalid_params"
    err = fault(s, "draw_station_offset", points=["40+00@12R", "41+00@12R"])
    assert "40+00" in err["message"]
    err = fault(s, "draw_station_offset", alignment="DESIGN:SR-100",
                points=["14+00", "15+00"])
    assert "reference" in err["message"]


def test_draft_turn_lane_passes_with_one_station_offset_call(tmp_path):
    probe = tasks.get("draft-turn-lane")
    doc = fixture.start_document(tmp_path, probe.start)
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    ok(s, "draw_station_offset", alignment=fixture.ALIGNMENT, layer=EOP,
       points=["30+00@12R", "31+20@24R", "36+00@24R", "36+00@12R"])
    result = probe.check(base, s)
    assert result.passed, result.detail


# ----------------------------------------------------------- along a path


def test_place_along_an_alignment_falls_on_round_stations_offset_and_turned():
    s = sr100(begin="10+37.50")
    ok(s, "define_block", name="DELINEATOR", entities=[
        {"type": "circle", "center": [0, 0], "radius": 0.5}])
    r = ok(s, "place_along", path="SR-100", every=200, offset="14R", block="DELINEATOR")
    first, last = entity(s, r["created"][0]), entity(s, r["created"][-1])
    want = s.query("station_to_xy", {"alignment": "SR-100", "station": "12+00", "offset": 14})
    assert first.position == pytest.approx(want["point"], abs=1e-6)
    assert "first at 12+00.00" in r["message"]
    assert len(r["created"]) == 7  # 12+00 ... 24+00
    on_curve = next(e for e in (entity(s, i) for i in r["created"])
                    if 1600 < e.position[0] < 2000)
    assert 0 < on_curve.rotation_deg < 30  # turned with the curve


def test_divide_a_line_into_points_and_a_chain_every_spacing():
    s = sr100()
    ok(s, "draw_alignment")
    r = ok(s, "place_along", path="LN-001", count=4, description="DIV")
    pts = [entity(s, i) for i in r["created"]]
    assert [p.position[0] for p in pts] == pytest.approx([1000, 1200, 1400, 1600])
    assert [p.number for p in pts] == [1, 2, 3, 4] and pts[0].description == "DIV"
    r = ok(s, "place_along", path=["LN-001", "AR-001", "LN-002"], every=500, offset=-6)
    assert len(r["created"]) == 4
    err = fault(s, "place_along", path="NOPE", every=10)
    assert "neither an entity nor an alignment" in err["message"]
    err = fault(s, "place_along", path="LN-001", every=10, count=2)
    assert "exactly one" in err["message"]


# ------------------------------------------------------------ command line


def test_the_command_line_speaks_points_tables_stations_and_marks():
    s = sr100()
    ok(s, "draw_alignment")

    def run(line, space="model"):
        r = route_line(s, line, space)
        assert r["kind"] == "result", r
        assert r["result"]["ok"], r["result"]
        return r["result"]

    run("point 1500,2000 1534,2059 description=MON")
    assert entity(s, "CP-002").description == "MON"
    run("so 14+00@12R 15+20@24R alignment=SR-100")
    run("along SR-100 every=500 offset=14R")
    run("labelseg LN-001 text_height=5")
    run("pointtable 26,20 points=1-2")
    assert any(isinstance(e, Table) for e in s.doc.model_entities.values())


def test_a_point_number_stays_unique_when_edited():
    s = Session()
    ok(s, "create_points", points=[{"point": [0, 0]}, {"point": [5, 5]}])
    err = fault(s, "modify_entity", id="CP-002", changes={"number": 1})
    assert "already exists" in err["message"]
    ok(s, "modify_entity", id="CP-002", changes={"number": 7, "description": "IP"})
    assert entity(s, "CP-002").number == 7
