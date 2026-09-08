"""WP1 tests: design/horizontal.py.

Alignment A (spec section 2.3): PIs (1000,1000) / (1814.359354,1000,R800) /
(2433.012702,1357.179677), begin 10+00: tangent 600, curve R=800 Delta=30 L,
tangent 500; length 1518.879; PC 16+00, PI 18+14.36, PT 20+18.88, END 25+18.88.
"""
from __future__ import annotations

import math
import os
import random
import re

import pytest

from roaddraft.design.angles import unit_vector
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (
    ANGLE_EPS,
    CONNECT_TOL,
    ELEMENT_KINDS,
    GEOM_EPS,
    PI,
    Alignment,
    CurveElement,
    TangentElement,
    alignment_from_elements,
    compile_pis,
    curve_data,
    curve_from_pi,
    element_from_dict,
    element_to_dict,
    elements_from_dicts,
    junction_kind,
    pis_from_elements,
    tangent_data,
    validate_continuity,
)
from roaddraft.design.model import DesignModel
from roaddraft.design.stations import StationEquation
from roaddraft.design.vertical import PVI, Profile

A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]
TOL = 1e-3


def make_A(**kw) -> Alignment:
    return Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                     begin_station=1000.0, **kw)


@pytest.fixture
def A():
    return make_A()


def curve_pis(deltas, radii, first_leg, legs, last_leg, start=(0.0, 0.0), d0=0.0):
    """PIs walking from ``start`` with heading ``d0``: legs between PIs, turning by deltas (+ = L)."""
    pts = [list(start)]
    d = d0
    lengths = [first_leg] + list(legs) + [last_leg]
    for i, dl in enumerate(deltas):
        u = unit_vector(d)
        p = pts[-1]
        pts.append([p[0] + lengths[i] * u[0], p[1] + lengths[i] * u[1]])
        d += dl
    u = unit_vector(d)
    p = pts[-1]
    pts.append([p[0] + lengths[-1] * u[0], p[1] + lengths[-1] * u[1]])
    return [PI(pts[0])] + [PI(pts[i + 1], radii[i]) for i in range(len(deltas))] + [PI(pts[-1])]


# ------------------------------------------------------------ curve math


def test_curve_R800_d30_T214_359_L418_879_E28_221_M27_259_C414_110_Dc7_162(A):
    row = curve_data(A, 1)
    assert row["tangent"] == pytest.approx(214.359354, abs=TOL)
    assert row["length"] == pytest.approx(418.879020, abs=TOL)
    assert row["external"] == pytest.approx(28.220944, abs=TOL)
    assert row["mid_ordinate"] == pytest.approx(27.259339, abs=TOL)
    assert row["chord"] == pytest.approx(414.110472, abs=TOL)
    assert row["degree_of_curve_deg"] == pytest.approx(7.1619725, abs=1e-6)
    assert row["degree_of_curve_dms"] == '7°09\'43"'
    assert row["delta_deg"] == pytest.approx(30.0, abs=1e-6)
    assert row["delta_dms"] == '30°00\'00"'
    assert row["radius"] == 800.0 and row["direction"] == "L"
    assert row["alignment"] == "ALIGN-1" and row["index"] == 1 and row["ref"] == "C-1"
    for key in ("pc", "pi", "pt", "center"):
        assert isinstance(row[key], list) and len(row[key]) == 2
    expected_keys = ["alignment", "index", "ref", "direction", "radius", "delta_deg", "delta_dms",
                     "tangent", "length", "external", "mid_ordinate", "chord",
                     "degree_of_curve_deg", "degree_of_curve_dms", "direction_in_deg",
                     "direction_out_deg", "azimuth_in_deg", "azimuth_out_deg", "bearing_in",
                     "bearing_out", "chord_direction_deg", "chord_azimuth_deg", "chord_bearing",
                     "pc_station", "pi_station", "pt_station", "mc_station", "pc_station_text",
                     "pi_station_text", "pt_station_text", "mc_station_text", "pc", "pi", "pt",
                     "center"]
    assert list(row.keys()) == expected_keys


