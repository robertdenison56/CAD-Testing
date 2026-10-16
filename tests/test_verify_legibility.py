"""Paper-space legibility (verify.legibility): oriented text footprints,
separating-axis overlap, the usable area, labels seen through a twisted
viewport, and a dimension's lines or a callout's leader through text
(d1-verify-v4)."""
from __future__ import annotations

import pytest

from roaddraft.core import geometry as geo
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.verify.context import Context
from roaddraft.verify.legibility import (
    OVERLAP_EPS_IN, Item, Stroke, clip_segment, crosses, crossing_pairs, outside,
    overlap_depth, overlapping_pairs, sheet_items, sheet_strokes, text_quad,
)
from tests.verify_mutations import BASE, PAVEMENT, SHEET, Base, _dimension_through_the_bearing
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1 as _SPEC
_L = _SPEC["layers"]


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
    assert len(shown) >= len(b.labels("station")) // 2 > 1
    for e in shown:
        q = items[e.id].quad
        edge = (q[1][0] - q[0][0], q[1][1] - q[0][1])
        # the text's baseline direction on paper is its model rotation + the twist
        want = geo.rotate_point([1.0, 0.0], e.rotation_deg + 90.0)
        norm = (edge[0] ** 2 + edge[1] ** 2) ** 0.5
        assert edge[0] / norm == pytest.approx(want[0], abs=1e-9)
        assert edge[1] / norm == pytest.approx(want[1], abs=1e-9)


# ------------------------------------------------- labels cut by a viewport's edge


def test_a_label_cut_by_its_viewport_is_clipped_and_the_reference_is_not():
    """A two-sheet viewport is sized round the labels its share carries
    (generator, 2026-10-12), so the reference shows every label whole; a
    viewport squeezed until the square BC/EC labels cross its edge earns a
    ``clipped`` finding under D1-08, like an item off the sheet."""
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify import verify
    from roaddraft.verify.legibility import clipped

    task = generate_task(1, curves=2, equations=True, task_type="plan-sheet", sheets=2)
    session = session_for_task(task)
    reference_solution(task, session)
    ctx = Context.build(session.doc, task.truth, DRAFTING_SPEC_V1)
    assert all(clipped(ctx, sv) == [] for sv in ctx.sheets)
    report = verify(session.doc, task.truth)
    assert report.effective_score == 100.0 and not report.all_findings()
    # a viewport 2 in high centred on the PC: the BC label's position (0.45 in off the
    # line) is inside it, but the text runs past its edge
    sheet = session.doc.sheet_by_ref("C-101")
    vp = sheet.viewports[0]
    pc = session.query("resolve_anchor", {"alignment": "ALIGN-1", "anchor": "PC-1"})["anchor_point"]
    r = session.execute("modify_viewport", {"sheet": "C-101", "viewport_id": vp.id,
                                            "changes": {"height_in": 2.0, "width_in": 2.0,
                                                        "model_center": pc}})
    assert r["ok"], r
    ctx = Context.build(session.doc, task.truth, DRAFTING_SPEC_V1)
    cut = clipped(ctx, ctx.sheet_view("C-101"))
    assert cut, "the square curve-point labels should now cross the viewport's edge"
    report = verify(session.doc, task.truth)
    codes = {f.code for f in report.check("D1-08").findings}
    assert "clipped" in codes and report.check("D1-08").credit < 1.0
    assert {i for f in report.check("D1-08").findings if f.code == "clipped" for i in f.entity_ids} >= set(cut)


# ------------------------------------------------- lines through text (d1-verify-v4)


def _stroke(eid, a, b):
    return Stroke(eid, list(a), list(b), (min(a[0], b[0]), min(a[1], b[1]),
                                          max(a[0], b[0]), max(a[1], b[1])))


def test_a_line_through_a_text_box_crosses_one_along_its_edge_or_stopping_at_it_does_not():
    q = text_quad([0.0, 0.0], "AB", 0.1, 0.0, "left", "bottom")
    w = geo.text_size("AB", 0.1)[0]
    assert crosses([-1.0, 0.05], [1.0, 0.05], q)             # right through
    assert crosses([-1.0, 0.05], [w / 2.0, 0.05], q)         # ends inside
    assert crosses([0.01, 0.01], [0.02, 0.02], q)            # lies inside
    assert not crosses([-1.0, 0.0], [1.0, 0.0], q)           # along the bottom edge
    assert not crosses([-1.0, 0.05], [0.0, 0.05], q)         # stops at the left edge
    assert not crosses([-1.0, 0.05], [OVERLAP_EPS_IN / 2.0, 0.05], q)  # within the epsilon
    assert crosses([-1.0, 0.05], [2.0 * OVERLAP_EPS_IN, 0.05], q)      # past it
    assert not crosses([-1.0, 0.2], [1.0, 0.2], q)           # clear above
    turned = text_quad([0.0, 0.0], "AB", 0.1, 45.0, "left", "bottom")
    assert crosses([0.1, -1.0], [0.1, 1.0], turned)
    assert not crosses([-0.5, -0.5], [0.5, 0.5], [[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001]])
    items = [_item("A", q), _item("T", turned)]
    assert crossing_pairs(items, [_stroke("L", [-1.0, 0.05], [1.0, 0.05])]) == [("L", "A"), ("L", "T")]
    assert crossing_pairs(items, [_stroke("A", [-1.0, 0.05], [1.0, 0.05])]) == [("A", "T")]  # not its own
    assert crossing_pairs(items, [_stroke("L", [-1.0, 0.0], [1.0, 0.0])]) == []


