"""The modify toolbox (commands/modify_handlers.py): trim, extend, break, join,
explode, chamfer, lengthen, and copy / rotate / mirror / scale / array.

The decisive test is the cul-de-sac probe: its trap is pavement edges drawn
the full length, through the bulb. With trim there is no square root to work
out by hand -- draw the edges through and cut them back to the circle -- and
the probe's own check scores it.
"""
from __future__ import annotations

import math

import ezdxf
import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, BlockRef, Circle, Line, Point, Polyline, Text
from roaddraft.probes import fixture, tasks
from roaddraft.probes.drafting import CL, EOP


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


def cul_de_sac() -> Session:
    """OAK-CT by its words, 14 ft edges drawn the whole way, the 45 ft bulb."""
    s = Session()
    ok(s, "create_alignment", name="OAK-CT", begin_station="10+00", start=[3000.0, 2000.0],
       legs=["N 00°00'00\" E 400"])
    ok(s, "draw_offset", offsets=["14L", "14R"])
    ok(s, "draw_circle", space="model", center=[3000.0, 2400.0], radius=45.0)
    return s


# --------------------------------------------------------------------- trim


def test_trim_cuts_the_edges_back_to_the_bulb_where_they_meet_it():
    s = cul_de_sac()
    r = ok(s, "trim", targets=[{"id": "LN-001", "at": [2986.0, 2399.0]},
                               {"id": "LN-002", "at": [3014.0, 2399.0]}],
           boundaries=["CI-001"])
    throat = 2400.0 - math.sqrt(45.0 ** 2 - 14.0 ** 2)  # 13+57.23
    for eid, x in (("LN-001", 2986.0), ("LN-002", 3014.0)):
        e = entity(s, eid)
        assert e.start == pytest.approx([x, 2000.0]) and e.end == pytest.approx([x, throat])
        assert e.anchor["kind"] == "offset" and e.anchor["station"] == pytest.approx(1000.0)
    assert "42.77' cut away" in r["message"]


def test_trimming_a_circle_twice_leaves_an_arc_and_keep_names_the_part_to_keep():
    s = cul_de_sac()
    ok(s, "trim", targets=[{"id": "LN-001", "at": [2986.0, 2399.0]},
                           {"id": "LN-002", "at": [3014.0, 2399.0]}])
    r = ok(s, "trim", targets=[{"id": "CI-001", "at": [3000.0, 2355.0]}])
    assert r["deleted"] == ["CI-001"] and len(r["created"]) == 1
    arc = entity(s, r["created"][0])
    assert isinstance(arc, Arc) and arc.radius == 45.0
    # the mouth between the edges is gone: the arc spans everything else
    s0, e0 = (arc.start_angle_deg % 360.0, arc.end_angle_deg % 360.0)
    assert (e0 - s0) % 360.0 == pytest.approx(360.0 - 2 * math.degrees(math.asin(14 / 45)))
    s2 = cul_de_sac()
    r = ok(s2, "trim", targets=[{"id": "LN-001", "keep": [2986.0, 2100.0]}])
    assert entity(s2, "LN-001").end[1] == pytest.approx(2400.0 - math.sqrt(45 ** 2 - 14 ** 2))


def test_trim_in_the_middle_splits_and_a_closed_shape_needs_two_cuts():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "draw_line", space="model", start=[30, -10], end=[30, 10])
    ok(s, "draw_line", space="model", start=[60, -10], end=[60, 10])
    r = ok(s, "trim", targets=[{"id": "LN-001", "at": [45, 0]}])
    assert entity(s, "LN-001").end == [30.0, 0.0]
    assert entity(s, r["created"][0]).start == pytest.approx([60.0, 0.0])
    ok(s, "draw_circle", space="model", center=[200, 0], radius=10)
    ok(s, "draw_line", space="model", start=[200, -20], end=[200, 0])
    err = fault(s, "trim", targets=[{"id": "CI-001", "at": [190, 0]}], boundaries=["LN-004"])
    assert "closed" in err["message"] and "two" in err["message"]
    err = fault(s, "trim", targets=[{"id": "LN-004", "at": [200, -15]}], boundaries=["LN-001"])
    assert "crosses none" in err["message"]
    err = fault(s, "trim", targets=[{"id": "LN-004"}])
    assert "at" in err["message"] and "keep" in err["message"]