def test_curve_R500_d45_T207_107_L392_699_E41_196_M38_060_C382_683():
    pis = curve_pis([45.0], [500.0], 800.0, [], 800.0)
    al = Alignment("B", compile_pis(pis), pis)
    row = curve_data(al, 1)
    assert row["tangent"] == pytest.approx(207.107, abs=TOL)
    assert row["length"] == pytest.approx(392.699, abs=TOL)
    assert row["external"] == pytest.approx(41.196, abs=TOL)
    assert row["mid_ordinate"] == pytest.approx(38.060, abs=TOL)
    assert row["chord"] == pytest.approx(382.683, abs=TOL)
    assert row["degree_of_curve_deg"] == pytest.approx(11.459156, abs=1e-6)
    assert row["delta_dms"] == '45°00\'00"'


# ------------------------------------------------------------ alignment A


def test_alignment_A_elements_600_curve_500_length_1518_879(A):
    assert [e.kind for e in A.elements] == ["tangent", "curve", "tangent"]
    assert A.elements[0].length == pytest.approx(600.0, abs=TOL)
    assert A.elements[1].length == pytest.approx(418.879, abs=TOL)
    assert A.elements[2].length == pytest.approx(500.0, abs=TOL)
    assert A.length == pytest.approx(1518.879, abs=TOL)
    assert A.elements[1].start_dist == pytest.approx(600.0, abs=TOL)
    assert A.elements[2].start_dist == pytest.approx(1018.879, abs=TOL)
    assert len(A.curves()) == 1 and len(A.tangents()) == 2
    assert A.curve_index(1) == 1
    assert A.tangent_index(2) == 2
    assert A.element_ref(0) == "T-1" and A.element_ref(1) == "C-1" and A.element_ref(2) == "T-2"
    assert A.elements[0].direction_deg == pytest.approx(0.0, abs=1e-6)
    assert A.elements[2].direction_deg == pytest.approx(30.0, abs=1e-6)


def test_A_pc_1600_pi_1814_359_pt_2018_879_end_25_18_88(A):
    row = curve_data(A, 1)
    assert row["pc_station"] == pytest.approx(1600.0, abs=TOL)
    assert row["pi_station"] == pytest.approx(1814.359, abs=TOL)
    assert row["pt_station"] == pytest.approx(2018.879, abs=TOL)
    assert row["mc_station"] == pytest.approx(1809.440, abs=TOL)
    assert row["pc_station_text"] == "16+00.00"
    assert row["pi_station_text"] == "18+14.36"
    assert row["pt_station_text"] == "20+18.88"
    assert row["mc_station_text"] == "18+09.44"
    assert A.end_station == pytest.approx(2518.879, abs=TOL)
    assert A.stations().end_text() == "25+18.88"
    assert A.stations().begin_text() == "10+00.00"


def test_A_center_1600_1800_direction_L_pt_2000_1107_180(A):
    c = A.elements[1]
    assert isinstance(c, CurveElement)
    assert c.center == pytest.approx([1600.0, 1800.0], abs=TOL)
    assert c.direction == "L"
    assert c.pc == pytest.approx([1600.0, 1000.0], abs=TOL)
    assert c.pt == pytest.approx([2000.0, 1107.180], abs=TOL)
    assert c.pi == pytest.approx([1814.359, 1000.0], abs=TOL)
    assert c.direction_in_deg == pytest.approx(0.0, abs=1e-6)
    assert c.direction_out_deg == pytest.approx(30.0, abs=1e-6)
    assert c.ccw_angles() == pytest.approx((270.0, 300.0), abs=1e-6)
    assert A.bbox() == pytest.approx((1000.0, 1000.0, 2433.012702, 1357.179677), abs=TOL)


