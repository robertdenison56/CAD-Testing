"""Reading a referenced design: station-based addressing inside a sheet file.

A plan set keeps the design in one file and the sheets in another that
references it, so the sheet file owns no alignments at all. Before this, every
roadway-native way to name a place -- "station 25+00", "the PC of the first
curve" -- answered "no alignment named 'SR-100'" exactly where annotation
happens. Queries now accept ``"DESIGN:SR-100"``.

Two invariants carry the weight:

* **points come back in host coordinates**, so they land on the geometry as
  drawn even when the attachment is moved, turned or scaled;
* **commands still refuse it.** Reading a referenced design is not owning it:
  nothing can be drawn, labelled or anchored to an alignment in someone else's
  file.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import entity_distance
from roaddraft.document.locate import resolve_entity

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def design_file(tmp_path):
    model = Session(project_name="design", out_dir=tmp_path)
    model.execute("create_layer", {"name": "V-ALIGN-CNTR"})
    model.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                       "pis": A_PIS})
    model.execute("draw_alignment", {"alignment": "SR-100", "layer": "V-ALIGN-CNTR"})
    model.execute("draw_offset", {"offsets": [-12, 12], "layer": "V-ALIGN-CNTR"})
    path = tmp_path / "design.rdoc.json"
    model.query("save_document", {"path": str(path)})
    return path


def plans(tmp_path, **attach):
    """A sheet file with the design referenced in, placed as asked."""
    design_file(tmp_path)
    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdoc.json")})
    r = host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                          "path": "design.rdoc.json", **attach})
    assert r["ok"], r
    return host


def test_a_sheet_file_can_read_the_design_it_references(tmp_path):
    s = plans(tmp_path)
    assert s.query("list_alignments", {})["alignments"] == []

    listed = s.query("list_alignments", {"include_references": True})
    assert listed["count"] == 1
    row = listed["alignments"][0]
    assert row["name"] == "DESIGN:SR-100" and row["reference"] == "DESIGN"
    assert row["read_only"] is True and row["curves"] == 1
    assert row["begin_station_text"] == "10+00.00"

    where = s.query("station_to_xy", {"alignment": "DESIGN:SR-100", "station": "16+00"})
    assert where["ok"] and where["point"] == pytest.approx([1600.0, 1000.0], abs=1e-6)

    pc = s.query("resolve_anchor", {"alignment": "DESIGN:SR-100", "anchor": "PC-1"})
    assert pc["ok"] and pc["auto_content"] == "16+00.00 BC"
    assert pc["point"] == pytest.approx([1600.0, 1000.0], abs=1e-6)
    assert "anchor to this referenced alignment" in pc["labelling"]

    curves = s.query("get_design_data", {"kind": "curves", "alignment": "DESIGN:SR-100"})
    assert curves["total"] == 1 and curves["rows"][0]["radius"] == 800.0


@pytest.mark.parametrize("attach,label", [
    ({}, "as placed"),
    ({"offset": [500.0, 300.0]}, "moved"),
    ({"offset": [500.0, 300.0], "rotation_deg": 30.0}, "moved and turned"),
    ({"offset": [-200.0, 50.0], "rotation_deg": -15.0, "scale": 2.0}, "scaled too"),
])
def test_points_land_on_the_geometry_as_drawn(tmp_path, attach, label):
    """The invariant: a station point must sit on the centerline the sheet
    actually shows, however the attachment is placed."""
    s = plans(tmp_path, **attach)
    centerline = [row["id"] for row in
                  s.query("find_entities", {"anchor": {"kind": "element"}})["entities"]]
    assert centerline, label

    for station in ("11+00", "16+00", "20+00"):
        r = s.query("station_to_xy", {"alignment": "DESIGN:SR-100", "station": station})
        assert r["ok"], r
        best = min(_distance_to(s, eid, r["point"]) for eid in centerline)
        assert best < 1e-6, f"{label}: {station} is {best:.4f} off the drawn centerline"

    # and an anchor point, which travels the same road
    pc = s.query("resolve_anchor", {"alignment": "DESIGN:SR-100", "anchor": "PC-1"})
    best = min(_distance_to(s, eid, pc["point"]) for eid in centerline)
    assert best < 1e-6, label


def _distance_to(session, eid, point) -> float:
    entity, owner, _ref, _space = resolve_entity(session.doc, eid)
    return entity_distance(owner, entity, point)


def test_xy_to_station_reads_host_coordinates_and_round_trips(tmp_path):
    s = plans(tmp_path, offset=[500.0, 300.0], rotation_deg=30.0)
    out = s.query("station_to_xy", {"alignment": "DESIGN:SR-100", "station": "16+00",
                                    "offset": 12.0})
    back = s.query("xy_to_station", {"alignment": "DESIGN:SR-100", "point": out["point"]})
    assert back["ok"], back
    assert back["station"] == pytest.approx(1600.0, abs=1e-3)
    assert back["offset"] == pytest.approx(12.0, abs=1e-3)
    assert back["side"] == "R"
    assert back["on_point"] == pytest.approx(out["on_point"], abs=1e-6)


def test_the_design_reads_as_designed_even_when_the_attachment_is_scaled(tmp_path):
    """Stations, radii and bearings describe the road; only points describe the
    sheet. A doubled attachment draws twice the size and is still a 800 ft curve."""
    s = plans(tmp_path, scale=2.0)
    curves = s.query("get_design_data", {"kind": "curves", "alignment": "DESIGN:SR-100"})
    row = curves["rows"][0]
    assert row["radius"] == 800.0 and row["delta_dms"] == "30°00'00\""
    assert row["pc_station_text"] == "16+00.00"
    placement = curves["placement"]
    assert placement["reference"] == "DESIGN" and placement["scale"] == 2.0
    assert "as designed" in placement["note"] and placement["read_only"] is True
    # the PC point, though, is where the sheet draws it: twice as far out
    assert row["pc"] == pytest.approx([3200.0, 2000.0], abs=1e-6)


def test_reading_a_referenced_design_is_not_owning_it(tmp_path):
    """The boundary: queries answer, the drawing and design commands refuse and
    say why, and the labelers anchor through the reference (2026-10-11)."""
    s = plans(tmp_path)
    s.execute("create_layer", {"name": "V-ANNO-TEXT"})
    for command, params in (
            ("draw_alignment", {"alignment": "DESIGN:SR-100"}),
            ("draw_offset", {"alignment": "DESIGN:SR-100", "offsets": [-12]}),
            ("modify_alignment", {"name": "DESIGN:SR-100",
                                  "changes": {"rename": "MINE"}}),
            ("delete_alignment", {"name": "DESIGN:SR-100"})):
        r = s.execute(command, params)
        assert not r["ok"], f"{command} should refuse a referenced alignment"
        assert "attached reference" in r["error"]["message"], command
        assert "place_label" in r["error"]["hint"], command
    assert s.doc.model_entities == {}
    r = s.execute("place_label", {"space": "model", "alignment": "DESIGN:SR-100",
                                  "anchor": "PC-1", "layer": "V-ANNO-TEXT"})
    assert r["ok"], r
    e = s.doc.model_entities[r["created"][0]]
    assert e.content == "16+00.00 BC" and e.anchor["alignment"] == "DESIGN:SR-100"
    assert e.anchor["placed_by"] == "place_label" and e.position == pytest.approx([1600.0, 1022.5])
    r = s.execute("modify_reference", {"name": "DESIGN", "changes": {"offset": [10.0, 0.0]}})
    assert r["ok"], r
    r = s.execute("place_label", {"space": "model", "alignment": "DESIGN:SR-100",
                                  "anchor": "PT-1", "layer": "V-ANNO-TEXT"})
    assert not r["ok"] and "at identity" in r["error"]["message"]
    # the basefile is untouched by all of that
    assert s.query("get_design_data", {"kind": "curves",
                                       "alignment": "DESIGN:SR-100"})["total"] == 1


def test_the_errors_say_where_the_alignments_actually_are(tmp_path):
    s = plans(tmp_path)
    r = s.query("station_to_xy", {"alignment": "SR-100", "station": "16+00"})
    assert not r["ok"] and "no alignment named 'SR-100'" in r["error"]["message"]
    assert "DESIGN:SR-100" in r["error"]["hint"]
    assert "owns no alignments" in r["error"]["hint"]

    r = s.query("station_to_xy", {"alignment": "DESIGN:NOPE", "station": "16+00"})
    assert not r["ok"] and "no alignment 'DESIGN:NOPE'" in r["error"]["message"]
    assert "DESIGN:SR-100" in r["error"]["hint"]

    r = s.query("station_to_xy", {"alignment": "MISSING:SR-100", "station": "16+00"})
    assert not r["ok"] and "DESIGN:SR-100" in r["error"]["hint"]

    bare = Session()
    r = bare.query("station_to_xy", {"alignment": "X:Y", "station": "16+00"})
    assert not r["ok"] and "no attachment carries a design model" in r["error"]["hint"]


def test_a_detached_reference_takes_its_design_with_it(tmp_path):
    s = plans(tmp_path)
    assert s.query("list_alignments", {"include_references": True})["count"] == 1
    assert s.execute("detach_reference", {"name": "DESIGN"})["ok"]
    assert s.query("list_alignments", {"include_references": True})["count"] == 0
    r = s.query("station_to_xy", {"alignment": "DESIGN:SR-100", "station": "16+00"})
    assert not r["ok"]


def test_the_host_own_design_is_unaffected_by_any_of_this(tmp_path):
    """No qualified name, no placement block, no behaviour change."""
    s = Session(project_name="own", out_dir=tmp_path)
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": A_PIS})
    listed = s.query("list_alignments", {})
    assert listed["alignments"][0]["name"] == "SR-100"
    assert "reference" not in listed["alignments"][0]
    curves = s.query("get_design_data", {"kind": "curves", "alignment": "SR-100"})
    assert "placement" not in curves
    r = s.query("station_to_xy", {"alignment": "SR-100", "station": "16+00"})
    assert r["point"] == pytest.approx([1600.0, 1000.0], abs=1e-6)
    assert s.execute("draw_alignment", {"alignment": "SR-100"})["ok"]