def test_trim_cuts_to_reference_linework_but_never_trims_it(tmp_path):
    s = Session.load(fixture.start_document(tmp_path, "sheets"))
    edges = s.query("find_entities", {"anchor": {"kind": "offset", "offset": 12}})
    ref_edge = edges["entities"][0]["id"]
    assert ref_edge.startswith("DESIGN:")
    err = fault(s, "trim", targets=[{"id": ref_edge, "at": edges["entities"][0]["point"]}])
    assert "reference" in err["message"] and "copy_entities" in err["hint"]
    # a host line across the referenced edge is cut by it
    q = edges["entities"][0]["point"]
    ok(s, "draw_line", space="model", start=[q[0], q[1] - 30], end=[q[0], q[1] + 30])
    own = [eid for eid, e in s.doc.model_entities.items() if isinstance(e, Line)][-1]
    r = ok(s, "trim", targets=[{"id": own, "at": [q[0], q[1] + 25]}], boundaries=[ref_edge])
    assert ref_edge in r["message"]


# ------------------------------------------------------------------- extend


def test_extend_runs_a_line_to_the_edge_and_an_arc_round_its_circle():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "draw_line", space="model", start=[150, -50], end=[150, 50])
    r = ok(s, "extend", targets=[{"id": "LN-001", "at": [95, 1]}])
    assert entity(s, "LN-001").end == [150.0, 0.0] and "50.00'" in r["message"]
    ok(s, "draw_arc", space="model", center=[0, 50], radius=50, start_angle_deg=270,
       end_angle_deg=300)
    ok(s, "draw_line", space="model", start=[40, 60], end=[40, 140])
    # round its circle the arc first meets the line itself on the far side, at (40, 80)
    ok(s, "extend", targets=[{"id": "AR-001", "end": "end"}], boundaries=["LN-003"])
    arc = entity(s, "AR-001")
    assert geo_point(arc, arc.end_angle_deg) == pytest.approx([40.0, 80.0])
    ok(s, "undo")
    # carried on downward, the line meets it sooner, at (40, 20)
    ok(s, "extend", targets=[{"id": "AR-001", "end": "end"}], boundaries=["LN-003"],
       extend_boundaries=True)
    arc = entity(s, "AR-001")
    assert geo_point(arc, arc.end_angle_deg) == pytest.approx([40.0, 20.0])
    ok(s, "draw_line", space="model", start=[500, 500], end=[600, 500])
    err = fault(s, "extend", targets=[{"id": "LN-004", "end": "end"}], boundaries=["LN-003"])
    assert "extend_boundaries" in err["hint"]


def geo_point(arc, angle):
    a = math.radians(angle)
    return [arc.center[0] + arc.radius * math.cos(a), arc.center[1] + arc.radius * math.sin(a)]


def test_extend_moves_a_polylines_last_vertex_and_refuses_closed_shapes():
    s = Session()
    ok(s, "draw_polyline", space="model", vertices=[[0, 0], [50, 0], [50, 20]])
    ok(s, "draw_line", space="model", start=[0, 60], end=[100, 60])
    ok(s, "extend", targets=[{"id": "PL-001", "end": "end"}])
    assert entity(s, "PL-001").vertices[-1] == pytest.approx([50.0, 60.0])
    ok(s, "draw_circle", space="model", center=[0, 0], radius=5)
    assert "closed" in fault(s, "extend", targets=[{"id": "CI-001", "end": "end"}])["message"]


# ------------------------------------------------------- break, join, explode


def test_break_splits_or_cuts_out_and_a_circle_becomes_an_arc():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    r = ok(s, "break_entity", id="LN-001", at=[40, 3])
    assert entity(s, "LN-001").end == [40.0, 0.0]
    assert entity(s, r["created"][0]).start == [40.0, 0.0]
    ok(s, "break_entity", id="LN-001", at=[10, 0], to=[20, 0])
    assert entity(s, "LN-001").end == [10.0, 0.0]
    ok(s, "draw_circle", space="model", center=[0, 100], radius=10)
    assert "two points" in fault(s, "break_entity", id="CI-001", at=[10, 100])["message"]
    r = ok(s, "break_entity", id="CI-001", at=[10, 100], to=[0, 110])  # a quarter, CCW
    arc = entity(s, r["created"][0])
    assert isinstance(arc, Arc)
    assert (arc.end_angle_deg - arc.start_angle_deg) % 360 == pytest.approx(270.0)
    ok(s, "draw_polyline", space="model", vertices=[[0, 0], [10, 0], [10, 10], [0, 10]],
       closed=True)
    ok(s, "break_entity", id="PL-001", at=[10, 5])
    pl = entity(s, "PL-001")
    assert not pl.closed and pl.vertices[0] == [10.0, 5.0] and pl.vertices[-1] == [10.0, 5.0]