def test_A_chord_bearing_N75E_back_N90E_ahead_N60E(A):
    row = curve_data(A, 1)
    assert row["chord_bearing"] == 'N 75°00\'00" E'
    assert row["bearing_in"] == 'N 90°00\'00" E'
    assert row["bearing_out"] == 'N 60°00\'00" E'
    assert row["chord_direction_deg"] == pytest.approx(15.0, abs=1e-6)
    assert row["chord_azimuth_deg"] == pytest.approx(75.0, abs=1e-6)
    assert row["azimuth_in_deg"] == pytest.approx(90.0, abs=1e-6)
    assert row["azimuth_out_deg"] == pytest.approx(60.0, abs=1e-6)
    t2 = tangent_data(A, 2)
    assert t2["bearing"] == 'N 60°00\'00" E'
    assert t2["ref"] == "T-2" and t2["index"] == 2
    assert t2["length"] == pytest.approx(500.0, abs=TOL)
    assert t2["start_station"] == pytest.approx(2018.879, abs=TOL)
    assert t2["end_station"] == pytest.approx(2518.879, abs=TOL)
    assert t2["mid_station"] == pytest.approx(2268.879, abs=TOL)
    assert t2["mid_point"] == pytest.approx([2216.506, 1232.180], abs=TOL)
    assert t2["start_station_text"] == "20+18.88" and t2["end_station_text"] == "25+18.88"
    assert t2["mid_station_text"] == "22+68.88"
    t1 = tangent_data(A, 1)
    assert t1["bearing"] == 'N 90°00\'00" E' and t1["azimuth_deg"] == pytest.approx(90.0)
    assert t1["mid_point"] == pytest.approx([1300.0, 1000.0], abs=TOL)
    assert list(t1.keys()) == ["alignment", "index", "ref", "start", "end", "length", "direction_deg",
                               "azimuth_deg", "bearing", "start_station", "end_station", "mid_station",
                               "start_station_text", "end_station_text", "mid_station_text", "mid_point"]
    with pytest.raises(DesignError):
        tangent_data(A, 3)
    with pytest.raises(DesignError):
        curve_data(A, 2)


# ---------------------------------------------------------- station <-> xy


def test_station_1800_xy_1797_923_1024_870_dir_14_324(A):
    p, d, i = A.station_to_xy(1800)
    assert p == pytest.approx([1797.923, 1024.870], abs=TOL)
    assert d == pytest.approx(14.324, abs=1e-3)
    assert i == 1
    assert A.point_at(800) == pytest.approx(p, abs=1e-9)
    assert A.direction_at(800) == pytest.approx(d, abs=1e-9)


def test_station_1800_offset25_1804_108_1000_647_radius_825(A):
    p, d, i = A.station_to_xy(1800, 25)
    assert p == pytest.approx([1804.108, 1000.647], abs=TOL)
    assert math.hypot(p[0] - 1600.0, p[1] - 1800.0) == pytest.approx(825.0, abs=TOL)
    p_left, _, _ = A.station_to_xy(1800, -25)
    assert math.hypot(p_left[0] - 1600.0, p_left[1] - 1800.0) == pytest.approx(775.0, abs=TOL)


def test_station_2300_xy_2243_458_1247_740(A):
    p, d, i = A.station_to_xy(2300)
    assert p == pytest.approx([2243.458, 1247.740], abs=TOL)
    assert d == pytest.approx(30.0, abs=1e-6)
    assert i == 2


def test_station_junction_picks_ahead_element(A):
    p, d, i = A.station_to_xy(1600)
    assert i == 1 and p == pytest.approx([1600.0, 1000.0], abs=TOL)
    p, d, i = A.station_to_xy(1000)
    assert i == 0 and p == pytest.approx([1000.0, 1000.0], abs=TOL)
    p, d, i = A.station_to_xy(A.end_station)
    assert i == 2 and p == pytest.approx([2433.012702, 1357.179677], abs=TOL)
    assert A.element_at(600.0)[0] == 1
    assert A.element_at(A.length) == (2, pytest.approx(500.0, abs=TOL))
    # offset 12 at the PC: right normal of heading 0 is -Y
    p, _, _ = A.station_to_xy(1600, 12)
    assert p == pytest.approx([1600.0, 988.0], abs=TOL)


