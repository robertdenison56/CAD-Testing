"""place_dimension: the measurement is the entity, the linework is derived.

What these tests hold the engine to is the property that makes a dimension
worth having over a line and a piece of text: the number cannot drift from
the geometry. Move a measured point, change the plot scale, show the same
dimension through a viewport at 1"=50' -- the reading still has to be the
distance that is really there.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document import dimgeom
from roaddraft.document.entities import Arc, Circle, Line, Polyline


def session(tmp_path=None) -> Session:
    s = Session(project_name="dimension-tests", out_dir=tmp_path)
    s.execute("create_layer", {"name": "V-ANNO-DIMS", "color": "black"})
    return s


def road(s: Session) -> Session:
    """A 24 ft pavement: LN-001 the right edge, LN-002 the left."""
    s.execute("draw_line", {"space": "model", "start": [0, -12], "end": [400, -12]})
    s.execute("draw_line", {"space": "model", "start": [0, 12], "end": [400, 12]})
    return s


def parts(s: Session, dim_id="DM-001", space="model"):
    _key, container = s.doc.resolve_space(space)
    return {e.id.split(":")[-1]: e for e in container[dim_id].primitives(s.doc)}


def ok(result):
    assert result["ok"], result.get("error")
    return result


# ------------------------------------------------------------------ linear


def test_linear_draws_extension_lines_a_dimension_line_arrows_and_text():
    s = road(session())
    r = ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 2.0, "layer": "V-ANNO-DIMS"}))
    assert r["created"] == ["DM-001"]
    assert r["message"] == ('linear dimension DM-001 ("24.00\'") placed in model '
                            'space, measured vertically')
    p = parts(s)
    assert sorted(p) == ["arrow1", "arrow2", "ext1", "ext2", "line", "text"]
    assert all(e.layer == "V-ANNO-DIMS" for e in p.values())

    # the dimension line runs through line_point, across the measured direction
    assert p["line"].start == pytest.approx([180, -12]) and \
           p["line"].end == pytest.approx([180, 12])
    # extension lines stand off the measured point and run past the dimension line
    assert p["ext1"].start == pytest.approx([100 + 0.6 * 2.0, -12])   # DIMEXO
    assert p["ext1"].end == pytest.approx([180 + 1.0 * 2.0, -12])     # DIMEXE
    # arrowheads sit inside, tips on the dimension line, pointing out
    assert isinstance(p["arrow1"], Polyline) and p["arrow1"].closed
    assert p["arrow1"].vertices[0] == pytest.approx([180, -12])
    assert p["arrow2"].vertices[0] == pytest.approx([180, 12])
    # text sits above the line (to its left when the line is vertical), upright
    assert p["text"].content == "24.00'"
    assert p["text"].height == 2.0 and p["text"].rotation_deg == pytest.approx(90.0)
    assert p["text"].position == pytest.approx([180 - 0.5 * 2.0, 0])
    assert (p["text"].halign, p["text"].valign) == ("center", "bottom")


def test_the_dimension_line_point_says_which_way_to_measure():
    """DIMLINEAR's own rule: drag clear of the points and you measure across."""
    s = session()
    across = ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [0, 0], "p2": [300, 400],
        "line_point": [150, -100], "text_height": 10}))          # dragged below
    beside = ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [0, 0], "p2": [300, 400],
        "line_point": [500, 200], "text_height": 10}))           # dragged to the side
    assert "measured horizontally" in across["message"]
    assert '"300.00\'"' in across["message"]
    assert "measured vertically" in beside["message"]
    assert '"400.00\'"' in beside["message"]


def test_rotation_deg_states_the_measured_direction_outright():
    s = session()
    r = ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [0, 0], "p2": [300, 400],
        "line_point": [150, -100], "rotation_deg": 90, "text_height": 10}))
    assert '"400.00\'"' in r["message"] and "measured" not in r["message"]


def test_aligned_measures_the_true_distance_between_the_points():
    s = session()
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "aligned", "p1": [0, 0], "p2": [300, 400],
        "line_point": [100, 200], "text_height": 10}))
    p = parts(s)
    assert p["text"].content == "500.00'"
    # the dimension line runs parallel to the measured pair
    line = p["line"]
    assert math.degrees(math.atan2(line.end[1] - line.start[1],
                                   line.end[0] - line.start[0])) == \
        pytest.approx(math.degrees(math.atan2(400, 300)))
    assert dimgeom.measure(s.doc.model_entities["DM-001"]) == pytest.approx(500.0)


# ------------------------------------------------------- what to measure


def test_of_entity_dimensions_one_entity_end_to_end():
    s = road(session())
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                     "of_entity": "LN-001", "line_point": [200, -40],
                                     "text_height": 8}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.p1 == pytest.approx([0, -12]) and dim.p2 == pytest.approx([400, -12])
    assert dimgeom.text_of(dim) == "400.00'"