def test_join_makes_one_line_one_arc_or_one_polyline_that_keeps_its_arcs():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[40, 0])
    ok(s, "draw_line", space="model", start=[50, 0], end=[100, 0])
    r = ok(s, "join_entities", ids=["LN-001", "LN-002"])
    assert entity(s, "LN-001").end == [100.0, 0.0] and "gap" in r["message"]
    ok(s, "draw_arc", space="model", center=[0, 0], radius=10, start_angle_deg=0,
       end_angle_deg=180)
    ok(s, "draw_arc", space="model", center=[0, 0], radius=10, start_angle_deg=180,
       end_angle_deg=360)
    r = ok(s, "join_entities", ids=["AR-001", "AR-002"])
    assert isinstance(entity(s, r["created"][0]), Circle)
    a_pis = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
    ok(s, "create_alignment", name="SR-100", pis=a_pis)
    ok(s, "draw_alignment")
    drawn = [eid for eid, e in s.doc.model_entities.items() if e.anchor]
    r = ok(s, "join_entities", ids=[drawn[2], drawn[0], drawn[1]])
    pl = entity(s, r["created"][0])
    assert isinstance(pl, Polyline) and pl.has_arcs and len(pl.vertices) == 4
    assert s.query("measure", {"entity": pl.id})["length"] == pytest.approx(
        s.doc.design.alignments["SR-100"].length, abs=1e-6)
    assert "anchor" in r["warnings"][0]
    a = ok(s, "draw_line", space="model", start=[0, 500], end=[10, 500])["created"][0]
    b = ok(s, "draw_line", space="model", start=[50, 500], end=[60, 510])["created"][0]
    err = fault(s, "join_entities", ids=[a, b])
    assert "end to end" in err["message"]


def test_explode_takes_polylines_blocks_and_hatches_apart():
    s = Session()
    ok(s, "draw_polyline", space="model", vertices=[[0, 0], [100, 0], [100, 50]],
       bulges=[0.0, 0.5, 0.0])
    r = ok(s, "explode_entities", ids=["PL-001"])
    kinds = sorted(entity(s, i).TYPE for i in r["created"])
    assert kinds == ["arc", "line"] and r["deleted"] == ["PL-001"]
    ok(s, "create_layer", name="V-SIGN")
    ok(s, "define_block", name="ARROW", entities=[
        {"type": "polyline", "vertices": [[0, 0], [10, 0], [8, 2]]},
        {"type": "text", "position": [0, 1], "content": "LT", "height": 1}])
    ok(s, "insert_block", space="model", block_name="ARROW", position=[50, 50],
       rotation_deg=90, layer="V-SIGN")
    r = ok(s, "explode_entities", ids=["BR-001"])
    parts = [entity(s, i) for i in r["created"]]
    assert all(p.layer == "V-SIGN" for p in parts)
    pl = next(p for p in parts if isinstance(p, Polyline))
    assert pl.vertices[1] == pytest.approx([50.0, 60.0])
    ok(s, "hatch", space="model", points=[[0, 0], [10, 0], [10, 10]])
    r = ok(s, "explode_entities", ids=["HT-001"])
    assert entity(s, r["created"][0]).closed
    line = ok(s, "draw_line", space="model", start=[0, 0], end=[1, 0])["created"][0]
    assert "simple" in fault(s, "explode_entities", ids=[line])["message"]


# ---------------------------------------------------------- chamfer, lengthen


def test_chamfer_by_two_distances_or_a_distance_and_an_angle():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "draw_line", space="model", start=[100, 0], end=[100, 80])
    r = ok(s, "chamfer", ids=["LN-001", "LN-002"], distance=10, distance2=20)
    cut = entity(s, r["created"][0])
    assert cut.start == pytest.approx([90.0, 0.0]) and cut.end == pytest.approx([100.0, 20.0])
    assert entity(s, "LN-001").end == pytest.approx([90.0, 0.0])
    ok(s, "undo")
    r = ok(s, "chamfer", ids=["LN-001", "LN-002"], distance=10, angle=45)
    assert entity(s, r["created"][0]).end == pytest.approx([100.0, 10.0])
    err = fault(s, "chamfer", ids=["LN-001", "LN-002"], distance=200)
    assert "less than" in err["message"]


