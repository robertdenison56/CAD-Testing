"""WP1 tests: design/anchors.py on alignment A (spec section 3.5)."""
from __future__ import annotations

import pytest

from roaddraft.design.anchors import (
    AnchorPoint, AnchorRef, infer_kind, list_anchors, parse_anchor, resolve_anchor,
)
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.stations import StationEquation

A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]
TOL = 1e-3


@pytest.fixture
def A():
    return Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                     begin_station=1000.0)


def near(p, q, tol=TOL):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def test_PC1_1600_1000_dir0(A):
    ap = resolve_anchor(A, parse_anchor("PC-1"))
    assert isinstance(ap, AnchorPoint)
    assert near(ap.point, [1600.0, 1000.0]) and ap.direction_deg == pytest.approx(0.0)
    assert ap.station == pytest.approx(1600.0, abs=TOL) and ap.station_text == "16+00.00"
    assert ap.kind_hint == "pc" and ap.curve_index == 1 and ap.tangent_index is None
    assert ap.element_index == 1 and ap.region == 1
    assert ap.to_record() == {"alignment": "ALIGN-1", "ref": "PC-1",
                              "station": ap.station, "offset": 0.0}


def test_MC1_1807_055_1027_259_station_1809_440(A):
    ap = resolve_anchor(A, parse_anchor("mc-1"))
    assert ap.ref == "MC-1"
    assert near(ap.point, [1807.055, 1027.259])
    assert ap.station == pytest.approx(1809.440, abs=TOL)
    assert ap.direction_deg == pytest.approx(15.0, abs=1e-6)


def test_PI1_point_1814_359_station_1814_359(A):
    ap = resolve_anchor(A, parse_anchor("PI-1"))
    assert near(ap.point, [1814.359, 1000.0]) and near(ap.on_point, [1814.359, 1000.0])
    assert ap.station == pytest.approx(1814.359, abs=TOL)
    assert ap.direction_deg == pytest.approx(0.0)  # heading of the back tangent
    assert ap.element_index == 1 and ap.curve_index == 1
    off = resolve_anchor(A, parse_anchor("PI-1@10"))
    assert near(off.point, [1814.359, 990.0])  # right of the back tangent


def test_T1_1300_1000_T2_2216_506_1232_180(A):
    t1 = resolve_anchor(A, parse_anchor("T-1"))
    assert near(t1.point, [1300.0, 1000.0]) and t1.tangent_index == 1
    assert t1.station == pytest.approx(1300.0, abs=TOL)
    t2 = resolve_anchor(A, parse_anchor("T-2"))
    assert near(t2.point, [2216.506, 1232.180])
    assert t2.station == pytest.approx(2268.879, abs=TOL)
    assert t2.direction_deg == pytest.approx(30.0, abs=1e-6) and t2.tangent_index == 2


def test_18_00_at_25_1804_108_1000_647(A):
    ap = resolve_anchor(A, parse_anchor("18+00@25"))
    assert ap.ref == "18+00.00" and ap.offset == 25.0
    assert near(ap.point, [1804.108, 1000.647])
    assert near(ap.on_point, [1797.923, 1024.870])
    assert ap.direction_deg == pytest.approx(14.324, abs=1e-3)
    assert ap.curve_index == 1 and ap.tangent_index is None


def test_18_00_at_25L_offset_neg25(A):
    ap = resolve_anchor(A, parse_anchor("18+00@25L"))
    assert ap.offset == -25.0
    right = resolve_anchor(A, parse_anchor("18+00 @ 25R"))
    assert right.offset == 25.0
    assert near(ap.point, [1791.738, 1049.093])


def test_numeric_1800_is_display(A):
    for value in (1800, 1800.0, "1800"):
        ap = resolve_anchor(A, parse_anchor(value))
        assert ap.ref == "18+00.00" and ap.station == pytest.approx(1800.0)
    eq = Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                   begin_station=1000.0, equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    ap = resolve_anchor(eq, parse_anchor(2800))  # display 28+00 -> raw 2300
    assert ap.station == pytest.approx(2300.0) and ap.station_text == "28+00.00"
    assert ap.region == 2


def test_dict_station_region_offset():
    eq = Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                   begin_station=1000.0, equations=[StationEquation(2000.0, 2000.0, 1800.0)])
    ref = parse_anchor({"station": "19+00", "offset": -10, "region": 2})
    assert isinstance(ref, AnchorRef) and ref.region == 2 and ref.offset == -10.0
    ap = resolve_anchor(eq, ref)
    assert ap.station == pytest.approx(2100.0) and ap.region == 2
    with pytest.raises(DesignError):  # ambiguous without a region
        resolve_anchor(eq, parse_anchor({"station": 1900}))
    ref = parse_anchor({"ref": "pc-1", "offset": "25L"})
    assert ref.ref == "PC-1" and ref.offset == -25.0
    with pytest.raises(DesignError):
        parse_anchor({"ref": "PC-1", "station": 1800})
    with pytest.raises(DesignError):
        parse_anchor({"ref": "PC-1", "bogus": 1})


def test_PC3_raises_lists_valid(A):
    with pytest.raises(DesignError) as ei:
        resolve_anchor(A, parse_anchor("PC-3"))
    assert "anchor 'PC-3' does not exist: ALIGN-1 has 1 curve (PC-1)" in str(ei.value)
    assert ei.value.hint.startswith("valid: BEGIN, END, PI-1..PI-1, PC-1..PC-1")
    assert "a station within 10+00.00..25+18.88" in ei.value.hint
    with pytest.raises(DesignError):
        resolve_anchor(A, parse_anchor("EQ-1"))
    with pytest.raises(DesignError) as ei:
        resolve_anchor(A, parse_anchor("26+00"))
    assert "26+00.00" in str(ei.value) and "25+18.88" in str(ei.value)


def test_PC3_no_dash_parse_error_hint():
    with pytest.raises(DesignError) as ei:
        parse_anchor("PC3")
    assert "cannot parse anchor 'PC3'" in str(ei.value)
    assert ei.value.hint and "PC-n" in ei.value.hint
    for bad in ("", "@5", "PC-0", "PC-1@x", True, None, [1, 2]):
        with pytest.raises(DesignError):
            parse_anchor(bad)


def test_infer_kind_from_anchor():
    assert infer_kind(parse_anchor("T-1")) == "bearing"
    assert infer_kind(parse_anchor("PC-2")) == "pc"
    assert infer_kind(parse_anchor("BEGIN")) == "begin"
    assert infer_kind(parse_anchor("EQ-1")) == "equation"
    assert infer_kind(parse_anchor("12+00")) == "station"
    assert infer_kind(parse_anchor("MC-1")) == "mc"


def test_list_anchors_count_2_plus_4_curves_plus_tangents_plus_eq(A):
    aps = list_anchors(A)
    assert [a.ref for a in aps] == ["BEGIN", "END", "PC-1", "PI-1", "PT-1", "MC-1", "T-1", "T-2"]
    eq = Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                   begin_station=1000.0, equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    aps = list_anchors(eq)
    assert len(aps) == 2 + 4 * 1 + 2 + 1 and aps[-1].ref == "EQ-1"
    assert aps[-1].station == pytest.approx(2000.0) and aps[-1].station_text == "25+00.00"
    begin, end = aps[0], aps[1]
    assert begin.station_text == "10+00.00" and end.station_text == "30+18.88"