def test_from_entity_and_to_entity_measure_between_points_on_them():
    s = road(session())
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "from_entity": "LN-001",
        "to_entity": "LN-002", "line_point": [200, 0], "text_height": 2}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.p1 == pytest.approx([200, -12])     # the middle of each edge
    assert dim.p2 == pytest.approx([200, 12])
    assert dimgeom.text_of(dim) == "24.00'"


def test_from_at_and_to_at_pick_the_place_on_each_entity():
    s = road(session())
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "from_entity": "LN-001", "from_at": "start",
        "to_entity": "LN-001", "to_at": "end", "line_point": [200, -40],
        "text_height": 8}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.p1 == pytest.approx([0, -12]) and dim.p2 == pytest.approx([400, -12])


def test_a_point_on_a_curve_comes_off_the_curve_not_its_chord():
    """point_at is what makes target selection safe on arcs."""
    s = session()
    s.execute("draw_arc", {"space": "model", "center": [0, 0], "radius": 100.0,
                           "start_angle_deg": 0, "end_angle_deg": 90})
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "from_entity": "AR-001", "from_at": "mid",
        "to_entity": "AR-001", "to_at": "end", "line_point": [150, 150],
        "text_height": 8}))
    dim = s.doc.model_entities["DM-001"]
    assert math.hypot(*dim.p1) == pytest.approx(100.0)   # on the arc, not inside it


# ----------------------------------------------------------------- angular


def test_angular_measures_the_wedge_the_dimension_was_dragged_into():
    s = session()
    common = {"space": "model", "kind": "angular", "center": [0, 0], "p1": [100, 0],
              "p2": [0, 100], "text_height": 6}
    ok(s.execute("place_dimension", {**common, "line_point": [40, 40]}))
    ok(s.execute("place_dimension", {**common, "line_point": [-40, -40]}))
    assert parts(s, "DM-001")["text"].content == "90°00'00\""
    assert parts(s, "DM-002")["text"].content == "270°00'00\""


def test_angular_between_two_lines_finds_the_vertex_and_the_dragged_angle():
    s = session()
    s.execute("draw_line", {"space": "model", "start": [-100, 0], "end": [100, 0]})
    s.execute("draw_line", {"space": "model", "start": [0, -100], "end": [0, 100]})
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "angular", "from_entity": "LN-001",
        "to_entity": "LN-002", "line_point": [30, 30], "text_height": 6}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.center == pytest.approx([0, 0])
    assert dim.p1 == pytest.approx([100, 0]) and dim.p2 == pytest.approx([0, 100])
    assert parts(s, "DM-001")["text"].content == "90°00'00\""
    # the same two lines, dragged into the lower left, call out that corner
    # instead -- from the other end of each line
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "angular", "from_entity": "LN-001",
        "to_entity": "LN-002", "line_point": [-30, -30], "text_height": 6}))
    assert parts(s, "DM-002")["text"].content == "90°00'00\""
    assert s.doc.model_entities["DM-002"].p1 == pytest.approx([-100, 0])


def test_angular_draws_an_arc_with_tangent_arrowheads_and_outside_text():
    s = session()
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "angular", "center": [0, 0], "p1": [100, 0],
        "p2": [0, 100], "line_point": [35.36, 35.36], "text_height": 6}))
    p = parts(s)
    assert isinstance(p["arc"], Arc)
    assert p["arc"].radius == pytest.approx(50.0, abs=0.01)
    assert (p["arc"].start_angle_deg, p["arc"].end_angle_deg) == pytest.approx((0, 90))
    assert p["text"].content == "90°00'00\""
    # the text sits outside the arc, clear of it
    assert math.hypot(*p["text"].position) > p["arc"].radius


def test_angular_decimal_degrees_when_asked():
    s = session()
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "angular", "center": [0, 0], "p1": [100, 0],
        "p2": [0, 100], "line_point": [40, 40], "unit_format": "decimal",
        "precision": 1, "text_height": 6}))
    assert parts(s)["text"].content == "90.0°"


# --------------------------------------------------------- radius/diameter


def test_radius_inside_the_circle_draws_out_from_the_centre():
    s = session()
    s.execute("draw_circle", {"space": "model", "center": [0, 0], "radius": 100.0})
    ok(s.execute("place_dimension", {"space": "model", "kind": "radius",
                                     "of_entity": "CI-001", "line_point": [50, 0],
                                     "text_height": 8}))
    p = parts(s)
    assert p["line"].start == pytest.approx([0, 0])
    assert p["line"].end == pytest.approx([100, 0])          # the arrow is on the circle
    assert p["arrow1"].vertices[0] == pytest.approx([100, 0])
    assert p["text"].content == "R=100.00'"


