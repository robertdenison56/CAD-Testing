"""Lettering a published sheet draws as linework, found by the redraft pipelines
(examples/ppm_redraft/traced.py) and kept on a trace layer of its base file.

Some sample sheets letter with no text layer -- an outlined font, a stroke font, a
dotted "DITCH" -- so the redraft drew their words as roadway and topography
linework, and stripping an alignment's annotation left its bearing behind as strokes
(pilot work, 2026-10-19). The detector has to take words and leave the symbols the
sheets are full of: fence marks along a line, hatching, a row of shrubs, a sprinkler
head, a tick beside a dash. Strokes here are in sheet inches, as the pipelines see them.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples" / "ppm_redraft"))
import traced  # noqa: E402

H = 0.14      # cap height, in
W = 0.09      # letter width
SPACE = 0.04  # between letters

#: a stroke font of straight lines: each letter a list of strokes in a 1 x 1 box
FONT = {
    "H": [[(0, 0), (0, 1)], [(1, 0), (1, 1)], [(0, 0.5), (1, 0.5)]],
    "E": [[(1, 1), (0, 1), (0, 0), (1, 0)], [(0, 0.5), (0.8, 0.5)]],
    "L": [[(0, 1), (0, 0), (1, 0)]],
    "T": [[(0, 1), (1, 1)], [(0.5, 1), (0.5, 0)]],
    "N": [[(0, 0), (0, 1), (1, 0), (1, 1)]],
    "4": [[(0.8, 0), (0.8, 1), (0, 0.35), (1, 0.35)]],
}


def path(pts, dash=None, fill=False):
    return {"id": f"p{id(pts)}", "pts": [tuple(p) for p in pts], "lw": 0.5, "dash": dash,
            "fill": fill, "dest": None}


def word(text, x=10.0, y=10.0, angle=0.0, gaps=None):
    """Strokes lettering ``text`` from (x, y), turned ``angle`` degrees; ``gaps`` gives
    the space after each letter."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    out, along = [], 0.0
    for k, ch in enumerate(text):
        for stroke in FONT[ch]:
            pts = []
            for u, v in stroke:
                px, py = along + u * W, v * H
                pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
            out.append(path(pts))
        along += W + (gaps[k] if gaps else SPACE)
    return out


def traced_of(paths):
    return [p for p in paths if p.get("traced")]


def test_a_word_is_found_and_its_routing_left_alone():
    strokes = word("HELT")
    assert traced.mark(strokes) == 1
    assert len(traced_of(strokes)) == len(strokes)
    assert all(p["dest"] is None for p in strokes)       # the pipeline still routes them


@pytest.mark.parametrize("angle", [0.0, 30.0, 90.0, -62.0])
def test_lettering_at_any_angle(angle):
    strokes = word("THEN", angle=angle)
    assert traced.mark(strokes) == 1 and len(traced_of(strokes)) == len(strokes)


def test_a_bearing_spaced_wide_is_found_a_piece_at_a_time():
    """L-1's "N 01°05'14" W": its letters stand further apart than a word's, so
    the word found takes in the strokes on its own band."""
    strokes = word("N4HE4T", gaps=[0.1, 0.03, 0.03, 0.1, 0.1, 0.1])
    traced.mark(strokes)
    assert len(traced_of(strokes)) == len(strokes)
    # a dash of the line the lettering sits in is not taken in
    dash = path([(10.0 + 6 * (W + 0.1), 10.0 + H / 2), (10.0 + 6 * (W + 0.1) + 0.08, 10.0 + H / 2)])
    strokes = word("HELT") + [dash]
    traced.mark(strokes)
    assert not dash.get("traced")


def _x(cx, cy, r=0.025):
    return [path([(cx - r, cy - r), (cx + r, cy + r)]), path([(cx - r, cy + r), (cx + r, cy - r)])]


