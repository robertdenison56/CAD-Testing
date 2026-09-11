"""Constant offsets: pavement edges, shoulders, right of way (design/offsets.py).

Test alignment A: begin 10+00, PIs (1000,1000) - (1814.359354,1000) R=800 -
(2433.012702,1357.179677). It runs due east to PC (1600,1000) at 16+00, turns
LEFT through delta = 30 deg about center (1600,1800), and leaves on a 500 ft
tangent. Centerline length 1518.879 ft; the arc is 800 x pi/6 = 418.879 ft.

Offsets are right-positive, so on an eastbound line +12 is 12 ft SOUTH
(y = 988) and -12 is 12 ft NORTH (y = 1012). The curve's center is north, so
the right offset is the OUTSIDE of the curve: R = 812, arc 812 x pi/6 =
425.1622; the left offset is the inside: R = 788, arc 412.5958.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.design.anchors import parse_offset
from roaddraft.design.errors import DesignError
from roaddraft.design.offsets import offset_length, offset_pieces, offset_radius
from roaddraft.document.entities import Arc, Line

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
TOL = 1e-6


def session_A() -> Session:
    s = Session(project_name="offset-tests")
    assert s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                                          "pis": A_PIS})["ok"]
    s.execute("create_layer", {"name": "V-ROAD-EOP", "color": "yellow"})
    return s


def alignment_A():
    return session_A().doc.design.alignments["ALIGN-1"]


def arc_point(piece, angle_deg):
    return [piece.center[0] + piece.radius * math.cos(math.radians(angle_deg)),
            piece.center[1] + piece.radius * math.sin(math.radians(angle_deg))]


def chain_ends(piece):
    """``(start, end)`` of a piece in stationing order."""
    if piece.kind == "tangent":
        return piece.start, piece.end
    s = arc_point(piece, piece.start_angle_deg)
    e = arc_point(piece, piece.end_angle_deg)
    return (s, e) if piece.direction == "L" else (e, s)


def test_tangent_offsets_right_is_south_988_left_is_north_1012():
    a = alignment_A()
    right = offset_pieces(a, 12.0)[0]
    left = offset_pieces(a, -12.0)[0]
    assert right.start == pytest.approx([1000.0, 988.0], abs=TOL)
    assert right.end == pytest.approx([1600.0, 988.0], abs=TOL)
    assert left.start == pytest.approx([1000.0, 1012.0], abs=TOL)
    assert left.end == pytest.approx([1600.0, 1012.0], abs=TOL)
    # a tangent keeps its direction and its length
    assert right.length == pytest.approx(600.0, abs=TOL)
    assert right.direction_deg == pytest.approx(0.0, abs=TOL)


def test_left_curve_R800_offsets_to_812_outside_788_inside_same_center():
    a = alignment_A()
    outside = offset_pieces(a, 12.0)[1]
    inside = offset_pieces(a, -12.0)[1]
    assert outside.radius == pytest.approx(812.0, abs=TOL)
    assert inside.radius == pytest.approx(788.0, abs=TOL)
    assert outside.center == pytest.approx([1600.0, 1800.0], abs=1e-4)
    assert inside.center == pytest.approx(outside.center, abs=TOL)
    # the angular extent is shared with the centerline, so only radius changes
    assert outside.start_angle_deg == pytest.approx(inside.start_angle_deg, abs=TOL)
    assert outside.end_angle_deg == pytest.approx(inside.end_angle_deg, abs=TOL)
    assert outside.length == pytest.approx(812.0 * math.pi / 6.0, abs=1e-4)   # 425.1622
    assert inside.length == pytest.approx(788.0 * math.pi / 6.0, abs=1e-4)    # 412.5958


def test_offset_chain_is_continuous_no_fillet_needed():
    """Radial lines are shared at the PC and PT, so the pieces meet exactly."""
    a = alignment_A()
    for offset in (-24.0, -12.0, 12.0, 24.0):
        pieces = offset_pieces(a, offset)
        assert len(pieces) == len(a.elements)
        prev_end = None
        for piece in pieces:
            start, end = chain_ends(piece)
            if prev_end is not None:
                assert math.dist(prev_end, start) < 1e-9, (offset, piece.ref)
            prev_end = end


def test_offset_length_1525_1622_outside_1512_5958_inside_vs_1518_879():
    a = alignment_A()
    assert a.length == pytest.approx(1518.879, abs=1e-3)
    assert offset_length(a, 12.0) == pytest.approx(1525.1622, abs=1e-3)
    assert offset_length(a, -12.0) == pytest.approx(1512.5958, abs=1e-3)
    assert offset_length(a, 0.0) == pytest.approx(a.length, abs=1e-6)


def test_offset_past_the_center_of_the_curve_raises():
    a = alignment_A()
    curve = a.curves()[0]
    assert offset_radius(curve, -799.0) == pytest.approx(1.0, abs=TOL)
    for bad in (-800.0, -900.0):
        with pytest.raises(DesignError, match="passes the center"):
            offset_pieces(a, bad)


def test_parse_offset_accepts_numbers_and_the_side_said_out_loud():
    assert parse_offset(12) == 12.0
    assert parse_offset(-12.5) == -12.5
    assert parse_offset("12L") == -12.0
    assert parse_offset("12R") == 12.0
    assert parse_offset("-12") == -12.0
    for bad in ("12X", "left", True):
        with pytest.raises(DesignError):
            parse_offset(bad)


def test_draw_offset_creates_anchored_lines_and_arcs_on_the_layer():
    s = session_A()
    r = s.execute("draw_offset", {"alignment": "ALIGN-1", "offsets": [-12, "12R"],
                                  "layer": "V-ROAD-EOP"})
    assert r["ok"], r
    assert r["message"] == ("ALIGN-1 offset 12.00' LT, 12.00' RT drawn on V-ROAD-EOP: "
                            "4 lines, 2 arcs")
    assert len(r["created"]) == 6 and not r["warnings"]
    ents = [s.doc.model_entities[eid] for eid in r["created"]]
    assert sum(isinstance(e, Line) for e in ents) == 4
    assert sum(isinstance(e, Arc) for e in ents) == 2
    assert all(e.layer == "V-ROAD-EOP" for e in ents)
    for e in ents:
        assert e.anchor["alignment"] == "ALIGN-1" and e.anchor["kind"] == "offset"
        assert e.anchor["placed_by"] == "draw_offset"
        assert e.anchor["offset"] in (-12.0, 12.0)
    left_arc = next(e for e in ents if isinstance(e, Arc) and e.anchor["offset"] == -12.0)
    assert left_arc.radius == pytest.approx(788.0, abs=TOL)
    # the anchor records the station the source element starts at: PC-1 = 16+00
    assert left_arc.anchor["ref"] == "C-1"
    assert left_arc.anchor["station"] == pytest.approx(1600.0, abs=1e-4)


def test_draw_offset_warns_on_a_repeat_and_replace_redraws():
    s = session_A()
    r = s.execute("draw_offset", {"offsets": [-12, -12], "layer": "V-ROAD-EOP"})
    assert r["ok"] and len(r["created"]) == 3
    assert r["warnings"] == ["offset 12.00' LT given twice; drawn once"]
    # drawing the same offset again warns but still draws, as draw_alignment does
    r = s.execute("draw_offset", {"offsets": [-12], "layer": "V-ROAD-EOP"})
    assert r["ok"] and len(r["created"]) == 3
    assert "already drawn" in r["warnings"][0] and "replace=true" in r["warnings"][0]
    # replace clears every earlier piece at that offset, leaving one clean chain
    r = s.execute("draw_offset", {"offsets": [-12], "layer": "V-ROAD-EOP", "replace": True})
    assert r["ok"] and len(r["deleted"]) == 6 and len(r["created"]) == 3
    assert not r["warnings"]
    assert len([e for e in s.doc.model_entities.values()
                if e.anchor and e.anchor["kind"] == "offset"]) == 3


def test_draw_offset_faults_when_the_offset_passes_the_center():
    s = session_A()
    r = s.execute("draw_offset", {"offsets": [-800]})
    assert not r["ok"]
    assert "passes the center" in r["error"]["message"]
    assert r["error"]["hint"]
    assert s.doc.model_entities == {}  # atomic: nothing drawn


def test_draw_offset_journal_replays(tmp_path):
    s = session_A()
    s.execute("draw_offset", {"offsets": [-12, 12], "layer": "V-ROAD-EOP"})
    path = tmp_path / "offset.journal.jsonl"
    assert s.query("save_journal", {"path": str(path)})["ok"]
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()