def test_clip_segment_to_a_viewport_rect():
    rect = (0.0, 0.0, 10.0, 5.0)
    assert clip_segment([-5.0, 2.0], [15.0, 2.0], rect) == ([0.0, 2.0], [10.0, 2.0])
    assert clip_segment([1.0, 1.0], [2.0, 2.0], rect) == ([1.0, 1.0], [2.0, 2.0])
    assert clip_segment([-5.0, 6.0], [15.0, 6.0], rect) is None
    assert clip_segment([-1.0, -1.0], [-1.0, 7.0], rect) is None
    a, b = clip_segment([5.0, -5.0], [5.0, 2.5], rect)
    assert a == pytest.approx([5.0, 0.0]) and b == pytest.approx([5.0, 2.5])


def test_the_width_dimension_through_the_bearing_names_the_dimension_and_the_bearing():
    """The generator's own flaw until d1-v6: the width dimension line through
    the bearing lettered above the tangent's midpoint.  D1-08 now charges
    the pair, naming the dimension and the bearing; the strokes it judges
    are the dimension's lines seen through the viewport, inside it."""
    b = Base(**PAVEMENT)
    ctx = Context.build(b.doc, b.truth, DRAFTING_SPEC_V1)
    strokes = sheet_strokes(ctx)
    n_dims = len(b.truth.dimensions)
    # the dimension line, two extension lines and, with the text and arrows flipped
    # outside a 24-ft span, the two stubs; never the arrowheads
    assert n_dims >= 2 and len(strokes) == 5 * n_dims
    rect = ctx.views[0].rect
    for st in strokes:
        for v in (st.a, st.b):
            assert rect[0] - 1e-9 <= v[0] <= rect[2] + 1e-9 and rect[1] - 1e-9 <= v[1] <= rect[3] + 1e-9
    assert crossing_pairs(sheet_items(ctx), strokes) == []
    before = {e.id for e in b.doc.model_entities.values() if e.TYPE == "dimension"}
    _dimension_through_the_bearing(b)
    moved = [e.id for e in b.doc.model_entities.values()
             if e.TYPE == "dimension" and e.id not in before]
    assert len(moved) == 1
    report = b.verify()
    overlaps = [f for f in report.check("D1-08").findings if f.code == "overlap"]
    assert len(overlaps) == 1 and overlaps[0].entity_ids == [moved[0], b.label("T-1", "bearing").id]
    assert "runs through the text" in overlaps[0].note
    assert report.check("D1-08").credit == pytest.approx(0.75)
    # on the vague level the dimension may sit anywhere on the tangent: only legibility moves
    vague = b.verify("vague")
    assert vague.check("D1-13").credit == 1.0 and vague.check("D1-08").credit == pytest.approx(0.75)


def test_a_callout_leader_through_a_label_is_charged_to_the_callout_and_not_to_its_own_text():
    """A callout's leader (the chain place_callout draws from the target to
    the text) through a station label is an overlap of the callout text and
    the label; the leader stopping at its own text is not, nor a leader
    clear of everything."""
    b = Base(**BASE)
    ctx = Context.build(b.doc, b.truth, DRAFTING_SPEC_V1)
    assert sheet_strokes(ctx) == []  # the layout sheet dimensions nothing and calls nothing out
    view = ctx.views[0]
    items = {it.entity_id: it for it in sheet_items(ctx)}
    label = next(e for e in b.labels("station") if e.id in items)
    quad = items[label.id].quad
    c = [sum(v[0] for v in quad) / 4.0, sum(v[1] for v in quad) / 4.0]
    r = b.ex("place_callout", {"space": SHEET, "target": [c[0] - 1.0, c[1]],
                               "position": [c[0] + 1.0, c[1]], "content": "N", "layer": _L["labels"]})
    text_id = r["created"][-1]
    ctx = Context.build(b.doc, b.truth, DRAFTING_SPEC_V1)
    strokes = [st for st in sheet_strokes(ctx) if st.entity_id == text_id]
    assert len(strokes) == 2  # the leader and the shoulder, owned by the callout's text
    assert (text_id, label.id) in crossing_pairs(sheet_items(ctx), strokes)
    report = b.verify()
    pairs = [tuple(f.entity_ids) for f in report.check("D1-08").findings if f.code == "overlap"]
    assert (text_id, label.id) in pairs
    assert all(text_id not in p or label.id in p for p in pairs), pairs
    # a callout whose leader runs through nothing adds no finding
    free = view.transform.to_paper(b.free_model_point())
    r = b.ex("place_callout", {"space": SHEET, "target": [free[0] - 0.5, free[1]],
                               "position": free, "content": "N", "layer": _L["labels"]})
    clear_id = r["created"][-1]
    again = b.verify()
    assert len([f for f in again.check("D1-08").findings if f.code == "overlap"]) == len(pairs)
    assert all(clear_id not in f.entity_ids for f in again.check("D1-08").findings)
