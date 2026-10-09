"""The drafting tools that work from a survey call or from linework already
drawn (commands/edit_handlers.py): draw_traverse, offset_entity, fillet, and
create_alignment from bearings and distances.

The decisive tests are at the end. The drafting-probes were written to find
what an agent could not do through the tool surface, and three of their misses
were missing tools: no bearing and distance input (draft-bearing-distance,
draft-roadway, draft-building) and no fillet (draft-intersection-corner, the
curb return). Each is solved here with the new tools alone -- no trigonometry
in the test -- and scored by the probe's own check.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, Line, Polyline
from roaddraft.probes import fixture, tasks
from roaddraft.probes.drafting import CL, EOP, SHLD

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


def elm_session() -> Session:
    """ELM-AVE's three tangents, by bearing and deflection."""
    s = Session()
    ok(s, "draw_traverse", space="model", start=[1000.0, 3000.0],
       legs=["S 80°00'00\" E 800", "40 L 700", "25 R 600"])
    return s


# ----------------------------------------------------------------- traverse


def test_a_traverse_draws_each_course_where_its_bearing_and_distance_put_it():
    s = elm_session()
    lines = [entity(s, eid) for eid in ("LN-001", "LN-002", "LN-003")]
    assert lines[0].start == [1000.0, 3000.0]
    assert lines[0].end == pytest.approx([1787.846202, 2861.081458], abs=1e-6)
    assert lines[1].end == pytest.approx([2394.063985, 3211.081458], abs=1e-6)
    assert lines[2].end == pytest.approx([2991.780804, 3263.374904], abs=1e-6)
    for a, b in zip(lines, lines[1:]):
        assert a.end == b.start
    r = s.query("measure", {"from": "LN-002", "to": "LN-002", "from_at": "start",
                            "to_at": "end"})
    assert r["bearing"] == "N 60°00'00\" E" and r["distance"] == pytest.approx(700.0)


def test_a_curve_course_draws_an_arc_that_meets_its_neighbours():
    s = Session()
    r = ok(s, "draw_traverse", space="model", start=[0, 0],
           legs=[{"azimuth": 90, "distance": 100},
                 {"radius": 100, "turn": "left", "delta": "90°00'00\""},
                 "N 0 E 50"])
    line, arc, last = (entity(s, eid) for eid in r["created"])
    assert isinstance(arc, Arc) and arc.center == pytest.approx([100.0, 100.0])
    s_ang, e_ang = arc.start_angle_deg, arc.end_angle_deg
    start = [arc.center[0] + 100 * math.cos(math.radians(s_ang)),
             arc.center[1] + 100 * math.sin(math.radians(s_ang))]
    end = [arc.center[0] + 100 * math.cos(math.radians(e_ang)),
           arc.center[1] + 100 * math.sin(math.radians(e_ang))]
    assert start == pytest.approx(line.end, abs=1e-9) and end == pytest.approx(last.start,
                                                                              abs=1e-9)
    assert "curve left R=100.00'" in r["message"]


def test_a_closed_boundary_reports_its_misclosure_and_closes_the_polyline():
    s = Session()
    r = ok(s, "draw_traverse", space="model", start=[0, 0], close=True, polyline=True,
           legs=["N 0 E 100", "90 R 100", "90 R 100.02", "90 R 99.97"])
    pl = entity(s, r["created"][0])
    assert isinstance(pl, Polyline) and pl.closed and len(pl.vertices) == 5
    assert "misses its start by 0.036'" in r["message"] and "1:11,094" in r["message"]
    q = s.query("traverse", {"start": [0, 0], "close": True,
                             "legs": ["N 0 E 100", "90 R 100", "90 R 100.02", "90 R 99.97"]})
    assert q["closure"]["precision"] == pytest.approx(400.01 / 0.036056, rel=1e-3)
    assert q["closing_course"]["distance"] == pytest.approx(0.036056, abs=1e-6)


def test_a_traverse_carries_on_from_the_end_of_an_entity_in_its_direction():
    s = elm_session()
    r = ok(s, "draw_traverse", space="model", start="LN-003", legs=["15 R 200"])
    added = entity(s, r["created"][0])
    assert added.start == entity(s, "LN-003").end
    assert s.query("measure", {"from": added.start, "to": added.end})["bearing"] == \
        "S 80°00'00\" E"
    assert "the end of LN-003" in r["message"]
    # from an entity's start the traverse walks away from it, back past its start
    r = ok(s, "draw_traverse", space="model", start="LN-001", start_at="start",
           legs=["0 R 100"])
    assert s.query("measure", {"from": [1000, 3000], "to": entity(s, r["created"][0]).end}
                   )["bearing"] == "N 80°00'00\" W"


