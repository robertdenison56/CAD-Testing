"""Annotating a sheet whose design is seen through a viewport.

Plan callouts belong on the sheet, in paper inches. What they point at is in
the model -- usually a referenced basefile -- and reaches the paper through a
viewport with a centre, a scale and sometimes a twist. These tests pin the
three things that used to be missing there:

* a callout on a sheet can *name* what it points at (an entity, or a station
  and offset) and the engine carries the tip through the viewport;
* model <-> sheet is a query, so nobody re-derives the viewport by hand;
* a hand-typed tip on a sheet is checked against the design it is looking at,
  not against whatever lettering happens to sit nearby.

The numbers that matter: SR-100's first curve straddles sheets C-101 and C-102,
so the middle of the whole arc is off one of them -- "mid" has to mean the
middle of what the sheet shows.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document import viewmap
from roaddraft.document.entities import Arc, Line, Polyline, Text, entity_distance
from roaddraft.document.locate import point_at, resolve_entity
from roaddraft.document.sheets import Viewport
from roaddraft.probes import fixture, tasks

REF_ALIGN = f"DESIGN:{fixture.ALIGNMENT}"


def window(twist=0.0, fpi=50.0, center_model=(1000.0, 1000.0)) -> Viewport:
    """A 10 x 6 in window centred at [17, 11] on the paper."""
    return Viewport(id="VP-T", center_paper=[17.0, 11.0], width_in=10.0, height_in=6.0,
                    model_center=list(center_model), feet_per_inch=fpi,
                    rotation_deg=twist)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    out = tmp_path_factory.mktemp("viewmap-project")
    _model, sheets = fixture.build(out)
    return out, sheets


def fresh(project) -> Session:
    out, sheets = project
    s = Session.load(sheets, out_dir=out)
    s.execute("create_layer", {"name": "S-ANNO-CALL", "color": "black"})
    return s


def edges(s: Session, sheet: str, **extra):
    r = s.query("find_entities", {"anchor": {"kind": "offset",
                                             "offset": list(fixture.EDGE_OFFSETS)},
                                  "visible_on": sheet, **extra})
    assert r["ok"], r
    return r["entities"]


def tip_of(s: Session, r: dict, sheet: str):
    """The leader tip of a callout, and the viewport it sits in."""
    _key, container = s.doc.resolve_space(sheet)
    leader = next(container[eid] for eid in r["created"]
                  if isinstance(container[eid], Line))
    vp = viewmap.viewport_under(s.doc.sheet_by_ref(sheet), leader.start)
    return leader.start, vp


def feet_off(s: Session, eid: str, tip, vp) -> float:
    entity, owner, _ref, _space = resolve_entity(s.doc, eid)
    return entity_distance(owner, entity, vp.transform().to_model(tip))


# ------------------------------------------------------------ the geometry


def test_a_line_is_cut_to_the_window_exactly():
    """The window shows model x 750..1250 at 1"=50'; the line runs 0..2000."""
    vp = window()
    line = Line(id="LN-1", start=[0.0, 1000.0], end=[2000.0, 1000.0])
    assert viewmap.visible_spans(None, line, vp) == [pytest.approx((0.375, 0.625))]
    point, direction, shown = viewmap.point_at_visible(None, line, "mid", vp)
    assert point == pytest.approx([1000.0, 1000.0]) and shown == pytest.approx(0.25)
    assert viewmap.point_at_visible(None, line, "start", vp)[0] == pytest.approx([750.0, 1000.0])
    assert viewmap.point_at_visible(None, line, "end", vp)[0] == pytest.approx([1250.0, 1000.0])
    # a line the window never sees
    far = Line(id="LN-2", start=[0.0, 5000.0], end=[2000.0, 5000.0])
    assert viewmap.visible_spans(None, far, vp) == []
    assert viewmap.point_at_visible(None, far, "mid", vp) is None


