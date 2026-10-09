"""Paths (document/paths.py): walking, projecting onto, offsetting and
intersecting linework, the kernel under offset, fillet, measure-along and snaps.

Sides follow the roadway convention: right of the direction of travel is
positive, as draw_offset takes 12 for 12 ft right. The strongest check here is
the cross-check against the design engine: SR-100 drawn as a line, an arc and a
line, offset 12 ft each way as a chain of entities, lands exactly where
draw_offset puts its edges -- tangents shifted, the curve 788 / 812 ft about the
same centre.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document import paths
from roaddraft.document.entities import Arc, Circle, Line, Polyline
from roaddraft.document.paths import ArcSeg, Path, PathError, Seg

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
L_SHAPE = Polyline(id="PL-1", vertices=[[0, 0], [100, 0], [100, 100]])


def ends(piece):
    return [round(v, 9) for v in piece.start + piece.end]


# --------------------------------------------------------------- projecting


def test_a_segment_projects_along_and_square_right_positive():
    s, foot, offset = Seg([0, 0], [100, 0]).project([30, -4])
    assert (s, foot, offset) == (pytest.approx(30.0), pytest.approx([30.0, 0.0]),
                                 pytest.approx(4.0))  # south of an eastbound line is right
    s, _foot, offset = Seg([0, 0], [100, 0]).project([130, 2])
    assert s == pytest.approx(130.0) and offset == pytest.approx(-2.0)


def test_an_arc_projects_right_outside_when_counter_clockwise_inside_when_clockwise():
    ccw = ArcSeg([0, 0], 100, 0, 90)
    s, foot, offset = ccw.project([0, 120])
    assert s == pytest.approx(50 * math.pi) and foot == pytest.approx([0, 100], abs=1e-9)
    assert offset == pytest.approx(20.0)
    cw = ccw.reversed()
    s, _foot, offset = cw.project([0, 120])
    assert s == pytest.approx(0.0, abs=1e-9) and offset == pytest.approx(-20.0)
    # past the end it runs on round the circle, to whichever end is nearer
    s, _foot, _off = ccw.project([-10, 100])
    assert s > ccw.length


def test_a_path_projects_onto_the_nearest_perpendicular_with_extensions_and_corners():
    path = Path.of_entity(L_SHAPE)
    p = path.project([50, -7])
    assert (p.along, p.offset, p.side, p.perpendicular, p.beyond) == \
        (pytest.approx(50.0), pytest.approx(7.0), "right", True, None)
    p = path.project([120, 50])
    assert p.along == pytest.approx(150.0) and p.offset == pytest.approx(20.0)
    p = path.project([-20, 3])
    assert p.beyond == "start" and p.along == pytest.approx(-20.0) and p.side == "left"
    p = path.project([100, 130])
    assert p.beyond == "end" and p.along == pytest.approx(230.0)
    # outside the corner there is no perpendicular: the corner itself
    p = path.project([110, -10])
    assert not p.perpendicular and p.foot == pytest.approx([100.0, 0.0])
    assert p.offset == pytest.approx(math.hypot(10, 10)) and p.side == "right"


def test_nearest_never_uses_an_extension():
    path = Path.of_entity(Line(id="LN-1", start=[0, 0], end=[100, 0]))
    point, distance, along = path.nearest([130, 40])
    assert point == pytest.approx([100.0, 0.0]) and distance == pytest.approx(50.0)
    assert along == pytest.approx(100.0)


# ------------------------------------------------------------------- chains


def test_a_chain_is_oriented_head_to_tail_from_the_first_entity():
    l1 = Line(id="LN-1", start=[0, 0], end=[100, 0])
    arc = Arc(id="AR-1", center=[100, 100], radius=100, start_angle_deg=-90, end_angle_deg=0)
    l2 = Line(id="LN-2", start=[200, 300], end=[200, 100])  # drawn the other way
    chain = Path.of_chain([l1, arc, l2])
    assert [p.kind for p in chain.pieces] == ["line", "arc", "line"]
    assert ends(chain.pieces[2]) == [200, 100, 200, 300]
    assert chain.owners == [0, 1, 2] and chain.length == pytest.approx(300 + 50 * math.pi)
    back = Path.of_chain([l2, arc, l1])
    assert back.pieces[1].sweep == pytest.approx(-90.0)  # the arc run clockwise
    assert back.start == pytest.approx([200.0, 300.0]) and back.end == pytest.approx([0, 0])


def test_a_chain_with_a_gap_or_a_closed_member_is_refused():
    with pytest.raises(PathError) as e:
        Path.of_chain([Line(id="LN-1", start=[0, 0], end=[10, 0]),
                       Line(id="LN-2", start=[11, 0], end=[20, 0])])
    assert "does not join" in str(e.value) and "in order" in e.value.hint
    with pytest.raises(PathError):
        Path.of_chain([Line(id="LN-1", start=[0, 0], end=[10, 0]),
                       Circle(id="CI-1", center=[20, 0], radius=10)])


# ---------------------------------------------------------------- offsetting


def test_an_l_offsets_mitred_outside_trimmed_inside_or_rounded():
    path = Path.of_entity(L_SHAPE)
    out, notes = path.offset(10)  # right of east-then-north is the outside
    assert [ends(p) for p in out] == [[0, -10, 110, -10], [110, -10, 110, 100]] and not notes
    inside, _ = path.offset(-10)
    assert [ends(p) for p in inside] == [[0, 10, 90, 10], [90, 10, 90, 100]]
    rounded, _ = path.offset(10, join="round")
    assert [p.kind for p in rounded] == ["line", "arc", "line"]
    corner = rounded[1]
    assert corner.center == pytest.approx([100, 0]) and corner.radius == pytest.approx(10)
    assert corner.start == pytest.approx([100, -10]) and corner.end == pytest.approx([110, 0],
                                                                                     abs=1e-9)


def test_offsetting_the_drawn_alignment_chain_matches_draw_offset():
    s = Session()
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00", "pis": A_PIS})
    drawn = s.execute("draw_alignment", {})["created"]
    edges = s.execute("draw_offset", {"offsets": [-12, 12]})["created"]
    chain = Path.of_chain([s.doc.model_entities[i] for i in drawn])
    by_offset = {}
    for eid in edges:
        e = s.doc.model_entities[eid]
        by_offset.setdefault(e.anchor["offset"], []).append(e)
    for d in (-12.0, 12.0):
        pieces, notes = chain.offset(d)
        assert not notes
        want = by_offset[d]
        assert len(pieces) == len(want) == 3
        for piece, e in zip(pieces, want):
            cls, geometry = paths.entity_fields_of(piece)
            assert cls is type(e)
            if cls is Line:
                assert geometry["start"] == pytest.approx(e.start, abs=1e-9)
                assert geometry["end"] == pytest.approx(e.end, abs=1e-9)
            else:
                assert geometry["center"] == pytest.approx(e.center, abs=1e-9)
                assert geometry["radius"] == pytest.approx(e.radius, abs=1e-9)
                assert geometry["radius"] in (pytest.approx(788.0), pytest.approx(812.0))


def test_an_arc_or_circle_offset_keeps_its_centre_and_refuses_to_collapse():
    arc_path = Path.of_entity(Arc(id="AR-1", center=[0, 0], radius=50,
                                  start_angle_deg=0, end_angle_deg=90))
    out, _ = arc_path.offset(-20)  # left of counter-clockwise travel: the inside
    assert out[0].radius == pytest.approx(30.0) and out[0].center == [0.0, 0.0]
    with pytest.raises(PathError) as e:
        arc_path.offset(-60)
    assert "inside of the curve" in e.value.hint
    circle = Path.of_entity(Circle(id="CI-1", center=[5, 5], radius=10))
    cls, geometry = paths.entity_fields_of(circle.offset(3)[0][0])
    assert cls is Circle and geometry == {"center": [5.0, 5.0], "radius": 13.0}


def test_a_piece_too_short_for_the_distance_drops_out_and_its_neighbours_meet():
    # a square that misses closing by a few hundredths, as a traverse does
    box = Polyline(id="PL-2", closed=True,
                   vertices=[[0, 0], [0, 100], [100, 100], [100.0, -0.02], [0.03, -0.02]])
    out, notes = Path.of_entity(box).offset(10)  # clockwise travel: right is inside
    assert len(out) == 4 and "dropped" in notes[0] and "piece 5" in notes[0]
    corners = sorted([round(v, 3) for v in p.start] for p in out)
    # the bottom edge runs at y = -0.02, so its parallel is at 9.98
    assert corners == [[10.0, 9.98], [10.0, 90.0], [90.0, 9.98], [90.0, 90.0]]
    with pytest.raises(PathError) as e:
        Path.of_entity(box).offset(60)
    assert "inside out" in str(e.value)


# ------------------------------------------------------------- intersections


def test_pieces_meet_only_where_both_really_are():
    assert paths.piece_intersections(Seg([0, 0], [10, 10]), Seg([0, 10], [10, 0])) == \
        [pytest.approx([5.0, 5.0])]
    assert paths.piece_intersections(Seg([0, 0], [4, 4]), Seg([0, 10], [10, 0])) == []
    upper = ArcSeg([0, 0], 100, 0, 180)
    hits = paths.piece_intersections(Seg([-200, 50], [200, 50]), upper)
    assert sorted(round(q[0], 6) for q in hits) == [round(-math.sqrt(7500), 6),
                                                     round(math.sqrt(7500), 6)]
    assert paths.piece_intersections(Seg([-200, -50], [200, -50]), upper) == []
    assert paths.circle_circle([0, 0], 5, [8, 0], 5) == [pytest.approx([4, 3]),
                                                         pytest.approx([4, -3])]
    assert paths.line_circle([-10, 5], [10, 5], [0, 0], 5) == [pytest.approx([0.0, 5.0])]