def test_traverse_faults_teach_and_leave_the_drawing_alone():
    s = Session()
    err = fault(s, "draw_traverse", space="model", start=[0, 0], legs=["40 L 100"])
    assert "turned from the previous course" in err["message"] and "bearing" in err["hint"]
    err = fault(s, "draw_traverse", space="model", start=[0, 0], polyline=True,
                legs=["N 0 E 10", {"radius": 5, "turn": "L", "delta": 90}])
    assert "straight courses only" in err["message"]
    err = fault(s, "draw_traverse", space="model", start=[0, 0], legs=["sideways 10"])
    assert "legs[0]" in err["message"]
    assert not s.doc.model_entities


def test_a_traverse_on_a_sheet_is_in_inches_and_says_so():
    s = Session()
    ok(s, "create_sheet", name="C-101")
    r = ok(s, "draw_traverse", space="C-101", start=[2, 2], legs=["N 0 E 1"])
    assert any("paper inches" in w for w in r["warnings"])


# ------------------------------------------------------------------- offset


def test_offset_a_line_left_right_toward_through_and_several_at_once():
    s = Session()
    ok(s, "create_layer", name="V-ROAD-EOP")
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0], layer="V-ROAD-EOP")
    r = ok(s, "offset_entity", ids=["LN-001"], distance=12, side="left")
    left = entity(s, r["created"][0])
    assert (left.start, left.end, left.layer) == ([0.0, 12.0], [100.0, 12.0], "V-ROAD-EOP")
    assert "12.00' left (north side)" in r["message"]
    r = ok(s, "offset_entity", ids=["LN-001"], distance=5, toward=[40, -60])
    assert entity(s, r["created"][0]).start == [0.0, -5.0]
    r = ok(s, "offset_entity", ids=["LN-001"], through=[70, -33.5])
    assert entity(s, r["created"][0]).end == [100.0, -33.5]
    r = ok(s, "offset_entity", ids=["LN-001"], offsets=["8L", 8, -20], layer="0")
    ys = [entity(s, eid).start[1] for eid in r["created"]]
    assert ys == [8.0, -8.0, 20.0] and all(entity(s, e).layer == "0" for e in r["created"])


def test_offset_arcs_circles_and_closed_polylines_say_inside_and_outside():
    s = Session()
    ok(s, "draw_arc", space="model", center=[0, 0], radius=50, start_angle_deg=0,
       end_angle_deg=90)
    r = ok(s, "offset_entity", ids=["AR-001"], distance=10, toward=[0, 0])
    assert entity(s, r["created"][0]).radius == pytest.approx(40.0)
    ok(s, "draw_circle", space="model", center=[500, 500], radius=30)
    r = ok(s, "offset_entity", ids=["CI-001"], distance=5, side="right")
    assert entity(s, r["created"][0]).radius == pytest.approx(35.0) and \
        "outside" in r["message"]
    ok(s, "draw_polyline", space="model", closed=True,
       vertices=[[0, 0], [60, 0], [60, 40], [0, 40]])
    r = ok(s, "offset_entity", ids=["PL-001"], distance=5, toward=[30, 20])
    inner = entity(s, r["created"][0])
    assert inner.closed and sorted(map(tuple, inner.vertices)) == \
        [(5.0, 5.0), (5.0, 35.0), (55.0, 5.0), (55.0, 35.0)]
    assert "5.00' inside" in r["message"]


def test_a_chain_offsets_as_one_path_and_a_drawn_alignment_says_where_the_design_is():
    s = Session()
    ok(s, "create_alignment", name="SR-100", begin_station="10+00", pis=A_PIS)
    drawn = ok(s, "draw_alignment")["created"]
    r = ok(s, "offset_entity", ids=drawn, offsets=[-12, 12])
    assert len(r["created"]) == 6
    radii = sorted(entity(s, eid).radius for eid in r["created"]
                   if isinstance(entity(s, eid), Arc))
    assert radii == pytest.approx([788.0, 812.0])
    assert any("draw_offset" in w for w in r["warnings"])
    for eid in r["created"]:  # plain copies: no design anchor claimed
        assert entity(s, eid).anchor is None