def test_radius_outside_the_circle_draws_a_leader_with_a_landing():
    s = session()
    s.execute("draw_circle", {"space": "model", "center": [0, 0], "radius": 100.0})
    ok(s.execute("place_dimension", {"space": "model", "kind": "radius",
                                     "of_entity": "CI-001", "line_point": [300, 0],
                                     "text_height": 8}))
    p = parts(s)
    assert p["line"].start == pytest.approx([100, 0])        # from the circle out
    assert p["landing"].end == pytest.approx([300, 0])
    assert p["text"].position == pytest.approx([300, 0])
    assert p["text"].halign == "left" and p["text"].valign == "middle"


def test_radius_of_an_arc_points_at_a_place_the_arc_actually_covers():
    s = session()
    s.execute("draw_arc", {"space": "model", "center": [0, 0], "radius": 100.0,
                           "start_angle_deg": 0, "end_angle_deg": 90})
    ok(s.execute("place_dimension", {"space": "model", "kind": "radius",
                                     "of_entity": "AR-001", "line_point": [-60, -60],
                                     "text_height": 8}))
    tip = s.doc.model_entities["DM-001"].p1     # 225 deg is off the arc: clamped
    angle = math.degrees(math.atan2(tip[1], tip[0])) % 360.0
    assert 0.0 <= angle <= 90.0


def test_diameter_spans_the_circle_with_the_text_at_the_centre():
    s = session()
    s.execute("draw_circle", {"space": "model", "center": [0, 0], "radius": 100.0})
    ok(s.execute("place_dimension", {"space": "model", "kind": "diameter",
                                     "of_entity": "CI-001", "line_point": [0, 0],
                                     "text_height": 8}))
    p = parts(s)
    assert p["line"].start == pytest.approx([-100, 0])
    assert p["line"].end == pytest.approx([100, 0])
    assert p["arrow1"].vertices[0] == pytest.approx([100, 0])
    assert p["arrow2"].vertices[0] == pytest.approx([-100, 0])
    assert p["text"].content == "Ø200.00'"


# --------------------------------------------------------------- arc length


def test_arc_length_measures_along_the_arc_not_across_it():
    s = session()
    s.execute("draw_arc", {"space": "model", "center": [0, 0], "radius": 100.0,
                           "start_angle_deg": 0, "end_angle_deg": 90})
    ok(s.execute("place_dimension", {"space": "model", "kind": "arc_length",
                                     "of_entity": "AR-001", "line_point": [0, 130],
                                     "text_height": 8}))
    p = parts(s)
    assert p["text"].content == f"L={math.pi * 50:.2f}'"     # quarter of 2 pi r
    assert isinstance(p["arc"], Arc) and p["arc"].radius == pytest.approx(130.0)
    # extension lines run radially from the measured arc out to the dimension arc
    assert p["ext1"].start == pytest.approx([100 + 0.6 * 8, 0])


def test_a_circle_has_no_ends_to_measure_an_arc_length_between():
    s = session()
    s.execute("draw_circle", {"space": "model", "center": [0, 0], "radius": 100.0})
    r = s.execute("place_dimension", {"space": "model", "kind": "arc_length",
                                      "of_entity": "CI-001", "line_point": [0, 130]})
    assert not r["ok"]
    assert "two ends of the arc" in r["error"]["message"]
    assert "counter-clockwise from p1" in r["error"]["hint"]


# ------------------------------------------------------------------- text


def test_text_override_replaces_the_number_and_empty_text_hides_it():
    s = road(session())
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text": "24' TYP", "text_height": 2}))
    assert parts(s)["text"].content == "24' TYP"
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [200, -12], "p2": [200, 12],
        "line_point": [260, 0], "text": "", "text_height": 2}))
    assert "text" not in parts(s, "DM-002")


def test_prefix_suffix_and_unit_formats():
    s = session()

    def reading(length=12.5, **extra):
        s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                      "p1": [0, 0], "p2": [length, 0],
                                      "line_point": [6, -20], "text_height": 2,
                                      **extra})
        return parts(s, f"DM-{len(s.doc.model_entities):03d}")["text"].content

    assert reading() == "12.50'"
    assert reading(12.6, precision=0) == "13'"
    assert reading(unit_format="feet_inches") == "12'-6\""
    assert reading(unit_format="decimal", suffix=" M") == "12.50 M"
    assert reading(prefix="W=") == "W=12.50'"