def test_xy_to_station_2228_458_1273_721_is_2300_offset_neg30(A):
    r = A.xy_to_station([2228.458, 1273.721])
    assert r["station"] == pytest.approx(2300.0, abs=TOL)
    assert r["offset"] == pytest.approx(-30.0, abs=TOL)
    assert r["on_point"] == pytest.approx([2243.458, 1247.740], abs=TOL)
    assert r["direction_deg"] == pytest.approx(30.0, abs=1e-6)
    assert r["element_index"] == 2
    assert set(r.keys()) == {"station", "offset", "on_point", "direction_deg", "element_index"}


def test_xy_to_station_1300_1012_offset_neg12(A):
    r = A.xy_to_station([1300.0, 1012.0])
    assert r["station"] == pytest.approx(1300.0, abs=TOL)
    assert r["offset"] == pytest.approx(-12.0, abs=TOL)
    assert r["on_point"] == pytest.approx([1300.0, 1000.0], abs=TOL)
    assert r["element_index"] == 0 and r["direction_deg"] == pytest.approx(0.0, abs=1e-9)
    r = A.xy_to_station([1600.0, 988.0])  # PC with offset 12 -> covered by the curve
    assert r["station"] == pytest.approx(1600.0, abs=TOL) and r["offset"] == pytest.approx(12.0, abs=TOL)
    r = A.xy_to_station([1804.108, 1000.647])
    assert r["station"] == pytest.approx(1800.0, abs=TOL) and r["offset"] == pytest.approx(25.0, abs=TOL)
    assert r["element_index"] == 1


def test_xy_before_begin_900_raises(A):
    with pytest.raises(DesignError) as ei:
        A.xy_to_station([900.0, 1000.0])
    assert str(ei.value) == ("point (900.00, 1000.00) does not project onto ALIGN-1 "
                             "(stations 10+00.00 to 25+18.88)")
    assert ei.value.hint == "points before BEGIN, after END, or at a curve center have no perpendicular station"
    with pytest.raises(DesignError):
        A.xy_to_station([2433.012702 + 100 * math.cos(math.radians(30)),
                         1357.179677 + 100 * math.sin(math.radians(30))])


def test_xy_at_center_1600_1800_raises(A):
    with pytest.raises(DesignError):
        A.xy_to_station([1600.0, 1800.0])


def test_roundtrip_200_random_stations_offsets_1e6(A):
    rng = random.Random(20260904)
    for _ in range(200):
        s = rng.uniform(A.begin_station, A.end_station)
        o = rng.uniform(-50.0, 50.0)
        p, _, _ = A.station_to_xy(s, o)
        r = A.xy_to_station(p)
        assert r["station"] == pytest.approx(s, abs=1e-6)
        assert r["offset"] == pytest.approx(o, abs=1e-6)


def test_station_2600_outside_raises_10_00_to_25_18_88(A):
    with pytest.raises(DesignError) as ei:
        A.station_to_xy(2600)
    assert str(ei.value) == "station 26+00.00 is outside ALIGN-1 (10+00.00 to 25+18.88)"
    with pytest.raises(DesignError):
        A.station_to_xy(999.0)


# ------------------------------------------------------- other alignments