def test_fence_marks_along_a_line_are_not_lettering():
    strokes = _x(10.0, 10.0) + [path([(10.03, 10.0), (10.17, 10.0)])] + _x(10.2, 10.0) + \
        [path([(10.23, 10.0), (10.37, 10.0)])] + _x(10.4, 10.0)
    assert traced.mark(strokes) == 0


def test_hatching_and_a_tick_row_are_not_lettering():
    hatch = [path([(10.0 + 0.03 * k, 10.0), (10.12 + 0.03 * k, 10.12)]) for k in range(8)]
    assert traced.mark(hatch) == 0
    ticks = [path([(10.0 + 0.05 * k, 10.0), (10.0 + 0.05 * k, 10.1)]) for k in range(6)]
    assert traced.mark(ticks) == 0


def test_a_row_of_circle_symbols_is_not_lettering():
    def circle(cx, cy, r=0.03):
        return path([(cx + r * math.cos(t * math.pi / 8), cy + r * math.sin(t * math.pi / 8))
                     for t in range(17)])
    assert traced.mark([circle(10.0 + 0.09 * k, 10.0) for k in range(5)]) == 0


def test_a_symbol_on_its_own_is_not_lettering():
    """A sprinkler head: a half circle with a V in it (PPM-204, sixteen of them)."""
    arc = path([(10.06 + 0.06 * math.cos(t * math.pi / 12), 10.0 + 0.06 * math.sin(t * math.pi / 12))
                for t in range(13)])
    vee = path([(10.03, 10.06), (10.06, 10.0), (10.09, 10.06)])
    base = path([(10.0, 10.0), (10.12, 10.0)])
    assert traced.mark([arc, vee, base]) == 0
    # a tick beside a dash
    assert traced.mark([path([(10.0, 10.05), (10.08, 10.05)]),
                        path([(10.1, 10.0), (10.1, 10.12)]),
                        path([(10.1, 10.05), (10.13, 10.05)])]) == 0


def test_only_leftovers_are_looked_at_and_a_config_box_keeps_a_region_out():
    strokes = word("HELT")
    for p in strokes[:3]:
        p["dest"] = "drop:glyph"
    assert traced.mark(strokes) == 0 or not any(p.get("traced") for p in strokes[:3])
    strokes = word("HELT")
    assert traced.mark(strokes, exclude=[(9.0, 9.0, 11.0, 11.0)]) == 0
    strokes = word("HELT")
    assert traced.mark(strokes, keep=lambda p: False) == 0


# ------------------------------------------------- the regenerated redrafts

REDRAFT = ROOT / "examples" / "Exmple Plans" / "Redraft"
L2 = REDRAFT / "Caltrans-PPM" / "2-2.05-Layouts-Profiles-and-Superelevation-Diagrams" / \
    "PPM-046-Route-65-Layout-Example-65-LAYOUT-2"
TRACE_LAYERS = {"V-ANNO-TRACE", "E-TOPO-TRACE", "D-DRAIN-TRACE",
                "P_ROAD_TRACE", "E_TOPO_TRACE", "P_DRAIN_TRACE"}


def _layers(path):
    from roaddraft.document.fileformat import read_document
    doc = read_document(path)
    return [e.get("layer") for e in ((doc.get("model") or {}).get("entities") or {}).values()]


def test_the_redraft_base_files_keep_traced_lettering_on_a_trace_layer():
    """L-2's "ROUTE 65", "EXIT" and "RAMP" were drawn on V-ROAD and V-ROAD-EDGE; the
    rebuilt base keeps them, as drawn, on V-ANNO-TRACE."""
    on = _layers(L2 / "0000000000aa01.rdraft")
    assert on.count("V-ANNO-TRACE") >= 40
    found = [p for p in REDRAFT.rglob("*.rdraft") if TRACE_LAYERS & set(_layers(p))]
    assert len(found) >= 60
    agencies = {p.relative_to(REDRAFT).parts[0] for p in found}
    assert agencies == {"Caltrans-PPM", "WFL", "CFL", "FDOT-NexGen"}