def test_mid_of_the_visible_part_is_not_mid_of_the_entity():
    vp = window()
    line = Line(id="LN-1", start=[1200.0, 1000.0], end=[5200.0, 1000.0])
    whole = point_at(None, line, "mid")[0]
    assert not viewmap.shows(vp, whole)                      # x=3200, far off the sheet
    seen = viewmap.point_at_visible(None, line, "mid", vp)[0]
    assert viewmap.shows(vp, seen) and seen == pytest.approx([1225.0, 1000.0])


def test_a_twisted_window_is_not_its_bounding_box():
    """Turned 30 degrees, the window's model bounding box has empty corners.
    A short line sitting in one is inside the box and outside the window."""
    vp = window(twist=30.0)
    box = vp.transform().visible_model_bbox(vp.width_in, vp.height_in)
    corner = [box[0] + 5.0, box[1] + 5.0]
    line = Line(id="LN-1", start=corner, end=[corner[0] + 10.0, corner[1]])
    assert box[0] <= corner[0] <= box[2] and box[1] <= corner[1] <= box[3]
    assert not viewmap.is_visible(None, line, vp)
    through = Line(id="LN-2", start=[box[0], 1000.0], end=[box[2], 1000.0])
    (t0, t1), = viewmap.visible_spans(None, through, vp)
    for t in (t0, t1):                       # each end of the span is on the window's edge
        q = vp.transform().to_paper(point_at(None, through, t)[0])
        x0, y0, x1, y1 = vp.paper_bbox()
        on_edge = min(abs(q[0] - x0), abs(q[0] - x1), abs(q[1] - y0), abs(q[1] - y1))
        assert on_edge < 1e-9


def test_an_arc_is_cut_where_it_crosses_the_window():
    vp = window()
    arc = Arc(id="AR-1", center=[1000.0, 400.0], radius=600.0,
              start_angle_deg=30.0, end_angle_deg=150.0)
    (t0, t1), = viewmap.visible_spans(None, arc, vp)
    assert 0.0 < t0 < 0.5 < t1 < 1.0 and t0 + t1 == pytest.approx(1.0, abs=1e-9)
    for t in (t0, t1):
        q = vp.transform().to_paper(point_at(None, arc, t)[0])
        assert min(abs(q[0] - 12.0), abs(q[0] - 22.0)) < 1e-9   # the window's sides
    point, _direction, _shown = viewmap.point_at_visible(None, arc, "mid", vp)
    assert point == pytest.approx([1000.0, 1000.0], abs=1e-6)     # top of the arc
    assert entity_distance(None, arc, point) < 1e-9


def test_a_polyline_that_leaves_and_comes_back_has_two_visible_runs():
    vp = window()                                             # x 750..1250, y 850..1150
    pl = Polyline(id="PL-1", vertices=[[700.0, 1000.0], [900.0, 1000.0], [900.0, 1400.0],
                                       [1100.0, 1400.0], [1100.0, 1000.0], [1300.0, 1000.0]],
                  closed=False)
    spans = viewmap.visible_spans(None, pl, vp)
    assert len(spans) == 2
    # 'mid' of two equal runs falls at the end of the first / start of the second:
    # either way it is a point the window shows
    for where in ("start", 0.25, "mid", 0.75, "end"):
        point = viewmap.point_at_visible(None, pl, where, vp)[0]
        assert viewmap.shows(vp, point), where


def test_text_has_no_part_to_take_only_a_place():
    vp = window()
    inside = Text(id="TX-1", position=[1000.0, 1000.0], content="A", height=5.0)
    outside = Text(id="TX-2", position=[3000.0, 1000.0], content="B", height=5.0)
    assert viewmap.visible_spans(None, inside, vp) is None
    assert viewmap.is_visible(None, inside, vp) and not viewmap.is_visible(None, outside, vp)


# ------------------------------------------------ model <-> sheet, as queries


