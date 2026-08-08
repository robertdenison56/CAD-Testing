import math

from roaddraft.api.session import Session
from roaddraft.document.entities import Line, Text


def centerline_session():
    """Tangent (600') -> 30-deg curve R=800 -> tangent (500'), like the demo."""
    s = Session(project_name="sta-tests")
    s.execute("create_layer", {"name": "CL", "color": "red"})
    r1 = s.execute("draw_line", {"space": "model", "start": [1000, 1000],
                                 "end": [1600, 1000], "layer": "CL"})
    r2 = s.execute("draw_arc", {"space": "model", "center": [1600, 1800],
                                "radius": 800, "start_angle_deg": -90,
                                "end_angle_deg": -60, "layer": "CL"})
    pt = [2000.0, 1800 - 800 * math.cos(math.radians(30))]
    end = [pt[0] + 500 * math.cos(math.radians(30)),
           pt[1] + 500 * math.sin(math.radians(30))]
    r3 = s.execute("draw_line", {"space": "model", "start": pt, "end": end,
                                 "layer": "CL"})
    ids = [r1["created"][0], r2["created"][0], r3["created"][0]]
    return s, ids


def test_stationing_full_chain():
    s, ids = centerline_session()
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": ids, "begin_station": 1000.0,
        "interval": 100.0})
    assert r["ok"], r
    # length = 600 + 800*rad(30) + 500 = 1518.879...; stations 10+00..25+00
    assert "10+00.00 to 25+18.88" in r["message"]
    texts = [e for e in s.doc.model_entities.values() if isinstance(e, Text)]
    ticks = [e for e in s.doc.model_entities.values()
             if isinstance(e, Line) and e.layer == "0"]
    labels = {t.content for t in texts}
    assert "10+00.00" in labels and "25+00.00" in labels
    assert "PC 16+00.00" in labels and "PT 20+18.88" in labels
    assert len([t for t in texts if "+" in t.content and " " not in t.content]) == 16
    assert len(ticks) == 16  # ticks landed on current layer "0"


def test_stationing_tick_geometry():
    s = Session()
    r = s.execute("draw_line", {"space": "model", "start": [0, 0],
                                "end": [500, 0]})
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": r["created"], "begin_station": 0.0,
        "interval": 100.0, "tick_half_len": 10.0})
    assert r["ok"]
    ticks = [e for e in s.doc.model_entities.values()
             if isinstance(e, Line) and e.id != "LN-001"]
    assert len(ticks) == 6  # 0,100,...,500
    first = min(ticks, key=lambda t: t.start[0])
    # perpendicular to an east-west line: vertical, +/-10
    assert abs(first.start[0] - first.end[0]) < 1e-9
    assert abs(abs(first.start[1] - first.end[1]) - 20.0) < 1e-9


def test_stationing_respects_reversed_elements():
    s = Session()
    # second line drawn "backwards" (end connects to first line's end)
    r1 = s.execute("draw_line", {"space": "model", "start": [0, 0],
                                 "end": [100, 0]})
    r2 = s.execute("draw_line", {"space": "model", "start": [200, 0],
                                 "end": [100, 0]})
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": r1["created"] + r2["created"],
        "begin_station": 0.0, "interval": 100.0})
    assert r["ok"] and "0+00.00 to 2+00.00" in r["message"]


def test_stationing_polyline_path():
    s = Session()
    r = s.execute("draw_polyline", {"space": "model",
                                    "vertices": [[0, 0], [100, 0], [100, 100]]})
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": r["created"], "begin_station": 500.0,
        "interval": 50.0})
    assert r["ok"] and "5+00.00 to 7+00.00" in r["message"]


def test_stationing_disconnected_fault():
    s = Session()
    r1 = s.execute("draw_line", {"space": "model", "start": [0, 0],
                                 "end": [100, 0]})
    r2 = s.execute("draw_line", {"space": "model", "start": [500, 500],
                                 "end": [600, 500]})
    before = len(s.doc.model_entities)
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": r1["created"] + r2["created"],
        "begin_station": 0.0})
    assert not r["ok"] and "gap" in r["error"]["message"]
    assert len(s.doc.model_entities) == before  # atomic


def test_stationing_labels_stay_upright():
    s = Session()
    # line heading west: direction 180deg; labels must not be upside down
    r = s.execute("draw_line", {"space": "model", "start": [1000, 0],
                                "end": [0, 0]})
    r = s.execute("annotate_stationing", {
        "space": "model", "path_ids": r["created"], "begin_station": 0.0})
    texts = [e for e in s.doc.model_entities.values() if isinstance(e, Text)]
    assert texts
    for t in texts:
        assert -90.0 < t.rotation_deg <= 90.0


def test_stationing_one_command_in_journal_and_undo():
    s, ids = centerline_session()
    n_before = len(s.doc.model_entities)
    s.execute("annotate_stationing", {"space": "model", "path_ids": ids,
                                      "begin_station": 1000.0})
    assert len(s.doc.model_entities) > n_before
    s.execute("undo", {})
    assert len(s.doc.model_entities) == n_before