def test_arrow_styles():
    s = session()

    def terminator(arrow):
        s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                      "p1": [0, 0], "p2": [100, 0], "arrow": arrow,
                                      "line_point": [50, -20], "text_height": 4})
        return parts(s, f"DM-{len(s.doc.model_entities):03d}")

    assert isinstance(terminator("arrow")["arrow1"], Polyline)
    assert isinstance(terminator("tick")["arrow1"], Line)
    assert isinstance(terminator("dot")["arrow1"], Circle)
    assert "arrow1" not in terminator("none")


def test_a_dimension_too_short_for_its_text_moves_both_outside_and_says_so():
    s = session()
    r = ok(s.execute("place_dimension", {
        "space": "model", "kind": "aligned", "p1": [0, 0], "p2": [10, 0],
        "line_point": [5, -20], "text_height": 8}))
    assert len(r["warnings"]) == 1
    assert "too short for its text" in r["warnings"][0]
    assert "drawn outside the extension lines" in r["warnings"][0]
    p = parts(s)
    # the arrows now sit beyond the measured points, and the text past the far one
    assert p["arrow1"].vertices[1][0] < 0 and p["arrow2"].vertices[1][0] > 10
    assert p["text"].position[0] > 10
    assert "stub2" in p


# ------------------------------------------- the number follows the geometry


def test_moving_a_measured_point_changes_the_reading():
    s = road(session())
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 2}))
    assert parts(s)["text"].content == "24.00'"
    ok(s.execute("modify_entity", {"id": "DM-001", "changes": {"p2": [100, 20]}}))
    assert parts(s)["text"].content == "32.00'"


def test_moving_the_dimension_moves_the_whole_thing():
    s = session()
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                     "p1": [0, 0], "p2": [100, 0],
                                     "line_point": [50, -20], "text_height": 4}))
    ok(s.execute("move_entities", {"ids": ["DM-001"], "delta": [10, 5]}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.p1 == pytest.approx([10, 5]) and dim.line_point == pytest.approx([60, -15])
    assert dimgeom.text_of(dim) == "100.00'"     # the measurement is unchanged


def test_annotation_scale_resizes_the_annotation_not_the_measurement():
    s = session()
    ok(s.execute("set_annotation_scale", {"scale": "1\"=50'"}))
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                     "p1": [0, 0], "p2": [400, 0],
                                     "line_point": [200, -60]}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.text_height == pytest.approx(5.0)          # 0.10 in x 50
    assert dim.annotative == {"scale": 50.0, "height_in": 0.10}
    assert dimgeom.size(dim, "arrow_size") == pytest.approx(6.0)

    ok(s.execute("set_annotation_scale", {"scale": "1\"=20'"}))
    dim = s.doc.model_entities["DM-001"]
    assert dim.text_height == pytest.approx(2.0)          # 0.10 in x 20
    assert dimgeom.size(dim, "arrow_size") == pytest.approx(2.4)
    assert dim.p2 == pytest.approx([400, 0])              # the survey did not move
    assert dimgeom.text_of(dim) == "400.00'"


def test_explicit_sizes_rescale_with_the_text_height():
    s = session()
    ok(s.execute("set_annotation_scale", {"scale": "1\"=50'"}))
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                     "p1": [0, 0], "p2": [400, 0], "arrow_size": 10.0,
                                     "line_point": [200, -60]}))
    ok(s.execute("set_annotation_scale", {"scale": "1\"=25'"}))
    assert s.doc.model_entities["DM-001"].arrow_size == pytest.approx(5.0)


def test_a_model_dimension_reads_the_same_feet_through_a_sheet_viewport():
    """The drawing shrinks onto paper at 1"=50'; the number must not."""
    s = road(session())
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    ok(s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11],
                                     "width_in": 30, "height_in": 18,
                                     "model_center": [200, 0], "feet_per_inch": 50.0}))
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 5}))
    dim = s.doc.model_entities["DM-001"]
    t = s.doc.sheets["SH-001"].viewports[0].transform()
    on_paper = dim.transformed(t.to_paper, t.rotation_deg, t.scale)
    assert on_paper.measure_scale == pytest.approx(50.0)
    assert on_paper.text_height == pytest.approx(0.10)      # 5 ft at 1"=50'
    assert dimgeom.text_of(on_paper) == "24.00'"
    assert dimgeom.measure(on_paper) == pytest.approx(24.0)


def test_measure_scale_dimensions_model_feet_from_a_sheet():
    s = session()
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    ok(s.execute("place_dimension", {
        "space": "C-101", "kind": "aligned", "p1": [2, 2], "p2": [6, 2],
        "line_point": [4, 1.5]}))
    assert parts(s, "DM-001", "SH-001")["text"].content == "4.00"     # paper inches
    ok(s.execute("place_dimension", {
        "space": "C-101", "kind": "aligned", "p1": [2, 4], "p2": [6, 4],
        "line_point": [4, 3.5], "measure_scale": 50}))
    assert parts(s, "DM-002", "SH-001")["text"].content == "200.00'"  # 4 in at 1"=50'


