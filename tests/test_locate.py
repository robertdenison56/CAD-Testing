"""Points on entities (document/locate.py).

The numbers that matter here are the arc ones. A 1,200 ft radius curve through
18.435 degrees has a chord 15.50 ft short of its own midpoint, so an agent that
averages the endpoints to "find the middle" aims 15.50 ft off the curve -- 0.31
in on paper at 1"=50'. point_at lands on the curve instead.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, Circle, Line, Polyline, Text, entity_distance
from roaddraft.document.locate import (
    as_fraction, entity_length, nearest_entity, point_at, representative_point,
    resolve_entity,
)

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def session_A(tmp_path=None) -> Session:
    s = Session(project_name="locate-tests", out_dir=tmp_path)
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": A_PIS})
    s.execute("draw_offset", {"offsets": [-12, 12]})
    return s


def test_as_fraction_names_and_numbers():
    assert as_fraction("start") == 0.0
    assert as_fraction("mid") == as_fraction("middle") == 0.5
    assert as_fraction("END") == 1.0
    assert as_fraction(0.25) == 0.25
    for bad in (-0.1, 1.5, "halfway", True, None):
        with pytest.raises(ValueError):
            as_fraction(bad)


def test_point_at_along_a_line():
    line = Line(id="LN-1", start=[0.0, 0.0], end=[100.0, 0.0])
    assert point_at(None, line, "start")[0] == pytest.approx([0.0, 0.0])
    assert point_at(None, line, "mid")[0] == pytest.approx([50.0, 0.0])
    assert point_at(None, line, "end")[0] == pytest.approx([100.0, 0.0])
    assert point_at(None, line, 0.25)[0] == pytest.approx([25.0, 0.0])
    assert point_at(None, line, "mid")[1] == pytest.approx(0.0)
    assert entity_length(None, line) == pytest.approx(100.0)


def test_point_at_on_an_arc_is_on_the_arc_not_on_its_chord():
    """R=1200 through 18.435 deg: the chord misses the curve by 15.50 ft."""
    arc = Arc(id="AR-1", center=[0.0, 0.0], radius=1200.0,
              start_angle_deg=270.0, end_angle_deg=288.434948822922)
    for where in ("start", "mid", "end", 0.25, 0.75):
        point, _direction = point_at(None, arc, where)
        assert entity_distance(None, arc, point) < 1e-9, where
        assert math.dist(point, arc.center) == pytest.approx(1200.0, abs=1e-9)
    start = point_at(None, arc, "start")[0]
    end = point_at(None, arc, "end")[0]
    chord_mid = [(start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0]
    sagitta = entity_distance(None, arc, chord_mid)
    assert sagitta == pytest.approx(15.50, abs=0.01)      # the trap, measured
    assert entity_length(None, arc) == pytest.approx(1200.0 * math.radians(18.434948822922),
                                                     abs=1e-6)
    # travelling CCW the tangent leads the radius by 90 degrees
    assert point_at(None, arc, "start")[1] == pytest.approx(0.0, abs=1e-9)


def test_point_at_walks_a_polyline_by_length():
    poly = Polyline(id="PL-1", vertices=[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]])
    assert entity_length(None, poly) == pytest.approx(200.0)
    assert point_at(None, poly, "mid")[0] == pytest.approx([100.0, 0.0])
    assert point_at(None, poly, 0.25)[0] == pytest.approx([50.0, 0.0])
    assert point_at(None, poly, 0.75)[0] == pytest.approx([100.0, 50.0])
    assert point_at(None, poly, 0.75)[1] == pytest.approx(90.0)
    closed = Polyline(id="PL-2", vertices=[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]],
                      closed=True)
    assert entity_length(None, closed) > 20.0      # the closing leg counts


def test_point_at_on_a_circle_and_on_things_with_no_path():
    circle = Circle(id="CI-1", center=[0.0, 0.0], radius=10.0)
    assert point_at(None, circle, "start")[0] == pytest.approx([10.0, 0.0])
    assert point_at(None, circle, 0.25)[0] == pytest.approx([0.0, 10.0], abs=1e-9)
    assert entity_length(None, circle) == pytest.approx(2 * math.pi * 10.0)
    text = Text(id="TX-1", position=[5.0, 6.0], content="EP", height=1.0)
    assert point_at(None, text, "mid")[0] == pytest.approx([5.0, 6.0])
    assert entity_length(None, text) is None


def test_representative_point_of_every_pavement_edge_is_on_it():
    s = session_A()
    for entity in s.doc.model_entities.values():
        point = representative_point(s.doc, entity)
        assert entity_distance(s.doc, entity, point) < 1e-6, entity.id


def test_resolve_entity_finds_its_own_and_referenced_entities(tmp_path):
    base = session_A(tmp_path)
    base_path = tmp_path / "design.rdoc.json"
    base.query("save_document", {"path": str(base_path)})

    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdoc.json")})
    host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                      "path": "design.rdoc.json"})
    host.execute("draw_line", {"space": "model", "start": [0, 0], "end": [1, 1]})

    own = resolve_entity(host.doc, "LN-001")
    assert own is not None and own[2] is None and own[3] == "model"
    through = resolve_entity(host.doc, "DESIGN:AR-001")
    assert through is not None
    entity, owner, ref, space = through
    assert entity.TYPE == "arc" and ref == "DESIGN" and space == "model"
    assert point_at(owner, entity, "mid")[0]
    assert resolve_entity(host.doc, "DESIGN:NOPE") is None
    assert resolve_entity(host.doc, "NOSUCHREF:AR-001") is None
    assert resolve_entity(host.doc, "unqualified") is None


def test_nearest_entity_reaches_through_a_reference(tmp_path):
    base = session_A(tmp_path)
    base_path = tmp_path / "design.rdoc.json"
    base.query("save_document", {"path": str(base_path)})
    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdoc.json")})
    host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                      "path": "design.rdoc.json"})
    on_the_edge = nearest_entity(host.doc, "model", [1300.0, 988.0])
    assert on_the_edge[0].startswith("DESIGN:") and on_the_edge[1] < 1e-6
    far = nearest_entity(host.doc, "model", [1300.0, 2000.0])
    assert far[1] > 100.0
    assert nearest_entity(Session().doc, "model", [0.0, 0.0]) is None