def test_lengthen_by_delta_total_percent_and_to_a_point():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "lengthen", id="LN-001", end="end", delta=25)
    assert entity(s, "LN-001").end == pytest.approx([125.0, 0.0])
    ok(s, "lengthen", id="LN-001", end="start", total=100)
    assert entity(s, "LN-001").start == pytest.approx([25.0, 0.0])
    ok(s, "lengthen", id="LN-001", at=[124, 0], percent=50)
    assert entity(s, "LN-001").end == pytest.approx([75.0, 0.0])
    ok(s, "lengthen", id="LN-001", end="end", to=[90, 30])
    assert entity(s, "LN-001").end == pytest.approx([90.0, 0.0])
    assert "cannot be shortened" in fault(s, "lengthen", id="LN-001", end="end",
                                          delta=-500)["message"]
    ok(s, "draw_arc", space="model", center=[0, 0], radius=100, start_angle_deg=0,
       end_angle_deg=90)
    ok(s, "lengthen", id="AR-001", end="end", delta=100 * math.pi / 4)
    assert entity(s, "AR-001").end_angle_deg == pytest.approx(135.0)


# ------------------------------------------------------------- transforms


def test_copy_repeats_drops_anchors_and_brings_reference_elements_in(tmp_path):
    s = Session()
    ok(s, "create_alignment", name="SR-100",
       pis=[[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]])
    ok(s, "draw_alignment")
    r = ok(s, "copy_entities", ids=["LN-001"], delta=[0, 100], count=3)
    assert len(r["created"]) == 3
    assert entity(s, r["created"][2]).start == pytest.approx([1000.0, 1300.0])
    assert all(entity(s, i).anchor is None for i in r["created"])
    ok(s, "create_points", points=[{"point": [0, 0]}])
    r = ok(s, "copy_entities", ids=["CP-001"], **{"from": [0, 0], "to": [5, 5]})
    assert entity(s, r["created"][0]).number == 2
    ref = Session.load(fixture.start_document(tmp_path, "sheets"))
    edge = ref.query("find_entities", {"anchor": {"kind": "offset"}})["entities"][0]["id"]
    r = ok(ref, "copy_entities", ids=[edge], delta=[0, 0])
    assert r["created"][0] in ref.doc.model_entities


def test_rotate_by_angle_or_by_turning_one_direction_onto_another():
    s = Session()
    ok(s, "draw_traverse", space="model", start=[1500.0, 1200.0], polyline=True, close=True,
       legs=["N 90°00'00\" E 60", "N 00°00'00\" E 40", "N 90°00'00\" W 60"])
    corner = [1500.0, 1200.0]
    ok(s, "rotate_entities", ids=["PL-001"], base=corner,
       from_direction=[[1500.0, 1200.0], [1560.0, 1200.0]], to_direction="N 30°00'00\" E")
    pl = entity(s, "PL-001")
    side = s.query("measure", {"from": pl.vertices[0], "to": pl.vertices[1]})
    assert side["bearing"] == "N 30°00'00\" E" and side["distance"] == pytest.approx(60.0)
    r = ok(s, "rotate_entities", ids=["PL-001"], base=corner, angle="90 CW", copy=True)
    assert len(r["created"]) == 1 and "clockwise" in r["message"]


