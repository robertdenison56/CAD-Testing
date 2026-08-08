import math

from roaddraft.core import geometry as geo


def test_rotate_point():
    p = geo.rotate_point([1, 0], 90)
    assert abs(p[0]) < 1e-9 and abs(p[1] - 1) < 1e-9
    p = geo.rotate_point([2, 0], 90, origin=[1, 0])
    assert abs(p[0] - 1) < 1e-9 and abs(p[1] - 1) < 1e-9


def test_arc_bbox_quadrants():
    bb = geo.arc_bbox([0, 0], 10, 0, 90)
    for got, want in zip(bb, (0, 0, 10, 10)):
        assert abs(got - want) < 1e-9
    bb = geo.arc_bbox([0, 0], 10, -90, -60)  # demo curve orientation
    assert abs(bb[0] - 0) < 1e-9
    assert abs(bb[1] - (-10)) < 1e-9
    assert abs(bb[2] - 5) < 1e-9  # cos(-60)*10
    assert abs(bb[3] - (-10 * math.sin(math.radians(60)))) < 1e-6


def test_arc_bbox_wraparound():
    bb = geo.arc_bbox([0, 0], 5, 350, 10)
    assert abs(bb[2] - 5) < 1e-9  # crosses 0 degrees
    assert bb[0] > 4.9 - 5  # small sweep only


def test_viewport_transform_no_rotation():
    t = geo.ViewportTransform([17, 11], [5000, 3000], 50)
    assert t.to_paper([5000, 3000]) == [17, 11]
    p = t.to_paper([5050, 3000])
    assert abs(p[0] - 18) < 1e-9 and abs(p[1] - 11) < 1e-9
    back = t.to_model(p)
    assert abs(back[0] - 5050) < 1e-9 and abs(back[1] - 3000) < 1e-9


def test_viewport_transform_with_twist():
    t = geo.ViewportTransform([17, 11], [5000, 3000], 50, rotation_deg=90)
    p = t.to_paper([5050, 3000])
    assert abs(p[0] - 17) < 1e-9 and abs(p[1] - 12) < 1e-9
    back = t.to_model(p)
    assert abs(back[0] - 5050) < 1e-6 and abs(back[1] - 3000) < 1e-6


def test_visible_model_bbox():
    t = geo.ViewportTransform([17, 11], [5000, 3000], 50)
    bb = t.visible_model_bbox(10, 10)
    assert bb == (4750, 2750, 5250, 3250)


def test_text_bbox_alignment():
    bb = geo.text_bbox([0, 0], "ABCD", 1.0, halign="left", valign="bottom")
    assert bb[0] == 0 and bb[1] == 0 and abs(bb[2] - 2.8) < 1e-9 and bb[3] == 1.0
    bb = geo.text_bbox([0, 0], "ABCD", 1.0, halign="center", valign="middle")
    assert abs(bb[0] + 1.4) < 1e-9 and abs(bb[1] + 0.5) < 1e-9


def test_bbox_utils():
    assert geo.bbox_union((0, 0, 1, 1), (2, 2, 3, 3)) == (0, 0, 3, 3)
    assert geo.bbox_intersects((0, 0, 2, 2), (1, 1, 3, 3))
    assert not geo.bbox_intersects((0, 0, 1, 1), (2, 2, 3, 3))
    assert geo.bbox_contains((0, 0, 10, 10), (1, 1, 2, 2))
    assert not geo.bbox_contains((0, 0, 10, 10), (9, 9, 11, 11))