# ------------------------------------------------------------ teaching errors


def test_a_linear_dimension_needs_two_points():
    s = session()
    r = s.execute("place_dimension", {"space": "model", "kind": "linear",
                                      "p1": [0, 0], "line_point": [50, -20]})
    assert not r["ok"] and r["error"]["type"] == "command_failed"
    assert "measures between two points" in r["error"]["message"]
    assert "of_entity" in r["error"]["hint"]


def test_points_separated_one_way_only_are_measured_that_way():
    """The drag cannot ask for the dimension that measures nothing."""
    s = session()
    for line_point in ([50, -200], [0, 50], [10, 50]):
        r = ok(s.execute("place_dimension", {"space": "model", "kind": "linear",
                                             "p1": [0, 0], "p2": [0, 100],
                                             "line_point": line_point,
                                             "text_height": 4}))
        assert '"100.00\'"' in r["message"]


def test_a_dimension_that_measures_nothing_is_refused_with_the_way_out():
    s = session()
    r = s.execute("place_dimension", {"space": "model", "kind": "linear",
                                      "p1": [0, 0], "p2": [0, 100], "rotation_deg": 0,
                                      "line_point": [50, -200]})
    assert not r["ok"]
    assert "measures at 0°" in r["error"]["message"]
    assert "drop rotation_deg" in r["error"]["hint"] and "aligned" in r["error"]["hint"]


def test_two_identical_points_measure_nothing_at_all():
    s = session()
    r = s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                      "p1": [10, 10], "p2": [10, 10],
                                      "line_point": [10, -20]})
    assert not r["ok"] and "the same point" in r["error"]["message"]


def test_measuring_something_in_another_space_is_refused():
    s = road(session())
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    r = s.execute("place_dimension", {"space": "C-101", "kind": "aligned",
                                      "of_entity": "LN-001", "line_point": [4, 4]})
    assert not r["ok"]
    assert "LN-001 is in model, but the dimension goes in SH-001" in r["error"]["message"]


def test_an_unknown_entity_points_at_how_to_find_one():
    s = session()
    r = s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                      "of_entity": "LN-404", "line_point": [0, 0]})
    assert not r["ok"] and "no entity 'LN-404'" in r["error"]["message"]
    assert "find_entities" in r["error"]["hint"]


def test_a_radius_dimension_of_a_line_says_what_it_measures():
    s = road(session())
    r = s.execute("place_dimension", {"space": "model", "kind": "radius",
                                      "of_entity": "LN-001", "line_point": [50, 50]})
    assert not r["ok"]
    assert "measures an arc or a circle" in r["error"]["message"]


def test_parallel_lines_have_no_angle_between_them():
    s = road(session())
    r = s.execute("place_dimension", {"space": "model", "kind": "angular",
                                      "from_entity": "LN-001", "to_entity": "LN-002",
                                      "line_point": [200, 0]})
    assert not r["ok"] and "parallel" in r["error"]["message"]


def test_an_invalid_kind_gets_the_schema_and_a_working_example():
    s = session()
    r = s.execute("place_dimension", {"space": "model", "kind": "curvature",
                                      "line_point": [0, 0]})
    assert not r["ok"] and r["error"]["type"] == "invalid_params"
    assert "valid_params_schema" in r["error"] and "example" in r["error"]


def test_a_failed_dimension_leaves_nothing_behind():
    s = session()
    before = s.doc.to_dict()
    s.execute("place_dimension", {"space": "model", "kind": "linear", "p1": [0, 0],
                                  "p2": [0, 100], "rotation_deg": 0,
                                  "line_point": [50, -200]})
    assert s.doc.to_dict() == before


# ------------------------------------------------- the rest of the surface


def test_a_dimension_survives_a_round_trip_and_a_journal_replay(tmp_path):
    s = road(session(tmp_path))
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "from_entity": "LN-001",
        "to_entity": "LN-002", "line_point": [200, 0], "text_height": 2,
        "arrow": "tick", "unit_format": "feet_inches", "suffix": " EP-EP"}))
    state = s.doc.to_dict()
    from roaddraft.document.document import Document
    assert Document.from_dict(state).to_dict() == state

    path = s.query("save_journal", {"path": str(tmp_path / "dim.journal.json")})["path"]
    replayed = Session.replay_journal(path, out_dir=tmp_path)
    assert replayed.doc.to_dict() == state
    assert parts(replayed)["text"].content == "24'-0\" EP-EP"


def test_undo_takes_the_dimension_back_out():
    s = road(session())
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                     "of_entity": "LN-001", "line_point": [200, -40]}))
    assert "DM-001" in s.doc.model_entities
    ok(s.execute("undo"))
    assert "DM-001" not in s.doc.model_entities