def test_mirror_keeps_text_readable_turns_arcs_and_blocks_over(tmp_path):
    s = Session(out_dir=tmp_path)
    ok(s, "draw_arc", space="model", center=[10, 0], radius=5, start_angle_deg=0,
       end_angle_deg=90)
    ok(s, "place_text", space="model", position=[10, 10], content="EP", height=1)
    ok(s, "draw_polyline", space="model", vertices=[[0, 0], [10, 0]], bulges=[0.5, 0])
    ok(s, "define_block", name="ARROW", entities=[
        {"type": "polyline", "vertices": [[0, 0], [10, 0], [8, 2]]}])
    ok(s, "insert_block", space="model", block_name="ARROW", position=[20, 0])
    r = ok(s, "mirror_entities", ids=["AR-001", "TX-001", "PL-001", "BR-001"],
           line=[[0, -1], [0, 1]])
    arc, text, pl, br = [entity(s, i) for i in r["created"]]
    # the arc covers the mirror image of 0-90 about x = 0: 90-180
    assert arc.center == pytest.approx([-10.0, 0.0])
    assert (arc.start_angle_deg % 360, arc.end_angle_deg % 360) == pytest.approx((90.0, 180.0))
    assert text.rotation_deg == pytest.approx(0.0) and text.halign == "right"
    assert pl.bulges[0] == pytest.approx(-0.5)
    assert br.mirrored and br.position == pytest.approx([-20.0, 0.0])
    tip = [p for p in s.doc.model_entities.values()][-1]
    from roaddraft.document.entities import expand_entities
    prims = expand_entities(s.doc, [tip])
    assert prims[0].vertices[1] == pytest.approx([-30.0, 0.0])
    out = s.query("export_dxf", {})
    blocks = [e for e in ezdxf.readfile(out["path"]).modelspace() if e.dxftype() == "INSERT"]
    assert sorted(b.dxf.xscale for b in blocks) == [-1.0, 1.0]
    assert "reads left to right" in r["message"]


def test_scale_by_factor_or_reference_and_annotative_text_lets_go():
    s = Session()
    ok(s, "set_annotation_scale", scale=50)
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "place_text", space="model", position=[0, 10], content="A", height=5)
    ok(s, "scale_entities", ids=["LN-001"], base=[0, 0], from_length=100, to_length=150)
    assert entity(s, "LN-001").end == pytest.approx([150.0, 0.0])
    r = ok(s, "scale_entities", ids=["TX-001"], base=[0, 0], factor=2)
    assert entity(s, "TX-001").height == 10.0 and entity(s, "TX-001").annotative is None
    assert "annotative" in r["warnings"][0]
    assert fault(s, "scale_entities", ids=["LN-001"], base=[0, 0],
                 factor=-1)["type"] == "invalid_params"


def test_array_in_rows_round_a_center_and_along_an_alignment():
    s = Session()
    ok(s, "create_alignment", name="SR-100", begin_station="10+37.50",
       pis=[[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]])
    ok(s, "define_block", name="POST", entities=[{"type": "circle", "center": [0, 0],
                                                 "radius": 0.5}])
    ok(s, "insert_block", space="model", block_name="POST", position=[0, 0])
    r = ok(s, "array_entities", ids=["BR-001"], kind="rectangular", rows=2, columns=3,
           row_spacing=10, column_spacing=20)
    assert len(r["created"]) == 5
    r = ok(s, "array_entities", ids=["BR-001"], kind="polar", center=[0, 10], count=4)
    assert entity(s, r["created"][0]).position == pytest.approx([10.0, 10.0])
    r = ok(s, "array_entities", ids=["BR-001"], kind="path", path="SR-100", every=500,
           offset="12R")
    first = entity(s, r["created"][0])
    # round stations: 15+00 is the first multiple of 500 past 10+37.50
    want = s.query("station_to_xy", {"alignment": "SR-100", "station": "15+00", "offset": 12})
    assert first.position == pytest.approx(want["point"], abs=1e-6)
    assert fault(s, "array_entities", ids=["BR-001"], kind="hex")["type"] == "invalid_params"


# ------------------------------------------------------ the probe it unblocks


def test_draft_cul_de_sac_passes_by_trimming_the_edges_to_the_bulb(tmp_path):
    probe = tasks.get("draft-cul-de-sac")
    doc = fixture.start_document(tmp_path, probe.start)
    base, s = Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)
    for layer in (CL, EOP):
        if layer not in s.doc.layers:
            ok(s, "create_layer", name=layer)
    ok(s, "create_alignment", name="OAK-CT", begin_station="10+00", start=[3000.0, 2000.0],
       legs=["N 00°00'00\" E 400.00"])
    ok(s, "draw_alignment", alignment="OAK-CT", layer=CL)
    end = s.query("resolve_anchor", {"alignment": "OAK-CT", "anchor": "END"})["anchor_point"]
    bulb = ok(s, "draw_circle", space="model", layer=EOP, center=end, radius=45)["created"][0]
    edges = ok(s, "draw_offset", alignment="OAK-CT", offsets=["14L", "14R"], layer=EOP)
    ok(s, "trim", targets=[{"id": eid, "at": end} for eid in edges["created"]],
       boundaries=[bulb])
    result = probe.check(base, s)
    assert result.passed, result.detail