def test_model_to_sheet_and_back_through_a_twisted_viewport(tmp_path):
    s = Session(project_name="twist", out_dir=tmp_path)
    s.execute("create_sheet", {"name": "L-2", "size": "ANSI_D"})
    s.execute("create_viewport", {"sheet": "L-2", "center_paper": [17.0, 11.0],
                                  "width_in": 30.0, "height_in": 18.0,
                                  "model_center": [5000.0, 2000.0], "feet_per_inch": 40.0,
                                  "rotation_deg": -6.457})
    model = [5321.5, 1877.25]
    r = s.query("model_to_sheet", {"sheet": "L-2", "point": model})
    assert r["ok"] and r["visible"] and r["viewport"] == "VP-001"
    # the published formula, worked by hand
    a = math.radians(-6.457)
    dx, dy = (model[0] - 5000.0) / 40.0, (model[1] - 2000.0) / 40.0
    by_hand = [17.0 + dx * math.cos(a) - dy * math.sin(a),
               11.0 + dx * math.sin(a) + dy * math.cos(a)]
    assert r["sheet_point"] == pytest.approx(by_hand, abs=1e-6)
    back = s.query("sheet_to_model", {"sheet": "L-2", "point": r["sheet_point"]})
    assert back["ok"] and back["inside"]
    assert back["point"] == pytest.approx(model, abs=1e-3)


def test_a_point_no_viewport_shows_is_answered_not_refused(project):
    s = fresh(project)
    r = s.query("model_to_sheet", {"sheet": "C-101", "point": [3500.0, 1300.0]})
    assert r["ok"] and r["visible"] is False and "no viewport of C-101" in r["note"]
    assert r["sheet_point"][0] > 34.0                          # off the right of the paper
    r = s.query("sheet_to_model", {"sheet": "C-101", "point": [0.2, 0.2]})
    assert r["ok"] and r["inside"] is False and "nearest" not in r
    r = s.query("model_to_sheet", {"sheet": "C-101", "point": [0, 0], "viewport": "VP-9"})
    assert not r["ok"] and "VP-9 is not on C-101" in r["error"]["message"]


def test_sheet_to_model_says_what_the_paper_is_looking_at(project):
    s = fresh(project)
    row = edges(s, "C-102")[0]
    r = s.query("sheet_to_model", {"sheet": "C-102", "point": row["sheet_point"]})
    assert r["ok"] and r["nearest"]["id"] == row["id"]
    assert r["nearest"]["distance_ft"] < 0.01


def test_a_sheet_with_no_viewport_teaches(tmp_path):
    s = Session(project_name="bare", out_dir=tmp_path)
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    for name in ("model_to_sheet", "sheet_to_model"):
        r = s.query(name, {"sheet": "C-101", "point": [1.0, 1.0]})
        assert not r["ok"] and "no viewport" in r["error"]["message"]
        assert "create_viewport" in r["error"]["hint"]


def test_station_and_entity_queries_can_answer_on_a_sheet(project):
    s = fresh(project)
    r = s.query("station_to_xy", {"alignment": REF_ALIGN, "station": "18+00",
                                  "offset": 12, "sheet": "C-101"})
    assert r["ok"] and r["on_sheet"]["visible"] and r["on_sheet"]["viewport"] == "VP-001"
    direct = s.query("model_to_sheet", {"sheet": "C-101", "point": r["point"]})
    assert r["on_sheet"]["sheet_point"] == pytest.approx(direct["sheet_point"])
    r = s.query("resolve_anchor", {"alignment": REF_ALIGN, "anchor": "PC-1",
                                   "sheet": "C-102"})
    assert r["ok"] and r["on_sheet"]["visible"] is False       # the PC is on C-101
    assert s.query("resolve_anchor", {"alignment": REF_ALIGN, "anchor": "PC-1",
                                      "sheet": "C-101"})["on_sheet"]["visible"]

    row = next(e for e in edges(s, "C-102") if e["type"] == "arc")
    r = s.query("point_on_entity", {"id": row["id"], "sheet": "C-102"})
    assert r["ok"] and r["on_sheet"]["sheet_point"] == pytest.approx(row["sheet_point"])
    assert r["on_sheet"]["shown"] < 1.0
    whole = s.query("point_on_entity", {"id": row["id"]})
    assert whole["point"] != pytest.approx(r["point"])          # mid of what is shown
    r = s.query("point_on_entity", {"id": row["id"], "sheet": "C-103"})
    assert not r["ok"] and "not visible on C-103" in r["error"]["message"]