def test_mirror_A_direction_R_pt_2000_892_820():
    pis = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 642.820323])]
    al = Alignment("MIRROR", compile_pis(pis), pis, begin_station=1000.0)
    c = al.elements[1]
    assert c.direction == "R"
    assert c.pt == pytest.approx([2000.0, 892.820], abs=TOL)
    assert c.center == pytest.approx([1600.0, 200.0], abs=TOL)
    assert c.direction_out_deg == pytest.approx(330.0, abs=1e-6)
    assert c.ccw_angles() == pytest.approx((60.0, 90.0), abs=1e-6)
    assert curve_data(al, 1)["chord_bearing"] == 'N 105°00\'00" E'.replace("N 105", "S 75").replace(" E", " E")
    p, d, _ = al.station_to_xy(1800, 25)
    assert math.hypot(p[0] - 1600.0, p[1] - 200.0) == pytest.approx(775.0, abs=TOL)  # right = toward center
    r = al.xy_to_station(p)
    assert r["station"] == pytest.approx(1800.0, abs=TOL) and r["offset"] == pytest.approx(25.0, abs=TOL)


def test_reverse_curve_B_deltas_26_565_T141_641_L278_189_length_3107_848_stations_858_1136_1971_2249():
    pis = [PI([0.0, 0.0]), PI([1000.0, 0.0], 600.0), PI([2000.0, 500.0], 600.0), PI([3000.0, 500.0])]
    B = Alignment("B", compile_pis(pis), pis)
    assert [e.kind for e in B.elements] == ["tangent", "curve", "tangent", "curve", "tangent"]
    c1, c2 = B.curves()
    assert c1.direction == "L" and c2.direction == "R"
    for c in (c1, c2):
        assert c.delta_deg == pytest.approx(26.565, abs=1e-3)
        assert c.tangent_length == pytest.approx(141.641, abs=TOL)
        assert c.length == pytest.approx(278.189, abs=TOL)
    assert B.length == pytest.approx(3107.848, abs=TOL)
    r1, r2 = curve_data(B, 1), curve_data(B, 2)
    assert r1["pc_station"] == pytest.approx(858.359, abs=TOL)
    assert r1["pt_station"] == pytest.approx(1136.548, abs=TOL)
    assert r2["pc_station"] == pytest.approx(1971.300, abs=TOL)
    assert r2["pt_station"] == pytest.approx(2249.489, abs=TOL)
    assert [junction_kind(B, i) for i in range(4)] == ["pc", "pt", "pc", "pt"]
    assert junction_kind(B, 4) is None and junction_kind(B, -1) is None
    assert B.curve_index(3) == 2 and B.tangent_index(4) == 3
    # continuity of heading through the reverse: PT-1 heading == tangent 2 heading
    assert B.direction_at(c1.end_dist) == pytest.approx(B.elements[2].direction_deg, abs=1e-9)


def test_compound_two_left_30_curves_no_zero_tangent_junction_pcc():
    T = 800.0 * math.tan(math.radians(15.0))
    pis = curve_pis([30.0, 30.0], [800.0, 800.0], 600.0, [2 * T], 500.0)
    els = compile_pis(pis)
    assert [e.kind for e in els] == ["tangent", "curve", "curve", "tangent"]
    C = Alignment("C", els, pis)
    assert junction_kind(C, 0) == "pc"
    assert junction_kind(C, 1) == "pcc"
    assert junction_kind(C, 2) == "pt"
    assert els[1].pt == pytest.approx(els[2].pc, abs=1e-6)
    assert els[2].start_dist == pytest.approx(els[1].end_dist, abs=1e-9)
    # BEGIN->PI-2 is 600 ft, so the first tangent is 600 - T; likewise the last is 500 - T
    assert els[0].length == pytest.approx(600.0 - T, abs=TOL)
    assert els[3].length == pytest.approx(500.0 - T, abs=TOL)
    assert C.length == pytest.approx((600.0 - T) + 2 * 418.879 + (500.0 - T), abs=TOL)
    assert C.curve_index(2) == 2
    # opposite-sense back-to-back curves are a PRC
    pis2 = curve_pis([30.0, -30.0], [800.0, 800.0], 600.0, [2 * T], 500.0)
    C2 = Alignment("C2", compile_pis(pis2), pis2)
    assert junction_kind(C2, 1) == "prc"
    # back-to-back curves cannot be recovered as PIs (source stays elements)
    assert pis_from_elements(els) == []
    assert alignment_from_elements("C", els).source == "elements"


