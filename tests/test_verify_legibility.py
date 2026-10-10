"""Paper-space legibility (verify.legibility): oriented text footprints,
separating-axis overlap, the usable area, labels seen through a twisted
viewport."""
from __future__ import annotations

import pytest

from roaddraft.core import geometry as geo
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.verify.context import Context
from roaddraft.verify.legibility import (
    OVERLAP_EPS_IN, Item, outside, overlap_depth, overlapping_pairs, sheet_items, text_quad,
)
from tests.verify_mutations import BASE, SHEET, Base


def _item(eid, quad):
    return Item(eid, quad, tuple(geo.bbox_of_points(quad)))


def test_text_quad_matches_the_engine_box_when_square():
    q = text_quad([1.0, 2.0], "12+00.00", 0.1, 0.0, "center", "bottom")
    assert tuple(geo.bbox_of_points(q)) == pytest.approx(
        geo.text_bbox([1.0, 2.0], "12+00.00", 0.1, 0.0, "center", "bottom"))


def test_parallel_diagonal_labels_do_not_overlap_though_their_boxes_do():
    a = text_quad([0.0, 0.0], "12+00.00", 0.1, 45.0, "center", "bottom")
    b = text_quad([-0.2, 0.2], "13+00.00", 0.1, 45.0, "center", "bottom")
    assert geo.bbox_intersects(tuple(geo.bbox_of_points(a)), tuple(geo.bbox_of_points(b)))
    assert overlap_depth(a, b) <= 0.0
    assert overlapping_pairs([_item("A", a), _item("B", b)]) == []


def test_touching_is_not_overlapping_crossing_is():
    a = text_quad([0.0, 0.0], "AB", 0.1, 0.0, "left", "bottom")
    w = geo.text_size("AB", 0.1)[0]
    touching = text_quad([w, 0.0], "AB", 0.1, 0.0, "left", "bottom")
    crossing = text_quad([w / 2, 0.05], "AB", 0.1, 90.0, "left", "bottom")
    assert overlap_depth(a, touching) <= OVERLAP_EPS_IN
    assert overlapping_pairs([_item("A", a), _item("T", touching)]) == []
    assert overlapping_pairs([_item("A", a), _item("C", crossing)]) == [("A", "C")]


def test_outside_the_usable_area():
    usable = (0.5, 1.75, 33.5, 21.5)
    inside = _item("IN", text_quad([10, 10], "X", 0.1, 0, "left", "bottom"))
    edge = _item("EDGE", text_quad([33.45, 10], "XXXX", 0.1, 0, "left", "bottom"))
    assert outside([inside, edge], usable) == ["EDGE"]


def test_reference_sheet_items_are_every_label_the_table_and_the_north_arrow():
    b = Base(**BASE)
    ctx = Context.build(b.doc, b.truth, DRAFTING_SPEC_V1)
    items = sheet_items(ctx)
    assert len(items) == b.n_labels + 2
    assert overlapping_pairs(items) == [] and outside(items, ctx.usable) == []


def test_a_twisted_viewport_turns_the_labels_with_it():
    b = Base(**BASE)
    b.ex("modify_viewport", {"sheet": SHEET, "viewport_id": b.viewport.id,
                             "changes": {"rotation_deg": 90.0, "width_in": 18.5,
                                         "height_in": 18.5}})
    ctx = Context.build(b.doc, b.truth, DRAFTING_SPEC_V1)
    items = {it.entity_id: it for it in sheet_items(ctx)}
    shown = [e for e in b.labels("station") if e.id in items]
    assert len(shown) > 10
    for e in shown:
        q = items[e.id].quad
        edge = (q[1][0] - q[0][0], q[1][1] - q[0][1])
        # the text's baseline direction on paper is its model rotation + the twist
        want = geo.rotate_point([1.0, 0.0], e.rotation_deg + 90.0)
        norm = (edge[0] ** 2 + edge[1] ** 2) ** 0.5
        assert edge[0] / norm == pytest.approx(want[0], abs=1e-9)
        assert edge[1] / norm == pytest.approx(want[1], abs=1e-9)
