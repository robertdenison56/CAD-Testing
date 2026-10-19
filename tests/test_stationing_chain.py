"""Entity-chain stationing from a pick: the elements chained to one, a start
point on the chain, and the station known there."""
import math

from roaddraft.api.session import Session
from roaddraft.commands.handlers import chain_elements
from roaddraft.document.entities import Line, Text

from tests.test_stationing import centerline_session


def station_texts(s):
    return {t.content: t for t in s.doc.model_entities.values()
            if isinstance(t, Text)}


def straight(start=(0, 0), end=(500, 0)):
    s = Session()
    r = s.execute("draw_line", {"space": "model", "start": list(start), "end": list(end)})
    return s, r["created"][0]


def test_chain_from_any_element_finds_the_whole_centerline():
    s, ids = centerline_session()
    assert chain_elements(s.doc, [ids[1]])[0] in (ids, ids[::-1])
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": [ids[0]], "chain": True, "begin_station": 1000.0})
    assert r["ok"], r
    assert "10+00.00 to 25+18.88" in r["message"]
    assert " > ".join(ids) in r["message"]
    assert "16+00.00 BC" in station_texts(s)


def test_start_point_at_the_far_end_runs_the_stations_from_there():
    s, lid = straight()
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": [lid], "start_point": [500, 0],
        "begin_station": "10+00", "interval": 100.0})
    assert r["ok"], r
    assert "10+00.00 to 15+00.00" in r["message"]
    texts = station_texts(s)
    ticks = {round(e.start[0], 6): e for e in s.doc.model_entities.values()
             if isinstance(e, Line) and e.id != lid}
    assert sorted(ticks) == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0]
    # 10+00 sits over x = 500 and 15+00 over x = 0, both reading upright
    assert abs(texts["10+00.00"].position[0] - 500) < 1e-9
    assert abs(texts["15+00.00"].position[0] - 0) < 1e-9
    assert -90 < texts["12+00.00"].rotation_deg <= 90


def test_start_point_inside_the_path_fixes_the_station_there():
    s, lid = straight()
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": [lid], "start_point": [130, 0],
        "begin_station": 1000.0})
    assert r["ok"], r
    # nearer the start, so stations climb toward x = 500
    assert "8+70.00 to 13+70.00" in r["message"]
    assert "10+00.00 at [130.00, 0.00]" in r["message"]
    texts = station_texts(s)
    assert abs(texts["10+00.00"].position[0] - 130) < 1e-9
    assert abs(texts["9+00.00"].position[0] - 30) < 1e-9
    assert "8+00.00" not in texts and "14+00.00" not in texts


def test_reverse_turns_the_stations_round_the_start_point():
    s, lid = straight()
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": [lid], "start_point": [130, 0],
        "begin_station": 1000.0, "reverse": True})
    assert r["ok"], r
    assert "6+30.00 to 11+30.00" in r["message"]
    texts = station_texts(s)
    assert abs(texts["10+00.00"].position[0] - 130) < 1e-9
    assert abs(texts["11+00.00"].position[0] - 30) < 1e-9


def test_reverse_without_a_start_point_begins_at_the_last_element():
    s, ids = centerline_session()
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": ids, "begin_station": 0.0, "reverse": True})
    assert r["ok"], r
    # the far tangent (500 ft) comes first now
    assert "5+00.00 BC" in station_texts(s)
    assert " > ".join(ids[::-1]) in r["message"]


def test_start_point_on_the_curve_and_nearer_the_end():
    s, ids = centerline_session()
    mid = [1600 + 800 * math.cos(math.radians(-75)), 1800 + 800 * math.sin(math.radians(-75))]
    r = s.execute("annotate_stationing", {
        "space": "model", "lettering": "full", "path_ids": [ids[0]], "chain": True, "start_point": mid,
        "begin_station": 2000.0})
    assert r["ok"], r
    # mid-curve is 809.44 ft from the first tangent's start and 709.44 from the
    # far end, so the stations run from the far end: 20+00 - 709.44 = 12+90.56
    assert "12+90.56 to 28+09.44" in r["message"]
    texts = station_texts(s)
    assert "17+90.56 BC" in texts and "22+09.44 EC" in texts
    assert not r["warnings"]


