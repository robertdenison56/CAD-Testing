"""Areas: hatching, the area query, the region tracer behind a pick-a-point
hatch (document/regions.py), hatch patterns (document/hatching.py), polylines
with arc segments, entity properties, and the transform behind mirror.
"""
from __future__ import annotations

import math

import ezdxf
import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.document import hatching, paths, regions
from roaddraft.document.clip import clip_primitives
from roaddraft.document.entities import (
    Arc, Hatch, Line, Polyline, Text, entity_distance, entity_from_dict,
)
from roaddraft.document.transform import Similarity, transform_entity

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def ok(s: Session, command: str, **params):
    r = s.execute(command, params)
    assert r["ok"], r
    return r


def fault(s: Session, command: str, **params):
    r = s.execute(command, params)
    assert not r["ok"], r
    return r["error"]


def q(s: Session, name: str, **params):
    r = s.query(name, params)
    assert r["ok"], r
    return r


def entity(s: Session, eid: str):
    return s.doc.find_entity(eid)[1]


# ------------------------------------------------------------- the tracer


def test_the_tracer_walks_round_the_point_dropping_dangles_and_keeping_islands():
    Seg, ArcSeg = paths.Seg, paths.ArcSeg
    pieces = [Seg([-10, 0], [110, 0]), Seg([100, -10], [100, 60]), Seg([110, 50], [-10, 50]),
              Seg([0, 60], [0, -10]),         # four lines that overshoot their corners
              Seg([100, 25], [70, 25]),       # a dangling line poking in
              ArcSeg([30, 25], 10, 0, 360)]   # a circle inside
    owners = ["L1", "L2", "L3", "L4", "L5", "C1"]
    circle = ("C1", {"vertices": [[40, 25], [20, 25]], "bulges": [1.0, 1.0]})
    r = regions.trace_region(pieces, owners, [50, 10], closed_shapes=[circle])
    assert r["ids"] == ["L1", "L2", "L3", "L4", "C1"]
    assert len(r["outer"]["vertices"]) == 4  # the dangle's foot is no corner
    m = regions.region_measure([r["outer"]] + r["islands"])
    assert m["area"] == pytest.approx(5000 - math.pi * 100)
    inside = regions.trace_region(pieces, owners, [30, 25])
    assert inside["ids"] == ["C1"]
    assert regions.loop_signed_area(inside["outer"]) == pytest.approx(math.pi * 100)
    with pytest.raises(regions.RegionError, match="not inside a closed region"):
        regions.trace_region(pieces, owners, [200, 25])


def test_tangent_arcs_and_small_gaps_still_close():
    Seg, ArcSeg = paths.Seg, paths.ArcSeg
    fillet = [Seg([0, 0], [100, 0]), ArcSeg([100, 50], 50, -90, 0), Seg([150, 50], [150, 100]),
              Seg([150, 100], [0, 100]), Seg([0, 100], [0, 0])]
    r = regions.trace_region(fillet, list("abcde"), [50, 50])
    assert regions.loop_signed_area(r["outer"]) == pytest.approx(
        150 * 100 - (50 * 50 - math.pi * 50 * 50 / 4))
    gappy = [Seg([0, 0], [500, 0]), Seg([0, 24], [500, 24]), Seg([100, -0.004], [100, 24.004]),
             Seg([300, 0.003], [300, 24])]
    r = regions.trace_region(gappy, list("abcd"), [200, 12])
    # the 0.003 gap shows as a sliver, not as an open boundary
    assert regions.loop_signed_area(r["outer"]) == pytest.approx(200 * 24, abs=0.5)