def test_visible_on_means_shown_and_says_where_on_the_paper(project):
    s = fresh(project)
    sheet = s.doc.sheet_by_ref("C-102")
    for row in edges(s, "C-102"):
        vp = sheet.viewport_by_id(row["viewport"])
        assert viewmap.in_window(vp, row["sheet_point"])
        assert feet_off(s, row["id"], row["sheet_point"], vp) < 0.01
    r = s.query("find_entities", {"space": "C-102", "visible_on": "C-102"})
    assert not r["ok"] and "visible_on filters model entities" in r["error"]["message"]


# ---------------------------------------------- callouts on the sheet itself


def test_a_sheet_callout_names_a_referenced_entity_and_lands_on_it(project):
    s = fresh(project)
    row = next(e for e in edges(s, "C-102") if e["type"] == "arc")
    x, y = row["sheet_point"]
    r = s.execute("place_callout", {"space": "C-102", "target_entity": row["id"],
                                    "position": [x + 2.5, y - 2.0],
                                    "content": "EDGE OF PAVEMENT",
                                    "layer": "S-ANNO-CALL"})
    assert r["ok"] and r["warnings"] == []
    assert f"pointing at {row['id']}" in r["message"] and "through VP-002" in r["message"]
    assert "of it C-102 shows" in r["message"]                 # the arc runs off the sheet
    tip, vp = tip_of(s, r, "C-102")
    assert tip == pytest.approx(row["sheet_point"], abs=1e-4)
    assert feet_off(s, row["id"], tip, vp) < 1e-6
    # it is sheet annotation: on the sheet, in inches, owning nothing in the model
    sheet = s.doc.sheet_by_ref("C-102")
    assert all(eid in sheet.entities for eid in r["created"])
    assert not s.doc.model_entities
    text = next(sheet.entities[eid] for eid in r["created"]
                if isinstance(sheet.entities[eid], Text))
    assert text.height == pytest.approx(0.10) and text.anchor is None


def test_the_same_curve_is_called_out_on_both_sheets_it_straddles(project):
    s = fresh(project)
    arc = next(e["id"] for e in edges(s, "C-102") if e["type"] == "arc")
    assert arc in [e["id"] for e in edges(s, "C-101")]
    tips = {}
    for sheet in ("C-101", "C-102"):
        r = s.execute("place_callout", {"space": sheet, "target_entity": arc,
                                        "position": [17.0, 4.0], "content": "EP",
                                        "layer": "S-ANNO-CALL"})
        assert r["ok"], r
        tip, vp = tip_of(s, r, sheet)
        assert vp is not None and feet_off(s, arc, tip, vp) < 1e-6
        tips[sheet] = vp.transform().to_model(tip)
    assert math.dist(tips["C-101"], tips["C-102"]) > 100.0    # two different stretches


def test_at_runs_along_what_the_sheet_shows(project):
    s = fresh(project)
    arc = next(e["id"] for e in edges(s, "C-102") if e["type"] == "arc")
    xs = []
    for where in ("start", 0.5, "end"):
        r = s.execute("place_callout", {"space": "C-102", "target_entity": arc,
                                        "at": where, "position": [17.0, 4.0],
                                        "content": "EP", "layer": "S-ANNO-CALL"})
        tip, vp = tip_of(s, r, "C-102")
        assert feet_off(s, arc, tip, vp) < 1e-6
        xs.append(tip[0])
    assert xs[0] == pytest.approx(vp.paper_bbox()[0], abs=1e-6)  # start = the window's edge
    assert xs[0] < xs[1] < xs[2]


