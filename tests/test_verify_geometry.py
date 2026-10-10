"""Linework and tick matching (verify.geometry): pieces, arcs told apart by
their midpoints, polylines judged segment by segment, ticks by crossing."""
from __future__ import annotations

import math

from roaddraft.core import geometry as geo
from roaddraft.document.entities import Arc, Line, Polyline
from roaddraft.verify.geometry import (
    crosses_at, element_piece, match_linework, match_ticks, pieces_of, same_piece,
)
from tests.verify_mutations import BASE, Base

TOL = 0.05


def test_line_matches_either_way_round():
    a = pieces_of(Line(id="L1", start=[0, 0], end=[100, 0]))[0]
    b = pieces_of(Line(id="L2", start=[100.01, 0.01], end=[0.02, 0]))[0]
    c = pieces_of(Line(id="L3", start=[0, 0], end=[100.2, 0]))[0]
    assert same_piece(a, b, TOL) and not same_piece(a, c, TOL)


def test_an_arc_is_not_its_complement_through_the_same_ends():
    short = pieces_of(Arc(id="A1", center=[0, 0], radius=100, start_angle_deg=0,
                          end_angle_deg=90))[0]
    long = pieces_of(Arc(id="A2", center=[0, 0], radius=100, start_angle_deg=90,
                         end_angle_deg=360))[0]
    assert geo.distance(short.a, long.b) < 1e-9 and geo.distance(short.b, long.a) < 1e-9
    assert not same_piece(short, long, TOL)


def test_reference_elements_match_their_drawn_entities():
    b = Base(**BASE)
    align = b.doc.design.alignments[b.A]
    res = match_linework(align, list(b.doc.model_entities.values()), "V-ALIGN-CNTR", TOL)
    assert all(len(em.hits) == 1 for em in res.elements) and not res.bad_entities


def test_one_bulged_polyline_through_every_element_matches_them_all():
    b = Base(**BASE)
    align = b.doc.design.alignments[b.A]
    verts, bulges = [list(align.elements[0].start)], []
    for el in align.elements:
        verts.append(list(el.end))
        if el.kind == "curve":
            bulges.append(geo.bulge_of_sweep(math.degrees(el.length / el.radius) * el.sign))
        else:
            bulges.append(0.0)
    pl = Polyline(id="PL-1", layer="V-ALIGN-CNTR", vertices=verts, bulges=bulges)
    res = match_linework(align, [pl], "V-ALIGN-CNTR", TOL)
    assert all(em.hits for em in res.elements) and not res.bad_entities


def test_part_of_a_tangent_is_on_the_design_but_earns_nothing():
    b = Base(**BASE)
    align = b.doc.design.alignments[b.A]
    t = align.elements[0]
    mid = [(t.start[0] + t.end[0]) / 2, (t.start[1] + t.end[1]) / 2]
    half = Line(id="LN-H", layer="V-ALIGN-CNTR", start=list(t.start), end=mid)
    res = match_linework(align, [half], "V-ALIGN-CNTR", TOL)
    assert not res.bad_entities and not any(em.hits for em in res.elements)
    off = Line(id="LN-O", layer="V-ALIGN-CNTR", start=list(t.start), end=[mid[0] + 1, mid[1]])
    assert match_linework(align, [off], "V-ALIGN-CNTR", TOL).bad_entities[0].id == "LN-O"


def test_element_piece_midpoint_lies_on_the_curve():
    b = Base(**BASE)
    align = b.doc.design.alignments[b.A]
    for el in align.curves():
        m = element_piece(el).m
        assert abs(geo.distance(m, el.center) - el.radius) < 1e-6
        assert abs(align.xy_to_station(m)["offset"]) < 1e-6


def test_a_one_sided_square_tick_crosses_but_a_skewed_one_does_not():
    tick = pieces_of(Line(id="T", start=[0, -10], end=[0, 10]))[0]
    one_sided = pieces_of(Line(id="A", start=[0, 0], end=[0, 25]))[0]
    skewed = pieces_of(Line(id="B", start=[0, 0], end=[25 * math.sin(math.radians(5)),
                                                        25 * math.cos(math.radians(5))]))[0]
    beside = pieces_of(Line(id="C", start=[0.2, -10], end=[0.2, 10]))[0]
    assert crosses_at(one_sided, tick, TOL, 1.0)
    assert not crosses_at(skewed, tick, TOL, 1.0)
    assert not crosses_at(beside, tick, TOL, 1.0)


def test_exact_ticks_need_the_stated_length_crossing_ticks_do_not():
    truth = [{"station": 0.0, "station_text": "0+00.00", "start": [0, -10], "end": [0, 10]}]
    long_tick = [Line(id="T", start=[0, -15], end=[0, 15])]
    exact = match_ticks(truth, long_tick, TOL, exact=True)[0]
    loose = match_ticks(truth, long_tick, TOL, exact=False, length_range=(5.0, 100.0))[0]
    assert not exact.hits and exact.near is not None
    assert loose.hits and loose.near is None
    too_long = match_ticks(truth, long_tick, TOL, exact=False, length_range=(5.0, 20.0))[0]
    assert not too_long.hits
