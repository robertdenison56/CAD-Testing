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


@pytest.mark.parametrize("twist", [0.0, 37.5, -140.0])
def test_a_dimension_row_carries_the_corners_of_its_text(tmp_path, twist):
    # Training plan decisions 9 and 10 (2026-11-13): a dimension's number is lettering
    # the verifier judges like any text (D1-08), through the viewport that shows it; a
    # dimension row carries that text's corners on the paper as a text row does
    from roaddraft.tasks.ground_truth import GroundTruth
    from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
    from roaddraft.verify import legibility
    from roaddraft.verify.context import Context
    s = project(tmp_path)
    vp = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]["viewports"][0]["id"]
    s.execute("modify_viewport", {"sheet": "C-101", "viewport_id": vp,
                                  "changes": {"rotation_deg": twist}})
    edges = find(s, anchor={"kind": "offset"})["entities"]
    assert len(edges) >= 2
    r = s.execute("place_dimension", {"space": "model", "kind": "aligned",
                                      "from_entity": edges[0]["id"], "from_at": 0.1,
                                      "to_entity": edges[1]["id"], "to_at": 0.1,
                                      "line_point": edges[0]["point"], "text_height": 5.0,
                                      "view_rotation": twist})
    assert r["ok"], r
    r = s.execute("place_dimension", {"space": "C-101", "kind": "aligned", "p1": [3, 20],
                                      "p2": [9, 20], "line_point": [6, 20.5]})
    assert r["ok"], r
    shown = find(s, visible_on="C-101", type="dimension")["entities"]
    own = find(s, space="C-101", type="dimension")["entities"]
    assert len(shown) == 1 and len(own) == 1
    assert all(len(row["paper_corners"]) == 4 for row in shown + own)
    assert all("paper_corners" not in row for row in find(s, type="dimension")["entities"])
    truth = GroundTruth.from_dict({"task_id": "find", "design_fingerprint": "",
                                   "sheets": [{"name": "C-101"}]})
    ctx = Context.build(s.doc, truth, DRAFTING_SPEC_V1, "vague")
    judged = {it.entity_id: it.quad for sv in ctx.sheets for it in legibility.sheet_items(ctx, sv)}
    for row in shown + own:
        quad = judged[row["id"]]
        assert all(abs(a - b) <= 6e-5 for p, q in zip(quad, row["paper_corners"])
                   for a, b in zip(p, q)), row["id"]
    # the model dimension's text reads upright on the sheet: its lower edge runs within a
    # quarter turn of level, left to right
    (x0, y0), (x1, y1) = shown[0]["paper_corners"][:2]
    assert x1 - x0 > 0.0 or abs(x1 - x0) < 1e-6
    # a dimension with its text hidden has no lettering to give corners for
    r = s.execute("place_dimension", {"space": "C-101", "kind": "aligned", "p1": [3, 18],
                                      "p2": [9, 18], "line_point": [6, 18.5], "text": ""})
    assert r["ok"], r
    rows = {row["id"]: row for row in find(s, space="C-101", type="dimension")["entities"]}
    assert "paper_corners" not in rows[r["created"][0]]


def test_a_dimension_is_listed_where_a_sheet_shows_its_text_though_not_its_line(tmp_path):
    # the number of a dimension too short for it stands outside, a text length past the
    # line it measures along: a frame can show (or cut) the number where it does not show
    # the middle of the dimension, and the listing of what that sheet shows says so
    s = project(tmp_path)
    r = s.execute("place_dimension", {"space": "model", "kind": "aligned", "p1": [1100, 988],
                                      "p2": [1100, 1012], "line_point": [1100, 1000],
                                      "text_height": 8.0})
    assert r["ok"] and any("too short for its text" in w for w in r["warnings"]), r
    dim = s.doc.model_entities[r["created"][0]]
    text = [e for e in dim.primitives(s.doc) if e.TYPE == "text"][0]
    mid = [(dim.p1[0] + dim.p2[0]) / 2.0, (dim.p1[1] + dim.p2[1]) / 2.0]
    away = [text.position[0] - mid[0], text.position[1] - mid[1]]
    assert (away[0] ** 2 + away[1] ** 2) ** 0.5 > 20.0  # the number stands well off the line
    vp = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]["viewports"][0]
    # a small window centred well past the number, away from the line: it shows the
    # number's point and not the middle of the dimension
    centre = [text.position[0] + 1.5 * away[0], text.position[1] + 1.5 * away[1]]
    reach = 2.0 * (away[0] ** 2 + away[1] ** 2) ** 0.5 / vp["feet_per_inch"]
    r = s.execute("modify_viewport", {"sheet": "C-101", "viewport_id": vp["id"], "changes": {
        "model_center": centre, "width_in": 2.0 * reach * 0.9, "height_in": 2.0 * reach * 0.9}})
    assert r["ok"], r
    from roaddraft.document import viewmap
    view = s.doc.sheets["SH-001"].viewports[0]
    assert viewmap.shows(view, text.position) and not viewmap.shows(view, mid)
    rows = find(s, visible_on="C-101", type="dimension")["entities"]
    assert [row["id"] for row in rows] == [dim.id]
    assert rows[0]["viewport"] == view.id and len(rows[0]["paper_corners"]) == 4
    assert "sheet_point" not in rows[0]  # the line itself does not show


def test_a_dimension_row_gives_its_corners_through_the_viewport_it_names(tmp_path):
    # two viewports on one sheet, one showing the middle of the dimension and the other
    # its number: the row is one viewport's reading, not a mix of the two
    from roaddraft.api.session import _paper_corners
    from roaddraft.document import viewmap
    from roaddraft.document.locate import point_at
    s = project(tmp_path)
    r = s.execute("place_dimension", {"space": "model", "kind": "aligned", "p1": [1100, 988],
                                      "p2": [1100, 1012], "line_point": [1100, 1000],
                                      "text_height": 8.0})
    assert r["ok"], r
    dim = s.doc.model_entities[r["created"][0]]
    text = [e for e in dim.primitives(s.doc) if e.TYPE == "text"][0]
    middle = point_at(s.doc, dim, "mid")[0]
    apart = ((middle[0] - text.position[0]) ** 2 + (middle[1] - text.position[1]) ** 2) ** 0.5
    assert apart > 10.0
    side = round(apart / 50.0, 3)  # a window too small to show both, at 50 ft to the inch
    first = s.query("get_sheet_state", {"sheet": "C-101"})["sheet"]["viewports"][0]
    assert s.execute("modify_viewport", {"sheet": "C-101", "viewport_id": first["id"], "changes": {
        "center_paper": [8.0, 8.0], "width_in": side, "height_in": side,
        "model_center": list(middle)}})["ok"]
    r = s.execute("create_viewport", {"sheet": "C-101", "center_paper": [20.0, 8.0],
                                      "width_in": side, "height_in": side,
                                      "model_center": list(text.position), "feet_per_inch": 50.0})
    assert r["ok"], r
    sheet = s.doc.sheets["SH-001"]
    one, two = sheet.viewports
    assert viewmap.shows(one, middle) and not viewmap.shows(one, text.position)
    assert viewmap.shows(two, text.position) and not viewmap.shows(two, middle)
    row = find(s, visible_on="C-101", type="dimension")["entities"][0]
    assert row["viewport"] == one.id
    assert row["sheet_point"] == pytest.approx([8.0, 8.0], abs=1e-3)
    assert row["paper_corners"] == _paper_corners(s.doc, text, one)
    assert all(abs(x - 8.0) < 6.0 for x, _y in row["paper_corners"])  # not over by x 20


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
