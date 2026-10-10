"""Window and crossing selection (document/window_select.py): the entities a
box dragged in the GUI's Select tool takes in. A window takes what lies wholly
inside it; a crossing also takes what it touches, judged on the geometry
rather than on bounding boxes."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.document.window_select import window_ids

BOX = ([0, 0], [20, 20])


def drawing() -> Session:
    s = Session()

    def run(command, params):
        r = s.execute(command, {"space": "model", **params})
        assert r["ok"], r
    run("draw_line", {"start": [2, 2], "end": [10, 10]})            # LN-001 inside
    run("draw_line", {"start": [-5, 30], "end": [30, -5]})          # LN-002 across
    run("draw_line", {"start": [25, 40], "end": [40, 25]})          # LN-003 clear
    run("draw_line", {"start": [15, 50], "end": [50, 15]})          # LN-004 beside
    run("draw_circle", {"center": [10, 10], "radius": 50})          # CI-001 around
    run("draw_arc", {"center": [10, 10], "radius": 5,
                     "start_angle_deg": 0, "end_angle_deg": 90})    # AR-001 inside
    run("place_text", {"position": [18, 18], "content": "EOP", "height": 2})
    return s


def select(s, a, b, crossing=False):
    return window_ids(s.doc, s.doc.model_entities, a, b, crossing=crossing)


def test_a_window_takes_only_what_lies_wholly_inside():
    assert select(drawing(), *BOX) == ["LN-001", "AR-001"]


def test_a_crossing_takes_what_it_touches_too():
    assert select(drawing(), *BOX, crossing=True) == [
        "LN-001", "LN-002", "AR-001", "TX-001"]


def test_crossing_is_decided_on_the_geometry_not_the_box():
    """LN-004's box overlaps the window but the line passes beside it, and the
    circle's box holds the window but the circle never enters it."""
    found = select(drawing(), *BOX, crossing=True)
    assert "LN-004" not in found and "CI-001" not in found


def test_the_corners_can_come_in_either_order():
    s = drawing()
    assert select(s, [20, 20], [0, 0]) == select(s, [0, 20], [20, 0]) == \
        select(s, *BOX)


def test_nothing_on_a_layer_switched_off():
    s = drawing()
    s.execute("create_layer", {"name": "HIDDEN"})
    s.execute("draw_line", {"space": "model", "layer": "HIDDEN",
                            "start": [5, 5], "end": [6, 6]})
    assert "LN-005" in select(s, *BOX)
    assert s.execute("modify_layer", {"name": "HIDDEN",
                                      "changes": {"visible": False}})["ok"]
    assert "LN-005" not in select(s, *BOX)
    assert "LN-005" not in select(s, *BOX, crossing=True)


def test_a_hatch_is_touched_by_a_crossing_inside_its_fill():
    s = Session()
    s.execute("draw_polyline", {"space": "model", "closed": True, "vertices": [
        [-100, -100], [100, -100], [100, 100], [-100, 100]]})
    assert s.execute("hatch", {"space": "model", "at": [0, 0], "pattern": "SOLID"})["ok"]
    assert select(s, *BOX, crossing=True) == ["HT-001"]
    assert select(s, *BOX) == []
    assert select(s, [-150, -150], [150, 150]) == ["PL-001", "HT-001"]


def test_a_block_is_judged_by_the_linework_it_draws():
    s = Session()
    assert s.execute("define_block", {"name": "TICK", "entities": [
        {"type": "line", "start": [0, 0], "end": [10, 0]},
        {"type": "line", "start": [0, 0], "end": [0, 10]}]})["ok"]
    assert s.execute("insert_block", {"space": "model", "block_name": "TICK",
                                      "position": [100, 100]})["ok"]
    bid = next(iter(s.doc.model_entities))
    # inside the block's box, between its two arms: no linework there
    assert select(s, [105, 105], [109, 109], crossing=True) == []
    assert select(s, [104, 98], [106, 102], crossing=True) == [bid]
    assert select(s, [95, 95], [115, 115]) == [bid]