def test_find_entities_hit_test_and_get_entity_see_dimensions():
    s = road(session())
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 2, "layer": "V-ANNO-DIMS"}))
    found = s.query("find_entities", {"type": "dimension"})
    assert [row["id"] for row in found["entities"]] == ["DM-001"]
    hits = s.query("hit_test", {"space": "model", "point": [180, 0], "tolerance": 1.0})
    assert "DM-001" in [h["id"] for h in hits["hits"]]
    assert s.query("get_entity", {"id": "DM-001"})["entity"]["kind"] == "linear"


def test_the_measure_query_reads_the_same_number_a_dimension_would():
    s = road(session())
    m = s.query("measure", {"from": "LN-001", "to": "LN-002"})
    assert m["distance"] == pytest.approx(24.0) and m["text"] == "24.00'"
    assert m["dx"] == 0.0 and m["dy"] == pytest.approx(24.0)
    assert m["bearing"] == 'N 00°00\'00" E'
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "from_entity": "LN-001",
        "to_entity": "LN-002", "line_point": [200, 0], "text_height": 2}))
    assert parts(s)["text"].content == m["text"]


def test_the_measure_query_reads_an_arc_off_its_own_geometry():
    s = session()
    s.execute("draw_arc", {"space": "model", "center": [0, 0], "radius": 100.0,
                           "start_angle_deg": 0, "end_angle_deg": 90})
    m = s.query("measure", {"entity": "AR-001"})
    assert m["radius"] == 100.0 and m["diameter"] == 200.0
    assert m["sweep"] == "90°00'00\"" and m["length"] == pytest.approx(math.pi * 50)


def test_measure_needs_two_ends_or_one_entity():
    s = session()
    r = s.query("measure", {"from": [0, 0]})
    assert not r["ok"] and "'from' and 'to'" in r["error"]["message"]


def test_dxf_export_writes_the_dimension_as_the_lines_and_text_it_renders(tmp_path):
    s = road(session(tmp_path))
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 2, "layer": "V-ANNO-DIMS"}))
    path = s.query("export_dxf", {"path": str(tmp_path / "dim.dxf")})["path"]
    import ezdxf
    msp = ezdxf.readfile(path).modelspace()
    on_layer = [e for e in msp if e.dxf.layer == "V-ANNO-DIMS"]
    assert sorted(e.dxftype() for e in on_layer) == \
        ["LINE", "LINE", "LINE", "LWPOLYLINE", "LWPOLYLINE", "TEXT"]
    text = next(e for e in on_layer if e.dxftype() == "TEXT")
    assert text.dxf.text == "24.00'"


def test_a_sheet_dimension_warns_when_it_runs_off_the_paper():
    s = session()
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    r = ok(s.execute("place_dimension", {"space": "C-101", "kind": "aligned",
                                         "p1": [2, 2], "p2": [40, 2],
                                         "line_point": [20, 1]}))
    assert any("beyond the" in w for w in r["warnings"])


def test_a_sheet_renders_a_dimension_drawn_in_model_space(tmp_path):
    s = road(session(tmp_path))
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    ok(s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11],
                                     "width_in": 30, "height_in": 18,
                                     "model_center": [200, 0], "feet_per_inch": 50.0}))
    ok(s.execute("place_dimension", {
        "space": "model", "kind": "linear", "p1": [100, -12], "p2": [100, 12],
        "line_point": [180, 0], "text_height": 5}))
    out = s.query("render_sheet", {"sheet": "C-101", "dpi": 60})
    assert out["ok"] and out["size_bytes"] > 0


# ------------------------------------------------- through a twisted view

TWISTS = (-170.0, -135.0, -100.0, -75.0, -30.0, 20.0, 60.0, 95.0, 140.0, 180.0)


def _reads_upright(paper_deg: float) -> bool:
    folded = (paper_deg + 180.0) % 360.0 - 180.0
    return -90.0 - 1e-6 <= folded <= 90.0 + 1e-6


def _on_paper(v, twist: float):
    """A model direction as a viewport twisted ``twist`` shows it."""
    a = math.radians(twist)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