def test_a_curb_return_meeting_the_lip_line_tangent_still_closes():
    # the arc arrives along the lip line from the far side: a 180 degree turn
    Seg, ArcSeg = paths.Seg, paths.ArcSeg
    pieces = [Seg([1000, 1012], [1261, 1012]), ArcSeg([1261, 1037], 25, -90, 0),
              Seg([1286, 1037], [1286, 1150]), Seg([1339, 1012], [1600, 1012]),
              ArcSeg([1339, 1037], 25, 270, 180), Seg([1314, 1037], [1314, 1150]),
              Seg([1261, 1012], [1339, 1012]), Seg([1286, 1130], [1314, 1130])]
    r = regions.trace_region(pieces, [str(i) for i in range(len(pieces))], [1300, 1070])
    corners = 2 * (25 * 25 - math.pi * 25 * 25 / 4)
    assert regions.loop_signed_area(r["outer"]) == pytest.approx(28 * 118 + corners)
    assert "0" not in r["ids"] and "3" not in r["ids"]  # the edges beyond stay out


def test_loop_area_centroid_and_reversal_are_exact_for_arcs():
    half_disc = {"vertices": [[10, 0], [-10, 0]], "bulges": [1.0, 0.0]}
    assert regions.loop_signed_area(half_disc) == pytest.approx(math.pi * 50)
    assert regions.loop_centroid(half_disc) == pytest.approx([0.0, 40 / (3 * math.pi)])
    loop = {"vertices": [[0, 0], [10, 0], [10, 10]], "bulges": [0.2, 0.0, -0.3]}
    assert regions.loop_signed_area(regions.reverse_loop(loop)) == pytest.approx(
        -regions.loop_signed_area(loop))
    with pytest.raises(regions.RegionError, match="does not close"):
        regions.chain_loops([Line(id="LN-1", start=[0, 0], end=[10, 0])])


# ------------------------------------------------------------------ hatch


def turn_lane() -> Session:
    s = Session()
    ok(s, "create_alignment", name="SR-100", begin_station="10+00", pis=A_PIS)
    ok(s, "draw_offset", offsets=[12])
    ok(s, "draw_station_offset", points=["14+00@12R", "15+20@24R", "21+00@24R", "21+00@12R"])
    return s


def test_hatch_by_a_point_inside_traces_the_lane_and_reports_its_area():
    s = turn_lane()
    r = ok(s, "hatch", space="model", at=[1700, 988], pattern="ANSI31")
    h = entity(s, r["created"][0])
    assert isinstance(h, Hatch) and h.pattern == "ANSI31" and h.scale == 80.0
    taper = 0.5 * 120 * 12          # the taper triangle, 14+00 to 15+20
    strip = 12 * (80 + (824 + 812) / 2 * math.radians(30) + (2100 - 2018.879021))
    assert "7,793.10 sq ft" in r["message"]
    assert regions.region_measure(h.loops)["area"] == pytest.approx(taper + strip, abs=1e-3)
    area = q(s, "area", at=[1700, 988])
    assert area["area"] == pytest.approx(taper + strip, abs=1e-3)
    assert area["square_yards"] == pytest.approx(area["area"] / 9, abs=1e-5)
    assert q(s, "area", ids=[h.id])["area"] == pytest.approx(area["area"])


def test_hatch_boundaries_nest_into_islands_and_patterns_are_checked():
    s = Session()
    ok(s, "draw_circle", space="model", center=[0, 0], radius=30)
    ok(s, "draw_polyline", space="model", vertices=[[-20, -20], [20, -20], [20, 20], [-20, 20]],
       closed=True)
    r = ok(s, "hatch", space="model", boundary=["CI-001", "PL-001"], pattern="ar-conc", scale=2)
    assert entity(s, r["created"][0]).pattern == "AR-CONC"
    assert "1,227.43 sq ft" in r["message"] and "1 island" in r["message"]
    err = fault(s, "hatch", space="model", points=[[0, 0], [1, 0], [1, 1]], pattern="ANSI99")
    assert "ANSI37" in err["message"]
    err = fault(s, "hatch", space="model", at=[100, 100])
    assert "not inside" in err["message"]
    assert "exactly one" in fault(s, "hatch", space="model")["message"]
    ok(s, "set_annotation_scale", scale=40)
    r = ok(s, "hatch", space="model", points=[[0, 0], [10, 0], [10, 10]], pattern="ANSI31")
    assert entity(s, r["created"][0]).scale == 40.0


