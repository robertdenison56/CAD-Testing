"""Object snaps and inquiry (document/snaps.py, the key_points / snap queries,
and measure along): the exact points a drafter picks instead of eyeballing,
and distances measured along a line and square off it.

The sheet-file tests are the ones that matter for plan production: in a sheet
file the design is a referenced basefile, seen through viewports, and a snap
on the paper has to land on it -- in paper inches -- the way a leader is drawn
to the edge of pavement it labels.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document import snaps
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Line, Polyline, Text,
)
from roaddraft.probes import fixture

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def kinds(points):
    return sorted((sp.kind, tuple(round(v, 6) for v in sp.point)) for sp in points)


def sr100() -> Session:
    s = Session()
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00", "pis": A_PIS})
    s.execute("draw_alignment", {})
    s.execute("draw_offset", {"offsets": [-12, 12]})
    return s


def q(s: Session, name: str, **params):
    r = s.query(name, params)
    assert r["ok"], r
    return r


# --------------------------------------------------------------- key points


def test_every_entity_type_offers_its_key_points():
    line = Line(id="LN-1", start=[0, 0], end=[10, 0])
    assert kinds(snaps.entity_key_points(line)) == [
        ("endpoint", (0.0, 0.0)), ("endpoint", (10.0, 0.0)), ("midpoint", (5.0, 0.0))]
    box = Polyline(id="PL-1", vertices=[[0, 0], [10, 0], [10, 10]], closed=True)
    got = snaps.entity_key_points(box)
    assert [sp.kind for sp in got].count("endpoint") == 3
    assert [sp.kind for sp in got].count("midpoint") == 3  # the closing side too
    arc = Arc(id="AR-1", center=[0, 0], radius=10, start_angle_deg=-45, end_angle_deg=100)
    got = kinds(snaps.entity_key_points(arc))
    assert ("center", (0.0, 0.0)) in got
    assert [k for k in got if k[0] == "quadrant"] == [("quadrant", (0.0, 10.0)),
                                                      ("quadrant", (10.0, 0.0))]
    mid = [k for k in got if k[0] == "midpoint"][0][1]
    assert math.hypot(*mid) == pytest.approx(10.0)  # on the arc, not on its chord
    circle = Circle(id="CI-1", center=[5, 5], radius=1)
    assert len([sp for sp in snaps.entity_key_points(circle) if sp.kind == "quadrant"]) == 4
    for e in (Text(id="TX-1", position=[1, 2], content="A", height=1),
              BlockRef(id="BR-1", block_name="NORTH_ARROW", position=[3, 4])):
        assert kinds(snaps.entity_key_points(e)) == [("insertion", tuple(e.position))]
    dim = Dimension(id="DM-1", kind="aligned", p1=[0, 0], p2=[10, 0], line_point=[5, 3])
    assert sorted(sp.label for sp in snaps.entity_key_points(dim)) == \
        ["line_point of DM-1", "p1 of DM-1", "p2 of DM-1"]


def test_an_alignment_offers_its_design_points_with_the_anchors_that_name_them():
    s = sr100()
    rows = q(s, "key_points", alignment="SR-100")["points"]
    by = {r["label"]: r for r in rows}
    assert by["BC-1 (PC-1) of SR-100"]["point"] == pytest.approx([1600.0, 1000.0], abs=1e-6)
    assert by["BC-1 (PC-1) of SR-100"]["anchor"] == "PC-1"
    assert by["PI-2 of SR-100"]["point"] == pytest.approx([1814.359354, 1000.0])
    assert by["EC-1 (PT-1) of SR-100"]["point"] == pytest.approx([2000.0, 1107.179677],
                                                                  abs=1e-6)
    assert "anchor" not in by["radius point of curve 1 of SR-100"]
    # the anchor really names the point: place_callout aims at it
    r = s.execute("place_callout", {"space": "model", "target_anchor": "PC-1",
                                    "position": [1650, 1100], "content": "BC"})
    assert r["ok"] and s.doc.model_entities[r["created"][0]].start == \
        pytest.approx(by["BC-1 (PC-1) of SR-100"]["point"], abs=1e-6)  # rows round to 6


def test_key_points_of_several_entities_include_where_they_cross():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 100]})
    s.execute("draw_line", {"space": "model", "start": [0, 100], "end": [100, 0]})
    s.execute("draw_circle", {"space": "model", "center": [50, 50], "radius": 20})
    rows = q(s, "key_points", ids=["LN-001", "LN-002", "CI-001"], kinds=["intersection"])
    points = sorted(tuple(round(v, 6) for v in r["point"]) for r in rows["points"])
    d = 20 / math.sqrt(2)
    assert len(points) == 5 and (50.0, 50.0) in points
    assert (round(50 + d, 6), round(50 + d, 6)) in points
    assert q(s, "key_points", space="model", bounds=[40, 40, 60, 60],
             kinds=["center"])["points"][0]["point"] == [50.0, 50.0]


# --------------------------------------------------------------------- snap


def test_the_nearest_key_point_wins_and_nearest_is_only_a_fallback():
    s = sr100()
    r = q(s, "snap", point=[1601.0, 1013.0])
    assert r["kind"] == "endpoint" and r["point"] == pytest.approx([1600.0, 1012.0])
    assert r["ids"] in (["LN-003"], ["AR-002"])
    r = q(s, "snap", point=[1601.0, 1001.0], modes=["design"])
    assert r["label"] == "BC-1 (PC-1) of SR-100" and r["anchor"] == "PC-1"
    r = q(s, "snap", point=[1300.0, 1003.0], modes=["endpoint", "nearest"])
    assert r["kind"] == "nearest" and r["point"] == pytest.approx([1300.0, 1000.0])
    r = q(s, "snap", point=[1300.0, 1050.0])
    assert not r["snapped"] and "tolerance" in r["hint"]


def test_perpendicular_and_tangent_snap_from_the_point_being_drawn_from():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    s.execute("draw_circle", {"space": "model", "center": [200, 0], "radius": 30})
    r = q(s, "snap", point=[41, 2], **{"from": [40, 60]}, modes=["perpendicular"])
    assert r["kind"] == "perpendicular" and r["point"] == pytest.approx([40.0, 0.0])
    r = q(s, "snap", point=[196, 29], **{"from": [100, 0]}, modes=["tangent"], tolerance=10)
    tangent = r["point"]
    radius_dir = [tangent[0] - 200, tangent[1]]
    to_from = [100 - tangent[0], 0 - tangent[1]]
    # square to the radius, to the 6 places the point is given in
    assert radius_dir[0] * to_from[0] + radius_dir[1] * to_from[1] == pytest.approx(0, abs=1e-4)
    err = s.query("snap", {"point": [1, 1], "modes": ["perpendicular"]})
    assert not err["ok"] and "from" in err["error"]["message"]


def test_snaps_find_referenced_linework_and_on_a_sheet_answer_in_paper_inches(tmp_path):
    s = Session.load(fixture.start_document(tmp_path, "sheets"))
    pc = next(r for r in q(s, "key_points", alignment="DESIGN:SR-100")["points"]
              if r.get("anchor") == "PC-1")["point"]
    # in the model, the referenced design's edges snap like the host's own
    r = q(s, "snap", point=[pc[0] + 1.0, pc[1] + 12.5], modes=["endpoint"])
    assert r["ids"][0].startswith("DESIGN:")
    # on the sheet that shows the BC, the snap sees it through the viewport
    for sheet in fixture.SHEETS:
        where = q(s, "model_to_sheet", sheet=sheet, point=pc)
        if where["visible"]:
            break
    paper = where["sheet_point"]
    r = q(s, "snap", space=sheet, point=[paper[0] + 0.03, paper[1] - 0.02],
          modes=["design"])
    assert r["kind"] == "design" and r["anchor"] == "PC-1"
    assert r["point"] == pytest.approx(paper, abs=1e-6)
    assert r["model_point"] == pytest.approx(pc, abs=1e-6) and r["viewport"]


# -------------------------------------------------------------- measure along


def test_measure_along_a_line_gives_distance_along_and_square_off_it():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    r = q(s, "measure", **{"from": [20, -5], "to": [70, 8]}, along="LN-001")
    assert r["from"]["along"] == 20.0 and r["from"]["offset"] == 5.0
    assert r["from"]["side"] == "right" and r["to"]["side"] == "left"
    assert r["along_distance"] == 50.0 and r["perpendicular_distance"] == 13.0
    assert r["along_text"] == "50.00'" and r["to"]["offset_text"] == "8.00' LEFT"
    r = q(s, "measure", **{"from": [130, 3]}, along="LN-001")
    assert r["from"]["beyond"] == "end" and r["from"]["along"] == 130.0


def test_measure_along_a_chain_and_along_the_alignment_agree():
    s = sr100()
    drawn = [eid for eid, e in s.doc.model_entities.items()
             if e.anchor and e.anchor.get("kind") == "element"]
    pts = {"from": [1300, 980], "to": [2000, 1100]}
    chain = q(s, "measure", **pts, along=drawn)
    design = q(s, "measure", **pts, along="SR-100")
    assert chain["to"]["along"] == pytest.approx(design["to"]["along"], abs=1e-6)
    assert chain["to"]["offset"] == pytest.approx(design["to"]["offset"], abs=1e-6)
    assert design["to"]["station_text"] == "20+15.32"
    assert design["along_distance"] == pytest.approx(715.316891, abs=1e-6)
    xy = q(s, "xy_to_station", point=[2000, 1100], alignment="SR-100")
    assert design["to"]["station"] == pytest.approx(xy["station"])


def test_measure_along_a_referenced_alignment_in_a_sheet_file(tmp_path):
    s = Session.load(fixture.start_document(tmp_path, "sheets"))
    pc = next(r for r in q(s, "key_points", alignment="DESIGN:SR-100")["points"]
              if r.get("anchor") == "PC-1")["point"]
    r = q(s, "measure", **{"from": pc}, along="DESIGN:SR-100")
    assert r["from"]["offset"] == pytest.approx(0.0, abs=1e-6)
    station = q(s, "resolve_anchor", anchor="PC-1", alignment="DESIGN:SR-100")
    assert r["from"]["station_text"] == station["station_text"]


def test_measure_along_faults_teach():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    r = s.query("measure", {"along": "LN-001"})
    assert not r["ok"] and "needs from" in r["error"]["message"]
    r = s.query("measure", {"from": [0, 0], "along": "NOPE"})
    assert not r["ok"]


def test_the_snap_pool_is_reused_until_the_drawing_changes():
    s = Session()
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    assert q(s, "snap", point=[99, 1])["point"] == [100.0, 0.0]
    pool = s._snap_pool("model", True)
    q(s, "snap", point=[1, 1])
    assert s._snap_pool("model", True) is pool          # same state: same pool
    s.execute("draw_line", {"space": "model", "start": [200, 0], "end": [300, 0]})
    assert q(s, "snap", point=[299, 1])["point"] == [300.0, 0.0]  # a command renews it
    s.execute("undo")
    assert not q(s, "snap", point=[299, 1])["snapped"]  # and so does an undo