@pytest.mark.parametrize("twist", TWISTS)
def test_a_model_dimension_given_the_view_s_twist_reads_upright_on_the_sheet(twist):
    """A dimension's text reads upright in the model, so through a twisted
    viewport it can plot upside down however the dimension is drawn.  Given
    the viewport's twist (``view_rotation``, as the labelers take it) the text
    reads upright on the sheet and sits above its line as read there."""
    blind = 0
    for heading in range(0, 360, 15):
        a = math.radians(heading)
        ahead, left = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        p1, p2 = [1000.0, 1000.0], [1000.0 + 120.0 * ahead[0], 1000.0 + 120.0 * ahead[1]]
        drag = [1000.0 + 60.0 * ahead[0] + 30.0 * left[0],
                1000.0 + 60.0 * ahead[1] + 30.0 * left[1]]
        s = session()
        base = {"space": "model", "kind": "aligned", "p1": p1, "p2": p2, "line_point": drag,
                "text_height": 5.0, "layer": "V-ANNO-DIMS"}
        ok(s.execute("place_dimension", base))
        ok(s.execute("place_dimension", {**base, "view_rotation": twist}))
        plain, seen = parts(s, "DM-001")["text"], parts(s, "DM-002")["text"]
        blind += not _reads_upright(plain.rotation_deg + twist)
        assert _reads_upright(seen.rotation_deg + twist), (heading, twist, seen.rotation_deg)
        # the text stands off the dimension line on the side that is up on the paper
        line = parts(s, "DM-002")["line"]
        mid = [(line.start[0] + line.end[0]) / 2.0, (line.start[1] + line.end[1]) / 2.0]
        off = _on_paper((seen.position[0] - mid[0], seen.position[1] - mid[1]), twist)
        reading = math.radians(seen.rotation_deg + twist)
        assert off[0] * -math.sin(reading) + off[1] * math.cos(reading) > 0.0, (heading, twist)
        # and it is the same dimension: the number, the line and the measured points
        assert seen.content == plain.content == "120.00'"
        assert line.start == pytest.approx(parts(s, "DM-001")["line"].start)
    assert blind, "some heading reads upside down through this twist without view_rotation"


def test_an_untwisted_dimension_is_recorded_as_it_always_was():
    s = road(session())
    base = {"space": "model", "kind": "aligned", "p1": [100, -12], "p2": [100, 12],
            "line_point": [180, 0], "text_height": 2.0, "layer": "V-ANNO-DIMS"}
    ok(s.execute("place_dimension", base))
    ok(s.execute("place_dimension", {**base, "view_rotation": 0}))
    ok(s.execute("place_dimension", {**base, "view_rotation": 120.0}))
    plain, zero, turned = (s.doc.model_entities[i] for i in ("DM-001", "DM-002", "DM-003"))
    assert "view_rotation" not in plain.to_dict() and "view_rotation" not in zero.to_dict()
    assert turned.to_dict()["view_rotation"] == 120.0
    assert [(e.TYPE, getattr(e, "rotation_deg", None), getattr(e, "position", None))
            for e in zero.primitives(s.doc)] == \
           [(e.TYPE, getattr(e, "rotation_deg", None), getattr(e, "position", None))
            for e in plain.primitives(s.doc)]
    again = type(turned).from_dict(turned.to_dict())
    assert again.view_rotation == 120.0
    assert again.primitives(s.doc)[-1].rotation_deg == turned.primitives(s.doc)[-1].rotation_deg


@pytest.mark.parametrize("twist", (-135.0, -60.0, 75.0, 180.0))
def test_radial_and_angular_text_read_through_the_twist_too(twist):
    for heading in range(0, 360, 30):
        a = math.radians(heading)
        out = [math.cos(a), math.sin(a)]
        s = session()
        common = {"space": "model", "layer": "V-ANNO-DIMS", "text_height": 4.0,
                  "view_rotation": twist}
        ok(s.execute("place_dimension", {**common, "kind": "radius", "center": [0, 0],
                                         "radius": 200.0,
                                         "line_point": [100 * out[0], 100 * out[1]]}))
        ok(s.execute("place_dimension", {**common, "kind": "radius", "center": [0, 0],
                                         "radius": 20.0,
                                         "line_point": [60 * out[0], 60 * out[1]]}))
        ok(s.execute("place_dimension", {
            **common, "kind": "angular", "center": [0, 0], "p1": [50 * out[0], 50 * out[1]],
            "p2": [50 * math.cos(a + 1.0), 50 * math.sin(a + 1.0)],
            "line_point": [80 * math.cos(a + 0.5), 80 * math.sin(a + 0.5)]}))
        for dim_id in ("DM-001", "DM-002", "DM-003"):
            text = parts(s, dim_id)["text"]
            assert _reads_upright(text.rotation_deg + twist), (dim_id, heading, twist)
        # the leader's landing and its text run level on the sheet
        leader = parts(s, "DM-002")
        run = _on_paper((leader["landing"].end[0] - leader["landing"].start[0],
                         leader["landing"].end[1] - leader["landing"].start[1]), twist)
        assert run[1] == pytest.approx(0.0, abs=1e-9)
        assert (leader["text"].rotation_deg + twist) % 360.0 == pytest.approx(0.0, abs=1e-9)
        # the text runs away from the leader: it starts where the landing ends
        assert (leader["text"].halign == "left") == (run[0] > 0.0)