def test_what_a_sheet_does_not_show_cannot_be_called_out_there(project):
    s = fresh(project)
    shown_on_3 = edges(s, "C-103")
    only_3 = next(e["id"] for e in shown_on_3
                  if e["id"] not in [x["id"] for x in edges(s, "C-101")])
    r = s.execute("place_callout", {"space": "C-101", "target_entity": only_3,
                                    "position": [17.0, 4.0], "content": "EP",
                                    "layer": "S-ANNO-CALL"})
    assert not r["ok"]
    assert f"{only_3} is not visible through any viewport of C-101" in r["error"]["message"]
    assert "it is on" in r["error"]["hint"] and "C-103" in r["error"]["hint"]
    assert "visible_on='C-101'" in r["error"]["hint"]
    assert not s.doc.sheet_by_ref("C-101").entities              # atomic: nothing drawn


def test_a_station_and_offset_is_a_target_too(project):
    """How most plan callouts are aimed. There is no entity at a station."""
    s = fresh(project)
    r = s.execute("place_callout", {"space": "C-101", "alignment": REF_ALIGN,
                                    "target_anchor": "18+00@12R",
                                    "position": [20.0, 6.0],
                                    "content": "STA 18+00, 12' RT\nBEGIN GUARDRAIL",
                                    "layer": "S-ANNO-CALL"})
    assert r["ok"] and r["warnings"] == []
    assert "pointing at DESIGN:SR-100 18+00.00, 12.00' RT through VP-001" in r["message"]
    tip, vp = tip_of(s, r, "C-101")
    want = s.query("station_to_xy", {"alignment": REF_ALIGN, "station": "18+00",
                                     "offset": 12})["point"]
    assert vp.transform().to_model(tip) == pytest.approx(want, abs=1e-6)
    # reading a referenced design is not owning it: nothing is anchored
    sheet = s.doc.sheet_by_ref("C-101")
    assert all(sheet.entities[eid].anchor is None for eid in r["created"])
    # the dict form and a named point work the same way
    r = s.execute("place_callout", {"space": "C-101", "alignment": REF_ALIGN,
                                    "target_anchor": {"station": 1800, "offset": -12},
                                    "position": [20.0, 16.0], "content": "EP",
                                    "layer": "S-ANNO-CALL"})
    assert r["ok"] and "12.00' LT" in r["message"]
    r = s.execute("place_callout", {"space": "C-101", "alignment": REF_ALIGN,
                                    "target_anchor": "PC-1", "position": [26.0, 6.0],
                                    "content": "PC", "layer": "S-ANNO-CALL"})
    assert r["ok"] and "PC-1 at 24+05.27" in r["message"]


def test_a_station_the_sheet_does_not_show_names_the_sheet_that_does(project):
    s = fresh(project)
    r = s.execute("place_callout", {"space": "C-102", "alignment": REF_ALIGN,
                                    "target_anchor": "PC-1", "position": [8.0, 16.0],
                                    "content": "PC", "layer": "S-ANNO-CALL"})
    assert not r["ok"] and "is not visible through any viewport of C-102" in r["error"]["message"]
    assert "it is on C-101" in r["error"]["hint"]


def test_target_anchor_faults_teach(project):
    s = fresh(project)
    base = {"space": "C-101", "position": [20.0, 6.0], "content": "A",
            "layer": "S-ANNO-CALL"}
    r = s.execute("place_callout", {**base, "target_anchor": "18+00"})
    assert not r["ok"] and "DESIGN:SR-100" in r["error"]["hint"]   # owns none; says whose
    r = s.execute("place_callout", {**base, "target_anchor": "18+00",
                                    "alignment": "DESIGN:SR-999"})
    assert not r["ok"] and "DESIGN:SR-100" in r["error"]["hint"]
    r = s.execute("place_callout", {**base, "target_anchor": "PC-9",
                                    "alignment": REF_ALIGN})
    assert not r["ok"]
    r = s.execute("place_callout", {**base, "target_anchor": "18+00", "target": [1, 1],
                                    "alignment": REF_ALIGN})
    assert not r["ok"] and "exactly one" in r["error"]["message"]
    r = s.execute("place_callout", {**base, "target": [17.0, 11.0], "at": "mid"})
    assert not r["ok"] and "at goes with target_entity" in r["error"]["message"]
    r = s.execute("place_callout", {**base, "target": [17.0, 11.0], "viewport": "VP-001"})
    assert not r["ok"] and "viewport goes with" in r["error"]["message"]
    r = s.execute("place_callout", {**base, "target_anchor": "18+00",
                                    "alignment": REF_ALIGN, "viewport": "VP-7"})
    assert not r["ok"] and "VP-7 is not on C-101" in r["error"]["message"]