def test_a_reference_element_is_copied_into_this_document(tmp_path):
    s = Session.load(fixture.start_document(tmp_path, "sheets"))
    edge = s.query("find_entities", {"anchor": {"kind": "offset", "offset": 12},
                                     "type": "line", "limit": 1})["entities"][0]["id"]
    assert edge.startswith("DESIGN:")
    r = ok(s, "offset_entity", ids=[edge], distance=6, side="right")
    copy = entity(s, r["created"][0])
    src = s.query("get_entity", {"id": edge})["entity"]
    gap = s.query("measure", {"from": copy.start, "along": edge})["from"]
    assert gap["offset"] == pytest.approx(6.0) and copy.anchor is None
    assert copy.layer == (src["layer"] if src["layer"] in s.doc.layers else "0")


def test_offset_faults_teach():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(s, "place_text", space="model", position=[0, 0], content="X", height=5)
    for params, says in (
            ({"ids": ["TX-001"], "distance": 5, "side": "left"}, "parallel of a line"),
            ({"ids": ["LN-001"], "distance": 5}, "exactly one of side"),
            ({"ids": ["LN-001"], "distance": 5, "offsets": [5]}, "exactly one of distance"),
            ({"ids": ["LN-001"], "offsets": [0]}, "entity itself"),
            ({"ids": ["LN-001"], "through": [50, 0]}, "on the linework"),
            ({"ids": ["LN-404"], "distance": 5, "side": "left"}, "not found")):
        assert says in fault(s, "offset_entity", **params)["message"], params


# ------------------------------------------------------------------- fillet


def test_fillet_rounds_a_corner_and_trims_both_lines_to_it():
    s = elm_session()
    r = ok(s, "fillet", ids=["LN-001", "LN-002"], radius=500)
    arc = entity(s, r["created"][0])
    assert set(r["modified"]) == {"LN-001", "LN-002"}
    assert arc.radius == 500.0 and "Δ=40°00'00\"" in r["message"]
    assert "T=181.99'" in r["message"] and "L=349.07'" in r["message"]
    # the fillet lands where create_alignment puts the same curve
    d = Session()
    ok(d, "create_alignment", name="ELM", start=[1000, 3000],
       legs=["S 80°00'00\" E 800", "40 L 700 R=500", "25 R 600 R=700"])
    curve = d.query("get_design_data", {"kind": "curves"})["rows"][0]
    assert arc.center == pytest.approx(curve["center"], abs=1e-6)
    assert entity(s, "LN-001").end == pytest.approx(curve["pc"], abs=1e-6)
    assert entity(s, "LN-002").start == pytest.approx(curve["pt"], abs=1e-6)
    assert s.execute("undo")["ok"] and entity(s, "LN-001").end == \
        pytest.approx([1787.846202, 2861.081458], abs=1e-6)


def test_fillet_extends_lines_that_stop_short_and_keeps_the_parts_clicked():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[80, 0])      # stops short
    ok(s, "draw_line", space="model", start=[100, 20], end=[100, 200])
    r = ok(s, "fillet", ids=["LN-001", "LN-002"], radius=10)
    arc = entity(s, r["created"][0])
    assert arc.center == pytest.approx([90.0, 10.0])
    assert entity(s, "LN-001").end == pytest.approx([90.0, 0.0])
    assert entity(s, "LN-002").start == pytest.approx([100.0, 10.0])
    # two crossing lines: the clicks say which quadrant gets the curve
    x = Session()
    ok(x, "draw_line", space="model", start=[-100, 0], end=[100, 0])
    ok(x, "draw_line", space="model", start=[0, -100], end=[0, 100])
    r = ok(x, "fillet", ids=["LN-001", "LN-002"], radius=20, keep=[[-50, 0], [0, -50]])
    assert entity(x, r["created"][0]).center == pytest.approx([-20.0, -20.0])
    assert entity(x, "LN-001").end == pytest.approx([-20.0, 0.0])
    assert entity(x, "LN-002").end == pytest.approx([0.0, -20.0])


def test_fillet_radius_zero_meets_at_the_corner_and_trim_false_leaves_the_lines():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[80, 0])
    ok(s, "draw_line", space="model", start=[100, 20], end=[100, 200])
    r = ok(s, "fillet", ids=["LN-001", "LN-002"], radius=0)
    assert not r["created"] and "meet at [100.00, 0.00]" in r["message"]
    assert entity(s, "LN-001").end == [100.0, 0.0]
    assert entity(s, "LN-002").start == [100.0, 0.0]
    t = Session()
    ok(t, "draw_line", space="model", start=[0, 0], end=[100, 0])
    ok(t, "draw_line", space="model", start=[100, 0], end=[100, 100])
    r = ok(t, "fillet", ids=["LN-001", "LN-002"], radius=10, trim=False)
    assert r["modified"] == [] and entity(t, "LN-001").end == [100.0, 0.0]


