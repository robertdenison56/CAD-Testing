"""find_entities / point_on_entity: locating things without dumping the document.

The job these exist for is the one an agent faces in a sheet file: the design
lives in the basefile, so the host owns nothing, and "the pavement edges on
C-102" has to be answerable without shipping every entity in the project.
"""
from __future__ import annotations

import json

import pytest

from roaddraft.api.session import Session

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def project(tmp_path):
    """A model file with edges and shoulders, referenced into a one-sheet plan set."""
    model = Session(project_name="design", out_dir=tmp_path)
    for name in ("V-ALIGN-CNTR", "V-ROAD-EOP", "V-ROAD-SHLD"):
        model.execute("create_layer", {"name": name})
    model.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                       "pis": A_PIS})
    model.execute("draw_alignment", {"alignment": "SR-100", "layer": "V-ALIGN-CNTR"})
    model.execute("draw_offset", {"offsets": [-12, 12], "layer": "V-ROAD-EOP"})
    model.execute("draw_offset", {"offsets": [-20, 20], "layer": "V-ROAD-SHLD"})
    model.query("save_document", {"path": str(tmp_path / "design.rdoc.json")})

    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdoc.json")})
    host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                      "path": "design.rdoc.json"})
    host.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    host.execute("create_viewport", {"sheet": "C-101", "center_paper": [17.0, 11.7],
                                     "width_in": 31.0, "height_in": 18.5,
                                     "model_center": [1200.0, 1000.0],
                                     "feet_per_inch": 50.0})
    return host


def find(s, **params):
    r = s.query("find_entities", params)
    assert r["ok"], r
    return r


def test_find_by_anchor_picks_the_pavement_edges_out_of_the_reference(tmp_path):
    s = project(tmp_path)
    everything = find(s)
    assert everything["total"] == 15          # 3 centerline + 6 edge + 6 shoulder
    edges = find(s, anchor={"kind": "offset", "offset": [-12, 12]})
    assert edges["total"] == 6
    assert {e["anchor"]["offset"] for e in edges["entities"]} == {-12.0, 12.0}
    assert all(e["reference"] == "DESIGN" and e["read_only"] for e in edges["entities"])
    # one side only
    assert find(s, anchor={"kind": "offset", "offset": -12})["total"] == 3
    # a filter that matches nothing is empty, not an error
    assert find(s, anchor={"kind": "offset", "offset": 99})["total"] == 0


def test_every_row_carries_a_point_that_is_on_the_entity(tmp_path):
    from roaddraft.document.entities import entity_distance
    from roaddraft.document.locate import resolve_entity
    s = project(tmp_path)
    for row in find(s)["entities"]:
        entity, owner, _ref, _space = resolve_entity(s.doc, row["id"])
        assert entity_distance(owner, entity, row["point"]) < 1e-3, row["id"]
        assert row["length"] > 0


def test_find_by_layer_and_type(tmp_path):
    s = project(tmp_path)
    assert find(s, layer="V-ROAD-SHLD")["total"] == 6
    assert find(s, layer=["V-ROAD-EOP", "V-ROAD-SHLD"])["total"] == 12
    assert find(s, type="arc")["total"] == 5
    assert find(s, type=["arc", "line"])["total"] == 15
    assert find(s, layer="V-ROAD-EOP", type="arc")["total"] == 2


def test_visible_on_keeps_only_what_the_sheet_shows(tmp_path):
    s = project(tmp_path)
    window = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]["viewports"][0]
    box = window["visible_model_bbox"]
    inside = find(s, visible_on="C-101")
    assert 0 < inside["total"] < find(s)["total"]
    # the filter is bbox overlap, so assert that, not that the point is inside
    from roaddraft.core import geometry as geo
    from roaddraft.document.locate import resolve_entity
    for row in inside["entities"]:
        entity, owner, _ref, _space = resolve_entity(s.doc, row["id"])
        assert geo.bbox_intersects(entity.bbox(owner), tuple(box)), row["id"]
    # and something outside the window really was dropped
    dropped = {e["id"] for e in find(s)["entities"]} - {e["id"] for e in inside["entities"]}
    assert dropped
    for eid in dropped:
        entity, owner, _ref, _space = resolve_entity(s.doc, eid)
        assert not geo.bbox_intersects(entity.bbox(owner), tuple(box))
    # a sheet with no viewport says so instead of guessing
    s.execute("create_sheet", {"name": "C-999", "size": "ANSI_D"})
    r = s.query("find_entities", {"visible_on": "C-999"})
    assert not r["ok"] and "no viewport" in r["error"]["message"]