def test_a_branch_stops_the_chain_unless_a_layer_or_a_pick_decides_it():
    s = Session()
    s.execute("create_layer", {"name": "CL"})
    s.execute("create_layer", {"name": "EP"})
    a = s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0],
                                "layer": "CL"})["created"][0]
    b = s.execute("draw_line", {"space": "model", "start": [100, 0], "end": [200, 0],
                                "layer": "CL"})["created"][0]
    c = s.execute("draw_line", {"space": "model", "start": [100, 0], "end": [100, 80],
                                "layer": "EP"})["created"][0]
    assert chain_elements(s.doc, [a]) == ([a, b], [])     # the centerline's layer wins
    s.execute("modify_entity", {"id": c, "changes": {"layer": "CL"}})
    ids, warnings = chain_elements(s.doc, [a])
    assert ids == [a] and "2 elements meet it" in warnings[0] and "[100.00, 0.00]" in warnings[0]
    assert chain_elements(s.doc, [a, b])[0] == [a, b]     # naming the way on
    r = s.execute("annotate_stationing", {"space": "model", "lettering": "full", "path_ids": [a], "chain": True,
                                          "begin_station": 0.0})
    assert r["ok"] and r["warnings"] and "0+00.00 to 1+00.00" in r["message"]


def test_an_element_off_the_chain_is_a_fault():
    s, ids = centerline_session()
    other = s.execute("draw_line", {"space": "model", "start": [0, 500],
                                    "end": [100, 500]})["created"][0]
    r = s.execute("annotate_stationing", {"space": "model", "lettering": "full", "path_ids": [ids[0], other],
                                          "chain": True, "begin_station": 0.0})
    assert not r["ok"] and "not on the chain" in r["error"]["message"]


def test_stationing_is_drawn_in_the_space_of_its_linework():
    # a model-space path named with a sheet as the space once drew its ticks on the
    # paper at their model coordinates, thousands of inches off the sheet (2026-10-18)
    s, lid = straight()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    before = len(s.doc.sheet_by_ref("C-101").entities)
    r = s.execute("annotate_stationing", {"space": "C-101", "path_ids": [lid], "begin_station": 0.0})
    assert not r["ok"]
    assert r["error"]["message"].startswith(f"path {lid} is in model space, not in space 'C-101'")
    assert "space='model'" in r["error"]["hint"]
    assert len(s.doc.sheet_by_ref("C-101").entities) == before
    # paper linework stations on its sheet, and is refused in model space
    pid = s.execute("draw_line", {"space": "C-101", "start": [2, 2], "end": [12, 2]})["created"][0]
    r = s.execute("annotate_stationing", {"space": "model", "path_ids": [pid], "begin_station": 0.0,
                                          "interval": 5.0, "tick_half_len": 0.1, "text_height": 0.1,
                                          "label_offset": 0.2})
    assert not r["ok"] and "is in sheet C-101, not in space 'model'" in r["error"]["message"]
    assert r["error"]["hint"] == "give space='C-101'"
    r = s.execute("annotate_stationing", {"space": "C-101", "path_ids": [pid], "begin_station": 0.0,
                                          "interval": 5.0, "tick_half_len": 0.1, "text_height": 0.1,
                                          "label_offset": 0.2})
    assert r["ok"], r
    assert all(2 <= e.start[0] <= 12 for e in s.doc.sheet_by_ref("C-101").entities.values()
               if isinstance(e, Line) and e.id != pid)


def test_a_start_point_off_the_path_is_taken_at_the_nearest_point():
    s, lid = straight()
    r = s.execute("annotate_stationing", {"space": "model", "lettering": "full", "path_ids": [lid],
                                          "start_point": [200, 12], "begin_station": 500.0})
    assert r["ok"]
    assert any("12.00 from the path" in w for w in r["warnings"])
    assert "3+00.00 to 8+00.00" in r["message"]


def test_chain_params_are_for_entity_chain_mode_only():
    s = Session()
    s.execute("create_alignment", {"name": "A", "begin_station": 0,
                                   "pis": [[0, 0], [500, 0]]})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "A",
                                          "start_point": [0, 0]})
    assert not r["ok"] and "entity-chain mode" in r["error"]["message"]


def test_begin_station_text_must_be_a_station():
    s, lid = straight()
    r = s.execute("annotate_stationing", {"space": "model", "lettering": "full", "path_ids": [lid],
                                          "begin_station": "ten"})
    assert not r["ok"] and "not a station" in r["error"]["message"]


def test_the_gui_chain_endpoint_returns_the_chain_in_order():
    from roaddraft.web.server import WebApp
    s, ids = centerline_session()
    app = WebApp(s)
    r = app.chain({"ids": [ids[2]]})
    assert r["ok"] and r["ids"] in (ids, ids[::-1]) and not r["warnings"]
    assert [row["entity"]["type"] for row in r["entities"]] in (
        ["line", "arc", "line"], ["line", "arc", "line"][::-1])
    bad = app.chain({"ids": ["LN-999"]})
    assert not bad["ok"] and "not found" in bad["error"]["message"]
    assert not app.chain({"ids": []})["ok"]