def test_a_hatch_renders_exports_as_a_real_dxf_hatch_and_reads_back(tmp_path):
    s = Session(out_dir=tmp_path)
    ok(s, "draw_circle", space="model", center=[0, 0], radius=30)
    ok(s, "draw_polyline", space="model", vertices=[[-20, -20], [20, -20], [20, 20], [-20, 20]],
       closed=True)
    ok(s, "hatch", space="model", boundary=["CI-001", "PL-001"], pattern="ANSI31", scale=10)
    ok(s, "hatch", space="model", points=[[100, 0], [140, 0], [140, 40]], opacity=0.5)
    assert q(s, "render_model")["path"]
    hatches = [e for e in ezdxf.readfile(q(s, "export_dxf")["path"]).modelspace()
               if e.dxftype() == "HATCH"]
    assert sorted(h.dxf.pattern_name for h in hatches) == ["ANSI31", "SOLID"]
    patterned = next(h for h in hatches if h.dxf.pattern_name == "ANSI31")
    assert len(patterned.paths) == 2
    again = entity_from_dict(entity(s, "HT-001").to_dict())
    assert again.loops == entity(s, "HT-001").loops


def test_pattern_lines_stay_inside_and_skip_islands():
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    hole = [[40, 40], [60, 40], [60, 60], [40, 60]]
    segs, dense = hatching.pattern_segments([square, hole], "LINE", 80, 0)
    across = sorted(seg for seg in segs if abs(seg[0][1] - 50.0) < 1e-9)
    assert across == [([0.0, 50.0], [40.0, 50.0]), ([60.0, 50.0], [100.0, 50.0])]
    assert not dense
    assert hatching.spacing("ANSI31", 50) == pytest.approx(6.25, abs=1e-6)


# --------------------------------------------------------- arcs in polylines


def test_a_polyline_with_arc_segments_measures_snaps_offsets_and_exports(tmp_path):
    s = Session(out_dir=tmp_path)
    ok(s, "draw_polyline", space="model", vertices=[[0, 0], [100, 0], [100, 50], [0, 50]],
       closed=True, bulges=[0, 0, 0, 1])
    pl = entity(s, "PL-001")
    assert pl.bbox(s.doc) == pytest.approx((-25.0, 0.0, 100.0, 50.0))
    assert q(s, "measure", entity="PL-001")["length"] == pytest.approx(250 + math.pi * 25)
    snap = q(s, "snap", point=[-24, 26], modes=["midpoint"])
    assert snap["point"] == pytest.approx([-25.0, 25.0])
    assert q(s, "snap", point=[1, 24], modes=["center"])["point"] == pytest.approx([0.0, 25.0])
    assert entity_distance(s.doc, pl, [-30, 25]) == pytest.approx(5.0)
    props = q(s, "get_entity", id="PL-001")["properties"]
    assert props["area"] == pytest.approx(5000 + math.pi * 25 ** 2 / 2, abs=1e-5)
    assert props["segments"][3]["kind"] == "curve" and props["segments"][3]["radius"] == 25.0
    r = ok(s, "offset_entity", ids=["PL-001"], distance=5, side="right")
    copy = entity(s, r["created"][0])
    assert isinstance(copy, Polyline) and copy.closed and copy.has_arcs
    path = s.query("export_dxf", {})["path"]
    lw = [e for e in ezdxf.readfile(path).modelspace() if e.dxftype() == "LWPOLYLINE"]
    assert any(abs(b[0] - 1.0) < 1e-9 for e in lw for b in e.get_points("b"))