def test_a_twisted_dimension_keeps_its_twist_when_it_is_moved_copied_turned_or_mirrored():
    """The viewport has not turned because the dimension moved: every edit that
    rebuilds a dimension carries ``view_rotation`` along, or the number would
    go back to reading upright in the model and upside down on the sheet."""
    twist = 150.0
    base = {"space": "model", "kind": "aligned", "p1": [100, -12], "p2": [100, 12],
            "line_point": [110, 0], "text_height": 2.0, "layer": "V-ANNO-DIMS",
            "view_rotation": twist}
    edits = [
        ("move_entities", {"ids": ["DM-001"], "delta": [10, 5]}),
        ("copy_entities", {"ids": ["DM-001"], "delta": [50.0, 0.0]}),
        ("rotate_entities", {"ids": ["DM-001"], "base": [100, 0], "angle": 35}),
        ("scale_entities", {"ids": ["DM-001"], "base": [100, 0], "factor": 2.0}),
        ("mirror_entities", {"ids": ["DM-001"], "line": [[0, 40], [400, 40]]}),
        ("array_entities", {"ids": ["DM-001"], "kind": "rectangular", "rows": 1, "columns": 3,
                            "column_spacing": 60.0}),
    ]
    for name, params in edits:
        s = road(session())
        ok(s.execute("place_dimension", base))
        ok(s.execute(name, params))
        dims = [e for e in s.doc.model_entities.values() if e.TYPE == "dimension"]
        assert len(dims) >= 1 and all(d.view_rotation == twist for d in dims), name
        for d in dims:
            text = [e for e in d.primitives(s.doc) if e.TYPE == "text"][0]
            assert _reads_upright(text.rotation_deg + twist), (name, d.id)
        ok(s.execute("undo", {}))
        assert s.doc.model_entities["DM-001"].view_rotation == twist


def test_modify_entity_sets_and_clears_a_dimension_s_twist():
    s = road(session())
    ok(s.execute("place_dimension", {"space": "model", "kind": "aligned", "p1": [100, -12],
                                     "p2": [100, 12], "line_point": [110, 0],
                                     "text_height": 2.0, "layer": "V-ANNO-DIMS"}))
    assert s.doc.model_entities["DM-001"].view_rotation is None
    ok(s.execute("modify_entity", {"id": "DM-001", "changes": {"view_rotation": 150.0}}))
    assert s.doc.model_entities["DM-001"].view_rotation == 150.0
    assert _reads_upright(parts(s)["text"].rotation_deg + 150.0)
    ok(s.execute("modify_entity", {"id": "DM-001", "changes": {"view_rotation": 0}}))
    assert s.doc.model_entities["DM-001"].view_rotation is None
    assert "view_rotation" not in s.doc.model_entities["DM-001"].to_dict()
    ok(s.execute("modify_entity", {"id": "DM-001", "changes": {"view_rotation": -40.0}}))
    assert s.doc.model_entities["DM-001"].view_rotation == -40.0
    # a field no dimension has is still refused, and the hint lists this one
    r = s.execute("modify_entity", {"id": "DM-001", "changes": {"twist": 5}})
    assert not r["ok"] and "view_rotation" in r["error"]["hint"]
    # on a sheet there is no view to read it through
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    r = ok(s.execute("place_dimension", {"space": "C-101", "kind": "aligned", "p1": [2, 2],
                                         "p2": [6, 2], "line_point": [4, 3]}))
    r = s.execute("modify_entity", {"id": r["created"][0], "changes": {"view_rotation": 30.0}})
    assert not r["ok"] and "already reads upright" in r["error"]["message"]


def test_view_rotation_is_for_model_dimensions_and_a_sheet_one_says_so():
    s = session()
    ok(s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"}))
    r = ok(s.execute("place_dimension", {"space": "C-101", "kind": "aligned",
                                         "p1": [2, 2], "p2": [6, 2], "line_point": [4, 3],
                                         "view_rotation": 120.0}))
    assert any("view_rotation 120 was not used" in w for w in r["warnings"])
    dim = s.doc.sheets["SH-001"].entities[r["created"][0]]
    assert dim.view_rotation is None
    assert parts(s, dim.id, "C-101")["text"].rotation_deg == 0.0


def test_the_repl_grammar_reaches_dimensioning():
    from roaddraft.api.lines import route_line
    s = road(session())
    r = route_line(s, "dim aligned of_entity=LN-001 line_point=200,-40 text_height=8")
    assert r["kind"] == "result" and r["result"]["ok"]
    assert '"400.00\'"' in r["result"]["message"]
    d = route_line(s, "dist LN-001 LN-002")
    assert d["result"]["distance"] == pytest.approx(24.0)