def test_find_text_by_content_and_search_a_sheet_space(tmp_path):
    s = project(tmp_path)
    s.execute("place_text", {"space": "C-101", "position": [17.0, 20.0],
                             "content": "ROADWAY PLAN", "height": 0.25})
    s.execute("place_text", {"space": "C-101", "position": [17.0, 19.0],
                             "content": "SEE DETAIL A", "height": 0.1})
    hits = find(s, space="C-101", content_contains="roadway")
    assert hits["total"] == 1 and hits["entities"][0]["content"] == "ROADWAY PLAN"
    assert find(s, space="C-101", type="text")["total"] == 2
    assert find(s, space="C-101")["space"] == "SH-001"


def test_paging_and_detail(tmp_path):
    s = project(tmp_path)
    page = find(s, limit=4)
    assert page["count"] == 4 and page["total"] == 15
    assert page["more"] == {"start": 4, "remaining": 11}
    rest = find(s, start=4, limit=100)
    assert rest["count"] == 11 and "more" not in rest
    summary = find(s, limit=1)["entities"][0]
    assert "entity" not in summary and "bbox" not in summary
    full = find(s, limit=1, detail="full")["entities"][0]
    assert full["entity"]["type"] == full["type"] and len(full["bbox"]) == 4


@pytest.mark.parametrize("twist", [0.0, 37.5])
def test_a_text_row_carries_the_corners_its_legibility_is_judged_by(tmp_path, twist):
    # Training plan decision 10 (2026-11-13): a drafter that cannot look at a plot
    # was told a text only by its box on the model's axes; each text row of what a
    # sheet shows now carries its lettering's four corners on that paper, the very
    # footprint D1-08 judges, and a sheet's own text its corners where it stands
    from roaddraft.tasks.ground_truth import GroundTruth
    from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
    from roaddraft.verify import legibility
    from roaddraft.verify.context import Context
    s = project(tmp_path)
    vp = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]["viewports"][0]["id"]
    s.execute("modify_viewport", {"sheet": "C-101", "viewport_id": vp,
                                  "changes": {"rotation_deg": twist}})
    s.execute("annotate_stationing", {"space": "model", "alignment": "DESIGN:SR-100"})
    s.execute("place_text", {"space": "C-101", "position": [17.0, 20.0],
                             "content": "ROADWAY PLAN", "height": 0.25, "rotation_deg": 12.0})
    shown = find(s, visible_on="C-101", type="text", limit=500)["entities"]
    own = find(s, space="C-101", type="text")["entities"]
    assert shown and own and all(len(row["paper_corners"]) == 4 for row in shown + own)
    assert all("paper_corners" not in row for row in find(s, type="text", limit=500)["entities"])
    truth = GroundTruth.from_dict({"task_id": "find", "design_fingerprint": "",
                                   "sheets": [{"name": "C-101"}]})
    ctx = Context.build(s.doc, truth, DRAFTING_SPEC_V1, "vague")
    judged = {it.entity_id: it.quad for sv in ctx.sheets for it in legibility.sheet_items(ctx, sv)}
    for row in shown + own:
        quad = judged[row["id"]]
        assert all(abs(a - b) <= 6e-5 for p, q in zip(quad, row["paper_corners"])
                   for a, b in zip(p, q)), row["id"]


def test_find_can_ignore_references_and_names_a_bad_space(tmp_path):
    s = project(tmp_path)
    assert find(s, include_references=False)["total"] == 0   # the host owns nothing
    r = s.query("find_entities", {"space": "C-404"})
    assert not r["ok"] and "not found" in r["error"]["message"]
    assert "valid spaces" in r["error"]["hint"]


def test_finding_the_edges_costs_a_fraction_of_dumping_the_document(tmp_path):
    """The reason this query exists: a dump does not scale to a real plan set."""
    s = project(tmp_path)
    dump = json.dumps(s.query("get_model_state", {"include_references": True}))
    answer = json.dumps(find(s, anchor={"kind": "offset", "offset": [-12, 12]}))
    assert len(answer) < len(dump) / 2


def test_point_on_entity_answers_for_reference_elements(tmp_path):
    s = project(tmp_path)
    arc = find(s, type="arc", layer="V-ROAD-EOP")["entities"][0]
    r = s.query("point_on_entity", {"id": arc["id"], "where": "mid"})
    assert r["ok"] and r["read_only"] is True and r["reference"] == "DESIGN"
    assert r["point"] == pytest.approx(arc["point"], abs=1e-3)
    assert r["direction_deg"] is not None and r["length"] > 0
    ends = [s.query("point_on_entity", {"id": arc["id"], "where": w})["point"]
            for w in ("start", "end")]
    assert ends[0] != ends[1]
    bad = s.query("point_on_entity", {"id": arc["id"], "where": "halfway"})
    assert not bad["ok"] and "start|mid|end" in bad["error"]["hint"]
    missing = s.query("point_on_entity", {"id": "DESIGN:NOPE"})
    assert not missing["ok"] and "find_entities" in missing["error"]["hint"]