def test_target_anchor_in_model_space_on_the_documents_own_alignment(tmp_path):
    s = Session(project_name="own", out_dir=tmp_path)
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": fixture.PIS})
    r = s.execute("place_callout", {"space": "model", "target_anchor": "14+00@20L",
                                    "position": [1500.0, 1300.0], "content": "R/W"})
    assert r["ok"] and r["warnings"] == [] and "SR-100 14+00.00, 20.00' LT" in r["message"]
    leader = next(s.doc.model_entities[eid] for eid in r["created"]
                  if isinstance(s.doc.model_entities[eid], Line))
    want = s.query("station_to_xy", {"station": "14+00", "offset": -20})["point"]
    assert leader.start == pytest.approx(want)


def test_only_a_sheet_sees_the_model(tmp_path):
    """Model -> sheet and sheet -> sheet are still faults, and say why."""
    s = Session(project_name="spaces", out_dir=tmp_path)
    for name in ("C-101", "C-102"):
        s.execute("create_sheet", {"name": name, "size": "ANSI_D"})
    on_sheet = s.execute("draw_line", {"space": "C-101", "start": [1, 1], "end": [2, 2]})
    for space in ("model", "C-102"):
        r = s.execute("place_callout", {"space": space, "position": [5, 5], "content": "A",
                                        "target_entity": on_sheet["created"][0]})
        assert not r["ok"] and "but the callout goes in" in r["error"]["message"]
        assert "through its viewports" in r["error"]["hint"]


def test_a_sheet_callout_journal_replays(tmp_path):
    s = Session(project_name="replay", out_dir=tmp_path)
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": fixture.PIS})
    s.execute("draw_offset", {"offsets": [-12, 12]})
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17.0, 11.7],
                                  "width_in": 31.0, "height_in": 18.5,
                                  "model_center": [1775.0, 1250.0], "feet_per_inch": 50.0,
                                  "rotation_deg": 12.5})
    edge = s.query("find_entities", {"anchor": {"kind": "offset"},
                                     "visible_on": "C-101"})["entities"][0]
    assert s.execute("place_callout", {"space": "C-101", "target_entity": edge["id"],
                                       "position": [20.0, 5.0], "content": "EP"})["ok"]
    assert s.execute("place_callout", {"space": "C-101", "target_anchor": "14+00@12R",
                                       "position": [9.0, 5.0], "content": "STA"})["ok"]
    path = tmp_path / "sheet-callout.journal.jsonl"
    assert s.query("save_journal", {"path": str(path)})["ok"]
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()


# ------------------------------------------- the net under a hand-typed tip


def test_a_hand_typed_tip_on_a_sheet_is_checked_against_the_design(project):
    """It used to search the sheet's own entities only, so it named whatever
    lettering sat nearby -- on every correct callout -- and never the line."""
    s = fresh(project)
    row = next(e for e in edges(s, "C-102") if e["type"] == "line")
    tip = row["sheet_point"]
    # lettering right on top of the spot, the way a real sheet has it
    s.execute("place_text", {"space": "C-102", "position": tip, "content": "30+00",
                             "height": 0.12, "layer": "S-ANNO-CALL"})
    r = s.execute("place_callout", {"space": "C-102", "target": tip,
                                    "position": [tip[0] + 3.0, tip[1] - 2.0],
                                    "content": "EP", "layer": "S-ANNO-CALL"})
    assert r["ok"]
    aim = r["warnings"][0]
    assert f"lands on {row['id']}" in aim and "seen through VP-002" in aim
    assert "of SR-100" in aim and "TX-" not in aim


