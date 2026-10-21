"""Laying an alignment out by PI and editing it afterwards: angle points (a PI
whose tangents meet with no curve, before its curve is chosen), curves added
later, and redrawing the drawn centerline in the same undoable command."""
import pytest

from roaddraft.api.session import Session
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (CurveElement, PI, TangentElement, compile_pis,
                                         pis_from_elements)
from roaddraft.web.server import WebApp

LAYOUT = [[0, 0], [1000, 0, 0], [1800, 600, 0], [3000, 600]]  # tangents only


def kinds(elements):
    return [e.kind for e in elements]


# ------------------------------------------------------------ the engine


def test_angle_points_compile_only_when_asked_for():
    with pytest.raises(DesignError, match="angle point"):
        compile_pis(LAYOUT)
    els = compile_pis(LAYOUT, angle_points=True)
    assert kinds(els) == ["tangent", "tangent", "tangent"]
    assert els[0].end == [1000.0, 0.0] and els[1].start == [1000.0, 0.0]
    assert els[1].start_dist == pytest.approx(1000.0)
    assert els[2].start_dist == pytest.approx(2000.0)  # 1000 + the 1000' leg


def test_angle_points_and_curves_mix():
    els = compile_pis([[0, 0], [1000, 0, 0], [1800, 600, 500], [3000, 600]],
                      angle_points=True)
    assert kinds(els) == ["tangent", "tangent", "curve", "tangent"]
    assert els[1].start == [1000.0, 0.0]          # turns at the angle point
    assert isinstance(els[2], CurveElement) and els[2].radius == 500.0
    for a, b in zip(els, els[1:]):                # continuous
        assert a.end == pytest.approx(b.start)
        assert a.start_dist + a.length == pytest.approx(b.start_dist)


def test_an_angle_point_cannot_turn_back_on_itself():
    with pytest.raises(DesignError, match="180"):
        compile_pis([[0, 0], [1000, 0, 0], [500, 0]], angle_points=True)


def test_angle_points_come_back_from_elements():
    pis = [[0, 0], [1000, 0, 0], [1800, 600, 500], [3000, 600]]
    recovered = pis_from_elements(compile_pis(pis, angle_points=True))
    assert [(round(q.point[0], 6), round(q.point[1], 6), q.radius) for q in recovered] \
        == [(0, 0, 0), (1000, 0, 0), (1800, 600, 500), (3000, 600, 0)]


def test_a_straight_run_of_tangents_is_not_an_angle_point():
    straight = [TangentElement([0, 0], [500, 0], 500, 0.0, 0),
                TangentElement([500, 0], [900, 0], 400, 0.0, 500)]
    assert [q.point for q in pis_from_elements(straight)] == [[0.0, 0.0], [900.0, 0.0]]


# ------------------------------------------------------------ the commands


def laid_out(session, **extra):
    r = session.execute("create_alignment", {"name": "A", "pis": LAYOUT,
                                             "angle_points": True, **extra})
    assert r["ok"], r
    return r


def test_create_by_pi_then_add_a_curve_and_redraw_in_one_step():
    s = Session()
    laid_out(s)
    s.execute("create_layer", {"name": "C-ALIGN", "color": "red"})
    assert s.execute("draw_alignment", {"alignment": "A", "layer": "C-ALIGN",
                                        "linetype": "center"})["ok"]
    before = sorted(s.doc.model_entities)
    pis = [[0, 0], [1000, 0, 400], [1800, 600, 0], [3000, 600]]  # a curve at PI-2
    r = s.execute("modify_alignment", {"name": "A", "changes": {"pis": pis},
                                       "angle_points": True, "redraw": True})
    assert r["ok"], r
    assert "drawn on C-ALIGN" in r["message"] and r["warnings"] == []
    drawn = list(s.doc.model_entities.values())
    assert sorted(e.TYPE for e in drawn) == ["arc", "line", "line", "line"]
    assert {(e.layer, e.linetype) for e in drawn} == {("C-ALIGN", "center")}
    assert set(r["deleted"]) == set(before) and len(r["created"]) == 4
    s.execute("undo", {})  # one step back: the tangent layout and its drawing
    assert sorted(s.doc.model_entities) == before
    assert s.doc.design.alignments["A"].curves() == []


def test_redraw_does_nothing_for_an_alignment_never_drawn():
    s = Session()
    laid_out(s)
    r = s.execute("modify_alignment", {
        "name": "A", "changes": {"pis": [[0, 0], [1000, 0, 300], [1800, 600, 0],
                                         [3000, 600]]},
        "angle_points": True, "redraw": True})
    assert r["ok"] and s.doc.model_entities == {}


def test_redraw_and_the_labels_following_leave_nothing_stale():
    """The label used to be named in a warning as not regenerated; it now
    follows the design (commands/label_updates.py), and the redrawn centerline
    is draw_alignment's work."""
    s = Session()
    laid_out(s)
    s.execute("draw_alignment", {"alignment": "A"})
    label = s.execute("place_label", {"space": "model", "alignment": "A",
                                      "anchor": "15+00"})["created"][0]
    pis = [[0, 0], [1000, 0, 300], [1800, 600, 0], [3000, 600]]
    r = s.execute("modify_alignment", {"name": "A", "changes": {"pis": pis},
                                       "angle_points": True, "redraw": True})
    assert r["ok"] and r["warnings"] == [] and label in r["modified"]
    fresh = Session()
    fresh.execute("create_alignment", {"name": "A", "pis": pis, "angle_points": True})
    want = fresh.doc.model_entities[fresh.execute("place_label", {
        "space": "model", "alignment": "A", "anchor": "15+00"})["created"][0]]
    got = s.doc.model_entities[label]
    assert got.position == pytest.approx(want.position) and got.content == want.content
    assert {e.anchor["placed_by"] for e in s.doc.model_entities.values()
            if e.anchor["kind"] == "element"} == {"draw_alignment"}


def test_without_angle_points_a_modify_still_teaches_the_radius():
    s = Session()
    laid_out(s)
    r = s.execute("modify_alignment", {"name": "A", "changes": {"pis": LAYOUT}})
    assert not r["ok"] and "angle point" in r["error"]["message"]


# ------------------------------------------------------------ the GUI state


def test_the_gui_gets_each_alignments_pis():
    s = Session()
    laid_out(s)
    a = WebApp(s).state()["alignments"][0]
    assert a["editable"] is True
    assert a["pis"] == [[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0], [1800.0, 600.0, 0.0],
                        [3000.0, 600.0, 0.0]]
    assert a["tangents"] == 3 and a["curves"] == 0


def test_an_imported_alignment_with_a_kink_is_editable_by_pi():
    s = Session()
    r = s.execute("create_alignment", {"name": "IMP", "elements": [
        {"kind": "tangent", "start": [0, 0], "end": [1000, 0]},
        {"kind": "tangent", "start": [1000, 0], "end": [1800, 600]}]})
    assert r["ok"], r
    a = WebApp(s).state()["alignments"][0]
    assert a["source"] == "elements" and a["editable"] is True
    assert [p[:2] for p in a["pis"]] == [[0.0, 0.0], [1000.0, 0.0], [1800.0, 600.0]]
