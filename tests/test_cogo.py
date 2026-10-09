"""Coordinate geometry (design/cogo.py): bearings and distances in, points out.

The numbers come from the drafting-probes, which describe their alignments the
way a report does. RAMP-B runs N 62°30' E 900 ft to a PI, then deflects 35°
right for 1,100 ft: PI [1798.31, 1415.57], end [2888.90, 1271.99]. ELM-AVE
runs S 80° E 800 ft, deflects 40° left for 700 ft, then 25° right for 600 ft.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.design import cogo
from roaddraft.design.cogo import CogoError


def test_forward_and_inverse_are_easting_by_sine_northing_by_cosine():
    assert cogo.forward([1000.0, 1000.0], 62.5, 900.0) == pytest.approx([1798.3, 1415.5],
                                                                        abs=0.1)
    assert cogo.forward([0.0, 0.0], 90.0, 10.0) == pytest.approx([10.0, 0.0], abs=1e-12)
    assert cogo.forward([0.0, 0.0], 180.0, 10.0) == pytest.approx([0.0, -10.0], abs=1e-12)
    azimuth, distance = cogo.inverse([0.0, 0.0], [-3.0, -4.0])
    assert distance == pytest.approx(5.0)
    assert azimuth == pytest.approx(180.0 + math.degrees(math.atan2(3.0, 4.0)))


@pytest.mark.parametrize("text, azimuth", [
    ("N 45°30'15\" E", 45.504166666), ("S45-30-15W", 225.504166666), ("N45E", 45.0),
    ("S 80 E", 100.0), ("n 10 w", 350.0), ("S 0 E", 180.0), ("N 90 E", 90.0),
])
def test_quadrant_bearings_read_as_azimuths(text, azimuth):
    assert cogo.parse_quadrant_bearing(text) == pytest.approx(azimuth, abs=1e-6)


def test_a_bearing_past_90_degrees_or_out_of_order_is_refused_with_a_hint():
    with pytest.raises(CogoError) as e:
        cogo.parse_quadrant_bearing("N 100 E")
    assert "at most 90" in str(e.value) and "S 80 E" in e.value.hint
    with pytest.raises(CogoError):
        cogo.parse_quadrant_bearing("E 45 N")
    with pytest.raises(CogoError) as e:
        cogo.parse_quadrant_bearing(45.0)
    assert "azimuth" in e.value.hint


@pytest.mark.parametrize("value, turn, signed", [
    ("40 L", None, -40.0), ("L40", None, -40.0), ("40L", None, -40.0),
    ("25°00'00\" RT", None, 25.0), ("LEFT 40", None, -40.0), ("40 left", None, -40.0),
    (-40, None, -40.0), (40, None, 40.0), ("40-30-00R", None, 40.5),
    (40, "left", -40.0), ("40", "R", 40.0), ("40 L", "left", -40.0),
])
def test_a_deflection_says_its_side_and_right_is_positive(value, turn, signed):
    assert cogo.parse_deflection(value, turn) == pytest.approx(signed)


def test_a_deflection_that_names_two_sides_is_refused():
    with pytest.raises(CogoError):
        cogo.parse_deflection("40 L", "right")
    with pytest.raises(CogoError):
        cogo.parse_deflection(-40, "left")
    with pytest.raises(CogoError):
        cogo.parse_deflection("L 40 R")


def test_each_way_of_giving_a_direction_and_the_one_way_rule():
    assert cogo.direction_of_leg({"azimuth": "75°30'"}, None, "leg") == pytest.approx(75.5)
    assert cogo.direction_of_leg({"deflection": "40 L"}, 100.0, "leg") == pytest.approx(60.0)
    # angle right from the backsight: 180 + a right deflection
    assert cogo.direction_of_leg({"angle_right": 220}, 100.0, "leg") == pytest.approx(140.0)
    with pytest.raises(CogoError) as e:
        cogo.direction_of_leg({"bearing": "N 1 E", "azimuth": 1}, None, "legs[0]")
    assert "exactly one" in str(e.value)
    with pytest.raises(CogoError) as e:
        cogo.direction_of_leg({"deflection": "40 L"}, None, "legs[0]")
    assert "turned from the previous course" in str(e.value) and "initial" in e.value.hint


def test_a_square_traverse_closes_and_one_short_course_reports_its_precision():
    square = cogo.run_traverse([0, 0], [{"bearing": "N 0 E", "distance": 100},
                                        {"deflection": "90 R", "distance": 100},
                                        {"deflection": "90R", "distance": 100},
                                        {"deflection": 90, "distance": 100}])
    assert square.end == pytest.approx([0.0, 0.0], abs=1e-9)
    assert square.misclosure()["precision_text"] == "closes exactly"
    short = cogo.run_traverse([0, 0], [cogo.parse_leg_text(t) for t in (
        "N 0 E 100", "N 90 E 100", "S 0 E 100", "S 90 W 99.9")], close=True)
    m = short.misclosure()
    assert m["distance"] == pytest.approx(0.1)
    assert m["precision"] == pytest.approx(399.9 / 0.1)
    # due west, which either quadrant can name
    assert m["precision_text"] == "1:3,999" and m["bearing"].endswith("90°00'00\" W")
    assert short.closing is not None and short.closing.length == pytest.approx(0.1)


def test_a_tangent_curve_continues_the_course_before_it():
    t = cogo.run_traverse([0, 0], [{"azimuth": 90, "distance": 100},
                                   {"radius": 100, "turn": "left", "delta": 90},
                                   {"radius": 100, "turn": "right", "length": 50 * math.pi}])
    line, left, right = t.courses
    assert left.start == pytest.approx([100.0, 0.0])
    assert left.center == pytest.approx([100.0, 100.0])
    assert left.end == pytest.approx([200.0, 100.0], abs=1e-9)
    assert left.length == pytest.approx(50 * math.pi)
    assert left.azimuth_out == pytest.approx(0.0, abs=1e-9)
    # as an arc entity a left curve runs counter-clockwise from its start
    assert left.arc_angles() == pytest.approx((-90.0, 0.0))
    assert right.center == pytest.approx([300.0, 100.0])
    assert right.end == pytest.approx([300.0, 200.0], abs=1e-9)
    assert right.arc_angles() == pytest.approx((90.0, 180.0))
    assert t.end == pytest.approx([300.0, 200.0], abs=1e-9)


def test_a_non_tangent_curve_is_placed_by_its_chord_bearing():
    # R=100, 90 degrees to the right, chord N 45 E: it starts heading due north
    t = cogo.run_traverse([0, 0], [{"radius": 100, "turn": "R", "chord": 100 * math.sqrt(2),
                                    "chord_bearing": "N 45 E"}])
    c = t.courses[0]
    assert not c.tangent and c.delta == pytest.approx(90.0)
    assert c.azimuth_in == pytest.approx(0.0, abs=1e-9)
    assert c.center == pytest.approx([100.0, 0.0], abs=1e-9)
    assert c.end == pytest.approx([100.0, 100.0], abs=1e-9)


def test_curve_courses_that_cannot_be_computed_say_why():
    cases = [
        ({"radius": 100, "delta": 30}, "turn"),
        ({"radius": 100, "turn": "L", "chord": 250}, "does not fit"),
        ({"radius": 100, "turn": "L"}, "delta, length or chord"),
        ({"radius": 100, "turn": "L", "delta": 30}, "tangent curve"),  # nothing before it
        ({"radius": 100, "turn": "L", "delta": 30, "distance": 5}, "also distance"),
        ({"bearing": "N 1 E", "distance": 10, "delta": 5}, "needs a radius"),
    ]
    for leg, says in cases:
        with pytest.raises(CogoError) as e:
            cogo.run_traverse([0, 0], [leg])
        assert says in str(e.value), (leg, str(e.value))


@pytest.mark.parametrize("text, leg", [
    ("N 45°30'15\" E 250.00", {"bearing": "N 45°30'15\" E", "distance": 250.0}),
    ("S80E 800", {"bearing": "S80E", "distance": 800.0}),
    ("N45-30-15W 100'", {"bearing": "N45-30-15W", "distance": 100.0}),
    ("AZ 75.5 250", {"azimuth": "75.5", "distance": 250.0}),
    ("AZ=75°30' 250", {"azimuth": "75°30'", "distance": 250.0}),
    ("40 L 700 R=500", {"deflection": "40 L", "distance": 700.0, "radius": 500.0}),
    ("25°00'00\" RT 600", {"deflection": "25°00'00\" RT", "distance": 600.0}),
    ("CURVE R=500 LEFT DELTA=40", {"radius": 500.0, "turn": "left", "delta": "40"}),
    ("C R=300 R L=200", {"radius": 300.0, "turn": "right", "length": 200.0}),
    ("curve r=500 right chord=300 cb=N80E",
     {"radius": 500.0, "turn": "right", "chord": 300.0, "chord_bearing": "N80E"}),
])
def test_a_course_can_be_typed_the_way_it_is_written(text, leg):
    assert cogo.parse_leg_text(text) == leg


def test_unreadable_course_text_is_refused_with_the_forms_it_takes():
    for text in ("", "250", "NORTH 250", "45 250", "CURVE R=500 SIDEWAYS"):
        with pytest.raises(CogoError) as e:
            cogo.parse_leg_text(text)
        assert e.value.hint or "empty" in str(e.value), text


def test_ramp_b_pis_from_its_bearing_and_deflection():
    rows = cogo.pis_from_legs([1000.0, 1000.0],
                              [{"bearing": "N 62°30'00\" E", "distance": 900.0},
                               {"deflection": "35°00'00\" R", "radius": 600, "distance": 1100.0}])
    assert len(rows) == 3 and len(rows[0]) == 2 and len(rows[2]) == 2
    assert rows[1][:2] == pytest.approx([1798.31, 1415.57], abs=0.005)
    assert rows[1][2] == 600.0
    assert rows[2] == pytest.approx([2888.90, 1271.99], abs=0.005)


def test_elm_ave_pis_carry_the_bearing_through_two_deflections():
    rows = cogo.pis_from_legs([1000.0, 3000.0], [cogo.parse_leg_text(t) for t in (
        "S 80°00'00\" E 800", "40 L 700 R=500", "25 R 600 R=700")])
    expected = [[1000.0, 3000.0]]
    for az, d in ((100.0, 800.0), (60.0, 700.0), (85.0, 600.0)):
        expected.append(cogo.forward(expected[-1], az, d))
    assert [r[:2] for r in rows] == [pytest.approx(p, abs=1e-9) for p in expected]
    assert [r[2] if len(r) == 3 else 0 for r in rows] == [0, 500.0, 700.0, 0]


def test_alignment_legs_put_a_radius_on_the_leg_that_starts_at_its_pi():
    with pytest.raises(CogoError) as e:
        cogo.pis_from_legs([0, 0], [{"bearing": "N 0 E", "distance": 100, "radius": 50}])
    assert "BEGIN" in str(e.value) and "next leg" in e.value.hint
    with pytest.raises(CogoError) as e:
        cogo.pis_from_legs([0, 0], [{"bearing": "N 0 E", "distance": 100},
                                    {"radius": 50, "turn": "L", "delta": 30}])
    assert "tangent from PI to PI" in str(e.value)


def test_initial_direction_is_one_of_bearing_or_azimuth():
    assert cogo.initial_azimuth_of({"initial_bearing": "S 80 E"}) == pytest.approx(100.0)
    assert cogo.initial_azimuth_of({"initial_azimuth": 15}) == pytest.approx(15.0)
    assert cogo.initial_azimuth_of({}) is None
    with pytest.raises(CogoError):
        cogo.initial_azimuth_of({"initial_bearing": "N 1 E", "initial_azimuth": 1})
