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


def test_a_labeler_in_a_sheet_file_is_sent_to_the_base_drawing_s_alignment(tmp_path):
    """The labelers work through a reference, so with no alignment of the
    document's own their fault names the one the base drawing carries, as
    the queries' does, and does not send the drafter to create_alignment."""
    s = plans(tmp_path)
    assert s.execute("create_layer", {"name": "V-ANNO-TEXT"})["ok"]
    assert s.execute("create_sheet", {"name": "C-101"})["ok"]
    lettering = [
        ("place_label", {"space": "model", "anchor": "PC-1", "layer": "V-ANNO-TEXT"}),
        ("place_label", {"space": "model", "alignment": "SR-100", "anchor": "PC-1",
                         "layer": "V-ANNO-TEXT"}),
        ("place_curve_table", {"space": "C-101", "position": [2, 2], "layer": "V-ANNO-TEXT"}),
        ("annotate_stationing", {"space": "model", "layer": "V-ANNO-TEXT"}),
        ("draw_station_offset", {"points": ["12+00@12L", "13+00@12L"],
                                 "layer": "V-ANNO-TEXT"}),
    ]
    for name, params in lettering:
        r = s.execute(name, params)
        assert not r["ok"], name
        hint = r["error"]["hint"]
        assert "owns no alignments" in hint and "['DESIGN:SR-100']" in hint, (name, hint)
        assert "create_alignment" not in hint, (name, hint)
    # the hint's name works as given
    r = s.execute("place_label", {"space": "model", "alignment": "DESIGN:SR-100",
                                  "anchor": "PC-1", "layer": "V-ANNO-TEXT"})
    assert r["ok"], r

    # a command that draws the design itself still says to make one: it cannot
    # work through a reference
    r = s.execute("draw_alignment", {"layer": "V-ANNO-TEXT"})
    assert not r["ok"] and "create_alignment" in r["error"]["hint"]

    # and a document with nothing attached is told the same as before
    bare = Session()
    assert bare.execute("create_layer", {"name": "V-ANNO-TEXT"})["ok"]
    r = bare.execute("place_label", {"space": "model", "anchor": "PC-1",
                                     "layer": "V-ANNO-TEXT"})
    assert not r["ok"] and "create_alignment" in r["error"]["hint"]
    r = bare.execute("annotate_stationing", {"space": "model", "layer": "V-ANNO-TEXT"})
    assert not r["ok"] and r["error"]["hint"] == ("or pass alignment=NAME for design-model "
                                                  "stationing")


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


# ------------------------------------------------- a referenced design profile

PVIS = [[1000, 100.0], [1500, 110.0, 300], [2000, 105.0]]


def profiled_plans(tmp_path):
    """The sheet file of ``plans``, its basefile carrying a profile on SR-100."""
    design_file(tmp_path)
    model = Session.load(tmp_path / "design.rdoc.json", out_dir=tmp_path)
    assert model.execute("create_profile", {"name": "SR-100 PGL", "alignment": "SR-100",
                                            "pvis": PVIS})["ok"]
    model.query("save_document", {"path": str(tmp_path / "design.rdoc.json")})
    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdoc.json")})
    assert host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                             "path": "design.rdoc.json"})["ok"]
    return host


def test_a_sheet_file_can_read_the_profile_its_basefile_carries(tmp_path):
    """A plan-and-profile sheet keeps the design in the alignment file; the
    profile reads through the reference the way the alignment does
    (pilot p06, 2026-10-19)."""
    s = profiled_plans(tmp_path)
    row = s.query("list_alignments", {"include_references": True})["alignments"][0]
    assert row["profiles"] == ["DESIGN:SR-100 PGL"]

    # the qualified name alone
    pvis = s.query("get_design_data", {"kind": "pvis", "profile": "DESIGN:SR-100 PGL"})
    assert pvis["ok"] and pvis["total"] == 3, pvis
    assert [r["elevation"] for r in pvis["rows"]] == [100.0, 110.0, 105.0]
    assert pvis["rows"][1]["station_text"] == "15+00.00"
    assert pvis["placement"]["reference"] == "DESIGN"

    # the referenced alignment, with or without the profile's own name
    for params in ({"alignment": "DESIGN:SR-100"},
                   {"alignment": "DESIGN:SR-100", "profile": "SR-100 PGL"},
                   {"alignment": "DESIGN:SR-100", "profile": "DESIGN:SR-100 PGL"}):
        vcs = s.query("get_design_data", {"kind": "vcs", **params})
        assert vcs["ok"] and vcs["total"] == 1, (params, vcs)
        assert vcs["rows"][0]["pvi_station_text"] == "15+00.00"
    overview = s.query("get_design_data", {"alignment": "DESIGN:SR-100"})
    assert overview["rows"][0]["profiles"] == ["DESIGN:SR-100 PGL"]
    profiles = s.query("get_design_data", {"kind": "profiles", "profile": "DESIGN:SR-100 PGL"})
    assert profiles["rows"][0]["station_range_text"] == "10+00.00 to 20+00.00"


def test_the_profile_errors_say_where_the_profiles_actually_are(tmp_path):
    s = profiled_plans(tmp_path)
    r = s.query("get_design_data", {"kind": "pvis", "profile": "SR-100 PGL"})
    assert not r["ok"] and "owns no profiles" in r["error"]["hint"]
    assert "DESIGN:SR-100 PGL" in r["error"]["hint"]
    r = s.query("get_design_data", {"kind": "pvis", "profile": "DESIGN:NOPE"})
    assert not r["ok"] and "no profile 'DESIGN:NOPE'" in r["error"]["message"]
    assert "DESIGN:SR-100 PGL" in r["error"]["hint"]
    r = s.query("get_design_data", {"kind": "pvis", "alignment": "DESIGN:SR-100",
                                    "profile": "NOPE"})
    assert not r["ok"] and "DESIGN:SR-100 PGL" in r["error"]["hint"]
    # nothing named: the host's own (none), and a pointer to the referenced ones
    r = s.query("get_design_data", {"kind": "profiles"})
    assert r["ok"] and r["total"] == 0 and "DESIGN:SR-100 PGL" in r["hint"]


def test_a_profile_is_created_in_the_file_that_owns_its_alignment(tmp_path):
    """create_profile still refuses a referenced alignment, and says where to
    put the profile instead."""
    s = profiled_plans(tmp_path)
    r = s.execute("create_profile", {"name": "MINE", "alignment": "DESIGN:SR-100",
                                     "pvis": PVIS})
    assert not r["ok"] and "attached reference" in r["error"]["message"]
    assert "create_profile there" in r["error"]["hint"]
    assert "get_design_data" in r["error"]["hint"]
    assert s.doc.design.profiles == {}


def test_the_host_own_profiles_read_as_before(tmp_path):
    s = Session(project_name="own", out_dir=tmp_path)
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00", "pis": A_PIS})
    assert s.execute("create_profile", {"name": "PGL", "alignment": "SR-100",
                                        "pvis": PVIS})["ok"]
    r = s.query("get_design_data", {"kind": "pvis", "profile": "PGL"})
    assert r["ok"] and r["total"] == 3 and "placement" not in r
    assert s.query("get_design_data", {})["rows"][0]["profiles"] == ["PGL"]
    r = s.query("get_design_data", {"kind": "pvis", "profile": "NOPE"})
    assert not r["ok"] and r["error"]["hint"] == "profiles: ['PGL']"
