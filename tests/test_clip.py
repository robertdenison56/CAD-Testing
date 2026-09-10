"""Geometric clipping (reference clip boundary / masks) and its polygon
helpers."""
import math

from roaddraft.core import geometry as geo
from roaddraft.core.units import unit_factor
from roaddraft.document.clip import clip_primitives
from roaddraft.document.entities import Arc, Circle, Line, Polyline, Text

SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_point_in_polygon_inside_outside_edge():
    assert geo.point_in_polygon([5, 5], SQUARE)
    assert not geo.point_in_polygon([15, 5], SQUARE)
    assert geo.point_in_polygon([10, 5], SQUARE)  # on an edge counts as inside
    concave = [[0, 0], [10, 0], [10, 10], [5, 5], [0, 10]]
    assert not geo.point_in_polygon([5, 8], concave)
    assert geo.point_in_polygon([2, 2], concave)


def test_segment_polygon_params_and_circle_angles():
    ts = geo.segment_polygon_params([-5, 5], [15, 5], SQUARE)
    assert [round(t, 9) for t in ts] == [0.25, 0.75]
    assert geo.segment_polygon_params([2, 2], [8, 8], SQUARE) == []
    angles = geo.circle_polygon_angles([10, 5], 3, SQUARE)  # crosses x=10 twice
    assert [round(a, 6) for a in angles] == [90.0, 270.0]


def test_unit_factor_table():
    assert abs(unit_factor("m", "us_survey_ft") - 3937.0 / 1200.0) < 1e-12
    assert abs(unit_factor("us_survey_ft", "inch") - 12.000024) < 1e-6
    assert unit_factor("ft", "feet") == 1.0
    try:
        unit_factor("furlong", "m")
        assert False, "unknown unit must raise"
    except ValueError as ex:
        assert "furlong" in str(ex)


def test_no_region_returns_input_unchanged():
    ln = Line(id="LN-001", start=[-5, 5], end=[15, 5])
    assert clip_primitives([ln]) == [ln]


def test_line_inside_kept_outside_dropped_crossing_cut():
    inside = Line(id="A", start=[1, 1], end=[9, 9])
    outside = Line(id="B", start=[11, 1], end=[19, 9])
    crossing = Line(id="C", start=[-5, 5], end=[15, 5])
    out = clip_primitives([inside, outside, crossing], boundary=SQUARE)
    assert out[0] is inside
    assert [e.id for e in out] == ["A", "C#1"]
    assert out[1].start == [0, 5] and out[1].end == [10, 5]


def test_mask_splits_line_into_two_pieces():
    ln = Line(id="LN-001", start=[-5, 5], end=[15, 5], layer="TOPO", color="red")
    out = clip_primitives([ln], masks=[SQUARE])
    assert [e.id for e in out] == ["LN-001#1", "LN-001#2"]
    assert out[0].start == [-5, 5] and out[0].end == [0, 5]
    assert out[1].start == [10, 5] and out[1].end == [15, 5]
    assert out[0].layer == "TOPO" and out[0].color == "red"


def test_boundary_minus_mask():
    hole = [[4, 4], [6, 4], [6, 6], [4, 6]]
    ln = Line(id="L", start=[-5, 5], end=[15, 5])
    out = clip_primitives([ln], boundary=SQUARE, masks=[hole])
    assert [(e.start, e.end) for e in out] == [([0, 5], [4, 5]), ([6, 5], [10, 5])]


def test_polyline_open_runs_and_closed_wrap():
    zig = Polyline(id="P", vertices=[[-5, 2], [5, 2], [5, 8], [15, 8]])
    out = clip_primitives([zig], boundary=SQUARE)
    assert len(out) == 1 and out[0].id == "P#1"
    assert out[0].vertices == [[0, 2], [5, 2], [5, 8], [10, 8]]
    assert out[0].closed is False

    square = Polyline(id="Q", vertices=SQUARE, closed=True)
    left_half = [[-1, -1], [5, -1], [5, 11], [-1, 11]]
    out = clip_primitives([square], boundary=left_half)
    assert len(out) == 1  # the two runs meet at the start vertex and merge
    assert out[0].vertices == [[5, 10], [0, 10], [0, 0], [5, 0]]

    whole = clip_primitives([square], boundary=[[-1, -1], [11, -1], [11, 11], [-1, 11]])
    assert whole == [square] and whole[0].closed is True


def test_arc_and_circle_cut_into_arcs():
    arc = Arc(id="AR", center=[0, 0], radius=10, start_angle_deg=0, end_angle_deg=180)
    left = [[-20, -20], [0, -20], [0, 20], [-20, 20]]
    out = clip_primitives([arc], boundary=left)
    assert len(out) == 1 and out[0].id == "AR#1"
    assert abs(out[0].start_angle_deg - 90) < 1e-9
    assert abs(out[0].end_angle_deg - 180) < 1e-9

    circle = Circle(id="CI", center=[0, 0], radius=10)
    right = [[0, -20], [20, -20], [20, 20], [0, 20]]
    out = clip_primitives([circle], masks=[right])
    assert len(out) == 1 and isinstance(out[0], Arc)
    assert abs(out[0].start_angle_deg - 90) < 1e-9
    assert abs(out[0].end_angle_deg - 270) < 1e-9
    # untouched circles: kept when inside, dropped when outside
    small = Circle(id="S", center=[5, 5], radius=1)
    far = Circle(id="F", center=[50, 50], radius=1)
    assert clip_primitives([small, far], boundary=SQUARE) == [small]
    # a mask fully inside the circle hides nothing of its outline
    assert clip_primitives([circle], masks=[[[-1, -1], [1, -1], [1, 1], [-1, 1]]]) == [circle]


def test_text_kept_by_insertion_point():
    t_in = Text(id="T1", position=[5, 5], content="IN", height=1)
    t_out = Text(id="T2", position=[50, 5], content="OUT", height=1)
    assert clip_primitives([t_in, t_out], boundary=SQUARE) == [t_in]


def test_lineweight_hook_survives_cutting():
    ln = Line(id="L", start=[-5, 5], end=[15, 5])
    ln._lw_mm = 0.7
    out = clip_primitives([ln], boundary=SQUARE)
    assert out[0]._lw_mm == 0.7