def test_fillet_faults_say_what_would_fit():
    s = Session()
    ok(s, "draw_line", space="model", start=[0, 0], end=[30, 0])
    ok(s, "draw_line", space="model", start=[30, 0], end=[30, 200])
    ok(s, "draw_line", space="model", start=[0, 10], end=[30, 10])
    ok(s, "draw_arc", space="model", center=[0, 0], radius=5, start_angle_deg=0,
       end_angle_deg=90)
    err = fault(s, "fillet", ids=["LN-001", "LN-002"], radius=100)
    assert "only 30.00'" in err["message"] and "30.00'" in err["hint"]
    assert "parallel" in fault(s, "fillet", ids=["LN-001", "LN-003"], radius=5)["message"]
    assert "two lines" in fault(s, "fillet", ids=["LN-001", "AR-001"], radius=5)["message"]
    assert "two different" in fault(s, "fillet", ids=["LN-001", "LN-001"], radius=5)["message"]


def test_a_referenced_line_is_not_trimmed_but_the_curve_can_be_drawn(tmp_path):
    corner = Session.load(fixture.start_document(tmp_path, "intersection"))
    from roaddraft.probes import tier2
    pieces = tier2._ne_pieces(corner)
    host = Session()
    path = tmp_path / fixture.INTERSECTION_FILE
    ok(host, "attach_reference", name="INT", path=str(path))
    ids = [f"INT:{pieces['main']}", f"INT:{pieces['cross']}"]
    err = fault(host, "fillet", ids=ids, radius=50)
    assert "trim: false" in err["hint"]
    r = ok(host, "fillet", ids=ids, radius=50, trim=False)
    assert entity(host, r["created"][0]).center == pytest.approx([5082.0, 5094.0])


# ------------------------------------------------- create_alignment by legs


def test_create_alignment_from_bearings_reports_the_pis_it_computed():
    s = Session()
    r = ok(s, "create_alignment", name="ELM-AVE", begin_station="10+00", start=[1000, 3000],
           legs=[{"bearing": "S 80°00'00\" E", "distance": 800},
                 {"deflection": "40°00'00\" L", "radius": 500, "distance": 700},
                 "25 R 600 R=700"])
    assert "PI-2 [1787.85, 2861.08] R=500" in r["message"]
    assert "END [2991.78, 3263.37]" in r["message"]
    bearings = [t["bearing"] for t in s.query("get_design_data", {"kind": "tangents"})["rows"]]
    assert bearings == ["S 80°00'00\" E", "N 60°00'00\" E", "N 85°00'00\" E"]


def test_create_alignment_legs_faults_are_phrased_in_legs():
    s = Session()
    err = fault(s, "create_alignment", name="X", start=[0, 0], legs=["N 0 E 100", "90 R 100"])
    assert "legs[1] starts at PI-2" in err["message"] and "angle_points" in err["hint"]
    ok(s, "create_alignment", name="X", start=[0, 0], legs=["N 0 E 100", "90 R 100"],
       angle_points=True)
    assert "go together" in fault(s, "create_alignment", name="Y", legs=["N 0 E 1"])["message"]
    assert "exactly one of pis" in fault(s, "create_alignment", name="Y", start=[0, 0],
                                         legs=["N 0 E 1"], pis=[[0, 0], [1, 1]])["message"]


# ------------------------------------------------- the probes these unblock


def begin(probe_id: str, tmp_path):
    probe = tasks.get(probe_id)
    doc = fixture.start_document(tmp_path, probe.start)
    return probe, Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)


def test_draft_bearing_distance_passes_from_the_words_alone(tmp_path):
    probe, base, s = begin("draft-bearing-distance", tmp_path)
    ok(s, "create_alignment", name="RAMP-B", begin_station="10+00", start=[1000, 1000],
       legs=["N 62°30'00\" E 900", "35°00'00\" R 1100 R=600"])
    ok(s, "draw_alignment", alignment="RAMP-B", layer=CL)
    result = probe.check(base, s)
    assert result.passed, result.detail