# ---------------------------------------------------------- compile faults


def test_R2300_longer_than_back_tangent_600_raises():
    pis = curve_pis([30.0], [2300.0], 600.0, [], 900.0)
    with pytest.raises(DesignError) as ei:
        compile_pis(pis)
    assert str(ei.value).startswith("curve at PI-2 (T=616.28') is longer than the back tangent from BEGIN (600.00')")
    pis = curve_pis([30.0], [2300.0], 900.0, [], 600.0)
    with pytest.raises(DesignError) as ei:
        compile_pis(pis)
    assert str(ei.value).startswith("curve at PI-2 (T=616.28') is longer than the ahead tangent to END (600.00')")
    # exactly fitting is fine (T == leg)
    compile_pis(curve_pis([30.0], [2300.0], 2300.0 * math.tan(math.radians(15.0)), [], 900.0))


def test_two_R1200_d30_on_600_overlap_43_08_raises():
    pis = curve_pis([30.0, 30.0], [1200.0, 1200.0], 800.0, [600.0], 800.0)
    with pytest.raises(DesignError) as ei:
        compile_pis(pis)
    assert str(ei.value) == ("curves at PI-2 (T=321.54') and PI-3 (T=321.54') overlap by 43.08' on "
                             "the 600.00' tangent between them; reduce a radius or move the PIs")


def test_interior_radius_0_angle_point_raises():
    with pytest.raises(DesignError) as ei:
        compile_pis([PI([0.0, 0.0]), PI([600.0, 0.0], 0.0), PI([1200.0, 600.0])])
    assert str(ei.value) == "PI-2 is an angle point (radius 0); interior PIs must have a curve radius"
    assert ei.value.hint == "pass [x, y, R] for every interior PI"
    with pytest.raises(DesignError) as ei:
        compile_pis([PI([0.0, 0.0], 100.0), PI([600.0, 0.0], 300.0), PI([1200.0, 600.0])])
    assert str(ei.value) == "BEGIN/END PIs cannot carry a radius"
    with pytest.raises(DesignError) as ei:
        compile_pis([PI([0.0, 0.0]), PI([0.005, 0.0], 300.0), PI([1200.0, 600.0])])
    assert str(ei.value) == "PI-1 and PI-2 are coincident"
    with pytest.raises(DesignError):
        compile_pis([PI([0.0, 0.0])])


def test_collinear_pi_raises():
    with pytest.raises(DesignError) as ei:
        compile_pis([PI([0.0, 0.0]), PI([600.0, 0.0], 500.0), PI([1200.0, 0.0])])
    assert str(ei.value) == "PI-2 has no deflection (collinear); remove it"
    with pytest.raises(DesignError) as ei:
        compile_pis([PI([0.0, 0.0]), PI([600.0, 0.0], 500.0), PI([0.0, 0.0])])
    assert str(ei.value) in ("PI-2 deflects 180°", "PI-1 and PI-3 are coincident")
    with pytest.raises(DesignError) as ei:
        curve_from_pi([0, 0], [600, 0], [-600, 0], 500.0, 0.0)
    assert str(ei.value) == "PI deflects 180°"


# ---------------------------------------------------------- serialization