def test_the_wrong_parallel_line_is_named_on_a_sheet_too(project):
    s = fresh(project)
    shoulder = s.query("find_entities", {"anchor": {"kind": "offset", "offset": -20.0},
                                         "type": "line", "visible_on": "C-102"})["entities"][0]
    r = s.execute("place_callout", {"space": "C-102", "target": shoulder["sheet_point"],
                                    "position": [17.0, 4.0], "content": "EDGE OF PAVEMENT",
                                    "layer": "S-ANNO-CALL"})
    assert r["ok"] and "20.00' LT of SR-100" in r["warnings"][0]   # not the 12 ft edge


def test_a_tip_in_empty_model_space_says_how_far_in_feet(project):
    s = fresh(project)
    edge = next(e for e in edges(s, "C-102") if e["type"] == "line")
    vp = s.doc.sheet_by_ref("C-102").viewport_by_id(edge["viewport"])
    model = vp.transform().to_model(edge["sheet_point"])
    off = vp.transform().to_paper([model[0], model[1] + 400.0])   # 400 ft from the road
    r = s.execute("place_callout", {"space": "C-102", "target": off,
                                    "position": [off[0] + 3.0, off[1] + 1.0],
                                    "content": "EP", "layer": "S-ANNO-CALL"})
    assert r["ok"]
    aim = r["warnings"][0]
    assert "points at empty space" in aim and "through VP-002" in aim
    assert "ft away" in aim and "DESIGN:" in aim and "target_anchor" in aim


def test_a_tip_outside_every_viewport_still_checks_the_sheet(project):
    s = fresh(project)
    drawn = s.execute("draw_line", {"space": "C-102", "start": [0.6, 0.6], "end": [1.2, 0.6],
                                    "layer": "S-ANNO-CALL"})
    r = s.execute("place_callout", {"space": "C-102", "target": [0.9, 0.6],
                                    "position": [0.9, 1.6], "content": "A",
                                    "layer": "S-ANNO-CALL"})
    assert r["ok"] and f"lands on {drawn['created'][0]}" in r["warnings"][0]
    assert "seen through" not in r["warnings"][0]


# ------------------------------------------------------ scoring paper space


def test_paper_space_work_is_scored_through_the_viewport(project):
    base = fresh(project)
    probe = tasks.get("edge-c102-paper")
    # built by hand on the sheet, from nothing but a line and some text
    s = fresh(project)
    row = edges(s, "C-102")[0]
    x, y = row["sheet_point"]
    s.execute("draw_line", {"space": "C-102", "start": [x, y], "end": [x + 2.0, y - 2.0],
                            "layer": "S-ANNO-CALL"})
    s.execute("place_text", {"space": "C-102", "position": [x + 2.1, y - 2.0],
                             "content": "EP", "height": 0.1, "layer": "S-ANNO-CALL"})
    assert probe.check(base, s).passed

    # the same callout 0.3 in off -- the curve trap, at paper size -- fails
    s = fresh(project)
    s.execute("draw_line", {"space": "C-102", "start": [x, y + 0.3],
                            "end": [x + 2.0, y - 2.0], "layer": "S-ANNO-CALL"})
    s.execute("place_text", {"space": "C-102", "position": [x + 2.1, y - 2.0],
                             "content": "EP", "height": 0.1, "layer": "S-ANNO-CALL"})
    result = probe.check(base, s)
    assert not result.passed and "nearest miss" in result.detail


def test_a_paper_probe_is_not_satisfied_by_work_in_the_model(project):
    base = fresh(project)
    s = fresh(project)
    tasks.get("edge-c102").solve(s)                           # a good callout, in the model
    assert tasks.get("edge-c102").check(base, s).passed
    result = tasks.get("edge-c102-paper").check(base, s)
    assert not result.passed and "paper space" in result.detail


def test_model_space_probes_accept_paper_space_work(project):
    """Aim is aim: the older probes do not care which space the callout is in."""
    base = fresh(project)
    s = fresh(project)
    tasks.get("edge-c102-paper").solve(s)
    assert tasks.get("edge-c102").check(base, s).passed