def test_draft_roadway_passes_from_the_words_alone(tmp_path):
    probe, base, s = begin("draft-roadway", tmp_path)
    ok(s, "create_alignment", name="ELM-AVE", begin_station="10+00", start=[1000, 3000],
       legs=[{"bearing": "S 80°00'00\" E", "distance": 800},
             {"deflection": "40°00'00\" L", "radius": 500, "distance": 700},
             {"deflection": 25, "turn": "right", "radius": 700, "distance": 600}])
    ok(s, "draw_alignment", alignment="ELM-AVE", layer=CL)
    ok(s, "draw_offset", alignment="ELM-AVE", layer=EOP, offsets=["11L", "11R"])
    ok(s, "draw_offset", alignment="ELM-AVE", layer=SHLD, offsets=["16L", "16R"])
    ok(s, "annotate_stationing", alignment="ELM-AVE", space="model", interval=100)
    result = probe.check(base, s)
    assert result.passed, result.detail


def test_draft_building_passes_as_a_closed_traverse(tmp_path):
    probe, base, s = begin("draft-building", tmp_path)
    ok(s, "create_layer", name="V-BLDG")
    r = ok(s, "draw_traverse", space="model", layer="V-BLDG", start=[1500, 1200],
           polyline=True, close=True,
           legs=["N 30°00'00\" E 60", "S 60°00'00\" E 40", "90 R 60", "90 R 40"])
    assert "closes on its start" in r["message"]
    result = probe.check(base, s)
    assert result.passed, result.detail


def test_draft_intersection_corner_passes_with_one_fillet(tmp_path):
    from roaddraft.probes import tier2
    probe, base, s = begin("draft-intersection-corner", tmp_path)
    pieces = tier2._ne_pieces(s)
    r = ok(s, "fillet", ids=[pieces["main"], pieces["cross"]], radius=50, layer=EOP)
    assert entity(s, r["created"][0]).center == pytest.approx([5082.0, 5094.0])
    result = probe.check(base, s)
    assert result.passed, result.detail


# ----------------------------------------------------------- command line


def test_the_command_line_speaks_bearings_offsets_and_fillets():
    s = Session()

    def run(line):
        r = route_line(s, line, "model")
        assert r["kind"] == "result" and r["result"]["ok"], r
        return r["result"]

    run('bd 1000,3000 "S 80-00-00 E 800" "40L 700" "N 85 E 600"')
    assert len(s.doc.model_entities) == 3
    assert run("fillet LN-001 LN-002 500")["created"] == ["AR-001"]
    r = run("offset LN-003 12 left")
    assert entity(s, r["created"][0]).layer == "0"
    r = run("offset LN-001 AR-001 LN-002 -12 12")
    assert len(r["created"]) == 6
    assert run("dist 1300,2970 1500,2930 along=LN-001")["along_distance"] == \
        pytest.approx(203.907478, abs=1e-6)
    assert run("snap 1608,2893")["kind"] == "endpoint"
    assert run('traverse 0,0 "N45E 100" "90R 100" "90R 100" "90R 100" close=true'
               )["closure"]["text"] == "closes on its start"
    run('alignment ELM start=1000,3000 legs=\'["S80E 800","40L 700 R=500","25R 600 R=700"]\'')
    assert "ELM" in s.doc.design.alignments
    # 'offset' with alignment offsets still draws an alignment's edges
    assert run("offset 12L 12R alignment=ELM")["created"]


# ------------------------------------------------------------------- as MCP


def test_an_agent_sees_the_new_tools_and_is_taught_the_route():
    import json
    from roaddraft.mcp.server import INSTRUCTIONS, RoadDraftMCP

    srv = RoadDraftMCP(Session())
    tools = {t["name"]: t for t in srv.handle({"jsonrpc": "2.0", "id": 1,
                                               "method": "tools/list"})["result"]["tools"]}
    for name in ("draw_traverse", "offset_entity", "fillet", "traverse", "key_points",
                 "snap"):
        assert name in tools and tools[name]["inputSchema"]["type"] == "object"
    assert "legs" in tools["create_alignment"]["inputSchema"]["properties"]
    assert "no trigonometry by hand" in tools["create_alignment"]["description"]
    assert "create_alignment takes start + legs" in INSTRUCTIONS

    def call(tool, **arguments):
        reply = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": tool, "arguments": arguments}})["result"]
        return reply["isError"], json.loads(reply["content"][0]["text"])

    err, out = call("draw_traverse", space="model", start=[0, 0],
                    legs=["N 0 E 100", "90 R 100"])
    assert not err and out["created"] == ["LN-001", "LN-002"]
    err, out = call("fillet", ids=["LN-001", "LN-002"], radius=20)
    assert not err and out["created"] == ["AR-001"]
    err, out = call("snap", point=[1, 79], modes=["endpoint"])
    assert not err and out["point"] == [0.0, 80.0]
    err, out = call("fillet", ids=["LN-001", "LN-002"], radius=500)
    assert err and "largest radius" in out["error"]["hint"]