def test_to_dict_from_dict_exact():
    A = make_A(equations=[StationEquation(2000.0, 2000.0, 2500.0)], description="demo")
    d = A.to_dict()
    assert list(d.keys()) == ["name", "description", "source", "begin_station", "pis", "equations", "elements"]
    assert d["name"] == "ALIGN-1" and d["description"] == "demo" and d["source"] == "pis"
    assert d["begin_station"] == 1000.0
    assert d["pis"][1] == {"point": [1814.359354, 1000.0], "radius": 800.0}
    assert d["equations"] == [{"raw_station": 2000.0, "back": 2000.0, "ahead": 2500.0}]
    assert list(d["elements"][0].keys()) == ["kind", "start", "end", "length", "direction_deg", "start_dist"]
    assert list(d["elements"][1].keys()) == ["kind", "pc", "pt", "pi", "center", "radius", "delta_deg",
                                             "direction", "length", "start_dist", "direction_in_deg",
                                             "direction_out_deg"]
    back = Alignment.from_dict(d)
    assert back == A
    assert back.to_dict() == d
    # element_from_dict trusts stored values (no recompute)
    e = dict(d["elements"][0]); e["length"] = 123.0
    assert element_from_dict(e).length == 123.0
    assert element_to_dict(A.elements[1]) == d["elements"][1]
    # defaults: missing pis/equations/description, source inferred
    minimal = {"name": "M", "elements": d["elements"]}
    m = Alignment.from_dict(minimal)
    assert m.pis == [] and m.equations == [] and m.description == "" and m.source == "elements"
    assert m.begin_station == 0.0
    m2 = Alignment.from_dict({"name": "M", "elements": d["elements"], "pis": d["pis"]})
    assert m2.source == "pis"
    with pytest.raises(DesignError):
        Alignment.from_dict({"elements": d["elements"]})
    with pytest.raises(DesignError):
        Alignment.from_dict({"name": "E", "elements": []})
    with pytest.raises(DesignError):
        element_from_dict({"kind": "banana"})
    # DesignModel round trip + fingerprint
    P = Profile("PROF-1", "ALIGN-1", [PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90)])
    model = DesignModel(alignments={"ALIGN-1": A}, profiles={"PROF-1": P})
    md = model.to_dict()
    assert list(md.keys()) == ["alignments", "profiles"]
    model2 = DesignModel.from_dict(md)
    assert model2 == model and model2.to_dict() == md
    assert model.fingerprint().startswith("sha256:") and len(model.fingerprint()) == 7 + 64
    assert model.fingerprint() == model2.fingerprint()
    assert model.fingerprint() != DesignModel().fingerprint()
    assert model.profiles_of("ALIGN-1") == [P] and model.profiles_of("X") == []
    assert DesignModel.from_dict(None).to_dict() == {"alignments": {}, "profiles": {}}
    assert DesignModel.from_dict({}).to_dict() == {"alignments": {}, "profiles": {}}


def test_spiral_element_rejected(A):
    assert ELEMENT_KINDS == ("tangent", "curve", "spiral")
    with pytest.raises(DesignError) as ei:
        element_from_dict({"kind": "spiral"})
    assert str(ei.value) == "spiral elements are not supported in this version"
    with pytest.raises(DesignError) as ei:
        elements_from_dicts([{"kind": "spiral"}])
    assert str(ei.value) == "spiral elements are not supported in this version"
    d = A.to_dict()
    d["elements"][1]["kind"] = "spiral"
    with pytest.raises(DesignError):
        Alignment.from_dict(d)