def test_a_clip_boundary_cuts_a_polyline_with_arcs_into_its_pieces():
    pl = Polyline(id="PL-1", vertices=[[0, 0], [100, 0], [100, 50]], bulges=[0, 0.5, 0])
    whole = clip_primitives([pl], boundary=[[-10, -10], [200, -10], [200, 200], [-10, 200]])
    assert whole == [pl]
    cut = clip_primitives([pl], boundary=[[-10, -10], [50, -10], [50, 10], [-10, 10]])
    assert len(cut) == 1 and isinstance(cut[0], Line)
    assert cut[0].end == pytest.approx([50.0, 0.0]) and cut[0].id == "PL-1#1"


# ------------------------------------------------------------- properties


def test_get_entity_reads_off_what_list_would():
    s = Session()
    ok(s, "create_alignment", name="SR-100", pis=A_PIS)
    ok(s, "draw_alignment")
    line = q(s, "get_entity", id="LN-001")["properties"]
    assert line["length"] == pytest.approx(600.0) and line["bearing"] == "N 90°00'00\" E"
    arc = q(s, "get_entity", id="AR-001")["properties"]
    assert arc["radius"] == 800.0 and arc["delta"] == "30°00'00\""
    assert arc["tangent"] == pytest.approx(214.359354, abs=1e-6)
    assert arc["chord"] == pytest.approx(414.110472, abs=1e-6)
    ok(s, "draw_circle", space="model", center=[0, 0], radius=10)
    assert q(s, "get_entity", id="CI-001")["properties"]["area"] == pytest.approx(math.pi * 100,
                                                                                abs=1e-5)


# -------------------------------------------------------------- transforms


def test_a_reflection_reverses_arcs_and_keeps_lettering_readable():
    t = Similarity.reflection([0, 0], [0, 1])  # across the y axis
    assert t.apply([3, 4]) == pytest.approx([-3, 4])
    arc = transform_entity(Arc(id="AR-1", center=[10, 0], radius=5, start_angle_deg=0,
                               end_angle_deg=90), t)
    assert arc.center == pytest.approx([-10, 0])
    assert (arc.start_angle_deg % 360, arc.end_angle_deg % 360) == pytest.approx((90, 180))
    text = transform_entity(Text(id="TX-1", position=[5, 0], content="EP", height=1), t)
    assert text.rotation_deg == pytest.approx(0) and text.halign == "right"
    flipped = transform_entity(Text(id="TX-2", position=[0, 5], content="EP", height=1,
                                    valign="bottom"), Similarity.reflection([0, 0], [1, 0]))
    assert flipped.valign == "top" and flipped.rotation_deg == pytest.approx(0)
    twice = t.then(t)
    assert not twice.mirror and twice.apply([3, 4]) == pytest.approx([3, 4])


# ------------------------------------------------------------ command line


def test_the_command_line_hatches_and_measures_areas():
    s = turn_lane()

    def run(line):
        r = route_line(s, line, "model")
        assert r["kind"] == "result" and r["result"]["ok"], r
        return r["result"]

    run("hatch 1700,988 ANSI31 40")
    assert run("area 1700,988")["text"].startswith("7,793.10 sq ft")
    assert run("list LN-001")["properties"]["length"] > 0


def test_a_click_inside_a_hatch_picks_it_but_linework_and_points_win_ties():
    s = Session()
    ok(s, "hatch", space="model", points=[[0, 0], [100, 0], [100, 100], [0, 100]])
    ok(s, "draw_line", space="model", start=[40, 50], end=[60, 50])
    ok(s, "create_points", points=[{"point": [50, 50]}])
    far = q(s, "hit_test", space="model", point=[20, 80], tolerance=5)
    assert far["hits"][0]["id"] == "HT-001"
    tie = q(s, "hit_test", space="model", point=[50, 50], tolerance=5)
    assert [h["id"] for h in tie["hits"][:2]] == ["CP-001", "LN-001"]
