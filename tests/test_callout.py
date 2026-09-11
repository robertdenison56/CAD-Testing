"""place_callout: text with a leader, for geometry that has no design model.

A pavement edge seen through a reference is read-only and belongs to another
document, so it cannot be labelled with place_label. A callout is what a
drafter actually places: an arrowhead on the thing, a leader, a shoulder, and
text sitting clear of the linework.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Line, Polyline, Text

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
TARGET = [1300.0, 988.0]          # a point on the +12 ft (right) pavement edge


def model_session(tmp_path=None) -> Session:
    s = Session(project_name="callout-tests", out_dir=tmp_path)
    s.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    return s


def parts(s: Session, r: dict, space="model"):
    _key, container = s.doc.resolve_space(space)
    return [container[eid] for eid in r["created"]]


def test_callout_draws_arrowhead_leader_shoulder_and_text():
    s = model_session()
    r = s.execute("place_callout", {"space": "model", "target": TARGET,
                                    "position": [1450.0, 900.0], "content": "EP 12' RT",
                                    "layer": "V-ANNO-TEXT"})
    assert r["ok"], r
    assert r["message"] == "callout TX-001 (\"EP 12' RT\") placed in model space"
    leader, shoulder, head, text = parts(s, r)
    assert isinstance(leader, Line) and isinstance(shoulder, Line)
    assert isinstance(head, Polyline) and isinstance(text, Text)
    assert all(e.layer == "V-ANNO-TEXT" for e in (leader, shoulder, head, text))
    # default landing is 2.5 x the 8 ft text height
    assert shoulder.start == pytest.approx([1430.0, 900.0], abs=1e-9)
    assert shoulder.end == pytest.approx([1450.0, 900.0], abs=1e-9)
    assert leader.start == pytest.approx(TARGET, abs=1e-9)
    assert leader.end == pytest.approx(shoulder.start, abs=1e-9)
    assert text.position == pytest.approx([1450.0, 900.0], abs=1e-9)
    assert text.content == "EP 12' RT" and text.height == 8.0
    # the arrowhead is a closed triangle with its tip on the target
    assert head.closed is True and len(head.vertices) == 3
    assert head.vertices[0] == pytest.approx(TARGET, abs=1e-9)
    assert math.dist(head.vertices[1], head.vertices[2]) == pytest.approx(2 * 8.0 * 0.18,
                                                                         abs=1e-9)


def test_text_sits_away_from_the_target_on_either_side():
    s = model_session()
    right = s.execute("place_callout", {"space": "model", "target": TARGET,
                                        "position": [1450.0, 900.0], "content": "A"})
    _leader, shoulder, _head, text = parts(s, right)
    assert text.halign == "left"                  # reads away from the leader
    assert shoulder.start[0] < text.position[0]   # shoulder comes from the target side
    left = s.execute("place_callout", {"space": "model", "target": TARGET,
                                       "position": [1200.0, 900.0], "content": "B"})
    _leader, shoulder, _head, text = parts(s, left)
    assert text.halign == "right"
    assert shoulder.start[0] > text.position[0]


def test_landing_zero_and_arrow_false_drop_those_pieces():
    s = model_session()
    r = s.execute("place_callout", {"space": "model", "target": TARGET,
                                    "position": [1450.0, 900.0], "content": "A",
                                    "landing": 0, "arrow": False})
    entities = parts(s, r)
    assert [e.TYPE for e in entities] == ["line", "text"]
    assert entities[0].end == pytest.approx([1450.0, 900.0], abs=1e-9)


def test_sheet_callout_defaults_to_a_tenth_inch_of_text():
    s = model_session()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r = s.execute("place_callout", {"space": "C-101", "target": [10.0, 12.0],
                                    "position": [14.0, 16.0], "content": "SEE DETAIL A"})
    assert r["ok"], r
    text = parts(s, r, "C-101")[-1]
    assert text.height == 0.10
    assert text.annotative is None                # paper text is not annotative


def test_model_callout_follows_the_annotation_scale():
    s = model_session()
    assert s.execute("set_annotation_scale", {"scale": 50})["ok"]
    r = s.execute("place_callout", {"space": "model", "target": TARGET,
                                    "position": [1450.0, 900.0], "content": "EP"})
    text = parts(s, r)[-1]
    assert text.height == pytest.approx(5.0)      # 0.10 in x 50 ft/in
    assert text.annotative == {"scale": 50.0, "height_in": 0.10}
    # and the shoulder follows the text height it was drawn at
    assert parts(s, r)[1].start[0] == pytest.approx(1450.0 - 2.5 * 5.0, abs=1e-9)


def test_callout_faults_on_a_negative_landing():
    s = model_session()
    r = s.execute("place_callout", {"space": "model", "target": TARGET,
                                    "position": [1450.0, 900.0], "content": "A",
                                    "landing": -5})
    assert not r["ok"] and "landing" in r["error"]["message"]
    assert s.doc.model_entities == {}


def test_calling_out_a_pavement_edge_seen_through_a_reference(tmp_path):
    """T2 end to end: find the edge in the reference, read what it is, call it out."""
    model = Session(project_name="SR-100 model", out_dir=tmp_path)
    model.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                       "pis": A_PIS})
    model.execute("draw_offset", {"offsets": [-12, 12]})
    model.query("save_document", {"path": str(tmp_path / "m.rdoc.json")})

    sheets = Session(project_name="SR-100 plans", out_dir=tmp_path)
    sheets.query("save_document", {"path": str(tmp_path / "s.rdoc.json")})
    sheets.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    assert sheets.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                               "path": "m.rdoc.json"})["ok"]

    hits = sheets.query("hit_test", {"space": "model", "point": TARGET, "tolerance": 3})
    assert hits["count"] == 1
    hit = hits["hits"][0]
    assert hit["id"].startswith("DESIGN:") and hit["read_only"] is True
    # the anchor travels through the reference, so the agent knows what it found
    entity = sheets.query("get_entity", {"id": hit["id"]})["entity"]
    anchor = entity["anchor"]
    assert anchor["alignment"] == "SR-100" and anchor["kind"] == "offset"
    assert anchor["offset"] == 12.0 and anchor["placed_by"] == "draw_offset"

    r = sheets.execute("place_callout", {
        "space": "model", "target": TARGET, "position": [1300.0, 800.0],
        "content": f"EP {abs(anchor['offset']):.0f}' RT", "layer": "V-ANNO-TEXT"})
    assert r["ok"], r
    text = parts(sheets, r)[-1]
    assert text.content == "EP 12' RT"
    # the callout is the host's own work; the referenced edge is untouched
    assert len(sheets.doc.model_entities) == 4
    assert text.anchor is None                    # no design model here to anchor to


def test_a_document_with_a_callout_survives_save_and_reload(tmp_path):
    """The dataclasses do not validate on construction, only from_dict does, so
    a handler writing a bad enum saves a file that cannot be opened again."""
    s = model_session(tmp_path)
    s.execute("place_callout", {"space": "model", "target": TARGET,
                                "position": [1450.0, 900.0], "content": "EP 12' RT"})
    path = tmp_path / "callout.rdoc.json"
    assert s.query("save_document", {"path": str(path)})["ok"]
    reopened = Session.load(path, out_dir=tmp_path)
    assert reopened.doc.to_dict() == s.doc.to_dict()
    text = [e for e in reopened.doc.model_entities.values() if isinstance(e, Text)][0]
    assert text.valign == "middle" and text.content == "EP 12' RT"


def test_aiming_by_entity_beats_aiming_by_hand_on_a_curve():
    """target_entity is the fix for the trap: the engine puts the leader tip on
    the arc, where averaging its endpoints would miss by the sagitta."""
    from roaddraft.document.entities import entity_distance
    s = model_session()
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": A_PIS})
    s.execute("draw_offset", {"offsets": [12], "layer": "V-ANNO-TEXT"})
    arc = next(e for e in s.doc.model_entities.values() if e.TYPE == "arc")
    r = s.execute("place_callout", {"space": "model", "target_entity": arc.id,
                                    "at": "mid", "position": [2600.0, 700.0],
                                    "content": "EP"})
    assert r["ok"], r
    leader = parts(s, r)[0]
    assert entity_distance(s.doc, arc, leader.start) < 1e-6
    assert not r["warnings"]
    # start and end land on it too, and differ
    tips = []
    for where in ("start", "end"):
        r = s.execute("place_callout", {"space": "model", "target_entity": arc.id,
                                        "at": where, "position": [2600.0, 700.0],
                                        "content": "EP"})
        tip = parts(s, r)[0].start
        assert entity_distance(s.doc, arc, tip) < 1e-6
        tips.append(tip)
    assert tips[0] != tips[1]


def test_callout_needs_exactly_one_of_target_and_target_entity():
    s = model_session()
    r = s.execute("place_callout", {"space": "model", "position": [0, 0], "content": "A"})
    assert not r["ok"] and "exactly one" in r["error"]["message"]
    assert "target_entity" in r["error"]["hint"]
    r = s.execute("place_callout", {"space": "model", "target": TARGET,
                                    "target_entity": "LN-001", "position": [0, 0],
                                    "content": "A"})
    assert not r["ok"] and "exactly one" in r["error"]["message"]


def test_callout_faults_on_an_id_that_is_not_there_or_in_another_space():
    s = model_session()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r = s.execute("place_callout", {"space": "model", "target_entity": "LN-404",
                                    "position": [0, 0], "content": "A"})
    assert not r["ok"] and "no entity 'LN-404'" in r["error"]["message"]
    assert "REFNAME:ID" in r["error"]["hint"]
    drawn = s.execute("draw_line", {"space": "C-101", "start": [1, 1], "end": [2, 2]})
    r = s.execute("place_callout", {"space": "model",
                                    "target_entity": drawn["created"][0],
                                    "position": [0, 0], "content": "A"})
    assert not r["ok"] and "but the callout goes in" in r["error"]["message"]


def test_a_leader_into_empty_space_says_so():
    """A hand-typed point that misses renders without complaint otherwise."""
    s = model_session()
    s.execute("create_alignment", {"name": "SR-100", "begin_station": "10+00",
                                   "pis": A_PIS})
    s.execute("draw_offset", {"offsets": [12], "layer": "V-ANNO-TEXT"})
    # 88 ft below the edge, in a document that has nothing else in it yet
    r = s.execute("place_callout", {"space": "model", "target": [1300.0, 900.0],
                                    "position": [1450.0, 800.0], "content": "EP"})
    assert r["ok"] and r["warnings"]
    assert "points at empty space" in r["warnings"][0]
    assert "88.00 away" in r["warnings"][0] and "target_entity" in r["warnings"][0]
    # on the edge itself: it says what it landed on, so a wrong line is visible
    r = s.execute("place_callout", {"space": "model", "target": [1300.0, 988.0],
                                    "position": [1450.0, 900.0], "content": "EP"})
    assert r["ok"] and "lands on" in r["warnings"][0]
    assert "12.00' RT of SR-100" in r["warnings"][0]
    # aiming by entity never trips it
    edge = next(e for e in s.doc.model_entities.values()
                if e.anchor and e.anchor.get("kind") == "offset")
    r = s.execute("place_callout", {"space": "model", "target_entity": edge.id,
                                    "position": [1450.0, 800.0], "content": "EP"})
    assert r["ok"] and not r["warnings"]


def test_callout_journal_replays(tmp_path):
    s = model_session(tmp_path)
    s.execute("place_callout", {"space": "model", "target": TARGET,
                                "position": [1450.0, 900.0], "content": "EP 12' RT"})
    path = tmp_path / "callout.journal.jsonl"
    assert s.query("save_journal", {"path": str(path)})["ok"]
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()