def test_elements_from_dicts_reproduces_compile_1e6(A):
    minimal = []
    for e in A.elements:
        if isinstance(e, TangentElement):
            minimal.append({"kind": "tangent", "start": e.start, "end": e.end})
        else:
            minimal.append({"kind": "curve", "pc": e.pc, "pt": e.pt, "center": e.center,
                            "direction": e.direction})
    els = elements_from_dicts(minimal)
    assert len(els) == len(A.elements)
    for got, exp in zip(els, A.elements):
        assert got.kind == exp.kind
        assert got.length == pytest.approx(exp.length, abs=1e-6)
        assert got.start_dist == pytest.approx(exp.start_dist, abs=1e-6)
        if isinstance(exp, CurveElement):
            assert got.radius == pytest.approx(exp.radius, abs=1e-6)
            assert got.delta_deg == pytest.approx(exp.delta_deg, abs=1e-6)
            assert got.direction == exp.direction
            assert got.pi == pytest.approx(exp.pi, abs=1e-6)
            assert got.direction_in_deg == pytest.approx(exp.direction_in_deg, abs=1e-6)
            assert got.direction_out_deg == pytest.approx(exp.direction_out_deg, abs=1e-6)
        else:
            assert got.direction_deg == pytest.approx(exp.direction_deg, abs=1e-6)
    # the stored shape is accepted too (and recomputed)
    stored = [dict(x) for x in A.to_dict()["elements"]]
    stored[0]["length"] = 999.0
    assert elements_from_dicts(stored)[0].length == pytest.approx(600.0, abs=1e-6)
    # continuity gap
    gap = [dict(x) for x in minimal]
    gap[1]["pc"] = [1600.0, 1000.05]
    with pytest.raises(DesignError) as ei:
        elements_from_dicts(gap)
    assert str(ei.value) == "element 2 starts 0.050 ft from the end of element 1"
    validate_continuity(els, CONNECT_TOL)
    with pytest.raises(DesignError):
        validate_continuity(elements_from_dicts(minimal[:1]) + elements_from_dicts(minimal[2:]))
    with pytest.raises(DesignError):
        elements_from_dicts([])
    with pytest.raises(DesignError):
        elements_from_dicts([{"kind": "curve", "pc": [0, 0], "pt": [1, 1]}])


def test_pi_recovery_from_elements_source_pis(A):
    els = elements_from_dicts([element_to_dict(e) for e in A.elements])
    al = alignment_from_elements("ALIGN-1", els, begin_station=1000.0, description="x")
    assert al.source == "pis"
    assert len(al.pis) == 3
    assert al.pis[0] == PI([1000.0, 1000.0], 0.0)
    assert al.pis[1].radius == pytest.approx(800.0, abs=1e-6)
    assert al.pis[1].point == pytest.approx([1814.359354, 1000.0], abs=1e-6)
    assert al.pis[2].point == pytest.approx([2433.012702, 1357.179677], abs=1e-6)
    assert al.begin_station == 1000.0 and al.description == "x"
    assert al.elements == els  # stored elements are kept as given (not recompiled)
    recovered = pis_from_elements(A.elements)
    assert [p.radius for p in recovered] == [0.0, 800.0, 0.0]
    # a heading kink between two tangents cannot be reproduced by compile_pis -> source elements
    kink = elements_from_dicts([{"kind": "tangent", "start": [0, 0], "end": [100, 0]},
                                {"kind": "tangent", "start": [100, 0], "end": [200, 50]}])
    al2 = alignment_from_elements("K", kink)
    assert al2.source == "elements" and al2.pis == []
    assert al2.length == pytest.approx(100 + math.hypot(100, 50), abs=1e-9)
    assert al2.station_to_xy(150)[2] == 1
    assert al2.xy_to_station([100.0, 0.0])["station"] == pytest.approx(100.0, abs=1e-9)


def test_no_forbidden_imports_in_design_package():
    import roaddraft.design as pkg
    root = os.path.dirname(pkg.__file__)
    banned = re.compile(r"^\s*(from|import)\s+(roaddraft\.)?(document|commands|api|web|tasks)\b|"
                        r"^\s*from\s+\.\.\s*(document|commands|api|web|tasks)\b|"
                        r"^\s*from\s+\.\.(document|commands|api|web|tasks)\b", re.M)
    offenders = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            src = fh.read()
        for m in banned.finditer(src):
            offenders.append(f"{name}: {m.group(0).strip()}")
    assert offenders == []
    # and nothing CAD-program specific
    for name in sorted(os.listdir(root)):
        if name.endswith(".py"):
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                src = fh.read()
            assert not re.search(r"^\s*(from|import)\s+(pyautocad|win32com|comtypes|arcpy)\b", src, re.M), name
    assert GEOM_EPS == 1e-6 and ANGLE_EPS == 1e-9 and CONNECT_TOL == 1e-3
